"""
Custom Reports API Views
Provides dynamic report generation capabilities via REST API.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum, Count, F, Avg, Min, Max, Q
from django.http import HttpResponse
from datetime import datetime, timedelta

from transactions.models import Transaction, InventoryLot, Trip, PurchaseOrder, Transfer, WasteReport
from vessels.models import Vessel
from products.models import Product, Category
from frontend.utils.exports import ExcelExporter, create_pdf_exporter_for_data

import logging

logger = logging.getLogger(__name__)


class CustomReportsViewSet(viewsets.ViewSet):
    """
    ViewSet for custom report generation.
    
    Provides endpoints for:
    - Vessel performance analysis
    - Product profitability reports
    - Inventory aging reports
    - Financial dashboards
    - Custom query-based reports
    """
    
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """List available custom report types."""
        return Response({
            'available_reports': {
                'vessel_performance': {
                    'endpoint': '/api/v1/custom-reports/vessel-performance/',
                    'description': 'Comprehensive vessel performance analysis',
                    'parameters': ['start_date', 'end_date', 'vessel_id', 'format']
                },
                'product_profitability': {
                    'endpoint': '/api/v1/custom-reports/product-profitability/',
                    'description': 'Product profitability analysis with cost tracking',
                    'parameters': ['start_date', 'end_date', 'category_id', 'format']
                },
                'inventory_aging': {
                    'endpoint': '/api/v1/custom-reports/inventory-aging/',
                    'description': 'Inventory aging analysis for stock management',
                    'parameters': ['vessel_id', 'days_threshold', 'format']
                },
                'financial_dashboard': {
                    'endpoint': '/api/v1/custom-reports/financial-dashboard/',
                    'description': 'Comprehensive financial dashboard data',
                    'parameters': ['start_date', 'end_date', 'format']
                },
                'custom_query': {
                    'endpoint': '/api/v1/custom-reports/custom-query/',
                    'description': 'Build custom reports with flexible parameters',
                    'parameters': ['query_type', 'filters', 'groupby', 'format']
                }
            },
            'common_parameters': {
                'start_date': 'Start date for analysis (YYYY-MM-DD)',
                'end_date': 'End date for analysis (YYYY-MM-DD)',
                'vessel_id': 'Filter by specific vessel',
                'format': 'Output format: json, excel, pdf (default: json)'
            }
        })
    
    @action(detail=False, methods=['get'], url_path='vessel-performance')
    def vessel_performance_report(self, request):
        """
        Generate comprehensive vessel performance analysis.
        
        Analyzes:
        - Revenue trends
        - Trip efficiency
        - Inventory turnover
        - Profitability metrics
        """
        try:
            # Get parameters
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            vessel_id = request.GET.get('vessel_id')
            export_format = request.GET.get('format', 'json').lower()
            
            # Set default date range if not provided
            if not start_date:
                start_date = (timezone.now() - timedelta(days=90)).strftime('%Y-%m-%d')
            if not end_date:
                end_date = timezone.now().strftime('%Y-%m-%d')
            
            # Build vessel query
            vessels = Vessel.objects.filter(active=True)
            if vessel_id:
                vessels = vessels.filter(id=vessel_id)
            
            performance_data = []
            
            for vessel in vessels:
                # Get vessel transactions
                transactions = Transaction.objects.filter(
                    vessel=vessel,
                    transaction_date__gte=start_date,
                    transaction_date__lte=end_date
                )
                
                # Calculate metrics
                sales_data = transactions.filter(transaction_type='SALE').aggregate(
                    total_sales=Sum(F('quantity') * F('unit_price')),
                    sales_count=Count('id'),
                    avg_sale_value=Avg(F('quantity') * F('unit_price'))
                )
                
                supply_data = transactions.filter(transaction_type='SUPPLY').aggregate(
                    total_supply_cost=Sum(F('quantity') * F('unit_price')),
                    supply_count=Count('id')
                )
                
                # Get trip data
                trips = Trip.objects.filter(
                    vessel=vessel,
                    trip_date__gte=start_date,
                    trip_date__lte=end_date,
                    is_completed=True
                ).aggregate(
                    trip_count=Count('id'),
                    total_passengers=Sum('passenger_count'),
                    avg_passengers=Avg('passenger_count')
                )
                
                # Calculate inventory turnover
                current_inventory = InventoryLot.objects.filter(
                    vessel=vessel,
                    remaining_quantity__gt=0
                ).aggregate(
                    inventory_value=Sum(F('remaining_quantity') * F('purchase_price')),
                    inventory_items=Count('id')
                )
                
                # Calculate profitability (simplified)
                revenue = sales_data['total_sales'] or 0
                costs = supply_data['total_supply_cost'] or 0
                profit = revenue - costs
                profit_margin = (profit / revenue * 100) if revenue > 0 else 0
                
                # Calculate revenue per passenger
                revenue_per_passenger = (
                    revenue / (trips['total_passengers'] or 1)
                ) if trips['total_passengers'] else 0
                
                vessel_performance = {
                    'vessel_id': vessel.id,
                    'vessel_name': vessel.name,
                    'analysis_period': f"{start_date} to {end_date}",
                    'financial_metrics': {
                        'total_revenue': float(revenue),
                        'total_costs': float(costs),
                        'gross_profit': float(profit),
                        'profit_margin_percent': round(profit_margin, 2),
                        'average_sale_value': float(sales_data['avg_sale_value'] or 0)
                    },
                    'operational_metrics': {
                        'total_trips': trips['trip_count'] or 0,
                        'total_passengers': trips['total_passengers'] or 0,
                        'average_passengers_per_trip': round(trips['avg_passengers'] or 0, 1),
                        'revenue_per_passenger': round(revenue_per_passenger, 2),
                        'sales_transactions': sales_data['sales_count'] or 0,
                        'supply_transactions': supply_data['supply_count'] or 0
                    },
                    'inventory_metrics': {
                        'current_inventory_value': float(current_inventory['inventory_value'] or 0),
                        'inventory_items_count': current_inventory['inventory_items'] or 0,
                        'inventory_turnover_estimate': round(
                            (costs / (current_inventory['inventory_value'] or 1)), 2
                        ) if current_inventory['inventory_value'] else 0
                    }
                }
                
                performance_data.append(vessel_performance)
            
            # Handle different export formats
            if export_format == 'json':
                return Response({
                    'success': True,
                    'report_type': 'vessel_performance_analysis',
                    'generated_at': timezone.now().isoformat(),
                    'analysis_period': f"{start_date} to {end_date}",
                    'vessel_count': len(performance_data),
                    'data': performance_data
                })
            
            elif export_format == 'excel':
                return self._export_vessel_performance_excel(performance_data, start_date, end_date)
            
            elif export_format == 'pdf':
                return self._export_vessel_performance_pdf(performance_data, start_date, end_date)
            
            else:
                return Response(
                    {'error': 'Invalid format. Supported: json, excel, pdf'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        except Exception as e:
            logger.error(f"Error generating vessel performance report: {e}")
            return Response(
                {'error': f'Report generation failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='product-profitability')
    def product_profitability_report(self, request):
        """
        Generate product profitability analysis.
        
        Analyzes:
        - Product profit margins
        - Sales volume trends
        - Cost analysis
        - Category performance
        """
        try:
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            category_id = request.GET.get('category_id')
            export_format = request.GET.get('format', 'json').lower()
            
            # Set default date range
            if not start_date:
                start_date = (timezone.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            if not end_date:
                end_date = timezone.now().strftime('%Y-%m-%d')
            
            # Build product query
            products = Product.objects.filter(active=True)
            if category_id:
                products = products.filter(category_id=category_id)
            
            profitability_data = []
            
            for product in products:
                # Get sales data
                sales = Transaction.objects.filter(
                    product=product,
                    transaction_type='SALE',
                    transaction_date__gte=start_date,
                    transaction_date__lte=end_date
                ).aggregate(
                    total_revenue=Sum(F('quantity') * F('unit_price')),
                    total_quantity_sold=Sum('quantity'),
                    avg_selling_price=Avg('unit_price'),
                    sales_count=Count('id')
                )
                
                # Get cost data (from FIFO consumptions)
                fifo_costs = Transaction.objects.filter(
                    product=product,
                    transaction_type='SALE',
                    transaction_date__gte=start_date,
                    transaction_date__lte=end_date
                ).prefetch_related('fifo_consumptions').all()
                
                total_cost = 0
                for sale in fifo_costs:
                    for consumption in sale.fifo_consumptions.all():
                        total_cost += float(consumption.consumed_quantity * consumption.unit_cost)
                
                # Calculate metrics
                revenue = float(sales['total_revenue'] or 0)
                cost = total_cost
                profit = revenue - cost
                profit_margin = (profit / revenue * 100) if revenue > 0 else 0
                quantity_sold = sales['total_quantity_sold'] or 0
                
                # Get current inventory
                current_stock = InventoryLot.objects.filter(
                    product=product,
                    remaining_quantity__gt=0
                ).aggregate(
                    total_stock=Sum('remaining_quantity'),
                    avg_cost=Avg('purchase_price')
                )
                
                product_data = {
                    'product_id': product.id,
                    'product_name': product.name,
                    'category': product.category.name,
                    'analysis_period': f"{start_date} to {end_date}",
                    'financial_performance': {
                        'total_revenue': revenue,
                        'total_cost': cost,
                        'gross_profit': profit,
                        'profit_margin_percent': round(profit_margin, 2),
                        'profit_per_unit': round(profit / quantity_sold, 3) if quantity_sold > 0 else 0
                    },
                    'sales_performance': {
                        'quantity_sold': quantity_sold,
                        'sales_transactions': sales['sales_count'] or 0,
                        'average_selling_price': float(sales['avg_selling_price'] or 0),
                        'average_order_size': round(
                            quantity_sold / (sales['sales_count'] or 1), 2
                        ) if sales['sales_count'] else 0
                    },
                    'inventory_status': {
                        'current_stock': current_stock['total_stock'] or 0,
                        'average_unit_cost': float(current_stock['avg_cost'] or 0),
                        'estimated_stock_value': float(
                            (current_stock['total_stock'] or 0) * (current_stock['avg_cost'] or 0)
                        )
                    }
                }
                
                # Only include products with sales activity
                if revenue > 0 or quantity_sold > 0:
                    profitability_data.append(product_data)
            
            # Sort by profit margin descending
            profitability_data.sort(key=lambda x: x['financial_performance']['profit_margin_percent'], reverse=True)
            
            if export_format == 'json':
                return Response({
                    'success': True,
                    'report_type': 'product_profitability_analysis',
                    'generated_at': timezone.now().isoformat(),
                    'analysis_period': f"{start_date} to {end_date}",
                    'product_count': len(profitability_data),
                    'data': profitability_data
                })
            
            elif export_format == 'excel':
                return self._export_product_profitability_excel(profitability_data, start_date, end_date)
            
            else:
                return Response(
                    {'error': 'Invalid format. Supported: json, excel'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        except Exception as e:
            logger.error(f"Error generating product profitability report: {e}")
            return Response(
                {'error': f'Report generation failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='inventory-aging')
    def inventory_aging_report(self, request):
        """
        Generate inventory aging analysis.
        
        Analyzes:
        - Stock age distribution
        - Slow-moving inventory
        - Potential waste identification
        - Reorder recommendations
        """
        try:
            vessel_id = request.GET.get('vessel_id')
            days_threshold = int(request.GET.get('days_threshold', 30))
            export_format = request.GET.get('format', 'json').lower()
            
            # Build inventory query
            inventory_lots = InventoryLot.objects.filter(
                remaining_quantity__gt=0
            ).select_related('vessel', 'product', 'product__category')
            
            if vessel_id:
                inventory_lots = inventory_lots.filter(vessel_id=vessel_id)
            
            aging_data = []
            current_date = timezone.now().date()
            
            for lot in inventory_lots:
                days_in_stock = (current_date - lot.purchase_date).days
                lot_value = lot.remaining_quantity * lot.purchase_price
                
                # Categorize by age
                if days_in_stock <= 7:
                    age_category = 'Fresh (0-7 days)'
                elif days_in_stock <= 30:
                    age_category = 'Recent (8-30 days)'
                elif days_in_stock <= 90:
                    age_category = 'Aging (31-90 days)'
                else:
                    age_category = 'Old (90+ days)'
                
                # Risk assessment
                if days_in_stock > days_threshold * 2:
                    risk_level = 'High'
                elif days_in_stock > days_threshold:
                    risk_level = 'Medium'
                else:
                    risk_level = 'Low'
                
                lot_data = {
                    'vessel_name': lot.vessel.name,
                    'product_name': lot.product.name,
                    'category': lot.product.category.name,
                    'purchase_date': lot.purchase_date.strftime('%Y-%m-%d'),
                    'days_in_stock': days_in_stock,
                    'age_category': age_category,
                    'remaining_quantity': lot.remaining_quantity,
                    'unit_cost': float(lot.purchase_price),
                    'lot_value': float(lot_value),
                    'risk_level': risk_level,
                    'recommendation': self._get_aging_recommendation(days_in_stock, days_threshold)
                }
                
                aging_data.append(lot_data)
            
            # Sort by days in stock (oldest first)
            aging_data.sort(key=lambda x: x['days_in_stock'], reverse=True)
            
            # Calculate summary statistics
            total_lots = len(aging_data)
            total_value = sum(lot['lot_value'] for lot in aging_data)
            high_risk_lots = len([lot for lot in aging_data if lot['risk_level'] == 'High'])
            old_stock_value = sum(
                lot['lot_value'] for lot in aging_data 
                if lot['days_in_stock'] > days_threshold
            )
            
            summary = {
                'total_inventory_lots': total_lots,
                'total_inventory_value': round(total_value, 3),
                'high_risk_lots': high_risk_lots,
                'old_stock_percentage': round(
                    (old_stock_value / total_value * 100) if total_value > 0 else 0, 2
                ),
                'average_age_days': round(
                    sum(lot['days_in_stock'] for lot in aging_data) / total_lots, 1
                ) if total_lots > 0 else 0
            }
            
            if export_format == 'json':
                return Response({
                    'success': True,
                    'report_type': 'inventory_aging_analysis',
                    'generated_at': timezone.now().isoformat(),
                    'analysis_parameters': {
                        'vessel_filter': vessel_id or 'All vessels',
                        'aging_threshold_days': days_threshold
                    },
                    'summary': summary,
                    'data': aging_data
                })
            
            elif export_format == 'excel':
                return self._export_inventory_aging_excel(aging_data, summary, days_threshold)
            
            else:
                return Response(
                    {'error': 'Invalid format. Supported: json, excel'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        except Exception as e:
            logger.error(f"Error generating inventory aging report: {e}")
            return Response(
                {'error': f'Report generation failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_aging_recommendation(self, days_in_stock, threshold):
        """Generate aging-based recommendations."""
        if days_in_stock > threshold * 3:
            return "Consider immediate sale or waste disposal"
        elif days_in_stock > threshold * 2:
            return "Promote for quick sale"
        elif days_in_stock > threshold:
            return "Monitor closely, consider promotion"
        else:
            return "Normal stock levels"
    
    def _export_vessel_performance_excel(self, data, start_date, end_date):
        """Export vessel performance data to Excel."""
        title = f"Vessel Performance Analysis - {start_date} to {end_date}"
        exporter = ExcelExporter(title=title)
        
        exporter.add_title(title, f"Generated on {timezone.now().strftime('%Y-%m-%d %H:%M')}")
        
        # Add summary metadata
        total_revenue = sum(v['financial_metrics']['total_revenue'] for v in data)
        total_profit = sum(v['financial_metrics']['gross_profit'] for v in data)
        
        metadata = {
            'Analysis Period': f"{start_date} to {end_date}",
            'Vessels Analyzed': len(data),
            'Total Revenue': f"{total_revenue:.3f} JOD",
            'Total Profit': f"{total_profit:.3f} JOD",
            'Average Profit Margin': f"{(total_profit/total_revenue*100):.2f}%" if total_revenue > 0 else "0%"
        }
        exporter.add_metadata(metadata)
        
        # Add headers
        headers = [
            'Vessel', 'Revenue', 'Costs', 'Profit', 'Profit %', 'Trips',
            'Passengers', 'Revenue/Passenger', 'Sales Txns', 'Avg Sale',
            'Inventory Value', 'Turnover Rate'
        ]
        exporter.add_headers(headers)
        
        # Add data rows
        data_rows = []
        for vessel in data:
            fm = vessel['financial_metrics']
            om = vessel['operational_metrics']
            im = vessel['inventory_metrics']
            
            row = [
                vessel['vessel_name'],
                fm['total_revenue'],
                fm['total_costs'],
                fm['gross_profit'],
                f"{fm['profit_margin_percent']}%",
                om['total_trips'],
                om['total_passengers'],
                om['revenue_per_passenger'],
                om['sales_transactions'],
                fm['average_sale_value'],
                im['current_inventory_value'],
                im['inventory_turnover_estimate']
            ]
            data_rows.append(row)
        
        exporter.add_data_rows(data_rows)
        
        filename = f"vessel_performance_{start_date}_to_{end_date}.xlsx"
        return exporter.get_response(filename)
    
    def _export_vessel_performance_pdf(self, data, start_date, end_date):
        """Export vessel performance data to PDF."""
        title = f"Vessel Performance Analysis - {start_date} to {end_date}"
        exporter = create_pdf_exporter_for_data(title, data_width="wide")
        
        exporter.add_title(title, f"Generated on {timezone.now().strftime('%Y-%m-%d %H:%M')}")
        
        # Add summary
        total_revenue = sum(v['financial_metrics']['total_revenue'] for v in data)
        total_profit = sum(v['financial_metrics']['gross_profit'] for v in data)
        
        metadata = {
            'Analysis Period': f"{start_date} to {end_date}",
            'Vessels Analyzed': len(data),
            'Total Revenue': f"{total_revenue:.3f} JOD",
            'Total Profit': f"{total_profit:.3f} JOD"
        }
        exporter.add_metadata(metadata)
        
        # Create summary table
        headers = ['Vessel', 'Revenue', 'Profit', 'Margin %', 'Trips', 'Passengers']
        data_rows = []
        
        for vessel in data:
            fm = vessel['financial_metrics']
            om = vessel['operational_metrics']
            
            row = [
                vessel['vessel_name'][:20],
                f"{fm['total_revenue']:.0f}",
                f"{fm['gross_profit']:.0f}",
                f"{fm['profit_margin_percent']:.1f}%",
                str(om['total_trips']),
                str(om['total_passengers'])
            ]
            data_rows.append(row)
        
        exporter.add_table(headers, data_rows)
        
        filename = f"vessel_performance_{start_date}_to_{end_date}.pdf"
        return exporter.get_response(filename)
    
    def _export_product_profitability_excel(self, data, start_date, end_date):
        """Export product profitability data to Excel."""
        title = f"Product Profitability Analysis - {start_date} to {end_date}"
        exporter = ExcelExporter(title=title)
        
        exporter.add_title(title, f"Generated on {timezone.now().strftime('%Y-%m-%d %H:%M')}")
        
        # Add summary
        total_revenue = sum(p['financial_performance']['total_revenue'] for p in data)
        total_profit = sum(p['financial_performance']['gross_profit'] for p in data)
        
        metadata = {
            'Analysis Period': f"{start_date} to {end_date}",
            'Products Analyzed': len(data),
            'Total Revenue': f"{total_revenue:.3f} JOD",
            'Total Profit': f"{total_profit:.3f} JOD"
        }
        exporter.add_metadata(metadata)
        
        # Add headers
        headers = [
            'Product', 'Category', 'Revenue', 'Cost', 'Profit', 'Margin %',
            'Qty Sold', 'Avg Price', 'Profit/Unit', 'Current Stock'
        ]
        exporter.add_headers(headers)
        
        # Add data rows
        data_rows = []
        for product in data:
            fp = product['financial_performance']
            sp = product['sales_performance']
            inv = product['inventory_status']
            
            row = [
                product['product_name'],
                product['category'],
                fp['total_revenue'],
                fp['total_cost'],
                fp['gross_profit'],
                f"{fp['profit_margin_percent']}%",
                sp['quantity_sold'],
                sp['average_selling_price'],
                fp['profit_per_unit'],
                inv['current_stock']
            ]
            data_rows.append(row)
        
        exporter.add_data_rows(data_rows)
        
        filename = f"product_profitability_{start_date}_to_{end_date}.xlsx"
        return exporter.get_response(filename)
    
    def _export_inventory_aging_excel(self, data, summary, threshold):
        """Export inventory aging data to Excel."""
        title = f"Inventory Aging Analysis - Threshold {threshold} days"
        exporter = ExcelExporter(title=title)
        
        exporter.add_title(title, f"Generated on {timezone.now().strftime('%Y-%m-%d %H:%M')}")
        
        # Add summary
        exporter.add_metadata(summary)
        
        # Add headers
        headers = [
            'Vessel', 'Product', 'Category', 'Purchase Date', 'Days in Stock',
            'Age Category', 'Quantity', 'Unit Cost', 'Lot Value', 'Risk Level', 'Recommendation'
        ]
        exporter.add_headers(headers)
        
        # Add data rows
        data_rows = []
        for lot in data:
            row = [
                lot['vessel_name'],
                lot['product_name'],
                lot['category'],
                lot['purchase_date'],
                lot['days_in_stock'],
                lot['age_category'],
                lot['remaining_quantity'],
                lot['unit_cost'],
                lot['lot_value'],
                lot['risk_level'],
                lot['recommendation']
            ]
            data_rows.append(row)
        
        exporter.add_data_rows(data_rows)
        
        filename = f"inventory_aging_{timezone.now().strftime('%Y%m%d')}.xlsx"
        return exporter.get_response(filename)