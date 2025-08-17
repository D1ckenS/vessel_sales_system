// Vessel Management JavaScript - EXACT COPY from template (NO MODIFICATIONS)

document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'vessel_management',
        fallbackTitle: 'Vessel Management',
    })

    // Apply translations
    window.updatePageTranslations();
    
    // Date picker functionality - OPTIMIZED
    const datePicker = document.getElementById('referenceDatePicker');
    const dateRangeDisplay = document.getElementById('dateRangeDisplay');
    const loadingOverlay = document.getElementById('loadingOverlay');
    
    datePicker?.addEventListener('change', function() {
        const selectedDate = this.value;
        if (selectedDate) updateVesselData(selectedDate);
    });
    
    // OPTIMIZED: Single AJAX update function
    async function updateVesselData(selectedDate) {
        loadingOverlay?.classList.remove('d-none');
        
        const refDate = new Date(selectedDate);
        const thirtyDaysAgo = new Date(refDate.getTime() - (30 * 24 * 60 * 60 * 1000));
        
        if (dateRangeDisplay) {
            const formatDate = date => date.toLocaleDateString('en-GB');
            dateRangeDisplay.textContent = `${formatDate(thirtyDaysAgo)} - ${formatDate(refDate)}`;
        }
        
        try {
            const response = await fetch('{% url "frontend:vessel_data_ajax" %}', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.getCsrfToken(),
                },
                body: JSON.stringify({ date: selectedDate })
            });
            
            const data = await response.json();
            
            if (data.success) {
                updateVesselCards(data.vessel_data);
                window.updatePageTranslations();
                updateVesselSpecificTranslations();
            } else {
                await alertTranslated('error_updating_vessel_data');
            }
        } catch (error) {
            await alertTranslated('error_updating_vessel_data');
        } finally {
            loadingOverlay?.classList.add('d-none');
        }
    }
    
    // OPTIMIZED: Update vessel cards function
    function updateVesselCards(vesselData) {
        vesselData.forEach(vessel => {
            const vesselCard = document.querySelector(`[data-vessel-id="${vessel.vessel_id}"]`);
            if (vesselCard) {
                // Update 30-day trips
                const totalTripsEl = vesselCard.querySelector('.vessel-total-trips');
                if (totalTripsEl) {
                    totalTripsEl.setAttribute('data-original', vessel.trips_30d);
                    totalTripsEl.textContent = window.translateNumber ? 
                        window.translateNumber(vessel.trips_30d) : vessel.trips_30d;
                }
                
                // Update revenue
                const revenueEl = vesselCard.querySelector('.vessel-revenue-30d');
                if (revenueEl) {
                    const formattedRevenue = Math.round(vessel.revenue_30d);
                    revenueEl.setAttribute('data-original', formattedRevenue);
                    revenueEl.textContent = window.translateNumber ? 
                        window.translateNumber(formattedRevenue) : formattedRevenue;
                }
            }
        });
    }
    
    // Modal functions
    window.editVessel = function(vesselId, name, nameAr, hasDutyFree, active) {
        document.getElementById('editVesselId').value = vesselId;
        document.getElementById('editName').value = name;
        document.getElementById('editNameAr').value = nameAr || '';
        document.getElementById('editHasDutyFree').checked = hasDutyFree;
        document.getElementById('editActive').checked = active;
        
        document.getElementById('editVesselForm').action = 
            `{% url 'frontend:edit_vessel' 0 %}`.replace('0', vesselId);
        
        new bootstrap.Modal(document.getElementById('editVesselModal')).show();
        // OPTIMIZED: Single timeout for translations
        setTimeout(() => {
            window.updatePageTranslations();
            updateVesselSpecificTranslations();
        }, 100);
    };

    // OPTIMIZED: Simplified loading message system
    function showLoadingMessage(translationKey) {
        if (window.translator && window.translator._) {
            const message = window.translator._(translationKey);
            const loadingToast = document.createElement('div');
            loadingToast.id = 'loadingToast';
            loadingToast.className = 'toast align-items-center text-white bg-primary border-0 position-fixed top-0 end-0 m-3';
            loadingToast.style.zIndex = '9999';
            loadingToast.innerHTML = `
                <div class="d-flex">
                    <div class="toast-body">
                        <span class="spinner-border spinner-border-sm me-2"></span>
                        ${message}
                    </div>
                </div>
            `;
            document.body.appendChild(loadingToast);
            
            const toast = new bootstrap.Toast(loadingToast);
            toast.show();
        }
    }

    function hideLoadingMessage() {
        const loadingToast = document.getElementById('loadingToast');
        if (loadingToast) {
            const toast = bootstrap.Toast.getInstance(loadingToast);
            if (toast) {
                toast.hide();
            }
            setTimeout(() => {
                if (loadingToast.parentNode) {
                    loadingToast.parentNode.removeChild(loadingToast);
                }
            }, 500);
        }
    }

    // OPTIMIZED: Toggle vessel status function
    window.toggleVesselStatus = async function(vesselId, vesselName, isActive) {
        const action = isActive ? 'deactivate' : 'activate';
        const confirmKey = isActive ? 'confirm_deactivate_vessel' : 'confirm_activate_vessel';
        
        const confirmed = await confirmTranslated(confirmKey, { vessel_name: vesselName });
        if (!confirmed) return;
        
        showLoadingMessage('updating_vessel_status');
        
        try {
            const response = await fetch(`{% url 'frontend:toggle_vessel_status' 0 %}`.replace('0', vesselId), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.getCsrfToken(),
                },
            });
            
            const data = await response.json();
            
            hideLoadingMessage();
            
            if (data.success) {
                const successKey = isActive ? 'vessel_deactivated_success' : 'vessel_activated_success';
                await alertTranslated(successKey, { vessel_name: vesselName });
                
                // OPTIMIZED: Single reload with delay
                setTimeout(() => location.reload(), 500);
            } else {
                await alertTranslated('error_updating_vessel_status');
            }
        } catch (error) {
            hideLoadingMessage();
            await alertTranslated('error_processing_request');
        }
    };
    
    // OPTIMIZED: View vessel stats function
    window.viewVesselStats = function(vesselId, vesselName) {
        window.currentStatsVesselId = vesselId;
        document.getElementById('statsVesselName').textContent = vesselName;
        
        fetch(`{% url 'frontend:vessel_statistics' 0 %}`.replace('0', vesselId))
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Update statistics display
                    const statsTotalTrips = document.getElementById('statsTotalTrips');
                    if (statsTotalTrips) {
                        statsTotalTrips.setAttribute('data-original', data.statistics.total_trips);
                        statsTotalTrips.textContent = window.translateNumber ? 
                            window.translateNumber(data.statistics.total_trips) : data.statistics.total_trips;
                    }
                    
                    document.getElementById('statsTotalRevenue').textContent = 
                        data.statistics.total_revenue.toFixed(2) + ' JOD';
                    
                    const statsTotalPassengers = document.getElementById('statsTotalPassengers');
                    if (statsTotalPassengers) {
                        statsTotalPassengers.setAttribute('data-original', data.statistics.total_passengers);
                        statsTotalPassengers.textContent = window.translateNumber ? 
                            window.translateNumber(data.statistics.total_passengers) : data.statistics.total_passengers;
                    }
                    
                    document.getElementById('statsAvgRevenue').textContent = 
                        data.statistics.avg_revenue_per_passenger.toFixed(2) + ' JOD';
                    
                    // Update top products
                    const topProductsList = document.getElementById('topProductsList');
                    if (data.top_products.length > 0) {
                        topProductsList.innerHTML = data.top_products.map(product => `
                            <div class="d-flex justify-content-between align-items-center py-2 border-bottom">
                                <span>${product.product__name}</span>
                                <span class="badge bg-primary">${window.translateNumber ? 
                                    window.translateNumber(product.total_quantity) : product.total_quantity} 
                                    <span data-translate="units">units</span>
                                </span>
                            </div>
                        `).join('');
                        
                        // OPTIMIZED: Single translation update
                        setTimeout(() => {
                            window.updatePageTranslations();
                            updateVesselSpecificTranslations();
                        }, 0);
                    } else {
                        topProductsList.innerHTML = '<p class="text-muted">No product data available</p>';
                    }
                }
            })
            .catch(error => {
                // Silent error handling - no console logs
                topProductsList.innerHTML = '<p class="text-muted">Error loading data</p>';
            });
        
        new bootstrap.Modal(document.getElementById('vesselStatsModal')).show();
        
        // OPTIMIZED: Single translation update
        setTimeout(() => {
            window.updatePageTranslations();
            updateVesselSpecificTranslations();
        }, 100);
    };
    
    window.exportVesselStats = function() {
        if (window.currentStatsVesselId) {
            window.open(`{% url 'frontend:vessel_statistics' 0 %}`.replace('0', window.currentStatsVesselId) + '?export=1');
        }
    };
    
    // Form handlers - OPTIMIZED
    document.getElementById('createVesselForm')?.addEventListener('submit', handleFormSubmit);
    document.getElementById('editVesselForm')?.addEventListener('submit', handleFormSubmit);
    
    async function handleFormSubmit(e) {
        e.preventDefault();
        const formData = new FormData(this);
        const isCreateForm = this.id === 'createVesselForm';
        const vesselName = formData.get('name');
        
        const loadingKey = isCreateForm ? 'creating_vessel' : 'updating_vessel';
        showLoadingMessage(loadingKey);
        
        try {
            const response = await fetch(this.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': window.getCsrfToken(),
                },
            });
            
            const data = await response.json();
            
            hideLoadingMessage();
            
            if (data.success) {
                const modal = bootstrap.Modal.getInstance(this.closest('.modal'));
                modal?.hide();
                
                const successKey = isCreateForm ? 'vessel_created_success' : 'vessel_updated_success';
                await alertTranslated(successKey, { vessel_name: vesselName });
                
                // OPTIMIZED: Single reload with delay
                setTimeout(() => location.reload(), 500);
            } else {
                const errorKey = isCreateForm ? 'error_creating_vessel' : 'error_updating_vessel';
                await alertTranslated(errorKey);
            }
        } catch (error) {
            hideLoadingMessage();
            await alertTranslated('error_processing_request');
        }
    }
    
    // OPTIMIZED: Language change listener
    window.addEventListener('languageChanged', function() {
        updateVesselSpecificTranslations();
    });
    
    // Initial call
    updateVesselSpecificTranslations();
});

// OPTIMIZED: Vessel-specific translations function
function updateVesselSpecificTranslations() {
    document.querySelectorAll('[data-translate="products_missing_pricing"]').forEach(element => {
        const countSpan = element.parentElement.querySelector('[data-number][data-original]');
        if (countSpan) {
            const count = countSpan.getAttribute('data-original') || countSpan.textContent.trim();
            const translatedCount = window.translateNumber ? window.translateNumber(count) : count;
            
            if (window.translator && window.translator._) {
                element.textContent = window.translator._('products_missing_pricing', { count: translatedCount });
            }
        }
    });
}
