from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
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
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

logger = logging.getLogger(__name__)

@operations_access_required
def supply_entry(request):
    """Step 1: Create new purchase order for supply transactions"""
    
    if request.method == 'GET':
        vessels = VesselCacheHelper.get_active_vessels()
        recent_pos = PurchaseOrder.objects.select_related('vessel', 'created_by').prefetch_related(
            'supply_transactions'
        ).order_by('-created_at')[:10]
        
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
    """Step 2: Multi-item supply entry for a specific purchase order (Shopping Cart Approach)"""
    
    try:
        po = PurchaseOrder.objects.select_related('vessel').get(id=po_id)
    except PurchaseOrder.DoesNotExist:
        BilingualMessages.error(request, 'Purchase Order not found.')
        return redirect('frontend:supply_entry')
    
    # Get existing supplies for this PO (to populate shopping cart if PO was previously started)
    existing_supplies = []
    if not po.is_completed:
        # Only load for incomplete POs - completed POs should be read-only
        po_transactions = Transaction.objects.filter(
            purchase_order=po,
            transaction_type='SUPPLY'
        ).select_related('product').order_by('created_at')
        
        # Convert to format expected by frontend shopping cart
        for supply in po_transactions:
            existing_supplies.append({
                'id': supply.id,  # Include for edit/delete functionality
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
    
    # If PO is completed, get read-only supply data for display
    completed_supplies = []
    if po.is_completed:
        print(f"🔍 DEBUG: PO {po.po_number} is completed, fetching supply transactions...")
        
        po_transactions = Transaction.objects.filter(
            purchase_order=po,
            transaction_type='SUPPLY'
        ).select_related('product').order_by('created_at')
        
        print(f"🔍 DEBUG: Found {po_transactions.count()} supply transactions")
        
        for supply in po_transactions:
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
        
        print(f"🔍 DEBUG: Completed supplies array: {completed_supplies}")
        
        # Check InventoryLots
        inventory_lots = InventoryLot.objects.filter(
            vessel=po.vessel,
            product__in=[supply.product for supply in po_transactions]
        )
        print(f"🔍 DEBUG: Found {inventory_lots.count()} inventory lots for this vessel")
        for lot in inventory_lots:
            print(f"🔍 DEBUG: Lot {lot.id}: {lot.product.name}, Remaining: {lot.remaining_quantity}, Original: {lot.original_quantity}")
    
    # Convert to JSON strings for safe template rendering
    existing_supplies_json = json.dumps(existing_supplies)
    completed_supplies_json = json.dumps(completed_supplies)
    
    print(f"🔍 DEBUG: completed_supplies_json length: {len(completed_supplies_json)}")
    print(f"🔍 DEBUG: JSON content: {completed_supplies_json[:200]}...")  # First 200 chars
    
    context = {
        'po': po,
        'existing_supplies_json': existing_supplies_json,  # JSON string
        'completed_supplies_json': completed_supplies_json,  # JSON string
        'can_edit': not po.is_completed,  # Frontend can use this to show/hide edit features
    }
    
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
    """Complete purchase order with proper inventory updates via individual transaction saves"""
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
            quantity = item.get('quantity')
            purchase_cost = item.get('purchase_cost')
            notes = item.get('notes', '')
            
            if not product_id or not quantity or not purchase_cost:
                return JsonResponse({'success': False, 'error': 'Invalid item data'})
            
            product = products_dict.get(product_id)
            if not product:
                return JsonResponse({'success': False, 'error': f'Product not found: {product_id}'})
            
            # Validate duty-free compatibility
            if product.is_duty_free and not po.vessel.has_duty_free:
                return JsonResponse({
                    'success': False, 
                    'error': f'Cannot add duty-free product {product.name} to {po.vessel.name}'
                })
            
            try:
                quantity_val = int(quantity)
                cost_val = Decimal(str(purchase_cost))
                if quantity_val <= 0 or cost_val <= 0:
                    raise ValueError("Values must be positive")
            except (ValueError, decimal.InvalidOperation):
                return JsonResponse({'success': False, 'error': f'Invalid quantity or cost for {product.name}'})
            
            validated_items.append({
                'product': product,
                'quantity': quantity_val,
                'unit_price': cost_val,
                'notes': notes
            })
            
            total_cost += quantity_val * cost_val
        
        # 🔥 CRITICAL FIX: Create transactions individually to trigger save() and _handle_supply()
        with transaction.atomic():
            print(f"🔍 Creating {len(validated_items)} supply transactions...")
            
            for item in validated_items:
                # This will call save() which calls _handle_supply() and creates InventoryLot
                supply_transaction = Transaction.objects.create(
                    vessel=po.vessel,
                    product=item['product'],
                    transaction_type='SUPPLY',
                    transaction_date=date.today(),
                    quantity=item['quantity'],
                    unit_price=item['unit_price'],
                    notes=item['notes'],
                    purchase_order=po,
                    created_by=request.user
                )
                print(f"🔍 Created transaction {supply_transaction.id} for {item['product'].name}")
            
            # Mark PO as completed
            po.is_completed = True
            po.save(update_fields=['is_completed', 'updated_at'])
            print(f"🔍 Marked PO {po.po_number} as completed")
        
        return JsonResponse({
            'success': True,
            'message': f'Purchase Order {po.po_number} completed successfully! '
                      f'{len(validated_items)} items received for {total_cost:.3f} JOD total cost.',
            'transaction_count': len(validated_items),
            'total_cost': float(total_cost),
            'po_number': po.po_number
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        print(f"🔍 ERROR in po_bulk_complete: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f'Error processing request: {str(e)}'})
    

@operations_access_required
def po_cancel(request):
    """Cancel PO and delete it from database (if no items committed)"""
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
            return JsonResponse({'success': False, 'error': 'Cannot cancel completed purchase order'})
        
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
            return JsonResponse({
                'success': True,
                'action': 'delete_po',
                'message': f'Purchase Order {po_number} cancelled and removed.'
            })
        
    except PurchaseOrder.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Purchase order not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error cancelling purchase order: {str(e)}'})
    
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
        export_format = data.get('format', 'pdf')
        language = data.get('language', 'en')
        
        if not po_id or not cart_items:
            return JsonResponse({'success': False, 'error': 'PO ID and cart items required'})
        
        # Get translated labels using existing system
        from frontend.export_views import get_translated_labels
        labels = get_translated_labels(request, {'language': language})
        
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
                quantity_breakdown = f"{num_boxes} {labels['boxes']} × {items_per_box} = {quantity} {labels['units_total']}"
                calculation_verification = f"{num_boxes} × {items_per_box} × {unit_price:.3f} = {total_amount:.3f} {labels['currency_jod']}"
            else:
                quantity_breakdown = f"{quantity} {labels['units_total']}"
                calculation_verification = f"{quantity} × {unit_price:.3f} = {total_amount:.3f} {labels['currency_jod']}"
            
            # Smart cost verification
            product_default_cost = float(product.purchase_price) if product.purchase_price else 0
            cost_status = f"✓ {labels['normal_status']}"
            
            if product_default_cost > 0:
                variance_pct = ((unit_price - product_default_cost) / product_default_cost) * 100
                
                if variance_pct > 20:
                    cost_status = f"⚠ {labels['high_cost_status']} (+{variance_pct:.1f}%)"
                    verification_alerts.append(f"{product.name}: Unit cost {unit_price:.3f} {labels['currency_jod']} is {variance_pct:.1f}% above standard ({product_default_cost:.3f} {labels['currency_jod']})")
                elif variance_pct < -20:
                    cost_status = f"⚠ {labels['low_cost_status']} ({variance_pct:.1f}%)"
                    verification_alerts.append(f"{product.name}: Unit cost {unit_price:.3f} {labels['currency_jod']} is {abs(variance_pct):.1f}% below standard ({product_default_cost:.3f} {labels['currency_jod']})")
            
            # Enhanced cart item for export
            enhanced_item = {
                'product_name': product.name,
                'product_item_id': product.item_id,
                'quantity_breakdown': quantity_breakdown,
                'unit_cost_display': f"{unit_price:.3f} {labels['currency_jod']} {labels['per_unit']}",
                'total_amount_display': f"{total_amount:.3f} {labels['currency_jod']}",
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
        
        metadata = {
            labels['export_date']: datetime.now().strftime('%d/%m/%Y %H:%M'),
            labels['po_number']: str(po.po_number),
            labels['vessel']: po.vessel.name,
            labels['po_date']: po.po_date.strftime('%d/%m/%Y'),
            labels['status']: status_display,
            labels['total_cost']: f"{total_cost:.3f} {labels['currency_jod']}",
            labels['total_items']: f"{len(enhanced_cart_data)} {labels['products']}",
            labels['total_quantity']: f"{total_quantity:.0f} {labels['units']}",
            labels['average_cost_per_unit']: f"{(total_cost / total_quantity) if total_quantity > 0 else 0:.3f} {labels['currency_jod']}",
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
            labels['total_products']: str(len(enhanced_cart_data)),
            labels['total_quantity']: f"{total_quantity:.0f} {labels['units']}",
            labels['total_cost']: f"{total_cost:.3f} {labels['currency_jod']}",
            labels['average_cost_per_unit']: f"{(total_cost / total_quantity) if total_quantity > 0 else 0:.3f} {labels['currency_jod']}",
            labels['verification_status']: f"{len(verification_alerts)} {labels['alerts']}" if verification_alerts else labels['no_alerts_message']
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
        
        # Generate title
        if language == 'ar':
            report_title = f"تقرير التحقق من أمر الشراء {po.po_number} ({labels['auto_generated']})"
        else:
            report_title = f"PO {po.po_number} Verification Report ({labels['auto_generated']})"
        
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
                'generation_date': datetime.now().strftime('%d/%m/%Y %H:%M'),
                'has_logo': False,
                'is_cart_export': True,
                'total_cost_for_checklist': total_cost,
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