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

    // Switch language
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
 * Add this to your base_scripts.js file
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
     * @param {string} month - Month name (Jan, February, etc.)
     * @param {string} targetLang - Target language ('en' or 'ar')
     * @returns {string} Translated month name
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
     * @param {string} text - Text containing month and year (e.g., "Jan 2024")
     * @param {string} targetLang - Target language
     * @returns {string} Translated text
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
     * @param {HTMLElement} element - DOM element containing month-year text
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
     * @param {string} selector - CSS selector for elements (optional)
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
   Language Toggle System
   ============================================================================= */

// Language toggle function
window.toggleLanguage = function() {
    const currentLang = window.translator.currentLanguage;
    const newLang = currentLang === 'en' ? 'ar' : 'en';
    
    // Switch language
    window.translator.setLanguage(newLang);
    
    // Update button text
    const langButton = document.getElementById('currentLangText');
    if (langButton) {
        const targetLang = newLang === 'en' ? 'AR' : 'EN';
        langButton.textContent = targetLang;
    }
    
    // 🎯 SIMPLE: Just set the dir attribute - CSS handles the rest
    document.documentElement.lang = newLang;
    document.documentElement.dir = newLang === 'ar' ? 'rtl' : 'ltr';
    
    if (newLang === 'ar') {
        document.body.classList.add('rtl-layout');
    } else {
        document.body.classList.remove('rtl-layout');
    }
    
    // Update translations
    setTimeout(() => {
        updatePageTranslations();
    }, 100);
};

/* =============================================================================
   Translation Update Functions
   ============================================================================= */

// Update page translations function
window.updatePageTranslations = function() {
    // Update elements with data-translate attribute
    document.querySelectorAll('[data-translate]').forEach(element => {
        const key = element.getAttribute('data-translate');
        const params = element.getAttribute('data-translate-params');
        const parsedParams = params ? JSON.parse(params) : {};
        element.textContent = window.translator._(key, parsedParams);
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

    // Update currency and badges immediately
    document.querySelectorAll('.badge, [data-currency], .text-muted small').forEach(element => {
        if (element.textContent.includes('JOD')) {
            const amount = element.textContent.match(/[\d,]+\.?\d*/);
            if (amount) {
                element.textContent = element.textContent.replace(/[\d,]+\.?\d* JOD/, translateCurrency(amount[0]));
            }
        }
    });
    
    // Update "Active" badges and status text
    document.querySelectorAll('.badge').forEach(element => {
        if (element.textContent.includes('Active') || element.textContent.includes('نشط')) {
            element.innerHTML = '<span data-translate="active">Active</span>';
            const span = element.querySelector('span');
            span.textContent = window.translator._('active');
        }
    });

    // Update currency symbols
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

    // Update timesince translations
    document.querySelectorAll('.transaction-time').forEach(element => {
        const originalTime = element.getAttribute('data-time');
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
            
            // Add "مضت" if not already there and if it doesn't contain "ago"
            if (!arabicTime.includes('مضت')) {
                arabicTime += ' مضت';
            }
            
            element.textContent = arabicTime;
        } else {
            // For English, ensure "ago" is present
            const timeWithoutAgo = originalTime.replace(' ago', '');
            element.textContent = timeWithoutAgo + ' ago';
        }
    });

    // 🔧 SALES ENTRY SPECIFIC TRANSLATIONS
    // Handle trip numbers in Recent Trips table
    document.querySelectorAll('tr td:first-child strong').forEach(element => {
        if (!element.classList.contains('po-number') && !element.getAttribute('data-original')) {
            const originalValue = element.textContent.trim();
            element.setAttribute('data-original', originalValue);
            if (window.translator.currentLanguage === 'ar') {
                element.textContent = translateNumber(originalValue);
            } else {
                element.textContent = originalValue;
            }
        }
    });

    // Handle passenger counts in Recent Trips
    document.querySelectorAll('td .fw-bold').forEach(element => {
        const text = element.textContent.trim();
        if (/^\d+$/.test(text) && !element.getAttribute('data-original')) {
            element.setAttribute('data-original', text);
            element.textContent = translateNumber(text);
        }
    });

    // Handle revenue amounts in Recent Trips
    document.querySelectorAll('td span.fw-bold').forEach(element => {
        const text = element.textContent.trim();
        if (/^\d+\.?\d*$/.test(text) && !element.getAttribute('data-original')) {
            element.setAttribute('data-original', text);
            element.textContent = translateNumber(text);
        }
    });

    // Handle trip dates in Recent Trips (direct date cells)
    document.querySelectorAll('tr td').forEach(element => {
        const text = element.textContent.trim();
        if (/^\d{2}\/\d{2}\/\d{4}$/.test(text) && !element.getAttribute('data-original')) {
            element.setAttribute('data-original', text);
            if (window.translator.currentLanguage === 'ar') {
                element.textContent = translateNumber(text);
            } else {
                element.textContent = text;
            }
        }
    });

    // 🔧 TRANSFER ENTRY SPECIFIC TRANSLATIONS
    // Handle transfer dates with proper selector
    document.querySelectorAll('[data-transfer-date]').forEach(element => {
        const originalDate = element.getAttribute('data-original') || element.textContent.trim();
        if (!element.getAttribute('data-original')) {
            element.setAttribute('data-original', originalDate);
        }
        
        if (window.translator.currentLanguage === 'ar') {
            element.textContent = translateNumber(originalDate);
        } else {
            element.textContent = originalDate;
        }
    });

    // Handle transfer quantities with [data-number] attribute
    document.querySelectorAll('td small span[data-number]').forEach(element => {
        const originalValue = element.getAttribute('data-original') || element.textContent.trim();
        if (!element.getAttribute('data-original')) {
            element.setAttribute('data-original', originalValue);
        }
        element.textContent = translateNumber(originalValue);
    });

    // 🔧 PURCHASE ORDER ENTRY REFRESH FIX
    // Force update PO dates that might not be updating properly
    document.querySelectorAll('.po-date').forEach(element => {
        const originalDate = element.getAttribute('data-date') || element.getAttribute('data-original') || element.textContent.trim();
        if (!element.getAttribute('data-original')) {
            element.setAttribute('data-original', originalDate);
        }
        
        if (window.translator.currentLanguage === 'ar') {
            element.textContent = translateNumber(originalDate);
        } else {
            element.textContent = originalDate;
        }
    });

    // Force update all time-ago elements that might have different classes
    document.querySelectorAll('small.text-muted').forEach(element => {
        const text = element.textContent.trim();
        if (text.includes('ago') || text.includes('مضت') || /\d+\s+(day|hour|minute|week|month|year)/.test(text)) {
            if (!element.getAttribute('data-time')) {
                element.setAttribute('data-time', text.replace(' مضت', '').replace(' ago', ''));
            }
            
            const originalTime = element.getAttribute('data-time');
            const currentLang = window.translator.currentLanguage;
            
            if (currentLang === 'ar') {
                let arabicTime = originalTime
                    .replace(/(\d+)\s*days?/g, (match, num) => translateNumber(num) + ' يوم')
                    .replace(/(\d+)\s*hours?/g, (match, num) => translateNumber(num) + ' ساعة') 
                    .replace(/(\d+)\s*minutes?/g, (match, num) => translateNumber(num) + ' دقيقة')
                    .replace(/(\d+)\s*weeks?/g, (match, num) => translateNumber(num) + ' أسبوع')
                    .replace(/(\d+)\s*months?/g, (match, num) => translateNumber(num) + ' شهر')
                    .replace(/(\d+)\s*years?/g, (match, num) => translateNumber(num) + ' سنة')
                    .replace(/,\s*/g, '، ')
                    .replace(/\s+/g, ' ')
                    .trim();
                
                if (!arabicTime.includes('مضت')) {
                    arabicTime += ' مضت';
                }
                
                element.textContent = arabicTime;
            } else {
                const timeWithoutAgo = originalTime.replace(' ago', '').replace(' مضت', '');
                element.textContent = timeWithoutAgo + ' ago';
            }
        }
    });

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
    const modalHtml = `
        <div class="modal fade" id="exportModal" tabindex="-1">
            <div class="modal-dialog">
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
    updatePageTranslations();
    
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