
// ── Inline SVG icon helper ───────────────────────────────────────────────────
function icon(name, size) {
  var s = size || 16;
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

// CSP migration: static controls use named data attributes instead of inline
// JavaScript. Keep an explicit map — never eval an attribute or expose every
// global function as a callable DOM action.
var _delegatedClickHandlers = Object.freeze({
  runSelfUpdate: function() { return runSelfUpdate(); },
  copyDeviceUrl: function() { return copyDeviceUrl(); },
  closeReportViewer: function() { return closeReportViewer(); },
  doSetup: function() { return doSetup(); },
  doLogin: function() { return doLogin(); },
  toggleMobileNav: function() { return toggleMobileNav(); },
  openLatestReport: function() { return openLatestReport(); },
  toggleCommandPalette: function() { return toggleCommandPalette(); },
  toggleNotifications: function() { return toggleNotifications(); },
  markAllNotificationsRead: function() { return markAllNotificationsRead(); },
  promptPwaInstall: function() { return promptPwaInstall(); },
  toggleTheme: function() { return toggleTheme(); },
  doLogout: function() { return doLogout(); },
  openChangelogModal: function() { return openChangelogModal(); },
  loadCustomerLicensesFromActive: function() { return loadCustomerLicensesFromActive(); },
  dashExportCurrentTab: function() { return dashExportCurrentTab(); },
  exportDashboardExcel: function() { return exportDashboardExcel(); },
  copyOverviewToClipboard: function() { return copyOverviewToClipboard(); },
  generateQBR: function() { return generateQBR(); },
  closeSettings: function() { return closeSettings(); },
  closePermissionsModal: function() { return closePermissionsModal(); },
  closeShortcutsModal: function() { return closeShortcutsModal(); },
  closeChangelogModal: function() { return closeChangelogModal(); },
  aiClearChat: function() { return aiClearChat(); },
  aiSend: function() { return aiSend(); },
  alertRunCheckNow: function() { return alertRunCheckNow(); },
  alsoSaveConfig: function() { return alsoSaveConfig(); },
  alsoSyncCustomers: function() { return alsoSyncCustomers(); },
  alsoTestConnection: function() { return alsoTestConnection(); },
  auditBack: function() { return auditBack(); },
  backupEncryptionKey: function() { return backupEncryptionKey(); },
  bulkDeleteCustomers: function() { return bulkDeleteCustomers(); },
  bulkTagCustomers: function() { return bulkTagCustomers(); },
  claudeCheckCli: function() { return claudeCheckCli(); },
  claudeSaveSettings: function() { return claudeSaveSettings(); },
  claudeTestConnection: function() { return claudeTestConnection(); },
  clearBulkSelection: function() { return clearBulkSelection(); },
  clearLogs: function() { return clearLogs(); },
  confirmITGlueOrgPick: function() { return confirmITGlueOrgPick(); },
  copyCode: function() { return copyCode(); },
  copyEncryptionKey: function() { return copyEncryptionKey(); },
  copyLogs: function() { return copyLogs(); },
  createBackup: function() { return createBackup(); },
  createUser: function() { return createUser(); },
  dashUnifiRefresh: function() { return dashUnifiRefresh(); },
  deleteSelectedRuns: function() { return deleteSelectedRuns(); },
  executeITGlueUpload: function() { return executeITGlueUpload(); },
  exportCSV: function() { return exportCSV(); },
  exportCustomersJSON: function() { return exportCustomersJSON(); },
  fgApiSave: function() { return fgApiSave(); },
  fgApiTest: function() { return fgApiTest(); },
  fgBootstrap: function() { return fgBootstrap(); },
  fgDownloadCredentials: function() { return fgDownloadCredentials(); },
  fgPollAll: function() { return fgPollAll(); },
  gdapDiscoverCustomers: function() { return gdapDiscoverCustomers(); },
  gdapImportSelected: function() { return gdapImportSelected(); },
  gdapSaveConfig: function() { return gdapSaveConfig(); },
  gdapTestConnection: function() { return gdapTestConnection(); },
  hostsAdd: function() { return hostsAdd(); },
  hostsHealthAll: function() { return hostsHealthAll(); },
  itglueSyncAllDocumentation: function() { return itglueSyncAllDocumentation(); },
  loadConfigBackups: function() { return loadConfigBackups(); },
  loadFiles: function() { return loadFiles(); },
  loadLogs: function() { return loadLogs(); },
  migrateEncryption: function() { return migrateEncryption(); },
  openFolder: function() { return openFolder(); },
  openITGlueImport: function() { return openITGlueImport(); },
  openManualCustomer: function() { return openManualCustomer(); },
  openMoreSheet: function() { return openMoreSheet(); },
  openPrivateBrowser: function() { return openPrivateBrowser(); },
  openReportsFolder: function() { return openReportsFolder(); },
  provisionStart: function() { return provisionStart(); },
  resetAuditDir: function() { return resetAuditDir(); },
  resetBrandColor: function() { return resetBrandColor(); },
  restoreBackup: function() { return restoreBackup(); },
  restoreEncryptionKey: function() { return restoreEncryptionKey(); },
  runCmsScan: function() { return runCmsScan(); },
  runComparison: function() { return runComparison(); },
  runCredentialTest: function() { return runCredentialTest(); },
  runDnsPentest: function() { return runDnsPentest(); },
  runITGlueImport: function() { return runITGlueImport(); },
  runNetworkQuickAudit: function() { return runNetworkQuickAudit(); },
  runPentest: function() { return runPentest(); },
  runSegTest: function() { return runSegTest(); },
  runSmbEnum: function() { return runSmbEnum(); },
  runSubnetScan: function() { return runSubnetScan(); },
  runTakeoverCheck: function() { return runTakeoverCheck(); },
  runTlsAudit: function() { return runTlsAudit(); },
  saveEmailSettings: function() { return saveEmailSettings(); },
  saveITGlueSettings: function() { return saveITGlueSettings(); },
  saveSettings: function() { return saveSettings(); },
  saveWebhookSettings: function() { return saveWebhookSettings(); },
  showAddUserForm: function() { return showAddUserForm(); },
  showRestoreKeyInput: function() { return showRestoreKeyInput(); },
  sshShowExec: function() { return sshShowExec(); },
  sshShowKeys: function() { return sshShowKeys(); },
  startSetup: function() { return startSetup(); },
  submitManualCustomer: function() { return submitManualCustomer(); },
  taskSchedRefresh: function() { return taskSchedRefresh(); },
  termConnect: function() { return termConnect(); },
  termDisconnect: function() { return termDisconnect(); },
  testAutotask: function() { return testAutotask(); },
  testMyITProcess: function() { return testMyITProcess(); },
  testEmail: function() { return testEmail(); },
  testITGlue: function() { return testITGlue(); },
  testWebhook: function() { return testWebhook(); },
  tsSaveConfig: function() { return tsSaveConfig(); },
  tsTestConnection: function() { return tsTestConnection(); },
  unifiSmAuth: function() { return unifiSmAuth(); },
  unifiSmLoadCoverage: function() { return unifiSmLoadCoverage(); },
  unifiSmLoadSites: function() { return unifiSmLoadSites(); },
  unifiSmSave: function() { return unifiSmSave(); },
  unifiSmSaveController: function() { return unifiSmSaveController(); },
  unifiSmTestController: function() { return unifiSmTestController(); },
  uniwebSaveConfig: function() { return uniwebSaveConfig(); },
  uniwebSync: function() { return uniwebSync(); },
  uploadLogo: function() { return uploadLogo(); },
  vpnLoadProfiles: function() { return vpnLoadProfiles(); },
  vpnShowCreate: function() { return vpnShowCreate(); },
  vpnShowImport: function() { return vpnShowImport(); },
  workshopAddFollowup: function() { return workshopAddFollowup(); },
  workshopAddWishlist: function() { return workshopAddWishlist(); },
  workshopLoad: function() { return workshopLoad(); },
});

document.addEventListener('click', function(event) {
  var control = event.target.closest('[data-click-handler]');
  if (!control) return;
  var handler = _delegatedClickHandlers[control.getAttribute('data-click-handler')];
  if (handler) handler();
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
        const r = await fetch('/static/ui_i18n.json?v=3027');
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
// Generates consistent markup for "no X yet" states with an optional
// call-to-action button row. Use in place of ad-hoc
//   '<div style="...">No data</div>'
// strings.
//   emptyStateHTML({
//     icon: '📭', title: 'Ingen enheter', desc: 'Legg til din første…',
//     actions: [{ label: '+ Legg til', onclick: 'addHost()', primary: true }],
//     variant: 'inline',   // or omit for full-card
//   })
function emptyStateHTML(opts) {
  opts = opts || {};
  var cls = opts.variant === 'inline' ? 'empty-state-inline' : 'empty-state';
  var parts = ['<div class="' + cls + '">'];
  if (opts.icon) parts.push('<div class="empty-icon">' + opts.icon + '</div>');
  if (opts.title) parts.push('<div class="empty-title">' + esc(opts.title) + '</div>');
  if (opts.desc) parts.push('<div class="empty-desc">' + esc(opts.desc) + '</div>');
  var actions = opts.actions || [];
  if (actions.length) {
    parts.push('<div class="empty-actions">');
    actions.forEach(function(a) {
      var btnCls = a.primary ? 'btn btn-primary' : 'btn btn-default';
      // onclick is a trusted developer-provided string (call site literal).
      parts.push('<button class="' + btnCls + '" onclick="' + a.onclick + '">' + esc(a.label) + '</button>');
    });
    parts.push('</div>');
  }
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
            icon: icon('clock', 16),
            action: function(){ overviewSelectCustomer(rid); },
            type: 'recent'
          });
        }
      });
    }
  }

  // Pages / Navigation
  var pages = [
    {label:t('nav_dashboard','Dashboard'), action:function(){showView('overview')},  section:t('nav_dashboard'), icon:icon('grid',16)},
    {label:t('nav_customers','Customers'), action:function(){showView('customers')}, section:t('nav_customers'), icon:icon('users',16)},
    {label:t('nav_m365_status'),     action:function(){showView('home')},      section:t('nav_customers'), icon:icon('cloud',16)},
    {label:t('nav_history','History'), action:function(){showView('history')},    section:t('nav_customers'), icon:icon('calendar',16)},
    {label:t('bc_hosts_ssh','Hosts'), action:function(){showView('hosts')},      section:t('nav_remote_access','Fjernaksess'),    icon:icon('monitor',16)},
    {label:t('bc_network','FortiGate / UniFi'), action:function(){showView('network')},    section:t('nav_network','Nettverk'),    icon:icon('globe',16)},
    {label:'VPN',             action:function(){showView('vpn')},        section:t('nav_network','Nettverk'),    icon:icon('lock',16)},
    {label:'TLS Monitor',     action:function(){showView('tls')},        section:t('nav_network','Nettverk'),    icon:icon('shield',16)},
    {label:t('nav_browser2','Browser'), action:function(){showView('browser')}, section:t('nav_tools','Verktøy'),    icon:icon('globe',16)},
    {label:'Tailscale',       action:function(){showView('tailscale')},  section:t('nav_tools','Verktøy'),    icon:icon('link',16)},
    {label:t('bc_provisioning','Provisjonering'), action:function(){showView('provision')},  section:t('nav_tools','Verktøy'),    icon:icon('gear',16)},
    {label:'Sybrt',           action:function(){showView('ai')},         section:'',                 icon:icon('sparkle',16)},
    {label:t('nav_integrations','Integrations'), action:function(){showView('integrations')},section:'',                icon:icon('plug',16)},
    {label:t('bc_log','Log'), action:function(){showView('logs')},        section:'',                icon:icon('document',16)},
    {label:t('hdr_settings','Settings'), action:function(){openSettings()}, section:'',                icon:icon('gear',16)},
    {label:t('tab_users','Users'),     action:function(){openSettings();setTimeout(function(){switchSettingsTab(document.querySelectorAll('.settings-tab-btn')[4],'stab-users')},100)}, section:t('hdr_settings'), icon:icon('users',16)},
    {label:t('hdr_branding','Branding'), action:function(){openSettings();setTimeout(function(){switchSettingsTab(document.querySelectorAll('.settings-tab-btn')[1],'stab-branding')},100)}, section:t('hdr_settings'), icon:icon('palette',16)},
  ];
  pages.forEach(function(p) {
    if (!q || p.label.toLowerCase().includes(q) || (p.section||'').toLowerCase().includes(q))
      results.push({label:p.label, hint:p.section, icon:p.icon, action:p.action, type:'page'});
  });

  // Actions
  var actions = [
    {label:t('btn_run_audit'),       action:function(){showView('home');setTimeout(startAudit,200)}, hint:'Ctrl+Shift+A', icon:icon('play',16)},
    {label:t('hdr_settings','Settings'),      action:function(){openSettings()},                              hint:'Ctrl+,',       icon:icon('gear',16)},
    {label:t('btn_export_excel','Export Excel'), action:function(){exportDashboardExcel()},                    hint:'',             icon:icon('chart',16)},
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
          icon: icon('building', 16),
          action: function(){ apiFetch('/api/customers/switch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer_id:c._id})}).then(function(){showView('home');loadStatus();}); },
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
          icon: icon('warning', 16),
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
      html += '<div class="cmd-item" tabindex="-1" onclick="closeCommandPalette();(' + '_cmdActions['+i+']' + ')()" style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-2) var(--space-5);cursor:pointer;transition:background 0.1s;border-radius:0;">'
        + '<span style="width:24px;flex-shrink:0;display:flex;align-items:center;justify-content:center;color:var(--text-muted);">' + r.icon + '</span>'
        + '<span style="flex:1;font-size:var(--font-base);color:var(--text);">' + esc(r.label) + '</span>'
        + (r.hint ? '<span style="font-size:var(--font-xs);color:var(--text-dim);">' + esc(r.hint) + '</span>' : '')
        + '</div>';
    });
  }
  document.getElementById('cmd-results').innerHTML = html;
  // Store action refs for onclick
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
    '<button class="toast-close" onclick="dismissToast(this.parentNode)" aria-label="' + t('btn_close') + '">&times;</button>';
  container.appendChild(toast);
  if (duration > 0) {
    setTimeout(function() { dismissToast(toast); }, duration);
  }
  return toast;
}

function showToastWithRetry(message, retryFn, type) {
  if (type === undefined) type = 'error';
  var container = document.getElementById('toast-container');
  if (!container) return;
  var toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.innerHTML = '<div class="toast-body">' + esc(message) +
    '<div class="toast-actions"><button onclick="dismissToast(this.closest(\'.toast\'));(' +
    'window._toastRetryFns[' + _toastRetryId + '])()">' +
    t('toast_retry') + '</button></div></div>' +
    '<button class="toast-close" onclick="dismissToast(this.parentNode)" aria-label="' + t('btn_close') + '">&times;</button>';
  if (!window._toastRetryFns) window._toastRetryFns = {};
  window._toastRetryFns[_toastRetryId] = retryFn;
  _toastRetryId++;
  container.appendChild(toast);
  return toast;
}
var _toastRetryId = 0;

function dismissToast(el) {
  if (!el || el.classList.contains('removing')) return;
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
      _allowedViews = _me.views || [];
      hideLoginView(); updateUserDisplay(); _postAuthInit();
    }
  } catch(e) { console.error('Request failed:', e); showLoginView('login'); }
}

function _postAuthInit() {
  loadStatus();
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
}

// A gate answers "may this be seen at all", never "is this showing right now".
// Writing style.display='' on everything allowed answered the second question
// too, and wiped out whatever the element's own state had decided. The audit
// badge carries a view gate and hides itself when no audit is running, so
// every page load un-hid it and announced a run that was not happening —
// nav-logs, nav-docs and the connection chip are all state-driven the same way.
// Hiding via a class leaves that state untouched, and !important still beats
// an inline display on the elements a user genuinely may not see.
function _setGated(el, allowed) {
  el.classList.toggle('gated-hidden', !allowed);
}

function applyWriteCapability() {
  var write = canWrite();
  document.body.classList.toggle('is-readonly', !write);
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
    var res = await fetch('/api/auth/login', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    if (!res.ok) { var err = await res.json(); showToast(err.error||t('err_login_failed','Login failed'),'error'); return; }
    var data = await res.json();
    setAuth();
    hideLoginView();
    checkAuth();
  } catch(e) { console.error('Request failed:', e); showToast(t('err_login_failed','Login failed'),'error'); }
}

async function doSetup() {
  var u = document.getElementById('setup-username').value.trim();
  var p = document.getElementById('setup-password').value;
  var n = document.getElementById('setup-displayname').value.trim();
  if (!u || !p || !n) { showToast(t('err_fill_all_fields','Fill in all fields'),'error'); return; }
  if (p.length < 8) { showToast(t('err_password_min_length','Password must be at least 8 characters'),'error'); return; }
  try {
    var res = await fetch('/api/auth/setup', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p,display_name:n})});
    if (!res.ok) { var err = await res.json(); showToast(err.error||t('err_setup_failed','Setup failed'),'error'); return; }
    var data = await res.json();
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

// Paths the server keeps open without the write capability. Sent by /auth/me
// rather than restated here — a second copy of the rule is the one that goes
// stale, and it would go stale in the direction of offering something the
// server refuses.
var _writeExempt = [];

// What this account reaches, resolved by the server. The interface holds no
// copy of the rules — it hides what is not in these lists, so a screen cannot
// drift from the route it leads to.
var _features = [];
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

async function apiFetch(url, options, _retryCount) {
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
  try {
    var r = await fetch(url, options);
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
      try { var eb = await r.json(); errBody = eb.error || eb.detail || JSON.stringify(eb); } catch(_) { errBody = await r.text().catch(function(){return '';}); }
      if (_retryCount < maxRetries) {
        showToast(t('err_server_error','Server error') + ' (' + (_retryCount+1) + '/' + maxRetries + '): ' + (errBody || r.status), 'warning', 3000);
        await new Promise(function(resolve) { setTimeout(resolve, 3000); });
        return apiFetch(url, options, _retryCount + 1);
      }
      showToastWithRetry(t('err_server_error','Server error') + ': ' + (errBody || 'HTTP ' + r.status), function() { apiFetch(url, options, 0); });
      console.error('API error', url, r.status, errBody);
      return null;
    }
    if (r.status === 401) {
      // Access cookie expired — refresh once using the HttpOnly refresh cookie.
      if (_retryCount === 0) {
        var ref = await fetch('/api/auth/refresh', {method:'POST'});
        if (ref.ok) { return apiFetch(url, options, _retryCount+1); }
      }
      setAuth(null, null);
      showLoginView('login');
      return null;
    }
    if (r.status >= 400) {
      // Client error — show message from body
      var errMsg = t('err_request_failed').replace('{status}', r.status);
      try {
        var errBody = await r.json();
        if (errBody.error) errMsg = errBody.error;
        else if (errBody.detail) errMsg = errBody.detail;
        else if (errBody.message) errMsg = errBody.message;
      } catch(_) {}
      showToast(errMsg, 'error');
      return null;
    }
    return null;
  } catch (e) {
    // Network error
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
    hosts:        [{label:t('nav_remote_access','Fjernaksess')}, {label:t('bc_hosts_ssh','Verter')}],
    terminal:     [{label:t('nav_remote_access','Fjernaksess'),view:'hosts'}, {label:'Terminal'}],
    rdp:          [{label:t('nav_remote_access','Fjernaksess'),view:'hosts'}, {label:'RDP'}],
    ssh:          [{label:t('nav_remote_access','Fjernaksess'),view:'hosts'}, {label:t('bc_ssh_keys','SSH-nøkler')}],
    network:      [{label:t('nav_network','Nettverk')}, {label:t('bc_network','FortiGate / UniFi')}],
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
      return sep + '<a href="javascript:void(0)" onclick="showView(\'' + esc(c.view) + '\')" style="color:var(--text-muted);text-decoration:none;transition:color 0.15s;"  onmouseover="this.style.color=\'var(--blue)\'" onmouseout="this.style.color=\'var(--text-muted)\'">' + esc(c.label) + '</a>';
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
  var _toolViews = {hosts:1, terminal:1, rdp:1, ssh:1, browser:1, workshop:1};
  var _customerViews = {customers:1, home:1, audit:1, history:1, files:1, setup:1, 'customer-detail':1, 'history-report':1};
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  if (_m365SubViews[name]) {
    var nb = document.getElementById('nav-customers');
    if (nb) nb.classList.add('active');
  } else if (_remoteViews[name]) {
    var nb = document.getElementById('nav-remote');
    if (nb) nb.classList.add('active');
  } else if (_networkViews[name]) {
    var nb = document.getElementById('nav-network');
    if (nb) nb.classList.add('active');
  } else if (_toolViews[name]) {
    var nb = document.getElementById('nav-tools');
    if (nb) nb.classList.add('active');
  } else if (_customerViews[name]) {
    var nb = document.getElementById('nav-customers');
    if (nb) nb.classList.add('active');
  } else {
    var nb = document.getElementById('nav-' + name);
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
}

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
    if (dash && dash.run_date) when = String(dash.run_date).substring(0, 16).replace('T', ' ');
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
    +   '<button data-write class="btn btn-primary" onclick="startAudit()">'
    +     icon('play', 14) + ' ' + esc(t('btn_run_audit')) + '</button>'
    +   '<button class="btn btn-default" onclick="showView(\'home\')">'
    +     esc(t('btn_see_last_result')) + '</button>'
    +   '<button class="btn btn-default" onclick="showView(\'history\')">'
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

// ── Integrations ──────────────────────────────────────────────────────────────
function switchIntegTab(btn, tabId) {
  document.querySelectorAll('.integ-tab-content').forEach(t => t.style.display = 'none');
  document.querySelectorAll('.integ-tab-btn').forEach(b => {
    b.classList.remove('active');
    b.style.borderBottom = 'none';
  });
  document.getElementById(tabId).style.display = 'block';
  btn.classList.add('active');
  btn.style.borderBottom = '2px solid var(--blue)';

  if (tabId === 'integ-wiki' && typeof wikiLoadAllCards === 'function') wikiLoadAllCards();
}

function toggleIntegConfig(id) {
  const el = document.getElementById(id);
  if (!el) return;
  // Computed, not inline. A panel whose hidden state comes from a stylesheet
  // class has an empty el.style.display, which read as "open" and made the
  // first click close everything and open nothing.
  const isOpen = getComputedStyle(el).display !== 'none';
  // Close all config panels first
  ['itglue-config','email-config','webhook-config','gdap-config','autotask-config',
   'myitprocess-config'].forEach(function(cid) {
    const c = document.getElementById(cid);
    if (c) c.style.display = 'none';
  });
  // Toggle the target
  if (!isOpen) el.style.display = 'block';
}

async function loadIntegrationStatus() {
  function setStatusWarn(dotId, labelId, text) {
    // The state between configured and not: something is stored, and we know
    // it did not work. Kept apart from setStatus's boolean because collapsing
    // it into "ok" is what let a rejected credential show as green.
    const dot = document.getElementById(dotId);
    const label = document.getElementById(labelId);
    if (!dot || !label) return;
    dot.style.background = 'var(--orange)';
    label.style.color = 'var(--orange)';
    label.textContent = text;
  }
  function setStatus(dotId, labelId, ok, okText, noText) {
    const dot = document.getElementById(dotId);
    const label = document.getElementById(labelId);
    if (!dot || !label) return;
    if (ok) {
      dot.style.background = 'var(--green)';
      label.style.color = 'var(--green)';
      label.textContent = okText || t('status_configured');
    } else {
      dot.style.background = 'var(--red)';
      label.style.color = 'var(--red)';
      label.textContent = noText || t('status_not_configured');
    }
  }
  function _setVal(id, value) {
    // Tolerant of a missing element, like setStatus above: this function
    // populates several cards and a view that has not rendered one of them
    // must not stop the rest being filled in.
    const el = document.getElementById(id);
    if (el) el.value = value;
  }
  try {
    const d = await apiFetch('/api/settings');
    if (!d) return;
    // IT Glue status + populate
    var _integCount = 0, _integActive = 0;
    setStatus('itglue-integ-dot', 'itglue-integ-label', !!d.itglue_api_key); _integCount++; if (d.itglue_api_key) _integActive++;
    document.getElementById('input-itglue-key').value = d.itglue_api_key || '';
    document.getElementById('input-itglue-region').value = d.itglue_region || 'eu';
    // Autotask status + populate. The two secrets come back masked, so the
    // *_set booleans are what say whether one is stored — writing the mask
    // into the field and saving it back would store the bullets.
    setStatus('autotask-integ-dot', 'autotask-integ-label', !!d.autotask_secret_set);
    _integCount++; if (d.autotask_secret_set) _integActive++;
    _setVal('input-autotask-code', d.autotask_integration_code_set ? '••••••' : '');
    _setVal('input-autotask-user', d.autotask_username || '');
    _setVal('input-autotask-secret', d.autotask_secret_set ? '••••••' : '');
    _setVal('input-autotask-queue', d.autotask_default_queue_id == null ? '' : d.autotask_default_queue_id);
    _setVal('input-autotask-priority', d.autotask_default_priority == null ? '' : d.autotask_default_priority);
    _setVal('input-autotask-status', d.autotask_default_status == null ? '' : d.autotask_default_status);
    // myITprocess status + populate
    setStatus('myitprocess-integ-dot', 'myitprocess-integ-label', !!d.myitprocess_api_key_set);
    _integCount++; if (d.myitprocess_api_key_set) _integActive++;
    _setVal('input-myitprocess-key', d.myitprocess_api_key_set ? '••••••' : '');
    _setVal('input-myitprocess-base', d.myitprocess_base_url || '');
    // Email status + populate
    setStatus('email-integ-dot', 'email-integ-label', !!d.smtp_server); _integCount++; if (d.smtp_server) _integActive++;
    // ALSO status + populate
    setStatus('also-integ-dot', 'also-integ-label', !!d.also_password_set); _integCount++; if (d.also_password_set) _integActive++;
    var _alsoU = document.getElementById('input-also-username');
    var _alsoP = document.getElementById('input-also-password');
    var _alsoC = document.getElementById('input-also-country');
    if (_alsoU) _alsoU.value = d.also_username || '';
    if (_alsoP) _alsoP.value = d.also_password || '';
    if (_alsoC) _alsoC.value = d.also_country || 'no';
    // UniFi Site Manager status. It was absent from this block entirely, so it
    // never counted towards "n/m configured" and its card was left on whatever
    // unifiSmLoadSaved() painted — blue "key saved" rather than the green every
    // other integration shows for a stored credential. A key that is stored is
    // configured here, exactly as it is for IT Glue and the rest.
    setStatus('unifi-sm-integ-dot', 'unifi-sm-integ-label', !!d.unifi_site_manager_api_key_set); _integCount++; if (d.unifi_site_manager_api_key_set) _integActive++;
    // Tailscale status + populate
    setStatus('ts-integ-dot', 'ts-integ-label', !!d.tailscale_api_key_set); _integCount++; if (d.tailscale_api_key_set) _integActive++;
    var _tsKey = document.getElementById('input-ts-api-key');
    var _tsTailnet = document.getElementById('input-ts-tailnet');
    if (_tsKey) _tsKey.value = d.tailscale_api_key || '';
    if (_tsTailnet) _tsTailnet.value = d.tailscale_tailnet || '-';
    // GDAP / Partner Center status + populate
    // Three states. Credentials stored is not the same claim as credentials
    // that work: a client secret Partner Center had just rejected still went
    // green and stayed green, because this card is repainted from the stored
    // config and the config recorded only that a setup had been attempted.
    // gdap_validated is null for configs written before it was recorded — that
    // is "we do not know", not "broken", so those keep their old appearance.
    if (d.gdap_configured && d.gdap_validated === false) {
      setStatusWarn('gdap-integ-dot', 'gdap-integ-label',
        t('gdap_status_unverified', 'Lagret — ikke verifisert'));
    } else {
      setStatus('gdap-integ-dot', 'gdap-integ-label', !!d.gdap_configured);
    }
    _integCount++; if (d.gdap_configured && d.gdap_validated !== false) _integActive++;
    if (d.gdap_configured) {
      var _gdapBtn = document.getElementById('gdap-discover-btn');
      if (_gdapBtn) _gdapBtn.style.display = 'block';
      var _gdapCount = document.getElementById('gdap-customer-count');
      if (_gdapCount && d.gdap_customer_count) _gdapCount.textContent = d.gdap_customer_count + ' ' + t('gdap_customers_linked', 'kunder koblet');
    }
    var _gdapTenant = document.getElementById('input-gdap-tenant');
    var _gdapClient = document.getElementById('input-gdap-client');
    if (_gdapTenant) _gdapTenant.value = d.gdap_partner_tenant_id || '';
    if (_gdapClient) _gdapClient.value = d.gdap_client_id || '';
    // Uniweb status + populate
    setStatus('uniweb-integ-dot', 'uniweb-integ-label', !!d.uniweb_password_set); _integCount++; if (d.uniweb_password_set) _integActive++;
    var _uwEmail = document.getElementById('input-uniweb-email');
    var _uwPass = document.getElementById('input-uniweb-password');
    if (_uwEmail) _uwEmail.value = d.uniweb_email || '';
    if (_uwPass) _uwPass.value = d.uniweb_password || '';
    if (d.uniweb_password_set && typeof uniwebCheckStatus === 'function') uniwebCheckStatus();
    // Update summary
    var sumEl = document.getElementById('integ-summary');
    if (sumEl) sumEl.innerHTML = '<span style="color:var(--green);">&#9679;</span> ' + _integActive + '/' + _integCount + ' ' + t('status_configured','configured');
    document.getElementById('input-smtp-server').value = d.smtp_server || '';
    document.getElementById('input-smtp-port').value = d.smtp_port || 587;
    document.getElementById('input-smtp-user').value = d.smtp_user || '';
    document.getElementById('input-smtp-password').value = d.smtp_password || '';
    document.getElementById('input-smtp-from').value = d.smtp_from || '';
    document.getElementById('input-email-recipient').value = d.email_default_recipient || '';
    document.getElementById('input-email-auto-send').checked = d.email_auto_send || false;
  } catch(e) {
    const label = document.getElementById('itglue-integ-label');
    if (label) { label.textContent = t('err_check_failed'); label.style.color = 'var(--red)'; }
  }
  // Webhook / scheduler status + populate
  try {
    const sched = await apiFetch('/api/scheduler');
    if (!sched) return;
    setStatus('webhook-integ-dot', 'webhook-integ-label', !!sched.webhook_url);
    document.getElementById('input-webhook-url').value = sched.webhook_url || '';
    const ao = sched.alert_on || {};
    document.getElementById('alert-audit-completed').checked = ao.audit_completed !== false;
    document.getElementById('alert-risk-score-drop').checked = ao.risk_score_drop !== false && ao.risk_score_drop !== 0;
    document.getElementById('alert-risk-score-drop-threshold').value = (typeof ao.risk_score_drop === 'number' ? ao.risk_score_drop : 5);
    document.getElementById('alert-new-risky-users').checked = ao.new_risky_users !== false;
    document.getElementById('alert-expired-credentials').checked = ao.expired_credentials !== false;
    document.getElementById('alert-secure-score-drop').checked = ao.secure_score_drop !== false && ao.secure_score_drop !== 0;
    document.getElementById('alert-secure-score-drop-threshold').value = (typeof ao.secure_score_drop === 'number' ? ao.secure_score_drop : 5);
    document.getElementById('alert-new-nsg-warnings').checked = ao.new_nsg_warnings !== false;
    document.getElementById('alert-mfa-below-threshold').checked = ao.mfa_below_threshold !== false && ao.mfa_below_threshold !== 0;
    document.getElementById('alert-mfa-threshold').value = (typeof ao.mfa_below_threshold === 'number' ? ao.mfa_below_threshold : 80);
  } catch(e) { console.warn('Alert options init failed:', e); }
}

async function testMyITProcess() {
  const out = document.getElementById('myitprocess-test-result');
  out.textContent = t('msg_testing', 'Tester…');
  out.style.color = 'var(--text-muted)';

  // Save first, same as the Autotask card. The endpoint can test an unsaved
  // key, but this button is the only thing on the card that writes — testing
  // without saving would leave an operator who saw "OK" with nothing stored.
  const saved = await _saveMyITProcessSettings();
  if (!saved) { out.textContent = t('msg_save_failed', 'Kunne ikke lagre'); out.style.color = 'var(--red)'; return; }

  const d = await apiFetch('/api/myitprocess/test', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}',
  });
  if (d && d.ok) {
    // The field names are the point of this test — nothing in the client has
    // met a real server, so what came back is what corrects it.
    const fields = (d.sample_fields || []).join(', ');
    out.textContent = t('status_ok', 'OK') + (fields ? ' — ' + fields : '');
    out.style.color = 'var(--green)';
  } else {
    out.textContent = (d && d.error) || t('msg_failed', 'Feilet');
    out.style.color = 'var(--red)';
  }
}

async function _saveMyITProcessSettings() {
  const val = function(id) { const el = document.getElementById(id); return el ? el.value.trim() : ''; };
  const body = {myitprocess_base_url: val('input-myitprocess-base')};
  // The mask means "unchanged". Sending it back would store the bullets.
  const key = val('input-myitprocess-key');
  if (key && key !== '••••••') body.myitprocess_api_key = key;

  const d = await apiFetch('/api/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  return !!(d && !d.error);
}

async function testAutotask() {
  const out = document.getElementById('autotask-test-result');
  out.textContent = t('msg_testing', 'Tester…');
  out.style.color = 'var(--text-muted)';

  // Save first. Zone discovery and the query both run server-side from stored
  // settings, so testing what is on screen means storing it — otherwise the
  // operator tests the previous credentials and is told they work.
  const saved = await _saveAutotaskSettings();
  if (!saved) { out.textContent = t('msg_save_failed', 'Kunne ikke lagre'); out.style.color = 'var(--red)'; return; }

  const d = await apiFetch('/api/autotask/test', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}',
  });
  if (d && d.ok) {
    out.textContent = t('status_ok', 'OK');
    out.style.color = 'var(--green)';
    const dot = document.getElementById('autotask-integ-dot');
    const label = document.getElementById('autotask-integ-label');
    if (dot) dot.style.background = 'var(--green)';
    if (label) { label.style.color = 'var(--green)'; label.textContent = t('status_configured'); }
  } else {
    out.textContent = (d && d.error) || t('msg_failed', 'Feilet');
    out.style.color = 'var(--red)';
  }
}

async function _saveAutotaskSettings() {
  const val = function(id) { const el = document.getElementById(id); return el ? el.value.trim() : ''; };
  const body = {
    autotask_username: val('input-autotask-user'),
    autotask_default_queue_id: val('input-autotask-queue'),
    autotask_default_priority: val('input-autotask-priority'),
    autotask_default_status: val('input-autotask-status'),
  };
  // The mask means "unchanged". Sending it back would store the bullets as the
  // secret, which is the classic way a settings form destroys a credential.
  const code = val('input-autotask-code');
  const secret = val('input-autotask-secret');
  if (code && code !== '••••••') body.autotask_integration_code = code;
  if (secret && secret !== '••••••') body.autotask_secret = secret;

  const d = await apiFetch('/api/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  return !!(d && !d.error);
}

async function saveITGlueSettings() {
  const msg = document.getElementById('itglue-save-msg');
  msg.textContent = t('btn_saving'); msg.style.color = 'var(--text-muted)';
  const d = await apiFetch('/api/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      itglue_api_key: document.getElementById('input-itglue-key').value.trim(),
      itglue_region: document.getElementById('input-itglue-region').value,
    })
  });
  if (d && !d.error) {
    msg.textContent = t('msg_saved'); msg.style.color = 'var(--green)';
    const dot = document.getElementById('itglue-integ-dot');
    const label = document.getElementById('itglue-integ-label');
    const hasKey = !!document.getElementById('input-itglue-key').value.trim();
    dot.style.background = hasKey ? 'var(--green)' : 'var(--red)';
    label.style.color = hasKey ? 'var(--green)' : 'var(--red)';
    label.textContent = hasKey ? t('status_configured') : t('status_not_configured');
  } else {
    msg.textContent = t('msg_error'); msg.style.color = 'var(--red)';
  }
  setTimeout(() => { msg.textContent = ''; }, 3000);
}

// ── GDAP / Partner Center ─────────────────────────────────────────────────
async function gdapSaveConfig() {
  var msg = document.getElementById('gdap-config-msg');
  msg.textContent = t('btn_saving'); msg.style.color = 'var(--text-muted)';
  var tenant = document.getElementById('input-gdap-tenant').value.trim();
  var client = document.getElementById('input-gdap-client').value.trim();
  var secret = document.getElementById('input-gdap-secret').value.trim();
  if (!tenant || !client) {
    msg.textContent = t('gdap_err_missing_fields', 'Partner Tenant ID og Client ID er paakrevd');
    msg.style.color = 'var(--red)';
    return;
  }
  var d = await apiFetch('/api/gdap/setup', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ partner_tenant_id: tenant, client_id: client, client_secret: secret })
  });
  if (d && d.ok) {
    if (d.validated) {
      msg.innerHTML = '<span style="color:var(--green);">' + t('msg_saved') + ' — ' + d.customer_count + ' ' + t('gdap_customers_found', 'kunder funnet') + '</span>';
    } else {
      msg.innerHTML = '<span style="color:var(--orange);">' + t('msg_saved') + ' — ' + (d.warning || '') + '</span>';
    }
    if (d.validated) {
      setStatus('gdap-integ-dot', 'gdap-integ-label', true);
    } else {
      setStatusWarn('gdap-integ-dot', 'gdap-integ-label',
        t('gdap_status_unverified', 'Lagret — ikke verifisert'));
    }
    document.getElementById('gdap-discover-btn').style.display = 'block';
    if (d.customer_count) {
      var cc = document.getElementById('gdap-customer-count');
      if (cc) cc.textContent = d.customer_count + ' ' + t('gdap_customers_linked', 'kunder koblet');
    }
  } else {
    msg.textContent = t('msg_error'); msg.style.color = 'var(--red)';
  }
}

async function gdapTestConnection() {
  var msg = document.getElementById('gdap-config-msg');
  msg.textContent = t('msg_checking'); msg.style.color = 'var(--text-muted)';
  // Save first (in case credentials changed)
  await gdapSaveConfig();
}

async function gdapDiscoverCustomers() {
  var panel = document.getElementById('gdap-discover-panel');
  var list = document.getElementById('gdap-discover-list');
  panel.style.display = 'block';
  list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;">' + t('msg_loading', 'Laster...') + '</div>';
  var d = await apiFetch('/api/gdap/customers');
  if (!d || !d.customers) {
    list.innerHTML = '<div style="color:var(--red);font-size:12px;">' + t('msg_error') + '</div>';
    return;
  }
  if (d.customers.length === 0) {
    list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;">' + t('gdap_no_customers', 'Ingen kunder funnet i Partner Center') + '</div>';
    return;
  }
  var html = '';
  d.customers.forEach(function(c) {
    var imported = c.already_imported;
    var gdapBadge = c.gdap_status === 'active' ? '<span style="background:var(--green);color:#fff;padding:1px 6px;border-radius:8px;font-size:10px;margin-left:6px;">GDAP</span>' : '';
    var importedBadge = imported ? '<span style="background:var(--blue);color:#fff;padding:1px 6px;border-radius:8px;font-size:10px;margin-left:6px;">' + (c.local_auth_mode === 'gdap' ? 'GDAP' : 'Legacy') + '</span>' : '';
    html += '<label style="display:flex;align-items:center;gap:8px;padding:6px 4px;border-bottom:1px solid var(--border);cursor:pointer;font-size:13px;">';
    html += '<input type="checkbox" class="gdap-import-cb" value="' + c.tenant_id + '" ' + (imported ? 'checked disabled' : '') + ' style="flex-shrink:0;">';
    html += '<div style="flex:1;min-width:0;">';
    html += '<div style="font-weight:600;">' + esc(c.company_name) + gdapBadge + importedBadge + '</div>';
    html += '<div style="font-size:11px;color:var(--text-dim);font-family:var(--mono);">' + esc(c.domain || c.tenant_id) + '</div>';
    if (c.gdap_roles && c.gdap_roles.length) {
      html += '<div style="font-size:10px;color:var(--text-muted);margin-top:2px;">' + t('gdap_roles', 'Roller') + ': ' + esc(c.gdap_roles.join(', ')) + '</div>';
    }
    html += '</div></label>';
  });
  list.innerHTML = html;
}

async function gdapImportSelected() {
  var cbs = document.querySelectorAll('.gdap-import-cb:checked:not(:disabled)');
  var tenantIds = [];
  cbs.forEach(function(cb) { tenantIds.push(cb.value); });
  if (tenantIds.length === 0) {
    showToast(t('gdap_select_customers', 'Velg minst en kunde'), 'warning');
    return;
  }
  var msg = document.getElementById('gdap-import-msg');
  msg.textContent = t('gdap_importing', 'Importerer...'); msg.style.color = 'var(--text-muted)';
  var d = await apiFetch('/api/gdap/import', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ tenant_ids: tenantIds })
  });
  if (d && d.imported) {
    var created = d.imported.filter(function(i) { return i.action === 'created'; }).length;
    var converted = d.imported.filter(function(i) { return i.action === 'converted'; }).length;
    msg.innerHTML = '<span style="color:var(--green);">' + created + ' ' + t('gdap_created', 'opprettet') + ', ' + converted + ' ' + t('gdap_converted', 'konvertert til GDAP') + '</span>';
    // Refresh customer list
    if (typeof loadDashboard === 'function') loadDashboard();
    if (typeof refreshCustomerList === 'function') refreshCustomerList();
    showToast(t('gdap_import_success', 'Kunder importert fra Partner Center'), 'success');
  } else {
    msg.textContent = t('msg_error'); msg.style.color = 'var(--red)';
  }
}

async function saveEmailSettings() {
  const msg = document.getElementById('email-save-msg');
  msg.textContent = t('btn_saving'); msg.style.color = 'var(--text-muted)';
  const d = await apiFetch('/api/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      smtp_server: document.getElementById('input-smtp-server').value.trim(),
      smtp_port: parseInt(document.getElementById('input-smtp-port').value) || 587,
      smtp_user: document.getElementById('input-smtp-user').value.trim(),
      smtp_password: document.getElementById('input-smtp-password').value.trim(),
      smtp_from: document.getElementById('input-smtp-from').value.trim(),
      email_default_recipient: document.getElementById('input-email-recipient').value.trim(),
      email_auto_send: document.getElementById('input-email-auto-send').checked,
    })
  });
  if (d && !d.error) {
    msg.textContent = t('msg_saved'); msg.style.color = 'var(--green)';
    const hasSmtp = !!document.getElementById('input-smtp-server').value.trim();
    document.getElementById('email-integ-dot').style.background = hasSmtp ? 'var(--green)' : 'var(--red)';
    document.getElementById('email-integ-label').style.color = hasSmtp ? 'var(--green)' : 'var(--red)';
    document.getElementById('email-integ-label').textContent = hasSmtp ? t('status_configured') : t('status_not_configured');
  } else {
    msg.textContent = t('msg_error'); msg.style.color = 'var(--red)';
  }
  setTimeout(() => { msg.textContent = ''; }, 3000);
}

async function saveWebhookSettings() {
  const msg = document.getElementById('webhook-save-msg');
  msg.textContent = t('btn_saving'); msg.style.color = 'var(--text-muted)';
  const d = await apiFetch('/api/scheduler', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      webhook_url: document.getElementById('input-webhook-url').value.trim(),
      alert_on: {
        audit_completed: document.getElementById('alert-audit-completed').checked,
        risk_score_drop: document.getElementById('alert-risk-score-drop').checked ? (parseInt(document.getElementById('alert-risk-score-drop-threshold').value) || 5) : false,
        new_risky_users: document.getElementById('alert-new-risky-users').checked,
        expired_credentials: document.getElementById('alert-expired-credentials').checked,
        secure_score_drop: document.getElementById('alert-secure-score-drop').checked ? (parseInt(document.getElementById('alert-secure-score-drop-threshold').value) || 5) : false,
        new_nsg_warnings: document.getElementById('alert-new-nsg-warnings').checked,
        mfa_below_threshold: document.getElementById('alert-mfa-below-threshold').checked ? (parseInt(document.getElementById('alert-mfa-threshold').value) || 80) : false,
      },
    })
  });
  if (d && !d.error) {
    msg.textContent = t('msg_saved'); msg.style.color = 'var(--green)';
    const hasUrl = !!document.getElementById('input-webhook-url').value.trim();
    document.getElementById('webhook-integ-dot').style.background = hasUrl ? 'var(--green)' : 'var(--red)';
    document.getElementById('webhook-integ-label').style.color = hasUrl ? 'var(--green)' : 'var(--red)';
    document.getElementById('webhook-integ-label').textContent = hasUrl ? t('status_configured') : t('status_not_configured');
  } else {
    msg.textContent = t('msg_error'); msg.style.color = 'var(--red)';
  }
  setTimeout(() => { msg.textContent = ''; }, 3000);
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
          if (lel) lel.textContent = dash.run_date.substring(0,10);
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
      var status = '';
      if (!isNaN(v)) {
        if (thresholds.red && v < thresholds.red) { color = 'var(--red)'; status = ''; }
        else if (thresholds.orange && v < thresholds.orange) { color = 'var(--orange)'; status = ''; }
        else { color = 'var(--green)'; status = '&#10003;'; }
      }
      var dot = '<span style="width:8px;height:8px;border-radius:50%;background:' + color + ';display:inline-block;"></span>';
      var tipText = hint || '';
      if (thresholds.red) tipText += (tipText ? ' · ' : '') + '< ' + thresholds.red + ' = ' + t('status_error','critical');
      if (thresholds.orange) tipText += (tipText ? ' · ' : '') + '< ' + thresholds.orange + ' = ' + t('lbl_needs_attention','warning');
      return '<div style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-3);background:var(--bg);border-radius:var(--radius-md);border:1px solid var(--border);cursor:default;transition:border-color var(--duration-fast);" onmouseover="this.style.borderColor=\'var(--blue)\'" onmouseout="this.style.borderColor=\'var(--border)\'"' + (tipText ? ' title="' + esc(tipText) + '"' : '') + '>'
        + dot
        + '<div style="flex:1;"><div style="font-size:var(--font-xs);color:var(--text-muted);">' + esc(label) + '</div></div>'
        + '<div style="font-size:var(--font-md);font-weight:700;color:' + color + ';">' + (isNaN(v) ? '-' : v + (suffix||'')) + '</div></div>';
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
  var name = c.CustomerName || c.customer_name || '';

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
    domEl.textContent = c.PrimaryDomain || c.primary_domain || '';
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
    // Relative "Audit N d siden" (frame 3a) instead of a bare date.
    var _rd = new Date(d.run_date.substring(0, 10));
    var _days = Math.floor((Date.now() - _rd.getTime()) / 86400000);
    lastEl.textContent = (!isNaN(_days) && _days >= 0)
      ? (_days === 0 ? 'Audit i dag' : 'Audit ' + _days + ' d siden')
      : 'Audit ' + d.run_date.substring(0, 10);
  } else if (lastEl) {
    lastEl.textContent = '';
  }
  // Show/hide licenses button based on ALSO linkage
  if (licBtn) {
    var alsoId = c.AlsoAccountId || c.also_account_id || '';
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
        <button class="btn btn-primary" onclick="startSetup()">${t('btn_start_setup')}</button>
      </div>`;
    return;
  }

  const c = d.customer;
  let warnsHtml = '';
  if (c.warns && c.warns.length > 0) {
    window._lastAuditWarns = c.warns;
    const items = c.warns.map(w => `<li>${w}</li>`).join('');
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
        <span style="margin-left:auto;font-size:11px;font-weight:400;"><a href="#" onclick="showView('customers');return false;" style="color:var(--blue);text-decoration:none;">${t('tip_all_customers_link')}</a></span>
      </div>
      <div class="customer-name">${esc(c.name)}</div>
      <div class="customer-domain">${esc(c.domain)}</div>
      <div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin-top:6px;">
        <span id="tag-pills-home">${tagPillsHtml(c.tags || [])}</span>
        <button class="btn btn-ghost" style="padding:1px 6px;font-size:10px;border:1px dashed var(--border);border-radius:10px;" onclick="openTagEditor('${esc(d.active_id)}',JSON.parse(this.dataset.tags))" data-tags="${esc(JSON.stringify(c.tags||[]))}">${t('tags')}</button>
      </div>
      <div id="tag-editor-${(d.active_id||'').replace(/[^a-zA-Z0-9_-]/g,'_')}" style="display:none;margin-top:8px;padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:8px;"></div>
      <div class="meta-row">
        <div class="meta-item"><strong>${esc(c.setup_date)}</strong>${t('lbl_setup_date')}</div>
      </div>
      ${warnsHtml}
      <div id="home-health-grid" style="display:none;margin-top:var(--space-4);"></div>
      ${hasCredentials ? `
      <div class="btn-row">
        <button class="btn btn-primary tooltip" data-tip="${t('tip_run_full_audit','Runs a full security check of the customer M365/Azure environment')}" onclick="startAudit()" ${runDisabled}>${runLabel} <kbd style="font-size:9px;opacity:0.6;margin-left:4px;padding:1px 4px;background:rgba(255,255,255,0.15);border-radius:3px;">Ctrl+Shift+A</kbd></button>
        <button class="btn btn-default tooltip" data-tip="${t('tip_check_permissions','Verifies that all required Graph API permissions are granted')}" onclick="checkPermissions()">${t('btn_check_permissions')}</button>
        <button class="btn btn-warning" onclick="renewCreds()">${t('btn_renew_credentials')}</button>
        <button class="btn btn-ghost" onclick="showView('customers')">${t('btn_switch_customer')}</button>
      </div>` : `
      <div style="padding:14px;margin-bottom:8px;background:rgba(210,153,34,0.1);border:1px solid rgba(210,153,34,0.3);border-radius:8px;font-size:13px;color:var(--orange);">
        ${t('msg_no_m365_configured','This customer does not have M365 access configured yet.')}
      </div>
      <div class="btn-row">
        <button class="btn btn-primary" onclick="startSetup()">${t('btn_setup_m365','Setup M365 access')}</button>
        <button class="btn btn-ghost" onclick="showView('customers')">${t('btn_switch_customer')}</button>
      </div>`}

      <div id="scope-panel" class="tooltip" data-tip="${t('tip_select_audit_sections','Select which sections to include in the audit')}" style="margin-top:14px;border-top:1px solid var(--border);padding-top:12px;">
        <div style="display:flex;align-items:center;cursor:pointer;user-select:none;" onclick="toggleScopePanel()">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;flex-shrink:0;"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          <span style="font-weight:600;font-size:13px;">${t('hdr_select_sections')}</span>
          <span id="scope-toggle-icon" style="margin-left:6px;font-size:10px;color:var(--text-muted);transition:transform .2s;">&#9654;</span>
          <span id="scope-summary" style="margin-left:auto;font-size:11px;color:var(--text-muted);"></span>
        </div>
        <div id="scope-body" style="display:none;margin-top:10px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
            <select id="preset-select" style="font-size:12px;padding:3px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg);color:var(--text);" onchange="applyPreset()">
              <option value="">${t('lbl_select_preset')}</option>
            </select>
            <button class="btn btn-ghost" style="padding:2px 10px;font-size:11px;" onclick="saveCustomPreset()">${t('btn_save_as_preset')}</button>
            <button id="preset-delete-btn" class="btn btn-ghost" style="padding:2px 10px;font-size:11px;display:none;color:var(--red);" onclick="deleteCustomPreset()">${t('btn_delete_preset')}</button>
          </div>
          <div style="display:flex;gap:6px;margin-bottom:10px;">
            <button class="btn btn-ghost" style="padding:2px 10px;font-size:11px;" onclick="scopeSelectAll()">${t('btn_select_all')}</button>
            <button class="btn btn-ghost" style="padding:2px 10px;font-size:11px;" onclick="scopeDeselectAll()">${t('btn_deselect_all')}</button>
          </div>
          <div id="scope-sections" style="display:flex;gap:24px;flex-wrap:wrap;"></div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:16px;" id="customer-notes-card">
      <div class="card-title" style="cursor:pointer;" onclick="toggleNotesCard()">
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

    <!-- Module cards removed — FortiGate and UniFi are now fully integrated -->

    <div class="card" style="margin-top:16px;" id="activity-log-card">
      <div class="card-title" style="cursor:pointer;" onclick="toggleActivityLog()">
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
    loadRemediation();
  }

  // Load expiry banner
  loadExpiryBanner();

  // Load activity log
  loadActivityLog();

  // Load customer notes
  loadCustomerNotes();
}

// ── Customer notes ─────────────────────────────────────────────────────────
let _notesDebounceTimer = null;
let _notesCollapsed = false;

function toggleNotesCard() {
  _notesCollapsed = !_notesCollapsed;
  const body = document.getElementById('notes-body');
  const icon = document.getElementById('notes-toggle-icon');
  if (body) body.style.display = _notesCollapsed ? 'none' : '';
  if (icon) icon.innerHTML = _notesCollapsed ? '&#9654;' : '&#9660;';
}

async function loadCustomerNotes() {
  try {
    const d = await apiFetch('/api/customer/notes');
    const ta = document.getElementById('customer-notes-textarea');
    if (!ta) return;
    ta.value = d.notes || '';
    showNotesTimestamp(d.last_saved);
    ta.oninput = () => {
      const status = document.getElementById('notes-save-status');
      if (status) { status.textContent = t('btn_saving'); status.style.color = 'var(--orange)'; }
      clearTimeout(_notesDebounceTimer);
      _notesDebounceTimer = setTimeout(() => saveCustomerNotes(ta.value), 1000);
    };
  } catch(e) { console.warn('loadCustomerNotes failed:', e); }
}

async function saveCustomerNotes(text) {
  try {
    const d = await apiFetch('/api/customer/notes', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({notes: text})
    });

    const status = document.getElementById('notes-save-status');
    if (d.ok) {
      if (status) { status.textContent = t('msg_saved').replace('✓ ', ''); status.style.color = 'var(--green)'; }
      showNotesTimestamp(d.last_saved);
      setTimeout(() => { if (status) status.textContent = ''; }, 3000);
    } else {
      if (status) { status.textContent = t('err_saving_notes'); status.style.color = 'var(--red)'; }
    }
  } catch(e) {
    const status = document.getElementById('notes-save-status');
    if (status) { status.textContent = t('err_saving_notes'); status.style.color = 'var(--red)'; }
  }
}

function showNotesTimestamp(isoStr) {
  const el = document.getElementById('notes-last-saved');
  if (!el || !isoStr) { if (el) el.textContent = ''; return; }
  try {
    const dt = new Date(isoStr);
    el.textContent = t('msg_last_saved').replace('{date}', dt.toLocaleDateString('nb-NO') + ' ' + dt.toLocaleTimeString('nb-NO', {hour:'2-digit',minute:'2-digit'}));
  } catch(e) { el.textContent = ''; }
}

async function loadDashboard() {
  const d = await apiFetch('/api/dashboard');
  if (d && d.has_data) renderDashboard(d);
}

function renderDashboard(d) {
  const m = d.metrics;
  const p = d.previous;

  // Format the run date
  let runDate = d.run_date;
  const dm = runDate.match(/^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})$/);
  if (dm) runDate = `${dm[3]}.${dm[2]}.${dm[1]} kl. ${dm[4]}:${dm[5]}`;

  function trend(key, label, lowerIsBetter) {
    if (!p || p[key] === undefined || m[key] === undefined) return '';
    const delta = m[key] - p[key];
    if (delta === 0) return '';
    const improved = lowerIsBetter ? delta < 0 : delta > 0;
    const arrow = improved ? '\u2191' : '\u2193';
    const color = improved ? 'var(--green)' : 'var(--red)';
    const sign = delta > 0 ? '+' : '';
    return `<span style="font-size:11px;color:${color};margin-left:4px;">${arrow} ${sign}${typeof delta === 'number' && delta % 1 !== 0 ? delta.toFixed(1) : delta}</span>`;
  }

  function metricColor(val, thresholds) {
    if (val >= thresholds[0]) return 'var(--green)';
    if (val >= thresholds[1]) return 'var(--orange)';
    return 'var(--red)';
  }

  const gradeColors = {A: 'var(--green)', B: '#4d9fb5', C: 'var(--orange)', D: 'var(--red)'};

  const dashHtml = `
    <div class="card" style="margin-top:16px;">
      <div class="card-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
        ${t('hdr_dashboard_latest')}
        <span style="margin-left:auto;font-size:11px;color:var(--text-dim);font-weight:400;">${runDate}</span>
      </div>

      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;">
        <div class="tooltip" data-tip="A=Utmerket, B=Bra, C=Moderat, D=Svakt, F=Kritisk" style="text-align:center;padding:12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;">
          <div style="font-size:36px;font-weight:800;color:${gradeColors[m.risk_grade] || 'var(--text)'};">${m.risk_grade}</div>
          <div style="font-size:11px;color:var(--text-dim);text-transform:uppercase;">${t('lbl_risk_grade')}</div>
          <div style="font-size:13px;font-weight:600;color:var(--text-muted);">${m.risk_score}/100 ${trend('risk_score', 'score', false)}</div>
        </div>
        <div class="tooltip" data-tip="${t('tip_mfa_share','Andel brukere med tofaktorautentisering aktivert')}" style="text-align:center;padding:12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;">
          <div style="font-size:28px;font-weight:700;color:${metricColor(m.mfa_coverage_pct, [95, 80])};">${m.mfa_coverage_pct?.toFixed(0) || 0}%</div>
          <div style="font-size:11px;color:var(--text-dim);text-transform:uppercase;">${t('lbl_mfa_coverage')}</div>
          ${trend('mfa_coverage_pct', 'MFA', false)}
        </div>
        <div style="text-align:center;padding:12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;">
          <div style="font-size:28px;font-weight:700;color:${metricColor(m.secure_score_pct, [75, 50])};">${m.secure_score_pct?.toFixed(0) || 0}%</div>
          <div style="font-size:11px;color:var(--text-dim);text-transform:uppercase;">${t('secure_score_2')}</div>
          ${trend('secure_score_pct', 'SS', false)}
        </div>
        <div style="text-align:center;padding:12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;">
          <div style="font-size:28px;font-weight:700;color:var(--text);">${m.total_users || 0}</div>
          <div style="font-size:11px;color:var(--text-dim);text-transform:uppercase;">${t('lbl_users')}</div>
          ${trend('total_users', 'users', false)}
        </div>
      </div>

      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;">
        <div style="text-align:center;padding:8px;font-size:12px;">
          <span style="font-weight:700;color:${m.users_no_mfa > 0 ? 'var(--red)' : 'var(--green)'};">${m.users_no_mfa || 0}</span>
          <span style="color:var(--text-dim);"> ${t('lbl_without_mfa')}</span>
          ${trend('users_no_mfa', 'noMFA', true)}
        </div>
        <div style="text-align:center;padding:8px;font-size:12px;">
          <span style="font-weight:700;">${m.ca_policies_enabled || 0}</span>
          <span style="color:var(--text-dim);"> ${t('lbl_ca_policies')}</span>
        </div>
        <div style="text-align:center;padding:8px;font-size:12px;">
          <span style="font-weight:700;">${m.intune_total_devices || 0}</span>
          <span style="color:var(--text-dim);"> ${t('lbl_devices')}</span>
        </div>
        <div style="text-align:center;padding:8px;font-size:12px;">
          <span style="font-weight:700;">${m.total_warns || 0}</span>
          <span style="color:var(--text-dim);"> ${t('lbl_warnings')}</span>
          ${trend('total_warns', 'warns', true)}
        </div>
      </div>
    </div>`;

  // Insert dashboard after the customer card
  const homeContent = document.getElementById('home-content');
  const modulesCard = homeContent.querySelector('.card:last-child');
  if (modulesCard) {
    modulesCard.insertAdjacentHTML('beforebegin', dashHtml);
  }
}

// ── Remediation tracking ──────────────────────────────────────────────────────

let _remediationRecs = [];
// {rec_id: ticket} for the active customer, so each row knows whether its
// finding already went to Autotask. Fetched once per render, not per row.
let _findingTickets = {};
// The other bucket. Kept in its own map rather than merged into the one above:
// a finding may legitimately have both, and one map keyed on rec_id would drop
// whichever arrived second.
let _findingRecs = {};
let _ticketCustomerId = '';

async function loadRemediation() {
  try {
    const [dashData, remData] = await Promise.all([
      apiFetch('/api/dashboard'),
      apiFetch('/api/remediation'),
    ]);
    if (!dashData || !remData) return;

    if (!dashData.has_data) return;
    const recs = (dashData.metrics && dashData.metrics.recommendations) || [];
    if (recs.length === 0) return;

    // /api/remediation already resolved the active customer server-side, so
    // take the id from there rather than keeping a second copy that can drift.
    _ticketCustomerId = remData.customer_id || '';
    _findingTickets = {};
    _findingRecs = {};
    if (_ticketCustomerId) {
      const cid = encodeURIComponent(_ticketCustomerId);
      // Both in parallel: they are independent and the list waits for neither
      // in particular. Settled rather than all-or-nothing, so one integration
      // being down does not blank the state of the other.
      const [tk, rc] = await Promise.allSettled([
        apiFetch('/api/hub/' + cid + '/tickets'),
        apiFetch('/api/hub/' + cid + '/recommendations'),
      ]);
      // A lookup that failed must not take the remediation list with it. The
      // rows still work; they just cannot show pushed state, and a second
      // click is refused by the server rather than by this cache.
      if (tk.status === 'fulfilled' && tk.value) _findingTickets = tk.value.tickets || {};
      else console.warn('ticket lookup failed:', tk.reason);
      if (rc.status === 'fulfilled' && rc.value) _findingRecs = rc.value.recommendations || {};
      else console.warn('recommendation lookup failed:', rc.reason);
    }

    _remediationRecs = recs;
    renderRemediation(recs, remData.items || {});
  } catch(e) { console.warn('loadRemediation failed:', e); }
}

function renderRemediation(recs, statuses) {
  const statusLabels = {open: t('status_open','Åpen'), in_progress: t('status_in_progress','Pågår'), done: t('status_done_label','Utført'), ignored: t('status_ignored','Ignorert')};
  const statusColors = {open: 'var(--red)', in_progress: 'var(--orange)', done: 'var(--green)', ignored: 'var(--text-dim)'};
  const statusBg     = {open: '#f8514915', in_progress: '#d2992215', done: '#3fb95015', ignored: '#8b949e15'};
  const priorityIcons = {critical: '!!', high: '!', medium: '~', low: '-'};
  const priorityColors = {critical: 'var(--red)', high: 'var(--orange)', medium: 'var(--blue)', low: 'var(--text-dim)'};

  let done = 0, inProgress = 0, ignored = 0, openCount = 0;
  const rows = recs.map(function(rec, idx) {
    const title = rec.title || rec.name || 'Rec #' + (idx+1);
    // Keyed on the language-independent id. It used to be the rendered title,
    // so marking an item done in Norwegian left it open again in English.
    // Runs from before ids existed fall back to the title they were stored under.
    const recId = rec.rec_id || title;
    const st = statuses[recId] || statuses[title] || {};
    const curStatus = st.status || 'open';
    const notes = st.notes || '';
    const priority = rec.priority || 'medium';

    if (curStatus === 'done') done++;
    else if (curStatus === 'in_progress') inProgress++;
    else if (curStatus === 'ignored') ignored++;
    else openCount++;

    return '<div class="rem-row" style="padding:10px 12px;border-bottom:1px solid var(--border);display:flex;align-items:flex-start;gap:10px;" data-rec-id="' + esc(recId) + '">'
      + '<span style="font-weight:700;color:' + (priorityColors[priority] || 'var(--text-dim)') + ';font-size:12px;min-width:18px;text-align:center;padding-top:2px;" title="' + esc(priority) + '">' + (priorityIcons[priority] || '~') + '</span>'
      + '<div style="flex:1;min-width:0;">'
      + '<div style="font-weight:600;font-size:13px;margin-bottom:2px;">' + esc(title) + '</div>'
      + (rec.detail ? '<div style="font-size:11px;color:var(--text-dim);margin-bottom:4px;">' + esc(rec.detail.substring(0,120)) + (rec.detail.length > 120 ? '...' : '') + '</div>' : '')
      + '<div style="display:flex;align-items:center;gap:8px;margin-top:4px;">'
      + '<select class="rem-status-select" onchange="updateRemediation(this)" style="font-size:11px;padding:2px 6px;border-radius:4px;border:1px solid var(--border);background:var(--bg);color:var(--text);cursor:pointer;">'
      + '<option value="open"' + (curStatus==='open'?' selected':'') + '>' + t('open') + '</option>'
      + '<option value="in_progress"' + (curStatus==='in_progress'?' selected':'') + '>' + t('in_progress') + '</option>'
      + '<option value="done"' + (curStatus==='done'?' selected':'') + '>' + t('done') + '</option>'
      + '<option value="ignored"' + (curStatus==='ignored'?' selected':'') + '>' + t('ignored') + '</option>'
      + '</select>'
      + '<input type="text" class="rem-notes-input" placeholder="' + t('tip_notes_placeholder_rem') + '" value="' + esc(notes) + '" onchange="updateRemediation(this)" style="font-size:11px;padding:2px 8px;border-radius:4px;border:1px solid var(--border);background:var(--bg);color:var(--text);flex:1;min-width:80px;" />'
      + _pushControl(recId, 'ticket')
      + _pushControl(recId, 'rec')
      + '</div>'
      + '<div class="rem-ticket-panel"></div>'
      + '</div>'
      + '<span class="rem-status-badge" style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;white-space:nowrap;background:' + statusBg[curStatus] + ';color:' + statusColors[curStatus] + ';border:1px solid ' + statusColors[curStatus] + '30;">' + statusLabels[curStatus] + '</span>'
      + '</div>';
  }).join('');

  const total = recs.length;
  const addressed = done + ignored;
  const pct = total > 0 ? Math.round(addressed / total * 100) : 0;

  const html = '<div class="card" id="remediation-card" style="margin-top:16px;">'
    + '<div class="card-title">'
    + '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>'
    + ' ' + t('hdr_remediation','Remediering')
    + '<span style="margin-left:auto;font-size:11px;color:var(--text-dim);font-weight:400;">' + t('msg_rem_addressed','{done}/{total} addressed ({pct}%)').replace('{done}',addressed).replace('{total}',total).replace('{pct}',pct) + '</span>'
    + '</div>'
    + '<div style="margin-bottom:12px;">'
    + '<div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-dim);margin-bottom:4px;">'
    + '<span>' + t('msg_rem_addressed_pct','{pct}% addressed').replace('{pct}',pct) + '</span>'
    + '<span style="display:flex;gap:10px;">'
    + '<span style="color:var(--red);">' + openCount + ' ' + t('status_open','Åpen').toLowerCase() + '</span>'
    + '<span style="color:var(--orange);">' + inProgress + ' ' + t('status_in_progress','Pågår').toLowerCase() + '</span>'
    + '<span style="color:var(--green);">' + done + ' ' + t('status_done_label','Utført').toLowerCase() + '</span>'
    + '<span style="color:var(--text-dim);">' + ignored + ' ' + t('status_ignored','Ignorert').toLowerCase() + '</span>'
    + '</span></div>'
    + '<div style="height:8px;background:var(--bg);border:1px solid var(--border);border-radius:4px;overflow:hidden;display:flex;">'
    + (done > 0 ? '<div style="width:' + (done/total*100) + '%;background:var(--green);"></div>' : '')
    + (ignored > 0 ? '<div style="width:' + (ignored/total*100) + '%;background:var(--text-dim);"></div>' : '')
    + (inProgress > 0 ? '<div style="width:' + (inProgress/total*100) + '%;background:var(--orange);"></div>' : '')
    + (openCount > 0 ? '<div style="width:' + (openCount/total*100) + '%;background:var(--red);opacity:0.3;"></div>' : '')
    + '</div></div>'
    + '<div style="max-height:400px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;">'
    + rows
    + '</div></div>';

  const homeContent = document.getElementById('home-content');
  const existing = document.getElementById('remediation-card');
  if (existing) existing.remove();
  const modulesCard = homeContent.querySelector('.card:last-child');
  if (modulesCard) {
    modulesCard.insertAdjacentHTML('beforebegin', html);
  }
}

// ── Finding → Autotask ticket, or myITprocess recommendation ────────────────
// Two buckets, and which one a finding belongs in is the operator's judgement:
// a ticket is something to fix this week, a recommendation is something to
// plan next quarter. Nothing here decides it, and nothing scheduled reaches
// either endpoint.
//
// One set of functions parameterised by kind rather than two near-copies. The
// duplicate-and-drift risk is real: the interesting behaviour — disable while
// in flight, surface the duplicate case, swap the control for a link — is
// identical, and only the fields and the endpoint differ.

var _PUSH_KINDS = {
  ticket: {
    endpoint: 'tickets',
    store: function() { return _findingTickets; },
    badge: 'lbl_ticket_exists',
    button: 'btn_create_ticket',
    heading: 'hdr_new_ticket',
    submit: 'btn_ticket_submit',
    created: 'msg_ticket_created',
    exists: 'msg_ticket_exists',
    duplicate: 'msg_ticket_duplicate',
    tip: '',
  },
  rec: {
    endpoint: 'recommendations',
    store: function() { return _findingRecs; },
    badge: 'lbl_recommendation_exists',
    button: 'btn_push_recommendation',
    heading: 'hdr_new_recommendation',
    submit: 'btn_rec_submit',
    created: 'msg_rec_created',
    exists: 'msg_rec_exists',
    duplicate: 'msg_rec_duplicate',
    tip: 'tip_push_recommendation',
  },
};

function _pushControl(recId, kind) {
  var cfg = _PUSH_KINDS[kind];
  var rec = cfg.store()[recId];
  if (rec) {
    var label = t(cfg.badge) + ' #' + esc(rec.external_id);
    return rec.external_url
      ? '<a class="tk-badge push-done" data-kind="' + kind + '" href="' + esc(rec.external_url)
        + '" target="_blank" rel="noopener noreferrer">' + label + '</a>'
      : '<span class="tk-badge push-done" data-kind="' + kind + '">' + label + '</span>';
  }
  if (!_ticketCustomerId) return '';
  return '<button class="btn btn-default push-btn" data-kind="' + kind + '"'
    + (cfg.tip ? ' title="' + esc(t(cfg.tip)) + '"' : '')
    + ' onclick="openPushPanel(this)">' + esc(t(cfg.button)) + '</button>';
}

function openPushPanel(btn) {
  var kind = btn.dataset.kind;
  var cfg = _PUSH_KINDS[kind];
  var row = btn.closest('.rem-row');
  var panel = row.querySelector('.rem-ticket-panel');

  // Same panel element for both, so opening one closes the other rather than
  // leaving two half-filled forms on one row.
  if (panel.classList.contains('is-open') && panel.dataset.kind === kind) {
    panel.classList.remove('is-open');
    return;
  }
  panel.dataset.kind = kind;

  var title = row.querySelector('div > div').textContent || '';
  var rec = _remediationRecs.find(function(r) { return (r.rec_id || r.title) === row.dataset.recId; }) || {};
  var fields = kind === 'ticket'
    ? _ticketFields(rec)
    : _recFields(rec);

  panel.innerHTML = '<div class="tk-head">' + esc(t(cfg.heading)) + '</div>'
    + '<div class="tk-form">'
    + '<label class="tk-label">' + esc(t('lbl_ticket_title'))
    + '<input type="text" class="tk-field tk-title" value="' + esc(title.trim()) + '" maxlength="255" /></label>'
    + fields
    + '<label class="tk-label">' + esc(t('lbl_ticket_notes'))
    + '<input type="text" class="tk-field tk-notes" maxlength="4000" placeholder="'
    + esc(t('tip_ticket_notes')) + '" /></label>'
    + '<div><button class="btn btn-primary tk-submit" onclick="submitPush(this)">'
    + esc(t(cfg.submit)) + '</button></div>'
    + '</div>';
  panel.classList.add('is-open');
  var titleInput = panel.querySelector('.tk-title');
  if (titleInput) titleInput.focus();
}

function _ticketFields(rec) {
  var prio = {critical: 1, high: 2, medium: 3, low: 4};
  var suggested = prio[rec.priority] || 3;
  function opt(v, label) {
    return '<option value="' + v + '"' + (suggested === v ? ' selected' : '') + '>' + esc(label) + '</option>';
  }
  return '<div class="tk-row">'
    + '<label class="tk-label">' + esc(t('lbl_ticket_priority'))
    + '<select class="tk-field tk-priority">'
    + opt(1, t('prio_critical')) + opt(2, t('prio_high'))
    + opt(3, t('prio_medium')) + opt(4, t('prio_low'))
    + '</select></label>'
    + '<label class="tk-label">' + esc(t('lbl_ticket_queue'))
    + '<input type="number" class="tk-field tk-queue" min="1" placeholder="—" /></label>'
    + '</div>';
}

function _recFields(rec) {
  // Free text, not a select. myITprocess category and priority vocabularies
  // have not been seen from a live instance, and a dropdown of guessed values
  // is worse than a field the operator can type the real one into.
  return '<div class="tk-row">'
    + '<label class="tk-label">' + esc(t('lbl_rec_category'))
    + '<input type="text" class="tk-field tk-category" maxlength="100" placeholder="—" /></label>'
    + '<label class="tk-label">' + esc(t('lbl_rec_priority'))
    + '<input type="text" class="tk-field tk-rec-priority" maxlength="50" placeholder="'
    + esc(rec.priority || '') + '" /></label>'
    + '</div>';
}

async function submitPush(btn) {
  var row = btn.closest('.rem-row');
  var panel = row.querySelector('.rem-ticket-panel');
  var kind = panel.dataset.kind;
  var cfg = _PUSH_KINDS[kind];
  var recId = row.dataset.recId;

  function val(sel) { var el = panel.querySelector(sel); return el ? el.value.trim() : ''; }

  var body = {rec_id: recId, title: val('.tk-title'), notes: val('.tk-notes')};
  if (kind === 'ticket') {
    var queue = val('.tk-queue');
    body.priority = parseInt(val('.tk-priority'), 10);
    body.queue_id = queue ? parseInt(queue, 10) : null;
  } else {
    body.category = val('.tk-category');
    body.priority = val('.tk-rec-priority');
  }

  // Disabled for the duration, because the server's idempotency is the safety
  // net and not the first line of defence — a double click should not need it.
  btn.disabled = true;
  try {
    var d = await apiFetch('/api/hub/' + encodeURIComponent(_ticketCustomerId) + '/' + cfg.endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (!d || !d.ok) { btn.disabled = false; return; }

    cfg.store()[recId] = d.ticket;
    panel.classList.remove('is-open');
    panel.innerHTML = '';
    var control = row.querySelector('.push-btn[data-kind="' + kind + '"]');
    if (control) control.outerHTML = _pushControl(recId, kind);

    if (d.duplicate_ticket_id) {
      // A real, unowned record exists in the other system. Saying so is the
      // point — the alternative leaves a customer to find it.
      showToast(t(cfg.duplicate)
        .replace('{dup}', '#' + d.duplicate_ticket_id)
        .replace('{id}', '#' + d.ticket.external_id), 'warning');
    } else if (d.created) {
      showToast(t(cfg.created).replace('{id}', '#' + d.ticket.external_id), 'success');
    } else {
      showToast(t(cfg.exists).replace('{id}', '#' + d.ticket.external_id), 'info');
    }
  } catch (e) {
    btn.disabled = false;
  }
}

async function updateRemediation(el) {
  const row = el.closest('.rem-row');
  const recId = row.dataset.recId;
  const select = row.querySelector('.rem-status-select');
  const notesInput = row.querySelector('.rem-notes-input');
  const status = select.value;
  const notes = notesInput.value;

  try {
    const d = await apiFetch('/api/remediation', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({rec_id: recId, status: status, notes: notes}),
    });

    if (d.ok) {
      const badge = row.querySelector('.rem-status-badge');
      const labels = {open: t('status_open','Åpen'), in_progress: t('status_in_progress','Pågår'), done: t('status_done_label','Utført'), ignored: t('status_ignored','Ignorert')};
      const colors = {open:'var(--red)', in_progress:'var(--orange)', done:'var(--green)', ignored:'var(--text-dim)'};
      const bgs = {open:'#f8514915', in_progress:'#d2992215', done:'#3fb95015', ignored:'#8b949e15'};
      badge.textContent = labels[status];
      badge.style.color = colors[status];
      badge.style.background = bgs[status];
      badge.style.borderColor = colors[status] + '30';
      loadRemediation();
    }
  } catch(e) { console.warn('updateRemediation failed:', e); showToast(t('err_generic','Feil ved oppdatering'), 'error'); }
}

// ── Expiry banner ─────────────────────────────────────────────────────────────
let _expiryData = null;

async function loadExpiryBanner() {
  try {
    const d = await apiFetch('/api/expiry/check');
    _expiryData = d;
    renderExpiryBanner(d);
  } catch(e) { console.warn('loadExpiryBanner failed:', e); }
}

function renderExpiryBanner(d) {
  const area = document.getElementById('expiry-banner-area');
  if (!area) return;
  const urgent = (d.items || []).filter(i => i.category === 'expired' || i.category === 'critical' || i.category === 'warning');
  if (urgent.length === 0) { area.innerHTML = ''; return; }
  const hasExpired  = urgent.some(i => i.category === 'expired');
  const hasCritical = urgent.some(i => i.category === 'critical');
  const cls = hasExpired ? 'has-expired' : hasCritical ? 'has-critical' : 'has-warning';
  const titleText = hasExpired ? t('expiry_expired','Credentials have expired!') : hasCritical ? t('expiry_critical','Credentials expiring soon!') : t('expiry_warning','Credentials expiring within 30 days');
  const itemsHtml = urgent.map(i => {
    const typeLabel = i.type === 'secret' ? t('expiry_type_secret','Client secret') : t('expiry_type_cert','Certificate');
    const daysText = i.days_remaining < 0 ? t('expiry_days_ago','expired {days} days ago').replace('{days}', Math.abs(i.days_remaining)) : t('expiry_days_remaining','{days} days remaining').replace('{days}', i.days_remaining);
    return '<div class="expiry-item"><span class="expiry-dot ' + i.category + '"></span><strong>' + esc(i.customer_name) + '</strong> — ' + typeLabel + ' (' + esc(i.expiry_date) + ', ' + daysText + ')</div>';
  }).join('');
  area.innerHTML = '<div class="expiry-banner ' + cls + '"><div class="expiry-banner-title"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg> ' + titleText + '</div>' + itemsHtml + '</div>';
}

function getExpiryBadgeForCustomer(customerId) {
  if (!_expiryData || !_expiryData.items) return '';
  const items = _expiryData.items.filter(i => i.customer_id === customerId && (i.category === 'expired' || i.category === 'critical' || i.category === 'warning'));
  if (items.length === 0) return '';
  const worst = items[0].category;
  const label = worst === 'expired' ? t('expiry_badge_expired','Expired') : worst === 'critical' ? t('expiry_badge_critical','Critical') : t('expiry_badge_warning','Expiring soon');
  return '<span class="cust-expiry-badge ' + worst + '">' + label + '</span>';
}

// ── Customer actions ───────────────────────────────────────────────────────────
async function newCustomer() {
  if (!await showConfirm(t('dlg_confirm_wipe'))) return;
  await apiFetch('/api/customer/wipe', { method: 'POST' });
  loadStatus();
}

async function renewCreds() {
  if (!await showConfirm(t('dlg_confirm_renew'))) return;
  await apiFetch('/api/customer/renew', { method: 'POST' });
  loadStatus();
}

// ── Setup flow ─────────────────────────────────────────────────────────────────
// Whether a setup run is in flight. Without it, landing on this view showed an
// empty "Progress" box with no form, no button and no explanation — a screen
// that could only be understood by somebody who already knew it was a log.
var _setupRunning = false;

// The parts of the view that only make sense once a run has started.
function _setupProgressCard() {
  var log = document.getElementById('setup-log');
  return log ? log.closest('.card') : null;
}

// What this screen looks like before anybody has asked for anything.
function _renderSetupIdle() {
  if (_setupRunning) return;   // a run owns the screen; leave it alone

  var view = document.getElementById('view-setup');
  if (!view) return;
  var card = _setupProgressCard();
  if (card) card.style.display = 'none';
  var dc = document.getElementById('device-code-card');
  if (dc) dc.classList.remove('visible');
  var result = document.getElementById('setup-result-area');
  if (result) result.innerHTML = '';

  var intro = document.getElementById('setup-intro');
  if (!intro) {
    intro = document.createElement('div');
    intro.id = 'setup-intro';
    intro.className = 'card';
    var anchor = card || result;
    if (anchor) view.insertBefore(intro, anchor); else view.appendChild(intro);
  }
  intro.style.display = '';
  intro.innerHTML =
      '<div class="card-title">' + esc(t('setup_intro_title')) + '</div>'
    + '<div style="font-size:13px;color:var(--text-muted);line-height:1.6;margin-bottom:16px;">'
    +   esc(t('setup_intro_body'))
    + '</div>'
    + '<div style="font-size:13px;color:var(--text-muted);line-height:1.9;margin-bottom:20px;">'
    +   '<div>' + icon('check', 14) + ' ' + esc(t('setup_intro_step_auth')) + '</div>'
    +   '<div>' + icon('check', 14) + ' ' + esc(t('setup_intro_step_cert')) + '</div>'
    +   '<div>' + icon('check', 14) + ' ' + esc(t('setup_intro_step_save')) + '</div>'
    + '</div>'
    + '<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">'
    +   '<button data-write class="btn btn-primary" onclick="startSetup()">'
    +     esc(t('btn_start_setup')) + '</button>'
    +   '<span style="font-size:12px;color:var(--text-dim);">' + esc(t('setup_intro_needs_ga')) + '</span>'
    + '</div>';

  // The button is a write action; re-run the gate so a read-only user sees the
  // explanation without an action they cannot take.
  if (typeof applyWriteCapability === 'function') applyWriteCapability();
}

function startSetup() {
  _setupRunning = true;   // before showView, so it does not render the idle state
  showView('setup');
  var intro = document.getElementById('setup-intro');
  if (intro) intro.style.display = 'none';
  var card = _setupProgressCard();
  if (card) card.style.display = '';
  document.getElementById('setup-log').innerHTML = '';
  document.getElementById('device-code-card').classList.remove('visible');
  document.getElementById('setup-result-area').innerHTML = '';

  _runSetupStream('/api/setup/stream');
}

// Read the setup SSE stream, re-attaching on a dropped connection. Setup is
// server-owned now — it keeps running and saves credentials even if this tab
// closes — so recovery is re-attaching with ?attach=1, which only ever attaches
// and never starts a second setup. The re-attach replays the device code so the
// operator can still finish signing in.
async function _runSetupStream(url) {
  while (_setupRunning) {
    var outcome = await _attemptSetupStream(url);
    if (outcome === 'done' || !_setupRunning) return;
    appendSetupLog({step:'NET', status:'warn', msg: t('msg_setup_reconnecting')});
    await new Promise(function(r){ setTimeout(r, 2000); });
    url = '/api/setup/stream?attach=1';
  }
}

async function _attemptSetupStream(url) {
  try {
    var resp = await fetch(url);
    if (!resp.ok) {
      appendSetupLog({step:'NET', status:'error', msg:'HTTP '+resp.status});
      _setupRunning = false;
      return 'done';
    }
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buf = '';
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buf += decoder.decode(chunk.value, {stream:true});
      var lines = buf.split('\n'); buf = lines.pop();
      for (var i = 0; i < lines.length; i++) {
        if (!lines[i].startsWith('data: ')) continue;
        try {
          var d = JSON.parse(lines[i].slice(6));
          if (d.type === 'log') appendSetupLog(d);
          else if (d.type === 'device_code') showDeviceCode(d);
          else if (d.type === 'error') appendSetupLog({step:'ERROR', status:'error', msg:d.msg});
          else if (d.type === 'ended') {
            // Re-attach found no active setup (finished or never started). Stop.
            _setupRunning = false;
            return 'done';
          } else if (d.type === 'done') {
            _setupRunning = false;
            hideDeviceCode();
            if (d.success) {
              apiFetch('/api/customers/register', {method:'POST'});
              document.getElementById('setup-result-area').innerHTML =
                '<div class="alert alert-success">'+t('msg_setup_complete')+'</div><button class="btn btn-primary" onclick="showView(\'home\')">'+t('btn_go_home')+'</button>';
            } else {
              document.getElementById('setup-result-area').innerHTML =
                '<div class="alert alert-error">'+t('msg_setup_failed')+'</div><button class="btn btn-default" onclick="startSetup()">'+t('btn_try_again')+'</button>';
            }
            return 'done';
          }
        } catch(_) {}
      }
    }
    return false;  // stream closed without 'done' — re-attach
  } catch (e) {
    return false;  // network error — re-attach
  }
}

function appendSetupLog(d) {
  const log = document.getElementById('setup-log');
  const icon = d.status === 'ok' ? '✓' : d.status === 'warn' ? '' : '✗';
  const cls  = d.status === 'ok' ? 'ok' : d.status === 'warn' ? 'warn' : 'error';
  const step = d.step ? `[${d.step}]` : '';
  const line = document.createElement('div');
  line.className = `log-line ${cls}`;
  line.innerHTML = `<span class="log-icon">${icon}</span><span class="log-step">${esc(step)}</span><span class="log-msg">${esc(d.msg)}</span>`;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

let _deviceCodeUrl = '';

function showDeviceCode(d) {
  const card = document.getElementById('device-code-card');
  document.getElementById('dc-code').textContent = d.code;
  const urlEl = document.getElementById('dc-url');
  urlEl.textContent = d.url;
  urlEl.href = d.url;
  _deviceCodeUrl = d.url;
  card.classList.add('visible');
  card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  // Auto-copy code and open private browser
  navigator.clipboard.writeText(d.code).then(() => {
    document.getElementById('dc-copy-hint').textContent = t('msg_code_copied_auto');
  }).catch(() => {});
  openPrivateBrowser();
}

// Open the sign-in URL in the operator's own browser.
//
// This used to POST to /api/open-private, which ran subprocess.Popen on the
// *server*. The server is headless and the technician is on a different
// machine entirely, so the button spawned a browser process nobody could
// see, then reported "Firefox (privat)" — the browser the server happened
// to have, not the one the reader was sitting in front of.
//
// A page cannot open a private window: browsers refuse that deliberately,
// and no flag or API changes it. So this opens a normal tab and the UI says
// plainly that a private session is the reader's own step. Being honest
// about it beats a button that claims something it never did.
function openPrivateBrowser() {
  if (!_deviceCodeUrl) return;
  var info = document.getElementById('dc-browser-info');
  var win = window.open(_deviceCodeUrl, '_blank', 'noopener,noreferrer');
  if (info) {
    info.textContent = win
      ? t('setup_opened_in_tab', 'Åpnet i ny fane')
      : t('setup_popup_blocked', 'Nettleseren blokkerte fanen — bruk lenken under');
  }
}

function hideDeviceCode() {
  document.getElementById('device-code-card').classList.remove('visible');
}

function copyCode() {
  const code = document.getElementById('dc-code').textContent;
  navigator.clipboard.writeText(code).then(() => {
    document.getElementById('dc-copy-hint').textContent = t('msg_copied');
    setTimeout(() => {
      document.getElementById('dc-copy-hint').textContent = t('msg_click_to_copy');
    }, 2000);
  });
}

// Copy the device sign-in URL. A page cannot open the reader's default browser
// in a private tab (see openPrivateBrowser), so when the popup is blocked — or
// the operator wants a different browser entirely — copy-paste is the reliable
// path. The URL is short and fixed (login.microsoft.com/device), but typing it
// by hand from another machine is exactly the friction this removes.
function copyDeviceUrl() {
  if (!_deviceCodeUrl) return;
  navigator.clipboard.writeText(_deviceCodeUrl).then(() => {
    showToast(t('msg_copied_short', 'Kopiert!'), 'success', 1500);
  }).catch(() => {});
}

// ── Audit scope selector ────────────────────────────────────────────────────────
let _scopeSections = [];   // [{name, category, enabled}]
let _scopeLoaded = false;
let _scopePanelOpen = false;

function toggleScopePanel() {
  _scopePanelOpen = !_scopePanelOpen;
  const body = document.getElementById('scope-body');
  const icon = document.getElementById('scope-toggle-icon');
  if (!body) return;
  body.style.display = _scopePanelOpen ? 'block' : 'none';
  if (icon) icon.innerHTML = _scopePanelOpen ? '&#9660;' : '&#9654;';
  if (_scopePanelOpen && !_scopeLoaded) loadScopeSections();
}

async function loadScopeSections() {
  try {
    const [secRes, scopeRes] = await Promise.all([
      apiFetch('/api/audit/sections'),
      apiFetch('/api/audit/scope'),
    ]);
    _scopeSections = secRes.sections || [];
    // Apply saved scope if available
    if (scopeRes.scope && scopeRes.scope.enabled_sections) {
      const saved = new Set(scopeRes.scope.enabled_sections);
      _scopeSections.forEach(s => { s.enabled = saved.has(s.name); });
    }
    _scopeLoaded = true;
    renderScopeSections();
    loadPresets();
  } catch (e) {
    const box = document.getElementById('scope-sections');
    if (box) box.innerHTML = '<div style="font-size:12px;color:var(--red);">' + t('err_could_not_load_sections') + '</div>';
  }
}

function renderScopeSections() {
  const box = document.getElementById('scope-sections');
  if (!box) return;
  const categories = {};
  _scopeSections.forEach(s => {
    if (!categories[s.category]) categories[s.category] = [];
    categories[s.category].push(s);
  });
  let html = '';
  for (const [cat, sections] of Object.entries(categories)) {
    const catId = cat.replace(/[^a-zA-Z0-9]/g, '_');
    const allChecked = sections.every(s => s.enabled);
    html += '<div style="min-width:220px;flex:1;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);padding:var(--space-3);">';
    html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-2);">';
    html += '<span style="font-weight:600;font-size:var(--font-xs);color:var(--blue);text-transform:uppercase;letter-spacing:.5px;">' + esc(cat) + ' <span style="color:var(--text-dim);font-weight:400;">(' + sections.length + ')</span></span>';
    html += '<label style="font-size:10px;color:var(--text-dim);cursor:pointer;display:flex;align-items:center;gap:3px;"><input type="checkbox" ' + (allChecked?'checked':'') + ' onchange="toggleScopeGroup(this,\'' + catId + '\')"> ' + t('btn_select_all','Alle') + '</label>';
    html += '</div>';
    for (const s of sections) {
      const id = 'scope-cb-' + s.name.replace(/[^a-zA-Z0-9]/g, '_');
      html += '<label style="display:flex;align-items:center;gap:6px;font-size:var(--font-xs);padding:2px 0;cursor:pointer;" data-scope-group="' + catId + '">';
      html += '<input type="checkbox" id="' + id + '" data-section="' + esc(s.name) + '" ' + (s.enabled ? 'checked' : '') + ' onchange="onScopeChange()">';
      html += esc(s.name) + '</label>';
    }
    html += '</div>';
  }
  box.innerHTML = html;
  updateScopeSummary();
}

function toggleScopeGroup(masterCb, groupId) {
  document.querySelectorAll('[data-scope-group="' + groupId + '"] input[type=checkbox]').forEach(function(cb) {
    cb.checked = masterCb.checked;
  });
  onScopeChange();
}

function onScopeChange() {
  document.querySelectorAll('#scope-sections input[type=checkbox]').forEach(cb => {
    const name = cb.getAttribute('data-section');
    const sec = _scopeSections.find(s => s.name === name);
    if (sec) sec.enabled = cb.checked;
  });
  updateScopeSummary();
  saveScopeDebounced();
}

function updateScopeSummary() {
  const el = document.getElementById('scope-summary');
  if (!el || !_scopeSections.length) return;
  const total = _scopeSections.length;
  const enabled = _scopeSections.filter(s => s.enabled).length;
  el.textContent = t('lbl_sections_selected').replace('{count}', enabled).replace('{total}', total);
}

function scopeSelectAll() {
  _scopeSections.forEach(s => { s.enabled = true; });
  renderScopeSections();
  saveScopeDebounced();
}

function scopeDeselectAll() {
  _scopeSections.forEach(s => { s.enabled = false; });
  renderScopeSections();
  saveScopeDebounced();
}

let _scopeSaveTimer = null;
function saveScopeDebounced() {
  clearTimeout(_scopeSaveTimer);
  _scopeSaveTimer = setTimeout(saveScope, 500);
}

async function saveScope() {
  const enabled = _scopeSections.filter(s => s.enabled).map(s => s.name);
  try {
    await apiFetch('/api/audit/scope', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ enabled_sections: enabled }),
    });
  } catch (_) {}
}

// ── Audit scope presets ──────────────────────────────────────────────────────
let _presets = [];

async function loadPresets() {
  try {
    const d = await apiFetch('/api/audit/presets');
    _presets = d.presets || [];
    renderPresetDropdown();
  } catch (_) {}
}

function renderPresetDropdown() {
  const sel = document.getElementById('preset-select');
  if (!sel) return;
  sel.innerHTML = '<option value="">' + t('lbl_select_preset') + '</option>';
  for (const p of _presets) {
    const opt = document.createElement('option');
    opt.value = p.name;
    opt.textContent = p.name + (p.builtin ? '' : ' ' + t('lbl_custom'));
    sel.appendChild(opt);
  }
}

function applyPreset() {
  const sel = document.getElementById('preset-select');
  const delBtn = document.getElementById('preset-delete-btn');
  if (!sel) return;
  const name = sel.value;
  if (delBtn) delBtn.style.display = 'none';
  if (!name) return;

  const preset = _presets.find(p => p.name === name);
  if (!preset) return;

  if (delBtn && !preset.builtin) delBtn.style.display = '';

  const enabledSet = new Set(preset.sections);
  _scopeSections.forEach(s => { s.enabled = enabledSet.has(s.name); });
  renderScopeSections();
  saveScopeDebounced();
}

async function saveCustomPreset() {
  const name = prompt(t('dlg_preset_name'));
  if (!name || !name.trim()) return;
  const sections = _scopeSections.filter(s => s.enabled).map(s => s.name);
  if (sections.length === 0) { showToast(t('msg_select_min_one_section'), 'warning'); return; }
  try {
    const d = await apiFetch('/api/audit/presets', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ name: name.trim(), sections }),
    });

    if (d.error) { showToast(d.error, 'error'); return; }
    await loadPresets();
    document.getElementById('preset-select').value = name.trim();
    const delBtn = document.getElementById('preset-delete-btn');
    if (delBtn) delBtn.style.display = '';
  } catch (e) { showToast(t('err_could_not_save_preset').replace('{msg}', e.message), 'error'); }
}

async function deleteCustomPreset() {
  const sel = document.getElementById('preset-select');
  if (!sel || !sel.value) return;
  const name = sel.value;
  if (!await showConfirm(t('dlg_confirm_delete_preset').replace('{name}', name))) return;
  try {
    const d = await apiFetch('/api/audit/presets/' + encodeURIComponent(name), { method: 'DELETE' });
    if (d.error) { showToast(d.error, 'error'); return; }
    await loadPresets();
    const delBtn = document.getElementById('preset-delete-btn');
    if (delBtn) delBtn.style.display = 'none';
  } catch (e) { showToast(t('err_could_not_delete_preset').replace('{msg}', e.message), 'error'); }
}

function getSelectedSectionNames() {
  if (!_scopeLoaded || !_scopeSections.length) return null;
  const enabled = _scopeSections.filter(s => s.enabled).map(s => s.name);
  if (enabled.length === _scopeSections.length) return null;
  if (enabled.length === 0) return null; // don't send empty — will run all as safety
  return enabled;
}

// ── Audit flow ─────────────────────────────────────────────────────────────────
const sectionRows = {}; // name -> tr element
const statusOrder = { pending: 0, running: 1, done: 2, skipped: 3, failed: 4 };

async function startAudit() {
  // Quick pre-flight permission check (non-blocking — warn only)
  try {
    const d = await apiFetch('/api/audit/validate-permissions', { method: 'POST' });
    if (d.missing && d.missing.length > 0) {
      const msg = t('dlg_permissions_missing').replace('{count}', d.missing.length).replace('{list}', d.missing.join('\n'));
      if (!await showConfirm(msg)) return;
    }
  } catch (_) {
    // Permission check failed — proceed anyway
  }

  // Reset state
  Object.keys(sectionRows).forEach(k => delete sectionRows[k]);
  sectionDone = 0;
  sectionTotal = 0; // will grow dynamically as sections register

  document.getElementById('section-tbody').innerHTML = '';
  document.getElementById('audit-done-area').style.display = 'none';
  document.getElementById('report-result').innerHTML = '';
  document.getElementById('audit-title').textContent = t('hdr_audit_title');
  document.getElementById('audit-subtitle').textContent = '';
  setAuditStatus('<div class="loader"></div><span>' + t('msg_starting') + '</span>');
  updateProgress(0, sectionTotal);
  window._auditStartTime = Date.now();
  window._auditSectionCount = 0;

  showView('audit');
  _showAuditRunningChrome();
  document.getElementById('audit-back-btn').disabled = true;
  auditRunning = true;
  var _ari = document.getElementById('audit-running-indicator'); if (_ari) _ari.style.display = 'flex';
  startAuditProgressPolling();

  // Build stream URL with optional section filter
  let streamUrl = '/api/audit/stream';
  const _selectedSections = getSelectedSectionNames();
  if (_selectedSections) {
    streamUrl += '?sections=' + encodeURIComponent(_selectedSections.join(','));
  }
  // Use fetch with auth header (EventSource can't send Authorization).
  // Wrapped in _runAuditStreamWithReconnect so a network blip doesn't
  // kill the visual feedback for a multi-hour audit; the polling
  // fallback (startAuditProgressPolling) keeps the progress bar alive
  // and we retry the stream with exponential backoff in the background.
  _runAuditStreamWithReconnect(streamUrl);
}

// Backoff sequence: 2s, 4s, 8s, 16s, 32s — caps at 32s, retries forever
// while auditRunning is true. Operator can navigate away and back to
// reset; closing the browser doesn't stop the server-side audit.
async function _runAuditStreamWithReconnect(streamUrl) {
  // The first call starts the audit. A dropped connection is a lost *view*, not
  // a lost run — the collection continues on the server and saves its results
  // regardless. Recovery re-attaches: GET /audit/stream now re-attaches to this
  // user's running run instead of starting a fresh one, and the reconnect below
  // adds ?attach=1 so a re-open can only ever attach, never launch a duplicate.
  // (The older code could call this exactly once and then only poll, because a
  // blind re-open used to start another audit.)
  const ok = await _attemptAuditStream(streamUrl);
  if (ok === 'done' || !auditRunning) return;
  await _watchAuditUntilServerIdle(false, streamUrl);
}

// Follow a run we can no longer see, until the server says it is over.
var _auditWatching = false;
async function _watchAuditUntilServerIdle(quiet, streamUrl) {
  if (_auditWatching) return;   // one watcher is enough; two would race
  _auditWatching = true;
  try {
    await _watchAuditLoop(quiet, streamUrl);
  } finally {
    _auditWatching = false;
  }
}

async function _watchAuditLoop(quiet, streamUrl) {
  if (!quiet && typeof showToast === 'function') {
    showToast(t('msg_audit_stream_lost'), 'warning', 8000);
  }
  setAuditStatus('<div class="loader"></div><span>' + t('msg_audit_running_no_stream') + '</span>');

  // Re-attach URL forces attach-only, so a re-open can never start a new audit.
  var attachUrl = streamUrl
    ? streamUrl + (streamUrl.indexOf('?') === -1 ? '?' : '&') + 'attach=1'
    : null;

  while (auditRunning) {
    await new Promise(r => setTimeout(r, 3000));
    let d = null;
    try {
      d = await apiFetch('/api/audit/progress');
    } catch (_) {
      continue;  // the server is unreachable; keep watching rather than guess
    }
    // Only an explicit false ends the watch. An older server that does not
    // send `running` leaves it undefined, and guessing "finished" there would
    // reintroduce exactly the wrong-by-assumption bug this replaced.
    if (d && d.running === false) {
      _finishAuditWithoutStream();
      return;
    }
    // The run is alive on the server — go back to watching it *live* rather than
    // polling. attach=1 guarantees this only ever re-attaches, and the running
    // check above means we never re-open against a run that already ended.
    if (attachUrl && d && d.running === true) {
      var outcome = await _attemptAuditStream(attachUrl);
      if (outcome === 'done' || !auditRunning) return;
      // Dropped again — restore the no-stream header and keep watching.
      setAuditStatus('<div class="loader"></div><span>' + t('msg_audit_running_no_stream') + '</span>');
    }
  }
}

// The audit ended while we were not watching. We never received the results
// payload, but the server wrote them to disk, so reload rather than invent.
function _finishAuditWithoutStream() {
  auditRunning = false;
  document.title = _origTitle;
  stopAuditProgressPolling();
  _hideAuditProgressBar();
  var ind = document.getElementById('audit-running-indicator');
  if (ind) ind.style.display = 'none';
  var back = document.getElementById('audit-back-btn');
  if (back) back.disabled = false;
  setAuditStatus('<span style="color:var(--orange)">' + t('msg_audit_done_stream_lost') + '</span>');
  if (typeof loadStatus === 'function') loadStatus();
}

async function _attemptAuditStream(streamUrl) {
  try {
    const resp = await fetch(streamUrl);
    if (!resp.ok) {
      // 409 = an audit is already running. Nothing was started by this call,
      // and there is no way to attach to the existing run's stream, so fall
      // through to watching its progress.
      if (resp.status === 409) return false;
      setAuditStatus('<span style="color:var(--red)">✗ HTTP '+resp.status+'</span>');
      return 'done';
    }
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buf = '';
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buf += decoder.decode(chunk.value, {stream:true});
      var lines = buf.split('\n'); buf = lines.pop();
      for (var i = 0; i < lines.length; i++) {
        if (!lines[i].startsWith('data: ')) continue;
        try {
          var d = JSON.parse(lines[i].slice(6));
          if (d.type === 'started') {
            var ts = new Date().toLocaleString('no-NO', {dateStyle:'short',timeStyle:'short'});
            document.getElementById('audit-title').textContent = t('hdr_audit_title') + ' \u2014 ' + d.customer;
            document.getElementById('audit-subtitle').textContent = ts;
            setAuditStatus('<div class="loader"></div><span>' + t('msg_audit_running') + '</span>');
          } else if (d.type === 'progress') {
            handleProgress(d);
          } else if (d.type === 'snapshot') {
            // Re-attach replay: jump the status to where the run is now; live
            // 'progress' events follow and fill in the per-section detail.
            if (typeof d.completed === 'number' && typeof d.total_sections === 'number') {
              setAuditStatus('<div class="loader"></div><span>' + t('msg_audit_running_sections').replace('{done}', d.completed).replace('{total}', d.total_sections) + '</span>');
            }
          } else if (d.type === 'ended') {
            // A re-attach found no active run (it finished or was cleared while
            // we were away). Reload to whatever the server saved.
            _finishAuditWithoutStream();
            return 'done';
          } else if (d.type === 'done') {
            auditRunning = false; document.title = _origTitle;
            stopAuditProgressPolling(); _hideAuditProgressBar();
            var _ari_d = document.getElementById('audit-running-indicator'); if (_ari_d) _ari_d.style.display = 'none';
            document.getElementById('audit-back-btn').disabled = false;
            handleAuditDone(d.results || []);
            if (d.email_status) {
              var area = document.getElementById('report-result');
              var color = d.email_status.ok ? 'var(--green)' : 'var(--orange)';
              var icon = d.email_status.ok ? '✓' : '';
              area.innerHTML += '<div class="alert" style="color:'+color+';margin-top:8px;font-size:13px;">'+icon+' '+esc(d.email_status.msg)+'</div>';
            }
            return 'done';
          } else if (d.type === 'error') {
            auditRunning = false; document.title = _origTitle;
            stopAuditProgressPolling(); _hideAuditProgressBar();
            var _ari_e = document.getElementById('audit-running-indicator'); if (_ari_e) _ari_e.style.display = 'none';
            document.getElementById('audit-back-btn').disabled = false;
            setAuditStatus('<span style="color:var(--red)">✗ '+t('status_error')+': '+esc(d.msg)+'</span>');
            return 'done';
          } else if (d.type === 'cancelled') {
            auditRunning = false; document.title = _origTitle;
            stopAuditProgressPolling(); _hideAuditProgressBar();
            setAuditStatus('<span style="color:var(--orange)">'+esc(d.msg)+'</span>');
            return 'done';
          }
        } catch(_) {}
      }
    }
    // Stream closed cleanly without 'done' — let reconnect loop handle it
    return false;
  } catch (e) {
    // Network error / connection reset — caller will retry with backoff
    return false;
  }
}

function handleProgress(d) {
  const { name, status, detail } = d;
  const icons = { pending:'', running:'', done:'✓', skipped:'→', failed:'✗' };
  const cls   = { pending:'s-pending', running:'s-running', done:'s-done', skipped:'s-skipped', failed:'s-failed' };
  const labels= { pending:t('status_pending'), running:t('status_running'), done:t('status_done'), skipped:t('status_skipped'), failed:t('status_failed') };

  if (sectionRows[name]) {
    const tr = sectionRows[name];
    tr.querySelector('.status-icon').textContent = icons[status] || '•';
    tr.querySelector('.status-icon').className = `status-icon ${cls[status] || ''}`;
    tr.querySelector('.status-text').textContent = statusLabel(status, labels);
    tr.querySelector('.status-text').className = `status-text ${cls[status] || ''}`;
    if (detail && status === 'failed') {
      tr.querySelector('.detail-cell').innerHTML += `<div class="err-text">${esc(detail)}</div>`;
    }
  } else {
    const tbody = document.getElementById('section-tbody');
    const tr = document.createElement('tr');
    // No pointer and no expander: the findings live in the summary above, so
    // there is nothing here to reveal. Every row used to offer the affordance,
    // including the twelve with an empty detail cell and nothing behind it.
    tr.innerHTML = `
      <td><span class="status-icon ${cls[status] || ''}">${icons[status] || '•'}</span></td>
      <td style="font-weight:500;">${esc(name)}</td>
      <td><span class="status-text ${cls[status] || ''}">${statusLabel(status, labels)}</span></td>
      <td class="detail-cell">${detail && status === 'failed' ? `<div class="err-text">${esc(detail)}</div>` : ''}</td>`;
    tbody.appendChild(tr);
    sectionRows[name] = tr;
  }

  const terminal = ['done', 'skipped', 'failed'];
  if (terminal.includes(status)) {
    sectionDone++;
    updateProgress(sectionDone, sectionTotal);
    setAuditStatus('<div class="loader"></div><span>' + t('msg_audit_running_sections').replace('{done}', sectionDone).replace('{total}', sectionTotal) + '</span>');
  }
}

// Everything the run flagged, gathered in one place and ordered by weight.
//
// The section table answers "did every section run", which is what you want
// while it is running. Afterwards the question is "what is wrong", and that
// answer was spread across twenty-six rows — most of them empty, since a
// section with nothing to report still takes a full row — with the longest
// lists truncated behind "+n til". Nothing is removed; this sits above it.
// A section that finished as expected says nothing; the icon already does.
// "Hoppet over" and "Feilet" keep their words, because those differ.
function statusLabel(status, labels) {
  return status === 'done' ? '' : (labels[status] || status);
}

function renderAuditFindings(results) {
  var box = document.getElementById('audit-findings');
  if (!box) return;

  var failures = [], skipped = [], findings = [];
  results.forEach(function (r) {
    // A skipped section carries its reason in the same field a failed one
    // uses, so "no Azure subscriptions found" — which is a legitimate skip on
    // a tenant without Azure — was announced as four failures in red at the
    // top of the list, while the table below correctly said "Hoppet over".
    // Status decides; the reason is only the wording.
    if (r.error && r.status === 'failed') failures.push({ section: r.name, text: r.error });
    else if (r.error && r.status === 'skipped') skipped.push({ section: r.name, text: r.error });
    (r.warns || []).forEach(function (w, i) {
      var level = (r.warn_levels || [])[i] || 'warn';
      findings.push({ section: r.name, text: w, level: level });
    });
  });

  if (!failures.length && !findings.length && !skipped.length) {
    box.style.display = 'block';
    box.innerHTML = '<div class="card" style="border-left:3px solid var(--green);">'
      + '<div style="font-weight:600;color:var(--green);">&#10003; '
      + esc(t('audit_no_findings', 'Ingen varsler')) + '</div>'
      + '<div style="color:var(--text-dim);font-size:12px;margin-top:4px;">'
      + esc(t('audit_no_findings_detail', 'Alle seksjoner fullførte uten å flagge noe.'))
      + '</div></div>';
    return;
  }

  function list(items, colour, heading) {
    if (!items.length) return '';
    return '<div style="margin-bottom:12px;">'
      + '<div style="font-weight:600;color:' + colour + ';margin-bottom:6px;font-size:13px;">'
      + esc(heading) + ' (' + items.length + ')</div>'
      + items.map(function (f) {
          // Wraps rather than squeezing: a fixed basis pinched the section
          // name to a few characters once the pane got narrow, and the app is
          // otherwise built for that — the tables scroll, the layout breaks at
          // 1100, 767 and 479.
          return '<div style="display:flex;flex-wrap:wrap;gap:2px 8px;padding:4px 0;'
            + 'border-bottom:1px solid var(--border);font-size:12px;">'
            + '<span style="color:var(--text-dim);flex:0 0 150px;min-width:120px;">'
            + esc(f.section) + '</span>'
            + '<span style="flex:1 1 220px;">' + esc(f.text) + '</span></div>';
        }).join('')
      + '</div>';
  }

  box.style.display = 'block';
  var anyCritical = findings.some(function (f) { return f.level === 'critical'; });
  box.innerHTML = '<div class="card" style="border-left:3px solid '
    + (failures.length || anyCritical ? 'var(--red)' : 'var(--orange)') + ';">'
    + list(failures, 'var(--red)', t('status_failed', 'Feilet'))
    + list(findings.filter(function (f) { return f.level === 'critical'; }),
           'var(--red)', t('status_critical_findings', 'Kritiske funn'))
    + list(findings.filter(function (f) { return f.level !== 'critical'; }),
           'var(--orange)', t('status_warnings', 'Varsler'))
    + list(skipped, 'var(--text-dim)', t('status_skipped', 'Hoppet over'))
    + '</div>';
}

function handleAuditDone(results) {
  let done = 0, warns = 0, failed = 0;

  // Update rows with final data (fills in warns and files)
  for (const r of results) {
    const status = r.status;
    const icons  = { pending:'', running:'', done:'✓', skipped:'→', failed:'✗' };
    const cls    = { pending:'s-pending', running:'s-running', done:'s-done', skipped:'s-skipped', failed:'s-failed' };
    const labels = { pending:t('status_pending'), running:t('status_running'), done:t('status_done'), skipped:t('status_skipped'), failed:t('status_failed') };

    if (sectionRows[r.name]) {
      const tr = sectionRows[r.name];
      // Update icon/status in case last progress event was 'running'
      tr.querySelector('.status-icon').textContent = icons[status] || '•';
      tr.querySelector('.status-icon').className = `status-icon ${cls[status] || ''}`;
      tr.querySelector('.status-text').textContent = statusLabel(status, labels);
      tr.querySelector('.status-text').className = `status-text ${cls[status] || ''}`;

      // The summary above carries every finding, labelled with its section.
      // This table used to carry them too — three times over: the first three
      // as pills, the remainder behind "+n til", and all of them again in an
      // expander. Two of those three renderings were lossy, and the lossy ones
      // were the visible ones.
      //
      // So the table keeps only what the summary cannot answer: whether each
      // section ran. An error or a skip reason belongs to the section rather
      // than to the findings list, so those stay.
      const detailCell = tr.querySelector('.detail-cell');
      if (r.warns && r.warns.length > 0) warns++;
      detailCell.innerHTML = r.error ? `<div class="err-text">${esc(r.error)}</div>` : '';

    }

    if (status === 'done' || status === 'skipped') done++;
    if (status === 'failed') { done++; failed++; }
  }

  updateProgress(results.length, results.length);
  var elapsed = window._auditStartTime ? Math.round((Date.now() - window._auditStartTime) / 1000) : 0;
  var elapsedStr = elapsed >= 60 ? Math.floor(elapsed/60) + 'm ' + (elapsed%60) + 's' : elapsed + 's';
  var totalFiles = results.reduce(function(s,r){ return s + (r.files ? r.files.length : 0); }, 0);
  setAuditStatus('<span style="color:var(--green)">' + t('msg_audit_complete').replace('{count}', results.length) + ' <span style="color:var(--text-dim);font-weight:400;">(' + elapsedStr + ' · ' + totalFiles + ' ' + t('nav_files','files') + ')</span></span>');

  document.getElementById('sum-done').textContent = done;
  document.getElementById('sum-warn').textContent = warns;
  document.getElementById('sum-fail').textContent = failed;
  document.getElementById('audit-done-area').style.display = 'block';
  renderAuditFindings(results);

  // Browser notification if tab is hidden
  if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
    new Notification('Sybr HUB', {
      body: t('msg_audit_complete','Audit complete').replace('{count}', results.length) + ' — ' + elapsedStr,
      icon: '/branding/sybr_logo_transparent.png',
    });
  }

  // Check grade and celebrate if A!
  setTimeout(async function() {
    try {
      var dash = await apiFetch('/api/dashboard');
      if (dash && dash.metrics && dash.metrics.risk_grade === 'A') {
        _celebrateConfetti();
        showToast('' + t('msg_grade_a','Grade A — excellent security posture!'), 'success', 5000);
      }
    } catch(e) {}
  }, 1500);
}

var _origTitle = document.title;
function updateProgress(done, total) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  document.getElementById('progress-fill').style.width = pct + '%';
  document.getElementById('progress-pct').textContent = pct + '%';
  document.getElementById('progress-label').textContent = t('audit_sections_count').replace('{done}', done).replace('{total}', total);
  // Update browser tab title with progress
  if (auditRunning) document.title = t('lbl_audit','Audit') + ' ' + pct + '% — ' + _origTitle;
  else document.title = _origTitle;
}

function setAuditStatus(html) {
  document.getElementById('audit-status-bar').innerHTML = html;
}

// ── Audit progress polling (REST) ───────────────────────────────────────────
var _auditProgressTimer = null;

function startAuditProgressPolling() {
  stopAuditProgressPolling();
  pollAuditProgress();  // don't wait 2s for the first honest denominator
  _auditProgressTimer = setInterval(pollAuditProgress, 2000);
}

function stopAuditProgressPolling() {
  if (_auditProgressTimer) { clearInterval(_auditProgressTimer); _auditProgressTimer = null; }
}

async function pollAuditProgress() {
  if (!auditRunning) { stopAuditProgressPolling(); _hideAuditProgressBar(); return; }
  try {
    var d = await apiFetch('/api/audit/progress');
    if (!d || !d.total_sections) return;
    // Update the global indicator in the header
    var ind = document.getElementById('audit-running-indicator');
    if (ind && ind.style.display !== 'none') {
      ind.innerHTML = '<span style="width:8px;height:8px;border-radius:50%;background:#fff;display:inline-block;"></span> '
        + 'Audit ' + d.progress + '% — ' + esc(d.current_section);
    }
    // The audit view's own bar used to derive its total from the sections that
    // had already announced themselves, so it read n / n after every section
    // and sat at 100% for the whole run. The server knows the real section
    // list; take the denominator from it and let the SSE handler move the
    // numerator between polls.
    if (typeof d.total_sections === 'number' && d.total_sections > 0) {
      sectionTotal = d.total_sections;
      if (currentView === 'audit') updateProgress(d.completed, sectionTotal);
    }
    // Update floating progress bar (shown on non-audit views)
    _showAuditProgressBar(d);
  } catch(e) { /* expected during SSE transition */ }
}

function _showAuditProgressBar(d) {
  var bar = document.getElementById('audit-progress-float');
  if (!bar) return;
  // Hide when already on the audit view (it has its own progress bar)
  if (currentView === 'audit') { bar.style.display = 'none'; return; }
  bar.style.display = 'block';
  var pct = d.progress || 0;
  bar.querySelector('.apf-fill').style.width = pct + '%';
  bar.querySelector('.apf-text').textContent = pct + '% — ' + (d.current_section || '...');
  bar.querySelector('.apf-counts').textContent = d.completed + ' / ' + d.total_sections;
}

function _hideAuditProgressBar() {
  var bar = document.getElementById('audit-progress-float');
  if (bar) bar.style.display = 'none';
}

function auditBack() {
  if (auditRunning) return;
  showView('home');
}

// ── Report generation ──────────────────────────────────────────────────────────
async function generateReport(fmt, reportType) {
  const area = currentView === 'history-report'
    ? document.getElementById('hist-report-result')
    : document.getElementById('report-result');
  const label = reportType === 'customer' ? t('lbl_customer_report') : t('lbl_tech_report');
  area.innerHTML = '<div class="loader"></div> ' + t('msg_generating_report').replace('{label}', label);

  try {
    const d_report = await apiFetch('/api/report/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format: fmt, report_type: reportType, lang: (currentView === 'history-report' ? document.getElementById('hist-report-lang')?.value : document.getElementById('report-lang')?.value) || 'no', frameworks: (currentView === 'history-report' ? document.getElementById('hist-report-frameworks')?.value : document.getElementById('report-frameworks')?.value) || 'all', theme: (currentView === 'history-report' ? document.getElementById('hist-report-theme')?.value : document.getElementById('report-theme')?.value) || 'light' }),
    });
    const d = d_report;
    if (!d) { area.innerHTML = '<div class="alert alert-error">' + t('err_could_not_generate_report') + '</div>'; return; }
    if (d.error) {
      area.innerHTML = `<div class="alert alert-error">${esc(d.error)}</div>`;
      return;
    }
    if (fmt === 'html' && d.html_url) {
      area.innerHTML = '<div class="alert alert-success" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--space-2);">'
        + '<span>' + esc(label) + '</span>'
        + '<div style="display:flex;gap:var(--space-2);">'
        + '<button class="btn btn-primary btn-sm" onclick="openReportViewer(\'' + d.html_url + '\')">' + t('vis_i_app') + '</button>'
        + '<a href="' + d.html_url + '" target="_blank" class="btn btn-ghost btn-sm">' + t('ny_fane') + '</a>'
        + '</div></div>';
    } else if (fmt === 'pdf' && d.pdf_url) {
      var _dlLink = '<a href="' + d.pdf_url + '" download style="color:var(--green);">' + t('msg_report_generated_download').replace('{label}', esc(label)).replace('✓ ', '').split(' — ')[1] + '</a>';
      area.innerHTML = '<div class="alert alert-success">✓ ' + esc(label) + ' (PDF) — ' + _dlLink + '</div>';
      window.open(d.pdf_url, '_blank');
    } else {
      area.innerHTML = '<div class="alert alert-success">' + t('msg_report_generated').replace('{label}', esc(label)) + '</div>';
    }
  } catch (e) {
    area.innerHTML = '<div class="alert alert-error">✗ ' + t('err_network_error').replace('{msg}', esc(e.message)) + '</div>';
  }
}

// ── Report Viewer ─────────────────────────────────────────────────────────────
function openReportViewer(url) {
  var modal = document.getElementById('report-viewer-modal');
  modal.style.display = 'flex';
  document.getElementById('report-viewer-link').href = url;
  document.getElementById('report-viewer-title').textContent = url.split('/').pop() || '';
  document.getElementById('report-viewer-iframe').src = url;
}
function closeReportViewer() {
  document.getElementById('report-viewer-modal').style.display = 'none';
  document.getElementById('report-viewer-iframe').src = 'about:blank';
}

// ── Remediation Tracking UI ──────────────────────────────────────────────────
async function loadRemediationPanel(containerId) {
  var el = document.getElementById(containerId);
  if (!el) return;
  try {
    var d = await apiFetch('/api/remediation');
    if (!d || d.error) { el.innerHTML = ''; return; }
    var items = d.items || {};
    var keys = Object.keys(items);
    if (keys.length === 0) {
      el.innerHTML = emptyStateHTML({
        variant: 'inline',
        icon: '\u{2705}',
        title: t('msg_no_remediation_title', 'Ingen anbefalinger ennå'),
        desc: t('msg_no_remediation', 'Ingen anbefalinger registrert. Kjør en audit først.'),
        actions: [
          { label: t('btn_run_audit', 'Kjør audit'), onclick: 'startAudit()', primary: true },
        ],
      });
      return;
    }

    var statusIcons = {open:'\u25CB', in_progress:'\u25D0', done:'\u2713', ignored:'\u2014'};
    var statusLabels = {open:t('status_open','Åpen'), in_progress:t('status_in_progress','Pågår'), done:t('status_done_label','Utført'), ignored:t('status_ignored','Ignorert')};
    var pct = d.pct || 0;
    var html = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-4);">'
      + '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;">' + t('hdr_remediation','Remediering') + '</div>'
      + '<div style="font-size:var(--font-sm);color:var(--text-muted);">' + t('msg_remediation_progress','{done}/{total} utført ({pct}%)').replace('{done}',d.done).replace('{total}',d.total).replace('{pct}',pct.toFixed(0)) + '</div></div>'
      + '<div style="background:var(--bg);border-radius:var(--radius-sm);height:6px;margin-bottom:var(--space-4);overflow:hidden;">'
      + '<div style="height:100%;width:' + pct + '%;background:var(--green);border-radius:var(--radius-sm);transition:width 0.4s;"></div></div>';

    keys.forEach(function(recId) {
      var item = items[recId];
      var st = item.status || 'open';
      // The stored key is an id now; the server resolves it back to a sentence
      // in the reader's language. An id shown raw means the finding no longer
      // appears in the latest run.
      var title = item.title || recId;
      html += '<div style="display:flex;align-items:flex-start;gap:var(--space-3);padding:var(--space-3) 0;border-bottom:1px solid var(--border);">'
        + '<span style="font-size:14px;flex-shrink:0;cursor:pointer;" onclick="cycleRemediation(\'' + esc(recId).replace(/'/g,"\\'") + '\',\'' + st + '\')" title="' + t('tip_click_change_status','Klikk for å endre status') + '">' + statusIcons[st] + '</span>'
        + '<div style="flex:1;min-width:0;">'
        + '<div style="font-size:var(--font-sm);' + (st==='done'?'text-decoration:line-through;color:var(--text-dim);':'') + '">' + esc(title) + '</div>'
        + (item.notes ? '<div style="font-size:var(--font-xs);color:var(--text-dim);margin-top:2px;">' + esc(item.notes) + '</div>' : '')
        + (item.updated_date ? '<div style="font-size:10px;color:var(--text-dim);margin-top:2px;">' + (item.updated_by||'') + ' — ' + new Date(item.updated_date).toLocaleDateString('no-NO') + '</div>' : '')
        + '</div></div>';
    });
    el.innerHTML = html;
  } catch(e) { el.innerHTML = ''; }
}

async function cycleRemediation(recId, currentStatus) {
  var cycle = {open:'in_progress', in_progress:'done', done:'ignored', ignored:'open'};
  var next = cycle[currentStatus] || 'open';
  await apiFetch('/api/remediation', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({rec_id:recId, status:next})});
  loadRemediationPanel('remediation-panel');
}

async function exportCSV() {
  const area = currentView === 'history-report'
    ? document.getElementById('hist-report-result')
    : document.getElementById('report-result');
  area.innerHTML = '<div class="loader"></div> ' + t('msg_generating_csv');
  try {
    const r = await fetch('/api/report/csv', { method: 'POST' });
    if (!r.ok) {
      try { const d = await r.json(); area.innerHTML = `<div class="alert alert-error">✗ ${esc(d.error)}</div>`; } catch(_) { area.innerHTML = '<div class="alert alert-error">' + t('err_export_failed','Export failed') + '</div>'; }
      return;
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'audit_export.csv';
    a.click();
    URL.revokeObjectURL(url);
    area.innerHTML = '<div class="alert alert-success">' + t('msg_csv_downloaded') + '</div>';
  } catch(e) {
    area.innerHTML = `<div class="alert alert-error">✗ ${esc(e.message)}</div>`;
  }
}

function openFolder() {
  apiFetch('/api/open-folder', { method: 'POST' }).catch(() => {});
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function _vpnStatField(label, value) {
  if (!value) return '';
  return '<div><div style="color:var(--text-dim);">' + esc(label) + '</div><div style="font-family:var(--mono);color:var(--text);font-weight:600;">' + esc(String(value)) + '</div></div>';
}

function _formatBytes(bytes) {
  if (!bytes || bytes < 1024) return (bytes||0) + ' B';
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB';
  if (bytes < 1073741824) return (bytes/1048576).toFixed(1) + ' MB';
  return (bytes/1073741824).toFixed(2) + ' GB';
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
    return d.toLocaleDateString('no-NO', {day:'2-digit',month:'short'});
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

// ── Webhook test ────────────────────────────────────────────────────────────────
async function testWebhook() {
  const url = document.getElementById('input-webhook-url').value.trim();
  const result = document.getElementById('webhook-test-result');
  if (!url) { result.textContent = '' + t('err_no_url'); return; }
  result.textContent = '' + t('msg_sending');
  try {
    const d = await apiFetch('/api/scheduler/test-webhook', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({webhook_url: url})
    });

    result.textContent = d.ok ? t('msg_uploaded_success') : '' + (d.error || t('status_error'));
    result.style.color = d.ok ? 'var(--green)' : 'var(--red)';
  } catch(e) { result.textContent = '' + e.message; }
}

// ── Email test ──────────────────────────────────────────────────────────────────
async function testEmail() {
  const result = document.getElementById('email-test-result');
  const server = document.getElementById('input-smtp-server').value.trim();
  if (!server) { result.textContent = '' + t('err_configure_smtp_first'); result.style.color = 'var(--red)'; return; }
  result.textContent = '' + t('msg_sending');
  result.style.color = 'var(--text-muted)';
  try {
    const d = await apiFetch('/api/email/test', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        smtp_server: server,
        smtp_port: parseInt(document.getElementById('input-smtp-port').value) || 587,
        smtp_user: document.getElementById('input-smtp-user').value.trim(),
        smtp_password: document.getElementById('input-smtp-password').value.trim(),
        smtp_from: document.getElementById('input-smtp-from').value.trim(),
        to: document.getElementById('input-email-recipient').value.trim(),
      })
    });
    result.textContent = d.ok ? '✓ ' + t('btn_test_email') + '!' : '' + (d.error || t('status_error'));
    result.style.color = d.ok ? 'var(--green)' : 'var(--red)';
  } catch(e) { result.textContent = '' + e.message; result.style.color = 'var(--red)'; }
}

// ── Logo upload ─────────────────────────────────────────────────────────────────
function refreshLogoPreview() {
  const img = document.getElementById('logo-preview');
  const noPreview = document.getElementById('logo-no-preview');
  const ts = Date.now();
  const testImg = new Image();
  testImg.onload = () => { img.src = '/api/settings/logo?t=' + ts; img.style.display = ''; noPreview.style.display = 'none'; };
  testImg.onerror = () => { img.style.display = 'none'; noPreview.style.display = ''; };
  testImg.src = '/api/settings/logo?t=' + ts;
}

async function uploadLogo() {
  const input = document.getElementById('input-logo-file');
  const msg = document.getElementById('logo-upload-msg');
  if (!input.files || !input.files[0]) { msg.textContent = t('msg_choose_file_first'); msg.style.color = 'var(--red)'; return; }
  msg.textContent = t('btn_uploading'); msg.style.color = 'var(--text-muted)';
  try {
    const fd = new FormData();
    fd.append('file', input.files[0]);
    const d = await apiFetch('/api/settings/logo', { method: 'POST', body: fd });
    if (d.ok) {
      msg.textContent = t('msg_logo_uploaded'); msg.style.color = 'var(--green)';
      refreshLogoPreview();
      input.value = '';
    } else {
      msg.textContent = d.error || t('status_error'); msg.style.color = 'var(--red)';
    }
  } catch(e) { msg.textContent = t('status_error') + ': ' + e.message; msg.style.color = 'var(--red)'; }
}

// ── Settings modal ─────────────────────────────────────────────────────────────
async function openSettings() {
  try {
    const d = await apiFetch('/api/settings');
    document.getElementById('input-audit-dir').value = d.audit_dir_custom || '';
    document.getElementById('input-cert-dir').value = d.cert_dir_custom || '';
    document.getElementById('input-company-name').value = d.branding?.company_name || '';
    document.getElementById('input-contact-email').value = d.branding?.contact_email || '';
    document.getElementById('input-website').value = d.branding?.website || '';
    var _bc = d.branding?.primary_color || '#4d9fb5';
    document.getElementById('input-brand-color').value = _bc;
    document.getElementById('input-brand-color-hex').value = _bc;
    document.getElementById('input-brand-color').oninput = function(){ document.getElementById('input-brand-color-hex').value = this.value; };
    document.getElementById('input-brand-color-hex').oninput = function(){ if(/^#[0-9a-fA-F]{6}$/.test(this.value)) document.getElementById('input-brand-color').value = this.value; };
    // Load logo preview
    refreshLogoPreview();
    document.getElementById('settings-current-dir').textContent =
      t('lbl_active_dir') + ': ' + d.audit_dir;
    document.getElementById('settings-msg').textContent = '';
    var _slt = document.getElementById('input-show-log-tab');
    if (_slt) _slt.checked = localStorage.getItem('msptk_show_log_tab') === '1';
    var _sdt = document.getElementById('input-show-docs-tab');
    if (_sdt) _sdt.checked = localStorage.getItem('msptk_show_docs_tab') === '1';

    // Set language selector
    var langSel = document.getElementById('input-language');
    if (langSel) langSel.value = _lang;

    // Load IT Glue settings
    document.getElementById('input-itglue-key').value = d.itglue_api_key || '';
    document.getElementById('input-itglue-region').value = d.itglue_region || 'eu';

    // Load email settings
    document.getElementById('input-smtp-server').value = d.smtp_server || '';
    document.getElementById('input-smtp-port').value = d.smtp_port || 587;
    document.getElementById('input-smtp-user').value = d.smtp_user || '';
    document.getElementById('input-smtp-password').value = d.smtp_password || '';
    document.getElementById('input-smtp-from').value = d.smtp_from || '';
    document.getElementById('input-email-recipient').value = d.email_default_recipient || '';
    document.getElementById('input-email-auto-send').checked = d.email_auto_send || false;

    // Load scheduler config
    try {
      const sched = await apiFetch('/api/scheduler');
      document.getElementById('input-scheduler-enabled').checked = sched.enabled || false;
      document.getElementById('input-scheduler-audit-all').checked = sched.audit_all_customers !== false;
      document.getElementById('input-scheduler-interval').value = sched.interval_hours || 168;
      document.getElementById('input-webhook-url').value = sched.webhook_url || '';
      document.getElementById('input-scheduler-backup').checked = sched.backup_after_audit || false;
      // Load alert_on event preferences
      const ao = sched.alert_on || {};
      document.getElementById('alert-audit-completed').checked = ao.audit_completed !== false;
      document.getElementById('alert-risk-score-drop').checked = ao.risk_score_drop !== false && ao.risk_score_drop !== 0;
      document.getElementById('alert-risk-score-drop-threshold').value = (typeof ao.risk_score_drop === 'number' ? ao.risk_score_drop : 5);
      document.getElementById('alert-new-risky-users').checked = ao.new_risky_users !== false;
      document.getElementById('alert-expired-credentials').checked = ao.expired_credentials !== false;
      document.getElementById('alert-secure-score-drop').checked = ao.secure_score_drop !== false && ao.secure_score_drop !== 0;
      document.getElementById('alert-secure-score-drop-threshold').value = (typeof ao.secure_score_drop === 'number' ? ao.secure_score_drop : 5);
      document.getElementById('alert-new-nsg-warnings').checked = ao.new_nsg_warnings !== false;
      document.getElementById('alert-mfa-below-threshold').checked = ao.mfa_below_threshold !== false && ao.mfa_below_threshold !== 0;
      document.getElementById('alert-mfa-threshold').value = (typeof ao.mfa_below_threshold === 'number' ? ao.mfa_below_threshold : 80);
    } catch (e) { console.warn('Scheduler settings init failed:', e); }

    // Load thresholds
    var th = d.thresholds || {};
    var _thEl;
    _thEl = document.getElementById('threshold-mfa'); if (_thEl) _thEl.value = th.mfa_pct || 80;
    _thEl = document.getElementById('threshold-secure-score'); if (_thEl) _thEl.value = th.secure_score_pct || 75;
    _thEl = document.getElementById('threshold-credential-days'); if (_thEl) _thEl.value = th.credential_warn_days || 30;
    _thEl = document.getElementById('threshold-alert-interval'); if (_thEl) _thEl.value = th.alert_interval_hours || 6;
    _thEl = document.getElementById('threshold-password-min'); if (_thEl) _thEl.value = th.password_min_length || 8;
    _thEl = document.getElementById('threshold-needs-audit'); if (_thEl) _thEl.value = th.needs_audit_days || 30;

    // Load backup info
    loadBackupInfo();

    // Load version info into settings modal
    try {
      const vr = await apiFetch('/api/version');
      const vi = document.getElementById('settings-version-info');
      if (vi) {
        vi.innerHTML = t('settings_version_info').replace('{version}', vr.describe || vr.version).replace('{commit}', vr.commit_hash || 'N/A').replace('{branch}', vr.branch || 'N/A').replace('{date}', vr.commit_date || 'N/A').replace(/\n/g, '<br>');
      }
      // Self-update is admin-only and only for a git checkout. The server
      // enforces both (admin role + can_write); this just decides visibility.
      var updRow = document.getElementById('settings-update-row');
      if (updRow && _currentUser && _currentUser.role === 'admin') {
        try {
          var sv = await apiFetch('/api/system/version');
          if (sv && sv.updatable) updRow.classList.remove('hidden');
        } catch (e) { /* leave hidden */ }
      }
    } catch (e) { /* ignore */ }
    // System info
    try {
      var si = await apiFetch('/api/system-info');
      var sEl = document.getElementById('settings-system-info');
      if (sEl && si) {
        sEl.innerHTML = 'Python: ' + esc(si.python_version) + '<br>'
          + 'Platform: ' + esc(si.platform) + '<br>'
          + 'DB: ' + si.db_size_mb + ' MB<br>'
          + t('nav_files','Files') + ': ' + si.audit_files + ' (' + si.audit_size_mb + ' MB)<br>'
          + 'PID: ' + si.pid;
      }
    } catch(e) {}
  } catch (e) {
    document.getElementById('settings-current-dir').textContent = t('msg_loading_settings_failed');
  }
  document.getElementById('settings-modal').classList.add('open');
  // Snapshot form values for dirty-flag detection
  _snapshotSettingsForm();
  _initSettingsDirtyTracking();
}

// ── Self-update (admin) ───────────────────────────────────────────────────────
// Pulls the deployed branch to origin and restarts onto the new code. The
// server does the git work and re-execs itself; here we confirm, kick it off,
// and poll /api/system/version until the new commit answers, then reload so the
// browser picks up the new frontend assets too.

async function runSelfUpdate() {
  var statusEl = document.getElementById('settings-update-status');
  var btn = document.getElementById('btn-self-update');
  if (!confirm(t('confirm_self_update', 'Update Sybr HUB to the latest code and restart? The app will be briefly unavailable.'))) return;
  if (btn) btn.disabled = true;
  if (statusEl) statusEl.textContent = t('msg_updating', 'Updating…');
  try {
    var d = await apiFetch('/api/system/update', { method: 'POST' });
    if (!d || !d.ok) {
      if (statusEl) statusEl.textContent = t('msg_update_failed', 'Update failed');
      if (btn) btn.disabled = false;
      return;
    }
    if (!d.restarting) {
      if (statusEl) statusEl.textContent = t('msg_already_current', 'Already up to date ({commit}).').replace('{commit}', d.to || '');
      if (btn) btn.disabled = false;
      return;
    }
    if (statusEl) statusEl.textContent = t('msg_update_restarting', 'Updated {from} → {to}. Restarting…').replace('{from}', d.from).replace('{to}', d.to);
    _pollForRestart(String(d.to || ''));
  } catch (e) {
    if (statusEl) statusEl.textContent = (e && e.message) ? e.message : t('msg_update_failed', 'Update failed');
    if (btn) btn.disabled = false;
  }
}

function _pollForRestart(expectedCommit) {
  var statusEl = document.getElementById('settings-update-status');
  var tries = 0;
  var iv = setInterval(async function () {
    tries++;
    try {
      var v = await apiFetch('/api/system/version');
      // running_commit is the SHA the *answering process* booted with, not the
      // working tree on disk — the tree advances ~1s before the re-exec, so
      // v.commit would flip to the new SHA while the OLD process is still
      // serving. Matching running_commit means the NEW process is up. It is the
      // short SHA and expectedCommit is the longer to-SHA, so prefix-match it.
      if (v && v.running_commit && expectedCommit.indexOf(v.running_commit) === 0) {
        clearInterval(iv);
        if (statusEl) statusEl.textContent = t('msg_update_done', 'Updated. Reloading…');
        setTimeout(function () { location.reload(); }, 800);
        return;
      }
    } catch (e) { /* server is mid-restart; keep polling */ }
    if (tries > 60) {  // ~2 minutes
      clearInterval(iv);
      if (statusEl) statusEl.textContent = t('msg_update_timeout', 'Restart is taking longer than expected — reload the page manually.');
    }
  }, 2000);
}

// ── Settings dirty-flag detection ─────────────────────────────────────────────
var _settingsSnapshot = null;
var _settingsDirty = false;

function _snapshotSettingsForm() {
  var modal = document.getElementById('settings-modal');
  var data = {};
  modal.querySelectorAll('input, select, textarea').forEach(function(el) {
    var key = el.id || el.name;
    if (!key) return;
    if (el.type === 'checkbox' || el.type === 'radio') {
      data[key] = el.checked;
    } else {
      data[key] = el.value;
    }
  });
  _settingsSnapshot = data;
  _settingsDirty = false;
}

function _isSettingsDirty() {
  if (!_settingsSnapshot) return false;
  var modal = document.getElementById('settings-modal');
  var dirty = false;
  modal.querySelectorAll('input, select, textarea').forEach(function(el) {
    var key = el.id || el.name;
    if (!key) return;
    var current = (el.type === 'checkbox' || el.type === 'radio') ? el.checked : el.value;
    if (_settingsSnapshot[key] !== undefined && _settingsSnapshot[key] !== current) dirty = true;
  });
  return dirty;
}

var _settingsDirtyTrackingInit = false;
function _initSettingsDirtyTracking() {
  if (_settingsDirtyTrackingInit) return;
  _settingsDirtyTrackingInit = true;
  var modal = document.getElementById('settings-modal');
  modal.addEventListener('input', function() { _settingsDirty = true; });
  modal.addEventListener('change', function() { _settingsDirty = true; });
}

function closeSettings() {
  if (_settingsDirty && _isSettingsDirty()) {
    if (!confirm(t('du_har_ulagrede_endringer_vil'))) return;
  }
  _settingsSnapshot = null;
  _settingsDirty = false;
  document.getElementById('settings-modal').classList.remove('open');
}

function closeSettingsOnBackdrop(e) {
  if (e.target === document.getElementById('settings-modal')) closeSettings();
}

// ── Permission validation ──────────────────────────────────────────────────────

function closePermissionsModal() {
  document.getElementById('permissions-modal').classList.remove('open');
}

async function checkPermissions() {
  const modal = document.getElementById('permissions-modal');
  const title = document.getElementById('perm-modal-title');
  const desc  = document.getElementById('perm-modal-desc');
  const body  = document.getElementById('perm-modal-body');

  title.textContent = t('hdr_permissions_check');
  desc.textContent = t('permissions_checking_desc');
  body.innerHTML = '<div style="display:flex;align-items:center;gap:8px;padding:24px 0;justify-content:center;"><div class="loader"></div><span style="color:var(--text-muted);">' + t('msg_checking_permissions') + '</span></div>';
  modal.classList.add('open');

  try {
    const d = await apiFetch('/api/audit/validate-permissions', { method: 'POST' });
    renderPermissionsResult(d);
  } catch (e) {
    desc.textContent = '';
    body.innerHTML = '<div class="alert alert-error">' + t('err_could_not_check_perms').replace('{msg}', esc(e.message)) + '</div>';
  }
}

function renderPermissionsResult(d) {
  const desc  = document.getElementById('perm-modal-desc');
  const body  = document.getElementById('perm-modal-body');

  const granted = d.granted || [];
  const missing = d.missing || [];
  const warnings = d.warnings || [];
  const connectivity = d.connectivity;

  // Summary line
  if (d.ok && missing.length === 0) {
    desc.innerHTML = '<span style="color:var(--green);font-weight:600;">' + t('msg_all_permissions_ok') + '</span>' +
      (connectivity ? ' ' + t('msg_connection_verified') : '');
  } else if (d.ok) {
    desc.innerHTML = '<span style="color:var(--orange);font-weight:600;">' + t('msg_non_critical_missing').replace('{count}', missing.length) + '</span>';
  } else {
    const critMissing = missing.filter(p => !warnings.some(w => w.startsWith(p)));
    desc.innerHTML = '<span style="color:var(--red);font-weight:600;">' + t('msg_permissions_missing').replace('{count}', missing.length) + '</span>' +
      (critMissing.length ? ' ' + t('msg_critical_count').replace('{count}', critMissing.length) : '');
  }

  let html = '';

  // Connectivity badge
  html += `<div style="margin-bottom:12px;padding:8px 12px;border-radius:6px;background:${connectivity ? 'rgba(63,185,80,0.1)' : 'rgba(248,81,73,0.1)'};border:1px solid ${connectivity ? 'rgba(63,185,80,0.3)' : 'rgba(248,81,73,0.3)'};font-size:13px;">` +
    `${connectivity ? '<span style="color:var(--green);">&#10003;</span> ' + t('msg_graph_connection_ok') : '<span style="color:var(--red);">&#10007;</span> ' + t('msg_graph_connection_failed')}` +
    '</div>';

  // Warnings
  if (warnings.length > 0) {
    html += '<div style="margin-bottom:12px;">';
    for (const w of warnings) {
      html += `<div style="font-size:12px;color:var(--orange);padding:3px 0;">${esc(w)}</div>`;
    }
    html += '</div>';
  }

  // Permission list table
  const allPerms = [...granted.map(p => ({name: p, ok: true})), ...missing.map(p => ({name: p, ok: false}))];
  allPerms.sort((a, b) => a.name.localeCompare(b.name));

  html += '<div style="border:1px solid var(--border);border-radius:6px;overflow:hidden;">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="background:var(--bg);"><th style="text-align:left;padding:6px 10px;font-weight:600;">' + t('lbl_permission') + '</th><th style="width:60px;text-align:center;padding:6px 10px;font-weight:600;">' + t('lbl_status') + '</th></tr></thead><tbody>';

  for (const p of allPerms) {
    const isWarnOnly = warnings.some(w => w.startsWith(p.name));
    let icon, color;
    if (p.ok) {
      icon = '&#10003;'; color = 'var(--green)';
    } else if (isWarnOnly) {
      icon = ''; color = 'var(--orange)';
    } else {
      icon = '&#10007;'; color = 'var(--red)';
    }
    html += `<tr style="border-top:1px solid var(--border);">`;
    html += `<td style="padding:5px 10px;font-family:var(--mono);font-size:11px;">${esc(p.name)}</td>`;
    html += `<td style="text-align:center;padding:5px 10px;color:${color};font-weight:700;">${icon}</td>`;
    html += '</tr>';
  }
  html += '</tbody></table></div>';

  html += '<div style="margin-top:10px;font-size:12px;color:var(--text-muted);">' + t('msg_permissions_granted').replace('{granted}', granted.length).replace('{total}', granted.length + missing.length) + '</div>';

  body.innerHTML = html;
}

// ── Encryption key backup/restore ──────────────────────────────────────────────
async function backupEncryptionKey() {
  if (!await showConfirm(t('dlg_confirm_show_key'))) return;
  try {
    const d = await apiFetch('/api/encryption/key-backup');
    if (!d.ok) { showToast(t('status_error') + ': ' + (d.error || t('err_unknown')), 'error'); return; }
    document.getElementById('encryption-key-value').textContent = d.key;
    document.getElementById('encryption-key-display').style.display = 'block';
    document.getElementById('encryption-copy-msg').textContent = '';
  } catch (e) { showToast(t('err_could_not_fetch_key', 'Kunne ikke hente nøkkel') + ': ' + e.message, 'error'); }
}

function copyEncryptionKey() {
  const key = document.getElementById('encryption-key-value').textContent;
  navigator.clipboard.writeText(key).then(() => {
    document.getElementById('encryption-copy-msg').textContent = t('btn_copied');
    setTimeout(() => { document.getElementById('encryption-copy-msg').textContent = ''; }, 3000);
  });
}

function showRestoreKeyInput() {
  document.getElementById('encryption-restore-input').style.display = 'block';
  document.getElementById('encryption-restore-msg').textContent = '';
}

async function restoreEncryptionKey() {
  const key = document.getElementById('input-restore-key').value.trim();
  const msg = document.getElementById('encryption-restore-msg');
  if (!key) { msg.textContent = t('msg_paste_key_first'); msg.style.color = 'var(--danger)'; return; }
  if (!await showConfirm(t('dlg_confirm_replace_key'))) return;
  try {
    const d = await apiFetch('/api/encryption/key-restore', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ key })
    });

    if (d.ok) {
      msg.textContent = t('msg_key_restored'); msg.style.color = 'var(--success)';
      document.getElementById('input-restore-key').value = '';
    } else {
      msg.textContent = d.error || t('err_invalid_key'); msg.style.color = 'var(--danger)';
    }
  } catch (e) { msg.textContent = t('status_error') + ': ' + e.message; msg.style.color = 'var(--danger)'; }
}

// ── Settings tabs ────────────────────────────────────────────────────────────
// ── Change Password ──────────────────────────────────────────────────────────
async function showChangePasswordModal() {
  var html = '<div style="font-size:var(--font-sm);font-weight:600;margin-bottom:var(--space-4);">' + t('btn_change_password','Change password') + '</div>'
    + '<input id="pw-current" type="password" class="field-input" placeholder="' + t('placeholder_current_password','Current password') + '" style="margin-bottom:var(--space-3);">'
    + '<input id="pw-new" type="password" class="field-input" placeholder="' + t('placeholder_new_password','New password (min 8)') + '" style="margin-bottom:var(--space-3);">'
    + '<input id="pw-confirm" type="password" class="field-input" placeholder="' + t('placeholder_confirm_password','Confirm new password') + '" style="margin-bottom:var(--space-3);">'
    + '<div id="pw-change-msg" style="font-size:var(--font-xs);margin-bottom:var(--space-3);"></div>'
    + '<div style="display:flex;gap:var(--space-2);justify-content:flex-end;">'
    + '<button class="btn btn-ghost" onclick="document.getElementById(\'confirm-modal\').style.display=\'none\'">' + t('btn_cancel') + '</button>'
    + '<button class="btn btn-primary" onclick="doChangePassword()">' + t('btn_save') + '</button>'
    + '</div>';
  document.getElementById('confirm-modal-title').textContent = '';
  document.getElementById('confirm-modal-body').innerHTML = html;
  document.getElementById('confirm-modal-body').style.display = 'block';
  document.querySelector('#confirm-modal .modal-actions').style.display = 'none';
  document.getElementById('confirm-modal').style.display = 'flex';
}

async function doChangePassword() {
  var cur = document.getElementById('pw-current').value;
  var nw = document.getElementById('pw-new').value;
  var cf = document.getElementById('pw-confirm').value;
  var msg = document.getElementById('pw-change-msg');
  if (nw.length < 8) { msg.innerHTML = '<span style="color:var(--red);">' + t('err_password_min_length') + '</span>'; return; }
  if (nw !== cf) { msg.innerHTML = '<span style="color:var(--red);">' + t('err_passwords_mismatch','Passwords do not match') + '</span>'; return; }
  var d = await apiFetch('/api/auth/change-password', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({current_password:cur, new_password:nw})});
  if (d && d.ok) {
    document.getElementById('confirm-modal').style.display = 'none';
    document.querySelector('#confirm-modal .modal-actions').style.display = '';
    showToast(t('msg_password_changed','Password changed'), 'success', 3000);
  } else {
    msg.innerHTML = '<span style="color:var(--red);">' + (d && d.error ? esc(d.error) : t('status_error')) + '</span>';
  }
}

// ── User Management ──────────────────────────────────────────────────────────
function showAddUserForm() { document.getElementById('add-user-form').style.display = 'block'; }

async function loadUsers() {
  var el = document.getElementById('users-list');
  if (!el) return;
  try {
    var d = await apiFetch('/api/auth/users');
    if (!d || !d.users) { el.innerHTML = '<div class="text-muted text-sm">' + t('status_error') + '</div>'; return; }
    var roleColors = {admin:'var(--blue)',technician:'var(--green)',viewer:'var(--text-dim)'};
    el.innerHTML = d.users.map(function(u) {
      var rc = roleColors[u.role] || 'var(--text-dim)';
      var lastLogin = u.last_login ? timeAgo(u.last_login) : t('msg_never','never');
      return '<div data-user-id="'+esc(u.id)+'" style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-3);border-bottom:1px solid var(--border);">'
        + '<div style="flex:1;">'
        + '<div style="font-weight:600;">' + esc(u.display_name) + ' <span style="font-size:var(--font-xs);color:var(--text-dim);font-family:var(--mono);">@' + esc(u.username) + '</span></div>'
        + '<div style="font-size:var(--font-xs);color:var(--text-dim);">' + t('lbl_last_prefix','Last:') + ' ' + lastLogin + '</div>'
        + '</div>'
        + '<select style="padding:2px 6px;font-size:var(--font-xs);border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg);color:var(--text);" onchange="changeUserRole(\'' + esc(u.id) + '\',this.value)">'
        + '<option value="viewer"' + (u.role==='viewer'?' selected':'') + '>' + t('viewer_2') + '</option>'
        + '<option value="technician"' + (u.role==='technician'?' selected':'') + '>' + t('technician_2') + '</option>'
        + '<option value="admin"' + (u.role==='admin'?' selected':'') + '>' + t('admin_2') + '</option>'
        + '</select>'
        + _capabilityToggles(u)
        + '<button class="btn btn-ghost btn-sm" onclick="editUserCustomers(\'' + esc(u.id) + '\',\'' + esc(u.display_name) + '\')" title="' + t('tip_customer_access','Customer access') + '"></button>'
        + (u.username !== (_currentUser && _currentUser.username) ? '<button class="btn btn-ghost btn-sm" style="color:var(--red);" onclick="deleteUser(\'' + esc(u.id) + '\',\'' + esc(u.username) + '\')">' + t('btn_delete') + '</button>' : '')
        + '</div>';
    }).join('');
  } catch(e) { el.innerHTML = ''; }
}

async function createUser() {
  var u = document.getElementById('new-user-username').value.trim();
  var n = document.getElementById('new-user-displayname').value.trim();
  var p = document.getElementById('new-user-password').value;
  var r = document.getElementById('new-user-role').value;
  var msg = document.getElementById('add-user-msg');
  if (!u || !p || p.length < 8) { msg.innerHTML = '<span style="color:var(--red);">' + t('err_password_min_length','Password must be at least 8 characters') + '</span>'; return; }
  var d = await apiFetch('/api/auth/users', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username:u, display_name:n||u, password:p, role:r})});
  if (d && d.ok) {
    document.getElementById('add-user-form').style.display = 'none';
    document.getElementById('new-user-username').value = '';
    document.getElementById('new-user-displayname').value = '';
    document.getElementById('new-user-password').value = '';
    loadUsers();
    showToast(t('msg_user_created','User created'), 'success', 2000);
  } else {
    msg.innerHTML = '<span style="color:var(--red);">' + (d && d.error ? esc(d.error) : t('status_error')) + '</span>';
  }
}

// Two capabilities, shown as what they are: grants, not part of the role.
// tenant_write is disabled until write is on, mirroring the server — it stands
// on can_write, and an account that may not save a note here has no business
// changing configuration in a customer's tenant.
function _capabilityToggles(u) {
  var write = !!u.can_write, tenant = !!u.tenant_write;
  return '<label style="display:flex;align-items:center;gap:4px;font-size:var(--font-xs);color:var(--text-muted);cursor:pointer;white-space:nowrap;" title="' + t('tip_cap_write','May change anything in Sybr HUB. Off by default for every account.') + '">'
    + '<input type="checkbox"' + (write ? ' checked' : '') + ' onchange="setUserCapability(\'' + esc(u.id) + '\',\'can_write\',this.checked)"> ' + t('lbl_cap_write','Write')
    + '</label>'
    + '<label style="display:flex;align-items:center;gap:4px;font-size:var(--font-xs);color:' + (write ? 'var(--text-muted)' : 'var(--text-dim)') + ';cursor:' + (write ? 'pointer' : 'not-allowed') + ';white-space:nowrap;" title="' + t('tip_cap_tenant','May write into a customer Microsoft tenant. Requires Write.') + '">'
    + '<input type="checkbox"' + (tenant ? ' checked' : '') + (write ? '' : ' disabled') + ' onchange="setUserCapability(\'' + esc(u.id) + '\',\'tenant_write\',this.checked)"> ' + t('lbl_cap_tenant','Tenant')
    + '</label>';
}

async function setUserCapability(userId, field, enabled) {
  // Removing your own write access is one of the few actions in here that
  // cannot be undone from in here — granting is itself a write, so the account
  // that gives it away needs somebody at a shell to get it back.
  var self = _currentUser && (_currentUser.id === userId);
  if (self && field === 'can_write' && !enabled) {
    var ok = confirm(t('dlg_revoke_own_write',
      'This removes your own write access. Granting it back is itself a write, so you will not be able to do it from here — it needs the grant_write script on the server. Continue?'));
    if (!ok) { loadUsers(); return; }
  }

  var body = {};
  body[field] = enabled;
  // Taking write away takes the tenant capability with it. Leaving it set on
  // an account that may not write at all is a state nobody should have to
  // reason about, and the server would refuse it anyway.
  if (field === 'can_write' && !enabled) body.tenant_write = false;

  var d = await apiFetch('/api/auth/users/' + userId, {
    method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (d && d.ok) {
    showToast(enabled ? t('msg_capability_granted','Access granted') : t('msg_capability_revoked','Access revoked'), 'success', 2000);
  }
  loadUsers();
}

async function changeUserRole(userId, newRole) {
  await apiFetch('/api/auth/users/' + userId, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({role:newRole})});
  showToast(t('msg_role_updated','Role updated'), 'success', 2000);
}

async function deleteUser(userId, username) {
  if (!await showTypedConfirm(
    username,
    t('dlg_confirm_delete_user','Delete user "{name}"?').replace('{name}', username),
    t('dlg_destructive_user_delete', 'Brukeren vil miste all tilgang umiddelbart. Aktive sesjoner avsluttes.')
  )) return;
  await apiFetch('/api/auth/users/' + userId, {method:'DELETE'});
  loadUsers();
  showToast(t('msg_user_deleted','User deleted'), 'success', 2000);
}

async function editUserCustomers(userId, displayName) {
  var panel = document.getElementById('rbac-panel-' + userId);
  if (panel) { panel.remove(); return; }
  // Remove other open panels
  document.querySelectorAll('.rbac-panel').forEach(function(p){p.remove();});

  // Find the user row and append panel after it
  var container = document.getElementById('users-list');
  var rows = container.querySelectorAll('[data-user-id]');
  var targetRow = null;
  rows.forEach(function(r) { if (r.dataset.userId === userId) targetRow = r; });
  if (!targetRow) return;

  var p = document.createElement('div');
  p.id = 'rbac-panel-' + userId;
  p.className = 'rbac-panel';
  p.style.cssText = 'padding:12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;margin:8px 0;';
  p.innerHTML = '<div class="loader" style="width:16px;height:16px;margin:8px auto;"></div>';
  targetRow.after(p);

  // Load customers and current access
  var customers = await apiFetch('/api/customers');
  var access = await apiFetch('/api/auth/users/' + userId + '/customers');
  if (!customers || !customers.customers) return;

  var accessSet = {};
  (access && access.customer_ids || []).forEach(function(id) { accessSet[id] = true; });
  var hasAny = Object.keys(accessSet).length > 0;

  var html = '<div style="font-size:12px;font-weight:600;margin-bottom:8px;">Kundetilgang for ' + esc(displayName) + '</div>';
  html += '<div style="margin-bottom:8px;font-size:11px;color:var(--text-muted);">' + (hasAny ? Object.keys(accessSet).length + ' ' + t('rbac_customers_selected','kunder valgt') : t('rbac_all_customers','Alle kunder (RBAC ikke konfigurert)')) + '</div>';
  html += '<div style="max-height:200px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;padding:4px;">';
  customers.customers.forEach(function(c) {
    var cid = c._id || '';
    var checked = accessSet[cid] ? ' checked' : '';
    html += '<label style="display:flex;align-items:center;gap:6px;padding:3px 6px;font-size:11px;cursor:pointer;"><input type="checkbox" class="rbac-cb" data-cid="'+esc(cid)+'"'+checked+'> '+esc(c.CustomerName||cid)+'</label>';
  });
  html += '</div>';
  html += '<div style="display:flex;gap:8px;margin-top:8px;">';
  html += '<button class="btn btn-primary btn-sm" onclick="saveUserCustomers(\''+userId+'\')">' + t('lagre_2') + '</button>';
  html += '<button class="btn btn-ghost btn-sm" onclick="document.getElementById(\'rbac-panel-'+userId+'\').remove()">' + t('avbryt') + '</button>';
  html += '<button class="btn btn-ghost btn-sm" style="margin-left:auto;font-size:10px;color:var(--text-dim);" onclick="clearUserCustomers(\''+userId+'\')">' + t('fjern_alle_gi_full_tilgang') + '</button>';
  html += '</div>';
  p.innerHTML = html;
}

async function saveUserCustomers(userId) {
  var panel = document.getElementById('rbac-panel-' + userId);
  if (!panel) return;
  var ids = [];
  panel.querySelectorAll('.rbac-cb:checked').forEach(function(cb) { ids.push(cb.dataset.cid); });
  await apiFetch('/api/auth/users/' + userId + '/customers', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({customer_ids:ids})});
  panel.remove();
  showToast(ids.length ? ids.length + ' ' + t('rbac_customers_assigned','kunder tildelt') : t('rbac_full_access','Full tilgang (ingen restriksjoner)'), 'success', 2000);
}

async function clearUserCustomers(userId) {
  await apiFetch('/api/auth/users/' + userId + '/customers', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({customer_ids:[]})});
  var panel = document.getElementById('rbac-panel-' + userId);
  if (panel) panel.remove();
  showToast(t('alle_kunder_tilgjengelig_rbac_fjernet'), 'success', 2000);
}

function switchSettingsTab(btn, paneId) {
  document.querySelectorAll('.settings-tab-btn').forEach(function(b) {
    b.classList.remove('active');
    b.style.borderBottomColor = 'transparent';
  });
  btn.classList.add('active');
  btn.style.borderBottomColor = 'var(--blue)';
  document.querySelectorAll('.settings-tab-pane').forEach(function(p) { p.style.display = 'none'; });
  var pane = document.getElementById(paneId);
  if (pane) pane.style.display = 'block';
  if (paneId === 'stab-users') loadUsers();
}

// ── Branding / White-label ────────────────────────────────────────────────────
async function applyBranding() {
  try {
    var d = await apiFetch('/api/settings');
    if (!d || !d.branding) return;
    var b = d.branding;
    var color = b.primary_color;
    if (color && /^#[0-9a-fA-F]{6}$/.test(color) && color !== '#4d9fb5') {
      var root = document.documentElement;
      root.style.setProperty('--blue', color);
      root.style.setProperty('--border-hi', color);
      // Derive button color (slightly darker)
      var r = parseInt(color.slice(1,3),16), g = parseInt(color.slice(3,5),16), bl = parseInt(color.slice(5,7),16);
      var darker = '#' + [r,g,bl].map(function(c){return Math.max(0,Math.round(c*0.75)).toString(16).padStart(2,'0')}).join('');
      root.style.setProperty('--blue-btn', darker);
      root.style.setProperty('--blue-dark', color + '1a');
      // Header border gradient
      var hdr = document.querySelector('header');
      if (hdr) hdr.style.borderImage = 'linear-gradient(to right, '+color+', transparent) 1';
    }
    // Company name in header
    if (b.company_name) {
      var titleEl = document.querySelector('title');
      if (titleEl) titleEl.textContent = b.company_name + ' — Sybr HUB';
    }
  } catch(e) { /* branding is non-critical */ }
}
function resetBrandColor() {
  document.getElementById('input-brand-color').value = '#4d9fb5';
  document.getElementById('input-brand-color-hex').value = '#4d9fb5';
}

async function saveSettings() {
  const dir = document.getElementById('input-audit-dir').value.trim();
  const msg = document.getElementById('settings-msg');
  msg.textContent = t('btn_saving');
  try {
    const d = await apiFetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        audit_dir: dir,
        cert_dir: document.getElementById('input-cert-dir').value.trim(),
        itglue_api_key: document.getElementById('input-itglue-key').value.trim(),
        itglue_region: document.getElementById('input-itglue-region').value,
        smtp_server: document.getElementById('input-smtp-server').value.trim(),
        smtp_port: parseInt(document.getElementById('input-smtp-port').value) || 587,
        smtp_user: document.getElementById('input-smtp-user').value.trim(),
        smtp_password: document.getElementById('input-smtp-password').value.trim(),
        smtp_from: document.getElementById('input-smtp-from').value.trim(),
        email_default_recipient: document.getElementById('input-email-recipient').value.trim(),
        email_auto_send: document.getElementById('input-email-auto-send').checked,
        branding: {
          company_name: document.getElementById('input-company-name').value.trim(),
          contact_email: document.getElementById('input-contact-email').value.trim(),
          website: document.getElementById('input-website').value.trim(),
          primary_color: document.getElementById('input-brand-color').value,
        },
        thresholds: {
          mfa_pct: parseInt(document.getElementById('threshold-mfa').value) || 80,
          secure_score_pct: parseInt(document.getElementById('threshold-secure-score').value) || 75,
          credential_warn_days: parseInt(document.getElementById('threshold-credential-days').value) || 30,
          alert_interval_hours: parseInt(document.getElementById('threshold-alert-interval').value) || 6,
          password_min_length: parseInt(document.getElementById('threshold-password-min').value) || 8,
          needs_audit_days: parseInt(document.getElementById('threshold-needs-audit').value) || 30,
        },
      }),
    });
    
    if (d.error) {
      msg.style.color = 'var(--red)';
      msg.textContent = '✗ ' + d.error;
    } else {
      msg.style.color = 'var(--green)';
      msg.textContent = t('msg_saved_active_dir').replace('{dir}', d.audit_dir);
      document.getElementById('settings-current-dir').textContent = t('lbl_active_dir') + ': ' + d.audit_dir;
      applyBranding(); // Re-apply brand colors immediately
      // Clear dirty flag and re-snapshot after successful save
      _snapshotSettingsForm();
    }

    // Save scheduler separately
    const schedData = {
      enabled: document.getElementById('input-scheduler-enabled').checked,
      audit_all_customers: document.getElementById('input-scheduler-audit-all').checked,
      interval_hours: parseInt(document.getElementById('input-scheduler-interval').value) || 168,
      webhook_url: document.getElementById('input-webhook-url').value.trim(),
      backup_after_audit: document.getElementById('input-scheduler-backup').checked,
      alert_on: {
        audit_completed: document.getElementById('alert-audit-completed').checked,
        risk_score_drop: document.getElementById('alert-risk-score-drop').checked ? (parseInt(document.getElementById('alert-risk-score-drop-threshold').value) || 5) : false,
        new_risky_users: document.getElementById('alert-new-risky-users').checked,
        expired_credentials: document.getElementById('alert-expired-credentials').checked,
        secure_score_drop: document.getElementById('alert-secure-score-drop').checked ? (parseInt(document.getElementById('alert-secure-score-drop-threshold').value) || 5) : false,
        new_nsg_warnings: document.getElementById('alert-new-nsg-warnings').checked,
        mfa_below_threshold: document.getElementById('alert-mfa-below-threshold').checked ? (parseInt(document.getElementById('alert-mfa-threshold').value) || 80) : false,
      },
    };
    await apiFetch('/api/scheduler', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(schedData)
    });
  } catch (e) {
    msg.style.color = 'var(--red)';
    msg.textContent = '✗ ' + t('err_network_error').replace('{msg}', e.message);
  }
}

async function resetAuditDir() {
  document.getElementById('input-audit-dir').value = '';
  await saveSettings();
}

// ── Backup ──────────────────────────────────────────────────────────────────────

async function loadBackupInfo() {
  try {
    const d = await apiFetch('/api/backup/info');
    const el = document.getElementById('backup-last-info');
    if (d.last_backup_date) {
      const dt = new Date(d.last_backup_date);
      el.innerHTML = t('msg_last_backup') + ': <strong>' + dt.toLocaleString('nb-NO') + '</strong>' +
        (d.last_backup_path ? '<br>' + esc(d.last_backup_path) : '');
    } else {
      el.textContent = t('msg_no_backup_yet');
    }
    document.getElementById('backup-default-dir').textContent = t('msg_default_dir') + ': ' + d.default_backup_dir;
  } catch (e) { /* ignore */ }
}

async function createBackup() {
  const msg = document.getElementById('backup-create-msg');
  msg.style.color = 'var(--text-muted)';
  msg.textContent = t('msg_creating_backup');
  try {
    const dest = document.getElementById('input-backup-dest').value.trim();
    const body = dest ? { dest_path: dest } : {};
    const d = await apiFetch('/api/backup/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (d.error) {
      msg.style.color = 'var(--red)';
      msg.textContent = d.error;
    } else {
      msg.style.color = 'var(--green)';
      const sizeMB = ((d.manifest?.zip_size_bytes || 0) / 1048576).toFixed(1);
      msg.textContent = t('msg_backup_created').replace('{size}', sizeMB).replace('{path}', d.path);
      loadBackupInfo();
    }
  } catch (e) {
    msg.style.color = 'var(--red)';
    msg.textContent = t('status_error') + ': ' + e.message;
  }
}

async function restoreBackup() {
  const msg = document.getElementById('backup-restore-msg');
  const zipPath = document.getElementById('input-restore-path').value.trim();
  if (!zipPath) { msg.style.color = 'var(--red)'; msg.textContent = t('msg_provide_zip_path'); return; }
  msg.style.color = 'var(--text-muted)';
  msg.textContent = t('msg_restoring');
  try {
    const d = await apiFetch('/api/backup/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zip_path: zipPath }),
    });

    if (d.error) {
      msg.style.color = 'var(--red)';
      msg.textContent = d.error;
    } else {
      const files = d.restored_files || {};
      let txt = t('msg_restored_files')
        .replace('{customers}', files.customers || 0)
        .replace('{audits}', files.audits || 0)
        .replace('{config}', files.config || 0)
        .replace('{certs}', files.certs || 0);
      if (files.database) txt += ' ' + t('msg_restored_db');
      if (files.activity_log) txt += ' ' + t('msg_restored_activity_log');
      if (d.restart_required) txt += ' ' + t('msg_restart_required');
      if (d.warning) {
        msg.style.color = 'var(--orange)';
        txt += ' ADVARSEL: ' + d.warning;
      } else {
        msg.style.color = 'var(--green)';
      }
      msg.textContent = txt;
    }
  } catch (e) {
    msg.style.color = 'var(--red)';
    msg.textContent = t('status_error') + ': ' + e.message;
  }
}

// ── Files ───────────────────────────────────────────────────────────────────────
async function loadFiles() {
  const noCustomer = document.getElementById('files-no-customer');
  const content = document.getElementById('files-content');
  try {
    const d = await apiFetch('/api/files');
    if (!d) { content.style.display = 'none'; return; }
    if (!d.has_customer) {
      noCustomer.style.display = 'block';
      content.style.display = 'none';
      return;
    }
    noCustomer.style.display = 'none';
    content.style.display = 'block';

    // Credentials
    const c = d.credentials || {};
    var _elCreds = document.getElementById('files-creds');
    if (_elCreds) _elCreds.innerHTML = `
      <div style="display:grid;grid-template-columns:140px 1fr;gap:4px 12px;">
        <span style="color:var(--text-muted);">${t('lbl_customer')}</span><span><strong>${esc(c.customer_name)}</strong></span>
        <span style="color:var(--text-muted);">${t('lbl_tenant_id')}</span><span style="font-family:var(--mono);font-size:12px;">${esc(c.tenant_id)}</span>
        <span style="color:var(--text-muted);">${t('lbl_client_id')}</span><span style="font-family:var(--mono);font-size:12px;">${esc(c.client_id)}</span>
        <span style="color:var(--text-muted);">${t('lbl_domain')}</span><span>${esc(c.domain)}</span>
        <span style="color:var(--text-muted);">${t('lbl_setup_date')}</span><span>${esc(c.setup_date)}</span>
        <span style="color:var(--text-muted);">${t('lbl_secret_expiry')}</span><span>${esc(c.secret_expiry)}</span>
      </div>`;

    // Certificate
    const cert = d.certificate || {};
    const certStatus = cert.exists
      ? t('files_cert_available').replace('{date}', esc(cert.expiry))
      : t('files_cert_missing');
    const encStatus = cert.encrypted
      ? `<span style="color:var(--green);">${t('status_encrypted')}</span>`
      : `<span style="color:var(--text-muted);">${t('status_password_protected')}</span>`;
    var _elCert = document.getElementById('files-cert');
    if (_elCert) _elCert.innerHTML = `
      <div style="display:grid;grid-template-columns:140px 1fr;gap:4px 12px;">
        <span style="color:var(--text-muted);">${t('lbl_status')}</span><span>${certStatus}</span>
        <span style="color:var(--text-muted);">${t('lbl_protection')}</span><span>${encStatus}</span>
        <span style="color:var(--text-muted);">${t('lbl_location')}</span><span style="font-family:var(--mono);font-size:11px;word-break:break-all;">${esc(cert.path)}</span>
      </div>`;

    // Reports
    const reports = d.reports || [];
    var _elReports = document.getElementById('files-reports');
    if (_elReports) {
      if (reports.length === 0) {
        _elReports.innerHTML = '<span style="color:var(--text-muted);">' + t('msg_no_reports_yet') + '</span>';
      } else {
        let html = '<div style="max-height:200px;overflow-y:auto;">';
        for (const r of reports) {
          html += `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border);font-size:12px;">
            <span>${esc(r.name)}</span>
            <span style="color:var(--text-muted);">${esc(r.size)}</span>
          </div>`;
        }
        html += '</div>';
        _elReports.innerHTML = html;
      }
    }

    // Raw data
    const raw = d.raw_data || {};
    var _elRaw = document.getElementById('files-rawdata');
    if (_elRaw) {
      if (raw.runs === 0) {
        _elRaw.innerHTML = '<span style="color:var(--text-muted);">' + t('msg_no_audit_runs_yet') + '</span>';
      } else {
        _elRaw.innerHTML = `
          <div style="display:grid;grid-template-columns:140px 1fr;gap:4px 12px;">
            <span style="color:var(--text-muted);">${t('lbl_runs')}</span><span>${raw.runs}</span>
            <span style="color:var(--text-muted);">${t('lbl_latest_run')}</span><span>${esc(raw.latest)}</span>
            <span style="color:var(--text-muted);">${t('lbl_total_size')}</span><span>${esc(raw.total_size)}</span>
            <span style="color:var(--text-muted);">${t('lbl_location')}</span><span style="font-family:var(--mono);font-size:11px;word-break:break-all;">${esc(raw.path)}</span>
          </div>`;
      }
    }
  } catch (e) {
    content.innerHTML = '<div class="alert alert-error">' + t('err_could_not_load_files').replace('{msg}', e.message) + '</div>';
    content.style.display = 'block';
    noCustomer.style.display = 'none';
  }
}

var _unifiDirectDevices = [];

async function loadNetworkDevices() {
  var box = document.getElementById('network-devices-content');
  if (!box) return;
  try {
    var d = await apiFetch('/api/network-devices');
    if (!d) { box.innerHTML = '<span style="color:var(--text-muted);">' + t('kunne_ikke_laste_nettverksenheter') + '</span>'; return; }

    var html = '';

    // ── FortiGate ──
    html += '<div class="card" style="margin-bottom:16px;">';
    html += '<div class="card-title">FortiGate</div>';
    if (d.fortigate) {
      html += '<div style="display:grid;grid-template-columns:140px 1fr;gap:4px 12px;margin-bottom:8px;font-size:13px;">';
      html += '<span style="color:var(--text-muted);">' + t('host') + '</span><span style="font-family:var(--mono);font-size:12px;">' + esc(d.fortigate.host) + ':' + d.fortigate.port + '</span>';
      html += '<span style="color:var(--text-muted);">VDOM</span><span>' + esc(d.fortigate.vdom) + '</span>';
      html += '<span style="color:var(--text-muted);">' + t('api_token') + '</span><span>' + (d.fortigate.has_token ? '<span style="color:var(--green);">' + t('konfigurert') + '</span>' : '<span style="color:var(--red);">' + t('mangler') + '</span>') + '</span>';
      html += '</div>';
      html += '<button class="btn btn-default" onclick="toggleNetworkConfig(\'fg-config\')" style="font-size:12px;padding:4px 12px;">' + t('endre') + '</button>';
    } else {
      html += '<div style="font-size:13px;color:var(--text-dim);margin-bottom:8px;">' + t('ikke_konfigurert_2') + '</div>';
      html += '<button class="btn btn-primary" onclick="toggleNetworkConfig(\'fg-config\')" style="font-size:12px;padding:5px 14px;">' + t('konfigurer_fortigate') + '</button>';
    }
    html += '<div id="fg-config" style="display:none;margin-top:12px;padding:12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);">';
    html += '<label class="field-label">' + t('host_ip_eller_fqdn') + '</label>';
    html += '<input class="field-input" id="input-fg-host" type="text" placeholder="192.168.1.1" value="' + esc((d.fortigate && d.fortigate.host) || '') + '">';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">';
    html += '<div><label class="field-label">' + t('port') + '</label><input class="field-input" id="input-fg-port" type="number" value="' + ((d.fortigate && d.fortigate.port) || 443) + '"></div>';
    html += '<div><label class="field-label">VDOM</label><input class="field-input" id="input-fg-vdom" type="text" value="' + esc((d.fortigate && d.fortigate.vdom) || 'root') + '"></div>';
    html += '</div>';
    html += '<label class="field-label" style="margin-top:8px;">' + t('api_token') + '</label>';
    html += '<input class="field-input" id="input-fg-token" type="password" placeholder="Lim inn FortiGate REST API-token">';
    html += '<label style="display:flex;align-items:center;gap:6px;margin-top:8px;font-size:12px;cursor:pointer;"><input type="checkbox" id="input-fg-verify-ssl" ' + (d.fortigate && d.fortigate.verify_ssl ? 'checked' : '') + '> ' + t('verifiser_ssl_sertifikat') + '</label>';
    html += '<div style="display:flex;gap:8px;margin-top:12px;align-items:center;">';
    html += '<button class="btn btn-default" onclick="testFortiGate()" style="font-size:12px;padding:4px 12px;">' + t('test_tilkobling') + '</button>';
    html += '<button class="btn btn-primary" onclick="saveFortiGate()" style="font-size:12px;padding:4px 12px;">' + t('lagre_2') + '</button>';
    html += '<span id="fg-test-result" style="font-size:11px;color:var(--text-muted);"></span>';
    html += '</div></div>';
    html += '</div>';

    // ── UniFi ──
    html += '<div class="card" style="margin-bottom:16px;">';
    html += '<div class="card-title">UniFi</div>';

    var ufMode = (d.unifi && d.unifi.mode) || 'controller';
    _unifiDirectDevices = (d.unifi && d.unifi.direct_devices) || [];

    // Mode selector
    html += '<div style="display:flex;gap:12px;margin-bottom:16px;">';
    html += '<label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;"><input type="radio" name="unifi-mode" value="controller" ' + (ufMode === 'controller' ? 'checked' : '') + ' onchange="toggleUniFiMode()"> ' + t('controller_2') + '</label>';
    html += '<label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;"><input type="radio" name="unifi-mode" value="direct" ' + (ufMode === 'direct' ? 'checked' : '') + ' onchange="toggleUniFiMode()"> ' + t('direkte_enheter') + '</label>';
    html += '</div>';

    // Controller mode
    html += '<div id="unifi-controller-section" style="' + (ufMode === 'controller' ? '' : 'display:none;') + '">';
    if (d.unifi && d.unifi.host && ufMode === 'controller') {
      html += '<div style="display:grid;grid-template-columns:140px 1fr;gap:4px 12px;margin-bottom:8px;font-size:13px;">';
      html += '<span style="color:var(--text-muted);">' + t('controller') + '</span><span style="font-family:var(--mono);font-size:12px;">' + esc(d.unifi.host) + '</span>';
      html += '<span style="color:var(--text-muted);">' + t('type') + '</span><span>' + (d.unifi.is_unifi_os ? 'UniFi OS (UDM/CK)' : 'Classic') + '</span>';
      html += '<span style="color:var(--text-muted);">' + t('site') + '</span><span>' + esc(d.unifi.site) + '</span>';
      html += '<span style="color:var(--text-muted);">' + t('credentials') + '</span><span>' + (d.unifi.has_credentials ? '<span style="color:var(--green);">OK</span>' : '<span style="color:var(--red);">' + t('mangler') + '</span>') + '</span>';
      html += '</div>';
      html += '<button class="btn btn-default" onclick="toggleNetworkConfig(\'uf-ctrl-config\')" style="font-size:12px;padding:4px 12px;">' + t('endre') + '</button>';
    } else {
      html += '<div style="font-size:13px;color:var(--text-dim);margin-bottom:8px;">' + t('ikke_konfigurert_2') + '</div>';
      html += '<button class="btn btn-primary" onclick="toggleNetworkConfig(\'uf-ctrl-config\')" style="font-size:12px;padding:5px 14px;">' + t('konfigurer_controller') + '</button>';
    }
    html += '<div id="uf-ctrl-config" style="display:none;margin-top:12px;padding:12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);">';
    html += '<label class="field-label">' + t('controller_url') + '</label>';
    html += '<input class="field-input" id="input-uf-host" type="text" placeholder="https://192.168.1.1:8443" value="' + esc((d.unifi && d.unifi.host) || '') + '">';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">';
    html += '<div><label class="field-label">' + t('brukernavn') + '</label><input class="field-input" id="input-uf-user" type="text" placeholder="admin"></div>';
    html += '<div><label class="field-label">' + t('passord') + '</label><input class="field-input" id="input-uf-pass" type="password" placeholder="' + t('passord') + '"></div>';
    html += '</div>';
    html += '<label class="field-label" style="margin-top:8px;">' + t('site') + '</label>';
    html += '<input class="field-input" id="input-uf-site" type="text" value="' + esc((d.unifi && d.unifi.site) || 'default') + '" placeholder="default">';
    html += '<label style="display:flex;align-items:center;gap:6px;margin-top:8px;font-size:12px;cursor:pointer;"><input type="checkbox" id="input-uf-os" ' + (d.unifi && d.unifi.is_unifi_os ? 'checked' : '') + '> ' + t('unifi_os_udm_cloud_key_gen2') + '</label>';
    html += '<div style="display:flex;gap:8px;margin-top:12px;align-items:center;">';
    html += '<button class="btn btn-default" onclick="testUniFi()" style="font-size:12px;padding:4px 12px;">' + t('test_tilkobling') + '</button>';
    html += '<button class="btn btn-primary" onclick="saveUniFi()" style="font-size:12px;padding:4px 12px;">' + t('lagre_2') + '</button>';
    html += '<span id="uf-test-result" style="font-size:11px;color:var(--text-muted);"></span>';
    html += '</div></div>';
    html += '</div>';

    // Direct devices mode
    html += '<div id="unifi-direct-section" style="' + (ufMode === 'direct' ? '' : 'display:none;') + '">';
    html += '<div style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">' + t('msg_unifi_direct_desc','Connect directly to individual UniFi devices via IP — no controller required.') + '</div>';
    html += '<div id="unifi-device-list"></div>';

    // Add device form (inline, not prompts)
    html += '<div style="margin-top:12px;padding:12px;border:1px dashed var(--border);border-radius:6px;">';
    html += '<div style="font-weight:600;font-size:12px;margin-bottom:8px;">' + t('btn_add_device','Add device') + '</div>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">';
    html += '<div><label class="field-label">' + t('ip_adresse') + '</label><input class="field-input" id="input-uf-dev-host" type="text" placeholder="192.168.1.10"></div>';
    html += '<div><label class="field-label">' + t('type') + '</label><select class="field-input" id="input-uf-dev-type" style="padding:8px 12px;"><option value="ap">' + t('access_point') + '</option><option value="gateway">' + t('gateway_firewall') + '</option><option value="switch">' + t('switch') + '</option></select></div>';
    html += '</div>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">';
    html += '<div><label class="field-label">' + t('brukernavn') + '</label><input class="field-input" id="input-uf-dev-user" type="text" value="ubnt" placeholder="ubnt"></div>';
    html += '<div><label class="field-label">' + t('passord') + '</label><input class="field-input" id="input-uf-dev-pass" type="password" value="ubnt" placeholder="ubnt"></div>';
    html += '</div>';
    html += '<button class="btn btn-primary" onclick="addUniFiDeviceFromForm()" style="font-size:12px;padding:5px 14px;margin-top:8px;">+ ' + t('btn_add','Add') + '</button>';
    html += '</div>';

    html += '<div style="margin-top:12px;"><button class="btn btn-primary" onclick="saveUniFiDirect()" style="font-size:12px;padding:5px 14px;">' + t('lagre_alle_enheter') + '</button></div>';
    html += '</div>';

    html += '</div>';

    box.innerHTML = html;
    renderUniFiDeviceList();
  } catch (e) {
    box.innerHTML = '<span style="color:var(--text-muted);">' + t('status_error','Error') + ': ' + esc(e.message) + '</span>';
  }
}

function toggleUniFiMode() {
  var mode = document.querySelector('input[name="unifi-mode"]:checked').value;
  document.getElementById('unifi-controller-section').style.display = mode === 'controller' ? '' : 'none';
  document.getElementById('unifi-direct-section').style.display = mode === 'direct' ? '' : 'none';
}

function renderUniFiDeviceList() {
  var box = document.getElementById('unifi-device-list');
  if (!box) return;
  if (_unifiDirectDevices.length === 0) {
    box.innerHTML = emptyStateHTML({
      variant: 'inline',
      icon: '\u{1F4E1}',
      title: t('msg_no_devices_yet', 'Ingen enheter registrert ennå'),
      desc: t('empty_devices_desc', 'Skann nettet eller legg til en UniFi-enhet manuelt for å komme i gang.'),
    });
    return;
  }
  var html = '<div style="display:flex;flex-direction:column;gap:8px;">';
  for (var i = 0; i < _unifiDirectDevices.length; i++) {
    var dev = _unifiDirectDevices[i];
    var typeLabel = {ap:'Access Point', gateway:'Gateway/FW', switch:'Switch'}[dev.type || 'ap'] || dev.type;
    html += '<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);font-size:12px;">';
    html += '<span style="font-family:var(--mono);min-width:130px;">' + esc(dev.host || '') + '</span>';
    html += '<span style="color:var(--text-muted);min-width:100px;">' + esc(typeLabel) + '</span>';
    html += '<span style="color:var(--text-muted);">' + esc(dev.username || 'ubnt') + '</span>';
    html += '<span id="dev-status-' + i + '" style="margin-left:auto;font-size:11px;color:var(--text-dim);">' + (dev.status || '') + '</span>';
    html += '<button class="btn btn-ghost" onclick="testUniFiDevice(' + i + ')" style="font-size:11px;padding:2px 8px;">' + t('test') + '</button>';
    html += '<button class="btn btn-ghost" onclick="removeUniFiDevice(' + i + ')" style="font-size:11px;padding:2px 8px;color:var(--red);">' + t('btn_remove','Remove') + '</button>';
    html += '</div>';
  }
  html += '</div>';
  box.innerHTML = html;
}

function addUniFiDevice() {
  // Legacy — replaced by addUniFiDeviceFromForm
  addUniFiDeviceFromForm();
}

function addUniFiDeviceFromForm() {
  var host = (document.getElementById('input-uf-dev-host') || {}).value || '';
  if (!host.trim()) { showToast(t('msg_enter_ip'), 'warning'); return; }
  var type = (document.getElementById('input-uf-dev-type') || {}).value || 'ap';
  var user = (document.getElementById('input-uf-dev-user') || {}).value || 'ubnt';
  var pass = (document.getElementById('input-uf-dev-pass') || {}).value || 'ubnt';
  _unifiDirectDevices.push({host: host.trim(), type: type, username: user, password: pass});
  renderUniFiDeviceList();
  // Clear IP field for next entry
  var hostInput = document.getElementById('input-uf-dev-host');
  if (hostInput) { hostInput.value = ''; hostInput.focus(); }
}

function removeUniFiDevice(idx) {
  _unifiDirectDevices.splice(idx, 1);
  renderUniFiDeviceList();
}

async function testUniFiDevice(idx) {
  var dev = _unifiDirectDevices[idx];
  var el = document.getElementById('dev-status-' + idx);
  if (el) el.innerHTML = '<span style="color:var(--text-muted);">' + t('msg_testing','Testing...') + '</span>';
  try {
    var d = await apiFetch('/api/unifi/test-device', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({host: dev.host, username: dev.username, password: dev.password, device_type: dev.type})
    });

    if (d.ok) {
      var info = [d.model, d.firmware, d.hostname].filter(Boolean).join(' — ');
      var methods = [];
      if (d.http) methods.push('HTTP');
      if (d.ssh) methods.push('SSH');
      if (el) el.innerHTML = '<span style="color:var(--green);">OK (' + methods.join('+') + ')' + (info ? ' — ' + esc(info) : '') + '</span>';
      dev.status = 'OK';
    } else {
      if (el) el.innerHTML = '<span style="color:var(--red);">' + esc(d.error || t('status_error','Error')) + '</span>';
    }
  } catch (e) {
    if (el) el.innerHTML = '<span style="color:var(--red);">' + esc(e.message) + '</span>';
  }
}

async function runNetworkQuickAudit() {
  var btn = document.getElementById('btn-run-network-audit');
  var box = document.getElementById('net-audit-result');
  btn.disabled = true;
  btn.textContent = t('status_running','Running...');
  box.innerHTML = '<div style="text-align:center;padding:24px;"><div class="loader" style="width:24px;height:24px;margin:0 auto 12px;"></div>' + t('msg_loading_network_devices','Loading data from network devices...') + '</div>';

  try {
    var d = await apiFetch('/api/network/quick-audit', {method: 'POST'});
    if (d.error) { box.innerHTML = '<div class="alert alert-error">' + esc(d.error) + '</div>'; return; }

    var html = '';
    // A count that a refused sub-read left null is unknown, not zero. Show "–"
    // so the grid does not print the literal "null" as if it were a measurement.
    var numOrDash = function(v) { return (v === null || v === undefined) ? '–' : v; };

    // FortiGate results
    if (d.fortigate) {
      var fg = d.fortigate;
      if (fg.error) {
        html += '<div class="card" style="margin-bottom:16px;"><div class="card-title">FortiGate</div><div class="alert alert-error">' + esc(fg.error) + '</div></div>';
      } else {
        html += '<div class="card" style="margin-bottom:16px;">';
        html += '<div class="card-title">FortiGate — ' + esc(fg.hostname) + '</div>';
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-bottom:16px;">';
        html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + esc(fg.firmware) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('firmware') + '</div></div>';
        html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + numOrDash(fg.policy_count) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_firewall_rules','Firewall rules') + '</div></div>';
        html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + numOrDash(fg.admin_count) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_admin_accounts','Admin accounts') + '</div></div>';
        html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + numOrDash(fg.vpn_tunnels) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_vpn_tunnels','VPN tunnels') + '</div></div>';
        html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + numOrDash(fg.interface_count) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('interfaces') + '</div></div>';
        html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + esc(fg.ha_mode || '–') + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_ha_mode','HA mode') + '</div></div>';
        html += '</div>';

        // Admin table
        html += '<div style="font-weight:600;font-size:13px;margin-bottom:6px;">' + t('admin_kontoer') + '</div>';
        html += '<table class="section-table" style="width:100%;margin-bottom:12px;"><thead><tr><th>' + t('navn') + '</th><th>' + t('profil') + '</th><th>' + t('trusted_host') + '</th><th>' + t('fa') + '</th></tr></thead><tbody>';
        for (var a of fg.admins) {
          var thColor = a.trusthost ? 'var(--green)' : 'var(--red)';
          var tfaColor = a.two_factor ? 'var(--green)' : 'var(--red)';
          html += '<tr><td>' + esc(a.name) + '</td><td>' + esc(a.profile) + '</td>';
          html += '<td style="color:' + thColor + ';">' + (a.trusthost ? 'Ja' : t('lbl_no','No')) + '</td>';
          html += '<td style="color:' + tfaColor + ';">' + (a.two_factor ? 'Ja' : t('lbl_no','No')) + '</td></tr>';
        }
        html += '</tbody></table>';

        // Policy warnings
        if (fg.policy_warnings.length > 0) {
          html += '<div style="font-weight:600;font-size:13px;margin-bottom:6px;color:var(--red);">Advarsler (' + fg.policy_warnings.length + ')</div>';
          html += '<ul style="margin-left:16px;font-size:12px;color:var(--text-muted);">';
          for (var w of fg.policy_warnings) html += '<li>' + esc(w) + '</li>';
          html += '</ul>';
        } else {
          html += '<div style="font-size:12px;color:var(--green);">' + t('ingen_policy_advarsler_funnet') + '</div>';
        }
        html += '<div style="font-size:11px;color:var(--text-dim);margin-top:8px;">S/N: ' + esc(fg.serial) + ' | ' + t('lbl_model','Model') + ': ' + esc(fg.model) + ' | ' + t('lbl_uptime','Uptime') + ': ' + esc(fg.uptime) + '</div>';
        html += '</div>';
      }
    }

    // UniFi results
    if (d.unifi) {
      var uf = d.unifi;
      if (uf.error) {
        html += '<div class="card" style="margin-bottom:16px;"><div class="card-title">UniFi</div><div class="alert alert-error">' + esc(uf.error) + '</div></div>';
      } else {
        html += '<div class="card" style="margin-bottom:16px;">';
        html += '<div class="card-title">UniFi</div>';

        if (uf.mode === 'direct') {
          // Direct device mode — summary row
          html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:12px;margin-bottom:16px;">';
          html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + uf.device_count + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_devices_count','Devices') + '</div></div>';
          html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;color:' + (uf.reachable === uf.device_count ? 'var(--green)' : 'var(--orange)') + ';">' + uf.reachable + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_reachable','Reachable') + '</div></div>';
          if (uf.default_creds_count > 0) {
            html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;color:var(--red);">' + uf.default_creds_count + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_default_password','Default password') + '</div></div>';
          }
          if (uf.outdated_firmware_count > 0) {
            html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;color:var(--orange);">' + uf.outdated_firmware_count + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_outdated_firmware','Outdated firmware') + '</div></div>';
          }
          if (uf.eol_count > 0) {
            html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;color:var(--red);">' + uf.eol_count + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('end_of_life') + '</div></div>';
          }
          html += '</div>';

          // Per-device cards
          for (var idx = 0; idx < uf.devices.length; idx++) {
            var dev = uf.devices[idx];
            var borderColor = !dev.ok ? 'var(--red)' : (dev.default_credentials || dev.is_default_config ? 'var(--orange)' : 'var(--border)');
            html += '<div style="border:1px solid ' + borderColor + ';border-radius:8px;padding:14px;margin-bottom:12px;" id="unifi-dev-card-' + idx + '">';

            // Header row
            html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">';
            html += '<div>';
            html += '<span style="font-weight:600;font-size:14px;">' + esc(dev.hostname || dev.label || dev.host) + '</span>';
            if (dev.model) html += '<span style="color:var(--text-muted);font-size:12px;margin-left:8px;">' + esc(dev.model) + '</span>';
            html += '</div>';
            html += '<div style="display:flex;gap:6px;align-items:center;">';
            var typeLabels = {ap: 'Access Point', gateway: 'Gateway', switch: 'Switch'};
            html += '<span style="font-size:11px;padding:2px 8px;border-radius:10px;background:var(--bg);border:1px solid var(--border);">' + esc(typeLabels[dev.device_type] || dev.device_type) + '</span>';
            if (dev.ok) {
              html += '<span style="font-size:11px;color:var(--green);">' + t('online') + '</span>';
            } else {
              html += '<span style="font-size:11px;color:var(--red);">' + t('offline') + '</span>';
            }
            html += '</div></div>';

            if (!dev.ok && dev.error) {
              html += '<div class="alert alert-error" style="margin:0;">' + esc(dev.error) + '</div>';
            } else {
              // Info grid — identity
              html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;font-size:12px;">';
              var monoFields = new Set(['Firmware', 'MAC', 'IP', 'Serienummer']);
              var fields = [
                [t('lbl_model','Model'), dev.model],
                [t('lbl_firmware','Firmware'), dev.firmware],
                [t('lbl_serial','Serial'), dev.serial],
                ['MAC', dev.mac],
                ['IP', dev.ip || dev.host],
                ['Hostname', dev.hostname && dev.hostname !== (dev.label || dev.host) ? dev.hostname : null],
                ['Oppetid', dev.uptime],
                ['Klienter', dev.client_count != null ? String(dev.client_count) : null],
              ];
              // Wireless fields
              if (dev.ssid_list && dev.ssid_list.length > 1) {
                fields.push([t('lbl_ssids','SSID-er'), dev.ssid_list.join(', ')]);
              } else if (dev.essid) {
                fields.push(['SSID', dev.essid]);
              }
              if (dev.channel) fields.push(['Kanal', dev.channel]);
              if (dev.wifi_security) fields.push(['WiFi-sikkerhet', dev.wifi_security]);
              // Management
              if (dev.inform_url) fields.push(['Inform URL', dev.inform_url]);
              fields.push(['Tilkobling', (dev.http && dev.ssh) ? 'HTTP + SSH' : dev.ssh ? 'SSH' : dev.http ? 'HTTP' : null]);

              for (var f of fields) {
                if (f[1]) {
                  html += '<div style="background:var(--bg);border-radius:4px;padding:6px 8px;">';
                  html += '<div style="color:var(--text-muted);font-size:10px;margin-bottom:2px;">' + f[0] + '</div>';
                  html += '<div style="font-family:' + (monoFields.has(f[0]) ? 'var(--mono)' : 'inherit') + ';font-size:11px;word-break:break-all;">' + esc(f[1]) + '</div>';
                  html += '</div>';
                }
              }
              html += '</div>';

              // Security findings
              var findings = [];
              if (dev.default_credentials) findings.push({sev: 'critical', text: t('warn_default_password','Default password (ubnt/ubnt) in use — should be changed immediately')});
              if (dev.is_default_config) findings.push({sev: 'warning', text: t('warn_factory_default','Factory default — device not configured')});
              if (!dev.adopted && dev.adoption_status) findings.push({sev: dev.adoption_status === 'factory default' ? 'warning' : 'info', text: t('lbl_adoption_status','Adoption status') + ': ' + dev.adoption_status});
              if (dev.wifi_security && (dev.wifi_security === 'none' || dev.wifi_security === 'open')) findings.push({sev: 'critical', text: t('warn_open_wifi','Open wireless network — no encryption')});
              if (!dev.http && dev.ssh) findings.push({sev: 'info', text: t('warn_no_https','HTTPS interface not available')});
              // Firmware check
              if (dev.fw_check) {
                if (dev.fw_check.eol) findings.push({sev: 'critical', text: 'End-of-life — ' + esc(dev.fw_check.model) + ' ' + t('msg_no_longer_supported','is no longer supported by Ubiquiti')});
                else if (dev.fw_check.up_to_date === false) findings.push({sev: dev.fw_check.severity === 'critical' ? 'critical' : 'warning', text: t('warn_outdated_firmware','Outdated firmware: ') + esc(dev.fw_check.current) + ' → ' + t('msg_update_to','update to') + ' ' + esc(dev.fw_check.latest)});
                else if (dev.fw_check.up_to_date === true) findings.push({sev: 'ok', text: t('msg_firmware_updated','Firmware up to date') + ' (' + esc(dev.fw_check.latest) + ')'});
              }

              if (findings.length > 0) {
                html += '<div style="margin-top:10px;">';
                for (var fn of findings) {
                  var fc = fn.sev === 'critical' ? 'var(--red)' : fn.sev === 'warning' ? 'var(--orange)' : fn.sev === 'ok' ? 'var(--green)' : 'var(--text-muted)';
                  var icon = fn.sev === 'critical' ? '!' : fn.sev === 'warning' ? '!' : fn.sev === 'ok' ? '\u2713' : 'i';
                  html += '<div style="display:flex;gap:6px;align-items:flex-start;padding:5px 8px;border-radius:4px;background:var(--bg);margin-bottom:4px;font-size:12px;">';
                  html += '<span style="color:' + fc + ';flex-shrink:0;">' + icon + '</span>';
                  html += '<span style="color:' + (fn.sev === 'info' ? 'var(--text-muted)' : fc) + ';">' + esc(fn.text) + '</span>';
                  html += '</div>';
                }
                html += '</div>';
              }

              // Action buttons
              html += '<div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;">';
              // Set-inform
              html += '<button class="btn btn-default" style="font-size:11px;padding:4px 10px;" onclick="unifiDeviceSetInform(\'' + esc(dev.host) + '\')">' + t('set_inform') + '</button>';
              // View config
              html += '<button class="btn btn-default" style="font-size:11px;padding:4px 10px;" onclick="unifiDeviceConfig(\'' + esc(dev.host) + '\')">' + t('btn_view_config','View config') + '</button>';
              // Reboot
              html += '<button class="btn btn-default" style="font-size:11px;padding:4px 10px;color:var(--orange);" onclick="unifiDeviceReboot(\'' + esc(dev.host) + '\')">' + t('btn_restart','Restart') + '</button>';
              html += '</div>';
              html += '<div id="unifi-action-' + idx + '" style="margin-top:8px;"></div>';
            }
            html += '</div>';
          }
        } else {
          // Controller mode
          html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:12px;margin-bottom:16px;">';
          html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + numOrDash(uf.device_count) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_devices_count','Devices') + '</div></div>';
          html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + numOrDash(uf.wlan_count) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_ssids','SSIDs') + '</div></div>';
          html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + numOrDash(uf.network_count) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_networks','Networks') + '</div></div>';
          html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + numOrDash(uf.firewall_rules) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_firewall_rules','Firewall rules') + '</div></div>';
          html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;color:' + (uf.active_alarms == null ? 'var(--text-muted)' : (uf.active_alarms > 0 ? 'var(--red)' : 'var(--green)')) + ';">' + numOrDash(uf.active_alarms) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_active_alarms','Active alarms') + '</div></div>';
          html += '</div>';

          // Device table
          html += '<div style="font-weight:600;font-size:13px;margin-bottom:6px;">' + t('lbl_devices_count','Devices') + '</div>';
          html += '<table class="section-table" style="width:100%;margin-bottom:12px;"><thead><tr><th>' + t('lbl_name','Name') + '</th><th>' + t('lbl_type','Type') + '</th><th>' + t('lbl_model','Model') + '</th><th>' + t('firmware') + '</th><th>' + t('lbl_upgrade','Upgrade') + '</th><th>' + t('lbl_clients','Clients') + '</th><th>' + t('status') + '</th></tr></thead><tbody>';
          for (var dev of uf.devices) {
            var statusColor = dev.status === 'online' ? 'var(--green)' : 'var(--red)';
            var upgradeHtml = dev.upgrade ? '<span style="color:var(--orange);">' + esc(dev.upgrade) + '</span>' : '<span style="color:var(--green);">OK</span>';
            html += '<tr><td>' + esc(dev.name) + '</td><td>' + esc(dev.type) + '</td><td>' + esc(dev.model) + '</td>';
            html += '<td style="font-family:var(--mono);font-size:11px;">' + esc(dev.firmware) + '</td>';
            html += '<td>' + upgradeHtml + '</td>';
            html += '<td>' + dev.clients + '</td>';
            html += '<td style="color:' + statusColor + ';">' + esc(dev.status) + '</td></tr>';
          }
          html += '</tbody></table>';

          // WLAN table
          if (uf.wlans && uf.wlans.length > 0) {
            html += '<div style="font-weight:600;font-size:13px;margin-bottom:6px;">' + t('lbl_wireless_networks','Wireless networks') + '</div>';
            html += '<table class="section-table" style="width:100%;"><thead><tr><th>SSID</th><th>' + t('lbl_security','Security') + '</th><th>' + t('lbl_guest','Guest') + '</th><th>' + t('lbl_active','Active') + '</th></tr></thead><tbody>';
            for (var w of uf.wlans) {
              var secColor = w.security === 'open' ? 'var(--red)' : 'var(--green)';
              html += '<tr><td>' + esc(w.name) + '</td>';
              html += '<td style="color:' + secColor + ';">' + esc(w.security) + '</td>';
              html += '<td>' + (w.guest ? t('lbl_yes','Yes') : t('lbl_no','No')) + '</td>';
              html += '<td>' + (w.enabled ? t('lbl_yes','Yes') : '<span style="color:var(--text-dim);">' + t('lbl_no','No') + '</span>') + '</td></tr>';
            }
            html += '</tbody></table>';
          }
        }
        html += '</div>';
      }
    }

    if (!html) html = '<div class="alert alert-error">' + t('msg_no_data_returned','No data returned') + '</div>';
    box.innerHTML = html;
  } catch (e) {
    box.innerHTML = '<div class="alert alert-error">' + t('status_error','Error') + ': ' + esc(e.message) + '</div>';
  } finally {
    btn.disabled = false;
    btn.textContent = t('btn_run_quick_check','Run quick check');
  }
}

async function saveUniFiDirect() {
  try {
    var d = await apiFetch('/api/unifi/save', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      // Only the fields this form owns. The route leaves everything else
      // alone; it used to reset each unmentioned field to its default, so
      // saving the device list blanked the customer's controller address.
      body: JSON.stringify({mode: 'direct', devices: _unifiDirectDevices})
    });
    if (!d) return;

    if (d.ok) showToast(t('msg_saved_devices').replace('{count}', _unifiDirectDevices.length), 'success');
    else showToast(t('status_error') + ': ' + (d.error || t('err_unknown')), 'error');
  } catch (e) {
    showToast(t('status_error') + ': ' + e.message, 'error');
  }
}

// ── UniFi direct device actions ──

function _getDeviceCredentials(host) {
  // Find the matching device in _unifiDirectDevices for its credentials
  var dev = _unifiDirectDevices.find(function(d) { return d.host === host; });
  return {
    host: host,
    username: (dev && dev.username) || 'ubnt',
    password: (dev && dev.password) || 'ubnt',
  };
}

async function unifiDeviceSetInform(host) {
  var url = prompt('Controller inform-URL (f.eks. http://192.168.1.1:8080/inform):');
  if (!url) return;
  var creds = _getDeviceCredentials(host);
  try {
    var d = await apiFetch('/api/unifi/set-inform', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({...creds, controller_url: url})
    });
    // apiFetch returns null on any HTTP error and has already told the user
    // why. Reading .ok off it throws a TypeError, which the catch below then
    // reports as a second, meaningless toast on top of the real one.
    if (!d) return;

    if (d.ok) {
      showToast(t('msg_inform_sent').replace('{host}', host) + ' — ' + (d.output || 'OK'), 'success', 8000);
    } else {
      showToast(t('status_error') + ': ' + (d.error || t('err_unknown')), 'error');
    }
  } catch (e) { showToast(t('status_error') + ': ' + e.message, 'error'); }
}

async function unifiDeviceReboot(host) {
  if (!await showConfirm(t('dlg_confirm_restart_device').replace('{host}', host))) return;
  var creds = _getDeviceCredentials(host);
  try {
    var d = await apiFetch('/api/unifi/reboot-device', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(creds)
    });
    if (!d) return;

    if (d.ok) showToast(d.output || t('msg_device_rebooting'), 'success');
    else showToast(t('status_error') + ': ' + (d.error || t('err_unknown')), 'error');
  } catch (e) { showToast(t('status_error') + ': ' + e.message, 'error'); }
}

async function unifiDeviceConfig(host) {
  var creds = _getDeviceCredentials(host);
  // Find the card to insert the config into
  var cards = document.querySelectorAll('[id^="unifi-action-"]');
  var targetEl = null;
  for (var card of cards) {
    if (card.closest('[id^="unifi-dev-card-"]')) {
      // Check if this card matches the host
      var parentCard = card.closest('[id^="unifi-dev-card-"]');
      if (parentCard && parentCard.textContent.includes(host)) {
        targetEl = card;
        break;
      }
    }
  }
  if (!targetEl) { targetEl = document.getElementById('unifi-action-0'); }
  if (targetEl) targetEl.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:12px;">' + t('msg_loading_config','Loading configuration...') + '</div>';

  try {
    var d = await apiFetch('/api/unifi/device-config', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(creds)
    });
    if (!d) {
      // apiFetch already reported the failure; clear the "Loading…" placeholder
      // so the card does not sit spinning forever.
      if (targetEl) targetEl.innerHTML = '';
      return;
    }

    if (d.ok && d.config) {
      // Auto-save backup
      apiFetch('/api/network/save-config-backup', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({host: host, config: d.config})
      }).catch(function() {});
      if (targetEl) {
        targetEl.innerHTML = '<div style="margin-top:4px;"><div style="display:flex;align-items:center;justify-content:space-between;"><div style="font-weight:600;font-size:12px;">' + t('lbl_running_config','Running configuration') + '</div><span style="font-size:10px;color:var(--green);">' + t('msg_backup_saved','Backup saved') + '</span></div>'
          + '<pre style="max-height:300px;overflow:auto;padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;font-size:11px;white-space:pre-wrap;word-break:break-all;">'
          + esc(d.config) + '</pre>'
          + '<button class="btn btn-default" style="font-size:11px;padding:3px 8px;margin-top:6px;" onclick="this.parentElement.parentElement.innerHTML=\'\'">' + t('btn_close','Close') + '</button></div>';
      } else {
        showToast(d.config.substring(0, 2000), 'info', 10000);
      }
    } else {
      var msg = t('status_error') + ': ' + (d.error || t('msg_no_config'));
      if (targetEl) targetEl.innerHTML = '<div class="alert alert-error" style="font-size:12px;">' + esc(msg) + '</div>';
      else showToast(msg, 'error');
    }
  } catch (e) {
    var msg = t('status_error') + ': ' + e.message;
    if (targetEl) targetEl.innerHTML = '<div class="alert alert-error" style="font-size:12px;">' + esc(msg) + '</div>';
    else showToast(msg, 'error');
  }
}

// ── Subnet scanner ──

async function runSubnetScan() {
  var btn = document.getElementById('btn-subnet-scan');
  var box = document.getElementById('subnet-scan-result');
  var subnet = document.getElementById('input-scan-subnet').value.trim();
  if (!subnet) { showToast(t('msg_enter_subnet'), 'warning'); return; }
  btn.disabled = true;
  btn.textContent = t('msg_scanning','Scanning...');
  box.innerHTML = '<div style="text-align:center;padding:16px;"><div class="loader" style="width:20px;height:20px;margin:0 auto 8px;"></div>' + t('msg_scanning','Scanning...').replace('...','') + ' ' + esc(subnet) + '...</div>';

  try {
    var d = await apiFetch('/api/network/scan', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({subnet: subnet})
    });
    if (!d) { box.innerHTML = ''; return; }

    if (d.error) { box.innerHTML = '<div class="alert alert-error">' + esc(d.error) + '</div>'; return; }

    // A scan that returned nothing at all is not the same as a scan that found
    // no devices; treat a missing list as an empty one rather than throwing.
    if (!d.found || d.found.length === 0) {
      box.innerHTML = '<div style="padding:12px;color:var(--text-muted);font-size:13px;">' + t('msg_no_devices_found','No devices found in') + ' ' + esc(subnet) + '</div>';
      return;
    }

    var html = '<div style="font-size:13px;margin-bottom:8px;"><strong>' + d.found.length + '</strong> ' + t('msg_devices_found_in','devices found in') + ' ' + esc(subnet) + '</div>';
    html += '<table class="section-table" style="width:100%;"><thead><tr><th>IP</th><th>SSH</th><th>HTTPS</th><th>UniFi</th><th>' + t('info') + '</th><th>' + t('btn_actions','Actions') + '</th></tr></thead><tbody>';
    for (var dev of d.found) {
      var isUf = dev.is_unifi ? '<span style="color:var(--green);">' + t('lbl_yes','Yes') + '</span>' : '<span style="color:var(--text-muted);">' + t('lbl_no','No') + '</span>';
      var hostSafe = esc(dev.host);
      var hostId = hostSafe.replace(/\./g,'_');
      html += '<tr>';
      html += '<td style="font-family:var(--mono);font-size:12px;">' + hostSafe + '</td>';
      html += '<td>' + (dev.ssh ? '<span style="color:var(--green);">&#10003;</span>' : '–') + '</td>';
      html += '<td>' + (dev.https ? '<span style="color:var(--green);">&#10003;</span>' : '–') + '</td>';
      html += '<td>' + isUf + '</td>';
      html += '<td style="font-size:11px;color:var(--text-muted);">' + esc(dev.device_hint || dev.ssh_banner || '') + '</td>';
      html += '<td style="white-space:nowrap;">';
      var alreadyAdded = _unifiDirectDevices.some(function(d2) { return d2.host === dev.host; });
      if (alreadyAdded) {
        html += '<button class="btn btn-default" style="font-size:10px;padding:2px 8px;color:var(--green);" disabled>' + t('status_added','Added') + '</button> ';
      } else {
        html += '<button class="btn btn-default" style="font-size:10px;padding:2px 8px;" id="scan-add-' + hostId + '" onclick="addScannedDevice(\'' + hostSafe + '\',this)">' + t('btn_add','Add') + '</button> ';
      }
      if (dev.ssh) {
        html += '<button class="btn btn-default" style="font-size:10px;padding:2px 8px;" onclick="scanDeviceSetInform(\'' + hostSafe + '\')">' + t('set_inform') + '</button> ';
        html += '<button class="btn btn-default" style="font-size:10px;padding:2px 8px;" onclick="scanDeviceConfig(\'' + hostSafe + '\',\'scan-cfg-' + hostId + '\')">' + t('btn_view_config','Vis konfig') + '</button> ';
        html += '<button class="btn btn-default" style="font-size:10px;padding:2px 8px;" onclick="scanDeviceReboot(\'' + hostSafe + '\')">' + t('btn_restart','Restart') + '</button>';
      }
      html += '</td>';
      html += '</tr>';
      if (dev.ssh) {
        html += '<tr id="scan-cfg-' + hostId + '" style="display:none;"><td colspan="6"></td></tr>';
      }
    }
    html += '</tbody></table>';
    box.innerHTML = html;
  } catch (e) {
    box.innerHTML = '<div class="alert alert-error">' + esc(e.message) + '</div>';
  } finally {
    btn.disabled = false;
    btn.textContent = t('btn_scan','Scan');
  }
}

async function addScannedDevice(host, btnEl) {
  if (_unifiDirectDevices.some(function(d) { return d.host === host; })) {
    if (btnEl) { btnEl.textContent = t('msg_already_exists','Exists'); btnEl.disabled = true; }
    return;
  }
  _unifiDirectDevices.push({host: host, username: 'ubnt', password: 'ubnt', device_type: 'ap', label: host});
  if (btnEl) { btnEl.textContent = t('btn_saving','Saving...'); btnEl.disabled = true; }

  try {
    var d = await apiFetch('/api/unifi/save', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mode: 'direct', devices: _unifiDirectDevices})
    });

    if (d.ok) {
      if (btnEl) { btnEl.textContent = t('status_added','Added'); btnEl.style.color = 'var(--green)'; }
      if (typeof loadNetworkDevices === 'function') loadNetworkDevices();
    } else {
      if (btnEl) { btnEl.textContent = t('status_error','Error'); btnEl.style.color = 'var(--red)'; }
    }
  } catch (e) {
    if (btnEl) { btnEl.textContent = t('status_error','Error'); btnEl.style.color = 'var(--red)'; }
  }
}

// ── Scan result device actions ──

function _scanDeviceCreds(host) {
  var dev = _unifiDirectDevices.find(function(d) { return d.host === host; });
  return { host: host, username: (dev && dev.username) || 'ubnt', password: (dev && dev.password) || 'ubnt' };
}

async function scanDeviceSetInform(host) {
  var presets = [
    { label: 'unifi.sybr.no', url: 'http://unifi.sybr.no:8080/inform' }
  ];
  // Use the confirm modal infrastructure to show preset + custom URL picker
  document.getElementById('confirm-modal-title').textContent = t('hdr_set_inform','Set-Inform') + ' \u2014 ' + host;
  var bodyEl = document.getElementById('confirm-modal-body');
  var pickHtml = '<div style="display:flex;flex-direction:column;gap:8px;margin-bottom:12px;">';
  for (var p of presets) {
    pickHtml += '<button class="btn btn-primary" style="font-size:12px;padding:8px 14px;" onclick="doScanSetInform(\'' + esc(host) + '\',\'' + esc(p.url) + '\')">' + esc(p.label) + ' <span style="font-size:10px;opacity:0.7;margin-left:4px;">' + esc(p.url) + '</span></button>';
  }
  pickHtml += '</div>';
  pickHtml += '<div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">' + t('eller_angi_manuelt') + '</div>';
  pickHtml += '<div style="display:flex;gap:6px;align-items:center;">';
  pickHtml += '<input class="field-input" id="scan-inform-custom-url" type="text" placeholder="http://controller:8080/inform" style="flex:1;margin:0;">';
  pickHtml += '<button class="btn btn-default" style="font-size:12px;padding:6px 12px;white-space:nowrap;" onclick="doScanSetInform(\'' + esc(host) + '\',document.getElementById(\'scan-inform-custom-url\').value.trim())">' + t('btn_send','Send') + '</button>';
  pickHtml += '</div>';
  bodyEl.innerHTML = pickHtml;
  var modal = document.getElementById('confirm-modal');
  modal.style.display = 'flex';
  // Hide default OK/Cancel — our inline buttons handle it; clicking backdrop closes
  modal.querySelector('.modal-actions').style.display = 'none';
}

async function doScanSetInform(host, url) {
  if (!url) { showToast(t('msg_enter_url','Enter a URL'), 'warning'); return; }
  var modal = document.getElementById('confirm-modal');
  modal.style.display = 'none';
  modal.querySelector('.modal-actions').style.display = '';
  var creds = _scanDeviceCreds(host);
  try {
    var d = await apiFetch('/api/unifi/set-inform', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({...creds, controller_url: url})
    });
    if (!d) return;
    if (d.ok) {
      showToast(t('msg_inform_sent').replace('{host}', host) + ' — ' + (d.output || 'OK'), 'success', 8000);
    } else {
      showToast(t('status_error') + ': ' + (d.error || t('err_unknown')), 'error');
    }
  } catch (e) { showToast(t('status_error') + ': ' + e.message, 'error'); }
}

async function scanDeviceConfig(host, rowId) {
  var row = document.getElementById(rowId);
  if (!row) return;
  var cell = row.querySelector('td');
  row.style.display = '';
  cell.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:12px;">' + t('msg_loading_config','Loading configuration...') + '</div>';
  var creds = _scanDeviceCreds(host);
  try {
    var d = await apiFetch('/api/unifi/device-config', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(creds)
    });
    if (!d) { row.style.display = 'none'; cell.innerHTML = ''; return; }
    if (d.ok && d.config) {
      apiFetch('/api/network/save-config-backup', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({host: host, config: d.config})
      }).catch(function() {});
      cell.innerHTML = '<div style="padding:6px;"><div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">'
        + '<span style="font-weight:600;font-size:12px;">' + t('lbl_running_config','Running configuration') + ' — ' + esc(host) + '</span>'
        + '<span style="font-size:10px;color:var(--green);">' + t('msg_backup_saved','Backup saved') + '</span></div>'
        + '<pre style="max-height:300px;overflow:auto;padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;font-size:11px;white-space:pre-wrap;word-break:break-all;">' + esc(d.config) + '</pre>'
        + '<button class="btn btn-default" style="font-size:11px;padding:3px 8px;margin-top:6px;" onclick="var r=document.getElementById(\'' + rowId + '\');r.style.display=\'none\';r.querySelector(\'td\').innerHTML=\'\';">' + t('btn_close','Close') + '</button></div>';
    } else {
      cell.innerHTML = '<div class="alert alert-error" style="font-size:12px;">' + esc(d.error || t('msg_no_config','No config')) + '</div>';
    }
  } catch (e) {
    cell.innerHTML = '<div class="alert alert-error" style="font-size:12px;">' + esc(e.message) + '</div>';
  }
}

async function scanDeviceReboot(host) {
  if (!await showConfirm(t('dlg_confirm_restart_device','Restart {host}?').replace('{host}', host))) return;
  var creds = _scanDeviceCreds(host);
  try {
    var d = await apiFetch('/api/unifi/reboot-device', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(creds)
    });
    if (!d) return;
    if (d.ok) showToast(d.output || t('msg_device_rebooting'), 'success');
    else showToast(t('status_error') + ': ' + (d.error || t('err_unknown')), 'error');
  } catch (e) { showToast(t('status_error') + ': ' + e.message, 'error'); }
}

// ── Config backup viewer ──

async function loadConfigBackups() {
  var box = document.getElementById('config-backups-list');
  box.innerHTML = '<div style="color:var(--text-muted);font-size:12px;">' + t('msg_loading','Loading...') + '</div>';
  try {
    var d = await apiFetch('/api/network/config-backups');
    if (!d.backups || d.backups.length === 0) {
      box.innerHTML = emptyStateHTML({
        variant: 'inline',
        icon: '\u{1F4BE}',
        title: t('msg_no_backups_yet_title', 'Ingen config-backups lagret ennå'),
        desc: t('empty_backups_desc', 'Åpne en enhet og bruk «Vis konfig» — backupen tas automatisk ved første visning.'),
      });
      return;
    }
    var html = '<table class="section-table" style="width:100%;"><thead><tr><th>' + t('lbl_timestamp','Timestamp') + '</th><th>' + t('lbl_device','Device') + '</th><th>' + t('lbl_size','Size') + '</th></tr></thead><tbody>';
    for (var b of d.backups) {
      html += '<tr>';
      html += '<td style="font-size:12px;">' + esc(b.timestamp) + '</td>';
      html += '<td style="font-family:var(--mono);font-size:12px;">' + esc(b.host) + '</td>';
      html += '<td style="font-size:12px;">' + Math.round(b.size / 1024) + ' KB</td>';
      html += '</tr>';
    }
    html += '</tbody></table>';
    box.innerHTML = html;
  } catch (e) {
    box.innerHTML = '<div class="alert alert-error">' + esc(e.message) + '</div>';
  }
}

function toggleNetworkConfig(id) {
  var el = document.getElementById(id);
  if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

async function testFortiGate() {
  var res = document.getElementById('fg-test-result');
  res.textContent = t('msg_testing','Testing...');
  res.style.color = 'var(--text-muted)';
  try {
    var d = await apiFetch('/api/fortigate/test', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        host: document.getElementById('input-fg-host').value,
        port: parseInt(document.getElementById('input-fg-port').value) || 443,
        api_token: document.getElementById('input-fg-token').value,
        vdom: document.getElementById('input-fg-vdom').value || 'root',
        verify_ssl: document.getElementById('input-fg-verify-ssl').checked,
      })
    });
    if (d && d.ok) {
      res.innerHTML = '<span style="color:var(--green);">OK — ' + esc(d.hostname) + ' (FW: ' + esc(d.firmware) + ', S/N: ' + esc(d.serial) + ')</span>';
    } else {
      res.innerHTML = '<span style="color:var(--red);">' + t('status_error','Error') + ': ' + esc(d && d.error ? d.error : t('err_connection_failed','Connection failed')) + '</span>';
    }
  } catch (e) {
    res.innerHTML = '<span style="color:var(--red);">' + esc(e.message) + '</span>';
  }
}

async function saveFortiGate() {
  var res = document.getElementById('fg-test-result');
  try {
    var d = await apiFetch('/api/fortigate/save', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        host: document.getElementById('input-fg-host').value,
        port: parseInt(document.getElementById('input-fg-port').value) || 443,
        api_token: document.getElementById('input-fg-token').value,
        vdom: document.getElementById('input-fg-vdom').value || 'root',
        verify_ssl: document.getElementById('input-fg-verify-ssl').checked,
      })
    });
    if (d && d.ok) {
      res.innerHTML = '<span style="color:var(--green);">' + t('msg_saved','Saved') + '</span>';
      loadNetworkDevices();
    } else {
      res.innerHTML = '<span style="color:var(--red);">' + esc(d && d.error ? d.error : t('err_save_failed','Save failed')) + '</span>';
    }
  } catch (e) {
    res.innerHTML = '<span style="color:var(--red);">' + esc(e.message) + '</span>';
  }
}

async function testUniFi() {
  var res = document.getElementById('uf-test-result');
  res.textContent = t('msg_testing','Testing...');
  res.style.color = 'var(--text-muted)';
  try {
    var d = await apiFetch('/api/unifi/test', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        host: document.getElementById('input-uf-host').value,
        username: document.getElementById('input-uf-user').value,
        password: document.getElementById('input-uf-pass').value,
        is_unifi_os: document.getElementById('input-uf-os').checked,
      })
    });

    if (d.ok) {
      res.innerHTML = '<span style="color:var(--green);">OK — ' + d.sites + ' site(s) (' + esc(d.controller_type) + '): ' + esc((d.site_names||[]).join(', ')) + '</span>';
    } else {
      res.innerHTML = '<span style="color:var(--red);">' + t('lbl_error','Feil') + ': ' + esc(d.error) + '</span>';
    }
  } catch (e) {
    res.innerHTML = '<span style="color:var(--red);">' + esc(e.message) + '</span>';
  }
}

async function saveUniFi() {
  var res = document.getElementById('uf-test-result');
  try {
    var d = await apiFetch('/api/unifi/save', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        host: document.getElementById('input-uf-host').value,
        username: document.getElementById('input-uf-user').value,
        password: document.getElementById('input-uf-pass').value,
        site: document.getElementById('input-uf-site').value || 'default',
        is_unifi_os: document.getElementById('input-uf-os').checked,
      })
    });
    if (d.ok) {
      res.innerHTML = '<span style="color:var(--green);">' + t('lagret') + '</span>';
      loadNetworkDevices();
    } else {
      res.innerHTML = '<span style="color:var(--red);">' + esc(d.error) + '</span>';
    }
  } catch (e) {
    res.innerHTML = '<span style="color:var(--red);">' + esc(e.message) + '</span>';
  }
}

async function openReportsFolder() {
  try {
    // Get the customer's audit folder path from the files API
    const d = await apiFetch('/api/files');
    const path = d && d.raw_data && d.raw_data.path ? d.raw_data.path : null;
    await apiFetch('/api/open-folder', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(path ? {path: path} : {})
    });
  } catch {}
}

async function testITGlue() {
  const result = document.getElementById('itglue-test-result');
  const key = document.getElementById('input-itglue-key').value;
  const region = document.getElementById('input-itglue-region').value;
  result.textContent = t('msg_testing');
  try {
    const d = await apiFetch('/api/itglue/test', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({api_key: key, region: region})
    });
    if (d && d.ok) {
      result.innerHTML = `<span style="color:var(--green);">✓ Tilkoblet (${d.organizations} organisasjoner)</span>`;
    } else {
      result.innerHTML = `<span style="color:var(--red);">✗ ${d ? esc(d.error) : t('status_error','Error')}</span>`;
    }
  } catch(e) {
    result.innerHTML = `<span style="color:var(--red);">✗ ${esc(e.message)}</span>`;
  }
}

let _itglueOrgCache = null;

// ── IT Glue org picker (reusable) ───────────────────────────────────────────
var _itgluePickerCallback = null;

async function openITGlueOrgPicker(callback, autoMatchName) {
  _itgluePickerCallback = callback;
  var modal = document.getElementById('itglue-org-picker-modal');
  var content = document.getElementById('itglue-org-picker-content');
  var btn = document.getElementById('btn-itglue-org-pick');
  modal.style.display = 'flex';
  btn.disabled = true;
  btn.textContent = t('btn_select');
  content.innerHTML = '<div style="text-align:center;padding:24px;"><div class="loader" style="width:24px;height:24px;margin:0 auto 12px;"></div>' + t('msg_fetching_orgs') + '</div>';

  try {
    if (!_itglueOrgCache) {
      var d = await apiFetch('/api/itglue/organizations', {method: 'POST'});
      if (d.error) { content.innerHTML = '<div class="alert alert-error">' + esc(d.error) + '</div>'; return; }
      _itglueOrgCache = d.organizations || [];
    }
    if (_itglueOrgCache.length === 0) {
      content.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-muted);">' + t('msg_no_orgs_found') + '</div>';
      return;
    }

    var orgs = _itglueOrgCache.slice().sort(function(a,b){ return a.name.localeCompare(b.name); });

    // Auto-match: find best match for current customer name
    var bestIdx = -1;
    if (autoMatchName) {
      var lower = autoMatchName.toLowerCase();
      // Exact match first
      for (var i = 0; i < orgs.length; i++) {
        if (orgs[i].name.toLowerCase() === lower) { bestIdx = i; break; }
      }
      // Partial match
      if (bestIdx < 0) {
        for (var i = 0; i < orgs.length; i++) {
          if (orgs[i].name.toLowerCase().indexOf(lower) >= 0 || lower.indexOf(orgs[i].name.toLowerCase()) >= 0) { bestIdx = i; break; }
        }
      }
    }

    var html = '<input type="text" id="itglue-org-picker-search" class="field-input" placeholder="' + t('lbl_search') + '" style="margin-bottom:10px;padding:6px 12px;font-size:12px;" oninput="filterITGlueOrgPicker()">';
    html += '<div style="max-height:300px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;">';
    for (var i = 0; i < orgs.length; i++) {
      var matched = (i === bestIdx);
      html += '<label class="itglue-org-picker-row" data-name="' + esc(orgs[i].name.toLowerCase()) + '" style="display:flex;align-items:center;gap:8px;padding:8px 12px;cursor:pointer;border-bottom:1px solid var(--border);' + (matched ? 'background:rgba(77,159,181,0.1);' : '') + '">';
      html += '<input type="radio" name="itglue-org-pick" value="' + esc(orgs[i].id) + '" data-orgname="' + esc(orgs[i].name) + '" ' + (matched ? 'checked' : '') + ' onchange="document.getElementById(\'btn-itglue-org-pick\').disabled=false;" style="width:16px;height:16px;">';
      html += '<span style="font-size:13px;">' + esc(orgs[i].name) + '</span>';
      if (matched) html += '<span style="margin-left:auto;font-size:10px;color:var(--green);font-weight:600;">' + t('msg_recommended_match') + '</span>';
      html += '</label>';
    }
    html += '</div>';
    content.innerHTML = html;
    if (bestIdx >= 0) btn.disabled = false;

    // Scroll to match
    setTimeout(function() {
      var checked = content.querySelector('input[name="itglue-org-pick"]:checked');
      if (checked) checked.closest('label').scrollIntoView({block:'center'});
    }, 100);
  } catch (e) {
    content.innerHTML = '<div class="alert alert-error">' + t('status_error') + ': ' + esc(e.message) + '</div>';
  }
}

function filterITGlueOrgPicker() {
  var q = (document.getElementById('itglue-org-picker-search') || {}).value.toLowerCase();
  document.querySelectorAll('.itglue-org-picker-row').forEach(function(row) {
    row.style.display = row.dataset.name.indexOf(q) >= 0 ? '' : 'none';
  });
}

function confirmITGlueOrgPick() {
  var selected = document.querySelector('input[name="itglue-org-pick"]:checked');
  if (!selected || !_itgluePickerCallback) return;
  document.getElementById('itglue-org-picker-modal').style.display = 'none';
  _itgluePickerCallback({id: selected.value, name: selected.dataset.orgname});
  _itgluePickerCallback = null;
}

var _itglueUploadBtn = null;

async function uploadReportsToITGlue(btn) {
  _itglueUploadBtn = btn;
  // Check IT Glue config
  try {
    var settings = await apiFetch('/api/settings');
    if (!settings.itglue_api_key_set) {
      if (await showConfirm(t('dlg_confirm_itglue_setup'))) {
        showView('integrations');
        setTimeout(function(){ toggleIntegConfig('itglue-config'); }, 300);
      }
      return;
    }
  } catch { showToast(t('err_check_settings_failed'), 'error'); return; }

  // Show the upload modal with file picker + org picker
  var modal = document.getElementById('itglue-upload-modal');
  var content = document.getElementById('itglue-upload-content');
  modal.style.display = 'flex';
  document.getElementById('btn-itglue-upload-go').disabled = true;
  content.innerHTML = '<div style="text-align:center;padding:24px;"><div class="loader" style="width:24px;height:24px;margin:0 auto 12px;"></div>' + t('msg_fetching_reports_orgs') + '</div>';

  try {
    // Fetch available reports and orgs in parallel
    var [reportsResp, orgsResp, filesResp] = await Promise.all([
      apiFetch('/api/itglue/available-reports'),
      _itglueOrgCache ? Promise.resolve({organizations: _itglueOrgCache}) : apiFetch('/api/itglue/organizations', {method:'POST'}),
      apiFetch('/api/files')
    ]);

    var files = reportsResp.files || [];
    if (files.length === 0) {
      content.innerHTML = '<div class="alert alert-error">' + t('msg_no_reports_available') + '</div>';
      return;
    }

    var orgs = orgsResp.organizations || [];
    if (!_itglueOrgCache && orgs.length > 0) _itglueOrgCache = orgs;
    if (orgs.length === 0) {
      content.innerHTML = '<div class="alert alert-error">' + t('msg_no_orgs_found_itglue') + '</div>';
      return;
    }
    orgs.sort(function(a,b){ return a.name.localeCompare(b.name); });

    // Auto-match customer name
    var customerName = (filesResp.credentials && filesResp.credentials.customer_name) || '';
    var bestOrgIdx = -1;
    if (customerName) {
      var lower = customerName.toLowerCase();
      for (var i = 0; i < orgs.length; i++) {
        if (orgs[i].name.toLowerCase() === lower) { bestOrgIdx = i; break; }
      }
      if (bestOrgIdx < 0) {
        for (var i = 0; i < orgs.length; i++) {
          if (orgs[i].name.toLowerCase().indexOf(lower) >= 0 || lower.indexOf(orgs[i].name.toLowerCase()) >= 0) { bestOrgIdx = i; break; }
        }
      }
    }

    // Build UI
    var html = '';

    // Step 1: File picker
    html += '<div style="font-weight:600;font-size:13px;margin-bottom:8px;">' + t('hdr_select_reports') + '</div>';
    html += '<div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;">';
    html += '<label style="font-size:12px;cursor:pointer;"><input type="checkbox" id="itglue-upload-select-all" onchange="document.querySelectorAll(\'.itglue-file-cb\').forEach(function(c){c.checked=this.checked}.bind(this));updateITGlueUploadBtn();" checked> ' + t('btn_select_all') + '</label>';
    html += '</div>';
    html += '<div style="max-height:180px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;margin-bottom:16px;">';
    for (var i = 0; i < files.length; i++) {
      var f = files[i];
      var ficon = f.name.endsWith('.pdf') ? icon('document',14) : icon('globe',14);
      html += '<label style="display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer;border-bottom:1px solid var(--border);font-size:12px;">';
      html += '<input type="checkbox" class="itglue-file-cb" value="' + esc(f.name) + '" checked onchange="updateITGlueUploadBtn()" style="width:15px;height:15px;">';
      html += ficon + ' <span style="flex:1;">' + esc(f.name) + '</span>';
      html += '<span style="color:var(--text-muted);">' + esc(f.size) + '</span>';
      html += '</label>';
    }
    html += '</div>';

    // Step 2: Org picker
    html += '<div style="font-weight:600;font-size:13px;margin-bottom:8px;">' + t('hdr_select_org') + '</div>';
    html += '<input type="text" id="itglue-upload-org-search" class="field-input" placeholder="' + t('lbl_search_org') + '" style="margin-bottom:6px;padding:6px 12px;font-size:12px;" oninput="filterITGlueUploadOrgs()">';
    html += '<div style="max-height:200px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;">';
    for (var i = 0; i < orgs.length; i++) {
      var matched = (i === bestOrgIdx);
      html += '<label class="itglue-upload-org-row" data-name="' + esc(orgs[i].name.toLowerCase()) + '" style="display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer;border-bottom:1px solid var(--border);' + (matched ? 'background:rgba(77,159,181,0.1);' : '') + '">';
      html += '<input type="radio" name="itglue-upload-org" value="' + esc(orgs[i].id) + '" data-orgname="' + esc(orgs[i].name) + '" ' + (matched ? 'checked' : '') + ' onchange="updateITGlueUploadBtn()" style="width:15px;height:15px;">';
      html += '<span style="font-size:12px;">' + esc(orgs[i].name) + '</span>';
      if (matched) html += '<span style="margin-left:auto;font-size:10px;color:var(--green);font-weight:600;">' + t('msg_recommended') + '</span>';
      html += '</label>';
    }
    html += '</div>';

    content.innerHTML = html;
    updateITGlueUploadBtn();

    // Scroll to matched org
    setTimeout(function() {
      var checked = content.querySelector('input[name="itglue-upload-org"]:checked');
      if (checked) checked.closest('label').scrollIntoView({block:'center'});
    }, 100);
  } catch (e) {
    content.innerHTML = '<div class="alert alert-error">' + t('status_error') + ': ' + esc(e.message) + '</div>';
  }
}

function filterITGlueUploadOrgs() {
  var q = (document.getElementById('itglue-upload-org-search') || {}).value.toLowerCase();
  document.querySelectorAll('.itglue-upload-org-row').forEach(function(r) {
    r.style.display = r.dataset.name.indexOf(q) >= 0 ? '' : 'none';
  });
}

function updateITGlueUploadBtn() {
  var fileCount = document.querySelectorAll('.itglue-file-cb:checked').length;
  var orgSelected = !!document.querySelector('input[name="itglue-upload-org"]:checked');
  var btn = document.getElementById('btn-itglue-upload-go');
  btn.disabled = fileCount === 0 || !orgSelected;
  btn.textContent = fileCount > 0 ? t('btn_upload_count').replace('{count}', fileCount) : t('btn_upload');
}

async function executeITGlueUpload() {
  var selectedFiles = [];
  document.querySelectorAll('.itglue-file-cb:checked').forEach(function(cb) {
    selectedFiles.push(cb.value);
  });
  var orgRadio = document.querySelector('input[name="itglue-upload-org"]:checked');
  if (!orgRadio || selectedFiles.length === 0) return;

  var orgId = orgRadio.value;
  var orgName = orgRadio.dataset.orgname;
  var btn = document.getElementById('btn-itglue-upload-go');
  btn.disabled = true;
  btn.textContent = t('btn_uploading');

  try {
    var d = await apiFetch('/api/itglue/upload/reports', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({org_id: orgId, files: selectedFiles})
    });

    if (d.error) { showToast(t('status_error') + ': ' + d.error, 'error'); return; }
    showToast(t('msg_uploaded_reports').replace('{count}', d.uploaded).replace('{org}', orgName) + ': ' + (d.files || []).join(', '), 'success', 8000);
    document.getElementById('itglue-upload-modal').style.display = 'none';
  } catch (e) {
    showToast(t('status_error') + ': ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = t('btn_upload');
  }
}

async function uploadToITGlue(btn) {
  // Determine upload type from card context
  const card = btn.closest('.card');
  const title = card.querySelector('.card-title')?.textContent || '';
  let uploadType = 'audit';
  if (title.includes('Tilkoblings') || title.includes('Connection') || title.includes('Sertifikat') || title.includes('Certificate')) uploadType = 'credentials';

  // First check if IT Glue is configured
  try {
    const settings = await apiFetch('/api/settings');
    if (!settings.itglue_api_key_set) {
      if (await showConfirm(t('dlg_confirm_itglue_setup_full'))) {
        showView('integrations');
        setTimeout(function(){ toggleIntegConfig('itglue-config'); }, 300);
      }
      return;
    }
  } catch { showToast(t('err_check_settings_failed'), 'error'); return; }

  // Get organizations list
  if (!_itglueOrgCache) {
    btn.disabled = true;
    setButtonLabel(btn, t('msg_fetching_orgs'));
    try {
      const d = await apiFetch('/api/itglue/organizations', {method: 'POST'});
      _itglueOrgCache = d.organizations || [];
    } catch(e) {
      showToast(t('err_error_fetching_orgs').replace('{msg}', e.message), 'error');
      btn.disabled = false;
      setButtonLabel(btn, t('btn_upload_to_itglue'));
      return;
    }
  }

  // Show org picker
  const orgId = await pickITGlueOrg(_itglueOrgCache);
  if (!orgId) { btn.disabled = false; setButtonLabel(btn, t('btn_upload_to_itglue')); return; }

  btn.disabled = true;
  setButtonLabel(btn, t('btn_uploading'));

  try {
    const endpoint = uploadType === 'credentials' ? '/api/itglue/upload/credentials' : '/api/itglue/upload/audit';
    const r = await fetch(endpoint, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({org_id: orgId})
    });
    const d = await r.json();
    if (d.ok) {
      setButtonLabel(btn, t('msg_uploaded_success'));
      btn.style.color = 'var(--green)';
      setTimeout(() => { setButtonLabel(btn, t('btn_upload_to_itglue')); btn.style.color = ''; btn.disabled = false; }, 3000);
    } else {
      showToast(t('status_error') + ': ' + (d.error || t('err_unknown')), 'error');
      setButtonLabel(btn, t('btn_upload_to_itglue'));
      btn.disabled = false;
    }
  } catch(e) {
    showToast(t('status_error') + ': ' + e.message, 'error');
    setButtonLabel(btn, t('btn_upload_to_itglue'));
    btn.disabled = false;
  }
}

function pickITGlueOrg(orgs) {
  return new Promise((resolve) => {
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop open';
    backdrop.innerHTML = `
      <div class="modal" style="max-height:80vh;overflow-y:auto;">
        <div class="modal-title" data-i18n="hdr_itglue_org_picker">${t('hdr_itglue_org_picker')}</div>
        <div class="modal-desc">${t('msg_select_org_upload','Select which organization to upload data to.')}</div>
        <input class="field-input" id="itglue-org-search" type="text" placeholder="${t('placeholder_search','Search...')}" style="margin-bottom:12px;">
        <div id="itglue-org-list" style="max-height:300px;overflow-y:auto;"></div>
        <div class="modal-actions">
          <button class="btn btn-default" id="itglue-org-cancel">${t('btn_cancel','Cancel')}</button>
        </div>
      </div>`;
    document.body.appendChild(backdrop);

    const list = backdrop.querySelector('#itglue-org-list');
    const search = backdrop.querySelector('#itglue-org-search');

    function render(filter) {
      const filtered = filter ? orgs.filter(o => o.name.toLowerCase().includes(filter.toLowerCase())) : orgs;
      list.innerHTML = filtered.map(o =>
        `<div style="padding:8px 12px;border-bottom:1px solid var(--border);cursor:pointer;font-size:13px;" class="itglue-org-item" data-id="${o.id}">${esc(o.name)}</div>`
      ).join('');
    }
    render('');

    search.oninput = () => render(search.value);
    list.onclick = (e) => {
      const item = e.target.closest('.itglue-org-item');
      if (item) { document.body.removeChild(backdrop); resolve(item.dataset.id); }
    };
    backdrop.querySelector('#itglue-org-cancel').onclick = () => {
      document.body.removeChild(backdrop);
      resolve(null);
    };
  });
}

async function migrateEncryption() {
  const btn = document.getElementById('btn-migrate-encrypt');
  const result = document.getElementById('migrate-encrypt-result');
  btn.disabled = true;
  result.textContent = t('msg_encrypting');
  try {
    const d = await apiFetch('/api/encrypt/migrate', {method:'POST'});
    if (d.ok) {
      result.innerHTML = '<span style="color:var(--green);">' + t('msg_files_encrypted').replace('{count}', d.files_encrypted) + '</span>';
    } else {
      result.innerHTML = `<span style="color:var(--red);">✗ ${t('status_error')}: ${d.error}</span>`;
    }
  } catch(e) {
    result.innerHTML = `<span style="color:var(--red);">✗ ${e.message}</span>`;
  }
  btn.disabled = false;
}

// ── History ─────────────────────────────────────────────────────────────────────
async function loadHistory() {
  const box = document.getElementById('history-content');
  const d = await apiFetch('/api/history');
  if (d) {
    renderHistory(d.history || []);
  } else {
    box.innerHTML = '<div class="alert alert-error">' + t('err_could_not_load_history') + '</div>';
  }
}

let _compareSelected = [];

function onCompareCheck(path, checked) {
  if (checked) {
    _compareSelected.push(path);
  } else {
    _compareSelected = _compareSelected.filter(p => p !== path);
  }
  var btnCompare = document.getElementById('btn-compare');
  var btnDelete = document.getElementById('btn-delete-selected');
  // Only allow compare if exactly 2 selected and both have metrics
  var canCompare = _compareSelected.length === 2;
  if (canCompare) {
    var cbs = document.querySelectorAll('input.compare-cb:checked');
    cbs.forEach(function(cb) {
      if (cb.dataset.hasMetrics === 'false') canCompare = false;
    });
  }
  btnCompare.style.display = canCompare ? 'inline-block' : 'none';
  btnDelete.style.display = _compareSelected.length > 0 ? 'inline-block' : 'none';
  btnDelete.textContent = t('btn_delete_selected') + ' (' + _compareSelected.length + ')';
}

async function runComparison() {
  if (_compareSelected.length !== 2) {
    showToast(t('msg_select_2_for_compare'), 'warning');
    return;
  }
  const btn = document.getElementById('btn-compare');
  btn.disabled = true;
  btn.textContent = t('btn_loading');
  const box = document.getElementById('compare-result');
  box.style.display = 'block';
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  box.innerHTML = '<div style="text-align:center;padding:24px;"><div class="loader" style="width:24px;height:24px;margin:0 auto 12px;"></div>' + t('msg_comparing') + '</div>';
  try {
    const d = await apiFetch('/api/audit/compare?run1=' + encodeURIComponent(_compareSelected[0]) + '&run2=' + encodeURIComponent(_compareSelected[1]));
    if (d.error) { box.innerHTML = `<div class="alert alert-error">${esc(d.error)}</div>`; return; }
    renderComparison(d, box);
    box.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    box.innerHTML = `<div class="alert alert-error">${t('status_error')}: ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = t('btn_compare_selected');
  }
}

async function deleteSelectedRuns() {
  if (_compareSelected.length === 0) return;
  var count = _compareSelected.length;
  if (!await showConfirm(t('dlg_confirm_delete_runs').replace('{count}', count))) return;
  try {
    var d = await apiFetch('/api/history/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({paths: _compareSelected})
    });

    if (d.errors && d.errors.length > 0) {
      showToast(t('hist_deleted_runs').replace('{count}', d.deleted) + ' — ' + d.errors.join(', '), 'warning', 8000);
    }
    _compareSelected = [];
    document.getElementById('btn-delete-selected').style.display = 'none';
    document.getElementById('btn-compare').style.display = 'none';
    loadHistory();
  } catch (e) {
    showToast(t('err_delete_failed').replace('{msg}', e.message), 'error');
  }
}

async function deleteAllCustomerRuns(customerDirName, customerName, runCount) {
  if (!await showTypedConfirm(
    customerName,
    t('dlg_confirm_delete_all_runs').replace('{count}', runCount).replace('{name}', customerName),
    t('dlg_destructive_audit_history', 'Dette fjerner {count} audit-kjøringer og tilhørende rapporter for denne kunden. Ikke reversibelt.').replace('{count}', runCount)
  )) return;
  try {
    var d = await apiFetch('/api/history/delete-customer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({customer_dir: customerDirName})
    });

    if (d.error) {
      showToast(t('status_error') + ': ' + d.error, 'error');
      return;
    }
    _compareSelected = [];
    document.getElementById('btn-delete-selected').style.display = 'none';
    document.getElementById('btn-compare').style.display = 'none';
    loadHistory();
  } catch (e) {
    showToast(t('err_delete_failed').replace('{msg}', e.message), 'error');
  }
}

function _fmtTs(ts) {
  const m = ts.match(/^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})$/);
  return m ? `${m[3]}.${m[2]}.${m[1]} kl. ${m[4]}:${m[5]}` : ts;
}

function renderComparison(data, box) {
  const labels = {
    risk_score: t('compare_risk_score'), risk_grade: t('compare_risk_grade'),
    mfa_coverage_pct: t('compare_mfa_coverage'), secure_score_pct: t('compare_secure_score'),
    total_users: t('compare_total_users'), users_no_mfa: t('compare_users_no_mfa'),
    ca_policies_enabled: t('compare_ca_policies'), intune_compliance_pct: t('compare_intune_compliance'),
    admin_roles_ga_count: t('compare_global_admins'), total_warns: t('compare_total_warnings'),
  };
  const ts1 = _fmtTs(data.run1.timestamp), ts2 = _fmtTs(data.run2.timestamp);
  let rows = '';
  for (const d of data.deltas) {
    const label = labels[d.key] || d.key;
    const v1 = d.run1 != null ? d.run1 : '\u2014';
    const v2 = d.run2 != null ? d.run2 : '\u2014';
    let arrow = '', color = 'var(--text-muted)', bg = 'transparent';
    if (d.direction === 'improved') { arrow = ' \u2191'; color = '#22c55e'; bg = 'rgba(34,197,94,0.08)'; }
    else if (d.direction === 'worsened') { arrow = ' \u2193'; color = '#ef4444'; bg = 'rgba(239,68,68,0.08)'; }
    else if (d.direction === 'unchanged') { arrow = ' \u2192'; color = 'var(--text-muted)'; }
    else { arrow = ' ~'; color = '#4d9fb5'; }
    const deltaStr = d.delta != null ? (d.delta > 0 ? '+' + d.delta : '' + d.delta) : '';
    const barWidth = d.delta != null ? Math.min(100, Math.abs(d.delta) * 2) : 0;
    const barColor = d.direction === 'improved' ? '#22c55e' : d.direction === 'worsened' ? '#ef4444' : '#4d9fb5';
    const barHtml = barWidth > 0 ? `<div style="display:inline-block;width:${barWidth}px;height:6px;border-radius:3px;background:${barColor};margin-left:6px;vertical-align:middle;"></div>` : '';
    rows += `<tr style="background:${bg};transition:background var(--duration-fast);" onmouseover="this.style.background='rgba(77,159,181,0.06)'" onmouseout="this.style.background='${bg}'">
      <td style="font-weight:500;">${esc(label)}</td>
      <td style="text-align:center;font-family:var(--mono);">${esc(String(v1))}</td>
      <td style="text-align:center;font-family:var(--mono);">${esc(String(v2))}</td>
      <td style="text-align:center;font-weight:600;color:${color};font-family:var(--mono);">${deltaStr ? esc(deltaStr) : ''}${arrow}${barHtml}</td>
    </tr>`;
  }
  box.innerHTML = `
    <div class="card" style="margin-top:20px;border-left:3px solid #1d6387;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
        <div class="card-title" style="margin:0;">${t('hdr_comparison')}</div>
        <button class="btn btn-ghost" style="padding:4px 10px;font-size:12px;" onclick="document.getElementById('compare-result').style.display='none';">${t('btn_close')}</button>
      </div>
      <div class="table-wrap">
        <table class="section-table" style="width:100%;">
          <thead><tr>
            <th style="text-align:left;">${t('lbl_metric')}</th>
            <th style="text-align:center;color:#1d6387;">${esc(ts1)}</th>
            <th style="text-align:center;color:#4d9fb5;">${esc(ts2)}</th>
            <th style="text-align:center;">${t('lbl_change')}</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
}

function renderHistory(runs) {
  const box = document.getElementById('history-content');
  _compareSelected = [];
  document.getElementById('btn-compare').style.display = 'none';
  document.getElementById('compare-result').style.display = 'none';

  if (runs.length === 0) {
    box.innerHTML = `
      <div class="empty-state">
        <div class="empty-title">${t('msg_no_prev_runs')}</div>
        <div class="empty-desc">${t('msg_run_audit_first')}</div>
        <button class="btn btn-primary" onclick="showView('home')" style="margin-top:var(--space-2);">${t('btn_run_audit')}</button>
      </div>`;
    return;
  }

  // Group by customer
  const grouped = {};
  for (const run of runs) {
    if (!grouped[run.customer]) grouped[run.customer] = [];
    grouped[run.customer].push(run);
  }

  let html = '';
  for (const [customer, customerRuns] of Object.entries(grouped)) {
    const customerDirName = customerRuns[0] && customerRuns[0].path ? customerRuns[0].path.split('/').slice(-2, -1)[0] : '';
    const escapedCustDir = esc(customerDirName.replace(/'/g, "\\'"));
    html += `<div class="card" style="margin-bottom:16px;">
      <div class="card-title" style="display:flex;align-items:center;justify-content:space-between;">
        <span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
          ${esc(customer)} <span style="font-weight:400;font-size:12px;color:var(--text-muted);">${t('hist_runs_count').replace('{count}', customerRuns.length)}</span>
        </span>
        <button class="btn btn-ghost" style="padding:3px 10px;font-size:11px;color:var(--red);"
          onclick="deleteAllCustomerRuns('${escapedCustDir}', '${esc(customer)}', ${customerRuns.length})">
          ${t('btn_delete_all')}
        </button>
      </div>
      <div class="table-wrap">
        <table class="section-table">
          <thead>
            <tr>
              <th style="width:32px;text-align:center;" title="${t('tip_compare_delete')}">⇄</th>
              <th>${t('lbl_date_time')}</th>
              <th>${t('lbl_files')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>`;

    for (const run of customerRuns) {
      // Format timestamp: "2026-03-12_0945" -> "12.03.2026 kl. 09:45"
      const ts = run.timestamp;
      let displayDate = ts;
      const m = ts.match(/^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})$/);
      if (m) {
        displayDate = `${m[3]}.${m[2]}.${m[1]} kl. ${m[4]}:${m[5]}`;
      }

      const escapedPath = esc(run.path.replace(/'/g, "\\'"));
      const canCompare = run.has_metrics !== false;
      var runTip = canCompare && run.metrics ? t('lbl_grade')+': '+(run.metrics.risk_grade||'-')+' · Score: '+(run.metrics.risk_score||'-')+' · MFA: '+(metricPct(run.metrics.mfa_coverage_pct) !== null ? metricPct(run.metrics.mfa_coverage_pct)+'%' : '-') : '';
      html += `
        <tr${canCompare ? '' : ' style="opacity:0.6;"'}${runTip ? ' title="'+esc(runTip)+'"' : ''} style="cursor:pointer;transition:background var(--duration-fast);${canCompare ? '' : 'opacity:0.6;'}" onmouseover="this.style.background='rgba(77,159,181,0.06)'" onmouseout="this.style.background=''">
          <td style="text-align:center;">
            <input type="checkbox" class="compare-cb" data-path="${esc(run.path)}" data-has-metrics="${canCompare}"
              onchange="onCompareCheck('${escapedPath}', this.checked)"
              style="accent-color:#1d6387;width:15px;height:15px;cursor:pointer;">
          </td>
          <td style="font-weight:500;">${esc(displayDate)}${canCompare ? '' : ' <span style="color:var(--red);font-size:11px;">' + t('ufullstendig') + '</span>'}${canCompare && run.metrics ? ' <span style="display:inline-block;width:20px;height:20px;line-height:20px;border-radius:4px;font-weight:800;font-size:10px;color:#fff;background:'+({A:'#3fb950',B:'#4d9fb5',C:'#d29922',D:'#f85149',F:'#8b0000'}[run.metrics.risk_grade]||'var(--text-dim)')+';text-align:center;vertical-align:middle;margin-left:6px;">'+(run.metrics.risk_grade||'?')+'</span>' : ''}</td>
          <td style="font-family:var(--mono);color:var(--text-muted);">${run.file_count} ${t('nav_files','filer')}</td>
          <td style="text-align:right;">
            <button class="btn btn-primary" style="padding:4px 12px;font-size:12px;"
              onclick="loadHistoryRun('${escapedPath}')">
              ${t('btn_generate_report')}
            </button>
          </td>
        </tr>`;
    }

    html += `</tbody></table></div></div>`;
  }

  box.innerHTML = html;
}

async function loadHistoryRun(path) {
  const box = document.getElementById('hist-report-info');
  const resultBox = document.getElementById('hist-report-result');
  resultBox.innerHTML = '';

  showView('history-report');
  document.getElementById('hist-report-title').textContent = t('msg_loading');
  document.getElementById('hist-report-subtitle').textContent = '';
  box.innerHTML = '<div class="loader"></div> ' + t('msg_loading_audit_data');

  try {
    const d = await apiFetch('/api/history/load', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });


    if (d.error) {
      box.innerHTML = `<div class="alert alert-error">✗ ${esc(d.error)}</div>`;
      return;
    }

    document.getElementById('hist-report-title').textContent = t('hdr_report_for').replace('{customer}', d.customer);

    // Format timestamp
    let displayDate = d.timestamp;
    const m = d.timestamp.match(/^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})$/);
    if (m) {
      displayDate = `${m[3]}.${m[2]}.${m[1]} kl. ${m[4]}:${m[5]}`;
    }
    document.getElementById('hist-report-subtitle').textContent = displayDate;

    box.innerHTML = t('msg_sections_data_loaded').replace('{sections}', '<strong>' + d.sections + '</strong>').replace('{files}', '<strong>' + d.files + '</strong>').replace('{date}', esc(displayDate));
  } catch (e) {
    box.innerHTML = `<div class="alert alert-error">✗ ${t('err_network_error').replace('{msg}', esc(e.message))}</div>`;
  }
}

// ── Tag utilities ──
var TAG_SUGGESTIONS=['Premium','Standard','Basic',t('tag_priority','Priority'),t('tag_new_customer','New customer'),t('tag_trial','Trial')];
var TAG_COLORS={'Premium':{bg:'#3fb95020',border:'#3fb95060',color:'#3fb950'},'Standard':{bg:'#4d9fb520',border:'#4d9fb560',color:'#4d9fb5'},'Basic':{bg:'#8b8b8b20',border:'#8b8b8b60',color:'#8b8b8b'},'Prioritert':{bg:'#f8514920',border:'#f8514960',color:'#f85149'},'Priority':{bg:'#f8514920',border:'#f8514960',color:'#f85149'},'Ny kunde':{bg:'#d2992220',border:'#d2992260',color:'#d29922'},'New customer':{bg:'#d2992220',border:'#d2992260',color:'#d29922'},'Proveperiode':{bg:'#a371f720',border:'#a371f760',color:'#a371f7'},'Trial':{bg:'#a371f720',border:'#a371f760',color:'#a371f7'}};
function tagPillHtml(tag){var tc=TAG_COLORS[tag]||{bg:'#58a6ff20',border:'#58a6ff50',color:'#58a6ff'};return '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:600;background:'+tc.bg+';border:1px solid '+tc.border+';color:'+tc.color+';margin-right:4px;margin-top:2px;white-space:nowrap;">'+esc(tag)+'</span>';}
function tagPillsHtml(tags){if(!tags||tags.length===0)return '';return tags.map(tagPillHtml).join('');}
async function saveCustomerTags(cid,tags){try{await apiFetch('/api/customer/tags',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer_id:cid,tags:tags})})}catch(e){console.error('save tags:',e)}}
function showTagEditor(cid,curTags){var ex=curTags?curTags.slice():[];var si=cid.replace(/[^a-zA-Z0-9_-]/g,'_');var ct=document.getElementById('tag-editor-'+si);if(!ct)return;var sf=TAG_SUGGESTIONS.filter(function(s){return ex.indexOf(s)===-1});var h='<div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center;margin-bottom:8px;">';ex.forEach(function(t,i){var tc=TAG_COLORS[t]||{bg:'#58a6ff20',border:'#58a6ff50',color:'#58a6ff'};h+='<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;background:'+tc.bg+';border:1px solid '+tc.border+';color:'+tc.color+';">'+esc(t)+' <span style="cursor:pointer;font-size:14px;line-height:1;opacity:0.7;" onclick="removeTagAndRefresh(\''+esc(cid)+'\','+i+')">&times;</span></span>'});h+='</div><div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">';h+='<input type="text" id="tag-input-'+si+'" placeholder="' + t('lbl_write_tag') + '" style="padding:4px 8px;border:1px solid var(--border);border-radius:6px;font-size:12px;background:var(--bg);color:var(--text);width:120px;" onkeydown="if(event.key===\'Enter\'){addTagFromInput(\''+esc(cid)+'\');event.preventDefault()}">';h+='<button class="btn btn-primary" style="padding:3px 10px;font-size:11px;" onclick="addTagFromInput(\''+esc(cid)+'\')">+</button></div>';if(sf.length>0){h+='<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:4px;">';sf.forEach(function(s){h+='<button class="btn btn-ghost" style="padding:2px 8px;font-size:10px;border:1px dashed var(--border);border-radius:12px;" onclick="addSuggestedTag(\''+esc(cid)+'\',\''+esc(s)+'\')">+ '+esc(s)+'</button>'});h+='</div>'}ct.innerHTML=h;ct.style.display='block'}
var _tagEditorData={};
function openTagEditor(cid,tags){_tagEditorData[cid]=tags?tags.slice():[];showTagEditor(cid,_tagEditorData[cid])}
function closeTagEditor(cid){var si=cid.replace(/[^a-zA-Z0-9_-]/g,'_');var c=document.getElementById('tag-editor-'+si);if(c){c.innerHTML='';c.style.display='none'}delete _tagEditorData[cid]}
function addTagFromInput(cid){var si=cid.replace(/[^a-zA-Z0-9_-]/g,'_');var inp=document.getElementById('tag-input-'+si);if(!inp||!inp.value.trim())return;if(!_tagEditorData[cid])_tagEditorData[cid]=[];if(_tagEditorData[cid].indexOf(inp.value.trim())===-1)_tagEditorData[cid].push(inp.value.trim());saveCustomerTags(cid,_tagEditorData[cid]).then(function(){showTagEditor(cid,_tagEditorData[cid]);refreshTagPills(cid,_tagEditorData[cid])})}
function addSuggestedTag(cid,tag){if(!_tagEditorData[cid])_tagEditorData[cid]=[];if(_tagEditorData[cid].indexOf(tag)===-1)_tagEditorData[cid].push(tag);saveCustomerTags(cid,_tagEditorData[cid]).then(function(){showTagEditor(cid,_tagEditorData[cid]);refreshTagPills(cid,_tagEditorData[cid])})}
function removeTagAndRefresh(cid,index){if(!_tagEditorData[cid])return;_tagEditorData[cid].splice(index,1);saveCustomerTags(cid,_tagEditorData[cid]).then(function(){showTagEditor(cid,_tagEditorData[cid]);refreshTagPills(cid,_tagEditorData[cid])})}
function refreshTagPills(cid,tags){var si=cid.replace(/[^a-zA-Z0-9_-]/g,'_');var el=document.getElementById('tag-pills-'+si);if(el)el.innerHTML=tagPillsHtml(tags)}

// ── Manual Customer ─────────────────────────────────────────────────────────────

function openManualCustomer() {
  var modal = document.getElementById('manual-customer-modal');
  modal.style.display = 'flex';
  document.getElementById('manual-cust-name').value = '';
  document.getElementById('manual-cust-domain').value = '';
  document.getElementById('manual-cust-email').value = '';
  document.getElementById('manual-cust-phone').value = '';
  document.getElementById('manual-cust-orgnum').value = '';
  document.getElementById('manual-cust-notes').value = '';
  document.getElementById('manual-cust-error').style.display = 'none';
  document.getElementById('manual-cust-name').focus();
}

async function submitManualCustomer() {
  var name = document.getElementById('manual-cust-name').value.trim();
  var errEl = document.getElementById('manual-cust-error');
  if (!name) {
    errEl.textContent = t('err_name_required');
    errEl.style.display = 'block';
    return;
  }
  errEl.style.display = 'none';
  var btn = document.getElementById('btn-manual-cust-save');
  btn.disabled = true;

  var d = await apiFetch('/api/customers/add-manual', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      name: name,
      primary_domain: document.getElementById('manual-cust-domain').value.trim(),
      contact_email: document.getElementById('manual-cust-email').value.trim(),
      contact_phone: document.getElementById('manual-cust-phone').value.trim(),
      org_number: document.getElementById('manual-cust-orgnum').value.trim(),
      notes: document.getElementById('manual-cust-notes').value.trim()
    })
  });
  btn.disabled = false;

  if (d && d.ok) {
    document.getElementById('manual-customer-modal').style.display = 'none';
    showToast(t('msg_customer_added'), 'success');
    loadCustomers();
  } else if (d && d.error) {
    errEl.textContent = d.error;
    errEl.style.display = 'block';
  }
}

// ── IT Glue Import ──────────────────────────────────────────────────────────────
var _itglueImportOrgs = [];

async function openITGlueImport() {
  var modal = document.getElementById('itglue-import-modal');
  var content = document.getElementById('itglue-import-content');
  var btn = document.getElementById('btn-itglue-import');
  modal.style.display = 'flex';
  btn.disabled = true;
  content.innerHTML = '<div style="text-align:center;padding:24px;"><div class="loader" style="width:24px;height:24px;margin:0 auto 12px;"></div><span data-i18n="msg_fetching_orgs_itglue">' + t('henter_organisasjoner_fra_it_glue') + '</span></div>';
  _itglueImportOrgs = [];

  try {
    var d = await apiFetch('/api/itglue/organizations', {method: 'POST'});
    if (d.error) {
      content.innerHTML = '<div class="alert alert-error">' + esc(d.error) + '</div>';
      return;
    }
    var orgs = d.organizations || [];
    if (orgs.length === 0) {
      content.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-muted);">' + t('msg_no_orgs_found_itglue') + '</div>';
      return;
    }

    // Get existing customers to show which are already imported
    var custData = await apiFetch('/api/customers');
    var existingNames = new Set();
    if (custData && custData.customers) {
      custData.customers.forEach(function(c) { existingNames.add((c.CustomerName || '').toLowerCase()); });
    }

    var html = '<div style="margin-bottom:12px;display:flex;gap:8px;align-items:center;">';
    html += '<input type="text" id="itglue-import-search" class="field-input" placeholder="' + t('lbl_search') + '" style="flex:1;padding:6px 12px;font-size:12px;" oninput="filterITGlueImport()">';
    html += '<label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer;white-space:nowrap;"><input type="checkbox" id="itglue-import-select-all" onchange="toggleAllITGlueImport(this.checked)"> ' + t('btn_select_all') + '</label>';
    html += '</div>';
    html += '<div style="max-height:350px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;">';
    html += '<table class="section-table" style="width:100%;"><thead><tr><th style="width:32px;"></th><th style="text-align:left;">' + t('lbl_organization') + '</th><th style="text-align:left;">' + t('lbl_id') + '</th><th></th></tr></thead><tbody>';

    orgs.sort(function(a, b) { return a.name.localeCompare(b.name); });
    _itglueImportOrgs = orgs;

    for (var i = 0; i < orgs.length; i++) {
      var o = orgs[i];
      var exists = existingNames.has(o.name.toLowerCase());
      html += '<tr class="itglue-import-row" data-name="' + esc(o.name.toLowerCase()) + '"' + (exists ? ' style="opacity:0.4;"' : '') + '>';
      html += '<td style="text-align:center;"><input type="checkbox" class="itglue-import-cb" data-idx="' + i + '" ' + (exists ? 'disabled title="' + esc(t('msg_already_imported')) + '"' : '') + ' onchange="updateITGlueImportBtn()" style="width:15px;height:15px;cursor:pointer;"></td>';
      html += '<td style="font-weight:500;">' + esc(o.name) + '</td>';
      html += '<td style="font-family:var(--mono);font-size:11px;color:var(--text-muted);">' + esc(o.id) + '</td>';
      html += '<td style="font-size:11px;color:var(--text-muted);">' + (exists ? '<span style="color:var(--green);">' + t('msg_already_exists') + '</span>' : '') + '</td>';
      html += '</tr>';
    }
    html += '</tbody></table></div>';
    content.innerHTML = html;
  } catch (e) {
    content.innerHTML = '<div class="alert alert-error">' + t('status_error') + ': ' + esc(e.message) + '</div>';
  }
}

function filterITGlueImport() {
  var q = (document.getElementById('itglue-import-search') || {}).value || '';
  q = q.toLowerCase();
  document.querySelectorAll('.itglue-import-row').forEach(function(row) {
    row.style.display = row.dataset.name.indexOf(q) >= 0 ? '' : 'none';
  });
}

function toggleAllITGlueImport(checked) {
  document.querySelectorAll('.itglue-import-cb:not(:disabled)').forEach(function(cb) {
    cb.checked = checked;
  });
  updateITGlueImportBtn();
}

function updateITGlueImportBtn() {
  var count = document.querySelectorAll('.itglue-import-cb:checked').length;
  var btn = document.getElementById('btn-itglue-import');
  btn.disabled = count === 0;
  btn.textContent = count > 0 ? t('btn_import_selected') + ' (' + count + ')' : t('btn_import_selected');
}

async function runITGlueImport() {
  var selected = [];
  document.querySelectorAll('.itglue-import-cb:checked').forEach(function(cb) {
    var idx = parseInt(cb.dataset.idx);
    if (_itglueImportOrgs[idx]) {
      selected.push({name: _itglueImportOrgs[idx].name, id: _itglueImportOrgs[idx].id});
    }
  });
  if (selected.length === 0) return;

  var btn = document.getElementById('btn-itglue-import');
  btn.disabled = true;
  btn.textContent = t('btn_importing');

  try {
    var d = await apiFetch('/api/customers/import-itglue', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({organizations: selected})
    });
    if (!d) return;
    if (d.error) {
      showToast(t('status_error') + ': ' + d.error, 'error');
      return;
    }

    var msg = t('msg_customers_imported').replace('{count}', d.imported);
    if (d.skipped > 0) msg += ' ' + t('msg_customers_skipped').replace('{count}', d.skipped);
    showToast(msg, 'success', 8000);

    document.getElementById('itglue-import-modal').style.display = 'none';
    loadCustomers();
  } catch (e) {
    showToast(t('status_error') + ': ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = t('btn_import_selected');
  }
}

// ── Customers management ────────────────────────────────────────────────────────
var _allCustomers = [];
var _customersActiveId = null;

async function loadCustomers() {
  const box = document.getElementById('customers-content');
  try {
    const [d, expiryResult] = await Promise.all([
      apiFetch('/api/customers'),
      _expiryData ? Promise.resolve(null) : apiFetch('/api/expiry/check')
    ]);
    if (!d) { box.innerHTML = '<div class="alert alert-error">' + t('err_could_not_load_customers') + '</div>'; return; }
    if (expiryResult) _expiryData = expiryResult;
    _allCustomers = d.customers || [];
    _customersActiveId = d.active_id;
    // Clear search on fresh load
    var searchEl = document.getElementById('customers-search');
    if (searchEl && !searchEl.value) customersFilter();
    else renderCustomers(_allCustomers, _customersActiveId);
  } catch(e) {
    box.innerHTML = `<div class="alert alert-error">${t('status_error')}: ${esc(e.message)}</div>`;
  }
}

async function exportCustomersJSON() {
  try {
    var d = await apiFetch('/api/dashboard/overview');
    if (!d || !d.customers) { showToast(t('status_error'), 'error'); return; }
    var exportData = {
      exported_at: new Date().toISOString(),
      customer_count: d.customers.length,
      customers: d.customers.map(function(c) {
        return {
          customer_id: c.customer_id,
          customer_name: c.customer_name,
          primary_domain: c.primary_domain,
          has_metrics: c.has_metrics,
          last_audit: c.last_audit,
          tags: c.tags,
          metrics: c.metrics,
        };
      })
    };
    var blob = new Blob([JSON.stringify(exportData, null, 2)], {type: 'application/json'});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = 'msp_customers_' + new Date().toISOString().substring(0,10) + '.json';
    a.click(); URL.revokeObjectURL(url);
    showToast(t('msg_exported','Exported') + ' ' + d.customers.length + ' ' + t('nav_customers').toLowerCase(), 'success', 3000);
  } catch(e) { showToast(t('status_error') + ': ' + e.message, 'error'); }
}

var _bulkSelectedCustomers = [];

// Favorites (stored in localStorage)
function _getFavorites() { try { return JSON.parse(localStorage.getItem('sybr_favorites') || '[]'); } catch(e) { return []; } }
function _setFavorites(arr) { localStorage.setItem('sybr_favorites', JSON.stringify(arr)); }
function toggleFavorite(customerId) {
  var favs = _getFavorites();
  var idx = favs.indexOf(customerId);
  if (idx >= 0) favs.splice(idx, 1); else favs.push(customerId);
  _setFavorites(favs);
  loadCustomers();
}

function toggleBulkCustomer(customerId, cb) {
  if (cb.checked) { if (_bulkSelectedCustomers.indexOf(customerId)===-1) _bulkSelectedCustomers.push(customerId); }
  else { _bulkSelectedCustomers = _bulkSelectedCustomers.filter(function(id){return id!==customerId}); }
  var bar = document.getElementById('customers-bulk-bar');
  if (_bulkSelectedCustomers.length > 0) {
    bar.style.display = 'flex';
    document.getElementById('customers-bulk-count').textContent = _bulkSelectedCustomers.length + ' ' + t('status_selected','valgt');
  } else {
    bar.style.display = 'none';
  }
}

function clearBulkSelection() {
  _bulkSelectedCustomers = [];
  document.querySelectorAll('.customer-bulk-cb').forEach(function(cb){cb.checked=false});
  document.getElementById('customers-bulk-bar').style.display = 'none';
}

async function bulkTagCustomers() {
  var tag = prompt(t('msg_enter_tag','Enter tag name:'));
  if (!tag || !tag.trim()) return;
  tag = tag.trim();
  var count = _bulkSelectedCustomers.length;
  for (var i=0; i<_bulkSelectedCustomers.length; i++) {
    // Get existing tags, add new one if not present
    var cid = _bulkSelectedCustomers[i];
    try {
      // Find customer in cached data to get current tags
      var existing = [];
      if (_allCustomers) {
        var c = _allCustomers.find(function(x){return x._id === cid});
        if (c) existing = c._tags || [];
      }
      if (existing.indexOf(tag) === -1) existing.push(tag);
      await apiFetch('/api/customer/tags', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({customer_id:cid, tags:existing})});
    } catch(e) { console.warn('Bulk tag update failed for', cid, e); }
  }
  clearBulkSelection();
  loadCustomers();
  showToast(t('msg_tag_added','Tag added to') + ' ' + count + ' ' + t('nav_customers').toLowerCase(), 'success', 2000);
}

async function bulkDeleteCustomers() {
  // Bulk delete is extra dangerous — require typing "SLETT" literally.
  var sentinel = t('lbl_type_delete_sentinel', 'SLETT');
  var n = _bulkSelectedCustomers.length;
  if (!await showTypedConfirm(
    sentinel,
    t('dlg_confirm_bulk_delete_customers', 'Slett {n} kunder?').replace('{n}', n),
    t('dlg_destructive_bulk_delete', 'Dette sletter {n} kunder permanent med alle audits, rapporter og credentials.').replace('{n}', n)
  )) return;
  for (var i=0; i<_bulkSelectedCustomers.length; i++) {
    await apiFetch('/api/customers/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({customer_id:_bulkSelectedCustomers[i]})});
  }
  clearBulkSelection();
  loadCustomers();
  showToast(t('msg_saved','OK'), 'success', 2000);
}

function customersFilter() {
  var q = (document.getElementById('customers-search').value || '').toLowerCase();
  var filtered = _allCustomers;
  if (q) {
    filtered = _allCustomers.filter(function(c) {
      return (c.CustomerName || '').toLowerCase().indexOf(q) !== -1
        || (c.PrimaryDomain || '').toLowerCase().indexOf(q) !== -1
        || (c.TenantId || '').toLowerCase().indexOf(q) !== -1
        || (c._tags || []).some(function(tag) { return tag.toLowerCase().indexOf(q) !== -1; });
    });
  }
  var countEl = document.getElementById('customers-count');
  if (countEl) {
    countEl.textContent = q ? filtered.length + ' / ' + _allCustomers.length + ' ' + t('nav_customers').toLowerCase() : _allCustomers.length + ' ' + t('nav_customers').toLowerCase();
  }
  renderCustomers(filtered, _customersActiveId);
}

function renderCustomers(customers, activeId) {
  const box = document.getElementById('customers-content');
  if (customers.length === 0) {
    box.innerHTML = `
      <div class="empty-state">
        <div class="empty-title" style="margin-bottom:var(--space-6);">${t('onboarding_title','Kom i gang med Sybr HUB')}</div>
        <div style="display:flex;gap:var(--space-6);justify-content:center;flex-wrap:wrap;margin-bottom:var(--space-6);">
          <div style="text-align:center;max-width:180px;">
            <div style="width:48px;height:48px;line-height:48px;border-radius:50%;background:var(--blue);color:#fff;font-weight:800;font-size:var(--font-lg);margin:0 auto var(--space-3);">1</div>
            <div style="font-size:var(--font-sm);font-weight:600;">${t('onboarding_step1_title','Legg til kunde')}</div>
            <div style="font-size:var(--font-xs);color:var(--text-muted);margin-top:var(--space-1);">${t('onboarding_step1_desc','Klikk \"+ Ny kunde\" og følg veiviseren')}</div>
          </div>
          <div style="text-align:center;max-width:180px;">
            <div style="width:48px;height:48px;line-height:48px;border-radius:50%;background:var(--blue);color:#fff;font-weight:800;font-size:var(--font-lg);margin:0 auto var(--space-3);">2</div>
            <div style="font-size:var(--font-sm);font-weight:600;">${t('onboarding_step2_title','Sett opp M365')}</div>
            <div style="font-size:var(--font-xs);color:var(--text-muted);margin-top:var(--space-1);">${t('onboarding_step2_desc','Autorisér tilgang til kundens Microsoft 365')}</div>
          </div>
          <div style="text-align:center;max-width:180px;">
            <div style="width:48px;height:48px;line-height:48px;border-radius:50%;background:var(--blue);color:#fff;font-weight:800;font-size:var(--font-lg);margin:0 auto var(--space-3);">3</div>
            <div style="font-size:var(--font-sm);font-weight:600;">${t('onboarding_step3_title','Kjør audit')}</div>
            <div style="font-size:var(--font-xs);color:var(--text-muted);margin-top:var(--space-1);">${t('onboarding_step3_desc','26 sikkerhetskontroller kjøres automatisk')}</div>
          </div>
        </div>
        <button class="btn btn-primary btn-lg" onclick="showView('setup')">${t('btn_new_customer','+ Ny kunde')}</button>
      </div>`;
    return;
  }

  // Sort favorites first
  var favs = _getFavorites();
  customers.sort(function(a,b) {
    var fa = favs.indexOf(a._id) >= 0 ? 0 : 1;
    var fb = favs.indexOf(b._id) >= 0 ? 0 : 1;
    return fa - fb;
  });

  let html = '';
  for (const c of customers) {
    const isActive = c._id === activeId;
    const isFav = favs.indexOf(c._id) >= 0;
    const activeClass = isActive ? 'border-color:var(--blue);' : '';
    const activeBadge = isActive ? '<span style="background:var(--blue);color:#fff;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;">' + t('status_active','Aktiv') + '</span>' : '';
    const isGdap = c.AuthMode === 'gdap';
    const gdapBadge = isGdap ? '<span style="background:linear-gradient(135deg,#0078d4,#00bcf2);color:#fff;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:600;">GDAP</span>' : '';
    const expiryBadge = isGdap ? '' : getExpiryBadgeForCustomer(c._id);
    const notesBadge = c._has_notes ? '<span style="background:var(--blue-dark);color:var(--blue);padding:2px 8px;border-radius:12px;font-size:11px;border:1px solid rgba(77,159,181,0.3);">' + t('lbl_notes','Notat') + '</span>' : '';
    const cTags = c._tags || [];
    const safeId = c._id.replace(/[^a-zA-Z0-9_-]/g, '_');

    // Find metrics from overview cache
    var _om = null;
    if (_overviewData && _overviewData.customers) {
      _om = _overviewData.customers.find(function(oc){ return oc.customer_id === c._id; });
    }
    var hasMetrics = _om && _om.has_metrics;
    var grade = hasMetrics ? (_om.metrics.risk_grade || '-') : '';
    var gradeColor = {A:'#3fb950',B:'#4d9fb5',C:'#d29922',D:'#f85149',F:'#8b0000'}[grade] || 'var(--text-dim)';
    var mfaPct = hasMetrics && metricPct(_om.metrics.mfa_coverage_pct) !== null ? metricPct(_om.metrics.mfa_coverage_pct) + '%' : '';
    var riskScore = hasMetrics && _om.metrics.risk_score !== undefined ? _om.metrics.risk_score : '';
    var configured = isGdap ? !!c.TenantId : !!(c.TenantId && c.ClientId);
    var statusDot = configured ? (hasMetrics ? '<span style="width:8px;height:8px;border-radius:50%;background:' + gradeColor + ';display:inline-block;"></span>' : '<span style="width:8px;height:8px;border-radius:50%;background:var(--text-dim);display:inline-block;" title="' + t('tip_no_audit_run','No audit run') + '"></span>') : '<span style="width:8px;height:8px;border-radius:50%;background:var(--orange);display:inline-block;" title="' + t('tip_not_configured','Not configured') + '"></span>';

    html += `
      <div class="card card-clickable" style="margin-bottom:var(--space-3);${activeClass}" onclick="overviewSelectCustomer('${esc(c._id)}')">
        <div style="display:flex;align-items:center;gap:var(--space-4);">
          <input type="checkbox" class="customer-bulk-cb" onclick="event.stopPropagation();toggleBulkCustomer('${esc(c._id)}',this)" style="width:16px;height:16px;flex-shrink:0;cursor:pointer;accent-color:var(--blue);">
          <span onclick="event.stopPropagation();toggleFavorite('${esc(c._id)}')" style="cursor:pointer;font-size:18px;flex-shrink:0;transition:transform var(--duration-fast);" onmouseover="this.style.transform='scale(1.2)'" onmouseout="this.style.transform=''">${isFav ? '\u2605' : '\u2606'}</span>
          ${grade ? '<div style="width:42px;height:42px;line-height:42px;border-radius:var(--radius-lg);font-weight:800;font-size:var(--font-lg);color:#fff;background:'+gradeColor+';text-align:center;flex-shrink:0;">'+grade+'</div>' : '<div style="width:42px;height:42px;line-height:42px;border-radius:var(--radius-lg);font-size:var(--font-lg);color:var(--text-dim);background:var(--bg);text-align:center;flex-shrink:0;border:1px dashed var(--border);">?</div>'}
          <div style="flex:1;min-width:0;">
            <div style="display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap;">
              ${statusDot}
              <span style="font-size:var(--font-md);font-weight:700;">${esc(c.CustomerName || t('lbl_unknown','Unknown'))}</span>
              ${activeBadge} ${gdapBadge} ${expiryBadge} ${notesBadge}
            </div>
            <div style="font-size:var(--font-xs);color:var(--text-dim);font-family:var(--mono);margin-top:2px;">${esc(c.PrimaryDomain || '')}</div>
            <div style="display:flex;gap:var(--space-4);margin-top:var(--space-2);font-size:var(--font-xs);color:var(--text-muted);">
              ${riskScore !== '' ? '<span>' + t('lbl_score_prefix','Score:') + ' <strong style="color:var(--text);">' + riskScore + '</strong></span>' : ''}
              ${mfaPct ? '<span>' + t('lbl_mfa_prefix','MFA:') + ' <strong style="color:var(--text);">' + mfaPct + '</strong></span>' : ''}
              ${_om && _om.last_audit ? '<span>' + t('lbl_last_prefix','Last:') + ' <strong style="color:var(--text);">' + _om.last_audit.substring(0,10) + '</strong></span>' : ''}
              <span id="tag-pills-${safeId}" style="display:inline;">${tagPillsHtml(cTags)}</span>
            </div>
          </div>
          <div style="display:flex;gap:var(--space-2);flex-shrink:0;" onclick="event.stopPropagation();">
            ${isActive
              ? (configured
                ? `<button class="btn btn-success btn-sm" onclick="startAudit()">${t('audit_2')}</button>`
                : `<button class="btn btn-primary btn-sm" onclick="startSetup()">${t('btn_setup','Sett opp')}</button>`)
              : `<button class="btn btn-primary btn-sm" onclick="switchCustomer('${esc(c._id)}')">${t('btn_activate')}</button>`
            }
            <button class="btn btn-ghost btn-sm" style="color:var(--text-dim);" onclick="deleteCustomer('${esc(c._id)}', '${esc(c.CustomerName)}')" title="${t('btn_delete')}">${t('btn_delete')}</button>
          </div>
        </div>
        <div id="tag-editor-${safeId}" style="display:none;margin-top:8px;padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:8px;"></div>
      </div>`;
  }
  box.innerHTML = html;
}

// ── Active-customer quick switcher (in the persistent bar) ─────────────────
// Lets the user switch the active customer from any view without navigating
// to the Kunder list. Data source: /api/customers. Warns if an audit is
// currently running — switching mid-audit invalidates its data.

var _customerSwitcherCache = null;
var _customerSwitcherCacheAt = 0;
var _CUST_SWITCHER_TTL = 30000;  // 30 s — cheap refresh

async function toggleActiveCustomerSwitcher(event) {
  if (event) event.stopPropagation();
  var sw = document.getElementById('active-customer-switcher');
  if (!sw) return;
  var isOpen = sw.style.display === 'flex';
  if (isOpen) { sw.style.display = 'none'; return; }
  sw.style.display = 'flex';
  var search = document.getElementById('customer-switcher-search');
  if (search) { search.value = ''; search.focus(); }
  await _populateCustomerSwitcher();
}

function _closeActiveCustomerSwitcher() {
  var sw = document.getElementById('active-customer-switcher');
  if (sw) sw.style.display = 'none';
}

async function _populateCustomerSwitcher() {
  var now = Date.now();
  if (!_customerSwitcherCache || (now - _customerSwitcherCacheAt) > _CUST_SWITCHER_TTL) {
    var data = await apiFetch('/api/customers');
    _customerSwitcherCache = Array.isArray(data) ? data
      : (data && Array.isArray(data.customers) ? data.customers : []);
    _customerSwitcherCacheAt = now;
  }
  _renderCustomerSwitcherList('');
  var search = document.getElementById('customer-switcher-search');
  if (search) {
    search.oninput = function() { _renderCustomerSwitcherList(search.value); };
  }
}

function _renderCustomerSwitcherList(query) {
  var list = document.getElementById('customer-switcher-list');
  if (!list) return;
  var q = (query || '').toLowerCase().trim();
  var customers = _customerSwitcherCache || [];
  var filtered = customers.filter(function(c) {
    if (!q) return true;
    var name = (c.CustomerName || c.name || '').toLowerCase();
    var dom = (c.PrimaryDomain || c.primary_domain || '').toLowerCase();
    return name.indexOf(q) !== -1 || dom.indexOf(q) !== -1;
  });
  if (!filtered.length) {
    list.innerHTML = '<div style="padding:16px;color:var(--text-dim);text-align:center;font-size:12px;">' + esc(t('msg_no_results', 'Ingen treff')) + '</div>';
    return;
  }
  var gradeColor = { A: '#3fb950', B: '#4d9fb5', C: '#d29922', D: '#f85149', F: '#8b0000' };
  list.innerHTML = filtered.slice(0, 100).map(function(c) {
    var id = c._id || c.id || '';
    var name = c.CustomerName || c.name || '';
    var dom = c.PrimaryDomain || c.primary_domain || '';
    var grade = c.risk_grade || c.health_grade || '';
    var active = c.is_active;
    var gradeBadge = grade && gradeColor[grade]
      ? '<span style="background:' + gradeColor[grade] + ';color:#fff;padding:0 5px;border-radius:var(--radius-sm);font-size:9px;font-weight:700;margin-left:6px;">' + grade + '</span>'
      : '';
    var activeMark = active
      ? '<span style="color:var(--blue);font-size:14px;">&#10003;</span>'
      : '<span style="width:14px;display:inline-block;"></span>';
    return '<div data-switch-id="' + esc(id) + '" style="padding:6px 8px;cursor:pointer;border-radius:var(--radius-sm);display:flex;align-items:center;gap:8px;' + (active ? 'background:rgba(77,159,181,0.08);' : '') + '">' +
      activeMark +
      '<div style="flex:1;min-width:0;">' +
        '<div style="font-weight:600;font-size:12px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(name) + gradeBadge + '</div>' +
        (dom ? '<div style="font-size:10px;color:var(--text-dim);font-family:var(--mono);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(dom) + '</div>' : '') +
      '</div>' +
    '</div>';
  }).join('');
}

// Delegated click on the list (avoids per-row inline onclick)
document.addEventListener('click', function(e) {
  var row = e.target.closest('#customer-switcher-list [data-switch-id]');
  if (!row) return;
  var id = row.getAttribute('data-switch-id');
  if (!id) return;
  _pickCustomerFromSwitcher(id);
});

async function _pickCustomerFromSwitcher(customerId) {
  if (auditRunning) {
    var ok = await showConfirm(
      t('dlg_confirm_switch_during_audit', 'En audit kjører for nåværende kunde. Bytte kunde nå vil avbryte kjøringen. Fortsette?')
    );
    if (!ok) return;
  }
  _closeActiveCustomerSwitcher();
  await switchCustomer(customerId);
  // Invalidate cache so the freshly-activated customer shows ✓ next open
  _customerSwitcherCache = null;
}

// Close on outside click or ESC
document.addEventListener('click', function(e) {
  var sw = document.getElementById('active-customer-switcher');
  if (!sw || sw.style.display !== 'flex') return;
  var trigger = document.getElementById('active-customer-trigger');
  if (sw.contains(e.target)) return;
  if (trigger && trigger.contains(e.target)) return;
  _closeActiveCustomerSwitcher();
});
document.addEventListener('keydown', function(e) {
  if (e.key !== 'Escape') return;
  var sw = document.getElementById('active-customer-switcher');
  if (sw && sw.style.display === 'flex') {
    _closeActiveCustomerSwitcher();
    e.stopPropagation();  // prevent closeTopModal from firing
  }
}, true);

async function switchCustomer(customerId) {
  try {
    const d = await apiFetch('/api/customers/switch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({customer_id: customerId})
    });
    if (d && d.ok) {
      _scopeLoaded = false; _scopeSections = [];
      loadCustomers();
      loadStatus();
      showToast(t('toast_customer_switched', 'Kunde byttet'), 'success', 2000);
    }
  } catch(e) { showToast(t('err_customer_switching_failed').replace('{msg}', e.message), 'error'); }
}

async function deleteCustomer(customerId, name) {
  if (!await showTypedConfirm(
    name,
    t('dlg_confirm_delete_customer').replace('{name}', name),
    t('dlg_destructive_irreversible', 'Dette fjerner permanent alle audits, rapporter, credentials og konfigurasjon for denne kunden.')
  )) return;
  try {
    await apiFetch('/api/customers/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({customer_id: customerId})
    });
    loadCustomers();
  } catch(e) { showToast(t('status_error') + ': ' + e.message, 'error'); }
}

// ── Multi-customer dashboard overview ────────────────────────────────────────
let _overviewData = null;
let _overviewSortKey = 'risk_score';
let _overviewSortAsc = true;

// ── Dashboard Charts ─────────────────────────────────────────────────────────
var _dashChartInstances = {};
var _dashAutoRefresh = null;
var _dashAutoRefreshSec = 60;
var _dashAutoRefreshRemaining = 0;

function toggleDashAutoRefresh() {
  if (_dashAutoRefresh) { stopDashAutoRefresh(); return; }
  _dashAutoRefreshRemaining = _dashAutoRefreshSec;
  var btn = document.getElementById('dash-autorefresh-btn');
  var cd = document.getElementById('dash-autorefresh-countdown');
  if (btn) btn.style.color = 'var(--green)';
  if (cd) { cd.style.display = 'inline'; cd.textContent = _dashAutoRefreshRemaining + 's'; }
  _dashAutoRefresh = setInterval(function() {
    _dashAutoRefreshRemaining--;
    if (cd) cd.textContent = _dashAutoRefreshRemaining + 's';
    if (_dashAutoRefreshRemaining <= 0) {
      _dashAutoRefreshRemaining = _dashAutoRefreshSec;
      if (currentView === 'overview') loadOverview();
    }
  }, 1000);
  showToast(t('msg_auto_refresh_on','Auto-oppdatering aktivert (60s)'), 'success', 2000);
}
function toggleRowActions(btn) {
  // Close any other open menus
  document.querySelectorAll('.row-actions-menu').forEach(function(m) { m.style.display = 'none'; });
  var menu = btn.nextElementSibling;
  menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}
// Close row action menus on outside click
document.addEventListener('click', function(e) {
  if (!e.target.closest('.row-actions-wrap')) {
    document.querySelectorAll('.row-actions-menu').forEach(function(m) { m.style.display = 'none'; });
  }
});

async function quickSwitchAndAudit(customerId) {
  document.querySelectorAll('.row-actions-menu').forEach(function(m) { m.style.display = 'none'; });
  await apiFetch('/api/customers/switch', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer_id:customerId})});
  showView('home');
  setTimeout(startAudit, 300);
}
async function quickSwitchAndView(customerId, view) {
  document.querySelectorAll('.row-actions-menu').forEach(function(m) { m.style.display = 'none'; });
  await apiFetch('/api/customers/switch', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer_id:customerId})});
  showView(view);
}

function stopDashAutoRefresh() {
  if (_dashAutoRefresh) { clearInterval(_dashAutoRefresh); _dashAutoRefresh = null; }
  var btn = document.getElementById('dash-autorefresh-btn');
  var cd = document.getElementById('dash-autorefresh-countdown');
  if (btn) btn.style.color = '';
  if (cd) cd.style.display = 'none';
}
function _celebrateConfetti() {
  var colors = ['#3fb950','#4d9fb5','#d29922','#bc8cff','#58a6ff','#f85149'];
  for (var i = 0; i < 40; i++) {
    var el = document.createElement('div');
    el.className = 'confetti-piece';
    el.style.left = Math.random() * 100 + 'vw';
    el.style.background = colors[Math.floor(Math.random() * colors.length)];
    el.style.animationDelay = (Math.random() * 1.5) + 's';
    el.style.animationDuration = (2 + Math.random() * 2) + 's';
    el.style.width = (5 + Math.random() * 8) + 'px';
    el.style.height = (5 + Math.random() * 8) + 'px';
    document.body.appendChild(el);
    setTimeout(function(e){ e.remove(); }.bind(null, el), 5000);
  }
}

function _animateCountUp(el, target, suffix, duration) {
  if (!el || isNaN(target)) return;

  // The element already shows the true value; this only animates towards it.
  //
  // It used to be the other way round: the markup carried a literal 0 and the
  // truth lived in data-count, so the number a reader saw depended on an
  // animation finishing. It often did not. start was pinned to 0, so a
  // re-render — this view refreshes itself — dropped the figure back to zero
  // and raced the previous loop, and requestAnimationFrame is throttled in a
  // background tab, so switching away could leave a tile reading 0 over a
  // table listing one customer.
  //
  // Starting from what is on screen makes a re-render a no-op instead of a
  // reset, and the generation counter means the newest call is the only one
  // still writing.
  var start = parseFloat(String(el.textContent).replace(/[^0-9.-]/g, ''));
  if (isNaN(start)) start = 0;
  if (start === target) return;

  var generation = (el._countGeneration || 0) + 1;
  el._countGeneration = generation;

  var startTime = null;
  duration = duration || 800;
  function step(ts) {
    if (el._countGeneration !== generation) return;   // superseded
    if (!startTime) startTime = ts;
    var progress = Math.min((ts - startTime) / duration, 1);
    var eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    var current = Math.round(start + (target - start) * eased);
    el.textContent = current + (suffix || '');
    if (progress < 1) requestAnimationFrame(step);
    else el.textContent = target + (suffix || '');   // land exactly on it
  }
  requestAnimationFrame(step);
}

function _renderDashboardCharts(withMetrics) {
  if (typeof Chart === 'undefined') return;
  // Destroy previous instances
  Object.values(_dashChartInstances).forEach(c => c.destroy());
  _dashChartInstances = {};

  const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim();
  const gridColor = getComputedStyle(document.documentElement).getPropertyValue('--border').trim();

  // Risk score bar chart — sorted by risk
  const barCanvas = document.getElementById('chart-risk-bar');
  if (barCanvas && withMetrics.length > 0) {
    const sorted = [...withMetrics].sort((a, b) => (a.metrics.risk_score||0) - (b.metrics.risk_score||0));
    const labels = sorted.map(c => c.customer_name.length > 15 ? c.customer_name.substring(0,14)+'…' : c.customer_name);
    const scores = sorted.map(c => c.metrics.risk_score || 0);
    const colors = scores.map(s => s >= 80 ? '#3fb950' : s >= 60 ? '#4d9fb5' : s >= 40 ? '#d29922' : '#f85149');
    _dashChartInstances.bar = new Chart(barCanvas, {
      type: 'bar',
      data: { labels, datasets: [{ data: scores, backgroundColor: colors, borderRadius: 4, borderSkipped: false }] },
      options: {
        indexAxis: 'y',
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ctx.parsed.x + '/100' } } },
        scales: {
          x: { max: 100, grid: { color: gridColor }, ticks: { color: textColor, font: { size: 11 } } },
          y: { grid: { display: false }, ticks: { color: textColor, font: { size: 11 } } }
        }
      }
    });
  }

  // Grade distribution renders as a CSS stacked bar in renderOverview() now,
  // so there is no donut chart to draw here.
}

// Cached extra dashboard data (health scores + costs) for overview enrichment
var _overviewHealthMap = {};
var _overviewCostMap = {};

// ── Integration health strip (top of Dashboard) ─────────────────────────
// Shows configured / not-configured / recent-failure state for the main
// integrations in one horizontal strip. Fed by /api/settings (config
// presence) + /api/scheduler/tasks (last run + error). Click → /integrations.

async function loadIntegrationHealthStrip() {
  var widget = document.getElementById('integration-health-widget');
  if (!widget) return;
  var [settings, schedRes] = await Promise.all([
    apiFetch('/api/settings').catch(function() { return null; }),
    apiFetch('/api/scheduler/tasks').catch(function() { return null; }),
  ]);
  if (!settings) { widget.style.display = 'none'; return; }

  var tasks = {};
  if (schedRes && schedRes.tasks) {
    schedRes.tasks.forEach(function(t) { tasks[t.id || t.task_id || ''] = t; });
  }

  // Item spec: id (matches scheduler task id where applicable), label,
  // configured flag, optional extra label shown on hover/under the name.
  var items = [
    { key: 'gdap',         label: 'M365 (GDAP)', configured: !!settings.gdap_configured,
      detail: settings.gdap_customer_count ? (settings.gdap_customer_count + ' ' + t('lbl_customers_lc','kunder')) : '' },
    { key: 'fortigate',    label: 'FortiGate',   configured: !!settings.fortigate_configured,
      taskId: 'fortigate_backup' },
    { key: 'unifi',        label: 'UniFi',       configured: !!settings.unifi_site_manager_api_key_set },
    { key: 'itglue',       label: 'IT Glue',     configured: !!settings.itglue_api_key_set },
    { key: 'also',         label: 'ALSO Cloud',  configured: !!settings.also_password_set,
      taskId: 'also_price_refresh' },
    { key: 'uniweb',       label: 'Uniweb',      configured: !!settings.uniweb_password_set,
      taskId: 'uniweb_sync' },
    { key: 'tailscale',    label: 'Tailscale',   configured: !!settings.tailscale_api_key_set },
    { key: 'smtp',         label: 'E-post',      configured: !!(settings.smtp_server && settings.smtp_password_set) },
  ];

  function relTime(iso) {
    if (!iso) return '';
    try {
      var diff = (Date.now() - new Date(iso).getTime()) / 1000;
      if (diff < 60) return t('time_now');
      if (diff < 3600) return Math.round(diff / 60) + 'm';
      if (diff < 86400) return Math.round(diff / 3600) + 't';
      return Math.round(diff / 86400) + 'd';
    } catch(_) { return ''; }
  }

  var cards = items.map(function(item) {
    var task = item.taskId ? tasks[item.taskId] : null;
    var state = 'neutral';  // grey
    if (item.configured) {
      state = 'ok';
      if (task && task.consecutive_failures > 0) state = 'warn';
    }
    var color = {
      ok:      'var(--color-success)',
      warn:    'var(--color-warning)',
      neutral: 'var(--text-dim)',
    }[state];
    var detail = item.detail;
    if (!detail && task && task.last_run) {
      detail = t('lbl_last_run', 'Sist') + ' ' + relTime(task.last_run) + ' siden';
    }
    if (!item.configured) detail = t('lbl_not_configured', 'Ikke konfigurert');
    return '' +
      '<div class="integ-health-card" data-integ-key="' + esc(item.key) + '" style="flex:1;min-width:128px;padding:10px 12px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);cursor:pointer;display:flex;flex-direction:column;gap:3px;transition:border-color var(--duration-fast);" title="' + esc(item.label) + '">' +
        '<div style="display:flex;align-items:center;gap:6px;">' +
          '<span style="width:8px;height:8px;border-radius:50%;background:' + color + ';flex-shrink:0;"></span>' +
          '<span style="font-size:12px;font-weight:600;color:var(--text);">' + esc(item.label) + '</span>' +
        '</div>' +
        (detail ? '<div style="font-size:10px;color:var(--text-dim);">' + esc(detail) + '</div>' : '') +
      '</div>';
  });

  widget.innerHTML = '' +
    '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-2);">' +
      '<div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">' + esc(t('hdr_integration_health', 'Integrasjonsstatus')) + '</div>' +
      '<a href="#" onclick="showView(\'integrations\');return false;" style="font-size:var(--font-xs);color:var(--blue);text-decoration:none;">' + esc(t('lbl_manage', 'Administrer')) + ' &rarr;</a>' +
    '</div>' +
    '<div style="display:flex;gap:var(--space-3);flex-wrap:wrap;">' + cards.join('') + '</div>';

  widget.style.display = 'block';
}

// Delegated click → open Integrasjoner view
document.addEventListener('click', function(e) {
  var card = e.target.closest('#integration-health-widget .integ-health-card');
  if (!card) return;
  showView('integrations');
});

async function loadOverview() {
  const box = document.getElementById('overview-content');
  // Integration health strip — fire-and-forget, independent of the
  // customer grid load. Errors in /api/settings shouldn't delay or break
  // dashboard rendering.
  loadIntegrationHealthStrip().catch(function(e) { console.debug('integ strip failed:', e); });
  // Fetch overview, health-scores, and costs in parallel
  const [d, healthData, costData, trendData] = await Promise.all([
    apiFetch('/api/dashboard/overview'),
    apiFetch('/api/dashboard/health-scores').catch(function() { return null; }),
    apiFetch('/api/dashboard/costs').catch(function() { return null; }),
    apiFetch('/api/dashboard/trends').catch(function() { return null; }),
  ]);
  window._overviewTrends = (trendData && trendData.trends) ? trendData.trends : {};
  if (d) {
    // Build lookup maps for health and cost data
    _overviewHealthMap = {};
    if (healthData && healthData.scores) {
      healthData.scores.forEach(function(h) { _overviewHealthMap[h.customer_id] = h; });
    }
    _overviewCostMap = {};
    if (costData && costData.customers) {
      costData.customers.forEach(function(c) { _overviewCostMap[c.customer_id] = c; });
    }
    _overviewData = {customers: d.customers || [], active_id: d.active_id};
    renderOverview(_overviewData.customers, _overviewData.active_id);
    // Update footer stats
    var fs = document.getElementById('footer-stats');
    if (fs) {
      var tc = _overviewData.customers.length;
      var wm = _overviewData.customers.filter(function(c){return c.has_metrics}).length;
      var tw = _overviewData.customers.reduce(function(s,c){return s + (c.has_metrics && c.metrics.total_warns ? c.metrics.total_warns : 0)}, 0);
      fs.textContent = tc + ' ' + t('nav_customers').toLowerCase() + ' · ' + wm + ' audits · ' + tw + ' warns';
    }
  } else {
    box.innerHTML = '<div class="alert alert-error">' + t('err_could_not_load_dashboard') + '</div>';
  }
}

var _gradeFilter = '';
var _quickFilter = 'all';
function filterByGrade(grade) {
  if (_gradeFilter === grade) { _gradeFilter = ''; } // toggle off
  else { _gradeFilter = grade; }
  filterOverview();
  if (_gradeFilter) showToast(t('lbl_grade') + ': ' + _gradeFilter, 'info', 1500);
}

function filterOverview() {
  if (!_overviewData) return;
  const search = (document.getElementById('overview-search')?.value || '').toLowerCase();
  const filter = document.getElementById('overview-filter')?.value || 'all';
  var qf = window._quickFilter || 'all';
  let filtered = _overviewData.customers.filter(c => {
    if (search && !c.customer_name.toLowerCase().includes(search) && !(c.primary_domain||'').toLowerCase().includes(search)) return false;
    if (filter === 'has_m365' && !c.has_m365) return false;
    if (filter === 'has_fortigate' && !c.has_fortigate) return false;
    if (filter === 'needs_setup' && (c.has_m365 || c.has_fortigate || c.has_unifi)) return false;
    if (filter === 'mfa80' && (!c.has_metrics || c.metrics.mfa_coverage_pct === undefined || c.metrics.mfa_coverage_pct >= 80)) return false;
    if (filter === 'riskdf' && (!c.has_metrics || (c.metrics.risk_grade !== 'D' && c.metrics.risk_grade !== 'F'))) return false;
    if (filter === 'noaudit' && c.has_metrics) return false;
    if (filter === 'stale') {
      if (!c.last_audit) return true; // never audited = stale
      try { var _sd = new Date(c.last_audit.replace(/_/g,'T').substring(0,16)); if ((Date.now() - _sd.getTime()) / 86400000 <= 30) return false; } catch(e) {}
    }
    if (_gradeFilter && (!c.has_metrics || c.metrics.risk_grade !== _gradeFilter)) return false;
    // Quick filter: "Problemer" = health grade D/F
    if (qf === 'problems') {
      var hd = _overviewHealthMap[c.customer_id];
      if (!hd || (hd.grade !== 'D' && hd.grade !== 'F')) return false;
    }
    // Quick filter: "Utloper snart" = has expiring items (health breakdown has license/domain issues)
    if (qf === 'expiring') {
      var he = _overviewHealthMap[c.customer_id];
      if (!he) return false;
      var br = he.breakdown || {};
      var hasExpiring = (br.license_compliance && br.license_compliance.score < br.license_compliance.max)
        || (br.domain_health && br.domain_health.score < br.domain_health.max);
      if (!hasExpiring) return false;
    }
    // Time filter
    var timeFilter = (document.getElementById('overview-time-filter') || {}).value || 'all';
    if (timeFilter !== 'all' && c.last_audit) {
      try {
        var auditDate = new Date(c.last_audit.replace(/_/g,'T').substring(0,16));
        var daysAgo = Math.floor((Date.now() - auditDate.getTime()) / 86400000);
        if (daysAgo > parseInt(timeFilter)) return false;
      } catch(e) {}
    }
    return true;
  });
  renderOverview(filtered, _overviewData.active_id);

  // Show active filter badges
  var afEl = document.getElementById('overview-active-filters');
  if (afEl) {
    var badges = [];
    if (search) badges.push('<span style="background:var(--blue-dark);color:var(--blue);padding:3px 10px;border-radius:var(--radius-full);font-size:var(--font-xs);border:1px solid rgba(77,159,181,0.3);cursor:pointer;" onclick="document.getElementById(\'overview-search\').value=\'\';filterOverview();">&#10005; &quot;' + esc(search) + '&quot;</span>');
    if (filter !== 'all') {
      var fLabels = {has_m365:'M365', has_fortigate:'FortiGate', needs_setup:t('filter_needs_setup','Needs setup'), mfa80:'MFA < 80%', riskdf:t('filter_grade_df','Grade D/F'), noaudit:t('filter_no_audit'), stale:t('filter_stale_audit','Stale audit')};
      badges.push('<span style="background:var(--blue-dark);color:var(--blue);padding:3px 10px;border-radius:var(--radius-full);font-size:var(--font-xs);border:1px solid rgba(77,159,181,0.3);cursor:pointer;" onclick="document.getElementById(\'overview-filter\').value=\'all\';filterOverview();">&#10005; ' + (fLabels[filter]||filter) + '</span>');
    }
    if (_gradeFilter) badges.push('<span style="background:var(--blue-dark);color:var(--blue);padding:3px 10px;border-radius:var(--radius-full);font-size:var(--font-xs);border:1px solid rgba(77,159,181,0.3);cursor:pointer;" onclick="_gradeFilter=\'\';filterOverview();">&#10005; ' + t('lbl_grade') + ': ' + _gradeFilter + '</span>');
    if (badges.length > 0) {
      badges.push('<span style="font-size:var(--font-xs);color:var(--text-dim);cursor:pointer;text-decoration:underline;" onclick="document.getElementById(\'overview-search\').value=\'\';document.getElementById(\'overview-filter\').value=\'all\';_gradeFilter=\'\';filterOverview();">' + t('btn_clear_all','Clear all') + '</span>');
      afEl.style.display = 'flex';
      afEl.innerHTML = badges.join('');
    } else {
      afEl.style.display = 'none';
      afEl.innerHTML = '';
    }
  }
}

function sortOverview(key) {
  if (_overviewSortKey === key) _overviewSortAsc = !_overviewSortAsc;
  else { _overviewSortKey = key; _overviewSortAsc = key === 'customer_name'; }
  filterOverview();
}

function renderOverview(customers, activeId) {
  const box = document.getElementById('overview-content');

  // Sort
  const sk = _overviewSortKey;
  customers.sort((a, b) => {
    let va = sk === 'customer_name' ? a.customer_name : (a.has_metrics ? (a.metrics[sk] ?? -1) : -1);
    let vb = sk === 'customer_name' ? b.customer_name : (b.has_metrics ? (b.metrics[sk] ?? -1) : -1);
    if (typeof va === 'string' || typeof vb === 'string') { va = String(va ?? '').toLowerCase(); vb = String(vb ?? '').toLowerCase(); }
    const cmp = va < vb ? -1 : va > vb ? 1 : 0;
    return _overviewSortAsc ? cmp : -cmp;
  });

  // Collect all tags from unfiltered data for the dropdown
  var allTags = [];
  (_overviewData ? _overviewData.customers : customers).forEach(function(c){(c.tags||[]).forEach(function(t){if(allTags.indexOf(t)===-1)allTags.push(t)})});
  var selectedTag = (document.getElementById('overview-tag-filter')||{}).value || '';
  if (selectedTag) customers = customers.filter(function(c){return (c.tags||[]).indexOf(selectedTag) !== -1});

  const total = customers.length;
  const withMetrics = customers.filter(c => c.has_metrics);
  const avgRisk = withMetrics.length > 0
    ? (withMetrics.reduce((s, c) => s + (c.metrics.risk_score || 0), 0) / withMetrics.length).toFixed(0)
    : '-';
  // One definition of "needs following up", used for the KPI tile, the
  // attention strip and the trend delta below, so they can't drift apart.
  const _needsAttn = m => !!m && (m.risk_grade === 'D' || m.risk_grade === 'F' || (m.mfa_coverage_pct !== undefined && m.mfa_coverage_pct < 80));
  const needsAttention = withMetrics.filter(c => _needsAttn(c.metrics)).length;
  const avgMfa = withMetrics.length > 0
    ? (withMetrics.reduce((s, c) => s + (c.metrics.mfa_coverage_pct || 0), 0) / withMetrics.length).toFixed(0)
    : '-';
  const now30d = new Date(); now30d.setDate(now30d.getDate() - 30);
  const staleCount = customers.filter(c => {
    if (!c.last_audit) return true;
    try { return new Date(c.last_audit.replace(/_/g,'T').substring(0,16)) < now30d; } catch(e) { return true; }
  }).length;

  // ── KPI trend chips ────────────────────────────────────────────────────
  // Deltas are measured over the customers that have BOTH a current and a
  // previous audit, so a customer audited for the first time this period
  // shows up as neither an improvement nor a regression. Customer count and
  // stale-audit count have no previous snapshot to compare against, so those
  // two tiles carry no chip rather than an invented one.
  const paired = withMetrics.filter(c => c.prev_metrics);
  const _avgDelta = key => {
    if (!paired.length) return null;
    const cur = paired.reduce((s, c) => s + (c.metrics[key] || 0), 0) / paired.length;
    const prv = paired.reduce((s, c) => s + (c.prev_metrics[key] || 0), 0) / paired.length;
    return cur - prv;
  };
  const riskDelta = _avgDelta('risk_score');
  const mfaDelta = _avgDelta('mfa_coverage_pct');
  const attnDelta = paired.length
    ? paired.filter(c => _needsAttn(c.metrics)).length - paired.filter(c => _needsAttn(c.prev_metrics)).length
    : null;

  // Renders nothing for a null or sub-unit delta, so "no change" stays quiet.
  function trendChip(delta, higherIsBetter, suffix) {
    if (delta === null || delta === undefined) return '';
    const d = Math.round(delta);
    if (d === 0) return '';
    // Written as an equality rather than a ternary: the i18n prose detector
    // reads `? d > 0 : d < 0` as a baked-in string.
    const good = higherIsBetter === (d > 0);
    const txt = (d > 0 ? '+' : '−') + Math.abs(d) + (suffix || '');
    return '<span class="kpi-trend" style="color:' + (good ? 'var(--green)' : 'var(--red)') + ';" title="'
      + esc(t('tip_since_previous_audit', 'Endring siden forrige audit')) + '">' + esc(txt) + '</span>';
  }

  const gradeColor = g => ({A:'#3fb950', B:'#4d9fb5', C:'#d29922', D:'#f85149', F:'#8b0000'}[g] || 'var(--text-muted)');

  function fmtDate(d) {
    if (!d) return '-';
    const dm = d.match(/^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})$/);
    if (dm) return `${dm[3]}.${dm[2]}.${dm[1]}`;
    return d.substring(0, 10);
  }

  var tagFilterHtml = '<select id="overview-tag-filter" onchange="filterOverview()" style="padding:4px 10px;border:1px solid var(--border);border-radius:6px;font-size:12px;background:var(--bg);color:var(--text);margin-left:12px;"><option value="">' + t('alle_tags') + '</option>';
  allTags.forEach(function(t){tagFilterHtml += '<option value="'+esc(t)+'"'+(selectedTag===t?' selected':'')+'>'+esc(t)+'</option>'});
  tagFilterHtml += '</select>';

  // Render search/filter bar only once — check if it exists
  var searchBar = document.getElementById('overview-search-bar');
  if (!searchBar) {
    var searchVal = '';
    var filterVal = 'all';
    box.innerHTML = `
    <div id="overview-summary"></div>
    <div id="overview-search-bar">
      <div class="dash-toolbar">
        <input id="overview-search" type="text" class="field-input" placeholder="${t('lbl_search_customer')}" style="width:220px;padding:7px 10px;font-size:13px;" oninput="filterOverview()">
        <select id="overview-filter" class="field-input" style="width:auto;padding:7px 10px;font-size:13px;" onchange="filterOverview()">
          <option value="all">${t('filter_all')}</option>
          <option value="has_m365">${t('filter_has_m365','Has M365')}</option>
          <option value="has_fortigate">${t('filter_has_fortigate','Has FortiGate')}</option>
          <option value="needs_setup">${t('filter_needs_setup','Needs setup')}</option>
          <option value="mfa80">${t('filter_mfa_80')}</option>
          <option value="riskdf">${t('filter_risk_df')}</option>
          <option value="noaudit">${t('filter_no_audit')}</option>
          <option value="stale">${t('filter_stale_audit','Stale audit')}</option>
        </select>
        <select id="overview-time-filter" class="field-input" style="width:auto;padding:7px 10px;font-size:13px;" onchange="filterOverview()">
          <option value="all">${t('filter_all_time','All time')}</option>
          <option value="7">${t('filter_last_7d','Last 7 days')}</option>
          <option value="30">${t('filter_last_30d','Last 30 days')}</option>
          <option value="90">${t('filter_last_90d','Last 90 days')}</option>
        </select>
        ${tagFilterHtml}
        <span style="width:1px;height:22px;background:var(--border);margin:0 4px;"></span>
        <button class="qpill" id="qp-all" onclick="_quickFilter='all';filterOverview();">${t('filter_quick_all','Alle')}</button>
        <button class="qpill" id="qp-problems" onclick="_quickFilter='problems';filterOverview();">${t('filter_quick_problems','Problemer')}</button>
        <button class="qpill" id="qp-expiring" onclick="_quickFilter='expiring';filterOverview();">${t('filter_quick_expiring','Utløper snart')}</button>
        <div style="flex:1;"></div>
        <button class="btn btn-primary btn-sm" id="bulk-audit-btn" onclick="startBulkAudit()" style="font-size:12px;">${t('btn_run_all_customers')}</button>
        <div class="colpick" id="overview-colpick">
          <button class="dash-tab-tool" onclick="toggleOverviewColpick(event)">${t('lbl_columns','Kolonner')} &#9662;</button>
          <div class="colpick-menu" id="overview-colpick-menu">
            <label><input type="checkbox" data-col="health" onchange="toggleOverviewColumn('health',this.checked)"> ${t('lbl_health','Helse')}</label>
            <label><input type="checkbox" data-col="users" onchange="toggleOverviewColumn('users',this.checked)"> ${t('lbl_users','Brukere')}</label>
            <label><input type="checkbox" data-col="trend" onchange="toggleOverviewColumn('trend',this.checked)"> ${t('lbl_trend','Trend')}</label>
            <label><input type="checkbox" data-col="tags" onchange="toggleOverviewColumn('tags',this.checked)"> ${t('lbl_tags','Tags')}</label>
          </div>
        </div>
      </div>
      <div id="bulk-audit-panel" style="display:none;"></div>
    </div>
    <div id="overview-active-filters" style="display:none;margin-bottom:var(--space-3);display:flex;gap:var(--space-2);flex-wrap:wrap;align-items:center;"></div>
    <div id="overview-table-content"></div>`;
  } else {
    searchVal = document.getElementById('overview-search')?.value || '';
    filterVal = document.getElementById('overview-filter')?.value || 'all';
  }

  var tableBox = document.getElementById('overview-table-content') || box;

  // Summary block (attention strip + KPI cards) goes into a persistent
  // container ABOVE the toolbar, so the mock's order holds — attention → KPI →
  // toolbar → table → charts — while the search input keeps focus/value.
  var summaryHtml = '';
  if (needsAttention > 0) {
    var _attnGradeD = withMetrics.filter(function(c){ return c.metrics.risk_grade === 'D' || c.metrics.risk_grade === 'F'; }).length;
    var _attnLowMfa = withMetrics.filter(function(c){ return c.metrics.mfa_coverage_pct !== undefined && c.metrics.mfa_coverage_pct < 80; }).length;
    var _attnNoAudit = customers.filter(function(c){ return !c.last_audit; }).length;
    var _attnParts = [];
    if (_attnGradeD) _attnParts.push(_attnGradeD + ' ' + t('attn_grade_d', 'med grade D'));
    if (_attnLowMfa) _attnParts.push(_attnLowMfa + ' ' + t('attn_low_mfa', 'med MFA < 80 %'));
    if (_attnNoAudit) _attnParts.push(_attnNoAudit + ' ' + t('attn_no_audit', 'uten audit'));
    summaryHtml += `
      <div class="attn-strip">
        <span class="attn-title">${needsAttention} ${t('lbl_needs_followup', 'kunder trenger oppfølging')}</span>
        <span class="attn-detail">${esc(_attnParts.join(' · '))}</span>
        <div style="flex:1;"></div>
        <button class="attn-action" onclick="_quickFilter='problems';filterOverview();">${t('btn_show_only_these', 'Vis kun disse')}</button>
      </div>`;
  }
  summaryHtml += `
    <div class="kpi-row">
      <div class="kpi-card"><div class="kpi-label">${t('lbl_total_customers')}</div><div class="kpi-value-row"><span class="kpi-value kpi-num" data-count="${total}" style="color:var(--text);">${total}</span></div></div>
      <div class="kpi-card"><div class="kpi-label">${t('lbl_avg_risk_score')}</div><div class="kpi-value-row"><span class="kpi-value kpi-num" data-count="${avgRisk !== '-' ? avgRisk : ''}" style="color:${avgRisk !== '-' && avgRisk < 50 ? 'var(--red)' : avgRisk !== '-' && avgRisk < 70 ? 'var(--orange)' : 'var(--green)'};">${avgRisk === '-' ? '-' : avgRisk}</span>${trendChip(riskDelta, true)}</div></div>
      <div class="kpi-card"><div class="kpi-label">${t('lbl_avg_mfa','MFA-dekning')}</div><div class="kpi-value-row"><span class="kpi-value kpi-num" data-count="${avgMfa !== '-' ? avgMfa : ''}" data-suffix="%" style="color:${avgMfa !== '-' && avgMfa < 80 ? 'var(--red)' : avgMfa !== '-' && avgMfa < 95 ? 'var(--orange)' : 'var(--green)'};">${avgMfa === '-' ? '-' : avgMfa + '%'}</span>${trendChip(mfaDelta, true, ' pp')}</div></div>
      <div class="kpi-card"><div class="kpi-label">${t('lbl_needs_attention')}</div><div class="kpi-value-row"><span class="kpi-value kpi-num" data-count="${needsAttention}" style="color:${needsAttention > 0 ? 'var(--red)' : 'var(--green)'};">${needsAttention}</span>${trendChip(attnDelta, false)}</div></div>
      <div class="kpi-card"><div class="kpi-label">${t('lbl_stale_30d','Utdatert >30d')}</div><div class="kpi-value-row"><span class="kpi-value kpi-num" data-count="${staleCount}" style="color:${staleCount > 0 ? 'var(--orange)' : 'var(--green)'};">${staleCount}</span></div></div>
    </div>`;
  var _sumBox = document.getElementById('overview-summary');
  if (_sumBox) _sumBox.innerHTML = summaryHtml;

  let html = '';

  // Build the grade-distribution stacked bar (charts sit below the table now).
  setTimeout(function() {
    var grades = {A:0, B:0, C:0, D:0, F:0};
    withMetrics.forEach(function(c) { var g = c.metrics.risk_grade; if (grades[g] !== undefined) grades[g]++; });
    var gc = {A:'var(--green)',B:'var(--blue)',C:'var(--orange)',D:'var(--red)',F:'#8b0000'};
    var stack = document.getElementById('grade-stack');
    if (stack) {
      stack.innerHTML = Object.keys(gc).map(function(k){ return grades[k] > 0 ? '<span style="flex:'+grades[k]+';background:'+gc[k]+';"></span>' : ''; }).join('') || '<span style="flex:1;background:var(--border);"></span>';
    }
    var legend = document.getElementById('grade-legend');
    if (legend) {
      legend.innerHTML = Object.keys(gc).filter(function(k){return grades[k]>0;}).map(function(k){ return '<span><b style="color:'+gc[k]+';">'+k+'</b> '+grades[k]+'</span>'; }).join('');
    }
  }, 60);

  // Render charts after DOM update
  setTimeout(() => {
    _renderDashboardCharts(withMetrics);
    // Animate KPI numbers
    document.querySelectorAll('.kpi-num').forEach(function(el) {
      var val = parseFloat(el.getAttribute('data-count'));
      var suffix = el.getAttribute('data-suffix') || '';
      if (!isNaN(val)) _animateCountUp(el, val, suffix, 900);
    });
  }, 50);

  if (customers.length === 0) {
    html += `
      <div class="card" style="text-align:center;padding:var(--space-16) var(--space-6);">
        <div style="font-size:var(--font-lg);font-weight:600;color:var(--text);margin-bottom:var(--space-2);">${t('msg_no_customers_registered')}</div>
        <div style="font-size:var(--font-sm);color:var(--text-dim);margin-bottom:var(--space-6);max-width:360px;margin-left:auto;margin-right:auto;">${t('msg_go_to_customers')}</div>
        <button class="btn btn-primary btn-lg" onclick="showView('customers')">${t('btn_add_first_customer')}</button>
      </div>`;
  } else {
    html += `
    <div class="card overview-table-wrap" style="padding:0;overflow:auto;max-height:70vh;background:var(--bg-panel);">
      <table class="slim-table customer-overview-table">
        <thead>
          <tr>
            <th class="sortable" onclick="sortOverview('customer_name')">${t('lbl_customer')} ${_overviewSortKey==='customer_name'?(_overviewSortAsc?'\u25B2':'\u25BC'):''}</th>
            <th>${t('lbl_status','Status')}</th>
            <th class="num sortable" onclick="sortOverview('risk_score')">${t('lbl_risk')} ${_overviewSortKey==='risk_score'?(_overviewSortAsc?'\u25B2':'\u25BC'):''}</th>
            <th class="num sortable" onclick="sortOverview('mfa_coverage_pct')">MFA ${_overviewSortKey==='mfa_coverage_pct'?(_overviewSortAsc?'\u25B2':'\u25BC'):''}</th>
            <th class="num sortable" onclick="sortOverview('secure_score_pct')">${t('lbl_secure_score','Secure score')} ${_overviewSortKey==='secure_score_pct'?(_overviewSortAsc?'\u25B2':'\u25BC'):''}</th>
            <th class="num">MRR</th>
            <th>${t('lbl_last_audit')}</th>
            <th class="col-opt col-hidden" data-optcol="health" title="${t('tip_health_grade','Health grade (A-F) across all integrations')}">${t('lbl_health','Helse')}</th>
            <th class="num col-opt col-hidden sortable" data-optcol="users" onclick="sortOverview('total_users')">${t('lbl_users','Brukere')}</th>
            <th class="col-opt col-hidden" data-optcol="trend">${t('lbl_trend','Trend')}</th>
            <th class="col-opt col-hidden" data-optcol="tags">${t('lbl_tags','Tags')}</th>
            <th style="width:40px;"></th>
          </tr>
        </thead>
        <tbody>`;

    function deltaHtml(cur, prev, key, higherIsBetter) {
      if (prev === undefined || prev === null || cur === undefined || cur === null) return '';
      var cv = typeof cur === 'object' ? cur[key] : cur;
      var pv = typeof prev === 'object' ? prev[key] : prev;
      if (cv === undefined || pv === undefined || cv === pv) return '';
      var diff = cv - pv;
      var isGood = higherIsBetter ? diff > 0 : diff < 0;
      var arrow = diff > 0 ? '&#9650;' : '&#9660;';
      var color = isGood ? 'var(--green)' : 'var(--red)';
      return '<span style="font-size:9px;color:'+color+';margin-left:3px;" title="'+( diff > 0 ? '+' : '')+diff.toFixed(0)+'">' + arrow + '</span>';
    }

    // Pagination
    var _pageSize = 25;
    var _totalPages = Math.ceil(customers.length / _pageSize);
    if (!window._dashPage || window._dashPage > _totalPages) window._dashPage = 1;
    var _startIdx = (window._dashPage - 1) * _pageSize;
    var _pagedCustomers = customers.slice(_startIdx, _startIdx + _pageSize);

    for (const c of _pagedCustomers) {
      const m = c.metrics || {};
      const pm = c.prev_metrics || {};
      const hasM = c.has_metrics;
      const hasPrev = !!c.prev_metrics;
      const grade = hasM ? (m.risk_grade || '-') : '-';
      const score = hasM ? (m.risk_score !== undefined ? m.risk_score : '-') : '-';
      const mfa = hasM && metricPct(m.mfa_coverage_pct) !== null ? metricPct(m.mfa_coverage_pct) + '%' : '-';
      const ss = hasM && metricPct(m.secure_score_pct) !== null ? metricPct(m.secure_score_pct) + '%' : '-';
      const users = hasM && m.total_users !== undefined ? m.total_users : '-';
      const lastAudit = fmtDate(c.last_audit);
      const mfaColor = !hasM || m.mfa_coverage_pct === undefined ? 'var(--text-muted)' : m.mfa_coverage_pct >= 95 ? 'var(--green)' : m.mfa_coverage_pct >= 80 ? 'var(--orange)' : 'var(--red)';
      const ssColor = !hasM || m.secure_score_pct === undefined ? 'var(--text-muted)' : m.secure_score_pct >= 75 ? 'var(--green)' : m.secure_score_pct >= 50 ? 'var(--orange)' : 'var(--red)';
      const activeBadge = c.is_active ? ' <span style="background:var(--blue);color:#fff;padding:1px 6px;border-radius:10px;font-size:10px;font-weight:600;vertical-align:middle;">' + t('status_active') + '</span>' : '';

      // Health score from enriched data
      const _hd = _overviewHealthMap[c.customer_id] || {};
      const healthGrade = _hd.grade || '-';
      const healthScore = _hd.total_score !== undefined ? _hd.total_score : '-';
      const healthColor = {A:'#3fb950',B:'#4d9fb5',C:'#d29922',D:'#f85149',F:'#8b0000'}[healthGrade] || 'var(--text-muted)';

      // MRR from cost data
      const _cd = _overviewCostMap[c.customer_id] || {};
      const mrrVal = _cd.total_monthly || 0;
      const mrrStr = mrrVal > 0 ? mrrVal.toLocaleString('nb-NO', {minimumFractionDigits:0, maximumFractionDigits:0}) + ' kr' : '-';

      // Grade → semantic colour var + derived status pill (frame 1b). The
      // -deep variant is the label colour: it sits on a 12% tint of its own
      // hue, which light theme has to compensate for to stay above WCAG AA.
      const _gv = {A:'var(--green)',B:'var(--blue)',C:'var(--orange)',D:'var(--red)',F:'var(--red)'}[grade] || 'var(--text-muted)';
      const _gvd = {A:'var(--green-deep)',B:'var(--blue-deep)',C:'var(--orange-deep)',D:'var(--red-deep)',F:'var(--red-deep)'}[grade] || 'var(--text-muted)';
      let _stLabel, _stColor, _stDeep;
      if (grade === 'D' || grade === 'F') { _stLabel = t('status_needs_followup','Trenger oppfølging'); _stColor = 'var(--red)'; _stDeep = 'var(--red-deep)'; }
      else if (hasM && m.total_warns > 0) { _stLabel = t('status_watch','Følg med'); _stColor = 'var(--orange)'; _stDeep = 'var(--orange-deep)'; }
      else if (hasM) { _stLabel = 'OK'; _stColor = 'var(--green)'; _stDeep = 'var(--green-deep)'; }
      else { _stLabel = '—'; _stColor = 'var(--text-dim)'; _stDeep = 'var(--text-muted)'; }
      const _stBg = hasM ? `color-mix(in srgb, ${_stColor} 12%, transparent)` : 'transparent';
      const _domBadges = `${c.has_m365 ? ' <span style="background:var(--blue);color:#fff;padding:0 4px;border-radius:3px;font-size:9px;font-weight:600;font-family:sans-serif;" title="M365 configured">M365</span>' : ''}${c.has_fortigate ? ' <span style="background:#e8590c;color:#fff;padding:0 4px;border-radius:3px;font-size:9px;font-weight:600;font-family:sans-serif;" title="FortiGate configured">FG</span>' : ''}${c.has_unifi ? ' <span style="background:#06b6d4;color:#fff;padding:0 4px;border-radius:3px;font-size:9px;font-weight:600;font-family:sans-serif;" title="UniFi configured">UF</span>' : ''}${!c.has_m365 && !c.has_fortigate && !c.has_unifi ? ' <span style="background:var(--text-dim);color:#fff;padding:0 4px;border-radius:3px;font-size:9px;font-weight:600;font-family:sans-serif;" title="'+t('filter_needs_setup','Needs setup')+'">?</span>' : ''}`;
      const _warnNote = `${hasM && m.total_warns > 0 ? '<div style="font-size:10px;color:var(--orange);margin-top:2px;">' + m.total_warns + ' ' + t('lbl_warnings','warnings') + '</div>' : ''}${(() => { if (!c.last_audit) return '<div style="font-size:10px;color:var(--text-dim);margin-top:1px;">'+t('lbl_never_audited','Never audited')+'</div>'; try { var _ad = new Date(c.last_audit.replace(/_/g,'T').substring(0,16)); var _da = Math.floor((Date.now()-_ad.getTime())/86400000); if (_da > 30) return '<div style="font-size:10px;color:var(--orange);margin-top:1px;">'+_da+'d '+t('lbl_since_audit','since audit')+'</div>'; } catch(e){} return ''; })()}`;

      html += `
          <tr onclick="overviewSelectCustomer('${esc(c.customer_id)}')"
              ondblclick="event.preventDefault();quickSwitchAndAudit('${esc(c.customer_id)}')"
              title="${t('tip_click_detail_dblclick_audit','Click: details · Double-click: run audit')}">
            <td>
              <div class="cust-cell">
                <span class="grade-tile" style="color:${_gvd};background:color-mix(in srgb, ${_gv} 12%, transparent);border-color:color-mix(in srgb, ${_gv} 40%, transparent);" onclick="event.stopPropagation();filterByGrade('${grade}')" title="${t('tip_click_filter_grade','Click to filter by grade')}">${grade}</span>
                <span style="min-width:0;">
                  <span class="cname">${esc(c.customer_name)}${activeBadge}</span>
                  <span class="cdom">${esc(c.primary_domain || '')}${_domBadges}</span>
                  ${_warnNote}
                </span>
              </div>
            </td>
            <td><span class="status-pill" style="color:${_stDeep};background:${_stBg};">${_stLabel}</span></td>
            <td class="num">${score}${hasPrev ? deltaHtml(m, pm, 'risk_score', true) : ''}</td>
            <td class="num" style="color:${mfaColor};">${mfa}${hasPrev ? deltaHtml(m, pm, 'mfa_coverage_pct', true) : ''}</td>
            <td class="num" style="color:${ssColor};">${ss}${hasPrev ? deltaHtml(m, pm, 'secure_score_pct', true) : ''}</td>
            <td class="num" style="color:${mrrVal > 0 ? 'var(--text-muted)' : 'var(--text-dim)'};font-weight:${mrrVal > 0 ? '600' : '400'};">${mrrStr}</td>
            <td style="color:var(--text-muted);font-size:12px;white-space:nowrap;">${lastAudit}</td>
            <td class="col-opt col-hidden" data-optcol="health" style="text-align:center;">
              <span onclick="event.stopPropagation();showView('overview');setTimeout(function(){var dt=document.querySelector('[data-dash-tab=health]');if(dt)dt.click();},200);" style="display:inline-block;width:26px;height:26px;line-height:26px;border-radius:50%;font-weight:700;font-size:12px;color:#fff;background:${healthColor};cursor:pointer;" title="${t('lbl_health','Helse')}: ${healthGrade} (${healthScore}/100)">${healthGrade}</span>
            </td>
            <td class="num col-opt col-hidden" data-optcol="users">${users}</td>
            <td class="col-opt col-hidden" data-optcol="trend" style="text-align:center;"><span id="spark-${esc(c.customer_id || c._id || '')}" style="display:inline-block;width:72px;height:24px;"></span></td>
            <td class="col-opt col-hidden" data-optcol="tags">${tagPillsHtml(c.tags || [])}</td>
            <td style="text-align:center;">
              <div style="position:relative;display:inline-block;" class="row-actions-wrap">
                <button onclick="event.stopPropagation();toggleRowActions(this)" style="background:none;border:none;cursor:pointer;font-size:18px;color:var(--text-dim);padding:2px 6px;border-radius:var(--radius-sm);transition:background var(--duration-fast);" onmouseover="this.style.background='rgba(255,255,255,0.06)'" onmouseout="this.style.background=''">&#8943;</button>
                <div class="row-actions-menu" style="display:none;position:absolute;right:0;top:100%;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:var(--space-1) 0;min-width:180px;box-shadow:var(--shadow-lg);z-index:50;animation:dropdown-in var(--duration-fast) var(--ease-out);">
                  <button onclick="event.stopPropagation();overviewSelectCustomer('${esc(c.customer_id)}')" style="display:flex;align-items:center;gap:var(--space-2);width:100%;padding:8px 14px;background:none;border:none;color:var(--text);font-size:13px;text-align:left;cursor:pointer;transition:background 0.1s;" onmouseover="this.style.background='rgba(77,159,181,0.1)'" onmouseout="this.style.background=''">${t('lbl_details')}</button>
                  <button onclick="event.stopPropagation();quickSwitchAndAudit('${esc(c.customer_id)}')" style="display:flex;align-items:center;gap:var(--space-2);width:100%;padding:8px 14px;background:none;border:none;color:var(--text);font-size:13px;text-align:left;cursor:pointer;transition:background 0.1s;" onmouseover="this.style.background='rgba(77,159,181,0.1)'" onmouseout="this.style.background=''">${t('btn_run_audit')}</button>
                  <button onclick="event.stopPropagation();quickSwitchAndView('${esc(c.customer_id)}','history')" style="display:flex;align-items:center;gap:var(--space-2);width:100%;padding:8px 14px;background:none;border:none;color:var(--text);font-size:13px;text-align:left;cursor:pointer;transition:background 0.1s;" onmouseover="this.style.background='rgba(77,159,181,0.1)'" onmouseout="this.style.background=''">${t('nav_history')}</button>
                  <button onclick="event.stopPropagation();window.open('/api/reports/customer-summary/${esc(c.customer_id)}','_blank')" style="display:flex;align-items:center;gap:var(--space-2);width:100%;padding:8px 14px;background:none;border:none;color:var(--text);font-size:13px;text-align:left;cursor:pointer;transition:background 0.1s;" onmouseover="this.style.background='rgba(77,159,181,0.1)'" onmouseout="this.style.background=''">${t('btn_generate_report')}</button>
                  <div style="border-top:1px solid var(--border);margin:var(--space-1) 0;"></div>
                  <button onclick="event.stopPropagation();deleteCustomer('${esc(c.customer_id)}','${esc(c.customer_name)}')" style="display:flex;align-items:center;gap:var(--space-2);width:100%;padding:8px 14px;background:none;border:none;color:var(--red);font-size:13px;text-align:left;cursor:pointer;transition:background 0.1s;" onmouseover="this.style.background='rgba(248,81,73,0.08)'" onmouseout="this.style.background=''">${t('btn_delete')}</button>
                </div>
              </div>
            </td>
          </tr>`;
    }

    html += `
        </tbody>
      </table>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:20px;">
      <div class="card" style="background:var(--bg-panel);padding:16px;">
        <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:10px;">${t('lbl_risk_distribution')}</div>
        <div style="position:relative;height:120px;"><canvas id="chart-risk-bar"></canvas></div>
      </div>
      <div class="card" style="background:var(--bg-panel);padding:16px;">
        <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:10px;">${t('lbl_grade_distribution')}</div>
        <div class="grade-stack" id="grade-stack"></div>
        <div class="grade-legend" id="grade-legend"></div>
      </div>
    </div>`;
  }

  // Pagination controls
  if (_totalPages > 1) {
    html += '<div style="display:flex;align-items:center;justify-content:center;gap:var(--space-3);padding:var(--space-4) 0;font-size:var(--font-sm);">'
      + '<button class="btn btn-ghost btn-sm" onclick="window._dashPage=Math.max(1,window._dashPage-1);filterOverview()" ' + (window._dashPage <= 1 ? 'disabled' : '') + '>&laquo; ' + t('btn_prev','Prev') + '</button>'
      + '<span style="color:var(--text-muted);">' + window._dashPage + ' / ' + _totalPages + '</span>'
      + '<button class="btn btn-ghost btn-sm" onclick="window._dashPage=Math.min('+_totalPages+',window._dashPage+1);filterOverview()" ' + (window._dashPage >= _totalPages ? 'disabled' : '') + '>' + t('btn_next','Next') + ' &raquo;</button>'
      + '</div>';
  }

  tableBox.innerHTML = html;

  // Apply saved column-visibility prefs, refresh the quick-filter pills,
  // and stamp "Oppdatert HH:MM" in the tab bar.
  applyOverviewColumnPrefs();
  _updateOverviewQuickPills();
  var _updT = document.getElementById('dash-updated-time');
  if (_updT) {
    _updT.textContent = new Date().toLocaleTimeString('no-NO', {hour:'2-digit', minute:'2-digit'});
    var _updW = document.getElementById('dash-updated-wrap');
    if (_updW) _updW.style.display = '';
  }

  // Make the overview table sortable
  var overviewTable = tableBox.querySelector('table');
  if (overviewTable) makeSortable(overviewTable);

  // Load sparkline trend data
  _loadSparklines();
}

// ── Overview column picker + quick-pill state (frame 1b) ─────────────────────
function _overviewColPrefs() {
  try { return JSON.parse(localStorage.getItem('sybr_overview_cols') || '{}') || {}; } catch (e) { return {}; }
}
function applyOverviewColumnPrefs() {
  var prefs = _overviewColPrefs();
  ['health', 'users', 'trend', 'tags'].forEach(function(col) {
    var show = !!prefs[col];
    document.querySelectorAll('[data-optcol="' + col + '"]').forEach(function(el) { el.classList.toggle('col-hidden', !show); });
    var cb = document.querySelector('#overview-colpick-menu input[data-col="' + col + '"]');
    if (cb) cb.checked = show;
  });
}
function toggleOverviewColumn(col, show) {
  var prefs = _overviewColPrefs();
  prefs[col] = !!show;
  try { localStorage.setItem('sybr_overview_cols', JSON.stringify(prefs)); } catch (e) { /* private mode */ }
  document.querySelectorAll('[data-optcol="' + col + '"]').forEach(function(el) { el.classList.toggle('col-hidden', !show); });
}
function toggleOverviewColpick(e) {
  if (e) e.stopPropagation();
  var menu = document.getElementById('overview-colpick-menu');
  if (!menu) return;
  if (menu.classList.toggle('open')) {
    setTimeout(function() { document.addEventListener('click', _closeOverviewColpickOutside); }, 0);
  } else {
    document.removeEventListener('click', _closeOverviewColpickOutside);
  }
}
function _closeOverviewColpickOutside(e) {
  var wrap = document.getElementById('overview-colpick');
  if (wrap && !wrap.contains(e.target)) {
    var menu = document.getElementById('overview-colpick-menu');
    if (menu) menu.classList.remove('open');
    document.removeEventListener('click', _closeOverviewColpickOutside);
  }
}
function _updateOverviewQuickPills() {
  var qf = window._quickFilter || 'all';
  [['qp-all', 'all'], ['qp-problems', 'problems'], ['qp-expiring', 'expiring']].forEach(function(pair) {
    var el = document.getElementById(pair[0]);
    if (el) el.classList.toggle('active', qf === pair[1]);
  });
}

async function _loadSparklines() {
  try {
    // Use pre-loaded trend data from /api/dashboard/trends (loaded in parallel with overview)
    var byCustomer = window._overviewTrends || {};
    // If no pre-loaded trends, try fetching
    if (!Object.keys(byCustomer).length) {
      var d = await apiFetch('/api/dashboard/trends');
      if (d && d.trends) byCustomer = d.trends;
    }
    if (!Object.keys(byCustomer).length) return;
    // Convert trend objects to score arrays
    var scoreMap = {};
    Object.keys(byCustomer).forEach(function(cid) {
      var points = byCustomer[cid];
      if (Array.isArray(points)) {
        scoreMap[cid] = points.map(function(p) { return typeof p === 'number' ? p : (p.score || 0); });
      }
    });
    Object.keys(scoreMap).forEach(function(cid) {
      var el = document.getElementById('spark-' + cid.replace(/[^a-zA-Z0-9_-]/g, '_'));
      if (!el) return;
      var scores = scoreMap[cid];
      if (scores.length < 2) { el.innerHTML = '<span style="color:var(--text-dim);font-size:10px;">—</span>'; return; }
      // Build SVG sparkline
      var w = 72, h = 24, pad = 2;
      var min = Math.min.apply(null, scores), max = Math.max.apply(null, scores);
      var range = max - min || 1;
      var pts = scores.map(function(s, i) {
        var x = pad + (i / (scores.length - 1)) * (w - 2*pad);
        var y = h - pad - ((s - min) / range) * (h - 2*pad);
        return x.toFixed(1) + ',' + y.toFixed(1);
      });
      var last = scores[scores.length - 1];
      var color = last >= 80 ? '#3fb950' : last >= 60 ? '#4d9fb5' : last >= 40 ? '#d29922' : '#f85149';
      el.innerHTML = '<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'">'
        + '<polyline points="'+pts.join(' ')+'" fill="none" stroke="'+color+'" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        + '<circle cx="'+pts[pts.length-1].split(',')[0]+'" cy="'+pts[pts.length-1].split(',')[1]+'" r="2" fill="'+color+'"/>'
        + '</svg>';
    });
  } catch(e) { /* sparklines are non-critical */ }
}

// ── Bulk Audit ──────────────────────────────────────────────────────────────
// ── Dashboard Excel Export & Clipboard Copy ─────────────────────────────────
async function exportDashboardExcel() {
  try {
    const r = await fetch('/api/export/excel', {method: 'POST'});
    if (!r.ok) { showToast(t('err_export_failed'), 'error'); return; }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const disp = r.headers.get('Content-Disposition') || '';
    const m = disp.match(/filename="?([^"]+)"?/);
    a.download = m ? m[1] : 'dashboard_export.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch(e) { showToast(t('err_export_failed') + ': ' + e.message, 'error'); }
}

function copyOverviewToClipboard() {
  if (!_overviewData || !_overviewData.customers) { showToast(t('msg_no_data_available'), 'warning'); return; }
  const customers = _overviewData.customers;
  const headers = ['Customer', 'Domain', 'Risk Grade', 'Risk Score', 'MFA Coverage %', 'Secure Score %', 'Total Users', 'Users Without MFA', 'CA Policies', 'Intune Compliance %', 'Global Admins', 'Last Audit Date', 'Tags'];
  let tsv = headers.join('\t') + '\n';
  for (const c of customers) {
    const m = c.metrics || {};
    const hasM = c.has_metrics;
    const row = [
      c.customer_name || '',
      c.primary_domain || '',
      hasM ? (m.risk_grade || '') : '',
      hasM && m.risk_score !== undefined ? m.risk_score : '',
      hasM && metricPct(m.mfa_coverage_pct, 1) !== null ? metricPct(m.mfa_coverage_pct, 1) : '',
      hasM && metricPct(m.secure_score_pct, 1) !== null ? metricPct(m.secure_score_pct, 1) : '',
      hasM && m.total_users !== undefined ? m.total_users : '',
      hasM && m.users_no_mfa !== undefined ? m.users_no_mfa : '',
      hasM && m.ca_policies_enabled !== undefined ? m.ca_policies_enabled : '',
      hasM && metricPct(m.intune_compliance_pct, 1) !== null ? metricPct(m.intune_compliance_pct, 1) : '',
      hasM && m.admin_roles_ga_count !== undefined ? m.admin_roles_ga_count : '',
      c.last_audit || '',
      (c.tags || []).join(', '),
    ];
    tsv += row.join('\t') + '\n';
  }
  navigator.clipboard.writeText(tsv).then(function() {
    var btn = event.target.closest('button');
    if (btn) { var orig = btn.textContent; btn.textContent = t('btn_copied'); setTimeout(function(){ btn.textContent = orig; }, 1500); }
  }).catch(function(e) { showToast(t('err_could_not_copy').replace('{msg}', e.message), 'error'); });
}

var _bulkAuditEventSource = null;
function startBulkAudit() {
  if (_bulkAuditEventSource) { showToast(t('err_bulk_audit_already_running'), 'warning'); return; }
  var btn = document.getElementById('bulk-audit-btn');
  if (btn) { btn.disabled = true; btn.textContent = t('status_running'); }
  var panel = document.getElementById('bulk-audit-panel');
  panel.style.display = 'block';
  panel.innerHTML = '<div class="card" style="padding:20px;margin-bottom:24px;" id="bulk-progress-card">' +
    '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">' +
    '<div style="font-weight:700;font-size:15px;">' + t('bulk_audit') + '</div>' +
    '<button class="btn btn-ghost" id="bulk-cancel-btn" onclick="cancelBulkAudit()" style="font-size:12px;padding:4px 10px;">' + t('avbryt') + '</button></div>' +
    '<div id="bulk-overall-status" style="font-size:13px;color:var(--text-muted);margin-bottom:12px;">' + t('starter') + '</div>' +
    '<div style="background:var(--bg);border-radius:6px;height:8px;overflow:hidden;margin-bottom:8px;">' +
    '<div id="bulk-overall-bar" style="height:100%;width:0%;background:var(--blue);transition:width 0.3s;border-radius:6px;"></div></div>' +
    '<div id="bulk-customer-status" style="font-size:13px;color:var(--text-muted);margin-bottom:8px;"></div>' +
    '<div style="background:var(--bg);border-radius:6px;height:6px;overflow:hidden;margin-bottom:16px;">' +
    '<div id="bulk-customer-bar" style="height:100%;width:0%;background:#4d9fb5;transition:width 0.3s;border-radius:6px;"></div></div>' +
    '<div id="bulk-results-table" style="display:none;">' +
    '<div style="font-weight:600;font-size:13px;margin-bottom:8px;">' + t('resultater') + '</div>' +
    '<table style="width:100%;border-collapse:collapse;font-size:12px;">' +
    '<thead><tr style="border-bottom:1px solid var(--border);">' +
    '<th style="text-align:left;padding:6px 8px;color:var(--text-muted);">' + t('kunde') + '</th>' +
    '<th style="text-align:center;padding:6px 8px;color:var(--text-muted);">' + t('grad') + '</th>' +
    '<th style="text-align:center;padding:6px 8px;color:var(--text-muted);">' + t('score') + '</th>' +
    '<th style="text-align:center;padding:6px 8px;color:var(--text-muted);">' + t('seksjoner_2') + '</th>' +
    '<th style="text-align:center;padding:6px 8px;color:var(--text-muted);">' + t('status') + '</th>' +
    '</tr></thead><tbody id="bulk-results-tbody"></tbody></table></div></div>';
  var _ari_b = document.getElementById('audit-running-indicator');
  if (_ari_b) { _ari_b.textContent = ''; _ari_b.innerHTML = '<span style="width:8px;height:8px;border-radius:50%;background:#fff;display:inline-block;"></span> ' + t('msg_bulk_audit_running'); _ari_b.onclick = function(){ showView('overview'); }; _ari_b.style.display = 'flex'; }
  var totalCustomers = 0, completedCustomers = 0, customerSectionsDone = 0, customerSectionsTotal = 0;
  fetch('/api/audit/bulk').then(async function(resp) {
    if (!resp.ok) { document.getElementById('bulk-overall-status').innerHTML = '<span style="color:var(--red)">HTTP '+resp.status+'</span>'; return; }
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buf = '';
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buf += decoder.decode(chunk.value, {stream:true});
      var lines = buf.split('\n'); buf = lines.pop();
      for (var li = 0; li < lines.length; li++) {
        if (!lines[li].startsWith('data: ')) continue;
        try {
        var d = JSON.parse(lines[li].slice(6));
    if (d.type === 'bulk_started') {
      totalCustomers = d.total_customers;
      var statusText = t('audit_customers_done').replace('{done}', '0').replace('{total}', totalCustomers);
      if (d.skipped_unconfigured > 0) statusText += ' — ' + t('msg_skipped_unconfigured').replace('{count}', d.skipped_unconfigured);
      document.getElementById('bulk-overall-status').textContent = statusText;
    } else if (d.type === 'customer_start') {
      customerSectionsDone = 0; customerSectionsTotal = 0;
      document.getElementById('bulk-customer-status').textContent = t('audit_running_customer').replace('{customer}', d.customer).replace('{index}', d.index + 1).replace('{total}', d.total);
      var _bcb = document.getElementById('bulk-customer-bar'); if (_bcb) _bcb.style.width = '0%';
    } else if (d.type === 'progress') {
      if (d.status === 'done' || d.status === 'failed' || d.status === 'skipped') customerSectionsDone++;
      if (d.status === 'running') customerSectionsTotal = Math.max(customerSectionsTotal, customerSectionsDone + 5);
      var custPct = customerSectionsTotal > 0 ? Math.min(95, Math.round((customerSectionsDone / customerSectionsTotal) * 100)) : 0;
      var _bcb2 = document.getElementById('bulk-customer-bar'); if (_bcb2) _bcb2.style.width = custPct + '%';
      document.getElementById('bulk-customer-status').innerHTML = t('audit_running_customer').replace('{customer}', '<b>' + esc(d.customer) + '</b>').replace('{index}', d.index + 1).replace('{total}', d.total) + ' &mdash; ' + esc(d.name) + ' <span style="color:var(--text-dim);">' + esc(d.detail) + '</span>';
    } else if (d.type === 'customer_done') {
      completedCustomers++;
      var overallPct = Math.round((completedCustomers / totalCustomers) * 100);
      document.getElementById('bulk-overall-bar').style.width = overallPct + '%';
      document.getElementById('bulk-overall-status').textContent = t('audit_customers_done').replace('{done}', completedCustomers).replace('{total}', totalCustomers);
      var _bcb3 = document.getElementById('bulk-customer-bar'); if (_bcb3) _bcb3.style.width = '100%';
      var gradeColors = {A:'#3fb950', B:'#4d9fb5', C:'#d29922', D:'#f85149', F:'#8b0000'};
      var tbody = document.getElementById('bulk-results-tbody');
      document.getElementById('bulk-results-table').style.display = 'block';
      var tr = document.createElement('tr');
      tr.style.borderBottom = '1px solid var(--border)';
      tr.innerHTML = '<td style="padding:6px 8px;font-weight:600;">' + esc(d.customer) + '</td>' +
        '<td style="text-align:center;padding:6px 8px;"><span style="display:inline-block;width:26px;height:26px;line-height:26px;border-radius:4px;font-weight:800;font-size:13px;color:#fff;background:' + (gradeColors[d.grade] || 'var(--text-muted)') + ';">' + esc(d.grade || '-') + '</span></td>' +
        '<td style="text-align:center;padding:6px 8px;">' + (d.risk_score || '-') + '</td>' +
        '<td style="text-align:center;padding:6px 8px;">' + d.sections_done + '/' + d.sections_total + '</td>' +
        '<td style="text-align:center;padding:6px 8px;color:var(--green);font-weight:600;">OK</td>';
      tbody.appendChild(tr);
    } else if (d.type === 'customer_error' || d.type === 'customer_skip') {
      completedCustomers++;
      document.getElementById('bulk-overall-bar').style.width = Math.round((completedCustomers / totalCustomers) * 100) + '%';
      document.getElementById('bulk-overall-status').textContent = t('audit_customers_done').replace('{done}', completedCustomers).replace('{total}', totalCustomers);
      var tbody2 = document.getElementById('bulk-results-tbody');
      document.getElementById('bulk-results-table').style.display = 'block';
      var tr2 = document.createElement('tr');
      tr2.style.borderBottom = '1px solid var(--border)';
      tr2.innerHTML = '<td style="padding:6px 8px;font-weight:600;">' + esc(d.customer) + '</td>' +
        '<td style="text-align:center;padding:6px 8px;">-</td><td style="text-align:center;padding:6px 8px;">-</td>' +
        '<td style="text-align:center;padding:6px 8px;">-</td>' +
        '<td style="text-align:center;padding:6px 8px;color:var(--red);font-weight:600;" title="' + esc(d.error || d.reason || '') + '">' + (d.type === 'customer_skip' ? t('status_skipped') : t('status_error')) + '</td>';
      tbody2.appendChild(tr2);
    } else if (d.type === 'bulk_done') {
      document.getElementById('bulk-overall-bar').style.width = '100%';
      document.getElementById('bulk-overall-bar').style.background = 'var(--green)';
      document.getElementById('bulk-overall-status').innerHTML = '<span style="color:var(--green);font-weight:700;">' + t('audit_finished').replace('{count}', completedCustomers) + '</span>';
      document.getElementById('bulk-customer-status').textContent = '';
      document.getElementById('bulk-cancel-btn').style.display = 'none';
      finishBulkAudit();
    } else if (d.type === 'error') {
      var errHtml = '<span style="color:var(--red);font-weight:700;">' + t('status_error') + ': ' + esc(d.msg) + '</span>';
      if (d.traceback) {
        errHtml += '<pre style="margin-top:10px;padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;font-size:11px;color:var(--red);overflow-x:auto;white-space:pre-wrap;text-align:left;">' + esc(d.traceback) + '</pre>';
      }
      document.getElementById('bulk-overall-status').innerHTML = errHtml;
      var cancelBtn = document.getElementById('bulk-cancel-btn');
      if (cancelBtn) cancelBtn.style.display = 'none';
      var _ari_be = document.getElementById('audit-running-indicator');
      if (_ari_be) _ari_be.style.display = 'none';
      var btn2 = document.getElementById('bulk-audit-btn');
      if (btn2) { btn2.disabled = false; btn2.textContent = t('btn_run_all_customers'); }
    }
      } catch(_e) {}
    }
  }
}).catch(function(e) {
    var statusEl = document.getElementById('bulk-overall-status');
    if (statusEl) statusEl.innerHTML = '<span style="color:var(--red);">' + t('err_lost_connection') + '</span>';
    finishBulkAudit();
  });
}
function cancelBulkAudit() {
  if (_bulkAuditEventSource) { _bulkAuditEventSource.close(); _bulkAuditEventSource = null; }
  document.getElementById('bulk-overall-status').innerHTML = '<span style="color:var(--orange);">' + t('status_cancelled') + '</span>';
  document.getElementById('bulk-customer-status').textContent = '';
  finishBulkAudit();
}
function finishBulkAudit() {
  if (_bulkAuditEventSource) { _bulkAuditEventSource.close(); _bulkAuditEventSource = null; }
  var btn = document.getElementById('bulk-audit-btn');
  if (btn) { btn.disabled = false; btn.textContent = t('btn_run_all_customers'); }
  var _ari_f = document.getElementById('audit-running-indicator');
  if (_ari_f) _ari_f.style.display = 'none';
}

async function overviewSelectCustomer(customerId) {
  try {
    const d = await apiFetch('/api/customers/switch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({customer_id: customerId})
    });

    if (d.ok) {
      // Track recent customers
      var recent = JSON.parse(localStorage.getItem('sybr_recent_customers') || '[]');
      recent = recent.filter(function(id){return id !== customerId});
      recent.unshift(customerId);
      localStorage.setItem('sybr_recent_customers', JSON.stringify(recent.slice(0,5)));
      showView('customer-detail');
      loadCustomerDetail(customerId);
    }
  } catch(e) { showToast(t('status_error') + ': ' + e.message, 'error'); }
}

// ── Customer Detail View ──────────────────────────────────────────────────────
var _detailChartInstance = null;

async function loadCustomerDetail(customerId) {
  var box = document.getElementById('customer-detail-content');
  box.innerHTML = '<div style="text-align:center;padding:48px;color:var(--text-muted);"><div class="loader" style="width:24px;height:24px;margin:0 auto 16px;"></div>' + t('msg_loading','Loading...') + '</div>';

  // Find customer from cached overview data — load if not cached yet
  if (!_overviewData || !_overviewData.customers) {
    try {
      var ovData = await apiFetch('/api/dashboard/overview');
      if (ovData) _overviewData = {customers: ovData.customers || [], active_id: ovData.active_id};
    } catch(e) { console.warn('Overview data load failed:', e); }
  }
  var cust = null;
  if (_overviewData && _overviewData.customers) {
    cust = _overviewData.customers.find(function(c){ return c.customer_id === customerId || c._id === customerId; });
  }
  if (!cust) { box.innerHTML = '<div class="alert alert-error">' + t('err_customer_not_found','Kunde ikke funnet') + '</div>'; return; }

  var m = cust.metrics || {};
  var hasM = cust.has_metrics;
  var gradeColor = function(g) { return {A:'#3fb950', B:'#4d9fb5', C:'#d29922', D:'#f85149', F:'#8b0000'}[g] || 'var(--text-muted)'; };

  // Update breadcrumb
  var bcItems = document.getElementById('breadcrumb-items');
  var bcNav = document.getElementById('breadcrumb');
  if (bcNav && bcItems) {
    bcNav.style.display = 'block';
    bcItems.innerHTML = '<a href="javascript:void(0)" onclick="showView(\'customers\')" style="color:var(--text-muted);text-decoration:none;">' + t('nav_customers') + '</a>' +
      ' <span style="margin:0 var(--space-2);color:var(--text-dim);opacity:0.5;">/</span> ' +
      '<span style="color:var(--text);font-weight:500;">' + esc(cust.customer_name) + '</span>';
  }

  var grade = hasM ? (m.risk_grade || '-') : '-';
  var score = hasM ? (m.risk_score !== undefined ? m.risk_score : '-') : '-';

  box.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-4);flex-wrap:wrap;gap:var(--space-4);">
      <div>
        <div style="font-size:var(--font-2xl);font-weight:800;">${esc(cust.customer_name)}</div>
        <div style="font-size:var(--font-sm);color:var(--text-dim);font-family:var(--mono);">${esc(cust.primary_domain || '')}</div>
      </div>
      <button class="btn btn-primary" onclick="quickSwitchAndAudit('${esc(customerId)}')">${t('btn_run_audit')}</button>
      <button class="btn btn-ghost" onclick="openLatestReport()" title="${t('btn_open_report','Open report')}">${t('btn_open_report','Report')}</button>
      <button class="btn btn-ghost" onclick="window.open('/api/reports/customer-summary/${esc(customerId)}','_blank')" title="${t('btn_generate_customer_report','Generate customer report')}">${t('btn_generate_report')}</button>
      <button class="btn btn-ghost" onclick="copyCustomerSummary()" title="${t('btn_copy_to_clipboard')}">${t('btn_copy_to_clipboard')}</button>
    </div>
    <div style="display:flex;gap:0;border-bottom:1px solid var(--border);margin-bottom:var(--space-6);">
      <button class="btn btn-ghost" style="border:none;border-bottom:2px solid var(--blue);border-radius:0;padding:var(--space-2) var(--space-4);font-size:var(--font-sm);font-weight:600;">${t('nav_dashboard')}</button>
      <button class="btn btn-ghost" onclick="showView('home')" style="border:none;border-bottom:2px solid transparent;border-radius:0;padding:var(--space-2) var(--space-4);font-size:var(--font-sm);">${t('nav_m365_status')}</button>
      <button class="btn btn-ghost" onclick="showView('history')" style="border:none;border-bottom:2px solid transparent;border-radius:0;padding:var(--space-2) var(--space-4);font-size:var(--font-sm);">${t('nav_history')}</button>
      <button class="btn btn-ghost" onclick="showView('files')" style="border:none;border-bottom:2px solid transparent;border-radius:0;padding:var(--space-2) var(--space-4);font-size:var(--font-sm);">${t('nav_files','Filer')}</button>
      ${cust.also_account_id ? '<button class="btn btn-ghost" onclick="loadCustomerLicenses(\'' + esc(cust.also_account_id) + '\')" style="border:none;border-bottom:2px solid transparent;border-radius:0;padding:var(--space-2) var(--space-4);font-size:var(--font-sm);">' + t('nav_licenses','Licenses') + '</button>' : ''}
    </div>

    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:var(--space-4);margin-bottom:var(--space-6);">
      <div class="card" style="text-align:center;padding:var(--space-5);">
        <div style="width:64px;height:64px;line-height:64px;border-radius:var(--radius-xl);font-weight:800;font-size:var(--font-2xl);color:#fff;background:${gradeColor(grade)};margin:0 auto var(--space-3);box-shadow:0 4px 12px ${gradeColor(grade)}40;">${grade}</div>
        <div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">${t('lbl_grade')}</div>
      </div>
      <div class="card" style="text-align:center;padding:var(--space-5);">
        <div style="position:relative;width:80px;height:80px;margin:0 auto var(--space-2);"><canvas id="gauge-risk"></canvas></div>
        <div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">${t('lbl_risk')}</div>
      </div>
      <div class="card" style="text-align:center;padding:var(--space-5);">
        <div style="position:relative;width:80px;height:80px;margin:0 auto var(--space-2);"><canvas id="gauge-mfa"></canvas></div>
        <div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">MFA</div>
      </div>
      <div class="card" style="text-align:center;padding:var(--space-5);">
        <div style="position:relative;width:80px;height:80px;margin:0 auto var(--space-2);"><canvas id="gauge-ss"></canvas></div>
        <div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">${t('secure_score_2')}</div>
      </div>
    </div>

    <div id="customer-baseline-panel"></div>

    <div class="card" style="padding:var(--space-5);margin-bottom:var(--space-4);">
      <div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:var(--space-3);">${t('lbl_trend')}</div>
      <div style="position:relative;height:250px;"><canvas id="chart-customer-trend"></canvas></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4);">
      <div class="card" style="padding:var(--space-5);">
        <div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:var(--space-4);">${t('lbl_details')}</div>
        <div style="display:grid;grid-template-columns:140px 1fr;gap:var(--space-2) var(--space-4);font-size:var(--font-sm);">
          <span style="color:var(--text-muted);">${t('lbl_users')}</span><span style="font-weight:600;">${hasM ? (m.total_users || 0) : '-'}</span>
          <span style="color:var(--text-muted);">${t('lbl_without_mfa')}</span><span style="font-weight:600;color:${hasM && m.users_no_mfa > 0 ? 'var(--red)' : 'var(--text)'};">${hasM ? (m.users_no_mfa || 0) : '-'}</span>
          <span style="color:var(--text-muted);">${t('lbl_ca_policies')}</span><span style="font-weight:600;">${hasM ? (m.ca_policies_enabled || 0) : '-'}</span>
          <span style="color:var(--text-muted);">${t('intune')}</span><span style="font-weight:600;">${hasM && metricPct(m.intune_compliance_pct) !== null ? metricPct(m.intune_compliance_pct)+'%' : '-'}</span>
          <span style="color:var(--text-muted);">${t('lbl_last_audit')}</span><span style="font-weight:600;">${cust.last_audit ? cust.last_audit.substring(0,10) : '-'}${cust.last_audit ? (() => { try { var d = new Date(cust.last_audit.replace(/_/g,'T').substring(0,16)); var days = Math.floor((Date.now()-d.getTime())/86400000); return ' <span style="color:var(--text-dim);font-weight:400;">(' + days + 'd)</span>'; } catch(e) { return ''; } })() : ''}</span>
          <span style="color:var(--text-muted);">${t('lbl_warnings','Warnings')}</span><span style="font-weight:600;color:${hasM && m.total_warns > 0 ? 'var(--orange)' : 'var(--text)'};">${hasM ? (m.total_warns || 0) : '-'}</span>
        </div>
      </div>
      <div class="card" style="padding:var(--space-5);">
        <div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:var(--space-4);">${t('lbl_tags')}</div>
        <div style="display:flex;flex-wrap:wrap;gap:var(--space-2);">
          ${(cust.tags || []).map(function(tag){ return '<span style="background:var(--blue-dark);color:var(--blue);padding:4px 10px;border-radius:var(--radius-full);font-size:var(--font-xs);border:1px solid rgba(77,159,181,0.3);">'+esc(tag)+'</span>'; }).join('') || '<span style="color:var(--text-dim);font-size:var(--font-sm);">'+t('msg_no_tags','Ingen tags')+'</span>'}
        </div>
      </div>
    </div>
  `;

  // Render gauge charts + trend chart + remediation
  setTimeout(function() { _renderGauges(score, hasM ? m.mfa_coverage_pct : null, hasM ? m.secure_score_pct : null); }, 50);
  _loadCustomerTrendChart(customerId);
  _loadCustomerBaselineCard(customerId);

  // Add remediation panel below existing content
  var remDiv = document.createElement('div');
  remDiv.className = 'card';
  remDiv.style.cssText = 'padding:var(--space-5);margin-top:var(--space-4);';
  remDiv.id = 'remediation-panel';
  remDiv.innerHTML = '<div class="text-sm text-muted">' + t('msg_loading_remediation','Laster remediering...') + '</div>';
  box.appendChild(remDiv);
  loadRemediationPanel('remediation-panel');

  // Add notes panel
  var notesDiv = document.createElement('div');
  notesDiv.className = 'card';
  notesDiv.style.cssText = 'padding:var(--space-5);margin-top:var(--space-4);';
  notesDiv.id = 'customer-notes-panel';
  notesDiv.innerHTML = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3);">'
    + '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;">' + t('hdr_notes','Notater') + '</div>'
    + '<div style="display:flex;gap:var(--space-2);align-items:center;">'
    + '<span id="notes-save-status" style="font-size:var(--font-xs);color:var(--text-dim);"></span>'
    + '<button class="btn btn-ghost btn-sm" onclick="saveCustomerNotes()">' + t('btn_save','Lagre') + '</button>'
    + '</div></div>'
    + '<textarea id="customer-notes-textarea" style="width:100%;min-height:120px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);color:var(--text);padding:var(--space-3);font-family:inherit;font-size:var(--font-sm);resize:vertical;" placeholder="' + t('placeholder_notes','Skriv notater om denne kunden...') + '"></textarea>';
  box.appendChild(notesDiv);
  _loadCustomerNotes();

  // Activity log for this customer
  var actDiv = document.createElement('div');
  actDiv.className = 'card';
  actDiv.style.cssText = 'padding:var(--space-5);margin-top:var(--space-4);';
  actDiv.id = 'customer-activity-panel';
  actDiv.innerHTML = '<div class="text-sm text-muted">' + t('msg_loading','Laster...') + '</div>';
  box.appendChild(actDiv);
  _loadCustomerActivity(cust.customer_name);

  // Uniweb Hosting card
  var uwDiv = document.createElement('div');
  uwDiv.id = 'customer-uniweb-panel';
  box.appendChild(uwDiv);
  _unifiedLoadUniwebCard(customerId);

  // Network Inventory card
  var netDiv = document.createElement('div');
  netDiv.className = 'card';
  netDiv.style.cssText = 'padding:var(--space-5);margin-top:var(--space-4);';
  netDiv.id = 'customer-network-panel';
  netDiv.innerHTML = '<div class="text-sm text-muted">' + t('msg_loading_network','Loading network inventory...') + '</div>';
  box.appendChild(netDiv);
  _loadCustomerNetworkInventory(customerId);

  // Infrastructure card (SSH hosts, VPN profiles, FortiGate, UniFi)
  var infraDiv = document.createElement('div');
  infraDiv.id = 'customer-infra-panel';
  box.appendChild(infraDiv);
  _loadCustomerInfraCard(customerId);
}

// ── Sybr Standard on the customer card ──────────────────────────────────────
// Two questions a technician opening a customer asks first: how far is this
// tenant from what we require, and did anything move since last time. The
// answers come from the same two endpoints the report reads, so the card and
// the PDF can never disagree.
//
// The card never invents a verdict. A requirement whose evidence was not
// collected is shown as not assessed and kept out of the percentage, and a
// customer with nothing to compare against is told that rather than shown a
// reassuring zero.
// Reason codes carry their values separately, so the sentence is assembled
// in the reader's language rather than shipped from the server in one.
function _reason(prefix, code, params) {
  var out = t(prefix + code, '');
  if (!out) return '';
  Object.keys(params || {}).forEach(function(k) {
    out = out.split('{' + k + '}').join(String(params[k]));
  });
  return out;
}

function _baselineStatusPill(status) {
  if (status === 'pass') return '<span style="color:var(--green);">&#10003;</span>';
  if (status === 'fail') return '<span style="color:var(--red);">&#10007;</span>';
  return '<span style="color:var(--text-dim);">&#8211;</span>';
}

async function _loadCustomerBaselineCard(customerId) {
  var el = document.getElementById('customer-baseline-panel');
  if (!el) return;

  var results = await Promise.all([
    apiFetch('/api/baselines/default/evaluate/' + encodeURIComponent(customerId) + '/latest?lang=' + _lang).catch(function(){ return null; }),
    apiFetch('/api/policy-backup/' + encodeURIComponent(customerId) + '/drift').catch(function(){ return null; })
  ]);
  var b = results[0], drift = results[1];
  if (!b) { el.style.display = 'none'; return; }
  if (!b.baseline) {
    // A customer with no audit yet. Say so quietly rather than showing an
    // empty card or, worse, a zero.
    el.innerHTML = '<div class="card" style="padding:var(--space-5);margin-bottom:var(--space-4);color:var(--text-dim);font-size:var(--font-sm);">'
      + esc(_reason('drift_', b.reason_code, {}) || t('msg_baseline_no_run','No audit run to measure against yet.')) + '</div>';
    return;
  }

  var pct = b.conformance_pct;
  var pctColor = pct === null || pct === undefined ? 'var(--text-dim)'
    : (pct >= 90 ? 'var(--green)' : (pct >= 70 ? 'var(--orange)' : 'var(--red)'));
  var pctText = pct === null || pct === undefined ? '&#8212;' : (pct + ' %');

  var html = '<div class="card" style="padding:var(--space-5);margin-bottom:var(--space-4);">';
  html += '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--space-3);margin-bottom:var(--space-4);">';
  html += '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;">'
        + esc(b.baseline.name) + ' ' + esc(b.baseline.version) + '</div>';
  html += '<div style="display:flex;align-items:baseline;gap:var(--space-2);">'
        + '<span style="font-size:var(--font-2xl);font-weight:800;color:' + pctColor + ';">' + pctText + '</span>'
        + '<span style="font-size:var(--font-xs);color:var(--text-muted);">' + t('lbl_conformance','conformance') + '</span></div>';
  html += '</div>';

  // What the percentage is a percentage of. Showing it without this invites
  // the reader to assume every requirement was measured.
  if (b.assessed === 0) {
    html += '<div style="font-size:var(--font-xs);color:var(--text-muted);margin-bottom:var(--space-3);">'
          + t('msg_baseline_nothing_assessed','No requirement could be assessed on this run. That describes the collection, not the tenant.') + '</div>';
  } else {
    html += '<div style="font-size:var(--font-xs);color:var(--text-muted);margin-bottom:var(--space-3);">'
          + t('msg_baseline_basis','{passed} of {assessed} assessed requirements met')
              .replace('{passed}', b.passed).replace('{assessed}', b.assessed)
          + (b.not_measured ? ' &middot; ' + t('msg_baseline_skipped','{n} not assessed').replace('{n}', b.not_measured) : '')
          + '</div>';
  }

  html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
  (b.checks || []).forEach(function(c) {
    var dim = c.status === 'not_measured';
    html += '<tr style="border-bottom:1px solid var(--border);">';
    html += '<td style="padding:6px 8px 6px 0;width:20px;">' + _baselineStatusPill(c.status) + '</td>';
    html += '<td style="padding:6px 0;' + (dim ? 'color:var(--text-dim);' : '') + '">' + esc(c.title) + '</td>';
    html += '<td style="padding:6px 0;text-align:right;color:var(--text-muted);">' + esc(_reason('bl_', c.reason_code, c.params)) + '</td>';
    html += '</tr>';
  });
  html += '</table>';

  // ── Drift ──
  html += '<div style="margin-top:var(--space-4);padding-top:var(--space-4);border-top:1px solid var(--border);">';
  html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">'
        + t('hdr_policy_drift','Changes since previous audit') + '</div>';
  if (!drift || !drift.measured) {
    html += '<div style="font-size:var(--font-xs);color:var(--text-dim);">'
          + esc((drift && _reason('drift_', drift.reason_code, drift.reason_params)) || t('msg_drift_not_measured','Not compared.')) + '</div>';
  } else if (!drift.added_total && !drift.removed_total && !drift.changed_total) {
    html += '<div style="font-size:var(--font-xs);color:var(--text-muted);">'
          + t('msg_drift_quiet','No policy changed since {run}.').replace('{run}', esc(drift.compared_with)) + '</div>';
  } else {
    html += '<div style="font-size:var(--font-xs);color:var(--text-muted);margin-bottom:var(--space-2);">'
          + t('msg_drift_summary','Compared with {run}: {added} added, {removed} removed, {changed} changed.')
              .replace('{run}', esc(drift.compared_with)).replace('{added}', drift.added_total)
              .replace('{removed}', drift.removed_total).replace('{changed}', drift.changed_total)
          + '</div>';
    html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
    (drift.snapshots || []).forEach(function(s) {
      if (!s.comparable) return;
      var rows = [];
      (s.removed || []).forEach(function(p){ rows.push([t('lbl_removed','Removed'), 'var(--red)', p, '']); });
      (s.changed || []).forEach(function(p){ rows.push([t('lbl_changed','Changed'), 'var(--orange)', p, (p.fields||[]).join(', ')]); });
      (s.added   || []).forEach(function(p){ rows.push([t('lbl_added','Added'), 'var(--green)', p, '']); });
      rows.forEach(function(r) {
        html += '<tr style="border-bottom:1px solid var(--border);">'
              + '<td style="padding:5px 8px 5px 0;color:' + r[1] + ';white-space:nowrap;">' + r[0] + '</td>'
              + '<td style="padding:5px 0;">' + esc(r[2].name || t('lbl_unnamed','(unnamed)')) + '</td>'
              + '<td style="padding:5px 0;text-align:right;color:var(--text-dim);">' + esc(r[3]) + '</td>'
              + '</tr>';
      });
    });
    html += '</table>';
  }
  html += '</div></div>';

  el.innerHTML = html;
}

// ── Customer Infrastructure Card ────────────────────────────────────────────

async function _loadCustomerInfraCard(customerId) {
  var el = document.getElementById('customer-infra-panel');
  if (!el) return;
  try {
    var d = await apiFetch('/api/dashboard/customer-infra/' + encodeURIComponent(customerId));
    if (!d) { el.style.display = 'none'; return; }

    var sshHosts = d.ssh_hosts || [];
    var vpnProfiles = d.vpn_profiles || [];
    var fg = d.fortigate;
    var uf = d.unifi;

    var hasAnything = sshHosts.length || vpnProfiles.length || fg || uf;
    if (!hasAnything) {
      el.innerHTML = '<div class="card" style="padding:var(--space-5);margin-top:var(--space-4);">'
        + '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:var(--space-3);">' + t('hdr_infrastructure','Infrastructure') + '</div>'
        + '<div style="color:var(--text-dim);font-size:var(--font-sm);">' + t('msg_no_infra_linked','No infrastructure linked to this customer. Link SSH hosts or VPN profiles from the Infrastructure section.') + '</div>'
        + '</div>';
      return;
    }

    var html = '<div class="card" style="padding:var(--space-5);margin-top:var(--space-4);">';
    html += '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:var(--space-4);">' + t('hdr_infrastructure','Infrastructure') + '</div>';

    // SSH Hosts
    if (sshHosts.length) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">' + t('hdr_ssh_hosts','SSH Hosts') + ' (' + sshHosts.length + ')</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;margin-bottom:var(--space-4);">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_host_name','Name') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_host_address','Host') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_username','Username') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_device_type','Type') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_group','Group') + '</th>';
      html += '<th style="text-align:center;padding:4px 8px;">' + t('lbl_status','Status') + '</th>';
      html += '<th style="padding:4px 8px;"></th>';
      html += '</tr></thead><tbody>';
      sshHosts.forEach(function(h) {
        var statusColor = h.is_reachable === true ? 'var(--green)' : h.is_reachable === false ? 'var(--red)' : 'var(--text-dim)';
        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(h.label) + '</td>';
        html += '<td style="padding:4px 8px;font-family:var(--mono);font-size:11px;">' + esc(h.hostname) + ':' + h.port + '</td>';
        html += '<td style="padding:4px 8px;">' + esc(h.username) + '</td>';
        html += '<td style="padding:4px 8px;">' + esc(h.device_type) + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(h.group_name || '-') + '</td>';
        html += '<td style="padding:4px 8px;text-align:center;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';"></span></td>';
        html += '<td style="padding:4px 8px;"><button class="btn btn-ghost" onclick="sshTerminal(\'' + h.id + '\')" style="padding:1px 6px;font-size:10px;color:var(--blue);">SSH</button></td>';
        html += '</tr>';
      });
      html += '</tbody></table>';
    }

    // VPN Profiles
    if (vpnProfiles.length) {
      var protocolLabels = {wireguard:'WireGuard', openvpn:'OpenVPN', azure:'Azure P2S', fortigate_ipsec:'FortiGate IPsec'};
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">' + t('hdr_vpn_profiles','VPN Profiles') + ' (' + vpnProfiles.length + ')</div>';
      html += '<div style="display:flex;flex-wrap:wrap;gap:var(--space-3);margin-bottom:var(--space-4);">';
      vpnProfiles.forEach(function(p) {
        var protoLabel = protocolLabels[p.protocol] || p.protocol;
        html += '<div style="display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3);background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);font-size:var(--font-xs);">';
        html += '<span style="font-weight:600;">' + esc(p.name) + '</span>';
        html += '<span style="color:var(--text-muted);">' + esc(protoLabel) + '</span>';
        html += '<button class="btn btn-ghost" onclick="vpnConnect(\'' + p.id + '\')" style="padding:1px 6px;font-size:10px;color:var(--green);">' + t('vpn_connect','Connect') + '</button>';
        html += '</div>';
      });
      html += '</div>';
    }

    // FortiGate + UniFi side by side
    if (fg || uf) {
      html += '<div style="display:grid;grid-template-columns:' + (fg && uf ? '1fr 1fr' : '1fr') + ';gap:var(--space-4);">';
      if (fg) {
        html += '<div style="padding:var(--space-3);background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);">';
        html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">FortiGate</div>';
        html += '<div style="font-size:var(--font-xs);display:grid;grid-template-columns:70px 1fr;gap:2px var(--space-2);">';
        html += '<span style="color:var(--text-muted);">' + t('host') + '</span><span style="font-family:var(--mono);">' + esc(fg.host) + '</span>';
        html += '<span style="color:var(--text-muted);">' + t('port') + '</span><span>' + fg.port + '</span>';
        html += '<span style="color:var(--text-muted);">VDOM</span><span>' + esc(fg.vdom) + '</span>';
        html += '</div></div>';
      }
      if (uf) {
        html += '<div style="padding:var(--space-3);background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);">';
        html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">UniFi</div>';
        html += '<div style="font-size:var(--font-xs);display:grid;grid-template-columns:70px 1fr;gap:2px var(--space-2);">';
        html += '<span style="color:var(--text-muted);">' + t('host') + '</span><span style="font-family:var(--mono);">' + esc(uf.host) + '</span>';
        html += '<span style="color:var(--text-muted);">' + t('site') + '</span><span>' + esc(uf.site) + '</span>';
        html += '<span style="color:var(--text-muted);">' + t('mode') + '</span><span>' + esc(uf.mode) + '</span>';
        html += '</div></div>';
      }
      html += '</div>';
    }

    html += '</div>';
    el.innerHTML = html;
  } catch(e) {
    el.style.display = 'none';
  }
}

// ── Network Inventory Card ──────────────────────────────────────────────────

async function _loadCustomerNetworkInventory(customerId) {
  var el = document.getElementById('customer-network-panel');
  if (!el) return;
  try {
    var d = await apiFetch('/api/dashboard/network-inventory/' + encodeURIComponent(customerId));
    if (!d) { el.style.display = 'none'; return; }

    var tot = d.totals || {};
    var hasDevices = (tot.aps || 0) + (tot.switches || 0) + (tot.gateways || 0) + (tot.firewalls || 0) > 0;
    if (!hasDevices) { el.style.display = 'none'; return; }

    var devs = d.devices || {};
    var alerts = d.alerts || [];

    // Header with device count summary
    var html = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-4);">';
    html += '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;">' + t('hdr_network_inventory','Network') + '</div>';
    html += '<div style="display:flex;gap:var(--space-4);font-size:var(--font-xs);color:var(--text-muted);">';
    if (tot.aps) html += '<span>' + tot.aps + ' ' + t('lbl_aps','APs') + '</span>';
    if (tot.switches) html += '<span>' + tot.switches + ' ' + t('lbl_switches','Switches') + '</span>';
    if (tot.gateways) html += '<span>' + tot.gateways + ' ' + t('lbl_gateways','Gateways') + '</span>';
    if (tot.firewalls) html += '<span>' + tot.firewalls + ' ' + t('lbl_firewalls','Firewalls') + '</span>';
    if (tot.total_clients) html += '<span>' + tot.total_clients + ' ' + t('lbl_total_clients','Clients') + '</span>';
    html += '</div></div>';

    // Alerts
    if (alerts.length > 0) {
      html += '<div style="margin-bottom:var(--space-4);">';
      for (var i = 0; i < alerts.length; i++) {
        var alertColor = alerts[i].indexOf('outdated') >= 0 ? 'var(--orange)' : alerts[i].indexOf('port usage') >= 0 ? 'var(--orange)' : 'var(--red)';
        html += '<div style="font-size:var(--font-xs);color:' + alertColor + ';padding:4px 0;">' + esc(alerts[i]) + '</div>';
      }
      html += '</div>';
    }

    // APs table
    if (devs.aps && devs.aps.length) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);margin-top:var(--space-3);">' + t('lbl_aps','Access Points') + '</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_device','Device') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_model','Model') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_firmware','Firmware') + '</th>';
      html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_clients','Clients') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_status','Status') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_capacity','Capacity') + '</th>';
      html += '</tr></thead><tbody>';
      for (var i = 0; i < devs.aps.length; i++) {
        var ap = devs.aps[i];
        var statusColor = ap.status === 'online' ? 'var(--green)' : 'var(--red)';
        var fwColor = (ap.fw_status === 'warning' || ap.fw_status === 'critical') ? 'var(--orange)' : 'var(--text)';
        var clientPct = Math.min(100, Math.round((ap.clients / 60) * 100));
        var barColor = clientPct > 80 ? 'var(--red)' : clientPct > 60 ? 'var(--orange)' : 'var(--green)';
        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(ap.name) + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(ap.model) + '</td>';
        html += '<td style="padding:4px 8px;color:' + fwColor + ';">' + esc(ap.firmware) + (ap.fw_status === 'warning' || ap.fw_status === 'critical' ? '' : '') + '</td>';
        html += '<td style="padding:4px 8px;text-align:right;font-weight:600;">' + (ap.clients || 0) + '</td>';
        html += '<td style="padding:4px 8px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';margin-right:4px;"></span>' + esc(ap.status) + '</td>';
        html += '<td style="padding:4px 8px;min-width:80px;"><div style="background:var(--bg-alt);border-radius:4px;height:6px;overflow:hidden;"><div style="width:' + clientPct + '%;height:100%;background:' + barColor + ';border-radius:4px;"></div></div></td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // Switches table
    if (devs.switches && devs.switches.length) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);margin-top:var(--space-4);">' + t('lbl_switches','Switches') + '</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_device','Device') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_model','Model') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_firmware','Firmware') + '</th>';
      html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_ports','Ports') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_status','Status') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_port_usage','Port usage') + '</th>';
      html += '</tr></thead><tbody>';
      for (var i = 0; i < devs.switches.length; i++) {
        var sw = devs.switches[i];
        var statusColor = sw.status === 'online' ? 'var(--green)' : 'var(--red)';
        var fwColor = (sw.fw_status === 'warning' || sw.fw_status === 'critical') ? 'var(--orange)' : 'var(--text)';
        var portPct = sw.ports_total > 0 ? Math.round((sw.ports_used / sw.ports_total) * 100) : 0;
        var barColor = portPct > 85 ? 'var(--red)' : portPct > 70 ? 'var(--orange)' : 'var(--green)';
        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(sw.name) + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(sw.model) + '</td>';
        html += '<td style="padding:4px 8px;color:' + fwColor + ';">' + esc(sw.firmware) + (sw.fw_status === 'warning' || sw.fw_status === 'critical' ? '' : '') + '</td>';
        html += '<td style="padding:4px 8px;text-align:right;font-weight:600;">' + sw.ports_used + '/' + sw.ports_total + '</td>';
        html += '<td style="padding:4px 8px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';margin-right:4px;"></span>' + esc(sw.status) + '</td>';
        html += '<td style="padding:4px 8px;min-width:80px;"><div style="background:var(--bg-alt);border-radius:4px;height:6px;overflow:hidden;"><div style="width:' + portPct + '%;height:100%;background:' + barColor + ';border-radius:4px;"></div></div></td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // Gateways table
    if (devs.gateways && devs.gateways.length) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);margin-top:var(--space-4);">' + t('lbl_gateways','Gateways') + '</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_device','Device') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_model','Model') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_firmware','Firmware') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_status','Status') + '</th>';
      html += '</tr></thead><tbody>';
      for (var i = 0; i < devs.gateways.length; i++) {
        var gw = devs.gateways[i];
        var statusColor = gw.status === 'online' ? 'var(--green)' : 'var(--red)';
        var fwColor = (gw.fw_status === 'warning' || gw.fw_status === 'critical') ? 'var(--orange)' : 'var(--text)';
        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(gw.name) + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(gw.model) + '</td>';
        html += '<td style="padding:4px 8px;color:' + fwColor + ';">' + esc(gw.firmware) + (gw.fw_status === 'warning' || gw.fw_status === 'critical' ? '' : '') + '</td>';
        html += '<td style="padding:4px 8px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';margin-right:4px;"></span>' + esc(gw.status) + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // Firewalls table
    if (devs.firewalls && devs.firewalls.length) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);margin-top:var(--space-4);">' + t('lbl_firewalls','Firewalls') + '</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_device','Device') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_model','Model') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_firmware','Firmware') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_ha_status','HA') + '</th>';
      html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_vpn_tunnels','VPN') + '</th>';
      html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_sessions','Sessions') + '</th>';
      html += '</tr></thead><tbody>';
      for (var i = 0; i < devs.firewalls.length; i++) {
        var fw = devs.firewalls[i];
        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(fw.name) + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(fw.model) + '</td>';
        html += '<td style="padding:4px 8px;">' + esc(fw.firmware) + '</td>';
        html += '<td style="padding:4px 8px;">' + esc(fw.ha || 'standalone') + '</td>';
        html += '<td style="padding:4px 8px;text-align:right;font-weight:600;">' + (fw.vpn_tunnels || 0) + '</td>';
        html += '<td style="padding:4px 8px;text-align:right;">' + (fw.active_sessions || 0).toLocaleString() + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // Placeholder divs for FortiGate threat summary and firewall audit
    if (tot.firewalls > 0) {
      html += '<div id="fg-threat-summary-panel" style="margin-top:var(--space-4);"><div class="text-sm text-muted">' + t('msg_loading_threats','Loading threat summary...') + '</div></div>';
      html += '<div id="fg-firewall-audit-panel" style="margin-top:var(--space-4);"><div class="text-sm text-muted">' + t('msg_loading_fw_audit','Loading firewall audit...') + '</div></div>';
    }

    // Placeholder divs for UniFi client inventory and WiFi health
    html += '<div id="unifi-clients-section"></div>';
    html += '<div id="unifi-wifi-health-section"></div>';

    el.innerHTML = html;

    // Load FortiGate threat summary and firewall audit if firewalls exist
    if (tot.firewalls > 0) {
      _loadFgThreatSummary(customerId);
      _loadFgFirewallAudit(customerId);
    }

    // Load UniFi client inventory and WiFi health in parallel
    _loadUnifiClientsSection(customerId);
    _loadUnifiWifiHealthSection(customerId);

  } catch(e) {
    // Network inventory is optional — hide silently if it fails
    if (el) el.style.display = 'none';
    console.debug('Network inventory load failed:', e);
  }
}

// ── FortiGate Threat Summary ───────────────────────────────────────────────

async function _loadFgThreatSummary(customerId) {
  var el = document.getElementById('fg-threat-summary-panel');
  if (!el) return;
  try {
    var d = await apiFetch('/api/fortigate/threats/' + encodeURIComponent(customerId));
    if (!d || !d.summary) { el.style.display = 'none'; return; }

    // A refused log read reports unavailable with total=null. Rendering it would
    // print "Total: 0" — a firewall with a clean threat log nobody could read.
    if (d.unavailable || d.summary.total === null || d.summary.total === undefined) {
      el.style.display = '';
      el.innerHTML = '<div class="text-xs text-muted">' +
        esc(t('msg_block_unavailable','{block} could not be read, so this picture is incomplete.')
          .replace('{block}', t('hdr_threat_summary','Threat Summary'))) + '</div>';
      return;
    }

    var s = d.summary;
    var html = '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">' + t('hdr_threat_summary','Threat Summary') + ' <span style="font-weight:400;text-transform:none;">(' + d.period_days + ' ' + t('lbl_days','days') + ')</span></div>';

    // Summary badges
    html += '<div style="display:flex;gap:var(--space-3);margin-bottom:var(--space-3);flex-wrap:wrap;">';
    html += '<div style="padding:6px 12px;border-radius:var(--radius-md);background:rgba(239,68,68,0.15);color:var(--red);font-size:var(--font-xs);font-weight:600;">' + t('sev_critical','Critical') + ': ' + (s.critical || 0) + '</div>';
    html += '<div style="padding:6px 12px;border-radius:var(--radius-md);background:rgba(249,115,22,0.15);color:var(--orange);font-size:var(--font-xs);font-weight:600;">' + t('sev_high','High') + ': ' + (s.high || 0) + '</div>';
    html += '<div style="padding:6px 12px;border-radius:var(--radius-md);background:rgba(234,179,8,0.15);color:#eab308;font-size:var(--font-xs);font-weight:600;">' + t('sev_medium','Medium') + ': ' + (s.medium || 0) + '</div>';
    html += '<div style="padding:6px 12px;border-radius:var(--radius-md);background:rgba(128,128,128,0.12);color:var(--text-muted);font-size:var(--font-xs);font-weight:600;">' + t('sev_low','Low') + ': ' + (s.low || 0) + '</div>';
    html += '<div style="padding:6px 12px;border-radius:var(--radius-md);background:var(--bg-alt);color:var(--text);font-size:var(--font-xs);font-weight:600;">' + t('lbl_total','Total') + ': ' + (s.total || 0) + '</div>';
    html += '</div>';

    // By type
    if (d.by_type && Object.keys(d.by_type).length > 0) {
      html += '<div style="display:flex;gap:var(--space-3);margin-bottom:var(--space-3);font-size:var(--font-xs);color:var(--text-muted);">';
      var typeLabels = {ips:'IPS', virus:'Antivirus', botnet:'Botnet', webfilter:'Web Filter'};
      for (var tkey in d.by_type) {
        html += '<span>' + (typeLabels[tkey] || tkey) + ': <strong style="color:var(--text);">' + d.by_type[tkey] + '</strong></span>';
      }
      html += '</div>';
    }

    // Recent events table (top 5 visible, rest collapsible)
    var recent = d.recent || [];
    if (recent.length > 0) {
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_time','Time') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_type','Type') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_severity','Severity') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_source_ip','Source IP') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_attack','Attack') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_action','Action') + '</th>';
      html += '</tr></thead><tbody>';
      var sevColors = {critical:'var(--red)', high:'var(--orange)', medium:'#eab308', low:'var(--text-muted)'};
      for (var i = 0; i < recent.length; i++) {
        var ev = recent[i];
        var rowStyle = i >= 5 ? 'display:none;' : '';
        var rowClass = i >= 5 ? 'fg-threat-extra' : '';
        html += '<tr class="' + rowClass + '" style="border-bottom:1px solid var(--border-dim);' + rowStyle + '">';
        html += '<td style="padding:4px 8px;font-family:var(--mono);font-size:11px;">' + esc(ev.timestamp) + '</td>';
        html += '<td style="padding:4px 8px;">' + esc(ev.type) + '</td>';
        html += '<td style="padding:4px 8px;"><span style="color:' + (sevColors[ev.severity] || 'var(--text)') + ';font-weight:600;">' + esc(ev.severity) + '</span></td>';
        html += '<td style="padding:4px 8px;font-family:var(--mono);font-size:11px;">' + esc(ev.srcip) + '</td>';
        html += '<td style="padding:4px 8px;">' + esc(ev.attack) + '</td>';
        html += '<td style="padding:4px 8px;"><span style="color:' + (ev.action === 'blocked' || ev.action === 'block' || ev.action === 'drop' ? 'var(--green)' : 'var(--orange)') + ';">' + esc(ev.action) + '</span></td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
      if (recent.length > 5) {
        html += '<button class="btn btn-ghost" style="font-size:var(--font-xs);margin-top:var(--space-2);padding:2px 8px;" onclick="var rows=document.querySelectorAll(\'.fg-threat-extra\');var show=rows[0]&&rows[0].style.display===\'none\';rows.forEach(function(r){r.style.display=show?\'table-row\':\'none\';});this.textContent=show?\'' + t('btn_show_less','Show less') + '\':\'' + t('btn_show_all','Show all') + ' (' + recent.length + ')\';">' + t('btn_show_all','Show all') + ' (' + recent.length + ')</button>';
      }
    }

    el.innerHTML = html;
  } catch(e) {
    if (el) el.innerHTML = '';
    console.debug('Threat summary load failed:', e);
  }
}

// ── FortiGate Firewall Rule Audit ──────────────────────────────────────────

async function _loadFgFirewallAudit(customerId) {
  var el = document.getElementById('fg-firewall-audit-panel');
  if (!el) return;
  try {
    var d = await apiFetch('/api/fortigate/firewall-audit/' + encodeURIComponent(customerId));
    if (!d || d.total_rules === undefined) { el.style.display = 'none'; return; }

    // An unreachable firewall reports unavailable with score/total_rules = null
    // (which is not === undefined, so the guard above lets it through). Rendering
    // it would show "null / 100" in red with a green "no issues" — a broken,
    // reassuring panel for a firewall nobody could read.
    if (d.unavailable || d.total_rules === null || d.score === null) {
      el.style.display = '';
      el.innerHTML = '<div class="text-xs text-muted">' +
        esc(t('msg_block_unavailable','{block} could not be read, so this picture is incomplete.')
          .replace('{block}', t('hdr_firewall_audit','Firewall Rule Audit'))) + '</div>';
      return;
    }

    // Score color
    var scoreColor = d.score >= 90 ? 'var(--green)' : d.score >= 70 ? 'var(--orange)' : 'var(--red)';

    var html = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3);">';
    html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;">' + t('hdr_firewall_audit','Firewall Rule Audit') + '</div>';
    html += '<div style="display:flex;align-items:baseline;gap:4px;">';
    html += '<span style="font-size:24px;font-weight:700;color:' + scoreColor + ';">' + d.score + '</span>';
    html += '<span style="font-size:var(--font-xs);color:var(--text-muted);">/ 100</span>';
    html += '</div></div>';

    // Stats row
    html += '<div style="display:flex;gap:var(--space-4);margin-bottom:var(--space-3);font-size:var(--font-xs);color:var(--text-muted);">';
    html += '<span>' + t('lbl_total_rules','Total rules') + ': <strong style="color:var(--text);">' + d.total_rules + '</strong></span>';
    html += '<span>' + t('lbl_enabled','Enabled') + ': <strong style="color:var(--text);">' + d.enabled + '</strong></span>';
    html += '<span>' + t('lbl_disabled_rules','Disabled') + ': <strong style="color:var(--text);">' + d.disabled + '</strong></span>';
    html += '<span>' + t('lbl_unused_rules','Unused') + ': <strong style="color:var(--text);">' + d.unused_rules + '</strong></span>';
    html += '</div>';

    // Issues table
    var issues = d.issues || [];
    if (issues.length > 0) {
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_policy','Policy') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_issue','Issue') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_severity','Severity') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_detail','Detail') + '</th>';
      html += '</tr></thead><tbody>';
      var issuePillColors = {any_any:'var(--red)', no_logging:'var(--orange)', unused:'var(--blue)', scheduled:'var(--blue)'};
      var issuePillBg = {any_any:'rgba(239,68,68,0.15)', no_logging:'rgba(249,115,22,0.15)', unused:'rgba(59,130,246,0.15)', scheduled:'rgba(59,130,246,0.15)'};
      var sevPillColors = {critical:'var(--red)', warning:'var(--orange)', info:'var(--blue)'};
      var sevPillBg = {critical:'rgba(239,68,68,0.15)', warning:'rgba(249,115,22,0.15)', info:'rgba(59,130,246,0.15)'};
      var issueLabels = {any_any: t('issue_any_any','Any-Any'), no_logging: t('issue_no_logging','No Logging'), unused: t('issue_unused','Unused'), scheduled: t('issue_scheduled','Scheduled')};
      for (var i = 0; i < issues.length; i++) {
        var iss = issues[i];
        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">#' + iss.policy_id + ' ' + esc(iss.name) + '</td>';
        html += '<td style="padding:4px 8px;"><span style="display:inline-block;padding:2px 8px;border-radius:var(--radius-full);font-size:11px;font-weight:600;color:' + (issuePillColors[iss.issue] || 'var(--text)') + ';background:' + (issuePillBg[iss.issue] || 'var(--bg-alt)') + ';">' + (issueLabels[iss.issue] || iss.issue) + '</span></td>';
        html += '<td style="padding:4px 8px;"><span style="display:inline-block;padding:2px 8px;border-radius:var(--radius-full);font-size:11px;font-weight:600;color:' + (sevPillColors[iss.severity] || 'var(--text)') + ';background:' + (sevPillBg[iss.severity] || 'var(--bg-alt)') + ';">' + esc(iss.severity) + '</span></td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(iss.detail) + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    } else {
      html += '<div style="font-size:var(--font-xs);color:var(--green);padding:var(--space-2) 0;">' + t('msg_no_fw_issues','No firewall policy issues detected.') + '</div>';
    }

    el.innerHTML = html;
  } catch(e) {
    if (el) el.innerHTML = '';
    console.debug('Firewall audit load failed:', e);
  }
}

// ── UniFi Client Inventory Section ─────────────────────────────────────────

function _formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  var units = ['B','KB','MB','GB','TB'];
  var i = Math.floor(Math.log(bytes) / Math.log(1024));
  if (i >= units.length) i = units.length - 1;
  return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
}

function _signalBars(dbm) {
  if (dbm === null || dbm === undefined) return '';
  var abs = Math.abs(dbm);
  // Color: green >-60 (abs<60), orange -60 to -75 (60-75), red <-75 (>75)
  var color = abs < 60 ? 'var(--green)' : abs <= 75 ? 'var(--orange)' : 'var(--red)';
  // 4-bar indicator
  var bars = abs < 55 ? 4 : abs < 65 ? 3 : abs < 75 ? 2 : 1;
  var h = '';
  for (var b = 1; b <= 4; b++) {
    var ht = 4 + b * 3;
    var bg = b <= bars ? color : 'var(--border)';
    h += '<span style="display:inline-block;width:3px;height:' + ht + 'px;background:' + bg + ';border-radius:1px;margin-right:1px;vertical-align:bottom;"></span>';
  }
  h += '<span style="font-size:10px;color:var(--text-muted);margin-left:3px;">' + dbm + '</span>';
  return h;
}

async function _loadUnifiClientsSection(customerId) {
  var el = document.getElementById('unifi-clients-section');
  if (!el) return;
  try {
    var d = await apiFetch('/api/unifi/clients/' + encodeURIComponent(customerId));
    if (!d || !d.ok || !d.clients || d.clients.length === 0) return;

    var clients = d.clients;
    var wireless = d.wireless || 0;
    var wired = d.wired || 0;

    var summary = t('lbl_devices_summary', '{total} devices ({wireless} wireless, {wired} wired)')
      .replace('{total}', clients.length)
      .replace('{wireless}', wireless)
      .replace('{wired}', wired);

    var html = '<div style="margin-top:var(--space-5);border-top:1px solid var(--border);padding-top:var(--space-4);">';
    html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3);cursor:pointer;" onclick="var tb=document.getElementById(\'unifi-clients-table\');var btn=document.getElementById(\'unifi-clients-toggle\');if(tb.style.display===\'none\'){tb.style.display=\'table\';btn.textContent=t(\'lbl_hide_clients\',\'Hide clients\');}else{tb.style.display=\'none\';btn.textContent=t(\'lbl_show_clients\',\'Show clients\');}">';
    html += '<div>';
    html += '<span style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;">' + t('hdr_connected_clients','Connected Clients') + '</span>';
    html += '<span style="font-size:var(--font-xs);color:var(--text-muted);margin-left:var(--space-3);">' + esc(summary) + '</span>';
    html += '</div>';
    html += '<span id="unifi-clients-toggle" style="font-size:var(--font-xs);color:var(--blue);cursor:pointer;">' + t('lbl_show_clients','Show clients') + '</span>';
    html += '</div>';

    // Collapsible table (hidden by default)
    html += '<table id="unifi-clients-table" style="display:none;width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
    html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
    html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_hostname','Hostname') + '</th>';
    html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_ip_address','IP') + '</th>';
    html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_mac_address','MAC') + '</th>';
    html += '<th style="text-align:center;padding:4px 8px;">' + t('lbl_type','Type') + '</th>';
    html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_signal','Signal') + '</th>';
    html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_bandwidth','Bandwidth') + '</th>';
    html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_connected_to','Connected to') + '</th>';
    html += '</tr></thead><tbody>';

    for (var i = 0; i < clients.length; i++) {
      var c = clients[i];
      var displayName = esc(c.name || c.hostname || c.mac);
      var typeIcon = c.type === 'wireless'
        ? '<span title="WiFi" style="color:var(--blue);">&#9678;</span>'
        : '<span title="Ethernet" style="color:var(--text-muted);">&#9644;</span>';
      var signalHtml = c.type === 'wireless' ? _signalBars(c.signal) : '<span style="color:var(--text-dim);">&#8212;</span>';
      var bw = _formatBytes((c.rx_bytes || 0) + (c.tx_bytes || 0));

      html += '<tr style="border-bottom:1px solid var(--border-dim);">';
      html += '<td style="padding:4px 8px;font-weight:500;">' + displayName + '</td>';
      html += '<td style="padding:4px 8px;font-family:var(--mono);font-size:11px;">' + esc(c.ip || '') + '</td>';
      html += '<td style="padding:4px 8px;font-family:var(--mono);font-size:11px;color:var(--text-muted);">' + esc(c.mac || '') + '</td>';
      html += '<td style="padding:4px 8px;text-align:center;">' + typeIcon + '</td>';
      html += '<td style="padding:4px 8px;">' + signalHtml + '</td>';
      html += '<td style="padding:4px 8px;text-align:right;color:var(--text-muted);">' + bw + '</td>';
      html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(c.connected_to || '') + '</td>';
      html += '</tr>';
    }

    html += '</tbody></table></div>';
    el.innerHTML = html;
  } catch(e) {
    console.debug('UniFi clients load failed:', e);
  }
}

// ── UniFi WiFi Health Section ──────────────────────────────────────────────

async function _loadUnifiWifiHealthSection(customerId) {
  var el = document.getElementById('unifi-wifi-health-section');
  if (!el) return;
  try {
    var d = await apiFetch('/api/unifi/wifi-health/' + encodeURIComponent(customerId));
    if (!d || !d.ok) return;

    var aps = d.aps || [];
    var ssids = d.ssids || [];
    var alerts = d.alerts || [];

    if (aps.length === 0 && ssids.length === 0 && alerts.length === 0) return;

    var html = '<div style="margin-top:var(--space-5);border-top:1px solid var(--border);padding-top:var(--space-4);">';
    html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-3);">' + t('hdr_wifi_health','WiFi Health') + '</div>';

    // Alerts
    if (alerts.length > 0) {
      html += '<div style="margin-bottom:var(--space-4);">';
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">' + t('hdr_alerts_wifi','WiFi Alerts') + ' (' + alerts.length + ')</div>';
      for (var i = 0; i < Math.min(alerts.length, 15); i++) {
        var a = alerts[i];
        var alertColor = a.type === 'rogue_ap' ? 'var(--red)' : 'var(--orange)';
        var alertLabel = a.type === 'rogue_ap' ? t('lbl_rogue_ap','Rogue AP')
          : a.type === 'high_interference' ? t('lbl_high_interference','High interference')
          : t('lbl_poor_satisfaction','Poor satisfaction');
        html += '<div style="font-size:var(--font-xs);color:' + alertColor + ';padding:2px 0;">';
        html += '<span style="font-weight:600;">' + esc(alertLabel) + ':</span> ' + esc(a.message);
        html += '</div>';
      }
      if (alerts.length > 15) {
        html += '<div style="font-size:var(--font-xs);color:var(--text-muted);padding:2px 0;">+ ' + (alerts.length - 15) + ' more...</div>';
      }
      html += '</div>';
    }

    // Per-AP health table
    if (aps.length > 0) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">' + t('hdr_ap_health','Access Point Health') + '</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;margin-bottom:var(--space-4);">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_device','Device') + '</th>';
      html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_clients','Clients') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_channel','Channel') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_satisfaction','Satisfaction') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_status','Status') + '</th>';
      html += '</tr></thead><tbody>';

      for (var i = 0; i < aps.length; i++) {
        var ap = aps[i];
        var satPct = ap.satisfaction != null ? ap.satisfaction : null;
        var satColor = satPct === null ? 'var(--text-dim)' : satPct >= 80 ? 'var(--green)' : satPct >= 70 ? 'var(--orange)' : 'var(--red)';
        var satBar = '';
        if (satPct !== null) {
          satBar = '<div style="display:flex;align-items:center;gap:var(--space-2);">';
          satBar += '<div style="flex:1;max-width:80px;background:var(--bg-alt);border-radius:4px;height:6px;overflow:hidden;">';
          satBar += '<div style="width:' + satPct + '%;height:100%;background:' + satColor + ';border-radius:4px;"></div></div>';
          satBar += '<span style="color:' + satColor + ';font-weight:600;">' + satPct + '%</span></div>';
        } else {
          satBar = '<span style="color:var(--text-dim);">&#8212;</span>';
        }
        var statusColor = ap.status === 'online' ? 'var(--green)' : 'var(--red)';

        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(ap.name) + '</td>';
        html += '<td style="padding:4px 8px;text-align:right;font-weight:600;">' + (ap.clients || 0) + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(ap.channels || '') + '</td>';
        html += '<td style="padding:4px 8px;">' + satBar + '</td>';
        html += '<td style="padding:4px 8px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';margin-right:4px;"></span>' + esc(ap.status) + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // SSID list
    if (ssids.length > 0) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">' + t('hdr_ssid_list','SSIDs') + '</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_ssid','SSID') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_security','Security') + '</th>';
      html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_clients','Clients') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_status','Status') + '</th>';
      html += '</tr></thead><tbody>';

      for (var i = 0; i < ssids.length; i++) {
        var s = ssids[i];
        var enabledLabel = s.enabled ? t('lbl_enabled','Enabled') : t('lbl_disabled','Disabled');
        var enabledColor = s.enabled ? 'var(--green)' : 'var(--text-dim)';
        var guestBadge = s.is_guest ? ' <span style="background:var(--blue);color:#fff;padding:0 4px;border-radius:3px;font-size:10px;">' + t('lbl_guest','Guest') + '</span>' : '';

        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(s.name) + guestBadge + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(s.security) + '</td>';
        html += '<td style="padding:4px 8px;text-align:right;font-weight:600;">' + (s.clients || 0) + '</td>';
        html += '<td style="padding:4px 8px;color:' + enabledColor + ';">' + esc(enabledLabel) + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    html += '</div>';
    el.innerHTML = html;
  } catch(e) {
    console.debug('UniFi WiFi health load failed:', e);
  }
}

async function openLatestReport() {
  try {
    var d = await apiFetch('/api/latest-report');
    if (d && d.has_report) { openReportViewer(d.url); }
    else { showToast(t('msg_no_report','No report found. Run an audit first.'), 'warning'); }
  } catch(e) { showToast(t('status_error'), 'error'); }
}

function copyCustomerSummary() {
  // Build text summary from visible KPIs
  var name = document.getElementById('active-customer-name')?.textContent || '';
  var domain = document.getElementById('active-customer-domain')?.textContent || '';
  var grade = document.getElementById('active-customer-grade')?.textContent || '';
  var lines = [
    name + (domain ? ' (' + domain + ')' : ''),
    '---',
  ];
  // Get KPIs from customer detail gauges if visible
  document.querySelectorAll('#customer-detail-content .card').forEach(function(card) {
    var label = card.querySelector('[style*="uppercase"]');
    var value = card.querySelector('[style*="font-weight:800"], [style*="font-weight: 800"]');
    if (label && value) lines.push(label.textContent.trim() + ': ' + value.textContent.trim());
  });
  if (grade) lines.splice(1, 0, t('lbl_grade') + ': ' + grade);
  var text = lines.join('\n');
  navigator.clipboard.writeText(text).then(function() {
    showToast(t('msg_copied','Kopiert til utklippstavle'), 'success', 2000);
  }).catch(function() {
    showToast(t('err_copy_failed','Kunne ikke kopiere'), 'error');
  });
}

async function _loadCustomerNotes() {
  try {
    var d = await apiFetch('/api/customer/notes');
    var ta = document.getElementById('customer-notes-textarea');
    if (ta && d) { ta.value = d.notes || ''; }
    if (d && d.last_saved) {
      var el = document.getElementById('notes-save-status');
      if (el) el.textContent = t('msg_last_saved','Sist lagret') + ': ' + new Date(d.last_saved).toLocaleString('no-NO',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
    }
  } catch(e) { console.warn('Customer notes load failed:', e); }
}

async function _loadCustomerActivity(customerName) {
  var el = document.getElementById('customer-activity-panel');
  if (!el) return;
  try {
    var d = await apiFetch('/api/activity-log?limit=15&customer=' + encodeURIComponent(customerName));
    var entries = d.entries || [];
    var actionIcons = {
      audit_started:'\u25B6', audit_completed:'\u2713', report_generated:'',
      email_sent:'', remediation_updated:'', backup_created:'',
      customer_switched:'', settings_changed:'', itglue_uploaded:'',
    };
    var html = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3);">'
      + '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;">' + t('hdr_activity_log') + '</div>'
      + '<span style="font-size:var(--font-xs);color:var(--text-dim);">' + t('lbl_last_prefix','Last:') + ' ' + entries.length + '</span></div>';
    if (entries.length === 0) {
      html += '<div style="font-size:var(--font-sm);color:var(--text-dim);padding:var(--space-2) 0;">' + t('msg_no_notifications','Ingen hendelser') + '</div>';
    } else {
      entries.forEach(function(e) {
        var icon = actionIcons[e.action] || '';
        var ts = e.timestamp ? timeAgo(e.timestamp) : '';
        html += '<div style="display:flex;gap:var(--space-3);padding:var(--space-2) 0;border-bottom:1px solid var(--border);font-size:var(--font-xs);">'
          + '<span style="flex-shrink:0;">' + icon + '</span>'
          + '<span style="flex:1;color:var(--text);">' + esc(e.action.replace(/_/g,' ')) + (e.detail ? ' — <span style="color:var(--text-muted);">' + esc(e.detail) + '</span>' : '') + '</span>'
          + '<span style="color:var(--text-dim);white-space:nowrap;">' + ts + (e.user ? ' · ' + esc(e.user) : '') + '</span>'
          + '</div>';
      });
    }
    el.innerHTML = html;
  } catch(e) { el.innerHTML = ''; }
}

async function saveCustomerNotes() {
  var ta = document.getElementById('customer-notes-textarea');
  if (!ta) return;
  var st = document.getElementById('notes-save-status');
  try {
    var d = await apiFetch('/api/customer/notes', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({notes:ta.value})});
    if (d && d.ok && st) { st.textContent = t('msg_saved','Lagret') + ' ✓'; st.style.color = 'var(--green)'; setTimeout(function(){ st.style.color = ''; },2000); }
  } catch(e) { if (st) { st.textContent = t('status_error'); st.style.color = 'var(--red)'; } }
}

var _gaugeInstances = [];
function _renderGauges(riskScore, mfaPct, ssPct) {
  if (typeof Chart === 'undefined') return;
  _gaugeInstances.forEach(function(c){ c.destroy(); });
  _gaugeInstances = [];

  function makeGauge(canvasId, value, maxVal) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || value === null || value === undefined || value === '-') return;
    var v = parseFloat(value);
    var pct = Math.min(100, Math.max(0, (v / maxVal) * 100));
    var color = pct >= 80 ? '#3fb950' : pct >= 60 ? '#4d9fb5' : pct >= 40 ? '#d29922' : '#f85149';
    var bg = getComputedStyle(document.documentElement).getPropertyValue('--border').trim();
    var g = new Chart(canvas, {
      type: 'doughnut',
      data: {
        datasets: [{
          data: [pct, 100 - pct],
          backgroundColor: [color, bg],
          borderWidth: 0,
          circumference: 270,
          rotation: 225,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: true, cutout: '75%',
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
      },
      plugins: [{
        id: 'gaugeText',
        afterDraw: function(chart) {
          var ctx = chart.ctx;
          var w = chart.width, h = chart.height;
          ctx.save();
          ctx.font = 'bold 16px Inter, sans-serif';
          ctx.fillStyle = color;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(Math.round(v) + (maxVal === 100 ? '%' : ''), w/2, h/2 + 4);
          ctx.restore();
        }
      }]
    });
    _gaugeInstances.push(g);
  }

  makeGauge('gauge-risk', riskScore, 100);
  makeGauge('gauge-mfa', mfaPct, 100);
  makeGauge('gauge-ss', ssPct, 100);
}

async function _loadCustomerTrendChart(customerId) {
  if (typeof Chart === 'undefined') return;
  if (_detailChartInstance) { _detailChartInstance.destroy(); _detailChartInstance = null; }

  try {
    var d = await apiFetch('/api/trends/' + encodeURIComponent(customerId));
    var entries = d.entries || [];
    if (entries.length < 2) {
      var canvas = document.getElementById('chart-customer-trend');
      if (canvas) canvas.parentElement.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:250px;color:var(--text-dim);font-size:var(--font-sm);">'+t('msg_not_enough_data','Ikke nok data for trend (min. 2 audits)')+'</div>';
      return;
    }

    var labels = entries.map(function(e){ return e.date ? e.date.substring(0,10) : ''; });
    var textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim();
    var gridColor = getComputedStyle(document.documentElement).getPropertyValue('--border').trim();

    _detailChartInstance = new Chart(document.getElementById('chart-customer-trend'), {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: t('lbl_risk') || 'Risikoscore',
            data: entries.map(function(e){ return e.risk_score; }),
            borderColor: '#4d9fb5', backgroundColor: 'rgba(77,159,181,0.1)',
            fill: true, tension: 0.3, pointRadius: 4, pointHoverRadius: 6,
          },
          {
            label: 'MFA %',
            data: entries.map(function(e){ return e.mfa_pct; }),
            borderColor: '#3fb950', backgroundColor: 'transparent',
            borderDash: [4,4], tension: 0.3, pointRadius: 3,
          },
          {
            label: 'Secure Score %',
            data: entries.map(function(e){ return e.secure_score_pct; }),
            borderColor: '#d29922', backgroundColor: 'transparent',
            borderDash: [8,4], tension: 0.3, pointRadius: 3,
          },
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { position: 'bottom', labels: { color: textColor, padding: 16, font: { size: 12 }, usePointStyle: true } },
          tooltip: { backgroundColor: 'rgba(0,0,0,0.8)', titleFont: { size: 13 }, bodyFont: { size: 12 } },
        },
        scales: {
          y: { min: 0, max: 100, grid: { color: gridColor }, ticks: { color: textColor, font: { size: 11 } } },
          x: { grid: { display: false }, ticks: { color: textColor, font: { size: 11 }, maxRotation: 45 } },
        }
      }
    });
  } catch(e) { /* trend chart is non-critical */ }
}

// ── Customer Licenses (ALSO Cloud) ───────────────────────────────────────────

var _currentAlsoAccountId = '';

function loadCustomerLicensesFromActive() {
  // Find the current customer's also_account_id from cached overview
  if (!_overviewData || !_overviewData.customers) return;
  var active = _overviewData.customers.find(function(c){ return c.is_active; });
  if (active && active.also_account_id) {
    loadCustomerLicenses(active.also_account_id);
  } else {
    showToast(t('also_no_account_linked','This customer is not linked to ALSO Cloud'), 'warning');
  }
}

async function loadCustomerLicenses(accountId) {
  _currentAlsoAccountId = accountId;
  var box = document.getElementById('customer-detail-content');
  if (!box) return;

  box.innerHTML = '<div style="text-align:center;padding:48px;color:var(--text-muted);"><div class="loader" style="width:24px;height:24px;margin:0 auto 16px;"></div>' + t('msg_loading_licenses','Loading licenses...') + '</div>';

  try {
    var d = await apiFetch('/api/also/subscriptions/' + encodeURIComponent(accountId));
    var subs = d.subscriptions || [];

    if (subs.length === 0) {
      box.innerHTML = '<div class="card" style="padding:var(--space-8);text-align:center;color:var(--text-dim);">'
        + '<div style="font-size:48px;margin-bottom:var(--space-4);"></div>'
        + '<div style="font-size:var(--font-lg);font-weight:600;margin-bottom:var(--space-2);">' + t('also_no_licenses','No licenses found') + '</div>'
        + '<div style="font-size:var(--font-sm);">' + t('also_no_licenses_desc','This customer has no active subscriptions in ALSO Cloud.') + '</div>'
        + '</div>';
      return;
    }

    // Calculate totals
    var totalMonthly = 0;
    var totalSeats = 0;
    var activeCount = 0;
    subs.forEach(function(s) {
      var qty = s.Quantity || s.quantity || s.SeatCount || 0;
      var price = s.Price || s.price || s.UnitPrice || s.MonthlyPrice || 0;
      totalSeats += qty;
      totalMonthly += qty * price;
      var st = (s.AccountState || s.Status || s.status || '').toLowerCase();
      if (st === 'active' || st === 'completed') activeCount++;
    });

    var html = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-4);flex-wrap:wrap;gap:var(--space-3);">'
      + '<div style="font-size:var(--font-xl);font-weight:700;">' + t('nav_licenses','Licenses') + '</div>'
      + '<div style="display:flex;gap:var(--space-4);">'
      + '<div class="card" style="padding:var(--space-3) var(--space-4);text-align:center;min-width:100px;">'
      + '<div style="font-size:var(--font-2xl);font-weight:800;color:var(--blue);">' + subs.length + '</div>'
      + '<div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">' + t('also_subscriptions','Subscriptions') + '</div></div>'
      + '<div class="card" style="padding:var(--space-3) var(--space-4);text-align:center;min-width:100px;">'
      + '<div style="font-size:var(--font-2xl);font-weight:800;color:var(--green);">' + activeCount + '</div>'
      + '<div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">' + t('active') + '</div></div>'
      + (totalSeats > 0 ? '<div class="card" style="padding:var(--space-3) var(--space-4);text-align:center;min-width:100px;">'
      + '<div style="font-size:var(--font-2xl);font-weight:800;color:var(--purple);">' + totalSeats + '</div>'
      + '<div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">' + t('also_total_seats','Total Seats') + '</div></div>' : '')
      + '</div></div>';

    // Table
    html += '<div class="card" style="padding:0;overflow:hidden;">'
      + '<table style="width:100%;border-collapse:collapse;font-size:var(--font-sm);">'
      + '<thead><tr style="background:var(--bg-tertiary);border-bottom:1px solid var(--border);">'
      + '<th style="text-align:left;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('also_product','Product') + '</th>'
      + '<th style="text-align:left;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('vendor') + '</th>'
      + '<th style="text-align:center;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('qty') + '</th>'
      + '<th style="text-align:center;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('term') + '</th>'
      + '<th style="text-align:center;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('started') + '</th>'
      + '<th style="text-align:center;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('renews') + '</th>'
      + '<th style="text-align:center;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('also_status','Status') + '</th>'
      + '</tr></thead><tbody>';

    subs.forEach(function(s, i) {
      var name = s.ServiceDisplayName || s.ProductName || s.Name || s.SubscriptionName || s.OfferName || '-';
      var vendor = s.VendorDisplayName || s.Vendor || '';
      var started = s.BillingStartDate ? s.BillingStartDate.slice(0,10) : '-';
      var renews = s.ContractEndDate ? s.ContractEndDate.slice(0,10) : '-';
      var status = s.AccountState || s.Status || s.status || 'Active';
      var statusLower = status.toLowerCase();
      var statusColor = statusLower === 'active' ? 'var(--green)' : statusLower === 'suspended' ? 'var(--red)' : statusLower === 'completed' ? 'var(--green)' : 'var(--orange)';
      var rowBg = i % 2 === 0 ? 'transparent' : 'var(--bg-tertiary)';
      var subId = s.AccountId || '';

      // Calculate term from date span
      var termLabel = '-';
      var termIcon = '';
      // Determine term from service name patterns first (most reliable),
      // then fall back to ContractEndDate-based calculation using remaining time
      var nameLower = (name || '').toLowerCase();
      var serviceLower = (s.ServiceName || '').toLowerCase();

      // NCE products: Monthly if name contains "monthly", otherwise Annual (default NCE term)
      if (nameLower.indexOf('(nce)') !== -1) {
        if (nameLower.indexOf('monthly') !== -1) { termLabel = 'Monthly'; termIcon = ''; }
        else { termLabel = 'Annual'; termIcon = ''; }
      }
      // Monthly subscriptions (Letsignit, Printix, etc)
      else if (nameLower.indexOf('monthly') !== -1) { termLabel = 'Monthly'; termIcon = ''; }
      // Azure Plan / Reserved Instance
      else if (nameLower.indexOf('azure plan') !== -1 && nameLower.indexOf('reserved') === -1) { termLabel = 'Pay-as-you-go'; termIcon = ''; }
      else if (nameLower.indexOf('reserved') !== -1) { termLabel = 'Reserved'; termIcon = ''; }
      // Organization tenant (no term)
      else if (nameLower.indexOf('tenant') !== -1) { termLabel = 'Tenant'; termIcon = ''; }
      // Adobe yearly
      else if (nameLower.indexOf('adobe') !== -1) { termLabel = 'Annual'; termIcon = ''; }
      // Fallback: use ContractEndDate vs now to estimate remaining term
      else if (s.ContractEndDate) {
        var endD = new Date(s.ContractEndDate);
        var nowD = new Date();
        var remMonths = (endD.getFullYear() - nowD.getFullYear()) * 12 + (endD.getMonth() - nowD.getMonth());
        if (remMonths <= 1) { termLabel = 'Monthly'; termIcon = ''; }
        else if (remMonths <= 14) { termLabel = 'Annual'; termIcon = ''; }
        else if (remMonths <= 38) { termLabel = '3-Year'; termIcon = ''; }
        else { termLabel = 'Long-term'; termIcon = ''; }
      }

      // Days until renewal
      var renewHtml = renews;
      if (renews !== '-') {
        var daysLeft = Math.round((new Date(renews) - new Date()) / 86400000);
        var renewColor = daysLeft < 0 ? 'var(--red)' : daysLeft < 30 ? 'var(--orange)' : 'var(--text-muted)';
        renewHtml = renews + ' <span style="font-size:10px;color:'+renewColor+';">(' + (daysLeft < 0 ? 'expired' : daysLeft + 'd') + ')</span>';
      }

      var termColor = termLabel === 'Monthly' ? 'var(--blue)' : termLabel === 'Annual' ? 'var(--purple)' : 'var(--text-muted)';

      var qty = s.Quantity || s.quantity || s.SeatCount || 0;

      html += '<tr style="background:' + rowBg + ';border-bottom:1px solid var(--border);cursor:pointer;" onclick="alsoToggleSubDetail(this,\''+subId+'\')">'
        + '<td style="padding:var(--space-3) var(--space-4);font-weight:500;">' + esc(name) + '</td>'
        + '<td style="padding:var(--space-3) var(--space-4);color:var(--text-muted);">' + esc(vendor) + '</td>'
        + '<td style="padding:var(--space-3) var(--space-4);text-align:center;font-weight:700;">' + (qty > 0 ? qty : '<span style="color:var(--text-dim);">-</span>') + '</td>'
        + '<td style="padding:var(--space-3) var(--space-4);text-align:center;"><span style="font-size:var(--font-xs);font-weight:600;color:'+termColor+';">'+termIcon+' '+termLabel+'</span></td>'
        + '<td style="padding:var(--space-3) var(--space-4);text-align:center;font-size:var(--font-xs);color:var(--text-dim);">' + started + '</td>'
        + '<td style="padding:var(--space-3) var(--space-4);text-align:center;font-size:var(--font-xs);">' + renewHtml + '</td>'
        + '<td style="padding:var(--space-3) var(--space-4);text-align:center;"><span style="display:inline-block;padding:2px 10px;border-radius:var(--radius-full);font-size:var(--font-xs);font-weight:600;color:#fff;background:' + statusColor + ';">' + esc(status) + '</span></td>'
        + '</tr>';
      // Detail row (hidden by default, loaded on click)
      html += '<tr id="also-sub-'+subId+'" style="display:none;"><td colspan="7" style="padding:0;"></td></tr>';
    });

    html += '</tbody></table></div>';

    box.innerHTML = html;
  } catch(e) {
    box.innerHTML = '<div class="alert alert-error">' + t('also_license_error','Failed to load licenses') + ': ' + esc(e.message) + '</div>';
  }
}

// ── Unified Customer Dashboard ──────────────────────────────────────────────

async function loadUnifiedDashboard() {
  var custId = _customersActiveId;
  if (!custId) { showToast(t('err_no_active_customer'), 'warning'); return; }

  // Use the home view container
  showView('home');
  var el = document.getElementById('home-content') || document.querySelector('.view[id="view-home"] > div') || document.getElementById('view-home');
  if (!el) return;
  el.innerHTML = '<div class="loader" style="width:24px;height:24px;margin:48px auto;"></div>';

  var d = await apiFetch('/api/customer/' + encodeURIComponent(custId) + '/unified');
  if (!d || d.error) { el.innerHTML = '<div style="color:var(--red);text-align:center;padding:48px;">'+esc(d&&d.error||'Failed')+'</div>'; return; }

  var html = '';

  var a = d.audit || {};
  var _grade = a.risk_grade || '-';
  var _gv = {A:'var(--green)',B:'var(--blue)',C:'var(--orange)',D:'var(--red)',F:'var(--red)'}[_grade] || 'var(--text-muted)';
  // Label colour for the tinted hero tile — see --*-deep in app.css.
  var _gvd = {A:'var(--green-deep)',B:'var(--blue-deep)',C:'var(--orange-deep)',D:'var(--red-deep)',F:'var(--red-deep)'}[_grade] || 'var(--text-muted)';

  // ── Hero ──
  var _meta = [];
  if (d.domain) _meta.push('<span style="font-family:var(--mono);">'+esc(d.domain)+'</span>');
  if (d.also_account_id) _meta.push('ALSO ID ' + esc(String(d.also_account_id)));
  if (d.source) _meta.push(esc(d.source));
  html += '<div class="cd-hero">'
    + '<span class="cd-hero-tile" style="color:'+_gvd+';background:color-mix(in srgb, '+_gv+' 12%, transparent);border-color:color-mix(in srgb, '+_gv+' 40%, transparent);">'+esc(_grade)+'</span>'
    + '<span class="cd-hero-id"><span class="cd-hero-name">'+esc(d.customer_name)+' <span class="cd-active-pill">' + t('aktiv_kunde') + '</span></span>'
    + '<span class="cd-hero-meta">'+_meta.join(' · ')+'</span></span>'
    + '<div style="flex:1;"></div>'
    + '<button class="context-ghost" onclick="openLatestReport()">' + t('btn_open_report','Åpne rapport') + '</button>'
    + '<button class="context-ghost" onclick="showView(\'history\')">' + t('nav_history','Historikk') + '</button>'
    + '<button class="btn btn-sm" style="padding:7px 16px;font-size:12px;background:var(--blue-btn);color:#fff;border:none;border-radius:var(--radius-md);font-weight:600;cursor:pointer;" onclick="showView(\'audit\')">' + t('btn_run_audit','Kjør audit') + '</button>'
    + '</div>';

  // ── Integration chips ──
  function _cdChip(name, color, status, opts) {
    opts = opts || {};
    return '<div class="cd-chip"' + (opts.id ? ' id="'+opts.id+'"' : '') + ' style="border-top-color:'+color+';' + (opts.onclick ? 'cursor:pointer;' : '') + '"' + (opts.onclick ? ' onclick="'+opts.onclick+'"' : '') + '>'
      + '<div class="cd-chip-name">'+esc(name)+'</div>'
      + '<div class="cd-chip-status" style="color:'+color+';">'+esc(status)+'</div></div>';
  }
  var _m365c = 'var(--text-dim)', _m365l = t('st_not_configured');
  if (d.m365 && d.m365.TenantId) { _m365c = 'var(--green)'; _m365l = t('st_configured'); }
  if (d.m365 && d.m365.secret_status === 'expired') { _m365c = 'var(--red)'; _m365l = t('st_secret_expired'); }
  else if (d.m365 && d.m365.secret_status === 'warning') { _m365c = 'var(--orange)'; _m365l = t('st_secret_days_left').replace('{days}', d.m365.secret_days_left); }
  var _fgc = d.fortigate ? 'var(--green)' : 'var(--text-dim)';
  var _fgl = d.fortigate ? (d.fortigate.FortiGateHost || t('st_configured_2','Konfigurert')) : t('st_not_configured_2','Ikke konfigurert');
  var _ufc = d.unifi ? 'var(--green)' : 'var(--text-dim)';
  var _ufl = d.unifi ? (d.unifi.UniFiHost || t('st_configured_2','Konfigurert')) : t('st_not_configured_2','Ikke konfigurert');
  // A block the server could not read is null, exactly like a block with
  // nothing in it — the difference is in d.unavailable. Rendering both as
  // "Ikke koblet" is what let a database hiccup show a customer as clean.
  var _gone = d.unavailable || {};
  function _failed(block) { return Object.prototype.hasOwnProperty.call(_gone, block); }

  var _aoc = d.also ? 'var(--green)' : 'var(--text-dim)';
  var _aol = d.also ? (d.also.total_subscriptions + ' subs' + (d.also.mrr > 0 ? ' · ' + d.also.mrr.toFixed(0) + ' ' + (d.also.currency||'kr') : '')) : t('st_not_linked','Ikke koblet');
  if (d.also && (d.also.expired > 0 || d.also.expiring_90d > 0)) { _aoc = d.also.expired > 0 ? 'var(--red)' : 'var(--orange)'; }
  if (_failed('also')) { _aoc = 'var(--orange)'; _aol = t('st_read_failed'); }
  var _sshN = d.ssh_hosts ? d.ssh_hosts.length : 0;
  var _sshc = _sshN > 0 ? 'var(--green)' : 'var(--text-dim)';
  var _sshl = _sshN ? _sshN + ' ' + t('lbl_hosts_short') : t('st_none');
  if (_failed('ssh_hosts')) { _sshc = 'var(--orange)'; _sshl = t('st_read_failed'); }
  html += '<div class="cd-chips">'
    + _cdChip('M365', _m365c, _m365l, {onclick:"showView('home')"})
    + _cdChip('FortiGate', _fgc, _fgl)
    + _cdChip('UniFi', _ufc, _ufl)
    + _cdChip('ALSO', _aoc, _aol, {onclick:"loadCustomerLicensesFromActive()"})
    + _cdChip(t('lbl_ssh_hosts'), _sshc, _sshl, {onclick:"showView('hosts')"})
    + _cdChip('Hosting', 'var(--text-dim)', t('st_loading','Laster…'), {id:'unified-uniweb-status'})
    + '</div>';

  // ── What this page could not read ──
  // Placed above "Krever handling" on purpose. That band is built from the
  // audit figures, so when the audit read fails it renders empty — a customer
  // with no findings and a customer whose findings could not be loaded looked
  // identical, and the reassuring one was the wrong answer.
  var _blockNames = {audit: t('blk_audit'), ssh_hosts: t('blk_ssh_hosts'), also: t('blk_also')};
  var _goneKeys = Object.keys(_gone);
  if (_goneKeys.length) {
    html += '<div class="cd-action-band" style="border-left:3px solid var(--orange);">'
      + '<div class="cd-action-title">' + esc(t('hdr_incomplete_data')) + '</div>';
    _goneKeys.forEach(function(k) {
      var label = _blockNames[k] || k;
      html += '<div class="cd-action-row"><span class="cd-dot" style="background:var(--orange);"></span>'
        + '<span class="cd-action-text">'
        + esc(t('msg_block_unavailable').replace('{block}', label))
        + '</span></div>';
    });
    html += '</div>';
  }

  // ── «Krever handling» — cross-source findings, actioned where the decision is made ──
  var _find = [];
  if ((a.users_no_mfa || 0) > 0) _find.push({sev:'crit', text: t('find_users_no_mfa').replace('{count}', a.users_no_mfa), src:t('src_m365_audit'), label:t('lbl_see_audit'), onclick:"showView('audit')"});
  if (d.m365 && d.m365.secret_days_left != null && d.m365.secret_days_left <= 60) _find.push({sev: d.m365.secret_days_left <= 14 ? 'crit' : 'warn', text: t('find_secret_expiring').replace('{days}', d.m365.secret_days_left), src:'M365', label:'M365-status', onclick:"showView('home')"});
  if (d.also && d.also.expired > 0) _find.push({sev:'crit', text: t('find_subs_expired').replace('{count}', d.also.expired), src:'ALSO', label:t('lbl_see_subscriptions'), onclick:"loadCustomerLicensesFromActive()"});
  if (d.also && d.also.expiring_90d > 0) _find.push({sev:'warn', text: t('find_subs_expiring').replace('{count}', d.also.expiring_90d), src:'ALSO', label:t('lbl_see_subscriptions'), onclick:"loadCustomerLicensesFromActive()"});
  if (_find.length) {
    html += '<div class="cd-action-band"><div class="cd-action-title">' + esc(t('hdr_needs_action')) + '</div>';
    _find.forEach(function(f) {
      var _dc = f.sev === 'crit' ? 'var(--red)' : 'var(--orange)';
      html += '<div class="cd-action-row"><span class="cd-dot" style="background:'+_dc+';"></span>'
        + '<span class="cd-action-text">'+esc(f.text)+'</span>'
        + '<span class="cd-action-src">'+esc(f.src)+'</span>'
        + '<button class="cd-action-btn" onclick="'+f.onclick+'">'+esc(f.label)+'</button></div>';
    });
    html += '</div>';
  }

  // ── Two columns: audit summary + M365 creds | subscriptions + hosts ──
  html += '<div class="cd-cols"><div class="cd-col">';

  if (d.audit) {
    var _ssc = (a.secure_score_pct||0) >= 70 ? 'var(--green)' : (a.secure_score_pct||0) >= 40 ? 'var(--orange)' : 'var(--red)';
    var _mfc = (a.mfa_coverage_pct||0) >= 90 ? 'var(--green)' : (a.mfa_coverage_pct||0) >= 70 ? 'var(--orange)' : 'var(--red)';
    var _nmc = (a.users_no_mfa||0) > 0 ? 'var(--red)' : 'var(--green)';
    html += '<div class="cd-card"><div class="cd-card-title">' + t('siste_m365_audit') + ' <span class="sub">'+esc(a.audit_date||'')+'</span><span class="link" onclick="openLatestReport()">' + t('full_rapport') + '</span></div>'
      + '<div class="cd-stat-grid">'
      + '<div class="cd-stat"><div class="n" style="color:'+_gv+';">'+esc(_grade)+'</div><div class="l">' + t('grade') + '</div></div>'
      + '<div class="cd-stat"><div class="n">'+Math.round(a.risk_score||0)+'</div><div class="l">' + t('risikoscore') + '</div></div>'
      + '<div class="cd-stat"><div class="n" style="color:'+_ssc+';">'+Math.round(a.secure_score_pct||0)+'%</div><div class="l">' + t('secure_score_3') + '</div></div>'
      + '<div class="cd-stat"><div class="n" style="color:'+_mfc+';">'+Math.round(a.mfa_coverage_pct||0)+'%</div><div class="l">MFA</div></div>'
      + '<div class="cd-stat"><div class="n">'+(a.total_users||0)+'</div><div class="l">' + t('brukere') + '</div></div>'
      + '<div class="cd-stat"><div class="n" style="color:'+_nmc+';">'+(a.users_no_mfa||0)+'</div><div class="l">' + t('uten_mfa') + '</div></div>'
      + '</div></div>';
  }

  if (d.m365 && d.m365.TenantId) {
    var _cred = '<span>' + t('tenant') + ' <b class="mono">'+esc(d.m365.TenantId||'-')+'</b></span>'
      + '<span>' + t('domene_2') + ' <b class="mono">'+esc(d.domain||'-')+'</b></span>';
    if (d.m365.secret_days_left != null) {
      var _sc = (d.m365.secret_status==='expired'||d.m365.secret_status==='critical') ? 'var(--red)' : d.m365.secret_status==='warning' ? 'var(--orange)' : 'var(--green)';
      _cred += '<span>' + t('secret_utloeper') + ' <b style="color:'+_sc+';">'+d.m365.secret_days_left+' d</b></span>';
    }
    if (d.m365.cert_days_left != null) {
      var _cc2 = (d.m365.cert_status==='expired'||d.m365.cert_status==='critical') ? 'var(--red)' : d.m365.cert_status==='warning' ? 'var(--orange)' : 'var(--green)';
      _cred += '<span>' + t('sertifikat_utloeper') + ' <b style="color:'+_cc2+';">'+d.m365.cert_days_left+' d</b></span>';
    }
    html += '<div class="cd-card"><div class="cd-card-title">' + t('m_legitimasjon') + '</div><div class="cd-creds">'+_cred+'</div></div>';
  }

  html += '</div><div class="cd-col">';

  if (d.also && d.also.renewals && d.also.renewals.length) {
    var _rens = d.also.renewals;
    var _crit = _rens.filter(function(r){ return r.days_left != null && r.days_left <= 90; }).sort(function(x,y){ return (x.days_left||0) - (y.days_left||0); });
    var _restN = _rens.filter(function(r){ return r.days_left == null || r.days_left > 90; }).length;
    html += '<div class="cd-card"><div class="cd-card-title">' + t('abonnementer_2') + ' <span class="sub">'+_rens.length+' totalt'+(d.also.mrr > 0 ? ' · MRR '+d.also.mrr.toFixed(0)+' '+(d.also.currency||'kr') : '')+'</span></div>';
    if (_crit.length) {
      _crit.forEach(function(r, i) {
        var _dc = r.days_left < 0 ? 'var(--red)' : r.days_left <= 30 ? 'var(--red)' : 'var(--orange)';
        var _dl = r.days_left < 0 ? t('st_expired') : r.days_left + ' d';
        html += '<div class="cd-row'+(i === 0 ? ' first' : '')+'"><span class="grow">'+esc(r.service_display)+'</span><span class="vendor">'+esc(r.vendor||'')+'</span><span class="days" style="color:'+_dc+';">'+_dl+'</span></div>';
      });
    } else {
      html += '<div style="font-size:12px;color:var(--text-muted);padding:6px 0;">' + esc(t('msg_none_expiring_soon')) + '</div>';
    }
    if (_restN) html += '<div style="font-size:11px;color:var(--text-muted);padding-top:8px;border-top:1px solid var(--row-divider);margin-top:2px;">'+esc(t('lbl_others_over_90d').replace('{count}', _restN))+'</div>';
    html += '</div>';
  }

  if (d.ssh_hosts && d.ssh_hosts.length) {
    html += '<div class="cd-card"><div class="cd-card-title">' + t('hosts') + ' <span class="sub">'+d.ssh_hosts.length+'</span></div>';
    d.ssh_hosts.forEach(function(h, i) {
      var _hc = h.is_reachable ? 'var(--green)' : 'var(--text-dim)';
      html += '<div class="cd-row'+(i === 0 ? ' first' : '')+'"><span class="cd-dot" style="background:'+_hc+';"></span><span class="grow">'+esc(h.label||h.hostname)+'</span><span class="mono">'+esc(h.hostname)+':'+esc(String(h.port))+'</span><button class="cd-row-btn" onclick="showView(\'hosts\')">' + t('aapne') + '</button></div>';
    });
    html += '</div>';
  }

  html += '</div></div>';

  // Placeholder for async Uniweb detail card
  html += '<div id="unified-uniweb-card"></div>';

  el.innerHTML = html;

  // Fetch Uniweb data async
  _unifiedLoadUniwebCard(custId);
}

async function _unifiedLoadUniwebCard(custId) {
  var statusEl = document.getElementById('unified-uniweb-status');
  var cardEl = document.getElementById('unified-uniweb-card') || document.getElementById('customer-uniweb-panel');

  try {
    var uw = await apiFetch('/api/uniweb/customer/' + encodeURIComponent(custId));
    if (!uw || !uw.matched) {
      if (statusEl) {
        statusEl.style.borderTopColor = 'var(--text-dim)';
        statusEl.querySelector('div:last-child').textContent = t('st_not_linked','Ikke koblet');
        statusEl.querySelector('div:last-child').style.color = 'var(--text-dim)';
      }
      return;
    }

    // Update status card
    var uwColor = 'var(--green)';
    var uwLabel = (uw.domains ? uw.domains.length : 0) + ' domener';
    if (uw.monthly_total > 0) uwLabel += ' \u00b7 ' + uw.monthly_total.toFixed(0) + ' kr/mnd';
    if (statusEl) {
      statusEl.style.borderTopColor = uwColor;
      statusEl.querySelector('div:last-child').textContent = uwLabel;
      statusEl.querySelector('div:last-child').style.color = uwColor;
    }

    // Build detail card
    if (!cardEl) return;

    // Helper: check if a date string is within N days from now
    function _uwDaysUntil(dateStr) {
      if (!dateStr || dateStr === '-') return null;
      try {
        var d = new Date(dateStr);
        if (isNaN(d.getTime())) return null;
        return Math.ceil((d.getTime() - Date.now()) / 86400000);
      } catch(e) { return null; }
    }

    // Helper: Norwegian relative time for last_sync
    function _uwRelativeTime(dateStr) {
      if (!dateStr) return '';
      try {
        var d = new Date(dateStr);
        var diff = Math.floor((Date.now() - d.getTime()) / 1000);
        if (diff < 60) return 'akkurat n\u00e5';
        if (diff < 3600) return Math.floor(diff/60) + ' min siden';
        if (diff < 86400) return Math.floor(diff/3600) + (Math.floor(diff/3600) === 1 ? ' time' : ' timer') + ' siden';
        if (diff < 604800) return Math.floor(diff/86400) + (Math.floor(diff/86400) === 1 ? ' ' + t('unit_day','dag') : ' ' + t('unit_days','dager')) + ' ' + t('unit_ago','siden');
        return d.toLocaleDateString('nb-NO', {day:'2-digit',month:'short',year:'numeric'});
      } catch(e) { return dateStr; }
    }

    // Section divider helper
    function _uwSection(icon, title) {
      return '<div style="display:flex;align-items:center;gap:6px;font-weight:600;font-size:12px;margin:14px 0 6px;padding-bottom:4px;border-bottom:1px solid var(--border);">'
        + '<span style="font-size:14px;opacity:0.7;">' + icon + '</span>'
        + '<span>' + title + '</span></div>';
    }

    var h = '';
    h += '<div class="card" style="padding:16px;margin-bottom:16px;">';

    // Header with last updated
    h += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">';
    h += '<div style="display:flex;align-items:center;gap:8px;">';
    h += '<span style="font-size:18px;"></span>';
    h += '<span style="font-size:14px;font-weight:600;">' + t('hosting_uniweb') + '</span>';
    h += '</div>';
    h += '<div style="display:flex;flex-direction:column;align-items:flex-end;gap:2px;">';
    h += '<div style="font-size:11px;color:var(--text-muted);">' + esc(uw.account_name) + (uw.account_id ? ' \u00b7 ID: ' + esc(uw.account_id) : '') + '</div>';
    if (uw.last_sync) {
      h += '<div style="font-size:10px;color:var(--text-dim);" title="' + esc(new Date(uw.last_sync).toLocaleString('nb-NO')) + '">' + t('lbl_last_updated','Sist oppdatert') + ': ' + _uwRelativeTime(uw.last_sync) + '</div>';
    }
    h += '</div></div>';

    // Summary metrics row
    h += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:8px;margin-bottom:4px;">';

    h += '<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px;">';
    h += '<div style="font-size:18px;font-weight:700;">' + (uw.domains ? uw.domains.length : 0) + '</div>';
    h += '<div style="font-size:10px;color:var(--text-muted);">' + t('domener') + '</div></div>';

    h += '<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px;">';
    h += '<div style="font-size:18px;font-weight:700;">' + (uw.subscriptions ? uw.subscriptions.length : 0) + '</div>';
    h += '<div style="font-size:10px;color:var(--text-muted);">' + t('abonnementer') + '</div></div>';

    h += '<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px;">';
    h += '<div style="font-size:18px;font-weight:700;color:var(--blue);">' + (uw.monthly_total > 0 ? uw.monthly_total.toFixed(0) : '0') + '</div>';
    h += '<div style="font-size:10px;color:var(--text-muted);">' + t('kr_mnd') + '</div></div>';

    h += '<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px;">';
    h += '<div style="font-size:18px;font-weight:700;">' + (uw.email ? uw.email.length : 0) + '</div>';
    h += '<div style="font-size:10px;color:var(--text-muted);">' + t('e_post_2') + '</div></div>';

    h += '<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px;">';
    h += '<div style="font-size:18px;font-weight:700;">' + (uw.ssl ? uw.ssl.length : 0) + '</div>';
    h += '<div style="font-size:10px;color:var(--text-muted);">SSL</div></div>';

    h += '</div>';

    // Domains table
    if (uw.domains && uw.domains.length) {
      h += _uwSection('', 'Domener');
      h += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:10px;">';
      h += '<thead><tr style="border-bottom:1px solid var(--border);">';
      h += '<th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('domene') + '</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">DNS</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('registrert') + '</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('lbl_expires') + '</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('status') + '</th>';
      h += '</tr></thead><tbody>';
      uw.domains.forEach(function(dom) {
        var domName = dom.domain || dom[''] || Object.values(dom)[0] || '';
        var dnsCount = dom.dns && Array.isArray(dom.dns) ? dom.dns.length : null;
        var regDate = dom.registered || dom.registration_date || dom.created || '';
        var expiryDays = _uwDaysUntil(dom.expiry);
        var expiryStyle = '';
        if (expiryDays !== null && expiryDays <= 30) {
          expiryStyle = expiryDays <= 7 ? 'color:var(--red);font-weight:600;' : 'color:var(--orange);font-weight:600;';
        }
        h += '<tr style="border-bottom:1px solid var(--border);cursor:pointer;" onclick="uwToggleDns(this,\'' + esc(domName).replace(/'/g,'') + '\')">';
        h += '<td style="padding:4px 6px;color:var(--blue);"><span class="uw-dns-arrow" style="display:inline-block;transition:transform 0.15s;font-size:9px;margin-right:4px;">&#9654;</span>' + esc(domName) + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;color:var(--text-dim);">' + (dnsCount !== null ? '<span style="background:var(--bg);padding:1px 6px;border-radius:8px;font-size:10px;">' + dnsCount + '</span>' : '-') + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;color:var(--text-dim);font-size:10px;">' + esc(regDate || '-') + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;' + expiryStyle + '">' + esc(dom.expiry || '-') + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;">' + esc(dom.status || '-') + '</td>';
        h += '</tr>';
      });
      h += '</tbody></table>';
    }

    // Subscriptions table
    if (uw.subscriptions && uw.subscriptions.length) {
      h += _uwSection('', 'Abonnementer');
      h += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:10px;">';
      h += '<thead><tr style="border-bottom:1px solid var(--border);">';
      h += '<th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('tjeneste') + '</th>';
      h += '<th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('bruker_domene') + '</th>';
      h += '<th style="text-align:right;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('pris_mnd') + '</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('fornyelse') + '</th>';
      h += '</tr></thead><tbody>';
      uw.subscriptions.forEach(function(sub) {
        var price = sub['Price per month'] || sub.price_monthly || '-';
        var renewal = sub['Renewed until'] || sub.renewal_date || '-';
        var renewDays = _uwDaysUntil(renewal);
        var renewStyle = '';
        var renewBg = '';
        if (renewDays !== null && renewDays <= 30) {
          if (renewDays <= 0) {
            renewStyle = 'color:var(--red);font-weight:700;';
            renewBg = 'background:rgba(220,53,69,0.08);';
          } else if (renewDays <= 7) {
            renewStyle = 'color:var(--red);font-weight:600;';
            renewBg = 'background:rgba(220,53,69,0.05);';
          } else {
            renewStyle = 'color:var(--orange);font-weight:600;';
            renewBg = 'background:rgba(255,152,0,0.05);';
          }
        }
        h += '<tr style="border-bottom:1px solid var(--border);' + renewBg + '">';
        h += '<td style="padding:4px 6px;">' + esc(sub.service_type || sub['Service type'] || '-') + '</td>';
        h += '<td style="padding:4px 6px;">' + esc(sub.username_domain || sub['Username/domain'] || '-') + '</td>';
        h += '<td style="text-align:right;padding:4px 6px;font-family:var(--mono);">' + esc(price) + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;' + renewStyle + '">' + esc(renewal);
        if (renewDays !== null && renewDays <= 30) {
          h += ' <span style="font-size:9px;opacity:0.8;">(' + (renewDays <= 0 ? 'utl\u00f8pt)' : renewDays + 'd)') + '</span>';
        }
        h += '</td></tr>';
      });
      h += '</tbody></table>';
    }

    // Email table (proper table instead of just count)
    if (uw.email && uw.email.length) {
      h += _uwSection('', 'E-postkontoer (' + uw.email.length + ')');
      h += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:10px;">';
      h += '<thead><tr style="border-bottom:1px solid var(--border);">';
      h += '<th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('adresse') + '</th>';
      h += '<th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('type') + '</th>';
      h += '<th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('domene') + '</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('kvote') + '</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('status') + '</th>';
      h += '</tr></thead><tbody>';
      uw.email.forEach(function(em) {
        var addr = em.address || em.email || em.username || '-';
        var emType = em.type || em.product || '-';
        var emDomain = em.domain || (typeof addr === 'string' && addr.indexOf('@') > 0 ? addr.split('@')[1] : '-');
        var quota = em.quota || em.disk_quota || em.size || '';
        var emStatus = em.status || em.state || '-';
        var statusColor = emStatus === 'active' || emStatus === 'aktiv' ? 'var(--green)' : 'var(--text-dim)';
        h += '<tr style="border-bottom:1px solid var(--border);">';
        h += '<td style="padding:4px 6px;font-family:var(--mono);font-size:10px;">' + esc(addr) + '</td>';
        h += '<td style="padding:4px 6px;">' + esc(emType) + '</td>';
        h += '<td style="padding:4px 6px;color:var(--text-dim);">' + esc(emDomain) + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;color:var(--text-dim);">' + esc(quota || '-') + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;"><span style="color:' + statusColor + ';">' + esc(emStatus) + '</span></td>';
        h += '</tr>';
      });
      h += '</tbody></table>';
    }

    // SSL certificates
    if (uw.ssl && uw.ssl.length) {
      h += _uwSection('', 'SSL-sertifikater (' + uw.ssl.length + ')');
      h += '<details style="font-size:12px;margin-top:2px;"><summary style="cursor:pointer;color:var(--text-muted);font-size:11px;">' + t('vis_detaljer') + '</summary>';
      h += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:4px;">';
      h += '<thead><tr style="border-bottom:1px solid var(--border);">';
      h += '<th style="text-align:left;padding:3px 6px;color:var(--text-muted);font-size:10px;">' + t('domene') + '</th>';
      h += '<th style="text-align:left;padding:3px 6px;color:var(--text-muted);font-size:10px;">' + t('type') + '</th>';
      h += '<th style="text-align:center;padding:3px 6px;color:var(--text-muted);font-size:10px;">' + t('lbl_expires') + '</th>';
      h += '</tr></thead><tbody>';
      uw.ssl.forEach(function(cert) {
        var certDays = _uwDaysUntil(cert.expiry);
        var certStyle = '';
        if (certDays !== null && certDays <= 30) {
          certStyle = certDays <= 7 ? 'color:var(--red);font-weight:600;' : 'color:var(--orange);';
        }
        h += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:3px 6px;">' + esc(cert.domain || '') + '</td><td style="padding:3px 6px;color:var(--text-muted);">' + esc(cert.type || '-') + '</td><td style="text-align:center;padding:3px 6px;' + certStyle + '">' + esc(cert.expiry || '-') + '</td></tr>';
      });
      h += '</tbody></table></details>';
    }

    h += '</div>';
    cardEl.innerHTML = h;
  } catch (e) {
    if (statusEl) {
      statusEl.querySelector('div:last-child').textContent = t('lbl_error','Feil');
      statusEl.querySelector('div:last-child').style.color = 'var(--red)';
    }
  }
}

async function uwToggleDns(row, domain) {
  // Check if DNS row already exists below
  var existing = row.nextElementSibling;
  if (existing && existing.classList.contains('uw-dns-row')) {
    existing.remove();
    var arrow = row.querySelector('.uw-dns-arrow');
    if (arrow) arrow.style.transform = 'rotate(0deg)';
    return;
  }

  // Rotate arrow down
  var arrow = row.querySelector('.uw-dns-arrow');
  if (arrow) arrow.style.transform = 'rotate(90deg)';

  // Insert loading spinner row
  var cols = row.querySelectorAll('td').length || 5;
  var loadingHtml = '<tr class="uw-dns-row"><td colspan="' + cols + '" style="padding:10px 16px;background:var(--bg);text-align:center;">';
  loadingHtml += '<div class="loader" style="width:14px;height:14px;display:inline-block;vertical-align:middle;"></div>';
  loadingHtml += '<span style="margin-left:8px;font-size:11px;color:var(--text-muted);">' + t('msg_fetching_dns') + '</span>';
  loadingHtml += '</td></tr>';
  row.insertAdjacentHTML('afterend', loadingHtml);
  var loadingRow = row.nextElementSibling;

  // Fetch DNS records
  try {
    var d = await apiFetch('/api/uniweb/dns/' + encodeURIComponent(domain));

    var dnsHtml = '<td colspan="' + cols + '" style="padding:8px 16px;background:var(--bg);">';
    if (d && d.records && d.records.length > 0) {
      dnsHtml += '<table style="width:100%;font-size:10px;border-collapse:collapse;">';
      dnsHtml += '<thead><tr style="border-bottom:1px solid var(--border);">';
      dnsHtml += '<th style="text-align:left;padding:2px 6px;color:var(--text-muted);">' + t('vertsnavn') + '</th>';
      dnsHtml += '<th style="text-align:center;padding:2px 6px;color:var(--text-muted);">' + t('type') + '</th>';
      dnsHtml += '<th style="text-align:left;padding:2px 6px;color:var(--text-muted);">' + t('verdi') + '</th>';
      dnsHtml += '<th style="text-align:right;padding:2px 6px;color:var(--text-muted);">TTL</th>';
      dnsHtml += '</tr></thead><tbody>';
      d.records.forEach(function(r) {
        var dnsColors = { 'A': '#4a90d9', 'AAAA': '#4a90d9', 'MX': '#9b59b6', 'CNAME': '#27ae60', 'TXT': '#e67e22', 'NS': '#95a5a6', 'SRV': '#3498db', 'SOA': '#7f8c8d', 'PTR': '#2980b9' };
        var typeColor = dnsColors[r.type] || 'var(--text)';
        var typeBg = r.type === 'A' || r.type === 'AAAA' ? 'rgba(74,144,217,0.1)' : r.type === 'MX' ? 'rgba(155,89,182,0.1)' : r.type === 'CNAME' ? 'rgba(39,174,96,0.1)' : r.type === 'TXT' ? 'rgba(230,126,34,0.1)' : r.type === 'NS' ? 'rgba(149,165,166,0.1)' : 'transparent';
        dnsHtml += '<tr style="border-bottom:1px solid var(--border);">';
        dnsHtml += '<td style="padding:2px 6px;">' + esc(r.hostname) + '</td>';
        dnsHtml += '<td style="text-align:center;padding:2px 6px;"><span style="color:' + typeColor + ';font-weight:600;background:' + typeBg + ';padding:1px 6px;border-radius:3px;font-size:9px;">' + esc(r.type) + '</span></td>';
        dnsHtml += '<td style="padding:2px 6px;font-family:var(--mono);font-size:9px;word-break:break-all;">' + esc(r.value) + '</td>';
        dnsHtml += '<td style="text-align:right;padding:2px 6px;color:var(--text-dim);">' + r.ttl + '</td></tr>';
      });
      dnsHtml += '</tbody></table>';
    } else {
      dnsHtml += '<span style="color:var(--text-dim);font-size:11px;">' + t('ingen_dns_poster_funnet') + '</span>';
    }
    dnsHtml += '</td>';

    // Replace loading row content
    if (loadingRow && loadingRow.classList.contains('uw-dns-row')) {
      loadingRow.innerHTML = dnsHtml;
    }
  } catch(e) {
    if (loadingRow && loadingRow.classList.contains('uw-dns-row')) {
      loadingRow.innerHTML = '<td colspan="' + cols + '" style="padding:8px 16px;background:var(--bg);"><span style="color:var(--red);font-size:11px;">' + t('feil_ved_henting_av_dns') + '</span></td>';
    }
  }
}

async function alsoToggleSubDetail(rowEl, subId) {
  var detailRow = document.getElementById('also-sub-' + subId);
  if (!detailRow) return;
  if (detailRow.style.display !== 'none') {
    detailRow.style.display = 'none';
    return;
  }
  detailRow.style.display = '';
  var cell = detailRow.querySelector('td');
  cell.innerHTML = '<div style="padding:12px 16px;"><div class="loader" style="width:14px;height:14px;display:inline-block;"></div> ' + t('loading_details') + '</div>';

  var d = await apiFetch('/api/also/subscription/' + encodeURIComponent(subId));
  if (!d || d.error) {
    cell.innerHTML = '<div style="padding:12px 16px;color:var(--red);font-size:12px;">' + esc(d && d.error || 'Failed to load') + '</div>';
    return;
  }
  var s = d.subscription || d;
  var fields = s.Fields || s.fields || [];
  var items = s.PriceableItems || s.priceableItems || [];

  var html = '<div style="padding:12px 16px;background:var(--bg);border-left:3px solid var(--blue);">';
  html += '<table style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">';
  html += '<tr><td style="padding:2px 12px 2px 0;white-space:nowrap;">' + t('contract') + '</td><td style="padding:2px 0;font-weight:600;">' + esc(s.ContractId || '-') + '</td></tr>';
  if (s.VendorReferenceId) html += '<tr><td style="padding:2px 12px 2px 0;">' + t('vendor_ref') + '</td><td style="padding:2px 0;font-family:var(--mono);font-size:11px;">' + esc(s.VendorReferenceId) + '</td></tr>';
  if (s.DependencyServiceName) html += '<tr><td style="padding:2px 12px 2px 0;">' + t('depends_on') + '</td><td style="padding:2px 0;">' + esc(s.DependencyServiceName.split('_').pop() || s.DependencyServiceName) + '</td></tr>';
  html += '</table>';

  // Fields (seat counts, config) — ALSO uses Name/DisplayName/Value (PascalCase)
  if (fields.length) {
    html += '<div style="font-size:11px;font-weight:600;margin-bottom:6px;color:var(--text);">' + t('seats_configuration') + '</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:10px;">';
    fields.forEach(function(f) {
      var label = f.DisplayName || f.displayName || f.Name || f.name || f.FieldName || '?';
      var val = f.Value != null ? f.Value : f.value != null ? f.value : '-';
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += '<td style="padding:4px 8px;color:var(--text-muted);width:220px;white-space:nowrap;vertical-align:top;">' + esc(label) + '</td>';
      html += '<td style="padding:4px 8px;font-weight:600;color:var(--text);word-break:break-word;">' + esc(String(val)) + '</td>';
      html += '</tr>';
    });
    html += '</table>';
  }

  // PriceableItems (pricing) — ALSO uses PriceableItemDescription, PurchasePrice, SalesPrice, etc.
  if (items.length) {
    html += '<div style="font-size:11px;font-weight:600;margin-bottom:4px;color:var(--text);">' + t('pricing') + '</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;">';
    html += '<tr style="border-bottom:1px solid var(--border);">'
      + '<th style="text-align:left;padding:3px 6px;color:var(--text-muted);">' + t('item') + '</th>'
      + '<th style="text-align:left;padding:3px 6px;color:var(--text-muted);">' + t('type') + '</th>'
      + '<th style="text-align:right;padding:3px 6px;color:var(--text-muted);">' + t('purchase') + '</th>'
      + '<th style="text-align:right;padding:3px 6px;color:var(--text-muted);">' + t('sales') + '</th>'
      + '<th style="text-align:right;padding:3px 6px;color:var(--text-muted);">RRP</th>'
      + '<th style="text-align:left;padding:3px 6px;color:var(--text-muted);">' + t('currency') + '</th>'
      + '<th style="text-align:left;padding:3px 6px;color:var(--text-muted);">' + t('product') + '</th>'
      + '</tr>';
    items.forEach(function(p) {
      var pDesc = p.PriceableItemDescription || p.priceableItemDescription || p.Description || p.DisplayName || '-';
      var pType = p.ChargeType || p.chargeType || '-';
      var pBuy = p.PurchasePrice != null ? p.PurchasePrice : p.purchasePrice;
      var pSell = p.SalesPrice != null ? p.SalesPrice : p.salesPrice;
      var pRrp = p.SuggestedRetailPrice != null ? p.SuggestedRetailPrice : p.suggestedRetailPrice;
      var pCurr = p.Currency || p.currency || '';
      var pProd = p.ProductNumber || p.productNumber || p.MaterialNumber || p.materialNumber || '';
      var pPrepaid = p.PrepaidPeriodInMonths || p.prepaidPeriodInMonths;
      var typeLabel = pType;
      if (pPrepaid) typeLabel += ' (' + pPrepaid + 'mo)';
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += '<td style="padding:3px 6px;">' + esc(pDesc) + '</td>';
      html += '<td style="padding:3px 6px;font-size:10px;color:var(--text-dim);">' + esc(typeLabel) + '</td>';
      html += '<td style="padding:3px 6px;text-align:right;font-family:var(--mono);">' + (pBuy != null ? Number(pBuy).toFixed(2) : '-') + '</td>';
      html += '<td style="padding:3px 6px;text-align:right;font-family:var(--mono);font-weight:600;">' + (pSell != null ? Number(pSell).toFixed(2) : '-') + '</td>';
      html += '<td style="padding:3px 6px;text-align:right;font-family:var(--mono);color:var(--text-dim);">' + (pRrp != null ? Number(pRrp).toFixed(2) : '-') + '</td>';
      html += '<td style="padding:3px 6px;font-size:10px;">' + esc(pCurr) + '</td>';
      html += '<td style="padding:3px 6px;font-family:var(--mono);font-size:10px;color:var(--text-dim);">' + esc(pProd) + '</td>';
      html += '</tr>';
    });
    html += '</table>';
  }

  if (!fields.length && !items.length) {
    // Log the raw keys so we can debug
    html += '<div style="font-size:12px;color:var(--text-dim);">No Fields/PriceableItems found. Keys: ' + esc(Object.keys(s).join(', ')) + '</div>';
  }

  html += '</div>';
  cell.innerHTML = html;
}

// ── Theme toggle ────────────────────────────────────────────────────────────────
// ── Notification bell ─────────────────────────────────────────────────────────
var _notifOpen = false;
var _notifLastSeen = localStorage.getItem('sybr_notif_seen') || '';

function toggleNotifications() {
  _notifOpen = !_notifOpen;
  var dd = document.getElementById('notif-dropdown');
  dd.style.display = _notifOpen ? 'block' : 'none';
  if (_notifOpen) loadNotifications();
}

async function loadNotifications() {
  try {
    var d = await apiFetch('/api/activity-log?limit=20');
    var entries = d.entries || [];
    var list = document.getElementById('notif-list');
    if (entries.length === 0) {
      list.innerHTML = '<div style="padding:var(--space-8) var(--space-4);text-align:center;color:var(--text-dim);font-size:var(--font-sm);">' + t('msg_no_notifications','Ingen varsler') + '</div>';
      return;
    }
    // Filter out low-value noise
    var _hideActions = new Set(['settings_changed','customer_switched']);
    entries = entries.filter(function(e) { return !_hideActions.has(e.action); });

    var actionIcons = {
      audit_started: '\u25B6', audit_completed: '\u2713', report_generated: '',
      customer_added: '', itglue_uploaded: '',
      email_sent: '', backup_created: '',
      backup_restored: '', history_deleted: '',
      remediation_updated: '',
    };
    var actionLabels = {
      audit_started: t('notif_audit_started','Audit started'),
      audit_completed: t('notif_audit_completed','Audit completed'),
      report_generated: t('notif_report_generated','Report generated'),
      customer_added: t('notif_customer_added','Customer added'),
      email_sent: t('notif_email_sent','Email sent'),
      backup_created: t('notif_backup_created','Backup created'),
      backup_restored: t('notif_backup_restored','Backup restored'),
      history_deleted: t('notif_history_deleted','History deleted'),
      itglue_uploaded: t('notif_itglue_uploaded','Uploaded to IT Glue'),
      remediation_updated: t('notif_remediation_updated','Remediation updated'),
    };
    var actionColors = {
      audit_completed: 'var(--green)', report_generated: 'var(--blue)',
      backup_created: 'var(--green)', email_sent: 'var(--blue)',
    };
    if (entries.length === 0) {
      list.innerHTML = '<div style="padding:var(--space-8) var(--space-4);text-align:center;color:var(--text-dim);font-size:var(--font-sm);">' + t('msg_no_notifications','No notifications') + '</div>';
      return;
    }
    list.innerHTML = entries.map(function(e) {
      var icon = actionIcons[e.action] || '';
      var color = actionColors[e.action] || 'var(--text-muted)';
      var label = actionLabels[e.action] || e.action.replace(/_/g,' ').replace(/^\w/,function(c){return c.toUpperCase()});
      var timeStr = e.timestamp ? timeAgo(e.timestamp) : '';
      var isNew = _notifLastSeen && e.timestamp > _notifLastSeen;
      return '<div style="padding:var(--space-3) var(--space-4);border-bottom:1px solid var(--border);display:flex;gap:var(--space-3);align-items:flex-start;'+(isNew?'background:rgba(77,159,181,0.06);':'')+'" onmouseover="this.style.background=\'rgba(77,159,181,0.08)\'" onmouseout="this.style.background=\''+(isNew?'rgba(77,159,181,0.06)':'')+'\'">'+
        '<span style="font-size:16px;flex-shrink:0;margin-top:2px;color:'+color+';">'+icon+'</span>'+
        '<div style="flex:1;min-width:0;">'+
          '<div style="font-size:var(--font-sm);color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+esc(label)+
            (e.customer ? ' — <span style="color:var(--blue);">'+esc(e.customer)+'</span>' : '')+
          '</div>'+
          (e.detail ? '<div style="font-size:var(--font-xs);color:var(--text-dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+esc(e.detail)+'</div>' : '')+
          '<div style="font-size:var(--font-xs);color:var(--text-dim);margin-top:2px;">'+timeStr+(e.user ? ' — '+esc(e.user) : '')+'</div>'+
        '</div></div>';
    }).join('');
  } catch(e) { /* non-critical */ }
}

function markAllNotificationsRead() {
  _notifLastSeen = new Date().toISOString();
  localStorage.setItem('sybr_notif_seen', _notifLastSeen);
  document.getElementById('notif-badge').style.display = 'none';
  loadNotifications();
}

async function _checkVpnHeaderBadge() {
  try {
    var d = await apiFetch('/api/vpn/status');
    // Single status chip: prefix "VPN · " ahead of the live dot when a tunnel
    // is up (the old standalone #vpn-header-badge was merged into #conn-status).
    var prefix = document.getElementById('vpn-chip-prefix');
    if (!prefix) return;
    if (d && d.state === 'connected') {
      prefix.style.display = 'inline';
      var stats = d.stats || {};
      var tip = 'VPN ' + t('vpn_connected','Connected');
      if (d.interface) tip += ' (' + d.interface + ')';
      if (stats.local_ip) tip += '\nIP: ' + stats.local_ip;
      if (stats.tx_bytes || stats.rx_bytes) tip += '\nTX: ' + _formatBytes(stats.tx_bytes||0) + ' / RX: ' + _formatBytes(stats.rx_bytes||0);
      tip += '\n' + t('tip_click_to_manage','Click to manage');
      prefix.title = tip;
    } else {
      prefix.style.display = 'none';
    }
  } catch(e) { /* VPN badge poll — retries every 30s */ }
}

// Re-check VPN status periodically
setInterval(_checkVpnHeaderBadge, 30000);

async function _checkNotifBadge() {
  try {
    var d = await apiFetch('/api/activity-log?limit=5');
    var entries = d.entries || [];
    var newCount = 0;
    if (_notifLastSeen) {
      entries.forEach(function(e) { if (e.timestamp > _notifLastSeen) newCount++; });
    } else {
      newCount = entries.length;
    }
    var badge = document.getElementById('notif-badge');
    var bnavBadge = document.getElementById('bnav-alerts-badge');
    if (newCount > 0) {
      var _nb = newCount > 9 ? '9+' : String(newCount);
      badge.textContent = _nb; badge.style.display = 'block';
      if (bnavBadge) { bnavBadge.textContent = _nb; bnavBadge.style.display = 'block'; }
    } else {
      badge.style.display = 'none';
      if (bnavBadge) bnavBadge.style.display = 'none';
    }
  } catch(e) { /* notification poll — retries periodically */ }
}

// Close notification dropdown when clicking outside.
// Match the toggles by data attribute, not by aria-label: translatePage()
// rewrites aria-label from data-i18n-aria-label, so on any locale but
// Norwegian the selector missed the bell and the same click that opened the
// dropdown closed it again — the bell looked dead. The attribute also covers
// the bottom-nav toggle, which the old selector never matched in any locale.
document.addEventListener('click', function(e) {
  if (_notifOpen && !e.target.closest('#notif-dropdown') && !e.target.closest('[data-notif-toggle]')) {
    _notifOpen = false;
    document.getElementById('notif-dropdown').style.display = 'none';
  }
});

function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  localStorage.setItem('sybr-theme', next);
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const btn = document.getElementById('theme-toggle-btn');
  // The header logo is two <img> elements, header-logo-dark and
  // header-logo-light, swapped by .logo-dark/.logo-light under
  // [data-theme="light"] in app.css. Setting a src here is left over from when
  // it was one element: the lookup found nothing, the guard swallowed it, and
  // the logo simply never changed with the theme. CSS owns it; this does not.
  const footerLogo = document.getElementById('footer-logo');

  if (theme === 'light') {
    // Half-filled circles, the same glyph family as the visible theme toggle
    // in the avatar menu. This button was the last emoji left in the header.
    btn.textContent = '◑';
    btn.title = t('tip_switch_dark_theme', 'Bytt til mørkt tema');
    if (footerLogo) { footerLogo.src = '/branding/300 x 86.png'; footerLogo.style.opacity = '0.6'; }
  } else {
    btn.textContent = '◐';
    btn.title = t('tip_switch_light_theme', 'Bytt til lyst tema');
    if (footerLogo) { footerLogo.src = '/branding/300 x 86.png'; footerLogo.style.opacity = '0.5'; }
  }
}

// ── Activity log ─────────────────────────────────────────────────────────────
var _activityLogOffset = 0;
var _activityLogExpanded = true;

var _activityIcons = {
  audit_started:     '\u25B6',
  audit_completed:   '\u2713',
  report_generated:  '\uD83D\uDCC4',
  customer_added:    '\u2795',
  customer_switched: '\uD83D\uDD04',
  itglue_uploaded:   '\u2601',
  settings_changed:  '\u2699',
  email_sent:        '\u2709',
};

function _activityLabel(key) {
  return t('activity_' + key, key.replace(/_/g, ' '));
}

function toggleActivityLog() {
  var body = document.getElementById('activity-log-body');
  var toggle = document.getElementById('activity-log-toggle');
  if (!body) return;
  _activityLogExpanded = !_activityLogExpanded;
  body.style.display = _activityLogExpanded ? '' : 'none';
  toggle.innerHTML = _activityLogExpanded ? '&#9660;' : '&#9654;';
}

async function loadActivityLog(append) {
  var list = document.getElementById('activity-log-list');
  var more = document.getElementById('activity-log-more');
  if (!list) return;

  if (!append) {
    _activityLogOffset = 0;
    list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:8px 0;">' + t('msg_loading') + '</div>';
  }

  try {
    var d = await apiFetch('/api/activity-log?limit=10&offset=' + _activityLogOffset);
    var entries = d.entries || [];

    if (!append) list.innerHTML = '';

    if (entries.length === 0 && _activityLogOffset === 0) {
      list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:8px 0;">' + t('msg_no_activity_yet') + '</div>';
      more.innerHTML = '';
      return;
    }

    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      var icon = _activityIcons[e.action] || '\u2022';
      var label = _activityLabel(e.action);
      var ts = formatActivityTime(e.timestamp);
      var custHtml = e.customer ? '<span style="color:var(--blue);margin-left:6px;">' + esc(e.customer) + '</span>' : '';
      var detailHtml = e.detail ? '<span style="color:var(--text-dim);margin-left:6px;font-size:11px;">' + esc(e.detail) + '</span>' : '';

      var row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:13px;';
      row.innerHTML =
        '<span style="width:20px;text-align:center;flex-shrink:0;">' + icon + '</span>' +
        '<span style="font-weight:500;">' + esc(label) + '</span>' + custHtml + detailHtml +
        '<span style="margin-left:auto;color:var(--text-dim);font-size:11px;white-space:nowrap;">' + esc(ts) + '</span>';
      list.appendChild(row);
    }

    _activityLogOffset += entries.length;

    if (entries.length >= 10) {
      more.innerHTML = '<button class="btn btn-ghost" style="font-size:12px;padding:4px 12px;" onclick="loadActivityLog(true)">' + t('btn_show_more') + '</button>';
    } else {
      more.innerHTML = '';
    }
  } catch (ex) {
    if (!append) list.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:8px 0;">' + t('err_could_not_load_activity') + '</div>';
  }
}

function formatActivityTime(isoStr) {
  try {
    var d = new Date(isoStr);
    var now = new Date();
    var diffMs = now - d;
    var diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return t('msg_just_now');
    if (diffMin < 60) return t('msg_min_ago').replace('{count}', diffMin);
    var diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return t('msg_hours_ago').replace('{count}', diffH);
    var diffD = Math.floor(diffH / 24);
    if (diffD < 7) return t('msg_days_ago').replace('{count}', diffD);
    return d.toLocaleDateString('nb-NO', { day: '2-digit', month: '2-digit', year: 'numeric' }) + ' ' + d.toLocaleTimeString('nb-NO', { hour: '2-digit', minute: '2-digit' });
  } catch(ex) {
    return isoStr;
  }
}

// ── Mobile nav toggle ────────────────────────────────────────────────────────
// showView() already closes the mobile nav after a nav-item click. This file
// owns the open/close state and resize-driven auto-close.

// Must match the @media (max-width) breakpoint in app.css that collapses the
// top nav into a hamburger. Keep these in sync.
var _NAV_MOBILE_BREAKPOINT = 1100;

function toggleMobileNav() {
  var nav = document.getElementById('main-nav');
  if (nav) nav.classList.toggle('open');
}

// ── Mobile bottom nav + «Mer» sheet (frame 4a) ──────────────────────────────
function openMoreSheet() {
  var b = document.getElementById('more-backdrop');
  if (b) { b.classList.add('open'); document.addEventListener('keydown', _closeMoreSheetEsc); }
  _syncBottomNav('more');
}
function closeMoreSheet() {
  var b = document.getElementById('more-backdrop');
  if (b) b.classList.remove('open');
  document.removeEventListener('keydown', _closeMoreSheetEsc);
  var av = document.querySelector('.view.active');
  _syncBottomNav(av ? av.id.replace('view-', '') : 'overview');
}
function _closeMoreSheetEsc(e) { if (e.key === 'Escape') closeMoreSheet(); }
function _syncBottomNav(name) {
  // Map every view onto one of the five bottom-tab groups.
  var map = {
    overview: 'dashboard',
    customers: 'customers', home: 'customers', audit: 'customers', history: 'customers',
    files: 'customers', setup: 'customers', 'customer-detail': 'customers',
    network: 'network', vpn: 'network', tls: 'network', tailscale: 'network', provision: 'network',
    more: 'more',
  };
  var active = map[name] || '';
  document.querySelectorAll('.bnav-item').forEach(function(el) {
    el.classList.toggle('active', el.getAttribute('data-bnav') === active);
  });
}

window.addEventListener('resize', function() {
  if (window.innerWidth > _NAV_MOBILE_BREAKPOINT) {
    var nav = document.getElementById('main-nav');
    if (nav) nav.classList.remove('open');
  }
});

// Belt-and-suspenders: close mobile nav on any nav-btn click inside #main-nav,
// even if the click handler doesn't route through showView() (e.g. Integrasjoner
// dropdown items, future additions). Uses event delegation so we don't need to
// wire per-button handlers.
document.addEventListener('click', function(e) {
  var target = e.target.closest('#main-nav .nav-btn, #main-nav .nav-dropdown-menu-inner button');
  if (!target) return;
  // Only act below the breakpoint — desktop doesn't need this.
  if (window.innerWidth > _NAV_MOBILE_BREAKPOINT) return;
  var nav = document.getElementById('main-nav');
  if (nav) nav.classList.remove('open');
});

// ── Changelog modal ──────────────────────────────────────────────────────────
function parseChangelogMd(md) {
  var html = '', inList = false, inCode = false, lines = md.split('\n');
  function fmt(s) { return s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>'); }
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    if (line.match(/^```/)) { if (inList) { html += '</ul>'; inList = false; } if (inCode) { html += '</pre>'; inCode = false; } else { html += '<pre style="background:var(--bg);padding:8px;border-radius:4px;font-size:12px;overflow-x:auto;">'; inCode = true; } continue; }
    if (inCode) { html += esc(line) + '\n'; continue; }
    if (line.match(/^## /)) { if (inList) { html += '</ul>'; inList = false; } html += '<h2>' + fmt(line.replace(/^## /, '')) + '</h2>'; }
    else if (line.match(/^### /)) { if (inList) { html += '</ul>'; inList = false; } html += '<h3>' + fmt(line.replace(/^### /, '')) + '</h3>'; }
    else if (line.match(/^\s*- /)) { if (!inList) { html += '<ul>'; inList = true; } html += '<li>' + fmt(line.replace(/^\s*- /, '')) + '</li>'; }
    else if (line.match(/^\*\*/)) { if (inList) { html += '</ul>'; inList = false; } html += '<p>' + fmt(line) + '</p>'; }
    else if (line.trim() === '') { if (inList) { html += '</ul>'; inList = false; } }
    else { if (inList) { html += '</ul>'; inList = false; } html += '<p style="margin:4px 0;color:var(--text-muted);">' + fmt(line) + '</p>'; }
  }
  if (inList) html += '</ul>';
  if (inCode) html += '</pre>';
  return html;
}
var _changelogCache = null;
var _changelogFull = '';
var _changelogLatest = '';
var _changelogTab = 'latest';

function openChangelogModal() {
  document.getElementById('changelog-modal').classList.add('open');
  if (_changelogCache) { _renderChangelogTab(); return; }
  apiFetch('/api/changelog').then(function(data) {
    // Use server-rendered HTML if available, fall back to JS parser
    _changelogFull = data.html || parseChangelogMd(data.content || '');
    _changelogLatest = data.latest_html || _changelogFull;
    _changelogCache = true;
    _renderChangelogTab();
  }).catch(function() { document.getElementById('changelog-content').innerHTML = '<p style="color:var(--text-dim);">' + t('err_could_not_load_changelog') + '</p>'; });
}

function _renderChangelogTab() {
  var content = _changelogTab === 'latest' ? _changelogLatest : _changelogFull;
  var tabs = '<div style="display:flex;gap:8px;margin-bottom:16px;">'
    + '<button class="btn btn-sm ' + (_changelogTab === 'latest' ? 'btn-primary' : 'btn-ghost') + '" onclick="_changelogTab=\'latest\';_renderChangelogTab();">' + t('siste_endringer') + '</button>'
    + '<button class="btn btn-sm ' + (_changelogTab === 'all' ? 'btn-primary' : 'btn-ghost') + '" onclick="_changelogTab=\'all\';_renderChangelogTab();">' + t('alle_versjoner') + '</button>'
    + '</div>';
  document.getElementById('changelog-content').innerHTML = tabs + content;
}

function closeChangelogModal() { document.getElementById('changelog-modal').classList.remove('open'); }
function filterChangelog() {
  var q = (document.getElementById('changelog-search').value || '').toLowerCase();
  if (!q) { _renderChangelogTab(); return; }
  // Show full changelog when searching
  var content = _changelogFull;
  document.getElementById('changelog-content').querySelectorAll('h2,h3,p,li,strong,ul').forEach(function(el) {
    el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

// ── Keyboard shortcuts ──────────────────────────────────────────────────────
function openShortcutsModal() {
  document.getElementById('shortcuts-modal').classList.add('open');
}
function closeShortcutsModal() {
  document.getElementById('shortcuts-modal').classList.remove('open');
}
function closeAllModals() {
  document.querySelectorAll('.modal-backdrop.open').forEach(function(m) {
    m.classList.remove('open');
  });
}

// Close only the topmost open modal. Used by ESC so a nested confirmation
// dialog doesn't wipe out an underlying settings modal with unsaved edits.
function closeTopModal() {
  var open = document.querySelectorAll('.modal-backdrop.open');
  if (open.length === 0) return false;
  open[open.length - 1].classList.remove('open');
  return true;
}

// ── Focus trap for modals ────────────────────────────────────────────────────
// When a modal opens we: remember who had focus, move focus into the modal,
// and constrain Tab to the modal's focusable elements. On close we restore
// focus. Watches class changes on every .modal-backdrop via MutationObserver
// so existing modal open/close call-sites keep working unchanged.

var _focusReturnStack = [];   // stack of elements to restore focus to, per modal
var _activeTrappedModal = null;

function _focusableElementsIn(root) {
  if (!root) return [];
  var sel = 'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';
  return Array.from(root.querySelectorAll(sel))
    .filter(function(el) {
      // Filter out elements that are visually hidden
      return el.offsetParent !== null || el === document.activeElement;
    });
}

function _onModalOpened(modal) {
  _focusReturnStack.push(document.activeElement);
  _activeTrappedModal = modal;
  // Move focus into the modal's first focusable element. Run on next tick
  // so rendered children are present.
  setTimeout(function() {
    var focusables = _focusableElementsIn(modal);
    var target = focusables.find(function(el) { return el.dataset.autofocus !== undefined; })
              || focusables[0]
              || modal;
    if (target && target.focus) {
      if (!target.hasAttribute('tabindex') && target === modal) {
        modal.setAttribute('tabindex', '-1');
      }
      try { target.focus({ preventScroll: true }); } catch (_) { target.focus(); }
    }
  }, 0);
}

function _onModalClosed(/*modal*/) {
  // Determine the topmost remaining open modal (if any) and refocus its
  // previously-active element, otherwise restore the pre-modal focus.
  var prev = _focusReturnStack.pop();
  var stillOpen = document.querySelectorAll('.modal-backdrop.open');
  _activeTrappedModal = stillOpen.length ? stillOpen[stillOpen.length - 1] : null;
  if (prev && typeof prev.focus === 'function' && document.contains(prev)) {
    try { prev.focus({ preventScroll: true }); } catch (_) { prev.focus(); }
  }
}

function _handleModalTab(e) {
  if (e.key !== 'Tab' || !_activeTrappedModal) return;
  var focusables = _focusableElementsIn(_activeTrappedModal);
  if (focusables.length === 0) {
    e.preventDefault();
    return;
  }
  var first = focusables[0];
  var last = focusables[focusables.length - 1];
  var active = document.activeElement;
  if (e.shiftKey) {
    if (active === first || !_activeTrappedModal.contains(active)) {
      e.preventDefault();
      last.focus();
    }
  } else {
    if (active === last) {
      e.preventDefault();
      first.focus();
    }
  }
}
document.addEventListener('keydown', _handleModalTab, true);

// Watch every .modal-backdrop's class attribute so we detect open/close
// without changing callers. Observer is lazy-initialized on first run.
(function initModalFocusObserver() {
  function watch(el) {
    var wasOpen = el.classList.contains('open');
    new MutationObserver(function(muts) {
      for (var i = 0; i < muts.length; i++) {
        if (muts[i].attributeName !== 'class') continue;
        var nowOpen = el.classList.contains('open');
        if (nowOpen === wasOpen) continue;
        if (nowOpen) _onModalOpened(el);
        else _onModalClosed(el);
        wasOpen = nowOpen;
      }
    }).observe(el, { attributes: true, attributeFilter: ['class'] });
  }
  function scanAndWatch() {
    document.querySelectorAll('.modal-backdrop:not([data-focus-watched])').forEach(function(el) {
      el.dataset.focusWatched = '1';
      watch(el);
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scanAndWatch);
  } else {
    scanAndWatch();
  }
  // Also watch for modals inserted dynamically (rare but cheap to cover)
  new MutationObserver(scanAndWatch).observe(document.body, { childList: true, subtree: true });
})();

document.addEventListener('keydown', function(e) {
  var tag = (e.target.tagName || '').toLowerCase();
  var isInput = (tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable);
  var mod = e.ctrlKey || e.metaKey;

  // Escape — close only the topmost modal (so an outer settings modal's
  // unsaved edits survive closing a nested confirmation), then reset filters
  // if no modal was actually open.
  if (e.key === 'Escape') {
    if (closeTopModal()) return;
    if (_gradeFilter) { _gradeFilter = ''; filterOverview(); }
    return;
  }

  // Skip remaining shortcuts when focus is in an input
  if (isInput) return;

  // Arrow keys — navigate dashboard table rows
  if (currentView === 'overview' && (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter')) {
    var rows = document.querySelectorAll('#overview-table-content tbody tr');
    if (rows.length > 0) {
      var focused = document.querySelector('#overview-table-content tbody tr.kb-focused');
      var idx = focused ? Array.from(rows).indexOf(focused) : -1;
      if (e.key === 'ArrowDown') { idx = Math.min(idx + 1, rows.length - 1); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { idx = Math.max(idx - 1, 0); e.preventDefault(); }
      else if (e.key === 'Enter' && focused) { focused.click(); return; }
      rows.forEach(function(r) { r.classList.remove('kb-focused'); r.style.outline = ''; });
      if (rows[idx]) {
        rows[idx].classList.add('kb-focused');
        rows[idx].style.outline = '2px solid var(--blue)';
        rows[idx].style.outlineOffset = '-2px';
        rows[idx].scrollIntoView({ block: 'nearest' });
      }
      return;
    }
  }

  // ? — show shortcuts help
  if (e.key === '?' || (e.shiftKey && e.key === '?')) {
    e.preventDefault();
    openShortcutsModal();
    return;
  }

  // Ctrl/Cmd + number — navigation
  if (mod && !e.shiftKey) {
    var views = { '1': 'overview', '2': 'home', '3': 'customers', '4': 'files', '5': 'history' };
    if (views[e.key]) {
      e.preventDefault();
      showView(views[e.key]);
      return;
    }
    // Ctrl+, — open settings
    if (e.key === ',') {
      e.preventDefault();
      openSettings();
      return;
    }
  }

  // Ctrl/Cmd + K — open command palette (works even in inputs)
  if (mod && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    toggleCommandPalette();
    return;
  }

  // Ctrl/Cmd + Shift + T — toggle theme
  if (mod && e.shiftKey && (e.key === 'T' || e.key === 't')) {
    e.preventDefault();
    toggleTheme();
    return;
  }

  // Ctrl/Cmd + Shift + A — start audit
  if (mod && e.shiftKey && (e.key === 'A' || e.key === 'a')) {
    e.preventDefault();
    if (!auditRunning) startAudit();
    return;
  }
});

// ── Init ───────────────────────────────────────────────────────────────────────
applyTheme(localStorage.getItem('sybr-theme') || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));
// ── AI quick-prompt cards ────────────────────────────────────────────────────
// Previously built from an inline <script> in index.html. Moved out so we can
// drop 'unsafe-inline' from the CSP script-src directive. Uses addEventListener
// (not inline onclick/onmouseover attributes) so the final step — dropping
// script-src-attr 'unsafe-inline' too — is easier later.
function renderAiQuickPrompts() {
  var el = document.getElementById('ai-quick-prompts');
  if (!el) return;
  var prompts = [
    {icon:'\u{1F6E1}', label:'ai_prompt_fortigate',     labelFb:'Show FortiGate status',   prompt:'ai_prompt_fortigate_text',     promptFb:'Show status for all FortiGate firewalls'},
    {icon:'\u{1F5A5}', label:'ai_prompt_ssh',           labelFb:'SSH health check',        prompt:'ai_prompt_ssh_text',           promptFb:'List all SSH hosts and check health status'},
    {icon:'\u{1F512}', label:'ai_prompt_vpn',           labelFb:'VPN status',              prompt:'ai_prompt_vpn_text',           promptFb:'What is the current VPN status?'},
    {icon:'\u{1F4CB}', label:'ai_prompt_cis',           labelFb:'CIS compliance',          prompt:'ai_prompt_cis_text',           promptFb:'Run CIS compliance check on active customer'},
    {icon:'\u{1F4E1}', label:'ai_prompt_unifi',         labelFb:'UniFi sites',             prompt:'ai_prompt_unifi_text',         promptFb:'List all UniFi sites with device status'},
    {icon:'\u{1F527}', label:'ai_prompt_troubleshoot',  labelFb:'Troubleshoot',            prompt:'ai_prompt_troubleshoot_text',  promptFb:'Help me troubleshoot network issues for this customer'},
  ];
  el.innerHTML = '';
  prompts.forEach(function(p) {
    var card = document.createElement('div');
    card.style.cssText = 'padding:10px;border:1px solid var(--border);border-radius:6px;cursor:pointer;font-size:12px;transition:background 0.1s;';
    card.textContent = p.icon + ' ' + t(p.label, p.labelFb);
    card.addEventListener('click', function() {
      if (typeof aiQuickPrompt === 'function') {
        aiQuickPrompt(t(p.prompt, p.promptFb));
      }
    });
    card.addEventListener('mouseover', function() { card.style.background = 'var(--bg-card)'; });
    card.addEventListener('mouseout',  function() { card.style.background = ''; });
    el.appendChild(card);
  });
}

loadI18n().then(() => { renderAiQuickPrompts(); checkAuth(); });
// ── PWA install prompt ─────────────────────────────────────────────────────
// Two install paths:
//   Chromium / Edge / Android Chrome: `beforeinstallprompt` fires when the
//     engagement heuristic is satisfied — we stash the event and trigger
//     its .prompt() on button click.
//   Safari iOS: no programmatic install API. Show a modal with step-by-
//     step "Share → Add to Home Screen" guidance.
//
// Visibility rules:
//   - Hide entirely when already installed (display-mode: standalone OR
//     iOS navigator.standalone).
//   - On mobile, show the button by default so iOS users have an entry
//     point even without the beforeinstallprompt event.
//   - On desktop, only reveal once beforeinstallprompt has fired (the
//     browser knows the app is installable); otherwise hide to avoid a
//     button that does nothing useful.

var _deferredPwaInstall = null;

function _isStandalone() {
  if (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) return true;
  if (window.navigator && window.navigator.standalone) return true;  // iOS
  return false;
}
function _isMobile() {
  return window.matchMedia && window.matchMedia('(max-width: 1100px)').matches;
}
function _isIOS() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
}

function _refreshPwaInstallButton() {
  var btn = document.getElementById('pwa-install-btn');
  if (!btn) return;
  if (_isStandalone()) { btn.style.display = 'none'; return; }
  if (_deferredPwaInstall) { btn.style.display = 'inline-flex'; return; }
  // No stashed event. On mobile, still show so iOS users can see the hint.
  btn.style.display = _isMobile() ? 'inline-flex' : 'none';
}

window.addEventListener('beforeinstallprompt', function(e) {
  e.preventDefault();
  _deferredPwaInstall = e;
  _refreshPwaInstallButton();
});

window.addEventListener('appinstalled', function() {
  _deferredPwaInstall = null;
  var btn = document.getElementById('pwa-install-btn');
  if (btn) btn.style.display = 'none';
  if (typeof showToast === 'function') {
    showToast(t('msg_pwa_installed', 'Appen er installert'), 'success', 2500);
  }
});

// Initial decision on load + whenever viewport crosses the mobile breakpoint.
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _refreshPwaInstallButton);
} else {
  _refreshPwaInstallButton();
}
window.addEventListener('resize', _refreshPwaInstallButton);

async function promptPwaInstall() {
  if (_deferredPwaInstall) {
    _deferredPwaInstall.prompt();
    try {
      var choice = await _deferredPwaInstall.userChoice;
      if (choice && choice.outcome !== 'dismissed') {
        _deferredPwaInstall = null;
        _refreshPwaInstallButton();
      }
    } catch (_) {}
    return;
  }
  // No stashed event — show manual instructions. iOS gets a richer modal
  // with the actual share+add-to-home-screen icons so it's discoverable.
  _showPwaInstallHelp();
}

function _showPwaInstallHelp() {
  var existing = document.getElementById('pwa-help-modal');
  if (existing) { existing.style.display = 'flex'; return; }
  var ios = _isIOS();
  var bodyHtml = ios ? '' +
    '<ol style="font-size:14px;line-height:1.8;padding-left:20px;margin:12px 0;color:var(--text);">' +
    '  <li>' + esc(t('pwa_ios_step1', 'Trykk på')) + ' <strong style="color:var(--blue);">' + esc(t('pwa_ios_share', 'Del')) + '</strong> ' + esc(t('pwa_ios_step1_end', '(boksen med pil) i bunnen av nettleseren.')) + '</li>' +
    '  <li>' + esc(t('pwa_ios_step2', 'Bla ned og velg')) + ' <strong style="color:var(--blue);">' + esc(t('pwa_ios_add', 'Legg til på hjem-skjermen')) + '</strong>.</li>' +
    '  <li>' + esc(t('pwa_ios_step3', 'Bekreft navn og trykk')) + ' <strong style="color:var(--blue);">' + esc(t('pwa_ios_confirm', 'Legg til')) + '</strong>.</li>' +
    '</ol>' +
    '<div style="font-size:12px;color:var(--text-dim);margin-top:8px;">' + esc(t('pwa_ios_hint', 'Appen åpner i fullskjerm uten nettleser-kontroller etter installasjon.')) + '</div>'
    :
    '<p style="font-size:14px;color:var(--text);line-height:1.6;">' + esc(t('pwa_generic_help', 'Åpne nettleserens meny og velg «Installer app» eller «Legg til på startskjerm».')) + '</p>';

  var html = '' +
    '<div class="modal-backdrop open" id="pwa-help-modal" onclick="if(event.target===this)document.getElementById(\'pwa-help-modal\').style.display=\'none\'" style="display:flex;">' +
      '<div class="modal" style="max-width:380px;">' +
        '<div class="modal-title" style="display:flex;align-items:center;gap:8px;">' + esc(t('pwa_help_title', 'Installer Sybr HUB som app')) + '</div>' +
        bodyHtml +
        '<div class="modal-actions">' +
          '<button class="btn btn-primary" onclick="document.getElementById(\'pwa-help-modal\').style.display=\'none\'">' + esc(t('btn_ok', 'OK')) + '</button>' +
        '</div>' +
      '</div>' +
    '</div>';
  var tmp = document.createElement('div');
  tmp.innerHTML = html;
  document.body.appendChild(tmp.firstChild);
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js').then(function(reg) {
    // If a waiting SW is ready (new version installed on a previous visit),
    // offer the user a toast to activate it.
    if (reg.waiting) _notifySwUpdateAvailable(reg.waiting);
    reg.addEventListener('updatefound', function() {
      var installing = reg.installing;
      if (!installing) return;
      installing.addEventListener('statechange', function() {
        if (installing.state === 'installed' && navigator.serviceWorker.controller) {
          _notifySwUpdateAvailable(installing);
        }
      });
    });
  }).catch(function(){});
  // When the new SW takes over, reload so the UI matches the served assets.
  var _swReloadGuard = false;
  navigator.serviceWorker.addEventListener('controllerchange', function() {
    if (_swReloadGuard) return;
    _swReloadGuard = true;
    location.reload();
  });
}

function _notifySwUpdateAvailable(worker) {
  if (typeof showToastWithRetry === 'function') {
    showToastWithRetry(t('msg_pwa_update_available', 'Ny versjon tilgjengelig'), function() {
      worker.postMessage({ type: 'SKIP_WAITING' });
    });
  }
}
if ('Notification' in window && Notification.permission === 'default') { Notification.requestPermission(); }

// Scroll-to-top button
window.addEventListener('scroll', function() {
  var btn = document.getElementById('scroll-top-btn');
  if (!btn) return;
  if (window.scrollY > 300) { btn.style.display = 'block'; setTimeout(function(){ btn.style.opacity = '1'; btn.style.transform = 'translateY(0)'; }, 10); }
  else { btn.style.opacity = '0'; btn.style.transform = 'translateY(10px)'; setTimeout(function(){ if (window.scrollY <= 300) btn.style.display = 'none'; }, 250); }
});

// ── Session timeout warning ─────────────────────────────────────────────────
// Refresh shortly before the one-hour access cookie expires. The refresh
// cookie remains HttpOnly; a failed refresh is handled by the next API call.
setInterval(function() {
  if (_currentUser) fetch('/api/auth/refresh', {method:'POST'}).catch(function(){});
}, 50 * 60 * 1000);

// ── Onboarding guide ────────────────────────────────────────────────────────
(function() {
  if (localStorage.getItem('onboarding_done')) return;
  var steps = [
    { title: t('onboarding_welcome_title', 'Velkommen!'), text: t('onboarding_welcome_text', 'Velkommen til Sybr HUB! La oss komme i gang.') },
    { title: t('onboarding_add_customer_title', 'Legg til kunde'), text: t('onboarding_add_customer_text', 'Legg til din første kunde via Kunder → + Ny kunde') },
    { title: t('onboarding_run_audit_title', 'Kjør audit'), text: t('onboarding_run_audit_text', 'Kjør en audit fra Hjem-siden') },
    { title: t('onboarding_results_title', 'Se resultater'), text: t('onboarding_results_text', 'Se resultater i Dashboard og generer rapporter') }
  ];
  var current = 0;
  var overlay = document.createElement('div');
  overlay.className = 'onboarding-overlay';
  overlay.innerHTML =
    '<div class="onboarding-modal">' +
      '<h2 id="ob-title"></h2>' +
      '<p id="ob-text"></p>' +
      '<div class="onboarding-dots" id="ob-dots"></div>' +
      '<div class="onboarding-btns">' +
        '<button class="btn btn-ghost" id="ob-prev" data-i18n="btn_prev">' + t('forrige') + '</button>' +
        '<button class="btn btn-primary" id="ob-next" data-i18n="btn_next">' + t('neste') + '</button>' +
      '</div>' +
      '<label class="onboarding-check">' +
        '<input type="checkbox" id="ob-noshow"> <span data-i18n="onboarding_dont_show">' + t('ikke_vis_igjen') + '</span>' +
      '</label>' +
    '</div>';
  document.body.appendChild(overlay);
  var titleEl = document.getElementById('ob-title');
  var textEl = document.getElementById('ob-text');
  var dotsEl = document.getElementById('ob-dots');
  var prevBtn = document.getElementById('ob-prev');
  var nextBtn = document.getElementById('ob-next');
  function render() {
    titleEl.textContent = steps[current].title;
    textEl.textContent = steps[current].text;
    var dots = '';
    for (var i = 0; i < steps.length; i++) dots += '<span' + (i === current ? ' class="active"' : '') + '></span>';
    dotsEl.innerHTML = dots;
    prevBtn.style.display = current === 0 ? 'none' : '';
    nextBtn.textContent = current === steps.length - 1 ? t('btn_finish') : t('btn_next');
  }
  prevBtn.onclick = function() { if (current > 0) { current--; render(); } };
  nextBtn.onclick = function() {
    if (current < steps.length - 1) { current++; render(); }
    else {
      if (document.getElementById('ob-noshow').checked) localStorage.setItem('onboarding_done', '1');
      overlay.remove();
    }
  };
  render();
})();

// ── Fetch version on startup ──
(async function loadVersion() {
  try {
    const v = await apiFetch('/api/version');
    const label = v.version.startsWith('v') ? v.version : 'v' + v.version;
    const hdr = document.getElementById('header-version');
    const ftr = document.getElementById('footer-version');
    const apiLabel = document.getElementById('api-version-label');
    if (hdr) hdr.textContent = label;
    if (ftr) ftr.textContent = label;
    if (apiLabel) apiLabel.textContent = '— ' + label;
  } catch (e) { /* keep fallback text */ }
})();
// ── Log / Troubleshooting ─────────────────────────────────────────────────────
var _logAutoRefreshTimer = null;

function levelColor(lvl) {
  if (lvl === 'ERROR' || lvl === 'CRITICAL') return 'var(--red)';
  if (lvl === 'WARNING') return 'var(--orange)';
  if (lvl === 'INFO') return 'var(--blue)';
  return 'var(--text-dim)';
}

async function loadLogs() {
  var level = (document.getElementById('log-level-filter') || {}).value || 'WARNING';
  var box = document.getElementById('log-content');
  var data = await apiFetch('/api/logs?level=' + level + '&limit=300');
  if (!data) return;
  var logs = data.logs || [];
  if (logs.length === 0) {
    box.innerHTML = '<span style="color:var(--text-dim);">' + t('msg_no_log_entries') + '</span>';
    document.getElementById('log-stats').textContent = '0 ' + t('msg_entries');
    return;
  }
  var counts = {DEBUG:0, INFO:0, WARNING:0, ERROR:0, CRITICAL:0};
  var html = logs.map(function(e) {
    counts[e.level] = (counts[e.level] || 0) + 1;
    var t = e.ts.replace('T', ' ').replace(/\.\d+([Z+][^\s]*)$/, '').replace(/([Z+][^\s]*)$/, '');
    var color = levelColor(e.level);
    var lvlBadge = '<span style="color:' + color + ';font-weight:700;min-width:60px;display:inline-block;">[' + e.level + ']</span>';
    var loggerSpan = '<span style="color:var(--text-dim);font-size:11px;">' + esc(e.logger) + '</span>';
    return '<div style="padding:2px 0;border-bottom:1px solid var(--border);word-break:break-all;">' +
      '<span style="color:var(--text-dim);margin-right:8px;">' + t + '</span>' +
      lvlBadge + ' ' + loggerSpan + '<br>' +
      '<span style="padding-left:8px;color:' + color + ';">' + esc(e.msg) + '</span>' +
      '</div>';
  }).join('');
  box.innerHTML = html;
  box.scrollTop = box.scrollHeight;
  var statsArr = [];
  if (counts.ERROR || counts.CRITICAL) statsArr.push('<span style="color:var(--red);font-weight:700;">' + (counts.ERROR + counts.CRITICAL) + ' ' + t('msg_errors_count') + '</span>');
  if (counts.WARNING) statsArr.push('<span style="color:var(--orange);">' + counts.WARNING + ' ' + t('msg_warnings_count') + '</span>');
  statsArr.push(logs.length + ' ' + t('msg_entries_total'));
  document.getElementById('log-stats').innerHTML = statsArr.join(' &nbsp;·&nbsp; ');
}

async function clearLogs() {
  await apiFetch('/api/logs/clear', {method: 'POST'});
  loadLogs();
}

function copyLogs() {
  var box = document.getElementById('log-content');
  var text = box ? box.innerText : '';
  navigator.clipboard.writeText(text).then(function() {
    showToast(t('msg_log_copied','Log copied to clipboard'), 'success', 2000);
  });
}

function toggleLogAutoRefresh() {
  var checked = document.getElementById('log-auto-refresh').checked;
  if (checked) {
    _logAutoRefreshTimer = setInterval(loadLogs, 3000);
  } else {
    clearInterval(_logAutoRefreshTimer);
    _logAutoRefreshTimer = null;
  }
}

function toggleLogTabVisibility() {
  var show = document.getElementById('input-show-log-tab').checked;
  var btn = document.getElementById('nav-logs');
  if (btn) btn.style.display = show ? 'inline-flex' : 'none';
  localStorage.setItem('msptk_show_log_tab', show ? '1' : '0');
}

function toggleDocsTabVisibility() {
  var show = document.getElementById('input-show-docs-tab').checked;
  var btn = document.getElementById('nav-docs');
  if (btn) btn.style.display = show ? 'inline-flex' : 'none';
  localStorage.setItem('msptk_show_docs_tab', show ? '1' : '0');
}

// Restore tab visibility on page load
(function() {
  if (localStorage.getItem('msptk_show_log_tab') === '1') {
    var btn = document.getElementById('nav-logs');
    if (btn) btn.style.display = 'inline-flex';
  }
  if (localStorage.getItem('msptk_show_docs_tab') === '1') {
    var btn = document.getElementById('nav-docs');
    if (btn) btn.style.display = 'inline-flex';
  }
})();

// Check auth on load
checkAuth();


// ═══════════════════════════════════════════════════════════════════
// CODE SPLIT — remaining sections moved to separate files:
// ── Offline / Online connection indicator ────────────────────────────────────
(function() {
  var banner = document.createElement('div');
  banner.id = 'offline-banner';
  banner.style.cssText = 'display:none;position:fixed;top:0;left:0;right:0;z-index:9999;background:#dc2626;color:#fff;text-align:center;padding:6px 16px;font-size:13px;font-weight:600;transition:transform 0.3s;transform:translateY(-100%);';
  banner.innerHTML = '' + t('msg_offline','No connection — working offline');
  document.body.appendChild(banner);

  function goOffline() {
    banner.style.display = 'block';
    requestAnimationFrame(function() { banner.style.transform = 'translateY(0)'; });
  }
  function goOnline() {
    banner.style.transform = 'translateY(-100%)';
    setTimeout(function() { banner.style.display = 'none'; }, 300);
    showToast(t('msg_back_online','Connection restored'), 'success', 2000);
  }

  window.addEventListener('offline', goOffline);
  window.addEventListener('online', goOnline);
  if (!navigator.onLine) goOffline();
})();

//   app-infra.js        — Hosts Management, Backup, FortiGate, UniFi, Terminal
//   app-dashboard.js    — Alerts Dashboard, Customer Health Scores
//   app-also.js         — ALSO Renewal Action List
//   app-tailscale.js    — Tailscale Integration
//   app-tls.js          — TLS / Certificate Monitor
//   app-integrations.js — Show View override, Docs tab, ALSO Cloud Marketplace
// ═══════════════════════════════════════════════════════════════════
