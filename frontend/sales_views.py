from django.forms import ValidationError
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import JsonResponse
from datetime import date
from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, InventoryLot, Trip, get_vessel_product_price, get_vessel_pricing_warnings, get_available_inventory
from .utils import BilingualMessages
from django.core.exceptions import ValidationError
import json
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
    """Step 1: Create new trip for sales transactions"""
    
    if request.method == 'GET':
        vessels = Vessel.objects.filter(active=True).order_by('name')
                
        # Get user's role
        user_role = get_user_role(request.user)
        
        # Filter recent trips based on user role
        if user_role == UserRoles.VESSEL_OPERATORS:
            # Vessel Operators see only today's trips
            today = date.today()
            recent_trips = Trip.objects.select_related('vessel', 'created_by').filter(
                trip_date=today
            ).order_by('-created_at')[:10]
        else:
            # Administrators, Managers, and higher roles see all recent trips
            recent_trips = Trip.objects.select_related('vessel', 'created_by').order_by('-created_at')[:10]
        
        context = {
            'vessels': vessels,
            'recent_trips': recent_trips,
            'today': date.today(),
            'user_role': user_role,  # Make sure this is included
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
            # Calculate COGS from FIFO consumption (parse from notes or recalculate)
            total_cogs = 0
            total_profit = 0
            
            try:
                # Try to parse COGS from notes if it was logged during sale
                if sale.notes and 'FIFO consumption:' in sale.notes:
                    # Parse the FIFO breakdown from notes
                    # Example: "FIFO consumption: 50 units @ 1.200 JOD; 50 units @ 1.150 JOD"
                    
                    fifo_pattern = r'(\d+(?:\.\d+)?)\s+units\s+@\s+(\d+(?:\.\d+)?)\s+JOD'
                    matches = re.findall(fifo_pattern, sale.notes)
                    
                    for qty_str, cost_str in matches:
                        consumed_qty = float(qty_str)
                        unit_cost = float(cost_str)
                        total_cogs += consumed_qty * unit_cost
                else:
                    # Fallback: estimate COGS using current available lots (not perfect but better than 0)
                    _, lots = get_available_inventory(sale.vessel, sale.product)
                    
                    if lots:
                        # Use average cost of current lots as estimate
                        avg_cost = sum(lot.purchase_price * lot.remaining_quantity for lot in lots) / sum(lot.remaining_quantity for lot in lots) if lots else 0
                        total_cogs = float(sale.quantity) * float(avg_cost)
                    else:
                        # Last resort: use product's default purchase price
                        total_cogs = float(sale.quantity) * float(sale.product.purchase_price)
                
                # Calculate profit
                total_revenue = float(sale.total_amount)
                total_profit = total_revenue - total_cogs
                
            except Exception as e:
                print(f"Error calculating COGS for sale {sale.id}: {e}")
                # Fallback to default purchase price
                total_cogs = float(sale.quantity) * float(sale.product.purchase_price)
                total_profit = float(sale.total_amount) - total_cogs
            
            completed_sales.append({
                'product_name': sale.product.name,
                'product_item_id': sale.product.item_id,
                'quantity': int(sale.quantity),
                'unit_price': float(sale.unit_price),
                'total_amount': float(sale.total_amount),
                'total_cogs': total_cogs,  # ✅ Added
                'total_profit': total_profit,  # ✅ Added
                'is_duty_free': sale.product.is_duty_free,  # ✅ Added
                'notes': sale.notes or '',
                'created_at': sale.created_at.strftime('%H:%M')
            })
    
    existing_sales_json = json.dumps(existing_sales)
    completed_sales_json = json.dumps(completed_sales)
    
    context = {
        'trip': trip,
        'existing_sales_json': existing_sales_json,  # JSON string
        'completed_sales_json': completed_sales_json,  # JSON string
        'can_edit': not trip.is_completed,  # Frontend can use this to show/hide edit features
    }
    
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
    
@operations_access_required
def trip_bulk_complete(request):
    """Complete trip with bulk transaction creation using vessel-specific pricing"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
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
        pricing_warnings = []
        
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
            
            # Get vessel-specific pricing
            actual_selling_price, is_custom_price, warning_message = get_vessel_product_price(trip.vessel, product)
            
            # Collect pricing warnings
            if warning_message:
                pricing_warnings.append({
                    'product_name': product.name,
                    'message': warning_message
                })
            
            # Check inventory availability
            available_quantity, lots = get_available_inventory(trip.vessel, product)
            
            if quantity > available_quantity:
                return JsonResponse({
                    'success': False, 
                    'error': f'Insufficient inventory for {product.name}. Available: {available_quantity}, Requested: {quantity}'
                })
            
            # Add to validated items with vessel-specific pricing
            validated_items.append({
                'product': product,
                'quantity': quantity,
                'notes': notes,
                'unit_price': actual_selling_price,  # Use vessel-specific price
                'revenue': quantity * actual_selling_price,
                'is_custom_price': is_custom_price
            })
            total_revenue += quantity * actual_selling_price
        
        # All items validated - now create transactions atomically
        
        with transaction.atomic():
            created_transactions = []
            
            for item in validated_items:
                # Create sale transaction with vessel-specific pricing
                sale_transaction = Transaction.objects.create(
                    vessel=trip.vessel,
                    product=item['product'],
                    transaction_type='SALE',
                    transaction_date=trip.trip_date,
                    quantity=item['quantity'],
                    unit_price=item['unit_price'],  # Vessel-specific price stored in transaction
                    trip=trip,
                    notes=item['notes'] or f'Sale for trip {trip.trip_number}',
                    created_by=request.user
                )
                created_transactions.append(sale_transaction)
            
            # Mark trip as completed
            trip.is_completed = True
            trip.save()
        
        response_data = {
            'success': True,
            'message': f'Trip {trip.trip_number} completed successfully!',
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



# Add this new view to handle trip cancellation

@operations_access_required
def trip_cancel(request):
    """Cancel trip and delete it from database (if no items committed)"""
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
            return JsonResponse({
                'success': True,
                'action': 'delete_trip',
                'message': f'Trip {trip_number} cancelled and removed.'
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