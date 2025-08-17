document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'trip_management',
        fallbackTitle: 'Trip Management',
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
        min_revenue: document.querySelector('input[name="min_revenue"]').value,
    };
}

function editTrip(tripId) {
    fetch(`/trips/${tripId}/edit/`, {
        method: 'GET',
        headers: {
            'X-CSRFToken': window.getCsrfToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('editTripId').value = data.trip.id;
            document.getElementById('editTripNumber').value = data.trip.trip_number;
            document.getElementById('editPassengerCount').value = data.trip.passenger_count;
            document.getElementById('editTripDate').value = data.trip.trip_date;
            document.getElementById('editTripNotes').value = data.trip.notes;

            const completedToggle = document.getElementById('editTripCompleted');
            if (completedToggle) {
                completedToggle.checked = data.trip.is_completed;
            }
            
            // FIXED: Store complete trip data including items for preservation
            window.currentTripData = {
                is_completed: data.trip.is_completed,
                trip_items: data.trip_items || [] // Include trip items data
            };

            new bootstrap.Modal(document.getElementById('editTripModal')).show();
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error loading trip data', 'danger');
    });
}

function saveTrip() {
    const tripId = document.getElementById('editTripId').value;
    const completedToggle = document.getElementById('editTripCompleted');
    
    const formData = {
        passenger_count: document.getElementById('editPassengerCount').value,
        trip_date: document.getElementById('editTripDate').value,
        notes: document.getElementById('editTripNotes').value
    };
    
    // Check if status is changing (only if toggle exists - admin/manager only)
    let statusChanged = false;
    let newStatus = null;
    
    if (completedToggle) {
        const currentStatus = window.currentTripData && window.currentTripData.is_completed;
        newStatus = completedToggle.checked;
        statusChanged = currentStatus !== newStatus;
        
        if (statusChanged) {
            // Status is changing - show confirmation
            const confirmMessage = newStatus 
                ? 'Mark this trip as completed? This will finalize all transactions and prevent further editing.'
                : 'Reopen this completed trip? This will allow editing of transactions and trip details.';
            
            showStatusChangeConfirmation(confirmMessage, formData, tripId, statusChanged, newStatus);
            return;
        }
    }
    
    // No status change - proceed with normal update
    performTripUpdate(tripId, formData, statusChanged, newStatus);
}

function showStatusChangeConfirmation(message, formData, tripId, statusChanged, newStatus) {
    document.getElementById('statusChangeMessage').textContent = message;
    
    const modal = new bootstrap.Modal(document.getElementById('statusChangeConfirmModal'));
    modal.show();
    
    document.getElementById('confirmStatusChange').onclick = function() {
        modal.hide();
        performTripUpdate(tripId, formData, statusChanged, newStatus);
    };
}

function performTripUpdate(tripId, formData, statusChanged, newStatus) {
    const saveButton = document.querySelector('#editTripModal .btn-primary');
    window.standardizeLoadingStates(saveButton, true);

    if (statusChanged) {
        // FIXED: Before toggling completed→incomplete, preserve cart data
        if (newStatus === false) { // Going from completed to incomplete
            preserveTripCartBeforeToggle(tripId);
        }
        
        // Use toggle endpoint for status changes (with transaction deletion)
        fetch(`/trips/${tripId}/toggle-status/`, {
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
                if (formData.passenger_count || formData.trip_date || formData.notes) {
                    updateTripFields(tripId, formData, saveButton, data.message);
                } else {
                    handleTripUpdateSuccess(saveButton, data.message);
                }
            } else {
                handleTripUpdateError(saveButton, data.error || 'Failed to update trip status');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            handleTripUpdateError(saveButton, 'Error updating trip status');
        });
    } else {
        // Use edit endpoint for normal field updates (no status change)
        updateTripFields(tripId, formData, saveButton, null);
    }
}

function preserveTripCartBeforeToggle(tripId) {
    try {
        const currentTripData = window.currentTripData;
        
        if (currentTripData && currentTripData.trip_items) {
            const preserveKey = `trip_toggle_preserve_${tripId}`;
            const cartData = currentTripData.trip_items.map(item => ({
                product_id: item.product_id,
                product_name: item.product_name,
                product_item_id: item.product_item_id,
                product_barcode: item.product_barcode || '',
                is_duty_free: item.is_duty_free,
                quantity: item.quantity,
                unit_price: item.unit_price,
                total_amount: item.total_amount,
                notes: item.notes || ''
            }));
            
            localStorage.setItem(preserveKey, JSON.stringify({
                items: cartData,
                timestamp: Date.now(),
                preserved_from: 'toggle_operation'
            }));
            
            console.log(`🔄 TRIP TOGGLE PRESERVE: Saved ${cartData.length} items for trip ${tripId}`);
        }
    } catch (error) {
        console.error('Error preserving trip cart data before toggle:', error);
    }
}

function updateTripFields(tripId, formData, saveButton, previousMessage) {
    fetch(`/trips/${tripId}/edit/`, {
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
                ? `${previousMessage} Trip details updated successfully.`
                : data.message;
            handleTripUpdateSuccess(saveButton, finalMessage);
        } else {
            handleTripUpdateError(saveButton, data.error || 'Failed to update trip');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        handleTripUpdateError(saveButton, 'Error updating trip');
    });
}

function handleTripUpdateSuccess(saveButton, message) {
    window.standardizeLoadingStates(saveButton, false);
    window.showAlert(message, 'success');
    bootstrap.Modal.getInstance(document.getElementById('editTripModal')).hide();
    setTimeout(() => location.reload(), 1000);
}

function handleTripUpdateError(saveButton, errorMessage) {
    window.standardizeLoadingStates(saveButton, false);
    window.showAlert(errorMessage, 'danger');
}

function executeTripSave(formData, tripId) {
    fetch(`/trips/${tripId}/edit/`, {
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
            bootstrap.Modal.getInstance(document.getElementById('editTripModal')).hide();
            setTimeout(() => location.reload(), 1000);
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error saving trip', 'danger');
    });
}

function deleteTrip(tripId) {
    fetch(`/trips/${tripId}/delete/`, {
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
            showTransactionConfirmationModal('trip', tripId, data);
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error deleting trip', 'danger');
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
                        <button type="button" class="btn btn-danger" onclick="confirmForceDelete('${type}', ${id})">
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

function confirmForceDelete(type, id) {
    // Immediately blur the button that triggered this
    if (document.activeElement && document.activeElement.tagName === 'BUTTON') {
        document.activeElement.blur();
    }
    
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

function handleDeletionError(data) {
    // Check if it's an inventory consumption error with suggested actions
    if ((data.error_type === 'inventory_consumption_blocked' || 
         data.error_type === 'inventory_conflict') && 
        data.suggested_actions) {
        showInventoryBlockedModal(data);
    } else {
        // Standard error display - handle both error and error_message
        const errorMsg = data.error || data.error_message || data.message || 'An error occurred';
        window.showAlert(errorMsg, 'danger');
    }
}