// ═══════════════════════════════════════════════════════════════════
// TLS / CERTIFICATE MONITOR
// ═══════════════════════════════════════════════════════════════════

import {esc} from './app-esc.js';
import {t} from './app-i18n.js';
import {registerUiHandlers} from './app-handlers.js';
import {canWrite} from './app-state.js';
import {toneClass, toneVar} from './app-format.js';
import {showConfirm} from './app-ui.js';
import {apiFetch} from './app-api.js';
import {_notifDays} from './app-dashboard.js';

// Handlers for the controls tlsLoadView renders (see registerUiHandlers in app-handlers.js).
registerUiHandlers({
  tlsCheckSingle: function() { tlsCheckSingle(); },
  tlsAutoDiscover: function() { tlsAutoDiscover(); },
  tlsScanAll: function() { tlsScanAll(); },
  tlsForget: function(el) { tlsForget(el.dataset.host, Number(el.dataset.port)); },
});

export function tlsLoadView() {
  var el = document.getElementById('tls-content');

  // What the checks found, kept. First, because it is the answer to "which
  // certificates need attention"; the checks below are how it gets filled.
  var html = '<div class="card tls-known" id="tls-known"><div class="loading-note">' + esc(t('msg_tls_loading', 'Laster...')) + '</div></div>';

  // ── Quick-check card ──
  html += '<div class="card p-4 mb-4">';
  html += '<div class="text-base fw-semibold mb-3">' + t('tls_scan_single','Check single endpoint') + '</div>';
  html += '<div class="flex gap-2 items-end flex-wrap">';
  html += '<div><label class="field-label">' + t('tls_host','Host') + '</label>';
  html += '<input id="tls-host" type="text" placeholder="sybr.no" class="field-input input-medium"></div>';
  html += '<div><label class="field-label">' + t('tls_port','Port') + '</label>';
  html += '<input id="tls-port" type="number" value="443" class="field-input input-narrow"></div>';
  html += '<button class="btn btn-primary" data-click-handler="tlsCheckSingle">' + t('tls_check','Check') + '</button>';
  html += '</div>';
  html += '<div id="tls-single-result" class="mt-3"></div>';
  html += '</div>';

  // ── Auto-discover + batch scan card ──
  html += '<div class="card p-4 mb-4">';
  html += '<div class="flex items-center justify-between mb-3">';
  html += '<div class="text-base fw-semibold">' + t('tls_scan_batch','Scan all customer endpoints') + '</div>';
  html += '<div class="flex gap-2">';
  html += '<button class="btn btn-sm bg-input border text-default rounded cursor-pointer" data-click-handler="tlsAutoDiscover" id="tls-discover-btn">' + t('tls_auto_discover','Auto-oppdag') + '</button>';
  html += '<button class="btn btn-primary btn-sm" data-click-handler="tlsScanAll" id="tls-scan-btn">' + t('tls_check','Check') + '</button>';
  html += '</div></div>';
  html += '<div class="text-sm text-muted mb-2">' + t('tls_discovery_hint','Samler endepunkter fra SSH-verter, FortiGate og UniFi-konfigurasjoner.') + '</div>';
  html += '<div id="tls-discovered" class="mb-2"></div>';
  html += '<div id="tls-batch-result"></div>';
  html += '</div>';

  el.innerHTML = html;
  tlsLoadKnown();
}

// ── What the checks found, kept ──
//
// Every check (one endpoint, a scan, the nightly certificate check) stores
// what it saw on the server; this lists it. An endpoint that stopped
// answering keeps the certificate it was last seen with, marked as such.

function tlsStateLabel(status) {
  switch (status) {
    case 'expired': return t('tls_state_expired', 'Utløpt');
    case 'expiring': return t('tls_state_expiring', 'Utløper snart');
    case 'invalid_chain': return t('tls_state_invalid_chain', 'Ugyldig kjede');
    case 'unreachable': return t('tls_state_unreachable', 'Ikke nådd');
    case 'weak': return t('tls_state_weak', 'Svak TLS');
    case 'ok': return t('tls_state_ok', 'Gyldig');
    default: return t('tls_state_unknown', 'Ukjent');
  }
}

// Why a chain did not validate, as the server classifies it
// (app/services/tls_monitor.py, _CHAIN_PROBLEMS). Varsler uses it too.
export function tlsChainLabel(code) {
  switch (code) {
    case 'self_signed': return t('tls_chain_self_signed', 'Selvsignert sertifikat');
    case 'untrusted': return t('tls_chain_untrusted', 'Utstederen er ikke klarert');
    case 'incomplete_chain': return t('tls_chain_incomplete_chain', 'Mellomsertifikat mangler, eller utstederen er ukjent');
    case 'hostname_mismatch': return t('tls_chain_hostname_mismatch', 'Navnet passer ikke med sertifikatet');
    case 'expired': return t('tls_chain_expired', 'Sertifikatet er utløpt');
    case 'not_yet_valid': return t('tls_chain_not_yet_valid', 'Sertifikatet er ikke gyldig ennå');
    case 'revoked': return t('tls_chain_revoked', 'Sertifikatet er trukket tilbake');
    default: return t('tls_chain_other', 'Kjeden kunne ikke valideres');
  }
}

async function tlsLoadKnown() {
  var el = document.getElementById('tls-known');
  if (!el) return;
  var data = await apiFetch('/api/tls/certificates');
  if (!data) {
    el.innerHTML = '<p class="tls-known-hint">' + esc(t('tls_known_failed', 'Kunne ikke hente de lagrede sertifikatene.')) + '</p>';
    return;
  }
  el.innerHTML = _tlsKnownHtml(data.endpoints || []);
}

function _tlsKnownHtml(rows) {
  var html = '<div class="tls-known-head"><span class="tls-known-title">' + esc(t('tls_known_title', 'Kjente sertifikater'))
    + '</span><span class="tls-known-count">' + Number(rows.length) + '</span></div>';
  html += '<p class="tls-known-hint">' + esc(t('tls_known_hint', 'Det siste hver sjekk så. Sertifikatsjekken går gjennom listen hver natt, sammen med brannmurene og kontrollerne kundeoppsettet peker på.')) + '</p>';
  if (!rows.length) {
    return html + '<p class="tls-known-empty">' + esc(t('tls_known_empty', 'Ingen endepunkter er sjekket ennå. Sjekk ett nedenfor, eller skann kundenes endepunkter.')) + '</p>';
  }
  var write = canWrite();
  html += '<div class="tls-known-scroll"><table class="tls-table"><thead><tr>';
  html += '<th>' + esc(t('tls_status', 'Status')) + '</th>';
  html += '<th>' + esc(t('tls_endpoint', 'Endepunkt')) + '</th>';
  html += '<th>' + esc(t('col_customer', 'Kunde')) + '</th>';
  html += '<th>' + esc(t('tls_subject', 'Sertifikat')) + '</th>';
  html += '<th>' + esc(t('tls_expires', 'Utløper')) + '</th>';
  html += '<th>' + esc(t('tls_checked', 'Sjekket')) + '</th>';
  if (write) html += '<th><span class="sr-only">' + esc(t('btn_remove', 'Fjern')) + '</span></th>';
  html += '</tr></thead><tbody>';
  rows.forEach(function(r) {
    var days = (r.days_remaining === null || r.days_remaining === undefined) ? '' : Number(r.days_remaining);
    html += '<tr>';
    html += '<td><span class="tls-state tls-state--' + esc(r.status) + '">' + esc(tlsStateLabel(r.status)) + '</span></td>';
    html += '<td><span class="tls-endpoint">' + esc(r.host) + ':' + Number(r.port) + '</span>'
      + (r.label ? '<span class="tls-sub">' + esc(r.label) + '</span>' : '') + '</td>';
    html += '<td>' + esc(r.customer_name || '-') + '</td>';
    html += '<td>' + esc(r.subject || '-')
      + (r.issuer ? '<span class="tls-sub">' + esc(r.issuer) + '</span>' : '')
      + (r.chain_valid === false ? '<span class="tls-sub tls-warn">' + esc(tlsChainLabel(r.chain_problem)) + '</span>' : '')
      + '</td>';
    html += '<td>' + esc((r.not_after || '').slice(0, 10) || '-')
      + (days !== '' ? '<span class="tls-sub">' + esc(_notifDays(days)) + '</span>' : '') + '</td>';
    html += '<td>' + esc((r.checked_at || '').slice(0, 10) || '-')
      + (r.error ? '<span class="tls-sub tls-warn">' + esc(r.stale ? t('tls_last_check_failed', 'Siste sjekk nådde ikke fram') : r.error) + '</span>' : '')
      + '</td>';
    if (write) {
      html += '<td><button class="btn btn-default btn-sm" data-click-handler="tlsForget"'
        + ' data-host="' + esc(r.host) + '" data-port="' + Number(r.port) + '"'
        + ' aria-label="' + esc(t('tls_forget', 'Fjern fra listen')) + ': ' + esc(r.host) + '">'
        + esc(t('btn_remove', 'Fjern')) + '</button></td>';
    }
    html += '</tr>';
  });
  return html + '</tbody></table></div>';
}

async function tlsForget(host, port) {
  var ok = await showConfirm(
    t('tls_forget_title', 'Fjerne endepunktet fra listen?'),
    t('tls_forget_body', 'Det sjekkes ikke lenger hver natt. Et endepunkt kundeoppsettet peker på, kommer tilbake ved neste sjekk.')
  );
  if (!ok) return;
  var r = await apiFetch('/api/tls/certificates?host=' + encodeURIComponent(host) + '&port=' + Number(port), {method: 'DELETE'});
  if (r) tlsLoadKnown();
}

async function tlsCheckSingle() {
  var host = document.getElementById('tls-host').value.trim()
    .replace(/^https?:\/\//i, '').replace(/\/.*$/, '').replace(/:(\d+)$/, function(_,p){ document.getElementById('tls-port').value=p; return ''; });
  document.getElementById('tls-host').value = host;
  var port = parseInt(document.getElementById('tls-port').value) || 443;
  var el = document.getElementById('tls-single-result');
  if (!host) { el.innerHTML = '<span class="text-danger">' + t('tls_error','Feil') + ': ' + t('tls_host_required','Vert er påkrevd') + '</span>'; return; }

  el.innerHTML = '<div class="loader align-middle"></div> <span class="text-muted text-sm">' + t('tls_scanning','Scanning...') + '</span>';

  var data = await apiFetch('/api/tls/check', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({host:host, port:port})});
  if (!data) { el.innerHTML = '<span class="text-danger">' + t('tls_connect_failed','Feil ved tilkobling') + '</span>'; return; }
  el.innerHTML = _tlsRenderSingleResult(data);
  tlsLoadKnown();
}

function _tlsRenderSingleResult(r) {
  if (r.error) {
    return '<div class="card p-3 edge-danger">'
      + '<strong class="text-danger">' + t('tls_error','Error') + '</strong>: ' + esc(r.error) + '</div>';
  }

  var chainBad = r.chain_valid === false;
  var statusColor = r.expired ? 'var(--red)' : r.expiring_soon || chainBad || r.weak_protocol || r.weak_cipher ? 'var(--orange)' : 'var(--green)';
  var statusLabel = r.expired ? t('tls_expired','Expired') : r.expiring_soon ? t('tls_expiring_soon','Expiring soon') : chainBad ? tlsStateLabel('invalid_chain') : r.weak_protocol || r.weak_cipher ? t('tls_weak','Weak') : t('tls_valid','Valid');

  var html = '<div class="card p-4 edge-tone ' + toneVar(statusColor) + '">';
  html += '<div class="flex items-center gap-2 mb-3">';
  html += '<span class="dot dot-lg ' + toneClass(statusColor) + '"></span>';
  html += '<strong class="text-base">' + esc(r.host) + ':' + Number(r.port) + '</strong>';
  html += '<span class="text-sm ' + toneClass(statusColor) + ' fw-semibold">' + statusLabel + '</span>';
  html += '</div>';
  if (chainBad) html += '<p class="tls-warn tls-chain-note">' + esc(tlsChainLabel(r.chain_problem)) + '</p>';

  html += '<div class="grid grid-cols-2 gap-2 text-sm text-muted">';
  html += '<span>' + t('tls_subject','Certificate') + ': <strong class="text-default">' + esc(r.subject && r.subject.commonName || '-') + '</strong></span>';
  html += '<span>' + t('tls_issuer','Issuer') + ': ' + esc(r.issuer && r.issuer.organizationName || r.issuer && r.issuer.commonName || '-') + '</span>';
  html += '<span>' + t('tls_expires','Expires') + ': <strong class="' + (r.expired ? 'text-danger' : r.expiring_soon ? 'text-warning' : 'text-default') + '">' + (r.not_after ? esc(r.not_after.slice(0,10)) : '-') + '</strong></span>';
  html += '<span>' + t('tls_days_left','Days left') + ': <strong class="' + (r.days_remaining < 0 ? 'text-danger' : r.days_remaining < 30 ? 'text-warning' : 'text-success') + '">' + (r.days_remaining != null ? Number(r.days_remaining) : '-') + '</strong></span>';
  html += '<span>' + t('tls_protocol','Protocol') + ': <span class="fw-semibold ' + (r.weak_protocol ? 'text-danger' : 'text-success') + '">' + esc(r.protocol_version || '-') + '</span></span>';
  html += '<span>' + t('tls_cipher','Cipher') + ': <span class="' + (r.weak_cipher ? 'text-danger' : 'text-default') + '">' + esc(r.cipher || '-') + '</span>' + (r.key_bits ? ' (' + Number(r.key_bits) + ' bit)' : '') + '</span>';
  if (r.san && r.san.length) {
    html += '<span class="col-span-2">SAN: ' + r.san.map(function(s){return esc(s);}).join(', ') + '</span>';
  }
  html += '<span>S/N: <span class="font-mono text-xs">' + esc(r.serial_number || '-') + '</span></span>';
  html += '</div></div>';
  return html;
}

// ── Global: discovered endpoints (populated by auto-discover, used by scan) ──
var _tlsDiscoveredEndpoints = null;

async function tlsAutoDiscover() {
  var btn = document.getElementById('tls-discover-btn');
  var el = document.getElementById('tls-discovered');
  btn.disabled = true;
  btn.textContent = t('msg_discovering','Discovering …');
  el.innerHTML = '<div class="loader align-middle"></div> <span class="text-muted text-sm">' + t('tls_scanning_hosts','Skanner konfigurerte verter ...') + '</span>';

  var data = await apiFetch('/api/tls/auto-discover');
  btn.disabled = false;
  btn.textContent = t('btn_auto_discover','Auto-discover');

  if (!data || !data.endpoints || !data.endpoints.length) {
    el.innerHTML = '<span class="text-sm text-muted">' + t('tls_none_on_hosts','Ingen TLS-endepunkter funnet blant de konfigurerte vertene.') + '</span>';
    _tlsDiscoveredEndpoints = null;
    return;
  }

  _tlsDiscoveredEndpoints = data.endpoints;

  // Group by source for display
  var bySource = {};
  data.endpoints.forEach(function(ep) {
    var src = ep.source || 'other';
    if (!bySource[src]) bySource[src] = [];
    bySource[src].push(ep);
  });

  var html = '<div class="text-sm mb-1">';
  html += '<span class="text-success fw-semibold">' + Number(data.count) + '</span> endpoints discovered: ';
  var parts = [];
  var sourceLabels = {ssh:'SSH hosts', fortigate:'FortiGate', unifi:'UniFi'};
  for (var src in bySource) {
    parts.push(bySource[src].length + ' ' + esc(sourceLabels[src] || src));
  }
  html += parts.join(', ');
  html += '</div>';

  // Compact list of hosts
  html += '<div class="flex flex-wrap gap-1 mt-1">';
  data.endpoints.forEach(function(ep) {
    var srcColor = ep.source === 'fortigate' ? 'var(--orange)' : ep.source === 'unifi' ? 'var(--blue)' : 'var(--green)';
    html += '<span class="inline-block py-0-5 px-2 bg-input border rounded-full text-xs font-mono">';
    html += '<span class="' + toneClass(srcColor) + ' mr-1">&#9679;</span>';
    html += esc(ep.host) + ':' + Number(ep.port);
    html += '</span>';
  });
  html += '</div>';

  el.innerHTML = html;
}

async function tlsScanAll() {
  var el = document.getElementById('tls-batch-result');
  var btn = document.getElementById('tls-scan-btn');
  btn.disabled = true;
  btn.textContent = t('tls_scanning','Scanning...');

  el.innerHTML = '<div class="loader loader-md mx-auto my-4"></div><div class="text-center text-muted text-sm">' + t('tls_scanning','Scanning...') + '</div>';

  // Use auto-discovered endpoints if available, otherwise fetch from server
  var endpoints;
  if (_tlsDiscoveredEndpoints && _tlsDiscoveredEndpoints.length) {
    endpoints = _tlsDiscoveredEndpoints;
  } else {
    // Fallback: call auto-discover on the backend
    var discoverData = await apiFetch('/api/tls/auto-discover');
    endpoints = (discoverData && discoverData.endpoints) ? discoverData.endpoints : [];
  }

  if (!endpoints.length) {
    el.innerHTML = '<div class="empty-note is-compact">' + t('tls_no_endpoints','No endpoints found.') + '</div>';
    btn.disabled = false;
    btn.textContent = t('tls_check','Check');
    return;
  }

  var data = await apiFetch('/api/tls/scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({endpoints:endpoints})});
  btn.disabled = false;
  btn.textContent = t('tls_check','Check');

  if (!data || !data.results) {
    el.innerHTML = '<div class="text-danger text-center p-4">' + t('tls_error','Error') + '</div>';
    return;
  }
  tlsLoadKnown();

  // ── KPI summary row ──
  var html = '<div class="grid grid-cols-5 gap-3 mb-4">';
  var kpis = [
    {label:'Totalt', value:Number(data.total), color:'var(--blue)'},
    {label:t('tls_valid','Valid'), value:Number(data.valid), color:'var(--green)'},
    {label:t('tls_expired','Expired'), value:Number(data.expired), color:data.expired>0?'var(--red)':'var(--text-dim)'},
    {label:t('tls_expiring_soon','Expiring soon'), value:Number(data.expiring_soon), color:data.expiring_soon>0?'var(--orange)':'var(--text-dim)'},
    {label:t('tls_weak','Weak') + ' TLS', value:Number(data.weak_tls), color:data.weak_tls>0?'var(--orange)':'var(--text-dim)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card kpi-card ' + toneVar(k.color) + '">';
    html += '<div class="kpi-value ' + toneClass(k.color) + '">'+k.value+'</div>';
    html += '<div class="kpi-label">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // ── Results table ──
  html += '<div class="overflow-x-auto">';
  html += '<table class="data-table">';
  html += '<thead><tr class="bg-base">';
  html += '<th class="p-2">' + t('tls_status','Status') + '</th>';
  html += '<th class="p-2">' + t('tls_host','Host') + '</th>';
  html += '<th class="p-2">' + t('tls_subject','Certificate') + '</th>';
  html += '<th class="p-2">' + t('tls_issuer','Issuer') + '</th>';
  html += '<th class="text-center p-2">' + t('tls_days_left','Days left') + '</th>';
  html += '<th class="p-2">' + t('tls_protocol','Protocol') + '</th>';
  html += '<th class="p-2">' + t('tls_cipher','Cipher') + '</th>';
  html += '</tr></thead><tbody>';

  // Sort: errors first, then expired, then expiring_soon, then broken chains,
  // then weak, then valid
  data.results.sort(function(a,b) {
    function score(r) {
      if (r.error) return 0;
      if (r.expired) return 1;
      if (r.expiring_soon) return 2;
      if (r.chain_valid === false) return 3;
      if (r.weak_protocol || r.weak_cipher) return 4;
      return 5;
    }
    return score(a) - score(b);
  });

  data.results.forEach(function(r) {
    var statusColor, statusText, statusIcon;
    if (r.error) {
      statusColor = 'var(--red)'; statusText = t('tls_error','Error'); statusIcon = '&#10007;';
    } else if (r.expired) {
      statusColor = 'var(--red)'; statusText = t('tls_expired','Expired'); statusIcon = '&#10007;';
    } else if (r.expiring_soon) {
      statusColor = 'var(--orange)'; statusText = t('tls_expiring_soon','Expiring soon'); statusIcon = '';
    } else if (r.chain_valid === false) {
      statusColor = 'var(--orange)'; statusText = tlsStateLabel('invalid_chain'); statusIcon = '';
    } else if (r.weak_protocol || r.weak_cipher) {
      statusColor = 'var(--orange)'; statusText = t('tls_weak','Weak'); statusIcon = '';
    } else {
      statusColor = 'var(--green)'; statusText = t('tls_valid','Valid'); statusIcon = '&#10003;';
    }

    html += '<tr>';
    html += '<td class="p-2 nowrap"><span class="' + toneClass(statusColor) + ' fw-semibold">'+statusIcon+' '+statusText+'</span></td>';
    html += '<td class="p-2 font-mono text-xs">' + esc(r.host) + ':' + Number(r.port) + (r.label ? '<br><span class="text-2xs text-dim">' + esc(r.label) + '</span>' : '') + '</td>';

    if (r.error) {
      html += '<td colspan="5" class="p-2 text-danger text-xs">' + esc(r.error) + '</td>';
    } else {
      html += '<td class="p-2">' + esc(r.subject && r.subject.commonName || '-')
        + (r.chain_valid === false ? '<span class="tls-sub tls-warn">' + esc(tlsChainLabel(r.chain_problem)) + '</span>' : '') + '</td>';
      html += '<td class="p-2 text-muted">' + esc(r.issuer && (r.issuer.organizationName || r.issuer.commonName) || '-') + '</td>';

      var daysColor = r.days_remaining < 0 ? 'var(--red)' : r.days_remaining < 30 ? 'var(--orange)' : 'var(--green)';
      html += '<td class="p-2 text-center"><strong class="' + toneClass(daysColor) + '">' + (r.days_remaining != null ? Number(r.days_remaining) : '-') + '</strong></td>';

      var protoColor = r.weak_protocol ? 'var(--red)' : 'var(--green)';
      html += '<td class="p-2"><span class="' + toneClass(protoColor) + ' fw-semibold">' + esc(r.protocol_version || '-') + '</span></td>';

      var cipherColor = r.weak_cipher ? 'var(--red)' : 'var(--text-muted)';
      html += '<td class="p-2 text-xs ' + toneClass(cipherColor) + '">' + esc(r.cipher || '-') + (r.key_bits ? ' <span class="text-dim">(' + Number(r.key_bits) + 'b)</span>' : '') + '</td>';
    }
    html += '</tr>';
  });

  html += '</tbody></table></div>';
  html += '<div class="mt-2 text-xs text-dim">' + t('tls_scan_complete','Scan complete') + ' · ' + (data.scanned_at ? esc(data.scanned_at.slice(0,19).replace('T',' ')) : '') + ' UTC</div>';

  el.innerHTML = html;
}
