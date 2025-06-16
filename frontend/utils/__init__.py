from django.contrib import messages
from django.utils.translation import gettext as _
from django.http import JsonResponse
from django.conf import settings

class BilingualMessages:
    """
    Utility class for sending bilingual messages
    """
    
    # Message translations - Add more as needed
    MESSAGES = {
        'en': {
            # Authentication messages
            'username_password_required': 'Username and password are required.',
            'login_successful': 'Welcome back, {username}! You have successfully logged in.',
            'logout_successful': 'You have been successfully logged out. See you soon, {username}!',
            'invalid_credentials': 'Invalid username or password. Please try again.',
            'account_deactivated': 'Your account has been deactivated. Please contact your administrator.',
            
            # User Management
            'user_created_success': 'User "{username}" has been created successfully.',
            'user_updated_success': 'User "{username}" has been updated successfully.',
            'username_exists': 'Username "{username}" already exists. Please choose a different username.',
            'email_exists': 'Email "{email}" is already in use. Please choose a different email.',
            'passwords_do_not_match': 'Passwords do not match. Please ensure both password fields are identical.',
            'password_too_short': 'Password must be at least 6 characters long.',
            'user_not_found': 'User not found.',
            'error_creating_user': 'Error creating user: {error}',
            'error_updating_user': 'Error updating user: {error}',
            'password_reset_success': 'Password for user "{username}" has been reset successfully.',
            'error_resetting_password': 'Error resetting password: {error}',
            'cannot_deactivate_yourself': 'You cannot deactivate your own account.',
            'user_activated_success': 'User "{username}" has been activated successfully.',
            'user_deactivated_success': 'User "{username}" has been deactivated successfully.',
            'current_password_incorrect': 'Current password is incorrect.',
            'password_changed_success': 'Your password has been changed successfully.',
            'error_changing_password': 'Error changing password: {error}',
            'error_setting_up_groups': 'Error setting up groups: {error}',
            
            # Product messages
            'product_created_success': 'Product "{name}" (ID: {item_id}) created successfully.',
            'product_created_with_stock': 'Product "{name}" created with stock: {vessels}',
            'product_already_exists': 'Item ID "{item_id}" already exists. Please use a different ID.',
            'invalid_category': 'Invalid category selected.',
            'invalid_data': 'Invalid data: {error}',
            'error_creating_product': 'Error creating product: {error}',
            'required_fields_missing': 'Please fill in all required fields.',
            'purchase_date_required': 'Purchase date is required for initial stock.',
            'no_valid_stock_data': 'No valid stock data provided',
            'cannot_add_duty_free': 'Cannot add duty-free product to {vessel_name}',
            'invalid_vessel_data': 'Invalid data for {vessel_name}',
            
            # Trip messages
            'trip_created_success': 'Trip {trip_number} created successfully! Now add sales items.',
            'trip_number_exists': 'Trip number "{trip_number}" already exists. Please use a different number.',
            'passenger_count_positive': 'Passenger count must be greater than 0.',
            'trip_not_found': 'Trip not found.',
            'trip_completed_success': 'Trip {trip_number} completed successfully!',
            'error_creating_trip': 'Error creating trip: {error}',
            'invalid_vessel': 'Invalid vessel selected.',
            
            # PO messages
            'po_created_success': 'Purchase Order {po_number} created successfully! Now add supply items.',
            'po_number_exists': 'Purchase Order "{po_number}" already exists. Please use a different number.',
            'po_completed_success': 'Purchase Order {po_number} completed! {count} items received for {cost} JOD total cost.',
            'po_not_found': 'Purchase Order not found.',
            'error_creating_po': 'Error creating purchase order: {error}',
            'po_number_required': 'Please enter a purchase order number',
            
            # Transfer messages
            'transfer_session_created': 'Transfer session created successfully!',
            
            # General messages
            'invalid_request_method': 'Invalid request method.',
            'back_to_inventory': 'Back to Inventory',
            'back_to_dashboard': 'Back to Dashboard',
            
            # Vessel pricing management
            'vessel_pricing_updated': 'Vessel pricing updated successfully.',
            'vessel_pricing_removed': 'Vessel pricing removed successfully.',
            'bulk_pricing_completed': 'Bulk pricing update completed: {successful} successful, {failed} failed.',
            'pricing_copied_successfully': 'Pricing copied successfully from {source} to {target_count} vessels.',
            'no_source_pricing': 'No pricing found for source vessel {vessel}.',
            'invalid_vessel_product_combination': 'Invalid vessel-product combination for pricing.',
        },
        'ar': {
            # Authentication messages (Arabic)
            'username_password_required': 'اسم المستخدم وكلمة المرور مطلوبان.',
            'login_successful': 'مرحباً بعودتك، {username}! تم تسجيل الدخول بنجاح.',
            'logout_successful': 'تم تسجيل الخروج بنجاح. نراك قريباً، {username}!',
            'invalid_credentials': 'اسم المستخدم أو كلمة المرور غير صحيحين. يرجى المحاولة مرة أخرى.',
            'account_deactivated': 'تم إلغاء تنشيط حسابك. يرجى الاتصال بالمدير.',
            
            # User Management (Arabic)
            'user_created_success': 'تم إنشاء المستخدم "{username}" بنجاح.',
            'user_updated_success': 'تم تحديث المستخدم "{username}" بنجاح.',
            'username_exists': 'اسم المستخدم "{username}" موجود بالفعل. يرجى اختيار اسم مستخدم مختلف.',
            'email_exists': 'البريد الإلكتروني "{email}" مستخدم بالفعل. يرجى اختيار بريد إلكتروني مختلف.',
            'passwords_do_not_match': 'كلمات المرور غير متطابقة. يرجى التأكد من أن حقلي كلمة المرور متطابقان.',
            'password_too_short': 'يجب أن تكون كلمة المرور 6 أحرف على الأقل.',
            'user_not_found': 'المستخدم غير موجود.',
            'error_creating_user': 'خطأ في إنشاء المستخدم: {error}',
            'error_updating_user': 'خطأ في تحديث المستخدم: {error}',
            'password_reset_success': 'تم إعادة تعيين كلمة المرور للمستخدم "{username}" بنجاح.',
            'error_resetting_password': 'خطأ في إعادة تعيين كلمة المرور: {error}',
            'cannot_deactivate_yourself': 'لا يمكنك إلغاء تنشيط حسابك الخاص.',
            'user_activated_success': 'تم تنشيط المستخدم "{username}" بنجاح.',
            'user_deactivated_success': 'تم إلغاء تنشيط المستخدم "{username}" بنجاح.',
            'current_password_incorrect': 'كلمة المرور الحالية غير صحيحة.',
            'password_changed_success': 'تم تغيير كلمة المرور الخاصة بك بنجاح.',
            'error_changing_password': 'خطأ في تغيير كلمة المرور: {error}',
            'error_setting_up_groups': 'خطأ في إعداد المجموعات: {error}',
            
            # Product messages (Arabic)
            'product_created_success': 'تم إنشاء المنتج "{name}" (الرقم: {item_id}) بنجاح.',
            'product_created_with_stock': 'تم إنشاء المنتج "{name}" مع المخزون: {vessels}',
            'product_already_exists': 'رقم الصنف "{item_id}" موجود بالفعل. يرجى استخدام رقم مختلف.',
            'invalid_category': 'فئة غير صالحة تم اختيارها.',
            'invalid_data': 'بيانات غير صالحة: {error}',
            'error_creating_product': 'خطأ في إنشاء المنتج: {error}',
            'required_fields_missing': 'يرجى ملء جميع الحقول المطلوبة.',
            'purchase_date_required': 'تاريخ الشراء مطلوب للمخزون الأولي.',
            'no_valid_stock_data': 'لم يتم توفير بيانات مخزون صالحة',
            'cannot_add_duty_free': 'لا يمكن إضافة منتج معفى من الرسوم إلى {vessel_name}',
            'invalid_vessel_data': 'بيانات غير صالحة لـ {vessel_name}',
            
            # Trip messages (Arabic)
            'trip_created_success': 'تم إنشاء الرحلة {trip_number} بنجاح! الآن أضف عناصر المبيعات.',
            'trip_number_exists': 'رقم الرحلة "{trip_number}" موجود بالفعل. يرجى استخدام رقم مختلف.',
            'passenger_count_positive': 'عدد الركاب يجب أن يكون أكبر من 0.',
            'trip_not_found': 'الرحلة غير موجودة.',
            'trip_completed_success': 'تم إكمال الرحلة {trip_number} بنجاح!',
            'error_creating_trip': 'خطأ في إنشاء الرحلة: {error}',
            'invalid_vessel': 'سفينة غير صالحة تم اختيارها.',
            
            # PO messages (Arabic)
            'po_created_success': 'تم إنشاء أمر الشراء {po_number} بنجاح! الآن أضف عناصر التوريد.',
            'po_number_exists': 'أمر الشراء "{po_number}" موجود بالفعل. يرجى استخدام رقم مختلف.',
            'po_completed_success': 'تم إكمال أمر الشراء {po_number}! تم استلام {count} عنصر بتكلفة إجمالية {cost} دينار.',
            'po_not_found': 'أمر الشراء غير موجود.',
            'error_creating_po': 'خطأ في إنشاء أمر الشراء: {error}',
            'po_number_required': 'يرجى إدخال رقم أمر الشراء',
            
            # Transfer messages (Arabic)
            'transfer_session_created': 'تمإنشاء جلسة تحويل بنجاح. الآن قم بإضافة عناصر التحويل.',
            # General messages (Arabic)
            'invalid_request_method': 'طريقة طلب غير صالحة.',
            'back_to_inventory': 'العودة للمخزون',
            'back_to_dashboard': 'العودة للوحة التحكم',
            
            # Vessel pricing management (Arabic)
            'vessel_pricing_updated': 'تم تحديث تسعير السفينة بنجاح.',
            'vessel_pricing_removed': 'تم إزالة تسعير السفينة بنجاح.',
            'bulk_pricing_completed': 'تم إكمال التحديث الجماعي للتسعير: {successful} نجح، {failed} فشل.',
            'pricing_copied_successfully': 'تم نسخ التسعير بنجاح من {source} إلى {target_count} سفن.',
            'no_source_pricing': 'لم يتم العثور على تسعير للسفينة المصدر {vessel}.',
            'invalid_vessel_product_combination': 'مزيج غير صالح من السفينة والمنتج للتسعير.',
        }
    }

    @classmethod
    def get_user_language(cls, request):
        """
        Determine user's preferred language from multiple sources.
        
        Priority order:
        1. Session preference (for authenticated users)
        2. Custom X-User-Language header (set by JavaScript)
        3. Accept-Language header
        4. Default to English
        
        Args:
            request: Django HttpRequest object
        
        Returns:
            str: Language code ('en' or 'ar')
        """
        # Try from session first (set by authentication system)
        if hasattr(request, 'session') and 'preferred_language' in request.session:
            lang = request.session['preferred_language']
            if lang in ['en', 'ar']:
                return lang
        
        # Try from custom header (set by JavaScript)
        if 'HTTP_X_USER_LANGUAGE' in request.META:
            lang = request.META['HTTP_X_USER_LANGUAGE']
            if lang in ['en', 'ar']:
                return lang
        
        # Try from Accept-Language header
        accept_lang = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        if 'ar' in accept_lang.lower():
            return 'ar'
        
        # Default implementation for backward compatibility
        return getattr(request, 'LANGUAGE_CODE', 'en')

    @classmethod
    def get_message(cls, message_key, language='en', **kwargs):
        """Get translated message with parameter substitution"""
        messages_dict = cls.MESSAGES.get(language, cls.MESSAGES['en'])
        message_template = messages_dict.get(message_key, message_key)
        
        try:
            return message_template.format(**kwargs)
        except KeyError:
            # If parameter substitution fails, return template as-is
            return message_template

    @classmethod
    def add_message(cls, request, level, message_key, **kwargs):
        """Add bilingual message to Django messages framework"""
        language = cls.get_user_language(request)
        message_text = cls.get_message(message_key, language, **kwargs)
        messages.add_message(request, level, message_text)

    @classmethod
    def success(cls, request, message_key, **kwargs):
        """Add bilingual success message"""
        cls.add_message(request, messages.SUCCESS, message_key, **kwargs)

    @classmethod
    def error(cls, request, message_key, **kwargs):
        """Add bilingual error message"""
        cls.add_message(request, messages.ERROR, message_key, **kwargs)

    @classmethod
    def warning(cls, request, message_key, **kwargs):
        """Add bilingual warning message"""
        cls.add_message(request, messages.WARNING, message_key, **kwargs)

    @classmethod
    def info(cls, request, message_key, **kwargs):
        """Add bilingual info message"""
        cls.add_message(request, messages.INFO, message_key, **kwargs)

    @classmethod
    def json_response(cls, request, success=True, message_key=None, data=None, **kwargs):
        """Return bilingual JSON response"""
        language = cls.get_user_language(request)
        
        response_data = {
            'success': success,
            'language': language
        }
        
        if message_key:
            response_data['message'] = cls.get_message(message_key, language, **kwargs)
        
        if data:
            response_data.update(data)
            
        return JsonResponse(response_data)


# Middleware to detect user language from various sources
class LanguageDetectionMiddleware:
    """
    Middleware to detect user's preferred language from various sources
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Try to get language from various sources
        language = self.detect_language(request)
        request.LANGUAGE_CODE = language
        
        response = self.get_response(request)
        return response

    def detect_language(self, request):
        """Detect user's preferred language"""
        
        # 1. Try from session (highest priority for authenticated users)
        if hasattr(request, 'session') and 'preferred_language' in request.session:
            lang = request.session['preferred_language']
            if lang in ['en', 'ar']:
                return lang
        
        # 2. Try from custom header (set by JavaScript)
        if 'HTTP_X_USER_LANGUAGE' in request.META:
            lang = request.META['HTTP_X_USER_LANGUAGE']
            if lang in ['en', 'ar']:
                return lang
        
        # 3. Try from Accept-Language header
        accept_lang = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        if 'ar' in accept_lang.lower():
            return 'ar'
        
        # 4. Default to English
        return 'en'


# Updated views.py helper functions
def get_vessel_display_name(vessel, language='en'):
    """
    Get vessel name in specified language.
    
    Args:
        vessel: Vessel model instance
        language: Language code ('en' or 'ar')
    
    Returns:
        str: Vessel name in requested language
    """
    if language == 'ar' and vessel.name_ar:
        return vessel.name_ar
    return vessel.name

def format_vessel_list(vessels, language='en'):
    """
    Format vessel list for user messages with proper separators.
    
    Args:
        vessels: List of Vessel instances
        language: Language code ('en' or 'ar')
    
    Returns:
        str: Comma-separated vessel names with language-appropriate separator
    """
    vessel_names = [get_vessel_display_name(v, language) for v in vessels]
    if language == 'ar':
        return '، '.join(vessel_names)  # Arabic comma
    else:
        return ', '.join(vessel_names)  # English comma