// ═══════════════════════════════════════════════════════════════════
// SETTINGS — webhooks, branding, version, users & backup
// ═══════════════════════════════════════════════════════════════════

// Handlers for the user list, the password dialog and the customer-access
// panel (see registerUiHandlers in app.js).
registerUiHandlers({
  doChangePassword: function() { doChangePassword(); },
  changeUserRole: function(el) { changeUserRole(el.dataset.userId, el.value); },
  editUserCustomers: function(el) { editUserCustomers(el.dataset.userId, el.dataset.displayName); },
  deleteUser: function(el) { deleteUser(el.dataset.userId, el.dataset.username); },
  setUserCapability: function(el) { setUserCapability(el.dataset.userId, el.dataset.capability, el.checked); },
  saveUserCustomers: function(el) { saveUserCustomers(el.dataset.userId); },
  clearUserCustomers: function(el) { clearUserCustomers(el.dataset.userId); },
});

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

    // Backup is an administrator's tab; the routes refuse anyone else.
    if (_currentUser && _currentUser.role === 'admin') loadBackupInfo();

    // Load version info into settings modal
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
  document.getElementById('settings-modal').classList.add('open');
  // Snapshot form values for dirty-flag detection
  _snapshotSettingsForm();
  _initSettingsDirtyTracking();
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
      (connectivity ? ' · ' + t('msg_connection_verified') : '');
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
async function showMfaSettings() {
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

async function showChangePasswordModal() {
  var html = '<div style="font-size:var(--font-sm);font-weight:600;margin-bottom:var(--space-4);">' + t('btn_change_password','Change password') + '</div>'
    + '<input id="pw-current" type="password" class="field-input" placeholder="' + t('placeholder_current_password','Current password') + '" style="margin-bottom:var(--space-3);">'
    + '<input id="pw-new" type="password" class="field-input" placeholder="' + t('placeholder_new_password','New password (min 8)') + '" style="margin-bottom:var(--space-3);">'
    + '<input id="pw-confirm" type="password" class="field-input" placeholder="' + t('placeholder_confirm_password','Confirm new password') + '" style="margin-bottom:var(--space-3);">'
    + '<div id="pw-change-msg" style="font-size:var(--font-xs);margin-bottom:var(--space-3);"></div>'
    + '<div style="display:flex;gap:var(--space-2);justify-content:flex-end;">'
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
  if (!passwordMeetsRule(nw)) { msg.innerHTML = '<span style="color:var(--red);">' + esc(t('err_password_rule')) + '</span>'; return; }
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
    el.innerHTML = d.users.map(function(u) {
      var lastLogin = u.last_login ? timeAgo(u.last_login) : t('msg_never','never');
      return '<div data-user-id="'+esc(u.id)+'" style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-3);border-bottom:1px solid var(--border);">'
        + '<div style="flex:1;">'
        + '<div style="font-weight:600;">' + esc(u.display_name) + ' <span style="font-size:var(--font-xs);color:var(--text-dim);font-family:var(--mono);">@' + esc(u.username) + '</span></div>'
        + '<div style="font-size:var(--font-xs);color:var(--text-dim);">' + t('lbl_last_prefix','Last:') + ' ' + esc(lastLogin) + '</div>'
        + '</div>'
        + '<select style="padding:2px 6px;font-size:var(--font-xs);border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg);color:var(--text);" data-change-handler="changeUserRole" data-user-id="' + esc(u.id) + '">'
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
          : (u.username !== (_currentUser && _currentUser.username) ? '<button class="btn btn-ghost btn-sm" style="color:var(--red);" data-click-handler="deleteUser" data-user-id="' + esc(u.id) + '" data-username="' + esc(u.username) + '">' + t('btn_delete') + '</button>' : ''))
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
  if (!u || !passwordMeetsRule(p)) { msg.innerHTML = '<span style="color:var(--red);">' + esc(t(u ? 'err_password_rule' : 'err_fill_all_fields')) + '</span>'; return; }
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
    + '<input type="checkbox"' + (write ? ' checked' : '') + ' data-change-handler="setUserCapability" data-user-id="' + esc(u.id) + '" data-capability="can_write"> ' + t('lbl_cap_write','Write')
    + '</label>'
    + '<label style="display:flex;align-items:center;gap:4px;font-size:var(--font-xs);color:' + (write ? 'var(--text-muted)' : 'var(--text-dim)') + ';cursor:' + (write ? 'pointer' : 'not-allowed') + ';white-space:nowrap;" title="' + t('tip_cap_tenant','May write into a customer Microsoft tenant. Requires Write.') + '">'
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
  p.innerHTML = '<div class="loader" style="width:16px;height:16px;margin:8px auto;"></div>';
  targetRow.after(p);

  // Load customers and current access
  var customers = await apiFetch('/api/customers');
  var access = await apiFetch('/api/auth/users/' + encodeURIComponent(userId) + '/customers');
  if (!customers || !customers.customers) return;

  var accessSet = {};
  (access && access.customer_ids || []).forEach(function(id) { accessSet[id] = true; });
  var hasAny = Object.keys(accessSet).length > 0;

  var html = '<div style="font-size:12px;font-weight:600;margin-bottom:8px;">Kundetilgang for ' + esc(displayName) + '</div>';
  html += '<div style="margin-bottom:8px;font-size:11px;color:var(--text-muted);">' + (access && access.is_admin ? t('rbac_admin_access') : (hasAny ? Object.keys(accessSet).length + ' ' + t('rbac_customers_selected','kunder valgt') : t('rbac_no_customers'))) + '</div>';
  html += '<label style="display:block;margin-bottom:8px;">' + t('rbac_access_mode')
    + ' <select class="rbac-mode"><option value="scoped"' + (access && access.access_mode === 'all' ? '' : ' selected') + '>' + t('rbac_scoped') + '</option>'
    + '<option value="all"' + (access && access.access_mode === 'all' ? ' selected' : '') + '>' + t('rbac_all_customers') + '</option></select></label>';
  html += '<div style="max-height:200px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;padding:4px;">';
  customers.customers.forEach(function(c) {
    var cid = c._id || '';
    var checked = accessSet[cid] ? ' checked' : '';
    html += '<label style="display:flex;align-items:center;gap:6px;padding:3px 6px;font-size:11px;cursor:pointer;"><input type="checkbox" class="rbac-cb" data-cid="'+esc(cid)+'"'+checked+'> '+esc(c.CustomerName||cid)+'</label>';
  });
  html += '</div>';
  html += '<div style="display:flex;gap:8px;margin-top:8px;">';
  html += '<button class="btn btn-primary btn-sm" data-click-handler="saveUserCustomers" data-user-id="' + esc(userId) + '">' + t('lagre_2') + '</button>';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="removeElement" data-target="rbac-panel-' + esc(userId) + '">' + t('avbryt') + '</button>';
  html += '<button class="btn btn-ghost btn-sm" style="margin-left:auto;font-size:10px;color:var(--text-dim);" data-click-handler="clearUserCustomers" data-user-id="' + esc(userId) + '">' + t('rbac_remove_access') + '</button>';
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
  if (paneId === 'stab-modules') loadModuleSettings();
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
      if (titleEl) titleEl.textContent = b.company_name + ' · Sybr HUB';
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
