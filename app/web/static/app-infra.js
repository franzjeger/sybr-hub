// ═══════════════════════════════════════════════════════════════════
// SHARED: Customer selector helper
// ═══════════════════════════════════════════════════════════════════

var _infraCustomerCache = null;

async function _populateCustomerSelect(selectId, selectedId) {
  var sel = document.getElementById(selectId);
  if (!sel) return;
  if (!_infraCustomerCache) {
    try {
      var ov = typeof _overviewData !== 'undefined' && _overviewData && _overviewData.customers
        ? _overviewData : await apiFetch('/api/dashboard/overview');
      _infraCustomerCache = (ov && ov.customers) || [];
    } catch(e) { _infraCustomerCache = []; }
  }
  _infraCustomerCache.forEach(function(c) {
    var id = c.customer_id || c._id;
    var opt = document.createElement('option');
    opt.value = id;
    opt.textContent = c.customer_name || id;
    if (selectedId && id === selectedId) opt.selected = true;
    sel.appendChild(opt);
  });
}

function _customerNameById(customerId) {
  if (!customerId) return '';
  if (_infraCustomerCache) {
    var c = _infraCustomerCache.find(function(c){ return (c.customer_id || c._id) === customerId; });
    if (c) return c.customer_name || customerId;
  }
  if (typeof _overviewData !== 'undefined' && _overviewData && _overviewData.customers) {
    var c2 = _overviewData.customers.find(function(c){ return (c.customer_id || c._id) === customerId; });
    if (c2) return c2.customer_name || customerId;
  }
  return customerId;
}

// ═══════════════════════════════════════════════════════════════════
// HOSTS MANAGEMENT
// ═══════════════════════════════════════════════════════════════════

async function hostsLoad() {
  var el = document.getElementById('hosts-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';

  // Pre-load customer cache for name resolution
  if (!_infraCustomerCache) { await _populateCustomerSelect('_dummy_nonexistent_'); }

  var typeFilter = document.getElementById('hosts-filter-type').value;
  var groupFilter = document.getElementById('hosts-filter-group').value;

  var url = '/api/ssh/hosts';
  var params = [];
  if (typeFilter) params.push('device_type=' + typeFilter);
  if (groupFilter) params.push('group=' + encodeURIComponent(groupFilter));
  if (params.length) url += '?' + params.join('&');

  var data = await apiFetch(url);
  if (!data) return;
  var hosts = data.hosts || [];

  // Populate group filter
  var groups = {};
  hosts.forEach(function(h) { if (h.group_name) groups[h.group_name] = true; });
  var grpSel = document.getElementById('hosts-filter-group');
  var curGrp = grpSel.value;
  grpSel.innerHTML = '<option value="">' + t('alle_grupper') + '</option>';
  Object.keys(groups).sort().forEach(function(g) {
    grpSel.innerHTML += '<option value="'+g+'"'+(g===curGrp?' selected':'')+'>'+g+'</option>';
  });

  if (!hosts.length) {
    el.innerHTML = '<div class="empty-state"><div class="empty-icon">&#128421;</div><div class="empty-title">' + t('msg_no_hosts','No hosts registered') + '</div><div class="empty-desc">' + t('msg_add_first_host','Click "Add host" to get started.') + '</div><button class="btn btn-primary" onclick="hostsAdd()">' + t('btn_add_host','Add host') + '</button></div>';
    return;
  }

  // ── Host cards: strict 3-row grid ──
  var html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;">';
  hosts.forEach(function(h) {
    var statusColor = h.is_reachable === true ? 'var(--green)' : h.is_reachable === false ? 'var(--red)' : 'var(--text-dim)';
    var typeIcons = {windows:'🖥️',linux:'🐧',fortigate:'🛡',unifi:'📡',pfsense:'🔒',openwrt:'📶',custom:'⚙️'};
    var icon = typeIcons[h.device_type] || '⚙️';

    html += '<div class="card" style="padding:14px;border-left:3px solid '+statusColor+';display:grid;grid-template-rows:24px 20px 1fr;height:100%;">';

    // ROW 1 — Header (24px): label + group badge + status dot
    html += '<div style="display:flex;align-items:center;height:24px;overflow:hidden;">';
    html += '<strong style="font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0;">'+icon+' '+(h.label||'-')+'</strong>';
    html += '<span style="font-size:10px;color:var(--text-dim);padding:1px 6px;background:var(--bg);border-radius:4px;flex-shrink:0;margin-left:6px;">'+(h.group_name||'-')+'</span>';
    html += '<span style="width:8px;height:8px;border-radius:50%;background:'+statusColor+';flex-shrink:0;margin-left:8px;"></span>';
    html += '</div>';

    // ROW 2 — Subtitle (20px): connection info + customer
    html += '<div style="font-size:12px;color:var(--text-muted);line-height:20px;height:20px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">';
    html += '<span style="font-family:var(--mono);">'+(h.hostname||'-')+':'+(h.port||'-')+'</span>';
    html += ' — '+(h.username||'-')+'@'+(h.device_type||'-');
    if (h.customer_id) {
      var _cn = _customerNameById(h.customer_id);
      html += ' <a href="javascript:void(0)" onclick="overviewSelectCustomer(\'' + h.customer_id + '\')" style="color:var(--blue);text-decoration:none;font-size:11px;margin-left:4px;" title="' + t('lbl_customer','Customer') + '">' + esc(_cn) + '</a>';
    }
    html += '</div>';

    // ROW 3 — Data (1fr): actions — always render all 5 buttons
    var isDesktop = (h.device_type === 'windows' || h.device_type === 'linux');
    var isNetwork = (['fortigate','unifi','pfsense','openwrt'].indexOf(h.device_type) !== -1);
    var webPort = h.port === 22 ? 443 : h.port;

    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;align-content:start;padding-top:8px;">';
    html += '<button class="btn btn-ghost" onclick="sshEditHost(\''+h.id+'\')" style="padding:2px 8px;font-size:11px;">' + t('btn_edit','Edit') + '</button>';
    html += '<button class="btn btn-ghost" onclick="sshTerminal(\''+h.id+'\')" style="padding:2px 8px;font-size:11px;color:var(--blue);">SSH</button>';
    html += '<button class="btn btn-ghost" style="padding:2px 8px;font-size:11px;color:var(--purple);'+(isDesktop?'':'opacity:0.3;pointer-events:none;')+'" onclick="sshRdp(\''+h.hostname+'\',\''+h.username+'\',\''+h.id+'\')">RDP</button>';
    html += '<button class="btn btn-ghost" style="padding:2px 8px;font-size:11px;color:var(--orange);'+(isNetwork?'':'opacity:0.3;pointer-events:none;')+'" onclick="openWebUI(\'https://'+h.hostname+':'+webPort+'\')">' + t('web_ui') + '</button>';
    html += '<button class="btn btn-ghost" onclick="sshDeleteHost(\''+h.id+'\')" style="padding:2px 8px;font-size:11px;color:var(--red);grid-column:span 2;justify-self:start;">' + t('btn_delete','Delete') + '</button>';
    html += '</div>';

    html += '</div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

function hostsAdd() {
  var el = document.getElementById('hosts-content');

  // Load keys for dropdown
  apiFetch('/api/ssh/keys').then(function(keysData) {
    var keys = (keysData && keysData.keys) || [];
    var keyOpts = '<option value="">' + t('ingen_bruk_passord') + '</option>';
    keys.forEach(function(k) { keyOpts += '<option value="'+k.id+'">'+k.name+' ('+k.fingerprint.slice(0,20)+'...)</option>'; });

    el.innerHTML = '<div style="max-width:560px;">'
      + '<h3 style="font-size:15px;font-weight:600;margin-bottom:16px;">' + t('legg_til_vert') + '</h3>'

      // Device type first — determines which fields to show
      + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('enhetstype') + '</label>'
      + '<select id="host-devtype" onchange="hostsTypeChanged()" style="width:100%;padding:8px 12px;margin-bottom:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
      + '<option value="windows">' + t('windows_server') + '</option>'
      + '<option value="linux">' + t('linux') + '</option>'
      + '<option value="fortigate">' + t('fortigate') + '</option>'
      + '<option value="unifi">' + t('unifi') + '</option>'
      + '<option value="pfsense">' + t('pfsense') + '</option>'
      + '<option value="openwrt">' + t('openwrt') + '</option>'
      + '<option value="custom">' + t('annet') + '</option>'
      + '</select>'

      + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">'
      + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('navn_2') + '</label>'
      + '<input id="host-label" type="text" placeholder="f.eks. DC01 eller FW-Autostrada" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
      + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('hostname_ip') + '</label>'
      + '<input id="host-hostname" type="text" placeholder="f.eks. 10.0.1.5" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
      + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;"><span id="host-user-label">' + t('brukernavn_2') + '</span></label>'
      + '<input id="host-username" type="text" placeholder="admin" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
      + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;"><span id="host-port-label">' + t('ssh_port') + '</span></label>'
      + '<input id="host-port" type="number" value="22" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
      + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('gruppe') + '</label>'
      + '<input id="host-group" type="text" placeholder="f.eks. produksjon, lab" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
      + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('autentisering') + '</label>'
      + '<select id="host-auth" onchange="hostsAuthChanged()" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
      + '<option value="password">' + t('lbl_password','Password') + '</option>'
      + '<option value="key">' + t('lbl_ssh_key','SSH key') + '</option>'
      + '</select></div>'
      + '</div>'

      // Auth fields
      + '<div id="host-auth-pass" style="margin-top:12px;"><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('passord_2') + '</label>'
      + '<input id="host-password" type="password" placeholder="' + t('placeholder_password','Password') + '" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
      + '<div id="host-auth-key" style="display:none;margin-top:12px;"><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_ssh_key','SSH key') + '</label>'
      + '<select id="host-keyid" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'+keyOpts+'</select></div>'

      // Customer selector
      + '<div style="margin-top:12px;"><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_customer','Customer') + '</label>'
      + '<select id="host-customer" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"><option value="">-- ' + t('lbl_no_customer','No customer') + ' --</option></select></div>'

      // Notes
      + '<div style="margin-top:12px;"><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_notes','Notes') + '</label>'
      + '<textarea id="host-notes" placeholder="' + t('placeholder_optional_notes','Optional notes...') + '" style="width:100%;height:50px;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;resize:vertical;"></textarea></div>'

      + '<div style="display:flex;gap:8px;margin-top:16px;">'
      + '<button class="btn btn-primary" onclick="hostsDoAdd()" style="padding:8px 20px;font-size:13px;">' + t('btn_add','Add') + '</button>'
      + '<button class="btn btn-ghost" onclick="hostsLoad()" style="padding:8px 20px;font-size:13px;">' + t('btn_cancel','Cancel') + '</button>'
      + '</div></div>';

    _populateCustomerSelect('host-customer');
    hostsTypeChanged();
  });
}

function hostsTypeChanged() {
  var type = document.getElementById('host-devtype').value;
  var portEl = document.getElementById('host-port');
  var portLabel = document.getElementById('host-port-label');
  var userEl = document.getElementById('host-username');
  var userLabel = document.getElementById('host-user-label');

  // Set sensible defaults per device type
  var defaults = {
    windows:   {port: 22, user: 'administrator', portLabel: 'SSH/RDP-port', userLabel: 'Brukernavn'},
    linux:     {port: 22, user: 'root', portLabel: 'SSH-port', userLabel: 'Brukernavn'},
    fortigate: {port: 22, user: 'admin', portLabel: 'SSH-port', userLabel: 'Admin-bruker'},
    unifi:     {port: 22, user: 'ubnt', portLabel: 'SSH-port', userLabel: 'SSH-bruker'},
    pfsense:   {port: 22, user: 'admin', portLabel: 'SSH-port', userLabel: 'Admin-bruker'},
    openwrt:   {port: 22, user: 'root', portLabel: 'SSH-port', userLabel: 'Brukernavn'},
    custom:    {port: 22, user: '', portLabel: 'Port', userLabel: 'Brukernavn'},
  };
  var d = defaults[type] || defaults.custom;
  portEl.value = d.port;
  if (!userEl.value || userEl.value === 'admin' || userEl.value === 'root' || userEl.value === 'ubnt' || userEl.value === 'administrator') {
    userEl.value = d.user;
    userEl.placeholder = d.user;
  }
  portLabel.textContent = d.portLabel;
  userLabel.textContent = d.userLabel;
}

function hostsAuthChanged() {
  var method = document.getElementById('host-auth').value;
  document.getElementById('host-auth-pass').style.display = method === 'password' ? 'block' : 'none';
  document.getElementById('host-auth-key').style.display = method === 'key' ? 'block' : 'none';
}

async function hostsDoAdd() {
  var body = {
    label: document.getElementById('host-label').value.trim(),
    hostname: document.getElementById('host-hostname').value.trim(),
    username: document.getElementById('host-username').value.trim(),
    port: parseInt(document.getElementById('host-port').value) || 22,
    device_type: document.getElementById('host-devtype').value,
    group_name: document.getElementById('host-group').value.trim(),
    auth_method: document.getElementById('host-auth').value,
    notes: document.getElementById('host-notes').value.trim(),
  };

  var custSel = document.getElementById('host-customer');
  if (custSel && custSel.value) body.customer_id = custSel.value;

  if (!body.label || !body.hostname || !body.username) {
    showToast(t('err_name_host_user_required','Name, hostname and username are required'), 'error');
    return;
  }

  if (body.auth_method === 'key') {
    var keyId = document.getElementById('host-keyid').value;
    if (keyId) body.auth_key_id = keyId;
  } else {
    var pass = document.getElementById('host-password').value;
    if (pass) body.password = pass;
  }

  var data = await apiFetch('/api/ssh/hosts', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if (data && data.ok) { showToast(t('msg_host_added','Host added'), 'success'); hostsLoad(); }
}

async function hostsHealthAll() {
  showToast(t('msg_checking_all_hosts','Checking all hosts...'), 'info', 2000);
  var data = await apiFetch('/api/ssh/hosts/health', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
  if (data) { showToast(t('msg_health_check_done','Health check completed'), 'success'); hostsLoad(); }
}

// ═══════════════════════════════════════════════════════════════════
// SSH MANAGEMENT
// ═══════════════════════════════════════════════════════════════════

async function sshShowKeys() {
  var el = document.getElementById('ssh-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';
  var data = await apiFetch('/api/ssh/keys');
  if (!data) return;
  var keys = data.keys || [];
  var html = '<div style="display:flex;gap:8px;margin-bottom:12px;"><button class="btn btn-primary" onclick="sshGenKey()" style="padding:6px 14px;font-size:12px;">' + t('btn_generate_key','Generate key') + '</button><button class="btn btn-ghost" onclick="sshImportKey()" style="padding:6px 14px;font-size:12px;">' + t('btn_import_key','Import key') + '</button></div>';
  if (!keys.length) { html += '<p style="color:var(--text-muted);">' + t('msg_no_ssh_keys','No SSH keys created yet.') + '</p>'; }
  else {
    html += '<table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:8px;">' + t('lbl_name','Name') + '</th><th>' + t('lbl_type','Type') + '</th><th>' + t('fingerprint_2') + '</th><th>' + t('lbl_created','Created') + '</th><th></th></tr></thead><tbody>';
    keys.forEach(function(k) {
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += '<td style="padding:8px;font-weight:600;">'+k.name+'</td>';
      html += '<td style="padding:8px;text-align:center;"><span style="padding:2px 8px;background:var(--bg);border-radius:4px;font-size:11px;font-family:var(--mono);">'+k.key_type+'</span></td>';
      html += '<td style="padding:8px;font-family:var(--mono);font-size:11px;color:var(--text-muted);">'+k.fingerprint+'</td>';
      html += '<td style="padding:8px;font-size:12px;color:var(--text-muted);">'+k.created_at.slice(0,10)+'</td>';
      html += '<td style="padding:8px;white-space:nowrap;"><button class="btn btn-ghost" onclick="sshViewKey(\''+k.id+'\')" style="padding:2px 8px;font-size:11px;">' + t('vis') + '</button> <button class="btn btn-ghost" onclick="sshDeleteKey(\''+k.id+'\')" style="padding:2px 8px;font-size:11px;color:var(--red);">' + t('slett') + '</button></td>';
      html += '</tr>';
    });
    html += '</tbody></table>';
  }
  el.innerHTML = html;
}

function sshGenKey() {
  var el = document.getElementById('ssh-content');
  el.innerHTML = '<div style="max-width:500px;">'
    + '<h3 style="font-size:15px;font-weight:600;margin-bottom:16px;">' + t('hdr_generate_ssh_key','Generate SSH key') + '</h3>'
    + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('navn_2') + '</label>'
    + '<input id="ssh-gen-name" type="text" placeholder="f.eks. deploy-key-kunde" style="width:100%;padding:8px 12px;margin-bottom:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
    + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_key_type','Key type') + '</label>'
    + '<select id="ssh-gen-type" style="width:100%;padding:8px 12px;margin-bottom:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
    + '<option value="ed25519">' + t('opt_ed25519','Ed25519 (recommended — fast, secure, short key)') + '</option>'
    + '<option value="rsa4096">' + t('opt_rsa4096','RSA 4096-bit (broad compatibility)') + '</option>'
    + '<option value="rsa2048">' + t('opt_rsa2048','RSA 2048-bit (legacy devices)') + '</option>'
    + '</select>'
    + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_description_optional','Description (optional)') + '</label>'
    + '<input id="ssh-gen-desc" type="text" placeholder="' + t('placeholder_key_desc','e.g. Used for automatic deploy to web servers') + '" style="width:100%;padding:8px 12px;margin-bottom:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
    + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_tags_optional','Tags (comma-separated, optional)') + '</label>'
    + '<input id="ssh-gen-tags" type="text" placeholder="f.eks. produksjon, deploy, web" style="width:100%;padding:8px 12px;margin-bottom:16px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
    + '<div id="ssh-gen-result" style="display:none;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px;"></div>'
    + '<div style="display:flex;gap:8px;">'
    + '<button class="btn btn-primary" id="ssh-gen-btn" onclick="sshDoGenKey()" style="padding:8px 20px;font-size:13px;">' + t('btn_generate','Generate') + '</button>'
    + '<button class="btn btn-ghost" onclick="sshShowKeys()" style="padding:8px 20px;font-size:13px;">' + t('btn_cancel','Cancel') + '</button>'
    + '</div></div>';
}

async function sshDoGenKey() {
  var name = document.getElementById('ssh-gen-name').value.trim();
  if (!name) { showToast(t('err_give_key_name','Give the key a name'),'error'); return; }
  var keyType = document.getElementById('ssh-gen-type').value;
  var desc = document.getElementById('ssh-gen-desc').value.trim();
  var tagsStr = document.getElementById('ssh-gen-tags').value.trim();
  var tags = tagsStr ? tagsStr.split(',').map(function(s){return s.trim();}).filter(Boolean) : [];

  var btn = document.getElementById('ssh-gen-btn');
  btn.disabled = true; btn.textContent = t('msg_generating','Generating...');

  var data = await apiFetch('/api/ssh/keys', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name, key_type:keyType, description:desc, tags:tags})});
  btn.disabled = false; btn.textContent = t('btn_generate','Generate');

  if (data && data.ok) {
    var k = data.key;
    var resEl = document.getElementById('ssh-gen-result');
    resEl.style.display = 'block';
    resEl.innerHTML = '<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;"><span style="font-size:18px;">&#10003;</span><strong style="color:var(--green);">' + t('msg_key_created','Key created') + '</strong></div>'
      + '<div style="font-size:12px;margin-bottom:8px;"><strong>' + t('fingerprint') + '</strong> <span style="font-family:var(--mono);">'+k.fingerprint+'</span></div>'
      + '<div style="font-size:12px;margin-bottom:8px;"><strong>' + t('type_3') + '</strong> '+k.key_type+'</div>'
      + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_public_key_copy','Public key (copy to servers):') + '</label>'
      + '<div style="position:relative;"><textarea readonly style="width:100%;height:60px;padding:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:11px;font-family:var(--mono);resize:none;">'+k.public_key+'</textarea>'
      + '<button onclick="navigator.clipboard.writeText(\''+k.public_key.replace(/'/g,"\\'")+'\');showToast(t(\'msg_copied_short\',\'Copied!\'),\'success\',1500);" style="position:absolute;top:4px;right:4px;padding:2px 8px;font-size:11px;background:var(--bg-card);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--text-muted);">' + t('btn_copy','Copy') + '</button></div>';
    showToast(t('msg_ssh_key_generated','SSH key generated'),'success');
  }
}

function sshImportKey() {
  var el = document.getElementById('ssh-content');
  el.innerHTML = '<div style="max-width:500px;">'
    + '<h3 style="font-size:15px;font-weight:600;margin-bottom:16px;">' + t('hdr_import_ssh_key','Import SSH key') + '</h3>'
    + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('navn_2') + '</label>'
    + '<input id="ssh-imp-name" type="text" placeholder="f.eks. eksisterende-deploy-key" style="width:100%;padding:8px 12px;margin-bottom:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
    + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_private_key_pem','Private key (PEM or OpenSSH format)') + '</label>'
    + '<textarea id="ssh-imp-pem" rows="8" placeholder="-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----" style="width:100%;padding:8px 12px;margin-bottom:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:11px;font-family:var(--mono);resize:vertical;"></textarea>'
    + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_description_optional','Description (optional)') + '</label>'
    + '<input id="ssh-imp-desc" type="text" placeholder="' + t('placeholder_key_desc','e.g. Used for automatic deploy to web servers') + '" style="width:100%;padding:8px 12px;margin-bottom:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
    + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_tags_optional','Tags (comma-separated, optional)') + '</label>'
    + '<input id="ssh-imp-tags" type="text" placeholder="f.eks. produksjon, deploy, web" style="width:100%;padding:8px 12px;margin-bottom:16px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
    + '<div id="ssh-imp-result" style="display:none;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px;"></div>'
    + '<div style="display:flex;gap:8px;">'
    + '<button class="btn btn-primary" id="ssh-imp-btn" onclick="sshDoImportKey()" style="padding:8px 20px;font-size:13px;">' + t('btn_import','Import') + '</button>'
    + '<button class="btn btn-ghost" onclick="sshShowKeys()" style="padding:8px 20px;font-size:13px;">' + t('btn_cancel','Cancel') + '</button>'
    + '</div></div>';
}

async function sshDoImportKey() {
  var name = document.getElementById('ssh-imp-name').value.trim();
  if (!name) { showToast(t('err_give_key_name','Give the key a name'),'error'); return; }
  var pem = document.getElementById('ssh-imp-pem').value;
  if (!pem.trim()) { showToast(t('err_paste_private_key','Paste the private key'),'error'); return; }
  var desc = document.getElementById('ssh-imp-desc').value.trim();
  var tagsStr = document.getElementById('ssh-imp-tags').value.trim();
  var tags = tagsStr ? tagsStr.split(',').map(function(s){return s.trim();}).filter(Boolean) : [];

  var btn = document.getElementById('ssh-imp-btn');
  btn.disabled = true; btn.textContent = t('msg_importing','Importing...');

  var data = await apiFetch('/api/ssh/keys/import', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name, private_key_pem:pem, description:desc, tags:tags})});
  btn.disabled = false; btn.textContent = t('btn_import','Import');

  if (data && data.ok) {
    var k = data.key;
    var resEl = document.getElementById('ssh-imp-result');
    resEl.style.display = 'block';
    resEl.innerHTML = '<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;"><span style="font-size:18px;">&#10003;</span><strong style="color:var(--green);">' + t('msg_key_imported','Key imported') + '</strong></div>'
      + '<div style="font-size:12px;margin-bottom:8px;"><strong>' + t('fingerprint') + '</strong> <span style="font-family:var(--mono);">'+k.fingerprint+'</span></div>'
      + '<div style="font-size:12px;margin-bottom:8px;"><strong>' + t('type_3') + '</strong> '+k.key_type+'</div>'
      + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_public_key_copy','Public key (copy to servers):') + '</label>'
      + '<div style="position:relative;"><textarea readonly style="width:100%;height:60px;padding:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:11px;font-family:var(--mono);resize:none;">'+k.public_key+'</textarea>'
      + '<button onclick="navigator.clipboard.writeText(\''+k.public_key.replace(/'/g,"\\'")+'\');showToast(t(\'msg_copied_short\',\'Copied!\'),\'success\',1500);" style="position:absolute;top:4px;right:4px;padding:2px 8px;font-size:11px;background:var(--bg-card);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--text-muted);">' + t('btn_copy','Copy') + '</button></div>';
    showToast(t('msg_ssh_key_imported','Key imported') + ': ' + k.fingerprint, 'success', 5000);
  }
}

async function sshViewKey(keyId) {
  var data = await apiFetch('/api/ssh/keys/' + keyId);
  if (!data || !data.key) return;
  var k = data.key;
  var el = document.getElementById('ssh-content');
  var html = '<div style="max-width:560px;">'
    + '<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">'
    + '<button class="btn btn-ghost" onclick="sshShowKeys()" style="padding:4px 10px;font-size:12px;">' + t('tilbake') + '</button>'
    + '<h3 style="font-size:15px;font-weight:600;margin:0;">'+k.name+'</h3>'
    + '<span style="padding:2px 8px;background:var(--bg);border-radius:4px;font-size:11px;font-family:var(--mono);">'+k.key_type+'</span>'
    + '</div>'
    + '<div class="card" style="padding:16px;">'
    + '<table style="width:100%;font-size:13px;">'
    + '<tr style="border-bottom:1px solid var(--border);"><td style="padding:8px;color:var(--text-muted);width:120px;">' + t('fingerprint_2') + '</td><td style="padding:8px;font-family:var(--mono);font-size:11px;">'+k.fingerprint+'</td></tr>'
    + '<tr style="border-bottom:1px solid var(--border);"><td style="padding:8px;color:var(--text-muted);">' + t('type_3') + '</td><td style="padding:8px;">'+k.key_type+'</td></tr>'
    + '<tr style="border-bottom:1px solid var(--border);"><td style="padding:8px;color:var(--text-muted);">' + t('lbl_created','Created') + '</td><td style="padding:8px;">'+k.created_at.slice(0,10)+'</td></tr>';
  if (k.description) html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:8px;color:var(--text-muted);">' + t('lbl_description','Description') + '</td><td style="padding:8px;">'+k.description+'</td></tr>';
  html += '</table></div>'
    + '<div style="margin-top:12px;"><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('public_key') + '</label>'
    + '<div style="position:relative;"><textarea readonly style="width:100%;height:60px;padding:8px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:11px;font-family:var(--mono);resize:none;">'+k.public_key+'</textarea>'
    + '<button onclick="navigator.clipboard.writeText(\''+k.public_key.replace(/'/g,"\\'")+'\');showToast(t(\'msg_copied_short\',\'Copied!\'),\'success\',1500);" style="position:absolute;top:4px;right:4px;padding:2px 8px;font-size:11px;background:var(--bg-card);border:1px solid var(--border);border-radius:4px;cursor:pointer;color:var(--text-muted);">' + t('btn_copy','Copy') + '</button></div></div>';

  // Show deployments
  if (data.deployments && data.deployments.length) {
    html += '<div style="margin-top:16px;"><div style="font-size:13px;font-weight:600;margin-bottom:8px;">' + t('lbl_deployed_to','Deployed to') + ' ('+data.deployments.length+' ' + t('lbl_hosts','hosts') + ')</div>';
    data.deployments.forEach(function(d) {
      html += '<div style="font-size:12px;color:var(--text-muted);padding:4px 0;">' + t('lbl_host','Host') + ': '+d.host_id.slice(0,8)+'... — '+d.deployed_at.slice(0,10)+'</div>';
    });
    html += '</div>';
  }

  html += '</div>';
  el.innerHTML = html;
}

async function sshDeleteKey(id) {
  if (!await showConfirm(t('dlg_confirm_delete_ssh_key'))) return;
  await apiFetch('/api/ssh/keys/'+id, {method:'DELETE'});
  sshShowKeys();
}

async function sshShowHosts() {
  var el = document.getElementById('ssh-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';
  var data = await apiFetch('/api/ssh/hosts');
  if (!data) return;
  var hosts = data.hosts || [];
  var html = '<div style="display:flex;gap:8px;margin-bottom:12px;"><button class="btn btn-primary" onclick="sshAddHost()" style="padding:6px 14px;font-size:12px;">' + t('legg_til_vert') + '</button><button class="btn btn-ghost" onclick="sshHealthAll()" style="padding:6px 14px;font-size:12px;">' + t('sjekk_alle') + '</button></div>';
  if (!hosts.length) { html += '<p style="color:var(--text-muted);">' + t('msg_no_hosts_short','No hosts registered.') + '</p>'; }
  else {
    html += '<table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:8px;">' + t('navn_2') + '</th><th>' + t('host_2') + '</th><th>' + t('type_3') + '</th><th>' + t('gruppe') + '</th><th>' + t('lbl_customer','Customer') + '</th><th>' + t('status_3') + '</th><th></th></tr></thead><tbody>';
    hosts.forEach(function(h) {
      var statusColor = h.is_reachable === true ? 'var(--green)' : h.is_reachable === false ? 'var(--red)' : 'var(--text-dim)';
      var statusDot = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:'+statusColor+';"></span>';
      var _custName = h.customer_id ? _customerNameById(h.customer_id) : '-';
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += '<td style="padding:8px;font-weight:600;">'+h.label+'</td>';
      html += '<td style="padding:8px;font-family:var(--mono);font-size:12px;">'+h.hostname+':'+h.port+'</td>';
      html += '<td style="padding:8px;font-size:12px;">'+h.device_type+'</td>';
      html += '<td style="padding:8px;font-size:12px;color:var(--text-muted);">'+(h.group_name||'-')+'</td>';
      html += '<td style="padding:8px;font-size:12px;">' + (h.customer_id ? '<a href="javascript:void(0)" onclick="overviewSelectCustomer(\'' + h.customer_id + '\')" style="color:var(--blue);text-decoration:none;">' + esc(_custName) + '</a>' : '-') + '</td>';
      html += '<td style="padding:8px;text-align:center;">'+statusDot+'</td>';
      html += '<td style="padding:8px;white-space:nowrap;">';
      html += '<button class="btn btn-ghost" onclick="sshEditHost(\''+h.id+'\')" style="padding:2px 8px;font-size:11px;">' + t('rediger') + '</button> ';
      html += '<button class="btn btn-ghost" onclick="sshTerminal(\''+h.id+'\')" style="padding:2px 8px;font-size:11px;color:var(--blue);">SSH</button> ';
      if (h.device_type === 'windows' || h.device_type === 'linux') {
        html += '<button class="btn btn-ghost" onclick="sshRdp(\''+h.hostname+'\',\''+h.username+'\')" style="padding:2px 8px;font-size:11px;color:var(--purple);">RDP</button> ';
      }
      html += '<button class="btn btn-ghost" onclick="sshDeleteHost(\''+h.id+'\')" style="padding:2px 8px;font-size:11px;color:var(--red);">' + t('slett') + '</button>';
      html += '</td>';
      html += '</tr>';
    });
    html += '</tbody></table>';
  }
  el.innerHTML = html;
}

function sshAddHost() {
  // Load keys for dropdown
  apiFetch('/api/ssh/keys').then(function(keysData) {
    var keys = (keysData && keysData.keys) || [];
    var keyOpts = '<option value="">' + t('ingen_bruk_passord') + '</option>';
    keys.forEach(function(k) { keyOpts += '<option value="'+k.id+'">'+k.name+' ('+k.key_type+' — '+k.fingerprint.slice(0,20)+'...)</option>'; });

    var el = document.getElementById('ssh-content');
    el.innerHTML = '<div style="max-width:560px;">'
      + '<h3 style="font-size:15px;font-weight:600;margin-bottom:16px;">' + t('legg_til_vertsmaskin') + '</h3>'
      + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">'
      // Rad 1: Navn + Hostname
      + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('navn_label') + '</label>'
      + '<input id="ssh-h-label" type="text" placeholder="f.eks. Webserver Prod" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
      + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('hostname_ip') + '</label>'
      + '<input id="ssh-h-host" type="text" placeholder="f.eks. 10.0.1.5" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
      // Rad 2: Brukernavn + Port
      + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('brukernavn_2') + '</label>'
      + '<input id="ssh-h-user" type="text" value="root" placeholder="root" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
      + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('port_2') + '</label>'
      + '<input id="ssh-h-port" type="number" value="22" min="1" max="65535" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
      // Rad 3: Enhetstype + Gruppe
      + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('enhetstype') + '</label>'
      + '<select id="ssh-h-devtype" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
      + '<option value="linux">Linux</option>'
      + '<option value="fortigate">FortiGate</option>'
      + '<option value="unifi">UniFi</option>'
      + '<option value="pfsense">pfSense</option>'
      + '<option value="openwrt">OpenWrt</option>'
      + '<option value="windows">Windows</option>'
      + '<option value="custom">' + t('annet') + '</option>'
      + '</select></div>'
      + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('gruppe') + '</label>'
      + '<input id="ssh-h-group" type="text" placeholder="f.eks. produksjon, lab, kunde-x" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
      + '</div>'
      // Autentisering
      + '<div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--border);">'
      + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_auth_method','Authentication method') + '</label>'
      + '<select id="ssh-h-auth" onchange="sshHostAuthChanged()" style="width:100%;padding:8px 12px;margin-bottom:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
      + '<option value="key">' + t('lbl_ssh_key','SSH key') + '</option>'
      + '<option value="password">' + t('lbl_password','Password') + '</option>'
      + '</select>'
      + '<div id="ssh-h-auth-key">'
      + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_ssh_key','SSH key') + '</label>'
      + '<select id="ssh-h-keyid" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'+keyOpts+'</select>'
      + '</div>'
      + '<div id="ssh-h-auth-pass" style="display:none;">'
      + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_password','Password') + '</label>'
      + '<input id="ssh-h-pass" type="password" placeholder="' + t('placeholder_ssh_password','SSH password') + '" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
      + '</div></div>'
      // Customer selector
      + '<div style="margin-top:12px;">'
      + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_customer','Customer') + '</label>'
      + '<select id="ssh-h-customer" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"><option value="">-- ' + t('lbl_no_customer','No customer') + ' --</option></select>'
      + '</div>'
      // Notater
      + '<div style="margin-top:12px;">'
      + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_notes_optional','Notes (optional)') + '</label>'
      + '<textarea id="ssh-h-notes" placeholder="' + t('placeholder_notes_example','e.g. Belongs to customer X, maintenance window Sundays...') + '" style="width:100%;height:60px;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;resize:vertical;"></textarea>'
      + '</div>'
      // Knapper
      + '<div style="display:flex;gap:8px;margin-top:16px;">'
      + '<button class="btn btn-primary" onclick="sshDoAddHost()" style="padding:8px 20px;font-size:13px;">' + t('btn_add','Add') + '</button>'
      + '<button class="btn btn-ghost" onclick="sshShowHosts()" style="padding:8px 20px;font-size:13px;">' + t('btn_cancel','Cancel') + '</button>'
      + '</div></div>';
    _populateCustomerSelect('ssh-h-customer');
  });
}

function sshHostAuthChanged() {
  var method = document.getElementById('ssh-h-auth').value;
  document.getElementById('ssh-h-auth-key').style.display = method === 'key' ? 'block' : 'none';
  document.getElementById('ssh-h-auth-pass').style.display = method === 'password' ? 'block' : 'none';
}

async function sshDoAddHost() {
  var label = document.getElementById('ssh-h-label').value.trim();
  var hostname = document.getElementById('ssh-h-host').value.trim();
  var username = document.getElementById('ssh-h-user').value.trim();
  if (!label || !hostname || !username) { showToast(t('err_name_host_user_required','Name, hostname and username are required'),'error'); return; }

  var body = {
    label: label,
    hostname: hostname,
    username: username,
    port: parseInt(document.getElementById('ssh-h-port').value) || 22,
    device_type: document.getElementById('ssh-h-devtype').value,
    group_name: document.getElementById('ssh-h-group').value.trim(),
    auth_method: document.getElementById('ssh-h-auth').value,
    notes: document.getElementById('ssh-h-notes').value.trim(),
  };

  var custSel = document.getElementById('ssh-h-customer');
  if (custSel && custSel.value) body.customer_id = custSel.value;

  if (body.auth_method === 'key') {
    var keyId = document.getElementById('ssh-h-keyid').value;
    if (keyId) body.auth_key_id = keyId;
  } else {
    var pass = document.getElementById('ssh-h-pass').value;
    if (pass) body.password = pass;
  }

  var data = await apiFetch('/api/ssh/hosts', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if (data && data.ok) { showToast(t('msg_host_added','Host added'),'success'); sshShowHosts(); }
}

async function sshDeleteHost(id) {
  if (!await showConfirm(t('dlg_confirm_delete_ssh_host'))) return;
  await apiFetch('/api/ssh/hosts/'+id, {method:'DELETE'});
  sshShowHosts();
}

async function sshEditHost(hostId) {
  var data = await apiFetch('/api/ssh/hosts/' + hostId);
  if (!data || !data.host) return;
  var h = data.host;

  // Load keys for dropdown
  var keysData = await apiFetch('/api/ssh/keys');
  var keys = (keysData && keysData.keys) || [];
  var keyOpts = '<option value="">' + t('ingen_bruk_passord') + '</option>';
  keys.forEach(function(k) { keyOpts += '<option value="'+k.id+'"'+(k.id===h.auth_key_id?' selected':'')+'>'+k.name+' ('+k.fingerprint.slice(0,20)+'...)</option>'; });

  // Use hosts-content if available, else ssh-content
  var el = document.getElementById('hosts-content') || document.getElementById('ssh-content');
  el.innerHTML = '<div style="max-width:560px;">'
    + '<h3 style="font-size:15px;font-weight:600;margin-bottom:16px;">' + t('rediger_vertsmaskin') + '</h3>'
    + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">'
    + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('navn_2') + '</label>'
    + '<input id="ssh-e-label" type="text" value="'+h.label+'" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
    + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('hostname_ip') + '</label>'
    + '<input id="ssh-e-host" type="text" value="'+h.hostname+'" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
    + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('brukernavn_2') + '</label>'
    + '<input id="ssh-e-user" type="text" value="'+h.username+'" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
    + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('port_2') + '</label>'
    + '<input id="ssh-e-port" type="number" value="'+h.port+'" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
    + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('enhetstype') + '</label>'
    + '<select id="ssh-e-devtype" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
    + ['linux','fortigate','unifi','pfsense','openwrt','windows','custom'].map(function(t){return '<option value="'+t+'"'+(t===h.device_type?' selected':'')+'>'+t+'</option>';}).join('')
    + '</select></div>'
    + '<div><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('gruppe') + '</label>'
    + '<input id="ssh-e-group" type="text" value="'+(h.group_name||'')+'" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
    + '</div>'
    + '<div style="margin-top:12px;"><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('passord_2') + '</label>'
    + '<input id="ssh-e-pass" type="password" placeholder="(uendret)" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"></div>'
    + '<div style="margin-top:12px;"><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_ssh_key','SSH key') + '</label>'
    + '<select id="ssh-e-keyid" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'+keyOpts+'</select></div>'
    + '<div style="margin-top:12px;"><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_customer','Customer') + '</label>'
    + '<select id="ssh-e-customer" style="width:100%;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"><option value="">-- ' + t('lbl_no_customer','No customer') + ' --</option></select></div>'
    + '<div style="margin-top:12px;"><label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_notes','Notes') + '</label>'
    + '<textarea id="ssh-e-notes" style="width:100%;height:60px;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;resize:vertical;">'+(h.notes||'')+'</textarea></div>'
    + '<div style="display:flex;gap:8px;margin-top:16px;">'
    + '<button class="btn btn-primary" onclick="sshDoEditHost(\''+hostId+'\')" style="padding:8px 20px;font-size:13px;">' + t('btn_save','Save') + '</button>'
    + '<button class="btn btn-ghost" onclick="hostsLoad?hostsLoad():sshShowHosts()" style="padding:8px 20px;font-size:13px;">' + t('btn_cancel','Cancel') + '</button>'
    + '</div></div>';
  _populateCustomerSelect('ssh-e-customer', h.customer_id);
}

async function sshDoEditHost(hostId) {
  var body = {
    label: document.getElementById('ssh-e-label').value.trim(),
    hostname: document.getElementById('ssh-e-host').value.trim(),
    username: document.getElementById('ssh-e-user').value.trim(),
    port: parseInt(document.getElementById('ssh-e-port').value) || 22,
    device_type: document.getElementById('ssh-e-devtype').value,
    group_name: document.getElementById('ssh-e-group').value.trim(),
    auth_key_id: document.getElementById('ssh-e-keyid').value || null,
    notes: document.getElementById('ssh-e-notes').value.trim(),
    customer_id: document.getElementById('ssh-e-customer').value || null,
  };
  var pass = document.getElementById('ssh-e-pass').value;
  if (pass) body.password = pass;
  var data = await apiFetch('/api/ssh/hosts/' + hostId, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if (data && data.ok) { showToast(t('msg_host_updated','Host updated'),'success'); hostsLoad ? hostsLoad() : sshShowHosts(); }
}

async function sshRdp(hostname, username, hostId) {
  // Navigate to RDP view and pre-fill host details
  showView('rdp');
  setTimeout(function() {
    var hostInput = document.getElementById('rdp-host-input');
    var userInput = document.getElementById('rdp-user-input');
    if (hostInput) hostInput.value = hostname;
    if (userInput) userInput.value = username || '';
    // Fetch stored password for RDP
    if (hostId) {
      apiFetch('/api/ssh/hosts/' + hostId + '/password').then(function(d) {
        if (d && d.password) {
          var passInput = document.getElementById('rdp-pass-input');
          if (passInput) passInput.value = d.password;
        }
      });
    }
  }, 200);
  return;
  // Legacy code below — kept for reference
  var data = await apiFetch('/api/rdp/launch', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({host: hostname, username: username, host_id: hostId || '', port: 3389})
  });
  if (data && data.ok) {
    showToast(t('msg_rdp_opened','RDP opened') + ': ' + data.client, 'success');
  } else {
    showToast(data && data.error ? data.error : t('err_rdp_failed','Could not start RDP'), 'error');
  }
}

function sshTerminal(hostId) {
  showView('terminal');
  document.getElementById('term-mode').value = 'ssh';
  termModeChanged();
  setTimeout(function() {
    document.getElementById('term-host-select').value = hostId;
    termConnect();
  }, 500);
}

async function sshHealthAll() {
  showToast(t('msg_checking_all_hosts','Checking all hosts...'),'info',2000);
  var data = await apiFetch('/api/ssh/hosts/health', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
  if (data) { showToast(t('msg_health_check_done','Health check completed'),'success'); sshShowHosts(); }
}

async function sshShowExec() {
  var el = document.getElementById('ssh-content');
  el.innerHTML = '<div style="margin-bottom:12px;"><label style="font-size:13px;font-weight:600;">' + t('lbl_select_hosts_command','Select hosts and enter a command:') + '</label></div>'
    + '<div id="ssh-exec-hosts" style="margin-bottom:12px;"></div>'
    + '<div style="display:flex;gap:8px;"><input id="ssh-exec-cmd" type="text" placeholder="f.eks. uptime" style="flex:1;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-family:var(--mono);font-size:13px;" onkeydown="if(event.key===\'Enter\')sshExecRun()"><button class="btn btn-primary" onclick="sshExecRun()" style="padding:8px 16px;">' + t('btn_run','Run') + '</button></div>'
    + '<div id="ssh-exec-results" style="margin-top:16px;"></div>';
  // Load hosts for checkboxes
  var data = await apiFetch('/api/ssh/hosts');
  if (!data) return;
  var hhtml = '';
  (data.hosts||[]).forEach(function(h) {
    hhtml += '<label style="display:inline-flex;align-items:center;gap:4px;margin-right:12px;font-size:13px;cursor:pointer;"><input type="checkbox" class="ssh-exec-host-cb" value="'+h.id+'"> '+h.label+'</label>';
  });
  document.getElementById('ssh-exec-hosts').innerHTML = hhtml || '<span style="color:var(--text-muted);">' + t('msg_no_hosts_short','No hosts registered.') + '</span>';
}

async function sshExecRun() {
  var cmd = document.getElementById('ssh-exec-cmd').value.trim();
  if (!cmd) return;
  var ids = []; document.querySelectorAll('.ssh-exec-host-cb:checked').forEach(function(cb){ids.push(cb.value);});
  if (!ids.length) { showToast(t('err_select_at_least_one_host','Select at least one host'),'error'); return; }
  document.getElementById('ssh-exec-results').innerHTML = '<div class="loader" style="width:20px;height:20px;margin:12px auto;"></div>';
  var data = await apiFetch('/api/ssh/exec', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({host_ids:ids,command:cmd})});
  if (!data) return;
  var html = '';
  (data.results||[]).forEach(function(r) {
    var color = r.exit_code === 0 ? 'var(--green)' : 'var(--red)';
    html += '<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px;">';
    html += '<div style="display:flex;justify-content:space-between;margin-bottom:8px;"><strong>'+r.host_label+'</strong><span style="color:'+color+';font-size:12px;">rc='+r.exit_code+'</span></div>';
    if (r.stdout) html += '<pre style="font-size:12px;font-family:var(--mono);color:var(--text-muted);white-space:pre-wrap;margin:0;">'+r.stdout+'</pre>';
    if (r.stderr) html += '<pre style="font-size:12px;font-family:var(--mono);color:var(--red);white-space:pre-wrap;margin:4px 0 0;">'+r.stderr+'</pre>';
    if (r.error) html += '<div style="color:var(--red);font-size:12px;margin-top:4px;">'+r.error+'</div>';
    html += '</div>';
  });
  document.getElementById('ssh-exec-results').innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════
// VPN MANAGEMENT
// ═══════════════════════════════════════════════════════════════════

async function vpnLoadProfiles() {
  var el = document.getElementById('vpn-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';
  if (!_infraCustomerCache) { await _populateCustomerSelect('_dummy_nonexistent_'); }
  var data = await apiFetch('/api/vpn/profiles');
  var status = await apiFetch('/api/vpn/status');
  if (!data) return;
  // Update status badge
  var badge = document.getElementById('vpn-status-badge');
  if (badge && status) {
    var conns = (status.connections || []);
    var activeCount = conns.filter(function(c){return c.state==='connected';}).length;
    var connectingCount = conns.filter(function(c){return c.state==='connecting';}).length;
    var st = activeCount > 0 ? 'connected' : connectingCount > 0 ? 'connecting' : 'disconnected';
    var colors = {connected:'var(--green)',connecting:'var(--orange)',disconnected:'var(--text-dim)',error:'var(--red)'};
    var label = st === 'connected' ? (activeCount > 1 ? activeCount + ' VPN' : t('vpn_connected','Connected'))
      : st === 'connecting' ? t('vpn_connecting','Connecting...')
      : t('vpn_disconnected','Disconnected');
    badge.textContent = label;
    badge.style.color = colors[st] || 'var(--text-dim)';
    badge.style.borderColor = colors[st] || 'var(--border)';
  }
  var profiles = data.profiles || [];
  var protocolLabels = {
    wireguard: 'WireGuard', openvpn: 'OpenVPN', azure: 'Azure P2S VPN',
    fortigate_ipsec: 'FortiGate IPsec', fortigate: 'FortiGate SSL',
  };
  var protocolIcons = {
    wireguard: '&#128272;', openvpn: '&#128274;', azure: '&#9729;',
    fortigate_ipsec: '&#128737;', fortigate: '&#128737;',
  };
  var html = '';
  if (!profiles.length) { html = '<div class="empty-state" style="padding:var(--space-8);"><div class="empty-icon">&#128274;</div><div class="empty-title">' + t('msg_no_vpn_profiles','No VPN profiles') + '</div><div class="empty-desc">' + t('msg_import_vpn','Import a .conf, .ovpn or .xml file to add a profile.') + '</div></div>'; }
  else {
    // Connection info summary when connected
    if (status && status.state === 'connected') {
      var stats = status.stats || {};
      var protoName = protocolLabels[stats.protocol] || stats.protocol || '';
      html += '<div class="card" style="border-color:var(--green);margin-bottom:var(--space-4);background:rgba(63,185,80,0.05);">'
        + '<div style="display:flex;align-items:center;gap:var(--space-3);margin-bottom:var(--space-4);">'
        + '<span style="width:12px;height:12px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);"></span>'
        + '<strong style="color:var(--green);flex:1;">' + t('vpn_connected','Connected') + (stats.profile_name ? ' — ' + esc(stats.profile_name) : '') + '</strong>'
        + '<span style="font-size:var(--font-xs);color:var(--text-muted);background:var(--bg);padding:2px 8px;border-radius:var(--radius-sm);">' + esc(protoName) + '</span>'
        + '</div>'
        + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:var(--space-3) var(--space-4);font-size:var(--font-xs);">'
        + _vpnStatField('Interface', status.interface)
        + _vpnStatField('Local IP', stats.local_ip)
        + _vpnStatField('Subnet', stats.subnet || stats.local_subnet)
        + _vpnStatField('Public IP', stats.public_ip)
        + _vpnStatField('Remote', stats.remote_ip)
        + _vpnStatField('Gateway', stats.gateway)
        + _vpnStatField('MTU', stats.mtu)
        + _vpnStatField('DNS', stats.dns_servers)
        + _vpnStatField('Encryption', stats.encryption)
        + _vpnStatField('TX', stats.tx_bytes ? _formatBytes(stats.tx_bytes) + (stats.tx_packets ? ' (' + stats.tx_packets + ' pkts)' : '') : null)
        + _vpnStatField('RX', stats.rx_bytes ? _formatBytes(stats.rx_bytes) + (stats.rx_packets ? ' (' + stats.rx_packets + ' pkts)' : '') : null)
        + _vpnStatField('Uptime', stats.uptime)
        + _vpnStatField(t('bc_network','Routes'), stats.route_count ? stats.route_count + ' ' + t('lbl_routes','routes') : null)
        + '</div>'
        + (stats.remote_subnets && stats.remote_subnets.length ? '<div style="margin-top:var(--space-3);"><div style="font-size:var(--font-xs);color:var(--text-dim);margin-bottom:var(--space-1);">' + t('remote_subnets') + '</div><div style="padding:var(--space-2) var(--space-3);background:var(--bg);border-radius:var(--radius-sm);font-family:var(--mono);font-size:10px;color:var(--text-muted);">' + stats.remote_subnets.map(function(r){return esc(r)}).join(' &middot; ') + '</div></div>' : '')
        + (stats.routes && stats.routes.length ? '<div style="margin-top:var(--space-3);"><div style="font-size:var(--font-xs);color:var(--text-dim);margin-bottom:var(--space-1);">' + t('lbl_routes','Routes') + '</div><div style="padding:var(--space-2) var(--space-3);background:var(--bg);border-radius:var(--radius-sm);font-family:var(--mono);font-size:10px;color:var(--text-muted);max-height:80px;overflow-y:auto;">' + stats.routes.map(function(r){return esc(r)}).join('<br>') + '</div></div>' : '')
        + '</div>';
    }

    html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:var(--space-4);">';
    profiles.forEach(function(p) {
      var conns = (status && status.connections) || [];
      var myConn = conns.find(function(c){return c.profile_id === p.id;});
      var isActive = myConn && myConn.state === 'connected';
      var isConnecting = myConn && myConn.state === 'connecting';
      var protoLabel = protocolLabels[p.protocol] || p.protocol;
      var protoIcon = protocolIcons[p.protocol] || '&#128274;';
      var statusDot = isActive ? '<span style="width:10px;height:10px;border-radius:50%;background:var(--green);display:inline-block;box-shadow:0 0 6px var(--green);"></span>'
        : isConnecting ? '<span style="width:10px;height:10px;border-radius:50%;background:var(--orange);display:inline-block;animation:pulse 1.5s infinite;"></span>'
        : '<span style="width:10px;height:10px;border-radius:50%;background:var(--text-dim);display:inline-block;"></span>';
      html += '<div class="card" style="'+(isActive?'border-color:var(--green);box-shadow:0 0 0 1px rgba(63,185,80,0.2);':'')+'">';
      html += '<div style="display:flex;align-items:center;gap:var(--space-3);margin-bottom:var(--space-3);">'+statusDot+'<strong style="flex:1;">'+esc(p.name)+'</strong><span style="padding:2px 8px;background:var(--bg);border-radius:var(--radius-sm);font-size:var(--font-xs);color:var(--text-muted);">'+protoIcon+' '+esc(protoLabel)+'</span></div>';
      if (p.description) html += '<p style="font-size:var(--font-xs);color:var(--text-muted);margin-bottom:var(--space-3);">'+esc(p.description)+'</p>';
      if (p.customer_id) { var _vcn = _customerNameById(p.customer_id); html += '<div style="font-size:var(--font-xs);color:var(--text-dim);margin-bottom:var(--space-3);">' + t('lbl_customer','Customer') + ': <a href="javascript:void(0)" onclick="overviewSelectCustomer(\'' + p.customer_id + '\')" style="color:var(--blue);text-decoration:none;">' + esc(_vcn) + '</a></div>'; }
      html += '<div style="display:flex;gap:var(--space-2);flex-wrap:wrap;">';
      if (isActive) {
        html += '<button class="btn btn-danger btn-sm" onclick="vpnDisconnect(\''+p.id+'\')">' + t('vpn_disconnect','Disconnect') + '</button>';
        html += '<button class="btn btn-ghost btn-sm" style="color:var(--red);" onclick="vpnForceDisconnect()" title="' + t('vpn_force_disconnect_tip','Kill VPN process and clean up interface') + '">' + t('vpn_force_disconnect','Force disconnect') + '</button>';
      } else if (isConnecting) {
        html += '<button class="btn btn-warning btn-sm" onclick="vpnForceDisconnect()">' + t('vpn_cancel','Cancel') + '</button>';
      } else {
        html += '<button class="btn btn-primary btn-sm" onclick="vpnConnect(\''+p.id+'\')">' + t('vpn_connect','Connect') + '</button>';
      }
      html += '<button class="btn btn-ghost btn-sm" onclick="vpnEditProfile(\''+p.id+'\')">' + t('btn_edit','Edit') + '</button>';
      html += '<button class="btn btn-ghost btn-sm" style="color:var(--text-dim);margin-left:auto;" onclick="vpnDeleteProfile(\''+p.id+'\')" title="' + t('btn_delete') + '">&#128465;</button>';
      html += '</div></div>';
    });
    html += '</div>';
  }
  el.innerHTML = html;
}

async function vpnConnect(id) {
  // Check if this is an Azure profile — needs Azure AD auth
  var profileData = await apiFetch('/api/vpn/profiles/' + id);
  if (profileData && profileData.profile && profileData.profile.protocol === 'azure') {
    vpnConnectAzure(id);
    return;
  }

  showToast(t('msg_connecting_vpn','Connecting to VPN...'),'info',3000);
  var data = await apiFetch('/api/vpn/connect/'+id, {method:'POST'});
  if (data && data.ok) { showToast(t('vpn_connected','Connected'),'success'); } else { showToast(data?.error||t('err_connection_failed','Connection failed'),'error'); }
  vpnLoadProfiles();
}

var _azureVpnProfileId = null;

async function vpnConnectAzure(profileId) {
  _azureVpnProfileId = profileId;

  // Try silent refresh first — no login needed if refresh token is cached
  showToast(t('msg_trying_auto_login','Trying automatic login...'),'info',5000);
  var silent = await apiFetch('/api/vpn/azure/try-silent', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile_id:profileId})});

  if (silent && silent.has_token) {
    showToast(t('msg_token_renewed_connecting','Token renewed — connecting to VPN...'),'info',10000);
    var connectResult = await apiFetch('/api/vpn/azure/connect-with-token', {
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({profile_id:profileId, access_token:silent.access_token})
    });
    if (connectResult && connectResult.ok) { showToast(t('msg_azure_vpn_connected','Azure VPN connected!'),'success'); }
    else { showToast(connectResult?.error||t('err_vpn_connection_failed','VPN connection failed'),'error'); }
    _azureVpnProfileId = null;
    vpnLoadProfiles();
    return;
  }

  // Silent failed — start PKCE paste-back flow (headless compatible)
  showToast(t('msg_starting_azure_login','Starting Azure login...'),'info',3000);
  var data = await apiFetch('/api/vpn/azure/pkce-start', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile_id:profileId})});
  if (!data || !data.ok) { showToast(data?.error||t('err_azure_login_failed','Could not start Azure login'),'error'); return; }

  // Show PKCE paste-back UI
  var vpnEl = document.getElementById('vpn-content');
  var html = '<div class="card" style="padding:24px;margin-bottom:16px;" id="pkce-panel">';
  html += '<div style="font-size:16px;font-weight:700;margin-bottom:12px;">' + t('azure_vpn_innlogging') + '</div>';
  html += '<div style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">' + t('1_aapne_denne_lenken_i_en_nettleser_kan_') + '</div>';
  html += '<div style="margin-bottom:16px;word-break:break-all;"><a href="'+esc(data.url)+'" target="_blank" style="font-size:13px;color:var(--blue);text-decoration:underline;">'+esc(data.url).substring(0,80)+'...</a>';
  html += ' <button class="btn btn-ghost btn-sm" onclick="var t=document.createElement(\'textarea\');t.value=this.dataset.url;document.body.appendChild(t);t.select();document.execCommand(\'copy\');document.body.removeChild(t);showToast(\'Kopiert!\',\'success\',1500);" data-url="'+esc(data.url)+'" style="margin-left:8px;">' + t('kopier') + '</button></div>';
  html += '<div style="font-size:13px;color:var(--text-muted);margin-bottom:8px;">' + t('2_logg_inn_med_azure_ad_nettleseren_vil_') + ' <code>localhost:2023</code> ' + t('den_vil_feile_det_er_forventet') + '</div>';
  html += '<div style="font-size:13px;color:var(--text-muted);margin-bottom:12px;">' + t('3_kopier_hele_urlen_fra_adressefeltet_og') + '</div>';
  html += '<div style="display:flex;gap:8px;margin-bottom:12px;">';
  html += '<input type="text" id="pkce-callback-url" placeholder="http://localhost:2023/?code=..." style="flex:1;padding:10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-family:var(--mono);font-size:12px;">';
  html += '<button class="btn btn-primary" onclick="pkceComplete(\''+esc(profileId)+'\')">' + t('koble_til') + '</button>';
  html += '</div>';
  html += '<div id="pkce-status"></div>';
  html += '<button class="btn btn-ghost btn-sm" onclick="document.getElementById(\'pkce-panel\').remove();" style="color:var(--text-dim);margin-top:8px;">' + t('avbryt_3') + '</button>';
  html += '</div>';

  var existingPanel = document.getElementById('pkce-panel');
  if (existingPanel) existingPanel.remove();
  if (vpnEl) vpnEl.insertAdjacentHTML('afterbegin', html);
}

async function pkceComplete(profileId) {
  var url = document.getElementById('pkce-callback-url').value.trim();
  if (!url) { showToast(t('lim_inn_urlen_fra_nettleseren'),'error'); return; }

  var statusEl = document.getElementById('pkce-status');
  if (statusEl) statusEl.innerHTML = '<div class="loader" style="width:16px;height:16px;display:inline-block;vertical-align:middle;margin-right:8px;"></div> Henter token...';

  var result = await apiFetch('/api/vpn/azure/pkce-complete', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({callback_url:url})
  });

  if (result && result.ok && result.access_token) {
    if (statusEl) statusEl.innerHTML = '<span style="color:var(--green);font-weight:600;">' + t('autentisert_kobler_til_vpn') + '</span>';
    var connectResult = await apiFetch('/api/vpn/azure/connect-with-token', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({profile_id:profileId, access_token:result.access_token})
    });
    if (connectResult && connectResult.ok) {
      showToast(t('azure_vpn_tilkoblet'),'success');
    } else {
      showToast(connectResult?.error||'VPN-tilkobling feilet','error');
    }
    setTimeout(function(){ var p = document.getElementById('pkce-panel'); if(p) p.remove(); vpnLoadProfiles(); }, 2000);
  } else {
    if (statusEl) statusEl.innerHTML = '<span style="color:var(--red);">' + esc(result?.error||'Autentisering feilet') + '</span>';
  }
}

// Device code flow only — no popup/browser auth for Azure VPN

async function vpnDisconnect(profileId) {
  var body = profileId ? JSON.stringify({profile_id: profileId}) : '{}';
  var data = await apiFetch('/api/vpn/disconnect', {method:'POST', headers:{'Content-Type':'application/json'}, body: body});
  if (data && data.ok) showToast(t('vpn_disconnected','Disconnected'),'success');
  else showToast(data && data.error ? data.error : t('status_error'),'error');
  vpnLoadProfiles();
  _checkVpnHeaderBadge();
}

async function vpnForceDisconnect() {
  showToast(t('vpn_force_disconnecting','Force disconnecting...'), 'warning', 2000);
  var data = await apiFetch('/api/vpn/force-disconnect', {method:'POST'});
  if (data && data.ok) showToast(t('vpn_disconnected','Disconnected'),'success');
  else {
    // Fallback — try normal disconnect
    await apiFetch('/api/vpn/disconnect', {method:'POST'});
    showToast(t('vpn_disconnected','Disconnected'),'success');
  }
  vpnLoadProfiles();
  _checkVpnHeaderBadge();
}

async function vpnDeleteProfile(id) {
  if (!await showConfirm(t('dlg_confirm_delete_vpn_profile'))) return;
  await apiFetch('/api/vpn/profiles/'+id, {method:'DELETE'});
  vpnLoadProfiles();
}

function vpnShowCreate() {
  var el = document.getElementById('vpn-content');
  el.innerHTML = '<div style="max-width:500px;">'
    + '<h3 style="font-size:15px;font-weight:600;margin-bottom:12px;">' + t('hdr_new_vpn_profile','New VPN profile') + '</h3>'
    + '<input id="vpn-create-name" type="text" placeholder="' + t('placeholder_profile_name','Profile name') + '" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
    + '<select id="vpn-create-protocol" onchange="vpnCreateProtocolChanged()" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
    + '<option value="">' + t('placeholder_select_protocol','Select protocol...') + '</option>'
    + '<option value="fortigate_ipsec">FortiGate IPsec (IKEv2)</option>'
    + '<option value="wireguard">WireGuard</option>'
    + '<option value="openvpn">OpenVPN</option>'
    + '<option value="azure">Azure P2S VPN</option>'
    + '</select>'
    + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_customer','Customer') + '</label>'
    + '<select id="vpn-create-customer" style="width:100%;padding:8px 12px;margin-bottom:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"><option value="">-- ' + t('lbl_no_customer','No customer') + ' --</option></select>'
    + '<div id="vpn-create-fields"></div>'
    + '<div style="display:flex;gap:8px;margin-top:16px;">'
    + '<button class="btn btn-primary" onclick="vpnDoCreate()" style="padding:8px 20px;font-size:13px;">' + t('btn_create','Create') + '</button>'
    + '<button class="btn btn-ghost" onclick="vpnLoadProfiles()" style="padding:8px 20px;font-size:13px;">' + t('btn_cancel','Cancel') + '</button>'
    + '</div></div>';
  _populateCustomerSelect('vpn-create-customer');
}

function vpnCreateProtocolChanged() {
  var protocol = document.getElementById('vpn-create-protocol').value;
  var el = document.getElementById('vpn-create-fields');
  var input = function(id, placeholder, type) {
    type = type || 'text';
    return '<input id="vpn-c-'+id+'" type="'+type+'" placeholder="'+placeholder+'" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">';
  };
  var label = function(text) { return '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;margin-top:8px;">'+text+'</label>'; };

  if (protocol === 'fortigate_ipsec') {
    el.innerHTML = label('FortiGate Gateway')
      + input('fg-host', 'Hostname / IP (f.eks. vpn.kunde.no)')
      + label('Brukernavn (EAP)')
      + input('fg-user', 'VPN-brukernavn')
      + label('Passord')
      + input('fg-pass', 'VPN-passord', 'password')
      + label('Pre-Shared Key (PSK)')
      + input('fg-psk', 'IKE PSK', 'password')
      + label(t('lbl_split_tunnel_routes','Split-tunnel routes (comma-separated, optional)'))
      + input('fg-routes', 'f.eks. 10.0.0.0/8, 172.16.0.0/12')
      + label(t('lbl_dns_servers_optional','DNS servers (optional)'))
      + input('fg-dns', 'f.eks. 10.0.0.1, 10.0.0.2');
  } else if (protocol === 'wireguard') {
    el.innerHTML = '<p style="color:var(--text-muted);font-size:13px;">' + t('msg_wireguard_recommend_import','For WireGuard we recommend using <strong>' + t('import_file') + '</strong> ' + t('with_a_conf_file') + '<br>Or fill in manually:') + '</p>'
      + label(t('lbl_private_key','Private key'))
      + input('wg-privkey', t('placeholder_base64_private_key','Base64-encoded private key'), 'password')
      + label(t('lbl_addresses_comma','Addresses (comma-separated)'))
      + input('wg-addr', 'f.eks. 10.0.0.2/32')
      + label('DNS')
      + input('wg-dns', 'f.eks. 1.1.1.1')
      + label('Peer Public Key')
      + input('wg-peer-pub', 'Base64-kodet peer public key')
      + label('Peer Endpoint')
      + input('wg-peer-ep', 'f.eks. vpn.server.no:51820')
      + label('Allowed IPs')
      + input('wg-peer-ips', 'f.eks. 0.0.0.0/0');
  } else if (protocol === 'openvpn') {
    el.innerHTML = '<p style="color:var(--text-muted);font-size:13px;">' + t('msg_openvpn_recommend_import','For OpenVPN we recommend using <strong>' + t('import_file') + '</strong> ' + t('with_an_ovpn_file') + '<br>Or enter connection details:') + '</p>'
      + label(t('lbl_username_optional','Username (optional)'))
      + input('ovpn-user', 'VPN-brukernavn')
      + label(t('lbl_password_optional','Password (optional)'))
      + input('ovpn-pass', 'VPN-passord', 'password')
      + label(t('lbl_config_paste_ovpn','Configuration (paste .ovpn content)'))
      + '<textarea id="vpn-c-ovpn-conf" placeholder="client\nremote vpn.server.no 1194\n..." style="width:100%;height:120px;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:12px;font-family:var(--mono);"></textarea>';
  } else if (protocol === 'azure') {
    el.innerHTML = '<p style="color:var(--text-muted);font-size:13px;">' + t('msg_azure_recommend_import','For Azure P2S we recommend using <strong>' + t('import_file') + '</strong> with VPN client XML from the Azure portal.') + '</p>'
      + label('Gateway FQDN')
      + input('az-gw', 'azuregateway-xxx.vpn.azure.com')
      + label('Tenant ID')
      + input('az-tenant', 'Entra ID tenant UUID')
      + label(t('lbl_client_id_optional','Client ID (optional)'))
      + input('az-client', t('lbl_default_azure_vpn_client','Default: Azure VPN client'));
  } else {
    el.innerHTML = '';
  }
}

async function vpnDoCreate() {
  var name = document.getElementById('vpn-create-name').value.trim();
  var protocol = document.getElementById('vpn-create-protocol').value;
  if (!name) { showToast(t('err_profile_name_required','Give the profile a name'),'error'); return; }
  if (!protocol) { showToast(t('err_protocol_required','Select a protocol'),'error'); return; }

  var config = {};
  var v = function(id) { var e = document.getElementById('vpn-c-'+id); return e ? e.value.trim() : ''; };

  if (protocol === 'fortigate_ipsec') {
    if (!v('fg-host') || !v('fg-user')) { showToast(t('err_host_user_required','Host and username are required'),'error'); return; }
    config = {
      host: v('fg-host'), username: v('fg-user'), password: v('fg-pass'), psk: v('fg-psk'),
      routes: v('fg-routes') ? v('fg-routes').split(',').map(function(s){return s.trim();}) : [],
      dns_servers: v('fg-dns') ? v('fg-dns').split(',').map(function(s){return s.trim();}) : [],
    };
  } else if (protocol === 'wireguard') {
    if (!v('wg-privkey') || !v('wg-peer-pub')) { showToast(t('err_wg_keys_required','Private key and peer public key are required'),'error'); return; }
    config = {
      private_key: v('wg-privkey'),
      addresses: v('wg-addr') ? v('wg-addr').split(',').map(function(s){return s.trim();}) : [],
      dns: v('wg-dns') ? v('wg-dns').split(',').map(function(s){return s.trim();}) : [],
      peers: [{public_key: v('wg-peer-pub'), endpoint: v('wg-peer-ep'), allowed_ips: v('wg-peer-ips') ? v('wg-peer-ips').split(',').map(function(s){return s.trim();}) : ['0.0.0.0/0']}],
    };
  } else if (protocol === 'openvpn') {
    var conf = document.getElementById('vpn-c-ovpn-conf');
    config = {config_content: conf ? conf.value : '', username: v('ovpn-user'), password: v('ovpn-pass')};
  } else if (protocol === 'azure') {
    config = {gateway_fqdn: v('az-gw'), tenant_id: v('az-tenant'), client_id: v('az-client') || '41b23e61-6c1e-4545-b367-cd054e0ed4b4'};
  }

  var vpnCustSel = document.getElementById('vpn-create-customer');
  var vpnCustId = vpnCustSel ? vpnCustSel.value : '';
  var createBody = {name:name, protocol:protocol, config:config};
  if (vpnCustId) createBody.customer_id = vpnCustId;
  var data = await apiFetch('/api/vpn/profiles', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(createBody)});
  if (data && data.ok) { showToast(t('msg_vpn_profile_created','VPN profile created'),'success'); vpnLoadProfiles(); }
}

async function vpnEditProfile(profileId) {
  var data = await apiFetch('/api/vpn/profiles/' + profileId);
  if (!data || !data.profile) return;
  var p = data.profile;
  var config = typeof p.config === 'string' ? JSON.parse(p.config) : p.config;

  var el = document.getElementById('vpn-content');
  var html = '<div style="max-width:500px;">'
    + '<h3 style="font-size:15px;font-weight:600;margin-bottom:16px;">' + t('rediger_vpn_profil') + '</h3>'
    + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('navn_2') + '</label>'
    + '<input id="vpn-edit-name" type="text" value="'+p.name+'" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
    + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('beskrivelse') + '</label>'
    + '<input id="vpn-edit-desc" type="text" value="'+(p.description||'')+'" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
    + '<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">' + t('protokoll') + ' <strong>'+p.protocol+'</strong></div>';

  // Protocol-specific fields
  if (p.protocol === 'fortigate_ipsec') {
    html += '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('host_2') + '</label>'
      + '<input id="vpn-edit-host" type="text" value="'+(config.host||'')+'" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
      + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_username','Username') + '</label>'
      + '<input id="vpn-edit-user" type="text" value="'+(config.username||'')+'" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
      + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_password_leave_blank','Password (leave blank to keep)') + '</label>'
      + '<input id="vpn-edit-pass" type="password" placeholder="' + t('placeholder_unchanged','Unchanged') + '" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
      + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_psk_leave_blank','PSK (leave blank to keep)') + '</label>'
      + '<input id="vpn-edit-psk" type="password" placeholder="' + t('placeholder_unchanged','Unchanged') + '" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
      + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_split_tunnel_routes_short','Split-tunnel routes') + '</label>'
      + '<input id="vpn-edit-routes" type="text" value="'+(config.routes||[]).join(', ')+'" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
      + '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">' + t('lbl_dns_servers','DNS servers') + '</label>'
      + '<input id="vpn-edit-dns" type="text" value="'+(config.dns_servers||[]).join(', ')+'" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">';
  }

  html += '<label style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;margin-top:8px;">' + t('lbl_customer','Customer') + '</label>'
    + '<select id="vpn-edit-customer" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"><option value="">-- ' + t('lbl_no_customer','No customer') + ' --</option></select>';

  html += '<div style="display:flex;gap:8px;margin-top:16px;">'
    + '<button class="btn btn-primary" onclick="vpnDoEdit(\''+profileId+'\',\''+p.protocol+'\')" style="padding:8px 20px;font-size:13px;">' + t('lagre_3') + '</button>'
    + '<button class="btn btn-ghost" onclick="vpnLoadProfiles()" style="padding:8px 20px;font-size:13px;">' + t('avbryt_3') + '</button>'
    + '</div></div>';
  el.innerHTML = html;
  _populateCustomerSelect('vpn-edit-customer', p.customer_id);
}

async function vpnDoEdit(profileId, protocol) {
  var body = {
    name: document.getElementById('vpn-edit-name').value.trim(),
    description: document.getElementById('vpn-edit-desc').value.trim(),
    customer_id: document.getElementById('vpn-edit-customer').value || null,
  };

  if (protocol === 'fortigate_ipsec') {
    var config = {
      host: document.getElementById('vpn-edit-host').value.trim(),
      username: document.getElementById('vpn-edit-user').value.trim(),
      routes: document.getElementById('vpn-edit-routes').value.split(',').map(function(s){return s.trim();}).filter(Boolean),
      dns_servers: document.getElementById('vpn-edit-dns').value.split(',').map(function(s){return s.trim();}).filter(Boolean),
    };
    var pass = document.getElementById('vpn-edit-pass').value;
    var psk = document.getElementById('vpn-edit-psk').value;
    if (pass) config.password = pass;
    if (psk) config.psk = psk;
    body.config = config;
  }

  var data = await apiFetch('/api/vpn/profiles/' + profileId, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if (data && data.ok) { showToast(t('msg_profile_updated','Profile updated'),'success'); vpnLoadProfiles(); }
}

function vpnShowImport() {
  var el = document.getElementById('vpn-content');
  el.innerHTML = '<div style="max-width:500px;">'
    + '<h3 style="font-size:15px;font-weight:600;margin-bottom:12px;">' + t('hdr_import_vpn_profile','Import VPN profile') + '</h3>'
    + '<input id="vpn-import-name" type="text" placeholder="' + t('placeholder_profile_name','Profile name') + '" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;">'
    + '<div id="vpn-drop-zone" style="border:2px dashed var(--border);border-radius:8px;padding:32px;text-align:center;cursor:pointer;margin-bottom:12px;transition:border-color 0.2s;" onclick="document.getElementById(\'vpn-file-input\').click()" ondragover="event.preventDefault();this.style.borderColor=\'var(--blue)\'" ondragleave="this.style.borderColor=\'var(--border)\'" ondrop="event.preventDefault();this.style.borderColor=\'var(--border)\';vpnHandleFiles(event.dataTransfer.files)">'
    + '<div style="font-size:24px;margin-bottom:8px;">📁</div>'
    + '<div style="color:var(--text-muted);font-size:13px;">' + t('msg_drag_drop_vpn','Drag and drop a') + ' <strong>.conf</strong>, <strong>.ovpn</strong>, ' + t('lbl_or','or') + ' <strong>.xml</strong> ' + t('msg_file_here','file here') + '</div>'
    + '<div style="color:var(--text-dim);font-size:12px;margin-top:4px;">' + t('msg_azure_vpn_select_both','Azure VPN: select <strong>both</strong> XML files (azurevpnconfig.xml + VpnSettings.xml)') + '</div>'
    + '<div style="color:var(--text-dim);font-size:12px;">' + t('msg_or_click_to_select','or click to select file(s)') + '</div>'
    + '</div>'
    + '<input id="vpn-file-input" type="file" accept=".conf,.ovpn,.xml,.toml" multiple style="display:none;" onchange="vpnHandleFiles(this.files)">'
    + '<div id="vpn-file-info" style="display:none;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:10px 12px;margin-bottom:12px;font-size:12px;">'
    + '<div style="display:flex;justify-content:space-between;align-items:center;"><span id="vpn-file-name" style="font-weight:600;"></span><button class="btn btn-ghost" onclick="vpnClearFile()" style="padding:2px 8px;font-size:11px;color:var(--red);">' + t('btn_remove','Remove') + '</button></div>'
    + '<div id="vpn-file-type" style="color:var(--text-muted);margin-top:4px;"></div>'
    + '</div>'
    + '<input id="vpn-import-content" type="hidden">'
    + '<button class="btn btn-primary" onclick="vpnDoImport()" id="vpn-import-btn" disabled style="padding:8px 20px;font-size:13px;">' + t('btn_import','Import') + '</button>'
    + '</div>';
}

var _vpnImportFiles = {};

function vpnHandleFiles(files) {
  if (!files || !files.length) return;
  _vpnImportFiles = {};
  var pending = files.length;

  for (var i = 0; i < files.length; i++) {
    (function(file) {
      var reader = new FileReader();
      reader.onload = function(e) {
        var content = e.target.result;
        // Detect which file this is
        if (content.indexOf('<AzVpnProfile>') !== -1 || content.indexOf('<audience>') !== -1 || content.indexOf('<serversecret>') !== -1) {
          _vpnImportFiles.azure_xml = content;
          _vpnImportFiles.azure_xml_name = file.name;
        } else if (content.indexOf('<VpnSettings>') !== -1 || content.indexOf('<VpnServer>') !== -1 || content.indexOf('<CustomDnsServers>') !== -1) {
          _vpnImportFiles.vpn_settings_xml = content;
          _vpnImportFiles.vpn_settings_name = file.name;
        } else if (file.name.endsWith('.conf') || content.indexOf('[Interface]') !== -1) {
          _vpnImportFiles.main = content;
          _vpnImportFiles.type = 'wireguard';
        } else if (file.name.endsWith('.ovpn') || content.indexOf('remote ') !== -1) {
          _vpnImportFiles.main = content;
          _vpnImportFiles.type = 'openvpn';
        } else {
          // Unknown XML — could be either
          _vpnImportFiles.main = content;
          _vpnImportFiles.type = 'auto';
        }

        pending--;
        if (pending === 0) vpnShowFileInfo(files);
      };
      reader.readAsText(file);
    })(files[i]);
  }
}

function vpnShowFileInfo(files) {
  document.getElementById('vpn-file-info').style.display = 'block';
  document.getElementById('vpn-drop-zone').style.display = 'none';

  var names = [];
  for (var i = 0; i < files.length; i++) names.push(files[i].name);
  document.getElementById('vpn-file-name').textContent = names.join(' + ');

  var type = t('lbl_unknown','Unknown');
  if (_vpnImportFiles.azure_xml) {
    type = 'Azure VPN' + (_vpnImportFiles.vpn_settings_xml ? ' (2 ' + t('lbl_files','files') + ' — ' + t('lbl_complete','complete') + ')' : ' (' + t('msg_missing_vpnsettings','missing VpnSettings.xml!') + ')');
  } else if (_vpnImportFiles.type === 'wireguard') type = 'WireGuard (.conf)';
  else if (_vpnImportFiles.type === 'openvpn') type = 'OpenVPN (.ovpn)';

  document.getElementById('vpn-file-type').textContent = 'Type: ' + type;
  document.getElementById('vpn-import-btn').disabled = false;

  // Combine content for import
  if (_vpnImportFiles.azure_xml) {
    // Merge both XMLs with separator
    var combined = _vpnImportFiles.azure_xml;
    if (_vpnImportFiles.vpn_settings_xml) {
      combined += '\n<!-- VPN_SETTINGS_SEPARATOR -->\n' + _vpnImportFiles.vpn_settings_xml;
    }
    document.getElementById('vpn-import-content').value = combined;
  } else {
    document.getElementById('vpn-import-content').value = _vpnImportFiles.main || '';
  }

  // Auto-fill name
  var nameInput = document.getElementById('vpn-import-name');
  if (!nameInput.value) {
    nameInput.value = (files[0].name || '').replace(/\.(conf|ovpn|xml|toml)$/i, '').replace(/azurevpnconfig/i, 'Azure VPN');
  }
}

function vpnClearFile() {
  document.getElementById('vpn-import-content').value = '';
  document.getElementById('vpn-file-info').style.display = 'none';
  document.getElementById('vpn-drop-zone').style.display = 'block';
  document.getElementById('vpn-import-btn').disabled = true;
  document.getElementById('vpn-file-input').value = '';
}

async function vpnDoImport() {
  var name = document.getElementById('vpn-import-name').value.trim();
  var content = document.getElementById('vpn-import-content').value;
  if (!name || !content) { showToast(t('err_select_file_and_name','Select a file and name the profile'),'error'); return; }
  var data = await apiFetch('/api/vpn/profiles/import', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,file_content:content})});
  if (data && data.ok) { showToast(t('msg_profile_imported','Profile imported:') + ' '+data.profile.protocol,'success'); vpnLoadProfiles(); }
}

// ═══════════════════════════════════════════════════════════════════
// LIVE DASHBOARD
// ═══════════════════════════════════════════════════════════════════

var _liveWs = null;

async function livePollNow() {
  var statusEl = document.getElementById('live-status') || document.getElementById('fg-live-status');
  if (statusEl) statusEl.textContent = t('msg_updating','Updating...');
  var status = await apiFetch('/api/status');
  var custId = status && status.active_id;
  if (!custId) { showToast(t('msg_select_customer_first','Select a customer first'),'error'); return; }
  var data = await apiFetch('/api/dashboard/poll/'+custId, {method:'POST'});
  if (data) liveRenderDevices(data.devices || []);
  if (statusEl) statusEl.textContent = t('msg_last_updated','Last updated') + ': ' + new Date().toLocaleTimeString();
}

async function fgBackupAll() {
  showToast(t('msg_backing_up_all','Kjører backup på alle FortiGates...'), 'info', 3000);
  var data = await apiFetch('/api/fortigate/backup-all', {method:'POST'});
  if (data) {
    showToast(data.success + '/' + data.total + ' ' + t('msg_backup_complete') + (data.failed ? ', ' + data.failed + ' ' + t('msg_backup_failed') : ''), data.failed ? 'warning' : 'success', 5000);
  } else {
    showToast(t('status_error'), 'error');
  }
}

async function fgPollAll() {
  var statusEl = document.getElementById('fg-live-status');
  if (statusEl) statusEl.textContent = t('msg_updating','Updating...');
  // Poll all customers that have FortiGate and merge live data into the FortiGate view
  var data = await apiFetch('/api/fortigate/all');
  if (data && data.fortigates) {
    // Trigger live poll for each FortiGate customer
    var pollPromises = [];
    var seenCids = {};
    for (var i = 0; i < data.fortigates.length; i++) {
      var cid = data.fortigates[i].customer_id;
      if (cid && !seenCids[cid]) {
        seenCids[cid] = true;
        pollPromises.push(apiFetch('/api/dashboard/poll/'+cid, {method:'POST'}).catch(function(){return null;}));
      }
    }
    await Promise.all(pollPromises);
    // Reload the FortiGate view with fresh data — but only if no detail panel is open
    if (!document.querySelector('.fg-detail-panel')) {
      dashLoadFortiGates();
    }
  }
  if (statusEl) statusEl.textContent = t('msg_last_updated','Sist oppdatert') + ': ' + new Date().toLocaleTimeString();
}

function liveSetInterval(seconds) {
  if (_liveWs && _liveWs.readyState === WebSocket.OPEN) {
    _liveWs.send(JSON.stringify({type:'set_interval',interval:parseInt(seconds)}));
  }
}

var _liveDevices = [];

function liveRenderDevices(devices) {
  _liveDevices = devices;
  var el = document.getElementById('live-devices');
  if (!devices.length) { el.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:48px;grid-column:1/-1;">' + t('ingen_enheter_funnet') + '</div>'; return; }
  var html = '';
  devices.forEach(function(d, idx) {
    var color = d.status === 'online' ? 'var(--green)' : d.status === 'error' ? 'var(--red)' : 'var(--text-dim)';
    var vendorIcon = d.vendor === 'fortigate' ? '🛡' : '📡';
    html += '<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:16px;border-left:3px solid '+color+';cursor:pointer;transition:background 0.15s;" onmouseover="this.style.background=\'var(--bg)\'" onmouseout="this.style.background=\'\'" onclick="liveShowDeviceDetail('+idx+')">';
    html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">';
    html += '<strong>'+vendorIcon+' '+d.name+'</strong>';
    html += '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:'+color+';"></span>';
    html += '</div>';
    html += '<div style="font-size:12px;color:var(--text-muted);display:grid;grid-template-columns:1fr 1fr;gap:4px;">';
    html += '<span>' + t('modell') + ' <strong style="color:var(--text);">'+(d.model||'-')+'</strong></span>';
    html += '<span>Firmware: '+(d.firmware||'-')+'</span>';
    if (d.wan_ip) html += '<span>' + t('wan') + ' <strong style="color:var(--text);">'+d.wan_ip+'</strong></span>';
    if (d.uptime) html += '<span>Uptime: '+d.uptime+'</span>';
    if (d.cpu_pct !== undefined && d.cpu_pct !== null) {
      var cpuColor = d.cpu_pct > 80 ? 'var(--red)' : d.cpu_pct > 50 ? 'var(--orange)' : 'var(--green)';
      html += '<span>' + t('cpu') + ' <span style="color:'+cpuColor+';font-weight:600;">'+d.cpu_pct+'%</span></span>';
    }
    if (d.mem_pct !== undefined && d.mem_pct !== null) {
      var memColor = d.mem_pct > 80 ? 'var(--red)' : d.mem_pct > 50 ? 'var(--orange)' : 'var(--green)';
      html += '<span>' + t('minne') + ' <span style="color:'+memColor+';font-weight:600;">'+d.mem_pct+'%</span></span>';
    }
    if (d.sessions !== undefined && d.sessions !== null) html += '<span>Sesjoner: '+d.sessions.toLocaleString()+'</span>';
    if (d.vpn_tunnels !== undefined && d.vpn_tunnels !== null) html += '<span>VPN: '+d.vpn_tunnels+' tunnel(er)</span>';
    if (d.ha_mode && d.ha_mode !== 'Standalone') html += '<span>HA: '+d.ha_mode+'</span>';
    if (d.clients !== undefined && d.clients !== null) html += '<span>Klienter: '+d.clients+'</span>';
    html += '</div>';
    if (d.error) html += '<div style="color:var(--red);font-size:11px;margin-top:6px;">'+d.error+'</div>';
    if (d.last_poll) html += '<div style="font-size:10px;color:var(--text-dim);margin-top:6px;">' + t('msg_last_polled','Last polled') + ': '+new Date(d.last_poll).toLocaleTimeString()+'</div>';
    html += '</div>';
  });
  el.innerHTML = html;
}

function liveShowDeviceDetail(idx) {
  var d = _liveDevices[idx];
  if (!d) return;
  var el = document.getElementById('live-devices');
  var color = d.status === 'online' ? 'var(--green)' : 'var(--red)';
  var vendorIcon = d.vendor === 'fortigate' ? '🛡' : '📡';

  var html = '<div style="grid-column:1/-1;max-width:700px;">';
  html += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">';
  html += '<button class="btn btn-ghost" onclick="livePollNow()" style="padding:4px 10px;font-size:12px;">' + t('tilbake') + '</button>';
  html += '<h3 style="font-size:16px;font-weight:700;margin:0;">'+vendorIcon+' '+d.name+'</h3>';
  html += '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:'+color+';"></span>';
  html += '</div>';

  // KPI cards
  var cards = [];
  if (d.cpu_pct !== undefined && d.cpu_pct !== null) cards.push({label:'CPU', value:d.cpu_pct+'%', color: d.cpu_pct>80?'var(--red)':d.cpu_pct>50?'var(--orange)':'var(--green)'});
  if (d.mem_pct !== undefined && d.mem_pct !== null) cards.push({label:'Minne', value:d.mem_pct+'%', color: d.mem_pct>80?'var(--red)':d.mem_pct>50?'var(--orange)':'var(--green)'});
  if (d.sessions !== undefined && d.sessions !== null) cards.push({label:'Sesjoner', value:d.sessions.toLocaleString(), color:'var(--blue)'});
  if (d.vpn_tunnels !== undefined && d.vpn_tunnels !== null) cards.push({label:'VPN-tunneler', value:d.vpn_tunnels, color:'var(--purple)'});
  if (d.clients !== undefined && d.clients !== null) cards.push({label:'Klienter', value:d.clients, color:'var(--green)'});

  if (cards.length) {
    html += '<div style="display:grid;grid-template-columns:repeat('+Math.min(cards.length,5)+',1fr);gap:10px;margin-bottom:16px;">';
    cards.forEach(function(c) {
      html += '<div class="card" style="padding:12px;text-align:center;border-top:2px solid '+c.color+';">';
      html += '<div style="font-size:22px;font-weight:700;">'+c.value+'</div>';
      html += '<div style="font-size:11px;color:var(--text-muted);">'+c.label+'</div>';
      html += '</div>';
    });
    html += '</div>';
  }

  // Detail table
  html += '<div class="card" style="padding:16px;">';
  html += '<table style="width:100%;font-size:13px;">';
  var rows = [
    ['Status', '<span style="color:'+color+';font-weight:600;">'+(d.status==='online'?'ONLINE':'OFFLINE')+'</span>'],
    ['Modell', d.model || '-'],
    ['Firmware', d.firmware || '-'],
    ['Serienummer', d.serial || '-'],
    ['WAN IP', d.wan_ip || '-'],
    ['Uptime', d.uptime || '-'],
  ];
  if (d.ha_mode) rows.push(['HA-modus', d.ha_mode]);
  if (d.extra) {
    if (d.extra.policy_count) rows.push(['Brannmurregler', d.extra.policy_count]);
    if (d.extra.host) rows.push(['API-host', d.extra.host + ':' + (d.extra.port||443)]);
  }
  if (d.last_poll) rows.push([t('msg_last_polled','Last polled'), new Date(d.last_poll).toLocaleString('no-NO')]);

  rows.forEach(function(r) {
    html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:8px;color:var(--text-muted);width:150px;">'+r[0]+'</td><td style="padding:8px;">'+r[1]+'</td></tr>';
  });
  html += '</table></div>';

  // Extra data sections for FortiGate
  if (d.vendor === 'fortigate' && d.extra) {
    var ex = d.extra;

    // Interfaces
    if (ex.interfaces && ex.interfaces.length) {
      html += '<div class="card" style="padding:16px;margin-top:12px;">';
      html += '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">Grensesnitt ('+ex.interfaces.length+')</div>';
      html += '<table style="width:100%;font-size:12px;border-collapse:collapse;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:4px;">' + t('navn_2') + '</th><th>IP</th><th>' + t('link') + '</th><th>' + t('hastighet') + '</th></tr></thead><tbody>';
      ex.interfaces.forEach(function(i) {
        if (!i.ip || i.ip === '0.0.0.0') return;
        html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px;font-weight:600;">'+i.name+'</td><td style="padding:4px;font-family:var(--mono);font-size:11px;">'+i.ip+'</td><td style="padding:4px;">'+(i.link?'<span style="color:var(--green);">' + t('up') + '</span>':'<span style="color:var(--red);">' + t('down') + '</span>')+'</td><td style="padding:4px;">'+(i.speed?i.speed+'M':'')+'</td></tr>';
      });
      html += '</tbody></table></div>';
    }

    // VPN tunnels
    if (ex.vpn_tunnels && ex.vpn_tunnels.length) {
      html += '<div class="card" style="padding:16px;margin-top:12px;">';
      html += '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">VPN-tunneler ('+ex.vpn_tunnels.length+')</div>';
      ex.vpn_tunnels.forEach(function(v) {
        html += '<div style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px;border-bottom:1px solid var(--border);">';
        html += '<strong>'+v.name+'</strong>';
        html += '<span style="color:var(--text-muted);">→ '+v.remote_gw+'</span>';
        html += '</div>';
      });
      html += '</div>';
    }

    // Policies
    if (ex.policies && ex.policies.length) {
      html += '<div class="card" style="padding:16px;margin-top:12px;">';
      html += '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">' + t('lbl_firewall_rules','Firewall rules') + ' ('+ex.policies.length+')</div>';
      html += '<table style="width:100%;font-size:11px;border-collapse:collapse;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:4px;">#</th><th style="text-align:left;padding:4px;">' + t('lbl_name','Name') + '</th><th>' + t('lbl_source','Source') + '</th><th>' + t('lbl_destination','Destination') + '</th><th>' + t('lbl_service','Service') + '</th><th>' + t('lbl_log','Log') + '</th></tr></thead><tbody>';
      ex.policies.forEach(function(p) {
        html += '<tr style="border-bottom:1px solid var(--border);">';
        html += '<td style="padding:4px;">'+p.id+'</td>';
        html += '<td style="padding:4px;font-weight:600;">'+p.name+'</td>';
        html += '<td style="padding:4px;font-size:10px;">'+p.src+'</td>';
        html += '<td style="padding:4px;font-size:10px;">'+p.dst+'</td>';
        html += '<td style="padding:4px;font-size:10px;">'+p.svc+'</td>';
        html += '<td style="padding:4px;font-size:10px;">'+(p.log==='all'||p.log==='utm'?'<span style="color:var(--green);">'+p.log+'</span>':'<span style="color:var(--red);">'+p.log+'</span>')+'</td>';
        html += '</tr>';
      });
      html += '</tbody></table></div>';
    }

    // DHCP + DNS + Admins row
    html += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:12px;">';

    // DHCP
    if (ex.dhcp && ex.dhcp.length) {
      html += '<div class="card" style="padding:12px;"><div style="font-size:12px;font-weight:600;margin-bottom:6px;">DHCP ('+ex.dhcp.length+')</div>';
      ex.dhcp.forEach(function(d2) { html += '<div style="font-size:11px;color:var(--text-muted);padding:2px 0;"><strong>'+d2.interface+'</strong>: '+d2.range+'</div>'; });
      html += '</div>';
    }

    // DNS
    if (ex.dns && ex.dns.primary) {
      html += '<div class="card" style="padding:12px;"><div style="font-size:12px;font-weight:600;margin-bottom:6px;">DNS</div>';
      html += '<div style="font-size:11px;color:var(--text-muted);">' + t('lbl_primary','Primary') + ': <strong>'+ex.dns.primary+'</strong></div>';
      if (ex.dns.secondary) html += '<div style="font-size:11px;color:var(--text-muted);">' + t('lbl_secondary','Secondary') + ': '+ex.dns.secondary+'</div>';
      html += '</div>';
    }

    // Admins
    if (ex.admins && ex.admins.length) {
      html += '<div class="card" style="padding:12px;"><div style="font-size:12px;font-weight:600;margin-bottom:6px;">Admin-kontoer ('+ex.admins.length+')</div>';
      ex.admins.forEach(function(a) {
        var warns = [];
        if (!a.two_factor) warns.push('<span style="color:var(--orange);">' + t('ingen_fa') + '</span>');
        if (!a.trusthost) warns.push('<span style="color:var(--orange);">' + t('ingen_trusthost') + '</span>');
        html += '<div style="font-size:11px;padding:2px 0;"><strong>'+a.name+'</strong> ('+a.profile+') '+(warns.length?warns.join(', '):'<span style="color:var(--green);">OK</span>')+'</div>';
      });
      html += '</div>';
    }

    html += '</div>';
  }

  // Action buttons
  if (d.vendor === 'fortigate') {
    html += '<div style="display:flex;gap:8px;margin-top:12px;">';
    html += '<button class="btn btn-primary" onclick="fgBackupConfig(\''+d.customer_id+'\')" style="padding:6px 14px;font-size:12px;">' + t('backup_config') + '</button>';
    html += '<button class="btn btn-ghost" onclick="fgShowBackups(\''+d.customer_id+'\')" style="padding:6px 14px;font-size:12px;">'+t('btn_backup_history','Backup-historikk')+'</button>';
    html += '<button class="btn btn-ghost" onclick="fgComplianceCheck(\''+d.customer_id+'\')" style="padding:6px 14px;font-size:12px;">' + t('cis_sjekk') + '</button>';
    html += '</div>';
    html += '<div id="fg-backup-list-'+d.customer_id+'" style="margin-top:8px;"></div>';
  }

  html += '</div>';
  el.innerHTML = html;
}

async function fgBackupConfig(customerId) {
  showToast(t('msg_backing_up_fortigate','Backing up FortiGate config...'), 'info', 3000);
  var data = await apiFetch('/api/fortigate/backup/' + customerId, {method:'POST'});
  if (data && data.ok) {
    showToast(t('msg_backup_completed','Backup completed:') + ' ' + (data.filename||''), 'success');
    fgShowBackups(customerId); // Refresh list
  } else {
    showToast(t('err_backup_failed','Backup failed:') + ' ' + (data&&data.error||t('lbl_unknown_error','unknown error')), 'error');
  }
}

async function fgShowBackups(customerId) {
  var el = document.getElementById('fg-backup-list-' + customerId);
  if (!el) return;
  // Toggle — if already showing, hide
  if (el.innerHTML && el.dataset.loaded) { el.innerHTML = ''; el.dataset.loaded = ''; return; }
  el.innerHTML = '<div class="loader" style="width:14px;height:14px;display:inline-block;"></div>';
  var data = await apiFetch('/api/fortigate/backups/' + customerId);
  if (!data || !data.length) { el.innerHTML = '<div style="font-size:11px;color:var(--text-muted);padding:4px 0;">'+t('msg_no_backups','Ingen backuper funnet')+'</div>'; el.dataset.loaded = '1'; return; }
  var h = '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:4px;">';
  h += '<thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:4px 6px;">'+t('col_filename','Fil')+'</th><th style="text-align:center;padding:4px 6px;">'+t('col_size','Størrelse')+'</th><th style="text-align:center;padding:4px 6px;">'+t('col_date','Dato')+'</th><th style="padding:4px 6px;"></th></tr></thead><tbody>';
  data.forEach(function(b) {
    h += '<tr style="border-bottom:1px solid var(--border);">';
    h += '<td style="padding:3px 6px;font-family:var(--mono);font-size:10px;">'+esc(b.filename)+'</td>';
    h += '<td style="padding:3px 6px;text-align:center;">'+((b.size/1024).toFixed(1))+' KB</td>';
    h += '<td style="padding:3px 6px;text-align:center;">'+esc((b.modified||'').substring(0,16))+'</td>';
    h += '<td style="padding:3px 6px;text-align:right;"><button class="btn btn-ghost" onclick="fgDownloadBackup(\''+customerId+'\',\''+esc(b.filename)+'\')" style="padding:2px 8px;font-size:10px;">'+t('btn_download','Last ned')+'</button></td>';
    h += '</tr>';
  });
  h += '</tbody></table>';
  el.innerHTML = h;
  el.dataset.loaded = '1';
}

async function fgDownloadBackup(customerId, filename) {
  var data = await apiFetch('/api/fortigate/backup/' + customerId + '/' + encodeURIComponent(filename));
  if (!data || !data.content) { showToast(t('err_download_failed','Nedlasting feilet'), 'error'); return; }
  var blob = new Blob([data.content], {type: 'text/plain'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function fgComplianceCheck(customerId) {
  // Find or create a results area in the detail view
  var existing = document.getElementById('fg-compliance-results');
  if (!existing) {
    var container = document.querySelector('#live-devices > div');
    if (container) {
      container.insertAdjacentHTML('beforeend', '<div id="fg-compliance-results" style="margin-top:12px;"></div>');
    }
  }
  var el = document.getElementById('fg-compliance-results');
  if (el) el.innerHTML = '<div class="card" style="padding:16px;"><div class="loader" style="width:16px;height:16px;display:inline-block;"></div> ' + t('msg_running_cis_check','Running CIS compliance check...') + '</div>';

  var data = await apiFetch('/api/fortigate/compliance/' + customerId);
  if (!data || !el) { showToast(t('err_check_failed','Check failed'), 'error'); return; }

  var findings = data.findings || [];
  var score = data.score || 0;
  var scoreColor = score >= 80 ? 'var(--green)' : score >= 50 ? 'var(--orange)' : 'var(--red)';

  var html = '<div class="card" style="padding:16px;">';
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">';
  html += '<div style="font-size:13px;font-weight:600;">' + t('cis_compliance') + '</div>';
  html += '<div style="font-size:20px;font-weight:700;color:'+scoreColor+';">'+score+'%</div>';
  html += '</div>';

  // Progress bar
  html += '<div style="background:var(--border);border-radius:4px;height:8px;margin-bottom:16px;overflow:hidden;">';
  html += '<div style="background:'+scoreColor+';height:100%;width:'+score+'%;border-radius:4px;transition:width 0.5s;"></div>';
  html += '</div>';

  if (findings.length) {
    html += '<table style="width:100%;font-size:12px;border-collapse:collapse;">';
    html += '<thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:6px;">' + t('kontroll') + '</th><th style="text-align:center;padding:6px;">' + t('status_3') + '</th><th style="text-align:left;padding:6px;">' + t('detaljer') + '</th></tr></thead><tbody>';
    findings.forEach(function(f) {
      var icon = f.status === 'pass' ? '<span style="color:var(--green);">&#10003;</span>' : f.status === 'fail' ? '<span style="color:var(--red);">&#10007;</span>' : '<span style="color:var(--orange);">&#9888;</span>';
      var rowBg = f.status === 'fail' ? 'background:rgba(248,81,73,0.05);' : '';
      html += '<tr style="border-bottom:1px solid var(--border);'+rowBg+'">';
      html += '<td style="padding:6px;font-weight:600;">'+f.title+'</td>';
      html += '<td style="padding:6px;text-align:center;">'+icon+'</td>';
      html += '<td style="padding:6px;color:var(--text-muted);font-size:11px;">'+(f.detail||f.description||'')+'</td>';
      html += '</tr>';
    });
    html += '</tbody></table>';
  } else {
    html += '<div style="color:var(--text-muted);">' + t('ingen_funn') + '</div>';
  }

  html += '</div>';
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════
// AI CONSOLE
// ═══════════════════════════════════════════════════════════════════

var _aiConversationId = null;

function aiQuickPrompt(text) {
  document.getElementById('ai-input').value = text;
  aiSend();
}

var _aiCustomerList = [];

async function aiLoadCustomers() {
  var data = await apiFetch('/api/customers');
  if (!data) return;
  _aiCustomerList = (data.customers || []).map(function(c) {
    return {id: c._id, name: c.CustomerName || '', domain: c.PrimaryDomain || ''};
  });
  // Populate native select
  var sel = document.getElementById('ai-customer-select');
  if (sel) {
    var html = '<option value="all">' + t('lbl_all_customers','All Customers') + '</option>';
    _aiCustomerList.forEach(function(c) {
      html += '<option value="' + esc(c.id) + '">' + esc(c.name) + (c.domain ? ' (' + esc(c.domain) + ')' : '') + '</option>';
    });
    sel.innerHTML = html;
  }
}

function aiSelectCustomerFromDropdown(sel) {
  var id = sel.value;
  var name = sel.options[sel.selectedIndex].textContent;
  document.getElementById('ai-customer').value = id;
}

function aiCustomerFilter(query) {
  var list = document.getElementById('ai-customer-list');
  var q = (query || '').toLowerCase();
  var html = '<div onclick="aiSelectCustomer(\'all\',\'' + t('lbl_all_customers','All customers') + '\')" style="padding:8px 12px;cursor:pointer;font-size:12px;font-weight:600;border-bottom:1px solid var(--border);" onmouseover="this.style.background=\'var(--bg)\'" onmouseout="this.style.background=\'\'">' + t('lbl_all_customers','All customers') + '</div>';
  var count = 0;
  _aiCustomerList.forEach(function(c) {
    if (q && c.name.toLowerCase().indexOf(q) === -1 && c.domain.toLowerCase().indexOf(q) === -1) return;
    if (count >= 20) return;
    count++;
    html += '<div onclick="aiSelectCustomer(\''+c.id+'\',\''+c.name.replace(/'/g,"\\'")+'\')" style="padding:6px 12px;cursor:pointer;font-size:12px;border-bottom:1px solid var(--border);" onmouseover="this.style.background=\'var(--bg)\'" onmouseout="this.style.background=\'\'">';
    html += '<div style="font-weight:600;">'+c.name+'</div>';
    if (c.domain) html += '<div style="font-size:10px;color:var(--text-muted);">'+c.domain+'</div>';
    html += '</div>';
  });
  if (count === 0 && q) html += '<div style="padding:8px 12px;font-size:12px;color:var(--text-muted);">' + t('ingen_treff') + '</div>';
  list.innerHTML = html;
  list.style.display = 'block';
}

function aiSelectCustomer(id, name) {
  document.getElementById('ai-customer').value = id;
  document.getElementById('ai-customer-search').value = id === 'all' ? '' : name;
  document.getElementById('ai-customer-list').style.display = 'none';
}

async function aiSend() {
  var input = document.getElementById('ai-input');
  var msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  var msgsEl = document.getElementById('ai-messages');

  // Clear welcome screen on first message only
  var welcomeEl = msgsEl.querySelector('[data-welcome]');
  if (welcomeEl) welcomeEl.remove();

  // Unique ID for this reply
  var replyId = 'ai-reply-' + Date.now();

  // Timestamp
  var now = new Date().toLocaleTimeString('no-NO', {hour:'2-digit',minute:'2-digit'});

  // Add user message at bottom
  var userDiv = document.createElement('div');
  userDiv.style.cssText = 'margin-bottom:16px;padding:10px 12px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;border-left:3px solid var(--blue);';
  userDiv.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;"><span style="font-weight:600;color:var(--blue);font-size:12px;">' + t('lbl_you','You') + '</span><span style="font-size:10px;color:var(--text-dim);">'+now+'</span></div><div style="font-size:13px;">'+msg.replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</div>';
  msgsEl.appendChild(userDiv);
  msgsEl.scrollTop = msgsEl.scrollHeight;

  // Add placeholder for assistant at bottom
  var aiDiv = document.createElement('div');
  aiDiv.style.cssText = 'margin-bottom:16px;padding:10px 12px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;border-left:3px solid var(--green);';
  aiDiv.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;"><span style="font-weight:600;color:var(--green);font-size:12px;"><img src="/static/sybrt-mascot.png" style="width:16px;height:16px;border-radius:50%;vertical-align:middle;margin-right:3px;">Sybrt</span><span id="'+replyId+'-time" style="font-size:10px;color:var(--text-dim);"></span></div><div id="'+replyId+'-text" style="white-space:pre-wrap;font-size:13px;"><span class="loader" style="width:14px;height:14px;display:inline-block;"></span></div>';
  msgsEl.appendChild(aiDiv);
  msgsEl.scrollTop = msgsEl.scrollHeight;

  // Get context
  var custId = document.getElementById('ai-customer').value;
  if (!custId) {
    var status = await apiFetch('/api/status');
    custId = status && status.active_id;
  }
  var focus = document.getElementById('ai-focus').value;
  try {
    var resp = await fetch('/api/claude/message', {
      method: 'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+_authToken},
      body: JSON.stringify({message:msg, conversation_id:_aiConversationId, customer_id:custId||'', focus:focus||'general'})
    });
    if (!resp.ok) { try { var e = await resp.json(); document.getElementById(replyId+'-text').textContent = t('status_error','Error')+': '+e.error; } catch(_) { document.getElementById(replyId+'-text').textContent = t('err_http_error','Error: HTTP') + ' '+resp.status; } return; }
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var replyEl = document.getElementById(replyId+'-text');
    replyEl.textContent = '';
    var buf = '';
    while (true) {
      var result = await reader.read();
      if (result.done) break;
      buf += decoder.decode(result.value, {stream:true});
      var lines = buf.split('\n');
      buf = lines.pop();
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        if (!line.startsWith('data: ')) continue;
        try {
          var evt = JSON.parse(line.slice(6));
          if (evt.type === 'text') replyEl.textContent += (evt.text || evt.content || '');
          else if (evt.type === 'tool_use') replyEl.innerHTML += '<div style="color:var(--orange);font-size:11px;margin:4px 0;">🔧 '+(evt.tool_name||evt.tool||'?')+'</div>';
          else if (evt.type === 'conversation_id') _aiConversationId = evt.conversation_id || evt.id;
          else if (evt.type === 'done') { var ts=document.getElementById(replyId+'-time'); if(ts) ts.textContent=new Date().toLocaleTimeString('no-NO',{hour:'2-digit',minute:'2-digit'}); }
          else if (evt.type === 'error') replyEl.innerHTML += '<div style="color:var(--red);">' + t('status_error','Error') + ': '+evt.msg+'</div>';
        } catch(_){}
      }
      msgsEl.scrollTop = msgsEl.scrollHeight;
    }
  } catch(e) {
    document.getElementById('ai-reply-text').textContent = t('err_network_error','Network error') + ': '+e.message;
  }
}

function aiClearChat() {
  _aiConversationId = null;
  document.getElementById('ai-messages').innerHTML = '<div data-welcome style="color:var(--text-muted);text-align:center;padding:48px;"><img src="/static/sybrt-mascot.png" alt="Sybrt" style="width:48px;height:48px;border-radius:50%;margin-bottom:8px;opacity:0.9;"><br>' + t('msg_new_chat_started','New chat started. Type a message to begin.') + '</div>';
}

// ═══════════════════════════════════════════════════════════════════
// PROVISIONING WIZARD
// ═══════════════════════════════════════════════════════════════════

var _provisionSession = null;
var _provisionSuggested = null;

async function provisionStart() {
  var data = await apiFetch('/api/provisioning/start', {method:'POST'});
  if (!data) return;
  _provisionSession = data.session_id;
  _provisionSuggested = null;
  provisionRenderStep(1);
}

function provisionRenderStep(step) {
  var el = document.getElementById('provision-content');
  var stepNames = ['',t('lbl_customer','Customer'),t('lbl_network','Network'),t('lbl_services','Services'),t('lbl_security','Security'),t('lbl_review','Review')];
  // Progress bar
  var html = '<div style="display:flex;gap:4px;margin-bottom:20px;">';
  for (var i = 1; i <= 5; i++) {
    var bg = i < step ? 'var(--green)' : i === step ? 'var(--blue)' : 'var(--border)';
    html += '<div style="flex:1;height:4px;border-radius:2px;background:'+bg+';"></div>';
  }
  html += '</div>';
  html += '<h3 style="font-size:15px;font-weight:600;margin-bottom:16px;">' + t('lbl_step','Step') + ' '+step+': '+stepNames[step]+'</h3>';

  if (step === 1) {
    html += '<div style="max-width:500px;">'
      + '<label class="field-label">' + t('lbl_customer_name') + ' *</label>'
      + '<input id="prov-name" type="text" class="field-input" placeholder="' + t('placeholder_customer_name','Customer name') + '" style="margin-bottom:8px;">'
      + '<label class="field-label">' + t('placeholder_location','Location') + '</label>'
      + '<input id="prov-location" type="text" class="field-input" placeholder="' + t('placeholder_location','Location') + '" style="margin-bottom:8px;">'
      + '<label class="field-label">' + t('lbl_device_type','Device type') + '</label>'
      + '<select id="prov-device" class="field-input" style="margin-bottom:8px;"><option value="fortigate">FortiGate</option><option value="unifi">UniFi</option><option value="both">' + t('lbl_both','Both') + '</option></select>'
      + '<label class="field-label">' + t('placeholder_target_host','Target host (IP)') + '</label>'
      + '<input id="prov-target" type="text" class="field-input" placeholder="192.168.1.99" style="margin-bottom:12px;">'
      + '<button class="btn btn-ghost btn-sm" onclick="provisionAutoFill()" style="font-size:12px;">' + t('btn_fill_from_customer','Fyll fra aktiv kunde') + '</button>'
      + '</div>';
    setTimeout(provisionAutoFill, 50);
  } else if (step === 2) {
    html += '<div style="max-width:600px;">'
      + '<label class="field-label">WAN</label>'
      + '<select id="prov-wan" class="field-input" style="margin-bottom:8px;"><option value="dhcp">DHCP</option><option value="static">' + t('lbl_static','Static') + '</option><option value="pppoe">PPPoE</option></select>'
      + '<div style="display:flex;gap:8px;align-items:end;margin-bottom:8px;">'
      + '<div style="flex:1;"><label class="field-label">' + t('lan_subnet') + '</label><input id="prov-subnet" type="text" class="field-input" placeholder="10.x.0.0/24" value="' + (_provisionSuggested ? _provisionSuggested.lan_subnet : '192.168.1.0/24') + '"></div>'
      + '<button class="btn btn-ghost btn-sm" onclick="provisionSuggestSubnets()" style="font-size:12px;white-space:nowrap;margin-bottom:1px;">' + t('btn_suggest_subnets','Auto-generer subnets') + '</button>'
      + '</div>'
      + '<label class="field-label">VLANs</label>'
      + '<div id="prov-vlan-table"></div>'
      + '<button class="btn btn-ghost btn-sm" onclick="provisionAddVlan()" style="font-size:12px;margin-top:6px;">+ ' + t('btn_add_vlan','Legg til VLAN') + '</button>'
      + '</div>';
    setTimeout(function() { provisionRenderVlans(_provisionSuggested ? _provisionSuggested.vlans : []); }, 20);
  } else if (step === 3) {
    html += '<div style="max-width:500px;">'
      + '<input id="prov-dns" type="text" placeholder="DNS-servere (komma)" value="1.1.1.1, 1.0.0.1" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);">'
      + '<input id="prov-ntp" type="text" placeholder="NTP-servere" value="0.pool.ntp.org" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);">'
      + '<input id="prov-syslog" type="text" placeholder="' + t('placeholder_syslog_server','Syslog server (optional)') + '" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);">'
      + '</div>';
  } else if (step === 4) {
    html += '<div style="max-width:500px;">'
      + '<input id="prov-admin-pw" type="password" placeholder="' + t('placeholder_admin_password','Admin password') + '" style="width:100%;padding:8px 12px;margin-bottom:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);">'
      + '<label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:8px;"><input type="checkbox" id="prov-webfilter" checked> ' + t('web_filter') + '</label>'
      + '<label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:8px;"><input type="checkbox" id="prov-ids" checked> IDS/IPS</label>'
      + '</div>';
  } else if (step === 5) {
    html += '<div id="prov-summary" style="color:var(--text-muted);">' + t('msg_loading_summary','Loading summary...') + '</div>'
      + '<div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap;">'
      + '<button class="btn btn-primary" onclick="provisionDeploy(\'rest\')" style="padding:8px 16px;">' + t('btn_deploy_rest','Deploy via REST API') + '</button>'
      + '<button class="btn btn-default" onclick="provisionGenerate(false)" style="padding:8px 16px;">' + t('btn_generate_config','Generate config') + '</button>'
      + '<button class="btn btn-ghost" onclick="provisionGenerate(true)" style="padding:8px 16px;">' + t('btn_generate_with_ai','Generate with AI') + '</button>'
      + '</div>'
      + '<div id="prov-deploy-result" style="display:none;margin-top:16px;"></div>'
      + '<pre id="prov-output" style="display:none;margin-top:16px;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:16px;font-size:12px;font-family:var(--mono);overflow-x:auto;white-space:pre-wrap;max-height:400px;overflow-y:auto;"></pre>';
    setTimeout(provisionLoadSummary, 100);
  }

  // Navigation buttons
  html += '<div style="display:flex;gap:8px;margin-top:20px;">';
  if (step > 1) html += '<button class="btn btn-ghost" onclick="provisionPrevStep('+step+')" style="padding:8px 16px;">' + t('tilbake') + '</button>';
  if (step < 5) html += '<button class="btn btn-primary" onclick="provisionNextStep('+step+')" style="padding:8px 16px;">' + t('neste_2') + '</button>';
  html += '</div>';
  el.innerHTML = html;
}

async function provisionNextStep(current) {
  var data = {};
  if (current === 1) {
    data = {name:document.getElementById('prov-name').value, location:document.getElementById('prov-location').value, device_type:document.getElementById('prov-device').value, target_host:document.getElementById('prov-target').value};
  } else if (current === 2) {
    var vlans = provisionCollectVlans();
    data = {wan_type:document.getElementById('prov-wan').value, lan_subnet:document.getElementById('prov-subnet').value, vlans:vlans};
  } else if (current === 3) {
    data = {dns_servers:document.getElementById('prov-dns').value.split(',').map(function(s){return s.trim();}), ntp_servers:document.getElementById('prov-ntp').value.split(',').map(function(s){return s.trim();}), syslog_server:document.getElementById('prov-syslog').value.trim()};
  } else if (current === 4) {
    data = {admin_password:document.getElementById('prov-admin-pw').value, web_filter:document.getElementById('prov-webfilter').checked, ids_ips:document.getElementById('prov-ids').checked};
  }
  await apiFetch('/api/provisioning/'+_provisionSession+'/step/'+current, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  provisionRenderStep(current + 1);
}

function provisionPrevStep(current) { provisionRenderStep(current - 1); }

async function provisionLoadSummary() {
  var data = await apiFetch('/api/provisioning/'+_provisionSession+'/summary');
  if (!data) return;
  var el = document.getElementById('prov-summary');
  var steps = data.steps || {};
  var html = '<div style="font-size:13px;">';
  if (steps['1']) html += '<div style="margin-bottom:8px;"><strong>' + t('kunde_2') + '</strong> '+(steps['1'].name||'-')+' @ '+(steps['1'].location||'-')+' ('+steps['1'].device_type+')</div>';
  if (steps['2']) html += '<div style="margin-bottom:8px;"><strong>' + t('nettverk') + '</strong> WAN='+steps['2'].wan_type+', LAN='+steps['2'].lan_subnet+(steps['2'].vlans?.length ? ', '+steps['2'].vlans.length+' VLANs' : '')+'</div>';
  if (steps['3']) html += '<div style="margin-bottom:8px;"><strong>' + t('tjenester') + '</strong> DNS='+(steps['3'].dns_servers||[]).join(',')+', NTP='+(steps['3'].ntp_servers||[]).join(',')+'</div>';
  if (steps['4']) html += '<div style="margin-bottom:8px;"><strong>' + t('sikkerhet') + '</strong> Web-filter='+(steps['4'].web_filter?'Ja':t('lbl_no','No'))+', IDS='+(steps['4'].ids_ips?'Ja':t('lbl_no','No'))+'</div>';
  html += '</div>';
  el.innerHTML = html;
}

async function provisionGenerate(useAi) {
  var el = document.getElementById('prov-output');
  el.style.display = 'block';
  el.textContent = useAi ? t('msg_generating_ai','Generating with AI...') : t('msg_generating_config','Generating configuration...');
  var data = await apiFetch('/api/provisioning/'+_provisionSession+'/generate', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({use_ai:useAi})});
  if (!data || !data.configs) { el.textContent = t('err_generation_failed','Generation failed'); return; }
  var text = '';
  if (data.configs.fortigate_cli) text += '# === FortiGate CLI ===\n' + data.configs.fortigate_cli + '\n\n';
  if (data.configs.unifi_json) text += '# === UniFi JSON ===\n' + data.configs.unifi_json;
  el.textContent = text || t('msg_no_config_generated','No configuration generated');
}

// ── Provisioning helpers ────────────────────────────────────────────────────

async function provisionAutoFill() {
  var data = await apiFetch('/api/network-devices');
  if (data && data.fortigate && data.fortigate.host) {
    var targetEl = document.getElementById('prov-target');
    if (targetEl && !targetEl.value) targetEl.value = data.fortigate.host;
  }
  var status = await apiFetch('/api/status');
  if (status && status.customer && status.customer.name) {
    var nameEl = document.getElementById('prov-name');
    if (nameEl && !nameEl.value) nameEl.value = status.customer.name;
  }
}

async function provisionSuggestSubnets() {
  var name = (document.getElementById('prov-name') || {}).value || '';
  if (!name) name = (document.getElementById('prov-name') || {}).placeholder || 'default';
  var data = await apiFetch('/api/provisioning/suggest-subnets', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name})
  });
  if (!data || !data.lan_subnet) return;
  _provisionSuggested = data;
  var subnetEl = document.getElementById('prov-subnet');
  if (subnetEl) subnetEl.value = data.lan_subnet;
  provisionRenderVlans(data.vlans || []);
}

var _provisionVlans = [];

function provisionRenderVlans(vlans) {
  _provisionVlans = vlans && vlans.length ? vlans : [];
  var el = document.getElementById('prov-vlan-table');
  if (!el) return;
  if (!_provisionVlans.length) {
    el.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:8px;">' + t('msg_no_vlans','Ingen VLANs. Klikk "Auto-generer subnets" eller legg til manuelt.') + '</div>';
    return;
  }
  var html = '<table style="width:100%;font-size:12px;border-collapse:collapse;">'
    + '<thead><tr style="text-align:left;color:var(--text-muted);"><th style="padding:4px;">' + t('navn_2') + '</th><th style="padding:4px;">' + t('vlan_id') + '</th><th style="padding:4px;">' + t('subnet') + '</th><th style="padding:4px;width:30px;"></th></tr></thead><tbody>';
  for (var i = 0; i < _provisionVlans.length; i++) {
    var v = _provisionVlans[i];
    html += '<tr style="border-top:1px solid var(--border);">'
      + '<td style="padding:4px;"><input type="text" class="field-input" value="' + esc(v.name || '') + '" data-vlan-idx="'+i+'" data-vlan-field="name" style="padding:4px 8px;font-size:12px;"></td>'
      + '<td style="padding:4px;"><input type="number" class="field-input" value="' + (v.id || '') + '" data-vlan-idx="'+i+'" data-vlan-field="id" style="padding:4px 8px;font-size:12px;width:70px;"></td>'
      + '<td style="padding:4px;"><input type="text" class="field-input" value="' + esc(v.subnet || '') + '" data-vlan-idx="'+i+'" data-vlan-field="subnet" style="padding:4px 8px;font-size:12px;"></td>'
      + '<td style="padding:4px;"><button class="btn btn-ghost btn-sm" onclick="provisionRemoveVlan('+i+')" style="padding:2px 6px;color:var(--red);">✕</button></td>'
      + '</tr>';
  }
  html += '</tbody></table>'
    + '<div style="font-size:11px;color:var(--text-muted);margin-top:6px;">Hver VLAN får standard policy: VLAN → WAN, NAT, full UTM. Spesialcase (no-UTM, web-only osv.) konfigurerer du i FortiGate-GUI etter generering.</div>';
  el.innerHTML = html;
}

function provisionAddVlan() {
  _provisionVlans.push({name:'', id:_provisionVlans.length ? Math.max.apply(null, _provisionVlans.map(function(v){return v.id||0;}))+10 : 10, subnet:''});
  provisionRenderVlans(_provisionVlans);
}

function provisionRemoveVlan(idx) {
  _provisionVlans.splice(idx, 1);
  provisionRenderVlans(_provisionVlans);
}

function provisionCollectVlans() {
  var rows = document.querySelectorAll('[data-vlan-idx]');
  var map = {};
  rows.forEach(function(el) {
    var idx = el.dataset.vlanIdx;
    if (!map[idx]) map[idx] = {};
    var field = el.dataset.vlanField;
    map[idx][field] = field === 'id' ? parseInt(el.value) || 0 : el.value.trim ? el.value.trim() : el.value;
  });
  return Object.values(map).filter(function(v) { return v.name || v.id; });
}

var _lastDeploySummary = null;

async function provisionDeploy(method) {
  var el = document.getElementById('prov-deploy-result');
  el.style.display = 'block';
  el.innerHTML = '<div style="color:var(--blue);font-size:13px;"><div class="loader" style="width:16px;height:16px;display:inline-block;vertical-align:middle;margin-right:8px;"></div>' + t('msg_deploying','Deployer konfigurasjon...') + '</div>';

  // First ensure config is generated
  await apiFetch('/api/provisioning/'+_provisionSession+'/generate', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({use_ai:false})});

  var data = await apiFetch('/api/provisioning/'+_provisionSession+'/deploy', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({method:method})
  });

  if (!data) { el.innerHTML = '<div class="alert alert-error">' + t('msg_deploy_failed','Deploy feilet') + '</div>'; return; }

  var fg = data.results && data.results.fortigate;
  if (!fg) { el.innerHTML = '<div class="alert alert-error">' + esc(data.error || t('msg_deploy_failed','Deploy feilet')) + '</div>'; return; }

  _lastDeploySummary = fg.config_summary || null;

  var ok = fg.success || 0;
  var total = fg.total || 0;
  var failed = fg.failed || 0;
  var statusClass = failed === 0 ? 'alert-success' : (ok > failed ? 'alert-warning' : 'alert-error');
  var statusText = failed === 0 ? t('msg_deploy_success','Konfigurasjon deployet') : (ok + '/' + total + ' OK, ' + failed + ' feilet');

  var html = '<div class="alert ' + statusClass + '" style="margin-bottom:12px;">' + statusText + '</div>';

  // Step details
  if (fg.details) {
    html += '<details style="margin-bottom:16px;"><summary style="cursor:pointer;font-size:13px;font-weight:600;margin-bottom:8px;">' + t('lbl_details','Detaljer') + ' (' + total + ' steg)</summary>';
    html += '<div style="font-size:12px;font-family:var(--mono);max-height:300px;overflow-y:auto;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px 12px;">';
    fg.details.forEach(function(d) {
      var icon = d.ok ? '<span style="color:var(--green);">✓</span>' : '<span style="color:var(--red);">✗</span>';
      html += '<div style="padding:2px 0;">' + icon + ' ' + esc(d.step) + (d.error ? ' — <span style="color:var(--red);">' + esc(d.error) + '</span>' : '') + '</div>';
    });
    html += '</div></details>';
  }

  // IP change notification
  if (fg.lan_ip_changed && fg.new_ip) {
    html += '<div class="alert alert-warning" style="margin:12px 0;">'
      + '<strong>' + t('msg_lan_ip_changed','Brannmurens LAN-adresse er endret') + '</strong><br>'
      + t('msg_lan_ip_old','Gammel IP') + ': <code>' + esc(fg.old_ip || '') + '</code> → '
      + t('msg_lan_ip_new','Ny IP') + ': <code>' + esc(fg.new_ip) + '</code><br><br>'
      + t('msg_lan_ip_instructions','Du må koble til det nye subnettet for å nå brannmuren. Forny DHCP-lease eller sett manuell IP.') + '<br><br>'
      + '<a href="https://' + esc(fg.new_ip) + ':8443" target="_blank" class="btn btn-primary btn-sm">'
      + t('btn_open_new_ip','Åpne brannmur på ny adresse') + ' → ' + esc(fg.new_ip) + ':8443</a>'
      + '</div>';
  }

  // Config summary
  if (_lastDeploySummary) {
    html += _renderConfigSummary(_lastDeploySummary);
  }

  el.innerHTML = html;
}

function _renderConfigSummary(s) {
  var html = '<div class="card" style="margin-top:16px;">';
  html += '<div class="card-title">' + t('hdr_config_summary','Konfigurasjonsoversikt') + '</div>';

  // System
  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:13px;margin-bottom:16px;">';
  html += '<div><strong>' + t('hostname') + '</strong> ' + esc(s.hostname || '') + '</div>';
  html += '<div><strong>' + t('fortigate') + '</strong> ' + esc(s.fortigate_host || '') + ':' + (s.fortigate_port || 443) + '</div>';
  html += '<div><strong>' + t('wan') + '</strong> ' + esc(s.wan_interface || '') + ' (' + esc(s.wan_mode || '') + ')</div>';
  html += '<div><strong>' + t('lan') + '</strong> ' + esc(s.lan_interface || '') + ' — ' + esc(s.lan_subnet || '') + '</div>';
  html += '<div><strong>' + t('dns') + '</strong> ' + esc((s.dns || []).join(', ')) + '</div>';
  html += '<div><strong>' + t('ntp') + '</strong> ' + esc((s.ntp || []).join(', ')) + '</div>';
  html += '</div>';

  // VLANs
  if (s.vlans && s.vlans.length) {
    html += '<div style="font-size:13px;font-weight:600;margin-bottom:6px;">VLANs</div>';
    html += '<table style="width:100%;font-size:12px;border-collapse:collapse;margin-bottom:16px;">';
    html += '<thead><tr style="text-align:left;color:var(--text-muted);border-bottom:1px solid var(--border);"><th style="padding:4px 8px;">ID</th><th style="padding:4px 8px;">' + t('navn_3') + '</th><th style="padding:4px 8px;">' + t('interface') + '</th><th style="padding:4px 8px;">' + t('subnet') + '</th><th style="padding:4px 8px;">' + t('gateway_2') + '</th><th style="padding:4px 8px;">DHCP</th></tr></thead><tbody>';
    s.vlans.forEach(function(v) {
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += '<td style="padding:4px 8px;font-family:var(--mono);">' + v.id + '</td>';
      html += '<td style="padding:4px 8px;">' + esc(v.name) + '</td>';
      html += '<td style="padding:4px 8px;font-family:var(--mono);">' + esc(v.interface) + '</td>';
      html += '<td style="padding:4px 8px;font-family:var(--mono);">' + esc(v.subnet) + '</td>';
      html += '<td style="padding:4px 8px;font-family:var(--mono);">' + esc(v.gateway) + '</td>';
      html += '<td style="padding:4px 8px;font-family:var(--mono);">' + esc(v.dhcp_range) + '</td>';
      html += '</tr>';
    });
    html += '</tbody></table>';
  }

  // VPN
  if (s.vpn) {
    html += '<div style="font-size:13px;font-weight:600;margin-bottom:6px;">IPsec VPN — ' + esc(s.vpn.name || '') + '</div>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:12px;margin-bottom:16px;">';
    html += '<div><strong>' + t('type_3') + '</strong> ' + esc(s.vpn.type) + '</div>';
    html += '<div><strong>' + t('wan') + '</strong> ' + esc(s.vpn.wan_interface) + '</div>';
    html += '<div><strong>' + t('kryptering') + '</strong> ' + esc(s.vpn.proposal) + '</div>';
    html += '<div><strong>' + t('dh_gruppe') + '</strong> ' + esc(s.vpn.dh_group) + '</div>';
    html += '<div><strong>' + t('tunnel_pool') + '</strong> ' + esc(s.vpn.tunnel_pool) + '</div>';
    html += '<div><strong>' + t('split_tunnel') + '</strong> ' + esc(s.vpn.split_tunnel) + '</div>';
    html += '<div style="grid-column:1/-1;border-top:1px solid var(--border);padding-top:8px;margin-top:4px;">';
    html += '<strong>' + t('bruker') + '</strong> <code style="background:var(--bg-card);padding:2px 6px;border-radius:4px;">' + esc(s.vpn.user) + '</code>';
    html += ' &nbsp; <strong>' + t('passord_2') + '</strong> <code style="background:var(--bg-card);padding:2px 6px;border-radius:4px;cursor:pointer;" onclick="navigator.clipboard.writeText(this.textContent);showToast(\'Kopiert\',\'success\',1500)">' + esc(s.vpn.user_password) + '</code>';
    html += '</div>';
    html += '<div style="grid-column:1/-1;">';
    html += '<strong>PSK:</strong> <code style="background:var(--bg-card);padding:2px 6px;border-radius:4px;cursor:pointer;word-break:break-all;" onclick="navigator.clipboard.writeText(this.textContent);showToast(\'Kopiert\',\'success\',1500)">' + esc(s.vpn.psk) + '</code>';
    html += '</div></div>';
  }

  // Security
  if (s.security_profiles) {
    html += '<div style="font-size:13px;font-weight:600;margin-bottom:6px;">' + t('sikkerhetsprofiler') + '</div>';
    html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;">';
    var sp = s.security_profiles;
    for (var k in sp) {
      var color = sp[k] === 'none' ? 'var(--red)' : 'var(--green)';
      html += '<span style="font-size:11px;padding:3px 10px;border-radius:12px;background:' + color + '22;color:' + color + ';border:1px solid ' + color + '44;">' + esc(k) + ': ' + esc(sp[k]) + '</span>';
    }
    html += '</div>';
  }

  // Actions
  html += '<div style="display:flex;gap:8px;margin-top:12px;padding-top:12px;border-top:1px solid var(--border);">';
  html += '<button class="btn btn-primary btn-sm" onclick="provisionDownloadSummary()">' + t('btn_download_summary','Last ned oversikt') + '</button>';
  html += '<button class="btn btn-default btn-sm" onclick="provisionCopySummary()">' + t('btn_copy_to_clipboard') + '</button>';
  html += '</div>';
  html += '</div>';
  return html;
}

function provisionDownloadSummary() {
  if (!_lastDeploySummary) return;
  var s = _lastDeploySummary;
  var lines = [];
  lines.push('╔══════════════════════════════════════════════════════════════╗');
  lines.push('║  FORTIGATE KONFIGURASJONSOVERSIKT                          ║');
  lines.push('║  ' + (s.customer || '').padEnd(58) + '║');
  lines.push('║  Generert: ' + (s.generated_at || '').substring(0,19).padEnd(48) + '║');
  lines.push('╚══════════════════════════════════════════════════════════════╝');
  lines.push('');
  lines.push('SYSTEM');
  lines.push('─'.repeat(60));
  lines.push('  Hostname:       ' + (s.hostname || ''));
  lines.push('  FortiGate:      ' + (s.fortigate_host || '') + ':' + (s.fortigate_port || 443));
  lines.push('  WAN interface:  ' + (s.wan_interface || '') + ' (' + (s.wan_mode || '') + ')');
  lines.push('  LAN interface:  ' + (s.lan_interface || '') + ' — ' + (s.lan_subnet || ''));
  lines.push('  LAN gateway:    ' + (s.lan_gateway || ''));
  lines.push('  DNS:            ' + (s.dns || []).join(', '));
  lines.push('  NTP:            ' + (s.ntp || []).join(', '));
  lines.push('');
  lines.push('VLANS');
  lines.push('─'.repeat(60));
  lines.push('  ' + 'ID'.padEnd(6) + 'Navn'.padEnd(16) + 'Interface'.padEnd(22) + 'Subnet'.padEnd(20) + 'GW');
  (s.vlans || []).forEach(function(v) {
    lines.push('  ' + String(v.id).padEnd(6) + (v.name||'').padEnd(16) + (v.interface||'').padEnd(22) + (v.subnet||'').padEnd(20) + (v.gateway||''));
  });
  lines.push('');
  if (s.vpn) {
    lines.push('IPSEC VPN');
    lines.push('─'.repeat(60));
    lines.push('  Navn:           ' + (s.vpn.name || ''));
    lines.push('  Type:           ' + (s.vpn.type || ''));
    lines.push('  WAN interface:  ' + (s.vpn.wan_interface || ''));
    lines.push('  Kryptering:     ' + (s.vpn.proposal || ''));
    lines.push('  DH-gruppe:      ' + (s.vpn.dh_group || ''));
    lines.push('  Tunnel-pool:    ' + (s.vpn.tunnel_pool || ''));
    lines.push('  Split-tunnel:   ' + (s.vpn.split_tunnel || ''));
    lines.push('');
    lines.push('  ⚠ CREDENTIALS (OPPBEVAR SIKKERT)');
    lines.push('  Bruker:         ' + (s.vpn.user || ''));
    lines.push('  Passord:        ' + (s.vpn.user_password || ''));
    lines.push('  PSK:            ' + (s.vpn.psk || ''));
    lines.push('');
  }
  if (s.security_profiles) {
    lines.push('SIKKERHETSPROFILER');
    lines.push('─'.repeat(60));
    var sp = s.security_profiles;
    for (var k in sp) { lines.push('  ' + (k + ':').padEnd(20) + sp[k]); }
    lines.push('');
  }
  if (s.hardening) {
    lines.push('HARDENING');
    lines.push('─'.repeat(60));
    var h = s.hardening;
    for (var k in h) { lines.push('  ' + (k + ':').padEnd(20) + h[k]); }
  }
  var text = lines.join('\n');
  var blob = new Blob([text], {type:'text/plain'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = (s.customer || 'fortigate').replace(/\s+/g,'-') + '_fortigate-config_' + new Date().toISOString().slice(0,10) + '.txt';
  a.click();
}

function provisionCopySummary() {
  if (!_lastDeploySummary) return;
  navigator.clipboard.writeText(JSON.stringify(_lastDeploySummary, null, 2));
  showToast(t('msg_copied','Kopiert til utklippstavle'), 'success', 2000);
}

// ═══════════════════════════════════════════════════════════════════
// FORTIGATE DASHBOARD (ALL CUSTOMERS)
// ═══════════════════════════════════════════════════════════════════

async function dashLoadFortiGates() {
  var el = document.getElementById('dash-fg-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div><div style="text-align:center;color:var(--text-muted);font-size:12px;">' + t('msg_loading_fortigates','Loading all FortiGate firewalls...') + '</div>';

  var data = await apiFetch('/api/fortigate/all');
  if (!data || !data.fortigates) { el.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:48px;">' + t('msg_no_fortigates','No FortiGates configured. Add under Integrations per customer.') + '</div>'; return; }

  var fgs = data.fortigates;
  if (!fgs.length) { el.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:48px;">' + t('msg_no_fortigates_short','No FortiGates configured.') + '</div>'; return; }

  var online = fgs.filter(function(f){return f.status==='online';}).length;
  var errors = fgs.filter(function(f){return f.status==='error';}).length;

  // Summary KPI cards
  var totalVpn = fgs.reduce(function(s,f){return s+(f.vpn_tunnels||0);},0);
  var totalPolicies = fgs.reduce(function(s,f){return s+(f.policy_count||0);},0);
  var avgCpu = 0, cpuCount = 0;
  fgs.forEach(function(f){if(f.cpu_pct!==null&&f.cpu_pct!==undefined){avgCpu+=f.cpu_pct;cpuCount++;}});
  avgCpu = cpuCount ? Math.round(avgCpu/cpuCount) : 0;
  var avgMem = 0, memCount = 0;
  fgs.forEach(function(f){if(f.mem_pct!==null&&f.mem_pct!==undefined){avgMem+=f.mem_pct;memCount++;}});
  avgMem = memCount ? Math.round(avgMem/memCount) : 0;

  // ── KPI row: fixed-height cards, no justify-content ──
  var html = '<div class="card-grid card-grid--kpi" style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:'Brannmurer', value:fgs.length, sub:online+' online'+(errors?' / '+errors+' feil':''), color:'var(--blue)'},
    {label:'Snitt CPU', value:avgCpu+'%', sub:'-', color: avgCpu>60?'var(--orange)':'var(--green)'},
    {label:'Snitt minne', value:avgMem+'%', sub:'-', color: avgMem>70?'var(--orange)':'var(--green)'},
    {label:'VPN-tunneler', value:totalVpn, sub:'totalt', color:'var(--purple)'},
    {label:'Brannmurregler', value:totalPolicies, sub:'totalt', color:'var(--text-muted)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card" style="padding:16px 8px;text-align:center;border-top:2px solid '+k.color+';height:90px;box-sizing:border-box;">';
    html += '<div style="font-size:20px;font-weight:700;line-height:24px;">'+k.value+'</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);line-height:16px;">'+k.label+'</div>';
    html += '<div style="font-size:10px;color:var(--text-dim);line-height:14px;">'+k.sub+'</div>';
    html += '</div>';
  });
  html += '</div>';

  html += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">';
  html += '<button class="btn btn-ghost" onclick="dashLoadFortiGates()" style="padding:4px 12px;font-size:11px;">' + t('oppdater') + '</button>';
  html += '<button class="btn btn-primary" onclick="fgBackupAll()" style="padding:4px 12px;font-size:11px;">' + t('backup_alle') + '</button>';
  html += '</div>';

  // ── Device cards: strict 3-row grid ──
  html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(350px,1fr));gap:12px;">';
  fgs.forEach(function(f) {
    var color = f.status === 'online' ? 'var(--green)' : f.status === 'error' ? 'var(--red)' : 'var(--orange)';
    html += '<div class="card" style="padding:14px;border-left:3px solid '+color+';display:grid;grid-template-rows:24px 20px 1fr;height:100%;cursor:pointer;" onclick="dashFgDetail(\''+f.customer_id+'\')">';

    // ROW 1 — Header (24px): hostname + status dot
    html += '<div style="display:flex;align-items:center;height:24px;overflow:hidden;">';
    html += '<strong style="font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0;">🛡 '+(f.hostname||f.host||'-')+'</strong>';
    html += '<span style="width:8px;height:8px;border-radius:50%;background:'+color+';flex-shrink:0;margin-left:8px;"></span>';
    html += '</div>';

    // ROW 2 — Subtitle (20px): customer name
    html += '<div style="font-size:11px;color:var(--text-muted);line-height:20px;height:20px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+(f.customer_name||'-')+'</div>';

    // ROW 3 — Data (1fr): 2-col stats grid, ALWAYS 8 fields
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:3px;font-size:12px;color:var(--text-muted);align-content:start;padding-top:6px;">';
    html += '<span>Model: <strong style="color:var(--text);">'+(f.model||'-')+'</strong></span>';
    html += '<span>FW: '+(f.firmware||'-')+'</span>';
    html += '<span>S/N: <span style="font-family:var(--mono);font-size:11px;">'+(f.serial||'-')+'</span></span>';
    html += '<span>Uptime: '+(f.uptime||'-')+'</span>';
    html += '<span>CPU: '+(f.cpu_pct!=null ? f.cpu_pct+'%' : '-')+'</span>';
    html += '<span>Mem: '+(f.mem_pct!=null ? f.mem_pct+'%' : '-')+'</span>';
    html += '<span>VPN: '+(f.vpn_tunnels!=null ? f.vpn_tunnels : '-')+'</span>';
    html += '<span>Rules: '+(f.policy_count!=null ? f.policy_count : '-')+'</span>';
    html += '</div>';

    html += '</div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

function dashFgDetail(customerId) {
  // Toggle inline detail panel below the FortiGate cards
  var existing = document.getElementById('fg-detail-' + customerId);
  if (existing) { existing.remove(); return; }
  // Remove any other open detail
  document.querySelectorAll('.fg-detail-panel').forEach(function(p) { p.remove(); });

  var el = document.getElementById('dash-fg-content');
  var panel = document.createElement('div');
  panel.id = 'fg-detail-' + customerId;
  panel.className = 'fg-detail-panel';
  panel.style.cssText = 'margin-top:16px;margin-bottom:16px;';
  panel.innerHTML = '<div class="card" style="padding:16px;border-left:3px solid var(--blue);"><div class="loader" style="width:16px;height:16px;margin:0 auto;"></div></div>';
  el.appendChild(panel);

  // Load threats, firewall audit, and live device data in parallel
  Promise.all([
    apiFetch('/api/fortigate/threats/' + customerId),
    apiFetch('/api/fortigate/firewall-audit/' + customerId),
    apiFetch('/api/dashboard/poll/' + customerId, {method:'POST'}).catch(function(){return null;})
  ]).then(function(results) {
    var threats = results[0];
    var audit = results[1];
    var liveData = results[2];
    // Find the FortiGate device in live data
    var dev = null;
    if (liveData && liveData.devices) {
      for (var i = 0; i < liveData.devices.length; i++) {
        if (liveData.devices[i].vendor === 'fortigate') { dev = liveData.devices[i]; break; }
      }
    }
    var ex = (dev && dev.extra) ? dev.extra : {};

    var h = '<div class="card" style="padding:16px;border-left:3px solid var(--blue);">';
    h += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">';
    h += '<div style="font-size:14px;font-weight:700;">'+t('hdr_fg_detail','FortiGate Detail')+'</div>';
    h += '<div style="display:flex;gap:8px;align-items:center;">';
    h += '<button class="btn btn-primary" onclick="fgBackupConfig(\''+customerId+'\')" style="padding:4px 12px;font-size:11px;">' + t('backup_config') + '</button>';
    h += '<button class="btn btn-ghost" onclick="fgShowBackups(\''+customerId+'\')" style="padding:4px 12px;font-size:11px;">'+t('btn_backup_history','Backup-historikk')+'</button>';
    h += '<button class="btn btn-ghost" onclick="document.getElementById(\'fg-detail-'+customerId+'\').remove()" style="padding:2px 8px;font-size:11px;">'+t('btn_close','Close')+'</button>';
    h += '</div></div>';
    h += '<div id="fg-backup-list-'+customerId+'" style="margin-bottom:8px;"></div>';

    // Threats
    if (threats && threats.summary) {
      var s = threats.summary;
      h += '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">'+t('hdr_threats','Threats')+' ('+t('lbl_last_7d','Last 7 days')+')</div>';
      h += '<div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;">';
      if (s.critical) h += '<span style="background:var(--red);color:#fff;padding:2px 10px;border-radius:10px;font-size:11px;font-weight:600;">'+s.critical+' Critical</span>';
      if (s.high) h += '<span style="background:var(--orange);color:#fff;padding:2px 10px;border-radius:10px;font-size:11px;font-weight:600;">'+s.high+' High</span>';
      if (s.medium) h += '<span style="background:#c9a800;color:#fff;padding:2px 10px;border-radius:10px;font-size:11px;font-weight:600;">'+s.medium+' Medium</span>';
      if (s.low) h += '<span style="background:var(--text-dim);color:#fff;padding:2px 10px;border-radius:10px;font-size:11px;font-weight:600;">'+s.low+' Low</span>';
      if (s.total === 0) h += '<span style="color:var(--green);font-size:12px;">&#10003; '+t('msg_no_threats','No threats detected')+'</span>';
      h += '</div>';
      if (threats.recent && threats.recent.length) {
        h += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:12px;">';
        h += '<thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:4px 6px;">'+t('col_time','Time')+'</th><th style="text-align:left;padding:4px 6px;">'+t('col_type','Type')+'</th><th style="text-align:center;padding:4px 6px;">'+t('col_severity','Severity')+'</th><th style="text-align:left;padding:4px 6px;">'+t('col_source','Source')+'</th><th style="text-align:left;padding:4px 6px;">'+t('col_attack','Attack')+'</th></tr></thead><tbody>';
        threats.recent.slice(0,5).forEach(function(e) {
          var sc = {critical:'var(--red)',high:'var(--orange)',medium:'#c9a800',low:'var(--text-dim)'}[e.severity]||'var(--text-dim)';
          h += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:3px 6px;">'+esc(e.timestamp||'').substring(0,16)+'</td><td style="padding:3px 6px;">'+esc(e.type)+'</td><td style="padding:3px 6px;text-align:center;color:'+sc+';font-weight:600;">'+esc(e.severity)+'</td><td style="padding:3px 6px;font-family:var(--mono);font-size:10px;">'+esc(e.srcip||'')+'</td><td style="padding:3px 6px;">'+esc(e.attack||'')+'</td></tr>';
        });
        h += '</tbody></table>';
      }
    } else {
      h += '<div style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">'+t('msg_no_threat_data','Could not load threat data')+'</div>';
    }

    // Firewall Audit
    if (audit && audit.total_rules !== undefined) {
      var scoreColor = audit.score >= 90 ? 'var(--green)' : audit.score >= 70 ? 'var(--orange)' : 'var(--red)';
      h += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">';
      h += '<div style="font-size:13px;font-weight:600;">'+t('hdr_fw_audit','Firewall Audit')+'</div>';
      h += '<span style="background:'+scoreColor+';color:#fff;padding:2px 10px;border-radius:10px;font-size:12px;font-weight:700;">'+audit.score+'/100</span>';
      h += '<span style="font-size:11px;color:var(--text-muted);">'+audit.total_rules+' '+t('lbl_rules','rules')+' ('+audit.enabled+' '+t('lbl_enabled','enabled')+')</span>';
      h += '</div>';
      if (audit.issues && audit.issues.length) {
        h += '<table style="width:100%;border-collapse:collapse;font-size:11px;">';
        h += '<thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:4px 6px;">' + t('policy') + '</th><th style="text-align:center;padding:4px 6px;">'+t('col_issue','Issue')+'</th><th style="text-align:center;padding:4px 6px;">'+t('col_severity','Severity')+'</th><th style="text-align:left;padding:4px 6px;">'+t('col_detail','Detail')+'</th></tr></thead><tbody>';
        audit.issues.forEach(function(iss) {
          var ic = iss.severity==='critical'?'var(--red)':'var(--orange)';
          h += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:3px 6px;font-weight:500;">'+esc(iss.name||'Policy '+iss.policy_id)+'</td><td style="padding:3px 6px;text-align:center;"><span style="font-size:10px;background:var(--bg-tertiary);padding:1px 6px;border-radius:8px;">'+esc(iss.issue)+'</span></td><td style="padding:3px 6px;text-align:center;color:'+ic+';font-weight:600;">'+esc(iss.severity)+'</td><td style="padding:3px 6px;color:var(--text-muted);">'+esc(iss.detail)+'</td></tr>';
        });
        h += '</tbody></table>';
      } else {
        h += '<div style="color:var(--green);font-size:12px;">&#10003; '+t('msg_no_issues','No issues found')+'</div>';
      }
    }

    // ── Live device data: interfaces, VPN, DHCP, DNS, admins ──
    if (dev) {
      h += '<div style="margin-top:16px;border-top:1px solid var(--border);padding-top:12px;">';
      h += '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">' + t('live_data') + '</div>';

      // KPI row
      var liveKpis = [];
      if (dev.cpu_pct != null) liveKpis.push({l:'CPU', v:dev.cpu_pct+'%', c:dev.cpu_pct>80?'var(--red)':dev.cpu_pct>50?'var(--orange)':'var(--green)'});
      if (dev.mem_pct != null) liveKpis.push({l:'Minne', v:dev.mem_pct+'%', c:dev.mem_pct>80?'var(--red)':dev.mem_pct>50?'var(--orange)':'var(--green)'});
      if (dev.sessions != null) liveKpis.push({l:'Sesjoner', v:dev.sessions.toLocaleString(), c:'var(--blue)'});
      if (dev.vpn_tunnels != null) liveKpis.push({l:'VPN-tunneler', v:dev.vpn_tunnels, c:'var(--purple)'});
      if (liveKpis.length) {
        h += '<div style="display:grid;grid-template-columns:repeat('+Math.min(liveKpis.length,5)+',1fr);gap:8px;margin-bottom:12px;">';
        liveKpis.forEach(function(k){h += '<div class="card" style="padding:10px;text-align:center;border-top:2px solid '+k.c+';"><div style="font-size:18px;font-weight:700;">'+k.v+'</div><div style="font-size:10px;color:var(--text-muted);">'+k.l+'</div></div>';});
        h += '</div>';
      }

      // Interfaces
      if (ex.interfaces && ex.interfaces.length) {
        h += '<div style="font-size:12px;font-weight:600;margin:10px 0 6px;">Grensesnitt ('+ex.interfaces.length+')</div>';
        h += '<table style="width:100%;font-size:11px;border-collapse:collapse;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:4px;">' + t('navn_3') + '</th><th>' + t('type_3') + '</th><th>IP</th><th>' + t('link') + '</th><th>' + t('hastighet') + '</th></tr></thead><tbody>';
        ex.interfaces.forEach(function(iface) {
          if (!iface.ip || iface.ip === '0.0.0.0') return;
          var linkColor = iface.link ? 'var(--green)' : 'var(--red)';
          h += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px;font-weight:600;">'+esc(iface.name)+'</td><td style="padding:4px;color:var(--text-muted);">'+(iface.type||'-')+'</td><td style="padding:4px;font-family:var(--mono);font-size:10px;">'+iface.ip+'/'+(iface.mask||'')+'</td><td style="padding:4px;"><span style="color:'+linkColor+';">'+(iface.link?'Up':'Down')+'</span></td><td style="padding:4px;">'+(iface.speed?iface.speed+'M':'')+'</td></tr>';
        });
        h += '</tbody></table>';
      }

      // VPN tunnels
      if (ex.vpn_tunnels && ex.vpn_tunnels.length) {
        h += '<div style="font-size:12px;font-weight:600;margin:12px 0 6px;">VPN-tunneler ('+ex.vpn_tunnels.length+')</div>';
        h += '<table style="width:100%;font-size:11px;border-collapse:collapse;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:4px;">' + t('navn_3') + '</th><th>' + t('remote_gw') + '</th><th>' + t('status_3') + '</th></tr></thead><tbody>';
        ex.vpn_tunnels.forEach(function(v) {
          var vpnColor = v.status === 'up' ? 'var(--green)' : 'var(--red)';
          h += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px;font-weight:600;">'+esc(v.name)+'</td><td style="padding:4px;font-family:var(--mono);font-size:10px;">'+esc(v.remote_gw||'-')+'</td><td style="padding:4px;"><span style="color:'+vpnColor+';">'+(v.status||'unknown')+'</span></td></tr>';
        });
        h += '</tbody></table>';
      }

      // SSL VPN active users
      if (ex.ssl_vpn_users && ex.ssl_vpn_users.length) {
        h += '<div style="font-size:12px;font-weight:600;margin:12px 0 6px;">SSL VPN-brukere ('+ex.ssl_vpn_users.length+' aktive)</div>';
        h += '<table style="width:100%;font-size:11px;border-collapse:collapse;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:4px;">' + t('bruker') + '</th><th>' + t('remote_ip') + '</th><th>' + t('tunnel_ip') + '</th><th>' + t('varighet') + '</th></tr></thead><tbody>';
        ex.ssl_vpn_users.forEach(function(u) {
          var dur = u.duration > 3600 ? Math.floor(u.duration/3600)+'t '+Math.floor((u.duration%3600)/60)+'m' : Math.floor(u.duration/60)+'m';
          h += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px;font-weight:500;">'+esc(u.user)+'</td><td style="padding:4px;font-family:var(--mono);font-size:10px;">'+esc(u.remote_ip)+'</td><td style="padding:4px;font-family:var(--mono);font-size:10px;">'+esc(u.tunnel_ip)+'</td><td style="padding:4px;">'+dur+'</td></tr>';
        });
        h += '</tbody></table>';
      }

      // Firewall policies (all rules with security profiles)
      if (ex.policies && ex.policies.length) {
        var badPolicies = ex.policies.filter(function(p){return p.action==='accept'&&p.src==='all'&&p.dst==='all'&&p.svc==='ALL';});
        var noProfile = ex.policies.filter(function(p){return p.action==='accept'&&(!p.profiles||!p.profiles.length)&&p.enabled!==false;});
        var segmentDeny = ex.policies.filter(function(p){return p.action==='deny'&&p.enabled!==false;});
        var acceptRules = ex.policies.filter(function(p){return p.action==='accept'&&p.enabled!==false;});
        h += '<div style="font-size:12px;font-weight:600;margin:12px 0 6px;">Brannmurregler ('+ex.policies.length+')';
        if (segmentDeny.length) h += ' <span style="color:var(--green);font-weight:400;">— '+segmentDeny.length+' segmentering (deny)</span>';
        h += ' <span style="color:var(--text-muted);font-weight:400;">— '+acceptRules.length+' accept</span>';
        if (badPolicies.length) h += ' <span style="color:var(--red);font-weight:400;">— '+badPolicies.length+' accept any/any/any</span>';
        if (noProfile.length) h += ' <span style="color:var(--orange);font-weight:400;">— '+noProfile.length+' uten sikkerhetsprofil</span>';
        h += '</div>';
        h += '<div style="overflow-x:auto;"><table style="width:100%;font-size:10px;border-collapse:collapse;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:3px;">#</th><th style="text-align:left;padding:3px;">' + t('navn_4') + '</th><th style="text-align:left;padding:3px;">' + t('inn') + '</th><th style="text-align:left;padding:3px;">' + t('ut') + '</th><th style="text-align:left;padding:3px;">' + t('kilde') + '</th><th style="text-align:left;padding:3px;">' + t('dest') + '</th><th style="text-align:left;padding:3px;">' + t('tjeneste_3') + '</th><th>' + t('aksjon') + '</th><th>NAT</th><th>' + t('logg') + '</th><th style="text-align:left;padding:3px;">' + t('sikkerhet') + '</th></tr></thead><tbody>';
        ex.policies.forEach(function(p) {
          if (p.enabled === false) return; // skip disabled
          var isBad = (p.action==='accept'&&p.src==='all'&&p.dst==='all'&&p.svc==='ALL');
          var noProf = (p.action==='accept'&&(!p.profiles||!p.profiles.length));
          var isDeny = (p.action==='deny');
          var rowBg = isBad ? 'background:rgba(255,0,0,0.06);' : isDeny ? 'background:rgba(63,185,80,0.04);' : noProf ? 'background:rgba(255,165,0,0.04);' : '';
          var logColor = (p.log==='all'||p.log==='utm') ? 'var(--green)' : p.action==='deny' ? 'var(--text-muted)' : 'var(--red)';
          var profHtml = isDeny ? '<span style="color:var(--green);">' + t('segmentering') + '</span>' : (p.profiles&&p.profiles.length) ? p.profiles.map(function(pr){return '<span style="background:rgba(77,159,181,0.15);padding:1px 4px;border-radius:3px;margin:1px;">'+esc(pr)+'</span>';}).join(' ') : '<span style="color:var(--orange);">' + t('ingen_2') + '</span>';
          h += '<tr style="border-bottom:1px solid var(--border);'+rowBg+'">';
          h += '<td style="padding:3px;">'+p.id+'</td>';
          h += '<td style="padding:3px;font-weight:500;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+esc(p.name)+'</td>';
          h += '<td style="padding:3px;font-size:9px;">'+esc(p.srcintf||'')+'</td>';
          h += '<td style="padding:3px;font-size:9px;">'+esc(p.dstintf||'')+'</td>';
          h += '<td style="padding:3px;font-size:9px;max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="'+esc(p.src)+'">'+esc(p.src)+'</td>';
          h += '<td style="padding:3px;font-size:9px;max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="'+esc(p.dst)+'">'+esc(p.dst)+'</td>';
          h += '<td style="padding:3px;font-size:9px;">'+esc(p.svc)+'</td>';
          var actionColor = p.action==='deny' ? 'var(--green)' : isBad ? 'var(--red)' : 'var(--text)';
          h += '<td style="padding:3px;text-align:center;color:'+actionColor+';font-weight:500;">'+(p.action||'accept')+'</td>';
          h += '<td style="padding:3px;text-align:center;">'+(p.nat?'✓':'')+'</td>';
          h += '<td style="padding:3px;text-align:center;color:'+logColor+';">'+esc(p.log||'-')+'</td>';
          h += '<td style="padding:3px;font-size:9px;">'+profHtml+'</td>';
          h += '</tr>';
        });
        h += '</tbody></table></div>';
      }

      // Static routes
      if (ex.static_routes && ex.static_routes.length) {
        h += '<div style="font-size:12px;font-weight:600;margin:12px 0 6px;">Statiske ruter ('+ex.static_routes.length+')</div>';
        h += '<table style="width:100%;font-size:11px;border-collapse:collapse;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:4px;">' + t('destinasjon') + '</th><th>' + t('gateway_2') + '</th><th>' + t('interface') + '</th><th>' + t('distanse') + '</th></tr></thead><tbody>';
        ex.static_routes.forEach(function(r) {
          h += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px;font-family:var(--mono);font-size:10px;">'+esc(r.dst)+'</td><td style="padding:4px;font-family:var(--mono);font-size:10px;">'+esc(r.gateway)+'</td><td style="padding:4px;">'+esc(r.device)+'</td><td style="padding:4px;">'+r.distance+'</td></tr>';
        });
        h += '</tbody></table>';
      }

      // SD-WAN status
      if (ex.sdwan && ex.sdwan.members && ex.sdwan.members.length) {
        h += '<div style="font-size:12px;font-weight:600;margin:12px 0 6px;">SD-WAN</div>';
        h += '<table style="width:100%;font-size:11px;border-collapse:collapse;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:4px;">' + t('interface') + '</th><th>' + t('status_3') + '</th><th>' + t('latency') + '</th><th>' + t('jitter') + '</th><th>' + t('pakketap') + '</th></tr></thead><tbody>';
        ex.sdwan.members.forEach(function(m) {
          var sColor = m.status==='up'||m.status==='alive' ? 'var(--green)' : 'var(--red)';
          var plColor = m.packet_loss > 1 ? 'var(--red)' : 'var(--green)';
          h += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px;font-weight:500;">'+esc(m.interface)+'</td><td style="padding:4px;color:'+sColor+';">'+(m.status||'-')+'</td><td style="padding:4px;">'+(m.latency?m.latency.toFixed(1)+'ms':'-')+'</td><td style="padding:4px;">'+(m.jitter?m.jitter.toFixed(1)+'ms':'-')+'</td><td style="padding:4px;color:'+plColor+';">'+(m.packet_loss?m.packet_loss.toFixed(1)+'%':'0%')+'</td></tr>';
        });
        h += '</tbody></table>';
      }

      // DHCP, DNS, Admins, FortiGuard licenses, Log stats
      h += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-top:12px;">';

      if (ex.dhcp && ex.dhcp.length) {
        h += '<div class="card" style="padding:10px;"><div style="font-size:11px;font-weight:600;margin-bottom:4px;">DHCP ('+ex.dhcp.length+')</div>';
        ex.dhcp.forEach(function(d2){h += '<div style="font-size:10px;color:var(--text-muted);padding:2px 0;"><strong>'+esc(d2.interface)+'</strong>: '+esc(d2.range)+'</div>';});
        h += '</div>';
      }
      if (ex.dns && ex.dns.primary) {
        h += '<div class="card" style="padding:10px;"><div style="font-size:11px;font-weight:600;margin-bottom:4px;">DNS</div>';
        h += '<div style="font-size:10px;color:var(--text-muted);">' + t('primaer') + ' <strong>'+esc(ex.dns.primary)+'</strong></div>';
        if (ex.dns.secondary) h += '<div style="font-size:10px;color:var(--text-muted);">Sekundær: '+esc(ex.dns.secondary)+'</div>';
        h += '</div>';
      }
      if (ex.admins && ex.admins.length) {
        h += '<div class="card" style="padding:10px;"><div style="font-size:11px;font-weight:600;margin-bottom:4px;">Admin-kontoer ('+ex.admins.length+')</div>';
        ex.admins.forEach(function(a){
          var warns = [];
          if (!a.two_factor) warns.push('ingen 2FA');
          if (!a.trusthost) warns.push('ingen trusthost');
          var warnHtml = warns.length ? ' <span style="color:var(--orange);font-size:9px;">⚠ '+warns.join(', ')+'</span>' : '';
          h += '<div style="font-size:10px;color:var(--text-muted);padding:2px 0;"><strong>'+esc(a.name||'-')+'</strong>'+(a.profile?' ('+esc(a.profile)+')':'')+warnHtml+'</div>';
        });
        h += '</div>';
      }
      if (ex.license_expiry && Object.keys(ex.license_expiry).length) {
        h += '<div class="card" style="padding:10px;"><div style="font-size:11px;font-weight:600;margin-bottom:4px;">' + t('fortiguard_lisenser') + '</div>';
        Object.keys(ex.license_expiry).forEach(function(k) {
          var lic = ex.license_expiry[k];
          var expDate = lic.expires ? new Date(lic.expires * 1000) : null;
          var daysLeft = expDate ? Math.floor((expDate - new Date()) / 86400000) : null;
          var color = daysLeft === null ? 'var(--text-muted)' : daysLeft < 30 ? 'var(--red)' : daysLeft < 90 ? 'var(--orange)' : 'var(--green)';
          h += '<div style="font-size:10px;padding:2px 0;display:flex;justify-content:space-between;"><span>'+esc(k)+'</span><span style="color:'+color+';">'+(expDate?expDate.toLocaleDateString('no-NO'):'—')+'</span></div>';
        });
        h += '</div>';
      }
      if (ex.log_stats && ex.log_stats.total_bytes) {
        var logPct = ex.log_stats.used_pct || 0;
        var logColor = logPct > 90 ? 'var(--red)' : logPct > 70 ? 'var(--orange)' : 'var(--green)';
        h += '<div class="card" style="padding:10px;"><div style="font-size:11px;font-weight:600;margin-bottom:4px;">' + t('logg_lagring') + '</div>';
        h += '<div style="font-size:16px;font-weight:700;color:'+logColor+';">'+logPct+'%</div>';
        h += '<div style="font-size:10px;color:var(--text-muted);">' + t('brukt_2') + '</div>';
        h += '</div>';
      }

      h += '</div>';

      if (dev.last_poll) h += '<div style="font-size:10px;color:var(--text-dim);margin-top:8px;">Sist pollet: '+new Date(dev.last_poll).toLocaleString('no-NO')+'</div>';
      h += '</div>';
    }

    h += '</div>';
    panel.innerHTML = h;
  });
}

// ═══════════════════════════════════════════════════════════════════
// CLAUDE AI INTEGRATION
// ═══════════════════════════════════════════════════════════════════

async function claudeLoadSaved() {
  var data = await apiFetch('/api/claude/status');
  if (!data) return;
  var dot = document.getElementById('claude-integ-dot');
  var label = document.getElementById('claude-integ-label');
  if (data.available) {
    dot.style.background = 'var(--green)';
    label.textContent = data.model || t('lbl_connected','Connected');
    label.style.color = 'var(--green)';
  } else if (data.api_key_configured) {
    dot.style.background = 'var(--orange)';
    label.textContent = t('lbl_key_saved_sdk_missing','Key saved, but SDK missing');
    label.style.color = 'var(--orange)';
  } else {
    dot.style.background = 'var(--text-dim)';
    label.textContent = t('lbl_not_configured','Not configured');
    label.style.color = 'var(--text-muted)';
  }
}

function claudeModeChanged() {
  var mode = document.getElementById('claude-mode').value;
  document.getElementById('claude-mode-api').style.display = mode === 'api' ? 'block' : 'none';
  document.getElementById('claude-mode-cli').style.display = mode === 'cli' ? 'block' : 'none';
  if (mode === 'cli') claudeCheckCli();
}

async function claudeCheckCli() {
  var el = document.getElementById('claude-cli-status');
  el.textContent = 'Sjekker...';
  var data = await apiFetch('/api/claude/cli-status');
  if (data && data.available) {
    el.innerHTML = '<span style="color:var(--green);">✓ Claude CLI funnet — ' + data.version + '</span>';
  } else {
    el.innerHTML = '<span style="color:var(--red);">✗ ' + (data && data.error ? data.error : 'Claude CLI ikke funnet') + '</span><br><span style="font-size:11px;color:var(--text-dim);">Installer: npm install -g @anthropic-ai/claude-code</span>';
  }
}

async function claudeSaveSettings() {
  var mode = document.getElementById('claude-mode').value;
  var key = document.getElementById('claude-api-key').value.trim();
  var model = document.getElementById('claude-model').value;
  var msg = document.getElementById('claude-save-msg');
  if (mode === 'api' && !key) { msg.innerHTML = '<span style="color:var(--red);">' + t('err_fill_api_key','Enter API key') + '</span>'; return; }
  var data = await apiFetch('/api/claude/settings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:key, mode:mode, model:model})});
  if (data && data.ok) {
    msg.innerHTML = '<span style="color:var(--green);">' + t('lagret_3') + '</span>';
    claudeLoadSaved();
  } else {
    msg.innerHTML = '<span style="color:var(--red);">'+(data&&data.error||t('status_error','Error'))+'</span>';
  }
}

async function claudeTestConnection() {
  var msg = document.getElementById('claude-save-msg');
  msg.textContent = t('msg_testing','Testing...');
  var data = await apiFetch('/api/claude/status');
  if (data && data.available) {
    msg.innerHTML = '<span style="color:var(--green);">' + t('lbl_connected','Connected') + ' — '+data.model+'</span>';
  } else {
    msg.innerHTML = '<span style="color:var(--red);">'+(data && !data.sdk_installed ? t('err_anthropic_not_installed','anthropic package not installed') : t('err_api_key_missing_invalid','API key missing or invalid'))+'</span>';
  }
}

// ═══════════════════════════════════════════════════════════════════
// FORTIGATE REST API INTEGRATION
// ═══════════════════════════════════════════════════════════════════

async function fgBootstrap() {
  var host = document.getElementById('fg-bootstrap-host').value.trim();
  var hostname = document.getElementById('fg-bootstrap-hostname').value.trim();
  var btn = document.getElementById('btn-fg-bootstrap');
  var status = document.getElementById('fg-bootstrap-status');
  var resultBox = document.getElementById('fg-bootstrap-result');

  if (!host) { showToast(t('angi_fortigate_ip_adresse'), 'warning'); return; }

  btn.disabled = true;
  status.textContent = 'Kobler til ' + host + ' med fabrikkinnstillinger...';
  resultBox.style.display = 'none';

  try {
    var d = await apiFetch('/api/fortigate/bootstrap', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({host: host, hostname: hostname || undefined})
    });

    if (d && d.ok) {
      status.innerHTML = '<span style="color:var(--green);font-weight:600;">' + t('ferdig') + '</span>';
      resultBox.style.display = 'block';
      resultBox.innerHTML =
        '<div style="font-weight:600;font-size:13px;margin-bottom:8px;color:var(--green);">' + t('fortigate_konfigurert') + '</div>' +
        '<table style="width:100%;font-size:12px;border-collapse:collapse;">' +
        '<tr><td style="padding:4px 8px;font-weight:600;white-space:nowrap;">' + t('host_2') + '</td><td style="padding:4px 8px;font-family:var(--mono);">' + esc(d.host) + '</td></tr>' +
        '<tr><td style="padding:4px 8px;font-weight:600;white-space:nowrap;">' + t('admin_passord') + '</td><td style="padding:4px 8px;"><code style="background:var(--bg);padding:2px 6px;border-radius:4px;user-select:all;font-size:13px;font-weight:600;">' + esc(d.admin_password) + '</code></td></tr>' +
        '<tr><td style="padding:4px 8px;font-weight:600;white-space:nowrap;">' + t('api_bruker') + '</td><td style="padding:4px 8px;font-family:var(--mono);">' + esc(d.api_admin) + '</td></tr>' +
        '<tr><td style="padding:4px 8px;font-weight:600;white-space:nowrap;">' + t('api_token_2') + '</td><td style="padding:4px 8px;"><code style="background:var(--bg);padding:2px 6px;border-radius:4px;user-select:all;font-size:13px;font-weight:600;">' + esc(d.api_token) + '</code></td></tr>' +
        '</table>' +
        '<div style="margin-top:10px;display:flex;gap:8px;">' +
        '<button class="btn btn-primary" style="font-size:11px;padding:4px 12px;" onclick="fgBootstrapAutoFill(\'' + esc(d.host) + '\',\'' + esc(d.api_token) + '\')">' + t('fyll_inn_og_lagre') + '</button>' +
        '<button class="btn btn-default" style="font-size:11px;padding:4px 12px;" onclick="navigator.clipboard.writeText(\'' + esc(d.api_token) + '\');showToast(\'API-token kopiert\',\'success\')">' + t('kopier_token') + '</button>' +
        '</div>' +
        '<div style="margin-top:8px;font-size:11px;color:var(--green);">' + (d.persisted ? t('msg_creds_in_keyring') : t('msg_creds_not_persisted') + (d.persist_error ? ' (' + esc(d.persist_error) + ')' : '') + ' ' + t('msg_save_password_now')) + '</div>';

      showToast(t('fortigate_bootstrap_fullfoert'), 'success', 6000);
    } else {
      status.innerHTML = '<span style="color:var(--red);">' + esc(d && d.error ? d.error : 'Bootstrap feilet') + '</span>';
      if (d && d.steps) {
        status.innerHTML += '<br><span style="font-size:10px;color:var(--text-dim);">Steg: ' + esc(d.steps.join(' → ')) + '</span>';
      }
      // Show password if it was set (partial success)
      if (d && d.admin_password && d.steps && d.steps.some(function(s) { return s.startsWith('password_set') || s.startsWith('reconnect'); })) {
        resultBox.style.display = 'block';
        var html = '<div style="font-weight:600;font-size:13px;margin-bottom:8px;color:var(--orange);">' + t('delvis_fullfoert_passord_ble_satt') + '</div>';
        html += '<table style="width:100%;font-size:12px;border-collapse:collapse;">';
        html += '<tr><td style="padding:4px 8px;font-weight:600;">' + t('host_2') + '</td><td style="padding:4px 8px;font-family:var(--mono);">' + esc(d.host) + '</td></tr>';
        html += '<tr><td style="padding:4px 8px;font-weight:600;">' + t('admin_passord') + '</td><td style="padding:4px 8px;"><code style="background:var(--bg);padding:2px 6px;border-radius:4px;user-select:all;font-size:13px;font-weight:600;">' + esc(d.admin_password) + '</code></td></tr>';
        if (d.api_admin) html += '<tr><td style="padding:4px 8px;font-weight:600;">' + t('api_bruker') + '</td><td style="padding:4px 8px;font-family:var(--mono);">' + esc(d.api_admin) + '</td></tr>';
        html += '</table>';
        if (d.raw_output) {
          html += '<div style="margin-top:8px;font-size:11px;color:var(--text-dim);"><strong>' + t('debug_output') + '</strong><pre style="max-height:150px;overflow:auto;padding:6px;background:var(--bg);border:1px solid var(--border);border-radius:4px;font-size:10px;margin-top:4px;">' + esc(d.raw_output) + '</pre></div>';
        }
        html += '<div style="margin-top:8px;font-size:11px;color:var(--orange);">' + t('lagre_passordet_opprett_api_noekkel_manu') + '</div>';
        resultBox.innerHTML = html;
      }
    }
  } catch (e) {
    status.innerHTML = '<span style="color:var(--red);">' + esc(e.message) + '</span>';
  } finally {
    btn.disabled = false;
  }
}

function fgBootstrapAutoFill(host, token) {
  document.getElementById('fg-api-host').value = host;
  document.getElementById('fg-api-token').value = token;
  // Bootstrap hardens admin-sport to 8443 (CIS) — match it in the saved config
  document.getElementById('fg-api-port').value = '8443';
  fgApiSave();
}

async function fgDownloadCredentials() {
  var active = window.activeCustomerId || (window.appState && window.appState.activeCustomerId);
  if (!active) {
    try {
      var st = await apiFetch('/api/customers/active');
      active = st && st._id;
    } catch (e) {}
  }
  if (!active) { showToast(t('err_no_active_customer'), 'warning'); return; }

  try {
    var d = await apiFetch('/api/fortigate/credentials/' + encodeURIComponent(active));
    if (!d || !d.ok) { showToast(t('ingen_lagrede_credentials'), 'warning'); return; }

    var lines = [
      '# FortiGate credentials',
      '# Kunde:        ' + (d.customer_name || ''),
      '# Generert:     ' + (d.bootstrapped_at || '(ukjent)'),
      '# Lastet ned:   ' + new Date().toISOString(),
      '#',
      '# ADVARSEL: Inneholder hemmeligheter. Slett etter bruk eller lagre kryptert.',
      '',
      'Host:           ' + (d.host || ''),
      'Port (HTTPS):   ' + (d.port || 8443),
      'Admin URL:      https://' + (d.host || '') + ':' + (d.port || 8443),
      '',
      'Admin user:     ' + (d.admin_user || 'admin'),
      'Admin password: ' + (d.admin_password || '(ikke lagret)'),
      '',
      'API user:       ' + (d.api_user || 'msp_api_admin'),
      'API token:      ' + (d.api_token || '(ikke lagret)'),
      ''
    ];
    var blob = new Blob([lines.join('\n')], {type: 'text/plain;charset=utf-8'});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    var safe = (d.customer_name || 'fortigate').replace(/[^A-Za-z0-9_\-]/g, '_');
    a.href = url;
    a.download = 'fortigate-credentials-' + safe + '.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(t('credentials_lastet_ned'), 'success');
  } catch (e) {
    showToast(e.message || 'Kunne ikke hente credentials', 'error');
  }
}

async function fgApiTest() {
  var host = document.getElementById('fg-api-host').value.trim();
  var port = document.getElementById('fg-api-port').value || '443';
  var token = document.getElementById('fg-api-token').value.trim();
  var vdom = document.getElementById('fg-api-vdom').value.trim() || 'root';
  var result = document.getElementById('fg-api-test-result');

  if (!host || !token) { result.innerHTML = '<span style="color:var(--red);">' + t('err_host_token_required','Host and token are required') + '</span>'; return; }
  result.textContent = t('msg_testing','Testing...');

  var data = await apiFetch('/api/fortigate/test', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({host:host, port:parseInt(port), api_token:token, vdom:vdom})});
  if (data && data.ok) {
    var info = data.hostname ? ' — ' + data.hostname + ' (' + (data.firmware || '') + ')' : '';
    result.innerHTML = '<span style="color:var(--green);">' + t('lbl_connected','Connected') + '!' + info + '</span>';
    document.getElementById('fg-integ-dot').style.background = 'var(--green)';
    document.getElementById('fg-integ-label').textContent = t('lbl_connected','Connected');
    document.getElementById('fg-integ-label').style.color = 'var(--green)';
  } else {
    result.innerHTML = '<span style="color:var(--red);">' + (data && data.error ? data.error : t('err_connection_failed','Connection failed')) + '</span>';
  }
}

async function fgApiSave() {
  var host = document.getElementById('fg-api-host').value.trim();
  var port = document.getElementById('fg-api-port').value || '443';
  var token = document.getElementById('fg-api-token').value.trim();
  var vdom = document.getElementById('fg-api-vdom').value.trim() || 'root';

  if (!host || !token) { showToast(t('err_host_token_required','Host and token are required'), 'error'); return; }

  // Save to active customer if one exists, otherwise to global settings
  var status = await apiFetch('/api/status');
  if (status && status.active_id) {
    var data = await apiFetch('/api/fortigate/save', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({host:host, port:parseInt(port), api_token:token, vdom:vdom})});
    if (data && data.ok) {
      showToast(t('msg_fortigate_config_saved','FortiGate config saved for active customer'), 'success');
      document.getElementById('fg-api-save-msg').innerHTML = '<span style="color:var(--green);">' + t('lbl_saved','Saved') + '</span>';
    }
  } else {
    showToast(t('err_select_customer_first','Select an active customer first to save FortiGate config'), 'error');
  }
}

async function fgApiLoadSaved() {
  var data = await apiFetch('/api/network-devices');
  if (data && data.fortigate) {
    var fg = data.fortigate;
    document.getElementById('fg-api-host').value = fg.host || '';
    document.getElementById('fg-api-port').value = fg.port || 443;
    document.getElementById('fg-api-vdom').value = fg.vdom || 'root';
    if (fg.has_token) {
      document.getElementById('fg-api-token').placeholder = t('placeholder_token_saved','Token saved — leave blank to keep');
      document.getElementById('fg-integ-dot').style.background = 'var(--blue)';
      document.getElementById('fg-integ-label').textContent = fg.host;
      document.getElementById('fg-integ-label').style.color = 'var(--blue)';
    }
  }
}

// ═══════════════════════════════════════════════════════════════════
// DASHBOARD SUB-TABS
// ═══════════════════════════════════════════════════════════════════

function switchDashTab(btn, tabId) {
  document.querySelectorAll('.dash-tab-content').forEach(function(el) { el.style.display = 'none'; });
  // Active state is CSS-driven now (.dash-tab-btn.active); just toggle the class.
  document.querySelectorAll('.dash-tab-btn').forEach(function(b) { b.classList.remove('active'); });
  var tab = document.getElementById(tabId);
  if (tab) tab.style.display = 'block';
  btn.classList.add('active');

  if (tabId === 'dash-renewals') dashLoadRenewals();
  if (tabId === 'dash-alerts') dashLoadAlerts();
  if (tabId === 'dash-health') dashLoadHealth();
  if (tabId === 'dash-costs') dashLoadCosts();
  if (tabId === 'dash-domains') dashLoadDomains();
  if (tabId === 'dash-archive') dashLoadArchive();
}

async function dashUnifiRefresh() {
  document.querySelectorAll('.unifi-detail-panel').forEach(function(p) { p.remove(); });
  await dashLoadUnifiAll();
}

async function dashLoadUnifiAll() {
  var el = document.getElementById('dash-unifi-content');
  if (!el) return;
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';

  var data = await apiFetch('/api/unifi/all');
  if (!data) { el.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:48px;">' + t('kunne_ikke_hente_unifi_data') + '</div>'; return; }

  var devices = data.devices || [];
  var summary = data.summary || {};

  if (!devices.length && !summary.configured_customers) {
    el.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:48px;">Ingen UniFi-enheter konfigurert. Legg til under Integrasjoner per kunde.</div>';
    return;
  }

  // KPI cards
  var html = '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:'Enheter', value:summary.total_devices||0, sub:(summary.online||0)+' online', color:'var(--blue)'},
    {label:'Online', value:summary.online||0, sub:summary.offline?summary.offline+' offline':'alle oppe', color:summary.offline?'var(--orange)':'var(--green)'},
    {label:'Klienter', value:summary.total_clients||0, sub:'tilkoblet', color:'var(--purple)'},
    {label:'Kunder', value:summary.configured_customers||0, sub:'med UniFi', color:'var(--text-muted)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card" style="padding:16px 8px;text-align:center;border-top:2px solid '+k.color+';"><div style="font-size:20px;font-weight:700;">'+k.value+'</div><div style="font-size:11px;color:var(--text-muted);">'+k.label+'</div><div style="font-size:10px;color:var(--text-dim);">'+k.sub+'</div></div>';
  });
  html += '</div>';

  // Store globally for detail panel
  window._unifiDevices = devices;

  // Device cards
  if (devices.length) {
    html += '<div id="unifi-cards-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(350px,1fr));gap:12px;">';
    devices.forEach(function(d, idx) {
      var color = d.status === 'online' ? 'var(--green)' : 'var(--red)';
      html += '<div class="card" style="padding:14px;border-left:3px solid '+color+';cursor:pointer;display:grid;grid-template-rows:24px 20px 1fr;height:100%;" onclick="dashUnifiDetail('+idx+')">';

      // ROW 1 — Header
      html += '<div style="display:flex;align-items:center;height:24px;overflow:hidden;">';
      html += '<span style="width:8px;height:8px;border-radius:50%;background:'+color+';flex-shrink:0;"></span>';
      html += '<strong style="flex:1;font-size:14px;margin-left:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">📡 '+esc(d.name||'-')+'</strong>';
      if (d.source === 'site_manager') html += '<span style="font-size:10px;background:var(--blue);color:#fff;padding:1px 6px;border-radius:8px;flex-shrink:0;">' + t('cloud') + '</span>';
      html += '</div>';

      // ROW 2 — Subtitle
      html += '<div style="font-size:11px;color:var(--text-muted);line-height:20px;height:20px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+esc(d.customer_name||d.model_full||d.model||'')+'</div>';

      // ROW 3 — Stats grid (enriched)
      html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:3px;font-size:12px;color:var(--text-muted);align-content:start;padding-top:6px;">';
      html += '<span>' + t('modell') + ' <strong style="color:var(--text);">'+(d.model||'-')+'</strong></span>';
      html += '<span>FW: '+(d.firmware||'-')+'</span>';
      html += '<span>' + t('klienter') + ' <strong>'+(d.clients!=null?d.clients:'-')+'</strong></span>';
      if (d.source === 'site_manager') {
        html += '<span>' + t('enheter') + ' <strong>'+(d.device_count||0)+'</strong>'+(d.offline_devices?' <span style="color:var(--red);">('+d.offline_devices+' off)</span>':'')+'</span>';
        html += '<span>Sites: '+(d.site_count||0)+'</span>';
        if (d.ip) html += '<span>' + t('wan') + ' <code style="font-size:11px;">'+esc(d.ip)+'</code></span>';
        if (d.isp) html += '<span>ISP: '+esc(d.isp)+'</span>';
        if (d.uptime) html += '<span>Uptime: '+_formatUptime(d.uptime)+'</span>';
        // Aggregate alerts from sub_sites
        var cardCrit = 0;
        if (d.sub_sites) d.sub_sites.forEach(function(ss) { cardCrit += ss.critical_notifications||0; });
        if (cardCrit) html += '<span style="color:var(--red);grid-column:1/-1;">⚠ '+cardCrit+' kritiske varsler</span>';
        if (d.firmware_update) html += '<span style="color:var(--orange);grid-column:1/-1;">⬆ '+esc(d.firmware_update)+'</span>';
      } else {
        html += '<span>Uptime: '+(d.uptime?_formatUptime(d.uptime):'-')+'</span>';
        if (d.upgrade_available) html += '<span style="color:var(--orange);grid-column:1/-1;">⬆ '+esc(d.upgrade_available)+'</span>';
      }
      html += '</div>';

      if (d.last_poll) html += '<div style="font-size:10px;color:var(--text-dim);margin-top:6px;">Pollet: '+new Date(d.last_poll).toLocaleTimeString('no-NO')+'</div>';
      html += '</div>';
    });
    html += '</div>';
  } else {
    html += '<div style="color:var(--text-muted);text-align:center;padding:24px;">'+summary.configured_customers+' ' + t('msg_customers_awaiting_data') + '</div>';
  }

  el.innerHTML = html;
  var statusEl = document.getElementById('unifi-live-status');
  if (statusEl) statusEl.textContent = t('msg_last_updated','Sist oppdatert') + ': ' + new Date().toLocaleTimeString('no-NO');
}

function dashUnifiDetail(idx) {
  var d = (window._unifiDevices || [])[idx];
  if (!d) return;
  var panelId = 'unifi-detail-' + idx;

  var existing = document.getElementById(panelId);
  if (existing) { existing.remove(); return; }
  document.querySelectorAll('.unifi-detail-panel').forEach(function(p) { p.remove(); });

  var el = document.getElementById('dash-unifi-content');
  var panel = document.createElement('div');
  panel.id = panelId;
  panel.className = 'unifi-detail-panel';
  panel.style.cssText = 'margin-top:16px;margin-bottom:16px;';

  var color = d.status === 'online' ? 'var(--green)' : 'var(--red)';
  var h = '<div class="card" style="padding:20px;border-left:3px solid '+color+';">';

  // Header
  h += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">';
  h += '<div style="font-size:16px;font-weight:700;">📡 '+esc(d.name||'-');
  if (d.source === 'site_manager') h += ' <span style="font-size:11px;background:var(--blue);color:#fff;padding:2px 8px;border-radius:8px;vertical-align:middle;">' + t('cloud') + '</span>';
  h += '</div>';
  h += '<button class="btn btn-ghost" onclick="document.getElementById(\''+panelId+'\').remove()" style="padding:2px 8px;font-size:11px;">'+t('btn_close','Lukk')+'</button>';
  h += '</div>';

  // ── Console info grid ──
  h += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px 20px;font-size:13px;margin-bottom:16px;">';
  h += '<div><span style="color:var(--text-muted);">' + t('status_3') + '</span> <strong style="color:'+color+';">'+(d.status==='online'?'Online':'Offline')+'</strong></div>';
  h += '<div><span style="color:var(--text-muted);">' + t('modell') + '</span> <strong>'+esc(d.model_full||d.model||'-')+'</strong></div>';
  h += '<div><span style="color:var(--text-muted);">' + t('firmware_2') + '</span> '+esc(d.firmware||'-')+'</div>';
  if (d.app_version) h += '<div><span style="color:var(--text-muted);">' + t('app_versjon') + '</span> '+esc(d.app_version)+'</div>';
  if (d.ip) h += '<div><span style="color:var(--text-muted);">' + t('wan_ip') + '</span> <code style="font-size:12px;">'+esc(d.ip)+'</code></div>';
  if (d.mac) h += '<div><span style="color:var(--text-muted);">' + t('mac') + '</span> <code style="font-size:12px;">'+esc(d.mac)+'</code></div>';
  if (d.serial) h += '<div><span style="color:var(--text-muted);">' + t('serienr') + '</span> <code style="font-size:12px;">'+esc(d.serial)+'</code></div>';
  if (d.isp) h += '<div><span style="color:var(--text-muted);">' + t('isp') + '</span> '+esc(d.isp)+'</div>';
  if (d.uptime) h += '<div><span style="color:var(--text-muted);">' + t('uptime') + '</span> '+_formatUptime(d.uptime)+'</div>';
  if (d.timezone) h += '<div><span style="color:var(--text-muted);">' + t('tidssone') + '</span> '+esc(d.timezone)+'</div>';
  if (d.release_channel) h += '<div><span style="color:var(--text-muted);">' + t('kanal') + '</span> '+esc(d.release_channel)+'</div>';
  if (d.version) h += '<div><span style="color:var(--text-muted);">' + t('unifi_os') + '</span> '+esc(d.version)+'</div>';
  if (d.hostname) h += '<div><span style="color:var(--text-muted);">' + t('hostname') + '</span> '+esc(d.hostname)+'</div>';
  if (d.internal_ip) h += '<div><span style="color:var(--text-muted);">' + t('intern_ip') + '</span> <code style="font-size:12px;">'+esc(d.internal_ip)+'</code></div>';
  if (d.direct_connect_domain) h += '<div><span style="color:var(--text-muted);">' + t('direct_connect') + '</span> <code style="font-size:11px;">'+esc(d.direct_connect_domain)+'</code></div>';
  if (d.country) h += '<div><span style="color:var(--text-muted);">' + t('land') + '</span> '+esc(d.country)+'</div>';
  if (d.cpu_id) h += '<div><span style="color:var(--text-muted);">' + t('cpu') + '</span> '+esc(d.cpu_id)+'</div>';
  if (d.firmware_update) h += '<div><span style="color:var(--orange);">' + t('fw_oppdatering') + '</span> '+esc(d.firmware_update)+'</div>';
  if (d.unadopted_devices) h += '<div><span style="color:var(--orange);">' + t('uadopterte_enheter') + '</span> '+d.unadopted_devices+'</div>';
  if (d.device_error) h += '<div><span style="color:var(--red);">' + t('feilkode') + '</span> '+d.device_error+'</div>';
  if (d.is_blocked) h += '<div><span style="color:var(--red);font-weight:600;">' + t('blokkert') + '</span></div>';
  h += '</div>';

  // ── KPI row ──
  h += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px;margin-bottom:16px;">';
  var kpis = [
    {l:'Enheter', v:d.device_count||0, c:'var(--blue)'},
    {l:'Klienter', v:d.clients||0, c:'var(--purple)'},
    {l:'Sites', v:d.site_count||0, c:'var(--text-muted)'},
  ];
  if (d.offline_devices) kpis.push({l:'Offline', v:d.offline_devices, c:'var(--red)'});
  kpis.forEach(function(k) {
    h += '<div style="text-align:center;padding:10px 6px;background:var(--bg-input);border-radius:6px;border-top:2px solid '+k.c+';">';
    h += '<div style="font-size:18px;font-weight:700;">'+k.v+'</div>';
    h += '<div style="font-size:11px;color:var(--text-muted);">'+k.l+'</div></div>';
  });
  h += '</div>';

  // ── Timestamps ──
  if (d.registered || d.last_backup || d.last_connection) {
    h += '<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:var(--text-dim);margin-bottom:16px;">';
    if (d.registered) h += '<span>Registrert: '+new Date(d.registered).toLocaleDateString('no-NO')+'</span>';
    if (d.last_backup) h += '<span>Siste backup: '+new Date(d.last_backup).toLocaleString('no-NO')+'</span>';
    if (d.last_connection) h += '<span>Siste tilkobling: '+new Date(d.last_connection).toLocaleString('no-NO')+'</span>';
    h += '</div>';
  }

  // ── Sub-sites table ──
  if (d.sub_sites && d.sub_sites.length) {
    h += '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">Sites ('+d.sub_sites.length+')</div>';
    h += '<div style="overflow-x:auto;">';
    h += '<table style="width:100%;border-collapse:collapse;font-size:12px;min-width:900px;">';
    h += '<thead><tr style="border-bottom:2px solid var(--border);color:var(--text-muted);font-size:11px;">';
    h += '<th style="text-align:left;padding:6px 8px;">' + t('site_2') + '</th>';
    h += '<th style="text-align:center;padding:6px 4px;">' + t('enheter') + '</th>';
    h += '<th style="text-align:center;padding:6px 4px;">' + t('klienter') + '</th>';
    h += '<th style="text-align:center;padding:6px 4px;">' + t('wifi') + '</th>';
    h += '<th style="text-align:center;padding:6px 4px;">' + t('wan_up') + '</th>';
    h += '<th style="text-align:center;padding:6px 4px;">' + t('gjester') + '</th>';
    h += '<th style="text-align:center;padding:6px 4px;">' + t('offline_2') + '</th>';
    h += '<th style="text-align:center;padding:6px 4px;">' + t('oppd') + '</th>';
    h += '<th style="text-align:center;padding:6px 4px;">WAN</th>';
    h += '<th style="text-align:center;padding:6px 4px;">' + t('varsler_3') + '</th>';
    h += '<th style="text-align:left;padding:6px 4px;">' + t('gateway_2') + '</th>';
    h += '<th style="text-align:left;padding:6px 4px;">ISP</th>';
    h += '</tr></thead><tbody>';

    d.sub_sites.forEach(function(s) {
      var warn = s.offline_devices || s.critical_notifications || s.alert_count;
      var rowStyle = warn ? 'background:rgba(255,100,100,0.04);' : '';
      h += '<tr style="border-bottom:1px solid var(--border);'+rowStyle+'">';
      h += '<td style="padding:5px 8px;font-weight:500;">'+esc(s.name)+'</td>';
      h += '<td style="text-align:center;padding:5px 4px;">'+s.device_count+'</td>';
      h += '<td style="text-align:center;padding:5px 4px;"><strong>'+s.client_count+'</strong> <span style="font-size:10px;color:var(--text-dim);">('+s.wifi_clients+'W/'+s.wired_clients+'E)</span></td>';
      h += '<td style="text-align:center;padding:5px 4px;">'+s.wifi_networks+' SSID</td>';
      var wup = s.wan_uptime_pct||0;
      var wupColor = wup >= 99 ? 'var(--green)' : wup >= 95 ? 'var(--orange)' : wup > 0 ? 'var(--red)' : 'var(--text-dim)';
      h += '<td style="text-align:center;padding:5px 4px;"><span style="color:'+wupColor+';font-weight:600;">'+(wup?wup+'%':'-')+'</span></td>';
      h += '<td style="text-align:center;padding:5px 4px;">'+(s.guest_count||0)+'</td>';
      h += '<td style="text-align:center;padding:5px 4px;">'+(s.offline_devices?'<span style="color:var(--red);font-weight:600;">'+s.offline_devices+'</span>':'0')+'</td>';
      h += '<td style="text-align:center;padding:5px 4px;">'+(s.pending_updates?'<span style="color:var(--orange);">'+s.pending_updates+'</span>':'0')+'</td>';
      h += '<td style="text-align:center;padding:5px 4px;">'+(s.wan_interfaces||0)+'</td>';
      h += '<td style="text-align:center;padding:5px 4px;">'+(s.critical_notifications?'<span style="color:var(--red);font-weight:600;">'+s.critical_notifications+'</span>':'0')+'</td>';
      var gwText = esc(s.gateway_model||'-');
      if (s.gateway_uptime) gwText += ' <span style="font-size:10px;color:var(--text-dim);">'+_formatUptime(s.gateway_uptime)+'</span>';
      h += '<td style="padding:5px 4px;">'+gwText+'</td>';
      h += '<td style="padding:5px 4px;">'+esc(s.isp||'-')+'</td>';
      h += '</tr>';

      // Detail row
      var details = [];
      if (s.tx_retry_pct) details.push('TX retry: '+(s.tx_retry_pct > 5 ? '<span style="color:var(--orange);">'+s.tx_retry_pct+'%</span>' : s.tx_retry_pct+'%'));
      if (s.wan_uptime_pct) details.push('WAN uptime: '+s.wan_uptime_pct+'%');
      if (s.gateway_version) details.push('GW FW: '+esc(s.gateway_version));
      if (s.gateway_mac) details.push('GW MAC: <code style="font-size:10px;">'+esc(s.gateway_mac)+'</code>');
      if (s.wan_interfaces) details.push('WAN: '+s.wan_interfaces);
      if (s.lan_networks) details.push('LAN: '+s.lan_networks);
      if (s.isp_org) details.push('ISP org: '+esc(s.isp_org));
      if (s.isp_asn) details.push('ASN: '+esc(s.isp_asn));
      if (s.country) details.push('Land: '+esc(s.country));
      if (s.internet_issues && s.internet_issues.length) details.push('<span style="color:var(--orange);">⚠ '+s.internet_issues.length+' nettverksproblem(er)</span>');
      if (details.length) {
        h += '<tr style="border-bottom:1px solid var(--border);background:var(--bg-input);">';
        h += '<td colspan="12" style="padding:4px 8px 4px 24px;font-size:11px;color:var(--text-dim);">'+details.join(' · ')+'</td></tr>';
      }
    });
    h += '</tbody></table></div>';

    // Summary bar
    var totalDev=0, totalCli=0, totalOff=0, totalUpd=0, totalCrit=0, avgWanUp=0, wanCount=0;
    d.sub_sites.forEach(function(s) {
      totalDev += s.device_count; totalCli += s.client_count;
      totalOff += s.offline_devices||0; totalUpd += s.pending_updates||0;
      totalCrit += s.critical_notifications||0;
      if (s.wan_uptime_pct) { avgWanUp += s.wan_uptime_pct; wanCount++; }
    });
    if (wanCount) avgWanUp = Math.round(avgWanUp * 10 / wanCount) / 10;

    h += '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;padding:8px 12px;background:var(--bg-input);border-radius:6px;font-size:12px;">';
    h += '<span>' + t('totalt') + ' <strong>'+totalDev+'</strong> ' + t('enheter_2') + '</span>';
    h += '<span><strong>'+totalCli+'</strong> ' + t('klienter_2') + '</span>';
    if (avgWanUp) { var wC = avgWanUp>=99?'var(--green)':avgWanUp>=95?'var(--orange)':'var(--red)'; h += '<span>' + t('wan_uptime') + ' <strong style="color:'+wC+';">'+avgWanUp+'%</strong></span>'; }
    if (totalOff) h += '<span style="color:var(--red);"><strong>'+totalOff+'</strong> ' + t('offline_2') + '</span>';
    if (totalUpd) h += '<span style="color:var(--orange);"><strong>'+totalUpd+'</strong> ' + t('ventende_oppdateringer') + '</span>';
    if (totalCrit) h += '<span style="color:var(--red);"><strong>'+totalCrit+'</strong> ' + t('kritiske_varsler') + '</span>';
    h += '</div>';
  }

  // Placeholders for async-loaded sections
  h += '<div id="'+panelId+'-devices" style="margin-top:16px;"></div>';
  h += '<div id="'+panelId+'-isp" style="margin-top:16px;"></div>';
  h += '<div id="'+panelId+'-wan" style="margin-top:16px;"></div>';

  h += '</div>';
  panel.innerHTML = h;
  el.appendChild(panel);
  panel.scrollIntoView({behavior:'smooth', block:'nearest'});

  // ── Async load: devices, ISP metrics, WAN per site ──
  if (d.source === 'site_manager' && d.id) {
    _loadUnifiDevices(panelId, d.id);
    _loadUnifiIspMetrics(panelId);
    if (d.sub_sites && d.sub_sites.length) _loadUnifiWan(panelId, d.sub_sites);
  }
}

async function _loadUnifiDevices(panelId, hostId) {
  var el = document.getElementById(panelId + '-devices');
  if (!el) return;
  el.innerHTML = '<div class="loader" style="width:14px;height:14px;margin:8px 0;"></div>';

  var data = await apiFetch('/api/unifi/sm/devices?host_id=' + hostId);
  if (!data || !data.ok || !data.devices || !data.devices.length) { el.innerHTML = ''; return; }

  var devs = data.devices;
  var typeIcons = {uap:'📶', usw:'🔌', ugw:'🌐', uxg:'🌐', udm:'🖥', ubb:'🔗'};

  var h = '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">Enheter ('+devs.length+')</div>';
  h += '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;min-width:800px;">';
  h += '<thead><tr style="border-bottom:2px solid var(--border);color:var(--text-muted);font-size:11px;">';
  h += '<th style="text-align:left;padding:6px 8px;">' + t('enhet') + '</th>';
  h += '<th style="text-align:left;padding:6px 4px;">' + t('modell') + '</th>';
  h += '<th style="text-align:left;padding:6px 4px;">IP</th>';
  h += '<th style="text-align:center;padding:6px 4px;">' + t('status_3') + '</th>';
  h += '<th style="text-align:left;padding:6px 4px;">' + t('type_3') + '</th>';
  h += '<th style="text-align:left;padding:6px 4px;">FW</th>';
  h += '<th style="text-align:left;padding:6px 4px;">' + t('uptime_2') + '</th>';
  h += '<th style="text-align:left;padding:6px 4px;">' + t('adoptert') + '</th>';
  h += '<th style="text-align:left;padding:6px 4px;">' + t('notat') + '</th>';
  h += '</tr></thead><tbody>';

  devs.forEach(function(dv) {
    var c = dv.status === 'online' ? 'var(--green)' : 'var(--red)';
    var icon = typeIcons[dv.type] || '📦';
    h += '<tr style="border-bottom:1px solid var(--border);">';
    h += '<td style="padding:5px 8px;">'+icon+' <strong>'+esc(dv.name||dv.mac||'-')+'</strong>';
    if (dv.is_console) h += ' <span style="font-size:10px;background:var(--blue);color:#fff;padding:0 4px;border-radius:4px;">' + t('console') + '</span>';
    h += '</td>';
    h += '<td style="padding:5px 4px;">'+esc(dv.model||'-')+' <span style="font-size:10px;color:var(--text-dim);">'+esc(dv.model_full||'')+'</span></td>';
    h += '<td style="padding:5px 4px;"><code style="font-size:11px;">'+esc(dv.ip||'-')+'</code></td>';
    h += '<td style="text-align:center;padding:5px 4px;"><span style="color:'+c+';font-weight:600;">'+(dv.status==='online'?'●':'○')+'</span></td>';
    h += '<td style="padding:5px 4px;">'+esc(dv.product_line||'-')+'</td>';
    h += '<td style="padding:5px 4px;">'+esc(dv.firmware||'-')+(dv.update_available?' <span style="color:var(--orange);">⬆ '+esc(dv.update_available)+'</span>':'')+'</td>';
    h += '<td style="padding:5px 4px;">'+esc(dv.uptime||'-')+'</td>';
    h += '<td style="padding:5px 4px;">'+(dv.adoption_time?new Date(dv.adoption_time).toLocaleDateString('no-NO'):'-')+'</td>';
    h += '<td style="padding:5px 4px;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px;color:var(--text-dim);">'+esc(dv.note||'')+'</td>';
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  el.innerHTML = h;
}

async function _loadUnifiIspMetrics(panelId) {
  var el = document.getElementById(panelId + '-isp');
  if (!el) return;
  el.innerHTML = '<div class="loader" style="width:14px;height:14px;margin:8px 0;"></div>';

  // Fetch both: 5m/24h for latest readings + 1h/7d for averages
  var results = await Promise.all([
    apiFetch('/api/unifi/sm/isp-metrics?metric_type=5m&duration=24h'),
    apiFetch('/api/unifi/sm/isp-metrics?metric_type=1h&duration=7d')
  ]);
  var data24h = (results[0] && results[0].ok) ? results[0] : null;
  var data7d = (results[1] && results[1].ok) ? results[1] : null;
  var data = data24h || data7d;
  if (!data || !data.ok || !data.sites || !data.sites.length) { el.innerHTML = ''; return; }

  var h = '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">' + t('isp_ytelse') + '</div>';
  h += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:10px;">';

  // Build lookup from 7d data for averages
  var avg7d = {};
  if (data7d && data7d.sites) data7d.sites.forEach(function(s) { avg7d[s.site_id] = s; });

  var sitesToRender = data.sites;
  sitesToRender.forEach(function(s) {
    var lat = s.latest || {};
    var avg = s.averages || {};
    var weekly = avg7d[s.site_id] || {};
    var weekAvg = weekly.averages || {};

    h += '<div style="padding:12px;background:var(--bg-input);border-radius:6px;">';
    h += '<div style="font-size:12px;font-weight:600;margin-bottom:8px;">'+esc(s.isp||'ISP')+'</div>';
    h += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;font-size:12px;">';
    h += '<div style="color:var(--text-dim);font-size:10px;"></div><div style="color:var(--text-dim);font-size:10px;text-align:center;">' + t('siste') + '</div><div style="color:var(--text-dim);font-size:10px;text-align:center;">' + t('snitt_d') + '</div>';
    // Download
    h += '<div>' + t('download') + '</div>';
    h += '<div style="text-align:center;"><strong>'+lat.download_mbps+'</strong> ' + t('mbps') + '</div>';
    h += '<div style="text-align:center;color:var(--text-dim);">-</div>';
    // Upload
    h += '<div>' + t('upload') + '</div>';
    h += '<div style="text-align:center;"><strong>'+lat.upload_mbps+'</strong> ' + t('mbps') + '</div>';
    h += '<div style="text-align:center;color:var(--text-dim);">-</div>';
    // Latency
    var latC = avg.latency_ms > 50 ? 'var(--red)' : avg.latency_ms > 20 ? 'var(--orange)' : 'var(--green)';
    var latC7 = weekAvg.latency_ms > 50 ? 'var(--red)' : weekAvg.latency_ms > 20 ? 'var(--orange)' : 'var(--green)';
    h += '<div>' + t('latency') + '</div>';
    h += '<div style="text-align:center;"><span style="color:'+latC+';font-weight:600;">'+avg.latency_ms+'ms</span></div>';
    h += '<div style="text-align:center;">'+(weekAvg.latency_ms?'<span style="color:'+latC7+';">'+weekAvg.latency_ms+'ms</span>':'-')+'</div>';
    // Packet loss
    var plC = avg.packet_loss > 1 ? 'var(--red)' : avg.packet_loss > 0.1 ? 'var(--orange)' : 'var(--green)';
    var plC7 = weekAvg.packet_loss > 1 ? 'var(--red)' : weekAvg.packet_loss > 0.1 ? 'var(--orange)' : 'var(--green)';
    h += '<div>' + t('pakketap') + '</div>';
    h += '<div style="text-align:center;"><span style="color:'+plC+';font-weight:600;">'+avg.packet_loss+'%</span></div>';
    h += '<div style="text-align:center;">'+(weekAvg.packet_loss!=null?'<span style="color:'+plC7+';">'+weekAvg.packet_loss+'%</span>':'-')+'</div>';
    // Uptime
    var upC = avg.uptime_pct < 99 ? 'var(--red)' : avg.uptime_pct < 99.9 ? 'var(--orange)' : 'var(--green)';
    var upC7 = weekAvg.uptime_pct < 99 ? 'var(--red)' : weekAvg.uptime_pct < 99.9 ? 'var(--orange)' : 'var(--green)';
    h += '<div>' + t('wan_uptime_2') + '</div>';
    h += '<div style="text-align:center;"><span style="color:'+upC+';font-weight:600;">'+avg.uptime_pct+'%</span></div>';
    h += '<div style="text-align:center;">'+(weekAvg.uptime_pct?'<span style="color:'+upC7+';">'+weekAvg.uptime_pct+'%</span>':'-')+'</div>';
    h += '</div>';
    h += '<div style="font-size:10px;color:var(--text-dim);margin-top:6px;">'+s.data_points+' ' + t('msg_measurements_24h') + ' '+(weekly.data_points?'/ '+weekly.data_points+' (7d)':'')+'</div>';
    h += '</div>';
  });
  h += '</div>';
  el.innerHTML = h;
}

async function _loadUnifiWan(panelId, subSites) {
  var el = document.getElementById(panelId + '-wan');
  if (!el) return;
  el.innerHTML = '<div class="loader" style="width:14px;height:14px;margin:8px 0;"></div>';

  // Load WAN details for each sub-site in parallel
  var promises = subSites.map(function(s) {
    return apiFetch('/api/unifi/sm/site/' + s.site_id + '/wan').then(function(d) { return {site: s.name, data: d}; }).catch(function() { return null; });
  });
  var results = await Promise.all(promises);
  results = results.filter(function(r) { return r && r.data && r.data.ok; });
  if (!results.length) { el.innerHTML = ''; return; }

  var h = '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">' + t('wan_gateway_sikkerhet') + '</div>';
  h += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px;">';

  results.forEach(function(r) {
    var gw = r.data.gateway || {};
    var wans = r.data.wans || [];
    h += '<div style="padding:12px;background:var(--bg-input);border-radius:6px;">';
    h += '<div style="font-size:12px;font-weight:600;margin-bottom:6px;">'+esc(r.site)+'</div>';
    // Gateway security
    if (gw.model) {
      h += '<div style="font-size:12px;margin-bottom:6px;">';
      h += '<span style="color:var(--text-muted);">' + t('gateway') + '</span> <strong>'+esc(gw.model)+'</strong>';
      var idsColor = gw.ids_mode === 'off' ? 'var(--red)' : 'var(--green)';
      h += ' · IDS: <span style="color:'+idsColor+';font-weight:600;">'+esc(gw.ids_mode)+'</span>';
      if (gw.inspection && gw.inspection !== 'off') h += ' · Inspeksjon: <span style="color:var(--green);">'+esc(gw.inspection)+'</span>';
      if (gw.ips_rules) h += ' · '+gw.ips_rules+' IPS-regler';
      h += '</div>';
    }
    // WAN interfaces
    wans.forEach(function(w) {
      h += '<div style="font-size:11px;padding:4px 0;border-top:1px solid var(--border);">';
      h += '<strong>'+esc(w.name)+'</strong>';
      if (w.external_ip) h += ' · <code style="font-size:10px;">'+esc(w.external_ip)+'</code>';
      if (w.isp) h += ' · '+esc(w.isp);
      if (w.isp_org) h += ' ('+esc(w.isp_org)+')';
      if (w.uptime_pct != null) {
        var wuC = w.uptime_pct < 99 ? 'var(--red)' : 'var(--green)';
        h += ' · Uptime: <span style="color:'+wuC+';">'+w.uptime_pct+'%</span>';
      }
      if (w.issues && w.issues.length) {
        h += '<div style="color:var(--orange);margin-top:2px;">';
        w.issues.forEach(function(iss) { h += '⚠ '+esc(iss)+'<br>'; });
        h += '</div>';
      }
      h += '</div>';
    });
    h += '</div>';
  });
  h += '</div>';
  el.innerHTML = h;
}

function _formatUptime(secs) {
  if (typeof secs !== 'number') return secs;
  var d = Math.floor(secs/86400), h = Math.floor((secs%86400)/3600), m = Math.floor((secs%3600)/60);
  if (d > 0) return d+'d '+h+'t';
  if (h > 0) return h+'t '+m+'m';
  return m+'m';
}

// ═══════════════════════════════════════════════════════════════════
// PENTEST
// ═══════════════════════════════════════════════════════════════════

async function runPentest() {
  var target = document.getElementById('pentest-target').value.trim();
  if (!target) { showToast(t('skriv_inn_et_target'), 'error'); return; }
  var scanType = document.getElementById('pentest-type').value;
  var scanMode = document.getElementById('pentest-scan-mode').value;
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader" style="width:24px;height:24px;margin:24px auto;"></div><div style="text-align:center;color:var(--text-muted);font-size:12px;">Scanner ' + esc(target) + '... Dette kan ta opptil 5 minutter.</div>';

  var endpoint = scanType === 'port' ? '/api/pentest/port-scan' : scanType === 'web' ? '/api/pentest/web-scan' : '/api/pentest/full-scan';
  var body = scanType === 'web' ? {url: target} : {target: target, scan_type: scanMode};
  var data = await apiFetch(endpoint, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});

  if (!data || !data.ok) {
    el.innerHTML = '<div class="card" style="padding:16px;border-left:3px solid var(--red);"><strong style="color:var(--red);">' + t('feil_2') + '</strong> ' + esc(data && data.error ? data.error : 'Ukjent feil') + '</div>';
    return;
  }

  _renderPentestResults(data, el, target);
}

function _renderPentestResults(data, el, target) {
  var findings = data.findings || [];
  var summary = data.summary || data.finding_summary || {};
  var sevColors = {critical:'var(--red)', high:'var(--orange)', medium:'#c9a800', low:'var(--text-muted)', info:'var(--blue)'};

  var html = '';

  // KPI cards
  html += '<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:16px;">';
  ['critical','high','medium','low','info','total'].forEach(function(sev) {
    var count = summary[sev] || 0;
    var color = sevColors[sev] || 'var(--text-muted)';
    var label = sev === 'total' ? 'Totalt' : sev.charAt(0).toUpperCase() + sev.slice(1);
    html += '<div class="card" style="padding:12px;text-align:center;border-top:2px solid '+color+';"><div style="font-size:22px;font-weight:700;color:'+color+';">'+count+'</div><div style="font-size:10px;color:var(--text-muted);">'+label+'</div></div>';
  });
  html += '</div>';

  // Network info
  if (data.network && data.network.hosts) {
    html += '<div class="card" style="padding:12px;margin-bottom:12px;"><div style="font-size:12px;font-weight:600;margin-bottom:6px;">' + t('nettverksskanning') + '</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);">'+data.network.host_count+' ' + t('msg_hosts_found') + ', '+data.network.total_open_ports+' ' + t('msg_open_ports') + '</div>';
    data.network.hosts.forEach(function(h) {
      html += '<div style="margin-top:8px;font-size:12px;"><strong>'+esc(h.hostname||h.ip)+'</strong> ('+h.port_count+' porter)'+(h.os?' — '+esc(h.os):'')+'</div>';
      if (h.ports.length) {
        html += '<table style="width:100%;font-size:10px;border-collapse:collapse;margin-top:4px;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:3px;">' + t('port_2') + '</th><th>' + t('tjeneste_3') + '</th><th>' + t('produkt') + '</th><th>' + t('versjon') + '</th></tr></thead><tbody>';
        h.ports.forEach(function(p) {
          html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:3px;font-weight:500;">'+p.port+'/'+p.protocol+'</td><td style="padding:3px;">'+esc(p.service)+'</td><td style="padding:3px;">'+esc(p.product)+'</td><td style="padding:3px;">'+esc(p.version)+'</td></tr>';
        });
        html += '</tbody></table>';
      }
    });
    html += '</div>';
  }

  // Web info
  if (data.web && data.web.info) {
    var wi = data.web.info;
    html += '<div class="card" style="padding:12px;margin-bottom:12px;"><div style="font-size:12px;font-weight:600;margin-bottom:6px;">' + t('websjekk') + '</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);">Status: '+wi.status_code+' | Server: '+esc(wi.server||'-')+' | URL: '+esc(wi.final_url||wi.url)+'</div>';
    html += '</div>';
  }

  // Findings table
  if (findings.length) {
    html += '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">Funn ('+findings.length+')</div>';
    html += '<div style="overflow-x:auto;"><table style="width:100%;font-size:11px;border-collapse:collapse;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:center;padding:4px;width:70px;">' + t('alvor') + '</th><th style="text-align:left;padding:4px;">' + t('funn') + '</th><th style="text-align:left;padding:4px;">' + t('detalj') + '</th><th style="text-align:left;padding:4px;">' + t('remediation') + '</th><th style="padding:4px;width:90px;"></th></tr></thead><tbody>';
    findings.forEach(function(f, i) {
      var sc = sevColors[f.severity] || 'var(--text-muted)';
      var rowId = 'pf-' + i;
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += '<td style="padding:4px;text-align:center;"><span style="background:'+sc+';color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;">'+f.severity+'</span></td>';
      html += '<td style="padding:4px;font-weight:500;">'+esc(f.title)+(f.cve?' <span style="font-size:9px;color:var(--blue);">'+esc(f.cve)+'</span>':'')+'</td>';
      html += '<td style="padding:4px;font-size:10px;color:var(--text-muted);max-width:250px;">'+esc(f.detail||'')+'</td>';
      html += '<td style="padding:4px;font-size:10px;color:var(--text-muted);max-width:250px;">'+esc(f.remediation||'')+'</td>';
      html += '<td style="padding:4px;text-align:right;"><button class="btn btn-ghost" onclick="_pentestToggleExplain(\''+rowId+'\','+i+')" style="padding:2px 8px;font-size:10px;white-space:nowrap;">'+esc(t('pentest_btn_explain','💡 Explain'))+'</button></td>';
      html += '</tr>';
      // Hidden explainer row, populated on first toggle
      html += '<tr id="'+rowId+'" style="display:none;"><td colspan="5" style="padding:0;"><div style="background:var(--bg-input);border-left:3px solid '+sc+';padding:12px 16px;font-size:11px;line-height:1.6;"></div></td></tr>';
    });
    html += '</tbody></table></div>';
  } else {
    html += '<div style="color:var(--green);text-align:center;padding:24px;">' + t('ingen_saarbarheter_funnet') + '</div>';
  }

  html += '<div style="display:flex;gap:8px;margin-top:16px;">';
  html += '<button class="btn btn-ghost" onclick="_pentestReport()" style="font-size:11px;">' + t('generer_rapport') + '</button>';
  html += '<button class="btn btn-ghost" onclick="_pentestSave()" style="font-size:11px;">' + t('lagre_scan') + '</button>';
  html += '</div>';
  html += '<div style="font-size:10px;color:var(--text-dim);margin-top:8px;">Skannet: ' + new Date(data.timestamp).toLocaleString('no-NO') + '</div>';
  el.innerHTML = html;
  window._lastPentestData = data;
}

// ── Pentest knowledge base lookup ────────────────────────────────────────────
// Maps a finding to (whyKey, fixKey) i18n keys.
// Title-substring overrides take priority over category mapping.
function _pentestKBLookup(finding) {
  var title = (finding.title || '').toLowerCase();
  var cat = finding.category || '';

  // Specific title overrides (most specific first)
  var titleMap = [
    {needle: 'rest api',                      why: 'kb_title_wp_users_why',    fix: 'kb_title_wp_users_fix'},
    {needle: 'wp-json',                       why: 'kb_title_wp_users_why',    fix: 'kb_title_wp_users_fix'},
    {needle: 'directory listing',             why: 'kb_title_dir_listing_why', fix: 'kb_title_dir_listing_fix'},
    {needle: 'upload-mappe',                  why: 'kb_title_dir_listing_why', fix: 'kb_title_dir_listing_fix'},
    {needle: 'zone transfer',                 why: 'kb_title_axfr_why',        fix: 'kb_title_axfr_fix'},
    {needle: 'axfr',                          why: 'kb_title_axfr_why',        fix: 'kb_title_axfr_fix'},
  ];
  for (var i = 0; i < titleMap.length; i++) {
    if (title.indexOf(titleMap[i].needle) !== -1) {
      return {why: titleMap[i].why, fix: titleMap[i].fix};
    }
  }

  // Category mapping (covers all categories from pentest modules)
  var catMap = {
    'tls_protocol':            ['kb_tls_protocol_why',          'kb_tls_protocol_fix'],
    'tls_cert':                ['kb_tls_cert_why',              'kb_tls_cert_fix'],
    'tls_cipher':              ['kb_tls_cipher_why',            'kb_tls_cipher_fix'],
    'ssl_config':              ['kb_ssl_config_why',            'kb_ssl_config_fix'],
    'certificate':             ['kb_certificate_why',           'kb_certificate_fix'],
    'missing_header':          ['kb_missing_header_why',        'kb_missing_header_fix'],
    'cookie_security':         ['kb_cookie_security_why',       'kb_cookie_security_fix'],
    'info_disclosure':         ['kb_info_disclosure_why',       'kb_info_disclosure_fix'],
    'misconfiguration':        ['kb_misconfiguration_why',      'kb_misconfiguration_fix'],
    'transport_security':      ['kb_transport_security_why',    'kb_transport_security_fix'],
    'dns_security':            ['kb_dns_security_why',          'kb_dns_security_fix'],
    'dns_recon':               ['kb_dns_recon_why',             'kb_dns_recon_fix'],
    'email_security':          ['kb_email_security_why',        'kb_email_security_fix'],
    'subdomain_takeover':      ['kb_subdomain_takeover_why',    'kb_subdomain_takeover_fix'],
    'cms_detection':           ['kb_cms_detection_why',         'kb_cms_detection_fix'],
    'cms_vuln':                ['kb_cms_vuln_why',              'kb_cms_vuln_fix'],
    'default_credential':      ['kb_default_credential_why',    'kb_default_credential_fix'],
    'known_vuln':              ['kb_known_vuln_why',            'kb_known_vuln_fix'],
    'outdated_version':        ['kb_outdated_version_why',      'kb_outdated_version_fix'],
    'smb_exposure':            ['kb_smb_exposure_why',          'kb_smb_exposure_fix'],
    'smb_null_session':        ['kb_smb_null_session_why',      'kb_smb_null_session_fix'],
    'smb_security':            ['kb_smb_security_why',          'kb_smb_security_fix'],
    'smb_users':               ['kb_smb_users_why',             'kb_smb_users_fix'],
    'smb_info':                ['kb_smb_info_why',              'kb_smb_info_fix'],
    'exposed_service':         ['kb_exposed_service_why',       'kb_exposed_service_fix'],
    'unknown_service':         ['kb_unknown_service_why',       'kb_unknown_service_fix'],
    'segmentation_fail':       ['kb_segmentation_fail_why',     'kb_segmentation_fail_fix'],
    'segmentation_unexpected': ['kb_segmentation_unexpected_why','kb_segmentation_unexpected_fix'],
    'segmentation_pass':       ['kb_segmentation_pass_why',     'kb_segmentation_pass_fix'],
    'segmentation_info':       ['kb_segmentation_info_why',     'kb_segmentation_info_fix'],
  };
  if (catMap[cat]) return {why: catMap[cat][0], fix: catMap[cat][1]};
  return {why: 'kb_default_why', fix: 'kb_default_fix'};
}

function _pentestToggleExplain(rowId, idx) {
  var row = document.getElementById(rowId);
  if (!row) return;
  var inner = row.querySelector('div');
  var findings = (window._lastPentestData && window._lastPentestData.findings) || [];
  var f = findings[idx];
  if (!f) return;

  if (row.style.display === 'none') {
    if (!inner.innerHTML) {
      var kb = _pentestKBLookup(f);
      var whyText = t(kb.why, '');
      var fixText = t(kb.fix, '');
      inner.innerHTML =
        '<div style="font-weight:600;color:var(--text);margin-bottom:4px;">' + esc(t('pentest_lbl_why','Why is this a problem?')) + '</div>'
        + '<div style="white-space:pre-line;color:var(--text-muted);margin-bottom:10px;">' + esc(whyText) + '</div>'
        + '<div style="font-weight:600;color:var(--text);margin-bottom:4px;">' + esc(t('pentest_lbl_how_to_fix','How to fix it')) + '</div>'
        + '<div style="white-space:pre-line;color:var(--text-muted);font-family:var(--mono);font-size:10px;">' + esc(fixText) + '</div>';
    }
    row.style.display = '';
  } else {
    row.style.display = 'none';
  }
}

async function runDnsPentest() {
  var target = document.getElementById('pentest-target').value.trim();
  if (!target) { showToast(t('skriv_inn_et_domene'), 'error'); return; }
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader" style="width:24px;height:24px;margin:24px auto;"></div><div style="text-align:center;color:var(--text-muted);font-size:12px;">DNS-sikkerhetsscan: ' + esc(target) + '...</div>';

  var data = await apiFetch('/api/pentest/dns-scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({domain:target})});
  if (!data || !data.ok) {
    el.innerHTML = '<div class="card" style="padding:16px;border-left:3px solid var(--red);"><strong style="color:var(--red);">' + t('feil_2') + '</strong> ' + esc(data&&data.error?data.error:'Ukjent feil') + '</div>';
    return;
  }

  var findings = data.findings || [];
  var subs = data.subdomains || [];
  var html = '';

  // Summary
  html += '<div style="font-size:14px;font-weight:600;margin-bottom:12px;">DNS-sikkerhet: '+esc(target)+'</div>';

  // Email security
  if (data.email_security) {
    var es = data.email_security;
    html += '<div class="card" style="padding:12px;margin-bottom:12px;"><div style="font-size:12px;font-weight:600;margin-bottom:6px;">E-postsikkerhet (Grade: '+esc(es.grade||'?')+')</div>';
    html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;font-size:11px;">';
    ['spf','dkim','dmarc','mx'].forEach(function(k) {
      var c = es[k]||{};
      var color = c.status==='pass'?'var(--green)':c.status==='fail'?'var(--red)':c.status==='warn'?'var(--orange)':'var(--text-muted)';
      html += '<div style="text-align:center;"><div style="font-weight:600;color:'+color+';text-transform:uppercase;">'+k+'</div><div style="color:var(--text-muted);font-size:10px;">'+(c.status||'?')+'</div></div>';
    });
    html += '</div></div>';
  }

  // Subdomains
  if (subs.length) {
    html += '<div class="card" style="padding:12px;margin-bottom:12px;"><div style="font-size:12px;font-weight:600;margin-bottom:6px;">Oppdagede subdomener ('+subs.length+')</div>';
    html += '<div style="display:flex;flex-wrap:wrap;gap:4px;">';
    subs.forEach(function(s) { html += '<span style="background:var(--bg);padding:2px 8px;border-radius:4px;font-size:10px;font-family:var(--mono);">'+esc(s.subdomain)+' → '+esc(s.ips[0]||'')+'</span>'; });
    html += '</div></div>';
  }

  // Findings
  _renderPentestResults({ok:true, findings:findings, summary:data.summary, timestamp:new Date().toISOString()}, el, target);
}

async function runCredentialTest() {
  var target = document.getElementById('pentest-target').value.trim();
  if (!target) { showToast(t('skriv_inn_en_host_ip'), 'error'); return; }
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader" style="width:24px;height:24px;margin:24px auto;"></div><div style="text-align:center;color:var(--text-muted);font-size:12px;">Tester standard-passord på ' + esc(target) + '...</div>';

  var data = await apiFetch('/api/pentest/credential-test', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({host:target})});
  if (!data || !data.ok) {
    el.innerHTML = '<div class="card" style="padding:16px;border-left:3px solid var(--red);"><strong style="color:var(--red);">' + t('feil_2') + '</strong> ' + esc(data&&data.error?data.error:'Ukjent feil') + '</div>';
    return;
  }

  var findings = data.findings || [];
  if (!findings.length) {
    el.innerHTML = '<div class="card" style="padding:16px;border-left:3px solid var(--green);">✓ Ingen standard-passord funnet på ' + esc(target) + '</div>';
    return;
  }

  _renderPentestResults({ok:true, findings:findings, summary:{critical:findings.filter(function(f){return f.severity==='critical'}).length, high:findings.filter(function(f){return f.severity==='high'}).length, medium:0, low:0, info:0, total:findings.length}, timestamp:new Date().toISOString()}, el, target);
}

async function _pentestReport() {
  var data = window._lastPentestData;
  if (!data || !data.findings || !data.findings.length) { showToast(t('kjoer_en_scan_foerst'), 'error'); return; }
  var target = document.getElementById('pentest-target').value.trim() || 'unknown';

  // Open HTML report in new tab
  var resp = await fetch('/api/pentest/report', {
    method: 'POST',
    headers: {'Content-Type':'application/json', 'Authorization':'Bearer '+_authToken},
    body: JSON.stringify({target:target, findings:data.findings, summary:data.summary||data.finding_summary, format:'html'})
  });
  if (resp.ok) {
    var html = await resp.text();
    var w = window.open('', '_blank');
    w.document.write(html);
    w.document.close();
  } else {
    showToast(t('kunne_ikke_generere_rapport'), 'error');
  }
}

async function _pentestSave() {
  var data = window._lastPentestData;
  if (!data || !data.findings) { showToast(t('kjoer_en_scan_foerst'), 'error'); return; }
  var target = document.getElementById('pentest-target').value.trim() || 'unknown';
  var r = await apiFetch('/api/pentest/save-scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({target:target, findings:data.findings, summary:data.summary||data.finding_summary, scan_type:'full'})});
  if (r && r.ok) showToast(t('scan_lagret_id') + ' '+r.scan_id+')', 'success');
  else showToast(t('kunne_ikke_lagre'), 'error');
}

async function runCmsScan() {
  var target = document.getElementById('pentest-target').value.trim();
  if (!target) { showToast(t('skriv_inn_en_url'), 'error'); return; }
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader" style="width:24px;height:24px;margin:24px auto;"></div><div style="text-align:center;color:var(--text-muted);font-size:12px;">CMS-skanning: ' + esc(target) + '...</div>';
  var data = await apiFetch('/api/pentest/cms-scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:target})});
  if (!data || !data.ok) { el.innerHTML = '<div class="card" style="padding:16px;border-left:3px solid var(--red);">Feil: ' + esc(data&&data.error?data.error:'Ukjent') + '</div>'; return; }
  var cms = data.cms || {};
  var html = '<div class="card" style="padding:12px;margin-bottom:12px;"><strong>' + t('cms') + '</strong> ' + esc(cms.cms||'Ingen detektert') + (cms.version ? ' v'+esc(cms.version) : '') + '</div>';
  _renderPentestResults({ok:true, findings:data.findings||[], summary:data.summary, timestamp:new Date().toISOString()}, el, target);
  el.innerHTML = html + el.innerHTML;
  window._lastPentestData = data;
}

async function runSmbEnum() {
  var target = document.getElementById('pentest-target').value.trim();
  if (!target) { showToast(t('skriv_inn_en_ip_hostname'), 'error'); return; }
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader" style="width:24px;height:24px;margin:24px auto;"></div><div style="text-align:center;color:var(--text-muted);font-size:12px;">SMB-enumerering: ' + esc(target) + '... (kan ta 60s)</div>';
  var data = await apiFetch('/api/pentest/smb-enum', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({host:target})});
  if (!data || !data.ok) { el.innerHTML = '<div class="card" style="padding:16px;border-left:3px solid var(--red);">Feil: ' + esc(data&&data.error?data.error:'Ukjent') + '</div>'; return; }
  _renderPentestResults({ok:true, findings:data.findings||[], summary:data.summary, timestamp:new Date().toISOString()}, el, target);
  window._lastPentestData = data;
}

async function runSegTest() {
  var el = document.getElementById('pentest-results');
  // Get active customer for auto-test
  var status = await apiFetch('/api/status');
  var custId = status && status.active_id;
  if (!custId) { showToast(t('velg_en_kunde_med_fortigate'), 'error'); return; }
  el.innerHTML = '<div class="loader" style="width:24px;height:24px;margin:24px auto;"></div><div style="text-align:center;color:var(--text-muted);font-size:12px;">' + t('tester_nettverkssegmentering_for_aktiv_kunde') + '</div>';
  var data = await apiFetch('/api/pentest/segmentation-test', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({customer_id:custId})});
  if (!data || !data.ok) { el.innerHTML = '<div class="card" style="padding:16px;border-left:3px solid var(--red);">Feil: ' + esc(data&&data.error?data.error:'Ukjent') + '</div>'; return; }
  var s = data.summary||{};
  var html = '<div class="card" style="padding:12px;margin-bottom:12px;"><strong>' + t('segmentering') + '</strong> ' + s.pass + ' OK, ' + s.fail + ' feilet av ' + s.total_tests + ' tester</div>';
  _renderPentestResults({ok:true, findings:data.findings||[], summary:{critical:s.critical||0,high:s.high||0,medium:s.medium||0,low:0,info:s.total_tests-(s.critical||0)-(s.high||0)-(s.medium||0),total:data.findings.length}, timestamp:new Date().toISOString()}, el, 'segmentering');
  el.innerHTML = html + el.innerHTML;
  window._lastPentestData = data;
}

async function runTlsAudit() {
  var raw = document.getElementById('pentest-target').value.trim();
  if (!raw) { showToast(t('pentest_msg_enter_host_port','Enter a hostname (or host:port)'), 'error'); return; }
  // Strip scheme and path; extract optional :port
  var host = raw.replace(/^https?:\/\//,'').replace(/\/.*$/,'');
  var port = 443;
  var m = host.match(/^([^:]+):(\d+)$/);
  if (m) { host = m[1]; port = parseInt(m[2],10); }
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader" style="width:24px;height:24px;margin:24px auto;"></div><div style="text-align:center;color:var(--text-muted);font-size:12px;">' + esc(t('pentest_msg_tls_progress','TLS audit in progress — probing TLS 1.0–1.3...')) + ' (' + esc(host) + ':' + port + ')</div>';
  var data = await apiFetch('/api/pentest/tls-audit', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({host:host, port:port})});
  if (!data || !data.ok) { el.innerHTML = '<div class="card" style="padding:16px;border-left:3px solid var(--red);">' + esc(t('pentest_msg_tls_failed','TLS audit failed')) + ': ' + esc(data&&data.error?data.error:t('pentest_msg_unknown_error','Unknown error')) + '</div>'; return; }

  // Render protocol matrix + cert summary above the standard findings list
  var p = data.protocols || {};
  var labelOn = t('pentest_pill_on','ON');
  var labelOff = t('pentest_pill_off','OFF');
  var pill = function(name, ok, goodWhenOn) {
    var good = goodWhenOn ? ok : !ok;
    var color = good ? '#3aa763' : '#d0021b';
    var label = ok ? labelOn : labelOff;
    return '<span style="display:inline-block;padding:2px 8px;margin-right:6px;border-radius:10px;font-size:11px;background:' + color + '22;color:' + color + ';border:1px solid ' + color + '55;">' + name + ' ' + label + '</span>';
  };
  var cert = data.certificate || {};
  var cipher = data.cipher || {};
  var topHtml = '<div class="card" style="margin-bottom:12px;padding:14px;">'
    + '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">' + esc(t('pentest_tls_status_header','🔐 TLS status')) + ' — ' + esc(host) + ':' + port + '</div>'
    + '<div style="margin-bottom:10px;">'
    + pill('TLS 1.0', !!p['TLSv1.0'], false)
    + pill('TLS 1.1', !!p['TLSv1.1'], false)
    + pill('TLS 1.2', !!p['TLSv1.2'], true)
    + pill('TLS 1.3', !!p['TLSv1.3'], true)
    + '</div>';
  if (cert.subject) {
    topHtml += '<div style="font-size:11px;color:var(--text-muted);line-height:1.6;">'
      + '<div><strong>' + esc(t('pentest_lbl_issuer','Issuer')) + ':</strong> ' + esc(cert.issuer && (cert.issuer.commonName || cert.issuer.organizationName) || '—') + '</div>'
      + '<div><strong>' + esc(t('pentest_lbl_expires','Expires')) + ':</strong> ' + esc(cert.not_after || '—') + (cert.days_to_expiry !== undefined ? ' (' + cert.days_to_expiry + ' ' + esc(t('pentest_lbl_days','days')) + ')' : '') + '</div>'
      + '<div><strong>' + esc(t('pentest_lbl_san','SAN')) + ':</strong> ' + esc((cert.sans || []).slice(0,5).join(', ') || '—') + '</div>'
      + '</div>';
  }
  if (cipher.name) {
    topHtml += '<div style="font-size:11px;color:var(--text-muted);margin-top:6px;"><strong>' + esc(t('pentest_lbl_cipher','Cipher')) + ':</strong> ' + esc(cipher.name) + ' (' + cipher.bits + ' ' + esc(t('pentest_lbl_bit','bit')) + ', ' + esc(cipher.protocol || '') + ')</div>';
  }
  topHtml += '</div>';

  _renderPentestResults({ok:true, findings:data.findings||[], summary:data.summary, timestamp:data.timestamp}, el, host);
  el.innerHTML = topHtml + el.innerHTML;
  window._lastPentestData = data;
}

async function runTakeoverCheck() {
  var raw = document.getElementById('pentest-target').value.trim();
  if (!raw) { showToast(t('pentest_msg_enter_domain','Enter a domain'), 'error'); return; }
  var domain = raw.replace(/^https?:\/\//,'').replace(/\/.*$/,'').replace(/:\d+$/,'');
  var el = document.getElementById('pentest-results');
  el.innerHTML = '<div class="loader" style="width:24px;height:24px;margin:24px auto;"></div>'
    + '<div style="text-align:center;color:var(--text-muted);font-size:12px;">' + esc(t('pentest_msg_takeover_progress','Subdomain takeover check — enumerating subdomains...')) + ' (' + esc(domain) + ')</div>';
  var data = await apiFetch('/api/pentest/takeover-check', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({domain:domain})});
  if (!data || !data.ok) { el.innerHTML = '<div class="card" style="padding:16px;border-left:3px solid var(--red);">' + esc(t('pentest_msg_takeover_failed','Takeover check failed')) + ': ' + esc(data&&data.error?data.error:t('pentest_msg_unknown_error','Unknown error')) + '</div>'; return; }

  var s = data.summary || {};
  var topHtml = '<div class="card" style="margin-bottom:12px;padding:12px;">'
    + '<strong>' + esc(t('pentest_takeover_summary','🪝 Takeover check')) + ':</strong> '
    + (data.checked || 0) + ' ' + esc(t('pentest_subdomains_checked','subdomains checked')) + ' — '
    + '<span style="color:#d0021b;">' + (s.critical||0) + ' ' + esc(t('pentest_sev_critical','critical')) + '</span>, '
    + '<span style="color:#f5a623;">' + (s.high||0) + ' ' + esc(t('pentest_sev_high','high')) + '</span>, '
    + (s.info||0) + ' ' + esc(t('pentest_sev_info','info'))
    + '</div>';

  if (!data.findings || !data.findings.length) {
    el.innerHTML = topHtml + '<div class="card" style="padding:14px;color:var(--text-muted);">' + esc(t('pentest_takeover_no_findings','No takeover risk found 🎉')) + '</div>';
  } else {
    _renderPentestResults({ok:true, findings:data.findings, summary:{critical:s.critical||0,high:s.high||0,medium:0,low:0,info:s.info||0,total:data.findings.length}, timestamp:data.timestamp}, el, domain);
    el.innerHTML = topHtml + el.innerHTML;
  }
  window._lastPentestData = data;
}

async function dashLoadSites() {
  var el = document.getElementById('dash-sites-content');
  if (_unifiSites && _unifiSites.length) {
    el.innerHTML = _renderSiteTable(_unifiSites);
    return;
  }
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';
  var data = await apiFetch('/api/unifi/site-manager/sites');
  if (!data || !data.sites) {
    el.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:48px;">Ingen siter tilgjengelig. Konfigurer UniFi Site Manager under Integrasjoner.</div>';
    return;
  }
  _unifiSites = data.sites;
  el.innerHTML = _renderSiteTable(data.sites);
}

// ═══════════════════════════════════════════════════════════════════
// UNIFI SITE MANAGER INTEGRATION
// ═══════════════════════════════════════════════════════════════════

// State for 2FA flow
var _unifiSm2faToken = '';
var _unifiSm2faCustomerId = '';

async function unifiSmAuth() {
  var apiKey = document.getElementById('unifi-sm-apikey').value.trim();
  var email = document.getElementById('unifi-sm-email').value.trim();
  var pass = document.getElementById('unifi-sm-password').value;

  if (!apiKey && (!email || !pass)) { showToast(t('err_fill_api_key_or_email','Enter API key or email/password'),'error'); return; }

  var btn = document.getElementById('unifi-sm-auth-btn');
  var result = document.getElementById('unifi-sm-auth-result');
  btn.disabled = true; btn.textContent = t('vpn_connecting','Connecting...');
  result.textContent = '';

  var body = apiKey ? {api_key: apiKey} : {username: email, password: pass};
  var data = await apiFetch('/api/unifi/site-manager/auth', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  btn.disabled = false; btn.textContent = t('lbl_connect','Koble til');

  if (data && data.ok) {
    _unifiSmAuthSuccess();
  } else if (data && data.requires_2fa) {
    // Show 2FA input
    _unifiSm2faToken = data.session_token || '';
    _unifiSm2faCustomerId = data.customer_id || '';
    _unifiSmShow2fa();
  } else {
    result.innerHTML = '<span style="color:var(--red);">'+(data && data.error ? data.error : t('err_connection_failed','Tilkobling feilet'))+'</span>';
  }
}

function _unifiSmShow2fa() {
  var result = document.getElementById('unifi-sm-auth-result');
  result.innerHTML =
    '<div style="margin-top:8px;">' +
      '<label style="font-size:0.95em;color:var(--fg2);">' + t('lbl_2fa_required','2FA-kode påkrevd') + '</label>' +
      '<div style="display:flex;gap:8px;margin-top:4px;">' +
        '<input id="unifi-sm-2fa-code" type="text" inputmode="numeric" pattern="[0-9]*" ' +
          'maxlength="6" placeholder="123456" autocomplete="one-time-code" ' +
          'style="width:120px;text-align:center;font-size:1.1em;letter-spacing:3px;">' +
        '<button id="unifi-sm-2fa-btn" class="btn btn-primary" onclick="unifiSmVerify2fa()">' +
          t('btn_verify','Verifiser') +
        '</button>' +
      '</div>' +
      '<div id="unifi-sm-2fa-error" style="margin-top:4px;"></div>' +
    '</div>';
  var codeInput = document.getElementById('unifi-sm-2fa-code');
  if (codeInput) {
    codeInput.focus();
    codeInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') unifiSmVerify2fa();
    });
  }
}

async function unifiSmVerify2fa() {
  var code = document.getElementById('unifi-sm-2fa-code').value.trim();
  if (!code || code.length < 6) {
    document.getElementById('unifi-sm-2fa-error').innerHTML =
      '<span style="color:var(--red);">' + t('err_2fa_enter_code','Skriv inn 6-sifret 2FA-kode') + '</span>';
    return;
  }

  var btn = document.getElementById('unifi-sm-2fa-btn');
  btn.disabled = true; btn.textContent = t('vpn_connecting','Connecting...');
  document.getElementById('unifi-sm-2fa-error').textContent = '';

  var data = await apiFetch('/api/unifi/site-manager/verify-2fa', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      session_token: _unifiSm2faToken,
      code: code,
      customer_id: _unifiSm2faCustomerId || undefined,
    }),
  });

  btn.disabled = false; btn.textContent = t('btn_verify','Verifiser');

  if (data && data.ok) {
    _unifiSmAuthSuccess();
  } else {
    document.getElementById('unifi-sm-2fa-error').innerHTML =
      '<span style="color:var(--red);">' + (data && data.error ? data.error : t('err_2fa_failed','2FA-verifisering feilet')) + '</span>';
    // Clear and re-focus for retry
    var codeInput = document.getElementById('unifi-sm-2fa-code');
    if (codeInput) { codeInput.value = ''; codeInput.focus(); }
  }
}

function _unifiSmAuthSuccess() {
  var result = document.getElementById('unifi-sm-auth-result');
  result.innerHTML = '<span style="color:var(--green);">' + t('lbl_connected','Tilkoblet') + '!</span>';
  document.getElementById('unifi-sm-integ-dot').style.background = 'var(--green)';
  document.getElementById('unifi-sm-integ-label').textContent = t('lbl_connected','Tilkoblet');
  document.getElementById('unifi-sm-integ-label').style.color = 'var(--green)';
  _unifiSm2faToken = '';
  _unifiSm2faCustomerId = '';
  unifiSmLoadSites();
}

async function unifiSmTestController() {
  var host = document.getElementById('unifi-sm-ctrl-host').value.trim();
  var user = document.getElementById('unifi-sm-ctrl-user').value.trim();
  var pass = document.getElementById('unifi-sm-ctrl-pass').value;
  var result = document.getElementById('unifi-sm-ctrl-result');
  if (!host || !user || !pass) { result.innerHTML = '<span style="color:var(--red);">' + t('err_fill_all_fields','Fill in all fields') + '</span>'; return; }
  result.textContent = t('msg_testing','Testing...');
  var data = await apiFetch('/api/unifi/test', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({host:host,username:user,password:pass,is_unifi_os:true})});
  if (data && data.ok) {
    result.innerHTML = '<span style="color:var(--green);">' + t('lbl_connected','Connected') + '! '+( data.sites ? data.sites+' ' + t('lbl_sites','sites') : '')+'</span>';
  } else {
    result.innerHTML = '<span style="color:var(--red);">'+(data&&data.error?data.error:'Tilkobling feilet')+'</span>';
  }
}

async function unifiSmSaveController() {
  var host = document.getElementById('unifi-sm-ctrl-host').value.trim();
  var user = document.getElementById('unifi-sm-ctrl-user').value.trim();
  var pass = document.getElementById('unifi-sm-ctrl-pass').value;
  if (!host || !user || !pass) { showToast(t('err_fill_all_fields','Fill in all fields'),'error'); return; }
  var data = await apiFetch('/api/settings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    unifi_controller_host: host,
    unifi_controller_username: user,
    unifi_controller_password: pass,
  })});
  if (data && data.ok) showToast(t('msg_controller_access_saved','Controller access saved'),'success');
}

async function unifiSmSave() {
  var apiKey = document.getElementById('unifi-sm-apikey').value.trim();
  if (!apiKey) { showToast(t('err_fill_api_key_first','Enter API key first'),'error'); return; }
  var data = await apiFetch('/api/settings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({unifi_site_manager_api_key: apiKey})});
  if (data && data.ok) { showToast(t('msg_api_key_saved','API key saved'),'success'); }
}

// Load saved UniFi SM key when integrations view opens
async function unifiSmLoadSaved() {
  var data = await apiFetch('/api/settings');
  if (data && data.unifi_site_manager_api_key) {
    var el = document.getElementById('unifi-sm-apikey');
    if (el) { el.value = data.unifi_site_manager_api_key; el.type = 'password'; }
    document.getElementById('unifi-sm-integ-dot').style.background = 'var(--blue)';
    document.getElementById('unifi-sm-integ-label').textContent = t('lbl_key_saved','Key saved');
    document.getElementById('unifi-sm-integ-label').style.color = 'var(--blue)';
  }
}

var _unifiSites = []; // cache for use in dashboard

async function unifiSmLoadSites() {
  var container = document.getElementById('unifi-sm-sites');
  var list = document.getElementById('unifi-sm-sites-list');
  container.style.display = 'block';
  list.innerHTML = '<div class="loader" style="width:16px;height:16px;margin:8px auto;"></div>';

  var data = await apiFetch('/api/unifi/site-manager/sites');
  if (!data || !data.sites) { list.innerHTML = '<span style="color:var(--text-muted);font-size:12px;">' + t('kunne_ikke_hente_siter') + '</span>'; return; }

  _unifiSites = data.sites;
  var sites = data.sites;
  if (!sites.length) { list.innerHTML = '<span style="color:var(--text-muted);font-size:12px;">' + t('ingen_siter_funnet') + '</span>'; return; }

  list.innerHTML = _renderSiteTable(sites);
}

function _renderSiteTable(sites) {
  // Split into multi-site controllers (ours) and standalone consoles
  var multiSite = sites.filter(function(s) { return s.sub_sites && s.sub_sites.length > 1; });
  var standalone = sites.filter(function(s) { return !s.sub_sites || s.sub_sites.length <= 1; });

  var html = '';

  // Render multi-site controllers with their sub-sites expanded
  multiSite.forEach(function(ctrl, ctrlIdx) {
    var ctrlStatus = ctrl.status === 'online' ? 'var(--green)' : 'var(--red)';
    // Controller banner
    html += '<div style="background:linear-gradient(135deg,var(--bg-card),var(--bg));border:1px solid var(--border);border-radius:8px;padding:14px 16px;margin-bottom:16px;cursor:pointer;" onclick="showSiteDetail('+sites.indexOf(ctrl)+')">';
    html += '<div style="display:flex;align-items:center;gap:10px;">';
    html += '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:'+ctrlStatus+';"></span>';
    html += '<strong style="font-size:15px;">'+ctrl.name+'</strong>';
    html += '<span style="font-size:12px;color:var(--text-muted);margin-left:4px;">'+ctrl.sub_sites.length+' siter — '+(ctrl.model||'Cloud Controller')+'</span>';
    html += '<span style="margin-left:auto;font-size:12px;color:var(--text-muted);">WAN: '+(ctrl.wan_ip||'-')+'</span>';
    html += '</div></div>';

    // Sub-sites as cards (clickable)
    html += '<div class="card-grid card-grid--sites" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;grid-auto-rows:1fr;margin-bottom:24px;">';
    ctrl.sub_sites.forEach(function(sub, subIdx) {
      var borderColor = sub.offline_devices > 0 ? 'var(--orange)' : sub.device_count > 0 ? 'var(--green)' : 'var(--text-dim)';
      // 2-row grid: 24px name | 1fr stats
      html += '<div class="card" style="padding:12px;border-left:3px solid '+borderColor+';display:grid;grid-template-rows:24px 1fr;height:100%;cursor:pointer;" onclick="showSubSiteDetail('+sites.indexOf(ctrl)+','+subIdx+')">';

      // ROW 1: name + badges (24px)
      html += '<div style="display:flex;align-items:center;height:24px;overflow:hidden;">';
      html += '<strong style="font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0;" title="'+sub.name+'">'+sub.name+'</strong>';
      if (sub.offline_devices > 0) html += '<span style="font-size:10px;color:var(--red);font-weight:600;white-space:nowrap;flex-shrink:0;margin-left:8px;">'+sub.offline_devices+' offline</span>';
      if (sub.critical_notifications > 0) html += '<span style="font-size:10px;color:var(--orange);font-weight:600;white-space:nowrap;flex-shrink:0;margin-left:6px;">'+sub.critical_notifications+' varsel</span>';
      html += '</div>';

      // ROW 2: stats (1fr)
      html += '<div style="display:flex;gap:12px;font-size:12px;color:var(--text-muted);align-items:start;padding-top:4px;">';
      html += '<span>' + t('lbl_devices','Devices') + ': <strong style="color:var(--text);">'+sub.device_count+'</strong></span>';
      html += '<span>' + t('lbl_clients','Clients') + ': '+(sub.wifi_clients+sub.wired_clients)+'</span>';
      html += '<span>SSID: '+(sub.wifi_networks||0)+'</span>';
      html += '<span>VLAN: '+(sub.lan_networks||0)+'</span>';
      html += '</div>';
      html += '</div>';
    });
    html += '</div>';
  });

  // Standalone consoles header
  if (standalone.length && multiSite.length) {
    html += '<div style="font-size:13px;font-weight:600;color:var(--text-muted);margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--border);">Selvstendige konsoller ('+standalone.length+')</div>';
  }

  // Standalone console cards
  if (standalone.length) {
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px;grid-auto-rows:1fr;">';
    standalone.forEach(function(s) {
      var idx = sites.indexOf(s);
      var statusColor = s.status === 'online' ? 'var(--green)' : 'var(--red)';
      var borderColor = s.offline_devices > 0 ? 'var(--orange)' : s.status === 'online' ? 'var(--green)' : 'var(--red)';
      // 3-row grid: 24px name | 20px WAN | 1fr stats
      html += '<div class="card" style="padding:14px;border-left:3px solid '+borderColor+';display:grid;grid-template-rows:24px 20px 1fr;height:100%;cursor:pointer;" onclick="showSiteDetail('+idx+')">';

      // ROW 1: name + dot (24px)
      html += '<div style="display:flex;align-items:center;height:24px;overflow:hidden;">';
      html += '<strong style="font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0;" title="'+(s.name||'')+'">'+(s.name||t('lbl_unknown','Unknown'))+'</strong>';
      html += '<span style="width:8px;height:8px;border-radius:50%;background:'+statusColor+';flex-shrink:0;margin-left:8px;"></span>';
      html += '</div>';

      // ROW 2: WAN IP (20px)
      html += '<div style="font-size:12px;color:var(--text-muted);line-height:20px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + t('wan') + ' <strong style="color:var(--text);">'+(s.wan_ip||'-')+'</strong></div>';

      // ROW 3: stats grid (1fr) — ALWAYS 6 fields
      html += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:3px;font-size:12px;color:var(--text-muted);align-content:start;padding-top:6px;">';
      html += '<span>' + t('lbl_devices','Devices') + ': <strong>'+(s.device_count||0)+'</strong>'+(s.offline_devices>0?' <span style="color:var(--red);">('+s.offline_devices+'⬇)</span>':'')+'</span>';
      html += '<span>' + t('lbl_clients','Clients') + ': '+(s.client_count||0)+'</span>';
      html += '<span>' + t('lbl_model','Model') + ': '+(s.model||'-')+'</span>';
      html += '<span>ISP: '+(s.isp||'-')+'</span>';
      html += '<span>FW: '+(s.firmware||'-')+'</span>';
      html += '<span>SSID: '+(s.wifi_networks||s.ssid_count||'-')+'</span>';
      html += '</div>';

      html += '</div>';
    });
    html += '</div>';
  }

  return html;
}

function showSubSiteDetail(hostIdx, subIdx) {
  var host = _unifiSites[hostIdx];
  if (!host || !host.sub_sites) return;
  var s = host.sub_sites[subIdx];
  if (!s) return;

  var el = document.getElementById('dash-sites-content');
  var html = '<div style="max-width:600px;">';
  html += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">';
  html += '<button class="btn btn-ghost" onclick="dashLoadSites()" style="padding:4px 10px;font-size:12px;">' + t('tilbake') + '</button>';
  html += '<h3 style="font-size:16px;font-weight:700;margin:0;">'+s.name+'</h3>';
  html += '<span style="font-size:12px;color:var(--text-muted);">del av '+host.name+'</span>';
  html += '</div>';

  // Status cards row
  var cards = [
    {label:t('lbl_devices','Devices'), value:s.device_count, sub: (s.wifi_devices||0)+' AP, '+(s.wired_devices||0)+' '+t('lbl_switch','switch')+(s.gateway_devices?' , '+s.gateway_devices+' gateway':''), color:'var(--blue)'},
    {label:t('lbl_clients','Clients'), value:s.client_count, sub: (s.wifi_clients||0)+' '+t('lbl_wireless_short','wireless')+', '+(s.wired_clients||0)+' '+t('lbl_wired_short','wired'), color:'var(--green)'},
    {label:t('lbl_guests','Guests'), value:s.guest_count, sub:'', color:'var(--purple)'},
    {label:t('lbl_wifi_networks','WiFi networks'), value:s.wifi_networks||0, sub:'', color:'var(--orange)'},
    {label:t('lbl_networks_vlan','Networks/VLAN'), value:s.lan_networks||0, sub:'', color:'var(--blue)'},
  ];
  html += '<div class="card-grid card-grid--kpi" style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;grid-auto-rows:1fr;margin-bottom:16px;">';
  cards.forEach(function(c) {
    html += '<div class="card" style="padding:12px;text-align:center;border-top:2px solid '+c.color+';">';
    html += '<div style="font-size:22px;font-weight:700;color:var(--text);">'+c.value+'</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);font-weight:600;">'+c.label+'</div>';
    if (c.sub) html += '<div style="font-size:10px;color:var(--text-dim);margin-top:2px;">'+c.sub+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // Detail sections
  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">';

  // Enheter-boks
  html += '<div class="card" style="padding:14px;">';
  html += '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">' + t('enheter') + '</div>';
  html += '<table style="width:100%;font-size:12px;">';
  html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:6px;color:var(--text-muted);">' + t('wifi_ap_er') + '</td><td style="padding:6px;text-align:right;">'+(s.wifi_devices||0)+'</td></tr>';
  html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:6px;color:var(--text-muted);">' + t('svitsjer_kabel') + '</td><td style="padding:6px;text-align:right;">'+(s.wired_devices||0)+'</td></tr>';
  if (s.gateway_devices) html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:6px;color:var(--text-muted);">' + t('gateway_3') + '</td><td style="padding:6px;text-align:right;">'+s.gateway_devices+'</td></tr>';
  html += '<tr style="font-weight:600;"><td style="padding:6px;">' + t('totalt') + '</td><td style="padding:6px;text-align:right;">'+s.device_count+'</td></tr>';
  html += '</table></div>';

  // Klienter-boks
  html += '<div class="card" style="padding:14px;">';
  html += '<div style="font-size:13px;font-weight:600;margin-bottom:8px;">' + t('lbl_clients','Clients') + '</div>';
  html += '<table style="width:100%;font-size:12px;">';
  html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:6px;color:var(--text-muted);">' + t('lbl_wireless','Wireless') + '</td><td style="padding:6px;text-align:right;">'+(s.wifi_clients||0)+'</td></tr>';
  html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:6px;color:var(--text-muted);">' + t('lbl_wired','Wired') + '</td><td style="padding:6px;text-align:right;">'+(s.wired_clients||0)+'</td></tr>';
  html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:6px;color:var(--text-muted);">' + t('lbl_guests','Guests') + '</td><td style="padding:6px;text-align:right;">'+(s.guest_count||0)+'</td></tr>';
  html += '<tr style="font-weight:600;"><td style="padding:6px;">' + t('totalt') + '</td><td style="padding:6px;text-align:right;">'+((s.wifi_clients||0)+(s.wired_clients||0))+'</td></tr>';
  html += '</table></div>';

  html += '</div>';  // grid end

  // Status & helsetabell
  html += '<div class="card" style="padding:16px;">';
  html += '<div style="font-size:13px;font-weight:600;margin-bottom:10px;">' + t('status_3') + '</div>';
  html += '<table style="width:100%;font-size:13px;">';
  var rows = [];

  // Offline
  if (s.offline_devices > 0) {
    rows.push(['Offline enheter', '<span style="color:var(--red);font-weight:600;">'+s.offline_devices+'</span> ('+(s.offline_wifi||0)+' WiFi, '+(s.offline_wired||0)+' kabel)']);
  } else {
    rows.push(['Offline enheter', '<span style="color:var(--green);">' + t('ingen_alt_online') + '</span>']);
  }

  // Updates
  if (s.pending_updates > 0) {
    rows.push(['Ventende oppdateringer', '<span style="color:var(--orange);font-weight:600;">'+s.pending_updates+' enhet(er)</span>']);
  } else {
    rows.push(['Firmware', '<span style="color:var(--green);">' + t('alt_oppdatert') + '</span>']);
  }

  // Alerts
  if (s.critical_notifications > 0) {
    rows.push([t('lbl_critical_alerts','Critical alerts'), '<span style="color:var(--red);font-weight:600;">'+s.critical_notifications+'</span>']);
  }

  // WiFi health
  if (s.tx_retry_pct > 0) {
    var retryColor = s.tx_retry_pct > 10 ? 'var(--red)' : s.tx_retry_pct > 5 ? 'var(--orange)' : 'var(--green)';
    rows.push(['WiFi TX Retry', '<span style="color:'+retryColor+';font-weight:600;">'+s.tx_retry_pct+'%</span>' + (s.tx_retry_pct > 10 ? ' — ' + t('lbl_high_check_interference','high, check interference/placement') : s.tx_retry_pct > 5 ? ' — ' + t('lbl_moderate','moderate') : ' — ' + t('lbl_good','good'))]);
  }

  // Infra
  rows.push(['', '']);
  rows.push(['WiFi-nettverk (SSID)', (s.wifi_networks||0) + ' stk']);
  rows.push(['Nettverk / VLAN', (s.lan_networks||0) + ' stk']);
  if (s.gateway_model) rows.push(['Gateway', s.gateway_model]);
  if (s.isp) rows.push(['ISP', s.isp]);
  rows.push(['Tidssone', s.timezone || '-']);

  rows.forEach(function(r) {
    if (r[0] === '' && r[1] === '') {
      html += '<tr><td colspan="2" style="padding:6px;border-bottom:1px solid var(--border);"></td></tr>';
    } else {
      html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:8px;color:var(--text-muted);width:180px;">'+r[0]+'</td><td style="padding:8px;">'+r[1]+'</td></tr>';
    }
  });
  html += '</table></div>';

  // Placeholder for async-loaded data (devices, WAN, ISP)
  html += '<div id="subsite-devices" style="margin-top:16px;"><div class="loader" style="width:16px;height:16px;margin:8px auto;"></div></div>';
  html += '<div id="subsite-wan" style="margin-top:16px;"></div>';

  // Live client/WiFi data section — tries to match site to a customer
  html += '<div id="subsite-live-data" style="margin-top:16px;"></div>';
  html += '</div>';

  if (el) el.innerHTML = html;

  // Try to load live UniFi data by matching site name to a customer
  _loadSubSiteLiveData(s.name);

  // Load devices — only works for standalone consoles, not cloud controllers
  if (host.type !== 'network-server') {
    _loadSubSiteDevices(host, s);
  } else {
    // For cloud controllers, show device type breakdown instead of empty table
    var devEl = document.getElementById('subsite-devices');
    if (devEl && s.device_count > 0) {
      var dhtml = '<div class="card" style="padding:16px;">';
      dhtml += '<div style="font-size:13px;font-weight:600;margin-bottom:10px;">Enheter ('+s.device_count+')</div>';
      dhtml += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;">';
      var types = [
        {label:'WiFi AP', count:s.wifi_devices||0, icon:'📡'},
        {label:'Svitsj/kabel', count:s.wired_devices||0, icon:'🔌'},
        {label:'Gateway', count:s.gateway_devices||0, icon:'🛡'},
      ];
      types.forEach(function(t) {
        if (t.count > 0) {
          dhtml += '<div style="background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:10px;text-align:center;">';
          dhtml += '<div style="font-size:18px;">'+t.icon+'</div>';
          dhtml += '<div style="font-size:18px;font-weight:700;">'+t.count+'</div>';
          dhtml += '<div style="font-size:11px;color:var(--text-muted);">'+t.label+'</div>';
          dhtml += '</div>';
        }
      });
      dhtml += '</div>';
      if (s.offline_devices > 0) {
        dhtml += '<div style="margin-top:8px;font-size:12px;color:var(--red);">'+s.offline_devices+' offline ('+(s.offline_wifi||0)+' WiFi, '+(s.offline_wired||0)+' ' + t('lbl_wired_short','wired') + ')</div>';
      }
      dhtml += '<div style="margin-top:8px;font-size:11px;color:var(--text-dim);">' + t('msg_device_list_requires_api_key','Detailed device list requires Organization API key (Connector API)') + '</div>';
      dhtml += '</div>';
      devEl.innerHTML = dhtml;
    } else if (devEl) {
      devEl.innerHTML = '';
    }
  }
  // Load WAN details for this site
  _loadSubSiteWan(s);
  return; // prevent fall-through to the old closing
}

async function _loadSubSiteLiveData(siteName) {
  var el = document.getElementById('subsite-live-data');
  if (!el) return;

  // Try to match site name to a customer with UniFi configured
  if (!_overviewData || !_overviewData.customers) {
    try {
      var ov = await apiFetch('/api/dashboard/overview');
      if (ov) _overviewData = {customers: ov.customers || [], active_id: ov.active_id};
    } catch(e) {}
  }
  if (!_overviewData || !_overviewData.customers) return;

  // Find customer by matching site name (fuzzy — contains)
  var matched = null;
  var sLower = siteName.toLowerCase().replace(/[^a-z0-9]/g, '');
  _overviewData.customers.forEach(function(c) {
    var cLower = (c.customer_name||'').toLowerCase().replace(/[^a-z0-9]/g, '');
    if (cLower && sLower && (cLower.indexOf(sLower) >= 0 || sLower.indexOf(cLower) >= 0)) {
      matched = c;
    }
  });

  if (!matched) {
    el.innerHTML = '';
    return;
  }

  var cid = matched.customer_id || matched._id;
  el.innerHTML = '<div class="card" style="padding:16px;border-left:3px solid var(--blue);"><div style="font-size:13px;font-weight:600;margin-bottom:8px;">'+t('hdr_live_data','Live data')+' — '+esc(matched.customer_name)+'</div><div class="loader" style="width:14px;height:14px;display:inline-block;"></div></div>';

  // Fetch clients and WiFi health in parallel
  var results = await Promise.all([
    apiFetch('/api/unifi/clients/' + cid),
    apiFetch('/api/unifi/wifi-health/' + cid)
  ]);
  var clientData = results[0];
  var wifiData = results[1];

  var h = '<div class="card" style="padding:16px;border-left:3px solid var(--blue);">';
  h += '<div style="font-size:13px;font-weight:600;margin-bottom:12px;">'+t('hdr_live_data','Live data')+' — '+esc(matched.customer_name)+'</div>';

  // Clients
  if (clientData && clientData.clients && clientData.clients.length) {
    var clients = clientData.clients;
    h += '<div style="font-size:12px;font-weight:600;margin-bottom:6px;">'+t('hdr_connected_clients','Connected clients')+' ('+clients.length+': '+(clientData.wireless||0)+' '+t('lbl_wireless_short','wireless')+', '+(clientData.wired||0)+' '+t('lbl_wired_short','wired')+')</div>';
    h += '<div style="max-height:300px;overflow-y:auto;"><table style="width:100%;border-collapse:collapse;font-size:11px;">';
    h += '<thead><tr style="border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--bg-card);"><th style="text-align:left;padding:4px 6px;">'+t('col_hostname','Hostname')+'</th><th style="text-align:left;padding:4px 6px;">IP</th><th style="text-align:center;padding:4px 6px;">'+t('col_type','Type')+'</th><th style="text-align:center;padding:4px 6px;">'+t('col_signal','Signal')+'</th><th style="text-align:left;padding:4px 6px;">'+t('col_connected_to','Connected to')+'</th></tr></thead><tbody>';
    clients.slice(0, 50).forEach(function(c) {
      var typeIcon = c.type === 'wireless' ? '📶' : '🔌';
      var sigHtml = '-';
      if (c.signal && c.type === 'wireless') {
        var sigColor = c.signal > -60 ? 'var(--green)' : c.signal > -75 ? 'var(--orange)' : 'var(--red)';
        sigHtml = '<span style="color:'+sigColor+';font-weight:600;">'+c.signal+' dBm</span>';
      }
      h += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:3px 6px;">'+esc(c.hostname||c.name||c.mac||'-')+'</td><td style="padding:3px 6px;font-family:var(--mono);font-size:10px;">'+esc(c.ip||'-')+'</td><td style="padding:3px 6px;text-align:center;">'+typeIcon+'</td><td style="padding:3px 6px;text-align:center;">'+sigHtml+'</td><td style="padding:3px 6px;font-size:10px;color:var(--text-muted);">'+esc(c.connected_to||'-')+'</td></tr>';
    });
    if (clients.length > 50) h += '<tr><td colspan="5" style="padding:6px;text-align:center;color:var(--text-muted);font-size:10px;">... og '+(clients.length-50)+' til</td></tr>';
    h += '</tbody></table></div>';
  } else {
    h += '<div style="font-size:11px;color:var(--text-muted);">'+t('msg_no_client_data','No client data available — check UniFi controller config on customer.')+'</div>';
  }

  // WiFi health
  if (wifiData && wifiData.aps && wifiData.aps.length) {
    h += '<div style="font-size:12px;font-weight:600;margin:12px 0 6px;">'+t('hdr_wifi_health','WiFi Health')+'</div>';
    if (wifiData.alerts && wifiData.alerts.length) {
      wifiData.alerts.forEach(function(a) {
        var ac = a.severity === 'critical' ? 'var(--red)' : 'var(--orange)';
        h += '<div style="font-size:11px;color:'+ac+';margin-bottom:2px;">⚠ '+esc(a.message)+'</div>';
      });
    }
    h += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:4px;">';
    h += '<thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:4px 6px;">AP</th><th style="text-align:center;padding:4px 6px;">'+t('lbl_clients','Clients')+'</th><th style="text-align:center;padding:4px 6px;">'+t('col_channel','Channel')+'</th><th style="text-align:center;padding:4px 6px;">'+t('col_satisfaction','Satisfaction')+'</th></tr></thead><tbody>';
    wifiData.aps.forEach(function(ap) {
      var satColor = (ap.satisfaction||0) >= 80 ? 'var(--green)' : (ap.satisfaction||0) >= 60 ? 'var(--orange)' : 'var(--red)';
      h += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:3px 6px;font-weight:500;">'+esc(ap.name||'-')+'</td><td style="padding:3px 6px;text-align:center;">'+ap.clients+'</td><td style="padding:3px 6px;text-align:center;font-size:10px;">'+esc(ap.channel||'-')+'</td><td style="padding:3px 6px;text-align:center;"><span style="color:'+satColor+';font-weight:600;">'+(ap.satisfaction||'-')+'%</span></td></tr>';
    });
    h += '</tbody></table>';
  }

  h += '</div>';
  el.innerHTML = h;
}

async function _loadSubSiteDevices(host, site) {
  var el = document.getElementById('subsite-devices');
  if (!el) return;
  var data = await apiFetch('/api/unifi/sm/devices?host_id='+encodeURIComponent(host.id));
  if (!data || !data.devices) { el.innerHTML = ''; return; }

  // Filter devices — show all for this host (we can't filter per-site via API)
  var devices = data.devices;
  var online = devices.filter(function(d){return d.status==='online';}).length;
  var offline = devices.filter(function(d){return d.status!=='online';}).length;

  var html = '<div class="card" style="padding:16px;">';
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">';
  html += '<div style="font-size:13px;font-weight:600;">Enheter ('+devices.length+')</div>';
  html += '<div style="font-size:12px;color:var(--text-muted);">'+online+' online';
  if (offline > 0) html += ', <span style="color:var(--red);">'+offline+' offline</span>';
  html += '</div></div>';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="border-bottom:1px solid var(--border);background:var(--bg);">';
  html += '<th style="text-align:left;padding:6px;">' + t('navn_4') + '</th>';
  html += '<th style="text-align:left;padding:6px;">' + t('modell') + '</th>';
  html += '<th style="text-align:left;padding:6px;">IP</th>';
  html += '<th style="text-align:center;padding:6px;">' + t('status_3') + '</th>';
  html += '<th style="text-align:left;padding:6px;">' + t('firmware_3') + '</th>';
  html += '<th style="text-align:left;padding:6px;">' + t('oppetid') + '</th>';
  html += '</tr></thead><tbody>';
  devices.forEach(function(d) {
    var statusColor = d.status === 'online' ? 'var(--green)' : 'var(--red)';
    var dot = '<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:'+statusColor+';"></span>';
    var fwBadge = '';
    if (d.firmware_status === 'updateAvailable') fwBadge = ' <span style="color:var(--orange);font-size:10px;" title="'+d.update_available+'">⬆</span>';
    html += '<tr style="border-bottom:1px solid var(--border);">';
    html += '<td style="padding:6px;font-weight:600;">'+(d.name||d.mac)+(d.is_console?' <span style="font-size:10px;color:var(--blue);">' + t('konsoll_2') + '</span>':'')+'</td>';
    html += '<td style="padding:6px;color:var(--text-muted);">'+d.model+'</td>';
    html += '<td style="padding:6px;font-family:var(--mono);font-size:11px;">'+(d.ip||'-')+'</td>';
    html += '<td style="padding:6px;text-align:center;">'+dot+'</td>';
    html += '<td style="padding:6px;font-family:var(--mono);font-size:11px;">'+(d.firmware||'-')+fwBadge+'</td>';
    html += '<td style="padding:6px;color:var(--text-muted);">'+(d.uptime||'-')+'</td>';
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  el.innerHTML = html;
}

async function _loadSubSiteWan(site) {
  var el = document.getElementById('subsite-wan');
  if (!el || !site.site_id) return;
  var data = await apiFetch('/api/unifi/sm/site/'+encodeURIComponent(site.site_id)+'/wan');
  if (!data || !data.ok) { el.innerHTML = ''; return; }

  var html = '';

  // WAN interfaces
  if (data.wans && data.wans.length) {
    html += '<div class="card" style="padding:16px;margin-bottom:12px;">';
    html += '<div style="font-size:13px;font-weight:600;margin-bottom:10px;">' + t('wan_grensesnitt') + '</div>';
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px;">';
    data.wans.forEach(function(w) {
      var uptimeColor = w.uptime_pct >= 99 ? 'var(--green)' : w.uptime_pct >= 95 ? 'var(--orange)' : 'var(--red)';
      html += '<div style="background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:12px;">';
      html += '<div style="font-weight:600;margin-bottom:6px;">'+w.name+'</div>';
      html += '<div style="font-size:12px;color:var(--text-muted);display:grid;gap:3px;">';
      if (w.external_ip) html += '<span>' + t('ekstern_ip') + ' <strong style="color:var(--text);">'+w.external_ip+'</strong></span>';
      if (w.isp) html += '<span>ISP: '+w.isp+(w.isp_org ? ' ('+w.isp_org+')' : '')+'</span>';
      html += '<span>' + t('uptime') + ' <span style="color:'+uptimeColor+';font-weight:600;">'+w.uptime_pct+'%</span></span>';
      if (w.issues && w.issues.length) html += '<span style="color:var(--red);">'+w.issues.length+' problem(er)</span>';
      html += '</div></div>';
    });
    html += '</div></div>';
  }

  // Gateway security
  if (data.gateway && data.gateway.model) {
    var gw = data.gateway;
    html += '<div class="card" style="padding:16px;">';
    html += '<div style="font-size:13px;font-weight:600;margin-bottom:10px;">' + t('gateway_sikkerhet') + '</div>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:3px;font-size:12px;color:var(--text-muted);">';
    html += '<span>' + t('modell') + ' <strong style="color:var(--text);">'+gw.model+'</strong></span>';
    var idsColor = gw.ids_mode === 'ids' || gw.ids_mode === 'ips' ? 'var(--green)' : 'var(--orange)';
    html += '<span>' + t('ids_ips') + ' <span style="color:'+idsColor+';font-weight:600;">'+gw.ids_mode.toUpperCase()+'</span></span>';
    html += '<span>Inspeksjon: '+gw.inspection+'</span>';
    if (gw.ips_rules) html += '<span>IPS-regler: '+gw.ips_rules.toLocaleString()+'</span>';
    html += '</div></div>';
  }

  el.innerHTML = html;

  if (el) el.innerHTML = html;
}

function showSiteDetail(idx) {
  var s = _unifiSites[idx];
  if (!s) return;
  var html = '<div style="max-width:600px;">';
  html += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">';
  html += '<button class="btn btn-ghost" onclick="dashLoadSites()" style="padding:4px 10px;font-size:12px;">' + t('tilbake') + '</button>';
  html += '<h3 style="font-size:16px;font-weight:700;margin:0;">'+(s.name||'-')+'</h3>';
  html += '</div>';

  // ── Detail card: strict table, ALL rows always rendered ──
  html += '<div class="card" style="padding:16px;">';
  html += '<table style="width:100%;font-size:13px;">';
  var statusHtml = '<span style="color:'+(s.status==='online'?'var(--green)':'var(--red)')+';font-weight:600;">'+(s.status ? s.status.toUpperCase() : '-')+'</span>';
  var fwHtml = (s.firmware||'-') + (s.firmware_update ? ' &rarr; <span style="color:var(--orange);">'+s.firmware_update+' tilgjengelig</span>' : '');
  var devHtml = (s.device_count!=null ? s.device_count : '-') + (s.offline_devices > 0 ? ' <span style="color:var(--red);">('+s.offline_devices+' offline)</span>' : '');
  var rows = [
    ['Status',          statusHtml],
    ['WAN IP',          s.wan_ip || '-'],
    ['Modell',          s.model_full || s.model || '-'],
    ['Firmware',        fwHtml],
    ['MAC',             s.mac || '-'],
    ['Serienummer',     s.serial || '-'],
    ['ISP',             s.isp || '-'],
    ['Enheter',         devHtml],
    ['Klienter',        s.client_count != null ? s.client_count : '-'],
    ['Siter',           s.site_count != null ? s.site_count : '-'],
    ['Registrert',      s.registered ? new Date(s.registered).toLocaleDateString('no-NO') : '-'],
    ['Siste backup',    s.last_backup ? new Date(s.last_backup).toLocaleString('no-NO') : '-'],
    ['Siste tilkobling',s.last_connection ? new Date(s.last_connection).toLocaleString('no-NO') : '-'],
  ];
  rows.forEach(function(r) {
    html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:8px;color:var(--text-muted);width:140px;">'+r[0]+'</td><td style="padding:8px;">'+r[1]+'</td></tr>';
  });
  html += '</table></div>';

  // ── Sub-sites table: always render (show empty-state row if none) ──
  html += '<div style="margin-top:16px;"><h4 style="font-size:14px;font-weight:600;margin-bottom:8px;">Siter ('+((s.sub_sites && s.sub_sites.length) || 0)+')</h4>';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="border-bottom:1px solid var(--border);background:var(--bg);">'
    + '<th style="text-align:left;padding:8px;">' + t('kundesite') + '</th>'
    + '<th style="text-align:center;padding:8px;">' + t('enheter') + '</th>'
    + '<th style="text-align:center;padding:8px;">' + t('offline_2') + '</th>'
    + '<th style="text-align:center;padding:8px;">' + t('wifi') + '</th>'
    + '<th style="text-align:center;padding:8px;">' + t('kabel') + '</th>'
    + '<th style="text-align:center;padding:8px;">' + t('gjest') + '</th>'
    + '<th style="text-align:center;padding:8px;">WLAN</th>'
    + '</tr></thead><tbody>';
  if (s.sub_sites && s.sub_sites.length) {
    var totDev=0,totOff=0,totWifi=0,totWired=0,totGuest=0,totWlan=0;
    s.sub_sites.forEach(function(sub) {
      var offVal = sub.offline_devices || 0;
      var offStyle = offVal > 0 ? 'color:var(--red);font-weight:600;' : '';
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += '<td style="padding:8px;font-weight:600;">'+(sub.name||'-')+'</td>';
      html += '<td style="padding:8px;text-align:center;">'+(sub.device_count!=null ? sub.device_count : '-')+'</td>';
      html += '<td style="padding:8px;text-align:center;'+offStyle+'">'+offVal+'</td>';
      html += '<td style="padding:8px;text-align:center;">'+(sub.wifi_clients!=null ? sub.wifi_clients : '-')+'</td>';
      html += '<td style="padding:8px;text-align:center;">'+(sub.wired_clients!=null ? sub.wired_clients : '-')+'</td>';
      html += '<td style="padding:8px;text-align:center;">'+(sub.guest_count!=null ? sub.guest_count : '-')+'</td>';
      html += '<td style="padding:8px;text-align:center;">'+(sub.wifi_networks!=null ? sub.wifi_networks : '-')+'</td>';
      html += '</tr>';
      totDev+=(sub.device_count||0); totOff+=offVal; totWifi+=(sub.wifi_clients||0); totWired+=(sub.wired_clients||0); totGuest+=(sub.guest_count||0); totWlan+=(sub.wifi_networks||0);
    });
    html += '<tr style="font-weight:700;background:var(--bg);">';
    html += '<td style="padding:8px;">' + t('totalt') + '</td>';
    html += '<td style="padding:8px;text-align:center;">'+totDev+'</td>';
    html += '<td style="padding:8px;text-align:center;'+(totOff>0?'color:var(--red);':'')+'">'+totOff+'</td>';
    html += '<td style="padding:8px;text-align:center;">'+totWifi+'</td>';
    html += '<td style="padding:8px;text-align:center;">'+totWired+'</td>';
    html += '<td style="padding:8px;text-align:center;">'+totGuest+'</td>';
    html += '<td style="padding:8px;text-align:center;">'+totWlan+'</td>';
    html += '</tr>';
  } else {
    html += '<tr><td colspan="7" style="padding:12px;text-align:center;color:var(--text-dim);">-</td></tr>';
  }
  html += '</tbody></table></div>';

  html += '</div>';

  var el = document.getElementById('dash-sites-content');
  if (el) el.innerHTML = html;
  // Also update in integration view if open
  var el2 = document.getElementById('unifi-sm-sites-list');
  if (el2 && el2.offsetParent) el2.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════
// TERMINAL
// ═══════════════════════════════════════════════════════════════════

var _termWs = null;
var _xterm = null;
var _xtermFit = null;

function _termEnsureXterm() {
  if (_xterm) return;
  var container = document.getElementById('term-container');
  container.innerHTML = '';
  _xterm = new Terminal({
    cursorBlink: true,
    fontSize: 14,
    fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
    theme: {
      background: '#0d1117',
      foreground: '#e6edf3',
      cursor: '#4d9fb5',
      selectionBackground: '#264f78',
      black: '#484f58', red: '#f85149', green: '#3fb950', yellow: '#d29922',
      blue: '#58a6ff', magenta: '#bc8cff', cyan: '#4d9fb5', white: '#e6edf3',
    },
  });
  _xtermFit = new FitAddon.FitAddon();
  _xterm.loadAddon(_xtermFit);
  _xterm.open(container);
  _xtermFit.fit();

  // Send keyboard input to WebSocket
  _xterm.onData(function(data) {
    if (_termWs && _termWs.readyState === WebSocket.OPEN) {
      _termWs.send(JSON.stringify({type: 'input', data: data}));
    }
  });

  // Handle resize
  _xterm.onResize(function(size) {
    if (_termWs && _termWs.readyState === WebSocket.OPEN) {
      _termWs.send(JSON.stringify({type: 'resize', cols: size.cols, rows: size.rows}));
    }
  });

  window.addEventListener('resize', function() { if (_xtermFit) _xtermFit.fit(); });
}

function termModeChanged() {
  var mode = document.getElementById('term-mode').value;
  var sshOpts = document.getElementById('term-ssh-opts');
  sshOpts.style.display = mode === 'ssh' ? 'flex' : 'none';
  if (mode === 'ssh') termLoadHosts();
}

async function termLoadHosts() {
  var sel = document.getElementById('term-host-select');
  var data = await apiFetch('/api/ssh/hosts');
  if (!data) return;
  sel.innerHTML = '<option value="">' + t('placeholder_select_host','Select host...') + '</option>';
  (data.hosts || []).forEach(function(h) {
    sel.innerHTML += '<option value="'+h.id+'">'+h.label+' ('+h.hostname+')</option>';
  });
}

var _termFontSize = parseInt(localStorage.getItem('sybr_term_fontsize') || '14');
function termChangeFontSize(delta) {
  _termFontSize = Math.max(10, Math.min(24, _termFontSize + delta));
  localStorage.setItem('sybr_term_fontsize', _termFontSize);
  if (window._term) {
    window._term.options.fontSize = _termFontSize;
    if (window._termFit) window._termFit.fit();
  }
}

function termConnect() {
  if (_termWs) termDisconnect();
  _termEnsureXterm();
  _xterm.clear();

  var mode = document.getElementById('term-mode').value;
  var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  var url = proto + '//' + location.host + '/api/ws/terminal?token=' + encodeURIComponent(_authToken) + '&mode=' + mode;

  if (mode === 'ssh') {
    var hostId = document.getElementById('term-host-select').value;
    var manual = document.getElementById('term-host-manual').value.trim();
    if (hostId) {
      url += '&host_id=' + encodeURIComponent(hostId);
    } else if (manual) {
      var parts = manual;
      var user = 'root', host = manual, port = 22;
      if (parts.indexOf('@') !== -1) { user = parts.split('@')[0]; parts = parts.split('@')[1]; }
      if (parts.indexOf(':') !== -1) { host = parts.split(':')[0]; port = parseInt(parts.split(':')[1]); } else { host = parts; }
      url += '&host=' + encodeURIComponent(host) + '&user=' + encodeURIComponent(user) + '&port=' + port;
    } else {
      showToast(t('err_select_host_or_manual','Select a host or enter host manually'), 'error');
      return;
    }
  }

  document.getElementById('term-status').textContent = t('vpn_connecting','Connecting...');
  document.getElementById('term-connect-btn').style.display = 'none';
  document.getElementById('term-disconnect-btn').style.display = 'inline-flex';

  _termWs = new WebSocket(url);

  _termWs.onopen = function() {
    document.getElementById('term-status').innerHTML = '<span style="color:var(--green);">' + t('tilkoblet') + '</span>';
    _xterm.focus();
    _xtermFit.fit();
    _termWs.send(JSON.stringify({type: 'resize', cols: _xterm.cols, rows: _xterm.rows}));
  };

  _termWs.onmessage = function(evt) {
    try {
      var msg = JSON.parse(evt.data);
      if (msg.type === 'output') {
        _xterm.write(msg.data);
      }
    } catch(e) {
      _xterm.write(evt.data);
    }
  };

  _termWs.onclose = function() {
    _xterm.write('\r\n\x1b[90m--- Sesjon avsluttet ---\x1b[0m\r\n');
    document.getElementById('term-status').innerHTML = '<span style="color:var(--text-muted);">' + t('frakoblet') + '</span>';
    document.getElementById('term-connect-btn').style.display = 'inline-flex';
    document.getElementById('term-disconnect-btn').style.display = 'none';
    _termWs = null;
  };

  _termWs.onerror = function() {
    document.getElementById('term-status').innerHTML = '<span style="color:var(--red);">' + t('tilkoblingsfeil') + '</span>';
  };
}

function termDisconnect() {
  if (_termWs) {
    _termWs.close();
    _termWs = null;
  }
}


// ═══════════════════════════════════════════════════════════════════
// GUACAMOLE JS CLIENT — direct WebSocket tunnel (no iframe)
// ═══════════════════════════════════════════════════════════════════

// Active Guacamole sessions for cleanup
var _guacSessions = {};

function _createGuacSession(containerId, token, connectionId) {
  var container = document.getElementById(containerId);
  if (!container) return null;
  container.innerHTML = '';
  container.style.width = '100%';
  container.style.height = 'calc(100vh - 140px)';
  container.style.overflow = 'hidden';
  container.tabIndex = 0;

  // Tunnel — use correct WS protocol based on page protocol
  var wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  var tunnel = new Guacamole.WebSocketTunnel(
    wsProto + '//' + window.location.host + '/guacamole/websocket-tunnel'
  );

  var client = new Guacamole.Client(tunnel);

  // Display element — force to top-left of container
  var displayEl = client.getDisplay().getElement();
  displayEl.style.cursor = 'none';
  displayEl.style.position = 'absolute';
  displayEl.style.top = '0';
  displayEl.style.left = '0';
  container.appendChild(displayEl);

  // Clipboard buffer for focus retry
  var _clipboardBuffer = '';

  // RDP -> Browser clipboard
  client.onclipboard = function(stream, mimetype) {
    if (mimetype !== 'text/plain') return;
    var data = '';
    stream.onblob = function(base64) {
      data += atob(base64);
    };
    stream.onend = function() {
      _clipboardBuffer = data;
      try {
        navigator.clipboard.writeText(data).catch(function(){});
      } catch(e) {}
    };
  };

  // Retry clipboard write on window focus
  var _focusHandler = function() {
    if (_clipboardBuffer) {
      try {
        navigator.clipboard.writeText(_clipboardBuffer).catch(function(){});
      } catch(e) {}
    }
  };
  window.addEventListener('focus', _focusHandler);

  // Browser -> RDP clipboard (paste event)
  var _pasteHandler = function(e) {
    var text = e.clipboardData.getData('text/plain');
    if (text) {
      var stream = client.createClipboardStream('text/plain');
      var writer = new Guacamole.StringWriter(stream);
      writer.sendText(text);
      writer.sendEnd();
    }
  };
  document.addEventListener('paste', _pasteHandler);

  // Mouse input
  var mouse = new Guacamole.Mouse(displayEl);
  function handleMouse(e) {
    container.focus();
    client.sendMouseState(e.state || e);
  }
  if (typeof mouse.on === 'function') {
    mouse.on('mousedown', handleMouse);
    mouse.on('mouseup', handleMouse);
    mouse.on('mousemove', handleMouse);
  } else {
    mouse.onmousedown = mouse.onmouseup = mouse.onmousemove = handleMouse;
  }

  // Fix Guacamole canvas visibility.
  // Guacamole sets default layer canvas z-index:-1 which hides it behind
  // parent divs with position:absolute. Fix: make all layer DIVS transparent
  // and shift canvas z-index up.
  function fixGuacLayers() {
    container.querySelectorAll('div').forEach(function(d) {
      if (d.style.position === 'absolute' && d.style.overflow === 'hidden') {
        d.style.background = 'none';
      }
    });
    container.querySelectorAll('canvas').forEach(function(c) {
      c.style.cursor = 'none';
      if (parseInt(c.style.zIndex) < 0) {
        c.style.zIndex = '0';
      }
    });
  }
  new MutationObserver(fixGuacLayers).observe(displayEl, { childList: true, subtree: true });
  // Run repeatedly during connection setup
  var _fixInterval = setInterval(fixGuacLayers, 200);
  setTimeout(function() { clearInterval(_fixInterval); }, 10000);

  // Keyboard input (only when container is focused)
  var keyboard = new Guacamole.Keyboard(container);
  keyboard.onkeydown = function(keysym) {
    // Intercept Ctrl+V (keysym 0x0076 with ctrl) — read clipboard and send to RDP
    if (keysym === 0x0076 && keyboard.pressed[0xFFE3]) { // 'v' + Ctrl
      if (navigator.clipboard && navigator.clipboard.readText) {
        navigator.clipboard.readText().then(function(text) {
          if (text) {
            var stream = client.createClipboardStream('text/plain');
            var writer = new Guacamole.StringWriter(stream);
            writer.sendText(text);
            writer.sendEnd();
            // Also send Ctrl+V to RDP so it pastes from remote clipboard
            setTimeout(function() {
              client.sendKeyEvent(1, keysym);
              setTimeout(function() { client.sendKeyEvent(0, keysym); }, 50);
            }, 100);
          }
        }).catch(function() {
          client.sendKeyEvent(1, keysym);
        });
        return;
      }
    }
    client.sendKeyEvent(1, keysym);
  };
  keyboard.onkeyup = function(keysym) { client.sendKeyEvent(0, keysym); };

  // Resize handler — debounced 300ms
  var _resizeTimer = null;
  function sendSize() {
    var w = container.offsetWidth;
    var h = container.offsetHeight;
    if (w > 0 && h > 0) {
      client.sendSize(w, h);
    }
  }
  var _resizeHandler = function() {
    clearTimeout(_resizeTimer);
    _resizeTimer = setTimeout(sendSize, 300);
  };
  window.addEventListener('resize', _resizeHandler);

  // State change — send size repeatedly after connect so RDP adjusts after login
  client.onstatechange = function(state) {
    if (state === Guacamole.Client.State.CONNECTED) {
      // Pulse resize: immediate, then at intervals to catch post-login adjustment
      var delays = [200, 1000, 2000, 4000, 6000, 10000];
      delays.forEach(function(ms) { setTimeout(sendSize, ms); });
    }
  };

  // Connect with actual container dimensions
  var w = Math.floor(container.offsetWidth * window.devicePixelRatio);
  var h = Math.floor(container.offsetHeight * window.devicePixelRatio);
  client.connect(
    'token=' + encodeURIComponent(token) +
    '&GUAC_DATA_SOURCE=mysql' +
    '&GUAC_ID=' + encodeURIComponent(connectionId) +
    '&GUAC_TYPE=c' +
    '&GUAC_WIDTH=' + w +
    '&GUAC_HEIGHT=' + h +
    '&GUAC_DPI=96'
  );

  container.focus();

  return {
    client: client,
    destroy: function() {
      try { client.disconnect(); } catch(e) {}
      keyboard.onkeydown = null;
      keyboard.onkeyup = null;
      window.removeEventListener('resize', _resizeHandler);
      window.removeEventListener('focus', _focusHandler);
      document.removeEventListener('paste', _pasteHandler);
      container.innerHTML = '';
    }
  };
}


// ═══════════════════════════════════════════════════════════════════
// REMOTE BROWSER — Guacamole VNC + Chromium on Xvfb (direct JS client)
// ═══════════════════════════════════════════════════════════════════

var _browserRunning = false;

function browserInit() {
  var el = document.getElementById('browser-content');
  if (!el) return;

  // Only build UI once
  if (document.getElementById('browser-url-input')) return;

  el.innerHTML =
    '<div style="display:flex;gap:6px;margin-bottom:12px;align-items:center;">' +
      '<input id="browser-url-input" type="text" placeholder="http://192.168.1.1" style="flex:1;padding:8px 14px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-family:var(--mono);font-size:13px;" onkeydown="if(event.key===\'Enter\')browserNavigate();">' +
      '<button class="btn btn-primary" id="browser-go-btn" onclick="browserNavigate()" style="padding:8px 16px;font-size:13px;">' + t('gaa') + '</button>' +
      '<button class="btn btn-success" id="browser-start-btn" onclick="browserStart()" style="padding:8px 16px;font-size:13px;">' + t('start_nettleser') + '</button>' +
      '<button class="btn btn-danger" id="browser-stop-btn" onclick="browserStop()" style="padding:8px 16px;font-size:13px;display:none;">' + t('stopp') + '</button>' +
      '<button class="btn btn-ghost" id="browser-fullscreen-btn" onclick="toggleFullscreen(\'browser-guac-container\')" style="padding:8px 12px;font-size:13px;display:none;" title="Fullskjerm">&#x26F6;</button>' +
      '<span id="browser-status" style="font-size:12px;color:var(--text-muted);min-width:80px;text-align:right;"></span>' +
    '</div>' +
    '<div id="browser-frame-wrap" style="border:1px solid var(--border);border-radius:8px;overflow:hidden;background:transparent;min-height:500px;position:relative;">' +
      '<div id="browser-placeholder" style="display:flex;align-items:center;justify-content:center;height:500px;color:#888;font-size:14px;">Klikk &laquo;Start nettleser&raquo; for &aring; &aring;pne en ekstern nettleser</div>' +
      '<div id="browser-guac-container" style="width:100%;height:calc(100vh - 160px);overflow:hidden;display:none;"></div>' +
    '</div>';

  // Check if a session is already running
  browserCheckStatus();
}

async function browserCheckStatus() {
  var data = await apiFetch('/api/browser/status');
  if (data && data.running && data.guac_token && data.guac_connection_id) {
    _browserRunning = true;
    _browserShowDirect(data.guac_token, data.guac_connection_id);
    browserUpdateButtons(true);
    if (data.url) {
      var input = document.getElementById('browser-url-input');
      if (input) input.value = data.url;
    }
  }
}

function browserUpdateButtons(running) {
  var startBtn = document.getElementById('browser-start-btn');
  var stopBtn = document.getElementById('browser-stop-btn');
  var fsBtn = document.getElementById('browser-fullscreen-btn');
  var goBtn = document.getElementById('browser-go-btn');
  if (startBtn) startBtn.style.display = running ? 'none' : '';
  if (stopBtn) stopBtn.style.display = running ? '' : 'none';
  if (fsBtn) fsBtn.style.display = running ? '' : 'none';
  if (goBtn) goBtn.disabled = !running;
}

function _browserShowDirect(token, connectionId) {
  var placeholder = document.getElementById('browser-placeholder');
  var guacContainer = document.getElementById('browser-guac-container');
  if (!guacContainer) return;

  if (placeholder) placeholder.style.display = 'none';
  guacContainer.style.display = 'block';

  // Destroy previous session if any
  if (_guacSessions.browser) {
    _guacSessions.browser.destroy();
    _guacSessions.browser = null;
  }

  var session = _createGuacSession('browser-guac-container', token, connectionId);
  if (session) {
    _guacSessions.browser = session;
  }
  var statusEl = document.getElementById('browser-status');
  if (statusEl) statusEl.innerHTML = '<span style="color:var(--green);">' + t('tilkoblet') + '</span>';
}

function openWebUI(url) {
  showView('browser');
  setTimeout(function() {
    var input = document.getElementById('browser-url-input');
    if (input) {
      input.value = url;
      browserStart();
    }
  }, 300);
}

async function browserStart() {
  var status = document.getElementById('browser-status');
  var input = document.getElementById('browser-url-input');
  var url = (input.value || '').trim();

  // Auto-add http:// if scheme is missing
  if (url && !/^https?:\/\//i.test(url)) {
    url = 'http://' + url;
    input.value = url;
  }

  // Request clipboard permission
  try {
    var perm = await navigator.permissions.query({name: 'clipboard-read'});
    if (perm.state === 'prompt') {
      await navigator.clipboard.readText().catch(function(){});
    }
  } catch(e) {}

  if (status) status.innerHTML = '<div class="loader" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:4px;"></div> Starter...';

  var data = await apiFetch('/api/browser/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url: url})
  });

  if (!data || !data.ok) {
    if (status) status.innerHTML = '<span style="color:var(--red);">' + esc(data && data.error ? data.error : 'Feil ved start') + '</span>';
    return;
  }

  _browserRunning = true;
  browserUpdateButtons(true);

  if (data.guac_token && data.guac_connection_id) {
    _browserShowDirect(data.guac_token, data.guac_connection_id);
  }
}

async function browserNavigate() {
  if (!_browserRunning) {
    // If not running, start instead
    await browserStart();
    return;
  }

  var input = document.getElementById('browser-url-input');
  var status = document.getElementById('browser-status');
  var url = (input.value || '').trim();
  if (!url) return;

  if (!/^https?:\/\//i.test(url)) {
    url = 'http://' + url;
    input.value = url;
  }

  if (status) status.innerHTML = '<div class="loader" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:4px;"></div> Navigerer...';

  var data = await apiFetch('/api/browser/navigate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url: url})
  });

  if (!data || !data.ok) {
    if (status) status.innerHTML = '<span style="color:var(--red);">' + esc(data && data.error ? data.error : 'Feil') + '</span>';
    return;
  }

  if (status) status.innerHTML = '<span style="color:var(--green);">' + t('tilkoblet') + '</span>';
}

async function browserStop() {
  var status = document.getElementById('browser-status');
  var placeholder = document.getElementById('browser-placeholder');
  var guacContainer = document.getElementById('browser-guac-container');

  if (status) status.innerHTML = '<div class="loader" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:4px;"></div> Stopper...';

  // Destroy Guacamole session
  if (_guacSessions.browser) {
    _guacSessions.browser.destroy();
    _guacSessions.browser = null;
  }

  var data = await apiFetch('/api/browser/stop', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'}
  });

  _browserRunning = false;
  browserUpdateButtons(false);

  if (guacContainer) { guacContainer.style.display = 'none'; guacContainer.innerHTML = ''; }
  if (placeholder) placeholder.style.display = 'flex';
  if (status) status.innerHTML = '';
}

function toggleFullscreen(elementId) {
  var el = document.getElementById(elementId);
  if (!el) return;
  if (document.fullscreenElement) {
    document.exitFullscreen();
  } else {
    el.requestFullscreen().catch(function() {});
  }
}
document.addEventListener('fullscreenchange', function() {
  // Trigger resize so Guacamole display re-scales in/out of fullscreen
  // Multiple delays to catch the DOM settling
  setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 100);
  setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 500);
});


// ═══════════════════════════════════════════════════════════════════
// REMOTE RDP — Apache Guacamole (direct JS client)
// ═══════════════════════════════════════════════════════════════════

var _rdpRunning = false;

function rdpInit() {
  var el = document.getElementById('rdp-content');
  if (!el) return;

  // Only build UI once
  if (document.getElementById('rdp-host-input')) return;

  el.innerHTML =
    '<div style="display:flex;gap:6px;margin-bottom:12px;align-items:center;flex-wrap:wrap;">' +
      '<input id="rdp-host-input" type="text" placeholder="Vert (f.eks. 192.168.1.10)" style="flex:2;min-width:160px;padding:8px 14px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-family:var(--mono);font-size:13px;">' +
      '<input id="rdp-port-input" type="text" placeholder="3389" style="width:70px;padding:8px 14px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-family:var(--mono);font-size:13px;">' +
      '<input id="rdp-user-input" type="text" placeholder="Brukernavn" style="flex:1;min-width:120px;padding:8px 14px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-family:var(--mono);font-size:13px;">' +
      '<input id="rdp-pass-input" type="password" placeholder="Passord" style="flex:1;min-width:120px;padding:8px 14px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-family:var(--mono);font-size:13px;" onkeydown="if(event.key===\'Enter\')rdpStart();">' +
      '<button class="btn btn-success" id="rdp-start-btn" onclick="rdpStart()" style="padding:8px 16px;font-size:13px;">' + t('koble_til') + '</button>' +
      '<button class="btn btn-danger" id="rdp-stop-btn" onclick="rdpStop()" style="padding:8px 16px;font-size:13px;display:none;">' + t('koble_fra') + '</button>' +
      '<button class="btn btn-ghost" id="rdp-fullscreen-btn" onclick="toggleFullscreen(\'rdp-guac-container\')" style="padding:8px 12px;font-size:13px;display:none;" title="Fullskjerm">&#x26F6;</button>' +
      '<span id="rdp-status" style="font-size:12px;color:var(--text-muted);min-width:80px;text-align:right;"></span>' +
    '</div>' +
    '<div id="rdp-frame-wrap" style="border:1px solid var(--border);border-radius:8px;overflow:hidden;background:transparent;position:relative;">' +
      '<div id="rdp-placeholder" style="display:flex;align-items:center;justify-content:center;height:calc(100vh - 180px);color:#888;font-size:14px;background:var(--bg);">' + t('fyll_inn_tilkoblingsdetaljer_og_klikk_la') + '</div>' +
      '<div id="rdp-guac-container" style="width:100%;height:calc(100vh - 180px);overflow:hidden;display:none;"></div>' +
    '</div>';

  // Check if a session is already running
  rdpCheckStatus();
}

async function rdpCheckStatus() {
  var data = await apiFetch('/api/rdp/status');
  if (data && data.running && data.guac_token && data.guac_connection_id) {
    _rdpRunning = true;
    _rdpShowDirect(data.guac_token, data.guac_connection_id);
    rdpUpdateButtons(true);
  }
}

function rdpUpdateButtons(running) {
  var startBtn = document.getElementById('rdp-start-btn');
  var stopBtn = document.getElementById('rdp-stop-btn');
  var fsBtn = document.getElementById('rdp-fullscreen-btn');
  var hostInput = document.getElementById('rdp-host-input');
  var portInput = document.getElementById('rdp-port-input');
  var userInput = document.getElementById('rdp-user-input');
  var passInput = document.getElementById('rdp-pass-input');
  if (startBtn) startBtn.style.display = running ? 'none' : '';
  if (stopBtn) stopBtn.style.display = running ? '' : 'none';
  if (fsBtn) fsBtn.style.display = running ? '' : 'none';
  if (hostInput) hostInput.disabled = running;
  if (portInput) portInput.disabled = running;
  if (userInput) userInput.disabled = running;
  if (passInput) passInput.disabled = running;
}

function _rdpShowDirect(token, connectionId) {
  var placeholder = document.getElementById('rdp-placeholder');
  var guacContainer = document.getElementById('rdp-guac-container');
  if (!guacContainer) return;

  if (placeholder) placeholder.style.display = 'none';
  guacContainer.style.display = 'block';

  // Destroy previous session if any
  if (_guacSessions.rdp) {
    _guacSessions.rdp.destroy();
    _guacSessions.rdp = null;
  }

  var session = _createGuacSession('rdp-guac-container', token, connectionId);
  if (session) {
    _guacSessions.rdp = session;
  }
  var statusEl = document.getElementById('rdp-status');
  if (statusEl) statusEl.innerHTML = '<span style="color:var(--green);">' + t('tilkoblet') + '</span>';
}

async function rdpStart() {
  var status = document.getElementById('rdp-status');
  var hostInput = document.getElementById('rdp-host-input');
  var portInput = document.getElementById('rdp-port-input');
  var userInput = document.getElementById('rdp-user-input');
  var passInput = document.getElementById('rdp-pass-input');

  var host = (hostInput.value || '').trim();
  if (!host) {
    showToast(t('vertsnavn_er_paakrevd'), 'error');
    hostInput.focus();
    return;
  }

  var port = parseInt(portInput.value, 10) || 3389;
  var username = (userInput.value || '').trim();
  var password = passInput.value || '';

  // Request clipboard permission
  try {
    var perm = await navigator.permissions.query({name: 'clipboard-read'});
    if (perm.state === 'prompt') {
      await navigator.clipboard.readText().catch(function(){});
    }
  } catch(e) {}

  if (status) status.innerHTML = '<div class="loader" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:4px;"></div> Kobler til...';

  var data = await apiFetch('/api/rdp/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({host: host, port: port, username: username, password: password})
  });

  if (!data || !data.ok) {
    if (status) status.innerHTML = '<span style="color:var(--red);">' + esc(data && data.error ? data.error : 'Feil ved tilkobling') + '</span>';
    return;
  }

  _rdpRunning = true;
  rdpUpdateButtons(true);

  if (data.guac_token && data.guac_connection_id) {
    _rdpShowDirect(data.guac_token, data.guac_connection_id);
  }
}

async function rdpStop() {
  var status = document.getElementById('rdp-status');
  var placeholder = document.getElementById('rdp-placeholder');
  var guacContainer = document.getElementById('rdp-guac-container');

  if (status) status.innerHTML = '<div class="loader" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:4px;"></div> Kobler fra...';

  // Destroy Guacamole session
  if (_guacSessions.rdp) {
    _guacSessions.rdp.destroy();
    _guacSessions.rdp = null;
  }

  await apiFetch('/api/rdp/stop', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'}
  });

  _rdpRunning = false;
  rdpUpdateButtons(false);

  if (guacContainer) { guacContainer.style.display = 'none'; guacContainer.innerHTML = ''; }
  if (placeholder) placeholder.style.display = 'flex';
  if (status) status.innerHTML = '';
}

