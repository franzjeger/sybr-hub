// ═══════════════════════════════════════════════════════════════════
// UI handlers for the markup this file builds. Controls name them in
// data-<event>-handler attributes and carry their arguments in data-*
// attributes; see app-handlers.js.
// ═══════════════════════════════════════════════════════════════════

import {esc} from './app-esc.js';
import {t} from './app-i18n.js';
import {registerUiHandlers} from './app-handlers.js';
import {registerToolCustomer} from './app-hooks.js';
import {_allCustomers, _overviewData, currentCustomerId, setOverviewData} from './app-state.js';
import {_formatBytes, badgeClass, toneClass, toneVar} from './app-format.js';
import {adminSignpostButton, openReportWindow, showConfirm, showToast} from './app-ui.js';
import {apiFetch} from './app-api.js';
import {renderToolCustomerPickers, showView, toolCustomerId} from './app.js';
import {dashLoadAlerts} from './app-dashboard.js';
import {overviewSelectCustomer} from './app-customers.js';
import {_checkVpnHeaderBadge, _syncBottomNav} from './app-chrome.js';

registerUiHandlers({
  // Hosts and SSH
  infraSelectCustomer: function(el) { overviewSelectCustomer(el.dataset.customerId); },
  sshEditHost: function(el) { sshEditHost(el.dataset.id); },
  sshTerminal: function(el) { sshTerminal(el.dataset.id); },
  // The host cards pass the host id as well; the SSH host table does not.
  sshRdp: function(el) {
    if (el.hasAttribute('data-host-id')) sshRdp(el.dataset.hostname, el.dataset.username, el.dataset.hostId);
    else sshRdp(el.dataset.hostname, el.dataset.username);
  },
  openWebUI: function(el) { openWebUI(el.dataset.url); },
  sshDeleteHost: function(el) { sshDeleteHost(el.dataset.id); },
  hostsTypeChanged: function() { hostsTypeChanged(); },
  hostsAuthChanged: function() { hostsAuthChanged(); },
  hostsDoAdd: function() { hostsDoAdd(); },
  sshGenKey: function() { sshGenKey(); },
  sshImportKey: function() { sshImportKey(); },
  sshViewKey: function(el) { sshViewKey(el.dataset.id); },
  sshDeleteKey: function(el) { sshDeleteKey(el.dataset.id); },
  sshDoGenKey: function() { sshDoGenKey(); },
  sshDoImportKey: function() { sshDoImportKey(); },
  sshCopyPublicKey: function(el) {
    navigator.clipboard.writeText(el.dataset.key);
    showToast(t('msg_copied_short', 'Copied!'), 'success', 1500);
  },
  sshAddHost: function() { sshAddHost(); },
  sshHealthAll: function() { sshHealthAll(); },
  sshHostAuthChanged: function() { sshHostAuthChanged(); },
  sshDoAddHost: function() { sshDoAddHost(); },
  sshShowHosts: function() { sshShowHosts(); },
  sshDoEditHost: function(el) { sshDoEditHost(el.dataset.id); },
  sshEditHostCancel: function() {
    if (hostsLoad) hostsLoad();
    else sshShowHosts();
  },
  sshExecRun: function() { sshExecRun(); },
  sshExecRunOnEnter: function(el, event) { if (event.key === 'Enter') sshExecRun(); },
  // VPN
  vpnDisconnect: function(el) { vpnDisconnect(el.dataset.id); },
  vpnForceDisconnect: function() { vpnForceDisconnect(); },
  vpnConnect: function(el) { vpnConnect(el.dataset.id); },
  vpnEditProfile: function(el) { vpnEditProfile(el.dataset.id); },
  vpnDeleteProfile: function(el) { vpnDeleteProfile(el.dataset.id); },
  pkceCopyUrl: function(el) {
    var ta = document.createElement('textarea');
    ta.value = el.dataset.url;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast(t('inf_copied_excl', 'Kopiert!'), 'success', 1500);
  },
  pkceComplete: function(el) { pkceComplete(el.dataset.id); },
  vpnCreateProtocolChanged: function() { vpnCreateProtocolChanged(); },
  vpnDoCreate: function() { vpnDoCreate(); },
  vpnDoEdit: function(el) { vpnDoEdit(el.dataset.id, el.dataset.protocol); },
  // The import drop zone, and the hidden file input a click on it opens.
  vpnOpenFilePicker: function() { document.getElementById('vpn-file-input').click(); },
  vpnDragOver: function(el, event) {
    event.preventDefault();
    el.style.borderColor = 'var(--blue)';
  },
  vpnDragLeave: function(el) { el.style.borderColor = 'var(--border)'; },
  vpnDropFiles: function(el, event) {
    event.preventDefault();
    el.style.borderColor = 'var(--border)';
    vpnHandleFiles(event.dataTransfer.files);
  },
  vpnHandleFiles: function(el) { vpnHandleFiles(el.files); },
  vpnClearFile: function() { vpnClearFile(); },
  vpnDoImport: function() { vpnDoImport(); },
  // Live devices and FortiGate
  liveShowDeviceDetail: function(el) { liveShowDeviceDetail(Number(el.dataset.index)); },
  livePollNow: function() { livePollNow(); },
  fgBackupConfig: function(el) { fgBackupConfig(el.dataset.customerId); },
  fgShowBackups: function(el) { fgShowBackups(el.dataset.customerId); },
  fgComplianceCheck: function(el) { fgComplianceCheck(el.dataset.customerId); },
  fgDownloadBackup: function(el) { fgDownloadBackup(el.dataset.customerId, el.dataset.filename); },
  dashLoadFortiGates: function() { dashLoadFortiGates(); },
  fgBackupAll: function() { fgBackupAll(); },
  dashFgDetail: function(el) { dashFgDetail(el.dataset.customerId); },
  fgBootstrapAutoFill: function(el) { fgBootstrapAutoFill(el.dataset.host, el.dataset.token); },
  fgCopyApiToken: function(el) {
    navigator.clipboard.writeText(el.dataset.token);
    showToast(t('inf_token_copied', 'API-token kopiert'), 'success');
  },
  // Provisioning
  provisionAutoFill: function() { provisionAutoFill(); },
  provisionSuggestSubnets: function() { provisionSuggestSubnets(); },
  provisionAddVlan: function() { provisionAddVlan(); },
  provisionDeploy: function(el) { provisionDeploy(el.dataset.method); },
  // data-ai="1" on "Generate with AI"; the plain button has no data-ai.
  provisionGenerate: function(el) { provisionGenerate(el.dataset.ai === '1'); },
  provisionPrevStep: function(el) { provisionPrevStep(Number(el.dataset.step)); },
  provisionNextStep: function(el) { provisionNextStep(Number(el.dataset.step)); },
  provisionRemoveVlan: function(el) { provisionRemoveVlan(Number(el.dataset.index)); },
  // A <code> holding a generated secret: a click copies its text.
  provisionCopySecret: function(el) {
    navigator.clipboard.writeText(el.textContent);
    showToast(t('inf_copied', 'Kopiert'), 'success', 1500);
  },
  provisionDownloadSummary: function() { provisionDownloadSummary(); },
  provisionCopySummary: function() { provisionCopySummary(); },
  // UniFi, sites and pentest
  dashUnifiDetail: function(el) { dashUnifiDetail(Number(el.dataset.index)); },
  _pentestToggleExplain: function(el) { _pentestToggleExplain(el.dataset.rowId, Number(el.dataset.index)); },
  _pentestReport: function() { _pentestReport(); },
  _pentestSave: function() { _pentestSave(); },
  unifiSmVerify2fa: function() { unifiSmVerify2fa(); },
  showSiteDetail: function(el) { showSiteDetail(Number(el.dataset.index)); },
  showSubSiteDetail: function(el) { showSubSiteDetail(Number(el.dataset.index), Number(el.dataset.subIndex)); },
  dashLoadSites: function() { dashLoadSites(); },
  // Remote browser and RDP
  browserNavigate: function() { browserNavigate(); },
  browserNavigateOnEnter: function(el, event) { if (event.key === 'Enter') browserNavigate(); },
  browserStart: function() { browserStart(); },
  browserStop: function() { browserStop(); },
  // data-target names the element to show fullscreen.
  toggleFullscreen: function(el) { toggleFullscreen(el.dataset.target); },
  rdpStart: function() { rdpStart(); },
  rdpStartOnEnter: function(el, event) { if (event.key === 'Enter') rdpStart(); },
  rdpStop: function() { rdpStop(); },
});

// ═══════════════════════════════════════════════════════════════════
// SHARED: Customer selector helper
// ═══════════════════════════════════════════════════════════════════

var _infraCustomerCache = null;

async function _populateCustomerSelect(selectId, selectedId) {
  var sel = document.getElementById(selectId);
  if (!sel) return;
  if (!_infraCustomerCache) {
    try {
      var ov = _overviewData && _overviewData.customers
        ? _overviewData : await apiFetch('/api/dashboard/overview');
      _infraCustomerCache = (ov && ov.customers) || [];
    } catch(e) { _infraCustomerCache = []; }
  }
  _infraCustomerCache.forEach(function(c) {
    var id = c.customer_id || c._id;
    var opt = document.createElement('option');
    opt.value = id;
    opt.textContent = c.customer_name || id;
    if (selectedId && id === selectedId) opt.selected = true;
    sel.appendChild(opt);
  });
}

function _customerNameById(customerId) {
  if (!customerId) return '';
  if (_infraCustomerCache) {
    var c = _infraCustomerCache.find(function(c){ return (c.customer_id || c._id) === customerId; });
    if (c) return c.customer_name || customerId;
  }
  if (_overviewData && _overviewData.customers) {
    var c2 = _overviewData.customers.find(function(c){ return (c.customer_id || c._id) === customerId; });
    if (c2) return c2.customer_name || customerId;
  }
  // The registry list the tools' customer bars read (app.js, toolCustomerId).
  var c3 = (_allCustomers || []).find(function(c){ return c._id === customerId; });
  if (c3) return c3.CustomerName || customerId;
  return customerId;
}

// ═══════════════════════════════════════════════════════════════════
// HOSTS MANAGEMENT
// ═══════════════════════════════════════════════════════════════════

export async function hostsLoad() {
  var box = _claim('hosts-content');
  var el = box.el;
  el.innerHTML = '<div class="loader loader-md"></div>';

  // Pre-load customer cache for name resolution
  if (!_infraCustomerCache) { await _populateCustomerSelect('_dummy_nonexistent_'); }

  var typeFilter = document.getElementById('hosts-filter-type').value;
  var groupFilter = document.getElementById('hosts-filter-group').value;

  var url = '/api/ssh/hosts';
  var params = [];
  if (typeFilter) params.push('device_type=' + typeFilter);
  if (groupFilter) params.push('group=' + encodeURIComponent(groupFilter));
  if (params.length) url += '?' + params.join('&');

  var data = await apiFetch(url);

  if (!box.owns()) return;
  if (!data) return;
  var hosts = data.hosts || [];

  // Populate group filter
  var groups = {};
  hosts.forEach(function(h) { if (h.group_name) groups[h.group_name] = true; });
  var grpSel = document.getElementById('hosts-filter-group');
  var curGrp = grpSel.value;
  grpSel.innerHTML = '<option value="">' + t('alle_grupper') + '</option>';
  Object.keys(groups).sort().forEach(function(g) {
    grpSel.innerHTML += '<option value="'+esc(g)+'"'+(g===curGrp?' selected':'')+'>'+esc(g)+'</option>';
  });

  if (!hosts.length) {
    el.innerHTML = '<div class="empty-state"><div class="empty-title">' + t('msg_no_hosts','No hosts registered') + '</div><div class="empty-desc">' + t('msg_add_first_host','Click "Add host" to get started.') + '</div><button class="btn btn-primary" data-write data-click-handler="hostsAdd">' + t('btn_add_host','Add host') + '</button></div>';
    return;
  }

  // ── Host cards: strict 3-row grid ──
  var html = '<div class="grid grid-auto-lg gap-3">';
  hosts.forEach(function(h) {
    var statusColor = h.is_reachable === true ? 'var(--green)' : h.is_reachable === false ? 'var(--red)' : 'var(--text-dim)';

    html += '<div class="card device-card edge-tone ' + toneVar(statusColor) + '">';

    // ROW 1 — Header (24px): label + group badge + status dot
    html += '<div class="device-card-head">';
    html += '<strong class="text-base nowrap overflow-hidden ellipsis flex-1 min-w-0">'+esc(h.label||'-')+'</strong>';
    html += '<span class="device-card-tag">'+esc(h.group_name||'-')+'</span>';
    html += '<span class="dot ' + toneClass(statusColor) + ' ml-2"></span>';
    html += '</div>';

    // ROW 2 — Subtitle (20px): connection info + customer
    html += '<div class="device-card-sub">';
    html += '<span class="font-mono">'+esc(h.hostname||'-')+':'+esc(h.port||'-')+'</span>';
    html += ' · '+esc(h.username||'-')+'@'+esc(h.device_type||'-');
    if (h.customer_id) {
      var _cn = _customerNameById(h.customer_id);
      html += ' <a href="#" data-click-handler="infraSelectCustomer" data-customer-id="' + esc(h.customer_id) + '" class="text-accent no-underline text-xs ml-1" title="' + t('lbl_customer','Customer') + '">' + esc(_cn) + '</a>';
    }
    html += '</div>';

    // ROW 3 — Data (1fr): actions — always render all 5 buttons
    var isDesktop = (h.device_type === 'windows' || h.device_type === 'linux');
    var isNetwork = (['fortigate','unifi','pfsense','openwrt'].indexOf(h.device_type) !== -1);
    var webPort = h.port === 22 ? 443 : Number(h.port);

    html += '<div class="grid grid-cols-2 gap-1 content-start pt-2">';
    html += '<button class="btn btn-ghost btn-sm" data-write data-click-handler="sshEditHost" data-id="'+esc(h.id)+'">' + t('btn_edit','Edit') + '</button>';
    html += '<button class="btn btn-ghost btn-sm text-accent" data-write data-click-handler="sshTerminal" data-id="'+esc(h.id)+'">SSH</button>';
    html += '<button class="btn btn-ghost btn-sm'+(isDesktop?'':' is-disabled')+'" data-write data-click-handler="sshRdp" data-hostname="'+esc(h.hostname)+'" data-username="'+esc(h.username)+'" data-host-id="'+esc(h.id)+'">RDP</button>';
    html += '<button class="btn btn-ghost btn-sm'+(isNetwork?'':' is-disabled')+'" data-click-handler="openWebUI" data-url="https://'+esc(h.hostname)+':'+webPort+'">' + t('web_ui') + '</button>';
    html += '<button class="btn btn-ghost btn-sm text-danger col-span-2 justify-self-start" data-write data-click-handler="sshDeleteHost" data-id="'+esc(h.id)+'">' + t('btn_delete','Delete') + '</button>';
    html += '</div>';

    html += '</div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

export function hostsAdd() {
  var el = _claim('hosts-content').el;

  // Load keys for dropdown
  apiFetch('/api/ssh/keys').then(function(keysData) {
    var keys = (keysData && keysData.keys) || [];
    var keyOpts = '<option value="">' + t('ingen_bruk_passord') + '</option>';
    keys.forEach(function(k) { keyOpts += '<option value="'+esc(k.id)+'">'+esc(k.name)+' ('+esc(k.fingerprint.slice(0,20))+'...)</option>'; });

    el.innerHTML = '<div class="max-w-md">'
      + '<h3 class="text-md fw-semibold mb-4">' + t('legg_til_vert') + '</h3>'

      // Device type first — determines which fields to show
      + '<label class="field-label">' + t('enhetstype') + '</label>'
      + '<select id="host-devtype" data-change-handler="hostsTypeChanged" class="field-input mb-3">'
      + '<option value="windows">' + t('windows_server') + '</option>'
      + '<option value="linux">' + t('linux') + '</option>'
      + '<option value="fortigate">' + t('fortigate') + '</option>'
      + '<option value="unifi">' + t('unifi') + '</option>'
      + '<option value="pfsense">' + t('pfsense') + '</option>'
      + '<option value="openwrt">' + t('openwrt') + '</option>'
      + '<option value="custom">' + t('annet') + '</option>'
      + '</select>'

      + '<div class="grid grid-cols-2 gap-3">'
      + '<div><label class="field-label">' + t('navn_2') + '</label>'
      + '<input id="host-label" type="text" placeholder="' + t('inf_ph_host_label','f.eks. DC01 eller FW-Hovedkontor') + '" class="field-input"></div>'
      + '<div><label class="field-label">' + t('hostname_ip') + '</label>'
      + '<input id="host-hostname" type="text" placeholder="f.eks. 10.0.1.5" class="field-input"></div>'
      + '<div><label class="field-label"><span id="host-user-label">' + t('brukernavn_2') + '</span></label>'
      + '<input id="host-username" type="text" placeholder="admin" class="field-input"></div>'
      + '<div><label class="field-label"><span id="host-port-label">' + t('ssh_port') + '</span></label>'
      + '<input id="host-port" type="number" value="22" class="field-input"></div>'
      + '<div><label class="field-label">' + t('gruppe') + '</label>'
      + '<input id="host-group" type="text" placeholder="f.eks. produksjon, lab" class="field-input"></div>'
      + '<div><label class="field-label">' + t('autentisering') + '</label>'
      + '<select id="host-auth" data-change-handler="hostsAuthChanged" class="field-input">'
      + '<option value="password">' + t('lbl_password','Password') + '</option>'
      + '<option value="key">' + t('lbl_ssh_key','SSH key') + '</option>'
      + '</select></div>'
      + '</div>'

      // Auth fields
      + '<div id="host-auth-pass" class="mt-3"><label class="field-label">' + t('passord_2') + '</label>'
      + '<input id="host-password" type="password" placeholder="' + t('placeholder_password','Password') + '" class="field-input"></div>'
      + '<div id="host-auth-key" class="mt-3" style="display:none;"><label class="field-label">' + t('lbl_ssh_key','SSH key') + '</label>'
      + '<select id="host-keyid" class="field-input">'+keyOpts+'</select></div>'

      // Customer selector
      + '<div class="mt-3"><label class="field-label">' + t('lbl_customer','Customer') + '</label>'
      + '<select id="host-customer" class="field-input"><option value="">-- ' + t('lbl_no_customer','No customer') + ' --</option></select></div>'

      // Notes
      + '<div class="mt-3"><label class="field-label">' + t('lbl_notes','Notes') + '</label>'
      + '<textarea id="host-notes" placeholder="' + t('placeholder_optional_notes','Optional notes...') + '" class="field-input textarea-sm resize-y"></textarea></div>'

      + '<div class="flex gap-2 mt-4">'
      + '<button class="btn btn-primary" data-write data-click-handler="hostsDoAdd">' + t('btn_add','Add') + '</button>'
      + '<button class="btn btn-ghost" data-click-handler="hostsLoad">' + t('btn_cancel','Cancel') + '</button>'
      + '</div></div>';

    _populateCustomerSelect('host-customer');
    hostsTypeChanged();
  });
}

function hostsTypeChanged() {
  var type = document.getElementById('host-devtype').value;
  var portEl = document.getElementById('host-port');
  var portLabel = document.getElementById('host-port-label');
  var userEl = document.getElementById('host-username');
  var userLabel = document.getElementById('host-user-label');

  // Set sensible defaults per device type
  var defaults = {
    windows:   {port: 22, user: 'administrator', portLabel: 'SSH/RDP-port', userLabel: t('inf_username','Brukernavn')},
    linux:     {port: 22, user: 'root', portLabel: 'SSH-port', userLabel: t('inf_username','Brukernavn')},
    fortigate: {port: 22, user: 'admin', portLabel: 'SSH-port', userLabel: t('inf_admin_user','Admin-bruker')},
    unifi:     {port: 22, user: 'ubnt', portLabel: 'SSH-port', userLabel: t('inf_ssh_user','SSH-bruker')},
    pfsense:   {port: 22, user: 'admin', portLabel: 'SSH-port', userLabel: t('inf_admin_user','Admin-bruker')},
    openwrt:   {port: 22, user: 'root', portLabel: 'SSH-port', userLabel: t('inf_username','Brukernavn')},
    custom:    {port: 22, user: '', portLabel: 'Port', userLabel: t('inf_username','Brukernavn')},
  };
  var d = defaults[type] || defaults.custom;
  portEl.value = d.port;
  if (!userEl.value || userEl.value === 'admin' || userEl.value === 'root' || userEl.value === 'ubnt' || userEl.value === 'administrator') {
    userEl.value = d.user;
    userEl.placeholder = d.user;
  }
  portLabel.textContent = d.portLabel;
  userLabel.textContent = d.userLabel;
}

function hostsAuthChanged() {
  var method = document.getElementById('host-auth').value;
  document.getElementById('host-auth-pass').style.display = method === 'password' ? 'block' : 'none';
  document.getElementById('host-auth-key').style.display = method === 'key' ? 'block' : 'none';
}

async function hostsDoAdd() {
  var body = {
    label: document.getElementById('host-label').value.trim(),
    hostname: document.getElementById('host-hostname').value.trim(),
    username: document.getElementById('host-username').value.trim(),
    port: parseInt(document.getElementById('host-port').value) || 22,
    device_type: document.getElementById('host-devtype').value,
    group_name: document.getElementById('host-group').value.trim(),
    auth_method: document.getElementById('host-auth').value,
    notes: document.getElementById('host-notes').value.trim(),
  };

  var custSel = document.getElementById('host-customer');
  if (custSel && custSel.value) body.customer_id = custSel.value;

  if (!body.label || !body.hostname || !body.username) {
    showToast(t('err_name_host_user_required','Name, hostname and username are required'), 'error');
    return;
  }

  if (body.auth_method === 'key') {
    var keyId = document.getElementById('host-keyid').value;
    if (keyId) body.auth_key_id = keyId;
  } else {
    var pass = document.getElementById('host-password').value;
    if (pass) body.password = pass;
  }

  var data = await apiFetch('/api/ssh/hosts', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if (data && data.ok) { showToast(t('msg_host_added','Host added'), 'success'); hostsLoad(); }
}

export async function hostsHealthAll() {
  showToast(t('msg_checking_all_hosts','Checking all hosts...'), 'info', 2000);
  var data = await apiFetch('/api/ssh/hosts/health', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
  if (data) { showToast(t('msg_health_check_done','Health check completed'), 'success'); hostsLoad(); }
}

// ═══════════════════════════════════════════════════════════════════
// SSH MANAGEMENT
// ═══════════════════════════════════════════════════════════════════

export async function sshShowKeys() {
  var box = _claim('ssh-content');
  var el = box.el;
  el.innerHTML = '<div class="loader loader-md"></div>';
  var data = await apiFetch('/api/ssh/keys');
  if (!box.owns() || !data) return;
  var keys = data.keys || [];
  var html = '<div class="flex gap-2 mb-3"><button class="btn btn-primary btn-sm" data-write data-click-handler="sshGenKey">' + t('btn_generate_key','Generate key') + '</button><button class="btn btn-ghost btn-sm" data-write data-click-handler="sshImportKey">' + t('btn_import_key','Import key') + '</button></div>';
  if (!keys.length) { html += '<p class="text-muted">' + t('msg_no_ssh_keys','No SSH keys created yet.') + '</p>'; }
  else {
    html += '<table class="data-table"><thead><tr><th class="p-2">' + t('lbl_name','Name') + '</th><th>' + t('lbl_type','Type') + '</th><th>' + t('fingerprint_2') + '</th><th>' + t('lbl_created','Created') + '</th><th></th></tr></thead><tbody>';
    keys.forEach(function(k) {
      html += '<tr>';
      html += '<td class="p-2 fw-semibold">'+esc(k.name)+'</td>';
      html += '<td class="p-2 text-center"><span class="py-0-5 px-2 bg-base rounded-sm text-xs font-mono">'+esc(k.key_type)+'</span></td>';
      html += '<td class="p-2 font-mono text-xs text-muted">'+esc(k.fingerprint)+'</td>';
      html += '<td class="p-2 text-sm text-muted">'+esc(k.created_at.slice(0,10))+'</td>';
      html += '<td class="p-2 nowrap"><button class="btn btn-ghost btn-sm" data-click-handler="sshViewKey" data-id="'+esc(k.id)+'">' + t('vis') + '</button> <button class="btn btn-ghost btn-sm text-danger" data-write data-click-handler="sshDeleteKey" data-id="'+esc(k.id)+'">' + t('slett') + '</button></td>';
      html += '</tr>';
    });
    html += '</tbody></table>';
  }
  el.innerHTML = html;
}

export function sshGenKey() {
  var el = _claim('ssh-content').el;
  el.innerHTML = '<div class="max-w-md">'
    + '<h3 class="text-md fw-semibold mb-4">' + t('hdr_generate_ssh_key','Generate SSH key') + '</h3>'
    + '<label class="field-label">' + t('navn_2') + '</label>'
    + '<input id="ssh-gen-name" type="text" placeholder="' + t('inf_ph_keyname','f.eks. deploy-key-kunde') + '" class="field-input mb-3">'
    + '<label class="field-label">' + t('lbl_key_type','Key type') + '</label>'
    + '<select id="ssh-gen-type" class="field-input mb-3">'
    + '<option value="ed25519">' + t('opt_ed25519','Ed25519 (recommended — fast, secure, short key)') + '</option>'
    + '<option value="rsa4096">' + t('opt_rsa4096','RSA 4096-bit (broad compatibility)') + '</option>'
    + '<option value="rsa2048">' + t('opt_rsa2048','RSA 2048-bit (legacy devices)') + '</option>'
    + '</select>'
    + '<label class="field-label">' + t('lbl_description_optional','Description (optional)') + '</label>'
    + '<input id="ssh-gen-desc" type="text" placeholder="' + t('placeholder_key_desc','e.g. Used for automatic deploy to web servers') + '" class="field-input mb-3">'
    + '<label class="field-label">' + t('lbl_tags_optional','Tags (comma-separated, optional)') + '</label>'
    + '<input id="ssh-gen-tags" type="text" placeholder="f.eks. produksjon, deploy, web" class="field-input mb-4">'
    + '<div id="ssh-gen-result" class="inset mb-4" style="display:none;"></div>'
    + '<div class="flex gap-2">'
    + '<button class="btn btn-primary" id="ssh-gen-btn" data-write data-click-handler="sshDoGenKey">' + t('btn_generate','Generate') + '</button>'
    + '<button class="btn btn-ghost" data-click-handler="sshShowKeys">' + t('btn_cancel','Cancel') + '</button>'
    + '</div></div>';
}

async function sshDoGenKey() {
  var name = document.getElementById('ssh-gen-name').value.trim();
  if (!name) { showToast(t('err_give_key_name','Give the key a name'),'error'); return; }
  var keyType = document.getElementById('ssh-gen-type').value;
  var desc = document.getElementById('ssh-gen-desc').value.trim();
  var tagsStr = document.getElementById('ssh-gen-tags').value.trim();
  var tags = tagsStr ? tagsStr.split(',').map(function(s){return s.trim();}).filter(Boolean) : [];

  var btn = document.getElementById('ssh-gen-btn');
  btn.disabled = true; btn.textContent = t('msg_generating','Generating...');

  var data = await apiFetch('/api/ssh/keys', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name, key_type:keyType, description:desc, tags:tags})});
  btn.disabled = false; btn.textContent = t('btn_generate','Generate');

  if (data && data.ok) {
    var k = data.key;
    var resEl = document.getElementById('ssh-gen-result');
    resEl.style.display = 'block';
    resEl.innerHTML = '<div class="flex items-center gap-2 mb-3"><span class="text-lg">&#10003;</span><strong class="text-success">' + t('msg_key_created','Key created') + '</strong></div>'
      + '<div class="text-sm mb-2"><strong>' + t('fingerprint') + '</strong> <span class="font-mono">'+esc(k.fingerprint)+'</span></div>'
      + '<div class="text-sm mb-2"><strong>' + t('type_3') + '</strong> '+esc(k.key_type)+'</div>'
      + '<label class="field-label">' + t('lbl_public_key_copy','Public key (copy to servers):') + '</label>'
      + '<div class="relative"><textarea readonly class="field-input textarea-sm resize-none">'+esc(k.public_key)+'</textarea>'
      + '<button data-click-handler="sshCopyPublicKey" data-key="'+esc(k.public_key)+'" class="copy-overlay">' + t('btn_copy','Copy') + '</button></div>';
    showToast(t('msg_ssh_key_generated','SSH key generated'),'success');
  }
}

function sshImportKey() {
  var el = _claim('ssh-content').el;
  el.innerHTML = '<div class="max-w-md">'
    + '<h3 class="text-md fw-semibold mb-4">' + t('hdr_import_ssh_key','Import SSH key') + '</h3>'
    + '<label class="field-label">' + t('navn_2') + '</label>'
    + '<input id="ssh-imp-name" type="text" placeholder="f.eks. eksisterende-deploy-key" class="field-input mb-3">'
    + '<label class="field-label">' + t('lbl_private_key_pem','Private key (PEM or OpenSSH format)') + '</label>'
    + '<textarea id="ssh-imp-pem" rows="8" placeholder="-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----" class="field-input mb-3 resize-y font-mono"></textarea>'
    + '<label class="field-label">' + t('lbl_description_optional','Description (optional)') + '</label>'
    + '<input id="ssh-imp-desc" type="text" placeholder="' + t('placeholder_key_desc','e.g. Used for automatic deploy to web servers') + '" class="field-input mb-3">'
    + '<label class="field-label">' + t('lbl_tags_optional','Tags (comma-separated, optional)') + '</label>'
    + '<input id="ssh-imp-tags" type="text" placeholder="f.eks. produksjon, deploy, web" class="field-input mb-4">'
    + '<div id="ssh-imp-result" class="inset mb-4" style="display:none;"></div>'
    + '<div class="flex gap-2">'
    + '<button class="btn btn-primary" id="ssh-imp-btn" data-write data-click-handler="sshDoImportKey">' + t('btn_import','Import') + '</button>'
    + '<button class="btn btn-ghost" data-click-handler="sshShowKeys">' + t('btn_cancel','Cancel') + '</button>'
    + '</div></div>';
}

async function sshDoImportKey() {
  var name = document.getElementById('ssh-imp-name').value.trim();
  if (!name) { showToast(t('err_give_key_name','Give the key a name'),'error'); return; }
  var pem = document.getElementById('ssh-imp-pem').value;
  if (!pem.trim()) { showToast(t('err_paste_private_key','Paste the private key'),'error'); return; }
  var desc = document.getElementById('ssh-imp-desc').value.trim();
  var tagsStr = document.getElementById('ssh-imp-tags').value.trim();
  var tags = tagsStr ? tagsStr.split(',').map(function(s){return s.trim();}).filter(Boolean) : [];

  var btn = document.getElementById('ssh-imp-btn');
  btn.disabled = true; btn.textContent = t('msg_importing','Importing...');

  var data = await apiFetch('/api/ssh/keys/import', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name, private_key_pem:pem, description:desc, tags:tags})});
  btn.disabled = false; btn.textContent = t('btn_import','Import');

  if (data && data.ok) {
    var k = data.key;
    var resEl = document.getElementById('ssh-imp-result');
    resEl.style.display = 'block';
    resEl.innerHTML = '<div class="flex items-center gap-2 mb-3"><span class="text-lg">&#10003;</span><strong class="text-success">' + t('msg_key_imported','Key imported') + '</strong></div>'
      + '<div class="text-sm mb-2"><strong>' + t('fingerprint') + '</strong> <span class="font-mono">'+esc(k.fingerprint)+'</span></div>'
      + '<div class="text-sm mb-2"><strong>' + t('type_3') + '</strong> '+esc(k.key_type)+'</div>'
      + '<label class="field-label">' + t('lbl_public_key_copy','Public key (copy to servers):') + '</label>'
      + '<div class="relative"><textarea readonly class="field-input textarea-sm resize-none">'+esc(k.public_key)+'</textarea>'
      + '<button data-click-handler="sshCopyPublicKey" data-key="'+esc(k.public_key)+'" class="copy-overlay">' + t('btn_copy','Copy') + '</button></div>';
    showToast(t('msg_ssh_key_imported','Key imported') + ': ' + k.fingerprint, 'success', 5000);
  }
}

async function sshViewKey(keyId) {
  var box = _claim('ssh-content');
  var data = await apiFetch('/api/ssh/keys/' + encodeURIComponent(keyId));
  if (!box.owns() || !data || !data.key) return;
  var k = data.key;
  var el = box.el;
  var html = '<div class="max-w-md">'
    + '<div class="flex items-center gap-3 mb-4">'
    + '<button class="btn btn-ghost btn-sm" data-click-handler="sshShowKeys">' + t('tilbake') + '</button>'
    + '<h3 class="text-md fw-semibold m-0">'+esc(k.name)+'</h3>'
    + '<span class="py-0-5 px-2 bg-base rounded-sm text-xs font-mono">'+esc(k.key_type)+'</span>'
    + '</div>'
    + '<div class="card p-4">'
    + '<table class="w-full text-ui">'
    + '<tr class="border-b"><td class="kv-key">' + t('fingerprint_2') + '</td><td class="p-2 font-mono text-xs">'+esc(k.fingerprint)+'</td></tr>'
    + '<tr class="border-b"><td class="p-2 text-muted">' + t('type_3') + '</td><td class="p-2">'+esc(k.key_type)+'</td></tr>'
    + '<tr class="border-b"><td class="p-2 text-muted">' + t('lbl_created','Created') + '</td><td class="p-2">'+esc(k.created_at.slice(0,10))+'</td></tr>';
  if (k.description) html += '<tr class="border-b"><td class="p-2 text-muted">' + t('lbl_description','Description') + '</td><td class="p-2">'+esc(k.description)+'</td></tr>';
  html += '</table></div>'
    + '<div class="mt-3"><label class="field-label">' + t('public_key') + '</label>'
    + '<div class="relative"><textarea readonly class="inset w-full textarea-sm text-default text-xs font-mono resize-none">'+esc(k.public_key)+'</textarea>'
    + '<button data-click-handler="sshCopyPublicKey" data-key="'+esc(k.public_key)+'" class="copy-overlay">' + t('btn_copy','Copy') + '</button></div></div>';

  // Show deployments
  if (data.deployments && data.deployments.length) {
    html += '<div class="mt-4"><div class="subhead">' + t('lbl_deployed_to','Deployed to') + ' ('+data.deployments.length+' ' + t('lbl_hosts','hosts') + ')</div>';
    data.deployments.forEach(function(d) {
      html += '<div class="text-sm text-muted py-1 px-0">' + t('lbl_host','Host') + ': '+esc(d.host_id.slice(0,8))+'... · '+esc(d.deployed_at.slice(0,10))+'</div>';
    });
    html += '</div>';
  }

  html += '</div>';
  el.innerHTML = html;
}

async function sshDeleteKey(id) {
  if (!await showConfirm(t('dlg_confirm_delete_ssh_key'))) return;
  await apiFetch('/api/ssh/keys/'+encodeURIComponent(id), {method:'DELETE'});
  sshShowKeys();
}

async function sshShowHosts() {
  var box = _claim('ssh-content');
  var el = box.el;
  el.innerHTML = '<div class="loader loader-md"></div>';
  var data = await apiFetch('/api/ssh/hosts');
  if (!box.owns() || !data) return;
  var hosts = data.hosts || [];
  var html = '<div class="flex gap-2 mb-3"><button class="btn btn-primary btn-sm" data-write data-click-handler="sshAddHost">' + t('legg_til_vert') + '</button><button class="btn btn-ghost btn-sm" data-click-handler="sshHealthAll">' + t('sjekk_alle') + '</button></div>';
  if (!hosts.length) { html += '<p class="text-muted">' + t('msg_no_hosts_short','No hosts registered.') + '</p>'; }
  else {
    html += '<table class="data-table"><thead><tr><th class="p-2">' + t('navn_2') + '</th><th>' + t('host_2') + '</th><th>' + t('type_3') + '</th><th>' + t('gruppe') + '</th><th>' + t('lbl_customer','Customer') + '</th><th>' + t('status_3') + '</th><th></th></tr></thead><tbody>';
    hosts.forEach(function(h) {
      var statusColor = h.is_reachable === true ? 'var(--green)' : h.is_reachable === false ? 'var(--red)' : 'var(--text-dim)';
      var statusDot = '<span class="dot ' + toneClass(statusColor) + '"></span>';
      var _custName = h.customer_id ? _customerNameById(h.customer_id) : '-';
      html += '<tr>';
      html += '<td class="p-2 fw-semibold">'+esc(h.label)+'</td>';
      html += '<td class="p-2 font-mono text-sm">'+esc(h.hostname)+':'+esc(h.port)+'</td>';
      html += '<td class="p-2 text-sm">'+esc(h.device_type)+'</td>';
      html += '<td class="p-2 text-sm text-muted">'+esc(h.group_name||'-')+'</td>';
      html += '<td class="p-2 text-sm">' + (h.customer_id ? '<a href="#" data-click-handler="infraSelectCustomer" data-customer-id="' + esc(h.customer_id) + '" class="text-accent no-underline">' + esc(_custName) + '</a>' : '-') + '</td>';
      html += '<td class="p-2 text-center">'+statusDot+'</td>';
      html += '<td class="p-2 nowrap">';
      html += '<button class="btn btn-ghost btn-sm" data-write data-click-handler="sshEditHost" data-id="'+esc(h.id)+'">' + t('rediger') + '</button> ';
      html += '<button class="btn btn-ghost btn-sm text-accent" data-write data-click-handler="sshTerminal" data-id="'+esc(h.id)+'">SSH</button> ';
      if (h.device_type === 'windows' || h.device_type === 'linux') {
        html += '<button class="btn btn-ghost btn-sm text-purple" data-write data-click-handler="sshRdp" data-hostname="'+esc(h.hostname)+'" data-username="'+esc(h.username)+'">RDP</button> ';
      }
      html += '<button class="btn btn-ghost btn-sm text-danger" data-write data-click-handler="sshDeleteHost" data-id="'+esc(h.id)+'">' + t('slett') + '</button>';
      html += '</td>';
      html += '</tr>';
    });
    html += '</tbody></table>';
  }
  el.innerHTML = html;
}

function sshAddHost() {
  var box = _claim('ssh-content');
  // Load keys for dropdown
  apiFetch('/api/ssh/keys').then(function(keysData) {
    if (!box.owns()) return;
    var keys = (keysData && keysData.keys) || [];
    var keyOpts = '<option value="">' + t('ingen_bruk_passord') + '</option>';
    keys.forEach(function(k) { keyOpts += '<option value="'+esc(k.id)+'">'+esc(k.name)+' ('+esc(k.key_type)+' · '+esc(k.fingerprint.slice(0,20))+'...)</option>'; });

    var el = box.el;
    el.innerHTML = '<div class="max-w-md">'
      + '<h3 class="text-md fw-semibold mb-4">' + t('legg_til_vertsmaskin') + '</h3>'
      + '<div class="grid grid-cols-2 gap-3">'
      // Rad 1: Navn + Hostname
      + '<div><label class="field-label">' + t('navn_label') + '</label>'
      + '<input id="ssh-h-label" type="text" placeholder="f.eks. Webserver Prod" class="field-input"></div>'
      + '<div><label class="field-label">' + t('hostname_ip') + '</label>'
      + '<input id="ssh-h-host" type="text" placeholder="f.eks. 10.0.1.5" class="field-input"></div>'
      // Rad 2: Brukernavn + Port
      + '<div><label class="field-label">' + t('brukernavn_2') + '</label>'
      + '<input id="ssh-h-user" type="text" value="root" placeholder="root" class="field-input"></div>'
      + '<div><label class="field-label">' + t('port_2') + '</label>'
      + '<input id="ssh-h-port" type="number" value="22" min="1" max="65535" class="field-input"></div>'
      // Rad 3: Enhetstype + Gruppe
      + '<div><label class="field-label">' + t('enhetstype') + '</label>'
      + '<select id="ssh-h-devtype" class="field-input">'
      + '<option value="linux">Linux</option>'
      + '<option value="fortigate">FortiGate</option>'
      + '<option value="unifi">UniFi</option>'
      + '<option value="pfsense">pfSense</option>'
      + '<option value="openwrt">OpenWrt</option>'
      + '<option value="windows">Windows</option>'
      + '<option value="custom">' + t('annet') + '</option>'
      + '</select></div>'
      + '<div><label class="field-label">' + t('gruppe') + '</label>'
      + '<input id="ssh-h-group" type="text" placeholder="' + t('inf_ph_group','f.eks. produksjon, lab, kunde-x') + '" class="field-input"></div>'
      + '</div>'
      // Autentisering
      + '<div class="mt-4 pt-4 border-t">'
      + '<label class="field-label">' + t('lbl_auth_method','Authentication method') + '</label>'
      + '<select id="ssh-h-auth" data-change-handler="sshHostAuthChanged" class="field-input mb-3">'
      + '<option value="key">' + t('lbl_ssh_key','SSH key') + '</option>'
      + '<option value="password">' + t('lbl_password','Password') + '</option>'
      + '</select>'
      + '<div id="ssh-h-auth-key">'
      + '<label class="field-label">' + t('lbl_ssh_key','SSH key') + '</label>'
      + '<select id="ssh-h-keyid" class="field-input">'+keyOpts+'</select>'
      + '</div>'
      + '<div id="ssh-h-auth-pass" style="display:none;">'
      + '<label class="field-label">' + t('lbl_password','Password') + '</label>'
      + '<input id="ssh-h-pass" type="password" placeholder="' + t('placeholder_ssh_password','SSH password') + '" class="field-input">'
      + '</div></div>'
      // Customer selector
      + '<div class="mt-3">'
      + '<label class="field-label">' + t('lbl_customer','Customer') + '</label>'
      + '<select id="ssh-h-customer" class="field-input"><option value="">-- ' + t('lbl_no_customer','No customer') + ' --</option></select>'
      + '</div>'
      // Notater
      + '<div class="mt-3">'
      + '<label class="field-label">' + t('lbl_notes_optional','Notes (optional)') + '</label>'
      + '<textarea id="ssh-h-notes" placeholder="' + t('placeholder_notes_example','e.g. Belongs to customer X, maintenance window Sundays...') + '" class="field-input textarea-sm resize-y"></textarea>'
      + '</div>'
      // Knapper
      + '<div class="flex gap-2 mt-4">'
      + '<button class="btn btn-primary" data-write data-click-handler="sshDoAddHost">' + t('btn_add','Add') + '</button>'
      + '<button class="btn btn-ghost" data-click-handler="sshShowHosts">' + t('btn_cancel','Cancel') + '</button>'
      + '</div></div>';
    _populateCustomerSelect('ssh-h-customer');
  });
}

function sshHostAuthChanged() {
  var method = document.getElementById('ssh-h-auth').value;
  document.getElementById('ssh-h-auth-key').style.display = method === 'key' ? 'block' : 'none';
  document.getElementById('ssh-h-auth-pass').style.display = method === 'password' ? 'block' : 'none';
}

async function sshDoAddHost() {
  var label = document.getElementById('ssh-h-label').value.trim();
  var hostname = document.getElementById('ssh-h-host').value.trim();
  var username = document.getElementById('ssh-h-user').value.trim();
  if (!label || !hostname || !username) { showToast(t('err_name_host_user_required','Name, hostname and username are required'),'error'); return; }

  var body = {
    label: label,
    hostname: hostname,
    username: username,
    port: parseInt(document.getElementById('ssh-h-port').value) || 22,
    device_type: document.getElementById('ssh-h-devtype').value,
    group_name: document.getElementById('ssh-h-group').value.trim(),
    auth_method: document.getElementById('ssh-h-auth').value,
    notes: document.getElementById('ssh-h-notes').value.trim(),
  };

  var custSel = document.getElementById('ssh-h-customer');
  if (custSel && custSel.value) body.customer_id = custSel.value;

  if (body.auth_method === 'key') {
    var keyId = document.getElementById('ssh-h-keyid').value;
    if (keyId) body.auth_key_id = keyId;
  } else {
    var pass = document.getElementById('ssh-h-pass').value;
    if (pass) body.password = pass;
  }

  var data = await apiFetch('/api/ssh/hosts', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if (data && data.ok) { showToast(t('msg_host_added','Host added'),'success'); sshShowHosts(); }
}

async function sshDeleteHost(id) {
  if (!await showConfirm(t('dlg_confirm_delete_ssh_host'))) return;
  await apiFetch('/api/ssh/hosts/'+encodeURIComponent(id), {method:'DELETE'});
  sshShowHosts();
}

async function sshEditHost(hostId) {
  // The hosts view when it is there, else the SSH view.
  var box = _claim(document.getElementById('hosts-content') ? 'hosts-content' : 'ssh-content');
  var data = await apiFetch('/api/ssh/hosts/' + encodeURIComponent(hostId));
  if (!box.owns() || !data || !data.host) return;
  var h = data.host;

  // Load keys for dropdown
  var keysData = await apiFetch('/api/ssh/keys');
  var keys = (keysData && keysData.keys) || [];
  var keyOpts = '<option value="">' + t('ingen_bruk_passord') + '</option>';
  keys.forEach(function(k) { keyOpts += '<option value="'+esc(k.id)+'"'+(k.id===h.auth_key_id?' selected':'')+'>'+esc(k.name)+' ('+esc(k.fingerprint.slice(0,20))+'...)</option>'; });

  if (!box.owns()) return;
  var el = box.el;
  el.innerHTML = '<div class="max-w-md">'
    + '<h3 class="text-md fw-semibold mb-4">' + t('rediger_vertsmaskin') + '</h3>'
    + '<div class="grid grid-cols-2 gap-3">'
    + '<div><label class="field-label">' + t('navn_2') + '</label>'
    + '<input id="ssh-e-label" type="text" value="'+esc(h.label)+'" class="field-input"></div>'
    + '<div><label class="field-label">' + t('hostname_ip') + '</label>'
    + '<input id="ssh-e-host" type="text" value="'+esc(h.hostname)+'" class="field-input"></div>'
    + '<div><label class="field-label">' + t('brukernavn_2') + '</label>'
    + '<input id="ssh-e-user" type="text" value="'+esc(h.username)+'" class="field-input"></div>'
    + '<div><label class="field-label">' + t('port_2') + '</label>'
    + '<input id="ssh-e-port" type="number" value="'+esc(h.port)+'" class="field-input"></div>'
    + '<div><label class="field-label">' + t('enhetstype') + '</label>'
    + '<select id="ssh-e-devtype" class="field-input">'
    + ['linux','fortigate','unifi','pfsense','openwrt','windows','custom'].map(function(t){return '<option value="'+t+'"'+(t===h.device_type?' selected':'')+'>'+t+'</option>';}).join('')
    + '</select></div>'
    + '<div><label class="field-label">' + t('gruppe') + '</label>'
    + '<input id="ssh-e-group" type="text" value="'+esc(h.group_name||'')+'" class="field-input"></div>'
    + '</div>'
    + '<div class="mt-3"><label class="field-label">' + t('passord_2') + '</label>'
    + '<input id="ssh-e-pass" type="password" placeholder="(uendret)" class="field-input"></div>'
    + '<div class="mt-3"><label class="field-label">' + t('lbl_ssh_key','SSH key') + '</label>'
    + '<select id="ssh-e-keyid" class="field-input">'+keyOpts+'</select></div>'
    + '<div class="mt-3"><label class="field-label">' + t('lbl_customer','Customer') + '</label>'
    + '<select id="ssh-e-customer" class="field-input"><option value="">-- ' + t('lbl_no_customer','No customer') + ' --</option></select></div>'
    + '<div class="mt-3"><label class="field-label">' + t('lbl_notes','Notes') + '</label>'
    + '<textarea id="ssh-e-notes" class="field-input textarea-sm resize-y">'+esc(h.notes||'')+'</textarea></div>'
    + '<div class="flex gap-2 mt-4">'
    + '<button class="btn btn-primary" data-write data-click-handler="sshDoEditHost" data-id="'+esc(hostId)+'">' + t('btn_save','Save') + '</button>'
    + '<button class="btn btn-ghost" data-click-handler="sshEditHostCancel">' + t('btn_cancel','Cancel') + '</button>'
    + '</div></div>';
  _populateCustomerSelect('ssh-e-customer', h.customer_id);
}

async function sshDoEditHost(hostId) {
  var body = {
    label: document.getElementById('ssh-e-label').value.trim(),
    hostname: document.getElementById('ssh-e-host').value.trim(),
    username: document.getElementById('ssh-e-user').value.trim(),
    port: parseInt(document.getElementById('ssh-e-port').value) || 22,
    device_type: document.getElementById('ssh-e-devtype').value,
    group_name: document.getElementById('ssh-e-group').value.trim(),
    auth_key_id: document.getElementById('ssh-e-keyid').value || null,
    notes: document.getElementById('ssh-e-notes').value.trim(),
    customer_id: document.getElementById('ssh-e-customer').value || null,
  };
  var pass = document.getElementById('ssh-e-pass').value;
  if (pass) body.password = pass;
  var data = await apiFetch('/api/ssh/hosts/' + encodeURIComponent(hostId), {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if (data && data.ok) { showToast(t('msg_host_updated','Host updated'),'success'); hostsLoad ? hostsLoad() : sshShowHosts(); }
}

async function sshRdp(hostname, username, hostId) {
  // Navigate to RDP view and pre-fill host details
  _rdpPendingHostId = hostId || '';
  showView('rdp');
  setTimeout(function() {
    var hostInput = document.getElementById('rdp-host-input');
    var userInput = document.getElementById('rdp-user-input');
    if (hostInput && hostId) hostInput.value = hostId;
    if (userInput) userInput.value = username || '';
  }, 200);
}

function sshTerminal(hostId) {
  showView('terminal');
  document.getElementById('term-mode').value = 'ssh';
  termModeChanged();
  setTimeout(function() {
    document.getElementById('term-host-select').value = hostId;
    termConnect();
  }, 500);
}

async function sshHealthAll() {
  showToast(t('msg_checking_all_hosts','Checking all hosts...'),'info',2000);
  var data = await apiFetch('/api/ssh/hosts/health', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
  if (data) { showToast(t('msg_health_check_done','Health check completed'),'success'); sshShowHosts(); }
}

export async function sshShowExec() {
  var box = _claim('ssh-content');
  var el = box.el;
  el.innerHTML = '<div class="mb-3"><label class="text-ui fw-semibold">' + t('lbl_select_hosts_command','Select hosts and enter a command:') + '</label></div>'
    + '<div id="ssh-exec-hosts" class="mb-3"></div>'
    + '<div class="flex gap-2"><input id="ssh-exec-cmd" type="text" placeholder="f.eks. uptime" class="field-input flex-1 font-mono w-auto" data-keydown-handler="sshExecRunOnEnter"><button class="btn btn-primary" data-write data-click-handler="sshExecRun">' + t('btn_run','Run') + '</button></div>'
    + '<div id="ssh-exec-results" class="mt-4"></div>';
  // Load hosts for checkboxes
  var data = await apiFetch('/api/ssh/hosts');
  if (!box.owns() || !data) return;
  var hhtml = '';
  (data.hosts||[]).forEach(function(h) {
    hhtml += '<label class="inline-flex items-center gap-1 mr-3 text-ui cursor-pointer"><input type="checkbox" class="ssh-exec-host-cb" value="'+esc(h.id)+'"> '+esc(h.label)+'</label>';
  });
  document.getElementById('ssh-exec-hosts').innerHTML = hhtml || '<span class="text-muted">' + t('msg_no_hosts_short','No hosts registered.') + '</span>';
}

async function sshExecRun() {
  var cmd = document.getElementById('ssh-exec-cmd').value.trim();
  if (!cmd) return;
  var ids = []; document.querySelectorAll('.ssh-exec-host-cb:checked').forEach(function(cb){ids.push(cb.value);});
  if (!ids.length) { showToast(t('err_select_at_least_one_host','Select at least one host'),'error'); return; }
  document.getElementById('ssh-exec-results').innerHTML = '<div class="loader loader-md mx-auto my-3"></div>';
  var data = await apiFetch('/api/ssh/exec', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({host_ids:ids,command:cmd})});
  if (!data) return;
  var html = '';
  (data.results||[]).forEach(function(r) {
    var color = r.exit_code === 0 ? 'var(--green)' : 'var(--red)';
    html += '<div class="bg-card border rounded-lg p-3 mb-2">';
    html += '<div class="flex justify-between mb-2"><strong>'+esc(r.host_label)+'</strong><span class="' + toneClass(color) + ' text-sm">rc='+esc(String(r.exit_code))+'</span></div>';
    if (r.stdout) html += '<pre class="text-sm font-mono text-muted pre-wrap m-0">'+esc(r.stdout)+'</pre>';
    if (r.stderr) html += '<pre class="text-sm font-mono text-danger pre-wrap mt-1 mb-0">'+esc(r.stderr)+'</pre>';
    if (r.error) html += '<div class="text-danger text-sm mt-1">'+esc(r.error)+'</div>';
    html += '</div>';
  });
  document.getElementById('ssh-exec-results').innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════
// VPN MANAGEMENT
// ═══════════════════════════════════════════════════════════════════

// A view's content box holds a list or one form at a time. Whatever takes a
// box over claims it, and an async load checks owns() before writing: if
// something else claimed the box meanwhile, the late answer is dropped.
// Without this, opening "new profile" before the VPN list had loaded lost the
// form the moment the list arrived; the hosts and SSH views had the same race.
var _contentSeq = {};
function _claim(id) {
  var seq = (_contentSeq[id] || 0) + 1;
  _contentSeq[id] = seq;
  return {
    el: document.getElementById(id),
    owns: function() { return _contentSeq[id] === seq; },
  };
}

function _vpnStatField(label, value) {
  if (!value) return '';
  return '<div><div class="text-dim">' + esc(label) + '</div><div class="font-mono text-default fw-semibold">' + esc(String(value)) + '</div></div>';
}

export async function vpnLoadProfiles() {
  var box = _claim('vpn-content');
  var el = box.el;
  el.innerHTML = '<div class="loader loader-md"></div>';
  if (!_infraCustomerCache) { await _populateCustomerSelect('_dummy_nonexistent_'); }
  var data = await apiFetch('/api/vpn/profiles');
  var status = await apiFetch('/api/vpn/status');
  if (!box.owns()) return;
  if (!data) return;
  // Update status badge
  var badge = document.getElementById('vpn-status-badge');
  if (badge && status) {
    var conns = (status.connections || []);
    var activeCount = conns.filter(function(c){return c.state==='connected';}).length;
    var connectingCount = conns.filter(function(c){return c.state==='connecting';}).length;
    var st = activeCount > 0 ? 'connected' : connectingCount > 0 ? 'connecting' : 'disconnected';
    var colors = {connected:'var(--green)',connecting:'var(--orange)',disconnected:'var(--text-dim)',error:'var(--red)'};
    var label = st === 'connected' ? (activeCount > 1 ? activeCount + ' VPN' : t('vpn_connected','Connected'))
      : st === 'connecting' ? t('vpn_connecting','Connecting...')
      : t('vpn_disconnected','Disconnected');
    badge.textContent = label;
    badge.style.color = colors[st] || 'var(--text-dim)';
    badge.style.borderColor = colors[st] || 'var(--border)';
  }
  var profiles = data.profiles || [];
  var vpnCapabilities = (status && status.capabilities && status.capabilities.protocols) || {};
  var protocolLabels = {
    wireguard: 'WireGuard', openvpn: 'OpenVPN', azure: 'Azure P2S VPN',
    fortigate_ipsec: 'FortiGate IPsec', fortigate: 'FortiGate SSL',
  };
  var protocolIcons = {
    wireguard: '', openvpn: '', azure: '',
    fortigate_ipsec: '', fortigate: '',
  };
  var html = '';
  var unavailableProtocols = Object.keys(vpnCapabilities).filter(function(protocol) {
    return vpnCapabilities[protocol] && !vpnCapabilities[protocol].available;
  });
  if (unavailableProtocols.length) {
    var firstUnavailable = vpnCapabilities[unavailableProtocols[0]];
    html += '<div class="card vpn-capability-warning">'
      + '<strong>' + t('vpn_external_control','External VPN control') + '</strong><br>'
      + esc(firstUnavailable.reason || t('vpn_external_control_desc','Tunnels must be established outside Sybr HUB on this host.'))
      + '</div>';
  }
  if (!profiles.length) { html = '<div class="empty-state p-8"><div class="empty-title">' + t('msg_no_vpn_profiles','No VPN profiles') + '</div><div class="empty-desc">' + t('msg_import_vpn','Import a .conf, .ovpn or .xml file to add a profile.') + '</div></div>'; }
  else {
    // Connection info summary when connected
    if (status && status.state === 'connected') {
      var stats = status.stats || {};
      var protoName = protocolLabels[stats.protocol] || stats.protocol || '';
      html += '<div class="card is-live mb-4">'
        + '<div class="flex items-center gap-3 mb-4">'
        + '<span class="dot dot-lg dot-glow text-success"></span>'
        + '<strong class="text-success flex-1">' + t('vpn_connected','Connected') + (stats.profile_name ? ' · ' + esc(stats.profile_name) : '') + '</strong>'
        + '<span class="text-xs text-muted bg-base py-0-5 px-2 rounded-sm">' + esc(protoName) + '</span>'
        + '</div>'
        + '<div class="grid grid-auto-sm gap-y-3 gap-x-4 text-xs">'
        + _vpnStatField('Interface', status.interface)
        + _vpnStatField('Local IP', stats.local_ip)
        + _vpnStatField('Subnet', stats.subnet || stats.local_subnet)
        + _vpnStatField('Public IP', stats.public_ip)
        + _vpnStatField('Remote', stats.remote_ip)
        + _vpnStatField('Gateway', stats.gateway)
        + _vpnStatField('MTU', stats.mtu)
        + _vpnStatField('DNS', stats.dns_servers)
        + _vpnStatField('Encryption', stats.encryption)
        + _vpnStatField('TX', stats.tx_bytes ? _formatBytes(stats.tx_bytes) + (stats.tx_packets ? ' (' + stats.tx_packets + ' pkts)' : '') : null)
        + _vpnStatField('RX', stats.rx_bytes ? _formatBytes(stats.rx_bytes) + (stats.rx_packets ? ' (' + stats.rx_packets + ' pkts)' : '') : null)
        + _vpnStatField('Uptime', stats.uptime)
        + _vpnStatField(t('bc_network','Routes'), stats.route_count ? stats.route_count + ' ' + t('lbl_routes','routes') : null)
        + '</div>'
        + (stats.remote_subnets && stats.remote_subnets.length ? '<div class="mt-3"><div class="text-xs text-dim mb-1">' + t('remote_subnets') + '</div><div class="py-2 px-3 bg-base rounded-sm font-mono text-2xs text-muted">' + stats.remote_subnets.map(function(r){return esc(r)}).join(' &middot; ') + '</div></div>' : '')
        + (stats.routes && stats.routes.length ? '<div class="mt-3"><div class="text-xs text-dim mb-1">' + t('lbl_routes','Routes') + '</div><div class="py-2 px-3 bg-base rounded-sm font-mono text-2xs text-muted max-h-sm overflow-y-auto">' + stats.routes.map(function(r){return esc(r)}).join('<br>') + '</div></div>' : '')
        + '</div>';
    }

    html += '<div class="grid grid-auto-lg gap-4">';
    profiles.forEach(function(p) {
      var conns = (status && status.connections) || [];
      var myConn = conns.find(function(c){return c.profile_id === p.id;});
      var isActive = myConn && myConn.state === 'connected';
      var isConnecting = myConn && myConn.state === 'connecting';
      var protoLabel = protocolLabels[p.protocol] || p.protocol;
      var protoIcon = protocolIcons[p.protocol] || '';
      var protocolCapability = vpnCapabilities[p.protocol];
      var mayConnect = !protocolCapability || protocolCapability.available;
      var statusDot = isActive ? '<span class="dot dot-lg dot-glow text-success"></span>'
        : isConnecting ? '<span class="dot dot-lg dot-pulse text-warning"></span>'
        : '<span class="dot dot-lg text-dim"></span>';
      html += '<div class="card' + (isActive ? ' is-live' : '') + '">';
      html += '<div class="flex items-center gap-3 mb-3">'+statusDot+'<strong class="flex-1">'+esc(p.name)+'</strong><span class="py-0-5 px-2 bg-base rounded-sm text-xs text-muted">'+protoIcon+' '+esc(protoLabel)+'</span></div>';
      if (p.description) html += '<p class="text-xs text-muted mb-3">'+esc(p.description)+'</p>';
      if (p.customer_id) { var _vcn = _customerNameById(p.customer_id); html += '<div class="text-xs text-dim mb-3">' + t('lbl_customer','Customer') + ': <a href="#" data-click-handler="infraSelectCustomer" data-customer-id="' + esc(p.customer_id) + '" class="text-accent no-underline">' + esc(_vcn) + '</a></div>'; }
      html += '<div class="flex gap-2 flex-wrap">';
      if (isActive) {
        html += '<button class="btn btn-danger btn-sm" data-write data-click-handler="vpnDisconnect" data-id="'+esc(p.id)+'">' + t('vpn_disconnect','Disconnect') + '</button>';
        html += '<button class="btn btn-ghost btn-sm text-danger" data-write data-click-handler="vpnForceDisconnect" title="' + t('vpn_force_disconnect_tip','Kill VPN process and clean up interface') + '">' + t('vpn_force_disconnect','Force disconnect') + '</button>';
      } else if (isConnecting) {
        html += '<button class="btn btn-warning btn-sm" data-write data-click-handler="vpnForceDisconnect">' + t('vpn_cancel','Cancel') + '</button>';
      } else {
        html += '<button class="btn btn-primary btn-sm" data-write data-click-handler="vpnConnect" data-id="'+esc(p.id)+'"'
          + (mayConnect ? '' : ' disabled aria-disabled="true" title="' + esc(protocolCapability.reason || '') + '"')
          + '>' + t('vpn_connect','Connect') + '</button>';
      }
      html += '<button class="btn btn-ghost btn-sm" data-write data-click-handler="vpnEditProfile" data-id="'+esc(p.id)+'">' + t('btn_edit','Edit') + '</button>';
      html += '<button class="btn btn-ghost btn-sm text-dim ml-auto" data-write data-click-handler="vpnDeleteProfile" data-id="'+esc(p.id)+'" title="' + t('btn_delete') + '">' + t('btn_delete') + '</button>';
      html += '</div></div>';
    });
    html += '</div>';
  }
  el.innerHTML = html;
}

async function vpnConnect(id) {
  // Check if this is an Azure profile — needs Azure AD auth
  var profileData = await apiFetch('/api/vpn/profiles/' + encodeURIComponent(id));
  if (profileData && profileData.profile && profileData.profile.protocol === 'azure') {
    vpnConnectAzure(id);
    return;
  }

  showToast(t('msg_connecting_vpn','Connecting to VPN...'),'info',3000);
  var data = await apiFetch('/api/vpn/connect/'+encodeURIComponent(id), {method:'POST'});
  if (data && data.ok) { showToast(t('vpn_connected','Connected'),'success'); } else { showToast(data?.error||t('err_connection_failed','Connection failed'),'error'); }
  vpnLoadProfiles();
}

var _azureVpnProfileId = null;

async function vpnConnectAzure(profileId) {
  _azureVpnProfileId = profileId;

  // Try silent refresh first — no login needed if refresh token is cached
  showToast(t('msg_trying_auto_login','Trying automatic login...'),'info',5000);
  var silent = await apiFetch('/api/vpn/azure/try-silent', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile_id:profileId})});

  if (silent && silent.has_token) {
    showToast(t('msg_token_renewed_connecting','Token renewed — connecting to VPN...'),'info',10000);
    var connectResult = await apiFetch('/api/vpn/azure/connect-with-token', {
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({profile_id:profileId, access_token:silent.access_token})
    });
    if (connectResult && connectResult.ok) { showToast(t('msg_azure_vpn_connected','Azure VPN connected!'),'success'); }
    else { showToast(connectResult?.error||t('err_vpn_connection_failed','VPN connection failed'),'error'); }
    _azureVpnProfileId = null;
    vpnLoadProfiles();
    return;
  }

  // Silent failed — start PKCE paste-back flow (headless compatible)
  showToast(t('msg_starting_azure_login','Starting Azure login...'),'info',3000);
  var data = await apiFetch('/api/vpn/azure/pkce-start', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile_id:profileId})});
  if (!data || !data.ok) { showToast(data?.error||t('err_azure_login_failed','Could not start Azure login'),'error'); return; }

  // Show PKCE paste-back UI
  var vpnEl = _claim('vpn-content').el;
  var html = '<div class="card p-6 mb-4" id="pkce-panel">';
  html += '<div class="text-md fw-bold mb-3">' + t('azure_vpn_innlogging') + '</div>';
  html += '<div class="text-ui text-muted mb-4">' + t('1_aapne_denne_lenken_i_en_nettleser_kan_') + '</div>';
  html += '<div class="mb-4 break-all"><a href="'+esc(data.url)+'" target="_blank" class="text-ui text-accent underline">'+esc(data.url).substring(0,80)+'...</a>';
  html += ' <button class="btn btn-ghost btn-sm ml-2" data-click-handler="pkceCopyUrl" data-url="'+esc(data.url)+'">' + t('kopier') + '</button></div>';
  html += '<div class="text-ui text-muted mb-2">' + t('2_logg_inn_med_azure_ad_nettleseren_vil_') + ' <code>localhost:2023</code> ' + t('den_vil_feile_det_er_forventet') + '</div>';
  html += '<div class="text-ui text-muted mb-3">' + t('3_kopier_hele_urlen_fra_adressefeltet_og') + '</div>';
  html += '<div class="flex gap-2 mb-3">';
  html += '<input type="text" id="pkce-callback-url" placeholder="http://localhost:2023/?code=..." class="inset flex-1 text-default font-mono text-sm">';
  html += '<button class="btn btn-primary" data-click-handler="pkceComplete" data-id="'+esc(profileId)+'">' + t('koble_til') + '</button>';
  html += '</div>';
  html += '<div id="pkce-status"></div>';
  html += '<button class="btn btn-ghost btn-sm text-dim mt-2" data-click-handler="removeElement" data-target="pkce-panel">' + t('avbryt_3') + '</button>';
  html += '</div>';

  var existingPanel = document.getElementById('pkce-panel');
  if (existingPanel) existingPanel.remove();
  if (vpnEl) vpnEl.insertAdjacentHTML('afterbegin', html);
}

async function pkceComplete(profileId) {
  var url = document.getElementById('pkce-callback-url').value.trim();
  if (!url) { showToast(t('lim_inn_urlen_fra_nettleseren'),'error'); return; }

  var statusEl = document.getElementById('pkce-status');
  if (statusEl) statusEl.innerHTML = '<div class="loader align-middle mr-2"></div> ' + t('inf_fetching_token','Henter token ...') + '';

  var result = await apiFetch('/api/vpn/azure/pkce-complete', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({callback_url:url})
  });

  if (result && result.ok && result.access_token) {
    if (statusEl) statusEl.innerHTML = '<span class="text-success fw-semibold">' + t('autentisert_kobler_til_vpn') + '</span>';
    var connectResult = await apiFetch('/api/vpn/azure/connect-with-token', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({profile_id:profileId, access_token:result.access_token})
    });
    if (connectResult && connectResult.ok) {
      showToast(t('azure_vpn_tilkoblet'),'success');
    } else {
      showToast(connectResult?.error||'VPN-tilkobling feilet','error');
    }
    setTimeout(function(){ var p = document.getElementById('pkce-panel'); if(p) p.remove(); vpnLoadProfiles(); }, 2000);
  } else {
    if (statusEl) statusEl.innerHTML = '<span class="text-danger">' + esc(result?.error||'Autentisering feilet') + '</span>';
  }
}

// Device code flow only — no popup/browser auth for Azure VPN

async function vpnDisconnect(profileId) {
  var body = profileId ? JSON.stringify({profile_id: profileId}) : '{}';
  var data = await apiFetch('/api/vpn/disconnect', {method:'POST', headers:{'Content-Type':'application/json'}, body: body});
  if (data && data.ok) showToast(t('vpn_disconnected','Disconnected'),'success');
  else showToast(data && data.error ? data.error : t('status_error'),'error');
  vpnLoadProfiles();
  _checkVpnHeaderBadge();
}

async function vpnForceDisconnect() {
  showToast(t('vpn_force_disconnecting','Force disconnecting...'), 'warning', 2000);
  var data = await apiFetch('/api/vpn/force-disconnect', {method:'POST'});
  if (data && data.ok) showToast(t('vpn_disconnected','Disconnected'),'success');
  else {
    // Fallback — try normal disconnect
    await apiFetch('/api/vpn/disconnect', {method:'POST'});
    showToast(t('vpn_disconnected','Disconnected'),'success');
  }
  vpnLoadProfiles();
  _checkVpnHeaderBadge();
}

async function vpnDeleteProfile(id) {
  if (!await showConfirm(t('dlg_confirm_delete_vpn_profile'))) return;
  await apiFetch('/api/vpn/profiles/'+encodeURIComponent(id), {method:'DELETE'});
  vpnLoadProfiles();
}

export function vpnShowCreate() {
  var el = _claim('vpn-content').el;
  el.innerHTML = '<div class="max-w-md">'
    + '<h3 class="text-md fw-semibold mb-3">' + t('hdr_new_vpn_profile','New VPN profile') + '</h3>'
    + '<input id="vpn-create-name" type="text" placeholder="' + t('placeholder_profile_name','Profile name') + '" class="field-input mb-2">'
    + '<select id="vpn-create-protocol" data-change-handler="vpnCreateProtocolChanged" class="field-input mb-2">'
    + '<option value="">' + t('placeholder_select_protocol','Select protocol...') + '</option>'
    + '<option value="fortigate_ipsec">FortiGate IPsec (IKEv2)</option>'
    + '<option value="wireguard">WireGuard</option>'
    + '<option value="openvpn">OpenVPN</option>'
    + '<option value="azure">Azure P2S VPN</option>'
    + '</select>'
    + '<label class="field-label">' + t('lbl_customer','Customer') + '</label>'
    + '<select id="vpn-create-customer" class="field-input mb-3"><option value="">-- ' + t('lbl_no_customer','No customer') + ' --</option></select>'
    + '<div id="vpn-create-fields"></div>'
    + '<div class="flex gap-2 mt-4">'
    + '<button class="btn btn-primary" data-write data-click-handler="vpnDoCreate">' + t('btn_create','Create') + '</button>'
    + '<button class="btn btn-ghost" data-click-handler="vpnLoadProfiles">' + t('btn_cancel','Cancel') + '</button>'
    + '</div></div>';
  _populateCustomerSelect('vpn-create-customer');
}

function vpnCreateProtocolChanged() {
  var protocol = document.getElementById('vpn-create-protocol').value;
  var el = document.getElementById('vpn-create-fields');
  var input = function(id, placeholder, type) {
    type = type || 'text';
    return '<input id="vpn-c-'+esc(id)+'" type="'+esc(type)+'" placeholder="'+esc(placeholder)+'" class="field-input mb-2">';
  };
  var label = function(text) { return '<label class="text-sm fw-semibold text-muted block mb-1 mt-2">'+esc(text)+'</label>'; };

  if (protocol === 'fortigate_ipsec') {
    el.innerHTML = label('FortiGate Gateway')
      + input('fg-host', t('inf_ph_vpn_host','Hostname / IP (f.eks. vpn.kunde.no)'))
      + label(t('inf_username_eap','Brukernavn (EAP)'))
      + input('fg-user', t('inf_vpn_user','VPN-brukernavn'))
      + label(t('inf_password','Passord'))
      + input('fg-pass', t('inf_vpn_pass','VPN-passord'), 'password')
      + label('Pre-Shared Key (PSK)')
      + input('fg-psk', 'IKE PSK', 'password')
      + label(t('lbl_split_tunnel_routes','Split-tunnel routes (comma-separated, optional)'))
      + input('fg-routes', 'f.eks. 10.0.0.0/8, 172.16.0.0/12')
      + label(t('lbl_dns_servers_optional','DNS servers (optional)'))
      + input('fg-dns', 'f.eks. 10.0.0.1, 10.0.0.2');
  } else if (protocol === 'wireguard') {
    el.innerHTML = '<p class="text-muted text-ui">' + t('msg_wireguard_recommend_import','For WireGuard we recommend using <strong>' + t('import_file') + '</strong> ' + t('with_a_conf_file') + '<br>Or fill in manually:') + '</p>'
      + label(t('lbl_private_key','Private key'))
      + input('wg-privkey', t('placeholder_base64_private_key','Base64-encoded private key'), 'password')
      + label(t('lbl_addresses_comma','Addresses (comma-separated)'))
      + input('wg-addr', 'f.eks. 10.0.0.2/32')
      + label('DNS')
      + input('wg-dns', 'f.eks. 1.1.1.1')
      + label('Peer Public Key')
      + input('wg-peer-pub', 'Base64-kodet peer public key')
      + label('Peer Endpoint')
      + input('wg-peer-ep', 'f.eks. vpn.server.no:51820')
      + label('Allowed IPs')
      + input('wg-peer-ips', 'f.eks. 0.0.0.0/0');
  } else if (protocol === 'openvpn') {
    el.innerHTML = '<p class="text-muted text-ui">' + t('msg_openvpn_recommend_import','For OpenVPN we recommend using <strong>' + t('import_file') + '</strong> ' + t('with_an_ovpn_file') + '<br>Or enter connection details:') + '</p>'
      + label(t('lbl_username_optional','Username (optional)'))
      + input('ovpn-user', t('inf_vpn_user','VPN-brukernavn'))
      + label(t('lbl_password_optional','Password (optional)'))
      + input('ovpn-pass', t('inf_vpn_pass','VPN-passord'), 'password')
      + label(t('lbl_config_paste_ovpn','Configuration (paste .ovpn content)'))
      + '<textarea id="vpn-c-ovpn-conf" placeholder="client\nremote vpn.server.no 1194\n..." class="field-input textarea-md mb-2 font-mono"></textarea>';
  } else if (protocol === 'azure') {
    el.innerHTML = '<p class="text-muted text-ui">' + t('msg_azure_recommend_import','For Azure P2S we recommend using <strong>' + t('import_file') + '</strong> with VPN client XML from the Azure portal.') + '</p>'
      + label('Gateway FQDN')
      + input('az-gw', 'azuregateway-xxx.vpn.azure.com')
      + label('Tenant ID')
      + input('az-tenant', 'Entra ID tenant UUID')
      + label(t('lbl_client_id_optional','Client ID (optional)'))
      + input('az-client', t('lbl_default_azure_vpn_client','Default: Azure VPN client'));
  } else {
    el.innerHTML = '';
  }
}

async function vpnDoCreate() {
  var name = document.getElementById('vpn-create-name').value.trim();
  var protocol = document.getElementById('vpn-create-protocol').value;
  if (!name) { showToast(t('err_profile_name_required','Give the profile a name'),'error'); return; }
  if (!protocol) { showToast(t('err_protocol_required','Select a protocol'),'error'); return; }

  var config = {};
  var v = function(id) { var e = document.getElementById('vpn-c-'+id); return e ? e.value.trim() : ''; };

  if (protocol === 'fortigate_ipsec') {
    if (!v('fg-host') || !v('fg-user')) { showToast(t('err_host_user_required','Host and username are required'),'error'); return; }
    config = {
      host: v('fg-host'), username: v('fg-user'), password: v('fg-pass'), psk: v('fg-psk'),
      routes: v('fg-routes') ? v('fg-routes').split(',').map(function(s){return s.trim();}) : [],
      dns_servers: v('fg-dns') ? v('fg-dns').split(',').map(function(s){return s.trim();}) : [],
    };
  } else if (protocol === 'wireguard') {
    if (!v('wg-privkey') || !v('wg-peer-pub')) { showToast(t('err_wg_keys_required','Private key and peer public key are required'),'error'); return; }
    config = {
      private_key: v('wg-privkey'),
      addresses: v('wg-addr') ? v('wg-addr').split(',').map(function(s){return s.trim();}) : [],
      dns: v('wg-dns') ? v('wg-dns').split(',').map(function(s){return s.trim();}) : [],
      peers: [{public_key: v('wg-peer-pub'), endpoint: v('wg-peer-ep'), allowed_ips: v('wg-peer-ips') ? v('wg-peer-ips').split(',').map(function(s){return s.trim();}) : ['0.0.0.0/0']}],
    };
  } else if (protocol === 'openvpn') {
    var conf = document.getElementById('vpn-c-ovpn-conf');
    config = {config_content: conf ? conf.value : '', username: v('ovpn-user'), password: v('ovpn-pass')};
  } else if (protocol === 'azure') {
    config = {gateway_fqdn: v('az-gw'), tenant_id: v('az-tenant'), client_id: v('az-client') || '41b23e61-6c1e-4545-b367-cd054e0ed4b4'};
  }

  var vpnCustSel = document.getElementById('vpn-create-customer');
  var vpnCustId = vpnCustSel ? vpnCustSel.value : '';
  var createBody = {name:name, protocol:protocol, config:config};
  if (vpnCustId) createBody.customer_id = vpnCustId;
  var data = await apiFetch('/api/vpn/profiles', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(createBody)});
  if (data && data.ok) { showToast(t('msg_vpn_profile_created','VPN profile created'),'success'); vpnLoadProfiles(); }
}

async function vpnEditProfile(profileId) {
  var data = await apiFetch('/api/vpn/profiles/' + encodeURIComponent(profileId));
  if (!data || !data.profile) return;
  var p = data.profile;
  var config = typeof p.config === 'string' ? JSON.parse(p.config) : p.config;

  var el = _claim('vpn-content').el;
  var html = '<div class="max-w-md">'
    + '<h3 class="text-md fw-semibold mb-4">' + t('rediger_vpn_profil') + '</h3>'
    + '<label class="field-label">' + t('navn_2') + '</label>'
    + '<input id="vpn-edit-name" type="text" value="'+esc(p.name)+'" class="field-input mb-2">'
    + '<label class="field-label">' + t('beskrivelse') + '</label>'
    + '<input id="vpn-edit-desc" type="text" value="'+esc(p.description||'')+'" class="field-input mb-2">'
    + '<div class="text-sm text-muted mb-2">' + t('protokoll') + ' <strong>'+esc(p.protocol)+'</strong></div>';

  // Protocol-specific fields
  if (p.protocol === 'fortigate_ipsec') {
    html += '<label class="field-label">' + t('host_2') + '</label>'
      + '<input id="vpn-edit-host" type="text" value="'+esc(config.host||'')+'" class="field-input mb-2">'
      + '<label class="field-label">' + t('lbl_username','Username') + '</label>'
      + '<input id="vpn-edit-user" type="text" value="'+esc(config.username||'')+'" class="field-input mb-2">'
      + '<label class="field-label">' + t('lbl_password_leave_blank','Password (leave blank to keep)') + '</label>'
      + '<input id="vpn-edit-pass" type="password" placeholder="' + t('placeholder_unchanged','Unchanged') + '" class="field-input mb-2">'
      + '<label class="field-label">' + t('lbl_psk_leave_blank','PSK (leave blank to keep)') + '</label>'
      + '<input id="vpn-edit-psk" type="password" placeholder="' + t('placeholder_unchanged','Unchanged') + '" class="field-input mb-2">'
      + '<label class="field-label">' + t('lbl_split_tunnel_routes_short','Split-tunnel routes') + '</label>'
      + '<input id="vpn-edit-routes" type="text" value="'+esc((config.routes||[]).join(', '))+'" class="field-input mb-2">'
      + '<label class="field-label">' + t('lbl_dns_servers','DNS servers') + '</label>'
      + '<input id="vpn-edit-dns" type="text" value="'+esc((config.dns_servers||[]).join(', '))+'" class="field-input mb-2">';
  }

  html += '<label class="text-sm fw-semibold text-muted block mb-1 mt-2">' + t('lbl_customer','Customer') + '</label>'
    + '<select id="vpn-edit-customer" class="field-input mb-2"><option value="">-- ' + t('lbl_no_customer','No customer') + ' --</option></select>';

  html += '<div class="flex gap-2 mt-4">'
    + '<button class="btn btn-primary" data-write data-click-handler="vpnDoEdit" data-id="'+esc(profileId)+'" data-protocol="'+esc(p.protocol)+'">' + t('lagre_3') + '</button>'
    + '<button class="btn btn-ghost" data-click-handler="vpnLoadProfiles">' + t('avbryt_3') + '</button>'
    + '</div></div>';
  el.innerHTML = html;
  _populateCustomerSelect('vpn-edit-customer', p.customer_id);
}

async function vpnDoEdit(profileId, protocol) {
  var body = {
    name: document.getElementById('vpn-edit-name').value.trim(),
    description: document.getElementById('vpn-edit-desc').value.trim(),
    customer_id: document.getElementById('vpn-edit-customer').value || null,
  };

  if (protocol === 'fortigate_ipsec') {
    var config = {
      host: document.getElementById('vpn-edit-host').value.trim(),
      username: document.getElementById('vpn-edit-user').value.trim(),
      routes: document.getElementById('vpn-edit-routes').value.split(',').map(function(s){return s.trim();}).filter(Boolean),
      dns_servers: document.getElementById('vpn-edit-dns').value.split(',').map(function(s){return s.trim();}).filter(Boolean),
    };
    var pass = document.getElementById('vpn-edit-pass').value;
    var psk = document.getElementById('vpn-edit-psk').value;
    if (pass) config.password = pass;
    if (psk) config.psk = psk;
    body.config = config;
  }

  var data = await apiFetch('/api/vpn/profiles/' + encodeURIComponent(profileId), {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if (data && data.ok) { showToast(t('msg_profile_updated','Profile updated'),'success'); vpnLoadProfiles(); }
}

export function vpnShowImport() {
  var el = _claim('vpn-content').el;
  el.innerHTML = '<div class="max-w-md">'
    + '<h3 class="text-md fw-semibold mb-3">' + t('hdr_import_vpn_profile','Import VPN profile') + '</h3>'
    + '<input id="vpn-import-name" type="text" placeholder="' + t('placeholder_profile_name','Profile name') + '" class="field-input mb-2">'
    + '<div id="vpn-drop-zone" class="drop-zone mb-3" data-click-handler="vpnOpenFilePicker" data-dragover-handler="vpnDragOver" data-dragleave-handler="vpnDragLeave" data-drop-handler="vpnDropFiles">'
    + '<div class="text-xl mb-2"></div>'
    + '<div class="text-muted text-ui">' + t('msg_drag_drop_vpn','Drag and drop a') + ' <strong>.conf</strong>, <strong>.ovpn</strong>, ' + t('lbl_or','or') + ' <strong>.xml</strong> ' + t('msg_file_here','file here') + '</div>'
    + '<div class="text-dim text-sm mt-1">' + t('msg_azure_vpn_select_both','Azure VPN: select <strong>both</strong> XML files (azurevpnconfig.xml + VpnSettings.xml)') + '</div>'
    + '<div class="text-dim text-sm">' + t('msg_or_click_to_select','or click to select file(s)') + '</div>'
    + '</div>'
    + '<input id="vpn-file-input" type="file" accept=".conf,.ovpn,.xml,.toml" multiple style="display:none;" data-change-handler="vpnHandleFiles">'
    + '<div id="vpn-file-info" class="inset mb-3 text-sm" style="display:none;">'
    + '<div class="flex justify-between items-center"><span id="vpn-file-name" class="fw-semibold"></span><button class="btn btn-ghost btn-sm text-danger" data-click-handler="vpnClearFile">' + t('btn_remove','Remove') + '</button></div>'
    + '<div id="vpn-file-type" class="text-muted mt-1"></div>'
    + '</div>'
    + '<input id="vpn-import-content" type="hidden">'
    + '<button class="btn btn-primary" data-write data-click-handler="vpnDoImport" id="vpn-import-btn" disabled>' + t('btn_import','Import') + '</button>'
    + '</div>';
}

var _vpnImportFiles = {};

function vpnHandleFiles(files) {
  if (!files || !files.length) return;
  _vpnImportFiles = {};
  var pending = files.length;

  for (var i = 0; i < files.length; i++) {
    (function(file) {
      var reader = new FileReader();
      reader.onload = function(e) {
        var content = e.target.result;
        // Detect which file this is
        if (content.indexOf('<AzVpnProfile>') !== -1 || content.indexOf('<audience>') !== -1 || content.indexOf('<serversecret>') !== -1) {
          _vpnImportFiles.azure_xml = content;
          _vpnImportFiles.azure_xml_name = file.name;
        } else if (content.indexOf('<VpnSettings>') !== -1 || content.indexOf('<VpnServer>') !== -1 || content.indexOf('<CustomDnsServers>') !== -1) {
          _vpnImportFiles.vpn_settings_xml = content;
          _vpnImportFiles.vpn_settings_name = file.name;
        } else if (file.name.endsWith('.conf') || content.indexOf('[Interface]') !== -1) {
          _vpnImportFiles.main = content;
          _vpnImportFiles.type = 'wireguard';
        } else if (file.name.endsWith('.ovpn') || content.indexOf('remote ') !== -1) {
          _vpnImportFiles.main = content;
          _vpnImportFiles.type = 'openvpn';
        } else {
          // Unknown XML — could be either
          _vpnImportFiles.main = content;
          _vpnImportFiles.type = 'auto';
        }

        pending--;
        if (pending === 0) vpnShowFileInfo(files);
      };
      reader.readAsText(file);
    })(files[i]);
  }
}

function vpnShowFileInfo(files) {
  document.getElementById('vpn-file-info').style.display = 'block';
  document.getElementById('vpn-drop-zone').style.display = 'none';

  var names = [];
  for (var i = 0; i < files.length; i++) names.push(files[i].name);
  document.getElementById('vpn-file-name').textContent = names.join(' + ');

  var type = t('lbl_unknown','Unknown');
  if (_vpnImportFiles.azure_xml) {
    type = 'Azure VPN' + (_vpnImportFiles.vpn_settings_xml ? ' (2 ' + t('lbl_files','files') + ' · ' + t('lbl_complete','complete') + ')' : ' (' + t('msg_missing_vpnsettings','missing VpnSettings.xml!') + ')');
  } else if (_vpnImportFiles.type === 'wireguard') type = 'WireGuard (.conf)';
  else if (_vpnImportFiles.type === 'openvpn') type = 'OpenVPN (.ovpn)';

  document.getElementById('vpn-file-type').textContent = t('lbl_type','Type') + ': ' + type;
  document.getElementById('vpn-import-btn').disabled = false;

  // Combine content for import
  if (_vpnImportFiles.azure_xml) {
    // Merge both XMLs with separator
    var combined = _vpnImportFiles.azure_xml;
    if (_vpnImportFiles.vpn_settings_xml) {
      combined += '\n<!-- VPN_SETTINGS_SEPARATOR -->\n' + /* safe-html: XML for the import API, never rendered */ _vpnImportFiles.vpn_settings_xml;
    }
    document.getElementById('vpn-import-content').value = combined;
  } else {
    document.getElementById('vpn-import-content').value = _vpnImportFiles.main || '';
  }

  // Auto-fill name
  var nameInput = document.getElementById('vpn-import-name');
  if (!nameInput.value) {
    nameInput.value = (files[0].name || '').replace(/\.(conf|ovpn|xml|toml)$/i, '').replace(/azurevpnconfig/i, 'Azure VPN');
  }
}

function vpnClearFile() {
  document.getElementById('vpn-import-content').value = '';
  document.getElementById('vpn-file-info').style.display = 'none';
  document.getElementById('vpn-drop-zone').style.display = 'block';
  document.getElementById('vpn-import-btn').disabled = true;
  document.getElementById('vpn-file-input').value = '';
}

async function vpnDoImport() {
  var name = document.getElementById('vpn-import-name').value.trim();
  var content = document.getElementById('vpn-import-content').value;
  if (!name || !content) { showToast(t('err_select_file_and_name','Select a file and name the profile'),'error'); return; }
  var data = await apiFetch('/api/vpn/profiles/import', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,file_content:content})});
  if (data && data.ok) { showToast(t('msg_profile_imported','Profile imported:') + ' '+data.profile.protocol,'success'); vpnLoadProfiles(); }
}

// ═══════════════════════════════════════════════════════════════════
// LIVE DASHBOARD
// ═══════════════════════════════════════════════════════════════════

var _liveWs = null;

export async function livePollNow() {
  var statusEl = document.getElementById('live-status') || document.getElementById('fg-live-status');
  if (statusEl) statusEl.textContent = t('msg_updating','Updating...');
  var custId = await toolCustomerId();
  if (!custId) { showToast(t('msg_select_customer_first','Select a customer first'),'error'); return; }
  var data = await apiFetch('/api/dashboard/poll/'+encodeURIComponent(custId), {method:'POST'});
  if (data) liveRenderDevices(data.devices || []);
  if (statusEl) statusEl.textContent = t('msg_last_updated','Last updated') + ': ' + new Date().toLocaleTimeString();
}

async function fgBackupAll() {
  showToast(t('msg_backing_up_all','Kjører backup på alle FortiGates...'), 'info', 3000);
  var data = await apiFetch('/api/fortigate/backup-all', {method:'POST'});
  if (data) {
    showToast(data.success + '/' + data.total + ' ' + t('msg_backup_complete') + (data.failed ? ', ' + data.failed + ' ' + t('msg_backup_failed') : ''), data.failed ? 'warning' : 'success', 5000);
  } else {
    showToast(t('status_error'), 'error');
  }
}

export async function fgPollAll() {
  var statusEl = document.getElementById('fg-live-status');
  if (statusEl) statusEl.textContent = t('msg_updating','Updating...');
  // Poll all customers that have FortiGate and merge live data into the FortiGate view
  var data = await apiFetch('/api/fortigate/all');
  if (data && data.fortigates) {
    // Trigger live poll for each FortiGate customer
    var pollPromises = [];
    var seenCids = {};
    for (var i = 0; i < data.fortigates.length; i++) {
      var cid = data.fortigates[i].customer_id;
      if (cid && !seenCids[cid]) {
        seenCids[cid] = true;
        pollPromises.push(apiFetch('/api/dashboard/poll/'+encodeURIComponent(cid), {method:'POST'}).catch(function(){return null;}));
      }
    }
    await Promise.all(pollPromises);
    // Reload the FortiGate view with fresh data — but only if no detail panel is open
    if (!document.querySelector('.fg-detail-panel')) {
      dashLoadFortiGates();
    }
  }
  if (statusEl) statusEl.textContent = t('msg_last_updated','Sist oppdatert') + ': ' + new Date().toLocaleTimeString();
}

export function liveSetInterval(seconds) {
  if (_liveWs && _liveWs.readyState === WebSocket.OPEN) {
    _liveWs.send(JSON.stringify({type:'set_interval',interval:parseInt(seconds)}));
  }
}

var _liveDevices = [];

export function liveRenderDevices(devices) {
  _liveDevices = devices;
  var el = document.getElementById('dash-fg-content');
  if (!devices.length) { el.innerHTML = '<div class="text-muted text-center p-12 col-span-full">' + t('ingen_enheter_funnet') + '</div>'; return; }
  var html = '';
  devices.forEach(function(d, idx) {
    var color = d.status === 'online' ? 'var(--green)' : d.status === 'error' ? 'var(--red)' : 'var(--text-dim)';
    var vendorIcon = d.vendor === 'fortigate' ? '' : '';
    html += '<div class="hover-bg bg-card border rounded-lg p-4 edge-tone ' + toneVar(color) + ' cursor-pointer" data-click-handler="liveShowDeviceDetail" data-index="'+idx+'">';
    html += '<div class="flex justify-between items-center mb-2">';
    html += '<strong>'+vendorIcon+' '+esc(d.name)+'</strong>';
    html += '<span class="dot ' + toneClass(color) + '"></span>';
    html += '</div>';
    html += '<div class="text-sm text-muted grid grid-cols-2 gap-1">';
    html += '<span>' + t('modell') + ' <strong class="text-default">'+esc(d.model||'-')+'</strong></span>';
    html += '<span>Firmware: '+esc(d.firmware||'-')+'</span>';
    if (d.wan_ip) html += '<span>' + t('wan') + ' <strong class="text-default">'+esc(d.wan_ip)+'</strong></span>';
    if (d.uptime) html += '<span>Uptime: '+esc(d.uptime)+'</span>';
    if (d.cpu_pct !== undefined && d.cpu_pct !== null) {
      var cpuColor = d.cpu_pct > 80 ? 'var(--red)' : d.cpu_pct > 50 ? 'var(--orange)' : 'var(--green)';
      html += '<span>' + t('cpu') + ' <span class="' + toneClass(cpuColor) + ' fw-semibold">'+Number(d.cpu_pct)+'%</span></span>';
    }
    if (d.mem_pct !== undefined && d.mem_pct !== null) {
      var memColor = d.mem_pct > 80 ? 'var(--red)' : d.mem_pct > 50 ? 'var(--orange)' : 'var(--green)';
      html += '<span>' + t('minne') + ' <span class="' + toneClass(memColor) + ' fw-semibold">'+Number(d.mem_pct)+'%</span></span>';
    }
    if (d.sessions !== undefined && d.sessions !== null) html += '<span>Sesjoner: '+Number(d.sessions).toLocaleString()+'</span>';
    if (d.vpn_tunnels !== undefined && d.vpn_tunnels !== null) html += '<span>VPN: '+Number(d.vpn_tunnels)+' ' + t('inf_tunnels','tunnel(er)') + '</span>';
    if (d.ha_mode && d.ha_mode !== 'Standalone') html += '<span>HA: '+esc(d.ha_mode)+'</span>';
    if (d.clients !== undefined && d.clients !== null) html += '<span>Klienter: '+Number(d.clients)+'</span>';
    html += '</div>';
    if (d.error) html += '<div class="text-danger text-xs mt-2">'+esc(d.error)+'</div>';
    if (d.last_poll) html += '<div class="text-2xs text-dim mt-2">' + t('msg_last_polled','Last polled') + ': '+new Date(d.last_poll).toLocaleTimeString()+'</div>';
    html += '</div>';
  });
  el.innerHTML = html;
}

function liveShowDeviceDetail(idx) {
  var d = _liveDevices[idx];
  if (!d) return;
  var el = document.getElementById('dash-fg-content');
  var color = d.status === 'online' ? 'var(--green)' : 'var(--red)';
  var vendorIcon = d.vendor === 'fortigate' ? '' : '';

  var html = '<div class="col-span-full max-w-md">';
  html += '<div class="flex items-center gap-3 mb-4">';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="livePollNow">' + t('tilbake') + '</button>';
  html += '<h3 class="text-md fw-bold m-0">'+vendorIcon+' '+esc(d.name)+'</h3>';
  html += '<span class="dot dot-lg ' + toneClass(color) + '"></span>';
  html += '</div>';

  // KPI cards
  var cards = [];
  if (d.cpu_pct !== undefined && d.cpu_pct !== null) cards.push({label:'CPU', value:Number(d.cpu_pct)+'%', color: d.cpu_pct>80?'var(--red)':d.cpu_pct>50?'var(--orange)':'var(--green)'});
  if (d.mem_pct !== undefined && d.mem_pct !== null) cards.push({label:'Minne', value:Number(d.mem_pct)+'%', color: d.mem_pct>80?'var(--red)':d.mem_pct>50?'var(--orange)':'var(--green)'});
  if (d.sessions !== undefined && d.sessions !== null) cards.push({label:'Sesjoner', value:Number(d.sessions).toLocaleString(), color:'var(--blue)'});
  if (d.vpn_tunnels !== undefined && d.vpn_tunnels !== null) cards.push({label:'VPN-tunneler', value:Number(d.vpn_tunnels), color:'var(--purple)'});
  if (d.clients !== undefined && d.clients !== null) cards.push({label:'Klienter', value:Number(d.clients), color:'var(--green)'});

  if (cards.length) {
    html += '<div class="kpi-row mb-4">';
    cards.forEach(function(c) {
      html += '<div class="card kpi-card top-tone ' + toneVar(c.color) + '">';
      html += '<div class="text-xl fw-bold">'+c.value+'</div>';
      html += '<div class="text-xs text-muted">'+c.label+'</div>';
      html += '</div>';
    });
    html += '</div>';
  }

  // Detail table
  html += '<div class="card p-4">';
  html += '<table class="w-full text-ui">';
  var rows = [
    ['Status', '<span class="' + toneClass(color) + ' fw-semibold">'+(d.status==='online'?'ONLINE':'OFFLINE')+'</span>'],
    ['Modell', esc(d.model || '-')],
    ['Firmware', esc(d.firmware || '-')],
    ['Serienummer', esc(d.serial || '-')],
    ['WAN IP', esc(d.wan_ip || '-')],
    ['Uptime', esc(d.uptime || '-')],
  ];
  if (d.ha_mode) rows.push(['HA-modus', esc(d.ha_mode)]);
  if (d.extra) {
    if (d.extra.policy_count) rows.push(['Brannmurregler', Number(d.extra.policy_count)]);
    if (d.extra.host) rows.push(['API-host', esc(d.extra.host + ':' + (d.extra.port||443))]);
  }
  if (d.last_poll) rows.push([t('msg_last_polled','Last polled'), new Date(d.last_poll).toLocaleString('no-NO')]);

  rows.forEach(function(r) {
    html += '<tr class="border-b"><td class="kv-key">'+r[0]+'</td><td class="p-2">'+r[1]+'</td></tr>';
  });
  html += '</table></div>';

  // Extra data sections for FortiGate
  if (d.vendor === 'fortigate' && d.extra) {
    var ex = d.extra;

    // Interfaces
    if (ex.interfaces && ex.interfaces.length) {
      html += '<div class="card p-4 mt-3">';
      html += '<div class="subhead">Grensesnitt ('+ex.interfaces.length+')</div>';
      html += '<table class="data-table"><thead><tr><th>' + t('navn_2') + '</th><th>IP</th><th>' + t('link') + '</th><th>' + t('hastighet') + '</th></tr></thead><tbody>';
      ex.interfaces.forEach(function(i) {
        if (!i.ip || i.ip === '0.0.0.0') return;
        html += '<tr><td class="fw-semibold">'+esc(i.name)+'</td><td class="font-mono text-xs">'+esc(i.ip)+'</td><td>'+(i.link?'<span class="text-success">' + t('up') + '</span>':'<span class="text-danger">' + t('down') + '</span>')+'</td><td>'+(i.speed?esc(i.speed)+'M':'')+'</td></tr>';
      });
      html += '</tbody></table></div>';
    }

    // VPN tunnels
    if (ex.vpn_tunnels && ex.vpn_tunnels.length) {
      html += '<div class="card p-4 mt-3">';
      html += '<div class="subhead">VPN-tunneler ('+ex.vpn_tunnels.length+')</div>';
      ex.vpn_tunnels.forEach(function(v) {
        html += '<div class="flex items-center gap-2 py-1 px-0 text-sm border-b">';
        html += '<strong>'+esc(v.name)+'</strong>';
        html += '<span class="text-muted">→ '+esc(v.remote_gw)+'</span>';
        html += '</div>';
      });
      html += '</div>';
    }

    // Policies
    if (ex.policies && ex.policies.length) {
      html += '<div class="card p-4 mt-3">';
      html += '<div class="subhead">' + t('lbl_firewall_rules','Firewall rules') + ' ('+ex.policies.length+')</div>';
      html += '<table class="data-table data-table--compact"><thead><tr><th>#</th><th>' + t('lbl_name','Name') + '</th><th>' + t('lbl_source','Source') + '</th><th>' + t('lbl_destination','Destination') + '</th><th>' + t('lbl_service','Service') + '</th><th>' + t('lbl_log','Log') + '</th></tr></thead><tbody>';
      ex.policies.forEach(function(p) {
        html += '<tr>';
        html += '<td>'+esc(String(p.id))+'</td>';
        html += '<td class="fw-semibold">'+esc(p.name)+'</td>';
        html += '<td class="text-2xs">'+esc(p.src)+'</td>';
        html += '<td class="text-2xs">'+esc(p.dst)+'</td>';
        html += '<td class="text-2xs">'+esc(p.svc)+'</td>';
        html += '<td class="text-2xs">'+(p.log==='all'||p.log==='utm'?'<span class="text-success">'+esc(p.log)+'</span>':'<span class="text-danger">'+esc(p.log)+'</span>')+'</td>';
        html += '</tr>';
      });
      html += '</tbody></table></div>';
    }

    // DHCP + DNS + Admins row
    html += '<div class="grid grid-cols-3 gap-3 mt-3">';

    // DHCP
    if (ex.dhcp && ex.dhcp.length) {
      html += '<div class="card p-3"><div class="subhead">DHCP ('+ex.dhcp.length+')</div>';
      ex.dhcp.forEach(function(d2) { html += '<div class="text-xs text-muted py-0-5 px-0"><strong>'+esc(d2.interface)+'</strong>: '+esc(d2.range)+'</div>'; });
      html += '</div>';
    }

    // DNS
    if (ex.dns && ex.dns.primary) {
      html += '<div class="card p-3"><div class="subhead">DNS</div>';
      html += '<div class="text-xs text-muted">' + t('lbl_primary','Primary') + ': <strong>'+esc(ex.dns.primary)+'</strong></div>';
      if (ex.dns.secondary) html += '<div class="text-xs text-muted">' + t('lbl_secondary','Secondary') + ': '+esc(ex.dns.secondary)+'</div>';
      html += '</div>';
    }

    // Admins
    if (ex.admins && ex.admins.length) {
      html += '<div class="card p-3"><div class="subhead">Admin-kontoer ('+ex.admins.length+')</div>';
      ex.admins.forEach(function(a) {
        var warns = [];
        if (!a.two_factor) warns.push('<span class="text-warning">' + t('ingen_fa') + '</span>');
        if (!a.trusthost) warns.push('<span class="text-warning">' + t('ingen_trusthost') + '</span>');
        html += '<div class="text-xs py-0-5 px-0"><strong>'+esc(a.name)+'</strong> ('+esc(a.profile)+') '+(warns.length?warns.join(', '):'<span class="text-success">OK</span>')+'</div>';
      });
      html += '</div>';
    }

    html += '</div>';
  }

  // Action buttons
  if (d.vendor === 'fortigate') {
    html += '<div class="flex gap-2 mt-3">';
    html += '<button class="btn btn-primary btn-sm" data-write data-click-handler="fgBackupConfig" data-customer-id="'+esc(d.customer_id)+'">' + t('backup_config') + '</button>';
    html += '<button class="btn btn-ghost btn-sm" data-click-handler="fgShowBackups" data-customer-id="'+esc(d.customer_id)+'">'+t('btn_backup_history','Backup-historikk')+'</button>';
    html += '<button class="btn btn-ghost btn-sm" data-click-handler="fgComplianceCheck" data-customer-id="'+esc(d.customer_id)+'">' + t('cis_sjekk') + '</button>';
    html += '</div>';
    html += '<div id="fg-backup-list-'+esc(d.customer_id)+'" class="mt-2"></div>';
  }

  html += '</div>';
  el.innerHTML = html;
}

async function fgBackupConfig(customerId) {
  showToast(t('msg_backing_up_fortigate','Backing up FortiGate config...'), 'info', 3000);
  var data = await apiFetch('/api/fortigate/backup/' + encodeURIComponent(customerId), {method:'POST'});
  if (data && data.ok) {
    showToast(t('msg_backup_completed','Backup completed:') + ' ' + (data.filename||''), 'success');
    fgShowBackups(customerId); // Refresh list
  } else {
    showToast(t('err_backup_failed','Backup failed:') + ' ' + (data&&data.error||t('lbl_unknown_error','unknown error')), 'error');
  }
}

async function fgShowBackups(customerId) {
  var el = document.getElementById('fg-backup-list-' + customerId);
  if (!el) return;
  // Toggle — if already showing, hide
  if (el.innerHTML && el.dataset.loaded) { el.innerHTML = ''; el.dataset.loaded = ''; return; }
  el.innerHTML = '<div class="loader"></div>';
  var data = await apiFetch('/api/fortigate/backups/' + encodeURIComponent(customerId));
  if (!data || !data.length) { el.innerHTML = '<div class="text-xs text-muted py-1 px-0">'+t('msg_no_backups','Ingen backuper funnet')+'</div>'; el.dataset.loaded = '1'; return; }
  var h = '<table class="data-table data-table--compact mt-1">';
  h += '<thead><tr><th>'+t('col_filename','Fil')+'</th><th class="text-center">'+t('col_size','Størrelse')+'</th><th class="text-center">'+t('col_date','Dato')+'</th><th></th></tr></thead><tbody>';
  data.forEach(function(b) {
    h += '<tr>';
    h += '<td class="font-mono text-2xs">'+esc(b.filename)+'</td>';
    h += '<td class="text-center">'+((b.size/1024).toFixed(1))+' KB</td>';
    h += '<td class="text-center">'+esc((b.modified||'').substring(0,16))+'</td>';
    h += '<td class="text-right"><button class="btn btn-ghost btn-sm" data-click-handler="fgDownloadBackup" data-customer-id="'+esc(customerId)+'" data-filename="'+esc(b.filename)+'">'+t('btn_download','Last ned')+'</button></td>';
    h += '</tr>';
  });
  h += '</tbody></table>';
  el.innerHTML = h;
  el.dataset.loaded = '1';
}

async function fgDownloadBackup(customerId, filename) {
  var data = await apiFetch('/api/fortigate/backup/' + encodeURIComponent(customerId) + '/' + encodeURIComponent(filename));
  if (!data || !data.content) { showToast(t('err_download_failed','Nedlasting feilet'), 'error'); return; }
  var blob = new Blob([data.content], {type: 'text/plain'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function fgComplianceCheck(customerId) {
  // Find or create a results area in the detail view
  var existing = document.getElementById('fg-compliance-results');
  if (!existing) {
    var container = document.querySelector('#dash-fg-content > div');
    if (container) {
      container.insertAdjacentHTML('beforeend', '<div id="fg-compliance-results" class="mt-3"></div>');
    }
  }
  var el = document.getElementById('fg-compliance-results');
  if (el) el.innerHTML = '<div class="card p-4"><div class="loader"></div> ' + t('msg_running_cis_check','Running CIS compliance check...') + '</div>';

  var data = await apiFetch('/api/fortigate/compliance/' + encodeURIComponent(customerId));
  if (!data || !el) { showToast(t('err_check_failed','Check failed'), 'error'); return; }

  var findings = data.findings || [];
  var score = Number(data.score) || 0;
  var scoreColor = score >= 80 ? 'var(--green)' : score >= 50 ? 'var(--orange)' : 'var(--red)';

  var html = '<div class="card p-4">';
  html += '<div class="flex justify-between items-center mb-3">';
  html += '<div class="text-ui fw-semibold">' + t('cis_compliance') + '</div>';
  html += '<div class="text-xl fw-bold ' + toneClass(scoreColor) + '">'+score+'%</div>';
  html += '</div>';

  // Progress bar
  html += '<div class="bar bar-lg mb-4">';
  html += '<div class="bar-fill ' + toneClass(scoreColor).replace('text-', 'is-') + '" data-bar="' + score + '"></div>';
  html += '</div>';

  if (findings.length) {
    html += '<table class="data-table">';
    html += '<thead><tr><th>' + t('kontroll') + '</th><th class="text-center">' + t('status_3') + '</th><th>' + t('detaljer') + '</th></tr></thead><tbody>';
    findings.forEach(function(f) {
      var icon = f.status === 'pass' ? '<span class="text-success">&#10003;</span>' : f.status === 'fail' ? '<span class="text-danger">&#10007;</span>' : '<span class="text-warning">!</span>';
      html += '<tr' + (f.status === 'fail' ? ' class="row-danger"' : '') + '>';
      html += '<td class="fw-semibold">'+esc(f.title)+'</td>';
      html += '<td class="text-center">'+icon+'</td>';
      html += '<td class="text-muted text-xs">'+esc(f.detail||f.description||'')+'</td>';
      html += '</tr>';
    });
    html += '</tbody></table>';
  } else {
    html += '<div class="text-muted">' + t('ingen_funn') + '</div>';
  }

  html += '</div>';
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════
// AI CONSOLE
// ═══════════════════════════════════════════════════════════════════

var _aiConversationId = null;

export function aiQuickPrompt(text) {
  document.getElementById('ai-input').value = text;
  aiSend();
}

var _aiCustomerList = [];

export async function aiLoadCustomers() {
  var data = await apiFetch('/api/customers');
  if (!data) return;
  _aiCustomerList = (data.customers || []).map(function(c) {
    return {id: c._id, name: c.CustomerName || '', domain: c.PrimaryDomain || ''};
  });
  // Populate native select
  var sel = document.getElementById('ai-customer-select');
  if (sel) {
    var html = '<option value="all">' + t('lbl_all_customers','All Customers') + '</option>';
    _aiCustomerList.forEach(function(c) {
      html += '<option value="' + esc(c.id) + '">' + esc(c.name) + (c.domain ? ' (' + esc(c.domain) + ')' : '') + '</option>';
    });
    sel.innerHTML = html;
    // Start from this tab's current customer, as the console's context.
    var current = currentCustomerId();
    if (current && _aiCustomerList.some(function(c) { return c.id === current; })) {
      sel.value = current;
      document.getElementById('ai-customer').value = current;
    }
  }
}

export function aiSelectCustomerFromDropdown(sel) {
  document.getElementById('ai-customer').value = sel.value;
}

var _aiExternalConsent = false;

function aiApproval(parent, evt) {
  var card = document.createElement('div');
  var detail = document.createElement('pre');
  detail.style.whiteSpace = 'pre-wrap';
  detail.textContent = evt.tool_name + '\n' + JSON.stringify(evt.parameters, null, 2);
  card.appendChild(detail);
  [true, false].forEach(function(approve) {
    var button = document.createElement('button');
    button.className = 'btn btn-sm';
    button.textContent = approve ? t('btn_approve','Approve action') : t('btn_reject','Reject');
    button.addEventListener('click', async function() {
      card.querySelectorAll('button').forEach(function(b) { b.disabled = true; });
      var result = await apiFetch('/api/claude/actions/' + encodeURIComponent(evt.approval_id), {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({approve:approve})
      });
      detail.textContent += '\n' + (result ? JSON.stringify(result, null, 2) : t('msg_outcome_unknown','Outcome unknown. Check the target before retrying.'));
    });
    card.appendChild(button);
  });
  parent.appendChild(card);
}

export async function aiSend() {
  var input = document.getElementById('ai-input');
  var msg = input.value.trim();
  if (!msg) return;
  if (!_aiExternalConsent) {
    if (!confirm(t('msg_ai_privacy','Messages, customer context and read tool results are sent to Anthropic. Do not include secrets. Approve external processing for this session?'))) return;
    _aiExternalConsent = true;
  }
  input.value = '';
  var msgsEl = document.getElementById('ai-messages');

  // Clear welcome screen on first message only
  var welcomeEl = msgsEl.querySelector('[data-welcome]');
  if (welcomeEl) welcomeEl.remove();

  // Unique ID for this reply
  var replyId = 'ai-reply-' + Date.now();

  // Timestamp
  var now = new Date().toLocaleTimeString('no-NO', {hour:'2-digit',minute:'2-digit'});

  // Add user message at bottom
  var userDiv = document.createElement('div');
  userDiv.style.cssText = 'margin-bottom:16px;padding:10px 12px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;border-left:3px solid var(--blue);';
  userDiv.innerHTML = '<div class="flex justify-between items-center mb-1"><span class="fw-semibold text-accent text-sm">' + t('lbl_you','You') + '</span><span class="text-2xs text-dim">'+now+'</span></div><div class="text-ui">'+esc(msg)+'</div>';
  msgsEl.appendChild(userDiv);
  msgsEl.scrollTop = msgsEl.scrollHeight;

  // Add placeholder for assistant at bottom
  var aiDiv = document.createElement('div');
  aiDiv.style.cssText = 'margin-bottom:16px;padding:10px 12px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;border-left:3px solid var(--green);';
  aiDiv.innerHTML = '<div class="flex justify-between items-center mb-1"><span class="fw-semibold text-success text-sm"><img src="/static/sybrt-mascot.png" alt="" class="avatar-xs">Sybrt</span><span id="'+replyId+'-time" class="text-2xs text-dim"></span></div><div id="'+replyId+'-text" class="pre-wrap text-ui"><span class="loader"></span></div>';
  msgsEl.appendChild(aiDiv);
  msgsEl.scrollTop = msgsEl.scrollHeight;

  // The customer the conversation is about: the one chosen above, which
  // starts as this tab's current customer. "all" is no single customer.
  var custId = document.getElementById('ai-customer').value;
  if (custId === 'all') custId = '';
  var focus = document.getElementById('ai-focus').value;
  try {
    var resp = await fetch('/api/claude/message', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({message:msg, conversation_id:_aiConversationId, customer_id:custId||'', focus:focus||'general', external_processing_consent:_aiExternalConsent})
    });
    if (!resp.ok) { try { var e = await resp.json(); document.getElementById(replyId+'-text').textContent = t('status_error','Error')+': '+e.error; } catch(_) { document.getElementById(replyId+'-text').textContent = t('err_http_error','Error: HTTP') + ' '+resp.status; } return; }
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var replyEl = document.getElementById(replyId+'-text');
    replyEl.textContent = '';
    var buf = '';
    while (true) {
      var result = await reader.read();
      if (result.done) break;
      buf += decoder.decode(result.value, {stream:true});
      var lines = buf.split('\n');
      buf = lines.pop();
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        if (!line.startsWith('data: ')) continue;
        try {
          var evt = JSON.parse(line.slice(6));
          if (evt.type === 'text') replyEl.textContent += (evt.text || evt.content || '');
          else if (evt.type === 'tool_use') replyEl.innerHTML += '<div class="text-warning text-xs my-1">'+esc(evt.tool_name||evt.tool||'?')+'</div>';
          else if (evt.type === 'approval_required') aiApproval(aiDiv, evt);
          else if (evt.type === 'conversation_id') _aiConversationId = evt.conversation_id || evt.id;
          else if (evt.type === 'done') { var ts=document.getElementById(replyId+'-time'); if(ts) ts.textContent=new Date().toLocaleTimeString('no-NO',{hour:'2-digit',minute:'2-digit'}); }
          else if (evt.type === 'error') replyEl.innerHTML += '<div class="text-danger">' + t('status_error','Error') + ': '+esc(evt.error || evt.msg || '')+'</div>';
        } catch(_){}
      }
      msgsEl.scrollTop = msgsEl.scrollHeight;
    }
  } catch(e) {
    // The reply pane is created per message as `<replyId>-text` above. There
    // has never been an 'ai-reply-text' element, so this handler threw a
    // TypeError of its own and swallowed the network error it exists to
    // report — leaving the message stuck on its loading spinner.
    var errEl = document.getElementById(replyId + '-text');
    if (errEl) errEl.textContent = t('err_network_error','Network error') + ': '+e.message;
  }
}

export function aiClearChat() {
  _aiConversationId = null;
  document.getElementById('ai-messages').innerHTML = '<div data-welcome class="empty-note"><img src="/static/sybrt-mascot.png" alt="Sybrt" class="avatar-lg"><br>' + t('msg_new_chat_started','New chat started. Type a message to begin.') + '</div>';
}

// ═══════════════════════════════════════════════════════════════════
// PROVISIONING WIZARD
// ═══════════════════════════════════════════════════════════════════

var _provisionSession = null;
var _provisionSuggested = null;

// The session is bound to the customer chosen in the bar above the wizard
// (this tab's current customer), or to none: that customer's stored device
// credentials are the only ones a deploy may use.
registerToolCustomer('provisioning', function() { if (_provisionSession) provisionStart(); });

export async function provisionStart() {
  renderToolCustomerPickers();
  var customerId = await toolCustomerId();
  var data = await apiFetch('/api/provisioning/start', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({customer_id: customerId}),
  });
  if (!data) return;
  _provisionSession = data.session_id;
  _provisionSuggested = null;
  provisionRenderStep(1);
}

function provisionRenderStep(step) {
  var el = document.getElementById('provision-content');
  var stepNames = ['',t('lbl_customer','Customer'),t('lbl_network','Network'),t('lbl_services','Services'),t('lbl_security','Security'),t('lbl_review','Review')];
  // Progress bar
  var html = '<div class="flex gap-1 mb-5">';
  for (var i = 1; i <= 5; i++) {
    html += '<div class="step-bar' + (i < step ? ' is-done' : i === step ? ' is-current' : '') + '"></div>';
  }
  html += '</div>';
  html += '<h3 class="text-md fw-semibold mb-4">' + t('lbl_step','Step') + ' '+Number(step)+': '+stepNames[step]+'</h3>';

  if (step === 1) {
    html += '<div class="max-w-md">'
      + '<label class="field-label">' + t('lbl_customer_name') + ' *</label>'
      + '<input id="prov-name" type="text" class="field-input mb-2" placeholder="' + t('placeholder_customer_name','Customer name') + '">'
      + '<label class="field-label">' + t('placeholder_location','Location') + '</label>'
      + '<input id="prov-location" type="text" class="field-input mb-2" placeholder="' + t('placeholder_location','Location') + '">'
      + '<label class="field-label">' + t('lbl_device_type','Device type') + '</label>'
      + '<select id="prov-device" class="field-input mb-2"><option value="fortigate">FortiGate</option><option value="unifi">UniFi</option><option value="both">' + t('lbl_both','Both') + '</option></select>'
      + '<label class="field-label">' + t('placeholder_target_host','Target host (IP)') + '</label>'
      + '<input id="prov-target" type="text" class="field-input mb-3" placeholder="192.168.1.99">'
      + '<button class="btn btn-ghost btn-sm" data-click-handler="provisionAutoFill">' + t('btn_fill_from_customer','Fyll fra aktiv kunde') + '</button>'
      + '</div>';
    setTimeout(provisionAutoFill, 50);
  } else if (step === 2) {
    html += '<div class="max-w-md">'
      + '<label class="field-label">WAN</label>'
      + '<select id="prov-wan" class="field-input mb-2"><option value="dhcp">DHCP</option><option value="static">' + t('lbl_static','Static') + '</option><option value="pppoe">PPPoE</option></select>'
      + '<div class="flex gap-2 items-end mb-2">'
      + '<div class="flex-1"><label class="field-label">' + t('lan_subnet') + '</label><input id="prov-subnet" type="text" class="field-input" placeholder="10.x.0.0/24" value="' + esc(_provisionSuggested ? _provisionSuggested.lan_subnet : '192.168.1.0/24') + '"></div>'
      + '<button class="btn btn-ghost btn-sm nowrap mb-0-5" data-click-handler="provisionSuggestSubnets">' + t('btn_suggest_subnets','Auto-generer subnets') + '</button>'
      + '</div>'
      + '<label class="field-label">VLANs</label>'
      + '<div id="prov-vlan-table"></div>'
      + '<button class="btn btn-ghost btn-sm mt-2" data-click-handler="provisionAddVlan">+ ' + t('btn_add_vlan','Legg til VLAN') + '</button>'
      + '</div>';
    setTimeout(function() { provisionRenderVlans(_provisionSuggested ? _provisionSuggested.vlans : []); }, 20);
  } else if (step === 3) {
    html += '<div class="max-w-md">'
      + '<input id="prov-dns" type="text" placeholder="DNS-servere (komma)" value="1.1.1.1, 1.0.0.1" class="field-input mb-2">'
      + '<input id="prov-ntp" type="text" placeholder="NTP-servere" value="0.pool.ntp.org" class="field-input mb-2">'
      + '<input id="prov-syslog" type="text" placeholder="' + t('placeholder_syslog_server','Syslog server (optional)') + '" class="field-input mb-2">'
      + '</div>';
  } else if (step === 4) {
    html += '<div class="max-w-md">'
      + '<input id="prov-admin-pw" type="password" placeholder="' + t('placeholder_admin_password','Admin password') + '" class="field-input mb-2">'
      + '<label class="flex items-center gap-2 text-ui mb-2"><input type="checkbox" id="prov-webfilter" checked> ' + t('web_filter') + '</label>'
      + '<label class="flex items-center gap-2 text-ui mb-2"><input type="checkbox" id="prov-ids" checked> IDS/IPS</label>'
      + '</div>';
  } else if (step === 5) {
    html += '<div id="prov-summary" class="text-muted">' + t('msg_loading_summary','Loading summary...') + '</div>'
      + '<div class="mt-4 flex gap-2 flex-wrap">'
      + '<button class="btn btn-primary" data-write data-click-handler="provisionDeploy" data-method="rest">' + t('btn_deploy_rest','Deploy via REST API') + '</button>'
      + '<button class="btn btn-default" data-write data-click-handler="provisionGenerate">' + t('btn_generate_config','Generate config') + '</button>'
      + '<button class="btn btn-ghost" data-write data-click-handler="provisionGenerate" data-ai="1">' + t('btn_generate_with_ai','Generate with AI') + '</button>'
      + '</div>'
      + '<div id="prov-deploy-result" class="mt-4" style="display:none;"></div>'
      + '<pre id="prov-output" class="inset mt-4 text-sm font-mono overflow-x-auto pre-wrap max-h-lg overflow-y-auto" style="display:none;"></pre>';
    setTimeout(provisionLoadSummary, 100);
  }

  // Navigation buttons
  html += '<div class="flex gap-2 mt-5">';
  if (step > 1) html += '<button class="btn btn-ghost" data-click-handler="provisionPrevStep" data-step="'+Number(step)+'">' + t('tilbake') + '</button>';
  if (step < 5) html += '<button class="btn btn-primary" data-click-handler="provisionNextStep" data-step="'+Number(step)+'">' + t('neste_2') + '</button>';
  html += '</div>';
  el.innerHTML = html;
}

async function provisionNextStep(current) {
  var data = {};
  if (current === 1) {
    data = {name:document.getElementById('prov-name').value, location:document.getElementById('prov-location').value, device_type:document.getElementById('prov-device').value, target_host:document.getElementById('prov-target').value};
  } else if (current === 2) {
    var vlans = provisionCollectVlans();
    data = {wan_type:document.getElementById('prov-wan').value, lan_subnet:document.getElementById('prov-subnet').value, vlans:vlans};
  } else if (current === 3) {
    data = {dns_servers:document.getElementById('prov-dns').value.split(',').map(function(s){return s.trim();}), ntp_servers:document.getElementById('prov-ntp').value.split(',').map(function(s){return s.trim();}), syslog_server:document.getElementById('prov-syslog').value.trim()};
  } else if (current === 4) {
    data = {admin_password:document.getElementById('prov-admin-pw').value, web_filter:document.getElementById('prov-webfilter').checked, ids_ips:document.getElementById('prov-ids').checked};
  }
  await apiFetch('/api/provisioning/'+encodeURIComponent(_provisionSession)+'/step/'+current, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  provisionRenderStep(current + 1);
}

function provisionPrevStep(current) { provisionRenderStep(current - 1); }

async function provisionLoadSummary() {
  var data = await apiFetch('/api/provisioning/'+encodeURIComponent(_provisionSession)+'/summary');
  if (!data) return;
  var el = document.getElementById('prov-summary');
  var steps = data.steps || {};
  var html = '<div class="text-ui">';
  if (steps['1']) html += '<div class="mb-2"><strong>' + t('kunde_2') + '</strong> '+esc(steps['1'].name||'-')+' @ '+esc(steps['1'].location||'-')+' ('+esc(steps['1'].device_type)+')</div>';
  if (steps['2']) html += '<div class="mb-2"><strong>' + t('nettverk') + '</strong> WAN='+esc(steps['2'].wan_type)+', LAN='+esc(steps['2'].lan_subnet)+(steps['2'].vlans?.length ? ', '+steps['2'].vlans.length+' VLANs' : '')+'</div>';
  if (steps['3']) html += '<div class="mb-2"><strong>' + t('tjenester') + '</strong> DNS='+esc((steps['3'].dns_servers||[]).join(','))+', NTP='+esc((steps['3'].ntp_servers||[]).join(','))+'</div>';
  if (steps['4']) html += '<div class="mb-2"><strong>' + t('sikkerhet') + '</strong> Web-filter='+(steps['4'].web_filter?'Ja':t('lbl_no','No'))+', IDS='+(steps['4'].ids_ips?'Ja':t('lbl_no','No'))+'</div>';
  html += '</div>';
  el.innerHTML = html;
}

async function provisionGenerate(useAi) {
  var el = document.getElementById('prov-output');
  el.style.display = 'block';
  el.textContent = useAi ? t('msg_generating_ai','Generating with AI...') : t('msg_generating_config','Generating configuration...');
  var data = await apiFetch('/api/provisioning/'+encodeURIComponent(_provisionSession)+'/generate', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({use_ai:useAi})});
  if (!data || !data.configs) { el.textContent = t('err_generation_failed','Generation failed'); return; }
  var text = '';
  if (data.configs.fortigate_cli) text += '# === FortiGate CLI ===\n' + data.configs.fortigate_cli + '\n\n';
  if (data.configs.unifi_json) text += '# === UniFi JSON ===\n' + data.configs.unifi_json;
  el.textContent = text || t('msg_no_config_generated','No configuration generated');
}

// ── Provisioning helpers ────────────────────────────────────────────────────

// From the customer chosen in the bar above the wizard.
async function provisionAutoFill() {
  var customerId = await toolCustomerId();
  if (!customerId) return;
  var data = await apiFetch('/api/network-devices/' + encodeURIComponent(customerId));
  if (data && data.fortigate && data.fortigate.host) {
    var targetEl = document.getElementById('prov-target');
    if (targetEl && !targetEl.value) targetEl.value = data.fortigate.host;
  }
  var nameEl = document.getElementById('prov-name');
  if (nameEl && !nameEl.value) nameEl.value = _customerNameById(customerId);
}

async function provisionSuggestSubnets() {
  var name = (document.getElementById('prov-name') || {}).value || '';
  if (!name) name = (document.getElementById('prov-name') || {}).placeholder || 'default';
  var data = await apiFetch('/api/provisioning/suggest-subnets', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name})
  });
  if (!data || !data.lan_subnet) return;
  _provisionSuggested = data;
  var subnetEl = document.getElementById('prov-subnet');
  if (subnetEl) subnetEl.value = data.lan_subnet;
  provisionRenderVlans(data.vlans || []);
}

var _provisionVlans = [];

function provisionRenderVlans(vlans) {
  _provisionVlans = vlans && vlans.length ? vlans : [];
  var el = document.getElementById('prov-vlan-table');
  if (!el) return;
  if (!_provisionVlans.length) {
    el.innerHTML = '<div class="text-muted text-sm p-2">' + t('msg_no_vlans','Ingen VLANs. Klikk "Auto-generer subnets" eller legg til manuelt.') + '</div>';
    return;
  }
  var html = '<table class="data-table">'
    + '<thead><tr class="text-left"><th>' + t('navn_2') + '</th><th>' + t('vlan_id') + '</th><th>' + t('subnet') + '</th><th class="col-check"></th></tr></thead><tbody>';
  for (var i = 0; i < _provisionVlans.length; i++) {
    var v = _provisionVlans[i];
    html += '<tr>'
      + '<td><input type="text" class="field-input py-1 px-2 text-sm" value="' + esc(v.name || '') + '" data-vlan-idx="'+i+'" data-vlan-field="name"></td>'
      + '<td><input type="number" class="field-input py-1 px-2 text-sm input-narrow" value="' + esc(v.id || '') + '" data-vlan-idx="'+i+'" data-vlan-field="id"></td>'
      + '<td><input type="text" class="field-input py-1 px-2 text-sm" value="' + esc(v.subnet || '') + '" data-vlan-idx="'+i+'" data-vlan-field="subnet"></td>'
      + '<td><button class="btn btn-ghost btn-sm text-danger" data-click-handler="provisionRemoveVlan" data-index="'+i+'">✕</button></td>'
      + '</tr>';
  }
  html += '</tbody></table>'
    + '<div class="text-xs text-muted mt-2">' + t('inf_vlan_policy_hint','Hver VLAN får standard policy: VLAN → WAN, NAT, full UTM. Spesialcase (no-UTM, web-only osv.) konfigurerer du i FortiGate-GUI etter') + ' generering.</div>';
  el.innerHTML = html;
}

function provisionAddVlan() {
  _provisionVlans.push({name:'', id:_provisionVlans.length ? Math.max.apply(null, _provisionVlans.map(function(v){return v.id||0;}))+10 : 10, subnet:''});
  provisionRenderVlans(_provisionVlans);
}

function provisionRemoveVlan(idx) {
  _provisionVlans.splice(idx, 1);
  provisionRenderVlans(_provisionVlans);
}

function provisionCollectVlans() {
  var rows = document.querySelectorAll('[data-vlan-idx]');
  var map = {};
  rows.forEach(function(el) {
    var idx = el.dataset.vlanIdx;
    if (!map[idx]) map[idx] = {};
    var field = el.dataset.vlanField;
    map[idx][field] = field === 'id' ? parseInt(el.value) || 0 : el.value.trim ? el.value.trim() : el.value;
  });
  return Object.values(map).filter(function(v) { return v.name || v.id; });
}

var _lastDeploySummary = null;

async function provisionDeploy(method) {
  var el = document.getElementById('prov-deploy-result');
  el.style.display = 'block';
  el.innerHTML = '<div class="text-accent text-ui"><div class="loader align-middle mr-2"></div>' + t('msg_deploying','Deployer konfigurasjon...') + '</div>';

  // First ensure config is generated
  await apiFetch('/api/provisioning/'+encodeURIComponent(_provisionSession)+'/generate', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({use_ai:false})});

  var data = await apiFetch('/api/provisioning/'+encodeURIComponent(_provisionSession)+'/deploy', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({method:method})
  });

  if (!data) { el.innerHTML = '<div class="alert alert-error">' + t('msg_deploy_failed','Deploy feilet') + '</div>'; return; }

  var fg = data.results && data.results.fortigate;
  if (!fg) { el.innerHTML = '<div class="alert alert-error">' + esc(data.error || t('msg_deploy_failed','Deploy feilet')) + '</div>'; return; }

  _lastDeploySummary = fg.config_summary || null;

  var ok = Number(fg.success) || 0;
  var total = Number(fg.total) || 0;
  var failed = Number(fg.failed) || 0;
  var statusClass = failed === 0 ? 'alert-success' : (ok > failed ? 'alert-warning' : 'alert-error');
  var statusText = failed === 0 ? t('msg_deploy_success','Konfigurasjon deployet') : (ok + '/' + total + ' OK, ' + failed + ' feilet');

  var html = '<div class="alert ' + statusClass + ' mb-3">' + statusText + '</div>';

  // Step details
  if (fg.details) {
    html += '<details class="mb-4"><summary class="cursor-pointer text-ui fw-semibold mb-2">' + t('lbl_details','Detaljer') + ' (' + total + ' steg)</summary>';
    html += '<div class="inset text-sm font-mono max-h-md overflow-y-auto">';
    fg.details.forEach(function(d) {
      var icon = d.ok ? '<span class="text-success">✓</span>' : '<span class="text-danger">✗</span>';
      html += '<div class="py-0-5 px-0">' + icon + ' ' + esc(d.step) + (d.error ? ' · <span class="text-danger">' + esc(d.error) + '</span>' : '') + '</div>';
    });
    html += '</div></details>';
  }

  // IP change notification
  if (fg.lan_ip_changed && fg.new_ip) {
    html += '<div class="alert alert-warning my-3">'
      + '<strong>' + t('msg_lan_ip_changed','Brannmurens LAN-adresse er endret') + '</strong><br>'
      + t('msg_lan_ip_old','Gammel IP') + ': <code>' + esc(fg.old_ip || '') + '</code> → '
      + t('msg_lan_ip_new','Ny IP') + ': <code>' + esc(fg.new_ip) + '</code><br><br>'
      + t('msg_lan_ip_instructions','Du må koble til det nye subnettet for å nå brannmuren. Forny DHCP-lease eller sett manuell IP.') + '<br><br>'
      + '<a href="https://' + esc(fg.new_ip) + ':8443" target="_blank" class="btn btn-primary btn-sm">'
      + t('btn_open_new_ip','Åpne brannmur på ny adresse') + ' → ' + esc(fg.new_ip) + ':8443</a>'
      + '</div>';
  }

  // Config summary
  if (_lastDeploySummary) {
    html += _renderConfigSummary(_lastDeploySummary);
  }

  el.innerHTML = html;
}

function _renderConfigSummary(s) {
  var html = '<div class="card mt-4">';
  html += '<div class="card-title">' + t('hdr_config_summary','Konfigurasjonsoversikt') + '</div>';

  // System
  html += '<div class="grid grid-cols-2 gap-3 text-ui mb-4">';
  html += '<div><strong>' + t('hostname') + '</strong> ' + esc(s.hostname || '') + '</div>';
  html += '<div><strong>' + t('fortigate') + '</strong> ' + esc(s.fortigate_host || '') + ':' + esc(s.fortigate_port || 443) + '</div>';
  html += '<div><strong>' + t('wan') + '</strong> ' + esc(s.wan_interface || '') + ' (' + esc(s.wan_mode || '') + ')</div>';
  html += '<div><strong>' + t('lan') + '</strong> ' + esc(s.lan_interface || '') + ' · ' + esc(s.lan_subnet || '') + '</div>';
  html += '<div><strong>' + t('dns') + '</strong> ' + esc((s.dns || []).join(', ')) + '</div>';
  html += '<div><strong>' + t('ntp') + '</strong> ' + esc((s.ntp || []).join(', ')) + '</div>';
  html += '</div>';

  // VLANs
  if (s.vlans && s.vlans.length) {
    html += '<div class="subhead">VLANs</div>';
    html += '<table class="data-table mb-4">';
    html += '<thead><tr class="text-left"><th>ID</th><th>' + t('navn_3') + '</th><th>' + t('interface') + '</th><th>' + t('subnet') + '</th><th>' + t('gateway_2') + '</th><th>DHCP</th></tr></thead><tbody>';
    s.vlans.forEach(function(v) {
      html += '<tr>';
      html += '<td class="font-mono">' + esc(v.id) + '</td>';
      html += '<td>' + esc(v.name) + '</td>';
      html += '<td class="font-mono">' + esc(v.interface) + '</td>';
      html += '<td class="font-mono">' + esc(v.subnet) + '</td>';
      html += '<td class="font-mono">' + esc(v.gateway) + '</td>';
      html += '<td class="font-mono">' + esc(v.dhcp_range) + '</td>';
      html += '</tr>';
    });
    html += '</tbody></table>';
  }

  // VPN
  if (s.vpn) {
    html += '<div class="subhead">IPsec VPN · ' + esc(s.vpn.name || '') + '</div>';
    html += '<div class="inset grid grid-cols-2 gap-2 text-sm mb-4">';
    html += '<div><strong>' + t('type_3') + '</strong> ' + esc(s.vpn.type) + '</div>';
    html += '<div><strong>' + t('wan') + '</strong> ' + esc(s.vpn.wan_interface) + '</div>';
    html += '<div><strong>' + t('kryptering') + '</strong> ' + esc(s.vpn.proposal) + '</div>';
    html += '<div><strong>' + t('dh_gruppe') + '</strong> ' + esc(s.vpn.dh_group) + '</div>';
    html += '<div><strong>' + t('tunnel_pool') + '</strong> ' + esc(s.vpn.tunnel_pool) + '</div>';
    html += '<div><strong>' + t('split_tunnel') + '</strong> ' + esc(s.vpn.split_tunnel) + '</div>';
    html += '<div class="col-span-full border-t pt-2 mt-1">';
    html += '<strong>' + t('bruker') + '</strong> <code class="bg-card py-0-5 px-2 rounded-sm">' + esc(s.vpn.user) + '</code>';
    html += ' &nbsp; <strong>' + t('passord_2') + '</strong> <code class="bg-card py-0-5 px-2 rounded-sm cursor-pointer" data-click-handler="provisionCopySecret">' + esc(s.vpn.user_password) + '</code>';
    html += '</div>';
    html += '<div class="col-span-full">';
    html += '<strong>PSK:</strong> <code class="bg-card py-0-5 px-2 rounded-sm cursor-pointer break-all" data-click-handler="provisionCopySecret">' + esc(s.vpn.psk) + '</code>';
    html += '</div></div>';
  }

  // Security
  if (s.security_profiles) {
    html += '<div class="subhead">' + t('sikkerhetsprofiler') + '</div>';
    html += '<div class="flex gap-2 flex-wrap mb-4">';
    var sp = s.security_profiles;
    for (var k in sp) {
      var color = sp[k] === 'none' ? 'var(--red)' : 'var(--green)';
      html += '<span class="' + badgeClass(color) + ' badge-bordered">' + esc(k) + ': ' + esc(sp[k]) + '</span>';
    }
    html += '</div>';
  }

  // Actions
  html += '<div class="flex gap-2 mt-3 pt-3 border-t">';
  html += '<button class="btn btn-primary btn-sm" data-click-handler="provisionDownloadSummary">' + t('btn_download_summary','Last ned oversikt') + '</button>';
  html += '<button class="btn btn-default btn-sm" data-click-handler="provisionCopySummary">' + t('btn_copy_to_clipboard') + '</button>';
  html += '</div>';
  html += '</div>';
  return html;
}

function provisionDownloadSummary() {
  if (!_lastDeploySummary) return;
  var s = _lastDeploySummary;
  var lines = [];
  lines.push('╔══════════════════════════════════════════════════════════════╗');
  lines.push('║  FORTIGATE KONFIGURASJONSOVERSIKT                          ║');
  lines.push('║  ' + (s.customer || '').padEnd(58) + '║');
  lines.push('║  Generert: ' + (s.generated_at || '').substring(0,19).padEnd(48) + '║');
  lines.push('╚══════════════════════════════════════════════════════════════╝');
  lines.push('');
  lines.push('SYSTEM');
  lines.push('─'.repeat(60));
  lines.push('  Hostname:       ' + (s.hostname || ''));
  lines.push('  FortiGate:      ' + (s.fortigate_host || '') + ':' + (s.fortigate_port || 443));
  lines.push('  WAN interface:  ' + (s.wan_interface || '') + ' (' + (s.wan_mode || '') + ')');
  lines.push('  LAN interface:  ' + (s.lan_interface || '') + ' · ' + (s.lan_subnet || ''));
  lines.push('  LAN gateway:    ' + (s.lan_gateway || ''));
  lines.push('  DNS:            ' + (s.dns || []).join(', '));
  lines.push('  NTP:            ' + (s.ntp || []).join(', '));
  lines.push('');
  lines.push('VLANS');
  lines.push('─'.repeat(60));
  lines.push('  ' + 'ID'.padEnd(6) + t('inf_col_name','Navn').padEnd(16) + 'Interface'.padEnd(22) + 'Subnet'.padEnd(20) + 'GW');
  (s.vlans || []).forEach(function(v) {
    lines.push('  ' + String(v.id).padEnd(6) + (v.name||'').padEnd(16) + (v.interface||'').padEnd(22) + (v.subnet||'').padEnd(20) + (v.gateway||''));
  });
  lines.push('');
  if (s.vpn) {
    lines.push('IPSEC VPN');
    lines.push('─'.repeat(60));
    lines.push('  ' + t('inf_lbl_name','Navn:').padEnd(16) + (s.vpn.name || ''));
    lines.push('  Type:           ' + (s.vpn.type || ''));
    lines.push('  WAN interface:  ' + (s.vpn.wan_interface || ''));
    lines.push('  Kryptering:     ' + (s.vpn.proposal || ''));
    lines.push('  DH-gruppe:      ' + (s.vpn.dh_group || ''));
    lines.push('  Tunnel-pool:    ' + (s.vpn.tunnel_pool || ''));
    lines.push('  Split-tunnel:   ' + (s.vpn.split_tunnel || ''));
    lines.push('');
    lines.push('  CREDENTIALS (OPPBEVAR SIKKERT)');
    lines.push('  ' + t('inf_lbl_user','Bruker:').padEnd(16) + (s.vpn.user || ''));
    lines.push('  ' + t('inf_lbl_password','Passord:').padEnd(16) + (s.vpn.user_password || ''));
    lines.push('  PSK:            ' + (s.vpn.psk || ''));
    lines.push('');
  }
  if (s.security_profiles) {
    lines.push('SIKKERHETSPROFILER');
    lines.push('─'.repeat(60));
    var sp = s.security_profiles;
    for (const k in sp) { lines.push('  ' + (k + ':').padEnd(20) + sp[k]); }
    lines.push('');
  }
  if (s.hardening) {
    lines.push('HARDENING');
    lines.push('─'.repeat(60));
    var h = s.hardening;
    for (const k in h) { lines.push('  ' + (k + ':').padEnd(20) + h[k]); }
  }
  var text = lines.join('\n');
  var blob = new Blob([text], {type:'text/plain'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = (s.customer || 'fortigate').replace(/\s+/g,'-') + '_fortigate-config_' + new Date().toISOString().slice(0,10) + '.txt';
  a.click();
}

function provisionCopySummary() {
  if (!_lastDeploySummary) return;
  navigator.clipboard.writeText(JSON.stringify(_lastDeploySummary, null, 2));
  showToast(t('msg_copied','Kopiert til utklippstavle'), 'success', 2000);
}

// ═══════════════════════════════════════════════════════════════════
// FORTIGATE DASHBOARD (ALL CUSTOMERS)
// ═══════════════════════════════════════════════════════════════════

export async function dashLoadFortiGates() {
  var el = document.getElementById('dash-fg-content');
  el.innerHTML = '<div class="loader loader-md"></div><div class="text-center text-muted text-sm">' + t('msg_loading_fortigates','Loading all FortiGate firewalls...') + '</div>';

  var data = await apiFetch('/api/fortigate/all');
  if (!data || !data.fortigates) { el.innerHTML = '<div class="empty-signpost"><p>' + esc(t('msg_no_fortigates','Ingen FortiGater konfigurert. Legg dem til per kunde under Administrasjon › Integrasjoner.')) + '</p>' + adminSignpostButton('integrations', 'btn_open_integrations') + '</div>'; return; }

  var fgs = data.fortigates;
  if (!fgs.length) { el.innerHTML = '<div class="empty-note">' + t('msg_no_fortigates_short','No FortiGates configured.') + '</div>'; return; }

  var online = fgs.filter(function(f){return f.status==='online';}).length;
  var errors = fgs.filter(function(f){return f.status==='error';}).length;

  // Summary KPI cards
  var totalVpn = fgs.reduce(function(s,f){return s+(f.vpn_tunnels||0);},0);
  var totalPolicies = fgs.reduce(function(s,f){return s+(f.policy_count||0);},0);
  var avgCpu = 0, cpuCount = 0;
  fgs.forEach(function(f){if(f.cpu_pct!==null&&f.cpu_pct!==undefined){avgCpu+=Number(f.cpu_pct);cpuCount++;}});
  avgCpu = cpuCount ? Math.round(avgCpu/cpuCount) : 0;
  var avgMem = 0, memCount = 0;
  fgs.forEach(function(f){if(f.mem_pct!==null&&f.mem_pct!==undefined){avgMem+=Number(f.mem_pct);memCount++;}});
  avgMem = memCount ? Math.round(avgMem/memCount) : 0;

  // ── KPI row: fixed-height cards, no justify-content ──
  var html = '<div class="card-grid card-grid--kpi grid grid-cols-5 gap-3 mb-4">';
  var kpis = [
    {label:'Brannmurer', value:fgs.length, sub:online+' online'+(errors?' / '+errors+' ' + t('inf_errors_lc','feil'):''), color:'var(--blue)'},
    {label:'Snitt CPU', value:avgCpu+'%', sub:'-', color: avgCpu>60?'var(--orange)':'var(--green)'},
    {label:'Snitt minne', value:avgMem+'%', sub:'-', color: avgMem>70?'var(--orange)':'var(--green)'},
    {label:'VPN-tunneler', value:Number(totalVpn), sub:'totalt', color:'var(--purple)'},
    {label:'Brannmurregler', value:Number(totalPolicies), sub:'totalt', color:'var(--text-muted)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card kpi-card ' + toneVar(k.color) + '">';
    html += '<div class="kpi-value">'+k.value+'</div>';
    html += '<div class="kpi-label">'+k.label+'</div>';
    html += '<div class="kpi-sub">'+k.sub+'</div>';
    html += '</div>';
  });
  html += '</div>';

  html += '<div class="flex items-center gap-3 mb-3">';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="dashLoadFortiGates">' + t('oppdater') + '</button>';
  html += '<button class="btn btn-primary btn-sm" data-write data-click-handler="fgBackupAll">' + t('backup_alle') + '</button>';
  html += '</div>';

  // ── Device cards: strict 3-row grid ──
  html += '<div class="grid grid-auto-lg gap-3">';
  fgs.forEach(function(f) {
    var color = f.status === 'online' ? 'var(--green)' : f.status === 'error' ? 'var(--red)' : 'var(--orange)';
    html += '<div class="card device-card cursor-pointer edge-tone ' + toneVar(color) + '" data-click-handler="dashFgDetail" data-customer-id="'+esc(f.customer_id)+'">';

    // ROW 1 — Header (24px): hostname + status dot
    html += '<div class="device-card-head">';
    html += '<strong class="text-base nowrap overflow-hidden ellipsis flex-1 min-w-0">'+esc(f.hostname||f.host||'-')+'</strong>';
    html += '<span class="dot ' + toneClass(color) + ' ml-2"></span>';
    html += '</div>';

    // ROW 2 — Subtitle (20px): customer name
    html += '<div class="device-card-sub">'+esc(f.customer_name||'-')+'</div>';

    // ROW 3 — Data (1fr): 2-col stats grid, ALWAYS 8 fields
    html += '<div class="grid grid-cols-2 gap-1 text-sm text-muted content-start pt-2">';
    html += '<span>Model: <strong class="text-default">'+esc(f.model||'-')+'</strong></span>';
    html += '<span>FW: '+esc(f.firmware||'-')+'</span>';
    html += '<span>S/N: <span class="font-mono text-xs">'+esc(f.serial||'-')+'</span></span>';
    html += '<span>Uptime: '+esc(f.uptime||'-')+'</span>';
    html += '<span>CPU: '+(f.cpu_pct!=null ? Number(f.cpu_pct)+'%' : '-')+'</span>';
    html += '<span>Mem: '+(f.mem_pct!=null ? Number(f.mem_pct)+'%' : '-')+'</span>';
    html += '<span>VPN: '+(f.vpn_tunnels!=null ? Number(f.vpn_tunnels) : '-')+'</span>';
    html += '<span>Rules: '+(f.policy_count!=null ? Number(f.policy_count) : '-')+'</span>';
    html += '</div>';

    html += '</div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

function dashFgDetail(customerId) {
  // Toggle inline detail panel below the FortiGate cards
  var existing = document.getElementById('fg-detail-' + customerId);
  if (existing) { existing.remove(); return; }
  // Remove any other open detail
  document.querySelectorAll('.fg-detail-panel').forEach(function(p) { p.remove(); });

  var el = document.getElementById('dash-fg-content');
  var panel = document.createElement('div');
  panel.id = 'fg-detail-' + customerId;
  panel.className = 'fg-detail-panel';
  panel.style.cssText = 'margin-top:16px;margin-bottom:16px;';
  panel.innerHTML = '<div class="card p-4 edge-accent"><div class="loader mx-auto"></div></div>';
  el.appendChild(panel);

  // Load threats, firewall audit, and live device data in parallel
  Promise.all([
    apiFetch('/api/fortigate/threats/' + encodeURIComponent(customerId)),
    apiFetch('/api/fortigate/firewall-audit/' + encodeURIComponent(customerId)),
    apiFetch('/api/dashboard/poll/' + encodeURIComponent(customerId), {method:'POST'}).catch(function(){return null;})
  ]).then(function(results) {
    var threats = results[0];
    var audit = results[1];
    var liveData = results[2];
    // Find the FortiGate device in live data
    var dev = null;
    if (liveData && liveData.devices) {
      for (var i = 0; i < liveData.devices.length; i++) {
        if (liveData.devices[i].vendor === 'fortigate') { dev = liveData.devices[i]; break; }
      }
    }
    var ex = (dev && dev.extra) ? dev.extra : {};

    var h = '<div class="card p-4 edge-accent">';
    h += '<div class="flex justify-between items-center mb-3">';
    h += '<div class="text-base fw-bold">'+t('hdr_fg_detail','FortiGate Detail')+'</div>';
    h += '<div class="flex gap-2 items-center">';
    h += '<button class="btn btn-primary btn-sm" data-write data-click-handler="fgBackupConfig" data-customer-id="'+esc(customerId)+'">' + t('backup_config') + '</button>';
    h += '<button class="btn btn-ghost btn-sm" data-click-handler="fgShowBackups" data-customer-id="'+esc(customerId)+'">'+t('btn_backup_history','Backup-historikk')+'</button>';
    h += '<button class="btn btn-ghost btn-sm" data-click-handler="removeElement" data-target="fg-detail-'+esc(customerId)+'">'+t('btn_close','Close')+'</button>';
    h += '</div></div>';
    h += '<div id="fg-backup-list-'+esc(customerId)+'" class="mb-2"></div>';

    // Threats
    if (threats && threats.summary) {
      var s = threats.summary;
      h += '<div class="subhead">'+t('hdr_threats','Threats')+' ('+t('lbl_last_7d','Last 7 days')+')</div>';
      h += '<div class="flex gap-2 mb-3 flex-wrap">';
      if (s.critical) h += '<span class="badge badge-danger">'+Number(s.critical)+' Critical</span>';
      if (s.high) h += '<span class="badge badge-warning">'+Number(s.high)+' High</span>';
      if (s.medium) h += '<span class="badge badge-info">'+Number(s.medium)+' Medium</span>';
      if (s.low) h += '<span class="badge">'+Number(s.low)+' Low</span>';
      if (s.total === 0) h += '<span class="text-success text-sm">&#10003; '+t('msg_no_threats','No threats detected')+'</span>';
      h += '</div>';
      if (threats.recent && threats.recent.length) {
        h += '<table class="data-table data-table--compact mb-3">';
        h += '<thead><tr><th>'+t('col_time','Time')+'</th><th>'+t('col_type','Type')+'</th><th class="text-center">'+t('col_severity','Severity')+'</th><th>'+t('col_source','Source')+'</th><th>'+t('col_attack','Attack')+'</th></tr></thead><tbody>';
        threats.recent.slice(0,5).forEach(function(e) {
          var sc = {critical:'var(--red)',high:'var(--orange)',medium:'var(--blue)',low:'var(--text-dim)'}[e.severity]||'var(--text-dim)';
          h += '<tr><td>'+esc(e.timestamp||'').substring(0,16)+'</td><td>'+esc(e.type)+'</td><td class="text-center ' + toneClass(sc) + ' fw-semibold">'+esc(e.severity)+'</td><td class="font-mono text-2xs">'+esc(e.srcip||'')+'</td><td>'+esc(e.attack||'')+'</td></tr>';
        });
        h += '</tbody></table>';
      }
    } else {
      h += '<div class="text-sm text-muted mb-3">'+t('msg_no_threat_data','Could not load threat data')+'</div>';
    }

    // Firewall Audit
    if (audit && audit.total_rules !== undefined) {
      var scoreColor = audit.score >= 90 ? 'var(--green)' : audit.score >= 70 ? 'var(--orange)' : 'var(--red)';
      h += '<div class="flex items-center gap-3 mb-2">';
      h += '<div class="text-ui fw-semibold">'+t('hdr_fw_audit','Firewall Audit')+'</div>';
      h += '<span class="' + badgeClass(scoreColor) + '">'+Number(audit.score)+'/100</span>';
      h += '<span class="text-xs text-muted">'+Number(audit.total_rules)+' '+t('lbl_rules','rules')+' ('+Number(audit.enabled)+' '+t('lbl_enabled','enabled')+')</span>';
      h += '</div>';
      if (audit.issues && audit.issues.length) {
        h += '<table class="data-table data-table--compact">';
        h += '<thead><tr><th>' + t('policy') + '</th><th class="text-center">'+t('col_issue','Issue')+'</th><th class="text-center">'+t('col_severity','Severity')+'</th><th>'+t('col_detail','Detail')+'</th></tr></thead><tbody>';
        audit.issues.forEach(function(iss) {
          var ic = iss.severity==='critical'?'var(--red)':'var(--orange)';
          h += '<tr><td class="fw-medium">'+esc(iss.name||'Policy '+iss.policy_id)+'</td><td class="text-center"><span class="text-2xs py-0-5 px-2 rounded-full">'+esc(iss.issue)+'</span></td><td class="text-center ' + toneClass(ic) + ' fw-semibold">'+esc(iss.severity)+'</td><td class="text-muted">'+esc(iss.detail)+'</td></tr>';
        });
        h += '</tbody></table>';
      } else {
        h += '<div class="text-success text-sm">&#10003; '+t('msg_no_issues','No issues found')+'</div>';
      }
    }

    // ── Live device data: interfaces, VPN, DHCP, DNS, admins ──
    if (dev) {
      h += '<div class="mt-4 border-t pt-3">';
      h += '<div class="subhead">' + t('live_data') + '</div>';

      // KPI row
      var liveKpis = [];
      if (dev.cpu_pct != null) liveKpis.push({l:'CPU', v:Number(dev.cpu_pct)+'%', c:dev.cpu_pct>80?'var(--red)':dev.cpu_pct>50?'var(--orange)':'var(--green)'});
      if (dev.mem_pct != null) liveKpis.push({l:'Minne', v:Number(dev.mem_pct)+'%', c:dev.mem_pct>80?'var(--red)':dev.mem_pct>50?'var(--orange)':'var(--green)'});
      if (dev.sessions != null) liveKpis.push({l:'Sesjoner', v:Number(dev.sessions).toLocaleString(), c:'var(--blue)'});
      if (dev.vpn_tunnels != null) liveKpis.push({l:'VPN-tunneler', v:Number(dev.vpn_tunnels), c:'var(--purple)'});
      if (liveKpis.length) {
        h += '<div class="kpi-row mb-3">';
        liveKpis.forEach(function(k){h += '<div class="card kpi-card top-tone ' + toneVar(k.c) + '"><div class="text-lg fw-bold">'+k.v+'</div><div class="text-2xs text-muted">'+k.l+'</div></div>';});
        h += '</div>';
      }

      // Interfaces
      if (ex.interfaces && ex.interfaces.length) {
        h += '<div class="subhead mt-3">Grensesnitt ('+ex.interfaces.length+')</div>';
        h += '<table class="data-table data-table--compact"><thead><tr><th>' + t('navn_3') + '</th><th>' + t('type_3') + '</th><th>IP</th><th>' + t('link') + '</th><th>' + t('hastighet') + '</th></tr></thead><tbody>';
        ex.interfaces.forEach(function(iface) {
          if (!iface.ip || iface.ip === '0.0.0.0') return;
          var linkColor = iface.link ? 'var(--green)' : 'var(--red)';
          h += '<tr><td class="fw-semibold">'+esc(iface.name)+'</td><td class="text-muted">'+esc(iface.type||'-')+'</td><td class="font-mono text-2xs">'+esc(iface.ip)+'/'+esc(iface.mask||'')+'</td><td><span class="' + toneClass(linkColor) + '">'+(iface.link?'Up':'Down')+'</span></td><td>'+(iface.speed?esc(iface.speed)+'M':'')+'</td></tr>';
        });
        h += '</tbody></table>';
      }

      // VPN tunnels
      if (ex.vpn_tunnels && ex.vpn_tunnels.length) {
        h += '<div class="subhead mt-3">VPN-tunneler ('+ex.vpn_tunnels.length+')</div>';
        h += '<table class="data-table data-table--compact"><thead><tr><th>' + t('navn_3') + '</th><th>' + t('remote_gw') + '</th><th>' + t('status_3') + '</th></tr></thead><tbody>';
        ex.vpn_tunnels.forEach(function(v) {
          var vpnColor = v.status === 'up' ? 'var(--green)' : 'var(--red)';
          h += '<tr><td class="fw-semibold">'+esc(v.name)+'</td><td class="font-mono text-2xs">'+esc(v.remote_gw||'-')+'</td><td><span class="' + toneClass(vpnColor) + '">'+esc(v.status||'unknown')+'</span></td></tr>';
        });
        h += '</tbody></table>';
      }

      // SSL VPN active users
      if (ex.ssl_vpn_users && ex.ssl_vpn_users.length) {
        h += '<div class="subhead mt-3">' + t('inf_ssl_vpn_users','SSL VPN-brukere') + ' ('+ex.ssl_vpn_users.length+' aktive)</div>';
        h += '<table class="data-table data-table--compact"><thead><tr><th>' + t('bruker') + '</th><th>' + t('remote_ip') + '</th><th>' + t('tunnel_ip') + '</th><th>' + t('varighet') + '</th></tr></thead><tbody>';
        ex.ssl_vpn_users.forEach(function(u) {
          var dur = u.duration > 3600 ? Math.floor(u.duration/3600)+'t '+Math.floor((u.duration%3600)/60)+'m' : Math.floor(u.duration/60)+'m';
          h += '<tr><td class="fw-medium">'+esc(u.user)+'</td><td class="font-mono text-2xs">'+esc(u.remote_ip)+'</td><td class="font-mono text-2xs">'+esc(u.tunnel_ip)+'</td><td>'+dur+'</td></tr>';
        });
        h += '</tbody></table>';
      }

      // Firewall policies (all rules with security profiles)
      if (ex.policies && ex.policies.length) {
        var badPolicies = ex.policies.filter(function(p){return p.action==='accept'&&p.src==='all'&&p.dst==='all'&&p.svc==='ALL';});
        var noProfile = ex.policies.filter(function(p){return p.action==='accept'&&(!p.profiles||!p.profiles.length)&&p.enabled!==false;});
        var segmentDeny = ex.policies.filter(function(p){return p.action==='deny'&&p.enabled!==false;});
        var acceptRules = ex.policies.filter(function(p){return p.action==='accept'&&p.enabled!==false;});
        h += '<div class="subhead mt-3">Brannmurregler ('+ex.policies.length+')';
        if (segmentDeny.length) h += ' <span class="text-success fw-normal">— '+segmentDeny.length+' segmentering (deny)</span>';
        h += ' <span class="text-muted fw-normal">— '+acceptRules.length+' accept</span>';
        if (badPolicies.length) h += ' <span class="text-danger fw-normal">— '+badPolicies.length+' accept any/any/any</span>';
        if (noProfile.length) h += ' <span class="text-warning fw-normal">— '+noProfile.length+' uten sikkerhetsprofil</span>';
        h += '</div>';
        h += '<div class="overflow-x-auto"><table class="data-table data-table--compact"><thead><tr><th>#</th><th>' + t('navn_4') + '</th><th>' + t('inn') + '</th><th>' + t('ut') + '</th><th>' + t('kilde') + '</th><th>' + t('dest') + '</th><th>' + t('tjeneste_3') + '</th><th>' + t('aksjon') + '</th><th>NAT</th><th>' + t('logg') + '</th><th>' + t('sikkerhet') + '</th></tr></thead><tbody>';
        ex.policies.forEach(function(p) {
          if (p.enabled === false) return; // skip disabled
          var isBad = (p.action==='accept'&&p.src==='all'&&p.dst==='all'&&p.svc==='ALL');
          var noProf = (p.action==='accept'&&(!p.profiles||!p.profiles.length));
          var isDeny = (p.action==='deny');
          var rowBg = isBad ? 'row-danger' : isDeny ? 'row-success' : noProf ? 'row-warning' : '';
          var logColor = (p.log==='all'||p.log==='utm') ? 'var(--green)' : p.action==='deny' ? 'var(--text-muted)' : 'var(--red)';
          var profHtml = isDeny ? '<span class="text-success">' + t('segmentering') + '</span>' : (p.profiles&&p.profiles.length) ? p.profiles.map(function(pr){return '<span class="badge badge-info">'+esc(pr)+'</span>';}).join(' ') : '<span class="text-warning">' + t('ingen_2') + '</span>';
          h += '<tr class="' + rowBg + '">';
          h += '<td>'+esc(String(p.id))+'</td>';
          h += '<td class="fw-medium max-w-sm overflow-hidden ellipsis nowrap">'+esc(p.name)+'</td>';
          h += '<td class="text-2xs">'+esc(p.srcintf||'')+'</td>';
          h += '<td class="text-2xs">'+esc(p.dstintf||'')+'</td>';
          h += '<td class="text-2xs max-w-sm overflow-hidden ellipsis nowrap" title="'+esc(p.src)+'">'+esc(p.src)+'</td>';
          h += '<td class="text-2xs max-w-sm overflow-hidden ellipsis nowrap" title="'+esc(p.dst)+'">'+esc(p.dst)+'</td>';
          h += '<td class="text-2xs">'+esc(p.svc)+'</td>';
          var actionColor = p.action==='deny' ? 'var(--green)' : isBad ? 'var(--red)' : 'var(--text)';
          h += '<td class="text-center ' + toneClass(actionColor) + ' fw-medium">'+esc(p.action||'accept')+'</td>';
          h += '<td class="text-center">'+(p.nat?'✓':'')+'</td>';
          h += '<td class="text-center ' + toneClass(logColor) + '">'+esc(p.log||'-')+'</td>';
          h += '<td class="text-2xs">'+profHtml+'</td>';
          h += '</tr>';
        });
        h += '</tbody></table></div>';
      }

      // Static routes
      if (ex.static_routes && ex.static_routes.length) {
        h += '<div class="subhead mt-3">Statiske ruter ('+ex.static_routes.length+')</div>';
        h += '<table class="data-table data-table--compact"><thead><tr><th>' + t('destinasjon') + '</th><th>' + t('gateway_2') + '</th><th>' + t('interface') + '</th><th>' + t('distanse') + '</th></tr></thead><tbody>';
        ex.static_routes.forEach(function(r) {
          h += '<tr><td class="font-mono text-2xs">'+esc(r.dst)+'</td><td class="font-mono text-2xs">'+esc(r.gateway)+'</td><td>'+esc(r.device)+'</td><td>'+esc(String(r.distance))+'</td></tr>';
        });
        h += '</tbody></table>';
      }

      // SD-WAN status
      if (ex.sdwan && ex.sdwan.members && ex.sdwan.members.length) {
        h += '<div class="subhead mt-3">SD-WAN</div>';
        h += '<table class="data-table data-table--compact"><thead><tr><th>' + t('interface') + '</th><th>' + t('status_3') + '</th><th>' + t('latency') + '</th><th>' + t('jitter') + '</th><th>' + t('pakketap') + '</th></tr></thead><tbody>';
        ex.sdwan.members.forEach(function(m) {
          var sColor = m.status==='up'||m.status==='alive' ? 'var(--green)' : 'var(--red)';
          var plColor = m.packet_loss > 1 ? 'var(--red)' : 'var(--green)';
          h += '<tr><td class="fw-medium">'+esc(m.interface)+'</td><td class="' + toneClass(sColor) + '">'+esc(m.status||'-')+'</td><td>'+(m.latency?m.latency.toFixed(1)+'ms':'-')+'</td><td>'+(m.jitter?m.jitter.toFixed(1)+'ms':'-')+'</td><td class="' + toneClass(plColor) + '">'+(m.packet_loss?m.packet_loss.toFixed(1)+'%':'0%')+'</td></tr>';
        });
        h += '</tbody></table>';
      }

      // DHCP, DNS, Admins, FortiGuard licenses, Log stats
      h += '<div class="grid grid-auto-md gap-3 mt-3">';

      if (ex.dhcp && ex.dhcp.length) {
        h += '<div class="card p-3"><div class="text-xs fw-semibold mb-1">DHCP ('+ex.dhcp.length+')</div>';
        ex.dhcp.forEach(function(d2){h += '<div class="text-2xs text-muted py-0-5 px-0"><strong>'+esc(d2.interface)+'</strong>: '+esc(d2.range)+'</div>';});
        h += '</div>';
      }
      if (ex.dns && ex.dns.primary) {
        h += '<div class="card p-3"><div class="text-xs fw-semibold mb-1">DNS</div>';
        h += '<div class="text-2xs text-muted">' + t('primaer') + ' <strong>'+esc(ex.dns.primary)+'</strong></div>';
        if (ex.dns.secondary) h += '<div class="text-2xs text-muted">' + t('inf_secondary','Sekundær') + ': '+esc(ex.dns.secondary)+'</div>';
        h += '</div>';
      }
      if (ex.admins && ex.admins.length) {
        h += '<div class="card p-3"><div class="text-xs fw-semibold mb-1">Admin-kontoer ('+ex.admins.length+')</div>';
        ex.admins.forEach(function(a){
          var warns = [];
          if (!a.two_factor) warns.push(t('inf_no_2fa','ingen 2FA'));
          if (!a.trusthost) warns.push(t('inf_no_trusthost','ingen trusthost'));
          var warnHtml = warns.length ? ' <span class="text-warning text-2xs">'+warns.join(', ')+'</span>' : '';
          h += '<div class="text-2xs text-muted py-0-5 px-0"><strong>'+esc(a.name||'-')+'</strong>'+(a.profile?' ('+esc(a.profile)+')':'')+warnHtml+'</div>';
        });
        h += '</div>';
      }
      if (ex.license_expiry && Object.keys(ex.license_expiry).length) {
        h += '<div class="card p-3"><div class="text-xs fw-semibold mb-1">' + t('fortiguard_lisenser') + '</div>';
        Object.keys(ex.license_expiry).forEach(function(k) {
          var lic = ex.license_expiry[k];
          var expDate = lic.expires ? new Date(lic.expires * 1000) : null;
          var daysLeft = expDate ? Math.floor((expDate - new Date()) / 86400000) : null;
          var color = daysLeft === null ? 'var(--text-muted)' : daysLeft < 30 ? 'var(--red)' : daysLeft < 90 ? 'var(--orange)' : 'var(--green)';
          h += '<div class="text-2xs py-0-5 px-0 flex justify-between"><span>'+esc(k)+'</span><span class="' + toneClass(color) + '">'+(expDate?expDate.toLocaleDateString('no-NO'):'—')+'</span></div>';
        });
        h += '</div>';
      }
      if (ex.log_stats && ex.log_stats.total_bytes) {
        var logPct = Number(ex.log_stats.used_pct) || 0;
        var logColor = logPct > 90 ? 'var(--red)' : logPct > 70 ? 'var(--orange)' : 'var(--green)';
        h += '<div class="card p-3"><div class="text-xs fw-semibold mb-1">' + t('logg_lagring') + '</div>';
        h += '<div class="text-md fw-bold ' + toneClass(logColor) + '">'+logPct+'%</div>';
        h += '<div class="text-2xs text-muted">' + t('brukt_2') + '</div>';
        h += '</div>';
      }

      h += '</div>';

      if (dev.last_poll) h += '<div class="text-2xs text-dim mt-2">Sist pollet: '+new Date(dev.last_poll).toLocaleString('no-NO')+'</div>';
      h += '</div>';
    }

    h += '</div>';
    panel.innerHTML = h;
  });
}

// ═══════════════════════════════════════════════════════════════════
// CLAUDE AI INTEGRATION
// ═══════════════════════════════════════════════════════════════════

export async function claudeLoadSaved() {
  var data = await apiFetch('/api/claude/status');
  if (!data) return;
  var dot = document.getElementById('claude-integ-dot');
  var label = document.getElementById('claude-integ-label');
  if (data.available) {
    dot.style.background = 'var(--green)';
    label.textContent = data.model || t('lbl_connected','Connected');
    label.style.color = 'var(--green)';
  } else if (data.api_key_configured) {
    dot.style.background = 'var(--orange)';
    label.textContent = t('lbl_key_saved_sdk_missing','Key saved, but SDK missing');
    label.style.color = 'var(--orange)';
  } else {
    dot.style.background = 'var(--text-dim)';
    label.textContent = t('lbl_not_configured','Not configured');
    label.style.color = 'var(--text-muted)';
  }
}

export function claudeModeChanged() {
  var mode = document.getElementById('claude-mode').value;
  document.getElementById('claude-mode-api').style.display = mode === 'api' ? 'block' : 'none';
  document.getElementById('claude-mode-cli').style.display = mode === 'cli' ? 'block' : 'none';
  if (mode === 'cli') claudeCheckCli();
}

export async function claudeCheckCli() {
  var el = document.getElementById('claude-cli-status');
  el.textContent = t('msg_checking','Checking …');
  var data = await apiFetch('/api/claude/cli-status');
  if (data && data.available) {
    el.innerHTML = '<span class="text-success">✓ Claude CLI funnet · ' + esc(data.version) + '</span>';
  } else {
    el.innerHTML = '<span class="text-danger">✗ ' + esc(data && data.error ? data.error : t('inf_claude_missing','Claude CLI ikke funnet')) + '</span><br><span class="text-xs text-dim">Installer: npm install -g @anthropic-ai/claude-code</span>';
  }
}

export async function claudeSaveSettings() {
  var mode = document.getElementById('claude-mode').value;
  var key = document.getElementById('claude-api-key').value.trim();
  var model = document.getElementById('claude-model').value;
  var msg = document.getElementById('claude-save-msg');
  if (mode === 'api' && !key) { msg.innerHTML = '<span class="text-danger">' + t('err_fill_api_key','Enter API key') + '</span>'; return; }
  var data = await apiFetch('/api/claude/settings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:key, mode:mode, model:model})});
  if (data && data.ok) {
    msg.innerHTML = '<span class="text-success">' + t('lagret_3') + '</span>';
    claudeLoadSaved();
  } else {
    msg.innerHTML = '<span class="text-danger">'+esc(data&&data.error||t('status_error','Error'))+'</span>';
  }
}

export async function claudeTestConnection() {
  var msg = document.getElementById('claude-save-msg');
  msg.textContent = t('msg_testing','Testing...');
  var data = await apiFetch('/api/claude/status');
  if (data && data.available) {
    msg.innerHTML = '<span class="text-success">' + t('lbl_connected','Connected') + ' · '+esc(data.model)+'</span>';
  } else {
    msg.innerHTML = '<span class="text-danger">'+(data && !data.sdk_installed ? t('err_anthropic_not_installed','anthropic package not installed') : t('err_api_key_missing_invalid','API key missing or invalid'))+'</span>';
  }
}

// ═══════════════════════════════════════════════════════════════════
// FORTIGATE REST API INTEGRATION
// ═══════════════════════════════════════════════════════════════════

export async function fgBootstrap() {
  var host = document.getElementById('fg-bootstrap-host').value.trim();
  var hostname = document.getElementById('fg-bootstrap-hostname').value.trim();
  var btn = document.getElementById('btn-fg-bootstrap');
  var status = document.getElementById('fg-bootstrap-status');
  var resultBox = document.getElementById('fg-bootstrap-result');

  if (!host) { showToast(t('angi_fortigate_ip_adresse'), 'warning'); return; }

  btn.disabled = true;
  status.textContent = t('inf_connecting_factory','Kobler til') + ' ' + host + ' ' + t('inf_with_factory_defaults','med fabrikkinnstillinger ...');
  resultBox.style.display = 'none';

  try {
    // Stored for the customer chosen on the card; with none, only shown.
    var bootCustomer = await toolCustomerId();
    var d = await apiFetch('/api/fortigate/bootstrap', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({host: host, hostname: hostname || undefined, customer_id: bootCustomer || undefined})
    });

    if (d && d.ok) {
      status.innerHTML = '<span class="text-success fw-semibold">' + t('ferdig') + '</span>';
      resultBox.style.display = 'block';
      resultBox.innerHTML =
        '<div class="fw-semibold text-ui mb-2 text-success">' + t('fortigate_konfigurert') + '</div>' +
        '<table class="data-table">' +
        '<tr><td class="fw-semibold nowrap">' + t('host_2') + '</td><td class="font-mono">' + esc(d.host) + '</td></tr>' +
        '<tr><td class="fw-semibold nowrap">' + t('admin_passord') + '</td><td><code class="bg-base py-0-5 px-2 rounded-sm select-all text-ui fw-semibold">' + esc(d.admin_password) + '</code></td></tr>' +
        '<tr><td class="fw-semibold nowrap">' + t('api_bruker') + '</td><td class="font-mono">' + esc(d.api_admin) + '</td></tr>' +
        '<tr><td class="fw-semibold nowrap">' + t('api_token_2') + '</td><td><code class="bg-base py-0-5 px-2 rounded-sm select-all text-ui fw-semibold">' + esc(d.api_token) + '</code></td></tr>' +
        '</table>' +
        '<div class="mt-3 flex gap-2">' +
        '<button class="btn btn-primary btn-sm" data-click-handler="fgBootstrapAutoFill" data-host="' + esc(d.host) + '" data-token="' + esc(d.api_token) + '">' + t('fyll_inn_og_lagre') + '</button>' +
        '<button class="btn btn-default btn-sm" data-click-handler="fgCopyApiToken" data-token="' + esc(d.api_token) + '">' + t('kopier_token') + '</button>' +
        '</div>' +
        '<div class="mt-2 text-xs text-success">' + (d.persisted ? t('msg_creds_in_keyring') : t('msg_creds_not_persisted') + (d.persist_error ? ' (' + esc(d.persist_error) + ')' : '') + ' ' + t('msg_save_password_now')) + '</div>';

      showToast(t('fortigate_bootstrap_fullfoert'), 'success', 6000);
    } else {
      status.innerHTML = '<span class="text-danger">' + esc(d && d.error ? d.error : 'Bootstrap feilet') + '</span>';
      if (d && d.steps) {
        status.innerHTML += '<br><span class="text-2xs text-dim">Steg: ' + esc(d.steps.join(' → ')) + '</span>';
      }
      // Show password if it was set (partial success)
      if (d && d.admin_password && d.steps && d.steps.some(function(s) { return s.startsWith('password_set') || s.startsWith('reconnect'); })) {
        resultBox.style.display = 'block';
        var html = '<div class="fw-semibold text-ui mb-2 text-warning">' + t('delvis_fullfoert_passord_ble_satt') + '</div>';
        html += '<table class="data-table">';
        html += '<tr><td class="fw-semibold">' + t('host_2') + '</td><td class="font-mono">' + esc(d.host) + '</td></tr>';
        html += '<tr><td class="fw-semibold">' + t('admin_passord') + '</td><td><code class="bg-base py-0-5 px-2 rounded-sm select-all text-ui fw-semibold">' + esc(d.admin_password) + '</code></td></tr>';
        if (d.api_admin) html += '<tr><td class="fw-semibold">' + t('api_bruker') + '</td><td class="font-mono">' + esc(d.api_admin) + '</td></tr>';
        html += '</table>';
        if (d.raw_output) {
          html += '<div class="mt-2 text-xs text-dim"><strong>' + t('debug_output') + '</strong><pre class="max-h-sm overflow-auto p-2 bg-base border rounded-sm text-2xs mt-1">' + esc(d.raw_output) + '</pre></div>';
        }
        html += '<div class="mt-2 text-xs text-warning">' + t('lagre_passordet_opprett_api_noekkel_manu') + '</div>';
        resultBox.innerHTML = html;
      }
    }
  } catch (e) {
    status.innerHTML = '<span class="text-danger">' + esc(e.message) + '</span>';
  } finally {
    btn.disabled = false;
  }
}

function fgBootstrapAutoFill(host, token) {
  document.getElementById('fg-api-host').value = host;
  document.getElementById('fg-api-token').value = token;
  // Bootstrap hardens admin-sport to 8443 (CIS) — match it in the saved config
  document.getElementById('fg-api-port').value = '8443';
  fgApiSave();
}

// The credentials stored for the customer chosen on the card.
export async function fgDownloadCredentials() {
  var active = await toolCustomerId();
  if (!active) { showToast(t('msg_tool_choose_customer', 'Velg kunden verktøyet skal gjelde, i feltet Kunde over.'), 'warning'); return; }

  try {
    var d = await apiFetch('/api/fortigate/credentials/' + encodeURIComponent(active));
    if (!d || !d.ok) { showToast(t('ingen_lagrede_credentials'), 'warning'); return; }

    var lines = [
      '# FortiGate credentials',
      '# ' + t('inf_hdr_customer','Kunde:').padEnd(14) + (d.customer_name || ''),
      '# Generert:     ' + (d.bootstrapped_at || t('inf_unknown_paren','(ukjent)')),
      '# ' + t('inf_hdr_downloaded','Lastet ned:').padEnd(14) + new Date().toISOString(),
      '#',
      '# ' + t('inf_secret_warning','ADVARSEL: Inneholder hemmeligheter. Slett etter bruk eller lagre kryptert.'),
      '',
      'Host:           ' + (d.host || ''),
      'Port (HTTPS):   ' + (d.port || 8443),
      'Admin URL:      https://' + (d.host || '') + ':' + (d.port || 8443),
      '',
      'Admin user:     ' + (d.admin_user || 'admin'),
      'Admin password: ' + (d.admin_password || t('inf_not_stored','(ikke lagret)')),
      '',
      'API user:       ' + (d.api_user || 'msp_api_admin'),
      'API token:      ' + (d.api_token || t('inf_not_stored','(ikke lagret)')),
      ''
    ];
    var blob = new Blob([lines.join('\n')], {type: 'text/plain;charset=utf-8'});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    var safe = (d.customer_name || 'fortigate').replace(/[^A-Za-z0-9_\-]/g, '_');
    a.href = url;
    a.download = 'fortigate-credentials-' + safe + '.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(t('credentials_lastet_ned'), 'success');
  } catch (e) {
    showToast(e.message || t('inf_creds_failed','Kunne ikke hente credentials'), 'error');
  }
}

export async function fgApiTest() {
  var host = document.getElementById('fg-api-host').value.trim();
  var port = document.getElementById('fg-api-port').value || '443';
  var token = document.getElementById('fg-api-token').value.trim();
  var vdom = document.getElementById('fg-api-vdom').value.trim() || 'root';
  var result = document.getElementById('fg-api-test-result');

  if (!host || !token) { result.innerHTML = '<span class="text-danger">' + t('err_host_token_required','Host and token are required') + '</span>'; return; }
  result.textContent = t('msg_testing','Testing...');

  var data = await apiFetch('/api/fortigate/test', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({host:host, port:parseInt(port), api_token:token, vdom:vdom})});
  if (data && data.ok) {
    var info = data.hostname ? ' · ' + esc(data.hostname) + ' (' + esc(data.firmware || '') + ')' : '';
    result.innerHTML = '<span class="text-success">' + t('lbl_connected','Connected') + '!' + info + '</span>';
    document.getElementById('fg-integ-dot').style.background = 'var(--green)';
    document.getElementById('fg-integ-label').textContent = t('lbl_connected','Connected');
    document.getElementById('fg-integ-label').style.color = 'var(--green)';
  } else {
    result.innerHTML = '<span class="text-danger">' + esc(data && data.error ? data.error : t('err_connection_failed','Connection failed')) + '</span>';
  }
}

export async function fgApiSave() {
  var host = document.getElementById('fg-api-host').value.trim();
  var port = document.getElementById('fg-api-port').value || '443';
  var token = document.getElementById('fg-api-token').value.trim();
  var vdom = document.getElementById('fg-api-vdom').value.trim() || 'root';

  if (!host || !token) { showToast(t('err_host_token_required','Host and token are required'), 'error'); return; }

  // Saved for the customer chosen on the card, the one the form was loaded for.
  var customerId = _fgApiCustomerId;
  if (!customerId) {
    showToast(t('err_select_customer_first','Velg kunden FortiGaten skal lagres for, i feltet Kunde.'), 'error');
    return;
  }
  var data = await apiFetch('/api/fortigate/save/' + encodeURIComponent(customerId), {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({host:host, port:parseInt(port), api_token:token, vdom:vdom})});
  if (data && data.ok) {
    showToast(t('msg_fortigate_config_saved','FortiGate-konfig lagret for {customer}').replace('{customer}', _customerNameById(customerId)), 'success');
    document.getElementById('fg-api-save-msg').innerHTML = '<span class="text-success">' + t('lbl_saved','Saved') + '</span>';
  }
}

// The customer the FortiGate card's form shows and saves to.
var _fgApiCustomerId = null;
registerToolCustomer('fgapi', function() { fgApiLoadSaved(); });

export async function fgApiLoadSaved() {
  renderToolCustomerPickers();
  var customerId = await toolCustomerId();
  _fgApiCustomerId = customerId;
  ['fg-api-host', 'fg-api-token'].forEach(function(id) { var el = document.getElementById(id); if (el) el.value = ''; });
  var portEl = document.getElementById('fg-api-port'); if (portEl) portEl.value = 443;
  var vdomEl = document.getElementById('fg-api-vdom'); if (vdomEl) vdomEl.value = 'root';
  var tokenEl = document.getElementById('fg-api-token'); if (tokenEl) tokenEl.placeholder = t('fortigate_rest_api_token', 'FortiGate REST API token');
  if (!customerId) return;
  var data = await apiFetch('/api/network-devices/' + encodeURIComponent(customerId));
  if (_fgApiCustomerId !== customerId) return;
  if (data && data.fortigate) {
    var fg = data.fortigate;
    document.getElementById('fg-api-host').value = fg.host || '';
    document.getElementById('fg-api-port').value = fg.port || 443;
    document.getElementById('fg-api-vdom').value = fg.vdom || 'root';
    if (fg.has_token) {
      document.getElementById('fg-api-token').placeholder = t('placeholder_token_saved','Token saved — leave blank to keep');
      document.getElementById('fg-integ-dot').style.background = 'var(--blue)';
      document.getElementById('fg-integ-label').textContent = fg.host;
      document.getElementById('fg-integ-label').style.color = 'var(--blue)';
    }
  }
}

// ═══════════════════════════════════════════════════════════════════
// DASHBOARD SUB-TABS
// ═══════════════════════════════════════════════════════════════════

export function switchDashTab(btn, tabId) {
  // Only Oversikt's own tabs: the network and billing pages use the same
  // button class for their tabs, and lost their highlight to this.
  document.querySelectorAll('#view-overview .dash-tab-content').forEach(function(el) { el.hidden = el.id !== tabId; });
  document.querySelectorAll('#view-overview .tab').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
  _syncBottomNav('overview');

  if (tabId === 'dash-alerts') dashLoadAlerts();
}

export async function dashUnifiRefresh() {
  document.querySelectorAll('.unifi-detail-panel').forEach(function(p) { p.remove(); });
  await dashLoadUnifiAll();
}

// The devices the UniFi tab last listed, by row index (dashUnifiDetail).
var _unifiDevices = [];

export async function dashLoadUnifiAll() {
  var el = document.getElementById('dash-unifi-content');
  if (!el) return;
  el.innerHTML = '<div class="loader loader-md"></div>';

  var data = await apiFetch('/api/unifi/all');
  if (!data) { el.innerHTML = '<div class="empty-note">' + t('kunne_ikke_hente_unifi_data') + '</div>'; return; }

  var devices = data.devices || [];
  var summary = data.summary || {};

  if (!devices.length && !summary.configured_customers) {
    el.innerHTML = '<div class="empty-signpost"><p>' + esc(t('inf_no_unifi','Ingen UniFi-enheter konfigurert. Legg dem til per kunde under Administrasjon › Integrasjoner.')) + '</p>' + adminSignpostButton('integrations', 'btn_open_integrations') + '</div>';
    return;
  }

  // KPI cards
  var html = '<div class="grid grid-cols-4 gap-3 mb-4">';
  var kpis = [
    {label:t('inf_devices','Enheter'), value:Number(summary.total_devices)||0, sub:(Number(summary.online)||0)+' online', color:'var(--blue)'},
    {label:'Online', value:Number(summary.online)||0, sub:summary.offline?Number(summary.offline)+' offline':t('inf_all_up','alle oppe'), color:summary.offline?'var(--orange)':'var(--green)'},
    {label:'Klienter', value:Number(summary.total_clients)||0, sub:t('inf_connected_lc','tilkoblet'), color:'var(--purple)'},
    {label:t('inf_customers','Kunder'), value:Number(summary.configured_customers)||0, sub:t('inf_with_unifi','med UniFi'), color:'var(--text-muted)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card kpi-card top-tone ' + toneVar(k.color) + '"><div class="text-xl fw-bold">'+k.value+'</div><div class="text-xs text-muted">'+k.label+'</div><div class="text-2xs text-dim">'+k.sub+'</div></div>';
  });
  html += '</div>';

  // Store globally for detail panel
  _unifiDevices = devices;

  // Device cards
  if (devices.length) {
    html += '<div id="unifi-cards-grid" class="grid grid-auto-lg gap-3">';
    devices.forEach(function(d, idx) {
      var color = d.status === 'online' ? 'var(--green)' : 'var(--red)';
      html += '<div class="card device-card cursor-pointer edge-tone ' + toneVar(color) + '" data-click-handler="dashUnifiDetail" data-index="'+idx+'">';

      // ROW 1 — Header
      html += '<div class="device-card-head">';
      html += '<span class="dot ' + toneClass(color) + '"></span>';
      html += '<strong class="flex-1 text-base ml-2 nowrap overflow-hidden ellipsis">'+esc(d.name||'-')+'</strong>';
      if (d.source === 'site_manager') html += '<span class="badge badge-info shrink-0">' + t('cloud') + '</span>';
      html += '</div>';

      // ROW 2 — Subtitle
      html += '<div class="device-card-sub">'+esc(d.customer_name||d.model_full||d.model||'')+'</div>';

      // ROW 3 — Stats grid (enriched)
      html += '<div class="grid grid-cols-2 gap-1 text-sm text-muted content-start pt-2">';
      html += '<span>' + t('modell') + ' <strong class="text-default">'+esc(d.model||'-')+'</strong></span>';
      html += '<span>FW: '+esc(d.firmware||'-')+'</span>';
      html += '<span>' + t('klienter') + ' <strong>'+(d.clients!=null?Number(d.clients):'-')+'</strong></span>';
      if (d.source === 'site_manager') {
        html += '<span>' + t('enheter') + ' <strong>'+(Number(d.device_count)||0)+'</strong>'+(d.offline_devices?' <span class="text-danger">('+Number(d.offline_devices)+' off)</span>':'')+'</span>';
        html += '<span>Sites: '+(Number(d.site_count)||0)+'</span>';
        if (d.ip) html += '<span>' + t('wan') + ' <code class="text-xs">'+esc(d.ip)+'</code></span>';
        if (d.isp) html += '<span>ISP: '+esc(d.isp)+'</span>';
        if (d.uptime) html += '<span>Uptime: '+_formatUptime(d.uptime)+'</span>';
        // Aggregate alerts from sub_sites
        var cardCrit = 0;
        if (d.sub_sites) d.sub_sites.forEach(function(ss) { cardCrit += Number(ss.critical_notifications)||0; });
        if (cardCrit) html += '<span class="text-danger col-span-full">'+cardCrit+' ' + t('inf_critical_alerts','kritiske varsler') + '</span>';
        if (d.firmware_update) html += '<span class="text-warning col-span-full">⬆ '+esc(d.firmware_update)+'</span>';
      } else {
        html += '<span>Uptime: '+(d.uptime?_formatUptime(d.uptime):'-')+'</span>';
        if (d.upgrade_available) html += '<span class="text-warning col-span-full">⬆ '+esc(d.upgrade_available)+'</span>';
      }
      html += '</div>';

      if (d.last_poll) html += '<div class="text-2xs text-dim mt-2">Pollet: '+new Date(d.last_poll).toLocaleTimeString('no-NO')+'</div>';
      html += '</div>';
    });
    html += '</div>';
  } else {
    html += '<div class="empty-note is-compact">'+Number(summary.configured_customers)+' ' + t('msg_customers_awaiting_data') + '</div>';
  }

  el.innerHTML = html;
  var statusEl = document.getElementById('unifi-live-status');
  if (statusEl) statusEl.textContent = t('msg_last_updated','Sist oppdatert') + ': ' + new Date().toLocaleTimeString('no-NO');
}

function dashUnifiDetail(idx) {
  var d = (_unifiDevices || [])[idx];
  if (!d) return;
  var panelId = 'unifi-detail-' + Number(idx);

  var existing = document.getElementById(panelId);
  if (existing) { existing.remove(); return; }
  document.querySelectorAll('.unifi-detail-panel').forEach(function(p) { p.remove(); });

  var el = document.getElementById('dash-unifi-content');
  var panel = document.createElement('div');
  panel.id = panelId;
  panel.className = 'unifi-detail-panel';
  panel.style.cssText = 'margin-top:16px;margin-bottom:16px;';

  var color = d.status === 'online' ? 'var(--green)' : 'var(--red)';
  var h = '<div class="card p-5 edge-tone ' + toneVar(color) + '">';

  // Header
  h += '<div class="flex justify-between items-center mb-4">';
  h += '<div class="text-md fw-bold">'+esc(d.name||'-');
  if (d.source === 'site_manager') h += ' <span class="badge badge-info align-middle">' + t('cloud') + '</span>';
  h += '</div>';
  h += '<button class="btn btn-ghost btn-sm" data-click-handler="removeElement" data-target="'+panelId+'">'+t('btn_close','Lukk')+'</button>';
  h += '</div>';

  // ── Console info grid ──
  h += '<div class="grid grid-auto-md gap-y-2 gap-x-5 text-ui mb-4">';
  h += '<div><span class="text-muted">' + t('status_3') + '</span> <strong class="' + toneClass(color) + '">'+(d.status==='online'?'Online':'Offline')+'</strong></div>';
  h += '<div><span class="text-muted">' + t('modell') + '</span> <strong>'+esc(d.model_full||d.model||'-')+'</strong></div>';
  h += '<div><span class="text-muted">' + t('firmware_2') + '</span> '+esc(d.firmware||'-')+'</div>';
  if (d.app_version) h += '<div><span class="text-muted">' + t('app_versjon') + '</span> '+esc(d.app_version)+'</div>';
  if (d.ip) h += '<div><span class="text-muted">' + t('wan_ip') + '</span> <code class="text-sm">'+esc(d.ip)+'</code></div>';
  if (d.mac) h += '<div><span class="text-muted">' + t('mac') + '</span> <code class="text-sm">'+esc(d.mac)+'</code></div>';
  if (d.serial) h += '<div><span class="text-muted">' + t('serienr') + '</span> <code class="text-sm">'+esc(d.serial)+'</code></div>';
  if (d.isp) h += '<div><span class="text-muted">' + t('isp') + '</span> '+esc(d.isp)+'</div>';
  if (d.uptime) h += '<div><span class="text-muted">' + t('uptime') + '</span> '+_formatUptime(d.uptime)+'</div>';
  if (d.timezone) h += '<div><span class="text-muted">' + t('tidssone') + '</span> '+esc(d.timezone)+'</div>';
  if (d.release_channel) h += '<div><span class="text-muted">' + t('kanal') + '</span> '+esc(d.release_channel)+'</div>';
  if (d.version) h += '<div><span class="text-muted">' + t('unifi_os') + '</span> '+esc(d.version)+'</div>';
  if (d.hostname) h += '<div><span class="text-muted">' + t('hostname') + '</span> '+esc(d.hostname)+'</div>';
  if (d.internal_ip) h += '<div><span class="text-muted">' + t('intern_ip') + '</span> <code class="text-sm">'+esc(d.internal_ip)+'</code></div>';
  if (d.direct_connect_domain) h += '<div><span class="text-muted">' + t('direct_connect') + '</span> <code class="text-xs">'+esc(d.direct_connect_domain)+'</code></div>';
  if (d.country) h += '<div><span class="text-muted">' + t('land') + '</span> '+esc(d.country)+'</div>';
  if (d.cpu_id) h += '<div><span class="text-muted">' + t('cpu') + '</span> '+esc(d.cpu_id)+'</div>';
  if (d.firmware_update) h += '<div><span class="text-warning">' + t('fw_oppdatering') + '</span> '+esc(d.firmware_update)+'</div>';
  if (d.unadopted_devices) h += '<div><span class="text-warning">' + t('uadopterte_enheter') + '</span> '+Number(d.unadopted_devices)+'</div>';
  if (d.device_error) h += '<div><span class="text-danger">' + t('feilkode') + '</span> '+esc(d.device_error)+'</div>';
  if (d.is_blocked) h += '<div><span class="text-danger fw-semibold">' + t('blokkert') + '</span></div>';
  h += '</div>';

  // ── KPI row ──
  h += '<div class="grid grid-auto-sm gap-2 mb-4">';
  var kpis = [
    {l:t('inf_devices','Enheter'), v:Number(d.device_count)||0, c:'var(--blue)'},
    {l:'Klienter', v:Number(d.clients)||0, c:'var(--purple)'},
    {l:'Sites', v:Number(d.site_count)||0, c:'var(--text-muted)'},
  ];
  if (d.offline_devices) kpis.push({l:'Offline', v:Number(d.offline_devices), c:'var(--red)'});
  kpis.forEach(function(k) {
    h += '<div class="text-center py-3 px-2 bg-input rounded top-tone ' + toneVar(k.c) + '">';
    h += '<div class="text-lg fw-bold">'+k.v+'</div>';
    h += '<div class="text-xs text-muted">'+k.l+'</div></div>';
  });
  h += '</div>';

  // ── Timestamps ──
  if (d.registered || d.last_backup || d.last_connection) {
    h += '<div class="flex gap-4 flex-wrap text-xs text-dim mb-4">';
    if (d.registered) h += '<span>Registrert: '+new Date(d.registered).toLocaleDateString('no-NO')+'</span>';
    if (d.last_backup) h += '<span>' + t('inf_last_backup','Siste backup') + ': '+new Date(d.last_backup).toLocaleString('no-NO')+'</span>';
    if (d.last_connection) h += '<span>' + t('inf_last_connection','Siste tilkobling') + ': '+new Date(d.last_connection).toLocaleString('no-NO')+'</span>';
    h += '</div>';
  }

  // ── Sub-sites table ──
  if (d.sub_sites && d.sub_sites.length) {
    h += '<div class="subhead">Sites ('+d.sub_sites.length+')</div>';
    h += '<div class="overflow-x-auto">';
    h += '<table class="data-table table-wide">';
    h += '<thead><tr class="text-xs">';
    h += '<th>' + t('site_2') + '</th>';
    h += '<th class="text-center">' + t('enheter') + '</th>';
    h += '<th class="text-center">' + t('klienter') + '</th>';
    h += '<th class="text-center">' + t('wifi') + '</th>';
    h += '<th class="text-center">' + t('wan_up') + '</th>';
    h += '<th class="text-center">' + t('gjester') + '</th>';
    h += '<th class="text-center">' + t('offline_2') + '</th>';
    h += '<th class="text-center">' + t('oppd') + '</th>';
    h += '<th class="text-center">WAN</th>';
    h += '<th class="text-center">' + t('varsler_3') + '</th>';
    h += '<th>' + t('gateway_2') + '</th>';
    h += '<th>ISP</th>';
    h += '</tr></thead><tbody>';

    d.sub_sites.forEach(function(s) {
      var warn = s.offline_devices || s.critical_notifications || s.alert_count;
      h += '<tr' + (warn ? ' class="row-danger"' : '') + '>';
      h += '<td class="fw-medium">'+esc(s.name)+'</td>';
      h += '<td class="text-center">'+Number(s.device_count)+'</td>';
      h += '<td class="text-center"><strong>'+Number(s.client_count)+'</strong> <span class="text-2xs text-dim">('+Number(s.wifi_clients)+'W/'+Number(s.wired_clients)+'E)</span></td>';
      h += '<td class="text-center">'+Number(s.wifi_networks)+' SSID</td>';
      var wup = Number(s.wan_uptime_pct)||0;
      var wupColor = wup >= 99 ? 'var(--green)' : wup >= 95 ? 'var(--orange)' : wup > 0 ? 'var(--red)' : 'var(--text-dim)';
      h += '<td class="text-center"><span class="' + toneClass(wupColor) + ' fw-semibold">'+(wup?wup+'%':'-')+'</span></td>';
      h += '<td class="text-center">'+(Number(s.guest_count)||0)+'</td>';
      h += '<td class="text-center">'+(s.offline_devices?'<span class="text-danger fw-semibold">'+Number(s.offline_devices)+'</span>':'0')+'</td>';
      h += '<td class="text-center">'+(s.pending_updates?'<span class="text-warning">'+Number(s.pending_updates)+'</span>':'0')+'</td>';
      h += '<td class="text-center">'+(Number(s.wan_interfaces)||0)+'</td>';
      h += '<td class="text-center">'+(s.critical_notifications?'<span class="text-danger fw-semibold">'+Number(s.critical_notifications)+'</span>':'0')+'</td>';
      var gwText = esc(s.gateway_model||'-');
      if (s.gateway_uptime) gwText += ' <span class="text-2xs text-dim">'+_formatUptime(s.gateway_uptime)+'</span>';
      h += '<td>'+gwText+'</td>';
      h += '<td>'+esc(s.isp||'-')+'</td>';
      h += '</tr>';

      // Detail row
      var details = [];
      if (s.tx_retry_pct) details.push('TX retry: '+(s.tx_retry_pct > 5 ? '<span class="text-warning">'+Number(s.tx_retry_pct)+'%</span>' : Number(s.tx_retry_pct)+'%'));
      if (s.wan_uptime_pct) details.push('WAN uptime: '+Number(s.wan_uptime_pct)+'%');
      if (s.gateway_version) details.push('GW FW: '+esc(s.gateway_version));
      if (s.gateway_mac) details.push('GW MAC: <code class="text-2xs">'+esc(s.gateway_mac)+'</code>');
      if (s.wan_interfaces) details.push('WAN: '+Number(s.wan_interfaces));
      if (s.lan_networks) details.push('LAN: '+Number(s.lan_networks));
      if (s.isp_org) details.push('ISP org: '+esc(s.isp_org));
      if (s.isp_asn) details.push('ASN: '+esc(s.isp_asn));
      if (s.country) details.push('Land: '+esc(s.country));
      if (s.internet_issues && s.internet_issues.length) details.push('<span class="text-warning">'+s.internet_issues.length+' ' + t('inf_network_issues','nettverksproblem(er)') + '</span>');
      if (details.length) {
        h += '<tr class="bg-input">';
        h += '<td colspan="12" class="text-xs text-dim">'+details.join(' · ')+'</td></tr>';
      }
    });
    h += '</tbody></table></div>';

    // Summary bar
    var totalDev=0, totalCli=0, totalOff=0, totalUpd=0, totalCrit=0, avgWanUp=0, wanCount=0;
    d.sub_sites.forEach(function(s) {
      totalDev += Number(s.device_count); totalCli += Number(s.client_count);
      totalOff += Number(s.offline_devices)||0; totalUpd += Number(s.pending_updates)||0;
      totalCrit += Number(s.critical_notifications)||0;
      if (s.wan_uptime_pct) { avgWanUp += Number(s.wan_uptime_pct); wanCount++; }
    });
    if (wanCount) avgWanUp = Math.round(avgWanUp * 10 / wanCount) / 10;

    h += '<div class="flex gap-4 flex-wrap mt-3 py-2 px-3 bg-input rounded text-sm">';
    h += '<span>' + t('totalt') + ' <strong>'+totalDev+'</strong> ' + t('enheter_2') + '</span>';
    h += '<span><strong>'+totalCli+'</strong> ' + t('klienter_2') + '</span>';
    if (avgWanUp) { var wC = avgWanUp>=99?'var(--green)':avgWanUp>=95?'var(--orange)':'var(--red)'; h += '<span>' + t('wan_uptime') + ' <strong class="' + toneClass(wC) + '">'+avgWanUp+'%</strong></span>'; }
    if (totalOff) h += '<span class="text-danger"><strong>'+totalOff+'</strong> ' + t('offline_2') + '</span>';
    if (totalUpd) h += '<span class="text-warning"><strong>'+totalUpd+'</strong> ' + t('ventende_oppdateringer') + '</span>';
    if (totalCrit) h += '<span class="text-danger"><strong>'+totalCrit+'</strong> ' + t('kritiske_varsler') + '</span>';
    h += '</div>';
  }

  // Placeholders for async-loaded sections
  h += '<div id="'+panelId+'-overview" class="mt-4"></div>';
  h += '<div id="'+panelId+'-devices" class="mt-4"></div>';
  h += '<div id="'+panelId+'-isp" class="mt-4"></div>';
  h += '<div id="'+panelId+'-wan" class="mt-4"></div>';

  h += '</div>';
  panel.innerHTML = h;
  el.appendChild(panel);
  panel.scrollIntoView({behavior:'smooth', block:'nearest'});

  // ── Async load: devices, ISP metrics, WAN per site ──
  if (d.source === 'site_manager' && d.id) {
    _loadUnifiSiteOverview(panelId, d.id, d.sub_sites);
    _loadUnifiDevices(panelId, d.id);
    // The ISP endpoint is account-wide. Pass this console's identity so the
    // panel can drop the other customers' sites instead of listing them under
    // whichever customer happens to be open.
    _loadUnifiIspMetrics(panelId, d.id, d.sub_sites);
    if (d.sub_sites && d.sub_sites.length) _loadUnifiWan(panelId, d.sub_sites);
  }
}

async function _loadUnifiDevices(panelId, hostId) {
  var el = document.getElementById(panelId + '-devices');
  if (!el) return;
  el.innerHTML = '<div class="loader my-2"></div>';

  var data = await apiFetch('/api/unifi/sm/devices?host_id=' + hostId);
  if (!data || !data.ok || !data.devices || !data.devices.length) { el.innerHTML = ''; return; }

  var devs = data.devices;

  var h = '<div class="subhead">' + t('inf_devices','Enheter') + ' ('+devs.length+')</div>';
  h += '<div class="overflow-x-auto"><table class="data-table table-wide">';
  h += '<thead><tr class="text-xs">';
  h += '<th>' + t('enhet') + '</th>';
  h += '<th>' + t('modell') + '</th>';
  h += '<th>IP</th>';
  h += '<th class="text-center">' + t('status_3') + '</th>';
  h += '<th>' + t('type_3') + '</th>';
  h += '<th>FW</th>';
  h += '<th>' + t('uptime_2') + '</th>';
  h += '<th>' + t('adoptert') + '</th>';
  h += '<th>' + t('notat') + '</th>';
  h += '</tr></thead><tbody>';

  devs.forEach(function(dv) {
    var c = dv.status === 'online' ? 'var(--green)' : 'var(--red)';
    h += '<tr>';
    h += '<td><strong>'+esc(dv.name||dv.mac||'-')+'</strong>';
    if (dv.is_console) h += ' <span class="badge badge-info">' + t('console') + '</span>';
    h += '</td>';
    h += '<td>'+esc(dv.model||'-')+' <span class="text-2xs text-dim">'+esc(dv.model_full||'')+'</span></td>';
    h += '<td><code class="text-xs">'+esc(dv.ip||'-')+'</code></td>';
    h += '<td class="text-center"><span class="' + toneClass(c) + ' fw-semibold">'+(dv.status==='online'?'●':'○')+'</span></td>';
    h += '<td>'+esc(dv.product_line||'-')+'</td>';
    h += '<td>'+esc(dv.firmware||'-')+(dv.update_available?' <span class="text-warning">⬆ '+esc(dv.update_available)+'</span>':'')+'</td>';
    h += '<td>'+esc(dv.uptime||'-')+'</td>';
    h += '<td>'+(dv.adoption_time?new Date(dv.adoption_time).toLocaleDateString('no-NO'):'-')+'</td>';
    h += '<td class="max-w-sm nowrap overflow-hidden ellipsis text-xs text-dim">'+esc(dv.note||'')+'</td>';
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  el.innerHTML = h;
}

// Renders the per-site rows from /api/unifi/sm/sites-overview. The endpoint
// is account-wide like the ISP one, so it is filtered to this console's sites
// for the same reason: a panel scoped to one customer must not show another's.
async function _loadUnifiSiteOverview(panelId, hostId, subSites) {
  var el = document.getElementById(panelId + '-overview');
  if (!el) return;
  el.innerHTML = '<div class="loader"></div>';

  var data = await apiFetch('/api/unifi/sm/sites-overview');
  if (!data || !data.ok || !data.sites) { el.innerHTML = ''; return; }

  var mine = {};
  if (hostId) mine[hostId] = true;
  (subSites || []).forEach(function(ss) {
    if (ss && (ss.site_id || ss.id)) mine[ss.site_id || ss.id] = true;
  });
  var rows = Object.keys(mine).length
    ? data.sites.filter(function(s) { return mine[s.site_id] || mine[s.host_id]; })
    : data.sites;
  if (!rows.length) { el.innerHTML = ''; return; }

  var h = '<div class="section-title">' + t('lbl_site_overview','Site-oversikt') + ' (' + rows.length + ')</div>';

  rows.forEach(function(s) {
    var d = s.devices || {}, c = s.clients || {}, g = s.gateway || {};
    h += '<div class="site-row">';

    h += '<div class="site-row__head">';
    h += '<strong class="site-row__name">' + esc(s.name || s.site_id || '-') + '</strong>';
    if (g.model) h += '<span class="site-row__model">' + esc(g.model) + '</span>';
    h += '<span class="site-badge site-badge--' + esc(g.ips_severity || 'unknown') + '">'
       + esc(g.ips_label || 'Unknown')
       + (g.ips_rules ? ' \u00b7 ' + Number(g.ips_rules) + ' ' + t('lbl_rules','regler') : '')
       + '</span>';
    h += '</div>';

    h += '<div class="site-row__stats">';
    h += '<span>' + t('inf_devices','Enheter') + ': <strong>' + Number(d.total) + '</strong>'
       + (d.offline ? ' <span class="is-bad">(' + Number(d.offline) + ' offline)</span>' : '') + '</span>';
    h += '<span>' + t('klienter','Klienter') + ': <strong>' + Number(c.total) + '</strong>'
       + (c.guest ? ' <span>(' + Number(c.guest) + ' gjest)</span>' : '') + '</span>';
    if (s.wan_uptime_pct !== null && s.wan_uptime_pct !== undefined) {
      h += '<span>' + t('wan_uptime_2','WAN uptime') + ': <strong class="'
         + (s.wan_uptime_pct < 99 ? 'is-bad' : 'is-ok') + '">' + Number(s.wan_uptime_pct) + '%</strong></span>';
    }
    if (d.pending_update) {
      h += '<span class="is-warn">' + Number(d.pending_update) + ' ' + t('lbl_pending_update','venter oppdatering') + '</span>';
    }
    if (s.isp && s.isp.name) h += '<span>' + esc(s.isp.name) + (s.isp.asn ? ' (AS' + esc(s.isp.asn) + ')' : '') + '</span>';
    h += '</div>';

    (s.wans || []).forEach(function(w) {
      h += '<div class="site-row__wan">' + esc(w.name) + ': ';
      h += (w.external_ip ? '<code>' + esc(w.external_ip) + '</code> ' : '');
      if (w.uptime_pct !== null && w.uptime_pct !== undefined) h += Number(w.uptime_pct) + '% ';
      // "Was down" outranks and suppresses an issue count: they are different
      // conversations, and showing both invites reading the smaller number as
      // the whole story.
      if (w.had_downtime) h += '<span class="is-bad">' + t('lbl_had_downtime','har hatt nedetid') + '</span>';
      else if (w.issue_count) h += '<span class="is-warn">' + Number(w.issue_count) + ' ' + t('lbl_issues','hendelser') + '</span>';
      h += '</div>';
    });

    if (s.findings && s.findings.length) {
      h += '<div class="site-row__findings">';
      s.findings.forEach(function(f) {
        h += '<span class="site-row__finding">' + esc(f) + '</span>';
      });
      h += '</div>';
    }
    h += '</div>';
  });

  el.innerHTML = h;
}

async function _loadUnifiIspMetrics(panelId, hostId, subSites) {
  var el = document.getElementById(panelId + '-isp');
  if (!el) return;
  el.innerHTML = '<div class="loader my-2"></div>';

  // Fetch both: 5m/24h for latest readings + 1h/7d for averages
  var results = await Promise.all([
    apiFetch('/api/unifi/sm/isp-metrics?metric_type=5m&duration=24h'),
    apiFetch('/api/unifi/sm/isp-metrics?metric_type=1h&duration=7d')
  ]);
  var data24h = (results[0] && results[0].ok) ? results[0] : null;
  var data7d = (results[1] && results[1].ok) ? results[1] : null;
  var data = data24h || data7d;
  if (!data || !data.ok || !data.sites || !data.sites.length) { el.innerHTML = ''; return; }

  var h = '<div class="subhead">' + t('isp_ytelse') + '</div>';
  h += '<div class="grid grid-auto-lg gap-3">';

  // Build lookup from 7d data for averages
  var avg7d = {};
  if (data7d && data7d.sites) data7d.sites.forEach(function(s) { avg7d[s.site_id] = s; });

  // /v1/isp-metrics reports every site in the Site Manager account. Without
  // this the panel listed all of them under whichever customer was open — one
  // customer's WAN figures shown on another's page.
  var mine = {};
  if (hostId) mine[hostId] = true;
  (subSites || []).forEach(function(ss) {
    if (ss && (ss.site_id || ss.id)) mine[ss.site_id || ss.id] = true;
  });
  var sitesToRender = Object.keys(mine).length
    ? data.sites.filter(function(s) { return mine[s.site_id]; })
    : data.sites;
  if (!sitesToRender.length) { el.innerHTML = ''; return; }

  sitesToRender.forEach(function(s) {
    var lat = s.latest || {};
    var avg = s.averages || {};
    var weekly = avg7d[s.site_id] || {};
    var weekAvg = weekly.averages || {};

    // A missing value renders as a dash in neutral grey. Formatting null as a
    // number printed "null Mbps"; colouring it printed a red 0% outage on a
    // link the sites table reports at 100%.
    function cell(value, unit, colour) {
      if (value === null || value === undefined) {
        return '<div class="text-center text-dim">-</div>';
      }
      return '<div class="text-center"><span class="fw-semibold ' + toneClass(colour) + '">'+esc(String(value))+esc(unit)+'</span></div>';
    }
    function band(value, warn, bad) {
      if (value === null || value === undefined) return '';
      return value > bad ? 'var(--red)' : value > warn ? 'var(--orange)' : 'var(--green)';
    }
    function uptimeBand(value) {
      if (value === null || value === undefined) return '';
      return value < 99 ? 'var(--red)' : value < 99.9 ? 'var(--orange)' : 'var(--green)';
    }

    h += '<div class="p-3 bg-input rounded">';
    h += '<div class="subhead">'+esc(s.isp || t('lbl_unknown_isp','Ukjent ISP'))+'</div>';
    if (!s.has_readings) {
      h += '<div class="text-sm text-dim">' + t('msg_no_isp_readings','Ingen ISP-målinger for denne siten.') + '</div>';
      h += '</div>';
      return;
    }
    h += '<div class="grid grid-cols-3 gap-2 text-sm">';
    h += '<div class="text-dim text-2xs"></div><div class="text-dim text-2xs text-center">' + t('siste') + '</div><div class="text-dim text-2xs text-center">' + t('snitt_d') + '</div>';
    h += '<div>' + t('download') + '</div>' + cell(lat.download_mbps, ' ' + t('mbps'), '') + '<div class="text-center text-dim">-</div>';
    h += '<div>' + t('upload') + '</div>' + cell(lat.upload_mbps, ' ' + t('mbps'), '') + '<div class="text-center text-dim">-</div>';
    h += '<div>' + t('latency') + '</div>'
       + cell(avg.latency_ms, 'ms', band(avg.latency_ms, 20, 50))
       + cell(weekAvg.latency_ms, 'ms', band(weekAvg.latency_ms, 20, 50));
    h += '<div>' + t('pakketap') + '</div>'
       + cell(avg.packet_loss, '%', band(avg.packet_loss, 0.1, 1))
       + cell(weekAvg.packet_loss, '%', band(weekAvg.packet_loss, 0.1, 1));
    h += '<div>' + t('wan_uptime_2') + '</div>'
       + cell(avg.uptime_pct, '%', uptimeBand(avg.uptime_pct))
       + cell(weekAvg.uptime_pct, '%', uptimeBand(weekAvg.uptime_pct));
    h += '</div>';
    h += '<div class="text-2xs text-dim mt-2">'+Number(s.data_points)+' ' + t('msg_measurements_24h') + ' '+(weekly.data_points?'/ '+Number(weekly.data_points)+' (7d)':'')+'</div>';
    h += '</div>';
  });
  h += '</div>';
  el.innerHTML = h;
}

async function _loadUnifiWan(panelId, subSites) {
  var el = document.getElementById(panelId + '-wan');
  if (!el) return;
  el.innerHTML = '<div class="loader my-2"></div>';

  // Load WAN details for each sub-site in parallel
  var promises = subSites.map(function(s) {
    return apiFetch('/api/unifi/sm/site/' + encodeURIComponent(s.site_id) + '/wan').then(function(d) { return {site: s.name, data: d}; }).catch(function() { return null; });
  });
  var results = await Promise.all(promises);
  results = results.filter(function(r) { return r && r.data && r.data.ok; });
  if (!results.length) { el.innerHTML = ''; return; }

  var h = '<div class="subhead">' + t('wan_gateway_sikkerhet') + '</div>';
  h += '<div class="grid grid-auto-lg gap-3">';

  results.forEach(function(r) {
    var gw = r.data.gateway || {};
    var wans = r.data.wans || [];
    h += '<div class="p-3 bg-input rounded">';
    h += '<div class="subhead">'+esc(r.site)+'</div>';
    // Gateway security
    if (gw.model) {
      h += '<div class="text-sm mb-2">';
      h += '<span class="text-muted">' + t('gateway') + '</span> <strong>'+esc(gw.model)+'</strong>';
      var idsColor = gw.ids_mode === 'off' ? 'var(--red)' : 'var(--green)';
      h += ' · IDS: <span class="' + toneClass(idsColor) + ' fw-semibold">'+esc(gw.ids_mode)+'</span>';
      if (gw.inspection && gw.inspection !== 'off') h += ' · Inspeksjon: <span class="text-success">'+esc(gw.inspection)+'</span>';
      if (gw.ips_rules) h += ' · '+Number(gw.ips_rules)+' IPS-regler';
      h += '</div>';
    }
    // WAN interfaces
    wans.forEach(function(w) {
      h += '<div class="text-xs py-1 px-0 border-t">';
      h += '<strong>'+esc(w.name)+'</strong>';
      if (w.external_ip) h += ' · <code class="text-2xs">'+esc(w.external_ip)+'</code>';
      if (w.isp) h += ' · '+esc(w.isp);
      if (w.isp_org) h += ' ('+esc(w.isp_org)+')';
      if (w.uptime_pct != null) {
        var wuC = w.uptime_pct < 99 ? 'var(--red)' : 'var(--green)';
        h += ' · Uptime: <span class="' + toneClass(wuC) + '">'+Number(w.uptime_pct)+'%</span>';
      }
      if (w.issues && w.issues.length) {
        h += '<div class="text-warning mt-0-5">';
        w.issues.forEach(function(iss) { h += ''+esc(iss)+'<br>'; });
        h += '</div>';
      }
      h += '</div>';
    });
    h += '</div>';
  });
  h += '</div>';
  el.innerHTML = h;
}

function _formatUptime(secs) {
  if (typeof secs !== 'number') return esc(secs);
  var d = Math.floor(secs/86400), h = Math.floor((secs%86400)/3600), m = Math.floor((secs%3600)/60);
  if (d > 0) return d+'d '+h+'t';
  if (h > 0) return h+'t '+m+'m';
  return m+'m';
}

// ═══════════════════════════════════════════════════════════════════
// PENTEST
// ═══════════════════════════════════════════════════════════════════

// Gate the SYN/stealth scan mode by the host's raw-socket capability, mirroring
// the VPN capability gating. FAIL CLOSED: the stealth <option> ships disabled
// and is enabled ONLY when the process affirmatively reports the capability, so
// a failed/blank probe leaves it disabled rather than offering a scan the server
// would refuse anyway (SR-006 review).
export async function loadPentestCapabilities() {
  var warn = document.getElementById('pentest-capability-warning');
  var modeSel = document.getElementById('pentest-scan-mode');
  var stealthOpt = modeSel ? modeSel.querySelector('option[value="stealth"]') : null;

  function disableStealth(reason) {
    if (stealthOpt) {
      stealthOpt.disabled = true;
      if (modeSel.value === 'stealth') modeSel.value = 'fast';
    }
    if (warn) {
      warn.textContent = reason || t('pentest_cap_unknown', 'Kunne ikke fastslå skann-rettigheter; stealth/SYN er avslått.');
      warn.style.display = 'block';
    }
  }

  var data = await apiFetch('/api/pentest/capabilities', {method:'GET'});
  var scan = data && data.scan;
  if (scan && scan.available === true) {
    if (stealthOpt) stealthOpt.disabled = false;
    if (warn) warn.style.display = 'none';
  } else {
    // Unavailable, an error (apiFetch returns null), or an unexpected shape.
    disableStealth(scan ? scan.reason : '');
  }
}

export async function runPentest() {
  var target = document.getElementById('pentest-target').value.trim();
  if (!target) { showToast(t('skriv_inn_et_target'), 'error'); return; }
  var scanType = document.getElementById('pentest-type').value;
  var scanMode = document.getElementById('pentest-scan-mode').value;
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader loader-lg"></div><div class="text-center text-muted text-sm">Scanner ' + esc(target) + '... ' + t('inf_may_take_5min','Dette kan ta opptil 5 minutter.') + '</div>';

  var endpoint = scanType === 'port' ? '/api/pentest/port-scan' : scanType === 'web' ? '/api/pentest/web-scan' : '/api/pentest/full-scan';
  var body = scanType === 'web' ? {url: target} : {target: target, scan_type: scanMode};
  var data = await apiFetch(endpoint, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});

  if (!data || !data.ok) {
    el.innerHTML = '<div class="card p-4 edge-danger"><strong class="text-danger">' + t('feil_2') + '</strong> ' + esc(data && data.error ? data.error : t('inf_unknown_error','Ukjent feil')) + '</div>';
    return;
  }

  _renderPentestResults(data, el, target);
}

// The pentest result on screen, for the KB lookup, exports and follow-up scans.
var _lastPentestData = null;

function _renderPentestResults(data, el, target) {
  var findings = data.findings || [];
  var summary = data.summary || data.finding_summary || {};
  var sevColors = {critical:'var(--red)', high:'var(--orange)', medium:'var(--blue)', low:'var(--text-muted)', info:'var(--blue)'};

  var html = '';

  // KPI cards
  html += '<div class="grid grid-cols-6 gap-2 mb-4">';
  ['critical','high','medium','low','info','total'].forEach(function(sev) {
    var count = Number(summary[sev]) || 0;
    var color = sevColors[sev] || 'var(--text-muted)';
    var label = sev === 'total' ? 'Totalt' : sev.charAt(0).toUpperCase() + sev.slice(1);
    html += '<div class="card kpi-card top-tone ' + toneVar(color) + '"><div class="text-xl fw-bold ' + toneClass(color) + '">'+count+'</div><div class="text-2xs text-muted">'+label+'</div></div>';
  });
  html += '</div>';

  // Network info
  if (data.network && data.network.hosts) {
    html += '<div class="card p-3 mb-3"><div class="subhead">' + t('nettverksskanning') + '</div>';
    html += '<div class="text-xs text-muted">'+Number(data.network.host_count)+' ' + t('msg_hosts_found') + ', '+Number(data.network.total_open_ports)+' ' + t('msg_open_ports') + '</div>';
    data.network.hosts.forEach(function(h) {
      html += '<div class="mt-2 text-sm"><strong>'+esc(h.hostname||h.ip)+'</strong> ('+Number(h.port_count)+' porter)'+(h.os?' · '+esc(h.os):'')+'</div>';
      if (h.ports.length) {
        html += '<table class="data-table data-table--compact mt-1"><thead><tr><th>' + t('port_2') + '</th><th>' + t('tjeneste_3') + '</th><th>' + t('produkt') + '</th><th>' + t('versjon') + '</th></tr></thead><tbody>';
        h.ports.forEach(function(p) {
          html += '<tr><td class="fw-medium">'+esc(p.port)+'/'+esc(p.protocol)+'</td><td>'+esc(p.service)+'</td><td>'+esc(p.product)+'</td><td>'+esc(p.version)+'</td></tr>';
        });
        html += '</tbody></table>';
      }
    });
    html += '</div>';
  }

  // Web info
  if (data.web && data.web.info) {
    var wi = data.web.info;
    html += '<div class="card p-3 mb-3"><div class="subhead">' + t('websjekk') + '</div>';
    html += '<div class="text-xs text-muted">Status: '+Number(wi.status_code)+' | Server: '+esc(wi.server||'-')+' | URL: '+esc(wi.final_url||wi.url)+'</div>';
    html += '</div>';
  }

  // Findings table
  if (findings.length) {
    html += '<div class="subhead">Funn ('+findings.length+')</div>';
    html += '<div class="overflow-x-auto"><table class="data-table data-table--compact"><thead><tr><th class="text-center col-status-sm">' + t('alvor') + '</th><th>' + t('funn') + '</th><th>' + t('detalj') + '</th><th>' + t('remediation') + '</th><th class="col-actions"></th></tr></thead><tbody>';
    findings.forEach(function(f, i) {
      var sc = sevColors[f.severity] || 'var(--text-muted)';
      var rowId = 'pf-' + i;
      html += '<tr>';
      html += '<td class="text-center"><span class="' + badgeClass(sc) + '">'+esc(f.severity)+'</span></td>';
      html += '<td class="fw-medium">'+esc(f.title)+(f.cve?' <span class="text-2xs text-accent">'+esc(f.cve)+'</span>':'')+'</td>';
      html += '<td class="text-2xs text-muted max-w-sm">'+esc(f.detail||'')+'</td>';
      html += '<td class="text-2xs text-muted max-w-sm">'+esc(f.remediation||'')+'</td>';
      html += '<td class="text-right"><button class="btn btn-ghost btn-sm nowrap" data-click-handler="_pentestToggleExplain" data-row-id="'+rowId+'" data-index="'+i+'">'+esc(t('pentest_btn_explain','Explain'))+'</button></td>';
      html += '</tr>';
      // Hidden explainer row, populated on first toggle
      html += '<tr id="'+rowId+'" style="display:none;"><td colspan="5"><div class="bg-input edge-tone ' + toneVar(sc) + ' py-3 px-4 text-xs lh-relaxed"></div></td></tr>';
    });
    html += '</tbody></table></div>';
  } else {
    html += '<div class="text-success text-center p-6">' + t('ingen_saarbarheter_funnet') + '</div>';
  }

  html += '<div class="flex gap-2 mt-4">';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="_pentestReport">' + t('generer_rapport') + '</button>';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="_pentestSave">' + t('lagre_scan') + '</button>';
  html += '</div>';
  html += '<div class="text-2xs text-dim mt-2">Skannet: ' + new Date(data.timestamp).toLocaleString('no-NO') + '</div>';
  el.innerHTML = html;
  _lastPentestData = data;
}

// ── Pentest knowledge base lookup ────────────────────────────────────────────
// Maps a finding to (whyKey, fixKey) i18n keys.
// Title-substring overrides take priority over category mapping.
function _pentestKBLookup(finding) {
  var title = (finding.title || '').toLowerCase();
  var cat = finding.category || '';

  // Specific title overrides (most specific first)
  var titleMap = [
    {needle: 'rest api',                      why: 'kb_title_wp_users_why',    fix: 'kb_title_wp_users_fix'},
    {needle: 'wp-json',                       why: 'kb_title_wp_users_why',    fix: 'kb_title_wp_users_fix'},
    {needle: 'directory listing',             why: 'kb_title_dir_listing_why', fix: 'kb_title_dir_listing_fix'},
    {needle: 'upload-mappe',                  why: 'kb_title_dir_listing_why', fix: 'kb_title_dir_listing_fix'},
    {needle: 'zone transfer',                 why: 'kb_title_axfr_why',        fix: 'kb_title_axfr_fix'},
    {needle: 'axfr',                          why: 'kb_title_axfr_why',        fix: 'kb_title_axfr_fix'},
  ];
  for (var i = 0; i < titleMap.length; i++) {
    if (title.indexOf(titleMap[i].needle) !== -1) {
      return {why: titleMap[i].why, fix: titleMap[i].fix};
    }
  }

  // Category mapping (covers all categories from pentest modules)
  var catMap = {
    'tls_protocol':            ['kb_tls_protocol_why',          'kb_tls_protocol_fix'],
    'tls_cert':                ['kb_tls_cert_why',              'kb_tls_cert_fix'],
    'tls_cipher':              ['kb_tls_cipher_why',            'kb_tls_cipher_fix'],
    'ssl_config':              ['kb_ssl_config_why',            'kb_ssl_config_fix'],
    'certificate':             ['kb_certificate_why',           'kb_certificate_fix'],
    'missing_header':          ['kb_missing_header_why',        'kb_missing_header_fix'],
    'cookie_security':         ['kb_cookie_security_why',       'kb_cookie_security_fix'],
    'info_disclosure':         ['kb_info_disclosure_why',       'kb_info_disclosure_fix'],
    'misconfiguration':        ['kb_misconfiguration_why',      'kb_misconfiguration_fix'],
    'transport_security':      ['kb_transport_security_why',    'kb_transport_security_fix'],
    'dns_security':            ['kb_dns_security_why',          'kb_dns_security_fix'],
    'dns_recon':               ['kb_dns_recon_why',             'kb_dns_recon_fix'],
    'email_security':          ['kb_email_security_why',        'kb_email_security_fix'],
    'subdomain_takeover':      ['kb_subdomain_takeover_why',    'kb_subdomain_takeover_fix'],
    'cms_detection':           ['kb_cms_detection_why',         'kb_cms_detection_fix'],
    'cms_vuln':                ['kb_cms_vuln_why',              'kb_cms_vuln_fix'],
    'default_credential':      ['kb_default_credential_why',    'kb_default_credential_fix'],
    'known_vuln':              ['kb_known_vuln_why',            'kb_known_vuln_fix'],
    'outdated_version':        ['kb_outdated_version_why',      'kb_outdated_version_fix'],
    'smb_exposure':            ['kb_smb_exposure_why',          'kb_smb_exposure_fix'],
    'smb_null_session':        ['kb_smb_null_session_why',      'kb_smb_null_session_fix'],
    'smb_security':            ['kb_smb_security_why',          'kb_smb_security_fix'],
    'smb_users':               ['kb_smb_users_why',             'kb_smb_users_fix'],
    'smb_info':                ['kb_smb_info_why',              'kb_smb_info_fix'],
    'exposed_service':         ['kb_exposed_service_why',       'kb_exposed_service_fix'],
    'unknown_service':         ['kb_unknown_service_why',       'kb_unknown_service_fix'],
    'segmentation_fail':       ['kb_segmentation_fail_why',     'kb_segmentation_fail_fix'],
    'segmentation_unexpected': ['kb_segmentation_unexpected_why','kb_segmentation_unexpected_fix'],
    'segmentation_pass':       ['kb_segmentation_pass_why',     'kb_segmentation_pass_fix'],
    'segmentation_info':       ['kb_segmentation_info_why',     'kb_segmentation_info_fix'],
  };
  if (catMap[cat]) return {why: catMap[cat][0], fix: catMap[cat][1]};
  return {why: 'kb_default_why', fix: 'kb_default_fix'};
}

function _pentestToggleExplain(rowId, idx) {
  var row = document.getElementById(rowId);
  if (!row) return;
  var inner = row.querySelector('div');
  var findings = (_lastPentestData && _lastPentestData.findings) || [];
  var f = findings[idx];
  if (!f) return;

  if (row.style.display === 'none') {
    if (!inner.innerHTML) {
      var kb = _pentestKBLookup(f);
      var whyText = t(kb.why, '');
      var fixText = t(kb.fix, '');
      inner.innerHTML =
        '<div class="fw-semibold text-default mb-1">' + esc(t('pentest_lbl_why','Why is this a problem?')) + '</div>'
        + '<div class="pre-line text-muted mb-3">' + esc(whyText) + '</div>'
        + '<div class="fw-semibold text-default mb-1">' + esc(t('pentest_lbl_how_to_fix','How to fix it')) + '</div>'
        + '<div class="pre-line text-muted font-mono text-2xs">' + esc(fixText) + '</div>';
    }
    row.style.display = '';
  } else {
    row.style.display = 'none';
  }
}

export async function runDnsPentest() {
  var target = document.getElementById('pentest-target').value.trim();
  if (!target) { showToast(t('skriv_inn_et_domene'), 'error'); return; }
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader loader-lg"></div><div class="text-center text-muted text-sm">DNS-sikkerhetsscan: ' + esc(target) + '...</div>';

  var data = await apiFetch('/api/pentest/dns-scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({domain:target})});
  if (!data || !data.ok) {
    el.innerHTML = '<div class="card p-4 edge-danger"><strong class="text-danger">' + t('feil_2') + '</strong> ' + esc(data&&data.error?data.error:t('inf_unknown_error','Ukjent feil')) + '</div>';
    return;
  }

  var findings = data.findings || [];
  var subs = data.subdomains || [];
  var html = '';

  // Summary
  html += '<div class="text-base fw-semibold mb-3">'+esc(t('pentest_dns_heading','DNS-sikkerhet: {domain}').replace('{domain}', target))+'</div>';

  // Email security
  if (data.email_security) {
    var es = data.email_security;
    html += '<div class="card p-3 mb-3"><div class="subhead">'+esc(t('pentest_dns_email_grade','E-postsikkerhet (karakter: {grade})').replace('{grade}', es.grade||'?'))+'</div>';
    html += '<div class="grid grid-cols-4 gap-2 text-xs">';
    ['spf','dkim','dmarc','mx'].forEach(function(k) {
      var c = es[k]||{};
      var color = c.status==='pass'?'var(--green)':c.status==='fail'?'var(--red)':c.status==='warn'?'var(--orange)':'var(--text-muted)';
      html += '<div class="text-center"><div class="fw-semibold ' + toneClass(color) + ' uppercase">'+k+'</div><div class="text-muted text-2xs">'+esc(c.status||'?')+'</div></div>';
    });
    html += '</div></div>';
  }

  // Subdomains
  if (subs.length) {
    html += '<div class="card p-3 mb-3"><div class="subhead">'+esc(t('pentest_dns_subdomains','Oppdagede subdomener ({count})').replace('{count}', String(subs.length)))+'</div>';
    html += '<div class="flex flex-wrap gap-1">';
    subs.forEach(function(s) { html += '<span class="bg-base py-0-5 px-2 rounded-sm text-2xs font-mono">'+esc(s.subdomain)+' → '+esc(s.ips[0]||'')+'</span>'; });
    html += '</div></div>';
  }

  // Findings. _renderPentestResults replaces the element's content, so the
  // e-mail and subdomain summary above goes in front of it afterwards; it
  // used to be built and then dropped, and the scan never showed either.
  _renderPentestResults({ok:true, findings:findings, summary:data.summary, timestamp:new Date().toISOString()}, el, target);
  el.insertAdjacentHTML('afterbegin', html);
}

export async function runCredentialTest() {
  var target = document.getElementById('pentest-target').value.trim();
  if (!target) { showToast(t('skriv_inn_en_host_ip'), 'error'); return; }
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader loader-lg"></div><div class="text-center text-muted text-sm">' + t('inf_testing_default_pw','Tester standard-passord på') + ' ' + esc(target) + '...</div>';

  var data = await apiFetch('/api/pentest/credential-test', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({host:target})});
  if (!data || !data.ok) {
    el.innerHTML = '<div class="card p-4 edge-danger"><strong class="text-danger">' + t('feil_2') + '</strong> ' + esc(data&&data.error?data.error:t('inf_unknown_error','Ukjent feil')) + '</div>';
    return;
  }

  var findings = data.findings || [];
  if (!findings.length) {
    el.innerHTML = '<div class="card p-4 edge-success">✓ ' + t('inf_no_default_pw','Ingen standard-passord funnet på') + ' ' + esc(target) + '</div>';
    return;
  }

  _renderPentestResults({ok:true, findings:findings, summary:{critical:findings.filter(function(f){return f.severity==='critical'}).length, high:findings.filter(function(f){return f.severity==='high'}).length, medium:0, low:0, info:0, total:findings.length}, timestamp:new Date().toISOString()}, el, target);
}

async function _pentestReport() {
  var data = _lastPentestData;
  if (!data || !data.findings || !data.findings.length) { showToast(t('kjoer_en_scan_foerst'), 'error'); return; }
  var target = document.getElementById('pentest-target').value.trim() || 'unknown';

  // Open HTML report in new tab
  var resp = await fetch('/api/pentest/report', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({target:target, findings:data.findings, summary:data.summary||data.finding_summary, format:'html'})
  });
  if (resp.ok) {
    // The report echoes text from the scanned hosts; never parse it as the app.
    openReportWindow(await resp.text(), t('pentest_report_title', 'Pentest report'));
  } else {
    showToast(t('kunne_ikke_generere_rapport'), 'error');
  }
}

async function _pentestSave() {
  var data = _lastPentestData;
  if (!data || !data.findings) { showToast(t('kjoer_en_scan_foerst'), 'error'); return; }
  var target = document.getElementById('pentest-target').value.trim() || 'unknown';
  var r = await apiFetch('/api/pentest/save-scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({target:target, findings:data.findings, summary:data.summary||data.finding_summary, scan_type:'full'})});
  if (r && r.ok) showToast(t('scan_lagret_id') + ' '+r.scan_id+')', 'success');
  else showToast(t('kunne_ikke_lagre'), 'error');
}

export async function runCmsScan() {
  var target = document.getElementById('pentest-target').value.trim();
  if (!target) { showToast(t('skriv_inn_en_url'), 'error'); return; }
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader loader-lg"></div><div class="text-center text-muted text-sm">CMS-skanning: ' + esc(target) + '...</div>';
  var data = await apiFetch('/api/pentest/cms-scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:target})});
  if (!data || !data.ok) { el.innerHTML = '<div class="card p-4 edge-danger">' + t('inf_error_colon','Feil') + ': ' + esc(data&&data.error?data.error:t('inf_unknown','Ukjent')) + '</div>'; return; }
  var cms = data.cms || {};
  var html = '<div class="card p-3 mb-3"><strong>' + t('cms') + '</strong> ' + esc(cms.cms||t('inf_none_detected','Ingen detektert')) + (cms.version ? ' v'+esc(cms.version) : '') + '</div>';
  _renderPentestResults({ok:true, findings:data.findings||[], summary:data.summary, timestamp:new Date().toISOString()}, el, target);
  el.innerHTML = html + el.innerHTML;
  _lastPentestData = data;
}

export async function runSmbEnum() {
  var target = document.getElementById('pentest-target').value.trim();
  if (!target) { showToast(t('skriv_inn_en_ip_hostname'), 'error'); return; }
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader loader-lg"></div><div class="text-center text-muted text-sm">SMB-enumerering: ' + esc(target) + '... ' + t('inf_may_take_60s','(kan ta 60s)') + '</div>';
  var data = await apiFetch('/api/pentest/smb-enum', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({host:target})});
  if (!data || !data.ok) { el.innerHTML = '<div class="card p-4 edge-danger">' + t('inf_error_colon','Feil') + ': ' + esc(data&&data.error?data.error:t('inf_unknown','Ukjent')) + '</div>'; return; }
  _renderPentestResults({ok:true, findings:data.findings||[], summary:data.summary, timestamp:new Date().toISOString()}, el, target);
  _lastPentestData = data;
}

export async function runSegTest() {
  var el = document.getElementById('pentest-results');
  // The customer chosen in the bar above the tests (this tab's current one).
  var custId = await toolCustomerId();
  if (!custId) { showToast(t('velg_en_kunde_med_fortigate'), 'error'); return; }
  el.innerHTML = '<div class="loader loader-lg"></div><div class="text-center text-muted text-sm">' + esc(t('tester_nettverkssegmentering_for_aktiv_kunde').replace('{customer}', _customerNameById(custId))) + '</div>';
  var data = await apiFetch('/api/pentest/segmentation-test', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({customer_id:custId})});
  if (!data || !data.ok) { el.innerHTML = '<div class="card p-4 edge-danger">' + t('inf_error_colon','Feil') + ': ' + esc(data&&data.error?data.error:t('inf_unknown','Ukjent')) + '</div>'; return; }
  var s = data.summary||{};
  var html = '<div class="card p-3 mb-3"><strong>' + t('segmentering') + '</strong> ' + Number(s.pass) + ' OK, ' + Number(s.fail) + ' ' + t('inf_failed_of','feilet av') + ' ' + Number(s.total_tests) + ' tester</div>';
  _renderPentestResults({ok:true, findings:data.findings||[], summary:{critical:s.critical||0,high:s.high||0,medium:s.medium||0,low:0,info:s.total_tests-(s.critical||0)-(s.high||0)-(s.medium||0),total:data.findings.length}, timestamp:new Date().toISOString()}, el, 'segmentering');
  el.innerHTML = html + el.innerHTML;
  _lastPentestData = data;
}

export async function runTlsAudit() {
  var raw = document.getElementById('pentest-target').value.trim();
  if (!raw) { showToast(t('pentest_msg_enter_host_port','Enter a hostname (or host:port)'), 'error'); return; }
  // Strip scheme and path; extract optional :port
  var host = raw.replace(/^https?:\/\//,'').replace(/\/.*$/,'');
  var port = 443;
  var m = host.match(/^([^:]+):(\d+)$/);
  if (m) { host = m[1]; port = parseInt(m[2],10); }
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader loader-lg"></div><div class="text-center text-muted text-sm">' + esc(t('pentest_msg_tls_progress','TLS audit in progress — probing TLS 1.0–1.3...')) + ' (' + esc(host) + ':' + port + ')</div>';
  var data = await apiFetch('/api/pentest/tls-audit', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({host:host, port:port})});
  if (!data || !data.ok) { el.innerHTML = '<div class="card p-4 edge-danger">' + esc(t('pentest_msg_tls_failed','TLS audit failed')) + ': ' + esc(data&&data.error?data.error:t('pentest_msg_unknown_error','Unknown error')) + '</div>'; return; }

  // Render protocol matrix + cert summary above the standard findings list
  var p = data.protocols || {};
  var labelOn = t('pentest_pill_on','ON');
  var labelOff = t('pentest_pill_off','OFF');
  var pill = function(name, ok, goodWhenOn) {
    var good = goodWhenOn ? ok : !ok;
    var color = good ? 'var(--green)' : 'var(--red)';
    var label = ok ? labelOn : labelOff;
    return '<span class="' + badgeClass(color) + ' badge-bordered mr-2">' + esc(name) + ' ' + label + '</span>';
  };
  var cert = data.certificate || {};
  var cipher = data.cipher || {};
  var topHtml = '<div class="card mb-3 p-4">'
    + '<div class="subhead">' + esc(t('pentest_tls_status_header','TLS status')) + ' · ' + esc(host) + ':' + port + '</div>'
    + '<div class="mb-3">'
    + pill('TLS 1.0', !!p['TLSv1.0'], false)
    + pill('TLS 1.1', !!p['TLSv1.1'], false)
    + pill('TLS 1.2', !!p['TLSv1.2'], true)
    + pill('TLS 1.3', !!p['TLSv1.3'], true)
    + '</div>';
  if (cert.subject) {
    topHtml += '<div class="text-xs text-muted lh-relaxed">'
      + '<div><strong>' + esc(t('pentest_lbl_issuer','Issuer')) + ':</strong> ' + esc(cert.issuer && (cert.issuer.commonName || cert.issuer.organizationName) || '—') + '</div>'
      + '<div><strong>' + esc(t('pentest_lbl_expires','Expires')) + ':</strong> ' + esc(cert.not_after || '—') + (cert.days_to_expiry !== undefined ? ' (' + Number(cert.days_to_expiry) + ' ' + esc(t('pentest_lbl_days','days')) + ')' : '') + '</div>'
      + '<div><strong>' + esc(t('pentest_lbl_san','SAN')) + ':</strong> ' + esc((cert.sans || []).slice(0,5).join(', ') || '—') + '</div>'
      + '</div>';
  }
  if (cipher.name) {
    topHtml += '<div class="text-xs text-muted mt-2"><strong>' + esc(t('pentest_lbl_cipher','Cipher')) + ':</strong> ' + esc(cipher.name) + ' (' + Number(cipher.bits) + ' ' + esc(t('pentest_lbl_bit','bit')) + ', ' + esc(cipher.protocol || '') + ')</div>';
  }
  topHtml += '</div>';

  _renderPentestResults({ok:true, findings:data.findings||[], summary:data.summary, timestamp:data.timestamp}, el, host);
  el.innerHTML = topHtml + el.innerHTML;
  _lastPentestData = data;
}

export async function runTakeoverCheck() {
  var raw = document.getElementById('pentest-target').value.trim();
  if (!raw) { showToast(t('pentest_msg_enter_domain','Enter a domain'), 'error'); return; }
  var domain = raw.replace(/^https?:\/\//,'').replace(/\/.*$/,'').replace(/:\d+$/,'');
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader loader-lg"></div>'
    + '<div class="text-center text-muted text-sm">' + esc(t('pentest_msg_takeover_progress','Subdomain takeover check — enumerating subdomains...')) + ' (' + esc(domain) + ')</div>';
  var data = await apiFetch('/api/pentest/takeover-check', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({domain:domain})});
  if (!data || !data.ok) { el.innerHTML = '<div class="card p-4 edge-danger">' + esc(t('pentest_msg_takeover_failed','Takeover check failed')) + ': ' + esc(data&&data.error?data.error:t('pentest_msg_unknown_error','Unknown error')) + '</div>'; return; }

  var s = data.summary || {};
  var topHtml = '<div class="card mb-3 p-3">'
    + '<strong>' + esc(t('pentest_takeover_summary','Takeover check')) + ':</strong> '
    + (Number(data.checked) || 0) + ' ' + esc(t('pentest_subdomains_checked','subdomains checked')) + ' · '
    + '<span class="text-danger">' + (Number(s.critical)||0) + ' ' + esc(t('pentest_sev_critical','critical')) + '</span>, '
    + '<span class="text-warning">' + (Number(s.high)||0) + ' ' + esc(t('pentest_sev_high','high')) + '</span>, '
    + (Number(s.info)||0) + ' ' + esc(t('pentest_sev_info','info'))
    + '</div>';

  if (!data.findings || !data.findings.length) {
    el.innerHTML = topHtml + '<div class="card p-4 text-muted">' + esc(t('pentest_takeover_no_findings','No takeover risk found ')) + '</div>';
  } else {
    _renderPentestResults({ok:true, findings:data.findings, summary:{critical:s.critical||0,high:s.high||0,medium:0,low:0,info:s.info||0,total:data.findings.length}, timestamp:data.timestamp}, el, domain);
    el.innerHTML = topHtml + el.innerHTML;
  }
  _lastPentestData = data;
}

async function dashLoadSites() {
  var el = document.getElementById('unifi-sm-sites-list');
  if (_unifiSites && _unifiSites.length) {
    el.innerHTML = _renderSiteTable(_unifiSites);
    return;
  }
  el.innerHTML = '<div class="loader loader-md"></div>';
  var data = await apiFetch('/api/unifi/site-manager/sites');
  if (!data || !data.sites) {
    el.innerHTML = '<div class="empty-signpost"><p>' + esc(t('inf_no_sites','Ingen siter tilgjengelig. Sett opp UniFi Site Manager under Administrasjon › Integrasjoner.')) + '</p>' + adminSignpostButton('integrations', 'btn_open_integrations') + '</div>';
    return;
  }
  _unifiSites = data.sites;
  el.innerHTML = _renderSiteTable(data.sites);
}

// ═══════════════════════════════════════════════════════════════════
// UNIFI SITE MANAGER INTEGRATION
// ═══════════════════════════════════════════════════════════════════

// State for 2FA flow
var _unifiSm2faToken = '';
var _unifiSm2faCustomerId = '';

// The email/password fields this was written against are not in the card,
// which offers an API key and controller access. Reading .value off the
// missing element threw before the API-key branch could run, so a perfectly
// good key failed with "Cannot read properties of null (reading 'value')".
// Read every field defensively: the account flow — and the 2FA handling below,
// which only applies to it — stays usable if the inputs are ever restored.
// keepWhitespace for secrets: a password may legitimately begin or end with a
// space, so it is the one field that must not be trimmed.
function _unifiSmField(id, keepWhitespace) {
  var el = document.getElementById(id);
  if (!el) return '';
  return keepWhitespace ? el.value : el.value.trim();
}

export async function unifiSmAuth() {
  var apiKey = _unifiSmField('unifi-sm-apikey');
  var email = _unifiSmField('unifi-sm-email');
  var pass = _unifiSmField('unifi-sm-password', true);

  if (!apiKey && (!email || !pass)) { showToast(t('err_fill_api_key_or_email','Enter API key or email/password'),'error'); return; }

  var btn = document.getElementById('unifi-sm-auth-btn');
  var result = document.getElementById('unifi-sm-auth-result');
  btn.disabled = true; btn.textContent = t('vpn_connecting','Connecting...');
  result.textContent = '';

  var body = apiKey ? {api_key: apiKey} : {username: email, password: pass};
  var data = await apiFetch('/api/unifi/site-manager/auth', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  btn.disabled = false; btn.textContent = t('lbl_connect','Koble til');

  if (data && data.ok) {
    _unifiSmAuthSuccess();
  } else if (data && data.requires_2fa) {
    // Show 2FA input
    _unifiSm2faToken = data.session_token || '';
    _unifiSm2faCustomerId = data.customer_id || '';
    _unifiSmShow2fa();
  } else {
    result.innerHTML = '<span class="text-danger">'+esc(data && data.error ? data.error : t('err_connection_failed','Tilkobling feilet'))+'</span>';
  }
}

function _unifiSmShow2fa() {
  var result = document.getElementById('unifi-sm-auth-result');
  result.innerHTML =
    '<div class="mt-2">' +
      '<label class="field-label">' + t('lbl_2fa_required','2FA-kode påkrevd') + '</label>' +
      '<div class="flex gap-2 mt-1">' +
        '<input id="unifi-sm-2fa-code" type="text" inputmode="numeric" pattern="[0-9]*" ' +
          'maxlength="6" placeholder="123456" autocomplete="one-time-code" ' +
          'class="field-input input-short code-input">' +
        '<button id="unifi-sm-2fa-btn" class="btn btn-primary" data-click-handler="unifiSmVerify2fa">' +
          t('btn_verify','Verifiser') +
        '</button>' +
      '</div>' +
      '<div id="unifi-sm-2fa-error" class="mt-1"></div>' +
    '</div>';
  var codeInput = document.getElementById('unifi-sm-2fa-code');
  if (codeInput) {
    codeInput.focus();
    codeInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') unifiSmVerify2fa();
    });
  }
}

async function unifiSmVerify2fa() {
  var code = document.getElementById('unifi-sm-2fa-code').value.trim();
  if (!code || code.length < 6) {
    document.getElementById('unifi-sm-2fa-error').innerHTML =
      '<span class="text-danger">' + t('err_2fa_enter_code','Skriv inn 6-sifret 2FA-kode') + '</span>';
    return;
  }

  var btn = document.getElementById('unifi-sm-2fa-btn');
  btn.disabled = true; btn.textContent = t('vpn_connecting','Connecting...');
  document.getElementById('unifi-sm-2fa-error').textContent = '';

  var data = await apiFetch('/api/unifi/site-manager/verify-2fa', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      session_token: _unifiSm2faToken,
      code: code,
      customer_id: _unifiSm2faCustomerId || undefined,
    }),
  });

  btn.disabled = false; btn.textContent = t('btn_verify','Verifiser');

  if (data && data.ok) {
    _unifiSmAuthSuccess();
  } else {
    document.getElementById('unifi-sm-2fa-error').innerHTML =
      '<span class="text-danger">' + esc(data && data.error ? data.error : t('err_2fa_failed','2FA-verifisering feilet')) + '</span>';
    // Clear and re-focus for retry
    var codeInput = document.getElementById('unifi-sm-2fa-code');
    if (codeInput) { codeInput.value = ''; codeInput.focus(); }
  }
}

function _unifiSmAuthSuccess() {
  var result = document.getElementById('unifi-sm-auth-result');
  result.innerHTML = '<span class="text-success">' + t('lbl_connected','Tilkoblet') + '!</span>';
  document.getElementById('unifi-sm-integ-dot').style.background = 'var(--green)';
  document.getElementById('unifi-sm-integ-label').textContent = t('lbl_connected','Tilkoblet');
  document.getElementById('unifi-sm-integ-label').style.color = 'var(--green)';
  _unifiSm2faToken = '';
  _unifiSm2faCustomerId = '';
  unifiSmLoadSites();
  // Coverage does not depend on the cloud key — it reads stored controller
  // logins — but this is the moment the operator is looking at UniFi access,
  // which is when "these customers still need a login" is worth reading.
  unifiSmLoadCoverage();
}

export async function unifiSmTestController() {
  var host = document.getElementById('unifi-sm-ctrl-host').value.trim();
  var user = document.getElementById('unifi-sm-ctrl-user').value.trim();
  var pass = document.getElementById('unifi-sm-ctrl-pass').value;
  var result = document.getElementById('unifi-sm-ctrl-result');
  if (!host || !user || !pass) { result.innerHTML = '<span class="text-danger">' + t('err_fill_all_fields','Fill in all fields') + '</span>'; return; }
  result.textContent = t('msg_testing','Testing...');
  var data = await apiFetch('/api/unifi/test', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({host:host,username:user,password:pass,is_unifi_os:true})});
  if (data && data.ok) {
    result.innerHTML = '<span class="text-success">' + t('lbl_connected','Connected') + '! '+( data.sites ? esc(data.sites)+' ' + t('lbl_sites','sites') : '')+'</span>';
  } else {
    result.innerHTML = '<span class="text-danger">'+esc(data&&data.error?data.error:'Tilkobling feilet')+'</span>';
  }
}

export async function unifiSmSaveController() {
  var host = document.getElementById('unifi-sm-ctrl-host').value.trim();
  var user = document.getElementById('unifi-sm-ctrl-user').value.trim();
  var pass = document.getElementById('unifi-sm-ctrl-pass').value;
  if (!host || !user || !pass) { showToast(t('err_fill_all_fields','Fill in all fields'),'error'); return; }
  var data = await apiFetch('/api/settings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    unifi_controller_host: host,
    unifi_controller_username: user,
    unifi_controller_password: pass,
  })});
  if (data && data.ok) showToast(t('msg_controller_access_saved','Controller access saved'),'success');
}

export async function unifiSmSave() {
  var apiKey = document.getElementById('unifi-sm-apikey').value.trim();
  if (!apiKey) { showToast(t('err_fill_api_key_first','Enter API key first'),'error'); return; }
  var data = await apiFetch('/api/settings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({unifi_site_manager_api_key: apiKey})});
  if (data && data.ok) { showToast(t('msg_api_key_saved','API key saved'),'success'); }
}

// Load saved UniFi SM key when integrations view opens.
//
// Populates the field only. The card's dot and label belong to the setStatus
// block in app.js that owns every other integration's status — painting them
// here as well made two writers of one value, and whichever ran last won.
export async function unifiSmLoadSaved() {
  var data = await apiFetch('/api/settings');
  if (data && data.unifi_site_manager_api_key) {
    var el = document.getElementById('unifi-sm-apikey');
    if (el) { el.value = data.unifi_site_manager_api_key; el.type = 'password'; }
  }
}

var _unifiSites = []; // cache for use in dashboard

// The cloud key answers for the whole account but stops at counts — it has no
// clients endpoint, and the Network API behind a console is not reachable
// through it. Everything past that needs a controller login stored against the
// customer, and this is the only place that says where one is missing.
export async function unifiSmLoadCoverage() {
  var list = document.getElementById('unifi-sm-coverage-list');
  if (!list) return;
  list.innerHTML = '<div class="loader"></div>';

  var data = await apiFetch('/api/unifi/controller-coverage');
  if (!data || !data.ok) { list.innerHTML = ''; return; }

  var LABEL = {
    full: t('lbl_access_full','Full tilgang'),
    host_only: t('lbl_access_needs_login','Mangler innlogging'),
    none: t('lbl_access_none','Ingen UniFi'),
    direct: t('lbl_access_direct','Direkte enheter')
  };

  var h = '<div class="sm-coverage__summary">'
        + Number(data.with_full_access) + ' ' + t('lbl_of','av') + ' ' + Number(data.total) + ' '
        + t('lbl_with_full_access','med full tilgang')
        + (data.needs_credentials
            ? ' \u00b7 <strong>' + Number(data.needs_credentials) + ' ' + t('lbl_needs_login_short','mangler innlogging') + '</strong>'
            : '')
        + '</div><div class="sm-coverage__list">';

  (data.customers || []).forEach(function(c) {
    h += '<div class="sm-coverage__row">';
    h += '<span class="sm-coverage__name">' + esc(c.name || c.customer_id) + '</span>';
    h += '<span class="sm-coverage__state--' + esc(c.state) + '">' + esc(LABEL[c.state] || c.state) + '</span>';
    if (c.reason) h += '<span class="sm-coverage__reason">' + esc(c.reason) + '</span>';
    h += '</div>';
  });

  list.innerHTML = h + '</div>';
}

export async function unifiSmLoadSites() {
  var container = document.getElementById('unifi-sm-sites');
  var list = document.getElementById('unifi-sm-sites-list');
  container.style.display = 'block';
  list.innerHTML = '<div class="loader mx-auto my-2"></div>';

  var data = await apiFetch('/api/unifi/site-manager/sites');
  if (!data || !data.sites) { list.innerHTML = '<span class="text-muted text-sm">' + t('kunne_ikke_hente_siter') + '</span>'; return; }

  _unifiSites = data.sites;
  var sites = data.sites;
  if (!sites.length) { list.innerHTML = '<span class="text-muted text-sm">' + t('ingen_siter_funnet') + '</span>'; return; }

  list.innerHTML = _renderSiteTable(sites);
}

export function _renderSiteTable(sites) {
  // Split into multi-site controllers (ours) and standalone consoles
  var multiSite = sites.filter(function(s) { return s.sub_sites && s.sub_sites.length > 1; });
  var standalone = sites.filter(function(s) { return !s.sub_sites || s.sub_sites.length <= 1; });

  var html = '';

  // Render multi-site controllers with their sub-sites expanded
  multiSite.forEach(function(ctrl, ctrlIdx) {
    var ctrlStatus = ctrl.status === 'online' ? 'var(--green)' : 'var(--red)';
    // Controller banner
    html += '<div class="site-controller mb-4" data-click-handler="showSiteDetail" data-index="'+sites.indexOf(ctrl)+'">';
    html += '<div class="flex items-center gap-3">';
    html += '<span class="dot dot-lg ' + toneClass(ctrlStatus) + '"></span>';
    html += '<strong class="text-md">'+esc(ctrl.name)+'</strong>';
    html += '<span class="text-sm text-muted ml-1">'+ctrl.sub_sites.length+' siter · '+esc(ctrl.model||'Cloud Controller')+'</span>';
    html += '<span class="ml-auto text-sm text-muted">WAN: '+esc(ctrl.wan_ip||'-')+'</span>';
    html += '</div></div>';

    // Sub-sites as cards (clickable)
    html += '<div class="card-grid card-grid--sites grid grid-auto-lg gap-3 auto-rows-fr mb-6">';
    ctrl.sub_sites.forEach(function(sub, subIdx) {
      var borderColor = sub.offline_devices > 0 ? 'var(--orange)' : sub.device_count > 0 ? 'var(--green)' : 'var(--text-dim)';
      // 2-row grid: 24px name | 1fr stats
      html += '<div class="card device-card is-short cursor-pointer edge-tone ' + toneVar(borderColor) + '" data-click-handler="showSubSiteDetail" data-index="'+sites.indexOf(ctrl)+'" data-sub-index="'+subIdx+'">';

      // ROW 1: name + badges (24px)
      html += '<div class="device-card-head">';
      html += '<strong class="text-ui nowrap overflow-hidden ellipsis flex-1 min-w-0" title="'+esc(sub.name)+'">'+esc(sub.name)+'</strong>';
      if (sub.offline_devices > 0) html += '<span class="text-2xs text-danger fw-semibold nowrap shrink-0 ml-2">'+Number(sub.offline_devices)+' offline</span>';
      if (sub.critical_notifications > 0) html += '<span class="text-2xs text-warning fw-semibold nowrap shrink-0 ml-2">'+Number(sub.critical_notifications)+' ' + t('inf_alert_sg','varsel') + '</span>';
      html += '</div>';

      // ROW 2: stats (1fr)
      html += '<div class="flex gap-3 text-sm text-muted items-start pt-1">';
      html += '<span>' + t('lbl_devices','Devices') + ': <strong class="text-default">'+Number(sub.device_count)+'</strong></span>';
      html += '<span>' + t('lbl_clients','Clients') + ': '+(Number(sub.wifi_clients)+Number(sub.wired_clients))+'</span>';
      html += '<span>SSID: '+(Number(sub.wifi_networks)||0)+'</span>';
      html += '<span>VLAN: '+(Number(sub.lan_networks)||0)+'</span>';
      html += '</div>';
      html += '</div>';
    });
    html += '</div>';
  });

  // Standalone consoles header
  if (standalone.length && multiSite.length) {
    html += '<div class="text-ui fw-semibold text-muted mb-3 pb-2 border-b">Selvstendige konsoller ('+standalone.length+')</div>';
  }

  // Standalone console cards
  if (standalone.length) {
    html += '<div class="grid grid-auto-lg gap-3 auto-rows-fr">';
    standalone.forEach(function(s) {
      var idx = sites.indexOf(s);
      var statusColor = s.status === 'online' ? 'var(--green)' : 'var(--red)';
      var borderColor = s.offline_devices > 0 ? 'var(--orange)' : s.status === 'online' ? 'var(--green)' : 'var(--red)';
      // 3-row grid: 24px name | 20px WAN | 1fr stats
      html += '<div class="card device-card cursor-pointer edge-tone ' + toneVar(borderColor) + '" data-click-handler="showSiteDetail" data-index="'+idx+'">';

      // ROW 1: name + dot (24px)
      html += '<div class="device-card-head">';
      html += '<strong class="text-base nowrap overflow-hidden ellipsis flex-1 min-w-0" title="'+esc(s.name||'')+'">'+esc(s.name||t('lbl_unknown','Unknown'))+'</strong>';
      html += '<span class="dot ' + toneClass(statusColor) + ' ml-2"></span>';
      html += '</div>';

      // ROW 2: WAN IP (20px)
      html += '<div class="device-card-sub">' + t('wan') + ' <strong class="text-default">'+esc(s.wan_ip||'-')+'</strong></div>';

      // ROW 3: stats grid (1fr) — ALWAYS 6 fields
      html += '<div class="grid grid-cols-3 gap-1 text-sm text-muted content-start pt-2">';
      html += '<span>' + t('lbl_devices','Devices') + ': <strong>'+(Number(s.device_count)||0)+'</strong>'+(s.offline_devices>0?' <span class="text-danger">('+Number(s.offline_devices)+'⬇)</span>':'')+'</span>';
      html += '<span>' + t('lbl_clients','Clients') + ': '+(Number(s.client_count)||0)+'</span>';
      html += '<span>' + t('lbl_model','Model') + ': '+esc(s.model||'-')+'</span>';
      html += '<span>ISP: '+esc(s.isp||'-')+'</span>';
      html += '<span>FW: '+esc(s.firmware||'-')+'</span>';
      html += '<span>SSID: '+esc(s.wifi_networks||s.ssid_count||'-')+'</span>';
      html += '</div>';

      html += '</div>';
    });
    html += '</div>';
  }

  return html;
}

function showSubSiteDetail(hostIdx, subIdx) {
  var host = _unifiSites[hostIdx];
  if (!host || !host.sub_sites) return;
  var s = host.sub_sites[subIdx];
  if (!s) return;

  var el = document.getElementById('unifi-sm-sites-list');
  var html = '<div class="max-w-md">';
  html += '<div class="flex items-center gap-3 mb-4">';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="dashLoadSites">' + t('tilbake') + '</button>';
  html += '<h3 class="text-md fw-bold m-0">'+esc(s.name)+'</h3>';
  html += '<span class="text-sm text-muted">' + t('inf_part_of','del av') + ' '+esc(host.name)+'</span>';
  html += '</div>';

  // Status cards row
  var cards = [
    {label:t('lbl_devices','Devices'), value:Number(s.device_count), sub: (Number(s.wifi_devices)||0)+' AP, '+(Number(s.wired_devices)||0)+' '+t('lbl_switch','switch')+(s.gateway_devices?' , '+Number(s.gateway_devices)+' gateway':''), color:'var(--blue)'},
    {label:t('lbl_clients','Clients'), value:Number(s.client_count), sub: (Number(s.wifi_clients)||0)+' '+t('lbl_wireless_short','wireless')+', '+(Number(s.wired_clients)||0)+' '+t('lbl_wired_short','wired'), color:'var(--green)'},
    {label:t('lbl_guests','Guests'), value:Number(s.guest_count), sub:'', color:'var(--purple)'},
    {label:t('lbl_wifi_networks','WiFi networks'), value:Number(s.wifi_networks)||0, sub:'', color:'var(--orange)'},
    {label:t('lbl_networks_vlan','Networks/VLAN'), value:Number(s.lan_networks)||0, sub:'', color:'var(--blue)'},
  ];
  html += '<div class="card-grid card-grid--kpi grid grid-cols-5 gap-3 auto-rows-fr mb-4">';
  cards.forEach(function(c) {
    html += '<div class="card kpi-card top-tone ' + toneVar(c.color) + '">';
    html += '<div class="text-xl fw-bold text-default">'+c.value+'</div>';
    html += '<div class="text-xs text-muted fw-semibold">'+c.label+'</div>';
    if (c.sub) html += '<div class="text-2xs text-dim mt-0-5">'+c.sub+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // Detail sections
  html += '<div class="grid grid-cols-2 gap-3 mb-4">';

  // Enheter-boks
  html += '<div class="card p-4">';
  html += '<div class="subhead">' + t('enheter') + '</div>';
  html += '<table class="w-full text-sm">';
  html += '<tr class="border-b"><td class="p-2 text-muted">' + t('wifi_ap_er') + '</td><td class="p-2 text-right">'+(Number(s.wifi_devices)||0)+'</td></tr>';
  html += '<tr class="border-b"><td class="p-2 text-muted">' + t('svitsjer_kabel') + '</td><td class="p-2 text-right">'+(Number(s.wired_devices)||0)+'</td></tr>';
  if (s.gateway_devices) html += '<tr class="border-b"><td class="p-2 text-muted">' + t('gateway_3') + '</td><td class="p-2 text-right">'+Number(s.gateway_devices)+'</td></tr>';
  html += '<tr class="fw-semibold"><td class="p-2">' + t('totalt') + '</td><td class="p-2 text-right">'+Number(s.device_count)+'</td></tr>';
  html += '</table></div>';

  // Klienter-boks
  html += '<div class="card p-4">';
  html += '<div class="subhead">' + t('lbl_clients','Clients') + '</div>';
  html += '<table class="w-full text-sm">';
  html += '<tr class="border-b"><td class="p-2 text-muted">' + t('lbl_wireless','Wireless') + '</td><td class="p-2 text-right">'+(Number(s.wifi_clients)||0)+'</td></tr>';
  html += '<tr class="border-b"><td class="p-2 text-muted">' + t('lbl_wired','Wired') + '</td><td class="p-2 text-right">'+(Number(s.wired_clients)||0)+'</td></tr>';
  html += '<tr class="border-b"><td class="p-2 text-muted">' + t('lbl_guests','Guests') + '</td><td class="p-2 text-right">'+(Number(s.guest_count)||0)+'</td></tr>';
  html += '<tr class="fw-semibold"><td class="p-2">' + t('totalt') + '</td><td class="p-2 text-right">'+((Number(s.wifi_clients)||0)+(Number(s.wired_clients)||0))+'</td></tr>';
  html += '</table></div>';

  html += '</div>';  // grid end

  // Status & helsetabell
  html += '<div class="card p-4">';
  html += '<div class="subhead mb-3">' + t('status_3') + '</div>';
  html += '<table class="w-full text-ui">';
  var rows = [];

  // Offline
  if (s.offline_devices > 0) {
    rows.push([t('inf_offline_devices','Offline enheter'), '<span class="text-danger fw-semibold">'+Number(s.offline_devices)+'</span> ('+(Number(s.offline_wifi)||0)+' WiFi, '+(Number(s.offline_wired)||0)+' kabel)']);
  } else {
    rows.push([t('inf_offline_devices','Offline enheter'), '<span class="text-success">' + t('ingen_alt_online') + '</span>']);
  }

  // Updates
  if (s.pending_updates > 0) {
    rows.push([t('inf_pending_updates','Ventende oppdateringer'), '<span class="text-warning fw-semibold">'+Number(s.pending_updates)+' ' + t('inf_devices_paren','enhet(er)') + '</span>']);
  } else {
    rows.push(['Firmware', '<span class="text-success">' + t('alt_oppdatert') + '</span>']);
  }

  // Alerts
  if (s.critical_notifications > 0) {
    rows.push([t('lbl_critical_alerts','Critical alerts'), '<span class="text-danger fw-semibold">'+Number(s.critical_notifications)+'</span>']);
  }

  // WiFi health
  if (s.tx_retry_pct > 0) {
    var retryColor = s.tx_retry_pct > 10 ? 'var(--red)' : s.tx_retry_pct > 5 ? 'var(--orange)' : 'var(--green)';
    rows.push(['WiFi TX Retry', '<span class="' + toneClass(retryColor) + ' fw-semibold">'+Number(s.tx_retry_pct)+'%</span>' + (s.tx_retry_pct > 10 ? ' · ' + t('lbl_high_check_interference','high, check interference/placement') : s.tx_retry_pct > 5 ? ' · ' + t('lbl_moderate','moderate') : ' · ' + t('lbl_good','good'))]);
  }

  // Infra
  rows.push(['', '']);
  rows.push(['WiFi-nettverk (SSID)', (Number(s.wifi_networks)||0) + ' stk']);
  rows.push(['Nettverk / VLAN', (Number(s.lan_networks)||0) + ' stk']);
  if (s.gateway_model) rows.push(['Gateway', esc(s.gateway_model)]);
  if (s.isp) rows.push(['ISP', esc(s.isp)]);
  rows.push(['Tidssone', esc(s.timezone || '-')]);

  rows.forEach(function(r) {
    if (r[0] === '' && r[1] === '') {
      html += '<tr><td colspan="2" class="p-2 border-b"></td></tr>';
    } else {
      html += '<tr class="border-b"><td class="kv-key">'+r[0]+'</td><td class="p-2">'+r[1]+'</td></tr>';
    }
  });
  html += '</table></div>';

  // Placeholder for async-loaded data (devices, WAN, ISP)
  html += '<div id="subsite-devices" class="mt-4"><div class="loader mx-auto my-2"></div></div>';
  html += '<div id="subsite-wan" class="mt-4"></div>';

  // Live client/WiFi data section — tries to match site to a customer
  html += '<div id="subsite-live-data" class="mt-4"></div>';
  html += '</div>';

  if (el) el.innerHTML = html;

  // Try to load live UniFi data by matching site name to a customer
  _loadSubSiteLiveData(s.name);

  // Load devices — only works for standalone consoles, not cloud controllers
  if (host.type !== 'network-server') {
    _loadSubSiteDevices(host, s);
  } else {
    // For cloud controllers, show device type breakdown instead of empty table
    var devEl = document.getElementById('subsite-devices');
    if (devEl && s.device_count > 0) {
      var dhtml = '<div class="card p-4">';
      dhtml += '<div class="subhead mb-3">' + t('inf_devices','Enheter') + ' ('+Number(s.device_count)+')</div>';
      dhtml += '<div class="grid grid-auto-sm gap-2">';
      var types = [
        {label:'WiFi AP', count:Number(s.wifi_devices)||0, icon:''},
        {label:'Svitsj/kabel', count:Number(s.wired_devices)||0, icon:''},
        {label:'Gateway', count:Number(s.gateway_devices)||0, icon:''},
      ];
      types.forEach(function(t) {
        if (t.count > 0) {
          dhtml += '<div class="kpi">';
          dhtml += '<div class="text-lg">'+t.icon+'</div>';
          dhtml += '<div class="text-lg fw-bold">'+t.count+'</div>';
          dhtml += '<div class="text-xs text-muted">'+t.label+'</div>';
          dhtml += '</div>';
        }
      });
      dhtml += '</div>';
      if (s.offline_devices > 0) {
        dhtml += '<div class="mt-2 text-sm text-danger">'+Number(s.offline_devices)+' offline ('+(Number(s.offline_wifi)||0)+' WiFi, '+(Number(s.offline_wired)||0)+' ' + t('lbl_wired_short','wired') + ')</div>';
      }
      dhtml += '<div class="mt-2 text-xs text-dim">' + t('msg_device_list_requires_api_key','Detailed device list requires Organization API key (Connector API)') + '</div>';
      dhtml += '</div>';
      devEl.innerHTML = dhtml;
    } else if (devEl) {
      devEl.innerHTML = '';
    }
  }
  // Load WAN details for this site
  _loadSubSiteWan(s);
  return; // prevent fall-through to the old closing
}

async function _loadSubSiteLiveData(siteName) {
  var el = document.getElementById('subsite-live-data');
  if (!el) return;

  // Try to match site name to a customer with UniFi configured
  if (!_overviewData || !_overviewData.customers) {
    try {
      var ov = await apiFetch('/api/dashboard/overview');
      if (ov) setOverviewData({customers: ov.customers || []});
    } catch(e) {}
  }
  if (!_overviewData || !_overviewData.customers) return;

  // Find customer by matching site name (fuzzy — contains)
  var matched = null;
  var sLower = siteName.toLowerCase().replace(/[^a-z0-9]/g, '');
  _overviewData.customers.forEach(function(c) {
    var cLower = (c.customer_name||'').toLowerCase().replace(/[^a-z0-9]/g, '');
    if (cLower && sLower && (cLower.indexOf(sLower) >= 0 || sLower.indexOf(cLower) >= 0)) {
      matched = c;
    }
  });

  if (!matched) {
    el.innerHTML = '';
    return;
  }

  var cid = matched.customer_id || matched._id;
  el.innerHTML = '<div class="card p-4 edge-accent"><div class="subhead">'+t('hdr_live_data','Live data')+' · '+esc(matched.customer_name)+'</div><div class="loader"></div></div>';

  // Fetch clients and WiFi health in parallel
  var results = await Promise.all([
    apiFetch('/api/unifi/clients/' + encodeURIComponent(cid)),
    apiFetch('/api/unifi/wifi-health/' + encodeURIComponent(cid))
  ]);
  var clientData = results[0];
  var wifiData = results[1];

  var h = '<div class="card p-4 edge-accent">';
  h += '<div class="subhead mb-3">'+t('hdr_live_data','Live data')+' · '+esc(matched.customer_name)+'</div>';

  // Clients
  if (clientData && clientData.clients && clientData.clients.length) {
    var clients = clientData.clients;
    h += '<div class="subhead">'+t('hdr_connected_clients','Connected clients')+' ('+clients.length+': '+(Number(clientData.wireless)||0)+' '+t('lbl_wireless_short','wireless')+', '+(Number(clientData.wired)||0)+' '+t('lbl_wired_short','wired')+')</div>';
    h += '<div class="max-h-md overflow-y-auto"><table class="data-table data-table--compact">';
    h += '<thead class="sticky-thead"><tr><th>'+t('col_hostname','Hostname')+'</th><th>IP</th><th class="text-center">'+t('col_type','Type')+'</th><th class="text-center">'+t('col_signal','Signal')+'</th><th>'+t('col_connected_to','Connected to')+'</th></tr></thead><tbody>';
    clients.slice(0, 50).forEach(function(c) {
      var typeIcon = c.type === 'wireless' ? '' : '';
      var sigHtml = '-';
      if (c.signal && c.type === 'wireless') {
        var sigColor = c.signal > -60 ? 'var(--green)' : c.signal > -75 ? 'var(--orange)' : 'var(--red)';
        sigHtml = '<span class="' + toneClass(sigColor) + ' fw-semibold">'+Number(c.signal)+' dBm</span>';
      }
      h += '<tr><td>'+esc(c.hostname||c.name||c.mac||'-')+'</td><td class="font-mono text-2xs">'+esc(c.ip||'-')+'</td><td class="text-center">'+typeIcon+'</td><td class="text-center">'+sigHtml+'</td><td class="text-2xs text-muted">'+esc(c.connected_to||'-')+'</td></tr>';
    });
    if (clients.length > 50) h += '<tr><td colspan="5" class="text-center text-muted text-2xs">... ' + t('inf_and_more','og') + ' '+(clients.length-50)+' ' + t('inf_more_suffix','til') + '</td></tr>';
    h += '</tbody></table></div>';
  } else {
    h += '<div class="text-xs text-muted">'+t('msg_no_client_data','No client data available — check UniFi controller config on customer.')+'</div>';
  }

  // WiFi health
  if (wifiData && wifiData.aps && wifiData.aps.length) {
    h += '<div class="subhead mt-3">'+t('hdr_wifi_health','WiFi Health')+'</div>';
    if (wifiData.alerts && wifiData.alerts.length) {
      wifiData.alerts.forEach(function(a) {
        var ac = a.severity === 'critical' ? 'var(--red)' : 'var(--orange)';
        h += '<div class="text-xs ' + toneClass(ac) + ' mb-0-5">'+esc(a.message)+'</div>';
      });
    }
    h += '<table class="data-table data-table--compact mt-1">';
    h += '<thead><tr><th>AP</th><th class="text-center">'+t('lbl_clients','Clients')+'</th><th class="text-center">'+t('col_channel','Channel')+'</th><th class="text-center">'+t('col_satisfaction','Satisfaction')+'</th></tr></thead><tbody>';
    wifiData.aps.forEach(function(ap) {
      var satColor = (ap.satisfaction||0) >= 80 ? 'var(--green)' : (ap.satisfaction||0) >= 60 ? 'var(--orange)' : 'var(--red)';
      h += '<tr><td class="fw-medium">'+esc(ap.name||'-')+'</td><td class="text-center">'+Number(ap.clients)+'</td><td class="text-center text-2xs">'+esc(ap.channel||'-')+'</td><td class="text-center"><span class="' + toneClass(satColor) + ' fw-semibold">'+esc(ap.satisfaction||'-')+'%</span></td></tr>';
    });
    h += '</tbody></table>';
  }

  h += '</div>';
  el.innerHTML = h;
}

async function _loadSubSiteDevices(host, site) {
  var el = document.getElementById('subsite-devices');
  if (!el) return;
  var data = await apiFetch('/api/unifi/sm/devices?host_id='+encodeURIComponent(host.id));
  if (!data || !data.devices) { el.innerHTML = ''; return; }

  // Filter devices — show all for this host (we can't filter per-site via API)
  var devices = data.devices;
  var online = devices.filter(function(d){return d.status==='online';}).length;
  var offline = devices.filter(function(d){return d.status!=='online';}).length;

  var html = '<div class="card p-4">';
  html += '<div class="flex justify-between items-center mb-3">';
  html += '<div class="text-ui fw-semibold">' + t('inf_devices','Enheter') + ' ('+devices.length+')</div>';
  html += '<div class="text-sm text-muted">'+online+' online';
  if (offline > 0) html += ', <span class="text-danger">'+offline+' offline</span>';
  html += '</div></div>';
  html += '<table class="data-table">';
  html += '<thead><tr class="bg-base">';
  html += '<th>' + t('navn_4') + '</th>';
  html += '<th>' + t('modell') + '</th>';
  html += '<th>IP</th>';
  html += '<th class="text-center">' + t('status_3') + '</th>';
  html += '<th>' + t('firmware_3') + '</th>';
  html += '<th>' + t('oppetid') + '</th>';
  html += '</tr></thead><tbody>';
  devices.forEach(function(d) {
    var statusColor = d.status === 'online' ? 'var(--green)' : 'var(--red)';
    var dot = '<span class="dot ' + toneClass(statusColor) + '"></span>';
    var fwBadge = '';
    if (d.firmware_status === 'updateAvailable') fwBadge = ' <span class="text-warning text-2xs" title="'+esc(d.update_available)+'">⬆</span>';
    html += '<tr>';
    html += '<td class="fw-semibold">'+esc(d.name||d.mac)+(d.is_console?' <span class="text-2xs text-accent">' + t('konsoll_2') + '</span>':'')+'</td>';
    html += '<td class="text-muted">'+esc(d.model)+'</td>';
    html += '<td class="font-mono text-xs">'+esc(d.ip||'-')+'</td>';
    html += '<td class="text-center">'+dot+'</td>';
    html += '<td class="font-mono text-xs">'+esc(d.firmware||'-')+fwBadge+'</td>';
    html += '<td class="text-muted">'+esc(d.uptime||'-')+'</td>';
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  el.innerHTML = html;
}

async function _loadSubSiteWan(site) {
  var el = document.getElementById('subsite-wan');
  if (!el || !site.site_id) return;
  var data = await apiFetch('/api/unifi/sm/site/'+encodeURIComponent(site.site_id)+'/wan');
  if (!data || !data.ok) { el.innerHTML = ''; return; }

  var html = '';

  // WAN interfaces
  if (data.wans && data.wans.length) {
    html += '<div class="card p-4 mb-3">';
    html += '<div class="subhead mb-3">' + t('wan_grensesnitt') + '</div>';
    html += '<div class="grid grid-auto-md gap-3">';
    data.wans.forEach(function(w) {
      var uptimeColor = w.uptime_pct >= 99 ? 'var(--green)' : w.uptime_pct >= 95 ? 'var(--orange)' : 'var(--red)';
      html += '<div class="inset">';
      html += '<div class="fw-semibold mb-2">'+esc(w.name)+'</div>';
      html += '<div class="text-sm text-muted grid gap-1">';
      if (w.external_ip) html += '<span>' + t('ekstern_ip') + ' <strong class="text-default">'+esc(w.external_ip)+'</strong></span>';
      if (w.isp) html += '<span>ISP: '+esc(w.isp)+(w.isp_org ? ' ('+esc(w.isp_org)+')' : '')+'</span>';
      html += '<span>' + t('uptime') + ' <span class="' + toneClass(uptimeColor) + ' fw-semibold">'+Number(w.uptime_pct)+'%</span></span>';
      if (w.issues && w.issues.length) html += '<span class="text-danger">'+w.issues.length+' ' + t('inf_problems','problem(er)') + '</span>';
      html += '</div></div>';
    });
    html += '</div></div>';
  }

  // Gateway security
  if (data.gateway && data.gateway.model) {
    var gw = data.gateway;
    html += '<div class="card p-4">';
    html += '<div class="subhead mb-3">' + t('gateway_sikkerhet') + '</div>';
    html += '<div class="grid grid-cols-2 gap-1 text-sm text-muted">';
    html += '<span>' + t('modell') + ' <strong class="text-default">'+esc(gw.model)+'</strong></span>';
    var idsColor = gw.ids_mode === 'ids' || gw.ids_mode === 'ips' ? 'var(--green)' : 'var(--orange)';
    html += '<span>' + t('ids_ips') + ' <span class="' + toneClass(idsColor) + ' fw-semibold">'+esc(gw.ids_mode.toUpperCase())+'</span></span>';
    html += '<span>Inspeksjon: '+esc(gw.inspection)+'</span>';
    if (gw.ips_rules) html += '<span>IPS-regler: '+Number(gw.ips_rules).toLocaleString()+'</span>';
    html += '</div></div>';
  }

  el.innerHTML = html;

  if (el) el.innerHTML = html;
}

function showSiteDetail(idx) {
  var s = _unifiSites[idx];
  if (!s) return;
  var html = '<div class="max-w-md">';
  html += '<div class="flex items-center gap-3 mb-4">';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="dashLoadSites">' + t('tilbake') + '</button>';
  html += '<h3 class="text-md fw-bold m-0">'+esc(s.name||'-')+'</h3>';
  html += '</div>';

  // ── Detail card: strict table, ALL rows always rendered ──
  html += '<div class="card p-4">';
  html += '<table class="w-full text-ui">';
  var statusHtml = '<span class="fw-semibold '+(s.status==='online'?'text-success':'text-danger')+'">'+(s.status ? esc(s.status.toUpperCase()) : '-')+'</span>';
  var fwHtml = esc(s.firmware||'-') + (s.firmware_update ? ' &rarr; <span class="text-warning">'+esc(s.firmware_update)+' tilgjengelig</span>' : '');
  var devHtml = (s.device_count!=null ? Number(s.device_count) : '-') + (s.offline_devices > 0 ? ' <span class="text-danger">('+Number(s.offline_devices)+' offline)</span>' : '');
  var rows = [
    ['Status',          statusHtml],
    ['WAN IP',          esc(s.wan_ip || '-')],
    ['Modell',          esc(s.model_full || s.model || '-')],
    ['Firmware',        fwHtml],
    ['MAC',             esc(s.mac || '-')],
    ['Serienummer',     esc(s.serial || '-')],
    ['ISP',             esc(s.isp || '-')],
    [t('inf_devices','Enheter'), devHtml],
    ['Klienter',        s.client_count != null ? Number(s.client_count) : '-'],
    ['Siter',           s.site_count != null ? Number(s.site_count) : '-'],
    ['Registrert',      s.registered ? new Date(s.registered).toLocaleDateString('no-NO') : '-'],
    [t('inf_last_backup','Siste backup'), s.last_backup ? new Date(s.last_backup).toLocaleString('no-NO') : '-'],
    [t('inf_last_connection','Siste tilkobling'),s.last_connection ? new Date(s.last_connection).toLocaleString('no-NO') : '-'],
  ];
  rows.forEach(function(r) {
    html += '<tr class="border-b"><td class="kv-key">'+r[0]+'</td><td class="p-2">'+r[1]+'</td></tr>';
  });
  html += '</table></div>';

  // ── Sub-sites table: always render (show empty-state row if none) ──
  html += '<div class="mt-4"><h4 class="text-base fw-semibold mb-2">Siter ('+((s.sub_sites && s.sub_sites.length) || 0)+')</h4>';
  html += '<table class="data-table">';
  html += '<thead><tr class="bg-base">'
    + '<th class="p-2">' + t('kundesite') + '</th>'
    + '<th class="text-center p-2">' + t('enheter') + '</th>'
    + '<th class="text-center p-2">' + t('offline_2') + '</th>'
    + '<th class="text-center p-2">' + t('wifi') + '</th>'
    + '<th class="text-center p-2">' + t('kabel') + '</th>'
    + '<th class="text-center p-2">' + t('gjest') + '</th>'
    + '<th class="text-center p-2">WLAN</th>'
    + '</tr></thead><tbody>';
  if (s.sub_sites && s.sub_sites.length) {
    var totDev=0,totOff=0,totWifi=0,totWired=0,totGuest=0,totWlan=0;
    s.sub_sites.forEach(function(sub) {
      var offVal = Number(sub.offline_devices) || 0;
      var offStyle = offVal > 0 ? 'text-danger fw-semibold' : '';
      html += '<tr>';
      html += '<td class="p-2 fw-semibold">'+esc(sub.name||'-')+'</td>';
      html += '<td class="p-2 text-center">'+(sub.device_count!=null ? Number(sub.device_count) : '-')+'</td>';
      html += '<td class="p-2 text-center '+offStyle+'">'+offVal+'</td>';
      html += '<td class="p-2 text-center">'+(sub.wifi_clients!=null ? Number(sub.wifi_clients) : '-')+'</td>';
      html += '<td class="p-2 text-center">'+(sub.wired_clients!=null ? Number(sub.wired_clients) : '-')+'</td>';
      html += '<td class="p-2 text-center">'+(sub.guest_count!=null ? Number(sub.guest_count) : '-')+'</td>';
      html += '<td class="p-2 text-center">'+(sub.wifi_networks!=null ? Number(sub.wifi_networks) : '-')+'</td>';
      html += '</tr>';
      totDev+=(Number(sub.device_count)||0); totOff+=offVal; totWifi+=(Number(sub.wifi_clients)||0); totWired+=(Number(sub.wired_clients)||0); totGuest+=(Number(sub.guest_count)||0); totWlan+=(Number(sub.wifi_networks)||0);
    });
    html += '<tr class="fw-bold bg-base">';
    html += '<td class="p-2">' + t('totalt') + '</td>';
    html += '<td class="p-2 text-center">'+totDev+'</td>';
    html += '<td class="p-2 text-center'+(totOff>0?' text-danger':'')+'">'+totOff+'</td>';
    html += '<td class="p-2 text-center">'+totWifi+'</td>';
    html += '<td class="p-2 text-center">'+totWired+'</td>';
    html += '<td class="p-2 text-center">'+totGuest+'</td>';
    html += '<td class="p-2 text-center">'+totWlan+'</td>';
    html += '</tr>';
  } else {
    html += '<tr><td colspan="7" class="p-3 text-center text-dim">-</td></tr>';
  }
  html += '</tbody></table></div>';

  html += '</div>';

  var el = document.getElementById('unifi-sm-sites-list');
  if (el) el.innerHTML = html;
  // Also update in integration view if open
  var el2 = document.getElementById('unifi-sm-sites-list');
  if (el2 && el2.offsetParent) el2.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════
// TERMINAL
// ═══════════════════════════════════════════════════════════════════

var _termWs = null;
var _xterm = null;
var _xtermFit = null;

function _termEnsureXterm() {
  if (_xterm) return;
  var container = document.getElementById('term-container');
  container.innerHTML = '';
  _xterm = new Terminal({
    cursorBlink: true,
    fontSize: 14,
    fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
    theme: {
      background: '#0d1117',
      foreground: '#e6edf3',
      cursor: '#4d9fb5',
      selectionBackground: '#264f78',
      black: '#484f58', red: '#f85149', green: '#3fb950', yellow: '#d29922',
      blue: '#58a6ff', magenta: '#bc8cff', cyan: '#4d9fb5', white: '#e6edf3',
    },
  });
  _xtermFit = new FitAddon.FitAddon();
  _xterm.loadAddon(_xtermFit);
  _xterm.open(container);
  _xtermFit.fit();

  // Send keyboard input to WebSocket
  _xterm.onData(function(data) {
    if (_termWs && _termWs.readyState === WebSocket.OPEN) {
      _termWs.send(JSON.stringify({type: 'input', data: data}));
    }
  });

  // Handle resize
  _xterm.onResize(function(size) {
    if (_termWs && _termWs.readyState === WebSocket.OPEN) {
      _termWs.send(JSON.stringify({type: 'resize', cols: size.cols, rows: size.rows}));
    }
  });

  window.addEventListener('resize', function() { if (_xtermFit) _xtermFit.fit(); });
}

export function termModeChanged() {
  var mode = document.getElementById('term-mode').value;
  var sshOpts = document.getElementById('term-ssh-opts');
  sshOpts.style.display = mode === 'ssh' ? 'flex' : 'none';
  if (mode === 'ssh') termLoadHosts();
}

async function termLoadHosts() {
  var sel = document.getElementById('term-host-select');
  var data = await apiFetch('/api/ssh/hosts');
  if (!data) return;
  sel.innerHTML = '<option value="">' + t('placeholder_select_host','Select host...') + '</option>';
  (data.hosts || []).forEach(function(h) {
    sel.innerHTML += '<option value="'+esc(h.id)+'">'+esc(h.label)+' ('+esc(h.hostname)+')</option>';
  });
}

var _termFontSize = parseInt(localStorage.getItem('sybr_term_fontsize') || '14');
export function termChangeFontSize(delta) {
  _termFontSize = Math.max(10, Math.min(24, _termFontSize + delta));
  localStorage.setItem('sybr_term_fontsize', _termFontSize);
}

export function termConnect() {
  if (_termWs) termDisconnect();
  _termEnsureXterm();
  _xterm.clear();

  var mode = document.getElementById('term-mode').value;
  var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  var url = proto + '//' + location.host + '/api/ws/terminal?mode=' + mode;

  if (mode === 'ssh') {
    var hostId = document.getElementById('term-host-select').value;
    var manual = document.getElementById('term-host-manual').value.trim();
    if (hostId) {
      url += '&host_id=' + encodeURIComponent(hostId);
    } else if (manual) {
      var parts = manual;
      var user = 'root', host = manual, port = 22;
      if (parts.indexOf('@') !== -1) { user = parts.split('@')[0]; parts = parts.split('@')[1]; }
      if (parts.indexOf(':') !== -1) { host = parts.split(':')[0]; port = parseInt(parts.split(':')[1]); } else { host = parts; }
      url += '&host=' + encodeURIComponent(host) + '&user=' + encodeURIComponent(user) + '&port=' + port;
    } else {
      showToast(t('err_select_host_or_manual','Select a host or enter host manually'), 'error');
      return;
    }
  }

  document.getElementById('term-status').textContent = t('vpn_connecting','Connecting...');
  document.getElementById('term-connect-btn').style.display = 'none';
  document.getElementById('term-disconnect-btn').style.display = 'inline-flex';

  _termWs = new WebSocket(url);

  _termWs.onopen = function() {
    document.getElementById('term-status').innerHTML = '<span class="text-success">' + t('tilkoblet') + '</span>';
    _xterm.focus();
    _xtermFit.fit();
    _termWs.send(JSON.stringify({type: 'resize', cols: _xterm.cols, rows: _xterm.rows}));
  };

  _termWs.onmessage = function(evt) {
    try {
      var msg = JSON.parse(evt.data);
      if (msg.type === 'output') {
        _xterm.write(msg.data);
      }
    } catch(e) {
      _xterm.write(evt.data);
    }
  };

  _termWs.onclose = function() {
    _xterm.write('\r\n\x1b[90m--- Sesjon avsluttet ---\x1b[0m\r\n');
    document.getElementById('term-status').innerHTML = '<span class="text-muted">' + t('frakoblet') + '</span>';
    document.getElementById('term-connect-btn').style.display = 'inline-flex';
    document.getElementById('term-disconnect-btn').style.display = 'none';
    _termWs = null;
  };

  _termWs.onerror = function() {
    document.getElementById('term-status').innerHTML = '<span class="text-danger">' + t('tilkoblingsfeil') + '</span>';
  };
}

export function termDisconnect() {
  if (_termWs) {
    _termWs.close();
    _termWs = null;
  }
}


// ═══════════════════════════════════════════════════════════════════
// GUACAMOLE JS CLIENT — direct WebSocket tunnel (no iframe)
// ═══════════════════════════════════════════════════════════════════

// Active Guacamole sessions for cleanup
var _guacSessions = {};

function _createGuacSession(containerId, token, connectionId) {
  var container = document.getElementById(containerId);
  if (!container) return null;
  container.innerHTML = '';
  container.style.width = '100%';
  container.style.height = 'calc(100vh - 140px)';
  container.style.overflow = 'hidden';
  container.tabIndex = 0;

  // Tunnel — use correct WS protocol based on page protocol
  var wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  var tunnel = new Guacamole.WebSocketTunnel(
    wsProto + '//' + window.location.host + '/guacamole/websocket-tunnel'
  );

  var client = new Guacamole.Client(tunnel);

  // Display element — force to top-left of container
  var displayEl = client.getDisplay().getElement();
  displayEl.style.cursor = 'none';
  displayEl.style.position = 'absolute';
  displayEl.style.top = '0';
  displayEl.style.left = '0';
  container.appendChild(displayEl);

  // Clipboard buffer for focus retry
  var _clipboardBuffer = '';

  // RDP -> Browser clipboard
  client.onclipboard = function(stream, mimetype) {
    if (mimetype !== 'text/plain') return;
    var data = '';
    stream.onblob = function(base64) {
      data += atob(base64);
    };
    stream.onend = function() {
      _clipboardBuffer = data;
      try {
        navigator.clipboard.writeText(data).catch(function(){});
      } catch(e) {}
    };
  };

  // Retry clipboard write on window focus
  var _focusHandler = function() {
    if (_clipboardBuffer) {
      try {
        navigator.clipboard.writeText(_clipboardBuffer).catch(function(){});
      } catch(e) {}
    }
  };
  window.addEventListener('focus', _focusHandler);

  // Browser -> RDP clipboard (paste event)
  var _pasteHandler = function(e) {
    var text = e.clipboardData.getData('text/plain');
    if (text) {
      var stream = client.createClipboardStream('text/plain');
      var writer = new Guacamole.StringWriter(stream);
      writer.sendText(text);
      writer.sendEnd();
    }
  };
  document.addEventListener('paste', _pasteHandler);

  // Mouse input
  var mouse = new Guacamole.Mouse(displayEl);
  function handleMouse(e) {
    container.focus();
    client.sendMouseState(e.state || e);
  }
  if (typeof mouse.on === 'function') {
    mouse.on('mousedown', handleMouse);
    mouse.on('mouseup', handleMouse);
    mouse.on('mousemove', handleMouse);
  } else {
    mouse.onmousedown = mouse.onmouseup = mouse.onmousemove = handleMouse;
  }

  // Fix Guacamole canvas visibility.
  // Guacamole sets default layer canvas z-index:-1 which hides it behind
  // parent divs with position:absolute. Fix: make all layer DIVS transparent
  // and shift canvas z-index up.
  function fixGuacLayers() {
    container.querySelectorAll('div').forEach(function(d) {
      if (d.style.position === 'absolute' && d.style.overflow === 'hidden') {
        d.style.background = 'none';
      }
    });
    container.querySelectorAll('canvas').forEach(function(c) {
      c.style.cursor = 'none';
      if (parseInt(c.style.zIndex) < 0) {
        c.style.zIndex = '0';
      }
    });
  }
  new MutationObserver(fixGuacLayers).observe(displayEl, { childList: true, subtree: true });
  // Run repeatedly during connection setup
  var _fixInterval = setInterval(fixGuacLayers, 200);
  setTimeout(function() { clearInterval(_fixInterval); }, 10000);

  // Keyboard input (only when container is focused)
  var keyboard = new Guacamole.Keyboard(container);
  keyboard.onkeydown = function(keysym) {
    // Intercept Ctrl+V (keysym 0x0076 with ctrl) — read clipboard and send to RDP
    if (keysym === 0x0076 && keyboard.pressed[0xFFE3]) { // 'v' + Ctrl
      if (navigator.clipboard && navigator.clipboard.readText) {
        navigator.clipboard.readText().then(function(text) {
          if (text) {
            var stream = client.createClipboardStream('text/plain');
            var writer = new Guacamole.StringWriter(stream);
            writer.sendText(text);
            writer.sendEnd();
            // Also send Ctrl+V to RDP so it pastes from remote clipboard
            setTimeout(function() {
              client.sendKeyEvent(1, keysym);
              setTimeout(function() { client.sendKeyEvent(0, keysym); }, 50);
            }, 100);
          }
        }).catch(function() {
          client.sendKeyEvent(1, keysym);
        });
        return;
      }
    }
    client.sendKeyEvent(1, keysym);
  };
  keyboard.onkeyup = function(keysym) { client.sendKeyEvent(0, keysym); };

  // Resize handler — debounced 300ms
  var _resizeTimer = null;
  function sendSize() {
    var w = container.offsetWidth;
    var h = container.offsetHeight;
    if (w > 0 && h > 0) {
      client.sendSize(w, h);
    }
  }
  var _resizeHandler = function() {
    clearTimeout(_resizeTimer);
    _resizeTimer = setTimeout(sendSize, 300);
  };
  window.addEventListener('resize', _resizeHandler);

  // State change — send size repeatedly after connect so RDP adjusts after login
  client.onstatechange = function(state) {
    if (state === Guacamole.Client.State.CONNECTED) {
      // Pulse resize: immediate, then at intervals to catch post-login adjustment
      var delays = [200, 1000, 2000, 4000, 6000, 10000];
      delays.forEach(function(ms) { setTimeout(sendSize, ms); });
    }
  };

  // Connect with actual container dimensions
  var w = Math.floor(container.offsetWidth * window.devicePixelRatio);
  var h = Math.floor(container.offsetHeight * window.devicePixelRatio);
  client.connect(
    'token=' + encodeURIComponent(token) +
    '&GUAC_DATA_SOURCE=mysql' +
    '&GUAC_ID=' + encodeURIComponent(connectionId) +
    '&GUAC_TYPE=c' +
    '&GUAC_WIDTH=' + w +
    '&GUAC_HEIGHT=' + h +
    '&GUAC_DPI=96'
  );

  container.focus();

  return {
    client: client,
    destroy: function() {
      try { client.disconnect(); } catch(e) {}
      keyboard.onkeydown = null;
      keyboard.onkeyup = null;
      window.removeEventListener('resize', _resizeHandler);
      window.removeEventListener('focus', _focusHandler);
      document.removeEventListener('paste', _pasteHandler);
      container.innerHTML = '';
    }
  };
}


// ═══════════════════════════════════════════════════════════════════
// REMOTE BROWSER — Guacamole VNC + Chromium on Xvfb (direct JS client)
// ═══════════════════════════════════════════════════════════════════

var _browserRunning = false;

export function browserInit() {
  var el = document.getElementById('browser-content');
  if (!el) return;

  // Only build UI once
  if (document.getElementById('browser-url-input')) return;

  el.innerHTML =
    '<div class="flex gap-2 mb-3 items-center flex-wrap">' +
      '<input id="browser-url-input" type="text" placeholder="http://192.168.1.1" class="field-input font-mono flex-field w-auto" data-keydown-handler="browserNavigateOnEnter">' +
      '<button class="btn btn-primary" id="browser-go-btn" data-write data-click-handler="browserNavigate">' + t('gaa') + '</button>' +
      '<button class="btn btn-primary" id="browser-start-btn" data-write data-click-handler="browserStart">' + t('start_nettleser') + '</button>' +
      '<button class="btn btn-danger" id="browser-stop-btn" data-write data-click-handler="browserStop" style="display:none;">' + t('stopp') + '</button>' +
      '<button class="btn btn-ghost" id="browser-fullscreen-btn" data-click-handler="toggleFullscreen" data-target="browser-guac-container" style="display:none;">' + t('btn_fullscreen','Fullskjerm') + '</button>' +
      '<span id="browser-status" class="session-status"></span>' +
    '</div>' +
    '<div id="browser-frame-wrap" class="session-frame">' +
      '<div id="browser-placeholder" class="session-placeholder">' + esc(t('browser_placeholder', 'Klikk «Start nettleser» for å åpne en ekstern nettleser.')) + '</div>' +
      '<div id="browser-guac-container" class="session-canvas" style="display:none;"></div>' +
    '</div>';

  // Check if a session is already running
  browserCheckStatus();
}

async function browserCheckStatus() {
  var data = await apiFetch('/api/browser/status');
  if (data && data.running && data.guac_token && data.guac_connection_id) {
    _browserRunning = true;
    _browserShowDirect(data.guac_token, data.guac_connection_id);
    browserUpdateButtons(true);
    if (data.url) {
      var input = document.getElementById('browser-url-input');
      if (input) input.value = data.url;
    }
  }
}

function browserUpdateButtons(running) {
  var startBtn = document.getElementById('browser-start-btn');
  var stopBtn = document.getElementById('browser-stop-btn');
  var fsBtn = document.getElementById('browser-fullscreen-btn');
  var goBtn = document.getElementById('browser-go-btn');
  if (startBtn) startBtn.style.display = running ? 'none' : '';
  if (stopBtn) stopBtn.style.display = running ? '' : 'none';
  if (fsBtn) fsBtn.style.display = running ? '' : 'none';
  if (goBtn) goBtn.disabled = !running;
}

function _browserShowDirect(token, connectionId) {
  var placeholder = document.getElementById('browser-placeholder');
  var guacContainer = document.getElementById('browser-guac-container');
  if (!guacContainer) return;

  if (placeholder) placeholder.style.display = 'none';
  guacContainer.style.display = 'block';

  // Destroy previous session if any
  if (_guacSessions.browser) {
    _guacSessions.browser.destroy();
    _guacSessions.browser = null;
  }

  var session = _createGuacSession('browser-guac-container', token, connectionId);
  if (session) {
    _guacSessions.browser = session;
  }
  var statusEl = document.getElementById('browser-status');
  if (statusEl) statusEl.innerHTML = '<span class="text-success">' + t('tilkoblet') + '</span>';
}

function openWebUI(url) {
  showView('browser');
  setTimeout(function() {
    var input = document.getElementById('browser-url-input');
    if (input) {
      input.value = url;
      browserStart();
    }
  }, 300);
}

async function browserStart() {
  var status = document.getElementById('browser-status');
  var input = document.getElementById('browser-url-input');
  var url = (input.value || '').trim();

  // Auto-add http:// if scheme is missing
  if (url && !/^https?:\/\//i.test(url)) {
    url = 'http://' + url;
    input.value = url;
  }

  // Request clipboard permission
  try {
    var perm = await navigator.permissions.query({name: 'clipboard-read'});
    if (perm.state === 'prompt') {
      await navigator.clipboard.readText().catch(function(){});
    }
  } catch(e) {}

  if (status) status.innerHTML = '<div class="loader align-middle mr-1"></div> Starter...';

  var data = await apiFetch('/api/browser/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url: url})
  });

  if (!data || !data.ok) {
    if (status) status.innerHTML = '<span class="text-danger">' + esc(data && data.error ? data.error : t('inf_start_failed','Feil ved start')) + '</span>';
    return;
  }

  _browserRunning = true;
  browserUpdateButtons(true);

  if (data.guac_token && data.guac_connection_id) {
    _browserShowDirect(data.guac_token, data.guac_connection_id);
  }
}

async function browserNavigate() {
  if (!_browserRunning) {
    // If not running, start instead
    await browserStart();
    return;
  }

  var input = document.getElementById('browser-url-input');
  var status = document.getElementById('browser-status');
  var url = (input.value || '').trim();
  if (!url) return;

  if (!/^https?:\/\//i.test(url)) {
    url = 'http://' + url;
    input.value = url;
  }

  if (status) status.innerHTML = '<div class="loader align-middle mr-1"></div> Navigerer...';

  var data = await apiFetch('/api/browser/navigate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url: url})
  });

  if (!data || !data.ok) {
    if (status) status.innerHTML = '<span class="text-danger">' + esc(data && data.error ? data.error : t('inf_error','Feil')) + '</span>';
    return;
  }

  if (status) status.innerHTML = '<span class="text-success">' + t('tilkoblet') + '</span>';
}

async function browserStop() {
  var status = document.getElementById('browser-status');
  var placeholder = document.getElementById('browser-placeholder');
  var guacContainer = document.getElementById('browser-guac-container');

  if (status) status.innerHTML = '<div class="loader align-middle mr-1"></div> Stopper...';

  // Destroy Guacamole session
  if (_guacSessions.browser) {
    _guacSessions.browser.destroy();
    _guacSessions.browser = null;
  }

  await apiFetch('/api/browser/stop', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'}
  });

  _browserRunning = false;
  browserUpdateButtons(false);

  if (guacContainer) { guacContainer.style.display = 'none'; guacContainer.innerHTML = ''; }
  if (placeholder) placeholder.style.display = 'flex';
  if (status) status.innerHTML = '';
}

function toggleFullscreen(elementId) {
  var el = document.getElementById(elementId);
  if (!el) return;
  if (document.fullscreenElement) {
    document.exitFullscreen();
  } else {
    el.requestFullscreen().catch(function() {});
  }
}
document.addEventListener('fullscreenchange', function() {
  // Trigger resize so Guacamole display re-scales in/out of fullscreen
  // Multiple delays to catch the DOM settling
  setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 100);
  setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 500);
});


// ═══════════════════════════════════════════════════════════════════
// REMOTE RDP — Apache Guacamole (direct JS client)
// ═══════════════════════════════════════════════════════════════════

var _rdpRunning = false;
var _rdpPendingHostId = '';

export function rdpInit() {
  var el = document.getElementById('rdp-content');
  if (!el) return;

  // Only build UI once
  if (document.getElementById('rdp-host-input')) return;

  el.innerHTML =
    '<div class="flex gap-2 mb-3 items-center flex-wrap">' +
      '<select id="rdp-host-input" class="field-input font-mono flex-field flex-field-2 w-auto"><option value="">' + t('rdp_select_host','Velg registrert host ...') + '</option></select>' +
      '<input id="rdp-port-input" type="text" placeholder="3389" class="field-input input-narrow font-mono">' +
      '<input id="rdp-user-input" type="text" placeholder="' + t('inf_ph_username','Brukernavn') + '" class="field-input font-mono flex-field w-auto">' +
      '<input id="rdp-pass-input" type="password" placeholder="' + t('inf_ph_password','Passord') + '" class="field-input font-mono flex-field w-auto" data-keydown-handler="rdpStartOnEnter">' +
      '<button class="btn btn-primary" id="rdp-start-btn" data-write data-click-handler="rdpStart">' + t('koble_til') + '</button>' +
      '<button class="btn btn-danger" id="rdp-stop-btn" data-write data-click-handler="rdpStop" style="display:none;">' + t('koble_fra') + '</button>' +
      '<button class="btn btn-ghost" id="rdp-fullscreen-btn" data-click-handler="toggleFullscreen" data-target="rdp-guac-container" style="display:none;">' + t('btn_fullscreen','Fullskjerm') + '</button>' +
      '<span id="rdp-status" class="session-status"></span>' +
    '</div>' +
    '<div id="rdp-frame-wrap" class="border rounded-lg overflow-hidden bg-none relative">' +
      '<div id="rdp-placeholder" class="session-placeholder is-tall">' + t('fyll_inn_tilkoblingsdetaljer_og_klikk_la') + '</div>' +
      '<div id="rdp-guac-container" class="session-canvas is-tall" style="display:none;"></div>' +
    '</div>';

  // Check if a session is already running
  apiFetch('/api/ssh/hosts').then(function(data) {
    var select = document.getElementById('rdp-host-input');
    if (!select || !data || !Array.isArray(data.hosts)) return;
    data.hosts.forEach(function(host) {
      var option = document.createElement('option');
      option.value = host.id;
      option.textContent = (host.label || host.hostname) + ' · ' + host.hostname;
      option.dataset.username = host.username || '';
      select.appendChild(option);
    });
    if (_rdpPendingHostId) select.value = _rdpPendingHostId;
    select.addEventListener('change', function() {
      var selected = select.options[select.selectedIndex];
      var userInput = document.getElementById('rdp-user-input');
      if (userInput && selected && selected.dataset.username) {
        userInput.value = selected.dataset.username;
      }
    });
  });
  rdpCheckStatus();
}

async function rdpCheckStatus() {
  var data = await apiFetch('/api/rdp/status');
  if (data && data.running && data.guac_token && data.guac_connection_id) {
    _rdpRunning = true;
    _rdpShowDirect(data.guac_token, data.guac_connection_id);
    rdpUpdateButtons(true);
  }
}

function rdpUpdateButtons(running) {
  var startBtn = document.getElementById('rdp-start-btn');
  var stopBtn = document.getElementById('rdp-stop-btn');
  var fsBtn = document.getElementById('rdp-fullscreen-btn');
  var hostInput = document.getElementById('rdp-host-input');
  var portInput = document.getElementById('rdp-port-input');
  var userInput = document.getElementById('rdp-user-input');
  var passInput = document.getElementById('rdp-pass-input');
  if (startBtn) startBtn.style.display = running ? 'none' : '';
  if (stopBtn) stopBtn.style.display = running ? '' : 'none';
  if (fsBtn) fsBtn.style.display = running ? '' : 'none';
  if (hostInput) hostInput.disabled = running;
  if (portInput) portInput.disabled = running;
  if (userInput) userInput.disabled = running;
  if (passInput) passInput.disabled = running;
}

function _rdpShowDirect(token, connectionId) {
  var placeholder = document.getElementById('rdp-placeholder');
  var guacContainer = document.getElementById('rdp-guac-container');
  if (!guacContainer) return;

  if (placeholder) placeholder.style.display = 'none';
  guacContainer.style.display = 'block';

  // Destroy previous session if any
  if (_guacSessions.rdp) {
    _guacSessions.rdp.destroy();
    _guacSessions.rdp = null;
  }

  var session = _createGuacSession('rdp-guac-container', token, connectionId);
  if (session) {
    _guacSessions.rdp = session;
  }
  var statusEl = document.getElementById('rdp-status');
  if (statusEl) statusEl.innerHTML = '<span class="text-success">' + t('tilkoblet') + '</span>';
}

async function rdpStart() {
  var status = document.getElementById('rdp-status');
  var hostInput = document.getElementById('rdp-host-input');
  var portInput = document.getElementById('rdp-port-input');
  var userInput = document.getElementById('rdp-user-input');
  var passInput = document.getElementById('rdp-pass-input');

  var hostId = (hostInput.value || '').trim();
  if (!hostId) {
    showToast(t('vertsnavn_er_paakrevd'), 'error');
    hostInput.focus();
    return;
  }

  var port = parseInt(portInput.value, 10) || 3389;
  var username = (userInput.value || '').trim();
  var password = passInput.value || '';

  // Request clipboard permission
  try {
    var perm = await navigator.permissions.query({name: 'clipboard-read'});
    if (perm.state === 'prompt') {
      await navigator.clipboard.readText().catch(function(){});
    }
  } catch(e) {}

  if (status) status.innerHTML = '<div class="loader align-middle mr-1"></div> ' + t('inf_connecting','Kobler til ...') + '';

  var data = await apiFetch('/api/rdp/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({host_id: hostId, port: port, username: username, password: password})
  });

  if (!data || !data.ok) {
    if (status) status.innerHTML = '<span class="text-danger">' + esc(data && data.error ? data.error : t('inf_connect_failed','Feil ved tilkobling')) + '</span>';
    return;
  }

  _rdpRunning = true;
  rdpUpdateButtons(true);

  if (data.guac_token && data.guac_connection_id) {
    _rdpShowDirect(data.guac_token, data.guac_connection_id);
  }
}

async function rdpStop() {
  var status = document.getElementById('rdp-status');
  var placeholder = document.getElementById('rdp-placeholder');
  var guacContainer = document.getElementById('rdp-guac-container');

  if (status) status.innerHTML = '<div class="loader align-middle mr-1"></div> ' + t('inf_disconnecting','Kobler fra ...') + '';

  // Destroy Guacamole session
  if (_guacSessions.rdp) {
    _guacSessions.rdp.destroy();
    _guacSessions.rdp = null;
  }

  await apiFetch('/api/rdp/stop', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'}
  });

  _rdpRunning = false;
  rdpUpdateButtons(false);

  if (guacContainer) { guacContainer.style.display = 'none'; guacContainer.innerHTML = ''; }
  if (placeholder) placeholder.style.display = 'flex';
  if (status) status.innerHTML = '';
}
