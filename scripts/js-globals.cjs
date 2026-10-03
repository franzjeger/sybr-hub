'use strict';
// The SPA is a set of classic scripts that share one global scope: a function
// declared at the top of app-audit.js is called from app-infra.js, and the
// browser resolves the name at call time. That makes two defects invisible to
// a per-file linter:
//
//   - a name declared in two files. The script that loads later silently
//     replaces the earlier definition (saveCustomerNotes was defined in both
//     app-customers.js and app-customer-detail.js, and only one ever ran);
//   - a call to a name no file declares, which only fails when that code path
//     runs in front of a user.
//
// This module reads the scripts index.html loads, in load order, and returns
// every top-level declaration. eslint.config.cjs gives each file the names
// the *other* files declare as globals, so `no-undef` sees the real scope and
// `no-redeclare` sees a second declaration of another file's name. main()
// reports cross-file duplicates directly, with both locations.
//
//   node scripts/js-globals.cjs          fail on a name declared twice
//   node scripts/js-globals.cjs --list   print every shared global and its file
const fs = require('node:fs');
const path = require('node:path');
const acorn = require('acorn');

const ROOT = path.join(__dirname, '..');
const STATIC_DIR = path.join(ROOT, 'app', 'web', 'static');

// Third-party bundles that index.html loads into the same scope. They are not
// linted; the names they define are declared by hand in eslint.config.cjs.
const THIRD_PARTY = new Set(['guacamole.min.js']);

// The first-party scripts index.html loads with a plain <script src>, in order.
function sharedScripts() {
  const html = fs.readFileSync(path.join(STATIC_DIR, 'index.html'), 'utf8');
  const files = [];
  const re = /<script\b[^>]*\bsrc="\/static\/([^"]+\.js)"[^>]*>/g;
  let match;
  while ((match = re.exec(html))) {
    const file = match[1];
    if (file.startsWith('vendor/') || THIRD_PARTY.has(file)) continue;
    // theme-init.js runs before the body is parsed and keeps to itself in an IIFE.
    if (file === 'theme-init.js') continue;
    files.push(file);
  }
  return files;
}

function patternNames(pattern, out) {
  if (!pattern) return out;
  switch (pattern.type) {
    case 'Identifier': out.push(pattern); break;
    case 'ObjectPattern':
      pattern.properties.forEach(p => patternNames(p.type === 'RestElement' ? p.argument : p.value, out));
      break;
    case 'ArrayPattern': pattern.elements.forEach(e => patternNames(e, out)); break;
    case 'RestElement': patternNames(pattern.argument, out); break;
    case 'AssignmentPattern': patternNames(pattern.left, out); break;
  }
  return out;
}

// Every name a script declares at its top level, with the line it is on.
function topLevelDeclarations(file) {
  const text = fs.readFileSync(path.join(STATIC_DIR, file), 'utf8');
  const ast = acorn.parse(text, {ecmaVersion: 'latest', sourceType: 'script', locations: true});
  const out = [];
  const add = (id, kind) => out.push({name: id.name, kind, file, line: id.loc.start.line});
  for (const node of ast.body) {
    if (node.type === 'FunctionDeclaration' && node.id) add(node.id, 'function');
    else if (node.type === 'ClassDeclaration' && node.id) add(node.id, 'class');
    else if (node.type === 'VariableDeclaration') {
      for (const decl of node.declarations) patternNames(decl.id, []).forEach(id => add(id, node.kind));
    }
  }
  return out;
}

// {file: [declaration, ...]} for every shared script.
function declarationsByFile() {
  const out = {};
  for (const file of sharedScripts()) out[file] = topLevelDeclarations(file);
  return out;
}

// The globals one file sees from the others: everything they declare. They are
// writable because the scripts do assign each other's state (_currentUser).
function globalsFor(file, byFile = declarationsByFile()) {
  const globals = {};
  for (const [other, declarations] of Object.entries(byFile)) {
    if (other === file) continue;
    for (const d of declarations) globals[d.name] = 'writable';
  }
  return globals;
}

function duplicates(byFile = declarationsByFile()) {
  const seen = new Map();
  for (const declarations of Object.values(byFile)) {
    for (const d of declarations) {
      if (!seen.has(d.name)) seen.set(d.name, []);
      seen.get(d.name).push(d);
    }
  }
  return [...seen.values()].filter(list => list.length > 1);
}

function main() {
  const byFile = declarationsByFile();
  if (process.argv.includes('--list')) {
    for (const [file, declarations] of Object.entries(byFile)) {
      for (const d of declarations) console.log(`${d.name}\t${d.kind}\t${file}:${d.line}`);
    }
    return;
  }
  const dups = duplicates(byFile);
  for (const list of dups) {
    const where = list.map(d => `app/web/static/${d.file}:${d.line}`).join(', ');
    console.error(`global \`${list[0].name}\` is declared more than once (${where}); ` +
      'the script that loads last silently replaces the others');
  }
  if (dups.length) process.exit(1);
  const total = Object.values(byFile).reduce((n, list) => n + list.length, 0);
  console.log(`Shared globals: ${total} names across ${Object.keys(byFile).length} scripts, none declared twice`);
}

module.exports = {sharedScripts, topLevelDeclarations, declarationsByFile, globalsFor, duplicates, main, STATIC_DIR};
if (require.main === module) main();
