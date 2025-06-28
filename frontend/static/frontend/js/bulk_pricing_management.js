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

function copyPricing() {
    const sourceVessel = document.getElementById('sourceVessel').value;
    const targetVessels = Array.from(document.getElementById('targetVessels').selectedOptions).map(opt => opt.value);
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
})();