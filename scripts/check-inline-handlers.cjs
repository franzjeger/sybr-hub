'use strict';
// The application CSP has no script-src-attr 'unsafe-inline', so an inline
// event handler (onclick="…") in index.html or in markup a script builds is
// blocked by the browser: the control silently does nothing. Controls name a
// registered handler in a data attribute instead (see app/web/static/app-handlers.js). This check fails on:
//
//   - an on*= attribute in a static HTML file or in a string a script builds
//     markup from, setAttribute('on…'), or a javascript: URL;
//   - data-<event>-handler for an event type the dispatcher does not listen to,
//     or with a name that is not a literal;
//   - a handler name used in markup that no registerUiHandlers() call defines,
//     or one that is registered and never used;
//   - a registerUiHandlers() call that is not a top-level call with an object
//     literal of named function expressions, or a name registered twice.
//
//   node scripts/check-inline-handlers.cjs
const fs = require('node:fs');
const path = require('node:path');
const acorn = require('acorn');

const STATIC_DIR = path.join(__dirname, '..', 'app', 'web', 'static');
const THIRD_PARTY = new Set(['guacamole.min.js']);

const INLINE_ATTRIBUTE = /(?:^|[\s"'\/])(on[a-z]+)\s*=/gi;
const JAVASCRIPT_URL = /(?:href|src|action)\s*=\s*\\?["']?\s*javascript:/i;
const HANDLER_ATTRIBUTE = /data-([a-z]+)-handler\s*=\s*(\\?["'])?([A-Za-z0-9_$]*)/g;

function children(node) {
  const out = [];
  for (const key of Object.keys(node)) {
    if (key === 'type' || key === 'start' || key === 'end' || key === 'loc') continue;
    const value = node[key];
    if (Array.isArray(value)) value.forEach(v => v && typeof v.type === 'string' && out.push(v));
    else if (value && typeof value.type === 'string') out.push(value);
  }
  return out;
}

function lineOf(text, index) {
  return text.slice(0, index).split('\n').length;
}

// The event types the dispatcher in app-handlers.js listens to.
function dispatchedEvents() {
  const text = fs.readFileSync(path.join(STATIC_DIR, 'app-handlers.js'), 'utf8');
  const match = /var UI_HANDLER_EVENTS = Object\.freeze\(\[([^\]]*)\]\)/.exec(text);
  if (!match) throw new Error('UI_HANDLER_EVENTS is missing from app-handlers.js');
  return new Set([...match[1].matchAll(/'([a-z]+)'/g)].map(m => m[1]));
}

function main() {
  const problems = [];
  const used = new Map();        // name -> first location
  const registered = new Map();  // name -> location
  const events = dispatchedEvents();
  const report = (where, message) => problems.push(`${where}: ${message}`);
  const use = (name, where) => { if (!used.has(name)) used.set(name, where); };

  function scanMarkup(fragment, where, {dynamicTail}) {
    for (const match of fragment.matchAll(INLINE_ATTRIBUTE)) {
      report(where, `inline event handler attribute ${match[1]}=; use data-<event>-handler and registerUiHandlers()`);
    }
    if (JAVASCRIPT_URL.test(fragment)) report(where, 'javascript: URL; use href="#" with a data-click-handler');
    for (const match of fragment.matchAll(HANDLER_ATTRIBUTE)) {
      const [, type, quote, name] = match;
      if (!events.has(type)) report(where, `data-${type}-handler: the dispatcher does not listen to "${type}"`);
      const atEnd = match.index + match[0].length === fragment.length;
      if (!name) {
        if (dynamicTail && atEnd) report(where, `data-${type}-handler name must be a literal, not an interpolated value`);
        else report(where, `data-${type}-handler without a handler name`);
        continue;
      }
      if (!quote) report(where, `data-${type}-handler="${name}" must be quoted`);
      if (dynamicTail && atEnd) report(where, `data-${type}-handler name must be a literal, not built from a value`);
      use(name, where);
    }
  }

  // Static HTML.
  for (const file of fs.readdirSync(STATIC_DIR).filter(f => f.endsWith('.html')).sort()) {
    const text = fs.readFileSync(path.join(STATIC_DIR, file), 'utf8');
    for (const tag of text.matchAll(/<[a-zA-Z][^>]*>/g)) {
      scanMarkup(tag[0], `app/web/static/${file}:${lineOf(text, tag.index)}`, {dynamicTail: false});
    }
  }

  // Scripts.
  for (const file of fs.readdirSync(STATIC_DIR).filter(f => f.endsWith('.js') && !THIRD_PARTY.has(f)).sort()) {
    const text = fs.readFileSync(path.join(STATIC_DIR, file), 'utf8');
    const ast = acorn.parse(text, {ecmaVersion: 'latest', sourceType: 'script', locations: true});
    const where = node => `app/web/static/${file}:${node.loc.start.line}`;

    for (const statement of ast.body) {
      const call = statement.type === 'ExpressionStatement' ? statement.expression : null;
      if (!call || call.type !== 'CallExpression' || call.callee.type !== 'Identifier' || call.callee.name !== 'registerUiHandlers') continue;
      call.__topLevel = true;
      const map = call.arguments[0];
      if (call.arguments.length !== 1 || !map || map.type !== 'ObjectExpression') {
        report(where(call), 'registerUiHandlers() takes one object literal');
        continue;
      }
      for (const property of map.properties) {
        const key = property.type === 'Property' && !property.computed
          ? (property.key.type === 'Identifier' ? property.key.name : property.key.value) : null;
        if (key === null || typeof key !== 'string') { report(where(property), 'handler names must be plain keys'); continue; }
        const value = property.value;
        if (property.kind !== 'init' || !['FunctionExpression', 'ArrowFunctionExpression'].includes(value.type)) {
          report(where(property), `handler "${key}" must be a function expression written in the map`);
        }
        if (registered.has(key)) report(where(property), `handler "${key}" is already registered at ${registered.get(key)}`);
        else registered.set(key, where(property));
      }
    }

    (function walk(node, parent) {
      if (node.type === 'CallExpression' && node.callee.type === 'Identifier' && node.callee.name === 'registerUiHandlers' && !node.__topLevel) {
        report(where(node), 'registerUiHandlers() must be called at the top level of a script, while it loads');
      }
      if (node.type === 'Literal' && typeof node.value === 'string') {
        scanMarkup(node.value, where(node), {dynamicTail: parent && parent.type === 'BinaryExpression' && parent.left === node});
      } else if (node.type === 'TemplateLiteral') {
        node.quasis.forEach((quasi, i) => {
          scanMarkup(quasi.value.cooked || '', where(quasi), {dynamicTail: i < node.expressions.length});
        });
      } else if (node.type === 'CallExpression' && node.callee.type === 'MemberExpression' &&
          !node.callee.computed && node.callee.property.name === 'setAttribute') {
        const [name, value] = node.arguments;
        if (name && name.type === 'Literal' && typeof name.value === 'string') {
          if (/^on/i.test(name.value)) report(where(node), `setAttribute('${name.value}', …) is an inline event handler`);
          const handler = /^data-([a-z]+)-handler$/.exec(name.value);
          if (handler) {
            if (value && value.type === 'Literal' && typeof value.value === 'string') use(value.value, where(node));
            else report(where(node), `${name.value} must be set to a literal handler name`);
          }
        }
      } else if (node.type === 'AssignmentExpression' && node.left.type === 'MemberExpression' &&
          node.left.object.type === 'MemberExpression' && !node.left.object.computed &&
          node.left.object.property.name === 'dataset' && !node.left.computed &&
          /^[a-z]+Handler$/.test(node.left.property.name)) {
        if (node.right.type === 'Literal' && typeof node.right.value === 'string') use(node.right.value, where(node));
        else report(where(node), `dataset.${node.left.property.name} must be set to a literal handler name`);
      }
      for (const child of children(node)) walk(child, node);
    })(ast, null);
  }

  for (const [name, where] of used) {
    if (!registered.has(name)) report(where, `no registerUiHandlers() call defines handler "${name}"`);
  }
  for (const [name, where] of registered) {
    if (!used.has(name)) report(where, `handler "${name}" is registered but no markup uses it`);
  }

  for (const problem of problems) console.error(problem);
  if (problems.length) {
    console.error(`${problems.length} inline-handler problem(s). The CSP blocks inline handlers; see app/web/static/app-handlers.js.`);
    process.exit(1);
  }
  console.log(`No inline event handlers; ${registered.size} registered UI handlers, all used`);
}

module.exports = {main};
if (require.main === module) main();
