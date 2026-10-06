// ═══════════════════════════════════════════════════════════════════
// ESCAPING: esc() for every value interpolated into markup
// ═══════════════════════════════════════════════════════════════════

// scripts/check-html-escaping.cjs enforces it: a value in an HTML string is
// esc()'d, numeric, a literal translation, or markup checked where it is built.
export function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Quote a CSV field and keep imported text from becoming an Excel formula.
// Numbers remain numbers, including negative quantities.
export function csvCell(value) {
  var text = value == null ? '' : String(value);
  if (typeof value === 'string' && (/^[\t\r\n]/.test(text) || /^[=+@-]/.test(text.trimStart()))) text = "'" + text;
  return '"' + text.replace(/"/g, '""') + '"';
}
