// ═══════════════════════════════════════════════════════════════════
// TAILSCALE INTEGRATION
// ═══════════════════════════════════════════════════════════════════

import {esc} from './app-esc.js';
import {t} from './app-i18n.js';
import {registerUiHandlers} from './app-handlers.js';
import {toneClass, toneVar} from './app-format.js';
import {adminSignpostButton, showConfirm, showToast} from './app-ui.js';
import {apiFetch} from './app-api.js';

// Handlers for the markup this file builds: the device cards and detail panel,
// subnet routes and auth keys.
registerUiHandlers({
  tsLoadDevices: function() { tsLoadDevices(); },
  tsShowCreateKey: function() { tsShowCreateKey(); },
  tsShowKeys: function() { tsShowKeys(); },
  tsShowDetail: function(el) { tsShowDetail(Number(el.dataset.index)); },
  tsRenameDevice: function(el) { tsRenameDevice(el.dataset.id, Number(el.dataset.index)); },
  tsAuthorizeDevice: function(el) { tsAuthorizeDevice(el.dataset.id, el.dataset.authorized === '1'); },
  tsToggleKeyExpiry: function(el) { tsToggleKeyExpiry(el.dataset.id, el.dataset.expiryDisabled === '1'); },
  tsRemoveDevice: function(el) { tsRemoveDevice(el.dataset.id); },
  tsUpdateTags: function(el) { tsUpdateTags(el.dataset.id, Number(el.dataset.index)); },
  tsToggleRoute: function(el) {
    tsToggleRoute(el.dataset.id, Number(el.dataset.index), el.dataset.route, el.dataset.enable === '1');
  },
  tsRevokeKey: function(el) { tsRevokeKey(el.dataset.id); },
  tsDoCreateKey: function() { tsDoCreateKey(); },
});

export async function tsTestConnection() {
  var msg = document.getElementById('ts-config-msg');
  msg.innerHTML = '<span class="text-muted">' + t('msg_testing','Testing...') + '</span>';
  try {
    var d = await apiFetch('/api/tailscale/test', {
      onError: function(message) { msg.textContent = message; msg.style.color = 'var(--red)'; },
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        api_key: document.getElementById('input-ts-api-key').value.trim(),
        tailnet: document.getElementById('input-ts-tailnet').value.trim() || '-',
      })
    });
    if (!d) return;
    if (d.ok) {
      msg.innerHTML = '<span class="text-success">&#10003; ' + t('msg_connection_verified','Connection verified') + ' · ' + Number(d.device_count) + ' ' + t('ts_devices_suffix','enheter') + '</span>';
      document.getElementById('ts-integ-dot').style.background = 'var(--green)';
      document.getElementById('ts-integ-label').textContent = d.device_count + ' ' + t('ts_devices_suffix');
      document.getElementById('ts-integ-label').style.color = 'var(--green)';
    } else {
      msg.innerHTML = '<span class="text-danger">&#10007; ' + esc(d && d.error ? d.error : t('status_error')) + '</span>';
    }
  } catch(e) {
    msg.innerHTML = '<span class="text-danger">' + esc(e.message) + '</span>';
  }
}

export async function tsSaveConfig() {
  var msg = document.getElementById('ts-config-msg');
  var body = {
    tailscale_api_key: document.getElementById('input-ts-api-key').value.trim(),
    tailscale_tailnet: document.getElementById('input-ts-tailnet').value.trim() || '-',
  };
  var d = await apiFetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  if (d && !d.error) {
    msg.innerHTML = '<span class="text-success">&#10003; ' + t('msg_saved','Saved') + '</span>';
  } else {
    msg.innerHTML = '<span class="text-danger">' + esc(d && d.error ? d.error : t('status_error')) + '</span>';
  }
}

// ── Tailscale Dashboard View ────────────────────────────────────────────────

var _tsDevices = [];

export function tsLoadView() {
  var el = document.getElementById('ts-content');
  el.innerHTML = '<div class="loader loader-md"></div><div class="text-center text-muted text-sm">' + t('msg_loading','Loading...') + '</div>';
  tsLoadDevices();
}

async function tsLoadDevices() {
  var el = document.getElementById('ts-content');
  var data = await apiFetch('/api/tailscale/devices');
  if (!data) {
    // apiFetch has said what went wrong; leave the page calm, not blank.
    el.innerHTML = '<div class="empty-state"><div class="empty-desc">' + esc(t('status_error', 'Feil')) + '</div></div>';
    return;
  }
  if (data.configured === false) {
    // The key is set on the Tailscale card under Administrasjon › Integrasjoner.
    el.innerHTML = '<div class="empty-state" id="ts-not-configured">'
      + '<div class="empty-title">' + esc(t('ts_not_configured_title', 'Tailscale er ikke satt opp')) + '</div>'
      + '<div class="empty-desc">' + esc(t('ts_not_configured', 'Legg inn en API-nøkkel på Tailscale-kortet under Administrasjon › Integrasjoner.')) + '</div>'
      + adminSignpostButton('integrations', 'btn_open_integrations', 'btn-primary')
      + '</div>';
    return;
  }

  var devices = data.devices || [];
  _tsDevices = devices;
  if (!devices.length) {
    el.innerHTML = '<div class="empty-note">' + t('ts_no_devices','No devices found in your tailnet.') + '</div>';
    return;
  }

  // ── KPI summary row ──
  var html = '<div class="grid grid-cols-5 gap-3 mb-4">';
  var kpis = [
    {label:t('ts_total','Total'), value:Number(data.total), color:'var(--blue)'},
    {label:t('ts_online','Online'), value:Number(data.online), color:'var(--green)'},
    {label:t('ts_offline','Offline'), value:Number(data.offline), color:data.offline>0?'var(--orange)':'var(--text-dim)'},
    {label:t('ts_stale','Stale (>7d)'), value:Number(data.stale), color:data.stale>0?'var(--red)':'var(--text-dim)'},
    {label:t('ts_key_expiring','Key expiring'), value:Number(data.expiring_keys), color:data.expiring_keys>0?'var(--orange)':'var(--text-dim)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card kpi-card ' + toneVar(k.color) + '">';
    html += '<div class="kpi-value ' + toneClass(k.color) + '">'+k.value+'</div>';
    html += '<div class="kpi-label">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // ── Action bar ──
  html += '<div class="flex items-center gap-3 mb-3">';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="tsLoadDevices">' + t('btn_refresh','Refresh') + '</button>';
  html += '<button class="btn btn-primary btn-sm" data-write data-click-handler="tsShowCreateKey">' + t('ts_create_key','Create auth key') + '</button>';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="tsShowKeys">' + t('ts_manage_keys','Manage keys') + '</button>';
  html += '</div>';
  html += '<div id="ts-key-panel" class="mb-4" style="display:none;"></div>';
  html += '<div id="ts-detail-panel" class="mb-4" style="display:none;"></div>';

  // ── Device cards: strict 3-row grid ──
  html += '<div class="grid grid-auto-lg gap-3">';

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

    html += '<div class="card card-clickable device-card cursor-pointer edge-tone ' + toneVar(color) + '" data-click-handler="tsShowDetail" data-index="'+Number(idx)+'">';

    // ROW 1 — Header (24px): name + badges + status dot
    html += '<div class="device-card-head">';
    html += '<strong class="text-base nowrap overflow-hidden ellipsis flex-1 min-w-0">'+icon+' '+esc(displayName)+'</strong>';
    if (d.update_available) html += '<span class="text-2xs text-warning shrink-0 ml-2" title="Update available">⬆</span>';
    if (hasRoutes) html += '<span class="text-2xs text-accent shrink-0 ml-1" title="Subnet router"></span>';
    if (d.is_exit_node) html += '<span class="text-2xs text-purple shrink-0 ml-1" title="Exit node"></span>';
    if (!d.authorized) html += '<span class="text-2xs text-warning shrink-0 ml-1" title="Not authorized"></span>';
    html += '<span class="dot ' + toneClass(color) + ' ml-2"></span>';
    html += '</div>';

    // ROW 2 — Subtitle (20px): Tailscale IP + user
    html += '<div class="device-card-sub">';
    html += '<span class="font-mono">'+esc(d.tailscale_ip||'-')+'</span>';
    if (d.user) html += ' · '+esc(d.user);
    html += '</div>';

    // ROW 3 — Data (1fr): 2-col stats grid, ALWAYS 8 fields
    html += '<div class="grid grid-cols-2 gap-1 text-sm text-muted content-start pt-2">';
    html += '<span>' + t('ts_lbl_os','OS') + ': <strong class="text-default">'+esc(d.os||'-')+'</strong></span>';
    html += '<span>' + t('ts_lbl_version','Versjon') + ': '+esc(d.client_version ? d.client_version.split('-')[0] : '-')+'</span>';
    html += '<span>' + t('ts_lbl_hostname','Vertsnavn') + ': <span class="font-mono text-xs">'+esc(d.hostname||'-')+'</span></span>';
    html += '<span>' + t('ts_lbl_status','Status') + ': <span class="' + toneClass(color) + ' fw-semibold">'+(d.online ? t('ts_online','Online') : t('ts_offline','Offline'))+'</span></span>';
    var lastSeenHtml = d.online ? t('ts_now','now') : esc(d.last_seen_ago || '-');
    html += '<span>' + t('ts_last_seen','Last seen') + ': '+lastSeenHtml+'</span>';
    var keyHtml = '-';
    if (d.key_expiry_disabled) { keyHtml = '<span class="text-dim">' + t('ts_key_expiry_off','deaktivert') + '</span>'; }
    else if (d.key_days_left != null) { var keyColor = d.key_days_left < 7 ? 'var(--red)' : d.key_days_left < 30 ? 'var(--orange)' : 'var(--green)'; keyHtml = '<span class="' + toneClass(keyColor) + ' fw-semibold">'+Number(d.key_days_left)+'d</span>'; }
    html += '<span>' + t('ts_lbl_key','Nøkkel') + ': '+keyHtml+'</span>';
    var tagHtml = '-';
    if (d.tags && d.tags.length) { tagHtml = d.tags.map(function(tg){return '<span class="text-2xs py-0-5 px-1 bg-base rounded-sm">'+esc(tg.replace('tag:',''))+'</span>';}).join(' '); }
    html += '<span class="col-span-2">' + t('ts_lbl_tags','Tagger') + ': '+tagHtml+'</span>';
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

  var html = '<div class="card p-5 edge-tone ' + toneVar(color) + '">';

  // Header
  html += '<div class="flex items-center justify-between mb-4">';
  html += '<div class="flex items-center gap-3">';
  html += '<span class="text-xl">'+icon+'</span>';
  html += '<div><div class="text-md fw-bold">'+esc(displayName)+'</div>';
  html += '<div class="text-sm text-muted font-mono">'+esc(d.tailscale_ip||'-')+' · '+esc(d.user||'-')+'</div></div>';
  html += '</div>';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="hideElement" data-target="ts-detail-panel">✕ ' + t('ts_close','Lukk') + '</button>';
  html += '</div>';

  // ── Info grid ──
  html += '<div class="grid grid-cols-3 gap-2 text-sm text-muted mb-4">';
  html += '<span>' + t('ts_lbl_status','Status') + ': <strong class="' + toneClass(color) + '">'+(d.online?t('ts_online','Online'):t('ts_offline','Offline'))+'</strong></span>';
  html += '<span>' + t('ts_lbl_os','OS') + ': <strong class="text-default">'+esc(d.os||'-')+'</strong></span>';
  html += '<span>Version: '+esc(d.client_version||'-')+'</span>';
  html += '<span>' + t('ts_lbl_hostname','Vertsnavn') + ': <span class="font-mono">'+esc(d.hostname||'-')+'</span></span>';
  html += '<span>' + t('ts_lbl_name','Navn') + ': <span class="font-mono">'+esc(d.name||'-')+'</span></span>';
  html += '<span>' + t('ts_lbl_node_id','Node-ID') + ': <span class="font-mono text-xs">'+esc(d.node_id||d.id||'-')+'</span></span>';
  html += '<span>' + t('ts_last_seen','Last seen') + ': '+(d.online ? t('ts_now','now') : esc(d.last_seen_ago||'-'))+'</span>';
  html += '<span>' + t('ts_lbl_created','Opprettet') + ': '+esc(d.created ? d.created.slice(0,10) : '-')+'</span>';
  html += '<span>' + t('ts_lbl_authorized','Autorisert') + ': '+(d.authorized ? '<span class="text-success">' + t('ts_yes','Ja') + '</span>' : '<span class="text-warning">' + t('ts_no','Nei') + '</span>')+'</span>';
  html += '<span>' + t('ts_lbl_key_expiry','Nøkkelutløp') + ': '+(d.key_expiry_disabled ? t('ts_disabled','Deaktivert') : d.key_expiry ? esc(d.key_expiry.slice(0,10))+' ('+Number(d.key_days_left)+'d)' : '-')+'</span>';
  html += '<span>' + t('ts_lbl_exit_node','Exit node') + ': '+(d.is_exit_node ? '<span class="text-purple">' + t('ts_yes','Ja') + '</span>' : t('ts_no','Nei'))+'</span>';
  html += '<span>' + t('ts_lbl_blocks_incoming','Blokkerer innkommende') + ': '+(d.blocks_incoming ? t('ts_yes','Ja') : t('ts_no','Nei'))+'</span>';
  // All IPs
  if (d.addresses && d.addresses.length > 1) {
    html += '<span class="col-span-3">' + t('ts_lbl_all_ips','Alle IP-er') + ': <span class="font-mono text-xs">'+d.addresses.map(function(a){return esc(a);}).join(', ')+'</span></span>';
  }
  html += '</div>';

  // ── Actions row ──
  html += '<div class="flex gap-2 flex-wrap mb-4 pb-4 border-b">';

  // Rename
  html += '<div class="flex items-center gap-1">';
  html += '<input id="ts-rename-'+Number(idx)+'" type="text" value="'+esc(d.given_name || d.hostname || '')+'" placeholder="' + t('ts_ph_display_name','Visningsnavn') + '" class="field-input input-short field-input-sm">';
  html += '<button class="btn btn-primary btn-sm" data-write data-click-handler="tsRenameDevice" data-id="'+esc(d.id)+'" data-index="'+Number(idx)+'">' + t('ts_rename','Gi nytt navn') + '</button>';
  html += '</div>';

  // Authorize toggle
  if (!d.authorized) {
    html += '<button class="btn btn-primary badge badge-success" data-write data-click-handler="tsAuthorizeDevice" data-id="'+esc(d.id)+'" data-authorized="1">' + t('ts_authorize','Autoriser') + '</button>';
  } else {
    html += '<button class="btn btn-ghost btn-sm" data-write data-click-handler="tsAuthorizeDevice" data-id="'+esc(d.id)+'" data-authorized="0">' + t('ts_deauthorize','Fjern autorisering') + '</button>';
  }

  // Key expiry toggle
  if (d.key_expiry_disabled) {
    html += '<button class="btn btn-ghost btn-sm" data-write data-click-handler="tsToggleKeyExpiry" data-id="'+esc(d.id)+'" data-expiry-disabled="0">' + t('ts_enable_key_expiry','Slå på nøkkelutløp') + '</button>';
  } else {
    html += '<button class="btn btn-ghost btn-sm" data-write data-click-handler="tsToggleKeyExpiry" data-id="'+esc(d.id)+'" data-expiry-disabled="1">' + t('ts_disable_key_expiry','Slå av nøkkelutløp') + '</button>';
  }

  // Remove
  html += '<button class="btn btn-ghost btn-sm text-danger ml-auto" data-write data-click-handler="tsRemoveDevice" data-id="'+esc(d.id)+'">' + t('ts_remove_device','Fjern enhet') + '</button>';
  html += '</div>';

  // ── Subnet Routes ──
  html += '<div class="mb-4">';
  html += '<div class="subhead">' + t('ts_subnet_routes','Subnett-ruter') + '</div>';
  html += '<div id="ts-routes-'+Number(idx)+'"><div class="loader"></div> ' + t('ts_loading_routes','Laster ruter ...') + '</div>';
  html += '</div>';

  // ── Tags editor ──
  html += '<div>';
  html += '<div class="subhead">' + t('ts_tags_heading','Tagger') + '</div>';
  var currentTags = (d.tags || []).map(function(tg){return tg.replace('tag:','');}).join(', ');
  html += '<div class="flex gap-2 items-center">';
  html += '<input id="ts-tags-'+Number(idx)+'" type="text" value="'+esc(currentTags)+'" placeholder="' + t('ts_ph_tags','tag1, tag2 (uten tag:-prefiks)') + '" class="field-input flex-1 w-auto">';
  html += '<button class="btn btn-primary btn-sm" data-write data-click-handler="tsUpdateTags" data-id="'+esc(d.id)+'" data-index="'+Number(idx)+'">' + t('ts_save_tags','Lagre tagger') + '</button>';
  html += '</div>';
  html += '<div class="text-2xs text-dim mt-1">' + t('ts_tags_hint','Kommaseparert. tag:-prefikset legges til automatisk.') + '</div>';
  html += '</div>';

  html += '<div id="ts-detail-msg" class="mt-3 text-sm"></div>';
  html += '</div>';
  panel.innerHTML = html;

  // Load routes async
  tsLoadRoutes(d.id, idx);
}

async function tsLoadRoutes(deviceId, idx) {
  var el = document.getElementById('ts-routes-'+idx);
  if (!el) return;
  var data = await apiFetch('/api/tailscale/device/'+encodeURIComponent(deviceId)+'/routes');
  if (!data || data.error) {
    el.innerHTML = '<span class="text-sm text-dim">' + t('ts_no_routes','Ingen ruter annonsert') + '</span>';
    return;
  }
  var routes = data.routes || [];
  if (!routes.length) {
    el.innerHTML = '<span class="text-sm text-dim">' + t('ts_no_routes_device','Ingen ruter annonsert av denne enheten') + '</span>';
    return;
  }

  var html = '<div class="flex flex-col gap-2">';
  routes.forEach(function(r) {
    var isExit = r.is_exit_node;
    var label = isExit ? t('ts_lbl_exit_node','Exit node') + ' ('+r.route+')' : ''+r.route;
    var statusColor = r.enabled ? 'var(--green)' : 'var(--text-dim)';
    var statusText = r.enabled ? t('ts_route_approved','Godkjent') : t('ts_route_pending','Venter');

    html += '<div class="inset flex items-center gap-3">';
    html += '<span class="font-mono text-sm flex-1">'+esc(label)+'</span>';
    html += '<span class="text-xs ' + toneClass(statusColor) + ' fw-semibold">'+statusText+'</span>';

    if (r.enabled) {
      html += '<button class="btn btn-ghost btn-sm text-danger" data-write data-click-handler="tsToggleRoute" data-id="'+esc(deviceId)+'" data-index="'+Number(idx)+'" data-route="'+esc(r.route)+'" data-enable="0">' + t('ts_route_disable','Deaktiver') + '</button>';
    } else {
      html += '<button class="btn btn-primary btn-sm" data-write data-click-handler="tsToggleRoute" data-id="'+esc(deviceId)+'" data-index="'+Number(idx)+'" data-route="'+esc(r.route)+'" data-enable="1">' + t('ts_route_approve','Godkjenn') + '</button>';
    }
    html += '</div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

async function tsToggleRoute(deviceId, idx, route, enable) {
  // Get current routes, toggle the target
  var data = await apiFetch('/api/tailscale/device/'+encodeURIComponent(deviceId)+'/routes');
  if (!data) return;
  var enabled = data.enabled || [];
  if (enable && enabled.indexOf(route) === -1) {
    enabled.push(route);
  } else if (!enable) {
    enabled = enabled.filter(function(r){return r !== route;});
  }
  var res = await apiFetch('/api/tailscale/device/'+encodeURIComponent(deviceId)+'/routes', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({routes: enabled})
  });
  if (res && res.ok) {
    showToast(enable ? t('ts_toast_route_approved','Rute godkjent') : t('ts_toast_route_disabled','Rute deaktivert'), 'success');
    tsLoadRoutes(deviceId, idx);
  } else {
    showToast(res && res.error || t('msg_failed','Feilet'), 'error');
  }
}

async function tsRenameDevice(deviceId, idx) {
  var name = document.getElementById('ts-rename-'+idx).value.trim();
  if (!name) return;
  var d = await apiFetch('/api/tailscale/device/'+encodeURIComponent(deviceId)+'/name', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:name})
  });
  if (d && d.ok) { showToast(t('ts_device_renamed','Enhet fikk nytt navn'), 'success'); tsLoadDevices(); }
  else { showToast(d && d.error || t('msg_failed','Feilet'), 'error'); }
}

async function tsAuthorizeDevice(deviceId, authorized) {
  var d = await apiFetch('/api/tailscale/device/'+encodeURIComponent(deviceId)+'/authorize', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({authorized:authorized})
  });
  if (d && d.ok) { showToast(authorized ? t('ts_device_authorized','Enhet autorisert') : t('ts_device_deauthorized','Autorisering fjernet'), 'success'); tsLoadDevices(); }
  else { showToast(d && d.error || t('msg_failed','Feilet'), 'error'); }
}

async function tsToggleKeyExpiry(deviceId, disabled) {
  var d = await apiFetch('/api/tailscale/device/'+encodeURIComponent(deviceId)+'/key', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({disabled:disabled})
  });
  if (d && d.ok) { showToast(disabled ? t('ts_key_expiry_disabled','Nøkkelutløp slått av') : t('ts_key_expiry_enabled','Nøkkelutløp slått på'), 'success'); tsLoadDevices(); }
  else { showToast(d && d.error || t('msg_failed','Feilet'), 'error'); }
}

async function tsRemoveDevice(deviceId) {
  if (!await showConfirm(t('ts_confirm_remove','Fjerne denne enheten fra tailnettet? Dette kan ikke angres.'))) return;
  var d = await apiFetch('/api/tailscale/device/'+encodeURIComponent(deviceId), {method:'DELETE'});
  if (d && d.ok) { showToast(t('ts_device_removed','Enhet fjernet'), 'success'); document.getElementById('ts-detail-panel').style.display='none'; tsLoadDevices(); }
  else { showToast(d && d.error || t('msg_failed','Feilet'), 'error'); }
}

async function tsUpdateTags(deviceId, idx) {
  var raw = document.getElementById('ts-tags-'+idx).value.trim();
  var tags = raw ? raw.split(',').map(function(t){t=t.trim(); return t.startsWith('tag:') ? t : 'tag:'+t;}).filter(function(t){return t.length > 4;}) : [];
  var d = await apiFetch('/api/tailscale/device/'+encodeURIComponent(deviceId)+'/tags', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tags:tags})
  });
  if (d && d.ok) { showToast(t('ts_tags_updated','Tagger oppdatert'), 'success'); tsLoadDevices(); }
  else { showToast(d && d.error || t('msg_failed','Feilet'), 'error'); }
}

async function tsShowKeys() {
  var panel = document.getElementById('ts-key-panel');
  if (panel.style.display !== 'none') { panel.style.display = 'none'; return; }
  panel.style.display = 'block';
  panel.innerHTML = '<div class="loader mx-auto my-2"></div>';

  var data = await apiFetch('/api/tailscale/keys');
  if (!data || data.error) { panel.innerHTML = '<div class="text-danger text-sm">'+esc(data && data.error || 'Error')+'</div>'; return; }

  var keys = data.keys || [];
  if (!keys.length) { panel.innerHTML = '<div class="card p-4 text-sm text-muted">' + t('ts_no_auth_keys','Ingen auth-nøkler funnet.') + '</div>'; return; }

  var html = '<div class="card p-4">';
  html += '<div class="subhead mb-3">' + t('ts_auth_keys','Auth Keys') + ' ('+keys.length+')</div>';
  html += '<table class="data-table">';
  html += '<thead><tr><th>ID</th><th>' + t('ts_col_description','Beskrivelse') + '</th><th class="text-center">' + t('ts_col_days_left','Dager igjen') + '</th><th class="text-center">' + t('ts_col_revoked','Tilbakekalt') + '</th><th></th></tr></thead><tbody>';
  keys.forEach(function(k) {
    var daysColor = k.days_left === null ? 'var(--text-dim)' : k.days_left < 7 ? 'var(--red)' : k.days_left < 30 ? 'var(--orange)' : 'var(--green)';
    html += '<tr>';
    html += '<td class="font-mono text-xs">'+esc(k.id.slice(0,12))+'...</td>';
    html += '<td>'+esc(k.description||'-')+'</td>';
    html += '<td class="text-center"><span class="' + toneClass(daysColor) + ' fw-semibold">'+(k.days_left!=null?Number(k.days_left):'-')+'</span></td>';
    html += '<td class="text-center">'+(k.revoked?'<span class="text-danger">' + t('ts_yes','Ja') + '</span>':t('ts_no','Nei'))+'</td>';
    html += '<td><button class="btn btn-ghost btn-sm text-danger" data-write data-click-handler="tsRevokeKey" data-id="'+esc(k.id)+'">' + t('ts_revoke','Tilbakekall') + '</button></td>';
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  panel.innerHTML = html;
}

function tsShowCreateKey() {
  var panel = document.getElementById('ts-key-panel');
  panel.style.display = 'block';
  var html = '<div class="card p-4">';
  html += '<div class="subhead mb-3">' + t('ts_create_key','Create auth key') + '</div>';
  html += '<div class="grid grid-cols-2 gap-3">';
  html += '<div><label class="field-label">' + t('ts_lbl_key_desc','Beskrivelse') + '</label>';
  html += '<input id="ts-key-desc" type="text" placeholder="' + t('ts_ph_key_desc','f.eks. onboarding-acme') + '" class="field-input"></div>';
  html += '<div><label class="field-label">' + t('ts_lbl_expiry_hours','Utløp (timer)') + '</label>';
  html += '<input id="ts-key-expiry" type="number" value="24" class="field-input"></div>';
  html += '</div>';
  html += '<div class="flex gap-3 mt-3">';
  html += '<label class="text-sm flex items-center gap-1"><input type="checkbox" id="ts-key-reusable"> ' + t('ts_reusable','Gjenbrukbar') + '</label>';
  html += '<label class="text-sm flex items-center gap-1"><input type="checkbox" id="ts-key-ephemeral"> ' + t('ts_ephemeral','Kortlevd') + '</label>';
  html += '<label class="text-sm flex items-center gap-1"><input type="checkbox" id="ts-key-preauth" checked> ' + t('ts_preauthorized','Forhåndsautorisert') + '</label>';
  html += '</div>';
  html += '<div class="flex gap-2 mt-3">';
  html += '<button class="btn btn-primary btn-sm" data-write data-click-handler="tsDoCreateKey">' + t('btn_create','Create') + '</button>';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="hideElement" data-target="ts-key-panel">' + t('btn_cancel','Cancel') + '</button>';
  html += '</div>';
  html += '<div id="ts-key-result" class="mt-3"></div>';
  html += '</div>';
  panel.innerHTML = html;
}

async function tsDoCreateKey() {
  var resultEl = document.getElementById('ts-key-result');
  resultEl.innerHTML = '<span class="text-muted text-sm">' + t('msg_loading','Loading...') + '</span>';
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
    resultEl.innerHTML = '<div class="inset mt-2">'
      + '<div class="text-xs text-muted mb-1">Auth key created · copy it now, it won\'t be shown again:</div>'
      + '<div class="font-mono text-sm break-all text-success select-all">'+esc(keyVal)+'</div>'
      + '</div>';
    showToast(t('ts_key_created','Auth key created'), 'success');
  } else {
    resultEl.innerHTML = '<span class="text-danger text-sm">' + esc(d && d.error || 'Failed') + '</span>';
  }
}

async function tsRevokeKey(keyId) {
  if (!await showConfirm(t('ts_confirm_revoke','Revoke this auth key?'))) return;
  var d = await apiFetch('/api/tailscale/keys/' + encodeURIComponent(keyId), {method:'DELETE'});
  if (d && d.ok) {
    showToast(t('ts_key_revoked','Key revoked'), 'success');
    tsShowKeys();
  } else {
    showToast(esc(d && d.error || t('msg_failed','Feilet')), 'error');
  }
}
