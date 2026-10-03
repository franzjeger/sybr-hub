// Granular M365 Baseline Engine UI

// Handlers for this view's buttons (see registerUiHandlers in app.js).
registerUiHandlers({
  baselineDeployPlan: function() { baselineDeployPlan(); },
  baselineDeployApply: function() { baselineDeployApply(); },
});

async function baselineDeployLoad() {
  var el = document.getElementById('baseline-deploy-content');
  if (!el) return;
  el.innerHTML = '<div class="loader loader-lg"></div>';

  if (!_customersActiveId) {
    var cs = await apiFetch('/api/customers');
    if (cs) { _allCustomers = cs.customers || []; _customersActiveId = cs.active_id; }
  }

  var d = await apiFetch('/api/baseline-deploy/schema');
  if (!d) { el.innerHTML = '<div class="alert alert-error">' + t('bd_error_loading_schema','Kunne ikke laste skjemaet') + '</div>'; return; }

  el.innerHTML = _renderBaselineForm(d);
}

function _renderBaselineForm(schema) {
  var cust = (_allCustomers || []).find(c => c._id === _customersActiveId)?.CustomerName || t('msg_no_customer_selected','Ingen kunde valgt');
  var html = '<div class="card bd-form">';
  html += '<div class="bd-customer">' + t('lbl_customer','Kunde') + ': <strong>' + esc(cust) + '</strong></div>';

  html += '<div class="bd-section-title">' + t('bd_select_policies','Velg policyene som skal rulles ut') + '</div>';

  var props = schema.$defs || {};

  html += '<div id="bd-policies" class="bd-policies">';

  // Hardcode the 4 categories based on the models for nice UI
  var categories = [
    { key: 'entra', title: t('bd_cat_entra','Entra ID-innstillinger'), def: 'EntraSettings' },
    { key: 'conditional_access', title: t('bd_cat_conditional_access','Conditional Access'), def: 'ConditionalAccessSettings' },
    { key: 'intune_config', title: t('bd_cat_intune_config','Intune-konfigurasjon'), def: 'IntuneConfigSettings' },
    { key: 'intune_compliance', title: t('bd_cat_intune_compliance','Intune-samsvar'), def: 'IntuneComplianceSettings' }
  ];

  categories.forEach(cat => {
      html += '<div class="bd-cat-title">' + cat.title + '</div>';
      var fields = props[cat.def]?.properties || {};
      Object.keys(fields).forEach(fieldName => {
          var field = fields[fieldName];
          html += '<label class="bd-field-row">';
          html += '<input type="checkbox" class="bd-pol" value="' + cat.key + '.' + esc(fieldName) + '" checked>';
          html += '<span class="bd-field-body"><span class="bd-field-name">' + esc(fieldName) + '</span>';
          html += '<span class="bd-field-desc">' + esc(field.description || '') + '</span>';
          html += '</span></label>';
      });
  });

  html += '</div>';
  html += '<button class="btn btn-primary" data-click-handler="baselineDeployPlan">' + t('bd_plan_deployment','Planlegg utrulling') + '</button>';
  html += '<div id="bd-plan" class="bd-plan-box"></div>';
  html += '</div>';
  return html;
}

async function baselineDeployPlan() {
  var box = document.getElementById('bd-plan');
  box.innerHTML = '<div class="loader loader-md"></div>';

  var selected = Array.from(document.querySelectorAll('.bd-pol:checked')).map(cb => cb.value);
  var body = {
      baseline: {
          entra: {}, conditional_access: {}, intune_config: {}, intune_compliance: {}
      },
      selected: selected
  };

  var d = await apiFetch('/api/baseline-deploy/' + encodeURIComponent(_customersActiveId) + '/plan', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });

  if (!d) { box.innerHTML = ''; return; }

  var html = '<div class="card bd-result-card">';
  html += '<div class="bd-result-title">' + t('bd_plan_title','Utrullingsplan') + '</div>';
  d.diff.changes.forEach(c => {
      html += '<div class="bd-change-row"><strong class="bd-change-create">+ ' + t('btn_create','Opprett') + '</strong> ' + esc(c.category + '.' + c.name) + '</div>';
  });

  // Store request body for apply
  window._bdLastReq = body;
  html += '<button class="btn btn-primary bd-apply-btn" data-click-handler="baselineDeployApply">' + t('bd_apply_changes','Rull ut endringene') + '</button>';
  html += '</div>';
  box.innerHTML = html;
}

async function baselineDeployApply() {
  var box = document.getElementById('bd-plan');
  box.innerHTML = '<div class="loader loader-md"></div>';

  var d = await apiFetch('/api/baseline-deploy/' + encodeURIComponent(_customersActiveId) + '/apply', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(window._bdLastReq)
  });

  if (!d) { box.innerHTML = ''; return; }

  var html = '<div class="card bd-result-card">';
  html += '<div class="bd-result-title">' + t('bd_result_title','Utrullingsresultat') + '</div>';
  d.result.applied.forEach(c => {
      html += '<div class="bd-result-ok">&#10003; ' + t('bd_applied','Rullet ut') + ': ' + esc(c.name) + '</div>';
  });
  d.result.failed.forEach(c => {
      html += '<div class="bd-result-fail">&#10007; ' + t('msg_failed','Feilet') + ': ' + esc(c.name) + ': ' + esc(c.error) + '</div>';
  });
  html += '</div>';
  box.innerHTML = html;
}
