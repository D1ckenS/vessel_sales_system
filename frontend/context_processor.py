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

# Enhanced base.html template additions (add these to your base.html)

# Add this to the <html> tag in base.html:
# <html lang="{{ CURRENT_LANGUAGE }}" dir="{{ LANGUAGE_DIRECTION }}">

# Add this CSS to handle RTL automatically:
"""
<style>
/* Enhanced RTL Support */
[dir="rtl"] {
    text-align: right;
}

[dir="rtl"] .navbar-nav {
    flex-direction: row-reverse;
}

[dir="rtl"] .navbar-brand {
    margin-left: auto;
    margin-right: 0;
}

[dir="rtl"] .btn-group {
    flex-direction: row-reverse;
}

[dir="rtl"] .d-flex {
    flex-direction: row-reverse;
}

[dir="rtl"] .ms-auto {
    margin-right: auto !important;
    margin-left: 0 !important;
}

[dir="rtl"] .me-auto {
    margin-left: auto !important;
    margin-right: 0 !important;
}

[dir="rtl"] .dropdown-menu {
    right: 0;
    left: auto;
}

/* Numbers in Arabic */
[dir="rtl"] .stats-number,
[dir="rtl"] .fw-bold[data-number] {
    font-family: 'Arabic-Indic', 'Tahoma', sans-serif;
}
</style>
"""

# Complete implementation checklist:

IMPLEMENTATION_CHECKLIST = """
## 🎯 COMPLETE TRANSLATION IMPLEMENTATION CHECKLIST

### ✅ COMPLETED:
1. ✅ Translation Bridge System (base.html)
2. ✅ Dashboard Quick Actions Fixed  
3. ✅ add_product.html Fully Translated
4. ✅ Bilingual Backend Messages System
5. ✅ Language Detection Middleware
6. ✅ JavaScript Language Communication
7. ✅ Backend Language Preference Endpoint

### 🔧 FINAL STEPS TO COMPLETE:

#### 1. Update All Templates (Priority: HIGH)
   - Apply translation patterns to remaining templates:
     - inventory_check.html (partially done)
     - transfer_center.html (needs review)
     - All report templates
     - Add `data-translate` to hardcoded text
     - Add `data-placeholder-en/ar` to input fields

#### 2. Replace All Views Messages (Priority: HIGH)  
   - Replace all `messages.error()` with `BilingualMessages.error()`
   - Replace all `messages.success()` with `BilingualMessages.success()` 
   - Update all AJAX JsonResponse with bilingual messages
   - Add more message translations to utils.py

#### 3. Settings Configuration (Priority: MEDIUM)
   - Add LanguageDetectionMiddleware to MIDDLEWARE
   - Add context processor to TEMPLATES
   - Create frontend/context_processors.py

#### 4. Form Validation Translation (Priority: MEDIUM)
   - Create custom form classes with bilingual error messages
   - Override Django form field error messages
   - Add client-side validation with translated messages

#### 5. Enhanced Features (Priority: LOW)
   - Add proper date formatting for Arabic
   - Add number formatting with Arabic-Indic numerals  
   - Add currency symbol translation (JOD ↔ دينار)
   - Add email notifications in user's language

### 🧪 TESTING CHECKLIST:
- [ ] Language toggle works on all pages
- [ ] All static text translates properly  
- [ ] Vessel names show in correct language
- [ ] Form placeholders translate
- [ ] Django messages appear in correct language
- [ ] AJAX responses use correct language
- [ ] RTL layout works properly
- [ ] localStorage persistence works
- [ ] Numbers display in Arabic-Indic when Arabic selected
- [ ] Page refresh maintains language choice

### 🚀 DEPLOYMENT NOTES:
- Ensure middleware is added to settings
- Create language preference migration if storing in database
- Test with different browser language settings
- Verify all static files are collected properly
"""

print(IMPLEMENTATION_CHECKLIST)