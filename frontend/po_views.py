from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group, Permission
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction, models
from django.db.models import Sum, F, Count, Q, Avg
from frontend.utils.validation_helpers import ValidationHelper
from .utils.query_helpers import TransactionQueryHelper
from transactions.models import Transaction, Trip, PurchaseOrder, InventoryLot
from vessels.models import Vessel
from .utils import BilingualMessages
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from datetime import date, datetime, timedelta
import json
import secrets
import string
from django.core.cache import cache
from .permissions import is_admin_or_manager, admin_or_manager_required, is_superuser_only, superuser_required
import traceback
from products.models import Product
from transactions.models import get_all_vessel_pricing_summary, get_vessel_pricing_warnings
from .permissions import get_user_role, UserRoles
from .utils.response_helpers import FormResponseHelper, JsonResponseHelper
from .utils.crud_helpers import CRUDHelper, AdminActionHelper
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

@login_required
@user_passes_test(is_admin_or_manager)
def po_management(request):
    """WORKING: PO management with template-required annotations"""
    
    # WORKING: Base queryset with template-required annotations
    purchase_orders = PurchaseOrder.objects.select_related(
        'vessel',           
        'created_by'        
    ).prefetch_related(
        'supply_transactions__product'  
    ).annotate(
        # These are the fields the template expects
        annotated_total_cost=Sum(
            F('supply_transactions__unit_price') * F('supply_transactions__quantity'),
            output_field=models.DecimalField()
        ),
        annotated_transaction_count=Count('supply_transactions'),
    )
    
    # Apply all filters using helper with custom field mappings
    purchase_orders = TransactionQueryHelper.apply_common_filters(
        purchase_orders, request,
        date_field='po_date',             # POs use po_date not transaction_date
        status_field='is_completed'       # Enable status filtering for POs
    )
    
    # Order for consistent results
    purchase_orders = purchase_orders.order_by('-po_date', '-created_at')
    
    # WORKING: Add cost performance class to each PO (for template)
    po_list = list(purchase_orders[:50])

    # WORKING: Simple statistics using separate queries
    po_stats = PurchaseOrder.objects.aggregate(
        total_pos=Count('id'),
        completed_pos=Count('id', filter=Q(is_completed=True)),
        in_progress_pos=Count('id', filter=Q(is_completed=False))
    )

    # Calculate financial statistics
    financial_stats = Transaction.objects.filter(
        transaction_type='SUPPLY',
        purchase_order__isnull=False
    ).aggregate(
        total_procurement_value=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        total_transactions=Count('id'),
        avg_po_value=Avg(F('unit_price') * F('quantity'), output_field=models.DecimalField())
    )

    # Set defaults for financial stats
    for key in ['total_procurement_value', 'total_transactions', 'avg_po_value']:
        if financial_stats[key] is None:
            financial_stats[key] = 0

    # Calculate completion rate
    total_pos = po_stats['total_pos'] or 1  # Avoid division by zero
    completed_pos = po_stats['completed_pos'] or 0
    completion_rate = (completed_pos / total_pos) * 100

    # Get top vessels by PO activity (simplified)
    top_vessels = Vessel.objects.filter(active=True).annotate(
        po_count=Count('purchase_orders')
    ).filter(po_count__gt=0).order_by('-po_count')[:5]

    # Recent activity
    recent_pos = PurchaseOrder.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7)
    )
    recent_pos_count = recent_pos.count()
    recent_value = recent_pos.aggregate(
        total=Sum(F('supply_transactions__unit_price') * F('supply_transactions__quantity'))
    )['total'] or 0

    # Get vessels for filter using helper
    vessels_for_filter = TransactionQueryHelper.get_vessels_for_filter()

    context = {
        'purchase_orders': po_list,
        'vessels': vessels_for_filter,
        'top_vessels': top_vessels,  # Simplified but functional
        'stats': {
            # Basic counts
            'total_pos': po_stats['total_pos'] or 0,
            'completed_pos': po_stats['completed_pos'] or 0,
            'in_progress_pos': po_stats['in_progress_pos'] or 0,
            'completion_rate': round(completion_rate, 1),
            
            # Financial metrics
            'total_procurement_value': financial_stats['total_procurement_value'],
            'avg_po_value': round(financial_stats['avg_po_value'], 2),
            
            # Transaction metrics
            'total_transactions': financial_stats['total_transactions'],
            'avg_transactions_per_po': round(
                financial_stats['total_transactions'] / max(po_stats['total_pos'], 1), 1
            ),
        },
        'recent_activity': {
            'recent_pos': recent_pos_count,
            'recent_value': recent_value,
        }
    }
    
    # Add filter context using helper
    context.update(TransactionQueryHelper.get_filter_context(request))
    
    return render(request, 'frontend/auth/po_management.html', context)

@login_required
@user_passes_test(is_admin_or_manager)
def edit_po(request, po_id):
    """Edit PO details"""
    if request.method == 'GET':
        # Get PO safely
        po, error = CRUDHelper.safe_get_object(PurchaseOrder, po_id, 'Purchase Order')
        if error:
            return error
            
        return JsonResponseHelper.success(data={
            'po': {
                'id': po.id,
                'po_number': po.po_number,
                'po_date': po.po_date.strftime('%Y-%m-%d'),
                'notes': po.notes or '',
                'vessel_id': po.vessel.id,
                'vessel_name': po.vessel.name,
            }
        })
    
    elif request.method == 'POST':
        # Load JSON safely
        data, error = CRUDHelper.safe_json_load(request)
        if error:
            return error
        
        # Get PO safely
        po, error = CRUDHelper.safe_get_object(PurchaseOrder, po_id, 'Purchase Order')
        if error:
            return error
        
        try:
            # Update PO fields
            if 'po_date' in data:
                po.po_date = datetime.strptime(data['po_date'], '%Y-%m-%d').date()
            
            if 'notes' in data:
                po.notes = data['notes']
            
            po.save()
            
            return JsonResponseHelper.success(
                message=f'Purchase Order {po.po_number} updated successfully'
            )
            
        except (ValueError, ValidationError) as e:
            return JsonResponseHelper.error(f'Invalid data: {str(e)}')
        except Exception as e:
            return JsonResponseHelper.error(str(e))

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["DELETE"])
def delete_po(request, po_id):
    """Delete PO with cascade option for transactions"""
    po, error = CRUDHelper.safe_get_object(PurchaseOrder, po_id, 'Purchase Order')
    if error:
        return error

    force_delete = AdminActionHelper.check_force_delete(request)

    # OPTIMIZED: Get transaction info in single query with computed amount
    transactions_info = [
        {
            'product_name': txn['product__name'],
            'quantity': txn['quantity'],
            'unit_price': txn['unit_price'],
            'amount': float(txn['quantity']) * float(txn['unit_price']),
        }
        for txn in po.supply_transactions.select_related('product').values(
            'product__name', 'quantity', 'unit_price'
        )
    ]

    transaction_count = len(transactions_info)

    if transaction_count > 0 and not force_delete:
        total_cost = sum(txn['amount'] for txn in transactions_info)

        return JsonResponseHelper.requires_confirmation(
            message=f'This PO has {transaction_count} supply transactions. Delete anyway?',
            confirmation_data={
                'transaction_count': transaction_count,
                'total_cost': total_cost,
                'transactions': transactions_info
            }
        )

    try:
        po_number = po.po_number

        if transaction_count > 0:
            with transaction.atomic():
                po.supply_transactions.all().delete()
                po.delete()

            return JsonResponseHelper.success(
                message=f'PO {po_number} and all {transaction_count} transactions deleted successfully. Inventory removed.'
            )
        else:
            po.delete()
            return JsonResponseHelper.success(
                message=f'PO {po_number} deleted successfully'
            )

    except Exception as e:
        return JsonResponseHelper.error(str(e))

@login_required
@user_passes_test(is_admin_or_manager)
def toggle_po_status(request, po_id):
    """Toggle PO completion status"""
    if request.method == 'POST':
        # Get PO safely
        po, error = CRUDHelper.safe_get_object(PurchaseOrder, po_id, 'Purchase Order')
        if error:
            return error
        
        # Toggle status with standardized response
        return CRUDHelper.toggle_boolean_field(po, 'is_completed', 'Purchase Order')

@login_required
@user_passes_test(is_admin_or_manager)
def po_details(request, po_id):
    """Get detailed PO information"""
    
    try:
        po = get_object_or_404(PurchaseOrder, id=po_id)
        
        # Get PO supplies
        supply_transactions = po.supply_transactions.select_related('product').order_by('created_at')
        
        # Calculate statistics
        total_cost = po.total_cost
        total_items = supply_transactions.count()
        avg_cost_per_item = total_cost / max(total_items, 1)
        
        # Items breakdown
        items_breakdown = []
        for supply in supply_transactions:
            items_breakdown.append({
                'product_name': supply.product.name,
                'quantity_ordered': float(supply.quantity),
                'quantity_received': float(supply.quantity),  # Assuming fully received
                'unit_cost': float(supply.unit_price),
                'total_cost': float(supply.total_amount),
            })
        
        return JsonResponse({
            'success': True,
            'po': {
                'po_number': po.po_number,
                'vessel_name': po.vessel.name,
                'vessel_name_ar': po.vessel.name_ar,
                'po_date': po.po_date.strftime('%d/%m/%Y'),
                'is_completed': po.is_completed,
                'created_by': po.created_by.username if po.created_by else 'System',
                'notes': po.notes,
                'supplier': 'Marina Supply Co.',  # Mock - implement supplier tracking
            },
            'statistics': {
                'total_cost': float(total_cost),
                'total_items': total_items,
                'avg_cost_per_item': float(avg_cost_per_item),
            },
            'items_breakdown': items_breakdown,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})