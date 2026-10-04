// ═══════════════════════════════════════════════════════════════════
// NETWORK: a customer's FortiGate and UniFi, on its page's Nettverk tab,
// and its files, on Detaljer
// ═══════════════════════════════════════════════════════════════════
//
// Setting up a customer's network gear happens on that customer's page: the
// Nettverk tab lists its FortiGate and its UniFi link with their state, and
// adds, edits and removes them. It used to live in Verktøy › Nettverk behind
// a "Kunde" field; Verktøy › Nettverk is the every-customer fleet view now.
//
// Every call names the customer the tab was opened for (_netCustomerId, the
// page's _custPage.id when it loaded), and every late answer is checked
// against the page still showing that customer. No secret reaches the
// browser: the listing says whether a token or a password is stored, and a
// device button names the customer so the server looks its login up.

import {esc} from './app-esc.js';
import {t} from './app-i18n.js';
import {registerUiHandlers} from './app-handlers.js';
import {_currentUser, _custPage, hasFeature} from './app-state.js';
import {formatRunName, toneClass, toneName} from './app-format.js';
import {emptyStateHTML, showConfirm, showToast} from './app-ui.js';
import {apiFetch} from './app-api.js';

// Handlers for the markup this file builds: the Nettverk tab's list and its
// forms, the quick check's device cards and the subnet scan results.
registerUiHandlers({
  netAddFortiGate: function() { _netOpenFortiGateForm(false); },
  netEditFortiGate: function() { _netOpenFortiGateForm(true); },
  netRemoveFortiGate: function() { _netRemoveFortiGate(); },
  netLinkUniFi: function() { _netOpenUniFiForm(false); },
  netEditUniFi: function() { _netOpenUniFiForm(true); },
  netRemoveUniFi: function() { _netRemoveUniFi(); },
  netCloseForm: function() { _netCloseForm(); },
  // The forms save on submit, so Enter in a field saves as Lagre does.
  netSaveFortiGate: function(el, event) { event.preventDefault(); _netSaveFortiGate(el); },
  netSaveUniFi: function(el, event) { event.preventDefault(); _netSaveUniFi(el); },
  netTestFortiGate: function(el) { _netTestFortiGate(el.closest('form')); },
  netTestUniFi: function(el) { _netTestUniFi(el.closest('form')); },
  netUniFiMode: function(el) { _netShowUniFiMode(el.closest('form')); },
  netAddDirectDevice: function(el) { _netAddDirectDevice(el.closest('form')); },
  // Enter in the add-device fields adds the device; it must not save the form.
  netDirectDeviceKey: function(el, event) {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    _netAddDirectDevice(el.closest('form'));
  },
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
    r.hidden = true;
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


// ── The customer's FortiGate and UniFi (Nettverk tab) ─────────────────────────
// The customer the tab was opened for, and what /network-devices last said
// about it. A save made after another customer's page opened still goes to
// the customer its form was opened for (the form carries the id); its answer
// is only shown if that customer's page is still the one on screen.
var _netCustomerId = null;
var _netDevices = null;
// The UniFi direct device list, as the listing gave it (no passwords) plus any
// device added in the form, which carries the password typed for it.
var _unifiDirectDevices = [];

function _netOnScreen(customerId) {
  return _custPage.id === customerId && _netCustomerId === customerId;
}

function _netCanSetUp() {
  return hasFeature('network');
}

// The tab's entry point (app-customer-detail.js): the list, the config
// backups, and nothing left over from the last customer.
export function custNetworkLoad(customerId) {
  _netCustomerId = customerId;
  _netDevices = null;
  _unifiDirectDevices = [];
  ['net-audit-result', 'subnet-scan-result', 'config-backups-list'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = '';
  });
  var backups = document.getElementById('cust-net-backups');
  if (backups) backups.hidden = true;
  var check = document.getElementById('cust-net-check');
  if (check) check.hidden = true;
  var box = document.getElementById('cust-net-setup');
  if (box) box.innerHTML = '<div class="card cust-net-card"><div class="loading-note">' + esc(t('msg_loading', 'Laster...')) + '</div></div>';
  _netLoadDevices(customerId);
  loadConfigBackups();
}

// After a save the list stays on screen until the new one arrives.
async function _netLoadDevices(customerId) {
  var box = document.getElementById('cust-net-setup');
  if (!box) return;
  var d = await apiFetch('/api/network-devices/' + encodeURIComponent(customerId));
  if (!_netOnScreen(customerId)) return;
  if (!d) {
    box.innerHTML = '<div class="card cust-net-card"><div class="alert alert-error">' + esc(t('kunne_ikke_laste_nettverksenheter')) + '</div></div>';
    return;
  }
  _netDevices = d;
  _unifiDirectDevices = ((d.unifi && d.unifi.direct_devices) || []).map(function(dev) { return Object.assign({}, dev); });
  _netRenderList(d);
  // The quick check reads the devices set up here; with none it has nothing to read.
  var check = document.getElementById('cust-net-check');
  if (check) check.hidden = !(d.fortigate || d.unifi);
}

function _netRenderList(d) {
  var box = document.getElementById('cust-net-setup');
  var setUp = _netCanSetUp();
  var fg = d.fortigate;
  var uf = d.unifi;
  var html = '<section class="card cust-net-card" aria-labelledby="cust-net-title">';
  html += '<div class="cust-card-head"><h3 class="card-title" id="cust-net-title">' + esc(t('net_setup_title')) + '</h3>';
  if (setUp && (!fg || !uf)) {
    html += '<div class="cust-net-actions">';
    if (!fg) html += '<button type="button" class="btn btn-default btn-sm" data-write data-click-handler="netAddFortiGate">' + esc(t('net_add_fortigate')) + '</button>';
    if (!uf) html += '<button type="button" class="btn btn-default btn-sm" data-write data-click-handler="netLinkUniFi">' + esc(t('net_link_unifi')) + '</button>';
    html += '</div>';
  }
  html += '</div>';

  if (!fg && !uf) {
    html += '<p class="cust-card-text">' + esc(t('msg_no_customer_network')) + '</p>';
  } else {
    html += '<table class="data-table cust-net-table"><thead><tr>'
      + '<th>' + esc(t('lbl_device')) + '</th>'
      + '<th>' + esc(t('net_col_address')) + '</th>'
      + '<th>' + esc(t('lbl_status')) + '</th>'
      + '<th><span class="sr-only">' + esc(t('btn_actions')) + '</span></th>'
      + '</tr></thead><tbody>';
    if (fg) html += _netFortiGateRow(fg, setUp);
    if (uf) html += _netUniFiRow(uf, setUp);
    html += '</tbody></table>';
  }
  html += '<div id="cust-net-form"></div>';
  html += '</section>';
  box.innerHTML = html;
}

function _netBadge(ok, label) {
  return '<span class="badge ' + (ok ? 'badge-success' : 'badge-warning') + '">' + esc(label) + '</span>';
}

function _netFortiGateRow(fg, setUp) {
  var html = '<tr data-net-row="fortigate">';
  html += '<td class="cust-net-name">FortiGate</td>';
  html += '<td class="cust-net-where"><span class="cust-net-addr">' + esc(fg.host) + ':' + esc(fg.port) + '</span>'
    + ' <span class="cust-net-sub">VDOM ' + esc(fg.vdom) + '</span></td>';
  html += '<td class="cust-net-status">' + (fg.has_token ? _netBadge(true, t('net_status_ready')) : _netBadge(false, t('net_status_token_missing'))) + '</td>';
  html += '<td class="cust-net-act">';
  if (setUp) {
    html += '<button type="button" class="btn btn-ghost btn-sm" data-write data-click-handler="netEditFortiGate">' + esc(t('endre')) + '</button>';
    // The hub's only copy of the firewall's admin login: an admin's call.
    if (!fg.has_admin_password || (_currentUser && _currentUser.role === 'admin')) {
      html += '<button type="button" class="btn btn-ghost btn-sm text-danger" data-write data-click-handler="netRemoveFortiGate">' + esc(t('btn_remove')) + '</button>';
    } else {
      html += '<span class="cust-net-sub">' + esc(t('net_remove_admin_only')) + '</span>';
    }
  }
  html += '</td></tr>';
  return html;
}

function _netUniFiRow(uf, setUp) {
  var direct = uf.mode === 'direct';
  var count = (uf.direct_devices || []).length;
  var html = '<tr data-net-row="unifi">';
  html += '<td class="cust-net-name">' + esc(t(direct ? 'net_row_unifi_direct' : 'net_row_unifi_controller')) + '</td>';
  if (direct) {
    html += '<td class="cust-net-where">' + esc(count === 1 ? t('net_devices_count_one') : t('net_devices_count').replace('{count}', count)) + '</td>';
    html += '<td class="cust-net-status">' + (count ? _netBadge(true, t('net_status_ready')) : _netBadge(false, t('net_status_no_devices'))) + '</td>';
  } else {
    html += '<td class="cust-net-where"><span class="cust-net-addr">' + esc(uf.host) + '</span>'
      + ' <span class="cust-net-sub">' + esc(t('site')) + ' ' + esc(uf.site) + '</span></td>';
    html += '<td class="cust-net-status">' + (uf.has_credentials ? _netBadge(true, t('net_status_ready')) : _netBadge(false, t('net_status_login_missing'))) + '</td>';
  }
  html += '<td class="cust-net-act">';
  if (setUp) {
    html += '<button type="button" class="btn btn-ghost btn-sm" data-write data-click-handler="netEditUniFi">' + esc(t('endre')) + '</button>';
    html += '<button type="button" class="btn btn-ghost btn-sm text-danger" data-write data-click-handler="netRemoveUniFi">' + esc(t('btn_remove')) + '</button>';
  }
  html += '</td></tr>';
  return html;
}

function _netCloseForm() {
  var box = document.getElementById('cust-net-form');
  if (box) box.innerHTML = '';
}

function _netResult(form, cls, text) {
  var el = form.querySelector('.cust-net-result');
  if (!el) return;
  el.className = 'cust-net-result text-xs ' + cls;
  el.textContent = text;
}

// ── FortiGate form ──
function _netOpenFortiGateForm(editing) {
  var box = document.getElementById('cust-net-form');
  if (!box || !_netCustomerId) return;
  var fg = (editing && _netDevices && _netDevices.fortigate) || null;
  var html = '<form class="inset cust-net-form" data-submit-handler="netSaveFortiGate" data-customer-id="' + esc(_netCustomerId) + '" data-editing="' + (fg ? '1' : '') + '">';
  html += '<h4 class="cust-net-form-title">' + esc(t(fg ? 'net_edit_fortigate' : 'net_add_fortigate')) + '</h4>';
  html += '<label class="field-label" for="input-fg-host">' + esc(t('host_ip_eller_fqdn')) + '</label>';
  html += '<input class="field-input" id="input-fg-host" type="text" autocomplete="off" placeholder="192.0.2.1" value="' + esc(fg ? fg.host : '') + '">';
  html += '<div class="grid grid-cols-2 gap-2 mt-2">';
  html += '<div><label class="field-label" for="input-fg-port">' + esc(t('port')) + '</label><input class="field-input" id="input-fg-port" type="number" min="1" max="65535" value="' + esc(fg ? fg.port : 443) + '"></div>';
  html += '<div><label class="field-label" for="input-fg-vdom">VDOM</label><input class="field-input" id="input-fg-vdom" type="text" value="' + esc(fg ? fg.vdom : 'root') + '"></div>';
  html += '</div>';
  html += '<label class="field-label mt-2" for="input-fg-token">' + esc(t('api_token')) + '</label>';
  html += '<input class="field-input" id="input-fg-token" type="password" autocomplete="new-password" placeholder="' + esc(t(fg && fg.has_token ? 'placeholder_token_saved' : 'net_token_placeholder')) + '">';
  html += '<label class="flex items-center gap-2 mt-2 text-sm cursor-pointer"><input type="checkbox" id="input-fg-verify-ssl"' + (fg && fg.verify_ssl ? ' checked' : '') + '> ' + esc(t('verifiser_ssl_sertifikat')) + '</label>';
  html += _netFormActions('fortigate');
  html += '</form>';
  box.innerHTML = html;
  document.getElementById('input-fg-host').focus();
}

// Lagre, the form's own Test tilkobling, and Avbryt.
function _netFormActions(form) {
  var test = form === 'fortigate'
    ? '<button type="button" class="btn btn-default btn-sm cust-net-test" data-click-handler="netTestFortiGate">'
    : '<button type="button" class="btn btn-default btn-sm cust-net-test" data-click-handler="netTestUniFi">';
  return '<div class="cust-net-form-actions">'
    + '<button type="submit" class="btn btn-primary btn-sm" data-write>' + esc(t('lagre_2')) + '</button>'
    + test + esc(t('test_tilkobling')) + '</button>'
    + '<button type="button" class="btn btn-ghost btn-sm" data-click-handler="netCloseForm">' + esc(t('btn_cancel')) + '</button>'
    + '<span class="cust-net-result text-xs" role="status"></span>'
    + '</div>';
}

function _netFortiGateBody() {
  return {
    host: document.getElementById('input-fg-host').value.trim(),
    port: parseInt(document.getElementById('input-fg-port').value, 10) || 443,
    api_token: document.getElementById('input-fg-token').value.trim(),
    vdom: document.getElementById('input-fg-vdom').value.trim() || 'root',
    verify_ssl: document.getElementById('input-fg-verify-ssl').checked,
  };
}

async function _netTestFortiGate(form) {
  var body = _netFortiGateBody();
  if (!body.host) { _netResult(form, 'text-danger', t('net_host_required')); return; }
  // A saved device is tested with its stored token, for the address it was stored for.
  if (!body.api_token) body.customer_id = form.dataset.customerId;
  _netResult(form, 'text-muted', t('msg_testing'));
  var d = await apiFetch('/api/fortigate/test', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (!d) { _netResult(form, '', ''); return; }
  if (d.ok) _netResult(form, 'text-success', t('net_test_ok_fortigate').replace('{name}', d.hostname || '').replace('{firmware}', d.firmware || ''));
  else _netResult(form, 'text-danger', t(d.error_key || 'err_connection_failed', d.error || ''));
}

async function _netSaveFortiGate(form) {
  var customerId = form.dataset.customerId;
  var body = _netFortiGateBody();
  if (!body.host) { _netResult(form, 'text-danger', t('net_host_required')); return; }
  // Blank keeps the stored token; the server leaves an absent one alone.
  if (!body.api_token) delete body.api_token;
  _netResult(form, 'text-muted', t('btn_saving'));
  var d = await apiFetch('/api/fortigate/save/' + encodeURIComponent(customerId), {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (!d) { _netResult(form, '', ''); return; }
  showToast(t('lagret'), 'success');
  if (d.token_cleared) showToast(t('msg_fortigate_token_cleared'), 'warning', 8000);
  if (_netOnScreen(customerId)) _netLoadDevices(customerId);
}

async function _netRemoveFortiGate() {
  var customerId = _netCustomerId;
  var fg = _netDevices && _netDevices.fortigate;
  if (!customerId || !fg) return;
  var body = t('dlg_remove_fortigate_body');
  if (fg.has_admin_password) body += ' ' + t('dlg_remove_fortigate_admin_pw');
  var title = t('dlg_remove_fortigate_title').replace('{host}', fg.host).replace('{customer}', _netCustomerName());
  if (!await showConfirm(title, body)) return;
  var d = await apiFetch('/api/fortigate/' + encodeURIComponent(customerId), {method: 'DELETE'});
  if (!d) return;
  showToast(t('msg_fortigate_removed'), 'success');
  if (_netOnScreen(customerId)) _netLoadDevices(customerId);
}

function _netCustomerName() {
  return (_custPage.cust && _custPage.cust.customer_name) || _netCustomerId || '';
}

// ── UniFi form: a controller and its site, or devices reached directly ──
function _netOpenUniFiForm(editing) {
  var box = document.getElementById('cust-net-form');
  if (!box || !_netCustomerId) return;
  var uf = (editing && _netDevices && _netDevices.unifi) || null;
  var mode = (uf && uf.mode) || 'controller';
  var controller = uf && mode === 'controller' ? uf : null;
  var html = '<form class="inset cust-net-form" data-submit-handler="netSaveUniFi" data-customer-id="' + esc(_netCustomerId) + '">';
  html += '<h4 class="cust-net-form-title">' + esc(t(uf ? 'net_edit_unifi' : 'net_link_unifi')) + '</h4>';
  html += '<fieldset class="cust-net-mode"><legend class="field-label">' + esc(t('net_unifi_mode')) + '</legend>';
  html += '<label class="flex items-center gap-2 text-ui cursor-pointer"><input type="radio" name="unifi-mode" value="controller"' + (mode === 'controller' ? ' checked' : '') + ' data-change-handler="netUniFiMode"> ' + esc(t('controller_2')) + '</label>';
  html += '<label class="flex items-center gap-2 text-ui cursor-pointer"><input type="radio" name="unifi-mode" value="direct"' + (mode === 'direct' ? ' checked' : '') + ' data-change-handler="netUniFiMode"> ' + esc(t('direkte_enheter')) + '</label>';
  html += '</fieldset>';

  // A controller and the site on it.
  html += '<div data-unifi-mode="controller"' + (mode === 'controller' ? '' : ' hidden') + '>';
  html += '<label class="field-label" for="input-uf-host">' + esc(t('controller_url')) + '</label>';
  html += '<input class="field-input" id="input-uf-host" type="text" autocomplete="off" placeholder="https://192.0.2.20:8443" value="' + esc(controller ? controller.host : '') + '">';
  html += '<div class="grid grid-cols-2 gap-2 mt-2">';
  html += '<div><label class="field-label" for="input-uf-user">' + esc(t('brukernavn')) + '</label><input class="field-input" id="input-uf-user" type="text" autocomplete="off" placeholder="' + esc(controller && controller.has_credentials ? t('net_login_saved') : 'admin') + '"></div>';
  html += '<div><label class="field-label" for="input-uf-pass">' + esc(t('passord')) + '</label><input class="field-input" id="input-uf-pass" type="password" autocomplete="new-password" placeholder="' + esc(controller && controller.has_credentials ? t('net_login_saved') : t('passord')) + '"></div>';
  html += '</div>';
  html += '<label class="field-label mt-2" for="input-uf-site">' + esc(t('site')) + '</label>';
  html += '<input class="field-input" id="input-uf-site" type="text" placeholder="default" value="' + esc((uf && uf.site) || 'default') + '">';
  html += '<label class="flex items-center gap-2 mt-2 text-sm cursor-pointer"><input type="checkbox" id="input-uf-os"' + (uf && uf.is_unifi_os ? ' checked' : '') + '> ' + esc(t('unifi_os_udm_cloud_key_gen2')) + '</label>';
  html += '</div>';

  // Devices reached one by one, no controller.
  html += '<div data-unifi-mode="direct"' + (mode === 'direct' ? '' : ' hidden') + '>';
  html += '<p class="cust-card-text">' + esc(t('msg_unifi_direct_desc')) + '</p>';
  html += '<div id="unifi-device-list"></div>';
  html += '<div class="cust-net-add-device" data-keydown-handler="netDirectDeviceKey">';
  html += '<div class="fw-semibold text-sm mb-2">' + esc(t('btn_add_device')) + '</div>';
  html += '<div class="grid grid-cols-2 gap-2">';
  html += '<div><label class="field-label" for="input-uf-dev-host">' + esc(t('ip_adresse')) + '</label><input class="field-input" id="input-uf-dev-host" type="text" autocomplete="off" placeholder="192.0.2.30"></div>';
  html += '<div><label class="field-label" for="input-uf-dev-type">' + esc(t('type')) + '</label><select class="field-input" id="input-uf-dev-type">'
    + '<option value="ap">' + esc(t('access_point')) + '</option>'
    + '<option value="gateway">' + esc(t('gateway_firewall')) + '</option>'
    + '<option value="switch">' + esc(t('switch')) + '</option></select></div>';
  html += '<div><label class="field-label" for="input-uf-dev-user">' + esc(t('brukernavn')) + '</label><input class="field-input" id="input-uf-dev-user" type="text" autocomplete="off" value="ubnt"></div>';
  html += '<div><label class="field-label" for="input-uf-dev-pass">' + esc(t('passord')) + '</label><input class="field-input" id="input-uf-dev-pass" type="password" autocomplete="new-password" value="ubnt"></div>';
  html += '</div>';
  html += '<button type="button" class="btn btn-default btn-sm mt-2" data-click-handler="netAddDirectDevice">' + esc(t('btn_add')) + '</button>';
  html += '</div>';
  html += '</div>';

  html += _netFormActions('unifi');
  html += '</form>';
  box.innerHTML = html;
  renderUniFiDeviceList();
  _netShowUniFiMode(box.querySelector('form'));
  var first = box.querySelector(mode === 'direct' ? '#input-uf-dev-host' : '#input-uf-host');
  if (first) first.focus();
}

function _netUniFiMode(form) {
  var on = form.querySelector('input[name="unifi-mode"]:checked');
  return on ? on.value : 'controller';
}

function _netShowUniFiMode(form) {
  var mode = _netUniFiMode(form);
  form.querySelectorAll('[data-unifi-mode]').forEach(function(el) { el.hidden = el.dataset.unifiMode !== mode; });
  // "Test tilkobling" tests a controller login; each direct device has its own Test.
  var test = form.querySelector('.cust-net-test');
  if (test) test.hidden = mode !== 'controller';
}

function _netUniFiControllerBody() {
  return {
    host: document.getElementById('input-uf-host').value.trim(),
    username: document.getElementById('input-uf-user').value.trim(),
    password: document.getElementById('input-uf-pass').value,
    is_unifi_os: document.getElementById('input-uf-os').checked,
  };
}

async function _netTestUniFi(form) {
  var body = _netUniFiControllerBody();
  if (!body.host) { _netResult(form, 'text-danger', t('net_controller_required')); return; }
  // A saved controller is tested with its stored login, for the address it was stored for.
  if (!body.password) body.customer_id = form.dataset.customerId;
  _netResult(form, 'text-muted', t('msg_testing'));
  var d = await apiFetch('/api/unifi/test', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (!d) { _netResult(form, '', ''); return; }
  if (d.ok) _netResult(form, 'text-success', t('net_test_ok_unifi').replace('{sites}', (d.site_names || []).join(', ')));
  else _netResult(form, 'text-danger', t(d.error_key || 'err_connection_failed', d.error || ''));
}

async function _netSaveUniFi(form) {
  var customerId = form.dataset.customerId;
  var body;
  if (_netUniFiMode(form) === 'direct') {
    if (!_unifiDirectDevices.length) { _netResult(form, 'text-danger', t('net_direct_need_device')); return; }
    // Only what the form owns; the route leaves the controller fields alone.
    body = {mode: 'direct', devices: _unifiDirectDevices.map(_netStoredDevice)};
  } else {
    var c = _netUniFiControllerBody();
    if (!c.host) { _netResult(form, 'text-danger', t('net_controller_required')); return; }
    body = {mode: 'controller', host: c.host, site: document.getElementById('input-uf-site').value.trim() || 'default', is_unifi_os: c.is_unifi_os};
    // Blank keeps the stored login.
    if (c.username) body.username = c.username;
    if (c.password) body.password = c.password;
  }
  _netResult(form, 'text-muted', t('btn_saving'));
  var d = await apiFetch('/api/unifi/save/' + encodeURIComponent(customerId), {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (!d) { _netResult(form, '', ''); return; }
  showToast(t('lagret'), 'success');
  if (d.credentials_cleared) showToast(t('msg_unifi_login_cleared'), 'warning', 8000);
  if (_netOnScreen(customerId)) _netLoadDevices(customerId);
}

// A direct device as it is stored: the type under the name the poller and the
// network audit read (device_type; the old form wrote "type", which they
// never read), and no field the listing added.
function _netStoredDevice(dev) {
  var out = {};
  Object.keys(dev).forEach(function(k) {
    if (k !== 'has_password' && k !== 'status' && k !== 'type') out[k] = dev[k];
  });
  out.device_type = dev.device_type || dev.type || 'ap';
  return out;
}

async function _netRemoveUniFi() {
  var customerId = _netCustomerId;
  if (!customerId || !(_netDevices && _netDevices.unifi)) return;
  var title = t('dlg_unlink_unifi_title').replace('{customer}', _netCustomerName());
  if (!await showConfirm(title, t('dlg_unlink_unifi_body'))) return;
  var d = await apiFetch('/api/unifi/' + encodeURIComponent(customerId), {method: 'DELETE'});
  if (!d) return;
  showToast(t('msg_unifi_unlinked'), 'success');
  if (_netOnScreen(customerId)) _netLoadDevices(customerId);
}

// ── The direct device list in the UniFi form ──
var _DEVICE_TYPE_KEYS = {ap: 'access_point', gateway: 'gateway_firewall', switch: 'switch'};

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
  var html = '<table class="data-table data-table--compact cust-net-table"><thead><tr>'
    + '<th>' + esc(t('ip_adresse')) + '</th><th>' + esc(t('type')) + '</th><th>' + esc(t('lbl_status')) + '</th>'
    + '<th><span class="sr-only">' + esc(t('btn_actions')) + '</span></th></tr></thead><tbody>';
  for (var i = 0; i < _unifiDirectDevices.length; i++) {
    var dev = _unifiDirectDevices[i];
    var type = dev.device_type || dev.type || 'ap';
    var login = dev.password ? t('net_device_password_new') : (dev.has_password ? t('net_device_password_saved') : t('net_device_password_shared'));
    html += '<tr>';
    html += '<td class="cust-net-name"><span class="cust-net-addr">' + esc(dev.host || '') + '</span></td>';
    html += '<td class="cust-net-where">' + esc(_DEVICE_TYPE_KEYS[type] ? t(_DEVICE_TYPE_KEYS[type]) : type)
      + ' <span class="cust-net-sub">' + esc(dev.username || 'ubnt') + ', ' + esc(login) + '</span></td>';
    html += '<td class="cust-net-status" id="dev-status-' + i + '"></td>';
    html += '<td class="cust-net-act">'
      + '<button type="button" class="btn btn-ghost btn-sm" data-click-handler="testUniFiDevice" data-index="' + i + '">' + esc(t('test')) + '</button>'
      + '<button type="button" class="btn btn-ghost btn-sm text-danger" data-click-handler="removeUniFiDevice" data-index="' + i + '">' + esc(t('btn_remove')) + '</button>'
      + '</td></tr>';
  }
  html += '</tbody></table>';
  box.innerHTML = html;
}

function _netAddDirectDevice(form) {
  var hostInput = form.querySelector('#input-uf-dev-host');
  var host = hostInput.value.trim();
  if (!host) { showToast(t('msg_enter_ip'), 'warning'); hostInput.focus(); return; }
  if (_unifiDirectDevices.some(function(d) { return d.host === host; })) {
    showToast(t('msg_already_exists'), 'warning');
    return;
  }
  _unifiDirectDevices.push({
    host: host,
    device_type: form.querySelector('#input-uf-dev-type').value || 'ap',
    username: form.querySelector('#input-uf-dev-user').value.trim() || 'ubnt',
    password: form.querySelector('#input-uf-dev-pass').value || 'ubnt',
  });
  renderUniFiDeviceList();
  hostInput.value = '';
  hostInput.focus();
}

function removeUniFiDevice(idx) {
  _unifiDirectDevices.splice(idx, 1);
  renderUniFiDeviceList();
}

async function testUniFiDevice(idx) {
  var dev = _unifiDirectDevices[idx];
  if (!dev) return;
  var el = document.getElementById('dev-status-' + idx);
  if (el) el.innerHTML = '<span class="text-muted">' + esc(t('msg_testing', 'Testing...')) + '</span>';
  // A device added in this form carries the login typed for it; a saved one
  // names the customer and the server uses the login stored for it.
  var body = {host: dev.host, device_type: dev.device_type || dev.type || 'ap'};
  if (dev.password) { body.username = dev.username || 'ubnt'; body.password = dev.password; }
  else body.customer_id = _netCustomerId;
  try {
    var d = await apiFetch('/api/unifi/test-device', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
    if (!el) return;
    if (!d) { el.innerHTML = ''; return; }
    if (d.ok) {
      var methods = [];
      if (d.http) methods.push('HTTP');
      if (d.ssh) methods.push('SSH');
      var info = [d.model, d.firmware, d.hostname].filter(Boolean).join(' · ');
      el.innerHTML = '<span class="badge badge-success">OK' + (methods.length ? ' ' + esc(methods.join('+')) : '') + '</span>'
        + (info ? ' <span class="cust-net-sub">' + esc(info) + '</span>' : '');
    } else {
      el.innerHTML = '<span class="text-danger text-xs">' + esc(d.error || t('status_error', 'Error')) + '</span>';
    }
  } catch (e) {
    if (el) el.innerHTML = '<span class="text-danger text-xs">' + esc(e.message) + '</span>';
  }
}

// ── Quick check ──
export async function runNetworkQuickAudit() {
  var btn = document.getElementById('btn-run-network-audit');
  var box = document.getElementById('net-audit-result');
  var cid = _netCustomerId;
  if (!cid || _custPage.id !== cid) return;
  btn.disabled = true;
  btn.textContent = t('status_running', 'Running...');
  box.innerHTML = '<div class="text-center p-6"><div class="loader loader-lg mx-auto mt-0 mb-3"></div>' + esc(t('msg_loading_network_devices', 'Loading data from network devices...')) + '</div>';
  try {
    var d = await apiFetch('/api/network/quick-audit/' + encodeURIComponent(cid), {method: 'POST'});
    if (!_netOnScreen(cid)) return;
    if (!d) { box.innerHTML = ''; return; }
    if (d.error) { box.innerHTML = '<div class="alert alert-error">' + esc(d.error) + '</div>'; return; }
    box.innerHTML = _quickAuditHtml(d);
  } catch (e) {
    box.innerHTML = '<div class="alert alert-error">' + esc(t('status_error', 'Error')) + ': ' + esc(e.message) + '</div>';
  } finally {
    btn.disabled = false;
    btn.textContent = t('btn_run_quick_check', 'Run quick check');
  }
}

// The quick check's answer as cards: the FortiGate's figures, admins and
// policy warnings; the UniFi devices, through the controller or one by one.
function _quickAuditHtml(d) {
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
      html += '<div class="overflow-x-auto mb-3"><table class="section-table w-full"><thead><tr><th>' + t('navn') + '</th><th>' + t('profil') + '</th><th>' + t('trusted_host') + '</th><th>' + t('fa') + '</th></tr></thead><tbody>';
      for (var a of fg.admins) {
        var thColor = a.trusthost ? 'var(--green)' : 'var(--red)';
        var tfaColor = a.two_factor ? 'var(--green)' : 'var(--red)';
        html += '<tr><td>' + esc(a.name) + '</td><td>' + esc(a.profile) + '</td>';
        html += '<td class="' + toneClass(thColor) + '">' + (a.trusthost ? t('lbl_yes', 'Yes') : t('lbl_no', 'No')) + '</td>';
        html += '<td class="' + toneClass(tfaColor) + '">' + (a.two_factor ? t('lbl_yes', 'Yes') : t('lbl_no', 'No')) + '</td></tr>';
      }
      html += '</tbody></table></div>';

      // Policy warnings
      if (fg.policy_warnings.length > 0) {
        html += '<div class="fw-semibold text-ui mb-2 text-danger">' + esc(t('net_policy_warnings').replace('{count}', fg.policy_warnings.length)) + '</div>';
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
          html += '<div class="inset bg-none mb-3 ' + (borderColor === 'var(--border)' ? '' : 'border-' + toneName(borderColor)) + '" data-unifi-card="' + esc(dev.host) + '">';

          // Header row
          html += '<div class="flex items-center justify-between mb-3">';
          html += '<div>';
          html += '<span class="fw-semibold text-base">' + esc(dev.hostname || dev.label || dev.host) + '</span>';
          if (dev.model) html += '<span class="text-muted text-sm ml-2">' + esc(dev.model) + '</span>';
          html += '</div>';
          html += '<div class="flex gap-2 items-center">';
                    html += '<span class="text-xs py-0-5 px-2 rounded-full bg-base border">' + esc(_DEVICE_TYPE_KEYS[dev.device_type] ? t(_DEVICE_TYPE_KEYS[dev.device_type]) : dev.device_type) + '</span>';
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
            // [label, value, set in the code face]
            var fields = [
              [t('lbl_model','Model'), dev.model],
              [t('lbl_firmware','Firmware'), dev.firmware, true],
              [t('lbl_serial','Serial'), dev.serial, true],
              ['MAC', dev.mac, true],
              ['IP', dev.ip || dev.host, true],
              [t('lbl_hostname'), dev.hostname && dev.hostname !== (dev.label || dev.host) ? dev.hostname : null],
              [t('lbl_uptime'), dev.uptime],
              [t('lbl_clients'), dev.client_count != null ? String(dev.client_count) : null],
            ];
            // Wireless fields
            if (dev.ssid_list && dev.ssid_list.length > 1) {
              fields.push([t('lbl_ssids','SSID-er'), dev.ssid_list.join(', ')]);
            } else if (dev.essid) {
              fields.push(['SSID', dev.essid]);
            }
            if (dev.channel) fields.push([t('lbl_channel'), dev.channel]);
            if (dev.wifi_security) fields.push([t('net_wifi_security'), dev.wifi_security]);
            // Management
            if (dev.inform_url) fields.push([t('net_inform_url'), dev.inform_url, true]);
            fields.push([t('net_connection'), (dev.http && dev.ssh) ? 'HTTP + SSH' : dev.ssh ? 'SSH' : dev.http ? 'HTTP' : null]);

            for (var f of fields) {
              if (f[1]) {
                html += '<div class="bg-base rounded-sm p-2">';
                html += '<div class="text-muted text-2xs mb-0-5">' + esc(f[0]) + '</div>';
                html += '<div class="text-xs break-all' + (f[2] ? ' font-mono' : '') + '">' + esc(f[1]) + '</div>';
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
              if (dev.fw_check.eol) findings.push({sev: 'critical', text: t('end_of_life') + ' · ' + dev.fw_check.model + ' ' + t('msg_no_longer_supported','is no longer supported by Ubiquiti')});
              else if (dev.fw_check.up_to_date === false) findings.push({sev: dev.fw_check.severity === 'critical' ? 'critical' : 'warning', text: t('warn_outdated_firmware','Outdated firmware: ') + dev.fw_check.current + ' → ' + t('msg_update_to','update to') + ' ' + dev.fw_check.latest});
              else if (dev.fw_check.up_to_date === true) findings.push({sev: 'ok', text: t('msg_firmware_updated','Firmware up to date') + ' (' + dev.fw_check.latest + ')'});
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
            html += '<button class="btn btn-default btn-sm" data-write data-click-handler="unifiDeviceSetInform" data-host="' + esc(dev.host) + '">' + t('set_inform') + '</button>';
            // View config
            html += '<button class="btn btn-default btn-sm" data-write data-click-handler="unifiDeviceConfig" data-host="' + esc(dev.host) + '">' + t('btn_view_config','View config') + '</button>';
            // Reboot
            html += '<button class="btn btn-default btn-sm text-warning" data-write data-click-handler="unifiDeviceReboot" data-host="' + esc(dev.host) + '">' + t('btn_restart','Restart') + '</button>';
            html += '</div>';
            html += '<div class="mt-2" data-unifi-action></div>';
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
        html += '<div class="overflow-x-auto mb-3"><table class="section-table w-full"><thead><tr><th>' + t('lbl_name','Name') + '</th><th>' + t('lbl_type','Type') + '</th><th>' + t('lbl_model','Model') + '</th><th>' + t('firmware') + '</th><th>' + t('lbl_upgrade','Upgrade') + '</th><th>' + t('lbl_clients','Clients') + '</th><th>' + t('status') + '</th></tr></thead><tbody>';
        for (const dev of uf.devices) {
          var statusColor = dev.status === 'online' ? 'var(--green)' : 'var(--red)';
          var upgradeHtml = dev.upgrade ? '<span class="text-warning">' + esc(dev.upgrade) + '</span>' : '<span class="text-success">OK</span>';
          html += '<tr><td>' + esc(dev.name) + '</td><td>' + esc(dev.type) + '</td><td>' + esc(dev.model) + '</td>';
          html += '<td class="font-mono text-xs">' + esc(dev.firmware) + '</td>';
          html += '<td>' + upgradeHtml + '</td>';
          html += '<td>' + Number(dev.clients) + '</td>';
          html += '<td class="' + toneClass(statusColor) + '">' + esc(dev.status) + '</td></tr>';
        }
        html += '</tbody></table></div>';

        // WLAN table
        if (uf.wlans && uf.wlans.length > 0) {
          html += '<div class="subhead">' + t('lbl_wireless_networks','Wireless networks') + '</div>';
          html += '<div class="overflow-x-auto"><table class="section-table w-full"><thead><tr><th>SSID</th><th>' + t('lbl_security','Security') + '</th><th>' + t('lbl_guest','Guest') + '</th><th>' + t('lbl_active','Active') + '</th></tr></thead><tbody>';
          for (const w of uf.wlans) {
            var secColor = w.security === 'open' ? 'var(--red)' : 'var(--green)';
            html += '<tr><td>' + esc(w.name) + '</td>';
            html += '<td class="' + toneClass(secColor) + '">' + esc(w.security) + '</td>';
            html += '<td>' + (w.guest ? t('lbl_yes','Yes') : t('lbl_no','No')) + '</td>';
            html += '<td>' + (w.enabled ? t('lbl_yes','Yes') : '<span class="text-dim">' + t('lbl_no','No') + '</span>') + '</td></tr>';
          }
          html += '</tbody></table></div>';
        }
      }
      html += '</div>';
    }
  }


  return html || '<div class="alert alert-error">' + esc(t('msg_no_data_returned', 'No data returned')) + '</div>';
}

// ── Direct device actions (the quick check's device cards, the scan results) ──
// Each names the device and the customer; the server connects with the login
// stored for that device if it is on the customer's list, and with the
// factory login if it is not (a device found by the scan).
function _deviceLogin(host) {
  return {host: host, customer_id: _netCustomerId};
}

async function unifiDeviceSetInform(host) {
  var url = prompt(t('net_inform_prompt'));
  if (!url) return;
  try {
    var d = await apiFetch('/api/unifi/set-inform', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.assign(_deviceLogin(host), {controller_url: url}))
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
  try {
    var d = await apiFetch('/api/unifi/reboot-device', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(_deviceLogin(host))
    });
    if (!d) return;

    if (d.ok) showToast(d.output || t('msg_device_rebooting'), 'success');
    else showToast(t('status_error') + ': ' + (d.error || t('err_unknown')), 'error');
  } catch (e) { showToast(t('status_error') + ': ' + e.message, 'error'); }
}

// The running config is saved as a backup for the customer each time it is shown.
function _saveConfigBackup(host, config) {
  var cid = _netCustomerId;
  if (!cid) return;
  apiFetch('/api/network/save-config-backup/' + encodeURIComponent(cid), {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({host: host, config: config})
  }).then(function(d) { if (d && _netOnScreen(cid)) loadConfigBackups(); }).catch(function() {});
}

async function unifiDeviceConfig(host) {
  // The card of this device, by its address.
  var targetEl = null;
  document.querySelectorAll('[data-unifi-card]').forEach(function(card) {
    if (!targetEl && card.dataset.unifiCard === host) targetEl = card.querySelector('[data-unifi-action]');
  });
  if (targetEl) targetEl.innerHTML = '<div class="p-2 text-muted text-sm">' + esc(t('msg_loading_config', 'Loading configuration...')) + '</div>';

  try {
    var d = await apiFetch('/api/unifi/device-config', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(_deviceLogin(host))
    });
    if (!d) {
      // apiFetch already reported the failure; clear the "Loading…" placeholder
      // so the card does not sit spinning forever.
      if (targetEl) targetEl.innerHTML = '';
      return;
    }

    if (d.ok && d.config) {
      _saveConfigBackup(host, d.config);
      if (targetEl) {
        targetEl.innerHTML = '<div class="mt-1"><div class="flex items-center justify-between"><div class="fw-semibold text-sm">' + esc(t('lbl_running_config', 'Running configuration')) + '</div><span class="text-2xs text-success">' + esc(t('msg_backup_saved', 'Backup saved')) + '</span></div>'
          + '<pre class="inset max-h-md overflow-auto text-xs pre-wrap break-all">'
          + esc(d.config) + '</pre>'
          + '<button class="btn btn-default btn-sm mt-2" data-click-handler="unifiDeviceConfigClose">' + esc(t('btn_close', 'Close')) + '</button></div>';
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
// Run from the hub, so the subnet must be reachable from it. "Legg til" adds a
// found device to this customer's direct devices and saves the list.

export async function runSubnetScan() {
  var btn = document.getElementById('btn-subnet-scan');
  var box = document.getElementById('subnet-scan-result');
  var subnet = document.getElementById('input-scan-subnet').value.trim();
  if (!subnet) { showToast(t('msg_enter_subnet'), 'warning'); return; }
  var cid = _netCustomerId;
  btn.disabled = true;
  btn.textContent = t('msg_scanning', 'Scanning...');
  box.innerHTML = '<div class="text-center p-4"><div class="loader loader-md mx-auto mt-0 mb-2"></div>' + esc(t('msg_scanning', 'Scanning...').replace('...', '')) + ' ' + esc(subnet) + '...</div>';

  try {
    var d = await apiFetch('/api/network/scan', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({subnet: subnet})
    });
    if (cid && !_netOnScreen(cid)) return;
    if (!d) { box.innerHTML = ''; return; }

    if (d.error) { box.innerHTML = '<div class="alert alert-error">' + esc(d.error) + '</div>'; return; }

    // A scan that returned nothing at all is not the same as a scan that found
    // no devices; treat a missing list as an empty one rather than throwing.
    if (!d.found || d.found.length === 0) {
      box.innerHTML = '<div class="p-3 text-muted text-ui">' + esc(t('msg_no_devices_found', 'No devices found in')) + ' ' + esc(subnet) + '</div>';
      return;
    }

    var html = '<div class="text-ui mb-2"><strong>' + Number(d.found.length) + '</strong> ' + esc(t('msg_devices_found_in', 'devices found in')) + ' ' + esc(subnet) + '</div>';
    html += '<div class="overflow-x-auto"><table class="section-table w-full"><thead><tr><th>IP</th><th>SSH</th><th>HTTPS</th><th>UniFi</th><th>' + esc(t('info')) + '</th><th>' + esc(t('btn_actions', 'Actions')) + '</th></tr></thead><tbody>';
    for (var dev of d.found) {
      var isUf = dev.is_unifi ? '<span class="text-success">' + esc(t('lbl_yes', 'Yes')) + '</span>' : '<span class="text-muted">' + esc(t('lbl_no', 'No')) + '</span>';
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
        html += '<button class="btn btn-default btn-sm text-success" disabled>' + esc(t('status_added', 'Added')) + '</button> ';
      } else {
        html += '<button class="btn btn-default btn-sm" data-write id="scan-add-' + esc(hostId) + '" data-click-handler="addScannedDevice" data-host="' + hostSafe + '">' + esc(t('btn_add', 'Add')) + '</button> ';
      }
      if (dev.ssh) {
        html += '<button class="btn btn-default btn-sm" data-write data-click-handler="scanDeviceSetInform" data-host="' + hostSafe + '">' + esc(t('set_inform')) + '</button> ';
        html += '<button class="btn btn-default btn-sm" data-write data-click-handler="scanDeviceConfig" data-host="' + hostSafe + '" data-row-id="scan-cfg-' + esc(hostId) + '">' + esc(t('btn_view_config', 'Vis konfig')) + '</button> ';
        html += '<button class="btn btn-default btn-sm" data-write data-click-handler="scanDeviceReboot" data-host="' + hostSafe + '">' + esc(t('btn_restart', 'Restart')) + '</button>';
      }
      html += '</td>';
      html += '</tr>';
      if (dev.ssh) {
        html += '<tr id="scan-cfg-' + esc(hostId) + '" hidden><td colspan="6"></td></tr>';
      }
    }
    html += '</tbody></table></div>';
    box.innerHTML = html;
  } catch (e) {
    box.innerHTML = '<div class="alert alert-error">' + esc(e.message) + '</div>';
  } finally {
    btn.disabled = false;
    btn.textContent = t('btn_scan', 'Scan');
  }
}

async function addScannedDevice(host, btnEl) {
  var cid = _netCustomerId;
  if (!cid) return;
  if (_unifiDirectDevices.some(function(d) { return d.host === host; })) {
    if (btnEl) { btnEl.textContent = t('msg_already_exists', 'Exists'); btnEl.disabled = true; }
    return;
  }
  if (btnEl) { btnEl.textContent = t('btn_saving', 'Saving...'); btnEl.disabled = true; }
  var devices = _unifiDirectDevices.map(_netStoredDevice);
  devices.push({host: host, username: 'ubnt', password: 'ubnt', device_type: 'ap', label: host});
  try {
    var d = await apiFetch('/api/unifi/save/' + encodeURIComponent(cid), {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mode: 'direct', devices: devices})
    });
    if (!btnEl) return;
    if (d && d.ok) {
      btnEl.textContent = t('status_added', 'Added');
      btnEl.classList.add('text-success');
      if (_netOnScreen(cid)) _netLoadDevices(cid);
    } else {
      btnEl.textContent = t('status_error', 'Error');
      btnEl.classList.add('text-danger');
      btnEl.disabled = false;
    }
  } catch (e) {
    if (btnEl) { btnEl.textContent = t('status_error', 'Error'); btnEl.classList.add('text-danger'); btnEl.disabled = false; }
  }
}

async function scanDeviceSetInform(host) {
  var presets = [
    { label: 'unifi.sybr.no', url: 'http://unifi.sybr.no:8080/inform' }
  ];
  // Use the confirm modal infrastructure to show preset + custom URL picker
  document.getElementById('confirm-modal-title').textContent = t('hdr_set_inform', 'Set-Inform') + ' · ' + host;
  var bodyEl = document.getElementById('confirm-modal-body');
  var pickHtml = '<div class="flex flex-col gap-2 mb-3">';
  for (var p of presets) {
    pickHtml += '<button class="btn btn-primary btn-sm" data-click-handler="doScanSetInform" data-host="' + esc(host) + '" data-url="' + esc(p.url) + '">' + esc(p.label) + ' <span class="text-2xs opacity-70 ml-1">' + esc(p.url) + '</span></button>';
  }
  pickHtml += '</div>';
  pickHtml += '<div class="text-sm text-muted mb-1">' + esc(t('eller_angi_manuelt')) + '</div>';
  pickHtml += '<div class="flex gap-2 items-center">';
  pickHtml += '<input class="field-input flex-1 m-0" id="scan-inform-custom-url" type="text" placeholder="http://controller:8080/inform">';
  pickHtml += '<button class="btn btn-default btn-sm nowrap" data-click-handler="doScanSetInformCustomUrl" data-host="' + esc(host) + '">' + esc(t('btn_send', 'Send')) + '</button>';
  pickHtml += '</div>';
  bodyEl.innerHTML = pickHtml;
  var modal = document.getElementById('confirm-modal');
  modal.style.display = 'flex';
  // Hide default OK/Cancel — our inline buttons handle it; clicking backdrop closes
  modal.querySelector('.modal-actions').style.display = 'none';
}

async function doScanSetInform(host, url) {
  if (!url) { showToast(t('msg_enter_url', 'Enter a URL'), 'warning'); return; }
  var modal = document.getElementById('confirm-modal');
  modal.style.display = 'none';
  modal.querySelector('.modal-actions').style.display = '';
  try {
    var d = await apiFetch('/api/unifi/set-inform', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.assign(_deviceLogin(host), {controller_url: url}))
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
  row.hidden = false;
  cell.innerHTML = '<div class="p-2 text-muted text-sm">' + esc(t('msg_loading_config', 'Loading configuration...')) + '</div>';
  try {
    var d = await apiFetch('/api/unifi/device-config', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(_deviceLogin(host))
    });
    if (!d) { row.hidden = true; cell.innerHTML = ''; return; }
    if (d.ok && d.config) {
      _saveConfigBackup(host, d.config);
      cell.innerHTML = '<div class="p-2"><div class="flex items-center justify-between mb-1">'
        + '<span class="fw-semibold text-sm">' + esc(t('lbl_running_config', 'Running configuration')) + ' · ' + esc(host) + '</span>'
        + '<span class="text-2xs text-success">' + esc(t('msg_backup_saved', 'Backup saved')) + '</span></div>'
        + '<pre class="inset max-h-md overflow-auto text-xs pre-wrap break-all">' + esc(d.config) + '</pre>'
        + '<button class="btn btn-default btn-sm mt-2" data-click-handler="scanDeviceConfigClose" data-row-id="' + esc(rowId) + '">' + esc(t('btn_close', 'Close')) + '</button></div>';
    } else {
      cell.innerHTML = '<div class="alert alert-error text-sm">' + esc(d.error || t('msg_no_config', 'No config')) + '</div>';
    }
  } catch (e) {
    cell.innerHTML = '<div class="alert alert-error text-sm">' + esc(e.message) + '</div>';
  }
}

async function scanDeviceReboot(host) {
  if (!await showConfirm(t('dlg_confirm_restart_device', 'Restart {host}?').replace('{host}', host))) return;
  try {
    var d = await apiFetch('/api/unifi/reboot-device', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(_deviceLogin(host))
    });
    if (!d) return;
    if (d.ok) showToast(d.output || t('msg_device_rebooting'), 'success');
    else showToast(t('status_error') + ': ' + (d.error || t('err_unknown')), 'error');
  } catch (e) { showToast(t('status_error') + ': ' + e.message, 'error'); }
}

// ── Config backups ──

// The card shows once there is a backup: one is saved each time a device's
// running config is shown ("Vis konfig" on a quick check card or a scan row).
export async function loadConfigBackups() {
  var card = document.getElementById('cust-net-backups');
  var box = document.getElementById('config-backups-list');
  var cid = _netCustomerId;
  if (!box || !cid) return;
  try {
    var d = await apiFetch('/api/network/config-backups/' + encodeURIComponent(cid));
    if (!_netOnScreen(cid)) return;
    var backups = (d && d.backups) || [];
    if (card) card.hidden = !backups.length;
    if (!backups.length) { box.innerHTML = ''; return; }
    var html = '<table class="data-table cust-net-backups"><thead><tr><th>' + esc(t('lbl_timestamp', 'Timestamp')) + '</th><th>' + esc(t('lbl_device', 'Device')) + '</th><th class="num">' + esc(t('lbl_size', 'Size')) + '</th></tr></thead><tbody>';
    for (var b of backups) {
      html += '<tr>';
      html += '<td>' + esc(b.timestamp) + '</td>';
      html += '<td class="font-mono">' + esc(b.host) + '</td>';
      html += '<td class="num">' + Math.round(Number(b.size) / 1024) + ' KB</td>';
      html += '</tr>';
    }
    html += '</tbody></table>';
    box.innerHTML = html;
  } catch (e) {
    box.innerHTML = '<div class="alert alert-error">' + esc(e.message) + '</div>';
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
