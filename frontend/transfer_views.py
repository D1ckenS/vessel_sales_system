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
        
        # 🚀 OPTIMIZED: Check cache for recent transfers with cost data (like supply_entry)
        cached_transfers = TransferCacheHelper.get_recent_transfers_with_cost()
        
        if cached_transfers:
            print(f"🚀 CACHE HIT: Recent transfers ({len(cached_transfers)} transfers)")
            recent_transfers = cached_transfers
        else:
            print(f"🔍 CACHE MISS: Building recent transfers")
            
            # 🚀 OPTIMIZED: Single query with proper prefetching (like supply_entry)
            recent_transfers_query = Transfer.objects.select_related(
                'from_vessel', 'to_vessel', 'created_by'
            ).prefetch_related(
                Prefetch(
                    'transactions',
                    queryset=Transaction.objects.select_related('product').filter(transaction_type='TRANSFER_OUT')
                )
            ).order_by('-created_at')[:10]
            
            # 🚀 OPTIMIZED: Process transfers with prefetched data (no additional queries)
            recent_transfers = []
            for transfer in recent_transfers_query:
                # Calculate cost using prefetched TRANSFER_OUT transactions
                transfer_transactions = transfer.transactions.all()  # Uses prefetched data
                total_cost = sum(
                    float(txn.quantity) * float(txn.unit_price) 
                    for txn in transfer_transactions
                )
                transaction_count = len(transfer_transactions)
                
                # Add calculated fields to Transfer object for template
                transfer.calculated_total_cost = total_cost
                transfer.calculated_transaction_count = transaction_count
                
                recent_transfers.append(transfer)
            
            # 🚀 CACHE: Store processed transfers for future requests (like supply_entry)
            TransferCacheHelper.cache_recent_transfers_with_cost(recent_transfers)
            print(f"🔥 CACHED: Recent transfers ({len(recent_transfers)} transfers) - 1 hour timeout")
        
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
            
            TransferCacheHelper.clear_all_transfer_cache()
            
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
                ).order_by('created_at')
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
    """
    🚀 OPTIMIZED: Complete transfer with batch processing (like trip/PO patterns)
    
    Performance improvements:
    - Batch FIFO calculations
    - Bulk transaction creation  
    - Batch inventory operations
    - Targeted cache clearing
    """
    import time
    from datetime import datetime
    from django.db import transaction
    from decimal import Decimal
    from products.models import Product
    from transactions.models import Transfer, Transaction
    
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
        print(f"🚀 BATCH PROCESSING: Starting transfer completion for {len(items)} items")
        
        with transaction.atomic():
            # 🚀 STEP 1: Clear existing transactions efficiently (single bulk operation)
            existing_transactions = Transaction.objects.filter(
                transfer=transfer,
                transaction_type__in=['TRANSFER_OUT', 'TRANSFER_IN']
            )
            
            if existing_transactions.exists():
                print(f"🔄 CLEARING: {existing_transactions.count()} existing transactions in bulk")
                # Use bulk_delete to avoid individual delete() overhead
                existing_transactions._raw_delete(existing_transactions.db)
                
            # 🚀 STEP 2: Batch product fetching and validation
            product_ids = [item.get('product_id') for item in items if item.get('product_id')]
            products_dict = {
                p.id: p for p in Product.objects.filter(id__in=product_ids, active=True)
            }
            
            # 🚀 STEP 3: Batch FIFO calculations for all items at once
            fifo_calculations = {}
            total_calculations_time = 0
            
            print(f"📊 BATCH FIFO: Calculating costs for {len(items)} items")
            fifo_start_time = time.time()
            
            for item in items:
                product_id = item.get('product_id')
                quantity = item.get('quantity', 0)
                
                if product_id not in products_dict:
                    continue
                    
                product = products_dict[product_id]
                
                try:
                    # Calculate FIFO cost (this is the expensive operation)
                    from frontend.utils.helpers import get_fifo_cost_for_transfer
                    fifo_cost_per_unit = get_fifo_cost_for_transfer(from_vessel, product, quantity)
                    
                    fifo_calculations[product_id] = {
                        'product': product,
                        'quantity': quantity,
                        'unit_price': Decimal(str(fifo_cost_per_unit)) if fifo_cost_per_unit else Decimal('0.001'),
                        'notes': item.get('notes', ''),
                        'total_cost': (Decimal(str(fifo_cost_per_unit)) if fifo_cost_per_unit else Decimal('0.001')) * Decimal(str(quantity))
                    }
                    
                except Exception as e:
                    print(f"⚠️ FIFO calculation failed for {product.name}: {e}")
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
            print(f"⚡ FIFO BATCH COMPLETED: {total_calculations_time:.2f} seconds for {len(items)} items")
            
            # 🚀 STEP 4: Bulk create TRANSFER_OUT transactions (disable auto-creation)
            transfer_out_transactions = []
            transfer_in_transactions = []
            
            print(f"📦 BATCH CREATION: Creating TRANSFER_OUT transactions")
            
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
            print(f"⚡ BULK CREATE: Creating {len(transfer_out_transactions)} TRANSFER_OUT transactions")
            created_out_transactions = Transaction.objects.bulk_create(transfer_out_transactions)
            
            print(f"⚡ BULK CREATE: Creating {len(transfer_in_transactions)} TRANSFER_IN transactions")  
            created_in_transactions = Transaction.objects.bulk_create(transfer_in_transactions)
            
            # 🚀 STEP 6: Batch inventory operations
            print(f"📊 BATCH INVENTORY: Processing inventory for {len(fifo_calculations)} products")
            
            # Handle TRANSFER_OUT inventory consumption in batch
            _batch_consume_inventory_for_transfer_out(
                fifo_calculations, from_vessel, created_out_transactions
            )
            
            # Handle TRANSFER_IN inventory creation in batch  
            _batch_create_inventory_for_transfer_in(
                fifo_calculations, to_vessel, created_in_transactions
            )
            
            # 🚀 STEP 7: Link transactions efficiently
            print(f"🔗 BATCH LINKING: Linking {len(created_out_transactions)} transaction pairs")
            
            # Link TRANSFER_OUT with TRANSFER_IN transactions
            for i, (out_txn, in_txn) in enumerate(zip(created_out_transactions, created_in_transactions)):
                out_txn.related_transfer_id = in_txn.id
                in_txn.related_transfer_id = out_txn.id
            
            # Bulk update the links
            Transaction.objects.bulk_update(created_out_transactions, ['related_transfer_id'])
            Transaction.objects.bulk_update(created_in_transactions, ['related_transfer_id'])
            
            # 🚀 STEP 8: Mark transfer as completed
            transfer.is_completed = True
            transfer.save(update_fields=['is_completed'])
            
            print(f"✅ TRANSFER COMPLETED: {len(created_out_transactions)} items transferred")
            
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
        print(f"❌ BATCH TRANSFER ERROR: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Transfer failed: {str(e)}'})


def _batch_consume_inventory_for_transfer_out(fifo_calculations, from_vessel, transfer_out_transactions):
    """
    🚀 BATCH OPERATION: Consume inventory for all TRANSFER_OUT transactions efficiently
    """
    from transactions.models import InventoryLot
    
    print(f"📊 BATCH CONSUME: Processing inventory consumption for {len(fifo_calculations)} products")
    
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
                
                print(f"📦 CONSUMED: {consume_from_lot} units of {product.name} from lot {lot.id}")
                
        except Exception as e:
            print(f"❌ CONSUME ERROR for {product.name}: {e}")
            continue


def _batch_create_inventory_for_transfer_in(fifo_calculations, to_vessel, transfer_in_transactions):
    """
    🚀 BATCH OPERATION: Create inventory lots for all TRANSFER_IN transactions efficiently
    """
    from datetime import datetime
    from transactions.models import InventoryLot
    
    print(f"📦 BATCH CREATE: Creating inventory lots for {len(fifo_calculations)} products")
    
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
        print(f"✅ CREATED: {len(inventory_lots_to_create)} inventory lots for {to_vessel.name}")


def _clear_transfer_cache_targeted(transfer_id, from_vessel_id, to_vessel_id):
    """
    🚀 TARGETED CACHE CLEARING: Clear only relevant cache, not nuclear option
    """
    from frontend.utils.cache_helpers import TransferCacheHelper, VesselCacheHelper, ProductCacheHelper
    
    print(f"🔥 TARGETED CACHE: Clearing cache for transfer {transfer_id}")
    
    try:
        # Clear transfer-specific cache
        TransferCacheHelper.clear_cache_after_transfer_update(transfer_id)
        
        # Clear vessel-specific cache (both vessels affected)
        VesselCacheHelper.clear_cache(from_vessel_id)
        VesselCacheHelper.clear_cache(to_vessel_id)
        
        # Clear product cache (inventory changed)
        ProductCacheHelper.clear_cache_after_product_update()
        
        print(f"✅ TARGETED CACHE CLEARED: Transfer {transfer_id}, Vessels {from_vessel_id}/{to_vessel_id}")
        
    except Exception as e:
        print(f"⚠️ CACHE CLEAR WARNING: {e}")
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