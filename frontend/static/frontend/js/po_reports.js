// PO Reports JavaScript - EXACT COPY from template (NO MODIFICATIONS)

// Enhanced translation for PO reports
document.addEventListener('DOMContentLoaded', function() {

    window.initializePage({
        titleKey: 'po_reports',
        fallbackTitle: 'PO Reports'
    })
    // Update on language change
    window.addEventListener('languageChanged', function() {
        updatePOPageTranslations();
    });
    
    function updatePOPageTranslations() {
        // Update PO numbers (first column, strong elements)
        document.querySelectorAll('tbody tr td:first-child strong').forEach(element => {
            const text = element.textContent.trim();
            if (/^\d+$/.test(text) || /^[٠-٩]+$/.test(text)) {
                let originalValue = element.getAttribute('data-original');
                if (!originalValue) {
                    // Convert Arabic numerals back to English for storage
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
        
        // Update dates in date column
        document.querySelectorAll('tbody tr td:nth-child(2) div').forEach(element => {
            const text = element.textContent.trim();
            if (/^\d{2}\/\d{2}\/\d{4}$/.test(text) || /^[٠-٩]{2}\/[٠-٩]{2}\/[٠-٩]{4}$/.test(text)) {
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
        
        // Update time stamps (HH:MM format)
        document.querySelectorAll('tbody tr td:nth-child(2) small').forEach(element => {
            const text = element.textContent.trim();
            if (/^\d{2}:\d{2}$/.test(text) || /^[٠-٩]{2}:[٠-٩]{2}$/.test(text)) {
                let originalValue = element.getAttribute('data-original');
                if (!originalValue) {
                    // Convert Arabic time back to English for storage
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
        'vesselPODropdown',
        'statusPODropdown'
    ]);
    
    // Initial call
    setTimeout(() => {
        updatePOPageTranslations();
        window.initializePage();
    }, 0);
 
});

// Vessel dropdown selection handler
function selectVesselPO(vesselId, element) {
    // Update hidden input
    document.getElementById('vesselPOInput').value = vesselId;
    
    // Update button text
    const buttonText = document.getElementById('selectedVesselPOText');
    buttonText.innerHTML = element.innerHTML;
    
    // Update active state
    document.querySelectorAll('#vesselPODropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
    element.classList.add('active');
    
    // Close dropdown
    const dropdown = bootstrap.Dropdown.getInstance(document.getElementById('vesselPODropdown'));
    if (dropdown) {
        dropdown.hide();
    }
    
    // Prevent default link behavior
    event.preventDefault();
    return false;
}

// Status dropdown selection handler
function selectStatusPO(statusValue, element) {
    // Update hidden input
    document.getElementById('statusPOInput').value = statusValue;
    
    // Update button text
    const buttonText = document.getElementById('selectedStatusPOText');
    buttonText.innerHTML = element.innerHTML;
    
    // Update active state
    document.querySelectorAll('#statusPODropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
    element.classList.add('active');
    
    // Close dropdown
    const dropdown = bootstrap.Dropdown.getInstance(document.getElementById('statusPODropdown'));
    if (dropdown) {
        dropdown.hide();
    }
    
    // Prevent default link behavior
    event.preventDefault();
    return false;
}

function printPOs() {
    window.templateUtils.showPrintComingSoon()
}

function viewPOAnalytics(poId) {
    window.templateUtils.showComingSoonAlert()
}