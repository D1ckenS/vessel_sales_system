from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction, models
import logging
from django.db.models import Sum, F, Count, Prefetch
from django.db.models.functions import Round
from django.urls import reverse
from frontend.utils.cache_helpers import TripCacheHelper, VesselCacheHelper, get_optimized_pagination
from transactions.models import Transaction, Trip
from vessels.models import Vessel
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from datetime import datetime
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .utils.response_helpers import JsonResponseHelper
from .utils.crud_helpers import CRUDHelper, AdminActionHelper
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required,
    is_admin_or_manager
)

logger = logging.getLogger('frontend')

@login_required
@user_passes_test(is_admin_or_manager)
def trip_management(request):
    """OPTIMIZED: Trip management with COUNT-free pagination"""
    
    # Get filter parameters
    vessel_filter = request.GET.get('vessel')
    status_filter = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    min_revenue = request.GET.get('min_revenue')
    
    # Use EXACT working pattern from trip_reports
    trips_query = Trip.objects.select_related(
        'vessel', 'created_by'
    ).prefetch_related(
        Prefetch(
            'sales_transactions',
            queryset=Transaction.objects.select_related('product', 'product__category')
        )
    ).annotate(
        # Add the WORKING annotation for revenue calculation
        annotated_revenue=Sum(F('sales_transactions__unit_price') * F('sales_transactions__quantity')),
        annotated_transaction_count=Count('sales_transactions')
    ).order_by('-trip_date', '-created_at')
    
    # Apply filters
    if vessel_filter:
        trips_query = trips_query.filter(vessel_id=vessel_filter)
    if status_filter == 'completed':
        trips_query = trips_query.filter(is_completed=True)
    elif status_filter == 'in_progress':
        trips_query = trips_query.filter(is_completed=False)
    if date_from:
        try:
            date_from_parsed = datetime.strptime(date_from, '%Y-%m-%d').date()
            trips_query = trips_query.filter(trip_date__gte=date_from_parsed)
        except ValueError:
            pass
    if date_to:
        try:
            date_to_parsed = datetime.strptime(date_to, '%Y-%m-%d').date()
            trips_query = trips_query.filter(trip_date__lte=date_to_parsed)
        except ValueError:
            pass
    
    # ✅ REPLACE Django Paginator with optimized pagination
    page_number = request.GET.get('page', 1)
    page_obj = get_optimized_pagination(trips_query, page_number, page_size=25, use_count=False)
    
    # Process trips list
    trips_list = page_obj.object_list
    
    # Initialize variables
    total_revenue = 0
    completed_count = 0
    total_passengers = 0
    
    # Process each trip
    for trip in trips_list:
        # Set values for template (CORRECT FIELD NAMES)
        trip_revenue = trip.annotated_revenue or 0
        trip_transaction_count = trip.annotated_transaction_count or 0
        
        trip.annotated_total_revenue = trip_revenue    # ✅ Template expects this field name
        trip.annotated_transaction_count = trip_transaction_count
        
        # Accumulate stats
        total_revenue += trip_revenue
        total_passengers += trip.passenger_count or 0
        
        # Performance classification (use the revenue value directly)
        if trip_revenue > 2000:
            trip.revenue_performance_class = 'high-revenue'
        elif trip_revenue > 1000:
            trip.revenue_performance_class = 'medium-revenue'
        else:
            trip.revenue_performance_class = 'low-revenue'
            
        # Count completed trips
        if trip.is_completed:
            completed_count += 1
    
    # Filter by minimum revenue if specified
    if min_revenue:
        try:
            min_rev = float(min_revenue)
            trips_list = [trip for trip in trips_list if trip.annotated_total_revenue >= min_rev]
        except ValueError:
            pass
    
    # Calculate summary stats
    total_trips = len(trips_list)
    in_progress_trips = total_trips - completed_count
    completion_rate = (completed_count / max(total_trips, 1)) * 100
    avg_revenue_per_trip = total_revenue / max(total_trips, 1)
    avg_passengers_per_trip = total_passengers / max(total_trips, 1)
    
    # Vessel performance analysis
    vessel_stats = {}
    for trip in trips_list:
        vessel_name = trip.vessel.name
        if vessel_name not in vessel_stats:
            vessel_stats[vessel_name] = {
                'vessel': trip.vessel,
                'trip_count': 0,
                'total_revenue': 0,
                'total_passengers': 0
            }
        vessel_stats[vessel_name]['trip_count'] += 1
        vessel_stats[vessel_name]['total_revenue'] += trip.annotated_total_revenue
        vessel_stats[vessel_name]['total_passengers'] += trip.passenger_count or 0
    
    # Top performing vessels
    top_vessels = sorted(
        vessel_stats.values(), 
        key=lambda x: x['total_revenue'], 
        reverse=True
    )[:5]
    
    context = {
        'trips': trips_list,
        'page_obj': page_obj,
        'active_vessels': VesselCacheHelper.get_active_vessels(),
        'top_vessels': top_vessels,
        'stats': {
            'total_trips': total_trips,
            'completed_trips': completed_count,
            'in_progress_trips': in_progress_trips,
            'completion_rate': round(completion_rate, 1),
            'total_revenue': total_revenue,
            'avg_revenue_per_trip': round(avg_revenue_per_trip, 2),
            'total_passengers': total_passengers,
            'avg_passengers_per_trip': round(avg_passengers_per_trip, 1),
        },
        'filters': {
            'vessel': vessel_filter,
            'status': status_filter,
            'date_from': date_from,
            'date_to': date_to,
            'min_revenue': min_revenue,
        }
    }
    
    return render(request, 'frontend/auth/trip_management.html', context)

@login_required
@user_passes_test(is_admin_or_manager)
def edit_trip(request, trip_id):
    """Edit trip details"""
    if request.method == 'GET':
        # FIXED: Include trip items data for cart preservation
        trip_items = []
        if trip.is_completed:
            # Get sales transactions for completed trips
            sales_transactions = Transaction.objects.filter(
                trip=trip,
                transaction_type='SALE'
            ).select_related('product').order_by('created_at')
            
            for sale in sales_transactions:
                trip_items.append({
                    'id': sale.id,
                    'product_id': sale.product.id,
                    'product_name': sale.product.name,
                    'product_item_id': sale.product.item_id,
                    'product_barcode': sale.product.barcode or '',
                    'is_duty_free': sale.product.is_duty_free,
                    'quantity': int(sale.quantity),
                    'unit_price': float(sale.unit_price),
                    'total_amount': float(sale.total_amount),
                    'notes': sale.notes or '',
                    'created_at': sale.created_at.strftime('%H:%M')
                })
        
        trip_data = {
            'id': trip.id,
            'trip_number': trip.trip_number,
            'passenger_count': trip.passenger_count,
            'trip_date': trip.trip_date.strftime('%Y-%m-%d'),
            'notes': trip.notes or '',
            'vessel_id': trip.vessel.id,
            'vessel_name': trip.vessel.name,
            'is_completed': trip.is_completed,
            'total_revenue': float(trip.total_revenue),
            'transaction_count': trip.transaction_count,
        }
        
        return JsonResponse({
            'success': True,
            'trip': trip_data,
            'trip_items': trip_items  # FIXED: Include trip items for preservation
        })
    
    elif request.method == 'POST':
        # Load JSON safely
        data, error = CRUDHelper.safe_json_load(request)
        if error:
            return error
        
        # Get trip safely
        trip, error = CRUDHelper.safe_get_object(Trip, trip_id, 'Trip')
        if error:
            return error
        
        try:
            # Track if status is changing for cache clearing
            status_changed = False
            old_status = trip.is_completed
            
            # Update trip fields with validation
            if 'passenger_count' in data:
                passenger_count = int(data['passenger_count'])
                if passenger_count <= 0:
                    return JsonResponseHelper.error('Passenger count must be positive')
                trip.passenger_count = passenger_count
            
            if 'trip_date' in data:
                trip.trip_date = datetime.strptime(data['trip_date'], '%Y-%m-%d').date()
            
            if 'notes' in data:
                trip.notes = data['notes']
            
            # 🚀 NEW: Handle completion status changes (admin/manager only)
            if 'is_completed' in data:
                # Check permission for status changes
                from .permissions import is_admin_or_manager
                if not is_admin_or_manager(request.user):
                    return JsonResponseHelper.error('Permission denied: Only administrators and managers can change trip status')
                
                new_status = bool(data['is_completed'])
                if new_status != old_status:
                    status_changed = True
                    trip.is_completed = new_status
                    
                    # Log the status change
                    action = "completed" if new_status else "reopened"
                    logger.info(f"🔄 TRIP STATUS CHANGE: Trip {trip.trip_number} {action} by {request.user.username}")
            
            trip.save()
            
            # 🚀 ENHANCED: Clear cache if status changed or always for consistency
            if status_changed:
                TripCacheHelper.clear_cache_after_trip_update(trip_id)
                # Also clear robust cache for status changes
                TripCacheHelper.clear_recent_trips_cache_only_when_needed()
                logger.debug(f"🔥 Enhanced cache cleared due to status change")
            else:
                TripCacheHelper.clear_cache_after_trip_delete(trip_id)
                TripCacheHelper.clear_recent_trips_cache_only_when_needed()
            
            # Create appropriate success message
            if status_changed:
                action = "completed" if trip.is_completed else "reopened for editing"
                message = f'Trip {trip.trip_number} updated and {action} successfully'
            else:
                message = f'Trip {trip.trip_number} updated successfully'
            
            TripCacheHelper.clear_cache_after_trip_delete(trip_id)
            TripCacheHelper.clear_recent_trips_cache_only_when_needed()
            
            return JsonResponseHelper.success(message=message, data={'trip_id': trip.id})
            
        except (ValueError, ValidationError) as e:
            return JsonResponseHelper.error(f'Invalid data: {str(e)}')
        except Exception as e:
            return JsonResponseHelper.error(str(e))

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["DELETE"])
def delete_trip(request, trip_id):
    """Delete trip with cascade option for transactions"""
    # Get trip safely
    trip, error = CRUDHelper.safe_get_object(Trip, trip_id, 'Trip')
    if error:
        return error
    
    # Check force delete
    force_delete = AdminActionHelper.check_force_delete(request)
    
    # OPTIMIZED: Get transaction info in single query
    transactions_info = [
        {
            'product_name': txn['product__name'],
            'quantity': txn['quantity'],
            'unit_price': txn['unit_price'],
            'amount': float(txn['quantity']) * float(txn['unit_price']),
        }
        for txn in trip.sales_transactions.select_related('product').values(
            'product__name', 'quantity', 'unit_price'
        )
    ]
    
    transaction_count = len(transactions_info)
    
    if transaction_count > 0 and not force_delete:
        # Calculate total for confirmation
        total_revenue = sum(
            float(txn['quantity']) * float(txn['unit_price']) 
            for txn in transactions_info
        )
        
        return JsonResponseHelper.requires_confirmation(
            message=f'This trip has {transaction_count} sales transactions. Delete anyway?',
            confirmation_data={
                'transaction_count': transaction_count,
                'total_revenue': total_revenue,
                'transactions': transactions_info
            }
        )
    
    try:
        trip_number = trip.trip_number
        
        if transaction_count > 0:
            # Enhanced: Use individual deletion for proper inventory restoration and error handling
            with transaction.atomic():
                for transaction_obj in trip.sales_transactions.all():
                    transaction_obj.delete()  # This now properly restores inventory and can raise ValidationError
                trip.delete()
            
            TripCacheHelper.clear_cache_after_trip_delete(trip_id)
            TripCacheHelper.clear_recent_trips_cache_only_when_needed()
            
            return JsonResponseHelper.success(
                message=f'Trip {trip_number} and all {transaction_count} transactions deleted successfully. Inventory restored.'
            )
        else:
            # No transactions, safe to delete
            trip.delete()
            
            TripCacheHelper.clear_cache_after_trip_delete(trip_id)
            TripCacheHelper.clear_recent_trips_cache_only_when_needed()
            
            return JsonResponseHelper.success(
                message=f'Trip {trip_number} deleted successfully'
            )

    except ValidationError as e:
        # Enhanced error handling for inventory conflicts
        error_message = str(e)
        
        # Extract message from ValidationError list format
        if error_message.startswith('[') and error_message.endswith(']'):
            error_message = error_message[2:-2]
        
        # Check if it's an inventory-related error
        if "inventory" in error_message.lower() or "lot" in error_message.lower():
            return JsonResponseHelper.error(
                error_message=f"Cannot delete trip due to inventory conflicts: {error_message}",
                error_type='inventory_conflict',
                suggested_actions=[
                    {
                        'action': 'view_transactions',
                        'label': 'View Transaction Log',
                        'url': reverse('frontend:transactions_list'),
                        'description': 'Review the transactions that may be causing conflicts'
                    },
                    {
                        'action': 'contact_admin',
                        'label': 'Contact Administrator',
                        'description': 'Get help resolving the inventory conflict'
                    }
                ]
            )
        else:
            return JsonResponseHelper.error(
                error_message=f"Cannot delete trip: {error_message}",
                error_type='validation_error'
            )
            
    except Exception as e:
        return JsonResponseHelper.error(
            error_message=f"An unexpected error occurred while deleting trip: {str(e)}",
            error_type='system_error'
        )

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def toggle_trip_status(request, trip_id):
    """Toggle trip completion status with proper transaction deletion"""
    # Get trip safely
    trip, error = CRUDHelper.safe_get_object(Trip, trip_id, 'Trip')
    if error:
        return error
    
    try:
        # Determine the action based on current status
        if trip.is_completed:
            # RESTART WORKFLOW: completed → incomplete
            with transaction.atomic():
                # Delete all sales transactions (automatically restores inventory)
                sales_transactions = Transaction.objects.filter(
                    trip=trip,
                    transaction_type='SALE'
                )
                
                transaction_count = sales_transactions.count()
                
                if transaction_count > 0:
                    logger.info(f"🔄 TRIP RESTART: Deleting {transaction_count} sales transactions for trip {trip.trip_number}")
                    
                    # Delete each transaction (triggers inventory restoration via Transaction.delete())
                    for txn in sales_transactions:
                        txn.delete()
                    
                    logger.info(f"✅ TRIP RESTART: Inventory restored for {transaction_count} items")
                
                # Mark as incomplete
                trip.is_completed = False
                trip.save()
                
                # Clear trip cache
                TripCacheHelper.clear_cache_after_trip_update(trip_id)
                
                logger.info(f"🔄 TRIP RESTART: Trip {trip.trip_number} reopened for editing")
            
            # Return redirect response to restart workflow at trip_sales
            return JsonResponse({
                'success': True,
                'action': 'restart_workflow',
                'message': f'Trip {trip.trip_number} reopened successfully. Inventory restored for {transaction_count} items.',
                'redirect_url': reverse('frontend:trip_sales', kwargs={'trip_id': trip_id}),
                'transaction_count': transaction_count,
                'trip_data': {
                    'trip_number': trip.trip_number,
                    'vessel': trip.vessel.name,
                    'is_completed': False
                }
            })
            
        else:
            # SIMPLE TOGGLE: incomplete → completed
            # Use standard toggle (stays on management page)
            trip.is_completed = True
            trip.save()
            
            # Clear trip cache
            TripCacheHelper.clear_cache_after_trip_update(trip_id)
            
            return JsonResponse({
                'success': True,
                'action': 'mark_completed',
                'message': f'Trip {trip.trip_number} marked as completed successfully.',
                'new_status': True,
                'trip_data': {
                    'trip_number': trip.trip_number,
                    'vessel': trip.vessel.name,
                    'is_completed': True
                }
            })
            
    except Exception as e:
        return JsonResponseHelper.error(
            error_message=f"Error toggling trip status: {str(e)}",
            error_type='system_error'
        )

@login_required
@user_passes_test(is_admin_or_manager)
def trip_details(request, trip_id):
    """Get detailed trip information - OPTIMIZED VERSION"""
    try:
        # OPTIMIZED: Single query with all related data
        trip = Trip.objects.select_related(
            'vessel', 'created_by'
        ).prefetch_related(
            'sales_transactions__product'  # Prefetch product data
        ).get(id=trip_id)
        
        # OPTIMIZED: Use prefetched data instead of separate queries
        sales_transactions = trip.sales_transactions.all()  # Uses prefetched data
        
        # Calculate statistics using prefetched data (no additional queries)
        total_revenue = trip.total_revenue  # Uses property with prefetched data
        total_items = sum(sale.quantity for sale in sales_transactions)
        revenue_per_passenger = total_revenue / max(trip.passenger_count, 1)
        
        # Build sales breakdown using prefetched data
        sales_breakdown = []
        for sale in sales_transactions:
            sales_breakdown.append({
                'product_name': sale.product.name,  # Uses prefetched data
                'quantity': float(sale.quantity),
                'unit_price': float(sale.unit_price),
                'total_amount': float(sale.total_amount),
            })
        
        return JsonResponseHelper.success(data={
            'trip': {
                'trip_number': trip.trip_number,
                'vessel_name': trip.vessel.name,  # Uses select_related data
                'vessel_name_ar': trip.vessel.name_ar,
                'trip_date': trip.trip_date.strftime('%d/%m/%Y'),
                'passenger_count': trip.passenger_count,
                'is_completed': trip.is_completed,
                'created_by': trip.created_by.username if trip.created_by else 'System',
                'notes': trip.notes,
            },
            'statistics': {
                'total_revenue': float(total_revenue),
                'total_items': total_items,
                'revenue_per_passenger': float(revenue_per_passenger),
            },
            'sales_breakdown': sales_breakdown,
        })
        
    except Trip.DoesNotExist:
        return JsonResponseHelper.not_found('Trip')
    except Exception as e:
        return JsonResponseHelper.error(str(e))