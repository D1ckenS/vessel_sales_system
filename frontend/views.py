from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count
from datetime import date, timedelta
from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, InventoryLot

@login_required
def dashboard(request):
    """Main dashboard with overview and navigation"""
    
    # Get basic stats
    today = date.today()
    vessels = Vessel.objects.filter(active=True)
    
    # Today's sales summary
    today_sales = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date=today
    ).aggregate(
        total_revenue=Sum('unit_price'),
        transaction_count=Count('id')
    )
    
    # Recent transactions
    recent_transactions = Transaction.objects.select_related(
        'vessel', 'product'
    ).order_by('-created_at')[:10]
    
    context = {
        'vessels': vessels,
        'today_sales': today_sales,
        'recent_transactions': recent_transactions,
        'today': today,
    }
    
    return render(request, 'frontend/dashboard.html', context)

@login_required
def sales_entry(request):
    """Simple sales entry interface"""
    return render(request, 'frontend/sales_entry.html')

@login_required
def inventory_check(request):
    """Quick inventory checking interface"""
    return render(request, 'frontend/inventory_check.html')

@login_required 
def transfer_center(request):
    """Simple transfer interface"""
    return render(request, 'frontend/transfer_center.html')

@login_required
def reports_dashboard(request):
    """Reports hub with different report options"""
    return render(request, 'frontend/reports_dashboard.html')

@login_required
def daily_report(request):
    """User-friendly daily reports"""
    return render(request, 'frontend/daily_report.html')

@login_required
def monthly_report(request):
    """User-friendly monthly reports"""
    return render(request, 'frontend/monthly_report.html')

@login_required
def analytics_report(request):
    """User-friendly analytics dashboard"""
    return render(request, 'frontend/analytics_report.html')