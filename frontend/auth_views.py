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
from django.db.models import Sum, F
from transactions.models import Transaction, Trip, PurchaseOrder
from vessels.models import Vessel
from .utils import BilingualMessages
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from datetime import date
import json
import secrets
import string

def is_admin_or_manager(user):
    return user.is_authenticated and (
        user.is_superuser or 
        user.groups.filter(name__in=['Administrators', 'Managers']).exists()
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
def create_user(request):
    """Create new user with enhanced validation"""
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
            
            messages.success(request, f'User "{username}" created successfully')
            return redirect('frontend:user_management')
            
        except Exception as e:
            messages.error(request, f'Error creating user: {str(e)}')
            return redirect('frontend:user_management')
    
    return redirect('frontend:user_management')

# UPDATED: Enhanced edit_user view
@login_required
@user_passes_test(is_admin_or_manager)
def edit_user(request, user_id):
    """Edit existing user"""
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        try:
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            is_staff = request.POST.get('is_staff') == 'on'
            
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
            
            # Update user
            user.username = username
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.is_active = is_active
            user.is_staff = is_staff
            user.save()
            
            messages.success(request, f'User "{username}" updated successfully')
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
    """Create default user groups - SIMPLIFIED VERSION"""
    try:
        # Simple group creation without complex permissions
        default_groups = [
            'Administrators',
            'Managers', 
            'Vessel Operators',
            'Inventory Staff',
            'Viewers'
        ]
        
        created_groups = []
        existing_groups = []
        
        for group_name in default_groups:
            group, created = Group.objects.get_or_create(name=group_name)
            if created:
                created_groups.append(group_name)
            else:
                existing_groups.append(group_name)
        
        # Simple success response
        message = f"Groups setup complete. Created: {len(created_groups)}, Existing: {len(existing_groups)}"
        
        return JsonResponse({
            'success': True,
            'created_groups': created_groups,
            'existing_groups': existing_groups,
            'message': message
        })
        
    except Exception as e:
        # Better error handling
        import traceback
        error_details = str(e)
        print(f"Setup groups error: {error_details}")  # For debugging
        print(traceback.format_exc())  # For debugging
        
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
    """Purchase Order management interface - complete Django admin replacement"""
    
    purchase_orders = PurchaseOrder.objects.select_related('vessel', 'created_by').order_by('-po_date', '-created_at')
    
    # Apply filters
    vessel_filter = request.GET.get('vessel')
    status_filter = request.GET.get('status')
    supplier_filter = request.GET.get('supplier')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if vessel_filter:
        purchase_orders = purchase_orders.filter(vessel_id=vessel_filter)
    if status_filter == 'completed':
        purchase_orders = purchase_orders.filter(is_completed=True)
    elif status_filter == 'in_progress':
        purchase_orders = purchase_orders.filter(is_completed=False)
    if date_from:
        purchase_orders = purchase_orders.filter(po_date__gte=date_from)
    if date_to:
        purchase_orders = purchase_orders.filter(po_date__lte=date_to)
    
    # Calculate statistics
    from datetime import timedelta
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    
    total_pos = PurchaseOrder.objects.count()
    completed_pos = PurchaseOrder.objects.filter(is_completed=True).count()
    pending_pos = total_pos - completed_pos
    
    # Total procurement value
    total_procurement_value = Transaction.objects.filter(
        transaction_type='SUPPLY'
    ).aggregate(
        total=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
    )['total'] or 0
    
    # PO analytics for last 30 days
    recent_pos = PurchaseOrder.objects.filter(po_date__gte=thirty_days_ago)
    recent_po_value = Transaction.objects.filter(
        transaction_type='SUPPLY',
        purchase_order__po_date__gte=thirty_days_ago
    ).aggregate(
        total_value=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
    )['total_value'] or 0

    recent_po_count = recent_pos.count()
    avg_po_value = recent_po_value / max(recent_po_count, 1)
    
    # Top suppliers (mock data - you can implement supplier tracking)
    top_suppliers = [
        {'name': 'Marina Supply Co.', 'total_value': 24550, 'po_count': 67},
        {'name': 'Red Sea Trading', 'total_value': 18920, 'po_count': 52},
        {'name': 'Gulf Beverages Ltd', 'total_value': 15780, 'po_count': 41},
        {'name': 'Aqaba Food Supplies', 'total_value': 12340, 'po_count': 38},
    ]
    
    # Enhanced PO data with analytics
    po_data = []
    for po in purchase_orders[:50]:  # Limit for performance
        # Get item count and average cost
        item_count = po.supply_transactions.count()
        avg_cost_per_item = po.total_cost / max(item_count, 1)
        
        po_data.append({
            'po': po,
            'item_count': item_count,
            'avg_cost_per_item': avg_cost_per_item,
            'supplier': 'Marina Supply Co.',  # Mock - implement supplier tracking
            'approval_status': 'approved' if po.is_completed else 'pending',
        })
    
    context = {
        'po_data': po_data,
        'vessels': Vessel.objects.filter(active=True).order_by('name'),
        'stats': {
            'total_pos': total_pos,
            'completed_pos': completed_pos,
            'pending_pos': pending_pos,
            'total_procurement_value': total_procurement_value,
            'avg_po_value': avg_po_value,
        },
        'top_suppliers': top_suppliers,
        'filters': {
            'vessel': vessel_filter,
            'status': status_filter,
            'supplier': supplier_filter,
            'date_from': date_from,
            'date_to': date_to,
        }
    }
    
    return render(request, 'frontend/auth/po_management.html', context)

@login_required
@user_passes_test(is_admin_or_manager)
def trip_management(request):
    """Trip management interface - complete Django admin replacement"""
    
    trips = Trip.objects.select_related('vessel', 'created_by').order_by('-trip_date', '-created_at')
    
    # Apply filters
    vessel_filter = request.GET.get('vessel')
    status_filter = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    min_revenue = request.GET.get('min_revenue')
    
    if vessel_filter:
        trips = trips.filter(vessel_id=vessel_filter)
    if status_filter == 'completed':
        trips = trips.filter(is_completed=True)
    elif status_filter == 'in_progress':
        trips = trips.filter(is_completed=False)
    if date_from:
        trips = trips.filter(trip_date__gte=date_from)
    if date_to:
        trips = trips.filter(trip_date__lte=date_to)
    
    # Calculate statistics
    from datetime import timedelta
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    
    total_trips = Trip.objects.count()
    completed_trips = Trip.objects.filter(is_completed=True).count()
    in_progress_trips = total_trips - completed_trips
    
    # Total revenue
    total_revenue = Transaction.objects.filter(
        transaction_type='SALE'
    ).aggregate(
        total=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
    )['total'] or 0
    
    # Daily average trips
    daily_avg_trips = Trip.objects.filter(
        trip_date__gte=thirty_days_ago
    ).count() / 30.0
    
    # Completion rate
    completion_rate = (completed_trips / max(total_trips, 1)) * 100
    
    # Vessel performance
    vessel_performance = []
    for vessel in Vessel.objects.filter(active=True):
        vessel_trips = Trip.objects.filter(
            vessel=vessel,
            trip_date__gte=thirty_days_ago,
            is_completed=True
        ).count()
        
        vessel_revenue = Transaction.objects.filter(
            vessel=vessel,
            transaction_type='SALE',
            transaction_date__gte=thirty_days_ago
        ).aggregate(
            total=Sum(F('unit_price') * F('quantity'), output_field=models.DecimalField())
        )['total'] or 0
        
        avg_trips_month = vessel_trips / 30.0 * 30  # Monthly average
        
        vessel_performance.append({
            'vessel': vessel,
            'trips_count': vessel_trips,
            'revenue': vessel_revenue,
            'avg_trips_month': avg_trips_month,
            'performance_class': 'high' if avg_trips_month > 15 else 'medium' if avg_trips_month > 10 else 'low'
        })
    
    # Enhanced trip data
    trip_data = []
    for trip in trips[:50]:  # Limit for performance
        # Calculate revenue and items
        trip_revenue = trip.total_revenue
        items_sold = trip.sales_transactions.aggregate(
            total_items=Sum('quantity')
        )['total_items'] or 0
        
        revenue_per_passenger = trip_revenue / max(trip.passenger_count, 1)
        
        # Filter by min revenue if specified
        if min_revenue and trip_revenue < float(min_revenue):
            continue
            
        trip_data.append({
            'trip': trip,
            'revenue': trip_revenue,
            'items_sold': items_sold,
            'revenue_per_passenger': revenue_per_passenger,
            'performance_class': 'high' if revenue_per_passenger > 15 else 'medium' if revenue_per_passenger > 8 else 'low'
        })
    
    context = {
        'trip_data': trip_data,
        'vessels': Vessel.objects.filter(active=True).order_by('name'),
        'vessel_performance': vessel_performance,
        'stats': {
            'total_trips': total_trips,
            'completed_trips': completed_trips,
            'in_progress_trips': in_progress_trips,
            'total_revenue': total_revenue,
            'daily_avg_trips': daily_avg_trips,
            'completion_rate': completion_rate,
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