from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction, models
from django.db.models import Sum, F, Count
from transactions.models import Trip
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
    """FIXED: Trip management with resolved property conflicts"""
    
    # Get filter parameters
    vessel_filter = request.GET.get('vessel')
    status_filter = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    min_revenue = request.GET.get('min_revenue')
    
    # FIXED: Use different annotation names to avoid conflicts
    trips_query = Trip.objects.select_related(
        'vessel', 'created_by'
    ).prefetch_related(
        'sales_transactions'
    ).annotate(
        # Use different names to avoid property conflicts
        annotated_total_revenue=Sum(
            F('sales_transactions__unit_price') * F('sales_transactions__quantity'),
            output_field=models.DecimalField()
        ),
        annotated_transaction_count=Count('sales_transactions'),
        # Calculate revenue per passenger
        revenue_per_passenger=models.Case(
            models.When(
                passenger_count__gt=0, 
                then=F('annotated_total_revenue') / F('passenger_count')
            ),
            default=0,
            output_field=models.DecimalField()
        ),
        # Performance classification
        revenue_performance_class=models.Case(
            models.When(revenue_per_passenger__gte=50, then=models.Value('high')),
            models.When(revenue_per_passenger__gte=25, then=models.Value('medium')),
            default=models.Value('low'),
            output_field=models.CharField()
        )
    ).order_by('-trip_date', '-created_at')
    
    # Apply filters
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
    if min_revenue:
        trips_query = trips_query.filter(annotated_total_revenue__gte=min_revenue)
    
    # FIXED: Statistics using the annotation names
    stats = trips_query.aggregate(
        total_trips=Count('id'),
        completed_trips=Count('id', filter=models.Q(is_completed=True)),
        total_revenue=Sum('annotated_total_revenue'),
        avg_daily_trips=Count('id') / 30.0
    )
    
    stats['in_progress_trips'] = stats['total_trips'] - stats['completed_trips']
    stats['completion_rate'] = (stats['completed_trips'] / max(stats['total_trips'], 1)) * 100
    
    # Vessel performance (keep as separate query)
    vessel_performance = Trip.objects.values(
        'vessel__name', 'vessel__name_ar'
    ).annotate(
        trip_count=Count('id'),
        avg_monthly=Count('id') / 12.0,
        vessel_total_revenue=Sum(
            F('sales_transactions__unit_price') * F('sales_transactions__quantity'),
            output_field=models.DecimalField()
        ),
        performance_class=models.Case(
            models.When(avg_monthly__gte=10, then=models.Value('high')),
            models.When(avg_monthly__gte=5, then=models.Value('medium')),
            default=models.Value('low'),
            output_field=models.CharField()
        ),
        performance_icon=models.Case(
            models.When(avg_monthly__gte=10, then=models.Value('arrow-up-circle')),
            models.When(avg_monthly__gte=5, then=models.Value('dash-circle')),
            default=models.Value('arrow-down-circle'),
            output_field=models.CharField()
        ),
        badge_class=models.Case(
            models.When(avg_monthly__gte=10, then=models.Value('bg-success')),
            models.When(avg_monthly__gte=5, then=models.Value('bg-warning')),
            default=models.Value('bg-danger'),
            output_field=models.CharField()
        )
    ).order_by('-trip_count')
    
    context = {
        'trips': trips_query[:50],  # Limit for performance
        'vessels': Vessel.objects.filter(active=True).order_by('name'),
        'vessel_performance': vessel_performance,
        'stats': {
            'total_trips': stats['total_trips'],
            'completed_trips': stats['completed_trips'],
            'in_progress_trips': stats['in_progress_trips'],
            'total_revenue': stats['total_revenue'] or 0,
            'daily_average': round(stats['avg_daily_trips'], 1),
            'completion_rate': round(stats['completion_rate'], 1),
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