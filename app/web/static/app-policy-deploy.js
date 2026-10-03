// ═══════════════════════════════════════════════════════════════════
// POLICY DEPLOYMENT — the only screen in this application that changes
// something inside a customer's Microsoft tenant.
// ═══════════════════════════════════════════════════════════════════
//
// Two steps, deliberately, and the first one is the point: a plan is read
// before anything is sent. The engine behind this refuses to apply a plan whose
// tenant has moved since, so the fingerprint travels with the confirmation
// rather than being recomputed at the moment of the click — recomputing it
// would confirm whatever the tenant looks like now, which is precisely the
// state nobody reviewed.
//
// The screen shows what the API returns and adds nothing: refusals with their
// reason, the rationale for each policy, and the consent state. A plan
// rendered as "3 changes" is not something a person can consent to.

import {esc} from './app-esc.js';
import {_lang, t} from './app-i18n.js';
import {registerUiHandlers} from './app-handlers.js';
import {_custPage, canTenantWrite} from './app-state.js';
import {toneClass} from './app-format.js';
import {showToast, showTypedConfirm} from './app-ui.js';
import {apiFetch} from './app-api.js';

// Handlers for the controls this screen renders (see registerUiHandlers in
// app-handlers.js). The tenant-changing ones carry data-write="tenant" in the markup.
registerUiHandlers({
  _pdLoadPolicies: function() { _pdLoadPolicies(); },
  _pdValidate: function() { _pdValidate(); },
  policyAdoptionLoad: function() { policyAdoptionLoad(); },
  policyDeployPlan: function() { policyDeployPlan(); },
  policyAdoptionSave: function() { policyAdoptionSave(); },
  policyEnforce: function(el) { policyEnforce(el.dataset.policyId, el.dataset.name); },
  policyRestorePlan: function() { policyRestorePlan(); },
  policyRestoreApply: function() { policyRestoreApply(); },
  policyConsentStart: function() { policyConsentStart(); },
  policyDeployApply: function() { policyDeployApply(); },
});

var _pdPlan = null;
var _pdTemplates = [];

export async function policyDeployLoad() {
  var el = document.getElementById('policy-deploy-content');
  if (!el) return;
  el.innerHTML = '<div class="loader loader-lg mx-auto my-8"></div>';

  var d = await apiFetch('/api/policy-deploy/templates?lang=' + _lang);
  if (!d || !d.templates) { el.innerHTML = '<div class="alert alert-error">' + t('status_error') + '</div>'; return; }
  _pdTemplates = d.templates;
  _pdPlan = null;
  el.innerHTML = _pdForm();
  _pdLoadPolicies();
  // Without the tenant-write grant this screen can be read but not used, and
  // its report-only and restore lists are behind the same grant: asking for
  // them only produced two identical red 403 toasts. The form says why its
  // buttons are off instead.
  if (!canTenantWrite()) return;
  policyEnforceLoad();
  policyRestoreLoad();
}

// The policies in the selected standard, each a checkbox so the operator picks
// which to deploy. A one-policy standard shows nothing here — there is nothing
// to choose. Tier and licence badges say what each is and whether it needs P2.
async function _pdLoadPolicies() {
  var box = document.getElementById('pd-select');
  var descEl = document.getElementById('pd-desc');
  var tid = document.getElementById('pd-template');
  if (!box || !tid) return;
  box.innerHTML = '';
  // The baseline's own description — from the templates list already loaded.
  if (descEl) {
    var meta = (_pdTemplates || []).filter(function(x) { return x.id === tid.value; })[0];
    descEl.innerHTML = (meta && meta.description)
      ? '<div class="text-xs text-dim mt-0 mb-4 lh-normal">' + esc(meta.description) + '</div>'
      : '';
  }
  var d = await apiFetch('/api/policy-deploy/template/' + encodeURIComponent(tid.value) + '?lang=' + _lang).catch(function(){ return null; });
  if (!d || !d.policies || d.policies.length <= 1) return;
  var tierLabel = { essential: t('lbl_tier_essential', 'Essential'), recommended: t('lbl_tier_recommended', 'Recommended'), extended: t('lbl_tier_extended', 'Extended') };
  var html = '<div class="text-xs text-muted mb-2">' + t('lbl_pick_policies', 'Choose which policies to deploy') + '</div>';
  d.policies.forEach(function(p) {
    var badges = '';
    if (p.tier) badges += '<span class="po-badge bg-input text-dim">' + esc(tierLabel[p.tier] || p.tier) + '</span>';
    if (p.requires_license) badges += '<span class="po-badge po-badge-report">' + esc(p.requires_license.toUpperCase().replace('ENTRA_', '')) + '</span>';
    html += '<label class="pd-pol-card">';
    html += '<input type="checkbox" class="pd-pol" value="' + esc(p.name) + '" checked>';
    html += '<span class="pd-pol-card-body"><span class="pd-pol-title">' + esc(p.name) + '</span><span class="pd-pol-badges">' + badges + '</span>';
    // effect = what the policy does and who it hits; why = why it matters.
    if (p.effect) html += '<span class="pd-pol-effect">' + esc(p.effect) + '</span>';
    if (p.why) html += '<span class="pd-pol-why">' + esc(p.why) + '</span>';
    html += '</span></label>';
  });
  box.innerHTML = html;
}

function _pdSelectedPolicies() {
  return Array.prototype.slice.call(document.querySelectorAll('#pd-select .pd-pol:checked')).map(function(c) { return c.value; });
}

function _pdForm() {
  var cust = _pdCustomerName() || t('msg_no_customer_selected', 'No customer selected');
  var html = '<div class="card p-5 mb-4">';
  html += '<div class="text-sm text-muted mb-4">'
       + t('lbl_customer', 'Customer') + ': <strong>' + esc(cust) + '</strong></div>';

  html += '<label class="field-label">'
       + t('lbl_standard', 'Standard') + '</label>';
  html += '<select id="pd-template" data-change-handler="_pdLoadPolicies" class="inset w-full mb-4 text-default">';
  _pdTemplates.forEach(function(tpl) {
    html += '<option value="' + esc(tpl.id) + '">' + esc(tpl.name) + ' ' + esc(tpl.version)
         + ' · ' + Number(tpl.policies) + ' ' + t('lbl_policies', 'policies') + '</option>';
  });
  html += '</select>';

  // The selected baseline's description, then its policies. Filled by
  // _pdLoadPolicies(). A one-policy standard shows a description but no list —
  // there is nothing to pick.
  html += '<div id="pd-desc"></div>';
  html += '<div id="pd-select" class="mb-4"></div>';

  // Required, never defaulted. An unfilled exclusion excludes nobody, inside a
  // policy that applies to everybody — so the field is empty and the button
  // stays disabled until it is not.
  html += '<label class="field-label">'
       + t('lbl_break_glass', 'Break-glass group (object ID)') + '</label>';
  html += '<input id="pd-breakglass" data-input-handler="_pdValidate" placeholder="00000000-0000-0000-0000-000000000000" '
       + 'class="inset w-full font-mono text-default">';
  html += '<div class="text-xs text-dim mt-2 mb-4">'
       + t('msg_break_glass_help', 'Every policy in the standard excludes this group. It must hold at least one account that can never be locked out.') + '</div>';

  html += '<button class="btn btn-ghost mr-2" id="pd-adopt-btn" disabled data-click-handler="policyAdoptionLoad">'
       + t('btn_check_existing', 'Check existing policies') + '</button>';
  html += '<button class="btn btn-primary" id="pd-plan-btn" disabled data-click-handler="policyDeployPlan">'
       + t('btn_plan', 'Show plan') + '</button>';
  if (!canTenantWrite()) {
    html += '<p class="pd-no-grant" id="pd-no-grant">' + esc(t('msg_pd_needs_tenant_write', 'Kontoen din kan ikke endre kundens tenant, så knappene er av. En administrator gir tilgangen under Administrasjon › Brukere (Tenant).')) + '</p>';
  }
  html += '</div><div id="pd-adopt"></div><div id="pd-plan"></div>'
       + '<div id="pd-enforce"></div><div id="pd-restore"></div>';
  return html;
}

// ── Asking for the permission ───────────────────────────────────────────────
// Sybr HUB cannot grant itself a write permission — it holds nothing that can
// widen its own access, which is what keeps a compromised toolkit from becoming
// a way into every customer's tenant. So a Global Admin signs in here, and the
// grant happens under their authority rather than the application's.

async function policyConsentStart() {
  var box = document.getElementById('pd-consent');
  if (!box) return;
  box.innerHTML = '<div class="loader loader-md my-3"></div>';

  var d = await apiFetch('/api/policy-deploy/' + encodeURIComponent(_pdCustomerId()) + '/consent/start', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}',
  });
  if (!d || !d.user_code) { box.innerHTML = ''; return; }

  var html = '<div class="inset mt-3">';
  html += '<div class="text-xs text-muted mb-2">'
       + t('msg_consent_step1', 'Open this page and sign in as a Global Admin of the customer tenant:') + '</div>';
  html += '<div><a href="' + esc(d.verification_uri) + '" target="_blank" rel="noopener noreferrer" class="text-accent">'
       + esc(d.verification_uri) + '</a></div>';
  html += '<div class="text-xs text-muted mt-3 mb-1">'
       + t('msg_consent_step2', 'Enter this code:') + '</div>';
  html += '<div class="code-display">'
       + esc(d.user_code) + '</div>';
  html += '<div id="pd-consent-status" class="text-xs text-dim mt-3">'
       + t('msg_consent_waiting', 'Waiting for the sign-in to complete...') + '</div>';
  html += '</div>';
  box.innerHTML = html;

  // The server blocks on the device-code poll, so this single request is the
  // wait — no polling loop of our own to get wrong.
  var r = await apiFetch('/api/policy-deploy/' + encodeURIComponent(_pdCustomerId()) + '/consent/complete', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}',
  });
  var status = document.getElementById('pd-consent-status');
  if (!r) { if (status) status.textContent = t('msg_consent_failed', 'The sign-in did not complete.'); return; }

  if (status) {
    status.style.color = 'var(--green)';
    status.textContent = r.already_complete
      ? t('msg_consent_already', 'The permission was already granted.')
      : t('msg_consent_done', 'Permission granted. Re-run the plan.');
  }
  showToast(t('msg_consent_done', 'Permission granted. Re-run the plan.'), 'success', 5000);
}

// ── Adopting what the customer already has ──────────────────────────────────
// The suggestions are a shortlist. Nothing here reaches a plan until the
// operator ticks a box and saves, because a policy overwritten by a fuzzy
// match is a production incident with a plausible-sounding cause.

function _pdValues() {
  return { break_glass_group: document.getElementById('pd-breakglass').value.trim() };
}

async function policyAdoptionLoad() {
  var el = document.getElementById('pd-adopt');
  el.innerHTML = '<div class="loader loader-md mx-auto my-4"></div>';

  var body = { template: document.getElementById('pd-template').value, values: _pdValues() };
  var d = await apiFetch('/api/policy-deploy/' + encodeURIComponent(_pdCustomerId()) + '/adoption/suggest', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (!d) { el.innerHTML = ''; return; }

  var confirmed = {};
  (d.confirmed || []).forEach(function(c) { confirmed[c.template] = c.policy_id; });

  var html = '<div class="card p-5 mt-4">';
  html += '<div class="card-title mb-2">'
       + t('hdr_adoption', 'Existing policies') + '</div>';
  html += '<div class="text-xs text-dim mb-3">'
       + t('msg_adoption_intro', 'The tenant may already have a policy doing the same job under another name. Choosing it means the standard takes it over and renames it, instead of adding a second one beside it. Suggestions are matched on what a policy does, never on its wording — nothing is adopted until you save.')
       + '</div>';

  var any = false;
  Object.keys(d.suggestions || {}).forEach(function(name) {
    var candidates = d.suggestions[name] || [];
    html += '<div class="py-3 px-0 border-b">';
    html += '<div class="fw-semibold text-xs">' + esc(name) + '</div>';
    if (!candidates.length && !confirmed[name]) {
      html += '<div class="text-xs text-dim mt-0-5">'
           + t('msg_no_candidate', 'Nothing in the tenant resembles this. It will be created.') + '</div>';
    } else {
      any = true;
      html += '<select data-adopt="' + esc(name) + '" class="w-full mt-2 p-2 text-xs bg-base border rounded-sm text-default">';
      html += '<option value="">' + t('opt_create_new', 'Create a new policy') + '</option>';
      candidates.forEach(function(c) {
        var sel = confirmed[name] === c.policy_id ? ' selected' : '';
        html += '<option value="' + esc(c.policy_id) + '"' + sel + '>'
             + esc(c.display_name) + ' [' + esc(c.state) + '] · ' + esc(c.reasons.join('; ')) + '</option>';
      });
      html += '</select>';
    }
    html += '</div>';
  });

  html += '<button class="btn btn-primary mt-3" data-write="tenant" data-click-handler="policyAdoptionSave">'
       + t('btn_save_adoption', 'Save choices') + '</button>';
  if (!any) {
    html += '<div class="text-xs text-dim mt-2">'
         + t('msg_nothing_to_adopt', 'Nothing to take over — every policy in the standard will be created.') + '</div>';
  }
  html += '</div>';
  el.innerHTML = html;
}

async function policyAdoptionSave() {
  var mapping = {};
  document.querySelectorAll('[data-adopt]').forEach(function(sel) {
    if (sel.value) mapping[sel.getAttribute('data-adopt')] = sel.value;
  });

  var d = await apiFetch('/api/policy-deploy/' + encodeURIComponent(_pdCustomerId()) + '/adoption', {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      template: document.getElementById('pd-template').value,
      values: _pdValues(),
      mapping: mapping,
    }),
  });
  if (!d || !d.ok) return;
  showToast(t('msg_adoption_saved', 'Choices saved'), 'success', 3000);
  // The plan is stale the moment the mapping changes, so it goes.
  var plan = document.getElementById('pd-plan');
  if (plan) plan.innerHTML = '';
  _pdPlan = null;
}

// ── Turning report-only into enforced ───────────────────────────────────────
// The step that was missing. A policy lands report-only so somebody can read
// what it would have blocked; acting on that reading used to mean the Entra
// portal — half the lifecycle living elsewhere, and the half where a policy
// starts turning sign-ins away.

async function policyEnforceLoad() {
  var el = document.getElementById('pd-enforce');
  if (!el) return;
  // Both of these build a customer-scoped URL. With no customer the id is an
  // empty string, so the path collapses to /api/policy-deploy//report-only —
  // an empty segment matches no route, and the 404 surfaced as a bare "Not
  // Found" toast on a screen that had not been asked to do anything yet.
  if (!_pdCustomerId()) { el.innerHTML = ''; return; }
  var d = await apiFetch('/api/policy-deploy/' + encodeURIComponent(_pdCustomerId()) + '/report-only');
  if (!d || !d.policies || !d.policies.length) { el.innerHTML = ''; return; }

  var html = '<div class="card p-5 mt-4">';
  html += '<div class="card-title mb-2">'
       + t('hdr_enforce', 'Report-only policies') + '</div>';
  html += '<div class="text-xs text-dim mb-3">'
       + t('msg_enforce_intro', 'These are live but block nobody. Read the sign-in logs in Entra to see who they would have stopped, then enforce.') + '</div>';
  html += '<table class="data-table data-table--compact">';
  d.policies.forEach(function(p) {
    html += '<tr class="align-top">';
    html += '<td class="py-2 px-0">' + esc(p.name);
    if (p.refused) {
      html += '<div class="text-danger mt-0-5">' + esc(p.refused) + '</div>';
    }
    html += '</td><td class="py-2 px-0 text-right nowrap">';
    if (p.refused) {
      html += '<span class="text-dim">' + t('lbl_cannot_enforce', 'Cannot enforce') + '</span>';
    } else {
      html += '<button class="btn btn-ghost btn-sm" data-write="tenant" data-click-handler="policyEnforce" data-policy-id="' + esc(p.policy_id) + '" data-name="' + esc(p.name) + '">'
           + t('btn_enforce', 'Enforce') + '</button>';
    }
    html += '</td></tr>';
  });
  html += '</table></div>';
  el.innerHTML = html;
}

async function policyEnforce(policyId, name) {
  var ok = await showTypedConfirm(
    name,
    t('dlg_confirm_enforce', 'Start enforcing «{name}»?').replace('{name}', name),
    t('dlg_enforce_warning', 'From this moment the policy turns sign-ins away. A restore point is taken first.')
  );
  if (!ok) return;
  var d = await apiFetch('/api/policy-deploy/' + encodeURIComponent(_pdCustomerId()) + '/enable', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({policy_id: policyId}),
  });
  if (!d || !d.ok) return;
  showToast(t('msg_enforced', 'Policy is now enforced'), 'success', 4000);
  policyEnforceLoad();
}

// ── Putting it back ─────────────────────────────────────────────────────────
// The same two steps. A rollback that skipped the plan would be the one path
// where somebody writes into production without reading what changes — which
// is exactly the moment they are most rushed.

async function policyRestoreLoad() {
  var el = document.getElementById('pd-restore');
  if (!el) return;
  // Both of these build a customer-scoped URL. With no customer the id is an
  // empty string, so the path collapses to /api/policy-deploy//report-only —
  // an empty segment matches no route, and the 404 surfaced as a bare "Not
  // Found" toast on a screen that had not been asked to do anything yet.
  if (!_pdCustomerId()) { el.innerHTML = ''; return; }
  var d = await apiFetch('/api/policy-restore/' + encodeURIComponent(_pdCustomerId()) + '/sources');
  if (!d || !d.sources || !d.sources.length) { el.innerHTML = ''; return; }

  var html = '<div class="card p-5 mt-4">';
  html += '<div class="card-title mb-2">'
       + t('hdr_restore', 'Restore') + '</div>';
  html += '<div class="text-xs text-dim mb-3">'
       + t('msg_restore_intro', 'Put the tenant back to a stored state. Restore points are taken immediately before a deployment; audit snapshots are older and coarser.') + '</div>';
  html += '<select id="pd-restore-source" class="inset w-full mb-3 text-default">';
  d.sources.forEach(function(s) {
    var kind = s.kind === 'deployment' ? t('lbl_before_deploy', 'before a deployment') : t('lbl_audit_run', 'audit run');
    html += '<option value="' + esc(s.kind) + '|' + esc(s.ref) + '">'
         + esc(s.captured_at) + ' · ' + kind + ' (' + Number(s.count) + ' ' + t('lbl_policies', 'policies') + ')</option>';
  });
  html += '</select>';
  html += '<button class="btn btn-ghost" data-click-handler="policyRestorePlan">' + t('btn_plan_restore', 'Show restore plan') + '</button>';
  html += '<div id="pd-restore-plan"></div></div>';
  el.innerHTML = html;
}

function _pdRestoreChoice() {
  var v = (document.getElementById('pd-restore-source') || {}).value || '';
  var parts = v.split('|');
  return { kind: parts[0], ref: parts.slice(1).join('|') };
}

async function policyRestorePlan() {
  var box = document.getElementById('pd-restore-plan');
  box.innerHTML = '<div class="loader loader-md mx-auto my-4"></div>';
  _pdPlan = null;

  var d = await apiFetch('/api/policy-restore/' + encodeURIComponent(_pdCustomerId()) + '/plan', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(_pdRestoreChoice()),
  });
  if (!d) { box.innerHTML = ''; return; }
  _pdRestore = d;
  box.innerHTML = _pdRenderRestorePlan(d);
}

var _pdRestore = null;

function _pdRenderRestorePlan(plan) {
  if (plan.missing_consent) {
    return '<div class="alert alert-error mt-3"><strong>'
      + t('hdr_missing_consent', 'Consent missing') + '.</strong> ' + t('msg_missing_consent', '') + '</div>';
  }
  if (!plan.changes.length) {
    return '<div class="mt-3 text-muted text-xs">'
      + t('msg_already_matches', 'The tenant already matches this stored state.') + '</div>';
  }
  var html = '<table class="data-table data-table--compact mt-3">';
  plan.changes.forEach(function(c) {
    var colour = c.refused ? 'var(--red)' : (c.action === 'delete' ? 'var(--orange)' : 'var(--green)');
    var label = c.refused ? t('lbl_refused', 'Refused') : t('lbl_action_' + c.action, c.action);
    html += '<tr class="align-top">'
      + '<td class="' + toneClass(colour) + ' fw-semibold nowrap">' + esc(label) + '</td>'
      + '<td>' + esc(c.name)
      + (c.refused ? '<div class="text-danger mt-0-5">' + esc(c.refused) + '</div>' : '')
      + '</td></tr>';
  });
  html += '</table>';
  html += '<button class="btn btn-primary mt-3" ' + (plan.applicable ? '' : 'disabled ')
       + 'data-write="tenant" data-click-handler="policyRestoreApply">' + t('btn_apply_restore', 'Restore {n} policy change(s)').replace('{n}', Number(plan.applicable)) + '</button>';
  return html;
}

async function policyRestoreApply() {
  if (!_pdRestore) return;
  var name = _pdCustomerName() || 'RESTORE';
  var ok = await showTypedConfirm(
    name,
    t('dlg_confirm_restore', 'Restore {n} policy change(s) on {customer}?')
      .replace('{n}', _pdRestore.applicable).replace('{customer}', name),
    t('dlg_restore_warning', 'This writes into the customer Microsoft tenant. A restore point of the current state is taken first.')
  );
  if (!ok) return;
  var d = await apiFetch('/api/policy-restore/' + encodeURIComponent(_pdCustomerId()) + '/apply', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      kind: _pdRestore.source.kind, ref: _pdRestore.source.ref,
      // The state that was reviewed, not the one that exists at this instant.
      fingerprint: _pdRestore.fingerprint,
    }),
  });
  if (!d) return;
  showToast(t('msg_restore_done', 'Restore finished'), 'success', 4000);
  policyDeployLoad();
}

// A GUID, checked here only to catch a paste that went wrong. The server and
// Graph are the authorities; this saves a round trip, it does not decide.
var _GUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function _pdValidate() {
  var v = (document.getElementById('pd-breakglass') || {}).value || '';
  // Without the grant the buttons stay off; the line under them says why.
  var ok = _GUID.test(v.trim()) && canTenantWrite();
  ['pd-plan-btn', 'pd-adopt-btn'].forEach(function(id) {
    var b = document.getElementById(id);
    if (b) b.disabled = !ok;
  });
}

async function policyDeployPlan() {
  var box = document.getElementById('pd-plan');
  box.innerHTML = '<div class="loader loader-md"></div>';
  _pdPlan = null;

  var selected = _pdSelectedPolicies();
  var body = {
    template: document.getElementById('pd-template').value,
    values: { break_glass_group: document.getElementById('pd-breakglass').value.trim() },
    select: selected,
  };
  var cid = _pdCustomerId();
  var d = await apiFetch('/api/policy-deploy/' + encodeURIComponent(cid) + '/plan?lang=' + _lang, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (_pdCustomerId() !== cid) return;   // another customer's page opened meanwhile
  if (!d) { box.innerHTML = ''; return; }
  d.select = selected;  // carried to apply so the approved plan is the one that runs
  d.customerId = cid;   // and the customer it was read for
  _pdPlan = d;
  box.innerHTML = _pdRenderPlan(d);
}

// The customer whose page this tab is on.
function _pdCustomerId() {
  return _custPage.id || '';
}

function _pdCustomerName() {
  return (_custPage.cust && _custPage.cust.customer_name) || '';
}

function _pdRenderPlan(plan) {
  var html = '<div class="card p-5">';
  html += '<div class="card-title mb-3">'
       + t('hdr_plan', 'Plan') + '</div>';

  if (plan.missing_consent) {
    html += '<div class="alert alert-error mb-4"><strong>'
         + t('hdr_missing_consent', 'Consent missing') + '.</strong> '
         + t('msg_missing_consent', 'This tenant has not consented to Policy.ReadWrite.ConditionalAccess. The plan is shown, and nothing can be applied.')
         + '<div class="mt-3"><button class="btn btn-primary" data-write="tenant" data-click-handler="policyConsentStart">'
         + t('btn_request_consent', 'Sign in as Global Admin and grant it') + '</button></div>'
         + '<div id="pd-consent"></div></div>';
  }

  if (!plan.changes.length) {
    html += '<div class="text-muted">' + t('msg_no_changes', 'The tenant already matches this standard.') + '</div></div>';
    return html;
  }

  html += '<div class="border rounded-lg overflow-hidden">';
  plan.changes.forEach(function(c) {
    var refused = !!c.refused;
    var cls = refused ? 'pd-diff-refused' : (c.action === 'delete' ? 'pd-diff-rem' : (c.action === 'update' ? 'pd-diff-chg' : 'pd-diff-add'));
    var icon = refused ? '&#10007;' : (c.action === 'delete' ? '−' : (c.action === 'update' ? '~' : '+'));
    var label = refused ? t('lbl_refused', 'Refused') : t('lbl_action_' + c.action, c.action);
    
    html += '<div class="pd-diff-row">';
    html += '<div class="pd-diff-head">';
    html += '<span class="pd-diff-icon ' + cls + '" aria-label="' + esc(label) + '" title="' + esc(label) + '">' + icon + '</span>';
    html += '<div class="flex-1">';
    html += '<div class="fw-semibold text-default">' + esc(c.name) + ' <span class="' + cls + ' text-xs fw-semibold py-0-5 px-2 rounded-full ml-2">' + esc(label) + '</span></div>';
    
    if (c.adopts) {
      html += '<div class="text-accent mt-1 text-sm">'
           + t('msg_adopts', 'Takes over «{name}» and renames it').replace('{name}', esc(c.adopts)) + '</div>';
    }
    if (c.why) html += '<div class="text-dim mt-1 text-sm italic">' + esc(c.why) + '</div>';
    if (c.fields && c.fields.length) {
      html += '<div class="text-muted mt-1 text-xs">' + t('drift_fields', 'Fields changed') + ': ' + esc(c.fields.join(', ')) + '</div>';
    }
    if (refused) html += '<div class="text-danger mt-1 text-sm fw-medium">' + esc(c.refused) + '</div>';
    
    html += '</div></div></div>';
  });
  html += '</div>';

  html += '<div class="mt-4 text-xs text-dim font-mono">'
       + t('lbl_fingerprint', 'Tenant fingerprint') + ': ' + esc(plan.fingerprint) + '</div>';

  var blocked = plan.missing_consent || plan.applicable === 0;
  html += '<div class="mt-4 flex gap-3 items-center">';
  html += '<button class="btn btn-primary" ' + (blocked ? 'disabled ' : '') + 'data-write="tenant" data-click-handler="policyDeployApply">'
       + t('btn_apply', 'Apply {n} change(s)').replace('{n}', Number(plan.applicable)) + '</button>';
  html += '<span class="text-xs text-muted">'
       + t('msg_apply_note', 'Applying re-checks the tenant and refuses if it has changed since this plan.') + '</span>';
  html += '</div></div>';
  return html;
}

async function policyDeployApply() {
  if (!_pdPlan) return;
  // Typed confirmation, as the destructive dialogs elsewhere use. This one
  // reaches into somebody else's production directory.
  var name = _pdCustomerName() || 'APPLY';
  var ok = await showTypedConfirm(
    name,
    t('dlg_confirm_deploy', 'Deploy {n} policy change(s) to {customer}?')
      .replace('{n}', _pdPlan.applicable).replace('{customer}', name),
    t('dlg_deploy_warning', 'This writes into the customer Microsoft tenant. New policies arrive in report-only mode.')
  );
  if (!ok) return;

  var body = {
    template: _pdPlan.template,
    // The fingerprint the plan was read against, not one recomputed now —
    // recomputing would confirm whatever the tenant looks like at this instant,
    // which is exactly the state nobody reviewed.
    fingerprint: _pdPlan.fingerprint,
    values: { break_glass_group: document.getElementById('pd-breakglass').value.trim() },
    // The same selection the plan was built from, so apply deploys exactly the
    // subset that was approved — a different set would not match the fingerprint.
    select: _pdPlan.select || [],
  };
  // Applied to the customer the plan was read for, and only on that
  // customer's page.
  if (!_pdPlan.customerId || _pdPlan.customerId !== _pdCustomerId()) return;
  var d = await apiFetch('/api/policy-deploy/' + encodeURIComponent(_pdPlan.customerId) + '/apply', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (!d) return;

  var box = document.getElementById('pd-plan');
  var html = '<div class="card p-5">';
  html += '<div class="card-title mb-3">'
       + t('hdr_result', 'Result') + '</div>';
  (d.applied || []).forEach(function(c) {
    html += '<div class="py-1 px-0 text-success">&#10003; ' + esc(c.name) + '</div>';
  });
  (d.failed || []).forEach(function(c) {
    html += '<div class="py-1 px-0 text-danger">&#10007; ' + esc(c.name) + ' · ' + esc(c.error || '') + '</div>';
  });
  (d.refused || []).forEach(function(c) {
    html += '<div class="py-1 px-0 text-dim">&#8211; ' + esc(c.name) + ' · ' + esc(c.refused || '') + '</div>';
  });
  html += '<div class="mt-3 text-xs text-muted">'
       + t('msg_restore_point', 'A restore point holding the policies as they were was written before anything changed.') + '</div>';
  html += '</div>';
  box.innerHTML = html;
  showToast(t('msg_deploy_done', 'Deployment finished'), 'success', 4000);
}
