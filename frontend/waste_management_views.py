from django.urls import reverse
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from frontend.utils.cache_helpers import VesselCacheHelper, WasteCacheHelper
from .utils.query_helpers import TransactionQueryHelper
from .utils.response_helpers import JsonResponseHelper
from .utils.crud_helpers import CRUDHelper, AdminActionHelper
from .permissions import is_admin_or_manager
from django.core.exceptions import ValidationError
from django.shortcuts import render
from transactions.models import WasteReport
from datetime import datetime
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from datetime import timedelta
from django.utils import timezone
import json

@login_required
@user_passes_test(is_admin_or_manager)
def waste_management(request):
    """Waste report management with pagination following transactions_list pattern"""
    
    # Base queryset with template-required annotations
    waste_reports = WasteReport.objects.select_related(
        'vessel', 'created_by'
    ).prefetch_related(
        'waste_transactions'
    ).order_by('-report_date', '-created_at')
    
    # Apply all filters using helper with custom field mappings
    waste_reports = TransactionQueryHelper.apply_common_filters(
        waste_reports, request,
        date_field='report_date',        # Waste reports use report_date
        status_field='is_completed'      # Enable status filtering for waste reports
    )
    
    # Order for consistent results
    waste_reports = waste_reports.order_by('-report_date', '-created_at')
    
    paginator = Paginator(waste_reports, 25)
    page_number = request.GET.get('page')
    
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    # Add cost performance class to each waste report (for template)
    waste_reports_list = list(page_obj)  # Changed from [:50] to use paginated results
    
    # OPTIMIZED: Calculate stats in Python using prefetched data
    total_cost = 0
    completed_count = 0
    total_transactions = 0
    total_waste_items = 0
    
    # Add template-required annotations for each waste report
    for waste_report in waste_reports_list:
        # Calculate cost using prefetched waste_transactions (no additional queries)
        waste_cost = sum(
            float(txn.quantity) * float(txn.unit_price) 
            for txn in waste_report.waste_transactions.all()
        )
        waste_transaction_count = len(waste_report.waste_transactions.all())
        waste_item_count = sum(
            int(txn.quantity) 
            for txn in waste_report.waste_transactions.all()
        )
        
        # Add calculated fields to waste report object for template
        waste_report.annotated_total_cost = waste_cost
        waste_report.annotated_transaction_count = waste_transaction_count
        waste_report.annotated_item_count = waste_item_count
        
        # Accumulate stats
        total_cost += waste_cost
        total_transactions += waste_transaction_count
        total_waste_items += waste_item_count
        
        # Calculate cost performance class for template styling
        if waste_cost > 500:
            waste_report.cost_performance_class = 'high-cost'
        elif waste_cost > 200:
            waste_report.cost_performance_class = 'medium-cost'
        else:
            waste_report.cost_performance_class = 'low-cost'
        
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
    
    context = {
        'waste_reports': waste_reports_list,
        'page_obj': page_obj,  # ADD: Pagination object for template
        'active_vessels': VesselCacheHelper.get_active_vessels(),
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
            'transaction_count': waste_report.transaction_count,
        }
        
        return JsonResponse({
            'success': True,
            'waste_report': waste_data
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
    waste_transactions = waste_report.waste_transactions.filter(
        transaction_type='WASTE'
    ).select_related('product')

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

    try:
        if waste_item_count > 0 and not force_delete:
            total_cost = waste_report.total_cost

            return JsonResponseHelper.requires_confirmation(
                message=f'This waste report has {waste_item_count} waste items. Delete anyway?',
                confirmation_data={
                    'waste_report_number': waste_report_number,
                    'vessel_name': waste_report.vessel.name,
                    'waste_item_count': waste_item_count,
                    'total_cost': float(total_cost),
                    'items': waste_items[:5]  # Show first 5 items for confirmation
                },
                detailed_message=f'Deleting "{waste_report_number}" will restore {waste_item_count} items back to inventory. Inventory updated.',
                suggested_actions=[
                    {
                        'action': 'view_inventory',
                        'label': 'Check Inventory After Deletion',
                        'url': reverse('frontend:inventory_check'),
                        'description': 'View updated inventory levels after restoration'
                    },
                    {
                        'action': 'view_transactions',
                        'label': 'Review Transaction History',
                        'url': reverse('frontend:transactions_list'),
                        'description': 'See the inventory restoration transactions'
                    }
                ]
            )
        else:
            # No transactions or force delete - proceed with deletion
            waste_report.delete()
            
            # Clear waste cache after deletion
            WasteCacheHelper.clear_cache_after_waste_delete(waste_id)
            
            return JsonResponseHelper.success(
                message=f'{waste_report_number} deleted successfully. Inventory restored.'
            )
            
    except ValidationError as e:
        # Handle any validation errors during deletion
        error_message = str(e)
        
        # Extract message from ValidationError list format
        if error_message.startswith('[') and error_message.endswith(']'):
            error_message = error_message[2:-2]  # Remove ['...']
        
        return JsonResponseHelper.error(
            error_message=f"Cannot delete waste report: {error_message}",
            error_type='validation_error',
            detailed_message=error_message,
            suggested_actions=[
                {
                    'action': 'contact_admin',
                    'label': 'Contact Administrator',
                    'description': 'Get help resolving the deletion conflict'
                }
            ]
        )
            
    except Exception as e:
        return JsonResponseHelper.error(
            error_message=f"An unexpected error occurred while deleting waste report: {str(e)}",
            error_type='system_error'
        )

@login_required
@user_passes_test(is_admin_or_manager)
def toggle_waste_status(request, waste_id):
    """Toggle waste report completion status - SIMPLE: Like PO pattern (0 cache clearing lines)"""
    # Get waste report safely
    waste_report, error = CRUDHelper.safe_get_object(WasteReport, waste_id, 'Waste Report')
    if error:
        return error
    
    # SIMPLE: No cache clearing needed (like PO toggle - works with simple versioning)
    # Toggle status with standardized response
    return CRUDHelper.toggle_boolean_field(waste_report, 'is_completed', 'Waste Report')