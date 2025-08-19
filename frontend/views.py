from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F, Q, Prefetch, DecimalField, ExpressionWrapper
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
    cache_key = f'dashboard_data_{today}_{user_role}'

    cached_data = cache.get(cache_key)
    if cached_data:
        cached_data['now'] = now
        return render(request, 'frontend/dashboard.html', cached_data)

    all_vessels = Vessel.objects.annotate(
        recent_trip_count=Count('trips', filter=Q(trips__trip_date__gte=today - timedelta(days=7))),
        today_transaction_count=Count('transactions', filter=Q(transactions__transaction_date=today)),
        today_revenue=Sum(
            ExpressionWrapper(
                F('transactions__unit_price') * F('transactions__quantity'),
                output_field=DecimalField()
            ),
            filter=Q(
                transactions__transaction_type='SALE',
                transactions__transaction_date=today
            )
        )
    ).order_by('-active', 'name')

    today_summary = Transaction.objects.filter(transaction_date=today).aggregate(
        total_revenue=Sum(
            ExpressionWrapper(
                F('unit_price') * F('quantity'),
                output_field=DecimalField()
            ),
            filter=Q(transaction_type='SALE')
        ),
        total_supply_cost=Sum(
            ExpressionWrapper(
                F('unit_price') * F('quantity'),
                output_field=DecimalField()
            ),
            filter=Q(transaction_type='SUPPLY')
        ),
        sales_count=Count('id', filter=Q(transaction_type='SALE')),
        supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
        transfer_out_count=Count('id', filter=Q(transaction_type='TRANSFER_OUT')),
        transfer_in_count=Count('id', filter=Q(transaction_type='TRANSFER_IN')),
        total_transactions=Count('id'),
        unique_vessels=Count('vessel', distinct=True),
        unique_products=Count('product', distinct=True),
        total_volume=Sum('quantity')
    )

    for key in today_summary:
        if today_summary[key] is None:
            today_summary[key] = 0

    recent_trips = Trip.objects.select_related('vessel').annotate(
        annotated_revenue=Sum(
            ExpressionWrapper(
                F('sales_transactions__unit_price') * F('sales_transactions__quantity'),
                output_field=DecimalField()
            ),
            filter=Q(sales_transactions__transaction_type='SALE')
        )
    ).order_by('-created_at')[:3]

    recent_pos = PurchaseOrder.objects.select_related('vessel').annotate(
        annotated_cost=Sum(
            ExpressionWrapper(
                F('supply_transactions__unit_price') * F('supply_transactions__quantity'),
                output_field=DecimalField()
            ),
            filter=Q(supply_transactions__transaction_type='SUPPLY')
        )
    ).order_by('-created_at')[:3]

    recent_activity = sorted(
        list(recent_trips) + list(recent_pos),
        key=lambda x: x.created_at,
        reverse=True
    )[:6]

    quick_stats = {
        'active_vessels': sum(1 for v in all_vessels if v.active),
        'total_transactions': sum(v.today_transaction_count or 0 for v in all_vessels),
    }

    # 🔔 Transfer Workflow Notifications
    transfer_notifications = get_transfer_workflow_notifications(request.user)

    context = {
        'vessels': all_vessels,
        'all_vessels': all_vessels,
        'today_sales': today_summary,
        'quick_stats': quick_stats,
        'recent_activity': recent_activity,
        'today': today,
        'now': now,
        'transfer_notifications': transfer_notifications,
    }

    cache.set(cache_key, {k: v for k, v in context.items() if k != 'now'}, 300)
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