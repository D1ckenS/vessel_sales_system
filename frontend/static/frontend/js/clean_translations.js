const fs = require('fs');
const path = 'frontend/static/frontend/js/translations.js'; // adjust if needed

// Load the file content
let code = fs.readFileSync(path, 'utf-8');

// Extract the JSON object from within the JS wrapper
const match = code.match(/window\.VesselSalesTranslations\s*=\s*({[\s\S]*?});\s*$/);
if (!match) {
  console.error('Could not find the translation object inside translations.js');
  process.exit(1);
}

const translationsObject = eval('(' + match[1] + ')'); // parse safely

const dedupeAndSort = obj => {
  const deduped = {};
  const seen = new Set();
  for (const [key, val] of Object.entries(obj)) {
    const hash = `${key}|||${val}`; // Only remove duplicates with same value
    if (!seen.has(hash)) {
      seen.add(hash);
      deduped[key] = val;
    }
  }

  // Return sorted object
  return Object.fromEntries(Object.entries(deduped).sort(([a], [b]) => a.localeCompare(b)));
};

const cleaned = {
  en: dedupeAndSort(translationsObject.en),
  ar: dedupeAndSort(translationsObject.ar)
};

// Re-wrap the object in JS format
const finalOutput =
  'window.VesselSalesTranslations = ' + JSON.stringify(cleaned, null, 2) + ';\n';

fs.writeFileSync('translations.cleaned.js', finalOutput, 'utf-8');
console.log('✅ Cleaned file written to translations.cleaned.js');