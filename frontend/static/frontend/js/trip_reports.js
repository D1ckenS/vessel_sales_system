// Trip Reports JavaScript - EXACT COPY from template (NO MODIFICATIONS)

// Enhanced translation for trip reports
document.addEventListener('DOMContentLoaded', function() {

    window.initializePage({
        titleKey: 'trip_reports',
        fallbackTitle: 'Trip Reports'
    });
    // Update on language change
    window.addEventListener('languageChanged', function() {
        updateTripPageTranslations();
        calculateRevenuePerPassenger();
    });
    
    function updateTripPageTranslations() {
        // Update trip numbers (first column, strong elements)
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
    
    function calculateRevenuePerPassenger() {
        document.querySelectorAll('.revenue-per-passenger').forEach(element => {
            const revenue = parseFloat(element.getAttribute('data-revenue')) || 0;
            const passengers = parseInt(element.getAttribute('data-passengers')) || 0;
            
            if (passengers > 0) {
                const revenuePerPassenger = (revenue / passengers).toFixed(3);
                element.setAttribute('data-original', revenuePerPassenger);
                
                if (window.translator && window.translator.currentLanguage === 'ar') {
                    element.textContent = window.translateNumber(revenuePerPassenger);
                } else {
                    element.textContent = revenuePerPassenger;
                }
            } else {
                element.textContent = '--';
            }
        });
    }
    
    // Make function available globally
    window.calculateRevenuePerPassenger = calculateRevenuePerPassenger;
    
    // Use universal dropdown z-index function from base_scripts.js
    window.setupUniversalDropdownZIndex([
        'vesselTripDropdown',
        'statusTripDropdown'
    ]);
    
    // Initial call
    setTimeout(() => {
        updateTripPageTranslations();
        calculateRevenuePerPassenger();
    }, 0);

});

// Vessel dropdown selection handler
function selectVesselTrip(vesselId, element) {
    // Update hidden input
    document.getElementById('vesselTripInput').value = vesselId;
    
    // Update button text
    const buttonText = document.getElementById('selectedVesselTripText');
    buttonText.innerHTML = element.innerHTML;
    
    // Update active state
    document.querySelectorAll('#vesselTripDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
    element.classList.add('active');
    
    // Close dropdown
    const dropdown = bootstrap.Dropdown.getInstance(document.getElementById('vesselTripDropdown'));
    if (dropdown) {
        dropdown.hide();
    }
    
    // Prevent default link behavior
    event.preventDefault();
    return false;
}

// Status dropdown selection handler
function selectStatusTrip(statusValue, element) {
    // Update hidden input
    document.getElementById('statusTripInput').value = statusValue;
    
    // Update button text
    const buttonText = document.getElementById('selectedStatusTripText');
    buttonText.innerHTML = element.innerHTML;
    
    // Update active state
    document.querySelectorAll('#statusTripDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
    element.classList.add('active');
    
    // Close dropdown
    const dropdown = bootstrap.Dropdown.getInstance(document.getElementById('statusTripDropdown'));
    if (dropdown) {
        dropdown.hide();
    }
    
    // Prevent default link behavior
    event.preventDefault();
    return false;
}

function exportTripReports() {
    const urlParams = new URLSearchParams(window.location.search);  

    const additionalData = {
        vessel_filter: urlParams.get('vessel') || '',
        start_date: urlParams.get('date_from') || '',
        end_date: urlParams.get('date_to') || '',
        status_filter: urlParams.get('status') || ''
    };
    
    window.showUnifiedExportModal('trips', additionalData);
}

function printTrips() {
    window.templateUtils.showPrintComingSoon();
}

function viewTripAnalytics(tripId) {
    window.templateUtils.showComingSoonAlert();
}