from .permissions import is_admin_or_manager
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from .utils import BilingualMessages
from products.models import Category

@login_required
@user_passes_test(is_admin_or_manager) 
def category_management(request):
    """Category management interface"""
    
    categories = Category.objects.annotate(
        product_count=Count('product'),
        active_product_count=Count('product', filter=Q(product__active=True))
    ).order_by('name')
    
    context = {
        'categories': categories,
    }
    
    return render(request, 'frontend/category_management.html', context)

@login_required
@user_passes_test(is_admin_or_manager)
def create_category(request):
    """Create new category"""
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            active = request.POST.get('active') == 'on'
            
            if not name:
                BilingualMessages.error(request, 'category_name_required')
                return redirect('frontend:category_management')
            
            # Check if category exists
            if Category.objects.filter(name=name).exists():
                BilingualMessages.error(request, 'category_exists', name=name)
                return redirect('frontend:category_management')
            
            category = Category.objects.create(
                name=name,
                description=description,
                active=active,
                created_by=request.user
            )
            
            BilingualMessages.success(request, 'category_created_success', name=category.name)
            return redirect('frontend:category_management')
            
        except Exception as e:
            BilingualMessages.error(request, 'error_creating_category', error=str(e))
            return redirect('frontend:category_management')
    
    return redirect('frontend:category_management')

@login_required
@user_passes_test(is_admin_or_manager)
def edit_category(request, category_id):
    """Edit existing category"""
    
    if request.method == 'POST':
        try:
            category = get_object_or_404(Category, id=category_id)
            
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            active = request.POST.get('active') == 'on'
            
            if not name:
                BilingualMessages.error(request, 'category_name_required')
                return redirect('frontend:category_management')
            
            # Check if category name exists (exclude current)
            if Category.objects.filter(name=name).exclude(id=category.id).exists():
                BilingualMessages.error(request, 'category_exists', name=name)
                return redirect('frontend:category_management')
            
            category.name = name
            category.description = description
            category.active = active
            category.save()
            
            BilingualMessages.success(request, 'category_updated_success', name=category.name)
            return redirect('frontend:category_management')
            
        except Exception as e:
            BilingualMessages.error(request, 'error_updating_category', error=str(e))
            return redirect('frontend:category_management')
    
    return redirect('frontend:category_management')

@login_required
@user_passes_test(is_admin_or_manager)
def delete_category(request, category_id):
    """Delete category (if no products associated)"""
    
    if request.method == 'POST':
        try:
            category = get_object_or_404(Category, id=category_id)
            
            # Check if category has products
            if category.products.exists():
                BilingualMessages.error(request, 'category_has_products', name=category.name)
            else:
                category_name = category.name
                category.delete()
                BilingualMessages.success(request, 'category_deleted_success', name=category_name)
            
            return redirect('frontend:category_management')
            
        except Exception as e:
            BilingualMessages.error(request, 'error_deleting_category', error=str(e))
            return redirect('frontend:category_management')
    
    return redirect('frontend:category_management')