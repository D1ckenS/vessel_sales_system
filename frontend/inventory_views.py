from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q, Sum, Min, Avg, Count
from django.http import JsonResponse
from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, InventoryLot
from .utils import BilingualMessages
from products.models import Product
import json

@login_required
def inventory_check(request):
    """OPTIMIZED: Inventory check with FIFO cost calculation"""
    
    # Get all vessels for selection
    vessels = Vessel.objects.filter(active=True).order_by('name')
    selected_vessel_id = request.GET.get('vessel')
    
    if not selected_vessel_id:
        # Show vessel selection if none selected
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
                'product_search': '',
                'stock_filter': '',
            }
        }
        return render(request, 'frontend/inventory_check.html', context)
    
    # Get selected vessel
    selected_vessel = get_object_or_404(Vessel, id=selected_vessel_id, active=True)
    
    # Get filter parameters
    product_search = request.GET.get('search', '').strip()
    stock_filter = request.GET.get('stock_filter', '')
    
    # OPTIMIZED: Get inventory summary with total quantities
    inventory_lots = InventoryLot.objects.filter(
        vessel=selected_vessel,
        remaining_quantity__gt=0,
        product__active=True
    ).select_related(
        'product', 'product__category'
    ).order_by('product__item_id')
    
    # Apply product search filter
    if product_search:
        inventory_lots = inventory_lots.filter(
            Q(product__name__icontains=product_search) | 
            Q(product__item_id__icontains=product_search) |
            Q(product__barcode__icontains=product_search)
        )
    
    # OPTIMIZED: Aggregate inventory data by product
    from django.db.models import Sum, Count
    inventory_summary = inventory_lots.values(
        'product__id', 'product__name', 'product__item_id', 
        'product__barcode', 'product__is_duty_free', 'product__category__name'
    ).annotate(
        total_quantity=Sum('remaining_quantity'),
        total_lots=Count('id')
    ).order_by('product__item_id')
    
    # Process aggregated data with FIFO cost calculation
    inventory_data = []
    vessel_total_value = 0
    vessel_low_stock = 0
    vessel_out_of_stock = 0
    
    for item in inventory_summary:
        product_id = item['product__id']
        total_qty = item['total_quantity']
        
        # FIFO COST: Get the oldest lot's cost for this product
        oldest_lot = InventoryLot.objects.filter(
            vessel=selected_vessel,
            product_id=product_id,
            remaining_quantity__gt=0
        ).order_by('purchase_date', 'created_at').first()
        
        fifo_cost = oldest_lot.purchase_price if oldest_lot else 0
        total_value = total_qty * fifo_cost
        
        # Determine stock status
        if total_qty <= 5:
            stock_status = 'low'
            status_class = 'warning'
            status_text = 'Low Stock'
            vessel_low_stock += 1
        else:
            stock_status = 'good'
            status_class = 'success'
            status_text = 'Good Stock'
        
        inventory_item = {
            'vessel_id': selected_vessel.id,
            'vessel_name': selected_vessel.name,
            'product_id': product_id,
            'product_name': item['product__name'],
            'product_item_id': item['product__item_id'],
            'product_barcode': item['product__barcode'] or '',
            'product_category': item['product__category__name'],
            'is_duty_free': item['product__is_duty_free'],
            'total_quantity': total_qty,
            'current_cost': fifo_cost,  # FIFO cost from oldest lot
            'total_value': total_value,
            'stock_status': stock_status,
            'status_class': status_class,
            'status_text': status_text,
            'total_lots': item['total_lots'],
        }
        
        # Apply stock filter
        if stock_filter == 'low' and stock_status != 'low':
            continue
        elif stock_filter == 'good' and stock_status != 'good':
            continue
        
        inventory_data.append(inventory_item)
        vessel_total_value += total_value
    
    # OPTIMIZED: Get out-of-stock products with single query
    if not stock_filter or stock_filter == 'out':
        # Products that had inventory but now have zero stock
        products_with_zero_stock = Product.objects.filter(
            active=True,
            inventory_lots__vessel=selected_vessel
        ).exclude(
            inventory_lots__vessel=selected_vessel,
            inventory_lots__remaining_quantity__gt=0
        ).select_related('category').distinct()
        
        # Apply search filter to zero-stock products
        if product_search:
            products_with_zero_stock = products_with_zero_stock.filter(
                Q(name__icontains=product_search) |
                Q(item_id__icontains=product_search) |
                Q(barcode__icontains=product_search)
            )
        
        for product in products_with_zero_stock:
            vessel_out_of_stock += 1
            inventory_data.append({
                'vessel_id': selected_vessel.id,
                'vessel_name': selected_vessel.name,
                'product_id': product.id,
                'product_name': product.name,
                'product_item_id': product.item_id,
                'product_barcode': product.barcode or '',
                'product_category': product.category.name,
                'is_duty_free': product.is_duty_free,
                'total_quantity': 0,
                'current_cost': 0,
                'total_value': 0,
                'stock_status': 'out',
                'status_class': 'danger',
                'status_text': 'Out of Stock',
                'total_lots': 0,
            })
    
    # Calculate final stats
    vessel_total_products = len(inventory_data)
    vessel_good_stock = vessel_total_products - vessel_low_stock - vessel_out_of_stock
    
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
        ).select_related(
            'vessel',
            'product',
            'created_by'
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