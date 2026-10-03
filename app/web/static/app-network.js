// ═══════════════════════════════════════════════════════════════════
// NETWORK — files, UniFi devices, subnet scan & config backup
// ═══════════════════════════════════════════════════════════════════

import {esc} from './app-esc.js';
import {t} from './app-i18n.js';
import {registerUiHandlers} from './app-handlers.js';
import {registerToolCustomer} from './app-hooks.js';
import {_custPage, currentCustomerId} from './app-state.js';
import {formatRunName, toneClass, toneName} from './app-format.js';
import {emptyStateHTML, showConfirm, showToast} from './app-ui.js';
import {apiFetch} from './app-api.js';
import {renderToolCustomerPickers, toolCustomerId, toolNoCustomerHtml} from './app.js';

// Handlers for the markup this file builds: the FortiGate and UniFi settings,
// the UniFi device cards and the subnet scan results.
registerUiHandlers({
  toggleNetworkConfig: function(el) { toggleNetworkConfig(el.dataset.config); },
  testFortiGate: function() { testFortiGate(); },
  saveFortiGate: function() { saveFortiGate(); },
  toggleUniFiMode: function() { toggleUniFiMode(); },
  testUniFi: function() { testUniFi(); },
  saveUniFi: function() { saveUniFi(); },
  addUniFiDeviceFromForm: function() { addUniFiDeviceFromForm(); },
  saveUniFiDirect: function() { saveUniFiDirect(); },
  testUniFiDevice: function(el) { testUniFiDevice(Number(el.dataset.index)); },
  removeUniFiDevice: function(el) { removeUniFiDevice(Number(el.dataset.index)); },
  unifiDeviceSetInform: function(el) { unifiDeviceSetInform(el.dataset.host); },
  unifiDeviceConfig: function(el) { unifiDeviceConfig(el.dataset.host); },
  unifiDeviceReboot: function(el) { unifiDeviceReboot(el.dataset.host); },
  // Close on the running config a device card shows: empties the card's action area.
  unifiDeviceConfigClose: function(el) { el.parentElement.parentElement.innerHTML = ''; },
  addScannedDevice: function(el) { addScannedDevice(el.dataset.host, el); },
  scanDeviceSetInform: function(el) { scanDeviceSetInform(el.dataset.host); },
  scanDeviceConfig: function(el) { scanDeviceConfig(el.dataset.host, el.dataset.rowId); },
  scanDeviceReboot: function(el) { scanDeviceReboot(el.dataset.host); },
  doScanSetInform: function(el) { doScanSetInform(el.dataset.host, el.dataset.url); },
  // The custom inform URL is read when the button is clicked.
  doScanSetInformCustomUrl: function(el) {
    doScanSetInform(el.dataset.host, document.getElementById('scan-inform-custom-url').value.trim());
  },
  // Close on the running config shown under a scan result: hides and empties its row.
  scanDeviceConfigClose: function(el) {
    var r = document.getElementById(el.dataset.rowId);
    r.style.display = 'none';
    r.querySelector('td').innerHTML = '';
  },
});

// ── Files ───────────────────────────────────────────────────────────────────────
// One customer's files, on its page's Detaljer.
export async function loadFiles(customerId) {
  const noCustomer = document.getElementById('files-no-customer');
  const content = document.getElementById('files-content');
  if (!customerId) {
    noCustomer.style.display = 'block';
    content.style.display = 'none';
    return;
  }
  try {
    const d = await apiFetch('/api/customer/' + encodeURIComponent(customerId) + '/files');
    // Another customer's page opened meanwhile: these are not its files.
    if (_custPage.id !== customerId) return;
    if (!d) { content.style.display = 'none'; return; }
    noCustomer.style.display = 'none';
    content.style.display = 'block';

    // Credentials
    const c = d.credentials || {};
    var _elCreds = document.getElementById('files-creds');
    if (_elCreds) _elCreds.innerHTML = `
      <div class="grid kv-grid gap-y-1 gap-x-3">
        <span class="text-muted">${t('lbl_customer')}</span><span><strong>${esc(c.customer_name)}</strong></span>
        <span class="text-muted">${t('lbl_tenant_id')}</span><span class="font-mono text-sm">${esc(c.tenant_id)}</span>
        <span class="text-muted">${t('lbl_client_id')}</span><span class="font-mono text-sm">${esc(c.client_id)}</span>
        <span class="text-muted">${t('lbl_domain')}</span><span>${esc(c.domain)}</span>
        <span class="text-muted">${t('lbl_setup_date')}</span><span>${esc(c.setup_date)}</span>
        <span class="text-muted">${t('lbl_secret_expiry')}</span><span>${esc(c.secret_expiry)}</span>
      </div>`;

    // Certificate
    const cert = d.certificate || {};
    const certStatus = cert.exists
      ? t('files_cert_available').replace('{date}', esc(cert.expiry))
      : t('files_cert_missing');
    const encStatus = cert.encrypted
      ? `<span class="text-success">${t('status_encrypted')}</span>`
      : `<span class="text-muted">${t('status_password_protected')}</span>`;
    var _elCert = document.getElementById('files-cert');
    if (_elCert) _elCert.innerHTML = `
      <div class="grid kv-grid gap-y-1 gap-x-3">
        <span class="text-muted">${t('lbl_status')}</span><span>${certStatus}</span>
        <span class="text-muted">${t('lbl_protection')}</span><span>${encStatus}</span>
      </div>`;

    // Reports
    const reports = d.reports || [];
    var _elReports = document.getElementById('files-reports');
    if (_elReports) {
      if (reports.length === 0) {
        _elReports.innerHTML = '<span class="text-muted">' + t('msg_no_reports_yet') + '</span>';
      } else {
        let html = '<div class="max-h-sm overflow-y-auto">';
        for (const r of reports) {
          html += `<div class="files-report-row">
            <span class="files-report-name">${esc(r.name)}</span>
            <span class="files-report-meta">${esc(r.run ? formatRunName(r.run, true) : '')} · ${esc(r.size)}</span>
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
        _elRaw.innerHTML = '<span class="text-muted">' + t('msg_no_audit_runs_yet') + '</span>';
      } else {
        _elRaw.innerHTML = `
          <div class="grid kv-grid gap-y-1 gap-x-3">
            <span class="text-muted">${t('lbl_runs')}</span><span>${Number(raw.runs)}</span>
            <span class="text-muted">${t('lbl_latest_run')}</span><span>${esc(formatRunName(raw.latest))}</span>
            <span class="text-muted">${t('lbl_total_size')}</span><span>${esc(raw.total_size)}</span>
          </div>`;
      }
    }
  } catch (e) {
    content.innerHTML = '<div class="alert alert-error">' + t('err_could_not_load_files').replace('{msg}', esc(e.message)) + '</div>';
    content.style.display = 'block';
    noCustomer.style.display = 'none';
  }
}

var _unifiDirectDevices = [];
// The customer Nettverk's Enheter and Audit are working on: the one picked in
// their customer bar, which is this tab's current customer. Every save on
// these tabs goes to the customer the form was loaded for, never to whichever
// customer another tab opened since.
var _netCustomerId = null;

export function setNetCustomerId(id) {
  _netCustomerId = id;
}

registerToolCustomer('network', function() { loadNetworkDevices(); _clearNetworkAudit(); });

function _clearNetworkAudit() {
  var box = document.getElementById('net-audit-result');
  if (box) box.innerHTML = '';
  var list = document.getElementById('config-backups-list');
  if (list) list.innerHTML = '';
}

export async function loadNetworkDevices() {
  var box = document.getElementById('network-devices-content');
  if (!box) return;
  renderToolCustomerPickers();
  var cid = await toolCustomerId();
  _netCustomerId = cid;
  if (!cid) { box.innerHTML = toolNoCustomerHtml(); return; }
  try {
    var d = await apiFetch('/api/network-devices/' + encodeURIComponent(cid));
    if (_netCustomerId !== cid) return;
    if (!d) { box.innerHTML = '<span class="text-muted">' + t('kunne_ikke_laste_nettverksenheter') + '</span>'; return; }

    var html = '';

    // ── FortiGate ──
    html += '<div class="card mb-4">';
    html += '<div class="card-title">FortiGate</div>';
    if (d.fortigate) {
      html += '<div class="grid kv-grid gap-y-1 gap-x-3 mb-2 text-ui">';
      html += '<span class="text-muted">' + t('host') + '</span><span class="font-mono text-sm">' + esc(d.fortigate.host) + ':' + esc(d.fortigate.port) + '</span>';
      html += '<span class="text-muted">VDOM</span><span>' + esc(d.fortigate.vdom) + '</span>';
      html += '<span class="text-muted">' + t('api_token') + '</span><span>' + (d.fortigate.has_token ? '<span class="text-success">' + t('konfigurert') + '</span>' : '<span class="text-danger">' + t('mangler') + '</span>') + '</span>';
      html += '</div>';
      html += '<button class="btn btn-default btn-sm" data-click-handler="toggleNetworkConfig" data-config="fg-config">' + t('endre') + '</button>';
    } else {
      html += '<div class="text-ui text-dim mb-2">' + t('ikke_konfigurert_2') + '</div>';
      html += '<button class="btn btn-primary btn-sm" data-click-handler="toggleNetworkConfig" data-config="fg-config">' + t('konfigurer_fortigate') + '</button>';
    }
    html += '<div id="fg-config" class="inset mt-3" style="display:none;">';
    html += '<label class="field-label">' + t('host_ip_eller_fqdn') + '</label>';
    html += '<input class="field-input" id="input-fg-host" type="text" placeholder="192.168.1.1" value="' + esc((d.fortigate && d.fortigate.host) || '') + '">';
    html += '<div class="grid grid-cols-2 gap-2 mt-2">';
    html += '<div><label class="field-label">' + t('port') + '</label><input class="field-input" id="input-fg-port" type="number" value="' + esc((d.fortigate && d.fortigate.port) || 443) + '"></div>';
    html += '<div><label class="field-label">VDOM</label><input class="field-input" id="input-fg-vdom" type="text" value="' + esc((d.fortigate && d.fortigate.vdom) || 'root') + '"></div>';
    html += '</div>';
    html += '<label class="field-label mt-2">' + t('api_token') + '</label>';
    html += '<input class="field-input" id="input-fg-token" type="password" placeholder="Lim inn FortiGate REST API-token">';
    html += '<label class="flex items-center gap-2 mt-2 text-sm cursor-pointer"><input type="checkbox" id="input-fg-verify-ssl" ' + (d.fortigate && d.fortigate.verify_ssl ? 'checked' : '') + '> ' + t('verifiser_ssl_sertifikat') + '</label>';
    html += '<div class="flex gap-2 mt-3 items-center">';
    html += '<button class="btn btn-default btn-sm" data-click-handler="testFortiGate">' + t('test_tilkobling') + '</button>';
    html += '<button class="btn btn-primary btn-sm" data-click-handler="saveFortiGate">' + t('lagre_2') + '</button>';
    html += '<span id="fg-test-result" class="text-xs text-muted"></span>';
    html += '</div></div>';
    html += '</div>';

    // ── UniFi ──
    html += '<div class="card mb-4">';
    html += '<div class="card-title">UniFi</div>';

    var ufMode = (d.unifi && d.unifi.mode) || 'controller';
    _unifiDirectDevices = (d.unifi && d.unifi.direct_devices) || [];

    // Mode selector
    html += '<div class="flex gap-3 mb-4">';
    html += '<label class="flex items-center gap-2 text-ui cursor-pointer"><input type="radio" name="unifi-mode" value="controller" ' + (ufMode === 'controller' ? 'checked' : '') + ' data-change-handler="toggleUniFiMode"> ' + t('controller_2') + '</label>';
    html += '<label class="flex items-center gap-2 text-ui cursor-pointer"><input type="radio" name="unifi-mode" value="direct" ' + (ufMode === 'direct' ? 'checked' : '') + ' data-change-handler="toggleUniFiMode"> ' + t('direkte_enheter') + '</label>';
    html += '</div>';

    // Controller mode
    html += '<div id="unifi-controller-section"' + (ufMode === 'controller' ? '' : ' hidden') + '>';
    if (d.unifi && d.unifi.host && ufMode === 'controller') {
      html += '<div class="grid kv-grid gap-y-1 gap-x-3 mb-2 text-ui">';
      html += '<span class="text-muted">' + t('controller') + '</span><span class="font-mono text-sm">' + esc(d.unifi.host) + '</span>';
      html += '<span class="text-muted">' + t('type') + '</span><span>' + (d.unifi.is_unifi_os ? 'UniFi OS (UDM/CK)' : 'Classic') + '</span>';
      html += '<span class="text-muted">' + t('site') + '</span><span>' + esc(d.unifi.site) + '</span>';
      html += '<span class="text-muted">' + t('credentials') + '</span><span>' + (d.unifi.has_credentials ? '<span class="text-success">OK</span>' : '<span class="text-danger">' + t('mangler') + '</span>') + '</span>';
      html += '</div>';
      html += '<button class="btn btn-default btn-sm" data-click-handler="toggleNetworkConfig" data-config="uf-ctrl-config">' + t('endre') + '</button>';
    } else {
      html += '<div class="text-ui text-dim mb-2">' + t('ikke_konfigurert_2') + '</div>';
      html += '<button class="btn btn-primary btn-sm" data-click-handler="toggleNetworkConfig" data-config="uf-ctrl-config">' + t('konfigurer_controller') + '</button>';
    }
    html += '<div id="uf-ctrl-config" class="inset mt-3" style="display:none;">';
    html += '<label class="field-label">' + t('controller_url') + '</label>';
    html += '<input class="field-input" id="input-uf-host" type="text" placeholder="https://192.168.1.1:8443" value="' + esc((d.unifi && d.unifi.host) || '') + '">';
    html += '<div class="grid grid-cols-2 gap-2 mt-2">';
    html += '<div><label class="field-label">' + t('brukernavn') + '</label><input class="field-input" id="input-uf-user" type="text" placeholder="admin"></div>';
    html += '<div><label class="field-label">' + t('passord') + '</label><input class="field-input" id="input-uf-pass" type="password" placeholder="' + t('passord') + '"></div>';
    html += '</div>';
    html += '<label class="field-label mt-2">' + t('site') + '</label>';
    html += '<input class="field-input" id="input-uf-site" type="text" value="' + esc((d.unifi && d.unifi.site) || 'default') + '" placeholder="default">';
    html += '<label class="flex items-center gap-2 mt-2 text-sm cursor-pointer"><input type="checkbox" id="input-uf-os" ' + (d.unifi && d.unifi.is_unifi_os ? 'checked' : '') + '> ' + t('unifi_os_udm_cloud_key_gen2') + '</label>';
    html += '<div class="flex gap-2 mt-3 items-center">';
    html += '<button class="btn btn-default btn-sm" data-click-handler="testUniFi">' + t('test_tilkobling') + '</button>';
    html += '<button class="btn btn-primary btn-sm" data-click-handler="saveUniFi">' + t('lagre_2') + '</button>';
    html += '<span id="uf-test-result" class="text-xs text-muted"></span>';
    html += '</div></div>';
    html += '</div>';

    // Direct devices mode
    html += '<div id="unifi-direct-section"' + (ufMode === 'direct' ? '' : ' hidden') + '>';
    html += '<div class="text-sm text-muted mb-3">' + t('msg_unifi_direct_desc','Connect directly to individual UniFi devices via IP — no controller required.') + '</div>';
    html += '<div id="unifi-device-list"></div>';

    // Add device form (inline, not prompts)
    html += '<div class="mt-3 p-3 border border-dashed rounded">';
    html += '<div class="fw-semibold text-sm mb-2">' + t('btn_add_device','Add device') + '</div>';
    html += '<div class="grid grid-cols-2 gap-2">';
    html += '<div><label class="field-label">' + t('ip_adresse') + '</label><input class="field-input" id="input-uf-dev-host" type="text" placeholder="192.168.1.10"></div>';
    html += '<div><label class="field-label">' + t('type') + '</label><select class="field-input py-2 px-3" id="input-uf-dev-type"><option value="ap">' + t('access_point') + '</option><option value="gateway">' + t('gateway_firewall') + '</option><option value="switch">' + t('switch') + '</option></select></div>';
    html += '</div>';
    html += '<div class="grid grid-cols-2 gap-2 mt-2">';
    html += '<div><label class="field-label">' + t('brukernavn') + '</label><input class="field-input" id="input-uf-dev-user" type="text" value="ubnt" placeholder="ubnt"></div>';
    html += '<div><label class="field-label">' + t('passord') + '</label><input class="field-input" id="input-uf-dev-pass" type="password" value="ubnt" placeholder="ubnt"></div>';
    html += '</div>';
    html += '<button class="btn btn-primary btn-sm mt-2" data-click-handler="addUniFiDeviceFromForm">+ ' + t('btn_add','Add') + '</button>';
    html += '</div>';

    html += '<div class="mt-3"><button class="btn btn-primary btn-sm" data-click-handler="saveUniFiDirect">' + t('lagre_alle_enheter') + '</button></div>';
    html += '</div>';

    html += '</div>';

    box.innerHTML = html;
    renderUniFiDeviceList();
  } catch (e) {
    box.innerHTML = '<span class="text-muted">' + t('status_error','Error') + ': ' + esc(e.message) + '</span>';
  }
}

function toggleUniFiMode() {
  var mode = document.querySelector('input[name="unifi-mode"]:checked').value;
  document.getElementById('unifi-controller-section').hidden = mode !== 'controller';
  document.getElementById('unifi-direct-section').hidden = mode !== 'direct';
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
  var html = '<div class="flex flex-col gap-2">';
  for (var i = 0; i < _unifiDirectDevices.length; i++) {
    var dev = _unifiDirectDevices[i];
    var typeLabel = {ap:'Access Point', gateway:'Gateway/FW', switch:'Switch'}[dev.type || 'ap'] || dev.type;
    html += '<div class="inset flex items-center gap-2 text-sm">';
    html += '<span class="font-mono col-host">' + esc(dev.host || '') + '</span>';
    html += '<span class="text-muted col-type">' + esc(typeLabel) + '</span>';
    html += '<span class="text-muted">' + esc(dev.username || 'ubnt') + '</span>';
    html += '<span id="dev-status-' + i + '" class="ml-auto text-xs text-dim">' + esc(dev.status || '') + '</span>';
    html += '<button class="btn btn-ghost btn-sm" data-click-handler="testUniFiDevice" data-index="' + i + '">' + t('test') + '</button>';
    html += '<button class="btn btn-ghost btn-sm text-danger" data-click-handler="removeUniFiDevice" data-index="' + i + '">' + t('btn_remove','Remove') + '</button>';
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
  if (el) el.innerHTML = '<span class="text-muted">' + t('msg_testing','Testing...') + '</span>';
  try {
    var d = await apiFetch('/api/unifi/test-device', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({host: dev.host, username: dev.username, password: dev.password, device_type: dev.type})
    });

    if (d.ok) {
      var info = [d.model, d.firmware, d.hostname].filter(Boolean).join(' · ');
      var methods = [];
      if (d.http) methods.push('HTTP');
      if (d.ssh) methods.push('SSH');
      if (el) el.innerHTML = '<span class="text-success">OK (' + methods.join('+') + ')' + (info ? ' · ' + esc(info) : '') + '</span>';
      dev.status = 'OK';
    } else {
      if (el) el.innerHTML = '<span class="text-danger">' + esc(d.error || t('status_error','Error')) + '</span>';
    }
  } catch (e) {
    if (el) el.innerHTML = '<span class="text-danger">' + esc(e.message) + '</span>';
  }
}

export async function runNetworkQuickAudit() {
  var btn = document.getElementById('btn-run-network-audit');
  var box = document.getElementById('net-audit-result');
  var cid = await toolCustomerId();
  if (!cid) { box.innerHTML = toolNoCustomerHtml(); return; }
  btn.disabled = true;
  btn.textContent = t('status_running','Running...');
  box.innerHTML = '<div class="text-center p-6"><div class="loader loader-lg mx-auto mt-0 mb-3"></div>' + t('msg_loading_network_devices','Loading data from network devices...') + '</div>';

  try {
    var d = await apiFetch('/api/network/quick-audit/' + encodeURIComponent(cid), {method: 'POST'});
    if (currentCustomerId() !== cid) return;
    if (!d) { box.innerHTML = ''; return; }
    if (d.error) { box.innerHTML = '<div class="alert alert-error">' + esc(d.error) + '</div>'; return; }

    var html = '';
    // A count that a refused sub-read left null is unknown, not zero. Show "–"
    // so the grid does not print the literal "null" as if it were a measurement.
    var numOrDash = function(v) { return (v === null || v === undefined) ? '—' : esc(String(v)); };

    // FortiGate results
    if (d.fortigate) {
      var fg = d.fortigate;
      if (fg.error) {
        html += '<div class="card mb-4"><div class="card-title">FortiGate</div><div class="alert alert-error">' + esc(fg.error) + '</div></div>';
      } else {
        html += '<div class="card mb-4">';
        html += '<div class="card-title">FortiGate · ' + esc(fg.hostname) + '</div>';
        html += '<div class="grid grid-auto-sm gap-3 mb-4">';
        html += '<div class="kpi"><div class="text-xl fw-bold">' + esc(fg.firmware) + '</div><div class="text-xs text-muted">' + t('firmware') + '</div></div>';
        html += '<div class="kpi"><div class="text-xl fw-bold">' + numOrDash(fg.policy_count) + '</div><div class="text-xs text-muted">' + t('lbl_firewall_rules','Firewall rules') + '</div></div>';
        html += '<div class="kpi"><div class="text-xl fw-bold">' + numOrDash(fg.admin_count) + '</div><div class="text-xs text-muted">' + t('lbl_admin_accounts','Admin accounts') + '</div></div>';
        html += '<div class="kpi"><div class="text-xl fw-bold">' + numOrDash(fg.vpn_tunnels) + '</div><div class="text-xs text-muted">' + t('lbl_vpn_tunnels','VPN tunnels') + '</div></div>';
        html += '<div class="kpi"><div class="text-xl fw-bold">' + numOrDash(fg.interface_count) + '</div><div class="text-xs text-muted">' + t('interfaces') + '</div></div>';
        html += '<div class="kpi"><div class="text-xl fw-bold">' + esc(fg.ha_mode || '—') + '</div><div class="text-xs text-muted">' + t('lbl_ha_mode','HA mode') + '</div></div>';
        html += '</div>';

        // Admin table
        html += '<div class="subhead">' + t('admin_kontoer') + '</div>';
        html += '<table class="section-table w-full mb-3"><thead><tr><th>' + t('navn') + '</th><th>' + t('profil') + '</th><th>' + t('trusted_host') + '</th><th>' + t('fa') + '</th></tr></thead><tbody>';
        for (var a of fg.admins) {
          var thColor = a.trusthost ? 'var(--green)' : 'var(--red)';
          var tfaColor = a.two_factor ? 'var(--green)' : 'var(--red)';
          html += '<tr><td>' + esc(a.name) + '</td><td>' + esc(a.profile) + '</td>';
          html += '<td class="' + toneClass(thColor) + '">' + (a.trusthost ? 'Ja' : t('lbl_no','No')) + '</td>';
          html += '<td class="' + toneClass(tfaColor) + '">' + (a.two_factor ? 'Ja' : t('lbl_no','No')) + '</td></tr>';
        }
        html += '</tbody></table>';

        // Policy warnings
        if (fg.policy_warnings.length > 0) {
          html += '<div class="fw-semibold text-ui mb-2 text-danger">Advarsler (' + fg.policy_warnings.length + ')</div>';
          html += '<ul class="ml-4 text-sm text-muted">';
          for (var w of fg.policy_warnings) html += '<li>' + esc(w) + '</li>';
          html += '</ul>';
        } else {
          html += '<div class="text-sm text-success">' + t('ingen_policy_advarsler_funnet') + '</div>';
        }
        html += '<div class="text-xs text-dim mt-2">S/N: ' + esc(fg.serial) + ' | ' + t('lbl_model','Model') + ': ' + esc(fg.model) + ' | ' + t('lbl_uptime','Uptime') + ': ' + esc(fg.uptime) + '</div>';
        html += '</div>';
      }
    }

    // UniFi results
    if (d.unifi) {
      var uf = d.unifi;
      if (uf.error) {
        html += '<div class="card mb-4"><div class="card-title">UniFi</div><div class="alert alert-error">' + esc(uf.error) + '</div></div>';
      } else {
        html += '<div class="card mb-4">';
        html += '<div class="card-title">UniFi</div>';

        if (uf.mode === 'direct') {
          // Direct device mode — summary row
          html += '<div class="grid grid-auto-sm gap-3 mb-4">';
          html += '<div class="kpi"><div class="text-xl fw-bold">' + Number(uf.device_count) + '</div><div class="text-xs text-muted">' + t('lbl_devices_count','Devices') + '</div></div>';
          html += '<div class="kpi"><div class="text-xl fw-bold ' + (uf.reachable === uf.device_count ? 'text-success' : 'text-warning') + '">' + Number(uf.reachable) + '</div><div class="text-xs text-muted">' + t('lbl_reachable','Reachable') + '</div></div>';
          if (uf.default_creds_count > 0) {
            html += '<div class="kpi"><div class="text-xl fw-bold text-danger">' + Number(uf.default_creds_count) + '</div><div class="text-xs text-muted">' + t('lbl_default_password','Default password') + '</div></div>';
          }
          if (uf.outdated_firmware_count > 0) {
            html += '<div class="kpi"><div class="text-xl fw-bold text-warning">' + Number(uf.outdated_firmware_count) + '</div><div class="text-xs text-muted">' + t('lbl_outdated_firmware','Outdated firmware') + '</div></div>';
          }
          if (uf.eol_count > 0) {
            html += '<div class="kpi"><div class="text-xl fw-bold text-danger">' + Number(uf.eol_count) + '</div><div class="text-xs text-muted">' + t('end_of_life') + '</div></div>';
          }
          html += '</div>';

          // Per-device cards
          for (var idx = 0; idx < uf.devices.length; idx++) {
            var dev = uf.devices[idx];
            var borderColor = !dev.ok ? 'var(--red)' : (dev.default_credentials || dev.is_default_config ? 'var(--orange)' : 'var(--border)');
            html += '<div class="inset bg-none mb-3 ' + (borderColor === 'var(--border)' ? '' : 'border-' + toneName(borderColor)) + '" id="unifi-dev-card-' + idx + '">';

            // Header row
            html += '<div class="flex items-center justify-between mb-3">';
            html += '<div>';
            html += '<span class="fw-semibold text-base">' + esc(dev.hostname || dev.label || dev.host) + '</span>';
            if (dev.model) html += '<span class="text-muted text-sm ml-2">' + esc(dev.model) + '</span>';
            html += '</div>';
            html += '<div class="flex gap-2 items-center">';
            var typeLabels = {ap: 'Access Point', gateway: 'Gateway', switch: 'Switch'};
            html += '<span class="text-xs py-0-5 px-2 rounded-full bg-base border">' + esc(typeLabels[dev.device_type] || dev.device_type) + '</span>';
            if (dev.ok) {
              html += '<span class="text-xs text-success">' + t('online') + '</span>';
            } else {
              html += '<span class="text-xs text-danger">' + t('offline') + '</span>';
            }
            html += '</div></div>';

            if (!dev.ok && dev.error) {
              html += '<div class="alert alert-error m-0">' + esc(dev.error) + '</div>';
            } else {
              // Info grid — identity
              html += '<div class="grid grid-auto-sm gap-2 text-sm">';
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
                  html += '<div class="bg-base rounded-sm p-2">';
                  html += '<div class="text-muted text-2xs mb-0-5">' + esc(f[0]) + '</div>';
                  html += '<div class="text-xs break-all' + (monoFields.has(f[0]) ? ' font-mono' : '') + '">' + esc(f[1]) + '</div>';
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
                if (dev.fw_check.eol) findings.push({sev: 'critical', text: 'End-of-life · ' + esc(dev.fw_check.model) + ' ' + t('msg_no_longer_supported','is no longer supported by Ubiquiti')});
                else if (dev.fw_check.up_to_date === false) findings.push({sev: dev.fw_check.severity === 'critical' ? 'critical' : 'warning', text: t('warn_outdated_firmware','Outdated firmware: ') + esc(dev.fw_check.current) + ' → ' + t('msg_update_to','update to') + ' ' + esc(dev.fw_check.latest)});
                else if (dev.fw_check.up_to_date === true) findings.push({sev: 'ok', text: t('msg_firmware_updated','Firmware up to date') + ' (' + esc(dev.fw_check.latest) + ')'});
              }

              if (findings.length > 0) {
                html += '<div class="mt-3">';
                for (var fn of findings) {
                  var fc = fn.sev === 'critical' ? 'var(--red)' : fn.sev === 'warning' ? 'var(--orange)' : fn.sev === 'ok' ? 'var(--green)' : 'var(--text-muted)';
                  var icon = fn.sev === 'critical' ? '!' : fn.sev === 'warning' ? '!' : fn.sev === 'ok' ? '\u2713' : 'i';
                  html += '<div class="flex gap-2 items-start py-1 px-2 rounded-sm bg-base mb-1 text-sm">';
                  html += '<span class="' + toneClass(fc) + ' shrink-0">' + icon + '</span>';
                  html += '<span class="' + toneClass(fn.sev === 'info' ? 'var(--text-muted)' : fc) + '">' + esc(fn.text) + '</span>';
                  html += '</div>';
                }
                html += '</div>';
              }

              // Action buttons
              html += '<div class="flex gap-2 mt-3 flex-wrap">';
              // Set-inform
              html += '<button class="btn btn-default btn-sm" data-click-handler="unifiDeviceSetInform" data-host="' + esc(dev.host) + '">' + t('set_inform') + '</button>';
              // View config
              html += '<button class="btn btn-default btn-sm" data-click-handler="unifiDeviceConfig" data-host="' + esc(dev.host) + '">' + t('btn_view_config','View config') + '</button>';
              // Reboot
              html += '<button class="btn btn-default btn-sm text-warning" data-click-handler="unifiDeviceReboot" data-host="' + esc(dev.host) + '">' + t('btn_restart','Restart') + '</button>';
              html += '</div>';
              html += '<div id="unifi-action-' + idx + '" class="mt-2"></div>';
            }
            html += '</div>';
          }
        } else {
          // Controller mode
          html += '<div class="grid grid-auto-sm gap-3 mb-4">';
          html += '<div class="kpi"><div class="text-xl fw-bold">' + numOrDash(uf.device_count) + '</div><div class="text-xs text-muted">' + t('lbl_devices_count','Devices') + '</div></div>';
          html += '<div class="kpi"><div class="text-xl fw-bold">' + numOrDash(uf.wlan_count) + '</div><div class="text-xs text-muted">' + t('lbl_ssids','SSIDs') + '</div></div>';
          html += '<div class="kpi"><div class="text-xl fw-bold">' + numOrDash(uf.network_count) + '</div><div class="text-xs text-muted">' + t('lbl_networks','Networks') + '</div></div>';
          html += '<div class="kpi"><div class="text-xl fw-bold">' + numOrDash(uf.firewall_rules) + '</div><div class="text-xs text-muted">' + t('lbl_firewall_rules','Firewall rules') + '</div></div>';
          html += '<div class="kpi"><div class="text-xl fw-bold ' + (uf.active_alarms == null ? 'text-muted' : (uf.active_alarms > 0 ? 'text-danger' : 'text-success')) + '">' + numOrDash(uf.active_alarms) + '</div><div class="text-xs text-muted">' + t('lbl_active_alarms','Active alarms') + '</div></div>';
          html += '</div>';

          // Device table
          html += '<div class="subhead">' + t('lbl_devices_count','Devices') + '</div>';
          html += '<table class="section-table w-full mb-3"><thead><tr><th>' + t('lbl_name','Name') + '</th><th>' + t('lbl_type','Type') + '</th><th>' + t('lbl_model','Model') + '</th><th>' + t('firmware') + '</th><th>' + t('lbl_upgrade','Upgrade') + '</th><th>' + t('lbl_clients','Clients') + '</th><th>' + t('status') + '</th></tr></thead><tbody>';
          for (const dev of uf.devices) {
            var statusColor = dev.status === 'online' ? 'var(--green)' : 'var(--red)';
            var upgradeHtml = dev.upgrade ? '<span class="text-warning">' + esc(dev.upgrade) + '</span>' : '<span class="text-success">OK</span>';
            html += '<tr><td>' + esc(dev.name) + '</td><td>' + esc(dev.type) + '</td><td>' + esc(dev.model) + '</td>';
            html += '<td class="font-mono text-xs">' + esc(dev.firmware) + '</td>';
            html += '<td>' + upgradeHtml + '</td>';
            html += '<td>' + Number(dev.clients) + '</td>';
            html += '<td class="' + toneClass(statusColor) + '">' + esc(dev.status) + '</td></tr>';
          }
          html += '</tbody></table>';

          // WLAN table
          if (uf.wlans && uf.wlans.length > 0) {
            html += '<div class="subhead">' + t('lbl_wireless_networks','Wireless networks') + '</div>';
            html += '<table class="section-table w-full"><thead><tr><th>SSID</th><th>' + t('lbl_security','Security') + '</th><th>' + t('lbl_guest','Guest') + '</th><th>' + t('lbl_active','Active') + '</th></tr></thead><tbody>';
            for (const w of uf.wlans) {
              var secColor = w.security === 'open' ? 'var(--red)' : 'var(--green)';
              html += '<tr><td>' + esc(w.name) + '</td>';
              html += '<td class="' + toneClass(secColor) + '">' + esc(w.security) + '</td>';
              html += '<td>' + (w.guest ? t('lbl_yes','Yes') : t('lbl_no','No')) + '</td>';
              html += '<td>' + (w.enabled ? t('lbl_yes','Yes') : '<span class="text-dim">' + t('lbl_no','No') + '</span>') + '</td></tr>';
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
  if (!_netCustomerId) return;
  try {
    var d = await apiFetch('/api/unifi/save/' + encodeURIComponent(_netCustomerId), {
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
      showToast(t('msg_inform_sent').replace('{host}', host) + ' · ' + (d.output || 'OK'), 'success', 8000);
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
  if (targetEl) targetEl.innerHTML = '<div class="p-2 text-muted text-sm">' + t('msg_loading_config','Loading configuration...') + '</div>';

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
      if (_netCustomerId) apiFetch('/api/network/save-config-backup/' + encodeURIComponent(_netCustomerId), {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({host: host, config: d.config})
      }).catch(function() {});
      if (targetEl) {
        targetEl.innerHTML = '<div class="mt-1"><div class="flex items-center justify-between"><div class="fw-semibold text-sm">' + t('lbl_running_config','Running configuration') + '</div><span class="text-2xs text-success">' + t('msg_backup_saved','Backup saved') + '</span></div>'
          + '<pre class="inset max-h-md overflow-auto text-xs pre-wrap break-all">'
          + esc(d.config) + '</pre>'
          + '<button class="btn btn-default btn-sm mt-2" data-click-handler="unifiDeviceConfigClose">' + t('btn_close','Close') + '</button></div>';
      } else {
        showToast(d.config.substring(0, 2000), 'info', 10000);
      }
    } else {
      const msg = t('status_error') + ': ' + (d.error || t('msg_no_config'));
      if (targetEl) targetEl.innerHTML = '<div class="alert alert-error text-sm">' + esc(msg) + '</div>';
      else showToast(msg, 'error');
    }
  } catch (e) {
    const msg = t('status_error') + ': ' + e.message;
    if (targetEl) targetEl.innerHTML = '<div class="alert alert-error text-sm">' + esc(msg) + '</div>';
    else showToast(msg, 'error');
  }
}

// ── Subnet scanner ──

export async function runSubnetScan() {
  var btn = document.getElementById('btn-subnet-scan');
  var box = document.getElementById('subnet-scan-result');
  var subnet = document.getElementById('input-scan-subnet').value.trim();
  if (!subnet) { showToast(t('msg_enter_subnet'), 'warning'); return; }
  btn.disabled = true;
  btn.textContent = t('msg_scanning','Scanning...');
  box.innerHTML = '<div class="text-center p-4"><div class="loader loader-md mx-auto mt-0 mb-2"></div>' + t('msg_scanning','Scanning...').replace('...','') + ' ' + esc(subnet) + '...</div>';

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
      box.innerHTML = '<div class="p-3 text-muted text-ui">' + t('msg_no_devices_found','No devices found in') + ' ' + esc(subnet) + '</div>';
      return;
    }

    var html = '<div class="text-ui mb-2"><strong>' + d.found.length + '</strong> ' + t('msg_devices_found_in','devices found in') + ' ' + esc(subnet) + '</div>';
    html += '<table class="section-table w-full"><thead><tr><th>IP</th><th>SSH</th><th>HTTPS</th><th>UniFi</th><th>' + t('info') + '</th><th>' + t('btn_actions','Actions') + '</th></tr></thead><tbody>';
    for (var dev of d.found) {
      var isUf = dev.is_unifi ? '<span class="text-success">' + t('lbl_yes','Yes') + '</span>' : '<span class="text-muted">' + t('lbl_no','No') + '</span>';
      var hostSafe = esc(dev.host);
      var hostId = String(dev.host).replace(/[^a-zA-Z0-9_-]/g, '_');
      html += '<tr>';
      html += '<td class="font-mono text-sm">' + hostSafe + '</td>';
      html += '<td>' + (dev.ssh ? '<span class="text-success">&#10003;</span>' : '—') + '</td>';
      html += '<td>' + (dev.https ? '<span class="text-success">&#10003;</span>' : '—') + '</td>';
      html += '<td>' + isUf + '</td>';
      html += '<td class="text-xs text-muted">' + esc(dev.device_hint || dev.ssh_banner || '') + '</td>';
      html += '<td class="nowrap">';
      var alreadyAdded = _unifiDirectDevices.some(function(d2) { return d2.host === dev.host; });
      if (alreadyAdded) {
        html += '<button class="btn btn-default btn-sm text-success" disabled>' + t('status_added','Added') + '</button> ';
      } else {
        html += '<button class="btn btn-default btn-sm" id="scan-add-' + hostId + '" data-click-handler="addScannedDevice" data-host="' + hostSafe + '">' + t('btn_add','Add') + '</button> ';
      }
      if (dev.ssh) {
        html += '<button class="btn btn-default btn-sm" data-click-handler="scanDeviceSetInform" data-host="' + hostSafe + '">' + t('set_inform') + '</button> ';
        html += '<button class="btn btn-default btn-sm" data-click-handler="scanDeviceConfig" data-host="' + hostSafe + '" data-row-id="scan-cfg-' + hostId + '">' + t('btn_view_config','Vis konfig') + '</button> ';
        html += '<button class="btn btn-default btn-sm" data-click-handler="scanDeviceReboot" data-host="' + hostSafe + '">' + t('btn_restart','Restart') + '</button>';
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
    if (!_netCustomerId) return;
    var d = await apiFetch('/api/unifi/save/' + encodeURIComponent(_netCustomerId), {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mode: 'direct', devices: _unifiDirectDevices})
    });

    if (d.ok) {
      if (btnEl) { btnEl.textContent = t('status_added','Added'); btnEl.style.color = 'var(--green)'; }
      loadNetworkDevices();
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
  var pickHtml = '<div class="flex flex-col gap-2 mb-3">';
  for (var p of presets) {
    pickHtml += '<button class="btn btn-primary btn-sm" data-click-handler="doScanSetInform" data-host="' + esc(host) + '" data-url="' + esc(p.url) + '">' + esc(p.label) + ' <span class="text-2xs opacity-70 ml-1">' + esc(p.url) + '</span></button>';
  }
  pickHtml += '</div>';
  pickHtml += '<div class="text-sm text-muted mb-1">' + t('eller_angi_manuelt') + '</div>';
  pickHtml += '<div class="flex gap-2 items-center">';
  pickHtml += '<input class="field-input flex-1 m-0" id="scan-inform-custom-url" type="text" placeholder="http://controller:8080/inform">';
  pickHtml += '<button class="btn btn-default btn-sm nowrap" data-click-handler="doScanSetInformCustomUrl" data-host="' + esc(host) + '">' + t('btn_send','Send') + '</button>';
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
      showToast(t('msg_inform_sent').replace('{host}', host) + ' · ' + (d.output || 'OK'), 'success', 8000);
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
  cell.innerHTML = '<div class="p-2 text-muted text-sm">' + t('msg_loading_config','Loading configuration...') + '</div>';
  var creds = _scanDeviceCreds(host);
  try {
    var d = await apiFetch('/api/unifi/device-config', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(creds)
    });
    if (!d) { row.style.display = 'none'; cell.innerHTML = ''; return; }
    if (d.ok && d.config) {
      if (_netCustomerId) apiFetch('/api/network/save-config-backup/' + encodeURIComponent(_netCustomerId), {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({host: host, config: d.config})
      }).catch(function() {});
      cell.innerHTML = '<div class="p-2"><div class="flex items-center justify-between mb-1">'
        + '<span class="fw-semibold text-sm">' + t('lbl_running_config','Running configuration') + ' · ' + esc(host) + '</span>'
        + '<span class="text-2xs text-success">' + t('msg_backup_saved','Backup saved') + '</span></div>'
        + '<pre class="inset max-h-md overflow-auto text-xs pre-wrap break-all">' + esc(d.config) + '</pre>'
        + '<button class="btn btn-default btn-sm mt-2" data-click-handler="scanDeviceConfigClose" data-row-id="' + esc(rowId) + '">' + t('btn_close','Close') + '</button></div>';
    } else {
      cell.innerHTML = '<div class="alert alert-error text-sm">' + esc(d.error || t('msg_no_config','No config')) + '</div>';
    }
  } catch (e) {
    cell.innerHTML = '<div class="alert alert-error text-sm">' + esc(e.message) + '</div>';
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

export async function loadConfigBackups() {
  var box = document.getElementById('config-backups-list');
  box.innerHTML = '<div class="text-muted text-sm">' + t('msg_loading','Loading...') + '</div>';
  try {
    var cid = await toolCustomerId();
    if (!cid) { if (box) box.innerHTML = toolNoCustomerHtml(); return; }
    var d = await apiFetch('/api/network/config-backups/' + encodeURIComponent(cid));
    if (currentCustomerId() !== cid) return;
    if (!d.backups || d.backups.length === 0) {
      box.innerHTML = emptyStateHTML({
        variant: 'inline',
        icon: '\u{1F4BE}',
        title: t('msg_no_backups_yet_title', 'Ingen config-backups lagret ennå'),
        desc: t('empty_backups_desc', 'Åpne en enhet og bruk «Vis konfig» — backupen tas automatisk ved første visning.'),
      });
      return;
    }
    var html = '<table class="section-table w-full"><thead><tr><th>' + t('lbl_timestamp','Timestamp') + '</th><th>' + t('lbl_device','Device') + '</th><th>' + t('lbl_size','Size') + '</th></tr></thead><tbody>';
    for (var b of d.backups) {
      html += '<tr>';
      html += '<td class="text-sm">' + esc(b.timestamp) + '</td>';
      html += '<td class="font-mono text-sm">' + esc(b.host) + '</td>';
      html += '<td class="text-sm">' + Math.round(b.size / 1024) + ' KB</td>';
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
      res.innerHTML = '<span class="text-success">OK · ' + esc(d.hostname) + ' (FW: ' + esc(d.firmware) + ', S/N: ' + esc(d.serial) + ')</span>';
    } else {
      res.innerHTML = '<span class="text-danger">' + t('status_error','Error') + ': ' + esc(d && d.error ? d.error : t('err_connection_failed','Connection failed')) + '</span>';
    }
  } catch (e) {
    res.innerHTML = '<span class="text-danger">' + esc(e.message) + '</span>';
  }
}

async function saveFortiGate() {
  var res = document.getElementById('fg-test-result');
  try {
    if (!_netCustomerId) return;
    var d = await apiFetch('/api/fortigate/save/' + encodeURIComponent(_netCustomerId), {
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
      res.innerHTML = '<span class="text-success">' + t('msg_saved','Saved') + '</span>';
      loadNetworkDevices();
    } else {
      res.innerHTML = '<span class="text-danger">' + esc(d && d.error ? d.error : t('err_save_failed','Save failed')) + '</span>';
    }
  } catch (e) {
    res.innerHTML = '<span class="text-danger">' + esc(e.message) + '</span>';
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
      res.innerHTML = '<span class="text-success">OK · ' + Number(d.sites) + ' site(s) (' + esc(d.controller_type) + '): ' + esc((d.site_names||[]).join(', ')) + '</span>';
    } else {
      res.innerHTML = '<span class="text-danger">' + t('lbl_error','Feil') + ': ' + esc(d.error) + '</span>';
    }
  } catch (e) {
    res.innerHTML = '<span class="text-danger">' + esc(e.message) + '</span>';
  }
}

async function saveUniFi() {
  var res = document.getElementById('uf-test-result');
  try {
    if (!_netCustomerId) return;
    var d = await apiFetch('/api/unifi/save/' + encodeURIComponent(_netCustomerId), {
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
      res.innerHTML = '<span class="text-success">' + t('lagret') + '</span>';
      loadNetworkDevices();
    } else {
      res.innerHTML = '<span class="text-danger">' + esc(d.error) + '</span>';
    }
  } catch (e) {
    res.innerHTML = '<span class="text-danger">' + esc(e.message) + '</span>';
  }
}

export async function testITGlue() {
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
      result.innerHTML = `<span class="text-success">✓ Tilkoblet (${Number(d.organizations)} organisasjoner)</span>`;
    } else {
      result.innerHTML = `<span class="text-danger">✗ ${d ? esc(d.error) : t('status_error','Error')}</span>`;
    }
  } catch(e) {
    result.innerHTML = `<span class="text-danger">✗ ${esc(e.message)}</span>`;
  }
}
