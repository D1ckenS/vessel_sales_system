/**
 * Extract raw user notes by removing system-generated waste report details
 * @param {string} notes - Full notes from database  
 * @returns {string} - Raw user notes without system formatting
 */
function extractUserNotesFromWaste(notes) {
    if (!notes || notes.trim() === '') {
        return '';
    }
    
    // Pattern: "Waste Report: {report_number}. Reason: {damage_reason}. {user_notes}"
    const wasteReportPattern = /^Waste Report: [^.]+\. Reason: [^.]+\.\s*/;
    
    if (wasteReportPattern.test(notes)) {
        // Remove the system prefix and return user notes
        return notes.replace(wasteReportPattern, '').trim();
    }
    
    // If no system formatting found, return as-is (raw user notes)
    return notes.trim();
}

/**
 * Extract system waste report details
 * @param {string} notes - Full notes from database
 * @returns {object|null} - {report_number, damage_reason} or null
 */
function extractWasteSystemDetails(notes) {
    if (!notes || !notes.includes('Waste Report:')) {
        return null;
    }
    
    const match = notes.match(/^Waste Report: ([^.]+)\. Reason: ([^.]+)\./);
    if (match) {
        return {
            report_number: match[1],
            damage_reason: match[2]
        };
    }
    
    return null;
}

/**
 * Check if notes are already system-formatted
 * @param {string} notes - Notes to check
 * @returns {boolean} - True if already formatted
 */
function isWasteNoteFormatted(notes) {
    if (!notes) return false;
    return notes.startsWith('Waste Report:') && notes.includes('Reason:');
}

/**
 * Format raw user notes with waste report details (use only once during transaction creation)
 * @param {string} reportNumber - Waste report number
 * @param {string} damageReason - Damage reason code
 * @param {string} userNotes - Raw user notes
 * @returns {string} - Formatted notes for database storage
 */
function formatWasteNotes(reportNumber, damageReason, userNotes = '') {
    let formattedNotes = `Waste Report: ${reportNumber}. Reason: ${damageReason}.`;
    
    if (userNotes && userNotes.trim()) {
        formattedNotes += ` ${userNotes.trim()}`;
    }
    
    return formattedNotes;
}