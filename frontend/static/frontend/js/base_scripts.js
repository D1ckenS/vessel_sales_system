/* =============================================================================
   Vessel Sales System - Base Scripts
   Translation Bridge System & Core JavaScript Functionality
   ============================================================================= */

/* =============================================================================
   Translation Bridge System
   ============================================================================= */

class TranslationBridge {
    constructor() {
        this.currentLanguage = 'en';
        this.translations = {};
        // Initialize without calling non-existent methods
        this.detectLanguage();
    }

    detectLanguage() {
        // Get language from HTML lang attribute or localStorage
        const htmlLang = document.documentElement.lang || 'en';
        const savedLang = localStorage.getItem('preferred_language') || htmlLang;
        this.currentLanguage = savedLang;
    }

    // Set translations from external file
    setTranslations(translations) {
        this.translations = translations;
    }

    // Get translated string with optional parameters
    _(key, params = {}) {
        const translation = this.translations[this.currentLanguage]?.[key] || key;
        return this.interpolate(translation, params);
    }

    // Replace {param} placeholders in strings
    interpolate(str, params) {
        return str.replace(/\{(\w+)\}/g, (match, key) => {
            return params[key] !== undefined ? params[key] : match;
        });
    }

    // Switch language - THIS IS THE KEY METHOD
    setLanguage(lang) {
        this.currentLanguage = lang;
        localStorage.setItem('preferred_language', lang);
        this.updateDynamicContent();
    }

    // Update dynamic content after language change
    updateDynamicContent() {
        document.querySelectorAll('[data-translate]').forEach(element => {
            const key = element.getAttribute('data-translate');
            const params = element.getAttribute('data-translate-params');
            const parsedParams = params ? JSON.parse(params) : {};
            element.textContent = this._(key, parsedParams);
        });
    }

    // Confirmation dialogs with translation support
    confirm(messageKey, params = {}) {
        const message = this._(messageKey, params);
        return confirm(message);
    }

    alert(messageKey, params = {}) {
        const message = this._(messageKey, params);
        alert(message);
    }
}

/**
 * MonthTranslator Class - Handles all month-related translations
 */
class MonthTranslator {
    constructor() {
        this.monthMappings = {
            // English abbreviations to full Arabic names
            'Jan': { en: 'Jan', ar: 'يناير' },
            'Feb': { en: 'Feb', ar: 'فبراير' },
            'Mar': { en: 'Mar', ar: 'مارس' },
            'Apr': { en: 'Apr', ar: 'أبريل' },
            'May': { en: 'May', ar: 'مايو' },
            'Jun': { en: 'Jun', ar: 'يونيو' },
            'Jul': { en: 'Jul', ar: 'يوليو' },
            'Aug': { en: 'Aug', ar: 'أغسطس' },
            'Sep': { en: 'Sep', ar: 'سبتمبر' },
            'Oct': { en: 'Oct', ar: 'أكتوبر' },
            'Nov': { en: 'Nov', ar: 'نوفمبر' },
            'Dec': { en: 'Dec', ar: 'ديسمبر' }
        };

        // Reverse mapping for Arabic to English
        this.arabicToEnglish = {};
        Object.keys(this.monthMappings).forEach(key => {
            this.arabicToEnglish[this.monthMappings[key].ar] = key;
        });

        // Full month names
        this.fullMonthNames = {
            'January': { en: 'January', ar: 'يناير' },
            'February': { en: 'February', ar: 'فبراير' },
            'March': { en: 'March', ar: 'مارس' },
            'April': { en: 'April', ar: 'أبريل' },
            'May': { en: 'May', ar: 'مايو' },
            'June': { en: 'June', ar: 'يونيو' },
            'July': { en: 'July', ar: 'يوليو' },
            'August': { en: 'August', ar: 'أغسطس' },
            'September': { en: 'September', ar: 'سبتمبر' },
            'October': { en: 'October', ar: 'أكتوبر' },
            'November': { en: 'November', ar: 'نوفمبر' },
            'December': { en: 'December', ar: 'ديسمبر' }
        };
    }

    /**
     * Translate month abbreviation or full name
     */
    translateMonth(month, targetLang = 'en') {
        // Check abbreviations first
        if (this.monthMappings[month]) {
            return this.monthMappings[month][targetLang];
        }
        
        // Check full names
        if (this.fullMonthNames[month]) {
            return this.fullMonthNames[month][targetLang];
        }
        
        // Check if it's an Arabic month that needs conversion to English
        if (this.arabicToEnglish[month]) {
            const englishAbbr = this.arabicToEnglish[month];
            return this.monthMappings[englishAbbr][targetLang];
        }
        
        // Return original if not found
        return month;
    }

    /**
     * Extract and translate month-year combinations
     */
    translateMonthYear(text, targetLang = 'en') {
        const monthYearMatch = text.match(/^([A-Za-z\u0600-\u06FF]+)\s+(\d{4}|[٠-٩]{4})$/);
        
        if (!monthYearMatch) return text;
        
        const monthPart = monthYearMatch[1];
        const yearPart = monthYearMatch[2];
        
        // Translate month
        const translatedMonth = this.translateMonth(monthPart, targetLang);
        
        // Translate year numbers
        let translatedYear = yearPart;
        if (targetLang === 'ar') {
            translatedYear = window.translateNumber ? window.translateNumber(yearPart) : yearPart;
        } else {
            // Convert Arabic numerals back to English
            translatedYear = yearPart.replace(/[٠-٩]/g, (char) => {
                const arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
                return arabicNumerals.indexOf(char).toString();
            });
        }
        
        return `${translatedMonth} ${translatedYear}`;
    }

    /**
     * Handle month-year elements with proper data storage
     */
    handleMonthYearElement(element) {
        const text = element.textContent.trim();
        const currentLang = window.translator ? window.translator.currentLanguage : 'en';
        
        // Store original English values if not already stored
        if (!element.getAttribute('data-original-month-year')) {
            // Determine if current text is in Arabic or English
            const monthYearMatch = text.match(/^([A-Za-z\u0600-\u06FF]+)\s+(\d{4}|[٠-٩]{4})$/);
            if (monthYearMatch) {
                const monthPart = monthYearMatch[1];
                const yearPart = monthYearMatch[2];
                
                // Convert to English for storage
                let englishMonth = monthPart;
                if (this.arabicToEnglish[monthPart]) {
                    englishMonth = this.arabicToEnglish[monthPart];
                }
                
                const englishYear = yearPart.replace(/[٠-٩]/g, (char) => {
                    const arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
                    return arabicNumerals.indexOf(char).toString();
                });
                
                element.setAttribute('data-original-month-year', `${englishMonth} ${englishYear}`);
            }
        }
        
        // Get stored original and translate
        const originalText = element.getAttribute('data-original-month-year');
        if (originalText) {
            const translatedText = this.translateMonthYear(originalText, currentLang);
            element.textContent = translatedText;
        }
    }

    /**
     * Process all month-year elements in the page
     */
    translateAllMonthYearElements(selector = null) {
        const selectors = selector ? [selector] : [
            '.col-md-4.col-sm-6 .text-center small.text-muted', // Revenue trends
            '.month-year', // Generic class for month-year elements
            '[data-month-year]' // Elements with month-year data attribute
        ];
        
        selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(element => {
                // Only process if it looks like month-year content
                const text = element.textContent.trim();
                if (/^([A-Za-z\u0600-\u06FF]+)\s+(\d{4}|[٠-٩]{4})$/.test(text)) {
                    this.handleMonthYearElement(element);
                }
            });
        });
    }
}

// Initialize global MonthTranslator instance
window.monthTranslator = new MonthTranslator();

/* =============================================================================
   Global Instances & Shorthand Functions
   ============================================================================= */

// Create global translation instance
window.translator = new TranslationBridge();

// Create global shorthand functions
window._ = function(key, params) {
    return window.translator._(key, params);
};

/* =============================================================================
   Custom Modal System
   ============================================================================= */

// Custom styled confirmation dialog
window.confirmTranslated = function(key, params) {
    return new Promise((resolve) => {
        const message = window.translator._(key, params);
        const modal = new bootstrap.Modal(document.getElementById('confirmationModal'));
        
        // Set message
        document.getElementById('confirmationMessage').textContent = message;
        
        // Handle buttons
        const confirmBtn = document.getElementById('confirmationConfirm');
        const cancelBtn = document.getElementById('confirmationCancel');
        
        // Remove old event listeners
        const newConfirmBtn = confirmBtn.cloneNode(true);
        const newCancelBtn = cancelBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
        cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);
        
        // Add new event listeners
        newConfirmBtn.addEventListener('click', () => {
            modal.hide();
            resolve(true);
        });
        
        newCancelBtn.addEventListener('click', () => {
            modal.hide();
            resolve(false);
        });
        
        // Handle backdrop click and escape key
        document.getElementById('confirmationModal').addEventListener('hidden.bs.modal', () => {
            resolve(false);
        }, { once: true });
        
        modal.show();
    });
};

// Custom styled alert dialog
window.alertTranslated = function(key, params) {
    return new Promise((resolve) => {
        const message = window.translator._(key, params);
        const modal = new bootstrap.Modal(document.getElementById('alertModal'));
        
        // Set message
        document.getElementById('alertMessage').textContent = message;
        
        // Handle OK button
        const okBtn = document.getElementById('alertOk');
        const newOkBtn = okBtn.cloneNode(true);
        okBtn.parentNode.replaceChild(newOkBtn, okBtn);
        
        newOkBtn.addEventListener('click', () => {
            modal.hide();
            resolve();
        });
        
        // Handle backdrop click and escape key
        document.getElementById('alertModal').addEventListener('hidden.bs.modal', () => {
            resolve();
        }, { once: true });
        
        modal.show();
    });
};

// Backward compatibility - update existing confirm/alert calls
window.showStyledConfirm = window.confirmTranslated;
window.showStyledAlert = window.alertTranslated;

/* =============================================================================
   Number & Currency Translation
   ============================================================================= */

// Number formatting for different languages
window.translateNumber = function(number) {
    const currentLang = window.translator ? window.translator.currentLanguage : 'en';
    
    if (currentLang === 'ar') {
        // Arabic-Indic numerals
        const arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
        return number.toString().replace(/[0-9]/g, (w) => arabicNumerals[+w]);
    }
    
    return number.toString(); // English numerals
};

// Format currency for different languages
window.translateCurrency = function(amount) {
    const currentLang = window.translator ? window.translator.currentLanguage : 'en';
    const translatedNumber = translateNumber(amount);
    
    if (currentLang === 'ar') {
        return translatedNumber + ' دينار'; // Arabic currency
    }
    
    return translatedNumber + ' JOD'; // English currency
};

// Helper function to update number elements
window.updateNumberElement = function(elementId, value) {
    const element = document.getElementById(elementId);
    if (element) {
        element.setAttribute('data-original', value.toString());
        const translatedNumber = translateNumber(value.toString());
        element.textContent = translatedNumber;
    }
};

/* =============================================================================
   Transaction Type Translation
   ============================================================================= */

// Transaction type translation helper
window.translateTransactionType = function(type) {
    // Map original transaction types to translation keys
    const typeMap = {
        'Sale': 'transaction_sale',
        'Supply': 'transaction_supply',
        'Transfer Out': 'transaction_transfer_out',
        'Transfer In': 'transaction_transfer_in',
        'Supply (Stock Received)': 'transaction_supply_received',
        'Sale (Sold to Customers)': 'transaction_sale_customers',
        'Transfer Out (Sent to Another Vessel)': 'transaction_transfer_out_vessel',
        'Transfer In (Received from Another Vessel)': 'transaction_transfer_in_vessel'
    };
    
    const translationKey = typeMap[type];
    return translationKey ? window.translator._(translationKey) : type;
};

/* =============================================================================
   🔧 FIXED Language Toggle System
   ============================================================================= */

// Language toggle function - CORRECTED VERSION
// 🔧 FIXED toggleLanguage function in base_scripts.js
// Language toggle function - CORRECTED VERSION
window.toggleLanguage = function() {
    console.log('🔄 toggleLanguage called');
    
    const currentLang = window.translator ? window.translator.currentLanguage : 
                       (document.documentElement.dir === 'rtl' ? 'ar' : 'en');
    const newLang = currentLang === 'en' ? 'ar' : 'en';
    
    console.log('Switching from', currentLang, 'to', newLang);
    
    // Update HTML attributes
    document.documentElement.dir = newLang === 'ar' ? 'rtl' : 'ltr';
    document.documentElement.lang = newLang;
    
    // Update body class for RTL layout
    if (newLang === 'ar') {
        document.body.classList.add('rtl-layout');
    } else {
        document.body.classList.remove('rtl-layout');
    }
    
    // Update translator state
    if (window.translator) {
        window.translator.currentLanguage = newLang;
        localStorage.setItem('preferred_language', newLang);
    }
    
    // Update language button (show opposite language)
    const btn = document.getElementById('currentLangText');
    if (btn) {
        btn.textContent = newLang === 'en' ? 'AR' : 'EN';
    }
    
    // 🎯 CRITICAL: Always call updatePageTranslations immediately
    console.log('🔄 Calling updatePageTranslations...');
    if (typeof updatePageTranslations === 'function') {
        updatePageTranslations();
    } else {
        console.log('⚠️ updatePageTranslations not found, using manual updates');
        manualTranslationUpdate(newLang);
    }
    
    // 🔥 IMPORTANT: Dispatch languageChanged event for templates
    console.log('📢 Dispatching languageChanged event');
    window.dispatchEvent(new Event('languageChanged'));
    
    // Also dispatch with a slight delay for any delayed operations
    setTimeout(() => {
        window.dispatchEvent(new Event('languageChanged'));
    }, 50);
    
    console.log('✅ Language toggle completed');
};

// Enhanced manual translation function for fallback
function manualTranslationUpdate(newLang) {
    const translations = {
        'ar': {
            'active': 'نشط',
            'inactive': 'غير نشط',
            'vessel_status': 'حالة السفن',
            'dashboard': 'لوحة التحكم',
            'sales_entry': 'إدخال المبيعات',
            'receive_stock': 'استلام البضائع',
            'inventory': 'إدارة المخزون',
            'transfers': 'التحويلات',
            'reports': 'التقارير',
            'transfer_entry': 'إدخال التحويل',
            'completed': 'مكتمل',
            'in_progress': 'قيد التنفيذ',
            'view': 'عرض',
            'add_sales': 'إضافة مبيعات',
            'add_items': 'إضافة عناصر'
        },
        'en': {
            'active': 'Active',
            'inactive': 'Inactive', 
            'vessel_status': 'Vessel Status',
            'dashboard': 'Dashboard',
            'sales_entry': 'Sales Entry',
            'receive_stock': 'Receive Stock',
            'inventory': 'Inventory',
            'transfers': 'Transfers',
            'reports': 'Reports',
            'transfer_entry': 'Transfer Entry',
            'completed': 'Completed',
            'in_progress': 'In Progress',
            'view': 'View',
            'add_sales': 'Add Sales',
            'add_items': 'Add Items'
        }
    };
    
    // Update all data-translate elements including the crucial badges
    Object.keys(translations[newLang]).forEach(key => {
        document.querySelectorAll(`[data-translate="${key}"]`).forEach(el => {
            el.textContent = translations[newLang][key];
            console.log(`✅ Updated ${key}: "${translations[newLang][key]}"`);
        });
    });
    
    // Update vessel names
    document.querySelectorAll('.vessel-name').forEach(element => {
        const enName = element.getAttribute('data-en');
        const arName = element.getAttribute('data-ar');
        
        if (newLang === 'ar' && arName) {
            element.textContent = arName;
        } else if (enName) {
            element.textContent = enName;
        }
    });
    
    // Force update numbers if translateNumber function exists
    if (window.translateNumber) {
        document.querySelectorAll('[data-number], .po-number, .trip-number').forEach(element => {
            const originalValue = element.getAttribute('data-original') || element.textContent.trim();
            if (!element.getAttribute('data-original')) {
                element.setAttribute('data-original', originalValue);
            }
            
            if (newLang === 'ar') {
                element.textContent = window.translateNumber(originalValue);
            } else {
                element.textContent = originalValue;
            }
        });
    }
}


/* =============================================================================
   Translation Update Functions
   ============================================================================= */

// Update page translations function
window.updatePageTranslations = function() {
    console.log('🔄 updatePageTranslations called - Current language:', window.translator.currentLanguage);
    
    // Update elements with data-translate attribute
    document.querySelectorAll('[data-translate]').forEach(element => {
        const key = element.getAttribute('data-translate');
        const params = element.getAttribute('data-translate-params');
        const parsedParams = params ? JSON.parse(params) : {};
        const translation = window.translator._(key, parsedParams);
        element.textContent = translation;
        
        // Debug specific badges
        if (key === 'active' || key === 'inactive') {
            console.log(`🔧 Updated ${key}: "${translation}"`);
        }
    });
    
    // Update vessel names based on current language
    document.querySelectorAll('.vessel-name').forEach(element => {
        const currentLang = window.translator.currentLanguage;
        const enName = element.getAttribute('data-en');
        const arName = element.getAttribute('data-ar');
        
        if (currentLang === 'ar' && arName) {
            element.textContent = arName;
        } else if (enName){
            element.textContent = enName;
        }
    });

    // Update transaction types immediately
    document.querySelectorAll('.transaction-type').forEach(element => {
        const originalType = element.getAttribute('data-type') || element.textContent;
        if (!element.getAttribute('data-type')) {
            element.setAttribute('data-type', originalType);
        }
        element.textContent = translateTransactionType(originalType);
    });

    // Update placeholders based on current language
    document.querySelectorAll('[data-placeholder-en]').forEach(element => {
        const currentLang = window.translator.currentLanguage;
        const enPlaceholder = element.getAttribute('data-placeholder-en');
        const arPlaceholder = element.getAttribute('data-placeholder-ar');
        
        if (currentLang === 'ar' && arPlaceholder) {
            element.placeholder = arPlaceholder;
        } else {
            element.placeholder = enPlaceholder;
        }
    });

    // 🔧 ENHANCED: Re-translate all elements with data-number attribute
    document.querySelectorAll('[data-number]').forEach(element => {
        const originalValue = element.getAttribute('data-original') || element.textContent.trim();
        if (!element.getAttribute('data-original')) {
            element.setAttribute('data-original', originalValue);
        }
        
        // Clean the original value to extract just the number
        const numberMatch = originalValue.match(/[\d,]+\.?\d*/);
        if (numberMatch) {
            const translatedNumber = translateNumber(numberMatch[0].replace(/,/g, ''));
            element.textContent = originalValue.replace(numberMatch[0], translatedNumber);
        } else {
            // For simple numbers without additional text
            element.textContent = translateNumber(originalValue);
        }
    });

    // 🔧 Handle date translations (trips, POs, transfers)
    ['trip', 'po', 'transfer'].forEach(type => {
        document.querySelectorAll(`[data-${type}-date]`).forEach(element => {
            const originalDate = element.getAttribute('data-original') || element.textContent.trim();
            if (!element.getAttribute('data-original')) {
                element.setAttribute('data-original', originalDate);
            }
            
            // Translate numbers in date format (DD/MM/YYYY)
            const currentLang = window.translator.currentLanguage;
            if (currentLang === 'ar') {
                const translatedDate = originalDate.replace(/\d/g, (digit) => {
                    const arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
                    return arabicNumerals[parseInt(digit)];
                });
                element.textContent = translatedDate;
            } else {
                element.textContent = originalDate;
            }
        });
    });

    // Update currency and currency symbols
    document.querySelectorAll('[data-currency-symbol]').forEach(element => {
        const currentLang = window.translator.currentLanguage;
        if (currentLang === 'ar') {
            element.textContent = 'دينار';
        } else {
            element.textContent = 'JOD';
        }
    });

    // Update transaction numbers and currency
    document.querySelectorAll('.transaction-quantity, .transaction-amount').forEach(element => {
        const originalValue = element.getAttribute('data-original') || element.textContent;
        const translatedNumber = translateNumber(originalValue);
        element.textContent = translatedNumber;
    });

    // ✅ CRITICAL FIX: More precise time-ago translation processing
    // Only process elements that are specifically marked as time-ago elements
    document.querySelectorAll('.transaction-time[data-time], .po-time-ago[data-time], [data-time-ago]').forEach(element => {
        const originalTime = element.getAttribute('data-time') || element.getAttribute('data-time-ago');
        const currentLang = window.translator.currentLanguage;
        
        if (currentLang === 'ar') {
            // Convert common English time phrases to Arabic (handle plurals)
            let arabicTime = originalTime
                .replace(/(\d+)\s*days?/g, (match, num) => translateNumber(num) + ' يوم')
                .replace(/(\d+)\s*hours?/g, (match, num) => translateNumber(num) + ' ساعة') 
                .replace(/(\d+)\s*minutes?/g, (match, num) => translateNumber(num) + ' دقيقة')
                .replace(/(\d+)\s*weeks?/g, (match, num) => translateNumber(num) + ' أسبوع')
                .replace(/(\d+)\s*months?/g, (match, num) => translateNumber(num) + ' شهر')
                .replace(/(\d+)\s*years?/g, (match, num) => translateNumber(num) + ' سنة')
                .replace(/,\s*/g, '، ')  // Replace comma with Arabic comma
                .replace(/\s+/g, ' ')  // Clean up extra spaces
                .trim();
            
            // Add "مضت" if not already there
            if (!arabicTime.includes('مضت')) {
                arabicTime += ' مضت';
            }
            
            element.textContent = arabicTime;
        } else {
            // For English, ensure "ago" is present
            const timeWithoutAgo = originalTime.replace(' ago', '').replace(' مضت', '');
            element.textContent = timeWithoutAgo + ' ago';
        }
    });

    // ✅ REMOVED: The problematic broad small.text-muted processing
    // This was causing issues with elements like "Last 90 days" getting "ago" added incorrectly
    
    // Update numbers with Arabic-Indic numerals
    ['.po-number', '.trip-number', '.count'].forEach(selector => {
        document.querySelectorAll(selector).forEach(element => {
            const originalValue = element.getAttribute('data-original') || element.textContent.trim();
            if (!element.getAttribute('data-original')) {
                element.setAttribute('data-original', originalValue);
            }
            if (window.translator.currentLanguage === 'ar') {
                const translatedNumber = window.translateNumber(originalValue);
                element.textContent = translatedNumber;
            } else {
                element.textContent = originalValue;
            }
        });
    });

    // 🔧 Handle title translations (for tooltips and button titles)
    document.querySelectorAll('[data-translate-title]').forEach(element => {
        const key = element.getAttribute('data-translate-title');
        const translatedTitle = window.translator._(key);
        element.setAttribute('title', translatedTitle);
    });

    // 🔧 Update select option text (for dropdowns)
    document.querySelectorAll('select option span[data-translate]').forEach(element => {
        const key = element.getAttribute('data-translate');
        element.textContent = window.translator._(key);
    });

    // 🔧 Recalculate revenue per passenger when language changes
    if (typeof calculateRevenuePerPassenger === 'function') {
        calculateRevenuePerPassenger();
    }
    
    // Update modal button text
    const cancelSpan = document.querySelector('#confirmationCancel span');
    const confirmSpan = document.querySelector('#confirmationConfirm span');
    const okSpan = document.querySelector('#alertOk span');
    
    if (cancelSpan) cancelSpan.textContent = _('cancel');
    if (confirmSpan) confirmSpan.textContent = _('confirm');
    if (okSpan) okSpan.textContent = _('ok');
};

/* =============================================================================
   Export System
   ============================================================================= */

// Get cookie helper function
window.getCookie = function(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
};

// Global export function
window.exportData = function(exportType, format, additionalData = {}) {
    // Show loading state
    const btn = event.target.closest('button');
    const originalHtml = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> ' + _('exporting');
    btn.disabled = true;
    
    // Determine endpoint based on export type
    let endpoint;
    switch(exportType) {
        case 'inventory':
            endpoint = '/export/inventory/';
            break;
        case 'transactions':
            endpoint = '/export/transactions/';
            break;
        case 'trips':
            endpoint = '/export/trips/';
            break;
        case 'purchase_orders':
            endpoint = '/export/purchase-orders/';
            break;
        case 'monthly_report':
            endpoint = '/export/monthly-report/';
            break;
        case 'daily_report':
            endpoint = '/export/daily-report/';
            break;
        case 'analytics_report':
            endpoint = '/export/analytics/';
            break;
        default:
            alertTranslated('export_type_not_supported');
            btn.innerHTML = originalHtml;
            btn.disabled = false;
            return;
    }
    
    // Prepare request data
    const requestData = {
        format: format, // 'excel' or 'pdf'
        ...additionalData
    };
    
    // Make request
    fetch(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || getCookie('csrftoken'),
        },
        body: JSON.stringify(requestData)
    })
    .then(response => {
        if (response.ok) {
            // Handle file download
            const contentDisposition = response.headers.get('Content-Disposition');
            const filename = contentDisposition ? 
                contentDisposition.split('filename=')[1].replace(/"/g, '') : 
                `export_${Date.now()}.${format === 'excel' ? 'xlsx' : 'pdf'}`;
            
            return response.blob().then(blob => {
                // Create download link
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                
                alertTranslated('export_successful', { filename: filename });
            });
        } else {
            return response.json().then(data => {
                throw new Error(data.error || 'Export failed');
            });
        }
    })
    .catch(error => {
        console.error('Export error:', error);
        alertTranslated('export_failed', { error: error.message });
    })
    .finally(() => {
        btn.innerHTML = originalHtml;
        btn.disabled = false;
    });
};

// Export modal function
window.showExportModal = function(exportType, additionalData = {}) {
    // Avoid conflicts with trip/po specific modals
    if (exportType === 'single_trip' || exportType === 'single_po') {
        console.warn('Use showTripExportModal or showPOExportModal for single exports');
        return;
    }
    
    const modalHtml = `
    <div class="modal fade" id="exportModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">
                        <i class="bi bi-download"></i> <span data-translate="export_data">Export Data</span>
                    </h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <p><span data-translate="choose_export_format">Choose your preferred export format:</span></p>
                    <div class="d-grid gap-2">
                        <button class="btn btn-success" onclick="exportData('${exportType}', 'excel', ${JSON.stringify(additionalData).replace(/"/g, '&quot;')}); bootstrap.Modal.getInstance(document.getElementById('exportModal')).hide();">
                            <i class="bi bi-file-earmark-excel"></i> <span data-translate="export_to_excel">Export to Excel (.xlsx)</span>
                        </button>
                        <button class="btn btn-danger" onclick="exportData('${exportType}', 'pdf', ${JSON.stringify(additionalData).replace(/"/g, '&quot;')}); bootstrap.Modal.getInstance(document.getElementById('exportModal')).hide();">
                            <i class="bi bi-file-earmark-pdf"></i> <span data-translate="export_to_pdf">Export to PDF</span>
                        </button>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                        <span data-translate="cancel">Cancel</span>
                    </button>
                </div>
            </div>
        </div>
    </div>
    `;
    
    // Remove existing modal if present
    const existingModal = document.getElementById('exportModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add modal to page
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Apply translations
    if (window.updatePageTranslations) {
        window.updatePageTranslations();
    }
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('exportModal'));
    modal.show();
    
    // Clean up when modal is hidden
    document.getElementById('exportModal').addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
};

/* =============================================================================
   Coming Soon Functions
   ============================================================================= */

function showComingSoon(feature) {
    // Map features to translation keys
    const featureMap = {
        'vessel_management': 'coming_soon_vessel_management',
        'product_management': 'coming_soon_product_management', 
        'trip_management': 'coming_soon_trip_management',
        'po_management': 'coming_soon_po_management'
    };
    
    const translationKey = featureMap[feature];
    const message = translationKey ? window.translator._(translationKey) : `${feature} feature coming soon!`;
    alert(message);
}

/* =============================================================================
   Global Translation Data & Initialization
   ============================================================================= */

// 🔧 ENHANCED INITIALIZATION WITH EXTERNAL TRANSLATIONS
document.addEventListener('DOMContentLoaded', function() {
    const savedLang = localStorage.getItem('preferred_language') || 'en';
    const langButton = document.getElementById('currentLangText');
    
    console.log('🚀 Initializing language system with:', savedLang);
    
    // Fix Issue 2: Show target language (opposite of current)
    if (langButton) {
        const targetLang = savedLang === 'en' ? 'AR' : 'EN';
        langButton.textContent = targetLang;
    }
    
    // Apply RTL for Arabic
    if (savedLang === 'ar') {
        document.body.classList.add('rtl-layout');
        document.documentElement.dir = 'rtl';
        document.documentElement.lang = 'ar';
    } else {
        document.body.classList.remove('rtl-layout');
        document.documentElement.dir = 'ltr';
        document.documentElement.lang = 'en';
    }
    
    // ✅ USE EXTERNAL TRANSLATIONS FILE
    if (window.VesselSalesTranslations) {
        window.translator.setTranslations(window.VesselSalesTranslations);
        console.log('✅ External translations loaded successfully');
    } else {
        console.error('❌ External translations not found! Make sure translations.js is loaded before base_scripts.js');
        return;
    }
    
    // Set current language
    window.translator.currentLanguage = savedLang;
    
    // Apply translations after page load
    setTimeout(() => {
        updatePageTranslations();
    }, 0);
    
    console.log('🎯 Language system initialized successfully');
});

window.cleanupModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        // Hide modal if it's still showing
        const bsModal = bootstrap.Modal.getInstance(modal);
        if (bsModal) {
            bsModal.hide();
        }
        // Remove from DOM after a short delay
        setTimeout(() => {
            if (modal.parentNode) {
                modal.parentNode.removeChild(modal);
            }
        }, 300);
    }
};