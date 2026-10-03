// ═══════════════════════════════════════════════════════════════════
// ESCAPING: esc() for every value interpolated into markup
// ═══════════════════════════════════════════════════════════════════

// scripts/check-html-escaping.cjs enforces it: a value in an HTML string is
// esc()'d, numeric, a literal translation, or markup checked where it is built.
function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
