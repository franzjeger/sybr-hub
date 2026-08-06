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

  html += '<button class="btn btn-primary" id="pd-plan-btn" disabled onclick="policyDeployPlan()">'
       + t('btn_plan', 'Show plan') + '</button>';
  html += '</div><div id="pd-plan"></div>';
  return html;
}

// A GUID, checked here only to catch a paste that went wrong. The server and
// Graph are the authorities; this saves a round trip, it does not decide.
var _GUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function _pdValidate() {
  var v = (document.getElementById('pd-breakglass') || {}).value || '';
  var btn = document.getElementById('pd-plan-btn');
  if (btn) btn.disabled = !_GUID.test(v.trim());
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
         + '</div>';
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
