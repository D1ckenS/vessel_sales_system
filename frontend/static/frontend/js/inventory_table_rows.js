// Inventory Table Rows JavaScript - EXACT COPY from template (NO MODIFICATIONS)

// Adjust colspan for empty row based on vessel column visibility
document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        customInit: () => {
            const vesselColumn = document.getElementById('vesselColumn');
            const emptyRow = document.querySelector('.vessel-aware-colspan');
            if (emptyRow) {
                emptyRow.colSpan = vesselColumn && vesselColumn.style.display === 'none' ? 6 : 7;
            }
        }
    });
});

