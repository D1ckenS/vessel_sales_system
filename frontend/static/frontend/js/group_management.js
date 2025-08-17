// Group Management JavaScript - EXACT COPY from template (NO MODIFICATIONS)

document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'group_management',
        fallbackTitle: 'Group Management',
    })
    
    // Update page translations
    updatePageTranslations();
    
    // Form handlers
    document.getElementById('createGroupForm').addEventListener('submit', function(e) {
        e.preventDefault();
        createGroup();
    });
    
    document.getElementById('editGroupForm').addEventListener('submit', function(e) {
        e.preventDefault();
        saveGroup();
    });
});

function createGroup() {
    const formData = new FormData(document.getElementById('createGroupForm'));
    const data = {
        name: formData.get('name'),
        description: formData.get('description')
    };
    
    fetch('/groups/create/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.getCsrfToken()
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('createGroupModal')).hide();
            window.showAlert(data.message, 'success');
            location.reload();
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error creating group', 'danger');
    });
}

function editGroup(groupId, groupName) {
    document.getElementById('editGroupId').value = groupId;
    document.getElementById('editGroupName').value = groupName;
    document.getElementById('editGroupForm').action = `/groups/${groupId}/edit/`;
    
    new bootstrap.Modal(document.getElementById('editGroupModal')).show();
}

function saveGroup() {
    const groupId = document.getElementById('editGroupId').value;
    const data = {
        name: document.getElementById('editGroupName').value
    };
    
    fetch(`/groups/${groupId}/edit/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.getCsrfToken()
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('editGroupModal')).hide();
            window.showAlert(data.message, 'success');
            location.reload();
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error updating group', 'danger');
    });
}

function deleteGroup(groupId, groupName) {
    // First attempt - check for users
    fetch(`/groups/${groupId}/delete/`, {
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
            confirmDeleteGroupWithUsers(groupId, groupName, data);
        } else {
            window.showAlert(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        window.showAlert('Error deleting group', 'danger');
    });
}

function confirmDeleteGroupWithUsers(groupId, groupName, data) {
    const usersList = data.users.map(u => `${u.username} (${u.is_active ? 'Active' : 'Inactive'})`).join('\n');
    const message = `Group "${groupName}" has ${data.user_count} users:\n\n${usersList}\n\nRemove all users and delete group?`;
    
    confirmTranslated(message).then(confirmed => {
        if (confirmed) {
            fetch(`/groups/${groupId}/delete/`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': window.getCsrfToken(),
                    'X-Force-Delete': 'true'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.showAlert(data.message, 'success');
                    location.reload();
                } else {
                    window.showAlert(data.error, 'danger');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                window.showAlert('Error deleting group', 'danger');
            });
        }
    });
}

function viewGroupDetails(groupId) {
    fetch(`/groups/${groupId}/details/`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const group = data.group;
                let usersTable = '';
                
                if (group.users.length > 0) {
                    usersTable = `
                        <div class="table-responsive">
                            <table class="table table-sm">
                                <thead class="table-light">
                                    <tr>
                                        <th>Username</th>
                                        <th>Full Name</th>
                                        <th>Status</th>
                                        <th>Last Login</th>
                                    </tr>
                                </thead>
                                <tbody>
                    `;
                    
                    group.users.forEach(user => {
                        const statusBadge = user.is_active ? 
                            '<span class="badge bg-success">Active</span>' : 
                            '<span class="badge bg-danger">Inactive</span>';
                        const staffBadge = user.is_staff ? 
                            ' <span class="badge bg-primary">Staff</span>' : '';
                        
                        usersTable += `
                            <tr>
                                <td><strong>${user.username}</strong></td>
                                <td>${user.full_name}</td>
                                <td>${statusBadge}${staffBadge}</td>
                                <td><small>${user.last_login}</small></td>
                            </tr>
                        `;
                    });
                    
                    usersTable += '</tbody></table></div>';
                } else {
                    usersTable = '<div class="alert alert-info">No users in this group</div>';
                }
                
                const content = `
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <h6><i class="bi bi-collection me-2"></i>Group: <strong>${group.name}</strong></h6>
                        </div>
                        <div class="col-md-6 text-end">
                            <span class="badge bg-primary">${group.user_count} users</span>
                        </div>
                    </div>
                    
                    <h6><i class="bi bi-people me-2"></i>Users in Group:</h6>
                    ${usersTable}
                `;
                
                document.getElementById('groupDetailsContent').innerHTML = content;
                new bootstrap.Modal(document.getElementById('groupDetailsModal')).show();
            } else {
                window.showAlert(data.error, 'danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            window.showAlert('Error loading group details', 'danger');
        });
}

function setupGroups() {
    // This function is already implemented in user_management.html
    // Copy the implementation from there
    confirmTranslated('Are you sure you want to set up default user groups?\n\nThis will create: Administrators, Managers, Vessel Operators, Inventory Staff, and Viewers.').then(confirmed => {
        if (confirmed) {
            fetch('/setup-groups/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': window.getCsrfToken(),
                    'Content-Type': 'application/json',
                },
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    let message = '';
                    if (data.created_groups.length > 0 && data.existing_groups.length > 0) {
                        message = `Groups setup complete!\n\n✅ Created: ${data.created_groups.join(', ')}\n\nℹ️ Already existed: ${data.existing_groups.join(', ')}`;
                    } else if (data.created_groups.length > 0) {
                        message = `All user groups created successfully!\n\n✅ Created: ${data.created_groups.join(', ')}`;
                    } else if (data.existing_groups.length > 0) {
                        message = `All user groups already exist!\n\nℹ️ Existing groups: ${data.existing_groups.join(', ')}\n\nNo changes were made.`;
                    } else {
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
                alertTranslated('Error setting up groups: ' + error.message);
            });
        }
    });
}
