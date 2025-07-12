from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db import transaction
from frontend.utils.cache_helpers import POCacheHelper, VesselCacheHelper, get_optimized_pagination
from .utils.query_helpers import TransactionQueryHelper
from transactions.models import PurchaseOrder
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from datetime import  datetime
from frontend.utils.cache_helpers import ProductCacheHelper
from .permissions import is_admin_or_manager
from .utils.response_helpers import JsonResponseHelper
from .utils.crud_helpers import CRUDHelper, AdminActionHelper
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

@login_required
@user_passes_test(is_admin_or_manager)
def po_management(request):
    """OPTIMIZED: PO management with COUNT-free pagination"""
    
    # Base queryset with template-required annotations
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
    
    # ✅ REPLACE Django Paginator with optimized pagination
    page_number = request.GET.get('page', 1)
    page_obj = get_optimized_pagination(purchase_orders, page_number, page_size=25, use_count=False)
    
    # WORKING: Add cost performance class to each PO (for template)
    po_list = page_obj.object_list  # Use optimized pagination object list
    
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
        
        if po_cost > 1000:
            po.cost_performance_class = 'high-cost'
        elif po_cost > 500:
            po.cost_performance_class = 'medium-cost'
        else:
            po.cost_performance_class = 'low-cost'
            
        # Count completed POs
        if po.is_completed:
            completed_count += 1

    total_pos = len(po_list)
    completed_pos = sum(1 for po in po_list if po.is_completed)
    in_progress_pos = total_pos - completed_pos
    total_procurement_value = total_cost
    total_transactions = sum(po.annotated_transaction_count for po in po_list)
    avg_po_value = total_cost / max(total_pos, 1)

    # Calculate completion rate
    completion_rate = (completed_pos / max(total_pos, 1)) * 100

    # Calculate recent activity from existing data
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
        'page_obj': page_obj,  # Optimized pagination object
        'vessels': vessels,
        'top_vessels': top_vessels,
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
                'is_completed': po.is_completed,
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
            # Track if status is changing for cache clearing
            status_changed = False
            old_status = po.is_completed
            
            # Update PO fields
            if 'po_date' in data:
                po.po_date = datetime.strptime(data['po_date'], '%Y-%m-%d').date()
            
            if 'notes' in data:
                po.notes = data['notes']
            
            # 🚀 NEW: Handle completion status changes (admin/manager only)
            if 'is_completed' in data:
                # Check permission for status changes
                from .permissions import is_admin_or_manager
                if not is_admin_or_manager(request.user):
                    return JsonResponseHelper.error('Permission denied: Only administrators and managers can change PO status')
                
                new_status = bool(data['is_completed'])
                if new_status != old_status:
                    status_changed = True
                    po.is_completed = new_status
                    
                    # Log the status change
                    action = "completed" if new_status else "reopened"
                    print(f"🔄 PO STATUS CHANGE: PO {po.po_number} {action} by {request.user.username}")
            
            po.save()
            
            # 🚀 ENHANCED: Clear cache if status changed or always for consistency
            if status_changed:
                POCacheHelper.clear_cache_after_po_update(po_id)
                print(f"🔥 Enhanced cache cleared due to status change")
            else:
                POCacheHelper.clear_cache_after_po_update(po_id)
            
            # Create appropriate success message
            if status_changed:
                action = "completed" if po.is_completed else "reopened for editing"
                message = f'PO {po.po_number} updated and {action} successfully'
            else:
                message = f'PO {po.po_number} updated successfully'

            return JsonResponseHelper.success(message=message, data={'po_id': po.id})
                
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
                for transaction_obj in po.supply_transactions.all():
                    transaction_obj.delete()  # This can now raise ValidationError
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
            
    except ValidationError as e:
        # 🛡️ ENHANCED ERROR HANDLING: Parse and format user-friendly messages
        error_message = str(e)
        
        # Extract message from ValidationError list format
        if error_message.startswith('[') and error_message.endswith(']'):
            error_message = error_message[2:-2]  # Remove ['...']
        
        # Check if it's an inventory consumption error
        if "Cannot delete supply transaction" in error_message:
            # Extract key information for better error display
            lines = error_message.split('\\n')  # Split on literal \n
            main_error = lines[0] if lines else error_message
            
            # Return enhanced error with additional context
            return JsonResponseHelper.error(
                error_message=main_error,
                error_type='inventory_consumption_blocked',
                detailed_message=error_message,
                suggested_actions=[
                    {
                        'action': 'view_transactions',
                        'label': 'View Transaction Log',
                        'url': reverse('frontend:transactions_list'),
                        'description': 'Find and delete the sales/transfers that consumed this inventory'
                    },
                    {
                        'action': 'view_inventory',
                        'label': 'Check Inventory Details',
                        'url': reverse('frontend:inventory_check'),
                        'description': 'View current inventory levels and consumption details'
                    },
                    {
                        'action': 'contact_admin',
                        'label': 'Contact Administrator',
                        'description': 'Get help identifying which transactions need to be deleted first'
                    }
                ]
            )
        else:
            # For other validation errors, return standard error
            return JsonResponseHelper.error(
                error_message=f"Cannot delete purchase order: {error_message}",
                error_type='validation_error'
            )
            
    except Exception as e:
        return JsonResponseHelper.error(
            error_message=f"An unexpected error occurred: {str(e)}",  # ← FIXED: was message=
            error_type='system_error'
        )

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