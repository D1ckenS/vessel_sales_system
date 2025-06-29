from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Prefetch
from django.http import JsonResponse
from datetime import date
from frontend.export_views import get_translated_labels
from frontend.utils.cache_helpers import VesselCacheHelper
from vessels.models import Vessel
from products.models import Product
from transactions.models import InventoryLot, Transaction, PurchaseOrder
from .utils import BilingualMessages
from django.core.exceptions import ValidationError
from datetime import datetime
import json
from decimal import Decimal
import decimal
from django.views.decorators.http import require_http_methods
from django.template.loader import render_to_string
from django.http import HttpResponse
import weasyprint
import io
import logging
from frontend.utils.cache_helpers import ProductCacheHelper, POCacheHelper
from .utils.helpers import (format_currency,
    format_currency_or_none,
    format_percentage,
    format_negative_if_supply,
    get_fifo_cost_for_transfer,
    calculate_transfer_amounts,
    calculate_totals_by_type,
    calculate_product_level_summary,
    translate_numbers_to_arabic,
    get_vessel_name_by_language,
    format_date_for_language,
    format_datetime_for_language,
    safe_float,
    safe_int,
    format_date,
    get_date_range_from_request,
    create_safe_response
    )
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

logger = logging.getLogger(__name__)

@operations_access_required
def supply_entry(request):
    """Step 1: Create new purchase order for supply transactions - OPTIMIZED"""
    
    if request.method == 'GET':
        vessels = VesselCacheHelper.get_active_vessels()
        
        # 🚀 OPTIMIZED: Check cache for recent POs with cost data
        cached_pos = POCacheHelper.get_recent_pos_with_cost()
        
        if cached_pos:
            print(f"🚀 CACHE HIT: Recent POs ({len(cached_pos)} POs)")
            recent_pos = cached_pos
        else:
            print(f"🔍 CACHE MISS: Building recent POs")
            
            # 🚀 OPTIMIZED: Single query with proper prefetching
            recent_pos_query = PurchaseOrder.objects.select_related(
                'vessel', 'created_by'
            ).prefetch_related(
                Prefetch(
                    'supply_transactions',
                    queryset=Transaction.objects.select_related('product')
                )
            ).order_by('-created_at')[:10]
            
            # 🚀 OPTIMIZED: Process POs with prefetched data (no additional queries)
            recent_pos = []
            for po in recent_pos_query:
                # Calculate cost using prefetched supply_transactions
                supply_transactions = po.supply_transactions.all()  # Uses prefetched data
                total_cost = sum(
                    float(txn.quantity) * float(txn.unit_price) 
                    for txn in supply_transactions
                )
                transaction_count = len(supply_transactions)
                
                # Add calculated fields to PO object for template
                po.calculated_total_cost = total_cost
                po.calculated_transaction_count = transaction_count
                
                recent_pos.append(po)
            
            # 🚀 CACHE: Store processed POs for future requests
            POCacheHelper.cache_recent_pos_with_cost(recent_pos)
            print(f"🔥 CACHED: Recent POs ({len(recent_pos)} POs) - 1 hour timeout")
        
        context = {
            'vessels': vessels,
            'recent_pos': recent_pos,
            'today': date.today(),
        }
        
        return render(request, 'frontend/supply_entry.html', context)
    
    elif request.method == 'POST':
        try:
            # Get form data
            vessel_id = request.POST.get('vessel')
            po_number = request.POST.get('po_number', '').strip()
            po_date = request.POST.get('po_date')
            notes = request.POST.get('notes', '').strip()
            
            # Validate required fields
            if not all([vessel_id, po_number, po_date]):
                BilingualMessages.error(request, 'required_fields_missing')
                return redirect('frontend:supply_entry')
            
            # Get vessel
            vessel = Vessel.objects.get(id=vessel_id, active=True)
            
            # Validate PO number uniqueness
            if PurchaseOrder.objects.filter(po_number=po_number).exists():
                BilingualMessages.error(request, 'po_number_exists', po_number=po_number)
                return redirect('frontend:supply_entry')
            
            po_date_obj = datetime.strptime(po_date, '%Y-%m-%d').date()
            
            # Create purchase order
            po = PurchaseOrder.objects.create(
                po_number=po_number,
                vessel=vessel,
                po_date=po_date_obj,
                notes=notes,
                created_by=request.user
            )
            
            # 🚀 CACHE: Clear recent POs cache after creation
            POCacheHelper.clear_cache_after_po_create()
            
            BilingualMessages.success(request, 'po_created_success', po_number=po_number)
            return redirect('frontend:po_supply', po_id=po.id)
            
        except Vessel.DoesNotExist:
            BilingualMessages.error(request, 'invalid_vessel')
            return redirect('frontend:supply_entry')
        except (ValueError, ValidationError) as e:
            BilingualMessages.error(request, 'invalid_data', error=str(e))
            return redirect('frontend:supply_entry')
        except Exception as e:
            BilingualMessages.error(request, 'error_creating_po', error=str(e))
            return redirect('frontend:supply_entry')

@operations_access_required
def po_supply(request, po_id):
    """Step 2: Multi-item supply entry for a specific purchase order (Shopping Cart Approach) - OPTIMIZED"""
    
    # 🚀 OPTIMIZED: Check cache first for completed POs (no DB query needed)
    cached_data = POCacheHelper.get_completed_po_data(po_id)
    if cached_data:
        print(f"🚀 CACHE HIT: Completed PO {po_id}")
        return render(request, 'frontend/po_supply.html', cached_data)
    
    try:
        # 🚀 SUPER OPTIMIZED: Single query with everything
        po = PurchaseOrder.objects.select_related(
            'vessel', 'created_by'
        ).prefetch_related(
            Prefetch(
                'supply_transactions',
                queryset=Transaction.objects.select_related(
                    'product', 'product__category'
                ).order_by('created_at')
            )
        ).get(id=po_id)
        
        # 🚀 FORCE: Get all transactions immediately to prevent additional queries
        supply_transactions = list(po.supply_transactions.all())
        
    except PurchaseOrder.DoesNotExist:
        BilingualMessages.error(request, 'Purchase Order not found.')
        return redirect('frontend:supply_entry')
    
    # 🚀 OPTIMIZED: Use prefetched data for all calculations (no additional queries)
    existing_supplies = []
    completed_supplies = []
    
    if not po.is_completed:
        # 🚀 OPTIMIZED: Process incomplete PO using prefetched data
        for supply in supply_transactions:
            existing_supplies.append({
                'id': supply.id,
                'product_id': supply.product.id,
                'product_name': supply.product.name,
                'product_item_id': supply.product.item_id,
                'product_barcode': supply.product.barcode or '',
                'is_duty_free': supply.product.is_duty_free,
                'quantity': int(supply.quantity),
                'unit_price': float(supply.unit_price),
                'total_amount': float(supply.total_amount),
                'notes': supply.notes or '',
                'created_at': supply.created_at.strftime('%H:%M')
            })
    else:
        # 🚀 OPTIMIZED: Process completed PO using prefetched data
        print(f"🔍 DEBUG: PO {po.po_number} is completed, processing {len(supply_transactions)} transactions")
        
        for supply in supply_transactions:
            print(f"🔍 DEBUG: Transaction {supply.id}: {supply.product.name}, Qty: {supply.quantity}, Price: {supply.unit_price}")
            completed_supplies.append({
                'product_name': supply.product.name,
                'product_item_id': supply.product.item_id,
                'product_barcode': supply.product.barcode or '',
                'quantity': int(supply.quantity),
                'unit_price': float(supply.unit_price),
                'total_amount': float(supply.total_amount),
                'is_duty_free': supply.product.is_duty_free,
                'notes': supply.notes or '',
                'created_at': supply.created_at.strftime('%H:%M')
            })
    
    # Convert to JSON strings for safe template rendering
    existing_supplies_json = json.dumps(existing_supplies)
    completed_supplies_json = json.dumps(completed_supplies)
    
    print(f"🔍 DEBUG: completed_supplies_json length: {len(completed_supplies_json)}")
    
    # Build final context
    context = {
        'po': po,
        'existing_supplies_json': existing_supplies_json,
        'completed_supplies_json': completed_supplies_json,
        'can_edit': not po.is_completed,
    }
    
    # 🚀 CACHE: Store completed PO data for future requests
    if po.is_completed:
        POCacheHelper.cache_completed_po_data(po_id, context)
        print(f"🚀 CACHED COMPLETED PO: {po_id}")
    
    return render(request, 'frontend/po_supply.html', context)


@operations_access_required
def po_complete(request, po_id):
    """Complete a purchase order and mark it as finished"""
    
    if request.method == 'POST':
        try:
            po = PurchaseOrder.objects.get(id=po_id)
            po.is_completed = True
            po.save()
            
            total_cost = po.total_cost
            transaction_count = po.transaction_count
            
            BilingualMessages.success(request, 
                f'Purchase Order {po.po_number} completed! '
                f'{transaction_count} items received for {total_cost:.3f} JOD total cost.'
            )
            
            return redirect('frontend:supply_entry')
            
        except PurchaseOrder.DoesNotExist:
            BilingualMessages.error(request, 'Purchase Order not found.')
            return redirect('frontend:supply_entry')

@operations_access_required
def supply_search_products(request):
    """AJAX endpoint to search for products for supply entry - optimized"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        search_term = data.get('search', '').strip()
        
        if not search_term:
            return JsonResponse({'success': False, 'error': 'Search term required'})
        
        # OPTIMIZED: Single query with select_related for category
        products = Product.objects.filter(
            active=True
        ).filter(
            Q(name__icontains=search_term) |
            Q(item_id__icontains=search_term) |
            Q(barcode__icontains=search_term)
        ).select_related('category').order_by('name')[:20]  # Limit results for performance
        
        # OPTIMIZED: Process all products in single loop
        products_data = [
            {
                'id': product.id,
                'name': product.name,
                'item_id': product.item_id,
                'barcode': product.barcode or '',
                'category': product.category.name,
                'purchase_price': float(product.purchase_price),
                'selling_price': float(product.selling_price),
                'is_duty_free': product.is_duty_free,
            }
            for product in products
        ]
        
        return JsonResponse({
            'success': True,
            'products': products_data
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
@operations_access_required
def po_bulk_complete(request):
    """Complete purchase order with proper inventory updates - CACHE AWARE"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        
        po_id = data.get('po_id')
        items = data.get('items', [])
        
        if not po_id or not items:
            return JsonResponse({'success': False, 'error': 'PO ID and items required'})
        
        # Get PO with vessel
        try:
            po = PurchaseOrder.objects.select_related('vessel').get(id=po_id)
        except PurchaseOrder.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Purchase order not found'})
        
        if po.is_completed:
            return JsonResponse({'success': False, 'error': 'Purchase order is already completed'})
        
        # Bulk fetch all products
        product_ids = [item.get('product_id') for item in items if item.get('product_id')]
        products_dict = {p.id: p for p in Product.objects.filter(id__in=product_ids, active=True)}
        
        # Validate all items
        validated_items = []
        total_cost = 0
        
        for item in items:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 0)
            unit_price = item.get('unit_price', 0)
            notes = item.get('notes', '').strip()
            
            boxes = item.get('boxes')
            items_per_box = item.get('items_per_box')
            
            # Validate breakdown if provided
            if boxes is not None and items_per_box is not None:
                boxes = int(boxes)
                items_per_box = int(items_per_box)
                calculated_quantity = boxes * items_per_box
                
                # Ensure calculated quantity matches the provided quantity
                if abs(calculated_quantity - quantity) > 0.001:
                    return JsonResponse({
                        'success': False, 
                        'error': f'Quantity mismatch: {boxes} boxes × {items_per_box} items = {calculated_quantity}, but quantity is {quantity}'
                    })
            
            if not product_id or quantity <= 0 or unit_price <= 0:
                continue
                
            product = products_dict.get(product_id)
            if not product:
                continue
                
            validated_items.append({
                'product': product,
                'quantity': Decimal(str(quantity)),
                'unit_price': Decimal(str(unit_price)),
                'notes': notes
            })
            
            total_cost += quantity * unit_price
        
        if not validated_items:
            return JsonResponse({'success': False, 'error': 'No valid items to process'})
        
        created_transactions = []
        
        with transaction.atomic():
            # Clear existing transactions for this PO (if any)
            Transaction.objects.filter(purchase_order=po, transaction_type='SUPPLY').delete()
            
            # Process each supply item
            for item_data in validated_items:
                product = item_data['product']
                quantity = item_data['quantity']
                unit_price = item_data['unit_price']
                notes = item_data['notes']
                
                # Create supply transaction
                supply_transaction = Transaction.objects.create(
                    vessel=po.vessel,
                    product=product,
                    transaction_type='SUPPLY',
                    quantity=quantity,
                    unit_price=unit_price,
                    transaction_date=po.po_date,
                    purchase_order=po,
                    notes=notes,
                    created_by=request.user,
                    boxes=boxes if boxes is not None else None,
                    items_per_box=items_per_box if items_per_box is not None else None
                )
                
                created_transactions.append(supply_transaction)
            
            # Mark PO as completed
            po.is_completed = True
            po.save()
            
            # 🚀 CACHE: Clear PO cache after completion
            POCacheHelper.clear_cache_after_po_complete(po_id)
        
        # Build success response
        response_data = {
            'success': True,
            'message': f'PO {po.po_number} completed successfully with {len(created_transactions)} items!',
            'po_data': {
                'po_number': po.po_number,
                'items_count': len(created_transactions),
                'total_cost': float(total_cost),
                'vessel': po.vessel.name
            }
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error completing PO: {str(e)}'})


@operations_access_required  
def po_cancel(request):
    """Cancel PO and delete it from database (if no items committed) - CACHE AWARE"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        po_id = data.get('po_id')
        
        if not po_id:
            return JsonResponse({'success': False, 'error': 'PO ID required'})
        
        # Get PO
        po = PurchaseOrder.objects.get(id=po_id)
        
        if po.is_completed:
            return JsonResponse({'success': False, 'error': 'Cannot cancel completed PO'})
        
        # Check if PO has any committed transactions
        existing_transactions = Transaction.objects.filter(purchase_order=po).count()
        
        if existing_transactions > 0:
            # PO has committed transactions - just clear cart but keep PO
            return JsonResponse({
                'success': True,
                'action': 'clear_cart',
                'message': f'Cart cleared. PO {po.po_number} kept (has committed transactions).'
            })
        else:
            # No committed transactions - safe to delete PO
            po_number = po.po_number
            po.delete()
            
            # 🚀 CACHE: Clear PO cache after deletion
            POCacheHelper.clear_cache_after_po_delete(po_id)
            
            return JsonResponse({
                'success': True,
                'action': 'delete_po',
                'message': f'PO {po_number} cancelled and removed.',
                'redirect_url': '/supply/'  # Redirect back to supply entry
            })
        
    except PurchaseOrder.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'PO not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error cancelling PO: {str(e)}'})

@operations_access_required
def supply_product_catalog(request):
    """AJAX endpoint to get products filtered by vessel's duty-free capability"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        vessel_id = data.get('vessel_id')
        
        # Get all active products
        products = Product.objects.filter(active=True).select_related('category').order_by('item_id')
        
        # If vessel_id provided, filter by duty-free capability
        if vessel_id:
            try:
                vessel = Vessel.objects.get(id=vessel_id, active=True)
                # If vessel doesn't support duty-free, exclude duty-free products
                if not vessel.has_duty_free:
                    products = products.filter(is_duty_free=False)
            except Vessel.DoesNotExist:
                pass  # If vessel not found, show all products
        
        products_data = []
        for product in products:
            products_data.append({
                'id': product.id,
                'name': product.name,
                'item_id': product.item_id,
                'barcode': product.barcode or '',
                'category': product.category.name,
                'purchase_price': float(product.purchase_price),
                'selling_price': float(product.selling_price),
                'is_duty_free': product.is_duty_free,
            })
        
        return JsonResponse({
            'success': True,
            'products': products_data
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
@operations_access_required
def supply_execute(request):
    """AJAX endpoint to execute supply transaction"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        # Get form data
        vessel_id = request.POST.get('vessel')
        product_id = request.POST.get('product_id')
        quantity = request.POST.get('quantity')
        purchase_cost = request.POST.get('purchase_cost')
        supply_date_str = request.POST.get('supply_date')
        supplier = request.POST.get('supplier', '').strip()
        reference = request.POST.get('reference', '').strip()
        notes = request.POST.get('notes', '').strip()
        
        # Validate required fields
        if not all([vessel_id, product_id, quantity, purchase_cost, supply_date_str]):
            return JsonResponse({'success': False, 'error': 'Missing required fields'})
        
        # Get objects
        vessel = Vessel.objects.get(id=vessel_id, active=True)
        product = Product.objects.get(id=product_id, active=True)
        
        # Validate duty-free compatibility
        if product.is_duty_free and not vessel.has_duty_free:
            return JsonResponse({
                'success': False, 
                'error': f'Cannot add duty-free product to {vessel.name} (vessel does not support duty-free items)'
            })
        
        # Parse values
        quantity_val = int(quantity)
        cost_val = Decimal(purchase_cost)
        
        if quantity_val <= 0 or cost_val <= 0:
            return JsonResponse({'success': False, 'error': 'Quantity and cost must be positive values'})
        
        # Parse supply date
        supply_date = datetime.strptime(supply_date_str, '%Y-%m-%d').date()
        
        # Build notes
        supply_notes = []
        if supplier:
            supply_notes.append(f'Supplier: {supplier}')
        if reference:
            supply_notes.append(f'Reference: {reference}')
        if notes:
            supply_notes.append(f'Notes: {notes}')
        
        final_notes = '; '.join(supply_notes) if supply_notes else f'Supply for {vessel.name}'
        
        # Create SUPPLY transaction (this will automatically create InventoryLot via your existing system)
        supply_transaction = Transaction.objects.create(
            vessel=vessel,
            product=product,
            transaction_type='SUPPLY',
            transaction_date=supply_date,
            quantity=quantity_val,
            unit_price=cost_val,
            notes=final_notes,
            created_by=request.user
        )
        
        # Your existing _handle_supply() method will create the InventoryLot automatically
        return JsonResponse({
            'success': True,
            'message': f'Supply recorded: {quantity_val} units of {product.name} added to {vessel.name} at {cost_val} JOD per unit',
            'transaction_id': supply_transaction.id
        })
        
    except (Vessel.DoesNotExist, Product.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Vessel or product not found'})
    except (ValueError, decimal.InvalidOperation):
        return JsonResponse({'success': False, 'error': 'Invalid quantity or cost value'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Supply failed: {str(e)}'})
    
@operations_access_required
@require_http_methods(["POST"])
def export_po_cart(request):
    """Export PO cart data with box breakdown for verification - AUTO-EXPORT during completion"""
    try:
        data = json.loads(request.body)
    
        po_id = data.get('po_id')
        cart_items = data.get('cart_items', [])
        language = data.get('language', 'en')
        
        if not po_id or not cart_items:
            return JsonResponse({'success': False, 'error': 'PO ID and cart items required'})
        
        # Get translated labels using existing system
        labels = get_translated_labels(request, data)
        language = labels['language']
        
        # Get PO for metadata
        try:
            po = PurchaseOrder.objects.select_related('vessel').get(id=po_id)
        except PurchaseOrder.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Purchase order not found'})
        
        # Process cart items with box breakdown
        total_cost = 0
        total_quantity = 0
        verification_alerts = []
        enhanced_cart_data = []
        
        # Get product defaults for comparison (single query)
        product_ids = [item.get('product_id') for item in cart_items if item.get('product_id')]
        products_dict = {p.id: p for p in Product.objects.filter(id__in=product_ids, active=True)}
        
        for item in cart_items:
            product_id = item.get('product_id')
            product = products_dict.get(product_id)
            
            if not product:
                continue
                
            # Extract cart data
            num_boxes = item.get('num_boxes', 0)
            items_per_box = item.get('items_per_box', 0)
            quantity = item.get('quantity', 0)
            unit_price = item.get('unit_price', 0)
            total_amount = item.get('total_amount', 0)
            
            total_cost += total_amount
            total_quantity += quantity
            
            # Create enhanced quantity breakdown display
            if num_boxes and items_per_box:
                quantity_breakdown = (
                    f"{translate_numbers_to_arabic(str(num_boxes), language)} {labels['boxes']} × "
                    f"{translate_numbers_to_arabic(str(items_per_box), language)} = "
                    f"{translate_numbers_to_arabic(str(quantity), language)} {labels['units_total']}"
                )

                calculation_verification = (
                    f"{translate_numbers_to_arabic(str(num_boxes), language)} × "
                    f"{translate_numbers_to_arabic(str(items_per_box), language)} × "
                    f"{translate_numbers_to_arabic(f'{unit_price:.3f}', language)} = "
                    f"{translate_numbers_to_arabic(f'{total_amount:.3f}', language)} {labels['jod']}"
                )
            else:
                quantity_breakdown = f"{translate_numbers_to_arabic(str(quantity), language)} {labels['units_total']}"
                calculation_verification = (
                    f"{translate_numbers_to_arabic(str(quantity), language)} × "
                    f"{translate_numbers_to_arabic(f'{unit_price:.3f}', language)} = "
                    f"{translate_numbers_to_arabic(f'{total_amount:.3f}', language)} {labels['jod']}"
                )
            
            # Smart cost verification
            product_default_cost = float(product.purchase_price) if product.purchase_price else 0
            cost_status = labels['normal_status']
            
            if product_default_cost > 0:
                variance_pct = ((unit_price - product_default_cost) / product_default_cost) * 100
                
                if variance_pct > 20:
                    cost_status = f"{labels['high_cost_status']} (+{variance_pct:.1f}%)"
                    verification_alerts.append(f"{product.name}: Unit cost {unit_price:.3f} {labels['jod']} is {variance_pct:.1f}% above standard ({product_default_cost:.3f} {labels['jod']})")
                elif variance_pct < -20:
                    cost_status = f"{labels['low_cost_status']} ({variance_pct:.1f}%)"
                    verification_alerts.append(f"{product.name}: Unit cost {unit_price:.3f} {labels['jod']} is {abs(variance_pct):.1f}% below standard ({product_default_cost:.3f} {labels['jod']})")
            
            # Enhanced cart item for export
            enhanced_item = {
                'product_name': product.name,
                'product_item_id': translate_numbers_to_arabic(product.item_id, language),
                'quantity_breakdown': quantity_breakdown,
                'unit_cost_display': f"{translate_numbers_to_arabic(f'{unit_price:.3f}', language)} {labels['jod']} {labels['per_unit']}",
                'total_amount_display': f"{translate_numbers_to_arabic(f'{total_amount:.3f}', language)} {labels['jod']}",
                'cost_status': cost_status,
                'calculation_verification': calculation_verification,
                'notes': item.get('notes', ''),
                'is_duty_free': product.is_duty_free
            }
            enhanced_cart_data.append(enhanced_item)
        
        # Generate verification report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"po_cart_verification_{po.po_number}_{timestamp}"
        
        # Enhanced metadata with proper status
        status_display = f"{labels['completed_status']} ({labels['auto_generated']})"
        
        # Get vessel name in appropriate language
        vessel_name = get_vessel_name_by_language(po.vessel, language)
        
        local_dt = timezone.localtime(timezone.now()).replace(tzinfo=None)
        
        metadata = {
            labels['export_date']: format_datetime_for_language(local_dt, language),
            labels['po_number']: translate_numbers_to_arabic(str(po.po_number), language),
            labels['vessel']: vessel_name,
            labels['po_date']: format_datetime_for_language(local_dt, language),
            labels['status']: status_display,
            labels['total_cost']: f"{translate_numbers_to_arabic(f'{total_cost:.3f}',language)} {labels['jod']}",
            labels['total_items']: f"{translate_numbers_to_arabic(str(len(enhanced_cart_data)), language)} {labels['products']}",
            labels['total_quantity']: f"{translate_numbers_to_arabic(f'{total_quantity:.0f}', language)} {labels['units']}",
            labels['average_cost_per_item_jod']: f"{translate_numbers_to_arabic(f'{(total_cost / total_quantity) if total_quantity > 0 else 0:.3f}', language)} {labels['jod']}",
            labels['verification_alerts']: f"{len(verification_alerts)} {labels['items_flagged']}" if verification_alerts else labels['no_alerts_message'],
            labels['generated_by']: request.user.username,
            labels['export_type']: labels['auto_generated']
        }
        
        # Table headers for verification report
        headers = [
            labels['product'],
            labels['product_id'], 
            labels['quantity_breakdown'],
            labels['unit_cost_calculated'],
            labels['invoice_amount'],
            labels['verification_status'],
            labels['notes']
        ]
        
        # Prepare table data
        table_data = []
        for item in enhanced_cart_data:
            row = [
                item['product_name'],
                item['product_item_id'],
                item['quantity_breakdown'],
                item['unit_cost_display'],
                item['total_amount_display'],
                item['cost_status'],
                item['notes'] or '-'
            ]
            table_data.append(row)
        
        # Summary data
        summary_data = {
            labels['total_products']: translate_numbers_to_arabic(str(len(enhanced_cart_data)), language),
            labels['total_quantity']: f"{translate_numbers_to_arabic(f'{total_quantity:.0f}', language)} {labels['units']}",
            labels['total_cost']: f"{translate_numbers_to_arabic(f'{total_cost:.3f}',language)} {labels['jod']}",
            labels['verification_status']: (
                f"{translate_numbers_to_arabic(str(len(verification_alerts)), language)} {labels['alerts']}"
                if verification_alerts
                else labels['all_items_normal']
            )
        }
        
        # Verification calculations for transparency
        verification_calculations = [
            {
                'product': item['product_name'],
                'calculation': item['calculation_verification'].split('=')[0].strip(),
                'result': item['calculation_verification'].split('=')[1].strip()
            }
            for item in enhanced_cart_data
        ]
        po_number_translated = translate_numbers_to_arabic(str(po.po_number), language)
        
        # Generate title
        if language == 'ar':
            report_title = f"{labels['po_report_title']} {po_number_translated} ({labels['auto_generated']})"
        else:
            report_title = f"{labels['po_report_title']} {po.po_number} ({labels['auto_generated']})"
        
        # Generate PDF using verification template
        try:
            context = {
                'title': report_title,
                'labels': labels,  # Pass all labels to template
                'metadata': metadata,
                'tables': [
                    {
                        'title': f"{report_title} - {labels['quantity_breakdown']} {labels['verification_status']}",
                        'id': 'po_cart_verification_table',
                        'headers': headers,
                        'rows': table_data
                    }
                ],
                'verification_calculations': verification_calculations,
                'verification_alerts': verification_alerts if verification_alerts else [labels['no_alerts_message']],
                'summary_data': summary_data,
                'orientation': 'portrait',
                'language': language,
                'generation_date': format_date_for_language(local_dt, language),
                'has_logo': False,
                'is_cart_export': True,
                'total_cost_for_checklist': translate_numbers_to_arabic(f'{total_cost:.3f}', language),
                'generated_on_text': labels['generated_on'],
                'report_info_text': labels['report_information'],
                'summary_text': labels['summary'],
                'verification_text': labels['verification_status'],
                'company_logo_text': labels['company_logo']
            }
            
            # Use the updated verification template (will be updated next)
            template_name = 'frontend/exports/po_verification_report.html'
            html_string = render_to_string(template_name, context)
            
            html = weasyprint.HTML(string=html_string)
            
            buffer = io.BytesIO()
            html.write_pdf(target=buffer)
            buffer.seek(0)
            
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename_base}.pdf"'
            response['Content-Length'] = len(buffer.getvalue())
            response.write(buffer.getvalue())
            
            return response
            
        except Exception as e:
            logger.error(f"PDF cart export error: {e}")
            return JsonResponse({'success': False, 'error': f'PDF export failed: {str(e)}'})
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Cart export error: {e}")
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})