"""
Transfer Workflow Views
Implements the collaborative two-party transfer approval system from new_features.txt
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Prefetch
from datetime import datetime
import json
import logging

from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, InventoryLot, Transfer
from vessel_management.models import (
    TransferWorkflow, 
    TransferItemEdit, 
    TransferApprovalHistory, 
    TransferNotification,
    UserVesselAssignment
)
from vessel_management.utils import VesselAccessHelper, VesselOperationValidator
from frontend.utils.cache_helpers import VesselCacheHelper
from .utils import BilingualMessages
from .permissions import operations_access_required

logger = logging.getLogger('frontend')


@operations_access_required
def transfer_workflow_dashboard(request):
    """
    Transfer workflow dashboard - now redirects to unified transfer_entry.
    The transfer_entry template now includes all dashboard functionality.
    """
    return redirect('frontend:transfer_entry')


@operations_access_required
def transfer_workflow_create(request):
    """
    Create a new collaborative transfer workflow.
    This replaces the simple transfer creation with approval workflow.
    """
    if request.method == 'GET':
        # Get vessels user can transfer FROM (initiate transfers)
        all_vessels_qs = Vessel.objects.filter(active=True)
        from_vessels = VesselAccessHelper.filter_vessels_by_user_access(all_vessels_qs, request.user)
        
        # Get vessels user can transfer TO (available destinations)
        # Show ALL active vessels - FROM vessel will be excluded dynamically in frontend
        to_vessels = all_vessels_qs
        
        context = {
            'from_vessels': from_vessels,
            'to_vessels': to_vessels,
            'today': timezone.now().date(),
        }
        
        return render(request, 'frontend/transfer_workflow/create.html', context)
    
    elif request.method == 'POST':
        try:
            with transaction.atomic():
                # Get form data
                from_vessel_id = request.POST.get('from_vessel')
                to_vessel_id = request.POST.get('to_vessel')
                transfer_date = request.POST.get('transfer_date')
                notes = request.POST.get('notes', '').strip()
                
                # Validate required fields
                if not all([from_vessel_id, to_vessel_id, transfer_date]):
                    BilingualMessages.error(request, 'required_fields_missing')
                    return redirect('frontend:transfer_workflow_create')
                
                # Get vessels
                from_vessel = get_object_or_404(Vessel, id=from_vessel_id, active=True)
                to_vessel = get_object_or_404(Vessel, id=to_vessel_id, active=True)
                
                # Validate user can initiate transfers from from_vessel
                can_initiate, error_msg = VesselOperationValidator.validate_transfer_initiation(
                    request.user, from_vessel
                )
                if not can_initiate:
                    BilingualMessages.error(request, 'vessel_access_denied', error=error_msg)
                    return redirect('frontend:transfer_workflow_create')
                
                # Don't pre-assign TO user - let any authorized user for the vessel review
                # This makes transfers vessel-based rather than user-specific
                to_user = None  # Will be assigned when someone actually reviews the transfer
                
                # Parse transfer date
                transfer_date_obj = datetime.strptime(transfer_date, '%Y-%m-%d').date()
                
                # Create base transfer record
                base_transfer = Transfer.objects.create(
                    from_vessel=from_vessel,
                    to_vessel=to_vessel,
                    transfer_date=transfer_date_obj,
                    notes=notes,
                    created_by=request.user,
                    is_completed=False  # Will be completed through workflow
                )
                
                # Create transfer workflow - don't assign users until final approval
                workflow = TransferWorkflow.objects.create(
                    base_transfer=base_transfer,
                    from_user=None,  # Will be assigned when transfer is finally approved
                    to_user=None,  # Will be assigned when someone actually reviews the transfer
                    status='created',
                    notes=notes
                )
                
                BilingualMessages.success(request, 
                    f'Transfer workflow created successfully. Transfer ID: {base_transfer.id}')
                
                return redirect('frontend:transfer_workflow_items', workflow_id=workflow.id)
                
        except Exception as e:
            logger.error(f"Error creating transfer workflow: {e}")
            BilingualMessages.error(request, f'Error creating transfer: {str(e)}')
            return redirect('frontend:transfer_workflow_create')


@operations_access_required
def transfer_workflow_items(request, workflow_id):
    """
    Add items to transfer workflow (FROM user perspective).
    Similar to transfer_items but with workflow context.
    """
    workflow = get_object_or_404(
        TransferWorkflow.objects.select_related(
            'base_transfer__from_vessel',
            'base_transfer__to_vessel',
            'from_user',
            'to_user'
        ),
        id=workflow_id
    )
    
    # Check if user can add items during creation (vessel-based access)
    from .permissions import can_access_operations
    from vessel_management.models import UserVesselAssignment
    
    can_modify = (
        request.user.is_superuser or
        request.user == workflow.base_transfer.created_by or  # Original creator
        (UserVesselAssignment.can_user_access_vessel(request.user, workflow.base_transfer.from_vessel) and
         can_access_operations(request.user))
    )
    
    if not can_modify or workflow.status != 'created':
        BilingualMessages.error(request, 'You cannot modify this transfer at this time.')
        return redirect('frontend:transfer_workflow_dashboard')
    
    # Get existing transfer transactions
    existing_items = Transaction.objects.filter(
        transfer=workflow.base_transfer,
        transaction_type='TRANSFER_OUT'
    ).select_related('product')
    
    context = {
        'workflow': workflow,
        'transfer': workflow.base_transfer,
        'existing_items': existing_items,
        'can_edit': workflow.status == 'created',
    }
    
    return render(request, 'frontend/transfer_workflow/items.html', context)


@operations_access_required
def transfer_workflow_add_item(request):
    """
    Add item to transfer workflow.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            workflow_id = data.get('workflow_id')
            product_id = data.get('product_id')
            quantity = data.get('quantity')
            notes = data.get('notes', '')
            
            workflow = get_object_or_404(TransferWorkflow, id=workflow_id)
            
            # Validate user permissions - vessel-based access
            from .permissions import can_access_operations
            from vessel_management.models import UserVesselAssignment
            
            can_add_item = (
                request.user.is_superuser or
                request.user == workflow.base_transfer.created_by or  # Original creator
                (UserVesselAssignment.can_user_access_vessel(request.user, workflow.base_transfer.from_vessel) and
                 can_access_operations(request.user))
            )
            
            if not can_add_item or workflow.status != 'created':
                return JsonResponse({'success': False, 'error': 'Cannot modify this transfer'})
            
            product = get_object_or_404(Product, id=product_id)
            
            with transaction.atomic():
                # Create TRANSFER_OUT transaction
                Transaction.objects.create(
                    vessel=workflow.base_transfer.from_vessel,
                    product=product,
                    transaction_type='TRANSFER_OUT',
                    quantity=quantity,
                    unit_price=product.purchase_price,
                    transaction_date=workflow.base_transfer.transfer_date,
                    transfer=workflow.base_transfer,
                    notes=notes,
                    created_by=request.user
                )
            
            return JsonResponse({
                'success': True,
                'message': 'Item added successfully'
            })
            
        except Exception as e:
            logger.error(f"Error adding transfer item: {e}")
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@operations_access_required
def transfer_workflow_remove_item(request):
    """
    Remove item from transfer workflow.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            workflow_id = data.get('workflow_id')
            item_id = data.get('item_id')
            
            workflow = get_object_or_404(TransferWorkflow, id=workflow_id)
            
            # Validate user permissions - vessel-based access
            from .permissions import can_access_operations
            from vessel_management.models import UserVesselAssignment
            
            can_remove_item = (
                request.user.is_superuser or
                request.user == workflow.base_transfer.created_by or  # Original creator
                (UserVesselAssignment.can_user_access_vessel(request.user, workflow.base_transfer.from_vessel) and
                 can_access_operations(request.user))
            )
            
            if not can_remove_item or workflow.status != 'created':
                return JsonResponse({'success': False, 'error': 'Cannot modify this transfer'})
            
            # Get and delete the transaction
            transaction_item = get_object_or_404(
                Transaction,
                id=item_id,
                transfer=workflow.base_transfer,
                transaction_type='TRANSFER_OUT'
            )
            
            transaction_item.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Item removed successfully'
            })
            
        except Exception as e:
            logger.error(f"Error removing transfer item: {e}")
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@operations_access_required
def transfer_workflow_submit(request):
    """
    Submit transfer workflow for review by TO user.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            workflow_id = data.get('workflow_id')
            items = data.get('items', [])
            
            workflow = get_object_or_404(TransferWorkflow, id=workflow_id)
            
            # Validate user permissions - check vessel access instead of specific user
            from .permissions import can_access_operations
            from vessel_management.models import UserVesselAssignment
            
            # Check if user has access to FROM vessel and operations permissions
            can_submit = (
                request.user.is_superuser or
                (UserVesselAssignment.can_user_access_vessel(request.user, workflow.base_transfer.from_vessel) and
                 can_access_operations(request.user))
            )
            
            if not can_submit:
                return JsonResponse({'success': False, 'error': 'You are not authorized to submit this transfer'})
                
            if workflow.status != 'created':
                return JsonResponse({'success': False, 'error': f'Transfer cannot be submitted in {workflow.get_status_display()} status. Only created transfers can be submitted.'})
            
            if not items:
                return JsonResponse({'success': False, 'error': 'No items to transfer'})
            
            with transaction.atomic():
                # Clear any existing transfer items
                Transaction.objects.filter(
                    transfer=workflow.base_transfer,
                    transaction_type__in=['TRANSFER_OUT', 'TRANSFER_IN']
                ).delete()
                
                # Add transfer items - Create transactions without consuming inventory yet
                # These will be "placeholder" transactions that don't execute FIFO until approved
                for item in items:
                    product = get_object_or_404(Product, id=item['product_id'])
                    quantity = item['quantity']
                    notes = item.get('notes', '')
                    
                    # Create TRANSFER_OUT transaction with pending flag
                    # Note: We'll override the save method behavior for workflow transfers
                    Transaction.objects.create(
                        vessel=workflow.base_transfer.from_vessel,
                        product=product,
                        transaction_type='TRANSFER_OUT',
                        quantity=quantity,
                        unit_price=product.purchase_price,  # Use current purchase price
                        transaction_date=workflow.base_transfer.transfer_date,
                        transfer=workflow.base_transfer,
                        transfer_to_vessel=workflow.base_transfer.to_vessel,  # Required for TRANSFER_OUT validation
                        notes=f"PENDING_APPROVAL: {notes}",  # Mark as pending approval
                        created_by=request.user
                    )
                
                # Submit workflow for review
                workflow.submit_for_review()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Transfer submitted for review by {workflow.base_transfer.to_vessel.name} vessel users',
                    'workflow_data': {
                        'id': workflow.id,
                        'status': workflow.get_status_display(),
                        'to_vessel': workflow.base_transfer.to_vessel.name,
                        'items_count': len(items)
                    }
                })
                
        except Exception as e:
            logger.error(f"Error submitting transfer workflow: {e}")
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@operations_access_required
def transfer_workflow_review(request, workflow_id):
    """
    Review transfer workflow (TO user perspective).
    Allows editing quantities and confirming/rejecting transfer.
    """
    workflow = get_object_or_404(
        TransferWorkflow.objects.select_related(
            'base_transfer__from_vessel',
            'base_transfer__to_vessel',
            'from_user',
            'to_user'
        ),
        id=workflow_id
    )
    
    # Check if user can review (assigned TO user or vessel-authorized user)
    from .permissions import can_access_operations
    from vessel_management.models import UserVesselAssignment
    
    # Determine what type of access this user has
    can_review_as_to_user = (
        request.user.is_superuser or
        (UserVesselAssignment.can_user_access_vessel(request.user, workflow.base_transfer.to_vessel) and
         can_access_operations(request.user))
    )
    
    can_confirm_as_from_user = (
        request.user.is_superuser or
        request.user == workflow.base_transfer.created_by or  # Original creator
        (UserVesselAssignment.can_user_access_vessel(request.user, workflow.base_transfer.from_vessel) and
         can_access_operations(request.user))
    )
    
    # Check access based on workflow status
    if workflow.status in ['pending_review', 'under_review']:
        # TO user review phase
        if not can_review_as_to_user:
            BilingualMessages.error(request, 'You are not authorized to review this transfer.')
            return redirect('frontend:transfer_workflow_dashboard')
    elif workflow.status == 'pending_confirmation':
        # FROM user confirmation phase (after TO user made edits)
        if not can_confirm_as_from_user:
            BilingualMessages.error(request, 'You are not authorized to confirm this transfer.')
            return redirect('frontend:transfer_workflow_dashboard')
    else:
        BilingualMessages.error(request, 'This transfer is not available for review.')
        return redirect('frontend:transfer_workflow_dashboard')
    
    # Start review if not already started
    if workflow.status == 'pending_review':
        workflow.start_review(request.user)
    
    # Get transfer items
    transfer_items = Transaction.objects.filter(
        transfer=workflow.base_transfer,
        transaction_type='TRANSFER_OUT'
    ).select_related('product')
    
    # Get edit history
    edit_history = TransferItemEdit.objects.filter(
        workflow=workflow
    ).select_related('product', 'edited_by').order_by('-edited_at')
    
    # Calculate total amount from transfer items
    total_amount = sum(item.total_amount for item in transfer_items)
    
    # Determine user's role and permissions
    is_to_user_phase = workflow.status in ['pending_review', 'under_review']
    is_from_user_phase = workflow.status == 'pending_confirmation'
    
    context = {
        'workflow': workflow,
        'transfer': workflow.base_transfer,
        'transfer_items': transfer_items,
        'edit_history': edit_history,
        'can_edit': workflow.can_be_edited and is_to_user_phase,  # Only TO users can edit during review
        'can_confirm': is_from_user_phase and can_confirm_as_from_user,  # FROM users confirm after edits
        'is_to_user_phase': is_to_user_phase,
        'is_from_user_phase': is_from_user_phase,
        'total_amount': total_amount,
    }
    
    return render(request, 'frontend/transfer_workflow/review.html', context)


@operations_access_required
def transfer_workflow_edit_quantities(request):
    """
    Edit transfer quantities (TO user only).
    Implements quantity editing workflow from requirements.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            workflow_id = data.get('workflow_id')
            edits = data.get('edits', [])
            
            workflow = get_object_or_404(TransferWorkflow, id=workflow_id)
            
            # Validate user and workflow state - vessel-based access
            from .permissions import can_access_operations
            from vessel_management.models import UserVesselAssignment
            
            can_edit = (
                request.user.is_superuser or
                (UserVesselAssignment.can_user_access_vessel(request.user, workflow.base_transfer.to_vessel) and
                 can_access_operations(request.user))
            )
            
            if not can_edit or not workflow.can_be_edited:
                return JsonResponse({'success': False, 'error': 'Cannot edit this transfer'})
            
            if not edits:
                return JsonResponse({'success': False, 'error': 'No edits provided'})
            
            with transaction.atomic():
                for edit in edits:
                    product_id = edit.get('product_id')
                    new_quantity = edit.get('new_quantity')
                    reason = edit.get('reason', '')
                    
                    # Get the transfer transaction
                    transfer_txn = Transaction.objects.get(
                        transfer=workflow.base_transfer,
                        product_id=product_id,
                        transaction_type='TRANSFER_OUT'
                    )
                    
                    original_quantity = transfer_txn.quantity
                    
                    # Record the edit
                    TransferItemEdit.objects.create(
                        workflow=workflow,
                        product_id=product_id,
                        original_quantity=original_quantity,
                        edited_quantity=new_quantity,
                        edited_by=request.user,
                        edit_reason=reason
                    )
                    
                    # Update the transaction quantity (total_amount is auto-calculated from quantity * unit_price)
                    transfer_txn.quantity = new_quantity
                    transfer_txn.save()
                
                # Mark workflow as having edits
                workflow.has_edits = True
                workflow.last_edited_by = request.user
                workflow.last_edited_at = timezone.now()
                workflow.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Transfer quantities edited. Changes recorded.',
                    'edits_count': len(edits)
                })
                
        except Exception as e:
            logger.error(f"Error editing transfer quantities: {e}")
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@operations_access_required
def transfer_workflow_confirm(request):
    """
    Confirm transfer workflow (both users).
    Implements mutual confirmation from requirements.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            workflow_id = data.get('workflow_id')
            action = data.get('action')  # 'confirm' or 'reject'
            reason = data.get('reason', '')
            
            workflow = get_object_or_404(TransferWorkflow, id=workflow_id)
            
            # Validate user can take this action - vessel-based access
            from .permissions import can_access_operations
            from vessel_management.models import UserVesselAssignment
            
            # Check if user can access FROM vessel (for confirmation after edits)
            can_access_from = (
                request.user.is_superuser or
                request.user == workflow.base_transfer.created_by or  # Original creator
                (UserVesselAssignment.can_user_access_vessel(request.user, workflow.base_transfer.from_vessel) and
                 can_access_operations(request.user))
            )
            
            # Check if user can access TO vessel (for review and confirmation)
            can_access_to = (
                request.user.is_superuser or
                (UserVesselAssignment.can_user_access_vessel(request.user, workflow.base_transfer.to_vessel) and
                 can_access_operations(request.user))
            )
            
            if not (can_access_from or can_access_to):
                return JsonResponse({'success': False, 'error': 'Not authorized'})
            
            if action == 'reject':
                workflow.reject_transfer(request.user, reason)
                return JsonResponse({
                    'success': True,
                    'message': 'Transfer rejected',
                    'status': 'rejected'
                })
            
            elif action == 'confirm':
                # Handle TO vessel user confirmation
                if can_access_to and workflow.status == 'under_review':
                    workflow.confirm_by_to_user(request.user)
                    message = 'Transfer confirmed by TO vessel user'
                    
                # Handle FROM vessel user confirmation
                elif can_access_from and workflow.status == 'pending_confirmation':
                    workflow.confirm_by_from_user(request.user)
                    message = 'Transfer confirmed by FROM vessel user'
                    
                else:
                    # Provide more specific error messages based on status and access
                    if workflow.status == 'under_review' and not can_access_to:
                        return JsonResponse({'success': False, 'error': f'You need access to {workflow.base_transfer.to_vessel.name} vessel to review this transfer'})
                    elif workflow.status == 'pending_confirmation' and not can_access_from:
                        return JsonResponse({'success': False, 'error': f'You need access to {workflow.base_transfer.from_vessel.name} vessel to confirm this transfer'})
                    elif workflow.status in ['completed', 'rejected', 'cancelled']:
                        return JsonResponse({'success': False, 'error': f'This transfer has already been {workflow.status} and cannot be modified'})
                    else:
                        return JsonResponse({'success': False, 'error': f'Transfer is in {workflow.get_status_display()} status and cannot be confirmed at this time'})
                
                # If both parties confirmed, execute the transfer
                if workflow.status == 'confirmed':
                    # Execute inventory transfer - now trigger FIFO consumption for pending transactions
                    try:
                        # Get existing TRANSFER_OUT transactions for this transfer
                        existing_items = Transaction.objects.filter(
                            transfer=workflow.base_transfer,
                            transaction_type='TRANSFER_OUT'
                        )
                        
                        if existing_items.exists():
                            # Execute the transfer properly by re-triggering FIFO and completion
                            with transaction.atomic():
                                for txn in existing_items:
                                    # Remove PENDING_APPROVAL flag from notes
                                    if txn.notes and txn.notes.startswith('PENDING_APPROVAL: '):
                                        txn.notes = txn.notes.replace('PENDING_APPROVAL: ', '')
                                    
                                    # Re-save transaction to execute FIFO consumption
                                    # Since workflow is now confirmed, _is_workflow_transfer_pending() returns False
                                    txn.save()
                                    logger.info(f"Re-saved transaction {txn.id} to execute FIFO consumption")
                                    
                                    # Force transfer completion if not already completed
                                    # Check if this TRANSFER_OUT already has a related TRANSFER_IN
                                    if not txn.related_transfer:
                                        try:
                                            txn._complete_transfer_idempotent()
                                            logger.info(f"Force-completed transfer for transaction: {txn.id}")
                                        except Exception as e:
                                            logger.error(f"Error completing transfer for transaction {txn.id}: {e}")
                                            raise e
                            
                            # Mark workflow as completed
                            workflow.complete_transfer(completed_by_user=request.user)
                            message += '. Transfer executed and inventories updated.'
                            
                        else:
                            return JsonResponse({'success': False, 'error': 'No items found for transfer execution'})
                            
                    except Exception as e:
                        return JsonResponse({'success': False, 'error': f'Transfer execution failed: {str(e)}'})
                
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'status': workflow.status,
                    'mutual_agreement': workflow.mutual_agreement
                })
            
        except Exception as e:
            logger.error(f"Error confirming transfer workflow: {e}")
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@operations_access_required
def transfer_workflow_history(request, workflow_id):
    """
    View complete transfer workflow history.
    Implements process history tracking from requirements.
    """
    workflow = get_object_or_404(
        TransferWorkflow.objects.select_related(
            'base_transfer__from_vessel',
            'base_transfer__to_vessel',
            'from_user',
            'to_user'
        ),
        id=workflow_id
    )
    
    # Validate user can view this workflow (vessel-based access)
    from .permissions import can_access_operations
    from vessel_management.models import UserVesselAssignment
    
    can_view = (
        request.user.is_superuser or
        request.user == workflow.base_transfer.created_by or  # Original creator
        (workflow.from_user and request.user == workflow.from_user) or  # Final FROM approver
        (workflow.to_user and request.user == workflow.to_user) or  # Final TO approver
        # Any user with vessel access
        (UserVesselAssignment.can_user_access_vessel(request.user, workflow.base_transfer.from_vessel) and can_access_operations(request.user)) or
        (UserVesselAssignment.can_user_access_vessel(request.user, workflow.base_transfer.to_vessel) and can_access_operations(request.user))
    )
    
    if not can_view:
        BilingualMessages.error(request, 'You are not authorized to view this transfer.')
        return redirect('frontend:transfer_workflow_dashboard')
    
    # Get complete history
    approval_history = TransferApprovalHistory.objects.filter(
        workflow=workflow
    ).select_related('user').order_by('performed_at')
    
    item_edits = TransferItemEdit.objects.filter(
        workflow=workflow
    ).select_related('product', 'edited_by').order_by('edited_at')
    
    notifications = TransferNotification.objects.filter(
        workflow=workflow
    ).select_related('recipient').order_by('created_at')
    
    transfer_items = Transaction.objects.filter(
        transfer=workflow.base_transfer,
        transaction_type='TRANSFER_OUT'
    ).select_related('product')
    
    # Calculate total amount
    total_amount = sum(item.total_amount for item in transfer_items)
    
    context = {
        'workflow': workflow,
        'transfer': workflow.base_transfer,
        'approval_history': approval_history,
        'item_edits': item_edits,
        'notifications': notifications,
        'transfer_items': transfer_items,
        'total_amount': total_amount,
    }
    
    return render(request, 'frontend/transfer_workflow/history.html', context)


@operations_access_required
def transfer_notifications_list(request):
    """
    List all transfer notifications for the user.
    """
    notifications = TransferNotification.objects.filter(
        recipient=request.user
    ).select_related(
        'workflow__base_transfer__from_vessel',
        'workflow__base_transfer__to_vessel'
    ).order_by('-created_at')
    
    # Pagination
    paginator = Paginator(notifications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Calculate read count for template
    unread_count = notifications.filter(is_read=False).count()
    total_count = notifications.count()
    read_count = total_count - unread_count
    
    context = {
        'notifications': page_obj,
        'unread_count': unread_count,
        'read_count': read_count,
    }
    
    return render(request, 'frontend/transfer_workflow/notifications.html', context)


@operations_access_required
def transfer_notification_mark_read(request):
    """
    Mark notifications as read.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            notification_ids = data.get('notification_ids', [])
            
            updated = TransferNotification.objects.filter(
                id__in=notification_ids,
                recipient=request.user
            ).update(
                is_read=True,
                read_at=timezone.now()
            )
            
            return JsonResponse({
                'success': True,
                'message': f'{updated} notifications marked as read'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})