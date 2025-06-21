from django.utils import timezone
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db import transaction
from frontend.utils.cache_helpers import VesselCacheHelper
from .utils.query_helpers import TransactionQueryHelper
from transactions.models import PurchaseOrder
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from datetime import  datetime
from frontend.utils.cache_helpers import ProductCacheHelper
from .permissions import is_admin_or_manager
from .utils.response_helpers import JsonResponseHelper
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
        'vessel', 'created_by'
    ).prefetch_related(
        'supply_transactions'
    ).order_by('-po_date', '-created_at')
    
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
    
    # OPTIMIZED: Calculate stats in Python using prefetched data
    total_cost = 0
    completed_count = 0

    for po in po_list:
        # Calculate cost using prefetched supply_transactions (no additional queries)
        po_cost = sum(
            float(txn.quantity) * float(txn.unit_price) 
            for txn in po.supply_transactions.all()
        )
        po_transaction_count = len(po.supply_transactions.all())
        
        # Add calculated fields to PO object for template
        po.annotated_total_cost = po_cost
        po.annotated_transaction_count = po_transaction_count
        
        # Accumulate stats
        total_cost += po_cost
        if po.is_completed:
            completed_count += 1

    total_pos = len(po_list)
    completed_pos = sum(1 for po in po_list if po.is_completed)
    in_progress_pos = total_pos - completed_pos
    total_procurement_value = total_cost  # Already calculated above
    total_transactions = sum(po.annotated_transaction_count for po in po_list)
    avg_po_value = total_cost / max(total_pos, 1)

    # Calculate completion rate
    completion_rate = (completed_pos / max(total_pos, 1)) * 100

    # Calculate recent activity from existing data
    from datetime import timedelta
    week_ago = timezone.now() - timedelta(days=7)
    recent_pos_count = sum(1 for po in po_list if po.created_at >= week_ago)
    recent_value = sum(po.annotated_total_cost for po in po_list if po.created_at >= week_ago)

    # Calculate vessel performance from existing data
    vessel_stats = {}
    for po in po_list:
        vessel_name = po.vessel.name
        if vessel_name not in vessel_stats:
            vessel_stats[vessel_name] = {
                'vessel': po.vessel,
                'po_count': 0,
                'total_value': 0
            }
        vessel_stats[vessel_name]['po_count'] += 1
        vessel_stats[vessel_name]['total_value'] += po.annotated_total_cost

    # Convert to list and sort by po_count
    top_vessels = sorted(vessel_stats.values(), key=lambda x: x['po_count'], reverse=True)[:5]

    # Get vessels for filter using helper
    vessels = VesselCacheHelper.get_active_vessels()

    context = {
        'purchase_orders': po_list,
        'vessels': vessels,
        'top_vessels': top_vessels,  # Simplified but functional
        'stats': {
            'total_pos': total_pos,
                'completed_pos': completed_pos,
                'in_progress_pos': in_progress_pos,
                'completion_rate': round(completion_rate, 1),
                'total_procurement_value': total_procurement_value,
                'avg_po_value': round(avg_po_value, 2),
                'total_transactions': total_transactions,
                'avg_transactions_per_po': round(total_transactions / max(total_pos, 1), 1),
            },
        'recent_activity': {
            'recent_pos': recent_pos_count,
            'recent_value': recent_value,
        },
        'top_suppliers': top_vessels,
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
            
            try:
                
                ProductCacheHelper.clear_cache_after_product_update()
                print("🔥 Product cache cleared after PO deletion")
            except Exception as e:
                print(f"⚠️ Cache clear error: {e}")

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