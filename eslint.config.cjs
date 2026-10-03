'use strict';
// Lints the browser code under app/web/static (not vendor/). The interface is
// a graph of ES modules (main.js is the entry); no-undef is what catches a
// name used without an import. A few files stay classic scripts: theme-init.js
// (runs in <head> before the first paint) and sw.js (the service worker).
// scripts/js-modules.cjs checks what ESLint does not: that every import names
// a module and an export that exist, and the layering in main.js.
const globals = require('globals');

// Loaded by index.html from vendor/ (and guacamole.min.js) as classic scripts
// before the entry module; modules read them as globals.
const THIRD_PARTY_GLOBALS = {
  Chart: 'readonly',
  DOMPurify: 'readonly',
  FitAddon: 'readonly',
  Guacamole: 'readonly',
  Terminal: 'readonly',
  marked: 'readonly',
};

// Browser globals whose names are also ordinary variable names. A function
// that reads `event` or `name` without declaring it compiles, runs, and reads
// window.event or window.name instead of what the author meant.
const CONFUSING_GLOBALS = ['event', 'name', 'status', 'length', 'top', 'parent', 'closed', 'opener', 'origin', 'external'];

const rules = {
  // A name used without being declared or imported.
  'no-undef': 'error',
  // An imported binding is read-only; a module changes another's state
  // through the setter it exports.
  'no-import-assign': 'error',
  // In a classic script, builtinGlobals also reports a top-level declaration
  // that collides with a name the browser already declares.
  'no-redeclare': ['error', {builtinGlobals: true}],
  'no-restricted-globals': ['error', ...CONFUSING_GLOBALS],
  // A module's top-level names are its own: one nothing reads or exports is
  // dead code.
  'no-unused-vars': ['warn', {vars: 'local', args: 'none', caughtErrors: 'none'}],
  // Free today: every loose comparison in the codebase is `== null`, which
  // means null-or-undefined on purpose. Keep it that way.
  eqeqeq: ['error', 'always', {null: 'ignore'}],
  'no-global-assign': 'error',
  'no-func-assign': 'error',
  'no-const-assign': 'error',
  'no-class-assign': 'error',
  'no-dupe-keys': 'error',
  'no-dupe-args': 'error',
  'no-dupe-class-members': 'error',
  'no-dupe-else-if': 'error',
  'no-duplicate-case': 'error',
  'no-self-assign': 'error',
  'no-self-compare': 'error',
  'no-unreachable': 'error',
  'no-unsafe-finally': 'error',
  'no-unsafe-negation': 'error',
  'no-unsafe-optional-chaining': 'error',
  'no-constant-binary-expression': 'error',
  'no-cond-assign': ['error', 'except-parens'],
  'no-compare-neg-zero': 'error',
  'no-loss-of-precision': 'error',
  'no-sparse-arrays': 'error',
  'no-template-curly-in-string': 'error',
  'no-unexpected-multiline': 'error',
  'no-obj-calls': 'error',
  'no-invalid-regexp': 'error',
  'no-empty-character-class': 'error',
  'no-async-promise-executor': 'error',
  'no-setter-return': 'error',
  'getter-return': 'error',
  'use-isnan': 'error',
  'valid-typeof': 'error',
  'no-shadow-restricted-names': 'error',
  'no-delete-var': 'error',
  'no-with': 'error',
  'no-eval': 'error',
  'no-implied-eval': 'error',
  'no-new-func': 'error',
  'no-script-url': 'error',
};

const browser = {...globals.browser, ...THIRD_PARTY_GLOBALS};

// The scripts that are not modules.
const CLASSIC = ['app/web/static/theme-init.js', 'app/web/static/sw.js'];

module.exports = [
  {
    ignores: ['app/web/static/vendor/**', 'app/web/static/guacamole.min.js'],
  },
  {
    files: ['app/web/static/*.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: browser,
    },
    linterOptions: {reportUnusedDisableDirectives: 'error'},
    rules,
  },
  {
    files: CLASSIC,
    languageOptions: {sourceType: 'script'},
  },
  {
    files: ['app/web/static/sw.js'],
    languageOptions: {globals: {...globals.serviceworker}},
  },
];
