from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from datetime import date
from frontend.utils.cache_helpers import VesselCacheHelper
from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, PurchaseOrder
from .utils import BilingualMessages
from django.core.exceptions import ValidationError
from datetime import datetime
import json
from decimal import Decimal
import decimal
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

@operations_access_required
def supply_entry(request):
    """Step 1: Create new purchase order for supply transactions"""
    
    if request.method == 'GET':
        vessels = VesselCacheHelper.get_active_vessels()
        recent_pos = PurchaseOrder.objects.select_related('vessel', 'created_by').order_by('-created_at')[:10]
        
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
        po_transactions = Transaction.objects.filter(
            purchase_order=po,
            transaction_type='SUPPLY'
        ).select_related('product').order_by('created_at')
        
        for supply in po_transactions:
            completed_supplies.append({
                'product_name': supply.product.name,
                'product_item_id': supply.product.item_id,
                'quantity': int(supply.quantity),
                'unit_price': float(supply.unit_price),
                'total_amount': float(supply.total_amount),  # This is the cost for supplies
                'is_duty_free': supply.product.is_duty_free,  # ✅ Added
                'notes': supply.notes or '',
                'created_at': supply.created_at.strftime('%H:%M')
            })
    
    # Convert to JSON strings for safe template rendering
    existing_supplies_json = json.dumps(existing_supplies)
    completed_supplies_json = json.dumps(completed_supplies)
    
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
    """AJAX endpoint to search for products for supply entry"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        search_term = data.get('search', '').strip()
        
        if not search_term:
            return JsonResponse({'success': False, 'error': 'Search term required'})
        
        # Search for active products
        products = Product.objects.filter(
            active=True
        ).filter(
            Q(name__icontains=search_term) |
            Q(item_id__icontains=search_term) |
            Q(barcode__icontains=search_term)
        ).select_related('category')
        
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
def po_bulk_complete(request):
    """Complete purchase order with bulk transaction creation"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        
        po_id = data.get('po_id')
        items = data.get('items', [])  # Array of items from frontend
        
        if not po_id or not items:
            return JsonResponse({'success': False, 'error': 'PO ID and items required'})
        
        # Get purchase order
        po = PurchaseOrder.objects.get(id=po_id)
        
        if po.is_completed:
            return JsonResponse({'success': False, 'error': 'Purchase order is already completed'})
        
        # Validate all items first (before saving anything)
        validated_items = []
        total_cost = 0
        
        for item in items:
            product_id = item.get('product_id')
            quantity = item.get('quantity')
            purchase_cost = item.get('purchase_cost')
            notes = item.get('notes', '')
            
            if not product_id or not quantity or not purchase_cost:
                return JsonResponse({'success': False, 'error': 'Invalid item data'})
            
            # Get product and validate
            try:
                product = Product.objects.get(id=product_id, active=True)
            except Product.DoesNotExist:
                return JsonResponse({'success': False, 'error': f'Product not found: {product_id}'})
            
            # Validate duty-free compatibility
            if product.is_duty_free and not po.vessel.has_duty_free:
                return JsonResponse({
                    'success': False, 
                    'error': f'Cannot add duty-free product {product.name} to {po.vessel.name}'
                })
            
            # Validate values
            try:
                quantity_val = int(quantity)
                cost_val = Decimal(str(purchase_cost))
                
                if quantity_val <= 0 or cost_val <= 0:
                    return JsonResponse({'success': False, 'error': 'Quantity and cost must be positive'})
                
            except (ValueError, decimal.InvalidOperation):
                return JsonResponse({'success': False, 'error': 'Invalid quantity or cost values'})
            
            # Add to validated items
            validated_items.append({
                'product': product,
                'quantity': quantity_val,
                'cost': cost_val,
                'notes': notes,
                'total_cost': quantity_val * cost_val
            })
            total_cost += quantity_val * cost_val
        
        # All items validated - now create transactions atomically
        
        with transaction.atomic():
            created_transactions = []
            
            for item in validated_items:
                supply_transaction = Transaction.objects.create(
                    vessel=po.vessel,
                    product=item['product'],
                    transaction_type='SUPPLY',
                    transaction_date=po.po_date,
                    quantity=item['quantity'],
                    unit_price=item['cost'],
                    purchase_order=po,
                    notes=item['notes'] or f'Supply for PO {po.po_number}',
                    created_by=request.user
                )
                created_transactions.append(supply_transaction)
            
            # Mark PO as completed
            po.is_completed = True
            po.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Purchase Order {po.po_number} completed successfully!',
            'po_data': {
                'po_number': po.po_number,
                'items_count': len(created_transactions),
                'total_cost': float(total_cost),
                'vessel': po.vessel.name
            }
        })
        
    except PurchaseOrder.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Purchase order not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error completing purchase order: {str(e)}'})
    

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