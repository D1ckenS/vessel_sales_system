// Transfer Reports JavaScript - EXACT COPY from template (NO MODIFICATIONS)

document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'transfer_reports',
        fallbackTitle: 'Transfer Reports',
        pageTranslations: pageTranslations
    });
    
    // Z-INDEX FIX: Handle dropdown show/hide events
    function setupDropdownZIndexFix(dropdownId) {
        const dropdown = document.getElementById(dropdownId);
        const filterCard = dropdown?.closest('.card');

        if (dropdown && filterCard) {
            dropdown.addEventListener('show.bs.dropdown', function () {
                filterCard.classList.add('filter-active');
            });
            
            dropdown.addEventListener('hide.bs.dropdown', function () {
                filterCard.classList.remove('filter-active');
            });
        }
    }
    
    // Apply z-index fix to dropdowns
    setupDropdownZIndexFix('vesselFilterDropdown');
    
    // Update page translations
    updatePageTranslations();
});

// Vessel filter dropdown selection handler
function selectVesselFilter(vesselId, element) {
    // Update hidden input
    document.getElementById('vesselFilterInput').value = vesselId;
    
    // Update button text
    const buttonText = document.getElementById('selectedVesselFilterText');
    buttonText.innerHTML = element.innerHTML;
    
    // Update active state
    document.querySelectorAll('#vesselFilterDropdown + .dropdown-menu .dropdown-item').forEach(item => {
        item.classList.remove('active');
    });
    element.classList.add('active');
    
    // Close dropdown
    const dropdown = bootstrap.Dropdown.getInstance(document.getElementById('vesselFilterDropdown'));
    if (dropdown) {
        dropdown.hide();
    }
    
    // Prevent default link behavior
    event.preventDefault();
    return false;
}

function toggleColumn(columnClass) {
    const columns = document.querySelectorAll(`.${columnClass}-column`);
    const isVisible = columns[0].style.display !== 'none';
    
    columns.forEach(col => {
        col.style.display = isVisible ? 'none' : '';
    });
}
