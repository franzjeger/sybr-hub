// ═══════════════════════════════════════════════════════════════════
// TLS / CERTIFICATE MONITOR
// ═══════════════════════════════════════════════════════════════════

function tlsLoadView() {
  var el = document.getElementById('tls-content');

  var html = '';

  // ── Quick-check card ──
  html += '<div class="card" style="padding:16px;margin-bottom:16px;">';
  html += '<div style="font-size:14px;font-weight:600;margin-bottom:12px;">' + t('tls_scan_single','Check single endpoint') + '</div>';
  html += '<div style="display:flex;gap:8px;align-items:end;flex-wrap:wrap;">';
  html += '<div><label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('tls_host','Host') + '</label>';
  html += '<input id="tls-host" type="text" placeholder="sybr.no" style="width:260px;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>';
  html += '<div><label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('tls_port','Port') + '</label>';
  html += '<input id="tls-port" type="number" value="443" style="width:80px;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>';
  html += '<button class="btn btn-primary" onclick="tlsCheckSingle()" style="padding:8px 20px;font-size:13px;">' + t('tls_check','Check') + '</button>';
  html += '</div>';
  html += '<div id="tls-single-result" style="margin-top:12px;"></div>';
  html += '</div>';

  // ── Auto-discover + batch scan card ──
  html += '<div class="card" style="padding:16px;margin-bottom:16px;">';
  html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">';
  html += '<div style="font-size:14px;font-weight:600;">' + t('tls_scan_batch','Scan all customer endpoints') + '</div>';
  html += '<div style="display:flex;gap:8px;">';
  html += '<button class="btn" onclick="tlsAutoDiscover()" id="tls-discover-btn" style="padding:6px 16px;font-size:12px;background:var(--bg-input);border:1px solid var(--border);color:var(--text);border-radius:6px;cursor:pointer;">' + t('tls_auto_discover','Auto-oppdag') + '</button>';
  html += '<button class="btn btn-primary" onclick="tlsScanAll()" id="tls-scan-btn" style="padding:6px 16px;font-size:12px;">' + t('tls_check','Check') + '</button>';
  html += '</div></div>';
  html += '<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">' + t('tls_discovery_hint','Samler endepunkter fra SSH-verter, FortiGate og UniFi-konfigurasjoner.') + '</div>';
  html += '<div id="tls-discovered" style="margin-bottom:8px;"></div>';
  html += '<div id="tls-batch-result"></div>';
  html += '</div>';

  el.innerHTML = html;
}

async function tlsCheckSingle() {
  var host = document.getElementById('tls-host').value.trim()
    .replace(/^https?:\/\//i, '').replace(/\/.*$/, '').replace(/:(\d+)$/, function(_,p){ document.getElementById('tls-port').value=p; return ''; });
  document.getElementById('tls-host').value = host;
  var port = parseInt(document.getElementById('tls-port').value) || 443;
  var el = document.getElementById('tls-single-result');
  if (!host) { el.innerHTML = '<span style="color:var(--red);">' + t('tls_error','Error') + ': ' + t('tls_host','Host') + ' required</span>'; return; }

  el.innerHTML = '<div class="loader" style="width:16px;height:16px;display:inline-block;vertical-align:middle;"></div> <span style="color:var(--text-muted);font-size:12px;">' + t('tls_scanning','Scanning...') + '</span>';

  var data = await apiFetch('/api/tls/check', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({host:host, port:port})});
  if (!data) { el.innerHTML = '<span style="color:var(--red);">' + t('tls_connect_failed','Feil ved tilkobling') + '</span>'; return; }
  el.innerHTML = _tlsRenderSingleResult(data);
}

function _tlsRenderSingleResult(r) {
  if (r.error) {
    return '<div class="card" style="padding:12px;border-left:3px solid var(--red);">'
      + '<strong style="color:var(--red);">' + t('tls_error','Error') + '</strong>: ' + esc(r.error) + '</div>';
  }

  var statusColor = r.expired ? 'var(--red)' : r.expiring_soon ? 'var(--orange)' : r.weak_protocol || r.weak_cipher ? 'var(--orange)' : 'var(--green)';
  var statusLabel = r.expired ? t('tls_expired','Expired') : r.expiring_soon ? t('tls_expiring_soon','Expiring soon') : r.weak_protocol || r.weak_cipher ? t('tls_weak','Weak') : t('tls_valid','Valid');

  var html = '<div class="card" style="padding:14px;border-left:3px solid '+statusColor+';">';
  html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">';
  html += '<span style="width:10px;height:10px;border-radius:50%;background:'+statusColor+';display:inline-block;"></span>';
  html += '<strong style="font-size:14px;">' + esc(r.host) + ':' + r.port + '</strong>';
  html += '<span style="font-size:12px;color:'+statusColor+';font-weight:600;">' + statusLabel + '</span>';
  html += '</div>';

  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px;color:var(--text-muted);">';
  html += '<span>' + t('tls_subject','Certificate') + ': <strong style="color:var(--text);">' + esc(r.subject && r.subject.commonName || '-') + '</strong></span>';
  html += '<span>' + t('tls_issuer','Issuer') + ': ' + esc(r.issuer && r.issuer.organizationName || r.issuer && r.issuer.commonName || '-') + '</span>';
  html += '<span>' + t('tls_expires','Expires') + ': <strong style="color:' + (r.expired ? 'var(--red)' : r.expiring_soon ? 'var(--orange)' : 'var(--text)') + ';">' + (r.not_after ? r.not_after.slice(0,10) : '-') + '</strong></span>';
  html += '<span>' + t('tls_days_left','Days left') + ': <strong style="color:' + (r.days_remaining < 0 ? 'var(--red)' : r.days_remaining < 30 ? 'var(--orange)' : 'var(--green)') + ';">' + (r.days_remaining != null ? r.days_remaining : '-') + '</strong></span>';
  html += '<span>' + t('tls_protocol','Protocol') + ': <span style="color:' + (r.weak_protocol ? 'var(--red)' : 'var(--green)') + ';font-weight:600;">' + esc(r.protocol_version || '-') + '</span></span>';
  html += '<span>' + t('tls_cipher','Cipher') + ': <span style="color:' + (r.weak_cipher ? 'var(--red)' : 'var(--text)') + ';">' + esc(r.cipher || '-') + '</span>' + (r.key_bits ? ' (' + r.key_bits + ' bit)' : '') + '</span>';
  if (r.san && r.san.length) {
    html += '<span style="grid-column:span 2;">SAN: ' + r.san.map(function(s){return esc(s);}).join(', ') + '</span>';
  }
  html += '<span>S/N: <span style="font-family:var(--mono);font-size:11px;">' + esc(r.serial_number || '-') + '</span></span>';
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
  el.innerHTML = '<div class="loader" style="width:14px;height:14px;display:inline-block;vertical-align:middle;"></div> <span style="color:var(--text-muted);font-size:12px;">' + t('tls_scanning_hosts','Skanner konfigurerte verter ...') + '</span>';

  var data = await apiFetch('/api/tls/auto-discover');
  btn.disabled = false;
  btn.textContent = t('btn_auto_discover','Auto-discover');

  if (!data || !data.endpoints || !data.endpoints.length) {
    el.innerHTML = '<span style="font-size:12px;color:var(--text-muted);">' + t('tls_none_on_hosts','Ingen TLS-endepunkter funnet blant de konfigurerte vertene.') + '</span>';
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

  var html = '<div style="font-size:12px;margin-bottom:4px;">';
  html += '<span style="color:var(--green);font-weight:600;">' + data.count + '</span> endpoints discovered: ';
  var parts = [];
  var sourceLabels = {ssh:'SSH hosts', fortigate:'FortiGate', unifi:'UniFi'};
  for (var src in bySource) {
    parts.push(bySource[src].length + ' ' + (sourceLabels[src] || src));
  }
  html += parts.join(', ');
  html += '</div>';

  // Compact list of hosts
  html += '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;">';
  data.endpoints.forEach(function(ep) {
    var srcColor = ep.source === 'fortigate' ? 'var(--orange)' : ep.source === 'unifi' ? 'var(--blue)' : 'var(--green)';
    html += '<span style="display:inline-block;padding:2px 8px;background:var(--bg-input);border:1px solid var(--border);border-radius:12px;font-size:11px;font-family:var(--mono);">';
    html += '<span style="color:'+srcColor+';margin-right:4px;">&#9679;</span>';
    html += esc(ep.host) + ':' + ep.port;
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

  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:16px auto;"></div><div style="text-align:center;color:var(--text-muted);font-size:12px;">' + t('tls_scanning','Scanning...') + '</div>';

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
    el.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:24px;">' + t('tls_no_endpoints','No endpoints found.') + '</div>';
    btn.disabled = false;
    btn.textContent = t('tls_check','Check');
    return;
  }

  var data = await apiFetch('/api/tls/scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({endpoints:endpoints})});
  btn.disabled = false;
  btn.textContent = t('tls_check','Check');

  if (!data || !data.results) {
    el.innerHTML = '<div style="color:var(--red);text-align:center;padding:16px;">' + t('tls_error','Error') + '</div>';
    return;
  }

  // ── KPI summary row ──
  var html = '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:'Totalt', value:data.total, color:'var(--blue)'},
    {label:t('tls_valid','Valid'), value:data.valid, color:'var(--green)'},
    {label:t('tls_expired','Expired'), value:data.expired, color:data.expired>0?'var(--red)':'var(--text-dim)'},
    {label:t('tls_expiring_soon','Expiring soon'), value:data.expiring_soon, color:data.expiring_soon>0?'var(--orange)':'var(--text-dim)'},
    {label:t('tls_weak','Weak') + ' TLS', value:data.weak_tls, color:data.weak_tls>0?'var(--orange)':'var(--text-dim)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card" style="padding:16px 8px;text-align:center;border-top:2px solid '+k.color+';height:90px;box-sizing:border-box;">';
    html += '<div style="font-size:22px;font-weight:700;line-height:24px;color:'+k.color+';">'+k.value+'</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);line-height:16px;">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // ── Results table ──
  html += '<div style="overflow-x:auto;">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="border-bottom:2px solid var(--border);background:var(--bg);">';
  html += '<th style="text-align:left;padding:8px;">' + t('tls_status','Status') + '</th>';
  html += '<th style="text-align:left;padding:8px;">' + t('tls_host','Host') + '</th>';
  html += '<th style="text-align:left;padding:8px;">' + t('tls_subject','Certificate') + '</th>';
  html += '<th style="text-align:left;padding:8px;">' + t('tls_issuer','Issuer') + '</th>';
  html += '<th style="text-align:center;padding:8px;">' + t('tls_days_left','Days left') + '</th>';
  html += '<th style="text-align:left;padding:8px;">' + t('tls_protocol','Protocol') + '</th>';
  html += '<th style="text-align:left;padding:8px;">' + t('tls_cipher','Cipher') + '</th>';
  html += '</tr></thead><tbody>';

  // Sort: errors first, then expired, then expiring_soon, then weak, then valid
  data.results.sort(function(a,b) {
    function score(r) {
      if (r.error) return 0;
      if (r.expired) return 1;
      if (r.expiring_soon) return 2;
      if (r.weak_protocol || r.weak_cipher) return 3;
      return 4;
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
    } else if (r.weak_protocol || r.weak_cipher) {
      statusColor = 'var(--orange)'; statusText = t('tls_weak','Weak'); statusIcon = '';
    } else {
      statusColor = 'var(--green)'; statusText = t('tls_valid','Valid'); statusIcon = '&#10003;';
    }

    html += '<tr style="border-bottom:1px solid var(--border);">';
    html += '<td style="padding:8px;white-space:nowrap;"><span style="color:'+statusColor+';font-weight:600;">'+statusIcon+' '+statusText+'</span></td>';
    html += '<td style="padding:8px;font-family:var(--mono);font-size:11px;">' + esc(r.host) + ':' + r.port + (r.label ? '<br><span style="font-family:inherit;font-size:10px;color:var(--text-dim);">' + esc(r.label) + '</span>' : '') + '</td>';

    if (r.error) {
      html += '<td colspan="5" style="padding:8px;color:var(--red);font-size:11px;">' + esc(r.error) + '</td>';
    } else {
      html += '<td style="padding:8px;">' + esc(r.subject && r.subject.commonName || '-') + '</td>';
      html += '<td style="padding:8px;color:var(--text-muted);">' + esc(r.issuer && (r.issuer.organizationName || r.issuer.commonName) || '-') + '</td>';

      var daysColor = r.days_remaining < 0 ? 'var(--red)' : r.days_remaining < 30 ? 'var(--orange)' : 'var(--green)';
      html += '<td style="padding:8px;text-align:center;"><strong style="color:'+daysColor+';">' + (r.days_remaining != null ? r.days_remaining : '-') + '</strong></td>';

      var protoColor = r.weak_protocol ? 'var(--red)' : 'var(--green)';
      html += '<td style="padding:8px;"><span style="color:'+protoColor+';font-weight:600;">' + esc(r.protocol_version || '-') + '</span></td>';

      var cipherColor = r.weak_cipher ? 'var(--red)' : 'var(--text-muted)';
      html += '<td style="padding:8px;font-size:11px;color:'+cipherColor+';">' + esc(r.cipher || '-') + (r.key_bits ? ' <span style="color:var(--text-dim);">(' + r.key_bits + 'b)</span>' : '') + '</td>';
    }
    html += '</tr>';
  });

  html += '</tbody></table></div>';
  html += '<div style="margin-top:8px;font-size:11px;color:var(--text-dim);">' + t('tls_scan_complete','Scan complete') + ' — ' + (data.scanned_at ? data.scanned_at.slice(0,19).replace('T',' ') : '') + ' UTC</div>';

  el.innerHTML = html;
}

