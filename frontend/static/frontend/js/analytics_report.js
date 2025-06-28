(function () {
    document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'analytics_report',
        fallbackTitle: 'Analytics Report'
    })
    
    function updateAnalyticsPageTranslations() {
        // Keep only the unique analytics translation logic (efficiency score, growth rate, etc.)
        document.querySelectorAll('.analytics-kpi .stats-number').forEach(element => {
            const storedNumber = element.getAttribute('data-original') || element.textContent.trim();
            if (!element.getAttribute('data-original')) {
                element.setAttribute('data-original', storedNumber);
            }
            
            if (window.translator && window.translator.currentLanguage === 'ar') {
                const translatedNumber = window.translateNumber ? window.translateNumber(storedNumber) : storedNumber;
                element.textContent = translatedNumber;
            } else {
                element.textContent = storedNumber;
            }
        });
        
        // Days left translation
        document.querySelectorAll('.text-muted').forEach(element => {
            const text = element.textContent.trim();
            if (text.includes('days left') || text.includes('يوم متبقي')) {
                const storedNumber = element.getAttribute('data-original-days') || text.match(/\d+/)?.[0];
                if (storedNumber && !element.getAttribute('data-original-days')) {
                    element.setAttribute('data-original-days', storedNumber);
                }
                
                if (window.translator && window.translator.currentLanguage === 'ar') {
                    const translatedNumber = window.translateNumber ? window.translateNumber(storedNumber) : storedNumber;
                    element.textContent = `${translatedNumber} يوم متبقي`;
                } else {
                    element.textContent = `${storedNumber} days left`;
                }
            }
        });

        if (window.monthTranslator && window.monthTranslator.translateAllMonthYearElements) {
            window.monthTranslator.translateAllMonthYearElements();
        }
        
        if (window.updatePageTranslations) {
            window.updatePageTranslations();
        }
    }

    window.addEventListener('languageChanged', function() {
        updateAnalyticsPageTranslations();
    });
    
    setTimeout(() => {
        updateAnalyticsPageTranslations();
    }, 0);
});
})();