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

function _poCustomerId() {
  return _customersActiveId || '';
}
function _poCustomerName() {
  var c = (_allCustomers || []).find(function(x) {
    return (x._id || x.customer_id) === _poCustomerId();
  });
  return (c && (c.CustomerName || c.customer_name)) || '';
}

async function policyOverviewLoad() {
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
      + (po.run ? ' &middot; ' + esc(po.run) : '');
    html += '</div>';
    html += _poWorkloadBlocks(po.workloads || {});
  }

  html += _poDriftBlock(po.drift || {});
  html += _poStandardBlock(po.standards || []);
  el.innerHTML = html;
}

function _poStatePill(code) {
  var cls = {
    'on':          'po-badge-on',
    'report-only': 'po-badge-report',
    'off':         'po-badge-off',
    'trusted':     'po-badge-trusted',
  }[code] || 'po-badge-unknown';
  var label = {
    'on':          t('lbl_policy_on', 'On'),
    'report-only': t('lbl_policy_report', 'Report-only'),
    'off':         t('lbl_policy_off', 'Off'),
    'trusted':     t('lbl_policy_trusted', 'Trusted'),
  }[code] || esc(code || '?');
  return '<span class="po-badge ' + cls + '">' + label + '</span>';
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
      + ' <span class="po-sub-count">(' + (wl.count || 0) + ')</span>'
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
                + '<span class="po-hint-dim">&#9656;</span> '
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
    out = out.split('{' + k + '}').join(String(params[k] || ''));
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
    + t('lbl_drift_against', 'Against run') + ': ' + esc(d.compared_with || '—')
    + ' &middot; '
    + '<span class="po-dr-add">' + (d.added_total || 0) + ' ' + t('lbl_added', 'added') + '</span>'
    + ' / '
    + '<span class="po-dr-rem">' + (d.removed_total || 0) + ' ' + t('lbl_removed', 'removed') + '</span>'
    + ' / '
    + '<span class="po-dr-chg">' + (d.changed_total || 0) + ' ' + t('lbl_changed', 'changed') + '</span>'
    + ' &middot; '
    + (d.snapshots || []).reduce(function(acc, s) { return acc + (s.unchanged || 0); }, 0)
    + ' ' + t('lbl_unchanged', 'unchanged')
    + '</div>';

  (d.snapshots || []).forEach(function(s) {
    var labelEsc = esc(s.name);
    if (s.comparable) {
      html += '<div class="po-sep">';
      html += '<div class="po-sep-title">' + labelEsc + '</div>';
      html += _poDriftList('po-dr-add', s.added || [], 'lbl_added');
      html += _poDriftList('po-dr-rem', s.removed || [], 'lbl_removed');
      if (s.changed && s.changed.length) {
        html += _poDriftList('po-dr-chg', s.changed || [], 'lbl_changed', true);
      }
      html += '</div>';
    } else {
      html += '<div class="po-sep-muted">'
        + '<span class="po-sep-title">' + labelEsc + '</span> — '
        + esc(_poReason('drift_', s.reason_code, s.reason_params)
               || t('msg_po_snap_unmeasured', 'not comparable against the previous run'))
        + '</div>';
    }
  });
  html += '</div>';
  return html;
}

function _poDriftList(cls, items, labelKey, withFields) {
  if (!items.length) return '';
  var html = '<div class="po-listline">';
  html += '<span class="' + cls + '">' + t(labelKey, labelKey) + ': </span>';
  html += items.map(function(p) {
    var s = esc(p.name || p.id || '');
    if (withFields && p.fields && p.fields.length) {
      s += ' <span class="po-fields">(' + p.fields.map(esc).join(', ') + ')</span>';
    }
    return s;
  }).join(', ');
  html += '</div>';
  return html;
}

function _poStandardBlock(standards) {
  if (!standards.length) return '';
  var html = '<div class="card">';
  html += '<div class="po-sec">' + t('hdr_std_gap', 'Avstand til Sybr-standarden') + '</div>';

  standards.forEach(function(std) {
    var missing = (std.policies || []).filter(function(p) { return !p.present; }).length;
    var total = (std.policies || []).length;
    html += '<div class="po-block">';
    html += '<div class="po-std-head">'
      + esc(std.name || std.id)
      + ' <span class="po-std-meta">v' + esc(std.version || '') + '</span>'
      + ' <span class="po-std-meta">' + missing + '/' + total + ' ' + t('lbl_missing', 'missing') + '</span>'
      + '</div>';
    html += '<table class="po-tbl">';
    (std.policies || []).forEach(function(p) {
      html += '<tr class="po-row">';
      html += '<td class="po-std-statecell">'
        + (p.present ? _poStatePill(p.state || 'on') : '<span class="po-absent">&#9572;</span>')
        + '</td>';
      html += '<td class="po-std-name">' + esc(p.name);
      if (p.why) html += '<div class="po-std-why">' + esc(p.why) + '</div>';
      html += '</td>';
      html += '<td class="po-std-statuscell' + (p.present ? '' : ' po-std-statuscell-missing') + '">'
        + (p.present ? esc(p.state || 'on') : t('lbl_std_missing', 'Ikke til stede'))
        + '</td></tr>';
    });
    html += '</table></div>';
  });
  html += '</div>';
  return html;
}
