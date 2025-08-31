( function () {
document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'category_management',
        fallbackTitle: 'Category Management',
        pageTranslations: pageTranslations
    })
    
    // Update page translations
    updatePageTranslations();
});

// REFACTORED with ModalManager for standardized modal handling
function showCreateCategoryModal() {
    window.ModalManager.showCrudModal({
        modalId: 'categoryModal',
        formId: 'categoryForm',
        titleKey: 'add_new_category',
        titleFallback: 'Add New Category',
        action: '{% url "frontend:create_category" %}',
        data: {
            categoryId: '',
            categoryName: '',
            categoryDescription: '',
            categoryActive: true,
            icon: 'bi bi-collection'
        }
    });
    
    // Update submit button text
    const submitBtn = document.getElementById('submitBtn');
    if (submitBtn) {
        submitBtn.innerHTML = '<i class="bi bi-check-circle"></i> <span data-translate="save_category">Save Category</span>';
    }
}

// REFACTORED with ModalManager for standardized modal handling
function editCategory(id, name, description, active) {
    window.ModalManager.showCrudModal({
        modalId: 'categoryModal',
        formId: 'categoryForm',
        titleKey: 'edit_category_title',
        titleFallback: 'Edit Category',
        action: `/categories/manage/${id}/edit/`,
        data: {
            categoryId: id,
            categoryName: name,
            categoryDescription: description,
            categoryActive: active,
            icon: 'bi bi-pencil'
        }
    });
    
    // Update submit button text
    const submitBtn = document.getElementById('submitBtn');
    if (submitBtn) {
        submitBtn.innerHTML = '<i class="bi bi-check-circle"></i> <span data-translate="save_category">Save Category</span>';
    }
}

// REFACTORED with ModalManager for standardized confirmation handling
async function deleteCategory(id, name) {
    const confirmed = await window.ModalManager.showConfirmation({
        titleKey: 'confirm_delete',
        messageKey: 'confirm_delete_category',
        messageParams: { name: name },
        confirmButtonKey: 'delete',
        cancelButtonKey: 'cancel'
    });

    if (confirmed) {
        // Create form and submit with standardized approach
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/categories/${id}/delete/`;
        
        const csrfToken = window.getCsrfToken();
        const csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrfmiddlewaretoken';
        csrfInput.value = csrfToken;
        form.appendChild(csrfInput);
        
        document.body.appendChild(form);
        form.submit();
    }
}

window.showCreateCategoryModal = showCreateCategoryModal;
window.editCategory = editCategory;
window.deleteCategory = deleteCategory;
})();