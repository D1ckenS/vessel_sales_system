from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, Prefetch
from django.http import JsonResponse
from datetime import date, datetime
from frontend.utils.cache_helpers import VesselCacheHelper, TransferCacheHelper
from frontend.utils.helpers import get_fifo_cost_for_transfer
from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, InventoryLot, Transfer, get_available_inventory
from .utils import BilingualMessages
from products.models import Product
from django.db import transaction
import json
from decimal import Decimal
import uuid
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

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
        vessels = VesselCacheHelper.get_active_vessels()
        
        # ✅ Show Transfer model records (like sales shows Trip records, supply shows PO records)
        recent_transfers = Transfer.objects.select_related(
            'from_vessel', 'to_vessel', 'created_by'
        ).prefetch_related(
            Prefetch(
                'transactions',
                queryset=Transaction.objects.filter(transaction_type='TRANSFER_OUT')
            )
        ).order_by('-created_at')[:10]
        
        context = {
            'vessels': vessels,
            'recent_transfers': recent_transfers,
            'today': date.today(),
        }
        
        return render(request, 'frontend/transfer_entry.html', context)
    
    elif request.method == 'POST':
        try:
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
            
            # Validate vessels are different
            if from_vessel_id == to_vessel_id:
                BilingualMessages.error(request, 'same_vessel_error')
                return redirect('frontend:transfer_entry')
            
            transfer_date_obj = datetime.strptime(transfer_date, '%Y-%m-%d').date()
            
            # ✅ Create Transfer record immediately (like sales creates Trip, supply creates PO)
            transfer = Transfer.objects.create(
                from_vessel=from_vessel,
                to_vessel=to_vessel,
                transfer_date=transfer_date_obj,
                notes=notes,
                is_completed=False,  # Start as incomplete
                created_by=request.user
            )
            
            # Clear transfer cache
            
            TransferCacheHelper.clear_recent_transfers_cache()
            
            BilingualMessages.success(request, 'transfer_created_success', transfer_number=transfer.id)
            # ✅ Redirect to transfer_items with transfer_id (like sales/supply pattern)
            return redirect('frontend:transfer_items', transfer_id=transfer.id)
            
        except Vessel.DoesNotExist:
            BilingualMessages.error(request, 'invalid_vessel')
            return redirect('frontend:transfer_entry')
        except (ValueError, ValidationError) as e:
            # Show actual error for debugging
            BilingualMessages.error(request, f'Validation error: {str(e)}')
            return redirect('frontend:transfer_entry')
        except Exception as e:
            # Show actual error for debugging  
            BilingualMessages.error(request, f'Actual error: {str(e)}')
            return redirect('frontend:transfer_entry')

@operations_access_required
def transfer_items(request, transfer_id):
    """Step 2: Multi-item transfer entry for a specific transfer (follows trip_sales/po_supply pattern)"""
    
    # 🚀 OPTIMIZED: Check cache first for completed transfers (no DB query needed)
    from frontend.utils.cache_helpers import TransferCacheHelper
    cached_data = TransferCacheHelper.get_completed_transfer_data(transfer_id)
    if cached_data:
        print(f"🚀 CACHE HIT: Completed transfer {transfer_id}")
        return render(request, 'frontend/transfer_items.html', cached_data)
    
    try:
        # 🚀 SUPER OPTIMIZED: Single query with everything (like trip_sales/po_supply)
        transfer = Transfer.objects.select_related(
            'from_vessel', 'to_vessel', 'created_by'
        ).prefetch_related(
            Prefetch(
                'transactions',
                queryset=Transaction.objects.select_related(
                    'product', 'product__category'
                ).filter(transaction_type='TRANSFER_OUT').order_by('created_at')
            )
        ).get(id=transfer_id)
        
        # 🚀 FORCE: Get all transactions immediately to prevent additional queries
        transfer_transactions = list(transfer.transactions.all())
        
    except Transfer.DoesNotExist:
        BilingualMessages.error(request, 'Transfer not found.')
        return redirect('frontend:transfer_entry')
    
    # 🚀 OPTIMIZED: Use prefetched data for all calculations (no additional queries)
    existing_transfers = []
    completed_transfers = []
    
    if not transfer.is_completed:
        # 🚀 OPTIMIZED: Process incomplete transfer using prefetched data (like trip_sales)
        for txn in transfer_transactions:
            existing_transfers.append({
                'id': txn.id,
                'product_id': txn.product.id,
                'product_name': txn.product.name,
                'product_item_id': txn.product.item_id,
                'product_barcode': txn.product.barcode or '',
                'is_duty_free': txn.product.is_duty_free,
                'quantity': int(txn.quantity),
                'unit_price': float(txn.unit_price),
                'total_amount': float(txn.total_amount),
                'notes': txn.notes or '',
                'created_at': txn.created_at.strftime('%H:%M')
            })
    else:
        # 🚀 OPTIMIZED: Process completed transfer using prefetched data (like po_supply)
        print(f"🔍 DEBUG: Transfer {transfer.id} is completed, processing {len(transfer_transactions)} transactions")
        
        for txn in transfer_transactions:
            print(f"🔍 DEBUG: Transaction {txn.id}: {txn.product.name}, Qty: {txn.quantity}, Price: {txn.unit_price}")
            completed_transfers.append({
                'product_name': txn.product.name,
                'product_item_id': txn.product.item_id,
                'product_barcode': txn.product.barcode or '',
                'quantity': int(txn.quantity),
                'unit_price': float(txn.unit_price),  # This is now the FIFO cost
                'total_amount': float(txn.total_amount),
                'is_duty_free': txn.product.is_duty_free,
                'notes': txn.notes or '',
                'created_at': txn.created_at.strftime('%H:%M')
            })
    
    # Convert to JSON strings for safe template rendering (like trip_sales/po_supply)
    existing_transfers_json = json.dumps(existing_transfers)
    completed_transfers_json = json.dumps(completed_transfers)
    
    print(f"🔍 DEBUG: completed_transfers_json length: {len(completed_transfers_json)}")
    
    # Build final context (follows trip_sales/po_supply pattern)
    context = {
        'transfer': transfer,
        'existing_transfers_json': existing_transfers_json,
        'completed_transfers_json': completed_transfers_json,
        'can_edit': not transfer.is_completed,  # Key flag like trip_sales/po_supply
    }
    
    # 🚀 CACHE: Store completed transfer data for future requests (like trip_sales/po_supply)
    if transfer.is_completed:
        TransferCacheHelper.cache_completed_transfer_data(transfer_id, context)
        print(f"🚀 CACHED COMPLETED TRANSFER: {transfer_id}")
    
    return render(request, 'frontend/transfer_items.html', context)

@operations_access_required
def transfer_available_products(request):
    """AJAX endpoint to get available products for transfer"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        vessel_id = data.get('vessel_id')
        
        if not vessel_id:
            return JsonResponse({'success': False, 'error': 'Vessel ID required'})
        
        # Get vessel
        vessel = Vessel.objects.get(id=vessel_id, active=True)
        
        # Get products with available inventory on this vessel
        available_lots = InventoryLot.objects.filter(
            vessel=vessel,
            remaining_quantity__gt=0,
            product__active=True
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
            products.append({
                'id': summary['product__id'],
                'name': summary['product__name'],
                'item_id': summary['product__item_id'],
                'barcode': summary['product__barcode'] or '',
                'is_duty_free': summary['product__is_duty_free'],
                'total_quantity': summary['total_quantity'],
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
def transfer_bulk_complete(request):
    """Complete transfer with bulk transaction creation and Transfer record creation"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        
        transfer_id = data.get('transfer_id')
        items = data.get('items', [])
        
        if not transfer_id or not items:
            return JsonResponse({'success': False, 'error': 'Transfer ID and items required'})
        
        # Get transfer record
        transfer = Transfer.objects.get(id=transfer_id)
        from_vessel = transfer.from_vessel
        to_vessel = transfer.to_vessel
        transfer_date = transfer.transfer_date
        notes = transfer.notes or ''
        
        # Validate all items first
        validated_items = []
        
        for item in items:
            product_id = item.get('product_id')
            quantity = item.get('quantity')
            item_notes = item.get('notes', '')
            
            if not product_id or not quantity:
                return JsonResponse({'success': False, 'error': 'Invalid item data'})
            
            # Get product and validate
            try:
                product = Product.objects.get(id=product_id, active=True)
            except Product.DoesNotExist:
                return JsonResponse({'success': False, 'error': f'Product not found: {product_id}'})
            
            # Validate duty-free compatibility
            if product.is_duty_free and not to_vessel.has_duty_free:
                return JsonResponse({
                    'success': False, 
                    'error': f'Cannot transfer duty-free product {product.name} to {to_vessel.name}'
                })
            
            # Check inventory availability
            try:
                # This will validate availability
                get_fifo_cost_for_transfer(from_vessel, product, quantity)
            except Exception as e:
                return JsonResponse({
                    'success': False, 
                    'error': f'Insufficient inventory for {product.name}: {str(e)}'
                })
            
            validated_items.append({
                'product': product,
                'quantity': quantity,
                'notes': item_notes
            })
        
        # All items validated - create transactions atomically
        with transaction.atomic():
            created_transactions = []
            
            for item in validated_items:
                # Create TRANSFER_OUT transaction linked to Transfer record
                transfer_out = Transaction.objects.create(
                    vessel=from_vessel,
                    product=item['product'],
                    transaction_type='TRANSFER_OUT',
                    transaction_date=transfer_date,
                    quantity=item['quantity'],
                    transfer_to_vessel=to_vessel,
                    transfer=transfer,  # Link to Transfer group
                    notes=item['notes'] or f'Transfer to {to_vessel.name}',
                    created_by=request.user
                )
                created_transactions.append(transfer_out)
            
            # Mark transfer as completed
            transfer.is_completed = True
            transfer.save()
            
            # Clear transfer cache
            TransferCacheHelper.clear_recent_transfers_cache()
        
        return JsonResponse({
            'success': True,
            'message': f'Transfer completed successfully! {len(created_transactions)} items transferred from {from_vessel.name} to {to_vessel.name}.',
            'transfer_id': transfer.id,
            'total_items': len(created_transactions)
        })
        
    except Transfer.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Transfer not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Transfer failed: {str(e)}'})
    
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
        from frontend.utils.helpers import get_fifo_cost_for_transfer
        
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
            print(f"FIFO calculation error for vessel {vessel_id}, product {product_id}, quantity {quantity}: {e}")
            
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
        print(f"Endpoint error: {e}")
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
                'message': f'Cart cleared. Transfer {transfer.transfer_number if hasattr(transfer, "transfer_number") else transfer.id} kept (has committed transactions).'
            })
        else:
            # No committed transactions - safe to delete transfer
            transfer_display = transfer.transfer_number if hasattr(transfer, 'transfer_number') else f"#{transfer.id}"
            transfer.delete()
            
            # 🚀 CACHE: Clear transfer cache after deletion
            from frontend.utils.cache_helpers import TransferCacheHelper
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