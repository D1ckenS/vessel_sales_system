(function () {
let pendingChanges = new Map();

// Enhanced translations for bulk pricing
document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'bulk_pricing_management',
        fallbackTitle: 'Bulk Pricing Management'
    })
    
    // Update page translations
    updatePageTranslations();
});

function updatePrice(input) {
    const vesselId = input.dataset.vesselId;
    const productId = input.dataset.productId;
    const defaultPrice = parseFloat(input.dataset.defaultPrice);
    const newPrice = parseFloat(input.value);
    const cell = input.parentElement;
    const diffElement = document.getElementById(`diff_${vesselId}_${productId}`);
    
    // Mark as pending change
    const key = `${vesselId}_${productId}`;
    pendingChanges.set(key, {
        vessel_id: vesselId,
        product_id: productId,
        price: newPrice
    });
    
    // Update cell appearance
    if (newPrice && newPrice !== defaultPrice) {
        cell.className = 'pricing-cell has-custom-price';
        
        // Update or create difference badge
        const difference = ((newPrice - defaultPrice) / defaultPrice * 100);
        const diffText = (difference > 0 ? '+' : '') + difference.toFixed(0) + '%';
        
        if (diffElement) {
            diffElement.textContent = diffText;
            diffElement.className = `price-difference diff-${difference > 0 ? 'positive' : 'negative'}`;
        } else {
            const newDiffElement = document.createElement('span');
            newDiffElement.id = `diff_${vesselId}_${productId}`;
            newDiffElement.className = `price-difference diff-${difference > 0 ? 'positive' : 'negative'}`;
            newDiffElement.textContent = diffText;
            cell.appendChild(newDiffElement);
        }
    } else {
        cell.className = 'pricing-cell has-default-price';
        if (diffElement) {
            diffElement.remove();
        }
    }
    
    // Visual indicator for unsaved changes
    input.style.border = '2px solid #ffc107';
}
// Removed invalid getCookie() call

// REFACTORED with standardized validation and fetch patterns
async function saveAllChanges() {
    if (pendingChanges.size === 0) {
        window.alertTranslated('no_changes_to_save');
        return;
    }
    
    const updates = Array.from(pendingChanges.values());

    try {
        // Use standardized fetch with CSRF
        const response = await window.standardizeFetchWithCSRF('/pricing/bulk-update/', { 
            updates: updates 
        });
        
        const data = await response.json();
        
        if (data.success) {
            window.alertTranslated('changes_saved');
            pendingChanges.clear();
            
            // Remove visual indicators
            document.querySelectorAll('.pricing-input').forEach(input => {
                input.style.border = '';
            });
        } else {
            window.alertTranslated('error_saving_changes', { error: data.error });
        }
    } catch (error) {
        window.alertTranslated('error_saving_changes', { error: error.message });
    }
}

// Source vessel dropdown selection handler - REFACTORED with DropdownManager
function selectSourceVessel(vesselId, element) {
    return window.DropdownManager.handleSelection({
        dropdownId: 'sourceVesselDropdown',
        inputId: 'sourceVesselInput',
        buttonTextId: 'selectedSourceVesselText',
        selectedValue: vesselId,
        selectedElement: element,
        closeDropdown: true
    });
}

// Target vessels multi-select dropdown handler - REFACTORED with DropdownManager
let selectedTargetVessels = new Set();

function toggleTargetVessel(vesselId, element, vesselName) {
    window.DropdownManager.handleMultiSelection({
        itemId: vesselId,
        selectedSet: selectedTargetVessels,
        inputId: 'targetVesselsInput',
        buttonTextId: 'selectedTargetVesselsText',
        itemName: vesselName,
        checkboxId: `target-${vesselId}`
    });
    
    // Update the element active state (DropdownManager doesn't handle this for multi-select)
    element.classList.toggle('active', selectedTargetVessels.has(vesselId));
    
    // Don't close dropdown for multi-select
    event.preventDefault();
    event.stopPropagation();
    return false;
}

// REFACTORED with standardized validation and fetch patterns
async function copyPricing() {
    const sourceVessel = document.getElementById('sourceVesselInput').value;
    const targetVessels = document.getElementById('targetVesselsInput').value.split(',').filter(id => id);
    const overwrite = document.getElementById('overwriteExisting').checked;
    
    // Validation using standardized patterns
    if (!sourceVessel) {
        window.alertTranslated('select_source_vessel');
        return;
    }
    
    if (targetVessels.length === 0) {
        window.alertTranslated('select_target_vessels');
        return;
    }

    try {
        // Use standardized fetch with CSRF
        const response = await window.standardizeFetchWithCSRF('/pricing/copy-template/', {
            source_vessel_id: sourceVessel,
            target_vessel_ids: targetVessels,
            overwrite: overwrite
        });

        const data = await response.json();
        
        if (data.success) {
            window.alertTranslated('pricing_copied');
            // Reload page to show updated pricing
            setTimeout(() => {
                window.location.reload();
            }, 1500);
        } else {
            window.alertTranslated('error_copying_pricing', { error: data.error });
        }
    } catch (error) {
        window.alertTranslated('error_copying_pricing', { error: error.message });
    }
};

window.updatePrice = updatePrice;
window.saveAllChanges = saveAllChanges;
window.copyPricing = copyPricing;
window.selectSourceVessel = selectSourceVessel;
window.toggleTargetVessel = toggleTargetVessel;
})();