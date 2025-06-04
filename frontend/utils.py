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
            
            # General messages
            'invalid_request_method': 'Invalid request method.',
            'back_to_inventory': 'Back to Inventory',
            'back_to_dashboard': 'Back to Dashboard',
        },
        'ar': {
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
            
            # General messages (Arabic)
            'invalid_request_method': 'طريقة طلب غير صالحة.',
            'back_to_inventory': 'العودة للمخزون',
            'back_to_dashboard': 'العودة للوحة التحكم',
        }
    }

    @classmethod
    def get_user_language(cls, request):
        """Get user's preferred language from session/localStorage"""
        # This would typically come from request headers, session, or user preference
        # For now, we'll use a default implementation
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
    def success(cls, request, message_key, **kwargs):
        """Add bilingual success message"""
        language = cls.get_user_language(request)
        message = cls.get_message(message_key, language, **kwargs)
        messages.success(request, message)

    @classmethod
    def error(cls, request, message_key, **kwargs):
        """Add bilingual error message"""
        language = cls.get_user_language(request)
        message = cls.get_message(message_key, language, **kwargs)
        messages.error(request, message)

    @classmethod
    def warning(cls, request, message_key, **kwargs):
        """Add bilingual warning message"""
        language = cls.get_user_language(request)
        message = cls.get_message(message_key, language, **kwargs)
        messages.warning(request, message)

    @classmethod
    def info(cls, request, message_key, **kwargs):
        """Add bilingual info message"""
        language = cls.get_user_language(request)
        message = cls.get_message(message_key, language, **kwargs)
        messages.info(request, message)

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


# Middleware to detect user language from localStorage/headers
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
        
        # 1. Try from custom header (set by JavaScript)
        if 'HTTP_X_USER_LANGUAGE' in request.META:
            lang = request.META['HTTP_X_USER_LANGUAGE']
            if lang in ['en', 'ar']:
                return lang
        
        # 2. Try from session
        if hasattr(request, 'session') and 'preferred_language' in request.session:
            lang = request.session['preferred_language']
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
    """Get vessel name in specified language"""
    if language == 'ar' and vessel.name_ar:
        return vessel.name_ar
    return vessel.name

def format_vessel_list(vessels, language='en'):
    """Format vessel list for messages"""
    vessel_names = [get_vessel_display_name(v, language) for v in vessels]
    if language == 'ar':
        return '، '.join(vessel_names)  # Arabic comma
    else:
        return ', '.join(vessel_names)  # English comma