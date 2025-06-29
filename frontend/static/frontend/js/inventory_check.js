( function () {
    window.getCsrfToken();
// Global state
let currentVessel = null;
let currentInventoryData = [];
let filteredData = [];
let searchTimeout = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'inventory_management',
        fallbackTitle: 'Inventory Management',
    })
    
    // Apply translations
    updatePageTranslations();
    
    // Auto-select first vessel
    const firstVesselTab = document.querySelector('.vessel-tab');
    if (firstVesselTab) {
        const vesselId = firstVesselTab.dataset.vesselId;
        const vesselNameEn = firstVesselTab.dataset.vesselNameEn;
        const vesselNameAr = firstVesselTab.dataset.vesselNameAr;
        const hasDutyFree = firstVesselTab.dataset.dutyFree === 'true';
        
        switchVessel(vesselId, vesselNameEn, vesselNameAr, hasDutyFree);
    }

    // Update on language change with inventory-specific handling
    window.addEventListener('languageChanged', function() {
        console.log('📢 Inventory: Received languageChanged event');
        updateInventorySpecificTranslations();
    });

    function updateInventorySpecificTranslations() {
        // Handle product IDs in the table
        document.querySelectorAll('.product-id[data-number]').forEach(element => {
            const originalValue = element.getAttribute('data-original') || element.textContent.trim();
            if (!element.getAttribute('data-original')) {
                element.setAttribute('data-original', originalValue);
            }
            
            if (window.translator && window.translator.currentLanguage === 'ar') {
                element.textContent = window.translateNumber ? window.translateNumber(originalValue) : originalValue;
            } else {
                element.textContent = originalValue;
            }
        });
        
        // Handle product IDs in modal content
        document.querySelectorAll('#modalContent small.text-muted').forEach(element => {
            const text = element.textContent.trim();
            // Only process pure numbers that look like product IDs
            if (/^\d+$/.test(text) || /^[٠-٩]+$/.test(text)) {
                let originalValue = element.getAttribute('data-original');
                if (!originalValue) {
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
});

function switchVessel(vesselId, vesselNameEn, vesselNameAr, hasDutyFree) {    
    // Update active tab
    document.querySelectorAll('.vessel-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelector(`[data-vessel-id="${vesselId}"]`).classList.add('active');
    
    // Reset filters
    clearFilters();
    
    // Update vessel info with current language
    currentVessel = {
        id: vesselId,
        name: vesselNameEn,
        name_ar: vesselNameAr || vesselNameEn,
        has_duty_free: hasDutyFree
    };
    
    // Update UI elements - PRESERVE vessel-name spans!
    updateVesselNameDisplay('selectedVesselName', vesselNameEn, vesselNameAr);
    updateVesselNameDisplay('filterVesselName', vesselNameEn, vesselNameAr);
    updateVesselNameDisplay('tableVesselName', vesselNameEn, vesselNameAr);
    
    // Show/hide duty-free badges
    const dutyBadges = ['dutyFreeBadge', 'tableDutyFreeBadge'];
    dutyBadges.forEach(badgeId => {
        const badge = document.getElementById(badgeId);
        if (hasDutyFree) {
            badge.style.display = 'inline';
        } else {
            badge.style.display = 'none';
        }
    });
    
    // Show vessel banner and hide inventory section
    document.getElementById('vesselBanner').style.display = 'block';
    document.getElementById('inventorySection').style.display = 'none';
    
    // Reset show inventory button
    const showBtn = document.getElementById('showInventoryBtn');
    showBtn.innerHTML = '<i class="bi bi-box-seam me-2"></i><span data-translate="show_inventory">Show Inventory</span>';
    showBtn.disabled = false;
    
    // Apply translations to the updated button
    updatePageTranslations();
}

// Helper function to update vessel name displays
function updateVesselNameDisplay(elementId, enName, arName) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    // Check if it already has a vessel-name span
    let vesselSpan = element.querySelector('.vessel-name');
    
    if (!vesselSpan) {
        // Create vessel-name span if it doesn't exist
        vesselSpan = document.createElement('span');
        vesselSpan.className = 'vessel-name';
        vesselSpan.setAttribute('data-en', enName);
        vesselSpan.setAttribute('data-ar', arName || enName);
        
        // Replace element content with the span
        element.innerHTML = '';
        element.appendChild(vesselSpan);
    } else {
        // Update existing span attributes
        vesselSpan.setAttribute('data-en', enName);
        vesselSpan.setAttribute('data-ar', arName || enName);
    }
    
    // Set content based on current language
    const currentLang = window.translator ? window.translator.currentLanguage : 'en';
    if (currentLang === 'ar' && arName) {
        vesselSpan.textContent = arName;
    } else {
        vesselSpan.textContent = enName;
    }
}

function loadInventoryData() {
    if (!currentVessel) {
        alertTranslated('please_select_vessel');
        return;
    }
    
    // Show loading state
    const showBtn = document.getElementById('showInventoryBtn');
    showBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span><span data-translate="loading">Loading...</span>';
    showBtn.disabled = true;
    updatePageTranslations(); // Apply translations to loading text
    
    // Show inventory section and loading overlay
    document.getElementById('inventorySection').style.display = 'block';
    document.getElementById('loadingOverlay').style.display = 'flex';
    
    // Get current filter values
    const searchTerm = document.getElementById('productSearch').value.trim();
    const stockFilter = document.getElementById('stockFilter').value;
    
    // Make AJAX request
    fetch(window.inventoryDataUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || window.getCsrfToken(),
        },
        body: JSON.stringify({
            vessel_id: currentVessel.id,
            search: searchTerm,
            stock_filter: stockFilter
        })
    })
    .then(response => {
        console.log('Response status:', response.status);
        console.log('Response headers:', response.headers);
        return response.text(); // Get as text first to see raw response
    })
    .then(responseText => {
        console.log('Raw response:', responseText);
        try {
            const data = JSON.parse(responseText);
            console.log('Parsed data:', data);
            if (data.success) {
                currentInventoryData = data.inventory_data;
                filteredData = [...currentInventoryData];
                updateInventoryDisplay(data);
            } else {
                console.error('Server returned error:', data.error);
                alertTranslated('error_loading_inventory', { error: data.error });
            }
        } catch (parseError) {
            console.error('JSON parse error:', parseError);
            console.error('Response was:', responseText);
            alertTranslated('error_loading_inventory_data');
        }
    })
    .catch(error => {
        console.error('Network/Fetch error:', error);
        alertTranslated('error_loading_inventory_data');
    })
    
    .finally(() => {
        // Hide loading overlay
        document.getElementById('loadingOverlay').style.display = 'none';
        
        // Reset button
        showBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-2"></i><span data-translate="refresh_inventory">Refresh Inventory</span>';
        showBtn.disabled = false;
        updatePageTranslations(); // Apply translations to button text
    });
}

function updateInventoryDisplay(data) {
    // Update stats with number localization
    const stats = data.vessel_stats;
    updateNumberElement('outOfStockCount', stats.out_of_stock_count);
    updateNumberElement('lowStockCount', stats.low_stock_count);
    updateNumberElement('totalProductsCount', stats.total_products);
    updateNumberElement('inventoryValue', stats.total_inventory_value.toFixed(0));
    
    // Update table
    updateInventoryTable();
}

function updateNumberElement(elementId, value) {
    const element = document.getElementById(elementId);
    if (element) {
        element.setAttribute('data-original', value.toString());
        const translatedNumber = translateNumber(value.toString());
        element.textContent = translatedNumber;
    }
}

function updateInventoryTable() {
    const tbody = document.getElementById('inventoryTableBody');
    const tableStats = document.getElementById('tableStats');
    
    if (filteredData.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-muted py-4">
                    <i class="bi bi-search" style="font-size: 2rem;"></i>
                    <p class="mt-2 mb-0"><span data-translate="no_inventory_found">No inventory found</span></p>
                    <small><span data-translate="try_adjusting_search">Try adjusting your search or filter criteria</span></small>
                </td>
            </tr>
        `;
        tableStats.innerHTML = '<span data-translate="no_results_found">No results found</span>';
        updatePageTranslations();
        return;
    }
    
    tbody.innerHTML = filteredData.map(item => `
        <tr ${item.stock_status === 'low' ? 'class="table-warning"' : item.stock_status === 'out' ? 'class="table-danger"' : ''}>
            <td>
                <div>
                    <h6 class="mb-1">${item.product_name}</h6>
                    <small class="text-muted">
                        <span data-translate="item_id">ID</span>: <span class="product-id" data-number data-original="${item.product_item_id}">${item.product_item_id}</span>
                        ${item.product_barcode ? ` • ${item.product_barcode}` : ''}
                        ${item.is_duty_free ? '<span class="badge bg-warning text-dark ms-1"><span data-translate="duty_free">Duty-Free</span></span>' : ''}
                    </small>
                </div>
            </td>
            <td class="text-center">
                <span class="fw-bold ${item.stock_status === 'low' ? 'text-warning' : item.stock_status === 'out' ? 'text-danger' : ''}" data-number data-original="${item.total_quantity}">
                    ${item.total_quantity}
                </span>
                <small class="text-muted d-block"><span data-translate="units">units</span></small>
            </td>
            <td class="text-center">
                <span class="badge bg-${item.status_class}">
                    ${item.stock_status === 'out' ? '<span data-translate="out_of_stock_status">Out of Stock</span>' :
                    item.stock_status === 'low' ? '<span data-translate="low_stock_status">Low Stock</span>' :
                    '<span data-translate="good_stock_status">Good Stock</span>'}
                </span>
            </td>
            <td class="text-end">
                ${item.total_quantity > 0 ? 
                    `<span class="fw-bold" data-number data-original="${item.current_cost.toFixed(3)}">${item.current_cost.toFixed(3)}</span>
                     <small class="text-muted d-block"><span data-currency-symbol>JOD</span> (<span dir="ltr" data-translate="fifo">FIFO</span>)</small>` : 
                    '<span class="text-muted">--</span>'
                }
            </td>
            <td class="text-end">
                <span class="fw-bold" data-number data-original="${item.total_value.toFixed(3)}">${item.total_value.toFixed(3)}</span>
                <small class="text-muted d-block"><span data-currency-symbol>JOD</span></small>
            </td>
            <td class="text-center">
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-info" onclick="viewDetails('${item.product_id}', '${item.vessel_id}')" data-translate="view_details" title="View Details">
                        <i class="bi bi-eye"></i>
                    </button>
                    ${item.stock_status !== 'out' ? 
                        `<button class="btn btn-outline-warning" onclick="quickTransfer('${item.product_id}', '${item.vessel_name.toLowerCase()}')" data-translate="quick_transfer" title="Quick Transfer">
                            <i class="bi bi-arrow-right"></i>
                         </button>` :
                        `<button class="btn btn-danger" onclick="urgentRestock('${item.product_id}', '${item.vessel_name.toLowerCase()}')" data-translate="urgent_restock" title="Urgent Restock">
                            <i class="bi bi-exclamation-triangle"></i>
                         </button>`
                    }
                </div>
            </td>
        </tr>
    `).join('');
    
    // Update table stats
    const searchTerm = document.getElementById('productSearch').value.trim();
    const stockFilter = document.getElementById('stockFilter').value;
    const hasFilters = searchTerm || stockFilter;
    
    tableStats.innerHTML = `
        <span data-translate="showing">Showing</span> <span data-number data-original="${filteredData.length}">${filteredData.length}</span> <span data-translate="of">of</span> <span data-number data-original="${currentInventoryData.length}">${currentInventoryData.length}</span> <span data-translate="products">products</span>
        ${hasFilters ? '(<span dir="ltr" data-translate="filtered">filtered</span>)' : ''}
        <span data-translate="on">on</span> ${getVesselName(currentVessel)}
        ${hasFilters ? `<button class="btn btn-outline-secondary btn-sm ms-2" onclick="clearFilters()">
            <i class="bi bi-x-circle"></i> <span data-translate="clear_filters">Clear Filters</span>
        </button>` : ''}
    `;
    
    // ✅ CRITICAL FIX: Apply translations to dynamically generated content
    updatePageTranslations();
    
    // ✅ ADDITIONAL FIX: Specifically handle product IDs after table generation
    document.querySelectorAll('.product-id[data-number]').forEach(element => {
        const originalValue = element.getAttribute('data-original');
        if (originalValue && window.translator && window.translator.currentLanguage === 'ar') {
            element.textContent = window.translateNumber ? window.translateNumber(originalValue) : originalValue;
        } else if (originalValue) {
            element.textContent = originalValue;
        }
    });
}

function handleSearchInput() {
    // Debounce search input
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        applyFilters();
    }, 300);
}

function handleFilterChange() {
    applyFilters();
}

function applyFilters() {
    const searchTerm = document.getElementById('productSearch').value.trim().toLowerCase();
    const stockFilter = document.getElementById('stockFilter').value;
    
    filteredData = currentInventoryData.filter(item => {
        // Apply search filter
        let matchesSearch = true;
        if (searchTerm) {
            matchesSearch = 
                item.product_name.toLowerCase().includes(searchTerm) ||
                item.product_item_id.toLowerCase().includes(searchTerm) ||
                item.product_barcode.toLowerCase().includes(searchTerm);
        }
        
        // Apply stock filter
        let matchesStock = true;
        if (stockFilter) {
            matchesStock = item.stock_status === stockFilter;
        }
        
        return matchesSearch && matchesStock;
    });
    
    updateInventoryTable();
}

function clearFilters() {
    document.getElementById('productSearch').value = '';
    document.getElementById('stockFilter').value = '';
    
    if (currentInventoryData.length > 0) {
        filteredData = [...currentInventoryData];
        updateInventoryTable();
    }
}

// Utility function to get vessel name in current language
function getVesselName(vessel) {
    if (!vessel) return '';
    const currentLang = window.translator ? window.translator.currentLanguage : 'en';
    if (currentLang === 'ar' && vessel.name_ar) {
        return vessel.name_ar;
    }
    return vessel.name;
}

// Existing functions
function viewDetails(productId, vesselId) {
    const modalContent = document.getElementById('modalContent');
    modalContent.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2"><span data-translate="loading_details">Loading details...</span></p></div>';
    
    new bootstrap.Modal(document.getElementById('productModal')).show();
    updatePageTranslations(); // Apply translations to modal content
    
    fetch(`/inventory/details/${productId}/${vesselId}/`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                modalContent.innerHTML = `
                    <div class="row">
                        <div class="col-md-6">
                            <h6><i class="bi bi-box-seam"></i> <span data-translate="product_information">Product Information</span></h6>
                            <table class="table table-sm">
                                <tr><td><strong><span data-translate="product_name">Product Name</span>:</strong></td><td>${data.product.name}</td></tr>
                                <tr><td><strong><span data-translate="item_id">Item ID</span>:</strong></td><td>${data.product.item_id}</td></tr>
                                <tr><td><strong><span data-translate="barcode">Barcode</span>:</strong></td><td>${data.product.barcode}</td></tr>
                                <tr><td><strong><span data-translate="category">Category</span>:</strong></td><td>${data.product.category}</td></tr>
                                <tr><td><strong><span data-translate="purchase_price">Purchase Price</span>:</strong></td><td><span data-number data-original="${data.product.purchase_price.toFixed(3)}">${data.product.purchase_price.toFixed(3)}</span> <span data-currency-symbol>JOD</span></td></tr>
                                <tr><td><strong><span data-translate="selling_price">Selling Price</span>:</strong></td><td><span data-number data-original="${data.product.selling_price.toFixed(3)}">${data.product.selling_price.toFixed(3)}</span> <span data-currency-symbol>JOD</span></td></tr>
                                <tr><td><strong><span data-translate="duty_free">Duty-Free</span>:</strong></td><td><span data-translate="${data.product.is_duty_free ? 'yes' : 'no'}">${data.product.is_duty_free ? 'Yes' : 'No'}</span></td></tr>
                            </table>
                        </div>
                        <div class="col-md-6">
                            <h6><i class="bi bi-ship"></i> <span data-translate="vessel_information">Vessel Information</span></h6>
                            <table class="table table-sm">
                                <tr><td><strong><span data-translate="vessel_name">Vessel Name</span>:</strong></td><td>${getVesselName(data.vessel)}</td></tr>
                                <tr><td><strong><span data-translate="supports_duty_free">Supports Duty-Free</span>:</strong></td><td><span data-translate="${data.vessel.has_duty_free ? 'yes' : 'no'}">${data.vessel.has_duty_free ? 'Yes' : 'No'}</span></td></tr>
                            </table>
                        </div>
                    </div>
                    <div class="row mt-3">
                        <div class="col-md-6">
                            <h6><i class="bi bi-layers"></i> <span data-translate="fifo_inventory_lots">FIFO Inventory Lots</span></h6>
                            <div class="table-responsive">
                                <table class="table table-sm">
                                    <thead>
                                        <tr>
                                            <th><span data-translate="purchase_date">Purchase Date</span></th>
                                            <th><span data-translate="remaining">Remaining</span></th>
                                            <th><span data-translate="unit_cost">Unit Cost</span></th>
                                            <th><span data-translate="total_value">Total Value</span></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${data.lots.map(lot => `
                                            <tr>
                                                <td>${lot.purchase_date}</td>
                                                <td><span data-number data-original="${lot.remaining_quantity}">${lot.remaining_quantity}</span>/<span data-number data-original="${lot.original_quantity}">${lot.original_quantity}</span></td>
                                                <td><span data-number data-original="${lot.purchase_price.toFixed(3)}">${lot.purchase_price.toFixed(3)}</span></td>
                                                <td><span data-number data-original="${lot.total_value.toFixed(3)}">${lot.total_value.toFixed(3)}</span></td>
                                            </tr>
                                        `).join('')}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <h6><i class="bi bi-clock-history"></i> <span data-translate="recent_transactions">Recent Transactions</span></h6>
                            <div class="table-responsive">
                                <table class="table table-sm">
                                    <thead>
                                        <tr>
                                            <th><span data-translate="date">Date</span></th>
                                            <th><span data-translate="type">Type</span></th>
                                            <th><span data-translate="quantity">Quantity</span></th>
                                            <th><span data-translate="amount">Amount</span></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${data.recent_transactions.map(txn => `
                                            <tr>
                                                <td>${txn.date}</td>
                                                <td>
                                                    <span class="badge ${
                                                        txn.type_code === 'SALE' ? 'bg-success' :
                                                        txn.type_code === 'SUPPLY' ? 'bg-primary' :
                                                        txn.type_code === 'TRANSFER_OUT' ? 'bg-warning' :
                                                        'bg-info'
                                                    }">${txn.type}</span>
                                                </td>
                                                <td><span data-number data-original="${txn.quantity}">${txn.quantity}</span></td>
                                                <td><span data-number data-original="${txn.total_amount.toFixed(3)}">${txn.total_amount.toFixed(3)}</span></td>
                                            </tr>
                                        `).join('')}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                `;
                updatePageTranslations(); // Apply translations to modal content
            } else {
                modalContent.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle"></i> 
                        <span data-translate="error_loading_product_details">Error loading product details</span>: ${data.error}
                    </div>
                `;
                updatePageTranslations();
            }
        })
        .catch(error => {
            modalContent.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle"></i> 
                    <span data-translate="error_loading_product_details">Error loading product details. Please try again.</span>
                </div>
            `;
            updatePageTranslations();
            console.error('Error:', error);
        });
}

function quickTransfer(productId, fromVessel) {
  const transferUrl = window.URLS.transferEntry;
  window.location.href = `${transferUrl}?product=${productId}&from=${fromVessel}`;
}

function urgentRestock(productId, vessel) {
  if (
    confirmTranslated('urgent_restock_needed', {
      productId,
      vessel,
      message: 'redirect_supply_entry'
    })
  ) {
    window.location.href = window.URLS.supplyEntry;
  }
}

function exportInventoryData() {
    // Check if vessel is selected
    if (!currentVessel) {
        alertTranslated('please_select_vessel');
        return;
    }
    
    // Get current filters
    const stockFilter = document.getElementById('stockFilter')?.value || '';
    const searchFilter = document.getElementById('searchInput')?.value || '';
    
    // Get current language
    const currentLanguage = window.translator ? window.translator.currentLanguage : 
                           localStorage.getItem('preferred_language') || 'en';
    
    // Extract vessel ID properly
    let vesselId;
    if (typeof currentVessel === 'object' && currentVessel.id) {
        vesselId = currentVessel.id;
    } else if (typeof currentVessel === 'string' || typeof currentVessel === 'number') {
        vesselId = currentVessel;
    } else {
        console.error('Invalid currentVessel format:', currentVessel);
        alertTranslated('please_select_vessel');
        return;
    }
    
    // Prepare additional data with filters (REMOVED min level logic)
    const additionalData = {
        vessel_id: vesselId,
        stock_filter: stockFilter,
        search_filter: searchFilter,
        low_stock_only: stockFilter === 'low',  // Low stock = quantity < 10 (defined in backend)
        language: currentLanguage
    };
    
    console.log('Exporting inventory with data:', additionalData);
    
    // Show export modal using the global function
    window.showUnifiedExportModal('inventory', additionalData);
}

const showComingSoon = (feature) => window.templateUtils.showComingSoonAlert(feature);
const printInventory = () => window.templateUtils.showPrintComingSoon();

window.switchVessel = switchVessel;
window.handleFilterChange = handleFilterChange;
window.loadInventoryData = loadInventoryData;
window.handleSearchInput = handleSearchInput;
window.viewDetails = viewDetails;
window.quickTransfer = quickTransfer;
window.urgentRestock = urgentRestock;
window.exportInventoryData = exportInventoryData;
window.showComingSoon = showComingSoon;
window.printInventory = printInventory;
})();