from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group, Permission
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction, models
from django.db.models import Sum, F, Count, Q, Avg
from frontend.utils.validation_helpers import ValidationHelper
from .utils.query_helpers import TransactionQueryHelper
from transactions.models import Transaction, Trip, PurchaseOrder, InventoryLot
from vessels.models import Vessel
from .utils import BilingualMessages
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from datetime import date, datetime, timedelta
import json
import secrets
import string
from django.core.cache import cache
from .permissions import is_admin_or_manager, admin_or_manager_required, is_superuser_only, superuser_required
import traceback
from products.models import Product
from transactions.models import get_all_vessel_pricing_summary, get_vessel_pricing_warnings
from .permissions import get_user_role, UserRoles
from .utils.response_helpers import FormResponseHelper, JsonResponseHelper
from .utils.crud_helpers import CRUDHelper, AdminActionHelper
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

def get_optimized_vessel_pricing_data():
    """
    Get vessel pricing data with database aggregations for performance.
    
    Returns:
        tuple: (vessel_pricing_data_dict, total_general_products_count)
    """
    
    # Get total general products count
    total_general_products = Product.objects.filter(is_duty_free=False, active=True).count()
    
    # OPTIMIZED: Get all vessels with their pricing counts in ONE query
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
    
    # Build vessel pricing data dictionary
    vessel_pricing_data = {}
    for vessel in touristic_vessels:
        # Get custom prices count for this vessel
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
        # Cache for 5 minutes
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
        
        # Authenticate user
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if user.is_active:
                login(request, user)
                
                # Restore language preference if exists
                preferred_language = request.session.get('preferred_language', 'en')
                request.session['preferred_language'] = preferred_language
                
                BilingualMessages.success(request, 'login_successful', username=user.username)
                
                # Redirect to intended page or dashboard
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
@user_passes_test(is_admin_or_manager)
def user_management(request):
    """Enhanced user management with statistics"""
    users = User.objects.all().order_by('username')
    groups = Group.objects.all().order_by('name')
    
    # Calculate statistics
    active_users_count = users.filter(is_active=True).count()
    staff_users_count = users.filter(is_staff=True).count()
    
    context = {
        'users': users,
        'groups': groups,
        'active_users_count': active_users_count,
        'staff_users_count': staff_users_count,
    }
    return render(request, 'frontend/auth/user_management.html', context)

@login_required
@user_passes_test(is_admin_or_manager)
def manage_user_groups(request, user_id):
    """Manage user group assignments"""
    if request.method == 'POST':
        # Get user safely
        user, error = CRUDHelper.safe_get_object(User, user_id, 'User')
        if error:
            return FormResponseHelper.error_redirect(
                request, 'frontend:user_management', 'User not found'
            )
        
        try:
            group_ids = request.POST.getlist('groups')
            
            # OPTIMIZED: Clear and set groups in single transaction
            with transaction.atomic():
                user.groups.clear()
                if group_ids:
                    groups = Group.objects.filter(id__in=group_ids)
                    user.groups.set(groups)
            
            return FormResponseHelper.success_redirect(
                request, 'frontend:user_management',
                'Groups updated for user "{username}"',
                username=user.username
            )
            
        except Exception as e:
            return FormResponseHelper.error_redirect(
                request, 'frontend:user_management',
                'Error updating groups: {error}', error=str(e)
            )
    
    return redirect('frontend:user_management')

@login_required
@user_passes_test(is_admin_or_manager)
def create_user(request):
    """Create new user with enhanced validation and group assignment"""
    if request.method == 'POST':
        try:
            # Extract data
            data = {
                'username': request.POST.get('username', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'first_name': request.POST.get('first_name', '').strip(),
                'last_name': request.POST.get('last_name', '').strip(),
                'password': request.POST.get('password'),
                'password_confirm': request.POST.get('password_confirm'),
                'is_active': request.POST.get('is_active') == 'on',
                'is_staff': request.POST.get('is_staff') == 'on',
                'group_ids': request.POST.getlist('groups')
            }
            
            # Validate required fields
            valid, error = ValidationHelper.validate_required_fields(
                data, ['username', 'password']
            )
            if not valid:
                return FormResponseHelper.error_redirect(
                    request, 'frontend:user_management', error.content.decode()
                )
            
            # Validate username
            valid, error = ValidationHelper.validate_username(data['username'])
            if not valid:
                return FormResponseHelper.error_redirect(
                    request, 'frontend:user_management', error.content.decode()
                )
            
            # Validate email if provided
            if data['email']:
                valid, error = ValidationHelper.validate_email(data['email'])
                if not valid:
                    return FormResponseHelper.error_redirect(
                        request, 'frontend:user_management', error.content.decode()
                    )
            
            # Validate password
            valid, error = ValidationHelper.validate_password_strength(
                data['password'], data['password_confirm']
            )
            if not valid:
                return FormResponseHelper.error_redirect(
                    request, 'frontend:user_management', error.content.decode()
                )
            
            # Create user with groups in single transaction
            with transaction.atomic():
                user = User.objects.create_user(
                    username=data['username'],
                    email=data['email'],
                    password=data['password'],
                    first_name=data['first_name'],
                    last_name=data['last_name'],
                    is_active=data['is_active'],
                    is_staff=data['is_staff']
                )
                
                # OPTIMIZED: Single query for groups instead of individual lookups
                if data['group_ids']:
                    groups = Group.objects.filter(id__in=data['group_ids'])
                    user.groups.set(groups)
            
            # Build success message
            group_names = list(user.groups.values_list('name', flat=True))
            group_info = f" and assigned to groups: {', '.join(group_names)}" if group_names else ""
            
            return FormResponseHelper.success_redirect(
                request, 'frontend:user_management',
                'User "{username}" created successfully{group_info}',
                username=data['username'], group_info=group_info
            )
            
        except Exception as e:
            return FormResponseHelper.error_redirect(
                request, 'frontend:user_management',
                'Error creating user: {error}', error=str(e)
            )
    
    return redirect('frontend:user_management')

# UPDATED: Enhanced edit_user view
@login_required
@user_passes_test(is_admin_or_manager)
def edit_user(request, user_id):
    """Edit existing user with group management"""
    # Get user safely
    user, error = CRUDHelper.safe_get_object(User, user_id, 'User')
    if error:
        return FormResponseHelper.error_redirect(
            request, 'frontend:user_management', 'User not found'
        )
    
    if request.method == 'POST':
        try:
            # Extract data
            data = {
                'username': request.POST.get('username', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'first_name': request.POST.get('first_name', '').strip(),
                'last_name': request.POST.get('last_name', '').strip(),
                'is_active': request.POST.get('is_active') == 'on',
                'is_staff': request.POST.get('is_staff') == 'on',
                'group_ids': request.POST.getlist('groups')
            }
            
            # Validate username
            valid, error = ValidationHelper.validate_username(data['username'], user.id)
            if not valid:
                return FormResponseHelper.error_redirect(
                    request, 'frontend:user_management', 
                    error.content.decode()
                )
            
            # Validate email if provided
            if data['email']:
                valid, error = ValidationHelper.validate_email(data['email'], user.id)
                if not valid:
                    return FormResponseHelper.error_redirect(
                        request, 'frontend:user_management',
                        error.content.decode()
                    )
            
            # Update user with groups in single transaction
            with transaction.atomic():
                # Update user fields
                user.username = data['username']
                user.email = data['email']
                user.first_name = data['first_name']
                user.last_name = data['last_name']
                user.is_active = data['is_active']
                user.is_staff = data['is_staff']
                user.save()
                
                # OPTIMIZED: Single query for groups
                if data['group_ids']:
                    groups = Group.objects.filter(id__in=data['group_ids'])
                    user.groups.set(groups)
                else:
                    user.groups.clear()
            
            # Build success message
            group_names = list(user.groups.values_list('name', flat=True))
            group_info = f" and assigned to groups: {', '.join(group_names)}" if group_names else ""
            
            return FormResponseHelper.success_redirect(
                request, 'frontend:user_management',
                'User "{username}" updated successfully{group_info}',
                username=data['username'], group_info=group_info
            )
            
        except Exception as e:
            return FormResponseHelper.error_redirect(
                request, 'frontend:user_management',
                'Error updating user: {error}', error=str(e)
            )
    
    return redirect('frontend:user_management')

# NEW: Reset user password
@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def reset_user_password(request, user_id):
    """Reset user password with generated temporary password"""
    # Get user safely
    user, error = CRUDHelper.safe_get_object(User, user_id, 'User')
    if error:
        return error
    
    try:
        # Generate random password
        alphabet = string.ascii_letters + string.digits
        new_password = ''.join(secrets.choice(alphabet) for i in range(12))
        
        # Set new password
        user.set_password(new_password)
        user.save()
        
        return JsonResponseHelper.success(
            message=f'Password reset for user "{user.username}"',
            new_password=new_password
        )
        
    except Exception as e:
        return JsonResponseHelper.error(str(e))

# NEW: Toggle user status (activate/deactivate)
@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def toggle_user_status(request, user_id):
    """Toggle user active status"""
    # Check self-action
    self_error = AdminActionHelper.prevent_self_action(request, user_id, 'deactivate')
    if self_error:
        return self_error
    
    # Get user safely
    user, error = CRUDHelper.safe_get_object(User, user_id, 'User')
    if error:
        return error
    
    # Toggle status with standardized response
    return CRUDHelper.toggle_boolean_field(user, 'is_active', 'User')

@login_required
def change_password(request):
    """Allow users to change their own password"""
    
    if request.method == 'POST':
        try:
            current_password = request.POST.get('current_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')
            
            # Validate current password
            if not request.user.check_password(current_password):
                BilingualMessages.error(request, 'current_password_incorrect')
                return render(request, 'frontend/auth/change_password.html')
            
            if len(new_password) < 6:
                BilingualMessages.error(request, 'password_too_short')
                return render(request, 'frontend/auth/change_password.html')
            
            if new_password != confirm_password:
                BilingualMessages.error(request, 'passwords_do_not_match')
                return render(request, 'frontend/auth/change_password.html')
            
            # Change password
            request.user.set_password(new_password)
            request.user.save()
            
            # Re-authenticate user
            user = authenticate(request, username=request.user.username, password=new_password)
            if user:
                login(request, user)
            
            BilingualMessages.success(request, 'password_changed_success')
            return redirect('frontend:dashboard')
            
        except Exception as e:
            BilingualMessages.error(request, 'error_changing_password', error=str(e))
    
    return render(request, 'frontend/auth/change_password.html')

@login_required
@user_passes_test(is_superuser_only)
def setup_groups(request):
    """Setup default groups with permissions"""
    if request.method == 'POST':
        try:
            # Default groups configuration
            default_groups = {
                'Administrators': [
                    'add_user', 'change_user', 'delete_user', 'view_user',
                    'add_group', 'change_group', 'delete_group', 'view_group',
                    'add_transaction', 'change_transaction', 'delete_transaction', 'view_transaction',
                    'add_product', 'change_product', 'delete_product', 'view_product',
                    'add_vessel', 'change_vessel', 'delete_vessel', 'view_vessel'
                ],
                'Managers': [
                    'view_user', 'change_user',
                    'add_transaction', 'change_transaction', 'view_transaction',
                    'add_product', 'change_product', 'view_product',
                    'view_vessel', 'change_vessel'
                ],
                'Vessel Operators': [
                    'add_transaction', 'view_transaction',
                    'view_product', 'view_vessel'
                ],
                'Inventory Staff': [
                    'view_transaction', 'add_product', 'change_product', 'view_product'
                ],
                'Viewers': [
                    'view_transaction', 'view_product', 'view_vessel'
                ]
            }
            
            created_groups = []
            
            # OPTIMIZED: Bulk operations instead of individual queries
            with transaction.atomic():
                # Get all permissions in single query
                all_permissions = {
                    perm.codename: perm 
                    for perm in Permission.objects.all()
                }
                
                for group_name, permission_names in default_groups.items():
                    # Create or get group
                    group, created = Group.objects.get_or_create(name=group_name)
                    
                    if created or not group.permissions.exists():
                        # OPTIMIZED: Set permissions in single operation
                        valid_permissions = [
                            all_permissions[perm_name] 
                            for perm_name in permission_names 
                            if perm_name in all_permissions
                        ]
                        
                        if valid_permissions:
                            group.permissions.set(valid_permissions)
                    
                    created_groups.append({
                        'name': group.name,
                        'created': created,
                        'permission_count': group.permissions.count()
                    })
            
            return JsonResponseHelper.success(
                message=f'Setup completed. Created/updated {len(created_groups)} groups',
                data={'groups': created_groups}
            )
            
        except Exception as e:
            return JsonResponseHelper.error(f'Error setting up groups: {str(e)}')
    
    return JsonResponseHelper.method_not_allowed(['POST'])

@login_required 
@user_passes_test(is_superuser_only)
def group_management(request):
    """Complete group management interface"""
    groups = Group.objects.all().order_by('name')
    
    # Calculate statistics for each group
    for group in groups:
        group.user_count = group.user_set.count()
        group.active_user_count = group.user_set.filter(is_active=True).count()
    
    # Overall statistics
    total_groups = groups.count()
    total_users_in_groups = User.objects.filter(groups__isnull=False).distinct().count()
    users_without_groups = User.objects.filter(groups__isnull=True).count()
    
    context = {
        'groups': groups,
        'stats': {
            'total_groups': total_groups,
            'total_users_in_groups': total_users_in_groups,
            'users_without_groups': users_without_groups,
        }
    }
    return render(request, 'frontend/auth/group_management.html', context)

@login_required
@user_passes_test(is_superuser_only)
def create_group(request):
    """Create new group with validation"""
    if request.method == 'POST':
        # Load JSON safely
        data, error = CRUDHelper.safe_json_load(request)
        if error:
            return error
        
        # Validate group data
        valid, error = ValidationHelper.validate_group_data(data)
        if not valid:
            return error
        
        try:
            # Create group
            group = Group.objects.create(name=data['name'].strip())
            
            return JsonResponseHelper.success(
                message=f'Group "{group.name}" created successfully',
                data={
                    'group': {
                        'id': group.id,
                        'name': group.name,
                        'user_count': 0
                    }
                }
            )
            
        except Exception as e:
            return JsonResponseHelper.error(str(e))
    
    return JsonResponseHelper.method_not_allowed(['POST'])

@login_required
@user_passes_test(is_superuser_only) 
def edit_group(request, group_id):
    """Edit existing group"""
    if request.method == 'GET':
        group, error = CRUDHelper.safe_get_object(Group, group_id, 'Group')
        if error:
            return error
            
        return JsonResponseHelper.success(data={
            'group': {
                'id': group.id,
                'name': group.name,
                'user_count': group.user_set.count(),
                'users': list(group.user_set.values('id', 'username'))
            }
        })
    
    elif request.method == 'POST':
        # Load JSON safely
        data, error = CRUDHelper.safe_json_load(request)
        if error:
            return error
        
        # Get group safely  
        group, error = CRUDHelper.safe_get_object(Group, group_id, 'Group')
        if error:
            return error
        
        # Validate group data
        valid, error = ValidationHelper.validate_group_data(data, group_id)
        if not valid:
            return error
        
        # Update group
        old_name = group.name
        group.name = data['name'].strip()
        group.save()
        
        return JsonResponseHelper.success(
            message=f'Group renamed from "{old_name}" to "{group.name}"',
            data={
                'group': {
                    'id': group.id,
                    'name': group.name,
                    'user_count': group.user_set.count()
                }
            }
        )
    
    return JsonResponseHelper.method_not_allowed(['GET', 'POST'])

@login_required
@user_passes_test(is_superuser_only)
@require_http_methods(["DELETE"])
def delete_group(request, group_id):
    """Delete group with confirmation"""
    # Get group safely
    group, error = CRUDHelper.safe_get_object(Group, group_id, 'Group')
    if error:
        return error
    
    # Check force delete
    force_delete = AdminActionHelper.check_force_delete(request)
    
    # OPTIMIZED: Single query to get user count and info
    users_info = list(group.user_set.values('username', 'is_active'))
    user_count = len(users_info)
    
    if user_count > 0 and not force_delete:
        return JsonResponseHelper.requires_confirmation(
            message=f'Group "{group.name}" has {user_count} users. Remove users and delete group?',
            confirmation_data={
                'user_count': user_count,
                'users': users_info
            }
        )
    
    try:
        group_name = group.name
        
        # OPTIMIZED: Clear users and delete in single transaction
        with transaction.atomic():
            group.user_set.clear()
            group.delete()
        
        return JsonResponseHelper.success(
            message=f'Group "{group_name}" and user assignments deleted successfully'
        )
        
    except Exception as e:
        return JsonResponseHelper.error(str(e))

@login_required
@user_passes_test(is_superuser_only)
def group_details(request, group_id):
    """Get detailed group information"""
    # Get group safely with optimized user data
    try:
        # OPTIMIZED: Single query with user data prefetch
        group = Group.objects.prefetch_related(
            'user_set__groups'  # Prefetch user groups for better performance
        ).get(id=group_id)
        
        # OPTIMIZED: Build user list without additional queries
        users_data = []
        for user in group.user_set.all():
            user_groups = [g.name for g in user.groups.all()]  # Uses prefetched data
            users_data.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_active': user.is_active,
                'is_staff': user.is_staff,
                'groups': user_groups,
                'last_login': user.last_login.strftime('%d/%m/%Y %H:%M') if user.last_login else 'Never'
            })
        
        return JsonResponseHelper.success(data={
            'group': {
                'id': group.id,
                'name': group.name,
                'user_count': len(users_data),
                'users': users_data,
                'permissions': list(group.permissions.values_list('name', flat=True))
            }
        })
        
    except Group.DoesNotExist:
        return JsonResponseHelper.not_found('Group')
    except Exception as e:
        return JsonResponseHelper.error(str(e))

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
    
# Update frontend/auth_views.py - Clean up the vessel_management and vessel_data_ajax views

@login_required
@user_passes_test(is_admin_or_manager)
def vessel_management(request):
    """CLEANED: Vessel management - removed unused pricing warnings collection"""
    
    # Date handling for 30-day revenue calculation
    reference_date = date.today()
    thirty_days_ago = reference_date - timedelta(days=30)
    
    # FIXED: Single query with correct relationship names
    vessels_data = Vessel.objects.annotate(
        total_trips=Count(
            'trips', 
            filter=models.Q(trips__is_completed=True),
            distinct=True
        ),
        trips_30d=Count(
            'trips',
            filter=models.Q(
                trips__is_completed=True,
                trips__trip_date__gte=thirty_days_ago,
                trips__trip_date__lte=reference_date
            ),
            distinct=True
        ),
        # Revenue calculations - FIXED: using 'transactions' instead of 'transaction_set'
        revenue_30d=models.Sum(
            models.Case(
                models.When(
                    transactions__transaction_type='SALE',
                    transactions__transaction_date__gte=thirty_days_ago,
                    transactions__transaction_date__lte=reference_date,
                    then=models.F('transactions__unit_price') * models.F('transactions__quantity')
                ),
                default=0,
                output_field=models.DecimalField()
            )
        ),
        # Passenger statistics - FIXED: using 'trips' instead of 'trip_set'
        total_passengers_30d=models.Sum(
            'trips__passenger_count',
            filter=models.Q(
                trips__is_completed=True,
                trips__trip_date__gte=thirty_days_ago,
                trips__trip_date__lte=reference_date
            )
        )
    ).order_by('name')
    
    # FIXED: Get overall statistics with correct field names
    vessel_stats = vessels_data.aggregate(
        total_vessels=Count('id'),
        active_vessels=Count('id', filter=models.Q(active=True)),
        duty_free_vessels=Count('id', filter=models.Q(has_duty_free=True)),
        inactive_vessels=Count('id', filter=models.Q(active=False))
    )
    
    # Get pricing summary with caching (KEEP THIS - needed for the single warning)
    pricing_summary = get_all_vessel_pricing_summary()
    
    # Build vessel data with optimized pricing
    vessel_data = []
    
    for vessel in vessels_data:
        # Get pricing warnings (still needed for individual vessel cards)
        pricing_warnings = get_vessel_pricing_warnings(vessel)
        
        # Calculate pricing completion data
        if vessel.has_duty_free:
            pricing_data = {
                'is_duty_free': True,
                'completion_percentage': 100,
                'products_priced': 0,
                'total_products': 0
            }
        else:
            total_general_products = pricing_summary['total_general_products']
            missing_count = pricing_warnings['missing_price_count']
            products_priced = total_general_products - missing_count
            completion_pct = (products_priced / max(total_general_products, 1)) * 100
            
            pricing_data = {
                'is_duty_free': False,
                'completion_percentage': round(completion_pct, 0),
                'products_priced': products_priced,
                'total_products': total_general_products
            }
        
        vessel_data.append({
            'vessel': vessel,
            'trips_30d': vessel.trips_30d or 0,
            'total_trips': vessel.total_trips or 0,
            'revenue_30d': float(vessel.revenue_30d or 0),
            'total_passengers_30d': vessel.total_passengers_30d or 0,
            'pricing_warnings': pricing_warnings,
            'pricing_data': pricing_data,
        })
    
    # CLEANED: Removed overall_pricing_warnings and vessel_warnings_summary collection
    context = {
        'vessel_data': vessel_data,
        'stats': vessel_stats,
        'pricing_summary': pricing_summary,  # KEEP THIS - needed for single warning
        'reference_date': reference_date,
        'thirty_days_ago': thirty_days_ago,
        'today': date.today(),
    }
    
    return render(request, 'frontend/auth/vessel_management.html', context)

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def vessel_data_ajax(request):
    """CLEANED: AJAX endpoint - removed unused pricing warnings"""
    
    try:
        data = json.loads(request.body)
        selected_date = data.get('date')
        
        if not selected_date:
            return JsonResponse({'success': False, 'error': 'Date required'})
        
        reference_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        thirty_days_ago = reference_date - timedelta(days=30)
        
        # FIXED: Single query with correct relationship names
        vessels_data = Vessel.objects.annotate(
            total_trips=Count(
                'trips', 
                filter=models.Q(trips__is_completed=True),
                distinct=True
            ),
            trips_30d=Count(
                'trips',
                filter=models.Q(
                    trips__is_completed=True,
                    trips__trip_date__gte=thirty_days_ago,
                    trips__trip_date__lte=reference_date
                ),
                distinct=True
            ),
            revenue_30d=models.Sum(
                models.Case(
                    models.When(
                        transactions__transaction_type='SALE',
                        transactions__transaction_date__gte=thirty_days_ago,
                        transactions__transaction_date__lte=reference_date,
                        then=models.F('transactions__unit_price') * models.F('transactions__quantity')
                    ),
                    default=0,
                    output_field=models.DecimalField()
                )
            ),
            total_passengers_30d=models.Sum(
                'trips__passenger_count',
                filter=models.Q(
                    trips__is_completed=True,
                    trips__trip_date__gte=thirty_days_ago,
                    trips__trip_date__lte=reference_date
                )
            )
        ).order_by('name')
        
        # Convert to list format
        vessel_data = list(vessels_data.values(
            'id', 'name', 'name_ar', 'has_duty_free', 'active',
            'trips_30d', 'total_trips', 'revenue_30d', 'total_passengers_30d'
        ))
        
        # Clean up the data
        for vessel in vessel_data:
            vessel['vessel_id'] = vessel.pop('id')
            vessel['vessel_name'] = vessel.pop('name')
            vessel['vessel_name_ar'] = vessel.pop('name_ar')
            vessel['revenue_30d'] = float(vessel['revenue_30d'] or 0)
            vessel['trips_30d'] = vessel['trips_30d'] or 0
            vessel['total_trips'] = vessel['total_trips'] or 0
            vessel['total_passengers_30d'] = vessel['total_passengers_30d'] or 0
        
        # CLEANED: Removed pricing warnings collection since we don't use them in AJAX
        return JsonResponse({
            'success': True,
            'vessel_data': vessel_data,
            'reference_date': reference_date.strftime('%Y-%m-%d'),
            'date_range': f"{thirty_days_ago.strftime('%d/%m/%Y')} - {reference_date.strftime('%d/%m/%Y')}",
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_admin_or_manager)
def create_vessel(request):
    """Create new vessel with validation"""
    if request.method == 'POST':
        # Extract data
        data = {
            'name': request.POST.get('name', '').strip(),
            'name_ar': request.POST.get('name_ar', '').strip(),
            'has_duty_free': request.POST.get('has_duty_free') == 'on',
            'active': request.POST.get('active') == 'on'
        }
        
        # Validate vessel data
        valid, error = ValidationHelper.validate_vessel_data(data)
        if not valid:
            return error
        
        try:
            # Create vessel
            vessel = Vessel.objects.create(
                name=data['name'],
                name_ar=data['name_ar'],
                has_duty_free=data['has_duty_free'],
                active=data['active'],
                created_by=request.user
            )
            
            return JsonResponseHelper.success(
                message=f'Vessel "{vessel.name}" created successfully',
                data={
                    'vessel_id': vessel.id,
                    'vessel_name': vessel.name
                }
            )
            
        except Exception as e:
            return JsonResponseHelper.error(str(e))
    
    return JsonResponseHelper.method_not_allowed(['POST'])

@login_required
@user_passes_test(is_admin_or_manager)
def edit_vessel(request, vessel_id):
    """Edit existing vessel"""
    if request.method == 'POST':
        # Get vessel safely
        vessel, error = CRUDHelper.safe_get_object(Vessel, vessel_id, 'Vessel')
        if error:
            return error
        
        # Extract data
        data = {
            'name': request.POST.get('name', '').strip(),
            'name_ar': request.POST.get('name_ar', '').strip(),
            'has_duty_free': request.POST.get('has_duty_free') == 'on',
            'active': request.POST.get('active') == 'on'
        }
        
        # Validate vessel data
        valid, error = ValidationHelper.validate_vessel_data(data, vessel.id)
        if not valid:
            return error
        
        try:
            # Update vessel
            vessel.name = data['name']
            vessel.name_ar = data['name_ar'] 
            vessel.has_duty_free = data['has_duty_free']
            vessel.active = data['active']
            vessel.save()
            
            return JsonResponseHelper.success(
                message=f'Vessel "{vessel.name}" updated successfully',
                vessel_name=vessel.name
            )
            
        except Exception as e:
            return JsonResponseHelper.error(str(e))
    
    return JsonResponseHelper.method_not_allowed(['POST'])

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def toggle_vessel_status(request, vessel_id):
    """Toggle vessel active status"""
    # Get vessel safely
    vessel, error = CRUDHelper.safe_get_object(Vessel, vessel_id, 'Vessel')
    if error:
        return error
    
    # Check if vessel has active transactions before deactivating
    if vessel.active:  # If currently active and we're deactivating
        # OPTIMIZED: Single query to check incomplete items
        incomplete_counts = {
            'incomplete_trips': Trip.objects.filter(vessel=vessel, is_completed=False).count(),
            'incomplete_pos': PurchaseOrder.objects.filter(vessel=vessel, is_completed=False).count()
        }
        
        total_incomplete = sum(incomplete_counts.values())
        if total_incomplete > 0:
            return JsonResponseHelper.error(
                f'Cannot deactivate vessel. Has {incomplete_counts["incomplete_trips"]} incomplete trips and {incomplete_counts["incomplete_pos"]} incomplete purchase orders.'
            )
    
    # Toggle status
    return CRUDHelper.toggle_boolean_field(vessel, 'active', 'Vessel')

@login_required
@user_passes_test(is_admin_or_manager)
def vessel_statistics(request, vessel_id):
    """Get detailed vessel statistics - OPTIMIZED VERSION"""
    # Get vessel safely
    vessel, error = CRUDHelper.safe_get_object(Vessel, vessel_id, 'Vessel')
    if error:
        return error
    
    try:
        # Calculate date ranges once
        today = timezone.now().date()
        thirty_days_ago = today - timedelta(days=30)
        ninety_days_ago = today - timedelta(days=90)
        
        # HEAVILY OPTIMIZED: Single query for all trip statistics
        trip_stats = Trip.objects.filter(vessel=vessel).aggregate(
            total_trips=Count('id', filter=Q(is_completed=True)),
            trips_30d=Count('id', filter=Q(
                trip_date__gte=thirty_days_ago, 
                is_completed=True
            )),
            total_passengers=Sum('passenger_count', filter=Q(is_completed=True))
        )
        
        # HEAVILY OPTIMIZED: Single query for all transaction statistics
        transaction_stats = Transaction.objects.filter(
            vessel=vessel, transaction_type='SALE'
        ).aggregate(
            total_revenue=Sum(
                F('unit_price') * F('quantity'), 
                output_field=models.DecimalField()
            ),
            revenue_30d=Sum(
                F('unit_price') * F('quantity'),
                filter=Q(transaction_date__gte=thirty_days_ago),
                output_field=models.DecimalField()
            ),
            transaction_count_90d=Count('id', filter=Q(
                transaction_date__gte=ninety_days_ago
            ))
        )
        
        # Set defaults for None values
        for key in trip_stats:
            if trip_stats[key] is None:
                trip_stats[key] = 0
                
        for key in transaction_stats:
            if transaction_stats[key] is None:
                transaction_stats[key] = 0
        
        # Calculate derived metrics
        avg_revenue_per_passenger = (
            transaction_stats['total_revenue'] / max(trip_stats['total_passengers'], 1)
        )
        
        # OPTIMIZED: Single query for top products (last 90 days)
        top_products = list(Transaction.objects.filter(
            vessel=vessel,
            transaction_type='SALE',
            transaction_date__gte=ninety_days_ago
        ).values('product__name').annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum(
                F('unit_price') * F('quantity'), 
                output_field=models.DecimalField()
            )
        ).order_by('-total_quantity')[:10])
        
        # OPTIMIZED: Monthly performance with single query
        monthly_performance = []
        
        # Build month ranges
        month_ranges = []
        for i in range(11, -1, -1):
            month_date = today - timedelta(days=i*30)
            month_start = date(month_date.year, month_date.month, 1)
            
            if month_date.month == 12:
                month_end = date(month_date.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(month_date.year, month_date.month + 1, 1) - timedelta(days=1)
            
            month_ranges.append((month_date, month_start, month_end))
        
        # Single query for all monthly data
        monthly_transactions = Transaction.objects.filter(
            vessel=vessel,
            transaction_type='SALE',
            transaction_date__gte=month_ranges[0][1],  # Earliest month start
            transaction_date__lte=month_ranges[-1][2]   # Latest month end
        ).values('transaction_date').annotate(
            monthly_revenue=Sum(
                F('unit_price') * F('quantity'), 
                output_field=models.DecimalField()
            )
        )
        
        # Group by month
        monthly_data = {}
        for txn in monthly_transactions:
            month_key = txn['transaction_date'].strftime('%Y-%m')
            if month_key not in monthly_data:
                monthly_data[month_key] = 0
            monthly_data[month_key] += float(txn['monthly_revenue'] or 0)
        
        # Build response
        for month_date, month_start, month_end in month_ranges:
            month_key = month_start.strftime('%Y-%m')
            monthly_performance.append({
                'month': month_date.strftime('%b %Y'),
                'revenue': monthly_data.get(month_key, 0)
            })
        
        return JsonResponseHelper.success(data={
            'vessel': {
                'name': vessel.name,
                'name_ar': vessel.name_ar,
                'has_duty_free': vessel.has_duty_free,
                'active': vessel.active,
            },
            'statistics': {
                'total_trips': trip_stats['total_trips'],
                'trips_30d': trip_stats['trips_30d'],
                'total_revenue': float(transaction_stats['total_revenue']),
                'revenue_30d': float(transaction_stats['revenue_30d']),
                'total_passengers': trip_stats['total_passengers'],
                'avg_revenue_per_passenger': float(avg_revenue_per_passenger),
            },
            'top_products': top_products,
            'monthly_performance': monthly_performance,
        })
        
    except Exception as e:
        return JsonResponseHelper.error(str(e))
    
@login_required
@user_passes_test(is_admin_or_manager)
def po_management(request):
    """WORKING: PO management with template-required annotations"""
    
    # WORKING: Base queryset with template-required annotations
    purchase_orders = PurchaseOrder.objects.select_related(
        'vessel',           
        'created_by'        
    ).prefetch_related(
        'supply_transactions__product'  
    ).annotate(
        # These are the fields the template expects
        annotated_total_cost=Sum(
            F('supply_transactions__unit_price') * F('supply_transactions__quantity'),
            output_field=models.DecimalField()
        ),
        annotated_transaction_count=Count('supply_transactions'),
    )
    
    # Apply all filters using helper with custom field mappings
    purchase_orders = TransactionQueryHelper.apply_common_filters(
        purchase_orders, request,
        date_field='po_date',             # POs use po_date not transaction_date
        status_field='is_completed'       # Enable status filtering for POs
    )
    
    # Order for consistent results
    purchase_orders = purchase_orders.order_by('-po_date', '-created_at')
    
    # WORKING: Add cost performance class to each PO (for template)
    po_list = list(purchase_orders[:50])

    # WORKING: Simple statistics using separate queries
    po_stats = PurchaseOrder.objects.aggregate(
        total_pos=Count('id'),
        completed_pos=Count('id', filter=Q(is_completed=True)),
        in_progress_pos=Count('id', filter=Q(is_completed=False))
    )

    # Calculate financial statistics
    financial_stats = Transaction.objects.filter(
        transaction_type='SUPPLY',
        purchase_order__isnull=False
    ).aggregate(
        total_procurement_value=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField()),
        total_transactions=Count('id'),
        avg_po_value=Avg(F('unit_price') * F('quantity'), output_field=models.DecimalField())
    )

    # Set defaults for financial stats
    for key in ['total_procurement_value', 'total_transactions', 'avg_po_value']:
        if financial_stats[key] is None:
            financial_stats[key] = 0

    # Calculate completion rate
    total_pos = po_stats['total_pos'] or 1  # Avoid division by zero
    completed_pos = po_stats['completed_pos'] or 0
    completion_rate = (completed_pos / total_pos) * 100

    # Get top vessels by PO activity (simplified)
    top_vessels = Vessel.objects.filter(active=True).annotate(
        po_count=Count('purchase_orders')
    ).filter(po_count__gt=0).order_by('-po_count')[:5]

    # Recent activity
    recent_pos = PurchaseOrder.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7)
    )
    recent_pos_count = recent_pos.count()
    recent_value = recent_pos.aggregate(
        total=Sum(F('supply_transactions__unit_price') * F('supply_transactions__quantity'))
    )['total'] or 0

    # Get vessels for filter using helper
    vessels_for_filter = TransactionQueryHelper.get_vessels_for_filter()

    context = {
        'purchase_orders': po_list,
        'vessels': vessels_for_filter,
        'top_vessels': top_vessels,  # Simplified but functional
        'stats': {
            # Basic counts
            'total_pos': po_stats['total_pos'] or 0,
            'completed_pos': po_stats['completed_pos'] or 0,
            'in_progress_pos': po_stats['in_progress_pos'] or 0,
            'completion_rate': round(completion_rate, 1),
            
            # Financial metrics
            'total_procurement_value': financial_stats['total_procurement_value'],
            'avg_po_value': round(financial_stats['avg_po_value'], 2),
            
            # Transaction metrics
            'total_transactions': financial_stats['total_transactions'],
            'avg_transactions_per_po': round(
                financial_stats['total_transactions'] / max(po_stats['total_pos'], 1), 1
            ),
        },
        'recent_activity': {
            'recent_pos': recent_pos_count,
            'recent_value': recent_value,
        }
    }
    
    # Add filter context using helper
    context.update(TransactionQueryHelper.get_filter_context(request))
    
    return render(request, 'frontend/auth/po_management.html', context)

@login_required
@user_passes_test(is_admin_or_manager)
def edit_po(request, po_id):
    """Edit PO details"""
    if request.method == 'GET':
        # Get PO safely
        po, error = CRUDHelper.safe_get_object(PurchaseOrder, po_id, 'Purchase Order')
        if error:
            return error
            
        return JsonResponseHelper.success(data={
            'po': {
                'id': po.id,
                'po_number': po.po_number,
                'po_date': po.po_date.strftime('%Y-%m-%d'),
                'notes': po.notes or '',
                'vessel_id': po.vessel.id,
                'vessel_name': po.vessel.name,
            }
        })
    
    elif request.method == 'POST':
        # Load JSON safely
        data, error = CRUDHelper.safe_json_load(request)
        if error:
            return error
        
        # Get PO safely
        po, error = CRUDHelper.safe_get_object(PurchaseOrder, po_id, 'Purchase Order')
        if error:
            return error
        
        try:
            # Update PO fields
            if 'po_date' in data:
                po.po_date = datetime.strptime(data['po_date'], '%Y-%m-%d').date()
            
            if 'notes' in data:
                po.notes = data['notes']
            
            po.save()
            
            return JsonResponseHelper.success(
                message=f'Purchase Order {po.po_number} updated successfully'
            )
            
        except (ValueError, ValidationError) as e:
            return JsonResponseHelper.error(f'Invalid data: {str(e)}')
        except Exception as e:
            return JsonResponseHelper.error(str(e))

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["DELETE"])
def delete_po(request, po_id):
    """Delete PO with cascade option for transactions"""
    # Get PO safely
    po, error = CRUDHelper.safe_get_object(PurchaseOrder, po_id, 'Purchase Order')
    if error:
        return error
    
    # Check force delete
    force_delete = AdminActionHelper.check_force_delete(request)
    
    # OPTIMIZED: Get transaction info in single query
    transactions_info = list(po.supply_transactions.select_related('product').values(
        'product__name', 'quantity', 'unit_price'
    ))
    
    transaction_count = len(transactions_info)
    
    if transaction_count > 0 and not force_delete:
        # Calculate total for confirmation
        total_cost = sum(
            float(txn['quantity']) * float(txn['unit_price'])
            for txn in transactions_info
        )
        
        return JsonResponseHelper.requires_confirmation(
            message=f'This PO has {transaction_count} supply transactions. Delete anyway?',
            confirmation_data={
                'transaction_count': transaction_count,
                'total_cost': total_cost,
                'transactions': transactions_info
            }
        )
    
    try:
        po_number = po.po_number
        
        if transaction_count > 0:
            # OPTIMIZED: Bulk operations in transaction
            with transaction.atomic():
                # Delete all related transactions  
                po.supply_transactions.all().delete()
                po.delete()
            
            return JsonResponseHelper.success(
                message=f'PO {po_number} and all {transaction_count} transactions deleted successfully. Inventory removed.'
            )
        else:
            # No transactions, safe to delete
            po.delete()
            return JsonResponseHelper.success(
                message=f'PO {po_number} deleted successfully'
            )
        
    except Exception as e:
        return JsonResponseHelper.error(str(e))

@login_required
@user_passes_test(is_admin_or_manager)
def toggle_po_status(request, po_id):
    """Toggle PO completion status"""
    if request.method == 'POST':
        # Get PO safely
        po, error = CRUDHelper.safe_get_object(PurchaseOrder, po_id, 'Purchase Order')
        if error:
            return error
        
        # Toggle status with standardized response
        return CRUDHelper.toggle_boolean_field(po, 'is_completed', 'Purchase Order')

@login_required
@user_passes_test(is_admin_or_manager)
def trip_management(request):
    """FIXED: Trip management with resolved property conflicts"""
    
    # Get filter parameters
    vessel_filter = request.GET.get('vessel')
    status_filter = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    min_revenue = request.GET.get('min_revenue')
    
    # FIXED: Use different annotation names to avoid conflicts
    trips_query = Trip.objects.select_related(
        'vessel', 'created_by'
    ).prefetch_related(
        'sales_transactions'
    ).annotate(
        # Use different names to avoid property conflicts
        annotated_total_revenue=Sum(
            F('sales_transactions__unit_price') * F('sales_transactions__quantity'),
            output_field=models.DecimalField()
        ),
        annotated_transaction_count=Count('sales_transactions'),
        # Calculate revenue per passenger
        revenue_per_passenger=models.Case(
            models.When(
                passenger_count__gt=0, 
                then=F('annotated_total_revenue') / F('passenger_count')
            ),
            default=0,
            output_field=models.DecimalField()
        ),
        # Performance classification
        revenue_performance_class=models.Case(
            models.When(revenue_per_passenger__gte=50, then=models.Value('high')),
            models.When(revenue_per_passenger__gte=25, then=models.Value('medium')),
            default=models.Value('low'),
            output_field=models.CharField()
        )
    ).order_by('-trip_date', '-created_at')
    
    # Apply filters
    if vessel_filter:
        trips_query = trips_query.filter(vessel_id=vessel_filter)
    if status_filter == 'completed':
        trips_query = trips_query.filter(is_completed=True)
    elif status_filter == 'in_progress':
        trips_query = trips_query.filter(is_completed=False)
    if date_from:
        trips_query = trips_query.filter(trip_date__gte=date_from)
    if date_to:
        trips_query = trips_query.filter(trip_date__lte=date_to)
    if min_revenue:
        trips_query = trips_query.filter(annotated_total_revenue__gte=min_revenue)
    
    # FIXED: Statistics using the annotation names
    stats = trips_query.aggregate(
        total_trips=Count('id'),
        completed_trips=Count('id', filter=models.Q(is_completed=True)),
        total_revenue=Sum('annotated_total_revenue'),
        avg_daily_trips=Count('id') / 30.0
    )
    
    stats['in_progress_trips'] = stats['total_trips'] - stats['completed_trips']
    stats['completion_rate'] = (stats['completed_trips'] / max(stats['total_trips'], 1)) * 100
    
    # Vessel performance (keep as separate query)
    vessel_performance = Trip.objects.values(
        'vessel__name', 'vessel__name_ar'
    ).annotate(
        trip_count=Count('id'),
        avg_monthly=Count('id') / 12.0,
        vessel_total_revenue=Sum(
            F('sales_transactions__unit_price') * F('sales_transactions__quantity'),
            output_field=models.DecimalField()
        ),
        performance_class=models.Case(
            models.When(avg_monthly__gte=10, then=models.Value('high')),
            models.When(avg_monthly__gte=5, then=models.Value('medium')),
            default=models.Value('low'),
            output_field=models.CharField()
        ),
        performance_icon=models.Case(
            models.When(avg_monthly__gte=10, then=models.Value('arrow-up-circle')),
            models.When(avg_monthly__gte=5, then=models.Value('dash-circle')),
            default=models.Value('arrow-down-circle'),
            output_field=models.CharField()
        ),
        badge_class=models.Case(
            models.When(avg_monthly__gte=10, then=models.Value('bg-success')),
            models.When(avg_monthly__gte=5, then=models.Value('bg-warning')),
            default=models.Value('bg-danger'),
            output_field=models.CharField()
        )
    ).order_by('-trip_count')
    
    context = {
        'trips': trips_query[:50],  # Limit for performance
        'vessels': Vessel.objects.filter(active=True).order_by('name'),
        'vessel_performance': vessel_performance,
        'stats': {
            'total_trips': stats['total_trips'],
            'completed_trips': stats['completed_trips'],
            'in_progress_trips': stats['in_progress_trips'],
            'total_revenue': stats['total_revenue'] or 0,
            'daily_average': round(stats['avg_daily_trips'], 1),
            'completion_rate': round(stats['completion_rate'], 1),
        },
        'filters': {
            'vessel': vessel_filter,
            'status': status_filter,
            'date_from': date_from,
            'date_to': date_to,
            'min_revenue': min_revenue,
        }
    }
    
    return render(request, 'frontend/auth/trip_management.html', context)

@login_required
@user_passes_test(is_admin_or_manager)
def edit_trip(request, trip_id):
    """Edit trip details"""
    if request.method == 'GET':
        # Get trip safely with vessel data
        trip, error = CRUDHelper.safe_get_object(Trip, trip_id, 'Trip')
        if error:
            return error
            
        return JsonResponseHelper.success(data={
            'trip': {
                'id': trip.id,
                'trip_number': trip.trip_number,
                'passenger_count': trip.passenger_count,
                'trip_date': trip.trip_date.strftime('%Y-%m-%d'),
                'notes': trip.notes or '',
                'vessel_id': trip.vessel.id,
                'vessel_name': trip.vessel.name,
            }
        })
    
    elif request.method == 'POST':
        # Load JSON safely
        data, error = CRUDHelper.safe_json_load(request)
        if error:
            return error
        
        # Get trip safely
        trip, error = CRUDHelper.safe_get_object(Trip, trip_id, 'Trip')
        if error:
            return error
        
        try:
            # Update trip fields with validation
            if 'passenger_count' in data:
                passenger_count = int(data['passenger_count'])
                if passenger_count <= 0:
                    return JsonResponseHelper.error('Passenger count must be positive')
                trip.passenger_count = passenger_count
            
            if 'trip_date' in data:
                trip.trip_date = datetime.strptime(data['trip_date'], '%Y-%m-%d').date()
            
            if 'notes' in data:
                trip.notes = data['notes']
            
            trip.save()
            
            return JsonResponseHelper.success(
                message=f'Trip {trip.trip_number} updated successfully'
            )
            
        except (ValueError, ValidationError) as e:
            return JsonResponseHelper.error(f'Invalid data: {str(e)}')
        except Exception as e:
            return JsonResponseHelper.error(str(e))

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["DELETE"])
def delete_trip(request, trip_id):
    """Delete trip with cascade option for transactions"""
    # Get trip safely
    trip, error = CRUDHelper.safe_get_object(Trip, trip_id, 'Trip')
    if error:
        return error
    
    # Check force delete
    force_delete = AdminActionHelper.check_force_delete(request)
    
    # OPTIMIZED: Get transaction info in single query
    transactions_info = list(trip.sales_transactions.select_related('product').values(
        'product__name', 'quantity', 'unit_price'
    ))
    
    transaction_count = len(transactions_info)
    
    if transaction_count > 0 and not force_delete:
        # Calculate total for confirmation
        total_revenue = sum(
            float(txn['quantity']) * float(txn['unit_price']) 
            for txn in transactions_info
        )
        
        return JsonResponseHelper.requires_confirmation(
            message=f'This trip has {transaction_count} sales transactions. Delete anyway?',
            confirmation_data={
                'transaction_count': transaction_count,
                'total_revenue': total_revenue,
                'transactions': transactions_info
            }
        )
    
    try:
        trip_number = trip.trip_number
        
        if transaction_count > 0:
            # OPTIMIZED: Bulk operations in transaction
            with transaction.atomic():
                # Delete all related transactions
                trip.sales_transactions.all().delete()
                trip.delete()
            
            return JsonResponseHelper.success(
                message=f'Trip {trip_number} and all {transaction_count} transactions deleted successfully. Inventory restored.'
            )
        else:
            # No transactions, safe to delete
            trip.delete()
            return JsonResponseHelper.success(
                message=f'Trip {trip_number} deleted successfully'
            )
        
    except Exception as e:
        return JsonResponseHelper.error(str(e))

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def toggle_trip_status(request, trip_id):
    """Toggle trip completion status"""
    # Get trip safely
    trip, error = CRUDHelper.safe_get_object(Trip, trip_id, 'Trip')
    if error:
        return error
    
    # Toggle status with standardized response
    return CRUDHelper.toggle_boolean_field(trip, 'is_completed', 'Trip')

@login_required
@user_passes_test(is_admin_or_manager)
def trip_details(request, trip_id):
    """Get detailed trip information - OPTIMIZED VERSION"""
    try:
        # OPTIMIZED: Single query with all related data
        trip = Trip.objects.select_related(
            'vessel', 'created_by'
        ).prefetch_related(
            'sales_transactions__product'  # Prefetch product data
        ).get(id=trip_id)
        
        # OPTIMIZED: Use prefetched data instead of separate queries
        sales_transactions = trip.sales_transactions.all()  # Uses prefetched data
        
        # Calculate statistics using prefetched data (no additional queries)
        total_revenue = trip.total_revenue  # Uses property with prefetched data
        total_items = sum(sale.quantity for sale in sales_transactions)
        revenue_per_passenger = total_revenue / max(trip.passenger_count, 1)
        
        # Build sales breakdown using prefetched data
        sales_breakdown = []
        for sale in sales_transactions:
            sales_breakdown.append({
                'product_name': sale.product.name,  # Uses prefetched data
                'quantity': float(sale.quantity),
                'unit_price': float(sale.unit_price),
                'total_amount': float(sale.total_amount),
            })
        
        return JsonResponseHelper.success(data={
            'trip': {
                'trip_number': trip.trip_number,
                'vessel_name': trip.vessel.name,  # Uses select_related data
                'vessel_name_ar': trip.vessel.name_ar,
                'trip_date': trip.trip_date.strftime('%d/%m/%Y'),
                'passenger_count': trip.passenger_count,
                'is_completed': trip.is_completed,
                'created_by': trip.created_by.username if trip.created_by else 'System',
                'notes': trip.notes,
            },
            'statistics': {
                'total_revenue': float(total_revenue),
                'total_items': total_items,
                'revenue_per_passenger': float(revenue_per_passenger),
            },
            'sales_breakdown': sales_breakdown,
        })
        
    except Trip.DoesNotExist:
        return JsonResponseHelper.not_found('Trip')
    except Exception as e:
        return JsonResponseHelper.error(str(e))

@login_required
@user_passes_test(is_admin_or_manager)
def po_details(request, po_id):
    """Get detailed PO information"""
    
    try:
        po = get_object_or_404(PurchaseOrder, id=po_id)
        
        # Get PO supplies
        supply_transactions = po.supply_transactions.select_related('product').order_by('created_at')
        
        # Calculate statistics
        total_cost = po.total_cost
        total_items = supply_transactions.count()
        avg_cost_per_item = total_cost / max(total_items, 1)
        
        # Items breakdown
        items_breakdown = []
        for supply in supply_transactions:
            items_breakdown.append({
                'product_name': supply.product.name,
                'quantity_ordered': float(supply.quantity),
                'quantity_received': float(supply.quantity),  # Assuming fully received
                'unit_cost': float(supply.unit_price),
                'total_cost': float(supply.total_amount),
            })
        
        return JsonResponse({
            'success': True,
            'po': {
                'po_number': po.po_number,
                'vessel_name': po.vessel.name,
                'vessel_name_ar': po.vessel.name_ar,
                'po_date': po.po_date.strftime('%d/%m/%Y'),
                'is_completed': po.is_completed,
                'created_by': po.created_by.username if po.created_by else 'System',
                'notes': po.notes,
                'supplier': 'Marina Supply Co.',  # Mock - implement supplier tracking
            },
            'statistics': {
                'total_cost': float(total_cost),
                'total_items': total_items,
                'avg_cost_per_item': float(avg_cost_per_item),
            },
            'items_breakdown': items_breakdown,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})