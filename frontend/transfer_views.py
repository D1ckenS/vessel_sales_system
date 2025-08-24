from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, Prefetch
from django.http import JsonResponse, Http404
from datetime import date, datetime
from frontend.utils.cache_helpers import ProductCacheHelper, VesselCacheHelper, TransferCacheHelper
from frontend.utils.helpers import get_fifo_cost_for_transfer
from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, InventoryLot, Transfer, get_available_inventory, get_available_inventory_at_date
from .utils import BilingualMessages
from products.models import Product
from django.db import transaction
import json
import logging

logger = logging.getLogger('frontend')
from decimal import Decimal
import uuid
import time
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)
from vessel_management.utils import VesselAccessHelper, VesselOperationValidator, VesselFormHelper
from vessel_management.models import TransferWorkflow, TransferNotification, UserVesselAssignment

@operations_access_required
def transfer_search_products(request):
    """AJAX endpoint to search for products with available inventory on specific vessel"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        
        data = json.loads(request.body)
        search_term = data.get('search', '').strip()
        vessel_id = data.get('vessel_id')
        
        if not search_term or not vessel_id:
            return JsonResponse({'success': False, 'error': 'Search term and vessel required'})
        
        # Get vessel
        vessel = Vessel.objects.get(id=vessel_id, active=True)
        
        # Validate user has access to this vessel for transfer operations
        can_access, error_msg = VesselOperationValidator.validate_transfer_initiation(request.user, vessel)
        if not can_access:
            return JsonResponse({'success': False, 'error': error_msg})
        
        # Search for products with available inventory on this vessel
        available_lots = InventoryLot.objects.filter(
            vessel=vessel,
            remaining_quantity__gt=0,
            product__active=True
        ).filter(
            Q(product__name__icontains=search_term) |
            Q(product__item_id__icontains=search_term) |
            Q(product__barcode__icontains=search_term)
        ).select_related('product')
        
        # Group by product and calculate totals
        product_summaries = available_lots.values(
            'product__id', 'product__name', 'product__item_id', 
            'product__barcode', 'product__is_duty_free'
        ).annotate(
            total_quantity=Sum('remaining_quantity')
        ).order_by('product__item_id')
        
        products = []
        for summary in product_summaries:
            product_id = summary['product__id']
            
            # Get FIFO lots for this product
            lots = InventoryLot.objects.filter(
                vessel=vessel,
                product_id=product_id,
                remaining_quantity__gt=0
            ).order_by('purchase_date', 'created_at')
            
            lots_data = []
            for lot in lots:
                lots_data.append({
                    'id': lot.id,
                    'purchase_date': lot.purchase_date.strftime('%d/%m/%Y'),
                    'remaining_quantity': lot.remaining_quantity,
                    'original_quantity': lot.original_quantity,
                    'purchase_price': float(lot.purchase_price)
                })
            
            products.append({
                'id': product_id,
                'name': summary['product__name'],
                'item_id': summary['product__item_id'],
                'barcode': summary['product__barcode'] or '',
                'is_duty_free': summary['product__is_duty_free'],
                'total_quantity': summary['total_quantity'],
                'lots': lots_data
            })
        
        return JsonResponse({
            'success': True,
            'products': products
        })
        
    except Vessel.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Vessel not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
@operations_access_required
def transfer_entry(request):
    """Step 1: Create new transfer (follows sales_entry/supply_entry pattern)"""
    
    if request.method == 'GET':
        # 🎯 USER CONSOLIDATION: Single user reference for entire view
        current_user = request.user  # Cache user to eliminate duplicate queries
        
        # 🔥 MEGA OPTIMIZATION: Try to get entire context from cache first
        from django.core.cache import cache
        # Include recent_transfers version in cache key so context becomes invalid when transfers change
        recent_transfers_version = cache.get('recent_transfers_version', 1)
        context_cache_key = f"transfer_entry_context_{current_user.id}_v{recent_transfers_version}"
        cached_context = cache.get(context_cache_key)
        
        if cached_context is not None:
            # Use cached context, only update dynamic data
            cached_context['today'] = date.today()
            return render(request, 'frontend/transfer_entry.html', cached_context)
        
        # 🚀 VESSEL CACHE: Use cached vessels for cross-page efficiency
        all_vessels_cached = VesselCacheHelper.get_all_vessels_basic_data()
        vessels = [v for v in all_vessels_cached if v.active]
        all_vessels_qs = vessels  # Same vessel list for both contexts
        
        # 🚀 OPTIMIZED: Check cache for recent transfers with cost data (like supply_entry)
        cached_transfers = TransferCacheHelper.get_recent_transfers_with_cost()
        
        if cached_transfers:
            logger.debug(f"Cache hit: Recent transfers ({len(cached_transfers)} transfers)")
            recent_transfers = cached_transfers
        else:
            logger.debug("Cache miss: Building recent transfers")
            
            # 🎯 OPTIMIZED: Add comprehensive select_related to avoid duplicate user queries  
            recent_transfers_query = Transfer.objects.select_related(
                'from_vessel', 'to_vessel', 'created_by',
                'workflow__from_user', 'workflow__to_user', 'workflow__completed_by'
            ).order_by('-created_at')[:5]
            
            # 🚀 BACK TO BASICS: Skip expensive calculations for now
            recent_transfers = []
            for transfer in recent_transfers_query:
                # Add minimal calculated fields to Transfer object using database fields
                transfer.display_total_cost = float(transfer.total_cost or 0)  # Use pre-calculated field
                transfer.display_transaction_count = transfer.item_count or 0  # Use pre-calculated field
                recent_transfers.append(transfer)
            
            # 🚀 CACHE: Store processed transfers for future requests (like supply_entry)
            TransferCacheHelper.cache_recent_transfers_with_cost(recent_transfers)
            logger.debug(f"Cached: Recent transfers ({len(recent_transfers)} transfers) - 1 hour timeout")
        
        # Get workflow models for dashboard stats - Updated for vessel-based workflow
        
        # 🎯 RADICAL ISOLATION: Skip all user-related queries temporarily
        user_vessel_ids = []  # Empty to eliminate any user-vessel queries
        
        # 🚀 BACK TO BASICS: Simple workflow count
        pending_transfers_count = 0  # Skip for now to avoid complex queries
        
        # Skip fetching pending_transfers objects entirely for dashboard
        pending_transfers = []
        
        # 🚀 BACK TO BASICS: Skip notification count for now
        notification_count = 0  # Skip to avoid additional queries
        
        # Skip fetching notification objects entirely for initial page load
        unread_notifications = []
        
        # 🎯 SAFE OPTIMIZATION: Reuse vessels to avoid duplicate context
        user_vessels = vessels  # Reuse existing data
        
        # Filter recent transfers to only show completed workflow transfers for count
        completed_transfers = []
        for transfer in recent_transfers:
            if hasattr(transfer, 'workflow') and transfer.workflow:
                # Only show as completed if workflow is actually completed
                if transfer.workflow.status == 'completed':
                    completed_transfers.append(transfer)
            else:
                # Non-workflow transfers (legacy) - consider completed if is_completed=True
                if transfer.is_completed:
                    completed_transfers.append(transfer)
        
        context = {
            'vessels': vessels,
            'recent_transfers': recent_transfers,  # All recent transfers for the list
            'completed_transfers': completed_transfers,  # Only completed for the count
            'today': date.today(),
            # Dashboard-style stats
            'pending_transfers': pending_transfers,
            'unread_notifications': unread_notifications,
            'user_vessels': user_vessels,
            'pending_count': pending_transfers_count,
            'notification_count': notification_count,
        }
        
        # 🚀 ULTRA OPTIMIZED: Manual vessel context to avoid helper queries
        # Add vessel auto-population data manually using cached data
        default_vessel = vessels[0] if vessels else None
        context['auto_populate_vessel'] = default_vessel
        context['vessel_dropdown_readonly'] = len(vessels) == 1
        
        # 🎯 DUPLICATE ELIMINATION: Use same vessel data for both contexts
        context['transfer_to_vessels'] = all_vessels_qs  
        context['transfer_from_vessels'] = vessels
        
        # 🔥 MEGA OPTIMIZATION: Cache entire context for 3 minutes
        # Skip caching if user has pending transfers (dynamic data)
        if pending_transfers_count == 0 and notification_count == 0:
            context_to_cache = context.copy()
            context_to_cache.pop('today', None)  # Remove today from cached version
            cache.set(context_cache_key, context_to_cache, 180)  # 3 minutes
        
        return render(request, 'frontend/transfer_entry.html', context)
    
    elif request.method == 'POST':
        try:
            with transaction.atomic():
                # Create workflow models
                
                # Get form data
                from_vessel_id = request.POST.get('from_vessel')
                to_vessel_id = request.POST.get('to_vessel')
                transfer_date = request.POST.get('transfer_date')
                notes = request.POST.get('notes', '').strip()
                
                # Validate required fields
                if not all([from_vessel_id, to_vessel_id, transfer_date]):
                    BilingualMessages.error(request, 'required_fields_missing')
                    return redirect('frontend:transfer_entry')
                
                # Get vessels
                from_vessel = Vessel.objects.get(id=from_vessel_id, active=True)
                to_vessel = Vessel.objects.get(id=to_vessel_id, active=True)
                
                # Validate user can initiate transfers from from_vessel
                can_initiate, error_msg = VesselOperationValidator.validate_transfer_initiation(
                    request.user, from_vessel
                )
                if not can_initiate:
                    BilingualMessages.error(request, 'vessel_access_denied', error=error_msg)
                    return redirect('frontend:transfer_entry')
                
                # Validate vessels are different
                if from_vessel_id == to_vessel_id:
                    BilingualMessages.error(request, 'same_vessel_error')
                    return redirect('frontend:transfer_entry')
                
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
                
                # Create transfer workflow - both users pending until final approval
                # Note: from_user and to_user will be set to final approvers only when confirmed
                # Original creator is tracked in base_transfer.created_by
                workflow = TransferWorkflow.objects.create(
                    base_transfer=base_transfer,
                    from_user=None,  # Will be set to final approver from FROM side
                    to_user=None,    # Will be set to final approver from TO side  
                    status='created',
                    notes=notes
                )
                
                # Clear transfer cache
                TransferCacheHelper.clear_all_transfer_cache()
                
                BilingualMessages.success(request, 
                    f'Transfer workflow created successfully. Transfer ID: {base_transfer.id}')
                
                # Redirect to transfer items page (now with workflow support)
                return redirect('frontend:transfer_items', workflow_id=workflow.id)
                
        except Vessel.DoesNotExist:
            BilingualMessages.error(request, 'invalid_vessel')
            return redirect('frontend:transfer_entry')
        except (ValueError, ValidationError) as e:
            BilingualMessages.error(request, f'Validation error: {str(e)}')
            return redirect('frontend:transfer_entry')
        except Exception as e:
            logger.error(f"Error creating transfer workflow: {e}")
            BilingualMessages.error(request, f'Error creating transfer: {str(e)}')
            return redirect('frontend:transfer_entry')

@operations_access_required
def transfer_items(request, workflow_id):
    """Step 2: Multi-item transfer entry for workflow (collaborative transfer system)"""
    
    # Try to get workflow by workflow ID first
    try:
        workflow = TransferWorkflow.objects.select_related(
            'base_transfer__from_vessel',
            'base_transfer__to_vessel', 
            'from_user',
            'to_user'
        ).get(id=workflow_id)
    except TransferWorkflow.DoesNotExist:
        # If not found, maybe workflow_id is actually a Transfer ID
        # Try to find TransferWorkflow by base_transfer__id
        try:
            workflow = TransferWorkflow.objects.select_related(
                'base_transfer__from_vessel',
                'base_transfer__to_vessel', 
                'from_user',
                'to_user'
            ).get(base_transfer__id=workflow_id)
            
            # Redirect to the correct URL with the actual workflow ID
            return redirect('frontend:transfer_items', workflow_id=workflow.id)
        except TransferWorkflow.DoesNotExist:
            raise Http404("No TransferWorkflow matches the given query.")
    
    # Access control for collaborative workflow:
    # - FROM user can access during 'created' status (to add items)
    # - Any user with operations access to TO vessel can review during 'submitted' status
    # - TO user (if assigned) can access during review process
    # - SuperUser can access anytime
    from .permissions import can_access_operations
    from vessel_management.models import UserVesselAssignment
    
    # Check if user has access to destination vessel
    can_access_to_vessel = (
        request.user.is_superuser or
        UserVesselAssignment.can_user_access_vessel(request.user, workflow.base_transfer.to_vessel)
    )
    
    # Check if user is original creator
    is_original_creator = request.user == workflow.base_transfer.created_by
    
    # Check if user has vessel access for FROM vessel
    can_access_from_vessel = (
        request.user.is_superuser or
        UserVesselAssignment.can_user_access_vessel(request.user, workflow.base_transfer.from_vessel)
    )
    
    user_has_access = (
        request.user.is_superuser or
        # Original creator can always access their own transfers (especially for confirmation after edits)
        is_original_creator or
        # Any FROM vessel user with operations can access during creation and confirmations  
        (can_access_from_vessel and can_access_operations(request.user) and workflow.status in ['created', 'submitted', 'pending_confirmation']) or
        # Any TO vessel user with operations can access during review phases
        (can_access_to_vessel and can_access_operations(request.user) and workflow.status in ['pending_review', 'submitted', 'under_review'])
    )
    
    if not user_has_access:
        BilingualMessages.error(request, 'You cannot modify this transfer at this time.')
        return redirect('frontend:transfer_entry')
    
    # Get the base transfer
    transfer = workflow.base_transfer
    
    # Get existing transfer transactions (items already added)
    existing_items = Transaction.objects.filter(
        transfer=transfer,
        transaction_type='TRANSFER_OUT'
    ).select_related('product').order_by('created_at')
    
    # Calculate totals from existing items
    total_cost = sum(float(item.total_amount) for item in existing_items)
    transaction_count = existing_items.count()
    
    # Add calculated fields to transfer object for template compatibility
    transfer.display_total_cost = total_cost
    transfer.display_transaction_count = transaction_count
    
    # Process items for JSON (same structure as original transfer_items)
    existing_transfers = []
    for txn in existing_items:
        existing_transfers.append({
            'id': txn.id,
            'product_id': txn.product.id,
            'product_name': txn.product.name,
            'product_item_id': txn.product.item_id,
            'product_barcode': getattr(txn.product, 'barcode', '') or '',
            'is_duty_free': getattr(txn.product, 'is_duty_free', False),
            'quantity': int(txn.quantity),
            'unit_price': float(txn.unit_price),
            'total_amount': float(txn.total_amount),
            'notes': txn.notes or '',
            'created_at': txn.created_at.strftime('%H:%M')
        })
    
    # Convert to JSON for template
    existing_transfers_json = json.dumps(existing_transfers)
    
    context = {
        'workflow': workflow,
        'transfer': transfer,
        'existing_transfers_json': existing_transfers_json,
        'completed_transfers_json': existing_transfers_json,  # For JavaScript compatibility
        'can_edit': workflow.status == 'created',  # Can edit only during creation
        'existing_items': existing_items,  # For template compatibility
    }
    
    return render(request, 'frontend/transfer_items.html', context)

@operations_access_required
def transfer_available_products(request):
    """AJAX endpoint to get available products for transfer with historical inventory support"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        vessel_id = data.get('vessel_id')
        transfer_date_str = data.get('transfer_date')  # Optional transfer date for historical inventory
        
        if not vessel_id:
            return JsonResponse({'success': False, 'error': 'Vessel ID required'})
        
        # Get vessel
        vessel = Vessel.objects.get(id=vessel_id, active=True)
        
        # Parse transfer date if provided
        from django.utils import timezone
        transfer_date = None
        use_historical_inventory = False
        
        if transfer_date_str:
            try:
                transfer_date = datetime.strptime(transfer_date_str, '%Y-%m-%d').date()
                today = timezone.now().date()
                use_historical_inventory = transfer_date < today
            except ValueError:
                pass  # Invalid date format, use current inventory
        
        # Get all active products
        products_query = Product.objects.filter(active=True)
        
        products = []
        
        for product in products_query:
            # Calculate available inventory (current or historical)
            if use_historical_inventory and transfer_date:
                available_quantity, _ = get_available_inventory_at_date(vessel, product, transfer_date)
            else:
                available_quantity, _ = get_available_inventory(vessel, product)
            
            # Only include products with available inventory
            if available_quantity <= 0:
                continue
            
            products.append({
                'id': product.id,
                'name': product.name,
                'item_id': product.item_id,
                'barcode': product.barcode or '',
                'is_duty_free': product.is_duty_free,
                'total_quantity': available_quantity,  # Use calculated historical/current quantity
            })
        
        # Sort by item_id like the original
        products.sort(key=lambda p: p['item_id'] or '')
        
        return JsonResponse({
            'success': True,
            'products': products
        })
        
    except Vessel.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Vessel not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@operations_access_required
def transfer_bulk_complete(request):
    """
    🚀 OPTIMIZED: Complete transfer with batch processing (like trip/PO patterns)
    
    Performance improvements:
    - Batch FIFO calculations
    - Bulk transaction creation  
    - Batch inventory operations
    - Targeted cache clearing
    """
    
    print(f"DEBUG: transfer_bulk_complete called")  # Debug print
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        
        transfer_id = data.get('transfer_id')
        items = data.get('items', [])
        
        if not transfer_id or not items:
            return JsonResponse({'success': False, 'error': 'Transfer ID and items required'})
        
        # Get transfer record with related data in single query
        transfer = Transfer.objects.select_related(
            'from_vessel', 'to_vessel', 'created_by'
        ).get(id=transfer_id)
        
        from_vessel = transfer.from_vessel
        to_vessel = transfer.to_vessel
        transfer_date = transfer.transfer_date
        
        # 🚀 OPTIMIZATION 1: Batch validation and FIFO calculations
        logger.info(f"Batch processing: Starting transfer completion for {len(items)} items")
        
        with transaction.atomic():
            # 🚀 STEP 1: Clear existing transactions efficiently (single bulk operation)
            existing_transactions = Transaction.objects.filter(
                transfer=transfer,
                transaction_type__in=['TRANSFER_OUT', 'TRANSFER_IN']
            )

            if existing_transactions.exists():
                logger.info(f"Transfer edit: Deleting {existing_transactions.count()} existing transfer transactions for inventory restoration")
                
                # Delete each transaction individually to trigger inventory restoration
                for txn in existing_transactions:
                    txn.delete()  # This calls the individual delete() method with inventory restoration
                
                logger.info(f"Transfer edit: Inventory restored for {existing_transactions.count()} transactions")
                
            # 🚀 STEP 2: Batch product fetching and validation
            product_ids = [item.get('product_id') for item in items if item.get('product_id')]
            products_dict = {
                p.id: p for p in Product.objects.filter(id__in=product_ids, active=True)
            }
            
            # 🚀 STEP 3: Batch FIFO calculations for all items at once
            fifo_calculations = {}
            total_calculations_time = 0
            
            logger.debug(f"Batch FIFO: Calculating costs for {len(items)} items")
            fifo_start_time = time.time()
            
            for item in items:
                product_id = item.get('product_id')
                quantity = item.get('quantity', 0)
                
                if product_id not in products_dict:
                    continue
                    
                product = products_dict[product_id]
                
                try:
                    # Calculate FIFO cost (this is the expensive operation)
                    fifo_cost_per_unit = get_fifo_cost_for_transfer(from_vessel, product, quantity)
                    
                    fifo_calculations[product_id] = {
                        'product': product,
                        'quantity': quantity,
                        'unit_price': Decimal(str(fifo_cost_per_unit)) if fifo_cost_per_unit else Decimal('0.001'),
                        'notes': item.get('notes', ''),
                        'total_cost': (Decimal(str(fifo_cost_per_unit)) if fifo_cost_per_unit else Decimal('0.001')) * Decimal(str(quantity))
                    }
                    
                except Exception as e:
                    logger.warning(f"FIFO calculation failed for {product.name}: {e}")
                    # Use fallback cost
                    fifo_calculations[product_id] = {
                        'product': product,
                        'quantity': quantity,
                        'unit_price': product.purchase_price or Decimal('0.001'),
                        'notes': item.get('notes', ''),
                        'total_cost': (product.purchase_price or Decimal('0.001')) * Decimal(str(quantity))
                    }
            
            fifo_end_time = time.time()
            total_calculations_time = fifo_end_time - fifo_start_time
            logger.debug(f"FIFO batch completed: {total_calculations_time:.2f} seconds for {len(items)} items")
            
            # 🚀 STEP 3.5: Validate inventory availability at transfer date
            from django.utils import timezone
            today = timezone.now().date()
            use_historical_inventory = transfer_date < today
            
            for product_id, calc_data in fifo_calculations.items():
                product = calc_data['product']
                quantity = calc_data['quantity']
                
                # Check available inventory at transfer date (point-in-time validation)
                if use_historical_inventory:
                    available_quantity, _ = get_available_inventory_at_date(from_vessel, product, transfer_date)
                else:
                    available_quantity, _ = get_available_inventory(from_vessel, product)
                
                if quantity > available_quantity:
                    return JsonResponse({
                        'success': False, 
                        'error': f'Insufficient inventory for {product.name}. Available at {transfer_date}: {available_quantity}, Requested: {quantity}'
                    })
            
            # 🚀 STEP 4: Bulk create TRANSFER_OUT transactions (disable auto-creation)
            transfer_out_transactions = []
            transfer_in_transactions = []
            
            logger.debug("Batch creation: Creating TRANSFER_OUT transactions")
            
            for product_id, calc_data in fifo_calculations.items():
                # Create TRANSFER_OUT transaction data
                transfer_out = Transaction(
                    vessel=from_vessel,
                    product=calc_data['product'],
                    transaction_type='TRANSFER_OUT',
                    transaction_date=transfer_date,
                    quantity=calc_data['quantity'],
                    unit_price=calc_data['unit_price'],
                    transfer_to_vessel=to_vessel,
                    transfer=transfer,
                    notes=calc_data['notes'] or f'Transfer to {to_vessel.name}',
                    created_by=request.user
                )
                transfer_out_transactions.append(transfer_out)
                
                # Create corresponding TRANSFER_IN transaction data
                transfer_in = Transaction(
                    vessel=to_vessel,
                    product=calc_data['product'],
                    transaction_type='TRANSFER_IN',
                    transaction_date=transfer_date,
                    quantity=calc_data['quantity'],
                    unit_price=calc_data['unit_price'],
                    transfer_from_vessel=from_vessel,
                    transfer=transfer,
                    notes=f'Received from {from_vessel.name}',
                    created_by=request.user
                )
                transfer_in_transactions.append(transfer_in)
            
            # 🚀 STEP 5: Use bulk_create for maximum efficiency
            logger.debug(f"Bulk create: Creating {len(transfer_out_transactions)} TRANSFER_OUT transactions")
            created_out_transactions = Transaction.objects.bulk_create(transfer_out_transactions)
            
            logger.debug(f"Bulk create: Creating {len(transfer_in_transactions)} TRANSFER_IN transactions")  
            created_in_transactions = Transaction.objects.bulk_create(transfer_in_transactions)
            
            # 🚀 STEP 6: Batch inventory operations
            logger.debug(f"Batch inventory: Processing inventory for {len(fifo_calculations)} products")
            
            # Handle TRANSFER_OUT inventory consumption in batch
            _batch_consume_inventory_for_transfer_out(
                fifo_calculations, from_vessel, created_out_transactions
            )
            
            # Handle TRANSFER_IN inventory creation in batch  
            _batch_create_inventory_for_transfer_in(
                fifo_calculations, to_vessel, created_in_transactions
            )
            
            # 🚀 STEP 7: Link transactions efficiently
            logger.debug(f"Batch linking: Linking {len(created_out_transactions)} transaction pairs")
            
            # Link TRANSFER_OUT with TRANSFER_IN transactions
            for i, (out_txn, in_txn) in enumerate(zip(created_out_transactions, created_in_transactions)):
                out_txn.related_transfer_id = in_txn.id
                in_txn.related_transfer_id = out_txn.id
            
            # Bulk update the links
            Transaction.objects.bulk_update(created_out_transactions, ['related_transfer_id'])
            Transaction.objects.bulk_update(created_in_transactions, ['related_transfer_id'])
            
            # 🚀 STEP 8: Mark transfer as completed and update summary fields
            transfer.is_completed = True
            transfer.save(update_fields=['is_completed'])
            
            # 🚀 UPDATE SUMMARY FIELDS: Update pre-calculated fields after transactions are added
            transfer.update_summary_fields()
            
            # Submit workflow for review (move from 'created' to 'pending_review')
            try:
                workflow = transfer.workflow
                if workflow and workflow.status == 'created':
                    workflow.submit_for_review()
                    logger.info(f"Workflow submitted for review: {workflow.id}")
            except Exception as e:
                logger.warning(f"Failed to submit workflow for review: {e}")
            
            logger.info(f"Transfer completed: {len(created_out_transactions)} items transferred")
            
        # 🚀 OPTIMIZATION 5: Targeted cache clearing (not nuclear option)
        _clear_transfer_cache_targeted(transfer_id, from_vessel.id, to_vessel.id)
        
        # Calculate totals for response
        total_cost = sum(calc_data['total_cost'] for calc_data in fifo_calculations.values())
        total_items = len(fifo_calculations)
        
        return JsonResponse({
            'success': True,
            'message': f'Transfer completed successfully! {total_items} items transferred from {from_vessel.name} to {to_vessel.name}.',
            'transfer_id': transfer.id,
            'total_items': total_items,
            'total_cost': float(total_cost),
            'processing_time': f'{total_calculations_time:.2f}s',
            'performance_improvement': 'Batch processing enabled'
        })
        
    except Transfer.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Transfer not found'})
    except Exception as e:
        logger.error(f"Batch transfer error: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Transfer failed: {str(e)}'})


def _batch_consume_inventory_for_transfer_out(fifo_calculations, from_vessel, transfer_out_transactions):
    """
    🚀 BATCH OPERATION: Consume inventory for all TRANSFER_OUT transactions efficiently
    """    
    logger.debug(f"Batch consume: Processing inventory consumption for {len(fifo_calculations)} products")
    
    for product_id, calc_data in fifo_calculations.items():
        product = calc_data['product']
        quantity = calc_data['quantity']
        
        try:
            # Get inventory lots for this product in FIFO order
            inventory_lots = InventoryLot.objects.filter(
                vessel=from_vessel,
                product=product,
                remaining_quantity__gt=0
            ).select_for_update().order_by('purchase_date', 'created_at')
            
            # Consume inventory using FIFO
            remaining_to_consume = int(quantity)
            
            for lot in inventory_lots:
                if remaining_to_consume <= 0:
                    break
                    
                consume_from_lot = min(remaining_to_consume, lot.remaining_quantity)
                lot.remaining_quantity -= consume_from_lot
                lot.save(update_fields=['remaining_quantity'])
                
                remaining_to_consume -= consume_from_lot
                
                logger.debug(f"Consumed: {consume_from_lot} units of {product.name} from lot {lot.id}")
                
        except Exception as e:
            logger.error(f"Consume error for {product.name}: {e}")
            continue


def _batch_create_inventory_for_transfer_in(fifo_calculations, to_vessel, transfer_in_transactions):
    """
    🚀 BATCH OPERATION: Create inventory lots for all TRANSFER_IN transactions efficiently
    """    
    logger.debug(f"Batch create: Creating inventory lots for {len(fifo_calculations)} products")
    
    inventory_lots_to_create = []
    
    for product_id, calc_data in fifo_calculations.items():
        product = calc_data['product']
        quantity = calc_data['quantity']
        unit_price = calc_data['unit_price']
        
        # Create inventory lot data
        inventory_lot = InventoryLot(
            vessel=to_vessel,
            product=product,
            purchase_date=datetime.now().date(),
            purchase_price=unit_price,
            original_quantity=int(quantity),
            remaining_quantity=int(quantity),
            created_by=transfer_in_transactions[0].created_by  # Use first transaction's creator
        )
        inventory_lots_to_create.append(inventory_lot)
    
    # Bulk create all inventory lots
    if inventory_lots_to_create:
        InventoryLot.objects.bulk_create(inventory_lots_to_create)
        logger.debug(f"Created: {len(inventory_lots_to_create)} inventory lots for {to_vessel.name}")


def _clear_transfer_cache_targeted(transfer_id, from_vessel_id, to_vessel_id):
    """
    🚀 TARGETED CACHE CLEARING: Clear only relevant cache, not nuclear option
    """    
    print(f"DEBUG: _clear_transfer_cache_targeted called for transfer {transfer_id}")  # Debug print
    logger.debug(f"Targeted cache: Clearing cache for transfer {transfer_id}")
    
    try:
        # Clear transfer-specific cache (use completion-specific method)
        TransferCacheHelper.clear_cache_after_transfer_complete(transfer_id)
        
        # Clear vessel-specific cache (both vessels affected)
        VesselCacheHelper.clear_cache(from_vessel_id)
        VesselCacheHelper.clear_cache(to_vessel_id)
        
        # Clear product cache (inventory changed)
        ProductCacheHelper.clear_cache_after_product_update()
        
        logger.debug(f"Targeted cache cleared: Transfer {transfer_id}, Vessels {from_vessel_id}/{to_vessel_id}")
        
    except Exception as e:
        logger.warning(f"Cache clear warning: {e}")
        # Fallback to nuclear option if targeted fails
        TransferCacheHelper.clear_all_transfer_cache()
    
@operations_access_required
def transfer_execute(request):
    """AJAX endpoint to execute transfer using existing FIFO system"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        
        # Get and validate data
        from_vessel_id = data.get('from_vessel_id')
        to_vessel_id = data.get('to_vessel_id')
        product_id = data.get('product_id')
        quantity = data.get('quantity')
        transfer_date = data.get('transfer_date')
        notes = data.get('notes', '')
        
        if not all([from_vessel_id, to_vessel_id, product_id, quantity, transfer_date]):
            return JsonResponse({'success': False, 'error': 'Missing required fields'})
        
        # Get objects
        from_vessel = Vessel.objects.get(id=from_vessel_id, active=True)
        to_vessel = Vessel.objects.get(id=to_vessel_id, active=True)
        product = Product.objects.get(id=product_id, active=True)
        
        # Validate vessels are different
        if from_vessel_id == to_vessel_id:
            return JsonResponse({'success': False, 'error': 'Source and destination vessels must be different'})
        
        # Validate duty-free compatibility
        if product.is_duty_free and not to_vessel.has_duty_free:
            return JsonResponse({
                'success': False, 
                'error': f'Cannot transfer duty-free product to {to_vessel.name} (vessel does not support duty-free items)'
            })
        
        # Check available inventory
        available_quantity, lots = get_available_inventory(from_vessel, product)
        
        if quantity > available_quantity:
            return JsonResponse({
                'success': False, 
                'error': f'Insufficient inventory. Available: {available_quantity}, Requested: {quantity}'
            })
        
        # Parse transfer date
        transfer_date_obj = datetime.strptime(transfer_date, '%Y-%m-%d').date()
        
        # Create TRANSFER_OUT transaction (your existing system handles the rest!)
        transfer_out = Transaction.objects.create(
            vessel=from_vessel,
            product=product,
            transaction_type='TRANSFER_OUT',
            transaction_date=transfer_date_obj,
            quantity=quantity,
            transfer_to_vessel=to_vessel,
            notes=notes or f'Transfer to {to_vessel.name}',
            created_by=request.user
        )
                
        return JsonResponse({
            'success': True,
            'message': f'Transfer completed: {quantity} units of {product.name} from {from_vessel.name} to {to_vessel.name}',
            'transfer_id': transfer_out.id
        })
        
    except (Vessel.DoesNotExist, Product.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Vessel or product not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Transfer failed: {str(e)}'})
    
@operations_access_required
def transfer_calculate_fifo_cost(request):
    """Calculate FIFO cost for transfer item (NO AVERAGES - ONLY TOTAL COST)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        vessel_id = data.get('vessel_id')
        product_id = data.get('product_id')
        quantity = data.get('quantity')
        
        if not all([vessel_id, product_id, quantity]):
            return JsonResponse({'success': False, 'error': 'Missing required parameters'})
        
        # Get objects
        vessel = Vessel.objects.get(id=vessel_id, active=True)
        product = Product.objects.get(id=product_id, active=True)
        
        # Get FIFO cost calculation using existing helper        
        try:
            result = get_fifo_cost_for_transfer(vessel, product, quantity)
            
            if isinstance(result, tuple) and len(result) == 2:
                # Expected format: (total_cost, consumption_details)
                fifo_total_cost, consumption_details = result
            elif isinstance(result, (int, float, Decimal)):
                # The function returns UNIT COST, not total cost
                fifo_unit_cost = Decimal(str(result))  # This is the actual unit cost
                fifo_total_cost = fifo_unit_cost * Decimal(str(quantity))  # Calculate total
                consumption_details = []
            else:
                raise ValueError(f"Unexpected return format from get_fifo_cost_for_transfer: {type(result)}")
            
            # REMOVED: No average_unit_cost - only return total_cost and fifo_breakdown
            return JsonResponse({
                'success': True,
                'total_cost': float(fifo_total_cost),      # Only total cost needed
                'fifo_breakdown': consumption_details if isinstance(consumption_details, list) else [],
                'quantity': quantity
            })
            
        except Exception as e:
            logger.error(f"FIFO calculation error for vessel {vessel_id}, product {product_id}, quantity {quantity}: {e}")
            
            # Fallback calculation - only total cost
            fallback_unit_cost = Decimal('0.050')  # 50 fils per unit
            fallback_total_cost = fallback_unit_cost * Decimal(str(quantity))
            
            return JsonResponse({
                'success': True,
                'total_cost': float(fallback_total_cost),  # Only total cost
                'fifo_breakdown': [],
                'quantity': quantity,
                'warning': 'Used fallback cost calculation due to FIFO error'
            })
        
    except Vessel.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Vessel not found'})
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Product not found'})
    except Exception as e:
        logger.error(f"Endpoint error: {e}")
        return JsonResponse({'success': False, 'error': str(e)})
    
@operations_access_required  
def transfer_cancel(request):
    """Cancel transfer and delete it from database (if no items committed) - Following trip/PO pattern"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        transfer_id = data.get('transfer_id')
        
        if not transfer_id:
            return JsonResponse({'success': False, 'error': 'Transfer ID required'})
        
        # Get transfer
        transfer = Transfer.objects.get(id=transfer_id)
        
        if transfer.is_completed:
            return JsonResponse({'success': False, 'error': 'Cannot cancel completed transfer'})
        
        # Check if transfer has any committed transactions
        # NOTE: Adjust the filter based on your actual Transfer model relationship
        existing_transactions = Transaction.objects.filter(
            transfer=transfer  # Use the correct foreign key field name
        ).count()
        
        if existing_transactions > 0:
            # Transfer has committed transactions - just clear cart but keep transfer
            return JsonResponse({
                'success': True,
                'action': 'clear_cart',
                'message': f'Cart cleared. Transfer {transfer.id} kept (has committed transactions).'
            })
        else:
            # No committed transactions - safe to delete transfer
            transfer_display = f"#{transfer.id}"
            transfer.delete()
            
            # 🚀 CACHE: Clear transfer cache after deletion
            TransferCacheHelper.clear_cache_after_transfer_delete(transfer_id)
            
            return JsonResponse({
                'success': True,
                'action': 'delete_transfer',
                'message': f'Transfer {transfer_display} cancelled and removed.',
                'redirect_url': '/transfer/'  # Redirect back to transfer entry
            })
        
    except Transfer.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Transfer not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error cancelling transfer: {str(e)}'})