from django.utils import timezone
from django.db import models
from datetime import datetime, timedelta, date
from django.contrib.auth.decorators import login_required
import calendar
from django.db.models import Avg, Sum, Count, F, Q, Case, When
from transactions.models import Transaction, InventoryLot, Trip, PurchaseOrder, get_vessel_pricing_warnings
from django.shortcuts import render
from vessels.models import Vessel
from products.models import Product
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

@reports_access_required
def trip_reports(request):
    """Trip-based sales reports"""
    
    # Get filter parameters
    vessel_filter = request.GET.get('vessel')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    status_filter = request.GET.get('status')
    
    # Base queryset
    trips = Trip.objects.select_related('vessel', 'created_by').prefetch_related('sales_transactions')
    
    # Apply filters
    if vessel_filter:
        trips = trips.filter(vessel_id=vessel_filter)
    if date_from:
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
        trips = trips.filter(trip_date__gte=date_from_obj)
    if date_to:
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
        trips = trips.filter(trip_date__lte=date_to_obj)
    if status_filter == 'completed':
        trips = trips.filter(is_completed=True)
    elif status_filter == 'in_progress':
        trips = trips.filter(is_completed=False)
    
    trips = trips.order_by('-trip_date', '-created_at')
    
    # Calculate summary statistics
    total_trips = trips.count()
    total_revenue = sum(trip.total_revenue for trip in trips)
    total_passengers = sum(trip.passenger_count for trip in trips)
    avg_revenue_per_trip = total_revenue / total_trips if total_trips > 0 else 0
    avg_revenue_per_passenger = total_revenue / total_passengers if total_passengers > 0 else 0
    
    # Get vessels for filter
    vessels = Vessel.objects.filter(active=True).order_by('name')
    
    context = {
        'trips': trips,
        'vessels': vessels,
        'filters': {
            'vessel': vessel_filter,
            'date_from': date_from,
            'date_to': date_to,
            'status': status_filter,
        },
        'summary': {
            'total_trips': total_trips,
            'total_revenue': total_revenue,
            'total_passengers': total_passengers,
            'avg_revenue_per_trip': avg_revenue_per_trip,
            'avg_revenue_per_passenger': avg_revenue_per_passenger,
        }
    }
    
    return render(request, 'frontend/trip_reports.html', context)

@reports_access_required
def po_reports(request):
    """Purchase Order reports"""
    
    # Get filter parameters
    vessel_filter = request.GET.get('vessel')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    status_filter = request.GET.get('status')
    
    # Base queryset
    purchase_orders = PurchaseOrder.objects.select_related('vessel', 'created_by').prefetch_related('supply_transactions')
    
    # Apply filters
    if vessel_filter:
        purchase_orders = purchase_orders.filter(vessel_id=vessel_filter)
    if date_from:
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
        purchase_orders = purchase_orders.filter(po_date__gte=date_from_obj)
    if date_to:
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
        purchase_orders = purchase_orders.filter(po_date__lte=date_to_obj)
    if status_filter == 'completed':
        purchase_orders = purchase_orders.filter(is_completed=True)
    elif status_filter == 'in_progress':
        purchase_orders = purchase_orders.filter(is_completed=False)
    
    purchase_orders = purchase_orders.order_by('-po_date', '-created_at')
    
    # Calculate summary statistics
    total_pos = purchase_orders.count()
    total_cost = sum(po.total_cost for po in purchase_orders)
    avg_cost_per_po = total_cost / total_pos if total_pos > 0 else 0
    
    # Get vessels for filter
    vessels = Vessel.objects.filter(active=True).order_by('name')
    
    context = {
        'purchase_orders': purchase_orders,
        'vessels': vessels,
        'filters': {
            'vessel': vessel_filter,
            'date_from': date_from,
            'date_to': date_to,
            'status': status_filter,
        },
        'summary': {
            'total_pos': total_pos,
            'total_cost': total_cost,
            'avg_cost_per_po': avg_cost_per_po,
        }
    }
    
    return render(request, 'frontend/po_reports.html', context)

@reports_access_required
def transactions_list(request):
    """Frontend transactions list to replace Django admin redirect"""
    
    # Get filter parameters
    transaction_type = request.GET.get('type')
    vessel_filter = request.GET.get('vessel')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Base queryset
    transactions = Transaction.objects.select_related(
        'vessel', 'product', 'created_by', 'trip', 'purchase_order'
    ).order_by('-transaction_date', '-created_at')
    
    # Apply filters
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    if vessel_filter:
        transactions = transactions.filter(vessel_id=vessel_filter)
    if date_from:
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
        transactions = transactions.filter(transaction_date__gte=date_from_obj)
    if date_to:
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
        transactions = transactions.filter(transaction_date__lte=date_to_obj)
    
    # Limit to recent transactions for performance
    transactions = transactions[:200]
    
    # Get vessels for filter
    vessels = Vessel.objects.filter(active=True).order_by('name')
    
    context = {
        'transactions': transactions,
        'vessels': vessels,
        'transaction_types': Transaction.TRANSACTION_TYPES,
        'filters': {
            'type': transaction_type,
            'vessel': vessel_filter,
            'date_from': date_from,
            'date_to': date_to,
        }
    }
    
    return render(request, 'frontend/transactions_list.html', context)

@reports_access_required
def reports_dashboard(request):
    """Reports hub with statistics and report options"""
    
    today = timezone.now().date()
    
    # Today's revenue from sales using F() expressions
    today_sales = Transaction.objects.filter(
        transaction_date=today,
        transaction_type='SALE'
    ).aggregate(
        total_revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        count=Count('id')
    )
    
    # Today's costs from supplies using F() expressions
    today_supplies = Transaction.objects.filter(
        transaction_date=today,
        transaction_type='SUPPLY'
    ).aggregate(
        total_cost=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        count=Count('id')
    )
    
    # Today's transaction count (all types)
    today_transactions = Transaction.objects.filter(
        transaction_date=today
    ).count()
    
    # Today's trips (completed and in-progress)
    today_trips = Trip.objects.filter(
        trip_date=today
    ).count()
    
    # Today's purchase orders (completed and in-progress)  
    today_pos = PurchaseOrder.objects.filter(
        po_date=today
    ).count()
    
    context = {
        'today_stats': {
            'revenue': today_sales['total_revenue'] or 0,
            'cost': today_supplies['total_cost'] or 0,  # Added cost
            'transactions': today_transactions,
            'trips': today_trips,
            'purchase_orders': today_pos,
        }
    }
    
    return render(request, 'frontend/reports_dashboard.html', context)

@reports_access_required
def comprehensive_report(request):
    """Comprehensive transaction report - all transaction types with filtering"""
    
    # Get filter parameters
    vessel_filter = request.GET.get('vessel')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    transaction_type_filter = request.GET.get('transaction_type')
    
    # Base queryset - all transactions
    transactions = Transaction.objects.select_related(
        'vessel', 'product', 'created_by', 'trip', 'purchase_order'
    ).order_by('-transaction_date', '-created_at')
    
    # Apply filters
    if vessel_filter:
        transactions = transactions.filter(vessel_id=vessel_filter)
        
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            transactions = transactions.filter(transaction_date__gte=date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            transactions = transactions.filter(transaction_date__lte=date_to_obj)
        except ValueError:
            pass
    else:
        # If no "to date", and we have "from date", make it a single day report
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                transactions = transactions.filter(transaction_date=date_from_obj)
            except ValueError:
                pass
    
    if transaction_type_filter:
        transactions = transactions.filter(transaction_type=transaction_type_filter)
    
    # Calculate summary statistics using F() expressions for calculated totals
    summary_stats = transactions.aggregate(
        total_transactions=Count('id'),
        total_sales_revenue=Sum(
            F('unit_price') * F('quantity'), 
            output_field=models.DecimalField(),
            filter=Q(transaction_type='SALE')
        ),
        total_purchase_cost=Sum(
            F('unit_price') * F('quantity'), 
            output_field=models.DecimalField(),
            filter=Q(transaction_type='SUPPLY')
        ),
        total_quantity=Sum('quantity'),
        sales_count=Count('id', filter=Q(transaction_type='SALE')),
        supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
        transfer_out_count=Count('id', filter=Q(transaction_type='TRANSFER_OUT')),
        transfer_in_count=Count('id', filter=Q(transaction_type='TRANSFER_IN')),
    )

    # Also update type_breakdown and vessel_breakdown:
    type_breakdown = []
    for type_code, type_display in Transaction.TRANSACTION_TYPES:
        type_stats = transactions.filter(transaction_type=type_code).aggregate(
            count=Count('id'),
            total_amount=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
            total_quantity=Sum('quantity')
        )
        if type_stats['count'] > 0:  # Only include types with data
            type_breakdown.append({
                'transaction_type': type_display,  # Use display name
                'transaction_code': type_code,     # Keep code for reference
                'count': type_stats['count'],
                'total_amount': type_stats['total_amount'],
                'total_quantity': type_stats['total_quantity']
            })

    vessel_breakdown = transactions.values(
        'vessel__name', 'vessel__name_ar'
    ).annotate(
        count=Count('id'),
        total_amount=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        total_quantity=Sum('quantity')
    ).order_by('vessel__name')

    product_breakdown = transactions.values(
        'product__name', 'product__item_id'
    ).annotate(
        count=Count('id'),
        total_amount=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        total_quantity=Sum('quantity')
    ).order_by('-total_quantity')[:10]
    
    # NEW: Check for pricing warnings in transactions
    pricing_warnings_count = 0
    if vessel_filter:
        # Check if filtered vessel is touristic and has pricing warnings
        try:
            filtered_vessel = Vessel.objects.get(id=vessel_filter)
            if not filtered_vessel.has_duty_free:
                
                vessel_warnings = get_vessel_pricing_warnings(filtered_vessel)
                if vessel_warnings['has_warnings']:
                    pricing_warnings_count = vessel_warnings['missing_price_count']
        except Vessel.DoesNotExist:
            pass
    
    # Get date range info
    date_range_info = None
    if date_from:
        if date_to:
            date_range_info = {
                'type': 'duration',
                'from': date_from,
                'to': date_to,
                'days': (datetime.strptime(date_to, '%Y-%m-%d').date() - 
                        datetime.strptime(date_from, '%Y-%m-%d').date()).days + 1
            }
        else:
            date_range_info = {
                'type': 'single_day',
                'date': date_from
            }
    
    # Get vessels for filter dropdown
    vessels = Vessel.objects.filter(active=True).order_by('name')
    
    # Limit transactions for display performance
    transactions_limited = transactions[:200]
    
    context = {
        'transactions': transactions_limited,
        'vessels': vessels,
        'transaction_types': Transaction.TRANSACTION_TYPES,
        'pricing_warnings': {
            'has_warnings': pricing_warnings_count > 0,
            'missing_prices_count': pricing_warnings_count,
            'message': f"⚠️ {pricing_warnings_count} products missing custom pricing" if pricing_warnings_count > 0 else None
        },
        'filters': {
            'vessel': vessel_filter,
            'date_from': date_from,
            'date_to': date_to,
            'transaction_type': transaction_type_filter,
        },
        'summary_stats': summary_stats,
        'type_breakdown': type_breakdown,
        'vessel_breakdown': vessel_breakdown,
        'product_breakdown': product_breakdown,
        'date_range_info': date_range_info,
        'total_shown': min(transactions.count(), 200),
        'total_available': transactions.count(),
    }
    
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
    
    # Get all active vessels
    vessels = Vessel.objects.filter(active=True).order_by('name')
    
    # === SUMMARY STATISTICS ===
    
    # Daily transactions for selected date
    daily_transactions = Transaction.objects.filter(transaction_date=selected_date)
    
    # Previous day transactions for comparison
    previous_transactions = Transaction.objects.filter(transaction_date=previous_date)
    
    # Summary stats for selected date - FIXED WITH PROPER output_field
    daily_stats = daily_transactions.aggregate(
        total_revenue=Sum(
            F('unit_price') * F('quantity'), 
            output_field=models.DecimalField(max_digits=15, decimal_places=3),
            filter=Q(transaction_type='SALE')
        ),
        total_purchase_cost=Sum(
            F('unit_price') * F('quantity'), 
            output_field=models.DecimalField(max_digits=15, decimal_places=3),
            filter=Q(transaction_type='SUPPLY')
        ),
        total_transactions=Count('id'),
        sales_count=Count('id', filter=Q(transaction_type='SALE')),
        supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
        transfer_count=Count('id', filter=Q(transaction_type__in=['TRANSFER_IN', 'TRANSFER_OUT'])),
        total_quantity=Sum('quantity'),
    )
    
    # Previous day stats for comparison - FIXED
    previous_stats = previous_transactions.aggregate(
        total_revenue=Sum(
            F('unit_price') * F('quantity'), 
            output_field=models.DecimalField(max_digits=15, decimal_places=3),
            filter=Q(transaction_type='SALE')
        ),
        total_transactions=Count('id'),
    )
    
    # Calculate profit margin
    daily_revenue = daily_stats['total_revenue'] or 0
    daily_costs = daily_stats['total_purchase_cost'] or 0
    daily_profit = daily_revenue - daily_costs
    profit_margin = (daily_profit / daily_revenue * 100) if daily_revenue > 0 else 0
    
    # Calculate change from previous day
    prev_revenue = previous_stats['total_revenue'] or 0
    revenue_change = ((daily_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0
    
    prev_transactions = previous_stats['total_transactions'] or 0
    transaction_change = daily_stats['total_transactions'] - prev_transactions
    
    # === VESSEL BREAKDOWN ===
    
    vessel_breakdown = []
    for vessel in vessels:
        vessel_transactions = daily_transactions.filter(vessel=vessel)
        
        # FIXED vessel stats with proper output_field
        vessel_stats = vessel_transactions.aggregate(
            revenue=Sum(
                F('unit_price') * F('quantity'), 
                output_field=models.DecimalField(max_digits=15, decimal_places=3),
                filter=Q(transaction_type='SALE')
            ),
            costs=Sum(
                F('unit_price') * F('quantity'), 
                output_field=models.DecimalField(max_digits=15, decimal_places=3),
                filter=Q(transaction_type='SUPPLY')
            ),
            sales_count=Count('id', filter=Q(transaction_type='SALE')),
            supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
            transfer_out_count=Count('id', filter=Q(transaction_type='TRANSFER_OUT')),
            transfer_in_count=Count('id', filter=Q(transaction_type='TRANSFER_IN')),
            total_quantity=Sum('quantity'),
        )
        
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
        
        # Calculate vessel profit
        vessel_revenue = vessel_stats['revenue'] or 0
        vessel_costs = vessel_stats['costs'] or 0
        vessel_profit = vessel_revenue - vessel_costs
        
        vessel_breakdown.append({
            'vessel': vessel,
            'stats': vessel_stats,
            'profit': vessel_profit,
            'trips': list(vessel_trips),
            'pos': list(vessel_pos),
        })
    
    # === INVENTORY CHANGES ===
    
    # Products that had inventory changes today - FIXED
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
    ).order_by('-total_out')[:20]  # Top 20 most active products
    
    # === BUSINESS INSIGHTS ===
    
    # Best performing vessel by revenue
    best_vessel = max(vessel_breakdown, key=lambda v: v['stats']['revenue'] or 0) if vessel_breakdown else None
    
    # Most active vessel by transaction count
    most_active_vessel = max(vessel_breakdown, key=lambda v: (v['stats']['sales_count'] or 0) + (v['stats']['supply_count'] or 0)) if vessel_breakdown else None
    
    # Low stock alerts (products with less than 10 units total across all vessels)
    low_stock_products = []
    out_of_stock_products = []

    for product in Product.objects.filter(active=True):
        total_stock = InventoryLot.objects.filter(
            product=product,
            remaining_quantity__gt=0
        ).aggregate(total=Sum('remaining_quantity'))['total'] or 0
        
        if total_stock == 0:
            out_of_stock_products.append({
                'product': product,
                'total_stock': total_stock
            })
        elif total_stock < 10:  # Low stock threshold (1-9 units)
            low_stock_products.append({
                'product': product,
                'total_stock': total_stock
            })
    
    # Unusual activity (vessels with unusually high transaction count compared to their average)
    unusual_activity = []
    for vessel_data in vessel_breakdown:
        vessel = vessel_data['vessel']
        today_count = (vessel_data['stats']['sales_count'] or 0) + (vessel_data['stats']['supply_count'] or 0)
        
        # Get average transaction count for this vessel over last 30 days
        thirty_days_ago = selected_date - timedelta(days=30)
        avg_transactions = Transaction.objects.filter(
            vessel=vessel,
            transaction_date__gte=thirty_days_ago,
            transaction_date__lt=selected_date
        ).values('transaction_date').annotate(
            daily_count=Count('id')
        ).aggregate(avg=Avg('daily_count'))['avg'] or 0
        
        # If today's count is 50% higher than average, flag it
        if avg_transactions > 0 and today_count > avg_transactions * 1.5:
            unusual_activity.append({
                'vessel': vessel,
                'today_count': today_count,
                'avg_count': round(avg_transactions, 1),
                'percentage_increase': round((today_count - avg_transactions) / avg_transactions * 100, 1)
            })
    
    # === ALL TRIPS AND POS FOR THE DAY ===
    
    # All trips on this date
    daily_trips = Trip.objects.filter(
        trip_date=selected_date
    ).select_related('vessel').order_by('vessel__name', 'trip_number')
    
    # All POs on this date
    daily_pos = PurchaseOrder.objects.filter(
        po_date=selected_date
    ).select_related('vessel').order_by('vessel__name', 'po_number')
    
    context = {
        'selected_date': selected_date,
        'previous_date': previous_date,
        'daily_stats': daily_stats,
        'daily_profit': daily_profit,
        'profit_margin': profit_margin,
        'revenue_change': revenue_change,
        'transaction_change': transaction_change,
        'vessel_breakdown': vessel_breakdown,
        'inventory_changes': inventory_changes,
        'best_vessel': best_vessel,
        'most_active_vessel': most_active_vessel,
        'low_stock_products': low_stock_products[:10],  # Limit to top 10
        'out_of_stock_products': out_of_stock_products[:10],  # Limit to top 10
        'unusual_activity': unusual_activity,
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
    
    # Generate year range from system start to future
    SYSTEM_START_YEAR = 2023  # Change this to when your system started
    current_year = timezone.now().year
    year_range = range(SYSTEM_START_YEAR, current_year + 1)  # From start year to current+2
    months ={
        1:'January',
        2:'February',
        3:'March',
        4:'April',
        5:'May',
        6:'June',
        7:'July',
        8:'August',
        9:'September',
        10:'October',
        11:'November',
        12:'December',
    }
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
    
    # === MONTHLY STATISTICS ===
    
    # Current month transactions
    monthly_transactions = Transaction.objects.filter(
        transaction_date__gte=first_day,
        transaction_date__lte=last_day
    )
    
    # Previous month transactions for comparison
    prev_monthly_transactions = Transaction.objects.filter(
        transaction_date__gte=prev_first_day,
        transaction_date__lte=prev_last_day
    )
    
    # Monthly summary stats
    monthly_stats = monthly_transactions.aggregate(
        total_revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
        total_costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
        total_transactions=Count('id'),
        sales_count=Count('id', filter=Q(transaction_type='SALE')),
        supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
        transfer_count=Count('id', filter=Q(transaction_type__in=['TRANSFER_IN', 'TRANSFER_OUT'])),
        total_quantity=Sum('quantity'),
    )
    
    # Previous month stats for comparison
    prev_monthly_stats = prev_monthly_transactions.aggregate(
        total_revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
        total_transactions=Count('id'),
    )
    
    # Calculate changes from previous month
    monthly_revenue = monthly_stats['total_revenue'] or 0
    monthly_costs = monthly_stats['total_costs'] or 0
    monthly_profit = monthly_revenue - monthly_costs
    
    prev_revenue = prev_monthly_stats['total_revenue'] or 0
    revenue_change = ((monthly_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0
    
    # === DAILY BREAKDOWN ===
    
    # Get daily stats for the month
    daily_breakdown = []
    current_date = first_day
    
    while current_date <= last_day:
        daily_transactions = monthly_transactions.filter(transaction_date=current_date)
        daily_stats = daily_transactions.aggregate(
            revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
            costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
            transactions=Count('id'),
            sales=Count('id', filter=Q(transaction_type='SALE')),
            supplies=Count('id', filter=Q(transaction_type='SUPPLY')),
        )
        
        daily_revenue = daily_stats['revenue'] or 0
        daily_costs = daily_stats['costs'] or 0
        daily_profit = daily_revenue - daily_costs
        
        daily_breakdown.append({
            'date': current_date,
            'day_name': current_date.strftime('%A'),
            'revenue': daily_revenue,
            'costs': daily_costs,
            'profit': daily_profit,
            'transactions': daily_stats['transactions'],
            'sales': daily_stats['sales'],
            'supplies': daily_stats['supplies'],
        })
        
        current_date += timedelta(days=1)
    
    # === VESSEL PERFORMANCE ===
    
    vessels = Vessel.objects.filter(active=True)
    vessel_performance = []
    
    for vessel in vessels:
        vessel_transactions = monthly_transactions.filter(vessel=vessel)
        vessel_stats = vessel_transactions.aggregate(
            revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
            costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
            sales_count=Count('id', filter=Q(transaction_type='SALE')),
            supply_count=Count('id', filter=Q(transaction_type='SUPPLY')),
            transfer_out_count=Count('id', filter=Q(transaction_type='TRANSFER_OUT')),
            transfer_in_count=Count('id', filter=Q(transaction_type='TRANSFER_IN')),
        )
        
        vessel_revenue = vessel_stats['revenue'] or 0
        vessel_costs = vessel_stats['costs'] or 0
        vessel_profit = vessel_revenue - vessel_costs
        
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
        
        vessel_performance.append({
            'vessel': vessel,
            'revenue': vessel_revenue,
            'costs': vessel_costs,
            'profit': vessel_profit,
            'sales_count': vessel_stats['sales_count'],
            'supply_count': vessel_stats['supply_count'],
            'transfer_out_count': vessel_stats['transfer_out_count'],
            'transfer_in_count': vessel_stats['transfer_in_count'],
            'trips_count': vessel_trips,
            'pos_count': vessel_pos,
        })
    
    # Sort by revenue descending
    vessel_performance.sort(key=lambda x: x['revenue'], reverse=True)
    
    # === TOP PRODUCTS ===
    
    top_products = monthly_transactions.values(
        'product__name', 'product__item_id'
    ).annotate(
        total_quantity_sold=Sum('quantity', filter=Q(transaction_type='SALE')),
        total_revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
        total_supplied=Sum('quantity', filter=Q(transaction_type='SUPPLY')),
        transaction_count=Count('id')
    ).filter(
        total_quantity_sold__gt=0
    ).order_by('-total_revenue')[:10]
    
    # === MONTH-OVER-MONTH TRENDS ===
    
    # Get last 12 months data for trends
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
        
        trend_stats = trend_transactions.aggregate(
            revenue=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SALE')),
            costs=Sum(F('unit_price') * F('quantity'), filter=Q(transaction_type='SUPPLY')),
        )
        
        trend_revenue = trend_stats['revenue'] or 0
        trend_costs = trend_stats['costs'] or 0
        
        trend_months.append({
            'month': trend_date.strftime('%B'),
            'year': trend_date.year,
            'revenue': trend_revenue,
            'costs': trend_costs,
            'profit': trend_revenue - trend_costs,
        })
    
    # Get month name
    month_name = calendar.month_name[month]
    profit_margin = ((monthly_profit / monthly_revenue * 100) if monthly_revenue > 0 else 0)
    
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
        'vessels': vessels,
        'profit_margin': profit_margin,
        'year_range': year_range,  # Added this line
        'months': months
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