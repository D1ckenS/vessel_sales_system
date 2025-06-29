/**
 * Extract user-visible notes by removing FIFO consumption details
 * @param {string} notes - Full notes from database
 * @returns {string} - User-friendly notes without FIFO details
 */
function displayUserNotes(notes) {
    if (!notes || notes.trim() === '') {
        return '';
    }
    
    // Split at FIFO marker and show only user portion
    const fifoIndex = notes.indexOf('. FIFO consumption:');
    if (fifoIndex > -1) {
        return notes.substring(0, fifoIndex);
    }
    
    // Check if notes start with FIFO (no user notes)
    if (notes.startsWith('FIFO consumption:')) {
        return ''; // No user notes, only system data
    }
    
    return notes; // No FIFO details found, return as-is
}

/**
 * Extract FIFO details for system use
 * @param {string} notes - Full notes from database
 * @returns {string|null} - FIFO consumption details or null
 */
function extractFifoDetails(notes) {
    if (!notes || !notes.includes('FIFO consumption:')) {
        return null;
    }
    
    const fifoIndex = notes.indexOf('FIFO consumption:');
    return notes.substring(fifoIndex);
}

/**
 * Update all notes displays on page load
 */
function updateNotesDisplays() {
    // Update all elements with data-notes attribute
    document.querySelectorAll('[data-notes]').forEach(element => {
        const fullNotes = element.getAttribute('data-notes');
        const userNotes = displayUserNotes(fullNotes);
        
        if (userNotes) {
            element.textContent = userNotes;
            element.style.display = '';
        } else {
            element.textContent = '-';
            element.style.color = '#6c757d'; // Muted color for empty state
        }
    });
}

// Auto-run on page load
document.addEventListener('DOMContentLoaded', updateNotesDisplays);