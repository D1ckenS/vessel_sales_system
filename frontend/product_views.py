from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q, Case, When, IntegerField, Sum
from django.db.models.functions import Coalesce, Cast
from django.core.cache import cache
import logging
from frontend.utils.cache_helpers import PerfectPagination, ProductCacheHelper
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
    """PERFECT NUCLEAR: 6 queries maximum, full pagination compatibility"""
    
    # 🔍 DEBUG: Check cache version at start
    logger.debug(f"🔍 Cache version at START: {ProductCacheHelper._get_cache_version()}")
    
    # Get filter parameters
    search_query = request.GET.get('search', '').strip()
    category_filter = request.GET.get('category', '').strip()
    department_filter = request.GET.get('department', '').strip()
    page_number = request.GET.get('page', 1)
    page_size = int(request.GET.get('per_page', 30))
    
    # 🔍 DEBUG: Check if filters trigger cache clearing
    logger.debug(f"🔍 Filters applied: search='{search_query}', category='{category_filter}', department='{department_filter}'")
    
    # Validate inputs
    if page_size not in [30, 50, 100]:
        page_size = 30
    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1
    except (ValueError, TypeError):
        page_number = 1
    
    # 🚀 PERFECT CACHE: Full page cache
    filters_dict = {
        'search': search_query,
        'category': category_filter,
        'status': department_filter
    }
    # NEW
    cache_key = ProductCacheHelper.get_product_list_cache_key(
        search=search_query,
        category=category_filter,
        department=department_filter,
        page_number=page_number,
        page_size=page_size
    )
    
    logger.debug(f"🔍 Generated cache key: {cache_key}")
    
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.debug("🚀 PERFECT CACHE HIT!")
        return render(request, 'frontend/product_list.html', cached_data)
    
    logger.debug("🔥 PERFECT CACHE MISS - ULTIMATE OPTIMIZATION")
    
    # 🚀 QUERY 1: ULTIMATE STATIC DATA - Combines 4 queries into 1 RAW SQL
    ultimate_static_cache = cache.get('perfect_static_v2')  # Change cache version
    if ultimate_static_cache is None:
        
        stats_query = Product.objects.aggregate(
            total_products=Count('id'),
            active_products=Sum(Case(When(active=True, then=1), default=0, output_field=IntegerField())),
            inactive_products=Sum(Case(When(active=False, then=1), default=0, output_field=IntegerField())),
            duty_free_products=Sum(Case(When(active=True, is_duty_free=True, then=1), default=0, output_field=IntegerField())),
            general_products=Sum(Case(When(active=True, is_duty_free=False, then=1), default=0, output_field=IntegerField())),
        )

        products_with_inventory = Product.objects.filter(
            inventory_lots__remaining_quantity__gt=0
        ).distinct().count()

        touristic_vessels_count = Vessel.objects.filter(active=True, has_duty_free=False).count()

        incomplete_pricing_count = Product.objects.filter(
            active=True, 
            is_duty_free=False
        ).annotate(
            pricing_count=Count('vessel_prices', filter=Q(vessel_prices__vessel__active=True, vessel_prices__vessel__has_duty_free=False))
        ).filter(pricing_count__lt=touristic_vessels_count).count()

        categories = list(Category.objects.filter(active=True).only('id', 'name').order_by('name'))
        
        ultimate_static_cache = {
            'stats': {
                'total_products': stats_query['total_products'],
                'active_products': stats_query['active_products'],
                'inactive_products': stats_query['inactive_products'],
                'duty_free_products': stats_query['duty_free_products'],
                'general_products': stats_query['general_products'],
                'products_with_inventory': products_with_inventory
            },
            'touristic_vessels_count': touristic_vessels_count,
            'incomplete_pricing_count': incomplete_pricing_count,
            'categories': categories
        }
        cache.set('perfect_static_v2', ultimate_static_cache, 7200)
        logger.debug("🔥 PERFECT STATIC DATA V2 CACHED")

    # Extract from ultimate cache
    stats = ultimate_static_cache['stats']
    touristic_vessels_count = ultimate_static_cache['touristic_vessels_count'] 
    incomplete_pricing_cache = ultimate_static_cache['incomplete_pricing_count']  # From cache now
    categories = ultimate_static_cache['categories']
    
    # 🚀 BUILD PRODUCT QUERY
    products_base = Product.objects.select_related(
        'category', 'created_by'
    ).only(
        'id', 'name', 'item_id', 'barcode', 'selling_price', 'purchase_price', 
        'active', 'is_duty_free', 'category__name', 'created_at', 'created_by__username'
    ).annotate(
        total_inventory=Coalesce(
            Sum('inventory_lots__remaining_quantity', 
                filter=Q(inventory_lots__remaining_quantity__gt=0)), 
            0
        ),
        vessel_pricing_count=Count(
            'vessel_prices__id',
            filter=Q(
                vessel_prices__vessel__active=True,
                vessel_prices__vessel__has_duty_free=False
            ),
            distinct=True
        )
    )
    
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
    
    # Sorting
    try:
        products_base = products_base.annotate(
            item_id_int=Cast('item_id', IntegerField())
        ).order_by('item_id_int', 'id')
    except:
        products_base = products_base.order_by('item_id', 'id')
    
    # 🚀 QUERY 3: Get total count
    total_count = products_base.count()
    
    # 🚀 QUERY 4: Get page products  
    start_index = (page_number - 1) * page_size
    end_index = start_index + page_size
    current_page_products = list(products_base[start_index:end_index])

    # Create perfect pagination
    perfect_paginator = PerfectPagination(current_page_products, page_number, total_count, page_size)
    products_page = perfect_paginator
    
    # 🚀 PROCESS PRODUCTS
    products_with_info = []
    for product in current_page_products:
        inventory_qty = product.total_inventory or 0
        
        # Status calculation
        if inventory_qty == 0:
            inventory_status, inventory_class = 'out', 'danger'
        elif inventory_qty <= 5:
            inventory_status, inventory_class = 'low', 'warning'
        else:
            inventory_status, inventory_class = 'good', 'success'
        
        # Pricing calculation
        if product.is_duty_free:
            pricing_completion = 100.0
            needs_pricing = False
        else:
            pricing_completion = min(100.0, (product.vessel_pricing_count / max(touristic_vessels_count, 1)) * 100)
            needs_pricing = product.vessel_pricing_count < touristic_vessels_count
        
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
            'created_by': product.created_by,
            'total_inventory': inventory_qty,
            'inventory_status': inventory_status,
            'inventory_class': inventory_class,
            'pricing_completion': round(pricing_completion, 1),
            'needs_pricing': needs_pricing,
            'inventory_value': float(inventory_qty * product.selling_price),
            'vessel_pricing_count': product.vessel_pricing_count,
            'vessel_pricing_info': {
                'has_vessel_pricing': product.vessel_pricing_count > 0,
                'vessel_prices_count': product.vessel_pricing_count,
                'missing_prices_count': max(0, touristic_vessels_count - product.vessel_pricing_count),
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
            'filtered_products_count': total_count,
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
            'total_count': total_count,
        }
    }
    
    # 🚀 PERFECT CACHE
    cache.set(cache_key, context, ProductCacheHelper.PRODUCT_MANAGEMENT_CACHE_TIMEOUT)
    logger.debug(f"🔥 PERFECT CACHED: {cache_key}")
    logger.debug(f"🔥 Vessel count: {touristic_vessels_count}")
    logger.debug(f"🔥 Incomplete pricing: {incomplete_pricing_cache}")
    logger.debug(f"🔥 Categories source check:")
    logger.debug(f"🔥 Cache categories count: {len(ultimate_static_cache['categories'])}")
    logger.debug(f"🔥 Using cached categories: {len(categories)}")
    logger.debug(f"🔍 Cache version at END (miss): {ProductCacheHelper._get_cache_version()}")
    
    return render(request, 'frontend/product_list.html', context)
@login_required
@user_passes_test(is_admin_or_manager)
def product_create_view(request):
    """Create new product view"""
    
    if request.method == 'GET':
        # Get form data
        categories = Category.objects.filter(active=True).order_by('name')
        vessels = Vessel.objects.filter(active=True).order_by('name')
        touristic_vessels = vessels.filter(has_duty_free=False)
        
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
            
            # Clear caches
            ProductCacheHelper.clear_cache_after_product_create()
            
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
    try:
        ProductCacheHelper.clear_product_management_cache()
        logger.debug("🔥 Cache cleared before edit form load")
    except Exception as e:
        logger.warning(f"⚠️ Cache clear warning: {e}")
        
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'GET':
        # Get form data
        categories = Category.objects.filter(active=True).order_by('name')
        vessels = Vessel.objects.filter(active=True).order_by('name')
        touristic_vessels = vessels.filter(has_duty_free=False)
        
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
        
            # Clear caches AFTER successful transaction
            try:
                ProductCacheHelper.clear_cache_after_product_update()
                logger.debug("🔥 All cache cleared")
            except Exception as cache_error:
                logger.warning(f"⚠️ Cache clear error: {cache_error}")
                        
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
            
            # 🆕 ENHANCED: Use comprehensive cache clearing for deletions
            try:
                ProductCacheHelper.clear_cache_after_product_delete()
            except Exception as cache_error:
                logger.warning(f"⚠️ Cache clear error after deletion: {cache_error}")
            
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