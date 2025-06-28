(function () {
function updateClock() {
    const now = new Date();
    const currentLang = window.translator ? window.translator.currentLanguage : 'en';

    const options = {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false
    };

    const timeString = now.toLocaleTimeString(currentLang === "ar" ? "ar-SA" : "en-GB", options);
    
    // Apply number translation if Arabic
    const translatedTime = currentLang === 'ar' ? 
        window.translateNumber(timeString) : timeString;
    
    const clockElement = document.getElementById("liveClock");
    if (clockElement) {
        clockElement.textContent = translatedTime;
    }
}

// Run once on page load
document.addEventListener("DOMContentLoaded", updateClock);

// Keep it updating every minute
setInterval(updateClock, 60000);

// Update clock every second
setInterval(updateClock, 1000);
updateClock(); // Initial call

// Auto-refresh stats every 5 minutes
setTimeout(function() {
    window.location.reload();
}, 300000);

// Add permission-specific translations
document.addEventListener('DOMContentLoaded', function() {
    window.initializePage({
        titleKey: 'dashboard',
        fallbackTitle: 'Dashboard'
    });
});
})();