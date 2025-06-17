from django.utils import timezone
from django.db import models
from datetime import datetime, timedelta, date
from django.contrib.auth.decorators import login_required
import calendar
from django.db.models import Avg, Sum, Count, F, Q, Case, When
from .utils.aggregators import TransactionAggregator, ProductAnalytics
from transactions.models import Transaction, InventoryLot, Trip, PurchaseOrder, get_vessel_pricing_warnings
from django.shortcuts import render
from vessels.models import Vessel
from products.models import Product
from .utils.query_helpers import TransactionQueryHelper, DateRangeHelper
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

@reports_access_required
def trip_reports(request):
    """COMPLETE WORKING: Trip-based sales reports with proper optimization"""
    
    # WORKING: Base queryset with proper relations - NO problematic annotations
    trips = Trip.objects.select_related(
        'vessel', 'created_by'
    ).prefetch_related(
        'sales_transactions__product'  # Prefetch for efficiency
    )
    
    # Apply all filters using helper with custom field mappings
    trips = TransactionQueryHelper.apply_common_filters(
        trips, request,
        date_field='trip_date',           # Trips use trip_date not transaction_date
        status_field='is_completed'       # Enable status filtering for trips
    )
    
    trips = trips.order_by('-trip_date', '-created_at')
    
    # WORKING: Calculate summary statistics using direct database aggregation
    # Get all sales transactions for the filtered trips in ONE query
    sales_transactions = Transaction.objects.filter(
        trip__in=trips,
        transaction_type='SALE'
    ).aggregate(
        total_revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        total_sales_count=Count('id'),
        avg_transaction_value=Avg(F('unit_price') * F('quantity'), output_field=models.DecimalField())
    )
    
    # WORKING: Calculate trip-level statistics
    trip_stats = trips.aggregate(
        total_trips=Count('id'),
        total_passengers=Sum('passenger_count'),
        completed_trips=Count('id', filter=Q(is_completed=True)),
        in_progress_trips=Count('id', filter=Q(is_completed=False))
    )
    
    # WORKING: Calculate additional metrics safely
    total_revenue = sales_transactions['total_revenue'] or 0
    total_trips = trip_stats['total_trips'] or 0
    total_passengers = trip_stats['total_passengers'] or 0
    total_sales_count = sales_transactions['total_sales_count'] or 0
    
    avg_revenue_per_trip = total_revenue / total_trips if total_trips > 0 else 0
    avg_revenue_per_passenger = total_revenue / total_passengers if total_passengers > 0 else 0
        
    # WORKING: Get top performing trips using direct aggregation
    top_trips = Trip.objects.filter(
        id__in=trips.values_list('id', flat=True)
    ).annotate(
        trip_revenue=Sum(
            F('sales_transactions__unit_price') * F('sales_transactions__quantity'),
            filter=Q(sales_transactions__transaction_type='SALE'),
            output_field=models.DecimalField()
        ),
        trip_sales_count=Count('sales_transactions', filter=Q(sales_transactions__transaction_type='SALE'))
    ).filter(trip_revenue__gt=0).order_by('-trip_revenue')[:5]
    
    context = {
        'trips': trips,
        'top_trips': top_trips,
        'summary': {
            'total_trips': total_trips,
            'total_revenue': total_revenue,
            'total_passengers': total_passengers,
            'total_sales_transactions': total_sales_count,
            'completed_trips': trip_stats['completed_trips'] or 0,
            'in_progress_trips': trip_stats['in_progress_trips'] or 0,
            'avg_revenue_per_trip': avg_revenue_per_trip,
            'avg_revenue_per_passenger': avg_revenue_per_passenger,
            'avg_transaction_value': sales_transactions['avg_transaction_value'] or 0,
        }
    }
    
    # Add filter context and vessels using helper
    context.update(TransactionQueryHelper.get_filter_context(request))
    
    return render(request, 'frontend/trip_reports.html', context)

@reports_access_required
def po_reports(request):
    """Purchase Order reports"""
    
    # Base queryset
    purchase_orders = PurchaseOrder.objects.select_related(
        'vessel', 'created_by'
    ).prefetch_related(
        'supply_transactions'
    )
    
    purchase_orders = TransactionQueryHelper.apply_common_filters(
        purchase_orders, request,
        date_field='po_date',
        status_field='is_completed'
    )
    
    purchase_orders = purchase_orders.order_by('-po_date', '-created_at')
    
    # Calculate summary statistics
    total_pos = purchase_orders.count()
    total_cost = sum(po.total_cost for po in purchase_orders)
    avg_cost_per_po = total_cost / total_pos if total_pos > 0 else 0
    
    
    context = {
        'purchase_orders': purchase_orders,
        'summary': {
            'total_pos': total_pos,
            'total_cost': total_cost,
            'avg_cost_per_po': avg_cost_per_po,
        }
    }
    
    # Add filter context and vessels using helper
    context.update(TransactionQueryHelper.get_filter_context(request))
    
    return render(request, 'frontend/po_reports.html', context)

@reports_access_required
def transactions_list(request):
    """OPTIMIZED: Frontend transactions list with enhanced template performance"""
    
    # Base queryset and filtering
    transactions = Transaction.objects.select_related(
        'vessel', 'product', 'product__category', 'created_by',
        'trip', 'purchase_order', 'transfer_to_vessel', 'transfer_from_vessel'
    ).order_by('-transaction_date', '-created_at')
    
    # Apply all common filters using helper
    transactions = TransactionQueryHelper.apply_common_filters(transactions, request)
    
    # OPTIMIZED: Pagination-ready limiting with total count
    total_count = transactions.count()
    page_size = 200
    transactions_limited = transactions[:page_size]
    
     # ALL AGGREGATIONS WITH 4 LINES (instead of 70+ lines)
    summary_stats = TransactionAggregator.get_enhanced_summary_stats(transactions)
    type_breakdown = TransactionAggregator.get_type_breakdown(transactions)
    vessel_activity = TransactionAggregator.get_vessel_breakdown(transactions, limit=5)
    recent_activity = TransactionAggregator.get_today_activity_summary()
    
    # OPTIMIZED: Build enhanced context
    context = {
        'transactions': transactions_limited,
        'transaction_types': Transaction.TRANSACTION_TYPES,
        'summary_stats': {
            # Use enhanced stats with automatic profit calculations and safe defaults
            **summary_stats,
            'showing_count': len(transactions_limited),
            'total_count': total_count,
            'is_filtered': bool(request.GET.get('transaction_type') or request.GET.get('vessel') or 
                               request.GET.get('date_from') or request.GET.get('date_to'))
        },
        'type_breakdown': type_breakdown,
        'vessel_activity': vessel_activity,
        'recent_activity': recent_activity,
        'pagination': {
            'page_size': page_size,
            'has_more': total_count > page_size,
            'showing': min(page_size, total_count),
            'total': total_count
        }
    }
    
    # Add filter context using helper
    context.update(TransactionQueryHelper.get_filter_context(request))
    
    return render(request, 'frontend/transactions_list.html', context)

@reports_access_required
def reports_dashboard(request):
    """Reports hub with statistics and report options"""
    
    # GET TODAY'S SUMMARY WITH 1 LINE (instead of 25+ lines)
    today_stats = TransactionAggregator.get_today_activity_summary()
    
    # Get today's other metrics
    today = timezone.now().date()
    today_trips = Trip.objects.filter(trip_date=today).count()
    today_pos = PurchaseOrder.objects.filter(po_date=today).count()
    
    context = {
        'today_stats': {
            'revenue': today_stats['today_revenue'] or 0,
            'cost': today_stats['today_supplies'] or 0,
            'transactions': today_stats['today_transactions'] or 0,
            'trips': today_trips,
            'purchase_orders': today_pos,
            'sales_count': today_stats['today_sales_count'] or 0,
            'supply_count': today_stats['today_supply_count'] or 0,
        }
    }
    
    return render(request, 'frontend/reports_dashboard.html', context)

@reports_access_required
def comprehensive_report(request):
    """Comprehensive transaction report - all transaction types with filtering"""
    
    # Base queryset - all transactions
    transactions = Transaction.objects.select_related(
        'vessel', 'product', 'created_by', 'trip', 'purchase_order'
    ).order_by('-transaction_date', '-created_at')
    
    # Apply all common filters in one line
    transactions = TransactionQueryHelper.apply_common_filters(transactions, request)
    
    # ALL AGGREGATIONS WITH 4 LINES (instead of 50+ lines)
    summary_stats = TransactionAggregator.get_enhanced_summary_stats(transactions)
    type_breakdown = TransactionAggregator.get_type_breakdown(transactions)
    vessel_breakdown = TransactionAggregator.get_vessel_breakdown(transactions)
    product_breakdown = TransactionAggregator.get_product_breakdown(transactions, limit=10)
    
    # Check for pricing warnings in transactions
    pricing_warnings_count = 0
    vessel_filter = request.GET.get('vessel')
    if vessel_filter:
        try:
            filtered_vessel = Vessel.objects.get(id=vessel_filter)
            if not filtered_vessel.has_duty_free:
                vessel_warnings = get_vessel_pricing_warnings(filtered_vessel)
                if vessel_warnings['has_warnings']:
                    pricing_warnings_count = vessel_warnings['missing_price_count']
        except Vessel.DoesNotExist:
            pass
    
    # Get date range info using helper
    date_range_info = DateRangeHelper.get_date_range_info(request)
    
    # Limit transactions for display performance
    transactions_limited = transactions[:200]
    
    context = {
        'transactions': transactions_limited,
        'transaction_types': Transaction.TRANSACTION_TYPES,
        'pricing_warnings': {
            'has_warnings': pricing_warnings_count > 0,
            'missing_prices_count': pricing_warnings_count,
            'message': f"⚠️ {pricing_warnings_count} products missing custom pricing" if pricing_warnings_count > 0 else None
        },
        'summary_stats': summary_stats,  # Enhanced with profit calculations
        'type_breakdown': type_breakdown,  # Includes percentages
        'vessel_breakdown': vessel_breakdown,  # Includes revenue/cost breakdown  
        'product_breakdown': product_breakdown,  # Enhanced analytics
        'date_range_info': date_range_info,
        'total_shown': min(transactions.count(), 200),
        'total_available': transactions.count(),
    }
    
    # Add filter context and vessels using helper
    context.update(TransactionQueryHelper.get_filter_context(request))
    
    return render(request, 'frontend/comprehensive_report.html', context)

@reports_access_required
def daily_report(request):
    """Comprehensive daily operations report for a specific date"""
    
    today = timezone.now().date()
    
    # Get selected date (default to today)
    selected_date_str = request.GET.get('date')
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()
    
    # Get previous day for comparison
    previous_date = selected_date - timedelta(days=1)
    
    # Daily transactions for selected date
    daily_transactions = Transaction.objects.filter(transaction_date=selected_date)
    previous_transactions = Transaction.objects.filter(transaction_date=previous_date)
    
    # GET ALL DAILY ANALYTICS WITH 2 LINES (instead of 50+ lines)
    comparison = TransactionAggregator.compare_periods(daily_transactions, previous_transactions)
    daily_stats = comparison['current']
    revenue_change = comparison['changes']['revenue_change_percent']
    transaction_change = comparison['changes']['transaction_change_count']
    
    # Get vessels using helper
    vessels = TransactionQueryHelper.get_vessels_for_filter()
    
    # GET VESSEL BREAKDOWN WITH 1 LINE (instead of 25+ lines per vessel)
    vessel_breakdown = TransactionAggregator.get_vessel_stats_for_date(daily_transactions, vessels)
    
    # Add trip and PO data to vessel breakdown
    for vessel_data in vessel_breakdown:
        vessel = vessel_data['vessel']
        
        # Get trips for this vessel on this date
        vessel_trips = Trip.objects.filter(
            vessel=vessel,
            trip_date=selected_date
        ).values('trip_number', 'is_completed', 'passenger_count')
        
        # Get POs for this vessel on this date
        vessel_pos = PurchaseOrder.objects.filter(
            vessel=vessel,
            po_date=selected_date
        ).values('po_number', 'is_completed')
        
        vessel_data.update({
            'trips': list(vessel_trips),
            'pos': list(vessel_pos)
        })
    
    # === INVENTORY CHANGES ===
    inventory_changes = daily_transactions.values(
        'product__name', 'product__item_id', 'vessel__name', 'vessel__name_ar'
    ).annotate(
        total_in=Sum('quantity', filter=Q(transaction_type__in=['SUPPLY', 'TRANSFER_IN'])),
        total_out=Sum('quantity', filter=Q(transaction_type__in=['SALE', 'TRANSFER_OUT'])),
        net_change=Sum(
            Case(
                When(transaction_type__in=['SUPPLY', 'TRANSFER_IN'], then=F('quantity')),
                When(transaction_type__in=['SALE', 'TRANSFER_OUT'], then=-F('quantity')),
                default=0,
                output_field=models.DecimalField(max_digits=15, decimal_places=3)
            )
        )
    ).filter(
        Q(total_in__gt=0) | Q(total_out__gt=0)
    ).order_by('-total_out')[:20]
    
    # === BUSINESS INSIGHTS ===
    best_vessel = max(vessel_breakdown, key=lambda v: v['stats']['revenue'] or 0) if vessel_breakdown else None
    most_active_vessel = max(vessel_breakdown, key=lambda v: (v['stats']['sales_count'] or 0) + (v['stats']['supply_count'] or 0)) if vessel_breakdown else None
    
    # Low stock alerts
    low_stock_products = []
    out_of_stock_products = []

    for product in Product.objects.filter(active=True):
        total_stock = InventoryLot.objects.filter(
            product=product,
            remaining_quantity__gt=0
        ).aggregate(total=Sum('remaining_quantity'))['total'] or 0
        
        if total_stock == 0:
            out_of_stock_products.append({'product': product, 'total_stock': total_stock})
        elif total_stock < 10:
            low_stock_products.append({'product': product, 'total_stock': total_stock})
    
    # All trips and POs for the day
    daily_trips = Trip.objects.filter(trip_date=selected_date).select_related('vessel').order_by('vessel__name', 'trip_number')
    daily_pos = PurchaseOrder.objects.filter(po_date=selected_date).select_related('vessel').order_by('vessel__name', 'po_number')
    
    context = {
        'selected_date': selected_date,
        'previous_date': previous_date,
        'daily_stats': daily_stats,  # Enhanced with all metrics
        'daily_profit': daily_stats['total_profit'],
        'profit_margin': daily_stats['profit_margin'],
        'revenue_change': revenue_change,
        'transaction_change': transaction_change,
        'vessel_breakdown': vessel_breakdown,  # Enhanced with profit margins
        'inventory_changes': inventory_changes,
        'best_vessel': best_vessel,
        'most_active_vessel': most_active_vessel,
        'low_stock_products': low_stock_products[:10],
        'out_of_stock_products': out_of_stock_products[:10],
        'daily_trips': daily_trips,
        'daily_pos': daily_pos,
        'vessels': vessels,
    }
    
    return render(request, 'frontend/daily_report.html', context)

@reports_access_required
def monthly_report(request):
    """Comprehensive monthly operations and financial report"""
    
    # Get selected month/year (default to current month)
    selected_month = request.GET.get('month')
    selected_year = request.GET.get('year')
    
    today = timezone.now().date()
    
    if selected_month and selected_year:
        try:
            month = int(selected_month)
            year = int(selected_year)
        except ValueError:
            month = today.month
            year = today.year
    else:
        month = today.month
        year = today.year
    
    # Generate year range and months
    SYSTEM_START_YEAR = 2023
    current_year = timezone.now().year
    year_range = range(SYSTEM_START_YEAR, current_year + 1)
    months = {i: calendar.month_name[i] for i in range(1, 13)}
    
    # Calculate month date range
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    
    # Previous month for comparison
    if month == 1:
        prev_month = 12
        prev_year = year - 1
    else:
        prev_month = month - 1
        prev_year = year
    
    prev_first_day = date(prev_year, prev_month, 1)
    if prev_month == 12:
        prev_last_day = date(prev_year + 1, 1, 1) - timedelta(days=1)
    else:
        prev_last_day = date(prev_year, prev_month + 1, 1) - timedelta(days=1)
    
    # Get monthly transactions
    monthly_transactions = Transaction.objects.filter(
        transaction_date__gte=first_day,
        transaction_date__lte=last_day
    )
    
    previous_transactions = Transaction.objects.filter(
        transaction_date__gte=prev_first_day,
        transaction_date__lte=prev_last_day
    )
    
    # GET MONTHLY COMPARISON WITH PROPER STRUCTURE
    comparison = TransactionAggregator.compare_periods(monthly_transactions, previous_transactions)
    monthly_stats = comparison['current']
    revenue_change = comparison['changes']['revenue_change_percent']
    
    # FIXED: Calculate monthly profit properly
    monthly_revenue = monthly_stats['total_revenue']
    monthly_costs = monthly_stats['total_cost'] 
    monthly_profit = monthly_revenue - monthly_costs
    
    # === DAILY BREAKDOWN ===
    daily_breakdown = []
    current_date = first_day
    while current_date <= last_day:
        daily_transactions = Transaction.objects.filter(transaction_date=current_date)
        daily_summary = TransactionAggregator.get_enhanced_summary_stats(daily_transactions)
        
        daily_breakdown.append({
            'date': current_date,
            'day_name': current_date.strftime('%A'),
            'revenue': daily_summary['total_revenue'],
            'costs': daily_summary['total_cost'],
            'profit': daily_summary['total_profit'],
            'transactions': daily_summary['total_transactions'],
            'sales': daily_summary['sales_count'],
            'supplies': daily_summary['supply_count'],
        })
        
        current_date += timedelta(days=1)
    
    # FIXED: GET VESSEL PERFORMANCE WITH TRIPS/POS DATA
    vessels = Vessel.objects.filter(active=True)
    vessel_performance = []
    
    for vessel in vessels:
        vessel_transactions = monthly_transactions.filter(vessel=vessel)
        vessel_stats = TransactionAggregator.get_enhanced_summary_stats(vessel_transactions)
        
        # Get trip and PO counts for the month
        vessel_trips = Trip.objects.filter(
            vessel=vessel,
            trip_date__gte=first_day,
            trip_date__lte=last_day
        ).count()
        
        vessel_pos = PurchaseOrder.objects.filter(
            vessel=vessel,
            po_date__gte=first_day,
            po_date__lte=last_day
        ).count()
        
        # Only include vessels with activity
        if vessel_stats['total_revenue'] > 0 or vessel_stats['total_cost'] > 0 or vessel_trips > 0 or vessel_pos > 0:
            vessel_performance.append({
                'vessel': vessel,
                'revenue': vessel_stats['total_revenue'],
                'costs': vessel_stats['total_cost'],
                'profit': vessel_stats['total_profit'],
                'sales_count': vessel_stats['sales_count'],
                'supply_count': vessel_stats['supply_count'],
                'transfer_out_count': vessel_stats['transfer_out_count'],
                'transfer_in_count': vessel_stats['transfer_in_count'],
                'trips_count': vessel_trips,
                'pos_count': vessel_pos,
            })
    
    # Sort by revenue descending
    vessel_performance.sort(key=lambda x: x['revenue'], reverse=True)
    
    # GET TOP PRODUCTS
    top_products = ProductAnalytics.get_top_selling_products(monthly_transactions, limit=10)
    
    # === 12-MONTH TRENDS ===
    trend_months = []
    for i in range(11, -1, -1):  # 12 months including current
        trend_date = date(year, month, 1) - timedelta(days=i*30)  # Approximate
        trend_first = date(trend_date.year, trend_date.month, 1)
        
        if trend_date.month == 12:
            trend_last = date(trend_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            trend_last = date(trend_date.year, trend_date.month + 1, 1) - timedelta(days=1)
        
        trend_transactions = Transaction.objects.filter(
            transaction_date__gte=trend_first,
            transaction_date__lte=trend_last
        )
        
        trend_stats = TransactionAggregator.get_enhanced_summary_stats(trend_transactions)
        
        trend_months.append({
            'month': trend_date.strftime('%B'),
            'year': trend_date.year,
            'revenue': trend_stats['total_revenue'],
            'costs': trend_stats['total_cost'],
            'profit': trend_stats['total_profit'],
        })
    
    # Get month name
    month_name = calendar.month_name[month]
    profit_margin = (monthly_profit / monthly_revenue * 100) if monthly_revenue > 0 else 0
    
    context = {
        'selected_month': month,
        'selected_year': year,
        'month_name': month_name,
        'first_day': first_day,
        'last_day': last_day,
        'monthly_stats': monthly_stats,
        'monthly_profit': monthly_profit,  # FIXED: Explicit profit calculation
        'revenue_change': revenue_change,
        'daily_breakdown': daily_breakdown,
        'vessel_performance': vessel_performance,  # FIXED: Includes trips/POs
        'top_products': top_products,
        'trend_months': trend_months,
        'year_range': year_range,
        'months': months,
        'profit_margin': profit_margin,
    }
    
    return render(request, 'frontend/monthly_report.html', context)

@reports_access_required
def analytics_report(request):
    """Advanced business analytics and KPI dashboard"""

    
    today = timezone.now().date()
    
    # Date ranges for analysis
    last_30_days = today - timedelta(days=30)
    last_90_days = today - timedelta(days=90)
    last_year = today - timedelta(days=365)
    
    # === KEY PERFORMANCE INDICATORS ===
    
    # Revenue KPIs (last 30 days)
    revenue_30_days = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date__gte=last_30_days
    ).aggregate(
        total_revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        avg_daily_revenue=Avg(F('unit_price') * F('quantity')),
        transaction_count=Count('id')
    )
    
    # Average revenue per transaction
    avg_revenue_per_transaction = (revenue_30_days['total_revenue'] or 0) / max(revenue_30_days['transaction_count'] or 1, 1)
    
    # === VESSEL ANALYTICS ===
    
    vessel_analytics = []
    for vessel in Vessel.objects.filter(active=True):
        # Last 30 days performance
        vessel_transactions = Transaction.objects.filter(
            vessel=vessel,
            transaction_date__gte=last_30_days
        )
        
        vessel_stats = vessel_transactions.aggregate(
            revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
            costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
            sales_count=Count('id', filter=Q(transaction_type='SALE')),
            avg_sale_amount=Avg(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
        )
        
        # Calculate utilization (trips/total possible trips)
        vessel_trips = Trip.objects.filter(
            vessel=vessel,
            trip_date__gte=last_30_days
        ).count()
        
        # Efficiency: revenue per trip
        revenue_per_trip = (vessel_stats['revenue'] or 0) / max(vessel_trips, 1)
        
        # Profit margin
        vessel_revenue = vessel_stats['revenue'] or 0
        vessel_costs = vessel_stats['costs'] or 0
        profit_margin = ((vessel_revenue - vessel_costs) / vessel_revenue * 100) if vessel_revenue > 0 else 0
        
        vessel_analytics.append({
            'vessel': vessel,
            'revenue': vessel_revenue,
            'costs': vessel_costs,
            'profit_margin': profit_margin,
            'trips_count': vessel_trips,
            'revenue_per_trip': revenue_per_trip,
            'avg_sale_amount': vessel_stats['avg_sale_amount'] or 0,
            'sales_count': vessel_stats['sales_count'] or 0,
        })
    
    # === PRODUCT ANALYTICS ===
    
    # Best performing products (last 90 days)
    top_products = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date__gte=last_90_days
    ).values(
        'product__name', 'product__item_id', 'product__category__name'
    ).annotate(
        total_revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        total_quantity=Sum('quantity'),
        transaction_count=Count('id'),
        avg_price=Avg('unit_price'),
    ).order_by('-total_revenue')[:15]
    
    # Inventory turnover analysis
    inventory_analysis = []
    for product in Product.objects.filter(active=True)[:20]:  # Top 20 products
        # Total stock
        total_stock = InventoryLot.objects.filter(
            product=product,
            remaining_quantity__gt=0
        ).aggregate(total=Sum('remaining_quantity'))['total'] or 0
        
        # Sales in last 30 days
        sales_30_days = Transaction.objects.filter(
            product=product,
            transaction_type='SALE',
            transaction_date__gte=last_30_days
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        # Calculate turnover rate (monthly sales / current stock)
        turnover_rate = (sales_30_days / max(total_stock, 1)) * 100 if total_stock > 0 else 0
        
        # Days of stock remaining
        daily_avg_sales = sales_30_days / 30
        days_remaining = total_stock / max(daily_avg_sales, 0.1)
        
        inventory_analysis.append({
            'product': product,
            'total_stock': total_stock,
            'sales_30_days': sales_30_days,
            'turnover_rate': turnover_rate,
            'days_remaining': min(days_remaining, 999),  # Cap at 999 days
        })
    
    # Sort by turnover rate
    inventory_analysis.sort(key=lambda x: x['turnover_rate'], reverse=True)
    
    # === SEASONAL TRENDS ===
    
    # Monthly revenue for last 12 months
    monthly_trends = []
    for i in range(11, -1, -1):
        trend_date = today - timedelta(days=i*30)
        month_start = date(trend_date.year, trend_date.month, 1)
        
        if trend_date.month == 12:
            month_end = date(trend_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(trend_date.year, trend_date.month + 1, 1) - timedelta(days=1)
        
        monthly_revenue = Transaction.objects.filter(
            transaction_type='SALE',
            transaction_date__gte=month_start,
            transaction_date__lte=month_end
        ).aggregate(
            revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
        )['revenue'] or 0
        
        monthly_trends.append({
            'month': calendar.month_name[trend_date.month],
            'year': trend_date.year,
            'revenue': monthly_revenue,
        })
    
    # === CUSTOMER ANALYTICS ===
    
    # Trip-based passenger analytics
    passenger_analytics = Trip.objects.filter(
        trip_date__gte=last_90_days,
        is_completed=True
    ).aggregate(
        total_passengers=Sum('passenger_count'),
        avg_passengers_per_trip=Avg('passenger_count'),
        total_trips=Count('id')
    )
    
    # Revenue per passenger
    total_revenue_90_days = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date__gte=last_90_days
    ).aggregate(revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()))['revenue'] or 0
    
    revenue_per_passenger = total_revenue_90_days / max(passenger_analytics['total_passengers'] or 1, 1)
    
    # === BUSINESS INSIGHTS ===
    
    # Growth rate (this month vs last month)
    this_month_start = date(today.year, today.month, 1)
    if today.month == 1:
        last_month_start = date(today.year - 1, 12, 1)
        last_month_end = date(today.year, 1, 1) - timedelta(days=1)
    else:
        last_month_start = date(today.year, today.month - 1, 1)
        last_month_end = date(today.year, today.month, 1) - timedelta(days=1)
    
    this_month_revenue = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date__gte=this_month_start
    ).aggregate(revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()))['revenue'] or 0
    
    last_month_revenue = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date__gte=last_month_start,
        transaction_date__lte=last_month_end
    ).aggregate(revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()))['revenue'] or 0
    
    growth_rate = ((this_month_revenue - last_month_revenue) / max(last_month_revenue, 1) * 100) if last_month_revenue > 0 else 0
    
    # Operational efficiency
    total_transactions_30_days = Transaction.objects.filter(
        transaction_date__gte=last_30_days
    ).count()
    
    efficiency_score = (total_transactions_30_days / 30) * 10  # Arbitrary scoring
    
    context = {
        'revenue_30_days': revenue_30_days,
        'avg_revenue_per_transaction': avg_revenue_per_transaction,
        'vessel_analytics': vessel_analytics,
        'top_products': top_products,
        'inventory_analysis': inventory_analysis[:10],  # Top 10
        'monthly_trends': monthly_trends,
        'passenger_analytics': passenger_analytics,
        'revenue_per_passenger': revenue_per_passenger,
        'growth_rate': growth_rate,
        'efficiency_score': min(efficiency_score, 100),  # Cap at 100
        'last_30_days': last_30_days,
        'last_90_days': last_90_days,
        'today': today,
    }
    
    return render(request, 'frontend/analytics_report.html', context)