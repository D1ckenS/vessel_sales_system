# frontend/permissions.py
"""
Role-Based Permission System for Vessel Sales System
Provides decorators and utilities for controlling access based on user groups
"""

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
from functools import wraps

# =============================================================================
# GROUP DEFINITIONS
# =============================================================================

class UserRoles:
    """Define all user roles and their hierarchy"""
    SUPERUSER = 'superuser'
    ADMINISTRATORS = 'Administrators'
    MANAGERS = 'Managers'
    VESSEL_OPERATORS = 'Vessel Operators'
    INVENTORY_STAFF = 'Inventory Staff'
    VIEWERS = 'Viewers'
    
    # Role hierarchy (higher number = more permissions)
    HIERARCHY = {
        SUPERUSER: 100,
        ADMINISTRATORS: 80,
        MANAGERS: 60,
        VESSEL_OPERATORS: 40,
        INVENTORY_STAFF: 30,
        VIEWERS: 10
    }

# =============================================================================
# PERMISSION CHECKER FUNCTIONS
# =============================================================================

def get_user_role(user):
    """
    Get the primary role of a user based on group membership.
    
    Args:
        user: Django User instance
    
    Returns:
        UserRoles: The user's primary role enum value
    """
    if not user.is_authenticated:
        return None
    
    if user.is_superuser:
        return UserRoles.SUPERUSER
    
    user_groups = user.groups.values_list('name', flat=True)
    
    # Return the highest priority role
    user_role = None
    highest_priority = 0
    
    for group_name in user_groups:
        if group_name in UserRoles.HIERARCHY:
            priority = UserRoles.HIERARCHY[group_name]
            if priority > highest_priority:
                highest_priority = priority
                user_role = group_name
    
    return user_role

def has_role(user, required_roles):
    """
    Check if user has any of the required roles.
    
    Args:
        user: Django User instance
        required_roles: Single role string or list of role strings
    
    Returns:
        bool: True if user has at least one of the required roles
    """
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    if isinstance(required_roles, str):
        required_roles = [required_roles]
    
    user_groups = set(user.groups.values_list('name', flat=True))
    required_groups = set(required_roles)
    
    return bool(user_groups.intersection(required_groups))

def has_minimum_role(user, minimum_role):
    """Check if user has at least the minimum role level"""
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    user_role = get_user_role(user)
    if not user_role:
        return False
    
    user_priority = UserRoles.HIERARCHY.get(user_role, 0)
    min_priority = UserRoles.HIERARCHY.get(minimum_role, 100)
    
    return user_priority >= min_priority

# =============================================================================
# SPECIFIC PERMISSION CHECKERS
# =============================================================================

def is_superuser_only(user):
    """Check if user is superuser"""
    return user.is_authenticated and user.is_superuser

def is_admin_or_manager(user):
    """Check if user is Administrator or Manager (FIXED VERSION)"""
    return user.is_authenticated and (
        user.is_superuser or 
        user.groups.filter(name__in=[UserRoles.ADMINISTRATORS, UserRoles.MANAGERS]).exists()
    )

def is_vessel_operator(user):
    """Check if user is Vessel Operator"""
    return has_role(user, UserRoles.VESSEL_OPERATORS)

def is_inventory_staff(user):
    """Check if user is Inventory Staff"""
    return has_role(user, UserRoles.INVENTORY_STAFF)

def can_access_operations(user):
    """Check if user can access operational functions (sales, supply, transfers)"""
    return has_role(user, [
        UserRoles.ADMINISTRATORS,
        UserRoles.VESSEL_OPERATORS
    ])

def can_access_reports(user):
    """Check if user can access reports"""
    return has_role(user, [
        UserRoles.ADMINISTRATORS,
        UserRoles.MANAGERS,
        UserRoles.INVENTORY_STAFF
    ])

def can_access_inventory(user):
    """Check if user can access inventory"""
    return user.is_authenticated  # All authenticated users can view inventory

def can_add_products(user):
    """Check if user can add products"""
    return has_role(user, [UserRoles.ADMINISTRATORS, UserRoles.MANAGERS])

def can_view_financials(user):
    """Check if user can view financial data (COGS, profit, etc.)"""
    return has_role(user, [UserRoles.ADMINISTRATORS, UserRoles.MANAGERS])

def can_edit_selling_prices(user):
    """Check if user can edit selling prices"""
    return has_role(user, [UserRoles.ADMINISTRATORS, UserRoles.MANAGERS])

def can_access_system_setup(user):
    """Check if user can access system setup"""
    return user.is_authenticated and user.is_superuser

# =============================================================================
# DECORATORS
# =============================================================================

def require_role(required_roles):
    """Decorator to require specific roles"""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not has_role(request.user, required_roles):
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Permission denied'})
                messages.error(request, 'You do not have permission to access this feature.')
                return redirect('frontend:dashboard')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def require_minimum_role(minimum_role):
    """Decorator to require minimum role level"""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not has_minimum_role(request.user, minimum_role):
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Permission denied'})
                messages.error(request, 'You do not have permission to access this feature.')
                return redirect('frontend:dashboard')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

# Common role decorators - FIXED VERSION
def superuser_required(view_func):
    """Decorator requiring superuser access"""
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if not is_superuser_only(request.user):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Permission denied'})
            messages.error(request, 'You do not have permission to access this feature.')
            return redirect('frontend:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def admin_or_manager_required(view_func):
    """Decorator requiring admin or manager access"""
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if not is_admin_or_manager(request.user):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Permission denied'})
            messages.error(request, 'You do not have permission to access this feature.')
            return redirect('frontend:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def operations_access_required(view_func):
    """Decorator requiring operations access (sales, supply, transfers)"""
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if not can_access_operations(request.user):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Permission denied'})
            messages.error(request, 'You do not have permission to access this feature.')
            return redirect('frontend:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def reports_access_required(view_func):
    """Decorator requiring reports access (Administrators, Managers & Inventory Staff)"""
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if not can_access_reports(request.user):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Permission denied'})
            messages.error(request, 'You do not have permission to access this feature.')
            return redirect('frontend:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

# =============================================================================
# CONTEXT PROCESSOR
# =============================================================================

def user_permissions_context(request):
    """Add user permissions to template context"""
    if not request.user.is_authenticated:
        return {}
    
    return {
        'user_role': get_user_role(request.user),
        'user_permissions': {
            'is_superuser': is_superuser_only(request.user),
            'is_admin_or_manager': is_admin_or_manager(request.user),
            'can_access_operations': can_access_operations(request.user),
            'can_access_reports': can_access_reports(request.user),
            'can_access_inventory': can_access_inventory(request.user),
            'can_add_products': can_add_products(request.user),
            'can_view_financials': can_view_financials(request.user),
            'can_edit_selling_prices': can_edit_selling_prices(request.user),
            'can_access_system_setup': can_access_system_setup(request.user),
        }
    }