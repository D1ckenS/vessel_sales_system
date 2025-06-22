from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group
from django.db import transaction
from frontend.utils.validation_helpers import ValidationHelper
from .utils import BilingualMessages
from django.views.decorators.http import require_http_methods
import secrets
from django.db.models import Count
import string
from django.core.cache import cache
from frontend.utils.cache_helpers import UserManagementCacheHelper
from .utils.response_helpers import FormResponseHelper, JsonResponseHelper
from .utils.crud_helpers import CRUDHelper, AdminActionHelper
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required,
    is_admin_or_manager
)

@login_required
@user_passes_test(is_admin_or_manager)
def create_user(request):
    """Create new user with enhanced validation and group assignment"""
    if request.method == 'POST':
        try:
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
            
            valid, error = ValidationHelper.validate_required_fields(
                data, ['username', 'password']
            )
            if not valid:
                return FormResponseHelper.error_redirect(
                    request, 'frontend:user_management', error.content.decode()
                )
            
            valid, error = ValidationHelper.validate_username(data['username'])
            if not valid:
                return FormResponseHelper.error_redirect(
                    request, 'frontend:user_management', error.content.decode()
                )
            
            if data['email']:
                valid, error = ValidationHelper.validate_email(data['email'])
                if not valid:
                    return FormResponseHelper.error_redirect(
                        request, 'frontend:user_management', error.content.decode()
                    )
            
            valid, error = ValidationHelper.validate_password_strength(
                data['password'], data['password_confirm']
            )
            if not valid:
                return FormResponseHelper.error_redirect(
                    request, 'frontend:user_management', error.content.decode()
                )
            
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
                
                try:
                    
                    UserManagementCacheHelper.clear_user_management_cache()
                except Exception as e:
                    print(f"⚠️ Cache clear error: {e}")
                if data['group_ids']:
                    groups = Group.objects.filter(id__in=data['group_ids'])
                    user.groups.set(groups)
            
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

@login_required
@user_passes_test(is_admin_or_manager)
def edit_user(request, user_id):
    """Edit existing user with group management"""
    
    user, error = CRUDHelper.safe_get_object(User, user_id, 'User')
    if error:
        return FormResponseHelper.error_redirect(
            request, 'frontend:user_management', 'User not found'
        )
    
    if request.method == 'POST':
        try:
            data = {
                'username': request.POST.get('username', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'first_name': request.POST.get('first_name', '').strip(),
                'last_name': request.POST.get('last_name', '').strip(),
                'is_active': request.POST.get('is_active') == 'on',
                'is_staff': request.POST.get('is_staff') == 'on',
                'group_ids': request.POST.getlist('groups')
            }
            
            valid, error = ValidationHelper.validate_username(data['username'], user.id)
            if not valid:
                return FormResponseHelper.error_redirect(
                    request, 'frontend:user_management', 
                    error.content.decode()
                )
            
            if data['email']:
                valid, error = ValidationHelper.validate_email(data['email'], user.id)
                if not valid:
                    return FormResponseHelper.error_redirect(
                        request, 'frontend:user_management',
                        error.content.decode()
                    )
            
            with transaction.atomic():
                # Update user fields
                user.username = data['username']
                user.email = data['email']
                user.first_name = data['first_name']
                user.last_name = data['last_name']
                user.is_active = data['is_active']
                user.is_staff = data['is_staff']
                user.save()
                
                if data['group_ids']:
                    groups = Group.objects.filter(id__in=data['group_ids'])
                    user.groups.set(groups)
                else:
                    user.groups.clear()
            
            try:
                UserManagementCacheHelper.clear_user_management_cache()
            except Exception as e:
                print(f"⚠️ Cache clear error: {e}")
                
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

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def reset_user_password(request, user_id):
    """Reset user password with generated temporary password"""
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
        
        try:
            UserManagementCacheHelper.clear_user_management_cache()
        except Exception as e:
            print(f"⚠️ Cache clear error: {e}")
            
        return JsonResponseHelper.success(
            message=f'Password reset for user "{user.username}"',
            new_password=new_password
        )
        
    except Exception as e:
        return JsonResponseHelper.error(str(e))

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["POST"])
def toggle_user_status(request, user_id):
    """Toggle user active status"""
    self_error = AdminActionHelper.prevent_self_action(request, user_id, 'deactivate')
    if self_error:
        return self_error
    
    user, error = CRUDHelper.safe_get_object(User, user_id, 'User')
    if error:
        return error
    try:
        UserManagementCacheHelper.clear_user_management_cache()
    except Exception as e:
        print(f"⚠️ Cache clear error: {e}")
        
    return CRUDHelper.toggle_boolean_field(user, 'is_active', 'User')

@login_required
def change_password(request):
    """Allow users to change their own password"""
    
    if request.method == 'POST':
        try:
            current_password = request.POST.get('current_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')
            
            if not request.user.check_password(current_password):
                BilingualMessages.error(request, 'current_password_incorrect')
                return render(request, 'frontend/auth/change_password.html')
            
            if len(new_password) < 6:
                BilingualMessages.error(request, 'password_too_short')
                return render(request, 'frontend/auth/change_password.html')
            
            if new_password != confirm_password:
                BilingualMessages.error(request, 'passwords_do_not_match')
                return render(request, 'frontend/auth/change_password.html')
            
            request.user.set_password(new_password)
            request.user.save()
            
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
def user_management(request):
    """🚀 Optimized: Minimal queries with caching, no template-based N+1"""

    # 🔒 Cache check
    cache_key = "user_management_data"
    cached_data = cache.get(cache_key)

    if cached_data:
        print("🚀 USER MANAGEMENT CACHE HIT")
        return render(request, 'frontend/auth/user_management.html', cached_data)

    print("🚀 USER MANAGEMENT CACHE MISS - Building fresh data")

    # 📦 Fetch users and prefetch groups
    users = User.objects.prefetch_related('groups').order_by('username')
    users_list = list(users)  # Force evaluation

    # Annotate group counts
    groups = Group.objects.annotate(user_count=Count('user')).order_by('name')
    groups_list = list(groups)

    # 🧮 Build user stats
    total_users = len(users_list)
    active_users = sum(1 for user in users_list if user.is_active)
    inactive_users = total_users - active_users
    staff_users = sum(1 for user in users_list if user.is_staff)
    superusers = sum(1 for user in users_list if user.is_superuser)
    users_with_groups = sum(1 for user in users_list if user.groups.exists())
    users_without_groups = total_users - users_with_groups

    # 🧮 Group stats
    total_groups = len(groups_list)
    empty_groups = sum(1 for group in groups_list if group.user_count == 0)

    # 🧠 Precompute group data to avoid repeated .all() calls in template
    for user in users_list:
        user.group_ids = [group.id for group in user.groups.all()]
        user.group_names = [group.name for group in user.groups.all()]

    # 📦 Package context
    context = {
        'users': users_list,
        'groups': groups_list,
        'stats': {
            'total_users': total_users,
            'active_users': active_users,
            'inactive_users': inactive_users,
            'staff_users': staff_users,
            'superuser_count': superusers,
            'users_with_groups': users_with_groups,
            'users_without_groups': users_without_groups,
        },
        'group_stats': {
            'total_groups': total_groups,
            'empty_groups': empty_groups,
            'groups_with_users': total_groups - empty_groups,
        },
        'active_users_count': active_users,
        'staff_users_count': staff_users,
    }

    # 💾 Cache for 30 minutes
    cache.set(cache_key, context, 1800)

    print(f"🚀 Cached {total_users} users & {total_groups} groups")
    return render(request, 'frontend/auth/user_management.html', context)