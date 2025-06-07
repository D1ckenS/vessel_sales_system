from django.forms import ValidationError
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q, F, Case, When, Avg
from django.http import JsonResponse, HttpResponse
from datetime import date, timedelta, datetime
from decimal import Decimal
import decimal
from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, InventoryLot, Trip, PurchaseOrder
from .utils import BilingualMessages
from django.utils import timezone
from django.db import models
from .utils.exports import ExcelExporter, PDFExporter

@login_required
def supply_entry(request):
    """Step 1: Create new purchase order for supply transactions"""
    
    if request.method == 'GET':
        vessels = Vessel.objects.filter(active=True).order_by('name')
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
            
            from datetime import datetime
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

@login_required
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
                'total_amount': float(supply.total_amount),
                'notes': supply.notes or '',
                'created_at': supply.created_at.strftime('%H:%M')
            })
    
    # Convert to JSON strings for safe template rendering
    import json
    existing_supplies_json = json.dumps(existing_supplies)
    completed_supplies_json = json.dumps(completed_supplies)
    
    context = {
        'po': po,
        'existing_supplies_json': existing_supplies_json,  # JSON string
        'completed_supplies_json': completed_supplies_json,  # JSON string
        'can_edit': not po.is_completed,  # Frontend can use this to show/hide edit features
    }
    
    return render(request, 'frontend/po_supply.html', context)


@login_required
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

@login_required
def supply_search_products(request):
    """AJAX endpoint to search for products for supply entry"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
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

@login_required
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
        from datetime import datetime
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

@login_required
def add_product(request):
    """Add new product with optional initial stock distribution"""
    
    if request.method == 'GET':
        # Display the add product form
        from products.models import Category
        
        categories = Category.objects.filter(active=True).order_by('name')
        vessels = Vessel.objects.filter(active=True).order_by('name')
        
        context = {
            'categories': categories,
            'vessels': vessels,
            'today': date.today(),
        }
        
        return render(request, 'frontend/add_product.html', context)
    
    elif request.method == 'POST':
        try:
            # Get form data
            name = request.POST.get('name', '').strip()
            item_id = request.POST.get('item_id', '').strip()
            barcode = request.POST.get('barcode', '').strip() or None
            category_id = request.POST.get('category')
            purchase_price = request.POST.get('purchase_price')
            selling_price = request.POST.get('selling_price')
            is_duty_free = request.POST.get('is_duty_free') == 'on'
            active = request.POST.get('active') == 'on'
            
            # Get action from either field
            action = request.POST.get('action') or request.POST.get('form_action')
            
            # Basic validation
            if not all([name, item_id, category_id, purchase_price, selling_price]):
                BilingualMessages.error(request, 'required_fields_missing')
                return redirect('frontend:add_product')
            
            # Validate unique item_id
            if Product.objects.filter(item_id=item_id).exists():
                BilingualMessages.error(request, 'product_already_exists', item_id=item_id)
                return redirect('frontend:add_product')
            
            # Get category
            from products.models import Category
            try:
                category = Category.objects.get(id=category_id, active=True)
            except Category.DoesNotExist:
                BilingualMessages.error(request, 'invalid_category')
                return redirect('frontend:add_product')
            
            # Create the product
            from decimal import Decimal
            product = Product.objects.create(
                name=name,
                item_id=item_id,
                barcode=barcode,
                category=category,
                purchase_price=Decimal(purchase_price),
                selling_price=Decimal(selling_price),
                is_duty_free=is_duty_free,
                active=active,
                created_by=request.user
            )
            
            # Handle initial stock
            if action == 'with_stock':
                purchase_date_str = request.POST.get('purchase_date')
                if not purchase_date_str:
                    BilingualMessages.error(request, 'purchase_date_required')
                    product.delete()
                    return redirect('frontend:add_product')
                
                from datetime import datetime
                purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d').date()
                
                # Process each vessel
                vessels_processed = []
                vessels = Vessel.objects.filter(active=True)
                
                for vessel in vessels:
                    vessel_enabled = request.POST.get(f'vessel_{vessel.id}_enabled') == 'on'
                    
                    if vessel_enabled:
                        quantity_str = request.POST.get(f'vessel_{vessel.id}_quantity', '').strip()
                        cost_str = request.POST.get(f'vessel_{vessel.id}_cost', '').strip()
                        
                        if quantity_str and cost_str:
                            try:
                                quantity = int(quantity_str)
                                cost = Decimal(cost_str)
                                
                                if quantity > 0 and cost > 0:
                                    # Duty-free validation
                                    if product.is_duty_free and not vessel.has_duty_free:
                                        BilingualMessages.error(request, 'cannot_add_duty_free', 
                                                              vessel_name=get_vessel_display_name(vessel, BilingualMessages.get_user_language(request)))
                                        product.delete()
                                        return redirect('frontend:add_product')
                                    
                                    # Create SUPPLY transaction
                                    supply_transaction = Transaction.objects.create(
                                        vessel=vessel,
                                        product=product,
                                        transaction_type='SUPPLY',
                                        transaction_date=purchase_date,
                                        quantity=quantity,
                                        unit_price=cost,
                                        notes=f'Initial stock for new product {product.item_id}',
                                        created_by=request.user
                                    )
                                    
                                    vessels_processed.append({
                                        'vessel': vessel,
                                        'quantity': quantity,
                                        'cost': cost
                                    })
                                    
                            except (ValueError, decimal.InvalidOperation) as e:
                                BilingualMessages.error(request, 'invalid_vessel_data', 
                                                      vessel_name=get_vessel_display_name(vessel, BilingualMessages.get_user_language(request)))
                                product.delete()
                                return redirect('frontend:add_product')
                
                if vessels_processed:
                    # Format vessel list for message
                    language = BilingualMessages.get_user_language(request)
                    vessel_list = '; '.join([
                        f'{get_vessel_display_name(v["vessel"], language)}: {v["quantity"]} units @ {v["cost"]} JOD'
                        for v in vessels_processed
                    ])
                    BilingualMessages.success(request, 'product_created_with_stock', 
                                            name=product.name, vessels=vessel_list)
                else:
                    BilingualMessages.error(request, 'no_valid_stock_data')
                    product.delete()
                    return redirect('frontend:add_product')
                    
            else:
                BilingualMessages.success(request, 'product_created_success', 
                                        name=product.name, item_id=product.item_id)
            
            return redirect('frontend:inventory_check')
            
        except Exception as e:
            BilingualMessages.error(request, 'error_creating_product', error=str(e))
            return redirect('frontend:add_product')
    
    else:
        BilingualMessages.error(request, 'invalid_request_method')
        return redirect('frontend:inventory_check')

@login_required
def dashboard(request):
    """Main dashboard with overview and navigation"""
    
    # Get basic stats
    today = date.today()
    now = datetime.now()
    vessels = Vessel.objects.filter(active=True)
    
    # Today's sales summary
    today_sales = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date=today
    ).aggregate(
        total_revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        transaction_count=Count('id')
    )
    
    # Recent transactions
    recent_transactions = Transaction.objects.select_related(
        'vessel', 'product'
    ).order_by('-created_at')[:6]
    
    context = {
        'vessels': vessels,
        'today_sales': today_sales,
        'recent_transactions': recent_transactions,
        'today': today,
        'now': now,
    }
    
    return render(request, 'frontend/dashboard.html', context)

@login_required
def sales_entry(request):
    """Step 1: Create new trip for sales transactions"""
    
    if request.method == 'GET':
        vessels = Vessel.objects.filter(active=True).order_by('name')
        recent_trips = Trip.objects.select_related('vessel', 'created_by').order_by('-created_at')[:10]
        
        context = {
            'vessels': vessels,
            'recent_trips': recent_trips,
            'today': date.today(),
        }
        
        return render(request, 'frontend/sales_entry.html', context)
    
    elif request.method == 'POST':
        try:
            # Get form data
            vessel_id = request.POST.get('vessel')
            trip_number = request.POST.get('trip_number', '').strip()
            passenger_count = request.POST.get('passenger_count')
            trip_date = request.POST.get('trip_date')
            notes = request.POST.get('notes', '').strip()
            
            # Validate required fields
            if not all([vessel_id, trip_number, passenger_count, trip_date]):
                BilingualMessages.error(request, 'required_fields_missing')
                return redirect('frontend:sales_entry')
            
            # Get vessel
            vessel = Vessel.objects.get(id=vessel_id, active=True)
            
            # Validate trip number uniqueness
            if Trip.objects.filter(trip_number=trip_number).exists():
                BilingualMessages.error(request, 'trip_number_exists', trip_number=trip_number)
                return redirect('frontend:sales_entry')
            
            # Parse and validate data
            passenger_count_val = int(passenger_count)
            if passenger_count_val <= 0:
                BilingualMessages.error(request, 'passenger_count_positive')
                return redirect('frontend:sales_entry')
            
            from datetime import datetime
            trip_date_obj = datetime.strptime(trip_date, '%Y-%m-%d').date()
            
            # Create trip
            trip = Trip.objects.create(
                trip_number=trip_number,
                vessel=vessel,
                passenger_count=passenger_count_val,
                trip_date=trip_date_obj,
                notes=notes,
                created_by=request.user
            )
            
            BilingualMessages.success(request, 'trip_created_success', trip_number=trip_number)
            return redirect('frontend:trip_sales', trip_id=trip.id)
            
        except Vessel.DoesNotExist:
            BilingualMessages.error(request, 'invalid_vessel')
            return redirect('frontend:sales_entry')
        except (ValueError, ValidationError) as e:
            BilingualMessages.error(request, 'invalid_data', error=str(e))
            return redirect('frontend:sales_entry')
        except Exception as e:
            BilingualMessages.error(request, 'error_creating_trip', error=str(e))
            return redirect('frontend:sales_entry')

@login_required
def trip_sales(request, trip_id):
    """Step 2: Multi-item sales entry for a specific trip (Shopping Cart Approach)"""
    
    try:
        trip = Trip.objects.select_related('vessel').get(id=trip_id)
    except Trip.DoesNotExist:
        BilingualMessages.error(request, 'Trip not found.')
        return redirect('frontend:sales_entry')
    
    # Get existing sales for this trip (to populate shopping cart if trip was previously started)
    existing_sales = []
    if not trip.is_completed:
        # Only load for incomplete trips - completed trips should be read-only
        trip_transactions = Transaction.objects.filter(
            trip=trip,
            transaction_type='SALE'
        ).select_related('product').order_by('created_at')
        
        # Convert to format expected by frontend shopping cart
        for sale in trip_transactions:
            existing_sales.append({
                'id': sale.id,  # Include for edit/delete functionality
                'product_id': sale.product.id,
                'product_name': sale.product.name,
                'product_item_id': sale.product.item_id,
                'product_barcode': sale.product.barcode or '',
                'is_duty_free': sale.product.is_duty_free,
                'quantity': int(sale.quantity),
                'unit_price': float(sale.unit_price),
                'total_amount': float(sale.total_amount),
                'notes': sale.notes or '',
                'created_at': sale.created_at.strftime('%H:%M')
            })
    
    # If trip is completed, get read-only sales data for display
    completed_sales = []
    if trip.is_completed:
        trip_transactions = Transaction.objects.filter(
            trip=trip,
            transaction_type='SALE'
        ).select_related('product').order_by('created_at')
        
        for sale in trip_transactions:
            completed_sales.append({
                'product_name': sale.product.name,
                'product_item_id': sale.product.item_id,
                'quantity': int(sale.quantity),
                'unit_price': float(sale.unit_price),
                'total_amount': float(sale.total_amount),
                'notes': sale.notes or '',
                'created_at': sale.created_at.strftime('%H:%M')
            })
    
    # Convert to JSON strings for safe template rendering
    import json
    existing_sales_json = json.dumps(existing_sales)
    completed_sales_json = json.dumps(completed_sales)
    
    context = {
        'trip': trip,
        'existing_sales_json': existing_sales_json,  # JSON string
        'completed_sales_json': completed_sales_json,  # JSON string
        'can_edit': not trip.is_completed,  # Frontend can use this to show/hide edit features
    }
    
    return render(request, 'frontend/trip_sales.html', context)

@login_required
def sales_search_products(request):
    """AJAX endpoint to search for products available on specific vessel"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
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
        
        # Filter duty-free products if vessel doesn't support them
        if not vessel.has_duty_free:
            available_lots = available_lots.filter(product__is_duty_free=False)
        
        # Group by product and calculate totals
        from django.db.models import Sum
        product_summaries = available_lots.values(
            'product__id', 'product__name', 'product__item_id', 
            'product__barcode', 'product__is_duty_free',
            'product__selling_price'
        ).annotate(
            total_quantity=Sum('remaining_quantity')
        ).order_by('product__item_id')
        
        products = []
        for summary in product_summaries:
            product_id = summary['product__id']
            
            # Get FIFO lots for this product (for detailed view)
            lots = InventoryLot.objects.filter(
                vessel=vessel,
                product_id=product_id,
                remaining_quantity__gt=0
            ).order_by('purchase_date', 'created_at')
            
            # Get current cost (oldest available lot)
            current_cost = lots.first().purchase_price if lots.exists() else 0
            
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
                'selling_price': float(summary['product__selling_price']),
                'current_cost': float(current_cost),
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

@login_required
def sales_validate_inventory(request):
    """AJAX endpoint to validate inventory and preview FIFO consumption"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        vessel_id = data.get('vessel_id')
        product_id = data.get('product_id')
        quantity = data.get('quantity', 0)
        
        if not all([vessel_id, product_id]) or quantity <= 0:
            return JsonResponse({'success': False, 'error': 'Invalid parameters'})
        
        # Get objects
        vessel = Vessel.objects.get(id=vessel_id, active=True)
        product = Product.objects.get(id=product_id, active=True)
        
        # Get available inventory and FIFO lots
        from transactions.models import get_available_inventory, consume_inventory_fifo
        available_quantity, lots = get_available_inventory(vessel, product)
        
        if quantity > available_quantity:
            return JsonResponse({
                'success': False, 
                'error': f'Insufficient inventory. Available: {available_quantity}, Requested: {quantity}'
            })
        
        # Simulate FIFO consumption to show preview
        consumption_preview = []
        remaining_to_consume = quantity
        total_fifo_cost = 0
        
        for lot in lots:
            if remaining_to_consume <= 0:
                break
            
            consumed_from_lot = min(lot.remaining_quantity, remaining_to_consume)
            lot_cost = consumed_from_lot * lot.purchase_price
            total_fifo_cost += lot_cost
            
            consumption_preview.append({
                'lot_date': lot.purchase_date.strftime('%d/%m/%Y'),
                'consumed_quantity': consumed_from_lot,
                'unit_cost': float(lot.purchase_price),
                'total_cost': float(lot_cost)
            })
            
            remaining_to_consume -= consumed_from_lot
        
        # Calculate profit
        total_revenue = quantity * product.selling_price
        total_profit = total_revenue - total_fifo_cost
        
        return JsonResponse({
            'success': True,
            'available_quantity': available_quantity,
            'after_sale_quantity': available_quantity - quantity,
            'consumption_preview': consumption_preview,
            'total_fifo_cost': float(total_fifo_cost),
            'total_revenue': float(total_revenue),
            'total_profit': float(total_profit),
            'selling_price': float(product.selling_price)
        })
        
    except (Vessel.DoesNotExist, Product.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Vessel or product not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def sales_execute(request):
    """AJAX endpoint to execute sales transaction using FIFO system"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        
        # Get and validate data
        vessel_id = data.get('vessel_id')
        product_id = data.get('product_id')
        quantity = data.get('quantity')
        sale_date = data.get('sale_date')
        notes = data.get('notes', '')
        
        if not all([vessel_id, product_id, quantity, sale_date]):
            return JsonResponse({'success': False, 'error': 'Missing required fields'})
        
        # Get objects
        vessel = Vessel.objects.get(id=vessel_id, active=True)
        product = Product.objects.get(id=product_id, active=True)
        
        # Validate duty-free compatibility
        if product.is_duty_free and not vessel.has_duty_free:
            return JsonResponse({
                'success': False, 
                'error': f'Cannot sell duty-free product on {vessel.name} (vessel does not support duty-free items)'
            })
        
        # Check available inventory
        from transactions.models import get_available_inventory
        available_quantity, lots = get_available_inventory(vessel, product)
        
        if quantity > available_quantity:
            return JsonResponse({
                'success': False, 
                'error': f'Insufficient inventory. Available: {available_quantity}, Requested: {quantity}'
            })
        
        # Parse sale date
        from datetime import datetime
        sale_date_obj = datetime.strptime(sale_date, '%Y-%m-%d').date()
        
        # Create SALE transaction (your existing system handles FIFO consumption!)
        sale_transaction = Transaction.objects.create(
            vessel=vessel,
            product=product,
            transaction_type='SALE',
            transaction_date=sale_date_obj,
            quantity=quantity,
            unit_price=product.selling_price,  # Use product's selling price
            notes=notes or f'Sale on {vessel.name}',
            created_by=request.user
        )
        
        # Your existing _handle_sale() method will:
        # 1. Consume inventory using FIFO
        # 2. Update InventoryLot remaining quantities
        # 3. Log FIFO consumption details in notes
        
        return JsonResponse({
            'success': True,
            'message': f'Sale completed: {quantity} units of {product.name} sold from {vessel.name}',
            'transaction_id': sale_transaction.id,
            'revenue': float(sale_transaction.total_amount)
        })
        
    except (Vessel.DoesNotExist, Product.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Vessel or product not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Sale failed: {str(e)}'})

@login_required
def inventory_check(request):
    """Vessel-specific inventory interface with tabs and focused stats"""
    
    # Get all active vessels for tabs
    vessels = Vessel.objects.filter(active=True).order_by('name')

    # For SPA, we don't auto-load data - just show the interface
    context = {
        'vessels': vessels,
        'selected_vessel': vessels.first() if vessels.exists() else None,
    }

    # Get selected vessel (default to first vessel)
    selected_vessel_id = request.GET.get('vessel')
    if selected_vessel_id:
        try:
            selected_vessel = Vessel.objects.get(id=selected_vessel_id, active=True)
        except Vessel.DoesNotExist:
            selected_vessel = vessels.first()
    else:
        selected_vessel = vessels.first()
    
    # Get search parameters
    product_search = request.GET.get('search', '')
    stock_filter = request.GET.get('stock', '')
    
    if not selected_vessel:
        # No vessels available
        context = {
            'vessels': vessels,
            'selected_vessel': None,
            'inventory_data': [],
            'vessel_stats': {
                'total_products': 0,
                'low_stock_count': 0,
                'out_of_stock_count': 0,
                'good_stock_count': 0,
                'total_inventory_value': 0,
            },
            'filters': {
                'product_search': product_search,
                'stock_filter': stock_filter,
            }
        }
        return render(request, 'frontend/inventory_check.html', context)
    
    # Get inventory for selected vessel only
    available_lots = InventoryLot.objects.filter(
        vessel=selected_vessel,
        remaining_quantity__gt=0,
        product__active=True
    ).select_related('product')
    
    # Apply product search filter
    if product_search:
        available_lots = available_lots.filter(
            Q(product__name__icontains=product_search) | 
            Q(product__item_id__icontains=product_search) |
            Q(product__barcode__icontains=product_search)
        )
    
    # Group by product and calculate vessel-specific stats
    from django.db.models import Sum
    inventory_summary = available_lots.values(
        'product__id', 'product__name', 'product__item_id', 
        'product__barcode', 'product__is_duty_free'
    ).annotate(
        total_quantity=Sum('remaining_quantity')
    ).order_by('product__item_id')
    
    # Build inventory data with vessel-specific calculations
    inventory_data = []
    vessel_total_value = 0
    vessel_low_stock = 0
    vessel_out_of_stock = 0
    
    for item in inventory_summary:
        product_id = item['product__id']
        total_qty = item['total_quantity']
        
        # Get FIFO lots for this product on this vessel
        lots = InventoryLot.objects.filter(
            vessel=selected_vessel,
            product_id=product_id,
            remaining_quantity__gt=0
        ).order_by('purchase_date', 'created_at')
        
        # Calculate current cost (oldest available lot) and total value
        current_cost = lots.first().purchase_price if lots.exists() else 0
        total_value = sum(lot.remaining_quantity * lot.purchase_price for lot in lots)
        
        # Determine stock status for this vessel
        if total_qty == 0:
            stock_status = 'out'
            status_class = 'danger'
            status_text = 'Out of Stock'
            vessel_out_of_stock += 1
        elif total_qty <= 10:  # Low stock threshold
            stock_status = 'low'
            status_class = 'warning' 
            status_text = 'Low Stock'
            vessel_low_stock += 1
        else:
            stock_status = 'good'
            status_class = 'success'
            status_text = 'Good Stock'
        
        # Apply stock level filter
        if stock_filter and stock_filter != stock_status:
            continue
            
        inventory_data.append({
            'vessel_id': selected_vessel.id,
            'vessel_name': selected_vessel.name,
            'product_id': product_id,
            'product_name': item['product__name'],
            'product_item_id': item['product__item_id'],
            'product_barcode': item['product__barcode'],
            'is_duty_free': item['product__is_duty_free'],
            'total_quantity': total_qty,
            'current_cost': current_cost,
            'total_value': total_value,
            'stock_status': stock_status,
            'status_class': status_class,
            'status_text': status_text,
            'lots': lots,
        })
        
        vessel_total_value += total_value
    
    # Check for products with zero inventory on this vessel
    all_products_on_vessel = InventoryLot.objects.filter(
        vessel=selected_vessel,
        product__active=True
    ).values('product_id').distinct()
    
    products_with_zero_stock = Product.objects.filter(
        active=True,
        id__in=[p['product_id'] for p in all_products_on_vessel]
    ).exclude(
        id__in=[item['product_id'] for item in inventory_data]
    )
    
    # Add zero-stock products if no stock filter applied
    if not stock_filter or stock_filter == 'out':
        for product in products_with_zero_stock:
            vessel_out_of_stock += 1
            inventory_data.append({
                'vessel_id': selected_vessel.id,
                'vessel_name': selected_vessel.name,
                'product_id': product.id,
                'product_name': product.name,
                'product_item_id': product.item_id,
                'product_barcode': product.barcode,
                'is_duty_free': product.is_duty_free,
                'total_quantity': 0,
                'current_cost': 0,
                'total_value': 0,
                'stock_status': 'out',
                'status_class': 'danger',
                'status_text': 'Out of Stock',
                'lots': [],
            })
    
    # Calculate vessel-specific stats
    vessel_total_products = len(inventory_data)
    vessel_good_stock = vessel_total_products - vessel_low_stock - vessel_out_of_stock
    
    # Prepare context
    context = {
        'vessels': vessels,
        'selected_vessel': selected_vessel,
        'inventory_data': inventory_data,
        'vessel_stats': {
            'total_products': vessel_total_products,
            'low_stock_count': vessel_low_stock,
            'out_of_stock_count': vessel_out_of_stock,
            'good_stock_count': vessel_good_stock,
            'total_inventory_value': vessel_total_value,
        },
        'filters': {
            'product_search': product_search,
            'stock_filter': stock_filter,
        }
    }
    
    return render(request, 'frontend/inventory_check.html', context)

@login_required
def inventory_details_ajax(request, product_id, vessel_id):
    """AJAX endpoint for product inventory details"""
    try:
        product = Product.objects.get(id=product_id)
        vessel = Vessel.objects.get(id=vessel_id)
        
        # Get FIFO lots for this product-vessel combination
        lots = InventoryLot.objects.filter(
            vessel=vessel,
            product=product,
            remaining_quantity__gt=0
        ).order_by('purchase_date', 'created_at')
        
        # Get recent transactions
        recent_transactions = Transaction.objects.filter(
            vessel=vessel,
            product=product
        ).order_by('-transaction_date', '-created_at')[:10]
        
        # Prepare data
        lots_data = []
        for lot in lots:
            lots_data.append({
                'purchase_date': lot.purchase_date.strftime('%d/%m/%Y'),
                'remaining_quantity': lot.remaining_quantity,
                'original_quantity': lot.original_quantity,
                'purchase_price': float(lot.purchase_price),
                'total_value': float(lot.remaining_quantity * lot.purchase_price)
            })
        
        transactions_data = []
        for txn in recent_transactions:
            transactions_data.append({
                'date': txn.transaction_date.strftime('%d/%m/%Y'),
                'type': txn.get_transaction_type_display(),
                'type_code': txn.transaction_type,
                'quantity': float(txn.quantity),
                'unit_price': float(txn.unit_price) if txn.unit_price else 0,
                'total_amount': float(txn.total_amount),
                'notes': txn.notes or ''
            })
        
        return JsonResponse({
            'success': True,
            'product': {
                'name': product.name,
                'item_id': product.item_id,
                'barcode': product.barcode or 'N/A',
                'category': product.category.name,
                'purchase_price': float(product.purchase_price),
                'selling_price': float(product.selling_price),
                'is_duty_free': product.is_duty_free,  # This should show the actual value
            },
            'vessel': {
                'name': vessel.name,
                'has_duty_free': vessel.has_duty_free,
            },
            'lots': lots_data,
            'recent_transactions': transactions_data
        })
        
    except (Product.DoesNotExist, Vessel.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Product or vessel not found'})
    
@login_required
def inventory_data_ajax(request):
    """AJAX endpoint to load vessel inventory data for SPA"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        vessel_id = data.get('vessel_id')
        search_term = data.get('search', '').strip()
        stock_filter = data.get('stock_filter', '')
        
        if not vessel_id:
            return JsonResponse({'success': False, 'error': 'Vessel ID required'})
        
        # Get vessel
        vessel = Vessel.objects.get(id=vessel_id, active=True)
        
        # Get inventory for selected vessel
        available_lots = InventoryLot.objects.filter(
            vessel=vessel,
            remaining_quantity__gt=0,
            product__active=True
        ).select_related('product')
        
        # Apply product search filter
        if search_term:
            available_lots = available_lots.filter(
                Q(product__name__icontains=search_term) | 
                Q(product__item_id__icontains=search_term) |
                Q(product__barcode__icontains=search_term)
            )
        
        # Group by product and calculate vessel-specific stats
        from django.db.models import Sum
        inventory_summary = available_lots.values(
            'product__id', 'product__name', 'product__item_id', 
            'product__barcode', 'product__is_duty_free'
        ).annotate(
            total_quantity=Sum('remaining_quantity')
        ).order_by('product__item_id')
        
        # Build inventory data with vessel-specific calculations
        inventory_data = []
        vessel_total_value = 0
        vessel_low_stock = 0
        vessel_out_of_stock = 0
        
        for item in inventory_summary:
            product_id = item['product__id']
            total_qty = item['total_quantity']
            
            # Get FIFO lots for this product on this vessel
            lots = InventoryLot.objects.filter(
                vessel=vessel,
                product_id=product_id,
                remaining_quantity__gt=0
            ).order_by('purchase_date', 'created_at')
            
            # Calculate current cost (oldest available lot) and total value
            current_cost = lots.first().purchase_price if lots.exists() else 0
            total_value = sum(lot.remaining_quantity * lot.purchase_price for lot in lots)
            
            # Determine stock status for this vessel
            if total_qty == 0:
                stock_status = 'out'
                status_class = 'danger'
                status_text = 'Out of Stock'
                vessel_out_of_stock += 1
            elif total_qty <= 10:  # Low stock threshold
                stock_status = 'low'
                status_class = 'warning' 
                status_text = 'Low Stock'
                vessel_low_stock += 1
            else:
                stock_status = 'good'
                status_class = 'success'
                status_text = 'Good Stock'
            
            # Apply stock level filter
            if stock_filter and stock_filter != stock_status:
                continue
                
            inventory_data.append({
                'vessel_id': vessel.id,
                'vessel_name': vessel.name,
                'vessel_name_ar': vessel.name_ar,
                'product_id': product_id,
                'product_name': item['product__name'],
                'product_item_id': item['product__item_id'],
                'product_barcode': item['product__barcode'] or '',
                'is_duty_free': item['product__is_duty_free'],
                'total_quantity': total_qty,
                'current_cost': float(current_cost),
                'total_value': float(total_value),
                'stock_status': stock_status,
                'status_class': status_class,
                'status_text': status_text,
            })
            
            vessel_total_value += total_value
        
        # Check for products with zero inventory on this vessel
        all_products_on_vessel = InventoryLot.objects.filter(
            vessel=vessel,
            product__active=True
        ).values('product_id').distinct()
        
        products_with_zero_stock = Product.objects.filter(
            active=True,
            id__in=[p['product_id'] for p in all_products_on_vessel]
        ).exclude(
            id__in=[item['product_id'] for item in inventory_data]
        )
        
        # Add zero-stock products if no stock filter applied or out filter selected
        if not stock_filter or stock_filter == 'out':
            for product in products_with_zero_stock:
                # Apply search filter for zero stock items too
                if search_term:
                    if not (search_term.lower() in product.name.lower() or 
                           search_term.lower() in product.item_id.lower() or 
                           (product.barcode and search_term.lower() in product.barcode.lower())):
                        continue
                
                vessel_out_of_stock += 1
                inventory_data.append({
                    'vessel_id': vessel.id,
                    'vessel_name': vessel.name,
                    'product_id': product.id,
                    'product_name': product.name,
                    'product_item_id': product.item_id,
                    'product_barcode': product.barcode or '',
                    'is_duty_free': product.is_duty_free,
                    'total_quantity': 0,
                    'current_cost': 0,
                    'total_value': 0,
                    'stock_status': 'out',
                    'status_class': 'danger',
                    'status_text': 'Out of Stock',
                })
        
        # Calculate vessel-specific stats
        vessel_total_products = len(inventory_data)
        vessel_good_stock = vessel_total_products - vessel_low_stock - vessel_out_of_stock
        
        return JsonResponse({
            'success': True,
            'vessel': {
                'id': vessel.id,
                'name': vessel.name,
                'has_duty_free': vessel.has_duty_free,
            },
            'inventory_data': inventory_data,
            'vessel_stats': {
                'total_products': vessel_total_products,
                'low_stock_count': vessel_low_stock,
                'out_of_stock_count': vessel_out_of_stock,
                'good_stock_count': vessel_good_stock,
                'total_inventory_value': float(vessel_total_value),
            }
        })
        
    except Vessel.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Vessel not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required 
def transfer_center(request):
    """Functional transfer interface with FIFO cost preservation"""
    
    # Get all active vessels for dropdown
    vessels = Vessel.objects.filter(active=True).order_by('name')
    
    # Get recent transfers (last 20 TRANSFER_OUT transactions)
    recent_transfers = Transaction.objects.filter(
        transaction_type='TRANSFER_OUT'
    ).select_related(
        'vessel', 'product', 'transfer_to_vessel', 'created_by'
    ).order_by('-created_at')[:20]
    
    context = {
        'vessels': vessels,
        'recent_transfers': recent_transfers,
        'today': date.today(),
    }
    
    return render(request, 'frontend/transfer_center.html', context)

@login_required
def transfer_search_products(request):
    """AJAX endpoint to search for products with available inventory on specific vessel"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
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
        from django.db.models import Sum
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

@login_required
def transfer_execute(request):
    """AJAX endpoint to execute transfer using existing FIFO system"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
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
        from transactions.models import get_available_inventory
        available_quantity, lots = get_available_inventory(from_vessel, product)
        
        if quantity > available_quantity:
            return JsonResponse({
                'success': False, 
                'error': f'Insufficient inventory. Available: {available_quantity}, Requested: {quantity}'
            })
        
        # Parse transfer date
        from datetime import datetime
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
        
        # Your existing _handle_transfer_out() method will:
        # 1. Consume inventory using FIFO
        # 2. Create TRANSFER_IN transaction automatically
        # 3. Preserve individual lot costs on destination vessel
        # 4. Link the transactions
        
        return JsonResponse({
            'success': True,
            'message': f'Transfer completed: {quantity} units of {product.name} from {from_vessel.name} to {to_vessel.name}',
            'transfer_id': transfer_out.id
        })
        
    except (Vessel.DoesNotExist, Product.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Vessel or product not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Transfer failed: {str(e)}'})
def get_vessel_badge_class(vessel_name):
    """Helper function to get vessel badge class"""
    colors = {
        'amman': 'bg-primary',
        'aylah': 'bg-danger',
        'sinaa': 'bg-success', 
        'nefertiti': 'bg-secondary',
        'babel': 'bg-warning',
        'dahab': 'bg-info',
    }
    return colors.get(vessel_name.lower(), 'bg-primary')

# AJAX endpoints for multi-item functionality
@login_required
def trip_bulk_complete(request):
    """Complete trip with bulk transaction creation"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        
        trip_id = data.get('trip_id')
        items = data.get('items', [])  # Array of items from frontend
        
        if not trip_id or not items:
            return JsonResponse({'success': False, 'error': 'Trip ID and items required'})
        
        # Get trip
        trip = Trip.objects.get(id=trip_id)
        
        if trip.is_completed:
            return JsonResponse({'success': False, 'error': 'Trip is already completed'})
        
        # Validate all items first (before saving anything)
        validated_items = []
        total_revenue = 0
        
        for item in items:
            product_id = item.get('product_id')
            quantity = item.get('quantity')
            notes = item.get('notes', '')
            
            if not product_id or not quantity:
                return JsonResponse({'success': False, 'error': 'Invalid item data'})
            
            # Get product and validate
            try:
                product = Product.objects.get(id=product_id, active=True)
            except Product.DoesNotExist:
                return JsonResponse({'success': False, 'error': f'Product not found: {product_id}'})
            
            # Validate duty-free compatibility
            if product.is_duty_free and not trip.vessel.has_duty_free:
                return JsonResponse({
                    'success': False, 
                    'error': f'Cannot sell duty-free product {product.name} on {trip.vessel.name}'
                })
            
            # Check inventory availability
            from transactions.models import get_available_inventory
            available_quantity, lots = get_available_inventory(trip.vessel, product)
            
            if quantity > available_quantity:
                return JsonResponse({
                    'success': False, 
                    'error': f'Insufficient inventory for {product.name}. Available: {available_quantity}, Requested: {quantity}'
                })
            
            # Add to validated items
            validated_items.append({
                'product': product,
                'quantity': quantity,
                'notes': notes,
                'revenue': quantity * product.selling_price
            })
            total_revenue += quantity * product.selling_price
        
        # All items validated - now create transactions atomically
        from django.db import transaction
        with transaction.atomic():
            created_transactions = []
            
            for item in validated_items:
                sale_transaction = Transaction.objects.create(
                    vessel=trip.vessel,
                    product=item['product'],
                    transaction_type='SALE',
                    transaction_date=trip.trip_date,
                    quantity=item['quantity'],
                    unit_price=item['product'].selling_price,
                    trip=trip,
                    notes=item['notes'] or f'Sale for trip {trip.trip_number}',
                    created_by=request.user
                )
                created_transactions.append(sale_transaction)
            
            # Mark trip as completed
            trip.is_completed = True
            trip.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Trip {trip.trip_number} completed successfully!',
            'trip_data': {
                'trip_number': trip.trip_number,
                'items_count': len(created_transactions),
                'total_revenue': float(total_revenue),
                'vessel': trip.vessel.name
            }
        })
        
    except Trip.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Trip not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error completing trip: {str(e)}'})

@login_required
def po_bulk_complete(request):
    """Complete purchase order with bulk transaction creation"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
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
        from django.db import transaction
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

# Add this new view to handle trip cancellation

@login_required
def trip_cancel(request):
    """Cancel trip and delete it from database (if no items committed)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        trip_id = data.get('trip_id')
        
        if not trip_id:
            return JsonResponse({'success': False, 'error': 'Trip ID required'})
        
        # Get trip
        trip = Trip.objects.get(id=trip_id)
        
        if trip.is_completed:
            return JsonResponse({'success': False, 'error': 'Cannot cancel completed trip'})
        
        # Check if trip has any committed transactions
        existing_transactions = Transaction.objects.filter(trip=trip).count()
        
        if existing_transactions > 0:
            # Trip has committed transactions - just clear cart but keep trip
            return JsonResponse({
                'success': True,
                'action': 'clear_cart',
                'message': f'Cart cleared. Trip {trip.trip_number} kept (has committed transactions).'
            })
        else:
            # No committed transactions - safe to delete trip
            trip_number = trip.trip_number
            trip.delete()
            return JsonResponse({
                'success': True,
                'action': 'delete_trip',
                'message': f'Trip {trip_number} cancelled and removed.'
            })
        
    except Trip.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Trip not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error cancelling trip: {str(e)}'})

# Add the same for PO
@login_required
def po_cancel(request):
    """Cancel PO and delete it from database (if no items committed)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
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

@login_required
def trip_reports(request):
    """Trip-based sales reports"""
    
    # Get filter parameters
    vessel_filter = request.GET.get('vessel')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    status_filter = request.GET.get('status')
    
    # Base queryset
    trips = Trip.objects.select_related('vessel', 'created_by').prefetch_related('sales_transactions')
    
    # Apply filters
    if vessel_filter:
        trips = trips.filter(vessel_id=vessel_filter)
    if date_from:
        from datetime import datetime
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
        trips = trips.filter(trip_date__gte=date_from_obj)
    if date_to:
        from datetime import datetime
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
        trips = trips.filter(trip_date__lte=date_to_obj)
    if status_filter == 'completed':
        trips = trips.filter(is_completed=True)
    elif status_filter == 'in_progress':
        trips = trips.filter(is_completed=False)
    
    trips = trips.order_by('-trip_date', '-created_at')
    
    # Calculate summary statistics
    total_trips = trips.count()
    total_revenue = sum(trip.total_revenue for trip in trips)
    total_passengers = sum(trip.passenger_count for trip in trips)
    avg_revenue_per_trip = total_revenue / total_trips if total_trips > 0 else 0
    avg_revenue_per_passenger = total_revenue / total_passengers if total_passengers > 0 else 0
    
    # Get vessels for filter
    vessels = Vessel.objects.filter(active=True).order_by('name')
    
    context = {
        'trips': trips,
        'vessels': vessels,
        'filters': {
            'vessel': vessel_filter,
            'date_from': date_from,
            'date_to': date_to,
            'status': status_filter,
        },
        'summary': {
            'total_trips': total_trips,
            'total_revenue': total_revenue,
            'total_passengers': total_passengers,
            'avg_revenue_per_trip': avg_revenue_per_trip,
            'avg_revenue_per_passenger': avg_revenue_per_passenger,
        }
    }
    
    return render(request, 'frontend/trip_reports.html', context)

@login_required
def po_reports(request):
    """Purchase Order reports"""
    
    # Get filter parameters
    vessel_filter = request.GET.get('vessel')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    status_filter = request.GET.get('status')
    
    # Base queryset
    purchase_orders = PurchaseOrder.objects.select_related('vessel', 'created_by').prefetch_related('supply_transactions')
    
    # Apply filters
    if vessel_filter:
        purchase_orders = purchase_orders.filter(vessel_id=vessel_filter)
    if date_from:
        from datetime import datetime
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
        purchase_orders = purchase_orders.filter(po_date__gte=date_from_obj)
    if date_to:
        from datetime import datetime
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
        purchase_orders = purchase_orders.filter(po_date__lte=date_to_obj)
    if status_filter == 'completed':
        purchase_orders = purchase_orders.filter(is_completed=True)
    elif status_filter == 'in_progress':
        purchase_orders = purchase_orders.filter(is_completed=False)
    
    purchase_orders = purchase_orders.order_by('-po_date', '-created_at')
    
    # Calculate summary statistics
    total_pos = purchase_orders.count()
    total_cost = sum(po.total_cost for po in purchase_orders)
    avg_cost_per_po = total_cost / total_pos if total_pos > 0 else 0
    
    # Get vessels for filter
    vessels = Vessel.objects.filter(active=True).order_by('name')
    
    context = {
        'purchase_orders': purchase_orders,
        'vessels': vessels,
        'filters': {
            'vessel': vessel_filter,
            'date_from': date_from,
            'date_to': date_to,
            'status': status_filter,
        },
        'summary': {
            'total_pos': total_pos,
            'total_cost': total_cost,
            'avg_cost_per_po': avg_cost_per_po,
        }
    }
    
    return render(request, 'frontend/po_reports.html', context)

@login_required
def transactions_list(request):
    """Frontend transactions list to replace Django admin redirect"""
    
    # Get filter parameters
    transaction_type = request.GET.get('type')
    vessel_filter = request.GET.get('vessel')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Base queryset
    transactions = Transaction.objects.select_related(
        'vessel', 'product', 'created_by', 'trip', 'purchase_order'
    ).order_by('-transaction_date', '-created_at')
    
    # Apply filters
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    if vessel_filter:
        transactions = transactions.filter(vessel_id=vessel_filter)
    if date_from:
        from datetime import datetime
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
        transactions = transactions.filter(transaction_date__gte=date_from_obj)
    if date_to:
        from datetime import datetime
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
        transactions = transactions.filter(transaction_date__lte=date_to_obj)
    
    # Limit to recent transactions for performance
    transactions = transactions[:200]
    
    # Get vessels for filter
    vessels = Vessel.objects.filter(active=True).order_by('name')
    
    context = {
        'transactions': transactions,
        'vessels': vessels,
        'transaction_types': Transaction.TRANSACTION_TYPES,
        'filters': {
            'type': transaction_type,
            'vessel': vessel_filter,
            'date_from': date_from,
            'date_to': date_to,
        }
    }
    
    return render(request, 'frontend/transactions_list.html', context)

@login_required
def set_language(request):
    """AJAX endpoint to set user's language preference"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        language = data.get('language', 'en')
        
        # Validate language
        if language not in ['en', 'ar']:
            return JsonResponse({'success': False, 'error': 'Invalid language'})
        
        # Save to session
        request.session['preferred_language'] = language
        
        return JsonResponse({
            'success': True,
            'language': language,
            'message': f'Language set to {language}'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def reports_dashboard(request):
    """Reports hub with statistics and report options"""
    from django.utils import timezone
    today = timezone.now().date()
    
    # Today's revenue from sales using F() expressions
    today_sales = Transaction.objects.filter(
        transaction_date=today,
        transaction_type='SALE'
    ).aggregate(
        total_revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        count=Count('id')
    )
    
    # Today's transaction count (all types)
    today_transactions = Transaction.objects.filter(
        transaction_date=today
    ).count()
    
    # Today's trips (completed and in-progress)
    today_trips = Trip.objects.filter(
        trip_date=today
    ).count()
    
    # Today's purchase orders (completed and in-progress)  
    today_pos = PurchaseOrder.objects.filter(
        po_date=today
    ).count()
    
    context = {
        'today_stats': {
            'revenue': today_sales['total_revenue'] or 0,
            'transactions': today_transactions,
            'trips': today_trips,
            'purchase_orders': today_pos,
        }
    }
    
    return render(request, 'frontend/reports_dashboard.html', context)

@login_required  
def comprehensive_report(request):
    """Comprehensive transaction report - all transaction types with filtering"""
    
    # Get filter parameters
    vessel_filter = request.GET.get('vessel')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    transaction_type_filter = request.GET.get('transaction_type')
    
    # Base queryset - all transactions
    transactions = Transaction.objects.select_related(
        'vessel', 'product', 'created_by', 'trip', 'purchase_order'
    ).order_by('-transaction_date', '-created_at')
    
    # Apply filters
    if vessel_filter:
        transactions = transactions.filter(vessel_id=vessel_filter)
        
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            transactions = transactions.filter(transaction_date__gte=date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            transactions = transactions.filter(transaction_date__lte=date_to_obj)
        except ValueError:
            pass
    else:
        # If no "to date", and we have "from date", make it a single day report
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                transactions = transactions.filter(transaction_date=date_from_obj)
            except ValueError:
                pass
    
    if transaction_type_filter:
        transactions = transactions.filter(transaction_type=transaction_type_filter)
    
    # Calculate summary statistics using F() expressions for calculated totals
    summary_stats = transactions.aggregate(
        total_transactions=Count('id'),
        total_sales_revenue=Sum(
            F('unit_price') * F('quantity'), 
            output_field=models.DecimalField(),
            filter=Q(transaction_type='SALE')
        ),
        total_purchase_cost=Sum(
            F('unit_price') * F('quantity'), 
            output_field=models.DecimalField(),
            filter=Q(transaction_type='SUPPLY')
        ),
        total_quantity=Sum('quantity'),
        sales_count=Count('id', filter=Q(transaction_type='SALE')),
        supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
        transfer_out_count=Count('id', filter=Q(transaction_type='TRANSFER_OUT')),
        transfer_in_count=Count('id', filter=Q(transaction_type='TRANSFER_IN')),
    )

    # Also update type_breakdown and vessel_breakdown:
    type_breakdown = []
    for type_code, type_display in Transaction.TRANSACTION_TYPES:
        type_stats = transactions.filter(transaction_type=type_code).aggregate(
            count=Count('id'),
            total_amount=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
            total_quantity=Sum('quantity')
        )
        if type_stats['count'] > 0:  # Only include types with data
            type_breakdown.append({
                'transaction_type': type_display,  # Use display name
                'transaction_code': type_code,     # Keep code for reference
                'count': type_stats['count'],
                'total_amount': type_stats['total_amount'],
                'total_quantity': type_stats['total_quantity']
            })

    vessel_breakdown = transactions.values(
        'vessel__name', 'vessel__name_ar'
    ).annotate(
        count=Count('id'),
        total_amount=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        total_quantity=Sum('quantity')
    ).order_by('vessel__name')

    product_breakdown = transactions.values(
        'product__name', 'product__item_id'
    ).annotate(
        count=Count('id'),
        total_amount=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        total_quantity=Sum('quantity')
    ).order_by('-total_quantity')[:10]
    
    # Get date range info
    date_range_info = None
    if date_from:
        if date_to:
            date_range_info = {
                'type': 'duration',
                'from': date_from,
                'to': date_to,
                'days': (datetime.strptime(date_to, '%Y-%m-%d').date() - 
                        datetime.strptime(date_from, '%Y-%m-%d').date()).days + 1
            }
        else:
            date_range_info = {
                'type': 'single_day',
                'date': date_from
            }
    
    # Get vessels for filter dropdown
    vessels = Vessel.objects.filter(active=True).order_by('name')
    
    # Limit transactions for display performance
    transactions_limited = transactions[:200]
    
    context = {
        'transactions': transactions_limited,
        'vessels': vessels,
        'transaction_types': Transaction.TRANSACTION_TYPES,
        'filters': {
            'vessel': vessel_filter,
            'date_from': date_from,
            'date_to': date_to,
            'transaction_type': transaction_type_filter,
        },
        'summary_stats': summary_stats,
        'type_breakdown': type_breakdown,
        'vessel_breakdown': vessel_breakdown,
        'product_breakdown': product_breakdown,
        'date_range_info': date_range_info,
        'total_shown': min(transactions.count(), 200),
        'total_available': transactions.count(),
    }
    
    return render(request, 'frontend/comprehensive_report.html', context)

@login_required
def daily_report(request):
    """Comprehensive daily operations report for a specific date"""
    from django.utils import timezone
    from datetime import timedelta
    from django.db import models  # CRITICAL: Import models here
    
    today = timezone.now().date()
    
    # Get selected date (default to today)
    selected_date_str = request.GET.get('date')
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()
    
    # Get previous day for comparison
    previous_date = selected_date - timedelta(days=1)
    
    # Get all active vessels
    vessels = Vessel.objects.filter(active=True).order_by('name')
    
    # === SUMMARY STATISTICS ===
    
    # Daily transactions for selected date
    daily_transactions = Transaction.objects.filter(transaction_date=selected_date)
    
    # Previous day transactions for comparison
    previous_transactions = Transaction.objects.filter(transaction_date=previous_date)
    
    # Summary stats for selected date - FIXED WITH PROPER output_field
    daily_stats = daily_transactions.aggregate(
        total_revenue=Sum(
            F('unit_price') * F('quantity'), 
            output_field=models.DecimalField(max_digits=15, decimal_places=3),
            filter=Q(transaction_type='SALE')
        ),
        total_purchase_cost=Sum(
            F('unit_price') * F('quantity'), 
            output_field=models.DecimalField(max_digits=15, decimal_places=3),
            filter=Q(transaction_type='SUPPLY')
        ),
        total_transactions=Count('id'),
        sales_count=Count('id', filter=Q(transaction_type='SALE')),
        supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
        transfer_count=Count('id', filter=Q(transaction_type__in=['TRANSFER_IN', 'TRANSFER_OUT'])),
        total_quantity=Sum('quantity'),
    )
    
    # Previous day stats for comparison - FIXED
    previous_stats = previous_transactions.aggregate(
        total_revenue=Sum(
            F('unit_price') * F('quantity'), 
            output_field=models.DecimalField(max_digits=15, decimal_places=3),
            filter=Q(transaction_type='SALE')
        ),
        total_transactions=Count('id'),
    )
    
    # Calculate profit margin
    daily_revenue = daily_stats['total_revenue'] or 0
    daily_costs = daily_stats['total_purchase_cost'] or 0
    daily_profit = daily_revenue - daily_costs
    profit_margin = (daily_profit / daily_revenue * 100) if daily_revenue > 0 else 0
    
    # Calculate change from previous day
    prev_revenue = previous_stats['total_revenue'] or 0
    revenue_change = ((daily_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0
    
    prev_transactions = previous_stats['total_transactions'] or 0
    transaction_change = daily_stats['total_transactions'] - prev_transactions
    
    # === VESSEL BREAKDOWN ===
    
    vessel_breakdown = []
    for vessel in vessels:
        vessel_transactions = daily_transactions.filter(vessel=vessel)
        
        # FIXED vessel stats with proper output_field
        vessel_stats = vessel_transactions.aggregate(
            revenue=Sum(
                F('unit_price') * F('quantity'), 
                output_field=models.DecimalField(max_digits=15, decimal_places=3),
                filter=Q(transaction_type='SALE')
            ),
            costs=Sum(
                F('unit_price') * F('quantity'), 
                output_field=models.DecimalField(max_digits=15, decimal_places=3),
                filter=Q(transaction_type='SUPPLY')
            ),
            sales_count=Count('id', filter=Q(transaction_type='SALE')),
            supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
            transfer_out_count=Count('id', filter=Q(transaction_type='TRANSFER_OUT')),
            transfer_in_count=Count('id', filter=Q(transaction_type='TRANSFER_IN')),
            total_quantity=Sum('quantity'),
        )
        
        # Get trips for this vessel on this date
        vessel_trips = Trip.objects.filter(
            vessel=vessel,
            trip_date=selected_date
        ).values('trip_number', 'is_completed', 'passenger_count')
        
        # Get POs for this vessel on this date
        vessel_pos = PurchaseOrder.objects.filter(
            vessel=vessel,
            po_date=selected_date
        ).values('po_number', 'is_completed')
        
        # Calculate vessel profit
        vessel_revenue = vessel_stats['revenue'] or 0
        vessel_costs = vessel_stats['costs'] or 0
        vessel_profit = vessel_revenue - vessel_costs
        
        vessel_breakdown.append({
            'vessel': vessel,
            'stats': vessel_stats,
            'profit': vessel_profit,
            'trips': list(vessel_trips),
            'pos': list(vessel_pos),
        })
    
    # === INVENTORY CHANGES ===
    
    # Products that had inventory changes today - FIXED
    inventory_changes = daily_transactions.values(
        'product__name', 'product__item_id', 'vessel__name', 'vessel__name_ar'
    ).annotate(
        total_in=Sum('quantity', filter=Q(transaction_type__in=['SUPPLY', 'TRANSFER_IN'])),
        total_out=Sum('quantity', filter=Q(transaction_type__in=['SALE', 'TRANSFER_OUT'])),
        net_change=Sum(
            Case(
                When(transaction_type__in=['SUPPLY', 'TRANSFER_IN'], then=F('quantity')),
                When(transaction_type__in=['SALE', 'TRANSFER_OUT'], then=-F('quantity')),
                default=0,
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            )
        )
    ).filter(
        Q(total_in__gt=0) | Q(total_out__gt=0)
    ).order_by('-total_out')[:20]  # Top 20 most active products
    
    # === BUSINESS INSIGHTS ===
    
    # Best performing vessel by revenue
    best_vessel = max(vessel_breakdown, key=lambda v: v['stats']['revenue'] or 0) if vessel_breakdown else None
    
    # Most active vessel by transaction count
    most_active_vessel = max(vessel_breakdown, key=lambda v: (v['stats']['sales_count'] or 0) + (v['stats']['supply_count'] or 0)) if vessel_breakdown else None
    
    # Low stock alerts (products with less than 10 units total across all vessels)
    low_stock_products = []
    for product in Product.objects.filter(active=True):
        total_stock = InventoryLot.objects.filter(
            product=product,
            remaining_quantity__gt=0
        ).aggregate(total=Sum('remaining_quantity'))['total'] or 0
        
        if total_stock < 10:
            low_stock_products.append({
                'product': product,
                'total_stock': total_stock
            })
    
    # Unusual activity (vessels with unusually high transaction count compared to their average)
    unusual_activity = []
    for vessel_data in vessel_breakdown:
        vessel = vessel_data['vessel']
        today_count = (vessel_data['stats']['sales_count'] or 0) + (vessel_data['stats']['supply_count'] or 0)
        
        # Get average transaction count for this vessel over last 30 days
        thirty_days_ago = selected_date - timedelta(days=30)
        avg_transactions = Transaction.objects.filter(
            vessel=vessel,
            transaction_date__gte=thirty_days_ago,
            transaction_date__lt=selected_date
        ).values('transaction_date').annotate(
            daily_count=Count('id')
        ).aggregate(avg=Avg('daily_count'))['avg'] or 0
        
        # If today's count is 50% higher than average, flag it
        if avg_transactions > 0 and today_count > avg_transactions * 1.5:
            unusual_activity.append({
                'vessel': vessel,
                'today_count': today_count,
                'avg_count': round(avg_transactions, 1),
                'percentage_increase': round((today_count - avg_transactions) / avg_transactions * 100, 1)
            })
    
    # === ALL TRIPS AND POS FOR THE DAY ===
    
    # All trips on this date
    daily_trips = Trip.objects.filter(
        trip_date=selected_date
    ).select_related('vessel').order_by('vessel__name', 'trip_number')
    
    # All POs on this date
    daily_pos = PurchaseOrder.objects.filter(
        po_date=selected_date
    ).select_related('vessel').order_by('vessel__name', 'po_number')
    
    context = {
        'selected_date': selected_date,
        'previous_date': previous_date,
        'daily_stats': daily_stats,
        'daily_profit': daily_profit,
        'profit_margin': profit_margin,
        'revenue_change': revenue_change,
        'transaction_change': transaction_change,
        'vessel_breakdown': vessel_breakdown,
        'inventory_changes': inventory_changes,
        'best_vessel': best_vessel,
        'most_active_vessel': most_active_vessel,
        'low_stock_products': low_stock_products[:10],  # Limit to top 10
        'unusual_activity': unusual_activity,
        'daily_trips': daily_trips,
        'daily_pos': daily_pos,
        'vessels': vessels,
    }
    
    return render(request, 'frontend/daily_report.html', context)

@login_required
def monthly_report(request):
    """Comprehensive monthly operations and financial report"""
    from django.utils import timezone
    from datetime import datetime, timedelta
    import calendar
    
    # Get selected month/year (default to current month)
    selected_month = request.GET.get('month')
    selected_year = request.GET.get('year')
    
    today = timezone.now().date()
    
    if selected_month and selected_year:
        try:
            month = int(selected_month)
            year = int(selected_year)
        except ValueError:
            month = today.month
            year = today.year
    else:
        month = today.month
        year = today.year
    
    # Generate year range from system start to future
    SYSTEM_START_YEAR = 2023  # Change this to when your system started
    current_year = timezone.now().year
    year_range = range(SYSTEM_START_YEAR, current_year + 1)  # From start year to current+2
    
    # Calculate month date range
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    
    # Previous month for comparison
    if month == 1:
        prev_month = 12
        prev_year = year - 1
    else:
        prev_month = month - 1
        prev_year = year
    
    prev_first_day = date(prev_year, prev_month, 1)
    if prev_month == 12:
        prev_last_day = date(prev_year + 1, 1, 1) - timedelta(days=1)
    else:
        prev_last_day = date(prev_year, prev_month + 1, 1) - timedelta(days=1)
    
    # === MONTHLY STATISTICS ===
    
    # Current month transactions
    monthly_transactions = Transaction.objects.filter(
        transaction_date__gte=first_day,
        transaction_date__lte=last_day
    )
    
    # Previous month transactions for comparison
    prev_monthly_transactions = Transaction.objects.filter(
        transaction_date__gte=prev_first_day,
        transaction_date__lte=prev_last_day
    )
    
    # Monthly summary stats
    monthly_stats = monthly_transactions.aggregate(
        total_revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
        total_costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
        total_transactions=Count('id'),
        sales_count=Count('id', filter=Q(transaction_type='SALE')),
        supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
        transfer_count=Count('id', filter=Q(transaction_type__in=['TRANSFER_IN', 'TRANSFER_OUT'])),
        total_quantity=Sum('quantity'),
    )
    
    # Previous month stats for comparison
    prev_monthly_stats = prev_monthly_transactions.aggregate(
        total_revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
        total_transactions=Count('id'),
    )
    
    # Calculate changes from previous month
    monthly_revenue = monthly_stats['total_revenue'] or 0
    monthly_costs = monthly_stats['total_costs'] or 0
    monthly_profit = monthly_revenue - monthly_costs
    
    prev_revenue = prev_monthly_stats['total_revenue'] or 0
    revenue_change = ((monthly_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0
    
    # === DAILY BREAKDOWN ===
    
    # Get daily stats for the month
    daily_breakdown = []
    current_date = first_day
    
    while current_date <= last_day:
        daily_transactions = monthly_transactions.filter(transaction_date=current_date)
        daily_stats = daily_transactions.aggregate(
            revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
            costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
            transactions=Count('id'),
            sales=Count('id', filter=Q(transaction_type='SALE')),
            supplies=Count('id', filter=Q(transaction_type='SUPPLY')),
        )
        
        daily_revenue = daily_stats['revenue'] or 0
        daily_costs = daily_stats['costs'] or 0
        daily_profit = daily_revenue - daily_costs
        
        daily_breakdown.append({
            'date': current_date,
            'day_name': current_date.strftime('%A'),
            'revenue': daily_revenue,
            'costs': daily_costs,
            'profit': daily_profit,
            'transactions': daily_stats['transactions'],
            'sales': daily_stats['sales'],
            'supplies': daily_stats['supplies'],
        })
        
        current_date += timedelta(days=1)
    
    # === VESSEL PERFORMANCE ===
    
    vessels = Vessel.objects.filter(active=True)
    vessel_performance = []
    
    for vessel in vessels:
        vessel_transactions = monthly_transactions.filter(vessel=vessel)
        vessel_stats = vessel_transactions.aggregate(
            revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
            costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
            sales_count=Count('id', filter=Q(transaction_type='SALE')),
            supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
            transfer_out_count=Count('id', filter=Q(transaction_type='TRANSFER_OUT')),
            transfer_in_count=Count('id', filter=Q(transaction_type='TRANSFER_IN')),
        )
        
        vessel_revenue = vessel_stats['revenue'] or 0
        vessel_costs = vessel_stats['costs'] or 0
        vessel_profit = vessel_revenue - vessel_costs
        
        # Get trip and PO counts for the month
        vessel_trips = Trip.objects.filter(
            vessel=vessel,
            trip_date__gte=first_day,
            trip_date__lte=last_day
        ).count()
        
        vessel_pos = PurchaseOrder.objects.filter(
            vessel=vessel,
            po_date__gte=first_day,
            po_date__lte=last_day
        ).count()
        
        vessel_performance.append({
            'vessel': vessel,
            'revenue': vessel_revenue,
            'costs': vessel_costs,
            'profit': vessel_profit,
            'sales_count': vessel_stats['sales_count'],
            'supply_count': vessel_stats['supply_count'],
            'transfer_out_count': vessel_stats['transfer_out_count'],
            'transfer_in_count': vessel_stats['transfer_in_count'],
            'trips_count': vessel_trips,
            'pos_count': vessel_pos,
        })
    
    # Sort by revenue descending
    vessel_performance.sort(key=lambda x: x['revenue'], reverse=True)
    
    # === TOP PRODUCTS ===
    
    top_products = monthly_transactions.values(
        'product__name', 'product__item_id'
    ).annotate(
        total_quantity_sold=Sum('quantity', filter=Q(transaction_type='SALE')),
        total_revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
        total_supplied=Sum('quantity', filter=Q(transaction_type='SUPPLY')),
        transaction_count=Count('id')
    ).filter(
        total_quantity_sold__gt=0
    ).order_by('-total_revenue')[:10]
    
    # === MONTH-OVER-MONTH TRENDS ===
    
    # Get last 12 months data for trends
    trend_months = []
    for i in range(11, -1, -1):  # 12 months including current
        trend_date = date(year, month, 1) - timedelta(days=i*30)  # Approximate
        trend_first = date(trend_date.year, trend_date.month, 1)
        
        if trend_date.month == 12:
            trend_last = date(trend_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            trend_last = date(trend_date.year, trend_date.month + 1, 1) - timedelta(days=1)
        
        trend_transactions = Transaction.objects.filter(
            transaction_date__gte=trend_first,
            transaction_date__lte=trend_last
        )
        
        trend_stats = trend_transactions.aggregate(
            revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
            costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
        )
        
        trend_revenue = trend_stats['revenue'] or 0
        trend_costs = trend_stats['costs'] or 0
        
        trend_months.append({
            'month': trend_date.strftime('%B'),
            'year': trend_date.year,
            'revenue': trend_revenue,
            'costs': trend_costs,
            'profit': trend_revenue - trend_costs,
        })
    
    # Get month name
    month_name = calendar.month_name[month]
    profit_margin = ((monthly_profit / monthly_revenue * 100) if monthly_revenue > 0 else 0)
    
    context = {
        'selected_month': month,
        'selected_year': year,
        'month_name': month_name,
        'first_day': first_day,
        'last_day': last_day,
        'monthly_stats': monthly_stats,
        'monthly_profit': monthly_profit,
        'revenue_change': revenue_change,
        'daily_breakdown': daily_breakdown,
        'vessel_performance': vessel_performance,
        'top_products': top_products,
        'trend_months': trend_months,
        'vessels': vessels,
        'profit_margin': profit_margin,
        'year_range': year_range,  # Added this line
    }
    
    return render(request, 'frontend/monthly_report.html', context)

@login_required
def analytics_report(request):
    """Advanced business analytics and KPI dashboard"""
    from django.utils import timezone
    from datetime import datetime, timedelta
    from django.db.models import Avg, Max, Min, Variance
    import calendar
    
    today = timezone.now().date()
    
    # Date ranges for analysis
    last_30_days = today - timedelta(days=30)
    last_90_days = today - timedelta(days=90)
    last_year = today - timedelta(days=365)
    
    # === KEY PERFORMANCE INDICATORS ===
    
    # Revenue KPIs (last 30 days)
    revenue_30_days = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date__gte=last_30_days
    ).aggregate(
        total_revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        avg_daily_revenue=Avg(F('unit_price') * F('quantity')),
        transaction_count=Count('id')
    )
    
    # Average revenue per transaction
    avg_revenue_per_transaction = (revenue_30_days['total_revenue'] or 0) / max(revenue_30_days['transaction_count'] or 1, 1)
    
    # === VESSEL ANALYTICS ===
    
    vessel_analytics = []
    for vessel in Vessel.objects.filter(active=True):
        # Last 30 days performance
        vessel_transactions = Transaction.objects.filter(
            vessel=vessel,
            transaction_date__gte=last_30_days
        )
        
        vessel_stats = vessel_transactions.aggregate(
            revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
            costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
            sales_count=Count('id', filter=Q(transaction_type='SALE')),
            avg_sale_amount=Avg(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
        )
        
        # Calculate utilization (trips/total possible trips)
        vessel_trips = Trip.objects.filter(
            vessel=vessel,
            trip_date__gte=last_30_days
        ).count()
        
        # Efficiency: revenue per trip
        revenue_per_trip = (vessel_stats['revenue'] or 0) / max(vessel_trips, 1)
        
        # Profit margin
        vessel_revenue = vessel_stats['revenue'] or 0
        vessel_costs = vessel_stats['costs'] or 0
        profit_margin = ((vessel_revenue - vessel_costs) / vessel_revenue * 100) if vessel_revenue > 0 else 0
        
        vessel_analytics.append({
            'vessel': vessel,
            'revenue': vessel_revenue,
            'costs': vessel_costs,
            'profit_margin': profit_margin,
            'trips_count': vessel_trips,
            'revenue_per_trip': revenue_per_trip,
            'avg_sale_amount': vessel_stats['avg_sale_amount'] or 0,
            'sales_count': vessel_stats['sales_count'] or 0,
        })
    
    # === PRODUCT ANALYTICS ===
    
    # Best performing products (last 90 days)
    top_products = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date__gte=last_90_days
    ).values(
        'product__name', 'product__item_id', 'product__category__name'
    ).annotate(
        total_revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        total_quantity=Sum('quantity'),
        transaction_count=Count('id'),
        avg_price=Avg('unit_price'),
    ).order_by('-total_revenue')[:15]
    
    # Inventory turnover analysis
    inventory_analysis = []
    for product in Product.objects.filter(active=True)[:20]:  # Top 20 products
        # Total stock
        total_stock = InventoryLot.objects.filter(
            product=product,
            remaining_quantity__gt=0
        ).aggregate(total=Sum('remaining_quantity'))['total'] or 0
        
        # Sales in last 30 days
        sales_30_days = Transaction.objects.filter(
            product=product,
            transaction_type='SALE',
            transaction_date__gte=last_30_days
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        # Calculate turnover rate (monthly sales / current stock)
        turnover_rate = (sales_30_days / max(total_stock, 1)) * 100 if total_stock > 0 else 0
        
        # Days of stock remaining
        daily_avg_sales = sales_30_days / 30
        days_remaining = total_stock / max(daily_avg_sales, 0.1)
        
        inventory_analysis.append({
            'product': product,
            'total_stock': total_stock,
            'sales_30_days': sales_30_days,
            'turnover_rate': turnover_rate,
            'days_remaining': min(days_remaining, 999),  # Cap at 999 days
        })
    
    # Sort by turnover rate
    inventory_analysis.sort(key=lambda x: x['turnover_rate'], reverse=True)
    
    # === SEASONAL TRENDS ===
    
    # Monthly revenue for last 12 months
    monthly_trends = []
    for i in range(11, -1, -1):
        trend_date = today - timedelta(days=i*30)
        month_start = date(trend_date.year, trend_date.month, 1)
        
        if trend_date.month == 12:
            month_end = date(trend_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(trend_date.year, trend_date.month + 1, 1) - timedelta(days=1)
        
        monthly_revenue = Transaction.objects.filter(
            transaction_type='SALE',
            transaction_date__gte=month_start,
            transaction_date__lte=month_end
        ).aggregate(
            revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
        )['revenue'] or 0
        
        monthly_trends.append({
            'month': calendar.month_name[trend_date.month],
            'year': trend_date.year,
            'revenue': monthly_revenue,
        })
    
    # === CUSTOMER ANALYTICS ===
    
    # Trip-based passenger analytics
    passenger_analytics = Trip.objects.filter(
        trip_date__gte=last_90_days,
        is_completed=True
    ).aggregate(
        total_passengers=Sum('passenger_count'),
        avg_passengers_per_trip=Avg('passenger_count'),
        total_trips=Count('id')
    )
    
    # Revenue per passenger
    total_revenue_90_days = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date__gte=last_90_days
    ).aggregate(revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()))['revenue'] or 0
    
    revenue_per_passenger = total_revenue_90_days / max(passenger_analytics['total_passengers'] or 1, 1)
    
    # === BUSINESS INSIGHTS ===
    
    # Growth rate (this month vs last month)
    this_month_start = date(today.year, today.month, 1)
    if today.month == 1:
        last_month_start = date(today.year - 1, 12, 1)
        last_month_end = date(today.year, 1, 1) - timedelta(days=1)
    else:
        last_month_start = date(today.year, today.month - 1, 1)
        last_month_end = date(today.year, today.month, 1) - timedelta(days=1)
    
    this_month_revenue = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date__gte=this_month_start
    ).aggregate(revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()))['revenue'] or 0
    
    last_month_revenue = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date__gte=last_month_start,
        transaction_date__lte=last_month_end
    ).aggregate(revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()))['revenue'] or 0
    
    growth_rate = ((this_month_revenue - last_month_revenue) / max(last_month_revenue, 1) * 100) if last_month_revenue > 0 else 0
    
    # Operational efficiency
    total_transactions_30_days = Transaction.objects.filter(
        transaction_date__gte=last_30_days
    ).count()
    
    efficiency_score = (total_transactions_30_days / 30) * 10  # Arbitrary scoring
    
    context = {
        'revenue_30_days': revenue_30_days,
        'avg_revenue_per_transaction': avg_revenue_per_transaction,
        'vessel_analytics': vessel_analytics,
        'top_products': top_products,
        'inventory_analysis': inventory_analysis[:10],  # Top 10
        'monthly_trends': monthly_trends,
        'passenger_analytics': passenger_analytics,
        'revenue_per_passenger': revenue_per_passenger,
        'growth_rate': growth_rate,
        'efficiency_score': min(efficiency_score, 100),  # Cap at 100
        'last_30_days': last_30_days,
        'last_90_days': last_90_days,
        'today': today,
    }
    
    return render(request, 'frontend/analytics_report.html', context)

@login_required
def export_inventory(request):
    """Export inventory data to Excel or PDF"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')  # 'excel' or 'pdf'
        vessel_id = data.get('vessel_id')
        
        # Get vessel and inventory data (similar to inventory_data_ajax)
        vessel = Vessel.objects.get(id=vessel_id, active=True)
        
        # Get inventory data (reuse logic from inventory_data_ajax)
        available_lots = InventoryLot.objects.filter(
            vessel=vessel,
            remaining_quantity__gt=0,
            product__active=True
        ).select_related('product')
        
        inventory_summary = available_lots.values(
            'product__id', 'product__name', 'product__item_id', 
            'product__barcode', 'product__is_duty_free'
        ).annotate(
            total_quantity=Sum('remaining_quantity')
        ).order_by('product__item_id')
        
        # Prepare data for export
        headers = ['Product Name', 'Item ID', 'Barcode', 'Stock Quantity', 'Current Cost (JOD)', 'Total Value (JOD)', 'Status']
        
        data_rows = []
        for item in inventory_summary:
            product_id = item['product__id']
            total_qty = item['total_quantity']
            
            # Get current cost (oldest lot)
            lots = InventoryLot.objects.filter(
                vessel=vessel,
                product_id=product_id,
                remaining_quantity__gt=0
            ).order_by('purchase_date', 'created_at')
            
            current_cost = lots.first().purchase_price if lots.exists() else 0
            total_value = sum(lot.remaining_quantity * lot.purchase_price for lot in lots)
            
            # Determine status
            if total_qty == 0:
                status = 'Out of Stock'
            elif total_qty <= 10:
                status = 'Low Stock'
            else:
                status = 'Good Stock'
                
            data_rows.append([
                item['product__name'],
                item['product__item_id'],
                item['product__barcode'] or 'N/A',
                total_qty,
                f"{current_cost:.3f}",
                f"{total_value:.3f}",
                status
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"inventory_{vessel.name}_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Vessel': vessel.name,
            'Total Products': len(data_rows),
            'Generated By': request.user.username
        }
        
        if export_format == 'excel':
            exporter = ExcelExporter()
            exporter.add_title(f"{vessel.name} Inventory Report", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_headers(headers)
            exporter.add_data_rows(data_rows)
            
            return exporter.get_response(f"{filename_base}.xlsx")
            
        else:  # PDF
            exporter = PDFExporter()
            exporter.add_title(f"{vessel.name} Inventory Report", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_table(headers, data_rows)
            
            return exporter.get_response(f"{filename_base}.pdf")
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def export_transactions(request):
    """Export transaction data to Excel or PDF"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get filter parameters
        vessel_filter = data.get('vessel_filter')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        transaction_type_filter = data.get('transaction_type_filter')
        
        # Build query (similar to comprehensive_report view)
        transactions = Transaction.objects.select_related(
            'vessel', 'product', 'created_by', 'trip', 'purchase_order'
        ).order_by('-transaction_date', '-created_at')
        
        # Apply filters
        if vessel_filter:
            transactions = transactions.filter(vessel_id=vessel_filter)
        if date_from:
            transactions = transactions.filter(transaction_date__gte=date_from)
        if date_to:
            transactions = transactions.filter(transaction_date__lte=date_to)
        if transaction_type_filter:
            transactions = transactions.filter(transaction_type=transaction_type_filter)
        
        # Prepare data
        headers = ['Date', 'Type', 'Vessel', 'Product', 'Quantity', 'Unit Price (JOD)', 'Total Amount (JOD)', 'Reference', 'Created By']
        
        data_rows = []
        for transaction in transactions[:1000]:  # Limit to 1000 rows for performance
            reference = ""
            if transaction.trip:
                reference = f"Trip: {transaction.trip.trip_number}"
            elif transaction.purchase_order:
                reference = f"PO: {transaction.purchase_order.po_number}"
            elif transaction.transfer_to_vessel:
                reference = f"To: {transaction.transfer_to_vessel.name}"
            
            data_rows.append([
                transaction.transaction_date.strftime('%d/%m/%Y'),
                transaction.get_transaction_type_display(),
                transaction.vessel.name,
                transaction.product.name,
                transaction.quantity,
                f"{transaction.unit_price:.3f}",
                f"{transaction.total_amount:.3f}",
                reference,
                transaction.created_by.username if transaction.created_by else 'System'
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"transactions_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Total Transactions': len(data_rows),
            'Filters Applied': 'Yes' if any([vessel_filter, date_from, date_to, transaction_type_filter]) else 'No',
            'Generated By': request.user.username
        }
        
        if date_from:
            metadata['Date From'] = date_from
        if date_to:
            metadata['Date To'] = date_to
        
        if export_format == 'excel':
            exporter = ExcelExporter()
            exporter.add_title("Transaction Report", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_headers(headers)
            exporter.add_data_rows(data_rows)
            
            return exporter.get_response(f"{filename_base}.xlsx")
            
        else:  # PDF
            exporter = PDFExporter()
            exporter.add_title("Transaction Report", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_table(headers, data_rows)
            
            return exporter.get_response(f"{filename_base}.pdf")
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def export_trips(request):
    """Export trip reports to Excel or PDF"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get filter parameters
        vessel_filter = data.get('vessel_filter')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        status_filter = data.get('status_filter')
        
        # Build query
        trips = Trip.objects.select_related('vessel', 'created_by')
        
        if vessel_filter:
            trips = trips.filter(vessel_id=vessel_filter)
        if date_from:
            trips = trips.filter(trip_date__gte=date_from)
        if date_to:
            trips = trips.filter(trip_date__lte=date_to)
        if status_filter == 'completed':
            trips = trips.filter(is_completed=True)
        elif status_filter == 'in_progress':
            trips = trips.filter(is_completed=False)
        
        trips = trips.order_by('-trip_date', '-created_at')
        
        # Prepare data
        headers = ['Trip Number', 'Vessel', 'Trip Date', 'Passengers', 'Revenue (JOD)', 'Items Sold', 'Status', 'Created By', 'Revenue per Passenger']
        
        data_rows = []
        for trip in trips:
            revenue = trip.total_revenue
            items_sold = trip.total_items_sold
            revenue_per_passenger = revenue / trip.passenger_count if trip.passenger_count > 0 else 0
            
            data_rows.append([
                trip.trip_number,
                trip.vessel.name,
                trip.trip_date.strftime('%d/%m/%Y'),
                trip.passenger_count,
                f"{revenue:.3f}",
                items_sold,
                'Completed' if trip.is_completed else 'In Progress',
                trip.created_by.username if trip.created_by else 'System',
                f"{revenue_per_passenger:.3f}"
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"trip_reports_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Total Trips': len(data_rows),
            'Generated By': request.user.username
        }
        
        if vessel_filter:
            vessel = Vessel.objects.get(id=vessel_filter)
            metadata['Vessel Filter'] = vessel.name
        if date_from:
            metadata['Date From'] = date_from
        if date_to:
            metadata['Date To'] = date_to
        
        if export_format == 'excel':
            exporter = ExcelExporter()
            exporter.add_title("Trip Reports", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_headers(headers)
            exporter.add_data_rows(data_rows)
            
            return exporter.get_response(f"{filename_base}.xlsx")
            
        else:  # PDF
            exporter = PDFExporter()
            exporter.add_title("Trip Reports", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_table(headers, data_rows)
            
            return exporter.get_response(f"{filename_base}.pdf")
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def export_purchase_orders(request):
    """Export purchase order reports to Excel or PDF"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get filter parameters
        vessel_filter = data.get('vessel_filter')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        status_filter = data.get('status_filter')
        
        # Build query
        purchase_orders = PurchaseOrder.objects.select_related('vessel', 'created_by')
        
        if vessel_filter:
            purchase_orders = purchase_orders.filter(vessel_id=vessel_filter)
        if date_from:
            purchase_orders = purchase_orders.filter(po_date__gte=date_from)
        if date_to:
            purchase_orders = purchase_orders.filter(po_date__lte=date_to)
        if status_filter == 'completed':
            purchase_orders = purchase_orders.filter(is_completed=True)
        elif status_filter == 'in_progress':
            purchase_orders = purchase_orders.filter(is_completed=False)
        
        purchase_orders = purchase_orders.order_by('-po_date', '-created_at')
        
        # Prepare data
        headers = ['PO Number', 'Vessel', 'PO Date', 'Total Cost (JOD)', 'Items Count', 'Status', 'Created By', 'Average Cost per Item']
        
        data_rows = []
        for po in purchase_orders:
            total_cost = po.total_cost
            items_count = po.transaction_count
            avg_cost_per_item = total_cost / items_count if items_count > 0 else 0
            
            data_rows.append([
                po.po_number,
                po.vessel.name,
                po.po_date.strftime('%d/%m/%Y'),
                f"{total_cost:.3f}",
                items_count,
                'Completed' if po.is_completed else 'In Progress',
                po.created_by.username if po.created_by else 'System',
                f"{avg_cost_per_item:.3f}"
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"purchase_order_reports_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Total Purchase Orders': len(data_rows),
            'Generated By': request.user.username
        }
        
        if vessel_filter:
            vessel = Vessel.objects.get(id=vessel_filter)
            metadata['Vessel Filter'] = vessel.name
        if date_from:
            metadata['Date From'] = date_from
        if date_to:
            metadata['Date To'] = date_to
        
        if export_format == 'excel':
            exporter = ExcelExporter()
            exporter.add_title("Purchase Order Reports", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_headers(headers)
            exporter.add_data_rows(data_rows)
            
            return exporter.get_response(f"{filename_base}.xlsx")
            
        else:  # PDF
            exporter = PDFExporter()
            exporter.add_title("Purchase Order Reports", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_table(headers, data_rows)
            
            return exporter.get_response(f"{filename_base}.pdf")
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def export_monthly_report(request):
    """Export monthly report to Excel or PDF"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        selected_month = int(data.get('month', datetime.now().month))
        selected_year = int(data.get('year', datetime.now().year))
        
        # Calculate month date range
        from datetime import date, timedelta
        import calendar
        
        first_day = date(selected_year, selected_month, 1)
        if selected_month == 12:
            last_day = date(selected_year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(selected_year, selected_month + 1, 1) - timedelta(days=1)
        
        # Get monthly transactions
        monthly_transactions = Transaction.objects.filter(
            transaction_date__gte=first_day,
            transaction_date__lte=last_day
        )
        
        # Calculate stats using F() expressions
        monthly_stats = monthly_transactions.aggregate(
            total_revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
            total_costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
            total_transactions=Count('id'),
            sales_count=Count('id', filter=Q(transaction_type='SALE')),
            supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
        )
        
        monthly_revenue = monthly_stats['total_revenue'] or 0
        monthly_costs = monthly_stats['total_costs'] or 0
        monthly_profit = monthly_revenue - monthly_costs
        
        # Get vessel performance
        vessels = Vessel.objects.filter(active=True)
        vessel_performance = []
        
        for vessel in vessels:
            vessel_transactions = monthly_transactions.filter(vessel=vessel)
            vessel_stats = vessel_transactions.aggregate(
                revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
                costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
                sales_count=Count('id', filter=Q(transaction_type='SALE')),
                supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
            )
            
            vessel_revenue = vessel_stats['revenue'] or 0
            vessel_costs = vessel_stats['costs'] or 0
            vessel_profit = vessel_revenue - vessel_costs
            
            vessel_performance.append([
                vessel.name,
                f"{vessel_revenue:.3f}",
                f"{vessel_costs:.3f}",
                f"{vessel_profit:.3f}",
                vessel_stats['sales_count'] or 0,
                vessel_stats['supply_count'] or 0
            ])
        
        # Generate filename
        month_name = calendar.month_name[selected_month]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"monthly_report_{month_name}_{selected_year}_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Report Month': f"{month_name} {selected_year}",
            'Total Revenue (JOD)': f"{monthly_revenue:.3f}",
            'Total Costs (JOD)': f"{monthly_costs:.3f}",
            'Total Profit (JOD)': f"{monthly_profit:.3f}",
            'Total Transactions': monthly_stats['total_transactions'] or 0,
            'Generated By': request.user.username
        }
        
        if export_format == 'excel':
            exporter = ExcelExporter()
            exporter.add_title(f"Monthly Report - {month_name} {selected_year}", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            
            # Add vessel performance table
            headers = ['Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit (JOD)', 'Sales Count', 'Supply Count']
            exporter.add_headers(headers)
            exporter.add_data_rows(vessel_performance)
            
            return exporter.get_response(f"{filename_base}.xlsx")
            
        else:  # PDF
            exporter = PDFExporter()
            exporter.add_title(f"Monthly Report - {month_name} {selected_year}", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            
            headers = ['Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit (JOD)', 'Sales Count', 'Supply Count']
            exporter.add_table(headers, vessel_performance)
            
            return exporter.get_response(f"{filename_base}.pdf")
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def export_daily_report(request):
    """Export daily report to Excel or PDF"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        selected_date_str = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        from datetime import datetime
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        
        # Get daily transactions
        daily_transactions = Transaction.objects.filter(transaction_date=selected_date)
        
        # Calculate daily stats
        daily_stats = daily_transactions.aggregate(
            total_revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
            total_costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
            total_transactions=Count('id'),
            sales_count=Count('id', filter=Q(transaction_type='SALE')),
            supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
        )
        
        daily_revenue = daily_stats['total_revenue'] or 0
        daily_costs = daily_stats['total_costs'] or 0
        daily_profit = daily_revenue - daily_costs
        
        # Get vessel breakdown
        vessels = Vessel.objects.filter(active=True)
        vessel_breakdown = []
        
        for vessel in vessels:
            vessel_transactions = daily_transactions.filter(vessel=vessel)
            vessel_stats = vessel_transactions.aggregate(
                revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
                costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
                sales_count=Count('id', filter=Q(transaction_type='SALE')),
                supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
            )
            
            vessel_revenue = vessel_stats['revenue'] or 0
            vessel_costs = vessel_stats['costs'] or 0
            vessel_profit = vessel_revenue - vessel_costs
            
            vessel_breakdown.append([
                vessel.name,
                f"{vessel_revenue:.3f}",
                f"{vessel_costs:.3f}",
                f"{vessel_profit:.3f}",
                vessel_stats['sales_count'] or 0,
                vessel_stats['supply_count'] or 0
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"daily_report_{selected_date.strftime('%Y%m%d')}_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Report Date': selected_date.strftime('%d/%m/%Y'),
            'Total Revenue (JOD)': f"{daily_revenue:.3f}",
            'Total Costs (JOD)': f"{daily_costs:.3f}",
            'Total Profit (JOD)': f"{daily_profit:.3f}",
            'Total Transactions': daily_stats['total_transactions'] or 0,
            'Generated By': request.user.username
        }
        
        if export_format == 'excel':
            exporter = ExcelExporter()
            exporter.add_title(f"Daily Report - {selected_date.strftime('%d/%m/%Y')}", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            
            headers = ['Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit (JOD)', 'Sales Count', 'Supply Count']
            exporter.add_headers(headers)
            exporter.add_data_rows(vessel_breakdown)
            
            return exporter.get_response(f"{filename_base}.xlsx")
            
        else:  # PDF
            exporter = PDFExporter()
            exporter.add_title(f"Daily Report - {selected_date.strftime('%d/%m/%Y')}", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            
            headers = ['Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit (JOD)', 'Sales Count', 'Supply Count']
            exporter.add_table(headers, vessel_breakdown)
            
            return exporter.get_response(f"{filename_base}.pdf")
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def export_analytics_report(request):
    """Export analytics report to Excel or PDF"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        from django.utils import timezone
        from datetime import timedelta
        
        today = timezone.now().date()
        last_30_days = today - timedelta(days=30)
        last_90_days = today - timedelta(days=90)
        
        # Get revenue KPIs (last 30 days)
        revenue_30_days = Transaction.objects.filter(
            transaction_type='SALE',
            transaction_date__gte=last_30_days
        ).aggregate(
            total_revenue=Sum(F('unit_price') * F('quantity')),
            transaction_count=Count('id')
        )
        
        # Get vessel analytics
        vessel_analytics = []
        for vessel in Vessel.objects.filter(active=True):
            vessel_transactions = Transaction.objects.filter(
                vessel=vessel,
                transaction_date__gte=last_30_days
            )
            
            vessel_stats = vessel_transactions.aggregate(
                revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
                costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
                sales_count=Count('id', filter=Q(transaction_type='SALE')),
            )
            
            vessel_revenue = vessel_stats['revenue'] or 0
            vessel_costs = vessel_stats['costs'] or 0
            profit_margin = ((vessel_revenue - vessel_costs) / vessel_revenue * 100) if vessel_revenue > 0 else 0
            
            vessel_analytics.append([
                vessel.name,
                f"{vessel_revenue:.3f}",
                f"{vessel_costs:.3f}",
                f"{profit_margin:.1f}%",
                vessel_stats['sales_count'] or 0
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"analytics_report_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Analysis Period': 'Last 30 Days',
            'Total Revenue (JOD)': f"{revenue_30_days['total_revenue'] or 0:.3f}",
            'Total Transactions': revenue_30_days['transaction_count'] or 0,
            'Generated By': request.user.username
        }
        
        if export_format == 'excel':
            exporter = ExcelExporter()
            exporter.add_title("Analytics Report", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            
            headers = ['Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit Margin (%)', 'Sales Count']
            exporter.add_headers(headers)
            exporter.add_data_rows(vessel_analytics)
            
            return exporter.get_response(f"{filename_base}.xlsx")
            
        else:  # PDF
            exporter = PDFExporter()
            exporter.add_title("Analytics Report", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            
            headers = ['Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit Margin (%)', 'Sales Count']
            exporter.add_table(headers, vessel_analytics)
            
            return exporter.get_response(f"{filename_base}.pdf")
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
@login_required
def transfer_entry(request):
    """Step 1: Create new transfer session"""
    
    if request.method == 'GET':
        vessels = Vessel.objects.filter(active=True).order_by('name')
        recent_transfers = Transaction.objects.filter(
            transaction_type='TRANSFER_OUT'
        ).select_related(
            'vessel', 'product', 'transfer_to_vessel', 'created_by'
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
            
            from datetime import datetime
            transfer_date_obj = datetime.strptime(transfer_date, '%Y-%m-%d').date()
            
            # Create transfer session (stored in localStorage on frontend)
            import uuid
            session_id = str(uuid.uuid4())
            
            # Store in session for backend reference
            transfer_session = {
                'session_id': session_id,
                'from_vessel_id': from_vessel_id,
                'to_vessel_id': to_vessel_id,
                'transfer_date': transfer_date,
                'notes': notes,
                'created_by': request.user.id
            }
            
            request.session[f'transfer_session_{session_id}'] = transfer_session
            
            BilingualMessages.success(request, 'transfer_session_created')
            return redirect('frontend:transfer_items', session_id=session_id)
            
        except Vessel.DoesNotExist:
            BilingualMessages.error(request, 'invalid_vessel')
            return redirect('frontend:transfer_entry')
        except Exception as e:
            BilingualMessages.error(request, 'error_creating_transfer', error=str(e))
            return redirect('frontend:transfer_entry')

@login_required
def transfer_items(request, session_id):
    """Step 2: Multi-item transfer entry for a specific transfer session"""
    
    # Get transfer session from Django session
    transfer_session_key = f'transfer_session_{session_id}'
    transfer_session_data = request.session.get(transfer_session_key)
    
    if not transfer_session_data:
        BilingualMessages.error(request, 'Transfer session not found.')
        return redirect('frontend:transfer_entry')
    
    # Get vessel objects
    try:
        from_vessel = Vessel.objects.get(id=transfer_session_data['from_vessel_id'])
        to_vessel = Vessel.objects.get(id=transfer_session_data['to_vessel_id'])
    except Vessel.DoesNotExist:
        BilingualMessages.error(request, 'Invalid vessels in transfer session.')
        return redirect('frontend:transfer_entry')
    
    # Create transfer session object for template
    transfer_session = {
        'session_id': session_id,
        'from_vessel': from_vessel,
        'to_vessel': to_vessel,
        'transfer_date': datetime.strptime(transfer_session_data['transfer_date'], '%Y-%m-%d').date(),
        'notes': transfer_session_data.get('notes', '')
    }
    
    context = {
        'transfer_session': transfer_session,
    }
    
    return render(request, 'frontend/transfer_items.html', context)

@login_required
def transfer_available_products(request):
    """AJAX endpoint to get available products for transfer"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
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
        from django.db.models import Sum
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

@login_required
def transfer_bulk_complete(request):
    """Complete transfer with bulk transaction creation"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        
        transfer_session_id = data.get('transfer_session_id')
        items = data.get('items', [])
        
        if not transfer_session_id or not items:
            return JsonResponse({'success': False, 'error': 'Transfer session ID and items required'})
        
        # Get transfer session
        transfer_session_key = f'transfer_session_{transfer_session_id}'
        transfer_session_data = request.session.get(transfer_session_key)
        
        if not transfer_session_data:
            return JsonResponse({'success': False, 'error': 'Transfer session not found'})
        
        # Get vessels
        from_vessel = Vessel.objects.get(id=transfer_session_data['from_vessel_id'])
        to_vessel = Vessel.objects.get(id=transfer_session_data['to_vessel_id'])
        transfer_date = datetime.strptime(transfer_session_data['transfer_date'], '%Y-%m-%d').date()
        
        # Validate all items first
        validated_items = []
        
        for item in items:
            product_id = item.get('product_id')
            quantity = item.get('quantity')
            notes = item.get('notes', '')
            
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
            from transactions.models import get_available_inventory
            available_quantity, lots = get_available_inventory(from_vessel, product)
            
            if quantity > available_quantity:
                return JsonResponse({
                    'success': False, 
                    'error': f'Insufficient inventory for {product.name}. Available: {available_quantity}, Requested: {quantity}'
                })
            
            validated_items.append({
                'product': product,
                'quantity': quantity,
                'notes': notes
            })
        
        # All items validated - create transactions atomically
        from django.db import transaction
        with transaction.atomic():
            created_transfers = []
            
            for item in validated_items:
                # Create TRANSFER_OUT transaction (this automatically creates TRANSFER_IN)
                transfer_out = Transaction.objects.create(
                    vessel=from_vessel,
                    product=item['product'],
                    transaction_type='TRANSFER_OUT',
                    transaction_date=transfer_date,
                    quantity=item['quantity'],
                    transfer_to_vessel=to_vessel,
                    notes=item['notes'] or f'Transfer to {to_vessel.name}',
                    created_by=request.user
                )
                created_transfers.append(transfer_out)
            
            # Clean up session
            del request.session[transfer_session_key]
        
        return JsonResponse({
            'success': True,
            'message': f'Transfer completed successfully! {len(created_transfers)} items transferred from {from_vessel.name} to {to_vessel.name}.',
            'transfer_data': {
                'from_vessel': from_vessel.name,
                'to_vessel': to_vessel.name,
                'items_count': len(created_transfers),
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error completing transfer: {str(e)}'})

@login_required
def sales_available_products(request):
    """AJAX endpoint to get available products for sales"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
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
        
        # Filter duty-free products if vessel doesn't support them
        if not vessel.has_duty_free:
            available_lots = available_lots.filter(product__is_duty_free=False)
        
        # Group by product and calculate totals
        from django.db.models import Sum
        product_summaries = available_lots.values(
            'product__id', 'product__name', 'product__item_id', 
            'product__barcode', 'product__is_duty_free',
            'product__selling_price'
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
                'selling_price': float(summary['product__selling_price']),
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

@login_required
def sales_calculate_cogs(request):
    """AJAX endpoint to calculate COGS for sales using FIFO simulation"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        vessel_id = data.get('vessel_id')
        product_id = data.get('product_id')
        quantity = data.get('quantity', 0)
        
        if not all([vessel_id, product_id]) or quantity <= 0:
            return JsonResponse({'success': False, 'error': 'Invalid parameters'})
        
        # Get objects
        vessel = Vessel.objects.get(id=vessel_id, active=True)
        product = Product.objects.get(id=product_id, active=True)
        
        # Get available inventory and FIFO lots
        from transactions.models import get_available_inventory
        available_quantity, lots = get_available_inventory(vessel, product)
        
        if quantity > available_quantity:
            return JsonResponse({
                'success': False, 
                'error': f'Insufficient inventory. Available: {available_quantity}, Requested: {quantity}'
            })
        
        # Simulate FIFO consumption to calculate COGS
        consumption_preview = []
        remaining_to_consume = quantity
        total_fifo_cost = 0
        
        for lot in lots:
            if remaining_to_consume <= 0:
                break
            
            consumed_from_lot = min(lot.remaining_quantity, remaining_to_consume)
            lot_cost = consumed_from_lot * lot.purchase_price
            total_fifo_cost += lot_cost
            
            consumption_preview.append({
                'lot_date': lot.purchase_date.strftime('%d/%m/%Y'),
                'consumed_quantity': consumed_from_lot,
                'unit_cost': float(lot.purchase_price),
                'total_cost': float(lot_cost)
            })
            
            remaining_to_consume -= consumed_from_lot
        
        return JsonResponse({
            'success': True,
            'total_cogs': float(total_fifo_cost),
            'consumption_breakdown': consumption_preview
        })
        
    except (Vessel.DoesNotExist, Product.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Vessel or product not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def supply_product_catalog(request):
    """AJAX endpoint to get products filtered by vessel's duty-free capability"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
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

from .utils import get_vessel_display_name, format_vessel_list