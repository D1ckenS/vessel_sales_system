// Sales Entry JavaScript - EXACT COPY from template (NO MODIFICATIONS)
// Vessel dropdown selection handler
function selectVessel(vesselId, element, vesselNameEn, vesselNameAr, hasDutyFree) {
    // Update hidden input
    document.getElementById('vesselInput').value = vesselId;
    
    // Update button text
    const buttonText = document.getElementById('selectedVesselText');
    buttonText.innerHTML = element.innerHTML;
    
    // Update active state
    document.querySelectorAll('#vesselDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
    element.classList.add('active');
    
    // Close dropdown
    const dropdown = bootstrap.Dropdown.getInstance(document.getElementById('vesselDropdown'));
    if (dropdown) {
        dropdown.hide();
    }
    
    // Prevent default link behavior
    return false;
}

function clearForm() {
    document.getElementById('tripForm').reset();
    
    // Reset vessel dropdown
    document.getElementById('vesselInput').value = '';
    document.getElementById('selectedVesselText').innerHTML = '<span data-translate="choose_vessel">Choose vessel...</span>';
    document.querySelectorAll('#vesselDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
}

function viewTripDetails(tripId) {
    // Redirect to trip sales page to view details
    window.location.href = `/sales/trip/${tripId}/`;
}

// Form validation
document.getElementById('tripForm').addEventListener('submit', function(e) {
    const tripNumber = document.querySelector('[name="trip_number"]').value.trim();
    const passengerCount = parseInt(document.querySelector('[name="passenger_count"]').value);
    
    if (!tripNumber) {
        e.preventDefault();
        alertTranslated('enter_trip_number');
        return;
    }
    
    if (!passengerCount || passengerCount <= 0) {
        e.preventDefault();
        alertTranslated('enter_valid_passenger_count');
        return;
    }
});

// ✅ CLEAN EVENT-DRIVEN TRANSLATION SYSTEM - NO FUNCTION OVERRIDES
document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'sales_entry',
        fallbackTitle: 'Sales Entry'
    })

    console.log('📝 Sales Entry: Initializing event-driven translation system');
    
    // Enhanced translation for sales entry
    function updateSalesPageTranslations() {
        console.log('🔄 Sales Entry: Updating page-specific translations');
        
        // Update trip numbers with proper reversion
        document.querySelectorAll('tbody tr td:first-child strong').forEach(element => {
            let originalValue = element.getAttribute('data-original');
            if (!originalValue) {
                originalValue = element.textContent.trim();
                element.setAttribute('data-original', originalValue);
            }
            
            if (window.translator && window.translator.currentLanguage === 'ar') {
                element.textContent = window.translateNumber ? window.translateNumber(originalValue) : originalValue;
            } else {
                element.textContent = originalValue;
            }
        });
        
        // Update passenger counts
        document.querySelectorAll('tbody tr td .fw-bold').forEach(element => {
            const text = element.textContent.trim();
            if (/^\d+$/.test(text) || /^[٠-٩]+$/.test(text)) {
                let originalValue = element.getAttribute('data-original');
                if (!originalValue) {
                    originalValue = text.replace(/[٠-٩]/g, (char) => {
                        const arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
                        return arabicNumerals.indexOf(char).toString();
                    });
                    element.setAttribute('data-original', originalValue);
                }
                
                if (window.translator && window.translator.currentLanguage === 'ar') {
                    element.textContent = window.translateNumber ? window.translateNumber(originalValue) : originalValue;
                } else {
                    element.textContent = originalValue;
                }
            }
        });
        
        // Update revenue amounts  
        document.querySelectorAll('tbody tr td span.fw-bold').forEach(element => {
            const text = element.textContent.trim();
            if (/^[\d.]+$/.test(text) || /^[٠-٩.]+$/.test(text)) {
                let originalValue = element.getAttribute('data-original');
                if (!originalValue) {
                    originalValue = text.replace(/[٠-٩]/g, (char) => {
                        const arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
                        return arabicNumerals.indexOf(char).toString();
                    });
                    element.setAttribute('data-original', originalValue);
                }
                
                if (window.translator && window.translator.currentLanguage === 'ar') {
                    element.textContent = window.translateNumber ? window.translateNumber(originalValue) : originalValue;
                } else {
                    element.textContent = originalValue;
                }
            }
        });
        
        // Update dates - now uses proper data-trip-date attribute from template
        document.querySelectorAll('span[data-trip-date]').forEach(element => {
            let originalValue = element.getAttribute('data-original');
            if (!originalValue) {
                originalValue = element.textContent.trim();
                element.setAttribute('data-original', originalValue);
            }
            
            if (window.translator && window.translator.currentLanguage === 'ar') {
                element.textContent = window.translateNumber ? window.translateNumber(originalValue) : originalValue;
            } else {
                element.textContent = originalValue;
            }
        });
        
        // Update currency symbols - now uses proper data-currency-symbol attribute from template
        document.querySelectorAll('span[data-currency-symbol]').forEach(element => {
            if (window.translator && window.translator.currentLanguage === 'ar') {
                element.textContent = 'د.أ';
            } else {
                element.textContent = 'JOD';
            }
        });
    }
    
    // Update on language change - LISTEN for events instead of overriding toggleLanguage
    window.addEventListener('languageChanged', function() {
        console.log('📢 Sales Entry: Received languageChanged event');
        updateSalesPageTranslations();
    });
    
    // Initial call to set up translations
    setTimeout(() => {
        updateSalesPageTranslations();
    }, 0);
    
    console.log('✅ Sales Entry: Event-driven translation system initialized');
});