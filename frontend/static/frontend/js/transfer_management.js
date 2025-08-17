// Transfer management JavaScript functions
function toggleColumn(columnClass) {
    const columns = document.querySelectorAll(`.${columnClass}-column`);
    const isVisible = columns[0].style.display !== 'none';
    columns.forEach(col => {
        col.style.display = isVisible ? 'none' : '';
    });
}

function editTransfer(transferId) {
    fetch(`/transfers/${transferId}/edit/`, {
        method: 'GET',
        headers: {
            'X-CSRFToken': window.getCsrfToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('editTransferId').value = data.transfer.id;
            document.getElementById('editFromVessel').value = data.transfer.from_vessel;
            document.getElementById('editToVessel').value = data.transfer.to_vessel;
            document.getElementById('editTransferDate').value = data.transfer.transfer_date;
            document.getElementById('editTransferNotes').value = data.transfer.notes;

            const completedToggle = document.getElementById('editTransferCompleted');
            if (completedToggle) {
                completedToggle.checked = data.transfer.is_completed;
            }
            
            // FIXED: Store complete transfer data including items for preservation
            window.currentTransferData = {
                is_completed: data.transfer.is_completed,
                transfer_items: data.transfer_items || [] // Include transfer items data
            };

            new bootstrap.Modal(document.getElementById('editTransferModal')).show();
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error loading transfer data', 'danger');
    });
}

function saveTransfer() {
    const transferId = document.getElementById('editTransferId').value;
    const completedToggle = document.getElementById('editTransferCompleted');
    
    const formData = {
        transfer_date: document.getElementById('editTransferDate').value,
        notes: document.getElementById('editTransferNotes').value
    };
    
    // Check if status is changing (only if toggle exists - admin/manager only)
    let statusChanged = false;
    let newStatus = null;
    
    if (completedToggle) {
        const currentStatus = window.currentTransferData && window.currentTransferData.is_completed;
        newStatus = completedToggle.checked;
        statusChanged = currentStatus !== newStatus;
        
        if (statusChanged) {
            // Status is changing - show confirmation
            const confirmMessage = newStatus 
                ? 'Mark this transfer as completed? This will finalize all transactions and prevent further editing.'
                : 'Reopen this completed transfer? This will allow editing of transactions and transfer details.';
            
            showStatusChangeConfirmation(confirmMessage, formData, transferId, statusChanged, newStatus);
            return;
        }
    }
    
    // No status change - proceed with normal update
    performTransferUpdate(transferId, formData, statusChanged, newStatus);
}

function showStatusChangeConfirmation(message, formData, transferId, statusChanged, newStatus) {
    document.getElementById('statusChangeMessage').textContent = message;
    
    const modal = new bootstrap.Modal(document.getElementById('statusChangeConfirmModal'));
    modal.show();
    
    document.getElementById('confirmStatusChange').onclick = function() {
        modal.hide();
        performTransferUpdate(transferId, formData, statusChanged, newStatus);
    };
}

function performTransferUpdate(transferId, formData, statusChanged, newStatus) {
    const saveButton = document.querySelector('#editTransferModal .btn-primary');
    window.standardizeLoadingStates(saveButton, true);

    if (statusChanged) {
        // FIXED: Before toggling completed→incomplete, preserve cart data
        if (newStatus === false) { // Going from completed to incomplete
            preserveTransferCartBeforeToggle(transferId);
        }
        
        // Use toggle endpoint for status changes (with transaction deletion)
        fetch(`/transfers/${transferId}/toggle-status/`, {
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
                if (formData.transfer_date || formData.notes) {
                    updateTransferFields(transferId, formData, saveButton, data.message);
                } else {
                    handleTransferUpdateSuccess(saveButton, data.message);
                }
            } else {
                handleTransferUpdateError(saveButton, data.error || 'Failed to update transfer status');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            handleTransferUpdateError(saveButton, 'Error updating transfer status');
        });
    } else {
        // Use edit endpoint for normal field updates (no status change)
        updateTransferFields(transferId, formData, saveButton, null);
    }
}

function preserveTransferCartBeforeToggle(transferId) {
    try {
        const currentTransferData = window.currentTransferData;
        
        if (currentTransferData && currentTransferData.transfer_items) {
            const preserveKey = `transfer_toggle_preserve_${transferId}`;
            const cartData = currentTransferData.transfer_items.map(item => ({
                product_id: item.product_id,
                product_name: item.product_name,
                product_item_id: item.product_item_id,
                quantity: item.quantity,
                unit_cost: item.unit_cost || item.unit_price || 0,
                total_cost: item.total_cost || 0,
                notes: item.notes || ''
            }));
            
            localStorage.setItem(preserveKey, JSON.stringify({
                items: cartData,
                timestamp: Date.now(),
                preserved_from: 'toggle_operation'
            }));
            
            console.log(`🔄 TRANSFER TOGGLE PRESERVE: Saved ${cartData.length} items for transfer ${transferId}`);
        }
    } catch (error) {
        console.error('Error preserving transfer cart data before toggle:', error);
    }
}

function updateTransferFields(transferId, formData, saveButton, previousMessage) {
    fetch(`/transfers/${transferId}/edit/`, {
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
            const finalMessage = previousMessage 
                ? `${previousMessage} Transfer details updated successfully.`
                : data.message;
            handleTransferUpdateSuccess(saveButton, finalMessage);
        } else {
            handleTransferUpdateError(saveButton, data.error || 'Failed to update transfer');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        handleTransferUpdateError(saveButton, 'Error updating transfer');
    });
}

function handleTransferUpdateSuccess(saveButton, message) {
    window.standardizeLoadingStates(saveButton, false);
    window.showAlert(message, 'success');
    bootstrap.Modal.getInstance(document.getElementById('editTransferModal')).hide();
    setTimeout(() => location.reload(), 1000);
}

function handleTransferUpdateError(saveButton, errorMessage) {
    window.standardizeLoadingStates(saveButton, false);
    window.showAlert(errorMessage, 'danger');
}

function executeTransferSave(formData, transferId) {
    const saveButton = document.querySelector('#editTransferModal .btn-primary');
    window.standardizeLoadingStates(saveButton, true);

    fetch(`/transfers/${transferId}/edit/`, {
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
            bootstrap.Modal.getInstance(document.getElementById('editTransferModal')).hide();
            setTimeout(() => location.reload(), 1000);
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.standardizeLoadingStates(saveButton, false);
        window.showAlert('Error saving transfer', 'danger');
    });
}

function deleteTransfer(transferId) {

    const existingModals = document.querySelectorAll('.modal.show, .modal[aria-hidden="false"]');
    existingModals.forEach(modal => {
        const modalInstance = bootstrap.Modal.getInstance(modal);
        if (modalInstance) {
            modalInstance.hide();
        }
        modal.setAttribute('aria-hidden', 'true');
        modal.style.display = 'none';
    });
    
    // Remove any modal backdrops
    const backdrops = document.querySelectorAll('.modal-backdrop');
    backdrops.forEach(backdrop => backdrop.remove());
    
    fetch(`/transfers/${transferId}/delete/`, {
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
            // Use the same pattern as trips - this is proven to work
            showTransactionConfirmationModal('transfer', transferId, data);
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error deleting transfer', 'danger');
    });
}

function showTransactionConfirmationModal(type, id, data) {
    const isTransfer = type === 'transfer';
    const title = isTransfer ? 'Delete Transfer with Transactions' : 
                  type === 'trip' ? 'Delete Trip with Transactions' : 'Delete PO with Transactions';
    const entityName = isTransfer ? 'transfer' : (type === 'trip' ? 'trip' : 'purchase order');
    const totalLabel = isTransfer ? 'Total Cost' : (type === 'trip' ? 'Total Revenue' : 'Total Cost');
    const totalValue = isTransfer ? data.total_cost : (type === 'trip' ? data.total_revenue : data.total_cost);
    
    // Build transaction list (same for all types)
    let transactionsList = '<ul class="list-group list-group-flush mb-3">';
    data.transactions.forEach(trans => {
        const typeLabel = isTransfer ? ` (${trans.type})` : '';
        transactionsList += `
            <li class="list-group-item d-flex justify-content-between">
                <span>${trans.product_name}${typeLabel}</span>
                <div>
                    <span class="badge bg-primary me-2">${trans.quantity} units</span>
                    <span class="fw-bold">
                        ${typeof trans.amount === 'number' ? trans.amount.toFixed(3) + ' JOD' : 'N/A'}
                    </span>
                </div>
            </li>
        `;
    });
    transactionsList += '</ul>';
    
    // 🔧 FIXED: Safe access to transaction_count
    const transactionCount = data.transaction_count || data.transactions.length || 0;
    
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
                            <strong>Warning!</strong> This ${entityName} has <strong>${transactionCount} transactions</strong> that will also be deleted.
                        </div>
                        
                        <div class="row mb-3">
                            <div class="col-md-6">
                                <div class="card">
                                    <div class="card-body text-center">
                                        <h5 class="card-title">${totalLabel}</h5>
                                        <h3 class="text-primary">${typeof totalValue === 'number' ? totalValue.toFixed(3) : totalValue} JOD</h3>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="card">
                                    <div class="card-body text-center">
                                        <h5 class="card-title">Transactions</h5>
                                        <h3 class="text-info">${transactionCount}</h3>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <h6>Transactions to be deleted:</h6>
                        ${transactionsList}
                        
                        <div class="alert alert-danger">
                            <i class="bi bi-exclamation-octagon me-2"></i>
                            <strong>This action cannot be undone!</strong> All transactions and related inventory changes will be permanently deleted.
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-danger" onclick="confirmDelete${type.charAt(0).toUpperCase() + type.slice(1)}(${id})">
                            <i class="bi bi-trash me-2"></i>Delete ${entityName.charAt(0).toUpperCase() + entityName.slice(1)}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal if any
    const existingModal = document.getElementById('deleteConfirmationModal');
    if (existingModal) existingModal.remove();
    
    // Add modal to DOM
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('deleteConfirmationModal'));
    modal.show();
    
    // Clean up on hide
    document.getElementById('deleteConfirmationModal').addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
}

function confirmDeleteTransfer(transferId) {
    // Force delete with confirmation
    fetch(`/transfers/${transferId}/delete/`, {
        method: 'DELETE',
        headers: {
            'X-CSRFToken': window.getCsrfToken(),
            'X-Force-Delete': 'true'
        }
    })
    .then(response => response.json())
    .then(data => {
        // Hide modal first
        const modal = bootstrap.Modal.getInstance(document.getElementById('deleteConfirmationModal'));
        if (modal) modal.hide();
        
        if (data.success) {
            window.showAlert(data.message, 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error deleting transfer', 'danger');
    });
}

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'transfer_management',
        fallbackTitle: 'Transfer Management'
    });
});