/* Assessment library (Fase B).
 *
 * A browsable list of named, scored frameworks — the Sybr Standard, Essential
 * Eight, a CIS subset, NIS2 hardening — each run against a customer's latest
 * audit and read back as named results, not check ids. The engine is
 * app/core/baseline.py; this screen only browses /api/baselines and renders
 * /api/baselines/{id}/evaluate/{customer}/latest.
 *
 * Class-based markup on purpose: the CSP budget keeps inline styles from
 * growing, so styling lives in app.css (.asmt-*) and interactions bind with
 * addEventListener rather than inline handlers. Every visible string goes
 * through t(); the reason codes are translated by _reason() from app.js, the
 * same helper the customer-card baseline panel uses.
 */

var _asmtBaselines = null;

async function assessmentsLoad() {
  var el = document.getElementById('assessments-content');
  if (!el) return;
  el.innerHTML = '<div class="loader asmt-loader"></div>';

  // The view can be opened before the customer list has loaded elsewhere.
  if (!_allCustomers || !_allCustomers.length || !_customersActiveId) {
    var cs = await apiFetch('/api/customers').catch(function () { return null; });
    if (cs) { _allCustomers = cs.customers || []; _customersActiveId = cs.active_id; }
  }

  var d = await apiFetch('/api/baselines?lang=' + _lang).catch(function () { return null; });
  if (!d || !d.baselines) {
    el.innerHTML = '<div class="alert alert-error" data-i18n="status_error"></div>';
    translatePage(el);
    return;
  }
  _asmtBaselines = d.baselines;
  el.innerHTML = _asmtLibraryHTML();
  _asmtBind();
}

function _asmtCustomerOptions() {
  var active = _customersActiveId || '';
  return (_allCustomers || []).map(function (c) {
    var id = c._id || c.customer_id || '';
    var name = c.CustomerName || c.customer_name || id;
    var sel = id === active ? ' selected' : '';
    return '<option value="' + esc(id) + '"' + sel + '>' + esc(name) + '</option>';
  }).join('');
}

function _asmtLibraryHTML() {
  var hasCustomers = (_allCustomers || []).length > 0;
  var h = '<div class="asmt-bar">';
  h += '<span class="asmt-bar-label">' + esc(t('lbl_customer', 'Customer')) + '</span>';
  if (hasCustomers) {
    h += '<select class="asmt-select" id="asmt-customer">' + _asmtCustomerOptions() + '</select>';
  } else {
    h += '<span class="asmt-bar-label">' + esc(t('msg_no_customer_selected', 'No customer selected')) + '</span>';
  }
  h += '</div>';
  h += '<div class="asmt-grid">';
  (_asmtBaselines || []).forEach(function (b) { h += _asmtCardHTML(b); });
  h += '</div>';
  h += '<div class="asmt-result" id="asmt-result"></div>';
  return h;
}

function _asmtCardHTML(b) {
  var count = String(b.checks || 0);
  var h = '<div class="asmt-card">';
  h += '<div class="asmt-card-top">';
  h += '<div><span class="asmt-card-name">' + esc(b.name) + '</span>';
  h += '<span class="asmt-card-ver">' + esc(b.version || '') + '</span></div>';
  h += '<span class="asmt-badge">' + esc(count) + ' ' + esc(t('lbl_checks', 'checks')) + '</span>';
  h += '</div>';
  if (b.description) { h += '<div class="asmt-card-desc">' + esc(b.description) + '</div>'; }
  var tags = [];
  if (b.is_default) {
    tags.push('<span class="asmt-tag asmt-badge-default">' + esc(t('lbl_house_standard', 'House standard')) + '</span>');
  }
  (b.tags || []).forEach(function (tag) {
    tags.push('<span class="asmt-tag">' + esc(tag) + '</span>');
  });
  if (tags.length) { h += '<div class="asmt-tags">' + tags.join('') + '</div>'; }
  h += '<div class="asmt-card-foot">';
  h += '<button class="btn btn-sm btn-primary asmt-run" data-baseline="' + esc(b.id) + '">'
     + esc(t('btn_run_assessment', 'Run assessment')) + '</button>';
  h += '</div></div>';
  return h;
}

function _asmtBind() {
  var buttons = document.querySelectorAll('.asmt-run');
  Array.prototype.forEach.call(buttons, function (btn) {
    btn.addEventListener('click', function () {
      _asmtRun(btn.getAttribute('data-baseline'));
    });
  });
}

async function _asmtRun(baselineId) {
  var box = document.getElementById('asmt-result');
  if (!box || !baselineId) return;
  var select = document.getElementById('asmt-customer');
  var customerId = select ? select.value : (_customersActiveId || '');
  if (!customerId) { showToast(t('msg_no_customer_selected', 'No customer selected'), 'error'); return; }

  box.innerHTML = '<div class="loader asmt-loader"></div>';
  var res = await apiFetch(
    '/api/baselines/' + encodeURIComponent(baselineId) + '/evaluate/'
    + encodeURIComponent(customerId) + '/latest?lang=' + _lang
  ).catch(function () { return null; });
  if (!res) {
    box.innerHTML = '';
    showToast(t('status_error', 'Something went wrong'), 'error');
    return;
  }
  box.innerHTML = _asmtResultHTML(res);
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

var _ASMT_SEV_KEYS = { critical: 'sev_critical', high: 'sev_high', medium: 'sev_medium', low: 'sev_low' };

function _asmtSevPill(severity) {
  if (!severity) return '';
  var key = _ASMT_SEV_KEYS[severity] || 'sev_medium';
  var extra = severity === 'critical' ? ' asmt-sev-critical' : (severity === 'high' ? ' asmt-sev-high' : '');
  return '<span class="asmt-sev' + extra + '">' + esc(t(key, severity)) + '</span>';
}

function _asmtResultHTML(res) {
  if (res.evaluated === false || !res.baseline) {
    var code = res.reason_code || 'no_runs';
    var msg = _reason('drift_', code, {}) || t('msg_baseline_no_run', 'No audit run to measure against yet.');
    return '<div class="asmt-empty">' + esc(msg) + '</div>';
  }

  var pct = res.conformance_pct;
  var none = pct === null || pct === undefined;
  var pctCls = none ? 'asmt-pct-none' : (pct >= 90 ? 'asmt-pct-good' : (pct >= 70 ? 'asmt-pct-mid' : 'asmt-pct-bad'));
  var pctTxt = none ? '&#8211;' : (pct + ' %');

  var h = '<div class="asmt-result-head">';
  h += '<div class="asmt-result-name">' + esc(res.baseline.name) + ' ' + esc(res.baseline.version || '') + '</div>';
  h += '<div><span class="asmt-pct ' + pctCls + '">' + pctTxt + '</span>';
  h += '<span class="asmt-pct-label">' + esc(t('lbl_conformance', 'conformance')) + '</span></div>';
  h += '</div>';

  if (res.assessed === 0) {
    h += '<div class="asmt-basis">' + esc(t('msg_baseline_none_assessed', 'None of the checks could be measured on this run.')) + '</div>';
  } else {
    var basis = t('msg_baseline_basis', '{passed} of {assessed} measured checks passed')
      .split('{passed}').join(String(res.passed)).split('{assessed}').join(String(res.assessed));
    if (res.not_measured) {
      basis += ' · ' + t('msg_baseline_skipped', '{n} not measured').split('{n}').join(String(res.not_measured));
    }
    h += '<div class="asmt-basis">' + esc(basis) + '</div>';
  }

  h += '<table class="asmt-checks">';
  (res.checks || []).forEach(function (c) {
    var nm = c.status === 'not_measured';
    var icon = c.status === 'pass' ? '&#10003;' : (c.status === 'fail' ? '&#10007;' : '&#8211;');
    h += '<tr class="' + (nm ? 'asmt-check-nm' : '') + '">';
    h += '<td class="asmt-ico asmt-ico-' + esc(c.status) + '">' + icon + '</td>';
    h += '<td><span class="asmt-check-title">' + esc(c.title) + '</span>' + _asmtSevPill(c.severity);
    if (c.why) { h += '<div class="asmt-check-why">' + esc(c.why) + '</div>'; }
    h += '</td>';
    h += '<td class="asmt-check-reason">' + esc(_reason('bl_', c.reason_code, c.params)) + '</td>';
    h += '</tr>';
  });
  h += '</table>';
  return h;
}
