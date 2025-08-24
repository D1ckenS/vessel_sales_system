from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F, Q, Prefetch, DecimalField, ExpressionWrapper, Subquery, OuterRef
from django.db.models.functions import Coalesce
from django.core.cache import cache
from django.http import JsonResponse
from datetime import date, datetime, timedelta
from frontend.utils.cache_helpers import VesselCacheHelper
from vessels.models import Vessel
from transactions.models import InventoryLot, PurchaseOrder, Transaction, Trip
from vessel_management.models import TransferWorkflow, UserVesselAssignment
from django.db import models
from .permissions import is_admin_or_manager, admin_or_manager_required, is_superuser_only
import json
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

@login_required
def dashboard(request):
    today = date.today()
    now = datetime.now()
    user_role = 'admin' if request.user.is_superuser else 'user'
    # 🚀 SKIP CACHING ON FIRST LOAD: Focus on query optimization instead of cache overhead
    # Cache adds 3+ database operations, optimize direct queries instead

    # 🚀 DASHBOARD VESSEL CACHING: Now optimized to eliminate cache overhead
    all_vessels = VesselCacheHelper.get_all_vessels_basic_data()
    active_vessels_count = sum(1 for v in all_vessels if v.active)

    # 🚀 GET TRIPS/POs FIRST: Need IDs for combined query
    recent_trips = Trip.objects.select_related('vessel').only(
        'id', 'trip_number', 'trip_date', 'passenger_count', 'is_completed', 'created_at',
        'vessel__id', 'vessel__name', 'vessel__name_ar'
    ).order_by('-created_at')[:3]

    recent_pos = PurchaseOrder.objects.select_related('vessel').only(
        'id', 'po_number', 'po_date', 'is_completed', 'created_at',
        'vessel__id', 'vessel__name', 'vessel__name_ar'
    ).order_by('-created_at')[:3]
    
    # 🚀 OPTIMIZED: SINGLE COMBINED QUERY for both today's stats AND recent financial data
    trip_ids = [trip.id for trip in recent_trips] if recent_trips else []
    po_ids = [po.id for po in recent_pos] if recent_pos else []
    
    # Single query to get all transaction data we need
    all_transactions = Transaction.objects.filter(
        Q(transaction_date=today) |  # Today's transactions (for stats)
        Q(trip_id__in=trip_ids, transaction_type='SALE') |  # Recent trip revenues
        Q(purchase_order_id__in=po_ids, transaction_type='SUPPLY')  # Recent PO costs
    ).select_related().values(
        'transaction_date', 'transaction_type', 'trip_id', 'purchase_order_id',
        'unit_price', 'quantity', 'vessel_id', 'product_id'
    )
    
    # Process all transactions in Python (more flexible than complex SQL aggregation)
    today_summary = {
        'total_revenue': 0, 'total_supply_cost': 0, 'sales_count': 0, 'supply_count': 0,
        'transfer_out_count': 0, 'transfer_in_count': 0, 'total_transactions': 0,
        'unique_vessels': set(), 'unique_products': set(), 'total_volume': 0
    }
    
    trip_revenue_dict = {}
    po_cost_dict = {}
    
    for transaction in all_transactions:
        amount = (transaction['unit_price'] or 0) * (transaction['quantity'] or 0)
        trans_type = transaction['transaction_type']
        
        # Today's statistics
        if transaction['transaction_date'] == today:
            if trans_type == 'SALE':
                today_summary['total_revenue'] += amount
                today_summary['sales_count'] += 1
            elif trans_type == 'SUPPLY':
                today_summary['total_supply_cost'] += amount
                today_summary['supply_count'] += 1
            elif trans_type == 'TRANSFER_OUT':
                today_summary['transfer_out_count'] += 1
            elif trans_type == 'TRANSFER_IN':
                today_summary['transfer_in_count'] += 1
            
            today_summary['total_transactions'] += 1
            today_summary['total_volume'] += transaction['quantity'] or 0
            today_summary['unique_vessels'].add(transaction['vessel_id'])
            today_summary['unique_products'].add(transaction['product_id'])
        
        # Recent financial data
        if trans_type == 'SALE' and transaction['trip_id']:
            trip_revenue_dict[transaction['trip_id']] = trip_revenue_dict.get(transaction['trip_id'], 0) + amount
        elif trans_type == 'SUPPLY' and transaction['purchase_order_id']:
            po_cost_dict[transaction['purchase_order_id']] = po_cost_dict.get(transaction['purchase_order_id'], 0) + amount
    
    # Convert sets to counts
    today_summary['unique_vessels'] = len(today_summary['unique_vessels'])
    today_summary['unique_products'] = len(today_summary['unique_products'])
    
    # Map results back to objects
    for trip in recent_trips:
        trip.annotated_revenue = trip_revenue_dict.get(trip.id, 0)
    
    for po in recent_pos:
        po.annotated_cost = po_cost_dict.get(po.id, 0)

    recent_activity = sorted(
        list(recent_trips) + list(recent_pos),
        key=lambda x: x.created_at,
        reverse=True
    )[:6]

    # 🚀 SIMPLIFIED QUICK STATS: Use direct count instead of loading all vessels
    quick_stats = {
        'active_vessels': active_vessels_count,
        'total_transactions': today_summary.get('total_transactions', 0),
    }

    # 🔔 Transfer Workflow Notifications
    transfer_notifications = get_transfer_workflow_notifications(request.user)

    context = {
        'vessels': [],  # Empty list for dashboard (not needed)
        'all_vessels': all_vessels,  # Vessels for dashboard display
        'today_sales': today_summary,
        'quick_stats': quick_stats,
        'recent_activity': recent_activity,
        'today': today,
        'now': now,
        'transfer_notifications': transfer_notifications,
    }

    # 🚀 SKIP FINAL CACHE: Avoid cache storage overhead for first-load optimization
    # cache.set(cache_key, {k: v for k, v in context.items() if k != 'now'}, 300)  # Disabled for better first-load performance
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

def get_transfer_workflow_notifications(user):
    """Get transfer workflow notifications for dashboard"""
    try:
        # Get user's vessel assignments
        if user.is_superuser:
            # SuperUsers can see all pending transfers
            pending_from_user = TransferWorkflow.objects.filter(
                status__in=['under_review', 'pending_confirmation']
            ).count()
            pending_to_user = 0  # SuperUsers handle via FROM logic
        else:
            user_vessels = UserVesselAssignment.objects.filter(
                user=user, is_active=True
            ).values_list('vessel_id', flat=True)
            
            if not user_vessels:
                return {'show_notification': False, 'pending_count': 0}
            
            # Count transfers where user has access to FROM vessel (pending confirmation after edits)
            pending_from_user = TransferWorkflow.objects.filter(
                base_transfer__from_vessel__in=user_vessels,
                status='pending_confirmation'
            ).count()
            
            # Count transfers where user has access to TO vessel (pending review or under review)
            pending_to_user = TransferWorkflow.objects.filter(
                base_transfer__to_vessel__in=user_vessels,
                status__in=['pending_review', 'under_review']
            ).count()
        
        total_pending = pending_from_user + pending_to_user
        
        if total_pending > 0:
            return {
                'show_notification': True,
                'pending_count': total_pending,
                'pending_from_user': pending_from_user,
                'pending_to_user': pending_to_user,
                'message_type': 'needs_confirmation' if pending_to_user > 0 else 'awaiting_response'
            }
        else:
            return {'show_notification': False, 'pending_count': 0}
            
    except Exception as e:
        # Return safe default on error
        return {'show_notification': False, 'pending_count': 0, 'error': str(e)}

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