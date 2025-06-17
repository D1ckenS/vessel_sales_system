def language_context(request):
    """Add language context to all templates"""
    
    # Get current language preference from session or default to English
    current_language = request.session.get('preferred_language', 'en')
    
    # Detect if user prefers RTL
    is_rtl = current_language == 'ar'
    
    return {
        'CURRENT_LANGUAGE': current_language,
        'IS_RTL': is_rtl,
        'LANGUAGE_DIRECTION': 'rtl' if is_rtl else 'ltr',
        'AVAILABLE_LANGUAGES': [
            {'code': 'en', 'name': 'English', 'native': 'English'},
            {'code': 'ar', 'name': 'Arabic', 'native': 'العربية'},
        ]
    }
    
def user_permissions_context(request):
    """Add user permissions to template context"""
    if not request.user.is_authenticated:
        return {
            'user_role': None,
            'user_permissions': {
                'is_superuser': False,
                'is_admin_or_manager': False,
                'can_access_operations': False,
                'can_access_reports': False,
                'can_access_inventory': False,
                'can_add_products': False,
                'can_view_financials': False,
                'can_edit_selling_prices': False,
                'can_access_system_setup': False,
            }
        }
    
    # Import permissions functions
    from .permissions import (
        get_user_role,
        is_superuser_only,
        is_admin_or_manager,
        can_access_operations,  # This function handles sales/supply/transfers
        can_access_reports,
        can_access_inventory,
        can_add_products,
        can_view_financials,
        can_edit_selling_prices,
        can_access_system_setup,
    )
    
    return {
        'user_role': get_user_role(request.user),
        'user_permissions': {
            'is_superuser': is_superuser_only(request.user),
            'is_admin_or_manager': is_admin_or_manager(request.user),
            'can_access_operations': can_access_operations(request.user),  # ✅ Covers all operations
            'can_access_reports': can_access_reports(request.user),
            'can_access_inventory': can_access_inventory(request.user),
            'can_add_products': can_add_products(request.user),
            'can_view_financials': can_view_financials(request.user),
            'can_edit_selling_prices': can_edit_selling_prices(request.user),
            'can_access_system_setup': can_access_system_setup(request.user),
        }
    }