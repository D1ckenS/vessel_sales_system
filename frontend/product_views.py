from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from frontend.views import is_admin_or_manager
from products.models import Product
from .utils import BilingualMessages
from products.models import Product, Category
from .utils import get_vessel_display_name, format_vessel_list

@login_required
@user_passes_test(is_admin_or_manager)
def product_management(request):
    """Product and Category management interface"""
    
    # Get all products with category info
    products = Product.objects.select_related('category', 'created_by').order_by('item_id')
    
    # Get all categories
    categories = Category.objects.annotate(
        product_count=Count('products')
    ).order_by('name')
    
    # Get search/filter parameters
    search_query = request.GET.get('search', '')
    category_filter = request.GET.get('category', '')
    status_filter = request.GET.get('status', '')
    
    # Apply filters
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(item_id__icontains=search_query) |
            Q(barcode__icontains=search_query)
        )
    
    if category_filter:
        products = products.filter(category_id=category_filter)
    
    if status_filter == 'active':
        products = products.filter(active=True)
    elif status_filter == 'inactive':
        products = products.filter(active=False)
    
    # Calculate summary stats
    total_products = Product.objects.count()
    active_products = Product.objects.filter(active=True).count()
    total_categories = categories.count()
    
    context = {
        'products': products,
        'categories': categories,
        'filters': {
            'search': search_query,
            'category': category_filter,
            'status': status_filter,
        },
        'stats': {
            'total_products': total_products,
            'active_products': active_products,
            'inactive_products': total_products - active_products,
            'total_categories': total_categories,
        }
    }
    
    return render(request, 'frontend/admin/product_management.html', context)

@login_required
@user_passes_test(is_admin_or_manager)
def add_product(request, product_id=None):
    """Enhanced product management: list, create, edit products with initial stock"""
    
    # FIXED: Import at function level - MOVED TO TOP OF FUNCTION
    from products.models import Category, Product
    from vessels.models import Vessel
    from transactions.models import Transaction
    from decimal import Decimal
    from datetime import date
    from django.db.models import Q
    from django.shortcuts import get_object_or_404
    import decimal
    
    # Determine operation mode with enhanced detection
    if product_id:
        mode = 'edit'
        product = get_object_or_404(Product, id=product_id)
    else:
        # Check URL name to determine mode explicitly
        resolver_match = request.resolver_match
        url_name = resolver_match.url_name if resolver_match else None
        
        if url_name == 'add_product_form':
            # Explicit create mode from /products/create/
            mode = 'create'
        elif url_name == 'product_management':
            # Explicit list mode from /products/manage/
            mode = 'list'
        else:
            # Legacy /products/add/ - check mode parameter or default to list
            mode = request.GET.get('mode', 'list')
        
        product = None
    
    if request.method == 'GET':
            # Get all data needed for the interface
            categories = Category.objects.filter(active=True).order_by('name')
            vessels = Vessel.objects.filter(active=True).order_by('name')
            
            # FIXED: Initialize context with common data first
            context = {
                'mode': mode,
                'categories': categories,
                'vessels': vessels,
                'today': date.today(),
            }
            
            # For list mode, get products with filtering
            if mode == 'list':
                # ENHANCED: Calculate total inventory for each product
                from django.db.models import Sum, F
                from transactions.models import InventoryLot
                
                products = Product.objects.select_related('category', 'created_by').order_by('item_id')
                
                # Apply filters
                search_query = request.GET.get('search', '')
                category_filter = request.GET.get('category', '')
                status_filter = request.GET.get('status', '')
                
                if search_query:
                    products = products.filter(
                        Q(name__icontains=search_query) |
                        Q(item_id__icontains=search_query) |
                        Q(barcode__icontains=search_query)
                    )
                
                if category_filter:
                    products = products.filter(category_id=category_filter)
                
                if status_filter == 'active':
                    products = products.filter(active=True)
                elif status_filter == 'inactive':
                    products = products.filter(active=False)
                
                # NEW: Calculate total inventory for each product
                products_with_inventory = []
                for product in products:
                    # Calculate total inventory across all vessels using InventoryLot
                    total_inventory = InventoryLot.objects.filter(
                        product=product,
                        remaining_quantity__gt=0
                    ).aggregate(
                        total=Sum('remaining_quantity')
                    )['total'] or 0
                    
                    # Add total_inventory as an attribute to the product
                    product.total_inventory = total_inventory
                    products_with_inventory.append(product)
                
                # Calculate stats
                total_products = Product.objects.count()
                active_products = Product.objects.filter(active=True).count()
                
                # FIXED: Update context instead of creating new one
                context.update({
                    'products': products_with_inventory,
                    'filters': {
                        'search': search_query,
                        'category': category_filter,
                        'status': status_filter,
                    },
                    'stats': {
                        'total_products': total_products,
                        'active_products': active_products,
                        'inactive_products': total_products - active_products,
                        'total_categories': categories.count(),
                    }
                })
            else:
                # Create or edit mode - FIXED: Update context instead of creating new one
                context.update({
                    'product': product,
                })
            
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
                if mode == 'edit':
                    return redirect('frontend:edit_product', product_id=product.id)
                else:
                    return redirect('frontend:add_product_form')
            
            # Validate unique item_id
            existing_product = Product.objects.filter(item_id=item_id)
            if mode == 'edit':
                existing_product = existing_product.exclude(id=product.id)
            
            if existing_product.exists():
                BilingualMessages.error(request, 'product_already_exists', item_id=item_id)
                if mode == 'edit':
                    return redirect('frontend:edit_product', product_id=product.id)
                else:
                    return redirect('frontend:add_product_form')
            
            # Get category - REMOVED the redundant import since it's at the top
            try:
                category = Category.objects.get(id=category_id, active=True)
            except Category.DoesNotExist:
                BilingualMessages.error(request, 'invalid_category')
                if mode == 'edit':
                    return redirect('frontend:edit_product', product_id=product.id)
                else:
                    return redirect('frontend:add_product_form')
            
            # Create or update the product
            if mode == 'edit':
                # Update existing product
                product.name = name
                product.item_id = item_id
                product.barcode = barcode
                product.category = category
                product.purchase_price = Decimal(purchase_price)
                product.selling_price = Decimal(selling_price)
                product.is_duty_free = is_duty_free
                product.active = active
                product.save()
                
                BilingualMessages.success(request, 'product_updated_success', name=product.name)
                return redirect('frontend:product_management')
            else:
                # Create new product
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
            
            # Handle initial stock (only for new products)
            if mode == 'create' and action == 'with_stock':
                purchase_date_str = request.POST.get('purchase_date')
                if not purchase_date_str:
                    BilingualMessages.error(request, 'purchase_date_required')
                    product.delete()
                    return redirect('frontend:add_product_form')
                
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
                                        return redirect('frontend:add_product_form')
                                    
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
                                return redirect('frontend:add_product_form')
                
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
                    return redirect('frontend:add_product_form')
                    
            else:
                BilingualMessages.success(request, 'product_created_success', 
                                        name=product.name, item_id=product.item_id)
            
            return redirect('frontend:product_management')
            
        except Exception as e:
            BilingualMessages.error(request, 'error_creating_product', error=str(e))
            if mode == 'edit':
                return redirect('frontend:edit_product', product_id=product.id)
            else:
                return redirect('frontend:add_product_form')
    
    else:
        BilingualMessages.error(request, 'invalid_request_method')
        return redirect('frontend:product_management')

@login_required
@user_passes_test(is_admin_or_manager)
def delete_product(request, product_id):
    """Delete or deactivate product"""
    
    if request.method == 'POST':
        try:
            product = get_object_or_404(Product, id=product_id)
            
            # Check if product has any transactions
            if product.transactions.exists():
                # Soft delete - set inactive
                product.active = False
                product.save()
                BilingualMessages.success(request, 'product_deactivated', name=product.name)
            else:
                # Hard delete if no transactions
                product_name = product.name
                product.delete()
                BilingualMessages.success(request, 'product_deleted', name=product_name)
            
            return redirect('frontend:product_management')
            
        except Exception as e:
            BilingualMessages.error(request, 'error_deleting_product', error=str(e))
            return redirect('frontend:product_management')
    
    return redirect('frontend:product_management')

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