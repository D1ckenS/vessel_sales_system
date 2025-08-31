(function () {
    // REFACTORED: Using PageManager (already very clean)
    const reportManager = new window.PageManager({
        titleKey: 'daily_report',
        fallbackTitle: 'Daily Report',
        customTranslationHandler: updateDailyReportTranslations
    });
    
    // REFACTORED: Already optimized with SpecializedTranslator
    function updateDailyReportTranslations() {
        window.SpecializedTranslator.updatePageSpecificTranslations({
            updateTransactionTypes: true,
            updateBadgeNumbers: true,
            updatePassengerCounts: true
        });
    }
    
    // Export and Print functions (simplified)
    function exportDailyReport() {
        const selectedDate = PageManager.getValue(PageManager.querySelector('[name="date"]')) 
            || new Date().toISOString().split('T')[0];
        
        showUnifiedExportModal('daily_report', { date: selectedDate });
    }
    
    function printDailyReport() {
        window.templateUtils.showPrintComingSoon();
    }
    
    // Export functions
    window.exportDailyReport = exportDailyReport;
    window.printDailyReport = printDailyReport;
    
})();

// REFACTORED SUMMARY:
// Original: 43 lines (already very optimized)
// Refactored: 33 lines with PageManager integration
// Reduction: 23% fewer lines (minor improvement since already optimized)
// Benefits:
//   - Consistent with other refactored files
//   - Better integration with PageManager pattern
//   - Cleaner helper method usage