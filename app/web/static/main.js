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
//        app-forms.js     protect edited fields during asynchronous loads
//        app-navigation.js, app-audit-presentation.js: composed interfaces
//        app-shell-status.js: connection status in the shell
//   3. Shell and feature modules form an acyclic graph. Shared formatters and
//      presentation helpers belong in services. Features call the shell through
//      app-navigation.js, and the audit calls the customer presenter through
//      app-audit-presentation.js. Both interfaces are wired explicitly below,
//      before authentication or view events. The module check rejects cycles.
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
import './app-forms.js';
import './app-shell-status.js';
import {showView, showNetworkTab, syncRoute, checkAuth, passwordMeetsRule, applyWriteCapability, applyFeatureVisibility, renderToolCustomerPickers, toolCustomerId, _syncConnChip, setVpnTunnelUp, toggleCommandPalette} from './app.js';
import {configureNavigation} from './app-navigation.js';
import {configureAuditPresentation} from './app-audit-presentation.js';
import './app-infra.js';
import {dashLoadAlerts, dashLoadArchive} from './app-dashboard.js';
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
import {openAdmin} from './app-settings.js';
import './app-network.js';
import {overviewSelectCustomer, loadCustomers} from './app-customers.js';
import './app-findings.js';
import {openCustomerPage, custAuditTabOpen, custPageAuditFinished, custReportFromRun, custSyncReportButton, setCustReportRun, setCustRuns} from './app-customer-detail.js';
import {renderAiQuickPrompts} from './app-chrome.js';
import './app-markup-handlers.js';

// Start-up: the strings first, then who is signed in. Run once per page
// load; checkAuth runs again after a sign-in, from the login form.
configureAuditPresentation({custAuditTabOpen, custPageAuditFinished, custReportFromRun, custSyncReportButton, setCustReportRun, setCustRuns});
configureNavigation({dashLoadAlerts, overviewSelectCustomer, loadCustomers, dashLoadArchive, openAdmin, openCustomerPage, showView, showNetworkTab, syncRoute, checkAuth, passwordMeetsRule, applyWriteCapability, applyFeatureVisibility, renderToolCustomerPickers, toolCustomerId, _syncConnChip, setVpnTunnelUp, toggleCommandPalette});
loadI18n().then(() => { renderAiQuickPrompts(); checkAuth(); });
