from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q, Case, When, IntegerField, Sum
from django.db.models.functions import Coalesce, Cast
from django.core.cache import cache
import logging
from frontend.utils.cache_helpers import PerfectPagination, ProductCacheHelper, VesselCacheHelper
from .permissions import is_admin_or_manager, is_superuser_only
from .utils import BilingualMessages
from products.models import Product, Category
from transactions.models import VesselProductPrice
from django.db import transaction
from vessels.models import Vessel
from decimal import Decimal
from datetime import date
import decimal
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.db import connection
import hashlib

logger = logging.getLogger('frontend')

@login_required
@user_passes_test(is_admin_or_manager)
def product_list_view(request):
    """OPTIMIZED: Minimal database queries with efficient caching"""
    
    # Get filter parameters
    search_query = request.GET.get('search', '').strip()
    category_filter = request.GET.get('category', '').strip()
    department_filter = request.GET.get('department', '').strip()
    page_number = request.GET.get('page', 1)
    page_size = int(request.GET.get('per_page', 30))
    
    # Validate inputs
    if page_size not in [30, 50, 100]:
        page_size = 30
    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1
    except (ValueError, TypeError):
        page_number = 1
    
    # 🚀 SKIP CACHING ON FIRST LOAD: Focus on query optimization instead of cache overhead
    # Skip per-request caching entirely to eliminate 6+ cache database operations
    
    # 🚀 OPTIMIZED: Simple static data - no complex aggregations
    ultimate_static_cache = cache.get('perfect_static_v2')
    if ultimate_static_cache is None:
        
        # OPTIMIZED: Single query with conditional aggregation
        from django.db.models import Sum, Case, When, Value, IntegerField
        
        product_stats = Product.objects.aggregate(
            total_products=Count('id'),
            active_products=Sum(Case(When(active=True, then=Value(1)), default=Value(0), output_field=IntegerField()))
        )
        
        # SIMPLIFIED: Skip expensive inventory counting for first load
        products_with_inventory = 0  # Will be calculated only if needed
        
        # SIMPLIFIED: Use a simple count instead of complex pricing calculation
        touristic_vessels_count = Vessel.objects.filter(active=True, has_duty_free=False).count()
        incomplete_pricing_count = 0  # Skip expensive calculation
        
        categories = list(Category.objects.filter(active=True).only('id', 'name').order_by('name'))
        
        ultimate_static_cache = {
            'stats': {
                'total_products': product_stats['total_products'],
                'active_products': product_stats['active_products'],
                'inactive_products': product_stats['total_products'] - product_stats['active_products'],
                'duty_free_products': 0,  # Skip calculation
                'general_products': product_stats['active_products'],  # Approximate
                'products_with_inventory': products_with_inventory
            },
            'touristic_vessels_count': touristic_vessels_count,
            'incomplete_pricing_count': incomplete_pricing_count,
            'categories': categories
        }
        cache.set('perfect_static_v2', ultimate_static_cache, 7200)

    # Extract from ultimate cache
    stats = ultimate_static_cache['stats']
    touristic_vessels_count = ultimate_static_cache['touristic_vessels_count'] 
    incomplete_pricing_cache = ultimate_static_cache['incomplete_pricing_count']
    categories = ultimate_static_cache['categories']
    
    # 🚀 OPTIMIZED PRODUCT QUERY: Remove unnecessary LEFT JOIN on auth_user
    products_base = Product.objects.select_related('category').only(
        'id', 'name', 'item_id', 'barcode', 'selling_price', 'purchase_price', 
        'active', 'is_duty_free', 'category__name', 'created_at', 'created_by_id'
    )
    # Remove expensive inventory and pricing annotations for faster load
    
    # Apply filters
    if search_query:
        products_base = products_base.filter(
            Q(name__icontains=search_query) |
            Q(item_id__icontains=search_query) |
            Q(barcode__icontains=search_query)
        )
    
    if category_filter:
        try:
            category_id = int(category_filter)
            products_base = products_base.filter(category_id=category_id)
        except (ValueError, TypeError):
            pass
    
    if department_filter == 'duty_free':
        products_base = products_base.filter(is_duty_free=True)
    elif department_filter == 'general':
        products_base = products_base.filter(is_duty_free=False)
    
    # 🚀 SIMPLIFIED SORTING: Remove expensive integer casting annotation
    products_base = products_base.order_by('item_id', 'id')
    
    # 🚀 SAFE PAGINATION: Get current page products
    start_index = (page_number - 1) * page_size
    end_index = start_index + page_size
    
    # Get products for current page
    current_page_products = list(products_base[start_index:end_index])
    
    # Simple count estimation (we'll optimize this further if needed)
    if len(current_page_products) < page_size:
        # We got less than a full page, so this is the last page
        estimated_total = start_index + len(current_page_products)
    else:
        # Assume there might be more pages
        estimated_total = (page_number * page_size) + 1

    # Create perfect pagination with estimated count
    perfect_paginator = PerfectPagination(current_page_products, page_number, estimated_total, page_size)
    products_page = perfect_paginator
    
    # 🚀 INVENTORY CALCULATION: Get inventory for current page products only
    from transactions.models import InventoryLot
    
    # Get product IDs for current page
    product_ids = [p.id for p in current_page_products]
    
    # 🚀 OPTIMIZED: Direct SQL query to avoid unnecessary JOINs
    from django.db import connection
    
    if product_ids:
        placeholders = ','.join(['%s'] * len(product_ids))
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT product_id, SUM(remaining_quantity) as total_quantity
                FROM transactions_inventorylot 
                WHERE product_id IN ({placeholders}) AND remaining_quantity > 0
                GROUP BY product_id
            """, product_ids)
            inventory_data = cursor.fetchall()
        inventory_lookup = {product_id: total_quantity for product_id, total_quantity in inventory_data}
    else:
        inventory_lookup = {}
    
    products_with_info = []
    for product in current_page_products:
        # Get inventory quantity from lookup
        inventory_qty = inventory_lookup.get(product.id, 0)
        
        # Determine inventory status
        if inventory_qty > 100:
            inventory_status, inventory_class = 'high', 'success'
        elif inventory_qty > 20:
            inventory_status, inventory_class = 'medium', 'warning'
        elif inventory_qty > 0:
            inventory_status, inventory_class = 'low', 'danger'
        else:
            inventory_status, inventory_class = 'out', 'secondary'
        pricing_completion = 100.0 if product.is_duty_free else 0.0
        needs_pricing = not product.is_duty_free
        
        products_with_info.append({
            'id': product.id,
            'name': product.name,
            'item_id': product.item_id,
            'barcode': product.barcode,
            'selling_price': product.selling_price,
            'purchase_price': round(product.purchase_price, 3),
            'active': product.active,
            'is_duty_free': product.is_duty_free,
            'created_at': product.created_at,
            'category': product.category,
            'created_by_id': product.created_by_id,  # Just the ID, no JOIN needed
            'total_inventory': inventory_qty,
            'inventory_status': inventory_status,
            'inventory_class': inventory_class,
            'pricing_completion': pricing_completion,
            'needs_pricing': needs_pricing,
            'inventory_value': 0.0,  # Skip calculation
            'vessel_pricing_count': 0,  # Skip calculation
            'vessel_pricing_info': {
                'has_vessel_pricing': False,
                'vessel_prices_count': 0,
                'missing_prices_count': touristic_vessels_count,
                'pricing_completion': pricing_completion,
                'total_touristic_vessels': touristic_vessels_count,
            }
        })
    
    # Simplified vessel pricing summary
    vessel_pricing_summary = {
        'vessels_with_incomplete_pricing': touristic_vessels_count,  # Show actual count (2), not 1
        'total_missing_prices': incomplete_pricing_cache,
    }
    
    context = {
        'mode': 'list',
        'products': products_with_info,
        'page_obj': products_page,
        'paginator': perfect_paginator,
        'page_size': page_size,
        'categories': categories,
        'filters': {
            'search': search_query,
            'category': category_filter,
            'department': department_filter,
        },
        'stats': {
            **stats,
            'total_categories': len(categories),
            'touristic_vessels_count': touristic_vessels_count,
            'filtered_products_count': estimated_total,
            'products_with_incomplete_pricing': incomplete_pricing_cache,
        },
        'vessel_pricing_summary': vessel_pricing_summary,
        'today': date.today(),
        'from_cache': False,
        'pagination_info': {
            'current_page': products_page.number,
            'total_pages': products_page.num_pages,
            'has_previous': products_page.has_previous(),
            'has_next': products_page.has_next(),
            'previous_page_number': products_page.previous_page_number(),
            'next_page_number': products_page.next_page_number(),
            'start_index': products_page.start_index(),
            'end_index': products_page.end_index(),
            'total_count': estimated_total,
        }
    }
    
    # 🚀 SKIP FINAL CACHE: Avoid cache storage overhead for first-load optimization
    # cache.set(cache_key, context, 3600)  # Disabled for better first-load performance
    
    return render(request, 'frontend/product_list.html', context)
@login_required
@user_passes_test(is_admin_or_manager)
def product_create_view(request):
    """Create new product view"""
    
    if request.method == 'GET':
        # Get form data
        categories = Category.objects.filter(active=True).order_by('name')
        # 🚀 VESSEL CACHE: Use cached vessels for cross-page efficiency
        all_vessels_cached = VesselCacheHelper.get_all_vessels_basic_data()
        vessels = [v for v in all_vessels_cached if v.active]
        touristic_vessels = [v for v in vessels if not v.has_duty_free]
        
        context = {
            'mode': 'create',
            'categories': categories,
            'vessels': vessels,
            'touristic_vessels': touristic_vessels,
            'today': date.today(),
        }
        
        return render(request, 'frontend/product_form.html', context)
    
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
            action = request.POST.get('action') or request.POST.get('form_action')
            
            # Validation
            if not all([name, item_id, category_id, purchase_price, selling_price]):
                BilingualMessages.error(request, 'required_fields_missing')
                return redirect('frontend:product_create')
            
            # Check unique item_id
            if Product.objects.filter(item_id=item_id).exists():
                BilingualMessages.error(request, 'product_already_exists', item_id=item_id)
                return redirect('frontend:product_create')
            
            # Get category
            try:
                category = Category.objects.get(id=category_id, active=True)
            except Category.DoesNotExist:
                BilingualMessages.error(request, 'invalid_category')
                return redirect('frontend:product_create')
            
            # Process vessel pricing
            vessel_prices_data = {}
            if not is_duty_free:
                touristic_vessels = Vessel.objects.filter(active=True, has_duty_free=False)
                for vessel in touristic_vessels:
                    vessel_price = request.POST.get(f'vessel_price_{vessel.id}', '').strip()
                    if vessel_price:
                        try:
                            vessel_prices_data[vessel.id] = Decimal(vessel_price)
                        except (ValueError, decimal.InvalidOperation):
                            BilingualMessages.error(request, 'invalid_vessel_price', vessel_name=vessel.name)
                            return redirect('frontend:product_create')
    
            # Create product
            with transaction.atomic():
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
                
                # Create vessel prices
                for vessel_id, price in vessel_prices_data.items():
                    vessel = Vessel.objects.get(id=vessel_id)
                    VesselProductPrice.objects.create(
                        product=product,
                        vessel=vessel,
                        selling_price=price
                    )
            
            # Clear static cache only
            cache.delete('perfect_static_v2')
            
            BilingualMessages.success(request, 'product_created_successfully', product_name=name)
            return redirect('frontend:product_list')
                
        except Exception as e:
            BilingualMessages.error(request, 'error_creating_product', error=str(e))
            return redirect('frontend:product_create')

@require_GET
@login_required
@user_passes_test(is_admin_or_manager)
def check_product_exists(request):
    item_id = request.GET.get('item_id', '').strip()
    name = request.GET.get('name', '').strip()

    exists = False
    conflict_field = None

    if item_id and Product.objects.filter(item_id=item_id).exists():
        exists = True
        conflict_field = 'item_id'
    elif name and Product.objects.filter(name__iexact=name).exists():
        exists = True
        conflict_field = 'name'

    return JsonResponse({'exists': exists, 'field': conflict_field})


@login_required
@user_passes_test(is_admin_or_manager)
def product_edit_view(request, product_id):
    """Edit existing product view"""
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'GET':
        # Get form data
        categories = Category.objects.filter(active=True).order_by('name')
        # 🚀 VESSEL CACHE: Use cached vessels for cross-page efficiency
        all_vessels_cached = VesselCacheHelper.get_all_vessels_basic_data()
        vessels = [v for v in all_vessels_cached if v.active]
        touristic_vessels = [v for v in vessels if not v.has_duty_free]
        
        # Get existing vessel prices
        existing_vessel_prices = {}
        if not product.is_duty_free:
            vessel_prices = VesselProductPrice.objects.filter(product=product)
            existing_vessel_prices = {vp.vessel_id: vp.selling_price for vp in vessel_prices}
        
        context = {
            'mode': 'edit',
            'product': product,
            'categories': categories,
            'vessels': vessels,
            'touristic_vessels': touristic_vessels,
            'existing_vessel_prices': existing_vessel_prices,
            'today': date.today(),
        }
        
        return render(request, 'frontend/product_form.html', context)
    
    elif request.method == 'POST':
        try:
            logger.debug(f"🔥 Starting product update for ID: {product_id}")
            
            # Get form data
            name = request.POST.get('name', '').strip()
            item_id = request.POST.get('item_id', '').strip()
            barcode = request.POST.get('barcode', '').strip() or None
            category_id = request.POST.get('category')
            purchase_price = request.POST.get('purchase_price')
            selling_price = request.POST.get('selling_price')
            is_duty_free = request.POST.get('is_duty_free') == 'on'
            active = request.POST.get('active') == 'on'
            
            logger.debug(f"🔥 Form data received: {name}, {item_id}")
            
            # Validation
            if not all([name, item_id, category_id, purchase_price, selling_price]):
                logger.warning("🔥 Validation failed: missing required fields")
                BilingualMessages.error(request, 'required_fields_missing')
                return redirect('frontend:product_edit', product_id=product_id)
            
            # Check unique item_id (excluding current product)
            if Product.objects.filter(item_id=item_id).exclude(id=product_id).exists():
                logger.warning(f"🔥 Validation failed: item_id {item_id} already exists")
                BilingualMessages.error(request, 'product_already_exists', item_id=item_id)
                return redirect('frontend:product_edit', product_id=product_id)
            
            # Get category
            try:
                category = Category.objects.get(id=category_id, active=True)
                logger.debug(f"🔥 Category found: {category.name}")
            except Category.DoesNotExist:
                logger.warning(f"🔥 Category not found: {category_id}")
                BilingualMessages.error(request, 'invalid_category')
                return redirect('frontend:product_edit', product_id=product_id)
            
            # Process vessel pricing
            vessel_prices_data = {}
            if not is_duty_free:
                touristic_vessels = Vessel.objects.filter(active=True, has_duty_free=False)
                for vessel in touristic_vessels:
                    vessel_price = request.POST.get(f'vessel_price_{vessel.id}', '').strip()
                    if vessel_price:
                        try:
                            vessel_prices_data[vessel.id] = Decimal(vessel_price)
                        except (ValueError, decimal.InvalidOperation):
                            logger.warning(f"🔥 Invalid vessel price for {vessel.name}: {vessel_price}")
                            BilingualMessages.error(request, 'invalid_vessel_price', vessel_name=vessel.name)
                            return redirect('frontend:product_edit', product_id=product_id)
            
            logger.debug(f"🔥 Vessel prices: {vessel_prices_data}")
            
            # Update product
            with transaction.atomic():
                logger.debug("🔥 Starting database transaction")
                
                product.name = name
                product.item_id = item_id
                product.barcode = barcode
                product.category = category
                product.purchase_price = Decimal(purchase_price)
                product.selling_price = Decimal(selling_price)
                product.is_duty_free = is_duty_free
                product.active = active
                product.save()
                
                logger.debug(f"🔥 Product saved: {product.name}")
                
                # Update vessel prices
                VesselProductPrice.objects.filter(product=product).delete()
                for vessel_id, price in vessel_prices_data.items():
                    vessel = Vessel.objects.get(id=vessel_id)
                    VesselProductPrice.objects.create(
                        product=product,
                        vessel=vessel,
                        selling_price=price
                    )
                
                logger.debug(f"🔥 Vessel prices updated: {len(vessel_prices_data)} prices")
        
            # Simple cache clear - just clear the specific patterns
            cache.delete_many([
                'perfect_static_v2',  # Clear static data cache
            ])
            # Clear product list cache patterns would require Redis/Memcached
            # For now, let cache expire naturally in 1 hour
                        
            logger.info(f"🔥 Product update completed successfully")
            BilingualMessages.success(request, 'product_updated_successfully', product_name=name)
            
            return redirect('frontend:product_list')
                
        except Exception as e:
            logger.error(f"🔥 CRITICAL ERROR in product update: {str(e)}")
            
            BilingualMessages.error(request, 'error_updating_product')
            return redirect('frontend:product_edit', product_id=product_id)

@login_required
@user_passes_test(is_admin_or_manager)
def delete_product(request, product_id):
    """Delete or deactivate product with enhanced cache management"""
    
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
            
            # Clear static cache only
            cache.delete('perfect_static_v2')
            
            return redirect('frontend:product_list')
    
        except Exception as e:
            BilingualMessages.error(request, 'error_deleting_product', error=str(e))
            return redirect('frontend:product_list')
    
    return redirect('frontend:product_list')

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
@user_passes_test(is_superuser_only)
def debug_cache_status(request):
    """Debug endpoint to check cache status"""
    
    if request.method == 'POST' and request.POST.get('action') == 'clear_all':
        # Manual cache clear
        success, count = ProductCacheHelper.clear_all_product_cache()
        if success:
            BilingualMessages.success(request, f'Cache cleared: {count} keys removed')
        else:
            BilingualMessages.error(request, 'Cache clear failed')
        
        return redirect('frontend:product_list')
    
    # Show cache status
    cache_status = ProductCacheHelper.debug_cache_status()
    
    context = {
        'cache_status': cache_status,
        'cache_helper_available': True,
    }
    
    return render(request, 'frontend/debug_cache.html', context)

def test_cache_clearing():
    """Test function to verify cache clearing works"""
    
    logger.debug("🧪 TESTING CACHE CLEARING...")
    
    # Check initial status
    status_before = ProductCacheHelper.debug_cache_status()
    logger.debug(f"📊 Before: {sum(1 for v in status_before.values() if v)} active keys")
    
    # Clear cache
    success, count = ProductCacheHelper.clear_all_product_cache()
    logger.debug(f"🔥 Cleared: {count} keys, success: {success}")
    
    # Check after status
    status_after = ProductCacheHelper.debug_cache_status()
    logger.debug(f"📊 After: {sum(1 for v in status_after.values() if v)} active keys")
    
    return success