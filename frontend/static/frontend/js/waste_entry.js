// Waste Entry JavaScript - EXACT COPY from template (NO MODIFICATIONS)

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
    document.getElementById('wasteForm').reset();
    
    // Reset vessel dropdown
    document.getElementById('vesselInput').value = '';
    document.getElementById('selectedVesselText').innerHTML = '<span data-translate="choose_vessel">Choose vessel...</span>';
    document.querySelectorAll('#vesselDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
}

// Form validation with correct field names
document.getElementById('wasteForm').addEventListener('submit', function(e) {
    const reportNumber = document.querySelector('[name="report_number"]').value.trim();
    const vessel = document.querySelector('[name="vessel"]').value;
    
    if (!reportNumber) {
        e.preventDefault();
        window.alertTranslated('enter_waste_number') || window.showAlert('Please enter waste report number', 'warning');
        return;
    }
    
    if (!vessel) {
        e.preventDefault();
        window.alertTranslated('select_vessel') || window.showAlert('Please select a vessel', 'warning');
        return;
    }
});

// Enhanced translation for waste entry
document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'waste_entry',
        fallbackTitle: 'Waste Entry'
    })
    
    // Update vessel names with proper translation
    document.querySelectorAll('.vessel-name').forEach(element => {
        const enName = element.getAttribute('data-en');
        const arName = element.getAttribute('data-ar');
        
        if (window.translator && window.translator.currentLanguage === 'ar' && arName) {
            element.textContent = arName;
        } else {
            element.textContent = enName;
        }
    });
});