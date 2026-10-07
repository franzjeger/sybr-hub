'use strict';
// The SPA is a graph of ES modules with one entry, the module index.html
// loads (app/web/static/main.js). ESLint checks each module on its own
// (no-undef catches a name used without an import); this checks the graph:
//
//   - every import is a relative specifier './name.js' naming a module in
//     app/web/static, and every name imported is exported there. A browser
//     refuses the whole graph over one missing export, so this is the check
//     that the page loads at all;
//   - imports are static. No import(), no 'export ... from', no default or
//     namespace imports: the server versions the specifiers it can see
//     (app/web/routes/frontend.py), and a module loaded under a second URL
//     is a second copy with its own state;
//   - every first-party script is either in the graph or one of the classic
//     scripts named below;
//   - the layering documented in main.js: leaves import nothing, services
//     import only leaves and each other without cycles, nothing imports the
//     markup handlers or the entry;
//   - the code a module runs while it loads touches nothing imported from a
//     module in its own import cycle. Function declarations are hoisted, but
//     another module's variables are not initialised until it has run, and in
//     a cycle that may not have happened yet.
//
//   node scripts/js-modules.cjs           check
//   node scripts/js-modules.cjs --order   print the order the browser runs them
const fs = require('node:fs');
const path = require('node:path');
const acorn = require('acorn');
const eslintScope = require('eslint-scope');

const ROOT = path.join(__dirname, '..');
const STATIC_DIR = path.join(ROOT, 'app', 'web', 'static');

// Third-party bundles, not ours to lint.
const THIRD_PARTY = new Set(['guacamole.min.js']);
// First-party files that are not modules: theme-init.js runs in <head>,
// before the first paint, which a module (always deferred) cannot; sw.js is
// the service worker, a separate global scope with nothing to import.
const CLASSIC = new Set(['theme-init.js', 'sw.js']);

const LEAVES = ['app-esc.js', 'app-i18n.js', 'app-icons.js', 'app-handlers.js', 'app-hooks.js', 'app-state.js'];
const SERVICES = ['app-format.js', 'app-ui.js', 'app-api.js', 'app-navigation.js', 'app-forms.js', 'app-shell-status.js', 'app-audit-presentation.js'];
const MARKUP_HANDLERS = 'app-markup-handlers.js';

function sourceTypeOf(file) {
  return CLASSIC.has(file) ? 'script' : 'module';
}

function parse(file, text = fs.readFileSync(path.join(STATIC_DIR, file), 'utf8'), options = {}) {
  return acorn.parse(text, {ecmaVersion: 'latest', sourceType: sourceTypeOf(file), locations: true, ranges: true, ...options});
}

// The module script each page loads: main.js for index.html (the
// interface), offline.js for offline.html. The first is the application's
// entry, the one the layering is about.
const SHELLS = ['index.html', 'offline.html'];

function entries() {
  return SHELLS.flatMap(shell => {
    const html = fs.readFileSync(path.join(STATIC_DIR, shell), 'utf8');
    const found = [...html.matchAll(/<script\b[^>]*\btype="module"[^>]*\bsrc="\/static\/([^"?]+\.js)"[^>]*>/g)].map(m => m[1]);
    if (found.length !== 1) throw new Error(`${shell} must load exactly one module script, found ${found.length}`);
    return found;
  });
}

const SPECIFIER = /^\.\/[A-Za-z0-9_-]+\.js$/;

// {file: {ast, imports: [{source, names: [name], node}], exports: Set}} for
// every module reachable from the entry, plus the problems found reading them.
function moduleGraph() {
  const modules = {};
  const problems = [];
  const where = (file, node) => `app/web/static/${file}:${node.loc.start.line}`;
  const queue = entries();
  while (queue.length) {
    const file = queue.shift();
    if (modules[file]) continue;
    const full = path.join(STATIC_DIR, file);
    if (!fs.existsSync(full)) { problems.push(`app/web/static/${file}: imported but missing`); continue; }
    let ast;
    try { ast = parse(file); } catch (e) { problems.push(`app/web/static/${file}: ${e.message}`); continue; }
    const info = {ast, imports: [], exports: new Set()};
    modules[file] = info;
    for (const node of ast.body) {
      if (node.type === 'ImportDeclaration') {
        const spec = String(node.source.value);
        if (!SPECIFIER.test(spec)) { problems.push(`${where(file, node)}: import '${spec}' must be './name.js'`); continue; }
        const names = [];
        for (const s of node.specifiers) {
          if (s.type !== 'ImportSpecifier') { problems.push(`${where(file, s)}: only named imports ({a, b}), no default or namespace import`); continue; }
          names.push(s.imported.name);
        }
        const source = spec.slice(2);
        info.imports.push({source, names, node});
        queue.push(source);
      } else if (node.type === 'ExportNamedDeclaration') {
        if (node.source) { problems.push(`${where(file, node)}: no 'export ... from'; import, then export`); continue; }
        const d = node.declaration;
        if (!d) { node.specifiers.forEach(s => info.exports.add(s.exported.name)); continue; }
        if (d.type === 'VariableDeclaration') d.declarations.forEach(x => x.id.type === 'Identifier' && info.exports.add(x.id.name));
        else if (d.id) info.exports.add(d.id.name);
      } else if (node.type === 'ExportDefaultDeclaration' || node.type === 'ExportAllDeclaration') {
        problems.push(`${where(file, node)}: named exports only`);
      }
    }
    (function walk(node) {
      if (!node || typeof node.type !== 'string') return;
      if (node.type === 'ImportExpression') problems.push(`${where(file, node)}: no import(); imports are static`);
      for (const key of Object.keys(node)) {
        if (key === 'loc' || key === 'range') continue;
        const value = node[key];
        if (Array.isArray(value)) value.forEach(walk);
        else if (value && typeof value.type === 'string') walk(value);
      }
    })(ast);
  }
  for (const [file, info] of Object.entries(modules)) {
    for (const imp of info.imports) {
      const target = modules[imp.source];
      if (!target) continue;
      for (const name of imp.names) {
        if (!target.exports.has(name)) problems.push(`${where(file, imp.node)}: ${imp.source} does not export ${name}`);
      }
    }
  }
  return {modules, problems};
}

// The order a browser evaluates the graph: depth first, imports in source
// order, each module after its imports (unless it is already in progress).
function evaluationOrder(modules, entry) {
  const seen = new Set();
  const order = [];
  (function visit(file) {
    if (seen.has(file) || !modules[file]) return;
    seen.add(file);
    for (const imp of modules[file].imports) visit(imp.source);
    order.push(file);
  })(entry);
  return order;
}

// Strongly connected components (Tarjan): {file: componentId}.
function components(modules) {
  let index = 0;
  const stack = [];
  const state = new Map();
  const comp = {};
  let next = 0;
  function connect(v) {
    const s = {index, low: index, onStack: true};
    index++;
    state.set(v, s);
    stack.push(v);
    for (const imp of modules[v].imports) {
      const w = imp.source;
      if (!modules[w]) continue;
      if (!state.has(w)) { connect(w); s.low = Math.min(s.low, state.get(w).low); }
      else if (state.get(w).onStack) s.low = Math.min(s.low, state.get(w).index);
    }
    if (s.low === s.index) {
      const id = next++;
      let w;
      do { w = stack.pop(); state.get(w).onStack = false; comp[w] = id; } while (w !== v);
    }
  }
  for (const v of Object.keys(modules)) if (!state.has(v)) connect(v);
  return comp;
}

// APIs that keep a function to call later rather than calling it now. A
// function handed to one of these does not run while its module loads; a
// function handed to anything else (forEach, an IIFE) is assumed to.
const DEFERRING_CALLS = new Set([
  'addEventListener', 'setTimeout', 'setInterval', 'requestAnimationFrame', 'then', 'catch', 'finally',
  'onViewShown', 'onSignedIn', 'onLoginViewShown', 'registerToolCustomer', 'registerUiHandlers',
]);
const DEFERRING_CONSTRUCTORS = new Set(['MutationObserver', 'ResizeObserver', 'IntersectionObserver']);

function calleeName(callee) {
  if (callee.type === 'Identifier') return callee.name;
  if (callee.type === 'MemberExpression' && !callee.computed) return callee.property.name;
  return null;
}

function setParents(node, parent) {
  if (!node || typeof node.type !== 'string') return;
  node.parent = parent;
  for (const key of Object.keys(node)) {
    if (key === 'parent' || key === 'loc' || key === 'range') continue;
    const value = node[key];
    if (Array.isArray(value)) value.forEach(v => setParents(v, node));
    else if (value && typeof value.type === 'string') setParents(value, node);
  }
}

// Whether a function written at this point runs later, not when it is reached.
function isDeferred(fn) {
  const parent = fn.parent;
  if (!parent) return false;
  if (fn.type === 'FunctionDeclaration') return true;   // runs when called; calls are followed
  if ((parent.type === 'CallExpression' || parent.type === 'NewExpression') && parent.arguments.includes(fn)) {
    const name = calleeName(parent.callee);
    return parent.type === 'NewExpression' ? DEFERRING_CONSTRUCTORS.has(name) : DEFERRING_CALLS.has(name);
  }
  // A handler map: registerUiHandlers({name: function() {...}}).
  if (parent.type === 'Property' && parent.value === fn) {
    const object = parent.parent;
    const call = object && object.parent;
    return !!call && call.type === 'CallExpression' && call.arguments.includes(object) && DEFERRING_CALLS.has(calleeName(call.callee));
  }
  // Stored, not called: el.onclick = function, var f = function, return function.
  if (parent.type === 'AssignmentExpression' && parent.right === fn) return true;
  if (parent.type === 'VariableDeclarator' && parent.init === fn) return true;
  if (parent.type === 'ReturnStatement') return true;
  return false;
}

// Whether this mention of a function calls it now. Handing it to an API
// that keeps it (setInterval(f), addEventListener('x', f)) or storing it does
// not; calling it, or handing it to anything else (list.forEach(f)), is
// assumed to.
function mentionRuns(id) {
  const parent = id.parent;
  if (!parent) return true;
  if ((parent.type === 'CallExpression' || parent.type === 'NewExpression') && parent.arguments.includes(id)) {
    const name = calleeName(parent.callee);
    return parent.type === 'NewExpression' ? !DEFERRING_CONSTRUCTORS.has(name) : !DEFERRING_CALLS.has(name);
  }
  if (parent.type === 'AssignmentExpression' && parent.right === id) return false;
  if (parent.type === 'VariableDeclarator' && parent.init === id) return false;
  return true;
}

// The innermost function around a node, or null at the top level.
function enclosingFunction(node) {
  for (let n = node.parent; n; n = n.parent) {
    if (n.type === 'FunctionDeclaration' || n.type === 'FunctionExpression' || n.type === 'ArrowFunctionExpression') return n;
  }
  return null;
}

// For one module: the imported names its top-level code reads while the
// module loads, directly or through its own functions it calls then.
function loadTimeImports(info) {
  const ast = info.ast;
  setParents(ast, null);
  const manager = eslintScope.analyze(ast, {ecmaVersion: 2022, sourceType: 'module'});
  const moduleScope = manager.globalScope.childScopes.find(s => s.type === 'module');
  const ownFunctions = new Map();   // name -> FunctionDeclaration at the top level
  for (const node of ast.body) {
    const d = node.type === 'ExportNamedDeclaration' ? node.declaration : node;
    if (d && d.type === 'FunctionDeclaration') ownFunctions.set(d.id.name, d);
  }
  const imported = new Map();       // local name -> source module
  for (const imp of info.imports) for (const spec of imp.node.specifiers) imported.set(spec.local.name, imp.source);

  // Every reference, with the function it sits in; whether it runs at load
  // depends on whether that function does.
  const refs = [];
  (function collect(scope) {
    for (const ref of scope.references) {
      const variable = ref.resolved;
      if (!variable || variable.scope !== moduleScope) continue;
      refs.push({name: ref.identifier.name, node: ref.identifier, fn: enclosingFunction(ref.identifier)});
    }
    scope.childScopes.forEach(collect);
  })(moduleScope);

  // Functions that run while the module loads: those reached at the top
  // level without being deferred, and the own functions they reference.
  const running = new Set();
  const runsNow = fn => {
    for (let f = fn; f; f = enclosingFunction(f)) {
      if (running.has(f)) return true;
      if (isDeferred(f)) return false;
    }
    return true;   // reached the top level through immediately-run functions
  };
  let changed = true;
  while (changed) {
    changed = false;
    for (const ref of refs) {
      const fn = ownFunctions.get(ref.name);
      if (!fn || running.has(fn)) continue;
      if (!mentionRuns(ref.node)) continue;
      if (ref.fn === null || runsNow(ref.fn)) { running.add(fn); changed = true; }
    }
  }
  const out = [];
  for (const ref of refs) {
    if (!imported.has(ref.name)) continue;
    if (ref.fn === null || runsNow(ref.fn)) out.push({name: ref.name, source: imported.get(ref.name), line: ref.node.loc.start.line});
  }
  return out;
}

function check() {
  const {modules, problems} = moduleGraph();
  const files = Object.keys(modules);
  const entry = entries()[0];

  // Every first-party script is a module of the graph or a known classic one.
  for (const file of fs.readdirSync(STATIC_DIR).filter(f => f.endsWith('.js')).sort()) {
    if (THIRD_PARTY.has(file) || CLASSIC.has(file) || modules[file]) continue;
    problems.push(`app/web/static/${file}: not imported by any module and not a known classic script`);
  }

  // Layering.
  const shellEntries = entries();
  const layer = file => LEAVES.includes(file) ? 1 : SERVICES.includes(file) ? 2 : file === MARKUP_HANDLERS ? 4 : shellEntries.includes(file) ? 5 : 3;
  for (const file of files) {
    for (const imp of modules[file].imports) {
      const from = layer(file);
      const to = layer(imp.source);
      const line = `app/web/static/${file}:${imp.node.loc.start.line}`;
      if (from === 1) problems.push(`${line}: ${file} is a leaf and imports nothing (it imports ${imp.source})`);
      else if (to > from) problems.push(`${line}: ${file} (layer ${from}) imports ${imp.source} (layer ${to}); see main.js`);
      if (to >= 4 && from !== 5) problems.push(`${line}: nothing but the entry imports ${imp.source}`);
    }
  }
  // offline.js, the offline page's script, is a graph of its own.
  for (const other of shellEntries.slice(1)) {
    if (modules[other] && modules[other].imports.length) problems.push(`app/web/static/${other}: the offline page imports nothing`);
  }
  for (const file of [...LEAVES, ...SERVICES, MARKUP_HANDLERS]) {
    if (!modules[file]) problems.push(`app/web/static/${file}: named in the layering but not in the graph`);
  }

  // No import cycles, including feature modules. Compose callbacks in main.js.
  const comp = components(modules);
  const members = {};
  for (const file of files) (members[comp[file]] = members[comp[file]] || []).push(file);
  for (const file of files) {
    const cycle = members[comp[file]];
    const selfImport = modules[file].imports.some(i => i.source === './' + file);
    if (cycle.length < 2 && !selfImport) continue;
    problems.push(`app/web/static/${file}: in an import cycle with ${(selfImport ? [file] : cycle.filter(f => f !== file)).join(', ')}`);
    for (const use of loadTimeImports(modules[file])) {
      if (comp[use.source] !== comp[file]) continue;
      problems.push(`app/web/static/${file}:${use.line}: reads ${use.name} from ${use.source} while loading, ` +
        'and the two are in an import cycle, so it may not have run yet. Defer it (a hook, an event, start-up in main.js).');
    }
  }
  return {modules, problems, comp, members, entry};
}

function main() {
  const {modules, problems, members, entry} = check();
  if (process.argv.includes('--order')) {
    evaluationOrder(modules, entry).forEach((f, i) => console.log(String(i + 1).padStart(3), f));
    return;
  }
  for (const p of problems) console.error(p);
  if (problems.length) {
    console.error(`${problems.length} module problem(s); see scripts/js-modules.cjs and the layering in main.js`);
    process.exit(1);
  }
  const cycles = Object.values(members).filter(m => m.length > 1);
  console.log(`Modules: ${Object.keys(modules).length} from ${entry}, every import resolves; ` +
    `layering holds; ${cycles.length} import cycles`);
}

module.exports = {STATIC_DIR, THIRD_PARTY, CLASSIC, sourceTypeOf, parse, entries, moduleGraph, evaluationOrder, check, main};
if (require.main === module) main();
