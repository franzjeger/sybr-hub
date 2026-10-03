// ═══════════════════════════════════════════════════════════════════
// FINDINGS: what the newest audit found for one customer, and what to do
// ═══════════════════════════════════════════════════════════════════
//
// One component, used on the customer page and on M365-status. It always
// names its customer: nothing here reads the per-user "active customer" a
// second tab can change.
//
// The list offers only actions that can work right now. A ticket button
// appears when Autotask is configured and this customer is linked; a plan
// button likewise for myITprocess. When an integration is configured but the
// customer is not linked, one notice above the list says so, instead of a
// dead button on every row.
//
// Controls carry data-action attributes and one delegated listener per mount
// handles them, so no customer data ever sits inside inline JavaScript.

var _FINDING_SEVERITIES = ['critical', 'high', 'medium', 'low'];
var _FINDING_STATUSES = ['open', 'in_progress', 'done', 'ignored'];
var _FINDING_CLOSED = {done: true, ignored: true};

var _PUSH = {
  ticket: {
    system: 'autotask',
    endpoint: 'tickets',
    field: 'ticket',
    badge: 'lbl_ticket_exists',
    button: 'btn_create_ticket',
    heading: 'hdr_new_ticket',
    submit: 'btn_ticket_submit',
    created: 'msg_ticket_created',
    exists: 'msg_ticket_exists',
    duplicate: 'msg_ticket_duplicate',
  },
  plan: {
    system: 'myitprocess',
    endpoint: 'recommendations',
    field: 'plan',
    badge: 'lbl_recommendation_exists',
    button: 'btn_push_recommendation',
    heading: 'hdr_new_recommendation',
    submit: 'btn_rec_submit',
    created: 'msg_rec_created',
    exists: 'msg_rec_exists',
    duplicate: 'msg_rec_duplicate',
  },
};

var _LINK_SYSTEMS = {
  autotask: {label: 'Autotask', field: 'autotask_account_id'},
  myitprocess: {label: 'myITprocess', field: 'myitprocess_account_id'},
  itglue: {label: 'IT Glue', field: 'itglue_org_id'},
};

function _findingsCanAct() {
  return !!(_currentUser && _currentUser.role !== 'viewer' && canWrite());
}

function _severityLabel(sev) {
  return t('sev_' + sev, sev);
}

function _statusLabel(st) {
  return {
    open: t('status_open', 'Åpen'),
    in_progress: t('status_in_progress', 'Pågår'),
    done: t('status_done_label', 'Utført'),
    ignored: t('status_ignored', 'Ignorert'),
  }[st] || st;
}

// Mount the findings list for one customer into `el`. Returns a promise that
// settles when the first render is done. `opts.onLinked` runs after a link
// changes, so the page around the list can refresh its own chips.
async function mountCustomerFindings(el, customerId, opts) {
  if (!el) return;
  var state = {customerId: customerId, data: null, showClosed: false, opts: opts || {}};
  el._findings = state;
  if (!el._findingsWired) {
    el.addEventListener('click', function(e) { _onFindingsClick(el, e); });
    el.addEventListener('change', function(e) { _onFindingsChange(el, e); });
    el._findingsWired = true;
  }
  el.innerHTML = '<div class="findings-loading"><div class="loader"></div></div>';
  await _reloadFindings(el);
}

async function _reloadFindings(el) {
  var state = el._findings;
  var d = await apiFetch('/api/hub/' + encodeURIComponent(state.customerId) + '/findings');
  // A different customer may have been mounted while this was in flight.
  if (el._findings !== state) return;
  if (!d) {
    el.innerHTML = '<div class="findings-notice is-error">' + esc(t('err_findings_unavailable', 'Kunne ikke hente funn.')) + '</div>';
    return;
  }
  state.data = d;
  _renderFindings(el);
}

function _renderFindings(el) {
  var state = el._findings;
  var d = state.data;
  var findings = d.findings || [];
  var counts = {open: 0, in_progress: 0, closed: 0};
  findings.forEach(function(f) {
    if (_FINDING_CLOSED[f.status]) counts.closed++;
    else if (f.status === 'in_progress') counts.in_progress++;
    else counts.open++;
  });

  var head = '<div class="findings-head">'
    + '<h2 class="section-title">' + esc(t('hdr_findings', 'Funn'))
    + (findings.length ? ' <span class="section-count">' + Number(findings.length) + '</span>' : '')
    + '</h2>';
  if (findings.length) {
    head += '<span class="findings-summary">'
      + esc(t('msg_findings_summary', '{open} åpne · {progress} pågår · {closed} lukket')
        .replace('{open}', counts.open).replace('{progress}', counts.in_progress).replace('{closed}', counts.closed))
      + '</span>';
    if (counts.closed) {
      head += '<button class="btn btn-ghost btn-sm" data-action="toggle-closed">'
        + esc(state.showClosed
          ? t('btn_hide_closed', 'Skjul lukkede')
          : t('btn_show_closed', 'Vis lukkede ({n})').replace('{n}', counts.closed))
        + '</button>';
    }
  }
  head += '</div>';

  var body = _findingsNotices(d);
  if (!d.audit_date) {
    body += '<div class="findings-empty">'
      + '<div class="findings-empty-title">' + esc(t('msg_findings_never_title', 'Ikke auditert ennå')) + '</div>'
      + '<div class="findings-empty-desc">' + esc(t('msg_findings_never_desc', 'Kjør en audit for å se hva som må rettes hos denne kunden.')) + '</div>'
      + '</div>';
  } else if (!findings.length) {
    body += '<div class="findings-empty">'
      + '<div class="findings-empty-title">' + esc(t('msg_findings_none_title', 'Ingen funn i siste audit')) + '</div>'
      + '<div class="findings-empty-desc">' + esc(t('msg_findings_none_desc', 'Auditen {date} fant ingenting å rette.').replace('{date}', _auditDateLabel(d.audit_date))) + '</div>'
      + '</div>';
  } else {
    var visible = findings.filter(function(f) { return state.showClosed || !_FINDING_CLOSED[f.status]; });
    body += '<ol class="finding-list">' + visible.map(function(f) { return _findingRow(f, d); }).join('') + '</ol>';
    if (!visible.length) {
      body += '<div class="findings-empty"><div class="findings-empty-desc">'
        + esc(t('msg_findings_all_closed', 'Alle funn er lukket.')) + '</div></div>';
    }
  }
  el.innerHTML = '<section class="findings">' + head + body + '</section>';
}

function _auditDateLabel(runName) {
  var date = String(runName || '').substring(0, 10);
  var parsed = new Date(date);
  if (isNaN(parsed.getTime())) return date;
  return parsed.toLocaleDateString(_lang === 'en' ? 'en-GB' : 'nb-NO', {day: 'numeric', month: 'long', year: 'numeric'});
}

// One line above the list for each action that is configured but not yet
// possible for this customer, so the reason is said once, where it applies.
function _findingsNotices(d) {
  if (!_findingsCanAct() || !(d.findings || []).length) return '';
  var integ = d.integrations || {};
  var out = '';
  ['autotask', 'myitprocess'].forEach(function(sys) {
    var s = integ[sys] || {};
    if (s.configured && !s.linked) {
      out += '<div class="findings-notice">'
        + '<span>' + esc(t('msg_link_to_push_' + sys, sys === 'autotask'
          ? 'Koble kunden til Autotask for å lage saker av funnene.'
          : 'Koble kunden til myITprocess for å legge funn til planleggingen.')) + '</span>'
        + '<button class="btn btn-default btn-sm" data-action="link" data-system="' + esc(sys) + '">'
        + esc(t('btn_link_system', 'Koble til {system}').replace('{system}', _LINK_SYSTEMS[sys].label)) + '</button>'
        + '</div>';
    }
  });
  if (!(integ.autotask || {}).configured && !(integ.myitprocess || {}).configured && hasFeature('integrations')) {
    out += '<div class="findings-notice is-muted">'
      + '<span>' + esc(t('msg_setup_psa_to_push', 'Sett opp Autotask eller myITprocess for å lage saker av funn.')) + '</span>'
      + '<button class="btn btn-ghost btn-sm" data-action="goto-integrations">' + esc(t('nav_integrations', 'Integrasjoner')) + '</button>'
      + '</div>';
  }
  return out;
}

function _findingRow(f, d) {
  var sev = _FINDING_SEVERITIES.indexOf(f.priority) === -1 ? 'medium' : f.priority;
  var closed = _FINDING_CLOSED[f.status];
  var canAct = _findingsCanAct();
  var actions = '';
  if (canAct) {
    actions += '<select class="finding-status" data-action="status" aria-label="' + esc(t('lbl_status', 'Status')) + '">'
      + _FINDING_STATUSES.map(function(st) {
        return '<option value="' + st + '"' + (st === f.status ? ' selected' : '') + '>' + esc(_statusLabel(st)) + '</option>';
      }).join('')
      + '</select>';
  } else {
    actions += '<span class="finding-status-label status-' + esc(f.status) + '">' + esc(_statusLabel(f.status)) + '</span>';
  }
  actions += _pushControl(f, d, 'ticket', canAct) + _pushControl(f, d, 'plan', canAct);
  if (canAct) {
    actions += '<button class="btn btn-ghost btn-sm" data-action="note">'
      + esc(f.notes ? t('btn_edit_note', 'Endre notat') : t('btn_add_note', 'Notat')) + '</button>';
  }

  return '<li class="finding' + (closed ? ' is-closed' : '') + '" data-rec="' + esc(f.rec_id) + '">'
    + '<span class="sev-chip sev-' + esc(sev) + '">' + esc(_severityLabel(sev)) + '</span>'
    + '<div class="finding-body">'
    + '<div class="finding-title">' + esc(f.title) + '</div>'
    + (f.detail ? '<div class="finding-detail">' + esc(f.detail) + '</div>' : '')
    + (f.notes ? '<div class="finding-note">' + esc(f.notes) + '</div>' : '')
    + '<div class="finding-actions">' + actions + '</div>'
    + '<div class="finding-panel" hidden></div>'
    + '</div></li>';
}

function _pushControl(f, d, kind, canAct) {
  var cfg = _PUSH[kind];
  var done = f[cfg.field];
  if (done) {
    var label = esc(t(cfg.badge) + ' #' + done.external_id);
    return done.external_url
      ? '<a class="push-done" href="' + esc(done.external_url) + '" target="_blank" rel="noopener noreferrer">' + label + '</a>'
      : '<span class="push-done">' + label + '</span>';
  }
  var integ = (d.integrations || {})[cfg.system] || {};
  if (!canAct || !integ.configured || !integ.linked) return '';
  return '<button class="btn btn-default btn-sm" data-action="push" data-kind="' + esc(kind) + '">' + esc(t(cfg.button)) + '</button>';
}

function _findingFor(el, row) {
  var recId = row && row.dataset.rec;
  return (el._findings.data.findings || []).find(function(f) { return f.rec_id === recId; });
}

async function _onFindingsClick(el, e) {
  var control = e.target.closest('[data-action]');
  if (!control || !el.contains(control)) return;
  var action = control.dataset.action;
  var state = el._findings;
  if (action === 'status') return;  // handled on change
  if (action === 'toggle-closed') {
    state.showClosed = !state.showClosed;
    _renderFindings(el);
  } else if (action === 'goto-integrations') {
    showView('integrations');
  } else if (action === 'link') {
    openLinkPicker(state.customerId, state.data.customer_name, control.dataset.system, function() {
      _reloadFindings(el);
      if (state.opts.onLinked) state.opts.onLinked();
    });
  } else if (action === 'push') {
    _openPushPanel(el, control.closest('.finding'), control.dataset.kind);
  } else if (action === 'note') {
    _openNotePanel(el, control.closest('.finding'));
  } else if (action === 'submit-push') {
    await _submitPush(el, control);
  } else if (action === 'save-note') {
    var row = control.closest('.finding');
    var f = _findingFor(el, row);
    var notes = row.querySelector('.finding-note-input').value.trim();
    await _saveStatus(el, f, f.status, notes);
  } else if (action === 'close-panel') {
    var panel = control.closest('.finding-panel');
    panel.hidden = true;
    panel.innerHTML = '';
  }
}

async function _onFindingsChange(el, e) {
  var select = e.target.closest('[data-action="status"]');
  if (!select) return;
  var f = _findingFor(el, select.closest('.finding'));
  if (f) await _saveStatus(el, f, select.value, f.notes || '');
}

async function _saveStatus(el, f, status, notes) {
  var d = await apiFetch('/api/hub/' + encodeURIComponent(el._findings.customerId) + '/findings/status', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({rec_id: f.rec_id, status: status, notes: notes}),
  });
  if (!d || !d.ok) { _renderFindings(el); return; }
  f.status = status;
  f.notes = notes;
  _renderFindings(el);
}

function _openPanel(row, html) {
  var panel = row.querySelector('.finding-panel');
  panel.innerHTML = /* safe-html: callers assemble it from esc()-ed parts */ html;
  panel.hidden = false;
  var first = panel.querySelector('input, select, textarea');
  if (first) first.focus();
  return panel;
}

function _openPushPanel(el, row, kind) {
  var cfg = _PUSH[kind];
  var f = _findingFor(el, row);
  if (!f) return;
  var fields = '';
  if (kind === 'ticket') {
    var suggested = {critical: 1, high: 2, medium: 3, low: 4}[f.priority] || 3;
    fields = '<label class="tk-label">' + esc(t('lbl_ticket_priority'))
      + '<select class="tk-field tk-priority">'
      + [[1, 'prio_critical'], [2, 'prio_high'], [3, 'prio_medium'], [4, 'prio_low']].map(function(p) {
        return '<option value="' + p[0] + '"' + (p[0] === suggested ? ' selected' : '') + '>' + esc(t(p[1])) + '</option>';
      }).join('')
      + '</select></label>';
  } else {
    // Free text: myITprocess vocabularies have not been seen from a live
    // instance, and a dropdown of guessed values is worse than a field.
    fields = '<label class="tk-label">' + esc(t('lbl_rec_category'))
      + '<input type="text" class="tk-field tk-category" maxlength="100"></label>'
      + '<label class="tk-label">' + esc(t('lbl_rec_priority'))
      + '<input type="text" class="tk-field tk-rec-priority" maxlength="50" placeholder="' + esc(_severityLabel(f.priority)) + '"></label>';
  }
  var panel = _openPanel(row, '<div class="tk-head">' + esc(t(cfg.heading)) + '</div>'
    + '<div class="tk-form">'
    + '<label class="tk-label tk-wide">' + esc(t('lbl_ticket_title'))
    + '<input type="text" class="tk-field tk-title" maxlength="255" value="' + esc(f.title) + '"></label>'
    + '<div class="tk-row">' + fields + '</div>'
    + '<label class="tk-label tk-wide">' + esc(t('lbl_ticket_notes'))
    + '<input type="text" class="tk-field tk-notes" maxlength="4000" placeholder="' + esc(t('tip_ticket_notes')) + '"></label>'
    + '<div class="tk-buttons">'
    + '<button class="btn btn-primary btn-sm" data-action="submit-push">' + esc(t(cfg.submit)) + '</button>'
    + '<button class="btn btn-ghost btn-sm" data-action="close-panel">' + esc(t('btn_cancel', 'Avbryt')) + '</button>'
    + '</div></div>');
  panel.dataset.kind = kind;
}

function _openNotePanel(el, row) {
  var f = _findingFor(el, row);
  if (!f) return;
  _openPanel(row, '<div class="tk-form">'
    + '<label class="tk-label tk-wide">' + esc(t('lbl_note', 'Notat'))
    + '<textarea class="tk-field finding-note-input" maxlength="4000" rows="2">' + esc(f.notes || '') + '</textarea></label>'
    + '<div class="tk-buttons">'
    + '<button class="btn btn-primary btn-sm" data-action="save-note">' + esc(t('btn_save', 'Lagre')) + '</button>'
    + '<button class="btn btn-ghost btn-sm" data-action="close-panel">' + esc(t('btn_cancel', 'Avbryt')) + '</button>'
    + '</div></div>');
}

async function _submitPush(el, btn) {
  var row = btn.closest('.finding');
  var panel = row.querySelector('.finding-panel');
  var kind = panel.dataset.kind;
  var cfg = _PUSH[kind];
  var f = _findingFor(el, row);
  function val(sel) { var node = panel.querySelector(sel); return node ? node.value.trim() : ''; }
  var body = {rec_id: f.rec_id, title: val('.tk-title'), notes: val('.tk-notes')};
  if (kind === 'ticket') {
    body.priority = parseInt(val('.tk-priority'), 10);
  } else {
    body.category = val('.tk-category');
    body.priority = val('.tk-rec-priority');
  }
  // Disabled while in flight: the server's idempotency is the safety net,
  // not the first line of defence against a double click.
  btn.disabled = true;
  var d = await apiFetch('/api/hub/' + encodeURIComponent(el._findings.customerId) + '/' + cfg.endpoint, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  if (!d || !d.ok) { btn.disabled = false; return; }
  f[cfg.field] = d.ticket;
  var id = '#' + d.ticket.external_id;
  if (d.duplicate_ticket_id) {
    // A real, unowned record exists in the other system. Saying so is the
    // point; otherwise the customer is the one to find it.
    showToast(t(cfg.duplicate).replace('{dup}', '#' + d.duplicate_ticket_id).replace('{id}', id), 'warning');
  } else if (d.created) {
    showToast(t(cfg.created).replace('{id}', id), 'success');
  } else {
    showToast(t(cfg.exists).replace('{id}', id), 'info');
  }
  _renderFindings(el);
}

// ── Link a customer to its PSA / documentation record ────────────────────────

function _nameScore(candidate, wanted) {
  var a = String(candidate || '').toLowerCase();
  var b = String(wanted || '').toLowerCase().replace(/\b(as|asa|ab|ltd|inc|gmbh)\b/g, '').trim();
  if (!b) return 0;
  if (a === b) return 3;
  if (a.indexOf(b) === 0) return 2;
  return a.indexOf(b) !== -1 ? 1 : 0;
}

async function _fetchLinkCandidates(system, query) {
  var d;
  if (system === 'autotask') {
    d = await apiFetch('/api/autotask/accounts?limit=50&search=' + encodeURIComponent(query || ''));
    return d ? d.accounts || [] : null;
  }
  if (system === 'myitprocess') {
    d = await apiFetch('/api/myitprocess/accounts');
    return d ? d.accounts || [] : null;
  }
  d = await apiFetch('/api/itglue/organizations', {method: 'POST'});
  return d ? d.organizations || [] : null;
}

// A modal to pick the record this customer is in the other system. Suggests
// by name; the server refuses a record another customer already holds.
function openLinkPicker(customerId, customerName, system, onDone) {
  var sys = _LINK_SYSTEMS[system];
  if (!sys) return;
  var backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop open';
  backdrop.setAttribute('role', 'dialog');
  backdrop.setAttribute('aria-modal', 'true');
  backdrop.innerHTML = '<div class="modal link-picker">'
    + '<div class="modal-title">' + esc(t('hdr_link_picker', 'Koble {customer} til {system}').replace('{customer}', customerName || '').replace('{system}', sys.label)) + '</div>'
    + '<input type="search" class="link-search" placeholder="' + esc(t('ph_link_search', 'Søk etter navn')) + '" value="' + esc(customerName || '') + '">'
    + '<div class="link-results" role="listbox"><div class="findings-loading"><div class="loader"></div></div></div>'
    + '<div class="modal-actions">'
    + '<button class="btn btn-ghost" data-action="unlink">' + esc(t('btn_unlink', 'Fjern kobling')) + '</button>'
    + '<button class="btn btn-default" data-action="close">' + esc(t('btn_close', 'Lukk')) + '</button>'
    + '</div></div>';
  document.body.appendChild(backdrop);

  var search = backdrop.querySelector('.link-search');
  var results = backdrop.querySelector('.link-results');
  var all = null;
  var timer = null;

  function close() {
    document.removeEventListener('keydown', onKey);
    backdrop.remove();
  }
  function onKey(e) { if (e.key === 'Escape') close(); }
  document.addEventListener('keydown', onKey);

  function render(list) {
    var q = search.value.trim();
    var shown = system === 'autotask' ? list : list.filter(function(r) {
      return !q || String(r.name || '').toLowerCase().indexOf(q.toLowerCase()) !== -1;
    });
    shown = shown.slice().sort(function(x, y) { return _nameScore(y.name, customerName) - _nameScore(x.name, customerName); });
    results.innerHTML = shown.length
      ? shown.slice(0, 50).map(function(r) {
        return '<button class="link-result" role="option" data-id="' + esc(String(r.id)) + '">'
          + '<span>' + esc(r.name || String(r.id)) + '</span><span class="link-result-id">' + esc(String(r.id)) + '</span></button>';
      }).join('')
      : '<div class="findings-empty-desc">' + esc(t('msg_link_no_results', 'Ingen treff')) + '</div>';
  }

  async function load() {
    var list = await _fetchLinkCandidates(system, search.value.trim());
    if (!document.body.contains(backdrop)) return;
    if (list === null) {
      results.innerHTML = '<div class="findings-notice is-error">' + esc(t('err_link_list_unavailable', 'Kunne ikke hente listen fra {system}.').replace('{system}', sys.label)) + '</div>';
      return;
    }
    all = list;
    render(all);
  }

  async function save(value) {
    var body = {};
    body[sys.field] = value;
    var d = await apiFetch('/api/hub/' + encodeURIComponent(customerId) + '/link', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (!d || !d.ok) return;
    showToast(value === null
      ? t('msg_link_removed', 'Koblingen er fjernet')
      : t('msg_link_saved', 'Kunden er koblet til {system}').replace('{system}', sys.label), 'success');
    close();
    if (onDone) onDone();
  }

  search.addEventListener('input', function() {
    if (system === 'autotask') {
      clearTimeout(timer);
      timer = setTimeout(load, 300);
    } else if (all) {
      render(all);
    }
  });
  backdrop.addEventListener('click', function(e) {
    if (e.target === backdrop) return close();
    var pick = e.target.closest('.link-result');
    if (pick) return save(pick.dataset.id);
    var action = e.target.closest('[data-action]');
    if (!action) return;
    if (action.dataset.action === 'close') close();
    else if (action.dataset.action === 'unlink') save(null);
  });
  search.focus();
  search.select();
  load();
}
