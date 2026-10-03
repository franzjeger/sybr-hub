'use strict';
// Lints the browser scripts under app/web/static (not vendor/). The rules are
// the ones that find defects in a codebase of classic scripts sharing one
// global scope; style is left alone. See scripts/js-globals.cjs for how the
// cross-file globals are worked out.
const globals = require('globals');
const {declarationsByFile, globalsFor} = require('./scripts/js-globals.cjs');

// Loaded by index.html from vendor/ (and guacamole.min.js) into the same scope.
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
  'no-undef': 'error',
  // builtinGlobals also reports a top-level declaration that collides with a
  // name another script (or the browser) already declares.
  'no-redeclare': ['error', {builtinGlobals: true}],
  'no-restricted-globals': ['error', ...CONFUSING_GLOBALS],
  // Top-level names are used from other files and from markup, so only local
  // variables are checked.
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

const byFile = declarationsByFile();
const shared = Object.keys(byFile).map(file => ({
  files: ['app/web/static/' + file],
  languageOptions: {globals: {...browser, ...globalsFor(file, byFile)}},
}));

module.exports = [
  {
    ignores: ['app/web/static/vendor/**', 'app/web/static/guacamole.min.js'],
  },
  {
    files: ['app/web/static/*.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'script',
      globals: browser,
    },
    linterOptions: {reportUnusedDisableDirectives: 'error'},
    rules,
  },
  ...shared,
  {
    files: ['app/web/static/sw.js'],
    languageOptions: {globals: {...globals.serviceworker}},
  },
];
