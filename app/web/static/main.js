// ═══════════════════════════════════════════════════════════════════
// ENTRY: the one script index.html loads
// ═══════════════════════════════════════════════════════════════════
//
// The interface is a graph of ES modules. Nothing is shared through window:
// a module imports what it uses from the module that declares it. index.html
// loads this module and nothing else of ours (theme-init.js runs before the
// first paint and stays a classic script; the vendored libraries in vendor/
// and guacamole.min.js are classic scripts loaded before it and are read as
// the globals they define: Chart, DOMPurify, FitAddon, Guacamole, Terminal,
// marked).
//
// Layers, lowest first. A module imports only from its own layer or below,
// and the two lower layers have no cycles (scripts/js-modules.cjs checks
// both):
//
//   1. Leaves, which import nothing:
//        app-esc.js       esc()
//        app-i18n.js      ui_i18n.json, t(), the interface language
//        app-icons.js     icon(), hydrateIcons()
//        app-handlers.js  registerUiHandlers() and the event dispatcher
//        app-hooks.js     onViewShown(), onSignedIn(), onLoginViewShown(),
//                         registerToolCustomer(): registries a feature adds
//                         to while it loads
//        app-state.js     the signed-in account and what it may reach, this
//                         tab's customer, the customer page, the shared
//                         customer lists; each with its setter
//   2. Services, which import only leaves and each other:
//        app-format.js    figures, run names, dates and sizes
//        app-ui.js        toasts, confirm dialogs, the login screen,
//                         skeletons, sortable tables, the report window
//        app-api.js       apiFetch()
//   3. The shell and the features: app.js (views and the address bar,
//      signing in, the command palette, the menus) and app-*.js. They call
//      each other, so they import each other: showView opens a customer's
//      page and the customer page calls showView. Those cycles are allowed
//      because the code a module runs while it loads touches nothing from
//      this layer: it declares functions and state, registers its handlers
//      and hooks (layer 1) and installs listeners. Calls between features
//      happen later, from events and from start-up below, when every
//      module has run. scripts/js-modules.cjs fails on a module whose
//      top-level code reads anything imported from its own cycle.
//   4. app-markup-handlers.js: the handlers index.html's own controls name.
//      Nothing imports it.
//   5. This module.
//
// The imports below are in the order the classic scripts loaded, so the
// side effects a module has while it loads (handlers, hooks, listeners)
// happen in the order they always did.
import './app-esc.js';
import {loadI18n} from './app-i18n.js';
import './app-icons.js';
import './app-handlers.js';
import './app-hooks.js';
import './app-state.js';
import './app-format.js';
import './app-ui.js';
import './app-api.js';
import {checkAuth} from './app.js';
import './app-infra.js';
import './app-dashboard.js';
import './app-also.js';
import './app-tailscale.js';
import './app-tls.js';
import './app-integrations.js';
import './app-policy-deploy.js';
import './app-baseline-deploy.js';
import './app-policy-overview.js';
import './app-assessments.js';
import './app-setup.js';
import './app-audit.js';
import './app-settings.js';
import './app-network.js';
import './app-customers.js';
import './app-findings.js';
import './app-customer-detail.js';
import {renderAiQuickPrompts} from './app-chrome.js';
import './app-markup-handlers.js';

// Start-up: the strings first, then who is signed in. Run once per page
// load; checkAuth runs again after a sign-in, from the login form.
loadI18n().then(() => { renderAiQuickPrompts(); checkAuth(); });
