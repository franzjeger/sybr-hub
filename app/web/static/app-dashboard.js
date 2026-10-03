// ═══════════════════════════════════════════════════════════════════
// ALERTS DASHBOARD — MORNING OVERVIEW
// ═══════════════════════════════════════════════════════════════════

// Handlers for the markup this file builds (see registerUiHandlers in app.js).
registerUiHandlers({
  // Notification centre
  notifSetSevFilter: function(el) { notifSetFilter('sev', el.dataset.sev); },
  notifSetFilter: function(el) { notifSetFilter(el.dataset.kind, el.value); },
  notifMarkAllRead: function() { notifMarkAllRead(); },
  notifOpenRules: function() { notifOpenRules(); },
  notifAct: function(el) { notifAct(el.dataset.id); },
  notifActReadOnly: function(el) { notifAct(el.dataset.id, true); },
  notifToggleRule: function(el) { notifToggleRule(el.dataset.key, el.checked); },
  // Report archive
  dashArchiveCleanup: function(el) { dashArchiveCleanup(Number(el.dataset.months)); },
  dashArchiveDelete: function(el) { dashArchiveDelete(el.dataset.path); },
  dashArchiveToggleRuns: function(el) {
    el.nextElementSibling.style.display = el.nextElementSibling.style.display === 'none' ? 'block' : 'none';
    el.querySelector('.chevron').classList.toggle('open');
  },
  // Customer overview: toolbar, filter badges, sorting and pagination
  filterOverview: function() { filterOverview(); },
  dashSetQuickFilter: function(el) { _quickFilter = el.dataset.quickFilter; filterOverview(); },
  dashClearSearchFilter: function() { document.getElementById('overview-search').value = ''; filterOverview(); },
  dashClearTypeFilter: function() { document.getElementById('overview-filter').value = 'all'; filterOverview(); },
  dashClearGradeFilter: function() { _gradeFilter = ''; filterOverview(); },
  dashClearAllFilters: function() {
    document.getElementById('overview-search').value = '';
    document.getElementById('overview-filter').value = 'all';
    _gradeFilter = '';
    _quickFilter = 'all';
    filterOverview();
  },
  startBulkAudit: function() { startBulkAudit(); },
  toggleOverviewColpick: function(el, event) { toggleOverviewColpick(event); },
  toggleOverviewColumn: function(el) { toggleOverviewColumn(el.dataset.col, el.checked); },
  sortOverview: function(el) { sortOverview(el.dataset.sort); },
  dashPagePrev: function() { window._dashPage = Math.max(1, window._dashPage - 1); filterOverview(); },
  dashPageNext: function(el) { window._dashPage = Math.min(Number(el.dataset.totalPages), window._dashPage + 1); filterOverview(); },
  // Customer overview rows. The controls inside a row stop the click so the
  // row's own handler does not open the customer as well.
  dashOverviewSelectCustomer: function(el) { overviewSelectCustomer(el.dataset.customerId); },
  dashRowQuickAudit: function(el, event) { event.preventDefault(); quickSwitchAndAudit(el.dataset.customerId); },
  dashFilterByGrade: function(el, event) { event.stopPropagation(); filterByGrade(el.dataset.grade); },
  dashToggleRowActions: function(el, event) { event.stopPropagation(); toggleRowActions(el); },
  dashRowDetails: function(el, event) { event.stopPropagation(); overviewSelectCustomer(el.dataset.customerId); },
  dashRowAudit: function(el, event) { event.stopPropagation(); quickSwitchAndAudit(el.dataset.customerId); },
  dashRowHistory: function(el, event) { event.stopPropagation(); quickSwitchAndView(el.dataset.customerId, 'history'); },
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
  (window._notifItems || []).forEach(function(n) { _notifMarkRead(n.id); });
  _notifRender();
}

function notifSetFilter(kind, value) {
  _notifState[kind] = value;
  _notifRender();
}

function notifOpenRules() {
  // Rules, thresholds and delivery channels are edited under "Automatiske
  // varsler" on the Integrations page. This used to open a 'settings' view,
  // which does not exist: every view was hidden and the screen went blank.
  showView('integrations');
  // The card sits inside a wrapper that also holds its heading; land on that.
  // Not smooth: the cards above repaint as their status loads, which cut a
  // smooth scroll short halfway down the page.
  var toggle = document.getElementById('alert-master-toggle');
  var card = toggle && toggle.closest('.card');
  var section = card && card.parentElement;
  if (!section) return;
  requestAnimationFrame(function() {
    section.scrollIntoView({block: 'start'});
    toggle.focus({preventScroll: true});
  });
}

// Severity vocabulary, shared by the chips, the dots and the badges so a
// colour never means two things in one screen.
var _SEV = {
  critical: { label: 'Kritisk', color: 'var(--red-deep)',    dot: 'var(--red)',    tint: 'color-mix(in srgb, var(--red) 12%, transparent)' },
  warning:  { label: 'Advarsel', color: 'var(--orange-deep)', dot: 'var(--orange)', tint: 'color-mix(in srgb, var(--orange) 12%, transparent)' },
  info:     { label: 'Info',     color: 'var(--text-muted)',  dot: 'var(--text-dim)', tint: 'color-mix(in srgb, var(--text-muted) 12%, transparent)' }
};

function _notifDays(n) {
  if (n === null || n === undefined) return '';
  return n < 0 ? t('lbl_expired', 'Utløpt') : n + ' ' + t('lbl_days_short', 'd');
}

async function dashLoadAlerts() {
  var el = document.getElementById('dash-alerts-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';

  // Three sources, fetched together. Uniweb is optional — a customer without
  // it configured is not an error, so its failure narrows the stream rather
  // than emptying the screen.
  var res = await Promise.all([
    apiFetch('/api/dashboard/alerts'),
    apiFetch('/api/uniweb/alerts').catch(function() { return null; }),
    apiFetch('/api/alerts/config').catch(function() { return null; })
  ]);
  var data = res[0], uniweb = res[1], cfg = res[2];

  if (!data) {
    el.innerHTML = '<div class="alert alert-error">' + t('msg_alerts_failed', 'Kunne ikke hente varsler.') + '</div>';
    return;
  }

  window._notifItems = _notifCollect(data, uniweb);
  window._notifConfig = cfg;
  _notifRender();
}

// Flatten the three shapes into one. Each item carries the id its read state
// is keyed on, which has to be stable across reloads — so it is built from
// what identifies the alert, never from its position in the list.
function _notifCollect(data, uniweb) {
  var out = [];

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

  // Soonest first inside every group, expired at the top.
  out.sort(function(a, b) {
    var x = (a.days === null || a.days === undefined) ? 9e9 : a.days;
    var y = (b.days === null || b.days === undefined) ? 9e9 : b.days;
    return x - y;
  });
  return out;
}

function _notifRender() {
  var el = document.getElementById('dash-alerts-content');
  if (!el) return;
  var items = window._notifItems || [];

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
    var col = key === 'all' ? 'var(--text)' : _SEV[key].color;
    html += '<button class="sev-chip' + (_notifState.sev === key ? ' active' : '') + '"'
         + ' style="color:' + col + ';" data-click-handler="notifSetSevFilter" data-sev="' + esc(key) + '">'
         + esc(p[1]) + ' <b>' + counts[key] + '</b></button>';
  });
  html += _notifSelect('source', t('lbl_source', 'Kilde'), Object.keys(sources));
  html += _notifSelect('customer', t('col_customer', 'Kunde'), Object.keys(customers));
  html += '<div style="flex:1;"></div>';
  html += '<button class="btn btn-default" style="font-size:12px;padding:5px 12px;color:var(--blue);border-color:transparent;" data-click-handler="notifMarkAllRead">' + t('btn_mark_all_read', 'Marker alle som lest') + '</button>';
  html += '<button class="btn btn-default" style="font-size:12px;padding:5px 12px;" data-click-handler="notifOpenRules">'
       + t('btn_alert_rules', 'Varslingsregler') + '</button>';
  html += '</div>';

  html += '<div class="notif-grid"><div>';
  if (!shown.length) {
    html += '<div class="notif-card" style="text-align:center;padding:40px;color:var(--text-muted);">'
         + (items.length
             ? t('msg_no_alerts_in_filter', 'Ingen varsler i dette filteret.')
             : t('msg_all_clear', 'Ingenting krever handling. Ingen legitimasjon, fornyelser eller domener utløper innen 30 dager.'))
         + '</div>';
  } else {
    // Urgency bands, not calendar days: these alerts describe what is about
    // to happen, so the useful grouping is how soon.
    var bands = [
      { title: t('grp_now', 'Krever handling nå'), test: function(n) { return n.days !== null && n.days !== undefined && n.days <= 7; } },
      { title: t('grp_month', 'Innen 30 dager'),   test: function(n) { return n.days !== null && n.days !== undefined && n.days > 7; } },
      { title: t('grp_other', 'Uten frist'),       test: function(n) { return n.days === null || n.days === undefined; } }
    ];
    bands.forEach(function(b) {
      var rows = shown.filter(b.test);
      if (!rows.length) return;
      html += '<div style="margin-bottom:20px;"><div class="notif-group-label">' + esc(b.title) + ' (' + rows.length + ')</div>';
      html += '<div class="notif-list">';
      rows.forEach(function(n) { html += _notifRow(n); });
      html += '</div></div>';
    });
  }
  html += '</div>' + _notifSidebar() + '</div>';

  el.innerHTML = html;
}

function _notifSelect(kind, label, values) {
  var html = '<select class="field-input" style="font-size:12px;padding:4px 8px;width:auto;"'
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
  var html = '<div class="notif-row' + (unread ? ' unread' : '') + (n.handled ? '" style="opacity:0.5;' : '"') + '>';
  html += '<span class="notif-dot" style="background:' + sev.dot + ';"></span>';
  html += '<div class="notif-body">';
  html += '<div class="notif-head"><span class="notif-title">' + esc(n.title) + '</span>';
  html += '<span class="notif-sev" style="color:' + sev.color + ';background:' + sev.tint + ';">' + esc(sev.label.toUpperCase()) + '</span>';
  if (n.days !== null && n.days !== undefined) {
    html += '<span class="notif-sev" style="color:' + sev.color + ';background:' + sev.tint + ';">' + esc(_notifDays(n.days)) + '</span>';
  }
  html += '</div>';
  html += '<div class="notif-meta">';
  if (n.customer) html += '<span class="cust">' + esc(n.customer) + '</span>';
  html += '<span class="src">' + esc(n.source) + '</span>';
  if (n.when) html += '<span>' + esc(n.when) + '</span>';
  html += '</div></div>';
  html += '<div class="notif-actions">';
  html += '<button class="btn btn-default" style="font-size:11px;padding:4px 10px;"'
       + ' data-click-handler="notifAct" data-id="' + esc(n.id) + '">' + esc(n.action) + '</button>';
  if (unread) {
    html += '<button class="btn btn-default" style="font-size:11px;padding:4px 8px;"'
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
  var n = (window._notifItems || []).filter(function(x) { return x.id === id; })[0];
  _notifMarkRead(id);
  if (!readOnly && n) {
    if (n.act === 'customer' && typeof showCustomerDetail === 'function' && n.customerId) {
      showCustomerDetail(n.customerId, n.customer);
      return;
    }
    if (n.act === 'domains' && hasModule('billing')) {
      var btn = document.querySelector('.dash-tab-btn[data-tab="dash-domains"]');
      if (btn) { switchDashTab(btn, 'dash-domains'); return; }
    }
  }
  _notifRender();
}

// The rule toggles are the real ones from /api/alerts/config, not decoration.
// Writing them is admin-only server-side, so a technician sees the true state
// disabled rather than a switch that silently fails.
function _notifSidebar() {
  var cfg = window._notifConfig;
  var isAdmin = (window._currentUser && window._currentUser.role === 'admin');
  var labels = {
    ssl_expiry: t('rule_ssl_expiry', 'TLS-sertifikater'),
    domain_expiry: t('rule_domain_expiry', 'Domener'),
    fortigate_threats: t('rule_fortigate_threats', 'Brannmur-hendelser'),
    firmware_outdated: t('rule_firmware', 'Utdatert firmware'),
    also_license_expiry: t('rule_also', 'Lisensfornyelser'),
    mfa_coverage: t('rule_mfa', 'MFA-dekning'),
    pentest_critical: t('rule_pentest', 'Kritiske pentest-funn')
  };

  var html = '<div class="notif-side"><div class="notif-card"><h4>' + t('hdr_alert_rules', 'Varslingsregler') + '</h4>';
  if (!cfg) {
    html += '<div style="font-size:12px;color:var(--text-muted);">'
         + t('msg_rules_unavailable', 'Kunne ikke hente reglene.') + '</div>';
  } else {
    var rules = cfg.rules || {};
    Object.keys(labels).forEach(function(k) {
      var on = rules[k] && rules[k].enabled;
      html += '<label class="rule-row"><span>' + esc(labels[k]) + '</span>'
           + '<span class="switch"><input type="checkbox"' + (on ? ' checked' : '')
           + (isAdmin ? '' : ' disabled')
           + ' data-change-handler="notifToggleRule" data-key="' + esc(k) + '"'
           + ' aria-label="' + esc(labels[k]) + '">'
           + '<span class="track"></span><span class="knob"></span></span></label>';
    });
    if (!cfg.enabled) {
      html += '<div style="font-size:11px;color:var(--orange-deep);margin-top:10px;">'
           + t('msg_alerts_disabled', 'Automatiske varsler er slått av, så ingen av reglene sender noe. Slå dem på i Innstillinger.')
           + '</div>';
    }
    if (!isAdmin) {
      html += '<div style="font-size:11px;color:var(--text-dim);margin-top:10px;">'
           + t('msg_rules_admin_only', 'Bare administratorer kan endre reglene.') + '</div>';
    }
  }
  html += '</div>';

  html += '<div class="notif-card"><h4>' + t('hdr_delivery', 'Levering') + '</h4>';
  if (cfg) {
    var chans = [];
    if (cfg.notify_teams) chans.push('Teams');
    if (cfg.notify_email && cfg.email_recipient) chans.push(esc(cfg.email_recipient));
    html += '<div style="font-size:12px;color:var(--text-muted);line-height:1.6;">'
         + (chans.length
             ? t('msg_delivery_to', 'Varsler sendes til') + ' ' + chans.join(', ') + '.'
             : t('msg_delivery_none', 'Ingen kanal er satt opp, så varslene vises bare her.'))
         + '</div>';
  }
  html += '<div style="margin-top:10px;"><button class="btn btn-default" style="font-size:11px;padding:4px 10px;"'
       + ' data-click-handler="notifOpenRules">' + t('btn_change_channels', 'Endre kanaler') + '</button></div></div>';

  html += '<div class="notif-card"><h4>' + t('hdr_read_state', 'Lest-status') + '</h4>'
       + '<div style="font-size:12px;color:var(--text-muted);line-height:1.6;">'
       + t('msg_read_local', 'Hva du har lest lagres i denne nettleseren. En kollega som åpner den samme listen ser sin egen status.')
       + '</div></div>';

  return html + '</div>';
}

async function notifToggleRule(key, on) {
  var cfg = window._notifConfig;
  if (!cfg) return;
  var rules = JSON.parse(JSON.stringify(cfg.rules || {}));
  rules[key] = Object.assign({}, rules[key] || {}, { enabled: on });
  var saved = await apiFetch('/api/alerts/config', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ rules: rules })
  });
  // apiFetch has already said why on a failure; put the switch back rather
  // than leaving it showing a state the server did not accept.
  if (!saved) { _notifRender(); return; }
  cfg.rules = rules;
  showToast(t('msg_rule_saved', 'Regel lagret'), 'success', 2000);
}

// ═══════════════════════════════════════════════════════════════════
// DOMAIN, MAIL AND LICENCE CHAIN (shown on the Domener tab)
// ═══════════════════════════════════════════════════════════════════

// ── Domain-Email Chain section builder ──

function _buildChainSection(chainData) {
  var html = '';
  html += '<div style="margin:20px 0;">';
  html += '<div style="font-size:15px;font-weight:700;margin-bottom:10px;">'+icon('mail',16)+' '+t('hdr_domain_email_chain','Domain-Email-License')+'</div>';

  if (!chainData || !chainData.items || chainData.items.length === 0) {
    html += '<div class="card" style="padding:16px;text-align:center;color:var(--green);font-size:12px;">';
    html += '<div style="font-size:24px;margin-bottom:4px;">&#10003;</div>';
    html += t('msg_no_chain_alerts','No domain-email mismatches found.')+'</div>';
    html += '</div>';
    return html;
  }

  var s = chainData.summary || {};

  // KPI badges
  html += '<div style="display:flex;gap:12px;margin-bottom:10px;font-size:12px;">';
  if (s.double_paying > 0) html += '<span style="background:var(--orange);color:#fff;padding:3px 10px;border-radius:10px;font-weight:600;">'+Number(s.double_paying)+' '+t('lbl_double_paying','Double Paying')+'</span>';
  if (s.missing_m365 > 0) html += '<span style="background:var(--red);color:#fff;padding:3px 10px;border-radius:10px;font-weight:600;">'+Number(s.missing_m365)+' '+t('lbl_missing_m365','Missing M365')+'</span>';
  if (s.unused_m365 > 0) html += '<span style="background:var(--blue);color:#fff;padding:3px 10px;border-radius:10px;font-weight:600;">'+Number(s.unused_m365)+' '+t('lbl_unused_m365','Unused M365')+'</span>';
  html += '</div>';

  // Table
  html += '<div class="card" style="padding:0;overflow:hidden;">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="background:var(--bg-tertiary);border-bottom:2px solid var(--border);">';
  html += '<th style="text-align:left;padding:8px;">'+t('col_customer','Customer')+'</th>';
  html += '<th style="text-align:left;padding:8px;">'+t('col_domain','Domain')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_mx_exchange','MX Exchange')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_has_m365','M365')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_uniweb_email','Uniweb Email')+'</th>';
  html += '<th style="text-align:left;padding:8px;">'+t('col_alert','Alert')+'</th>';
  html += '</tr></thead><tbody>';

  var chkY = '<span style="color:var(--green);font-weight:700;font-size:14px;">&#10003;</span>';
  var chkN = '<span style="color:var(--red);font-weight:700;font-size:14px;">&#10007;</span>';

  chainData.items.forEach(function(item, i) {
    var rowBg = i % 2 === 0 ? 'transparent' : 'var(--bg-tertiary)';
    var alertHtml = '';
    item.alerts.forEach(function(a) {
      var sevColors = {critical:'var(--red)', warning:'var(--orange)', info:'var(--blue)'};
      var sevLabels = {critical:t('lbl_severity_critical','Critical'), warning:t('lbl_severity_warning','Warning'), info:t('lbl_severity_info','Info')};
      alertHtml += '<div style="margin-bottom:2px;"><span style="font-size:10px;font-weight:600;color:#fff;background:'+(sevColors[a.severity]||'var(--text-dim)')+';padding:1px 6px;border-radius:8px;">'+esc(sevLabels[a.severity]||a.severity)+'</span> <span style="font-size:11px;">'+esc(a.message)+'</span></div>';
    });

    html += '<tr style="background:'+rowBg+';border-bottom:1px solid var(--border);">';
    html += '<td style="padding:6px 8px;font-weight:500;">'+esc(item.customer_name)+'</td>';
    html += '<td style="padding:6px 8px;">'+esc(item.domain)+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;">'+(item.mx_exchange ? chkY : chkN)+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;">'+(item.has_m365 ? chkY : chkN)+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;">'+(item.has_uniweb_email ? chkY : chkN)+'</td>';
    html += '<td style="padding:6px 8px;">'+alertHtml+'</td>';
    html += '</tr>';
  });

  html += '</tbody></table></div>';
  html += '</div>';
  return html;
}

function _fmtBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  if (bytes < 1024) return Number(bytes) + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
  return (bytes / 1073741824).toFixed(2) + ' GB';
}

// ═══════════════════════════════════════════════════════════════════
// UNIFIED COST OVERVIEW — ALSO MRR + UNIWEB HOSTING
// ═══════════════════════════════════════════════════════════════════

async function dashLoadCosts() {
  var el = document.getElementById('dash-costs-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';

  var data = await apiFetch('/api/dashboard/costs');
  if (!data) { el.innerHTML = '<div style="color:var(--red);text-align:center;padding:48px;">' + t('dash_costs_load_failed','Kunne ikke laste kostnadsdata') + '</div>'; return; }

  var customers = data.customers || [];
  var totals = data.totals || {};

  if (customers.length === 0) {
    el.innerHTML = '<div class="card" style="padding:32px;text-align:center;color:var(--text-muted);"><div style="font-size:14px;font-weight:600;margin-bottom:4px;">' + t('dash_no_cost_data','Ingen kostnadsdata') + '</div><div style="font-size:12px;">' + t('dash_no_cost_hint','Synkroniser ALSO-fornyelser eller Uniweb-kontoer for å se kostnader her.') + '</div></div>';
    return;
  }

  var html = '';

  // ── KPI row ──
  html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:'Total MRR',           value:_fmtNOK(totals.total_monthly),  color:'var(--blue)'},
    {label:'ALSO MRR',            value:_fmtNOK(totals.also_mrr),       color:'#7c5cfc'},
    {label:'Uniweb manedlig',     value:_fmtNOK(totals.uniweb_monthly), color:'#e67e22'},
    {label:t('dash_customer_count','Antall kunder'), value:Number(totals.customer_count),           color:'var(--text)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card" style="padding:16px 8px;text-align:center;border-top:2px solid '+k.color+';height:90px;box-sizing:border-box;">';
    html += '<div style="font-size:20px;font-weight:700;line-height:24px;color:'+k.color+';">'+k.value+'</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);line-height:16px;">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // ── Customer cost table ──
  html += '<div class="card" style="padding:0;overflow:hidden;">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="background:var(--bg-tertiary);border-bottom:2px solid var(--border);">';
  html += '<th style="text-align:left;padding:8px;">'+t('col_customer','Kunde')+'</th>';
  html += '<th style="text-align:right;padding:8px;">'+t('col_also_mrr','ALSO MRR')+'</th>';
  html += '<th style="text-align:right;padding:8px;">'+t('col_uniweb_cost','Uniweb')+'</th>';
  html += '<th style="text-align:right;padding:8px;">'+t('col_total_cost','Total')+'</th>';
  html += '<th style="text-align:center;padding:8px;width:180px;">'+t('col_distribution','Fordeling')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_subs','Abb.')+'</th>';
  html += '</tr></thead><tbody>';

  var maxTotal = customers.length ? customers[0].total_monthly : 1;

  customers.forEach(function(c, i) {
    var rowBg = i % 2 === 0 ? 'transparent' : 'var(--bg-tertiary)';
    var alsoPct = c.total_monthly > 0 ? (c.also_mrr / c.total_monthly * 100) : 0;
    var uniwebPct = c.total_monthly > 0 ? (c.uniweb_monthly / c.total_monthly * 100) : 0;
    var barWidth = maxTotal > 0 ? Math.max((c.total_monthly / maxTotal * 100), 2) : 0;

    html += '<tr style="background:'+rowBg+';border-bottom:1px solid var(--border);">';
    html += '<td style="padding:6px 8px;font-weight:500;">'+esc(c.customer_name)+'</td>';
    html += '<td style="padding:6px 8px;text-align:right;color:#7c5cfc;font-weight:600;">'+_fmtNOK(c.also_mrr)+'</td>';
    html += '<td style="padding:6px 8px;text-align:right;color:#e67e22;font-weight:600;">'+_fmtNOK(c.uniweb_monthly)+'</td>';
    html += '<td style="padding:6px 8px;text-align:right;font-weight:700;">'+_fmtNOK(c.total_monthly)+'</td>';

    // Stacked bar
    html += '<td style="padding:6px 8px;">';
    html += '<div style="display:flex;height:14px;border-radius:3px;overflow:hidden;background:var(--bg-tertiary);width:'+barWidth+'%;">';
    if (alsoPct > 0)   html += '<div style="width:'+alsoPct+'%;background:#7c5cfc;" title="ALSO '+Math.round(alsoPct)+'%"></div>';
    if (uniwebPct > 0) html += '<div style="width:'+uniwebPct+'%;background:#e67e22;" title="Uniweb '+Math.round(uniwebPct)+'%"></div>';
    html += '</div></td>';

    // Subscription counts
    html += '<td style="padding:6px 8px;text-align:center;font-size:11px;color:var(--text-muted);">';
    if (c.also_subscriptions) html += '<span style="color:#7c5cfc;" title="ALSO">'+Number(c.also_subscriptions)+'</span>';
    if (c.also_subscriptions && c.uniweb_subscriptions) html += ' / ';
    if (c.uniweb_subscriptions) html += '<span style="color:#e67e22;" title="Uniweb">'+Number(c.uniweb_subscriptions)+'</span>';
    if (!c.also_subscriptions && !c.uniweb_subscriptions) html += '-';
    html += '</td>';

    html += '</tr>';
  });

  // ── Total row ──
  html += '<tr style="background:var(--bg-tertiary);border-top:2px solid var(--border);font-weight:700;">';
  html += '<td style="padding:8px;">' + t('dash_total','Totalt') + ' ('+Number(totals.customer_count)+' ' + t('dash_customers_lc','kunder') + ')</td>';
  html += '<td style="padding:8px;text-align:right;color:#7c5cfc;">'+_fmtNOK(totals.also_mrr)+'</td>';
  html += '<td style="padding:8px;text-align:right;color:#e67e22;">'+_fmtNOK(totals.uniweb_monthly)+'</td>';
  html += '<td style="padding:8px;text-align:right;">'+_fmtNOK(totals.total_monthly)+'</td>';
  html += '<td style="padding:8px;"></td>';
  html += '<td style="padding:8px;"></td>';
  html += '</tr>';

  html += '</tbody></table></div>';

  // ── Legend ──
  html += '<div style="display:flex;gap:16px;margin-top:8px;font-size:11px;color:var(--text-muted);">';
  html += '<span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#7c5cfc;margin-right:4px;vertical-align:middle;"></span>ALSO Cloud</span>';
  html += '<span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#e67e22;margin-right:4px;vertical-align:middle;"></span>' + t('dash_uniweb_hosting','Uniweb Hosting') + '</span>';
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
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>' +
    '<div style="text-align:center;color:var(--text-muted);font-size:12px;margin-top:8px;">' + t('dash_checking_tls','Sjekker TLS-sertifikater for alle domener ...') + '</div>';

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
    el.innerHTML = '<div style="color:var(--red);text-align:center;padding:48px;">' + t('dash_domains_load_failed','Kunne ikke laste domenedata') + '</div>';
    return;
  }

  var domains = data.domains || [];
  var s = data.summary || {};
  var html = '';

  // KPI cards
  html += '<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:t('dash_domains_total', 'Domener totalt'), value:Number(s.total)||0, color:'var(--blue)'},
    {label:t('dash_domains_healthy', 'Friske'), value:Number(s.healthy)||0, color:'var(--green)'},
    {label:t('dash_domains_warning', 'Advarsel'), value:Number(s.warning)||0, color:s.warning>0?'var(--orange)':'var(--text-dim)'},
    {label:t('dash_domains_critical', 'Kritisk'), value:Number(s.critical)||0, color:s.critical>0?'var(--red)':'var(--text-dim)'},
    {label:t('dash_missing_spf','Mangler SPF'), value:Number(s.missing_spf)||0, color:s.missing_spf>0?'var(--orange)':'var(--text-dim)'},
    {label:t('dash_missing_dmarc','Mangler DMARC'), value:Number(s.missing_dmarc)||0, color:s.missing_dmarc>0?'var(--orange)':'var(--text-dim)'}
  ];
  kpis.forEach(function(k) {
    html += '<div class="card" style="padding:16px 8px;text-align:center;border-top:2px solid ' + k.color + ';height:90px;box-sizing:border-box;">';
    html += '<div style="font-size:22px;font-weight:700;line-height:24px;color:' + k.color + ';">' + k.value + '</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);line-height:16px;">' + k.label + '</div>';
    html += '</div>';
  });
  html += '</div>';

  if (s.ssl_expiring_30d > 0) {
    html += '<div class="card" style="padding:10px 16px;margin-bottom:16px;border-left:3px solid var(--orange);background:rgba(255,165,0,0.05);font-size:12px;color:var(--orange);font-weight:600;">';
    html += Number(s.ssl_expiring_30d) + ' ' + t('dash_ssl_expiring_30d','SSL-sertifikat utløper innen 30 dager');
    html += '</div>';
  }

  if (domains.length === 0) {
    html += '<div class="card" style="padding:32px;text-align:center;color:var(--text-muted);">';
    html += '<div style="font-size:14px;">' + t('dash_no_domains','Ingen domener funnet') + '</div>';
    html += '<div style="font-size:12px;margin-top:4px;">' + t('dash_no_domains_hint','Synkroniser Uniweb-data for å se domener her.') + '</div>';
    html += '</div>';
    el.innerHTML = html + chainHtml;
    return;
  }

  // Domain table
  html += '<div class="card" style="padding:0;overflow:hidden;">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="background:var(--bg-tertiary);border-bottom:2px solid var(--border);">';
  html += '<th style="text-align:center;padding:8px;width:30px;">'+t('col_health','Helse')+'</th>';
  html += '<th style="text-align:left;padding:8px;">'+t('col_domain','Domene')+'</th>';
  html += '<th style="text-align:left;padding:8px;">'+t('col_customer','Kunde')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_ssl','SSL')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_spf','SPF')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_dkim','DKIM')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_dmarc','DMARC')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_dns','DNS')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_expires','Utløper')+'</th>';
  html += '</tr></thead><tbody>';

  domains.forEach(function(d, i) {
    var healthColors = {good:'var(--green)', warning:'var(--orange)', critical:'var(--red)', unknown:'var(--text-dim)'};
    var healthLabels = {good:'OK', warning:'!', critical:'X', unknown:'?'};
    var hColor = healthColors[d.health] || 'var(--text-dim)';
    var rowBg = i % 2 === 0 ? 'transparent' : 'var(--bg-tertiary)';

    // SSL cell
    var sslHtml = '';
    if (d.ssl && d.ssl.days_remaining !== null && d.ssl.days_remaining !== undefined) {
      var sslColor = 'var(--green)';
      if (d.ssl.days_remaining < 0) sslColor = 'var(--red)';
      else if (d.ssl.days_remaining < 30) sslColor = 'var(--orange)';
      var sslLabel = d.ssl.days_remaining < 0 ? t('lbl_expired_short', 'Utløpt') : Number(d.ssl.days_remaining) + 'd';
      var gradeStr = d.ssl.grade ? ' ' + esc(d.ssl.grade) : '';
      sslHtml = '<span style="color:' + sslColor + ';font-weight:600;" title="' + esc(d.ssl.issuer || '') + ' · ' + t('dash_valid_until','gyldig til') + ' ' + esc(d.ssl.valid_until || '') + '">' + sslLabel + gradeStr + '</span>';
    } else {
      sslHtml = '<span style="color:var(--text-dim);">—</span>';
    }

    // Check/X helper
    var chkY = '<span style="color:var(--green);font-weight:700;font-size:14px;">&#10003;</span>';
    var chkN = '<span style="color:var(--red);font-weight:700;font-size:14px;">&#10007;</span>';

    // Expiry cell
    var expiryHtml = '';
    if (d.days_until_expiry !== null && d.days_until_expiry !== undefined) {
      var expColor = 'var(--text)';
      if (d.days_until_expiry < 0) expColor = 'var(--red)';
      else if (d.days_until_expiry < 90) expColor = 'var(--orange)';
      expiryHtml = '<span style="color:' + expColor + ';" title="' + esc(d.expiry) + '">' + (d.days_until_expiry < 0 ? esc(t('lbl_expired_short', 'Utløpt')) : Number(d.days_until_expiry) + 'd') + '</span>';
    } else {
      expiryHtml = '<span style="color:var(--text-dim);">—</span>';
    }

    html += '<tr style="background:' + rowBg + ';border-bottom:1px solid var(--border);">';
    html += '<td style="padding:6px 8px;text-align:center;"><span style="display:inline-block;width:22px;height:22px;line-height:22px;border-radius:50%;background:' + hColor + ';color:#fff;font-weight:700;font-size:11px;">' + healthLabels[d.health] + '</span></td>';
    html += '<td style="padding:6px 8px;font-weight:500;">' + esc(d.domain) + '</td>';
    html += '<td style="padding:6px 8px;">' + esc(d.customer_name) + '</td>';
    html += '<td style="padding:6px 8px;text-align:center;">' + sslHtml + '</td>';
    html += '<td style="padding:6px 8px;text-align:center;">' + (d.has_spf ? chkY : chkN) + '</td>';
    html += '<td style="padding:6px 8px;text-align:center;">' + (d.has_dkim ? chkY : chkN) + '</td>';
    html += '<td style="padding:6px 8px;text-align:center;">' + (d.has_dmarc ? chkY : chkN) + '</td>';
    html += '<td style="padding:6px 8px;text-align:center;color:var(--text-muted);">' + esc(String(d.dns_records)) + '</td>';
    html += '<td style="padding:6px 8px;text-align:center;font-size:11px;">' + expiryHtml + '</td>';
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

function dashToggleAutoRefresh(btn) {
  if (_dashRefreshInterval) {
    clearInterval(_dashRefreshInterval);
    _dashRefreshInterval = null;
    if (btn) { btn.textContent = t('btn_auto_refresh_off','Auto-refresh: Off'); btn.style.opacity = '0.5'; }
    return;
  }
  _dashRefreshInterval = setInterval(function() {
    var active = document.querySelector('.dash-tab-btn.active');
    if (active) active.click();
  }, _dashRefreshSeconds * 1000);
  if (btn) { btn.textContent = t('btn_auto_refresh_on','Auto-refresh: 2m'); btn.style.opacity = '1'; }
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
      var text = td.textContent.trim().replace(/"/g, '""');
      cells.push('"' + text + '"');
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
function dashExportCosts() { _dashExportTableCSV('dash-costs-content', 'costs'); }
function dashExportDomains() { _dashExportTableCSV('dash-domains-content', 'domains'); }

// Navigate to customer detail view from dashboard tables
function showCustomerDetail(customerId, customerName) {
  if (!customerId) return;
  if (typeof overviewSelectCustomer === 'function') {
    overviewSelectCustomer(customerId);
  }
}

function dashExportCurrentTab() {
  var active = document.querySelector('.dash-tab-content[style*="display: block"], .dash-tab-content[style*="display:block"]');
  if (!active) return;
  var id = active.id;
  if (id === 'dash-alerts') dashExportAlerts();
  else if (id === 'dash-costs') dashExportCosts();
  else if (id === 'dash-domains') dashExportDomains();
  else if (id === 'dash-renewals') _dashExportTableCSV('dash-renewals-content', 'renewals');
  else if (id === 'dash-customers') _dashExportTableCSV('overview-content', 'customers');
  else if (id === 'dash-archive') showToast(t('err_no_export','Export not available for this tab'), 'info');
  else showToast(t('err_no_export','Export not available for this tab'), 'info');
}


// ═══════════════════════════════════════════════════════════════════
// REPORT ARCHIVE
// ═══════════════════════════════════════════════════════════════════

async function dashLoadArchive() {
  var el = document.getElementById('dash-archive-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';

  var data = await apiFetch('/api/reports/archive');
  if (!data) { el.innerHTML = '<div style="color:var(--red);text-align:center;padding:48px;">' + t('dash_load_failed','Kunne ikke laste') + '</div>'; return; }

  var html = '';

  // KPI
  html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:t('lbl_total_reports','Rapporter'), value:Number(data.total_reports), color:'var(--blue)'},
    {label:t('lbl_customers','Kunder'), value:data.customers.length, color:'var(--text)'},
    {label:t('lbl_total_size','Størrelse'), value:Number(data.total_size_mb) + ' MB', color:'var(--text-muted)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card" style="padding:16px 8px;text-align:center;border-top:2px solid '+k.color+';height:90px;box-sizing:border-box;">';
    html += '<div style="font-size:22px;font-weight:700;line-height:24px;color:'+k.color+';">'+k.value+'</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);line-height:16px;">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // Cleanup button
  html += '<div style="display:flex;gap:8px;margin-bottom:16px;">';
  html += '<button class="btn btn-ghost" data-write data-click-handler="dashArchiveCleanup" data-months="3" style="font-size:12px;">'+t('btn_cleanup_3m','Delete older than 3 months')+'</button>';
  html += '<button class="btn btn-ghost" data-write data-click-handler="dashArchiveCleanup" data-months="6" style="font-size:12px;">'+t('btn_cleanup_6m','Delete older than 6 months')+'</button>';
  html += '<button class="btn btn-ghost" data-write data-click-handler="dashArchiveCleanup" data-months="12" style="font-size:12px;">'+t('btn_cleanup_12m','Delete older than 12 months')+'</button>';
  html += '</div>';

  if (data.customers.length === 0) {
    html += '<div class="card" style="padding:32px;text-align:center;color:var(--text-muted);">'+t('msg_no_reports','No reports found.')+'</div>';
    el.innerHTML = html;
    return;
  }

  // Customer list with collapsible runs
  data.customers.forEach(function(c, idx) {
    html += '<div class="card" style="padding:0;margin-bottom:8px;">';
    html += '<div data-click-handler="dashArchiveToggleRuns" style="padding:12px 16px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;">';
    html += '<div><span style="font-weight:600;">'+esc(c.customer_name)+'</span> <span style="font-size:12px;color:var(--text-muted);">('+Number(c.run_count)+' '+t('lbl_reports','reports')+', '+Number(c.total_size_mb)+' MB)</span></div>';
    html += '<span class="chevron" style="font-size:10px;color:var(--text-dim);transition:transform 0.2s;">&#9660;</span>';
    html += '</div>';
    html += '<div style="display:none;border-top:1px solid var(--border);">';
    html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
    html += '<thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:6px 16px;">'+t('lbl_date','Date')+'</th><th style="text-align:center;padding:6px;">'+t('lbl_files','Files')+'</th><th style="text-align:center;padding:6px;">'+t('lbl_size','Size')+'</th><th style="text-align:center;padding:6px;">PDF</th><th style="text-align:center;padding:6px;">HTML</th><th style="text-align:right;padding:6px 16px;"></th></tr></thead><tbody>';
    c.runs.forEach(function(r) {
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += '<td style="padding:6px 16px;">'+esc(r.date || r.name)+'</td>';
      html += '<td style="padding:6px;text-align:center;">'+Number(r.file_count)+'</td>';
      html += '<td style="padding:6px;text-align:center;">'+Number(r.size_mb)+' MB</td>';
      html += '<td style="padding:6px;text-align:center;">'+(r.has_pdf ? '<span style="color:var(--green);">&#10003;</span>' : '<span style="color:var(--text-dim);">-</span>')+'</td>';
      html += '<td style="padding:6px;text-align:center;">'+(r.has_html ? '<span style="color:var(--green);">&#10003;</span>' : '<span style="color:var(--text-dim);">-</span>')+'</td>';
      html += '<td style="padding:6px 16px;text-align:right;"><button class="btn btn-ghost" data-write data-click-handler="dashArchiveDelete" data-path="'+esc(r.path)+'" style="font-size:11px;color:var(--red);padding:2px 8px;">'+t('btn_delete','Delete')+'</button></td>';
      html += '</tr>';
    });
    html += '</tbody></table></div></div>';
  });

  el.innerHTML = html;
}

async function dashArchiveDelete(path) {
  if (!confirm(t('confirm_delete_report','Delete this report permanently?'))) return;
  var d = await apiFetch('/api/reports/archive/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({path:path})});
  if (d && d.ok) {
    showToast(t('msg_deleted','Deleted'), 'success', 2000);
    dashLoadArchive();
  } else {
    showToast((d && d.error) || t('status_error'), 'error');
  }
}

async function generateQBR() {
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
  if (!confirm(t('confirm_cleanup_reports','Delete all reports older than') + ' ' + months + ' ' + t('lbl_months','months') + '?')) return;
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
let _overviewData = null;
let _overviewSortKey = 'risk_score';
let _overviewSortAsc = true;

// ── Dashboard Charts ─────────────────────────────────────────────────────────
var _dashChartInstances = {};
var _dashAutoRefresh = null;
var _dashAutoRefreshSec = 60;
var _dashAutoRefreshRemaining = 0;

function toggleDashAutoRefresh() {
  if (_dashAutoRefresh) { stopDashAutoRefresh(); return; }
  _dashAutoRefreshRemaining = _dashAutoRefreshSec;
  var btn = document.getElementById('dash-autorefresh-btn');
  var cd = document.getElementById('dash-autorefresh-countdown');
  if (btn) btn.style.color = 'var(--green)';
  if (cd) { cd.style.display = 'inline'; cd.textContent = _dashAutoRefreshRemaining + 's'; }
  _dashAutoRefresh = setInterval(function() {
    _dashAutoRefreshRemaining--;
    if (cd) cd.textContent = _dashAutoRefreshRemaining + 's';
    if (_dashAutoRefreshRemaining <= 0) {
      _dashAutoRefreshRemaining = _dashAutoRefreshSec;
      if (currentView === 'overview') loadOverview();
    }
  }, 1000);
  showToast(t('msg_auto_refresh_on','Auto-oppdatering aktivert (60s)'), 'success', 2000);
}
function toggleRowActions(btn) {
  // Close any other open menus
  document.querySelectorAll('.row-actions-menu').forEach(function(m) { m.style.display = 'none'; });
  var menu = btn.nextElementSibling;
  menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}
// Close row action menus on outside click
document.addEventListener('click', function(e) {
  if (!e.target.closest('.row-actions-wrap')) {
    document.querySelectorAll('.row-actions-menu').forEach(function(m) { m.style.display = 'none'; });
  }
});

async function quickSwitchAndAudit(customerId) {
  document.querySelectorAll('.row-actions-menu').forEach(function(m) { m.style.display = 'none'; });
  await switchActiveCustomer(customerId);
  showView('home');
  setTimeout(startAudit, 300);
}
async function quickSwitchAndView(customerId, view) {
  document.querySelectorAll('.row-actions-menu').forEach(function(m) { m.style.display = 'none'; });
  await switchActiveCustomer(customerId);
  showView(view);
}

function stopDashAutoRefresh() {
  if (_dashAutoRefresh) { clearInterval(_dashAutoRefresh); _dashAutoRefresh = null; }
  var btn = document.getElementById('dash-autorefresh-btn');
  var cd = document.getElementById('dash-autorefresh-countdown');
  if (btn) btn.style.color = '';
  if (cd) cd.style.display = 'none';
}
function _celebrateConfetti() {
  var colors = ['#3fb950','#4d9fb5','#d29922','#bc8cff','#58a6ff','#f85149'];
  for (var i = 0; i < 40; i++) {
    var el = document.createElement('div');
    el.className = 'confetti-piece';
    el.style.left = Math.random() * 100 + 'vw';
    el.style.background = colors[Math.floor(Math.random() * colors.length)];
    el.style.animationDelay = (Math.random() * 1.5) + 's';
    el.style.animationDuration = (2 + Math.random() * 2) + 's';
    el.style.width = (5 + Math.random() * 8) + 'px';
    el.style.height = (5 + Math.random() * 8) + 'px';
    document.body.appendChild(el);
    setTimeout(function(e){ e.remove(); }.bind(null, el), 5000);
  }
}

function _animateCountUp(el, target, suffix, duration) {
  if (!el || isNaN(target)) return;

  // The element already shows the true value; this only animates towards it.
  //
  // It used to be the other way round: the markup carried a literal 0 and the
  // truth lived in data-count, so the number a reader saw depended on an
  // animation finishing. It often did not. start was pinned to 0, so a
  // re-render — this view refreshes itself — dropped the figure back to zero
  // and raced the previous loop, and requestAnimationFrame is throttled in a
  // background tab, so switching away could leave a tile reading 0 over a
  // table listing one customer.
  //
  // Starting from what is on screen makes a re-render a no-op instead of a
  // reset, and the generation counter means the newest call is the only one
  // still writing.
  var start = parseFloat(String(el.textContent).replace(/[^0-9.-]/g, ''));
  if (isNaN(start)) start = 0;
  if (start === target) return;

  var generation = (el._countGeneration || 0) + 1;
  el._countGeneration = generation;

  var startTime = null;
  duration = duration || 800;
  function step(ts) {
    if (el._countGeneration !== generation) return;   // superseded
    if (!startTime) startTime = ts;
    var progress = Math.min((ts - startTime) / duration, 1);
    var eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    var current = Math.round(start + (target - start) * eased);
    el.textContent = current + (suffix || '');
    if (progress < 1) requestAnimationFrame(step);
    else el.textContent = target + (suffix || '');   // land exactly on it
  }
  requestAnimationFrame(step);
}

function _renderDashboardCharts(withMetrics) {
  if (typeof Chart === 'undefined') return;
  // Destroy previous instances
  Object.values(_dashChartInstances).forEach(c => c.destroy());
  _dashChartInstances = {};

  const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim();
  const gridColor = getComputedStyle(document.documentElement).getPropertyValue('--border').trim();

  // Risk score bar chart — sorted by risk
  const barCanvas = document.getElementById('chart-risk-bar');
  if (barCanvas && withMetrics.length > 0) {
    const sorted = [...withMetrics].sort((a, b) => (a.metrics.risk_score||0) - (b.metrics.risk_score||0));
    const labels = sorted.map(c => c.customer_name.length > 15 ? c.customer_name.substring(0,14)+'…' : c.customer_name);
    const scores = sorted.map(c => c.metrics.risk_score || 0);
    const colors = scores.map(s => s >= 80 ? '#3fb950' : s >= 60 ? '#4d9fb5' : s >= 40 ? '#d29922' : '#f85149');
    _dashChartInstances.bar = new Chart(barCanvas, {
      type: 'bar',
      data: { labels, datasets: [{ data: scores, backgroundColor: colors, borderRadius: 4, borderSkipped: false }] },
      options: {
        indexAxis: 'y',
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ctx.parsed.x + '/100' } } },
        scales: {
          x: { max: 100, grid: { color: gridColor }, ticks: { color: textColor, font: { size: 11 } } },
          y: { grid: { display: false }, ticks: { color: textColor, font: { size: 11 } } }
        }
      }
    });
  }

  // Grade distribution renders as a CSS stacked bar in renderOverview() now,
  // so there is no donut chart to draw here.
}

// Cached extra dashboard data (health scores + costs) for overview enrichment
var _overviewHealthMap = {};
var _overviewCostMap = {};

// ── Integration health strip (top of Dashboard) ─────────────────────────
// Shows configured / not-configured / recent-failure state for the main
// integrations in one horizontal strip. Fed by /api/settings (config
// presence) + /api/scheduler/tasks (last run + error). Click → /integrations.

async function loadIntegrationHealthStrip() {
  var widget = document.getElementById('integration-health-widget');
  if (!widget) return;
  var [settings, schedRes] = await Promise.all([
    apiFetch('/api/settings').catch(function() { return null; }),
    apiFetch('/api/scheduler/tasks').catch(function() { return null; }),
  ]);
  if (!settings) { widget.style.display = 'none'; return; }

  var tasks = {};
  if (schedRes && schedRes.tasks) {
    schedRes.tasks.forEach(function(t) { tasks[t.id || t.task_id || ''] = t; });
  }

  // Item spec: id (matches scheduler task id where applicable), label,
  // configured flag, optional extra label shown on hover/under the name.
  var items = [
    { key: 'gdap',         label: 'M365 (GDAP)', configured: !!settings.gdap_configured,
      detail: settings.gdap_customer_count ? (settings.gdap_customer_count + ' ' + t('lbl_customers_lc','kunder')) : '' },
    // The core loop first: where findings come from, then where they go.
    { key: 'autotask',     label: 'Autotask',    configured: !!(settings.autotask_integration_code_set && settings.autotask_secret_set && settings.autotask_username) },
    { key: 'myitprocess',  label: 'myITprocess', configured: !!settings.myitprocess_api_key_set },
    { key: 'itglue',       label: 'IT Glue',     configured: !!settings.itglue_api_key_set },
    { key: 'smtp',         label: t('integ_email', 'E-post'), configured: !!(settings.smtp_server && settings.smtp_password_set) },
    { key: 'fortigate',    label: 'FortiGate',   configured: !!settings.fortigate_configured,
      taskId: 'fortigate_backup' },
    { key: 'unifi',        label: 'UniFi',       configured: !!settings.unifi_site_manager_api_key_set },
    { key: 'also',         label: 'ALSO Cloud',  configured: !!settings.also_password_set,
      taskId: 'also_price_refresh', module: 'billing' },
    { key: 'uniweb',       label: 'Uniweb',      configured: !!settings.uniweb_password_set,
      taskId: 'uniweb_sync', module: 'billing' },
    { key: 'tailscale',    label: 'Tailscale',   configured: !!settings.tailscale_api_key_set, module: 'tailscale' },
  ].filter(function(item) { return !item.module || hasModule(item.module); });

  function relTime(iso) {
    if (!iso) return '';
    try {
      var diff = (Date.now() - new Date(iso).getTime()) / 1000;
      if (diff < 60) return t('time_now');
      if (diff < 3600) return Math.round(diff / 60) + 'm';
      if (diff < 86400) return Math.round(diff / 3600) + 't';
      return Math.round(diff / 86400) + 'd';
    } catch(_) { return ''; }
  }

  var cards = items.map(function(item) {
    var task = item.taskId ? tasks[item.taskId] : null;
    var state = 'neutral';  // grey
    if (item.configured) {
      state = 'ok';
      if (task && task.consecutive_failures > 0) state = 'warn';
    }
    var color = {
      ok:      'var(--color-success)',
      warn:    'var(--color-warning)',
      neutral: 'var(--text-dim)',
    }[state];
    var detail = item.detail;
    if (!detail && task && task.last_run) {
      detail = t('lbl_last_run', 'Sist') + ' ' + relTime(task.last_run) + ' siden';
    }
    if (!item.configured) detail = t('lbl_not_configured', 'Ikke konfigurert');
    return '' +
      '<div class="integ-health-card" data-integ-key="' + esc(item.key) + '" style="min-width:0;padding:10px 12px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);cursor:pointer;display:flex;flex-direction:column;gap:3px;transition:border-color var(--duration-fast);" title="' + esc(item.label) + '">' +
        '<div style="display:flex;align-items:center;gap:6px;">' +
          '<span style="width:8px;height:8px;border-radius:50%;background:' + color + ';flex-shrink:0;"></span>' +
          '<span style="font-size:12px;font-weight:600;color:var(--text);">' + esc(item.label) + '</span>' +
        '</div>' +
        (detail ? '<div style="font-size:10px;color:var(--text-dim);">' + esc(detail) + '</div>' : '') +
      '</div>';
  });

  widget.innerHTML = '' +
    '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-2);">' +
      '<div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">' + esc(t('hdr_integration_health', 'Integrasjonsstatus')) + '</div>' +
      '<a href="#" data-click-handler="showView" data-view="integrations" style="font-size:var(--font-xs);color:var(--blue);text-decoration:none;">' + esc(t('lbl_manage', 'Administrer')) + ' &rarr;</a>' +
    '</div>' +
    // A grid, so a short last row keeps the cards' size instead of stretching them.
    '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(128px,1fr));gap:var(--space-3);">' + cards.join('') + '</div>';

  widget.style.display = 'block';
}

// Delegated click → open Integrasjoner view
document.addEventListener('click', function(e) {
  var card = e.target.closest('#integration-health-widget .integ-health-card');
  if (!card) return;
  showView('integrations');
});

async function loadOverview() {
  const box = document.getElementById('overview-content');
  // Integration health strip — fire-and-forget, independent of the
  // customer grid load. Errors in /api/settings shouldn't delay or break
  // dashboard rendering.
  loadIntegrationHealthStrip().catch(function(e) { console.debug('integ strip failed:', e); });
  // Fetch overview, health-scores, and costs in parallel
  const [d, healthData, costData, trendData] = await Promise.all([
    apiFetch('/api/dashboard/overview'),
    apiFetch('/api/dashboard/health-scores').catch(function() { return null; }),
    apiFetch('/api/dashboard/costs').catch(function() { return null; }),
    apiFetch('/api/dashboard/trends').catch(function() { return null; }),
  ]);
  window._overviewTrends = (trendData && trendData.trends) ? trendData.trends : {};
  if (d) {
    // Build lookup maps for health and cost data
    _overviewHealthMap = {};
    if (healthData && healthData.scores) {
      healthData.scores.forEach(function(h) { _overviewHealthMap[h.customer_id] = h; });
    }
    _overviewCostMap = {};
    if (costData && costData.customers) {
      costData.customers.forEach(function(c) { _overviewCostMap[c.customer_id] = c; });
    }
    _overviewData = {customers: d.customers || [], active_id: d.active_id};
    renderOverview(_overviewData.customers, _overviewData.active_id);
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
// One definition, shared by the KPI tile, the attention strip above it and
// the "Vis kun disse" filter, so the three cannot drift apart. A customer
// needs attention when its last audit found a poor result, when it has never
// been audited, or when that audit is older than _STALE_DAYS. Counting only
// poor results showed a green 0 on an install where nobody had been audited:
// a customer nobody has looked at is not a customer without problems.
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

function _needsAttention(c) {
  return !c.has_metrics || _poorResult(c.metrics) || _auditIsStale(c);
}

var _gradeFilter = '';
var _quickFilter = 'all';
function filterByGrade(grade) {
  if (_gradeFilter === grade) { _gradeFilter = ''; } // toggle off
  else { _gradeFilter = grade; }
  filterOverview();
  if (_gradeFilter) showToast(t('lbl_grade') + ': ' + _gradeFilter, 'info', 1500);
}

function filterOverview() {
  if (!_overviewData) return;
  const search = (document.getElementById('overview-search')?.value || '').toLowerCase();
  const filter = document.getElementById('overview-filter')?.value || 'all';
  var qf = window._quickFilter || 'all';
  let filtered = _overviewData.customers.filter(c => {
    if (search && !c.customer_name.toLowerCase().includes(search) && !(c.primary_domain||'').toLowerCase().includes(search)) return false;
    if (filter === 'has_m365' && !c.has_m365) return false;
    if (filter === 'has_fortigate' && !c.has_fortigate) return false;
    if (filter === 'needs_setup' && (c.has_m365 || c.has_fortigate || c.has_unifi)) return false;
    if (filter === 'mfa80' && (!c.has_metrics || c.metrics.mfa_coverage_pct === undefined || c.metrics.mfa_coverage_pct >= 80)) return false;
    if (filter === 'riskdf' && (!c.has_metrics || (c.metrics.risk_grade !== 'D' && c.metrics.risk_grade !== 'F'))) return false;
    if (filter === 'noaudit' && c.has_metrics) return false;
    // Same meaning as the "Utdatert >30d" tile. Never-audited customers have
    // their own option (noaudit) instead of hiding inside this one.
    if (filter === 'stale' && !_auditIsStale(c)) return false;
    if (_gradeFilter && (!c.has_metrics || c.metrics.risk_grade !== _gradeFilter)) return false;
    if (qf === 'attention' && !_needsAttention(c)) return false;
    // Quick filter: "Problemer" = health grade D/F
    if (qf === 'problems') {
      var hd = _overviewHealthMap[c.customer_id];
      if (!hd || (hd.grade !== 'D' && hd.grade !== 'F')) return false;
    }
    // Quick filter: "Utloper snart" = has expiring items (health breakdown has license/domain issues)
    if (qf === 'expiring') {
      var he = _overviewHealthMap[c.customer_id];
      if (!he) return false;
      var br = he.breakdown || {};
      var hasExpiring = (br.license_compliance && br.license_compliance.score < br.license_compliance.max)
        || (br.domain_health && br.domain_health.score < br.domain_health.max);
      if (!hasExpiring) return false;
    }
    // Time filter
    var timeFilter = (document.getElementById('overview-time-filter') || {}).value || 'all';
    if (timeFilter !== 'all' && c.last_audit) {
      var daysAgo = _auditAgeDays(c);
      if (daysAgo !== null && daysAgo > parseInt(timeFilter)) return false;
    }
    return true;
  });
  renderOverview(filtered, _overviewData.active_id);

  // Show active filter badges
  var afEl = document.getElementById('overview-active-filters');
  if (afEl) {
    var badges = [];
    if (search) badges.push('<span style="background:var(--blue-dark);color:var(--blue);padding:3px 10px;border-radius:var(--radius-full);font-size:var(--font-xs);border:1px solid rgba(77,159,181,0.3);cursor:pointer;" data-click-handler="dashClearSearchFilter">&#10005; &quot;' + esc(search) + '&quot;</span>');
    if (filter !== 'all') {
      var fLabels = {has_m365:'M365', has_fortigate:'FortiGate', needs_setup:t('filter_needs_setup','Needs setup'), mfa80:'MFA < 80%', riskdf:t('filter_grade_df','Grade D/F'), noaudit:t('filter_no_audit'), stale:t('filter_stale_audit','Stale audit')};
      badges.push('<span style="background:var(--blue-dark);color:var(--blue);padding:3px 10px;border-radius:var(--radius-full);font-size:var(--font-xs);border:1px solid rgba(77,159,181,0.3);cursor:pointer;" data-click-handler="dashClearTypeFilter">&#10005; ' + esc(fLabels[filter]||filter) + '</span>');
    }
    if (_gradeFilter) badges.push('<span style="background:var(--blue-dark);color:var(--blue);padding:3px 10px;border-radius:var(--radius-full);font-size:var(--font-xs);border:1px solid rgba(77,159,181,0.3);cursor:pointer;" data-click-handler="dashClearGradeFilter">&#10005; ' + t('lbl_grade') + ': ' + esc(_gradeFilter) + '</span>');
    // Set by "Vis kun disse" on the attention strip. Without a badge the table
    // stayed narrowed with nothing on screen saying so.
    if (qf === 'attention') badges.push('<button type="button" class="filter-badge" id="overview-attention-badge">&#10005; ' + esc(t('lbl_needs_attention')) + '</button>');
    if (badges.length > 0) {
      badges.push('<span style="font-size:var(--font-xs);color:var(--text-dim);cursor:pointer;text-decoration:underline;" data-click-handler="dashClearAllFilters">' + t('btn_clear_all','Clear all') + '</span>');
      afEl.style.display = 'flex';
      afEl.innerHTML = badges.join('');
      var attnBadge = document.getElementById('overview-attention-badge');
      if (attnBadge) attnBadge.addEventListener('click', function() { _quickFilter = 'all'; filterOverview(); });
    } else {
      afEl.style.display = 'none';
      afEl.innerHTML = '';
    }
  }
}

function sortOverview(key) {
  if (_overviewSortKey === key) _overviewSortAsc = !_overviewSortAsc;
  else { _overviewSortKey = key; _overviewSortAsc = key === 'customer_name'; }
  filterOverview();
}

function renderOverview(customers, activeId) {
  const box = document.getElementById('overview-content');

  // Sort
  const sk = _overviewSortKey;
  customers.sort((a, b) => {
    let va = sk === 'customer_name' ? a.customer_name : (a.has_metrics ? (a.metrics[sk] ?? -1) : -1);
    let vb = sk === 'customer_name' ? b.customer_name : (b.has_metrics ? (b.metrics[sk] ?? -1) : -1);
    if (typeof va === 'string' || typeof vb === 'string') { va = String(va ?? '').toLowerCase(); vb = String(vb ?? '').toLowerCase(); }
    const cmp = va < vb ? -1 : va > vb ? 1 : 0;
    return _overviewSortAsc ? cmp : -cmp;
  });

  // Collect all tags from unfiltered data for the dropdown
  var allTags = [];
  (_overviewData ? _overviewData.customers : customers).forEach(function(c){(c.tags||[]).forEach(function(t){if(allTags.indexOf(t)===-1)allTags.push(t)})});
  var selectedTag = (document.getElementById('overview-tag-filter')||{}).value || '';
  if (selectedTag) customers = customers.filter(function(c){return (c.tags||[]).indexOf(selectedTag) !== -1});

  const total = customers.length;
  const withMetrics = customers.filter(c => c.has_metrics);
  const avgRisk = withMetrics.length > 0
    ? (withMetrics.reduce((s, c) => s + (c.metrics.risk_score || 0), 0) / withMetrics.length).toFixed(0)
    : '-';
  // Who needs attention, and why: see _needsAttention. The breakdown feeds
  // the attention strip; the parts overlap (an old audit can also be a poor
  // one), so the tile shows the union rather than their sum.
  const needsAttention = customers.filter(_needsAttention).length;
  const attnPoor = withMetrics.filter(c => _poorResult(c.metrics)).length;
  const neverAudited = total - withMetrics.length;
  // Only customers that have an audit can have an old one; the never-audited
  // are counted on their own rather than hidden inside "older than 30 days".
  const staleCount = withMetrics.filter(_auditIsStale).length;
  const withMfa = withMetrics.filter(c => typeof c.metrics.mfa_coverage_pct === 'number');
  const avgMfa = withMfa.length > 0
    ? (withMfa.reduce((s, c) => s + c.metrics.mfa_coverage_pct, 0) / withMfa.length).toFixed(0)
    : '-';

  // ── KPI trend chips ────────────────────────────────────────────────────
  // Deltas are measured over the customers that have BOTH a current and a
  // previous audit, so a customer audited for the first time this period
  // shows up as neither an improvement nor a regression. Customer count,
  // stale-audit count and the attention tile have no previous snapshot to
  // compare against (a missing or old audit has no "before"), so those tiles
  // carry no chip rather than one that measures something else.
  const paired = withMetrics.filter(c => c.prev_metrics);
  const _avgDelta = key => {
    if (!paired.length) return null;
    const cur = paired.reduce((s, c) => s + (c.metrics[key] || 0), 0) / paired.length;
    const prv = paired.reduce((s, c) => s + (c.prev_metrics[key] || 0), 0) / paired.length;
    return cur - prv;
  };
  const riskDelta = _avgDelta('risk_score');
  const mfaDelta = _avgDelta('mfa_coverage_pct');

  // Green means "checked, and fine". A zero over customers without data is
  // not that, and neither is a dash where no average could be taken.
  const KPI_NEUTRAL = 'var(--text-dim)';
  const attnColor = needsAttention > 0 ? (attnPoor > 0 ? 'var(--red)' : 'var(--orange)')
    : (total > 0 ? 'var(--green)' : KPI_NEUTRAL);
  const staleColor = staleCount > 0 ? 'var(--orange)'
    : (total > 0 && neverAudited === 0 ? 'var(--green)' : KPI_NEUTRAL);
  const riskColor = avgRisk === '-' ? KPI_NEUTRAL
    : avgRisk < 50 ? 'var(--red)' : avgRisk < 70 ? 'var(--orange)' : 'var(--green)';
  const mfaColor = avgMfa === '-' ? KPI_NEUTRAL
    : avgMfa < 80 ? 'var(--red)' : avgMfa < 95 ? 'var(--orange)' : 'var(--green)';

  // Renders nothing for a null or sub-unit delta, so "no change" stays quiet.
  function trendChip(delta, higherIsBetter, suffix) {
    if (delta === null || delta === undefined) return '';
    const d = Math.round(delta);
    if (d === 0) return '';
    // Written as an equality rather than a ternary: the i18n prose detector
    // reads `? d > 0 : d < 0` as a baked-in string.
    const good = higherIsBetter === (d > 0);
    const txt = (d > 0 ? '+' : '−') + Math.abs(d) + (suffix || '');
    return '<span class="kpi-trend" style="color:' + (good ? 'var(--green)' : 'var(--red)') + ';" title="'
      + esc(t('tip_since_previous_audit', 'Endring siden forrige audit')) + '">' + esc(txt) + '</span>';
  }

  function fmtDate(d) {
    return d ? formatRunName(d, true) : '-';
  }

  var tagFilterHtml = '<select id="overview-tag-filter" data-change-handler="filterOverview" style="padding:4px 10px;border:1px solid var(--border);border-radius:6px;font-size:12px;background:var(--bg);color:var(--text);margin-left:12px;"><option value="">' + t('alle_tags') + '</option>';
  allTags.forEach(function(t){tagFilterHtml += '<option value="'+esc(t)+'"'+(selectedTag===t?' selected':'')+'>'+esc(t)+'</option>'});
  tagFilterHtml += '</select>';

  // Render search/filter bar only once — check if it exists
  var searchBar = document.getElementById('overview-search-bar');
  if (!searchBar) {
    box.innerHTML = `
    <div id="overview-summary"></div>
    <div id="overview-search-bar">
      <div class="dash-toolbar">
        <input id="overview-search" type="text" class="field-input" placeholder="${t('lbl_search_customer')}" style="width:220px;padding:7px 10px;font-size:13px;" data-input-handler="filterOverview">
        <select id="overview-filter" class="field-input" style="width:auto;padding:7px 10px;font-size:13px;" data-change-handler="filterOverview">
          <option value="all">${t('filter_all')}</option>
          <option value="has_m365">${t('filter_has_m365','Has M365')}</option>
          <option value="has_fortigate">${t('filter_has_fortigate','Has FortiGate')}</option>
          <option value="needs_setup">${t('filter_needs_setup','Needs setup')}</option>
          <option value="mfa80">${t('filter_mfa_80')}</option>
          <option value="riskdf">${t('filter_risk_df')}</option>
          <option value="noaudit">${t('filter_no_audit')}</option>
          <option value="stale">${t('filter_stale_audit','Stale audit')}</option>
        </select>
        <select id="overview-time-filter" class="field-input" style="width:auto;padding:7px 10px;font-size:13px;" data-change-handler="filterOverview">
          <option value="all">${t('filter_all_time','All time')}</option>
          <option value="7">${t('filter_last_7d','Last 7 days')}</option>
          <option value="30">${t('filter_last_30d','Last 30 days')}</option>
          <option value="90">${t('filter_last_90d','Last 90 days')}</option>
        </select>
        ${tagFilterHtml}
        <span style="width:1px;height:22px;background:var(--border);margin:0 4px;"></span>
        <button class="qpill" id="qp-all" data-click-handler="dashSetQuickFilter" data-quick-filter="all">${t('filter_quick_all','Alle')}</button>
        <button class="qpill" id="qp-problems" data-click-handler="dashSetQuickFilter" data-quick-filter="problems">${t('filter_quick_problems','Problemer')}</button>
        <button class="qpill" id="qp-expiring" data-click-handler="dashSetQuickFilter" data-quick-filter="expiring">${t('filter_quick_expiring','Utløper snart')}</button>
        <div style="flex:1;"></div>
        <button class="btn btn-primary btn-sm" id="bulk-audit-btn" data-click-handler="startBulkAudit" style="font-size:12px;">${t('btn_run_all_customers')}</button>
        <div class="colpick" id="overview-colpick">
          <button class="dash-tab-tool" data-click-handler="toggleOverviewColpick">${t('lbl_columns','Kolonner')} &#9662;</button>
          <div class="colpick-menu" id="overview-colpick-menu">
            <label><input type="checkbox" data-col="health" data-change-handler="toggleOverviewColumn"> ${t('lbl_health','Helse')}</label>
            <label><input type="checkbox" data-col="users" data-change-handler="toggleOverviewColumn"> ${t('lbl_users','Brukere')}</label>
            <label><input type="checkbox" data-col="trend" data-change-handler="toggleOverviewColumn"> ${t('lbl_trend','Trend')}</label>
            <label><input type="checkbox" data-col="tags" data-change-handler="toggleOverviewColumn"> ${t('lbl_tags','Tags')}</label>
          </div>
        </div>
      </div>
      <div id="bulk-audit-panel" style="display:none;"></div>
    </div>
    <div id="overview-active-filters" style="display:none;margin-bottom:var(--space-3);display:flex;gap:var(--space-2);flex-wrap:wrap;align-items:center;"></div>
    <div id="overview-table-content"></div>`;
  }

  var tableBox = document.getElementById('overview-table-content') || box;

  // Summary block (attention strip + KPI cards) goes into a persistent
  // container ABOVE the toolbar, so the mock's order holds — attention → KPI →
  // toolbar → table → charts — while the search input keeps focus/value.
  var summaryHtml = '';
  if (needsAttention > 0) {
    var _attnGradeD = withMetrics.filter(function(c){ return c.metrics.risk_grade === 'D' || c.metrics.risk_grade === 'F'; }).length;
    var _attnLowMfa = withMetrics.filter(function(c){ return typeof c.metrics.mfa_coverage_pct === 'number' && c.metrics.mfa_coverage_pct < 80; }).length;
    var _attnParts = [];
    if (_attnGradeD) _attnParts.push(_attnGradeD + ' ' + t('attn_grade_d'));
    if (_attnLowMfa) _attnParts.push(_attnLowMfa + ' ' + t('attn_low_mfa'));
    if (neverAudited) _attnParts.push(neverAudited + ' ' + t('attn_no_audit'));
    if (staleCount) _attnParts.push(staleCount + ' ' + t('attn_stale'));
    summaryHtml += `
      <div class="attn-strip${attnPoor ? '' : ' attn-strip--gaps'}">
        <span class="attn-title">${needsAttention} ${t('lbl_needs_followup', 'kunder trenger oppfølging')}</span>
        <span class="attn-detail">${esc(_attnParts.join(' · '))}</span>
        <div style="flex:1;"></div>
        <button class="attn-action" data-click-handler="dashSetQuickFilter" data-quick-filter="attention">${t('btn_show_only_these', 'Vis kun disse')}</button>
      </div>`;
  }
  summaryHtml += `
    <div class="kpi-row">
      <div class="kpi-card"><div class="kpi-label">${t('lbl_total_customers')}</div><div class="kpi-value-row"><span class="kpi-value kpi-num" data-count="${total}" style="color:var(--text);">${total}</span></div></div>
      <div class="kpi-card"><div class="kpi-label">${t('lbl_avg_risk_score')}</div><div class="kpi-value-row"><span class="kpi-value kpi-num" data-count="${avgRisk !== '-' ? avgRisk : ''}" style="color:${riskColor};">${avgRisk === '-' ? '-' : avgRisk}</span>${trendChip(riskDelta, true)}</div></div>
      <div class="kpi-card"><div class="kpi-label">${t('lbl_avg_mfa','MFA-dekning')}</div><div class="kpi-value-row"><span class="kpi-value kpi-num" data-count="${avgMfa !== '-' ? avgMfa : ''}" data-suffix="%" style="color:${mfaColor};">${avgMfa === '-' ? '-' : avgMfa + '%'}</span>${trendChip(mfaDelta, true, ' pp')}</div></div>
      <div class="kpi-card" id="kpi-needs-attention"><div class="kpi-label">${t('lbl_needs_attention')}</div><div class="kpi-value-row"><span class="kpi-value kpi-num" data-count="${needsAttention}" style="color:${attnColor};">${needsAttention}</span></div></div>
      <div class="kpi-card" id="kpi-stale"><div class="kpi-label">${t('lbl_stale_30d','Utdatert >30d')}</div><div class="kpi-value-row"><span class="kpi-value kpi-num" data-count="${staleCount}" style="color:${staleColor};">${staleCount}</span></div></div>
    </div>`;
  var _sumBox = document.getElementById('overview-summary');
  if (_sumBox) _sumBox.innerHTML = summaryHtml;

  let html = '';

  // Build the grade-distribution stacked bar (charts sit below the table now).
  setTimeout(function() {
    var grades = {A:0, B:0, C:0, D:0, F:0};
    withMetrics.forEach(function(c) { var g = c.metrics.risk_grade; if (grades[g] !== undefined) grades[g]++; });
    var gc = {A:'var(--green)',B:'var(--blue)',C:'var(--orange)',D:'var(--red)',F:'#8b0000'};
    var stack = document.getElementById('grade-stack');
    if (stack) {
      stack.innerHTML = Object.keys(gc).map(function(k){ return grades[k] > 0 ? '<span style="flex:'+grades[k]+';background:'+gc[k]+';"></span>' : ''; }).join('') || '<span style="flex:1;background:var(--border);"></span>';
    }
    var legend = document.getElementById('grade-legend');
    if (legend) {
      legend.innerHTML = Object.keys(gc).filter(function(k){return grades[k]>0;}).map(function(k){ return '<span><b style="color:'+gc[k]+';">'+esc(k)+'</b> '+grades[k]+'</span>'; }).join('');
    }
  }, 60);

  // Render charts after DOM update
  setTimeout(() => {
    _renderDashboardCharts(withMetrics);
    // Animate KPI numbers
    document.querySelectorAll('.kpi-num').forEach(function(el) {
      var val = parseFloat(el.getAttribute('data-count'));
      var suffix = el.getAttribute('data-suffix') || '';
      if (!isNaN(val)) _animateCountUp(el, val, suffix, 900);
    });
  }, 50);

  if (customers.length === 0) {
    html += `
      <div class="card" style="text-align:center;padding:var(--space-16) var(--space-6);">
        <div style="font-size:var(--font-lg);font-weight:600;color:var(--text);margin-bottom:var(--space-2);">${t('msg_no_customers_registered')}</div>
        <div style="font-size:var(--font-sm);color:var(--text-dim);margin-bottom:var(--space-6);max-width:360px;margin-left:auto;margin-right:auto;">${t('msg_go_to_customers')}</div>
        <button class="btn btn-primary btn-lg" data-click-handler="showView" data-view="customers">${t('btn_add_first_customer')}</button>
      </div>`;
  } else {
    html += `
    <div class="card overview-table-wrap" style="padding:0;overflow:auto;max-height:70vh;background:var(--bg-panel);">
      <table class="slim-table customer-overview-table">
        <thead>
          <tr>
            <th class="sortable" data-click-handler="sortOverview" data-sort="customer_name">${t('lbl_customer')} ${_overviewSortKey==='customer_name'?(_overviewSortAsc?'\u25B2':'\u25BC'):''}</th>
            <th>${t('lbl_status','Status')}</th>
            <th class="num sortable" data-click-handler="sortOverview" data-sort="risk_score">${t('lbl_risk')} ${_overviewSortKey==='risk_score'?(_overviewSortAsc?'\u25B2':'\u25BC'):''}</th>
            <th class="num sortable" data-click-handler="sortOverview" data-sort="mfa_coverage_pct">MFA ${_overviewSortKey==='mfa_coverage_pct'?(_overviewSortAsc?'\u25B2':'\u25BC'):''}</th>
            <th class="num sortable" data-click-handler="sortOverview" data-sort="secure_score_pct">${t('lbl_secure_score','Secure score')} ${_overviewSortKey==='secure_score_pct'?(_overviewSortAsc?'\u25B2':'\u25BC'):''}</th>
            <th class="num">MRR</th>
            <th>${t('lbl_last_audit')}</th>
            <th class="col-opt col-hidden" data-optcol="health" title="${t('tip_health_grade','Health grade (A-F) across all integrations')}">${t('lbl_health','Helse')}</th>
            <th class="num col-opt col-hidden sortable" data-optcol="users" data-click-handler="sortOverview" data-sort="total_users">${t('lbl_users','Brukere')}</th>
            <th class="col-opt col-hidden" data-optcol="trend">${t('lbl_trend','Trend')}</th>
            <th class="col-opt col-hidden" data-optcol="tags">${t('lbl_tags','Tags')}</th>
            <th style="width:40px;"></th>
          </tr>
        </thead>
        <tbody>`;

    function deltaHtml(cur, prev, key, higherIsBetter) {
      if (prev === undefined || prev === null || cur === undefined || cur === null) return '';
      var cv = typeof cur === 'object' ? cur[key] : cur;
      var pv = typeof prev === 'object' ? prev[key] : prev;
      if (cv === undefined || pv === undefined || cv === pv) return '';
      var diff = cv - pv;
      var isGood = higherIsBetter ? diff > 0 : diff < 0;
      var arrow = diff > 0 ? '&#9650;' : '&#9660;';
      var color = isGood ? 'var(--green)' : 'var(--red)';
      return '<span style="font-size:9px;color:'+color+';margin-left:3px;" title="'+( diff > 0 ? '+' : '')+diff.toFixed(0)+'">' + arrow + '</span>';
    }

    // Pagination
    var _pageSize = 25;
    var _totalPages = Math.ceil(customers.length / _pageSize);
    if (!window._dashPage || window._dashPage > _totalPages) window._dashPage = 1;
    var _startIdx = (window._dashPage - 1) * _pageSize;
    var _pagedCustomers = customers.slice(_startIdx, _startIdx + _pageSize);

    for (const c of _pagedCustomers) {
      const m = c.metrics || {};
      const pm = c.prev_metrics || {};
      const hasM = c.has_metrics;
      const hasPrev = !!c.prev_metrics;
      const grade = hasM ? (m.risk_grade || '-') : '-';
      const score = hasM ? (m.risk_score !== undefined ? m.risk_score : '-') : '-';
      const mfa = hasM && metricPct(m.mfa_coverage_pct) !== null ? metricPct(m.mfa_coverage_pct) + '%' : '-';
      const ss = hasM && metricPct(m.secure_score_pct) !== null ? metricPct(m.secure_score_pct) + '%' : '-';
      const users = hasM && m.total_users !== undefined ? m.total_users : '-';
      const lastAudit = esc(fmtDate(c.last_audit));
      const mfaColor = !hasM || m.mfa_coverage_pct === undefined ? 'var(--text-muted)' : m.mfa_coverage_pct >= 95 ? 'var(--green)' : m.mfa_coverage_pct >= 80 ? 'var(--orange)' : 'var(--red)';
      const ssColor = !hasM || m.secure_score_pct === undefined ? 'var(--text-muted)' : m.secure_score_pct >= 75 ? 'var(--green)' : m.secure_score_pct >= 50 ? 'var(--orange)' : 'var(--red)';
      const activeBadge = c.is_active ? ' <span style="background:var(--blue);color:#fff;padding:1px 6px;border-radius:10px;font-size:10px;font-weight:600;vertical-align:middle;">' + t('status_active') + '</span>' : '';

      // Health score from enriched data
      const _hd = _overviewHealthMap[c.customer_id] || {};
      const healthGrade = _hd.grade || '-';
      const healthScore = _hd.total_score !== undefined ? _hd.total_score : '-';
      const healthColor = {A:'#3fb950',B:'#4d9fb5',C:'#d29922',D:'#f85149',F:'#8b0000'}[healthGrade] || 'var(--text-muted)';

      // MRR from cost data
      const _cd = _overviewCostMap[c.customer_id] || {};
      const mrrVal = Number(_cd.total_monthly) || 0;
      const mrrStr = mrrVal > 0 ? mrrVal.toLocaleString('nb-NO', {minimumFractionDigits:0, maximumFractionDigits:0}) + ' kr' : '-';

      // Grade → semantic colour var + derived status pill (frame 1b). The
      // -deep variant is the label colour: it sits on a 12% tint of its own
      // hue, which light theme has to compensate for to stay above WCAG AA.
      const _gv = {A:'var(--green)',B:'var(--blue)',C:'var(--orange)',D:'var(--red)',F:'var(--red)'}[grade] || 'var(--text-muted)';
      const _gvd = {A:'var(--green-deep)',B:'var(--blue-deep)',C:'var(--orange-deep)',D:'var(--red-deep)',F:'var(--red-deep)'}[grade] || 'var(--text-muted)';
      let _stLabel, _stColor, _stDeep;
      if (grade === 'D' || grade === 'F') { _stLabel = t('status_needs_followup','Trenger oppfølging'); _stColor = 'var(--red)'; _stDeep = 'var(--red-deep)'; }
      else if (hasM && m.total_warns > 0) { _stLabel = t('status_watch','Følg med'); _stColor = 'var(--orange)'; _stDeep = 'var(--orange-deep)'; }
      else if (hasM) { _stLabel = 'OK'; _stColor = 'var(--green)'; _stDeep = 'var(--green-deep)'; }
      else { _stLabel = '—'; _stColor = 'var(--text-dim)'; _stDeep = 'var(--text-muted)'; }
      const _stBg = hasM ? `color-mix(in srgb, ${_stColor} 12%, transparent)` : 'transparent';
      const _domBadges = `${c.has_m365 ? ' <span style="background:var(--blue);color:#fff;padding:0 4px;border-radius:3px;font-size:9px;font-weight:600;font-family:sans-serif;" title="M365 configured">M365</span>' : ''}${c.has_fortigate ? ' <span style="background:#e8590c;color:#fff;padding:0 4px;border-radius:3px;font-size:9px;font-weight:600;font-family:sans-serif;" title="FortiGate configured">FG</span>' : ''}${c.has_unifi ? ' <span style="background:#06b6d4;color:#fff;padding:0 4px;border-radius:3px;font-size:9px;font-weight:600;font-family:sans-serif;" title="UniFi configured">UF</span>' : ''}${!c.has_m365 && !c.has_fortigate && !c.has_unifi ? ' <span style="background:var(--text-dim);color:#fff;padding:0 4px;border-radius:3px;font-size:9px;font-weight:600;font-family:sans-serif;" title="'+t('filter_needs_setup','Needs setup')+'">?</span>' : ''}`;
      const _warnNote = `${hasM && m.total_warns > 0 ? '<div style="font-size:10px;color:var(--orange);margin-top:2px;">' + Number(m.total_warns) + ' ' + t('lbl_warnings','warnings') + '</div>' : ''}${(() => { if (!c.last_audit) return '<div style="font-size:10px;color:var(--text-dim);margin-top:1px;">'+t('lbl_never_audited','Never audited')+'</div>'; if (_auditIsStale(c)) return '<div style="font-size:10px;color:var(--orange);margin-top:1px;">'+Math.floor(_auditAgeDays(c))+'d '+t('lbl_since_audit','since audit')+'</div>'; return ''; })()}`;

      html += `
          <tr data-click-handler="dashOverviewSelectCustomer" data-customer-id="${esc(c.customer_id)}"
              data-dblclick-handler="dashRowQuickAudit"
              title="${t('tip_click_detail_dblclick_audit','Click: details · Double-click: run audit')}">
            <td>
              <div class="cust-cell">
                <span class="grade-tile" style="color:${_gvd};background:color-mix(in srgb, ${_gv} 12%, transparent);border-color:color-mix(in srgb, ${_gv} 40%, transparent);" data-click-handler="dashFilterByGrade" data-grade="${esc(grade)}" title="${t('tip_click_filter_grade','Click to filter by grade')}">${esc(grade)}</span>
                <span style="min-width:0;">
                  <span class="cname">${esc(c.customer_name)}${activeBadge}</span>
                  <span class="cdom">${esc(c.primary_domain || '')}${_domBadges}</span>
                  ${_warnNote}
                </span>
              </div>
            </td>
            <td><span class="status-pill" style="color:${_stDeep};background:${_stBg};">${_stLabel}</span></td>
            <td class="num">${esc(String(score))}${hasPrev ? deltaHtml(m, pm, 'risk_score', true) : ''}</td>
            <td class="num" style="color:${mfaColor};">${mfa}${hasPrev ? deltaHtml(m, pm, 'mfa_coverage_pct', true) : ''}</td>
            <td class="num" style="color:${ssColor};">${ss}${hasPrev ? deltaHtml(m, pm, 'secure_score_pct', true) : ''}</td>
            <td class="num" style="color:${mrrVal > 0 ? 'var(--text-muted)' : 'var(--text-dim)'};font-weight:${mrrVal > 0 ? '600' : '400'};">${mrrStr}</td>
            <td style="color:var(--text-muted);font-size:12px;white-space:nowrap;">${lastAudit}</td>
            <td class="col-opt col-hidden" data-optcol="health" style="text-align:center;">
              <span style="display:inline-block;width:26px;height:26px;line-height:26px;border-radius:50%;font-weight:700;font-size:12px;color:#fff;background:${healthColor};" title="${t('lbl_health','Helse')}: ${esc(healthGrade)} (${esc(String(healthScore))}/100)">${esc(healthGrade)}</span>
            </td>
            <td class="num col-opt col-hidden" data-optcol="users">${esc(String(users))}</td>
            <td class="col-opt col-hidden" data-optcol="trend" style="text-align:center;"><span id="spark-${esc(c.customer_id || c._id || '')}" style="display:inline-block;width:72px;height:24px;"></span></td>
            <td class="col-opt col-hidden" data-optcol="tags">${tagPillsHtml(c.tags || [])}</td>
            <td style="text-align:center;">
              <div style="position:relative;display:inline-block;" class="row-actions-wrap">
                <button class="hover-subtle" data-click-handler="dashToggleRowActions" style="background:none;border:none;cursor:pointer;font-size:18px;color:var(--text-dim);padding:2px 6px;border-radius:var(--radius-sm);transition:background var(--duration-fast);">&#8943;</button>
                <div class="row-actions-menu" style="display:none;position:absolute;right:0;top:100%;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:var(--space-1) 0;min-width:180px;box-shadow:var(--shadow-lg);z-index:50;animation:dropdown-in var(--duration-fast) var(--ease-out);">
                  <button class="hover-menu-item" data-click-handler="dashRowDetails" data-customer-id="${esc(c.customer_id)}" style="display:flex;align-items:center;gap:var(--space-2);width:100%;padding:8px 14px;background:none;border:none;color:var(--text);font-size:13px;text-align:left;cursor:pointer;transition:background 0.1s;">${t('lbl_details')}</button>
                  <button class="hover-menu-item" data-click-handler="dashRowAudit" data-customer-id="${esc(c.customer_id)}" style="display:flex;align-items:center;gap:var(--space-2);width:100%;padding:8px 14px;background:none;border:none;color:var(--text);font-size:13px;text-align:left;cursor:pointer;transition:background 0.1s;">${t('btn_run_audit')}</button>
                  <button class="hover-menu-item" data-click-handler="dashRowHistory" data-customer-id="${esc(c.customer_id)}" style="display:flex;align-items:center;gap:var(--space-2);width:100%;padding:8px 14px;background:none;border:none;color:var(--text);font-size:13px;text-align:left;cursor:pointer;transition:background 0.1s;">${t('nav_history')}</button>
                  <button class="hover-menu-item" data-click-handler="dashRowReport" data-customer-id="${esc(c.customer_id)}" style="display:flex;align-items:center;gap:var(--space-2);width:100%;padding:8px 14px;background:none;border:none;color:var(--text);font-size:13px;text-align:left;cursor:pointer;transition:background 0.1s;">${t('btn_generate_report')}</button>
                  <div style="border-top:1px solid var(--border);margin:var(--space-1) 0;"></div>
                  <button class="hover-menu-item-danger" data-click-handler="dashRowArchive" data-customer-id="${esc(c.customer_id)}" data-customer-name="${esc(c.customer_name)}" style="display:flex;align-items:center;gap:var(--space-2);width:100%;padding:8px 14px;background:none;border:none;color:var(--red);font-size:13px;text-align:left;cursor:pointer;transition:background 0.1s;">${t('btn_archive','Archive')}</button>
                </div>
              </div>
            </td>
          </tr>`;
    }

    html += `
        </tbody>
      </table>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:12px;margin-top:20px;">
      <div class="card" style="background:var(--bg-panel);padding:16px;">
        <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:10px;">${t('lbl_risk_distribution')}</div>
        ${withMetrics.length
          ? '<div style="position:relative;height:120px;"><canvas id="chart-risk-bar"></canvas></div>'
          : '<div class="chart-empty">' + esc(t('msg_chart_no_audits')) + '</div>'}
      </div>
      <div class="card" style="background:var(--bg-panel);padding:16px;">
        <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:10px;">${t('lbl_grade_distribution')}</div>
        ${withMetrics.length
          ? '<div class="grade-stack" id="grade-stack"></div><div class="grade-legend" id="grade-legend"></div>'
          : '<div class="chart-empty">' + esc(t('msg_chart_no_audits')) + '</div>'}
      </div>
    </div>`;
  }

  // Pagination controls
  if (_totalPages > 1) {
    html += '<div style="display:flex;align-items:center;justify-content:center;gap:var(--space-3);padding:var(--space-4) 0;font-size:var(--font-sm);">'
      + '<button class="btn btn-ghost btn-sm" data-click-handler="dashPagePrev" ' + (window._dashPage <= 1 ? 'disabled' : '') + '>&laquo; ' + t('btn_prev','Prev') + '</button>'
      + '<span style="color:var(--text-muted);">' + Number(window._dashPage) + ' / ' + _totalPages + '</span>'
      + '<button class="btn btn-ghost btn-sm" data-click-handler="dashPageNext" data-total-pages="' + Number(_totalPages) + '" ' + (window._dashPage >= _totalPages ? 'disabled' : '') + '>' + t('btn_next','Next') + ' &raquo;</button>'
      + '</div>';
  }

  tableBox.innerHTML = html;

  // Apply saved column-visibility prefs, refresh the quick-filter pills,
  // and stamp "Oppdatert HH:MM" in the tab bar.
  applyOverviewColumnPrefs();
  _updateOverviewQuickPills();
  var _updT = document.getElementById('dash-updated-time');
  if (_updT) {
    _updT.textContent = new Date().toLocaleTimeString('no-NO', {hour:'2-digit', minute:'2-digit'});
    var _updW = document.getElementById('dash-updated-wrap');
    if (_updW) _updW.style.display = '';
  }

  // Make the overview table sortable
  var overviewTable = tableBox.querySelector('table');
  if (overviewTable) makeSortable(overviewTable);

  // Load sparkline trend data
  _loadSparklines();
}
