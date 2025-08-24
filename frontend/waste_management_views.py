from django.urls import reverse
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from frontend.utils.cache_helpers import VesselCacheHelper, WasteCacheHelper, get_optimized_pagination
from .utils.query_helpers import TransactionQueryHelper
from .utils.response_helpers import JsonResponseHelper
from .utils.crud_helpers import CRUDHelper, AdminActionHelper
from .permissions import is_admin_or_manager
from django.core.exceptions import ValidationError
from transactions.models import Transaction
from django.shortcuts import render
from transactions.models import WasteReport
from datetime import datetime
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from datetime import timedelta
from django.utils import timezone
import json
import logging
from django.db import transaction

logger = logging.getLogger('frontend')

@login_required
@user_passes_test(is_admin_or_manager)
def waste_management(request):
    """OPTIMIZED: Waste report management with COUNT-free pagination"""
    
    # 🚀 CACHE: Check for cached waste report list (only when no filters applied)
    has_filters = any([
        request.GET.get('search', ''),
        request.GET.get('vessel', ''),
        request.GET.get('status', ''),
        request.GET.get('date_from', ''),
        request.GET.get('date_to', '')
    ])
    
    using_cached_data = False
    
    if not has_filters:
        cached_waste_list = WasteCacheHelper.get_waste_mgmt_list()
        
        if cached_waste_list:
            logger.debug(f"Cache hit: Waste Management List ({len(cached_waste_list)} waste reports)")
            waste_reports = cached_waste_list
            using_cached_data = True
        else:
            logger.debug("Cache miss: Building waste management list")
            
            # 🚀 OPTIMIZED: Build and cache evaluated list of waste report objects
            waste_reports = list(WasteReport.objects.select_related(
                'vessel', 'created_by'
            ).order_by('-report_date', '-created_at'))
            
            # 🚀 CACHE: Store evaluated waste report list for future requests
            WasteCacheHelper.cache_waste_mgmt_list(waste_reports)
            logger.debug(f"Cached: Waste Management List ({len(waste_reports)} waste reports) - 1 hour timeout")
            using_cached_data = True
    else:
        # Filters applied - always do fresh query (can't use cache)
        waste_reports = WasteReport.objects.select_related(
            'vessel', 'created_by'
        )
        
        # Apply all filters using helper with custom field mappings
        waste_reports = TransactionQueryHelper.apply_common_filters(
            waste_reports, request,
            date_field='report_date',        # Waste reports use report_date
            status_field='is_completed'      # Enable status filtering for waste reports
        )
        
        # Order for consistent results
        waste_reports = waste_reports.order_by('-report_date', '-created_at')
    
    # ✅ REPLACE Django Paginator with optimized pagination
    page_number = request.GET.get('page', 1)
    page_obj = get_optimized_pagination(waste_reports, page_number, page_size=25, use_count=False)
    
    # Add cost performance class to each waste report (for template)
    waste_reports_list = page_obj.object_list  # Use optimized pagination object list
    
    # OPTIMIZED: Calculate stats using pre-calculated fields (NO additional queries)
    total_cost = 0
    completed_count = 0
    total_waste_items = 0
    total_transactions = 0
    
    for waste_report in waste_reports_list:
        # Use pre-calculated fields instead of manual calculation
        waste_cost = float(waste_report.total_cost)
        waste_transaction_count = waste_report.item_count  # Pre-calculated transaction count
        waste_item_count = waste_report.item_count  # Same as transaction count for waste reports
        
        # Add calculated fields to waste report object for template
        waste_report.annotated_total_cost = waste_cost
        waste_report.annotated_transaction_count = waste_transaction_count
        waste_report.annotated_item_count = waste_item_count
        
        # Accumulate stats
        total_cost += waste_cost
        total_transactions += waste_transaction_count
        total_waste_items += waste_item_count
        
        # Performance classification for template styling
        if waste_cost > 500:
            waste_report.cost_performance_class = 'high-waste'
        elif waste_cost > 200:
            waste_report.cost_performance_class = 'medium-waste'
        else:
            waste_report.cost_performance_class = 'low-waste'
        
        # Count completed waste reports
        if waste_report.is_completed:
            completed_count += 1
    
    # Calculate derived stats
    total_reports = len(waste_reports_list)
    in_progress_count = total_reports - completed_count
    completion_rate = (completed_count / max(total_reports, 1)) * 100
    avg_waste_cost = total_cost / max(total_reports, 1)
    avg_cost_per_item = total_cost / max(total_waste_items, 1)
    
    # Calculate recent activity from existing data
    week_ago = timezone.now() - timedelta(days=7)
    recent_reports_count = sum(1 for report in waste_reports_list if report.created_at >= week_ago)
    recent_value = sum(report.annotated_total_cost for report in waste_reports_list if report.created_at >= week_ago)
    
    # Calculate vessel performance from existing data
    vessel_stats = {}
    for waste_report in waste_reports_list:
        vessel_name = waste_report.vessel.name
        if vessel_name not in vessel_stats:
            vessel_stats[vessel_name] = {
                'vessel': waste_report.vessel,
                'report_count': 0,
                'total_value': 0,
                'total_items': 0
            }
        vessel_stats[vessel_name]['report_count'] += 1
        vessel_stats[vessel_name]['total_value'] += waste_report.annotated_total_cost
        vessel_stats[vessel_name]['total_items'] += waste_report.annotated_item_count
    
    # Convert to list and sort by total waste cost
    top_vessels = sorted(
        vessel_stats.values(), 
        key=lambda x: x['total_value'], 
        reverse=True
    )[:5]
    
    # Calculate environmental impact metrics
    environmental_stats = {
        'total_items_wasted': total_waste_items,
        'avg_waste_per_report': total_waste_items / max(total_reports, 1),
        'highest_waste_vessel': top_vessels[0]['vessel'].name if top_vessels else 'N/A',
        'waste_reduction_target': max(0, total_waste_items - (total_waste_items * 0.1)),  # 10% reduction target
    }
    
    all_vessels = VesselCacheHelper.get_all_vessels_basic_data()
    vessels = [v for v in all_vessels if v.active]
    
    context = {
        'waste_reports': waste_reports_list,
        'page_obj': page_obj,  # Optimized pagination object
        'active_vessels': vessels,
        'page_title': 'Waste Management',
        'stats': {
            'total_reports': total_reports,
            'completed_reports': completed_count,
            'in_progress_reports': in_progress_count,
            'completion_rate': round(completion_rate, 1),
            'total_waste_value': total_cost,
            'avg_waste_cost': round(avg_waste_cost, 2),
            'total_transactions': total_transactions,
            'avg_transactions_per_report': round(total_transactions / max(total_reports, 1), 1),
            'total_waste_items': total_waste_items,
            'avg_cost_per_item': round(avg_cost_per_item, 2),
        },
        'recent_activity': {
            'recent_reports': recent_reports_count,
            'recent_value': recent_value,
        },
        'top_vessels': top_vessels,
        'environmental_stats': environmental_stats,
        'current_filters': {
            'search': request.GET.get('search', ''),
            'vessel': request.GET.get('vessel', ''),
            'status': request.GET.get('status', ''),
            'date_from': request.GET.get('date_from', ''),
            'date_to': request.GET.get('date_to', ''),
        }
    }
    
    return render(request, 'frontend/auth/waste_management.html', context)

@login_required
@user_passes_test(is_admin_or_manager)
def edit_waste_report(request, waste_id):
    """Edit waste report details following PO edit pattern"""
    waste_report, error = CRUDHelper.safe_get_object(WasteReport, waste_id, 'Waste Report')
    if error:
        return error

    if request.method == 'GET':
        waste_data = {
            'id': waste_report.id,
            'report_number': waste_report.report_number,
            'report_date': waste_report.report_date.strftime('%Y-%m-%d'),
            'notes': waste_report.notes,
            'is_completed': waste_report.is_completed,
            'vessel_name': waste_report.vessel.name,
            'total_cost': float(waste_report.total_cost),
            'transaction_count': waste_report.item_count,
        }
        
        waste_items = []
        if waste_report.is_completed:
            # Get waste transactions for completed reports
            waste_transactions = Transaction.objects.filter(
                waste_report=waste_report,
                transaction_type='WASTE'
            ).select_related('product').order_by('created_at')
            
            for waste in waste_transactions:
                waste_items.append({
                    'id': waste.id,
                    'product_id': waste.product.id,
                    'product_name': waste.product.name,
                    'product_item_id': waste.product.item_id,
                    'quantity': int(waste.quantity),
                    'unit_price': float(waste.unit_price),
                    'total_cost': float(waste.total_amount),
                    'damage_reason': waste.damage_reason,
                    'notes': waste.notes or '',
                    'created_at': waste.created_at.strftime('%H:%M')
                })
        
        return JsonResponse({
            'success': True,
            'waste_report': waste_data,
            'waste_items': waste_items  # FIXED: Include waste items for preservation
        })

    if request.method == 'POST':
        try:
            # Parse JSON data (consistent with other templates)
            data = json.loads(request.body)
            
            # Validate required fields
            report_date = data.get('report_date')
            notes = data.get('notes', '').strip()
            is_completed = data.get('is_completed', False)
            
            if not report_date:
                return JsonResponseHelper.error(
                    error_message="Report date is required",
                    error_type='validation_error'
                )
            
            # Parse and validate date
            try:
                report_date = datetime.strptime(report_date, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponseHelper.error(
                    error_message="Invalid date format",
                    error_type='validation_error'
                )
            
            # Track if status is changing to trigger proper cache clearing
            original_status = waste_report.is_completed
            status_changed = original_status != is_completed
            
            # Update waste report fields
            waste_report.report_date = report_date
            waste_report.notes = notes
            waste_report.is_completed = is_completed
            waste_report.save()
            
            # Clear waste cache after update
            WasteCacheHelper.clear_cache_after_waste_update(waste_id)
            
            # Create appropriate success message
            if status_changed:
                action = "completed" if waste_report.is_completed else "reopened for editing"
                message = f'Waste report {waste_report.report_number} updated and {action} successfully'
            else:
                message = f'Waste report {waste_report.report_number} updated successfully'
            
            return JsonResponseHelper.success(message=message)
            
        except ValueError as e:
            return JsonResponseHelper.error(
                error_message="Invalid date format",
                error_type='validation_error'
            )
        except Exception as e:
            return JsonResponseHelper.error(
                error_message=f"Failed to update waste report: {str(e)}",
                error_type='system_error'
            )

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["DELETE"])
def delete_waste_report(request, waste_id):
    """
    Delete waste report following transfer pattern with inventory restoration
    
    Logic:
    - Waste report deletion automatically deletes linked waste transactions
    - Each waste transaction deletion triggers inventory restoration via _restore_inventory_for_waste()
    - FIFO restoration ensures accurate inventory recovery
    """
    waste_report, error = CRUDHelper.safe_get_object(WasteReport, waste_id, 'Waste Report')
    if error:
        return error

    force_delete = AdminActionHelper.check_force_delete(request)

    # Get waste transactions for analysis
    waste_transactions = waste_report.waste_transactions.select_related('product')

    waste_items = []
    for txn in waste_transactions:
        waste_items.append({
            'id': txn.id,
            'product_name': txn.product.name,
            'product_item_id': txn.product.item_id,
            'quantity': txn.quantity,
            'unit_price': txn.unit_price,
            'amount': float(txn.quantity) * float(txn.unit_price),
            'damage_reason': txn.damage_reason or 'Not specified',
        })

    waste_item_count = len(waste_items)
    waste_report_number = waste_report.report_number

    # Confirmation check
    if waste_item_count > 0 and not force_delete:
        total_cost = waste_report.total_cost

        return JsonResponseHelper.requires_confirmation(
            message=f'This waste report has {waste_item_count} waste items. Delete anyway?',
            confirmation_data={
                'waste_report_number': waste_report_number,
                'vessel_name': waste_report.vessel.name,
                'waste_item_count': waste_item_count,
                'total_cost': float(total_cost),
                'items': waste_items
            },
            detailed_message=f'Deleting "{waste_report_number}" will restore {waste_item_count} items back to inventory. Inventory updated.'
        )

    # Main deletion logic
    try:
        if waste_item_count > 0:
            with transaction.atomic():
                # Manually delete waste transactions to trigger inventory restoration
                waste_transactions = waste_report.waste_transactions.select_related('product')
                
                for waste_txn in waste_transactions:
                    logger.info(f"🗑️ DELETING WASTE: {waste_txn.product.name} x{waste_txn.quantity} (ID: {waste_txn.id})")
                    waste_txn.delete()  # This calls _restore_inventory_for_waste()
                
                # Delete the empty waste report
                waste_report.delete()
            
            # Clear cache
            WasteCacheHelper.clear_cache_after_waste_delete(waste_id)

            return JsonResponseHelper.success(
                message=f'{waste_report_number} and all {waste_item_count} waste items deleted successfully. Inventory restored.'
            )
        else:
            # No transactions - simple deletion
            waste_report.delete()
            
            # Clear waste cache after deletion
            WasteCacheHelper.clear_cache_after_waste_delete(waste_id)
            
            return JsonResponseHelper.success(
                message=f'{waste_report_number} deleted successfully.'
            )
            
    except ValidationError as e:
        # Handle any validation errors during deletion
        error_message = str(e)
        
        # Extract message from ValidationError list format
        if error_message.startswith('[') and error_message.endswith(']'):
            error_message = error_message[2:-2]  # Remove ['...']
        
        return JsonResponseHelper.error(
            error_message=f"Cannot delete waste report: {error_message}",
            error_type='validation_error'
        )
            
    except Exception as e:
        return JsonResponseHelper.error(
            error_message=f"An unexpected error occurred while deleting waste report: {str(e)}",
            error_type='system_error'
        )

@login_required
@user_passes_test(is_admin_or_manager)
def toggle_waste_status(request, waste_id):
    """
    Enhanced toggle waste report completion status with workflow restart capability
    
    Behavior:
    - completed → incomplete: Delete transactions, restore inventory, redirect to waste_items
    - incomplete → completed: Simple boolean toggle (stays on management page)
    """
    # Get waste report safely
    waste_report, error = CRUDHelper.safe_get_object(WasteReport, waste_id, 'Waste Report')
    if error:
        return error
    
    try:
        # Determine the action based on current status
        if waste_report.is_completed:
            # RESTART WORKFLOW: completed → incomplete
            with transaction.atomic():
                # Delete all waste transactions (automatically restores inventory)
                waste_transactions = Transaction.objects.filter(
                    waste_report=waste_report,
                    transaction_type='WASTE'
                )
                
                transaction_count = waste_transactions.count()
                
                if transaction_count > 0:
                    logger.info(f"🔄 WASTE RESTART: Deleting {transaction_count} waste transactions for report {waste_report.report_number}")
                    
                    # Delete each transaction (triggers inventory restoration via Transaction.delete())
                    for txn in waste_transactions:
                        txn.delete()
                    
                    logger.info(f"✅ WASTE RESTART: Inventory restored for {transaction_count} items")
                
                # Mark as incomplete
                waste_report.is_completed = False
                waste_report.save()
                
                # Clear waste cache
                WasteCacheHelper.clear_cache_after_waste_update(waste_id)
                
                logger.info(f"🔄 WASTE RESTART: Report {waste_report.report_number} reopened for editing")
            
            # Return redirect response to restart workflow at waste_items
            return JsonResponse({
                'success': True,
                'action': 'restart_workflow',
                'message': f'Waste report {waste_report.report_number} reopened successfully. Inventory restored for {transaction_count} items.',
                'redirect_url': reverse('frontend:waste_items', kwargs={'waste_id': waste_id}),
                'transaction_count': transaction_count,
                'waste_data': {
                    'report_number': waste_report.report_number,
                    'vessel': waste_report.vessel.name,
                    'is_completed': False
                }
            })
            
        else:
            # SIMPLE TOGGLE: incomplete → completed
            # Use standard toggle (stays on management page)
            waste_report.is_completed = True
            waste_report.save()
            
            # Clear waste cache
            WasteCacheHelper.clear_cache_after_waste_update(waste_id)
            
            return JsonResponse({
                'success': True,
                'action': 'mark_completed',
                'message': f'Waste report {waste_report.report_number} marked as completed successfully.',
                'new_status': True,
                'waste_data': {
                    'report_number': waste_report.report_number,
                    'vessel': waste_report.vessel.name,
                    'is_completed': True
                }
            })
            
    except Exception as e:
        return JsonResponseHelper.error(
            error_message=f"Error toggling waste report status: {str(e)}",
            error_type='system_error'
        )