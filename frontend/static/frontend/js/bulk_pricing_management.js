(function () {
let pendingChanges = new Map();

// Enhanced translations for bulk pricing
document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'bulk_pricing_management',
        fallbackTitle: 'Bulk Pricing Management',
        pageTranslations: bulkPricingTranslations
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
window.getCookie()

function saveAllChanges() {
    if (pendingChanges.size === 0) {
        alertTranslated('no_changes_to_save');
        return;
    }
    
    const updates = Array.from(pendingChanges.values());
    
    fetch('/pricing/bulk-update/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.getCsrfToken(),
        },
        body: JSON.stringify({ updates: updates })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alertTranslated('changes_saved');
            pendingChanges.clear();
            
            // Remove visual indicators
            document.querySelectorAll('.pricing-input').forEach(input => {
                input.style.border = '';
            });
        } else {
            alertTranslated('error_saving_changes', { error: data.error });
        }
    })
    .catch(error => {
        alertTranslated('error_saving_changes', { error: error.message });
    });
}

// Source vessel dropdown selection handler
function selectSourceVessel(vesselId, element) {
    // Update hidden input
    document.getElementById('sourceVesselInput').value = vesselId;
    
    // Update button text
    const buttonText = document.getElementById('selectedSourceVesselText');
    buttonText.innerHTML = element.innerHTML;
    
    // Update active state
    document.querySelectorAll('#sourceVesselDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
    element.classList.add('active');
    
    // Close dropdown
    const dropdown = bootstrap.Dropdown.getInstance(document.getElementById('sourceVesselDropdown'));
    if (dropdown) {
        dropdown.hide();
    }
    
    // Prevent default link behavior
    event.preventDefault();
    return false;
}

// Target vessels multi-select dropdown handler
let selectedTargetVessels = new Set();

function toggleTargetVessel(vesselId, element, vesselName) {
    const checkbox = document.getElementById(`target-${vesselId}`);
    
    // Toggle selection
    if (selectedTargetVessels.has(vesselId)) {
        selectedTargetVessels.delete(vesselId);
        checkbox.checked = false;
        element.classList.remove('active');
    } else {
        selectedTargetVessels.add(vesselId);
        checkbox.checked = true;
        element.classList.add('active');
    }
    
    // Update hidden input with comma-separated values
    document.getElementById('targetVesselsInput').value = Array.from(selectedTargetVessels).join(',');
    
    // Update button text
    const buttonText = document.getElementById('selectedTargetVesselsText');
    if (selectedTargetVessels.size === 0) {
        buttonText.innerHTML = '<span data-translate="select_vessels">Select vessels...</span>';
    } else if (selectedTargetVessels.size === 1) {
        buttonText.innerHTML = `<i class="bi bi-ship me-2"></i>${vesselName}`;
    } else {
        buttonText.innerHTML = `<i class="bi bi-ship me-2"></i>${selectedTargetVessels.size} vessels selected`;
    }
    
    // Don't close dropdown for multi-select
    event.preventDefault();
    event.stopPropagation();
    return false;
}

function copyPricing() {
    const sourceVessel = document.getElementById('sourceVesselInput').value;
    const targetVessels = document.getElementById('targetVesselsInput').value.split(',').filter(id => id);
    const overwrite = document.getElementById('overwriteExisting').checked;
    
    if (!sourceVessel) {
        alertTranslated('select_source_vessel');
        return;
    }
    
    if (targetVessels.length === 0) {
        alertTranslated('select_target_vessels');
        return;
    }
    
    fetch('/pricing/copy-template/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.getCsrfToken(),
        },
        body: JSON.stringify({
            source_vessel_id: sourceVessel,
            target_vessel_ids: targetVessels,
            overwrite: overwrite
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alertTranslated('pricing_copied');
            // Reload page to show updated pricing
            setTimeout(() => {
                window.location.reload();
            }, 1500);
        } else {
            alertTranslated('error_copying_pricing', { error: data.error });
        }
    })
    .catch(error => {
        alertTranslated('error_copying_pricing', { error: error.message });
    });
};

window.updatePrice = updatePrice;
window.saveAllChanges = saveAllChanges;
window.copyPricing = copyPricing;
window.selectSourceVessel = selectSourceVessel;
window.toggleTargetVessel = toggleTargetVessel;
})();