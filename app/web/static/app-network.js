// ═══════════════════════════════════════════════════════════════════
// NETWORK — files, UniFi devices, subnet scan & config backup
// ═══════════════════════════════════════════════════════════════════

import {esc} from './app-esc.js';
import {t} from './app-i18n.js';
import {registerUiHandlers} from './app-handlers.js';
import {registerToolCustomer} from './app-hooks.js';
import {_custPage, currentCustomerId} from './app-state.js';
import {formatRunName} from './app-format.js';
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
        _elRaw.innerHTML = '<span style="color:var(--text-muted);">' + t('msg_no_audit_runs_yet') + '</span>';
      } else {
        _elRaw.innerHTML = `
          <div style="display:grid;grid-template-columns:140px 1fr;gap:4px 12px;">
            <span style="color:var(--text-muted);">${t('lbl_runs')}</span><span>${Number(raw.runs)}</span>
            <span style="color:var(--text-muted);">${t('lbl_latest_run')}</span><span>${esc(formatRunName(raw.latest))}</span>
            <span style="color:var(--text-muted);">${t('lbl_total_size')}</span><span>${esc(raw.total_size)}</span>
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
    if (!d) { box.innerHTML = '<span style="color:var(--text-muted);">' + t('kunne_ikke_laste_nettverksenheter') + '</span>'; return; }

    var html = '';

    // ── FortiGate ──
    html += '<div class="card" style="margin-bottom:16px;">';
    html += '<div class="card-title">FortiGate</div>';
    if (d.fortigate) {
      html += '<div style="display:grid;grid-template-columns:140px 1fr;gap:4px 12px;margin-bottom:8px;font-size:13px;">';
      html += '<span style="color:var(--text-muted);">' + t('host') + '</span><span style="font-family:var(--mono);font-size:12px;">' + esc(d.fortigate.host) + ':' + esc(d.fortigate.port) + '</span>';
      html += '<span style="color:var(--text-muted);">VDOM</span><span>' + esc(d.fortigate.vdom) + '</span>';
      html += '<span style="color:var(--text-muted);">' + t('api_token') + '</span><span>' + (d.fortigate.has_token ? '<span style="color:var(--green);">' + t('konfigurert') + '</span>' : '<span style="color:var(--red);">' + t('mangler') + '</span>') + '</span>';
      html += '</div>';
      html += '<button class="btn btn-default" data-click-handler="toggleNetworkConfig" data-config="fg-config" style="font-size:12px;padding:4px 12px;">' + t('endre') + '</button>';
    } else {
      html += '<div style="font-size:13px;color:var(--text-dim);margin-bottom:8px;">' + t('ikke_konfigurert_2') + '</div>';
      html += '<button class="btn btn-primary" data-click-handler="toggleNetworkConfig" data-config="fg-config" style="font-size:12px;padding:5px 14px;">' + t('konfigurer_fortigate') + '</button>';
    }
    html += '<div id="fg-config" style="display:none;margin-top:12px;padding:12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);">';
    html += '<label class="field-label">' + t('host_ip_eller_fqdn') + '</label>';
    html += '<input class="field-input" id="input-fg-host" type="text" placeholder="192.168.1.1" value="' + esc((d.fortigate && d.fortigate.host) || '') + '">';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">';
    html += '<div><label class="field-label">' + t('port') + '</label><input class="field-input" id="input-fg-port" type="number" value="' + esc((d.fortigate && d.fortigate.port) || 443) + '"></div>';
    html += '<div><label class="field-label">VDOM</label><input class="field-input" id="input-fg-vdom" type="text" value="' + esc((d.fortigate && d.fortigate.vdom) || 'root') + '"></div>';
    html += '</div>';
    html += '<label class="field-label" style="margin-top:8px;">' + t('api_token') + '</label>';
    html += '<input class="field-input" id="input-fg-token" type="password" placeholder="Lim inn FortiGate REST API-token">';
    html += '<label style="display:flex;align-items:center;gap:6px;margin-top:8px;font-size:12px;cursor:pointer;"><input type="checkbox" id="input-fg-verify-ssl" ' + (d.fortigate && d.fortigate.verify_ssl ? 'checked' : '') + '> ' + t('verifiser_ssl_sertifikat') + '</label>';
    html += '<div style="display:flex;gap:8px;margin-top:12px;align-items:center;">';
    html += '<button class="btn btn-default" data-click-handler="testFortiGate" style="font-size:12px;padding:4px 12px;">' + t('test_tilkobling') + '</button>';
    html += '<button class="btn btn-primary" data-click-handler="saveFortiGate" style="font-size:12px;padding:4px 12px;">' + t('lagre_2') + '</button>';
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
    html += '<label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;"><input type="radio" name="unifi-mode" value="controller" ' + (ufMode === 'controller' ? 'checked' : '') + ' data-change-handler="toggleUniFiMode"> ' + t('controller_2') + '</label>';
    html += '<label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;"><input type="radio" name="unifi-mode" value="direct" ' + (ufMode === 'direct' ? 'checked' : '') + ' data-change-handler="toggleUniFiMode"> ' + t('direkte_enheter') + '</label>';
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
      html += '<button class="btn btn-default" data-click-handler="toggleNetworkConfig" data-config="uf-ctrl-config" style="font-size:12px;padding:4px 12px;">' + t('endre') + '</button>';
    } else {
      html += '<div style="font-size:13px;color:var(--text-dim);margin-bottom:8px;">' + t('ikke_konfigurert_2') + '</div>';
      html += '<button class="btn btn-primary" data-click-handler="toggleNetworkConfig" data-config="uf-ctrl-config" style="font-size:12px;padding:5px 14px;">' + t('konfigurer_controller') + '</button>';
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
    html += '<button class="btn btn-default" data-click-handler="testUniFi" style="font-size:12px;padding:4px 12px;">' + t('test_tilkobling') + '</button>';
    html += '<button class="btn btn-primary" data-click-handler="saveUniFi" style="font-size:12px;padding:4px 12px;">' + t('lagre_2') + '</button>';
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
    html += '<button class="btn btn-primary" data-click-handler="addUniFiDeviceFromForm" style="font-size:12px;padding:5px 14px;margin-top:8px;">+ ' + t('btn_add','Add') + '</button>';
    html += '</div>';

    html += '<div style="margin-top:12px;"><button class="btn btn-primary" data-click-handler="saveUniFiDirect" style="font-size:12px;padding:5px 14px;">' + t('lagre_alle_enheter') + '</button></div>';
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
    html += '<span id="dev-status-' + i + '" style="margin-left:auto;font-size:11px;color:var(--text-dim);">' + esc(dev.status || '') + '</span>';
    html += '<button class="btn btn-ghost" data-click-handler="testUniFiDevice" data-index="' + i + '" style="font-size:11px;padding:2px 8px;">' + t('test') + '</button>';
    html += '<button class="btn btn-ghost" data-click-handler="removeUniFiDevice" data-index="' + i + '" style="font-size:11px;padding:2px 8px;color:var(--red);">' + t('btn_remove','Remove') + '</button>';
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
      var info = [d.model, d.firmware, d.hostname].filter(Boolean).join(' · ');
      var methods = [];
      if (d.http) methods.push('HTTP');
      if (d.ssh) methods.push('SSH');
      if (el) el.innerHTML = '<span style="color:var(--green);">OK (' + methods.join('+') + ')' + (info ? ' · ' + esc(info) : '') + '</span>';
      dev.status = 'OK';
    } else {
      if (el) el.innerHTML = '<span style="color:var(--red);">' + esc(d.error || t('status_error','Error')) + '</span>';
    }
  } catch (e) {
    if (el) el.innerHTML = '<span style="color:var(--red);">' + esc(e.message) + '</span>';
  }
}

export async function runNetworkQuickAudit() {
  var btn = document.getElementById('btn-run-network-audit');
  var box = document.getElementById('net-audit-result');
  var cid = await toolCustomerId();
  if (!cid) { box.innerHTML = toolNoCustomerHtml(); return; }
  btn.disabled = true;
  btn.textContent = t('status_running','Running...');
  box.innerHTML = '<div style="text-align:center;padding:24px;"><div class="loader" style="width:24px;height:24px;margin:0 auto 12px;"></div>' + t('msg_loading_network_devices','Loading data from network devices...') + '</div>';

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
        html += '<div class="card" style="margin-bottom:16px;"><div class="card-title">FortiGate</div><div class="alert alert-error">' + esc(fg.error) + '</div></div>';
      } else {
        html += '<div class="card" style="margin-bottom:16px;">';
        html += '<div class="card-title">FortiGate · ' + esc(fg.hostname) + '</div>';
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-bottom:16px;">';
        html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + esc(fg.firmware) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('firmware') + '</div></div>';
        html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + numOrDash(fg.policy_count) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_firewall_rules','Firewall rules') + '</div></div>';
        html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + numOrDash(fg.admin_count) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_admin_accounts','Admin accounts') + '</div></div>';
        html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + numOrDash(fg.vpn_tunnels) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_vpn_tunnels','VPN tunnels') + '</div></div>';
        html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + numOrDash(fg.interface_count) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('interfaces') + '</div></div>';
        html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + esc(fg.ha_mode || '—') + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_ha_mode','HA mode') + '</div></div>';
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
          html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;">' + Number(uf.device_count) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_devices_count','Devices') + '</div></div>';
          html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;color:' + (uf.reachable === uf.device_count ? 'var(--green)' : 'var(--orange)') + ';">' + Number(uf.reachable) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_reachable','Reachable') + '</div></div>';
          if (uf.default_creds_count > 0) {
            html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;color:var(--red);">' + Number(uf.default_creds_count) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_default_password','Default password') + '</div></div>';
          }
          if (uf.outdated_firmware_count > 0) {
            html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;color:var(--orange);">' + Number(uf.outdated_firmware_count) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('lbl_outdated_firmware','Outdated firmware') + '</div></div>';
          }
          if (uf.eol_count > 0) {
            html += '<div style="padding:12px;background:var(--bg);border-radius:6px;text-align:center;"><div style="font-size:20px;font-weight:700;color:var(--red);">' + Number(uf.eol_count) + '</div><div style="font-size:11px;color:var(--text-muted);">' + t('end_of_life') + '</div></div>';
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
                  html += '<div style="color:var(--text-muted);font-size:10px;margin-bottom:2px;">' + esc(f[0]) + '</div>';
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
                if (dev.fw_check.eol) findings.push({sev: 'critical', text: 'End-of-life · ' + esc(dev.fw_check.model) + ' ' + t('msg_no_longer_supported','is no longer supported by Ubiquiti')});
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
              html += '<button class="btn btn-default" style="font-size:11px;padding:4px 10px;" data-click-handler="unifiDeviceSetInform" data-host="' + esc(dev.host) + '">' + t('set_inform') + '</button>';
              // View config
              html += '<button class="btn btn-default" style="font-size:11px;padding:4px 10px;" data-click-handler="unifiDeviceConfig" data-host="' + esc(dev.host) + '">' + t('btn_view_config','View config') + '</button>';
              // Reboot
              html += '<button class="btn btn-default" style="font-size:11px;padding:4px 10px;color:var(--orange);" data-click-handler="unifiDeviceReboot" data-host="' + esc(dev.host) + '">' + t('btn_restart','Restart') + '</button>';
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
          for (const dev of uf.devices) {
            var statusColor = dev.status === 'online' ? 'var(--green)' : 'var(--red)';
            var upgradeHtml = dev.upgrade ? '<span style="color:var(--orange);">' + esc(dev.upgrade) + '</span>' : '<span style="color:var(--green);">OK</span>';
            html += '<tr><td>' + esc(dev.name) + '</td><td>' + esc(dev.type) + '</td><td>' + esc(dev.model) + '</td>';
            html += '<td style="font-family:var(--mono);font-size:11px;">' + esc(dev.firmware) + '</td>';
            html += '<td>' + upgradeHtml + '</td>';
            html += '<td>' + Number(dev.clients) + '</td>';
            html += '<td style="color:' + statusColor + ';">' + esc(dev.status) + '</td></tr>';
          }
          html += '</tbody></table>';

          // WLAN table
          if (uf.wlans && uf.wlans.length > 0) {
            html += '<div style="font-weight:600;font-size:13px;margin-bottom:6px;">' + t('lbl_wireless_networks','Wireless networks') + '</div>';
            html += '<table class="section-table" style="width:100%;"><thead><tr><th>SSID</th><th>' + t('lbl_security','Security') + '</th><th>' + t('lbl_guest','Guest') + '</th><th>' + t('lbl_active','Active') + '</th></tr></thead><tbody>';
            for (const w of uf.wlans) {
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
      if (_netCustomerId) apiFetch('/api/network/save-config-backup/' + encodeURIComponent(_netCustomerId), {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({host: host, config: d.config})
      }).catch(function() {});
      if (targetEl) {
        targetEl.innerHTML = '<div style="margin-top:4px;"><div style="display:flex;align-items:center;justify-content:space-between;"><div style="font-weight:600;font-size:12px;">' + t('lbl_running_config','Running configuration') + '</div><span style="font-size:10px;color:var(--green);">' + t('msg_backup_saved','Backup saved') + '</span></div>'
          + '<pre style="max-height:300px;overflow:auto;padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;font-size:11px;white-space:pre-wrap;word-break:break-all;">'
          + esc(d.config) + '</pre>'
          + '<button class="btn btn-default" style="font-size:11px;padding:3px 8px;margin-top:6px;" data-click-handler="unifiDeviceConfigClose">' + t('btn_close','Close') + '</button></div>';
      } else {
        showToast(d.config.substring(0, 2000), 'info', 10000);
      }
    } else {
      const msg = t('status_error') + ': ' + (d.error || t('msg_no_config'));
      if (targetEl) targetEl.innerHTML = '<div class="alert alert-error" style="font-size:12px;">' + esc(msg) + '</div>';
      else showToast(msg, 'error');
    }
  } catch (e) {
    const msg = t('status_error') + ': ' + e.message;
    if (targetEl) targetEl.innerHTML = '<div class="alert alert-error" style="font-size:12px;">' + esc(msg) + '</div>';
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
      var hostId = String(dev.host).replace(/[^a-zA-Z0-9_-]/g, '_');
      html += '<tr>';
      html += '<td style="font-family:var(--mono);font-size:12px;">' + hostSafe + '</td>';
      html += '<td>' + (dev.ssh ? '<span style="color:var(--green);">&#10003;</span>' : '—') + '</td>';
      html += '<td>' + (dev.https ? '<span style="color:var(--green);">&#10003;</span>' : '—') + '</td>';
      html += '<td>' + isUf + '</td>';
      html += '<td style="font-size:11px;color:var(--text-muted);">' + esc(dev.device_hint || dev.ssh_banner || '') + '</td>';
      html += '<td style="white-space:nowrap;">';
      var alreadyAdded = _unifiDirectDevices.some(function(d2) { return d2.host === dev.host; });
      if (alreadyAdded) {
        html += '<button class="btn btn-default" style="font-size:10px;padding:2px 8px;color:var(--green);" disabled>' + t('status_added','Added') + '</button> ';
      } else {
        html += '<button class="btn btn-default" style="font-size:10px;padding:2px 8px;" id="scan-add-' + hostId + '" data-click-handler="addScannedDevice" data-host="' + hostSafe + '">' + t('btn_add','Add') + '</button> ';
      }
      if (dev.ssh) {
        html += '<button class="btn btn-default" style="font-size:10px;padding:2px 8px;" data-click-handler="scanDeviceSetInform" data-host="' + hostSafe + '">' + t('set_inform') + '</button> ';
        html += '<button class="btn btn-default" style="font-size:10px;padding:2px 8px;" data-click-handler="scanDeviceConfig" data-host="' + hostSafe + '" data-row-id="scan-cfg-' + hostId + '">' + t('btn_view_config','Vis konfig') + '</button> ';
        html += '<button class="btn btn-default" style="font-size:10px;padding:2px 8px;" data-click-handler="scanDeviceReboot" data-host="' + hostSafe + '">' + t('btn_restart','Restart') + '</button>';
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
  var pickHtml = '<div style="display:flex;flex-direction:column;gap:8px;margin-bottom:12px;">';
  for (var p of presets) {
    pickHtml += '<button class="btn btn-primary" style="font-size:12px;padding:8px 14px;" data-click-handler="doScanSetInform" data-host="' + esc(host) + '" data-url="' + esc(p.url) + '">' + esc(p.label) + ' <span style="font-size:10px;opacity:0.7;margin-left:4px;">' + esc(p.url) + '</span></button>';
  }
  pickHtml += '</div>';
  pickHtml += '<div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">' + t('eller_angi_manuelt') + '</div>';
  pickHtml += '<div style="display:flex;gap:6px;align-items:center;">';
  pickHtml += '<input class="field-input" id="scan-inform-custom-url" type="text" placeholder="http://controller:8080/inform" style="flex:1;margin:0;">';
  pickHtml += '<button class="btn btn-default" style="font-size:12px;padding:6px 12px;white-space:nowrap;" data-click-handler="doScanSetInformCustomUrl" data-host="' + esc(host) + '">' + t('btn_send','Send') + '</button>';
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
  cell.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:12px;">' + t('msg_loading_config','Loading configuration...') + '</div>';
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
      cell.innerHTML = '<div style="padding:6px;"><div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">'
        + '<span style="font-weight:600;font-size:12px;">' + t('lbl_running_config','Running configuration') + ' · ' + esc(host) + '</span>'
        + '<span style="font-size:10px;color:var(--green);">' + t('msg_backup_saved','Backup saved') + '</span></div>'
        + '<pre style="max-height:300px;overflow:auto;padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;font-size:11px;white-space:pre-wrap;word-break:break-all;">' + esc(d.config) + '</pre>'
        + '<button class="btn btn-default" style="font-size:11px;padding:3px 8px;margin-top:6px;" data-click-handler="scanDeviceConfigClose" data-row-id="' + esc(rowId) + '">' + t('btn_close','Close') + '</button></div>';
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

export async function loadConfigBackups() {
  var box = document.getElementById('config-backups-list');
  box.innerHTML = '<div style="color:var(--text-muted);font-size:12px;">' + t('msg_loading','Loading...') + '</div>';
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
      res.innerHTML = '<span style="color:var(--green);">OK · ' + esc(d.hostname) + ' (FW: ' + esc(d.firmware) + ', S/N: ' + esc(d.serial) + ')</span>';
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
      res.innerHTML = '<span style="color:var(--green);">OK · ' + Number(d.sites) + ' site(s) (' + esc(d.controller_type) + '): ' + esc((d.site_names||[]).join(', ')) + '</span>';
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
      res.innerHTML = '<span style="color:var(--green);">' + t('lagret') + '</span>';
      loadNetworkDevices();
    } else {
      res.innerHTML = '<span style="color:var(--red);">' + esc(d.error) + '</span>';
    }
  } catch (e) {
    res.innerHTML = '<span style="color:var(--red);">' + esc(e.message) + '</span>';
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
      result.innerHTML = `<span style="color:var(--green);">✓ Tilkoblet (${Number(d.organizations)} organisasjoner)</span>`;
    } else {
      result.innerHTML = `<span style="color:var(--red);">✗ ${d ? esc(d.error) : t('status_error','Error')}</span>`;
    }
  } catch(e) {
    result.innerHTML = `<span style="color:var(--red);">✗ ${esc(e.message)}</span>`;
  }
}
