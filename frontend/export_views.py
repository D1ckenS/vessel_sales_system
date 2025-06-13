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
from .utils.exports import ExcelExporter
from .utils.weasy_exporter import create_weasy_exporter_for_data, create_weasy_exporter
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
import logging
from products.models import Product, Category
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# Set up logging
logger = logging.getLogger(__name__)

# ===============================================================================
# HELPER FUNCTIONS
# ===============================================================================

def format_currency(value, decimals=3):
    """Format currency with specified decimal places"""
    try:
        return f"{float(value):.{decimals}f}"
    except (ValueError, TypeError):
        return "0.000"

def format_percentage(value):
    """Format percentage with 0 decimal places"""
    try:
        return f"{float(value):.0f}%"
    except (ValueError, TypeError):
        return "0%"

def format_negative_if_supply(value, transaction_type):
    """Format value as negative if it's a supply transaction"""
    try:
        formatted_value = float(value)
        if transaction_type in ['SUPPLY', 'TRANSFER_IN']:
            return f"({format_currency(abs(formatted_value), 3)})"
        return format_currency(formatted_value, 3)
    except (ValueError, TypeError):
        return "0.000"

def get_fifo_cost_for_transfer(vessel, product, quantity):
    """Get FIFO cost for transfer without actually consuming inventory"""
    lots = InventoryLot.objects.filter(
        vessel=vessel,
        product=product,
        remaining_quantity__gt=0
    ).order_by('purchase_date', 'created_at')
    
    remaining_to_transfer = float(quantity)
    total_cost = 0
    
    for lot in lots:
        if remaining_to_transfer <= 0:
            break
            
        available = float(lot.remaining_quantity)
        to_take = min(available, remaining_to_transfer)
        
        total_cost += to_take * float(lot.purchase_price)
        remaining_to_transfer -= to_take
    
    if remaining_to_transfer > 0:
        # Not enough inventory, use product's purchase price as fallback
        if hasattr(product, 'purchase_price'):
            total_cost += remaining_to_transfer * float(product.purchase_price)
        else:
            total_cost += remaining_to_transfer * float(product.cost_price or 0)
    
    return total_cost / float(quantity) if quantity > 0 else 0

def calculate_transfer_amounts(transaction):
    """Calculate proper amounts for transfer transactions using FIFO"""
    if transaction.transaction_type == 'TRANSFER_OUT':
        # Use FIFO cost as "revenue" for transfer out
        try:
            fifo_cost = get_fifo_cost_for_transfer(
                transaction.vessel, 
                transaction.product, 
                transaction.quantity
            )
            return fifo_cost * float(transaction.quantity)
        except Exception as e:
            logger.warning(f"Error calculating FIFO cost for transfer: {e}")
            return float(transaction.quantity) * float(transaction.unit_price)
    elif transaction.transaction_type == 'TRANSFER_IN':
        # Use the same FIFO cost as "supply cost" for transfer in
        try:
            if hasattr(transaction, 'related_transfer') and transaction.related_transfer:
                return calculate_transfer_amounts(transaction.related_transfer)
            else:
                # Fallback: use the transaction's unit price
                return float(transaction.quantity) * float(transaction.unit_price)
        except Exception as e:
            logger.warning(f"Error calculating transfer in cost: {e}")
            return float(transaction.quantity) * float(transaction.unit_price)
    return float(transaction.quantity) * float(transaction.unit_price)

def calculate_totals_by_type(transactions):
    """Calculate totals split by transaction type"""
    totals = {
        'total_sales': 0,
        'total_supplies': 0,
        'total_transfers': 0
    }
    
    for transaction in transactions:
        if transaction.transaction_type == 'SALE':
            totals['total_sales'] += float(transaction.quantity) * float(transaction.unit_price)
        elif transaction.transaction_type == 'SUPPLY':
            totals['total_supplies'] += float(transaction.quantity) * float(transaction.unit_price)
        elif transaction.transaction_type in ['TRANSFER_OUT', 'TRANSFER_IN']:
            # Only count transfer out to avoid double counting
            if transaction.transaction_type == 'TRANSFER_OUT':
                totals['total_transfers'] += calculate_transfer_amounts(transaction)
    
    return totals

def calculate_product_level_summary(transactions):
    """Calculate product-level summary for reports"""
    from collections import defaultdict
    
    products = defaultdict(lambda: {
        'name': '',
        'product_id': '',
        'qty_supplied': 0,
        'qty_sold': 0, 
        'total_cost': 0,
        'total_revenue': 0
    })
    
    for transaction in transactions:
        if not transaction.product:
            continue
            
        product_key = transaction.product.id
        product_data = products[product_key]
        
        # Set product info
        product_data['name'] = transaction.product.name
        product_data['product_id'] = getattr(transaction.product, 'product_id', 'N/A')
        
        # Calculate quantities and amounts
        quantity = safe_float(transaction.quantity)
        
        if transaction.transaction_type == 'SUPPLY':
            product_data['qty_supplied'] += quantity
            product_data['total_cost'] += quantity * safe_float(transaction.unit_price)
        elif transaction.transaction_type == 'SALE':
            product_data['qty_sold'] += quantity
            product_data['total_revenue'] += quantity * safe_float(transaction.unit_price)
        # Note: Transfers are not included in product summary as they don't change overall inventory
    
    # Convert to list format for export
    summary_data = []
    for product_data in products.values():
        net_profit = product_data['total_revenue'] - product_data['total_cost']
        summary_data.append([
            product_data['name'],
            product_data['product_id'],
            format_currency(product_data['qty_supplied'], 3),
            format_currency(product_data['qty_sold'], 3),
            format_currency(product_data['total_cost'], 3),
            format_currency(product_data['total_revenue'], 3),
            format_currency(net_profit, 3)
        ])
    
    # Sort by net profit descending
    summary_data.sort(key=lambda x: float(x[6].replace(',', '').replace('(', '-').replace(')', '')), reverse=True)
    
    return summary_data

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
# INVENTORY EXPORT
# ===============================================================================

@login_required
@require_http_methods(["POST"])
def export_inventory(request):
    """Export current inventory status to Excel or PDF"""
    try:
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get filters
        category_id = data.get('category_id')
        low_stock_only = data.get('low_stock_only', False)
        
        # Build query
        inventory_lots = InventoryLot.objects.select_related(
            'product', 'product__category', 'vessel'
        ).filter(
            quantity__gt=0  # Only active inventory
        ).order_by('product__name', 'vessel__name')
        
        # Apply filters
        if category_id:
            inventory_lots = inventory_lots.filter(product__category_id=category_id)
        if low_stock_only:
            inventory_lots = inventory_lots.filter(quantity__lte=F('product__minimum_stock_level'))
        
        # Prepare inventory data
        inventory_data = []
        total_value = 0
        
        for lot in inventory_lots[:2000]:  # Limit to prevent memory issues
            unit_cost = safe_float(getattr(lot, 'unit_cost', lot.product.cost_price if lot.product else 0))
            total_cost = safe_float(lot.quantity) * unit_cost
            total_value += total_cost
            
            inventory_data.append([
                lot.product.name if lot.product else 'N/A',
                lot.product.product_id if lot.product else 'N/A',
                lot.product.category.name if lot.product and lot.product.category else 'N/A',
                lot.vessel.name if lot.vessel else 'N/A',
                format_currency(lot.quantity, 3),
                format_currency(getattr(lot.product, 'minimum_stock_level', 0) if lot.product else 0, 3),
                format_currency(unit_cost, 3),
                format_currency(total_cost, 3),
                format_date(lot.created_at.date()) if hasattr(lot, 'created_at') and lot.created_at else 'N/A'
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"inventory_export_{timestamp}"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Total Records': len(inventory_data),
            'Total Inventory Value (JOD)': format_currency(total_value, 3),
            'Generated By': request.user.username,
            'Category Filter': category_id or 'All',
            'Low Stock Only': 'Yes' if low_stock_only else 'No'
        }
        
        headers = [
            'Product Name', 'Product ID', 'Category', 'Vessel', 
            'Current Stock', 'Minimum Level', 'Unit Cost (JOD)', 
            'Total Value (JOD)', 'Last Updated'
        ]
        
        # Create summary data
        low_stock_count = len([item for item in inventory_data if safe_float(item[4].replace(',', '')) <= safe_float(item[5].replace(',', ''))]) if inventory_data else 0
        
        summary_data = {
            'Total Products': len(inventory_data),
            'Total Value (JOD)': format_currency(total_value, 3),
            'Average Value per Item (JOD)': format_currency((total_value / len(inventory_data)) if inventory_data else 0, 3),
            'Low Stock Items': low_stock_count
        }
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Inventory Export")
                exporter.add_title("Inventory Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(inventory_data)
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel inventory export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_weasy_exporter_for_data("Inventory Report", "wide")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, inventory_data, table_title="Current Inventory Status")
                exporter.add_summary(summary_data)
                
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
            
        # Calculate totals by type
        transaction_list = list(transactions[:5000])  # Limit to prevent memory issues
        totals_by_type = calculate_totals_by_type(transaction_list)
        
        # Prepare table data with new formatting
        table_data = []
        
        for transaction in transaction_list:
            # Calculate amount based on transaction type
            if transaction.transaction_type in ['TRANSFER_OUT', 'TRANSFER_IN']:
                amount = calculate_transfer_amounts(transaction)
            else:
                amount = safe_float(transaction.quantity) * safe_float(transaction.unit_price)
            
            # Format amount (negative for supplies and transfer ins)
            formatted_amount = format_negative_if_supply(amount, transaction.transaction_type)
            
            table_data.append([
                format_date(transaction.transaction_date),
                transaction.get_transaction_type_display() if hasattr(transaction, 'get_transaction_type_display') else transaction.transaction_type,
                transaction.vessel.name if transaction.vessel else 'N/A',
                transaction.product.name if transaction.product else 'N/A',
                transaction.product.category.name if transaction.product and transaction.product.category else 'N/A',
                format_currency(transaction.quantity, 3),
                format_currency(transaction.unit_price, 3),
                formatted_amount,  # This will show negative for supplies
                transaction.trip.trip_number if transaction.trip else 'N/A',
                transaction.purchase_order.po_number if transaction.purchase_order else 'N/A',
                transaction.created_by.username if transaction.created_by else 'System',
                transaction.notes or ''
            ])
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"transactions_export_{timestamp}"
        
        # Metadata with split totals
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Date Range': f"{format_date(start_date)} to {format_date(end_date)}",
            'Total Records': len(table_data),
            'Total Sales (JOD)': format_currency(totals_by_type['total_sales'], 3),
            'Total Supplies (JOD)': f"({format_currency(totals_by_type['total_supplies'], 3)})",
            'Total Transfers (JOD)': format_currency(totals_by_type['total_transfers'], 3),
            'Generated By': request.user.username,
            'Filters Applied': f"Vessel: {vessel_id or 'All'}, Type: {transaction_type or 'All'}, Product: {product_id or 'All'}"
        }
        
        headers = [
            'Date', 'Type', 'Vessel', 'Product', 'Category', 
            'Quantity', 'Unit Price (JOD)', 'Total Amount (JOD)', 
            'Trip #', 'PO #', 'Created By', 'Notes'
        ]
        
        # Create product-level summary (replaces redundant summary)
        product_summary = calculate_product_level_summary(transaction_list)
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Transactions Export")
                exporter.add_title("Transactions Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(table_data)
                
                # Only add product summary if we have data and it's not the same as metadata
                if product_summary and len(product_summary) > 0:
                    # Add spacing
                    exporter.current_row += 1
                    
                    # Add product summary title
                    exporter.worksheet[f'A{exporter.current_row}'] = "Product Summary"
                    exporter.worksheet[f'A{exporter.current_row}'].font = Font(size=14, bold=True, color="2C3E50")
                    
                    # Merge across all columns
                    if exporter.header_count > 1:
                        end_column = get_column_letter(exporter.header_count)
                        try:
                            exporter.worksheet.merge_cells(f'A{exporter.current_row}:{end_column}{exporter.current_row}')
                        except:
                            pass
                    
                    exporter.current_row += 1
                    
                    # Add product summary headers
                    summary_headers = ['Item Name', 'Item ID', 'Qty Supplied', 'Qty Sold', 'Total Cost', 'Total Revenue', 'Net Profit']
                    for col_idx, header in enumerate(summary_headers, 1):
                        cell = exporter.worksheet.cell(row=exporter.current_row, column=col_idx, value=header)
                        cell.font = exporter.header_font
                        cell.alignment = exporter.header_alignment
                        cell.fill = PatternFill(start_color="E3F2FD", end_color="E3F2FD", fill_type="solid")
                        cell.border = exporter.border
                    
                    exporter.current_row += 1
                    
                    # Add product summary data
                    for row in product_summary:
                        for col_idx, value in enumerate(row, 1):
                            cell = exporter.worksheet.cell(row=exporter.current_row, column=col_idx, value=str(value))
                            cell.border = exporter.border
                            if col_idx >= 3:  # Numeric columns
                                cell.alignment = Alignment(horizontal='right', vertical='center')
                        exporter.current_row += 1
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_weasy_exporter_for_data("Transactions Report", "wide")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, table_data, table_title="Transaction History")
                
                # Add product summary instead of redundant summary
                if product_summary and len(product_summary) > 0:
                    summary_headers = ['Item Name', 'Item ID', 'Qty Supplied', 'Qty Sold', 'Total Cost', 'Total Revenue', 'Net Profit']
                    exporter.add_table(summary_headers, product_summary, table_title="Product Summary")
                
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
# TRIP EXPORTS (LIST AND INDIVIDUAL)
# ===============================================================================

@login_required
@require_http_methods(["POST"])
def export_trips(request):
    """Export trips list to Excel or PDF - Updated with simplified status"""
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
            
            # Determine trip status (Completed/Pending)
            trip_status = "Completed" if getattr(trip, 'is_completed', False) or getattr(trip, 'status', '') == 'completed' else "Pending"
            
            table_data.append([
                trip.trip_number,
                format_date(trip.trip_date),
                trip.vessel.name if trip.vessel else 'N/A',
                trip_status,
                format_currency(trip_revenue, 3),
                safe_int(transaction_count),
                safe_int(getattr(trip, 'passenger_count', 0)),
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
            'Total Revenue (JOD)': format_currency(total_revenue, 3),
            'Generated By': request.user.username,
            'Vessel Filter': vessel_id or 'All',
            'Status Filter': status or 'All'
        }
        
        headers = [
            'Trip Number', 'Date', 'Vessel', 'Status', 
            'Revenue (JOD)', 'Transactions', 'Passengers', 'Created By'
        ]
        
        # Create summary data
        summary_data = {
            'Total Trips': len(table_data),
            'Total Revenue (JOD)': format_currency(total_revenue, 3),
            'Average Revenue per Trip (JOD)': format_currency((total_revenue / len(table_data)) if table_data else 0, 3)
        }
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Trips Export")
                exporter.add_title("Trips Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(table_data)
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel trips export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_weasy_exporter_for_data("Trips Report", "wide")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, table_data, table_title="Trips Overview")
                exporter.add_summary(summary_data)
                
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
    """Export individual trip details - Updated with proper formatting"""
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
                format_currency(transaction.quantity, 3),
                format_currency(transaction.unit_price, 3),
                format_currency(cogs / safe_float(transaction.quantity) if safe_float(transaction.quantity) > 0 else 0, 3),
                format_currency(revenue, 3),
                format_currency(cogs, 3),
                format_currency(profit, 3),
                transaction.notes or ''
            ])
        
        total_profit = total_revenue - total_cogs
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"trip_{trip.trip_number}_{timestamp}"
        
        # Determine trip status
        trip_status = "Completed" if getattr(trip, 'is_completed', False) or getattr(trip, 'status', '') == 'completed' else "Pending"
        
        # Metadata
        metadata = {
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Trip Number': trip.trip_number,
            'Vessel': trip.vessel.name if trip.vessel else 'N/A',
            'Trip Date': format_date(trip.trip_date),
            'Status': trip_status,
            'Passengers': safe_int(getattr(trip, 'passenger_count', 0)),
            'Total Revenue (JOD)': format_currency(total_revenue, 3),
            'Total COGS (JOD)': format_currency(total_cogs, 3),
            'Total Profit (JOD)': format_currency(total_profit, 3),
            'Profit Margin': format_percentage((total_profit/total_revenue*100) if total_revenue > 0 else 0),
            'Generated By': request.user.username
        }
        
        headers = [
            'Time', 'Product', 'Product ID', 'Quantity', 
            'Unit Selling Price (JOD)', 'COGS per Unit (JOD)', 
            'Revenue (JOD)', 'COGS (JOD)', 'Profit (JOD)', 'Notes'
        ]
        
        # Create summary data
        summary_data = {
            'Total Items Sold': len(transaction_data),
            'Total Revenue (JOD)': format_currency(total_revenue, 3),
            'Total COGS (JOD)': format_currency(total_cogs, 3),
            'Total Profit (JOD)': format_currency(total_profit, 3),
            'Profit Margin': format_percentage((total_profit/total_revenue*100) if total_revenue > 0 else 0)
        }
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title=f"Trip {trip.trip_number}")
                exporter.add_title(f"Trip Sales Report - {trip.trip_number}", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(transaction_data)
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel single trip export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_weasy_exporter_for_data(f"Trip {trip.trip_number} Report", "wide")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, transaction_data, table_title=f"Trip {trip.trip_number} - Transaction Details")
                exporter.add_summary(summary_data)
                
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
    """Export purchase orders list to Excel or PDF"""
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
            
            # Determine PO status
            po_status = "Completed" if getattr(po, 'is_completed', False) else "Pending"
            
            table_data.append([
                po.po_number,
                format_date(po.po_date),
                po.vessel.name if po.vessel else 'N/A',
                getattr(po, 'supplier_name', 'N/A'),
                po_status,
                format_currency(po_cost, 3),
                safe_int(item_count),
                format_date(getattr(po, 'expected_delivery_date', None)) if hasattr(po, 'expected_delivery_date') else 'N/A',
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
            'Total Cost (JOD)': format_currency(total_cost, 3),
            'Generated By': request.user.username,
            'Status Filter': status or 'All',
            'Vessel Filter': vessel_id or 'All'
        }
        
        headers = [
            'PO Number', 'Date Created', 'Vessel', 'Supplier', 'Status',
            'Total Cost (JOD)', 'Total Items', 'Expected Delivery', 
            'Created By', 'Notes'
        ]
        
        # Create summary data
        summary_data = {
            'Total POs': len(table_data),
            'Total Cost (JOD)': format_currency(total_cost, 3),
            'Average Cost (JOD)': format_currency((total_cost / len(table_data)) if table_data else 0, 3),
            'Completed POs': len([row for row in table_data if row[4] == 'Completed']),
            'Pending POs': len([row for row in table_data if row[4] == 'Pending'])
        }
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Purchase Orders Export")
                exporter.add_title("Purchase Orders Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(table_data)
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel PO export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_weasy_exporter_for_data("Purchase Orders Report", "wide")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, table_data, table_title="Purchase Orders Overview")
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.pdf")
                
            except Exception as e:
                logger.error(f"PDF PO export error: {e}")
                return JsonResponse({'success': False, 'error': f'PDF export failed: {str(e)}'})
                
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Purchase orders export error: {e}")
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})

@require_http_methods(["POST"])
def export_single_po(request, po_id):
    """Export individual purchase order details for journal entries"""
    try:
        data = json.loads(request.body)
        export_format = data.get('format', 'excel')
        
        # Get PO
        po = get_object_or_404(PurchaseOrder, id=po_id)
        
        # Get PO transactions (supply transactions)
        transactions = Transaction.objects.filter(
            purchase_order=po,
            transaction_type='SUPPLY'
        ).select_related('product', 'product__category').order_by('transaction_date')
        
        # Calculate total cost
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
            'Supplier': getattr(po, 'supplier_name', 'N/A'),
            'Status': 'Completed' if getattr(po, 'is_completed', False) else 'Pending',
            'Total Cost (JOD)': f"{total_cost:.3f}",
            'Generated By': request.user.username
        }
        
        headers = [
            'Time', 'Product', 'Product ID', 'Quantity', 
            'Unit Cost (JOD)', 'Total Cost (JOD)', 'Notes'
        ]
        
        # Create summary data (used by both Excel and PDF)
        summary_data = {
            'Total Items Received': len(transaction_data),
            'Total Cost (JOD)': f"{total_cost:.3f}",
            'Average Cost per Item (JOD)': f"{(total_cost / len(transaction_data)) if transaction_data else 0:.3f}"
        }
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title=f"PO {po.po_number}")
                exporter.add_title(f"Purchase Order Supply Report - {po.po_number}", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(transaction_data)
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel single PO export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_weasy_exporter_for_data(f"PO {po.po_number} Report", "normal")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, transaction_data, table_title=f"PO {po.po_number} - Item Details")
                exporter.add_summary(summary_data)
                
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
    """Export monthly performance report with transfer tracking"""
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
        
        # Get month name
        month_name = calendar.month_name[selected_month]
        
        # Calculate performance for each vessel
        vessels = Vessel.objects.filter(active=True)
        vessel_performance = []
        monthly_revenue = 0
        monthly_costs = 0
        monthly_transfer_out = 0
        monthly_transfer_in = 0
        
        for vessel in vessels:
            # Get sales (revenue) for the month
            sales = Transaction.objects.filter(
                vessel=vessel,
                transaction_type='SALE',
                transaction_date__gte=start_date,
                transaction_date__lte=end_date
            ).aggregate(
                revenue=Sum(F('quantity') * F('unit_price')),
                count=Count('id')
            )
            
            # Get supplies (costs) for the month
            supplies = Transaction.objects.filter(
                vessel=vessel,
                transaction_type='SUPPLY',
                transaction_date__gte=start_date,
                transaction_date__lte=end_date
            ).aggregate(
                costs=Sum(F('quantity') * F('unit_price')),
                count=Count('id')
            )
            
            # Get transfer out for the month
            transfers_out = Transaction.objects.filter(
                vessel=vessel,
                transaction_type='TRANSFER_OUT',
                transaction_date__gte=start_date,
                transaction_date__lte=end_date
            )
            transfer_out_total = sum(calculate_transfer_amounts(t) for t in transfers_out)
            
            # Get transfer in for the month
            transfers_in = Transaction.objects.filter(
                vessel=vessel,
                transaction_type='TRANSFER_IN',
                transaction_date__gte=start_date,
                transaction_date__lte=end_date
            )
            transfer_in_total = sum(calculate_transfer_amounts(t) for t in transfers_in)
            
            revenue = safe_float(sales['revenue'])
            costs = safe_float(supplies['costs'])
            profit = revenue - costs
            profit_margin = (profit / revenue * 100) if revenue > 0 else 0
            
            monthly_revenue += revenue
            monthly_costs += costs
            monthly_transfer_out += transfer_out_total
            monthly_transfer_in += transfer_in_total
            
            vessel_performance.append([
                vessel.name,
                format_currency(revenue, 3),
                format_currency(costs, 3),
                format_currency(profit, 3),
                format_percentage(profit_margin),
                safe_int(sales['count']),
                safe_int(supplies['count']),
                format_currency(transfer_out_total, 3),
                format_currency(transfer_in_total, 3)
            ])
        
        monthly_profit = monthly_revenue - monthly_costs
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"monthly_report_{selected_year}_{selected_month:02d}_{timestamp}"
        
        # Metadata
        metadata = {
            'Report Period': f"{month_name} {selected_year}",
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Date Range': f"{format_date(start_date)} to {format_date(end_date)}",
            'Total Revenue (JOD)': format_currency(monthly_revenue, 3),
            'Total Costs (JOD)': format_currency(monthly_costs, 3),
            'Total Profit (JOD)': format_currency(monthly_profit, 3),
            'Total Transfer Out (JOD)': format_currency(monthly_transfer_out, 3),
            'Total Transfer In (JOD)': format_currency(monthly_transfer_in, 3),
            'Overall Profit Margin': format_percentage((monthly_profit / monthly_revenue * 100) if monthly_revenue > 0 else 0),
            'Generated By': request.user.username
        }
        
        headers = [
            'Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit (JOD)', 
            'Profit Margin (%)', 'Sales Count', 'Supply Count',
            'Transfer Out (JOD)', 'Transfer In (JOD)'
        ]
        
        # Create summary data 
        summary_data = {
            'Total Vessels': len(vessel_performance),
            'Total Revenue (JOD)': format_currency(monthly_revenue, 3),
            'Total Profit (JOD)': format_currency(monthly_profit, 3),
            'Overall Profit Margin': format_percentage((monthly_profit / monthly_revenue * 100) if monthly_revenue > 0 else 0),
            'Net Transfers': format_currency(monthly_transfer_out - monthly_transfer_in, 3)
        }
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Monthly Report")
                exporter.add_title(f"Monthly Report - {month_name} {selected_year}", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(vessel_performance)
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel monthly report export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_weasy_exporter_for_data("Monthly Report", "normal")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, vessel_performance, table_title=f"Monthly Performance - {month_name} {selected_year}")
                exporter.add_summary(summary_data)
                
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
        
        # Calculate performance for each vessel for the selected day
        vessels = Vessel.objects.filter(active=True)
        vessel_performance = []
        daily_revenue = 0
        daily_costs = 0
        
        for vessel in vessels:
            # Get sales (revenue) for the day
            sales = Transaction.objects.filter(
                vessel=vessel,
                transaction_type='SALE',
                transaction_date=selected_date
            ).aggregate(
                revenue=Sum(F('quantity') * F('unit_price')),
                count=Count('id')
            )
            
            # Get supplies (costs) for the day
            supplies = Transaction.objects.filter(
                vessel=vessel,
                transaction_type='SUPPLY',
                transaction_date=selected_date
            ).aggregate(
                costs=Sum(F('quantity') * F('unit_price')),
                count=Count('id')
            )
            
            revenue = safe_float(sales['revenue'])
            costs = safe_float(supplies['costs'])
            profit = revenue - costs
            profit_margin = (profit / revenue * 100) if revenue > 0 else 0
            
            # Only include vessels with activity
            if revenue > 0 or costs > 0:
                daily_revenue += revenue
                daily_costs += costs
                
                vessel_performance.append([
                    vessel.name,
                    format_currency(revenue, 3),
                    format_currency(costs, 3),
                    format_currency(profit, 3),
                    format_percentage(profit_margin),
                    safe_int(sales['count']),
                    safe_int(supplies['count'])
                ])
        
        daily_profit = daily_revenue - daily_costs
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"daily_report_{selected_date.strftime('%Y%m%d')}_{timestamp}"
        
        # Metadata
        metadata = {
            'Report Date': format_date(selected_date),
            'Export Date': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'Total Revenue (JOD)': format_currency(daily_revenue, 3),
            'Total Costs (JOD)': format_currency(daily_costs, 3),
            'Total Profit (JOD)': format_currency(daily_profit, 3),
            'Overall Profit Margin': format_percentage((daily_profit / daily_revenue * 100) if daily_revenue > 0 else 0),
            'Generated By': request.user.username
        }
        
        headers = [
            'Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit (JOD)', 
            'Profit Margin (%)', 'Sales Count', 'Supply Count'
        ]
        
        # Create summary data
        summary_data = {
            'Active Vessels': len(vessel_performance),
            'Total Revenue (JOD)': format_currency(daily_revenue, 3),
            'Total Profit (JOD)': format_currency(daily_profit, 3),
            'Overall Profit Margin': format_percentage((daily_profit / daily_revenue * 100) if daily_revenue > 0 else 0)
        }
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Daily Report")
                exporter.add_title(f"Daily Report - {format_date(selected_date)}", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(vessel_performance)
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel daily report export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF
            try:
                exporter = create_weasy_exporter_for_data("Daily Report", "normal")
                exporter.add_metadata(metadata)
                exporter.add_table(headers, vessel_performance, table_title=f"Daily Performance - {format_date(selected_date)}")
                exporter.add_summary(summary_data)
                
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
    """Export analytics report with performance metrics and charts"""
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
        
        # Calculate comprehensive analytics for each vessel
        vessels = Vessel.objects.filter(active=True)
        vessel_analytics = []
        total_revenue = 0
        total_costs = 0
        total_pos = 0
        po_analytics = []
        
        for vessel in vessels:
            # Get sales data
            sales_stats = Transaction.objects.filter(
                vessel=vessel,
                transaction_type='SALE',
                transaction_date__gte=start_date,
                transaction_date__lte=end_date
            ).aggregate(
                revenue=Sum(F('quantity') * F('unit_price')),
                sales_count=Count('id'),
                avg_transaction=Sum(F('quantity') * F('unit_price')) / Count('id')
            )
            
            # Get supply data
            supply_stats = Transaction.objects.filter(
                vessel=vessel,
                transaction_type='SUPPLY',
                transaction_date__gte=start_date,
                transaction_date__lte=end_date
            ).aggregate(
                costs=Sum(F('quantity') * F('unit_price')),
                supply_count=Count('id')
            )
            
            # Get PO data
            po_stats = PurchaseOrder.objects.filter(
                vessel=vessel,
                po_date__gte=start_date,
                po_date__lte=end_date
            ).aggregate(
                po_count=Count('id'),
                total_po_cost=Sum('total_cost')
            )
            
            revenue = safe_float(sales_stats['revenue'])
            costs = safe_float(supply_stats['costs'])
            po_cost = safe_float(po_stats['total_po_cost'])
            profit_margin = ((revenue - costs) / revenue * 100) if revenue > 0 else 0
            
            total_revenue += revenue
            total_costs += costs
            total_pos += safe_int(po_stats['po_count'])
            
            # Only include vessels with activity
            if revenue > 0 or costs > 0 or po_cost > 0:
                vessel_analytics.append([
                    vessel.name,
                    format_currency(revenue, 3),
                    format_currency(costs, 3),
                    format_percentage(profit_margin),
                    safe_int(sales_stats['sales_count']),
                    format_currency(safe_float(sales_stats['avg_transaction']), 3),
                    safe_int(po_stats['po_count']),
                    format_currency(po_cost, 3)
                ])
                
                # For PO chart data
                if po_cost > 0:
                    po_analytics.append((vessel.name[:15], po_cost))
        
        # Sort by revenue (descending)
        vessel_analytics.sort(key=lambda x: float(x[1].replace(',', '')), reverse=True)
        
        total_profit = total_revenue - total_costs
        
        # Calculate additional statistics
        total_stats = Transaction.objects.filter(
            transaction_date__gte=start_date,
            transaction_date__lte=end_date
        ).aggregate(
            transaction_count=Count('id')
        )
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"analytics_report_{timestamp}"
        
        # Metadata
        metadata = {
            'Analysis Period': f"{format_date(start_date)} to {format_date(end_date)}",
            'Total Revenue (JOD)': format_currency(total_revenue, 3),
            'Total Costs (JOD)': format_currency(total_costs, 3),
            'Total Profit (JOD)': format_currency(total_profit, 3),
            'Total Transactions': safe_int(total_stats['transaction_count']),
            'Total Purchase Orders': total_pos,
            'Average Daily Revenue (JOD)': format_currency((total_revenue / (end_date - start_date).days), 3),
            'Overall Profit Margin': format_percentage((total_profit / total_revenue * 100) if total_revenue > 0 else 0),
            'Generated By': request.user.username
        }
        
        headers = [
            'Vessel', 'Revenue (JOD)', 'Costs (JOD)', 'Profit Margin (%)', 
            'Sales Count', 'Avg Transaction Value (JOD)', 'PO Count', 'PO Total Cost (JOD)'
        ]
        
        # Create summary data
        summary_data = {
            'Analysis Period': f"{(end_date - start_date).days} days",
            'Total Revenue (JOD)': format_currency(total_revenue, 3),
            'Overall Profit Margin': format_percentage((total_profit / total_revenue * 100) if total_revenue > 0 else 0),
            'Best Performing Vessel': vessel_analytics[0][0] if vessel_analytics else 'N/A',
            'Total Purchase Orders': total_pos
        }
        
        if export_format == 'excel':
            try:
                exporter = ExcelExporter(title="Analytics Report")
                exporter.add_title("Analytics Report", f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                exporter.add_metadata(metadata)
                exporter.add_headers(headers)
                exporter.add_data_rows(vessel_analytics)
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.xlsx")
                
            except Exception as e:
                logger.error(f"Excel analytics export error: {e}")
                return JsonResponse({'success': False, 'error': f'Excel export failed: {str(e)}'})
        
        else:  # PDF - Now landscape with charts
            try:
                exporter = create_weasy_exporter(title="Analytics Report", template_type="analytics", orientation="landscape")
                exporter.add_metadata(metadata)
                
                # Add charts for analytics
                if vessel_analytics:
                    # Extract numeric values for charts
                    try:
                        # Revenue chart - extract vessel names and revenue values
                        revenue_data = []
                        profit_data = []
                        
                        for row in vessel_analytics[:8]:  # Limit to top 8 vessels for readability
                            vessel_name = str(row[0])[:15]  # Truncate long names
                            
                            # Extract revenue (column 1) - handle formatted numbers
                            revenue_str = str(row[1]).replace(',', '').replace('JOD', '').strip()
                            try:
                                revenue_val = float(revenue_str)
                                revenue_data.append((vessel_name, revenue_val))
                            except ValueError:
                                pass
                            
                            # Extract profit margin (column 3) - handle percentage
                            profit_str = str(row[3]).replace('%', '').replace(',', '').strip()
                            try:
                                profit_val = float(profit_str)
                                profit_data.append((vessel_name, profit_val))
                            except ValueError:
                                pass
                        
                        if revenue_data:
                            exporter.add_chart(revenue_data, 'bar', 'Revenue by Vessel (JOD)', 'revenue_chart')
                        
                        if profit_data:
                            exporter.add_chart(profit_data, 'bar', 'Profit Margin by Vessel (%)', 'profit_chart')
                        
                        # Add PO chart
                        if po_analytics:
                            # Sort PO data by cost (descending) and take top 8
                            po_analytics.sort(key=lambda x: x[1], reverse=True)
                            po_chart_data = po_analytics[:8]
                            exporter.add_chart(po_chart_data, 'bar', 'Purchase Order Costs by Vessel (JOD)', 'po_chart')
                            
                    except Exception as chart_error:
                        logger.warning(f"Could not create charts for analytics: {chart_error}")
                
                exporter.add_table(headers, vessel_analytics, table_title="Vessel Performance Analytics")
                exporter.add_summary(summary_data)
                
                return exporter.get_response(f"{filename_base}.pdf")
                
            except Exception as e:
                logger.error(f"PDF analytics export error: {e}")
                return JsonResponse({'success': False, 'error': f'PDF export failed: {str(e)}'})
                
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Analytics export error: {e}")
        return JsonResponse({'success': False, 'error': f'Export failed: {str(e)}'})