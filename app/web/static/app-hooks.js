// ═══════════════════════════════════════════════════════════════════
// HOOKS: where a script says what to do when something happens elsewhere
// ═══════════════════════════════════════════════════════════════════

// Registries other scripts add to while they load. They hold nothing but the
// functions registered with them, so a script can register whatever has or
// has not loaded before it.

// A script that owns a view says what to do when it opens with
// onViewShown(name, fn), instead of wrapping showView. The wrappers stacked:
// each called the one before it in load order, and a throw in one cut off
// every wrapper after it.
var _viewOpeners = {};

function onViewShown(name, fn) {
  (_viewOpeners[name] = _viewOpeners[name] || []).push(fn);
}

function viewShown(name) {
  (_viewOpeners[name] || []).forEach(function(fn) {
    try { fn(); } catch (e) { console.error('Opening view ' + name + ' failed:', e); }
  });
}

// What other scripts do once someone has signed in (app-chrome.js: the tour).
var _signedInHooks = [];

function onSignedIn(fn) {
  _signedInHooks.push(fn);
}

function signedIn() {
  _signedInHooks.forEach(function(fn) { fn(); });
}

// What other scripts do when the login screen comes up (app-chrome.js: take
// the tour down).
var _loginViewHooks = [];

function onLoginViewShown(fn) {
  _loginViewHooks.push(fn);
}

function loginViewShown() {
  _loginViewHooks.forEach(function(fn) { fn(); });
}

// A tool that acts on one customer (its customer bar, [data-tool-customer])
// says how to reload when the bar's choice changes.
var _toolReloaders = {};

function registerToolCustomer(tool, reload) { _toolReloaders[tool] = reload; }

function reloadToolCustomer(tool) {
  var reload = _toolReloaders[tool];
  if (reload) reload();
}
