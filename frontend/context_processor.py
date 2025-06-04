def language_context(request):
    """Add language context to all templates"""
    
    # Get current language preference
    current_language = getattr(request, 'LANGUAGE_CODE', 'en')
    
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