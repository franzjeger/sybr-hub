
// ── Inline SVG icon helper ───────────────────────────────────────────────────
function icon(name, size) {
  var s = Number(size) || 16;
  var paths = {
    document:  'M6 2a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7.414A2 2 0 0 0 15.414 6L12 2.586A2 2 0 0 0 10.586 2H6zm5 1.414L14.586 7H12a1 1 0 0 1-1-1V3.414zM7 10h6v1.5H7V10zm0 3h4v1.5H7V13z',
    refresh:   'M17.65 6.35A7.958 7.958 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z',
    download:  'M12 16l-5-5 1.41-1.41L11 12.17V4h2v8.17l2.59-2.58L17 11l-5 5zM5 18v2h14v-2H5z',
    warning:   'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z',
    check:     'M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z',
    x:         'M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z',
    lock:      'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1s3.1 1.39 3.1 3.1v2z',
    globe:     'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z',
    server:    'M20 3H4c-1.1 0-2 .9-2 2v4c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 6H4V5h16v4zm0 4H4c-1.1 0-2 .9-2 2v4c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2v-4c0-1.1-.9-2-2-2zm0 6H4v-4h16v4zM6 7.5a1.5 1.5 0 1 0 3 0 1.5 1.5 0 0 0-3 0zm0 9a1.5 1.5 0 1 0 3 0 1.5 1.5 0 0 0-3 0z',
    shield:    'M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z',
    // Used by the command palette and the navigation menus. Emoji were used
    // here once; they render in the font's own colours and at the font's own
    // weight, so a single 🔒 beside a row of line icons is the one thing on
    // the screen the design language does not reach.
    grid:      'M3 3h8v8H3V3zm10 0h8v8h-8V3zM3 13h8v8H3v-8zm10 0h8v8h-8v-8z',
    users:     'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
    cloud:     'M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96z',
    calendar:  'M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z',
    monitor:   'M20 18c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2H4c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2H0v2h24v-2h-4zM4 6h16v10H4V6z',
    link:      'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
    gear:      'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 0 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
    sparkle:   'M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4L12 2z',
    plug:      'M16 7V3h-2v4h-4V3H8v4H6v6l4 4v4h4v-4l4-4V7h-2z',
    palette:   'M12 3a9 9 0 0 0 0 18c.83 0 1.5-.67 1.5-1.5 0-.39-.15-.74-.39-1.01a1.49 1.49 0 0 1 1.14-2.49H16a5 5 0 0 0 5-5c0-4.42-4.03-8-9-8zm-5.5 9a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zm3-4a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zm5 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zm3 4a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3z',
    play:      'M8 5v14l11-7L8 5z',
    chart:     'M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z',
    building:  'M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z',
    clock:     'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67V7z',
    search:    'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
    // Added for the files view, which carried 📂 📁 🗂 🔐 🔓 as emoji.
    folder:    'M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z',
    key:       'M12.65 10A5.99 5.99 0 0 0 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6a5.99 5.99 0 0 0 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
    unlock:    'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6h1.9c0-1.71 1.39-3.1 3.1-3.1s3.1 1.39 3.1 3.1v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  };
  var d = paths[name];
  if (!d) return '';
  return '<span class="ic" style="width:'+s+'px;height:'+s+'px;">'
    + '<svg width="'+s+'" height="'+s+'" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">'
    + '<path d="'+d+'"/></svg></span>';
}

// Sets a button's label without discarding the icon in front of it. Buttons
// that carry one are markup of the form
//   <button><span class="ic">…svg…</span><span data-i18n="key">Label</span></button>
// and btn.textContent = '…' flattens both spans into a bare string, so the
// icon disappeared the first time the button changed state and never came
// back. Writing to the label span leaves the icon alone.
function setButtonLabel(btn, text) {
  if (!btn) return;
  var label = btn.querySelector('[data-i18n]');
  if (label) label.textContent = text;
  else btn.textContent = text;
}

// ── Event handlers without inline JavaScript ─────────────────────────────────
// The CSP has script-src-attr 'none': the browser runs no inline event-handler
// attribute (onclick and the rest). A control names its handler in a data
// attribute instead:
//
//   <button data-click-handler="showView" data-view="audit">…</button>
//   <select data-change-handler="setLanguage">…</select>
//
// One listener per event type, on document in the capture phase, looks the
// name up in the map below and calls it as handler(element, event). Arguments
// come from the element's own data-* attributes; an attribute is never
// evaluated, and only names registered here can be called — this is not a way
// to reach any global function from markup.
//
// Each script registers the handlers its own markup uses with
// registerUiHandlers({...}), once, at load. A name can be registered only once
// and the map is frozen when the document has loaded.
//
// Dispatch mirrors how inline handlers bubbled: from the event target outwards,
// every element with a handler for this event type runs it, until one calls
// event.stopPropagation(). Because it runs in the capture phase, that call also
// stops the document-level listeners (click-outside-to-close and the like),
// just as stopPropagation() in an inline handler did. It also stops listeners
// added with addEventListener on elements *inside* the one whose handler made
// the call, which an inline handler on that element did not: inside a
// container that stops clicks (the shared stopPropagation handler on a dialog),
// give controls data-*-handler attributes rather than their own listeners.
var UI_HANDLER_EVENTS = Object.freeze(['click', 'dblclick', 'input', 'change', 'keydown', 'submit', 'dragover', 'dragleave', 'drop']);
var _uiHandlers = Object.create(null);

function registerUiHandlers(handlers) {
  Object.keys(handlers).forEach(function(name) {
    if (Object.isFrozen(_uiHandlers)) throw new Error('UI handler registered after load: ' + name);
    if (name in _uiHandlers) throw new Error('UI handler registered twice: ' + name);
    if (typeof handlers[name] !== 'function') throw new TypeError('UI handler is not a function: ' + name);
    _uiHandlers[name] = handlers[name];
  });
}

function _dispatchUiEvent(event) {
  var attribute = 'data-' + event.type + '-handler';
  // The elements with a handler, innermost first, fixed before any handler runs
  // as the browser fixes an event's path: a handler that removes part of the
  // page does not stop the ancestors that were there from getting the event.
  var path = [];
  var node = event.target;
  if (node && node.nodeType !== 1) node = node.parentElement;
  for (; node && node.nodeType === 1; node = node.parentElement) {
    // A disabled control never ran its inline handler either.
    if (node.hasAttribute(attribute) && !node.matches(':disabled')) path.push(node);
  }
  for (var i = 0; i < path.length; i++) {
    var name = path[i].getAttribute(attribute);
    var handler = _uiHandlers[name];
    if (!handler) { console.error('No UI handler registered as "' + name + '" (' + attribute + ')'); continue; }
    // <a href="#"> with a click handler is a button that looks like a link.
    // Following the "#" would change the route; inline handlers ended in
    // `return false` for the same reason.
    if (event.type === 'click' && path[i].tagName === 'A' && path[i].getAttribute('href') === '#') event.preventDefault();
    handler(path[i], event);
    if (event.cancelBubble) break;
  }
}

UI_HANDLER_EVENTS.forEach(function(type) { document.addEventListener(type, _dispatchUiEvent, true); });
document.addEventListener('DOMContentLoaded', function() { Object.freeze(_uiHandlers); });

// Handlers shared by markup in several scripts.
registerUiHandlers({
  showView: function(el) { showView(el.dataset.view); },
  // data-target names an element by id.
  hideElement: function(el) { var target = document.getElementById(el.dataset.target); if (target) target.style.display = 'none'; },
  removeElement: function(el) { var target = document.getElementById(el.dataset.target); if (target) target.remove(); },
  // On a modal's backdrop: a click on the backdrop itself, not on the dialog.
  hideOnBackdrop: function(el, event) { if (event.target === el) el.style.display = 'none'; },
  removeOnBackdrop: function(el, event) { if (event.target === el) el.remove(); },
  // On a container whose clicks must not reach a clickable row or card behind it.
  stopPropagation: function(el, event) { event.stopPropagation(); },
});

// Handlers for the markup app.js builds: the command palette, toasts and Home.
registerUiHandlers({
  runCommandPaletteItem: function(el) {
    closeCommandPalette();
    window._cmdActions[Number(el.dataset.index)]();
  },
  dismissToast: function(el) { dismissToast(el.parentNode); },
  retryToast: function(el) { retryToast(el.closest('.toast')); },
  openTagEditor: function(el) { openTagEditor(el.dataset.customerId, JSON.parse(el.dataset.tags)); },
  checkPermissions: function() { checkPermissions(); },
  renewCreds: function() { renewCreds(); },
  toggleScopePanel: function() { toggleScopePanel(); },
  applyPreset: function() { applyPreset(); },
  saveCustomPreset: function() { saveCustomPreset(); },
  deleteCustomPreset: function() { deleteCustomPreset(); },
  scopeSelectAll: function() { scopeSelectAll(); },
  scopeDeselectAll: function() { scopeDeselectAll(); },
  toggleNotesCard: function() { toggleNotesCard(); },
  toggleActivityLog: function() { toggleActivityLog(); },
});

// Handlers for the static markup in index.html.
registerUiHandlers({
  // Arguments come from data-* attributes on the control.
  generateReport: function(el) { generateReport(el.dataset.format, el.dataset.reportType); },
  toggleIntegConfig: function(el) { toggleIntegConfig(el.dataset.config); },
  switchSettingsTab: function(el) { switchSettingsTab(el, el.dataset.tab); },
  switchNetSub: function(el) { switchNetSub(el, el.dataset.tab); },
  switchDashTab: function(el) { switchDashTab(el, el.dataset.tab); },
  switchDocsTab: function(el) {
    switchDocsTab(el, el.dataset.tab);
    if (el.dataset.tab === 'docs-repo') docsRepoLoad();
  },
  termChangeFontSize: function(el) { termChangeFontSize(Number(el.dataset.delta)); },
  resolveConfirm: function(el) { resolveConfirm(el.dataset.answer === 'true'); },
  uploadToITGlue: function(el) { uploadToITGlue(el); },
  uploadReportsToITGlue: function(el) { uploadReportsToITGlue(el); },
  dashToggleAutoRefresh: function(el) { dashToggleAutoRefresh(el); },
  scrollToTop: function() { window.scrollTo({top: 0, behavior: 'smooth'}); },
  // Menus that close themselves before acting.
  toggleAvatarMenu: function(el, event) { toggleAvatarMenu(event); },
  toggleActiveCustomerSwitcher: function(el, event) { toggleActiveCustomerSwitcher(event); },
  moreSheetShowView: function(el) { closeMoreSheet(); showView(el.dataset.view); },
  moreSheetOpenSettings: function() { closeMoreSheet(); openSettings(); },
  moreSheetLogout: function() { closeMoreSheet(); doLogout(); },
  avatarShowMfaSettings: function() { closeAvatarMenu(); showMfaSettings(); },
  avatarShowChangePassword: function() { closeAvatarMenu(); showChangePasswordModal(); },
  avatarOpenShortcuts: function() { closeAvatarMenu(); openShortcutsModal(); },
  avatarOpenSettings: function() { closeAvatarMenu(); openSettings(); },
  // Modal backdrops: only a click on the backdrop itself closes them.
  deactivateOnBackdrop: function(el, event) { if (event.target === el) el.classList.remove('active'); },
  cancelConfirmOnBackdrop: function(el, event) { if (event.target === el) resolveConfirm(false); },
  closeShortcutsModalOnBackdrop: function(el, event) { if (event.target === el) closeShortcutsModal(); },
  closePermissionsModalOnBackdrop: function(el, event) { if (event.target === el) closePermissionsModal(); },
  closeMoreSheetOnBackdrop: function(el, event) { if (event.target === el) closeMoreSheet(); },
  closeChangelogModalOnBackdrop: function(el, event) { if (event.target === el) closeChangelogModal(); },
  closeCommandPaletteOnBackdrop: function(el, event) { if (event.target === el) closeCommandPalette(); },
  closeSettingsOnBackdrop: function(el, event) { closeSettingsOnBackdrop(event); },
  // change / input
  alertSaveConfig: function() { alertSaveConfig(); },
  alertToggleMaster: function(el) { alertToggleMaster(el.checked); },
  hostsLoad: function() { hostsLoad(); },
  toggleLogTabVisibility: function() { toggleLogTabVisibility(); },
  toggleLogAutoRefresh: function() { toggleLogAutoRefresh(); },
  termModeChanged: function() { termModeChanged(); },
  setLanguage: function(el) { setLanguage(el.value); },
  liveSetInterval: function(el) { liveSetInterval(el.value); },
  claudeModeChanged: function() { claudeModeChanged(); },
  aiSelectCustomerFromDropdown: function(el) { aiSelectCustomerFromDropdown(el); },
  filterChangelog: function() { filterChangelog(); },
  customersFilter: function() { customersFilter(); },
  // keydown
  doSetupOnEnter: function(el, event) { if (event.key === 'Enter') doSetup(); },
  doLoginOnEnter: function(el, event) { if (event.key === 'Enter') doLogin(); },
  aiSendOnEnter: function(el, event) {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); aiSend(); }
  },
  // Plain calls.
  copyDeviceUrl: function() { copyDeviceUrl(); },
  closeReportViewer: function() { closeReportViewer(); },
  doSetup: function() { doSetup(); },
  doLogin: function() { doLogin(); },
  toggleMobileNav: function() { toggleMobileNav(); },
  openLatestReport: function() { openLatestReport(); },
  startAudit: function() { startAudit(); },
  // Verktøy holds documentation too, so it stays when the remote module is
  // off; its own click opens the first thing in it this account may use.
  openToolsDefault: function() { showView(canOpenView('hosts') ? 'hosts' : 'docs'); },
  toggleCommandPalette: function() { toggleCommandPalette(); },
  toggleNotifications: function() { toggleNotifications(); },
  markAllNotificationsRead: function() { markAllNotificationsRead(); },
  promptPwaInstall: function() { promptPwaInstall(); },
  toggleTheme: function() { toggleTheme(); },
  doLogout: function() { doLogout(); },
  openChangelogModal: function() { openChangelogModal(); },
  loadCustomerLicensesFromActive: function() { loadCustomerLicensesFromActive(); },
  dashExportCurrentTab: function() { dashExportCurrentTab(); },
  exportDashboardExcel: function() { exportDashboardExcel(); },
  copyOverviewToClipboard: function(el) { copyOverviewToClipboard(el); },
  generateQBR: function() { generateQBR(); },
  closeSettings: function() { closeSettings(); },
  closePermissionsModal: function() { closePermissionsModal(); },
  closeShortcutsModal: function() { closeShortcutsModal(); },
  closeChangelogModal: function() { closeChangelogModal(); },
  aiClearChat: function() { aiClearChat(); },
  aiSend: function() { aiSend(); },
  alertRunCheckNow: function() { alertRunCheckNow(); },
  alsoSaveConfig: function() { alsoSaveConfig(); },
  alsoSyncCustomers: function() { alsoSyncCustomers(); },
  alsoTestConnection: function() { alsoTestConnection(); },
  auditBack: function() { auditBack(); },
  backupEncryptionKey: function() { backupEncryptionKey(); },
  bulkDeleteCustomers: function() { bulkDeleteCustomers(); },
  bulkTagCustomers: function() { bulkTagCustomers(); },
  claudeCheckCli: function() { claudeCheckCli(); },
  claudeSaveSettings: function() { claudeSaveSettings(); },
  claudeTestConnection: function() { claudeTestConnection(); },
  clearBulkSelection: function() { clearBulkSelection(); },
  clearLogs: function() { clearLogs(); },
  confirmITGlueOrgPick: function() { confirmITGlueOrgPick(); },
  copyCode: function() { copyCode(); },
  copyEncryptionKey: function() { copyEncryptionKey(); },
  copyLogs: function() { copyLogs(); },
  createBackup: function() { createBackup(); },
  createUser: function() { createUser(); },
  dashUnifiRefresh: function() { dashUnifiRefresh(); },
  deleteSelectedRuns: function() { deleteSelectedRuns(); },
  executeITGlueUpload: function() { executeITGlueUpload(); },
  exportCSV: function() { exportCSV(); },
  exportCustomersJSON: function() { exportCustomersJSON(); },
  fgApiSave: function() { fgApiSave(); },
  fgApiTest: function() { fgApiTest(); },
  fgBootstrap: function() { fgBootstrap(); },
  fgDownloadCredentials: function() { fgDownloadCredentials(); },
  fgPollAll: function() { fgPollAll(); },
  gdapDiscoverCustomers: function() { gdapDiscoverCustomers(); },
  gdapImportSelected: function() { gdapImportSelected(); },
  gdapSaveConfig: function() { gdapSaveConfig(); },
  gdapTestConnection: function() { gdapTestConnection(); },
  hostsAdd: function() { hostsAdd(); },
  hostsHealthAll: function() { hostsHealthAll(); },
  itglueSyncAllDocumentation: function() { itglueSyncAllDocumentation(); },
  loadConfigBackups: function() { loadConfigBackups(); },
  loadFiles: function() { loadFiles(); },
  loadLogs: function() { loadLogs(); },
  migrateEncryption: function() { migrateEncryption(); },
  openITGlueImport: function() { openITGlueImport(); },
  openManualCustomer: function() { openManualCustomer(); },
  openMoreSheet: function() { openMoreSheet(); },
  openPrivateBrowser: function() { openPrivateBrowser(); },
  provisionStart: function() { provisionStart(); },
  resetAuditDir: function() { resetAuditDir(); },
  resetBrandColor: function() { resetBrandColor(); },
  restoreBackup: function() { restoreBackup(); },
  restoreEncryptionKey: function() { restoreEncryptionKey(); },
  runCmsScan: function() { runCmsScan(); },
  runComparison: function() { runComparison(); },
  runCredentialTest: function() { runCredentialTest(); },
  runDnsPentest: function() { runDnsPentest(); },
  runITGlueImport: function() { runITGlueImport(); },
  runNetworkQuickAudit: function() { runNetworkQuickAudit(); },
  runPentest: function() { runPentest(); },
  runSegTest: function() { runSegTest(); },
  runSmbEnum: function() { runSmbEnum(); },
  runSubnetScan: function() { runSubnetScan(); },
  runTakeoverCheck: function() { runTakeoverCheck(); },
  runTlsAudit: function() { runTlsAudit(); },
  saveEmailSettings: function() { saveEmailSettings(); },
  saveITGlueSettings: function() { saveITGlueSettings(); },
  saveSettings: function() { saveSettings(); },
  saveWebhookSettings: function() { saveWebhookSettings(); },
  showAddUserForm: function() { showAddUserForm(); },
  showRestoreKeyInput: function() { showRestoreKeyInput(); },
  sshShowExec: function() { sshShowExec(); },
  sshShowKeys: function() { sshShowKeys(); },
  startSetup: function() { startSetup(); },
  submitManualCustomer: function() { submitManualCustomer(); },
  taskSchedRefresh: function() { taskSchedRefresh(); },
  termConnect: function() { termConnect(); },
  termDisconnect: function() { termDisconnect(); },
  testAutotask: function() { testAutotask(); },
  testMyITProcess: function() { testMyITProcess(); },
  testEmail: function() { testEmail(); },
  testITGlue: function() { testITGlue(); },
  testWebhook: function() { testWebhook(); },
  tsSaveConfig: function() { tsSaveConfig(); },
  tsTestConnection: function() { tsTestConnection(); },
  unifiSmAuth: function() { unifiSmAuth(); },
  unifiSmLoadCoverage: function() { unifiSmLoadCoverage(); },
  unifiSmLoadSites: function() { unifiSmLoadSites(); },
  unifiSmSave: function() { unifiSmSave(); },
  unifiSmSaveController: function() { unifiSmSaveController(); },
  unifiSmTestController: function() { unifiSmTestController(); },
  uniwebSaveConfig: function() { uniwebSaveConfig(); },
  uniwebSync: function() { uniwebSync(); },
  uploadLogo: function() { uploadLogo(); },
  vpnLoadProfiles: function() { vpnLoadProfiles(); },
  vpnShowCreate: function() { vpnShowCreate(); },
  vpnShowImport: function() { vpnShowImport(); },
});

// ── Reusable sortable table utility ──────────────────────────────────────────
function makeSortable(tableEl) {
  if (!tableEl) return;
  var thead = tableEl.querySelector('thead');
  if (!thead) return;
  var ths = thead.querySelectorAll('th');
  ths.forEach(function(th, colIdx) {
    // Skip columns that are too narrow / utility (checkboxes, empty, icon-only)
    if (th.querySelector('input[type="checkbox"]')) return;
    if (th.textContent.trim().length === 0 && !th.getAttribute('data-sort-key')) return;
    th.classList.add('sortable');
    th.setAttribute('data-col-idx', colIdx);
    th.addEventListener('click', function() {
      var asc = true;
      if (th.classList.contains('sort-asc')) { asc = false; }
      // Clear sort state on all siblings
      ths.forEach(function(s) { s.classList.remove('sort-asc', 'sort-desc'); });
      th.classList.add(asc ? 'sort-asc' : 'sort-desc');
      _sortTableByCol(tableEl, colIdx, asc);
    });
  });
}

function _sortTableByCol(tableEl, colIdx, asc) {
  var tbody = tableEl.querySelector('tbody');
  if (!tbody) return;
  var rows = Array.from(tbody.querySelectorAll('tr'));
  // Separate data rows from separator/subtotal rows, cache cells once
  var dataRows = [];
  var otherRows = [];
  var cellCache = new Map();
  rows.forEach(function(r) {
    var cells = r.querySelectorAll('td');
    if (cells.length <= 1 && r.querySelector('td[colspan]')) {
      otherRows.push(r);
    } else {
      dataRows.push(r);
      cellCache.set(r, cells);
    }
  });
  // Pre-extract sort values to avoid DOM reads during sort
  var sortValues = new Map();
  dataRows.forEach(function(r) {
    var cell = cellCache.get(r)[colIdx];
    if (cell) {
      var v = (cell.getAttribute('data-sort-value') || cell.textContent).trim();
      sortValues.set(r, v);
    }
  });
  dataRows.sort(function(a, b) {
    var va = sortValues.get(a) || '';
    var vb = sortValues.get(b) || '';
    var na = parseFloat(va.replace(/[^0-9.\-]/g, ''));
    var nb = parseFloat(vb.replace(/[^0-9.\-]/g, ''));
    if (!isNaN(na) && !isNaN(nb)) {
      return asc ? na - nb : nb - na;
    }
    var cmp = va.localeCompare(vb, 'no', {sensitivity: 'base'});
    return asc ? cmp : -cmp;
  });
  // Re-append in sorted order
  dataRows.forEach(function(r) { tbody.appendChild(r); });
  otherRows.forEach(function(r) { tbody.appendChild(r); });
}

// ── DOM element cache ─────────────────────────────────────────────────────────
// Cache frequently accessed elements to reduce DOM queries.
// Uses lazy initialization — elements are cached on first access.
var _domCache = {};
function $(id) {
  if (!(id in _domCache)) _domCache[id] = document.getElementById(id);
  return _domCache[id];
}
function _invalidateDomCache() { _domCache = {}; }

// ── i18n ──────────────────────────────────────────────────────────────────────
let _i18n = {};
let _lang = localStorage.getItem('ui_lang') || 'no';

async function loadI18n() {
    try {
        // The shell carries the content-versioned URL; a fixed number here
        // kept serving a cached file after the strings changed.
        var meta = document.querySelector('meta[name="sybr-i18n"]');
        const r = await fetch(meta ? meta.content : '/static/ui_i18n.json');
        if (!r.ok) throw new Error('HTTP ' + r.status);
        _i18n = await r.json();
        translatePage();
    } catch (e) {
        console.warn('i18n load failed:', e);
    }
}

function t(key, fallback) {
    if (_i18n[_lang] && _i18n[_lang][key]) return _i18n[_lang][key];
    if (_i18n['no'] && _i18n['no'][key]) return _i18n['no'][key];
    return fallback || key;
}

function setLanguage(lang) {
    _lang = lang;
    localStorage.setItem('ui_lang', lang);
    translatePage();
}

// Attributes that can carry user-facing text. aria-label and alt were not
// handled at all, so marking them up did nothing and the Norwegian in them was
// permanently untranslatable — invisible to sighted users and stuck in one
// language for everyone using a screen reader.
var _I18N_ATTRS = ['title', 'placeholder', 'aria-label', 'alt'];

function translatePage(root) {
    var scope = root || document;
    // Single DOM scan with combined selector instead of one per attribute.
    var selector = '[data-i18n]' + _I18N_ATTRS.map(function (a) {
        return ',[data-i18n-' + a + ']';
    }).join('');
    scope.querySelectorAll(selector).forEach(el => {
        var key = el.getAttribute('data-i18n');
        if (key) {
            var val = t(key);
            if ((el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') && el.getAttribute('placeholder')) {
                el.placeholder = val;
            } else {
                el.textContent = val;
            }
        }
        _I18N_ATTRS.forEach(function (attr) {
            var attrKey = el.getAttribute('data-i18n-' + attr);
            if (attrKey) el.setAttribute(attr, t(attrKey));
        });
    });
}

// ── Styled confirm modal (replaces native confirm()) ─────────────────────────
var _confirmResolver = null;
// ── Empty-state helper ──────────────────────────────────────────────────────
// Generates consistent markup for "no X yet" states. Use in place of ad-hoc
//   '<div style="...">No data</div>'
// strings.
//   emptyStateHTML({
//     icon: '📭', title: 'Ingen enheter', desc: 'Legg til din første…',
//     variant: 'inline',   // or omit for full-card
//   })
// It once took an `actions` list of buttons whose onclick was a JavaScript
// string. Nothing used it, and the CSP no longer runs inline handlers.
function emptyStateHTML(opts) {
  opts = opts || {};
  var cls = opts.variant === 'inline' ? 'empty-state-inline' : 'empty-state';
  var parts = ['<div class="' + cls + '">'];
  if (opts.icon) parts.push('<div class="empty-icon">' + esc(opts.icon) + '</div>');
  if (opts.title) parts.push('<div class="empty-title">' + esc(opts.title) + '</div>');
  if (opts.desc) parts.push('<div class="empty-desc">' + esc(opts.desc) + '</div>');
  parts.push('</div>');
  return parts.join('');
}

function showConfirm(title, body) {
  return new Promise(function(resolve) {
    _confirmResolver = resolve;
    document.getElementById('confirm-modal-title').textContent = title;
    var bodyEl = document.getElementById('confirm-modal-body');
    bodyEl.textContent = body || '';
    bodyEl.style.display = body ? 'block' : 'none';
    var modal = document.getElementById('confirm-modal');
    modal.style.display = 'flex';
    document.getElementById('confirm-modal-ok').focus();
  });
}

// Confirm dialog that requires the user to type the exact subject (usually
// a customer or user name) before the destructive button is enabled. Use
// for actions that are hard to reverse — deletes, bulk wipes, etc.
//
//   if (!await showTypedConfirm(customer.name, "Slett kunde", "Dette sletter alle audits, rapporter og credentials permanent.")) return;
function showTypedConfirm(subject, title, body) {
  return new Promise(function(resolve) {
    _confirmResolver = resolve;
    document.getElementById('confirm-modal-title').textContent = title;
    var bodyEl = document.getElementById('confirm-modal-body');

    // Build a body that stays purely DOM (no innerHTML with user subject) so
    // an attacker-controlled customer name can't slip in markup.
    bodyEl.innerHTML = '';
    if (body) {
      var p = document.createElement('div');
      p.textContent = body;
      bodyEl.appendChild(p);
    }
    var hint = document.createElement('div');
    hint.style.cssText = 'margin-top:12px;font-size:11px;color:var(--text-dim);';
    hint.appendChild(document.createTextNode(t('lbl_type_to_confirm', 'Skriv') + ' '));
    var strong = document.createElement('strong');
    strong.style.cssText = 'color:var(--text);font-family:var(--mono);';
    strong.textContent = subject;
    hint.appendChild(strong);
    hint.appendChild(document.createTextNode(' ' + t('lbl_type_to_confirm_suffix', 'for å bekrefte:')));
    bodyEl.appendChild(hint);

    var input = document.createElement('input');
    input.id = 'confirm-modal-input';
    input.type = 'text';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.style.cssText = 'margin-top:8px;width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg);color:var(--text);font-family:var(--mono);font-size:13px;box-sizing:border-box;';
    bodyEl.appendChild(input);
    bodyEl.style.display = 'block';

    var ok = document.getElementById('confirm-modal-ok');
    ok.disabled = true;
    ok.style.opacity = '0.5';
    ok.style.cursor = 'not-allowed';

    input.addEventListener('input', function() {
      var match = input.value === subject;
      ok.disabled = !match;
      ok.style.opacity = match ? '' : '0.5';
      ok.style.cursor = match ? '' : 'not-allowed';
    });
    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && input.value === subject) {
        e.preventDefault();
        resolveConfirm(true);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        resolveConfirm(false);
      }
    });

    var modal = document.getElementById('confirm-modal');
    modal.style.display = 'flex';
    setTimeout(function() { input.focus(); }, 50);
  });
}

function resolveConfirm(val) {
  document.getElementById('confirm-modal').style.display = 'none';
  // Reset the OK button in case this was a typed-confirm
  var ok = document.getElementById('confirm-modal-ok');
  if (ok) {
    ok.disabled = false;
    ok.style.opacity = '';
    ok.style.cursor = '';
  }
  if (_confirmResolver) { _confirmResolver(val); _confirmResolver = null; }
}

// ── Command Palette (Cmd+K) ──────────────────────────────────────────────────
var _cmdPaletteOpen = false;
var _cmdSelectedIdx = -1;

function toggleCommandPalette() { _cmdPaletteOpen ? closeCommandPalette() : openCommandPalette(); }

function openCommandPalette() {
  var el = document.getElementById('cmd-palette');
  el.style.display = 'flex';
  _cmdPaletteOpen = true;
  _cmdSelectedIdx = -1;
  var input = document.getElementById('cmd-input');
  input.value = '';
  input.focus();
  _renderCmdResults('');
  input.oninput = function() { _renderCmdResults(this.value); _cmdSelectedIdx = -1; };
  input.onkeydown = function(e) {
    var items = document.querySelectorAll('.cmd-item');
    if (e.key === 'ArrowDown') { e.preventDefault(); _cmdSelectedIdx = Math.min(_cmdSelectedIdx+1, items.length-1); _highlightCmd(items); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); _cmdSelectedIdx = Math.max(_cmdSelectedIdx-1, 0); _highlightCmd(items); }
    else if (e.key === 'Enter' && _cmdSelectedIdx >= 0 && items[_cmdSelectedIdx]) { e.preventDefault(); items[_cmdSelectedIdx].click(); }
    else if (e.key === 'Escape') { closeCommandPalette(); }
  };
}
function closeCommandPalette() {
  document.getElementById('cmd-palette').style.display = 'none';
  _cmdPaletteOpen = false;
}
function _highlightCmd(items) {
  items.forEach(function(el, i) { el.style.background = i === _cmdSelectedIdx ? 'rgba(77,159,181,0.15)' : ''; });
  if (items[_cmdSelectedIdx]) items[_cmdSelectedIdx].scrollIntoView({block:'nearest'});
}

function _renderCmdResults(query) {
  var q = (query || '').toLowerCase().trim();
  var results = [];

  // Recent customers (shown when search is empty)
  if (!q && _overviewData && _overviewData.customers) {
    var recentIds = JSON.parse(localStorage.getItem('sybr_recent_customers') || '[]');
    if (recentIds.length > 0) {
      recentIds.forEach(function(rid) {
        var rc = _overviewData.customers.find(function(c){ return c.customer_id === rid || c._id === rid; });
        if (rc) {
          results.push({
            label: rc.customer_name,
            hint: rc.primary_domain || '',
            icon: 'clock',
            action: function(){ overviewSelectCustomer(rid); },
            type: 'recent'
          });
        }
      });
    }
  }

  // Pages / Navigation
  var pages = [
    {label:t('nav_dashboard','Dashboard'), action:function(){showView('overview')},  section:t('nav_dashboard'), icon:'grid'},
    {label:t('nav_customers','Customers'), action:function(){showView('customers')}, section:t('nav_customers'), icon:'users'},
    {label:t('nav_m365_status'),     action:function(){showView('home')},      section:t('nav_customers'), icon:'cloud'},
    {label:t('nav_history','History'), action:function(){showView('history')},    section:t('nav_customers'), icon:'calendar'},
    {label:t('bc_hosts_ssh','Hosts'), action:function(){showView('hosts')},      section:t('nav_remote_access','Fjerntilgang'),    icon:'monitor'},
    {label:t('bc_network','FortiGate / UniFi'), action:function(){showView('network')},    section:t('nav_network','Nettverk'),    icon:'globe'},
    {label:'VPN',             action:function(){showView('vpn')},        section:t('nav_network','Nettverk'),    icon:'lock'},
    {label:'TLS Monitor',     action:function(){showView('tls')},        section:t('nav_network','Nettverk'),    icon:'shield'},
    {label:t('nav_browser2','Browser'), action:function(){showView('browser')}, section:t('nav_tools','Verktøy'),    icon:'globe'},
    {label:'Tailscale',       action:function(){showView('tailscale')},  section:t('nav_tools','Verktøy'),    icon:'link'},
    {label:t('bc_provisioning','Provisjonering'), action:function(){showView('provision')},  section:t('nav_tools','Verktøy'),    icon:'gear'},
    {label:'Sybrt',           action:function(){showView('ai')},         section:'',                 icon:'sparkle'},
    {label:t('nav_integrations','Integrations'), action:function(){showView('integrations')},section:'',                icon:'plug'},
    {label:t('bc_log','Log'), action:function(){showView('logs')},        section:'',                icon:'document'},
    {label:t('hdr_settings','Settings'), action:function(){openSettings()}, section:'',                icon:'gear'},
    {label:t('tab_users','Users'),     action:function(){openSettings();setTimeout(function(){switchSettingsTab(document.querySelectorAll('.settings-tab-btn')[4],'stab-users')},100)}, section:t('hdr_settings'), icon:'users'},
    {label:t('hdr_branding','Branding'), action:function(){openSettings();setTimeout(function(){switchSettingsTab(document.querySelectorAll('.settings-tab-btn')[1],'stab-branding')},100)}, section:t('hdr_settings'), icon:'palette'},
  ];
  pages.forEach(function(p) {
    if (!q || p.label.toLowerCase().includes(q) || (p.section||'').toLowerCase().includes(q))
      results.push({label:p.label, hint:p.section, icon:p.icon, action:p.action, type:'page'});
  });

  // Actions
  var actions = [
    {label:t('btn_run_audit'),       action:function(){showView('home');setTimeout(startAudit,200)}, hint:'Ctrl+Shift+A', icon:'play'},
    {label:t('hdr_settings','Settings'),      action:function(){openSettings()},                              hint:'Ctrl+,',       icon:'gear'},
    {label:t('btn_export_excel','Export Excel'), action:function(){exportDashboardExcel()},                    hint:'',             icon:'chart'},
  ];
  if (q) {
    actions.forEach(function(a) {
      if (a.label.toLowerCase().includes(q)) results.push({label:a.label, hint:a.hint, icon:a.icon, action:a.action, type:'action'});
    });
  }

  // Customers (dynamic from cached overview data)
  if (q && _overviewData && _overviewData.customers) {
    _overviewData.customers.forEach(function(c) {
      if (c.customer_name.toLowerCase().includes(q) || (c.primary_domain||'').toLowerCase().includes(q)) {
        results.push({
          label: c.customer_name,
          hint: c.primary_domain || '',
          icon: 'building',
          action: function(){ switchActiveCustomer(c._id).then(function(){showView('home');loadStatus();}); },
          type: 'customer'
        });
      }
    });
  }

  // Audit findings (from last loaded audit results)
  if (q && q.length >= 2 && window._lastAuditWarns) {
    window._lastAuditWarns.forEach(function(w) {
      if (w.toLowerCase().includes(q)) {
        results.push({
          label: w.length > 80 ? w.substring(0,77)+'...' : w,
          hint: t('lbl_finding','Funn'),
          icon: 'warning',
          action: function(){ showView('home'); },
          type: 'finding'
        });
      }
    });
  }

  // Render
  var html = '';
  if (results.length === 0) {
    html = '<div style="padding:var(--space-8) var(--space-5);text-align:center;color:var(--text-dim);font-size:var(--font-sm);">' + t('msg_no_results', 'Ingen treff') + '</div>';
  } else {
    var lastType = '';
    results.forEach(function(r, i) {
      if (r.type !== lastType) {
        var sectionLabel = r.type === 'recent' ? t('lbl_recent','Nylige') : r.type === 'page' ? t('lbl_navigation','Navigasjon') : r.type === 'action' ? t('lbl_actions','Handlinger') : r.type === 'finding' ? t('lbl_findings','Funn') : t('nav_customers');
        html += '<div style="padding:var(--space-1) var(--space-5);font-size:var(--font-xs);color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;font-weight:600;'+(lastType?'margin-top:var(--space-2);border-top:1px solid var(--border);padding-top:var(--space-2);':'')+'">' + sectionLabel + '</div>';
        lastType = r.type;
      }
      html += '<div class="cmd-item" tabindex="-1" data-click-handler="runCommandPaletteItem" data-index="' + i + '" style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-2) var(--space-5);cursor:pointer;transition:background 0.1s;border-radius:0;">'
        + '<span style="width:24px;flex-shrink:0;display:flex;align-items:center;justify-content:center;color:var(--text-muted);">' + icon(r.icon, 16) + '</span>'
        + '<span style="flex:1;font-size:var(--font-base);color:var(--text);">' + esc(r.label) + '</span>'
        + (r.hint ? '<span style="font-size:var(--font-xs);color:var(--text-dim);">' + esc(r.hint) + '</span>' : '')
        + '</div>';
    });
  }
  document.getElementById('cmd-results').innerHTML = html;
  // The actions runCommandPaletteItem calls, by data-index.
  window._cmdActions = results.map(function(r){return r.action});
}

// ── Toast notification system ─────────────────────────────────────────────────
function showToast(message, type, duration) {
  if (type === undefined) type = 'error';
  if (duration === undefined) duration = 5000;
  var container = document.getElementById('toast-container');
  if (!container) return;
  var toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.innerHTML = '<div class="toast-body">' + esc(message) + '</div>' +
    '<button class="toast-close" data-click-handler="dismissToast" aria-label="' + t('btn_close') + '">&times;</button>';
  container.appendChild(toast);
  if (duration > 0) {
    setTimeout(function() { dismissToast(toast); }, duration);
  }
  return toast;
}

function showToastWithRetry(message, retryFn, type, dedupeKey) {
  if (type === undefined) type = 'error';
  var container = document.getElementById('toast-container');
  if (!container) return;
  if (dedupeKey) {
    var existing = Array.from(container.children).find(function(el) {
      return el.dataset.errorKey === dedupeKey && !el.classList.contains('removing');
    });
    if (existing) return existing;
  }
  var toast = document.createElement('div');
  if (dedupeKey) toast.dataset.errorKey = dedupeKey;
  toast.dataset.retryId = _toastRetryId;
  toast.className = 'toast toast-' + type;
  toast.innerHTML = '<div class="toast-body">' + esc(message) +
    '<div class="toast-actions"><button data-click-handler="retryToast">' +
    t('toast_retry') + '</button></div></div>' +
    '<button class="toast-close" data-click-handler="dismissToast" aria-label="' + t('btn_close') + '">&times;</button>';
  if (!window._toastRetryFns) window._toastRetryFns = {};
  window._toastRetryFns[_toastRetryId] = retryFn;
  _toastRetryId++;
  container.appendChild(toast);
  return toast;
}
var _toastRetryId = 0;

function retryToast(el) {
  var retryFn = el && window._toastRetryFns && window._toastRetryFns[el.dataset.retryId];
  dismissToast(el);
  if (retryFn) retryFn();
}

function dismissToast(el) {
  if (!el || el.classList.contains('removing')) return;
  if (el.dataset.retryId && window._toastRetryFns) delete window._toastRetryFns[el.dataset.retryId];
  el.classList.add('removing');
  setTimeout(function() { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
}

// ── apiFetch wrapper ──────────────────────────────────────────────────────────
// Authentication is cookie-only in the browser. The HttpOnly tokens cannot
// be read by injected JavaScript and do not survive in localStorage dumps.
var _currentUser = null;

function setAuth() {
  // Remove credentials left by versions that persisted bearer tokens.
  localStorage.removeItem('msptk_token');
  localStorage.removeItem('msptk_refresh');
}

async function checkAuth() {
  try {
    var res = await fetch('/api/auth/status');
    var data = await res.json();
    // The endpoint reports setup_required. Reading a setup_complete that the
    // server never sends made this !undefined === true on every call, so the
    // setup form came back even straight after it had succeeded — and the
    // second attempt then failed with "Oppsett er allerede fullført".
    if (data.setup_required) { showLoginView('setup'); return; }
    // Validate the HttpOnly access cookie.
    var me = await fetch('/api/auth/me');
    if (me.status === 401) {
      // The refresh token is another HttpOnly cookie; no token enters JS.
      var ref = await fetch('/api/auth/refresh', {method:'POST'});
      if (!ref.ok) { showLoginView('login'); return; }
      me = await fetch('/api/auth/me');
    }
    if (!me.ok) { showLoginView('login'); return; }
    if (me.ok) {
      // /auth/me answers {user: {...}}. Storing the envelope meant every read
      // of _currentUser.role and _currentUser.display_name was undefined, so
      // the avatar has been showing "?" for as long as it has existed.
      var _me = await me.json();
      _currentUser = _me.user || _me;
      if (_me.write_exempt) _writeExempt = _me.write_exempt;
      _features = _me.features || [];
      _modules = _me.modules || [];
      _allowedViews = _me.views || [];
      hideLoginView(); updateUserDisplay();
      if (_me.mfa_required) { await showMfaSettings(); } else { _postAuthInit(); }
    }
  } catch(e) { console.error('Request failed:', e); showLoginView('login'); }
}

function _postAuthInit() {
  loadStatus();
  // Land where the address says, else on the cross-customer dashboard: the
  // question a technician arrives with is "which customer needs me", not
  // whichever customer was active last time.
  applyRoute();
  applyBranding();
  _checkNotifBadge();
  _checkVpnHeaderBadge();
  startConnectionMonitor();
}

// ── Live connection monitor ───────────────────────────────────────────────
// Polls /api/health (public, unauth) every 30 s. Updates the dot in the
// header: green=ok, yellow=checking/timeout, red=down. Reflects both the
// browser's navigator.onLine state and the server's db_ok field. Cheap
// enough to run continuously after login.

var _connMonitorInterval = null;
var _connLastOk = true;

function _setConnStatus(state, label, title) {
  var box = document.getElementById('conn-status');
  var dot = document.getElementById('conn-status-dot');
  var lbl = document.getElementById('conn-status-label');
  if (!box || !dot) return;
  box.style.display = 'flex';
  var colors = {
    ok:       'var(--color-success)',
    checking: 'var(--color-warning)',
    down:     'var(--color-danger)',
  };
  dot.style.background = colors[state] || 'var(--text-dim)';
  if (lbl) lbl.textContent = label;
  box.title = title || label;
}

async function _pollConnection() {
  if (!navigator.onLine) {
    _setConnStatus('down', t('conn_offline', 'Offline'), t('conn_offline_title', 'Ingen nettverksforbindelse'));
    _connLastOk = false;
    return;
  }
  _setConnStatus('checking', t('conn_checking', '...'), t('conn_checking_title', 'Sjekker server'));
  try {
    var ctrl = new AbortController();
    var timeoutId = setTimeout(function() { ctrl.abort(); }, 5000);
    var r = await fetch('/api/health', { signal: ctrl.signal, cache: 'no-store' });
    clearTimeout(timeoutId);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    var d = await r.json();
    if (d && d.status === 'ok' && d.db_ok) {
      _setConnStatus('ok', t('conn_live', 'Live'), t('conn_live_title', 'Server OK — v{v}').replace('{v}', d.version || '?'));
      if (!_connLastOk) {
        showToast(t('msg_connection_restored', 'Forbindelse gjenopprettet'), 'success', 2000);
      }
      _connLastOk = true;
    } else {
      _setConnStatus('down', t('conn_degraded', 'Degradert'), t('conn_degraded_title', 'Server svarer, men DB utilgjengelig'));
      _connLastOk = false;
    }
  } catch (e) {
    _setConnStatus('down', t('conn_down', 'Nede'), t('conn_down_title', 'Ingen svar fra server'));
    _connLastOk = false;
  }
}

function startConnectionMonitor() {
  if (_connMonitorInterval) return;
  _pollConnection();
  _connMonitorInterval = setInterval(_pollConnection, 30000);
  // Also re-poll when the tab becomes visible again and on network events.
  document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible') _pollConnection();
  });
  window.addEventListener('online', _pollConnection);
  window.addEventListener('offline', _pollConnection);
}

function showLoginView(mode) {
  var el = document.getElementById('auth-overlay');
  if (!el) return;
  el.style.display = 'flex';
  document.querySelector('header').style.display = 'none';
  var _bnLogin = document.getElementById('bottom-nav'); if (_bnLogin) _bnLogin.style.display = 'none';
  document.getElementById('auth-setup-form').style.display = mode === 'setup' ? 'block' : 'none';
  document.getElementById('auth-login-form').style.display = mode === 'login' ? 'block' : 'none';
  // Show version in login
  fetch('/api/version').then(function(r){return r.json()}).then(function(d){
    var lv = document.getElementById('login-version'); if (lv) lv.textContent = 'v' + (d.version||'');
  }).catch(function(){});
}

function hideLoginView() {
  var el = document.getElementById('auth-overlay');
  if (el) el.style.display = 'none';
  document.querySelector('header').style.display = '';
  var _bnApp = document.getElementById('bottom-nav'); if (_bnApp) _bnApp.style.display = '';
}

function updateUserDisplay() {
  if (!_currentUser) return;
  var role = _currentUser.role || '';
  var fullName = _currentUser.display_name || _currentUser.username || '';
  var initials = fullName.split(/\s+/).filter(Boolean).map(function(w){return w.charAt(0).toUpperCase()}).join('').substring(0, 2) || '?';
  // Populate the avatar button + account-menu identity header (frame 3a).
  var ini = document.getElementById('avatar-initials');
  if (ini) ini.textContent = initials;
  var nm = document.getElementById('avatar-name');
  if (nm) nm.textContent = fullName;
  var em = document.getElementById('avatar-email');
  if (em) em.textContent = _currentUser.email || _currentUser.username || '';
  var btn = document.getElementById('avatar-btn');
  if (btn) btn.title = fullName + (role ? ' (' + role + ')' : '');
  // Legacy hidden element — kept so any remaining reference resolves.
  var el = document.getElementById('user-display');
  if (el) el.textContent = initials;
  applyWriteCapability();
  // An audit may already be running — started by a schedule, another tab, or
  // another technician. Ask rather than assume; the badge should reflect the
  // server on every load, not only when somebody opens the audit view.
  if (typeof _reconcileAuditState === 'function') _reconcileAuditState();
}

// ── Read-only accounts ───────────────────────────────────────────────────────
// The server decides; this only stops the interface offering what it will
// refuse. Anything marked data-write is hidden without the capability, and a
// badge says why rather than leaving someone hunting for a menu that is gone.
function canWrite() {
  return !!(_currentUser && _currentUser.can_write);
}

// The second, stricter tier. tenant_write is what lets a control change a
// customer's Microsoft tenant (policy deploy/enforce/restore, consent). The
// server checks it separately via require_tenant_write, and it implies
// can_write — so a control marked data-write="tenant" needs both.
function canTenantWrite() {
  return !!(_currentUser && _currentUser.tenant_write);
}

function applyFeatureVisibility() {
  // Marked elements name a feature; unmarked ones are visible to anyone who
  // signed in. Same shape as data-write, and deliberately a separate attribute:
  // "may change things" and "may reach this at all" are different questions and
  // conflating them is how one of them stops being asked.
  document.querySelectorAll('[data-feature]').forEach(function(el) {
    _setGated(el, hasFeature(el.getAttribute('data-feature')));
  });
  document.querySelectorAll('[data-view-gate]').forEach(function(el) {
    _setGated(el, canOpenView(el.getAttribute('data-view-gate')));
  });
  // An optional module an administrator switched off is gone for everyone,
  // and its controls with it (app/core/modules.py).
  document.querySelectorAll('[data-module]').forEach(function(el) {
    _setGated(el, hasModule(el.getAttribute('data-module')));
  });
}

function hasModule(key) {
  return _modules.indexOf(key) !== -1;
}

// A gate answers "may this be seen at all", never "is this showing right now".
// Writing style.display='' on everything allowed answered the second question
// too, and wiped out whatever the element's own state had decided. The audit
// badge carries a view gate and hides itself when no audit is running, so
// every page load un-hid it and announced a run that was not happening —
// nav-logs and the connection chip are state-driven the same way.
// Hiding via a class leaves that state untouched, and !important still beats
// an inline display on the elements a user genuinely may not see.
function _setGated(el, allowed) {
  el.classList.toggle('gated-hidden', !allowed);
}

function applyWriteCapability() {
  var write = canWrite();
  document.body.classList.toggle('is-readonly', !write);
  // Second tier: an account with can_write but not tenant_write sees ordinary
  // write controls and not the tenant-changing ones. is-readonly already hides
  // every [data-write] (tenant ones included), so this only has to catch the
  // in-between account; the overlap on a read-only user is harmless.
  document.body.classList.toggle('is-no-tenant-write', !canTenantWrite());
  applyFeatureVisibility();
  var badge = document.getElementById('readonly-badge');
  if (badge) {
    badge.style.display = write ? 'none' : '';
    badge.title = t('tip_readonly', 'Your account has read access. Changes require write.');
    badge.textContent = t('lbl_readonly', 'Read-only');
  }
}

// ── Avatar account menu ──────────────────────────────────────────────────────
function toggleAvatarMenu(e) {
  if (e) e.stopPropagation();
  var m = document.getElementById('avatar-menu');
  var b = document.getElementById('avatar-btn');
  if (!m) return;
  var open = m.classList.toggle('open');
  if (b) b.classList.toggle('open', open);
  if (open) {
    // Defer so this same click doesn't immediately close it.
    setTimeout(function() {
      document.addEventListener('click', _closeAvatarMenuOutside);
      document.addEventListener('keydown', _closeAvatarMenuEsc);
    }, 0);
  } else {
    _detachAvatarMenuListeners();
  }
}
function closeAvatarMenu() {
  var m = document.getElementById('avatar-menu');
  var b = document.getElementById('avatar-btn');
  if (m) m.classList.remove('open');
  if (b) b.classList.remove('open');
  _detachAvatarMenuListeners();
}
function _detachAvatarMenuListeners() {
  document.removeEventListener('click', _closeAvatarMenuOutside);
  document.removeEventListener('keydown', _closeAvatarMenuEsc);
}
function _closeAvatarMenuOutside(e) {
  var m = document.getElementById('avatar-menu');
  var b = document.getElementById('avatar-btn');
  if (m && !m.contains(e.target) && b && !b.contains(e.target)) closeAvatarMenu();
}
function _closeAvatarMenuEsc(e) { if (e.key === 'Escape') closeAvatarMenu(); }

async function doLogin() {
  var u = document.getElementById('login-username').value.trim();
  var p = document.getElementById('login-password').value;
  if (!u || !p) return;
  try {
    var res = await fetch('/api/auth/login', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p,otp:document.getElementById('login-otp').value.trim()})});
    if (!res.ok) { var err = await res.json(); showToast(err.error||t('err_login_failed','Login failed'),'error'); return; }
    setAuth();
    hideLoginView();
    checkAuth();
  } catch(e) { console.error('Request failed:', e); showToast(t('err_login_failed','Login failed'),'error'); }
}

// Mirrors validate_password() on the server, so a form can state the rule
// instead of a round-trip teaching it. The server stays the authority.
function passwordMeetsRule(p) {
  return typeof p === 'string' && p.length >= 10 && /[A-Za-z]/.test(p) && /[0-9]/.test(p) && /[^A-Za-z0-9]/.test(p);
}

async function doSetup() {
  var u = document.getElementById('setup-username').value.trim();
  var p = document.getElementById('setup-password').value;
  var n = document.getElementById('setup-displayname').value.trim();
  if (!u || !p || !n) { showToast(t('err_fill_all_fields','Fill in all fields'),'error'); return; }
  if (!passwordMeetsRule(p)) { showToast(t('err_password_rule'), 'error'); return; }
  try {
    var res = await fetch('/api/auth/setup', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p,display_name:n})});
    if (!res.ok) { var err = await res.json(); showToast(err.error||t('err_setup_failed','Setup failed'),'error'); return; }
    setAuth();
    hideLoginView();
    _postAuthInit();
    showToast(t('msg_admin_created','Admin account created!'),'success');
    checkAuth();
  } catch(e) { console.error('Request failed:', e); showToast(t('err_setup_failed','Setup failed'),'error'); }
}

async function doLogout() {
  await apiFetch('/api/auth/logout', {method:'POST'});
  setAuth(null, null);
  _currentUser = null;
  showLoginView('login');
}

// A metric that was never measured is null, not undefined — SQLite NULL comes
// through JSON as null, and `null !== undefined` is true. Every guard here
// used that test, so an unmeasured figure reached .toFixed and threw "Cannot
// read properties of null". That became reachable the moment sections started
// reporting "not measured" instead of a zero, which is the whole point of
// them: intune_compliance_pct is null on any tenant without Intune.
function metricPct(value, digits) {
  if (value === null || value === undefined || value === '' || isNaN(value)) return null;
  return Number(value).toFixed(digits === undefined ? 0 : digits);
}

// The same rule for counts. A run that did not count users without MFA has
// no such key in its metrics, and `Number(undefined) || 0` turned that into a
// reassuring zero printed right under a finding about an admin without MFA.
// Unmeasured reads "ukjent" on every card that shows the figure.
function metricKnown(value) {
  return !(value === null || value === undefined || value === '' || isNaN(value));
}
function metricCount(value) {
  return metricKnown(value) ? String(Number(value)) : t('lbl_unknown_value', 'ukjent');
}

// Run folders are named "YYYY-MM-DD_HHMMSS" (older ones "YYYY-MM-DD_HHMM",
// some with a suffix after). That name is for the file system; a person reads
// the date and time. Returns the input unchanged when it is not a run name.
// `short` gives the date alone in a compact form, for tables and lists.
function formatRunName(name, short) {
  var m = /^(\d{4})-(\d{2})-(\d{2})(?:[_T ](\d{2}):?(\d{2}))?/.exec(String(name || ''));
  if (!m) return String(name || '');
  var locale = _lang === 'en' ? 'en-GB' : 'nb-NO';
  var date = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  if (isNaN(date.getTime())) return String(name);
  if (short) return date.toLocaleDateString(locale, {day: 'numeric', month: 'short', year: 'numeric'});
  var day = date.toLocaleDateString(locale, {day: 'numeric', month: 'long', year: 'numeric'});
  if (!m[4]) return day;
  return t('fmt_run_date_time', '{date} kl. {time}').replace('{date}', day).replace('{time}', m[4] + ':' + m[5]);
}

// "Auditert i dag" / "Auditert for 3 d siden" from a run name, for the
// context bar. One function, because two places wrote that element.
function auditAgeLabel(name) {
  var date = new Date(String(name || '').substring(0, 10));
  var days = Math.floor((Date.now() - date.getTime()) / 86400000);
  if (isNaN(days) || days < 0) return t('lbl_audited_on', 'Auditert {date}').replace('{date}', formatRunName(name, true));
  return days === 0 ? t('ctx_audited_today', 'Auditert i dag') : t('ctx_audited_days_ago', 'Auditert for {n} d siden').replace('{n}', days);
}

// Paths the server keeps open without the write capability. Sent by /auth/me
// rather than restated here — a second copy of the rule is the one that goes
// stale, and it would go stale in the direction of offering something the
// server refuses.
var _writeExempt = [];

// What this account reaches, resolved by the server. The interface holds no
// copy of the rules — it hides what is not in these lists, so a screen cannot
// drift from the route it leads to.
var _features = [];
var _modules = [];
var _allowedViews = [];

function hasFeature(key) {
  // Empty until /auth/me answers. Hiding everything for that instant is the
  // right way round: showing a control and taking it away reads as a bug, and
  // offering one that will 403 reads as a broken tool.
  return _features.indexOf(key) !== -1;
}

function canOpenView(name) {
  return _allowedViews.indexOf(name) !== -1;
}

function _wouldBeRefused(url, options) {
  var method = ((options && options.method) || 'GET').toUpperCase();
  if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return false;
  if (canWrite()) return false;
  var path = String(url).split('?')[0].replace(/\/$/, '');
  return _writeExempt.indexOf(path) === -1;
}

var _sessionRecovery = null;

function recoverSession() {
  // An integration can return 401 while the Sybr session is still valid.
  // Share recovery across concurrent requests so refresh cookies cannot race.
  if (!_sessionRecovery) {
    _sessionRecovery = (async function() {
      var me = await fetch('/api/auth/me');
      if (me.ok) return 'valid';
      if (me.status !== 401) return 'unavailable';
      var ref = await fetch('/api/auth/refresh', {method:'POST'});
      if (ref.ok) return 'refreshed';
      // A refused refresh credential means sign in again. Only a server that
      // could not answer (5xx, rate limit, network) is a lost connection.
      if (ref.status === 400 || ref.status === 401 || ref.status === 403) return 'expired';
      return 'unavailable';
    })().catch(function() { return 'unavailable'; }).finally(function() {
      _sessionRecovery = null;
    });
  }
  return _sessionRecovery;
}

// Every change of the active customer goes through here, one at a time. Two
// switches in flight could land in either order on the server, leaving a
// different customer active than the page on screen, and notes saved there.
var _switchQueue = Promise.resolve();

function switchActiveCustomer(customerId) {
  var next = _switchQueue.then(function() {
    return apiFetch('/api/customers/switch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({customer_id: customerId}),
    });
  });
  _switchQueue = next.catch(function() {});
  return next;
}

async function apiFetch(url, options, _retryCount, _authRetried) {
  if (_retryCount === undefined) _retryCount = 0;
  var maxRetries = 2;
  // Answered here as well as by the server. Marking every control that writes
  // is possible for the ones in the markup and unbounded for the ones built at
  // runtime, so this is the half that cannot be forgotten: a read-only account
  // gets told why, instead of a button that appears to do nothing.
  if (_wouldBeRefused(url, options)) {
    showToast(t('err_readonly_account', 'Your account has read access. Changes require write.'), 'warning', 4000);
    return null;
  }
  if (!options) options = {};
  if (!options.headers) options.headers = {};
  var requestOptions = Object.assign({}, options);
  requestOptions.headers = new Headers(options.headers);
  requestOptions.headers.set('Accept-Language', _lang === 'en' ? 'en' : 'nb-NO');
  delete requestOptions.onError;
  try {
    var r = await fetch(url, requestOptions);
    if (r.ok) {
      var ct = (r.headers.get('content-type') || '');
      if (ct.indexOf('application/json') !== -1) {
        return await r.json();
      }
      // Non-JSON but successful — return a wrapper
      var text = await r.text();
      try { return JSON.parse(text); } catch(_) { return { _raw: text, ok: true }; }
    }
    // HTTP error
    if (r.status >= 500) {
      // Server error — show actual error from response body
      var errBody = '';
      var eb = null;
      try {
        eb = await r.json();
        errBody = eb.error_key ? t(eb.error_key, eb.error) : (eb.error || eb.detail || JSON.stringify(eb));
        if (eb.error_id) errBody += ' (' + t('lbl_error_id', 'Feil-ID') + ': ' + eb.error_id + ')';
      } catch(_) { errBody = await r.text().catch(function(){return '';}); }
      var safeRead = /^(GET|HEAD)$/.test((options.method || 'GET').toUpperCase());
      if (safeRead && (!eb || eb.error_type !== 'integration_error') && _retryCount < maxRetries) {
        showToast(t('err_server_error','Server error') + ' (' + (_retryCount+1) + '/' + maxRetries + '): ' + (errBody || r.status), 'warning', 3000);
        await new Promise(function(resolve) { setTimeout(resolve, 3000); });
        return apiFetch(url, options, _retryCount + 1, _authRetried);
      }
      if (options.onError) options.onError(errBody || 'HTTP ' + r.status);
      showToastWithRetry(t('err_server_error','Server error') + ': ' + (errBody || 'HTTP ' + r.status), function() { apiFetch(url, options, 0); }, 'error', eb && eb.error_key || url);
      console.error('API error', url, r.status, errBody);
      return null;
    }
    if (r.status === 401) {
      var sessionState = await recoverSession();
      if (sessionState === 'expired') {
        setAuth();
        showLoginView('login');
        return null;
      }
      if (sessionState === 'unavailable') {
        showToastWithRetry(t('toast_lost_connection'), function() { apiFetch(url, options, 0); });
        return null;
      }
      if (sessionState === 'refreshed' && !_authRetried) return apiFetch(url, options, _retryCount, true);
      // Our session is valid: display the endpoint's error below.
    }
    if (r.status >= 400) {
      // Client error — show message from body
      var errMsg = t('err_request_failed').replace('{status}', r.status);
      try {
        const errBody = await r.json();
        if (errBody.error_key) errMsg = t(errBody.error_key, errBody.error);
        else if (errBody.error) errMsg = errBody.error;
        else if (errBody.detail) errMsg = errBody.detail;
        else if (errBody.message) errMsg = errBody.message;
      } catch(_) {}
      if (options.onError) options.onError(errMsg);
      showToast(errMsg, 'error');
      return null;
    }
    return null;
  } catch (e) {
    // Network error
    if (options.onError) options.onError(t('toast_lost_connection'));
    showToastWithRetry(t('toast_lost_connection'), function() { apiFetch(url, options, 0); });
    return null;
  }
}

// ── Global error handlers ─────────────────────────────────────────────────────
window.onerror = function(msg, src, line, col, err) {
  var display = (err && err.message) ? err.message : String(msg);
  if (display.length > 120) display = display.substring(0, 120) + '...';
  showToast(t('toast_unexpected_error').replace('{msg}', display), 'error');
};
window.onunhandledrejection = function(event) {
  var reason = event.reason;
  var display = (reason && reason.message) ? reason.message : String(reason);
  if (display.length > 120) display = display.substring(0, 120) + '...';
  showToast(t('toast_unexpected_error').replace('{msg}', display), 'error');
};

// ── State ──────────────────────────────────────────────────────────────────────
let currentView = 'home';
let auditRunning = false;
let auditOutDir = null;
let sectionTotal = 0;
let sectionDone = 0;

let SECTION_COUNT = 0; // auto-detected from actual sections

// ── Skeleton loading ───────────────────────────────────────────────────────────
function skeletonHTML(type) {
  var s = '<div class="skeleton ';
  var row = s + 'skeleton-row"></div>';
  var text = s + 'skeleton-text"></div>';
  var textW = '<div class="skeleton skeleton-text" style="width:50%"></div>';
  var title = s + 'skeleton-title"></div>';
  if (type === 'home') {
    return '<div class="skeleton-card">' + title +
      '<div class="skeleton skeleton-title" style="width:60%;height:24px;margin-bottom:6px;"></div>' +
      '<div class="skeleton skeleton-text" style="width:35%;margin-bottom:16px;"></div>' +
      '<div style="display:flex;gap:24px;flex-wrap:wrap;">' +
        '<div class="skeleton skeleton-metric"></div>' +
        '<div class="skeleton skeleton-metric"></div>' +
        '<div class="skeleton skeleton-metric"></div>' +
      '</div>' +
      '<div style="display:flex;gap:10px;margin-top:20px;">' +
        '<div class="skeleton" style="width:120px;height:36px;border-radius:6px;"></div>' +
        '<div class="skeleton" style="width:140px;height:36px;border-radius:6px;"></div>' +
      '</div></div>' +
      '<div class="skeleton-card" style="margin-top:16px;">' + title + text + text + textW + '</div>';
  }
  if (type === 'dashboard') {
    var cards = '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:20px;">' +
      '<div class="skeleton skeleton-metric"></div><div class="skeleton skeleton-metric"></div><div class="skeleton skeleton-metric"></div></div>';
    var rows = '';
    for (var i = 0; i < 5; i++) rows += row;
    return cards + '<div class="skeleton-card">' + title + rows + '</div>';
  }
  if (type === 'customers') {
    var html = '';
    for (var j = 0; j < 3; j++) {
      html += '<div class="skeleton-card"><div style="display:flex;align-items:center;gap:12px;"><div style="flex:1;">' +
        '<div class="skeleton skeleton-title" style="width:40%;"></div>' +
        '<div class="skeleton skeleton-text" style="width:30%;"></div>' +
        '<div style="display:flex;gap:24px;margin-top:8px;"><div class="skeleton" style="width:80px;height:14px;border-radius:4px;"></div>' +
        '<div class="skeleton" style="width:100px;height:14px;border-radius:4px;"></div></div></div>' +
        '<div class="skeleton" style="width:90px;height:36px;border-radius:6px;"></div></div></div>';
    }
    return html;
  }
  if (type === 'files') {
    var html2 = '';
    for (var k = 0; k < 4; k++) {
      html2 += '<div class="skeleton-card">' + title +
        '<div class="skeleton skeleton-text" style="width:70%;"></div>' +
        '<div class="skeleton skeleton-text" style="width:55%;"></div>' + textW + '</div>';
    }
    return html2;
  }
  if (type === 'history') {
    var html3 = '';
    for (var m = 0; m < 6; m++) html3 += row;
    return html3;
  }
  return '';
}

// ── View routing ───────────────────────────────────────────────────────────────
// M365 sub-views that should highlight the "M365 / Azure" nav button
var _m365SubViews = {home: true, files: true, audit: true, setup: true};

function _updateBreadcrumb(name) {
  var bc = document.getElementById('breadcrumb');
  var items = document.getElementById('breadcrumb-items');
  if (!bc || !items) return;
  var map = {
    overview:     [{label:t('nav_dashboard')}],
    customers:    [{label:t('nav_customers')}],
    home:         [{label:t('nav_customers'),view:'customers'}, {label:t('nav_m365_status')}],
    audit:        [{label:t('nav_customers'),view:'customers'}, {label:t('nav_m365_status'),view:'home'}, {label:'Audit'}],
    history:      [{label:t('nav_customers'),view:'customers'}, {label:t('nav_history')}],
    assessments:  [{label:t('nav_customers'),view:'customers'}, {label:t('nav_assessments','Vurderingsbibliotek')}],
    hosts:        [{label:t('nav_remote_access','Fjerntilgang')}, {label:t('bc_hosts_ssh','Verter')}],
    terminal:     [{label:t('nav_remote_access','Fjerntilgang'),view:'hosts'}, {label:'Terminal'}],
    rdp:          [{label:t('nav_remote_access','Fjerntilgang'),view:'hosts'}, {label:'RDP'}],
    ssh:          [{label:t('nav_remote_access','Fjerntilgang'),view:'hosts'}, {label:t('bc_ssh_keys','SSH-nøkler')}],
    network:      [{label:t('nav_network','Nettverk')}],
    vpn:          [{label:t('nav_network','Nettverk')}, {label:'VPN'}],
    tls:          [{label:t('nav_network','Nettverk')}, {label:'TLS Monitor'}],
    browser:      [{label:t('nav_tools','Verktøy')}, {label:'Nettleser'}],
    tailscale:    [{label:t('nav_tools','Verktøy')}, {label:'Tailscale'}],
    provision:    [{label:t('nav_tools','Verktøy')}, {label:t('bc_provisioning','Provisjonering')}],
    ai:           [{label:'Sybrt'}],
    integrations: [{label:t('nav_integrations')}],
    logs:         [{label:t('bc_log','Log')}],
    'customer-detail': [{label:t('nav_customers'),view:'customers'}, {label:t('bc_customer_detail','Customer detail')}],
  };
  var crumbs = map[name] || [{label:name}];
  if (crumbs.length <= 1) { bc.style.display = 'none'; return; }
  bc.style.display = 'block';
  items.innerHTML = crumbs.map(function(c, i) {
    var sep = i > 0 ? ' <span style="margin:0 var(--space-2);color:var(--text-dim);opacity:0.5;">/</span> ' : '';
    if (i < crumbs.length - 1 && c.view) {
      return sep + '<a href="#" class="hover-link" data-click-handler="showView" data-view="' + esc(c.view) + '" style="color:var(--text-muted);text-decoration:none;transition:color 0.15s;">' + esc(c.label) + '</a>';
    } else if (i < crumbs.length - 1) {
      return sep + '<span style="color:var(--text-muted);">' + esc(c.label) + '</span>';
    }
    return sep + '<span style="color:var(--text);font-weight:500;">' + esc(c.label) + '</span>';
  }).join('');
}

// ── View timer cleanup ────────────────────────────────────────────────────────
// Central registry of view-specific intervals to clear on view switch.
// Global timers (VPN badge, session timeout) are excluded.
var _viewTimers = [];
function _registerViewTimer(id) { if (id) _viewTimers.push(id); return id; }
function _cleanupViewTimers() {
  _viewTimers.forEach(function(id) { clearInterval(id); });
  _viewTimers = [];
  // Also clear known named timers
  if (typeof stopDashAutoRefresh === 'function') stopDashAutoRefresh();
  if (typeof stopAuditProgressPolling === 'function') stopAuditProgressPolling();
  if (typeof _logAutoRefreshTimer !== 'undefined' && _logAutoRefreshTimer) {
    clearInterval(_logAutoRefreshTimer); _logAutoRefreshTimer = null;
    var cb = document.getElementById('log-auto-refresh');
    if (cb) cb.checked = false;
  }
  if (typeof _dashRefreshInterval !== 'undefined' && _dashRefreshInterval) {
    clearInterval(_dashRefreshInterval); _dashRefreshInterval = null;
  }
  if (typeof _renewalScanTimer !== 'undefined' && _renewalScanTimer) {
    clearInterval(_renewalScanTimer); _renewalScanTimer = null;
  }
  if (typeof _priceScanTimer !== 'undefined' && _priceScanTimer) {
    clearInterval(_priceScanTimer); _priceScanTimer = null;
  }
}

// A script that owns a view says what to do when it opens with
// onViewShown(name, fn), instead of wrapping showView. The wrappers stacked:
// each called the one before it in load order, and a throw in one cut off
// every wrapper after it.
var _viewOpeners = {};

function onViewShown(name, fn) {
  (_viewOpeners[name] = _viewOpeners[name] || []).push(fn);
}

function showView(name) {
  _cleanupViewTimers();
  // Check for unsaved settings changes if the settings modal is open
  var settingsModal = document.getElementById('settings-modal');
  if (settingsModal && settingsModal.classList.contains('open') && _settingsDirty && _isSettingsDirty()) {
    if (!confirm(t('du_har_ulagrede_endringer_vil'))) return;
    _settingsSnapshot = null;
    _settingsDirty = false;
    settingsModal.classList.remove('open');
  }
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  var viewEl = document.getElementById('view-' + name);
  if (viewEl) { viewEl.classList.add('active'); viewEl.style.animation = 'view-fade-in 0.25s ease-out'; }

  // Highlight correct nav button
  // IA (frame 2a): Fjernaksess/Terminal/Nettleser/Workshop live under Verktøy;
  // Tailscale + Provisjonering under Nettverk. _remoteViews kept (empty) so the
  // branch below stays valid; hosts/terminal/rdp now highlight Verktøy.
  var _remoteViews = {};
  var _networkViews = {network:1, vpn:1, tls:1, tailscale:1, provision:1};
  var _toolViews = {hosts:1, terminal:1, rdp:1, ssh:1, browser:1};
  var _customerViews = {customers:1, home:1, audit:1, history:1, files:1, setup:1, 'customer-detail':1, 'history-report':1, 'policy-overview':1, 'policy-deploy':1, 'baseline-deploy':1, 'assessments':1};
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  if (_m365SubViews[name]) {
    const nb = document.getElementById('nav-customers');
    if (nb) nb.classList.add('active');
  } else if (_remoteViews[name]) {
    const nb = document.getElementById('nav-remote');
    if (nb) nb.classList.add('active');
  } else if (_networkViews[name]) {
    const nb = document.getElementById('nav-network');
    if (nb) nb.classList.add('active');
  } else if (_toolViews[name]) {
    const nb = document.getElementById('nav-tools');
    if (nb) nb.classList.add('active');
  } else if (_customerViews[name]) {
    const nb = document.getElementById('nav-customers');
    if (nb) nb.classList.add('active');
  } else {
    const nb = document.getElementById('nav-' + name);
    if (nb) nb.classList.add('active');
  }
  _syncBottomNav(name);

  // Show/hide M365 sub-tab bar
  var subBar = document.getElementById('m365-subtab-bar');
  if (subBar) {
    subBar.style.display = _m365SubViews[name] ? 'block' : 'none';
    // Highlight active sub-tab
    document.querySelectorAll('.m365-sub-btn').forEach(function(b) {
      var isCurrent = b.dataset.sub === name;
      b.style.borderBottom = isCurrent ? '2px solid var(--blue)' : 'none';
      b.style.color = isCurrent ? 'var(--blue)' : '';
    });
  }

  // Close mobile nav when a view is selected
  var nav = document.getElementById('main-nav');
  if (nav) nav.classList.remove('open');

  currentView = name;
  _updateBreadcrumb(name);

  // Show skeleton placeholders immediately before data loads
  if (name === 'overview') {
    if (_bulkAuditEventSource) {
    } else {
      document.getElementById('overview-content').innerHTML = skeletonHTML('dashboard');
      loadOverview();
    }
  } else if (name === 'home') {
    document.getElementById('home-content').innerHTML = skeletonHTML('home');
    loadStatus();
  } else if (name === 'customers') {
    document.getElementById('customers-content').innerHTML = skeletonHTML('customers');
    loadCustomers();
  } else if (name === 'files') {
    loadFiles();
  } else if (name === 'network') {
    loadNetworkDevices();
  } else if (name === 'history') {
    document.getElementById('history-content').innerHTML = skeletonHTML('history');
    loadHistory();
  } else if (name === 'integrations') {
    loadIntegrationStatus();
    unifiSmLoadSaved();
    fgApiLoadSaved();
    claudeLoadSaved();
  } else if (name === 'logs') {
    loadLogs();
  } else if (name === 'audit') {
    // Opening a view must never start work. Reconcile with the server instead:
    // the badge and this screen should show what is actually running, not what
    // some tab believed when it was last looked at.
    _reconcileAuditState();
  } else if (name === 'setup') {
    _renderSetupIdle();
  }
  // Lets CSS drop chrome a view replaces, like the bar's audit button on the
  // customer page, which has its own.
  document.body.dataset.view = name;
  // The customer page records its own address once it knows which customer.
  if (name !== 'customer-detail') syncRoute(name);
  (_viewOpeners[name] || []).forEach(function(fn) {
    try { fn(); } catch (e) { console.error('Opening view ' + name + ' failed:', e); }
  });
}

// ── Address bar ─────────────────────────────────────────────────────────────
// The view, and the customer it is about, live in the URL: Back, reload and a
// shared link land where they should. #/customer/<id> is a customer's page and
// #/<view> the rest. Applying a route sets a flag so the showView it causes
// does not push the same address again.
var _routeApplying = false;

function syncRoute(name, customerId) {
  if (_routeApplying || !name) return;
  var target = name === 'customer-detail' && customerId
    ? '#/customer/' + encodeURIComponent(customerId)
    : '#/' + name;
  if (location.hash !== target) history.pushState(null, '', target);
}

async function applyRoute() {
  var customer = /^#\/customer\/([^/]+)$/.exec(location.hash);
  var view = /^#\/([a-z0-9-]+)$/.exec(location.hash);
  _routeApplying = true;
  try {
    if (customer) {
      await overviewSelectCustomer(decodeURIComponent(customer[1]));
    } else if (view && document.getElementById('view-' + view[1])
        && (!_allowedViews.length || _allowedViews.indexOf(view[1]) !== -1)) {
      showView(view[1]);
    } else {
      showView('overview');
    }
  } finally {
    _routeApplying = false;
  }
}

window.addEventListener('popstate', function() { if (_currentUser) applyRoute(); });

// The one authority on whether an audit is running is the server. A client
// flag that outlives its run leaves a badge lit with nothing behind it.
async function _reconcileAuditState() {
  try {
    var d = await apiFetch('/api/audit/progress');
    if (!d || d.running === undefined) return;   // older server: leave as-is
    if (d.running && !auditRunning) {
      // Started elsewhere — another tab, a schedule, another technician.
      auditRunning = true;
      var ind = document.getElementById('audit-running-indicator');
      if (ind) ind.style.display = 'flex';
      _showAuditRunningChrome();
      startAuditProgressPolling();
      _watchAuditUntilServerIdle(true);   // we never had a stream to lose
    } else if (d.running) {
      _showAuditRunningChrome();
    } else if (auditRunning) {
      _finishAuditWithoutStream();
    } else {
      _clearStaleAuditBadge();
      if (currentView === 'audit') _renderAuditIdle();
    }
  } catch (_) { /* offline: say nothing rather than claim either state */ }
}

// The audit view's markup is written as though you can only ever arrive
// mid-run: a spinner, "Starting audit…", "0 / 0 sections", 0%. Open it when
// nothing is running and it announces a run that does not exist. These two
// functions give it the state it never had.
function _auditChrome() {
  return [
    document.getElementById('audit-status-bar'),
    document.querySelector('#view-audit .progress-row'),
    document.getElementById('section-table') ? document.getElementById('section-table').closest('.card') : null,
  ];
}

function _showAuditRunningChrome() {
  var idle = document.getElementById('audit-idle');
  if (idle) idle.style.display = 'none';
  _auditChrome().forEach(function(el) { if (el) el.style.display = ''; });
}

async function _renderAuditIdle() {
  var view = document.getElementById('view-audit');
  if (!view || auditRunning) return;

  // Nothing is running, so the running chrome is a lie. Put it away.
  _auditChrome().forEach(function(el) { if (el) el.style.display = 'none'; });
  var tbody = document.getElementById('section-tbody');
  if (tbody && !tbody.children.length) {
    var findings = document.getElementById('audit-findings');
    if (findings) findings.style.display = 'none';
  }

  var idle = document.getElementById('audit-idle');
  if (!idle) {
    idle = document.createElement('div');
    idle.id = 'audit-idle';
    idle.className = 'card';
    var bar = document.getElementById('audit-status-bar');
    if (bar && bar.parentNode) bar.parentNode.insertBefore(idle, bar); else view.appendChild(idle);
  }
  idle.style.display = '';

  var when = '';
  try {
    var dash = await apiFetch('/api/dashboard');
    if (dash && dash.run_date) when = formatRunName(dash.run_date);
  } catch (_) { /* the last run's date is a nicety, not a precondition */ }

  idle.innerHTML =
      '<div class="card-title">' + esc(t('hdr_audit_idle')) + '</div>'
    + '<div style="font-size:13px;color:var(--text-muted);line-height:1.6;margin-bottom:16px;">'
    +   esc(t('msg_audit_idle_body'))
    + '</div>'
    + '<div style="font-size:13px;color:var(--text-muted);margin-bottom:20px;">'
    +   esc(t('lbl_last_audit')) + ': '
    +   '<strong style="color:var(--text);">' + esc(when || t('lbl_never')) + '</strong>'
    + '</div>'
    + '<div style="display:flex;gap:8px;flex-wrap:wrap;">'
    +   '<button data-write class="btn btn-primary" data-click-handler="startAudit">'
    +     icon('play', 14) + ' ' + esc(t('btn_run_audit')) + '</button>'
    +   '<button class="btn btn-default" data-click-handler="showView" data-view="home">'
    +     esc(t('btn_see_last_result')) + '</button>'
    +   '<button class="btn btn-default" data-click-handler="showView" data-view="history">'
    +     esc(t('nav_history', 'History')) + '</button>'
    + '</div>';

  if (typeof applyWriteCapability === 'function') applyWriteCapability();
}

function _clearStaleAuditBadge() {
  auditRunning = false;
  stopAuditProgressPolling();
  _hideAuditProgressBar();
  var ind = document.getElementById('audit-running-indicator');
  if (ind) ind.style.display = 'none';
  var back = document.getElementById('audit-back-btn');
  if (back) back.disabled = false;
}

function switchNetSub(btn, tabId) {
  document.querySelectorAll('.net-sub-content').forEach(function(c) { c.style.display = 'none'; });
  document.querySelectorAll('.net-sub-btn').forEach(function(b) {
    b.classList.remove('active');
    b.style.borderBottom = 'none';
    b.style.color = '';
  });
  document.getElementById(tabId).style.display = 'block';
  btn.classList.add('active');
  btn.style.borderBottom = '2px solid var(--blue)';
  btn.style.color = 'var(--blue)';

  if (tabId === 'net-fortigates') dashLoadFortiGates();
  if (tabId === 'net-unifi') dashLoadUnifiAll();
  if (tabId === 'net-pentest' && typeof loadPentestCapabilities === 'function') loadPentestCapabilities();
}

// ── Home: load status ──────────────────────────────────────────────────────────
async function loadStatus() {
  const box = document.getElementById('home-content');
  const d = await apiFetch('/api/status');
  if (d) {
    renderHome(d);
    if (d.has_config && d.has_credentials) {
      _loadHealthGrid();
      // Fetch last audit date for active customer bar
      try {
        var dash = await apiFetch('/api/dashboard');
        if (dash && dash.run_date) {
          var lel = document.getElementById('active-customer-last-audit');
          if (lel) lel.textContent = auditAgeLabel(dash.run_date);
        }
      } catch(e) {}
    }
  } else {
    box.innerHTML = `<div class="alert alert-error">${t('err_could_not_load_status')}</div>`;
  }
}

async function _loadHealthGrid() {
  try {
    var d = await apiFetch('/api/dashboard');
    if (!d || !d.has_data) return;
    var m = d.metrics || {};
    var grid = document.getElementById('home-health-grid');
    if (!grid) return;

    function healthCard(label, value, suffix, thresholds, hint) {
      var v = parseFloat(value);
      var color = 'var(--text-dim)';
      if (!isNaN(v)) {
        if (thresholds.red && v < thresholds.red) color = 'var(--red)';
        else if (thresholds.orange && v < thresholds.orange) color = 'var(--orange)';
        else color = 'var(--green)';
      }
      var dot = '<span style="width:8px;height:8px;border-radius:50%;background:' + color + ';display:inline-block;"></span>';
      var tipText = hint || '';
      if (thresholds.red) tipText += (tipText ? ' · ' : '') + '< ' + thresholds.red + ' = ' + t('status_error','critical');
      if (thresholds.orange) tipText += (tipText ? ' · ' : '') + '< ' + thresholds.orange + ' = ' + t('lbl_needs_attention','warning');
      return '<div style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-3);background:var(--bg);border-radius:var(--radius-md);border:1px solid var(--border);cursor:default;transition:border-color var(--duration-fast);" class="hover-border-accent"' + (tipText ? ' title="' + esc(tipText) + '"' : '') + '>'
        + dot
        + '<div style="flex:1;"><div style="font-size:var(--font-xs);color:var(--text-muted);">' + esc(label) + '</div></div>'
        + '<div style="font-size:var(--font-md);font-weight:700;color:' + color + ';">' + (isNaN(v) ? '-' : v + esc(suffix||'')) + '</div></div>';
    }

    grid.style.display = 'grid';
    grid.style.cssText = 'display:grid;grid-template-columns:repeat(3,1fr);gap:var(--space-3);margin-top:var(--space-4);';
    grid.innerHTML =
      healthCard(t('lbl_risk','Risk Score'), m.risk_score, '', {red:50, orange:70}) +
      healthCard('MFA', m.mfa_coverage_pct, '%', {red:80, orange:95}) +
      healthCard(t('lbl_secure_score','Secure Score'), m.secure_score_pct, '%', {red:50, orange:75}) +
      healthCard(t('lbl_users','Users'), m.total_users, '', {}) +
      healthCard(t('lbl_without_mfa','Without MFA'), m.users_no_mfa, '', {red:999, orange:1}) +
      healthCard(t('lbl_ca_policies','CA Policies'), m.ca_policies_enabled, '', {red:1, orange:3});
  } catch(e) {}
}

function _updateActiveCustomerBar(d) {
  var bar = document.getElementById('active-customer-bar');
  if (!bar) return;
  var nameEl = document.getElementById('active-customer-name');
  var domEl = document.getElementById('active-customer-domain');
  var gradeEl = document.getElementById('active-customer-grade');
  var lastEl = document.getElementById('active-customer-last-audit');
  var licBtn = document.getElementById('active-bar-licenses-btn');

  // Always show the bar once authenticated — even without an active
  // customer, the bar is the persistent entry point to the switcher.
  bar.style.display = 'flex';

  var c = (d && d.customer) || {};
  var name = c.name || '';

  // The bar's audit button acts on the active customer, so it exists only
  // when there is one.
  var runBtn = document.getElementById('context-run-audit');
  if (runBtn) runBtn.classList.toggle('hidden', !name);

  if (!name) {
    // Placeholder state: "Velg kunde" in dim italic, and collapse the
    // empty domain/grade spans so the trigger's flex-gap doesn't leave
    // the chevron floating across empty space.
    nameEl.textContent = t('lbl_select_customer', 'Velg kunde');
    nameEl.style.color = 'var(--text-dim)';
    nameEl.style.fontStyle = 'italic';
    if (domEl) domEl.style.display = 'none';
    if (gradeEl) gradeEl.style.display = 'none';
    if (lastEl) lastEl.textContent = '';
    if (licBtn) licBtn.style.display = 'none';
    return;
  }

  // Active customer state
  nameEl.style.color = '';
  nameEl.style.fontStyle = '';
  nameEl.textContent = name;
  if (domEl) {
    domEl.style.display = '';
    domEl.textContent = c.domain || '';
  }
  if (gradeEl) {
    gradeEl.style.display = '';
    if (d && d.risk_grade) {
      // Tinted, grade-coloured pill "B · 78/100" (frame 3a). color-mix keeps
      // the tint theme-adaptive without a second light-theme definition.
      var gvar = {A:'var(--green)',B:'var(--blue)',C:'var(--orange)',D:'var(--red)',F:'var(--red)'}[d.risk_grade] || 'var(--text-muted)';
      var scoreTxt = (d.risk_score !== undefined && d.risk_score !== null && d.risk_score !== '') ? ' · ' + d.risk_score + '/100' : '';
      gradeEl.innerHTML = '<span class="context-grade-pill" style="color:' + gvar + ';background:color-mix(in srgb, ' + gvar + ' 12%, transparent);">' + esc(d.risk_grade + scoreTxt) + '</span>';
    } else {
      gradeEl.innerHTML = '';
    }
  }
  if (lastEl && d && d.run_date) {
    // Relative ("Auditert for 3 d siden", frame 3a) instead of a bare date.
    lastEl.textContent = auditAgeLabel(d.run_date);
  } else if (lastEl) {
    lastEl.textContent = '';
  }
  // Show/hide licenses button based on ALSO linkage
  if (licBtn) {
    var alsoId = c.also_account_id || '';
    if (alsoId) {
      licBtn.style.display = '';
      licBtn.onclick = function(){ loadCustomerLicenses(alsoId); };
    } else {
      licBtn.style.display = 'none';
    }
  }
}

function renderHome(d) {
  const box = document.getElementById('home-content');
  _updateActiveCustomerBar(d);

  if (!d.has_config) {
    box.innerHTML = `
      <div class="empty-state">
        <div class="empty-title">${t('msg_no_customer_configured')}</div>
        <div class="empty-desc">
          ${t('msg_first_time_setup_desc').replace('\n', '<br>')}
        </div>
        <button class="btn btn-primary" data-click-handler="startSetup">${t('btn_start_setup')}</button>
      </div>`;
    return;
  }

  const c = d.customer;
  let warnsHtml = '';
  if (c.warns && c.warns.length > 0) {
    window._lastAuditWarns = c.warns;
    const items = c.warns.map(w => `<li>${esc(w)}</li>`).join('');
    warnsHtml = `<div class="warn-badge"><ul>${items}</ul></div>`;
  }

  const hasCredentials = d.has_credentials !== false;
  const runDisabled = d.audit_running ? 'disabled' : (!hasCredentials ? 'disabled' : '');
  const runLabel    = d.audit_running ? t('btn_audit_running') : (!hasCredentials ? t('msg_missing_m365_setup','Missing M365 setup') : t('btn_run_audit'));

  box.innerHTML = `
    <div id="expiry-banner-area"></div>
    <div class="card">
      <div class="card-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
        ${t('hdr_active_customer')}
        <span style="margin-left:auto;font-size:11px;font-weight:400;"><a href="#" data-click-handler="showView" data-view="customers" style="color:var(--blue);text-decoration:none;">${t('tip_all_customers_link')}</a></span>
      </div>
      <div class="customer-name">${esc(c.name)}</div>
      <div class="customer-domain">${esc(c.domain)}</div>
      <div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin-top:6px;">
        <span id="tag-pills-home">${tagPillsHtml(c.tags || [])}</span>
        <button class="btn btn-ghost" style="padding:1px 6px;font-size:10px;border:1px dashed var(--border);border-radius:10px;" data-click-handler="openTagEditor" data-customer-id="${esc(d.active_id)}" data-tags="${esc(JSON.stringify(c.tags||[]))}">${t('tags')}</button>
      </div>
      <div id="tag-editor-${(d.active_id||'').replace(/[^a-zA-Z0-9_-]/g,'_')}" style="display:none;margin-top:8px;padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:8px;"></div>
      <div class="meta-row">
        <div class="meta-item"><strong>${esc(c.setup_date)}</strong>${t('lbl_setup_date')}</div>
      </div>
      ${warnsHtml}
      <div id="home-health-grid" style="display:none;margin-top:var(--space-4);"></div>
      ${hasCredentials ? `
      <div class="btn-row">
        <button class="btn btn-primary tooltip" data-tip="${t('tip_run_full_audit','Runs a full security check of the customer M365/Azure environment')}" data-click-handler="startAudit" ${runDisabled}>${runLabel} <kbd style="font-size:9px;opacity:0.6;margin-left:4px;padding:1px 4px;background:rgba(255,255,255,0.15);border-radius:3px;">Ctrl+Shift+A</kbd></button>
        <button class="btn btn-default tooltip" data-tip="${t('tip_check_permissions','Verifies that all required Graph API permissions are granted')}" data-click-handler="checkPermissions">${t('btn_check_permissions')}</button>
        <button class="btn btn-warning" data-click-handler="renewCreds">${t('btn_renew_credentials')}</button>
        <button class="btn btn-ghost" data-click-handler="showView" data-view="customers">${t('btn_switch_customer')}</button>
      </div>` : `
      <div style="padding:14px;margin-bottom:8px;background:rgba(210,153,34,0.1);border:1px solid rgba(210,153,34,0.3);border-radius:8px;font-size:13px;color:var(--orange);">
        ${t('msg_no_m365_configured','This customer does not have M365 access configured yet.')}
      </div>
      <div class="btn-row">
        <button class="btn btn-primary" data-click-handler="startSetup">${t('btn_setup_m365','Setup M365 access')}</button>
        <button class="btn btn-ghost" data-click-handler="showView" data-view="customers">${t('btn_switch_customer')}</button>
      </div>`}

      <div id="scope-panel" class="tooltip" data-tip="${t('tip_select_audit_sections','Select which sections to include in the audit')}" style="margin-top:14px;border-top:1px solid var(--border);padding-top:12px;">
        <div style="display:flex;align-items:center;cursor:pointer;user-select:none;" data-click-handler="toggleScopePanel">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;flex-shrink:0;"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          <span style="font-weight:600;font-size:13px;">${t('hdr_select_sections')}</span>
          <span id="scope-toggle-icon" style="margin-left:6px;font-size:10px;color:var(--text-muted);transition:transform .2s;">&#9654;</span>
          <span id="scope-summary" style="margin-left:auto;font-size:11px;color:var(--text-muted);"></span>
        </div>
        <div id="scope-body" style="display:none;margin-top:10px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
            <select id="preset-select" style="font-size:12px;padding:3px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--text);" data-change-handler="applyPreset">
              <option value="">${t('lbl_select_preset')}</option>
            </select>
            <button class="btn btn-ghost" style="padding:2px 10px;font-size:11px;" data-click-handler="saveCustomPreset">${t('btn_save_as_preset')}</button>
            <button id="preset-delete-btn" class="btn btn-ghost" style="padding:2px 10px;font-size:11px;display:none;color:var(--red);" data-click-handler="deleteCustomPreset">${t('btn_delete_preset')}</button>
          </div>
          <div style="display:flex;gap:6px;margin-bottom:10px;">
            <button class="btn btn-ghost" style="padding:2px 10px;font-size:11px;" data-click-handler="scopeSelectAll">${t('btn_select_all')}</button>
            <button class="btn btn-ghost" style="padding:2px 10px;font-size:11px;" data-click-handler="scopeDeselectAll">${t('btn_deselect_all')}</button>
          </div>
          <div id="scope-sections" style="display:flex;gap:24px;flex-wrap:wrap;"></div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:16px;" id="customer-notes-card">
      <div class="card-title" style="cursor:pointer;" data-click-handler="toggleNotesCard">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
        ${t('hdr_customer_notes')}
        <span id="notes-toggle-icon" style="margin-left:auto;font-size:11px;color:var(--text-muted);font-weight:400;">&#9660;</span>
      </div>
      <div id="notes-body">
        <textarea id="customer-notes-textarea"
          placeholder="${t('tip_notes_placeholder')}"
          style="width:100%;min-height:120px;resize:vertical;font-family:var(--mono);font-size:13px;white-space:pre-wrap;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:10px;box-sizing:border-box;line-height:1.5;"
        ></textarea>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;">
          <span id="notes-save-status" style="font-size:11px;color:var(--text-dim);"></span>
          <span id="notes-last-saved" style="font-size:11px;color:var(--text-dim);"></span>
        </div>
      </div>
    </div>

    <!-- Module cards removed · FortiGate and UniFi are now fully integrated -->

    <div class="card" style="margin-top:16px;" id="activity-log-card">
      <div class="card-title" style="cursor:pointer;" data-click-handler="toggleActivityLog">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 8v4l3 3"/><circle cx="12" cy="12" r="10"/></svg>
        ${t('hdr_activity_log')}
        <span id="activity-log-toggle" style="margin-left:auto;font-size:11px;color:var(--text-muted);font-weight:400;">&#9660;</span>
      </div>
      <div id="activity-log-body">
        <div id="activity-log-list" style="display:flex;flex-direction:column;gap:0;"></div>
        <div id="activity-log-more" style="text-align:center;margin-top:8px;"></div>
      </div>
    </div>`;

  // Load dashboard if config exists
  if (d.has_config) {
    loadDashboard();
    var findingsBox = document.createElement('div');
    findingsBox.id = 'home-findings';
    findingsBox.className = 'card home-findings';
    var firstCard = box.querySelector('.card');
    if (firstCard) firstCard.insertAdjacentElement('afterend', findingsBox);
    else box.appendChild(findingsBox);
    mountCustomerFindings(findingsBox, d.active_id);
  }

  // Load expiry banner
  loadExpiryBanner();

  // Load activity log
  loadActivityLog();

  // Load customer notes
  loadCustomerNotes();
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function _vpnStatField(label, value) {
  if (!value) return '';
  return '<div><div style="color:var(--text-dim);">' + esc(label) + '</div><div style="font-family:var(--mono);color:var(--text);font-weight:600;">' + esc(String(value)) + '</div></div>';
}

// app-customer-detail.js used to declare a second _formatBytes. It loads later,
// so its version was the one every caller got and this one never ran; it is
// the one kept here.
function _formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  var units = ['B','KB','MB','GB','TB'];
  var i = Math.floor(Math.log(bytes) / Math.log(1024));
  if (i >= units.length) i = units.length - 1;
  return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
}

function timeAgo(dateStr) {
  if (!dateStr) return '';
  try {
    var d = new Date(dateStr);
    var now = Date.now();
    var diff = Math.floor((now - d.getTime()) / 1000);
    if (diff < 60) return t('time_just_now','just now');
    if (diff < 3600) return Math.floor(diff/60) + ' ' + t('time_min_ago','min ago');
    if (diff < 86400) return Math.floor(diff/3600) + ' ' + t('time_hours_ago','hours ago');
    if (diff < 604800) return Math.floor(diff/86400) + ' ' + t('time_days_ago','days ago');
    return d.toLocaleDateString(_lang === 'en' ? 'en-GB' : 'nb-NO', {day:'2-digit',month:'short'});
  } catch(e) { return dateStr; }
}

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Opens a generated HTML report (tenant and scan data) in a new window. The
// report is parsed inside an iframe sandboxed without allow-scripts, so no
// handler or script in it can run as the app. allow-same-origin and
// allow-modals are only there for this wrapper: it sizes the frame to the
// report and sends Ctrl+P to the report itself, which then paginates at paper
// width instead of printing one screen of the wrapper.
function openReportWindow(html, title) {
  var win = window.open('', '_blank');
  if (!win) return null;
  var doc = win.document;
  doc.title = title;
  doc.body.style.margin = '0';
  var frame = doc.createElement('iframe');
  frame.setAttribute('sandbox', 'allow-same-origin allow-modals');
  frame.title = title;
  frame.style.cssText = 'display:block;width:100%;height:100vh;border:0;';
  function fit() {
    var root = frame.contentDocument && frame.contentDocument.documentElement;
    if (!root) return;
    frame.style.height = '0';
    frame.style.height = root.scrollHeight + 'px';
  }
  function printReport(e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'p' || e.key === 'P')) {
      e.preventDefault();
      frame.contentWindow.print();
    }
  }
  frame.addEventListener('load', function() {
    fit();
    frame.contentDocument.addEventListener('keydown', printReport);
  });
  win.addEventListener('resize', fit);
  doc.addEventListener('keydown', printReport);
  frame.srcdoc = /* safe-html: parsed in the script-less sandbox above */ html;
  doc.body.appendChild(frame);
  return win;
}

// ═══════════════════════════════════════════════════════════════════
// CODE SPLIT — app.js is core only now (auth, i18n, api, nav, home,
// helpers). Feature sections live in their own files:
//   app-setup.js            customer setup: actions, credentials, PKCE
//   app-audit.js            remediation, audit scope/presets/flow/history
//   app-settings.js         webhooks, branding, self-update, users, backup
//   app-network.js          files, UniFi devices, subnet scan, config backup
//   app-customers.js        notes, expiry banner, IT Glue picker, tags,
//                           management, quick switcher, bulk + export
//   app-customer-detail.js  the full customer detail view
//   app-dashboard.js        alerts dashboard, overview, charts, health
//   app-integrations.js     integrations view + GDAP
//   app-chrome.js           theme, notifications, shortcuts, onboarding,
//                           offline indicator, bootstrap (checkAuth)
//   app-infra.js / app-also.js / app-tailscale.js / app-tls.js
//   app-policy-deploy.js / app-baseline-deploy.js / app-policy-overview.js
//   app-assessments.js
// ═══════════════════════════════════════════════════════════════════
