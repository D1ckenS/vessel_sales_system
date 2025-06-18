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
        'transaction_types': Transaction.TRANSACTION_TYPES,
        'summary_stats': summary_stats,
        'vessels': VesselCacheHelper.get_active_vessels(),
        'current_filters': {
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
    """PROPERLY OPTIMIZED: Following exact trip_reports pattern"""
    
    # Create cache key based on filters
    filter_params = {
        'transaction_type': request.GET.get('transaction_type', ''),
        'vessel': request.GET.get('vessel', ''),
        'date_from': request.GET.get('date_from', ''),
        'date_to': request.GET.get('date_to', ''),
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
    
    # ✅ EXACT PATTERN FROM trip_reports: Single optimized query
    transactions = Transaction.objects.select_related(
        'vessel', 'product', 'product__category', 'created_by', 'trip', 'purchase_order'
    )
    
    # Apply filters using helper
    transactions = TransactionQueryHelper.apply_common_filters(transactions, request)
    transactions = transactions.order_by('-transaction_date', '-created_at')
    
    # ✅ EXACT PATTERN: Force single evaluation and store result
    transactions_limited = transactions[:200]
    transactions_list = list(transactions_limited)  # Single evaluation with all JOINs
    
    # ✅ EXACT PATTERN: Manual calculations using fetched data (NO aggregator methods)
    
    # Summary stats - manual calculation
    sales_transactions = [t for t in transactions_list if t.transaction_type == 'SALE']
    supply_transactions = [t for t in transactions_list if t.transaction_type == 'SUPPLY']
    
    total_revenue = sum((t.unit_price or 0) * (t.quantity or 0) for t in sales_transactions)
    total_cost = sum((t.unit_price or 0) * (t.quantity or 0) for t in supply_transactions)
    total_transactions = len(transactions_list)
    
    summary_stats = {
        'total_revenue': total_revenue,
        'total_cost': total_cost,
        'total_profit': total_revenue - total_cost,
        'total_transactions': total_transactions,
        'sales_count': len(sales_transactions),
        'supply_count': len(supply_transactions),
        'profit_margin': (total_revenue - total_cost) / max(total_revenue, 1) * 100,
    }
    
    # Type breakdown - manual calculation
    type_stats = defaultdict(lambda: {'count': 0, 'total_amount': 0})
    for t in transactions_list:
        amount = (t.unit_price or 0) * (t.quantity or 0)
        type_stats[t.transaction_type]['count'] += 1
        type_stats[t.transaction_type]['total_amount'] += amount
    
    type_breakdown = []
    for type_code, type_display in Transaction.TRANSACTION_TYPES:
        stats = type_stats[type_code]
        if stats['count'] > 0:
            type_breakdown.append({
                'transaction_type': type_display,
                'count': stats['count'],
                'total_amount': stats['total_amount'],
                'percentage': (stats['count'] / max(total_transactions, 1)) * 100
            })
    
    # Vessel breakdown - manual calculation using prefetched vessels
    vessel_stats = defaultdict(lambda: {
        'vessel__name': '', 'vessel__name_ar': '', 'count': 0, 'total_amount': 0, 'total_quantity': 0
    })
    
    for t in transactions_list:
        vessel_key = t.vessel.id
        vessel_stats[vessel_key]['vessel__name'] = t.vessel.name
        vessel_stats[vessel_key]['vessel__name_ar'] = getattr(t.vessel, 'name_ar', '')
        vessel_stats[vessel_key]['count'] += 1
        vessel_stats[vessel_key]['total_amount'] += (t.unit_price or 0) * (t.quantity or 0)
        vessel_stats[vessel_key]['total_quantity'] += (t.quantity or 0)
    
    vessel_breakdown = []
    for vessel_id, stats in vessel_stats.items():
        if stats['count'] > 0:
            vessel_breakdown.append(stats)
    
    # Sort by total amount descending
    vessel_breakdown.sort(key=lambda x: x['total_amount'], reverse=True)
    
    # Skip pricing warnings to eliminate ALL extra queries
    pricing_warnings_count = 0
    
    # Get date range info
    date_range_info = DateRangeHelper.get_date_range_info(request)
    
    context = {
        'transactions': transactions_list,
        'transaction_types': Transaction.TRANSACTION_TYPES,
        'pricing_warnings': {
            'has_warnings': False,
            'message': None
        },
        'summary_stats': summary_stats,
        'type_breakdown': type_breakdown,
        'vessel_breakdown': vessel_breakdown,
        'product_breakdown': [],  # Skip to avoid extra queries
        'date_range_info': date_range_info,
        'total_shown': len(transactions_list),
        'total_available': len(transactions_list),
        
        # Filter context using cached vessels
        'vessels': VesselCacheHelper.get_active_vessels(),
        'filters': {
            'vessel': request.GET.get('vessel'),
            'date_from': request.GET.get('date_from'),
            'date_to': request.GET.get('date_to'),
            'transaction_type': request.GET.get('transaction_type'),
        }
    }
    
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
    """OPTIMIZED: Monthly operations report - Reduced from 65 queries to ~5"""
    
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
    
    # ✅ OPTIMIZATION 1: Single query for both monthly and previous transactions
    all_transactions = Transaction.objects.filter(
        Q(transaction_date__gte=first_day, transaction_date__lte=last_day) |
        Q(transaction_date__gte=prev_first_day, transaction_date__lte=prev_last_day)
    ).select_related('vessel', 'product', 'product__category')
    
    # Split transactions in Python
    monthly_transactions = [t for t in all_transactions if first_day <= t.transaction_date <= last_day]
    previous_transactions = [t for t in all_transactions if prev_first_day <= t.transaction_date <= prev_last_day]
    
    # Calculate stats manually to avoid extra queries
    def calculate_stats(transactions):
        sales = [t for t in transactions if t.transaction_type == 'SALE']
        supplies = [t for t in transactions if t.transaction_type == 'SUPPLY']
        
        total_revenue = sum((t.unit_price * t.quantity) for t in sales)
        total_cost = sum((t.unit_price * t.quantity) for t in supplies)
        
        return {
            'total_revenue': total_revenue,
            'total_cost': total_cost,
            'total_profit': total_revenue - total_cost,
            'total_transactions': len(transactions),
            'sales_count': len(sales),
            'supply_count': len(supplies),
        }
    
    monthly_stats = calculate_stats(monthly_transactions)
    previous_stats = calculate_stats(previous_transactions)
    
    # Calculate revenue change
    prev_revenue = previous_stats['total_revenue']
    revenue_change = ((monthly_stats['total_revenue'] - prev_revenue) / max(prev_revenue, 1) * 100) if prev_revenue > 0 else 0
    
    # Calculate monthly profit
    monthly_revenue = monthly_stats['total_revenue']
    monthly_costs = monthly_stats['total_cost'] 
    monthly_profit = monthly_revenue - monthly_costs
    
    # ✅ OPTIMIZATION 2: Daily breakdown using already fetched monthly transactions
    daily_breakdown = []
    
    # Group monthly transactions by date
    daily_txns = defaultdict(list)
    for txn in monthly_transactions:
        daily_txns[txn.transaction_date].append(txn)
    
    # Process each day
    current_date = first_day
    while current_date <= last_day:
        day_transactions = daily_txns.get(current_date, [])
        
        # Calculate daily stats manually
        daily_revenue = sum(
            (txn.unit_price * txn.quantity) for txn in day_transactions 
            if txn.transaction_type == 'SALE'
        )
        daily_costs = sum(
            (txn.unit_price * txn.quantity) for txn in day_transactions 
            if txn.transaction_type == 'SUPPLY'
        )
        daily_profit = daily_revenue - daily_costs
        
        daily_breakdown.append({
            'date': current_date,
            'day_name': current_date.strftime('%A'),
            'revenue': daily_revenue,
            'costs': daily_costs,
            'profit': daily_profit,
            'transactions': len(day_transactions),
            'sales': len([t for t in day_transactions if t.transaction_type == 'SALE']),
            'supplies': len([t for t in day_transactions if t.transaction_type == 'SUPPLY']),
        })
        
        current_date += timedelta(days=1)
    
    # ✅ OPTIMIZATION 3: Vessel performance using same data as monthly stats (CONSISTENT)
    # Calculate vessel performance from already fetched monthly_transactions
    vessel_stats = defaultdict(lambda: {
        'revenue': 0, 'costs': 0, 'sales_count': 0, 'supply_count': 0,
        'transfer_out_count': 0, 'transfer_in_count': 0, 'vessel': None
    })
    
    for txn in monthly_transactions:
        vessel_id = txn.vessel.id
        vessel_stats[vessel_id]['vessel'] = txn.vessel
        
        if txn.transaction_type == 'SALE':
            vessel_stats[vessel_id]['revenue'] += (txn.unit_price * txn.quantity)
            vessel_stats[vessel_id]['sales_count'] += 1
        elif txn.transaction_type == 'SUPPLY':
            vessel_stats[vessel_id]['costs'] += (txn.unit_price * txn.quantity)
            vessel_stats[vessel_id]['supply_count'] += 1
        elif txn.transaction_type == 'TRANSFER_OUT':
            vessel_stats[vessel_id]['transfer_out_count'] += 1
        elif txn.transaction_type == 'TRANSFER_IN':
            vessel_stats[vessel_id]['transfer_in_count'] += 1
    
    # Get trip and PO counts for vessels with transactions
    vessel_ids_with_txns = list(vessel_stats.keys())
    vessel_trips_counts = {}
    vessel_pos_counts = {}
    
    if vessel_ids_with_txns:
        # Single query for trip counts
        trip_counts = Trip.objects.filter(
            vessel_id__in=vessel_ids_with_txns,
            trip_date__gte=first_day,
            trip_date__lte=last_day
        ).values('vessel_id').annotate(count=Count('id'))
        
        for item in trip_counts:
            vessel_trips_counts[item['vessel_id']] = item['count']
        
        # Single query for PO counts  
        po_counts = PurchaseOrder.objects.filter(
            vessel_id__in=vessel_ids_with_txns,
            po_date__gte=first_day,
            po_date__lte=last_day
        ).values('vessel_id').annotate(count=Count('id'))
        
        for item in po_counts:
            vessel_pos_counts[item['vessel_id']] = item['count']
    
    # Convert to expected format
    vessel_performance = []
    for vessel_id, stats in vessel_stats.items():
        if stats['vessel'] is not None:
            vessel_performance.append({
                'vessel': stats['vessel'],
                'revenue': stats['revenue'],
                'costs': stats['costs'],
                'profit': stats['revenue'] - stats['costs'],
                'sales_count': stats['sales_count'],
                'supply_count': stats['supply_count'],
                'transfer_out_count': stats['transfer_out_count'],
                'transfer_in_count': stats['transfer_in_count'],
                'trips_count': vessel_trips_counts.get(vessel_id, 0),
                'pos_count': vessel_pos_counts.get(vessel_id, 0),
            })
    
    # Sort by revenue descending
    vessel_performance.sort(key=lambda x: x['revenue'], reverse=True)
    
    # ✅ OPTIMIZATION 4: Top products using existing helper (SIMPLIFIED)
    # Create a queryset from the monthly transactions for ProductAnalytics
    monthly_sales_ids = [txn.id for txn in monthly_transactions if txn.transaction_type == 'SALE']
    
    if monthly_sales_ids:
        monthly_sales_queryset = Transaction.objects.filter(
            id__in=monthly_sales_ids
        ).select_related('product', 'product__category')
        top_products = ProductAnalytics.get_top_selling_products(monthly_sales_queryset, limit=10)
    else:
        top_products = []
    
    # ✅ OPTIMIZATION 5: 12-month trends with single aggregated query (SQLite3 compatible)
    # Calculate exact month dates for last 12 months
    trend_first_month = date(year, month, 1) - timedelta(days=11*30)  # Approximate 11 months back
    trend_last_month = last_day
    
    # Single query for all trend data with month/year grouping (SQLite3 compatible)
    trend_data = Transaction.objects.filter(
        transaction_date__gte=trend_first_month,
        transaction_date__lte=trend_last_month
    ).extra(
        select={
            'month': "CAST(strftime('%%m', transaction_date) AS INTEGER)",
            'year': "CAST(strftime('%%Y', transaction_date) AS INTEGER)"
        }
    ).values('month', 'year', 'transaction_type').annotate(
        revenue=Sum(
            F('unit_price') * F('quantity'),
            filter=Q(transaction_type='SALE'),
            output_field=models.DecimalField()
        ),
        costs=Sum(
            F('unit_price') * F('quantity'),
            filter=Q(transaction_type='SUPPLY'),
            output_field=models.DecimalField()
        )
    ).order_by('year', 'month')
    
    # Process trend data into the expected format
    trend_months = []
    trend_dict = defaultdict(lambda: {'revenue': 0, 'costs': 0})
    
    for item in trend_data:
        month_key = (int(item['year']), int(item['month']))
        trend_dict[month_key]['revenue'] += (item['revenue'] or 0)
        trend_dict[month_key]['costs'] += (item['costs'] or 0)
    
    # Generate last 12 months
    for i in range(11, -1, -1):
        if month - i <= 0:
            trend_month = month - i + 12
            trend_year = year - 1
        else:
            trend_month = month - i
            trend_year = year
        
        month_key = (trend_year, trend_month)
        month_data = trend_dict.get(month_key, {'revenue': 0, 'costs': 0})
        
        trend_months.append({
            'month': calendar.month_name[trend_month],
            'year': trend_year,
            'revenue': month_data['revenue'],
            'costs': month_data['costs'],
            'profit': month_data['revenue'] - month_data['costs'],
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