// Norwegian UI text carries no em or en dashes; the owner's rule, and the copy
// pass removed them all. ui_i18n.json is guarded by tests/test_norwegian_copy.py.
// This covers the strings the scripts build themselves: a separator between two
// parts is " · ", a range takes a hyphen. Exempt are the English fallback (the
// second argument of t()), and a dash standing alone as a "no value" mark.
const fs = require('node:fs');
const acorn = require('acorn');

const DIR = 'app/web/static/';
const DASH = /[—–]/;
// A lone dash, possibly inside a span, is a placeholder, not prose.
const PLACEHOLDER = /^\s*(<span[^>]*>)?[—–](<\/span>)?\s*$/;

function main() {
  const problems = [];
  for (const file of fs.readdirSync(DIR).filter(f => f.endsWith('.js') && !f.includes('.min.') && f !== 'sw.js')) {
    const src = fs.readFileSync(DIR + file, 'utf8');
    const ast = acorn.parse(src, {ecmaVersion: 'latest', locations: true});
    const fallbacks = new Set();
    const visit = (node, fn) => {
      if (!node || typeof node.type !== 'string') return;
      fn(node);
      for (const key in node) {
        const value = node[key];
        if (Array.isArray(value)) value.forEach(child => visit(child, fn));
        else if (value && typeof value.type === 'string') visit(value, fn);
      }
    };
    visit(ast, node => {
      if (node.type === 'CallExpression' && node.callee.type === 'Identifier'
          && node.callee.name === 't' && node.arguments[1]) fallbacks.add(node.arguments[1]);
    });
    visit(ast, node => {
      let text = null;
      if (node.type === 'Literal' && typeof node.value === 'string' && !fallbacks.has(node)) text = node.value;
      if (node.type === 'TemplateElement') text = node.value.cooked || '';
      if (text && DASH.test(text) && !PLACEHOLDER.test(text)) {
        problems.push(`${file}:${node.loc.start.line} ${JSON.stringify(text.slice(0, 60))}`);
      }
    });
  }
  if (problems.length) {
    console.error('Em or en dash in text the scripts build (use " · " or a hyphen):');
    problems.forEach(p => console.error('  ' + p));
    process.exit(1);
  }
  console.log('No dashes in script-built UI text');
}

module.exports = { main };
if (require.main === module) main();
