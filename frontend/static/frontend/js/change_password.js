// Change Password Page JavaScript
// Handles form validation, password strength checking, and page initialization

// Set up translations for this page
document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'change_password',
        fallbackTitle: 'Change Password',
    })
});

document.getElementById('changePasswordForm').addEventListener('submit', function(e) {
    const newPassword = document.getElementById('new_password').value;
    const confirmPassword = document.getElementById('confirm_password').value;
    
    // Check if passwords match
    if (newPassword !== confirmPassword) {
        e.preventDefault();
        alert('New passwords do not match!');
        return false;
    }
    
    // Check password length
    if (newPassword.length < 6) {
        e.preventDefault();
        alert('Password must be at least 6 characters long!');
        return false;
    }
    
    // Optional: Check password strength
    if (!isPasswordStrong(newPassword)) {
        const proceed = confirm('Your password could be stronger. It\'s recommended to include uppercase letters, numbers, and special characters. Continue anyway?');
        if (!proceed) {
            e.preventDefault();
            return false;
        }
    }
});

function isPasswordStrong(password) {
    // Basic password strength check
    const hasUpper = /[A-Z]/.test(password);
    const hasLower = /[a-z]/.test(password);
    const hasNumber = /\d/.test(password);
    const hasSpecial = /[!@#$%^&*(),.?":{}|<>]/.test(password);
    const isLongEnough = password.length >= 8;
    
    return hasUpper && hasLower && hasNumber && hasSpecial && isLongEnough;
}

// Real-time password strength indicator
document.getElementById('new_password').addEventListener('input', function() {
    const password = this.value;
    updateStrengthIndicator(calculatePasswordStrength(password));
});

function calculatePasswordStrength(password) {
    let score = 0;
    
    if (password.length >= 6) score++;
    if (password.length >= 8) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[a-z]/.test(password)) score++;
    if (/\d/.test(password)) score++;
    if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) score++;
    
    return score;
}

function updateStrengthIndicator(score) {
    const indicator = document.getElementById('password-strength');
    let strength, color, width, strengthText;
    
    if (score <= 2) {
        strength = 'password_strength_weak';
        color = 'danger';
        width = '33%';
    } else if (score <= 4) {
        strength = 'password_strength_medium';
        color = 'warning';
        width = '66%';
    } else {
        strength = 'password_strength_strong';
        color = 'success';
        width = '100%';
    }
    
    // Get translated strength text
    strengthText = window.translator ? window.translator._(strength) : strength;
    
    indicator.innerHTML = `
        <div class="progress" style="height: 8px;">
            <div class="progress-bar bg-${color}" role="progressbar" style="width: ${width};" aria-valuenow="${score}" aria-valuemin="0" aria-valuemax="6"></div>
        </div>
        <small class="text-${color}">Password strength: ${strengthText}</small>
    `;
}