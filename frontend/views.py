from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F, Q
from django.http import JsonResponse
from datetime import date, datetime, timedelta
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
    """OPTIMIZED: Main dashboard with minimal database queries"""
    
    # Get basic stats
    today = date.today()
    now = datetime.now()
    
    # All vessels with activity statistics
    all_vessels = Vessel.objects.annotate(
        recent_trip_count=Count(
            'trips',
            filter=Q(trips__trip_date__gte=today - timedelta(days=7))
        ),
        today_transaction_count=Count(
            'transactions',
            filter=Q(transactions__transaction_date=today)
        )
    ).order_by('-active', 'name')
    
    # Active vessels for quick stats
    vessels = all_vessels.filter(active=True).order_by('name')
    
    # OPTIMIZED: Today's comprehensive sales summary with related stats
    today_stats = Transaction.objects.filter(
        transaction_date=today
    ).aggregate(
        # Sales stats
        total_revenue=Sum(
            F('unit_price') * F('quantity'), 
            filter=Q(transaction_type='SALE'),
            output_field=models.DecimalField()
        ),
        sales_count=Count('id', filter=Q(transaction_type='SALE')),
        
        # Supply stats
        total_supply_cost=Sum(
            F('unit_price') * F('quantity'),
            filter=Q(transaction_type='SUPPLY'),
            output_field=models.DecimalField()
        ),
        supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
        
        # Transfer stats
        transfer_out_count=Count('id', filter=Q(transaction_type='TRANSFER_OUT')),
        transfer_in_count=Count('id', filter=Q(transaction_type='TRANSFER_IN')),
        
        # Overall stats
        total_transactions=Count('id'),
        unique_vessels=Count('vessel', distinct=True),
        unique_products=Count('product', distinct=True)
    )
    
    # OPTIMIZED: Recent transactions with all related data
    recent_transactions = Transaction.objects.select_related(
        'vessel', 
        'product', 
        'product__category',
        'created_by',
        'trip',
        'purchase_order'
    ).order_by('-created_at')[:6]
    
    # OPTIMIZED: Quick dashboard metrics
    quick_stats = {
        'active_vessels': vessels.count(),
        'today_trips': Trip.objects.filter(trip_date=today).count(),
        'today_pos': PurchaseOrder.objects.filter(po_date=today).count(),
        'low_stock_products': InventoryLot.objects.filter(
            remaining_quantity__lte=5,
            remaining_quantity__gt=0
        ).values('product').distinct().count(),
    }
    
    # OPTIMIZED: Vessel performance summary (top 5 by recent activity)
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
    
    context = {
        'vessels': vessels,
        'all_vessels': all_vessels,
        'today_sales': today_stats,  # Contains comprehensive today stats
        'recent_transactions': recent_transactions,
        'quick_stats': quick_stats,
        'top_vessels': top_vessels,
        'today': today,
        'now': now,
    }
    
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