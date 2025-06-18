from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F, Q, Prefetch
from django.core.cache import cache
from django.http import JsonResponse
from datetime import date, datetime, timedelta
from frontend.utils.cache_helpers import VesselCacheHelper
from vessels.models import Vessel
from transactions.models import InventoryLot, PurchaseOrder, Transaction, Trip
from django.db import models
from .permissions import is_admin_or_manager, admin_or_manager_required
import json
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

@login_required
def dashboard(request):
    """HEAVILY OPTIMIZED: Your current dashboard with caching and query optimization"""
    
    # Get basic stats
    today = date.today()
    now = datetime.now()
    
    # Cache key specific to today and user role (different users might see different data)
    user_role = 'admin' if request.user.is_superuser else 'user'
    cache_key = f'dashboard_data_{today}_{user_role}'
    
    # Try cache first (5 minutes cache)
    cached_data = cache.get(cache_key)
    if cached_data:
        # Add real-time elements that shouldn't be cached
        cached_data['now'] = now
        return render(request, 'frontend/dashboard.html', cached_data)

    all_vessels = Vessel.objects.annotate(
        recent_trip_count=Count(
            'trips',
            filter=Q(trips__trip_date__gte=today - timedelta(days=7))
        ),
        today_transaction_count=Count(
            'transactions',
            filter=Q(transactions__transaction_date=today)
        ),
        
        # ADD: Additional useful stats in same query
        today_revenue=Sum(
            F('transactions__unit_price') * F('transactions__quantity'),
            filter=Q(
                transactions__transaction_type='SALE',
                transactions__transaction_date=today
            ),
            output_field=models.DecimalField()
        ),
        week_revenue=Sum(
            F('transactions__unit_price') * F('transactions__quantity'),
            filter=Q(
                transactions__transaction_type='SALE',
                transactions__transaction_date__gte=today - timedelta(days=7)
            ),
            output_field=models.DecimalField()
        ),
        current_inventory_count=Count(
            'inventory_lots__product',
            distinct=True,
            filter=Q(inventory_lots__remaining_quantity__gt=0)
        )
    ).order_by('-active', 'name')
    
    vessels = VesselCacheHelper.get_active_vessels()
    
    today_sales = Transaction.objects.filter(
        transaction_date=today
    ).aggregate(
        total_revenue=Sum(
            F('unit_price') * F('quantity'), 
            filter=Q(transaction_type='SALE'),
            output_field=models.DecimalField()
        ),
        sales_count=Count('id', filter=Q(transaction_type='SALE')),
        
        total_supply_cost=Sum(
            F('unit_price') * F('quantity'),
            filter=Q(transaction_type='SUPPLY'),
            output_field=models.DecimalField()
        ),
        supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
        
        transfer_out_count=Count('id', filter=Q(transaction_type='TRANSFER_OUT')),
        transfer_in_count=Count('id', filter=Q(transaction_type='TRANSFER_IN')),
        
        total_transactions=Count('id'),
        unique_vessels=Count('vessel', distinct=True),
        unique_products=Count('product', distinct=True),
        
        total_volume=Sum('quantity'),
        avg_transaction_value=models.Avg(
            F('unit_price') * F('quantity'),
            output_field=models.DecimalField()
        )
    )
    
    # Calculate profit metrics (matching your style)
    total_revenue = today_sales['total_revenue'] or 0
    total_supply_cost = today_sales['total_supply_cost'] or 0
    total_profit = total_revenue - total_supply_cost
    profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    # Add profit to today_sales
    today_sales['total_profit'] = total_profit
    today_sales['profit_margin'] = round(profit_margin, 2)
    
    recent_transactions = Transaction.objects.select_related(
        'vessel', 
        'product', 
        'product__category',
        'created_by'
    ).prefetch_related(
        # Better prefetch strategy
        Prefetch('trip', queryset=Trip.objects.select_related('vessel')),
        Prefetch('purchase_order', queryset=PurchaseOrder.objects.select_related('vessel'))
    ).order_by('-created_at')[:6]
    
    active_vessel_count = len([v for v in vessels if v.active])
    
    # Combine trip and PO counts in single operations  
    daily_counts = {
        'today_trips': Trip.objects.filter(trip_date=today).count(),
        'today_pos': PurchaseOrder.objects.filter(po_date=today).count(),
    }
    
    # Low stock calculation (your pattern)
    low_stock_count = InventoryLot.objects.filter(
        remaining_quantity__lte=5,
        remaining_quantity__gt=0
    ).values('product').distinct().count()
    
    # Combine into quick_stats (your exact structure)
    quick_stats = {
        'active_vessels': active_vessel_count,
        'today_trips': daily_counts['today_trips'],
        'today_pos': daily_counts['today_pos'],
        'low_stock_products': low_stock_count,
    }
    
    vessels_with_revenue = [v for v in vessels if hasattr(v, 'week_revenue') and v.week_revenue]
    
    if len(vessels_with_revenue) >= 5:
        # Use data from our enhanced vessel query
        top_vessels = sorted(vessels_with_revenue, key=lambda v: v.week_revenue or 0, reverse=True)[:5]
    else:
        # Fallback to your original query if needed
        top_vessels = Vessel.objects.filter(active=True).annotate(
            recent_revenue=Sum(
                F('transactions__unit_price') * F('transactions__quantity'),
                filter=Q(
                    transactions__transaction_type='SALE',
                    transactions__transaction_date__gte=today - timedelta(days=7)
                ),
                output_field=models.DecimalField()
            ),
            week_trips=Count(
                'trips',
                filter=Q(trips__trip_date__gte=today - timedelta(days=7))
            )
        ).order_by('-recent_revenue')[:5]
    
    # Handle None values safely (your pattern)
    for key in ['total_revenue', 'total_supply_cost', 'sales_count', 'supply_count',
                'transfer_out_count', 'transfer_in_count', 'total_transactions',
                'unique_vessels', 'unique_products', 'total_volume', 'avg_transaction_value']:
        if today_sales[key] is None:
            today_sales[key] = 0
    
    context = {
        'vessels': vessels,
        'all_vessels': all_vessels,
        'today_sales': today_sales,
        'recent_transactions': recent_transactions,
        'quick_stats': quick_stats,
        'top_vessels': top_vessels,
        'today': today,
        'now': now,  # Don't cache this - always current
    }
    
    # Cache everything except 'now' for 5 minutes
    cache_context = {k: v for k, v in context.items() if k != 'now'}
    cache.set(cache_key, cache_context, 300)  # 5 minutes
    
    return render(request, 'frontend/dashboard.html', context)

def get_vessel_badge_class(vessel_name):
    """Helper function to get vessel badge class"""
    colors = {
        'amman': 'bg-primary',
        'aylah': 'bg-danger',
        'sinaa': 'bg-success', 
        'nefertiti': 'bg-secondary',
        'babel': 'bg-warning',
        'dahab': 'bg-info',
    }
    return colors.get(vessel_name.lower(), 'bg-primary')

@login_required
def set_language(request):
    """AJAX endpoint to set user's language preference"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        language = data.get('language', 'en')
        
        # Validate language
        if language not in ['en', 'ar']:
            return JsonResponse({'success': False, 'error': 'Invalid language'})
        
        # Save to session
        request.session['preferred_language'] = language
        
        return JsonResponse({
            'success': True,
            'language': language,
            'message': f'Language set to {language}'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})