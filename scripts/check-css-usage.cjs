// Classes in app.css that nothing puts on an element. A rule for a class no
// markup, script or server template uses never matches; it only costs the
// next reader the time to find that out. Two redesigns left a few hundred.
//
// A class counts as used when its name appears as a whole word in
// index.html, a script (ours and the vendored ones, which add their own
// classes: xterm, Chart.js), ui_i18n.json or the web layer's Python. That is
// generous on purpose: a word in a comment keeps a class alive, and nothing
// used is ever reported.
//
// Classes built at runtime are the hard part: 'grade-' + grade, `is-${tone}`,
// toneClass(c).replace('text-', 'is-'). Every literal that ends in a hyphen
// and is joined to something (a +, a ${, a replace) is a prefix, and a class
// that starts with one is treated as used. That covers the families the
// scripts build; a new way of building class names needs a new pattern here.
//
//   node scripts/check-css-usage.cjs           report, exit 1 if any class is unused
//   node scripts/check-css-usage.cjs --fix     also remove the selectors those classes make dead
//   node scripts/check-css-usage.cjs --verbose list the classes only a prefix keeps
const fs = require('node:fs');
const path = require('node:path');

const STATIC = 'app/web/static';
const CSS = path.join(STATIC, 'app.css');

// Classes set by something this script cannot read: none today. A class
// goes here with the reason, never to silence a report.
const ALLOW = new Map([
]);

// The utility layer's scales are kept whole: someone writing mt-6 should find
// it beside mt-4 and mt-8, whether or not a page uses it today. Spacing,
// gap, alignment, line height, weight and width steps.
const SCALES = [
  /^(m|p)[trblxy]?-(auto|0|0-5|\d+)$/,
  /^gap(-[xy])?-(0|0-5|\d+)$/,
  /^(items|self|justify)-[a-z]+$/,
  /^(lh|fw)-[a-z]+$/,
  /^max-w-(xs|sm|md|lg|xl)$/,
];

// Prefixes the scripts join to a closed set of words, and that set. Without
// it, 'text-' + toneName(c) would keep every text-* class alive, and
// 'grade-' + grade every grade-* one.
const TONES = /^(success|danger|warning|accent|info|purple|default|muted|dim|border)$/;
const CLOSED = new Map([
  ['text-', TONES],     // toneClass (app-format.js)
  ['border-', TONES],   // 'border-' + toneName (app-network.js)
  ['tone-', TONES],     // toneVar (app-format.js)
  ['is-', TONES],       // toneClass(c).replace('text-', 'is-'): a bar's fill
  ['grade-', /^([A-F]|none)$/],
  ['status-', /^(open|in_progress|done|ignored)$/],   // a finding's status
]);

function sources() {
  const files = [path.join(STATIC, 'index.html'), path.join(STATIC, 'ui_i18n.json')];
  for (const dir of [STATIC, path.join(STATIC, 'vendor')]) {
    if (!fs.existsSync(dir)) continue;
    for (const f of fs.readdirSync(dir).sort()) if (f.endsWith('.js')) files.push(path.join(dir, f));
  }
  const walk = dir => {
    for (const e of fs.readdirSync(dir, {withFileTypes: true})) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith('.py')) files.push(p);
    }
  };
  walk('app/web');
  return files.map(f => ({file: f, text: fs.readFileSync(f, 'utf8')}));
}

// Every word a source could set as a class, and every prefix it builds one from.
function usage(srcs) {
  const words = new Set();
  const prefixes = new Set();
  for (const {text} of srcs) {
    for (const m of text.matchAll(/[A-Za-z_][\w-]*/g)) words.add(m[0]);
    // 'badge-' + x, "grade-tile grade-" + x, `x-` + y
    for (const m of text.matchAll(/([A-Za-z_][\w-]*-)['"`]\s*\+/g)) prefixes.add(m[1]);
    // `is-${tone}`, f"badge-{level}"
    for (const m of text.matchAll(/([A-Za-z_][\w-]*-)\$?\{/g)) prefixes.add(m[1]);
    // .replace('text-', 'is-')
    for (const m of text.matchAll(/replace\(\s*['"][^'"]*['"]\s*,\s*['"]([A-Za-z_][\w-]*-)['"]/g)) prefixes.add(m[1]);
  }
  return {words, prefixes};
}

// The style rules of a stylesheet, with where their selector starts and their
// block ends, through @media and @supports; @keyframes and @font-face hold no
// class selectors and are skipped.
function rules(css) {
  const out = [];
  // Blank comments and strings out, keeping offsets, so braces inside them do not count.
  const plain = css.replace(/\/\*[\s\S]*?\*\//g, m => m.replace(/[^\n]/g, ' '))
    .replace(/(["'])(?:\\.|(?!\1)[^\\\n])*\1/g, m => m.replace(/[^\n]/g, ' '));
  function block(from, to) {
    let i = from;
    while (i < to) {
      const open = plain.indexOf('{', i);
      if (open === -1 || open >= to) return;
      const head = plain.slice(i, open);
      // The selector or at-rule prelude starts after the last ; or } before it.
      const start = i + head.search(/\S/);
      let depth = 1, j = open + 1;
      while (j < to && depth) { if (plain[j] === '{') depth++; else if (plain[j] === '}') depth--; j++; }
      const prelude = plain.slice(start, open).trim();
      if (prelude.startsWith('@')) {
        if (/^@(media|supports|container|layer)\b/.test(prelude)) block(open + 1, j - 1);
      } else if (prelude) {
        out.push({start, open, end: j, selector: css.slice(start, open)});
      }
      i = j;
    }
  }
  block(0, plain.length);
  return out;
}

// Selectors of a list, split on the commas between them (not inside :is()).
function splitSelectors(text) {
  const parts = [];
  let depth = 0, last = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '(' || text[i] === '[') depth++;
    else if (text[i] === ')' || text[i] === ']') depth--;
    else if (text[i] === ',' && !depth) { parts.push(text.slice(last, i)); last = i + 1; }
  }
  parts.push(text.slice(last));
  return parts;
}

function classesOf(selector) {
  // Not inside [attr="..."]: that is a value, not a class.
  const bare = selector.replace(/\[[^\]]*\]/g, '');
  return [...bare.matchAll(/\.(-?[A-Za-z_][\w-]*)/g)].map(m => m[1]);
}

function analyse() {
  const css = fs.readFileSync(CSS, 'utf8');
  const {words, prefixes} = usage(sources());
  const state = new Map();   // class -> 'used' | 'prefix' | 'unused'
  const verdict = cls => {
    if (!state.has(cls)) {
      if (words.has(cls) || ALLOW.has(cls) || SCALES.some(re => re.test(cls))) state.set(cls, 'used');
      else if ([...prefixes].some(p => cls.startsWith(p) && cls.length > p.length
        && (!CLOSED.has(p) || CLOSED.get(p).test(cls.slice(p.length))))) state.set(cls, 'prefix');
      else state.set(cls, 'unused');
    }
    return state.get(cls);
  };
  const found = rules(css).map(rule => {
    const selectors = splitSelectors(rule.selector);
    const dead = selectors.map(s => classesOf(s).some(c => verdict(c) === 'unused'));
    return {...rule, selectors, dead};
  });
  const unused = [...state].filter(([, v]) => v === 'unused').map(([c]) => c).sort();
  const byPrefix = [...state].filter(([, v]) => v === 'prefix').map(([c]) => c).sort();
  return {css, found, unused, byPrefix};
}

function fix({css, found}) {
  let out = '';
  let at = 0;
  let removed = 0;
  for (const rule of found) {
    if (!rule.dead.some(Boolean)) continue;
    if (rule.dead.every(Boolean)) {
      // The whole rule, with the indentation before it and the line break after.
      let s = rule.start;
      while (s > 0 && (css[s - 1] === ' ' || css[s - 1] === '\t')) s--;
      let e = rule.end;
      if (css[e] === '\n') e++;
      out += css.slice(at, s);
      at = e;
    } else {
      const kept = rule.selectors.filter((_, i) => !rule.dead[i]).map(s => s.trim());
      const joiner = rule.selector.includes(',\n') ? ',\n' + (rule.selector.match(/,\n(\s*)/) || ['', ''])[1] : ', ';
      out += css.slice(at, rule.start) + kept.join(joiner) + ' ';
      at = rule.open;
    }
    removed += rule.dead.filter(Boolean).length;
  }
  out += css.slice(at);
  // A block left empty by the removal (an @media with nothing in it).
  out = out.replace(/@media[^{]*\{\s*\}\n?/g, '');
  fs.writeFileSync(CSS, out);
  return removed;
}

function main() {
  const argv = process.argv.slice(2);
  const result = analyse();
  if (argv.includes('--verbose') && result.byPrefix.length) {
    console.log(`Kept by a built prefix (${result.byPrefix.length}): ${result.byPrefix.join(' ')}`);
  }
  if (argv.includes('--fix') && result.unused.length) {
    const n = fix(result);
    console.log(`Removed ${n} selector(s) for ${result.unused.length} unused class(es)`);
    return;
  }
  if (result.unused.length) {
    console.error(`app.css styles ${result.unused.length} class(es) nothing uses (node scripts/check-css-usage.cjs --fix removes them):`);
    for (const cls of result.unused) {
      const lines = result.found.filter(r => r.selectors.some(s => classesOf(s).includes(cls)))
        .map(r => result.css.slice(0, r.start).split('\n').length);
      console.error(`  .${cls}  (line ${lines.join(', ')})`);
    }
    process.exit(1);
  }
  const total = result.found.reduce((n, r) => n + r.selectors.length, 0);
  console.log(`app.css: every class is used (${total} selectors in ${result.found.length} rules)`);
}

module.exports = {main, analyse};
if (require.main === module) main();
