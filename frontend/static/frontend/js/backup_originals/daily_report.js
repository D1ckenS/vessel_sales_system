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
    
    // REFACTORED with SpecializedTranslator - reduced from 50+ lines to 7 lines!
    function updateDailyReportTranslations() {
        window.SpecializedTranslator.updatePageSpecificTranslations({
            updateTransactionTypes: true,
            updateBadgeNumbers: true,
            updatePassengerCounts: true
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