"""
API Export Views
Provides REST API endpoints for PDF and Excel export functionality.
"""

from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.http import HttpResponse
from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models import Sum, Count, F, Avg, Min, Max, Q
from django.shortcuts import get_object_or_404

from products.models import Product, Category
from transactions.models import Transaction, InventoryLot, Trip, PurchaseOrder, Transfer, WasteReport
from vessels.models import Vessel
from frontend.utils.exports import ExcelExporter, PDFExporter, create_pdf_exporter_for_data
from frontend.utils.helpers import (
    format_currency, format_date, get_date_range_from_request,
    calculate_totals_by_type, calculate_product_level_summary
)

import logging

logger = logging.getLogger(__name__)


class ExportViewSet(viewsets.ViewSet):
    """
    ViewSet for export operations via API.
    
    Provides endpoints for:
    - Transaction exports (PDF/Excel)
    - Inventory reports (PDF/Excel)  
    - Sales reports (PDF/Excel)
    - Financial summaries (PDF/Excel)
    """
    
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """List available export endpoints and their descriptions."""
        return Response({
            'available_exports': {
                'transactions': {
                    'excel': '/api/v1/exports/transactions/excel/',
                    'pdf': '/api/v1/exports/transactions/pdf/',
                    'description': 'Export transaction data in Excel or PDF format'
                },
                'inventory': {
                    'current': '/api/v1/exports/inventory/current/',
                    'lots': '/api/v1/exports/inventory/lots/',
                    'description': 'Export current inventory or lot details'
                },
                'sales': {
                    'summary': '/api/v1/exports/sales/summary/',
                    'detailed': '/api/v1/exports/sales/detailed/',
                    'description': 'Export sales summaries and detailed reports'
                },
                'vessels': {
                    'inventory': '/api/v1/exports/vessels/{vessel_id}/inventory/',
                    'summary': '/api/v1/exports/vessels/{vessel_id}/summary/',
                    'description': 'Export vessel-specific data'
                }
            },
            'common_parameters': {
                'start_date': 'Filter start date (YYYY-MM-DD)',
                'end_date': 'Filter end date (YYYY-MM-DD)',
                'vessel_id': 'Filter by specific vessel ID',
                'format': 'Output format: excel, pdf (default: excel)'
            },
            'authentication': 'Bearer token required for all endpoints'
        })
    
    @action(detail=False, methods=['get'], url_path='transactions/excel')
    def export_transactions_excel(self, request):
        """
        Export transactions to Excel format.
        
        Query Parameters:
        - start_date: Start date for filtering (YYYY-MM-DD)
        - end_date: End date for filtering (YYYY-MM-DD)
        - vessel: Vessel ID to filter by
        - transaction_type: Type of transaction (SALE, SUPPLY, etc.)
        - format: Optional format specification
        """
        try:
            # Get query parameters
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            vessel_id = request.GET.get('vessel')
            transaction_type = request.GET.get('transaction_type')
            
            # Build query
            transactions = Transaction.objects.select_related(
                'vessel', 'product', 'created_by'
            ).all()
            
            # Apply filters
            if start_date:
                transactions = transactions.filter(transaction_date__gte=start_date)
            if end_date:
                transactions = transactions.filter(transaction_date__lte=end_date)
            if vessel_id:
                transactions = transactions.filter(vessel_id=vessel_id)
            if transaction_type:
                transactions = transactions.filter(transaction_type=transaction_type)
            
            # Order by date
            transactions = transactions.order_by('-transaction_date', '-created_at')
            
            # Create Excel exporter
            title = f"Transactions Export - {timezone.now().strftime('%Y-%m-%d')}"
            exporter = ExcelExporter(title=title)
            
            # Add title and metadata
            subtitle = f"Period: {start_date or 'All'} to {end_date or 'All'}"
            exporter.add_title(title, subtitle)
            
            metadata = {
                'Generated': timezone.now().strftime('%Y-%m-%d %H:%M'),
                'Total Records': transactions.count(),
                'Filter - Vessel': vessel_id or 'All',
                'Filter - Type': transaction_type or 'All'
            }
            exporter.add_metadata(metadata)
            
            # Add headers
            headers = [
                'Date', 'Transaction ID', 'Vessel', 'Product', 'Type',
                'Quantity', 'Unit Price', 'Total Amount', 'Created By', 'Notes'
            ]
            exporter.add_headers(headers)
            
            # Add data
            data_rows = []
            total_amount = 0
            
            for transaction in transactions:
                total = transaction.quantity * transaction.unit_price
                total_amount += total
                
                row = [
                    transaction.transaction_date.strftime('%Y-%m-%d'),
                    transaction.id,
                    transaction.vessel.name,
                    transaction.product.name,
                    transaction.get_transaction_type_display(),
                    transaction.quantity,
                    float(transaction.unit_price),
                    float(total),
                    transaction.created_by.username if transaction.created_by else 'System',
                    transaction.notes or ''
                ]
                data_rows.append(row)
            
            exporter.add_data_rows(data_rows)
            
            # Add summary
            summary = {
                'Total Transactions': len(data_rows),
                'Total Value': f"{total_amount:.3f} JOD",
                'Average Transaction': f"{total_amount/len(data_rows):.3f} JOD" if data_rows else "0.000 JOD"
            }
            exporter.add_summary(summary)
            
            # Generate filename
            filename = f"transactions_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            return exporter.get_response(filename)
            
        except Exception as e:
            logger.error(f"Error exporting transactions to Excel: {e}")
            return Response(
                {'error': f'Export failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='transactions/pdf')
    def export_transactions_pdf(self, request):
        """Export transactions to PDF format."""
        try:
            # Get query parameters (same as Excel)
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            vessel_id = request.GET.get('vessel')
            transaction_type = request.GET.get('transaction_type')
            
            # Build query (same logic as Excel)
            transactions = Transaction.objects.select_related(
                'vessel', 'product', 'created_by'
            ).all()
            
            if start_date:
                transactions = transactions.filter(transaction_date__gte=start_date)
            if end_date:
                transactions = transactions.filter(transaction_date__lte=end_date)
            if vessel_id:
                transactions = transactions.filter(vessel_id=vessel_id)
            if transaction_type:
                transactions = transactions.filter(transaction_type=transaction_type)
            
            transactions = transactions.order_by('-transaction_date', '-created_at')
            
            # Create PDF exporter
            title = f"Transactions Report - {timezone.now().strftime('%Y-%m-%d')}"
            subtitle = f"Period: {start_date or 'All'} to {end_date or 'All'}"
            
            # Use landscape for wide transaction data
            exporter = create_pdf_exporter_for_data(title, data_width="wide")
            exporter.add_title(title, subtitle)
            
            # Add metadata
            metadata = {
                'Generated': timezone.now().strftime('%Y-%m-%d %H:%M'),
                'Total Records': transactions.count(),
                'Filter - Vessel': vessel_id or 'All',
                'Filter - Type': transaction_type or 'All'
            }
            exporter.add_metadata(metadata)
            
            # Prepare table data
            headers = [
                'Date', 'ID', 'Vessel', 'Product', 'Type',
                'Qty', 'Price', 'Total', 'User'
            ]
            
            data_rows = []
            total_amount = 0
            
            for transaction in transactions:
                total = transaction.quantity * transaction.unit_price
                total_amount += total
                
                row = [
                    transaction.transaction_date.strftime('%Y-%m-%d'),
                    str(transaction.id),
                    transaction.vessel.name[:20],  # Truncate for PDF
                    transaction.product.name[:25],
                    transaction.get_transaction_type_display(),
                    str(transaction.quantity),
                    f"{transaction.unit_price:.3f}",
                    f"{total:.3f}",
                    transaction.created_by.username if transaction.created_by else 'System'
                ]
                data_rows.append(row)
            
            exporter.add_table(headers, data_rows)
            
            # Add summary
            summary = {
                'Total Transactions': len(data_rows),
                'Total Value': f"{total_amount:.3f} JOD",
                'Average Transaction': f"{total_amount/len(data_rows):.3f} JOD" if data_rows else "0.000 JOD"
            }
            exporter.add_summary(summary)
            
            # Generate filename
            filename = f"transactions_report_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            return exporter.get_response(filename)
            
        except Exception as e:
            logger.error(f"Error exporting transactions to PDF: {e}")
            return Response(
                {'error': f'Export failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='inventory/excel')
    def export_inventory_excel(self, request):
        """Export current inventory levels to Excel."""
        try:
            vessel_id = request.GET.get('vessel')
            low_stock_only = request.GET.get('low_stock_only', 'false').lower() == 'true'
            
            # Get inventory data
            inventory_query = InventoryLot.objects.select_related(
                'vessel', 'product', 'product__category'
            ).filter(remaining_quantity__gt=0)
            
            if vessel_id:
                inventory_query = inventory_query.filter(vessel_id=vessel_id)
            
            inventory_lots = inventory_query.order_by('vessel__name', 'product__name', 'purchase_date')
            
            # Create Excel exporter
            title = f"Inventory Report - {timezone.now().strftime('%Y-%m-%d')}"
            exporter = ExcelExporter(title=title)
            
            exporter.add_title(title, f"Current inventory levels as of {timezone.now().strftime('%Y-%m-%d %H:%M')}")
            
            # Add metadata
            metadata = {
                'Generated': timezone.now().strftime('%Y-%m-%d %H:%M'),
                'Filter - Vessel': vessel_id or 'All vessels',
                'Filter - Low Stock Only': 'Yes' if low_stock_only else 'No',
                'Total Lots': inventory_lots.count()
            }
            exporter.add_metadata(metadata)
            
            # Add headers
            headers = [
                'Vessel', 'Product', 'Category', 'Purchase Date',
                'Original Quantity', 'Remaining Quantity', 'Unit Cost',
                'Total Value', 'Days in Stock'
            ]
            exporter.add_headers(headers)
            
            # Add data
            data_rows = []
            total_value = 0
            
            for lot in inventory_lots:
                lot_value = lot.remaining_quantity * lot.purchase_price
                total_value += lot_value
                
                days_in_stock = (timezone.now().date() - lot.purchase_date).days
                
                row = [
                    lot.vessel.name,
                    lot.product.name,
                    lot.product.category.name,
                    lot.purchase_date.strftime('%Y-%m-%d'),
                    lot.original_quantity,
                    lot.remaining_quantity,
                    float(lot.purchase_price),
                    float(lot_value),
                    days_in_stock
                ]
                data_rows.append(row)
            
            exporter.add_data_rows(data_rows)
            
            # Add summary
            summary = {
                'Total Inventory Lots': len(data_rows),
                'Total Inventory Value': f"{total_value:.3f} JOD",
                'Average Lot Value': f"{total_value/len(data_rows):.3f} JOD" if data_rows else "0.000 JOD"
            }
            exporter.add_summary(summary)
            
            filename = f"inventory_report_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            return exporter.get_response(filename)
            
        except Exception as e:
            logger.error(f"Error exporting inventory to Excel: {e}")
            return Response(
                {'error': f'Export failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='sales-summary/excel')
    def export_sales_summary_excel(self, request):
        """Export sales summary by product to Excel."""
        try:
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            vessel_id = request.GET.get('vessel')
            
            # Build sales query
            sales = Transaction.objects.filter(
                transaction_type='SALE'
            ).select_related('vessel', 'product', 'product__category')
            
            if start_date:
                sales = sales.filter(transaction_date__gte=start_date)
            if end_date:
                sales = sales.filter(transaction_date__lte=end_date)
            if vessel_id:
                sales = sales.filter(vessel_id=vessel_id)
            
            # Aggregate by product
            product_sales = sales.values(
                'product__name',
                'product__category__name',
                'vessel__name'
            ).annotate(
                total_quantity=Sum('quantity'),
                total_revenue=Sum(F('quantity') * F('unit_price')),
                avg_price=Avg('unit_price'),
                transaction_count=Count('id')
            ).order_by('-total_revenue')
            
            # Create Excel exporter
            title = f"Sales Summary - {timezone.now().strftime('%Y-%m-%d')}"
            exporter = ExcelExporter(title=title)
            
            subtitle = f"Period: {start_date or 'All'} to {end_date or 'All'}"
            exporter.add_title(title, subtitle)
            
            # Add metadata
            metadata = {
                'Generated': timezone.now().strftime('%Y-%m-%d %H:%M'),
                'Filter - Vessel': vessel_id or 'All vessels',
                'Period From': start_date or 'Beginning',
                'Period To': end_date or 'Today',
                'Products Sold': product_sales.count()
            }
            exporter.add_metadata(metadata)
            
            # Add headers
            headers = [
                'Product', 'Category', 'Vessel', 'Total Quantity',
                'Total Revenue', 'Average Price', 'Transaction Count'
            ]
            exporter.add_headers(headers)
            
            # Add data
            data_rows = []
            total_revenue = 0
            total_quantity = 0
            
            for sale in product_sales:
                total_revenue += sale['total_revenue'] or 0
                total_quantity += sale['total_quantity'] or 0
                
                row = [
                    sale['product__name'],
                    sale['product__category__name'],
                    sale['vessel__name'],
                    sale['total_quantity'],
                    float(sale['total_revenue'] or 0),
                    float(sale['avg_price'] or 0),
                    sale['transaction_count']
                ]
                data_rows.append(row)
            
            exporter.add_data_rows(data_rows)
            
            # Add summary
            summary = {
                'Total Products': len(data_rows),
                'Total Revenue': f"{total_revenue:.3f} JOD",
                'Total Quantity Sold': int(total_quantity),
                'Average Revenue per Product': f"{total_revenue/len(data_rows):.3f} JOD" if data_rows else "0.000 JOD"
            }
            exporter.add_summary(summary)
            
            filename = f"sales_summary_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            return exporter.get_response(filename)
            
        except Exception as e:
            logger.error(f"Error exporting sales summary to Excel: {e}")
            return Response(
                {'error': f'Export failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='financial-summary/pdf')
    def export_financial_summary_pdf(self, request):
        """Export financial summary to PDF."""
        try:
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            vessel_id = request.GET.get('vessel')
            
            # Build date range
            if not start_date:
                start_date = (timezone.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            if not end_date:
                end_date = timezone.now().strftime('%Y-%m-%d')
            
            # Get financial data
            transactions = Transaction.objects.filter(
                transaction_date__gte=start_date,
                transaction_date__lte=end_date
            )
            
            if vessel_id:
                transactions = transactions.filter(vessel_id=vessel_id)
            
            # Calculate totals by type
            financial_data = transactions.values('transaction_type').annotate(
                total_quantity=Sum('quantity'),
                total_value=Sum(F('quantity') * F('unit_price')),
                transaction_count=Count('id')
            ).order_by('transaction_type')
            
            # Create PDF exporter
            title = f"Financial Summary - {start_date} to {end_date}"
            exporter = create_pdf_exporter_for_data(title, data_width="normal")
            
            exporter.add_title(title, f"Generated on {timezone.now().strftime('%Y-%m-%d %H:%M')}")
            
            # Add metadata
            metadata = {
                'Period From': start_date,
                'Period To': end_date,
                'Vessel Filter': vessel_id or 'All vessels',
                'Generated By': request.user.username,
                'Total Transactions': transactions.count()
            }
            exporter.add_metadata(metadata)
            
            # Prepare summary table
            headers = ['Transaction Type', 'Count', 'Total Quantity', 'Total Value (JOD)']
            data_rows = []
            grand_total = 0
            
            for data in financial_data:
                value = data['total_value'] or 0
                grand_total += value
                
                row = [
                    data['transaction_type'],
                    str(data['transaction_count']),
                    str(data['total_quantity'] or 0),
                    f"{value:.3f}"
                ]
                data_rows.append(row)
            
            exporter.add_table(headers, data_rows)
            
            # Add summary
            summary = {
                'Grand Total': f"{grand_total:.3f} JOD",
                'Average per Transaction': f"{grand_total/transactions.count():.3f} JOD" if transactions.count() > 0 else "0.000 JOD",
                'Report Period': f"{(datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days + 1} days"
            }
            exporter.add_summary(summary)
            
            filename = f"financial_summary_{start_date}_to_{end_date}.pdf"
            return exporter.get_response(filename)
            
        except Exception as e:
            logger.error(f"Error exporting financial summary to PDF: {e}")
            return Response(
                {'error': f'Export failed: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='formats')
    def available_formats(self, request):
        """
        Get list of available export formats and endpoints.
        """
        formats = {
            'transactions': {
                'excel': '/api/v1/exports/transactions/excel/',
                'pdf': '/api/v1/exports/transactions/pdf/',
                'description': 'Export transaction records with filters'
            },
            'inventory': {
                'excel': '/api/v1/exports/inventory/excel/',
                'description': 'Export current inventory levels'
            },
            'sales_summary': {
                'excel': '/api/v1/exports/sales-summary/excel/',
                'description': 'Export sales summary by product'
            },
            'financial_summary': {
                'pdf': '/api/v1/exports/financial-summary/pdf/',
                'description': 'Export financial summary report'
            }
        }
        
        return Response({
            'available_formats': formats,
            'common_parameters': {
                'start_date': 'Filter start date (YYYY-MM-DD)',
                'end_date': 'Filter end date (YYYY-MM-DD)', 
                'vessel': 'Vessel ID to filter by',
                'transaction_type': 'Transaction type filter (SALE, SUPPLY, etc.)'
            }
        })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_vessel_summary(request, vessel_id):
    """
    Export summary for a specific vessel.
    
    URL: /api/v1/exports/vessels/{vessel_id}/summary/
    Format: ?format=pdf|excel (default: excel)
    """
    try:
        vessel = get_object_or_404(Vessel, id=vessel_id)
        export_format = request.GET.get('format', 'excel').lower()
        
        # Get vessel data
        transactions = Transaction.objects.filter(vessel=vessel).select_related('product')
        inventory_lots = InventoryLot.objects.filter(vessel=vessel, remaining_quantity__gt=0).select_related('product')
        
        # Calculate statistics
        total_transactions = transactions.count()
        total_sales = transactions.filter(transaction_type='SALE').aggregate(
            count=Count('id'),
            revenue=Sum(F('quantity') * F('unit_price'))
        )
        
        current_inventory_value = inventory_lots.aggregate(
            value=Sum(F('remaining_quantity') * F('purchase_price'))
        )['value'] or 0
        
        if export_format == 'pdf':
            # Create PDF export
            title = f"Vessel Summary - {vessel.name}"
            exporter = create_pdf_exporter_for_data(title, data_width="normal")
            exporter.add_title(title, f"Generated on {timezone.now().strftime('%Y-%m-%d %H:%M')}")
            
            # Add vessel info
            metadata = {
                'Vessel Name': vessel.name,
                'Duty Free': 'Yes' if vessel.has_duty_free else 'No',
                'Total Transactions': total_transactions,
                'Total Sales Count': total_sales['count'] or 0,
                'Total Sales Revenue': f"{total_sales['revenue'] or 0:.3f} JOD",
                'Current Inventory Value': f"{current_inventory_value:.3f} JOD"
            }
            exporter.add_metadata(metadata)
            
            # Add recent transactions table
            recent_transactions = transactions.order_by('-transaction_date')[:20]
            headers = ['Date', 'Product', 'Type', 'Quantity', 'Unit Price', 'Total']
            data_rows = []
            
            for txn in recent_transactions:
                row = [
                    txn.transaction_date.strftime('%Y-%m-%d'),
                    txn.product.name[:30],
                    txn.get_transaction_type_display(),
                    str(txn.quantity),
                    f"{txn.unit_price:.3f}",
                    f"{txn.quantity * txn.unit_price:.3f}"
                ]
                data_rows.append(row)
            
            exporter.add_table(headers, data_rows)
            
            filename = f"vessel_summary_{vessel.name}_{timezone.now().strftime('%Y%m%d')}.pdf"
            return exporter.get_response(filename)
        
        else:  # Excel format
            title = f"Vessel Summary - {vessel.name}"
            exporter = ExcelExporter(title=title)
            exporter.add_title(title, f"Generated on {timezone.now().strftime('%Y-%m-%d %H:%M')}")
            
            # Add vessel metadata
            metadata = {
                'Vessel Name': vessel.name,
                'Duty Free': 'Yes' if vessel.has_duty_free else 'No',
                'Total Transactions': total_transactions,
                'Total Sales Count': total_sales['count'] or 0,
                'Total Sales Revenue': f"{total_sales['revenue'] or 0:.3f} JOD",
                'Current Inventory Value': f"{current_inventory_value:.3f} JOD"
            }
            exporter.add_metadata(metadata)
            
            # Add detailed transactions
            headers = [
                'Date', 'Product', 'Category', 'Type', 'Quantity', 
                'Unit Price', 'Total Amount', 'Created By', 'Notes'
            ]
            exporter.add_headers(headers)
            
            data_rows = []
            for txn in transactions.order_by('-transaction_date'):
                row = [
                    txn.transaction_date.strftime('%Y-%m-%d'),
                    txn.product.name,
                    txn.product.category.name,
                    txn.get_transaction_type_display(),
                    txn.quantity,
                    float(txn.unit_price),
                    float(txn.quantity * txn.unit_price),
                    txn.created_by.username if txn.created_by else 'System',
                    txn.notes or ''
                ]
                data_rows.append(row)
            
            exporter.add_data_rows(data_rows)
            
            filename = f"vessel_summary_{vessel.name}_{timezone.now().strftime('%Y%m%d')}.xlsx"
            return exporter.get_response(filename)
    
    except Exception as e:
        logger.error(f"Error exporting vessel summary: {e}")
        return Response(
            {'error': f'Export failed: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )