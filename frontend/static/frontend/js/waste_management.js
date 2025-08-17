document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'waste_management',
        fallbackTitle: 'Waste Management',
    })
    
    // Update page translations
    updatePageTranslations();
});

function toggleColumn(columnClass) {
    const columns = document.querySelectorAll(`.${columnClass}-column`);
    const isVisible = columns[0].style.display !== 'none';
    
    columns.forEach(col => {
        col.style.display = isVisible ? 'none' : '';
    });
}

function getFilterData() {
    return {
        vessel: document.getElementById('vesselFilter').value,
        status: document.getElementById('statusFilter').value,
        date_from: document.getElementById('dateFromFilter').value,
        date_to: document.getElementById('dateToFilter').value,
        min_cost: document.querySelector('input[name="min_cost"]').value,
    };
}

function editWasteReport(wasteId) {
    fetch(`/wastes/${wasteId}/edit/`, {
        method: 'GET',
        headers: {
            'X-CSRFToken': window.getCsrfToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('editWasteReportId').value = data.waste_report.id;
            document.getElementById('editReportNumber').value = data.waste_report.report_number;
            document.getElementById('editVesselName').value = data.waste_report.vessel_name;
            document.getElementById('editReportDate').value = data.waste_report.report_date;
            document.getElementById('editWasteNotes').value = data.waste_report.notes;

            const completedToggle = document.getElementById('editWasteCompleted');
            if (completedToggle) {
                completedToggle.checked = data.waste_report.is_completed;
            }
            
            // FIXED: Store complete waste data including items for preservation
            window.currentWasteReportData = {
                is_completed: data.waste_report.is_completed,
                waste_items: data.waste_items || [] // Include waste items data
            };

            new bootstrap.Modal(document.getElementById('editWasteReportModal')).show();
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error loading waste report data', 'danger');
    });
}

function saveWasteReport() {
    const wasteId = document.getElementById('editWasteReportId').value;
    const completedToggle = document.getElementById('editWasteCompleted');
    
    const formData = {
        report_date: document.getElementById('editReportDate').value,
        notes: document.getElementById('editWasteNotes').value
    };
    
    // Check if status is changing (only if toggle exists - admin/manager only)
    let statusChanged = false;
    let newStatus = null;
    
    if (completedToggle) {
        const currentStatus = window.currentWasteReportData && window.currentWasteReportData.is_completed;
        newStatus = completedToggle.checked;
        statusChanged = currentStatus !== newStatus;
        
        if (statusChanged) {
            // Status is changing - show confirmation
            const confirmMessage = newStatus 
                ? 'Mark this waste report as completed? This will finalize all waste transactions and prevent further editing.'
                : 'Reopen this completed waste report? This will allow editing of waste transactions and report details.';
            
            document.getElementById('statusChangeMessage').innerHTML = confirmMessage;
            
            // Set up confirmation handler
            document.getElementById('confirmStatusChange').onclick = function() {
                performWasteReportUpdate(wasteId, formData, statusChanged, newStatus);
                bootstrap.Modal.getInstance(document.getElementById('statusChangeConfirmModal')).hide();
            };
            
            new bootstrap.Modal(document.getElementById('statusChangeConfirmModal')).show();
            return;
        }
    }
    
    // No status change - proceed with normal update
    performWasteReportUpdate(wasteId, formData, statusChanged, newStatus);
}

function performWasteReportUpdate(wasteId, formData, statusChanged, newStatus) {
    const saveButton = document.querySelector('#editWasteReportModal .btn-primary');
    window.standardizeLoadingStates(saveButton, true);

    if (statusChanged) {
        // FIXED: Before toggling completed→incomplete, preserve cart data
        if (newStatus === false) { // Going from completed to incomplete
            preserveWasteCartBeforeToggle(wasteId);
        }
        
        // Use toggle endpoint for status changes (with transaction deletion)
        fetch(`/wastes/${wasteId}/toggle-status/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.getCsrfToken()
            },
            body: JSON.stringify({})
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // After successful status toggle, update other fields if needed
                if (formData.report_date || formData.notes) {
                    updateWasteReportFields(wasteId, formData, saveButton, data.message);
                } else {
                    handleWasteUpdateSuccess(saveButton, data.message);
                }
            } else {
                handleWasteUpdateError(saveButton, data.error || 'Failed to update waste report status');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            handleWasteUpdateError(saveButton, 'Error updating waste report status');
        });
    } else {
        // Use edit endpoint for normal field updates (no status change)
        updateWasteReportFields(wasteId, formData, saveButton, null);
    }
}

// FIXED: New function to preserve cart data before toggle
function preserveWasteCartBeforeToggle(wasteId) {
    try {
        // Extract current waste items from the current waste report data
        // This data comes from the modal when we opened it
        const currentWasteData = window.currentWasteReportData;
        
        if (currentWasteData && currentWasteData.waste_items) {
            // Store the items in localStorage with special preservation key
            const preserveKey = `waste_toggle_preserve_${wasteId}`;
            const cartData = currentWasteData.waste_items.map(item => ({
                product_id: item.product_id,
                product_name: item.product_name,
                product_item_id: item.product_item_id,
                quantity: item.quantity,
                unit_cost: item.unit_cost || item.unit_price || 0,
                total_cost: item.total_cost || 0,
                damage_reason: item.damage_reason,
                notes: item.notes || ''
            }));
            
            localStorage.setItem(preserveKey, JSON.stringify({
                items: cartData,
                timestamp: Date.now(),
                preserved_from: 'toggle_operation'
            }));
            
            console.log(`🔄 TOGGLE PRESERVE: Saved ${cartData.length} items for waste ${wasteId}`);
        }
    } catch (error) {
        console.error('Error preserving cart data before toggle:', error);
        // Don't block the toggle operation if preservation fails
    }
}

function updateWasteReportFields(wasteId, formData, saveButton, previousMessage) {
    fetch(`/wastes/${wasteId}/edit/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.getCsrfToken()
        },
        body: JSON.stringify(formData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Combine messages if there was a previous status change
            const finalMessage = previousMessage 
                ? `${previousMessage} Report details updated successfully.`
                : data.message;
            handleWasteUpdateSuccess(saveButton, finalMessage);
        } else {
            handleWasteUpdateError(saveButton, data.error || 'Failed to update waste report');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        handleWasteUpdateError(saveButton, 'Error updating waste report');
    });
}

function handleWasteUpdateSuccess(saveButton, message) {
    window.standardizeLoadingStates(saveButton, false);
    window.showAlert(message, 'success');
    bootstrap.Modal.getInstance(document.getElementById('editWasteReportModal')).hide();
    setTimeout(() => location.reload(), 1000); // Refresh to show updated data
}

function handleWasteUpdateError(saveButton, errorMessage) {
    window.standardizeLoadingStates(saveButton, false);
    window.showAlert(errorMessage, 'danger');
}

function performWasteReportSave(wasteId, formData) {
    const saveButton = document.querySelector('#editWasteReportModal .btn-primary');
    window.standardizeLoadingStates(saveButton, true);

    fetch(`/wastes/${wasteId}/edit/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.getCsrfToken()
        },
        body: JSON.stringify(formData)
    })
    .then(response => response.json())
    .then(data => {
        window.standardizeLoadingStates(saveButton, false);
        
        if (data.success) {
            window.showAlert(data.message, 'success');
            bootstrap.Modal.getInstance(document.getElementById('editWasteReportModal')).hide();
            setTimeout(() => location.reload(), 1000);
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.standardizeLoadingStates(saveButton, false);
        window.showAlert('Error saving waste report', 'danger');
    });
}

function deleteWasteReport(wasteId) {
    fetch(`/wastes/${wasteId}/delete/`, {
        method: 'DELETE',
        headers: {
            'X-CSRFToken': window.getCsrfToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.showAlert(data.message, 'success');
            location.reload();
        } else if (data.requires_confirmation) {
            showTransactionConfirmationModal('waste', wasteId, data);
        } else {
            window.showAlert(data.error || 'Failed to delete waste report', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error deleting waste report', 'danger');
    });

}

function showTransactionConfirmationModal(type, id, data) {
    const title = 'Delete Waste Report with Items';
    const entityName = 'waste report';
    
    // Build waste items list
    let itemsList = '<ul class="list-group list-group-flush mb-3">';
    data.items.forEach(item => {
        itemsList += `
            <li class="list-group-item d-flex justify-content-between">
                <div>
                    <span>${item.product_name}</span>
                    <br><small class="text-muted">${item.damage_reason}</small>
                </div>
                <div class="text-end">
                    <span class="badge bg-primary me-2">${item.quantity} units</span>
                    <span class="fw-bold">${item.amount.toFixed(3)} JOD</span>
                </div>
            </li>
        `;
    });
    itemsList += '</ul>';
    
    const modalHTML = `
        <div class="modal fade" id="deleteConfirmationModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header bg-danger text-white">
                        <h5 class="modal-title">
                            <i class="bi bi-exclamation-triangle me-2"></i>
                            ${title}
                        </h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="alert alert-warning">
                            <i class="bi bi-exclamation-triangle me-2"></i>
                            <strong>Warning!</strong> This ${entityName} "${data.waste_report_number}" has <strong>${data.waste_item_count} waste items</strong> that will be restored to inventory.
                        </div>
                        
                        <div class="row mb-3">
                            <div class="col-md-6">
                                <div class="card bg-light">
                                    <div class="card-body text-center">
                                        <h6 class="card-title">Total Waste Cost</h6>
                                        <h4 class="text-primary">${data.total_cost.toFixed(3)} JOD</h4>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="card bg-light">
                                    <div class="card-body text-center">
                                        <h6 class="card-title">Waste Items</h6>
                                        <h4 class="text-danger">${data.waste_item_count}</h4>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <h6>Waste items to be restored to inventory:</h6>
                        ${itemsList}
                        
                        <div class="alert alert-info">
                            <i class="bi bi-info-circle me-2"></i>
                            <strong>Inventory Restoration:</strong> All waste items will be returned to inventory for vessel "${data.vessel_name}".
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            <i class="bi bi-x-circle me-1"></i> Cancel
                        </button>
                        <button type="button" class="btn btn-danger" onclick="confirmForceDelete('waste', ${id})">
                            <i class="bi bi-trash me-1"></i> Delete Waste Report & Restore Inventory
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal if any
    const existingModal = document.getElementById('deleteConfirmationModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // Show modal
    new bootstrap.Modal(document.getElementById('deleteConfirmationModal')).show();
}

function confirmForceDelete(type, id) {
    // Immediately blur the button that triggered this
    if (document.activeElement && document.activeElement.tagName === 'BUTTON') {
        document.activeElement.blur();
    }
    
    const url = `/wastes/${id}/delete/`;
    
    // Close the confirmation modal first
    const confirmModal = document.getElementById('deleteConfirmationModal');
    if (confirmModal) {
        const modalInstance = bootstrap.Modal.getInstance(confirmModal);
        if (modalInstance) {
            modalInstance.hide();
        }
        confirmModal.remove();
    }
    
    // Remove any modal backdrops
    const backdrops = document.querySelectorAll('.modal-backdrop');
    backdrops.forEach(backdrop => backdrop.remove());
    
    fetch(url, {
        method: 'DELETE',
        headers: {
            'X-CSRFToken': window.getCsrfToken(),
            'X-Force-Delete': 'true'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.showAlert(data.message, 'success');
            location.reload();
        } else {
            window.showAlert(data.error || 'Failed to delete waste report', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error deleting waste report', 'danger');
    });
}