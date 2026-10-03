// ═══════════════════════════════════════════════════════════════════
// SHARED UI: toasts, confirm dialogs, the login screen and page furniture
// ═══════════════════════════════════════════════════════════════════

// ── Toast notification system ─────────────────────────────────────────────────
registerUiHandlers({
  dismissToast: function(el) { dismissToast(el.parentNode); },
  retryToast: function(el) { retryToast(el.closest('.toast')); },
});

function showToast(message, type, duration) {
  if (type === undefined) type = 'error';
  if (duration === undefined) duration = 5000;
  var container = document.getElementById('toast-container');
  if (!container) return;
  var toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.innerHTML = '<div class="toast-body">' + esc(message) + '</div>' +
    '<button class="toast-close" data-click-handler="dismissToast" aria-label="' + t('btn_close') + '">&times;</button>';
  container.appendChild(toast);
  if (duration > 0) {
    setTimeout(function() { dismissToast(toast); }, duration);
  }
  return toast;
}

function showToastWithRetry(message, retryFn, type, dedupeKey) {
  if (type === undefined) type = 'error';
  var container = document.getElementById('toast-container');
  if (!container) return;
  if (dedupeKey) {
    var existing = Array.from(container.children).find(function(el) {
      return el.dataset.errorKey === dedupeKey && !el.classList.contains('removing');
    });
    if (existing) return existing;
  }
  var toast = document.createElement('div');
  if (dedupeKey) toast.dataset.errorKey = dedupeKey;
  toast.dataset.retryId = _toastRetryId;
  toast.className = 'toast toast-' + type;
  toast.innerHTML = '<div class="toast-body">' + esc(message) +
    '<div class="toast-actions"><button data-click-handler="retryToast">' +
    t('toast_retry') + '</button></div></div>' +
    '<button class="toast-close" data-click-handler="dismissToast" aria-label="' + t('btn_close') + '">&times;</button>';
  _toastRetryFns[_toastRetryId] = retryFn;
  _toastRetryId++;
  container.appendChild(toast);
  return toast;
}
var _toastRetryId = 0;
// Each retry toast's action, by its data-retry-id, until it is dismissed.
var _toastRetryFns = {};

function retryToast(el) {
  var retryFn = el && _toastRetryFns[el.dataset.retryId];
  dismissToast(el);
  if (retryFn) retryFn();
}

function dismissToast(el) {
  if (!el || el.classList.contains('removing')) return;
  if (el.dataset.retryId) delete _toastRetryFns[el.dataset.retryId];
  el.classList.add('removing');
  setTimeout(function() { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
}

// ── Global error handlers ─────────────────────────────────────────────────────
window.onerror = function(msg, src, line, col, err) {
  var display = (err && err.message) ? err.message : String(msg);
  if (display.length > 120) display = display.substring(0, 120) + '...';
  showToast(t('toast_unexpected_error').replace('{msg}', display), 'error');
};
window.onunhandledrejection = function(event) {
  var reason = event.reason;
  var display = (reason && reason.message) ? reason.message : String(reason);
  if (display.length > 120) display = display.substring(0, 120) + '...';
  showToast(t('toast_unexpected_error').replace('{msg}', display), 'error');
};

// ── Styled confirm modal (replaces native confirm()) ─────────────────────────
var _confirmResolver = null;
// ── Empty-state helper ──────────────────────────────────────────────────────
// Generates consistent markup for "no X yet" states. Use in place of ad-hoc
//   '<div style="...">No data</div>'
// strings.
//   emptyStateHTML({
//     icon: '📭', title: 'Ingen enheter', desc: 'Legg til din første…',
//     variant: 'inline',   // or omit for full-card
//   })
// It once took an `actions` list of buttons whose onclick was a JavaScript
// string. Nothing used it, and the CSP no longer runs inline handlers.
function emptyStateHTML(opts) {
  opts = opts || {};
  var cls = opts.variant === 'inline' ? 'empty-state-inline' : 'empty-state';
  var parts = ['<div class="' + cls + '">'];
  if (opts.icon) parts.push('<div class="empty-icon">' + esc(opts.icon) + '</div>');
  if (opts.title) parts.push('<div class="empty-title">' + esc(opts.title) + '</div>');
  if (opts.desc) parts.push('<div class="empty-desc">' + esc(opts.desc) + '</div>');
  parts.push('</div>');
  return parts.join('');
}

function showConfirm(title, body) {
  return new Promise(function(resolve) {
    _confirmResolver = resolve;
    document.getElementById('confirm-modal-title').textContent = title;
    var bodyEl = document.getElementById('confirm-modal-body');
    bodyEl.textContent = body || '';
    bodyEl.style.display = body ? 'block' : 'none';
    var modal = document.getElementById('confirm-modal');
    modal.style.display = 'flex';
    document.getElementById('confirm-modal-ok').focus();
  });
}

// Confirm dialog that requires the user to type the exact subject (usually
// a customer or user name) before the destructive button is enabled. Use
// for actions that are hard to reverse — deletes, bulk wipes, etc.
//
//   if (!await showTypedConfirm(customer.name, "Slett kunde", "Dette sletter alle audits, rapporter og credentials permanent.")) return;
function showTypedConfirm(subject, title, body) {
  return new Promise(function(resolve) {
    _confirmResolver = resolve;
    document.getElementById('confirm-modal-title').textContent = title;
    var bodyEl = document.getElementById('confirm-modal-body');

    // Build a body that stays purely DOM (no innerHTML with user subject) so
    // an attacker-controlled customer name can't slip in markup.
    bodyEl.innerHTML = '';
    if (body) {
      var p = document.createElement('div');
      p.textContent = body;
      bodyEl.appendChild(p);
    }
    var hint = document.createElement('div');
    hint.style.cssText = 'margin-top:12px;font-size:11px;color:var(--text-dim);';
    hint.appendChild(document.createTextNode(t('lbl_type_to_confirm', 'Skriv') + ' '));
    var strong = document.createElement('strong');
    strong.style.cssText = 'color:var(--text);font-family:var(--mono);';
    strong.textContent = subject;
    hint.appendChild(strong);
    hint.appendChild(document.createTextNode(' ' + t('lbl_type_to_confirm_suffix', 'for å bekrefte:')));
    bodyEl.appendChild(hint);

    var input = document.createElement('input');
    input.id = 'confirm-modal-input';
    input.type = 'text';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.style.cssText = 'margin-top:8px;width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg);color:var(--text);font-family:var(--mono);font-size:13px;box-sizing:border-box;';
    bodyEl.appendChild(input);
    bodyEl.style.display = 'block';

    var ok = document.getElementById('confirm-modal-ok');
    ok.disabled = true;
    ok.style.opacity = '0.5';
    ok.style.cursor = 'not-allowed';

    input.addEventListener('input', function() {
      var match = input.value === subject;
      ok.disabled = !match;
      ok.style.opacity = match ? '' : '0.5';
      ok.style.cursor = match ? '' : 'not-allowed';
    });
    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && input.value === subject) {
        e.preventDefault();
        resolveConfirm(true);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        resolveConfirm(false);
      }
    });

    var modal = document.getElementById('confirm-modal');
    modal.style.display = 'flex';
    setTimeout(function() { input.focus(); }, 50);
  });
}

function resolveConfirm(val) {
  document.getElementById('confirm-modal').style.display = 'none';
  // Reset the OK button in case this was a typed-confirm
  var ok = document.getElementById('confirm-modal-ok');
  if (ok) {
    ok.disabled = false;
    ok.style.opacity = '';
    ok.style.cursor = '';
  }
  if (_confirmResolver) { _confirmResolver(val); _confirmResolver = null; }
}

// ── Login screen ──────────────────────────────────────────────────────────────
function showLoginView(mode) {
  loginViewShown();
  var el = document.getElementById('auth-overlay');
  if (!el) return;
  el.style.display = 'flex';
  document.querySelector('header').style.display = 'none';
  var _bnLogin = document.getElementById('bottom-nav'); if (_bnLogin) _bnLogin.style.display = 'none';
  document.getElementById('auth-setup-form').style.display = mode === 'setup' ? 'block' : 'none';
  document.getElementById('auth-login-form').style.display = mode === 'login' ? 'block' : 'none';
  // Show version in login
  fetch('/api/version').then(function(r){return r.json()}).then(function(d){
    var lv = document.getElementById('login-version'); if (lv) lv.textContent = 'v' + (d.version||'');
  }).catch(function(){});
}

function hideLoginView() {
  var el = document.getElementById('auth-overlay');
  if (el) el.style.display = 'none';
  document.querySelector('header').style.display = '';
  var _bnApp = document.getElementById('bottom-nav'); if (_bnApp) _bnApp.style.display = '';
}

// Sets a button's label without discarding the icon in front of it. Buttons
// that carry one are markup of the form
//   <button><span class="ic">…svg…</span><span data-i18n="key">Label</span></button>
// and btn.textContent = '…' flattens both spans into a bare string, so the
// icon disappeared the first time the button changed state and never came
// back. Writing to the label span leaves the icon alone.
function setButtonLabel(btn, text) {
  if (!btn) return;
  var label = btn.querySelector('[data-i18n]');
  if (label) label.textContent = text;
  else btn.textContent = text;
}

// ── Reusable sortable table utility ──────────────────────────────────────────
function makeSortable(tableEl) {
  if (!tableEl) return;
  var thead = tableEl.querySelector('thead');
  if (!thead) return;
  var ths = thead.querySelectorAll('th');
  ths.forEach(function(th, colIdx) {
    // Skip columns that are too narrow / utility (checkboxes, empty, icon-only)
    if (th.querySelector('input[type="checkbox"]')) return;
    if (th.textContent.trim().length === 0 && !th.getAttribute('data-sort-key')) return;
    th.classList.add('sortable');
    th.setAttribute('data-col-idx', colIdx);
    th.addEventListener('click', function() {
      var asc = true;
      if (th.classList.contains('sort-asc')) { asc = false; }
      // Clear sort state on all siblings
      ths.forEach(function(s) { s.classList.remove('sort-asc', 'sort-desc'); });
      th.classList.add(asc ? 'sort-asc' : 'sort-desc');
      _sortTableByCol(tableEl, colIdx, asc);
    });
  });
}

function _sortTableByCol(tableEl, colIdx, asc) {
  var tbody = tableEl.querySelector('tbody');
  if (!tbody) return;
  var rows = Array.from(tbody.querySelectorAll('tr'));
  // Separate data rows from separator/subtotal rows, cache cells once
  var dataRows = [];
  var otherRows = [];
  var cellCache = new Map();
  rows.forEach(function(r) {
    var cells = r.querySelectorAll('td');
    if (cells.length <= 1 && r.querySelector('td[colspan]')) {
      otherRows.push(r);
    } else {
      dataRows.push(r);
      cellCache.set(r, cells);
    }
  });
  // Pre-extract sort values to avoid DOM reads during sort
  var sortValues = new Map();
  dataRows.forEach(function(r) {
    var cell = cellCache.get(r)[colIdx];
    if (cell) {
      var v = (cell.getAttribute('data-sort-value') || cell.textContent).trim();
      sortValues.set(r, v);
    }
  });
  dataRows.sort(function(a, b) {
    var va = sortValues.get(a) || '';
    var vb = sortValues.get(b) || '';
    var na = parseFloat(va.replace(/[^0-9.\-]/g, ''));
    var nb = parseFloat(vb.replace(/[^0-9.\-]/g, ''));
    if (!isNaN(na) && !isNaN(nb)) {
      return asc ? na - nb : nb - na;
    }
    var cmp = va.localeCompare(vb, 'no', {sensitivity: 'base'});
    return asc ? cmp : -cmp;
  });
  // Re-append in sorted order
  dataRows.forEach(function(r) { tbody.appendChild(r); });
  otherRows.forEach(function(r) { tbody.appendChild(r); });
}

// ── Skeleton loading ───────────────────────────────────────────────────────────
function skeletonHTML(type) {
  var s = '<div class="skeleton ';
  var row = s + 'skeleton-row"></div>';
  var text = s + 'skeleton-text"></div>';
  var textW = '<div class="skeleton skeleton-text" style="width:50%"></div>';
  var title = s + 'skeleton-title"></div>';
  if (type === 'home') {
    return '<div class="skeleton-card">' + title +
      '<div class="skeleton skeleton-title" style="width:60%;height:24px;margin-bottom:6px;"></div>' +
      '<div class="skeleton skeleton-text" style="width:35%;margin-bottom:16px;"></div>' +
      '<div style="display:flex;gap:24px;flex-wrap:wrap;">' +
        '<div class="skeleton skeleton-metric"></div>' +
        '<div class="skeleton skeleton-metric"></div>' +
        '<div class="skeleton skeleton-metric"></div>' +
      '</div>' +
      '<div style="display:flex;gap:10px;margin-top:20px;">' +
        '<div class="skeleton" style="width:120px;height:36px;border-radius:6px;"></div>' +
        '<div class="skeleton" style="width:140px;height:36px;border-radius:6px;"></div>' +
      '</div></div>' +
      '<div class="skeleton-card" style="margin-top:16px;">' + title + text + text + textW + '</div>';
  }
  if (type === 'dashboard') {
    var cards = '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:20px;">' +
      '<div class="skeleton skeleton-metric"></div><div class="skeleton skeleton-metric"></div><div class="skeleton skeleton-metric"></div></div>';
    var rows = '';
    for (var i = 0; i < 5; i++) rows += row;
    return cards + '<div class="skeleton-card">' + title + rows + '</div>';
  }
  if (type === 'customers') {
    var html = '';
    for (var j = 0; j < 3; j++) {
      html += '<div class="skeleton-card"><div style="display:flex;align-items:center;gap:12px;"><div style="flex:1;">' +
        '<div class="skeleton skeleton-title" style="width:40%;"></div>' +
        '<div class="skeleton skeleton-text" style="width:30%;"></div>' +
        '<div style="display:flex;gap:24px;margin-top:8px;"><div class="skeleton" style="width:80px;height:14px;border-radius:4px;"></div>' +
        '<div class="skeleton" style="width:100px;height:14px;border-radius:4px;"></div></div></div>' +
        '<div class="skeleton" style="width:90px;height:36px;border-radius:6px;"></div></div></div>';
    }
    return html;
  }
  if (type === 'files') {
    var html2 = '';
    for (var k = 0; k < 4; k++) {
      html2 += '<div class="skeleton-card">' + title +
        '<div class="skeleton skeleton-text" style="width:70%;"></div>' +
        '<div class="skeleton skeleton-text" style="width:55%;"></div>' + textW + '</div>';
    }
    return html2;
  }
  if (type === 'history') {
    var html3 = '';
    for (var m = 0; m < 6; m++) html3 += row;
    return html3;
  }
  return '';
}

// A button to a pane of Administrasjon, for the places that say "set this up
// under Administrasjon". Nothing for an account that cannot open the page:
// the sentence beside it still says where, for the administrator to act on.
function adminSignpostButton(pane, labelKey, extraClass) {
  if (!canOpenView('admin')) return '';
  return '<button class="btn ' + esc(extraClass || 'btn-default btn-sm') + '" data-click-handler="openAdmin" data-pane="' + esc(pane) + '">'
    + esc(t(labelKey)) + '</button>';
}

// Opens a generated HTML report (tenant and scan data) in a new window. The
// report is parsed inside an iframe sandboxed without allow-scripts, so no
// handler or script in it can run as the app. allow-same-origin and
// allow-modals are only there for this wrapper: it sizes the frame to the
// report and sends Ctrl+P to the report itself, which then paginates at paper
// width instead of printing one screen of the wrapper.
function openReportWindow(html, title) {
  var win = window.open('', '_blank');
  if (!win) return null;
  var doc = win.document;
  doc.title = title;
  doc.body.style.margin = '0';
  var frame = doc.createElement('iframe');
  frame.setAttribute('sandbox', 'allow-same-origin allow-modals');
  frame.title = title;
  frame.style.cssText = 'display:block;width:100%;height:100vh;border:0;';
  function fit() {
    var root = frame.contentDocument && frame.contentDocument.documentElement;
    if (!root) return;
    frame.style.height = '0';
    frame.style.height = root.scrollHeight + 'px';
  }
  function printReport(e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'p' || e.key === 'P')) {
      e.preventDefault();
      frame.contentWindow.print();
    }
  }
  frame.addEventListener('load', function() {
    fit();
    frame.contentDocument.addEventListener('keydown', printReport);
  });
  win.addEventListener('resize', fit);
  doc.addEventListener('keydown', printReport);
  frame.srcdoc = /* safe-html: parsed in the script-less sandbox above */ html;
  doc.body.appendChild(frame);
  return win;
}
