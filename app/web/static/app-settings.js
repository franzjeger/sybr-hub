// ═══════════════════════════════════════════════════════════════════
// SETTINGS — webhooks, branding, version, users & backup
// ═══════════════════════════════════════════════════════════════════

import {esc} from './app-esc.js';
import {_lang, t} from './app-i18n.js';
import {icon} from './app-icons.js';
import {registerUiHandlers} from './app-handlers.js';
import {onViewShown} from './app-hooks.js';
import {_currentUser, canOpenView} from './app-state.js';
import {timeAgo} from './app-format.js';
import {showConfirm, showToast, showTypedConfirm} from './app-ui.js';
import {apiFetch} from './app-api.js';
import {checkAuth, currentView, passwordMeetsRule, showView, syncRoute} from './app.js';
import {claudeLoadSaved, unifiSmLoadSaved} from './app-infra.js';
import {dashLoadArchive} from './app-dashboard.js';
import {alertLoadConfig, loadIntegrationStatus, taskSchedRefresh} from './app-integrations.js';

// Handlers for the user list, the password dialog and the customer-access
// panel (see registerUiHandlers in app-handlers.js).
registerUiHandlers({
  chooseLogoFile: function() { chooseLogoFile(); },
  logoFileChosen: function() { logoFileChosen(); },
  doChangePassword: function() { doChangePassword(); },
  changeUserRole: function(el) { changeUserRole(el.dataset.userId, el.value); },
  editUserCustomers: function(el) { editUserCustomers(el.dataset.userId, el.dataset.displayName); },
  deleteUser: function(el) { deleteUser(el.dataset.userId, el.dataset.username); },
  setUserCapability: function(el) { setUserCapability(el.dataset.userId, el.dataset.capability, el.checked); },
  saveUserCustomers: function(el) { saveUserCustomers(el.dataset.userId); },
  clearUserCustomers: function(el) { clearUserCustomers(el.dataset.userId); },
});

// ── Webhook test ────────────────────────────────────────────────────────────────
export async function testWebhook() {
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
export async function testEmail() {
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

// The visible "Velg fil" opens the hidden input; the chosen name shows beside it.
function chooseLogoFile() {
  var input = document.getElementById('input-logo-file');
  if (input) input.click();
}
function logoFileChosen() {
  var input = document.getElementById('input-logo-file');
  var name = document.getElementById('logo-file-name');
  if (!name) return;
  var f = input && input.files && input.files[0];
  name.removeAttribute('data-i18n');
  name.textContent = f ? f.name : t('msg_no_file_chosen', 'Ingen fil valgt');
}

export async function uploadLogo() {
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
      logoFileChosen();
    } else {
      msg.textContent = d.error || t('status_error'); msg.style.color = 'var(--red)';
    }
  } catch(e) { msg.textContent = t('status_error') + ': ' + e.message; msg.style.color = 'var(--red)'; }
}

// ── Administrasjon ─────────────────────────────────────────────────────────────
// One page with a left rail where the settings modal used to be. The rail
// names the panes and the address carries the one on screen (#/admin/<pane>),
// so every way in (the avatar menu, Ctrl+,, the palette, a signpost elsewhere)
// lands on the pane it meant, named by id rather than by position.
var ADMIN_PANES = ['integrations', 'alerts', 'users', 'modules', 'branding', 'storage', 'system'];
export var _adminPane = 'integrations';

function _adminPaneOrDefault(pane) {
  return ADMIN_PANES.indexOf(pane) !== -1 ? pane : 'integrations';
}

// Opens Administrasjon on a pane. Only an administrator reaches the page; for
// anyone else the settings that are theirs are the account's, so Ctrl+, opens
// those instead of a page that would refuse them.
export function openAdmin(pane) {
  if (!canOpenView('admin')) { openAccountModal(); return; }
  _adminPane = _adminPaneOrDefault(pane || _adminPane);
  if (currentView === 'admin') { adminShowPane(_adminPane); return; }
  showView('admin');
}

onViewShown('admin', function() {
  _loadAdminSettings();
  adminShowPane(_adminPane);
});

// Shows one pane and loads what it lists. The form fields of every pane are
// filled once per visit by _loadAdminSettings, so moving between panes keeps
// what was typed.
export function adminShowPane(pane) {
  _adminPane = _adminPaneOrDefault(pane);
  document.querySelectorAll('#admin-rail .admin-rail-item').forEach(function(b) {
    var on = b.dataset.pane === _adminPane;
    b.classList.toggle('active', on);
    if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  });
  document.querySelectorAll('#view-admin .admin-pane').forEach(function(p) {
    p.hidden = p.id !== 'admin-pane-' + _adminPane;
  });
  if (_adminPane === 'integrations') {
    loadIntegrationStatus();
    unifiSmLoadSaved();
    claudeLoadSaved();
  } else if (_adminPane === 'alerts') {
    alertLoadConfig();
    taskSchedRefresh();
  } else if (_adminPane === 'users') {
    loadUsers();
  } else if (_adminPane === 'modules') {
    loadModuleSettings();
  } else if (_adminPane === 'storage') {
    loadBackupInfo();
    dashLoadArchive();
  }
  syncRoute('admin');
}

async function _loadAdminSettings() {
  try {
    const d = await apiFetch('/api/settings');
    // The storage paths are an administrator's: the server leaves them out
    // for anyone else, and a form filled from nothing must not post nothing
    // back over them (an empty path resets it to the default).
    _storagePathsLoaded = d.audit_dir !== undefined;
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
      d.audit_dir ? t('lbl_active_dir') + ': ' + d.audit_dir : '';
    document.querySelectorAll('#view-admin [data-settings-msg]').forEach(function(m) { m.textContent = ''; });

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
      const custList = await apiFetch('/api/customers');
      _renderSchedulerCustomers(sched, (custList && custList.customers) || []);
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

    // Load version info into the System pane
    try {
      const vr = await apiFetch('/api/version');
      const vi = document.getElementById('settings-version-info');
      if (vi) {
        // Line breaks come from CSS (white-space: pre-line), so the values
        // can go in as text rather than as markup.
        // The version a person can quote in a support case. Commit, branch
        // and the host's Python, platform and PID are for whoever runs the
        // server, who has them where the server runs.
        vi.textContent = t('settings_version_info').replace('{version}', vr.version || vr.describe);
        // There is no in-app updater, so an
        // "Oppdater nå" button could only ever fail. Say where updates come
        // from instead.
        var note = document.getElementById('settings-update-note');
        if (!note) {
          note = document.createElement('div');
          note.id = 'settings-update-note';
          note.className = 'field-hint';
          note.setAttribute('data-admin-only', '');
          vi.insertAdjacentElement('afterend', note);
        }
        note.textContent = t('settings_updates_runbook');
      }
    } catch (e) { /* ignore */ }
  } catch (e) {
    document.getElementById('settings-current-dir').textContent = t('msg_loading_settings_failed');
  }
  // Snapshot form values for dirty-flag detection
  _snapshotSettingsForm();
  _initSettingsDirtyTracking();
}

// ── Automatisk audit: which customers ─────────────────────────────────────────
// Every customer set up for auditing (value ""), or one customer by id. The
// one-customer mode used to audit the setup staging slot, whoever was set up
// last; it names its customer now. Settings saved before that say "one
// customer" without saying which, and a customer can be deleted after it was
// chosen: either way the audit does not run, the list shows a placeholder
// ("?", which no customer id can be) and the line under it says why. Saving
// with the placeholder still chosen leaves the stored choice alone.
var SCHED_UNSET = '?';
var _schedCustomers = [];

function _renderSchedulerCustomers(sched, customers) {
  _schedCustomers = customers;
  var sel = document.getElementById('input-scheduler-customer');
  var warn = document.getElementById('scheduler-customer-warning');
  var one = sched.audit_all_customers === false;
  var known = customers.some(function(c) { return c._id === sched.customer_id; });
  var problem = !one ? '' : (!sched.customer_id ? 'msg_scheduler_customer_unset' : (known ? '' : 'msg_scheduler_customer_gone'));
  var html = '<option value="">' + esc(t('opt_scheduler_all_customers')) + '</option>';
  if (problem) html += '<option value="' + SCHED_UNSET + '" disabled>' + esc(t('opt_scheduler_customer_unset')) + '</option>';
  customers.slice().sort(function(a, b) {
    return String(a.CustomerName || a._id).localeCompare(String(b.CustomerName || b._id), _lang);
  }).forEach(function(c) {
    html += '<option value="' + esc(c._id) + '">' + esc(c.CustomerName || c._id) + '</option>';
  });
  sel.innerHTML = html;
  sel.value = problem ? SCHED_UNSET : (one ? sched.customer_id : '');
  warn.textContent = problem ? t(problem) : '';
  warn.hidden = !problem;
}

// The scope fields of the scheduler block, or nothing while the placeholder
// is still chosen.
function _schedulerScope() {
  var value = document.getElementById('input-scheduler-customer').value;
  if (value === SCHED_UNSET) return {};
  return value ? {audit_all_customers: false, customer_id: value} : {audit_all_customers: true, customer_id: null};
}

// ── Settings dirty-flag detection ─────────────────────────────────────────────
var _storagePathsLoaded = false;
var _settingsSnapshot = null;
var _settingsDirty = false;

// The fields the Lagre on Branding, Lagring and Automatisk audit sends. The
// integration cards and the alert rules save themselves, so they are no part
// of "unsaved changes".
function _settingsFormFields() {
  return document.querySelectorAll('#view-admin [data-settings-form] input, #view-admin [data-settings-form] select, #view-admin [data-settings-form] textarea');
}

function _snapshotSettingsForm() {
  var data = {};
  _settingsFormFields().forEach(function(el) {
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
  if (!_settingsSnapshot || !_settingsDirty) return false;
  var dirty = false;
  _settingsFormFields().forEach(function(el) {
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
  var page = document.getElementById('view-admin');
  page.addEventListener('input', function(e) { if (e.target.closest('[data-settings-form]')) _settingsDirty = true; });
  page.addEventListener('change', function(e) { if (e.target.closest('[data-settings-form]')) _settingsDirty = true; });
}

// Leaving Administrasjon with unsaved edits asks first. True when it is fine
// to go: nothing unsaved, or the person said to discard it.
export function adminMayLeave() {
  if (!_isSettingsDirty()) return true;
  if (!confirm(t('du_har_ulagrede_endringer_vil'))) return false;
  _settingsSnapshot = null;
  _settingsDirty = false;
  return true;
}

// ── Konto ──────────────────────────────────────────────────────────────────────
// What belongs to the person rather than the installation: language, sign-in
// confirmation and password.
export function openAccountModal() {
  var name = document.getElementById('account-name');
  var email = document.getElementById('account-email');
  if (_currentUser) {
    if (name) name.textContent = _currentUser.display_name || _currentUser.username || '';
    if (email) email.textContent = _currentUser.email || _currentUser.username || '';
  }
  var lang = document.getElementById('input-language');
  if (lang) lang.value = _lang;
  document.getElementById('account-modal').classList.add('open');
}

export function closeAccountModal() {
  document.getElementById('account-modal').classList.remove('open');
}

// ── Permission validation ──────────────────────────────────────────────────────

export function closePermissionsModal() {
  document.getElementById('permissions-modal').classList.remove('open');
}

// One customer's app permissions: the customer whose page the button is on.
export async function checkPermissions(customerId) {
  if (!customerId) return;
  const modal = document.getElementById('permissions-modal');
  const title = document.getElementById('perm-modal-title');
  const desc  = document.getElementById('perm-modal-desc');
  const body  = document.getElementById('perm-modal-body');

  title.textContent = t('hdr_permissions_check');
  desc.textContent = t('permissions_checking_desc');
  body.innerHTML = '<div class="flex items-center gap-2 py-6 px-0 justify-center"><div class="loader"></div><span class="text-muted">' + t('msg_checking_permissions') + '</span></div>';
  modal.classList.add('open');

  try {
    const d = await apiFetch('/api/audit/validate-permissions?customer_id=' + encodeURIComponent(customerId), { method: 'POST' });
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
    desc.innerHTML = '<span class="text-success fw-semibold">' + t('msg_all_permissions_ok') + '</span>' +
      (connectivity ? ' · ' + t('msg_connection_verified') : '');
  } else if (d.ok) {
    desc.innerHTML = '<span class="text-warning fw-semibold">' + t('msg_non_critical_missing').replace('{count}', missing.length) + '</span>';
  } else {
    const critMissing = missing.filter(p => !warnings.some(w => w.startsWith(p)));
    desc.innerHTML = '<span class="text-danger fw-semibold">' + t('msg_permissions_missing').replace('{count}', missing.length) + '</span>' +
      (critMissing.length ? ' ' + t('msg_critical_count').replace('{count}', critMissing.length) : '');
  }

  let html = '';

  // Connectivity badge
  html += `<div class="status-box ${connectivity ? 'is-ok' : 'is-bad'} mb-3">` +
    `${connectivity ? '<span class="text-success">&#10003;</span> ' + t('msg_graph_connection_ok') : '<span class="text-danger">&#10007;</span> ' + t('msg_graph_connection_failed')}` +
    '</div>';

  // Warnings
  if (warnings.length > 0) {
    html += '<div class="mb-3">';
    for (const w of warnings) {
      html += `<div class="text-sm text-warning py-1 px-0">${esc(w)}</div>`;
    }
    html += '</div>';
  }

  // Permission list table
  const allPerms = [...granted.map(p => ({name: p, ok: true})), ...missing.map(p => ({name: p, ok: false}))];
  allPerms.sort((a, b) => a.name.localeCompare(b.name));

  html += '<div class="border rounded overflow-hidden">';
  html += '<table class="data-table">';
  html += '<thead><tr class="bg-base"><th>' + t('lbl_permission') + '</th><th class="col-status-sm text-center">' + t('lbl_status') + '</th></tr></thead><tbody>';

  for (const p of allPerms) {
    const isWarnOnly = warnings.some(w => w.startsWith(p.name));
    let icon, tone;
    if (p.ok) {
      icon = '&#10003;'; tone = 'text-success';
    } else if (isWarnOnly) {
      icon = ''; tone = 'text-warning';
    } else {
      icon = '&#10007;'; tone = 'text-danger';
    }
    html += `<tr>`;
    html += `<td class="font-mono text-xs">${esc(p.name)}</td>`;
    html += `<td class="text-center fw-bold ${tone}">${icon}</td>`;
    html += '</tr>';
  }
  html += '</tbody></table></div>';

  html += '<div class="mt-3 text-sm text-muted">' + t('msg_permissions_granted').replace('{granted}', granted.length).replace('{total}', granted.length + missing.length) + '</div>';

  body.innerHTML = html;
}

// ── Encryption key backup/restore ──────────────────────────────────────────────
export async function backupEncryptionKey() {
  if (!await showConfirm(t('dlg_confirm_show_key'))) return;
  try {
    const d = await apiFetch('/api/encryption/key-backup');
    if (!d.ok) { showToast(t('status_error') + ': ' + (d.error || t('err_unknown')), 'error'); return; }
    document.getElementById('encryption-key-value').textContent = d.key;
    document.getElementById('encryption-key-display').style.display = 'block';
    document.getElementById('encryption-copy-msg').textContent = '';
  } catch (e) { showToast(t('err_could_not_fetch_key', 'Kunne ikke hente nøkkel') + ': ' + e.message, 'error'); }
}

export function copyEncryptionKey() {
  const key = document.getElementById('encryption-key-value').textContent;
  navigator.clipboard.writeText(key).then(() => {
    document.getElementById('encryption-copy-msg').textContent = t('btn_copied');
    setTimeout(() => { document.getElementById('encryption-copy-msg').textContent = ''; }, 3000);
  });
}

export function showRestoreKeyInput() {
  document.getElementById('encryption-restore-input').style.display = 'block';
  document.getElementById('encryption-restore-msg').textContent = '';
}

export async function restoreEncryptionKey() {
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
export async function showMfaSettings() {
  var status = await apiFetch('/api/auth/mfa');
  if (!status) return;
  var modal = document.getElementById('confirm-modal');
  document.getElementById('confirm-modal-title').textContent = t('lbl_mfa_settings','MFA / verify login');
  var body = document.getElementById('confirm-modal-body');
  body.style.display = 'block';
  body.replaceChildren();
  var notice = document.createElement('p');
  notice.textContent = status.enabled ? t('msg_mfa_enabled','MFA is enabled. Verification is valid for five minutes.') : t('msg_mfa_setup','Add the secret to an authenticator app, then confirm with its code.');
  body.appendChild(notice);
  function field(type, label, autocomplete) {
    var wrapper = document.createElement('label');
    wrapper.textContent = label;
    var input = document.createElement('input');
    input.type = type; input.className = 'field-input'; input.autocomplete = autocomplete;
    wrapper.appendChild(input); body.appendChild(wrapper); return input;
  }
  var password = field('password', t('lbl_password','Password'), 'current-password');
  var code = field('text', t('lbl_otp','One-time code'), 'one-time-code');
  var output = document.createElement('pre'); output.style.whiteSpace = 'pre-wrap';
  body.appendChild(output);
  var enrolling = false;
  var enrollmentComplete = false;
  async function submit(path) {
    var response = await apiFetch('/api/auth/' + path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password:password.value,otp:code.value.trim()})});
    if (!response) return;
    if (response.secret) {
      output.textContent = response.secret;
      enrolling = true;
      primary.textContent = t('btn_confirm','Confirm');
    } else if (response.recovery_codes) {
      enrollmentComplete = true;
      output.textContent = t('msg_mfa_recovery','Store these single-use recovery codes offline. They are shown only once.') + '\n' + response.recovery_codes.join('\n');
      password.value = ''; code.value = ''; primary.disabled = true;
    } else {
      output.textContent = t('msg_saved','Saved'); password.value = ''; code.value = '';
      if (path === 'mfa/disable') window.location.reload();
    }
  }
  var primary = document.createElement('button'); primary.className = 'btn btn-primary';
  primary.textContent = status.enabled ? t('btn_verify_login','Verify login') : t('btn_enable_mfa','Enable MFA');
  primary.addEventListener('click', async function() {
    primary.disabled = true;
    try { await submit(status.enabled ? 'step-up' : enrolling ? 'mfa/confirm' : 'mfa/enroll'); }
    finally { if (!output.textContent.includes('\n')) primary.disabled = false; }
  });
  body.appendChild(primary);
  if (status.enabled) {
    var disable = document.createElement('button'); disable.className = 'btn btn-ghost';
    disable.textContent = t('btn_disable_mfa','Disable MFA');
    disable.addEventListener('click', function() { submit('mfa/disable'); }); body.appendChild(disable);
  }
  var close = document.createElement('button'); close.className = 'btn btn-ghost'; close.textContent = t('btn_close','Close');
  close.addEventListener('click', function() { body.replaceChildren(); modal.style.display='none'; document.querySelector('#confirm-modal .modal-actions').style.display=''; if (enrollmentComplete) checkAuth(); }); body.appendChild(close);
  document.querySelector('#confirm-modal .modal-actions').style.display = 'none'; modal.style.display = 'flex'; password.focus();
}

export async function showChangePasswordModal() {
  var html = '<div class="text-sm fw-semibold mb-4">' + t('btn_change_password','Change password') + '</div>'
    + '<input id="pw-current" type="password" class="field-input mb-3" placeholder="' + t('placeholder_current_password','Current password') + '">'
    + '<input id="pw-new" type="password" class="field-input mb-3" placeholder="' + t('placeholder_new_password','New password (min 8)') + '">'
    + '<input id="pw-confirm" type="password" class="field-input mb-3" placeholder="' + t('placeholder_confirm_password','Confirm new password') + '">'
    + '<div id="pw-change-msg" class="text-xs mb-3"></div>'
    + '<div class="flex gap-2 justify-end">'
    + '<button class="btn btn-ghost" data-click-handler="hideElement" data-target="confirm-modal">' + t('btn_cancel') + '</button>'
    + '<button class="btn btn-primary" data-click-handler="doChangePassword">' + t('btn_save') + '</button>'
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
  if (!passwordMeetsRule(nw)) { msg.innerHTML = '<span class="text-danger">' + esc(t('err_password_rule')) + '</span>'; return; }
  if (nw !== cf) { msg.innerHTML = '<span class="text-danger">' + t('err_passwords_mismatch','Passwords do not match') + '</span>'; return; }
  var d = await apiFetch('/api/auth/change-password', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({current_password:cur, new_password:nw})});
  if (d && d.ok) {
    document.getElementById('confirm-modal').style.display = 'none';
    document.querySelector('#confirm-modal .modal-actions').style.display = '';
    showToast(t('msg_password_changed','Password changed'), 'success', 3000);
  } else {
    msg.innerHTML = '<span class="text-danger">' + (d && d.error ? esc(d.error) : t('status_error')) + '</span>';
  }
}

// ── User Management ──────────────────────────────────────────────────────────
export function showAddUserForm() { document.getElementById('add-user-form').style.display = 'block'; }

async function loadUsers() {
  var el = document.getElementById('users-list');
  if (!el) return;
  try {
    var d = await apiFetch('/api/auth/users');
    if (!d || !d.users) { el.innerHTML = '<div class="text-muted text-sm">' + t('status_error') + '</div>'; return; }
    el.innerHTML = d.users.map(function(u) {
      var lastLogin = u.last_login ? timeAgo(u.last_login) : t('msg_never','never');
      return '<div data-user-id="'+esc(u.id)+'" class="flex items-center gap-3 p-3 border-b">'
        + '<div class="flex-1">'
        + '<div class="fw-semibold">' + esc(u.display_name) + ' <span class="text-xs text-dim font-mono">@' + esc(u.username) + '</span></div>'
        + '<div class="text-xs text-dim">' + t('lbl_last_prefix','Last:') + ' ' + esc(lastLogin) + '</div>'
        + '</div>'
        + '<select class="py-0-5 px-2 text-xs border rounded-sm bg-base text-default" data-change-handler="changeUserRole" data-user-id="' + esc(u.id) + '">'
        + '<option value="viewer"' + (u.role==='viewer'?' selected':'') + '>' + t('viewer_2') + '</option>'
        + '<option value="technician"' + (u.role==='technician'?' selected':'') + '>' + t('technician_2') + '</option>'
        + '<option value="admin"' + (u.role==='admin'?' selected':'') + '>' + t('admin_2') + '</option>'
        + '</select>'
        + _capabilityToggles(u)
        + '<button class="btn btn-ghost btn-sm" data-click-handler="editUserCustomers" data-user-id="' + esc(u.id) + '" data-display-name="' + esc(u.display_name) + '" title="' + esc(t('tip_customer_access','Customer access')) + '" aria-label="' + esc(t('tip_customer_access','Customer access')) + '">' + icon('users', 14) + '</button>'
        // No delete for yourself, and none for the system account: the server
        // refuses both, so the button would only earn an error.
        + (u.is_system
          ? '<span class="user-system-badge" title="' + esc(t('tip_system_account', 'Sybr HUB bruker kontoen til planlagte jobber og tunneler. Den kan ikke logge inn eller slettes.')) + '">' + esc(t('lbl_system_account', 'Systemkonto')) + '</span>'
          : (u.username !== (_currentUser && _currentUser.username) ? '<button class="btn btn-ghost btn-sm text-danger" data-click-handler="deleteUser" data-user-id="' + esc(u.id) + '" data-username="' + esc(u.username) + '">' + t('btn_delete') + '</button>' : ''))
        + '</div>';
    }).join('');
  } catch(e) { el.innerHTML = ''; }
}

export async function createUser() {
  var u = document.getElementById('new-user-username').value.trim();
  var n = document.getElementById('new-user-displayname').value.trim();
  var p = document.getElementById('new-user-password').value;
  var r = document.getElementById('new-user-role').value;
  var msg = document.getElementById('add-user-msg');
  if (!u || !passwordMeetsRule(p)) { msg.innerHTML = '<span class="text-danger">' + esc(t(u ? 'err_password_rule' : 'err_fill_all_fields')) + '</span>'; return; }
  var d = await apiFetch('/api/auth/users', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username:u, display_name:n||u, password:p, role:r})});
  if (d && d.ok) {
    document.getElementById('add-user-form').style.display = 'none';
    document.getElementById('new-user-username').value = '';
    document.getElementById('new-user-displayname').value = '';
    document.getElementById('new-user-password').value = '';
    loadUsers();
    showToast(t('msg_user_created','User created'), 'success', 2000);
  } else {
    msg.innerHTML = '<span class="text-danger">' + (d && d.error ? esc(d.error) : t('status_error')) + '</span>';
  }
}

// Two capabilities, shown as what they are: grants, not part of the role.
// tenant_write is disabled until write is on, mirroring the server — it stands
// on can_write, and an account that may not save a note here has no business
// changing configuration in a customer's tenant.
function _capabilityToggles(u) {
  var write = !!u.can_write, tenant = !!u.tenant_write;
  return '<label class="flex items-center gap-1 text-xs text-muted cursor-pointer nowrap" title="' + t('tip_cap_write','May change anything in Sybr HUB. Off by default for every account.') + '">'
    + '<input type="checkbox"' + (write ? ' checked' : '') + ' data-change-handler="setUserCapability" data-user-id="' + esc(u.id) + '" data-capability="can_write"> ' + t('lbl_cap_write','Write')
    + '</label>'
    + '<label class="flex items-center gap-1 text-xs nowrap ' + (write ? 'text-muted cursor-pointer' : 'text-dim cursor-not-allowed') + '" title="' + t('tip_cap_tenant','May write into a customer Microsoft tenant. Requires Write.') + '">'
    + '<input type="checkbox"' + (tenant ? ' checked' : '') + (write ? '' : ' disabled') + ' data-change-handler="setUserCapability" data-user-id="' + esc(u.id) + '" data-capability="tenant_write"> ' + t('lbl_cap_tenant','Tenant')
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

  var d = await apiFetch('/api/auth/users/' + encodeURIComponent(userId), {
    method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (d && d.ok) {
    showToast(enabled ? t('msg_capability_granted','Access granted') : t('msg_capability_revoked','Access revoked'), 'success', 2000);
  }
  loadUsers();
}

async function changeUserRole(userId, newRole) {
  await apiFetch('/api/auth/users/' + encodeURIComponent(userId), {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({role:newRole})});
  showToast(t('msg_role_updated','Role updated'), 'success', 2000);
}

async function deleteUser(userId, username) {
  if (!await showTypedConfirm(
    username,
    t('dlg_confirm_delete_user','Delete user "{name}"?').replace('{name}', username),
    t('dlg_destructive_user_delete', 'Brukeren vil miste all tilgang umiddelbart. Aktive sesjoner avsluttes.')
  )) return;
  await apiFetch('/api/auth/users/' + encodeURIComponent(userId), {method:'DELETE'});
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
  p.innerHTML = '<div class="loader mx-auto my-2"></div>';
  targetRow.after(p);

  // Load customers and current access
  var customers = await apiFetch('/api/customers');
  var access = await apiFetch('/api/auth/users/' + encodeURIComponent(userId) + '/customers');
  if (!customers || !customers.customers) return;

  var accessSet = {};
  (access && access.customer_ids || []).forEach(function(id) { accessSet[id] = true; });
  var hasAny = Object.keys(accessSet).length > 0;

  var html = '<div class="subhead">Kundetilgang for ' + esc(displayName) + '</div>';
  html += '<div class="mb-2 text-xs text-muted">' + (access && access.is_admin ? t('rbac_admin_access') : (hasAny ? Object.keys(accessSet).length + ' ' + t('rbac_customers_selected','kunder valgt') : t('rbac_no_customers'))) + '</div>';
  html += '<label class="block mb-2">' + t('rbac_access_mode')
    + ' <select class="rbac-mode"><option value="scoped"' + (access && access.access_mode === 'all' ? '' : ' selected') + '>' + t('rbac_scoped') + '</option>'
    + '<option value="all"' + (access && access.access_mode === 'all' ? ' selected' : '') + '>' + t('rbac_all_customers') + '</option></select></label>';
  html += '<div class="max-h-sm overflow-y-auto border rounded p-1">';
  customers.customers.forEach(function(c) {
    var cid = c._id || '';
    var checked = accessSet[cid] ? ' checked' : '';
    html += '<label class="flex items-center gap-2 py-1 px-2 text-xs cursor-pointer"><input type="checkbox" class="rbac-cb" data-cid="'+esc(cid)+'"'+checked+'> '+esc(c.CustomerName||cid)+'</label>';
  });
  html += '</div>';
  html += '<div class="flex gap-2 mt-2">';
  html += '<button class="btn btn-primary btn-sm" data-click-handler="saveUserCustomers" data-user-id="' + esc(userId) + '">' + t('lagre_2') + '</button>';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="removeElement" data-target="rbac-panel-' + esc(userId) + '">' + t('avbryt') + '</button>';
  html += '<button class="btn btn-ghost btn-sm ml-auto text-dim" data-click-handler="clearUserCustomers" data-user-id="' + esc(userId) + '">' + t('rbac_remove_access') + '</button>';
  html += '</div>';
  p.innerHTML = html;
  var mode = p.querySelector('.rbac-mode');
  function updateAccessMode() { p.querySelectorAll('.rbac-cb').forEach(function(cb) { cb.disabled = mode.value === 'all'; }); }
  mode.addEventListener('change', updateAccessMode);
  updateAccessMode();
}

async function saveUserCustomers(userId) {
  var panel = document.getElementById('rbac-panel-' + userId);
  if (!panel) return;
  var ids = [];
  var mode = panel.querySelector('.rbac-mode').value;
  if (mode === 'scoped') panel.querySelectorAll('.rbac-cb:checked').forEach(function(cb) { ids.push(cb.dataset.cid); });
  var saved = await apiFetch('/api/auth/users/' + encodeURIComponent(userId) + '/customers', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({access_mode:mode, customer_ids:ids})});
  if (!saved || !saved.ok) return;
  panel.remove();
  showToast(mode === 'all' ? t('rbac_all_customers') : (ids.length ? ids.length + ' ' + t('rbac_customers_assigned') : t('rbac_no_customers')), 'success', 2000);
}

async function clearUserCustomers(userId) {
  var saved = await apiFetch('/api/auth/users/' + encodeURIComponent(userId) + '/customers', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({access_mode:'scoped', customer_ids:[]})});
  if (!saved || !saved.ok) return;
  var panel = document.getElementById('rbac-panel-' + userId);
  if (panel) panel.remove();
  showToast(t('rbac_no_customers'), 'success', 2000);
}

// ── Modules ───────────────────────────────────────────────────────────────────
// One switch per optional module. A change reloads the page: navigation,
// views and routes all depend on it, and a reload is the one way to be sure
// nothing still shows a part that was just switched off.
async function loadModuleSettings() {
  var list = document.getElementById('modules-list');
  if (!list) return;
  var d = await apiFetch('/api/settings/modules');
  if (!d) return;
  list.innerHTML = (d.modules || []).map(function(m) {
    return '<label class="module-row">'
      + '<input type="checkbox" class="module-toggle" data-module-key="' + esc(m.key) + '"' + (m.enabled ? ' checked' : '') + '>'
      + '<span class="module-text"><span class="module-name">' + esc(t('module_' + m.key, m.key)) + '</span>'
      + '<span class="module-desc">' + esc(t('module_' + m.key + '_desc', '')) + '</span></span>'
      + '</label>';
  }).join('');
  if (!list._wired) {
    list.addEventListener('change', async function(e) {
      var box = e.target.closest('.module-toggle');
      if (!box) return;
      var body = {};
      body[box.dataset.moduleKey] = box.checked;
      box.disabled = true;
      var r = await apiFetch('/api/settings/modules', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      if (!r || !r.ok) { box.checked = !box.checked; box.disabled = false; return; }
      showToast(t('msg_modules_saved', 'Lagret. Siden lastes inn på nytt.'), 'success');
      setTimeout(function() { location.reload(); }, 600);
    });
    list._wired = true;
  }
}

// ── Branding / White-label ────────────────────────────────────────────────────
export async function applyBranding() {
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
      if (titleEl) titleEl.textContent = b.company_name + ' · Sybr HUB';
    }
  } catch(e) { /* branding is non-critical */ }
}
export function resetBrandColor() {
  document.getElementById('input-brand-color').value = '#4d9fb5';
  document.getElementById('input-brand-color-hex').value = '#4d9fb5';
}

// The status line beside the Lagre on the pane on screen.
function _settingsMsgEl() {
  return document.querySelector('#admin-pane-' + _adminPane + ' [data-settings-msg]')
    || document.querySelector('#view-admin [data-settings-msg]');
}

export async function saveSettings() {
  const dir = document.getElementById('input-audit-dir').value.trim();
  const msg = _settingsMsgEl();
  msg.style.color = '';
  msg.textContent = t('btn_saving');
  try {
    var body = {
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
    };
    // The server keeps a field that was not sent; only paths it showed us go back.
    if (_storagePathsLoaded) {
      body.audit_dir = dir;
      body.cert_dir = document.getElementById('input-cert-dir').value.trim();
    }
    const d = await apiFetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!d) {
      // apiFetch has said why.
      msg.textContent = '';
      return;
    } else if (d.error) {
      msg.style.color = 'var(--red)';
      msg.textContent = '✗ ' + d.error;
    } else {
      msg.style.color = 'var(--green)';
      msg.textContent = d.audit_dir ? t('msg_saved_active_dir').replace('{dir}', d.audit_dir) : t('msg_saved', 'Lagret');
      if (d.audit_dir) document.getElementById('settings-current-dir').textContent = t('lbl_active_dir') + ': ' + d.audit_dir;
      applyBranding(); // Re-apply brand colors immediately
      // Clear dirty flag and re-snapshot after successful save
      _snapshotSettingsForm();
    }

    // Save scheduler separately
    const schedData = {
      enabled: document.getElementById('input-scheduler-enabled').checked,
      ..._schedulerScope(),
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
    const schedSaved = await apiFetch('/api/scheduler', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(schedData)
    });
    // A refused block (apiFetch has said why) is not saved, whatever the
    // line above says about the rest of the form.
    if (!schedSaved) msg.textContent = '';
    else {
      const sched = await apiFetch('/api/scheduler');
      if (sched) { _renderSchedulerCustomers(sched, _schedCustomers); _snapshotSettingsForm(); }
    }
  } catch (e) {
    msg.style.color = 'var(--red)';
    msg.textContent = '✗ ' + t('err_network_error').replace('{msg}', e.message);
  }
}

export async function resetAuditDir() {
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

export async function createBackup() {
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

export async function restoreBackup() {
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
