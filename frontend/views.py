from django.forms import ValidationError
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Count, Q, F
from django.http import JsonResponse
from datetime import date, datetime
from decimal import Decimal
import decimal
from vessels.models import Vessel
from products.models import Product
from transactions.models import Transaction, InventoryLot, Trip, PurchaseOrder
from .utils import BilingualMessages
from django.db import models
from products.models import Product
from django.core.exceptions import ValidationError
import json

def is_admin_or_manager(user):
    """Check if user is superuser or in admin/manager groups"""
    if user.is_superuser:
        return True
    user_groups = [group.name.lower() for group in user.groups.all()]
    return 'administrators' in user_groups or 'managers' in user_groups

@login_required
def dashboard(request):
    """Main dashboard with overview and navigation"""
    
    # Get basic stats
    today = date.today()
    now = datetime.now()
    vessels = Vessel.objects.filter(active=True)
    
    # Today's sales summary
    today_sales = Transaction.objects.filter(
        transaction_type='SALE',
        transaction_date=today
    ).aggregate(
        total_revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        transaction_count=Count('id')
    )
    
    # Recent transactions
    recent_transactions = Transaction.objects.select_related(
        'vessel', 'product'
    ).order_by('-created_at')[:6]
    
    context = {
        'vessels': vessels,
        'today_sales': today_sales,
        'recent_transactions': recent_transactions,
        'today': today,
        'now': now,
    }
    
    return render(request, 'frontend/dashboard.html', context)

def get_vessel_badge_class(vessel_name):
    """Helper function to get vessel badge class"""
    colors = {
        'amman': 'bg-primary',
        'aylah': 'bg-danger',
        'sinaa': 'bg-success', 
        'nefertiti': 'bg-secondary',
        'babel': 'bg-warning',
        'dahab': 'bg-info',
    }
    return colors.get(vessel_name.lower(), 'bg-primary')

@login_required
def set_language(request):
    """AJAX endpoint to set user's language preference"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        language = data.get('language', 'en')
        
        # Validate language
        if language not in ['en', 'ar']:
            return JsonResponse({'success': False, 'error': 'Invalid language'})
        
        # Save to session
        request.session['preferred_language'] = language
        
        return JsonResponse({
            'success': True,
            'language': language,
            'message': f'Language set to {language}'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})