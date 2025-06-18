from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group, Permission
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction, models
from django.db.models import Sum, F, Count, Q, Avg
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
        try:
            user = get_object_or_404(User, id=user_id)
            group_ids = request.POST.getlist('groups')
            
            # Clear existing groups and add new ones
            user.groups.clear()
            if group_ids:
                groups = Group.objects.filter(id__in=group_ids)
                user.groups.set(groups)
            
            messages.success(request, f'Groups updated for user "{user.username}"')
            return redirect('frontend:user_management')
            
        except Exception as e:
            messages.error(request, f'Error updating groups: {str(e)}')
            return redirect('frontend:user_management')
    
    return redirect('frontend:user_management')

@login_required
@user_passes_test(is_admin_or_manager)
def create_user(request):
    """Create new user with enhanced validation and group assignment"""
    if request.method == 'POST':
        try:
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            password = request.POST.get('password')
            password_confirm = request.POST.get('password_confirm')
            is_active = request.POST.get('is_active') == 'on'
            is_staff = request.POST.get('is_staff') == 'on'
            group_ids = request.POST.getlist('groups')
            
            # Validation
            if not username:
                messages.error(request, 'Username is required')
                return redirect('frontend:user_management')
            
            if not password:
                messages.error(request, 'Password is required')
                return redirect('frontend:user_management')
            
            if password != password_confirm:
                messages.error(request, 'Passwords do not match')
                return redirect('frontend:user_management')
            
            # Check if username exists
            if User.objects.filter(username=username).exists():
                messages.error(request, f'Username "{username}" already exists')
                return redirect('frontend:user_management')
            
            # Validate password strength
            try:
                validate_password(password)
            except ValidationError as e:
                messages.error(request, f'Password validation failed: {"; ".join(e.messages)}')
                return redirect('frontend:user_management')
            
            # Create user
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=is_active,
                    is_staff=is_staff
                )
                
                # Add to groups
                if group_ids:
                    groups = Group.objects.filter(id__in=group_ids)
                    user.groups.set(groups)
            
            # Build success message with group info
            group_names = list(user.groups.values_list('name', flat=True))
            group_info = f" and assigned to groups: {', '.join(group_names)}" if group_names else ""
            
            messages.success(request, f'User "{username}" created successfully{group_info}')
            return redirect('frontend:user_management')
            
        except Exception as e:
            messages.error(request, f'Error creating user: {str(e)}')
            return redirect('frontend:user_management')
    
    return redirect('frontend:user_management')

# UPDATED: Enhanced edit_user view
@login_required
@user_passes_test(is_admin_or_manager)
def edit_user(request, user_id):
    """Edit existing user with group management"""
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        try:
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            is_staff = request.POST.get('is_staff') == 'on'
            group_ids = request.POST.getlist('groups')
            
            # Validation
            if not username:
                messages.error(request, 'Username is required')
                return redirect('frontend:user_management')
            
            # Check if username exists for other users
            if User.objects.filter(username=username).exclude(id=user_id).exists():
                messages.error(request, f'Username "{username}" already exists')
                return redirect('frontend:user_management')
            
            # Prevent self-deactivation
            if user_id == request.user.id and not is_active:
                messages.error(request, 'You cannot deactivate your own account')
                return redirect('frontend:user_management')
            
            # Update user with transaction
            with transaction.atomic():
                user.username = username
                user.email = email
                user.first_name = first_name
                user.last_name = last_name
                user.is_active = is_active
                user.is_staff = is_staff
                user.save()
                
                # Update groups
                if group_ids:
                    groups = Group.objects.filter(id__in=group_ids)
                    user.groups.set(groups)
                else:
                    user.groups.clear()
            
            # Build success message with group info
            group_names = list(user.groups.values_list('name', flat=True))
            group_info = f" Groups: {', '.join(group_names)}" if group_names else " (No groups assigned)"
            
            messages.success(request, f'User "{username}" updated successfully.{group_info}')
            return redirect('frontend:user_management')
            
        except Exception as e:
            messages.error(request, f'Error updating user: {str(e)}')
            return redirect('frontend:user_management')
    
    return redirect('frontend:user_management')

# NEW: Reset user password
@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def reset_user_password(request, user_id):
    """Reset user password with generated temporary password"""
    try:
        user = get_object_or_404(User, id=user_id)
        
        # Generate random password
        alphabet = string.ascii_letters + string.digits
        new_password = ''.join(secrets.choice(alphabet) for i in range(12))
        
        # Set new password
        user.set_password(new_password)
        user.save()
        
        return JsonResponse({
            'success': True,
            'new_password': new_password,
            'message': f'Password reset for user "{user.username}"'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

# NEW: Toggle user status (activate/deactivate)
@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def toggle_user_status(request, user_id):
    """Toggle user active status"""
    try:
        user = get_object_or_404(User, id=user_id)
        
        # Prevent self-deactivation
        if user_id == request.user.id:
            return JsonResponse({
                'success': False,
                'error': 'You cannot deactivate your own account'
            })
        
        # Toggle status
        user.is_active = not user.is_active
        user.save()
        
        status = 'activated' if user.is_active else 'deactivated'
        
        return JsonResponse({
            'success': True,
            'is_active': user.is_active,
            'message': f'User "{user.username}" {status} successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

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
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def setup_groups(request):
    """Create default user groups with enhanced feedback"""
    try:
        # Define groups with descriptions
        default_groups = [
            {
                'name': 'Administrators',
                'description': 'Full operational access except system setup'
            },
            {
                'name': 'Managers',
                'description': 'Reports and inventory management access'
            },
            {
                'name': 'Vessel Operators',
                'description': 'Sales, supply, transfers, and inventory access'
            },
            {
                'name': 'Inventory Staff',
                'description': 'Inventory and reports access only'
            },
            {
                'name': 'Viewers',
                'description': 'Read-only access to inventory and basic reports'
            }
        ]
        
        created_groups = []
        existing_groups = []
        
        with transaction.atomic():
            for group_data in default_groups:
                group, created = Group.objects.get_or_create(
                    name=group_data['name'],
                    defaults={'name': group_data['name']}
                )
                if created:
                    created_groups.append(group_data['name'])
                else:
                    existing_groups.append(group_data['name'])
        
        # Detailed response with counts
        total_groups = Group.objects.count()
        user_counts = {group.name: group.user_set.count() for group in Group.objects.all()}
        
        message = f"Groups setup complete. Total groups: {total_groups}"
        if created_groups:
            message += f"\n✅ Created: {', '.join(created_groups)}"
        if existing_groups:
            message += f"\nℹ️ Already existed: {', '.join(existing_groups)}"
        
        return JsonResponse({
            'success': True,
            'created_groups': created_groups,
            'existing_groups': existing_groups,
            'total_groups': total_groups,
            'user_counts': user_counts,
            'message': message
        })
        
    except Exception as e:
        error_details = str(e)
        print(f"Setup groups error: {error_details}")
        print(traceback.format_exc())
        
        return JsonResponse({
            'success': False,
            'error': f'Error creating groups: {error_details}'
        })

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
    """Create new user group"""
    if request.method == 'POST':
        try:
            
            data = json.loads(request.body)
            
            name = data.get('name', '').strip()
            description = data.get('description', '').strip()
            
            # Validation
            if not name:
                return JsonResponse({'success': False, 'error': 'Group name is required'})
            
            # Check if group exists
            if Group.objects.filter(name=name).exists():
                return JsonResponse({'success': False, 'error': f'Group "{name}" already exists'})
            
            # Create group
            group = Group.objects.create(name=name)
            
            return JsonResponse({
                'success': True,
                'message': f'Group "{name}" created successfully',
                'group': {
                    'id': group.id,
                    'name': group.name,
                    'user_count': 0
                }
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
@user_passes_test(is_superuser_only) 
def edit_group(request, group_id):
    """Edit existing group"""
    if request.method == 'GET':
        try:
            group = Group.objects.get(id=group_id)
            return JsonResponse({
                'success': True,
                'group': {
                    'id': group.id,
                    'name': group.name,
                    'user_count': group.user_set.count(),
                    'users': list(group.user_set.values('id', 'username'))
                }
            })
        except Group.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Group not found'})
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            group = Group.objects.get(id=group_id)
            new_name = data.get('name', '').strip()
            
            # Validation
            if not new_name:
                return JsonResponse({'success': False, 'error': 'Group name is required'})
            
            # Check if name exists for other groups
            if Group.objects.filter(name=new_name).exclude(id=group_id).exists():
                return JsonResponse({'success': False, 'error': f'Group "{new_name}" already exists'})
            
            # Update group
            old_name = group.name
            group.name = new_name
            group.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Group renamed from "{old_name}" to "{new_name}"',
                'group': {
                    'id': group.id,
                    'name': group.name,
                    'user_count': group.user_set.count()
                }
            })
            
        except Group.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Group not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
@user_passes_test(is_superuser_only)
@require_http_methods(["DELETE"])
def delete_group(request, group_id):
    """Delete group with validation"""
    try:
        group = Group.objects.get(id=group_id)
        
        # Check if group has users
        user_count = group.user_set.count()
        force_delete = request.headers.get('X-Force-Delete') == 'true'
        
        if user_count > 0 and not force_delete:
            # Return user details for confirmation
            users_info = list(group.user_set.values('username', 'is_active'))
            
            return JsonResponse({
                'success': False,
                'requires_confirmation': True,
                'user_count': user_count,
                'users': users_info,
                'error': f'Group "{group.name}" has {user_count} users. Remove users and delete group?'
            })
        
        group_name = group.name
        
        # Delete with cascade if confirmed
        if force_delete and user_count > 0:
            # Remove all users from group first
            group.user_set.clear()
        
        # Delete the group
        group.delete()
        
        message = f'Group "{group_name}" deleted successfully'
        if force_delete and user_count > 0:
            message += f' (removed {user_count} users from group)'
        
        return JsonResponse({
            'success': True,
            'message': message
        })
        
    except Group.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Group not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_superuser_only)
def group_details(request, group_id):
    """Get detailed group information including permissions"""
    try:
        group = Group.objects.get(id=group_id)
        
        # Get users in group
        users = group.user_set.all().order_by('username')
        users_data = []
        for user in users:
            users_data.append({
                'id': user.id,
                'username': user.username,
                'full_name': user.get_full_name() or '-',
                'is_active': user.is_active,
                'is_staff': user.is_staff,
                'last_login': user.last_login.strftime('%d/%m/%Y %H:%M') if user.last_login else 'Never'
            })
        
        # Get permissions (if any custom permissions are set)
        permissions = group.permissions.all()
        permissions_data = [{'name': perm.name, 'codename': perm.codename} for perm in permissions]
        
        return JsonResponse({
            'success': True,
            'group': {
                'id': group.id,
                'name': group.name,
                'user_count': len(users_data),
                'users': users_data,
                'permissions': permissions_data
            }
        })
        
    except Group.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Group not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

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
    """Create new vessel"""
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            name_ar = request.POST.get('name_ar', '').strip()
            has_duty_free = request.POST.get('has_duty_free') == 'on'
            active = request.POST.get('active') == 'on'
            
            # Validation
            if not name:
                return JsonResponse({'success': False, 'error': 'Vessel name is required'})
            
            # Check if vessel name exists
            if Vessel.objects.filter(name=name).exists():
                return JsonResponse({'success': False, 'error': f'Vessel "{name}" already exists'})
            
            # Create vessel
            vessel = Vessel.objects.create(
                name=name,
                name_ar=name_ar,
                has_duty_free=has_duty_free,
                active=active,
                created_by=request.user
            )
            
            return JsonResponse({
                'success': True,
                'vessel_name': vessel.name,
                'message': f'Vessel "{vessel.name}" created successfully'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'POST method required'})

@login_required
@user_passes_test(is_admin_or_manager)
def edit_vessel(request, vessel_id):
    """Edit existing vessel"""
    
    if request.method == 'POST':
        try:
            vessel = get_object_or_404(Vessel, id=vessel_id)
            
            name = request.POST.get('name', '').strip()
            name_ar = request.POST.get('name_ar', '').strip()
            has_duty_free = request.POST.get('has_duty_free') == 'on'
            active = request.POST.get('active') == 'on'
            
            # Validation
            if not name:
                return JsonResponse({'success': False, 'error': 'Vessel name is required'})
            
            # Check if vessel name exists (exclude current)
            if Vessel.objects.filter(name=name).exclude(id=vessel_id).exists():
                return JsonResponse({'success': False, 'error': f'Vessel "{name}" already exists'})
            
            # Update vessel
            vessel.name = name
            vessel.name_ar = name_ar
            vessel.has_duty_free = has_duty_free
            vessel.active = active
            vessel.save()
            
            return JsonResponse({
                'success': True,
                'vessel_name': vessel.name,
                'message': f'Vessel "{vessel.name}" updated successfully'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'POST method required'})

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def toggle_vessel_status(request, vessel_id):
    """Toggle vessel active status"""
    
    try:
        vessel = get_object_or_404(Vessel, id=vessel_id)
        
        # Check if vessel has any active transactions
        if vessel.active:  # If currently active and we're deactivating
            # Check for incomplete trips or POs
            incomplete_trips = Trip.objects.filter(vessel=vessel, is_completed=False).count()
            incomplete_pos = PurchaseOrder.objects.filter(vessel=vessel, is_completed=False).count()
            
            if incomplete_trips > 0 or incomplete_pos > 0:
                return JsonResponse({
                    'success': False,
                    'error': f'Cannot deactivate vessel. Has {incomplete_trips} incomplete trips and {incomplete_pos} incomplete purchase orders.'
                })
        
        # Toggle status
        vessel.active = not vessel.active
        vessel.save()
        
        status = 'activated' if vessel.active else 'deactivated'
        
        return JsonResponse({
            'success': True,
            'is_active': vessel.active,
            'message': f'Vessel "{vessel.name}" {status} successfully'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_admin_or_manager)
def vessel_statistics(request, vessel_id):
    """Get detailed vessel statistics"""
    
    try:
        vessel = get_object_or_404(Vessel, id=vessel_id)
        
        # Calculate statistics
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        ninety_days_ago = timezone.now().date() - timedelta(days=90)
        
        # Trip statistics
        total_trips = Trip.objects.filter(vessel=vessel, is_completed=True).count()
        trips_30d = Trip.objects.filter(
            vessel=vessel,
            trip_date__gte=thirty_days_ago,
            is_completed=True
        ).count()
        
        # Revenue statistics
        total_revenue = Transaction.objects.filter(
            vessel=vessel,
            transaction_type='SALE'
        ).aggregate(
            total=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
        )['total'] or 0
        
        revenue_30d = Transaction.objects.filter(
            vessel=vessel,
            transaction_type='SALE',
            transaction_date__gte=thirty_days_ago
        ).aggregate(
            total=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
        )['total'] or 0
        
        # Passenger statistics
        total_passengers = Trip.objects.filter(
            vessel=vessel,
            is_completed=True
        ).aggregate(total=Sum('passenger_count'))['total'] or 0
        
        avg_revenue_per_passenger = total_revenue / max(total_passengers, 1)
        
        # Top products (last 90 days)
        top_products = Transaction.objects.filter(
            vessel=vessel,
            transaction_type='SALE',
            transaction_date__gte=ninety_days_ago
        ).values(
            'product__name'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
        ).order_by('-total_quantity')[:10]
        
        # Monthly performance (last 12 months)
        monthly_performance = []
        for i in range(11, -1, -1):
            month_date = timezone.now().date() - timedelta(days=i*30)
            month_start = date(month_date.year, month_date.month, 1)
            
            if month_date.month == 12:
                month_end = date(month_date.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(month_date.year, month_date.month + 1, 1) - timedelta(days=1)
            
            month_revenue = Transaction.objects.filter(
                vessel=vessel,
                transaction_type='SALE',
                transaction_date__gte=month_start,
                transaction_date__lte=month_end
            ).aggregate(
                total=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
            )['total'] or 0
            
            monthly_performance.append({
                'month': month_date.strftime('%b %Y'),
                'revenue': float(month_revenue)
            })
        
        return JsonResponse({
            'success': True,
            'vessel': {
                'name': vessel.name,
                'name_ar': vessel.name_ar,
                'has_duty_free': vessel.has_duty_free,
                'active': vessel.active,
            },
            'statistics': {
                'total_trips': total_trips,
                'trips_30d': trips_30d,
                'total_revenue': float(total_revenue),
                'revenue_30d': float(revenue_30d),
                'total_passengers': total_passengers,
                'avg_revenue_per_passenger': float(avg_revenue_per_passenger),
            },
            'top_products': list(top_products),
            'monthly_performance': monthly_performance,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
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
        try:
            po = PurchaseOrder.objects.get(id=po_id)
            return JsonResponse({
                'success': True,
                'po': {
                    'id': po.id,
                    'po_number': po.po_number,
                    'po_date': po.po_date.strftime('%Y-%m-%d'),
                    'notes': po.notes or '',
                    'vessel_id': po.vessel.id,
                    'vessel_name': po.vessel.name,
                }
            })
        except PurchaseOrder.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Purchase Order not found'})
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            po = PurchaseOrder.objects.get(id=po_id)
            
            # Update PO fields
            po.po_date = datetime.strptime(data.get('po_date'), '%Y-%m-%d').date()
            po.notes = data.get('notes', '')
            po.save()
            
            return JsonResponse({
                'success': True, 
                'message': f'Purchase Order {po.po_number} updated successfully'
            })
            
        except PurchaseOrder.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Purchase Order not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["DELETE"])
def delete_po(request, po_id):
    """Delete PO with cascade option for transactions and proper inventory removal"""
    try:
        po = PurchaseOrder.objects.get(id=po_id)
        
        # Get transaction count for confirmation
        transaction_count = po.supply_transactions.count()
        
        # Check if force delete was requested (cascade)
        force_delete = request.headers.get('X-Force-Delete') == 'true'
        
        if transaction_count > 0 and not force_delete:
            # Return transaction details for user confirmation
            transactions_info = []
            for supply_txn in po.supply_transactions.all():
                transactions_info.append({
                    'product_name': supply_txn.product.name,
                    'quantity': float(supply_txn.quantity),
                    'amount': float(supply_txn.total_amount)
                })
            
            return JsonResponse({
                'success': False,
                'requires_confirmation': True,
                'transaction_count': transaction_count,
                'total_cost': float(po.total_cost),
                'transactions': transactions_info,
                'error': f'This PO has {transaction_count} supply transactions. Delete anyway?'
            })
        
        po_number = po.po_number
        
        # Delete with cascade if confirmed
        if force_delete and transaction_count > 0:
            with transaction.atomic():
                # For supply transactions, we need to properly remove inventory
                for supply_txn in po.supply_transactions.all():
                    # Find and remove the exact inventory lots created by this supply
                    lots_to_remove = InventoryLot.objects.filter(
                        vessel=supply_txn.vessel,
                        product=supply_txn.product,
                        purchase_date=supply_txn.transaction_date,
                        purchase_price=supply_txn.unit_price,
                        original_quantity=int(supply_txn.quantity)
                    ).order_by('created_at')
                    
                    # Remove the lots (this will affect inventory counts)
                    removed_count = 0
                    for lot in lots_to_remove:
                        if removed_count < supply_txn.quantity:
                            quantity_to_remove = min(lot.remaining_quantity, supply_txn.quantity - removed_count)
                            if lot.remaining_quantity <= quantity_to_remove:
                                # Remove entire lot
                                lot.delete()
                                removed_count += lot.original_quantity
                            else:
                                # Partially remove from lot
                                lot.remaining_quantity -= quantity_to_remove
                                lot.original_quantity -= quantity_to_remove
                                lot.save()
                                removed_count += quantity_to_remove
                    
                    # If we couldn't remove exact lots, create a reversal sale transaction
                    if removed_count < supply_txn.quantity:
                        remaining_to_remove = supply_txn.quantity - removed_count
                        Transaction.objects.create(
                            vessel=supply_txn.vessel,
                            product=supply_txn.product,
                            transaction_type='SALE',
                            transaction_date=supply_txn.transaction_date,
                            quantity=remaining_to_remove,
                            unit_price=supply_txn.unit_price,
                            notes=f"Inventory removal from deleted PO {po_number}",
                            created_by=request.user
                        )
                
                # Delete all related transactions
                po.supply_transactions.all().delete()
                
                # Then delete the PO
                po.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'PO {po_number} and all {transaction_count} transactions deleted successfully. Inventory removed.'
            })
        else:
            # No transactions, safe to delete
            po.delete()
            return JsonResponse({
                'success': True,
                'message': f'PO {po_number} deleted successfully'
            })
        
    except PurchaseOrder.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Purchase Order not found'})
    except Exception as e:
        print(f"Delete PO error: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_admin_or_manager)
def toggle_po_status(request, po_id):
    """Toggle PO completion status"""
    if request.method == 'POST':
        try:
            po = PurchaseOrder.objects.get(id=po_id)
            po.is_completed = not po.is_completed
            po.save()
            
            status = 'completed' if po.is_completed else 'in progress'
            return JsonResponse({
                'success': True,
                'message': f'Purchase Order {po.po_number} marked as {status}',
                'new_status': po.is_completed
            })
            
        except PurchaseOrder.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Purchase Order not found'})

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
        try:
            trip = Trip.objects.get(id=trip_id)
            return JsonResponse({
                'success': True,
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
        except Trip.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Trip not found'})
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            trip = Trip.objects.get(id=trip_id)
            
            # Update trip fields
            trip.passenger_count = int(data.get('passenger_count', trip.passenger_count))
            trip.trip_date = datetime.strptime(data.get('trip_date'), '%Y-%m-%d').date()
            trip.notes = data.get('notes', '')
            trip.save()
            
            return JsonResponse({
                'success': True, 
                'message': f'Trip {trip.trip_number} updated successfully'
            })
            
        except Trip.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Trip not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

# Add these enhanced deletion methods to your auth_views.py

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["DELETE"])
def delete_trip(request, trip_id):
    """Delete trip with cascade option for transactions and proper inventory restoration"""
    try:
        trip = Trip.objects.get(id=trip_id)
        
        # Get transaction count for confirmation
        transaction_count = trip.sales_transactions.count()
        
        # Check if force delete was requested (cascade)
        force_delete = request.headers.get('X-Force-Delete') == 'true'
        
        if transaction_count > 0 and not force_delete:
            # Return transaction details for user confirmation
            transactions_info = []
            for sale_txn in trip.sales_transactions.all():
                transactions_info.append({
                    'product_name': sale_txn.product.name,
                    'quantity': float(sale_txn.quantity),
                    'amount': float(sale_txn.total_amount)
                })
            
            return JsonResponse({
                'success': False,
                'requires_confirmation': True,
                'transaction_count': transaction_count,
                'total_revenue': float(trip.total_revenue),
                'transactions': transactions_info,
                'error': f'This trip has {transaction_count} sales transactions. Delete anyway?'
            })
        
        trip_number = trip.trip_number
        
        # Delete with cascade if confirmed
        if force_delete and transaction_count > 0:
            # Handle inventory restoration for sales transactions
            with transaction.atomic():
                for sale_txn in trip.sales_transactions.all():
                    # Restore inventory by creating a new supply transaction (reversal)
                    # This maintains proper FIFO tracking
                    Transaction.objects.create(
                        vessel=sale_txn.vessel,
                        product=sale_txn.product,
                        transaction_type='SUPPLY',
                        transaction_date=sale_txn.transaction_date,
                        quantity=sale_txn.quantity,
                        unit_price=sale_txn.unit_price,  # Restore at original sale price (closest approximation)
                        notes=f"Inventory restoration from deleted trip {trip_number}",
                        created_by=request.user
                    )
                
                # Delete all related transactions first
                trip.sales_transactions.all().delete()
                
                # Then delete the trip
                trip.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Trip {trip_number} and all {transaction_count} transactions deleted successfully. Inventory restored.'
            })
        else:
            # No transactions, safe to delete
            trip.delete()
            return JsonResponse({
                'success': True,
                'message': f'Trip {trip_number} deleted successfully'
            })
        
    except Trip.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Trip not found'})
    except Exception as e:
        print(f"Delete trip error: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def toggle_trip_status(request, trip_id):
    """Toggle trip completion status"""
    try:
        trip = Trip.objects.get(id=trip_id)
        trip.is_completed = not trip.is_completed
        trip.save()
        
        status = 'completed' if trip.is_completed else 'in progress'
        return JsonResponse({
            'success': True,
            'message': f'Trip {trip.trip_number} marked as {status}',
            'new_status': trip.is_completed
        })
        
    except Trip.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Trip not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_admin_or_manager)
def trip_details(request, trip_id):
    """Get detailed trip information"""
    
    try:
        trip = get_object_or_404(Trip, id=trip_id)
        
        # Get trip sales
        sales_transactions = trip.sales_transactions.select_related('product').order_by('created_at')
        
        # Calculate statistics
        total_revenue = trip.total_revenue
        total_items = sales_transactions.aggregate(
            total_items=Sum('quantity')
        )['total_items'] or 0
        
        revenue_per_passenger = total_revenue / max(trip.passenger_count, 1)
        
        # Sales breakdown
        sales_breakdown = []
        for sale in sales_transactions:
            sales_breakdown.append({
                'product_name': sale.product.name,
                'quantity': float(sale.quantity),
                'unit_price': float(sale.unit_price),
                'total_amount': float(sale.total_amount),
            })
        
        return JsonResponse({
            'success': True,
            'trip': {
                'trip_number': trip.trip_number,
                'vessel_name': trip.vessel.name,
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
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

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