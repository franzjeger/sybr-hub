// ═══════════════════════════════════════════════════════════════════
// SHELL: the views and the address bar, signing in, the command palette,
// the top-bar menus and the connection chip
// ═══════════════════════════════════════════════════════════════════
//
// The helpers every screen uses live in leaf scripts of their own:
//   app-esc.js       esc()
//   app-i18n.js      ui_i18n.json, t(), the interface language
//   app-icons.js     icon(), hydrateIcons()
//   app-handlers.js  registerUiHandlers() and the event dispatcher
//   app-hooks.js     onViewShown(), onSignedIn() and the other registries
//   app-state.js     the account, this tab's customer, the customer page,
//                    the shared customer lists
//   app-format.js    figures, run names, dates and sizes
//   app-ui.js        toasts, confirm dialogs, the login screen, skeletons
//   app-api.js       apiFetch()
// Each feature is a script of its own (app-audit.js, app-dashboard.js, ...).

import {esc} from './app-esc.js';
import {t} from './app-i18n.js';
import {icon} from './app-icons.js';
import {registerUiHandlers} from './app-handlers.js';
import {reloadToolCustomer, signedIn, viewShown} from './app-hooks.js';
import {
  _allCustomers, _allowedViews, _currentUser, _overviewData, canOpenView, canTenantWrite,
  canWrite, currentCustomerId, hasFeature, hasModule, setAllCustomers, setCurrentCustomer,
  setCurrentUser, setOverviewData, setSession,
} from './app-state.js';
import {hideLoginView, showLoginView, showToast, skeletonHTML} from './app-ui.js';
import {apiFetch, setAuth} from './app-api.js';
import {dashLoadFortiGates, dashLoadUnifiAll} from './app-infra.js';
import {loadOverview, stopDashAutoRefresh, stopDashRefreshInterval} from './app-dashboard.js';
import {stopAlsoScans} from './app-also.js';
import {tlsLoadView} from './app-tls.js';
import {_renderSetupIdle, renewCreds} from './app-setup.js';
import {
  _reconcileAuditState, applyPreset, deleteCustomPreset, saveCustomPreset, scopeDeselectAll,
  scopeSelectAll, startAudit, stopAuditProgressPolling, toggleScopePanel,
} from './app-audit.js';
import {
  _adminPane, adminMayLeave, applyBranding, checkPermissions, openAccountModal, openAdmin,
  showMfaSettings,
} from './app-settings.js';
import {loadNetworkDevices, setNetCustomerId} from './app-network.js';
import {
  _bulkAuditEventSource, exportDashboardExcel, loadCustomers, openTagEditor,
  overviewSelectCustomer,
} from './app-customers.js';
import {
  _custHash, CUSTOMER_TAB_ALIASES, openCurrentCustomerTab, openCustomerPage,
} from './app-customer-detail.js';
import {
  _checkNotifBadge, _checkVpnHeaderBadge, _syncBottomNav, loadLogs, stopLogAutoRefresh,
} from './app-chrome.js';

// Handlers shared by markup in several scripts (the generic ones are in
// app-handlers.js).
registerUiHandlers({
  showView: function(el) { showView(el.dataset.view); },
});

// Handlers for the markup app.js builds: the command palette and Home.
registerUiHandlers({
  runCommandPaletteItem: function(el) {
    closeCommandPalette();
    _cmdActions[Number(el.dataset.index)]();
  },
  openTagEditor: function(el) { openTagEditor(el.dataset.customerId, JSON.parse(el.dataset.tags)); },
  checkPermissions: function(el) { checkPermissions(el.dataset.customerId); },
  renewCreds: function(el) { renewCreds(el.dataset.customerId); },
  toggleScopePanel: function() { toggleScopePanel(); },
  applyPreset: function() { applyPreset(); },
  saveCustomPreset: function() { saveCustomPreset(); },
  deleteCustomPreset: function() { deleteCustomPreset(); },
  scopeSelectAll: function() { scopeSelectAll(); },
  scopeDeselectAll: function() { scopeDeselectAll(); },
});

// ── Command Palette (Cmd+K) ──────────────────────────────────────────────────
var _cmdPaletteOpen = false;
var _cmdSelectedIdx = -1;
// The actions runCommandPaletteItem calls, by data-index.
var _cmdActions = [];

export function toggleCommandPalette() { _cmdPaletteOpen ? closeCommandPalette() : openCommandPalette(); }

function openCommandPalette() {
  var el = document.getElementById('cmd-palette');
  el.style.display = 'flex';
  _cmdPaletteOpen = true;
  _cmdSelectedIdx = -1;
  var input = document.getElementById('cmd-input');
  input.value = '';
  input.focus();
  _renderCmdResults('');
  // Recent customers and customer search need the customer list. Opened
  // before anything had loaded it, the palette had neither.
  if (!_overviewData) {
    apiFetch('/api/dashboard/overview').then(function(d) {
      if (d && !_overviewData) setOverviewData({customers: d.customers || []});
      if (_cmdPaletteOpen) _renderCmdResults(input.value);
    });
  }
  input.oninput = function() { _renderCmdResults(this.value); _cmdSelectedIdx = -1; };
  input.onkeydown = function(e) {
    var items = document.querySelectorAll('.cmd-item');
    if (e.key === 'ArrowDown') { e.preventDefault(); _cmdSelectedIdx = Math.min(_cmdSelectedIdx+1, items.length-1); _highlightCmd(items); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); _cmdSelectedIdx = Math.max(_cmdSelectedIdx-1, 0); _highlightCmd(items); }
    else if (e.key === 'Enter') {
      // Enter takes the highlighted result, or the first one once something
      // is typed: "Beta" then Enter opened nothing until an arrow key had
      // picked the only match.
      var pick = _cmdSelectedIdx >= 0 ? items[_cmdSelectedIdx] : (input.value.trim() ? items[0] : null);
      if (pick) { e.preventDefault(); pick.click(); }
    }
    else if (e.key === 'Escape') { closeCommandPalette(); }
  };
}
export function closeCommandPalette() {
  document.getElementById('cmd-palette').style.display = 'none';
  _cmdPaletteOpen = false;
  // Focus left in the hidden input made every shortcut after a pick read as
  // typing: Ctrl+1 straight after choosing a customer did nothing.
  var input = document.getElementById('cmd-input');
  if (input && document.activeElement === input) input.blur();
}
function _highlightCmd(items) {
  items.forEach(function(el, i) { el.style.background = i === _cmdSelectedIdx ? 'rgba(77,159,181,0.15)' : ''; });
  if (items[_cmdSelectedIdx]) items[_cmdSelectedIdx].scrollIntoView({block:'nearest'});
}

function _renderCmdResults(query) {
  var q = (query || '').toLowerCase().trim();
  var results = [];

  // Recent customers (shown when search is empty)
  if (!q && _overviewData && _overviewData.customers) {
    var recentIds = JSON.parse(localStorage.getItem('sybr_recent_customers') || '[]');
    if (recentIds.length > 0) {
      recentIds.forEach(function(rid) {
        var rc = _overviewData.customers.find(function(c){ return c.customer_id === rid || c._id === rid; });
        if (rc) {
          results.push({
            label: rc.customer_name,
            hint: rc.primary_domain || '',
            icon: 'clock',
            action: function(){ overviewSelectCustomer(rid); },
            type: 'recent'
          });
        }
      });
    }
  }

  // Pages / Navigation
  var pages = [
    {label:t('nav_overview','Oversikt'), view:'overview', action:function(){showView('overview')},  section:'', icon:'grid'},
    {label:t('nav_customers','Customers'), view:'customers', action:function(){showView('customers')}, section:t('nav_customers'), icon:'users'},
    // Verktøy, in the order of its menu.
    {label:t('nav_network','Nettverk'), view:'network', action:function(){showView('network')}, section:t('nav_tools','Verktøy'), icon:'globe'},
    {label:t('tls_monitor','TLS-monitor'), view:'network', action:function(){showNetworkTab('net-tls')}, section:t('nav_network','Nettverk'), icon:'shield'},
    {label:'VPN', view:'vpn', action:function(){showView('vpn')}, section:t('nav_tools','Verktøy'), icon:'lock'},
    {label:t('nav_remote_access2','Fjerntilgang'), view:'hosts', action:function(){showView('hosts')}, section:t('nav_tools','Verktøy'), icon:'monitor'},
    {label:t('nav_browser2','Browser'), view:'browser', action:function(){showView('browser')}, section:t('nav_remote_access2','Fjerntilgang'), icon:'globe'},
    {label:'Tailscale', view:'tailscale', action:function(){showView('tailscale')}, section:t('nav_tools','Verktøy'), icon:'link'},
    {label:t('pentest','Pentest'), view:'pentest', action:function(){showView('pentest')}, section:t('nav_tools','Verktøy'), icon:'shield'},
    {label:t('provisjonering','Provisjonering'), view:'provision', action:function(){showView('provision')}, section:t('nav_tools','Verktøy'), icon:'gear'},
    {label:t('nav_billing','Lisenser og hosting'), view:'billing', action:function(){showView('billing')}, section:t('nav_tools','Verktøy'), icon:'chart'},
    {label:'Sybrt', view:'ai', action:function(){showView('ai')}, section:t('nav_tools','Verktøy'), icon:'sparkle'},
    {label:t('nav_help','Hjelp'), view:'docs', action:function(){showView('docs')}, section:'', icon:'document'},
    // Administrasjon and its panes, named by id: the palette used to pick
    // a settings tab by its position in the strip.
    {label:t('nav_admin','Administrasjon'), view:'admin', action:function(){openAdmin()}, section:'', icon:'gear'},
    {label:t('nav_integrations','Integrations'), view:'admin', action:function(){openAdmin('integrations')}, section:t('nav_admin'), icon:'plug'},
    {label:t('admin_alerts','Varsler og planlagte oppgaver'), view:'admin', action:function(){openAdmin('alerts')}, section:t('nav_admin'), icon:'bell'},
    {label:t('tab_users','Users'), view:'admin', action:function(){openAdmin('users')}, section:t('nav_admin'), icon:'users'},
    {label:t('tab_modules','Moduler'), view:'admin', action:function(){openAdmin('modules')}, section:t('nav_admin'), icon:'grid'},
    {label:t('hdr_branding','Branding'), view:'admin', action:function(){openAdmin('branding')}, section:t('nav_admin'), icon:'palette'},
    {label:t('admin_storage','Lagring og backup'), view:'admin', action:function(){openAdmin('storage')}, section:t('nav_admin'), icon:'document'},
    {label:t('admin_system','System'), view:'admin', action:function(){openAdmin('system')}, section:t('nav_admin'), icon:'gear'},
    {label:t('bc_log','Log'), view:'logs', action:function(){showView('logs')}, section:t('nav_admin'), icon:'document'},
    {label:t('konto','Konto'), action:function(){openAccountModal()}, section:'', icon:'users'},
  ];
  // A page the account cannot open is not offered: the palette listed every
  // view, and picking one this account may not see opened a blank page.
  var isAdmin = !!(_currentUser && _currentUser.role === 'admin');
  pages = pages.filter(function(p) { return (!p.view || canOpenView(p.view)) && (!p.admin || isAdmin); });
  pages.forEach(function(p) {
    if (!q || p.label.toLowerCase().includes(q) || (p.section||'').toLowerCase().includes(q))
      results.push({label:p.label, hint:p.section, icon:p.icon, action:p.action, type:'page'});
  });

  // Actions
  var actions = [
    {label:t('btn_run_audit'),       action:function(){startAudit()}, hint:'Ctrl+Shift+A', icon:'play'},
    {label:t('btn_export_excel','Export Excel'), action:function(){exportDashboardExcel()},                    hint:'',             icon:'chart'},
  ];
  if (!canWrite()) actions = actions.filter(function(a) { return a.label !== t('btn_run_audit'); });
  if (q) {
    actions.forEach(function(a) {
      if (a.label.toLowerCase().includes(q)) results.push({label:a.label, hint:a.hint, icon:a.icon, action:a.action, type:'action'});
    });
  }

  // Customers (dynamic from cached overview data)
  if (q && _overviewData && _overviewData.customers) {
    _overviewData.customers.forEach(function(c) {
      if (c.customer_name.toLowerCase().includes(q) || (c.primary_domain||'').toLowerCase().includes(q)) {
        results.push({
          label: c.customer_name,
          hint: c.primary_domain || '',
          icon: 'building',
          action: function(){ overviewSelectCustomer(c.customer_id); },
          type: 'customer'
        });
      }
    });
  }

  // Render
  var html = '';
  if (results.length === 0) {
    html = '<div style="padding:var(--space-8) var(--space-5);text-align:center;color:var(--text-dim);font-size:var(--font-sm);">' + t('msg_no_results', 'Ingen treff') + '</div>';
  } else {
    var lastType = '';
    results.forEach(function(r, i) {
      if (r.type !== lastType) {
        var sectionLabel = r.type === 'recent' ? t('lbl_recent','Nylige') : r.type === 'page' ? t('lbl_navigation','Navigasjon') : r.type === 'action' ? t('lbl_actions','Handlinger') : r.type === 'finding' ? t('lbl_findings','Funn') : t('nav_customers');
        html += '<div style="padding:var(--space-1) var(--space-5);font-size:var(--font-xs);color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;font-weight:600;'+(lastType?'margin-top:var(--space-2);border-top:1px solid var(--border);padding-top:var(--space-2);':'')+'">' + sectionLabel + '</div>';
        lastType = r.type;
      }
      html += '<div class="cmd-item" tabindex="-1" data-click-handler="runCommandPaletteItem" data-index="' + i + '" style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-2) var(--space-5);cursor:pointer;transition:background 0.1s;border-radius:0;">'
        + '<span style="width:24px;flex-shrink:0;display:flex;align-items:center;justify-content:center;color:var(--text-muted);">' + icon(r.icon, 16) + '</span>'
        + '<span style="flex:1;font-size:var(--font-base);color:var(--text);">' + esc(r.label) + '</span>'
        + (r.hint ? '<span style="font-size:var(--font-xs);color:var(--text-dim);">' + esc(r.hint) + '</span>' : '')
        + '</div>';
    });
  }
  document.getElementById('cmd-results').innerHTML = html;
  _cmdActions = results.map(function(r){return r.action});
}

// Called once on load (main.js, after the strings) and again after a
// sign-in. Not shared between callers: a check that began before the sign-in
// would answer "signed out" for the one after it.
export async function checkAuth() {
  try {
    var res = await fetch('/api/auth/status');
    var data = await res.json();
    // The endpoint reports setup_required. Reading a setup_complete that the
    // server never sends made this !undefined === true on every call, so the
    // setup form came back even straight after it had succeeded — and the
    // second attempt then failed with "Oppsett er allerede fullført".
    if (data.setup_required) { showLoginView('setup'); return; }
    // Validate the HttpOnly access cookie.
    var me = await fetch('/api/auth/me');
    if (me.status === 401) {
      // The refresh token is another HttpOnly cookie; no token enters JS.
      var ref = await fetch('/api/auth/refresh', {method:'POST'});
      if (!ref.ok) { showLoginView('login'); return; }
      me = await fetch('/api/auth/me');
    }
    if (!me.ok) { showLoginView('login'); return; }
    if (me.ok) {
      var _me = await me.json();
      setSession(_me);
      hideLoginView(); updateUserDisplay();
      if (_me.mfa_required) { await showMfaSettings(); } else { _postAuthInit(); }
    }
  } catch(e) { console.error('Request failed:', e); showLoginView('login'); }
}

function _postAuthInit() {
  // Land where the address says, else on the cross-customer dashboard: the
  // question a technician arrives with is "which customer needs me", not
  // whichever customer was active last time.
  applyRoute();
  applyBranding();
  _checkNotifBadge();
  _checkVpnHeaderBadge();
  startConnectionMonitor();
  signedIn();
}

// ── Live connection monitor ───────────────────────────────────────────────
// Polls /api/health (public, unauth) every 30 s. Updates the dot in the
// header: green=ok, yellow=checking/timeout, red=down. Reflects both the
// browser's navigator.onLine state and the server's db_ok field. Cheap
// enough to run continuously after login.

var _connMonitorInterval = null;
var _connLastOk = true;

// The chip is quiet when everything is fine: it shows while a VPN tunnel is
// up, and when the server cannot be reached.
var _connState = 'ok';
var _vpnTunnelUp = false;

// The VPN badge (app-chrome.js) says whether a tunnel is up.
export function setVpnTunnelUp(up) {
  _vpnTunnelUp = up;
}

export function _syncConnChip() {
  var box = document.getElementById('conn-status');
  if (box) box.style.display = (_vpnTunnelUp || _connState !== 'ok') ? 'flex' : 'none';
}

function _setConnStatus(state, label, title) {
  var box = document.getElementById('conn-status');
  var dot = document.getElementById('conn-status-dot');
  var lbl = document.getElementById('conn-status-label');
  if (!box || !dot) return;
  // A check in flight is no news; keep what the last answer said.
  if (state !== 'checking') _connState = state;
  _syncConnChip();
  var colors = {
    ok:       'var(--color-success)',
    checking: 'var(--color-warning)',
    down:     'var(--color-danger)',
  };
  dot.style.background = colors[state] || 'var(--text-dim)';
  if (lbl) lbl.textContent = label;
  box.title = title || label;
}

async function _pollConnection() {
  if (!navigator.onLine) {
    _setConnStatus('down', t('conn_offline', 'Offline'), t('conn_offline_title', 'Ingen nettverksforbindelse'));
    _connLastOk = false;
    return;
  }
  _setConnStatus('checking', t('conn_checking', '...'), t('conn_checking_title', 'Sjekker server'));
  try {
    var ctrl = new AbortController();
    var timeoutId = setTimeout(function() { ctrl.abort(); }, 5000);
    var r = await fetch('/api/health', { signal: ctrl.signal, cache: 'no-store' });
    clearTimeout(timeoutId);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    var d = await r.json();
    if (d && d.status === 'ok' && d.db_ok) {
      _setConnStatus('ok', t('conn_live', 'Live'), t('conn_live_title', 'Server OK — v{v}').replace('{v}', d.version || '?'));
      if (!_connLastOk) {
        showToast(t('msg_connection_restored', 'Forbindelse gjenopprettet'), 'success', 2000);
      }
      _connLastOk = true;
    } else {
      _setConnStatus('down', t('conn_degraded', 'Degradert'), t('conn_degraded_title', 'Server svarer, men DB utilgjengelig'));
      _connLastOk = false;
    }
  } catch (e) {
    _setConnStatus('down', t('conn_down', 'Nede'), t('conn_down_title', 'Ingen svar fra server'));
    _connLastOk = false;
  }
}

function startConnectionMonitor() {
  if (_connMonitorInterval) return;
  _pollConnection();
  _connMonitorInterval = setInterval(_pollConnection, 30000);
  // Also re-poll when the tab becomes visible again and on network events.
  document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible') _pollConnection();
  });
  window.addEventListener('online', _pollConnection);
  window.addEventListener('offline', _pollConnection);
}

function updateUserDisplay() {
  if (!_currentUser) return;
  var role = _currentUser.role || '';
  var fullName = _currentUser.display_name || _currentUser.username || '';
  var initials = fullName.split(/\s+/).filter(Boolean).map(function(w){return w.charAt(0).toUpperCase()}).join('').substring(0, 2) || '?';
  // Populate the avatar button + account-menu identity header (frame 3a).
  var ini = document.getElementById('avatar-initials');
  if (ini) ini.textContent = initials;
  var nm = document.getElementById('avatar-name');
  if (nm) nm.textContent = fullName;
  var em = document.getElementById('avatar-email');
  if (em) em.textContent = _currentUser.email || _currentUser.username || '';
  var btn = document.getElementById('avatar-btn');
  if (btn) btn.title = fullName + (role ? ' (' + role + ')' : '');
  // Legacy hidden element — kept so any remaining reference resolves.
  var el = document.getElementById('user-display');
  if (el) el.textContent = initials;
  applyWriteCapability();
  // An audit may already be running — started by a schedule, another tab, or
  // another technician. Ask rather than assume; the badge should reflect the
  // server on every load, not only when somebody opens the audit view.
  _reconcileAuditState();
}

export function applyFeatureVisibility() {
  // Marked elements name a feature; unmarked ones are visible to anyone who
  // signed in. Same shape as data-write, and deliberately a separate attribute:
  // "may change things" and "may reach this at all" are different questions and
  // conflating them is how one of them stops being asked.
  document.querySelectorAll('[data-feature]').forEach(function(el) {
    _setGated(el, hasFeature(el.getAttribute('data-feature')));
  });
  document.querySelectorAll('[data-view-gate]').forEach(function(el) {
    _setGated(el, canOpenView(el.getAttribute('data-view-gate')));
  });
  // An optional module an administrator switched off is gone for everyone,
  // and its controls with it (app/core/modules.py).
  document.querySelectorAll('[data-module]').forEach(function(el) {
    _setGated(el, hasModule(el.getAttribute('data-module')));
  });
  _syncToolsMenu();
}

// A gate answers "may this be seen at all", never "is this showing right now".
// Writing style.display='' on everything allowed answered the second question
// too, and wiped out whatever the element's own state had decided. The audit
// badge carries a view gate and hides itself when no audit is running, so
// every page load un-hid it and announced a run that was not happening —
// nav-logs and the connection chip are state-driven the same way.
// Hiding via a class leaves that state untouched, and !important still beats
// an inline display on the elements a user genuinely may not see.
function _setGated(el, allowed) {
  el.classList.toggle('gated-hidden', !allowed);
}

export function applyWriteCapability() {
  var write = canWrite();
  document.body.classList.toggle('is-readonly', !write);
  // Second tier: an account with can_write but not tenant_write sees ordinary
  // write controls and not the tenant-changing ones. is-readonly already hides
  // every [data-write] (tenant ones included), so this only has to catch the
  // in-between account; the overlap on a read-only user is harmless.
  document.body.classList.toggle('is-no-tenant-write', !canTenantWrite());
  // [data-admin-only]: server paths, backup, the API reference. Hidden by
  // CSS for everyone else, the same way is-readonly hides [data-write].
  document.body.classList.toggle('is-admin', !!(_currentUser && _currentUser.role === 'admin'));
  applyFeatureVisibility();
  var badge = document.getElementById('readonly-badge');
  if (badge) {
    badge.style.display = write ? 'none' : '';
    badge.title = t('tip_readonly', 'Your account has read access. Changes require write.');
    badge.textContent = t('lbl_readonly', 'Read-only');
  }
}

// ── Verktøy ───────────────────────────────────────────────────────────────────
// Opens on hover (CSS) and on a click, so touch and keyboard reach it too.
export function toggleToolsMenu(e) {
  if (e) e.stopPropagation();
  var dd = document.getElementById('nav-tools-dd');
  if (!dd) return;
  if (dd.classList.contains('open')) { closeToolsMenu(); return; }
  dd.classList.remove('is-resting');
  dd.classList.add('open');
  var btn = document.getElementById('nav-tools');
  if (btn) btn.setAttribute('aria-expanded', 'true');
  setTimeout(function() {
    document.addEventListener('click', _closeToolsMenuOutside);
    document.addEventListener('keydown', _closeToolsMenuEsc);
  }, 0);
}
function closeToolsMenu() {
  var dd = document.getElementById('nav-tools-dd');
  if (dd) {
    dd.classList.remove('open');
    // Chosen with the pointer still over the menu, hover would hold it open
    // over the page that just opened; it rests until the pointer leaves.
    if (dd.matches(':hover')) {
      dd.classList.add('is-resting');
      dd.addEventListener('mouseleave', function rest() {
        dd.classList.remove('is-resting');
        dd.removeEventListener('mouseleave', rest);
      });
    }
  }
  var btn = document.getElementById('nav-tools');
  if (btn) btn.setAttribute('aria-expanded', 'false');
  document.removeEventListener('click', _closeToolsMenuOutside);
  document.removeEventListener('keydown', _closeToolsMenuEsc);
}
function _closeToolsMenuOutside(e) {
  var dd = document.getElementById('nav-tools-dd');
  if (dd && !dd.contains(e.target)) closeToolsMenu();
}
function _closeToolsMenuEsc(e) { if (e.key === 'Escape') closeToolsMenu(); }

// Verktøy with nothing in it this account may open is no menu at all.
function _syncToolsMenu() {
  var dd = document.getElementById('nav-tools-dd');
  if (!dd) return;
  var items = dd.querySelectorAll('.navdd-item');
  var any = Array.prototype.some.call(items, function(el) { return getComputedStyle(el).display !== 'none'; });
  dd.classList.toggle('gated-hidden', !any);
}

// ── Avatar account menu ──────────────────────────────────────────────────────
export function toggleAvatarMenu(e) {
  if (e) e.stopPropagation();
  var m = document.getElementById('avatar-menu');
  var b = document.getElementById('avatar-btn');
  if (!m) return;
  var open = m.classList.toggle('open');
  if (b) b.classList.toggle('open', open);
  if (open) {
    // Defer so this same click doesn't immediately close it.
    setTimeout(function() {
      document.addEventListener('click', _closeAvatarMenuOutside);
      document.addEventListener('keydown', _closeAvatarMenuEsc);
    }, 0);
  } else {
    _detachAvatarMenuListeners();
  }
}
export function closeAvatarMenu() {
  var m = document.getElementById('avatar-menu');
  var b = document.getElementById('avatar-btn');
  if (m) m.classList.remove('open');
  if (b) b.classList.remove('open');
  _detachAvatarMenuListeners();
}
function _detachAvatarMenuListeners() {
  document.removeEventListener('click', _closeAvatarMenuOutside);
  document.removeEventListener('keydown', _closeAvatarMenuEsc);
}
function _closeAvatarMenuOutside(e) {
  var m = document.getElementById('avatar-menu');
  var b = document.getElementById('avatar-btn');
  if (m && !m.contains(e.target) && b && !b.contains(e.target)) closeAvatarMenu();
}
function _closeAvatarMenuEsc(e) { if (e.key === 'Escape') closeAvatarMenu(); }

export async function doLogin() {
  var u = document.getElementById('login-username').value.trim();
  var p = document.getElementById('login-password').value;
  if (!u || !p) return;
  try {
    var res = await fetch('/api/auth/login', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p,otp:document.getElementById('login-otp').value.trim()})});
    if (!res.ok) { var err = await res.json(); showToast(err.error||t('err_login_failed','Login failed'),'error'); return; }
    setAuth();
    // checkAuth shows the app once /auth/me has said who signed in. Shown
    // here, the menus were live for an account the page did not know yet:
    // Administrasjon clicked in that moment opened Konto, as for a viewer.
    await checkAuth();
  } catch(e) { console.error('Request failed:', e); showToast(t('err_login_failed','Login failed'),'error'); }
}

// Mirrors validate_password() on the server, so a form can state the rule
// instead of a round-trip teaching it. The server stays the authority.
export function passwordMeetsRule(p) {
  return typeof p === 'string' && p.length >= 10 && /[A-Za-z]/.test(p) && /[0-9]/.test(p) && /[^A-Za-z0-9]/.test(p);
}

export async function doSetup() {
  var u = document.getElementById('setup-username').value.trim();
  var p = document.getElementById('setup-password').value;
  var n = document.getElementById('setup-displayname').value.trim();
  if (!u || !p || !n) { showToast(t('err_fill_all_fields','Fill in all fields'),'error'); return; }
  if (!passwordMeetsRule(p)) { showToast(t('err_password_rule'), 'error'); return; }
  try {
    var res = await fetch('/api/auth/setup', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p,display_name:n})});
    if (!res.ok) { var err = await res.json(); showToast(err.error||t('err_setup_failed','Setup failed'),'error'); return; }
    setAuth();
    hideLoginView();
    _postAuthInit();
    showToast(t('msg_admin_created','Admin account created!'),'success');
    checkAuth();
  } catch(e) { console.error('Request failed:', e); showToast(t('err_setup_failed','Setup failed'),'error'); }
}

export async function doLogout() {
  await apiFetch('/api/auth/logout', {method:'POST'});
  setAuth(null, null);
  setCurrentUser(null);
  showLoginView('login');
}

// ── Tools that act on one customer ──────────────────────────────────────────
// Nettverk's Enheter and Audit and the FortiGate API form each work on one
// customer at a time. They say which in a customer bar ([data-tool-customer]),
// whose choice is this tab's current customer; picking another there changes
// it for this tab only and reloads the tool. A tool sends that id with every
// call; there is no customer the server would assume.
async function _ensureCustomerList() {
  if (!_allCustomers || !_allCustomers.length) {
    var cs = await apiFetch('/api/customers');
    if (cs) setAllCustomers(cs.customers || []);
  }
  return _allCustomers || [];
}

// This tab's current customer, if this account can still see it.
export async function toolCustomerId() {
  var list = await _ensureCustomerList();
  var id = currentCustomerId();
  return list.some(function(c) { return c._id === id; }) ? id : null;
}

export async function renderToolCustomerPickers() {
  var bars = document.querySelectorAll('[data-tool-customer]');
  if (!bars.length) return;
  var list = await _ensureCustomerList();
  var current = await toolCustomerId();
  bars.forEach(function(bar) {
    var opts = '<option value="">' + esc(t('lbl_choose_customer', 'Velg kunde')) + '</option>'
      + list.map(function(c) {
        return '<option value="' + esc(c._id) + '"' + (c._id === current ? ' selected' : '') + '>' + esc(c.CustomerName || c._id) + '</option>';
      }).join('');
    bar.innerHTML = '<label class="tool-customer-label"><span>' + esc(t('lbl_tool_customer', 'Kunde')) + '</span>'
      + '<select class="field-input tool-customer-select" data-change-handler="toolCustomerChanged" data-tool="' + esc(bar.dataset.toolCustomer) + '">'
      + opts + '</select></label>';
  });
}

export function toolNoCustomerHtml() {
  return '<div class="empty-signpost"><p>' + esc(t('msg_tool_choose_customer', 'Velg kunden verktøyet skal gjelde, i feltet Kunde over.')) + '</p></div>';
}

registerUiHandlers({
  toolCustomerChanged: function(el) {
    if (!el.value) return;   // the empty first option is a prompt, not a choice
    setCurrentCustomer(el.value);
    document.querySelectorAll('.tool-customer-select').forEach(function(s) { if (s !== el) s.value = el.value; });
    reloadToolCustomer(el.dataset.tool);
  },
});

// ── State ──────────────────────────────────────────────────────────────────────
export let currentView = 'home';

// ── View routing ───────────────────────────────────────────────────────────────

// Which top-bar item a view belongs to, so the bar, the breadcrumb and the
// mobile bar agree. Views the avatar menu opens (Administrasjon, Hjelp) light
// none of the three.
var _NAV_GROUP = {
  overview: 'overview',
  customers: 'customers', 'customer-detail': 'customers', setup: 'customers',
  network: 'tools', vpn: 'tools', hosts: 'tools', terminal: 'tools', rdp: 'tools', ssh: 'tools',
  browser: 'tools', tailscale: 'tools', pentest: 'tools', provision: 'tools', billing: 'tools', ai: 'tools',
};

function _updateBreadcrumb(name) {
  var bc = document.getElementById('breadcrumb');
  var items = document.getElementById('breadcrumb-items');
  if (!bc || !items) return;
  var tools = {label:t('nav_tools','Verktøy')};
  var remote = {label:t('nav_remote_access2','Fjerntilgang'),view:'hosts'};
  var map = {
    overview:     [{label:t('nav_overview','Oversikt')}],
    customers:    [{label:t('nav_customers')}],
    setup:        [{label:t('nav_customers'),view:'customers'}, {label:t('nav_new_customer','Ny kunde')}],
    network:      [tools, {label:t('nav_network','Nettverk')}],
    vpn:          [tools, {label:'VPN'}],
    hosts:        [tools, {label:t('nav_remote_access2','Fjerntilgang')}],
    terminal:     [tools, remote, {label:t('hdr_terminal','Terminal')}],
    rdp:          [tools, remote, {label:'RDP'}],
    ssh:          [tools, remote, {label:t('bc_ssh_keys','SSH-nøkler')}],
    browser:      [tools, remote, {label:t('nettleser','Nettleser')}],
    tailscale:    [tools, {label:'Tailscale'}],
    pentest:      [tools, {label:t('pentest','Pentest')}],
    provision:    [tools, {label:t('provisjonering','Provisjonering')}],
    billing:      [tools, {label:t('nav_billing','Lisenser og hosting')}],
    ai:           [tools, {label:t('sybrt','Sybrt')}],
    logs:         [{label:t('nav_admin','Administrasjon'),admin:'system'}, {label:t('bc_log','Log')}],
    'customer-detail': [{label:t('nav_customers'),view:'customers'}, {label:t('bc_customer_detail','Customer detail')}],
  };
  var crumbs = map[name] || [{label:name}];
  if (crumbs.length <= 1) { bc.style.display = 'none'; return; }
  bc.style.display = 'block';
  items.innerHTML = crumbs.map(function(c, i) {
    var sep = i > 0 ? ' <span style="margin:0 var(--space-2);color:var(--text-dim);opacity:0.5;">/</span> ' : '';
    if (i < crumbs.length - 1 && c.admin) {
      return sep + '<a href="#" class="hover-link crumb-link" data-click-handler="openAdmin" data-pane="' + esc(c.admin) + '">' + esc(c.label) + '</a>';
    } else if (i < crumbs.length - 1 && c.view) {
      return sep + '<a href="#" class="hover-link" data-click-handler="showView" data-view="' + esc(c.view) + '" style="color:var(--text-muted);text-decoration:none;transition:color 0.15s;">' + esc(c.label) + '</a>';
    } else if (i < crumbs.length - 1) {
      return sep + '<span style="color:var(--text-muted);">' + esc(c.label) + '</span>';
    }
    return sep + '<span style="color:var(--text);font-weight:500;">' + esc(c.label) + '</span>';
  }).join('');
}

// ── View timer cleanup ────────────────────────────────────────────────────────
// Central registry of view-specific intervals to clear on view switch.
// Global timers (VPN badge, session timeout) are excluded.
var _viewTimers = [];
function _registerViewTimer(id) { if (id) _viewTimers.push(id); return id; }
function _cleanupViewTimers() {
  _viewTimers.forEach(function(id) { clearInterval(id); });
  _viewTimers = [];
  // And the named timers the views own.
  stopDashAutoRefresh();
  stopAuditProgressPolling();
  stopLogAutoRefresh();
  stopDashRefreshInterval();
  stopAlsoScans();
}

export function showView(name) {
  // Integrasjoner was a page of its own; it is a pane of Administrasjon now.
  if (name === 'integrations') { openAdmin('integrations'); return; }
  // TLS-monitor is a tab of Nettverk.
  if (name === 'tls') { showNetworkTab('net-tls'); return; }
  // M365-status, Filer, Audit, Historikk, the policy pages and Vurderinger
  // are tabs of the customer page now: this tab's current customer's.
  if (CUSTOMER_TAB_ALIASES[name]) { openCurrentCustomerTab(CUSTOMER_TAB_ALIASES[name][0], CUSTOMER_TAB_ALIASES[name][1]); return; }
  // Leaving Administrasjon with unsaved edits asks first.
  if (currentView === 'admin' && name !== 'admin' && !adminMayLeave()) return;
  _cleanupViewTimers();
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  var viewEl = document.getElementById('view-' + name);
  if (viewEl) { viewEl.classList.add('active'); viewEl.style.animation = 'view-fade-in 0.25s ease-out'; }

  // Light the top-bar item the view belongs to.
  document.querySelectorAll('.nav-btn').forEach(function(b) {
    b.classList.remove('active');
    b.removeAttribute('aria-current');
  });
  var navBtn = document.getElementById('nav-' + (_NAV_GROUP[name] || ''));
  if (navBtn) { navBtn.classList.add('active'); navBtn.setAttribute('aria-current', 'page'); }
  closeToolsMenu();
  _syncBottomNav(name);

  currentView = name;
  _updateBreadcrumb(name);

  // Show skeleton placeholders immediately before data loads
  if (name === 'overview') {
    if (_bulkAuditEventSource) {
    } else {
      document.getElementById('overview-content').innerHTML = skeletonHTML('dashboard');
      loadOverview();
    }
  } else if (name === 'customers') {
    document.getElementById('customers-content').innerHTML = skeletonHTML('customers');
    loadCustomers();
  } else if (name === 'network') {
    loadNetworkDevices();
  } else if (name === 'logs') {
    loadLogs();
  } else if (name === 'setup') {
    _renderSetupIdle();
  }
  document.body.dataset.view = name;
  // The customer page records its own address once it knows which customer.
  if (name !== 'customer-detail') syncRoute(name);
  viewShown(name);
}

// ── Address bar ─────────────────────────────────────────────────────────────
// The view, and the customer it is about, live in the URL: Back, reload and a
// shared link land where they should. #/customer/<id> is a customer's page and
// #/<view> the rest. Applying a route sets a flag so the showView it causes
// does not push the same address again.
var _routeApplying = false;

export function syncRoute(name, customerId) {
  if (_routeApplying || !name) return;
  var target = '#/' + name;
  if (name === 'customer-detail' && customerId) target = _custHash();
  else if (name === 'admin') target = '#/admin/' + _adminPane;
  if (location.hash !== target) history.pushState(null, '', target);
}

async function applyRoute() {
  var customer = /^#\/customer\/([^/]+)(?:\/([a-z]+)(?:\/([a-z]+))?)?$/.exec(location.hash);
  var admin = /^#\/admin(?:\/([a-z-]+))?$/.exec(location.hash);
  var view = /^#\/([a-z0-9-]+)$/.exec(location.hash);
  _routeApplying = true;
  try {
    if (customer) {
      await openCustomerPage(decodeURIComponent(customer[1]), customer[2], customer[3]);
    } else if (view && CUSTOMER_TAB_ALIASES[view[1]]) {
      // #/audit, #/history and the rest were pages about the active customer;
      // they are this tab's current customer's page's tabs now.
      var alias = CUSTOMER_TAB_ALIASES[view[1]];
      await openCurrentCustomerTab(alias[0], alias[1]);
      history.replaceState(null, '', currentView === 'customer-detail' ? _custHash() : '#/' + currentView);
    } else if (admin || (view && view[1] === 'integrations')) {
      // #/integrations was a page of its own; it is a pane of Administrasjon now.
      var pane = admin ? admin[1] : 'integrations';
      if (canOpenView('admin')) {
        openAdmin(pane);
        history.replaceState(null, '', '#/admin/' + _adminPane);
      } else {
        showView('overview');
        history.replaceState(null, '', '#/overview');
      }
    } else if (view && view[1] === 'tls') {
      // TLS-monitor was a page of its own; it is a tab of Nettverk now.
      showNetworkTab('net-tls');
    } else if (view && document.getElementById('view-' + view[1])
        && (!_allowedViews.length || _allowedViews.indexOf(view[1]) !== -1)) {
      showView(view[1]);
    } else {
      showView('overview');
    }
  } finally {
    _routeApplying = false;
  }
}

window.addEventListener('popstate', function() { if (_currentUser) applyRoute(); });

// Opens Nettverk on one of its tabs: TLS-monitor is reached this way.
export function showNetworkTab(tabId) {
  if (currentView !== 'network') showView('network');
  var btn = document.querySelector('.net-sub-btn[data-tab="' + tabId + '"]');
  if (btn) switchNetSub(btn, tabId);
}

export function switchNetSub(btn, tabId) {
  document.querySelectorAll('.net-sub-content').forEach(function(c) { c.style.display = 'none'; });
  document.querySelectorAll('.net-sub-btn').forEach(function(b) { b.classList.remove('active'); });
  document.getElementById(tabId).style.display = 'block';
  btn.classList.add('active');
  if (tabId === 'net-audit') {
    // The audit tab works on the same customer as Enheter.
    renderToolCustomerPickers();
    toolCustomerId().then(function(id) { setNetCustomerId(id); });
  }

  if (tabId === 'net-fortigates') dashLoadFortiGates();
  if (tabId === 'net-unifi') dashLoadUnifiAll();
  if (tabId === 'net-tls') tlsLoadView();
}
