// Transactions List JavaScript - EXACT COPY from template (NO MODIFICATIONS)
// Note: This file contains Django template variables that are processed during template rendering

// Enhanced translation for transactions list
document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'transactions_list',
        fallbackTitle: 'Transactions List'
    })
    
    // Setup Bootstrap dropdown z-index management
    setupDropdownZIndex();
    
    // Initialize product search functionality
    initializeProductSearch();
    
    // Update on language change
    window.addEventListener('languageChanged', function() {
        updateTransactionsPageTranslations();
    });
    
    function setupDropdownZIndex() {
        // Use universal dropdown z-index function from base_scripts.js
        const dropdownCounter = window.setupUniversalDropdownZIndex([
            'transactionTypeDropdown',
            'vesselDropdown'
        ]);
        
        // Make counter available globally for product search
        window.dropdownCounter = dropdownCounter;
    }
    
    function initializeProductSearch() {
        const searchInput = document.getElementById('product-search');
        const hiddenSelect = document.getElementById('product-select');
        const container = searchInput?.closest('.search-dropdown-container');
        
        if (!searchInput || !hiddenSelect || !container) return;
        
        // Create dropdown element
        const dropdown = document.createElement('div');
        dropdown.id = 'product-dropdown';
        dropdown.className = 'search-dropdown';
        container.appendChild(dropdown);
        
        // Get all product options  
        const allProducts = Array.from(hiddenSelect.options).slice(1); // Skip "All Products"
        let filteredProducts = [...allProducts];
        let selectedIndex = -1;
        
        // Set initial value if there's a selected product
        const selectedOption = hiddenSelect.options[hiddenSelect.selectedIndex];
        if (selectedOption && selectedOption.value) {
            searchInput.value = selectedOption.textContent.trim();
        }
        
        function showDropdown() {
            dropdown.classList.add('show');
            container.classList.add('dropdown-active');
            
            // BOSS FIX: Use global counter system
            if (window.dropdownCounter) {
                window.dropdownCounter.add();
            }
        }
        
        function hideDropdown() {
            dropdown.classList.remove('show');
            container.classList.remove('dropdown-active');
            selectedIndex = -1;
            
            // BOSS FIX: Use global counter system
            if (window.dropdownCounter) {
                window.dropdownCounter.remove();
            }
        }
        
        // Event listeners
        searchInput.addEventListener('input', function() {
            const term = this.value.toLowerCase().trim();
            
            if (!term) {
                filteredProducts = [...allProducts];
            } else {
                filteredProducts = allProducts.filter(option => {
                    const name = option.dataset.name;
                    const itemId = option.dataset.itemId;
                    return name.includes(term) || itemId.includes(term);
                });
            }
            updateDropdown();
            showDropdown();
        });
        
        searchInput.addEventListener('focus', function() {
            updateDropdown();
            showDropdown();
        });
        
        searchInput.addEventListener('blur', function() {
            setTimeout(hideDropdown, 150);
        });
        
        function updateDropdown() {
            dropdown.innerHTML = '';
            
            if (filteredProducts.length === 0) {
                dropdown.innerHTML = '<div class="search-item text-muted">No products found</div>';
                return;
            }
            
            // Add "All Products" option if no search term
            if (!searchInput.value.trim()) {
                const allItem = document.createElement('a');
                allItem.href = '#';
                allItem.className = 'search-item';
                allItem.textContent = 'All Products';
                allItem.addEventListener('click', (e) => {
                    e.preventDefault();
                    selectProduct('', '');
                });
                dropdown.appendChild(allItem);
            }
            
            filteredProducts.forEach(option => {
                const item = document.createElement('a');
                item.href = '#';
                item.className = 'search-item';
                item.textContent = option.textContent.trim();
                
                item.addEventListener('click', (e) => {
                    e.preventDefault();
                    selectProduct(option.value, option.textContent.trim());
                });
                
                dropdown.appendChild(item);
            });
        }
        
        function selectProduct(value, text) {
            hiddenSelect.value = value;
            searchInput.value = text;
            hideDropdown();
        }
        
        // Initialize
        updateDropdown();
        hideDropdown();
    }
    
    function updateTransactionsPageTranslations() {
        const searchInput = document.getElementById('product-search');
        const hiddenSelect = document.getElementById('product-select');
        const container = searchInput?.closest('.search-dropdown-container');
        const filterCard = searchInput?.closest('.card');
        
        let dropdown = document.getElementById('product-dropdown');
        
        // Create dropdown if it doesn't exist
        if (!dropdown) {
            dropdown = document.createElement('div');
            dropdown.id = 'product-dropdown';
            dropdown.className = 'search-dropdown';
            container.appendChild(dropdown);
        } else {
            // Ensure it has the correct class
            dropdown.className = 'search-dropdown';
        }
        
        if (!searchInput || !hiddenSelect || !dropdown || !container) return;
        
        // Get all product options
        const allProducts = Array.from(hiddenSelect.options).slice(1); // Skip "All Products" option
        let filteredProducts = [...allProducts];
        let selectedIndex = -1;
        
        // Set initial value if there's a selected product
        const selectedOption = hiddenSelect.querySelector('option[selected]');
        if (selectedOption && selectedOption.value) {
            searchInput.value = selectedOption.textContent.trim();
        }
        
        function showDropdown() {
            dropdown.classList.add('show');
            container.classList.add('dropdown-active');
        }
        
        function hideDropdown() {
            dropdown.classList.remove('show');
            container.classList.remove('dropdown-active');
            selectedIndex = -1;
        }
        
        function filterProducts(searchTerm) {
            const term = searchTerm.toLowerCase().trim();
            if (!term) {
                filteredProducts = [...allProducts];
            } else {
                filteredProducts = allProducts.filter(option => {
                    const name = option.getAttribute('data-name') || '';
                    const itemId = option.getAttribute('data-item-id') || '';
                    return name.includes(term) || itemId.includes(term);
                });
            }
            updateDropdown();
        }
        
        function updateDropdown() {
            dropdown.innerHTML = '';
            
            const searchTerm = searchInput.value.toLowerCase().trim();
            
            // Always add "All Products" option first
            const allOption = document.createElement('div');
            allOption.className = 'search-item';
            allOption.textContent = 'All Products';
            allOption.setAttribute('data-value', '');
            dropdown.appendChild(allOption);
            
            // Add filtered products
            filteredProducts.forEach((option, index) => {
                const item = document.createElement('div');
                item.className = 'search-item';
                item.textContent = option.textContent;
                item.setAttribute('data-value', option.value);
                item.setAttribute('data-index', index);
                
                // Highlight matching text only if there's a search term
                if (searchTerm) {
                    const text = item.textContent;
                    const regex = new RegExp(`(${searchTerm})`, 'gi');
                    item.innerHTML = text.replace(regex, '<mark>$1</mark>');
                }
                
                dropdown.appendChild(item);
            });
            
            // Show "No results" if no products found and user has searched
            if (filteredProducts.length === 0 && searchTerm) {
                const noResults = document.createElement('div');
                noResults.className = 'search-item text-muted';
                noResults.textContent = 'No products found';
                dropdown.appendChild(noResults);
            }
        }
        
        // Event listeners
        searchInput.addEventListener('input', function() {
            filterProducts(this.value);
            showDropdown();
            selectedIndex = -1;
        });
        
        searchInput.addEventListener('focus', function() {
            // Always show dropdown on focus (click on empty field shows all products)
            filterProducts(this.value);
            showDropdown();
        });
        
        searchInput.addEventListener('blur', function() {
            // Delay hiding to allow click on dropdown items
            setTimeout(hideDropdown, 150);
        });
        
        searchInput.addEventListener('keydown', function(e) {
            const items = dropdown.querySelectorAll('.search-item:not(.text-muted)');
            
            switch(e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
                    updateSelection(items);
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    selectedIndex = Math.max(selectedIndex - 1, -1);
                    updateSelection(items);
                    break;
                case 'Enter':
                    e.preventDefault();
                    if (selectedIndex >= 0 && items[selectedIndex]) {
                        selectProduct(items[selectedIndex]);
                    }
                    break;
                case 'Escape':
                    hideDropdown();
                    searchInput.blur();
                    break;
            }
        });
        
        function updateSelection(items) {
            items.forEach((item, index) => {
                item.classList.toggle('active', index === selectedIndex);
            });
        }
        
        function selectProduct(item) {
            const value = item.getAttribute('data-value');
            const text = item.textContent.replace(/\n/g, '').trim();
            
            hiddenSelect.value = value;
            searchInput.value = value ? text : '';
            hideDropdown();
        }
        
        // Handle dropdown clicks
        dropdown.addEventListener('click', function(e) {
            if (e.target.classList.contains('search-item') && !e.target.classList.contains('text-muted')) {
                selectProduct(e.target);
            }
        });
        
        // Hide dropdown when clicking outside
        document.addEventListener('click', function(e) {
            if (!container.contains(e.target)) {
                hideDropdown();
            }
        });
        
        // Initialize dropdown content but don't show it
        updateDropdown();
        
        // Only show initial content if there's no existing search value
        if (!searchInput.value.trim()) {
            hideDropdown(); // Ensure dropdown is hidden initially
        }
    }
    
    function updateTransactionsPageTranslations() {
        // Update transaction dates
        document.querySelectorAll('.transaction-date').forEach(element => {
            const originalDate = element.getAttribute('data-date') || element.textContent.trim();
            if (!element.getAttribute('data-date')) {
                element.setAttribute('data-date', originalDate);
            }
            
            if (window.translator.currentLanguage === 'ar') {
                element.textContent = window.translateNumber(originalDate);
            } else {
                element.textContent = originalDate;
            }
        });
        
        // Update transaction times (HH:MM format)
        document.querySelectorAll('.transaction-time').forEach(element => {
            const originalTime = element.getAttribute('data-time') || element.textContent.trim();
            if (!element.getAttribute('data-time')) {
                element.setAttribute('data-time', originalTime);
            }
            
            if (window.translator.currentLanguage === 'ar') {
                element.textContent = window.translateNumber(originalTime);
            } else {
                element.textContent = originalTime;
            }
        });
        
        // Update transaction types in badges
        document.querySelectorAll('.transaction-type-badge').forEach(element => {
            const originalType = element.getAttribute('data-type') || element.textContent.trim();
            if (!element.getAttribute('data-type')) {
                element.setAttribute('data-type', originalType);
            }
            element.textContent = window.translateTransactionType(originalType);
        });
        
        // Update dropdown transaction types
        document.querySelectorAll('option[data-transaction-type]').forEach(element => {
            const originalType = element.getAttribute('data-transaction-type');
            if (originalType) {
                element.textContent = window.translateTransactionType(originalType);
            }
        });
        
        // Update product IDs (ID: 104, ID: 101, etc.) - FIXED VERSION
        document.querySelectorAll('td small.text-muted').forEach(element => {
            const text = element.textContent.trim();
            if (text.includes('ID:') || text.includes('رقم:')) {
                // Store original value if not already stored
                let originalText = element.getAttribute('data-original');
                if (!originalText) {
                    // If it's already in Arabic, convert back to English first
                    if (text.includes('رقم:')) {
                        const arabicMatch = text.match(/([٠-٩]+)/);
                        if (arabicMatch) {
                            const englishNumber = arabicMatch[0].replace(/[٠-٩]/g, (char) => {
                                const arabicNumerals = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
                                return arabicNumerals.indexOf(char).toString();
                            });
                            originalText = `ID: ${englishNumber}`;
                        }
                    } else {
                        originalText = text;
                    }
                    element.setAttribute('data-original', originalText);
                }
                
                // Extract the number from original text
                const numberMatch = originalText.match(/(\d+)/);
                if (numberMatch) {
                    const originalNumber = numberMatch[0];
                    
                    const currentLang = window.translator.currentLanguage;
                    if (currentLang === 'ar') {
                        const translatedNumber = window.translateNumber(originalNumber);
                        element.textContent = `رقم: ${translatedNumber}`;
                    } else {
                        element.textContent = originalText; // Always revert to original English
                    }
                }
            }
        });
        
        // Update timesince information
        document.querySelectorAll('.transaction-time-ago').forEach(element => {
            const originalTime = element.getAttribute('data-time');
            if (!originalTime) {
                const currentText = element.textContent.trim();
                const cleanTime = currentText.replace(' ago', '').replace(' مضت', '');
                element.setAttribute('data-time', cleanTime);
            }
            
            const timeValue = element.getAttribute('data-time');
            const currentLang = window.translator.currentLanguage;
            
            if (currentLang === 'ar') {
                let arabicTime = timeValue
                    .replace(/(\d+)\s*days?/g, (match, num) => window.translateNumber(num) + ' يوم')
                    .replace(/(\d+)\s*hours?/g, (match, num) => window.translateNumber(num) + ' ساعة') 
                    .replace(/(\d+)\s*minutes?/g, (match, num) => window.translateNumber(num) + ' دقيقة')
                    .replace(/(\d+)\s*weeks?/g, (match, num) => window.translateNumber(num) + ' أسبوع')
                    .replace(/(\d+)\s*months?/g, (match, num) => window.translateNumber(num) + ' شهر')
                    .replace(/(\d+)\s*years?/g, (match, num) => window.translateNumber(num) + ' سنة')
                    .replace(/,\s*/g, '، ')
                    .replace(/\s+/g, ' ')
                    .trim();
                
                if (!arabicTime.includes('مضت')) {
                    arabicTime += ' مضت';
                }
                
                element.textContent = arabicTime;
            } else {
                const timeWithoutAgo = timeValue.replace(' ago', '').replace(' مضت', '');
                element.textContent = timeWithoutAgo + ' ago';
            }
        });
        
        // Update Trip/PO numbers in links
        document.querySelectorAll('td a small').forEach(element => {
            const text = element.textContent.trim();
            // Check if it contains a number (trip or PO number)
            const numberMatch = text.match(/(\d+)/);
            if (numberMatch) {
                let originalNumber = numberMatch[0];
                let originalText = element.getAttribute('data-original');
                if (!originalText) {
                    originalText = text;
                    element.setAttribute('data-original', originalText);
                }
                
                if (window.translator.currentLanguage === 'ar') {
                    const translatedNumber = window.translateNumber(originalNumber);
                    const newText = originalText.replace(/\d+/, translatedNumber);
                    element.textContent = newText;
                } else {
                    element.textContent = originalText;
                }
            }
        });
    }
    
    // Initial call
    setTimeout(() => {
        updateTransactionsPageTranslations();
    }, 0);

});

// Transaction Type dropdown selection handler
function selectTransactionType(typeCode, element) {
    // Update hidden input
    document.getElementById('transactionTypeInput').value = typeCode;
    
    // Update button text
    const buttonText = document.getElementById('selectedTransactionTypeText');
    buttonText.innerHTML = element.innerHTML;
    
    // Update active state
    document.querySelectorAll('#transactionTypeDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
    element.classList.add('active');
    
    // Close dropdown
    const dropdown = bootstrap.Dropdown.getInstance(document.getElementById('transactionTypeDropdown'));
    if (dropdown) {
        dropdown.hide();
    }
    
    // Prevent default link behavior
    event.preventDefault();
    return false;
}

// Vessel dropdown selection handler
function selectVessel(vesselId, element) {
    // Update hidden input
    document.getElementById('vesselInput').value = vesselId;
    
    // Update button text
    const buttonText = document.getElementById('selectedVesselText');
    const selectedText = element.textContent.trim();
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
    event.preventDefault();
    return false;
}

//document.querySelector('[name="date_to"]')?.value || '',
function exportTransactions(btn) {
    const urlParams = new URLSearchParams(window.location.search);
    const productId = btn.closest('td[data-product-id]')?.dataset.productId;
    const additionalData = {
        transaction_type: urlParams.get('transaction_type') || '',
        vessel_id: urlParams.get('vessel') || '',
        product_id: urlParams.get('product') || productId || '',
        start_date: urlParams.get('date_from') || '',
        end_date: urlParams.get('date_to') || ''
    };
    console.log('additionalData', additionalData);
    window.showUnifiedExportModal('transactions', additionalData);
}

function deleteTransaction(transactionId, transactionType, productName, vesselName) {
    // Show confirmation modal
    const modalHTML = `
        <div class="modal fade" id="deleteTransactionModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header bg-danger text-white">
                        <h5 class="modal-title">
                            <i class="bi bi-exclamation-triangle me-2"></i>
                            Delete Transaction
                        </h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" onclick="this.blur()"></button>
                    </div>
                    <div class="modal-body">
                        <div class="alert alert-warning">
                            <i class="bi bi-info-circle me-2"></i>
                            <strong>Are you sure?</strong><br>
                            This will permanently delete this transaction and may affect inventory levels.
                        </div>
                        
                        <h6>Transaction Details:</h6>
                        <ul class="list-unstyled">
                            <li><strong>Type:</strong> <span class="badge bg-secondary">${transactionType}</span></li>
                            <li><strong>Product:</strong> ${productName}</li>
                            <li><strong>Vessel:</strong> ${vesselName}</li>
                        </ul>
                        
                        <div class="alert alert-info">
                            <i class="bi bi-lightbulb me-2"></i>
                            <strong>What happens:</strong><br>
                            ${getTransactionDeletionEffect(transactionType)}
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal" onclick="this.blur()">
                            <i class="bi bi-x-circle me-1"></i> Cancel
                        </button>
                        <button type="button" class="btn btn-danger" onclick="this.blur(); confirmTransactionDelete(${transactionId})">
                            <i class="bi bi-trash me-1"></i> Delete Transaction
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal
    const existingModal = document.getElementById('deleteTransactionModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add and show modal
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    new bootstrap.Modal(document.getElementById('deleteTransactionModal')).show();
}

function getTransactionDeletionEffect(transactionType) {
    switch(transactionType) {
        case 'SALE':
            return 'Inventory will be restored to the vessel (products added back to stock)';
        case 'SUPPLY':
            return 'Inventory will be removed from the vessel (products removed from stock)';
        case 'TRANSFER_OUT':
            return 'Inventory will be restored to source vessel and removed from destination vessel';
        case 'TRANSFER_IN':
            return 'Inventory will be removed from this vessel';
        case 'WASTE':
            return 'Inventory will be restored to the vessel (wasted products added back to stock)';
        default:
            return 'Inventory levels will be adjusted accordingly';
    }
}

function confirmTransactionDelete(transactionId) {
    fetch(`/transactions/${transactionId}/delete/`, {
        method: 'DELETE',
        headers: {
            'X-CSRFToken': window.getCsrfToken()
        }
    })
    .then(response => {
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return response.json();
        } else {
            throw new Error(`Server returned ${response.status}: ${response.statusText}`);
        }
    })
    .then(data => {
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('deleteTransactionModal'));
        if (modal) {
            modal.hide();
        }
        
        if (data.success) {
            window.showAlert(data.message, 'success');
            location.reload();
        } else {
            // Check for enhanced error handling
            if (data.error_type === 'inventory_consumption_blocked' && data.suggested_actions) {
                showInventoryBlockedModal(data);
            } else {
                const errorMsg = data.error || data.error_message || data.message || 'An error occurred';
                window.showAlert(errorMsg, 'danger');
            }
        }
    })
    .catch(error => {
        console.error('Error:', error);
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('deleteTransactionModal'));
        if (modal) {
            modal.hide();
        }
        
        setTimeout(() => {
            if (error.message.includes('400')) {
                window.showAlert('Cannot delete: This transaction has dependencies that prevent deletion.', 'danger');
            } else {
                window.showAlert('Error deleting transaction: ' + error.message, 'danger');
            }
        }, 200);
    });
}

function showInventoryBlockedModal(errorData) {
    // First, properly close any existing modals and clear focus
    const existingConfirmModal = document.getElementById('deleteConfirmationModal');
    if (existingConfirmModal) {
        const modalInstance = bootstrap.Modal.getInstance(existingConfirmModal);
        if (modalInstance) {
            modalInstance.hide();
        }
        existingConfirmModal.remove();
    }
    
    // Remove any existing inventory modal
    const existingModal = document.getElementById('inventoryBlockedModal');
    if (existingModal) {
        const modalInstance = bootstrap.Modal.getInstance(existingModal);
        if (modalInstance) {
            modalInstance.hide();
        }
        existingModal.remove();
    }
    
    // Clear any focused elements
    if (document.activeElement && document.activeElement.blur) {
        document.activeElement.blur();
    }

    // Process the detailed message to convert \n to <br>
    let detailedMessage = errorData.detailed_message || errorData.error_message || errorData.error || '';
    
    // Clean up the message format
    if (detailedMessage.startsWith('[') && detailedMessage.endsWith(']')) {
        detailedMessage = detailedMessage.slice(2, -2); // Remove [' and ']
    }
    
    // Convert \n to HTML line breaks and format sections
    detailedMessage = detailedMessage
        .replace(/\\n\\n/g, '<br><br>')  // Double newlines
        .replace(/\\n/g, '<br>')         // Single newlines
        .replace(/❌ REASON:/g, '<strong>❌ REASON:</strong>')
        .replace(/📊 DETAILS:/g, '<strong>📊 DETAILS:</strong>')
        .replace(/📅 ORIGINAL TRANSACTION:/g, '<strong>📅 ORIGINAL TRANSACTION:</strong>')
        .replace(/🔧 TO FIX THIS ISSUE:/g, '<strong>🔧 TO FIX THIS ISSUE:</strong>')
        .replace(/💡 QUICK ACTIONS:/g, '<strong>💡 QUICK ACTIONS:</strong>');

    const modalHTML = `
        <div class="modal fade" id="inventoryBlockedModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header bg-warning text-dark">
                        <h5 class="modal-title">
                            <i class="bi bi-exclamation-triangle me-2"></i>
                            Inventory Usage Detected
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" onclick="this.blur()"></button>
                    </div>
                    <div class="modal-body">
                        <div class="alert alert-warning">
                            <i class="bi bi-info-circle me-2"></i>
                            <strong>Why can't I delete this?</strong><br>
                            This supply transaction has inventory that was already sold or transferred. 
                            Deleting it would create data inconsistencies.
                        </div>
                        
                        <div class="accordion" id="errorDetailsAccordion">
                            <div class="accordion-item">
                                <h2 class="accordion-header">
                                    <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#errorDetails">
                                        <i class="bi bi-info-circle me-2"></i>
                                        Technical Details
                                    </button>
                                </h2>
                                <div id="errorDetails" class="accordion-collapse collapse" data-bs-parent="#errorDetailsAccordion">
                                    <div class="accordion-body">
                                        <div class="bg-light p-3 rounded">
                                            <small class="font-monospace">${detailedMessage}</small>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            <i class="bi bi-x-circle me-1"></i>
                            Close
                        </button>
                        <a href="/transactions/" class="btn btn-primary">
                            <i class="bi bi-list-ul me-1"></i>
                            View All Transactions
                        </a>
                        <a href="/inventory/" class="btn btn-outline-info">
                            <i class="bi bi-boxes me-1"></i>
                            Check Inventory
                        </a>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // Show modal with delay to ensure DOM is ready
    setTimeout(() => {
        const modal = new bootstrap.Modal(document.getElementById('inventoryBlockedModal'));
        modal.show();
    }, 100);
}
