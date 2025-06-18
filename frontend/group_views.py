from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group, Permission
from django.db import transaction
from frontend.utils.validation_helpers import ValidationHelper
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
from .permissions import is_admin_or_manager, is_superuser_only
from .utils.response_helpers import FormResponseHelper, JsonResponseHelper
from .utils.crud_helpers import CRUDHelper, AdminActionHelper
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

@login_required
@user_passes_test(is_admin_or_manager)
def manage_user_groups(request, user_id):
    """Manage user group assignments"""
    if request.method == 'POST':
        user, error = CRUDHelper.safe_get_object(User, user_id, 'User')
        if error:
            return FormResponseHelper.error_redirect(
                request, 'frontend:user_management', 'User not found'
            )
        
        try:
            group_ids = request.POST.getlist('groups')
            
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
@user_passes_test(is_superuser_only)
def setup_groups(request):
    """Setup default groups with permissions"""
    if request.method == 'POST':
        try:
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
            
            with transaction.atomic():
                all_permissions = {
                    perm.codename: perm 
                    for perm in Permission.objects.all()
                }
                
                for group_name, permission_names in default_groups.items():
                    # Create or get group
                    group, created = Group.objects.get_or_create(name=group_name)
                    
                    if created or not group.permissions.exists():
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
        data, error = CRUDHelper.safe_json_load(request)
        if error:
            return error
        
        valid, error = ValidationHelper.validate_group_data(data)
        if not valid:
            return error
        
        try:
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
        data, error = CRUDHelper.safe_json_load(request)
        if error:
            return error
        
        group, error = CRUDHelper.safe_get_object(Group, group_id, 'Group')
        if error:
            return error
        
        valid, error = ValidationHelper.validate_group_data(data, group_id)
        if not valid:
            return error
        
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
    group, error = CRUDHelper.safe_get_object(Group, group_id, 'Group')
    if error:
        return error
    
    force_delete = AdminActionHelper.check_force_delete(request)
    
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
    try:
        group = Group.objects.prefetch_related(
            'user_set__groups'
        ).get(id=group_id)
        
        users_data = []
        for user in group.user_set.all():
            user_groups = [g.name for g in user.groups.all()]
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