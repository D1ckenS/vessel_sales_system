from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db import transaction
from decimal import Decimal
from django.db.models import Avg, Sum, Count, F, Q, Case, When, Max, Min
import json
from vessels.models import Vessel
from products.models import Product
from transactions.models import VesselProductPrice, get_all_vessel_pricing_summary, get_vessel_pricing_warnings
from .permissions import admin_or_manager_required

@login_required
@user_passes_test(admin_or_manager_required)
def bulk_pricing_management(request):
    """OPTIMIZED: Bulk vessel pricing management interface with fixed annotations"""
    
    # OPTIMIZED: Get touristic vessels with pricing statistics
    touristic_vessels = Vessel.objects.filter(
        active=True, 
        has_duty_free=False
    ).annotate(
        # Count custom prices for each vessel
        custom_prices_count=Count(
            'custom_prices',
            filter=Q(
                custom_prices__product__active=True,
                custom_prices__product__is_duty_free=False
            )
        )
    ).order_by('name')
    
    # OPTIMIZED: Get general products with pricing status
    general_products_with_stats = Product.objects.filter(
        active=True, 
        is_duty_free=False
    ).annotate(
        # Count how many vessels have custom pricing for this product
        vessels_with_custom_price=Count(
            'vessel_prices',
            filter=Q(
                vessel_prices__vessel__active=True,
                vessel_prices__vessel__has_duty_free=False
            )
        )
    ).select_related('category').order_by('item_id')
    
    # Convert to list to avoid reusing the annotated queryset
    general_products = list(general_products_with_stats)
    
    # OPTIMIZED: Get existing pricing data efficiently
    vessel_prices_qs = VesselProductPrice.objects.select_related(
        'vessel', 'product'
    ).filter(
        vessel__active=True,
        vessel__has_duty_free=False,
        product__active=True,
        product__is_duty_free=False
    )
    
    # Build existing prices dictionary more efficiently
    existing_prices = {
        f"{vp.vessel_id}_{vp.product_id}": {
            'price': vp.selling_price,
            'created_at': vp.created_at,
            'updated_at': vp.updated_at,
            'vessel_name': vp.vessel.name,
            'product_name': vp.product.name
        }
        for vp in vessel_prices_qs
    }
    
    # OPTIMIZED: Calculate completion stats efficiently
    total_general_products = len(general_products)
    total_touristic_vessels = touristic_vessels.count()
    total_combinations = total_touristic_vessels * total_general_products
    completed_combinations = len(existing_prices)
    completion_percentage = (completed_combinations / max(total_combinations, 1)) * 100
    
    # OPTIMIZED: Get pricing summary with cached calculations
    pricing_summary = {}
    for vessel in touristic_vessels:
        vessel_completion = (vessel.custom_prices_count / max(total_general_products, 1)) * 100
        pricing_summary[vessel.id] = {
            'vessel_name': vessel.name,
            'products_priced': vessel.custom_prices_count,
            'total_products': total_general_products,
            'completion_percentage': round(vessel_completion, 1),
            'missing_count': total_general_products - vessel.custom_prices_count,
            'has_warnings': vessel.custom_prices_count < total_general_products
        }
    
    # FIXED: Product pricing statistics using annotated values correctly
    product_pricing_stats = {}
    for product in general_products:
        # Access the annotated field correctly
        vessels_covered = product.vessels_with_custom_price
        coverage_percentage = (vessels_covered / max(total_touristic_vessels, 1)) * 100
        product_pricing_stats[product.id] = {
            'product_name': product.name,
            'vessels_covered': vessels_covered,
            'total_vessels': total_touristic_vessels,
            'coverage_percentage': round(coverage_percentage, 1),
            'missing_vessels': total_touristic_vessels - vessels_covered,
            'needs_attention': vessels_covered < total_touristic_vessels
        }
    
    # Calculate additional statistics
    vessels_with_complete_pricing = sum(1 for v in pricing_summary.values() if v['completion_percentage'] == 100)
    products_with_complete_pricing = sum(1 for p in product_pricing_stats.values() if p['coverage_percentage'] == 100)
    
    context = {
        'touristic_vessels': touristic_vessels,
        'general_products': general_products,
        'existing_prices': existing_prices,
        'pricing_summary': pricing_summary,
        'product_pricing_stats': product_pricing_stats,
        'stats': {
            'total_vessels': total_touristic_vessels,
            'total_products': total_general_products,
            'total_combinations': total_combinations,
            'completed_combinations': completed_combinations,
            'completion_percentage': round(completion_percentage, 1),
            'missing_combinations': total_combinations - completed_combinations,
            'vessels_with_complete_pricing': vessels_with_complete_pricing,
            'products_with_complete_pricing': products_with_complete_pricing
        }
    }
    
    return render(request, 'frontend/bulk_pricing_management.html', context)

@login_required
@user_passes_test(admin_or_manager_required)
def update_vessel_pricing(request):
    """AJAX endpoint to update vessel pricing"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        vessel_id = data.get('vessel_id')
        product_id = data.get('product_id')
        price = data.get('price')
        action = data.get('action', 'update')  # 'update' or 'delete'
        
        if not vessel_id or not product_id:
            return JsonResponse({'success': False, 'error': 'Vessel and product IDs required'})
        
        vessel = Vessel.objects.get(id=vessel_id)
        product = Product.objects.get(id=product_id)
        
        # Validate vessel is touristic and product is general
        if vessel.has_duty_free:
            return JsonResponse({'success': False, 'error': 'Vessel-specific pricing only for touristic vessels'})
        
        if product.is_duty_free:
            return JsonResponse({'success': False, 'error': 'Vessel-specific pricing only for general products'})
        
        if action == 'delete':
            # Remove vessel pricing
            VesselProductPrice.objects.filter(vessel=vessel, product=product).delete()
            return JsonResponse({
                'success': True,
                'message': f'Custom pricing removed for {product.name} on {vessel.name}',
                'action': 'deleted'
            })
        
        elif action == 'update':
            if not price:
                return JsonResponse({'success': False, 'error': 'Price is required'})
            
            try:
                price_decimal = Decimal(str(price))
                if price_decimal <= 0:
                    return JsonResponse({'success': False, 'error': 'Price must be greater than 0'})
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'error': 'Invalid price format'})
            
            # Update or create vessel pricing
            vessel_price, created = VesselProductPrice.objects.update_or_create(
                vessel=vessel,
                product=product,
                defaults={
                    'selling_price': price_decimal,
                    'created_by': request.user
                }
            )
            
            action_text = 'created' if created else 'updated'
            return JsonResponse({
                'success': True,
                'message': f'Custom pricing {action_text} for {product.name} on {vessel.name}',
                'action': action_text,
                'price': float(price_decimal),
                'difference': float(price_decimal - product.selling_price),
                'difference_percent': float(((price_decimal - product.selling_price) / product.selling_price) * 100)
            })
        
        else:
            return JsonResponse({'success': False, 'error': 'Invalid action'})
        
    except (Vessel.DoesNotExist, Product.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Vessel or product not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(admin_or_manager_required)
def bulk_update_pricing(request):
    """Bulk update pricing for multiple products/vessels"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        updates = data.get('updates', [])  # Array of {vessel_id, product_id, price}
        
        if not updates:
            return JsonResponse({'success': False, 'error': 'No updates provided'})
        
        successful_updates = 0
        failed_updates = []
        
        with transaction.atomic():
            for update in updates:
                try:
                    vessel_id = update.get('vessel_id')
                    product_id = update.get('product_id')
                    price = update.get('price')
                    
                    if not all([vessel_id, product_id, price]):
                        failed_updates.append(f"Missing data for update: {update}")
                        continue
                    
                    vessel = Vessel.objects.get(id=vessel_id)
                    product = Product.objects.get(id=product_id)
                    price_decimal = Decimal(str(price))
                    
                    # Validate
                    if vessel.has_duty_free or product.is_duty_free:
                        failed_updates.append(f"Invalid vessel-product combination: {vessel.name} - {product.name}")
                        continue
                    
                    if price_decimal <= 0:
                        failed_updates.append(f"Invalid price for {product.name}: {price}")
                        continue
                    
                    # Update or create
                    VesselProductPrice.objects.update_or_create(
                        vessel=vessel,
                        product=product,
                        defaults={
                            'selling_price': price_decimal,
                            'created_by': request.user
                        }
                    )
                    successful_updates += 1
                    
                except Exception as e:
                    failed_updates.append(f"Error updating {update}: {str(e)}")
        
        return JsonResponse({
            'success': True,
            'successful_updates': successful_updates,
            'failed_updates': len(failed_updates),
            'errors': failed_updates,
            'message': f'Bulk update completed: {successful_updates} successful, {len(failed_updates)} failed'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(admin_or_manager_required)
def copy_pricing_template(request):
    """Copy pricing from one vessel to others"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        source_vessel_id = data.get('source_vessel_id')
        target_vessel_ids = data.get('target_vessel_ids', [])
        overwrite = data.get('overwrite', False)
        
        if not source_vessel_id or not target_vessel_ids:
            return JsonResponse({'success': False, 'error': 'Source and target vessels required'})
        
        source_vessel = Vessel.objects.get(id=source_vessel_id)
        target_vessels = Vessel.objects.filter(id__in=target_vessel_ids)
        
        # Get source vessel pricing
        source_prices = VesselProductPrice.objects.filter(vessel=source_vessel)
        
        if not source_prices.exists():
            return JsonResponse({'success': False, 'error': f'No pricing found for {source_vessel.name}'})
        
        copied_count = 0
        skipped_count = 0
        
        with transaction.atomic():
            for target_vessel in target_vessels:
                for source_price in source_prices:
                    existing = VesselProductPrice.objects.filter(
                        vessel=target_vessel, 
                        product=source_price.product
                    ).exists()
                    
                    if existing and not overwrite:
                        skipped_count += 1
                        continue
                    
                    VesselProductPrice.objects.update_or_create(
                        vessel=target_vessel,
                        product=source_price.product,
                        defaults={
                            'selling_price': source_price.selling_price,
                            'created_by': request.user
                        }
                    )
                    copied_count += 1
        
        return JsonResponse({
            'success': True,
            'copied_count': copied_count,
            'skipped_count': skipped_count,
            'message': f'Copied {copied_count} prices, skipped {skipped_count} existing'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})