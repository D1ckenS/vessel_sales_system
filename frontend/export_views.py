from django.utils import timezone
from datetime import datetime, timedelta, date
from django.contrib.auth.decorators import login_required
import calendar
from django.db.models import Sum, Count, F, Q
import json
from .utils import BilingualMessages
from django.http import JsonResponse, HttpResponse
from transactions.models import Transaction, InventoryLot, Trip, PurchaseOrder
from vessels.models import Vessel
from .utils.exports import ExcelExporter, PDFExporter, create_pdf_exporter_for_data
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
import logging
from products.models import Product, Category

# Set up logging
logger = logging.getLogger(__name__)

# ===============================================================================
# HELPER FUNCTIONS
# ===============================================================================

def safe_float(value, default=0.0):
    """Safely convert value to float"""
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    """Safely convert value to int"""
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default

def format_datetime(dt):
    """Format datetime for export"""
    if dt:
        return dt.strftime('%d/%m/%Y %H:%M')
    return ''

def format_date(dt):
    """Format date for export"""
    if dt:
        return dt.strftime('%d/%m/%Y')
    return ''

def get_date_range_from_request(data):
    """Extract and validate date range from request data"""
    try:
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            start_date = timezone.now().date() - timedelta(days=30)
            
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date = timezone.now().date()
            
        return start_date, end_date
    except ValueError as e:
        logger.error(f"Date parsing error: {e}")
        return None, None

def create_safe_response(content, content_type, filename):
    """Create a safe HTTP response with proper headers"""
    response = HttpResponse(content_type=content_type)
    clean_filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
    response['Content-Disposition'] = f'attachment; filename="{clean_filename}"'
    response['Content-Length'] = len(content)
    return response

# ===============================================================================
# TRANSACTION EXPORTS
# ===============================================================================

@login_required
@require_http_methods(["POST"])
def export_transactions(request):
    """Export transactions to Excel or PDF with comprehensive filtering"""
    try:
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get filters
        start_date, end_date = get_date_range_from_request(data)
        if not start_date or not end_date:
            return JsonResponse({'success': False, 'error': 'Invalid date range'})
            
        vessel_id = data.get('vessel_id')
        transaction_type = data.get('transaction_type')
        product_id = data.get('product_id')
        
        # Build query with proper field names
        transactions = Transaction.objects.select_related(
            'vessel', 'product', 'product__category', 'created_by', 'trip', 'purchase_order'
        ).filter(
            transaction_date__gte=start_date,
            transaction_date__lte=end_date
        ).order_by('-transaction_date')
        
        # Apply filters
        if vessel_id:
            transactions = transactions.filter(vessel_id=vessel_id)
        if transaction_type:
            transactions = transactions.filter(transaction_type=transaction_type)
        if product_id:
            transactions = transactions.filter(product_id=product_id)
            
        # Prepare table data
        table_data = []
        total_amount = 0
        
        for transaction in transactions[:5000]:  # Limit to prevent memory issues
            amount = safe_float(transaction.quantity) * safe_float(transaction.unit_price)
            total_amount += amount
            
            table_data.append([
                format_date(transaction.transaction_date),
                transaction.get_transaction_type_display() if hasattr(transaction, 'get_transaction_type_display') else transaction.transaction_type,
                transaction.vessel.name if transaction.vessel else 'N/A',
                transaction.product.name if transaction.product else 'N/A',
                transaction.product.category.name if transaction.product and transaction.product.category else 'N/A',
                safe_float(transaction.quantity),
                safe_float(transaction.unit_price),
                amount,
                transaction.trip.trip_number if transaction.trip else 'N/A',
                transaction.purchase_order.po_number if transaction.purchase_order else 'N/A',
                transaction.created_by.username if transaction.created_by else 'System',
                transaction.notes or ''
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"transactions_export_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Date Range': f"{format_date(start_date)} to {format_date(end_date)}",
            'Total Records': len(table_data),
            'Total Amount (JOD)': f"{total_amount:.3f}",
            'Generated By': request.user.username,
            'Filters Applied': f"Vessel: {vessel_id or 'All'}, Type: {transaction_type or 'All'}, Product: {product_id or 'All'}"
        }
        
        headers = [
            'Date', 'Type', 'Vessel', 'Product', 'Category', 
            'Quantity', 'Unit Price (JOD)', 'Total Amount (JOD)', 
            'Trip #', 'PO #', 'Created By', 'Notes'
        ]
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Transactions Export")
                exporter.add_title("Transactions Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(table_data)
                
                # Add summary
                summary_data = {
                    'Total Records': len(table_data),
                    'Total Amount (JOD)': f"{total_amount:.3f}",
                    'Date Range': f"{format_date(start_date)} to {format_date(end_date)}"
                }
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_pdf_exporter_for_data("Transactions Report", "wide")
                exporter.add_title("Transactions Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, table_data, auto_size_columns=True)
                
                return exporter.get_response(f"{filename_base}.pdf")
                
            except Exception as e:
                logger.error(f"PDF export error: {e}")
                return JsonResponse({'success': False, 'error': f'PDF export failed: {str(e)}'})
                
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Transaction export error: {e}")
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})

# ===============================================================================
# INVENTORY EXPORTS
# ===============================================================================

@login_required
@require_http_methods(["POST"])
def export_inventory(request):
    """Export current inventory status to Excel or PDF"""
    try:
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get filters
        vessel_id = data.get('vessel_id')
        category_id = data.get('category_id')
        low_stock_only = data.get('low_stock_only', False)
        
        # Get all products
        products = Product.objects.select_related('category').filter(active=True)
        
        if category_id:
            products = products.filter(category_id=category_id)
        
        # Calculate current stock for each product
        inventory_data = []
        total_value = 0
        
        for product in products:
            # Calculate current stock based on transactions
            stock_query = Transaction.objects.filter(product=product)
            
            if vessel_id:
                stock_query = stock_query.filter(vessel_id=vessel_id)
            
            # Calculate stock: supplies - sales
            supplies = stock_query.filter(
                transaction_type='SUPPLY'
            ).aggregate(
                total=Sum('quantity')
            )['total'] or 0
            
            sales = stock_query.filter(
                transaction_type='SALE'
            ).aggregate(
                total=Sum('quantity')
            )['total'] or 0
            
            current_stock = supplies - sales
            
            # Skip products with no stock if requested
            min_stock = getattr(product, 'min_stock_level', 10) or 10
            if low_stock_only and current_stock >= min_stock:
                continue
                
            # Calculate value
            unit_price = safe_float(getattr(product, 'current_price', None) or getattr(product, 'default_price', 0))
            total_item_value = current_stock * unit_price
            total_value += total_item_value
            
            # Get vessel name if filtered by vessel
            vessel_name = 'All Vessels'
            if vessel_id:
                try:
                    vessel = Vessel.objects.get(id=vessel_id)
                    vessel_name = vessel.name
                except Vessel.DoesNotExist:
                    vessel_name = 'Unknown Vessel'
            
            inventory_data.append([
                product.name,
                getattr(product, 'product_id', 'N/A') or 'N/A',
                product.category.name if product.category else 'Uncategorized',
                safe_float(current_stock),
                unit_price,
                total_item_value,
                vessel_name,
                min_stock,
                'Low Stock' if current_stock < min_stock else 'OK',
                format_datetime(getattr(product, 'updated_at', None) or getattr(product, 'created_at', None))
            ])
        
        # Sort by total value descending
        inventory_data.sort(key=lambda x: safe_float(x[5]), reverse=True)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"inventory_export_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Total Items': len(inventory_data),
            'Total Inventory Value (JOD)': f"{total_value:.3f}",
            'Generated By': request.user.username,
            'Vessel Filter': vessel_name if vessel_id else 'All Vessels',
            'Category Filter': f"Category ID: {category_id}" if category_id else 'All Categories',
            'Low Stock Only': 'Yes' if low_stock_only else 'No'
        }
        
        headers = [
            'Product Name', 'Product ID', 'Category', 'Current Stock', 
            'Unit Price (JOD)', 'Total Value (JOD)', 'Vessel', 
            'Min Stock Level', 'Stock Status', 'Last Updated'
        ]
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Inventory Export")
                exporter.add_title("Inventory Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(inventory_data)
                
                # Add summary
                summary_data = {
                    'Total Items': len(inventory_data),
                    'Total Value (JOD)': f"{total_value:.3f}",
                    'Low Stock Items': len([item for item in inventory_data if item[8] == 'Low Stock'])
                }
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel inventory export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_pdf_exporter_for_data("Inventory Report", "wide")
                exporter.add_title("Inventory Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, inventory_data, auto_size_columns=True)
                
                return exporter.get_response(f"{filename_base}.pdf")
                
            except Exception as e:
                logger.error(f"PDF inventory export error: {e}")
                return JsonResponse({'success': False, 'error': f'PDF export failed: {str(e)}'})
                
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Inventory export error: {e}")
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})

# ===============================================================================
# TRIP EXPORTS (LIST AND INDIVIDUAL)
# ===============================================================================

@login_required
@require_http_methods(["POST"])
def export_trips(request):
    """Export trips list to Excel or PDF - FIXED VERSION"""
    try:
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get filters
        start_date, end_date = get_date_range_from_request(data)
        if not start_date or not end_date:
            return JsonResponse({'success': False, 'error': 'Invalid date range'})
            
        vessel_id = data.get('vessel_id')
        status = data.get('status')
        
        # Build query
        trips = Trip.objects.select_related(
            'vessel', 'created_by'
        ).filter(
            trip_date__gte=start_date,
            trip_date__lte=end_date
        ).order_by('-trip_date')
        
        # Apply filters
        if vessel_id:
            trips = trips.filter(vessel_id=vessel_id)
        if status:
            trips = trips.filter(status=status)
            
        # Prepare table data
        table_data = []
        total_revenue = 0
        
        for trip in trips[:2000]:  # Limit to prevent memory issues
            # Calculate trip revenue from transactions
            trip_revenue = Transaction.objects.filter(
                trip=trip,
                transaction_type='SALE'
            ).aggregate(
                total=Sum(F('quantity') * F('unit_price'))
            )['total'] or 0
            
            total_revenue += trip_revenue
            
            # Get transaction count
            transaction_count = Transaction.objects.filter(trip=trip).count()
            
            table_data.append([
                trip.trip_number,
                format_date(trip.trip_date),
                trip.vessel.name if trip.vessel else 'N/A',
                trip.get_status_display() if hasattr(trip, 'get_status_display') else getattr(trip, 'status', 'N/A'),
                safe_float(trip_revenue),
                safe_int(transaction_count),
                safe_int(getattr(trip, 'passenger_count', 0)),
                format_datetime(trip.start_time) if hasattr(trip, 'start_time') and trip.start_time else 'N/A',
                format_datetime(trip.end_time) if hasattr(trip, 'end_time') and trip.end_time else 'Ongoing',
                trip.created_by.username if trip.created_by else 'System'
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"trips_export_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Date Range': f"{format_date(start_date)} to {format_date(end_date)}",
            'Total Records': len(table_data),
            'Total Revenue (JOD)': f"{total_revenue:.3f}",
            'Generated By': request.user.username,
            'Vessel Filter': vessel_id or 'All',
            'Status Filter': status or 'All'
        }
        
        headers = [
            'Trip Number', 'Date', 'Vessel', 'Status', 
            'Revenue (JOD)', 'Transactions', 'Passengers', 'Start Time', 
            'End Time', 'Created By'
        ]
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Trips Export")
                exporter.add_title("Trips Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(table_data)
                
                # Add summary
                summary_data = {
                    'Total Trips': len(table_data),
                    'Total Revenue (JOD)': f"{total_revenue:.3f}",
                    'Average Revenue per Trip (JOD)': f"{(total_revenue / len(table_data)) if table_data else 0:.3f}"
                }
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel trips export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_pdf_exporter_for_data("Trips Report", "wide")
                exporter.add_title("Trips Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, table_data, auto_size_columns=True)
                
                return exporter.get_response(f"{filename_base}.pdf")
                
            except Exception as e:
                logger.error(f"PDF trips export error: {e}")
                return JsonResponse({'success': False, 'error': f'PDF export failed: {str(e)}'})
                
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Trips export error: {e}")
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})

@require_http_methods(["POST"])
def export_single_trip(request, trip_id):
    """Export individual trip details for journal entries"""
    try:
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get trip
        trip = get_object_or_404(Trip, id=trip_id)
        
        # Get trip transactions
        transactions = Transaction.objects.filter(
            trip=trip
        ).select_related('product', 'product__category').order_by('transaction_date')
        
        # Calculate totals
        total_revenue = 0
        total_cogs = 0
        
        # Prepare transaction data
        transaction_data = []
        for transaction in transactions:
            revenue = safe_float(transaction.quantity) * safe_float(transaction.unit_price)
            # Calculate COGS - you may need to adjust this based on your cost calculation
            cogs = safe_float(transaction.quantity) * safe_float(getattr(transaction, 'cost_per_unit', transaction.unit_price * 0.7))  # Example: 70% cost ratio
            profit = revenue - cogs
            
            total_revenue += revenue
            total_cogs += cogs
            
            transaction_data.append([
                format_datetime(transaction.transaction_date),
                transaction.product.name if transaction.product else 'N/A',
                transaction.product.product_id if transaction.product else 'N/A',
                safe_float(transaction.quantity),
                safe_float(transaction.unit_price),
                cogs / safe_float(transaction.quantity) if safe_float(transaction.quantity) > 0 else 0,
                revenue,
                cogs,
                profit,
                transaction.notes or ''
            ])
        
        total_profit = total_revenue - total_cogs
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"trip_{trip.trip_number}_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Trip Number': trip.trip_number,
            'Vessel': trip.vessel.name if trip.vessel else 'N/A',
            'Trip Date': format_date(trip.trip_date),
            'Status': trip.get_status_display() if hasattr(trip, 'get_status_display') else getattr(trip, 'status', 'N/A'),
            'Passengers': safe_int(getattr(trip, 'passenger_count', 0)),
            'Total Revenue (JOD)': f"{total_revenue:.3f}",
            'Total COGS (JOD)': f"{total_cogs:.3f}",
            'Total Profit (JOD)': f"{total_profit:.3f}",
            'Profit Margin (%)': f"{(total_profit/total_revenue*100) if total_revenue > 0 else 0:.1f}%",
            'Generated By': request.user.username
        }
        
        headers = [
            'Time', 'Product', 'Product ID', 'Quantity', 
            'Unit Selling Price (JOD)', 'COGS per Unit (JOD)', 
            'Revenue (JOD)', 'COGS (JOD)', 'Profit (JOD)', 'Notes'
        ]
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title=f"Trip {trip.trip_number}")
                exporter.add_title(f"Trip Sales Report - {trip.trip_number}", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(transaction_data)
                
                # Add summary
                summary_data = {
                    'Total Items Sold': len(transaction_data),
                    'Total Revenue (JOD)': f"{total_revenue:.3f}",
                    'Total COGS (JOD)': f"{total_cogs:.3f}",
                    'Total Profit (JOD)': f"{total_profit:.3f}",
                    'Profit Margin (%)': f"{(total_profit/total_revenue*100) if total_revenue > 0 else 0:.1f}%"
                }
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel single trip export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_pdf_exporter_for_data(f"Trip {trip.trip_number} Report", "wide")
                exporter.add_title(f"Trip Sales Report - {trip.trip_number}", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, transaction_data, auto_size_columns=True)
                
                return exporter.get_response(f"{filename_base}.pdf")
                
            except Exception as e:
                logger.error(f"PDF single trip export error: {e}")
                return JsonResponse({'success': False, 'error': f'PDF export failed: {str(e)}'})
                
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Single trip export error: {e}")
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})

# ===============================================================================
# PURCHASE ORDER EXPORTS (LIST AND INDIVIDUAL)
# ===============================================================================

@login_required
@require_http_methods(["POST"])
def export_purchase_orders(request):
    """Export purchase orders list to Excel or PDF - FIXED VERSION"""
    try:
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get filters
        start_date, end_date = get_date_range_from_request(data)
        if not start_date or not end_date:
            return JsonResponse({'success': False, 'error': 'Invalid date range'})
            
        vessel_id = data.get('vessel_id')
        status = data.get('status')
        
        # Build query
        pos = PurchaseOrder.objects.select_related(
            'vessel', 'created_by'
        ).filter(
            po_date__gte=start_date,
            po_date__lte=end_date
        ).order_by('-po_date')
        
        # Apply filters
        if status:
            if hasattr(PurchaseOrder, 'status'):
                pos = pos.filter(status=status)
            elif hasattr(PurchaseOrder, 'is_completed'):
                if status == 'completed':
                    pos = pos.filter(is_completed=True)
                elif status == 'pending':
                    pos = pos.filter(is_completed=False)
        if vessel_id:
            pos = pos.filter(vessel_id=vessel_id)
            
        # Prepare table data
        table_data = []
        total_cost = 0
        
        for po in pos[:2000]:  # Limit to prevent memory issues
            # Calculate PO cost from transactions
            po_cost = Transaction.objects.filter(
                purchase_order=po,
                transaction_type='SUPPLY'
            ).aggregate(
                total=Sum(F('quantity') * F('unit_price'))
            )['total'] or 0
            
            total_cost += po_cost
            
            # Get item count
            item_count = Transaction.objects.filter(purchase_order=po).count()
            
            table_data.append([
                po.po_number,
                format_date(po.po_date),
                po.vessel.name if po.vessel else 'N/A',
                getattr(po, 'supplier_name', 'N/A'),
                'Completed' if getattr(po, 'is_completed', False) else 'Pending',
                safe_float(po_cost),
                safe_int(item_count),
                format_date(getattr(po, 'expected_delivery_date', None)) if hasattr(po, 'expected_delivery_date') else 'N/A',
                format_date(getattr(po, 'actual_delivery_date', None)) if hasattr(po, 'actual_delivery_date') else 'Pending',
                po.created_by.username if po.created_by else 'System',
                getattr(po, 'notes', '') or ''
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"purchase_orders_export_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Date Range': f"{format_date(start_date)} to {format_date(end_date)}",
            'Total Records': len(table_data),
            'Total Cost (JOD)': f"{total_cost:.3f}",
            'Generated By': request.user.username,
            'Status Filter': status or 'All',
            'Vessel Filter': vessel_id or 'All'
        }
        
        headers = [
            'PO Number', 'Date Created', 'Vessel', 'Supplier', 'Status',
            'Total Cost (JOD)', 'Total Items', 'Expected Delivery', 
            'Actual Delivery', 'Created By', 'Notes'
        ]
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Purchase Orders Export")
                exporter.add_title("Purchase Orders Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(table_data)
                
                # Add summary
                summary_data = {
                    'Total POs': len(table_data),
                    'Total Cost (JOD)': f"{total_cost:.3f}",
                    'Average Cost (JOD)': f"{(total_cost / len(table_data)) if table_data else 0:.3f}"
                }
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel PO export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_pdf_exporter_for_data("Purchase Orders Report", "wide")
                exporter.add_title("Purchase Orders Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, table_data, auto_size_columns=True)
                
                return exporter.get_response(f"{filename_base}.pdf")
                
            except Exception as e:
                logger.error(f"PDF PO export error: {e}")
                return JsonResponse({'success': False, 'error': f'PDF export failed: {str(e)}'})
                
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"PO export error: {e}")
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})

@login_required
@require_http_methods(["POST"])
def export_single_po(request, po_id):
    """Export individual purchase order details for journal entries"""
    try:
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get PO
        po = get_object_or_404(PurchaseOrder, id=po_id)
        
        # Get PO transactions
        transactions = Transaction.objects.filter(
            purchase_order=po
        ).select_related('product', 'product__category').order_by('transaction_date')
        
        # Calculate totals
        total_cost = 0
        
        # Prepare transaction data
        transaction_data = []
        for transaction in transactions:
            cost = safe_float(transaction.quantity) * safe_float(transaction.unit_price)
            total_cost += cost
            
            transaction_data.append([
                format_datetime(transaction.transaction_date),
                transaction.product.name if transaction.product else 'N/A',
                transaction.product.product_id if transaction.product else 'N/A',
                safe_float(transaction.quantity),
                safe_float(transaction.unit_price),
                cost,
                transaction.notes or ''
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"po_{po.po_number}_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'PO Number': po.po_number,
            'Vessel': po.vessel.name if po.vessel else 'N/A',
            'PO Date': format_date(po.po_date),
            'Status': 'Completed' if getattr(po, 'is_completed', False) else 'Pending',
            'Supplier': getattr(po, 'supplier_name', 'N/A'),
            'Total Cost (JOD)': f"{total_cost:.3f}",
            'Total Items': len(transaction_data),
            'Average Cost per Item (JOD)': f"{(total_cost / len(transaction_data)) if transaction_data else 0:.3f}",
            'Generated By': request.user.username
        }
        
        headers = [
            'Time', 'Product', 'Product ID', 'Quantity', 
            'Unit Cost (JOD)', 'Total Cost (JOD)', 'Notes'
        ]
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title=f"PO {po.po_number}")
                exporter.add_title(f"Purchase Order Supply Report - {po.po_number}", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(transaction_data)
                
                # Add summary
                summary_data = {
                    'Total Items Received': len(transaction_data),
                    'Total Cost (JOD)': f"{total_cost:.3f}",
                    'Average Cost per Item (JOD)': f"{(total_cost / len(transaction_data)) if transaction_data else 0:.3f}"
                }
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel single PO export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_pdf_exporter_for_data(f"PO {po.po_number} Report", "normal")
                exporter.add_title(f"Purchase Order Supply Report - {po.po_number}", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, transaction_data, auto_size_columns=True)
                
                return exporter.get_response(f"{filename_base}.pdf")
                
            except Exception as e:
                logger.error(f"PDF single PO export error: {e}")
                return JsonResponse({'success': False, 'error': f'PDF export failed: {str(e)}'})
                
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Single PO export error: {e}")
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})

# ===============================================================================
# MONTHLY REPORT EXPORTS
# ===============================================================================

@login_required
@require_http_methods(["POST"])
def export_monthly_report(request):
    """Export monthly performance report"""
    try:
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get month and year
        selected_month = safe_int(data.get('month', datetime.now().month))
        selected_year = safe_int(data.get('year', datetime.now().year))
        
        if not (1 <= selected_month <= 12) or selected_year < 2020:
            return JsonResponse({'success': False, 'error': 'Invalid month or year'})
        
        # Calculate date range for the month
        start_date = datetime(selected_year, selected_month, 1).date()
        if selected_month == 12:
            end_date = datetime(selected_year + 1, 1, 1).date() - timedelta(days=1)
        else:
            end_date = datetime(selected_year, selected_month + 1, 1).date() - timedelta(days=1)
        
        # Get all vessels
        vessels = Vessel.objects.filter(active=True)
        
        # Calculate vessel performance
        vessel_performance = []
        monthly_revenue = 0
        monthly_costs = 0
        monthly_profit = 0
        
        for vessel in vessels:
            # Get vessel transactions for the month
            vessel_transactions = Transaction.objects.filter(
                vessel=vessel,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date
            )
            
            vessel_stats = vessel_transactions.aggregate(
                revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
                costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
                sales_count=Count('id', filter=Q(transaction_type='SALE')),
                supply_count=Count('id', filter=Q(transaction_type='SUPPLY'))
            )
            
            vessel_revenue = safe_float(vessel_stats['revenue'])
            vessel_costs = safe_float(vessel_stats['costs'])
            vessel_profit = vessel_revenue - vessel_costs
            
            monthly_revenue += vessel_revenue
            monthly_costs += vessel_costs
            monthly_profit += vessel_profit
            
            # Calculate profit margin
            profit_margin = (vessel_profit / vessel_revenue * 100) if vessel_revenue > 0 else 0
            
            vessel_performance.append([
                vessel.name,
                vessel_revenue,
                vessel_costs,
                vessel_profit,
                f"{profit_margin:.1f}%",
                safe_int(vessel_stats['sales_count']),
                safe_int(vessel_stats['supply_count'])
            ])
        
        # Sort by profit descending
        vessel_performance.sort(key=lambda x: safe_float(x[3]), reverse=True)
        
        # Generate filename
        month_name = calendar.month_name[selected_month]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"monthly_report_{month_name}_{selected_year}_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Report Month': f"{month_name} {selected_year}",
            'Total Revenue (JOD)': f"{monthly_revenue:.3f}",
            'Total Costs (JOD)': f"{monthly_costs:.3f}",
            'Total Profit (JOD)': f"{monthly_profit:.3f}",
            'Profit Margin (%)': f"{(monthly_profit / monthly_revenue * 100) if monthly_revenue > 0 else 0:.1f}%",
            'Generated By': request.user.username
        }
        
        headers = [
            'Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit (JOD)', 
            'Profit Margin (%)', 'Sales Count', 'Supply Count'
        ]
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Monthly Report")
                exporter.add_title(f"Monthly Report - {month_name} {selected_year}", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(vessel_performance)
                
                # Add summary
                summary_data = {
                    'Total Vessels': len(vessel_performance),
                    'Total Revenue (JOD)': f"{monthly_revenue:.3f}",
                    'Total Profit (JOD)': f"{monthly_profit:.3f}",
                    'Overall Profit Margin (%)': f"{(monthly_profit / monthly_revenue * 100) if monthly_revenue > 0 else 0:.1f}%"
                }
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel monthly report export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_pdf_exporter_for_data("Monthly Report", "normal")
                exporter.add_title(f"Monthly Report - {month_name} {selected_year}", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, vessel_performance, auto_size_columns=True)
                
                return exporter.get_response(f"{filename_base}.pdf")
                
            except Exception as e:
                logger.error(f"PDF monthly report export error: {e}")
                return JsonResponse({'success': False, 'error': f'PDF export failed: {str(e)}'})
                
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Monthly report export error: {e}")
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})

# ===============================================================================
# DAILY REPORT EXPORTS
# ===============================================================================

@login_required
@require_http_methods(["POST"])
def export_daily_report(request):
    """Export daily performance report"""
    try:
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get date
        selected_date = data.get('date')
        if selected_date:
            selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        else:
            selected_date = timezone.now().date()
        
        # Get all vessels
        vessels = Vessel.objects.filter(active=True)
        
        # Calculate vessel performance for the day
        vessel_performance = []
        daily_revenue = 0
        daily_costs = 0
        
        for vessel in vessels:
            # Get vessel transactions for the day
            vessel_transactions = Transaction.objects.filter(
                vessel=vessel,
                created_at__date=selected_date
            )
            
            vessel_stats = vessel_transactions.aggregate(
                revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
                costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
                sales_count=Count('id', filter=Q(transaction_type='SALE')),
                supply_count=Count('id', filter=Q(transaction_type='SUPPLY'))
            )
            
            vessel_revenue = safe_float(vessel_stats['revenue'])
            vessel_costs = safe_float(vessel_stats['costs'])
            vessel_profit = vessel_revenue - vessel_costs
            
            daily_revenue += vessel_revenue
            daily_costs += vessel_costs
            
            # Only include vessels with activity
            if vessel_revenue > 0 or vessel_costs > 0:
                vessel_performance.append([
                    vessel.name,
                    vessel_revenue,
                    vessel_costs,
                    vessel_profit,
                    safe_int(vessel_stats['sales_count']),
                    safe_int(vessel_stats['supply_count'])
                ])
        
        # Sort by revenue descending
        vessel_performance.sort(key=lambda x: safe_float(x[1]), reverse=True)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"daily_report_{selected_date.strftime('%Y%m%d')}_{timestamp}"
        
        # Metadata
        daily_profit = daily_revenue - daily_costs
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Report Date': format_date(selected_date),
            'Total Revenue (JOD)': f"{daily_revenue:.3f}",
            'Total Costs (JOD)': f"{daily_costs:.3f}",
            'Total Profit (JOD)': f"{daily_profit:.3f}",
            'Active Vessels': len(vessel_performance),
            'Generated By': request.user.username
        }
        
        headers = [
            'Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit (JOD)', 
            'Sales Count', 'Supply Count'
        ]
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Daily Report")
                exporter.add_title(f"Daily Report - {format_date(selected_date)}", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(vessel_performance)
                
                # Add summary
                summary_data = {
                    'Active Vessels': len(vessel_performance),
                    'Total Revenue (JOD)': f"{daily_revenue:.3f}",
                    'Total Profit (JOD)': f"{daily_profit:.3f}"
                }
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel daily report export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_pdf_exporter_for_data("Daily Report", "normal")
                exporter.add_title(f"Daily Report - {format_date(selected_date)}", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, vessel_performance, auto_size_columns=True)
                
                return exporter.get_response(f"{filename_base}.pdf")
                
            except Exception as e:
                logger.error(f"PDF daily report export error: {e}")
                return JsonResponse({'success': False, 'error': f'PDF export failed: {str(e)}'})
                
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Daily report export error: {e}")
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})

# ===============================================================================
# ANALYTICS EXPORT
# ===============================================================================

@login_required
@require_http_methods(["POST"])
def export_analytics(request):
    """Export analytics report with performance metrics"""
    try:
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get date range (default to last 30 days)
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)
        
        # Override with request data if provided
        if data.get('start_date'):
            start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
        if data.get('end_date'):
            end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
        
        # Get overall statistics
        total_stats = Transaction.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).aggregate(
            total_revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
            total_costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
            transaction_count=Count('id'),
            sales_count=Count('id', filter=Q(transaction_type='SALE')),
            supply_count=Count('id', filter=Q(transaction_type='SUPPLY'))
        )
        
        # Get vessel analytics
        vessels = Vessel.objects.filter(active=True)
        vessel_analytics = []
        
        for vessel in vessels:
            vessel_transactions = Transaction.objects.filter(
                vessel=vessel,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date
            )
            
            vessel_stats = vessel_transactions.aggregate(
                revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
                costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
                sales_count=Count('id', filter=Q(transaction_type='SALE')),
                avg_transaction_value=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')) / Count('id', filter=Q(transaction_type='SALE'))
            )
            
            vessel_revenue = safe_float(vessel_stats['revenue'])
            vessel_costs = safe_float(vessel_stats['costs'])
            profit_margin = ((vessel_revenue - vessel_costs) / vessel_revenue * 100) if vessel_revenue > 0 else 0
            
            vessel_analytics.append([
                vessel.name,
                vessel_revenue,
                vessel_costs,
                f"{profit_margin:.1f}%",
                safe_int(vessel_stats['sales_count']),
                safe_float(vessel_stats['avg_transaction_value']),
                'Duty-Free' if vessel.has_duty_free else 'Regular'
            ])
        
        # Sort by revenue descending
        vessel_analytics.sort(key=lambda x: safe_float(x[1]), reverse=True)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"analytics_report_{timestamp}"
        
        # Metadata
        total_revenue = safe_float(total_stats['total_revenue'])
        total_costs = safe_float(total_stats['total_costs'])
        total_profit = total_revenue - total_costs
        
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Analysis Period': f"{format_date(start_date)} to {format_date(end_date)}",
            'Total Revenue (JOD)': f"{total_revenue:.3f}",
            'Total Costs (JOD)': f"{total_costs:.3f}",
            'Total Profit (JOD)': f"{total_profit:.3f}",
            'Total Transactions': safe_int(total_stats['transaction_count']),
            'Average Daily Revenue (JOD)': f"{(total_revenue / (end_date - start_date).days):.3f}",
            'Generated By': request.user.username
        }
        
        headers = [
            'Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit Margin (%)', 
            'Sales Count', 'Avg Transaction Value (JOD)', 'Type'
        ]
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Analytics Report")
                exporter.add_title("Analytics Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(vessel_analytics)
                
                # Add summary
                summary_data = {
                    'Analysis Period': f"{(end_date - start_date).days} days",
                    'Total Revenue (JOD)': f"{total_revenue:.3f}",
                    'Overall Profit Margin (%)': f"{(total_profit / total_revenue * 100) if total_revenue > 0 else 0:.1f}%",
                    'Best Performing Vessel': vessel_analytics[0][0] if vessel_analytics else 'N/A'
                }
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel analytics export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_pdf_exporter_for_data("Analytics Report", "wide")
                exporter.add_title("Analytics Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, vessel_analytics, auto_size_columns=True)
                
                return exporter.get_response(f"{filename_base}.pdf")
                
            except Exception as e:
                logger.error(f"PDF analytics export error: {e}")
                return JsonResponse({'success': False, 'error': f'PDF export failed: {str(e)}'})
                
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Analytics export error: {e}")
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})