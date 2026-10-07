import {navOpenCustomerPage as openCustomerPage} from './app-navigation.js';
import {_celebrateConfetti, requestAuditNotifications} from './app-ui.js';
// ═══════════════════════════════════════════════════════════════════
// AUDIT — scope, presets, flow & history
// ═══════════════════════════════════════════════════════════════════

import {esc} from './app-esc.js';
import {t} from './app-i18n.js';
import {registerUiHandlers} from './app-handlers.js';
import {_custPage, currentCustomerId} from './app-state.js';
import {formatRunName, metricPct, toneClass} from './app-format.js';
import {showConfirm, showToast, showTypedConfirm} from './app-ui.js';
import {apiFetch, auditTabHeaders} from './app-api.js';
import {navShowView as showView} from './app-navigation.js';
import {currentView} from './app-state.js';

import {presentCustAuditTabOpen as custAuditTabOpen, presentCustPageAuditFinished as custPageAuditFinished, presentCustReportFromRun as custReportFromRun, presentCustSyncReportButton as custSyncReportButton, presentSetCustReportRun as setCustReportRun, presentSetCustRuns as setCustRuns} from './app-audit-presentation.js';


registerUiHandlers({
  toggleScopeGroup: function(el) { toggleScopeGroup(el, el.dataset.group); },
  onScopeChange: function() { onScopeChange(); },
  openReportViewer: function(el) { openReportViewer(el.dataset.url); },
  deleteAllCustomerRuns: function(el) { deleteAllCustomerRuns(el.dataset.dir, el.dataset.customer, Number(el.dataset.count)); },
  onCompareCheck: function(el) { onCompareCheck(el.dataset.path, el.checked); },
  loadHistoryRun: function(el) { loadHistoryRun(el.dataset.path); },
  openCustomerSummary: function(el) { window.open('/api/reports/customer-summary/' + encodeURIComponent(el.dataset.customerId), '_blank'); },
});

// ── Audit scope selector ────────────────────────────────────────────────────────
// The sections of the customer whose page is open. _scopeCustomerId is the
// customer they were read for, and the only one they are saved back to: a
// save still pending when the page moves to another customer goes to the one
// it belongs to.
let _scopeSections = [];   // [{name, category, enabled}]
export let _scopeLoaded = false;
let _scopeCustomerId = null;
let _scopePanelOpen = false;
let _scopeLoadGeneration = 0;
let _scopeLoading = false;

// The chooser reads its sections again for the next customer page.
export function resetAuditScope() {
  _scopeLoadGeneration++;
  _scopeLoading = false;
  _scopeLoaded = false;
  _scopeSections = [];
  const box = document.getElementById('scope-sections');
  if (box) box.replaceChildren();
  const summary = document.getElementById('scope-summary');
  if (summary) summary.textContent = '';
}

export function toggleScopePanel() {
  _scopePanelOpen = !_scopePanelOpen;
  const body = document.getElementById('scope-body');
  const icon = document.getElementById('scope-toggle-icon');
  if (!body) return;
  body.hidden = !_scopePanelOpen;
  if (icon) icon.innerHTML = _scopePanelOpen ? '&#9660;' : '&#9654;';
  if (_scopePanelOpen && !_scopeLoaded) loadScopeSections();
}

export async function loadScopeSections() {
  const customerId = _custPage.id;
  if (!customerId || _scopeLoading) return;
  const generation = _scopeLoadGeneration;
  _scopeLoading = true;
  const cid = encodeURIComponent(customerId);
  try {
    const [secRes, scopeRes] = await Promise.all([
      apiFetch('/api/audit/sections?customer_id=' + cid),
      apiFetch('/api/audit/scope?customer_id=' + cid),
    ]);
    if (_custPage.id !== customerId || generation !== _scopeLoadGeneration) return;
    _scopeCustomerId = customerId;
    _scopeSections = secRes.sections || [];
    // Apply saved scope if available
    if (scopeRes.scope && scopeRes.scope.enabled_sections) {
      const saved = new Set(scopeRes.scope.enabled_sections);
      _scopeSections.forEach(s => { s.enabled = saved.has(s.name); });
    }
    _scopeLoaded = true;
    renderScopeSections();
    loadPresets();
  } catch (e) {
    if (generation !== _scopeLoadGeneration) return;
    const box = document.getElementById('scope-sections');
    if (box) box.innerHTML = '<div class="text-sm text-danger">' + t('err_could_not_load_sections') + '</div>';
  } finally {
    if (generation === _scopeLoadGeneration) _scopeLoading = false;
  }
}

function renderScopeSections() {
  const box = document.getElementById('scope-sections');
  if (!box) return;
  const categories = {};
  _scopeSections.forEach(s => {
    if (!categories[s.category]) categories[s.category] = [];
    categories[s.category].push(s);
  });
  let html = '';
  for (const [cat, sections] of Object.entries(categories)) {
    const catId = cat.replace(/[^a-zA-Z0-9]/g, '_');
    const allChecked = sections.every(s => s.enabled);
    html += '<div class="inset scope-group">';
    html += '<div class="flex items-center justify-between mb-2">';
    html += '<span class="card-title mb-0">' + esc(cat) + ' <span class="text-dim fw-normal">(' + sections.length + ')</span></span>';
    html += '<label class="text-2xs text-dim cursor-pointer flex items-center gap-1"><input type="checkbox" ' + (allChecked?'checked':'') + ' data-change-handler="toggleScopeGroup" data-group="' + esc(catId) + '"> ' + t('btn_select_all','Alle') + '</label>';
    html += '</div>';
    for (const s of sections) {
      const id = 'scope-cb-' + s.name.replace(/[^a-zA-Z0-9]/g, '_');
      html += '<label class="flex items-center gap-2 text-xs py-0-5 px-0 cursor-pointer" data-scope-group="' + catId + '">';
      html += '<input type="checkbox" id="' + id + '" data-section="' + esc(s.name) + '" ' + (s.enabled ? 'checked' : '') + ' data-change-handler="onScopeChange">';
      html += esc(s.name) + '</label>';
    }
    html += '</div>';
  }
  box.innerHTML = html;
  updateScopeSummary();
}

function toggleScopeGroup(masterCb, groupId) {
  document.querySelectorAll('[data-scope-group="' + groupId + '"] input[type=checkbox]').forEach(function(cb) {
    cb.checked = masterCb.checked;
  });
  onScopeChange();
}

function onScopeChange() {
  document.querySelectorAll('#scope-sections input[type=checkbox]').forEach(cb => {
    const name = cb.getAttribute('data-section');
    const sec = _scopeSections.find(s => s.name === name);
    if (sec) sec.enabled = cb.checked;
  });
  updateScopeSummary();
  saveScopeDebounced();
}

export function updateScopeSummary() {
  const el = document.getElementById('scope-summary');
  if (!el || !_scopeSections.length) return;
  const total = _scopeSections.length;
  const enabled = _scopeSections.filter(s => s.enabled).length;
  el.textContent = t('lbl_sections_selected').replace('{count}', enabled).replace('{total}', total);
}

export function scopeSelectAll() {
  _scopeSections.forEach(s => { s.enabled = true; });
  renderScopeSections();
  saveScopeDebounced();
}

export function scopeDeselectAll() {
  _scopeSections.forEach(s => { s.enabled = false; });
  renderScopeSections();
  saveScopeDebounced();
}

let _scopeSaveTimer = null;
function saveScopeDebounced() {
  clearTimeout(_scopeSaveTimer);
  _scopeSaveTimer = setTimeout(saveScope, 500);
}

async function saveScope() {
  if (!_scopeCustomerId) return;
  const enabled = _scopeSections.filter(s => s.enabled).map(s => s.name);
  try {
    await apiFetch('/api/audit/scope?customer_id=' + encodeURIComponent(_scopeCustomerId), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ enabled_sections: enabled }),
    });
  } catch (_) {}
}

// ── Audit scope presets ──────────────────────────────────────────────────────
let _presets = [];

async function loadPresets() {
  try {
    const d = await apiFetch('/api/audit/presets');
    _presets = d.presets || [];
    renderPresetDropdown();
  } catch (_) {}
}

function renderPresetDropdown() {
  const sel = document.getElementById('preset-select');
  if (!sel) return;
  sel.innerHTML = '<option value="">' + t('lbl_select_preset') + '</option>';
  for (const p of _presets) {
    const opt = document.createElement('option');
    opt.value = p.name;
    opt.textContent = p.name + (p.builtin ? '' : ' ' + t('lbl_custom'));
    sel.appendChild(opt);
  }
}

export function applyPreset() {
  const sel = document.getElementById('preset-select');
  const delBtn = document.getElementById('preset-delete-btn');
  if (!sel) return;
  const name = sel.value;
  if (delBtn) delBtn.hidden = true;
  if (!name) return;

  const preset = _presets.find(p => p.name === name);
  if (!preset) return;

  if (delBtn && !preset.builtin) delBtn.hidden = false;

  const enabledSet = new Set(preset.sections);
  _scopeSections.forEach(s => { s.enabled = enabledSet.has(s.name); });
  renderScopeSections();
  saveScopeDebounced();
}

export async function saveCustomPreset() {
  const name = prompt(t('dlg_preset_name'));
  if (!name || !name.trim()) return;
  const sections = _scopeSections.filter(s => s.enabled).map(s => s.name);
  if (sections.length === 0) { showToast(t('msg_select_min_one_section'), 'warning'); return; }
  try {
    const d = await apiFetch('/api/audit/presets', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ name: name.trim(), sections }),
    });

    if (d.error) { showToast(d.error, 'error'); return; }
    await loadPresets();
    document.getElementById('preset-select').value = name.trim();
    const delBtn = document.getElementById('preset-delete-btn');
    if (delBtn) delBtn.hidden = false;
  } catch (e) { showToast(t('err_could_not_save_preset').replace('{msg}', e.message), 'error'); }
}

export async function deleteCustomPreset() {
  const sel = document.getElementById('preset-select');
  if (!sel || !sel.value) return;
  const name = sel.value;
  if (!await showConfirm(t('dlg_confirm_delete_preset').replace('{name}', name))) return;
  try {
    const d = await apiFetch('/api/audit/presets/' + encodeURIComponent(name), { method: 'DELETE' });
    if (d.error) { showToast(d.error, 'error'); return; }
    await loadPresets();
    const delBtn = document.getElementById('preset-delete-btn');
    if (delBtn) delBtn.hidden = true;
  } catch (e) { showToast(t('err_could_not_delete_preset').replace('{msg}', e.message), 'error'); }
}

function getSelectedSectionNames() {
  if (!_scopeLoaded || !_scopeSections.length) return null;
  const enabled = _scopeSections.filter(s => s.enabled).map(s => s.name);
  if (enabled.length === _scopeSections.length) return null;
  if (enabled.length === 0) return null; // don't send empty — will run all as safety
  return enabled;
}

// ── Audit state ────────────────────────────────────────────────────────────────
export let auditRunning = false;
// The customer the running audit (this account's one at a time) is for. The
// customer page shows the run only on that customer's Audit tab.
export let auditCustomerId = null;
let sectionTotal = 0;
let sectionDone = 0;

// The one authority on whether an audit is running is the server. A client
// flag that outlives its run leaves a badge lit with nothing behind it.
export async function _reconcileAuditState() {
  try {
    // This account's running audit, whichever customer it is for.
    var d = await apiFetch('/api/audit/progress');
    if (!d || d.running === undefined) return;   // older server: leave as-is
    if (d.running && !auditRunning) {
      // Started elsewhere — another tab, a schedule, another technician.
      auditRunning = true;
      auditCustomerId = d.customer_id || null;
      var ind = document.getElementById('audit-running-indicator');
      if (ind) ind.style.display = 'flex';
      _showAuditRunOrIdle();
      startAuditProgressPolling();
      // We never had a stream to lose; with the customer known, the watcher
      // can re-attach to the run's live stream.
      _watchAuditUntilServerIdle(true, auditCustomerId ? '/api/audit/stream?customer_id=' + encodeURIComponent(auditCustomerId) : null);
    } else if (d.running) {
      auditCustomerId = d.customer_id || auditCustomerId;
      _showAuditRunOrIdle();
    } else if (auditRunning) {
      _finishAuditWithoutStream();
    } else {
      _clearStaleAuditBadge();
      if (custAuditTabOpen()) _renderAuditIdle();
    }
  } catch (_) { /* offline: say nothing rather than claim either state */ }
}

// The audit view's markup is written as though you can only ever arrive
// mid-run: a spinner, "Starting audit…", "0 / 0 sections", 0%. Open it when
// nothing is running and it announces a run that does not exist. These two
// functions give it the state it never had.
function _auditChrome() {
  return [
    document.getElementById('audit-status-bar'),
    document.querySelector('#view-audit .progress-row'),
    document.getElementById('section-table') ? document.getElementById('section-table').closest('.card') : null,
  ];
}

export function _showAuditRunningChrome() {
  var idle = document.getElementById('audit-idle');
  if (idle) idle.style.display = 'none';
  _auditChrome().forEach(function(el) { if (el) el.style.display = ''; });
}

// Whether the run in progress is this page's customer's.
export function _auditRunIsThisPages() {
  return (auditRunning || _auditStarting) && (!auditCustomerId || auditCustomerId === _custPage.id);
}

// The run on its own customer's Audit tab; on any other customer's, the idle
// state, while the floating bar says a run is going on elsewhere.
function _showAuditRunOrIdle() {
  if (_auditRunIsThisPages()) _showAuditRunningChrome();
  else if (currentView === 'customer-detail' && _custPage.tab === 'audit') _renderAuditIdle();
}

export function _renderAuditIdle() {
  var view = document.getElementById('view-audit');
  if (!view || _auditRunIsThisPages()) return;

  // Nothing is running, so the running chrome is a lie. Put it away.
  _auditChrome().forEach(function(el) { if (el) el.style.display = 'none'; });
  var tbody = document.getElementById('section-tbody');
  if (tbody && !tbody.children.length) {
    var findings = document.getElementById('audit-findings');
    if (findings) findings.style.display = 'none';
  }

  var idle = document.getElementById('audit-idle');
  if (!idle) {
    idle = document.createElement('div');
    idle.id = 'audit-idle';
    idle.className = 'card';
    var bar = document.getElementById('audit-status-bar');
    if (bar && bar.parentNode) bar.parentNode.insertBefore(idle, bar); else view.appendChild(idle);
  }
  idle.style.display = '';

  // The last run of the customer whose page this is, as its head says.
  var last = _custPage.cust && _custPage.cust.last_audit;
  var when = last ? formatRunName(last) : '';

  // The page's one Kjør audit is in its head; the runs are listed below.
  idle.innerHTML =
      '<div class="card-title">' + esc(t('hdr_audit_idle')) + '</div>'
    + '<div class="cust-card-text">' + esc(t('msg_audit_idle_body_tab', 'Ingen audit kjører for kunden nå. Kjør audit starter en, og fremdriften vises her.')) + '</div>'
    + '<div class="cust-card-text">' + esc(t('lbl_last_audit')) + ': '
    +   '<strong>' + esc(when || t('lbl_never')) + '</strong></div>';
}

function _clearStaleAuditBadge() {
  auditRunning = false;
  auditCustomerId = null;
  stopAuditProgressPolling();
  _hideAuditProgressBar();
  var ind = document.getElementById('audit-running-indicator');
  if (ind) ind.style.display = 'none';
}

// ── Audit flow ─────────────────────────────────────────────────────────────────
const sectionRows = {}; // name -> tr element
// Between the click and the run's stream: the Audit tab opening meanwhile
// must not ask the server, which does not know of the run yet, and paint it
// idle over the run starting.
var _auditStarting = false;
// When the run on screen started, for the elapsed time in its summary.
var _auditStartTime = null;

// Audits one customer: the one named, else the page on screen, else this
// tab's current customer (the keyboard shortcut has no page to ask).
export async function startAudit(customerId) {
  customerId = customerId || (currentView === 'customer-detail' && _custPage.id) || currentCustomerId();
  if (!customerId) { showView('customers'); return; }
  // Asked here, inside the click, so the browser shows the prompt and the
  // operator knows what it is for: a notice when the audit finishes.
  requestAuditNotifications();
  const cid = encodeURIComponent(customerId);
  // Quick pre-flight permission check (non-blocking — warn only)
  try {
    const d = await apiFetch('/api/audit/validate-permissions?customer_id=' + cid, { method: 'POST' });
    if (d.missing && d.missing.length > 0) {
      const msg = t('dlg_permissions_missing').replace('{count}', d.missing.length).replace('{list}', d.missing.join('\n'));
      if (!await showConfirm(msg)) return;
    }
  } catch (_) {
    // Permission check failed — proceed anyway
  }

  _auditStarting = true;
  auditCustomerId = customerId;
  // Reset state
  Object.keys(sectionRows).forEach(k => delete sectionRows[k]);
  sectionDone = 0;
  sectionTotal = 0; // will grow dynamically as sections register

  document.getElementById('section-tbody').innerHTML = '';
  document.getElementById('audit-done-area').style.display = 'none';
  document.getElementById('report-result').innerHTML = '';
  setAuditStatus('<div class="loader"></div><span>' + t('msg_starting') + '</span>');
  updateProgress(0, sectionTotal);
  _auditStartTime = Date.now();

  // The run shows on its customer's Audit tab.
  await openCustomerPage(customerId, 'audit');
  _showAuditRunningChrome();
  auditRunning = true;
  _auditStarting = false;
  var _ari = document.getElementById('audit-running-indicator'); if (_ari) _ari.style.display = 'flex';
  startAuditProgressPolling();

  // Build stream URL: the customer, and the section filter if there is one.
  // The sections are this customer's only when the chooser was read for it.
  let streamUrl = '/api/audit/stream?customer_id=' + cid;
  const _selectedSections = _scopeCustomerId === customerId ? getSelectedSectionNames() : null;
  if (_selectedSections) {
    streamUrl += '&sections=' + encodeURIComponent(_selectedSections.join(','));
  }
  // Use fetch with auth header (EventSource can't send Authorization).
  // Wrapped in _runAuditStreamWithReconnect so a network blip doesn't
  // kill the visual feedback for a multi-hour audit; the polling
  // fallback (startAuditProgressPolling) keeps the progress bar alive
  // and we retry the stream with exponential backoff in the background.
  _runAuditStreamWithReconnect(streamUrl);
}

// Backoff sequence: 2s, 4s, 8s, 16s, 32s — caps at 32s, retries forever
// while auditRunning is true. Operator can navigate away and back to
// reset; closing the browser doesn't stop the server-side audit.
async function _runAuditStreamWithReconnect(streamUrl) {
  // The first call starts the audit. A dropped connection is a lost *view*, not
  // a lost run — the collection continues on the server and saves its results
  // regardless. Recovery re-attaches: GET /audit/stream now re-attaches to this
  // user's running run instead of starting a fresh one, and the reconnect below
  // adds ?attach=1 so a re-open can only ever attach, never launch a duplicate.
  // (The older code could call this exactly once and then only poll, because a
  // blind re-open used to start another audit.)
  const ok = await _attemptAuditStream(streamUrl);
  if (ok === 'done' || !auditRunning) return;
  await _watchAuditUntilServerIdle(false, streamUrl);
}

// Follow a run we can no longer see, until the server says it is over.
var _auditWatching = false;
async function _watchAuditUntilServerIdle(quiet, streamUrl) {
  if (_auditWatching) return;   // one watcher is enough; two would race
  _auditWatching = true;
  try {
    await _watchAuditLoop(quiet, streamUrl);
  } finally {
    _auditWatching = false;
  }
}

async function _watchAuditLoop(quiet, streamUrl) {
  if (!quiet) {
    showToast(t('msg_audit_stream_lost'), 'warning', 8000);
  }
  setAuditStatus('<div class="loader"></div><span>' + t('msg_audit_running_no_stream') + '</span>');

  // Re-attach URL forces attach-only, so a re-open can never start a new audit.
  var attachUrl = streamUrl ? streamUrl + '&attach=1' : null;

  while (auditRunning) {
    await new Promise(r => setTimeout(r, 3000));
    let d = null;
    try {
      d = await apiFetch('/api/audit/progress');
    } catch (_) {
      continue;  // the server is unreachable; keep watching rather than guess
    }
    // Only an explicit false ends the watch. An older server that does not
    // send `running` leaves it undefined, and guessing "finished" there would
    // reintroduce exactly the wrong-by-assumption bug this replaced.
    if (d && d.running === false) {
      _finishAuditWithoutStream();
      return;
    }
    // The run is alive on the server — go back to watching it *live* rather than
    // polling. attach=1 guarantees this only ever re-attaches, and the running
    // check above means we never re-open against a run that already ended.
    if (attachUrl && d && d.running === true) {
      var outcome = await _attemptAuditStream(attachUrl);
      if (outcome === 'done' || !auditRunning) return;
      // Dropped again — restore the no-stream header and keep watching.
      setAuditStatus('<div class="loader"></div><span>' + t('msg_audit_running_no_stream') + '</span>');
    }
  }
}

// The audit ended while we were not watching. We never received the results
// payload, but the server wrote them to disk, so reload rather than invent.
function _finishAuditWithoutStream() {
  auditRunning = false;
  document.title = _origTitle;
  stopAuditProgressPolling();
  _hideAuditProgressBar();
  var ind = document.getElementById('audit-running-indicator');
  if (ind) ind.style.display = 'none';
  setAuditStatus('<span class="text-warning">' + t('msg_audit_done_stream_lost') + '</span>');
  custPageAuditFinished();
}

// What auto-send came to, in the reader's language. The completion event is
// built where no reader is known, so it carries the key and the values; msg
// is the server's Norwegian text for an event from before it did.
function _emailStatusText(s) {
  var out = s.msg_key ? t(s.msg_key, s.msg || '') : (s.msg || '');
  var params = s.msg_params || {};
  Object.keys(params).forEach(function(k) {
    out = out.split('{' + k + '}').join(String(params[k]));
  });
  return out;
}

async function _attemptAuditStream(streamUrl) {
  try {
    const resp = await fetch(streamUrl, {method: streamUrl.indexOf('attach=1') === -1 ? 'POST' : 'GET', headers: auditTabHeaders()});
    if (!resp.ok) {
      // 409 = an audit is already running. Nothing was started by this call,
      // and there is no way to attach to the existing run's stream, so fall
      // through to watching its progress.
      if (resp.status === 409) return false;
      setAuditStatus('<span class="text-danger">✗ HTTP '+Number(resp.status)+'</span>');
      return 'done';
    }
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buf = '';
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buf += decoder.decode(chunk.value, {stream:true});
      var lines = buf.split('\n'); buf = lines.pop();
      for (var i = 0; i < lines.length; i++) {
        if (!lines[i].startsWith('data: ')) continue;
        try {
          var d = JSON.parse(lines[i].slice(6));
          if (d.type === 'started') {
            setAuditStatus('<div class="loader"></div><span>' + t('msg_audit_running') + '</span>');
          } else if (d.type === 'progress') {
            handleProgress(d);
          } else if (d.type === 'snapshot') {
            // Re-attach replay: jump the status to where the run is now; live
            // 'progress' events follow and fill in the per-section detail.
            if (typeof d.completed === 'number' && typeof d.total_sections === 'number') {
              setAuditStatus('<div class="loader"></div><span>' + t('msg_audit_running_sections').replace('{done}', Number(d.completed)).replace('{total}', Number(d.total_sections)) + '</span>');
            }
          } else if (d.type === 'ended') {
            // A re-attach found no active run (it finished or was cleared while
            // we were away). Reload to whatever the server saved.
            _finishAuditWithoutStream();
            return 'done';
          } else if (d.type === 'done') {
            auditRunning = false; document.title = _origTitle;
            stopAuditProgressPolling(); _hideAuditProgressBar();
            var _ari_d = document.getElementById('audit-running-indicator'); if (_ari_d) _ari_d.style.display = 'none';
            handleAuditDone(d.results || []);
            if (d.email_status) {
              var area = document.getElementById('report-result');
              var color = d.email_status.ok ? 'var(--green)' : 'var(--orange)';
              var icon = d.email_status.ok ? '✓' : '';
              area.innerHTML += '<div class="alert ' + toneClass(color) + ' mt-2 text-ui">'+icon+' '+esc(_emailStatusText(d.email_status))+'</div>';
            }
            return 'done';
          } else if (d.type === 'error') {
            auditRunning = false; document.title = _origTitle;
            stopAuditProgressPolling(); _hideAuditProgressBar();
            var _ari_e = document.getElementById('audit-running-indicator'); if (_ari_e) _ari_e.style.display = 'none';
            setAuditStatus('<span class="text-danger">✗ '+t('status_error')+': '+esc(d.msg)+'</span>');
            return 'done';
          } else if (d.type === 'cancelled') {
            auditRunning = false; document.title = _origTitle;
            stopAuditProgressPolling(); _hideAuditProgressBar();
            setAuditStatus('<span class="text-warning">'+esc(d.msg)+'</span>');
            return 'done';
          }
        } catch(_) {}
      }
    }
    // Stream closed cleanly without 'done' — let reconnect loop handle it
    return false;
  } catch (e) {
    // Network error / connection reset — caller will retry with backoff
    return false;
  }
}

function handleProgress(d) {
  const { name, status, detail } = d;
  const icons = { pending:'', running:'', done:'✓', skipped:'→', failed:'✗' };
  const cls   = { pending:'s-pending', running:'s-running', done:'s-done', skipped:'s-skipped', failed:'s-failed' };
  const labels= { pending:t('status_pending'), running:t('status_running'), done:t('status_done'), skipped:t('status_skipped'), failed:t('status_failed') };

  if (sectionRows[name]) {
    const tr = sectionRows[name];
    tr.querySelector('.status-icon').textContent = icons[status] || '•';
    tr.querySelector('.status-icon').className = `status-icon ${cls[status] || ''}`;
    tr.querySelector('.status-text').textContent = statusLabel(status, labels);
    tr.querySelector('.status-text').className = `status-text ${cls[status] || ''}`;
    if (detail && status === 'failed') {
      tr.querySelector('.detail-cell').innerHTML += `<div class="err-text">${esc(detail)}</div>`;
    }
  } else {
    const tbody = document.getElementById('section-tbody');
    const tr = document.createElement('tr');
    // No pointer and no expander: the findings live in the summary above, so
    // there is nothing here to reveal. Every row used to offer the affordance,
    // including the twelve with an empty detail cell and nothing behind it.
    tr.innerHTML = `
      <td><span class="status-icon ${cls[status] || ''}">${icons[status] || '•'}</span></td>
      <td class="fw-medium">${esc(name)}</td>
      <td><span class="status-text ${cls[status] || ''}">${esc(statusLabel(status, labels))}</span></td>
      <td class="detail-cell">${detail && status === 'failed' ? `<div class="err-text">${esc(detail)}</div>` : ''}</td>`;
    tbody.appendChild(tr);
    sectionRows[name] = tr;
  }

  const terminal = ['done', 'skipped', 'failed'];
  if (terminal.includes(status)) {
    sectionDone++;
    updateProgress(sectionDone, sectionTotal);
    setAuditStatus('<div class="loader"></div><span>' + t('msg_audit_running_sections').replace('{done}', sectionDone).replace('{total}', Number(sectionTotal)) + '</span>');
  }
}

// Everything the run flagged, gathered in one place and ordered by weight.
//
// The section table answers "did every section run", which is what you want
// while it is running. Afterwards the question is "what is wrong", and that
// answer was spread across twenty-six rows — most of them empty, since a
// section with nothing to report still takes a full row — with the longest
// lists truncated behind "+n til". Nothing is removed; this sits above it.
// A section that finished as expected says nothing; the icon already does.
// "Hoppet over" and "Feilet" keep their words, because those differ.
function statusLabel(status, labels) {
  return status === 'done' ? '' : (labels[status] || status);
}

function renderAuditFindings(results) {
  var box = document.getElementById('audit-findings');
  if (!box) return;

  var failures = [], skipped = [], findings = [];
  results.forEach(function (r) {
    // A skipped section carries its reason in the same field a failed one
    // uses, so "no Azure subscriptions found" — which is a legitimate skip on
    // a tenant without Azure — was announced as four failures in red at the
    // top of the list, while the table below correctly said "Hoppet over".
    // Status decides; the reason is only the wording.
    if (r.error && r.status === 'failed') failures.push({ section: r.name, text: r.error });
    else if (r.error && r.status === 'skipped') skipped.push({ section: r.name, text: r.error });
    (r.warns || []).forEach(function (w, i) {
      var level = (r.warn_levels || [])[i] || 'warn';
      findings.push({ section: r.name, text: w, level: level });
    });
  });

  if (!failures.length && !findings.length && !skipped.length) {
    box.style.display = 'block';
    box.innerHTML = '<div class="card edge-success">'
      + '<div class="fw-semibold text-success">&#10003; '
      + esc(t('audit_no_findings', 'Ingen varsler')) + '</div>'
      + '<div class="text-dim text-sm mt-1">'
      + esc(t('audit_no_findings_detail', 'Alle seksjoner fullførte uten å flagge noe.'))
      + '</div></div>';
    return;
  }

  var colours = {red: 'var(--red)', orange: 'var(--orange)', dim: 'var(--text-dim)'};
  function list(items, colour, heading) {
    if (!items.length) return '';
    return '<div class="mb-3">'
      + '<div class="fw-semibold ' + toneClass(colours[colour]) + ' mb-2 text-ui">'
      + esc(heading) + ' (' + items.length + ')</div>'
      + items.map(function (f) {
          // Wraps rather than squeezing: a fixed basis pinched the section
          // name to a few characters once the pane got narrow, and the app is
          // otherwise built for that — the tables scroll, the layout breaks at
          // 1100, 767 and 479.
          return '<div class="audit-finding">'
            + '<span class="audit-finding-section">' + esc(f.section) + '</span>'
            + '<span class="audit-finding-text">' + esc(f.text) + '</span></div>';
        }).join('')
      + '</div>';
  }

  box.style.display = 'block';
  var anyCritical = findings.some(function (f) { return f.level === 'critical'; });
  box.innerHTML = '<div class="card ' + (failures.length || anyCritical ? 'edge-danger' : 'edge-warning') + '">'
    + list(failures, 'red', t('status_failed', 'Feilet'))
    + list(findings.filter(function (f) { return f.level === 'critical'; }),
           'red', t('status_critical_findings', 'Kritiske funn'))
    + list(findings.filter(function (f) { return f.level !== 'critical'; }),
           'orange', t('status_warnings', 'Varsler'))
    + list(skipped, 'dim', t('status_skipped', 'Hoppet over'))
    + '</div>';
}

function handleAuditDone(results) {
  let done = 0, warns = 0, failed = 0;

  // Update rows with final data (fills in warns and files)
  for (const r of results) {
    const status = r.status;
    const icons  = { pending:'', running:'', done:'✓', skipped:'→', failed:'✗' };
    const cls    = { pending:'s-pending', running:'s-running', done:'s-done', skipped:'s-skipped', failed:'s-failed' };
    const labels = { pending:t('status_pending'), running:t('status_running'), done:t('status_done'), skipped:t('status_skipped'), failed:t('status_failed') };

    if (sectionRows[r.name]) {
      const tr = sectionRows[r.name];
      // Update icon/status in case last progress event was 'running'
      tr.querySelector('.status-icon').textContent = icons[status] || '•';
      tr.querySelector('.status-icon').className = `status-icon ${cls[status] || ''}`;
      tr.querySelector('.status-text').textContent = statusLabel(status, labels);
      tr.querySelector('.status-text').className = `status-text ${cls[status] || ''}`;

      // The summary above carries every finding, labelled with its section.
      // This table used to carry them too — three times over: the first three
      // as pills, the remainder behind "+n til", and all of them again in an
      // expander. Two of those three renderings were lossy, and the lossy ones
      // were the visible ones.
      //
      // So the table keeps only what the summary cannot answer: whether each
      // section ran. An error or a skip reason belongs to the section rather
      // than to the findings list, so those stay.
      const detailCell = tr.querySelector('.detail-cell');
      if (r.warns && r.warns.length > 0) warns++;
      detailCell.innerHTML = r.error ? `<div class="err-text">${esc(r.error)}</div>` : '';

    }

    if (status === 'done' || status === 'skipped') done++;
    if (status === 'failed') { done++; failed++; }
  }

  updateProgress(results.length, results.length);
  var elapsed = _auditStartTime ? Math.round((Date.now() - _auditStartTime) / 1000) : 0;
  var elapsedStr = elapsed >= 60 ? Math.floor(elapsed/60) + 'm ' + (elapsed%60) + 's' : elapsed + 's';
  var totalFiles = results.reduce(function(s,r){ return s + (r.files ? r.files.length : 0); }, 0);
  setAuditStatus('<span class="text-success">' + t('msg_audit_complete').replace('{count}', results.length) + ' <span class="text-dim fw-normal">(' + elapsedStr + ' · ' + Number(totalFiles) + ' ' + t('nav_files','files') + ')</span></span>');

  // What Rapport builds from: this run, which the server now holds for its
  // customer.
  setCustReportRun({customerId: auditCustomerId});
  custSyncReportButton();
  custPageAuditFinished();
  document.getElementById('sum-done').textContent = done;
  document.getElementById('sum-warn').textContent = warns;
  document.getElementById('sum-fail').textContent = failed;
  document.getElementById('audit-done-area').style.display = 'block';
  renderAuditFindings(results);

  // Browser notification if tab is hidden
  if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
    new Notification('Sybr HUB', {
      body: t('msg_audit_complete','Audit complete').replace('{count}', results.length) + ' (' + elapsedStr + ')',
      icon: '/branding/sybr_logo_transparent.png',
    });
  }

  // Check grade and celebrate if A!
  var doneFor = auditCustomerId;
  setTimeout(async function() {
    if (!doneFor) return;
    try {
      var dash = await apiFetch('/api/dashboard?customer_id=' + encodeURIComponent(doneFor));
      if (dash && dash.metrics && dash.metrics.risk_grade === 'A') {
        _celebrateConfetti();
        showToast('' + t('msg_grade_a','Grade A — excellent security posture!'), 'success', 5000);
      }
    } catch(e) {}
  }, 1500);
}

var _origTitle = document.title;
function updateProgress(done, total) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  document.getElementById('progress-fill').style.width = pct + '%';
  document.getElementById('progress-pct').textContent = pct + '%';
  document.getElementById('progress-label').textContent = t('audit_sections_count').replace('{done}', done).replace('{total}', total);
  // Update browser tab title with progress
  if (auditRunning) document.title = t('lbl_audit','Audit') + ' ' + pct + '% · ' + _origTitle;
  else document.title = _origTitle;
}

function setAuditStatus(html) {
  document.getElementById('audit-status-bar').innerHTML = /* safe-html: every caller passes markup built inline, which the check reads at the call */ html;
}

// ── Audit progress polling (REST) ───────────────────────────────────────────
var _auditProgressTimer = null;

function startAuditProgressPolling() {
  stopAuditProgressPolling();
  pollAuditProgress();  // don't wait 2s for the first honest denominator
  _auditProgressTimer = setInterval(pollAuditProgress, 2000);
}

export function stopAuditProgressPolling() {
  if (_auditProgressTimer) { clearInterval(_auditProgressTimer); _auditProgressTimer = null; }
}

export async function pollAuditProgress() {
  if (!auditRunning) { stopAuditProgressPolling(); _hideAuditProgressBar(); return; }
  try {
    var d = await apiFetch('/api/audit/progress');
    if (!d || !d.total_sections) return;
    // Update the global indicator in the header
    var ind = document.getElementById('audit-running-indicator');
    if (ind && ind.style.display !== 'none') {
      ind.innerHTML = '<span class="dot"></span> '
        + 'Audit ' + Number(d.progress) + '% · ' + esc(d.current_section);
    }
    // The audit view's own bar used to derive its total from the sections that
    // had already announced themselves, so it read n / n after every section
    // and sat at 100% for the whole run. The server knows the real section
    // list; take the denominator from it and let the SSE handler move the
    // numerator between polls.
    if (typeof d.total_sections === 'number' && d.total_sections > 0) {
      sectionTotal = d.total_sections;
      if (custAuditTabOpen()) updateProgress(d.completed, sectionTotal);
    }
    // Update floating progress bar (shown on non-audit views)
    _showAuditProgressBar(d);
  } catch(e) { /* expected during SSE transition */ }
}

function _showAuditProgressBar(d) {
  var bar = document.getElementById('audit-progress-float');
  if (!bar) return;
  // Hide when the run's own progress is on screen.
  if (custAuditTabOpen()) { bar.style.display = 'none'; return; }
  bar.style.display = 'block';
  var pct = d.progress || 0;
  bar.querySelector('.apf-fill').style.width = pct + '%';
  bar.querySelector('.apf-text').textContent = pct + '% · ' + (d.current_section || '...');
  bar.querySelector('.apf-counts').textContent = d.completed + ' / ' + d.total_sections;
}

function _hideAuditProgressBar() {
  var bar = document.getElementById('audit-progress-float');
  if (bar) bar.style.display = 'none';
}

// ── Report generation ──────────────────────────────────────────────────────────
// From the run selected for this customer (the one just audited, or one
// picked in the runs list).
export async function generateReport(fmt, reportType, customerId) {
  const area = document.getElementById('report-result');
  const label = reportType === 'customer' ? t('lbl_customer_report') : t('lbl_tech_report');
  area.innerHTML = '<div class="loader"></div> ' + t('msg_generating_report').replace('{label}', label);

  try {
    const d_report = await apiFetch('/api/report/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ customer_id: customerId, format: fmt, report_type: reportType, lang: document.getElementById('report-lang')?.value || 'no', frameworks: document.getElementById('report-frameworks')?.value || 'all', theme: document.getElementById('report-theme')?.value || 'light' }),
    });
    const d = d_report;
    if (!d) { area.innerHTML = '<div class="alert alert-error">' + t('err_could_not_generate_report') + '</div>'; return; }
    if (d.error) {
      area.innerHTML = `<div class="alert alert-error">${esc(d.error)}</div>`;
      return;
    }
    if (fmt === 'html' && d.html_url) {
      area.innerHTML = '<div class="alert alert-success flex items-center justify-between flex-wrap gap-2">'
        + '<span>' + esc(label) + '</span>'
        + '<div class="flex gap-2">'
        + '<button class="btn btn-primary btn-sm" data-click-handler="openReportViewer" data-url="' + esc(d.html_url) + '">' + t('vis_i_app') + '</button>'
        + '<a href="' + esc(d.html_url) + '" target="_blank" class="btn btn-ghost btn-sm">' + t('ny_fane') + '</a>'
        + '</div></div>';
    } else if (fmt === 'pdf' && d.pdf_url) {
      // The link text is its own key. It used to be cut out of a sentence at
      // its dash, so rewording the sentence would have shown "undefined".
      var _dlLink = '<a href="' + esc(d.pdf_url) + '" download class="text-success">' + esc(t('btn_download', 'Last ned')) + '</a>';
      area.innerHTML = '<div class="alert alert-success">✓ ' + esc(label) + ' (PDF) · ' + _dlLink + '</div>';
      window.open(d.pdf_url, '_blank');
    } else {
      area.innerHTML = '<div class="alert alert-success">' + t('msg_report_generated').replace('{label}', esc(label)) + '</div>';
    }
  } catch (e) {
    area.innerHTML = '<div class="alert alert-error">✗ ' + t('err_network_error').replace('{msg}', esc(e.message)) + '</div>';
  }
}

// ── Report Viewer ─────────────────────────────────────────────────────────────
function openReportViewer(url) {
  var modal = document.getElementById('report-viewer-modal');
  modal.style.display = 'flex';
  document.getElementById('report-viewer-link').href = url;
  document.getElementById('report-viewer-title').textContent = url.split('/').pop() || '';
  document.getElementById('report-viewer-iframe').src = url;
}
export function closeReportViewer() {
  document.getElementById('report-viewer-modal').style.display = 'none';
  document.getElementById('report-viewer-iframe').src = 'about:blank';
}

export async function exportCSV(customerId) {
  const area = document.getElementById('report-result');
  area.innerHTML = '<div class="loader"></div> ' + t('msg_generating_csv');
  try {
    const r = await fetch('/api/report/csv', {
      // The report language the screen offers, as generateReport sends it.
      method: 'POST', headers: auditTabHeaders({'Content-Type': 'application/json'}), body: JSON.stringify({customer_id: customerId, lang: document.getElementById('report-lang')?.value || 'no'}),
    });
    if (!r.ok) {
      try { const d = await r.json(); area.innerHTML = `<div class="alert alert-error">✗ ${esc(d.error)}</div>`; } catch(_) { area.innerHTML = '<div class="alert alert-error">' + t('err_export_failed','Export failed') + '</div>'; }
      return;
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'audit_export.csv';
    a.click();
    URL.revokeObjectURL(url);
    area.innerHTML = '<div class="alert alert-success">' + t('msg_csv_downloaded') + '</div>';
  } catch(e) {
    area.innerHTML = `<div class="alert alert-error">✗ ${esc(e.message)}</div>`;
  }
}

// ── History ─────────────────────────────────────────────────────────────────────
// The runs of the customer whose page is open: /api/history lists every
// customer this account reaches.
export async function loadHistory(customerId) {
  const box = document.getElementById('history-content');
  const d = await apiFetch('/api/history');
  if (customerId && customerId !== _custPage.id) return;
  if (d) {
    var runs = (d.history || []).filter(function(r) { return !customerId || r.customer_id === customerId; });
    setCustRuns(runs);
    renderHistory(runs, !!customerId);
    custSyncReportButton();
  } else {
    box.innerHTML = '<div class="alert alert-error">' + t('err_could_not_load_history') + '</div>';
  }
}

let _compareSelected = [];

function onCompareCheck(path, checked) {
  if (checked) {
    _compareSelected.push(path);
  } else {
    _compareSelected = _compareSelected.filter(p => p !== path);
  }
  var btnCompare = document.getElementById('btn-compare');
  var btnDelete = document.getElementById('btn-delete-selected');
  // Only allow compare if exactly 2 selected and both have metrics
  var canCompare = _compareSelected.length === 2;
  if (canCompare) {
    var cbs = document.querySelectorAll('input.compare-cb:checked');
    cbs.forEach(function(cb) {
      if (cb.dataset.hasMetrics === 'false') canCompare = false;
    });
  }
  btnCompare.style.display = canCompare ? 'inline-block' : 'none';
  btnDelete.style.display = _compareSelected.length > 0 ? 'inline-block' : 'none';
  btnDelete.textContent = t('btn_delete_selected') + ' (' + _compareSelected.length + ')';
}

export async function runComparison() {
  if (_compareSelected.length !== 2) {
    showToast(t('msg_select_2_for_compare'), 'warning');
    return;
  }
  const btn = document.getElementById('btn-compare');
  btn.disabled = true;
  btn.textContent = t('btn_loading');
  const box = document.getElementById('compare-result');
  box.style.display = 'block';
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  box.innerHTML = '<div class="text-center p-6"><div class="loader loader-lg mx-auto mt-0 mb-3"></div>' + t('msg_comparing') + '</div>';
  try {
    const d = await apiFetch('/api/audit/compare?run1=' + encodeURIComponent(_compareSelected[0]) + '&run2=' + encodeURIComponent(_compareSelected[1]));
    if (d.error) { box.innerHTML = `<div class="alert alert-error">${esc(d.error)}</div>`; return; }
    renderComparison(d, box);
    box.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    box.innerHTML = `<div class="alert alert-error">${t('status_error')}: ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = t('btn_compare_selected');
  }
}

export async function deleteSelectedRuns() {
  if (_compareSelected.length === 0) return;
  var count = _compareSelected.length;
  if (!await showConfirm(t('dlg_confirm_delete_runs').replace('{count}', count))) return;
  try {
    var d = await apiFetch('/api/history/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({paths: _compareSelected})
    });

    if (d.errors && d.errors.length > 0) {
      showToast(t('hist_deleted_runs').replace('{count}', d.deleted) + ' · ' + d.errors.join(', '), 'warning', 8000);
    }
    _compareSelected = [];
    document.getElementById('btn-delete-selected').style.display = 'none';
    document.getElementById('btn-compare').style.display = 'none';
    loadHistory();
  } catch (e) {
    showToast(t('err_delete_failed').replace('{msg}', e.message), 'error');
  }
}

async function deleteAllCustomerRuns(customerDirName, customerName, runCount) {
  if (!await showTypedConfirm(
    customerName,
    t('dlg_confirm_delete_all_runs').replace('{count}', runCount).replace('{name}', customerName),
    t('dlg_destructive_audit_history', 'Dette fjerner {count} audit-kjøringer og tilhørende rapporter for denne kunden. Ikke reversibelt.').replace('{count}', runCount)
  )) return;
  try {
    var d = await apiFetch('/api/history/delete-customer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({customer_dir: customerDirName})
    });

    if (d.error) {
      showToast(t('status_error') + ': ' + d.error, 'error');
      return;
    }
    _compareSelected = [];
    document.getElementById('btn-delete-selected').style.display = 'none';
    document.getElementById('btn-compare').style.display = 'none';
    loadHistory();
  } catch (e) {
    showToast(t('err_delete_failed').replace('{msg}', e.message), 'error');
  }
}

function renderComparison(data, box) {
  const labels = {
    risk_score: t('compare_risk_score'), risk_grade: t('compare_risk_grade'),
    mfa_coverage_pct: t('compare_mfa_coverage'), secure_score_pct: t('compare_secure_score'),
    total_users: t('compare_total_users'), users_no_mfa: t('compare_users_no_mfa'),
    ca_policies_enabled: t('compare_ca_policies'), intune_compliance_pct: t('compare_intune_compliance'),
    admin_roles_ga_count: t('compare_global_admins'), total_warns: t('compare_total_warnings'),
  };
  const ts1 = formatRunName(data.run1.timestamp), ts2 = formatRunName(data.run2.timestamp);
  let rows = '';
  for (const d of data.deltas) {
    const label = labels[d.key] || d.key;
    const v1 = d.run1 != null ? d.run1 : '\u2014';
    const v2 = d.run2 != null ? d.run2 : '\u2014';
    let arrow = '', tone = 'text-muted', row = '';
    if (d.direction === 'improved') { arrow = ' \u2191'; tone = 'text-success'; row = 'row-success'; }
    else if (d.direction === 'worsened') { arrow = ' \u2193'; tone = 'text-danger'; row = 'row-danger'; }
    else if (d.direction === 'unchanged') { arrow = ' \u2192'; tone = 'text-muted'; }
    else { arrow = ' ~'; tone = 'text-accent'; }
    const deltaStr = d.delta != null ? (d.delta > 0 ? '+' + d.delta : '' + d.delta) : '';
    const barWidth = d.delta != null ? Math.min(100, Math.abs(d.delta) * 2) : 0;
    const barHtml = barWidth > 0 ? `<span class="delta-bar" data-bar="${barWidth}"></span>` : '';
    rows += `<tr class="hover-tint ${row}">
      <td class="fw-medium">${esc(label)}</td>
      <td class="text-center font-mono">${esc(String(v1))}</td>
      <td class="text-center font-mono">${esc(String(v2))}</td>
      <td class="text-center fw-semibold font-mono ${tone}">${deltaStr ? esc(deltaStr) : ''}${arrow}${barHtml}</td>
    </tr>`;
  }
  box.innerHTML = `
    <div class="card mt-5 edge-accent">
      <div class="flex items-center justify-between mb-4">
        <div class="card-title m-0">${t('hdr_comparison')}</div>
        <button class="btn btn-ghost btn-sm" data-click-handler="hideElement" data-target="compare-result">${t('btn_close')}</button>
      </div>
      <div class="table-wrap">
        <table class="section-table w-full">
          <thead><tr>
            <th class="text-left">${t('lbl_metric')}</th>
            <th class="text-center text-muted">${esc(ts1)}</th>
            <th class="text-center text-accent">${esc(ts2)}</th>
            <th class="text-center">${t('lbl_change')}</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
}

function renderHistory(runs, scoped) {
  const box = document.getElementById('history-content');
  _compareSelected = [];
  document.getElementById('btn-compare').style.display = 'none';
  document.getElementById('compare-result').style.display = 'none';

  if (runs.length === 0) {
    // Kjør audit is in the page's head; this says there is nothing yet.
    box.innerHTML = '<div class="card cust-card-text">' + esc(t('msg_no_prev_runs')) + '</div>';
    return;
  }

  // Group by customer
  const grouped = {};
  for (const run of runs) {
    if (!grouped[run.customer]) grouped[run.customer] = [];
    grouped[run.customer].push(run);
  }

  let html = '';
  for (const [customer, customerRuns] of Object.entries(grouped)) {
    const customerDirName = customerRuns[0] && customerRuns[0].path ? customerRuns[0].path.split('/').slice(-2, -1)[0] : '';
    html += `<div class="card mb-4">
      <div class="card-title flex items-center justify-between">
        <span>
          ${scoped ? '' : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>' + esc(customer)} <span class="fw-normal text-sm text-muted">${customerRuns.length === 1 ? t('hist_runs_count_one', '(1 kjøring)') : t('hist_runs_count').replace('{count}', customerRuns.length)}</span>
        </span>
        <button class="btn btn-ghost btn-sm text-danger"
          data-click-handler="deleteAllCustomerRuns" data-dir="${esc(customerDirName)}" data-customer="${esc(customer)}" data-count="${customerRuns.length}">
          ${t('btn_delete_all')}
        </button>
      </div>
      <div class="table-wrap">
        <table class="section-table">
          <thead>
            <tr>
              <th class="col-check text-center" title="${t('tip_compare_delete')}">⇄</th>
              <th>${t('lbl_date_time')}</th>
              <th>${t('lbl_files')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>`;

    for (const run of customerRuns) {
      const displayDate = formatRunName(run.timestamp);
      // The full report is rebuilt from the run's evidence files. A run that
      // kept only its metrics still belongs in the history; it offers the
      // summary report, which reads the metrics.
      const hasEvidence = Number(run.file_count) > 0;

      const canCompare = run.has_metrics !== false;
      var runTip = canCompare && run.metrics ? t('lbl_grade')+': '+(run.metrics.risk_grade||'-')+' · Score: '+(run.metrics.risk_score||'-')+' · MFA: '+(metricPct(run.metrics.mfa_coverage_pct) !== null ? metricPct(run.metrics.mfa_coverage_pct)+'%' : '-') : '';
      html += `
        <tr${runTip ? ' title="'+esc(runTip)+'"' : ''} class="hover-tint cursor-pointer${canCompare ? '' : ' opacity-60'}">
          <td class="text-center">
            <input type="checkbox" class="compare-cb checkbox" data-path="${esc(run.path)}" data-has-metrics="${canCompare}"
              data-change-handler="onCompareCheck">
          </td>
          <td class="fw-medium">${esc(displayDate)}${canCompare ? '' : ' <span class="text-danger text-xs">' + t('ufullstendig') + '</span>'}${canCompare && run.metrics ? ' <span class="grade-tile grade-tile-sm ml-2 grade-' + esc(String(run.metrics.risk_grade || 'none')) + '">'+esc(run.metrics.risk_grade||'?')+'</span>' : ''}</td>
          <td class="hist-files">${hasEvidence ? Number(run.file_count) + ' ' + esc(t('nav_files', 'filer')) : esc(t('lbl_metrics_only', 'Bare nøkkeltall'))}</td>
          <td class="hist-action">
            ${hasEvidence
              ? '<button class="btn btn-primary btn-sm" data-click-handler="loadHistoryRun" data-path="' + esc(run.path) + '">' + esc(t('btn_generate_report')) + '</button>'
              : (run.customer_id
                ? '<button class="btn btn-default btn-sm" data-click-handler="openCustomerSummary" data-customer-id="' + esc(run.customer_id) + '" title="' + esc(t('tip_summary_report', 'Kjøringen har ingen bevisfiler, så hele rapporten kan ikke bygges. Sammendraget leser nøkkeltallene.')) + '">' + esc(t('btn_summary_report', 'Sammendragsrapport')) + '</button>'
                : '')}
          </td>
        </tr>`;
    }

    html += `</tbody></table></div></div>`;
  }

  box.innerHTML = html;
}

// A run picked in the list: the server selects it for this user and this
// customer, and the Rapport button builds from it.
async function loadHistoryRun(path) {
  const customerId = _custPage.id;
  const area = document.getElementById('report-result');
  if (area) area.innerHTML = '<div class="loader"></div> ' + esc(t('msg_loading_audit_data'));
  try {
    const d = await apiFetch('/api/history/load', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ customer_id: customerId, path }),
    });
    if (_custPage.id !== customerId) return;
    if (!d || d.error) {
      if (area) area.innerHTML = d && d.error ? '<div class="alert alert-error">✗ ' + esc(d.error) + '</div>' : '';
      return;
    }
    custReportFromRun(d.timestamp);
  } catch (e) {
    if (area) area.innerHTML = '<div class="alert alert-error">✗ ' + esc(t('err_network_error').replace('{msg}', e.message)) + '</div>';
  }
}
