// ═══════════════════════════════════════════════════════════════════
// CUSTOMERS — notes, expiry, IT Glue, tags, management & switcher
// ═══════════════════════════════════════════════════════════════════

registerUiHandlers({
  // IT Glue organisation picker, upload and import dialogs.
  filterITGlueOrgPicker: function() { filterITGlueOrgPicker(); },
  itglueOrgPickEnable: function() { document.getElementById('btn-itglue-org-pick').disabled = false; },
  itglueUploadSelectAll: function(el) {
    document.querySelectorAll('.itglue-file-cb').forEach(function(c) { c.checked = el.checked; });
    updateITGlueUploadBtn();
  },
  updateITGlueUploadBtn: function() { updateITGlueUploadBtn(); },
  filterITGlueUploadOrgs: function() { filterITGlueUploadOrgs(); },
  filterITGlueImport: function() { filterITGlueImport(); },
  toggleAllITGlueImport: function(el) { toggleAllITGlueImport(el.checked); },
  updateITGlueImportBtn: function() { updateITGlueImportBtn(); },
  // Tag editor.
  removeTagAndRefresh: function(el) { removeTagAndRefresh(el.dataset.customerId, Number(el.dataset.index)); },
  tagEditorAddOnEnter: function(el, event) {
    if (event.key === 'Enter') { addTagFromInput(el.dataset.customerId); event.preventDefault(); }
  },
  addTagFromInput: function(el) { addTagFromInput(el.dataset.customerId); },
  addSuggestedTag: function(el) { addSuggestedTag(el.dataset.customerId, el.dataset.tag); },
  // Customer cards: the bulk checkbox and the star must not open the card.
  overviewSelectCustomer: function(el) { overviewSelectCustomer(el.dataset.id); },
  customerCardToggleBulk: function(el, event) { event.stopPropagation(); toggleBulkCustomer(el.dataset.id, el); },
  customerCardToggleFavorite: function(el, event) { event.stopPropagation(); toggleFavorite(el.dataset.id); },
  deleteCustomer: function(el) { deleteCustomer(el.dataset.id, el.dataset.name); },
  cancelBulkAudit: function() { cancelBulkAudit(); },
});

// ── Expiry banner ─────────────────────────────────────────────────────────────
let _expiryData = null;

async function loadExpiryBanner() {
  try {
    const d = await apiFetch('/api/expiry/check');
    _expiryData = d;
    renderExpiryBanner(d);
  } catch(e) { console.warn('loadExpiryBanner failed:', e); }
}

function renderExpiryBanner(d) {
  const area = document.getElementById('expiry-banner-area');
  if (!area) return;
  const urgent = (d.items || []).filter(i => i.category === 'expired' || i.category === 'critical' || i.category === 'warning');
  if (urgent.length === 0) { area.innerHTML = ''; return; }
  const hasExpired  = urgent.some(i => i.category === 'expired');
  const hasCritical = urgent.some(i => i.category === 'critical');
  const cls = hasExpired ? 'has-expired' : hasCritical ? 'has-critical' : 'has-warning';
  const titleText = hasExpired ? t('expiry_expired','Credentials have expired!') : hasCritical ? t('expiry_critical','Credentials expiring soon!') : t('expiry_warning','Credentials expiring within 30 days');
  const itemsHtml = urgent.map(i => {
    const typeLabel = i.type === 'secret' ? t('expiry_type_secret','Client secret') : t('expiry_type_cert','Certificate');
    const daysText = i.days_remaining < 0 ? t('expiry_days_ago','expired {days} days ago').replace('{days}', Math.abs(i.days_remaining)) : t('expiry_days_remaining','{days} days remaining').replace('{days}', Number(i.days_remaining));
    return '<div class="expiry-item"><span class="expiry-dot ' + esc(i.category) + '"></span><strong>' + esc(i.customer_name) + '</strong> · ' + typeLabel + ' (' + esc(i.expiry_date) + ', ' + daysText + ')</div>';
  }).join('');
  area.innerHTML = '<div class="expiry-banner ' + cls + '"><div class="expiry-banner-title"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg> ' + titleText + '</div>' + itemsHtml + '</div>';
}

function getExpiryBadgeForCustomer(customerId) {
  if (!_expiryData || !_expiryData.items) return '';
  const items = _expiryData.items.filter(i => i.customer_id === customerId && (i.category === 'expired' || i.category === 'critical' || i.category === 'warning'));
  if (items.length === 0) return '';
  const worst = items[0].category;
  const label = worst === 'expired' ? t('expiry_badge_expired','Expired') : worst === 'critical' ? t('expiry_badge_critical','Critical') : t('expiry_badge_warning','Expiring soon');
  return '<span class="cust-expiry-badge ' + esc(worst) + '">' + label + '</span>';
}

let _itglueOrgCache = null;

// ── IT Glue org picker (reusable) ───────────────────────────────────────────
var _itgluePickerCallback = null;

async function openITGlueOrgPicker(callback, autoMatchName) {
  _itgluePickerCallback = callback;
  var modal = document.getElementById('itglue-org-picker-modal');
  var content = document.getElementById('itglue-org-picker-content');
  var btn = document.getElementById('btn-itglue-org-pick');
  modal.style.display = 'flex';
  btn.disabled = true;
  btn.textContent = t('btn_select');
  content.innerHTML = '<div style="text-align:center;padding:24px;"><div class="loader" style="width:24px;height:24px;margin:0 auto 12px;"></div>' + t('msg_fetching_orgs') + '</div>';

  try {
    if (!_itglueOrgCache) {
      var d = await apiFetch('/api/itglue/organizations', {method: 'POST'});
      if (d.error) { content.innerHTML = '<div class="alert alert-error">' + esc(d.error) + '</div>'; return; }
      _itglueOrgCache = d.organizations || [];
    }
    if (_itglueOrgCache.length === 0) {
      content.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-muted);">' + t('msg_no_orgs_found') + '</div>';
      return;
    }

    var orgs = _itglueOrgCache.slice().sort(function(a,b){ return a.name.localeCompare(b.name); });

    // Auto-match: find best match for current customer name
    var bestIdx = -1;
    if (autoMatchName) {
      var lower = autoMatchName.toLowerCase();
      // Exact match first
      for (let i = 0; i < orgs.length; i++) {
        if (orgs[i].name.toLowerCase() === lower) { bestIdx = i; break; }
      }
      // Partial match
      if (bestIdx < 0) {
        for (let i = 0; i < orgs.length; i++) {
          if (orgs[i].name.toLowerCase().indexOf(lower) >= 0 || lower.indexOf(orgs[i].name.toLowerCase()) >= 0) { bestIdx = i; break; }
        }
      }
    }

    var html = '<input type="text" id="itglue-org-picker-search" class="field-input" placeholder="' + t('lbl_search') + '" style="margin-bottom:10px;padding:6px 12px;font-size:12px;" data-input-handler="filterITGlueOrgPicker">';
    html += '<div style="max-height:300px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;">';
    for (let i = 0; i < orgs.length; i++) {
      var matched = (i === bestIdx);
      html += '<label class="itglue-org-picker-row" data-name="' + esc(orgs[i].name.toLowerCase()) + '" style="display:flex;align-items:center;gap:8px;padding:8px 12px;cursor:pointer;border-bottom:1px solid var(--border);' + (matched ? 'background:rgba(77,159,181,0.1);' : '') + '">';
      html += '<input type="radio" name="itglue-org-pick" value="' + esc(orgs[i].id) + '" data-orgname="' + esc(orgs[i].name) + '" ' + (matched ? 'checked' : '') + ' data-change-handler="itglueOrgPickEnable" style="width:16px;height:16px;">';
      html += '<span style="font-size:13px;">' + esc(orgs[i].name) + '</span>';
      if (matched) html += '<span style="margin-left:auto;font-size:10px;color:var(--green);font-weight:600;">' + t('msg_recommended_match') + '</span>';
      html += '</label>';
    }
    html += '</div>';
    content.innerHTML = html;
    if (bestIdx >= 0) btn.disabled = false;

    // Scroll to match
    setTimeout(function() {
      var checked = content.querySelector('input[name="itglue-org-pick"]:checked');
      if (checked) checked.closest('label').scrollIntoView({block:'center'});
    }, 100);
  } catch (e) {
    content.innerHTML = '<div class="alert alert-error">' + t('status_error') + ': ' + esc(e.message) + '</div>';
  }
}

function filterITGlueOrgPicker() {
  var q = (document.getElementById('itglue-org-picker-search') || {}).value.toLowerCase();
  document.querySelectorAll('.itglue-org-picker-row').forEach(function(row) {
    row.style.display = row.dataset.name.indexOf(q) >= 0 ? '' : 'none';
  });
}

function confirmITGlueOrgPick() {
  var selected = document.querySelector('input[name="itglue-org-pick"]:checked');
  if (!selected || !_itgluePickerCallback) return;
  document.getElementById('itglue-org-picker-modal').style.display = 'none';
  _itgluePickerCallback({id: selected.value, name: selected.dataset.orgname});
  _itgluePickerCallback = null;
}

var _itglueUploadBtn = null;

async function uploadReportsToITGlue(btn) {
  _itglueUploadBtn = btn;
  // Check IT Glue config
  try {
    var settings = await apiFetch('/api/settings');
    if (!settings.itglue_api_key_set) {
      if (await showConfirm(t('dlg_confirm_itglue_setup'))) {
        openAdmin('integrations');
        setTimeout(function(){ toggleIntegConfig('itglue-config'); }, 300);
      }
      return;
    }
  } catch { showToast(t('err_check_settings_failed'), 'error'); return; }

  // Show the upload modal with file picker + org picker
  var modal = document.getElementById('itglue-upload-modal');
  var content = document.getElementById('itglue-upload-content');
  modal.style.display = 'flex';
  document.getElementById('btn-itglue-upload-go').disabled = true;
  content.innerHTML = '<div style="text-align:center;padding:24px;"><div class="loader" style="width:24px;height:24px;margin:0 auto 12px;"></div>' + t('msg_fetching_reports_orgs') + '</div>';

  try {
    // Fetch available reports and orgs in parallel
    var [reportsResp, orgsResp, filesResp] = await Promise.all([
      apiFetch('/api/itglue/available-reports'),
      _itglueOrgCache ? Promise.resolve({organizations: _itglueOrgCache}) : apiFetch('/api/itglue/organizations', {method:'POST'}),
      apiFetch('/api/files')
    ]);

    var files = reportsResp.files || [];
    if (files.length === 0) {
      content.innerHTML = '<div class="alert alert-error">' + t('msg_no_reports_available') + '</div>';
      return;
    }

    var orgs = orgsResp.organizations || [];
    if (!_itglueOrgCache && orgs.length > 0) _itglueOrgCache = orgs;
    if (orgs.length === 0) {
      content.innerHTML = '<div class="alert alert-error">' + t('msg_no_orgs_found_itglue') + '</div>';
      return;
    }
    orgs.sort(function(a,b){ return a.name.localeCompare(b.name); });

    // Auto-match customer name
    var customerName = (filesResp.credentials && filesResp.credentials.customer_name) || '';
    var bestOrgIdx = -1;
    if (customerName) {
      var lower = customerName.toLowerCase();
      for (let i = 0; i < orgs.length; i++) {
        if (orgs[i].name.toLowerCase() === lower) { bestOrgIdx = i; break; }
      }
      if (bestOrgIdx < 0) {
        for (let i = 0; i < orgs.length; i++) {
          if (orgs[i].name.toLowerCase().indexOf(lower) >= 0 || lower.indexOf(orgs[i].name.toLowerCase()) >= 0) { bestOrgIdx = i; break; }
        }
      }
    }

    // Build UI
    var html = '';

    // Step 1: File picker
    html += '<div style="font-weight:600;font-size:13px;margin-bottom:8px;">' + t('hdr_select_reports') + '</div>';
    html += '<div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;">';
    html += '<label style="font-size:12px;cursor:pointer;"><input type="checkbox" id="itglue-upload-select-all" data-change-handler="itglueUploadSelectAll" checked> ' + t('btn_select_all') + '</label>';
    html += '</div>';
    html += '<div style="max-height:180px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;margin-bottom:16px;">';
    for (let i = 0; i < files.length; i++) {
      var f = files[i];
      var ficon = f.name.endsWith('.pdf') ? icon('document',14) : icon('globe',14);
      html += '<label style="display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer;border-bottom:1px solid var(--border);font-size:12px;">';
      html += '<input type="checkbox" class="itglue-file-cb" value="' + esc(f.name) + '" checked data-change-handler="updateITGlueUploadBtn" style="width:15px;height:15px;">';
      html += ficon + ' <span style="flex:1;">' + esc(f.name) + '</span>';
      html += '<span style="color:var(--text-muted);">' + esc(f.size) + '</span>';
      html += '</label>';
    }
    html += '</div>';

    // Step 2: Org picker
    html += '<div style="font-weight:600;font-size:13px;margin-bottom:8px;">' + t('hdr_select_org') + '</div>';
    html += '<input type="text" id="itglue-upload-org-search" class="field-input" placeholder="' + t('lbl_search_org') + '" style="margin-bottom:6px;padding:6px 12px;font-size:12px;" data-input-handler="filterITGlueUploadOrgs">';
    html += '<div style="max-height:200px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;">';
    for (let i = 0; i < orgs.length; i++) {
      var matched = (i === bestOrgIdx);
      html += '<label class="itglue-upload-org-row" data-name="' + esc(orgs[i].name.toLowerCase()) + '" style="display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer;border-bottom:1px solid var(--border);' + (matched ? 'background:rgba(77,159,181,0.1);' : '') + '">';
      html += '<input type="radio" name="itglue-upload-org" value="' + esc(orgs[i].id) + '" data-orgname="' + esc(orgs[i].name) + '" ' + (matched ? 'checked' : '') + ' data-change-handler="updateITGlueUploadBtn" style="width:15px;height:15px;">';
      html += '<span style="font-size:12px;">' + esc(orgs[i].name) + '</span>';
      if (matched) html += '<span style="margin-left:auto;font-size:10px;color:var(--green);font-weight:600;">' + t('msg_recommended') + '</span>';
      html += '</label>';
    }
    html += '</div>';

    content.innerHTML = html;
    updateITGlueUploadBtn();

    // Scroll to matched org
    setTimeout(function() {
      var checked = content.querySelector('input[name="itglue-upload-org"]:checked');
      if (checked) checked.closest('label').scrollIntoView({block:'center'});
    }, 100);
  } catch (e) {
    content.innerHTML = '<div class="alert alert-error">' + t('status_error') + ': ' + esc(e.message) + '</div>';
  }
}

function filterITGlueUploadOrgs() {
  var q = (document.getElementById('itglue-upload-org-search') || {}).value.toLowerCase();
  document.querySelectorAll('.itglue-upload-org-row').forEach(function(r) {
    r.style.display = r.dataset.name.indexOf(q) >= 0 ? '' : 'none';
  });
}

function updateITGlueUploadBtn() {
  var fileCount = document.querySelectorAll('.itglue-file-cb:checked').length;
  var orgSelected = !!document.querySelector('input[name="itglue-upload-org"]:checked');
  var btn = document.getElementById('btn-itglue-upload-go');
  btn.disabled = fileCount === 0 || !orgSelected;
  btn.textContent = fileCount > 0 ? t('btn_upload_count').replace('{count}', fileCount) : t('btn_upload');
}

async function executeITGlueUpload() {
  var selectedFiles = [];
  document.querySelectorAll('.itglue-file-cb:checked').forEach(function(cb) {
    selectedFiles.push(cb.value);
  });
  var orgRadio = document.querySelector('input[name="itglue-upload-org"]:checked');
  if (!orgRadio || selectedFiles.length === 0) return;

  var orgId = orgRadio.value;
  var orgName = orgRadio.dataset.orgname;
  var btn = document.getElementById('btn-itglue-upload-go');
  btn.disabled = true;
  btn.textContent = t('btn_uploading');

  try {
    var d = await apiFetch('/api/itglue/upload/reports', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({org_id: orgId, files: selectedFiles})
    });

    if (d.error) { showToast(t('status_error') + ': ' + d.error, 'error'); return; }
    showToast(t('msg_uploaded_reports').replace('{count}', d.uploaded).replace('{org}', orgName) + ': ' + (d.files || []).join(', '), 'success', 8000);
    document.getElementById('itglue-upload-modal').style.display = 'none';
  } catch (e) {
    showToast(t('status_error') + ': ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = t('btn_upload');
  }
}

async function uploadToITGlue(btn) {
  // Determine upload type from card context
  const card = btn.closest('.card');
  const title = card.querySelector('.card-title')?.textContent || '';
  let uploadType = 'audit';
  if (title.includes('Tilkoblings') || title.includes('Connection') || title.includes('Sertifikat') || title.includes('Certificate')) uploadType = 'credentials';

  // First check if IT Glue is configured
  try {
    const settings = await apiFetch('/api/settings');
    if (!settings.itglue_api_key_set) {
      if (await showConfirm(t('dlg_confirm_itglue_setup_full'))) {
        openAdmin('integrations');
        setTimeout(function(){ toggleIntegConfig('itglue-config'); }, 300);
      }
      return;
    }
  } catch { showToast(t('err_check_settings_failed'), 'error'); return; }

  // Get organizations list
  if (!_itglueOrgCache) {
    btn.disabled = true;
    setButtonLabel(btn, t('msg_fetching_orgs'));
    try {
      const d = await apiFetch('/api/itglue/organizations', {method: 'POST'});
      _itglueOrgCache = d.organizations || [];
    } catch(e) {
      showToast(t('err_error_fetching_orgs').replace('{msg}', e.message), 'error');
      btn.disabled = false;
      setButtonLabel(btn, t('btn_upload_to_itglue'));
      return;
    }
  }

  // Show org picker
  const orgId = await pickITGlueOrg(_itglueOrgCache);
  if (!orgId) { btn.disabled = false; setButtonLabel(btn, t('btn_upload_to_itglue')); return; }

  btn.disabled = true;
  setButtonLabel(btn, t('btn_uploading'));

  try {
    const endpoint = uploadType === 'credentials' ? '/api/itglue/upload/credentials' : '/api/itglue/upload/audit';
    const r = await fetch(endpoint, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({org_id: orgId})
    });
    const d = await r.json();
    if (d.ok) {
      setButtonLabel(btn, t('msg_uploaded_success'));
      btn.style.color = 'var(--green)';
      setTimeout(() => { setButtonLabel(btn, t('btn_upload_to_itglue')); btn.style.color = ''; btn.disabled = false; }, 3000);
    } else {
      showToast(t('status_error') + ': ' + (d.error || t('err_unknown')), 'error');
      setButtonLabel(btn, t('btn_upload_to_itglue'));
      btn.disabled = false;
    }
  } catch(e) {
    showToast(t('status_error') + ': ' + e.message, 'error');
    setButtonLabel(btn, t('btn_upload_to_itglue'));
    btn.disabled = false;
  }
}

function pickITGlueOrg(orgs) {
  return new Promise((resolve) => {
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop open';
    backdrop.innerHTML = `
      <div class="modal" style="max-height:80vh;overflow-y:auto;">
        <div class="modal-title" data-i18n="hdr_itglue_org_picker">${t('hdr_itglue_org_picker')}</div>
        <div class="modal-desc">${t('msg_select_org_upload','Select which organization to upload data to.')}</div>
        <input class="field-input" id="itglue-org-search" type="text" placeholder="${t('placeholder_search','Search...')}" style="margin-bottom:12px;">
        <div id="itglue-org-list" style="max-height:300px;overflow-y:auto;"></div>
        <div class="modal-actions">
          <button class="btn btn-default" id="itglue-org-cancel">${t('btn_cancel','Cancel')}</button>
        </div>
      </div>`;
    document.body.appendChild(backdrop);

    const list = backdrop.querySelector('#itglue-org-list');
    const search = backdrop.querySelector('#itglue-org-search');

    function render(filter) {
      const filtered = filter ? orgs.filter(o => o.name.toLowerCase().includes(filter.toLowerCase())) : orgs;
      list.innerHTML = filtered.map(o =>
        `<div style="padding:8px 12px;border-bottom:1px solid var(--border);cursor:pointer;font-size:13px;" class="itglue-org-item" data-id="${esc(o.id)}">${esc(o.name)}</div>`
      ).join('');
    }
    render('');

    search.oninput = () => render(search.value);
    list.onclick = (e) => {
      const item = e.target.closest('.itglue-org-item');
      if (item) { document.body.removeChild(backdrop); resolve(item.dataset.id); }
    };
    backdrop.querySelector('#itglue-org-cancel').onclick = () => {
      document.body.removeChild(backdrop);
      resolve(null);
    };
  });
}

async function migrateEncryption() {
  const btn = document.getElementById('btn-migrate-encrypt');
  const result = document.getElementById('migrate-encrypt-result');
  btn.disabled = true;
  result.textContent = t('msg_encrypting');
  try {
    const d = await apiFetch('/api/encrypt/migrate', {method:'POST'});
    if (d.ok) {
      result.innerHTML = '<span style="color:var(--green);">' + t('msg_files_encrypted').replace('{count}', Number(d.files_encrypted)) + '</span>';
    } else {
      result.innerHTML = `<span style="color:var(--red);">✗ ${t('status_error')}: ${esc(d.error)}</span>`;
    }
  } catch(e) {
    result.innerHTML = `<span style="color:var(--red);">✗ ${esc(e.message)}</span>`;
  }
  btn.disabled = false;
}

// ── Tag utilities ──
var TAG_SUGGESTIONS=['Premium','Standard','Basic',t('tag_priority','Priority'),t('tag_new_customer','New customer'),t('tag_trial','Trial')];
var TAG_COLORS={'Premium':{bg:'#3fb95020',border:'#3fb95060',color:'#3fb950'},'Standard':{bg:'#4d9fb520',border:'#4d9fb560',color:'#4d9fb5'},'Basic':{bg:'#8b8b8b20',border:'#8b8b8b60',color:'#8b8b8b'},'Prioritert':{bg:'#f8514920',border:'#f8514960',color:'#f85149'},'Priority':{bg:'#f8514920',border:'#f8514960',color:'#f85149'},'Ny kunde':{bg:'#d2992220',border:'#d2992260',color:'#d29922'},'New customer':{bg:'#d2992220',border:'#d2992260',color:'#d29922'},'Proveperiode':{bg:'#a371f720',border:'#a371f760',color:'#a371f7'},'Trial':{bg:'#a371f720',border:'#a371f760',color:'#a371f7'}};
function tagPillHtml(tag){var tc=TAG_COLORS[tag]||{bg:'#58a6ff20',border:'#58a6ff50',color:'#58a6ff'};return '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:600;background:'+tc.bg+';border:1px solid '+tc.border+';color:'+tc.color+';margin-right:4px;margin-top:2px;white-space:nowrap;">'+esc(tag)+'</span>';}
function tagPillsHtml(tags){if(!tags||tags.length===0)return '';return tags.map(tagPillHtml).join('');}
async function saveCustomerTags(cid,tags){try{await apiFetch('/api/customer/tags',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer_id:cid,tags:tags})})}catch(e){console.error('save tags:',e)}}
function showTagEditor(cid,curTags){var ex=curTags?curTags.slice():[];var si=cid.replace(/[^a-zA-Z0-9_-]/g,'_');var ct=_tagEl('tag-editor-'+si);if(!ct)return;var sf=TAG_SUGGESTIONS.filter(function(s){return ex.indexOf(s)===-1});var h='<div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center;margin-bottom:8px;">';ex.forEach(function(t,i){var tc=TAG_COLORS[t]||{bg:'#58a6ff20',border:'#58a6ff50',color:'#58a6ff'};h+='<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;background:'+tc.bg+';border:1px solid '+tc.border+';color:'+tc.color+';">'+esc(t)+' <span style="cursor:pointer;font-size:14px;line-height:1;opacity:0.7;" data-click-handler="removeTagAndRefresh" data-customer-id="'+esc(cid)+'" data-index="'+i+'">&times;</span></span>'});h+='</div><div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">';h+='<input type="text" id="tag-input-'+si+'" placeholder="' + t('lbl_write_tag') + '" style="padding:4px 8px;border:1px solid var(--border);border-radius:6px;font-size:12px;background:var(--bg);color:var(--text);width:120px;" data-keydown-handler="tagEditorAddOnEnter" data-customer-id="'+esc(cid)+'">';h+='<button class="btn btn-primary" style="padding:3px 10px;font-size:11px;" data-click-handler="addTagFromInput" data-customer-id="'+esc(cid)+'">+</button></div>';if(sf.length>0){h+='<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:4px;">';sf.forEach(function(s){h+='<button class="btn btn-ghost" style="padding:2px 8px;font-size:10px;border:1px dashed var(--border);border-radius:12px;" data-click-handler="addSuggestedTag" data-customer-id="'+esc(cid)+'" data-tag="'+esc(s)+'">+ '+esc(s)+'</button>'});h+='</div>'}ct.innerHTML=h;ct.style.display='block'}
// The Kunder list and the customer page's Detaljer both carry a tag editor for
// a customer, with the same ids. The one on the page on screen is meant.
function _tagEl(id) {
  return document.querySelector('.view.active [id="' + id + '"]') || document.getElementById(id);
}
var _tagEditorData={};
function openTagEditor(cid,tags){_tagEditorData[cid]=tags?tags.slice():[];showTagEditor(cid,_tagEditorData[cid])}
function closeTagEditor(cid){var si=cid.replace(/[^a-zA-Z0-9_-]/g,'_');var c=_tagEl('tag-editor-'+si);if(c){c.innerHTML='';c.style.display='none'}delete _tagEditorData[cid]}
function addTagFromInput(cid){var si=cid.replace(/[^a-zA-Z0-9_-]/g,'_');var inp=_tagEl('tag-input-'+si);if(!inp||!inp.value.trim())return;if(!_tagEditorData[cid])_tagEditorData[cid]=[];if(_tagEditorData[cid].indexOf(inp.value.trim())===-1)_tagEditorData[cid].push(inp.value.trim());saveCustomerTags(cid,_tagEditorData[cid]).then(function(){showTagEditor(cid,_tagEditorData[cid]);refreshTagPills(cid,_tagEditorData[cid])})}
function addSuggestedTag(cid,tag){if(!_tagEditorData[cid])_tagEditorData[cid]=[];if(_tagEditorData[cid].indexOf(tag)===-1)_tagEditorData[cid].push(tag);saveCustomerTags(cid,_tagEditorData[cid]).then(function(){showTagEditor(cid,_tagEditorData[cid]);refreshTagPills(cid,_tagEditorData[cid])})}
function removeTagAndRefresh(cid,index){if(!_tagEditorData[cid])return;_tagEditorData[cid].splice(index,1);saveCustomerTags(cid,_tagEditorData[cid]).then(function(){showTagEditor(cid,_tagEditorData[cid]);refreshTagPills(cid,_tagEditorData[cid])})}
function refreshTagPills(cid,tags){var si=cid.replace(/[^a-zA-Z0-9_-]/g,'_');var el=_tagEl('tag-pills-'+si);if(el)el.innerHTML=tagPillsHtml(tags)}

// ── Manual Customer ─────────────────────────────────────────────────────────────

function openNewCustomer() {
  var modal = document.getElementById('manual-customer-modal');
  modal.style.display = 'flex';
  document.getElementById('new-cust-choices').hidden = false;
  document.getElementById('new-cust-form').hidden = true;
  document.getElementById('btn-manual-cust-save').hidden = true;
  document.getElementById('manual-cust-name').value = '';
  document.getElementById('manual-cust-domain').value = '';
  document.getElementById('manual-cust-email').value = '';
  document.getElementById('manual-cust-phone').value = '';
  document.getElementById('manual-cust-orgnum').value = '';
  document.getElementById('manual-cust-notes').value = '';
  document.getElementById('manual-cust-error').style.display = 'none';
}

function newCustomerWithM365() {
  document.getElementById('manual-customer-modal').style.display = 'none';
  startSetup();
}

function newCustomerManual() {
  document.getElementById('new-cust-choices').hidden = true;
  document.getElementById('new-cust-form').hidden = false;
  document.getElementById('btn-manual-cust-save').hidden = false;
  document.getElementById('manual-cust-name').focus();
}

async function submitManualCustomer() {
  var name = document.getElementById('manual-cust-name').value.trim();
  var errEl = document.getElementById('manual-cust-error');
  if (!name) {
    errEl.textContent = t('err_name_required');
    errEl.style.display = 'block';
    return;
  }
  errEl.style.display = 'none';
  var btn = document.getElementById('btn-manual-cust-save');
  btn.disabled = true;

  var d = await apiFetch('/api/customers/add-manual', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      name: name,
      primary_domain: document.getElementById('manual-cust-domain').value.trim(),
      contact_email: document.getElementById('manual-cust-email').value.trim(),
      contact_phone: document.getElementById('manual-cust-phone').value.trim(),
      org_number: document.getElementById('manual-cust-orgnum').value.trim(),
      notes: document.getElementById('manual-cust-notes').value.trim()
    })
  });
  btn.disabled = false;

  if (d && d.ok) {
    document.getElementById('manual-customer-modal').style.display = 'none';
    showToast(t('msg_customer_added'), 'success');
    loadCustomers();
    // Straight to the new customer's page when the server names it.
    var newId = d.customer_id || d.id || (d.customer && (d.customer._id || d.customer.customer_id));
    if (newId) openCustomerPage(newId, 'funn');
  } else if (d && d.error) {
    errEl.textContent = d.error;
    errEl.style.display = 'block';
  }
}

// ── IT Glue Import ──────────────────────────────────────────────────────────────
var _itglueImportOrgs = [];

async function openITGlueImport() {
  var modal = document.getElementById('itglue-import-modal');
  var content = document.getElementById('itglue-import-content');
  var btn = document.getElementById('btn-itglue-import');
  modal.style.display = 'flex';
  btn.disabled = true;
  content.innerHTML = '<div style="text-align:center;padding:24px;"><div class="loader" style="width:24px;height:24px;margin:0 auto 12px;"></div><span data-i18n="msg_fetching_orgs_itglue">' + t('henter_organisasjoner_fra_it_glue') + '</span></div>';
  _itglueImportOrgs = [];

  try {
    var d = await apiFetch('/api/itglue/organizations', {method: 'POST'});
    if (d.error) {
      content.innerHTML = '<div class="alert alert-error">' + esc(d.error) + '</div>';
      return;
    }
    var orgs = d.organizations || [];
    if (orgs.length === 0) {
      content.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-muted);">' + t('msg_no_orgs_found_itglue') + '</div>';
      return;
    }

    // Get existing customers to show which are already imported
    var custData = await apiFetch('/api/customers');
    var existingNames = new Set();
    if (custData && custData.customers) {
      custData.customers.forEach(function(c) { existingNames.add((c.CustomerName || '').toLowerCase()); });
    }

    var html = '<div style="margin-bottom:12px;display:flex;gap:8px;align-items:center;">';
    html += '<input type="text" id="itglue-import-search" class="field-input" placeholder="' + t('lbl_search') + '" style="flex:1;padding:6px 12px;font-size:12px;" data-input-handler="filterITGlueImport">';
    html += '<label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer;white-space:nowrap;"><input type="checkbox" id="itglue-import-select-all" data-change-handler="toggleAllITGlueImport"> ' + t('btn_select_all') + '</label>';
    html += '</div>';
    html += '<div style="max-height:350px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;">';
    html += '<table class="section-table" style="width:100%;"><thead><tr><th style="width:32px;"></th><th style="text-align:left;">' + t('lbl_organization') + '</th><th style="text-align:left;">' + t('lbl_id') + '</th><th></th></tr></thead><tbody>';

    orgs.sort(function(a, b) { return a.name.localeCompare(b.name); });
    _itglueImportOrgs = orgs;

    for (var i = 0; i < orgs.length; i++) {
      var o = orgs[i];
      var exists = existingNames.has(o.name.toLowerCase());
      html += '<tr class="itglue-import-row" data-name="' + esc(o.name.toLowerCase()) + '"' + (exists ? ' style="opacity:0.4;"' : '') + '>';
      html += '<td style="text-align:center;"><input type="checkbox" class="itglue-import-cb" data-idx="' + i + '" ' + (exists ? 'disabled title="' + esc(t('msg_already_imported')) + '"' : '') + ' data-change-handler="updateITGlueImportBtn" style="width:15px;height:15px;cursor:pointer;"></td>';
      html += '<td style="font-weight:500;">' + esc(o.name) + '</td>';
      html += '<td style="font-family:var(--mono);font-size:11px;color:var(--text-muted);">' + esc(o.id) + '</td>';
      html += '<td style="font-size:11px;color:var(--text-muted);">' + (exists ? '<span style="color:var(--green);">' + t('msg_already_exists') + '</span>' : '') + '</td>';
      html += '</tr>';
    }
    html += '</tbody></table></div>';
    content.innerHTML = html;
  } catch (e) {
    content.innerHTML = '<div class="alert alert-error">' + t('status_error') + ': ' + esc(e.message) + '</div>';
  }
}

function filterITGlueImport() {
  var q = (document.getElementById('itglue-import-search') || {}).value || '';
  q = q.toLowerCase();
  document.querySelectorAll('.itglue-import-row').forEach(function(row) {
    row.style.display = row.dataset.name.indexOf(q) >= 0 ? '' : 'none';
  });
}

function toggleAllITGlueImport(checked) {
  document.querySelectorAll('.itglue-import-cb:not(:disabled)').forEach(function(cb) {
    cb.checked = checked;
  });
  updateITGlueImportBtn();
}

function updateITGlueImportBtn() {
  var count = document.querySelectorAll('.itglue-import-cb:checked').length;
  var btn = document.getElementById('btn-itglue-import');
  btn.disabled = count === 0;
  btn.textContent = count > 0 ? t('btn_import_selected') + ' (' + count + ')' : t('btn_import_selected');
}

async function runITGlueImport() {
  var selected = [];
  document.querySelectorAll('.itglue-import-cb:checked').forEach(function(cb) {
    var idx = parseInt(cb.dataset.idx);
    if (_itglueImportOrgs[idx]) {
      selected.push({name: _itglueImportOrgs[idx].name, id: _itglueImportOrgs[idx].id});
    }
  });
  if (selected.length === 0) return;

  var btn = document.getElementById('btn-itglue-import');
  btn.disabled = true;
  btn.textContent = t('btn_importing');

  try {
    var d = await apiFetch('/api/customers/import-itglue', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({organizations: selected})
    });
    if (!d) return;
    if (d.error) {
      showToast(t('status_error') + ': ' + d.error, 'error');
      return;
    }

    var msg = t('msg_customers_imported').replace('{count}', d.imported);
    if (d.skipped > 0) msg += ' ' + t('msg_customers_skipped').replace('{count}', d.skipped);
    showToast(msg, 'success', 8000);

    document.getElementById('itglue-import-modal').style.display = 'none';
    loadCustomers();
  } catch (e) {
    showToast(t('status_error') + ': ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = t('btn_import_selected');
  }
}

// ── Customers management ────────────────────────────────────────────────────────
var _allCustomers = [];
var _customersActiveId = null;

async function loadCustomers() {
  const box = document.getElementById('customers-content');
  try {
    const [d, expiryResult] = await Promise.all([
      apiFetch('/api/customers'),
      _expiryData ? Promise.resolve(null) : apiFetch('/api/expiry/check')
    ]);
    if (!d) { box.innerHTML = '<div class="alert alert-error">' + t('err_could_not_load_customers') + '</div>'; return; }
    if (expiryResult) _expiryData = expiryResult;
    _allCustomers = d.customers || [];
    _customersActiveId = d.active_id;
    // Through the filter whatever the search box holds. This used to render
    // the whole list whenever the box was *not* empty, so a list that
    // finished loading after you typed showed every customer again.
    customersFilter();
  } catch(e) {
    box.innerHTML = `<div class="alert alert-error">${t('status_error')}: ${esc(e.message)}</div>`;
  }
}

async function exportCustomersJSON() {
  try {
    var d = await apiFetch('/api/dashboard/overview');
    if (!d || !d.customers) { showToast(t('status_error'), 'error'); return; }
    var exportData = {
      exported_at: new Date().toISOString(),
      customer_count: d.customers.length,
      customers: d.customers.map(function(c) {
        return {
          customer_id: c.customer_id,
          customer_name: c.customer_name,
          primary_domain: c.primary_domain,
          has_metrics: c.has_metrics,
          last_audit: c.last_audit,
          tags: c.tags,
          metrics: c.metrics,
        };
      })
    };
    var blob = new Blob([JSON.stringify(exportData, null, 2)], {type: 'application/json'});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = 'msp_customers_' + new Date().toISOString().substring(0,10) + '.json';
    a.click(); URL.revokeObjectURL(url);
    showToast(t('msg_exported','Exported') + ' ' + d.customers.length + ' ' + t('nav_customers').toLowerCase(), 'success', 3000);
  } catch(e) { showToast(t('status_error') + ': ' + e.message, 'error'); }
}

var _bulkSelectedCustomers = [];

// Favorites (stored in localStorage)
function _getFavorites() { try { return JSON.parse(localStorage.getItem('sybr_favorites') || '[]'); } catch(e) { return []; } }
function _setFavorites(arr) { localStorage.setItem('sybr_favorites', JSON.stringify(arr)); }
function toggleFavorite(customerId) {
  var favs = _getFavorites();
  var idx = favs.indexOf(customerId);
  if (idx >= 0) favs.splice(idx, 1); else favs.push(customerId);
  _setFavorites(favs);
  loadCustomers();
}

function toggleBulkCustomer(customerId, cb) {
  if (cb.checked) { if (_bulkSelectedCustomers.indexOf(customerId)===-1) _bulkSelectedCustomers.push(customerId); }
  else { _bulkSelectedCustomers = _bulkSelectedCustomers.filter(function(id){return id!==customerId}); }
  var bar = document.getElementById('customers-bulk-bar');
  if (_bulkSelectedCustomers.length > 0) {
    bar.style.display = 'flex';
    document.getElementById('customers-bulk-count').textContent = _bulkSelectedCustomers.length + ' ' + t('status_selected','valgt');
  } else {
    bar.style.display = 'none';
  }
}

function clearBulkSelection() {
  _bulkSelectedCustomers = [];
  document.querySelectorAll('.customer-bulk-cb').forEach(function(cb){cb.checked=false});
  document.getElementById('customers-bulk-bar').style.display = 'none';
}

async function bulkTagCustomers() {
  var tag = prompt(t('msg_enter_tag','Enter tag name:'));
  if (!tag || !tag.trim()) return;
  tag = tag.trim();
  var count = _bulkSelectedCustomers.length;
  for (var i=0; i<_bulkSelectedCustomers.length; i++) {
    // Get existing tags, add new one if not present
    var cid = _bulkSelectedCustomers[i];
    try {
      // Find customer in cached data to get current tags
      var existing = [];
      if (_allCustomers) {
        var c = _allCustomers.find(function(x){return x._id === cid});
        if (c) existing = c._tags || [];
      }
      if (existing.indexOf(tag) === -1) existing.push(tag);
      await apiFetch('/api/customer/tags', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({customer_id:cid, tags:existing})});
    } catch(e) { console.warn('Bulk tag update failed for', cid, e); }
  }
  clearBulkSelection();
  loadCustomers();
  showToast(t('msg_tag_added','Tag added to') + ' ' + count + ' ' + t('nav_customers').toLowerCase(), 'success', 2000);
}

async function bulkDeleteCustomers() {
  // Retirement affects multiple registrations; require explicit acknowledgement.
  var sentinel = t('lbl_type_archive_sentinel', 'ARKIVER');
  var n = _bulkSelectedCustomers.length;
  if (!await showTypedConfirm(
    sentinel,
    t('dlg_confirm_bulk_delete_customers', 'Arkiver {n} kunder?').replace('{n}', n),
    t('msg_customer_archive_retention','Kunderegistreringen arkiveres og aktive nøkkelringhemmeligheter fjernes. Audits, rapporter, sertifikater og historikk beholdes. Full sletting gjøres via driftsprosedyren.')
  )) return;
  for (var i=0; i<_bulkSelectedCustomers.length; i++) {
    var archived = await apiFetch('/api/customers/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({customer_id:_bulkSelectedCustomers[i]})});
    if (!archived || !archived.ok) { loadCustomers(); return; }
  }
  clearBulkSelection();
  loadCustomers();
  showToast(t('msg_saved','OK'), 'success', 2000);
}

function customersFilter() {
  var q = (document.getElementById('customers-search').value || '').toLowerCase();
  var filtered = _allCustomers;
  if (q) {
    filtered = _allCustomers.filter(function(c) {
      return (c.CustomerName || '').toLowerCase().indexOf(q) !== -1
        || (c.PrimaryDomain || '').toLowerCase().indexOf(q) !== -1
        || (c.TenantId || '').toLowerCase().indexOf(q) !== -1
        || (c._tags || []).some(function(tag) { return tag.toLowerCase().indexOf(q) !== -1; });
    });
  }
  var countEl = document.getElementById('customers-count');
  if (countEl) {
    countEl.textContent = q ? filtered.length + ' / ' + _allCustomers.length + ' ' + t('nav_customers').toLowerCase() : _allCustomers.length + ' ' + t('nav_customers').toLowerCase();
  }
  renderCustomers(filtered, _customersActiveId);
}

function renderCustomers(customers, activeId) {
  const box = document.getElementById('customers-content');
  // A search that matches nothing is not a fresh install: the getting-started
  // steps below would tell someone with fifty customers to add their first.
  if (customers.length === 0 && _allCustomers.length > 0) {
    box.innerHTML = '<div class="empty-state-inline"><div class="empty-title">' + esc(t('msg_no_results')) + '</div></div>';
    return;
  }
  if (customers.length === 0) {
    box.innerHTML = `
      <div class="empty-state">
        <div class="empty-title" style="margin-bottom:var(--space-6);">${t('onboarding_title','Kom i gang med Sybr HUB')}</div>
        <div style="display:flex;gap:var(--space-6);justify-content:center;flex-wrap:wrap;margin-bottom:var(--space-6);">
          <div style="text-align:center;max-width:180px;">
            <div style="width:48px;height:48px;line-height:48px;border-radius:50%;background:var(--blue);color:#fff;font-weight:800;font-size:var(--font-lg);margin:0 auto var(--space-3);">1</div>
            <div style="font-size:var(--font-sm);font-weight:600;">${t('onboarding_step1_title','Legg til kunde')}</div>
            <div style="font-size:var(--font-xs);color:var(--text-muted);margin-top:var(--space-1);">${t('onboarding_step1_desc','Klikk \"+ Ny kunde\" og følg veiviseren')}</div>
          </div>
          <div style="text-align:center;max-width:180px;">
            <div style="width:48px;height:48px;line-height:48px;border-radius:50%;background:var(--blue);color:#fff;font-weight:800;font-size:var(--font-lg);margin:0 auto var(--space-3);">2</div>
            <div style="font-size:var(--font-sm);font-weight:600;">${t('onboarding_step2_title','Sett opp M365')}</div>
            <div style="font-size:var(--font-xs);color:var(--text-muted);margin-top:var(--space-1);">${t('onboarding_step2_desc')}</div>
          </div>
          <div style="text-align:center;max-width:180px;">
            <div style="width:48px;height:48px;line-height:48px;border-radius:50%;background:var(--blue);color:#fff;font-weight:800;font-size:var(--font-lg);margin:0 auto var(--space-3);">3</div>
            <div style="font-size:var(--font-sm);font-weight:600;">${t('onboarding_step3_title','Kjør audit')}</div>
            <div style="font-size:var(--font-xs);color:var(--text-muted);margin-top:var(--space-1);">${t('onboarding_step3_desc')}</div>
          </div>
        </div>
        <button data-write class="btn btn-primary btn-lg" data-click-handler="startSetup">${t('btn_new_customer','+ Ny kunde')}</button>
      </div>`;
    return;
  }

  // Sort favorites first
  var favs = _getFavorites();
  customers.sort(function(a,b) {
    var fa = favs.indexOf(a._id) >= 0 ? 0 : 1;
    var fb = favs.indexOf(b._id) >= 0 ? 0 : 1;
    return fa - fb;
  });

  let html = '';
  for (const c of customers) {
    const isFav = favs.indexOf(c._id) >= 0;
    const isGdap = c.AuthMode === 'gdap';
    const gdapBadge = isGdap ? '<span style="background:linear-gradient(135deg,#0078d4,#00bcf2);color:#fff;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:600;">GDAP</span>' : '';
    const expiryBadge = isGdap ? '' : getExpiryBadgeForCustomer(c._id);
    const notesBadge = c._has_notes ? '<span style="background:var(--blue-dark);color:var(--blue);padding:2px 8px;border-radius:12px;font-size:11px;border:1px solid rgba(77,159,181,0.3);">' + t('lbl_notes','Notat') + '</span>' : '';
    const cTags = c._tags || [];
    const safeId = c._id.replace(/[^a-zA-Z0-9_-]/g, '_');

    // Find metrics from overview cache
    var _om = null;
    if (_overviewData && _overviewData.customers) {
      _om = _overviewData.customers.find(function(oc){ return oc.customer_id === c._id; });
    }
    var hasMetrics = _om && _om.has_metrics;
    var grade = hasMetrics ? (_om.metrics.risk_grade || '-') : '';
    var gradeColor = {A:'#3fb950',B:'#4d9fb5',C:'#d29922',D:'#f85149',F:'#8b0000'}[grade] || 'var(--text-dim)';
    var mfaPct = hasMetrics && metricPct(_om.metrics.mfa_coverage_pct) !== null ? metricPct(_om.metrics.mfa_coverage_pct) + '%' : '';
    var riskScore = hasMetrics && _om.metrics.risk_score !== undefined ? _om.metrics.risk_score : '';
    var configured = isGdap ? !!c.TenantId : !!(c.TenantId && c.ClientId);
    var statusDot = configured ? (hasMetrics ? '<span style="width:8px;height:8px;border-radius:50%;background:' + gradeColor + ';display:inline-block;"></span>' : '<span style="width:8px;height:8px;border-radius:50%;background:var(--text-dim);display:inline-block;" title="' + t('tip_no_audit_run','No audit run') + '"></span>') : '<span style="width:8px;height:8px;border-radius:50%;background:var(--orange);display:inline-block;" title="' + t('tip_not_configured','Not configured') + '"></span>';

    html += `
      <div class="card card-clickable cust-card" data-click-handler="overviewSelectCustomer" data-id="${esc(c._id)}">
        <div class="cust-card-row">
          <input type="checkbox" class="customer-bulk-cb" data-click-handler="customerCardToggleBulk" data-id="${esc(c._id)}" style="width:16px;height:16px;flex-shrink:0;cursor:pointer;accent-color:var(--blue);">
          <span class="hover-scale" data-click-handler="customerCardToggleFavorite" data-id="${esc(c._id)}" style="cursor:pointer;font-size:18px;flex-shrink:0;transition:transform var(--duration-fast);">${isFav ? '\u2605' : '\u2606'}</span>
          ${grade ? '<div style="width:42px;height:42px;line-height:42px;border-radius:var(--radius-lg);font-weight:800;font-size:var(--font-lg);color:#fff;background:'+gradeColor+';text-align:center;flex-shrink:0;">'+esc(grade)+'</div>' : '<div style="width:42px;height:42px;line-height:42px;border-radius:var(--radius-lg);font-size:var(--font-lg);color:var(--text-dim);background:var(--bg);text-align:center;flex-shrink:0;border:1px dashed var(--border);">?</div>'}
          <div class="cust-card-main">
            <div class="cust-card-name">
              ${statusDot}
              <span class="cust-card-name-text">${esc(c.CustomerName || t('lbl_unknown','Unknown'))}</span>
              ${gdapBadge} ${expiryBadge} ${notesBadge}
            </div>
            <div class="cust-card-domain">${esc(c.PrimaryDomain || '')}</div>
            <div class="cust-card-metrics">
              ${riskScore !== '' ? '<span>' + t('lbl_score_prefix','Score:') + ' <strong style="color:var(--text);">' + esc(String(riskScore)) + '</strong></span>' : ''}
              ${mfaPct ? '<span>' + t('lbl_mfa_prefix','MFA:') + ' <strong style="color:var(--text);">' + mfaPct + '</strong></span>' : ''}
              ${_om && _om.last_audit ? '<span>' + t('lbl_last_prefix','Last:') + ' <strong style="color:var(--text);">' + esc(formatRunName(_om.last_audit, true)) + '</strong></span>' : ''}
              <span id="tag-pills-${safeId}" class="cust-card-tags">${tagPillsHtml(cTags)}</span>
            </div>
          </div>
          <div class="cust-card-actions" data-click-handler="stopPropagation">
            <button class="btn btn-ghost btn-sm" style="color:var(--text-dim);" data-click-handler="deleteCustomer" data-id="${esc(c._id)}" data-name="${esc(c.CustomerName)}" title="${t('btn_archive','Archive')}">${t('btn_archive','Archive')}</button>
          </div>
        </div>
        <div id="tag-editor-${safeId}" style="display:none;margin-top:8px;padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:8px;"></div>
      </div>`;
  }
  box.innerHTML = html;
}

async function deleteCustomer(customerId, name) {
  if (!await showTypedConfirm(
    name,
    t('dlg_confirm_delete_customer').replace('{name}', name),
    t('msg_customer_archive_retention','Kunderegistreringen arkiveres og aktive nøkkelringhemmeligheter fjernes. Audits, rapporter, sertifikater og historikk beholdes. Full sletting gjøres via driftsprosedyren.')
  )) return;
  try {
    await apiFetch('/api/customers/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({customer_id: customerId})
    });
    loadCustomers();
  } catch(e) { showToast(t('status_error') + ': ' + e.message, 'error'); }
}

// ── Overview column picker + quick-pill state (frame 1b) ─────────────────────
function _overviewColPrefs() {
  try { return JSON.parse(localStorage.getItem('sybr_overview_cols') || '{}') || {}; } catch (e) { return {}; }
}
function applyOverviewColumnPrefs() {
  var prefs = _overviewColPrefs();
  ['health', 'users', 'trend', 'tags'].forEach(function(col) {
    var show = !!prefs[col];
    document.querySelectorAll('[data-optcol="' + col + '"]').forEach(function(el) { el.classList.toggle('col-hidden', !show); });
    var cb = document.querySelector('#overview-colpick-menu input[data-col="' + col + '"]');
    if (cb) cb.checked = show;
  });
}
function toggleOverviewColumn(col, show) {
  var prefs = _overviewColPrefs();
  prefs[col] = !!show;
  try { localStorage.setItem('sybr_overview_cols', JSON.stringify(prefs)); } catch (e) { /* private mode */ }
  document.querySelectorAll('[data-optcol="' + col + '"]').forEach(function(el) { el.classList.toggle('col-hidden', !show); });
}
function toggleOverviewColpick(e) {
  if (e) e.stopPropagation();
  var menu = document.getElementById('overview-colpick-menu');
  if (!menu) return;
  if (menu.classList.toggle('open')) {
    setTimeout(function() { document.addEventListener('click', _closeOverviewColpickOutside); }, 0);
  } else {
    document.removeEventListener('click', _closeOverviewColpickOutside);
  }
}
function _closeOverviewColpickOutside(e) {
  var wrap = document.getElementById('overview-colpick');
  if (wrap && !wrap.contains(e.target)) {
    var menu = document.getElementById('overview-colpick-menu');
    if (menu) menu.classList.remove('open');
    document.removeEventListener('click', _closeOverviewColpickOutside);
  }
}
function _updateOverviewQuickPills() {
  var qf = window._quickFilter || 'all';
  [['qp-all', 'all'], ['qp-problems', 'problems'], ['qp-expiring', 'expiring']].forEach(function(pair) {
    var el = document.getElementById(pair[0]);
    if (el) el.classList.toggle('active', qf === pair[1]);
  });
}

async function _loadSparklines() {
  try {
    // Use pre-loaded trend data from /api/dashboard/trends (loaded in parallel with overview)
    var byCustomer = window._overviewTrends || {};
    // If no pre-loaded trends, try fetching
    if (!Object.keys(byCustomer).length) {
      var d = await apiFetch('/api/dashboard/trends');
      if (d && d.trends) byCustomer = d.trends;
    }
    if (!Object.keys(byCustomer).length) return;
    // Convert trend objects to score arrays
    var scoreMap = {};
    Object.keys(byCustomer).forEach(function(cid) {
      var points = byCustomer[cid];
      if (Array.isArray(points)) {
        scoreMap[cid] = points.map(function(p) { return typeof p === 'number' ? p : (p.score || 0); });
      }
    });
    Object.keys(scoreMap).forEach(function(cid) {
      var el = document.getElementById('spark-' + cid.replace(/[^a-zA-Z0-9_-]/g, '_'));
      if (!el) return;
      var scores = scoreMap[cid];
      if (scores.length < 2) { el.innerHTML = '<span style="color:var(--text-dim);font-size:10px;">—</span>'; return; }
      // Build SVG sparkline
      var w = 72, h = 24, pad = 2;
      var min = Math.min.apply(null, scores), max = Math.max.apply(null, scores);
      var range = max - min || 1;
      var pts = scores.map(function(s, i) {
        var x = pad + (i / (scores.length - 1)) * (w - 2*pad);
        var y = h - pad - ((s - min) / range) * (h - 2*pad);
        return x.toFixed(1) + ',' + y.toFixed(1);
      });
      var last = scores[scores.length - 1];
      var color = last >= 80 ? '#3fb950' : last >= 60 ? '#4d9fb5' : last >= 40 ? '#d29922' : '#f85149';
      el.innerHTML = '<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'">'
        + '<polyline points="'+pts.join(' ')+'" fill="none" stroke="'+color+'" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        + '<circle cx="'+pts[pts.length-1].split(',')[0]+'" cy="'+pts[pts.length-1].split(',')[1]+'" r="2" fill="'+color+'"/>'
        + '</svg>';
    });
  } catch(e) { /* sparklines are non-critical */ }
}

// ── Bulk Audit ──────────────────────────────────────────────────────────────
// ── Dashboard Excel Export & Clipboard Copy ─────────────────────────────────
async function exportDashboardExcel() {
  try {
    const r = await fetch('/api/export/excel', {method: 'POST'});
    if (!r.ok) { showToast(t('err_export_failed'), 'error'); return; }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const disp = r.headers.get('Content-Disposition') || '';
    const m = disp.match(/filename="?([^"]+)"?/);
    a.download = m ? m[1] : 'dashboard_export.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch(e) { showToast(t('err_export_failed') + ': ' + e.message, 'error'); }
}

// The button is passed in. This read the global `event` inside the clipboard
// promise's callback, where it is undefined, so every successful copy threw
// and reported "could not copy" instead of showing the copied state.
function copyOverviewToClipboard(button) {
  if (!_overviewData || !_overviewData.customers) { showToast(t('msg_no_data_available'), 'warning'); return; }
  const customers = _overviewData.customers;
  const headers = ['Customer', 'Domain', 'Risk Grade', 'Risk Score', 'MFA Coverage %', 'Secure Score %', 'Total Users', 'Users Without MFA', 'CA Policies', 'Intune Compliance %', 'Global Admins', 'Last Audit Date', 'Tags'];
  let tsv = headers.join('\t') + '\n';
  for (const c of customers) {
    const m = c.metrics || {};
    const hasM = c.has_metrics;
    const row = [
      c.customer_name || '',
      c.primary_domain || '',
      hasM ? (m.risk_grade || '') : '',
      hasM && m.risk_score !== undefined ? m.risk_score : '',
      hasM && metricPct(m.mfa_coverage_pct, 1) !== null ? metricPct(m.mfa_coverage_pct, 1) : '',
      hasM && metricPct(m.secure_score_pct, 1) !== null ? metricPct(m.secure_score_pct, 1) : '',
      hasM && m.total_users !== undefined ? m.total_users : '',
      hasM && m.users_no_mfa !== undefined ? m.users_no_mfa : '',
      hasM && m.ca_policies_enabled !== undefined ? m.ca_policies_enabled : '',
      hasM && metricPct(m.intune_compliance_pct, 1) !== null ? metricPct(m.intune_compliance_pct, 1) : '',
      hasM && m.admin_roles_ga_count !== undefined ? m.admin_roles_ga_count : '',
      c.last_audit || '',
      (c.tags || []).join(', '),
    ];
    tsv += row.join('\t') + '\n';
  }
  navigator.clipboard.writeText(tsv).then(function() {
    var btn = button && button.closest('button');
    if (btn) { var orig = btn.textContent; btn.textContent = t('btn_copied'); setTimeout(function(){ btn.textContent = orig; }, 1500); }
  }).catch(function(e) { showToast(t('err_could_not_copy').replace('{msg}', e.message), 'error'); });
}

var _bulkAuditEventSource = null;
function startBulkAudit() {
  if (_bulkAuditEventSource) { showToast(t('err_bulk_audit_already_running'), 'warning'); return; }
  var btn = document.getElementById('bulk-audit-btn');
  if (btn) { btn.disabled = true; btn.textContent = t('status_running'); }
  var panel = document.getElementById('bulk-audit-panel');
  panel.style.display = 'block';
  panel.innerHTML = '<div class="card" style="padding:20px;margin-bottom:24px;" id="bulk-progress-card">' +
    '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">' +
    '<div style="font-weight:700;font-size:15px;">' + t('bulk_audit') + '</div>' +
    '<button class="btn btn-ghost" id="bulk-cancel-btn" data-click-handler="cancelBulkAudit" style="font-size:12px;padding:4px 10px;">' + t('avbryt') + '</button></div>' +
    '<div id="bulk-overall-status" style="font-size:13px;color:var(--text-muted);margin-bottom:12px;">' + t('starter') + '</div>' +
    '<div style="background:var(--bg);border-radius:6px;height:8px;overflow:hidden;margin-bottom:8px;">' +
    '<div id="bulk-overall-bar" style="height:100%;width:0%;background:var(--blue);transition:width 0.3s;border-radius:6px;"></div></div>' +
    '<div id="bulk-customer-status" style="font-size:13px;color:var(--text-muted);margin-bottom:8px;"></div>' +
    '<div style="background:var(--bg);border-radius:6px;height:6px;overflow:hidden;margin-bottom:16px;">' +
    '<div id="bulk-customer-bar" style="height:100%;width:0%;background:#4d9fb5;transition:width 0.3s;border-radius:6px;"></div></div>' +
    '<div id="bulk-results-table" style="display:none;">' +
    '<div style="font-weight:600;font-size:13px;margin-bottom:8px;">' + t('resultater') + '</div>' +
    '<table style="width:100%;border-collapse:collapse;font-size:12px;">' +
    '<thead><tr style="border-bottom:1px solid var(--border);">' +
    '<th style="text-align:left;padding:6px 8px;color:var(--text-muted);">' + t('kunde') + '</th>' +
    '<th style="text-align:center;padding:6px 8px;color:var(--text-muted);">' + t('grad') + '</th>' +
    '<th style="text-align:center;padding:6px 8px;color:var(--text-muted);">' + t('score') + '</th>' +
    '<th style="text-align:center;padding:6px 8px;color:var(--text-muted);">' + t('seksjoner_2') + '</th>' +
    '<th style="text-align:center;padding:6px 8px;color:var(--text-muted);">' + t('status') + '</th>' +
    '</tr></thead><tbody id="bulk-results-tbody"></tbody></table></div></div>';
  var _ari_b = document.getElementById('audit-running-indicator');
  if (_ari_b) { _ari_b.textContent = ''; _ari_b.innerHTML = '<span style="width:8px;height:8px;border-radius:50%;background:#fff;display:inline-block;"></span> ' + t('msg_bulk_audit_running'); _ari_b.onclick = function(){ showView('overview'); }; _ari_b.style.display = 'flex'; }
  var totalCustomers = 0, completedCustomers = 0, customerSectionsDone = 0, customerSectionsTotal = 0;
  fetch('/api/audit/bulk', {method:'POST'}).then(async function(resp) {
    if (!resp.ok) { document.getElementById('bulk-overall-status').innerHTML = '<span style="color:var(--red)">HTTP '+Number(resp.status)+'</span>'; return; }
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buf = '';
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buf += decoder.decode(chunk.value, {stream:true});
      var lines = buf.split('\n'); buf = lines.pop();
      for (var li = 0; li < lines.length; li++) {
        if (!lines[li].startsWith('data: ')) continue;
        try {
        var d = JSON.parse(lines[li].slice(6));
    if (d.type === 'bulk_started') {
      totalCustomers = d.total_customers;
      var statusText = t('audit_customers_done').replace('{done}', '0').replace('{total}', totalCustomers);
      if (d.skipped_unconfigured > 0) statusText += ' · ' + t('msg_skipped_unconfigured').replace('{count}', d.skipped_unconfigured);
      document.getElementById('bulk-overall-status').textContent = statusText;
    } else if (d.type === 'customer_start') {
      customerSectionsDone = 0; customerSectionsTotal = 0;
      document.getElementById('bulk-customer-status').textContent = t('audit_running_customer').replace('{customer}', d.customer).replace('{index}', d.index + 1).replace('{total}', d.total);
      var _bcb = document.getElementById('bulk-customer-bar'); if (_bcb) _bcb.style.width = '0%';
    } else if (d.type === 'progress') {
      if (d.status === 'done' || d.status === 'failed' || d.status === 'skipped') customerSectionsDone++;
      if (d.status === 'running') customerSectionsTotal = Math.max(customerSectionsTotal, customerSectionsDone + 5);
      var custPct = customerSectionsTotal > 0 ? Math.min(95, Math.round((customerSectionsDone / customerSectionsTotal) * 100)) : 0;
      var _bcb2 = document.getElementById('bulk-customer-bar'); if (_bcb2) _bcb2.style.width = custPct + '%';
      document.getElementById('bulk-customer-status').innerHTML = t('audit_running_customer').replace('{customer}', '<b>' + esc(d.customer) + '</b>').replace('{index}', Number(d.index) + 1).replace('{total}', Number(d.total)) + ' &mdash; ' + esc(d.name) + ' <span style="color:var(--text-dim);">' + esc(d.detail) + '</span>';
    } else if (d.type === 'customer_done') {
      completedCustomers++;
      var overallPct = Math.round((completedCustomers / totalCustomers) * 100);
      document.getElementById('bulk-overall-bar').style.width = overallPct + '%';
      document.getElementById('bulk-overall-status').textContent = t('audit_customers_done').replace('{done}', completedCustomers).replace('{total}', totalCustomers);
      var _bcb3 = document.getElementById('bulk-customer-bar'); if (_bcb3) _bcb3.style.width = '100%';
      var gradeColors = {A:'#3fb950', B:'#4d9fb5', C:'#d29922', D:'#f85149', F:'#8b0000'};
      var tbody = document.getElementById('bulk-results-tbody');
      document.getElementById('bulk-results-table').style.display = 'block';
      var tr = document.createElement('tr');
      tr.style.borderBottom = '1px solid var(--border)';
      tr.innerHTML = '<td style="padding:6px 8px;font-weight:600;">' + esc(d.customer) + '</td>' +
        '<td style="text-align:center;padding:6px 8px;"><span style="display:inline-block;width:26px;height:26px;line-height:26px;border-radius:4px;font-weight:800;font-size:13px;color:#fff;background:' + (gradeColors[d.grade] || 'var(--text-muted)') + ';">' + esc(d.grade || '-') + '</span></td>' +
        '<td style="text-align:center;padding:6px 8px;">' + esc(d.risk_score || '-') + '</td>' +
        '<td style="text-align:center;padding:6px 8px;">' + Number(d.sections_done) + '/' + Number(d.sections_total) + '</td>' +
        '<td style="text-align:center;padding:6px 8px;color:var(--green);font-weight:600;">OK</td>';
      tbody.appendChild(tr);
    } else if (d.type === 'customer_error' || d.type === 'customer_skip') {
      completedCustomers++;
      document.getElementById('bulk-overall-bar').style.width = Math.round((completedCustomers / totalCustomers) * 100) + '%';
      document.getElementById('bulk-overall-status').textContent = t('audit_customers_done').replace('{done}', completedCustomers).replace('{total}', totalCustomers);
      var tbody2 = document.getElementById('bulk-results-tbody');
      document.getElementById('bulk-results-table').style.display = 'block';
      var tr2 = document.createElement('tr');
      tr2.style.borderBottom = '1px solid var(--border)';
      tr2.innerHTML = '<td style="padding:6px 8px;font-weight:600;">' + esc(d.customer) + '</td>' +
        '<td style="text-align:center;padding:6px 8px;">-</td><td style="text-align:center;padding:6px 8px;">-</td>' +
        '<td style="text-align:center;padding:6px 8px;">-</td>' +
        '<td style="text-align:center;padding:6px 8px;color:var(--red);font-weight:600;" title="' + esc(d.error || d.reason || '') + '">' + (d.type === 'customer_skip' ? t('status_skipped') : t('status_error')) + '</td>';
      tbody2.appendChild(tr2);
    } else if (d.type === 'bulk_done') {
      document.getElementById('bulk-overall-bar').style.width = '100%';
      document.getElementById('bulk-overall-bar').style.background = 'var(--green)';
      document.getElementById('bulk-overall-status').innerHTML = '<span style="color:var(--green);font-weight:700;">' + t('audit_finished').replace('{count}', completedCustomers) + '</span>';
      document.getElementById('bulk-customer-status').textContent = '';
      document.getElementById('bulk-cancel-btn').style.display = 'none';
      finishBulkAudit();
    } else if (d.type === 'error') {
      var errHtml = '<span style="color:var(--red);font-weight:700;">' + t('status_error') + ': ' + esc(d.msg) + '</span>';
      if (d.traceback) {
        errHtml += '<pre style="margin-top:10px;padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;font-size:11px;color:var(--red);overflow-x:auto;white-space:pre-wrap;text-align:left;">' + esc(d.traceback) + '</pre>';
      }
      document.getElementById('bulk-overall-status').innerHTML = errHtml;
      var cancelBtn = document.getElementById('bulk-cancel-btn');
      if (cancelBtn) cancelBtn.style.display = 'none';
      var _ari_be = document.getElementById('audit-running-indicator');
      if (_ari_be) _ari_be.style.display = 'none';
      var btn2 = document.getElementById('bulk-audit-btn');
      if (btn2) { btn2.disabled = false; btn2.textContent = t('btn_run_all_customers'); }
    }
      } catch(_e) {}
    }
  }
}).catch(function(e) {
    var statusEl = document.getElementById('bulk-overall-status');
    if (statusEl) statusEl.innerHTML = '<span style="color:var(--red);">' + t('err_lost_connection') + '</span>';
    finishBulkAudit();
  });
}
function cancelBulkAudit() {
  if (_bulkAuditEventSource) { _bulkAuditEventSource.close(); _bulkAuditEventSource = null; }
  document.getElementById('bulk-overall-status').innerHTML = '<span style="color:var(--orange);">' + t('status_cancelled') + '</span>';
  document.getElementById('bulk-customer-status').textContent = '';
  finishBulkAudit();
}
function finishBulkAudit() {
  if (_bulkAuditEventSource) { _bulkAuditEventSource.close(); _bulkAuditEventSource = null; }
  var btn = document.getElementById('bulk-audit-btn');
  if (btn) { btn.disabled = false; btn.textContent = t('btn_run_all_customers'); }
  var _ari_f = document.getElementById('audit-running-indicator');
  if (_ari_f) _ari_f.style.display = 'none';
}

// Opens a customer's page, on Funn. Kept by this name: the Kunder list, the
// Oversikt rows and the palette all open customers through it.
function overviewSelectCustomer(customerId) {
  return openCustomerPage(customerId, 'funn');
}
