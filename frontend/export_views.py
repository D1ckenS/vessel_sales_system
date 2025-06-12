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

@login_required
def export_inventory(request):
    """Export inventory data to Excel or PDF"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')  # 'excel' or 'pdf'
        vessel_id = data.get('vessel_id')
        
        # Get vessel and inventory data (similar to inventory_data_ajax)
        vessel = Vessel.objects.get(id=vessel_id, active=True)
        
        # Get inventory data (reuse logic from inventory_data_ajax)
        available_lots = InventoryLot.objects.filter(
            vessel=vessel,
            remaining_quantity__gt=0,
            product__active=True
        ).select_related('product')
        
        inventory_summary = available_lots.values(
            'product__id', 'product__name', 'product__item_id', 
            'product__barcode', 'product__is_duty_free'
        ).annotate(
            total_quantity=Sum('remaining_quantity')
        ).order_by('product__item_id')
        
        # Prepare data for export
        headers = ['Product Name', 'Item ID', 'Barcode', 'Stock Quantity', 'Current Cost (JOD)', 'Total Value (JOD)', 'Status']
        
        data_rows = []
        for item in inventory_summary:
            product_id = item['product__id']
            total_qty = item['total_quantity']
            
            # Get current cost (oldest lot)
            lots = InventoryLot.objects.filter(
                vessel=vessel,
                product_id=product_id,
                remaining_quantity__gt=0
            ).order_by('purchase_date', 'created_at')
            
            current_cost = lots.first().purchase_price if lots.exists() else 0
            total_value = sum(lot.remaining_quantity * lot.purchase_price for lot in lots)
            
            # Determine status
            if total_qty == 0:
                status = 'Out of Stock'
            elif total_qty <= 10:
                status = 'Low Stock'
            else:
                status = 'Good Stock'
                
            data_rows.append([
                item['product__name'],
                item['product__item_id'],
                item['product__barcode'] or 'N/A',
                total_qty,
                f"{current_cost:.3f}",
                f"{total_value:.3f}",
                status
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"inventory_{vessel.name}_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Vessel': vessel.name,
            'Total Products': len(data_rows),
            'Generated By': request.user.username
        }
        
        if export_format == 'excel':
            exporter = ExcelExporter()
            exporter.add_title(f"{vessel.name} Inventory Report", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_headers(headers)
            exporter.add_data_rows(data_rows)
            
            return exporter.get_response(f"{filename_base}.xlsx")
            
        else:  # PDF
            exporter = PDFExporter()
            exporter.add_title(f"{vessel.name} Inventory Report", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_table(headers, data_rows)
            
            return exporter.get_response(f"{filename_base}.pdf")
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def export_transactions(request):
    """Export transaction data to Excel or PDF"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get filter parameters
        vessel_filter = data.get('vessel_filter')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        transaction_type_filter = data.get('transaction_type_filter')
        
        # Build query (similar to comprehensive_report view)
        transactions = Transaction.objects.select_related(
            'vessel', 'product', 'created_by', 'trip', 'purchase_order'
        ).order_by('-transaction_date', '-created_at')
        
        # Apply filters
        if vessel_filter:
            transactions = transactions.filter(vessel_id=vessel_filter)
        if date_from:
            transactions = transactions.filter(transaction_date__gte=date_from)
        if date_to:
            transactions = transactions.filter(transaction_date__lte=date_to)
        if transaction_type_filter:
            transactions = transactions.filter(transaction_type=transaction_type_filter)
        
        # Prepare data
        headers = ['Date', 'Type', 'Vessel', 'Product', 'Quantity', 'Unit Price (JOD)', 'Total Amount (JOD)', 'Reference', 'Created By']
        
        data_rows = []
        for transaction in transactions[:1000]:  # Limit to 1000 rows for performance
            reference = ""
            if transaction.trip:
                reference = f"Trip: {transaction.trip.trip_number}"
            elif transaction.purchase_order:
                reference = f"PO: {transaction.purchase_order.po_number}"
            elif transaction.transfer_to_vessel:
                reference = f"To: {transaction.transfer_to_vessel.name}"
            
            data_rows.append([
                transaction.transaction_date.strftime('%d/%m/%Y'),
                transaction.get_transaction_type_display(),
                transaction.vessel.name,
                transaction.product.name,
                transaction.quantity,
                f"{transaction.unit_price:.3f}",
                f"{transaction.total_amount:.3f}",
                reference,
                transaction.created_by.username if transaction.created_by else 'System'
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"transactions_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Total Transactions': len(data_rows),
            'Filters Applied': 'Yes' if any([vessel_filter, date_from, date_to, transaction_type_filter]) else 'No',
            'Generated By': request.user.username
        }
        
        if date_from:
            metadata['Date From'] = date_from
        if date_to:
            metadata['Date To'] = date_to
        
        if export_format == 'excel':
            exporter = ExcelExporter()
            exporter.add_title("Transaction Report", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_headers(headers)
            exporter.add_data_rows(data_rows)
            
            return exporter.get_response(f"{filename_base}.xlsx")
            
        else:  # PDF
            exporter = PDFExporter()
            exporter.add_title("Transaction Report", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_table(headers, data_rows)
            
            return exporter.get_response(f"{filename_base}.pdf")
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def export_trips(request):
    """Export trip reports to Excel or PDF"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get filter parameters
        vessel_filter = data.get('vessel_filter')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        status_filter = data.get('status_filter')
        
        # Build query
        trips = Trip.objects.select_related('vessel', 'created_by')
        
        if vessel_filter:
            trips = trips.filter(vessel_id=vessel_filter)
        if date_from:
            trips = trips.filter(trip_date__gte=date_from)
        if date_to:
            trips = trips.filter(trip_date__lte=date_to)
        if status_filter == 'completed':
            trips = trips.filter(is_completed=True)
        elif status_filter == 'in_progress':
            trips = trips.filter(is_completed=False)
        
        trips = trips.order_by('-trip_date', '-created_at')
        
        # Prepare data
        headers = ['Trip Number', 'Vessel', 'Trip Date', 'Passengers', 'Revenue (JOD)', 'Items Sold', 'Status', 'Created By', 'Revenue per Passenger']
        
        data_rows = []
        for trip in trips:
            revenue = trip.total_revenue
            items_sold = trip.total_items_sold
            revenue_per_passenger = revenue / trip.passenger_count if trip.passenger_count > 0 else 0
            
            data_rows.append([
                trip.trip_number,
                trip.vessel.name,
                trip.trip_date.strftime('%d/%m/%Y'),
                trip.passenger_count,
                f"{revenue:.3f}",
                items_sold,
                'Completed' if trip.is_completed else 'In Progress',
                trip.created_by.username if trip.created_by else 'System',
                f"{revenue_per_passenger:.3f}"
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"trip_reports_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Total Trips': len(data_rows),
            'Generated By': request.user.username
        }
        
        if vessel_filter:
            vessel = Vessel.objects.get(id=vessel_filter)
            metadata['Vessel Filter'] = vessel.name
        if date_from:
            metadata['Date From'] = date_from
        if date_to:
            metadata['Date To'] = date_to
        
        if export_format == 'excel':
            exporter = ExcelExporter()
            exporter.add_title("Trip Reports", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_headers(headers)
            exporter.add_data_rows(data_rows)
            
            return exporter.get_response(f"{filename_base}.xlsx")
            
        else:  # PDF
            exporter = PDFExporter()
            exporter.add_title("Trip Reports", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_table(headers, data_rows)
            
            return exporter.get_response(f"{filename_base}.pdf")
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def export_purchase_orders(request):
    """Export purchase order reports to Excel or PDF"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get filter parameters
        vessel_filter = data.get('vessel_filter')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        status_filter = data.get('status_filter')
        
        # Build query
        purchase_orders = PurchaseOrder.objects.select_related('vessel', 'created_by')
        
        if vessel_filter:
            purchase_orders = purchase_orders.filter(vessel_id=vessel_filter)
        if date_from:
            purchase_orders = purchase_orders.filter(po_date__gte=date_from)
        if date_to:
            purchase_orders = purchase_orders.filter(po_date__lte=date_to)
        if status_filter == 'completed':
            purchase_orders = purchase_orders.filter(is_completed=True)
        elif status_filter == 'in_progress':
            purchase_orders = purchase_orders.filter(is_completed=False)
        
        purchase_orders = purchase_orders.order_by('-po_date', '-created_at')
        
        # Prepare data
        headers = ['PO Number', 'Vessel', 'PO Date', 'Total Cost (JOD)', 'Items Count', 'Status', 'Created By', 'Average Cost per Item']
        
        data_rows = []
        for po in purchase_orders:
            total_cost = po.total_cost
            items_count = po.transaction_count
            avg_cost_per_item = total_cost / items_count if items_count > 0 else 0
            
            data_rows.append([
                po.po_number,
                po.vessel.name,
                po.po_date.strftime('%d/%m/%Y'),
                f"{total_cost:.3f}",
                items_count,
                'Completed' if po.is_completed else 'In Progress',
                po.created_by.username if po.created_by else 'System',
                f"{avg_cost_per_item:.3f}"
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"purchase_order_reports_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Total Purchase Orders': len(data_rows),
            'Generated By': request.user.username
        }
        
        if vessel_filter:
            vessel = Vessel.objects.get(id=vessel_filter)
            metadata['Vessel Filter'] = vessel.name
        if date_from:
            metadata['Date From'] = date_from
        if date_to:
            metadata['Date To'] = date_to
        
        if export_format == 'excel':
            exporter = ExcelExporter()
            exporter.add_title("Purchase Order Reports", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_headers(headers)
            exporter.add_data_rows(data_rows)
            
            return exporter.get_response(f"{filename_base}.xlsx")
            
        else:  # PDF
            exporter = PDFExporter()
            exporter.add_title("Purchase Order Reports", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            exporter.add_table(headers, data_rows)
            
            return exporter.get_response(f"{filename_base}.pdf")
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def export_monthly_report(request):
    """Export monthly report to Excel or PDF"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        selected_month = int(data.get('month', datetime.now().month))
        selected_year = int(data.get('year', datetime.now().year))
        
        # Calculate month date range
        
        first_day = date(selected_year, selected_month, 1)
        if selected_month == 12:
            last_day = date(selected_year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(selected_year, selected_month + 1, 1) - timedelta(days=1)
        
        # Get monthly transactions
        monthly_transactions = Transaction.objects.filter(
            transaction_date__gte=first_day,
            transaction_date__lte=last_day
        )
        
        # Calculate stats using F() expressions
        monthly_stats = monthly_transactions.aggregate(
            total_revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
            total_costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
            total_transactions=Count('id'),
            sales_count=Count('id', filter=Q(transaction_type='SALE')),
            supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
        )
        
        monthly_revenue = monthly_stats['total_revenue'] or 0
        monthly_costs = monthly_stats['total_costs'] or 0
        monthly_profit = monthly_revenue - monthly_costs
        
        # Get vessel performance
        vessels = Vessel.objects.filter(active=True)
        vessel_performance = []
        
        for vessel in vessels:
            vessel_transactions = monthly_transactions.filter(vessel=vessel)
            vessel_stats = vessel_transactions.aggregate(
                revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
                costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
                sales_count=Count('id', filter=Q(transaction_type='SALE')),
                supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
            )
            
            vessel_revenue = vessel_stats['revenue'] or 0
            vessel_costs = vessel_stats['costs'] or 0
            vessel_profit = vessel_revenue - vessel_costs
            
            vessel_performance.append([
                vessel.name,
                f"{vessel_revenue:.3f}",
                f"{vessel_costs:.3f}",
                f"{vessel_profit:.3f}",
                vessel_stats['sales_count'] or 0,
                vessel_stats['supply_count'] or 0
            ])
        
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
            'Total Transactions': monthly_stats['total_transactions'] or 0,
            'Generated By': request.user.username
        }
        
        if export_format == 'excel':
            exporter = ExcelExporter()
            exporter.add_title(f"Monthly Report - {month_name} {selected_year}", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            
            # Add vessel performance table
            headers = ['Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit (JOD)', 'Sales Count', 'Supply Count']
            exporter.add_headers(headers)
            exporter.add_data_rows(vessel_performance)
            
            return exporter.get_response(f"{filename_base}.xlsx")
            
        else:  # PDF
            exporter = PDFExporter()
            exporter.add_title(f"Monthly Report - {month_name} {selected_year}", f"Generated on {datetime.now().strftime('%d/%m/%Y')}")
            exporter.add_metadata(metadata)
            
            headers = ['Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit (JOD)', 'Sales Count', 'Supply Count']
            exporter.add_table(headers, vessel_performance)
            
            return exporter.get_response(f"{filename_base}.pdf")
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

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
        
        # Build query
        transactions = Transaction.objects.select_related(
            'vessel', 'product', 'product__category', 'created_by', 'trip', 'purchase_order'
        ).filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).order_by('-created_at')
        
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
                format_datetime(transaction.created_at),
                transaction.get_transaction_type_display() if hasattr(transaction, 'get_transaction_type_display') else transaction.transaction_type,
                transaction.vessel.name if transaction.vessel else 'N/A',
                transaction.product.name if transaction.product else 'N/A',
                transaction.product.category.name if transaction.product and transaction.product.category else 'N/A',
                f"{safe_float(transaction.quantity):.2f}",
                f"{safe_float(transaction.unit_price):.3f}",
                f"{amount:.3f}",
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
            'Date & Time', 'Type', 'Vessel', 'Product', 'Category', 
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
        
        # Get current inventory - this is a complex calculation
        # You might need to adjust this based on your actual inventory calculation logic
        
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
            if low_stock_only and current_stock >= (product.min_stock_level or 10):
                continue
                
            # Calculate value
            unit_price = safe_float(product.current_price or product.default_price)
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
                product.product_id or 'N/A',
                product.category.name if product.category else 'Uncategorized',
                f"{current_stock:.2f}",
                f"{unit_price:.3f}",
                f"{total_item_value:.3f}",
                vessel_name,
                f"{product.min_stock_level or 0:.0f}",
                'Low Stock' if current_stock < (product.min_stock_level or 10) else 'OK',
                format_datetime(product.updated_at or product.created_at)
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
# PURCHASE ORDER EXPORTS
# ===============================================================================

@login_required
@require_http_methods(["POST"])
def export_purchase_orders(request):
    """Export purchase orders to Excel or PDF"""
    try:
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get filters
        start_date, end_date = get_date_range_from_request(data)
        if not start_date or not end_date:
            return JsonResponse({'success': False, 'error': 'Invalid date range'})
            
        status = data.get('status')
        vessel_id = data.get('vessel_id')
        
        # Build query
        pos = PurchaseOrder.objects.select_related(
            'vessel', 'created_by'
        ).filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).order_by('-created_at')
        
        # Apply filters
        if status:
            pos = pos.filter(status=status)
        if vessel_id:
            pos = pos.filter(vessel_id=vessel_id)
            
        # Prepare table data
        table_data = []
        total_cost = 0
        
        for po in pos[:2000]:  # Limit to prevent memory issues
            po_total = safe_float(po.total_cost)
            total_cost += po_total
            
            table_data.append([
                po.po_number,
                format_date(po.created_at),
                po.vessel.name if po.vessel else 'N/A',
                po.supplier_name or 'N/A',
                po.get_status_display() if hasattr(po, 'get_status_display') else po.status,
                f"{po_total:.3f}",
                safe_int(po.total_items),
                format_date(po.expected_delivery_date),
                format_date(po.actual_delivery_date) if po.actual_delivery_date else 'Pending',
                po.created_by.username if po.created_by else 'System',
                po.notes or ''
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

# ===============================================================================
# TRIPS EXPORTS
# ===============================================================================

@login_required
@require_http_methods(["POST"])
def export_trips(request):
    """Export trips to Excel or PDF"""
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
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).order_by('-created_at')
        
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
                format_datetime(trip.created_at),
                trip.vessel.name if trip.vessel else 'N/A',
                trip.get_status_display() if hasattr(trip, 'get_status_display') else trip.status,
                f"{trip_revenue:.3f}",
                safe_int(transaction_count),
                format_datetime(trip.start_time) if trip.start_time else 'N/A',
                format_datetime(trip.end_time) if trip.end_time else 'Ongoing',
                trip.created_by.username if trip.created_by else 'System',
                trip.notes or ''
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
            'Trip Number', 'Date Created', 'Vessel', 'Status', 
            'Revenue (JOD)', 'Transactions', 'Start Time', 
            'End Time', 'Created By', 'Notes'
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
                f"{vessel_revenue:.3f}",
                f"{vessel_costs:.3f}",
                f"{vessel_profit:.3f}",
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
                    f"{vessel_revenue:.3f}",
                    f"{vessel_costs:.3f}",
                    f"{vessel_profit:.3f}",
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
                f"{vessel_revenue:.3f}",
                f"{vessel_costs:.3f}",
                f"{profit_margin:.1f}%",
                safe_int(vessel_stats['sales_count']),
                f"{safe_float(vessel_stats['avg_transaction_value']):.3f}",
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