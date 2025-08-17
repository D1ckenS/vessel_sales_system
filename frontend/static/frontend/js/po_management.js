// PO Management JavaScript - EXACT COPY from template (NO MODIFICATIONS)

document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'po_management',
        fallbackTitle: 'PO Management',
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
    };
}

function editPO(poId) {
    fetch(`/purchase-orders/${poId}/edit/`, {
        method: 'GET',
        headers: {
            'X-CSRFToken': window.getCsrfToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('editPOId').value = data.po.id;
            document.getElementById('editPONumber').value = data.po.po_number;
            document.getElementById('editPODate').value = data.po.po_date;
            document.getElementById('editPONotes').value = data.po.notes;

            // Set PO completion status toggle (admin/manager only)
            const completedToggle = document.getElementById('editPOCompleted');
            if (completedToggle) {
                completedToggle.checked = data.po.is_completed;
            }
            
            // Store current PO data for status change detection
            window.currentPOData = {
                is_completed: data.po.is_completed
            };

            new bootstrap.Modal(document.getElementById('editPOModal')).show();
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error loading PO data', 'danger');
    });
}

function savePO() {
    const poId = document.getElementById('editPOId').value;
    const completedToggle = document.getElementById('editPOCompleted');
    
    const formData = {
        po_date: document.getElementById('editPODate').value,
        notes: document.getElementById('editPONotes').value
    };
    
    // Add completion status if toggle exists (admin/manager only)
    if (completedToggle) {
        formData.is_completed = completedToggle.checked;
        
        // Check if status is changing
        const currentStatus = window.currentPOData && window.currentPOData.is_completed;
        const newStatus = completedToggle.checked;
        
        if (currentStatus !== newStatus) {
            // Status is changing - show confirmation
            const confirmMessage = newStatus 
                ? 'Mark this PO as completed? This will finalize all supply transactions and prevent further editing.'
                : 'Reopen this completed PO? This will allow editing of supply transactions and PO details.';
            
            showPOStatusChangeConfirmation(confirmMessage, formData, poId);
            return; // Exit here, modal will handle the save
        }
    }
    
    // Proceed with save (no status change)
    executePOSave(formData, poId);
}

function showPOStatusChangeConfirmation(message, formData, poId) {
    // Set the message
    document.getElementById('poStatusChangeMessage').textContent = message;
    
    // Show the modal
    const modal = new bootstrap.Modal(document.getElementById('poStatusChangeConfirmModal'));
    modal.show();
    
    // Handle confirmation
    document.getElementById('confirmPOStatusChange').onclick = function() {
        // Hide confirmation modal
        modal.hide();
        
        // Proceed with the actual save
        executePOSave(formData, poId);
    };
}

function executePOSave(formData, poId) {
    fetch(`/purchase-orders/${poId}/edit/`, {
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
            window.showAlert(data.message, 'success');
            bootstrap.Modal.getInstance(document.getElementById('editPOModal')).hide();
            setTimeout(() => location.reload(), 1000);
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error saving PO', 'danger');
    });
}

// Update the deletePO function to use the new error handler
function deletePO(poId) {
    fetch(`/purchase-orders/${poId}/delete/`, {
        method: 'DELETE',
        headers: {
            'X-CSRFToken': window.getCsrfToken()
        }
    })
    .then(response => {
        // Check if response is JSON
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return response.json();
        } else {
            // If it's not JSON (like an HTML error page), throw an error
            throw new Error(`Server returned ${response.status}: ${response.statusText}`);
        }
    })
    .then(data => {
        if (data.success) {
            window.showAlert(data.message, 'success');
            location.reload();
        } else if (data.requires_confirmation) {
            showTransactionConfirmationModal('po', poId, data);
        } else {
            // Use enhanced error handling
            handleDeletionError(data);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        // More specific error message
        if (error.message.includes('500')) {
            window.showAlert('Server error occurred. The operation may have inventory conflicts that prevent deletion.', 'danger');
        } else if (error.message.includes('Unexpected token')) {
            window.showAlert('Server returned an invalid response. Please try again.', 'danger');
        } else {
            window.showAlert('Error deleting PO: ' + error.message, 'danger');
        }
    });
}

function showTransactionConfirmationModal(type, id, data) {
    const isTrip = type === 'trip';
    const title = isTrip ? 'Delete Trip with Transactions' : 'Delete PO with Transactions';
    const entityName = isTrip ? 'trip' : 'purchase order';
    const totalLabel = isTrip ? 'Total Revenue' : 'Total Cost';
    const totalValue = isTrip ? data.total_revenue : data.total_cost;
    
    // Build transaction list
    let transactionsList = '<ul class="list-group list-group-flush mb-3">';
    data.transactions.forEach(trans => {
        transactionsList += `
            <li class="list-group-item d-flex justify-content-between">
                <span>${trans.product_name}</span>
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
                            <strong>Warning!</strong> This ${entityName} has <strong>${data.transaction_count} transactions</strong> that will also be deleted.
                        </div>
                        
                        <div class="row mb-3">
                            <div class="col-md-6">
                                <div class="card bg-light">
                                    <div class="card-body text-center">
                                        <h6 class="card-title">${totalLabel}</h6>
                                        <h4 class="text-primary">${totalValue.toFixed(3)} JOD</h4>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="card bg-light">
                                    <div class="card-body text-center">
                                        <h6 class="card-title">Transactions</h6>
                                        <h4 class="text-danger">${data.transaction_count}</h4>
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
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            <i class="bi bi-x-circle me-1"></i> Cancel
                        </button>
                        <button type="button" class="btn btn-danger" onclick="this.blur(); confirmForceDelete('${type}', ${id})">
                            <i class="bi bi-trash me-1"></i> Delete ${entityName.charAt(0).toUpperCase() + entityName.slice(1)} & Transactions
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

function handleDeletionError(data) {
    // Check if it's an inventory consumption error with suggested actions
    if (data.error_type === 'inventory_consumption_blocked' && data.suggested_actions) {
        showInventoryBlockedModal(data);
    } else {
        // Standard error display - handle both error and error_message
        const errorMsg = data.error || data.error_message || data.message || 'An error occurred';
        window.showAlert(errorMsg, 'danger');
    }
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

function confirmForceDelete(type, id) {
    const url = type === 'trip' ?
        `/trips/${id}/delete/` :       
        `/purchase-orders/${id}/delete/`;  
    
    fetch(url, {
        method: 'DELETE',
        headers: {
            'X-CSRFToken': window.getCsrfToken(),
            'X-Force-Delete': 'true'
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
        if (data.success) {
            // Properly close modal before reload
            const modal = bootstrap.Modal.getInstance(document.getElementById('deleteConfirmationModal'));
            if (modal) {
                modal.hide();
            }
            window.showAlert(data.message, 'success');
            location.reload();
        } else {
            // Close the confirmation modal first, then show error
            const modal = bootstrap.Modal.getInstance(document.getElementById('deleteConfirmationModal'));
            if (modal) {
                modal.hide();
            }
            
            // Small delay to let the modal close before showing error
            setTimeout(() => {
                handleDeletionError(data);
            }, 200);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        
        // Close modal on error too
        const modal = bootstrap.Modal.getInstance(document.getElementById('deleteConfirmationModal'));
        if (modal) {
            modal.hide();
        }
        
        setTimeout(() => {
            if (error.message.includes('400')) {
                window.showAlert('Cannot delete: This item has dependencies that prevent deletion.', 'danger');
            } else {
                window.showAlert(`Error deleting ${type}: ${error.message}`, 'danger');
            }
        }, 200);
    });
}
