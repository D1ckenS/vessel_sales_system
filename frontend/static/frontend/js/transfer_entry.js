// Transfer Entry JavaScript - EXACT COPY from template (NO MODIFICATIONS)

// Add page-specific translations
document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'transfer_entry',
        fallbackTitle: 'Transfer Entry',
    })    
    
    // Enhanced translation for transfer entry
    function updateTransferPageTranslations() {
        console.log('🔄 Transfer Entry: Updating page-specific translations');
        
        // Update transfer dates
        document.querySelectorAll('tbody tr td span[data-transfer-date]').forEach(element => {
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
        
        // Update transaction counts (# of Items column)
        document.querySelectorAll('tbody tr td .fw-bold.text-warning').forEach(element => {
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
        
        // Update time-since elements - simplified to use standard translation
        document.querySelectorAll('small.transaction-time').forEach(element => {
            const timeText = element.getAttribute('data-time');
            if (timeText && window.translator && window.translator.currentLanguage === 'ar') {
                // Just translate numbers in time expressions, let standard translation handle "ago"
                let translatedTime = timeText.replace(/\d+/g, (match) => {
                    return window.translateNumber ? window.translateNumber(match) : match;
                });
                element.innerHTML = `${translatedTime} <span data-translate="ago">ago</span>`;
            }
        });
    }
    
    // Update on language change
    window.addEventListener('languageChanged', function() {
        console.log('📢 Transfer Entry: Received languageChanged event');
        updateTransferPageTranslations();
    });
    
    // Apply initial translations
    updatePageTranslations();
    
    // Initial call for transfer-specific translations
    setTimeout(() => {
        updateTransferPageTranslations();
    }, 0);
});

// From Vessel dropdown selection handler
function selectFromVessel(vesselId, element, vesselNameEn, vesselNameAr, hasDutyFree) {
    // Update hidden input
    document.getElementById('fromVesselInput').value = vesselId;
    
    // Update button text
    const buttonText = document.getElementById('selectedFromVesselText');
    buttonText.innerHTML = element.innerHTML;
    
    // Update active state
    document.querySelectorAll('#fromVesselDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
    element.classList.add('active');
    
    // Close dropdown
    const dropdown = bootstrap.Dropdown.getInstance(document.getElementById('fromVesselDropdown'));
    if (dropdown) {
        dropdown.hide();
    }
    
    // Populate destination vessel dropdown (exclude source vessel)
    populateToVesselDropdown(vesselId);
    
    // Clear any previous selection for destination
    document.getElementById('toVesselInput').value = '';
    document.getElementById('selectedToVesselText').innerHTML = '<span data-translate="choose_destination_vessel">Choose destination vessel...</span>';
    
    // Prevent default link behavior
    return false;
}

// To Vessel dropdown selection handler
function selectToVessel(vesselId, element, vesselNameEn, vesselNameAr, hasDutyFree) {
    // Update hidden input
    document.getElementById('toVesselInput').value = vesselId;
    
    // Update button text
    const buttonText = document.getElementById('selectedToVesselText');
    buttonText.innerHTML = element.innerHTML;
    
    // Update active state
    document.querySelectorAll('#toVesselDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
    element.classList.add('active');
    
    // Close dropdown
    const dropdown = bootstrap.Dropdown.getInstance(document.getElementById('toVesselDropdown'));
    if (dropdown) {
        dropdown.hide();
    }
    
    // Prevent default link behavior
    return false;
}

function populateToVesselDropdown(excludeVesselId) {
    const toVesselMenu = document.getElementById('toVesselDropdownMenu');
    const toVesselButton = document.getElementById('toVesselDropdown');
    
    // Clear existing options
    toVesselMenu.innerHTML = '';
    
    // Get all vessels from the from vessel dropdown
    const fromVesselItems = document.querySelectorAll('#fromVesselDropdown + .dropdown-menu .dropdown-item');
    
    fromVesselItems.forEach(item => {
        const vesselId = item.getAttribute('data-value');
        const vesselName = item.getAttribute('data-name');
        const vesselNameAr = item.getAttribute('data-name-ar');
        const hasDutyFree = item.getAttribute('data-duty-free') === 'True';
        
        // Exclude the selected source vessel
        if (vesselId !== excludeVesselId) {
            const li = document.createElement('li');
            const a = document.createElement('a');
            a.className = 'dropdown-item';
            a.href = '#';
            a.setAttribute('data-value', vesselId);
            a.setAttribute('data-name', vesselName);
            a.setAttribute('data-name-ar', vesselNameAr);
            a.setAttribute('data-duty-free', hasDutyFree);
            a.setAttribute('onclick', `selectToVessel('${vesselId}', this, '${vesselName}', '${vesselNameAr}', ${hasDutyFree})`);
            
            a.innerHTML = `
                <i class="bi bi-ship me-2 text-success"></i>
                <span class="vessel-name" data-en="${vesselName}" data-ar="${vesselNameAr}">${vesselName}</span>
                ${hasDutyFree ? '<span class="badge bg-success ms-2"><span data-translate="duty_free">Duty-Free</span></span>' : ''}
            `;
            
            li.appendChild(a);
            toVesselMenu.appendChild(li);
        }
    });
    
    // Enable the destination dropdown
    toVesselButton.disabled = false;
}

function clearForm() {
    document.getElementById('transferForm').reset();
    
    // Reset from vessel dropdown
    document.getElementById('fromVesselInput').value = '';
    document.getElementById('selectedFromVesselText').innerHTML = '<span data-translate="choose_source_vessel">Choose source vessel...</span>';
    document.querySelectorAll('#fromVesselDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // Reset to vessel dropdown
    document.getElementById('toVesselInput').value = '';
    document.getElementById('selectedToVesselText').innerHTML = '<span data-translate="first_select_source_vessel">First select source vessel...</span>';
    document.getElementById('toVesselDropdown').disabled = true;
    document.getElementById('toVesselDropdownMenu').innerHTML = '';
    document.querySelectorAll('#toVesselDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
}

function viewTransferDetails(transferId) {
    window.location.href = `/transfer/${transferId}/`;
}

function resumeTransfer(transferId) {
    window.location.href = `/transfer/${transferId}/`;
}