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

function showCreateCategoryModal() {
    // Reset form for create mode
    document.getElementById('categoryForm').action = '{% url "frontend:create_category" %}';
    document.getElementById('categoryId').value = '';
    document.getElementById('categoryName').value = '';
    document.getElementById('categoryDescription').value = '';
    document.getElementById('categoryActive').checked = true;
    
    // Update modal title
    document.getElementById('modalTitle').innerHTML = '<i class="bi bi-collection"></i> <span data-translate="add_new_category">Add New Category</span>';
    document.getElementById('submitBtn').innerHTML = '<i class="bi bi-check-circle"></i> <span data-translate="save_category">Save Category</span>';
    
    // Apply translations to modal content
    updatePageTranslations();
    
    // Show modal
    new bootstrap.Modal(document.getElementById('categoryModal')).show();
}

function editCategory(id, name, description, active) {
    // Set form for edit mode
    document.getElementById('categoryForm').action = `/categories/manage/${id}/edit/`;
    document.getElementById('categoryId').value = id;
    document.getElementById('categoryName').value = name;
    document.getElementById('categoryDescription').value = description;
    document.getElementById('categoryActive').checked = active;
    
    // Update modal title
    document.getElementById('modalTitle').innerHTML = '<i class="bi bi-pencil"></i> <span data-translate="edit_category_title">Edit Category</span>';
    document.getElementById('submitBtn').innerHTML = '<i class="bi bi-check-circle"></i> <span data-translate="save_category">Save Category</span>';
    
    // Apply translations to modal content
    updatePageTranslations();
    
    // Show modal
    new bootstrap.Modal(document.getElementById('categoryModal')).show();
}

function deleteCategory(id, name) {
    confirmTranslated('confirm_delete_category', { name: name }).then(confirmed => {
        if (confirmed) {
            // Create form and submit
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
    });
}

window.showCreateCategoryModal = showCreateCategoryModal;
window.editCategory = editCategory;
window.deleteCategory = deleteCategory;
})();