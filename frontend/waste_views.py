from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q, Sum
from django.http import JsonResponse
from datetime import date, datetime
from decimal import Decimal
import json
from frontend.utils.cache_helpers import VesselCacheHelper, WasteCacheHelper
from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, InventoryLot, WasteReport
from .utils import BilingualMessages
from .permissions import operations_access_required
from django.core.exceptions import ValidationError
from django.db import transaction

@login_required
def waste_entry(request):
    '''Step 1: Create new waste report for damaged/expired items'''
    
    # Check permissions (Inventory Staff, Managers, Administrators - NOT Vessel Operators)
    if not (request.user.groups.filter(name__in=['Inventory Staff', 'Managers', 'Administrators']).exists() or request.user.is_superuser):
        BilingualMessages.error(request, 'Access denied. Insufficient permissions.')
        return redirect('frontend:dashboard')
    
    if request.method == 'GET':
        vessels = VesselCacheHelper.get_active_vessels()
        
        # Get recent waste reports
        recent_reports = WasteReport.objects.select_related(
            'vessel', 'created_by'
        ).prefetch_related(
            'waste_transactions'
        ).order_by('-created_at')[:10]
        
        context = {
            'vessels': vessels,
            'recent_reports': recent_reports,
            'today': date.today(),
        }
        
        return render(request, 'frontend/waste_entry.html', context)
    
    elif request.method == 'POST':
        try:
            vessel_id = request.POST.get('vessel')
            report_number = request.POST.get('report_number', '').strip()
            report_date = request.POST.get('report_date')
            notes = request.POST.get('notes', '').strip()
            
            if not all([vessel_id, report_number, report_date]):
                BilingualMessages.error(request, 'required_fields_missing')
                return redirect('frontend:waste_entry')
            
            vessel = Vessel.objects.get(id=vessel_id, active=True)
            
            # Validate report number uniqueness
            if WasteReport.objects.filter(report_number=report_number).exists():
                BilingualMessages.error(request, 'waste_report_number_exists')
                return redirect('frontend:waste_entry')
            
            report_date_obj = datetime.strptime(report_date, '%Y-%m-%d').date()
            
            # Create waste report
            waste_report = WasteReport.objects.create(
                report_number=report_number,
                vessel=vessel,
                report_date=report_date_obj,
                notes=notes,
                created_by=request.user
            )
            
            WasteCacheHelper.clear_cache_after_waste_create()
            
            BilingualMessages.success(request, 'waste_report_created')
            return redirect('frontend:waste_items', waste_id=waste_report.id)
            
        except Exception as e:
            BilingualMessages.error(request, 'error_creating_waste_report')
            return redirect('frontend:waste_entry')

@login_required
def waste_items(request, waste_id):
    '''Step 2: Add damaged/expired items to waste report'''
    
    try:
        waste_report = WasteReport.objects.select_related('vessel').get(id=waste_id)
    except WasteReport.DoesNotExist:
        BilingualMessages.error(request, 'Waste report not found.')
        return redirect('frontend:waste_entry')
    
    # Get existing waste items
    existing_waste_items = []
    completed_waste_items = []
    
    if waste_report.is_completed:
        # For completed reports, show all items as completed
        waste_transactions = Transaction.objects.filter(
            waste_report=waste_report,
            transaction_type='WASTE'
        ).select_related('product').order_by('created_at')
        
        for waste in waste_transactions:
            completed_waste_items.append({
                'id': waste.id,
                'product_id': waste.product.id,
                'product_name': waste.product.name,
                'product_item_id': waste.product.item_id,
                'quantity': int(waste.quantity),
                'unit_price': float(waste.unit_price),
                'total_amount': float(waste.total_amount),
                'damage_reason': waste.damage_reason,
                'notes': waste.notes or '',
                'created_at': waste.created_at.strftime('%H:%M')
            })
    else:
        # For active reports, show items as existing/editable
        waste_transactions = Transaction.objects.filter(
            waste_report=waste_report,
            transaction_type='WASTE'
        ).select_related('product').order_by('created_at')
        
        for waste in waste_transactions:
            existing_waste_items.append({
                'id': waste.id,
                'product_id': waste.product.id,
                'product_name': waste.product.name,
                'product_item_id': waste.product.item_id,
                'quantity': int(waste.quantity),
                'unit_price': float(waste.unit_price),
                'total_amount': float(waste.total_amount),
                'damage_reason': waste.damage_reason,
                'notes': waste.notes or '',
                'created_at': waste.created_at.strftime('%H:%M')
            })
    
    # Convert to JSON for JavaScript
    existing_waste_items_json = json.dumps(existing_waste_items)
    completed_waste_items_json = json.dumps(completed_waste_items)
    
    context = {
        'waste_report': waste_report,
        'existing_waste_items_json': existing_waste_items_json,
        'completed_waste_items_json': completed_waste_items_json,
        'can_edit': not waste_report.is_completed,
        'damage_reasons': Transaction.DAMAGE_REASONS,
    }
    
    return render(request, 'frontend/waste_items.html', context)

@login_required
def waste_search_products(request):
    '''AJAX endpoint to search for products available on specific vessel'''
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        search_term = data.get('search', '').strip()
        vessel_id = data.get('vessel_id')
        
        if not search_term or not vessel_id:
            return JsonResponse({'success': False, 'error': 'Search term and vessel required'})
        
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
            
            # Get FIFO cost (oldest available lot)
            oldest_lot = InventoryLot.objects.filter(
                vessel=vessel,
                product_id=product_id,
                remaining_quantity__gt=0
            ).order_by('purchase_date', 'created_at').first()
            
            current_cost = oldest_lot.purchase_price if oldest_lot else 0
            
            products.append({
                'id': product_id,
                'name': summary['product__name'],
                'item_id': summary['product__item_id'],
                'barcode': summary['product__barcode'] or '',
                'is_duty_free': summary['product__is_duty_free'],
                'available_quantity': summary['total_quantity'],  # ← Fixed field name
                'current_cost': float(current_cost),
            })
        
        return JsonResponse({
            'success': True,
            'products': products
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def waste_available_products(request):
    """AJAX endpoint to get all products available for waste on specific vessel"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        vessel_id = data.get('vessel_id')
        
        if not vessel_id:
            return JsonResponse({'success': False, 'error': 'Vessel ID required'})
        
        vessel = Vessel.objects.get(id=vessel_id, active=True)
        
        # Get all products with available inventory on this vessel
        available_lots = InventoryLot.objects.filter(
            vessel=vessel,
            remaining_quantity__gt=0,
            product__active=True
        ).select_related('product')
        
        # Group by product and calculate totals
        product_summaries = available_lots.values(
            'product__id', 'product__name', 'product__item_id', 
            'product__barcode', 'product__is_duty_free',
            'product__category__name'
        ).annotate(
            total_quantity=Sum('remaining_quantity')
        ).order_by('product__item_id')
        
        products = []
        for summary in product_summaries:
            product_id = summary['product__id']
            
            # Get FIFO cost (oldest available lot)
            oldest_lot = InventoryLot.objects.filter(
                vessel=vessel,
                product_id=product_id,
                remaining_quantity__gt=0
            ).order_by('purchase_date', 'created_at').first()
            
            current_cost = oldest_lot.purchase_price if oldest_lot else 0
            
            # Get detailed lots information for this product
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
                'category': summary['product__category__name'],
                'is_duty_free': summary['product__is_duty_free'],
                'available_quantity': summary['total_quantity'],  # ← Fixed field name
                'current_cost': float(current_cost),
                'lots': lots_data
            })
        
        return JsonResponse({
            'success': True,
            'products': products,
            'vessel_name': vessel.name
        })
        
    except Vessel.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Vessel not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def waste_bulk_complete(request):
    '''Complete waste report with multiple waste items'''
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        waste_id = data.get('waste_id')
        items = data.get('items', [])
        
        if not waste_id or not items:
            return JsonResponse({'success': False, 'error': 'Waste ID and items required'})
        
        waste_report = WasteReport.objects.select_related('vessel').get(id=waste_id)
        
        if waste_report.is_completed:
            return JsonResponse({'success': False, 'error': 'Waste report is already completed'})
        
        created_transactions = []
        total_cost = 0
        
        # FIXED: Use select_for_update to prevent database locks
        with transaction.atomic():
            # Lock the waste report to prevent concurrent updates
            waste_report = WasteReport.objects.select_for_update().get(id=waste_id)
            
            # Clear existing transactions for this waste report
            Transaction.objects.filter(waste_report=waste_report, transaction_type='WASTE').delete()
            
            # Process each waste item
            for item in items:
                product_id = item.get('product_id')
                quantity = Decimal(str(item.get('quantity', 0)))
                damage_reason = item.get('damage_reason', '')
                notes = item.get('notes', '').strip()
                
                if quantity <= 0:
                    continue
                
                try:
                    product = Product.objects.select_for_update().get(id=product_id)
                    
                    # Get FIFO cost for waste tracking
                    oldest_lot = InventoryLot.objects.filter(
                        vessel=waste_report.vessel,
                        product=product,
                        remaining_quantity__gt=0
                    ).order_by('purchase_date', 'created_at').first()
                    
                    if not oldest_lot:
                        continue  # Skip if no inventory available
                    
                    unit_cost = oldest_lot.purchase_price
                    
                    # Create waste transaction
                    waste_transaction = Transaction.objects.create(
                        vessel=waste_report.vessel,
                        product=product,
                        transaction_type='WASTE',
                        quantity=quantity,
                        unit_price=unit_cost,
                        transaction_date=waste_report.report_date,
                        waste_report=waste_report,
                        damage_reason=damage_reason,
                        notes=f"Waste Report: {waste_report.report_number}. Reason: {damage_reason}. {notes}",
                        created_by=request.user
                    )
                    
                    created_transactions.append(waste_transaction)
                    total_cost += quantity * unit_cost
                    
                except Product.DoesNotExist:
                    continue  # Skip invalid products
            
            # Mark waste report as completed
            waste_report.is_completed = True
            waste_report.save()
            WasteCacheHelper.clear_cache_after_waste_complete(waste_report.id)
        
        return JsonResponse({
            'success': True,
            'message': f'Waste report {waste_report.report_number} completed successfully with {len(created_transactions)} items!',
            'waste_data': {
                'report_number': waste_report.report_number,
                'items_count': len(created_transactions),
                'total_cost': float(total_cost),
                'vessel': waste_report.vessel.name
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error completing waste report: {str(e)}'})

@login_required
def waste_cancel(request):
    '''Cancel waste report and delete it from database (if no items committed)'''
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        waste_id = data.get('waste_id')
        
        if not waste_id:
            return JsonResponse({'success': False, 'error': 'Waste ID required'})
        
        # Get waste report
        waste_report = WasteReport.objects.get(id=waste_id)
        
        if waste_report.is_completed:
            return JsonResponse({'success': False, 'error': 'Cannot cancel completed waste report'})
        
        # Check if waste report has any committed transactions
        existing_transactions = Transaction.objects.filter(waste_report=waste_report).count()
        
        if existing_transactions > 0:
            # Waste report has committed transactions - just clear cart but keep report
            return JsonResponse({
                'success': True,
                'action': 'clear_cart',
                'message': f'Cart cleared. Waste report {waste_report.report_number} kept (has committed transactions).'
            })
        else:
            # No committed transactions - safe to delete waste report
            report_number = waste_report.report_number
            waste_report.delete()
            
            WasteCacheHelper.clear_cache_after_waste_delete(waste_id)
            
            return JsonResponse({
                'success': True,
                'action': 'delete_report',
                'message': f'Waste report {report_number} cancelled and removed.',
                'redirect_url': '/waste/'  # Redirect back to waste entry
            })
        
    except WasteReport.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Waste report not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error cancelling waste report: {str(e)}'})