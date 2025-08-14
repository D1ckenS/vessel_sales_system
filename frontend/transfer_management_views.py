from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db import transaction
from frontend.utils.cache_helpers import TransferCacheHelper, VesselCacheHelper, get_optimized_pagination
from .utils.query_helpers import TransactionQueryHelper
from transactions.models import Transfer
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from datetime import datetime
from frontend.utils.cache_helpers import ProductCacheHelper
from .permissions import is_admin_or_manager
from .utils.response_helpers import JsonResponseHelper
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .utils.crud_helpers import CRUDHelper, AdminActionHelper
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)
import json
import logging

logger = logging.getLogger('frontend')

@login_required
@user_passes_test(is_admin_or_manager)
def transfer_management(request):
    """OPTIMIZED: Transfer management with COUNT-free pagination"""
    
    # Get filter parameters
    from_vessel_filter = request.GET.get('from_vessel')
    to_vessel_filter = request.GET.get('to_vessel')
    status_filter = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    search_filter = request.GET.get('search', '').strip()
    
    # Base queryset with prefetched transactions
    transfers = Transfer.objects.select_related(
        'from_vessel', 'to_vessel', 'created_by'
    ).prefetch_related(
        'transactions'
    )
    
    # Apply filters
    if from_vessel_filter:
        transfers = transfers.filter(from_vessel_id=from_vessel_filter)
    if to_vessel_filter:
        transfers = transfers.filter(to_vessel_id=to_vessel_filter)
    if status_filter == 'completed':
        transfers = transfers.filter(is_completed=True)
    elif status_filter == 'in_progress':
        transfers = transfers.filter(is_completed=False)
    if date_from:
        try:
            date_from_parsed = datetime.strptime(date_from, '%Y-%m-%d').date()
            transfers = transfers.filter(transfer_date__gte=date_from_parsed)
        except ValueError:
            pass
    if date_to:
        try:
            date_to_parsed = datetime.strptime(date_to, '%Y-%m-%d').date()
            transfers = transfers.filter(transfer_date__lte=date_to_parsed)
        except ValueError:
            pass
    if search_filter:
        transfers = transfers.filter(
            Q(from_vessel__name__icontains=search_filter) |
            Q(to_vessel__name__icontains=search_filter) |
            Q(notes__icontains=search_filter)
        )
    
    # Order for consistent results
    transfers = transfers.order_by('-transfer_date', '-created_at')
    
    # ✅ REPLACE Django Paginator with optimized pagination
    page_number = request.GET.get('page', 1)
    page_obj = get_optimized_pagination(transfers, page_number, page_size=25, use_count=False)
    
    # Add cost performance class to each transfer (for template)
    transfer_list = page_obj.object_list  # Use optimized pagination object list
    
    # OPTIMIZED: Calculate stats in Python using prefetched data
    total_cost = 0
    completed_count = 0
    total_transactions = 0
    
    # Add template-required annotations for each transfer
    for transfer in transfer_list:
        # Calculate cost using prefetched transactions (no additional queries)
        transfer_cost = sum(
            float(txn.quantity or 0) * float(txn.unit_price or 0)  # ✅ Add float() and handle None
            for txn in transfer.transactions.all()
            if txn.transaction_type == 'TRANSFER_OUT'  # Only count TRANSFER_OUT to avoid double counting
        )
        transfer_transaction_count = len([
            txn for txn in transfer.transactions.all()
            if txn.transaction_type == 'TRANSFER_OUT'
        ])
        
        # Add calculated fields to transfer object for template
        transfer.annotated_total_cost = transfer_cost
        transfer.annotated_transaction_count = transfer_transaction_count
        
        # Accumulate stats
        total_cost += transfer_cost
        total_transactions += transfer_transaction_count
        
        # Calculate cost performance class for template styling
        if transfer_cost > 1000:
            transfer.cost_performance_class = 'high-cost'
        elif transfer_cost > 500:
            transfer.cost_performance_class = 'medium-cost'
        else:
            transfer.cost_performance_class = 'low-cost'
        
        # Count completed transfers
        if transfer.is_completed:
            completed_count += 1
    
    # Calculate derived stats
    total_transfers = len(transfer_list)
    in_progress_count = total_transfers - completed_count
    completion_rate = (completed_count / max(total_transfers, 1)) * 100
    avg_transfer_cost = total_cost / max(total_transfers, 1)
    
    # Calculate recent activity from existing data
    week_ago = timezone.now() - timedelta(days=7)
    recent_transfers_count = sum(1 for transfer in transfer_list if transfer.created_at >= week_ago)
    recent_value = sum(transfer.annotated_total_cost for transfer in transfer_list if transfer.created_at >= week_ago)
    
    # Calculate vessel performance from existing data
    vessel_stats = {}
    for transfer in transfer_list:
        from_vessel_name = transfer.from_vessel.name
        to_vessel_name = transfer.to_vessel.name
        
        # Track outgoing transfers (from_vessel)
        if from_vessel_name not in vessel_stats:
            vessel_stats[from_vessel_name] = {
                'vessel': transfer.from_vessel,
                'outgoing_count': 0,
                'incoming_count': 0,
                'total_value': 0
            }
        vessel_stats[from_vessel_name]['outgoing_count'] += 1
        vessel_stats[from_vessel_name]['total_value'] += transfer.annotated_total_cost
        
        # Track incoming transfers (to_vessel)
        if to_vessel_name not in vessel_stats:
            vessel_stats[to_vessel_name] = {
                'vessel': transfer.to_vessel,
                'outgoing_count': 0,
                'incoming_count': 0,
                'total_value': 0
            }
        vessel_stats[to_vessel_name]['incoming_count'] += 1
    
    # Convert to list and sort by total transfer activity
    top_vessels = sorted(
        vessel_stats.values(), 
        key=lambda x: x['outgoing_count'] + x['incoming_count'], 
        reverse=True
    )[:5]
    
    context = {
        'transfers': transfer_list,
        'page_obj': page_obj,  # Optimized pagination object
        'active_vessels': VesselCacheHelper.get_active_vessels(),
        'page_title': 'Transfer Management',
        'stats': {
            'total_transfers': total_transfers,
            'completed_transfers': completed_count,
            'in_progress_transfers': in_progress_count,
            'completion_rate': round(completion_rate, 1),
            'total_transfer_value': total_cost,
            'avg_transfer_cost': round(avg_transfer_cost, 2),
            'total_transactions': total_transactions,
            'avg_transactions_per_transfer': round(total_transactions / max(total_transfers, 1), 1),
        },
        'recent_activity': {
            'recent_transfers': recent_transfers_count,
            'recent_value': recent_value,
        },
        'top_vessels': top_vessels,
        'current_filters': {
            'search': search_filter,
            'from_vessel': from_vessel_filter,
            'to_vessel': to_vessel_filter,
            'status': status_filter,
            'date_from': date_from,
            'date_to': date_to,
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
        
        transfer_items = []
        if transfer.is_completed:
            # Get transfer transactions for completed transfers
            transfer_transactions = transfer.transactions.filter(
                transaction_type__in=['TRANSFER_OUT', 'TRANSFER_IN']
            ).select_related('product').order_by('created_at')
            
            # Use TRANSFER_OUT transactions for cart data (avoid duplicates)
            for txn in transfer_transactions.filter(transaction_type='TRANSFER_OUT'):
                transfer_items.append({
                    'id': txn.id,
                    'product_id': txn.product.id,
                    'product_name': txn.product.name,
                    'product_item_id': txn.product.item_id,
                    'quantity': int(txn.quantity),
                    'unit_cost': float(txn.unit_price),
                    'total_cost': float(txn.total_amount),
                    'notes': txn.notes or '',
                    'created_at': txn.created_at.strftime('%H:%M')
                })
        
        return JsonResponse({
            'success': True,
            'transfer': transfer_data,
            'transfer_items': transfer_items  # FIXED: Include transfer items for preservation
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
                        logger.info(f"🔄 EDIT REOPENING: Removing {transfer_in_transactions.count()} TRANSFER_IN transactions")
                        
                        # Delete each TRANSFER_IN transaction (this removes inventory via Transaction.delete())
                        for txn in transfer_in_transactions:
                            txn.delete()
                        
                        logger.info(f"✅ EDIT REOPENED: All TRANSFER_IN inventory removed from {transfer.to_vessel.name}")
            
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
                    
                    cache.delete(completed_cache_key)
                    logger.debug(f"🔥 DELETED SPECIFIC CACHE: {completed_cache_key}")
                
                TransferCacheHelper.clear_all_transfer_cache()
                logger.debug("🔥 Enhanced cache cleared due to status change")
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
                    logger.info(f"🗑️ DELETING TRANSFER_OUT: {txn.product.name} x{txn.quantity} (ID: {txn.id})")
                    # This will automatically delete the linked TRANSFER_IN via Transaction.delete()
                    txn.delete()
                
                # Step 2: Delete any remaining TRANSFER_IN transactions (orphaned ones)
                remaining_transfer_in = transfer.transactions.filter(transaction_type='TRANSFER_IN')
                for txn in remaining_transfer_in:
                    logger.info(f"🗑️ DELETING REMAINING TRANSFER_IN: {txn.product.name} x{txn.quantity} (ID: {txn.id})")
                    # This will validate consumption and raise ValidationError if consumed
                    txn.delete()
                
                # Step 3: Delete the transfer group
                transfer.delete()
            
            # Clear cache
            try:
                ProductCacheHelper.clear_cache_after_product_update()
                TransferCacheHelper.clear_cache_after_transfer_delete(transfer_id)
                logger.debug("🔥 Cache cleared after transfer deletion")
            except Exception as e:
                logger.warning(f"⚠️ Cache clear error: {e}")

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
    """Toggle transfer completion status with proper transaction deletion"""
    # Get transfer safely
    transfer, error = CRUDHelper.safe_get_object(Transfer, transfer_id, 'Transfer')
    if error:
        return error
    
    try:
        # Determine the action based on current status
        if transfer.is_completed:
            # RESTART WORKFLOW: completed → incomplete
            with transaction.atomic():
                # Delete all TRANSFER_IN transactions to remove inventory from destination vessel
                transfer_in_transactions = transfer.transactions.filter(transaction_type='TRANSFER_IN')
                
                transaction_count = transfer_in_transactions.count()
                
                if transaction_count > 0:
                    logger.info(f"🔄 TRANSFER RESTART: Removing {transaction_count} TRANSFER_IN transactions for transfer {transfer.id}")
                    
                    # Delete each TRANSFER_IN transaction (this removes inventory via Transaction.delete())
                    for txn in transfer_in_transactions:
                        txn.delete()
                    
                    logger.info(f"✅ TRANSFER RESTART: All TRANSFER_IN inventory removed from {transfer.to_vessel.name}")
                
                # Mark as incomplete
                transfer.is_completed = False
                transfer.save()
                
                # Clear transfer cache
                TransferCacheHelper.clear_cache_after_transfer_update(transfer_id)
                
                logger.info(f"🔄 TRANSFER RESTART: Transfer {transfer.id} reopened for editing")
            
            # Return redirect response to restart workflow at transfer_items
            return JsonResponse({
                'success': True,
                'action': 'restart_workflow',
                'message': f'Transfer reopened successfully. Inventory restored for {transaction_count} items.',
                'redirect_url': reverse('frontend:transfer_items', kwargs={'transfer_id': transfer_id}),
                'transaction_count': transaction_count,
                'transfer_data': {
                    'from_vessel': transfer.from_vessel.name,
                    'to_vessel': transfer.to_vessel.name,
                    'is_completed': False
                }
            })
            
        else:
            # SIMPLE TOGGLE: incomplete → completed
            # Use standard toggle (stays on management page)
            transfer.is_completed = True
            transfer.save()
            
            # Clear transfer cache
            TransferCacheHelper.clear_cache_after_transfer_update(transfer_id)
            
            return JsonResponse({
                'success': True,
                'action': 'mark_completed',
                'message': f'Transfer marked as completed successfully.',
                'new_status': True,
                'transfer_data': {
                    'from_vessel': transfer.from_vessel.name,
                    'to_vessel': transfer.to_vessel.name,
                    'is_completed': True
                }
            })
            
    except Exception as e:
        return JsonResponseHelper.error(
            error_message=f"Error toggling transfer status: {str(e)}",
            error_type='system_error'
        )