
import {tlsChainLabel, _taskSchedLabel, _activityLabel, _notifDays} from './app-format.js';
// ═══════════════════════════════════════════════════════════════════
// ALERTS DASHBOARD — MORNING OVERVIEW
// ═══════════════════════════════════════════════════════════════════

import {csvCell, esc} from './app-esc.js';
import {t} from './app-i18n.js';
import {icon} from './app-icons.js';
import {registerUiHandlers} from './app-handlers.js';
import {onViewShown} from './app-hooks.js';
import {_overviewData, canOpenView, hasModule, setOverviewData} from './app-state.js';
import {badgeClass, formatRunName, metricPct, timeAgo, toneClass, toneVar} from './app-format.js';
import {adminSignpostButton, openReportWindow, showConfirm, showToast} from './app-ui.js';
import {apiFetch} from './app-api.js';
import {navShowNetworkTab as showNetworkTab, navShowView as showView} from './app-navigation.js';
import {currentView} from './app-state.js';
import {switchDashTab} from './app-infra.js';
import {dashLoadRenewals} from './app-also.js';

import {alertDetail} from './app-integrations.js';
import {startAudit} from './app-audit.js';
import {openAdmin} from './app-settings.js';
import {deleteCustomer, overviewSelectCustomer, startBulkAudit} from './app-customers.js';
import {openCustomerPage} from './app-customer-detail.js';


// Handlers for the markup this file builds (see registerUiHandlers in app-handlers.js).
function closeExportMenu(restoreFocus) {
  var menu = document.getElementById('overview-export-dd');
  menu.classList.remove('open');
  menu.classList.add('is-resting');
  var trigger = document.getElementById('overview-export-toggle');
  trigger.setAttribute('aria-expanded', 'false');
  if (restoreFocus) trigger.focus();
}
document.addEventListener('click', function(event) {
  var menu = document.getElementById('overview-export-dd');
  if (menu && menu.classList.contains('open') && event.target.id !== 'overview-export-toggle' && !event.target.closest('#overview-export-toggle')) closeExportMenu(false);
});
document.addEventListener('keydown', function(event) {
  var menu = document.getElementById('overview-export-dd');
  if (event.key === 'Escape' && menu && menu.classList.contains('open')) {
    event.preventDefault(); closeExportMenu(true);
  }
});
registerUiHandlers({
  dashToggleExportMenu: function() {
    var menu = document.getElementById('overview-export-dd');
    var open = !menu.classList.contains('open');
    if (!open) { closeExportMenu(false); return; }
    menu.classList.remove('is-resting');
    menu.classList.add('open');
    document.getElementById('overview-export-toggle').setAttribute('aria-expanded', 'true');
  },
  // Notification centre
  notifSetSevFilter: function(el) { notifSetFilter('sev', el.dataset.sev); },
  notifSetFilter: function(el) { notifSetFilter(el.dataset.kind, el.value); },
  notifMarkAllRead: function() { notifMarkAllRead(); },
  notifOpenRules: function() { notifOpenRules(); },
  notifAct: function(el) { notifAct(el.dataset.id); },
  notifActReadOnly: function(el) { notifAct(el.dataset.id, true); },
  // Report archive
  dashArchiveCleanup: function(el) { dashArchiveCleanup(Number(el.dataset.months)); },
  dashArchiveDelete: function(el) { dashArchiveDelete(el.dataset.path); },
  dashArchiveToggleRuns: function(el) {
    el.nextElementSibling.style.display = el.nextElementSibling.style.display === 'none' ? 'block' : 'none';
    el.querySelector('.chevron').classList.toggle('open');
    el.setAttribute('aria-expanded', el.nextElementSibling.style.display !== 'none' ? 'true' : 'false');
  },
  // Customer overview: toolbar, filter badges, sorting and pagination
  filterOverview: function() { filterOverview(); },
  dashSetQuickFilter: function(el) { _quickFilter = el.dataset.quickFilter; filterOverview(); },
  dashClearSearchFilter: function() { document.getElementById('overview-search').value = ''; filterOverview(); },
  dashClearGradeFilter: function() { clearGradeFilter(); },
  dashClearAllFilters: function() {
    document.getElementById('overview-search').value = '';
    _gradeFilter = '';
    _quickFilter = 'all';
    filterOverview();
  },
  startBulkAudit: function() { startBulkAudit(); },
  sortOverview: function(el) { sortOverview(el.dataset.sort); },
  dashPagePrev: function() { _dashPage = Math.max(1, _dashPage - 1); filterOverview(); },
  dashPageNext: function(el) { _dashPage = Math.min(Number(el.dataset.totalPages), _dashPage + 1); filterOverview(); },
  // Customer overview rows. The controls inside a row stop the click so the
  // row's own handler does not open the customer as well.
  dashOverviewSelectCustomer: function(el) { overviewSelectCustomer(el.dataset.customerId); },
  dashFilterByGrade: function(el, event) { event.stopPropagation(); filterByGrade(el.dataset.grade); },
  dashToggleRowActions: function(el, event) { event.stopPropagation(); toggleRowActions(el); },
  dashRowDetails: function(el, event) { event.stopPropagation(); overviewSelectCustomer(el.dataset.customerId); },
  dashRowAudit: function(el, event) { event.stopPropagation(); quickSwitchAndAudit(el.dataset.customerId); },
  dashRowHistory: function(el, event) { event.stopPropagation(); quickSwitchAndView(el.dataset.customerId, 'audit'); },
  dashRowReport: function(el, event) { event.stopPropagation(); window.open('/api/reports/customer-summary/' + encodeURIComponent(el.dataset.customerId), '_blank'); },
  dashRowArchive: function(el, event) { event.stopPropagation(); deleteCustomer(el.dataset.customerId, el.dataset.customerName); },
});

// ── 7a: one merged stream, grouped by urgency, severity as filter chips ──
//
// The three sources (credential expiry, licence renewals, Uniweb hosting)
// used to render as three tables stacked down the page. Nothing merged them,
// so "what should I do first" meant reading three sortings in turn and
// holding the answer in your head. They are now one list.
//
// The design groups by "I dag" / "Tidligere denne uken", which fits an event
// feed. These alerts are not events — they are forward-looking state, and the
// only timestamp on them is a future expiry date. Grouping them under "today"
// would put a label on the rows that means nothing. The axis that carries the
// same "act on this first" meaning for state is how soon it bites, so the
// groups are urgency bands and severity stays where 7a put it: in the chips.

var _notifState = { sev: 'all', source: 'all', customer: 'all' };

// Read state is per-browser. There is no server-side "seen" store, and
// inventing one that silently disagreed between two technicians' sessions
// would be worse than saying so — the sidebar states where it lives.
var _NOTIF_READ_KEY = 'sybr.notif.read';

function _notifRead() {
  try { return JSON.parse(localStorage.getItem(_NOTIF_READ_KEY) || '[]'); } catch (e) { return []; }
}
function _notifIsRead(id) { return _notifRead().indexOf(id) !== -1; }
function _notifMarkRead(id) {
  var seen = _notifRead();
  if (seen.indexOf(id) === -1) { seen.push(id); }
  // Keep the list from growing without bound as alerts come and go.
  try { localStorage.setItem(_NOTIF_READ_KEY, JSON.stringify(seen.slice(-500))); } catch (e) { /* private mode */ }
}

function notifMarkAllRead() {
  (_notifItems || []).forEach(function(n) { _notifMarkRead(n.id); });
  _notifRender();
}

function notifSetFilter(kind, value) {
  _notifState[kind] = value;
  _notifRender();
}

function notifOpenRules() {
  // Rules, thresholds and delivery channels are edited under Administrasjon ›
  // Varsler. This used to open a 'settings' view, which does not exist: every
  // view was hidden and the screen went blank.
  openAdmin('alerts');
  // Land on the alert card, past the Automatisk audit card above it. Not
  // smooth: the panes repaint as their status loads, which cut a smooth
  // scroll short.
  var toggle = document.getElementById('alert-master-toggle');
  var card = toggle && toggle.closest('.card');
  if (!card) return;
  requestAnimationFrame(function() {
    card.scrollIntoView({block: 'start'});
    toggle.focus({preventScroll: true});
  });
}

// Severity vocabulary, shared by the chips, the dots and the badges so a
// colour never means two things in one screen.
var _SEV = {
  // tone: the is-* modifier .filter-chip, .notif-dot and .notif-sev colour by.
  critical: { label: 'Kritisk', tone: 'is-critical' },
  warning:  { label: 'Advarsel', tone: 'is-warning' },
  info:     { label: 'Info',     tone: 'is-info' }
};



// What Varsler last loaded: its items, the alert settings and the coverage
// the server reported. Unset until it has loaded once.
var _notifItems;
var _notifConfig;
var _notifCoverage;

export async function dashLoadAlerts() {
  var el = document.getElementById('dash-alerts-content');
  el.innerHTML = '<div class="loader loader-md"></div>';

  // Three sources, fetched together. Uniweb is optional — a customer without
  // it configured is not an error, so its failure narrows the stream rather
  // than emptying the screen.
  var res = await Promise.all([
    apiFetch('/api/dashboard/alerts'),
    hasModule('billing') ? apiFetch('/api/uniweb/alerts').catch(function() { return null; }) : null,
    apiFetch('/api/alerts/config').catch(function() { return null; }),
    // What the automatic alerts sent (certificates, domains, firmware...)
    // and what happened (the bell's events).
    apiFetch('/api/alerts/history?limit=200').catch(function() { return null; }),
    apiFetch('/api/activity-log?limit=20').catch(function() { return null; }),
  ]);
  var data = res[0], uniweb = res[1], cfg = res[2], history = res[3], activity = res[4];

  if (!data) {
    el.innerHTML = '<div class="alert alert-error">' + t('msg_alerts_failed', 'Kunne ikke hente varsler.') + '</div>';
    return;
  }

  _notifItems = _notifCollect(data, uniweb, history, activity);
  _notifConfig = cfg;
  _notifCoverage = data.coverage || null;
  _notifRender();
}

// Flatten the three shapes into one. Each item carries the id its read state
// is keyed on, which has to be stable across reloads — so it is built from
// what identifies the alert, never from its position in the list.
function _notifCollect(data, uniweb, history, activity) {
  var out = [];
  var idByName = {};
  ((_overviewData && _overviewData.customers) || []).forEach(function(c) { idByName[c.customer_name] = c.customer_id; });

  (data.credential_expiry || []).forEach(function(i) {
    out.push({
      id: 'cred:' + (i.customer_id || i.customer_name) + ':' + (i.type || '') + ':' + (i.expiry_date || ''),
      sev: i.category || 'info',
      title: t('notif_cred_expiry', 'Legitimasjon utløper') + ': ' + (i.type || ''),
      customer: i.customer_name, customerId: i.customer_id || '',
      source: t('src_credentials', 'Legitimasjon'),
      days: i.days_remaining, when: i.expiry_date,
      action: t('btn_open_customer', 'Åpne kunde'), act: 'customer'
    });
  });

  (data.renewals || []).forEach(function(i) {
    out.push({
      id: 'renew:' + (i.customer_id || i.customer_name) + ':' + (i.service_name || '') + ':' + (i.contract_end || ''),
      sev: i.category || 'info',
      title: t('notif_renewal', 'Fornyelse') + ': ' + (i.service_name || ''),
      customer: i.customer_name, customerId: i.customer_id || '',
      source: 'ALSO',
      days: i.days_remaining, when: i.contract_end,
      handled: !!i.handled,
      action: t('btn_see_renewal', 'Se fornyelse'), act: 'customer'
    });
  });

  // What the TLS checks last saw, read from stored state rather than from
  // what the alert engine managed to send: the engine records an alert only
  // once a Teams or e-mail channel took it, so with no channel set up an
  // expiring certificate showed nowhere. Expired, expiring within 30 days, or
  // a chain that does not validate.
  (data.certificates || []).forEach(function(i) {
    var endpoint = (i.host || '') + ':' + (i.port || '');
    var detail = [];
    if (i.label) detail.push(i.label);
    if (i.chain_problem) detail.push(tlsChainLabel(i.chain_problem));
    if (i.stale) detail.push(t('tls_last_check_failed', 'Siste sjekk nådde ikke fram'));
    var tlsTab = canOpenView('network');
    out.push({
      id: 'tls:' + endpoint + ':' + (i.kind || '') + ':' + (i.not_after || ''),
      sev: i.category || 'warning',
      title: (i.kind === 'chain' ? t('notif_tls_chain', 'Ugyldig sertifikatkjede') : t('notif_tls_cert', 'TLS-sertifikat')) + ': ' + endpoint,
      customer: i.customer_name || '', customerId: i.customer_id || '',
      source: t('src_certificates', 'Sertifikater'),
      // The expiry date for an expiring certificate; for a broken chain, the
      // day it was last checked, as for firmware.
      days: i.days_remaining, when: i.kind === 'chain' ? String(i.checked_at || '').slice(0, 10) : (i.not_after || ''),
      detail: detail.join(' · '),
      action: tlsTab ? t('btn_open_tls', 'Åpne TLS') : t('btn_open_customer', 'Åpne kunde'),
      act: tlsTab ? 'tls' : 'customer', tab: 'nettverk'
    });
  });

  // The firmware each device was last read with: end of life, or behind.
  (data.firmware || []).forEach(function(i) {
    // An end-of-life model's "latest" is its last release, often the one it
    // runs; only a device that is behind has somewhere to go.
    var behind = i.status === 'outdated' && i.latest && i.latest !== i.version;
    var detail = (i.vendor === 'fortigate' ? 'FortiGate' : 'UniFi') + (i.model ? ' ' + i.model : '')
      + (i.version ? ', ' + i.version : '') + (behind ? ' → ' + i.latest : '');
    if (i.read_error) detail += ' · ' + t('fw_last_read_failed', 'Siste lesing feilet');
    out.push({
      id: 'fw:' + (i.customer_id || '') + ':' + (i.vendor || '') + ':' + (i.device_key || '') + ':' + (i.status || '') + ':' + (i.version || ''),
      sev: i.category || 'warning',
      title: (i.status === 'eol' ? t('notif_fw_eol', 'Enheten har nådd end of life') : t('notif_fw_outdated', 'Utdatert firmware')) + ': ' + (i.device_name || ''),
      customer: i.customer_name || '', customerId: i.customer_id || '',
      source: t('src_firmware', 'Firmware'),
      days: null, when: String(i.checked_at || '').slice(0, 10), detail: detail,
      action: t('btn_open_network_tab', 'Åpne Nettverk'), act: 'customer', tab: 'nettverk'
    });
  });

  var typeLabels = {
    domain: t('lbl_type_domain', 'Domene'),
    subscription: t('lbl_type_subscription', 'Abonnement'),
    ssl: t('lbl_type_ssl', 'SSL')
  };
  if (uniweb && uniweb.items) {
    uniweb.items.forEach(function(i) {
      out.push({
        id: 'uniweb:' + (i.customer_name || '') + ':' + (i.type || '') + ':' + (i.item_name || ''),
        sev: i.category || 'info',
        title: (typeLabels[i.type] || i.type || '') + ': ' + (i.item_name || ''),
        customer: i.customer_name, customerId: '',
        source: 'Uniweb',
        days: i.days_remaining, when: i.expiry_date,
        action: t('btn_see_domain', 'Se domene'), act: 'domains'
      });
    });
  }

  // What the automatic alerts sent in the last 30 days: the newest of each
  // (the engine repeats an alert every check while it holds).
  var ruleLabels = {
    ssl_expiry: t('rule_ssl_expiry', 'TLS-sertifikater'), domain_expiry: t('rule_domain_expiry', 'Domener'),
    fortigate_threats: t('rule_fortigate_threats', 'Brannmur-hendelser'), firmware_outdated: t('rule_firmware', 'Utdatert firmware'),
    also_license_expiry: t('rule_also', 'Lisensfornyelser'), mfa_coverage: t('rule_mfa', 'MFA-dekning'),
    pentest_critical: t('rule_pentest', 'Kritiske pentest-funn'),
  };
  var since = new Date(Date.now() - 30 * 86400000).toISOString();
  var seenAlert = {};
  ((history && history.entries) || []).forEach(function(h) {
    if (!h.sent_at || h.sent_at < since) return;
    var key = (h.type || '') + ':' + (h.customer || '') + ':' + (h.item || '');
    if (seenAlert[key]) return;
    seenAlert[key] = true;
    out.push({
      id: 'alert:' + key, kind: 'alert',
      sev: h.severity === 'critical' ? 'critical' : 'warning',
      title: (ruleLabels[h.type] || h.type || '') + (h.item ? ': ' + h.item : ''),
      customer: h.customer || '', customerId: idByName[h.customer] || '',
      source: t('src_alert_engine', 'Automatiske varsler'),
      days: null, when: String(h.sent_at).slice(0, 10), detail: alertDetail(h),
      action: t('btn_open_customer', 'Åpne kunde'), act: 'customer'
    });
  });

  // The bell's events: what has happened, newest first.
  var hide = {settings_changed: true, customer_switched: true, alert_config_changed: true};
  ((activity && activity.entries) || []).forEach(function(e) {
    if (hide[e.action]) return;
    var customerRow = ((_overviewData && _overviewData.customers) || []).find(function(c) { return c.customer_id === e.customer || c.customer_name === e.customer; });
    out.push({
      id: 'event:' + (e.timestamp || '') + ':' + (e.action || ''), kind: 'event',
      sev: 'info', title: _activityLabel(e.action || ''),
      customer: customerRow ? customerRow.customer_name : (e.customer || ''), customerId: customerRow ? customerRow.customer_id : '',
      source: t('src_events', 'Hendelser'),
      days: null, when: e.timestamp ? timeAgo(e.timestamp) : '', detail: e.detail || '',
      action: t('btn_open_customer', 'Åpne kunde'), act: 'customer'
    });
  });

  // Soonest first inside every group, expired at the top; without a date,
  // the most severe first (an end-of-life firewall before a self-signed
  // certificate).
  var rank = {critical: 0, warning: 1, info: 2};
  out.sort(function(a, b) {
    var x = (a.days === null || a.days === undefined) ? 9e9 : a.days;
    var y = (b.days === null || b.days === undefined) ? 9e9 : b.days;
    return (x - y) || ((rank[a.sev] === undefined ? 3 : rank[a.sev]) - (rank[b.sev] === undefined ? 3 : rank[b.sev]));
  });
  return out;
}

function _notifRender() {
  var el = document.getElementById('dash-alerts-content');
  if (!el) return;
  var items = _notifItems || [];

  // Chip counts describe the whole stream, not the filtered view — a chip
  // that recounted itself after being clicked could never be clicked back.
  var counts = { all: items.length, critical: 0, warning: 0, info: 0 };
  var sources = {}, customers = {};
  items.forEach(function(n) {
    if (counts[n.sev] !== undefined) counts[n.sev]++;
    sources[n.source] = 1;
    if (n.customer) customers[n.customer] = 1;
  });

  var shown = items.filter(function(n) {
    return (_notifState.sev === 'all' || n.sev === _notifState.sev)
        && (_notifState.source === 'all' || n.source === _notifState.source)
        && (_notifState.customer === 'all' || n.customer === _notifState.customer);
  });

  var html = '<div class="notif-toolbar">';
  [['all', t('sev_all', 'Alle')], ['critical', _SEV.critical.label],
   ['warning', _SEV.warning.label], ['info', _SEV.info.label]].forEach(function(p) {
    var key = p[0];
    var tone = key === 'all' ? 'is-all' : _SEV[key].tone;
    html += '<button class="filter-chip ' + tone + (_notifState.sev === key ? ' active' : '') + '"'
         + ' data-click-handler="notifSetSevFilter" data-sev="' + esc(key) + '">'
         + esc(p[1]) + ' <b>' + counts[key] + '</b></button>';
  });
  html += _notifSelect('source', t('lbl_source', 'Kilde'), Object.keys(sources));
  html += _notifSelect('customer', t('col_customer', 'Kunde'), Object.keys(customers));
  html += '<div class="flex-1"></div>';
  html += '<button class="btn btn-link btn-sm" data-click-handler="notifMarkAllRead">' + t('btn_mark_all_read', 'Marker alle som lest') + '</button>';
  html += '</div>';

  html += '<div class="notif-grid"><div>';
  if (!shown.length) {
    html += '<div class="notif-card empty-note">'
         + (items.length
             ? t('msg_no_alerts_in_filter', 'Ingen varsler i dette filteret.')
             : t('msg_all_clear', 'Ingenting krever handling. Ingen legitimasjon, fornyelser, domener eller sertifikater utløper innen 30 dager, og ingen av enhetene som er lest, har utdatert firmware.'))
         + '</div>';
  } else {
    // Urgency bands, not calendar days: these alerts describe what is about
    // to happen, so the useful grouping is how soon.
    var dated = function(n) { return n.days !== null && n.days !== undefined; };
    var bands = [
      { title: t('grp_now', 'Krever handling nå'), test: function(n) { return dated(n) && n.days <= 7; } },
      { title: t('grp_month', 'Innen 30 dager'),   test: function(n) { return dated(n) && n.days > 7; } },
      { title: t('grp_alerted', 'Sendt av automatiske varsler'), test: function(n) { return n.kind === 'alert'; } },
      { title: t('grp_other', 'Uten frist'),       test: function(n) { return !dated(n) && !n.kind; } },
      { title: t('grp_events', 'Siste hendelser'), test: function(n) { return n.kind === 'event'; } }
    ];
    bands.forEach(function(b) {
      var rows = shown.filter(b.test);
      if (!rows.length) return;
      html += '<div class="mb-5"><div class="notif-group-label">' + esc(b.title) + ' (' + rows.length + ')</div>';
      html += '<div class="notif-list">';
      rows.forEach(function(n) { html += _notifRow(n); });
      html += '</div></div>';
    });
  }
  html += '</div>' + _notifSidebar() + '</div>';

  el.innerHTML = html;
}

function _notifSelect(kind, label, values) {
  var html = '<select class="field-input field-input-sm w-auto"'
           + ' aria-label="' + esc(label) + '"'
           + ' data-change-handler="notifSetFilter" data-kind="' + esc(kind) + '">';
  html += '<option value="all"' + (_notifState[kind] === 'all' ? ' selected' : '') + '>'
       + esc(label) + ': ' + t('lbl_all', 'Alle') + '</option>';
  values.sort().forEach(function(v) {
    html += '<option value="' + esc(v) + '"' + (_notifState[kind] === v ? ' selected' : '') + '>' + esc(v) + '</option>';
  });
  return html + '</select>';
}

function _notifRow(n) {
  var sev = _SEV[n.sev] || _SEV.info;
  var unread = !_notifIsRead(n.id);
  var html = '<div class="notif-row' + (unread ? ' unread' : '') + (n.handled ? ' is-handled' : '') + '">';
  html += '<span class="notif-dot ' + sev.tone + '"></span>';
  html += '<div class="notif-body">';
  html += '<div class="notif-head"><span class="notif-title">' + esc(n.title) + '</span>';
  html += '<span class="notif-sev ' + sev.tone + '">' + esc(sev.label.toUpperCase()) + '</span>';
  if (n.days !== null && n.days !== undefined) {
    html += '<span class="notif-sev ' + sev.tone + '">' + esc(_notifDays(n.days)) + '</span>';
  }
  html += '</div>';
  html += '<div class="notif-meta">';
  if (n.customer) html += '<span class="cust">' + esc(n.customer) + '</span>';
  html += '<span class="src">' + esc(n.source) + '</span>';
  if (n.when) html += '<span>' + esc(n.when) + '</span>';
  if (n.detail) html += '<span class="notif-detail">' + esc(n.detail) + '</span>';
  html += '</div></div>';
  html += '<div class="notif-actions">';
  // An event or alert about no customer we know has nothing to open.
  if (n.act !== 'customer' || n.customerId) {
    html += '<button class="btn btn-default btn-sm"'
         + ' data-click-handler="notifAct" data-id="' + esc(n.id) + '">' + esc(n.action) + '</button>';
  }
  if (unread) {
    html += '<button class="btn btn-default btn-sm"'
         + ' title="' + t('tip_mark_read', 'Marker som lest') + '"'
         + ' aria-label="' + t('tip_mark_read', 'Marker som lest') + '"'
         + ' data-click-handler="notifActReadOnly" data-id="' + esc(n.id) + '">&#10003;</button>';
  }
  html += '</div></div>';
  return html;
}

// One click both acts and marks read — a technician who has opened the
// customer has plainly seen the alert.
function notifAct(id, readOnly) {
  var n = (_notifItems || []).filter(function(x) { return x.id === id; })[0];
  _notifMarkRead(id);
  if (!readOnly && n) {
    // A certificate is handled on Verktøy › Nettverk › TLS, where it can be
    // checked again; firmware on the customer's Nettverk tab.
    if (n.act === 'tls' && canOpenView('network')) {
      showNetworkTab('net-tls');
      return;
    }
    if (n.act === 'customer' && n.tab && n.customerId) {
      openCustomerPage(n.customerId, n.tab);
      return;
    }
    if (n.act === 'customer' && n.customerId) {
      showCustomerDetail(n.customerId, n.customer);
      return;
    }
    if (n.act === 'domains' && canOpenView('billing')) {
      showBillingTab('dash-domains');
      return;
    }
  }
  _notifRender();
}

// Where the alerts go, and the way to the rules: the switches themselves are
// under Administrasjon › Varsler.
function _notifSidebar() {
  var cfg = _notifConfig;
  var html = '<div class="notif-side"><div class="notif-card"><h4>' + esc(t('hdr_delivery', 'Levering')) + '</h4>';
  if (cfg) {
    var chans = [];
    // The switch alone sends nothing: Teams needs a stored webhook.
    if (cfg.notify_teams && cfg.teams_webhook_set !== false) chans.push('Teams');
    if (cfg.notify_email && cfg.email_recipient) chans.push(cfg.email_recipient);
    html += '<p class="notif-side-text">'
         + esc(chans.length
             ? t('msg_delivery_to', 'Varsler sendes til') + ' ' + chans.join(', ') + '.'
             : t('msg_delivery_none', 'Ingen kanal er satt opp, så varslene vises bare her.'))
         + '</p>';
    if (!cfg.enabled) {
      html += '<p class="notif-side-text is-warn">' + esc(t('msg_alerts_disabled', 'Automatiske varsler er slått av, så ingen av reglene sender noe. Slå dem på under Administrasjon › Varsler.')) + '</p>';
    }
  } else {
    html += '<p class="notif-side-text">' + esc(t('msg_rules_unavailable', 'Kunne ikke hente reglene.')) + '</p>';
  }
  html += canOpenView('admin')
    ? '<button class="btn btn-default btn-sm" data-click-handler="notifOpenRules">' + esc(t('btn_change_channels', 'Endre kanaler')) + '</button>'
    : '<p class="notif-side-text">' + esc(t('msg_rules_admin_only', 'Bare administratorer kan endre reglene.')) + '</p>';
  return html + '</div>' + _notifCoverageCard() + '</div>';
}

// What the certificate and firmware items rest on. An empty list means
// nothing needs action only if something was looked at; this says how much
// was, and when.
function _notifCoverageCard() {
  var cov = _notifCoverage;
  if (!cov) return '';
  var html = '<div class="notif-card"><h4>' + esc(t('hdr_checked_state', 'Hva er sjekket')) + '</h4>';
  var tls = cov.tls || {};
  var fw = cov.firmware || {};
  var day = function(iso) { return String(iso || '').slice(0, 10); };
  var line;
  if (tls.unavailable) line = t('msg_cov_tls_unavailable', 'Lagrede sertifikater kunne ikke leses.');
  else if (!tls.endpoints) line = t('msg_cov_tls_none', 'Ingen TLS-endepunkter er sjekket ennå.');
  else line = t('msg_cov_tls', 'TLS-endepunkter sjekket: {n}, sist {date}.').replace('{n}', Number(tls.endpoints)).replace('{date}', day(tls.last_checked))
    + (tls.unreachable ? ' ' + t('msg_cov_tls_unreachable', 'Ikke nådd: {n}.').replace('{n}', Number(tls.unreachable)) : '');
  html += '<p class="notif-side-text">' + esc(line) + '</p>';
  if (fw.unavailable) line = t('msg_cov_fw_unavailable', 'Lagret firmware kunne ikke leses.');
  else if (!fw.devices) line = t('msg_cov_fw_none', 'Ingen enheters firmware er lest ennå.');
  else line = t('msg_cov_fw', 'Enheter med lest firmware: {n}, sist {date}.').replace('{n}', Number(fw.devices)).replace('{date}', day(fw.last_read))
    + (fw.unknown ? ' ' + t('msg_cov_fw_unknown', 'Firmware ikke bekreftet: {n}.').replace('{n}', Number(fw.unknown)) : '');
  html += '<p class="notif-side-text' + (fw.unknown ? ' is-warn' : '') + '">' + esc(line) + '</p>';
  // A table past its window turns every "current" into "not confirmed"; say so,
  // or the unconfirmed count above has no explanation.
  (fw.stale_tables || []).forEach(function(s) {
    line = t('msg_cov_fw_table_stale', 'Firmwaretabellen for {vendor} er utdatert, siste oppdatering {date}. Enheter på nyeste kjente versjon kan derfor ikke bekreftes.')
      .replace('{vendor}', s.vendor === 'fortigate' ? 'FortiOS' : 'UniFi')
      .replace('{date}', function() { return day(s.as_of); });
    html += '<p class="notif-side-text is-warn">' + esc(line) + '</p>';
  });
  return html + '</div>';
}

// ═══════════════════════════════════════════════════════════════════
// DOMAIN, MAIL AND LICENCE CHAIN (shown on the Domener tab)
// ═══════════════════════════════════════════════════════════════════

// ── Domain-Email Chain section builder ──

function _buildChainSection(chainData) {
  var html = '';
  html += '<div class="my-5">';
  html += '<div class="text-md fw-bold mb-3">'+icon('mail',16)+' '+t('hdr_domain_email_chain','Domain-Email-License')+'</div>';

  if (!chainData || !chainData.items || chainData.items.length === 0) {
    html += '<div class="card p-4 text-center text-success text-sm">';
    html += '<div class="text-xl mb-1">&#10003;</div>';
    html += t('msg_no_chain_alerts','No domain-email mismatches found.')+'</div>';
    html += '</div>';
    return html;
  }

  var s = chainData.summary || {};

  // KPI badges
  html += '<div class="flex gap-3 mb-3 text-sm">';
  if (s.double_paying > 0) html += '<span class="badge badge-warning">'+Number(s.double_paying)+' '+t('lbl_double_paying','Double Paying')+'</span>';
  if (s.missing_m365 > 0) html += '<span class="badge badge-danger">'+Number(s.missing_m365)+' '+t('lbl_missing_m365','Missing M365')+'</span>';
  if (s.unused_m365 > 0) html += '<span class="badge badge-info">'+Number(s.unused_m365)+' '+t('lbl_unused_m365','Unused M365')+'</span>';
  html += '</div>';

  // Table
  html += '<div class="card p-0 overflow-hidden">';
  html += '<table class="data-table">';
  html += '<thead><tr>';
  html += '<th class="p-2">'+t('col_customer','Customer')+'</th>';
  html += '<th class="p-2">'+t('col_domain','Domain')+'</th>';
  html += '<th class="text-center p-2">'+t('col_mx_exchange','MX Exchange')+'</th>';
  html += '<th class="text-center p-2">'+t('col_has_m365','M365')+'</th>';
  html += '<th class="text-center p-2">'+t('col_uniweb_email','Uniweb Email')+'</th>';
  html += '<th class="p-2">'+t('col_alert','Alert')+'</th>';
  html += '</tr></thead><tbody>';

  var chkY = '<span class="text-success fw-bold text-base">&#10003;</span>';
  var chkN = '<span class="text-danger fw-bold text-base">&#10007;</span>';

  chainData.items.forEach(function(item, i) {
    var alertHtml = '';
    item.alerts.forEach(function(a) {
      var sevColors = {critical:'var(--red)', warning:'var(--orange)', info:'var(--blue)'};
      var sevLabels = {critical:t('lbl_severity_critical','Critical'), warning:t('lbl_severity_warning','Warning'), info:t('lbl_severity_info','Info')};
      alertHtml += '<div class="mb-0-5"><span class="'+badgeClass(sevColors[a.severity])+'">'+esc(sevLabels[a.severity]||a.severity)+'</span> <span class="text-xs">'+esc(a.message)+'</span></div>';
    });

    html += '<tr>';
    html += '<td class="fw-medium">'+esc(item.customer_name)+'</td>';
    html += '<td>'+esc(item.domain)+'</td>';
    html += '<td class="text-center">'+(item.mx_exchange ? chkY : chkN)+'</td>';
    html += '<td class="text-center">'+(item.has_m365 ? chkY : chkN)+'</td>';
    html += '<td class="text-center">'+(item.has_uniweb_email ? chkY : chkN)+'</td>';
    html += '<td>'+alertHtml+'</td>';
    html += '</tr>';
  });

  html += '</tbody></table></div>';
  html += '</div>';
  return html;
}

// ═══════════════════════════════════════════════════════════════════
// UNIFIED COST OVERVIEW — ALSO MRR + UNIWEB HOSTING
// ═══════════════════════════════════════════════════════════════════

async function dashLoadCosts() {
  var el = document.getElementById('dash-costs-content');
  el.innerHTML = '<div class="loader loader-md"></div>';

  var data = await apiFetch('/api/dashboard/costs');
  if (!data) { el.innerHTML = '<div class="text-danger text-center p-12">' + t('dash_costs_load_failed','Kunne ikke laste kostnadsdata') + '</div>'; return; }

  var customers = data.customers || [];
  var totals = data.totals || {};

  if (customers.length === 0) {
    el.innerHTML = '<div class="card empty-note is-compact"><div class="text-base fw-semibold mb-1">' + t('dash_no_cost_data','Ingen kostnadsdata') + '</div><div class="text-sm">' + t('dash_no_cost_hint','Synkroniser ALSO-fornyelser eller Uniweb-kontoer for å se kostnader her.') + '</div></div>';
    return;
  }

  var html = '';

  // ── KPI row ──
  html += '<div class="grid grid-cols-4 gap-3 mb-4">';
  var kpis = [
    {label:'Total MRR',           value:_fmtNOK(totals.total_monthly),  color:'var(--blue)'},
    {label:'ALSO MRR',            value:_fmtNOK(totals.also_mrr),       color:'#7c5cfc'},
    {label:'Uniweb manedlig',     value:_fmtNOK(totals.uniweb_monthly), color:'#e67e22'},
    {label:t('dash_customer_count','Antall kunder'), value:Number(totals.customer_count),           color:'var(--text)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card kpi-card ' + toneVar(k.color) + '">';
    html += '<div class="kpi-value ' + toneClass(k.color) + '">'+k.value+'</div>';
    html += '<div class="kpi-label">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // ── Customer cost table ──
  html += '<div class="card p-0 overflow-hidden">';
  html += '<table class="data-table">';
  html += '<thead><tr>';
  html += '<th class="p-2">'+t('col_customer','Kunde')+'</th>';
  html += '<th class="text-right p-2">'+t('col_also_mrr','ALSO MRR')+'</th>';
  html += '<th class="text-right p-2">'+t('col_uniweb_cost','Uniweb')+'</th>';
  html += '<th class="text-right p-2">'+t('col_total_cost','Total')+'</th>';
  html += '<th class="text-center p-2 col-bar">'+t('col_distribution','Fordeling')+'</th>';
  html += '<th class="text-center p-2">'+t('col_subs','Abb.')+'</th>';
  html += '</tr></thead><tbody>';

  var maxTotal = customers.length ? customers[0].total_monthly : 1;

  customers.forEach(function(c, i) {
    var alsoPct = c.total_monthly > 0 ? (c.also_mrr / c.total_monthly * 100) : 0;
    var uniwebPct = c.total_monthly > 0 ? (c.uniweb_monthly / c.total_monthly * 100) : 0;
    var barWidth = maxTotal > 0 ? Math.max((c.total_monthly / maxTotal * 100), 2) : 0;

    html += '<tr>';
    html += '<td class="fw-medium">'+esc(c.customer_name)+'</td>';
    html += '<td class="text-right text-purple fw-semibold">'+_fmtNOK(c.also_mrr)+'</td>';
    html += '<td class="text-right text-warning fw-semibold">'+_fmtNOK(c.uniweb_monthly)+'</td>';
    html += '<td class="text-right fw-bold">'+_fmtNOK(c.total_monthly)+'</td>';

    // Stacked bar
    html += '<td>';
    html += '<div class="stack-bar" data-bar="'+barWidth+'">';
    if (alsoPct > 0)   html += '<div class="stack-seg bg-purple" data-bar="'+alsoPct+'" title="ALSO '+Math.round(alsoPct)+'%"></div>';
    if (uniwebPct > 0) html += '<div class="stack-seg bg-warning" data-bar="'+uniwebPct+'" title="Uniweb '+Math.round(uniwebPct)+'%"></div>';
    html += '</div></td>';

    // Subscription counts
    html += '<td class="text-center text-xs text-muted">';
    if (c.also_subscriptions) html += '<span class="text-purple" title="ALSO">'+Number(c.also_subscriptions)+'</span>';
    if (c.also_subscriptions && c.uniweb_subscriptions) html += ' / ';
    if (c.uniweb_subscriptions) html += '<span class="text-warning" title="Uniweb">'+Number(c.uniweb_subscriptions)+'</span>';
    if (!c.also_subscriptions && !c.uniweb_subscriptions) html += '-';
    html += '</td>';

    html += '</tr>';
  });

  // ── Total row ──
  html += '<tr class="fw-bold">';
  html += '<td class="p-2">' + t('dash_total','Totalt') + ' ('+Number(totals.customer_count)+' ' + t('dash_customers_lc','kunder') + ')</td>';
  html += '<td class="p-2 text-right text-purple">'+_fmtNOK(totals.also_mrr)+'</td>';
  html += '<td class="p-2 text-right text-warning">'+_fmtNOK(totals.uniweb_monthly)+'</td>';
  html += '<td class="p-2 text-right">'+_fmtNOK(totals.total_monthly)+'</td>';
  html += '<td class="p-2"></td>';
  html += '<td class="p-2"></td>';
  html += '</tr>';

  html += '</tbody></table></div>';

  // ── Legend ──
  html += '<div class="flex gap-4 mt-2 text-xs text-muted">';
  html += '<span><span class="swatch bg-purple"></span>ALSO Cloud</span>';
  html += '<span><span class="swatch bg-warning"></span>' + t('dash_uniweb_hosting','Uniweb Hosting') + '</span>';
  html += '</div>';

  el.innerHTML = html;
}

function _fmtNOK(val) {
  if (val === null || val === undefined || val === 0) return '0 kr';
  return Number(val).toLocaleString('nb-NO', {minimumFractionDigits: 0, maximumFractionDigits: 0}) + ' kr';
}

// ═══════════════════════════════════════════════════════════════════
// DOMAIN HEALTH DASHBOARD
// ═══════════════════════════════════════════════════════════════════

async function dashLoadDomains() {
  var el = document.getElementById('dash-domains-content');
  el.innerHTML = '<div class="loader loader-md"></div>' +
    '<div class="text-center text-muted text-sm mt-2">' + t('dash_checking_tls','Sjekker TLS-sertifikater for alle domener ...') + '</div>';

  // The domain, mail and licence chain (paying twice for mail, a domain
  // with M365 mail but no licence) lived on the Helse tab. It is about
  // domains, so it is read here.
  var both = await Promise.all([
    apiFetch('/api/dashboard/domains'),
    apiFetch('/api/dashboard/domain-email-chain').catch(function() { return null; }),
  ]);
  var data = both[0];
  var chainHtml = _buildChainSection(both[1]);
  if (!data) {
    el.innerHTML = '<div class="text-danger text-center p-12">' + t('dash_domains_load_failed','Kunne ikke laste domenedata') + '</div>';
    return;
  }

  var domains = data.domains || [];
  var s = data.summary || {};
  var html = '';

  // KPI cards
  html += '<div class="grid grid-cols-6 gap-3 mb-4">';
  var kpis = [
    {label:t('dash_domains_total', 'Domener totalt'), value:Number(s.total)||0, color:'var(--blue)'},
    {label:t('dash_domains_healthy', 'Friske'), value:Number(s.healthy)||0, color:'var(--green)'},
    {label:t('dash_domains_warning', 'Advarsel'), value:Number(s.warning)||0, color:s.warning>0?'var(--orange)':'var(--text-dim)'},
    {label:t('dash_domains_critical', 'Kritisk'), value:Number(s.critical)||0, color:s.critical>0?'var(--red)':'var(--text-dim)'},
    {label:t('dash_missing_spf','Mangler SPF'), value:Number(s.missing_spf)||0, color:s.missing_spf>0?'var(--orange)':'var(--text-dim)'},
    {label:t('dash_missing_dmarc','Mangler DMARC'), value:Number(s.missing_dmarc)||0, color:s.missing_dmarc>0?'var(--orange)':'var(--text-dim)'}
  ];
  kpis.forEach(function(k) {
    html += '<div class="card kpi-card ' + toneVar(k.color) + '">';
    html += '<div class="kpi-value ' + toneClass(k.color) + '">' + k.value + '</div>';
    html += '<div class="kpi-label">' + k.label + '</div>';
    html += '</div>';
  });
  html += '</div>';

  if (s.ssl_expiring_30d > 0) {
    html += '<div class="callout callout-warning mb-4 text-warning fw-semibold">';
    html += Number(s.ssl_expiring_30d) + ' ' + t('dash_ssl_expiring_30d','SSL-sertifikat utløper innen 30 dager');
    html += '</div>';
  }

  if (domains.length === 0) {
    html += '<div class="card empty-note is-compact">';
    html += '<div class="text-base">' + t('dash_no_domains','Ingen domener funnet') + '</div>';
    html += '<div class="text-sm mt-1">' + t('dash_no_domains_hint','Synkroniser Uniweb-data for å se domener her.') + '</div>';
    html += '</div>';
    el.innerHTML = html + chainHtml;
    return;
  }

  // Domain table
  html += '<div class="card p-0 overflow-hidden">';
  html += '<table class="data-table">';
  html += '<thead><tr>';
  html += '<th class="text-center p-2 col-check">'+t('col_health','Helse')+'</th>';
  html += '<th class="p-2">'+t('col_domain','Domene')+'</th>';
  html += '<th class="p-2">'+t('col_customer','Kunde')+'</th>';
  html += '<th class="text-center p-2">'+t('col_ssl','SSL')+'</th>';
  html += '<th class="text-center p-2">'+t('col_spf','SPF')+'</th>';
  html += '<th class="text-center p-2">'+t('col_dkim','DKIM')+'</th>';
  html += '<th class="text-center p-2">'+t('col_dmarc','DMARC')+'</th>';
  html += '<th class="text-center p-2">'+t('col_dns','DNS')+'</th>';
  html += '<th class="text-center p-2">'+t('col_expires','Utløper')+'</th>';
  html += '</tr></thead><tbody>';

  domains.forEach(function(d, i) {
    var healthColors = {good:'var(--green)', warning:'var(--orange)', critical:'var(--red)', unknown:'var(--text-dim)'};
    var healthLabels = {good:'OK', warning:'!', critical:'X', unknown:'?'};
    var hColor = healthColors[d.health] || 'var(--text-dim)';

    // SSL cell
    var sslHtml = '';
    if (d.ssl && d.ssl.days_remaining !== null && d.ssl.days_remaining !== undefined) {
      var sslColor = 'var(--green)';
      if (d.ssl.days_remaining < 0) sslColor = 'var(--red)';
      else if (d.ssl.days_remaining < 30) sslColor = 'var(--orange)';
      var sslLabel = d.ssl.days_remaining < 0 ? t('lbl_expired_short', 'Utløpt') : Number(d.ssl.days_remaining) + 'd';
      var gradeStr = d.ssl.grade ? ' ' + esc(d.ssl.grade) : '';
      sslHtml = '<span class="' + toneClass(sslColor) + ' fw-semibold" title="' + esc(d.ssl.issuer || '') + ' · ' + t('dash_valid_until','gyldig til') + ' ' + esc(d.ssl.valid_until || '') + '">' + sslLabel + gradeStr + '</span>';
    } else {
      sslHtml = '<span class="text-dim">—</span>';
    }

    // Check/X helper
    var chkY = '<span class="text-success fw-bold text-base">&#10003;</span>';
    var chkN = '<span class="text-danger fw-bold text-base">&#10007;</span>';

    // Expiry cell
    var expiryHtml = '';
    if (d.days_until_expiry !== null && d.days_until_expiry !== undefined) {
      var expColor = 'var(--text)';
      if (d.days_until_expiry < 0) expColor = 'var(--red)';
      else if (d.days_until_expiry < 90) expColor = 'var(--orange)';
      expiryHtml = '<span class="' + toneClass(expColor) + '" title="' + esc(d.expiry) + '">' + (d.days_until_expiry < 0 ? esc(t('lbl_expired_short', 'Utløpt')) : Number(d.days_until_expiry) + 'd') + '</span>';
    } else {
      expiryHtml = '<span class="text-dim">—</span>';
    }

    html += '<tr>';
    html += '<td class="text-center"><span class="health-mark ' + toneVar(hColor) + '">' + healthLabels[d.health] + '</span></td>';
    html += '<td class="fw-medium">' + esc(d.domain) + '</td>';
    html += '<td>' + esc(d.customer_name) + '</td>';
    html += '<td class="text-center">' + sslHtml + '</td>';
    html += '<td class="text-center">' + (d.has_spf ? chkY : chkN) + '</td>';
    html += '<td class="text-center">' + (d.has_dkim ? chkY : chkN) + '</td>';
    html += '<td class="text-center">' + (d.has_dmarc ? chkY : chkN) + '</td>';
    html += '<td class="text-center text-muted">' + esc(String(d.dns_records)) + '</td>';
    html += '<td class="text-center text-xs">' + expiryHtml + '</td>';
    html += '</tr>';
  });

  html += '</tbody></table></div>';
  el.innerHTML = html + chainHtml;
}


// ═══════════════════════════════════════════════════════════════════
// DASHBOARD AUTO-REFRESH
// ═══════════════════════════════════════════════════════════════════

var _dashRefreshInterval = null;
var _dashRefreshSeconds = 120; // 2 minutes

// The ↻ in Oversikt's tab bar: lit and pressed while the refresh runs. It
// used to swap its glyph for "Auto-refresh: 2m", and leaving Oversikt stopped
// the timer but left the button saying it was on.
function _dashPaintAutoRefresh(on) {
  var btn = document.getElementById('dash-autorefresh-btn');
  if (!btn) return;
  btn.classList.toggle('accent', on);
  btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  btn.title = on ? t('btn_auto_refresh_on') : t('tip_auto_refresh');
}

export function stopDashRefreshInterval() {
  if (_dashRefreshInterval) { clearInterval(_dashRefreshInterval); _dashRefreshInterval = null; }
  _dashPaintAutoRefresh(false);
}

export function dashToggleAutoRefresh() {
  if (_dashRefreshInterval) { stopDashRefreshInterval(); return; }
  _dashRefreshInterval = setInterval(function() {
    var active = document.querySelector('#view-overview .tab.active');
    if (active && currentView === 'overview') active.click();
  }, _dashRefreshSeconds * 1000);
  _dashPaintAutoRefresh(true);
}


// ═══════════════════════════════════════════════════════════════════
// CSV EXPORT FOR DASHBOARD TABLES
// ═══════════════════════════════════════════════════════════════════

function _dashExportTableCSV(containerId, filename) {
  var el = document.getElementById(containerId);
  if (!el) return;
  var table = el.querySelector('table');
  if (!table) { showToast(t('err_no_data','No data to export'), 'error'); return; }

  var rows = [];
  table.querySelectorAll('tr').forEach(function(tr) {
    var cells = [];
    tr.querySelectorAll('th, td').forEach(function(td) {
      cells.push(csvCell(td.textContent.trim()));
    });
    if (cells.length) rows.push(cells.join(';'));
  });

  var csv = '\uFEFF' + rows.join('\n'); // BOM for Excel
  var blob = new Blob([csv], {type: 'text/csv;charset=utf-8;'});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = (filename || 'export') + '_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
  URL.revokeObjectURL(url);
  showToast(t('msg_exported','Exported') + ' ' + a.download, 'success', 2000);
}

function dashExportAlerts() { _dashExportTableCSV('dash-alerts-content', 'alerts'); }

// Oversikt on one of its tabs.
export function openOverviewTab(tabId) {
  if (currentView !== 'overview') showView('overview');
  var btn = document.querySelector('#view-overview .tab[data-tab="' + tabId + '"]');
  if (btn) switchDashTab(btn, tabId);
}

// ── Lisenser og hosting (Verktøy, billing module) ───────────────────────────
// Fornyelser, Kostnader and Domener were dashboard tabs; they are distributor
// finance, not "who needs me today", so they are a tool of their own.
var _billingTab = 'dash-renewals';

export function switchBillingTab(btn, tabId) {
  _billingTab = tabId;
  document.querySelectorAll('#view-billing .billing-tab-btn').forEach(function(b) {
    var on = b.dataset.tab === tabId;
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  document.querySelectorAll('#view-billing .billing-tab-content').forEach(function(p) { p.hidden = p.id !== tabId; });
  // Fornyelser carries its own export among its tools; one is enough.
  var exp = document.getElementById('billing-export');
  if (exp) exp.hidden = tabId === 'dash-renewals';
  if (tabId === 'dash-renewals') dashLoadRenewals();
  if (tabId === 'dash-costs') dashLoadCosts();
  if (tabId === 'dash-domains') dashLoadDomains();
}

function showBillingTab(tabId) {
  if (currentView !== 'billing') showView('billing');
  var btn = document.querySelector('#view-billing .billing-tab-btn[data-tab="' + tabId + '"]');
  if (btn) switchBillingTab(btn, tabId);
}

onViewShown('billing', function() { showBillingTab(_billingTab); });

export function billingExportCurrentTab() {
  var names = {'dash-renewals': 'renewals', 'dash-costs': 'costs', 'dash-domains': 'domains'};
  _dashExportTableCSV(_billingTab + '-content', names[_billingTab] || 'export');
}

// Navigate to customer detail view from dashboard tables
function showCustomerDetail(customerId, customerName) {
  if (!customerId) return;
  overviewSelectCustomer(customerId);
}

export function dashExportCurrentTab() {
  var active = document.querySelector('#view-overview .dash-tab-content:not([hidden])');
  if (!active) return;
  var id = active.id;
  if (id === 'dash-alerts') dashExportAlerts();
  else if (id === 'dash-customers') _dashExportTableCSV('overview-content', 'customers');
  else showToast(t('err_no_export','Export not available for this tab'), 'info');
}


// ═══════════════════════════════════════════════════════════════════
// REPORT ARCHIVE
// ═══════════════════════════════════════════════════════════════════

export async function dashLoadArchive() {
  var el = document.getElementById('dash-archive-content');
  el.innerHTML = '<div class="loader loader-md"></div>';

  var data = await apiFetch('/api/reports/archive');
  if (!data) { el.innerHTML = '<div class="text-danger text-center p-12">' + t('dash_load_failed','Kunne ikke laste') + '</div>'; return; }

  var html = '';

  // KPI
  html += '<div class="grid grid-cols-3 gap-3 mb-4">';
  var kpis = [
    {label:t('lbl_total_reports','Rapporter'), value:Number(data.total_reports), color:'var(--blue)'},
    {label:t('lbl_customers','Kunder'), value:data.customers.length, color:'var(--text)'},
    {label:t('lbl_total_size','Størrelse'), value:Number(data.total_size_mb) + ' MB', color:'var(--text-muted)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card kpi-card ' + toneVar(k.color) + '">';
    html += '<div class="kpi-value ' + toneClass(k.color) + '">'+k.value+'</div>';
    html += '<div class="kpi-label">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // Cleanup buttons. They wrap: in one row they ran off a 375 px screen.
  html += '<div class="flex flex-wrap gap-2 mb-4">';
  html += '<button class="btn btn-ghost btn-sm" data-write data-click-handler="dashArchiveCleanup" data-months="3">'+t('btn_cleanup_3m','Delete older than 3 months')+'</button>';
  html += '<button class="btn btn-ghost btn-sm" data-write data-click-handler="dashArchiveCleanup" data-months="6">'+t('btn_cleanup_6m','Delete older than 6 months')+'</button>';
  html += '<button class="btn btn-ghost btn-sm" data-write data-click-handler="dashArchiveCleanup" data-months="12">'+t('btn_cleanup_12m','Delete older than 12 months')+'</button>';
  html += '</div>';

  if (data.customers.length === 0) {
    html += '<div class="card empty-note is-compact">'+t('msg_no_reports','No reports found.')+'</div>';
    el.innerHTML = html;
    return;
  }

  // Customer list with collapsible runs
  data.customers.forEach(function(c, idx) {
    html += '<div class="card p-0 mb-2">';
    html += '<button type="button" aria-expanded="false" data-click-handler="dashArchiveToggleRuns" class="btn btn-ghost w-full flex justify-between items-center">';
    html += '<span><span class="fw-semibold">'+esc(c.customer_name)+'</span> <span class="text-sm text-muted">('+Number(c.run_count)+' '+t('lbl_reports','reports')+', '+Number(c.total_size_mb)+' MB)</span></span>';
    html += '<span class="chevron text-2xs text-dim transition-transform">&#9660;</span>';
    html += '</button>';
    html += '<div class="border-t overflow-x-auto" style="display:none;">';
    html += '<table class="data-table">';
    html += '<thead><tr><th>'+t('lbl_date','Date')+'</th><th class="text-center">'+t('lbl_files','Files')+'</th><th class="text-center">'+t('lbl_size','Size')+'</th><th class="text-center">PDF</th><th class="text-center">HTML</th><th class="text-right"></th></tr></thead><tbody>';
    c.runs.forEach(function(r) {
      html += '<tr>';
      html += '<td>'+esc(r.date || r.name)+'</td>';
      html += '<td class="text-center">'+Number(r.file_count)+'</td>';
      html += '<td class="text-center">'+Number(r.size_mb)+' MB</td>';
      html += '<td class="text-center">'+(r.has_pdf ? '<span class="text-success">&#10003;</span>' : '<span class="text-dim">-</span>')+'</td>';
      html += '<td class="text-center">'+(r.has_html ? '<span class="text-success">&#10003;</span>' : '<span class="text-dim">-</span>')+'</td>';
      html += '<td class="text-right"><button class="btn btn-ghost btn-sm text-danger" data-write data-click-handler="dashArchiveDelete" data-path="'+esc(r.path)+'">'+t('btn_delete','Delete')+'</button></td>';
      html += '</tr>';
    });
    html += '</tbody></table></div></div>';
  });

  el.innerHTML = html;
}

async function dashArchiveDelete(path) {
  if (!await showConfirm(t('confirm_delete_report','Delete this report permanently?'))) return;
  var d = await apiFetch('/api/reports/archive/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({path:path})});
  if (d && d.ok) {
    showToast(t('msg_deleted','Deleted'), 'success', 2000);
    dashLoadArchive();
  } else {
    showToast((d && d.error) || t('status_error'), 'error');
  }
}

export async function generateQBR() {
  showToast(t('msg_generating','Generating...'), 'info', 2000);
  try {
    var r = await apiFetch('/api/reports/batch-summary', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({})});
    if (!r) { showToast(t('status_error'), 'error'); return; }
    if (r.error) { showToast(r.error, 'error'); return; }
    var report = r._raw || '';
    if (!report) { showToast(t('err_no_data','No data'), 'error'); return; }
    // A blob: URL would inherit the app's origin; the report carries tenant names.
    openReportWindow(report, t('qbr_rapport', 'QBR report'));
    showToast(t('msg_qbr_generated','QBR report opened — use Ctrl+P to save as PDF'), 'success', 5000);
  } catch(e) { showToast(t('status_error') + ': ' + e.message, 'error'); }
}

async function dashArchiveCleanup(months) {
  // Asked in the page's own dialog; it was the browser's confirm().
  if (!await showConfirm(t('dlg_cleanup_reports').replace('{months}', months), t('dlg_cleanup_reports_body'))) return;
  var d = await apiFetch('/api/reports/archive/cleanup', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({months:months})});
  if (d && d.ok) {
    showToast(d.deleted + ' ' + t('msg_reports_deleted','reports deleted') + ' (' + d.freed_mb + ' MB)', 'success', 3000);
    dashLoadArchive();
  } else {
    showToast((d && d.error) || t('status_error'), 'error');
  }
}

// ═══════════════════════════════════════════════════════════════════
// DASHBOARD OVERVIEW + CHARTS + HEALTH STRIP — carved out of app.js
// ═══════════════════════════════════════════════════════════════════

// ── Multi-customer dashboard overview ────────────────────────────────────────
// Worst open finding first: who needs attention leads.
let _overviewSortKey = 'open_findings';
let _overviewSortAsc = false;

// A row's ⋯ opens its menu and, pressed again, closes it. It only ever
// opened: the second click closed every menu and opened this one again.
function _closeRowActions(except) {
  document.querySelectorAll('.row-actions-menu').forEach(function(m) {
    if (m === except) return;
    m.hidden = true;
    var btn = m.previousElementSibling;
    if (btn) btn.setAttribute('aria-expanded', 'false');
  });
}
function toggleRowActions(btn) {
  var menu = btn.nextElementSibling;
  _closeRowActions(menu);
  menu.hidden = !menu.hidden;
  btn.setAttribute('aria-expanded', menu.hidden ? 'false' : 'true');
}
// Close row action menus on outside click
document.addEventListener('click', function(e) {
  if (!e.target.closest('.row-actions-wrap')) _closeRowActions(null);
});

async function quickSwitchAndAudit(customerId) {
  _closeRowActions(null);
  await openCustomerPage(customerId, 'audit');
  startAudit();
}
async function quickSwitchAndView(customerId, tab) {
  _closeRowActions(null);
  await openCustomerPage(customerId, tab);
}



// ── Integrations: one banner when a configured one is failing ───────────
// Oversikt answers "who needs me today". A strip of every integration's
// state answered "how is the installation", which is Administrasjon's
// question; what belongs here is the one thing that does need someone: an
// integration that is set up and has started failing.
async function loadIntegrationHealthStrip() {
  var widget = document.getElementById('integration-health-widget');
  if (!widget) return;
  var schedRes = await apiFetch('/api/scheduler/tasks').catch(function() { return null; });
  var failing = ((schedRes && schedRes.tasks) || []).filter(function(task) {
    return task.enabled !== false && Number(task.consecutive_failures) > 0;
  });
  if (!failing.length) { widget.hidden = true; widget.innerHTML = ''; return; }
  var names = failing.map(function(task) { return _taskSchedLabel(task); });
  widget.innerHTML = '<div class="integ-failing-banner">'
    + '<span>' + esc(t('msg_integrations_failing', 'Planlagte oppgaver feiler: {tasks}.').replace('{tasks}', names.join(', '))) + '</span>'
    + adminSignpostButton('alerts', 'btn_open_scheduled_tasks')
    + '</div>';
  widget.hidden = false;
}

export async function loadOverview() {
  const box = document.getElementById('overview-content');
  // Independent of the customer list: a failing settings call must not
  // delay or break it.
  loadIntegrationHealthStrip().catch(function(e) { console.debug('integration banner failed:', e); });
  const d = await apiFetch('/api/dashboard/overview');
  if (d) {
    setOverviewData({customers: d.customers || []});
    filterOverview();
    // Update footer stats
    var fs = document.getElementById('footer-stats');
    if (fs) {
      var tc = _overviewData.customers.length;
      var wm = _overviewData.customers.filter(function(c){return c.has_metrics}).length;
      var tw = _overviewData.customers.reduce(function(s,c){return s + (c.has_metrics && c.metrics.total_warns ? c.metrics.total_warns : 0)}, 0);
      fs.textContent = t('footer_stats', '{customers} kunder · {audited} auditert · {warns} advarsler')
        .replace('{customers}', tc).replace('{audited}', wm).replace('{warns}', tw);
    }
  } else {
    box.innerHTML = '<div class="alert alert-error">' + t('err_could_not_load_dashboard') + '</div>';
  }
}

// ── Who needs attention ─────────────────────────────────────────────────
// One definition, shared by the attention strip and the "Vis kun disse"
// filter, so the two cannot drift apart. A customer needs attention when it
// has an open critical or high finding, when its last audit found a poor
// result, when it has never been audited, or when that audit is older than
// _STALE_DAYS: a customer nobody has looked at is not a customer without
// problems.
var _STALE_DAYS = 30;

// Run directories are named "YYYY-MM-DD_HHMM" (older) or
// "YYYY-MM-DD_HHMMSS_ffffff_<id>" (UTC, current). Turning the underscore into
// a "T" gave "2026-10-02T1430", which Date cannot parse: every age came out
// NaN, so no audited customer was ever counted as stale.
function _auditAgeDays(c) {
  var m = /^(\d{4})-(\d{2})-(\d{2})(?:_(\d{2})(\d{2}))?/.exec((c && c.last_audit) || '');
  if (!m) return null;
  var when = Date.UTC(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0));
  return (Date.now() - when) / 86400000;
}

function _auditIsStale(c) {
  var age = _auditAgeDays(c);
  return age !== null && age > _STALE_DAYS;
}

// Unmeasured metrics arrive as null, and null < 80 is true in JavaScript, so a
// tenant without MFA data used to count as "MFA under 80 %".
function _poorResult(m) {
  if (!m) return false;
  return m.risk_grade === 'D' || m.risk_grade === 'F'
    || (typeof m.mfa_coverage_pct === 'number' && m.mfa_coverage_pct < 80);
}

function _openFindings(c) {
  return c.open_findings || {critical: 0, high: 0, medium: 0, low: 0};
}

function _hasUrgentFindings(c) {
  var f = _openFindings(c);
  return f.critical > 0 || f.high > 0;
}

function _needsAttention(c) {
  return !c.has_metrics || _hasUrgentFindings(c) || _poorResult(c.metrics) || _auditIsStale(c);
}

// The order of the list: worst open finding first. A customer never audited
// ranks just below one with a high finding: nobody knows what it holds, which
// is more urgent than a list of medium ones.
export function _findingWeight(c) {
  if (!c.has_metrics) return 9999;
  var f = _openFindings(c);
  return f.critical * 1e6 + f.high * 1e4 + f.medium * 1e2 + f.low;
}

export var _gradeFilter = '';

export function clearGradeFilter() {
  _gradeFilter = '';
  filterOverview();
}
var _quickFilter = 'all';
// The overview table's page, 1-based; unset until the table has rendered.
var _dashPage;
function filterByGrade(grade) {
  if (_gradeFilter === grade) { _gradeFilter = ''; } // toggle off
  else { _gradeFilter = grade; }
  filterOverview();
  if (_gradeFilter) showToast(t('lbl_grade') + ': ' + _gradeFilter, 'info', 1500);
}

function filterOverview() {
  if (!_overviewData) return;
  const search = (document.getElementById('overview-search')?.value || '').toLowerCase();
  var qf = _quickFilter || 'all';
  let filtered = _overviewData.customers.filter(c => {
    if (search && !c.customer_name.toLowerCase().includes(search) && !(c.primary_domain||'').toLowerCase().includes(search)) return false;
    if (_gradeFilter && (!c.has_metrics || c.metrics.risk_grade !== _gradeFilter)) return false;
    if (qf === 'attention' && !_needsAttention(c)) return false;
    return true;
  });
  renderOverview(filtered);

  // Show active filter badges
  var afEl = document.getElementById('overview-active-filters');
  if (afEl) {
    var badges = [];
    if (search) badges.push('<button type="button" class="filter-badge" data-click-handler="dashClearSearchFilter">&#10005; &quot;' + esc(search) + '&quot;</button>');
    if (_gradeFilter) badges.push('<button type="button" class="filter-badge" data-click-handler="dashClearGradeFilter">&#10005; ' + esc(t('lbl_grade') + ': ' + _gradeFilter) + '</button>');
    // Set by "Vis kun disse" on the attention strip. Without a badge the list
    // stayed narrowed with nothing on screen saying so.
    if (qf === 'attention') badges.push('<button type="button" class="filter-badge" id="overview-attention-badge">&#10005; ' + esc(t('lbl_needs_attention')) + '</button>');
    if (badges.length > 0) {
      badges.push('<button type="button" class="filter-clear" data-click-handler="dashClearAllFilters">' + esc(t('btn_clear_all','Clear all')) + '</button>');
      afEl.hidden = false;
      afEl.innerHTML = badges.join('');
      var attnBadge = document.getElementById('overview-attention-badge');
      if (attnBadge) attnBadge.addEventListener('click', function() { _quickFilter = 'all'; filterOverview(); });
    } else {
      afEl.hidden = true;
      afEl.innerHTML = '';
    }
  }
}

function sortOverview(key) {
  if (_overviewSortKey === key) _overviewSortAsc = !_overviewSortAsc;
  // Names A to Z; findings and MFA worst first.
  else { _overviewSortKey = key; _overviewSortAsc = key === 'customer_name' || key === 'mfa_coverage_pct'; }
  filterOverview();
}

// The open findings of a customer as one chip per severity that has any.
function _openFindingChips(c) {
  if (!c.has_metrics) return '<span class="sev-count sev-unknown">' + esc(t('lbl_never_audited', 'Aldri auditert')) + '</span>';
  var f = _openFindings(c);
  var labels = {critical: t('sev_critical', 'Kritisk'), high: t('sev_high', 'Høy'), medium: t('sev_medium', 'Middels'), low: t('sev_low', 'Lav')};
  var chips = ['critical', 'high', 'medium', 'low'].filter(function(s) { return f[s] > 0; }).map(function(s) {
    return '<span class="sev-count sev-' + s + '">' + esc(labels[s]) + ' ' + Number(f[s]) + '</span>';
  });
  return chips.length ? chips.join('') : '<span class="sev-count sev-none">' + esc(t('lbl_no_open_findings', 'Ingen åpne')) + '</span>';
}

function renderOverview(customers) {
  const box = document.getElementById('overview-content');

  // Sort: worst open finding first unless the person chose otherwise.
  const sk = _overviewSortKey;
  customers.sort((a, b) => {
    let va, vb;
    if (sk === 'customer_name') { va = a.customer_name.toLowerCase(); vb = b.customer_name.toLowerCase(); }
    else if (sk === 'open_findings') { va = _findingWeight(a); vb = _findingWeight(b); }
    else {
      va = a.has_metrics && typeof a.metrics[sk] === 'number' ? a.metrics[sk] : 1e9;
      vb = b.has_metrics && typeof b.metrics[sk] === 'number' ? b.metrics[sk] : 1e9;
    }
    const cmp = va < vb ? -1 : va > vb ? 1 : 0;
    return _overviewSortAsc ? cmp : -cmp;
  });

  // The strip counts every customer, not the ones the search or a quick
  // filter left on screen: typing a name changed "N kunder trenger
  // oppfølging", which is a fact about the portfolio, not about the list.
  const all = (_overviewData && _overviewData.customers) || customers;
  const total = all.length;
  const withMetrics = all.filter(c => c.has_metrics);
  const needsAttention = all.filter(_needsAttention).length;
  const neverAudited = total - withMetrics.length;
  const staleCount = withMetrics.filter(_auditIsStale).length;

  // The toolbar is built once, so the search field keeps its focus and value.
  if (!document.getElementById('overview-search-bar')) {
    box.innerHTML = `
    <div id="overview-summary"></div>
    <div id="overview-search-bar">
      <div class="dash-toolbar">
        <input id="overview-search" type="text" class="field-input overview-search" placeholder="${esc(t('lbl_search_customer'))}" aria-label="${esc(t('lbl_search_customer'))}" data-input-handler="filterOverview">
        <div class="dash-toolbar-spacer"></div>
        <button class="btn btn-default btn-sm" data-write id="bulk-audit-btn" data-click-handler="startBulkAudit">${esc(t('btn_run_all_customers'))}</button>
      </div>
      <div id="bulk-audit-panel" hidden></div>
    </div>
    <div id="overview-active-filters" class="overview-filters" hidden></div>
    <div id="overview-table-content"></div>`;
  }

  var tableBox = document.getElementById('overview-table-content') || box;

  // Who needs me today, and why: the parts overlap (an old audit can also
  // hold a critical finding), so the title counts customers, not reasons.
  var summaryHtml = '';
  if (needsAttention > 0) {
    var crit = withMetrics.filter(function(c) { return _openFindings(c).critical > 0; }).length;
    var high = withMetrics.filter(function(c) { var f = _openFindings(c); return !f.critical && f.high > 0; }).length;
    var lowMfa = withMetrics.filter(function(c) { return typeof c.metrics.mfa_coverage_pct === 'number' && c.metrics.mfa_coverage_pct < 80; }).length;
    var parts = [];
    if (crit) parts.push(crit + ' ' + t('attn_critical', 'med kritiske funn'));
    if (high) parts.push(high + ' ' + t('attn_high', 'med høye funn'));
    if (lowMfa) parts.push(lowMfa + ' ' + t('attn_low_mfa'));
    if (neverAudited) parts.push(neverAudited + ' ' + t('attn_no_audit'));
    if (staleCount) parts.push(staleCount + ' ' + t('attn_stale'));
    summaryHtml = `
      <div class="attn-strip${crit || high ? '' : ' attn-strip--gaps'}">
        <span class="attn-title" data-count="${Number(needsAttention)}">${Number(needsAttention)} ${esc(t('lbl_needs_followup', 'kunder trenger oppfølging'))}</span>
        <span class="attn-detail">${esc(parts.join(' · '))}</span>
        <div class="dash-toolbar-spacer"></div>
        <button class="attn-action" data-click-handler="dashSetQuickFilter" data-quick-filter="attention">${esc(t('btn_show_only_these', 'Vis kun disse'))}</button>
      </div>`;
  } else if (total > 0) {
    summaryHtml = '<div class="attn-strip attn-strip--clear"><span class="attn-title" data-count="0">' + esc(t('msg_nobody_needs_you', 'Ingen kunder har åpne kritiske eller høye funn, og alle er auditert den siste måneden.')) + '</span></div>';
  }
  var sumBox = document.getElementById('overview-summary');
  if (sumBox) sumBox.innerHTML = summaryHtml;

  let html = '';
  if (customers.length === 0) {
    html += `
      <div class="card empty-signpost">
        <p>${esc(_overviewData && _overviewData.customers.length ? t('msg_no_results', 'Ingen treff') : t('msg_no_customers_registered'))}</p>
        ${_overviewData && _overviewData.customers.length ? '' : '<button class="btn btn-primary" data-click-handler="showView" data-view="customers">' + esc(t('btn_add_first_customer')) + '</button>'}
      </div>`;
    tableBox.innerHTML = html;
    return;
  }

  var arrow = function(key) { return _overviewSortKey === key ? (_overviewSortAsc ? ' ▲' : ' ▼') : ''; };
  html += `
    <div class="card overview-table-wrap">
      <table class="slim-table customer-overview-table">
        <thead>
          <tr>
            <th class="sortable"><button type="button" class="btn btn-ghost btn-sm" data-click-handler="sortOverview" data-sort="customer_name">${esc(t('lbl_customer'))}${arrow('customer_name')}</button></th>
            <th class="sortable"><button type="button" class="btn btn-ghost btn-sm" data-click-handler="sortOverview" data-sort="open_findings">${esc(t('hdr_open_findings', 'Åpne funn'))}${arrow('open_findings')}</button></th>
            <th class="num sortable"><button type="button" class="btn btn-ghost btn-sm" data-click-handler="sortOverview" data-sort="mfa_coverage_pct">MFA${arrow('mfa_coverage_pct')}</button></th>
            <th>${esc(t('lbl_last_audit'))}</th>
            <th class="overview-menu-col"></th>
          </tr>
        </thead>
        <tbody>`;

  // Pagination
  var _pageSize = 25;
  var _totalPages = Math.ceil(customers.length / _pageSize);
  if (!_dashPage || _dashPage > _totalPages) _dashPage = 1;
  var _startIdx = (_dashPage - 1) * _pageSize;
  var _pagedCustomers = customers.slice(_startIdx, _startIdx + _pageSize);

  for (const c of _pagedCustomers) {
    const m = c.metrics || {};
    const hasM = c.has_metrics;
    const grade = hasM ? (m.risk_grade || '-') : '-';
    const mfa = hasM && metricPct(m.mfa_coverage_pct) !== null ? metricPct(m.mfa_coverage_pct) + '%' : '-';
    const mfaClass = !hasM || typeof m.mfa_coverage_pct !== 'number' ? 'is-unknown' : m.mfa_coverage_pct >= 95 ? 'is-good' : m.mfa_coverage_pct >= 80 ? 'is-warn' : 'is-bad';
    const lastAudit = c.last_audit ? formatRunName(c.last_audit, true) : '-';
    const age = _auditAgeDays(c);
    const ageNote = !c.last_audit ? ''
      : _auditIsStale(c) ? '<span class="overview-age is-stale">' + esc(Math.floor(age) + 'd ' + t('lbl_since_audit', 'siden audit')) + '</span>' : '';

    html += `
          <tr data-click-handler="dashOverviewSelectCustomer" data-customer-id="${esc(c.customer_id)}"
              title="${esc(t('tip_click_to_open_customer', 'Åpne kunden'))}">
            <td>
              <div class="cust-cell">
                <button type="button" class="grade-tile grade-${esc(grade.replace('-', 'none'))}" data-click-handler="dashFilterByGrade" data-grade="${esc(grade)}" title="${esc(t('tip_click_filter_grade','Click to filter by grade'))}">${esc(grade)}</button>
                <span class="cust-cell-text">
                  <span class="cname">${esc(c.customer_name)}</span>
                  <span class="cdom">${esc(c.primary_domain || '')}</span>
                </span>
              </div>
            </td>
            <td><span class="sev-counts">${_openFindingChips(c)}</span></td>
            <td class="num overview-mfa ${mfaClass}">${esc(mfa)}</td>
            <td class="overview-last">${esc(lastAudit)}${ageNote}</td>
            <td class="overview-menu-col">
              <div class="row-actions-wrap">
                <button class="row-actions-btn" data-click-handler="dashToggleRowActions" aria-haspopup="true" aria-expanded="false" aria-label="${esc(t('lbl_more_actions', 'Flere handlinger'))}">&#8943;</button>
                <div class="row-actions-menu" hidden>
                  <button class="hover-menu-item" data-click-handler="dashRowDetails" data-customer-id="${esc(c.customer_id)}">${esc(t('btn_open_customer', 'Åpne kunde'))}</button>
                  <button class="hover-menu-item" data-write data-click-handler="dashRowAudit" data-customer-id="${esc(c.customer_id)}">${esc(t('btn_run_audit'))}</button>
                  <button class="hover-menu-item" data-click-handler="dashRowHistory" data-customer-id="${esc(c.customer_id)}">${esc(t('hdr_runs', 'Kjøringer'))}</button>
                  <button class="hover-menu-item" data-click-handler="dashRowReport" data-customer-id="${esc(c.customer_id)}">${esc(t('btn_summary_report', 'Sammendragsrapport'))}</button>
                  <div class="row-actions-sep"></div>
                  <button class="hover-menu-item-danger" data-write data-click-handler="dashRowArchive" data-customer-id="${esc(c.customer_id)}" data-customer-name="${esc(c.customer_name)}">${esc(t('btn_archive','Archive'))}</button>
                </div>
              </div>
            </td>
          </tr>`;
  }
  html += `
        </tbody>
      </table>
    </div>`;

  if (_totalPages > 1) {
    html += '<div class="overview-pager">'
      + '<button class="btn btn-ghost btn-sm" data-click-handler="dashPagePrev" ' + (_dashPage <= 1 ? 'disabled' : '') + '>&laquo; ' + esc(t('btn_prev','Prev')) + '</button>'
      + '<span>' + Number(_dashPage) + ' / ' + Number(_totalPages) + '</span>'
      + '<button class="btn btn-ghost btn-sm" data-click-handler="dashPageNext" data-total-pages="' + Number(_totalPages) + '" ' + (_dashPage >= _totalPages ? 'disabled' : '') + '>' + esc(t('btn_next','Next')) + ' &raquo;</button>'
      + '</div>';
  }

  tableBox.innerHTML = html;
  // Stamp "Oppdatert HH:MM" in the tab bar.
  var _updT = document.getElementById('dash-updated-time');
  if (_updT) {
    _updT.textContent = new Date().toLocaleTimeString('no-NO', {hour:'2-digit', minute:'2-digit'});
    var _updW = document.getElementById('dash-updated-wrap');
    if (_updW) _updW.hidden = false;
  }
}
