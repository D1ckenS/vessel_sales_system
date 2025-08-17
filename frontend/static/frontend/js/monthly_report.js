// Monthly Report JavaScript - EXACT COPY from template (NO MODIFICATIONS)

// Enhanced translation for monthly report
document.addEventListener('DOMContentLoaded', function() {

    window.initializePage({
        titleKey: 'monthly_report',
        fallbackTitle: 'Monthly Report'
    });
    // Update on language change
    window.addEventListener('languageChanged', function() {
        updateMonthlyReportTranslations();
    });
    
    function updateMonthlyReportTranslations() {
        // Update month/year in header
        updateHeaderMonthYear();
        
        // Update dropdown options
        updateDropdownTranslations();
        
        // Update dates in daily breakdown table
        updateDailyBreakdownDates();
        
        // Update day names in daily breakdown
        updateDayNames();
        
        // Update product IDs in top products
        updateProductIds();
        
        // Update 12-month trend data
        updateTrendMonths();
        
        // Update years in trend and dropdowns
        updateYearNumbers();
    }
    
    function updateHeaderMonthYear() {
        // ✅ FIXED: Handle header month/year translation
        const headerElement = document.querySelector('.report-header-date');
        if (headerElement) {
            const month = headerElement.getAttribute('data-month');
            const year = headerElement.getAttribute('data-year');
            const currentLang = window.translator.currentLanguage;
            
            // Month translation mapping
            const monthTranslations = {
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
            
            const translatedMonth = monthTranslations[month] ? monthTranslations[month][currentLang] : month;
            const translatedYear = currentLang === 'ar' ? window.translateNumber(year) : year;
            
            headerElement.textContent = `${translatedMonth} ${translatedYear}`;
        }
    }
    
    function updateDropdownTranslations() {
        // Update month dropdown options
        document.querySelectorAll('select[name="month"] option').forEach(option => {
            const value = option.value;
            if (value && value !== "") {
                const currentLang = window.translator.currentLanguage;
                
                // Month translation mapping
                const monthTranslations = {
                    '1': { en: 'January', ar: 'يناير' },
                    '2': { en: 'February', ar: 'فبراير' },
                    '3': { en: 'March', ar: 'مارس' },
                    '4': { en: 'April', ar: 'أبريل' },
                    '5': { en: 'May', ar: 'مايو' },
                    '6': { en: 'June', ar: 'يونيو' },
                    '7': { en: 'July', ar: 'يوليو' },
                    '8': { en: 'August', ar: 'أغسطس' },
                    '9': { en: 'September', ar: 'سبتمبر' },
                    '10': { en: 'October', ar: 'أكتوبر' },
                    '11': { en: 'November', ar: 'نوفمبر' },
                    '12': { en: 'December', ar: 'ديسمبر' }
                };
                
                if (monthTranslations[value]) {
                    option.textContent = monthTranslations[value][currentLang];
                }
            }
        });
        
        // Update year dropdown options
        document.querySelectorAll('select[name="year"] option').forEach(option => {
            const originalYear = option.getAttribute('data-original') || option.textContent;
            if (!option.getAttribute('data-original')) {
                option.setAttribute('data-original', originalYear);
            }
            
            if (window.translator.currentLanguage === 'ar') {
                option.textContent = window.translateNumber(originalYear);
            } else {
                option.textContent = originalYear;
            }
        });
    }
    
    function updateDailyBreakdownDates() {
        // Update dates in daily performance table (d/m format)
        document.querySelectorAll('tbody tr td:first-child').forEach(element => {
            const text = element.textContent.trim();
            if (/^\d{1,2}\/\d{1,2}$/.test(text) || /^[٠-٩]{1,2}\/[٠-٩]{1,2}$/.test(text)) {
                let originalValue = element.getAttribute('data-original');
                if (!originalValue) {
                    // Convert Arabic date back to English for storage
                    originalValue = text.replace(/[٠-٩]/g, (char) => {
                        const arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
                        return arabicNumerals.indexOf(char).toString();
                    });
                    element.setAttribute('data-original', originalValue);
                }
                
                if (window.translator.currentLanguage === 'ar') {
                    element.textContent = window.translateNumber(originalValue);
                } else {
                    element.textContent = originalValue;
                }
            }
        });
    }
    
    function updateDayNames() {
        // Update day names in daily breakdown
        document.querySelectorAll('.day-name').forEach(element => {
            const enName = element.getAttribute('data-en');
            const arName = element.getAttribute('data-ar');
            const currentLang = window.translator.currentLanguage;
            
            // Day name translations
            const dayTranslations = {
                'Monday': { en: 'Monday', ar: 'الاثنين' },
                'Tuesday': { en: 'Tuesday', ar: 'الثلاثاء' },
                'Wednesday': { en: 'Wednesday', ar: 'الأربعاء' },
                'Thursday': { en: 'Thursday', ar: 'الخميس' },
                'Friday': { en: 'Friday', ar: 'الجمعة' },
                'Saturday': { en: 'Saturday', ar: 'السبت' },
                'Sunday': { en: 'Sunday', ar: 'الأحد' }
            };
            
            const dayKey = enName || element.textContent.trim();
            if (dayTranslations[dayKey]) {
                if (currentLang === 'ar') {
                    element.textContent = dayTranslations[dayKey].ar;
                } else {
                    element.textContent = dayTranslations[dayKey].en;
                }
            }
        });
    }
    
    function updateProductIds() {
        // Update product IDs in top products section
        document.querySelectorAll('.col-md-4 .card-body small.text-muted').forEach(element => {
            const text = element.textContent.trim();
            if (/^\d+$/.test(text) || /^[٠-٩]+$/.test(text)) {
                let originalValue = element.getAttribute('data-original');
                if (!originalValue) {
                    // Convert Arabic numbers back to English for storage
                    originalValue = text.replace(/[٠-٩]/g, (char) => {
                        const arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
                        return arabicNumerals.indexOf(char).toString();
                    });
                    element.setAttribute('data-original', originalValue);
                }
                
                if (window.translator.currentLanguage === 'ar') {
                    element.textContent = window.translateNumber(originalValue);
                } else {
                    element.textContent = originalValue;
                }
            }
        });
    }
    
    function updateTrendMonths() {
        // ✅ FIXED: Update month/year in 12-month trend with proper reset
        document.querySelectorAll('.trend-month-year').forEach(element => {
            const month = element.getAttribute('data-month');
            const year = element.getAttribute('data-year');
            const currentLang = window.translator.currentLanguage;
            
            // Month abbreviation translations
            const monthAbbrTranslations = {
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
            
            if (currentLang === 'ar') {
                const arabicMonth = monthAbbrTranslations[month]?.ar || month;
                const arabicYear = window.translateNumber(year);
                element.textContent = `${arabicMonth} ${arabicYear}`;
            } else {
                // ✅ CRITICAL: Always revert to original English format
                element.textContent = `${month} ${year}`;
            }
        });
    }
    
    function updateYearNumbers() {
        // Update any standalone year numbers (4 digits)
        document.querySelectorAll('td, th, span, div').forEach(element => {
            // Skip if element has child elements (to avoid processing containers)
            if (element.children.length > 0) return;
            
            const text = element.textContent.trim();
            if (/^\d{4}$/.test(text) || /^[٠-٩]{4}$/.test(text)) {
                let originalValue = element.getAttribute('data-original');
                if (!originalValue) {
                    // Convert Arabic numbers back to English for storage
                    originalValue = text.replace(/[٠-٩]/g, (char) => {
                        const arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
                        return arabicNumerals.indexOf(char).toString();
                    });
                    element.setAttribute('data-original', originalValue);
                }
                
                if (window.translator.currentLanguage === 'ar') {
                    element.textContent = window.translateNumber(originalValue);
                } else {
                    element.textContent = originalValue;
                }
            }
        });
    }
    
    // Use universal dropdown z-index function from base_scripts.js
    window.setupUniversalDropdownZIndex([
        'monthDropdown',
        'yearDropdown'
    ]);
    
    // Initial call
    setTimeout(() => {
        updateMonthlyReportTranslations();
        updatePageTranslations(); // Call global translation update
    }, 100);
});

// Month dropdown selection handler
function selectMonth(monthValue, element, monthName) {
    // Update hidden input
    document.getElementById('monthInput').value = monthValue;
    
    // Update button text
    const buttonText = document.getElementById('selectedMonthText');
    buttonText.textContent = monthName;
    
    // Update active state
    document.querySelectorAll('#monthDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
    element.classList.add('active');
    
    // Close dropdown
    const dropdown = bootstrap.Dropdown.getInstance(document.getElementById('monthDropdown'));
    if (dropdown) {
        dropdown.hide();
    }
    
    // Prevent default link behavior
    event.preventDefault();
    return false;
}

// Year dropdown selection handler
function selectYear(yearValue, element) {
    // Update hidden input
    document.getElementById('yearInput').value = yearValue;
    
    // Update button text
    const buttonText = document.getElementById('selectedYearText');
    buttonText.textContent = yearValue;
    
    // Update active state
    document.querySelectorAll('#yearDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
    element.classList.add('active');
    
    // Close dropdown
    const dropdown = bootstrap.Dropdown.getInstance(document.getElementById('yearDropdown'));
    if (dropdown) {
        dropdown.hide();
    }
    
    // Prevent default link behavior
    event.preventDefault();
    return false;
}

function exportMonthlyReport() {
    const urlParams = new URLSearchParams(window.location.search);

    const additionalData = {
        month: urlParams.get('month'),
        year: urlParams.get('year'),
    };

    window.showUnifiedExportModal('monthly_report', additionalData);
};