// ═══════════════════════════════════════════════════════════════════
// TAILSCALE INTEGRATION
// ═══════════════════════════════════════════════════════════════════

async function tsTestConnection() {
  var msg = document.getElementById('ts-config-msg');
  msg.innerHTML = '<span style="color:var(--text-muted);">' + t('msg_testing','Testing...') + '</span>';
  try {
    var d = await apiFetch('/api/tailscale/test', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        api_key: document.getElementById('input-ts-api-key').value.trim(),
        tailnet: document.getElementById('input-ts-tailnet').value.trim() || '-',
      })
    });
    if (d && d.ok) {
      msg.innerHTML = '<span style="color:var(--green);">&#10003; ' + t('msg_connection_verified','Connection verified') + ' — ' + d.device_count + ' ' + t('ts_devices_suffix','enheter') + '</span>';
      document.getElementById('ts-integ-dot').style.background = 'var(--green)';
      document.getElementById('ts-integ-label').textContent = d.device_count + ' devices';
      document.getElementById('ts-integ-label').style.color = 'var(--green)';
    } else {
      msg.innerHTML = '<span style="color:var(--red);">&#10007; ' + esc(d && d.error ? d.error : t('status_error')) + '</span>';
    }
  } catch(e) {
    msg.innerHTML = '<span style="color:var(--red);">' + esc(e.message) + '</span>';
  }
}

async function tsSaveConfig() {
  var msg = document.getElementById('ts-config-msg');
  var settings = await apiFetch('/api/settings');
  var body = Object.assign({}, settings || {}, {
    tailscale_api_key: document.getElementById('input-ts-api-key').value.trim(),
    tailscale_tailnet: document.getElementById('input-ts-tailnet').value.trim() || '-',
  });
  var d = await apiFetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  if (d && !d.error) {
    msg.innerHTML = '<span style="color:var(--green);">&#10003; ' + t('msg_saved','Saved') + '</span>';
  } else {
    msg.innerHTML = '<span style="color:var(--red);">' + esc(d && d.error ? d.error : t('status_error')) + '</span>';
  }
}

// ── Tailscale Dashboard View ────────────────────────────────────────────────

var _tsDevices = [];

function tsLoadView() {
  var el = document.getElementById('ts-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div><div style="text-align:center;color:var(--text-muted);font-size:12px;">' + t('msg_loading','Loading...') + '</div>';
  tsLoadDevices();
}

async function tsLoadDevices() {
  var el = document.getElementById('ts-content');
  var data = await apiFetch('/api/tailscale/devices');
  if (!data || data.error) {
    el.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:48px;">'
      + (data && data.error ? esc(data.error) : t('ts_not_configured','Tailscale not configured. Go to Settings → Integrations.'))
      + '</div>';
    return;
  }

  var devices = data.devices || [];
  _tsDevices = devices;
  if (!devices.length) {
    el.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:48px;">' + t('ts_no_devices','No devices found in your tailnet.') + '</div>';
    return;
  }

  // ── KPI summary row ──
  var html = '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:t('ts_total','Total'), value:data.total, color:'var(--blue)'},
    {label:t('ts_online','Online'), value:data.online, color:'var(--green)'},
    {label:t('ts_offline','Offline'), value:data.offline, color:data.offline>0?'var(--orange)':'var(--text-dim)'},
    {label:t('ts_stale','Stale (>7d)'), value:data.stale, color:data.stale>0?'var(--red)':'var(--text-dim)'},
    {label:t('ts_key_expiring','Key expiring'), value:data.expiring_keys, color:data.expiring_keys>0?'var(--orange)':'var(--text-dim)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card" style="padding:16px 8px;text-align:center;border-top:2px solid '+k.color+';height:90px;box-sizing:border-box;">';
    html += '<div style="font-size:22px;font-weight:700;line-height:24px;color:'+k.color+';">'+k.value+'</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);line-height:16px;">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // ── Action bar ──
  html += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">';
  html += '<button class="btn btn-ghost" onclick="tsLoadDevices()" style="padding:4px 12px;font-size:11px;">' + t('btn_refresh','Refresh') + '</button>';
  html += '<button class="btn btn-primary" onclick="tsShowCreateKey()" style="padding:4px 12px;font-size:11px;">' + t('ts_create_key','Create auth key') + '</button>';
  html += '<button class="btn btn-ghost" onclick="tsShowKeys()" style="padding:4px 12px;font-size:11px;">' + t('ts_manage_keys','Manage keys') + '</button>';
  html += '</div>';
  html += '<div id="ts-key-panel" style="display:none;margin-bottom:16px;"></div>';
  html += '<div id="ts-detail-panel" style="display:none;margin-bottom:16px;"></div>';

  // ── Device cards: strict 3-row grid ──
  html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px;">';

  // Sort: online first, then by name
  devices.sort(function(a,b) {
    if (a.online !== b.online) return a.online ? -1 : 1;
    return (a.given_name || a.hostname || '').localeCompare(b.given_name || b.hostname || '');
  });

  devices.forEach(function(d, idx) {
    var color = d.online ? 'var(--green)' : d.stale_days > 7 ? 'var(--red)' : 'var(--orange)';
    var displayName = d.given_name || d.hostname || d.name || '-';
    var osIcons = {linux:'', windows:'', macOS:'', iOS:'', android:'', freebsd:''};
    var icon = osIcons[d.os] || '';
    var hasRoutes = (d.advertised_routes && d.advertised_routes.length > 0);

    html += '<div class="card card-clickable" style="padding:14px;border-left:3px solid '+color+';display:grid;grid-template-rows:24px 20px 1fr;height:100%;cursor:pointer;" onclick="tsShowDetail('+idx+')">';

    // ROW 1 — Header (24px): name + badges + status dot
    html += '<div style="display:flex;align-items:center;height:24px;overflow:hidden;">';
    html += '<strong style="font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0;">'+icon+' '+esc(displayName)+'</strong>';
    if (d.update_available) html += '<span style="font-size:10px;color:var(--orange);flex-shrink:0;margin-left:6px;" title="Update available">⬆</span>';
    if (hasRoutes) html += '<span style="font-size:10px;color:var(--blue);flex-shrink:0;margin-left:4px;" title="Subnet router"></span>';
    if (d.is_exit_node) html += '<span style="font-size:10px;color:var(--purple);flex-shrink:0;margin-left:4px;" title="Exit node"></span>';
    if (!d.authorized) html += '<span style="font-size:10px;color:var(--orange);flex-shrink:0;margin-left:4px;" title="Not authorized"></span>';
    html += '<span style="width:8px;height:8px;border-radius:50%;background:'+color+';flex-shrink:0;margin-left:8px;"></span>';
    html += '</div>';

    // ROW 2 — Subtitle (20px): Tailscale IP + user
    html += '<div style="font-size:12px;color:var(--text-muted);line-height:20px;height:20px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">';
    html += '<span style="font-family:var(--mono);">'+(d.tailscale_ip||'-')+'</span>';
    if (d.user) html += ' — '+esc(d.user);
    html += '</div>';

    // ROW 3 — Data (1fr): 2-col stats grid, ALWAYS 8 fields
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:3px;font-size:12px;color:var(--text-muted);align-content:start;padding-top:6px;">';
    html += '<span>' + t('ts_lbl_os','OS') + ': <strong style="color:var(--text);">'+(d.os||'-')+'</strong></span>';
    html += '<span>' + t('ts_lbl_version','Versjon') + ': '+(d.client_version ? d.client_version.split('-')[0] : '-')+'</span>';
    html += '<span>' + t('ts_lbl_hostname','Vertsnavn') + ': <span style="font-family:var(--mono);font-size:11px;">'+esc(d.hostname||'-')+'</span></span>';
    html += '<span>' + t('ts_lbl_status','Status') + ': <span style="color:'+color+';font-weight:600;">'+(d.online ? t('ts_online','Online') : t('ts_offline','Offline'))+'</span></span>';
    var lastSeenHtml = d.online ? t('ts_now','now') : (d.last_seen_ago || '-');
    html += '<span>' + t('ts_last_seen','Last seen') + ': '+lastSeenHtml+'</span>';
    var keyHtml = '-';
    if (d.key_expiry_disabled) { keyHtml = '<span style="color:var(--text-dim);">' + t('ts_key_expiry_off','deaktivert') + '</span>'; }
    else if (d.key_days_left != null) { var keyColor = d.key_days_left < 7 ? 'var(--red)' : d.key_days_left < 30 ? 'var(--orange)' : 'var(--green)'; keyHtml = '<span style="color:'+keyColor+';font-weight:600;">'+d.key_days_left+'d</span>'; }
    html += '<span>' + t('ts_lbl_key','Nøkkel') + ': '+keyHtml+'</span>';
    var tagHtml = '-';
    if (d.tags && d.tags.length) { tagHtml = d.tags.map(function(tg){return '<span style="font-size:10px;padding:1px 5px;background:var(--bg);border-radius:3px;">'+esc(tg.replace('tag:',''))+'</span>';}).join(' '); }
    html += '<span style="grid-column:span 2;">' + t('ts_lbl_tags','Tagger') + ': '+tagHtml+'</span>';
    html += '</div>';

    html += '</div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

// ── Device Detail Panel ─────────────────────────────────────────────────────

async function tsShowDetail(idx) {
  var d = _tsDevices[idx];
  if (!d) return;
  var panel = document.getElementById('ts-detail-panel');
  panel.style.display = 'block';
  panel.scrollIntoView({behavior:'smooth', block:'start'});

  var color = d.online ? 'var(--green)' : 'var(--orange)';
  var displayName = d.given_name || d.hostname || d.name || '-';
  var osIcons = {linux:'', windows:'', macOS:'', iOS:'', android:'', freebsd:''};
  var icon = osIcons[d.os] || '';

  var html = '<div class="card" style="padding:20px;border-left:4px solid '+color+';">';

  // Header
  html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">';
  html += '<div style="display:flex;align-items:center;gap:10px;">';
  html += '<span style="font-size:24px;">'+icon+'</span>';
  html += '<div><div style="font-size:16px;font-weight:700;">'+esc(displayName)+'</div>';
  html += '<div style="font-size:12px;color:var(--text-muted);font-family:var(--mono);">'+(d.tailscale_ip||'-')+' — '+esc(d.user||'-')+'</div></div>';
  html += '</div>';
  html += '<button class="btn btn-ghost" onclick="document.getElementById(\'ts-detail-panel\').style.display=\'none\'" style="padding:4px 10px;font-size:12px;">✕ ' + t('ts_close','Lukk') + '</button>';
  html += '</div>';

  // ── Info grid ──
  html += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:12px;color:var(--text-muted);margin-bottom:16px;">';
  html += '<span>' + t('ts_lbl_status','Status') + ': <strong style="color:'+color+';">'+(d.online?t('ts_online','Online'):t('ts_offline','Offline'))+'</strong></span>';
  html += '<span>' + t('ts_lbl_os','OS') + ': <strong style="color:var(--text);">'+esc(d.os||'-')+'</strong></span>';
  html += '<span>Version: '+esc(d.client_version||'-')+'</span>';
  html += '<span>' + t('ts_lbl_hostname','Vertsnavn') + ': <span style="font-family:var(--mono);">'+esc(d.hostname||'-')+'</span></span>';
  html += '<span>' + t('ts_lbl_name','Navn') + ': <span style="font-family:var(--mono);">'+esc(d.name||'-')+'</span></span>';
  html += '<span>' + t('ts_lbl_node_id','Node-ID') + ': <span style="font-family:var(--mono);font-size:11px;">'+esc(d.node_id||d.id||'-')+'</span></span>';
  html += '<span>' + t('ts_last_seen','Last seen') + ': '+(d.online ? t('ts_now','now') : (d.last_seen_ago||'-'))+'</span>';
  html += '<span>' + t('ts_lbl_created','Opprettet') + ': '+(d.created ? d.created.slice(0,10) : '-')+'</span>';
  html += '<span>' + t('ts_lbl_authorized','Autorisert') + ': '+(d.authorized ? '<span style="color:var(--green);">' + t('ts_yes','Ja') + '</span>' : '<span style="color:var(--orange);">' + t('ts_no','Nei') + '</span>')+'</span>';
  html += '<span>' + t('ts_lbl_key_expiry','Nøkkelutløp') + ': '+(d.key_expiry_disabled ? t('ts_disabled','Deaktivert') : d.key_expiry ? d.key_expiry.slice(0,10)+' ('+d.key_days_left+'d)' : '-')+'</span>';
  html += '<span>' + t('ts_lbl_exit_node','Exit node') + ': '+(d.is_exit_node ? '<span style="color:var(--purple);">' + t('ts_yes','Ja') + '</span>' : t('ts_no','Nei'))+'</span>';
  html += '<span>' + t('ts_lbl_blocks_incoming','Blokkerer innkommende') + ': '+(d.blocks_incoming ? t('ts_yes','Ja') : t('ts_no','Nei'))+'</span>';
  // All IPs
  if (d.addresses && d.addresses.length > 1) {
    html += '<span style="grid-column:span 3;">' + t('ts_lbl_all_ips','Alle IP-er') + ': <span style="font-family:var(--mono);font-size:11px;">'+d.addresses.map(function(a){return esc(a);}).join(', ')+'</span></span>';
  }
  html += '</div>';

  // ── Actions row ──
  html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid var(--border);">';

  // Rename
  html += '<div style="display:flex;align-items:center;gap:4px;">';
  html += '<input id="ts-rename-'+idx+'" type="text" value="'+esc(d.given_name || d.hostname || '')+'" placeholder="' + t('ts_ph_display_name','Visningsnavn') + '" style="width:160px;padding:4px 8px;background:var(--bg-input);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:12px;">';
  html += '<button class="btn btn-primary" onclick="tsRenameDevice(\''+d.id+'\','+idx+')" style="padding:4px 10px;font-size:11px;">' + t('ts_rename','Gi nytt navn') + '</button>';
  html += '</div>';

  // Authorize toggle
  if (!d.authorized) {
    html += '<button class="btn btn-primary" onclick="tsAuthorizeDevice(\''+d.id+'\',true)" style="padding:4px 12px;font-size:11px;color:#fff;background:var(--green);">' + t('ts_authorize','Autoriser') + '</button>';
  } else {
    html += '<button class="btn btn-ghost" onclick="tsAuthorizeDevice(\''+d.id+'\',false)" style="padding:4px 12px;font-size:11px;">' + t('ts_deauthorize','Fjern autorisering') + '</button>';
  }

  // Key expiry toggle
  if (d.key_expiry_disabled) {
    html += '<button class="btn btn-ghost" onclick="tsToggleKeyExpiry(\''+d.id+'\',false)" style="padding:4px 12px;font-size:11px;">' + t('ts_enable_key_expiry','Slå på nøkkelutløp') + '</button>';
  } else {
    html += '<button class="btn btn-ghost" onclick="tsToggleKeyExpiry(\''+d.id+'\',true)" style="padding:4px 12px;font-size:11px;">' + t('ts_disable_key_expiry','Slå av nøkkelutløp') + '</button>';
  }

  // Remove
  html += '<button class="btn btn-ghost" onclick="tsRemoveDevice(\''+d.id+'\')" style="padding:4px 12px;font-size:11px;color:var(--red);margin-left:auto;">' + t('ts_remove_device','Fjern enhet') + '</button>';
  html += '</div>';

  // ── Subnet Routes ──
  html += '<div style="margin-bottom:16px;">';
  html += '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">' + t('ts_subnet_routes','Subnett-ruter') + '</div>';
  html += '<div id="ts-routes-'+idx+'"><div class="loader" style="width:14px;height:14px;display:inline-block;"></div> ' + t('ts_loading_routes','Laster ruter ...') + '</div>';
  html += '</div>';

  // ── Tags editor ──
  html += '<div>';
  html += '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">' + t('ts_tags_heading','Tagger') + '</div>';
  var currentTags = (d.tags || []).map(function(tg){return tg.replace('tag:','');}).join(', ');
  html += '<div style="display:flex;gap:8px;align-items:center;">';
  html += '<input id="ts-tags-'+idx+'" type="text" value="'+esc(currentTags)+'" placeholder="' + t('ts_ph_tags','tag1, tag2 (uten tag:-prefiks)') + '" style="flex:1;padding:6px 10px;background:var(--bg-input);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:12px;">';
  html += '<button class="btn btn-primary" onclick="tsUpdateTags(\''+d.id+'\','+idx+')" style="padding:4px 12px;font-size:11px;">' + t('ts_save_tags','Lagre tagger') + '</button>';
  html += '</div>';
  html += '<div style="font-size:10px;color:var(--text-dim);margin-top:4px;">' + t('ts_tags_hint','Kommaseparert. tag:-prefikset legges til automatisk.') + '</div>';
  html += '</div>';

  html += '<div id="ts-detail-msg" style="margin-top:10px;font-size:12px;"></div>';
  html += '</div>';
  panel.innerHTML = html;

  // Load routes async
  tsLoadRoutes(d.id, idx);
}

async function tsLoadRoutes(deviceId, idx) {
  var el = document.getElementById('ts-routes-'+idx);
  if (!el) return;
  var data = await apiFetch('/api/tailscale/device/'+deviceId+'/routes');
  if (!data || data.error) {
    el.innerHTML = '<span style="font-size:12px;color:var(--text-dim);">' + t('ts_no_routes','Ingen ruter annonsert') + '</span>';
    return;
  }
  var routes = data.routes || [];
  if (!routes.length) {
    el.innerHTML = '<span style="font-size:12px;color:var(--text-dim);">' + t('ts_no_routes_device','Ingen ruter annonsert av denne enheten') + '</span>';
    return;
  }

  var html = '<div style="display:flex;flex-direction:column;gap:6px;">';
  routes.forEach(function(r) {
    var isExit = r.is_exit_node;
    var label = isExit ? 'Exit node ('+r.route+')' : ''+r.route;
    var statusColor = r.enabled ? 'var(--green)' : 'var(--text-dim)';
    var statusText = r.enabled ? t('ts_route_approved','Godkjent') : t('ts_route_pending','Venter');

    html += '<div style="display:flex;align-items:center;gap:10px;padding:6px 10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;">';
    html += '<span style="font-family:var(--mono);font-size:12px;flex:1;">'+esc(label)+'</span>';
    html += '<span style="font-size:11px;color:'+statusColor+';font-weight:600;">'+statusText+'</span>';

    if (r.enabled) {
      html += '<button class="btn btn-ghost" onclick="tsToggleRoute(\''+deviceId+'\','+idx+',\''+r.route+'\',false)" style="padding:2px 8px;font-size:10px;color:var(--red);">' + t('ts_route_disable','Deaktiver') + '</button>';
    } else {
      html += '<button class="btn btn-primary" onclick="tsToggleRoute(\''+deviceId+'\','+idx+',\''+r.route+'\',true)" style="padding:2px 8px;font-size:10px;">' + t('ts_route_approve','Godkjenn') + '</button>';
    }
    html += '</div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

async function tsToggleRoute(deviceId, idx, route, enable) {
  // Get current routes, toggle the target
  var data = await apiFetch('/api/tailscale/device/'+deviceId+'/routes');
  if (!data) return;
  var enabled = data.enabled || [];
  if (enable && enabled.indexOf(route) === -1) {
    enabled.push(route);
  } else if (!enable) {
    enabled = enabled.filter(function(r){return r !== route;});
  }
  var res = await apiFetch('/api/tailscale/device/'+deviceId+'/routes', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({routes: enabled})
  });
  if (res && res.ok) {
    showToast(enable ? 'Route approved' : 'Route disabled', 'success');
    tsLoadRoutes(deviceId, idx);
  } else {
    showToast(res && res.error || 'Failed', 'error');
  }
}

async function tsRenameDevice(deviceId, idx) {
  var name = document.getElementById('ts-rename-'+idx).value.trim();
  if (!name) return;
  var d = await apiFetch('/api/tailscale/device/'+deviceId+'/name', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:name})
  });
  if (d && d.ok) { showToast(t('ts_device_renamed','Enhet fikk nytt navn'), 'success'); tsLoadDevices(); }
  else { showToast(d && d.error || 'Failed', 'error'); }
}

async function tsAuthorizeDevice(deviceId, authorized) {
  var d = await apiFetch('/api/tailscale/device/'+deviceId+'/authorize', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({authorized:authorized})
  });
  if (d && d.ok) { showToast(authorized ? t('ts_device_authorized','Enhet autorisert') : t('ts_device_deauthorized','Autorisering fjernet'), 'success'); tsLoadDevices(); }
  else { showToast(d && d.error || 'Failed', 'error'); }
}

async function tsToggleKeyExpiry(deviceId, disabled) {
  var d = await apiFetch('/api/tailscale/device/'+deviceId+'/key', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({disabled:disabled})
  });
  if (d && d.ok) { showToast(disabled ? t('ts_key_expiry_disabled','Nøkkelutløp slått av') : t('ts_key_expiry_enabled','Nøkkelutløp slått på'), 'success'); tsLoadDevices(); }
  else { showToast(d && d.error || 'Failed', 'error'); }
}

async function tsRemoveDevice(deviceId) {
  if (!confirm(t('ts_confirm_remove','Fjerne denne enheten fra tailnettet? Dette kan ikke angres.'))) return;
  var d = await apiFetch('/api/tailscale/device/'+deviceId, {method:'DELETE'});
  if (d && d.ok) { showToast(t('ts_device_removed','Enhet fjernet'), 'success'); document.getElementById('ts-detail-panel').style.display='none'; tsLoadDevices(); }
  else { showToast(d && d.error || 'Failed', 'error'); }
}

async function tsUpdateTags(deviceId, idx) {
  var raw = document.getElementById('ts-tags-'+idx).value.trim();
  var tags = raw ? raw.split(',').map(function(t){t=t.trim(); return t.startsWith('tag:') ? t : 'tag:'+t;}).filter(function(t){return t.length > 4;}) : [];
  var d = await apiFetch('/api/tailscale/device/'+deviceId+'/tags', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tags:tags})
  });
  if (d && d.ok) { showToast(t('ts_tags_updated','Tagger oppdatert'), 'success'); tsLoadDevices(); }
  else { showToast(d && d.error || 'Failed', 'error'); }
}

async function tsShowKeys() {
  var panel = document.getElementById('ts-key-panel');
  if (panel.style.display !== 'none') { panel.style.display = 'none'; return; }
  panel.style.display = 'block';
  panel.innerHTML = '<div class="loader" style="width:16px;height:16px;margin:8px auto;"></div>';

  var data = await apiFetch('/api/tailscale/keys');
  if (!data || data.error) { panel.innerHTML = '<div style="color:var(--red);font-size:12px;">'+esc(data && data.error || 'Error')+'</div>'; return; }

  var keys = data.keys || [];
  if (!keys.length) { panel.innerHTML = '<div class="card" style="padding:16px;font-size:12px;color:var(--text-muted);">' + t('ts_no_auth_keys','Ingen auth-nøkler funnet.') + '</div>'; return; }

  var html = '<div class="card" style="padding:16px;">';
  html += '<div style="font-size:13px;font-weight:600;margin-bottom:10px;">' + t('ts_auth_keys','Auth Keys') + ' ('+keys.length+')</div>';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:6px;">ID</th><th style="text-align:left;padding:6px;">' + t('ts_col_description','Beskrivelse') + '</th><th style="text-align:center;padding:6px;">' + t('ts_col_days_left','Dager igjen') + '</th><th style="text-align:center;padding:6px;">' + t('ts_col_revoked','Tilbakekalt') + '</th><th></th></tr></thead><tbody>';
  keys.forEach(function(k) {
    var daysColor = k.days_left === null ? 'var(--text-dim)' : k.days_left < 7 ? 'var(--red)' : k.days_left < 30 ? 'var(--orange)' : 'var(--green)';
    html += '<tr style="border-bottom:1px solid var(--border);">';
    html += '<td style="padding:6px;font-family:var(--mono);font-size:11px;">'+esc(k.id.slice(0,12))+'...</td>';
    html += '<td style="padding:6px;">'+esc(k.description||'-')+'</td>';
    html += '<td style="padding:6px;text-align:center;"><span style="color:'+daysColor+';font-weight:600;">'+(k.days_left!=null?k.days_left:'-')+'</span></td>';
    html += '<td style="padding:6px;text-align:center;">'+(k.revoked?'<span style="color:var(--red);">' + t('ts_yes','Ja') + '</span>':t('ts_no','Nei'))+'</td>';
    html += '<td style="padding:6px;"><button class="btn btn-ghost" onclick="tsRevokeKey(\''+k.id+'\')" style="padding:2px 8px;font-size:11px;color:var(--red);">' + t('ts_revoke','Tilbakekall') + '</button></td>';
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  panel.innerHTML = html;
}

function tsShowCreateKey() {
  var panel = document.getElementById('ts-key-panel');
  panel.style.display = 'block';
  var html = '<div class="card" style="padding:16px;">';
  html += '<div style="font-size:13px;font-weight:600;margin-bottom:12px;">' + t('ts_create_key','Create auth key') + '</div>';
  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">';
  html += '<div><label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('ts_lbl_key_desc','Beskrivelse') + '</label>';
  html += '<input id="ts-key-desc" type="text" placeholder="' + t('ts_ph_key_desc','f.eks. onboarding-acme') + '" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>';
  html += '<div><label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('ts_lbl_expiry_hours','Utløp (timer)') + '</label>';
  html += '<input id="ts-key-expiry" type="number" value="24" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>';
  html += '</div>';
  html += '<div style="display:flex;gap:12px;margin-top:10px;">';
  html += '<label style="font-size:12px;display:flex;align-items:center;gap:4px;"><input type="checkbox" id="ts-key-reusable"> ' + t('ts_reusable','Gjenbrukbar') + '</label>';
  html += '<label style="font-size:12px;display:flex;align-items:center;gap:4px;"><input type="checkbox" id="ts-key-ephemeral"> ' + t('ts_ephemeral','Kortlevd') + '</label>';
  html += '<label style="font-size:12px;display:flex;align-items:center;gap:4px;"><input type="checkbox" id="ts-key-preauth" checked> ' + t('ts_preauthorized','Forhåndsautorisert') + '</label>';
  html += '</div>';
  html += '<div style="display:flex;gap:8px;margin-top:12px;">';
  html += '<button class="btn btn-primary" onclick="tsDoCreateKey()" style="padding:6px 16px;font-size:12px;">' + t('btn_create','Create') + '</button>';
  html += '<button class="btn btn-ghost" onclick="document.getElementById(\'ts-key-panel\').style.display=\'none\'" style="padding:6px 16px;font-size:12px;">' + t('btn_cancel','Cancel') + '</button>';
  html += '</div>';
  html += '<div id="ts-key-result" style="margin-top:10px;"></div>';
  html += '</div>';
  panel.innerHTML = html;
}

async function tsDoCreateKey() {
  var resultEl = document.getElementById('ts-key-result');
  resultEl.innerHTML = '<span style="color:var(--text-muted);font-size:12px;">' + t('msg_loading','Loading...') + '</span>';
  var expiryHours = parseInt(document.getElementById('ts-key-expiry').value) || 24;
  var d = await apiFetch('/api/tailscale/keys', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      description: document.getElementById('ts-key-desc').value.trim(),
      reusable: document.getElementById('ts-key-reusable').checked,
      ephemeral: document.getElementById('ts-key-ephemeral').checked,
      preauthorized: document.getElementById('ts-key-preauth').checked,
      expiry_seconds: expiryHours * 3600,
    })
  });
  if (d && d.ok && d.key) {
    var keyVal = d.key.key || d.key.id || '(see admin console)';
    resultEl.innerHTML = '<div style="background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:10px;margin-top:8px;">'
      + '<div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">Auth key created — copy it now, it won\'t be shown again:</div>'
      + '<div style="font-family:var(--mono);font-size:12px;word-break:break-all;color:var(--green);user-select:all;">'+esc(keyVal)+'</div>'
      + '</div>';
    showToast(t('ts_key_created','Auth key created'), 'success');
  } else {
    resultEl.innerHTML = '<span style="color:var(--red);font-size:12px;">' + esc(d && d.error || 'Failed') + '</span>';
  }
}

async function tsRevokeKey(keyId) {
  if (!confirm(t('ts_confirm_revoke','Revoke this auth key?'))) return;
  var d = await apiFetch('/api/tailscale/keys/' + keyId, {method:'DELETE'});
  if (d && d.ok) {
    showToast(t('ts_key_revoked','Key revoked'), 'success');
    tsShowKeys();
  } else {
    showToast(esc(d && d.error || 'Failed'), 'error');
  }
}

