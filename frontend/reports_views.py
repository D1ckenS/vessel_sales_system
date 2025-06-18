from collections import defaultdict
from django.utils import timezone
from django.db import models
from datetime import datetime, timedelta, date
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
import calendar
import hashlib
from django.db.models import Avg, Sum, Count, F, Q, Case, When, Prefetch

from frontend.utils.cache_helpers import VesselCacheHelper
from .utils.aggregators import TransactionAggregator, ProductAnalytics
from transactions.models import Transaction, InventoryLot, Trip, PurchaseOrder, get_vessel_pricing_warnings
from django.shortcuts import render
from vessels.models import Vessel
from products.models import Product
from .utils.query_helpers import TransactionQueryHelper, DateRangeHelper
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
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
        Prefetch(
            'sales_transactions',
            queryset=Transaction.objects.select_related('product', 'product__category')
        )
    )
    
    # Apply all filters using helper with custom field mappings
    trips = TransactionQueryHelper.apply_common_filters(
        trips, request,
        date_field='trip_date',           # Trips use trip_date not transaction_date
        status_field='is_completed'       # Enable status filtering for trips
    )
    
    trips = trips.order_by('-trip_date', '-created_at')
    
    # Force single evaluation and store result
    trips_list = list(trips)  # Single evaluation with all JOINs
    trip_ids = [trip.id for trip in trips_list]
    
    # WORKING: Calculate summary statistics using direct database aggregation
    # Get all sales transactions for the filtered trips in ONE query
    sales_transactions = Transaction.objects.filter(
        trip_id__in=trip_ids,
        transaction_type='SALE'
    ).aggregate(
        total_revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        total_sales_count=Count('id'),
        avg_transaction_value=Avg(F('unit_price') * F('quantity'), output_field=models.DecimalField())
    )
    
    # WORKING: Calculate trip-level statistics
    trip_stats = {
        'total_trips': len(trips_list),
        'total_passengers': sum(trip.passenger_count or 0 for trip in trips_list),
        'completed_trips': sum(1 for trip in trips_list if trip.is_completed),
        'in_progress_trips': sum(1 for trip in trips_list if not trip.is_completed),
    }
    
    # WORKING: Calculate additional metrics safely
    total_revenue = sales_transactions['total_revenue'] or 0
    total_trips = trip_stats['total_trips'] or 0
    total_passengers = trip_stats['total_passengers'] or 0
    total_sales_count = sales_transactions['total_sales_count'] or 0
    
    avg_revenue_per_trip = total_revenue / total_trips if total_trips > 0 else 0
    avg_revenue_per_passenger = total_revenue / total_passengers if total_passengers > 0 else 0
        
    # WORKING: Get top performing trips using direct aggregation
    top_trips = trips.annotate(
        trip_revenue=Sum(F('sales_transactions__unit_price') * F('sales_transactions__quantity'))
    ).filter(trip_revenue__gt=0).order_by('-trip_revenue')[:5]
    
    context = {
        'trips': trips_list,
        'top_trips': top_trips,
        'vessels': VesselCacheHelper.get_active_vessels(),
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
    context['current_filters'] = {
        'vessel': request.GET.get('vessel', ''),
        'date_from': request.GET.get('date_from', ''),
        'date_to': request.GET.get('date_to', ''),
        'status': request.GET.get('status', ''),
    }
    
    return render(request, 'frontend/trip_reports.html', context)

@reports_access_required
def po_reports(request):
    """Purchase Order reports"""
    
    # Base queryset
    purchase_orders = PurchaseOrder.objects.select_related(
        'vessel', 'created_by'        
    ).prefetch_related(
        Prefetch(
            'supply_transactions',
            queryset=Transaction.objects.select_related('product', 'product__category')
        )
    ).annotate(
        # Your existing annotations...
        annotated_total_cost=Sum(
            F('supply_transactions__unit_price') * F('supply_transactions__quantity'),
            output_field=models.DecimalField()
        ),
        annotated_transaction_count=Count('supply_transactions'),
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
    """Enhanced transaction list with advanced filtering and pagination"""
    
    # ✅ STEP 1: Single optimized query with all relationships
    transactions = Transaction.objects.select_related(
        'vessel',                    # ✅ Eliminates vessel lookups
        'product',                   # ✅ Eliminates product lookups
        'product__category',         # ✅ Eliminates category lookups  
        'created_by',                # ✅ Eliminates user lookups
        'trip',                      # ✅ Eliminates trip lookups
        'purchase_order'             # ✅ Eliminates PO lookups
    ).prefetch_related(
        'trip__vessel',              # ✅ For trip vessel info
        'purchase_order__vessel'     # ✅ For PO vessel info  
    )
    
    # ✅ STEP 2: Apply filters using helper (your existing code)
    transactions = TransactionQueryHelper.apply_common_filters(transactions, request)
    
    # ✅ STEP 3: Order results (your existing code)
    transactions = transactions.order_by('-transaction_date', '-created_at')
    
    # ✅ STEP 4: Pagination with count optimization
    paginator = Paginator(transactions, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # ✅ STEP 5: Calculate summary stats ONCE (not per transaction type)
    if page_obj.object_list:
        # Get stats for current page only to avoid expensive full table scan
        page_transactions = list(page_obj.object_list)
        
        summary_stats = {
            'total_displayed': len(page_transactions),
            'page_number': page_obj.number,
            'total_pages': page_obj.paginator.num_pages,
        }
        
        # Optional: Add type breakdown for current page only
        type_counts = {}
        for tx in page_transactions:
            tx_type = tx.transaction_type
            type_counts[tx_type] = type_counts.get(tx_type, 0) + 1
            
        summary_stats['type_breakdown'] = type_counts
    else:
        summary_stats = {
            'total_displayed': 0,
            'page_number': 1,
            'total_pages': 1,
            'type_breakdown': {}
        }
    
    # ✅ STEP 6: Context (your existing structure)
    context = {
        'page_obj': page_obj,
        'transactions': page_obj.object_list,  # For template compatibility
        'summary_stats': summary_stats,
        'current_filters': {
            'vessel': request.GET.get('vessel', ''),
            'product': request.GET.get('product', ''),
            'transaction_type': request.GET.get('transaction_type', ''),
            'date_from': request.GET.get('date_from', ''),
            'date_to': request.GET.get('date_to', ''),
        }
    }
    
    return render(request, 'frontend/transactions_list.html', context)

@reports_access_required
def reports_dashboard(request):
    """CORRECTED: Reports hub with caching and correct field names"""
    
    today = timezone.now().date()
    cache_key = f'reports_dashboard_{today}'
    
    # Cache for 30 minutes
    cached_data = cache.get(cache_key)
    if cached_data:
        cached_data['last_updated'] = timezone.now()
        return render(request, 'frontend/reports_dashboard.html', cached_data)
    
    # Get today's stats using EXACT method that exists
    today_stats = TransactionAggregator.get_today_activity_summary()
    
    # Get today's other metrics
    today_trips = Trip.objects.filter(trip_date=today).count()
    today_pos = PurchaseOrder.objects.filter(po_date=today).count()
    
    context = {
        'today_stats': {
            'revenue': today_stats['today_revenue'] or 0,
            'cost': today_stats['today_supplies'] or 0,  # FIXED: Correct field name
            'profit': (today_stats['today_revenue'] or 0) - (today_stats['today_supplies'] or 0),
            'transactions': today_stats['today_transactions'] or 0,
            'trips': today_trips,
            'purchase_orders': today_pos,
            'sales_count': today_stats['today_sales_count'] or 0,
            'supply_count': today_stats['today_supply_count'] or 0,
        },
        'last_updated': timezone.now(),
    }
    
    # Cache for 30 minutes
    cache.set(cache_key, context, 1800)
    
    return render(request, 'frontend/reports_dashboard.html', context)

@reports_access_required
def comprehensive_report(request):
    """CORRECTED: Comprehensive transaction report with proper caching"""
    
    # Create cache key based on filters
    filter_params = {
        'transaction_type': request.GET.get('transaction_type', ''),
        'vessel': request.GET.get('vessel', ''),
        'product': request.GET.get('product', ''),
        'date_from': request.GET.get('date_from', ''),
        'date_to': request.GET.get('date_to', ''),
        'status': request.GET.get('status', ''),
        'min_amount': request.GET.get('min_amount', ''),
        'max_amount': request.GET.get('max_amount', ''),
    }
    
    # Create a hash of filter parameters for cache key
    filter_string = '|'.join(f"{k}:{v}" for k, v in filter_params.items() if v)
    filter_hash = hashlib.md5(filter_string.encode()).hexdigest()[:12]
    
    today = timezone.now().date()
    cache_key = f'comprehensive_report_{today}_{filter_hash}'
    
    # Cache duration based on whether querying current data
    date_to = request.GET.get('date_to')
    if not date_to or (date_to and datetime.strptime(date_to, '%Y-%m-%d').date() >= today):
        cache_duration = 1800  # 30 minutes for current data
    else:
        cache_duration = 7200  # 2 hours for historical data
    
    # Try cache first
    cached_data = cache.get(cache_key)
    if cached_data:
        return render(request, 'frontend/comprehensive_report.html', cached_data)
    
    # Base queryset - all transactions
    transactions = Transaction.objects.select_related(
        'vessel', 'product', 'created_by', 'trip', 'purchase_order'
    ).order_by('-transaction_date', '-created_at')
    
    # Apply all common filters using EXACT existing helper
    transactions = TransactionQueryHelper.apply_common_filters(transactions, request)
    
    # Use EXACT existing helper methods
    summary_stats = TransactionAggregator.get_enhanced_summary_stats(transactions)
    type_breakdown = TransactionAggregator.get_type_breakdown(transactions)
    vessel_breakdown = TransactionAggregator.get_vessel_breakdown(transactions)
    product_breakdown = TransactionAggregator.get_product_breakdown(transactions, limit=10)
    
    # Check for pricing warnings (keep your exact pattern)
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
    
    # Get date range info using EXACT existing helper
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
        'summary_stats': summary_stats,
        'type_breakdown': type_breakdown,
        'vessel_breakdown': vessel_breakdown,
        'product_breakdown': product_breakdown,
        'date_range_info': date_range_info,
        'total_shown': min(transactions.count(), 200),
        'total_available': transactions.count(),
    }
    
    # Add filter context using EXACT existing helper
    context.update(TransactionQueryHelper.get_filter_context(request))
    
    # Cache the results
    cache.set(cache_key, context, cache_duration)
    
    return render(request, 'frontend/comprehensive_report.html', context)

@reports_access_required
def daily_report(request):
    from django.db.models import OuterRef, Subquery
    from collections import defaultdict

    # Parse selected date
    selected_date_str = request.GET.get('date')
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date() if selected_date_str else timezone.now().date()
    except ValueError:
        selected_date = timezone.now().date()
    
    today = timezone.now().date()
    cache_key = f'daily_report_{selected_date}'
    cache_duration = 3600 if selected_date == today else 86400

    if cached := cache.get(cache_key):
        return render(request, 'frontend/daily_report.html', cached)

    previous_date = selected_date - timedelta(days=1)

    # === Transactions ===
    transactions_qs = Transaction.objects.select_related(
        'vessel', 'product', 'product__category', 'created_by'
    )

    daily_transactions = transactions_qs.filter(transaction_date=selected_date).order_by('-created_at')
    previous_transactions = transactions_qs.filter(transaction_date=previous_date).order_by('-created_at')

    comparison = TransactionAggregator.compare_periods(daily_transactions, previous_transactions)
    stats = comparison['current']
    revenue_change = comparison['changes']['revenue_change_percent']
    transaction_change = comparison['changes']['transaction_change_count']

    # === Vessels & Vessel Breakdown ===
    vessels = VesselCacheHelper.get_active_vessels()
    
    # Prefetch all transactions in one go
    vessel_transactions = Transaction.objects.filter(
        transaction_date=selected_date,
        vessel__in=vessels
    ).select_related('vessel', 'product', 'product__category', 'created_by')

    # Now pass the full batch to the modified aggregator
    vessel_breakdown = TransactionAggregator.get_vessel_stats_for_date(vessel_transactions, vessels)


    # === Grouped Trips & POs by vessel ===
    trips_by_vessel = defaultdict(list)
    for trip in Trip.objects.filter(trip_date=selected_date).values(
        'vessel_id', 'trip_number', 'is_completed', 'passenger_count'
    ):
        trips_by_vessel[trip['vessel_id']].append(trip)

    pos_by_vessel = defaultdict(list)
    for po in PurchaseOrder.objects.filter(po_date=selected_date).values(
        'vessel_id', 'po_number', 'is_completed'
    ):
        pos_by_vessel[po['vessel_id']].append(po)

    for v in vessel_breakdown:
        v_id = v['vessel'].id
        v['trips'] = trips_by_vessel.get(v_id, [])
        v['pos'] = pos_by_vessel.get(v_id, [])

    # === Inventory changes ===
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
    ).filter(Q(total_in__gt=0) | Q(total_out__gt=0)).order_by('-total_out')[:20]

    # === Stock levels: One query to rule them all ===
    stock_subquery = InventoryLot.objects.filter(
        product=OuterRef('pk'),
        remaining_quantity__gte=0
    ).values('product').annotate(
        total_stock=Sum('remaining_quantity')
    ).values('total_stock')

    products = Product.objects.filter(active=True).annotate(
        total_stock=Subquery(stock_subquery)
    )

    low_stock_products = []
    out_of_stock_products = []

    for product in products:
        stock = product.total_stock or 0
        if stock == 0:
            out_of_stock_products.append({'product': product, 'total_stock': 0})
        elif stock < 10:
            low_stock_products.append({'product': product, 'total_stock': stock})

    # === Best vessel & activity highlights ===
    best_vessel = max(vessel_breakdown, key=lambda v: v.get('profit') or 0, default=None)
    most_active_vessel = max(
        vessel_breakdown, key=lambda v: v.get('stats', {}).get('total_quantity') or 0, default=None
    )

    # === Values-only queries for reports ===
    daily_trips = Trip.objects.filter(trip_date=selected_date).values(
        'trip_number', 'is_completed', 'passenger_count', 'vessel__name'
    )
    daily_pos = PurchaseOrder.objects.filter(po_date=selected_date).values(
        'po_number', 'is_completed', 'vessel__name'
    )

    context = {
        'selected_date': selected_date,
        'previous_date': previous_date,
        'daily_stats': stats,
        'daily_profit': stats['total_profit'],
        'profit_margin': stats['profit_margin'],
        'revenue_change': revenue_change,
        'transaction_change': transaction_change,
        'vessel_breakdown': vessel_breakdown,
        'inventory_changes': inventory_changes,
        'best_vessel': best_vessel,
        'most_active_vessel': most_active_vessel,
        'low_stock_products': low_stock_products[:10],
        'out_of_stock_products': out_of_stock_products[:10],
        'daily_trips': daily_trips,
        'daily_pos': daily_pos,
        'vessels': vessels,
    }

    cache.set(cache_key, context, cache_duration)
    return render(request, 'frontend/daily_report.html', context)

@reports_access_required
def monthly_report(request):
    """CORRECTED: Monthly operations report with SQLite-compatible queries"""
    
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
    
    # Cache key for this specific month/year
    cache_key = f'monthly_report_{year}_{month}'
    
    # Cache duration: 2 hours for current month, 24 hours for historical
    current_month = today.month
    current_year = today.year
    cache_duration = 7200 if (month == current_month and year == current_year) else 86400
    
    # Try cache first
    cached_data = cache.get(cache_key)
    if cached_data:
        return render(request, 'frontend/monthly_report.html', cached_data)
    
    # Generate year range and months
    SYSTEM_START_YEAR = 2023
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
    
    # Use EXACT existing helper method
    comparison = TransactionAggregator.compare_periods(monthly_transactions, previous_transactions)
    monthly_stats = comparison['current']
    revenue_change = comparison['changes']['revenue_change_percent']
    
    # Calculate monthly profit using the exact fields that exist
    monthly_revenue = monthly_stats['total_revenue']
    monthly_costs = monthly_stats['total_cost'] 
    monthly_profit = monthly_revenue - monthly_costs
    
    # Daily breakdown - SQLite compatible approach
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
    
    # Vessel performance using existing pattern from your code
    vessels = VesselCacheHelper.get_active_vessels()
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
    
    # Get top products using existing helper
    top_products = ProductAnalytics.get_top_selling_products(monthly_transactions, limit=10)
    
    # Calculate 12-month trends (simplified to avoid complex date arithmetic)
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
        'monthly_profit': monthly_profit,
        'revenue_change': revenue_change,
        'daily_breakdown': daily_breakdown,
        'vessel_performance': vessel_performance,
        'top_products': top_products,
        'trend_months': trend_months,
        'year_range': year_range,
        'months': months,
        'profit_margin': profit_margin,
    }
    
    # Cache the results
    cache.set(cache_key, context, cache_duration)
    
    return render(request, 'frontend/monthly_report.html', context)

@reports_access_required
def analytics_report(request):
    """HEAVILY OPTIMIZED: Advanced business analytics and KPI dashboard"""
    
    today = timezone.now().date()
    
    # Date ranges for analysis
    last_30_days = today - timedelta(days=30)
    last_90_days = today - timedelta(days=90)
    last_year = today - timedelta(days=365)
    
    # === KEY PERFORMANCE INDICATORS ===
    
    # Revenue KPIs (last 30 days) - OPTIMIZED: Single query
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
    
    # === VESSEL ANALYTICS === (OPTIMIZED: Single query instead of loop)
    
    vessel_analytics_raw = Vessel.objects.filter(active=True).annotate(
        # Revenue and costs for last 30 days
        revenue=Sum(
            F('transactions__unit_price') * F('transactions__quantity'),
            filter=Q(
                transactions__transaction_type='SALE',
                transactions__transaction_date__gte=last_30_days
            ),
            output_field=models.DecimalField()
        ),
        costs=Sum(
            F('transactions__unit_price') * F('transactions__quantity'),
            filter=Q(
                transactions__transaction_type='SUPPLY', 
                transactions__transaction_date__gte=last_30_days
            ),
            output_field=models.DecimalField()
        ),
        sales_count=Count(
            'transactions',
            filter=Q(
                transactions__transaction_type='SALE',
                transactions__transaction_date__gte=last_30_days
            )
        ),
        trips_count=Count(
            'trips',
            filter=Q(trips__trip_date__gte=last_30_days)
        ),
        avg_sale_amount=Avg(
            F('transactions__unit_price') * F('transactions__quantity'),
            filter=Q(
                transactions__transaction_type='SALE',
                transactions__transaction_date__gte=last_30_days
            )
        )
    ).order_by('-revenue')
    
    # Convert to list and calculate derived fields
    vessel_analytics = []
    for vessel in vessel_analytics_raw:
        revenue = vessel.revenue or 0
        costs = vessel.costs or 0
        trips = vessel.trips_count or 0
        
        vessel_analytics.append({
            'vessel': vessel,
            'revenue': revenue,
            'costs': costs,
            'profit_margin': ((revenue - costs) / revenue * 100) if revenue > 0 else 0,
            'trips_count': trips,
            'revenue_per_trip': revenue / max(trips, 1),
            'avg_sale_amount': vessel.avg_sale_amount or 0,
            'sales_count': vessel.sales_count or 0,
        })
    
    # === PRODUCT ANALYTICS === (ALREADY OPTIMIZED: Single query)
    
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
    
    # === INVENTORY ANALYSIS === (OPTIMIZED: Single query instead of loop)
    
    inventory_analysis_raw = Product.objects.filter(active=True).annotate(
        # Current total stock
        total_stock=Sum(
            'inventory_lots__remaining_quantity',
            filter=Q(inventory_lots__remaining_quantity__gt=0)
        ),
        # Sales in last 30 days
        sales_30_days=Sum(
            'transactions__quantity',
            filter=Q(
                transactions__transaction_type='SALE',
                transactions__transaction_date__gte=last_30_days
            )
        )
    ).filter(
        # Only include products with stock or recent sales
        Q(total_stock__gt=0) | Q(sales_30_days__gt=0)
    ).order_by('-sales_30_days')[:20]
    
    # Convert to list and calculate turnover metrics
    inventory_analysis = []
    for product in inventory_analysis_raw:
        total_stock = product.total_stock or 0
        sales_30_days = product.sales_30_days or 0
        
        # Calculate turnover rate (monthly sales / current stock)
        turnover_rate = (sales_30_days / max(total_stock, 1)) * 100 if total_stock > 0 else 0
        
        # Days of stock remaining
        daily_avg_sales = sales_30_days / 30
        days_remaining = total_stock / max(daily_avg_sales, 0.1) if daily_avg_sales > 0 else 999
        
        inventory_analysis.append({
            'product': product,
            'total_stock': total_stock,
            'sales_30_days': sales_30_days,
            'turnover_rate': turnover_rate,
            'days_remaining': min(days_remaining, 999),  # Cap at 999 days
        })
    
    # Sort by turnover rate
    inventory_analysis.sort(key=lambda x: x['turnover_rate'], reverse=True)
    
    # === SEASONAL TRENDS === (OPTIMIZED: Single query with date truncation)
    
    # Get monthly revenue for last 12 months in single query
    monthly_trends_raw = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date__gte=today - timedelta(days=365)
    ).extra(
        select={
            'month': "CAST(strftime('%%m', transaction_date) AS INTEGER)",
            'year': "CAST(strftime('%%Y', transaction_date) AS INTEGER)"
        }
    ).values('month', 'year').annotate(
        revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
    ).order_by('year', 'month')
    
    # Convert to desired format and fill missing months
    monthly_trends = []
    trends_dict = {(int(item['year']), int(item['month'])): item['revenue'] for item in monthly_trends_raw}
    
    for i in range(11, -1, -1):
        trend_date = today - timedelta(days=i*30)
        month_key = (trend_date.year, trend_date.month)
        revenue = trends_dict.get(month_key, 0)
        
        monthly_trends.append({
            'month': calendar.month_name[trend_date.month],
            'year': trend_date.year,
            'revenue': revenue,
        })
    
    # === CUSTOMER ANALYTICS === (OPTIMIZED: Single query)
    
    passenger_analytics = Trip.objects.filter(
        trip_date__gte=last_90_days,
        is_completed=True
    ).aggregate(
        total_passengers=Sum('passenger_count'),
        avg_passengers_per_trip=Avg('passenger_count'),
        total_trips=Count('id')
    )
    
    # Revenue per passenger - reuse existing calculation
    total_revenue_90_days = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date__gte=last_90_days
    ).aggregate(revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()))['revenue'] or 0
    
    revenue_per_passenger = total_revenue_90_days / max(passenger_analytics['total_passengers'] or 1, 1)
    
    # === BUSINESS INSIGHTS === (OPTIMIZED: Combined queries)
    
    # Growth rate calculation - combine this month and last month in single query
    this_month_start = date(today.year, today.month, 1)
    if today.month == 1:
        last_month_start = date(today.year - 1, 12, 1)
        last_month_end = date(today.year, 1, 1) - timedelta(days=1)
    else:
        last_month_start = date(today.year, today.month - 1, 1)
        last_month_end = date(today.year, today.month, 1) - timedelta(days=1)
    
    # Single query for both months
    monthly_comparison = Transaction.objects.filter(
        transaction_type='SALE'
    ).aggregate(
        this_month_revenue=Sum(
            F('unit_price') * F('quantity'),
            filter=Q(transaction_date__gte=this_month_start),
            output_field=models.DecimalField()
        ),
        last_month_revenue=Sum(
            F('unit_price') * F('quantity'),
            filter=Q(
                transaction_date__gte=last_month_start,
                transaction_date__lte=last_month_end
            ),
            output_field=models.DecimalField()
        )
    )
    
    this_month_revenue = monthly_comparison['this_month_revenue'] or 0
    last_month_revenue = monthly_comparison['last_month_revenue'] or 0
    
    growth_rate = ((this_month_revenue - last_month_revenue) / max(last_month_revenue, 1) * 100) if last_month_revenue > 0 else 0
    
    # Operational efficiency - reuse existing query
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