// ═══════════════════════════════════════════════════════════════════
// CUSTOMER SETUP — actions, credentials & PKCE flow
// ═══════════════════════════════════════════════════════════════════

import {esc} from './app-esc.js';
import {t} from './app-i18n.js';
import {registerUiHandlers} from './app-handlers.js';
import {showConfirm, showToast} from './app-ui.js';
import {apiFetch} from './app-api.js';
import {applyWriteCapability, showView} from './app.js';

registerUiHandlers({
  setupCopyPkceUrl: function() { const el = document.getElementById('pkce-url-out'); el.select(); document.execCommand('copy'); },
  setupPastePkceOob: function() { navigator.clipboard.readText().then(text => document.getElementById('pkce-oob-input').value = text); },
  submitPkceOob: function() { submitPkceOob(); },
});

// ── Customer actions ───────────────────────────────────────────────────────────
// Renews one customer's credentials: the one whose page the button is on.
export async function renewCreds(customerId) {
  if (!customerId) return;
  if (!await showConfirm(t('dlg_confirm_renew'))) return;
  // Renewal issues a fresh certificate + client secret — exactly what first-run
  // setup does. Clear the old local credentials, then run the same device-code
  // sign-in so the operator finishes this one action with working, renewed
  // credentials, instead of being dropped back on a status page with none and a
  // "run setup again" note. startSetup() drives /api/setup/stream to completion.
  var d = await apiFetch('/api/customer/renew', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({customer_id: customerId}),
  });
  if (!d || !d.ok) return;
  startSetup();
}

// Setup ends by registering the customer it set up; the answer says which, and
// "Åpne kunden" opens that one (openSetupCustomer).
export var _setupCustomerId = null;
async function _registerSetupCustomer() {
  var reg = await apiFetch('/api/customers/register', {method: 'POST'});
  if (reg && reg.customer_id) _setupCustomerId = reg.customer_id;
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
export function _renderSetupIdle() {
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
    // What the operator will actually do. The sign-in is PKCE out-of-band: a
    // link opened in a private window, then the address of the blank page it
    // ends on pasted back. This used to promise "a one-time code", which is
    // the device-code flow the setup no longer uses.
    + '<ol class="setup-intro-steps">'
    +   '<li>' + esc(t('setup_intro_step_link')) + '</li>'
    +   '<li>' + esc(t('setup_intro_step_signin')) + '</li>'
    +   '<li>' + esc(t('setup_intro_step_paste')) + '</li>'
    + '</ol>'
    + '<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">'
    +   '<button data-write class="btn btn-primary" data-click-handler="startSetup">'
    +     esc(t('btn_start_setup')) + '</button>'
    +   '<span style="font-size:12px;color:var(--text-dim);">' + esc(t('setup_intro_needs_ga')) + '</span>'
    + '</div>';

  // The button is a write action; re-run the gate so a read-only user sees the
  // explanation without an action they cannot take.
  applyWriteCapability();
}


export function startSetup() {
  _setupRunning = true;
  showView('setup');
  var intro = document.getElementById('setup-intro');
  if (intro) intro.style.display = 'none';
  var card = _setupProgressCard();
  if (card) card.style.display = '';
  document.getElementById('setup-log').innerHTML = '';
  document.getElementById('setup-result-area').innerHTML = '';
  
  // New PKCE flow
  startPkceAuth();
}




async function startPkceAuth() {
  document.getElementById('pkce-login-card').classList.add('visible');
  document.getElementById('setup-log').innerHTML = '';
  appendSetupLog({step: 'AUTH', status: 'warn', msg: t('pkce_log_gen')});
  
  try {
    const res = await fetch('/api/setup/pkce/start');
    const data = await res.json();
    if (data.url) {
      appendSetupLog({step: 'AUTH', status: 'ok', msg: t('pkce_log_ready')});
      
      document.getElementById('pkce-login-card').innerHTML = `
        <div class="device-code-title">${esc(t('pkce_login_req'))}</div>
        <div class="device-code-step">${esc(t('pkce_desc'))}</div>
        
        <div style="margin: 12px 0; font-size: 13px;">
          1. ${t('pkce_step1_txt')}<br>
          2. ${t('pkce_step2_txt')}<br>
          3. ${t('pkce_step3_txt')}<br>
          4. ${t('pkce_step4_txt')}
        </div>
        
        <div style="margin:2px 0 16px; display:flex; align-items:center; gap:8px;">
          <span style="font-size:11px; color:var(--text-dim); font-weight: bold;">${esc(t('pkce_lbl_step1'))}</span>
          <input type="text" id="pkce-url-out" readonly value="${esc(data.url)}" style="flex: 1; padding: 6px; font-size: 11px; background: var(--bg); border: 1px solid var(--border); color: var(--text);">
          <button class="btn btn-default" style="padding: 4px 8px; font-size: 11px;" data-click-handler="setupCopyPkceUrl">${esc(t('btn_copy'))}</button>
        </div>
        
        <div style="margin:16px 0 2px; display:flex; align-items:center; gap:8px;">
          <span style="font-size:11px; color:var(--text-dim); font-weight: bold;">${esc(t('pkce_lbl_step4'))}</span>
          <input type="text" id="pkce-oob-input" placeholder="https://login.microsoftonline.com/common/oauth2/nativeclient?code=..." style="flex: 1; padding: 6px; font-size: 11px; background: var(--bg); border: 1px solid var(--border); color: var(--text);">
          <button class="btn btn-default" style="padding: 4px 8px; font-size: 11px;" data-click-handler="setupPastePkceOob">${esc(t('btn_paste'))}</button>
        </div>
        
        <div style="margin-top:12px;">
          <button class="btn btn-primary" data-click-handler="submitPkceOob" style="width: 100%;">${esc(t('pkce_btn_complete'))}</button>
        </div>
      `;
    } else {
      appendSetupLog({step: 'AUTH', status: 'error', msg: t('pkce_log_no_url')});
    }
  } catch (err) {
    appendSetupLog({step: 'NET', status: 'error', msg: String(err)});
  }
}

async function submitPkceOob() {
    const input = document.getElementById('pkce-oob-input').value.trim();
    if (!input) return;
    if (input.includes('/reprocess')) {
        appendSetupLog({step: 'AUTH', status: 'error', msg: t('pkce_log_early')});
        return;
    }
    
    let code = '';
    let state = '';
    try {
        const url = new URL(input);
        code = url.searchParams.get('code');
        state = url.searchParams.get('state');
    } catch(e) {
        appendSetupLog({step: 'AUTH', status: 'error', msg: t('pkce_log_invalid_url')});
        return;
    }
    
    if (!code || !state) {
        appendSetupLog({step: 'AUTH', status: 'error', msg: t('pkce_log_no_code')});
        return;
    }
    
    appendSetupLog({step: 'GRAPH', status: 'warn', msg: t('pkce_log_exchange')});
    
    try {
        const res = await apiFetch('/api/setup/pkce/callback-manual', {
            method: 'POST',
            body: JSON.stringify({code, state})
        });
        if (res && res.ok) {
            appendSetupLog({step: 'GRAPH', status: 'ok', msg: t('pkce_log_saved')});
            document.getElementById('pkce-login-card').classList.remove('visible');
            await _registerSetupCustomer();
            document.getElementById('setup-result-area').innerHTML = '<div class="alert alert-success">'+esc(t('msg_setup_complete'))+'</div><button class="btn btn-primary" data-click-handler="openSetupCustomer">'+esc(t('btn_open_customer'))+'</button>';
        } else {
            appendSetupLog({step: 'GRAPH', status: 'error', msg: t('pkce_log_error')});
        }
    } catch(err) {
        appendSetupLog({step: 'NET', status: 'error', msg: String(err)});
    }
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
    var resp = await fetch(url, {method: url.indexOf('attach=1') === -1 ? 'POST' : 'GET'});
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
              await _registerSetupCustomer();
              document.getElementById('setup-result-area').innerHTML =
                '<div class="alert alert-success">'+t('msg_setup_complete')+'</div><button class="btn btn-primary" data-click-handler="openSetupCustomer">'+t('btn_open_customer')+'</button>';
            } else {
              document.getElementById('setup-result-area').innerHTML =
                '<div class="alert alert-error">'+t('msg_setup_failed')+'</div><button class="btn btn-default" data-click-handler="startSetup">'+t('btn_try_again')+'</button>';
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
export function openPrivateBrowser() {
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

export function copyCode() {
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
export function copyDeviceUrl() {
  if (!_deviceCodeUrl) return;
  navigator.clipboard.writeText(_deviceCodeUrl).then(() => {
    showToast(t('msg_copied_short', 'Kopiert!'), 'success', 1500);
  }).catch(() => {});
}
