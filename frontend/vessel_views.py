from django.utils import timezone
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db import models
from django.db.models import Sum, F, Count, Q
from frontend.utils.validation_helpers import ValidationHelper
from transactions.models import Transaction, Trip, PurchaseOrder
from vessels.models import Vessel
from django.views.decorators.http import require_http_methods
from datetime import date, datetime, timedelta
import json
from django.core.cache import cache
from .permissions import is_admin_or_manager
from transactions.models import get_all_vessel_pricing_summary, get_vessel_pricing_warnings
from .utils.response_helpers import JsonResponseHelper
from .utils.crud_helpers import CRUDHelper
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

@login_required
@user_passes_test(is_admin_or_manager)
def vessel_management(request):
    """CLEANED: Vessel management - removed unused pricing warnings collection"""
    
    reference_date = date.today()
    thirty_days_ago = reference_date - timedelta(days=30)
    
    vessels_data = Vessel.objects.annotate(
        total_trips=Count(
            'trips', 
            filter=models.Q(trips__is_completed=True),
            distinct=True
        ),
        trips_30d=Count(
            'trips',
            filter=models.Q(
                trips__is_completed=True,
                trips__trip_date__gte=thirty_days_ago,
                trips__trip_date__lte=reference_date
            ),
            distinct=True
        ),
        revenue_30d=models.Sum(
            models.Case(
                models.When(
                    transactions__transaction_type='SALE',
                    transactions__transaction_date__gte=thirty_days_ago,
                    transactions__transaction_date__lte=reference_date,
                    then=models.F('transactions__unit_price') * models.F('transactions__quantity')
                ),
                default=0,
                output_field=models.DecimalField()
            )
        ),
        total_passengers_30d=models.Sum(
            'trips__passenger_count',
            filter=models.Q(
                trips__is_completed=True,
                trips__trip_date__gte=thirty_days_ago,
                trips__trip_date__lte=reference_date
            )
        )
    ).order_by('name')
    
    vessel_stats = vessels_data.aggregate(
        total_vessels=Count('id'),
        active_vessels=Count('id', filter=models.Q(active=True)),
        duty_free_vessels=Count('id', filter=models.Q(has_duty_free=True)),
        inactive_vessels=Count('id', filter=models.Q(active=False))
    )
    
    pricing_summary = get_all_vessel_pricing_summary()
    
    vessel_data = []
    
    for vessel in vessels_data:
        pricing_warnings = get_vessel_pricing_warnings(vessel)
        
        if vessel.has_duty_free:
            pricing_data = {
                'is_duty_free': True,
                'completion_percentage': 100,
                'products_priced': 0,
                'total_products': 0
            }
        else:
            total_general_products = pricing_summary['total_general_products']
            missing_count = pricing_warnings['missing_price_count']
            products_priced = total_general_products - missing_count
            completion_pct = (products_priced / max(total_general_products, 1)) * 100
            
            pricing_data = {
                'is_duty_free': False,
                'completion_percentage': round(completion_pct, 0),
                'products_priced': products_priced,
                'total_products': total_general_products
            }
        
        vessel_data.append({
            'vessel': vessel,
            'trips_30d': vessel.trips_30d or 0,
            'total_trips': vessel.total_trips or 0,
            'revenue_30d': float(vessel.revenue_30d or 0),
            'total_passengers_30d': vessel.total_passengers_30d or 0,
            'pricing_warnings': pricing_warnings,
            'pricing_data': pricing_data,
        })
    
    context = {
        'vessel_data': vessel_data,
        'stats': vessel_stats,
        'pricing_summary': pricing_summary,
        'reference_date': reference_date,
        'thirty_days_ago': thirty_days_ago,
        'today': date.today(),
    }
    
    return render(request, 'frontend/auth/vessel_management.html', context)

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def vessel_data_ajax(request):
    """CLEANED: AJAX endpoint - removed unused pricing warnings"""
    
    try:
        data = json.loads(request.body)
        selected_date = data.get('date')
        
        if not selected_date:
            return JsonResponse({'success': False, 'error': 'Date required'})
        
        reference_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        thirty_days_ago = reference_date - timedelta(days=30)
        
        vessels_data = Vessel.objects.annotate(
            total_trips=Count(
                'trips', 
                filter=models.Q(trips__is_completed=True),
                distinct=True
            ),
            trips_30d=Count(
                'trips',
                filter=models.Q(
                    trips__is_completed=True,
                    trips__trip_date__gte=thirty_days_ago,
                    trips__trip_date__lte=reference_date
                ),
                distinct=True
            ),
            revenue_30d=models.Sum(
                models.Case(
                    models.When(
                        transactions__transaction_type='SALE',
                        transactions__transaction_date__gte=thirty_days_ago,
                        transactions__transaction_date__lte=reference_date,
                        then=models.F('transactions__unit_price') * models.F('transactions__quantity')
                    ),
                    default=0,
                    output_field=models.DecimalField()
                )
            ),
            total_passengers_30d=models.Sum(
                'trips__passenger_count',
                filter=models.Q(
                    trips__is_completed=True,
                    trips__trip_date__gte=thirty_days_ago,
                    trips__trip_date__lte=reference_date
                )
            )
        ).order_by('name')
        
        vessel_data = list(vessels_data.values(
            'id', 'name', 'name_ar', 'has_duty_free', 'active',
            'trips_30d', 'total_trips', 'revenue_30d', 'total_passengers_30d'
        ))
        
        for vessel in vessel_data:
            vessel['vessel_id'] = vessel.pop('id')
            vessel['vessel_name'] = vessel.pop('name')
            vessel['vessel_name_ar'] = vessel.pop('name_ar')
            vessel['revenue_30d'] = float(vessel['revenue_30d'] or 0)
            vessel['trips_30d'] = vessel['trips_30d'] or 0
            vessel['total_trips'] = vessel['total_trips'] or 0
            vessel['total_passengers_30d'] = vessel['total_passengers_30d'] or 0
        
        return JsonResponse({
            'success': True,
            'vessel_data': vessel_data,
            'reference_date': reference_date.strftime('%Y-%m-%d'),
            'date_range': f"{thirty_days_ago.strftime('%d/%m/%Y')} - {reference_date.strftime('%d/%m/%Y')}",
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_admin_or_manager)
def create_vessel(request):
    """Create new vessel with validation"""
    if request.method == 'POST':
        data = {
            'name': request.POST.get('name', '').strip(),
            'name_ar': request.POST.get('name_ar', '').strip(),
            'has_duty_free': request.POST.get('has_duty_free') == 'on',
            'active': request.POST.get('active') == 'on'
        }
        
        valid, error = ValidationHelper.validate_vessel_data(data)
        if not valid:
            return error
        
        try:
            vessel = Vessel.objects.create(
                name=data['name'],
                name_ar=data['name_ar'],
                has_duty_free=data['has_duty_free'],
                active=data['active'],
                created_by=request.user
            )
            
            return JsonResponseHelper.success(
                message=f'Vessel "{vessel.name}" created successfully',
                data={
                    'vessel_id': vessel.id,
                    'vessel_name': vessel.name
                }
            )
            
        except Exception as e:
            return JsonResponseHelper.error(str(e))
    
    return JsonResponseHelper.method_not_allowed(['POST'])

@login_required
@user_passes_test(is_admin_or_manager)
def edit_vessel(request, vessel_id):
    """Edit existing vessel"""
    if request.method == 'POST':
        vessel, error = CRUDHelper.safe_get_object(Vessel, vessel_id, 'Vessel')
        if error:
            return error
        
        data = {
            'name': request.POST.get('name', '').strip(),
            'name_ar': request.POST.get('name_ar', '').strip(),
            'has_duty_free': request.POST.get('has_duty_free') == 'on',
            'active': request.POST.get('active') == 'on'
        }
        
        valid, error = ValidationHelper.validate_vessel_data(data, vessel.id)
        if not valid:
            return error
        
        try:
            # Update vessel
            vessel.name = data['name']
            vessel.name_ar = data['name_ar'] 
            vessel.has_duty_free = data['has_duty_free']
            vessel.active = data['active']
            vessel.save()
            
            return JsonResponseHelper.success(
                message=f'Vessel "{vessel.name}" updated successfully',
                vessel_name=vessel.name
            )
            
        except Exception as e:
            return JsonResponseHelper.error(str(e))
    
    return JsonResponseHelper.method_not_allowed(['POST'])

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def toggle_vessel_status(request, vessel_id):
    """Toggle vessel active status"""
    vessel, error = CRUDHelper.safe_get_object(Vessel, vessel_id, 'Vessel')
    if error:
        return error
    
    if vessel.active:
        incomplete_counts = {
            'incomplete_trips': Trip.objects.filter(vessel=vessel, is_completed=False).count(),
            'incomplete_pos': PurchaseOrder.objects.filter(vessel=vessel, is_completed=False).count()
        }
        
        total_incomplete = sum(incomplete_counts.values())
        if total_incomplete > 0:
            return JsonResponseHelper.error(
                f'Cannot deactivate vessel. Has {incomplete_counts["incomplete_trips"]} incomplete trips and {incomplete_counts["incomplete_pos"]} incomplete purchase orders.'
            )
    
    return CRUDHelper.toggle_boolean_field(vessel, 'active', 'Vessel')

@login_required
@user_passes_test(is_admin_or_manager)
def vessel_statistics(request, vessel_id):
    """Get detailed vessel statistics - OPTIMIZED VERSION"""
    vessel, error = CRUDHelper.safe_get_object(Vessel, vessel_id, 'Vessel')
    if error:
        return error
    
    try:
        today = timezone.now().date()
        thirty_days_ago = today - timedelta(days=30)
        ninety_days_ago = today - timedelta(days=90)
        
        trip_stats = Trip.objects.filter(vessel=vessel).aggregate(
            total_trips=Count('id', filter=Q(is_completed=True)),
            trips_30d=Count('id', filter=Q(
                trip_date__gte=thirty_days_ago, 
                is_completed=True
            )),
            total_passengers=Sum('passenger_count', filter=Q(is_completed=True))
        )
        
        transaction_stats = Transaction.objects.filter(
            vessel=vessel, transaction_type='SALE'
        ).aggregate(
            total_revenue=Sum(
                F('unit_price') * F('quantity'), 
                output_field=models.DecimalField()
            ),
            revenue_30d=Sum(
                F('unit_price') * F('quantity'),
                filter=Q(transaction_date__gte=thirty_days_ago),
                output_field=models.DecimalField()
            ),
            transaction_count_90d=Count('id', filter=Q(
                transaction_date__gte=ninety_days_ago
            ))
        )
        
        for key in trip_stats:
            if trip_stats[key] is None:
                trip_stats[key] = 0
                
        for key in transaction_stats:
            if transaction_stats[key] is None:
                transaction_stats[key] = 0
        
        avg_revenue_per_passenger = (
            transaction_stats['total_revenue'] / max(trip_stats['total_passengers'], 1)
        )
        
        top_products = list(Transaction.objects.filter(
            vessel=vessel,
            transaction_type='SALE',
            transaction_date__gte=ninety_days_ago
        ).values('product__name').annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum(
                F('unit_price') * F('quantity'), 
                output_field=models.DecimalField()
            )
        ).order_by('-total_quantity')[:10])
        
        monthly_performance = []
        
        month_ranges = []
        for i in range(11, -1, -1):
            month_date = today - timedelta(days=i*30)
            month_start = date(month_date.year, month_date.month, 1)
            
            if month_date.month == 12:
                month_end = date(month_date.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(month_date.year, month_date.month + 1, 1) - timedelta(days=1)
            
            month_ranges.append((month_date, month_start, month_end))
        
        monthly_transactions = Transaction.objects.filter(
            vessel=vessel,
            transaction_type='SALE',
            transaction_date__gte=month_ranges[0][1],
            transaction_date__lte=month_ranges[-1][2]
        ).values('transaction_date').annotate(
            monthly_revenue=Sum(
                F('unit_price') * F('quantity'), 
                output_field=models.DecimalField()
            )
        )
        
        monthly_data = {}
        for txn in monthly_transactions:
            month_key = txn['transaction_date'].strftime('%Y-%m')
            if month_key not in monthly_data:
                monthly_data[month_key] = 0
            monthly_data[month_key] += float(txn['monthly_revenue'] or 0)
        
        for month_date, month_start, month_end in month_ranges:
            month_key = month_start.strftime('%Y-%m')
            monthly_performance.append({
                'month': month_date.strftime('%b %Y'),
                'revenue': monthly_data.get(month_key, 0)
            })
        
        return JsonResponseHelper.success(data={
            'vessel': {
                'name': vessel.name,
                'name_ar': vessel.name_ar,
                'has_duty_free': vessel.has_duty_free,
                'active': vessel.active,
            },
            'statistics': {
                'total_trips': trip_stats['total_trips'],
                'trips_30d': trip_stats['trips_30d'],
                'total_revenue': float(transaction_stats['total_revenue']),
                'revenue_30d': float(transaction_stats['revenue_30d']),
                'total_passengers': trip_stats['total_passengers'],
                'avg_revenue_per_passenger': float(avg_revenue_per_passenger),
            },
            'top_products': top_products,
            'monthly_performance': monthly_performance,
        })
        
    except Exception as e:
        return JsonResponseHelper.error(str(e))