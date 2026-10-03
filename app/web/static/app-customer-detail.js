// ═══════════════════════════════════════════════════════════════════
// CUSTOMER DETAIL VIEW
// ═══════════════════════════════════════════════════════════════════

// sshTerminal and vpnConnect (data-id) are registered by app-infra.js.
registerUiHandlers({
  // FortiGate threat log: show or hide the rows past the first five.
  cdToggleFgThreatRows: function(el) {
    var rows = document.querySelectorAll('.fg-threat-extra');
    var show = rows[0] && rows[0].style.display === 'none';
    rows.forEach(function(r) { r.style.display = show ? 'table-row' : 'none'; });
    el.textContent = show ? el.dataset.lessLabel : el.dataset.allLabel;
  },
  cdToggleUnifiClients: function() {
    var tb = document.getElementById('unifi-clients-table');
    var btn = document.getElementById('unifi-clients-toggle');
    if (tb.style.display === 'none') { tb.style.display = 'table'; btn.textContent = t('lbl_hide_clients', 'Hide clients'); } else { tb.style.display = 'none'; btn.textContent = t('lbl_show_clients', 'Show clients'); }
  },
  alsoToggleSubDetail: function(el) { alsoToggleSubDetail(el, el.dataset.subId); },
  uwToggleDns: function(el) { uwToggleDns(el, el.dataset.domain); },
});

// ── Customer Detail View ──────────────────────────────────────────────────────
var _detailChartInstance = null;

async function loadCustomerDetail(customerId) {
  syncRoute('customer-detail', customerId);
  var box = document.getElementById('customer-detail-content');
  box.innerHTML = '<div style="text-align:center;padding:48px;color:var(--text-muted);"><div class="loader" style="width:24px;height:24px;margin:0 auto 16px;"></div>' + t('msg_loading','Loading...') + '</div>';

  // Find customer from cached overview data — load if not cached yet
  if (!_overviewData || !_overviewData.customers) {
    try {
      var ovData = await apiFetch('/api/dashboard/overview');
      if (ovData) _overviewData = {customers: ovData.customers || [], active_id: ovData.active_id};
    } catch(e) { console.warn('Overview data load failed:', e); }
  }
  var cust = null;
  if (_overviewData && _overviewData.customers) {
    cust = _overviewData.customers.find(function(c){ return c.customer_id === customerId || c._id === customerId; });
  }
  if (!cust) { box.innerHTML = '<div class="alert alert-error">' + t('err_customer_not_found','Kunde ikke funnet') + '</div>'; return; }

  var m = cust.metrics || {};
  var hasM = cust.has_metrics;
  var gradeColor = function(g) { return {A:'#3fb950', B:'#4d9fb5', C:'#d29922', D:'#f85149', F:'#8b0000'}[g] || 'var(--text-muted)'; };

  // Update breadcrumb
  var bcItems = document.getElementById('breadcrumb-items');
  var bcNav = document.getElementById('breadcrumb');
  if (bcNav && bcItems) {
    bcNav.style.display = 'block';
    bcItems.innerHTML = '<a href="#" data-click-handler="showView" data-view="customers" style="color:var(--text-muted);text-decoration:none;">' + t('nav_customers') + '</a>' +
      ' <span style="margin:0 var(--space-2);color:var(--text-dim);opacity:0.5;">/</span> ' +
      '<span style="color:var(--text);font-weight:500;">' + esc(cust.customer_name) + '</span>';
  }

  var grade = hasM ? (m.risk_grade || '-') : '-';
  var score = hasM ? (m.risk_score !== undefined ? m.risk_score : '-') : '-';
  var auditMeta = cust.last_audit
    ? t('lbl_audited_on', 'Auditert {date}').replace('{date}', _auditDateLabel(cust.last_audit))
    : t('msg_never_audited', 'Aldri auditert');
  var gradePill = hasM && m.risk_grade
    ? '<span class="grade-pill grade-' + esc(String(m.risk_grade)) + '">' + esc(t('lbl_grade', 'Karakter') + ' ' + m.risk_grade) + '</span>'
    : '';
  var canAudit = !!cust.has_m365;
  var canSetup = hasFeature('audit') && canWrite();

  // The page answers one question first: what is wrong here, and what do I do
  // about it. Identity and the one primary action on top; links to the PSA
  // and documentation next, because the actions on each finding depend on
  // them; then the findings. Metrics and history follow.
  box.innerHTML = `
    <div class="cust-head">
      <div class="cust-head-main">
        <h1 class="cust-title">${esc(cust.customer_name)}</h1>
        <div class="cust-meta">
          ${cust.primary_domain ? '<span class="cust-domain">' + esc(cust.primary_domain) + '</span>' : ''}
          <span>${esc(auditMeta)}</span>
          ${gradePill}
        </div>
      </div>
      <div class="cust-head-actions">
        <button class="btn btn-primary" id="cust-run-audit" data-write ${canAudit ? '' : 'disabled title="' + esc(t('tip_audit_needs_m365', 'M365-tilgang må settes opp før en audit kan kjøre')) + '"'}>${esc(t('btn_run_audit'))}</button>
        <button class="btn btn-ghost" data-click-handler="openLatestReport">${esc(t('btn_open_report', 'Rapport'))}</button>
        <button class="btn btn-ghost" id="cust-generate-report">${esc(t('btn_generate_report'))}</button>
      </div>
    </div>
    ${canAudit ? '' : '<div class="findings-notice is-warning cust-access-notice"><span>' + esc(t('msg_m365_missing', 'M365-tilgang er ikke satt opp for denne kunden, så den kan ikke auditeres ennå.')) + '</span>' + (canSetup ? '<button class="btn btn-default btn-sm" id="cust-setup-m365">' + esc(t('btn_setup_m365', 'Sett opp M365-tilgang')) + '</button>' : '') + '</div>'}
    <div id="cust-links" class="cust-links"></div>
    <div id="cust-findings"></div>
    <nav class="cust-tabs">
      <button class="cust-tab" id="cust-tab-status">${esc(t('nav_m365_status'))}</button>
      <button class="cust-tab" id="cust-tab-history">${esc(t('nav_history'))}</button>
      <button class="cust-tab" id="cust-tab-files">${esc(t('nav_files', 'Filer'))}</button>
      ${cust.also_account_id && hasModule('billing') ? '<button class="cust-tab" id="cust-tab-licenses">' + esc(t('nav_licenses', 'Lisenser')) + '</button>' : ''}
    </nav>

    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:var(--space-4);margin-bottom:var(--space-6);">
      <div class="card" style="text-align:center;padding:var(--space-5);">
        <div style="width:64px;height:64px;line-height:64px;border-radius:var(--radius-xl);font-weight:800;font-size:var(--font-2xl);color:#fff;background:${gradeColor(grade)};margin:0 auto var(--space-3);box-shadow:0 4px 12px ${gradeColor(grade)}40;">${esc(grade)}</div>
        <div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">${t('lbl_grade')}</div>
      </div>
      <div class="card" style="text-align:center;padding:var(--space-5);">
        <div style="position:relative;width:80px;height:80px;margin:0 auto var(--space-2);"><canvas id="gauge-risk"></canvas></div>
        <div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">${t('lbl_risk')}</div>
      </div>
      <div class="card" style="text-align:center;padding:var(--space-5);">
        <div style="position:relative;width:80px;height:80px;margin:0 auto var(--space-2);"><canvas id="gauge-mfa"></canvas></div>
        <div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">MFA</div>
      </div>
      <div class="card" style="text-align:center;padding:var(--space-5);">
        <div style="position:relative;width:80px;height:80px;margin:0 auto var(--space-2);"><canvas id="gauge-ss"></canvas></div>
        <div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">${t('secure_score_2')}</div>
      </div>
    </div>

    <div id="customer-baseline-panel"></div>
    <div id="customer-policies-panel"></div>

    <div class="card cust-trend" id="cust-trend">
      <div class="cust-card-title">${t('lbl_trend')}</div>
      <div class="cust-trend-body" id="cust-trend-body"></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4);">
      <div class="card" style="padding:var(--space-5);">
        <div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:var(--space-4);">${t('lbl_details')}</div>
        <dl class="cust-details" id="cust-details">
          ${_detailRow(t('lbl_users'), hasM, m.total_users)}
          ${_detailRow(t('lbl_users_without_mfa', 'Brukere uten MFA'), hasM, m.users_no_mfa, 'is-bad')}
          ${_detailRow(t('lbl_ca_policies'), hasM, m.ca_policies_enabled)}
          <dt>${t('intune')}</dt><dd${hasM && metricPct(m.intune_compliance_pct) === null ? ' class="is-unknown"' : ''}>${!hasM ? '-' : metricPct(m.intune_compliance_pct) !== null ? metricPct(m.intune_compliance_pct) + '%' : esc(t('lbl_unknown_value', 'ukjent'))}</dd>
          <dt>${t('lbl_last_audit')}</dt><dd>${cust.last_audit ? esc(formatRunName(cust.last_audit)) : '-'}${_auditAgeSuffix(cust.last_audit)}</dd>
          ${_detailRow(t('lbl_warnings_title', 'Advarsler'), hasM, m.total_warns, 'is-warn')}
        </dl>
      </div>
      <div class="card" style="padding:var(--space-5);">
        <div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:var(--space-4);">${t('lbl_tags')}</div>
        <div style="display:flex;flex-wrap:wrap;gap:var(--space-2);">
          ${(cust.tags || []).map(function(tag){ return '<span style="background:var(--blue-dark);color:var(--blue);padding:4px 10px;border-radius:var(--radius-full);font-size:var(--font-xs);border:1px solid rgba(77,159,181,0.3);">'+esc(tag)+'</span>'; }).join('') || '<span style="color:var(--text-dim);font-size:var(--font-sm);">'+t('msg_no_tags','Ingen tags')+'</span>'}
        </div>
      </div>
    </div>
  `;

  // Render gauge charts + trend chart + remediation
  setTimeout(function() { _renderGauges(score, hasM ? m.mfa_coverage_pct : null, hasM ? m.secure_score_pct : null); }, 50);
  _loadCustomerTrendChart(customerId);
  _loadCustomerBaselineCard(customerId);
  _loadCustomerPoliciesCard(customerId);

  _wireCustomerHead(customerId, cust);
  _loadCustomerLinks(customerId, cust.customer_name);
  mountCustomerFindings(document.getElementById('cust-findings'), customerId, {
    onLinked: function() { _loadCustomerLinks(customerId, cust.customer_name); },
  });

  // Add notes panel
  var notesDiv = document.createElement('div');
  notesDiv.className = 'card';
  notesDiv.style.cssText = 'padding:var(--space-5);margin-top:var(--space-4);';
  notesDiv.id = 'customer-notes-panel';
  notesDiv.innerHTML = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3);">'
    + '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;">' + t('hdr_notes','Notater') + '</div>'
    + '<div style="display:flex;gap:var(--space-2);align-items:center;">'
    + '<span id="detail-notes-status" style="font-size:var(--font-xs);color:var(--text-dim);"></span>'
    + '<button class="btn btn-ghost btn-sm" id="detail-notes-save">' + t('btn_save','Lagre') + '</button>'
    + '</div></div>'
    + '<textarea id="detail-notes-textarea" style="width:100%;min-height:120px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);color:var(--text);padding:var(--space-3);font-family:inherit;font-size:var(--font-sm);resize:vertical;" placeholder="' + t('placeholder_notes','Skriv notater om denne kunden...') + '"></textarea>';
  box.appendChild(notesDiv);
  document.getElementById('detail-notes-save').addEventListener('click', saveDetailNotes);
  _loadCustomerNotes();

  // Activity log for this customer
  var actDiv = document.createElement('div');
  actDiv.className = 'card';
  actDiv.style.cssText = 'padding:var(--space-5);margin-top:var(--space-4);';
  actDiv.id = 'customer-activity-panel';
  actDiv.innerHTML = '<div class="text-sm text-muted">' + t('msg_loading','Laster...') + '</div>';
  box.appendChild(actDiv);
  _loadCustomerActivity(cust.customer_name);

  // Uniweb Hosting card, part of the billing module
  if (hasModule('billing')) {
    var uwDiv = document.createElement('div');
    uwDiv.id = 'customer-uniweb-panel';
    box.appendChild(uwDiv);
    _unifiedLoadUniwebCard(customerId);
  }

  // Network Inventory card
  var netDiv = document.createElement('div');
  netDiv.className = 'card';
  netDiv.style.cssText = 'padding:var(--space-5);margin-top:var(--space-4);';
  netDiv.id = 'customer-network-panel';
  netDiv.innerHTML = '<div class="text-sm text-muted">' + t('msg_loading_network','Loading network inventory...') + '</div>';
  box.appendChild(netDiv);
  _loadCustomerNetworkInventory(customerId);

  // Infrastructure card (SSH hosts, VPN profiles, FortiGate, UniFi)
  var infraDiv = document.createElement('div');
  infraDiv.id = 'customer-infra-panel';
  box.appendChild(infraDiv);
  _loadCustomerInfraCard(customerId);
}

// One row of the Detaljer card: a count from the latest run's metrics, the
// word "ukjent" when that run did not measure it, a dash with no run at all.
// `alarm` colours a measured figure above zero.
function _detailRow(label, hasMetrics, value, alarm) {
  var cls = '';
  if (hasMetrics && !metricKnown(value)) cls = 'is-unknown';
  else if (hasMetrics && alarm && Number(value) > 0) cls = alarm;
  return '<dt>' + esc(label) + '</dt><dd' + (cls ? ' class="' + esc(cls) + '"' : '') + '>'
    + (hasMetrics ? esc(metricCount(value)) : '-') + '</dd>';
}

// " (12d)" after a run folder name, or nothing. Folder names are
// "YYYY-MM-DD_HHMMSS_…", which Date cannot read whole; the date part is enough.
function _auditAgeSuffix(runName) {
  var date = new Date(String(runName || '').substring(0, 10));
  if (!runName || isNaN(date.getTime())) return '';
  var days = Math.max(0, Math.floor((Date.now() - date.getTime()) / 86400000));
  return ' <span style="color:var(--text-dim);font-weight:400;">(' + Number(days) + 'd)</span>';
}

// ── Customer page head: the one primary action, and the links strip ─────────

// Switch the server's per-user active customer, then keep the header in step.
// Audit, setup and the per-customer views still read it, so a page that names
// a customer makes it the active one before acting.
async function activateCustomer(customerId) {
  var d = await switchActiveCustomer(customerId);
  if (d && typeof loadStatus === 'function') loadStatus();
  return !!d;
}

function _wireCustomerHead(customerId, cust) {
  var run = document.getElementById('cust-run-audit');
  if (run) run.addEventListener('click', async function() {
    if (run.disabled) return;
    run.disabled = true;
    if (await activateCustomer(customerId)) await startAudit();
    run.disabled = false;
  });
  var setup = document.getElementById('cust-setup-m365');
  if (setup) setup.addEventListener('click', async function() {
    if (await activateCustomer(customerId)) startSetup();
  });
  var report = document.getElementById('cust-generate-report');
  if (report) report.addEventListener('click', function() {
    window.open('/api/reports/customer-summary/' + encodeURIComponent(customerId), '_blank');
  });
  [['cust-tab-status', 'home'], ['cust-tab-history', 'history'], ['cust-tab-files', 'files']].forEach(function(pair) {
    var tab = document.getElementById(pair[0]);
    if (tab) tab.addEventListener('click', async function() {
      if (await activateCustomer(customerId)) showView(pair[1]);
    });
  });
  var lic = document.getElementById('cust-tab-licenses');
  if (lic) lic.addEventListener('click', function() { loadCustomerLicenses(cust.also_account_id); });
}

// The PSA and documentation records this customer is linked to. Only
// integrations that are set up appear; one that is not set up is the
// Integrations page's business, not this customer's.
async function _loadCustomerLinks(customerId, customerName) {
  var el = document.getElementById('cust-links');
  if (!el) return;
  var d = await apiFetch('/api/hub/' + encodeURIComponent(customerId));
  if (!d || document.getElementById('cust-links') !== el) return;
  var canLink = hasFeature('integrations') && canWrite();
  var chips = [];
  [['autotask', 'Autotask'], ['myitprocess', 'myITprocess'], ['itglue', 'IT Glue']].forEach(function(pair) {
    var sys = pair[0], label = pair[1], b = d[sys] || {};
    if (!b.status || b.status === 'not_configured') return;
    if (b.status === 'not_linked') {
      chips.push(canLink
        ? '<button class="link-chip is-unlinked" data-link="' + sys + '">' + esc(t('btn_link_system', 'Koble til {system}').replace('{system}', label)) + '</button>'
        : '<span class="link-chip is-unlinked">' + esc(label + ': ' + t('lbl_not_linked', 'ikke koblet')) + '</span>');
      return;
    }
    if (b.status === 'unavailable') {
      chips.push('<span class="link-chip is-warning" title="' + esc(b.reason || '') + '">' + esc(label + ': ' + t('lbl_unavailable', 'utilgjengelig')) + '</span>');
      return;
    }
    var name = b.account_name || b.account_id || b.organization_id || '';
    var text = esc(label) + ' <span class="link-chip-name">' + esc(String(name)) + '</span>';
    if (sys === 'itglue' && b.documents_url) {
      chips.push('<a class="link-chip" href="' + esc(b.documents_url) + '" target="_blank" rel="noopener noreferrer">' + text + '</a>'
        + (canLink ? '<button class="link-chip-edit" data-link="itglue" aria-label="' + esc(t('btn_change_link', 'Endre kobling')) + '">' + esc(t('btn_change', 'Endre')) + '</button>' : ''));
    } else {
      chips.push(canLink
        ? '<button class="link-chip" data-link="' + sys + '" title="' + esc(t('btn_change_link', 'Endre kobling')) + '">' + text + '</button>'
        : '<span class="link-chip">' + text + '</span>');
    }
  });
  el.innerHTML = chips.length ? '<span class="cust-links-label">' + esc(t('hdr_links', 'Koblinger')) + '</span>' + chips.join('') : '';
  el.onclick = function(e) {
    var btn = e.target.closest('[data-link]');
    if (!btn) return;
    openLinkPicker(customerId, customerName, btn.dataset.link, function() {
      _loadCustomerLinks(customerId, customerName);
      mountCustomerFindings(document.getElementById('cust-findings'), customerId, {
        onLinked: function() { _loadCustomerLinks(customerId, customerName); },
      });
    });
  };
}

// ── Sybr Standard on the customer card ──────────────────────────────────────
// Two questions a technician opening a customer asks first: how far is this
// tenant from what we require, and did anything move since last time. The
// answers come from the same two endpoints the report reads, so the card and
// the PDF can never disagree.
//
// The card never invents a verdict. A requirement whose evidence was not
// collected is shown as not assessed and kept out of the percentage, and a
// customer with nothing to compare against is told that rather than shown a
// reassuring zero.
// Reason codes carry their values separately, so the sentence is assembled
// in the reader's language rather than shipped from the server in one.
function _reason(prefix, code, params) {
  var out = t(prefix + code, '');
  if (!out) return '';
  Object.keys(params || {}).forEach(function(k) {
    // A run is named to a person by its date, not its folder.
    out = out.split('{' + k + '}').join(String(k === 'run' ? formatRunName(params[k]) : params[k]));
  });
  return out;
}

// The sentence beside a requirement. The server sends a reason code and the
// values behind it, including the internal path the check reads
// ("mfa.has_data"). A person reads which part of the collection was missing,
// never the field name.
var _BASELINE_SECTIONS = ['mfa', 'admin_roles', 'ca', 'secure_score', 'entra_devices', 'intune',
  'exchange', 'backup_coverage', 'sharepoint', 'usage'];

function _baselineValue(v) {
  if (v === true) return t('lbl_yes', 'Ja');
  if (v === false) return t('lbl_no', 'Nei');
  if (v === null || v === undefined) return t('lbl_unknown_value', 'ukjent');
  return String(v);
}

function baselineReason(c) {
  var p = c.params || {};
  var code = c.reason_code;
  if (code === 'guard_unset') {
    var section = String(p.guard || '').split('.')[0];
    if (section === 'drift') return t('bl_guard_unset_drift', 'Ikke vurdert: det finnes ingen tidligere kjøring å sammenligne policyene med.');
    var name = _BASELINE_SECTIONS.indexOf(section) >= 0
      ? t('bl_section_' + section, '') : '';
    return t('bl_guard_unset', 'Ikke vurdert: {section} ble ikke samlet inn i denne kjøringen.')
      .replace('{section}', name || t('bl_section_unknown', 'grunnlaget for dette kravet'));
  }
  if (!code) return '';
  var out = t('bl_' + code, '');
  return out
    .split('{actual}').join(_baselineValue(p.actual))
    .split('{expected}').join(_baselineValue(p.expected))
    .split('{op}').join(String(p.op || ''));
}

function _baselineStatusPill(status) {
  if (status === 'pass') return '<span style="color:var(--green);">&#10003;</span>';
  if (status === 'fail') return '<span style="color:var(--red);">&#10007;</span>';
  return '<span style="color:var(--text-dim);">&#8211;</span>';
}

// The policies actually in production for this customer, lifted onto the card
// by the last audit. Read-only; each row carries a plain-language line the
// server produced from the raw policy object, so it reads the same everywhere.
async function _loadCustomerPoliciesCard(customerId) {
  var el = document.getElementById('customer-policies-panel');
  if (!el) return;
  var inv = await apiFetch('/api/policy-backup/' + encodeURIComponent(customerId) + '/live').catch(function(){ return null; });
  if (!inv || !inv.workloads || Object.keys(inv.workloads).length === 0) { el.style.display = 'none'; return; }
  el.style.display = '';

  function stateP(s) {
    var map = { 'on': ['var(--green)', t('lbl_policy_on','On')],
                'report-only': ['var(--orange)', t('lbl_policy_report','Report-only')],
                'off': ['var(--text-dim)', t('lbl_policy_off','Off')],
                'trusted': ['var(--blue)', t('lbl_policy_trusted','Trusted')] };
    var m = map[s];
    var colour = m ? m[0] : 'var(--text-muted)';
    var label = m ? m[1] : s;
    return '<span style="display:inline-block;padding:1px 8px;border-radius:10px;font-size:10px;font-weight:600;color:#fff;background:' + colour + ';">' + esc(label) + '</span>';
  }
  function loc(v) { return (v && (v[_lang] || v.no || v.en)) || ''; }

  var html = '<div class="card" style="padding:var(--space-5);margin-bottom:var(--space-4);">';
  html += '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--space-3);margin-bottom:var(--space-4);">';
  html += '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;">'
        + t('hdr_policies_live','Policies in production') + '</div>';
  html += '<div style="font-size:var(--font-xs);color:var(--text-muted);">'
        + t('lbl_captured','Captured') + ': ' + esc((inv.captured_at || '').slice(0, 10)) + '</div>';
  html += '</div>';

  Object.keys(inv.workloads).forEach(function(k) {
    var wl = inv.workloads[k];
    html += '<div style="margin-bottom:var(--space-3);">';
    html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">'
          + esc(loc(wl.label)) + ' <span style="color:var(--text-dim);font-weight:400;">(' + Number(wl.count) + ')</span></div>';
    html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
    (wl.items || []).forEach(function(it) {
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += '<td style="padding:6px 8px 6px 0;white-space:nowrap;vertical-align:top;">' + stateP(it.state) + '</td>';
      html += '<td style="padding:6px 8px 6px 0;font-weight:600;vertical-align:top;">' + esc(it.name) + '</td>';
      html += '<td style="padding:6px 0;color:var(--text-muted);">' + esc(loc(it.summary)) + '</td>';
      html += '</tr>';
    });
    html += '</table></div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

async function _loadCustomerBaselineCard(customerId) {
  var el = document.getElementById('customer-baseline-panel');
  if (!el) return;

  var results = await Promise.all([
    apiFetch('/api/baselines/default/evaluate/' + encodeURIComponent(customerId) + '/latest?lang=' + _lang).catch(function(){ return null; }),
    apiFetch('/api/policy-backup/' + encodeURIComponent(customerId) + '/drift').catch(function(){ return null; })
  ]);
  var b = results[0], drift = results[1];
  if (!b) { el.style.display = 'none'; return; }
  if (!b.baseline) {
    // A customer with no audit yet. Say so quietly rather than showing an
    // empty card or, worse, a zero.
    el.innerHTML = '<div class="card" style="padding:var(--space-5);margin-bottom:var(--space-4);color:var(--text-dim);font-size:var(--font-sm);">'
      + esc(_reason('drift_', b.reason_code, {}) || t('msg_baseline_no_run','No audit run to measure against yet.')) + '</div>';
    return;
  }

  var pct = b.conformance_pct;
  var pctColor = pct === null || pct === undefined ? 'var(--text-dim)'
    : (pct >= 90 ? 'var(--green)' : (pct >= 70 ? 'var(--orange)' : 'var(--red)'));
  var nothing = b.assessed === 0;

  var html = '<div class="card cust-standard" id="cust-standard">';
  html += '<div class="cust-standard-head">';
  html += '<div class="cust-card-title">' + esc(b.baseline.name) + ' ' + esc(b.baseline.version) + '</div>';
  // No percentage when nothing was assessed: a dash beside "etterlevelse"
  // still reads as a score.
  if (!nothing && pct !== null && pct !== undefined) {
    html += '<div class="cust-standard-pct"><span style="color:' + pctColor + ';">' + Number(pct) + ' %</span>'
          + '<span class="cust-standard-pct-label">' + esc(t('lbl_conformance', 'etterlevelse')) + '</span></div>';
  }
  html += '</div>';

  var rows = '<table class="cust-standard-table">';
  (b.checks || []).forEach(function(c) {
    var dim = c.status === 'not_measured';
    rows += '<tr' + (dim ? ' class="is-dim"' : '') + '>';
    rows += '<td class="cust-standard-mark">' + _baselineStatusPill(c.status) + '</td>';
    rows += '<td>' + esc(c.title) + '</td>';
    rows += '<td class="cust-standard-reason">' + esc(baselineReason(c)) + '</td>';
    rows += '</tr>';
  });
  rows += '</table>';

  // What the percentage is a percentage of. Showing it without this invites
  // the reader to assume every requirement was measured. When nothing could
  // be assessed, one sentence says so and the requirements fold away: nine
  // rows each saying "not assessed" tell the reader nothing the sentence
  // does not.
  if (nothing) {
    html += '<p class="cust-standard-note">' + esc(t('msg_baseline_nothing_assessed', 'Ingen krav kunne vurderes, fordi kjøringen ikke samlet inn det kravene leser. Det sier noe om innsamlingen, ikke om tenanten.')) + '</p>';
    html += '<details class="cust-standard-details"><summary>'
          + esc(t('btn_show_requirements', 'Vis kravene ({n})').replace('{n}', Number((b.checks || []).length)))
          + '</summary>' + rows + '</details>';
  } else {
    html += '<p class="cust-standard-note">'
          + esc(t('msg_baseline_basis', '{passed} of {assessed} assessed requirements met')
              .replace('{passed}', Number(b.passed)).replace('{assessed}', Number(b.assessed)))
          + (b.not_measured ? ' &middot; ' + esc(t('msg_baseline_skipped', '{n} not assessed').replace('{n}', Number(b.not_measured))) : '')
          + '</p>';
    html += rows;
  }

  // ── Drift ──
  html += '<div style="margin-top:var(--space-4);padding-top:var(--space-4);border-top:1px solid var(--border);">';
  html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">'
        + t('hdr_policy_drift','Changes since previous audit') + '</div>';
  if (!drift || !drift.measured) {
    html += '<div style="font-size:var(--font-xs);color:var(--text-dim);">'
          + esc((drift && _reason('drift_', drift.reason_code, drift.reason_params)) || t('msg_drift_not_measured','Not compared.')) + '</div>';
  } else if (!drift.added_total && !drift.removed_total && !drift.changed_total) {
    html += '<div style="font-size:var(--font-xs);color:var(--text-muted);">'
          + esc(t('msg_drift_quiet','No policy changed since {run}.').replace('{run}', formatRunName(drift.compared_with))) + '</div>';
  } else {
    html += '<div style="font-size:var(--font-xs);color:var(--text-muted);margin-bottom:var(--space-2);">'
          + t('msg_drift_summary','Compared with {run}: {added} added, {removed} removed, {changed} changed.')
              .replace('{run}', esc(formatRunName(drift.compared_with))).replace('{added}', Number(drift.added_total))
              .replace('{removed}', Number(drift.removed_total)).replace('{changed}', Number(drift.changed_total))
          + '</div>';
    html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
    // Label and colour per kind, kept apart from the policies themselves.
    var kinds = {
      removed: [t('lbl_removed','Removed'), 'var(--red)'],
      changed: [t('lbl_changed','Changed'), 'var(--orange)'],
      added: [t('lbl_added','Added'), 'var(--green)'],
    };
    (drift.snapshots || []).forEach(function(s) {
      if (!s.comparable) return;
      var rows = [];
      (s.removed || []).forEach(function(p){ rows.push(['removed', p, '']); });
      (s.changed || []).forEach(function(p){ rows.push(['changed', p, (p.fields||[]).join(', ')]); });
      (s.added   || []).forEach(function(p){ rows.push(['added', p, '']); });
      rows.forEach(function(r) {
        var kind = kinds[r[0]];
        html += '<tr style="border-bottom:1px solid var(--border);">'
              + '<td style="padding:5px 8px 5px 0;color:' + kind[1] + ';white-space:nowrap;">' + kind[0] + '</td>'
              + '<td style="padding:5px 0;">' + esc(r[1].name || t('lbl_unnamed','(unnamed)')) + '</td>'
              + '<td style="padding:5px 0;text-align:right;color:var(--text-dim);">' + esc(r[2]) + '</td>'
              + '</tr>';
      });
    });
    html += '</table>';
  }
  html += '</div></div>';

  el.innerHTML = html;
}

// ── Customer Infrastructure Card ────────────────────────────────────────────

async function _loadCustomerInfraCard(customerId) {
  var el = document.getElementById('customer-infra-panel');
  if (!el) return;
  try {
    var d = await apiFetch('/api/dashboard/customer-infra/' + encodeURIComponent(customerId));
    if (!d) { el.style.display = 'none'; return; }

    // SSH hosts are the remote module's; with it off they are not this page's either.
    var sshHosts = hasModule('remote') ? (d.ssh_hosts || []) : [];
    var vpnProfiles = d.vpn_profiles || [];
    var fg = d.fortigate;
    var uf = d.unifi;

    var hasAnything = sshHosts.length || vpnProfiles.length || fg || uf;
    if (!hasAnything) {
      el.innerHTML = '<div class="card" style="padding:var(--space-5);margin-top:var(--space-4);">'
        + '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:var(--space-3);">' + t('hdr_infrastructure','Infrastructure') + '</div>'
        + '<div style="color:var(--text-dim);font-size:var(--font-sm);">' + t('msg_no_infra_linked','No infrastructure linked to this customer. Link SSH hosts or VPN profiles from the Infrastructure section.') + '</div>'
        + '</div>';
      return;
    }

    var html = '<div class="card" style="padding:var(--space-5);margin-top:var(--space-4);">';
    html += '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:var(--space-4);">' + t('hdr_infrastructure','Infrastructure') + '</div>';

    // SSH Hosts
    if (sshHosts.length) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">' + t('hdr_ssh_hosts','SSH Hosts') + ' (' + sshHosts.length + ')</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;margin-bottom:var(--space-4);">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_host_name','Name') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_host_address','Host') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_username','Username') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_device_type','Type') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_group','Group') + '</th>';
      html += '<th style="text-align:center;padding:4px 8px;">' + t('lbl_status','Status') + '</th>';
      html += '<th style="padding:4px 8px;"></th>';
      html += '</tr></thead><tbody>';
      sshHosts.forEach(function(h) {
        var statusColor = h.is_reachable === true ? 'var(--green)' : h.is_reachable === false ? 'var(--red)' : 'var(--text-dim)';
        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(h.label) + '</td>';
        html += '<td style="padding:4px 8px;font-family:var(--mono);font-size:11px;">' + esc(h.hostname) + ':' + Number(h.port) + '</td>';
        html += '<td style="padding:4px 8px;">' + esc(h.username) + '</td>';
        html += '<td style="padding:4px 8px;">' + esc(h.device_type) + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(h.group_name || '-') + '</td>';
        html += '<td style="padding:4px 8px;text-align:center;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';"></span></td>';
        html += '<td style="padding:4px 8px;"><button class="btn btn-ghost" data-write data-click-handler="sshTerminal" data-id="' + esc(h.id) + '" style="padding:1px 6px;font-size:10px;color:var(--blue);">SSH</button></td>';
        html += '</tr>';
      });
      html += '</tbody></table>';
    }

    // VPN Profiles
    if (vpnProfiles.length) {
      var protocolLabels = {wireguard:'WireGuard', openvpn:'OpenVPN', azure:'Azure P2S', fortigate_ipsec:'FortiGate IPsec'};
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">' + t('hdr_vpn_profiles','VPN Profiles') + ' (' + vpnProfiles.length + ')</div>';
      html += '<div style="display:flex;flex-wrap:wrap;gap:var(--space-3);margin-bottom:var(--space-4);">';
      vpnProfiles.forEach(function(p) {
        var protoLabel = protocolLabels[p.protocol] || p.protocol;
        html += '<div style="display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3);background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);font-size:var(--font-xs);">';
        html += '<span style="font-weight:600;">' + esc(p.name) + '</span>';
        html += '<span style="color:var(--text-muted);">' + esc(protoLabel) + '</span>';
        html += '<button class="btn btn-ghost" data-write data-click-handler="vpnConnect" data-id="' + esc(p.id) + '" style="padding:1px 6px;font-size:10px;color:var(--green);">' + t('vpn_connect','Connect') + '</button>';
        html += '</div>';
      });
      html += '</div>';
    }

    // FortiGate + UniFi side by side
    if (fg || uf) {
      html += '<div style="display:grid;grid-template-columns:' + (fg && uf ? '1fr 1fr' : '1fr') + ';gap:var(--space-4);">';
      if (fg) {
        html += '<div style="padding:var(--space-3);background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);">';
        html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">FortiGate</div>';
        html += '<div style="font-size:var(--font-xs);display:grid;grid-template-columns:70px 1fr;gap:2px var(--space-2);">';
        html += '<span style="color:var(--text-muted);">' + t('host') + '</span><span style="font-family:var(--mono);">' + esc(fg.host) + '</span>';
        html += '<span style="color:var(--text-muted);">' + t('port') + '</span><span>' + Number(fg.port) + '</span>';
        html += '<span style="color:var(--text-muted);">VDOM</span><span>' + esc(fg.vdom) + '</span>';
        html += '</div></div>';
      }
      if (uf) {
        html += '<div style="padding:var(--space-3);background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);">';
        html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">UniFi</div>';
        html += '<div style="font-size:var(--font-xs);display:grid;grid-template-columns:70px 1fr;gap:2px var(--space-2);">';
        html += '<span style="color:var(--text-muted);">' + t('host') + '</span><span style="font-family:var(--mono);">' + esc(uf.host) + '</span>';
        html += '<span style="color:var(--text-muted);">' + t('site') + '</span><span>' + esc(uf.site) + '</span>';
        html += '<span style="color:var(--text-muted);">' + t('mode') + '</span><span>' + esc(uf.mode) + '</span>';
        html += '</div></div>';
      }
      html += '</div>';
    }

    html += '</div>';
    el.innerHTML = html;
  } catch(e) {
    el.style.display = 'none';
  }
}

// ── Network Inventory Card ──────────────────────────────────────────────────

async function _loadCustomerNetworkInventory(customerId) {
  var el = document.getElementById('customer-network-panel');
  if (!el) return;
  try {
    var d = await apiFetch('/api/dashboard/network-inventory/' + encodeURIComponent(customerId));
    if (!d) { el.style.display = 'none'; return; }

    var tot = d.totals || {};
    var hasDevices = (tot.aps || 0) + (tot.switches || 0) + (tot.gateways || 0) + (tot.firewalls || 0) > 0;
    if (!hasDevices) { el.style.display = 'none'; return; }

    var devs = d.devices || {};
    var alerts = d.alerts || [];

    // Header with device count summary
    var html = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-4);">';
    html += '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;">' + t('hdr_network_inventory','Network') + '</div>';
    html += '<div style="display:flex;gap:var(--space-4);font-size:var(--font-xs);color:var(--text-muted);">';
    if (tot.aps) html += '<span>' + Number(tot.aps) + ' ' + t('lbl_aps','APs') + '</span>';
    if (tot.switches) html += '<span>' + Number(tot.switches) + ' ' + t('lbl_switches','Switches') + '</span>';
    if (tot.gateways) html += '<span>' + Number(tot.gateways) + ' ' + t('lbl_gateways','Gateways') + '</span>';
    if (tot.firewalls) html += '<span>' + Number(tot.firewalls) + ' ' + t('lbl_firewalls','Firewalls') + '</span>';
    if (tot.total_clients) html += '<span>' + Number(tot.total_clients) + ' ' + t('lbl_total_clients','Clients') + '</span>';
    html += '</div></div>';

    // Alerts
    if (alerts.length > 0) {
      html += '<div style="margin-bottom:var(--space-4);">';
      for (var i = 0; i < alerts.length; i++) {
        var alertColor = alerts[i].indexOf('outdated') >= 0 ? 'var(--orange)' : alerts[i].indexOf('port usage') >= 0 ? 'var(--orange)' : 'var(--red)';
        html += '<div style="font-size:var(--font-xs);color:' + alertColor + ';padding:4px 0;">' + esc(alerts[i]) + '</div>';
      }
      html += '</div>';
    }

    // APs table
    if (devs.aps && devs.aps.length) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);margin-top:var(--space-3);">' + t('lbl_aps','Access Points') + '</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_device','Device') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_model','Model') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_firmware','Firmware') + '</th>';
      html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_clients','Clients') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_status','Status') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_capacity','Capacity') + '</th>';
      html += '</tr></thead><tbody>';
      for (let i = 0; i < devs.aps.length; i++) {
        var ap = devs.aps[i];
        let statusColor = ap.status === 'online' ? 'var(--green)' : 'var(--red)';
        let fwColor = (ap.fw_status === 'warning' || ap.fw_status === 'critical') ? 'var(--orange)' : 'var(--text)';
        var clientPct = Math.min(100, Math.round((ap.clients / 60) * 100));
        let barColor = clientPct > 80 ? 'var(--red)' : clientPct > 60 ? 'var(--orange)' : 'var(--green)';
        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(ap.name) + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(ap.model) + '</td>';
        html += '<td style="padding:4px 8px;color:' + fwColor + ';">' + esc(ap.firmware) + (ap.fw_status === 'warning' || ap.fw_status === 'critical' ? '' : '') + '</td>';
        html += '<td style="padding:4px 8px;text-align:right;font-weight:600;">' + (Number(ap.clients) || 0) + '</td>';
        html += '<td style="padding:4px 8px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';margin-right:4px;"></span>' + esc(ap.status) + '</td>';
        html += '<td style="padding:4px 8px;min-width:80px;"><div style="background:var(--bg-alt);border-radius:4px;height:6px;overflow:hidden;"><div style="width:' + clientPct + '%;height:100%;background:' + barColor + ';border-radius:4px;"></div></div></td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // Switches table
    if (devs.switches && devs.switches.length) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);margin-top:var(--space-4);">' + t('lbl_switches','Switches') + '</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_device','Device') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_model','Model') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_firmware','Firmware') + '</th>';
      html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_ports','Ports') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_status','Status') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_port_usage','Port usage') + '</th>';
      html += '</tr></thead><tbody>';
      for (let i = 0; i < devs.switches.length; i++) {
        var sw = devs.switches[i];
        let statusColor = sw.status === 'online' ? 'var(--green)' : 'var(--red)';
        let fwColor = (sw.fw_status === 'warning' || sw.fw_status === 'critical') ? 'var(--orange)' : 'var(--text)';
        var portPct = sw.ports_total > 0 ? Math.round((sw.ports_used / sw.ports_total) * 100) : 0;
        let barColor = portPct > 85 ? 'var(--red)' : portPct > 70 ? 'var(--orange)' : 'var(--green)';
        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(sw.name) + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(sw.model) + '</td>';
        html += '<td style="padding:4px 8px;color:' + fwColor + ';">' + esc(sw.firmware) + (sw.fw_status === 'warning' || sw.fw_status === 'critical' ? '' : '') + '</td>';
        html += '<td style="padding:4px 8px;text-align:right;font-weight:600;">' + Number(sw.ports_used) + '/' + Number(sw.ports_total) + '</td>';
        html += '<td style="padding:4px 8px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';margin-right:4px;"></span>' + esc(sw.status) + '</td>';
        html += '<td style="padding:4px 8px;min-width:80px;"><div style="background:var(--bg-alt);border-radius:4px;height:6px;overflow:hidden;"><div style="width:' + portPct + '%;height:100%;background:' + barColor + ';border-radius:4px;"></div></div></td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // Gateways table
    if (devs.gateways && devs.gateways.length) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);margin-top:var(--space-4);">' + t('lbl_gateways','Gateways') + '</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_device','Device') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_model','Model') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_firmware','Firmware') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_status','Status') + '</th>';
      html += '</tr></thead><tbody>';
      for (let i = 0; i < devs.gateways.length; i++) {
        var gw = devs.gateways[i];
        let statusColor = gw.status === 'online' ? 'var(--green)' : 'var(--red)';
        let fwColor = (gw.fw_status === 'warning' || gw.fw_status === 'critical') ? 'var(--orange)' : 'var(--text)';
        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(gw.name) + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(gw.model) + '</td>';
        html += '<td style="padding:4px 8px;color:' + fwColor + ';">' + esc(gw.firmware) + (gw.fw_status === 'warning' || gw.fw_status === 'critical' ? '' : '') + '</td>';
        html += '<td style="padding:4px 8px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';margin-right:4px;"></span>' + esc(gw.status) + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // Firewalls table
    if (devs.firewalls && devs.firewalls.length) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);margin-top:var(--space-4);">' + t('lbl_firewalls','Firewalls') + '</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_device','Device') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_model','Model') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_firmware','Firmware') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_ha_status','HA') + '</th>';
      html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_vpn_tunnels','VPN') + '</th>';
      html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_sessions','Sessions') + '</th>';
      html += '</tr></thead><tbody>';
      for (let i = 0; i < devs.firewalls.length; i++) {
        var fw = devs.firewalls[i];
        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(fw.name) + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(fw.model) + '</td>';
        html += '<td style="padding:4px 8px;">' + esc(fw.firmware) + '</td>';
        html += '<td style="padding:4px 8px;">' + esc(fw.ha || 'standalone') + '</td>';
        html += '<td style="padding:4px 8px;text-align:right;font-weight:600;">' + (Number(fw.vpn_tunnels) || 0) + '</td>';
        html += '<td style="padding:4px 8px;text-align:right;">' + (Number(fw.active_sessions) || 0).toLocaleString() + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // Placeholder divs for FortiGate threat summary and firewall audit
    if (tot.firewalls > 0) {
      html += '<div id="fg-threat-summary-panel" style="margin-top:var(--space-4);"><div class="text-sm text-muted">' + t('msg_loading_threats','Loading threat summary...') + '</div></div>';
      html += '<div id="fg-firewall-audit-panel" style="margin-top:var(--space-4);"><div class="text-sm text-muted">' + t('msg_loading_fw_audit','Loading firewall audit...') + '</div></div>';
    }

    // Placeholder divs for UniFi client inventory and WiFi health
    html += '<div id="unifi-clients-section"></div>';
    html += '<div id="unifi-wifi-health-section"></div>';

    el.innerHTML = html;

    // Load FortiGate threat summary and firewall audit if firewalls exist
    if (tot.firewalls > 0) {
      _loadFgThreatSummary(customerId);
      _loadFgFirewallAudit(customerId);
    }

    // Load UniFi client inventory and WiFi health in parallel
    _loadUnifiClientsSection(customerId);
    _loadUnifiWifiHealthSection(customerId);

  } catch(e) {
    // Network inventory is optional — hide silently if it fails
    if (el) el.style.display = 'none';
    console.debug('Network inventory load failed:', e);
  }
}

// ── FortiGate Threat Summary ───────────────────────────────────────────────

async function _loadFgThreatSummary(customerId) {
  var el = document.getElementById('fg-threat-summary-panel');
  if (!el) return;
  try {
    var d = await apiFetch('/api/fortigate/threats/' + encodeURIComponent(customerId));
    if (!d || !d.summary) { el.style.display = 'none'; return; }

    // A refused log read reports unavailable with total=null. Rendering it would
    // print "Total: 0" — a firewall with a clean threat log nobody could read.
    if (d.unavailable || d.summary.total === null || d.summary.total === undefined) {
      el.style.display = '';
      el.innerHTML = '<div class="text-xs text-muted">' +
        esc(t('msg_block_unavailable','{block} could not be read, so this picture is incomplete.')
          .replace('{block}', t('hdr_threat_summary','Threat Summary'))) + '</div>';
      return;
    }

    var s = d.summary;
    var html = '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">' + t('hdr_threat_summary','Threat Summary') + ' <span style="font-weight:400;text-transform:none;">(' + Number(d.period_days) + ' ' + t('lbl_days','days') + ')</span></div>';

    // Summary badges
    html += '<div style="display:flex;gap:var(--space-3);margin-bottom:var(--space-3);flex-wrap:wrap;">';
    html += '<div style="padding:6px 12px;border-radius:var(--radius-md);background:rgba(239,68,68,0.15);color:var(--red);font-size:var(--font-xs);font-weight:600;">' + t('sev_critical','Critical') + ': ' + (Number(s.critical) || 0) + '</div>';
    html += '<div style="padding:6px 12px;border-radius:var(--radius-md);background:rgba(249,115,22,0.15);color:var(--orange);font-size:var(--font-xs);font-weight:600;">' + t('sev_high','High') + ': ' + (Number(s.high) || 0) + '</div>';
    html += '<div style="padding:6px 12px;border-radius:var(--radius-md);background:rgba(234,179,8,0.15);color:#eab308;font-size:var(--font-xs);font-weight:600;">' + t('sev_medium','Medium') + ': ' + (Number(s.medium) || 0) + '</div>';
    html += '<div style="padding:6px 12px;border-radius:var(--radius-md);background:rgba(128,128,128,0.12);color:var(--text-muted);font-size:var(--font-xs);font-weight:600;">' + t('sev_low','Low') + ': ' + (Number(s.low) || 0) + '</div>';
    html += '<div style="padding:6px 12px;border-radius:var(--radius-md);background:var(--bg-alt);color:var(--text);font-size:var(--font-xs);font-weight:600;">' + t('lbl_total','Total') + ': ' + (Number(s.total) || 0) + '</div>';
    html += '</div>';

    // By type
    if (d.by_type && Object.keys(d.by_type).length > 0) {
      html += '<div style="display:flex;gap:var(--space-3);margin-bottom:var(--space-3);font-size:var(--font-xs);color:var(--text-muted);">';
      var typeLabels = {ips:'IPS', virus:'Antivirus', botnet:'Botnet', webfilter:'Web Filter'};
      for (var tkey in d.by_type) {
        html += '<span>' + (typeLabels[tkey] || esc(tkey)) + ': <strong style="color:var(--text);">' + Number(d.by_type[tkey]) + '</strong></span>';
      }
      html += '</div>';
    }

    // Recent events table (top 5 visible, rest collapsible)
    var recent = d.recent || [];
    if (recent.length > 0) {
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_time','Time') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_type','Type') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_severity','Severity') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_source_ip','Source IP') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_attack','Attack') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_action','Action') + '</th>';
      html += '</tr></thead><tbody>';
      var sevColors = {critical:'var(--red)', high:'var(--orange)', medium:'#eab308', low:'var(--text-muted)'};
      for (var i = 0; i < recent.length; i++) {
        var ev = recent[i];
        var rowStyle = i >= 5 ? 'display:none;' : '';
        var rowClass = i >= 5 ? 'fg-threat-extra' : '';
        html += '<tr class="' + rowClass + '" style="border-bottom:1px solid var(--border-dim);' + rowStyle + '">';
        html += '<td style="padding:4px 8px;font-family:var(--mono);font-size:11px;">' + esc(ev.timestamp) + '</td>';
        html += '<td style="padding:4px 8px;">' + esc(ev.type) + '</td>';
        html += '<td style="padding:4px 8px;"><span style="color:' + (sevColors[ev.severity] || 'var(--text)') + ';font-weight:600;">' + esc(ev.severity) + '</span></td>';
        html += '<td style="padding:4px 8px;font-family:var(--mono);font-size:11px;">' + esc(ev.srcip) + '</td>';
        html += '<td style="padding:4px 8px;">' + esc(ev.attack) + '</td>';
        html += '<td style="padding:4px 8px;"><span style="color:' + (ev.action === 'blocked' || ev.action === 'block' || ev.action === 'drop' ? 'var(--green)' : 'var(--orange)') + ';">' + esc(ev.action) + '</span></td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
      if (recent.length > 5) {
        html += '<button class="btn btn-ghost" style="font-size:var(--font-xs);margin-top:var(--space-2);padding:2px 8px;" data-click-handler="cdToggleFgThreatRows" data-less-label="' + esc(t('btn_show_less','Show less')) + '" data-all-label="' + esc(t('btn_show_all','Show all') + ' (' + recent.length + ')') + '">' + t('btn_show_all','Show all') + ' (' + recent.length + ')</button>';
      }
    }

    el.innerHTML = html;
  } catch(e) {
    if (el) el.innerHTML = '';
    console.debug('Threat summary load failed:', e);
  }
}

// ── FortiGate Firewall Rule Audit ──────────────────────────────────────────

async function _loadFgFirewallAudit(customerId) {
  var el = document.getElementById('fg-firewall-audit-panel');
  if (!el) return;
  try {
    var d = await apiFetch('/api/fortigate/firewall-audit/' + encodeURIComponent(customerId));
    if (!d || d.total_rules === undefined) { el.style.display = 'none'; return; }

    // An unreachable firewall reports unavailable with score/total_rules = null
    // (which is not === undefined, so the guard above lets it through). Rendering
    // it would show "null / 100" in red with a green "no issues" — a broken,
    // reassuring panel for a firewall nobody could read.
    if (d.unavailable || d.total_rules === null || d.score === null) {
      el.style.display = '';
      el.innerHTML = '<div class="text-xs text-muted">' +
        esc(t('msg_block_unavailable','{block} could not be read, so this picture is incomplete.')
          .replace('{block}', t('hdr_firewall_audit','Firewall Rule Audit'))) + '</div>';
      return;
    }

    // Score color
    var scoreColor = d.score >= 90 ? 'var(--green)' : d.score >= 70 ? 'var(--orange)' : 'var(--red)';

    var html = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3);">';
    html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;">' + t('hdr_firewall_audit','Firewall Rule Audit') + '</div>';
    html += '<div style="display:flex;align-items:baseline;gap:4px;">';
    html += '<span style="font-size:24px;font-weight:700;color:' + scoreColor + ';">' + Number(d.score) + '</span>';
    html += '<span style="font-size:var(--font-xs);color:var(--text-muted);">/ 100</span>';
    html += '</div></div>';

    // Stats row
    html += '<div style="display:flex;gap:var(--space-4);margin-bottom:var(--space-3);font-size:var(--font-xs);color:var(--text-muted);">';
    html += '<span>' + t('lbl_total_rules','Total rules') + ': <strong style="color:var(--text);">' + Number(d.total_rules) + '</strong></span>';
    html += '<span>' + t('lbl_enabled','Enabled') + ': <strong style="color:var(--text);">' + Number(d.enabled) + '</strong></span>';
    html += '<span>' + t('lbl_disabled_rules','Disabled') + ': <strong style="color:var(--text);">' + Number(d.disabled) + '</strong></span>';
    html += '<span>' + t('lbl_unused_rules','Unused') + ': <strong style="color:var(--text);">' + Number(d.unused_rules) + '</strong></span>';
    html += '</div>';

    // Issues table
    var issues = d.issues || [];
    if (issues.length > 0) {
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_policy','Policy') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_issue','Issue') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_severity','Severity') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('col_detail','Detail') + '</th>';
      html += '</tr></thead><tbody>';
      var issuePillColors = {any_any:'var(--red)', no_logging:'var(--orange)', unused:'var(--blue)', scheduled:'var(--blue)'};
      var issuePillBg = {any_any:'rgba(239,68,68,0.15)', no_logging:'rgba(249,115,22,0.15)', unused:'rgba(59,130,246,0.15)', scheduled:'rgba(59,130,246,0.15)'};
      var sevPillColors = {critical:'var(--red)', warning:'var(--orange)', info:'var(--blue)'};
      var sevPillBg = {critical:'rgba(239,68,68,0.15)', warning:'rgba(249,115,22,0.15)', info:'rgba(59,130,246,0.15)'};
      var issueLabels = {any_any: t('issue_any_any','Any-Any'), no_logging: t('issue_no_logging','No Logging'), unused: t('issue_unused','Unused'), scheduled: t('issue_scheduled','Scheduled')};
      for (var i = 0; i < issues.length; i++) {
        var iss = issues[i];
        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">#' + Number(iss.policy_id) + ' ' + esc(iss.name) + '</td>';
        html += '<td style="padding:4px 8px;"><span style="display:inline-block;padding:2px 8px;border-radius:var(--radius-full);font-size:11px;font-weight:600;color:' + (issuePillColors[iss.issue] || 'var(--text)') + ';background:' + (issuePillBg[iss.issue] || 'var(--bg-alt)') + ';">' + (issueLabels[iss.issue] || esc(iss.issue)) + '</span></td>';
        html += '<td style="padding:4px 8px;"><span style="display:inline-block;padding:2px 8px;border-radius:var(--radius-full);font-size:11px;font-weight:600;color:' + (sevPillColors[iss.severity] || 'var(--text)') + ';background:' + (sevPillBg[iss.severity] || 'var(--bg-alt)') + ';">' + esc(iss.severity) + '</span></td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(iss.detail) + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    } else {
      html += '<div style="font-size:var(--font-xs);color:var(--green);padding:var(--space-2) 0;">' + t('msg_no_fw_issues','No firewall policy issues detected.') + '</div>';
    }

    el.innerHTML = html;
  } catch(e) {
    if (el) el.innerHTML = '';
    console.debug('Firewall audit load failed:', e);
  }
}

// ── UniFi Client Inventory Section ─────────────────────────────────────────

function _signalBars(dbm) {
  if (dbm === null || dbm === undefined) return '';
  var abs = Math.abs(dbm);
  // Color: green >-60 (abs<60), orange -60 to -75 (60-75), red <-75 (>75)
  var color = abs < 60 ? 'var(--green)' : abs <= 75 ? 'var(--orange)' : 'var(--red)';
  // 4-bar indicator
  var bars = abs < 55 ? 4 : abs < 65 ? 3 : abs < 75 ? 2 : 1;
  var h = '';
  for (var b = 1; b <= 4; b++) {
    var ht = 4 + b * 3;
    var bg = b <= bars ? color : 'var(--border)';
    h += '<span style="display:inline-block;width:3px;height:' + ht + 'px;background:' + bg + ';border-radius:1px;margin-right:1px;vertical-align:bottom;"></span>';
  }
  h += '<span style="font-size:10px;color:var(--text-muted);margin-left:3px;">' + Number(dbm) + '</span>';
  return h;
}

async function _loadUnifiClientsSection(customerId) {
  var el = document.getElementById('unifi-clients-section');
  if (!el) return;
  try {
    var d = await apiFetch('/api/unifi/clients/' + encodeURIComponent(customerId));
    if (!d || !d.ok || !d.clients || d.clients.length === 0) return;

    var clients = d.clients;
    var wireless = d.wireless || 0;
    var wired = d.wired || 0;

    var summary = t('lbl_devices_summary', '{total} devices ({wireless} wireless, {wired} wired)')
      .replace('{total}', clients.length)
      .replace('{wireless}', wireless)
      .replace('{wired}', wired);

    var html = '<div style="margin-top:var(--space-5);border-top:1px solid var(--border);padding-top:var(--space-4);">';
    html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3);cursor:pointer;" data-click-handler="cdToggleUnifiClients">';
    html += '<div>';
    html += '<span style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;">' + t('hdr_connected_clients','Connected Clients') + '</span>';
    html += '<span style="font-size:var(--font-xs);color:var(--text-muted);margin-left:var(--space-3);">' + esc(summary) + '</span>';
    html += '</div>';
    html += '<span id="unifi-clients-toggle" style="font-size:var(--font-xs);color:var(--blue);cursor:pointer;">' + t('lbl_show_clients','Show clients') + '</span>';
    html += '</div>';

    // Collapsible table (hidden by default)
    html += '<table id="unifi-clients-table" style="display:none;width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
    html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
    html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_hostname','Hostname') + '</th>';
    html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_ip_address','IP') + '</th>';
    html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_mac_address','MAC') + '</th>';
    html += '<th style="text-align:center;padding:4px 8px;">' + t('lbl_type','Type') + '</th>';
    html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_signal','Signal') + '</th>';
    html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_bandwidth','Bandwidth') + '</th>';
    html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_connected_to','Connected to') + '</th>';
    html += '</tr></thead><tbody>';

    for (var i = 0; i < clients.length; i++) {
      var c = clients[i];
      var displayName = esc(c.name || c.hostname || c.mac);
      var typeIcon = c.type === 'wireless'
        ? '<span title="WiFi" style="color:var(--blue);">&#9678;</span>'
        : '<span title="Ethernet" style="color:var(--text-muted);">&#9644;</span>';
      var signalHtml = c.type === 'wireless' ? _signalBars(c.signal) : '<span style="color:var(--text-dim);">&#8212;</span>';
      var bw = _formatBytes((c.rx_bytes || 0) + (c.tx_bytes || 0));

      html += '<tr style="border-bottom:1px solid var(--border-dim);">';
      html += '<td style="padding:4px 8px;font-weight:500;">' + displayName + '</td>';
      html += '<td style="padding:4px 8px;font-family:var(--mono);font-size:11px;">' + esc(c.ip || '') + '</td>';
      html += '<td style="padding:4px 8px;font-family:var(--mono);font-size:11px;color:var(--text-muted);">' + esc(c.mac || '') + '</td>';
      html += '<td style="padding:4px 8px;text-align:center;">' + typeIcon + '</td>';
      html += '<td style="padding:4px 8px;">' + signalHtml + '</td>';
      html += '<td style="padding:4px 8px;text-align:right;color:var(--text-muted);">' + bw + '</td>';
      html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(c.connected_to || '') + '</td>';
      html += '</tr>';
    }

    html += '</tbody></table></div>';
    el.innerHTML = html;
  } catch(e) {
    console.debug('UniFi clients load failed:', e);
  }
}

// ── UniFi WiFi Health Section ──────────────────────────────────────────────

async function _loadUnifiWifiHealthSection(customerId) {
  var el = document.getElementById('unifi-wifi-health-section');
  if (!el) return;
  try {
    var d = await apiFetch('/api/unifi/wifi-health/' + encodeURIComponent(customerId));
    if (!d || !d.ok) return;

    var aps = d.aps || [];
    var ssids = d.ssids || [];
    var alerts = d.alerts || [];

    if (aps.length === 0 && ssids.length === 0 && alerts.length === 0) return;

    var html = '<div style="margin-top:var(--space-5);border-top:1px solid var(--border);padding-top:var(--space-4);">';
    html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-3);">' + t('hdr_wifi_health','WiFi Health') + '</div>';

    // Alerts
    if (alerts.length > 0) {
      html += '<div style="margin-bottom:var(--space-4);">';
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">' + t('hdr_alerts_wifi','WiFi Alerts') + ' (' + alerts.length + ')</div>';
      for (let i = 0; i < Math.min(alerts.length, 15); i++) {
        var a = alerts[i];
        var alertColor = a.type === 'rogue_ap' ? 'var(--red)' : 'var(--orange)';
        var alertLabel = a.type === 'rogue_ap' ? t('lbl_rogue_ap','Rogue AP')
          : a.type === 'high_interference' ? t('lbl_high_interference','High interference')
          : t('lbl_poor_satisfaction','Poor satisfaction');
        html += '<div style="font-size:var(--font-xs);color:' + alertColor + ';padding:2px 0;">';
        html += '<span style="font-weight:600;">' + esc(alertLabel) + ':</span> ' + esc(a.message);
        html += '</div>';
      }
      if (alerts.length > 15) {
        html += '<div style="font-size:var(--font-xs);color:var(--text-muted);padding:2px 0;">+ ' + (alerts.length - 15) + ' more...</div>';
      }
      html += '</div>';
    }

    // Per-AP health table
    if (aps.length > 0) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">' + t('hdr_ap_health','Access Point Health') + '</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;margin-bottom:var(--space-4);">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_device','Device') + '</th>';
      html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_clients','Clients') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_channel','Channel') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_satisfaction','Satisfaction') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_status','Status') + '</th>';
      html += '</tr></thead><tbody>';

      for (let i = 0; i < aps.length; i++) {
        var ap = aps[i];
        var satPct = ap.satisfaction != null ? Number(ap.satisfaction) : null;
        var satColor = satPct === null ? 'var(--text-dim)' : satPct >= 80 ? 'var(--green)' : satPct >= 70 ? 'var(--orange)' : 'var(--red)';
        var satBar = '';
        if (satPct !== null) {
          satBar = '<div style="display:flex;align-items:center;gap:var(--space-2);">';
          satBar += '<div style="flex:1;max-width:80px;background:var(--bg-alt);border-radius:4px;height:6px;overflow:hidden;">';
          satBar += '<div style="width:' + satPct + '%;height:100%;background:' + satColor + ';border-radius:4px;"></div></div>';
          satBar += '<span style="color:' + satColor + ';font-weight:600;">' + satPct + '%</span></div>';
        } else {
          satBar = '<span style="color:var(--text-dim);">&#8212;</span>';
        }
        var statusColor = ap.status === 'online' ? 'var(--green)' : 'var(--red)';

        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(ap.name) + '</td>';
        html += '<td style="padding:4px 8px;text-align:right;font-weight:600;">' + (Number(ap.clients) || 0) + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(ap.channels || '') + '</td>';
        html += '<td style="padding:4px 8px;">' + satBar + '</td>';
        html += '<td style="padding:4px 8px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';margin-right:4px;"></span>' + esc(ap.status) + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // SSID list
    if (ssids.length > 0) {
      html += '<div style="font-size:var(--font-xs);font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:var(--space-2);">' + t('hdr_ssid_list','SSIDs') + '</div>';
      html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
      html += '<thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);">';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_ssid','SSID') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_security','Security') + '</th>';
      html += '<th style="text-align:right;padding:4px 8px;">' + t('lbl_clients','Clients') + '</th>';
      html += '<th style="text-align:left;padding:4px 8px;">' + t('lbl_status','Status') + '</th>';
      html += '</tr></thead><tbody>';

      for (let i = 0; i < ssids.length; i++) {
        var s = ssids[i];
        var enabledLabel = s.enabled ? t('lbl_enabled','Enabled') : t('lbl_disabled','Disabled');
        var enabledColor = s.enabled ? 'var(--green)' : 'var(--text-dim)';
        var guestBadge = s.is_guest ? ' <span style="background:var(--blue);color:#fff;padding:0 4px;border-radius:3px;font-size:10px;">' + t('lbl_guest','Guest') + '</span>' : '';

        html += '<tr style="border-bottom:1px solid var(--border-dim);">';
        html += '<td style="padding:4px 8px;font-weight:500;">' + esc(s.name) + guestBadge + '</td>';
        html += '<td style="padding:4px 8px;color:var(--text-muted);">' + esc(s.security) + '</td>';
        html += '<td style="padding:4px 8px;text-align:right;font-weight:600;">' + (Number(s.clients) || 0) + '</td>';
        html += '<td style="padding:4px 8px;color:' + enabledColor + ';">' + esc(enabledLabel) + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    html += '</div>';
    el.innerHTML = html;
  } catch(e) {
    console.debug('UniFi WiFi health load failed:', e);
  }
}

async function openLatestReport() {
  try {
    var d = await apiFetch('/api/latest-report');
    if (d && d.has_report) { openReportViewer(d.url); }
    else { showToast(t('msg_no_report','No report found. Run an audit first.'), 'warning'); }
  } catch(e) { showToast(t('status_error'), 'error'); }
}

function copyCustomerSummary() {
  // Build text summary from visible KPIs
  var name = document.getElementById('active-customer-name')?.textContent || '';
  var domain = document.getElementById('active-customer-domain')?.textContent || '';
  var grade = document.getElementById('active-customer-grade')?.textContent || '';
  var lines = [
    name + (domain ? ' (' + domain + ')' : ''),
    '---',
  ];
  // Get KPIs from customer detail gauges if visible
  document.querySelectorAll('#customer-detail-content .card').forEach(function(card) {
    var label = card.querySelector('[style*="uppercase"]');
    var value = card.querySelector('[style*="font-weight:800"], [style*="font-weight: 800"]');
    if (label && value) lines.push(label.textContent.trim() + ': ' + value.textContent.trim());
  });
  if (grade) lines.splice(1, 0, t('lbl_grade') + ': ' + grade);
  var text = lines.join('\n');
  navigator.clipboard.writeText(text).then(function() {
    showToast(t('msg_copied','Kopiert til utklippstavle'), 'success', 2000);
  }).catch(function() {
    showToast(t('err_copy_failed','Kunne ikke kopiere'), 'error');
  });
}

async function _loadCustomerNotes() {
  // Held from before the request: if another customer's page replaces this
  // one meanwhile, the answer lands in a detached box, not in that page's,
  // where saving would have written it into the wrong customer's notes.
  var ta = document.getElementById('detail-notes-textarea');
  var el = document.getElementById('detail-notes-status');
  try {
    var d = await apiFetch('/api/customer/notes');
    if (!ta || !ta.isConnected) return;
    if (d) { ta.value = d.notes || ''; }
    if (d && d.last_saved) {
      if (el) el.textContent = t('msg_last_saved','Sist lagret') + ': ' + new Date(d.last_saved).toLocaleString('no-NO',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
    }
  } catch(e) { console.warn('Customer notes load failed:', e); }
}

async function _loadCustomerActivity(customerName) {
  var el = document.getElementById('customer-activity-panel');
  if (!el) return;
  try {
    var d = await apiFetch('/api/activity-log?limit=15&customer=' + encodeURIComponent(customerName));
    var entries = d.entries || [];
    var actionIcons = {
      audit_started:'\u25B6', audit_completed:'\u2713', report_generated:'',
      email_sent:'', remediation_updated:'', backup_created:'',
      customer_switched:'', settings_changed:'', itglue_uploaded:'',
    };
    var html = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3);">'
      + '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;">' + t('hdr_activity_log') + '</div>'
      + '<span style="font-size:var(--font-xs);color:var(--text-dim);">' + t('lbl_last_prefix','Last:') + ' ' + entries.length + '</span></div>';
    if (entries.length === 0) {
      html += '<div style="font-size:var(--font-sm);color:var(--text-dim);padding:var(--space-2) 0;">' + t('msg_no_notifications','Ingen hendelser') + '</div>';
    } else {
      entries.forEach(function(e) {
        var icon = actionIcons[e.action] || '';
        var ts = e.timestamp ? timeAgo(e.timestamp) : '';
        html += '<div style="display:flex;gap:var(--space-3);padding:var(--space-2) 0;border-bottom:1px solid var(--border);font-size:var(--font-xs);">'
          + '<span style="flex-shrink:0;">' + icon + '</span>'
          + '<span style="flex:1;color:var(--text);">' + esc(e.action.replace(/_/g,' ')) + (e.detail ? ' · <span style="color:var(--text-muted);">' + esc(e.detail) + '</span>' : '') + '</span>'
          + '<span style="color:var(--text-dim);white-space:nowrap;">' + esc(ts) + (e.user ? ' · ' + esc(e.user) : '') + '</span>'
          + '</div>';
      });
    }
    el.innerHTML = html;
  } catch(e) { el.innerHTML = ''; }
}

// Its own name and element ids: the M365-status view renders a notes box too,
// views are hidden rather than destroyed, and sharing ids made this page read
// and save the hidden box's text over what was typed here.
async function saveDetailNotes() {
  var ta = document.getElementById('detail-notes-textarea');
  if (!ta) return;
  var st = document.getElementById('detail-notes-status');
  try {
    var d = await apiFetch('/api/customer/notes', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({notes:ta.value})});
    if (d && d.ok && st) { st.textContent = t('msg_saved','Lagret') + ' ✓'; st.style.color = 'var(--green)'; setTimeout(function(){ st.style.color = ''; },2000); }
  } catch(e) { if (st) { st.textContent = t('status_error'); st.style.color = 'var(--red)'; } }
}

var _gaugeInstances = [];
function _renderGauges(riskScore, mfaPct, ssPct) {
  if (typeof Chart === 'undefined') return;
  _gaugeInstances.forEach(function(c){ c.destroy(); });
  _gaugeInstances = [];

  function makeGauge(canvasId, value, maxVal) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || value === null || value === undefined || value === '-') return;
    var v = parseFloat(value);
    var pct = Math.min(100, Math.max(0, (v / maxVal) * 100));
    var color = pct >= 80 ? '#3fb950' : pct >= 60 ? '#4d9fb5' : pct >= 40 ? '#d29922' : '#f85149';
    var bg = getComputedStyle(document.documentElement).getPropertyValue('--border').trim();
    var g = new Chart(canvas, {
      type: 'doughnut',
      data: {
        datasets: [{
          data: [pct, 100 - pct],
          backgroundColor: [color, bg],
          borderWidth: 0,
          circumference: 270,
          rotation: 225,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: true, cutout: '75%',
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
      },
      plugins: [{
        id: 'gaugeText',
        afterDraw: function(chart) {
          var ctx = chart.ctx;
          var w = chart.width, h = chart.height;
          ctx.save();
          ctx.font = 'bold 16px Inter, sans-serif';
          ctx.fillStyle = color;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(Math.round(v) + (maxVal === 100 ? '%' : ''), w/2, h/2 + 4);
          ctx.restore();
        }
      }]
    });
    _gaugeInstances.push(g);
  }

  makeGauge('gauge-risk', riskScore, 100);
  makeGauge('gauge-mfa', mfaPct, 100);
  makeGauge('gauge-ss', ssPct, 100);
}

async function _loadCustomerTrendChart(customerId) {
  if (_detailChartInstance) { _detailChartInstance.destroy(); _detailChartInstance = null; }

  try {
    var d = await apiFetch('/api/trends/' + encodeURIComponent(customerId));
    var entries = d.entries || [];
    var body = document.getElementById('cust-trend-body');
    if (!body) return;
    // A trend needs two points. Below that the card is one line, not a
    // chart-sized frame around a sentence.
    if (entries.length < 2) {
      body.innerHTML = '<p class="cust-trend-empty">' + esc(t('msg_not_enough_data', 'Trenden vises når kunden har minst to kjøringer.')) + '</p>';
      return;
    }
    if (typeof Chart === 'undefined') return;
    body.innerHTML = '<div class="cust-trend-chart"><canvas id="chart-customer-trend"></canvas></div>';

    var labels = entries.map(function(e){ return e.date ? e.date.substring(0,10) : ''; });
    var textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim();
    var gridColor = getComputedStyle(document.documentElement).getPropertyValue('--border').trim();

    _detailChartInstance = new Chart(document.getElementById('chart-customer-trend'), {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: t('lbl_risk') || 'Risikoscore',
            data: entries.map(function(e){ return e.risk_score; }),
            borderColor: '#4d9fb5', backgroundColor: 'rgba(77,159,181,0.1)',
            fill: true, tension: 0.3, pointRadius: 4, pointHoverRadius: 6,
          },
          {
            label: 'MFA %',
            data: entries.map(function(e){ return e.mfa_pct; }),
            borderColor: '#3fb950', backgroundColor: 'transparent',
            borderDash: [4,4], tension: 0.3, pointRadius: 3,
          },
          {
            label: 'Secure Score %',
            data: entries.map(function(e){ return e.secure_score_pct; }),
            borderColor: '#d29922', backgroundColor: 'transparent',
            borderDash: [8,4], tension: 0.3, pointRadius: 3,
          },
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { position: 'bottom', labels: { color: textColor, padding: 16, font: { size: 12 }, usePointStyle: true } },
          tooltip: { backgroundColor: 'rgba(0,0,0,0.8)', titleFont: { size: 13 }, bodyFont: { size: 12 } },
        },
        scales: {
          y: { min: 0, max: 100, grid: { color: gridColor }, ticks: { color: textColor, font: { size: 11 } } },
          x: { grid: { display: false }, ticks: { color: textColor, font: { size: 11 }, maxRotation: 45 } },
        }
      }
    });
  } catch(e) { /* trend chart is non-critical */ }
}

// ── Customer Licenses (ALSO Cloud) ───────────────────────────────────────────

var _currentAlsoAccountId = '';

function loadCustomerLicensesFromActive() {
  // Find the current customer's also_account_id from cached overview
  if (!_overviewData || !_overviewData.customers) return;
  var active = _overviewData.customers.find(function(c){ return c.is_active; });
  if (active && active.also_account_id) {
    loadCustomerLicenses(active.also_account_id);
  } else {
    showToast(t('also_no_account_linked','This customer is not linked to ALSO Cloud'), 'warning');
  }
}

async function loadCustomerLicenses(accountId) {
  _currentAlsoAccountId = accountId;
  var box = document.getElementById('customer-detail-content');
  if (!box) return;

  box.innerHTML = '<div style="text-align:center;padding:48px;color:var(--text-muted);"><div class="loader" style="width:24px;height:24px;margin:0 auto 16px;"></div>' + t('msg_loading_licenses','Loading licenses...') + '</div>';

  try {
    var d = await apiFetch('/api/also/subscriptions/' + encodeURIComponent(accountId));
    var subs = d.subscriptions || [];

    if (subs.length === 0) {
      box.innerHTML = '<div class="card" style="padding:var(--space-8);text-align:center;color:var(--text-dim);">'
        + '<div style="font-size:48px;margin-bottom:var(--space-4);"></div>'
        + '<div style="font-size:var(--font-lg);font-weight:600;margin-bottom:var(--space-2);">' + t('also_no_licenses','No licenses found') + '</div>'
        + '<div style="font-size:var(--font-sm);">' + t('also_no_licenses_desc','This customer has no active subscriptions in ALSO Cloud.') + '</div>'
        + '</div>';
      return;
    }

    // Calculate totals
    var totalSeats = 0;
    var activeCount = 0;
    subs.forEach(function(s) {
      var qty = Number(s.Quantity || s.quantity || s.SeatCount) || 0;
      totalSeats += qty;
      var st = (s.AccountState || s.Status || s.status || '').toLowerCase();
      if (st === 'active' || st === 'completed') activeCount++;
    });

    var html = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-4);flex-wrap:wrap;gap:var(--space-3);">'
      + '<div style="font-size:var(--font-xl);font-weight:700;">' + t('nav_licenses','Licenses') + '</div>'
      + '<div style="display:flex;gap:var(--space-4);">'
      + '<div class="card" style="padding:var(--space-3) var(--space-4);text-align:center;min-width:100px;">'
      + '<div style="font-size:var(--font-2xl);font-weight:800;color:var(--blue);">' + subs.length + '</div>'
      + '<div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">' + t('also_subscriptions','Subscriptions') + '</div></div>'
      + '<div class="card" style="padding:var(--space-3) var(--space-4);text-align:center;min-width:100px;">'
      + '<div style="font-size:var(--font-2xl);font-weight:800;color:var(--green);">' + activeCount + '</div>'
      + '<div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">' + t('active') + '</div></div>'
      + (totalSeats > 0 ? '<div class="card" style="padding:var(--space-3) var(--space-4);text-align:center;min-width:100px;">'
      + '<div style="font-size:var(--font-2xl);font-weight:800;color:var(--purple);">' + totalSeats + '</div>'
      + '<div style="font-size:var(--font-xs);color:var(--text-muted);text-transform:uppercase;">' + t('also_total_seats','Total Seats') + '</div></div>' : '')
      + '</div></div>';

    // Table
    html += '<div class="card" style="padding:0;overflow:hidden;">'
      + '<table style="width:100%;border-collapse:collapse;font-size:var(--font-sm);">'
      + '<thead><tr style="background:var(--bg-tertiary);border-bottom:1px solid var(--border);">'
      + '<th style="text-align:left;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('also_product','Product') + '</th>'
      + '<th style="text-align:left;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('vendor') + '</th>'
      + '<th style="text-align:center;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('qty') + '</th>'
      + '<th style="text-align:center;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('term') + '</th>'
      + '<th style="text-align:center;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('started') + '</th>'
      + '<th style="text-align:center;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('renews') + '</th>'
      + '<th style="text-align:center;padding:var(--space-3) var(--space-4);font-weight:600;color:var(--text-muted);font-size:var(--font-xs);text-transform:uppercase;">' + t('also_status','Status') + '</th>'
      + '</tr></thead><tbody>';

    subs.forEach(function(s, i) {
      var name = s.ServiceDisplayName || s.ProductName || s.Name || s.SubscriptionName || s.OfferName || '-';
      var vendor = s.VendorDisplayName || s.Vendor || '';
      var started = s.BillingStartDate ? esc(s.BillingStartDate.slice(0,10)) : '-';
      var renews = s.ContractEndDate ? s.ContractEndDate.slice(0,10) : '-';
      var status = s.AccountState || s.Status || s.status || 'Active';
      var statusLower = status.toLowerCase();
      var statusColor = statusLower === 'active' ? 'var(--green)' : statusLower === 'suspended' ? 'var(--red)' : statusLower === 'completed' ? 'var(--green)' : 'var(--orange)';
      var rowBg = i % 2 === 0 ? 'transparent' : 'var(--bg-tertiary)';
      var subId = s.AccountId || '';

      // Calculate term from date span
      var termLabel = '-';
      var termIcon = '';
      // Determine term from service name patterns first (most reliable),
      // then fall back to ContractEndDate-based calculation using remaining time
      var nameLower = (name || '').toLowerCase();

      // NCE products: Monthly if name contains "monthly", otherwise Annual (default NCE term)
      if (nameLower.indexOf('(nce)') !== -1) {
        if (nameLower.indexOf('monthly') !== -1) { termLabel = 'Monthly'; termIcon = ''; }
        else { termLabel = 'Annual'; termIcon = ''; }
      }
      // Monthly subscriptions (Letsignit, Printix, etc)
      else if (nameLower.indexOf('monthly') !== -1) { termLabel = 'Monthly'; termIcon = ''; }
      // Azure Plan / Reserved Instance
      else if (nameLower.indexOf('azure plan') !== -1 && nameLower.indexOf('reserved') === -1) { termLabel = 'Pay-as-you-go'; termIcon = ''; }
      else if (nameLower.indexOf('reserved') !== -1) { termLabel = 'Reserved'; termIcon = ''; }
      // Organization tenant (no term)
      else if (nameLower.indexOf('tenant') !== -1) { termLabel = 'Tenant'; termIcon = ''; }
      // Adobe yearly
      else if (nameLower.indexOf('adobe') !== -1) { termLabel = 'Annual'; termIcon = ''; }
      // Fallback: use ContractEndDate vs now to estimate remaining term
      else if (s.ContractEndDate) {
        var endD = new Date(s.ContractEndDate);
        var nowD = new Date();
        var remMonths = (endD.getFullYear() - nowD.getFullYear()) * 12 + (endD.getMonth() - nowD.getMonth());
        if (remMonths <= 1) { termLabel = 'Monthly'; termIcon = ''; }
        else if (remMonths <= 14) { termLabel = 'Annual'; termIcon = ''; }
        else if (remMonths <= 38) { termLabel = '3-Year'; termIcon = ''; }
        else { termLabel = 'Long-term'; termIcon = ''; }
      }

      // Days until renewal
      var renewHtml = esc(renews);
      if (renews !== '-') {
        var daysLeft = Math.round((new Date(renews) - new Date()) / 86400000);
        var renewColor = daysLeft < 0 ? 'var(--red)' : daysLeft < 30 ? 'var(--orange)' : 'var(--text-muted)';
        renewHtml = esc(renews) + ' <span style="font-size:10px;color:'+renewColor+';">(' + (daysLeft < 0 ? 'expired' : daysLeft + 'd') + ')</span>';
      }

      var termColor = termLabel === 'Monthly' ? 'var(--blue)' : termLabel === 'Annual' ? 'var(--purple)' : 'var(--text-muted)';

      var qty = Number(s.Quantity || s.quantity || s.SeatCount) || 0;

      html += '<tr style="background:' + rowBg + ';border-bottom:1px solid var(--border);cursor:pointer;" data-click-handler="alsoToggleSubDetail" data-sub-id="'+esc(subId)+'">'
        + '<td style="padding:var(--space-3) var(--space-4);font-weight:500;">' + esc(name) + '</td>'
        + '<td style="padding:var(--space-3) var(--space-4);color:var(--text-muted);">' + esc(vendor) + '</td>'
        + '<td style="padding:var(--space-3) var(--space-4);text-align:center;font-weight:700;">' + (qty > 0 ? qty : '<span style="color:var(--text-dim);">-</span>') + '</td>'
        + '<td style="padding:var(--space-3) var(--space-4);text-align:center;"><span style="font-size:var(--font-xs);font-weight:600;color:'+termColor+';">'+termIcon+' '+termLabel+'</span></td>'
        + '<td style="padding:var(--space-3) var(--space-4);text-align:center;font-size:var(--font-xs);color:var(--text-dim);">' + started + '</td>'
        + '<td style="padding:var(--space-3) var(--space-4);text-align:center;font-size:var(--font-xs);">' + renewHtml + '</td>'
        + '<td style="padding:var(--space-3) var(--space-4);text-align:center;"><span style="display:inline-block;padding:2px 10px;border-radius:var(--radius-full);font-size:var(--font-xs);font-weight:600;color:#fff;background:' + statusColor + ';">' + esc(status) + '</span></td>'
        + '</tr>';
      // Detail row (hidden by default, loaded on click)
      html += '<tr id="also-sub-'+esc(subId)+'" style="display:none;"><td colspan="7" style="padding:0;"></td></tr>';
    });

    html += '</tbody></table></div>';

    box.innerHTML = html;
  } catch(e) {
    box.innerHTML = '<div class="alert alert-error">' + t('also_license_error','Failed to load licenses') + ': ' + esc(e.message) + '</div>';
  }
}

// ── Unified Customer Dashboard ──────────────────────────────────────────────

async function loadUnifiedDashboard() {
  var custId = _customersActiveId;
  if (!custId) { showToast(t('err_no_active_customer'), 'warning'); return; }

  // Use the home view container
  showView('home');
  var el = document.getElementById('home-content') || document.querySelector('.view[id="view-home"] > div') || document.getElementById('view-home');
  if (!el) return;
  el.innerHTML = '<div class="loader" style="width:24px;height:24px;margin:48px auto;"></div>';

  var d = await apiFetch('/api/customer/' + encodeURIComponent(custId) + '/unified');
  if (!d || d.error) { el.innerHTML = '<div style="color:var(--red);text-align:center;padding:48px;">'+esc(d&&d.error||'Failed')+'</div>'; return; }

  var html = '';

  var a = d.audit || {};
  var _grade = a.risk_grade || '-';
  var _gv = {A:'var(--green)',B:'var(--blue)',C:'var(--orange)',D:'var(--red)',F:'var(--red)'}[_grade] || 'var(--text-muted)';
  // Label colour for the tinted hero tile — see --*-deep in app.css.
  var _gvd = {A:'var(--green-deep)',B:'var(--blue-deep)',C:'var(--orange-deep)',D:'var(--red-deep)',F:'var(--red-deep)'}[_grade] || 'var(--text-muted)';

  // ── Hero ──
  var _meta = [];
  if (d.domain) _meta.push('<span style="font-family:var(--mono);">'+esc(d.domain)+'</span>');
  if (d.also_account_id) _meta.push('ALSO ID ' + esc(String(d.also_account_id)));
  if (d.source) _meta.push(esc(d.source));
  html += '<div class="cd-hero">'
    + '<span class="cd-hero-tile" style="color:'+_gvd+';background:color-mix(in srgb, '+_gv+' 12%, transparent);border-color:color-mix(in srgb, '+_gv+' 40%, transparent);">'+esc(_grade)+'</span>'
    + '<span class="cd-hero-id"><span class="cd-hero-name">'+esc(d.customer_name)+' <span class="cd-active-pill">' + t('aktiv_kunde') + '</span></span>'
    + '<span class="cd-hero-meta">'+_meta.join(' · ')+'</span></span>'
    + '<div style="flex:1;"></div>'
    + '<button class="context-ghost" data-click-handler="openLatestReport">' + t('btn_open_report','Åpne rapport') + '</button>'
    + '<button class="context-ghost" data-click-handler="showView" data-view="history">' + t('nav_history','Historikk') + '</button>'
    + '<button class="btn btn-sm" style="padding:7px 16px;font-size:12px;background:var(--blue-btn);color:#fff;border:none;border-radius:var(--radius-md);font-weight:600;cursor:pointer;" data-click-handler="showView" data-view="audit">' + t('btn_run_audit','Kjør audit') + '</button>'
    + '</div>';

  // ── Integration chips ──
  // Where a chip or an action button leads. Callers name an entry, so the
  // attribute markup stays in this table and never travels with data.
  var _cdClicks = {
    home: 'data-click-handler="showView" data-view="home"',
    audit: 'data-click-handler="showView" data-view="audit"',
    hosts: 'data-click-handler="showView" data-view="hosts"',
    licenses: 'data-click-handler="loadCustomerLicensesFromActive"',
  };
  function _cdChip(name, color, status, opts) {
    opts = opts || {};
    return '<div class="cd-chip"' + (opts.id ? ' id="'+esc(opts.id)+'"' : '') + ' style="border-top-color:'+esc(color)+';' + (opts.click ? 'cursor:pointer;' : '') + '"' + (opts.click ? ' '+_cdClicks[opts.click] : '') + '>'
      + '<div class="cd-chip-name">'+esc(name)+'</div>'
      + '<div class="cd-chip-status" style="color:'+esc(color)+';">'+esc(status)+'</div></div>';
  }
  var _m365c = 'var(--text-dim)', _m365l = t('st_not_configured');
  if (d.m365 && d.m365.TenantId) { _m365c = 'var(--green)'; _m365l = t('st_configured'); }
  if (d.m365 && d.m365.secret_status === 'expired') { _m365c = 'var(--red)'; _m365l = t('st_secret_expired'); }
  else if (d.m365 && d.m365.secret_status === 'warning') { _m365c = 'var(--orange)'; _m365l = t('st_secret_days_left').replace('{days}', d.m365.secret_days_left); }
  var _fgc = d.fortigate ? 'var(--green)' : 'var(--text-dim)';
  var _fgl = d.fortigate ? (d.fortigate.FortiGateHost || t('st_configured_2','Konfigurert')) : t('st_not_configured_2','Ikke konfigurert');
  var _ufc = d.unifi ? 'var(--green)' : 'var(--text-dim)';
  var _ufl = d.unifi ? (d.unifi.UniFiHost || t('st_configured_2','Konfigurert')) : t('st_not_configured_2','Ikke konfigurert');
  // A block the server could not read is null, exactly like a block with
  // nothing in it — the difference is in d.unavailable. Rendering both as
  // "Ikke koblet" is what let a database hiccup show a customer as clean.
  var _gone = d.unavailable || {};
  function _failed(block) { return Object.prototype.hasOwnProperty.call(_gone, block); }

  var _aoc = d.also ? 'var(--green)' : 'var(--text-dim)';
  var _aol = d.also ? (d.also.total_subscriptions + ' subs' + (d.also.mrr > 0 ? ' · ' + d.also.mrr.toFixed(0) + ' ' + (d.also.currency||'kr') : '')) : t('st_not_linked','Ikke koblet');
  if (d.also && (d.also.expired > 0 || d.also.expiring_90d > 0)) { _aoc = d.also.expired > 0 ? 'var(--red)' : 'var(--orange)'; }
  if (_failed('also')) { _aoc = 'var(--orange)'; _aol = t('st_read_failed'); }
  var _sshN = d.ssh_hosts ? d.ssh_hosts.length : 0;
  var _sshc = _sshN > 0 ? 'var(--green)' : 'var(--text-dim)';
  var _sshl = _sshN ? _sshN + ' ' + t('lbl_hosts_short') : t('st_none');
  if (_failed('ssh_hosts')) { _sshc = 'var(--orange)'; _sshl = t('st_read_failed'); }
  html += '<div class="cd-chips">'
    + _cdChip('M365', _m365c, _m365l, {click:'home'})
    + _cdChip('FortiGate', _fgc, _fgl)
    + _cdChip('UniFi', _ufc, _ufl)
    + _cdChip('ALSO', _aoc, _aol, {click:'licenses'})
    + _cdChip(t('lbl_ssh_hosts'), _sshc, _sshl, {click:'hosts'})
    + _cdChip('Hosting', 'var(--text-dim)', t('st_loading','Laster…'), {id:'unified-uniweb-status'})
    + '</div>';

  // ── What this page could not read ──
  // Placed above "Krever handling" on purpose. That band is built from the
  // audit figures, so when the audit read fails it renders empty — a customer
  // with no findings and a customer whose findings could not be loaded looked
  // identical, and the reassuring one was the wrong answer.
  var _blockNames = {audit: t('blk_audit'), ssh_hosts: t('blk_ssh_hosts'), also: t('blk_also')};
  var _goneKeys = Object.keys(_gone);
  if (_goneKeys.length) {
    html += '<div class="cd-action-band" style="border-left:3px solid var(--orange);">'
      + '<div class="cd-action-title">' + esc(t('hdr_incomplete_data')) + '</div>';
    _goneKeys.forEach(function(k) {
      var label = _blockNames[k] || k;
      html += '<div class="cd-action-row"><span class="cd-dot" style="background:var(--orange);"></span>'
        + '<span class="cd-action-text">'
        + esc(t('msg_block_unavailable').replace('{block}', label))
        + '</span></div>';
    });
    html += '</div>';
  }

  // ── «Krever handling» — cross-source findings, actioned where the decision is made ──
  var _find = [];
  if ((a.users_no_mfa || 0) > 0) _find.push({sev:'crit', text: t('find_users_no_mfa').replace('{count}', a.users_no_mfa), src:t('src_m365_audit'), label:t('lbl_see_audit'), click:'audit'});
  if (d.m365 && d.m365.secret_days_left != null && d.m365.secret_days_left <= 60) _find.push({sev: d.m365.secret_days_left <= 14 ? 'crit' : 'warn', text: t('find_secret_expiring').replace('{days}', d.m365.secret_days_left), src:'M365', label:'M365-status', click:'home'});
  if (d.also && d.also.expired > 0) _find.push({sev:'crit', text: t('find_subs_expired').replace('{count}', d.also.expired), src:'ALSO', label:t('lbl_see_subscriptions'), click:'licenses'});
  if (d.also && d.also.expiring_90d > 0) _find.push({sev:'warn', text: t('find_subs_expiring').replace('{count}', d.also.expiring_90d), src:'ALSO', label:t('lbl_see_subscriptions'), click:'licenses'});
  if (_find.length) {
    html += '<div class="cd-action-band"><div class="cd-action-title">' + esc(t('hdr_needs_action')) + '</div>';
    _find.forEach(function(f) {
      var _dc = f.sev === 'crit' ? 'var(--red)' : 'var(--orange)';
      html += '<div class="cd-action-row"><span class="cd-dot" style="background:'+_dc+';"></span>'
        + '<span class="cd-action-text">'+esc(f.text)+'</span>'
        + '<span class="cd-action-src">'+esc(f.src)+'</span>'
        + '<button class="cd-action-btn" '+_cdClicks[f.click]+'>'+esc(f.label)+'</button></div>';
    });
    html += '</div>';
  }

  // ── Two columns: audit summary + M365 creds | subscriptions + hosts ──
  html += '<div class="cd-cols"><div class="cd-col">';

  if (d.audit) {
    var _ssc = (a.secure_score_pct||0) >= 70 ? 'var(--green)' : (a.secure_score_pct||0) >= 40 ? 'var(--orange)' : 'var(--red)';
    var _mfc = (a.mfa_coverage_pct||0) >= 90 ? 'var(--green)' : (a.mfa_coverage_pct||0) >= 70 ? 'var(--orange)' : 'var(--red)';
    var _nmc = (a.users_no_mfa||0) > 0 ? 'var(--red)' : 'var(--green)';
    html += '<div class="cd-card"><div class="cd-card-title">' + t('siste_m365_audit') + ' <span class="sub">'+esc(a.audit_date||'')+'</span><span class="link" data-click-handler="openLatestReport">' + t('full_rapport') + '</span></div>'
      + '<div class="cd-stat-grid">'
      + '<div class="cd-stat"><div class="n" style="color:'+_gv+';">'+esc(_grade)+'</div><div class="l">' + t('grade') + '</div></div>'
      + '<div class="cd-stat"><div class="n">'+Math.round(a.risk_score||0)+'</div><div class="l">' + t('risikoscore') + '</div></div>'
      + '<div class="cd-stat"><div class="n" style="color:'+_ssc+';">'+Math.round(a.secure_score_pct||0)+'%</div><div class="l">' + t('secure_score_3') + '</div></div>'
      + '<div class="cd-stat"><div class="n" style="color:'+_mfc+';">'+Math.round(a.mfa_coverage_pct||0)+'%</div><div class="l">MFA</div></div>'
      + '<div class="cd-stat"><div class="n">'+(Number(a.total_users)||0)+'</div><div class="l">' + t('brukere') + '</div></div>'
      + '<div class="cd-stat"><div class="n" style="color:'+_nmc+';">'+(Number(a.users_no_mfa)||0)+'</div><div class="l">' + t('uten_mfa') + '</div></div>'
      + '</div></div>';
  }

  if (d.m365 && d.m365.TenantId) {
    var _cred = '<span>' + t('tenant') + ' <b class="mono">'+esc(d.m365.TenantId||'-')+'</b></span>'
      + '<span>' + t('domene_2') + ' <b class="mono">'+esc(d.domain||'-')+'</b></span>';
    if (d.m365.secret_days_left != null) {
      var _sc = (d.m365.secret_status==='expired'||d.m365.secret_status==='critical') ? 'var(--red)' : d.m365.secret_status==='warning' ? 'var(--orange)' : 'var(--green)';
      _cred += '<span>' + t('secret_utloeper') + ' <b style="color:'+_sc+';">'+Number(d.m365.secret_days_left)+' d</b></span>';
    }
    if (d.m365.cert_days_left != null) {
      var _cc2 = (d.m365.cert_status==='expired'||d.m365.cert_status==='critical') ? 'var(--red)' : d.m365.cert_status==='warning' ? 'var(--orange)' : 'var(--green)';
      _cred += '<span>' + t('sertifikat_utloeper') + ' <b style="color:'+_cc2+';">'+Number(d.m365.cert_days_left)+' d</b></span>';
    }
    html += '<div class="cd-card"><div class="cd-card-title">' + t('m_legitimasjon') + '</div><div class="cd-creds">'+_cred+'</div></div>';
  }

  html += '</div><div class="cd-col">';

  if (d.also && d.also.renewals && d.also.renewals.length) {
    var _rens = d.also.renewals;
    var _crit = _rens.filter(function(r){ return r.days_left != null && r.days_left <= 90; }).sort(function(x,y){ return (x.days_left||0) - (y.days_left||0); });
    var _restN = _rens.filter(function(r){ return r.days_left == null || r.days_left > 90; }).length;
    html += '<div class="cd-card"><div class="cd-card-title">' + t('abonnementer_2') + ' <span class="sub">'+_rens.length+' totalt'+(d.also.mrr > 0 ? ' · MRR '+d.also.mrr.toFixed(0)+' '+esc(d.also.currency||'kr') : '')+'</span></div>';
    if (_crit.length) {
      _crit.forEach(function(r, i) {
        var _dc = r.days_left < 0 ? 'var(--red)' : r.days_left <= 30 ? 'var(--red)' : 'var(--orange)';
        var _dl = r.days_left < 0 ? t('st_expired') : Number(r.days_left) + ' d';
        html += '<div class="cd-row'+(i === 0 ? ' first' : '')+'"><span class="grow">'+esc(r.service_display)+'</span><span class="vendor">'+esc(r.vendor||'')+'</span><span class="days" style="color:'+_dc+';">'+_dl+'</span></div>';
      });
    } else {
      html += '<div style="font-size:12px;color:var(--text-muted);padding:6px 0;">' + esc(t('msg_none_expiring_soon')) + '</div>';
    }
    if (_restN) html += '<div style="font-size:11px;color:var(--text-muted);padding-top:8px;border-top:1px solid var(--row-divider);margin-top:2px;">'+esc(t('lbl_others_over_90d').replace('{count}', _restN))+'</div>';
    html += '</div>';
  }

  if (d.ssh_hosts && d.ssh_hosts.length) {
    html += '<div class="cd-card"><div class="cd-card-title">' + t('hosts') + ' <span class="sub">'+d.ssh_hosts.length+'</span></div>';
    d.ssh_hosts.forEach(function(h, i) {
      var _hc = h.is_reachable ? 'var(--green)' : 'var(--text-dim)';
      html += '<div class="cd-row'+(i === 0 ? ' first' : '')+'"><span class="cd-dot" style="background:'+_hc+';"></span><span class="grow">'+esc(h.label||h.hostname)+'</span><span class="mono">'+esc(h.hostname)+':'+esc(String(h.port))+'</span><button class="cd-row-btn" data-click-handler="showView" data-view="hosts">' + t('aapne') + '</button></div>';
    });
    html += '</div>';
  }

  html += '</div></div>';

  // Placeholder for async Uniweb detail card
  html += '<div id="unified-uniweb-card"></div>';

  el.innerHTML = html;

  // Fetch Uniweb data async
  _unifiedLoadUniwebCard(custId);
}

async function _unifiedLoadUniwebCard(custId) {
  var statusEl = document.getElementById('unified-uniweb-status');
  var cardEl = document.getElementById('unified-uniweb-card') || document.getElementById('customer-uniweb-panel');

  try {
    var uw = await apiFetch('/api/uniweb/customer/' + encodeURIComponent(custId));
    if (!uw || !uw.matched) {
      if (statusEl) {
        statusEl.style.borderTopColor = 'var(--text-dim)';
        statusEl.querySelector('div:last-child').textContent = t('st_not_linked','Ikke koblet');
        statusEl.querySelector('div:last-child').style.color = 'var(--text-dim)';
      }
      return;
    }

    // Update status card
    var uwColor = 'var(--green)';
    var uwLabel = (uw.domains ? uw.domains.length : 0) + ' ' + t('domener');
    if (uw.monthly_total > 0) uwLabel += ' \u00b7 ' + uw.monthly_total.toFixed(0) + ' ' + t('kr_mnd');
    if (statusEl) {
      statusEl.style.borderTopColor = uwColor;
      statusEl.querySelector('div:last-child').textContent = uwLabel;
      statusEl.querySelector('div:last-child').style.color = uwColor;
    }

    // Build detail card
    if (!cardEl) return;

    // Helper: check if a date string is within N days from now
    function _uwDaysUntil(dateStr) {
      if (!dateStr || dateStr === '-') return null;
      try {
        var d = new Date(dateStr);
        if (isNaN(d.getTime())) return null;
        return Math.ceil((d.getTime() - Date.now()) / 86400000);
      } catch(e) { return null; }
    }

    function _uwRelativeTime(dateStr) { return timeAgo(dateStr); }

    // Section divider helper
    function _uwSection(icon, title) {
      return '<div style="display:flex;align-items:center;gap:6px;font-weight:600;font-size:12px;margin:14px 0 6px;padding-bottom:4px;border-bottom:1px solid var(--border);">'
        + '<span style="font-size:14px;opacity:0.7;">' + esc(icon) + '</span>'
        + '<span>' + esc(title) + '</span></div>';
    }

    var h = '';
    h += '<div class="card" style="padding:16px;margin-bottom:16px;">';

    // Header with last updated
    h += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">';
    h += '<div style="display:flex;align-items:center;gap:8px;">';
    h += '<span style="font-size:18px;"></span>';
    h += '<span style="font-size:14px;font-weight:600;">' + t('hosting_uniweb') + '</span>';
    h += '</div>';
    h += '<div style="display:flex;flex-direction:column;align-items:flex-end;gap:2px;">';
    h += '<div style="font-size:11px;color:var(--text-muted);">' + esc(uw.account_name) + (uw.account_id ? ' \u00b7 ID: ' + esc(uw.account_id) : '') + '</div>';
    if (uw.last_sync) {
      h += '<div style="font-size:10px;color:var(--text-dim);" title="' + esc(new Date(uw.last_sync).toLocaleString(_lang === 'en' ? 'en-GB' : 'nb-NO')) + '">' + t('lbl_last_updated','Sist oppdatert') + ': ' + esc(_uwRelativeTime(uw.last_sync)) + '</div>';
    }
    h += '</div></div>';

    // Summary metrics row
    h += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:8px;margin-bottom:4px;">';

    h += '<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px;">';
    h += '<div style="font-size:18px;font-weight:700;">' + (uw.domains ? uw.domains.length : 0) + '</div>';
    h += '<div style="font-size:10px;color:var(--text-muted);">' + t('domener') + '</div></div>';

    h += '<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px;">';
    h += '<div style="font-size:18px;font-weight:700;">' + (uw.subscriptions ? uw.subscriptions.length : 0) + '</div>';
    h += '<div style="font-size:10px;color:var(--text-muted);">' + t('abonnementer') + '</div></div>';

    h += '<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px;">';
    h += '<div style="font-size:18px;font-weight:700;color:var(--blue);">' + (uw.monthly_total > 0 ? uw.monthly_total.toFixed(0) : '0') + '</div>';
    h += '<div style="font-size:10px;color:var(--text-muted);">' + t('kr_mnd') + '</div></div>';

    h += '<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px;">';
    h += '<div style="font-size:18px;font-weight:700;">' + (uw.email ? uw.email.length : 0) + '</div>';
    h += '<div style="font-size:10px;color:var(--text-muted);">' + t('e_post_2') + '</div></div>';

    h += '<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px;">';
    h += '<div style="font-size:18px;font-weight:700;">' + (uw.ssl ? uw.ssl.length : 0) + '</div>';
    h += '<div style="font-size:10px;color:var(--text-muted);">SSL</div></div>';

    h += '</div>';

    // Domains table
    if (uw.domains && uw.domains.length) {
      h += _uwSection('', t('domener'));
      h += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:10px;">';
      h += '<thead><tr style="border-bottom:1px solid var(--border);">';
      h += '<th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('domene') + '</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">DNS</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('registrert') + '</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('lbl_expires') + '</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('status') + '</th>';
      h += '</tr></thead><tbody>';
      uw.domains.forEach(function(dom) {
        var domName = dom.domain || dom[''] || Object.values(dom)[0] || '';
        var dnsCount = dom.dns && Array.isArray(dom.dns) ? dom.dns.length : null;
        var regDate = dom.registered || dom.registration_date || dom.created || '';
        var expiryDays = _uwDaysUntil(dom.expiry);
        var expiryStyle = '';
        if (expiryDays !== null && expiryDays <= 30) {
          expiryStyle = expiryDays <= 7 ? 'color:var(--red);font-weight:600;' : 'color:var(--orange);font-weight:600;';
        }
        h += '<tr style="border-bottom:1px solid var(--border);cursor:pointer;" data-click-handler="uwToggleDns" data-domain="' + esc(domName) + '">';
        h += '<td style="padding:4px 6px;color:var(--blue);"><span class="uw-dns-arrow" style="display:inline-block;transition:transform 0.15s;font-size:9px;margin-right:4px;">&#9654;</span>' + esc(domName) + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;color:var(--text-dim);">' + (dnsCount !== null ? '<span style="background:var(--bg);padding:1px 6px;border-radius:8px;font-size:10px;">' + dnsCount + '</span>' : '-') + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;color:var(--text-dim);font-size:10px;">' + esc(regDate || '-') + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;' + expiryStyle + '">' + esc(dom.expiry || '-') + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;">' + esc(dom.status || '-') + '</td>';
        h += '</tr>';
      });
      h += '</tbody></table>';
    }

    // Subscriptions table
    if (uw.subscriptions && uw.subscriptions.length) {
      h += _uwSection('', t('abonnementer'));
      h += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:10px;">';
      h += '<thead><tr style="border-bottom:1px solid var(--border);">';
      h += '<th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('tjeneste') + '</th>';
      h += '<th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('bruker_domene') + '</th>';
      h += '<th style="text-align:right;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('pris_mnd') + '</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('fornyelse') + '</th>';
      h += '</tr></thead><tbody>';
      uw.subscriptions.forEach(function(sub) {
        var price = sub['Price per month'] || sub.price_monthly || sub['Price per month'] || '-';
        var renewal = sub['Renewed until'] || sub.renewal_date || sub['Renewed until'] || '-';
        var renewDays = _uwDaysUntil(renewal);
        var renewStyle = '';
        var renewBg = '';
        if (renewDays !== null && renewDays <= 30) {
          if (renewDays <= 0) {
            renewStyle = 'color:var(--red);font-weight:700;';
            renewBg = 'background:rgba(220,53,69,0.08);';
          } else if (renewDays <= 7) {
            renewStyle = 'color:var(--red);font-weight:600;';
            renewBg = 'background:rgba(220,53,69,0.05);';
          } else {
            renewStyle = 'color:var(--orange);font-weight:600;';
            renewBg = 'background:rgba(255,152,0,0.05);';
          }
        }
        h += '<tr style="border-bottom:1px solid var(--border);' + renewBg + '">';
        h += '<td style="padding:4px 6px;">' + esc(sub.service_type || sub.Service || sub['Service type'] || '-') + '</td>';
        h += '<td style="padding:4px 6px;">' + esc(sub.username_domain || sub.Username || sub['Username/domain'] || '-') + '</td>';
        h += '<td style="text-align:right;padding:4px 6px;font-family:var(--mono);">' + esc(price) + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;' + renewStyle + '">' + esc(renewal);
        if (renewDays !== null && renewDays <= 30) {
          h += ' <span style="font-size:9px;opacity:0.8;">(' + (renewDays <= 0 ? t('lbl_expired', 'Expired') + ')'  : renewDays + 'd)') + '</span>';
        }
        h += '</td></tr>';
      });
      h += '</tbody></table>';
    }

    // Email table (proper table instead of just count)
    if (uw.email && uw.email.length) {
      h += _uwSection('', t('uniweb_email_accounts') + ' (' + uw.email.length + ')');
      h += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:10px;">';
      h += '<thead><tr style="border-bottom:1px solid var(--border);">';
      h += '<th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('adresse') + '</th>';
      h += '<th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('type') + '</th>';
      h += '<th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('domene') + '</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('kvote') + '</th>';
      h += '<th style="text-align:center;padding:4px 6px;color:var(--text-muted);font-size:10px;">' + t('status') + '</th>';
      h += '</tr></thead><tbody>';
      uw.email.forEach(function(em) {
        var addr = em.address || em[''] || em.email || em.username || '-';
        var emType = em.type || em.Type || em.product || '-';
        var emDomain = em.domain || (typeof addr === 'string' && addr.indexOf('@') > 0 ? addr.split('@')[1] : '-');
        var quota = em.quota || em.disk_quota || em.size || '';
        var emStatus = em.status || em.state || '-';
        var statusColor = emStatus === 'active' || emStatus === 'aktiv' ? 'var(--green)' : 'var(--text-dim)';
        h += '<tr style="border-bottom:1px solid var(--border);">';
        h += '<td style="padding:4px 6px;font-family:var(--mono);font-size:10px;">' + esc(addr) + '</td>';
        h += '<td style="padding:4px 6px;">' + esc(emType) + '</td>';
        h += '<td style="padding:4px 6px;color:var(--text-dim);">' + esc(emDomain) + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;color:var(--text-dim);">' + esc(quota || '-') + '</td>';
        h += '<td style="text-align:center;padding:4px 6px;"><span style="color:' + statusColor + ';">' + esc(emStatus) + '</span></td>';
        h += '</tr>';
      });
      h += '</tbody></table>';
    }

    // SSL certificates
    if (uw.ssl && uw.ssl.length) {
      h += _uwSection('', t('uniweb_ssl_certificates') + ' (' + uw.ssl.length + ')');
      h += '<details style="font-size:12px;margin-top:2px;"><summary style="cursor:pointer;color:var(--text-muted);font-size:11px;">' + t('vis_detaljer') + '</summary>';
      h += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:4px;">';
      h += '<thead><tr style="border-bottom:1px solid var(--border);">';
      h += '<th style="text-align:left;padding:3px 6px;color:var(--text-muted);font-size:10px;">' + t('domene') + '</th>';
      h += '<th style="text-align:left;padding:3px 6px;color:var(--text-muted);font-size:10px;">' + t('type') + '</th>';
      h += '<th style="text-align:center;padding:3px 6px;color:var(--text-muted);font-size:10px;">' + t('lbl_expires') + '</th>';
      h += '</tr></thead><tbody>';
      uw.ssl.forEach(function(cert) {
        var certDays = _uwDaysUntil(cert.expiry);
        var certStyle = '';
        if (certDays !== null && certDays <= 30) {
          certStyle = certDays <= 7 ? 'color:var(--red);font-weight:600;' : 'color:var(--orange);';
        }
        h += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:3px 6px;">' + esc(cert.domain || '') + '</td><td style="padding:3px 6px;color:var(--text-muted);">' + esc(cert.type || '-') + '</td><td style="text-align:center;padding:3px 6px;' + certStyle + '">' + esc(cert.expiry || '-') + '</td></tr>';
      });
      h += '</tbody></table></details>';
    }

    h += '<div id="uw-cust-ar"></div>';
    h += '<div id="uw-cust-emaildns"></div>';
    h += '</div>';
    cardEl.innerHTML = h;

    // Per-customer AR (outstanding invoices) and the email-security cross-audit,
    // filled async so neither blocks the rest of the card.
    _loadCustomerAr(custId);
    _loadCustomerEmailDns(custId);
  } catch (e) {
    if (statusEl) {
      statusEl.querySelector('div:last-child').textContent = t('lbl_error','Feil');
      statusEl.querySelector('div:last-child').style.color = 'var(--red)';
    }
  }
}

// Per-customer receivables, shown inside the customer's Uniweb card. Rendered
// only when the customer actually owes something — an empty ledger stays quiet
// rather than adding a "nothing owed" block to every customer. A genuine
// failure shows a muted note (never a silent gap that reads as "nothing owed").
async function _loadCustomerAr(custId) {
  var box = document.getElementById('uw-cust-ar');
  if (!box) return;
  try {
    var ar = await apiFetch('/api/uniweb/partner/orders/' + encodeURIComponent(custId));
    if (!ar) throw new Error('Receivables unavailable');
    if (ar.matched === false || (ar.open_count || 0) === 0) { box.innerHTML = ''; return; }
    box.innerHTML = '<div class="uwar-custhead">' + t('uniweb_ar_section', 'Utestående fakturaer') + '</div>' + _uwArBody(ar);
  } catch (e) {
    box.innerHTML = '<div class="uwar-custhead">' + t('uniweb_ar_section', 'Utestående fakturaer') + '</div>'
      + '<div class="uwar-msg">' + t('uniweb_ar_failed', 'Kunne ikke laste faktura-oversikten. Sjekk at Uniweb er konfigurert.') + '</div>';
  }
}

// Email-security cross-audit for the customer's Uniweb-held domains. Shown only
// when there is at least one gap — a clean posture stays quiet — and it marks
// the domains Uniweb hosts the DNS for, where the gap is fixable from here
// (the fix button itself arrives in Phase 3b).
function _ednsChip(status) {
  var cls = status === 'pass' ? 'uwed-ok' : status === 'fail' ? 'uwed-fail'
    : status === 'warn' ? 'uwed-warn' : 'uwed-na';
  return '<span class="uwed-chip ' + cls + '">' + esc(status || '—') + '</span>';
}

function _renderCustomerEmailDns(d) {
  var domains = (d.domains || []).filter(function(x) { return x.gaps && x.gaps.length; });
  var h = '<div class="uwar-custhead">' + t('uniweb_edns_section', 'E-postsikkerhet (DNS)') + '</div>';
  h += '<div class="uwar-panel"><table class="uwar-tbl"><thead><tr>';
  h += '<th>' + t('domene', 'Domene') + '</th>';
  h += '<th class="uwar-c">SPF</th><th class="uwar-c">DMARC</th><th class="uwar-c">DKIM</th>';
  h += '<th class="uwar-c">' + t('status', 'Status') + '</th>';
  h += '</tr></thead><tbody>';
  domains.forEach(function(x) {
    h += '<tr>';
    h += '<td class="uwar-mono">' + esc(x.domain) + '</td>';
    h += '<td class="uwar-c">' + _ednsChip(x.spf) + '</td>';
    h += '<td class="uwar-c">' + _ednsChip(x.dmarc) + '</td>';
    h += '<td class="uwar-c">' + _ednsChip(x.dkim) + '</td>';
    h += '<td class="uwar-c">' + (x.fixable_here
      ? '<span class="uwed-fix">' + t('uniweb_edns_fixable', 'Kan fikses her') + '</span>' : '') + '</td>';
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  if (d.truncated) {
    h += '<div class="uwar-msg">' + t('uniweb_edns_truncated', 'Viser de første domenene.') + '</div>';
  }
  return h;
}

async function _loadCustomerEmailDns(custId) {
  var box = document.getElementById('uw-cust-emaildns');
  if (!box) return;
  try {
    var d = await apiFetch('/api/uniweb/partner/email-dns/' + encodeURIComponent(custId));
    if (!d) throw new Error('Email DNS unavailable');
    if (d.matched === false || (d.with_gaps || 0) === 0) { box.innerHTML = ''; return; }
    box.innerHTML = _renderCustomerEmailDns(d);
  } catch (e) {
    box.innerHTML = '<div class="uwar-custhead">' + t('uniweb_edns_section', 'E-postsikkerhet (DNS)') + '</div>'
      + '<div class="uwar-msg">' + t('uniweb_edns_failed', 'Kunne ikke laste e-postsikkerhetssjekken.') + '</div>';
  }
}

async function uwToggleDns(row, domain) {
  // Check if DNS row already exists below
  var existing = row.nextElementSibling;
  var arrow = row.querySelector('.uw-dns-arrow');
  if (existing && existing.classList.contains('uw-dns-row')) {
    existing.remove();
    if (arrow) arrow.style.transform = 'rotate(0deg)';
    return;
  }

  // Rotate arrow down
  if (arrow) arrow.style.transform = 'rotate(90deg)';

  // Insert loading spinner row
  var cols = row.querySelectorAll('td').length || 5;
  var loadingHtml = '<tr class="uw-dns-row"><td colspan="' + cols + '" style="padding:10px 16px;background:var(--bg);text-align:center;">';
  loadingHtml += '<div class="loader" style="width:14px;height:14px;display:inline-block;vertical-align:middle;"></div>';
  loadingHtml += '<span style="margin-left:8px;font-size:11px;color:var(--text-muted);">' + t('msg_fetching_dns') + '</span>';
  loadingHtml += '</td></tr>';
  row.insertAdjacentHTML('afterend', loadingHtml);
  var loadingRow = row.nextElementSibling;

  // Fetch DNS records
  try {
    var d = await apiFetch('/api/uniweb/dns/' + encodeURIComponent(domain));
    if (!d || !Array.isArray(d.records)) throw new Error('DNS data unavailable');

    var dnsHtml = '<td colspan="' + cols + '" style="padding:8px 16px;background:var(--bg);">';
    if (d && d.records && d.records.length > 0) {
      dnsHtml += '<table style="width:100%;font-size:10px;border-collapse:collapse;">';
      dnsHtml += '<thead><tr style="border-bottom:1px solid var(--border);">';
      dnsHtml += '<th style="text-align:left;padding:2px 6px;color:var(--text-muted);">' + t('vertsnavn') + '</th>';
      dnsHtml += '<th style="text-align:center;padding:2px 6px;color:var(--text-muted);">' + t('type') + '</th>';
      dnsHtml += '<th style="text-align:left;padding:2px 6px;color:var(--text-muted);">' + t('verdi') + '</th>';
      dnsHtml += '<th style="text-align:right;padding:2px 6px;color:var(--text-muted);">TTL</th>';
      dnsHtml += '</tr></thead><tbody>';
      d.records.forEach(function(r) {
        var dnsColors = { 'A': '#4a90d9', 'AAAA': '#4a90d9', 'MX': '#9b59b6', 'CNAME': '#27ae60', 'TXT': '#e67e22', 'NS': '#95a5a6', 'SRV': '#3498db', 'SOA': '#7f8c8d', 'PTR': '#2980b9' };
        var typeColor = dnsColors[r.type] || 'var(--text)';
        var typeBg = r.type === 'A' || r.type === 'AAAA' ? 'rgba(74,144,217,0.1)' : r.type === 'MX' ? 'rgba(155,89,182,0.1)' : r.type === 'CNAME' ? 'rgba(39,174,96,0.1)' : r.type === 'TXT' ? 'rgba(230,126,34,0.1)' : r.type === 'NS' ? 'rgba(149,165,166,0.1)' : 'transparent';
        dnsHtml += '<tr style="border-bottom:1px solid var(--border);">';
        dnsHtml += '<td style="padding:2px 6px;">' + esc(r.hostname) + '</td>';
        dnsHtml += '<td style="text-align:center;padding:2px 6px;"><span style="color:' + typeColor + ';font-weight:600;background:' + typeBg + ';padding:1px 6px;border-radius:3px;font-size:9px;">' + esc(r.type) + '</span></td>';
        dnsHtml += '<td style="padding:2px 6px;font-family:var(--mono);font-size:9px;word-break:break-all;">' + esc(r.value) + '</td>';
        dnsHtml += '<td style="text-align:right;padding:2px 6px;color:var(--text-dim);">' + Number(r.ttl) + '</td></tr>';
      });
      dnsHtml += '</tbody></table>';
    } else {
      dnsHtml += '<span style="color:var(--text-dim);font-size:11px;">' + t('ingen_dns_poster_funnet') + '</span>';
    }
    dnsHtml += '</td>';

    // Replace loading row content
    if (loadingRow && loadingRow.classList.contains('uw-dns-row')) {
      loadingRow.innerHTML = dnsHtml;
    }
  } catch(e) {
    if (loadingRow && loadingRow.classList.contains('uw-dns-row')) {
      loadingRow.innerHTML = '<td colspan="' + cols + '" style="padding:8px 16px;background:var(--bg);"><span style="color:var(--red);font-size:11px;">' + t('feil_ved_henting_av_dns') + '</span></td>';
    }
  }
}

async function alsoToggleSubDetail(rowEl, subId) {
  var detailRow = document.getElementById('also-sub-' + subId);
  if (!detailRow) return;
  if (detailRow.style.display !== 'none') {
    detailRow.style.display = 'none';
    return;
  }
  detailRow.style.display = '';
  var cell = detailRow.querySelector('td');
  cell.innerHTML = '<div style="padding:12px 16px;"><div class="loader" style="width:14px;height:14px;display:inline-block;"></div> ' + t('loading_details') + '</div>';

  var d = await apiFetch('/api/also/subscription/' + encodeURIComponent(subId));
  if (!d || d.error) {
    cell.innerHTML = '<div style="padding:12px 16px;color:var(--red);font-size:12px;">' + esc(d && d.error || 'Failed to load') + '</div>';
    return;
  }
  var s = d.subscription || d;
  var fields = s.Fields || s.fields || [];
  var items = s.PriceableItems || s.priceableItems || [];

  var html = '<div style="padding:12px 16px;background:var(--bg);border-left:3px solid var(--blue);">';
  html += '<table style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">';
  html += '<tr><td style="padding:2px 12px 2px 0;white-space:nowrap;">' + t('contract') + '</td><td style="padding:2px 0;font-weight:600;">' + esc(s.ContractId || '-') + '</td></tr>';
  if (s.VendorReferenceId) html += '<tr><td style="padding:2px 12px 2px 0;">' + t('vendor_ref') + '</td><td style="padding:2px 0;font-family:var(--mono);font-size:11px;">' + esc(s.VendorReferenceId) + '</td></tr>';
  if (s.DependencyServiceName) html += '<tr><td style="padding:2px 12px 2px 0;">' + t('depends_on') + '</td><td style="padding:2px 0;">' + esc(s.DependencyServiceName.split('_').pop() || s.DependencyServiceName) + '</td></tr>';
  html += '</table>';

  // Fields (seat counts, config) — ALSO uses Name/DisplayName/Value (PascalCase)
  if (fields.length) {
    html += '<div style="font-size:11px;font-weight:600;margin-bottom:6px;color:var(--text);">' + t('seats_configuration') + '</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:10px;">';
    fields.forEach(function(f) {
      var label = f.DisplayName || f.displayName || f.Name || f.name || f.FieldName || '?';
      var val = f.Value != null ? f.Value : f.value != null ? f.value : '-';
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += '<td style="padding:4px 8px;color:var(--text-muted);width:220px;white-space:nowrap;vertical-align:top;">' + esc(label) + '</td>';
      html += '<td style="padding:4px 8px;font-weight:600;color:var(--text);word-break:break-word;">' + esc(String(val)) + '</td>';
      html += '</tr>';
    });
    html += '</table>';
  }

  // PriceableItems (pricing) — ALSO uses PriceableItemDescription, PurchasePrice, SalesPrice, etc.
  if (items.length) {
    html += '<div style="font-size:11px;font-weight:600;margin-bottom:4px;color:var(--text);">' + t('pricing') + '</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;">';
    html += '<tr style="border-bottom:1px solid var(--border);">'
      + '<th style="text-align:left;padding:3px 6px;color:var(--text-muted);">' + t('item') + '</th>'
      + '<th style="text-align:left;padding:3px 6px;color:var(--text-muted);">' + t('type') + '</th>'
      + '<th style="text-align:right;padding:3px 6px;color:var(--text-muted);">' + t('purchase') + '</th>'
      + '<th style="text-align:right;padding:3px 6px;color:var(--text-muted);">' + t('sales') + '</th>'
      + '<th style="text-align:right;padding:3px 6px;color:var(--text-muted);">RRP</th>'
      + '<th style="text-align:left;padding:3px 6px;color:var(--text-muted);">' + t('currency') + '</th>'
      + '<th style="text-align:left;padding:3px 6px;color:var(--text-muted);">' + t('product') + '</th>'
      + '</tr>';
    items.forEach(function(p) {
      var pDesc = p.PriceableItemDescription || p.priceableItemDescription || p.Description || p.DisplayName || '-';
      var pType = p.ChargeType || p.chargeType || '-';
      var pBuy = p.PurchasePrice != null ? p.PurchasePrice : p.purchasePrice;
      var pSell = p.SalesPrice != null ? p.SalesPrice : p.salesPrice;
      var pRrp = p.SuggestedRetailPrice != null ? p.SuggestedRetailPrice : p.suggestedRetailPrice;
      var pCurr = p.Currency || p.currency || '';
      var pProd = p.ProductNumber || p.productNumber || p.MaterialNumber || p.materialNumber || '';
      var pPrepaid = p.PrepaidPeriodInMonths || p.prepaidPeriodInMonths;
      var typeLabel = pType;
      if (pPrepaid) typeLabel += ' (' + pPrepaid + 'mo)';
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += '<td style="padding:3px 6px;">' + esc(pDesc) + '</td>';
      html += '<td style="padding:3px 6px;font-size:10px;color:var(--text-dim);">' + esc(typeLabel) + '</td>';
      html += '<td style="padding:3px 6px;text-align:right;font-family:var(--mono);">' + (pBuy != null ? Number(pBuy).toFixed(2) : '-') + '</td>';
      html += '<td style="padding:3px 6px;text-align:right;font-family:var(--mono);font-weight:600;">' + (pSell != null ? Number(pSell).toFixed(2) : '-') + '</td>';
      html += '<td style="padding:3px 6px;text-align:right;font-family:var(--mono);color:var(--text-dim);">' + (pRrp != null ? Number(pRrp).toFixed(2) : '-') + '</td>';
      html += '<td style="padding:3px 6px;font-size:10px;">' + esc(pCurr) + '</td>';
      html += '<td style="padding:3px 6px;font-family:var(--mono);font-size:10px;color:var(--text-dim);">' + esc(pProd) + '</td>';
      html += '</tr>';
    });
    html += '</table>';
  }

  if (!fields.length && !items.length) {
    // Log the raw keys so we can debug
    html += '<div style="font-size:12px;color:var(--text-dim);">No Fields/PriceableItems found. Keys: ' + esc(Object.keys(s).join(', ')) + '</div>';
  }

  html += '</div>';
  cell.innerHTML = html;
}
