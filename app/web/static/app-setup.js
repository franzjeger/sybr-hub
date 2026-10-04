// ═══════════════════════════════════════════════════════════════════
// CUSTOMER SETUP — actions, credentials & PKCE flow
// ═══════════════════════════════════════════════════════════════════

import {esc} from './app-esc.js';
import {t} from './app-i18n.js';
import {registerUiHandlers} from './app-handlers.js';
import {showConfirm} from './app-ui.js';
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
  // setup does. Clear the old local credentials, then run the same sign-in
  // (startSetup, the PKCE flow) so the operator finishes this one action with
  // working, renewed credentials, instead of being dropped back on a status
  // page with none and a "run setup again" note.
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
    + '<div class="text-ui text-muted lh-relaxed mb-4">'
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
    + '<div class="flex items-center gap-3 flex-wrap">'
    +   '<button data-write class="btn btn-primary" data-click-handler="startSetup">'
    +     esc(t('btn_start_setup')) + '</button>'
    +   '<span class="text-sm text-dim">' + esc(t('setup_intro_needs_ga')) + '</span>'
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
        
        <div class="my-3 text-ui">
          1. ${t('pkce_step1_txt')}<br>
          2. ${t('pkce_step2_txt')}<br>
          3. ${t('pkce_step3_txt')}<br>
          4. ${t('pkce_step4_txt')}
        </div>
        
        <div class="mt-0-5 mb-4 flex items-center gap-2">
          <span class="text-xs text-dim fw-bold">${esc(t('pkce_lbl_step1'))}</span>
          <input type="text" id="pkce-url-out" readonly value="${esc(data.url)}" class="flex-1 p-2 text-xs bg-base border text-default">
          <button class="btn btn-default btn-sm" data-click-handler="setupCopyPkceUrl">${esc(t('btn_copy'))}</button>
        </div>
        
        <div class="mt-4 mb-0-5 flex items-center gap-2">
          <span class="text-xs text-dim fw-bold">${esc(t('pkce_lbl_step4'))}</span>
          <input type="text" id="pkce-oob-input" placeholder="https://login.microsoftonline.com/common/oauth2/nativeclient?code=..." class="flex-1 p-2 text-xs bg-base border text-default">
          <button class="btn btn-default btn-sm" data-click-handler="setupPastePkceOob">${esc(t('btn_paste'))}</button>
        </div>
        
        <div class="mt-3">
          <button class="btn btn-primary w-full" data-click-handler="submitPkceOob">${esc(t('pkce_btn_complete'))}</button>
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
