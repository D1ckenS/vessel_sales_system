from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
import logging
from frontend.utils.cache_helpers import VesselCacheHelper, get_optimized_pagination
from frontend.utils.query_helpers import TransactionQueryHelper
from transactions.models import Transaction
from products.models import Product
from .utils.response_helpers import JsonResponseHelper
from .utils.crud_helpers import CRUDHelper
from .permissions import is_admin_or_manager
from django.urls import reverse
from django.core.paginator import Paginator
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

logger = logging.getLogger('frontend')
    
@reports_access_required
def transactions_list(request):
    """✅ FULLY OPTIMIZED: Single query with zero N+1 issues"""
    
    # ✅ STEP 1: Single optimized query - removed problematic prefetch_related
    transactions = Transaction.objects.select_related(
        'vessel',           # All vessel fields included
        'product', 
        'product__category',
        'created_by',
        'trip',             # Trip basic info
        'purchase_order'    # PO basic info
        # REMOVED: prefetch_related - was causing extra vessel queries
    )
    
    # ✅ STEP 2: Apply filters using existing helper
    transactions = TransactionQueryHelper.apply_common_filters(transactions, request)
    
    # ✅ STEP 3: Order results 
    transactions = transactions.order_by('-transaction_date', '-created_at')
    
    # ✅ STEP 4: REPLACE Django Paginator with optimized pagination
    page_number = request.GET.get('page', 1)
    page_obj = get_optimized_pagination(transactions, page_number, page_size=50, use_count=False)
    
    # ✅ STEP 5: Calculate summary stats from current page only
    transaction_list = page_obj.object_list
    summary_stats = {
        'total_displayed': len(transaction_list),
        'page_number': page_obj.number,
        'has_next': page_obj.has_next,
        'has_previous': page_obj.has_previous(),
    }
    
    # Optional: Add type breakdown for current page
    if transaction_list:
        type_counts = {}
        for tx in transaction_list:
            tx_type = tx.transaction_type
            type_counts[tx_type] = type_counts.get(tx_type, 0) + 1
        summary_stats['type_breakdown'] = type_counts
    else:
        summary_stats['type_breakdown'] = {}
    
    # ✅ STEP 6: Use cached vessels (should be cached for 1 year)
    vessels = VesselCacheHelper.get_active_vessels()
    
    # ✅ STEP 6.1: Get active products for filter dropdown
    products = Product.objects.filter(active=True).select_related('category').order_by('name')
    
    # ✅ STEP 7: Context with optimized data
    context = {
        'page_obj': page_obj,
        'transactions': transaction_list,  # Template compatibility
        'transaction_types': Transaction.TRANSACTION_TYPES,
        'summary_stats': summary_stats,
        'vessels': vessels,  # Cached vessels
        'products': products,  # Active products for filter dropdown
        'current_filters': {
            'product': request.GET.get('product', ''),
            'transaction_type': request.GET.get('transaction_type', ''),
            'date_from': request.GET.get('date_from', ''),
            'date_to': request.GET.get('date_to', ''),
        }
    }
    
    return render(request, 'frontend/transactions_list.html', context)


@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["DELETE"])
def delete_transaction(request, transaction_id):
    """
    🔧 ENHANCED: Delete individual transaction with proper transfer linking
    
    Handles all transaction types:
    - SALE: Restores inventory using FIFO details
    - SUPPLY: Validates no consumption (like PO validation)
    - TRANSFER_OUT: Auto-deletes linked TRANSFER_IN, restores inventory  
    - TRANSFER_IN: Validates no consumption, removes transferred inventory
    - WASTE: Restores inventory using purchase price
    """
    
    # Get transaction safely
    transaction_obj, error = CRUDHelper.safe_get_object(Transaction, transaction_id, 'Transaction')
    if error:
        return error
    
    try:
        transaction_type = transaction_obj.transaction_type
        product_name = transaction_obj.product.name
        vessel_name = transaction_obj.vessel.name
        quantity = transaction_obj.quantity
        
        # 🔧 ENHANCED: Special handling for transfer transactions
        if transaction_type == 'TRANSFER_OUT':
            # Check if there's a linked TRANSFER_IN
            linked_transfer_in = transaction_obj.related_transfer
            if linked_transfer_in:
                logger.info(f"🔗 TRANSFER_OUT deletion will auto-delete linked TRANSFER_IN: {linked_transfer_in.id}")
                
        elif transaction_type == 'TRANSFER_IN':
            # Find the TRANSFER_OUT that points to this TRANSFER_IN
            linked_transfer_out = Transaction.objects.filter(
                related_transfer=transaction_obj,
                transaction_type='TRANSFER_OUT'
            ).first()
            
            if linked_transfer_out:
                logger.info(f"🔗 TRANSFER_IN deletion will auto-delete linked TRANSFER_OUT: {linked_transfer_out.id}")
                # Delete the TRANSFER_OUT, which will cascade delete this TRANSFER_IN
                linked_transfer_out.delete()
                return JsonResponseHelper.success(
                    message=f'Transfer In transaction for {product_name} deleted successfully. Linked Transfer Out also deleted and inventory restored.'
                )
            else:
                logger.warning(f"🔍 ORPHANED: TRANSFER_IN {transaction_obj.id} has no linked TRANSFER_OUT")
        
        # Delete transaction (this triggers the enhanced delete method with proper linking)
        transaction_obj.delete()
        
        # 🔧 ENHANCED: Better success messages based on transaction type
        if transaction_type == 'TRANSFER_OUT':
            message = f'Transfer Out transaction for {product_name} deleted successfully. Linked Transfer In also deleted and inventory restored to {vessel_name}.'
        elif transaction_type == 'TRANSFER_IN':
            message = f'Transfer In transaction for {product_name} deleted successfully. Transferred inventory removed from {vessel_name}.'
        elif transaction_type == 'SUPPLY':
            message = f'Supply transaction for {product_name} deleted successfully. Inventory removed from {vessel_name}.'
        elif transaction_type == 'SALE':
            message = f'Sale transaction for {product_name} deleted successfully. Inventory restored to {vessel_name}.'
        elif transaction_type == 'WASTE':
            message = f'Waste transaction for {product_name} deleted successfully. Inventory restored to {vessel_name}.'
        else:
            message = f'{transaction_type} transaction for {product_name} on {vessel_name} deleted successfully. Inventory updated.'
        
        return JsonResponseHelper.success(message=message)
        
    except ValidationError as e:
        # 🛡️ ENHANCED: Better error handling for different transaction types
        error_message = str(e)
        
        # Extract message from ValidationError list format
        if error_message.startswith('[') and error_message.endswith(']'):
            error_message = error_message[2:-2]
        
        # Provide transaction-type specific error context
        if transaction_type == 'SUPPLY' and "Cannot delete supply transaction" in error_message:
            return JsonResponseHelper.error(
                error_message=f"Cannot delete supply transaction - inventory has been consumed: {error_message}",
                error_type='supply_consumption_blocked',
                detailed_message=error_message,
                suggested_actions=[
                    {
                        'action': 'view_consumption',
                        'label': 'View What Consumed This Inventory',
                        'url': reverse('frontend:transactions_list'),
                        'description': f'Find the sales/transfers that consumed {product_name} from {vessel_name}'
                    },
                    {
                        'action': 'check_inventory',
                        'label': 'Check Current Inventory',
                        'url': reverse('frontend:inventory_check'),
                        'description': 'Review current inventory levels and consumption details'
                    }
                ]
            )
        
        elif transaction_type == 'TRANSFER_IN' and ("Cannot delete" in error_message or "consumed" in error_message.lower()):
            return JsonResponseHelper.error(
                error_message=f"Cannot delete transfer in - transferred inventory has been consumed: {error_message}",
                error_type='transfer_in_consumption_blocked',
                detailed_message=error_message,
                suggested_actions=[
                    {
                        'action': 'view_consumption',
                        'label': 'View What Consumed Transferred Inventory',
                        'url': reverse('frontend:transactions_list'),
                        'description': f'Find the sales/transfers that consumed {product_name} on {vessel_name}'
                    },
                    {
                        'action': 'check_destination_inventory', 
                        'label': 'Check Destination Vessel Inventory',
                        'url': reverse('frontend:inventory_check'),
                        'description': f'Review inventory levels on {vessel_name} to understand consumption'
                    }
                ]
            )
        
        # Generic validation error
        return JsonResponseHelper.error(
            error_message=f"Cannot delete {transaction_type.lower()} transaction: {error_message}",
            error_type='validation_error'
        )
            
    except Exception as e:
        return JsonResponseHelper.error(
            error_message=f"An unexpected error occurred while deleting {transaction_type.lower()} transaction: {str(e)}",
            error_type='system_error'
        )