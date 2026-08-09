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

var _pdPlan = null;
var _pdTemplates = [];

async function policyDeployLoad() {
  var el = document.getElementById('policy-deploy-content');
  if (!el) return;
  el.innerHTML = '<div class="loader" style="width:24px;height:24px;margin:32px auto;"></div>';

  // The active customer lives in state the customers view fills, so opening
  // this screen first would show "no customer selected" for a session that has
  // one. Fetched directly rather than by calling loadCustomers(), which renders
  // into DOM that only exists on that view.
  if (!_customersActiveId) {
    var cs = await apiFetch('/api/customers');
    if (cs) { _allCustomers = cs.customers || []; _customersActiveId = cs.active_id; }
  }

  var d = await apiFetch('/api/policy-deploy/templates?lang=' + _lang);
  if (!d || !d.templates) { el.innerHTML = '<div class="alert alert-error">' + t('status_error') + '</div>'; return; }
  _pdTemplates = d.templates;
  _pdPlan = null;
  el.innerHTML = _pdForm();
  policyEnforceLoad();
  policyRestoreLoad();
}

function _pdForm() {
  var cust = _pdCustomerName() || t('msg_no_customer_selected', 'No customer selected');
  var html = '<div class="card" style="padding:var(--space-5);margin-bottom:var(--space-4);">';
  html += '<div style="font-size:var(--font-sm);color:var(--text-muted);margin-bottom:var(--space-4);">'
       + t('lbl_customer', 'Customer') + ': <strong>' + esc(cust) + '</strong></div>';

  html += '<label style="display:block;font-size:var(--font-xs);color:var(--text-muted);margin-bottom:4px;">'
       + t('lbl_standard', 'Standard') + '</label>';
  html += '<select id="pd-template" style="width:100%;padding:8px;margin-bottom:var(--space-4);background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);color:var(--text);">';
  _pdTemplates.forEach(function(tpl) {
    html += '<option value="' + esc(tpl.id) + '">' + esc(tpl.name) + ' ' + esc(tpl.version)
         + ' — ' + tpl.policies + ' ' + t('lbl_policies', 'policies') + '</option>';
  });
  html += '</select>';

  // Required, never defaulted. An unfilled exclusion excludes nobody, inside a
  // policy that applies to everybody — so the field is empty and the button
  // stays disabled until it is not.
  html += '<label style="display:block;font-size:var(--font-xs);color:var(--text-muted);margin-bottom:4px;">'
       + t('lbl_break_glass', 'Break-glass group (object ID)') + '</label>';
  html += '<input id="pd-breakglass" oninput="_pdValidate()" placeholder="00000000-0000-0000-0000-000000000000" '
       + 'style="width:100%;padding:8px;font-family:var(--mono);background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);color:var(--text);">';
  html += '<div style="font-size:var(--font-xs);color:var(--text-dim);margin:6px 0 var(--space-4);">'
       + t('msg_break_glass_help', 'Every policy in the standard excludes this group. It must hold at least one account that can never be locked out.') + '</div>';

  html += '<button class="btn btn-ghost" id="pd-adopt-btn" disabled onclick="policyAdoptionLoad()" style="margin-right:var(--space-2);">'
       + t('btn_check_existing', 'Check existing policies') + '</button>';
  html += '<button class="btn btn-primary" id="pd-plan-btn" disabled onclick="policyDeployPlan()">'
       + t('btn_plan', 'Show plan') + '</button>';
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
  box.innerHTML = '<div class="loader" style="width:18px;height:18px;margin:12px 0;"></div>';

  var d = await apiFetch('/api/policy-deploy/' + encodeURIComponent(_pdCustomerId()) + '/consent/start', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}',
  });
  if (!d || !d.user_code) { box.innerHTML = ''; return; }

  var html = '<div style="margin-top:var(--space-3);padding:var(--space-3);border:1px solid var(--border);border-radius:var(--radius-md);background:var(--bg);">';
  html += '<div style="font-size:var(--font-xs);color:var(--text-muted);margin-bottom:6px;">'
       + t('msg_consent_step1', 'Open this page and sign in as a Global Admin of the customer tenant:') + '</div>';
  html += '<div><a href="' + esc(d.verification_uri) + '" target="_blank" rel="noopener noreferrer" style="color:var(--blue);">'
       + esc(d.verification_uri) + '</a></div>';
  html += '<div style="font-size:var(--font-xs);color:var(--text-muted);margin:10px 0 4px;">'
       + t('msg_consent_step2', 'Enter this code:') + '</div>';
  html += '<div style="font-family:var(--mono);font-size:22px;font-weight:700;letter-spacing:2px;">'
       + esc(d.user_code) + '</div>';
  html += '<div id="pd-consent-status" style="font-size:var(--font-xs);color:var(--text-dim);margin-top:10px;">'
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
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:16px auto;"></div>';

  var body = { template: document.getElementById('pd-template').value, values: _pdValues() };
  var d = await apiFetch('/api/policy-deploy/' + encodeURIComponent(_pdCustomerId()) + '/adoption/suggest', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (!d) { el.innerHTML = ''; return; }

  var confirmed = {};
  (d.confirmed || []).forEach(function(c) { confirmed[c.template] = c.policy_id; });

  var html = '<div class="card" style="padding:var(--space-5);margin-top:var(--space-4);">';
  html += '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:var(--space-2);">'
       + t('hdr_adoption', 'Existing policies') + '</div>';
  html += '<div style="font-size:var(--font-xs);color:var(--text-dim);margin-bottom:var(--space-3);">'
       + t('msg_adoption_intro', 'The tenant may already have a policy doing the same job under another name. Choosing it means the standard takes it over and renames it, instead of adding a second one beside it. Suggestions are matched on what a policy does, never on its wording — nothing is adopted until you save.')
       + '</div>';

  var any = false;
  Object.keys(d.suggestions || {}).forEach(function(name) {
    var candidates = d.suggestions[name] || [];
    html += '<div style="padding:var(--space-3) 0;border-bottom:1px solid var(--border);">';
    html += '<div style="font-weight:600;font-size:var(--font-xs);">' + esc(name) + '</div>';
    if (!candidates.length && !confirmed[name]) {
      html += '<div style="font-size:var(--font-xs);color:var(--text-dim);margin-top:2px;">'
           + t('msg_no_candidate', 'Nothing in the tenant resembles this. It will be created.') + '</div>';
    } else {
      any = true;
      html += '<select data-adopt="' + esc(name) + '" style="width:100%;margin-top:6px;padding:6px;font-size:var(--font-xs);background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);">';
      html += '<option value="">' + t('opt_create_new', 'Create a new policy') + '</option>';
      candidates.forEach(function(c) {
        var sel = confirmed[name] === c.policy_id ? ' selected' : '';
        html += '<option value="' + esc(c.policy_id) + '"' + sel + '>'
             + esc(c.display_name) + ' [' + esc(c.state) + '] — ' + esc(c.reasons.join('; ')) + '</option>';
      });
      html += '</select>';
    }
    html += '</div>';
  });

  html += '<button class="btn btn-primary" style="margin-top:var(--space-3);" onclick="policyAdoptionSave()">'
       + t('btn_save_adoption', 'Save choices') + '</button>';
  if (!any) {
    html += '<div style="font-size:var(--font-xs);color:var(--text-dim);margin-top:var(--space-2);">'
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

  var html = '<div class="card" style="padding:var(--space-5);margin-top:var(--space-4);">';
  html += '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:var(--space-2);">'
       + t('hdr_enforce', 'Report-only policies') + '</div>';
  html += '<div style="font-size:var(--font-xs);color:var(--text-dim);margin-bottom:var(--space-3);">'
       + t('msg_enforce_intro', 'These are live but block nobody. Read the sign-in logs in Entra to see who they would have stopped, then enforce.') + '</div>';
  html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
  d.policies.forEach(function(p) {
    html += '<tr style="border-bottom:1px solid var(--border);vertical-align:top;">';
    html += '<td style="padding:8px 0;">' + esc(p.name);
    if (p.refused) {
      html += '<div style="color:var(--red);margin-top:2px;">' + esc(p.refused) + '</div>';
    }
    html += '</td><td style="padding:8px 0;text-align:right;white-space:nowrap;">';
    if (p.refused) {
      html += '<span style="color:var(--text-dim);">' + t('lbl_cannot_enforce', 'Cannot enforce') + '</span>';
    } else {
      html += '<button class="btn btn-ghost btn-sm" onclick="policyEnforce(\'' + esc(p.policy_id) + '\',\'' + esc(p.name).replace(/'/g,"\\'") + '\')">'
           + t('btn_enforce', 'Enforce') + '</button>';
    }
    html += '</td></tr>';
  });
  html += '</table></div>';
  el.innerHTML = html;
}

async function policyEnforce(policyId, name) {
  if (typeof showTypedConfirm === 'function') {
    var ok = await showTypedConfirm(
      name,
      t('dlg_confirm_enforce', 'Start enforcing «{name}»?').replace('{name}', name),
      t('dlg_enforce_warning', 'From this moment the policy turns sign-ins away. A restore point is taken first.')
    );
    if (!ok) return;
  }
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

  var html = '<div class="card" style="padding:var(--space-5);margin-top:var(--space-4);">';
  html += '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:var(--space-2);">'
       + t('hdr_restore', 'Restore') + '</div>';
  html += '<div style="font-size:var(--font-xs);color:var(--text-dim);margin-bottom:var(--space-3);">'
       + t('msg_restore_intro', 'Put the tenant back to a stored state. Restore points are taken immediately before a deployment; audit snapshots are older and coarser.') + '</div>';
  html += '<select id="pd-restore-source" style="width:100%;padding:8px;margin-bottom:var(--space-3);background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);color:var(--text);">';
  d.sources.forEach(function(s) {
    var kind = s.kind === 'deployment' ? t('lbl_before_deploy', 'before a deployment') : t('lbl_audit_run', 'audit run');
    html += '<option value="' + esc(s.kind) + '|' + esc(s.ref) + '">'
         + esc(s.captured_at) + ' — ' + kind + ' (' + s.count + ' ' + t('lbl_policies', 'policies') + ')</option>';
  });
  html += '</select>';
  html += '<button class="btn btn-ghost" onclick="policyRestorePlan()">' + t('btn_plan_restore', 'Show restore plan') + '</button>';
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
  box.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:16px auto;"></div>';
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
    return '<div class="alert alert-error" style="margin-top:var(--space-3);"><strong>'
      + t('hdr_missing_consent', 'Consent missing') + '.</strong> ' + t('msg_missing_consent', '') + '</div>';
  }
  if (!plan.changes.length) {
    return '<div style="margin-top:var(--space-3);color:var(--text-muted);font-size:var(--font-xs);">'
      + t('msg_already_matches', 'The tenant already matches this stored state.') + '</div>';
  }
  var html = '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;margin-top:var(--space-3);">';
  plan.changes.forEach(function(c) {
    var colour = c.refused ? 'var(--red)' : (c.action === 'delete' ? 'var(--orange)' : 'var(--green)');
    var label = c.refused ? t('lbl_refused', 'Refused') : t('lbl_action_' + c.action, c.action);
    html += '<tr style="border-bottom:1px solid var(--border);vertical-align:top;">'
      + '<td style="padding:6px 10px 6px 0;color:' + colour + ';font-weight:600;white-space:nowrap;">' + esc(label) + '</td>'
      + '<td style="padding:6px 0;">' + esc(c.name)
      + (c.refused ? '<div style="color:var(--red);margin-top:2px;">' + esc(c.refused) + '</div>' : '')
      + '</td></tr>';
  });
  html += '</table>';
  html += '<button class="btn btn-primary" style="margin-top:var(--space-3);" ' + (plan.applicable ? '' : 'disabled ')
       + 'onclick="policyRestoreApply()">' + t('btn_apply_restore', 'Restore {n} policy change(s)').replace('{n}', plan.applicable) + '</button>';
  return html;
}

async function policyRestoreApply() {
  if (!_pdRestore) return;
  var name = _pdCustomerName() || 'RESTORE';
  if (typeof showTypedConfirm === 'function') {
    var ok = await showTypedConfirm(
      name,
      t('dlg_confirm_restore', 'Restore {n} policy change(s) on {customer}?')
        .replace('{n}', _pdRestore.applicable).replace('{customer}', name),
      t('dlg_restore_warning', 'This writes into the customer Microsoft tenant. A restore point of the current state is taken first.')
    );
    if (!ok) return;
  }
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
  var ok = _GUID.test(v.trim());
  ['pd-plan-btn', 'pd-adopt-btn'].forEach(function(id) {
    var b = document.getElementById(id);
    if (b) b.disabled = !ok;
  });
}

async function policyDeployPlan() {
  var box = document.getElementById('pd-plan');
  box.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';
  _pdPlan = null;

  var body = {
    template: document.getElementById('pd-template').value,
    values: { break_glass_group: document.getElementById('pd-breakglass').value.trim() },
  };
  var d = await apiFetch('/api/policy-deploy/' + encodeURIComponent(_pdCustomerId()) + '/plan?lang=' + _lang, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (!d) { box.innerHTML = ''; return; }
  _pdPlan = d;
  box.innerHTML = _pdRenderPlan(d);
}

function _pdCustomerId() {
  return _customersActiveId || '';
}

function _pdCustomer() {
  var id = _pdCustomerId();
  if (!id) return null;
  return (_allCustomers || []).find(function(c) {
    return (c._id || c.customer_id) === id;
  }) || null;
}

function _pdCustomerName() {
  var c = _pdCustomer();
  return (c && (c.CustomerName || c.customer_name)) || '';
}

function _pdRenderPlan(plan) {
  var html = '<div class="card" style="padding:var(--space-5);">';
  html += '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:var(--space-3);">'
       + t('hdr_plan', 'Plan') + '</div>';

  if (plan.missing_consent) {
    html += '<div class="alert alert-error" style="margin-bottom:var(--space-4);"><strong>'
         + t('hdr_missing_consent', 'Consent missing') + '.</strong> '
         + t('msg_missing_consent', 'This tenant has not consented to Policy.ReadWrite.ConditionalAccess. The plan is shown, and nothing can be applied.')
         + '<div style="margin-top:var(--space-3);"><button class="btn btn-primary" onclick="policyConsentStart()">'
         + t('btn_request_consent', 'Sign in as Global Admin and grant it') + '</button></div>'
         + '<div id="pd-consent"></div></div>';
  }

  if (!plan.changes.length) {
    html += '<div style="color:var(--text-muted);">' + t('msg_no_changes', 'The tenant already matches this standard.') + '</div></div>';
    return html;
  }

  html += '<table style="width:100%;font-size:var(--font-xs);border-collapse:collapse;">';
  plan.changes.forEach(function(c) {
    var refused = !!c.refused;
    var colour = refused ? 'var(--red)' : (c.action === 'delete' ? 'var(--orange)' : 'var(--green)');
    var label = refused ? t('lbl_refused', 'Refused') : t('lbl_action_' + c.action, c.action);
    html += '<tr style="border-bottom:1px solid var(--border);vertical-align:top;">';
    html += '<td style="padding:8px 10px 8px 0;white-space:nowrap;color:' + colour + ';font-weight:600;">' + esc(label) + '</td>';
    html += '<td style="padding:8px 0;">';
    html += '<div style="font-weight:600;">' + esc(c.name) + '</div>';
    if (c.adopts) {
      html += '<div style="color:var(--blue);margin-top:2px;">'
           + t('msg_adopts', 'Takes over «{name}» and renames it').replace('{name}', esc(c.adopts)) + '</div>';
    }
    if (c.why) html += '<div style="color:var(--text-dim);margin-top:2px;">' + esc(c.why) + '</div>';
    if (c.fields && c.fields.length) {
      html += '<div style="color:var(--text-muted);margin-top:4px;">' + t('drift_fields', 'Fields changed') + ': ' + esc(c.fields.join(', ')) + '</div>';
    }
    if (refused) html += '<div style="color:var(--red);margin-top:4px;">' + esc(c.refused) + '</div>';
    html += '</td></tr>';
  });
  html += '</table>';

  html += '<div style="margin-top:var(--space-4);font-size:var(--font-xs);color:var(--text-dim);font-family:var(--mono);">'
       + t('lbl_fingerprint', 'Tenant fingerprint') + ': ' + esc(plan.fingerprint) + '</div>';

  var blocked = plan.missing_consent || plan.applicable === 0;
  html += '<div style="margin-top:var(--space-4);display:flex;gap:var(--space-3);align-items:center;">';
  html += '<button class="btn btn-primary" ' + (blocked ? 'disabled ' : '') + 'onclick="policyDeployApply()">'
       + t('btn_apply', 'Apply {n} change(s)').replace('{n}', plan.applicable) + '</button>';
  html += '<span style="font-size:var(--font-xs);color:var(--text-muted);">'
       + t('msg_apply_note', 'Applying re-checks the tenant and refuses if it has changed since this plan.') + '</span>';
  html += '</div></div>';
  return html;
}

async function policyDeployApply() {
  if (!_pdPlan) return;
  // Typed confirmation, as the destructive dialogs elsewhere use. This one
  // reaches into somebody else's production directory.
  if (typeof showTypedConfirm === 'function') {
    var name = _pdCustomerName() || 'APPLY';
    var ok = await showTypedConfirm(
      name,
      t('dlg_confirm_deploy', 'Deploy {n} policy change(s) to {customer}?')
        .replace('{n}', _pdPlan.applicable).replace('{customer}', name),
      t('dlg_deploy_warning', 'This writes into the customer Microsoft tenant. New policies arrive in report-only mode.')
    );
    if (!ok) return;
  }

  var body = {
    template: _pdPlan.template,
    // The fingerprint the plan was read against, not one recomputed now —
    // recomputing would confirm whatever the tenant looks like at this instant,
    // which is exactly the state nobody reviewed.
    fingerprint: _pdPlan.fingerprint,
    values: { break_glass_group: document.getElementById('pd-breakglass').value.trim() },
  };
  var d = await apiFetch('/api/policy-deploy/' + encodeURIComponent(_pdCustomerId()) + '/apply', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (!d) return;

  var box = document.getElementById('pd-plan');
  var html = '<div class="card" style="padding:var(--space-5);">';
  html += '<div style="font-size:var(--font-sm);font-weight:600;color:var(--blue);text-transform:uppercase;margin-bottom:var(--space-3);">'
       + t('hdr_result', 'Result') + '</div>';
  (d.applied || []).forEach(function(c) {
    html += '<div style="padding:4px 0;color:var(--green);">&#10003; ' + esc(c.name) + '</div>';
  });
  (d.failed || []).forEach(function(c) {
    html += '<div style="padding:4px 0;color:var(--red);">&#10007; ' + esc(c.name) + ' — ' + esc(c.error || '') + '</div>';
  });
  (d.refused || []).forEach(function(c) {
    html += '<div style="padding:4px 0;color:var(--text-dim);">&#8211; ' + esc(c.name) + ' — ' + esc(c.refused || '') + '</div>';
  });
  html += '<div style="margin-top:var(--space-3);font-size:var(--font-xs);color:var(--text-muted);">'
       + t('msg_restore_point', 'A restore point holding the policies as they were was written before anything changed.') + '</div>';
  html += '</div>';
  box.innerHTML = html;
  showToast(t('msg_deploy_done', 'Deployment finished'), 'success', 4000);
}
