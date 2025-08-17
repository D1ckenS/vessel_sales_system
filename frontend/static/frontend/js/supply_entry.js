// Supply Entry JavaScript - EXACT COPY from template (NO MODIFICATIONS)

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
    document.getElementById('poForm').reset();
    
    // Reset vessel dropdown
    document.getElementById('vesselInput').value = '';
    document.getElementById('selectedVesselText').innerHTML = '<span data-translate="choose_vessel">Choose vessel...</span>';
    document.querySelectorAll('#vesselDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
}

function resumePO(poId) {
    window.location.href = `/supply/po/${poId}/`;
}

function viewPODetails(poId) {
    window.location.href = `/supply/po/${poId}/`;
}

// Enhanced translation for supply entry
document.addEventListener('DOMContentLoaded', function() {

    window.initializePage({
        titleKey: 'receive_stock',
        fallbackTitle: 'Receive Stock'
    });
    // Update on language change
    window.addEventListener('languageChanged', function() {
        updateSupplyPageTranslations();
        updateTooltips();
    });
    
    function updateSupplyPageTranslations() {
        // Update PO numbers with Arabic-Indic numerals
        document.querySelectorAll('td:first-child strong').forEach(element => {
            const originalText = element.textContent;
            if (window.translator.currentLanguage === 'ar') {
                const translatedText = window.translateNumber(originalText);
                element.textContent = translatedText;
            }
        });
        
        // Update dates with Arabic-Indic numerals
        document.querySelectorAll('.po-date').forEach(element => {
            const originalDate = element.getAttribute('data-date');
            if (originalDate && window.translator.currentLanguage === 'ar') {
                const translatedDate = window.translateNumber(originalDate);
                element.textContent = translatedDate;
            } else if (originalDate) {
                element.textContent = originalDate;
            }
        });
        
        // Update PO costs and item counts
        document.querySelectorAll('.po-cost, .po-items').forEach(element => {
            const originalValue = element.getAttribute('data-original') || element.textContent.trim();
            if (!element.getAttribute('data-original')) {
                element.setAttribute('data-original', originalValue);
            }
            const translatedNumber = window.translateNumber(originalValue);
            element.textContent = translatedNumber;
        });
    }
    
    function updateTooltips() {
        // Update clickable row tooltips
        document.querySelectorAll('tr[data-po-id]').forEach(row => {
            const isCompleted = row.getAttribute('data-completed') === 'True';
            if (!isCompleted) {
                const tooltip = window.translator._('click_to_resume_po');
                row.setAttribute('title', tooltip);
            }
        });
    }
    
    // Initial call
    setTimeout(() => {
        updateSupplyPageTranslations();
        updateTooltips();
    }, 0);
});

// Form validation with translated messages
document.getElementById('poForm').addEventListener('submit', function(e) {
    const poNumber = document.querySelector('[name="po_number"]').value.trim();
    
    if (!poNumber) {
        e.preventDefault();
        const message = window.translator._('enter_po_number');
        alert(message);
        return;
    }
});

// Add cursor pointer style for clickable rows
const style = document.createElement('style');
style.textContent = `
    .cursor-pointer {
        cursor: pointer;
    }
    .cursor-pointer:hover {
        background-color: var(--bs-info) !important;
    }
`;
document.head.appendChild(style);