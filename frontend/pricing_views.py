from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db import transaction
from decimal import Decimal
import json
from vessels.models import Vessel
from products.models import Product
from transactions.models import VesselProductPrice, get_all_vessel_pricing_summary, get_vessel_pricing_warnings
from .permissions import admin_or_manager_required

@login_required
@user_passes_test(admin_or_manager_required)
def bulk_pricing_management(request):
    """Bulk vessel pricing management interface"""
    
    # Get all touristic vessels and general products
    touristic_vessels = Vessel.objects.filter(active=True, has_duty_free=False).order_by('name')
    general_products = Product.objects.filter(active=True, is_duty_free=False).order_by('item_id')
    
    # Get existing pricing data
    existing_prices = {}
    vessel_prices = VesselProductPrice.objects.select_related('vessel', 'product')
    for vp in vessel_prices:
        key = f"{vp.vessel.id}_{vp.product.id}"
        existing_prices[key] = {
            'price': vp.selling_price,
            'created_at': vp.created_at,
            'updated_at': vp.updated_at
        }
    
    # Get pricing summary
    pricing_summary = get_all_vessel_pricing_summary()
    
    # Calculate completion stats
    total_combinations = len(touristic_vessels) * len(general_products)
    completed_combinations = len(existing_prices)
    completion_percentage = (completed_combinations / max(total_combinations, 1)) * 100
    
    context = {
        'touristic_vessels': touristic_vessels,
        'general_products': general_products,
        'existing_prices': existing_prices,
        'pricing_summary': pricing_summary,
        'stats': {
            'total_vessels': len(touristic_vessels),
            'total_products': len(general_products),
            'total_combinations': total_combinations,
            'completed_combinations': completed_combinations,
            'completion_percentage': completion_percentage,
            'missing_combinations': total_combinations - completed_combinations
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