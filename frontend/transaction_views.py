from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from frontend.utils.cache_helpers import VesselCacheHelper
from frontend.utils.query_helpers import TransactionQueryHelper
from transactions.models import Transaction
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
    
@reports_access_required
def transactions_list(request):
    """Enhanced transaction list with advanced filtering and pagination"""
    
    # ✅ STEP 1: Single optimized query with all relationships
    transactions = Transaction.objects.select_related(
        'vessel',
        'product',
        'product__category',
        'created_by',
        'trip',
        'purchase_order'
    ).prefetch_related(
        'trip__vessel',
        'purchase_order__vessel'
    )
    
    # ✅ STEP 2: Apply filters using helper (your existing code)
    transactions = TransactionQueryHelper.apply_common_filters(transactions, request)
    
    # ✅ STEP 3: Order results (your existing code)
    transactions = transactions.order_by('-transaction_date', '-created_at')
    
    # ✅ STEP 4: Pagination with count optimization
    paginator = Paginator(transactions, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # ✅ STEP 5: Calculate summary stats ONCE (not per transaction type)
    if page_obj.object_list:
        # Get stats for current page only to avoid expensive full table scan
        page_transactions = list(page_obj.object_list)
        
        summary_stats = {
            'total_displayed': len(page_transactions),
            'page_number': page_obj.number,
            'total_pages': page_obj.paginator.num_pages,
        }
        
        # Optional: Add type breakdown for current page only
        type_counts = {}
        for tx in page_transactions:
            tx_type = tx.transaction_type
            type_counts[tx_type] = type_counts.get(tx_type, 0) + 1
            
        summary_stats['type_breakdown'] = type_counts
    else:
        summary_stats = {
            'total_displayed': 0,
            'page_number': 1,
            'total_pages': 1,
            'type_breakdown': {}
        }
    
    # ✅ STEP 6: Context (your existing structure)
    context = {
        'page_obj': page_obj,
        'transactions': page_obj.object_list,  # For template compatibility
        'transaction_types': Transaction.TRANSACTION_TYPES,
        'summary_stats': summary_stats,
        'vessels': VesselCacheHelper.get_active_vessels(),
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
    """Delete individual transaction with proper inventory handling"""
    
    # Get transaction safely
    transaction_obj, error = CRUDHelper.safe_get_object(Transaction, transaction_id, 'Transaction')
    if error:
        return error
    
    try:
        transaction_type = transaction_obj.transaction_type
        product_name = transaction_obj.product.name
        vessel_name = transaction_obj.vessel.name
        
        # Delete transaction (this triggers the enhanced delete method)
        transaction_obj.delete()
        
        return JsonResponseHelper.success(
            message=f'{transaction_type} transaction for {product_name} on {vessel_name} deleted successfully. Inventory updated.'
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
                        'label': 'Check Inventory',
                        'url': reverse('frontend:inventory_check'),
                        'description': 'View current inventory levels and consumption details'
                    },
                    {
                        'action': 'contact_admin',
                        'label': 'Contact Administrator',
                        'description': 'If you need to force delete this transaction, contact your system administrator'
                    }
                ]
            )
        
        # Handle other validation errors
        return JsonResponseHelper.error(
            error_message=error_message,
            error_type='validation_error'
        )
            
    except Exception as e:
        return JsonResponseHelper.error(
            error_message=f"An unexpected error occurred: {str(e)}",
            error_type='system_error'
        )