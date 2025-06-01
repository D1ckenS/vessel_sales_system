from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q, F
from django.http import JsonResponse
from datetime import date, timedelta
from decimal import Decimal
import decimal
from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, InventoryLot

@login_required
def supply_entry(request):
    """Supply entry interface for receiving new stock"""
    
    if request.method == 'GET':
        # Display the supply entry form
        vessels = Vessel.objects.filter(active=True).order_by('name')
        
        # Get recent supply transactions
        recent_supplies = Transaction.objects.filter(
            transaction_type='SUPPLY'
        ).select_related(
            'vessel', 'product', 'created_by'
        ).order_by('-created_at')[:20]
        
        # In your sales_entry and supply_entry views, add:
        vessel_colors = {
            'amman': 'bg-primary',
            'aylah': 'bg-danger', 
            'sinaa': 'bg-success',
            'nefertiti': 'bg-secondary',
            'babel': 'bg-warning',
            'dahab': 'bg-info'
        }
        
        context = {
            'vessels': vessels,
            'recent_supplies': recent_supplies,
            'today': date.today(),
            'vessel_colors': vessel_colors,
        }
        
        return render(request, 'frontend/supply_entry.html', context)

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
            
            print(f"DEBUG: Form action received: '{action}' (from POST keys: {list(request.POST.keys())})")
            print(f"DEBUG: Product data - name: '{name}', item_id: '{item_id}'")
            
            # Basic validation
            if not all([name, item_id, category_id, purchase_price, selling_price]):
                messages.error(request, 'Please fill in all required fields.')
                return redirect('frontend:add_product')
            
            # Validate unique item_id
            if Product.objects.filter(item_id=item_id).exists():
                messages.error(request, f'Item ID "{item_id}" already exists. Please use a different ID.')
                return redirect('frontend:add_product')
            
            # Get category
            from products.models import Category
            try:
                category = Category.objects.get(id=category_id, active=True)
            except Category.DoesNotExist:
                messages.error(request, 'Invalid category selected.')
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
            
            print(f"DEBUG: Product created successfully with ID: {product.id}")
            
            # Handle initial stock - USE SAME LOGIC AS SUPPLY ENTRY
            if action == 'with_stock':
                print(f"DEBUG: Processing initial stock (action: {action})")
                
                purchase_date_str = request.POST.get('purchase_date')
                if not purchase_date_str:
                    messages.error(request, 'Purchase date is required for initial stock.')
                    product.delete()
                    return redirect('frontend:add_product')
                
                from datetime import datetime
                purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d').date()
                
                # Process each vessel - SIMPLIFIED LOGIC
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
                                        messages.error(request, f'Cannot add duty-free product to {vessel.name}')
                                        product.delete()
                                        return redirect('frontend:add_product')
                                    
                                    # Create SUPPLY transaction - SAME AS SUPPLY ENTRY
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
                                    
                                    print(f"DEBUG: Created SUPPLY transaction ID {supply_transaction.id} for {vessel.name}")
                                    vessels_processed.append(f'{vessel.name}: {quantity} units @ {cost} JOD')
                                    
                            except (ValueError, decimal.InvalidOperation) as e:
                                print(f"DEBUG: Error processing {vessel.name}: {e}")
                                messages.error(request, f'Invalid data for {vessel.name}')
                                product.delete()
                                return redirect('frontend:add_product')
                
                if vessels_processed:
                    messages.success(request, f'Product "{product.name}" created with stock: {"; ".join(vessels_processed)}')
                else:
                    messages.error(request, 'No valid stock data provided')
                    product.delete()
                    return redirect('frontend:add_product')
                    
            else:
                print(f"DEBUG: Product only mode (action: {action})")
                messages.success(request, f'Product "{product.name}" (ID: {product.item_id}) created successfully.')
            
            return redirect('frontend:inventory_check')
            
            return redirect('frontend:inventory_check')
            
        except Exception as e:
            print(f"DEBUG: Exception occurred: {e}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            messages.error(request, f'Error creating product: {str(e)}')
            return redirect('frontend:add_product')
    
    else:
        messages.error(request, 'Invalid request method.')
        return redirect('frontend:inventory_check')

@login_required
def dashboard(request):
    """Main dashboard with overview and navigation"""
    
    # Get basic stats
    today = date.today()
    vessels = Vessel.objects.filter(active=True)
    
    # Today's sales summary
    today_sales = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date=today
    ).aggregate(
        total_revenue=Sum(F('unit_price') * F('quantity')),
        transaction_count=Count('id')
    )
    
    # Recent transactions
    recent_transactions = Transaction.objects.select_related(
        'vessel', 'product'
    ).order_by('-created_at')[:10]
    
    context = {
        'vessels': vessels,
        'today_sales': today_sales,
        'recent_transactions': recent_transactions,
        'today': today,
    }
    
    return render(request, 'frontend/dashboard.html', context)

@login_required
def sales_entry(request):
    """Functional sales entry interface with FIFO integration"""
    
    if request.method == 'GET':
        # Display the sales entry form
        vessels = Vessel.objects.filter(active=True).order_by('name')
        
        # Get today's sales for the table
        today = date.today()
        today_sales = Transaction.objects.filter(
            transaction_type='SALE',
            transaction_date=today
        ).select_related(
            'vessel', 'product', 'created_by'
        ).order_by('-created_at')
        
        # In your sales_entry and supply_entry views, add:
        vessel_colors = {
            'amman': 'bg-primary',
            'aylah': 'bg-danger', 
            'sinaa': 'bg-success',
            'nefertiti': 'bg-secondary',
            'babel': 'bg-warning',
            'dahab': 'bg-info'
        }
        
        context = {
            'vessels': vessels,
            'today_sales': today_sales,
            'today': today,
            'vessel_colors': vessel_colors
        }
        
        return render(request, 'frontend/sales_entry.html', context)

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

@login_required
def reports_dashboard(request):
    """Reports hub with different report options"""
    return render(request, 'frontend/reports_dashboard.html')

@login_required
def daily_report(request):
    """User-friendly daily reports"""
    return render(request, 'frontend/daily_report.html')

@login_required
def monthly_report(request):
    """User-friendly monthly reports"""
    return render(request, 'frontend/monthly_report.html')

@login_required
def analytics_report(request):
    """User-friendly analytics dashboard"""
    return render(request, 'frontend/analytics_report.html')