'use strict';
// Stored-XSS guard for the SPA. Every value interpolated into an HTML string
// must be escaped (esc/escJs), numeric, a literal translation, or HTML that is
// itself checked where it is built. A value that already is escaped HTML can
// be marked with a leading /* safe-html */ comment; keep those rare.
//
//   node scripts/check-html-escaping.cjs          enforce ENFORCED, count the rest
//   node scripts/check-html-escaping.cjs --all    list every finding in every file
//   node scripts/check-html-escaping.cjs FILE...  list findings for the given files
const fs = require('node:fs');
const path = require('node:path');
const acorn = require('acorn');

const STATIC_DIR = path.join(__dirname, '..', 'app', 'web', 'static');

// Files that must stay clean. Add a file here once it passes.
const ENFORCED = new Set([
  'app-findings.js',
  'app-customers.js',
  'app-dashboard.js',
  'app-infra.js',
  'app-network.js',
  'app-tailscale.js',
  'app-also.js',
  'app-assessments.js',
  'app-audit.js',
  'app-baseline-deploy.js',
  'app-policy-deploy.js',
  'app-policy-overview.js',
  'app.js',
  'app-chrome.js',
  'app-settings.js',
  'app-setup.js',
  'app-tls.js',
  'app-integrations.js',
  'app-customer-detail.js',
]);

const HTML_PROPS = new Set(['innerHTML', 'outerHTML', 'srcdoc']);
const HTML_METHODS = {insertAdjacentHTML: 1, createContextualFragment: 0, write: 0, writeln: 0};
const NUMBER_FUNCS = new Set(['Number', 'parseInt', 'parseFloat', 'isNaN', 'isFinite', 'Boolean']);
// Methods that only return numbers or booleans.
const NUMBER_METHODS = new Set([
  'toFixed', 'toPrecision', 'toExponential', 'indexOf', 'lastIndexOf', 'findIndex', 'includes',
  'startsWith', 'endsWith', 'some', 'every', 'test', 'getTime', 'getFullYear', 'getMonth', 'getDate',
  'getDay', 'getHours', 'getMinutes', 'getSeconds', 'localeCompare', 'charCodeAt',
]);
// Methods whose result is as safe as their receiver (and listed arguments).
const PRESERVING_METHODS = new Set([
  'slice', 'substring', 'substr', 'toUpperCase', 'toLowerCase', 'trim', 'trimStart', 'trimEnd',
  'toString', 'toLocaleString', 'toLocaleDateString', 'toLocaleTimeString', 'toDateString',
  'toTimeString', 'toISOString', 'toUTCString', 'charAt', 'at', 'padStart', 'padEnd', 'repeat',
  'filter', 'sort', 'reverse', 'concat', 'flat', 'join', 'replace', 'replaceAll', 'split',
]);
const ITERATION_CALLBACKS = new Set(['forEach', 'map', 'filter', 'some', 'every', 'find', 'findIndex', 'flatMap']);
const UNSAFE = {kind: 'unsafe'};
const SAFE = {kind: 'safe'};

class Scope {
  constructor(parent, node) {
    this.parent = parent;
    this.node = node;
    this.bindings = new Map();
  }
  declare(name, kind) {
    let binding = this.bindings.get(name);
    if (!binding) {
      binding = {name, kind, values: [], unsafe: false, why: null, fn: null};
      this.bindings.set(name, binding);
      allBindings.push(binding);
    }
    return binding;
  }
  lookup(name) {
    for (let scope = this; scope; scope = scope.parent) {
      const binding = scope.bindings.get(name);
      if (binding) return binding;
    }
    return null;
  }
}

// Per-analysis state, reset by analyze().
let allBindings = [];
let functionScopes = new Map();
let functionReturns = new Map();
let declaredFunctions = new Map();
let globalScope = new Scope(null, null);

function children(node) {
  const out = [];
  for (const key in node) {
    if (key === 'type' || key === 'start' || key === 'end' || key === 'loc' || key === '__file') continue;
    const value = node[key];
    if (Array.isArray(value)) {
      for (const child of value) if (child && typeof child.type === 'string') out.push(child);
    } else if (value && typeof value.type === 'string') {
      out.push(value);
    }
  }
  return out;
}

function isFunction(node) {
  return node.type === 'FunctionDeclaration' || node.type === 'FunctionExpression' ||
    node.type === 'ArrowFunctionExpression';
}

function patternNames(pattern, out = []) {
  if (!pattern) return out;
  switch (pattern.type) {
    case 'Identifier': out.push(pattern.name); break;
    case 'ObjectPattern': pattern.properties.forEach(p => patternNames(p.type === 'RestElement' ? p.argument : p.value, out)); break;
    case 'ArrayPattern': pattern.elements.forEach(e => patternNames(e, out)); break;
    case 'RestElement': patternNames(pattern.argument, out); break;
    case 'AssignmentPattern': patternNames(pattern.left, out); break;
  }
  return out;
}

function memberName(node) {
  if (node.type !== 'MemberExpression') return null;
  if (!node.computed && node.property.type === 'Identifier') return node.property.name;
  if (node.computed && node.property.type === 'Literal') return String(node.property.value);
  return null;
}

function rootIdentifier(node) {
  while (node.type === 'MemberExpression') node = node.object;
  return node.type === 'Identifier' ? node : null;
}

// ── Pass 1: declarations, function scopes and return values ───────────
function declarePass(node, scope, parent, fnStack) {
  if (isFunction(node)) {
    if (node.type === 'FunctionDeclaration' && node.id) {
      const binding = scope.declare(node.id.name, 'function');
      binding.fn = node;
      declaredFunctions.set(node, binding);
    }
    const inner = new Scope(scope, node);
    functionScopes.set(node, inner);
    functionReturns.set(node, []);
    if (node.type === 'FunctionExpression' && node.id) inner.declare(node.id.name, 'function').fn = node;
    // An array iteration callback receives an element of its receiver and a
    // numeric index, so a constant table stays constant inside the callback.
    const iterates = parent && parent.type === 'CallExpression' && parent.arguments[0] === node &&
      ITERATION_CALLBACKS.has(memberName(parent.callee));
    node.params.forEach((param, i) => {
      let value = UNSAFE;
      if (iterates && param.type === 'Identifier' && i === 0) value = {node: parent.callee.object, scope};
      if (iterates && param.type === 'Identifier' && i === 1) value = SAFE;
      for (const name of patternNames(param)) inner.declare(name, 'param').values.push(value);
    });
    if (node.body.type !== 'BlockStatement') functionReturns.get(node).push({node: node.body, scope: inner});
    declarePass(node.body, inner, node, fnStack.concat([node]));
    return;
  }
  const fn = fnStack[fnStack.length - 1];
  switch (node.type) {
    case 'VariableDeclaration': {
      const loopHead = parent && (parent.type === 'ForInStatement' || parent.type === 'ForOfStatement') && parent.left === node;
      for (const decl of node.declarations) {
        if (decl.id.type === 'Identifier') {
          const binding = scope.declare(decl.id.name, node.kind);
          if (loopHead) binding.values.push(parent.type === 'ForOfStatement' ? {node: parent.right, scope} : UNSAFE);
          else binding.values.push(decl.init ? {node: decl.init, scope} : SAFE);
        } else {
          for (const name of patternNames(decl.id)) scope.declare(name, node.kind).values.push(UNSAFE);
        }
      }
      break;
    }
    case 'CatchClause':
      for (const name of patternNames(node.param)) scope.declare(name, 'catch').values.push(UNSAFE);
      break;
    case 'ClassDeclaration':
      if (node.id) scope.declare(node.id.name, 'class').values.push(UNSAFE);
      break;
    case 'ReturnStatement':
      if (fn) functionReturns.get(fn).push(node.argument ? {node: node.argument, scope} : SAFE);
      break;
  }
  for (const child of children(node)) declarePass(child, scope, node, fnStack);
}

// ── Pass 2: every later assignment to a binding ───────────────────────
function resolveForWrite(scope, name) {
  return scope.lookup(name) || globalScope.declare(name, 'implicit');
}

function assignPass(node, scope) {
  if (isFunction(node)) scope = functionScopes.get(node);
  switch (node.type) {
    case 'AssignmentExpression':
      if (node.left.type === 'Identifier') {
        const binding = resolveForWrite(scope, node.left.name);
        const numeric = !['=', '+=', '||=', '&&=', '??='].includes(node.operator);
        binding.values.push(numeric ? SAFE : {node: node.right, scope});
      } else if (node.left.type === 'MemberExpression') {
        const root = rootIdentifier(node.left);
        const binding = root && scope.lookup(root.name);
        if (binding) binding.values.push({node: node.right, scope});
      } else {
        for (const name of patternNames(node.left)) resolveForWrite(scope, name).values.push(UNSAFE);
      }
      break;
    case 'ForInStatement':
    case 'ForOfStatement':
      if (node.left.type !== 'VariableDeclaration') {
        for (const name of patternNames(node.left)) resolveForWrite(scope, name).values.push(UNSAFE);
      }
      break;
    case 'CallExpression': {
      // push/unshift/splice and Object.assign put values into an existing container.
      const method = memberName(node.callee);
      let target = null;
      let added = [];
      if (method === 'push' || method === 'unshift') { target = node.callee.object; added = node.arguments; }
      else if (method === 'splice') { target = node.callee.object; added = node.arguments.slice(2); }
      else if (method === 'assign' && node.callee.object.type === 'Identifier' && node.callee.object.name === 'Object') {
        target = node.arguments[0];
        added = node.arguments.slice(1);
      }
      const root = target && rootIdentifier(target);
      const binding = root && scope.lookup(root.name);
      if (binding) for (const arg of added) binding.values.push({node: arg, scope});
      break;
    }
  }
  for (const child of children(node)) assignPass(child, scope);
}

// ── Value safety ──────────────────────────────────────────────────────
function isAnnotated(node) {
  return node.__file.annotated.has(node.start);
}

function htmlLike(text) {
  return /<\/?[a-zA-Z][\w-]*|<!--/.test(text);
}

function concatParts(node, out = []) {
  if (node.type === 'BinaryExpression' && node.operator === '+') {
    concatParts(node.left, out);
    concatParts(node.right, out);
  } else {
    out.push(node);
  }
  return out;
}

function isStringLiteral(node) {
  return node.type === 'Literal' && typeof node.value === 'string';
}

function isHtmlExpression(node) {
  if (node.type === 'TemplateLiteral') return node.quasis.some(q => htmlLike(q.value.cooked || ''));
  if (node.type === 'BinaryExpression' && node.operator === '+') {
    return concatParts(node).some(part => isStringLiteral(part) && htmlLike(part.value));
  }
  return false;
}

function isGlobalHelper(scope, name) {
  const binding = scope.lookup(name);
  return binding && binding === globalScope.bindings.get(name) && binding.kind === 'function';
}

function isBuiltin(scope, name) {
  return !scope.lookup(name);
}

// Returns the sub-expressions that make `node` unsafe; empty means safe.
function unsafeLeaves(node, scope) {
  if (isAnnotated(node)) return [];
  switch (node.type) {
    case 'Literal':
      return [];
    case 'TemplateLiteral':
      if (isHtmlExpression(node)) return [];
      return node.expressions.flatMap(e => unsafeLeaves(e, scope));
    case 'BinaryExpression':
      if (node.operator !== '+') return [];
      if (isHtmlExpression(node)) return [];
      return concatParts(node).flatMap(p => unsafeLeaves(p, scope));
    case 'UnaryExpression':
    case 'UpdateExpression':
      return [];
    case 'LogicalExpression':
      // A falsy left side renders as '', 0, false, null, undefined or NaN.
      if (node.operator === '&&') return unsafeLeaves(node.right, scope);
      return unsafeLeaves(node.left, scope).concat(unsafeLeaves(node.right, scope));
    case 'ConditionalExpression':
      return unsafeLeaves(node.consequent, scope).concat(unsafeLeaves(node.alternate, scope));
    case 'SequenceExpression':
      return unsafeLeaves(node.expressions[node.expressions.length - 1], scope);
    case 'AssignmentExpression':
      return node.operator === '=' ? unsafeLeaves(node.right, scope) : [node];
    case 'ChainExpression':
      return unsafeLeaves(node.expression, scope).length ? [node] : [];
    case 'ArrayExpression':
      return node.elements.filter(Boolean).flatMap(e => unsafeLeaves(e.type === 'SpreadElement' ? e.argument : e, scope));
    case 'ObjectExpression':
      return node.properties.flatMap(p => unsafeLeaves(p.type === 'SpreadElement' ? p.argument : p.value, scope));
    case 'FunctionExpression':
    case 'ArrowFunctionExpression':
      return [];
    case 'Identifier': {
      if (node.name === 'undefined' || node.name === 'NaN' || node.name === 'Infinity') return [];
      const binding = scope.lookup(node.name);
      return binding && !binding.unsafe && binding.kind !== 'function' && binding.kind !== 'class' ? [] : [node];
    }
    case 'MemberExpression':
      // Reading markup back from the DOM yields what the parser already accepted.
      if (['length', 'innerHTML', 'outerHTML'].includes(memberName(node))) return [];
      // A property of a safe container (constant lookup table) is safe.
      return unsafeLeaves(node.object, scope).length ? [node] : [];
    case 'NewExpression':
      return node.callee.type === 'Identifier' && node.callee.name === 'Date' && isBuiltin(scope, 'Date') ? [] : [node];
    case 'CallExpression':
      return callIsSafe(node, scope) ? [] : [node];
    default:
      return [node];
  }
}

function safe(node, scope) {
  return unsafeLeaves(node, scope).length === 0;
}

const evaluating = new Set();

function returnsSafe(fnNode) {
  const declared = declaredFunctions.get(fnNode);
  if (declared) return !declared.returnsUnsafe;
  // Function expressions are evaluated on demand; a recursive call adds nothing.
  if (evaluating.has(fnNode)) return true;
  evaluating.add(fnNode);
  try {
    return functionReturns.get(fnNode).every(r => r === SAFE || safe(r.node, r.scope));
  } finally {
    evaluating.delete(fnNode);
  }
}

// replace(/[^a-zA-Z0-9_-]/g, '_') leaves only characters that are inert in
// HTML text, attributes and quoted inline JavaScript.
function whitelistRegex(node) {
  if (!node || !node.regex || !node.regex.flags.includes('g')) return false;
  const match = /^\[\^((?:\\.|[^\]\\])*)\]\+?$/.exec(node.regex.pattern);
  if (!match) return false;
  return /^[A-Za-z0-9_\-. :,@+\/]*$/.test(match[1].replace(/\\[wds.\-_:@\/]/g, ''));
}

// Every function a name can hold (its declaration plus any reassignment), or
// null when it may also hold something that is not a function.
function functionsOf(binding) {
  if (!binding) return null;
  const fns = binding.fn ? [binding.fn] : [];
  for (const value of binding.values) {
    if (!value.node || !isFunction(value.node)) return null;
    fns.push(value.node);
  }
  return fns.length ? fns : null;
}

function allReturnSafe(fns) {
  return !!fns && fns.every(returnsSafe);
}

function callIsSafe(node, scope) {
  const callee = node.callee;
  const args = node.arguments;
  if (isFunction(callee)) return returnsSafe(callee);
  if (callee.type === 'Identifier') {
    const name = callee.name;
    if ((name === 'esc' || name === 'escJs') && isGlobalHelper(scope, name)) return true;
    // t(key, fallback) returns the translation, else the fallback, else the key.
    if (name === 't' && isGlobalHelper(scope, name)) return args.every(a => safe(a, scope));
    if (NUMBER_FUNCS.has(name) && isBuiltin(scope, name)) return true;
    if (name === 'String' && isBuiltin(scope, name)) return args.every(a => safe(a, scope));
    return allReturnSafe(functionsOf(scope.lookup(name)));
  }
  if (callee.type === 'MemberExpression') {
    const method = memberName(callee);
    const object = callee.object;
    if (object.type === 'Identifier' && object.name === 'Math' && isBuiltin(scope, 'Math')) return true;
    if (object.type === 'Identifier' && object.name === 'Date' && isBuiltin(scope, 'Date') && method === 'now') return true;
    if (NUMBER_METHODS.has(method)) return true;
    if (method === 'map' || method === 'flatMap') {
      const fn = args[0];
      if (!fn) return false;
      if (isFunction(fn)) return returnsSafe(fn);
      if (fn.type === 'Identifier') return allReturnSafe(functionsOf(scope.lookup(fn.name)));
      return false;
    }
    if (method === 'replace' || method === 'replaceAll') {
      if (!args[1] || isFunction(args[1]) || !safe(args[1], scope)) return false;
      return whitelistRegex(args[0]) || safe(object, scope);
    }
    if (PRESERVING_METHODS.has(method)) {
      const extra = ['padStart', 'padEnd', 'join', 'concat'].includes(method) ? args : [];
      return safe(object, scope) && extra.every(a => safe(a, scope));
    }
  }
  return false;
}

// Propagate "unsafe" through bindings and named functions until stable.
function solve() {
  const functions = [...declaredFunctions.values()];
  let changed = true;
  while (changed) {
    changed = false;
    for (const binding of allBindings) {
      if (binding.unsafe) continue;
      for (const value of binding.values) {
        if (value === SAFE) continue;
        if (value === UNSAFE) {
          binding.unsafe = true;
          binding.why = binding.kind === 'param' ? 'a function parameter' : 'set from outside this code';
          break;
        }
        const leaves = unsafeLeaves(value.node, value.scope);
        if (leaves.length) {
          binding.unsafe = true;
          binding.why = (binding.kind === 'param' ? 'an element of ' : 'assigned from ') +
            snippet(leaves[0]) + ' on line ' + leaves[0].loc.start.line;
          break;
        }
      }
      if (binding.unsafe) changed = true;
    }
    for (const fn of functions) {
      if (fn.returnsUnsafe) continue;
      const bad = functionReturns.get(fn.fn).some(r => r !== SAFE && !safe(r.node, r.scope));
      if (bad) { fn.returnsUnsafe = true; changed = true; }
    }
  }
}

// ── HTML context: esc() is not enough inside an inline JS string ───────
// Tracks enough of the HTML tokenizer to know whether a position is inside
// a quoted JavaScript string of an on* attribute or javascript: URL.
function inlineScriptString(prefix) {
  let state = 'unknown';
  let attr = '';
  let quote = '';
  let script = false;
  let jsQuote = '';
  for (let i = 0; i < prefix.length; i++) {
    const c = prefix[i];
    if (state === 'unknown' || state === 'text') {
      if (c === '<' && /[a-zA-Z]/.test(prefix[i + 1] || '')) { state = 'tag'; attr = ''; }
      continue;
    }
    if (state === 'tag') {
      if (c === '>') state = 'text';
      else if (c === '=') state = 'before-value';
      else if (/\s/.test(c)) attr = '';
      else attr += c.toLowerCase();
      continue;
    }
    if (state === 'before-value') {
      if (c === '"' || c === "'") {
        quote = c;
        state = 'value';
        script = /^on/.test(attr) || ((attr === 'href' || attr === 'src') && /^\s*javascript:/i.test(prefix.slice(i + 1)));
        jsQuote = '';
      } else if (!/\s/.test(c)) {
        state = 'tag';
      }
      continue;
    }
    if (state === 'value') {
      if (c === quote) { state = 'tag'; attr = ''; continue; }
      if (!script) continue;
      if (jsQuote) {
        if (c === '\\') i++;
        else if (c === jsQuote) jsQuote = '';
      } else if (c === "'" || c === '`' || (c === '"' && quote === "'")) {
        jsQuote = c;
      }
    }
  }
  return state === 'value' && script && jsQuote !== '';
}

// True when the value went through esc() but not escJs(), directly or via a
// variable: HTML escaping alone lets a quote close the inline JS string.
function htmlEscapedOnly(node, scope, seen = new Set()) {
  switch (node.type) {
    case 'CallExpression': {
      if (node.callee.type === 'Identifier' && node.callee.name === 'esc' && isGlobalHelper(scope, 'esc')) return true;
      const method = memberName(node.callee);
      if ((method === 'replace' || method === 'replaceAll') && whitelistRegex(node.arguments[0])) return false;
      return PRESERVING_METHODS.has(method) && htmlEscapedOnly(node.callee.object, scope, seen);
    }
    case 'ConditionalExpression':
      return htmlEscapedOnly(node.consequent, scope, seen) || htmlEscapedOnly(node.alternate, scope, seen);
    case 'LogicalExpression':
      return htmlEscapedOnly(node.left, scope, seen) || htmlEscapedOnly(node.right, scope, seen);
    case 'BinaryExpression':
      return node.operator === '+' && concatParts(node).some(p => htmlEscapedOnly(p, scope, seen));
    case 'Identifier': {
      const binding = scope.lookup(node.name);
      if (!binding || seen.has(binding)) return false;
      seen.add(binding);
      return binding.values.some(v => v.node && htmlEscapedOnly(v.node, v.scope, seen));
    }
    default:
      return false;
  }
}

// ── Pass 3: find HTML sinks and report unsafe values ───────────────────
function snippet(node) {
  const text = node.__file.text.slice(node.start, node.end).replace(/\s+/g, ' ');
  return text.length > 70 ? text.slice(0, 67) + '...' : text;
}

function describe(leaf, scope) {
  if (leaf.type === 'Identifier') {
    const binding = scope.lookup(leaf.name);
    if (binding && binding.why) return '`' + leaf.name + '` is ' + binding.why;
    if (!binding) return '`' + leaf.name + '` is a global';
  }
  return '`' + snippet(leaf) + '`';
}

function checkFile(file, ast, findings) {
  const seen = new Set();
  function report(leaf, scope, message) {
    const key = leaf.start + ':' + leaf.end;
    if (seen.has(key)) return;
    seen.add(key);
    findings.push({file, line: leaf.loc.start.line, column: leaf.loc.start.column + 1,
      message: message || ('unescaped value in HTML: ' + describe(leaf, scope))});
  }
  function checkValue(node, scope) {
    for (const leaf of unsafeLeaves(node, scope)) report(leaf, scope);
  }
  function checkHtmlExpression(node, scope) {
    const parts = node.type === 'TemplateLiteral'
      ? node.quasis.flatMap((q, i) => i < node.expressions.length ? [q, node.expressions[i]] : [q])
      : concatParts(node);
    let prefix = '';
    for (const part of parts) {
      if (part.type === 'TemplateElement') { prefix += part.value.cooked || ''; continue; }
      if (isStringLiteral(part)) { prefix += part.value; continue; }
      if (!isAnnotated(part) && inlineScriptString(prefix) && htmlEscapedOnly(part, scope)) {
        report(part, scope, 'esc() inside an inline JavaScript string, use escJs(): `' + snippet(part) + '`');
      } else {
        checkValue(part, scope);
      }
      prefix += 'x';
    }
  }
  function walk(node, scope, parent, fnName) {
    if (isFunction(node)) {
      scope = functionScopes.get(node);
      fnName = node.id ? node.id.name : (parent && parent.type === 'VariableDeclarator' && parent.id.type === 'Identifier' ? parent.id.name : '');
    }
    switch (node.type) {
      case 'AssignmentExpression': {
        const prop = memberName(node.left);
        if (prop && HTML_PROPS.has(prop)) checkValue(node.right, scope);
        else if (node.left.type === 'Identifier' && /html/i.test(node.left.name)) checkValue(node.right, scope);
        break;
      }
      case 'VariableDeclarator':
        if (node.id.type === 'Identifier' && /html/i.test(node.id.name) && node.init) checkValue(node.init, scope);
        break;
      case 'CallExpression': {
        const method = memberName(node.callee);
        if (method && Object.prototype.hasOwnProperty.call(HTML_METHODS, method)) {
          const isDocWrite = method === 'write' || method === 'writeln';
          if (!isDocWrite || /document$/.test(snippet(node.callee.object))) {
            const arg = node.arguments[HTML_METHODS[method]];
            if (arg) checkValue(arg, scope);
          }
        } else if ((method === 'push' || method === 'unshift') && /html/i.test(snippet(node.callee.object))) {
          node.arguments.forEach(a => checkValue(a, scope));
        }
        break;
      }
      case 'ReturnStatement':
        if (node.argument && /html$/i.test(fnName || '')) checkValue(node.argument, scope);
        break;
      case 'TemplateLiteral':
        if (parent && parent.type !== 'TaggedTemplateExpression' && isHtmlExpression(node)) checkHtmlExpression(node, scope);
        break;
      case 'BinaryExpression':
        if (node.operator === '+' && !(parent && parent.type === 'BinaryExpression' && parent.operator === '+') && isHtmlExpression(node)) {
          checkHtmlExpression(node, scope);
        }
        break;
    }
    for (const child of children(node)) walk(child, scope, node, fnName);
  }
  walk(ast, globalScope, null, '');
}

function annotatedStarts(text, comments) {
  const starts = new Set();
  for (const comment of comments) {
    if (comment.type !== 'Block' || !/^\s*safe-html\b/.test(comment.value)) continue;
    let i = comment.end;
    while (i < text.length && /[\s(]/.test(text[i])) i++;
    starts.add(i);
  }
  return starts;
}

// Analyses scripts that share one global scope (as the SPA's do) and returns
// every unescaped interpolation as {file, line, column, message}.
function analyze(sources) {
  allBindings = [];
  functionScopes = new Map();
  functionReturns = new Map();
  declaredFunctions = new Map();
  globalScope = new Scope(null, null);
  const parsed = sources.map(({file, text}) => {
    const comments = [];
    const ast = acorn.parse(text, {ecmaVersion: 'latest', sourceType: 'script', locations: true, onComment: comments});
    tagFile(ast, {file, text, annotated: annotatedStarts(text, comments)});
    return {file, ast};
  });
  for (const p of parsed) declarePass(p.ast, globalScope, null, []);
  for (const p of parsed) assignPass(p.ast, globalScope);
  solve();
  const findings = [];
  for (const p of parsed) checkFile(p.file, p.ast, findings);
  return findings;
}

function tagFile(node, info) {
  node.__file = info;
  for (const child of children(node)) tagFile(child, info);
}

function main() {
  const args = process.argv.slice(2);
  const listAll = args.includes('--all');
  const only = args.filter(a => !a.startsWith('--')).map(a => path.basename(a));
  const files = fs.readdirSync(STATIC_DIR).filter(f => /^app(-[\w-]+)?\.js$/.test(f)).sort();
  const findings = analyze(files.map(file => ({file, text: fs.readFileSync(path.join(STATIC_DIR, file), 'utf8')})));
  const byFile = new Map();
  for (const f of findings) byFile.set(f.file, (byFile.get(f.file) || 0) + 1);

  const shown = findings.filter(f => listAll ? true : only.length ? only.includes(f.file) : ENFORCED.has(f.file));
  for (const f of shown) console.log(`app/web/static/${f.file}:${f.line}:${f.column}: ${f.message}`);
  if (only.length || listAll) {
    console.log(`${shown.length} finding(s)`);
    process.exit(shown.length ? 1 : 0);
  }
  const pending = files.filter(f => !ENFORCED.has(f) && byFile.get(f));
  if (pending.length) {
    console.log('HTML escaping not yet enforced: ' + pending.map(f => f + ' (' + byFile.get(f) + ')').join(', '));
  }
  if (shown.length) {
    console.error(`${shown.length} unescaped HTML interpolation(s). Wrap text in esc() and numbers in Number().`);
    process.exit(1);
  }
  console.log('HTML escaping check passed for ' + [...ENFORCED].sort().join(', '));
}

module.exports = {analyze, main};
if (require.main === module) main();
