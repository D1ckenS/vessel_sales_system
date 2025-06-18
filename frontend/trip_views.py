from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction, models
from django.db.models import Sum, F, Count, Prefetch
from django.db.models.functions import Round
from frontend.utils.cache_helpers import VesselCacheHelper
from transactions.models import Transaction, Trip
from vessels.models import Vessel
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from datetime import datetime
from django.core.cache import cache
from .utils.response_helpers import JsonResponseHelper
from .utils.crud_helpers import CRUDHelper, AdminActionHelper
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required,
    is_admin_or_manager
)

@login_required
@user_passes_test(is_admin_or_manager)
def trip_management(request):
    """OPTIMIZED: Trip management following inventory pattern - 4-5 queries max"""
    
    # Get filter parameters
    vessel_filter = request.GET.get('vessel')
    status_filter = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    min_revenue = request.GET.get('min_revenue')
    
    # OPTIMIZED: Simple base query like inventory_views.py
    trips_query = Trip.objects.select_related(
        'vessel', 'created_by'
    ).prefetch_related(
        'sales_transactions'
    ).order_by('-trip_date', '-created_at')
    
    # Apply filters (same as before)
    if vessel_filter:
        trips_query = trips_query.filter(vessel_id=vessel_filter)
    if status_filter == 'completed':
        trips_query = trips_query.filter(is_completed=True)
    elif status_filter == 'in_progress':
        trips_query = trips_query.filter(is_completed=False)
    if date_from:
        trips_query = trips_query.filter(trip_date__gte=date_from)
    if date_to:
        trips_query = trips_query.filter(trip_date__lte=date_to)
    
    # OPTIMIZED: Get limited dataset early like inventory does
    trips_list = list(trips_query[:50])
    
    # OPTIMIZED: Calculate everything in Python using prefetched data
    total_revenue = 0
    completed_count = 0
    vessel_revenues = {}
    
    for trip in trips_list:
        # Calculate revenue using prefetched sales_transactions (no additional queries)
        trip_revenue = sum(
            float(txn.quantity) * float(txn.unit_price) 
            for txn in trip.sales_transactions.all()
        )
        trip_transaction_count = len(trip.sales_transactions.all())
        
        # Add calculated fields to trip object for template
        trip.annotated_total_revenue = trip_revenue
        trip.annotated_transaction_count = trip_transaction_count
        trip.revenue_per_passenger = round(
            trip_revenue / max(trip.passenger_count, 1), 2
        ) if trip.passenger_count > 0 else 0
        
        # Performance classification in Python
        if trip.revenue_per_passenger >= 50:
            trip.revenue_performance_class = 'high'
        elif trip.revenue_per_passenger >= 25:
            trip.revenue_performance_class = 'medium'
        else:
            trip.revenue_performance_class = 'low'
        
        # Apply min_revenue filter in Python
        if min_revenue and trip_revenue < float(min_revenue):
            continue
            
        # Accumulate stats
        total_revenue += trip_revenue
        if trip.is_completed:
            completed_count += 1
        
        # Vessel performance tracking
        vessel_key = trip.vessel.name
        if vessel_key not in vessel_revenues:
            vessel_revenues[vessel_key] = {
                'vessel__name': trip.vessel.name,
                'vessel__name_ar': trip.vessel.name_ar,
                'trip_count': 0,
                'vessel_total_revenue': 0
            }
        vessel_revenues[vessel_key]['trip_count'] += 1
        vessel_revenues[vessel_key]['vessel_total_revenue'] += trip_revenue
    
    # Calculate final stats
    total_trips = len(trips_list)
    in_progress_count = total_trips - completed_count
    
    # OPTIMIZED: Vessel performance calculated from processed data
    vessel_performance = []
    for vessel_data in vessel_revenues.values():
        avg_monthly = vessel_data['trip_count'] / 12.0
        
        # Performance classification
        if avg_monthly >= 10:
            performance_class = 'high'
            performance_icon = 'arrow-up-circle'
            badge_class = 'bg-success'
        elif avg_monthly >= 5:
            performance_class = 'medium'
            performance_icon = 'dash-circle'
            badge_class = 'bg-warning'
        else:
            performance_class = 'low'
            performance_icon = 'arrow-down-circle'
            badge_class = 'bg-danger'
        
        vessel_performance.append({
            'vessel__name': vessel_data['vessel__name'],
            'vessel__name_ar': vessel_data['vessel__name_ar'],
            'trip_count': vessel_data['trip_count'],
            'avg_monthly': round(avg_monthly, 1),
            'vessel_total_revenue': vessel_data['vessel_total_revenue'],
            'performance_class': performance_class,
            'performance_icon': performance_icon,
            'badge_class': badge_class,
        })
    
    # Sort vessel performance by trip count
    vessel_performance.sort(key=lambda x: x['trip_count'], reverse=True)
    
    # OPTIMIZED: Get vessels for filter in single query
    vessels = VesselCacheHelper.get_active_vessels()
    
    context = {
        'trips': trips_list,
        'vessels': vessels,
        'vessel_performance': vessel_performance,
        'stats': {
            'total_trips': total_trips,
            'completed_trips': completed_count,
            'in_progress_trips': in_progress_count,
            'total_revenue': total_revenue,
            'daily_average': round(total_trips / 30.0, 1),
            'completion_rate': round((completed_count / max(total_trips, 1)) * 100, 1),
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
        # Get trip safely with vessel data
        trip, error = CRUDHelper.safe_get_object(Trip, trip_id, 'Trip')
        if error:
            return error
            
        return JsonResponseHelper.success(data={
            'trip': {
                'id': trip.id,
                'trip_number': trip.trip_number,
                'passenger_count': trip.passenger_count,
                'trip_date': trip.trip_date.strftime('%Y-%m-%d'),
                'notes': trip.notes or '',
                'vessel_id': trip.vessel.id,
                'vessel_name': trip.vessel.name,
            }
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
            
            trip.save()
            
            return JsonResponseHelper.success(
                message=f'Trip {trip.trip_number} updated successfully'
            )
            
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
            # OPTIMIZED: Bulk operations in transaction
            with transaction.atomic():
                # Delete all related transactions
                trip.sales_transactions.all().delete()
                trip.delete()
            
            return JsonResponseHelper.success(
                message=f'Trip {trip_number} and all {transaction_count} transactions deleted successfully. Inventory restored.'
            )
        else:
            # No transactions, safe to delete
            trip.delete()
            return JsonResponseHelper.success(
                message=f'Trip {trip_number} deleted successfully'
            )
        
    except Exception as e:
        return JsonResponseHelper.error(str(e))

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def toggle_trip_status(request, trip_id):
    """Toggle trip completion status"""
    # Get trip safely
    trip, error = CRUDHelper.safe_get_object(Trip, trip_id, 'Trip')
    if error:
        return error
    
    # Toggle status with standardized response
    return CRUDHelper.toggle_boolean_field(trip, 'is_completed', 'Trip')

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