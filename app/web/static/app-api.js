// ═══════════════════════════════════════════════════════════════════
// API: apiFetch, the one way the interface calls the server
// ═══════════════════════════════════════════════════════════════════

import {connectionChecked} from './app-hooks.js';
import {_lang, t} from './app-i18n.js';
import {_currentUser, _writeExempt, canWrite} from './app-state.js';
import {showLoginView, showToast, showToastWithRetry} from './app-ui.js';

// Unique per document, including duplicated tabs. It carries only the report
// view's identity; cookies and server customer grants still authorize requests.
var _auditTab = typeof crypto.randomUUID === 'function' ? crypto.randomUUID()
  : Array.from(crypto.getRandomValues(new Uint8Array(16)), function(b) { return b.toString(16).padStart(2, '0'); }).join('');
export function auditTabHeaders(headers) {
  var out = new Headers(headers || {});
  out.set('X-Audit-Tab', _auditTab);
  return out;
}

export function setAuth() {
  // Remove credentials left by versions that persisted bearer tokens.
  localStorage.removeItem('msptk_token');
  localStorage.removeItem('msptk_refresh');
}

function _wouldBeRefused(url, options) {
  var method = ((options && options.method) || 'GET').toUpperCase();
  if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return false;
  // Until /auth/me has answered, the account and its exempt paths are not
  // known, and refusing then turned a customer switch made during start-up
  // into a "read access" toast for an admin. The server decides that case.
  if (!_currentUser) return false;
  if (canWrite()) return false;
  var path = String(url).split('?')[0].replace(/\/$/, '');
  return _writeExempt.indexOf(path) === -1;
}

var _sessionRecovery = null;

function recoverSession() {
  // An integration can return 401 while the Sybr session is still valid.
  // Share recovery across concurrent requests so refresh cookies cannot race.
  if (!_sessionRecovery) {
    _sessionRecovery = (async function() {
      var me = await fetch('/api/auth/me');
      if (me.ok) return 'valid';
      if (me.status !== 401) return 'unavailable';
      var ref = await fetch('/api/auth/refresh', {method:'POST'});
      if (ref.ok) return 'refreshed';
      // A refused refresh credential means sign in again. Only a server that
      // could not answer (5xx, rate limit, network) is a lost connection.
      if (ref.status === 400 || ref.status === 401 || ref.status === 403) return 'expired';
      return 'unavailable';
    })().catch(function() { return 'unavailable'; }).finally(function() {
      _sessionRecovery = null;
    });
  }
  return _sessionRecovery;
}

export async function apiFetch(url, options, _retryCount, _authRetried) {
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
  var requestOptions = Object.assign({}, options);
  requestOptions.headers = auditTabHeaders(options.headers);
  requestOptions.headers.set('Accept-Language', _lang === 'en' ? 'en' : 'nb-NO');
  delete requestOptions.onError;
  delete requestOptions.retry;
  try {
    var r = await fetch(url, requestOptions);
    if ((options.method || 'GET').toUpperCase() === 'POST' && (/^\/api\/(itglue|autotask|myitprocess|also|tailscale|email)\/test$/.test(url) || url === '/api/settings' || url === '/api/gdap/setup')) setTimeout(connectionChecked, 0);
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
      var eb = null;
      try {
        eb = await r.json();
        errBody = eb.error_key ? t(eb.error_key, eb.error) : (eb.error || eb.detail || JSON.stringify(eb));
        if (eb.error_id) errBody += ' (' + t('lbl_error_id', 'Feil-ID') + ': ' + eb.error_id + ')';
      } catch(_) { errBody = await r.text().catch(function(){return '';}); }
      var safeRead = /^(GET|HEAD)$/.test((options.method || 'GET').toUpperCase());
      if (options.retry !== false && safeRead && (!eb || eb.error_type !== 'integration_error') && _retryCount < maxRetries) {
        showToast(t('err_server_error','Server error') + ' (' + (_retryCount+1) + '/' + maxRetries + '): ' + (errBody || r.status), 'warning', 3000);
        await new Promise(function(resolve) { setTimeout(resolve, 3000); });
        return apiFetch(url, options, _retryCount + 1, _authRetried);
      }
      if (options.onError) options.onError(errBody || 'HTTP ' + r.status);
      if (options.retry === false) showToast(errBody || 'HTTP ' + r.status, 'error');
      else showToastWithRetry(t('err_server_error','Server error') + ': ' + (errBody || 'HTTP ' + r.status), function() { apiFetch(url, options, 0); }, 'error', eb && eb.error_key || url);
      console.error('API error', url, r.status, errBody);
      return null;
    }
    if (r.status === 401) {
      var sessionState = await recoverSession();
      if (sessionState === 'expired') {
        setAuth();
        showLoginView('login');
        return null;
      }
      if (sessionState === 'unavailable') {
        if (options.onError) options.onError(t('toast_lost_connection'));
        if (options.retry === false) showToast(t('toast_lost_connection'), 'error');
        else showToastWithRetry(t('toast_lost_connection'), function() { apiFetch(url, options, 0); });
        return null;
      }
      if (sessionState === 'refreshed' && !_authRetried) return apiFetch(url, options, _retryCount, true);
      // Our session is valid: display the endpoint's error below.
    }
    if (r.status >= 400) {
      // Client error — show message from body
      var errMsg = t('err_request_failed').replace('{status}', r.status);
      try {
        const errBody = await r.json();
        if (errBody.error_key) errMsg = t(errBody.error_key, errBody.error);
        else if (errBody.error) errMsg = errBody.error;
        else if (errBody.detail) errMsg = errBody.detail;
        else if (errBody.message) errMsg = errBody.message;
      } catch(_) {}
      if (options.onError) options.onError(errMsg);
      showToast(errMsg, 'error');
      return null;
    }
    return null;
  } catch (e) {
    // Network error
    if (options.onError) options.onError(t('toast_lost_connection'));
    if (options.retry === false) showToast(t('toast_lost_connection'), 'error');
    else showToastWithRetry(t('toast_lost_connection'), function() { apiFetch(url, options, 0); });
    return null;
  }
}
