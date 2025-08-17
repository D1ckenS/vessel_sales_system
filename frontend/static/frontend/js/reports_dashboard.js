// Reports Dashboard JavaScript - EXACT COPY from template (NO MODIFICATIONS)

document.addEventListener('DOMContentLoaded', function() {

    window.initializePage({
        titleKey: 'reports_dashboard',
        fallbackTitle: 'Reports Dashboard'
    })
    // Update time display
    const now = new Date();
    const timeString = now.toLocaleTimeString();
    document.getElementById('last-updated-time').textContent = timeString;
    
    // Initialize page with translations
    window.initializePage({
        titleKey: 'reports_dashboard',
        fallbackTitle: 'Reports Dashboard',
    });
});

const showComingSoon = (feature) => window.templateUtils.showComingSoonAlert(feature);
