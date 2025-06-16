/* =============================================================================
   Vessel Sales System - Base Scripts (PRODUCTION OPTIMIZED)
   Translation Bridge System & Core JavaScript Functionality
   ============================================================================= */

/* =============================================================================
   Translation Bridge System
   ============================================================================= */

class TranslationBridge {
    constructor() {
        this.currentLanguage = 'en';
        this.translations = {};
        this.detectLanguage();
    }

    detectLanguage() {
        const htmlLang = document.documentElement.lang || 'en';
        const savedLang = localStorage.getItem('preferred_language') || htmlLang;
        this.currentLanguage = savedLang;
    }

    setTranslations(translations) {
        this.translations = translations;
    }

    _(key, params = {}) {
        const translation = this.translations[this.currentLanguage]?.[key] || key;
        return this.interpolate(translation, params);
    }

    interpolate(str, params) {
        return str.replace(/\{(\w+)\}/g, (match, key) => {
            return params[key] !== undefined ? params[key] : match;
        });
    }

    setLanguage(lang) {
        this.currentLanguage = lang;
        localStorage.setItem('preferred_language', lang);
        this.updateDynamicContent();
    }

    updateDynamicContent() {
        document.querySelectorAll('[data-translate]').forEach(element => {
            const key = element.getAttribute('data-translate');
            const params = element.getAttribute('data-translate-params');
            const parsedParams = params ? JSON.parse(params) : {};
            element.textContent = this._(key, parsedParams);
        });
    }
}

/* =============================================================================
   Month Translation System
   ============================================================================= */

class MonthTranslator {
    constructor() {
        this.monthMappings = {
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

        this.arabicToEnglish = {};
        Object.keys(this.monthMappings).forEach(key => {
            this.arabicToEnglish[this.monthMappings[key].ar] = key;
        });
    }

    translateMonth(month, targetLang = 'en') {
        if (this.monthMappings[month]) {
            return this.monthMappings[month][targetLang] || month;
        }

        const foundKey = Object.keys(this.monthMappings).find(key => 
            this.monthMappings[key].en === month || this.monthMappings[key].ar === month
        );
        
        return foundKey ? this.monthMappings[foundKey][targetLang] || month : month;
    }

    updateMonthElements(selector = null) {
        const selectors = selector ? [selector] : [
            '.col-md-4.col-sm-6 .text-center small.text-muted',
            '.month-year', 
            '[data-month-year]'
        ];
        
        selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(element => {
                const text = element.textContent.trim();
                if (/^([A-Za-z\u0600-\u06FF]+)\s+(\d{4}|[٠-٩]{4})$/.test(text)) {
                    this.handleMonthYearElement(element);
                }
            });
        });
    }

    handleMonthYearElement(element) {
        const text = element.textContent.trim();
        const parts = text.split(' ');
        
        if (parts.length === 2) {
            const month = parts[0];
            const year = parts[1];
            const currentLang = window.translator?.currentLanguage || 'en';
            
            const translatedMonth = this.translateMonth(month, currentLang);
            const translatedYear = window.translateNumber ? window.translateNumber(year) : year;
            
            element.textContent = `${translatedMonth} ${translatedYear}`;
        }
    }
}

// Initialize global instances
window.translator = new TranslationBridge();
window.monthTranslator = new MonthTranslator();

// Global shorthand function
window._ = function(key, params) {
    return window.translator._(key, params);
};

/* =============================================================================
   Custom Modal System (Using Existing Base Modals)
   ============================================================================= */

window.confirmTranslated = function(key, params) {
    return new Promise((resolve) => {
        const message = window.translator._(key, params);
        const modal = new bootstrap.Modal(document.getElementById('confirmationModal'));
        
        document.getElementById('confirmationMessage').textContent = message;
        
        const confirmBtn = document.getElementById('confirmationConfirm');
        const cancelBtn = document.getElementById('confirmationCancel');
        
        const newConfirmBtn = confirmBtn.cloneNode(true);
        const newCancelBtn = cancelBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
        cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);
        
        newConfirmBtn.addEventListener('click', () => {
            modal.hide();
            resolve(true);
        });
        
        newCancelBtn.addEventListener('click', () => {
            modal.hide();
            resolve(false);
        });
        
        document.getElementById('confirmationModal').addEventListener('hidden.bs.modal', () => {
            resolve(false);
        }, { once: true });
        
        modal.show();
    });
};

window.alertTranslated = function(key, params) {
    return new Promise((resolve) => {
        const message = window.translator._(key, params);
        const modal = new bootstrap.Modal(document.getElementById('alertModal'));
        
        document.getElementById('alertMessage').textContent = message;
        
        const okBtn = document.getElementById('alertOk');
        const newOkBtn = okBtn.cloneNode(true);
        okBtn.parentNode.replaceChild(newOkBtn, okBtn);
        
        newOkBtn.addEventListener('click', () => {
            modal.hide();
            resolve();
        });
        
        document.getElementById('alertModal').addEventListener('hidden.bs.modal', () => {
            resolve();
        }, { once: true });
        
        modal.show();
    });
};

// Backward compatibility
window.showStyledConfirm = window.confirmTranslated;
window.showStyledAlert = window.alertTranslated;

/* =============================================================================
   Number & Currency Translation
   ============================================================================= */

window.translateNumber = function(number) {
    const currentLang = window.translator?.currentLanguage || 'en';
    
    if (currentLang === 'ar') {
        const arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
        return number.toString().replace(/[0-9]/g, (w) => arabicNumerals[+w]);
    }
    
    return number.toString();
};

window.translateCurrency = function(amount) {
    const currentLang = window.translator?.currentLanguage || 'en';
    const translatedNumber = translateNumber(amount);
    
    if (currentLang === 'ar') {
        return translatedNumber + ' دينار';
    }
    
    return translatedNumber + ' JOD';
};

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

window.translateTransactionType = function(type) {
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
   OPTIMIZED Language Toggle System
   ============================================================================= */

window.toggleLanguage = function() {
    const currentLang = window.translator?.currentLanguage || 
                       (document.documentElement.dir === 'rtl' ? 'ar' : 'en');
    const newLang = currentLang === 'en' ? 'ar' : 'en';
    
    // Update HTML attributes
    document.documentElement.dir = newLang === 'ar' ? 'rtl' : 'ltr';
    document.documentElement.lang = newLang;
    
    // Update body class for RTL layout
    document.body.classList.toggle('rtl-layout', newLang === 'ar');
    
    // Update translator state
    if (window.translator) {
        window.translator.currentLanguage = newLang;
        localStorage.setItem('preferred_language', newLang);
    }
    
    // Update language button
    const btn = document.getElementById('currentLangText');
    if (btn) {
        btn.textContent = newLang === 'en' ? 'AR' : 'EN';
    }
    
    // Single optimized translation update
    if (typeof updatePageTranslations === 'function') {
        updatePageTranslations();
    } else {
        manualTranslationUpdate(newLang);
    }
    
    // Single event dispatch
    window.dispatchEvent(new Event('languageChanged'));
};

// Optimized manual translation function
function manualTranslationUpdate(newLang) {
    const translations = {
        'ar': {
            'active': 'نشط', 'inactive': 'غير نشط', 'vessel_status': 'حالة السفن',
            'dashboard': 'لوحة التحكم', 'sales_entry': 'إدخال المبيعات',
            'receive_stock': 'استلام البضائع', 'inventory': 'إدارة المخزون',
            'transfers': 'التحويلات', 'reports': 'التقارير',
            'completed': 'مكتمل', 'in_progress': 'قيد التنفيذ'
        },
        'en': {
            'active': 'Active', 'inactive': 'Inactive', 'vessel_status': 'Vessel Status',
            'dashboard': 'Dashboard', 'sales_entry': 'Sales Entry',
            'receive_stock': 'Receive Stock', 'inventory': 'Inventory',
            'transfers': 'Transfers', 'reports': 'Reports',
            'completed': 'Completed', 'in_progress': 'In Progress'
        }
    };
    
    // Batch update all translations
    Object.keys(translations[newLang]).forEach(key => {
        document.querySelectorAll(`[data-translate="${key}"]`).forEach(el => {
            el.textContent = translations[newLang][key];
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
    
    // Update numbers if needed
    if (window.translateNumber) {
        document.querySelectorAll('[data-number], .po-number, .trip-number').forEach(element => {
            const originalValue = element.getAttribute('data-original') || element.textContent.trim();
            if (!element.getAttribute('data-original')) {
                element.setAttribute('data-original', originalValue);
            }
            
            element.textContent = newLang === 'ar' ? 
                window.translateNumber(originalValue) : originalValue;
        });
    }
}

/* =============================================================================
   Global Translation Update Function
   ============================================================================= */

window.updatePageTranslations = function() {
    // Update elements with data-translate attribute
    document.querySelectorAll('[data-translate]').forEach(element => {
        const key = element.getAttribute('data-translate');
        const params = element.getAttribute('data-translate-params');
        const parsedParams = params ? JSON.parse(params) : {};
        element.textContent = window.translator._(key, parsedParams);
    });
    
    // UPDATE: Add automatic transaction type translation (NEW!)
    document.querySelectorAll('.transaction-type[data-type], .transaction-type-badge[data-type]').forEach(element => {
        const originalType = element.getAttribute('data-type');
        if (originalType && window.translateTransactionType) {
            element.textContent = window.translateTransactionType(originalType);
        }
    });
    
    // UPDATE: Also handle dropdown options with transaction types (NEW!)
    document.querySelectorAll('option[data-transaction-type]').forEach(element => {
        const originalType = element.getAttribute('data-transaction-type');
        if (originalType && window.translateTransactionType) {
            element.textContent = window.translateTransactionType(originalType);
        }
    });
    
    // Update vessel names
    document.querySelectorAll('.vessel-name').forEach(element => {
        const currentLang = window.translator?.currentLanguage || 'en';
        const enName = element.getAttribute('data-en');
        const arName = element.getAttribute('data-ar');
        
        if (currentLang === 'ar' && arName) {
            element.textContent = arName;
        } else if (enName) {
            element.textContent = enName;
        }
    });
    
    // Update numbers
    document.querySelectorAll('[data-number]').forEach(element => {
        const originalValue = element.getAttribute('data-original');
        if (originalValue) {
            const currentLang = window.translator?.currentLanguage || 'en';
            element.textContent = currentLang === 'ar' ? 
                window.translateNumber(originalValue) : originalValue;
        }
    });
    
    // Update month elements
    window.monthTranslator?.updateMonthElements();
};

/* =============================================================================
   Export Functions (Optimized)
   ============================================================================= */

window.exportWithOptions = function(exportType, additionalData = {}) {
    const btn = event.target;
    const originalHtml = btn.innerHTML;
    
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Exporting...';
    btn.disabled = true;
    
    const formData = new FormData();
    Object.keys(additionalData).forEach(key => {
        formData.append(key, additionalData[key]);
    });
    
    fetch(`/export/${exportType}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
        },
        body: formData
    })
    .then(response => {
        if (response.ok) {
            const contentDisposition = response.headers.get('Content-Disposition');
            const filename = contentDisposition ? 
                contentDisposition.split('filename=')[1].replace(/"/g, '') : 
                `export_${Date.now()}.xlsx`;
            
            return response.blob().then(blob => {
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
        alertTranslated('export_failed', { error: error.message });
    })
    .finally(() => {
        btn.innerHTML = originalHtml;
        btn.disabled = false;
    });
};

/* =============================================================================
   Export Functions (BACKWARD COMPATIBILITY)
   ============================================================================= */

window.showExportModal = function(exportType, additionalData = {}) {
    // Avoid conflicts with trip/po specific modals
    if (exportType === 'single_trip' || exportType === 'single_po') {
        return;
    }
    
    const modalHtml = `
    <div class="modal fade" id="exportModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">
                        <i class="bi bi-download me-2"></i>
                        <span data-translate="export_options">Export Options</span>
                    </h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="d-grid gap-2">
                        <button class="btn btn-outline-primary" onclick="exportWithFormat('${exportType}', 'excel', ${JSON.stringify(additionalData)})">
                            <i class="bi bi-file-earmark-spreadsheet me-2"></i>
                            <span data-translate="export_to_excel">Export to Excel (.xlsx)</span>
                        </button>
                        <button class="btn btn-outline-danger" onclick="exportWithFormat('${exportType}', 'pdf', ${JSON.stringify(additionalData)})">
                            <i class="bi bi-file-earmark-pdf me-2"></i>
                            <span data-translate="export_to_pdf">Export to PDF</span>
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

window.exportWithFormat = function(exportType, format, additionalData = {}) {
    const btn = event.target;
    const originalHtml = btn.innerHTML;
    
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Exporting...';
    btn.disabled = true;
    
    const formData = new FormData();
    formData.append('format', format);
    Object.keys(additionalData).forEach(key => {
        formData.append(key, additionalData[key]);
    });
    
    fetch(`/export/${exportType}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
        },
        body: formData
    })
    .then(response => {
        if (response.ok) {
            const contentDisposition = response.headers.get('Content-Disposition');
            const filename = contentDisposition ? 
                contentDisposition.split('filename=')[1].replace(/"/g, '') : 
                `export_${Date.now()}.${format === 'excel' ? 'xlsx' : 'pdf'}`;
            
            return response.blob().then(blob => {
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
                
                // Close modal
                const modal = bootstrap.Modal.getInstance(document.getElementById('exportModal'));
                if (modal) modal.hide();
            });
        } else {
            return response.json().then(data => {
                throw new Error(data.error || 'Export failed');
            });
        }
    })
    .catch(error => {
        alertTranslated('export_failed', { error: error.message });
    })
    .finally(() => {
        btn.innerHTML = originalHtml;
        btn.disabled = false;
    });
};

/* =============================================================================
   Coming Soon Functions (BACKWARD COMPATIBILITY)
   ============================================================================= */

window.showComingSoon = function(feature) {
    // Map features to translation keys
    const featureMap = {
        'vessel_management': 'coming_soon_vessel_management',
        'product_management': 'coming_soon_product_management', 
        'trip_management': 'coming_soon_trip_management',
        'po_management': 'coming_soon_po_management'
    };
    
    const translationKey = featureMap[feature];
    const message = translationKey ? window.translator._(translationKey) : `${feature} feature coming soon!`;
    alertTranslated('feature_coming_soon', { feature: message });
};

/* =============================================================================
   Modal Cleanup Utility
   ============================================================================= */

window.cleanupModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        const bsModal = bootstrap.Modal.getInstance(modal);
        if (bsModal) {
            bsModal.hide();
        }
        setTimeout(() => {
            if (modal.parentNode) {
                modal.parentNode.removeChild(modal);
            }
        }, 300);
    }
};

/* =============================================================================
   Initialization (PRODUCTION OPTIMIZED)
   ============================================================================= */

document.addEventListener('DOMContentLoaded', function() {
    const savedLang = localStorage.getItem('preferred_language') || 'en';
    const langButton = document.getElementById('currentLangText');
    
    // Set language button
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
    
    // Load external translations
    if (window.VesselSalesTranslations) {
        window.translator.setTranslations(window.VesselSalesTranslations);
    }
    
    // Set current language and apply translations
    window.translator.currentLanguage = savedLang;
    
    // Single translation update on load
    setTimeout(() => {
        updatePageTranslations();
    }, 0);
});