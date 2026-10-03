// ═══════════════════════════════════════════════════════════════════
// POLICY OVERVIEW — one screen that answers:
//   • what the customer has in production (by workload, with a summary
//     line the interface can read in its own language);
//   • what changed on the tenant since the last audit (drift) — or
//     that it could not be measured, and why;
//   • how far the tenant is from the Sybr standards, by name.
// Read-only: every value is composed on the server from the existing
// inventory + drift + templates. Nothing here is sent to a tenant.
// Styles are in app.css: the CSP budget counts inline style=, so new
// screens are expected to build on classes (the assessment library does).
// ═══════════════════════════════════════════════════════════════════

import {esc} from './app-esc.js';
import {_lang, t} from './app-i18n.js';
import {_custPage} from './app-state.js';
import {formatRunName} from './app-format.js';
import {apiFetch} from './app-api.js';

// The customer whose page this tab is on.
function _poCustomerId() {
  return _custPage.id || '';
}
function _poCustomerName() {
  return (_custPage.cust && _custPage.cust.customer_name) || '';
}

export async function policyOverviewLoad() {
  var el = document.getElementById('policy-overview-content');
  if (!el) return;
  el.innerHTML = '<div class="po-loading"><div class="loader"></div></div>';

  var cid = _poCustomerId();
  if (!cid) {
    el.innerHTML = '<div class="card po-dim">'
      + esc(t('msg_no_customer_selected', 'No customer selected')) + '</div>';
    return;
  }

  var po = await apiFetch('/api/policy-overview/' + encodeURIComponent(cid) + '?lang=' + _lang)
    .catch(function() { return null; });
  // Another customer's page opened meanwhile: this answer is not its.
  if (_poCustomerId() !== cid) return;
  if (!po) {
    el.innerHTML = '<div class="alert alert-error">' + esc(t('status_error', 'Error')) + '</div>';
    return;
  }

  var cust = _poCustomerName();
  var html = '';

  if (!po.inventory_present) {
    html += '<div class="card po-dim">'
      + esc(t('msg_po_no_audit', 'No policies captured yet — run an audit first')) + '</div>';
  } else {
    html += '<div class="po-meta">'
      + esc(cust ? cust : cid)
      + ' &middot; ' + t('lbl_captured', 'Captured')
      + ': ' + esc((po.captured_at || '').slice(0, 10))
      + (po.run ? ' &middot; ' + esc(formatRunName(po.run)) : '');
    html += '</div>';
    html += _poWorkloadBlocks(po.workloads || {});
  }

  html += _poDriftBlock(po.drift || {});
  html += _poStandardBlock(po.standards || []);
  el.innerHTML = html;
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

function _poLoc(v) {
  if (v == null) return '';
  if (typeof v === 'string') return v;
  return (v && (v[_lang] || v.no || v.en)) || '';
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
        html += '<div style="display:flex; flex-direction:column; gap:4px; margin-top:8px;">';
        html += _poDriftList('add', s.added || []);
        html += _poDriftList('rem', s.removed || []);
        html += _poDriftList('chg', s.changed || [], true);
        html += '</div></div>';
      } else {
        html += '<div class="po-sep-muted"><span class="po-sep-title" style="display:inline-flex; align-items:center; margin:0 8px 0 0; color:var(--text);">' + labelEsc + '</span> · ' + t('lbl_unchanged', 'unchanged') + '</div>';
      }
    } else {
      html += '<div class="po-sep-muted">'
        + '<span class="po-sep-title" style="display:inline-flex; align-items:center; margin:0 8px 0 0; color:var(--text);">' + labelEsc + '</span> · '
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
      + '<span class="po-std-meta" style="font-weight:600;">'
      + (measured
        ? present + '/' + total + ' ' + t('lbl_implemented', 'implemented') + ' (' + pct + '%)'
        : esc(t('lbl_std_unmeasured', 'ikke målt')))
      + '</span>'
      + '</div>';
    if (measured) {
      html += '<div class="po-progress-wrap" style="margin-bottom:16px;"><div class="po-progress-fill' + pcls + '" style="width:' + pct + '%;"></div></div>';
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
