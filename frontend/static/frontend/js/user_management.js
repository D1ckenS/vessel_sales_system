// User Management JavaScript - EXACT COPY from template (NO MODIFICATIONS)

document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'user_management',
        fallbackTitle: 'User Management',
    })    
    // Update page translations
    updatePageTranslations();
});

function setupGroups() {
    confirmTranslated('Are you sure you want to set up default user groups?\n\nThis will create: Administrators, Managers, Vessel Operators, Inventory Staff, and Viewers.').then(confirmed => {
        if (confirmed) {
            console.log('User confirmed, making fetch request');
            
            // Show loading state (optional - add loading button effect)
            const button = event.target;
            const originalText = button.innerHTML;
            button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Setting up...';
            button.disabled = true;
            
            fetch('{% url "frontend:setup_groups" %}', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': window.getCsrfToken(),
                    'Content-Type': 'application/json',
                },
            })
            .then(response => {
                console.log('Response received:', response.status);
                
                // Reset button state
                button.innerHTML = originalText;
                button.disabled = false;
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Data received:', data);
                
                if (data.success) {
                    // Check what actually happened and show appropriate message
                    let message = '';
                    
                    if (data.created_groups.length > 0 && data.existing_groups.length > 0) {
                        // Some created, some already existed
                        message = `Groups setup complete!\n\n✅ Created: ${data.created_groups.join(', ')}\n\nℹ️ Already existed: ${data.existing_groups.join(', ')}`;
                    } else if (data.created_groups.length > 0) {
                        // All groups were newly created
                        message = `All user groups created successfully!\n\n✅ Created: ${data.created_groups.join(', ')}`;
                    } else if (data.existing_groups.length > 0) {
                        // All groups already existed
                        message = `All user groups already exist!\n\nℹ️ Existing groups: ${data.existing_groups.join(', ')}\n\nNo changes were made.`;
                    } else {
                        // Fallback
                        message = 'Groups setup completed successfully!';
                    }
                    
                    alertTranslated(message).then(() => {
                        location.reload();
                    });
                } else {
                    alertTranslated('Error: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Setup groups error:', error);
                
                // Reset button state
                button.innerHTML = originalText;
                button.disabled = false;
                
                alertTranslated('Error setting up groups: ' + error.message);
            });
        } else {
            console.log('User cancelled setup');
        }
    });
}

function editUser(userId, username, firstName, lastName, email, isActive, isStaff, userGroups) {
    document.getElementById('editUserId').value = userId;
    document.getElementById('editUsername').value = username;
    document.getElementById('editFirstName').value = firstName;
    document.getElementById('editLastName').value = lastName;
    document.getElementById('editEmail').value = email;
    document.getElementById('editIsActive').checked = isActive;
    document.getElementById('editIsStaff').checked = isStaff;
    
    document.getElementById('editUserForm').action = `/users/${userId}/edit/`;
    
    new bootstrap.Modal(document.getElementById('editUserModal')).show();
}

function manageUserGroups(userId, username, userGroups) {
    document.getElementById('manageGroupsUserId').value = userId;
    document.getElementById('manageGroupsUsername').textContent = username;
    
    // Clear all checkboxes
    document.querySelectorAll('#manageGroupsForm input[name="groups"]').forEach(checkbox => {
        checkbox.checked = false;
    });
    
    // Check boxes for user's current groups
    userGroups.forEach(groupId => {
        const checkbox = document.querySelector(`#manageGroupsForm input[name="groups"][value="${groupId}"]`);
        if (checkbox) {
            checkbox.checked = true;
        }
    });
    
    document.getElementById('manageGroupsForm').action = `/users/${userId}/groups/`;
    
    new bootstrap.Modal(document.getElementById('manageGroupsModal')).show();
}

function resetPassword(userId, username) {
    confirmTranslated('confirm_reset_password', { username: username }).then(confirmed => {
        if (confirmed) {
            fetch(`/users/${userId}/reset-password/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': window.getCsrfToken(),
                    'Content-Type': 'application/json',
                },
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert(`Password reset successful!\nNew password: ${data.new_password}`);
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error resetting password');
            });
        }
    });
}

function toggleUserStatus(userId, username, isActive) {
    const action = isActive ? 'deactivate' : 'activate';
    const confirmKey = isActive ? 'confirm_deactivate_user' : 'confirm_activate_user';
    
    confirmTranslated(confirmKey, { username: username }).then(confirmed => {
        if (confirmed) {
            fetch(`/users/${userId}/toggle-status/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': window.getCsrfToken(),
                    'Content-Type': 'application/json',
                },
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error updating user status');
            });
        }
    });
}
