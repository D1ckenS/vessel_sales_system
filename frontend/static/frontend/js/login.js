// Login Page JavaScript
// Translation System (simplified version matching base.html)
let currentLanguage = localStorage.getItem('preferred_language') || 'en';

function updateLanguageDisplay() {
    // Update all translatable elements
    const elements = document.querySelectorAll('[data-translate]');
    elements.forEach(element => {
        const key = element.getAttribute('data-translate');
        const text = VesselSalesTranslations[currentLanguage][key];
        if (text) {
            element.textContent = text;
        }
    });
    
    // Update document direction and language
    document.documentElement.setAttribute('dir', currentLanguage === 'ar' ? 'rtl' : 'ltr');
    document.documentElement.setAttribute('lang', currentLanguage);
    
    // Update body class for RTL
    if (currentLanguage === 'ar') {
        document.body.classList.add('rtl');
    } else {
        document.body.classList.remove('rtl');
    }
}

function toggleLanguage() {
    currentLanguage = currentLanguage === 'en' ? 'ar' : 'en';
    localStorage.setItem('preferred_language', currentLanguage);
    updateLanguageDisplay();
}

// Initialize language on page load
document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'login',
        fallbackTitle: 'Login'
    });

    updateLanguageDisplay();
    
    // Focus on username field
    document.getElementById('username').focus();
    
    // Form submission with loading state
    const form = document.getElementById('loginForm');
    const submitBtn = form.querySelector('button[type="submit"]');
    
    form.addEventListener('submit', function(e) {
        const loadingText = VesselSalesTranslations[currentLanguage]['signing_in'];
        submitBtn.innerHTML = '<span class="loading me-2"></span>' + loadingText;
        submitBtn.disabled = true;
    });
});

// Handle Enter key
document.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        document.getElementById('loginForm').submit();
    }
});