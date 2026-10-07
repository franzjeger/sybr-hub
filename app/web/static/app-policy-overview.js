// Policy planning is local to the Hub. Tenant changes keep their own guarded flows.
import {esc} from './app-esc.js';
import {_lang, t} from './app-i18n.js';
import {_custPage, canWrite, _currentUser} from './app-state.js';
import {formatRunName} from './app-format.js';
import {apiFetch} from './app-api.js';
import {registerUiHandlers} from './app-handlers.js';
import {showConfirm, showToast} from './app-ui.js';
import {onLoginViewShown} from './app-hooks.js';

var _po = null;
var _poCid = '';
var _poPane = 'overview';
var _poArea = '';
var _poPackage = '';
var _poTier = '';
var _poStatus = '';
var _poQuery = '';
var _poDraft = new Set();
var _poBusy = false;
var _poSequence = 0;

// Drafts stay in this authenticated tab, never in browser storage.
var _poSessions = new Map();
var _poReviews = {};
var _poOpen = new Set();
var _poBase = '';
function _poPlanKey() { return JSON.stringify([_poPackage, Array.from(_poDraft).sort()]); }
function _poReviewFields(review) {
  return {status: (review && review.status) || 'not_assessed', note: (review && review.note) || '', review_due: (review && review.review_due) || ''};
}
function _poCapture() {
  if (!_po || !_poCid) return;
  document.querySelectorAll('#po-results article[data-policy-id]').forEach(function(card) {
    var id = card.dataset.policyId;
    var details = card.querySelector('details');
    if (details.open) _poOpen.add(id); else _poOpen.delete(id);
    var form = card.querySelector('form');
    if (!form) return;
    var fields = new FormData(form);
    var draft = {status: fields.get('status'), note: fields.get('note'), review_due: fields.get('review_due') || ''};
    if (JSON.stringify(draft) === JSON.stringify(_poReviewFields(_po.plan.reviews[id]))) delete _poReviews[id];
    else _poReviews[id] = draft;
  });
  _poSessions.set(_poCid, {package: _poPackage, ids: Array.from(_poDraft), reviews: _poReviews, open: _poOpen, base: _poBase, plan: _po.plan});
}
function _poDirty() { return !!_po && (_poPlanKey() !== _poBase || Object.keys(_poReviews).length > 0); }
function _poDirtyNotice() {
  _poCapture();
  var el = document.getElementById('po-draft-notice');
  if (el) el.hidden = !_poDirty();
}
onLoginViewShown(function() { ++_poSequence; _poSessions.clear(); _poReviews = {}; _poOpen = new Set(); _po = null; _poCid = ''; });
window.addEventListener('beforeunload', function(event) {
  _poCapture();
  var dirty = _poDirty() || Array.from(_poSessions.values()).some(function(s) { return JSON.stringify([s.package, s.ids.slice().sort()]) !== s.base || Object.keys(s.reviews).length > 0; });
  if (dirty) { event.preventDefault(); event.returnValue = ''; }
});

registerUiHandlers({
  poGuide: function(el) {
    var step = el.dataset.step;
    if (step === 'package') _poPane = 'packages';
    else if (step === 'evidence') _poPane = 'tenant';
    else {
      _poPane = 'library'; _poArea = ''; _poTier = ''; _poQuery = ''; _poStatus = 'actionable';
      if (step === 'pilot' || step === 'verify') {
        var next = _po.catalog.policies.filter(function(p) { return _poDraft.has(p.id) && _poStatusOf(p) !== 'aligned' && _poStatusOf(p) !== 'exception'; }).sort(function(a, b) { return a.stage - b.stage; })[0];
        if (next) { _poQuery = next.id; _poOpen.add(next.id); }
      }
    }
    _poRender();
  },
  poDraftEdited: function() { _poDirtyNotice(); },
  poDiscardDraft: async function() {
    if (_poBusy || !await showConfirm(t('pl_discard_draft'), t('pl_discard_confirm'))) return;
    _poSessions.delete(_poCid); _poReviews = {}; _poBase = _poPlanKey();
    _po = null; await policyOverviewLoad();
  },
  poPane: function(el) { if (!_poBusy) { _poPane = el.dataset.pane; _poRender(); } },
  poArea: function(el) { _poPane = 'library'; _poArea = el.dataset.area; _poRender(); },
  poFilter: function(el) {
    if (el.id === 'po-area') _poArea = el.value;
    if (el.id === 'po-tier') _poTier = el.value;
    if (el.id === 'po-status') _poStatus = el.value;
    if (el.id === 'po-search') _poQuery = el.value;
    _poResults();
  },
  poPackage: function(el) {
    if (_poBusy) return;
    _poPackage = el.dataset.package;
    _poDraft = new Set(_po.catalog.packages.find(function(p) { return p.id === _poPackage; }).policy_ids);
    _poRender();
  },
  poSelect: function(el) {
    if (_poBusy) return;
    if (el.checked) _poDraft.add(el.dataset.policy); else _poDraft.delete(el.dataset.policy);
    _poDependencies();
    _poResults();
    _poSelectionCount();
    _poDirtyNotice();
  },
  poSavePlan: function() { _poSavePlan(); },
  poReview: function(el, event) { event.preventDefault(); _poSaveReview(el); },
  poReload: function() { if (!_poBusy) policyOverviewLoad(); },
});

function _poCanEdit() {
  return canWrite() && _currentUser && ['admin', 'technician'].indexOf(_currentUser.role) !== -1;
}
function _poCustomerId() { return _custPage.id || ''; }
function _poLoc(v) { return typeof v === 'string' ? v : ((v && (v[_lang] || v.en || v.no)) || ''); }
function _poStatusOf(p) {
  var r = _po.plan.reviews[p.id];
  return r && r.stale ? 'stale' : (r && r.status) || 'not_assessed';
}
function _poDependencies() {
  var policies = _po.catalog.policies;
  function add(id) {
    var p = policies.find(function(x) { return x.id === id; });
    p.dependencies.forEach(function(dep) {
      if (!_poDraft.has(dep)) { _poDraft.add(dep); add(dep); }
    });
  }
  Array.from(_poDraft).forEach(add);
}

export async function policyOverviewLoad() {
  var el = document.getElementById('policy-overview-content');
  if (!el) return;
  var cid = _poCustomerId();
  var sequence = ++_poSequence;
  _poCapture();
  el.innerHTML = '<div class="po-loading"><div class="loader"></div></div>';
  if (!cid) { el.textContent = t('msg_no_customer_selected'); return; }
  var po = await apiFetch('/api/policy-overview/' + encodeURIComponent(cid) + '?lang=' + _lang);
  if (cid !== _poCustomerId() || sequence !== _poSequence) return;
  if (!po) { el.textContent = t('status_error'); return; }
  if (_poCid !== cid) { _poPane = 'overview'; _poArea = ''; _poTier = ''; _poStatus = ''; _poQuery = ''; }
  var session = _poSessions.get(cid);
  _poCid = cid;
  _po = po;
  _poPackage = po.plan.package_id || po.catalog.packages.find(function(p) { return p.recommended; }).id;
  _poDraft = new Set(po.plan.package_id ? po.plan.policy_ids : po.catalog.packages.find(function(p) { return p.id === _poPackage; }).policy_ids);
  _poBase = _poPlanKey(); _poReviews = {}; _poOpen = new Set();
  if (session) {
    var dirty = JSON.stringify([session.package, session.ids.slice().sort()]) !== session.base || Object.keys(session.reviews).length > 0;
    if (dirty) { _poPackage = session.package; _poDraft = new Set(session.ids); _poReviews = session.reviews; _poBase = session.base; _po.plan = session.plan; }
    _poOpen = session.open;
  }
  _poRender();
}

function _poSelectionCount() {
  var el = document.getElementById('po-selection-count');
  if (el) el.textContent = _poDraft.size + ' ' + t('pl_selected');
}
function _poRender() {
  var el = document.getElementById('policy-overview-content');
  if (!el || !_po || _poCid !== _poCustomerId()) return;
  _poCapture();
  var html = '<div class="pl-heading"><div><h3>' + esc(t('pl_title')) + '</h3><p>' + esc(t('pl_intro')) + '</p></div>'
    + '<span class="pl-version">v' + esc(_po.catalog.version) + ' · ' + esc(t('pl_reviewed')) + ' ' + esc(_po.catalog.reviewed_on) + '</span></div>';
  html += '<nav class="pl-nav" aria-label="' + esc(t('pl_navigation')) + '">';
  ['overview', 'packages', 'library', 'tenant', 'changes'].forEach(function(pane) {
    html += '<button type="button" class="btn btn-sm' + (_poPane === pane ? ' btn-primary' : '') + '" aria-current="' + (_poPane === pane ? 'page' : 'false') + '" data-click-handler="poPane" data-pane="' + pane + '">' + esc(t('pl_' + pane)) + '</button>';
  });
  html += '</nav><div class="alert alert-warning flex flex-wrap gap-2" id="po-draft-notice"' + (_poDirty() ? '' : ' hidden') + '><span>' + esc(t('pl_unsaved_draft')) + '</span><button type="button" class="btn btn-sm" data-click-handler="poDiscardDraft">' + esc(t('pl_discard_draft')) + '</button></div>';
  if (_poPane === 'overview' || _poPane === 'packages' || _poPane === 'library') {
    html += '<div class="card pl-plan-bar"><div><strong>' + esc(_poLoc(_po.catalog.packages.find(function(p) { return p.id === _poPackage; }).name)) + '</strong>'
      + '<div class="text-muted">' + esc(t(_po.plan.package_id ? 'pl_saved_plan' : 'pl_proposal')) + ' · <span id="po-selection-count">' + Number(_poDraft.size) + ' ' + esc(t('pl_selected')) + '</span></div></div>';
    if (_poCanEdit()) html += '<button type="button" class="btn btn-primary" data-click-handler="poSavePlan"' + (_poBusy ? ' disabled' : '') + '>' + esc(t('pl_save_plan')) + '</button>';
    html += '</div><p class="text-muted text-sm">' + esc(t('pl_internal')) + '</p>';
  }
  if (_poPane === 'overview') html += _poOverview();
  if (_poPane === 'packages') html += _poPackages();
  if (_poPane === 'library') html += _poLibrary();
  if (_poPane === 'tenant') {
    html += '<p class="text-muted">' + esc(t('pl_captured_note')) + '</p>';
    if (_po.inventory_present) {
      html += '<p class="po-meta">' + esc(t('lbl_captured')) + ': ' + esc((_po.captured_at || '').slice(0, 10))
        + (_po.run ? ' · ' + esc(formatRunName(_po.run)) : '') + '</p>' + _poWorkloadBlocks(_po.workloads || {});
    } else html += '<div class="card po-dim">' + esc(t('msg_po_no_audit')) + '</div>';
    html += _poStandardBlock(_po.standards || []);
  }
  if (_poPane === 'changes') html += _poDriftBlock(_po.drift || {});
  html += '<button type="button" class="btn btn-sm mt-3" data-click-handler="poReload">' + esc(t('pl_reload')) + '</button>';
  el.innerHTML = html;
  _poResults();
}

function _poOverview() {
  var selectedIds = _po.plan.package_id ? _po.plan.policy_ids : Array.from(_poDraft);
  var selected = _po.catalog.policies.filter(function(p) { return selectedIds.indexOf(p.id) !== -1; });
  var html = '<div class="card mb-4"><h3>' + esc(t('pl_workflow')) + '</h3><p>' + esc(t(_po.plan.package_id ? 'pl_next_review' : 'pl_next_package')) + '</p><div class="flex flex-wrap gap-2">';
  ['package', 'evidence', 'actions', 'pilot', 'verify'].forEach(function(step, index) {
    html += '<button type="button" class="btn btn-sm" data-click-handler="poGuide" data-step="' + step + '">' + (index + 1) + '. ' + esc(t('pl_step_' + step)) + '</button>';
  });
  html += '</div><p class="text-muted text-sm mt-3">' + esc(t('pl_workflow_note')) + '</p></div><div class="pl-stats">';
  ['aligned', 'needs_change', 'exception', 'not_assessed', 'stale'].forEach(function(status) {
    html += '<div class="card pl-stat"><strong>' + selected.filter(function(p) { return _poStatusOf(p) === status; }).length + '</strong><span>' + esc(t('pl_status_' + status)) + '</span></div>';
  });
  html += '</div><p class="text-muted text-sm">' + esc(t(_po.plan.package_id ? 'pl_status_note' : 'pl_status_proposal_note')) + '</p><div class="pl-areas">';
  _po.catalog.areas.forEach(function(area) {
    var policies = _po.catalog.policies.filter(function(p) { return p.area === area.id; });
    var confirmed = policies.filter(function(p) { return selected.indexOf(p) !== -1 && _poStatusOf(p) === 'aligned'; }).length;
    html += '<button type="button" class="card pl-area" data-click-handler="poArea" data-area="' + esc(area.id) + '"><strong>' + esc(_poLoc(area.name)) + '</strong><span>' + policies.length + ' ' + esc(t('pl_recommendations')) + '</span><span class="text-muted">' + confirmed + ' ' + esc(t('pl_confirmed')) + '</span></button>';
  });
  html += '</div><div class="card mt-4"><h3>' + esc(t('pl_rollout')) + '</h3><ol class="pl-stages">';
  [1, 2, 3].forEach(function(stage) { html += '<li><strong>' + esc(t('pl_stage_' + stage)) + '</strong><p>' + esc(t('pl_stage_desc_' + stage)) + '</p></li>'; });
  return html + '</ol></div>';
}
function _poPackages() {
  var html = '<div class="pl-packages">';
  _po.catalog.packages.forEach(function(p) {
    html += '<article class="card pl-package' + (p.id === _poPackage ? ' pl-active' : '') + '"><h3>' + esc(_poLoc(p.name)) + '</h3>'
      + (p.recommended ? '<span class="po-badge po-badge-trusted">' + esc(t('pl_recommended')) + '</span>' : '')
      + '<p>' + esc(_poLoc(p.description)) + '</p><p class="text-muted">' + esc(_poLoc(p.audience)) + '</p><p><strong>' + p.policy_ids.length + '</strong> ' + esc(t('pl_recommendations')) + '</p><div class="flex gap-1 flex-wrap">';
    _po.catalog.areas.filter(function(a) { return _po.catalog.policies.some(function(pol) { return pol.area === a.id && p.policy_ids.indexOf(pol.id) !== -1; }); }).forEach(function(a) { html += '<span class="po-badge">' + esc(_poLoc(a.name)) + '</span>'; });
    html += '</div><button type="button" class="btn mt-4" data-click-handler="poPackage" data-package="' + esc(p.id) + '"' + (_poBusy ? ' disabled' : '') + '>' + esc(t('pl_use_package')) + '</button></article>';
  });
  return html + '</div><p class="text-muted mt-4">' + esc(t('pl_package_note')) + '</p>';
}
function _poOptions(values, current) {
  return values.map(function(v) { return '<option value="' + esc(v[0]) + '"' + (v[0] === current ? ' selected' : '') + '>' + esc(v[1]) + '</option>'; }).join('');
}
function _poLibrary() {
  var html = '<div class="pl-filters"><label>' + esc(t('pl_search')) + '<input id="po-search" class="field-input" type="search" value="' + esc(_poQuery) + '" data-input-handler="poFilter"></label>';
  html += '<label>' + esc(t('pl_area')) + '<select id="po-area" class="field-input" data-change-handler="poFilter">' + _poOptions([['', t('pl_all_areas')]].concat(_po.catalog.areas.map(function(a) { return [a.id, _poLoc(a.name)]; })), _poArea) + '</select></label>';
  html += '<label>' + esc(t('pl_tier')) + '<select id="po-tier" class="field-input" data-change-handler="poFilter">' + _poOptions([['', t('pl_all')]].concat(['essential', 'recommended', 'extended'].map(function(k) { return [k, t('pl_tier_' + k)]; })), _poTier) + '</select></label>';
  html += '<label>' + esc(t('pl_status')) + '<select id="po-status" class="field-input" data-change-handler="poFilter">' + _poOptions([['', t('pl_all')], ['selected', t('pl_in_plan')], ['actionable', t('pl_actionable')]].concat(['not_assessed', 'aligned', 'needs_change', 'exception', 'stale'].map(function(k) { return [k, t('pl_status_' + k)]; })), _poStatus) + '</select></label></div>';
  return html + '<p class="text-muted text-sm">' + esc(t('pl_dependencies_note')) + '</p><div id="po-results" aria-live="polite"></div>';
}
function _poResults() {
  _poCapture();
  var el = document.getElementById('po-results');
  if (!el || !_po) return;
  var query = _poQuery.toLocaleLowerCase();
  var policies = _po.catalog.policies.filter(function(p) {
    return (!_poArea || p.area === _poArea) && (!_poTier || p.tier === _poTier)
      && (!_poStatus || (_poStatus === 'selected' ? _poDraft.has(p.id) : (_poStatus === 'actionable' ? _poDraft.has(p.id) && ['not_assessed', 'needs_change', 'stale'].indexOf(_poStatusOf(p)) !== -1 : _poStatusOf(p) === _poStatus)))
      && (!query || [_poLoc(p.name), _poLoc(p.desired), _poLoc(p.license), p.id].join(' ').toLocaleLowerCase().indexOf(query) !== -1);
  }).sort(function(a, b) { return a.stage - b.stage || a.area.localeCompare(b.area); });
  var html = '<p class="text-muted">' + policies.length + ' ' + esc(t('pl_recommendations')) + '</p>';
  policies.forEach(function(p) {
    var area = _po.catalog.areas.find(function(a) { return a.id === p.area; });
    var review = _po.plan.reviews[p.id];
    var draft = _poReviews[p.id] || _poReviewFields(review);
    html += '<article class="card pl-policy" data-policy-id="' + esc(p.id) + '"><div class="pl-policy-head"><div><span class="pl-eyebrow">' + esc(_poLoc(area.name)) + ' · ' + esc(t('pl_tier_' + p.tier)) + ' · ' + esc(t('pl_stage_' + p.stage)) + '</span><h3>' + esc(_poLoc(p.name)) + '</h3></div><span class="po-badge">' + esc(t('pl_status_' + _poStatusOf(p))) + '</span></div><p>' + esc(_poLoc(p.desired)) + '</p>';
    var check = (_po.captured_checks || {})[p.id];
    html += '<div class="pl-captured-check text-sm"><strong>' + esc(t('pl_captured_settings')) + ': </strong>' + esc(t('pl_check_' + (check ? check.state : 'unsupported')))
      + (check && check.matches.length ? '<ul>' + check.matches.map(function(match) { return '<li>' + esc(match.name) + ' · ' + esc(match.state) + '</li>'; }).join('') + '</ul>' : '')
      + '<p class="text-muted">' + esc(t('pl_check_review')) + '</p></div>';
    if (_poCanEdit()) html += '<label class="pl-select"><input type="checkbox" data-change-handler="poSelect" data-policy="' + esc(p.id) + '"' + (_poDraft.has(p.id) ? ' checked' : '') + (_poBusy ? ' disabled' : '') + '> ' + esc(t('pl_in_plan')) + '</label>';
    html += '<details' + (_poOpen.has(p.id) ? ' open' : '') + '><summary>' + esc(t('pl_details')) + '</summary><div class="pl-detail-grid"><section><h4>' + esc(t('pl_settings')) + '</h4><ul>';
    p.settings.forEach(function(s) { html += '<li>' + esc(_poLoc(s)) + '</li>'; });
    html += '</ul></section><section><h4>' + esc(t('pl_license')) + '</h4><p>' + esc(_poLoc(p.license)) + '</p><h4>' + esc(t('pl_dependencies')) + '</h4><p>'
      + (p.dependencies.length ? p.dependencies.map(function(id) { return esc(_poLoc(_po.catalog.policies.find(function(x) { return x.id === id; }).name)); }).join(', ') : esc(t('pl_none')))
      + '</p></section>';
    ['why', 'impact', 'verify', 'rollback'].forEach(function(key) { html += '<section><h4>' + esc(t('pl_' + key)) + '</h4><p>' + esc(_poLoc(p[key])) + '</p></section>'; });
    html += '</div><div class="pl-sources"><a href="' + esc(area.portal) + '" target="_blank" rel="noopener noreferrer">' + esc(t('pl_portal')) + '</a>';
    p.sources.forEach(function(s) { html += '<a href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer">' + esc(s.title) + '</a>'; });
    html += '<span class="text-muted">' + esc(t('pl_reviewed')) + ': ' + esc(p.reviewed_on) + '</span></div>';
    if (review) html += '<div class="pl-evidence"><strong>' + esc(t('pl_evidence')) + '</strong><p>' + esc(review.note) + '</p><p class="text-muted">' + esc(review.reviewed_by) + ' · ' + esc(review.reviewed_at.slice(0, 10)) + (review.review_due ? ' · ' + esc(t('pl_due')) + ': ' + esc(review.review_due) : '') + '</p></div>';
    if (_poCanEdit()) {
      html += '<form class="pl-review" data-input-handler="poDraftEdited" data-change-handler="poDraftEdited" data-submit-handler="poReview" data-policy="' + esc(p.id) + '"><h4>' + esc(t('pl_assess')) + '</h4><label>' + esc(t('pl_status')) + '<select name="status" class="field-input">'
        + _poOptions(['not_assessed', 'aligned', 'needs_change', 'exception'].map(function(s) { return [s, t('pl_status_' + s)]; }), draft.status)
        + '</select></label><label>' + esc(t('pl_evidence_hint')) + '<textarea name="note" class="field-input" maxlength="2000" rows="3">' + esc(draft.note) + '</textarea></label><label>' + esc(t('pl_due_hint')) + '<input name="review_due" type="date" class="field-input" value="' + esc(draft.review_due) + '"></label><button class="btn btn-primary" type="submit"' + (_poBusy ? ' disabled' : '') + '>' + esc(t('pl_save_review')) + '</button></form>';
    }
    html += '</details></article>';
  });
  if (!policies.length) html += '<div class="card">' + esc(t('pl_no_results')) + '</div>';
  el.innerHTML = html;
}
async function _poSavePlan() {
  if (_poBusy || !_poCanEdit()) return;
  var cid = _poCid;
  _poBusy = true;
  var plan;
  try {
    plan = await apiFetch('/api/policy-overview/' + encodeURIComponent(cid) + '/plan', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({package_id: _poPackage, policy_ids: Array.from(_poDraft), expected_revision: _po.plan.revision})});
  } finally { _poBusy = false; }
  if (cid !== _poCustomerId() || cid !== _poCid) return;
  if (plan) { _po.plan = plan; _poDraft = new Set(plan.policy_ids); _poBase = _poPlanKey(); showToast(t('pl_plan_saved'), 'success'); _poRender(); }
}
async function _poSaveReview(form) {
  if (_poBusy || !_poCanEdit()) return;
  var cid = _poCid;
  var fields = new FormData(form);
  _poBusy = true;
  var button = form.querySelector('button');
  button.disabled = true;
  var plan;
  try {
    plan = await apiFetch('/api/policy-overview/' + encodeURIComponent(cid) + '/reviews/' + encodeURIComponent(form.dataset.policy), {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({status: fields.get('status'), note: fields.get('note'), review_due: fields.get('review_due') || null, expected_revision: _po.plan.revision})});
  } finally { _poBusy = false; button.disabled = false; }
  if (cid !== _poCustomerId() || cid !== _poCid) return;
  if (plan) {
    var id = form.dataset.policy;
    var submitted = {status: fields.get('status'), note: fields.get('note'), review_due: fields.get('review_due') || ''};
    var card = document.querySelector('#po-results article[data-policy-id="' + id + '"]');
    var currentForm = card && card.querySelector('form');
    var current = currentForm && new FormData(currentForm);
    var unchanged = current ? ['status', 'note', 'review_due'].every(function(key) { return (current.get(key) || '') === submitted[key]; })
      : JSON.stringify(_poReviews[id] || submitted) === JSON.stringify(submitted);
    _po.plan = plan;
    if (unchanged) {
      delete _poReviews[id];
      if (currentForm) {
        var canonical = _poReviewFields(plan.reviews[id]);
        Object.keys(canonical).forEach(function(key) { currentForm.elements.namedItem(key).value = canonical[key]; });
      }
    }
    _poDirtyNotice(); showToast(t('pl_review_saved'), 'success');
    if (!card) return;
    form = currentForm;
    card.querySelector('.pl-policy-head .po-badge').textContent = t('pl_status_' + _poStatusOf({id: form.dataset.policy}));
    // Keep the open form and its evidence visible after saving.
    var evidence = card.querySelector('.pl-evidence');
    if (evidence) evidence.remove();
    var review = plan.reviews[form.dataset.policy];
    if (review) {
      var div = document.createElement('div'); div.className = 'pl-evidence';
      div.textContent = t('pl_evidence') + ': ' + review.note + ' · ' + review.reviewed_at.slice(0, 10);
      form.before(div);
    }
  }
}

function _poStateLabel(code) {
  return {
    'on':          t('lbl_policy_on', 'On'),
    'report-only': t('lbl_policy_report', 'Report-only'),
    'off':         t('lbl_policy_off', 'Off'),
    'trusted':     t('lbl_policy_trusted', 'Trusted'),
  }[code] || String(code || '?');
}

function _poStatePill(code) {
  var cls = {
    'on':          'po-badge-on',
    'report-only': 'po-badge-report',
    'off':         'po-badge-off',
    'trusted':     'po-badge-trusted',
  }[code] || 'po-badge-unknown';
  return '<span class="po-badge ' + cls + '">' + esc(_poStateLabel(code)) + '</span>';
}

function _poHintClass(code) {
  if (code === 'add_break_glass') return 'po-hint po-hint-danger';
  if (code === 'enforce')         return 'po-hint po-hint-warn';
  return 'po-hint po-hint-info';
}

function _poWorkloadBlocks(workloads) {
  var html = '<div class="card po-block">';
  html += '<div class="po-sec">' + t('hdr_policies_live', 'Policies in production') + '</div>';

  var keys = Object.keys(workloads || {});
  if (!keys.length) {
    html += '<div class="po-dim">' + esc(t('msg_po_no_policies', 'No policies captured on this customer yet.')) + '</div></div>';
    return html;
  }

  keys.forEach(function(k) {
    var wl = workloads[k] || {};
    html += '<div class="po-block">';
    html += '<div class="po-sub">'
      + esc(_poLoc(wl.label))
      + ' <span class="po-sub-count">' + (Number(wl.count) || 0) + '</span>'
      + '</div>';
    html += '<table class="po-tbl">';
    (wl.items || []).forEach(function(it) {
      html += '<tr class="po-row">';
      html += '<td class="po-statecell">' + _poStatePill(it.state) + '</td>';
      html += '<td class="po-namecell">' + esc(it.name || '');
      var hints = (it.improvements || []);
      if (hints.length) {
        html += '<div class="po-hints">';
        hints.forEach(function(h) {
          html += '<span class="' + _poHintClass(h.code) + '">'
                + esc(_poLoc(h.text) || h.code) + '</span>';
        });
        html += '</div>';
      }
      html += '</td>';
      html += '<td class="po-cell">' + esc(_poLoc(it.summary)) + '</td>';
      html += '</tr>';
    });
    html += '</table></div>';
  });
  html += '</div>';
  return html;
}

function _poReason(prefix, code, params) {
  if (!code) return '';
  var out = t(prefix + code, '');
  if (!out) return '';
  Object.keys(params || {}).forEach(function(k) {
    var v = k === 'run' ? formatRunName(params[k]) : params[k];
    out = out.split('{' + k + '}').join(String(v || ''));
  });
  return out;
}

function _poDriftBlock(d) {
  var html = '<div class="card po-block">';
  html += '<div class="po-sec">' + t('hdr_drift', 'Drift since last audit') + '</div>';

  if (!d.measured) {
    html += '<div class="po-dim po-xs">'
      + esc(_poReason('drift_', d.reason_code, d.reason_params)
             || t('msg_po_drift_unmeasured', 'No comparison available for this customer yet.'))
      + '</div></div>';
    return html;
  }

  html += '<div class="po-meta">'
    + t('lbl_drift_against', 'Against run') + ': ' + esc(d.compared_with ? formatRunName(d.compared_with) : '-')
    + ' &middot; '
    + '<span class="po-dr-count-add">' + (Number(d.added_total) || 0) + ' ' + t('lbl_added', 'added') + '</span>'
    + ' / '
    + '<span class="po-dr-count-rem">' + (Number(d.removed_total) || 0) + ' ' + t('lbl_removed', 'removed') + '</span>'
    + ' / '
    + '<span class="po-dr-count-chg">' + (Number(d.changed_total) || 0) + ' ' + t('lbl_changed', 'changed') + '</span>'
    + ' &middot; '
    + Number((d.snapshots || []).reduce(function(acc, s) { return acc + (s.unchanged || 0); }, 0))
    + ' ' + t('lbl_unchanged', 'unchanged')
    + '</div>';

  (d.snapshots || []).forEach(function(s) {
    var labelEsc = esc(s.name);
    if (s.comparable) {
      if ((s.added && s.added.length) || (s.removed && s.removed.length) || (s.changed && s.changed.length)) {
        html += '<div class="po-sep">';
        html += '<div class="po-sep-title">' + labelEsc + '</div>';
        html += '<div class="flex flex-col gap-1 mt-2">';
        html += _poDriftList('add', s.added || []);
        html += _poDriftList('rem', s.removed || []);
        html += _poDriftList('chg', s.changed || [], true);
        html += '</div></div>';
      } else {
        html += '<div class="po-sep-muted"><span class="po-sep-title inline-flex items-center mt-0 mb-0 mr-2 text-default">' + labelEsc + '</span> · ' + t('lbl_unchanged', 'unchanged') + '</div>';
      }
    } else {
      html += '<div class="po-sep-muted">'
        + '<span class="po-sep-title inline-flex items-center mt-0 mb-0 mr-2 text-default">' + labelEsc + '</span> · '
        + esc(_poReason('drift_', s.reason_code, s.reason_params)
               || t('msg_po_snap_unmeasured', 'not comparable against the previous run'))
        + '</div>';
    }
  });
  html += '</div>';
  return html;
}

function _poDriftList(type, items, withFields) {
  if (!items.length) return '';
  var icon = type === 'add' ? '+' : type === 'rem' ? '−' : '~';
  var label = type === 'add' ? t('lbl_added', 'Added') : type === 'rem' ? t('lbl_removed', 'Removed') : t('lbl_changed', 'Changed');
  var cls = type === 'add' ? 'po-dr-add' : type === 'rem' ? 'po-dr-rem' : 'po-dr-chg';
  
  var html = '';
  items.forEach(function(p) {
    html += '<div class="po-dr-row">'
      + '<span class="po-dr-icon ' + cls + '" aria-label="' + esc(label)
      + '" title="' + esc(label) + '">' + icon + '</span>';
    html += '<span class="po-dr-name">' + esc(p.name || p.id || '') + '</span>';
    if (withFields && p.fields && p.fields.length) {
      html += '<span class="po-fields">(' + p.fields.map(function(f) { return esc(f); }).join(', ') + ')</span>';
    }
    html += '</div>';
  });
  return html;
}

// Presence is only known when the run captured the tenant's policies. The
// server says so per standard (`measured`) and per policy (`present` null).
// Unknown is shown as unknown, in a neutral colour: fourteen red "Ikke til
// stede" on a customer nobody had captured read as fourteen failures.
function _poStandardBlock(standards) {
  if (!standards.length) return '';
  var html = '<div class="card" id="po-standards">';
  html += '<div class="po-sec">' + t('hdr_std_gap', 'Avstand til Sybr-standarden') + '</div>';

  html += '<p class="text-muted text-sm">' + esc(t('pl_name_note')) + '</p>';
  if (standards.some(function(std) { return std.measured === false; })) {
    html += '<div class="po-dim po-xs po-std-note">'
      + esc(t('msg_po_std_unknown', 'Kundens policyer er ikke samlet inn ennå, så det er ukjent hvilke av standardens policyer som finnes. En audit samler dem inn.'))
      + '</div>';
  }

  standards.forEach(function(std) {
    var measured = std.measured !== false;
    var total = (std.policies || []).length;
    var present = (std.policies || []).filter(function(p) { return p.present === true; }).length;
    var pct = total > 0 ? Math.round((present / total) * 100) : 0;
    var pcls = pct === 100 ? ' success' : '';

    html += '<div class="po-block">';
    html += '<div class="po-std-head">'
      + '<span>' + esc(std.name || std.id) + ' <span class="po-std-meta">v' + esc(std.version || '') + '</span></span>'
      + '<span class="po-std-meta fw-semibold">'
      + (measured
        ? present + '/' + total + ' ' + t('pl_name_matched', 'name matched') + ' (' + pct + '%)'
        : esc(t('lbl_std_unmeasured', 'ikke målt')))
      + '</span>'
      + '</div>';
    if (measured) {
      html += '<div class="po-progress-wrap mb-4"><div class="po-progress-fill' + pcls + '" data-bar="' + pct + '"></div></div>';
    }

    html += '<table class="po-tbl">';
    (std.policies || []).forEach(function(p) {
      var mark, status, statusCls = '';
      if (p.present === true) {
        mark = _poStatePill(p.state || 'on');
        status = esc(_poStateLabel(p.state || 'on'));
      } else if (p.present === false) {
        mark = '<span class="po-absent">&#10007;</span>';
        status = esc(t('lbl_std_missing', 'Ikke til stede'));
        statusCls = ' po-std-statuscell-missing';
      } else {
        mark = '<span class="po-unknown">?</span>';
        status = esc(t('lbl_std_unknown', 'Ukjent, ikke samlet inn'));
        statusCls = ' po-std-statuscell-unknown';
      }
      html += '<tr class="po-row">';
      html += '<td class="po-std-statecell">' + mark + '</td>';
      html += '<td class="po-std-name">' + esc(p.name);
      if (p.why) html += '<div class="po-std-why">' + esc(p.why) + '</div>';
      html += '</td>';
      html += '<td class="po-std-statuscell' + statusCls + '">' + status + '</td></tr>';
    });
    html += '</table></div>';
  });
  html += '</div>';
  return html;
}
