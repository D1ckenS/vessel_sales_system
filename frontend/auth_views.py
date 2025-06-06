# frontend/auth_views.py
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group, Permission
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from .utils import BilingualMessages

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

def is_admin_or_manager(user):
    """Check if user is admin or manager"""
    return user.is_superuser or user.groups.filter(name__in=['Managers', 'Administrators']).exists()

@login_required
@user_passes_test(is_admin_or_manager)
def user_management(request):
    """User management interface for admins and managers"""
    
    # Get all users with their groups
    users = User.objects.prefetch_related('groups').order_by('username')
    groups = Group.objects.all().order_by('name')
    
    context = {
        'users': users,
        'groups': groups,
    }
    
    return render(request, 'frontend/auth/user_management.html', context)

@login_required
@user_passes_test(is_admin_or_manager)
def create_user(request):
    """Create new user"""
    
    if request.method == 'POST':
        try:
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            password = request.POST.get('password', '')
            confirm_password = request.POST.get('confirm_password', '')
            group_ids = request.POST.getlist('groups')
            is_active = request.POST.get('is_active') == 'on'
            is_staff = request.POST.get('is_staff') == 'on'
            
            # Validation
            if not username or not password:
                BilingualMessages.error(request, 'username_password_required')
                return redirect('frontend:user_management')
            
            if password != confirm_password:
                BilingualMessages.error(request, 'passwords_do_not_match')
                return redirect('frontend:user_management')
            
            if len(password) < 6:
                BilingualMessages.error(request, 'password_too_short')
                return redirect('frontend:user_management')
            
            # Check if username exists
            if User.objects.filter(username=username).exists():
                BilingualMessages.error(request, 'username_exists', username=username)
                return redirect('frontend:user_management')
            
            # Check if email exists (if provided)
            if email and User.objects.filter(email=email).exists():
                BilingualMessages.error(request, 'email_exists', email=email)
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
                
                BilingualMessages.success(request, 'user_created_success', username=username)
                
        except Exception as e:
            BilingualMessages.error(request, 'error_creating_user', error=str(e))
    
    return redirect('frontend:user_management')

@login_required
@user_passes_test(is_admin_or_manager)
def edit_user(request, user_id):
    """Edit existing user"""
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        BilingualMessages.error(request, 'user_not_found')
        return redirect('frontend:user_management')
    
    if request.method == 'POST':
        try:
            email = request.POST.get('email', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            group_ids = request.POST.getlist('groups')
            is_active = request.POST.get('is_active') == 'on'
            is_staff = request.POST.get('is_staff') == 'on'
            
            # Check if email exists for other users
            if email and User.objects.filter(email=email).exclude(id=user.id).exists():
                BilingualMessages.error(request, 'email_exists', email=email)
                return redirect('frontend:user_management')
            
            # Update user
            with transaction.atomic():
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
                
                BilingualMessages.success(request, 'user_updated_success', username=user.username)
                
        except Exception as e:
            BilingualMessages.error(request, 'error_updating_user', error=str(e))
    
    return redirect('frontend:user_management')

@login_required
@user_passes_test(is_admin_or_manager)
def reset_user_password(request, user_id):
    """Reset user password"""
    
    if request.method == 'POST':
        try:
            user = User.objects.get(id=user_id)
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')
            
            if not new_password or len(new_password) < 6:
                BilingualMessages.error(request, 'password_too_short')
                return redirect('frontend:user_management')
            
            if new_password != confirm_password:
                BilingualMessages.error(request, 'passwords_do_not_match')
                return redirect('frontend:user_management')
            
            user.set_password(new_password)
            user.save()
            
            BilingualMessages.success(request, 'password_reset_success', username=user.username)
            
        except User.DoesNotExist:
            BilingualMessages.error(request, 'user_not_found')
        except Exception as e:
            BilingualMessages.error(request, 'error_resetting_password', error=str(e))
    
    return redirect('frontend:user_management')

@login_required
@user_passes_test(is_admin_or_manager)
def toggle_user_status(request, user_id):
    """Toggle user active status"""
    
    if request.method == 'POST':
        try:
            user = User.objects.get(id=user_id)
            
            # Don't allow deactivating yourself
            if user == request.user:
                BilingualMessages.error(request, 'cannot_deactivate_yourself')
                return redirect('frontend:user_management')
            
            user.is_active = not user.is_active
            user.save()
            
            status = 'activated' if user.is_active else 'deactivated'
            BilingualMessages.success(request, f'user_{status}_success', username=user.username)
            
        except User.DoesNotExist:
            BilingualMessages.error(request, 'user_not_found')
        except Exception as e:
            BilingualMessages.error(request, 'error_updating_user', error=str(e))
    
    return redirect('frontend:user_management')

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
def setup_groups(request):
    """Setup default user groups and permissions"""
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Create default groups
                groups_config = {
                    'Administrators': [
                        'Can access all features',
                        'Can manage users and permissions',
                        'Can view all reports',
                        'Can export all data'
                    ],
                    'Managers': [
                        'Can view all vessel operations',
                        'Can manage trips and purchase orders',
                        'Can view reports and analytics',
                        'Can export reports'
                    ],
                    'Vessel Operators': [
                        'Can manage assigned vessel operations',
                        'Can create trips and sales',
                        'Can view inventory for assigned vessels',
                        'Limited reporting access'
                    ],
                    'Inventory Staff': [
                        'Can manage inventory and transfers',
                        'Can create purchase orders',
                        'Can view inventory reports',
                        'Cannot access financial data'
                    ],
                    'Viewers': [
                        'Read-only access to reports',
                        'Cannot modify any data',
                        'Basic dashboard access'
                    ]
                }
                
                created_groups = []
                for group_name, description in groups_config.items():
                    group, created = Group.objects.get_or_create(name=group_name)
                    if created:
                        created_groups.append(group_name)
                
                BilingualMessages.success(request, 
                    f'Groups setup completed. Created: {", ".join(created_groups) if created_groups else "All groups already exist"}'
                )
                
        except Exception as e:
            BilingualMessages.error(request, 'error_setting_up_groups', error=str(e))
    
    return redirect('frontend:user_management')

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
    """AJAX endpoint to check user permissions"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    try:
        import json
        data = json.loads(request.body)
        permission_name = data.get('permission')
        
        has_permission = request.user.has_perm(permission_name) or request.user.is_superuser
        
        return JsonResponse({
            'success': True,
            'has_permission': has_permission,
            'user_groups': [group.name for group in request.user.groups.all()],
            'is_superuser': request.user.is_superuser
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})