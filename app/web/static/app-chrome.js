// ═══════════════════════════════════════════════════════════════════
// CHROME — theme, notifications, shortcuts, onboarding & bootstrap
// ═══════════════════════════════════════════════════════════════════

// ── Theme toggle ────────────────────────────────────────────────────────────────
// ── Notification bell ─────────────────────────────────────────────────────────
var _notifOpen = false;
var _notifLastSeen = localStorage.getItem('sybr_notif_seen') || '';

function toggleNotifications() {
  _notifOpen = !_notifOpen;
  var dd = document.getElementById('notif-dropdown');
  dd.style.display = _notifOpen ? 'block' : 'none';
  if (_notifOpen) loadNotifications();
}

async function loadNotifications() {
  try {
    var d = await apiFetch('/api/activity-log?limit=20');
    var entries = d.entries || [];
    var list = document.getElementById('notif-list');
    if (entries.length === 0) {
      list.innerHTML = '<div style="padding:var(--space-8) var(--space-4);text-align:center;color:var(--text-dim);font-size:var(--font-sm);">' + t('msg_no_notifications','Ingen varsler') + '</div>';
      return;
    }
    // Filter out low-value noise
    var _hideActions = new Set(['settings_changed','customer_switched']);
    entries = entries.filter(function(e) { return !_hideActions.has(e.action); });

    var actionIcons = {
      audit_started: '\u25B6', audit_completed: '\u2713', report_generated: '',
      customer_added: '', itglue_uploaded: '',
      email_sent: '', backup_created: '',
      backup_restored: '', history_deleted: '',
      remediation_updated: '',
    };
    var actionLabels = {
      audit_started: t('notif_audit_started','Audit started'),
      audit_completed: t('notif_audit_completed','Audit completed'),
      report_generated: t('notif_report_generated','Report generated'),
      customer_added: t('notif_customer_added','Customer added'),
      email_sent: t('notif_email_sent','Email sent'),
      backup_created: t('notif_backup_created','Backup created'),
      backup_restored: t('notif_backup_restored','Backup restored'),
      history_deleted: t('notif_history_deleted','History deleted'),
      itglue_uploaded: t('notif_itglue_uploaded','Uploaded to IT Glue'),
      remediation_updated: t('notif_remediation_updated','Remediation updated'),
    };
    var actionColors = {
      audit_completed: 'var(--green)', report_generated: 'var(--blue)',
      backup_created: 'var(--green)', email_sent: 'var(--blue)',
    };
    if (entries.length === 0) {
      list.innerHTML = '<div style="padding:var(--space-8) var(--space-4);text-align:center;color:var(--text-dim);font-size:var(--font-sm);">' + t('msg_no_notifications','No notifications') + '</div>';
      return;
    }
    list.innerHTML = entries.map(function(e) {
      var icon = actionIcons[e.action] || '';
      var color = actionColors[e.action] || 'var(--text-muted)';
      var label = actionLabels[e.action] || e.action.replace(/_/g,' ').replace(/^\w/,function(c){return c.toUpperCase()});
      var timeStr = e.timestamp ? timeAgo(e.timestamp) : '';
      var isNew = _notifLastSeen && e.timestamp > _notifLastSeen;
      return '<div style="padding:var(--space-3) var(--space-4);border-bottom:1px solid var(--border);display:flex;gap:var(--space-3);align-items:flex-start;'+(isNew?'background:rgba(77,159,181,0.06);':'')+'" class="hover-tint-strong">'+
        '<span style="font-size:16px;flex-shrink:0;margin-top:2px;color:'+color+';">'+icon+'</span>'+
        '<div style="flex:1;min-width:0;">'+
          '<div style="font-size:var(--font-sm);color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+esc(label)+
            (e.customer ? ' · <span style="color:var(--blue);">'+esc(e.customer)+'</span>' : '')+
          '</div>'+
          (e.detail ? '<div style="font-size:var(--font-xs);color:var(--text-dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+esc(e.detail)+'</div>' : '')+
          '<div style="font-size:var(--font-xs);color:var(--text-dim);margin-top:2px;">'+esc(timeStr)+(e.user ? ' · '+esc(e.user) : '')+'</div>'+
        '</div></div>';
    }).join('');
  } catch(e) { /* non-critical */ }
}

function markAllNotificationsRead() {
  _notifLastSeen = new Date().toISOString();
  localStorage.setItem('sybr_notif_seen', _notifLastSeen);
  document.getElementById('notif-badge').style.display = 'none';
  loadNotifications();
}

async function _checkVpnHeaderBadge() {
  // Signed-out pages and accounts without the VPN feature have nothing to show
  // here, and the server refuses them.
  if (!_currentUser || !hasFeature('vpn')) return;
  try {
    var d = await apiFetch('/api/vpn/status');
    // Single status chip: prefix "VPN · " ahead of the live dot when a tunnel
    // is up (the old standalone #vpn-header-badge was merged into #conn-status).
    var prefix = document.getElementById('vpn-chip-prefix');
    if (!prefix) return;
    if (d && d.state === 'connected') {
      prefix.style.display = 'inline';
      var stats = d.stats || {};
      var tip = 'VPN ' + t('vpn_connected','Connected');
      if (d.interface) tip += ' (' + d.interface + ')';
      if (stats.local_ip) tip += '\nIP: ' + stats.local_ip;
      if (stats.tx_bytes || stats.rx_bytes) tip += '\nTX: ' + _formatBytes(stats.tx_bytes||0) + ' / RX: ' + _formatBytes(stats.rx_bytes||0);
      tip += '\n' + t('tip_click_to_manage','Click to manage');
      prefix.title = tip;
    } else {
      prefix.style.display = 'none';
    }
  } catch(e) { /* VPN badge poll — retries every 30s */ }
}

// Re-check VPN status periodically
setInterval(_checkVpnHeaderBadge, 30000);

async function _checkNotifBadge() {
  try {
    var d = await apiFetch('/api/activity-log?limit=5');
    var entries = d.entries || [];
    var newCount = 0;
    if (_notifLastSeen) {
      entries.forEach(function(e) { if (e.timestamp > _notifLastSeen) newCount++; });
    } else {
      newCount = entries.length;
    }
    var badge = document.getElementById('notif-badge');
    var bnavBadge = document.getElementById('bnav-alerts-badge');
    if (newCount > 0) {
      var _nb = newCount > 9 ? '9+' : String(newCount);
      badge.textContent = _nb; badge.style.display = 'block';
      if (bnavBadge) { bnavBadge.textContent = _nb; bnavBadge.style.display = 'block'; }
    } else {
      badge.style.display = 'none';
      if (bnavBadge) bnavBadge.style.display = 'none';
    }
  } catch(e) { /* notification poll — retries periodically */ }
}

// Close notification dropdown when clicking outside.
// Match the toggles by data attribute, not by aria-label: translatePage()
// rewrites aria-label from data-i18n-aria-label, so on any locale but
// Norwegian the selector missed the bell and the same click that opened the
// dropdown closed it again — the bell looked dead. The attribute also covers
// the bottom-nav toggle, which the old selector never matched in any locale.
document.addEventListener('click', function(e) {
  if (_notifOpen && !e.target.closest('#notif-dropdown') && !e.target.closest('[data-notif-toggle]')) {
    _notifOpen = false;
    document.getElementById('notif-dropdown').style.display = 'none';
  }
});

function toggleTheme() {
  const root = document.documentElement;
  const current = root.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  localStorage.setItem('sybr-theme', next);
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const btn = document.getElementById('theme-toggle-btn');
  // The header logo is two <img> elements, header-logo-dark and
  // header-logo-light, swapped by .logo-dark/.logo-light under
  // [data-theme="light"] in app.css. Setting a src here is left over from when
  // it was one element: the lookup found nothing, the guard swallowed it, and
  // the logo simply never changed with the theme. CSS owns it; this does not.
  const footerLogo = document.getElementById('footer-logo');

  if (theme === 'light') {
    // Half-filled circles, the same glyph family as the visible theme toggle
    // in the avatar menu. This button was the last emoji left in the header.
    btn.textContent = '◑';
    btn.title = t('tip_switch_dark_theme', 'Bytt til mørkt tema');
    if (footerLogo) { footerLogo.src = '/branding/300 x 86.png'; footerLogo.style.opacity = '0.6'; }
  } else {
    btn.textContent = '◐';
    btn.title = t('tip_switch_light_theme', 'Bytt til lyst tema');
    if (footerLogo) { footerLogo.src = '/branding/300 x 86.png'; footerLogo.style.opacity = '0.5'; }
  }
}

// Handlers for the activity log and changelog controls (see registerUiHandlers
// in app.js).
registerUiHandlers({
  loadMoreActivity: function() { loadActivityLog(true); },
  showChangelogTab: function(el) { _changelogTab = el.dataset.tab; _renderChangelogTab(); },
});

// ── Activity log ─────────────────────────────────────────────────────────────
var _activityLogOffset = 0;
var _activityLogExpanded = true;

var _activityIcons = {
  audit_started:     '\u25B6',
  audit_completed:   '\u2713',
  report_generated:  '\uD83D\uDCC4',
  customer_added:    '\u2795',
  customer_switched: '\uD83D\uDD04',
  itglue_uploaded:   '\u2601',
  settings_changed:  '\u2699',
  email_sent:        '\u2709',
};

function _activityLabel(key) {
  return t('activity_' + key, key.replace(/_/g, ' '));
}

function toggleActivityLog() {
  var body = document.getElementById('activity-log-body');
  var toggle = document.getElementById('activity-log-toggle');
  if (!body) return;
  _activityLogExpanded = !_activityLogExpanded;
  body.style.display = _activityLogExpanded ? '' : 'none';
  toggle.innerHTML = _activityLogExpanded ? '&#9660;' : '&#9654;';
}

async function loadActivityLog(append) {
  var list = document.getElementById('activity-log-list');
  var more = document.getElementById('activity-log-more');
  if (!list) return;

  if (!append) {
    _activityLogOffset = 0;
    list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:8px 0;">' + t('msg_loading') + '</div>';
  }

  try {
    var d = await apiFetch('/api/activity-log?limit=10&offset=' + _activityLogOffset);
    var entries = d.entries || [];

    if (!append) list.innerHTML = '';

    if (entries.length === 0 && _activityLogOffset === 0) {
      list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:8px 0;">' + t('msg_no_activity_yet') + '</div>';
      more.innerHTML = '';
      return;
    }

    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      var icon = _activityIcons[e.action] || '\u2022';
      var label = _activityLabel(e.action);
      var ts = formatActivityTime(e.timestamp);
      var custHtml = e.customer ? '<span style="color:var(--blue);margin-left:6px;">' + esc(e.customer) + '</span>' : '';
      var detailHtml = e.detail ? '<span style="color:var(--text-dim);margin-left:6px;font-size:11px;">' + esc(e.detail) + '</span>' : '';

      var row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:13px;';
      row.innerHTML =
        '<span style="width:20px;text-align:center;flex-shrink:0;">' + icon + '</span>' +
        '<span style="font-weight:500;">' + esc(label) + '</span>' + custHtml + detailHtml +
        '<span style="margin-left:auto;color:var(--text-dim);font-size:11px;white-space:nowrap;">' + esc(ts) + '</span>';
      list.appendChild(row);
    }

    _activityLogOffset += entries.length;

    if (entries.length >= 10) {
      more.innerHTML = '<button class="btn btn-ghost" style="font-size:12px;padding:4px 12px;" data-click-handler="loadMoreActivity">' + t('btn_show_more') + '</button>';
    } else {
      more.innerHTML = '';
    }
  } catch (ex) {
    if (!append) list.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:8px 0;">' + t('err_could_not_load_activity') + '</div>';
  }
}

function formatActivityTime(isoStr) {
  try {
    var d = new Date(isoStr);
    var now = new Date();
    var diffMs = now - d;
    var diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return t('msg_just_now');
    if (diffMin < 60) return t('msg_min_ago').replace('{count}', diffMin);
    var diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return t('msg_hours_ago').replace('{count}', diffH);
    var diffD = Math.floor(diffH / 24);
    if (diffD < 7) return t('msg_days_ago').replace('{count}', diffD);
    return d.toLocaleDateString('nb-NO', { day: '2-digit', month: '2-digit', year: 'numeric' }) + ' ' + d.toLocaleTimeString('nb-NO', { hour: '2-digit', minute: '2-digit' });
  } catch(ex) {
    return isoStr;
  }
}

// ── Mobile nav toggle ────────────────────────────────────────────────────────
// showView() already closes the mobile nav after a nav-item click. This file
// owns the open/close state and resize-driven auto-close.

// Must match the @media (max-width) breakpoint in app.css that collapses the
// top nav into a hamburger. Keep these in sync.
var _NAV_MOBILE_BREAKPOINT = 1100;

function toggleMobileNav() {
  var nav = document.getElementById('main-nav');
  if (nav) nav.classList.toggle('open');
}

// ── Mobile bottom nav + «Mer» sheet (frame 4a) ──────────────────────────────
function openMoreSheet() {
  var b = document.getElementById('more-backdrop');
  if (b) { b.classList.add('open'); document.addEventListener('keydown', _closeMoreSheetEsc); }
  _syncBottomNav('more');
}
function closeMoreSheet() {
  var b = document.getElementById('more-backdrop');
  if (b) b.classList.remove('open');
  document.removeEventListener('keydown', _closeMoreSheetEsc);
  var av = document.querySelector('.view.active');
  _syncBottomNav(av ? av.id.replace('view-', '') : 'overview');
}
function _closeMoreSheetEsc(e) { if (e.key === 'Escape') closeMoreSheet(); }
function _syncBottomNav(name) {
  // Map every view onto one of the five bottom-tab groups.
  var map = {
    overview: 'dashboard',
    customers: 'customers', home: 'customers', audit: 'customers', history: 'customers',
    files: 'customers', setup: 'customers', 'customer-detail': 'customers',
    network: 'network', vpn: 'network', tls: 'network', tailscale: 'network', provision: 'network',
    more: 'more',
  };
  var active = map[name] || '';
  document.querySelectorAll('.bnav-item').forEach(function(el) {
    el.classList.toggle('active', el.getAttribute('data-bnav') === active);
  });
}

window.addEventListener('resize', function() {
  if (window.innerWidth > _NAV_MOBILE_BREAKPOINT) {
    var nav = document.getElementById('main-nav');
    if (nav) nav.classList.remove('open');
  }
});

// Belt-and-suspenders: close mobile nav on any nav-btn click inside #main-nav,
// even if the click handler doesn't route through showView() (e.g. Integrasjoner
// dropdown items, future additions). Uses event delegation so we don't need to
// wire per-button handlers.
document.addEventListener('click', function(e) {
  var target = e.target.closest('#main-nav .nav-btn, #main-nav .nav-dropdown-menu-inner button');
  if (!target) return;
  // Only act below the breakpoint — desktop doesn't need this.
  if (window.innerWidth > _NAV_MOBILE_BREAKPOINT) return;
  var nav = document.getElementById('main-nav');
  if (nav) nav.classList.remove('open');
});

// ── Changelog modal ──────────────────────────────────────────────────────────
function parseChangelogMd(md) {
  var html = '', inList = false, inCode = false, lines = md.split('\n');
  // Escaped first, as the server's renderer does, so the fallback cannot
  // turn the changelog into markup either.
  function fmt(s) { return esc(s).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>'); }
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    if (line.match(/^```/)) { if (inList) { html += '</ul>'; inList = false; } if (inCode) { html += '</pre>'; inCode = false; } else { html += '<pre style="background:var(--bg);padding:8px;border-radius:4px;font-size:12px;overflow-x:auto;">'; inCode = true; } continue; }
    if (inCode) { html += esc(line) + '\n'; continue; }
    if (line.match(/^## /)) { if (inList) { html += '</ul>'; inList = false; } html += '<h2>' + fmt(line.replace(/^## /, '')) + '</h2>'; }
    else if (line.match(/^### /)) { if (inList) { html += '</ul>'; inList = false; } html += '<h3>' + fmt(line.replace(/^### /, '')) + '</h3>'; }
    else if (line.match(/^\s*- /)) { if (!inList) { html += '<ul>'; inList = true; } html += '<li>' + fmt(line.replace(/^\s*- /, '')) + '</li>'; }
    else if (line.match(/^\*\*/)) { if (inList) { html += '</ul>'; inList = false; } html += '<p>' + fmt(line) + '</p>'; }
    else if (line.trim() === '') { if (inList) { html += '</ul>'; inList = false; } }
    else { if (inList) { html += '</ul>'; inList = false; } html += '<p style="margin:4px 0;color:var(--text-muted);">' + fmt(line) + '</p>'; }
  }
  if (inList) html += '</ul>';
  if (inCode) html += '</pre>';
  return html;
}
var _changelogCache = null;
var _changelogFull = '';
var _changelogLatest = '';
var _changelogTab = 'latest';

function openChangelogModal() {
  document.getElementById('changelog-modal').classList.add('open');
  if (_changelogCache) { _renderChangelogTab(); return; }
  apiFetch('/api/changelog').then(function(data) {
    // CHANGELOG.md is not package data, so a wheel or container install does
    // not carry it. An empty panel read as "no releases yet".
    if (data && data.available === false) {
      document.getElementById('changelog-content').innerHTML =
        '<p style="color:var(--text-dim);">'
        + esc(t('changelog_not_in_this_build',
                'Endringsloggen følger ikke med denne installasjonen.'))
        + '</p>';
      return;
    }
    // Use server-rendered HTML if available, fall back to JS parser
    _changelogFull = (/* safe-html: the server escapes the changelog before it renders it (_md_to_html) */ data.html) || parseChangelogMd(data.content || '');
    _changelogLatest = (/* safe-html: rendered by the same escaping renderer as data.html */ data.latest_html) || _changelogFull;
    _changelogCache = true;
    _renderChangelogTab();
  }).catch(function() { document.getElementById('changelog-content').innerHTML = '<p style="color:var(--text-dim);">' + t('err_could_not_load_changelog') + '</p>'; });
}

function _renderChangelogTab() {
  var content = _changelogTab === 'latest' ? _changelogLatest : _changelogFull;
  var tabs = '<div style="display:flex;gap:8px;margin-bottom:16px;">'
    + '<button class="btn btn-sm ' + (_changelogTab === 'latest' ? 'btn-primary' : 'btn-ghost') + '" data-click-handler="showChangelogTab" data-tab="latest">' + t('siste_endringer') + '</button>'
    + '<button class="btn btn-sm ' + (_changelogTab === 'all' ? 'btn-primary' : 'btn-ghost') + '" data-click-handler="showChangelogTab" data-tab="all">' + t('alle_versjoner') + '</button>'
    + '</div>';
  document.getElementById('changelog-content').innerHTML = tabs + content;
}

function closeChangelogModal() { document.getElementById('changelog-modal').classList.remove('open'); }
function filterChangelog() {
  var q = (document.getElementById('changelog-search').value || '').toLowerCase();
  if (!q) { _renderChangelogTab(); return; }
  // Search the full changelog, not only the tab that is open. The full text
  // was looked up here and then never rendered, so a search on the default
  // "latest" tab only ever searched the latest release.
  var box = document.getElementById('changelog-content');
  box.innerHTML = _changelogFull;
  box.querySelectorAll('h2,h3,p,li,strong,ul').forEach(function(el) {
    el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

// ── Keyboard shortcuts ──────────────────────────────────────────────────────
function openShortcutsModal() {
  document.getElementById('shortcuts-modal').classList.add('open');
}
function closeShortcutsModal() {
  document.getElementById('shortcuts-modal').classList.remove('open');
}
function closeAllModals() {
  document.querySelectorAll('.modal-backdrop.open').forEach(function(m) {
    m.classList.remove('open');
  });
}

// Close only the topmost open modal. Used by ESC so a nested confirmation
// dialog doesn't wipe out an underlying settings modal with unsaved edits.
function closeTopModal() {
  var open = document.querySelectorAll('.modal-backdrop.open');
  if (open.length === 0) return false;
  open[open.length - 1].classList.remove('open');
  return true;
}

// ── Focus trap for modals ────────────────────────────────────────────────────
// When a modal opens we: remember who had focus, move focus into the modal,
// and constrain Tab to the modal's focusable elements. On close we restore
// focus. Watches class changes on every .modal-backdrop via MutationObserver
// so existing modal open/close call-sites keep working unchanged.

var _focusReturnStack = [];   // stack of elements to restore focus to, per modal
var _activeTrappedModal = null;

function _focusableElementsIn(root) {
  if (!root) return [];
  var sel = 'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';
  return Array.from(root.querySelectorAll(sel))
    .filter(function(el) {
      // Filter out elements that are visually hidden
      return el.offsetParent !== null || el === document.activeElement;
    });
}

function _onModalOpened(modal) {
  _focusReturnStack.push(document.activeElement);
  _activeTrappedModal = modal;
  // Move focus into the modal's first focusable element. Run on next tick
  // so rendered children are present.
  setTimeout(function() {
    var focusables = _focusableElementsIn(modal);
    var target = focusables.find(function(el) { return el.dataset.autofocus !== undefined; })
              || focusables[0]
              || modal;
    if (target && target.focus) {
      if (!target.hasAttribute('tabindex') && target === modal) {
        modal.setAttribute('tabindex', '-1');
      }
      try { target.focus({ preventScroll: true }); } catch (_) { target.focus(); }
    }
  }, 0);
}

function _onModalClosed(/*modal*/) {
  // Determine the topmost remaining open modal (if any) and refocus its
  // previously-active element, otherwise restore the pre-modal focus.
  var prev = _focusReturnStack.pop();
  var stillOpen = document.querySelectorAll('.modal-backdrop.open');
  _activeTrappedModal = stillOpen.length ? stillOpen[stillOpen.length - 1] : null;
  if (prev && typeof prev.focus === 'function' && document.contains(prev)) {
    try { prev.focus({ preventScroll: true }); } catch (_) { prev.focus(); }
  }
}

function _handleModalTab(e) {
  if (e.key !== 'Tab' || !_activeTrappedModal) return;
  var focusables = _focusableElementsIn(_activeTrappedModal);
  if (focusables.length === 0) {
    e.preventDefault();
    return;
  }
  var first = focusables[0];
  var last = focusables[focusables.length - 1];
  var active = document.activeElement;
  if (e.shiftKey) {
    if (active === first || !_activeTrappedModal.contains(active)) {
      e.preventDefault();
      last.focus();
    }
  } else {
    if (active === last) {
      e.preventDefault();
      first.focus();
    }
  }
}
document.addEventListener('keydown', _handleModalTab, true);

// Watch every .modal-backdrop's class attribute so we detect open/close
// without changing callers. Observer is lazy-initialized on first run.
(function initModalFocusObserver() {
  function watch(el) {
    var wasOpen = el.classList.contains('open');
    new MutationObserver(function(muts) {
      for (var i = 0; i < muts.length; i++) {
        if (muts[i].attributeName !== 'class') continue;
        var nowOpen = el.classList.contains('open');
        if (nowOpen === wasOpen) continue;
        if (nowOpen) _onModalOpened(el);
        else _onModalClosed(el);
        wasOpen = nowOpen;
      }
    }).observe(el, { attributes: true, attributeFilter: ['class'] });
  }
  function scanAndWatch() {
    document.querySelectorAll('.modal-backdrop:not([data-focus-watched])').forEach(function(el) {
      el.dataset.focusWatched = '1';
      watch(el);
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scanAndWatch);
  } else {
    scanAndWatch();
  }
  // Also watch for modals inserted dynamically (rare but cheap to cover)
  new MutationObserver(scanAndWatch).observe(document.body, { childList: true, subtree: true });
})();

document.addEventListener('keydown', function(e) {
  var tag = (e.target.tagName || '').toLowerCase();
  var isInput = (tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable);
  var mod = e.ctrlKey || e.metaKey;

  // Escape — close only the topmost modal (so an outer settings modal's
  // unsaved edits survive closing a nested confirmation), then reset filters
  // if no modal was actually open.
  if (e.key === 'Escape') {
    if (closeTopModal()) return;
    if (_gradeFilter) { _gradeFilter = ''; filterOverview(); }
    return;
  }

  // Skip remaining shortcuts when focus is in an input
  if (isInput) return;

  // Arrow keys — navigate dashboard table rows
  if (currentView === 'overview' && (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter')) {
    var rows = document.querySelectorAll('#overview-table-content tbody tr');
    if (rows.length > 0) {
      var focused = document.querySelector('#overview-table-content tbody tr.kb-focused');
      var idx = focused ? Array.from(rows).indexOf(focused) : -1;
      if (e.key === 'ArrowDown') { idx = Math.min(idx + 1, rows.length - 1); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { idx = Math.max(idx - 1, 0); e.preventDefault(); }
      else if (e.key === 'Enter' && focused) { focused.click(); return; }
      rows.forEach(function(r) { r.classList.remove('kb-focused'); r.style.outline = ''; });
      if (rows[idx]) {
        rows[idx].classList.add('kb-focused');
        rows[idx].style.outline = '2px solid var(--blue)';
        rows[idx].style.outlineOffset = '-2px';
        rows[idx].scrollIntoView({ block: 'nearest' });
      }
      return;
    }
  }

  // ? — show shortcuts help
  if (e.key === '?' || (e.shiftKey && e.key === '?')) {
    e.preventDefault();
    openShortcutsModal();
    return;
  }

  // Ctrl/Cmd + number — navigation
  if (mod && !e.shiftKey) {
    var views = { '1': 'overview', '2': 'home', '3': 'customers', '4': 'files', '5': 'history' };
    if (views[e.key]) {
      e.preventDefault();
      showView(views[e.key]);
      return;
    }
    // Ctrl+, — open settings
    if (e.key === ',') {
      e.preventDefault();
      openSettings();
      return;
    }
  }

  // Ctrl/Cmd + K — open command palette (works even in inputs)
  if (mod && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    toggleCommandPalette();
    return;
  }

  // Ctrl/Cmd + Shift + T — toggle theme
  if (mod && e.shiftKey && (e.key === 'T' || e.key === 't')) {
    e.preventDefault();
    toggleTheme();
    return;
  }

  // Ctrl/Cmd + Shift + A — start audit
  if (mod && e.shiftKey && (e.key === 'A' || e.key === 'a')) {
    e.preventDefault();
    if (!auditRunning) startAudit();
    return;
  }
});

// ── Init ───────────────────────────────────────────────────────────────────────
applyTheme(localStorage.getItem('sybr-theme') || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));
// ── AI quick-prompt cards ────────────────────────────────────────────────────
// Previously built from an inline <script> in index.html. Moved out so we can
// drop 'unsafe-inline' from the CSP script-src directive. Uses addEventListener,
// since the CSP runs no inline event-handler attributes either.
function renderAiQuickPrompts() {
  var el = document.getElementById('ai-quick-prompts');
  if (!el) return;
  var prompts = [
    {icon:'\u{1F6E1}', label:'ai_prompt_fortigate',     labelFb:'Show FortiGate status',   prompt:'ai_prompt_fortigate_text',     promptFb:'Show status for all FortiGate firewalls'},
    {icon:'\u{1F5A5}', label:'ai_prompt_ssh',           labelFb:'SSH health check',        prompt:'ai_prompt_ssh_text',           promptFb:'List all SSH hosts and check health status'},
    {icon:'\u{1F512}', label:'ai_prompt_vpn',           labelFb:'VPN status',              prompt:'ai_prompt_vpn_text',           promptFb:'What is the current VPN status?'},
    {icon:'\u{1F4CB}', label:'ai_prompt_cis',           labelFb:'CIS compliance',          prompt:'ai_prompt_cis_text',           promptFb:'Run CIS compliance check on active customer'},
    {icon:'\u{1F4E1}', label:'ai_prompt_unifi',         labelFb:'UniFi sites',             prompt:'ai_prompt_unifi_text',         promptFb:'List all UniFi sites with device status'},
    {icon:'\u{1F527}', label:'ai_prompt_troubleshoot',  labelFb:'Troubleshoot',            prompt:'ai_prompt_troubleshoot_text',  promptFb:'Help me troubleshoot network issues for this customer'},
  ];
  el.innerHTML = '';
  prompts.forEach(function(p) {
    var card = document.createElement('div');
    card.style.cssText = 'padding:10px;border:1px solid var(--border);border-radius:6px;cursor:pointer;font-size:12px;transition:background 0.1s;';
    card.textContent = p.icon + ' ' + t(p.label, p.labelFb);
    card.addEventListener('click', function() {
      if (typeof aiQuickPrompt === 'function') {
        aiQuickPrompt(t(p.prompt, p.promptFb));
      }
    });
    card.addEventListener('mouseover', function() { card.style.background = 'var(--bg-card)'; });
    card.addEventListener('mouseout',  function() { card.style.background = ''; });
    el.appendChild(card);
  });
}

loadI18n().then(() => { renderAiQuickPrompts(); checkAuth(); });
// ── PWA install prompt ─────────────────────────────────────────────────────
// Two install paths:
//   Chromium / Edge / Android Chrome: `beforeinstallprompt` fires when the
//     engagement heuristic is satisfied — we stash the event and trigger
//     its .prompt() on button click.
//   Safari iOS: no programmatic install API. Show a modal with step-by-
//     step "Share → Add to Home Screen" guidance.
//
// Visibility rules:
//   - Hide entirely when already installed (display-mode: standalone OR
//     iOS navigator.standalone).
//   - On mobile, show the button by default so iOS users have an entry
//     point even without the beforeinstallprompt event.
//   - On desktop, only reveal once beforeinstallprompt has fired (the
//     browser knows the app is installable); otherwise hide to avoid a
//     button that does nothing useful.

var _deferredPwaInstall = null;

function _isStandalone() {
  if (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) return true;
  if (window.navigator && window.navigator.standalone) return true;  // iOS
  return false;
}
function _isMobile() {
  return window.matchMedia && window.matchMedia('(max-width: 1100px)').matches;
}
function _isIOS() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
}

function _refreshPwaInstallButton() {
  var btn = document.getElementById('pwa-install-btn');
  if (!btn) return;
  if (_isStandalone()) { btn.style.display = 'none'; return; }
  if (_deferredPwaInstall) { btn.style.display = 'inline-flex'; return; }
  // No stashed event. On mobile, still show so iOS users can see the hint.
  btn.style.display = _isMobile() ? 'inline-flex' : 'none';
}

window.addEventListener('beforeinstallprompt', function(e) {
  e.preventDefault();
  _deferredPwaInstall = e;
  _refreshPwaInstallButton();
});

window.addEventListener('appinstalled', function() {
  _deferredPwaInstall = null;
  var btn = document.getElementById('pwa-install-btn');
  if (btn) btn.style.display = 'none';
  if (typeof showToast === 'function') {
    showToast(t('msg_pwa_installed', 'Appen er installert'), 'success', 2500);
  }
});

// Initial decision on load + whenever viewport crosses the mobile breakpoint.
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _refreshPwaInstallButton);
} else {
  _refreshPwaInstallButton();
}
window.addEventListener('resize', _refreshPwaInstallButton);

async function promptPwaInstall() {
  if (_deferredPwaInstall) {
    _deferredPwaInstall.prompt();
    try {
      var choice = await _deferredPwaInstall.userChoice;
      if (choice && choice.outcome !== 'dismissed') {
        _deferredPwaInstall = null;
        _refreshPwaInstallButton();
      }
    } catch (_) {}
    return;
  }
  // No stashed event — show manual instructions. iOS gets a richer modal
  // with the actual share+add-to-home-screen icons so it's discoverable.
  _showPwaInstallHelp();
}

function _showPwaInstallHelp() {
  var existing = document.getElementById('pwa-help-modal');
  if (existing) { existing.style.display = 'flex'; return; }
  var ios = _isIOS();
  var bodyHtml = ios ? '' +
    '<ol style="font-size:14px;line-height:1.8;padding-left:20px;margin:12px 0;color:var(--text);">' +
    '  <li>' + esc(t('pwa_ios_step1', 'Trykk på')) + ' <strong style="color:var(--blue);">' + esc(t('pwa_ios_share', 'Del')) + '</strong> ' + esc(t('pwa_ios_step1_end', '(boksen med pil) i bunnen av nettleseren.')) + '</li>' +
    '  <li>' + esc(t('pwa_ios_step2', 'Bla ned og velg')) + ' <strong style="color:var(--blue);">' + esc(t('pwa_ios_add', 'Legg til på hjem-skjermen')) + '</strong>.</li>' +
    '  <li>' + esc(t('pwa_ios_step3', 'Bekreft navn og trykk')) + ' <strong style="color:var(--blue);">' + esc(t('pwa_ios_confirm', 'Legg til')) + '</strong>.</li>' +
    '</ol>' +
    '<div style="font-size:12px;color:var(--text-dim);margin-top:8px;">' + esc(t('pwa_ios_hint', 'Appen åpner i fullskjerm uten nettleser-kontroller etter installasjon.')) + '</div>'
    :
    '<p style="font-size:14px;color:var(--text);line-height:1.6;">' + esc(t('pwa_generic_help', 'Åpne nettleserens meny og velg «Installer app» eller «Legg til på startskjerm».')) + '</p>';

  var html = '' +
    '<div class="modal-backdrop open" id="pwa-help-modal" data-click-handler="hideOnBackdrop" style="display:flex;">' +
      '<div class="modal" style="max-width:380px;">' +
        '<div class="modal-title" style="display:flex;align-items:center;gap:8px;">' + esc(t('pwa_help_title', 'Installer Sybr HUB som app')) + '</div>' +
        bodyHtml +
        '<div class="modal-actions">' +
          '<button class="btn btn-primary" data-click-handler="hideElement" data-target="pwa-help-modal">' + esc(t('btn_ok', 'OK')) + '</button>' +
        '</div>' +
      '</div>' +
    '</div>';
  var tmp = document.createElement('div');
  tmp.innerHTML = html;
  document.body.appendChild(tmp.firstChild);
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js').then(function(reg) {
    // If a waiting SW is ready (new version installed on a previous visit),
    // offer the user a toast to activate it.
    if (reg.waiting) _notifySwUpdateAvailable(reg.waiting);
    reg.addEventListener('updatefound', function() {
      var installing = reg.installing;
      if (!installing) return;
      installing.addEventListener('statechange', function() {
        if (installing.state === 'installed' && navigator.serviceWorker.controller) {
          _notifySwUpdateAvailable(installing);
        }
      });
    });
  }).catch(function(){});
  // The new worker takes over only when someone accepts the update. The tab
  // that accepted reloads; any other open tab may hold a terminal or RDP
  // session, so it is offered the reload instead of having it done to it.
  var _swReloadGuard = false;
  navigator.serviceWorker.addEventListener('controllerchange', function() {
    if (_swReloadGuard) return;
    _swReloadGuard = true;
    if (_swUpdateAccepted) { location.reload(); return; }
    if (typeof showToastWithRetry === 'function') {
      showToastWithRetry(t('msg_pwa_update_available', 'Ny versjon tilgjengelig'), function() {
        location.reload();
      });
    }
  });
}

var _swUpdateAccepted = false;

function _notifySwUpdateAvailable(worker) {
  if (typeof showToastWithRetry === 'function') {
    showToastWithRetry(t('msg_pwa_update_available', 'Ny versjon tilgjengelig'), function() {
      _swUpdateAccepted = true;
      worker.postMessage({ type: 'SKIP_WAITING' });
    });
  }
}

// Desktop notifications are asked for when an audit starts (startAudit),
// a moment the operator can connect with the question, not on page load.
function requestAuditNotifications() {
  if ('Notification' in window && Notification.permission === 'default') {
    var asked = Notification.requestPermission();
    if (asked && asked.catch) asked.catch(function() {});
  }
}

// Scroll-to-top button
window.addEventListener('scroll', function() {
  var btn = document.getElementById('scroll-top-btn');
  if (!btn) return;
  if (window.scrollY > 300) { btn.style.display = 'block'; setTimeout(function(){ btn.style.opacity = '1'; btn.style.transform = 'translateY(0)'; }, 10); }
  else { btn.style.opacity = '0'; btn.style.transform = 'translateY(10px)'; setTimeout(function(){ if (window.scrollY <= 300) btn.style.display = 'none'; }, 250); }
});

// ── Session timeout warning ─────────────────────────────────────────────────
// Refresh shortly before the one-hour access cookie expires. The refresh
// cookie remains HttpOnly; a failed refresh is handled by the next API call.
setInterval(function() {
  if (_currentUser) fetch('/api/auth/refresh', {method:'POST'}).catch(function(){});
}, 50 * 60 * 1000);

// ── Onboarding guide ────────────────────────────────────────────────────────
// A four-step tour of the real path through the product, shown once per user
// after they have signed in. It used to run the moment this script loaded, so
// it sat on top of the login form, and finishing it only stuck if a "do not
// show again" box was ticked, so it came back on every reload. Finishing and
// dismissing (skip button or Escape) now both count as done, per account.
//
// The completion flag lives in this browser. The key without a user suffix is
// the one older versions wrote; it still counts so nobody who already closed
// the tour for good sees it again.
var _ONBOARDING_KEY = 'onboarding_done';
var _onboarding = null;  // {overlay, step} while the tour is open

function _onboardingUserKey() {
  var u = window._currentUser;
  return u && (u.id || u.username) ? _ONBOARDING_KEY + ':' + (u.id || u.username) : null;
}

function _onboardingIsDone() {
  var key = _onboardingUserKey();
  if (!key) return true;  // nobody signed in: nothing to show
  try {
    return !!(localStorage.getItem(_ONBOARDING_KEY) || localStorage.getItem(key));
  } catch (e) {
    return true;  // storage blocked: better silent than shown on every load
  }
}

function _onboardingSteps() {
  return [
    {title: t('onboarding_add_customer_title'), text: t('onboarding_add_customer_text')},
    {title: t('onboarding_m365_title'), text: t('onboarding_m365_text')},
    {title: t('onboarding_run_audit_title'), text: t('onboarding_run_audit_text')},
    {title: t('onboarding_findings_title'), text: t('onboarding_findings_text')}
  ];
}

function _onboardingRender() {
  if (!_onboarding) return;
  var steps = _onboardingSteps();
  var step = _onboarding.step;
  var root = _onboarding.overlay;
  var last = step === steps.length - 1;
  root.querySelector('#ob-step').textContent = t('onboarding_step_of')
    .replace('{n}', String(step + 1)).replace('{total}', String(steps.length));
  root.querySelector('#ob-title').textContent = steps[step].title;
  root.querySelector('#ob-text').textContent = steps[step].text;
  var dots = root.querySelector('#ob-dots');
  dots.replaceChildren();
  steps.forEach(function(_, i) {
    var dot = document.createElement('span');
    if (i === step) dot.className = 'active';
    dots.appendChild(dot);
  });
  root.querySelector('#ob-skip').textContent = t('btn_skip');
  root.querySelector('#ob-skip').hidden = last;
  root.querySelector('#ob-prev').textContent = t('btn_prev');
  root.querySelector('#ob-prev').hidden = step === 0;
  root.querySelector('#ob-next').textContent = last ? t('btn_finish') : t('btn_next');
}

// Taken down without counting as seen: the session ended under it.
function _onboardingRemove() {
  if (!_onboarding) return;
  document.removeEventListener('keydown', _onboardingKeydown);
  _onboarding.overlay.remove();
  _onboarding = null;
}

function _onboardingClose() {
  if (!_onboarding) return;
  var key = _onboardingUserKey();
  try { if (key) localStorage.setItem(key, '1'); } catch (e) { /* private mode */ }
  _onboardingRemove();
}

function _onboardingKeydown(e) {
  if (e.key === 'Escape') { e.preventDefault(); _onboardingClose(); }
}

function showOnboardingGuide() {
  if (_onboarding) { _onboardingRender(); return; }  // texts may have loaded since
  if (_onboardingIsDone()) return;
  var overlay = document.createElement('div');
  overlay.className = 'onboarding-overlay';
  overlay.innerHTML =
    '<div class="onboarding-modal" role="dialog" aria-modal="true" aria-labelledby="ob-title" aria-describedby="ob-text">' +
      '<div class="onboarding-eyebrow" id="ob-step"></div>' +
      '<h2 id="ob-title"></h2>' +
      '<p id="ob-text"></p>' +
      '<div class="onboarding-dots" id="ob-dots"></div>' +
      '<div class="onboarding-btns">' +
        '<button type="button" class="btn btn-ghost" id="ob-skip"></button>' +
        '<span class="onboarding-nav">' +
          '<button type="button" class="btn btn-ghost" id="ob-prev"></button>' +
          '<button type="button" class="btn btn-primary" id="ob-next"></button>' +
        '</span>' +
      '</div>' +
    '</div>';
  document.body.appendChild(overlay);
  _onboarding = {overlay: overlay, step: 0};
  overlay.querySelector('#ob-skip').addEventListener('click', _onboardingClose);
  overlay.querySelector('#ob-prev').addEventListener('click', function() {
    if (_onboarding && _onboarding.step > 0) { _onboarding.step--; _onboardingRender(); }
  });
  overlay.querySelector('#ob-next').addEventListener('click', function() {
    if (!_onboarding) return;
    if (_onboarding.step < _onboardingSteps().length - 1) { _onboarding.step++; _onboardingRender(); }
    else _onboardingClose();
  });
  document.addEventListener('keydown', _onboardingKeydown);
  _onboardingRender();
  overlay.querySelector('#ob-next').focus();
}

// Signing in ends in _postAuthInit (app.js) on every path: a password login, a
// restored session, first-run setup and finished MFA enrolment. Hooking it
// here keeps the tour out of the login screen without app.js knowing about it,
// and hooking showLoginView takes it down if the session ends while it is open.
(function() {
  var afterSignIn = window._postAuthInit;
  if (typeof afterSignIn === 'function') {
    window._postAuthInit = function() {
      var result = afterSignIn.apply(this, arguments);
      showOnboardingGuide();
      return result;
    };
  }
  var toLogin = window.showLoginView;
  if (typeof toLogin === 'function') {
    window.showLoginView = function() {
      _onboardingRemove();
      return toLogin.apply(this, arguments);
    };
  }
})();

// ── Fetch version on startup ──
(async function loadVersion() {
  try {
    const v = await apiFetch('/api/version');
    const label = v.version.startsWith('v') ? v.version : 'v' + v.version;
    const hdr = document.getElementById('header-version');
    const ftr = document.getElementById('footer-version');
    const apiLabel = document.getElementById('api-version-label');
    if (hdr) hdr.textContent = label;
    if (ftr) ftr.textContent = label;
    if (apiLabel) apiLabel.textContent = '· ' + label;
  } catch (e) { /* keep fallback text */ }
})();
// ── Log / Troubleshooting ─────────────────────────────────────────────────────
var _logAutoRefreshTimer = null;

function levelColor(lvl) {
  if (lvl === 'ERROR' || lvl === 'CRITICAL') return 'var(--red)';
  if (lvl === 'WARNING') return 'var(--orange)';
  if (lvl === 'INFO') return 'var(--blue)';
  return 'var(--text-dim)';
}

async function loadLogs() {
  var level = (document.getElementById('log-level-filter') || {}).value || 'WARNING';
  var box = document.getElementById('log-content');
  var data = await apiFetch('/api/logs?level=' + level + '&limit=300');
  if (!data) return;
  var logs = data.logs || [];
  if (logs.length === 0) {
    box.innerHTML = '<span style="color:var(--text-dim);">' + t('msg_no_log_entries') + '</span>';
    document.getElementById('log-stats').textContent = '0 ' + t('msg_entries');
    return;
  }
  var counts = {DEBUG:0, INFO:0, WARNING:0, ERROR:0, CRITICAL:0};
  var html = logs.map(function(e) {
    counts[e.level] = (counts[e.level] || 0) + 1;
    var ts = e.ts.replace('T', ' ').replace(/\.\d+([Z+][^\s]*)$/, '').replace(/([Z+][^\s]*)$/, '');
    var color = levelColor(e.level);
    var lvlBadge = '<span style="color:' + color + ';font-weight:700;min-width:60px;display:inline-block;">[' + esc(e.level) + ']</span>';
    var loggerSpan = '<span style="color:var(--text-dim);font-size:11px;">' + esc(e.logger) + '</span>';
    return '<div style="padding:2px 0;border-bottom:1px solid var(--border);word-break:break-all;">' +
      '<span style="color:var(--text-dim);margin-right:8px;">' + esc(ts) + '</span>' +
      lvlBadge + ' ' + loggerSpan + '<br>' +
      '<span style="padding-left:8px;color:' + color + ';">' + esc(e.msg) + '</span>' +
      '</div>';
  }).join('');
  box.innerHTML = html;
  box.scrollTop = box.scrollHeight;
  var statsArr = [];
  if (counts.ERROR || counts.CRITICAL) statsArr.push('<span style="color:var(--red);font-weight:700;">' + (counts.ERROR + counts.CRITICAL) + ' ' + t('msg_errors_count') + '</span>');
  if (counts.WARNING) statsArr.push('<span style="color:var(--orange);">' + counts.WARNING + ' ' + t('msg_warnings_count') + '</span>');
  statsArr.push(logs.length + ' ' + t('msg_entries_total'));
  document.getElementById('log-stats').innerHTML = statsArr.join(' &nbsp;·&nbsp; ');
}

async function clearLogs() {
  await apiFetch('/api/logs/clear', {method: 'POST'});
  loadLogs();
}

function copyLogs() {
  var box = document.getElementById('log-content');
  var text = box ? box.innerText : '';
  navigator.clipboard.writeText(text).then(function() {
    showToast(t('msg_log_copied','Log copied to clipboard'), 'success', 2000);
  });
}

function toggleLogAutoRefresh() {
  var checked = document.getElementById('log-auto-refresh').checked;
  if (checked) {
    _logAutoRefreshTimer = setInterval(loadLogs, 3000);
  } else {
    clearInterval(_logAutoRefreshTimer);
    _logAutoRefreshTimer = null;
  }
}

function toggleLogTabVisibility() {
  var show = document.getElementById('input-show-log-tab').checked;
  var btn = document.getElementById('nav-logs');
  if (btn) btn.style.display = show ? 'inline-flex' : 'none';
  localStorage.setItem('msptk_show_log_tab', show ? '1' : '0');
}

// Restore tab visibility on page load
(function() {
  if (localStorage.getItem('msptk_show_log_tab') === '1') {
    const btn = document.getElementById('nav-logs');
    if (btn) btn.style.display = 'inline-flex';
  }
})();

// Check auth on load
checkAuth();

// ── Offline / Online connection indicator ────────────────────────────────────
(function() {
  var banner = document.createElement('div');
  banner.id = 'offline-banner';
  banner.style.cssText = 'display:none;position:fixed;top:0;left:0;right:0;z-index:9999;background:#dc2626;color:#fff;text-align:center;padding:6px 16px;font-size:13px;font-weight:600;transition:transform 0.3s;transform:translateY(-100%);';
  banner.innerHTML = '' + t('msg_offline','No connection — working offline');
  document.body.appendChild(banner);

  function goOffline() {
    banner.style.display = 'block';
    requestAnimationFrame(function() { banner.style.transform = 'translateY(0)'; });
  }
  function goOnline() {
    banner.style.transform = 'translateY(-100%)';
    setTimeout(function() { banner.style.display = 'none'; }, 300);
    showToast(t('msg_back_online','Connection restored'), 'success', 2000);
  }

  window.addEventListener('offline', goOffline);
  window.addEventListener('online', goOnline);
  if (!navigator.onLine) goOffline();
})();
