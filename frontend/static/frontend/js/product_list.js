// Product List JavaScript - EXACT COPY from template (NO MODIFICATIONS)

document.addEventListener('DOMContentLoaded', () => {
    window.initializePage({
        titleKey: 'product_list',
        fallbackTitle: 'Product List'
    })
    // --- Product Deletion ---
    function deleteProduct(productId, productName) {
        confirmTranslated('confirm_delete_product', { name: productName }).then(confirmed => {
            if (confirmed) {
                const form = document.createElement('form');
                form.method = 'POST';
                form.action = `/products/manage/${productId}/delete/`;

                const csrfTokenField = document.getElementById('csrfTokenPlaceholder');
                if (!csrfTokenField) return; // Extra safeguard

                const csrfInput = document.createElement('input');
                csrfInput.type = 'hidden';
                csrfInput.name = 'csrfmiddlewaretoken';
                csrfInput.value = csrfTokenField.value;
                form.appendChild(csrfInput);

                document.body.appendChild(form);
                form.submit();
            }
        });
    }

    // Make deleteProduct globally accessible (for inline onclick or buttons)
    window.deleteProduct = deleteProduct;

    // --- Export placeholder ---
    function exportProducts() {
        alertTranslated('export_products');
    }
    window.exportProducts = exportProducts;

    // --- Bulk pricing modal stub ---
    function showBulkPricingModal() {
        alertTranslated('bulk_pricing_coming_soon');
    }
    window.showBulkPricingModal = showBulkPricingModal;

    // --- Page size change ---
    function changePageSize(newSize) {
        const url = new URL(window.location);
        url.searchParams.set('per_page', newSize);
        url.searchParams.set('page', '1');
        window.location.href = url.toString();
    }
    window.changePageSize = changePageSize;

    // --- Jump to page ---
    function jumpToPage() {
        const pageInput = document.getElementById('pageJumpInput');
        if (!pageInput) return; // Prevent null crash

        const pageNumber = parseInt(pageInput.value);
        const maxPage = parseInt(pageInput.getAttribute('max')) || 1;

        if (pageNumber >= 1 && pageNumber <= maxPage) {
            const url = new URL(window.location);
            url.searchParams.set('page', pageNumber);
            window.location.href = url.toString();
        } else {
            alert('Please enter a valid page number between 1 and ' + maxPage);
            const currentPage = parseInt(pageInput.getAttribute('value')) || 1;
            pageInput.value = currentPage;
        }
    }
    window.jumpToPage = jumpToPage;

    function handlePageJump(event) {
        if (event.key === 'Enter') {
            jumpToPage();
        }
    }

    // Attach Enter key listener to page jump input
    const pageJumpInput = document.getElementById('pageJumpInput');
    if (pageJumpInput) {
        pageJumpInput.addEventListener('keydown', handlePageJump);
    }
    // --- Extra UI Translations ---
    if (typeof VesselSalesTranslations !== 'undefined') {
        Object.assign(VesselSalesTranslations, {
            'showing': 'Showing',
            'of': 'of',
            'per_page': 'Per page',
            'go_to_page': 'Go to page',
            'go': 'Go',
            'department': 'Department',
            'all_departments': 'All Departments',
            'duty_free': 'Duty-Free',
            'unit_cost': 'Unit Cost'
        });
    }
});