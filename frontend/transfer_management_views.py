from django.urls import reverse
from django.utils import timezone
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db import transaction
from frontend.utils.cache_helpers import TransferCacheHelper, VesselCacheHelper
from .utils.query_helpers import TransactionQueryHelper
from transactions.models import Transfer
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from datetime import datetime
from frontend.utils.cache_helpers import ProductCacheHelper
from .permissions import is_admin_or_manager
from .utils.response_helpers import JsonResponseHelper
from .utils.crud_helpers import CRUDHelper, AdminActionHelper
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)
import json

@login_required
@user_passes_test(is_admin_or_manager)
def transfer_management(request):
    """Transfer management with template-required annotations following PO pattern"""
    
    # Base queryset with template-required annotations
    transfers = Transfer.objects.select_related(
        'from_vessel', 'to_vessel', 'created_by'
    ).prefetch_related(
        'transactions'  # Use 'transactions' not 'transfer_transactions'
    ).order_by('-transfer_date', '-created_at')
    
    # Apply all filters using helper with custom field mappings
    transfers = TransactionQueryHelper.apply_common_filters(
        transfers, request,
        date_field='transfer_date',        # Transfers use transfer_date
        status_field='is_completed'        # Enable status filtering for transfers
    )
    
    # Order for consistent results
    transfers = transfers.order_by('-transfer_date', '-created_at')
    
    # Add cost performance class to each transfer (for template)
    transfer_list = list(transfers[:50])
    
    # Add template-required annotations for each transfer
    for transfer in transfer_list:
        # Calculate cost performance class for template styling
        total_cost = transfer.total_cost
        if total_cost > 1000:
            transfer.cost_performance_class = 'high-cost'
        elif total_cost > 500:
            transfer.cost_performance_class = 'medium-cost'
        else:
            transfer.cost_performance_class = 'low-cost'
    
    context = {
        'transfers': transfer_list,
        'active_vessels': VesselCacheHelper.get_active_vessels(),
        'total_count': transfers.count() if transfers.count() <= 1000 else '1000+',
        'page_title': 'Transfer Management',
        'current_filters': {
            'search': request.GET.get('search', ''),
            'vessel': request.GET.get('vessel', ''),
            'status': request.GET.get('status', ''),
            'date_from': request.GET.get('date_from', ''),
            'date_to': request.GET.get('date_to', ''),
        }
    }
    
    return render(request, 'frontend/auth/transfer_management.html', context)

@login_required
@user_passes_test(is_admin_or_manager)
def edit_transfer(request, transfer_id):
    """Edit transfer details following PO edit pattern"""
    transfer, error = CRUDHelper.safe_get_object(Transfer, transfer_id, 'Transfer')
    if error:
        return error

    if request.method == 'GET':
        transfer_data = {
            'id': transfer.id,
            'transfer_date': transfer.transfer_date.strftime('%Y-%m-%d'),
            'notes': transfer.notes,
            'is_completed': transfer.is_completed,
            'from_vessel': transfer.from_vessel.name,
            'to_vessel': transfer.to_vessel.name,
        }
        
        return JsonResponse({
            'success': True,
            'transfer': transfer_data
        })

    if request.method == 'POST':
        try:
            # Parse JSON data
            data = json.loads(request.body)
            
            # Validate required fields
            transfer_date = data.get('transfer_date')
            notes = data.get('notes', '')
            is_completed = data.get('is_completed', False)
            
            if not transfer_date:
                return JsonResponseHelper.error('Transfer date is required')
            
            # Parse and validate date
            try:
                transfer_date = datetime.strptime(transfer_date, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponseHelper.error('Invalid date format')
            
            # Track if status is changing to trigger proper cache clearing
            original_status = transfer.is_completed
            status_changed = original_status != is_completed
            
            # CRITICAL: Handle inventory when changing status from completed to incomplete
            if original_status and not is_completed:
                # Was completed, now marking as incomplete
                # Delete all TRANSFER_IN transactions to remove inventory from destination vessel
                with transaction.atomic():
                    transfer_in_transactions = transfer.transactions.filter(transaction_type='TRANSFER_IN')
                    
                    if transfer_in_transactions.exists():
                        print(f"🔄 EDIT REOPENING: Removing {transfer_in_transactions.count()} TRANSFER_IN transactions")
                        
                        # Delete each TRANSFER_IN transaction (this removes inventory via Transaction.delete())
                        for txn in transfer_in_transactions:
                            txn.delete()
                        
                        print(f"✅ EDIT REOPENED: All TRANSFER_IN inventory removed from {transfer.to_vessel.name}")
            
            # Update transfer fields
            transfer.transfer_date = transfer_date
            transfer.notes = notes
            transfer.is_completed = is_completed
            transfer.save()
            
            # Clear cache appropriately
            if status_changed:
                # 🔧 FIX: Clear specific completed transfer cache when toggling status
                if original_status and not is_completed:
                    # Was completed, now incomplete - remove specific completed cache
                    completed_cache_key = TransferCacheHelper.get_completed_transfer_cache_key(transfer_id)
                    from django.core.cache import cache
                    cache.delete(completed_cache_key)
                    print(f"🔥 DELETED SPECIFIC CACHE: {completed_cache_key}")
                
                TransferCacheHelper.clear_all_transfer_cache()
                print("🔥 Enhanced cache cleared due to status change")
            else:
                TransferCacheHelper.clear_cache_after_transfer_update(transfer_id)
            
            # Create appropriate success message
            if status_changed:
                action = "completed" if transfer.is_completed else "reopened for editing"
                message = f'Transfer {transfer.id} updated and {action} successfully'
            else:
                message = f'Transfer {transfer.id} updated successfully'

            return JsonResponseHelper.success(message=message, data={'transfer_id': transfer.id})
                
        except (ValueError, ValidationError) as e:
            return JsonResponseHelper.error(f'Invalid data: {str(e)}')
        except Exception as e:
            return JsonResponseHelper.error(str(e))

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["DELETE"])
def delete_transfer(request, transfer_id):
    """
    🔧 FIXED: Delete transfer with proper OUT/IN linking and validation
    
    Logic:
    - TRANSFER_OUT deletion automatically deletes linked TRANSFER_IN (via related_transfer)
    - TRANSFER_IN deletion validates no consumption (like PO validation)
    - Proper linking ensures consistency
    """
    transfer, error = CRUDHelper.safe_get_object(Transfer, transfer_id, 'Transfer')
    if error:
        return error

    force_delete = AdminActionHelper.check_force_delete(request)

    # 🔧 IMPROVED: Get linked transaction pairs for better analysis
    transfer_out_transactions = []
    transfer_in_transactions = []
    transfer_transactions = transfer.transactions.filter(
        transaction_type__in=['TRANSFER_OUT', 'TRANSFER_IN']
    )

    for txn in transfer_transactions.select_related('product', 'related_transfer'):
        txn_info = {
            'id': txn.id,
            'product_name': txn.product.name,
            'quantity': txn.quantity,
            'unit_price': txn.unit_price,
            'amount': float(txn.quantity) * float(txn.unit_price),
            'type': txn.transaction_type,
            'related_transfer_id': txn.related_transfer.id if txn.related_transfer else None
        }
        
        if txn.transaction_type == 'TRANSFER_OUT':
            transfer_out_transactions.append(txn_info)
        elif txn.transaction_type == 'TRANSFER_IN':
            transfer_in_transactions.append(txn_info)

    # 🔧 CHANGE: Count transfers as single operations for user display
    user_transfer_count = len(transfer_out_transactions)  # Only count OUT (user operations)
    actual_transaction_count = len(transfer_out_transactions) + len(transfer_in_transactions)  # Keep for system

    if actual_transaction_count > 0 and not force_delete:
        total_cost = transfer.total_cost

        return JsonResponseHelper.requires_confirmation(
            message=f'This transfer has {user_transfer_count} transfer operations ({actual_transaction_count} system transactions). Delete anyway?',
            confirmation_data={
                'transaction_count': user_transfer_count,  # Show user-friendly count
                'actual_transaction_count': actual_transaction_count,  # Keep actual count
                'total_cost': round(total_cost, 3),
                'transactions': transfer_out_transactions,  # Show only OUT for display
                'transfer_out_transactions': transfer_out_transactions,  # Keep for safety
                'transfer_in_transactions': transfer_in_transactions  # Keep for safety
            }
        )

    try:
        transfer_number = f"Transfer {transfer.id}"

        if actual_transaction_count > 0:
            with transaction.atomic():
                # 🔧 FIXED: Proper deletion order and linking
                
                # Step 1: Delete TRANSFER_OUT transactions (they auto-delete linked TRANSFER_IN via related_transfer)
                transfer_out_txns = transfer.transactions.filter(transaction_type='TRANSFER_OUT')
                for txn in transfer_out_txns:
                    print(f"🗑️ DELETING TRANSFER_OUT: {txn.product.name} x{txn.quantity} (ID: {txn.id})")
                    # This will automatically delete the linked TRANSFER_IN via Transaction.delete()
                    txn.delete()
                
                # Step 2: Delete any remaining TRANSFER_IN transactions (orphaned ones)
                remaining_transfer_in = transfer.transactions.filter(transaction_type='TRANSFER_IN')
                for txn in remaining_transfer_in:
                    print(f"🗑️ DELETING REMAINING TRANSFER_IN: {txn.product.name} x{txn.quantity} (ID: {txn.id})")
                    # This will validate consumption and raise ValidationError if consumed
                    txn.delete()
                
                # Step 3: Delete the transfer group
                transfer.delete()
            
            # Clear cache
            try:
                ProductCacheHelper.clear_cache_after_product_update()
                TransferCacheHelper.clear_cache_after_transfer_delete(transfer_id)
                print("🔥 Cache cleared after transfer deletion")
            except Exception as e:
                print(f"⚠️ Cache clear error: {e}")

            return JsonResponseHelper.success(
                message=f'{transfer_number} and all {actual_transaction_count} linked transactions deleted successfully. Inventory updated.'
            )
        else:
            # No transactions, safe to delete
            transfer.delete()
            TransferCacheHelper.clear_cache_after_transfer_delete(transfer_id)
            return JsonResponseHelper.success(
                message=f'{transfer_number} deleted successfully'
            )
            
    except ValidationError as e:
        # 🛡️ ENHANCED: Better error handling for inventory consumption
        error_message = str(e)
        
        # Extract message from ValidationError list format
        if error_message.startswith('[') and error_message.endswith(']'):
            error_message = error_message[2:-2]  # Remove ['...']
        
        # Check if it's a TRANSFER_IN consumption error
        if "Cannot delete" in error_message or "consumed" in error_message.lower():
            # Extract key information for better error display
            lines = error_message.split('\\n')
            main_error = lines[0] if lines else error_message
            
            # Return enhanced error with transfer-specific context
            return JsonResponseHelper.error(
                error_message=f"Cannot delete transfer - transferred inventory has been consumed: {main_error}",
                error_type='transfer_inventory_consumed',
                detailed_message=error_message,
                suggested_actions=[
                    {
                        'action': 'view_transactions',
                        'label': 'View Transaction Log',
                        'url': reverse('frontend:transactions_list'),
                        'description': 'Find and delete the sales/transfers that consumed from the transferred inventory'
                    },
                    {
                        'action': 'check_destination_vessel',
                        'label': 'Check Destination Vessel Inventory',
                        'url': reverse('frontend:inventory_check'),
                        'description': 'Review inventory levels on the destination vessel to understand consumption'
                    },
                    {
                        'action': 'contact_admin',
                        'label': 'Contact Administrator',
                        'description': 'Get help resolving the inventory conflict'
                    }
                ]
            )
        else:
            return JsonResponseHelper.error(
                error_message=f"Cannot delete transfer: {error_message}",
                error_type='validation_error'
            )
            
    except Exception as e:
        return JsonResponseHelper.error(
            error_message=f"An unexpected error occurred while deleting transfer: {str(e)}",
            error_type='system_error'
        )

@login_required
@user_passes_test(is_admin_or_manager)
def toggle_transfer_status(request, transfer_id):
    """Toggle transfer completion status - SIMPLE: Like PO pattern (0 cache clearing lines)"""
    # Get transfer safely
    transfer, error = CRUDHelper.safe_get_object(Transfer, transfer_id, 'Transfer')
    if error:
        return error
    
    # SIMPLE: No cache clearing needed (like PO toggle - works with simple versioning)
    # Toggle status with standardized response
    return CRUDHelper.toggle_boolean_field(transfer, 'is_completed', 'Transfer')