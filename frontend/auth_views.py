# frontend/auth_views.py
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group, Permission
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.contenttypes.models import ContentType
from django.db import transaction, models
from django.db.models import Sum, F, Count
from transactions.models import Transaction, Trip, PurchaseOrder
from vessels.models import Vessel
from .utils import BilingualMessages
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from datetime import date, datetime
import json
import secrets
import string
from .permissions import is_admin_or_manager, admin_or_manager_required, superuser_required
from .permissions import (
    operations_access_required,
    reports_access_required,
    admin_or_manager_required
)

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
        import traceback
        error_details = str(e)
        print(f"Setup groups error: {error_details}")
        print(traceback.format_exc())
        
        return JsonResponse({
            'success': False,
            'error': f'Error creating groups: {error_details}'
        })

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
        import json
        from .permissions import get_user_role, UserRoles
        
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
    
@login_required
@user_passes_test(is_admin_or_manager)
def vessel_management(request):
    """Vessel management interface - complete Django admin replacement"""
    
    vessels = Vessel.objects.all().order_by('name')
    
    # Calculate statistics
    total_vessels = vessels.count()
    active_vessels = vessels.filter(active=True).count()
    duty_free_vessels = vessels.filter(has_duty_free=True).count()
    inactive_vessels = total_vessels - active_vessels
    
    # Get performance data for each vessel (last 30 days)
    from datetime import timedelta
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    
    vessel_data = []
    for vessel in vessels:
        # Get trip count and revenue for last 30 days
        trips_30d = Trip.objects.filter(
            vessel=vessel,
            trip_date__gte=thirty_days_ago,
            is_completed=True
        ).count()
        
        revenue_30d = Transaction.objects.filter(
            vessel=vessel,
            transaction_type='SALE',
            transaction_date__gte=thirty_days_ago
        ).aggregate(
            total=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
        )['total'] or 0
        
        vessel_data.append({
            'vessel': vessel,
            'trips_30d': trips_30d,
            'revenue_30d': revenue_30d,
        })
    
    context = {
        'vessel_data': vessel_data,
        'stats': {
            'total_vessels': total_vessels,
            'active_vessels': active_vessels,
            'duty_free_vessels': duty_free_vessels,
            'inactive_vessels': inactive_vessels,
        }
    }
    
    return render(request, 'frontend/auth/vessel_management.html', context)

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
        from datetime import timedelta
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
    """Real PO management - CRUD for all POs"""
    
    # Get filter parameters
    vessel_filter = request.GET.get('vessel')
    status_filter = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Get REAL POs with annotations
    purchase_orders = PurchaseOrder.objects.select_related('vessel', 'created_by').annotate(
        annotated_transaction_count=Count('supply_transactions'),
        annotated_total_cost=Sum(
            F('supply_transactions__unit_price') * F('supply_transactions__quantity'),
            output_field=models.DecimalField()
        )
    ).order_by('-po_date', '-created_at')
    
    # Apply filters
    if vessel_filter:
        purchase_orders = purchase_orders.filter(vessel_id=vessel_filter)
    if status_filter == 'completed':
        purchase_orders = purchase_orders.filter(is_completed=True)
    elif status_filter == 'in_progress':
        purchase_orders = purchase_orders.filter(is_completed=False)
    if date_from:
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
        purchase_orders = purchase_orders.filter(po_date__gte=date_from_obj)
    if date_to:
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
        purchase_orders = purchase_orders.filter(po_date__lte=date_to_obj)
    
    # Real statistics
    total_pos = purchase_orders.count()
    completed_pos = purchase_orders.filter(is_completed=True).count()
    pending_pos = total_pos - completed_pos
    
    # Total procurement value (real data)
    total_procurement_value = Transaction.objects.filter(
        transaction_type='SUPPLY'
    ).aggregate(
        total=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
    )['total'] or 0
    
    # Real supplier analysis (vessel-based since no supplier field)
    top_suppliers = Transaction.objects.filter(
        transaction_type='SUPPLY'
    ).values(
        'vessel__name', 'vessel__name_ar'
    ).annotate(
        total_value=Sum(F('unit_price') * F('quantity')),
        po_count=Count('purchase_order', distinct=True)
    ).order_by('-total_value')[:10]
    
    context = {
        'purchase_orders': purchase_orders[:50],  # Limit for performance
        'vessels': Vessel.objects.filter(active=True).order_by('name'),
        'top_suppliers': top_suppliers,
        'stats': {
            'total_pos': total_pos,
            'completed_pos': completed_pos,
            'pending_pos': pending_pos,
            'total_procurement_value': total_procurement_value,
        },
        'filters': {
            'vessel': vessel_filter,
            'status': status_filter,
            'date_from': date_from,
            'date_to': date_to,
        }
    }
    
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
            import json
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
def delete_po(request, po_id):
    """Delete PO with validation"""
    if request.method == 'DELETE':
        try:
            po = PurchaseOrder.objects.get(id=po_id)
            
            # Check if PO has transactions
            if po.supply_transactions.exists():
                return JsonResponse({
                    'success': False, 
                    'error': 'Cannot delete purchase order with existing supply transactions'
                })
            
            po_number = po.po_number
            po.delete()
            
            return JsonResponse({
                'success': True, 
                'message': f'Purchase Order {po_number} deleted successfully'
            })
            
        except PurchaseOrder.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Purchase Order not found'})
        except Exception as e:
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
    """Real trip management - CRUD for all trips"""
    
    # Get filter parameters
    vessel_filter = request.GET.get('vessel')
    status_filter = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    min_revenue = request.GET.get('min_revenue')
    
    # Get REAL trips with annotations - FIXED: Use annotated_ prefix to avoid conflicts
    trips = Trip.objects.select_related('vessel', 'created_by').annotate(
        annotated_transaction_count=Count('sales_transactions'),
        annotated_total_revenue=Sum(
            F('sales_transactions__unit_price') * F('sales_transactions__quantity'),
            output_field=models.DecimalField()
        )
    ).order_by('-trip_date', '-created_at')
    
    # Apply filters
    if vessel_filter:
        trips = trips.filter(vessel_id=vessel_filter)
    if status_filter == 'completed':
        trips = trips.filter(is_completed=True)
    elif status_filter == 'in_progress':
        trips = trips.filter(is_completed=False)
    if date_from:
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
        trips = trips.filter(trip_date__gte=date_from_obj)
    if date_to:
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
        trips = trips.filter(trip_date__lte=date_to_obj)
    if min_revenue:
        # Use annotated field for filtering
        trips = trips.filter(annotated_total_revenue__gte=min_revenue)
    
    # Real statistics
    total_trips = trips.count()
    completed_trips = trips.filter(is_completed=True).count()
    in_progress_trips = total_trips - completed_trips
    
    # Calculate total revenue using aggregation
    total_revenue = Transaction.objects.filter(
        transaction_type='SALE'
    ).aggregate(
        total=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
    )['total'] or 0
    
    # Additional statistics
    daily_average = total_trips / 30.0 if total_trips > 0 else 0  # Approximate
    completion_rate = (completed_trips / max(total_trips, 1)) * 100
    
    # Vessel performance (real data)
    vessel_performance = Trip.objects.values(
        'vessel__name', 'vessel__name_ar'
    ).annotate(
        trip_count=Count('id'),
        avg_monthly=Count('id') / 12.0,  # Approximate monthly average
        total_revenue=Sum(
            F('sales_transactions__unit_price') * F('sales_transactions__quantity'),
            output_field=models.DecimalField()
        )
    ).order_by('-trip_count')
    
    # Add performance indicators to vessel performance
    for vessel_perf in vessel_performance:
        if vessel_perf['avg_monthly'] >= 10:
            vessel_perf['performance_class'] = 'high'
            vessel_perf['performance_icon'] = 'arrow-up-circle'
            vessel_perf['badge_class'] = 'bg-success'
        elif vessel_perf['avg_monthly'] >= 5:
            vessel_perf['performance_class'] = 'medium'
            vessel_perf['performance_icon'] = 'dash-circle'
            vessel_perf['badge_class'] = 'bg-warning'
        else:
            vessel_perf['performance_class'] = 'low'
            vessel_perf['performance_icon'] = 'arrow-down-circle'
            vessel_perf['badge_class'] = 'bg-danger'
    
    # Add calculated fields to trips for template
    for trip in trips:
        # Calculate revenue per passenger
        if hasattr(trip, 'annotated_total_revenue') and trip.annotated_total_revenue and trip.passenger_count:
            trip.revenue_per_passenger = trip.annotated_total_revenue / trip.passenger_count
            # Performance class for revenue per passenger
            if trip.revenue_per_passenger >= 50:
                trip.revenue_performance_class = 'high'
            elif trip.revenue_per_passenger >= 25:
                trip.revenue_performance_class = 'medium'
            else:
                trip.revenue_performance_class = 'low'
        else:
            trip.revenue_per_passenger = 0
            trip.revenue_performance_class = 'low'
    
    context = {
        'trips': trips[:50],  # Limit for performance
        'vessels': Vessel.objects.filter(active=True).order_by('name'),
        'vessel_performance': vessel_performance,
        'stats': {
            'total_trips': total_trips,
            'completed_trips': completed_trips,
            'in_progress_trips': in_progress_trips,
            'total_revenue': total_revenue,
            'daily_average': round(daily_average, 1),
            'completion_rate': round(completion_rate, 1),
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
            import json
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

@login_required
@user_passes_test(is_admin_or_manager)
@require_http_methods(["DELETE"])
def delete_trip(request, trip_id):
    """Delete trip with validation"""
    try:
        trip = Trip.objects.get(id=trip_id)
        
        # Check if trip has transactions
        if trip.sales_transactions.exists():
            return JsonResponse({
                'success': False, 
                'error': 'Cannot delete trip with existing sales transactions'
            })
        
        trip_number = trip.trip_number
        trip.delete()
        
        return JsonResponse({
            'success': True, 
            'message': f'Trip {trip_number} deleted successfully'
        })
        
    except Trip.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Trip not found'})
    except Exception as e:
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