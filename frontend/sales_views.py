from django.shortcuts import render, redirect
from django.db.models import Q, Sum, Prefetch
from django.http import JsonResponse
from datetime import date
from frontend.utils.cache_helpers import VesselCacheHelper, TripCacheHelper
from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, InventoryLot, Trip, get_vessel_product_price, get_vessel_pricing_warnings, get_available_inventory
from .utils import BilingualMessages
from django.core.exceptions import ValidationError
import json
from decimal import Decimal
from django.db import transaction
import re
from datetime import datetime
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required,
    get_user_role,
    UserRoles
)

@operations_access_required
def sales_entry(request):
    """Step 1: Create new trip for sales transactions - OPTIMIZED"""
    
    if request.method == 'GET':
        print(f"🔍 REQUEST INFO:")
        print(f"   Method: {request.method}")
        print(f"   Headers: {dict(request.headers)}")
        print(f"   User Agent: {request.META.get('HTTP_USER_AGENT', 'Unknown')}")
        print(f"   Referer: {request.META.get('HTTP_REFERER', 'None')}")
        print(f"   Cache-Control: {request.META.get('HTTP_CACHE_CONTROL', 'None')}")
        
        vessels = VesselCacheHelper.get_active_vessels()
                
        # Get user's role
        user_role = get_user_role(request.user)
        
        # 🚀 OPTIMIZED: Check cache for recent trips with revenue data
        today = date.today() if user_role == UserRoles.VESSEL_OPERATORS else None
        
        # Try robust cache first (survives browser navigation better)
        cached_trips = TripCacheHelper.get_recent_trips_with_revenue_robust(str(user_role), today)
        
        if cached_trips:
            print(f"🚀 ROBUST CACHE HIT: Recent trips for {user_role} ({len(cached_trips)} trips)")
            recent_trips = cached_trips
        else:
            print(f"🔍 ROBUST CACHE MISS: Building recent trips for {user_role}")
            
            # 🚀 OPTIMIZED: Single query with proper prefetching
            base_query = Trip.objects.select_related(
                'vessel', 'created_by'
            ).prefetch_related(
                Prefetch(
                    'sales_transactions',
                    queryset=Transaction.objects.select_related('product')
                )
            )
            
            # Filter recent trips based on user role
            if user_role == UserRoles.VESSEL_OPERATORS:
                recent_trips_query = base_query.filter(
                    trip_date=today
                ).order_by('-created_at')[:10]
            else:
                recent_trips_query = base_query.order_by('-created_at')[:10]
            
            # 🚀 OPTIMIZED: Process trips with prefetched data (no additional queries)
            recent_trips = []
            for trip in recent_trips_query:
                sales_transactions = trip.sales_transactions.all()
                total_revenue = sum(
                    float(txn.quantity) * float(txn.unit_price) 
                    for txn in sales_transactions
                )
                transaction_count = len(sales_transactions)
                
                trip.calculated_total_revenue = total_revenue
                trip.calculated_transaction_count = transaction_count
                recent_trips.append(trip)
            
            # 🚀 ROBUST CACHE: Store with longer timeout for browser navigation
            TripCacheHelper.cache_recent_trips_with_revenue_robust(str(user_role), recent_trips, today)
        
        context = {
            'vessels': vessels,
            'recent_trips': recent_trips,
            'today': date.today(),
            'user_role': user_role,
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
            
            # 🚀 CACHE: Clear recent trips cache after creation
            TripCacheHelper.clear_cache_after_trip_create()
            
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

@operations_access_required
def trip_sales(request, trip_id):
    """Step 2: Multi-item sales entry for a specific trip (Shopping Cart Approach) - OPTIMIZED"""
    
    # 🚀 OPTIMIZED: Check cache first for completed trips (no DB query needed)
    from frontend.utils.cache_helpers import TripCacheHelper
    
    cached_data = TripCacheHelper.get_completed_trip_data(trip_id)
    if cached_data:
        print(f"🚀 CACHE HIT: Completed trip {trip_id}")
        return render(request, 'frontend/trip_sales.html', cached_data)
    
    try:
        # 🚀 SUPER OPTIMIZED: Single query with everything
        trip = Trip.objects.select_related(
            'vessel', 'created_by'
        ).prefetch_related(
            Prefetch(
                'sales_transactions',
                queryset=Transaction.objects.select_related(
                    'product', 'product__category'
                ).order_by('created_at')
            )
        ).get(id=trip_id)
        
        # 🚀 FORCE: Get all transactions immediately to prevent additional queries
        sales_transactions = list(trip.sales_transactions.all())
        
    except Trip.DoesNotExist:
        BilingualMessages.error(request, 'Trip not found.')
        return redirect('frontend:sales_entry')
    
    # Prepare context data
    existing_sales = []
    completed_sales = []
    
    if not trip.is_completed:
        # 🚀 OPTIMIZED: Process incomplete trip using prefetched data
        for sale in sales_transactions:
            existing_sales.append({
                'id': sale.id,
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
    else:
        # 🚀 OPTIMIZED: Process completed trip using prefetched data
        for sale in sales_transactions:
            # Calculate COGS from FIFO consumption (parse from notes or recalculate)
            total_cogs = 0
            total_profit = 0
            
            try:
                # Try to parse COGS from notes if it was logged during sale
                if sale.notes and 'FIFO consumption:' in sale.notes:
                    # Parse the FIFO breakdown from notes
                    fifo_pattern = r'(\d+(?:\.\d+)?)\s+units\s+@\s+(\d+(?:\.\d+)?)\s+JOD'
                    matches = re.findall(fifo_pattern, sale.notes)
                    
                    for qty_str, price_str in matches:
                        qty = float(qty_str)
                        price = float(price_str)
                        total_cogs += qty * price
                    
                    total_profit = float(sale.total_amount) - total_cogs
                else:
                    # Fallback: estimate COGS as 70% of selling price
                    total_cogs = float(sale.total_amount) * 0.7
                    total_profit = float(sale.total_amount) * 0.3
                    
            except (ValueError, AttributeError):
                # Fallback calculation
                total_cogs = float(sale.total_amount) * 0.7
                total_profit = float(sale.total_amount) * 0.3
            
            completed_sales.append({
                'id': sale.id,
                'product_id': sale.product.id,
                'product_name': sale.product.name,
                'product_item_id': sale.product.item_id,
                'product_barcode': sale.product.barcode or '',
                'quantity': int(sale.quantity),
                'unit_price': float(sale.unit_price),
                'total_amount': float(sale.total_amount),
                'total_cogs': total_cogs,
                'total_profit': total_profit,
                'is_duty_free': sale.product.is_duty_free,
                'notes': sale.notes or '',
                'created_at': sale.created_at.strftime('%H:%M')
            })
    
    # Convert to JSON for frontend
    existing_sales_json = json.dumps(existing_sales)
    completed_sales_json = json.dumps(completed_sales)
    
    # Build final context
    context = {
        'trip': trip,
        'existing_sales_json': existing_sales_json,
        'completed_sales_json': completed_sales_json,
        'can_edit': not trip.is_completed,
    }
    
    # 🚀 CACHE: Store completed trip data for future requests
    if trip.is_completed:
        from frontend.utils.cache_helpers import TripCacheHelper
        TripCacheHelper.cache_completed_trip_data(trip_id, context)
    
    return render(request, 'frontend/trip_sales.html', context)

@operations_access_required
def sales_search_products(request):
    """AJAX endpoint to search for products available on specific vessel"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
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

@operations_access_required
def sales_validate_inventory(request):
    """AJAX endpoint to validate inventory and preview FIFO consumption"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
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
    
# Add this import at the top of sales_views.py
from frontend.utils.cache_helpers import TripCacheHelper

@operations_access_required
def trip_bulk_complete(request):
    """Complete trip with multiple sales items (AJAX) - CACHE AWARE"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        trip_id = data.get('trip_id')
        sales_items = data.get('sales_items', [])
        
        if not trip_id or not sales_items:
            return JsonResponse({'success': False, 'error': 'Trip ID and sales items required'})
        
        # Get trip
        trip = Trip.objects.select_related('vessel').get(id=trip_id)
        
        if trip.is_completed:
            return JsonResponse({'success': False, 'error': 'Trip is already completed'})
        
        created_transactions = []
        total_revenue = 0
        pricing_warnings = []
        
        with transaction.atomic():
            # Clear existing transactions for this trip (if any)
            existing_sales_transactions = Transaction.objects.filter(
                trip=trip, 
                transaction_type='SALE'
            )

            if existing_sales_transactions.exists():
                print(f"🔄 TRIP EDIT: Deleting {existing_sales_transactions.count()} existing sales transactions individually for inventory restoration")
                
                # Delete each transaction individually to trigger inventory restoration
                for txn in existing_sales_transactions:
                    txn.delete()  # This calls the individual delete() method with inventory restoration
                
                print(f"✅ TRIP EDIT: Inventory restored for {existing_sales_transactions.count()} transactions")
            
            # Process each sales item
            for item in sales_items:
                product_id = item.get('product_id')
                quantity = Decimal(str(item.get('quantity', 0)))
                unit_price = Decimal(str(item.get('unit_price', 0)))
                notes = item.get('notes', '').strip()
                
                if quantity <= 0 or unit_price <= 0:
                    continue
                
                # Get product
                product = Product.objects.get(id=product_id)
                
                # Check vessel-specific pricing
                vessel_price = get_vessel_product_price(trip.vessel, product)
                if not vessel_price:
                    pricing_warnings.append({
                        'product_name': product.name,
                        'vessel_name': trip.vessel.name,
                        'used_price': float(unit_price)
                    })
                
                # Create sales transaction
                sale_transaction = Transaction.objects.create(
                    vessel=trip.vessel,
                    product=product,
                    transaction_type='SALE',
                    quantity=quantity,
                    unit_price=unit_price,
                    transaction_date=trip.trip_date,
                    trip=trip,
                    notes=notes,
                    created_by=request.user
                )
                
                created_transactions.append(sale_transaction)
                total_revenue += quantity * unit_price
                
            # 🚀 CACHE: Clear cache after adding transactions (before completion)
            if created_transactions:
                TripCacheHelper.clear_recent_trips_cache_only_when_needed()
                print(f"🔥 Cache cleared after adding {len(created_transactions)} transactions")
            
            # Mark trip as completed
            trip.is_completed = True
            trip.save()
    
            # 🚀 CACHE: Clear trip cache after completion
            TripCacheHelper.clear_cache_after_trip_update(trip_id)
            TripCacheHelper.clear_cache_after_trip_complete(trip_id)
        
        # Build success response
        response_data = {
            'success': True,
            'message': f'Trip {trip.trip_number} completed successfully with {len(created_transactions)} items!',
            'trip_data': {
                'trip_number': trip.trip_number,
                'items_count': len(created_transactions),
                'total_revenue': float(total_revenue),
                'vessel': trip.vessel.name
            }
        }
        
        # Include pricing warnings if any
        if pricing_warnings:
            response_data['pricing_warnings'] = pricing_warnings
            response_data['warning_message'] = f"⚠️ {len(pricing_warnings)} items used default pricing on touristic vessel"
        
        return JsonResponse(response_data)
        
    except Trip.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Trip not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error completing trip: {str(e)}'})


@operations_access_required
def trip_cancel(request):
    """Cancel trip and delete it from database (if no items committed) - CACHE AWARE"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
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
            
            # 🚀 CACHE: Clear trip cache after deletion
            TripCacheHelper.clear_cache_after_trip_delete(trip_id)
            
            return JsonResponse({
                'success': True,
                'action': 'delete_trip',
                'message': f'Trip {trip_number} cancelled and removed.',
                'redirect_url': '/sales/'  # Redirect back to sales entry
            })
        
    except Trip.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Trip not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error cancelling trip: {str(e)}'})
    
@operations_access_required
def sales_available_products(request):
    """AJAX endpoint to get available products for sales with vessel-specific pricing"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
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
        product_summaries = available_lots.values(
            'product__id', 'product__name', 'product__item_id', 
            'product__barcode', 'product__is_duty_free',
            'product__selling_price'
        ).annotate(
            total_quantity=Sum('remaining_quantity')
        ).order_by('product__item_id')
        
        products = []
        pricing_warnings = []
        
        for summary in product_summaries:
            product_id = summary['product__id']
            product = Product.objects.get(id=product_id)
            
            # Get vessel-specific pricing
            actual_price, is_custom_price, warning_message = get_vessel_product_price(vessel, product)
            
            # Collect warnings for non-duty-free vessels using default pricing
            if warning_message:
                pricing_warnings.append({
                    'product_id': product_id,
                    'product_name': product.name,
                    'message': warning_message
                })
            
            products.append({
                'id': product_id,
                'name': summary['product__name'],
                'item_id': summary['product__item_id'],
                'barcode': summary['product__barcode'] or '',
                'is_duty_free': summary['product__is_duty_free'],
                'selling_price': float(actual_price),  # Use vessel-specific price
                'default_price': float(product.selling_price),  # Include default for comparison
                'is_custom_price': is_custom_price,
                'total_quantity': summary['total_quantity'],
            })
        
        # Get overall vessel pricing warnings
        vessel_warnings = get_vessel_pricing_warnings(vessel)
        
        return JsonResponse({
            'success': True,
            'products': products,
            'pricing_warnings': pricing_warnings,
            'vessel_warnings': {
                'has_warnings': vessel_warnings['has_warnings'],
                'missing_price_count': vessel_warnings['missing_price_count'],
                'message': vessel_warnings['message'],
                'detailed_message': f"⚠️ {vessel_warnings['missing_price_count']} products missing custom pricing for {vessel.name}" if vessel_warnings['has_warnings'] else None
            },
            'vessel_info': {
                'name': vessel.name,
                'is_touristic': not vessel.has_duty_free,
                'pricing_completion': ((vessel_warnings.get('total_products', 0) - vessel_warnings['missing_price_count']) / max(vessel_warnings.get('total_products', 0), 1)) * 100 if vessel_warnings.get('total_products') else 100
            }
        })
        
    except Vessel.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Vessel not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@operations_access_required
def sales_calculate_cogs(request):
    """AJAX endpoint to calculate COGS for sales using FIFO simulation with vessel-specific pricing"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        vessel_id = data.get('vessel_id')
        product_id = data.get('product_id')
        quantity = data.get('quantity', 0)
        
        if not all([vessel_id, product_id]) or quantity <= 0:
            return JsonResponse({'success': False, 'error': 'Invalid parameters'})
        
        # Get objects
        vessel = Vessel.objects.get(id=vessel_id, active=True)
        product = Product.objects.get(id=product_id, active=True)
        
        # Get vessel-specific pricing
        actual_selling_price, is_custom_price, warning_message = get_vessel_product_price(vessel, product)
        
        # Get available inventory and FIFO lots
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
        
        # Calculate profit using vessel-specific selling price
        total_revenue = quantity * actual_selling_price
        total_profit = total_revenue - total_fifo_cost
        
        response_data = {
            'success': True,
            'total_cogs': float(total_fifo_cost),
            'total_revenue': float(total_revenue),
            'total_profit': float(total_profit),
            'consumption_breakdown': consumption_preview,
            'pricing_info': {
                'selling_price': float(actual_selling_price),
                'default_price': float(product.selling_price),
                'is_custom_price': is_custom_price,
                'price_difference': float(actual_selling_price - product.selling_price)
            }
        }
        
        # Add warning if using default price on touristic vessel
        if warning_message:
            response_data['pricing_warning'] = warning_message
        
        return JsonResponse(response_data)
        
    except (Vessel.DoesNotExist, Product.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Vessel or product not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
@operations_access_required
def sales_execute(request):
    """AJAX endpoint to execute sales transaction using FIFO system"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
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
        available_quantity, lots = get_available_inventory(vessel, product)
        
        if quantity > available_quantity:
            return JsonResponse({
                'success': False, 
                'error': f'Insufficient inventory. Available: {available_quantity}, Requested: {quantity}'
            })
        
        # Parse sale date
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