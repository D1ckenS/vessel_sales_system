from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import JsonResponse
from datetime import date, datetime
from frontend.utils.cache_helpers import VesselCacheHelper
from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, InventoryLot, get_available_inventory
from .utils import BilingualMessages
from products.models import Product
from django.db import transaction
import json
import uuid
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

@operations_access_required
def transfer_search_products(request):
    """AJAX endpoint to search for products with available inventory on specific vessel"""
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
        
        # Group by product and calculate totals
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
    
@operations_access_required
def transfer_entry(request):
    """Step 1: Create new transfer session"""
    
    if request.method == 'GET':
        vessels = VesselCacheHelper.get_active_vessels()
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
            
            transfer_date_obj = datetime.strptime(transfer_date, '%Y-%m-%d').date()
            
            # Create transfer session (stored in localStorage on frontend)
            
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

@operations_access_required
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

@operations_access_required
def transfer_available_products(request):
    """AJAX endpoint to get available products for transfer"""
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
        
        # Group by product and calculate totals
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

@operations_access_required
def transfer_bulk_complete(request):
    """Complete transfer with bulk transaction creation"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
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
    
@operations_access_required
def transfer_execute(request):
    """AJAX endpoint to execute transfer using existing FIFO system"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
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
        available_quantity, lots = get_available_inventory(from_vessel, product)
        
        if quantity > available_quantity:
            return JsonResponse({
                'success': False, 
                'error': f'Insufficient inventory. Available: {available_quantity}, Requested: {quantity}'
            })
        
        # Parse transfer date
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
                
        return JsonResponse({
            'success': True,
            'message': f'Transfer completed: {quantity} units of {product.name} from {from_vessel.name} to {to_vessel.name}',
            'transfer_id': transfer_out.id
        })
        
    except (Vessel.DoesNotExist, Product.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Vessel or product not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Transfer failed: {str(e)}'})