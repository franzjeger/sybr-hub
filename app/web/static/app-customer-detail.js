import {_syncBottomNav} from './app-ui.js';
import {_activityLabel, _reason, baselineReason} from './app-format.js';
// ═══════════════════════════════════════════════════════════════════
// CUSTOMER DETAIL VIEW
// ═══════════════════════════════════════════════════════════════════

import {esc} from './app-esc.js';
import {_lang, t} from './app-i18n.js';
import {registerUiHandlers} from './app-handlers.js';
import {
  _custPage, _overviewData, canOpenView, canWrite, currentCustomerId, hasFeature, hasModule,
  setCurrentCustomer, setCustPage, setOverviewData,
} from './app-state.js';
import {
  _formatBytes, badgeClass, formatRunName, metricCount, metricKnown, metricPct, timeAgo, toneClass,
} from './app-format.js';
import {setButtonLabel, showToast} from './app-ui.js';
import {apiFetch} from './app-api.js';
import {navApplyFeatureVisibility as applyFeatureVisibility, navApplyWriteCapability as applyWriteCapability, navShowView as showView, navSyncRoute as syncRoute} from './app-navigation.js';
import {currentView} from './app-state.js';
import {_uwArBody} from './app-also.js';
import {policyDeployLoad} from './app-policy-deploy.js';
import {baselineDeployLoad} from './app-baseline-deploy.js';
import {policyOverviewLoad} from './app-policy-overview.js';
import {assessmentsLoad} from './app-assessments.js';
import {_setupCustomerId, startSetup} from './app-setup.js';
import {
  _auditRunIsThisPages, _reconcileAuditState, _renderAuditIdle, _scopeLoaded,
  _showAuditRunningChrome, auditCustomerId, auditRunning, exportCSV, generateReport, loadHistory,
  loadScopeSections, pollAuditProgress, resetAuditScope, startAudit, updateScopeSummary,
} from './app-audit.js';
import {custNetworkLoad, loadFiles} from './app-network.js';
import {renderExpiryBanner, tagPillsHtml, uploadReportsToITGlue} from './app-customers.js';
import {_auditDateLabel, mountCustomerFindings, openLinkPicker} from './app-findings.js';


// sshTerminal and vpnConnect (data-id) are registered by app-infra.js.
function riskCoverageHtml(coverage) {
  var state = (coverage && coverage.state) || 'unknown';
  var issues = (coverage && coverage.issues) || [];
  return '<section class="card mb-4" id="cust-risk-coverage"><h3>' + esc(t('risk_coverage_title')) + '</h3><p>'
    + esc(t('risk_coverage_' + state)) + '</p>'
    + (issues.length ? '<ul>' + issues.map(function(issue) { return '<li>' + esc(issue[_lang] || issue.en || issue.no) + '</li>'; }).join('') + '</ul>' : '') + '</section>';
}

registerUiHandlers({
  // FortiGate threat log: show or hide the rows past the first five.
  cdToggleFgThreatRows: function(el) {
    var rows = document.querySelectorAll('.fg-threat-extra');
    var show = rows[0] && rows[0].hidden;
    rows.forEach(function(r) { r.hidden = !show; });
    el.textContent = show ? el.dataset.lessLabel : el.dataset.allLabel;
  },
  cdToggleUnifiClients: function() {
    var tb = document.getElementById('unifi-clients-table');
    var btn = document.getElementById('unifi-clients-toggle');
    if (tb.hidden) { tb.hidden = false; btn.textContent = t('lbl_hide_clients', 'Hide clients'); } else { tb.hidden = true; btn.textContent = t('lbl_show_clients', 'Show clients'); }
  },
  alsoToggleSubDetail: function(el) { alsoToggleSubDetail(el, el.dataset.subId); },
  uwToggleDns: function(el) { uwToggleDns(el, el.dataset.domain); },
  // The customer page: its tabs, the Rapport button and Policyer's Rull ut.
  custTab: function(el) { showCustomerTab(el.dataset.tab); },
  custReportDefault: function(el) { custReport(el.dataset.kind || 'customer-pdf', el); },
  custReport: function(el) { custReport(el.dataset.kind, el); },
  custToggleReportMenu: function(el) { _custToggleMenu('cust-report-menu', el); },
  custToggleDeployMenu: function(el) { _custToggleMenu('cust-deploy-menu', el); },
  custPolicySub: function(el) { showCustomerTab('policyer', el.dataset.sub); },
  // After setup: the customer it created or renewed.
  openSetupCustomer: function() { openSetupCustomer(); },
  // Tilgang's Tailscale nodes: hand a node to this customer, or take it back.
  custTsAssign: function(el) { _custTsAssign(el.dataset.customerId, el); },
  custTsUnassign: function(el) { _custTsUnassign(el.dataset.customerId, el.dataset.deviceId); },
  custTsCopy: function(el) { _custTsCopy(el.dataset.value); },
});

// ── The customer page ─────────────────────────────────────────────────────────
// The customer is the context. One page, its tabs switching in place and the
// address carrying the tab: #/customer/<id> is Funn, #/customer/<id>/<tab> the
// others, and Policyer's deploy flows add /ca or /intune. Every call the page
// and its tabs make names this page's customer (_custPage.id); the server has
// no "active customer" to fall back on, so a second tab on another customer
// cannot reach into this one. Every late answer is checked against the id it
// was asked for before it is shown.
var CUSTOMER_TABS = ['funn', 'audit', 'policyer', 'vurderinger', 'nettverk', 'tilgang', 'detaljer'];
var _detailChartInstance = null;

// The pages that were about "the active customer" are its tabs now. An old
// address or a call by the old name lands on the tab it became.
export var CUSTOMER_TAB_ALIASES = {
  home: ['funn'], files: ['detaljer'], audit: ['audit'], history: ['audit'], 'history-report': ['audit'],
  'policy-overview': ['policyer'], 'policy-deploy': ['policyer', 'ca'], 'baseline-deploy': ['policyer', 'intune'],
  assessments: ['vurderinger'],
};

export function _custHash() {
  var h = '#/customer/' + encodeURIComponent(_custPage.id || '');
  if (_custPage.tab && _custPage.tab !== 'funn') h += '/' + _custPage.tab;
  if (_custPage.tab === 'policyer' && _custPage.sub) h += '/' + _custPage.sub;
  return h;
}

// Only the last customer asked for opens. An earlier click still in flight
// would otherwise render its page over the one asked for.
var _custPageSeq = 0;

export async function openCustomerPage(customerId, tab, sub) {
  tab = CUSTOMER_TABS.indexOf(tab) !== -1 ? tab : 'funn';
  if (customerId === _custPage.id && currentView === 'customer-detail' && _custPage.cust) {
    showCustomerTab(tab, sub);
    return;
  }
  var seq = ++_custPageSeq;
  // This tab's current customer, and Nylige in the palette (app.js).
  setCurrentCustomer(customerId);
  resetAuditScope();
  _custReportRun = null;
  setCustPage({id: customerId, cust: null, tab: tab, sub: sub || '', loaded: {}});
  showView('customer-detail');
  _custShowPanels(tab, sub || '');
  syncRoute('customer-detail', customerId);
  await loadCustomerDetail(customerId);
  if (seq !== _custPageSeq || !_custPage.cust) return;
  showCustomerTab(_custPage.tab, _custPage.sub);
}

// This tab's current customer's page on a tab: what showView('audit') and the
// other old names mean now. With no customer yet the list is where to choose one.
export async function openCurrentCustomerTab(tab, sub) {
  var id = (currentView === 'customer-detail' && _custPage.id) || currentCustomerId();
  if (!id) { showView('customers'); return; }
  await openCustomerPage(id, tab, sub);
}

// Setup registers the customer it set up and says which (_setupCustomerId,
// app-setup.js); that is the page "Åpne kunden" opens.
function openSetupCustomer() {
  if (_setupCustomerId) openCustomerPage(_setupCustomerId, 'funn');
  else showView('customers');
}

function _custShowPanels(tab, sub) {
  document.querySelectorAll('#cust-tabs .tab').forEach(function(b) {
    var on = b.dataset.tab === tab;
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', on ? 'true' : 'false');
    b.tabIndex = on ? 0 : -1;
  });
  CUSTOMER_TABS.forEach(function(name) {
    var panel = document.getElementById('cust-panel-' + name);
    if (panel) panel.hidden = name !== tab;
  });
  if (tab === 'policyer') {
    var po = document.getElementById('view-policy-overview');
    var pd = document.getElementById('view-policy-deploy');
    var bd = document.getElementById('view-baseline-deploy');
    if (po) po.hidden = !!sub;
    if (pd) pd.hidden = sub !== 'ca';
    if (bd) bd.hidden = sub !== 'intune';
  }
}

// Shows one tab of the page on screen, in place, and loads it the first time.
function showCustomerTab(tab, sub) {
  if (!_custPage.id) return;
  tab = CUSTOMER_TABS.indexOf(tab) !== -1 ? tab : 'funn';
  // A tab this account cannot open (gated away) is not shown by address either.
  var btn = document.getElementById('cust-tab-' + tab);
  if (btn && btn.classList.contains('gated-hidden')) { tab = 'funn'; sub = ''; }
  sub = tab === 'policyer' && (sub === 'ca' || sub === 'intune') && canOpenView(sub === 'ca' ? 'policy-deploy' : 'baseline-deploy') ? sub : '';
  _custPage.tab = tab;
  _custPage.sub = sub;
  _custShowPanels(tab, sub);
  _custCloseMenus();
  syncRoute('customer-detail', _custPage.id);
  _syncBottomNav('customer-detail');
  var key = tab === 'policyer' ? tab + ':' + sub : tab;
  if (tab === 'audit') {
    // The run is whatever the server says, every time the tab opens.
    _custLoadAudit();
  } else if (!_custPage.loaded[key]) {
    _custPage.loaded[key] = true;
    if (tab === 'policyer' && !sub) policyOverviewLoad();
    else if (tab === 'policyer' && sub === 'ca') policyDeployLoad();
    else if (tab === 'policyer' && sub === 'intune') baselineDeployLoad();
    else if (tab === 'vurderinger') assessmentsLoad();
    else if (tab === 'nettverk') _custLoadNetwork(_custPage.id);
    else if (tab === 'tilgang') _custLoadAccess(_custPage.id);
    else if (tab === 'detaljer') _custLoadDetails(_custPage.id);
  }
  // Out of a run on Audit the floating progress bar is the run's only sign.
  if (auditRunning) pollAuditProgress();
}

// Whether the run's own progress is on screen: the Audit tab of the customer
// the run is for.
export function custAuditTabOpen() {
  return currentView === 'customer-detail' && _custPage.tab === 'audit'
    && (!auditCustomerId || auditCustomerId === _custPage.id);
}

// After a run finishes, what it changed: the findings, the figures, the runs.
export function custPageAuditFinished() {
  if (currentView !== 'customer-detail' || !_custPage.id) return;
  var id = _custPage.id;
  _custPage.loaded = {};
  loadCustomerDetail(id).then(function() {
    if (_custPage.id === id && _custPage.tab === 'audit') loadHistory(id);
  });
}

function _custCloseMenus() {
  ['cust-report-menu', 'cust-deploy-menu'].forEach(function(id) {
    var m = document.getElementById(id);
    if (m && !m.hidden) {
      m.hidden = true;
      var btn = m.parentNode.querySelector('[aria-expanded]');
      if (btn) btn.setAttribute('aria-expanded', 'false');
    }
  });
}

function _custToggleMenu(menuId, btn) {
  var m = document.getElementById(menuId);
  if (!m) return;
  var open = m.hidden;
  _custCloseMenus();
  m.hidden = !open;
  if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
}

document.addEventListener('click', function(e) {
  if (e.target.closest('.split-btn')) return;
  _custCloseMenus();
});
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') _custCloseMenus(); });

// Arrow keys move between the tabs, as a tab list should.
document.addEventListener('keydown', function(e) {
  if (!e.target.closest || !e.target.closest('#cust-tabs')) return;
  if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
  var tabs = Array.prototype.filter.call(document.querySelectorAll('#cust-tabs .tab'), function(b) {
    return !b.classList.contains('gated-hidden') && getComputedStyle(b).display !== 'none';
  });
  var i = tabs.indexOf(document.activeElement);
  if (i === -1) return;
  e.preventDefault();
  var next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
  next.focus();
  showCustomerTab(next.dataset.tab);
});

// ── The head and Funn ─────────────────────────────────────────────────────────
async function loadCustomerDetail(customerId) {
  var head = document.getElementById('cust-page-head');
  var box = document.getElementById('customer-detail-content');
  box.innerHTML = '<div class="loading-note"><div class="loader"></div> ' + esc(t('msg_loading','Loading...')) + '</div>';

  // The list the page reads its customer from; always fresh, since an audit
  // or a decision on another page may have changed its figures.
  try {
    var ovData = await apiFetch('/api/dashboard/overview');
    if (ovData) setOverviewData({customers: ovData.customers || []});
  } catch(e) { console.warn('Overview data load failed:', e); }
  if (_custPage.id !== customerId) return;
  var cust = null;
  if (_overviewData && _overviewData.customers) {
    cust = _overviewData.customers.find(function(c){ return c.customer_id === customerId || c._id === customerId; });
  }
  if (!cust) {
    head.innerHTML = '';
    box.innerHTML = '<div class="alert alert-error">' + t('err_customer_not_found','Kunde ikke funnet') + '</div>';
    return;
  }
  _custPage.cust = cust;

  var m = cust.metrics || {};
  var hasM = cust.has_metrics;

  var bcItems = document.getElementById('breadcrumb-items');
  var bcNav = document.getElementById('breadcrumb');
  if (bcNav && bcItems) {
    bcNav.style.display = 'block';
    bcItems.innerHTML = '<a href="#" class="hover-link crumb-link" data-click-handler="showView" data-view="customers">' + t('nav_customers') + '</a>' +
      ' <span class="crumb-sep">/</span> ' +
      '<span class="crumb-current">' + esc(cust.customer_name) + '</span>';
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

  // One primary action for the page, on every tab: Kjør audit. Reports are
  // the Audit tab's.
  head.innerHTML = `
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
        <button class="btn btn-primary" id="cust-run-audit" data-write data-feature="audit" ${canAudit ? '' : 'disabled title="' + esc(t('tip_audit_needs_m365', 'M365-tilgang må settes opp før en audit kan kjøre')) + '"'}>${esc(t('btn_run_audit'))}</button>
      </div>
    </div>
    ${canAudit ? '' : '<div class="findings-notice is-warning cust-access-notice"><span>' + esc(t('msg_m365_missing', 'M365-tilgang er ikke satt opp for denne kunden, så den kan ikke auditeres ennå.')) + '</span>' + (canSetup ? '<button class="btn btn-default btn-sm" id="cust-setup-m365">' + esc(t('btn_setup_m365', 'Sett opp M365-tilgang')) + '</button>' : '') + '</div>'}`;

  // Funn: what is wrong here and what to do about it, first; the PSA and
  // documentation links next, because the actions on each finding depend on
  // them; then the figures and the trend.
  box.innerHTML = `
    <div id="cust-links" class="cust-links"></div>
    <div id="cust-findings"></div>

    <div class="grid grid-cols-4 gap-4 my-6">
      <div class="card text-center p-5">
        <div class="grade-hero grade-${esc(grade)}">${esc(grade)}</div>
        <div class="label-caps">${t('lbl_grade')}</div>
      </div>
      <div class="card text-center p-5">
        <div class="gauge"><canvas id="gauge-risk"></canvas></div>
        <div class="label-caps">${t('lbl_risk')}</div>
      </div>
      <div class="card text-center p-5">
        <div class="gauge"><canvas id="gauge-mfa"></canvas></div>
        <div class="label-caps">MFA</div>
      </div>
      <div class="card text-center p-5">
        <div class="gauge"><canvas id="gauge-ss"></canvas></div>
        <div class="label-caps">${t('secure_score_2')}</div>
      </div>
    </div>

    ${riskCoverageHtml(m && m.risk_coverage)}
    <div id="customer-baseline-panel"></div>

    <div class="card cust-trend" id="cust-trend">
      <div class="card-title">${t('lbl_trend')}</div>
      <div class="cust-trend-body" id="cust-trend-body"></div>
    </div>

    <div class="card cust-figures">
      <div class="card-title">${esc(t('lbl_key_figures', 'Nøkkeltall'))}</div>
      <dl class="cust-details" id="cust-details">
        ${_detailRow(t('lbl_users'), hasM, m.total_users)}
        ${_detailRow(t('lbl_users_without_mfa', 'Brukere uten MFA'), hasM, m.users_no_mfa, 'is-bad')}
        ${_detailRow(t('lbl_ca_policies'), hasM, m.ca_policies_enabled)}
        <dt>${t('intune')}</dt><dd${hasM && metricPct(m.intune_compliance_pct) === null ? ' class="is-unknown"' : ''}>${!hasM ? '-' : metricPct(m.intune_compliance_pct) !== null ? metricPct(m.intune_compliance_pct) + '%' : esc(t('lbl_unknown_value', 'ukjent'))}</dd>
        <dt>${t('lbl_last_audit')}</dt><dd>${cust.last_audit ? esc(formatRunName(cust.last_audit)) : '-'}${_auditAgeSuffix(cust.last_audit)}</dd>
        ${_detailRow(t('lbl_warnings_title', 'Advarsler'), hasM, m.total_warns, 'is-warn')}
      </dl>
    </div>
  `;
  applyFeatureVisibility();

  setTimeout(function() { _renderGauges(score, hasM ? m.mfa_coverage_pct : null, hasM ? m.secure_score_pct : null); }, 50);
  _loadCustomerTrendChart(customerId);
  _loadCustomerBaselineCard(customerId);

  _wireCustomerHead(customerId, cust);
  _loadCustomerLinks(customerId, cust.customer_name);
  mountCustomerFindings(document.getElementById('cust-findings'), customerId, {
    onLinked: function() { _loadCustomerLinks(customerId, cust.customer_name); },
  });
}

// One row of the Nøkkeltall card: a count from the latest run's metrics, the
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
  return ' <span class="text-dim fw-normal">(' + Number(days) + 'd)</span>';
}

function _wireCustomerHead(customerId, cust) {
  var run = document.getElementById('cust-run-audit');
  if (run) run.addEventListener('click', async function() {
    if (run.disabled) return;
    run.disabled = true;
    // startAudit opens the Audit tab, where the run shows.
    await startAudit(customerId);
    run.disabled = !cust.has_m365;
  });
  // Setup writes to its own staging slot and registers the customer it set
  // up; it does not read which customer is open.
  var setup = document.getElementById('cust-setup-m365');
  if (setup) setup.addEventListener('click', function() { startSetup(); });
}

// ── Audit ─────────────────────────────────────────────────────────────────────
// The run (live or idle), the section chooser, the Rapport button and the
// runs before it, for this customer.
var _custRuns = [];
var _custReportRun = null;

export function setCustRuns(runs) { _custRuns = runs; }
export function setCustReportRun(run) { _custReportRun = run; }

function _custLoadAudit() {
  if (_auditRunIsThisPages()) _showAuditRunningChrome();
  else if (hasFeature('audit')) _reconcileAuditState();
  else _renderAuditIdle();
  // The chooser's summary ("all 26 sections") before anyone opens it.
  if (hasFeature('audit')) { if (_scopeLoaded) updateScopeSummary(); else loadScopeSections(); }
  loadHistory(_custPage.id);
}

// Rapport: Kunderapport (PDF) unless the customer has no run with evidence
// files to build it from, in which case the summary report, which reads the
// figures, is the honest default.
function _custHasEvidenceRun() {
  return _custRuns.some(function(r) { return Number(r.file_count) > 0; });
}

export function custSyncReportButton() {
  var main = document.getElementById('cust-report-main');
  if (!main) return;
  var full = _custHasEvidenceRun() || !!_custReportRun;
  main.dataset.kind = full ? 'customer-pdf' : 'summary';
  setButtonLabel(main, full ? t('lbl_customer_report_pdf', 'Kunderapport (PDF)') : t('btn_summary_report', 'Sammendragsrapport'));
  document.querySelectorAll('#cust-report-menu [data-kind]').forEach(function(b) {
    var needsRun = ['tech-pdf', 'customer-html', 'tech-html', 'csv'].indexOf(b.dataset.kind) !== -1;
    b.disabled = needsRun && !full;
    if (b.dataset.kind === 'summary') b.hidden = !full;
  });
}

// The full reports are built from a run the server has selected for this
// user and this customer: the one just audited, or one picked in the runs
// list. With neither, the latest run that kept its evidence files.
async function _custEnsureReportRun() {
  if (_custReportRun && _custReportRun.customerId === _custPage.id) return true;
  var customerId = _custPage.id;
  var run = _custRuns.find(function(r) { return Number(r.file_count) > 0; });
  var area = document.getElementById('report-result');
  if (!run) {
    if (area) area.innerHTML = '<div class="alert alert-warning">' + esc(t('msg_no_evidence_run', 'Ingen kjøring har bevisfiler, så hele rapporten kan ikke bygges. Sammendragsrapporten leser nøkkeltallene.')) + '</div>';
    return false;
  }
  var d = await apiFetch('/api/history/load', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({customer_id: customerId, path: run.path}),
  });
  if (!d || d.error || _custPage.id !== customerId) return false;
  _custReportRun = {customerId: customerId, timestamp: run.timestamp};
  return true;
}

async function custReport(kind, btn) {
  _custCloseMenus();
  if (kind === 'summary') {
    window.open('/api/reports/customer-summary/' + encodeURIComponent(_custPage.id), '_blank');
    return;
  }
  if (kind === 'itglue') { uploadReportsToITGlue(_custPage.id); return; }
  if (!(await _custEnsureReportRun())) return;
  if (kind === 'csv') { exportCSV(_custPage.id); return; }
  var spec = {
    'customer-pdf': ['pdf', 'customer'], 'customer-html': ['html', 'customer'],
    'tech-pdf': ['pdf', 'tech'], 'tech-html': ['html', 'tech'],
  }[kind];
  if (spec) generateReport(spec[0], spec[1], _custPage.id);
}

// A run picked in the runs list is what Rapport builds from.
export function custReportFromRun(timestamp) {
  _custReportRun = {customerId: _custPage.id, timestamp: timestamp};
  custSyncReportButton();
  var area = document.getElementById('report-result');
  if (area) area.innerHTML = '<div class="alert alert-info">' + esc(t('msg_report_from_run', 'Rapport bygges fra kjøringen {date}.').replace('{date}', formatRunName(timestamp))) + '</div>';
  var bar = document.getElementById('cust-report');
  if (bar) bar.scrollIntoView({block: 'nearest'});
  _custToggleMenu('cust-report-menu', bar ? bar.querySelector('.split-caret') : null);
}

// ── Nettverk, Tilgang, Detaljer ───────────────────────────────────────────────
function _custLoadNetwork(customerId) {
  // Its FortiGate and UniFi, set up here, the quick check and the backups.
  custNetworkLoad(customerId);
  var body = document.getElementById('cust-network-body');
  body.innerHTML = '<div class="card" id="customer-network-panel"><div class="loading-note">' + esc(t('msg_loading_network', 'Laster nettverk...')) + '</div></div>';
  _loadCustomerNetworkInventory(customerId).then(function() {
    var panel = document.getElementById('customer-network-panel');
    if (!panel || panel.style.display !== 'none' || _custPage.id !== customerId) return;
    // Nothing read from its devices yet. The list above says what is set up.
    body.innerHTML = '';
  });
}

function _custLoadAccess(customerId) {
  var body = document.getElementById('cust-access-body');
  body.innerHTML = '<div id="customer-infra-panel"></div>'
    + (hasModule('tailscale') && canOpenView('tailscale') ? '<div id="customer-tailscale-panel" class="card cust-ts"></div>' : '');
  _loadCustomerInfraCard(customerId);
  if (document.getElementById('customer-tailscale-panel')) _loadCustomerTailscale(customerId);
}

async function _custLoadDetails(customerId) {
  var cust = _custPage.cust || {};
  var body = document.getElementById('cust-details-body');
  var extra = document.getElementById('cust-details-extra');
  body.innerHTML = '<div class="loading-note"><div class="loader"></div></div>';
  extra.innerHTML = '';
  var st = await apiFetch('/api/customer/' + encodeURIComponent(customerId) + '/status');
  if (_custPage.id !== customerId) return;
  var c = (st && st.customer) || {};
  var tags = c.tags || cust.tags || [];
  var safeId = String(customerId).replace(/[^a-zA-Z0-9_-]/g, '_');
  var hasCredentials = !!(st && st.has_credentials);

  // Microsoft 365 access: the tenant connection, and the two things done
  // with the app's credentials.
  var html = '<div class="card cust-access-card">'
    + '<div class="card-title">' + esc(t('hdr_m365_access', 'Microsoft 365-tilgang')) + '</div>'
    + '<p class="cust-card-text">' + esc(cust.has_m365 ? t('msg_m365_connected', 'Tenanten er koblet til, og kunden kan auditeres.') : t('msg_m365_missing', 'M365-tilgang er ikke satt opp for denne kunden, så den kan ikke auditeres ennå.')) + '</p>'
    + (hasCredentials ? '<div class="btn-row">'
      + '<button class="btn btn-default btn-sm" data-click-handler="checkPermissions" data-customer-id="' + esc(customerId) + '">' + esc(t('btn_check_permissions')) + '</button>'
      + '<button class="btn btn-default btn-sm" data-write data-click-handler="renewCreds" data-customer-id="' + esc(customerId) + '">' + esc(t('btn_renew_credentials')) + '</button>'
      + '</div>' : '')
    + '</div>';

  // Tags, editable here.
  html += '<div class="card">'
    + '<div class="card-title">' + esc(t('lbl_tags')) + '</div>'
    + '<div class="cust-tags-row"><span id="tag-pills-' + esc(safeId) + '">' + tagPillsHtml(tags) + '</span>'
    + '<button class="btn btn-ghost btn-sm" data-write data-click-handler="openTagEditor" aria-expanded="false" data-customer-id="' + esc(customerId) + '" data-tags="' + esc(JSON.stringify(tags)) + '">' + esc(t('btn_edit_tags', 'Endre tags')) + '</button></div>'
    + '<div id="tag-editor-' + esc(safeId) + '" class="cust-tag-editor" hidden></div>'
    + '</div>';

  // Notes.
  html += '<div class="card" id="customer-notes-panel">'
    + '<div class="cust-card-head"><div class="card-title">' + esc(t('hdr_notes', 'Notater')) + '</div>'
    + '<span id="detail-notes-status" class="cust-card-status"></span>'
    + '<button class="btn btn-ghost btn-sm" data-write id="detail-notes-save">' + esc(t('btn_save', 'Lagre')) + '</button></div>'
    + '<textarea id="detail-notes-textarea" class="field-input cust-notes" placeholder="' + esc(t('placeholder_notes', 'Skriv notater om denne kunden...')) + '"></textarea>'
    + '</div>';
  body.innerHTML = html;
  document.getElementById('detail-notes-save').addEventListener('click', function() { saveDetailNotes(customerId); });
  _loadCustomerNotes(customerId);

  // Files: names and dates.
  loadFiles(customerId);

  // Credential expiry for this customer, not every customer.
  apiFetch('/api/expiry/check').then(function(d) {
    if (!d || _custPage.id !== customerId) return;
    renderExpiryBanner({items: (d.items || []).filter(function(i) { return i.customer_id === customerId; })});
  });

  // Hosting and licences (billing module), then what has happened here.
  var extraHtml = '';
  if (hasModule('billing')) {
    extraHtml += '<div id="customer-uniweb-panel"></div>';
    if (cust.also_account_id) {
      extraHtml += '<div class="card"><div class="cust-card-head"><div class="card-title">' + esc(t('nav_licenses', 'Lisenser')) + '</div>'
        + '<button class="btn btn-ghost btn-sm" id="cust-load-licenses">' + esc(t('btn_show_licenses', 'Vis lisenser')) + '</button></div>'
        + '<div id="cust-licenses-panel"></div></div>';
    }
  }
  extraHtml += '<div class="card" id="customer-activity-panel"><div class="loading-note">' + esc(t('msg_loading','Laster...')) + '</div></div>';
  extra.innerHTML = extraHtml;
  if (hasModule('billing')) _unifiedLoadUniwebCard(customerId);
  var lic = document.getElementById('cust-load-licenses');
  if (lic) lic.addEventListener('click', function() { loadCustomerLicenses(cust.also_account_id); });
  _loadCustomerActivity(cust.customer_name || c.name || '');
  applyWriteCapability();
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


// The sentence beside a requirement. The server sends a reason code and the
// values behind it, including the internal path the check reads
// ("mfa.has_data"). A person reads which part of the collection was missing,
// never the field name.






function _baselineStatusPill(status) {
  if (status === 'pass') return '<span class="text-success">&#10003;</span>';
  if (status === 'fail') return '<span class="text-danger">&#10007;</span>';
  return '<span class="text-dim">&#8211;</span>';
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
    el.innerHTML = '<div class="card p-5 mb-4 text-dim text-sm">'
      + esc(_reason('drift_', b.reason_code, {}) || t('msg_baseline_no_run','No audit run to measure against yet.')) + '</div>';
    return;
  }

  var pct = b.conformance_pct;
  var pctColor = pct === null || pct === undefined ? 'var(--text-dim)'
    : (pct >= 90 ? 'var(--green)' : (pct >= 70 ? 'var(--orange)' : 'var(--red)'));
  var nothing = b.assessed === 0;

  var html = '<div class="card cust-standard" id="cust-standard">';
  html += '<div class="cust-standard-head">';
  html += '<div class="card-title">' + esc(b.baseline.name) + ' ' + esc(b.baseline.version) + '</div>';
  // No percentage when nothing was assessed: a dash beside "etterlevelse"
  // still reads as a score.
  if (!nothing && pct !== null && pct !== undefined) {
    html += '<div class="cust-standard-pct"><span class="' + toneClass(pctColor) + '">' + Number(pct) + ' %</span>'
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
  html += '<div class="mt-4 pt-4 border-t">';
  html += '<div class="label-caps mb-2">'
        + t('hdr_policy_drift','Changes since previous audit') + '</div>';
  if (!drift || !drift.measured) {
    html += '<div class="text-xs text-dim">'
          + esc((drift && _reason('drift_', drift.reason_code, drift.reason_params)) || t('msg_drift_not_measured','Not compared.')) + '</div>';
  } else if (!drift.added_total && !drift.removed_total && !drift.changed_total) {
    html += '<div class="text-xs text-muted">'
          + esc(t('msg_drift_quiet','No policy changed since {run}.').replace('{run}', formatRunName(drift.compared_with))) + '</div>';
  } else {
    html += '<div class="text-xs text-muted mb-2">'
          + t('msg_drift_summary','Compared with {run}: {added} added, {removed} removed, {changed} changed.')
              .replace('{run}', esc(formatRunName(drift.compared_with))).replace('{added}', Number(drift.added_total))
              .replace('{removed}', Number(drift.removed_total)).replace('{changed}', Number(drift.changed_total))
          + '</div>';
    html += '<table class="data-table data-table--compact">';
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
        html += '<tr>'
              + '<td class="' + toneClass(kind[1]) + ' nowrap">' + kind[0] + '</td>'
              + '<td>' + esc(r[1].name || t('lbl_unnamed','(unnamed)')) + '</td>'
              + '<td class="text-right text-dim">' + esc(r[2]) + '</td>'
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
      el.innerHTML = '<div class="card p-5 mt-4">'
        + '<div class="card-title mb-3">' + t('hdr_infrastructure','Infrastructure') + '</div>'
        + '<div class="cust-infra-empty"><span>' + esc(t('msg_no_infra_linked', 'Ingen infrastruktur knyttet til denne kunden. En SSH-vert eller VPN-profil knyttes til kunden der den legges inn.')) + '</span>'
        + (canOpenView('hosts') ? '<button class="btn btn-default btn-sm" data-click-handler="showView" data-view="hosts">' + esc(t('btn_open_hosts', 'Åpne Verter')) + '</button>' : '')
        + (canOpenView('vpn') ? '<button class="btn btn-default btn-sm" data-click-handler="showView" data-view="vpn">' + esc(t('btn_open_vpn', 'Åpne VPN')) + '</button>' : '')
        + '</div>'
        + '</div>';
      return;
    }

    var html = '<div class="card p-5 mt-4">';
    html += '<div class="card-title mb-4">' + t('hdr_infrastructure','Infrastructure') + '</div>';

    // SSH Hosts
    if (sshHosts.length) {
      html += '<div class="label-caps mb-2">' + t('hdr_ssh_hosts','SSH Hosts') + ' (' + sshHosts.length + ')</div>';
      html += '<table class="data-table data-table--compact mb-4">';
      html += '<thead><tr>';
      html += '<th>' + t('lbl_host_name','Name') + '</th>';
      html += '<th>' + t('lbl_host_address','Host') + '</th>';
      html += '<th>' + t('lbl_username','Username') + '</th>';
      html += '<th>' + t('lbl_device_type','Type') + '</th>';
      html += '<th>' + t('lbl_group','Group') + '</th>';
      html += '<th class="text-center">' + t('lbl_status','Status') + '</th>';
      html += '<th></th>';
      html += '</tr></thead><tbody>';
      sshHosts.forEach(function(h) {
        var statusColor = h.is_reachable === true ? 'var(--green)' : h.is_reachable === false ? 'var(--red)' : 'var(--text-dim)';
        html += '<tr>';
        html += '<td class="fw-medium">' + esc(h.label) + '</td>';
        html += '<td class="font-mono text-xs">' + esc(h.hostname) + ':' + Number(h.port) + '</td>';
        html += '<td>' + esc(h.username) + '</td>';
        html += '<td>' + esc(h.device_type) + '</td>';
        html += '<td class="text-muted">' + esc(h.group_name || '-') + '</td>';
        html += '<td class="text-center"><span class="dot ' + toneClass(statusColor) + '"></span></td>';
        html += '<td><button class="btn btn-ghost btn-sm text-accent" data-write data-click-handler="sshTerminal" data-id="' + esc(h.id) + '">SSH</button></td>';
        html += '</tr>';
      });
      html += '</tbody></table>';
    }

    // VPN Profiles
    if (vpnProfiles.length) {
      var protocolLabels = {wireguard:'WireGuard', openvpn:'OpenVPN', azure:'Azure P2S', fortigate_ipsec:'FortiGate IPsec'};
      html += '<div class="label-caps mb-2">' + t('hdr_vpn_profiles','VPN Profiles') + ' (' + vpnProfiles.length + ')</div>';
      html += '<div class="flex flex-wrap gap-3 mb-4">';
      vpnProfiles.forEach(function(p) {
        var protoLabel = protocolLabels[p.protocol] || p.protocol;
        html += '<div class="inset flex items-center gap-2 text-xs">';
        html += '<span class="fw-semibold">' + esc(p.name) + '</span>';
        html += '<span class="text-muted">' + esc(protoLabel) + '</span>';
        html += '<button class="btn btn-ghost btn-sm text-success" data-write data-click-handler="vpnConnect" data-id="' + esc(p.id) + '">' + t('vpn_connect','Connect') + '</button>';
        html += '</div>';
      });
      html += '</div>';
    }

    // FortiGate + UniFi side by side
    if (fg || uf) {
      html += '<div class="grid gap-4' + (fg && uf ? ' grid-cols-2' : '') + '">';
      if (fg) {
        html += '<div class="inset">';
        html += '<div class="label-caps mb-2">FortiGate</div>';
        html += '<div class="kv-grid kv-grid--narrow text-xs">';
        html += '<span class="text-muted">' + t('host') + '</span><span class="font-mono">' + esc(fg.host) + '</span>';
        html += '<span class="text-muted">' + t('port') + '</span><span>' + Number(fg.port) + '</span>';
        html += '<span class="text-muted">VDOM</span><span>' + esc(fg.vdom) + '</span>';
        html += '</div></div>';
      }
      if (uf) {
        html += '<div class="inset">';
        html += '<div class="label-caps mb-2">UniFi</div>';
        html += '<div class="kv-grid kv-grid--narrow text-xs">';
        html += '<span class="text-muted">' + t('host') + '</span><span class="font-mono">' + esc(uf.host) + '</span>';
        html += '<span class="text-muted">' + t('site') + '</span><span>' + esc(uf.site) + '</span>';
        html += '<span class="text-muted">' + t('mode') + '</span><span>' + esc(uf.mode) + '</span>';
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
    var html = '<div class="flex items-center justify-between mb-4">';
    html += '<div class="card-title mb-0">' + t('hdr_network_inventory','Network') + '</div>';
    html += '<div class="flex gap-4 text-xs text-muted">';
    if (tot.aps) html += '<span>' + Number(tot.aps) + ' ' + t('lbl_aps','APs') + '</span>';
    if (tot.switches) html += '<span>' + Number(tot.switches) + ' ' + t('lbl_switches','Switches') + '</span>';
    if (tot.gateways) html += '<span>' + Number(tot.gateways) + ' ' + t('lbl_gateways','Gateways') + '</span>';
    if (tot.firewalls) html += '<span>' + Number(tot.firewalls) + ' ' + t('lbl_firewalls','Firewalls') + '</span>';
    if (tot.total_clients) html += '<span>' + Number(tot.total_clients) + ' ' + t('lbl_total_clients','Clients') + '</span>';
    html += '</div></div>';

    // Alerts
    if (alerts.length > 0) {
      html += '<div class="mb-4">';
      for (var i = 0; i < alerts.length; i++) {
        var alertColor = alerts[i].indexOf('outdated') >= 0 ? 'var(--orange)' : alerts[i].indexOf('port usage') >= 0 ? 'var(--orange)' : 'var(--red)';
        html += '<div class="text-xs ' + toneClass(alertColor) + ' py-1 px-0">' + esc(alerts[i]) + '</div>';
      }
      html += '</div>';
    }

    // APs table
    if (devs.aps && devs.aps.length) {
      html += '<div class="label-caps mb-2 mt-3">' + t('lbl_aps','Access Points') + '</div>';
      html += '<table class="data-table data-table--compact">';
      html += '<thead><tr>';
      html += '<th>' + t('lbl_device','Device') + '</th>';
      html += '<th>' + t('lbl_model','Model') + '</th>';
      html += '<th>' + t('lbl_firmware','Firmware') + '</th>';
      html += '<th class="text-right">' + t('lbl_clients','Clients') + '</th>';
      html += '<th>' + t('lbl_status','Status') + '</th>';
      html += '<th>' + t('lbl_capacity','Capacity') + '</th>';
      html += '</tr></thead><tbody>';
      for (let i = 0; i < devs.aps.length; i++) {
        var ap = devs.aps[i];
        let statusColor = ap.status === 'online' ? 'var(--green)' : 'var(--red)';
        let fwColor = (ap.fw_status === 'warning' || ap.fw_status === 'critical') ? 'var(--orange)' : 'var(--text)';
        var clientPct = Math.min(100, Math.round((ap.clients / 60) * 100));
        let barColor = clientPct > 80 ? 'var(--red)' : clientPct > 60 ? 'var(--orange)' : 'var(--green)';
        html += '<tr>';
        html += '<td class="fw-medium">' + esc(ap.name) + '</td>';
        html += '<td class="text-muted">' + esc(ap.model) + '</td>';
        html += '<td class="' + toneClass(fwColor) + '">' + esc(ap.firmware) + (ap.fw_status === 'warning' || ap.fw_status === 'critical' ? '' : '') + '</td>';
        html += '<td class="text-right fw-semibold">' + (Number(ap.clients) || 0) + '</td>';
        html += '<td><span class="dot ' + toneClass(statusColor) + ' mr-1"></span>' + esc(ap.status) + '</td>';
        html += '<td class="cell-bar"><div class="bar"><div class="bar-fill ' + toneClass(barColor).replace('text-', 'is-') + '" data-bar="' + clientPct + '"></div></div></td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // Switches table
    if (devs.switches && devs.switches.length) {
      html += '<div class="label-caps mb-2 mt-4">' + t('lbl_switches','Switches') + '</div>';
      html += '<table class="data-table data-table--compact">';
      html += '<thead><tr>';
      html += '<th>' + t('lbl_device','Device') + '</th>';
      html += '<th>' + t('lbl_model','Model') + '</th>';
      html += '<th>' + t('lbl_firmware','Firmware') + '</th>';
      html += '<th class="text-right">' + t('lbl_ports','Ports') + '</th>';
      html += '<th>' + t('lbl_status','Status') + '</th>';
      html += '<th>' + t('lbl_port_usage','Port usage') + '</th>';
      html += '</tr></thead><tbody>';
      for (let i = 0; i < devs.switches.length; i++) {
        var sw = devs.switches[i];
        let statusColor = sw.status === 'online' ? 'var(--green)' : 'var(--red)';
        let fwColor = (sw.fw_status === 'warning' || sw.fw_status === 'critical') ? 'var(--orange)' : 'var(--text)';
        var portPct = sw.ports_total > 0 ? Math.round((sw.ports_used / sw.ports_total) * 100) : 0;
        let barColor = portPct > 85 ? 'var(--red)' : portPct > 70 ? 'var(--orange)' : 'var(--green)';
        html += '<tr>';
        html += '<td class="fw-medium">' + esc(sw.name) + '</td>';
        html += '<td class="text-muted">' + esc(sw.model) + '</td>';
        html += '<td class="' + toneClass(fwColor) + '">' + esc(sw.firmware) + (sw.fw_status === 'warning' || sw.fw_status === 'critical' ? '' : '') + '</td>';
        html += '<td class="text-right fw-semibold">' + Number(sw.ports_used) + '/' + Number(sw.ports_total) + '</td>';
        html += '<td><span class="dot ' + toneClass(statusColor) + ' mr-1"></span>' + esc(sw.status) + '</td>';
        html += '<td class="cell-bar"><div class="bar"><div class="bar-fill ' + toneClass(barColor).replace('text-', 'is-') + '" data-bar="' + portPct + '"></div></div></td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // Gateways table
    if (devs.gateways && devs.gateways.length) {
      html += '<div class="label-caps mb-2 mt-4">' + t('lbl_gateways','Gateways') + '</div>';
      html += '<table class="data-table data-table--compact">';
      html += '<thead><tr>';
      html += '<th>' + t('lbl_device','Device') + '</th>';
      html += '<th>' + t('lbl_model','Model') + '</th>';
      html += '<th>' + t('lbl_firmware','Firmware') + '</th>';
      html += '<th>' + t('lbl_status','Status') + '</th>';
      html += '</tr></thead><tbody>';
      for (let i = 0; i < devs.gateways.length; i++) {
        var gw = devs.gateways[i];
        let statusColor = gw.status === 'online' ? 'var(--green)' : 'var(--red)';
        let fwColor = (gw.fw_status === 'warning' || gw.fw_status === 'critical') ? 'var(--orange)' : 'var(--text)';
        html += '<tr>';
        html += '<td class="fw-medium">' + esc(gw.name) + '</td>';
        html += '<td class="text-muted">' + esc(gw.model) + '</td>';
        html += '<td class="' + toneClass(fwColor) + '">' + esc(gw.firmware) + (gw.fw_status === 'warning' || gw.fw_status === 'critical' ? '' : '') + '</td>';
        html += '<td><span class="dot ' + toneClass(statusColor) + ' mr-1"></span>' + esc(gw.status) + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // Firewalls table
    if (devs.firewalls && devs.firewalls.length) {
      html += '<div class="label-caps mb-2 mt-4">' + t('lbl_firewalls','Firewalls') + '</div>';
      html += '<table class="data-table data-table--compact">';
      html += '<thead><tr>';
      html += '<th>' + t('lbl_device','Device') + '</th>';
      html += '<th>' + t('lbl_model','Model') + '</th>';
      html += '<th>' + t('lbl_firmware','Firmware') + '</th>';
      html += '<th>' + t('lbl_ha_status','HA') + '</th>';
      html += '<th class="text-right">' + t('lbl_vpn_tunnels','VPN') + '</th>';
      html += '<th class="text-right">' + t('lbl_sessions','Sessions') + '</th>';
      html += '</tr></thead><tbody>';
      for (let i = 0; i < devs.firewalls.length; i++) {
        var fw = devs.firewalls[i];
        html += '<tr>';
        html += '<td class="fw-medium">' + esc(fw.name) + '</td>';
        html += '<td class="text-muted">' + esc(fw.model) + '</td>';
        html += '<td>' + esc(fw.firmware) + '</td>';
        html += '<td>' + esc(fw.ha || 'standalone') + '</td>';
        html += '<td class="text-right fw-semibold">' + (Number(fw.vpn_tunnels) || 0) + '</td>';
        html += '<td class="text-right">' + (Number(fw.active_sessions) || 0).toLocaleString() + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // Placeholder divs for FortiGate threat summary and firewall audit
    if (tot.firewalls > 0) {
      html += '<div id="fg-threat-summary-panel" class="mt-4"><div class="text-sm text-muted">' + t('msg_loading_threats','Loading threat summary...') + '</div></div>';
      html += '<div id="fg-firewall-audit-panel" class="mt-4"><div class="text-sm text-muted">' + t('msg_loading_fw_audit','Loading firewall audit...') + '</div></div>';
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
    var html = '<div class="label-caps mb-2">' + t('hdr_threat_summary','Threat Summary') + ' <span class="fw-normal normal-case">(' + Number(d.period_days) + ' ' + t('lbl_days','days') + ')</span></div>';

    // Summary badges
    html += '<div class="flex gap-3 mb-3 flex-wrap">';
    html += '<span class="sev-count sev-critical">' + t('sev_critical','Critical') + ': ' + (Number(s.critical) || 0) + '</span>';
    html += '<span class="sev-count sev-high">' + t('sev_high','High') + ': ' + (Number(s.high) || 0) + '</span>';
    html += '<span class="sev-count sev-medium">' + t('sev_medium','Medium') + ': ' + (Number(s.medium) || 0) + '</span>';
    html += '<span class="sev-count sev-low">' + t('sev_low','Low') + ': ' + (Number(s.low) || 0) + '</span>';
    html += '<span class="sev-count sev-low">' + t('lbl_total','Total') + ': ' + (Number(s.total) || 0) + '</span>';
    html += '</div>';

    // By type
    if (d.by_type && Object.keys(d.by_type).length > 0) {
      html += '<div class="flex gap-3 mb-3 text-xs text-muted">';
      var typeLabels = {ips:'IPS', virus:'Antivirus', botnet:'Botnet', webfilter:'Web Filter'};
      for (var tkey in d.by_type) {
        html += '<span>' + (typeLabels[tkey] || esc(tkey)) + ': <strong class="text-default">' + Number(d.by_type[tkey]) + '</strong></span>';
      }
      html += '</div>';
    }

    // Recent events table (top 5 visible, rest collapsible)
    var recent = d.recent || [];
    if (recent.length > 0) {
      html += '<table class="data-table data-table--compact">';
      html += '<thead><tr>';
      html += '<th>' + t('col_time','Time') + '</th>';
      html += '<th>' + t('col_type','Type') + '</th>';
      html += '<th>' + t('col_severity','Severity') + '</th>';
      html += '<th>' + t('col_source_ip','Source IP') + '</th>';
      html += '<th>' + t('col_attack','Attack') + '</th>';
      html += '<th>' + t('col_action','Action') + '</th>';
      html += '</tr></thead><tbody>';
      var sevTones = {critical:'text-danger', high:'text-warning', medium:'text-accent', low:'text-muted'};
      for (var i = 0; i < recent.length; i++) {
        var ev = recent[i];
        html += i >= 5 ? '<tr class="fg-threat-extra" hidden>' : '<tr>';
        html += '<td class="font-mono text-xs">' + esc(ev.timestamp) + '</td>';
        html += '<td>' + esc(ev.type) + '</td>';
        html += '<td><span class="fw-semibold ' + (sevTones[ev.severity] || 'text-default') + '">' + esc(ev.severity) + '</span></td>';
        html += '<td class="font-mono text-xs">' + esc(ev.srcip) + '</td>';
        html += '<td>' + esc(ev.attack) + '</td>';
        html += '<td><span class="' + (ev.action === 'blocked' || ev.action === 'block' || ev.action === 'drop' ? 'text-success' : 'text-warning') + '">' + esc(ev.action) + '</span></td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
      if (recent.length > 5) {
        html += '<button class="btn btn-ghost btn-sm mt-2" data-click-handler="cdToggleFgThreatRows" data-less-label="' + esc(t('btn_show_less','Show less')) + '" data-all-label="' + esc(t('btn_show_all','Show all') + ' (' + recent.length + ')') + '">' + t('btn_show_all','Show all') + ' (' + recent.length + ')</button>';
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

    var html = '<div class="flex items-center justify-between mb-3">';
    html += '<div class="label-caps">' + t('hdr_firewall_audit','Firewall Rule Audit') + '</div>';
    html += '<div class="flex items-baseline gap-1">';
    html += '<span class="text-xl fw-bold ' + toneClass(scoreColor) + '">' + Number(d.score) + '</span>';
    html += '<span class="text-xs text-muted">/ 100</span>';
    html += '</div></div>';

    // Stats row
    html += '<div class="flex gap-4 mb-3 text-xs text-muted">';
    html += '<span>' + t('lbl_total_rules','Total rules') + ': <strong class="text-default">' + Number(d.total_rules) + '</strong></span>';
    html += '<span>' + t('lbl_enabled','Enabled') + ': <strong class="text-default">' + Number(d.enabled) + '</strong></span>';
    html += '<span>' + t('lbl_disabled_rules','Disabled') + ': <strong class="text-default">' + Number(d.disabled) + '</strong></span>';
    html += '<span>' + t('lbl_unused_rules','Unused') + ': <strong class="text-default">' + Number(d.unused_rules) + '</strong></span>';
    html += '</div>';

    // Issues table
    var issues = d.issues || [];
    if (issues.length > 0) {
      html += '<table class="data-table data-table--compact">';
      html += '<thead><tr>';
      html += '<th>' + t('col_policy','Policy') + '</th>';
      html += '<th>' + t('col_issue','Issue') + '</th>';
      html += '<th>' + t('col_severity','Severity') + '</th>';
      html += '<th>' + t('col_detail','Detail') + '</th>';
      html += '</tr></thead><tbody>';
      var issuePillColors = {any_any:'var(--red)', no_logging:'var(--orange)', unused:'var(--blue)', scheduled:'var(--blue)'};
      var sevPillColors = {critical:'var(--red)', warning:'var(--orange)', info:'var(--blue)'};
      var issueLabels = {any_any: t('issue_any_any','Any-Any'), no_logging: t('issue_no_logging','No Logging'), unused: t('issue_unused','Unused'), scheduled: t('issue_scheduled','Scheduled')};
      for (var i = 0; i < issues.length; i++) {
        var iss = issues[i];
        html += '<tr>';
        html += '<td class="fw-medium">#' + Number(iss.policy_id) + ' ' + esc(iss.name) + '</td>';
        html += '<td><span class="' + badgeClass(issuePillColors[iss.issue]) + '">' + (issueLabels[iss.issue] || esc(iss.issue)) + '</span></td>';
        html += '<td><span class="' + badgeClass(sevPillColors[iss.severity]) + '">' + esc(iss.severity) + '</span></td>';
        html += '<td class="text-muted">' + esc(iss.detail) + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    } else {
      html += '<div class="text-xs text-success py-2 px-0">' + t('msg_no_fw_issues','No firewall policy issues detected.') + '</div>';
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
  var tone = abs < 60 ? 'text-success' : abs <= 75 ? 'text-warning' : 'text-danger';
  // 4-bar indicator
  var bars = abs < 55 ? 4 : abs < 65 ? 3 : abs < 75 ? 2 : 1;
  var h = '<span class="signal ' + tone + '">';
  for (var b = 1; b <= 4; b++) {
    h += '<span class="signal-bar' + (b <= bars ? ' is-on' : '') + '"></span>';
  }
  h += '</span>';
  h += '<span class="text-2xs text-muted ml-1">' + Number(dbm) + '</span>';
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

    var html = '<div class="mt-5 border-t pt-4">';
    html += '<div class="flex items-center justify-between mb-3 cursor-pointer" data-click-handler="cdToggleUnifiClients">';
    html += '<div>';
    html += '<span class="label-caps">' + t('hdr_connected_clients','Connected Clients') + '</span>';
    html += '<span class="text-xs text-muted ml-3">' + esc(summary) + '</span>';
    html += '</div>';
    html += '<span id="unifi-clients-toggle" class="text-xs text-accent cursor-pointer">' + t('lbl_show_clients','Show clients') + '</span>';
    html += '</div>';

    // Collapsible table (hidden by default)
    html += '<table id="unifi-clients-table" class="data-table data-table--compact" hidden>';
    html += '<thead><tr>';
    html += '<th>' + t('lbl_hostname','Hostname') + '</th>';
    html += '<th>' + t('lbl_ip_address','IP') + '</th>';
    html += '<th>' + t('lbl_mac_address','MAC') + '</th>';
    html += '<th class="text-center">' + t('lbl_type','Type') + '</th>';
    html += '<th>' + t('lbl_signal','Signal') + '</th>';
    html += '<th class="text-right">' + t('lbl_bandwidth','Bandwidth') + '</th>';
    html += '<th>' + t('lbl_connected_to','Connected to') + '</th>';
    html += '</tr></thead><tbody>';

    for (var i = 0; i < clients.length; i++) {
      var c = clients[i];
      var displayName = esc(c.name || c.hostname || c.mac);
      var typeIcon = c.type === 'wireless'
        ? '<span title="WiFi" class="text-accent">&#9678;</span>'
        : '<span title="Ethernet" class="text-muted">&#9644;</span>';
      var signalHtml = c.type === 'wireless' ? _signalBars(c.signal) : '<span class="text-dim">&#8212;</span>';
      var bw = _formatBytes((c.rx_bytes || 0) + (c.tx_bytes || 0));

      html += '<tr>';
      html += '<td class="fw-medium">' + displayName + '</td>';
      html += '<td class="font-mono text-xs">' + esc(c.ip || '') + '</td>';
      html += '<td class="font-mono text-xs text-muted">' + esc(c.mac || '') + '</td>';
      html += '<td class="text-center">' + typeIcon + '</td>';
      html += '<td>' + signalHtml + '</td>';
      html += '<td class="text-right text-muted">' + bw + '</td>';
      html += '<td class="text-muted">' + esc(c.connected_to || '') + '</td>';
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

    var html = '<div class="mt-5 border-t pt-4">';
    html += '<div class="label-caps mb-3">' + t('hdr_wifi_health','WiFi Health') + '</div>';

    // Alerts
    if (alerts.length > 0) {
      html += '<div class="mb-4">';
      html += '<div class="label-caps mb-2">' + t('hdr_alerts_wifi','WiFi Alerts') + ' (' + alerts.length + ')</div>';
      for (let i = 0; i < Math.min(alerts.length, 15); i++) {
        var a = alerts[i];
        var alertColor = a.type === 'rogue_ap' ? 'var(--red)' : 'var(--orange)';
        var alertLabel = a.type === 'rogue_ap' ? t('lbl_rogue_ap','Rogue AP')
          : a.type === 'high_interference' ? t('lbl_high_interference','High interference')
          : t('lbl_poor_satisfaction','Poor satisfaction');
        html += '<div class="text-xs ' + toneClass(alertColor) + ' py-0-5 px-0">';
        html += '<span class="fw-semibold">' + esc(alertLabel) + ':</span> ' + esc(a.message);
        html += '</div>';
      }
      if (alerts.length > 15) {
        html += '<div class="text-xs text-muted py-0-5 px-0">+ ' + (alerts.length - 15) + ' more...</div>';
      }
      html += '</div>';
    }

    // Per-AP health table
    if (aps.length > 0) {
      html += '<div class="label-caps mb-2">' + t('hdr_ap_health','Access Point Health') + '</div>';
      html += '<table class="data-table data-table--compact mb-4">';
      html += '<thead><tr>';
      html += '<th>' + t('lbl_device','Device') + '</th>';
      html += '<th class="text-right">' + t('lbl_clients','Clients') + '</th>';
      html += '<th>' + t('lbl_channel','Channel') + '</th>';
      html += '<th>' + t('lbl_satisfaction','Satisfaction') + '</th>';
      html += '<th>' + t('lbl_status','Status') + '</th>';
      html += '</tr></thead><tbody>';

      for (let i = 0; i < aps.length; i++) {
        var ap = aps[i];
        var satPct = ap.satisfaction != null ? Number(ap.satisfaction) : null;
        var satColor = satPct === null ? 'var(--text-dim)' : satPct >= 80 ? 'var(--green)' : satPct >= 70 ? 'var(--orange)' : 'var(--red)';
        var satBar = '';
        if (satPct !== null) {
          satBar = '<div class="flex items-center gap-2">';
          satBar += '<div class="bar flex-1 max-w-bar">';
          satBar += '<div class="bar-fill ' + toneClass(satColor).replace('text-', 'is-') + '" data-bar="' + satPct + '"></div></div>';
          satBar += '<span class="' + toneClass(satColor) + ' fw-semibold">' + satPct + '%</span></div>';
        } else {
          satBar = '<span class="text-dim">&#8212;</span>';
        }
        var statusColor = ap.status === 'online' ? 'var(--green)' : 'var(--red)';

        html += '<tr>';
        html += '<td class="fw-medium">' + esc(ap.name) + '</td>';
        html += '<td class="text-right fw-semibold">' + (Number(ap.clients) || 0) + '</td>';
        html += '<td class="text-muted">' + esc(ap.channels || '') + '</td>';
        html += '<td>' + satBar + '</td>';
        html += '<td><span class="dot ' + toneClass(statusColor) + ' mr-1"></span>' + esc(ap.status) + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    // SSID list
    if (ssids.length > 0) {
      html += '<div class="label-caps mb-2">' + t('hdr_ssid_list','SSIDs') + '</div>';
      html += '<table class="data-table data-table--compact">';
      html += '<thead><tr>';
      html += '<th>' + t('lbl_ssid','SSID') + '</th>';
      html += '<th>' + t('lbl_security','Security') + '</th>';
      html += '<th class="text-right">' + t('lbl_clients','Clients') + '</th>';
      html += '<th>' + t('lbl_status','Status') + '</th>';
      html += '</tr></thead><tbody>';

      for (let i = 0; i < ssids.length; i++) {
        var s = ssids[i];
        var enabledLabel = s.enabled ? t('lbl_enabled','Enabled') : t('lbl_disabled','Disabled');
        var enabledColor = s.enabled ? 'var(--green)' : 'var(--text-dim)';
        var guestBadge = s.is_guest ? ' <span class="badge badge-info">' + t('lbl_guest','Guest') + '</span>' : '';

        html += '<tr>';
        html += '<td class="fw-medium">' + esc(s.name) + guestBadge + '</td>';
        html += '<td class="text-muted">' + esc(s.security) + '</td>';
        html += '<td class="text-right fw-semibold">' + (Number(s.clients) || 0) + '</td>';
        html += '<td class="' + toneClass(enabledColor) + '">' + esc(enabledLabel) + '</td>';
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

async function _loadCustomerNotes(customerId) {
  // Held from before the request: if another customer's page replaces this
  // one meanwhile, the answer lands in a detached box, not in that page's.
  var ta = document.getElementById('detail-notes-textarea');
  var el = document.getElementById('detail-notes-status');
  try {
    var d = await apiFetch('/api/customer/' + encodeURIComponent(customerId) + '/notes');
    if (!ta || !ta.isConnected || _custPage.id !== customerId) return;
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
    // Older versions logged every customer switch: noise here, as in the bell.
    var entries = (d.entries || []).filter(function(e) { return e.action !== 'customer_switched' && e.action !== 'settings_changed'; });
    var actionIcons = {
      audit_started:'\u25B6', audit_completed:'\u2713', report_generated:'',
      email_sent:'', remediation_updated:'', backup_created:'',
      customer_switched:'', settings_changed:'', itglue_uploaded:'',
    };
    var html = '<div class="flex items-center justify-between mb-3">'
      + '<div class="card-title mb-0">' + t('hdr_activity_log') + '</div>'
      + '<span class="text-xs text-dim">' + t('lbl_last_prefix','Last:') + ' ' + entries.length + '</span></div>';
    if (entries.length === 0) {
      html += '<div class="text-sm text-dim py-2 px-0">' + t('msg_no_notifications','Ingen hendelser') + '</div>';
    } else {
      entries.forEach(function(e) {
        var icon = actionIcons[e.action] || '';
        var ts = e.timestamp ? timeAgo(e.timestamp) : '';
        html += '<div class="flex gap-3 py-2 px-0 border-b text-xs">'
          + '<span class="shrink-0">' + icon + '</span>'
          + '<span class="flex-1 text-default">' + esc(_activityLabel(e.action)) + (e.detail ? ' · <span class="text-muted">' + esc(e.detail) + '</span>' : '') + '</span>'
          + '<span class="text-dim nowrap">' + esc(ts) + (e.user ? ' · ' + esc(e.user) : '') + '</span>'
          + '</div>';
      });
    }
    el.innerHTML = html;
  } catch(e) { el.innerHTML = ''; }
}

// Saved to the customer whose page the box is on, named in the address: the
// notes are that customer's whichever customer another tab has open.
async function saveDetailNotes(customerId) {
  var ta = document.getElementById('detail-notes-textarea');
  if (!ta || !customerId || _custPage.id !== customerId) return;
  var st = document.getElementById('detail-notes-status');
  try {
    var d = await apiFetch('/api/customer/' + encodeURIComponent(customerId) + '/notes', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({notes:ta.value})});
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

export async function loadCustomerLicenses(accountId) {
  // On the customer page's Detaljer tab, under Lisenser.
  var box = document.getElementById('cust-licenses-panel');
  if (!box) return;

  box.innerHTML = '<div class="empty-note"><div class="loader loader-lg mx-auto mt-0 mb-4"></div>' + t('msg_loading_licenses','Loading licenses...') + '</div>';

  try {
    var d = await apiFetch('/api/also/subscriptions/' + encodeURIComponent(accountId));
    var subs = d.subscriptions || [];

    if (subs.length === 0) {
      box.innerHTML = '<div class="card p-8 text-center text-dim">'
        + '<div class="text-icon mb-4"></div>'
        + '<div class="text-lg fw-semibold mb-2">' + t('also_no_licenses','No licenses found') + '</div>'
        + '<div class="text-sm">' + t('also_no_licenses_desc','This customer has no active subscriptions in ALSO Cloud.') + '</div>'
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

    var html = '<div class="flex items-center justify-between mb-4 flex-wrap gap-3">'
      + '<div class="text-xl fw-bold">' + t('nav_licenses','Licenses') + '</div>'
      + '<div class="kpi-row kpi-row--inline">'
      + '<div class="kpi">'
      + '<div class="kpi-value text-accent">' + subs.length + '</div>'
      + '<div class="kpi-label">' + t('also_subscriptions','Subscriptions') + '</div></div>'
      + '<div class="kpi">'
      + '<div class="kpi-value text-success">' + activeCount + '</div>'
      + '<div class="kpi-label">' + t('active') + '</div></div>'
      + (totalSeats > 0 ? '<div class="kpi">'
      + '<div class="kpi-value text-purple">' + totalSeats + '</div>'
      + '<div class="kpi-label">' + t('also_total_seats','Total Seats') + '</div></div>' : '')
      + '</div></div>';

    // Table
    html += '<div class="card p-0 overflow-hidden">'
      + '<table class="data-table data-table--roomy">'
      + '<thead><tr>'
      + '<th class="label-caps">' + t('also_product','Product') + '</th>'
      + '<th class="label-caps">' + t('vendor') + '</th>'
      + '<th class="label-caps text-center py-3 px-4">' + t('qty') + '</th>'
      + '<th class="label-caps text-center py-3 px-4">' + t('term') + '</th>'
      + '<th class="label-caps text-center py-3 px-4">' + t('started') + '</th>'
      + '<th class="label-caps text-center py-3 px-4">' + t('renews') + '</th>'
      + '<th class="label-caps text-center py-3 px-4">' + t('also_status','Status') + '</th>'
      + '</tr></thead><tbody>';

    subs.forEach(function(s, i) {
      var name = s.ServiceDisplayName || s.ProductName || s.Name || s.SubscriptionName || s.OfferName || '-';
      var vendor = s.VendorDisplayName || s.Vendor || '';
      var started = s.BillingStartDate ? esc(s.BillingStartDate.slice(0,10)) : '-';
      var renews = s.ContractEndDate ? s.ContractEndDate.slice(0,10) : '-';
      var status = s.AccountState || s.Status || s.status || 'Active';
      var statusLower = status.toLowerCase();
      var statusColor = statusLower === 'active' ? 'var(--green)' : statusLower === 'suspended' ? 'var(--red)' : statusLower === 'completed' ? 'var(--green)' : 'var(--orange)';
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
        renewHtml = esc(renews) + ' <span class="text-2xs ' + toneClass(renewColor) + '">(' + (daysLeft < 0 ? 'expired' : daysLeft + 'd') + ')</span>';
      }

      var termColor = termLabel === 'Monthly' ? 'var(--blue)' : termLabel === 'Annual' ? 'var(--purple)' : 'var(--text-muted)';

      var qty = Number(s.Quantity || s.quantity || s.SeatCount) || 0;

      html += '<tr class="cursor-pointer" data-click-handler="alsoToggleSubDetail" data-sub-id="'+esc(subId)+'">'
        + '<td class="fw-medium">' + esc(name) + '</td>'
        + '<td class="text-muted">' + esc(vendor) + '</td>'
        + '<td class="text-center fw-bold">' + (qty > 0 ? qty : '<span class="text-dim">-</span>') + '</td>'
        + '<td class="text-center"><span class="text-xs fw-semibold ' + toneClass(termColor) + '">'+termIcon+' '+termLabel+'</span></td>'
        + '<td class="text-center text-xs text-dim">' + started + '</td>'
        + '<td class="text-center text-xs">' + renewHtml + '</td>'
        + '<td class="text-center"><span class="' + badgeClass(statusColor) + '">' + esc(status) + '</span></td>'
        + '</tr>';
      // Detail row (hidden by default, loaded on click)
      html += '<tr id="also-sub-'+esc(subId)+'" style="display:none;"><td colspan="7"></td></tr>';
    });

    html += '</tbody></table></div>';

    box.innerHTML = html;
  } catch(e) {
    box.innerHTML = '<div class="alert alert-error">' + t('also_license_error','Failed to load licenses') + ': ' + esc(e.message) + '</div>';
  }
}

// ── Hosting card (billing module) ───────────────────────────────────────────

export async function _unifiedLoadUniwebCard(custId) {
  var cardEl = document.getElementById('customer-uniweb-panel');

  try {
    var uw = await apiFetch('/api/uniweb/customer/' + encodeURIComponent(custId));
    if (!uw || !uw.matched || !cardEl) return;

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
      return '<div class="flex items-center gap-2 fw-semibold text-sm mt-4 mb-2 pb-1 border-b">'
        + '<span class="text-base opacity-70">' + esc(icon) + '</span>'
        + '<span>' + esc(title) + '</span></div>';
    }

    var h = '';
    h += '<div class="card p-4 mb-4">';

    // Header with last updated
    h += '<div class="flex items-center justify-between mb-3">';
    h += '<div class="flex items-center gap-2">';
    h += '<span class="text-lg"></span>';
    h += '<span class="text-base fw-semibold">' + t('hosting_uniweb') + '</span>';
    h += '</div>';
    h += '<div class="flex flex-col items-end gap-0-5">';
    h += '<div class="text-xs text-muted">' + esc(uw.account_name) + (uw.account_id ? ' \u00b7 ID: ' + esc(uw.account_id) : '') + '</div>';
    if (uw.last_sync) {
      h += '<div class="text-2xs text-dim" title="' + esc(new Date(uw.last_sync).toLocaleString(_lang === 'en' ? 'en-GB' : 'nb-NO')) + '">' + t('lbl_last_updated','Sist oppdatert') + ': ' + esc(_uwRelativeTime(uw.last_sync)) + '</div>';
    }
    h += '</div></div>';

    // Summary metrics row
    h += '<div class="grid grid-auto-sm gap-2 mb-1">';

    h += '<div class="kpi">';
    h += '<div class="text-lg fw-bold">' + (uw.domains ? uw.domains.length : 0) + '</div>';
    h += '<div class="text-2xs text-muted">' + t('domener') + '</div></div>';

    h += '<div class="kpi">';
    h += '<div class="text-lg fw-bold">' + (uw.subscriptions ? uw.subscriptions.length : 0) + '</div>';
    h += '<div class="text-2xs text-muted">' + t('abonnementer') + '</div></div>';

    h += '<div class="kpi">';
    h += '<div class="text-lg fw-bold text-accent">' + (uw.monthly_total > 0 ? uw.monthly_total.toFixed(0) : '0') + '</div>';
    h += '<div class="text-2xs text-muted">' + t('kr_mnd') + '</div></div>';

    h += '<div class="kpi">';
    h += '<div class="text-lg fw-bold">' + (uw.email ? uw.email.length : 0) + '</div>';
    h += '<div class="text-2xs text-muted">' + t('e_post_2') + '</div></div>';

    h += '<div class="kpi">';
    h += '<div class="text-lg fw-bold">' + (uw.ssl ? uw.ssl.length : 0) + '</div>';
    h += '<div class="text-2xs text-muted">SSL</div></div>';

    h += '</div>';

    // Domains table
    if (uw.domains && uw.domains.length) {
      h += _uwSection('', t('domener'));
      h += '<table class="data-table data-table--compact mb-3">';
      h += '<thead><tr>';
      h += '<th class="text-2xs">' + t('domene') + '</th>';
      h += '<th class="text-center text-2xs">DNS</th>';
      h += '<th class="text-center text-2xs">' + t('registrert') + '</th>';
      h += '<th class="text-center text-2xs">' + t('lbl_expires') + '</th>';
      h += '<th class="text-center text-2xs">' + t('status') + '</th>';
      h += '</tr></thead><tbody>';
      uw.domains.forEach(function(dom) {
        var domName = dom.domain || dom[''] || Object.values(dom)[0] || '';
        var dnsCount = dom.dns && Array.isArray(dom.dns) ? dom.dns.length : null;
        var regDate = dom.registered || dom.registration_date || dom.created || '';
        var expiryDays = _uwDaysUntil(dom.expiry);
        var expiryStyle = '';
        if (expiryDays !== null && expiryDays <= 30) {
          expiryStyle = expiryDays <= 7 ? 'text-danger fw-semibold' : 'text-warning fw-semibold';
        }
        h += '<tr class="cursor-pointer" data-click-handler="uwToggleDns" data-domain="' + esc(domName) + '">';
        h += '<td class="text-accent"><span class="uw-dns-arrow inline-block transition-transform text-2xs mr-1">&#9654;</span>' + esc(domName) + '</td>';
        h += '<td class="text-center text-dim">' + (dnsCount !== null ? '<span class="bg-base py-0-5 px-2 rounded-full text-2xs">' + dnsCount + '</span>' : '-') + '</td>';
        h += '<td class="text-center text-dim text-2xs">' + esc(regDate || '-') + '</td>';
        h += '<td class="text-center ' + expiryStyle + '">' + esc(dom.expiry || '-') + '</td>';
        h += '<td class="text-center">' + esc(dom.status || '-') + '</td>';
        h += '</tr>';
      });
      h += '</tbody></table>';
    }

    // Subscriptions table
    if (uw.subscriptions && uw.subscriptions.length) {
      h += _uwSection('', t('abonnementer'));
      h += '<table class="data-table data-table--compact mb-3">';
      h += '<thead><tr>';
      h += '<th class="text-2xs">' + t('tjeneste') + '</th>';
      h += '<th class="text-2xs">' + t('bruker_domene') + '</th>';
      h += '<th class="text-right text-2xs">' + t('pris_mnd') + '</th>';
      h += '<th class="text-center text-2xs">' + t('fornyelse') + '</th>';
      h += '</tr></thead><tbody>';
      uw.subscriptions.forEach(function(sub) {
        var price = sub['Price per month'] || sub.price_monthly || sub['Price per month'] || '-';
        var renewal = sub['Renewed until'] || sub.renewal_date || sub['Renewed until'] || '-';
        var renewDays = _uwDaysUntil(renewal);
        var renewStyle = '';
        var renewBg = '';
        if (renewDays !== null && renewDays <= 30) {
          if (renewDays <= 0) {
            renewStyle = 'text-danger fw-bold';
            renewBg = 'row-danger';
          } else if (renewDays <= 7) {
            renewStyle = 'text-danger fw-semibold';
            renewBg = 'row-danger';
          } else {
            renewStyle = 'text-warning fw-semibold';
            renewBg = 'row-warning';
          }
        }
        h += '<tr class="' + renewBg + '">';
        h += '<td>' + esc(sub.service_type || sub.Service || sub['Service type'] || '-') + '</td>';
        h += '<td>' + esc(sub.username_domain || sub.Username || sub['Username/domain'] || '-') + '</td>';
        h += '<td class="text-right font-mono">' + esc(price) + '</td>';
        h += '<td class="text-center ' + renewStyle + '">' + esc(renewal);
        if (renewDays !== null && renewDays <= 30) {
          h += ' <span class="text-2xs opacity-80">(' + (renewDays <= 0 ? t('lbl_expired', 'Expired') + ')'  : renewDays + 'd)') + '</span>';
        }
        h += '</td></tr>';
      });
      h += '</tbody></table>';
    }

    // Email table (proper table instead of just count)
    if (uw.email && uw.email.length) {
      h += _uwSection('', t('uniweb_email_accounts') + ' (' + uw.email.length + ')');
      h += '<table class="data-table data-table--compact mb-3">';
      h += '<thead><tr>';
      h += '<th class="text-2xs">' + t('adresse') + '</th>';
      h += '<th class="text-2xs">' + t('type') + '</th>';
      h += '<th class="text-2xs">' + t('domene') + '</th>';
      h += '<th class="text-center text-2xs">' + t('kvote') + '</th>';
      h += '<th class="text-center text-2xs">' + t('status') + '</th>';
      h += '</tr></thead><tbody>';
      uw.email.forEach(function(em) {
        var addr = em.address || em[''] || em.email || em.username || '-';
        var emType = em.type || em.Type || em.product || '-';
        var emDomain = em.domain || (typeof addr === 'string' && addr.indexOf('@') > 0 ? addr.split('@')[1] : '-');
        var quota = em.quota || em.disk_quota || em.size || '';
        var emStatus = em.status || em.state || '-';
        var statusColor = emStatus === 'active' || emStatus === 'aktiv' ? 'var(--green)' : 'var(--text-dim)';
        h += '<tr>';
        h += '<td class="font-mono text-2xs">' + esc(addr) + '</td>';
        h += '<td>' + esc(emType) + '</td>';
        h += '<td class="text-dim">' + esc(emDomain) + '</td>';
        h += '<td class="text-center text-dim">' + esc(quota || '-') + '</td>';
        h += '<td class="text-center"><span class="' + toneClass(statusColor) + '">' + esc(emStatus) + '</span></td>';
        h += '</tr>';
      });
      h += '</tbody></table>';
    }

    // SSL certificates
    if (uw.ssl && uw.ssl.length) {
      h += _uwSection('', t('uniweb_ssl_certificates') + ' (' + uw.ssl.length + ')');
      h += '<details class="text-sm mt-0-5"><summary class="cursor-pointer text-muted text-xs">' + t('vis_detaljer') + '</summary>';
      h += '<table class="data-table data-table--compact mt-1">';
      h += '<thead><tr>';
      h += '<th class="text-2xs">' + t('domene') + '</th>';
      h += '<th class="text-2xs">' + t('type') + '</th>';
      h += '<th class="text-center text-2xs">' + t('lbl_expires') + '</th>';
      h += '</tr></thead><tbody>';
      uw.ssl.forEach(function(cert) {
        var certDays = _uwDaysUntil(cert.expiry);
        var certStyle = '';
        if (certDays !== null && certDays <= 30) {
          certStyle = certDays <= 7 ? 'text-danger fw-semibold' : 'text-warning';
        }
        h += '<tr><td>' + esc(cert.domain || '') + '</td><td class="text-muted">' + esc(cert.type || '-') + '</td><td class="text-center ' + certStyle + '">' + esc(cert.expiry || '-') + '</td></tr>';
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
    // The chip that showed this failure went with the M365-status page; say
    // it where the card would have been.
    console.warn('Hosting card load failed:', e);
    if (cardEl) cardEl.innerHTML = '<div class="alert alert-error">' + esc(t('hosting_uniweb')) + ': ' + esc(t('lbl_error', 'Feil')) + '</div>';
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

export async function uwToggleDns(row, domain) {
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
  var loadingHtml = '<tr class="uw-dns-row"><td colspan="' + cols + '" class="py-3 px-4 bg-base text-center">';
  loadingHtml += '<div class="loader align-middle"></div>';
  loadingHtml += '<span class="ml-2 text-xs text-muted">' + t('msg_fetching_dns') + '</span>';
  loadingHtml += '</td></tr>';
  row.insertAdjacentHTML('afterend', loadingHtml);
  var loadingRow = row.nextElementSibling;

  // Fetch DNS records
  try {
    var d = await apiFetch('/api/uniweb/dns/' + encodeURIComponent(domain));
    if (!d || !Array.isArray(d.records)) throw new Error('DNS data unavailable');

    var dnsHtml = '<td colspan="' + cols + '" class="py-2 px-4 bg-base">';
    if (d && d.records && d.records.length > 0) {
      dnsHtml += '<table class="data-table data-table--compact">';
      dnsHtml += '<thead><tr>';
      dnsHtml += '<th>' + t('vertsnavn') + '</th>';
      dnsHtml += '<th class="text-center">' + t('type') + '</th>';
      dnsHtml += '<th>' + t('verdi') + '</th>';
      dnsHtml += '<th class="text-right">TTL</th>';
      dnsHtml += '</tr></thead><tbody>';
      d.records.forEach(function(r) {
        var dnsBadges = { 'A': 'badge-info', 'AAAA': 'badge-info', 'MX': 'badge-purple', 'CNAME': 'badge-success', 'TXT': 'badge-warning', 'SRV': 'badge-info', 'PTR': 'badge-info' };
        var typeBadge = 'badge ' + (dnsBadges[r.type] || '');
        dnsHtml += '<tr>';
        dnsHtml += '<td>' + esc(r.hostname) + '</td>';
        dnsHtml += '<td class="text-center"><span class="' + typeBadge + '">' + esc(r.type) + '</span></td>';
        dnsHtml += '<td class="font-mono text-2xs break-all">' + esc(r.value) + '</td>';
        dnsHtml += '<td class="text-right text-dim">' + Number(r.ttl) + '</td></tr>';
      });
      dnsHtml += '</tbody></table>';
    } else {
      dnsHtml += '<span class="text-dim text-xs">' + t('ingen_dns_poster_funnet') + '</span>';
    }
    dnsHtml += '</td>';

    // Replace loading row content
    if (loadingRow && loadingRow.classList.contains('uw-dns-row')) {
      loadingRow.innerHTML = dnsHtml;
    }
  } catch(e) {
    if (loadingRow && loadingRow.classList.contains('uw-dns-row')) {
      loadingRow.innerHTML = '<td colspan="' + cols + '" class="py-2 px-4 bg-base"><span class="text-danger text-xs">' + t('feil_ved_henting_av_dns') + '</span></td>';
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
  cell.innerHTML = '<div class="py-3 px-4"><div class="loader"></div> ' + t('loading_details') + '</div>';

  var d = await apiFetch('/api/also/subscription/' + encodeURIComponent(subId));
  if (!d || d.error) {
    cell.innerHTML = '<div class="py-3 px-4 text-danger text-sm">' + esc(d && d.error || 'Failed to load') + '</div>';
    return;
  }
  var s = d.subscription || d;
  var fields = s.Fields || s.fields || [];
  var items = s.PriceableItems || s.priceableItems || [];

  var html = '<div class="callout">';
  html += '<table class="kv-table text-sm text-muted mb-3">';
  html += '<tr><td class="nowrap">' + t('contract') + '</td><td class="fw-semibold">' + esc(s.ContractId || '-') + '</td></tr>';
  if (s.VendorReferenceId) html += '<tr><td>' + t('vendor_ref') + '</td><td class="font-mono text-xs">' + esc(s.VendorReferenceId) + '</td></tr>';
  if (s.DependencyServiceName) html += '<tr><td>' + t('depends_on') + '</td><td>' + esc(s.DependencyServiceName.split('_').pop() || s.DependencyServiceName) + '</td></tr>';
  html += '</table>';

  // Fields (seat counts, config) — ALSO uses Name/DisplayName/Value (PascalCase)
  if (fields.length) {
    html += '<div class="text-xs fw-semibold mb-2 text-default">' + t('seats_configuration') + '</div>';
    html += '<table class="data-table data-table--compact mb-3">';
    fields.forEach(function(f) {
      var label = f.DisplayName || f.displayName || f.Name || f.name || f.FieldName || '?';
      var val = f.Value != null ? f.Value : f.value != null ? f.value : '-';
      html += '<tr>';
      html += '<td class="text-muted nowrap align-top cell-label">' + esc(label) + '</td>';
      html += '<td class="fw-semibold text-default break-word">' + esc(String(val)) + '</td>';
      html += '</tr>';
    });
    html += '</table>';
  }

  // PriceableItems (pricing) — ALSO uses PriceableItemDescription, PurchasePrice, SalesPrice, etc.
  if (items.length) {
    html += '<div class="text-xs fw-semibold mb-1 text-default">' + t('pricing') + '</div>';
    html += '<table class="data-table data-table--compact">';
    html += '<tr>'
      + '<th>' + t('item') + '</th>'
      + '<th>' + t('type') + '</th>'
      + '<th class="text-right">' + t('purchase') + '</th>'
      + '<th class="text-right">' + t('sales') + '</th>'
      + '<th class="text-right">RRP</th>'
      + '<th>' + t('currency') + '</th>'
      + '<th>' + t('product') + '</th>'
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
      html += '<tr>';
      html += '<td>' + esc(pDesc) + '</td>';
      html += '<td class="text-2xs text-dim">' + esc(typeLabel) + '</td>';
      html += '<td class="text-right font-mono">' + (pBuy != null ? Number(pBuy).toFixed(2) : '-') + '</td>';
      html += '<td class="text-right font-mono fw-semibold">' + (pSell != null ? Number(pSell).toFixed(2) : '-') + '</td>';
      html += '<td class="text-right font-mono text-dim">' + (pRrp != null ? Number(pRrp).toFixed(2) : '-') + '</td>';
      html += '<td class="text-2xs">' + esc(pCurr) + '</td>';
      html += '<td class="font-mono text-2xs text-dim">' + esc(pProd) + '</td>';
      html += '</tr>';
    });
    html += '</table>';
  }

  if (!fields.length && !items.length) {
    // Log the raw keys so we can debug
    html += '<div class="text-sm text-dim">No Fields/PriceableItems found. Keys: ' + esc(Object.keys(s).join(', ')) + '</div>';
  }

  html += '</div>';
  cell.innerHTML = html;
}

// ── Tilgang: this customer's Tailscale nodes ────────────────────────────────
// A node belongs to a customer when a technician assigned it here, or when it
// carries the customer's tag (tag:customer-<slug>) in the tailnet; the server
// decides (app/services/tailscale_customers.py). Each row says how to reach
// the node; a hand assignment can be taken back, a tag is changed in Tailscale.
async function _loadCustomerTailscale(customerId) {
  var el = document.getElementById('customer-tailscale-panel');
  if (!el) return;
  el.innerHTML = '<div class="card-title">Tailscale</div><div class="loading-note"><div class="loader"></div></div>';
  var d = await apiFetch('/api/tailscale/customer/' + encodeURIComponent(customerId) + '/nodes').catch(function() { return null; });
  if (!el.isConnected || _custPage.id !== customerId) return;
  var head = '<div class="cust-card-head"><div class="card-title">Tailscale</div>'
    + '<button class="btn btn-ghost btn-sm" data-view-gate="tailscale" data-click-handler="showView" data-view="tailscale">' + esc(t('btn_all_tailscale_nodes', 'Alle noder')) + '</button>'
    + '</div>';
  if (!d) {
    el.innerHTML = head + '<p class="cust-card-text">' + esc(t('err_tailscale_nodes', 'Nodene kunne ikke hentes fra Tailscale.')) + '</p>';
    return;
  }
  if (!d.configured) {
    el.innerHTML = head + '<p class="cust-card-text">' + esc(t('msg_tailscale_not_configured', 'Tailscale er ikke satt opp. API-nøkkelen legges inn under Administrasjon.')) + '</p>';
    return;
  }

  var html = head;
  var nodes = d.nodes || [];
  if (!nodes.length) {
    html += '<p class="cust-card-text">' + esc(t('msg_tailscale_no_nodes', 'Ingen Tailscale-noder er knyttet til kunden.')) + '</p>';
  } else {
    html += '<table class="cust-ts-table"><thead><tr>'
      + '<th>' + esc(t('lbl_host_name', 'Navn')) + '</th>'
      + '<th>' + esc(t('lbl_status', 'Status')) + '</th>'
      + '<th>' + esc(t('lbl_connect_to', 'Koble til')) + '</th>'
      + '<th>' + esc(t('lbl_linked_by', 'Knyttet')) + '</th>'
      + '<th></th></tr></thead><tbody>';
    nodes.forEach(function(n) {
      var status = n.online
        ? '<span class="cust-ts-state is-online">' + esc(t('lbl_ts_online', 'Pålogget')) + '</span>'
        : '<span class="cust-ts-state">' + esc(t('lbl_ts_offline', 'Frakoblet')) + (n.last_seen_ago ? ' · ' + esc(n.last_seen_ago) : '') + '</span>';
      var connect = '';
      [n.ip, n.dns_name].forEach(function(v) {
        if (v) connect += '<button class="cust-ts-addr" data-click-handler="custTsCopy" data-value="' + esc(v) + '" title="' + esc(t('tip_click_to_copy', 'Klikk for å kopiere')) + '">' + esc(v) + '</button>';
      });
      var source = n.source === 'manual' ? t('lbl_linked_manual', 'for hånd') : t('lbl_linked_tag', 'med tag');
      var remove = n.source === 'manual'
        ? '<button class="btn btn-ghost btn-sm" data-write data-click-handler="custTsUnassign" data-customer-id="' + esc(customerId) + '" data-device-id="' + esc(n.id) + '">' + esc(t('btn_remove_link', 'Fjern')) + '</button>'
        : '';
      html += '<tr>'
        + '<td><span class="cust-ts-name">' + esc(n.name || n.hostname || '') + '</span> <span class="cust-ts-os">' + esc(n.os || '') + '</span></td>'
        + '<td>' + status + '</td>'
        + '<td><div class="cust-ts-connect">' + (connect || '-') + '</div></td>'
        + '<td>' + esc(source) + '</td>'
        + '<td>' + remove + '</td>'
        + '</tr>';
    });
    html += '</tbody></table>';
  }
  html += '<p class="cust-card-text cust-ts-hint">' + esc(t('msg_tailscale_tag_hint', 'Noder med taggen {tag} i Tailscale knyttes hit av seg selv.').replace('{tag}', d.tag || '')) + '</p>';
  html += '<div class="cust-ts-assign" data-write>'
    + '<select class="field-input" id="cust-ts-device" aria-label="' + esc(t('lbl_tailscale_assign', 'Knytt en node til kunden')) + '"><option value="">' + esc(t('lbl_tailscale_assign', 'Knytt en node til kunden')) + '</option></select>'
    + '<button class="btn btn-default btn-sm" data-click-handler="custTsAssign" data-customer-id="' + esc(customerId) + '">' + esc(t('btn_link_node', 'Knytt til')) + '</button>'
    + '</div>';
  el.innerHTML = html;
  applyWriteCapability();
  if (canWrite()) _custTsFillChoices(customerId);
}

// The nodes no customer has yet, for the assign list.
async function _custTsFillChoices(customerId) {
  var all = await apiFetch('/api/tailscale/devices').catch(function() { return null; });
  var sel = document.getElementById('cust-ts-device');
  if (!sel || !all || _custPage.id !== customerId) return;
  (all.devices || []).filter(function(dev) { return !dev.customer_id && !dev.customer_hidden; }).forEach(function(dev) {
    var opt = document.createElement('option');
    opt.value = dev.id;
    opt.textContent = (dev.given_name || dev.hostname || dev.name || dev.id) + (dev.tailscale_ip ? ' (' + dev.tailscale_ip + ')' : '');
    sel.appendChild(opt);
  });
}

async function _custTsAssign(customerId, btn) {
  var sel = document.getElementById('cust-ts-device');
  if (!sel || !sel.value || _custPage.id !== customerId) return;
  btn.disabled = true;
  var d = await apiFetch('/api/tailscale/device/' + encodeURIComponent(sel.value) + '/customer', {
    method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({customer_id: customerId}),
  });
  btn.disabled = false;
  if (d && d.ok) _loadCustomerTailscale(customerId);
}

async function _custTsUnassign(customerId, deviceId) {
  if (_custPage.id !== customerId) return;
  var d = await apiFetch('/api/tailscale/device/' + encodeURIComponent(deviceId) + '/customer', {
    method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({customer_id: null}),
  });
  if (d && d.ok) _loadCustomerTailscale(customerId);
}

function _custTsCopy(value) {
  if (!value || !navigator.clipboard) return;
  navigator.clipboard.writeText(value).then(function() { showToast(t('msg_copied', 'Kopiert til utklippstavle'), 'success', 1500); });
}
