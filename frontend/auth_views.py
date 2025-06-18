from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Count, Q
from vessels.models import Vessel
from .utils import BilingualMessages
import json
from django.core.cache import cache
from products.models import Product
from transactions.models import get_all_vessel_pricing_summary
from .permissions import get_user_role, UserRoles

def get_optimized_vessel_pricing_data():
    """
    Get vessel pricing data with database aggregations for performance.
    
    Returns:
        tuple: (vessel_pricing_data_dict, total_general_products_count)
    """
    
    total_general_products = Product.objects.filter(is_duty_free=False, active=True).count()
    
    touristic_vessels = Vessel.objects.filter(
        has_duty_free=False, 
        active=True
    ).annotate(
        custom_prices_count=Count(
            'custom_prices',
            filter=Q(
                custom_prices__product__is_duty_free=False,
                custom_prices__product__active=True
            )
        )
    ).order_by('name')
    
    vessel_pricing_data = {}
    for vessel in touristic_vessels:
        custom_prices_count = vessel.custom_prices_count
        missing_count = max(0, total_general_products - custom_prices_count)
        completion_pct = (custom_prices_count / max(total_general_products, 1)) * 100
        
        vessel_pricing_data[vessel.id] = {
            'completion_percentage': round(completion_pct, 0),
            'products_priced': custom_prices_count,
            'total_products': total_general_products,
            'missing_count': missing_count,
            'has_warnings': missing_count > 0
        }
    
    return vessel_pricing_data, total_general_products

def get_cached_pricing_summary():
    """
    Get pricing summary with caching for performance optimization.
    Uses 5-minute cache to reduce database load.
    
    Returns:
        dict: Cached pricing summary data
    """
    
    cache_key = 'vessel_pricing_summary'
    summary = cache.get(cache_key)
    
    if summary is None:
        
        summary = get_all_vessel_pricing_summary()
        cache.set(cache_key, summary, 300)
    
    return summary

def user_login(request):
    """User login view with bilingual support"""
    
    if request.user.is_authenticated:
        return redirect('frontend:dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        if not username or not password:
            BilingualMessages.error(request, 'username_password_required')
            return render(request, 'frontend/auth/login.html')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if user.is_active:
                login(request, user)
                
                preferred_language = request.session.get('preferred_language', 'en')
                request.session['preferred_language'] = preferred_language
                
                BilingualMessages.success(request, 'login_successful', username=user.username)
                
                next_url = request.GET.get('next', 'frontend:dashboard')
                return redirect(next_url)
            else:
                BilingualMessages.error(request, 'account_deactivated')
        else:
            BilingualMessages.error(request, 'invalid_credentials')
    
    return render(request, 'frontend/auth/login.html')

@login_required
def user_logout(request):
    """User logout view"""
    username = request.user.username
    logout(request)
    BilingualMessages.success(request, 'logout_successful', username=username)
    return redirect('frontend:login')

@login_required
def user_profile(request):
    """User profile view"""
    
    context = {
        'user': request.user,
        'user_groups': request.user.groups.all(),
    }
    return render(request, 'frontend/auth/user_profile.html', context)

@login_required
def check_permission(request):
    """AJAX endpoint to check user permissions with detailed info"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        data = json.loads(request.body)
        permission_name = data.get('permission')
        
        user_role = get_user_role(request.user)
        has_permission = request.user.has_perm(permission_name) if permission_name else False
        
        return JsonResponse({
            'success': True,
            'has_permission': has_permission,
            'user_role': user_role,
            'user_groups': [group.name for group in request.user.groups.all()],
            'is_superuser': request.user.is_superuser,
            'role_hierarchy': UserRoles.HIERARCHY.get(user_role, 0) if user_role else 0
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})