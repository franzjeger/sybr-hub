import {navOpenCustomerPage as openCustomerPage} from './app-navigation.js';
import {navOpenAdmin as openAdmin} from './app-navigation.js';
import {toggleIntegConfig} from './app-forms.js';
// ═══════════════════════════════════════════════════════════════════
// CUSTOMERS — notes, expiry, IT Glue, tags, management & switcher
// ═══════════════════════════════════════════════════════════════════

import {esc} from './app-esc.js';
import {_lang, t} from './app-i18n.js';
import {icon} from './app-icons.js';
import {registerUiHandlers} from './app-handlers.js';
import {_allCustomers, _overviewData, setAllCustomers} from './app-state.js';
import {formatRunName, metricPct, toneClass} from './app-format.js';
import {setButtonLabel, showConfirm, showToast, showTypedConfirm} from './app-ui.js';
import {apiFetch} from './app-api.js';
import {navShowView as showView} from './app-navigation.js';

import {startSetup} from './app-setup.js';



registerUiHandlers({
  // IT Glue organisation picker, upload and import dialogs.
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

export function renderExpiryBanner(d) {
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

// The customer whose reports the open upload dialog sends.
var _itglueUploadCustomerId = null;

export async function uploadReportsToITGlue(customerId) {
  if (!customerId) return;
  _itglueUploadCustomerId = customerId;
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
  content.innerHTML = '<div class="text-center p-6"><div class="loader loader-lg mx-auto mt-0 mb-3"></div>' + t('msg_fetching_reports_orgs') + '</div>';

  try {
    // Fetch available reports and orgs in parallel
    var [reportsResp, orgsResp, filesResp] = await Promise.all([
      apiFetch('/api/itglue/available-reports?customer_id=' + encodeURIComponent(customerId)),
      _itglueOrgCache ? Promise.resolve({organizations: _itglueOrgCache}) : apiFetch('/api/itglue/organizations', {method:'POST'}),
      apiFetch('/api/customer/' + encodeURIComponent(customerId) + '/files')
    ]);
    if (_itglueUploadCustomerId !== customerId) return;

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
    html += '<div class="subhead">' + t('hdr_select_reports') + '</div>';
    html += '<div class="flex gap-2 items-center mb-2">';
    html += '<label class="text-sm cursor-pointer"><input type="checkbox" id="itglue-upload-select-all" data-change-handler="itglueUploadSelectAll" checked> ' + t('btn_select_all') + '</label>';
    html += '</div>';
    html += '<div class="max-h-sm overflow-y-auto border rounded mb-4">';
    for (let i = 0; i < files.length; i++) {
      var f = files[i];
      var ficon = f.name.endsWith('.pdf') ? icon('document',14) : icon('globe',14);
      html += '<label class="flex items-center gap-2 py-2 px-3 cursor-pointer border-b text-sm">';
      html += '<input type="checkbox" class="itglue-file-cb checkbox" value="' + esc(f.name) + '" checked data-change-handler="updateITGlueUploadBtn">';
      html += ficon + ' <span class="flex-1">' + esc(f.name) + '</span>';
      html += '<span class="text-muted">' + esc(f.size) + '</span>';
      html += '</label>';
    }
    html += '</div>';

    // Step 2: Org picker
    html += '<div class="subhead">' + t('hdr_select_org') + '</div>';
    html += '<input type="text" id="itglue-upload-org-search" class="field-input mb-2 py-2 px-3 text-sm" placeholder="' + t('lbl_search_org') + '" data-input-handler="filterITGlueUploadOrgs">';
    html += '<div class="max-h-sm overflow-y-auto border rounded">';
    for (let i = 0; i < orgs.length; i++) {
      var matched = (i === bestOrgIdx);
      html += '<label class="itglue-upload-org-row picker-row' + (matched ? ' is-match' : '') + '" data-name="' + esc(orgs[i].name.toLowerCase()) + '">';
      html += '<input type="radio" class="checkbox" name="itglue-upload-org" value="' + esc(orgs[i].id) + '" data-orgname="' + esc(orgs[i].name) + '" ' + (matched ? 'checked' : '') + ' data-change-handler="updateITGlueUploadBtn">';
      html += '<span class="text-sm">' + esc(orgs[i].name) + '</span>';
      if (matched) html += '<span class="ml-auto text-2xs text-success fw-semibold">' + t('msg_recommended') + '</span>';
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

export async function executeITGlueUpload() {
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
      body: JSON.stringify({customer_id: _itglueUploadCustomerId, org_id: orgId, files: selectedFiles})
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

export async function uploadToITGlue(btn, customerId) {
  if (!customerId) return;
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
      body: JSON.stringify({customer_id: customerId, org_id: orgId})
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
      <div class="modal">
        <div class="modal-title" data-i18n="hdr_itglue_org_picker">${t('hdr_itglue_org_picker')}</div>
        <div class="modal-desc">${t('msg_select_org_upload','Select which organization to upload data to.')}</div>
        <input class="field-input mb-3" id="itglue-org-search" type="text" placeholder="${t('placeholder_search','Search...')}">
        <div id="itglue-org-list" class="max-h-md overflow-y-auto"></div>
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
        `<div class="itglue-org-item py-2 px-3 border-b cursor-pointer text-ui" data-id="${esc(o.id)}">${esc(o.name)}</div>`
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

export async function migrateEncryption() {
  const btn = document.getElementById('btn-migrate-encrypt');
  const result = document.getElementById('migrate-encrypt-result');
  btn.disabled = true;
  result.textContent = t('msg_encrypting');
  try {
    const d = await apiFetch('/api/encrypt/migrate', {method:'POST'});
    if (d.ok) {
      result.innerHTML = '<span class="text-success">' + t('msg_files_encrypted').replace('{count}', Number(d.files_encrypted)) + '</span>';
    } else {
      result.innerHTML = `<span class="text-danger">✗ ${t('status_error')}: ${esc(d.error)}</span>`;
    }
  } catch(e) {
    result.innerHTML = `<span class="text-danger">✗ ${esc(e.message)}</span>`;
  }
  btn.disabled = false;
}

// ── Tag utilities ──
var TAG_SUGGESTIONS=['Premium','Standard','Basic',t('tag_priority','Priority'),t('tag_new_customer','New customer'),t('tag_trial','Trial')];
// A known tag keeps its colour; any other tag is info blue.
var TAG_TONES={'Premium':'badge-success','Standard':'badge-info','Basic':'','Prioritert':'badge-danger','Priority':'badge-danger','Ny kunde':'badge-warning','New customer':'badge-warning','Proveperiode':'badge-purple','Trial':'badge-purple'};
function _tagTone(tag){return Object.prototype.hasOwnProperty.call(TAG_TONES,tag)?TAG_TONES[tag]:'badge-info';}
function tagPillHtml(tag){return '<span class="badge badge-bordered tag-pill '+_tagTone(tag)+'">'+esc(tag)+'</span>';}
export function tagPillsHtml(tags){if(!tags||tags.length===0)return '';return tags.map(tagPillHtml).join('');}
async function saveCustomerTags(cid,tags){try{await apiFetch('/api/customer/'+encodeURIComponent(cid)+'/tags',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tags:tags})})}catch(e){console.error('save tags:',e)}}
function showTagEditor(cid,curTags){var ex=curTags?curTags.slice():[];var si=cid.replace(/[^a-zA-Z0-9_-]/g,'_');var ct=_tagEl('tag-editor-'+si);if(!ct)return;var sf=TAG_SUGGESTIONS.filter(function(s){return ex.indexOf(s)===-1});var h='<div class="flex flex-wrap gap-1 items-center mb-2">';ex.forEach(function(t,i){h+='<span class="badge badge-bordered '+_tagTone(t)+'">'+esc(t)+' <span class="cursor-pointer text-base lh-none opacity-70" data-click-handler="removeTagAndRefresh" data-customer-id="'+esc(cid)+'" data-index="'+i+'">&times;</span></span>'});h+='</div><div class="flex gap-2 items-center flex-wrap">';h+='<input type="text" id="tag-input-'+si+'" class="field-input field-input-sm tag-input" placeholder="' + t('lbl_write_tag') + '" data-keydown-handler="tagEditorAddOnEnter" data-customer-id="'+esc(cid)+'">';h+='<button class="btn btn-primary btn-sm" data-click-handler="addTagFromInput" data-customer-id="'+esc(cid)+'">+</button></div>';if(sf.length>0){h+='<div class="mt-2 flex flex-wrap gap-1">';sf.forEach(function(s){h+='<button class="btn btn-ghost btn-sm border border-dashed rounded-full" data-click-handler="addSuggestedTag" data-customer-id="'+esc(cid)+'" data-tag="'+esc(s)+'">+ '+esc(s)+'</button>'});h+='</div>'}ct.innerHTML=h;ct.hidden=false}
// The Kunder list and the customer page's Detaljer both carry a tag editor for
// a customer, with the same ids. The one on the page on screen is meant.
function _tagEl(id) {
  return document.querySelector('.view.active [id="' + id + '"]') || document.getElementById(id);
}
var _tagEditorData={};
// "Endre tags" opens the editor and, pressed again, closes it.
export function openTagEditor(cid,tags){
  var open=_tagEl('tag-editor-'+cid.replace(/[^a-zA-Z0-9_-]/g,'_'));
  if(open&&!open.hidden){closeTagEditor(cid);_tagButtons(cid,function(b){b.setAttribute('aria-expanded','false')});return}
  _tagEditorData[cid]=tags?tags.slice():[];showTagEditor(cid,_tagEditorData[cid]);
  _tagButtons(cid,function(b){b.setAttribute('aria-expanded','true')})}
function _tagButtons(cid,fn){document.querySelectorAll('[data-click-handler="openTagEditor"]').forEach(function(b){if(b.dataset.customerId===cid)fn(b)})}
function closeTagEditor(cid){var si=cid.replace(/[^a-zA-Z0-9_-]/g,'_');var c=_tagEl('tag-editor-'+si);if(c){c.innerHTML='';c.hidden=true}delete _tagEditorData[cid]}
function addTagFromInput(cid){var si=cid.replace(/[^a-zA-Z0-9_-]/g,'_');var inp=_tagEl('tag-input-'+si);if(!inp||!inp.value.trim())return;if(!_tagEditorData[cid])_tagEditorData[cid]=[];if(_tagEditorData[cid].indexOf(inp.value.trim())===-1)_tagEditorData[cid].push(inp.value.trim());saveCustomerTags(cid,_tagEditorData[cid]).then(function(){showTagEditor(cid,_tagEditorData[cid]);refreshTagPills(cid,_tagEditorData[cid])})}
function addSuggestedTag(cid,tag){if(!_tagEditorData[cid])_tagEditorData[cid]=[];if(_tagEditorData[cid].indexOf(tag)===-1)_tagEditorData[cid].push(tag);saveCustomerTags(cid,_tagEditorData[cid]).then(function(){showTagEditor(cid,_tagEditorData[cid]);refreshTagPills(cid,_tagEditorData[cid])})}
function removeTagAndRefresh(cid,index){if(!_tagEditorData[cid])return;_tagEditorData[cid].splice(index,1);saveCustomerTags(cid,_tagEditorData[cid]).then(function(){showTagEditor(cid,_tagEditorData[cid]);refreshTagPills(cid,_tagEditorData[cid])})}
// The pills, and the tags "Endre tags" reopens the editor with: the button
// carries them, and reopening from the tags the page was drawn with made the
// next save drop every tag added since.
function refreshTagPills(cid,tags){
  var si=cid.replace(/[^a-zA-Z0-9_-]/g,'_');var el=_tagEl('tag-pills-'+si);if(el)el.innerHTML=tagPillsHtml(tags);
  _tagButtons(cid,function(b){b.dataset.tags=JSON.stringify(tags)})}

// ── Manual Customer ─────────────────────────────────────────────────────────────

export function openNewCustomer() {
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

export function newCustomerWithM365() {
  document.getElementById('manual-customer-modal').style.display = 'none';
  startSetup();
}

export function newCustomerManual() {
  document.getElementById('new-cust-choices').hidden = true;
  document.getElementById('new-cust-form').hidden = false;
  document.getElementById('btn-manual-cust-save').hidden = false;
  document.getElementById('manual-cust-name').focus();
}

export async function submitManualCustomer() {
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

export async function openITGlueImport() {
  var modal = document.getElementById('itglue-import-modal');
  var content = document.getElementById('itglue-import-content');
  var btn = document.getElementById('btn-itglue-import');
  modal.style.display = 'flex';
  btn.disabled = true;
  content.innerHTML = '<div class="text-center p-6"><div class="loader loader-lg mx-auto mt-0 mb-3"></div><span data-i18n="msg_fetching_orgs_itglue">' + t('henter_organisasjoner_fra_it_glue') + '</span></div>';
  _itglueImportOrgs = [];

  try {
    var d = await apiFetch('/api/itglue/organizations', {method: 'POST'});
    if (d.error) {
      content.innerHTML = '<div class="alert alert-error">' + esc(d.error) + '</div>';
      return;
    }
    var orgs = d.organizations || [];
    if (orgs.length === 0) {
      content.innerHTML = '<div class="empty-note is-compact">' + t('msg_no_orgs_found_itglue') + '</div>';
      return;
    }

    // Get existing customers to show which are already imported
    var custData = await apiFetch('/api/customers');
    var existingNames = new Set();
    if (custData && custData.customers) {
      custData.customers.forEach(function(c) { existingNames.add((c.CustomerName || '').toLowerCase()); });
    }

    var html = '<div class="mb-3 flex gap-2 items-center">';
    html += '<input type="text" id="itglue-import-search" class="field-input flex-1 py-2 px-3 text-sm" placeholder="' + t('lbl_search') + '" data-input-handler="filterITGlueImport">';
    html += '<label class="text-sm flex items-center gap-1 cursor-pointer nowrap"><input type="checkbox" id="itglue-import-select-all" data-change-handler="toggleAllITGlueImport"> ' + t('btn_select_all') + '</label>';
    html += '</div>';
    html += '<div class="max-h-lg overflow-y-auto border rounded">';
    html += '<table class="section-table w-full"><thead><tr><th class="col-check"></th><th class="text-left">' + t('lbl_organization') + '</th><th class="text-left">' + t('lbl_id') + '</th><th></th></tr></thead><tbody>';

    orgs.sort(function(a, b) { return a.name.localeCompare(b.name); });
    _itglueImportOrgs = orgs;

    for (var i = 0; i < orgs.length; i++) {
      var o = orgs[i];
      var exists = existingNames.has(o.name.toLowerCase());
      html += '<tr class="itglue-import-row' + (exists ? ' opacity-50' : '') + '" data-name="' + esc(o.name.toLowerCase()) + '">';
      html += '<td class="text-center"><input type="checkbox" class="itglue-import-cb checkbox" data-idx="' + i + '" ' + (exists ? 'disabled title="' + esc(t('msg_already_imported')) + '"' : '') + ' data-change-handler="updateITGlueImportBtn"></td>';
      html += '<td class="fw-medium">' + esc(o.name) + '</td>';
      html += '<td class="font-mono text-xs text-muted">' + esc(o.id) + '</td>';
      html += '<td class="text-xs text-muted">' + (exists ? '<span class="text-success">' + t('msg_already_exists') + '</span>' : '') + '</td>';
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

export async function runITGlueImport() {
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
export async function loadCustomers() {
  const box = document.getElementById('customers-content');
  try {
    const [d, expiryResult] = await Promise.all([
      apiFetch('/api/customers'),
      _expiryData ? Promise.resolve(null) : apiFetch('/api/expiry/check')
    ]);
    if (!d) { box.innerHTML = '<div class="alert alert-error">' + t('err_could_not_load_customers') + '</div>'; return; }
    if (expiryResult) _expiryData = expiryResult;
    setAllCustomers(d.customers || []);
    // Through the filter whatever the search box holds. This used to render
    // the whole list whenever the box was *not* empty, so a list that
    // finished loading after you typed showed every customer again.
    customersFilter();
  } catch(e) {
    box.innerHTML = `<div class="alert alert-error">${t('status_error')}: ${esc(e.message)}</div>`;
  }
}

export async function exportCustomersJSON() {
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

export function clearBulkSelection() {
  _bulkSelectedCustomers = [];
  document.querySelectorAll('.customer-bulk-cb').forEach(function(cb){cb.checked=false});
  document.getElementById('customers-bulk-bar').style.display = 'none';
}

export async function bulkTagCustomers() {
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
      await apiFetch('/api/customer/' + encodeURIComponent(cid) + '/tags', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tags:existing})});
    } catch(e) { console.warn('Bulk tag update failed for', cid, e); }
  }
  clearBulkSelection();
  loadCustomers();
  showToast(t('msg_tag_added','Tag added to') + ' ' + count + ' ' + t('nav_customers').toLowerCase(), 'success', 2000);
}

export async function bulkDeleteCustomers() {
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

export function customersFilter() {
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
  renderCustomers(filtered);
}

function renderCustomers(customers) {
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
        <div class="empty-title mb-6">${t('onboarding_title','Kom i gang med Sybr HUB')}</div>
        <div class="flex gap-6 justify-center flex-wrap mb-6">
          <div class="text-center max-w-sm">
            <div class="step-num">1</div>
            <div class="text-sm fw-semibold">${t('onboarding_step1_title','Legg til kunde')}</div>
            <div class="text-xs text-muted mt-1">${t('onboarding_step1_desc','Klikk \"+ Ny kunde\" og følg veiviseren')}</div>
          </div>
          <div class="text-center max-w-sm">
            <div class="step-num">2</div>
            <div class="text-sm fw-semibold">${t('onboarding_step2_title','Sett opp M365')}</div>
            <div class="text-xs text-muted mt-1">${t('onboarding_step2_desc')}</div>
          </div>
          <div class="text-center max-w-sm">
            <div class="step-num">3</div>
            <div class="text-sm fw-semibold">${t('onboarding_step3_title','Kjør audit')}</div>
            <div class="text-xs text-muted mt-1">${t('onboarding_step3_desc')}</div>
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
    const gdapBadge = isGdap ? '<span class="badge badge-info">GDAP</span>' : '';
    const expiryBadge = isGdap ? '' : getExpiryBadgeForCustomer(c._id);
    const notesBadge = c._has_notes ? '<span class="badge badge-info badge-bordered">' + t('lbl_notes','Notat') + '</span>' : '';
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
    var statusDot = configured ? (hasMetrics ? '<span class="dot ' + toneClass(gradeColor) + '"></span>' : '<span class="dot text-dim" title="' + t('tip_no_audit_run','No audit run') + '"></span>') : '<span class="dot text-warning" title="' + t('tip_not_configured','Not configured') + '"></span>';

    html += `
      <div class="card card-clickable cust-card" data-click-handler="overviewSelectCustomer" data-id="${esc(c._id)}">
        <div class="cust-card-row">
          <input type="checkbox" class="customer-bulk-cb checkbox shrink-0" data-click-handler="customerCardToggleBulk" data-id="${esc(c._id)}">
          <span class="hover-scale cursor-pointer text-lg shrink-0 transition-transform" data-click-handler="customerCardToggleFavorite" data-id="${esc(c._id)}">${isFav ? '\u2605' : '\u2606'}</span>
          ${grade ? '<div class="grade-tile grade-tile-lg grade-' + esc(grade.replace('-', 'none')) + '">'+esc(grade)+'</div>' : '<div class="grade-tile grade-tile-lg is-empty">?</div>'}
          <div class="cust-card-main">
            <div class="cust-card-name">
              ${statusDot}
              <span class="cust-card-name-text">${esc(c.CustomerName || t('lbl_unknown','Unknown'))}</span>
              ${gdapBadge} ${expiryBadge} ${notesBadge}
            </div>
            <div class="cust-card-domain">${esc(c.PrimaryDomain || '')}</div>
            <div class="cust-card-metrics">
              ${riskScore !== '' ? '<span>' + t('lbl_score_prefix','Score:') + ' <strong class="text-default">' + esc(String(riskScore)) + '</strong></span>' : ''}
              ${mfaPct ? '<span>' + t('lbl_mfa_prefix','MFA:') + ' <strong class="text-default">' + mfaPct + '</strong></span>' : ''}
              ${_om && _om.last_audit ? '<span>' + t('lbl_last_prefix','Last:') + ' <strong class="text-default">' + esc(formatRunName(_om.last_audit, true)) + '</strong></span>' : ''}
              <span id="tag-pills-${safeId}" class="cust-card-tags">${tagPillsHtml(cTags)}</span>
            </div>
          </div>
          <div class="cust-card-actions" data-click-handler="stopPropagation">
            <button class="btn btn-ghost btn-sm text-dim" data-click-handler="deleteCustomer" data-id="${esc(c._id)}" data-name="${esc(c.CustomerName)}" title="${t('btn_archive','Archive')}">${t('btn_archive','Archive')}</button>
          </div>
        </div>
        <div id="tag-editor-${safeId}" class="cust-tag-editor" hidden></div>
      </div>`;
  }
  box.innerHTML = html;
}

export async function deleteCustomer(customerId, name) {
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


// ── Bulk Audit ──────────────────────────────────────────────────────────────
// ── Dashboard Excel Export & Clipboard Copy ─────────────────────────────────
export async function exportDashboardExcel() {
  try {
    // In the reader's language: the overview has no report-language choice.
    const r = await fetch('/api/export/excel', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({lang: _lang === 'en' ? 'en' : 'no'})});
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
export function copyOverviewToClipboard(button) {
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

export var _bulkAuditEventSource = null;
export function startBulkAudit() {
  if (_bulkAuditEventSource) { showToast(t('err_bulk_audit_already_running'), 'warning'); return; }
  var btn = document.getElementById('bulk-audit-btn');
  if (btn) { btn.disabled = true; btn.textContent = t('status_running'); }
  var panel = document.getElementById('bulk-audit-panel');
  panel.style.display = 'block';
  panel.innerHTML = '<div class="card p-5 mb-6" id="bulk-progress-card">' +
    '<div class="flex items-center justify-between mb-4">' +
    '<div class="fw-bold text-md">' + t('bulk_audit') + '</div>' +
    '<button class="btn btn-ghost btn-sm" id="bulk-cancel-btn" data-click-handler="cancelBulkAudit">' + t('avbryt') + '</button></div>' +
    '<div id="bulk-overall-status" class="text-ui text-muted mb-3">' + t('starter') + '</div>' +
    '<div class="bar bar-lg mb-2">' +
    '<div id="bulk-overall-bar" class="bar-fill"></div></div>' +
    '<div id="bulk-customer-status" class="text-ui text-muted mb-2"></div>' +
    '<div class="bar mb-4">' +
    '<div id="bulk-customer-bar" class="bar-fill"></div></div>' +
    '<div id="bulk-results-table" style="display:none;">' +
    '<div class="subhead">' + t('resultater') + '</div>' +
    '<table class="data-table">' +
    '<thead><tr>' +
    '<th>' + t('kunde') + '</th>' +
    '<th class="text-center">' + t('grad') + '</th>' +
    '<th class="text-center">' + t('score') + '</th>' +
    '<th class="text-center">' + t('seksjoner_2') + '</th>' +
    '<th class="text-center">' + t('status') + '</th>' +
    '</tr></thead><tbody id="bulk-results-tbody"></tbody></table></div></div>';
  var _ari_b = document.getElementById('audit-running-indicator');
  if (_ari_b) { _ari_b.textContent = ''; _ari_b.innerHTML = '<span class="dot"></span> ' + t('msg_bulk_audit_running'); _ari_b.onclick = function(){ showView('overview'); }; _ari_b.style.display = 'flex'; }
  var totalCustomers = 0, completedCustomers = 0, customerSectionsDone = 0, customerSectionsTotal = 0;
  fetch('/api/audit/bulk', {method:'POST'}).then(async function(resp) {
    if (!resp.ok) { document.getElementById('bulk-overall-status').innerHTML = '<span class="text-danger">HTTP '+Number(resp.status)+'</span>'; return; }
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
      document.getElementById('bulk-customer-status').innerHTML = t('audit_running_customer').replace('{customer}', '<b>' + esc(d.customer) + '</b>').replace('{index}', Number(d.index) + 1).replace('{total}', Number(d.total)) + ' &mdash; ' + esc(d.name) + ' <span class="text-dim">' + esc(d.detail) + '</span>';
    } else if (d.type === 'customer_done') {
      completedCustomers++;
      var overallPct = Math.round((completedCustomers / totalCustomers) * 100);
      document.getElementById('bulk-overall-bar').style.width = overallPct + '%';
      document.getElementById('bulk-overall-status').textContent = t('audit_customers_done').replace('{done}', completedCustomers).replace('{total}', totalCustomers);
      var _bcb3 = document.getElementById('bulk-customer-bar'); if (_bcb3) _bcb3.style.width = '100%';
      var tbody = document.getElementById('bulk-results-tbody');
      document.getElementById('bulk-results-table').style.display = 'block';
      var tr = document.createElement('tr');
      tr.style.borderBottom = '1px solid var(--border)';
      tr.innerHTML = '<td class="fw-semibold">' + esc(d.customer) + '</td>' +
        '<td class="text-center"><span class="grade-tile grade-' + esc(String(d.grade || 'none')) + '">' + esc(d.grade || '-') + '</span></td>' +
        '<td class="text-center">' + esc(d.risk_score || '-') + '</td>' +
        '<td class="text-center">' + Number(d.sections_done) + '/' + Number(d.sections_total) + '</td>' +
        '<td class="text-center text-success fw-semibold">OK</td>';
      tbody.appendChild(tr);
    } else if (d.type === 'customer_error' || d.type === 'customer_skip') {
      completedCustomers++;
      document.getElementById('bulk-overall-bar').style.width = Math.round((completedCustomers / totalCustomers) * 100) + '%';
      document.getElementById('bulk-overall-status').textContent = t('audit_customers_done').replace('{done}', completedCustomers).replace('{total}', totalCustomers);
      var tbody2 = document.getElementById('bulk-results-tbody');
      document.getElementById('bulk-results-table').style.display = 'block';
      var tr2 = document.createElement('tr');
      tr2.style.borderBottom = '1px solid var(--border)';
      tr2.innerHTML = '<td class="fw-semibold">' + esc(d.customer) + '</td>' +
        '<td class="text-center">-</td><td class="text-center">-</td>' +
        '<td class="text-center">-</td>' +
        '<td class="text-center text-danger fw-semibold" title="' + esc(d.error || d.reason || '') + '">' + (d.type === 'customer_skip' ? t('status_skipped') : t('status_error')) + '</td>';
      tbody2.appendChild(tr2);
    } else if (d.type === 'bulk_done') {
      document.getElementById('bulk-overall-bar').style.width = '100%';
      document.getElementById('bulk-overall-bar').style.background = 'var(--green)';
      document.getElementById('bulk-overall-status').innerHTML = '<span class="text-success fw-bold">' + t('audit_finished').replace('{count}', completedCustomers) + '</span>';
      document.getElementById('bulk-customer-status').textContent = '';
      document.getElementById('bulk-cancel-btn').style.display = 'none';
      finishBulkAudit();
    } else if (d.type === 'error') {
      var errHtml = '<span class="text-danger fw-bold">' + t('status_error') + ': ' + esc(d.msg) + '</span>';
      if (d.traceback) {
        errHtml += '<pre class="inset mt-3 text-xs text-danger overflow-x-auto pre-wrap text-left">' + esc(d.traceback) + '</pre>';
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
    if (statusEl) statusEl.innerHTML = '<span class="text-danger">' + t('err_lost_connection') + '</span>';
    finishBulkAudit();
  });
}
function cancelBulkAudit() {
  if (_bulkAuditEventSource) { _bulkAuditEventSource.close(); _bulkAuditEventSource = null; }
  document.getElementById('bulk-overall-status').innerHTML = '<span class="text-warning">' + t('status_cancelled') + '</span>';
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
export function overviewSelectCustomer(customerId) {
  return openCustomerPage(customerId, 'funn');
}
