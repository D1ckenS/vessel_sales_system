( function () {
    document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'daily_report',
        fallbackTitle: 'Daily Report'
    })
    // Update on language change
    window.addEventListener('languageChanged', function() {
        updateDailyReportTranslations();
    });
    
    function updateDailyReportTranslations() {
        // Handle transaction breakdown types specifically
        document.querySelectorAll('.transaction-type[data-type]').forEach(element => {
            const type = element.getAttribute('data-type');
            const currentLang = window.translator.currentLanguage;
            
            // Map transaction breakdown types to translations
            const typeTranslations = {
                'sales': currentLang === 'ar' ? 'المبيعات' : 'Sales',
                'supplies': currentLang === 'ar' ? 'التوريدات' : 'Supplies', 
                'transfers': currentLang === 'ar' ? 'التحويلات' : 'Transfers'
            };
            
            if (typeTranslations[type]) {
                element.textContent = typeTranslations[type];
            }
        });
        
        // Update trip numbers and PO numbers in badges
        document.querySelectorAll('.badge').forEach(element => {
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
        
        // Update passenger counts in trip details
        document.querySelectorAll('small.text-muted').forEach(element => {
            const text = element.textContent;
            if (text.includes('passengers') || text.includes('راكب')) {
                const match = text.match(/(\d+)|([٠-٩]+)/);
                if (match) {
                    let originalNumber = match[0];
                    // Convert Arabic to English if needed
                    if (/[٠-٩]/.test(originalNumber)) {
                        originalNumber = originalNumber.replace(/[٠-٩]/g, (char) => {
                            const arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
                            return arabicNumerals.indexOf(char).toString();
                        });
                    }
                    
                    const currentLang = window.translator.currentLanguage;
                    if (currentLang === 'ar') {
                        const translatedNumber = window.translateNumber(originalNumber);
                        // Update the entire text with proper Arabic structure
                        const vesselName = element.querySelector('.vessel-name')?.textContent || '';
                        element.innerHTML = `<span class="vessel-name" data-en="${element.querySelector('.vessel-name')?.getAttribute('data-en') || ''}" data-ar="${element.querySelector('.vessel-name')?.getAttribute('data-ar') || ''}">${element.querySelector('.vessel-name')?.textContent || ''}</span> - ${translatedNumber} راكب`;
                    } else {
                        // Reconstruct English text
                        const vesselName = element.querySelector('.vessel-name')?.textContent || '';
                        element.innerHTML = `<span class="vessel-name" data-en="${element.querySelector('.vessel-name')?.getAttribute('data-en') || ''}" data-ar="${element.querySelector('.vessel-name')?.getAttribute('data-ar') || ''}">${element.querySelector('.vessel-name')?.textContent || ''}</span> - ${originalNumber} passengers`;
                    }
                }
            }
        });
    }
    
    // Initial call
    setTimeout(() => {
        updateDailyReportTranslations();
        updatePageTranslations(); // Call global translation update
    }, 0);

});

// Export and Print functions
function exportDailyReport() {
    const selectedDate = document.querySelector('[name="date"]')?.value || new Date().toISOString().split('T')[0];
    
    showUnifiedExportModal('daily_report', {
        date: selectedDate
    });
}

function printDailyReport() {
    window.templateUtils.showPrintComingSoon()
}

window.exportDailyReport = exportDailyReport;
window.printDailyReport = printDailyReport;
})();