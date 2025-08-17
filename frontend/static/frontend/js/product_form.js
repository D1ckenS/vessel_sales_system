// Product Form JavaScript - EXACT COPY from template (NO MODIFICATIONS)

document.addEventListener('DOMContentLoaded', () => {
    // --- Field Validity & Save Button Control ---
    const saveBtn = document.getElementById('saveProductBtn');
    const saveWithStockBtn = document.getElementById('saveWithStockBtn');
    let fieldValidity = { item_id: true, name: true };

    ['item_id', 'name'].forEach(fieldId => {
        const input = document.getElementById(fieldId);
        if (!input) return;

        const checkExists = async () => {
            const currentValue = input.value.trim();
            if (!currentValue) return;

            const param = `${fieldId}=${encodeURIComponent(currentValue)}`;
            const response = await fetch(`/products/check-exists/?${param}`);
            const data = await response.json();

            if (data.exists) {
                showAlert(`${fieldId.toUpperCase()} already exists`, 'warning');
                input.classList.add('is-invalid');
                fieldValidity[fieldId] = false;
            } else {
                input.classList.remove('is-invalid');
                fieldValidity[fieldId] = true;
            }

            const isFormValid = fieldValidity.item_id && fieldValidity.name;
            if (saveBtn) saveBtn.disabled = !isFormValid;
            if (saveWithStockBtn) saveWithStockBtn.disabled = !isFormValid;
        };

        input.addEventListener('blur', checkExists);
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                checkExists();
            }
        });
    });

    function updateVesselAvailability() {
        const dutyFreeSwitch = document.getElementById('dutyFreeSwitch');
        const isDutyFree = dutyFreeSwitch.checked;

        document.querySelectorAll('.vessel-checkbox').forEach(checkbox => {
            const row = checkbox.closest('tr');
            const vesselId = checkbox.dataset.vesselId;
            const vesselHasDutyFree = row.querySelector('.badge') !== null;

            if (isDutyFree && !vesselHasDutyFree) {
                checkbox.disabled = true;
                checkbox.checked = false;
                row.style.opacity = '0.5';
                clearVesselInputs(vesselId);
            } else {
                checkbox.disabled = false;
                row.style.opacity = '1';
            }
        });

        const dutyFreeWarning = document.getElementById('dutyFreeWarning');
        dutyFreeWarning.style.display = isDutyFree ? 'block' : 'none';

    }

    function clearVesselInputs(vesselId) {
        const quantityInput = document.querySelector(`input[name="vessel_${vesselId}_quantity"]`);
        const costInput = document.querySelector(`input[name="vessel_${vesselId}_cost"]`);

        quantityInput.value = '';
        quantityInput.readOnly = true;
        quantityInput.style.backgroundColor = '#f8f9fa';

        costInput.value = '';
        costInput.readOnly = true;
        costInput.style.backgroundColor = '#f8f9fa';

        updateVesselTotal(vesselId);
    }

    function clearAllVessels() {
        document.querySelectorAll('.vessel-checkbox').forEach(checkbox => {
            checkbox.checked = false;
            checkbox.disabled = false;
            const vesselId = checkbox.dataset.vesselId;
            clearVesselInputs(vesselId);
            checkbox.closest('tr').style.opacity = '1';
        });

        const dutyFreeWarning = document.getElementById('dutyFreeWarning');
        dutyFreeWarning.style.display = 'none';

        updateGrandTotal();
    }

    function updateVesselTotal(vesselId) {
        const quantityInput = document.querySelector(`input[name="vessel_${vesselId}_quantity"]`);
        const costInput = document.querySelector(`input[name="vessel_${vesselId}_cost"]`);
        const totalElement = document.querySelector(`.total-value[data-vessel-id="${vesselId}"]`);

        const quantity = parseFloat(quantityInput.value) || 0;
        const cost = parseFloat(costInput.value) || 0;
        const total = quantity * cost;

        totalElement.textContent = total.toFixed(3);
        updateGrandTotal();
    }

    function updateGrandTotal() {
        let grandTotal = 0;
        document.querySelectorAll('.total-value').forEach(element => {
            const value = parseFloat(element.textContent) || 0;
            grandTotal += value;
        });

        document.getElementById('grandTotal').textContent = grandTotal.toFixed(3);
    }
});

document.addEventListener('DOMContentLoaded', function() {
    // Enhanced vessel pricing toggle
    const enableVesselPricing = document.getElementById('enableVesselPricing');
    const vesselPricingContent = document.getElementById('vesselPricingContent');
    
    if (enableVesselPricing) {
        enableVesselPricing.addEventListener('change', function() {
            if (this.checked) {
                vesselPricingContent.style.display = 'block';
                vesselPricingContent.style.animation = 'fadeIn 0.3s ease';
            } else {
                vesselPricingContent.style.display = 'none';
            }
        });
    }
    
    // Enhanced duty-free toggle
    const dutyFreeSwitch = document.getElementById('dutyFreeSwitch');
    const vesselPricingCard = document.getElementById('vesselPricingCard');
    
    if (dutyFreeSwitch) {
        dutyFreeSwitch.addEventListener('change', function() {
            if (this.checked) {
                vesselPricingCard.style.display = 'none';
            } else {
                vesselPricingCard.style.display = 'block';
            }
        });
    }
    
    // Enhanced form validation with better UX
    const form = document.getElementById('productForm');
    const inputs = form.querySelectorAll('input[required], select[required]');
    
    inputs.forEach(input => {
        input.addEventListener('blur', function() {
            if (this.value.trim() === '') {
                this.classList.add('is-invalid');
            } else {
                this.classList.remove('is-invalid');
                this.classList.add('is-valid');
            }
        });
        
        input.addEventListener('input', function() {
            if (this.classList.contains('is-invalid') && this.value.trim() !== '') {
                this.classList.remove('is-invalid');
                this.classList.add('is-valid');
            }
        });
    });
    
    // Enhanced AJAX validation for item_id and name
    const nameInput = document.querySelector('input[name="name"]');
    const itemIdInput = document.querySelector('input[name="item_id"]');
    const ajaxAlert = document.getElementById('ajaxAlert');
    
    function checkUniqueness(field, value) {
        if (value.trim() === '') return;
        
        fetch(`/products/check-exists/?${field}=${encodeURIComponent(value)}`)
            .then(response => response.json())
            .then(data => {
                if (data.exists) {
                    showAlert(`${field === 'item_id' ? 'Item ID' : 'Product name'} already exists!`, 'danger');
                    if (field === 'item_id') {
                        itemIdInput.classList.add('is-invalid');
                    } else {
                        nameInput.classList.add('is-invalid');
                    }
                }
            })
            .catch(error => console.error('Error:', error));
    }
    
    // Debounced uniqueness checking
    let timeout;
    [nameInput, itemIdInput].forEach(input => {
        if (input) {
            input.addEventListener('input', function() {
                clearTimeout(timeout);
                timeout = setTimeout(() => {
                    const field = this.name;
                    const value = this.value;
                    checkUniqueness(field, value);
                }, 500);
            });
        }
    });
    
    // Enhanced placeholder translation
    function updatePlaceholders() {
        const currentLang = window.translator ? window.translator.currentLanguage : 'en';
        
        document.querySelectorAll('[data-placeholder-en], [data-placeholder-ar]').forEach(element => {
            const placeholder = element.getAttribute(`data-placeholder-${currentLang}`);
            if (placeholder) {
                element.placeholder = placeholder;
            }
        });
    }
    
    // Update placeholders on language change
    if (window.translator) {
        window.addEventListener('languageChanged', updatePlaceholders);
        updatePlaceholders(); // Initial call
    }
    
    // Enhanced form submission with loading state
    form.addEventListener('submit', function(e) {
        const submitButtons = form.querySelectorAll('button[type="submit"]');
        
        submitButtons.forEach(btn => {
            const originalText = btn.innerHTML;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Saving...';
            btn.disabled = true;
            
            // Re-enable after 5 seconds as failsafe
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }, 5000);
        });
    });
});

// CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .is-invalid {
        border-color: #dc3545 !important;
        box-shadow: 0 0 0 0.2rem rgba(220, 53, 69, 0.25) !important;
    }
    
    .is-valid {
        border-color: #198754 !important;
        box-shadow: 0 0 0 0.2rem rgba(25, 135, 84, 0.25) !important;
    }
`;

function showAlert(message, type = 'warning') {
    window.showAlert(message, type);
}

document.head.appendChild(style);