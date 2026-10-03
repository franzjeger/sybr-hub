// ═══════════════════════════════════════════════════════════════════
// MARKUP HANDLERS: the handlers index.html's own controls name
// ═══════════════════════════════════════════════════════════════════
//
// Each script registers the handlers for the markup it builds; this one holds
// those for the static markup in index.html, which reaches into most
// features. Nothing imports it: the entry module loads it, and it sits above
// every script whose functions it calls.

import {setLanguage} from './app-i18n.js';
import {registerUiHandlers} from './app-handlers.js';
import {_custPage} from './app-state.js';
import {resolveConfirm} from './app-ui.js';
import {
  closeAvatarMenu, closeCommandPalette, doLogin, doLogout, doSetup, showView, switchNetSub,
  toggleAvatarMenu, toggleCommandPalette, toggleToolsMenu,
} from './app.js';
import {
  aiClearChat, aiSelectCustomerFromDropdown, aiSend, claudeCheckCli, claudeModeChanged,
  claudeSaveSettings, claudeTestConnection, dashUnifiRefresh, fgApiSave, fgApiTest, fgBootstrap,
  fgDownloadCredentials, fgPollAll, hostsAdd, hostsHealthAll, hostsLoad, liveSetInterval,
  provisionStart, runCmsScan, runCredentialTest, runDnsPentest, runPentest, runSegTest,
  runSmbEnum, runTakeoverCheck, runTlsAudit, sshShowExec, sshShowKeys, switchDashTab,
  termChangeFontSize, termConnect, termDisconnect, termModeChanged, unifiSmAuth,
  unifiSmLoadCoverage, unifiSmLoadSites, unifiSmSave, unifiSmSaveController,
  unifiSmTestController, vpnLoadProfiles, vpnShowCreate, vpnShowImport,
} from './app-infra.js';
import {
  billingExportCurrentTab, dashExportCurrentTab, dashToggleAutoRefresh, generateQBR,
  openOverviewTab, switchBillingTab,
} from './app-dashboard.js';
import {tsSaveConfig, tsTestConnection} from './app-tailscale.js';
import {
  alertRunCheckNow, alertSaveConfig, alertToggleMaster, alsoSaveConfig, alsoSyncCustomers,
  alsoTestConnection, gdapDiscoverCustomers, gdapImportSelected, gdapSaveConfig,
  gdapTestConnection, itglueSyncAllDocumentation, saveEmailSettings, saveITGlueSettings,
  saveWebhookSettings, taskSchedRefresh, testAutotask, testMyITProcess, toggleIntegConfig,
  uniwebSaveConfig, uniwebSync,
} from './app-integrations.js';
import {copyCode, copyDeviceUrl, openPrivateBrowser, startSetup} from './app-setup.js';
import {closeReportViewer, deleteSelectedRuns, runComparison} from './app-audit.js';
import {
  adminShowPane, backupEncryptionKey, closeAccountModal, closePermissionsModal, copyEncryptionKey,
  createBackup, createUser, openAccountModal, openAdmin, resetAuditDir, resetBrandColor,
  restoreBackup, restoreEncryptionKey, saveSettings, showAddUserForm, showChangePasswordModal,
  showMfaSettings, showRestoreKeyInput, testEmail, testWebhook, uploadLogo,
} from './app-settings.js';
import {loadConfigBackups, runNetworkQuickAudit, runSubnetScan, testITGlue} from './app-network.js';
import {
  bulkDeleteCustomers, bulkTagCustomers, clearBulkSelection, confirmITGlueOrgPick,
  copyOverviewToClipboard, customersFilter, executeITGlueUpload, exportCustomersJSON,
  exportDashboardExcel, migrateEncryption, newCustomerManual, newCustomerWithM365,
  openITGlueImport, openNewCustomer, runITGlueImport, submitManualCustomer, uploadToITGlue,
} from './app-customers.js';
import {
  clearLogs, closeMoreSheet, closeShortcutsModal, copyLogs, loadLogs, openMoreSheet,
  openShortcutsModal, promptPwaInstall, toggleLogAutoRefresh, toggleNotifications, toggleTheme,
} from './app-chrome.js';

// Handlers for the static markup in index.html.
registerUiHandlers({
  // Arguments come from data-* attributes on the control.
  toggleIntegConfig: function(el) { toggleIntegConfig(el.dataset.config); },
  switchNetSub: function(el) { switchNetSub(el, el.dataset.tab); },
  switchDashTab: function(el) { switchDashTab(el, el.dataset.tab); },
  openOverviewTab: function(el) { openOverviewTab(el.dataset.tab); },
  termChangeFontSize: function(el) { termChangeFontSize(Number(el.dataset.delta)); },
  resolveConfirm: function(el) { resolveConfirm(el.dataset.answer === 'true'); },
  // On the customer page's Detaljer: that page's customer.
  uploadToITGlue: function(el) { uploadToITGlue(el, _custPage.id); },
  dashToggleAutoRefresh: function(el) { dashToggleAutoRefresh(el); },
  scrollToTop: function() { window.scrollTo({top: 0, behavior: 'smooth'}); },
  // Menus that close themselves before acting.
  toggleAvatarMenu: function(el, event) { toggleAvatarMenu(event); },
  moreSheetShowView: function(el) { closeMoreSheet(); showView(el.dataset.view); },
  moreSheetOpenAdmin: function() { closeMoreSheet(); openAdmin(); },
  moreSheetOpenAccount: function() { closeMoreSheet(); openAccountModal(); },
  moreSheetLogout: function() { closeMoreSheet(); doLogout(); },
  avatarOpenAccount: function() { closeAvatarMenu(); openAccountModal(); },
  avatarOpenShortcuts: function() { closeAvatarMenu(); openShortcutsModal(); },
  avatarOpenAdmin: function() { closeAvatarMenu(); openAdmin(); },
  avatarOpenHelp: function() { closeAvatarMenu(); showView('docs'); },
  accountShowMfaSettings: function() { closeAccountModal(); showMfaSettings(); },
  accountShowChangePassword: function() { closeAccountModal(); showChangePasswordModal(); },
  // Administrasjon: the rail, and a signpost elsewhere that names a pane.
  adminShowPane: function(el) { adminShowPane(el.dataset.pane); },
  openAdmin: function(el) { openAdmin(el.dataset.pane); },
  // Modal backdrops: only a click on the backdrop itself closes them.
  deactivateOnBackdrop: function(el, event) { if (event.target === el) el.classList.remove('active'); },
  cancelConfirmOnBackdrop: function(el, event) { if (event.target === el) resolveConfirm(false); },
  closeShortcutsModalOnBackdrop: function(el, event) { if (event.target === el) closeShortcutsModal(); },
  closePermissionsModalOnBackdrop: function(el, event) { if (event.target === el) closePermissionsModal(); },
  closeMoreSheetOnBackdrop: function(el, event) { if (event.target === el) closeMoreSheet(); },
  closeCommandPaletteOnBackdrop: function(el, event) { if (event.target === el) closeCommandPalette(); },
  closeAccountModalOnBackdrop: function(el, event) { if (event.target === el) closeAccountModal(); },
  // change / input
  alertSaveConfig: function() { alertSaveConfig(); },
  alertToggleMaster: function(el) { alertToggleMaster(el.checked); },
  hostsLoad: function() { hostsLoad(); },
  toggleLogAutoRefresh: function() { toggleLogAutoRefresh(); },
  termModeChanged: function() { termModeChanged(); },
  setLanguage: function(el) { setLanguage(el.value); },
  liveSetInterval: function(el) { liveSetInterval(el.value); },
  claudeModeChanged: function() { claudeModeChanged(); },
  aiSelectCustomerFromDropdown: function(el) { aiSelectCustomerFromDropdown(el); },
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
  toggleToolsMenu: function(el, event) { toggleToolsMenu(event); },
  switchBillingTab: function(el) { switchBillingTab(el, el.dataset.tab); },
  billingExportCurrentTab: function() { billingExportCurrentTab(); },
  toggleCommandPalette: function() { toggleCommandPalette(); },
  toggleNotifications: function() { toggleNotifications(); },
  promptPwaInstall: function() { promptPwaInstall(); },
  toggleTheme: function() { toggleTheme(); },
  doLogout: function() { doLogout(); },
  dashExportCurrentTab: function() { dashExportCurrentTab(); },
  exportDashboardExcel: function() { exportDashboardExcel(); },
  copyOverviewToClipboard: function(el) { copyOverviewToClipboard(el); },
  generateQBR: function() { generateQBR(); },
  closeAccountModal: function() { closeAccountModal(); },
  closePermissionsModal: function() { closePermissionsModal(); },
  closeShortcutsModal: function() { closeShortcutsModal(); },
  aiClearChat: function() { aiClearChat(); },
  aiSend: function() { aiSend(); },
  alertRunCheckNow: function() { alertRunCheckNow(); },
  alsoSaveConfig: function() { alsoSaveConfig(); },
  alsoSyncCustomers: function() { alsoSyncCustomers(); },
  alsoTestConnection: function() { alsoTestConnection(); },
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
  loadLogs: function() { loadLogs(); },
  migrateEncryption: function() { migrateEncryption(); },
  openITGlueImport: function() { openITGlueImport(); },
  openNewCustomer: function() { openNewCustomer(); },
  newCustomerWithM365: function() { newCustomerWithM365(); },
  newCustomerManual: function() { newCustomerManual(); },
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
