// Handlers for the markup this file builds: the docs tree, the ALSO and
// Uniweb import and match dialogs, and the task scheduler.
registerUiHandlers({
  docsRepoOpen: function(el) { docsRepoOpen(el.dataset.docsPath); },
  alsoDoImport: function() { alsoDoImport(); },
  alsoLinkMatched: function() { alsoLinkMatched(); },
  uniwebShowMatch: function(el) { uniwebShowMatch(el.dataset.id); },
  uniwebShowDetail: function(el) { uniwebShowDetail(el.dataset.id); },
  uniwebShowImport: function() { uniwebShowImport(); },
  uniwebDoMatch: function(el) { uniwebDoMatch(el.dataset.id); },
  uniwebCloseImportOnBackdrop: function(el, event) { if (event.target === el) uniwebCloseImport(); },
  uniwebCloseImport: function() { uniwebCloseImport(); },
  uniwebFilterImport: function() { uniwebFilterImport(); },
  uniwebToggleAllImport: function(el) { uniwebToggleAllImport(el.checked); },
  uniwebUpdateImportBtn: function() { uniwebUpdateImportBtn(); },
  uniwebDoImport: function() { uniwebDoImport(); },
  taskSchedToggle: function(el) { taskSchedToggle(el.dataset.id, el.checked); },
  taskSchedRunNow: function(el) { taskSchedRunNow(el.dataset.id, el); },
});

// What each view this file owns loads when it opens.
onViewShown('hosts', function() { hostsLoad(); });
onViewShown('ssh', function() { sshShowKeys(); });
onViewShown('vpn', function() { vpnLoadProfiles(); });
onViewShown('live', function() { livePollNow(); });
onViewShown('terminal', function() {
  var ts = document.getElementById('term-screen');
  if (ts) ts.focus();
});
onViewShown('pentest', function() { loadPentestCapabilities(); });
onViewShown('policy-overview', function() { policyOverviewLoad(); });
onViewShown('policy-deploy', function() { policyDeployLoad(); });
onViewShown('baseline-deploy', function() { baselineDeployLoad(); });
onViewShown('assessments', function() { assessmentsLoad(); });
onViewShown('tailscale', function() { tsLoadView(); });
onViewShown('browser', function() { browserInit(); });
onViewShown('rdp', function() { rdpInit(); });
onViewShown('docs', function() { docsRepoLoad(); });
onViewShown('ai', function() {
  aiLoadCustomers();
  var el = document.getElementById('ai-status');
  apiFetch('/api/claude/status').then(function(d) {
    if (!el || !d) return;
    if (d.available) { el.textContent = d.model; return; }
    // Not set up: say where, with a way there. The key lives on the Sybrt
    // AI card under Administrasjon › Integrasjoner.
    el.innerHTML = esc(t('msg_not_configured_setup_api_key', 'Ikke satt opp. Legg inn API-nøkkelen på Sybrt AI-kortet under Administrasjon › Integrasjoner.'))
      + ' ' + adminSignpostButton('integrations', 'btn_open_integrations', 'btn-ghost btn-sm');
  });
});


// ── In-app docs viewer ───────────────────────────────────────────────────
// The documents a person using the app reads: the changelog, and a user
// guide when the build has one. /api/docs/list names them and
// /api/docs/file returns one; it is rendered client-side with marked.js and
// sanitised through DOMPurify, so a document cannot run script in our
// origin. The API reference and Swagger are for administrators
// ([data-admin-only], hidden by CSS for everyone else).

var _docsRepoTreeLoaded = false;

async function docsRepoLoad() {
  if (_docsRepoTreeLoaded) return;
  var treeBox = document.getElementById('docs-repo-tree');
  if (!treeBox) return;
  treeBox.innerHTML = '<div class="docs-dim">' + esc(t('laster')) + '</div>';
  try {
    var data = await apiFetch('/api/docs/list');
    if (!data || !data.root) throw new Error('no tree');
    // The documents are not package data, so an install may carry none. Say
    // so instead of an empty list that reads as "there are no documents".
    if (data.available === false) {
      treeBox.innerHTML = '<div class="docs-unavailable">'
        + esc(t('docs_not_in_this_build',
                'Dokumentasjonen følger ikke med denne installasjonen.'))
        + '</div>';
      return;
    }
    var offered = _docsFileList(data.root);
    // One document needs no list to choose from.
    treeBox.innerHTML = offered.length > 1 ? _docsRenderTree(data.root) : '';
    treeBox.hidden = offered.length < 2;
    _docsRepoTreeLoaded = true;
    // Open the first document the listing offers (the user guide when there
    // is one). A name of our own here would be a second list, and the last
    // one drifted: it opened files docs/ did not hold.
    if (offered.length) docsRepoOpen(offered[0]);
  } catch (e) {
    treeBox.innerHTML = '<div class="docs-error">' + esc(t('integ_docs_load_failed','Kunne ikke laste dokumentasjon')) + ': ' + esc(String(e)) + '</div>';
  }
}

// Every file path in the listing, in the order it gives them.
function _docsFileList(node) {
  if (!node) return [];
  if (node.type === 'file') return [node.path];
  var out = [];
  (node.children || []).forEach(function(c) {
    out = out.concat(_docsFileList(c));
  });
  return out;
}

// The documents as buttons, titled in the reader's language.
function _docsRenderTree(root) {
  return (root.children || []).filter(function(n) { return n.type === 'file'; }).map(function(n) {
    var title = t('docs_title_' + n.key, '') || n.name.replace(/\.md$/i, '');
    return '<button type="button" class="docs-doc" data-docs-path="' + esc(n.path) + '" data-click-handler="docsRepoOpen">' + esc(title) + '</button>';
  }).join('');
}

async function docsRepoOpen(path) {
  var content = document.getElementById('docs-repo-content');
  if (!content) return;
  content.innerHTML = '<div style="color:var(--text-muted);">' + t('laster') + '</div>';
  try {
    var data = await apiFetch('/api/docs/file?path=' + encodeURIComponent(path));
    if (!data || !data.content) throw new Error('empty doc');
    if (typeof window.marked === 'undefined' || typeof window.DOMPurify === 'undefined') {
      // CDN not loaded — fall back to <pre> for at least a usable view
      content.innerHTML = '<pre style="white-space:pre-wrap;font-family:var(--mono);font-size:12px;">' + esc(data.content) + '</pre>';
      return;
    }
    var rendered = window.marked.parse(data.content, { gfm: true, breaks: false });
    content.innerHTML = /* safe-html: DOMPurify output */ window.DOMPurify.sanitize(rendered, { USE_PROFILES: { html: true } });
    content.scrollTop = 0;
    document.querySelectorAll('.docs-doc').forEach(function(el) {
      el.classList.toggle('is-active', el.getAttribute('data-docs-path') === path);
    });
  } catch (e) {
    content.innerHTML = '<div style="color:var(--color-danger);">' + t('integ_doc_open_failed','Kunne ikke åpne dokumentet') + ': ' + esc(String(e)) + '</div>';
  }
}

// ── ALSO Cloud Marketplace ───────────────────────────────────────────────────
async function alsoTestConnection() {
  var msg = document.getElementById('also-config-msg');
  msg.innerHTML = '<span style="color:var(--text-muted);">' + t('msg_testing','Testing...') + '</span>';
  try {
    var d = await apiFetch('/api/also/test', {
      onError: function(message) { msg.textContent = message; msg.style.color = 'var(--red)'; },
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        username: document.getElementById('input-also-username').value.trim(),
        password: document.getElementById('input-also-password').value.trim(),
        country: document.getElementById('input-also-country').value,
      })
    });
    if (!d) return;
    if (d.ok) {
      msg.innerHTML = '<span style="color:var(--green);">&#10003; ' + t('msg_connection_verified','Connection verified') + '</span>';
      document.getElementById('also-integ-dot').style.background = 'var(--green)';
      document.getElementById('also-integ-label').textContent = t('status_configured','Configured');
      document.getElementById('also-integ-label').style.color = 'var(--green)';
    } else {
      msg.innerHTML = '<span style="color:var(--red);">&#10007; ' + esc(d && d.error ? d.error : t('status_error')) + '</span>';
    }
  } catch(e) {
    msg.innerHTML = '<span style="color:var(--red);">' + esc(e.message) + '</span>';
  }
}

async function alsoSaveConfig() {
  var msg = document.getElementById('also-config-msg');
  var settings = await apiFetch('/api/settings');
  var body = Object.assign({}, settings || {}, {
    also_username: document.getElementById('input-also-username').value.trim(),
    also_password: document.getElementById('input-also-password').value.trim(),
    also_country: document.getElementById('input-also-country').value,
  });
  var d = await apiFetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  if (d && !d.error) {
    msg.innerHTML = '<span style="color:var(--green);">&#10003; ' + t('msg_saved','Saved') + '</span>';
    _integPaint('also', body.also_password ? 'ok' : 'off');
  } else {
    msg.innerHTML = '<span style="color:var(--red);">' + esc(d && d.error ? d.error : t('status_error')) + '</span>';
  }
}

async function alsoSyncCustomers() {
  var msg = document.getElementById('also-config-msg');
  msg.innerHTML = '<span style="color:var(--text-muted);">' + t('msg_loading','Loading...') + '</span>';
  try {
    var d = await apiFetch('/api/also/sync-preview');
    if (!d || d.error) { msg.innerHTML = '<span style="color:var(--red);">' + esc(d && d.error ? d.error : t('status_error')) + '</span>'; return; }

    var newC = d.customers.filter(function(c){return c.status === 'new'});
    var matched = d.customers.filter(function(c){return c.status === 'matched'});

    var html = '<div style="margin-top:var(--space-3);font-size:var(--font-sm);">'
      + '<div style="margin-bottom:var(--space-2);"><strong>' + t('also') + '</strong> ' + Number(d.also_total) + ' | <span style="color:var(--green);">Matched: ' + Number(d.matched) + '</span> | <span style="color:var(--blue);">New: ' + Number(d.new) + '</span></div>';

    if (newC.length > 0) {
      html += '<div style="max-height:200px;overflow-y:auto;border:1px solid var(--border);border-radius:var(--radius-md);margin-bottom:var(--space-3);">';
      newC.forEach(function(c) {
        html += '<label style="display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3);border-bottom:1px solid var(--border);font-size:var(--font-xs);cursor:pointer;">'
          + '<input type="checkbox" checked class="also-import-cb" data-name="' + esc(c.also_name) + '" data-domain="' + esc(c.also_domain||'') + '" data-id="' + esc(c.also_id||'') + '">'
          + '<span style="flex:1;">' + esc(c.also_name) + '</span>'
          + '<span style="color:var(--text-dim);font-family:var(--mono);font-size:10px;">' + esc(c.also_domain||'') + '</span>'
          + '</label>';
      });
      html += '</div>';
      html += '<button class="btn btn-primary btn-sm" data-write data-click-handler="alsoDoImport">' + t('btn_import','Import') + ' ' + newC.length + ' ' + t('nav_customers').toLowerCase() + '</button>';
    } else {
      html += '<div style="color:var(--green);">' + t('all_also_customers_already_matched') + '</div>';
    }

    if (matched.length > 0) {
      // Check how many are NOT yet linked (missing AlsoAccountId)
      var unlinked = matched.filter(function(c){return c.also_id && c.match && c.match.toolkit_id;});
      if (unlinked.length > 0) {
        html += '<div style="margin-top:var(--space-3);padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);display:flex;align-items:center;gap:var(--space-3);">';
        html += '<span style="font-size:var(--font-sm);flex:1;">' + unlinked.length + ' matched customers can be linked to ALSO for license viewing</span>';
        html += '<button class="btn btn-primary btn-sm" data-write data-click-handler="alsoLinkMatched" id="also-link-btn">' + t('link_all') + '</button>';
        html += '</div>';
      }
      html += '<details style="margin-top:var(--space-3);font-size:var(--font-xs);"><summary style="cursor:pointer;color:var(--text-muted);">Matched (' + matched.length + ')</summary><div style="max-height:150px;overflow-y:auto;margin-top:var(--space-2);">';
      matched.forEach(function(c) {
        var icon = c.match.match_type === 'exact_name' ? '&#10003;' : c.match.match_type === 'domain' ? '\u25CF' : '&#8776;';
        html += '<div style="padding:2px 0;display:flex;gap:var(--space-2);"><span>' + icon + '</span><span style="flex:1;">' + esc(c.also_name) + '</span><span style="color:var(--text-dim);">&rarr; ' + esc(c.match.toolkit_name) + '</span></div>';
      });
      html += '</div></details>';
      // Store matched data for the link action
      window._alsoMatchedForLink = unlinked;
    }
    html += '</div>';
    msg.innerHTML = html;
  } catch(e) {
    msg.innerHTML = '<span style="color:var(--red);">' + esc(e.message) + '</span>';
  }
}

async function alsoDoImport() {
  var cbs = document.querySelectorAll('.also-import-cb:checked');
  var toImport = [];
  cbs.forEach(function(cb) { toImport.push({name:cb.dataset.name, domain:cb.dataset.domain, also_id:cb.dataset.id}); });
  if (!toImport.length) { showToast(t('nothing_selected'),'warning'); return; }
  var d = await apiFetch('/api/also/sync-customers', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({customers:toImport})});
  if (d && d.ok) {
    showToast(t('msg_imported','Imported') + ' ' + d.imported + ' ' + t('nav_customers').toLowerCase(), 'success', 3000);
    document.getElementById('also-config-msg').innerHTML = '<span style="color:var(--green);">&#10003; ' + t('msg_imported','Importert') + ': ' + Number(d.imported) + '</span>';
  } else { showToast(d && d.error ? d.error : t('status_error'), 'error'); }
}

async function alsoLinkMatched() {
  var matches = window._alsoMatchedForLink || [];
  if (!matches.length) { showToast(t('no_matches_to_link'), 'warning'); return; }
  var btn = document.getElementById('also-link-btn');
  if (btn) { btn.disabled = true; btn.textContent = t('msg_linking','Linking …'); }

  var payload = matches.map(function(c) {
    return {toolkit_id: c.match.toolkit_id, also_id: c.also_id};
  });

  var d = await apiFetch('/api/also/link-matched', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({matches: payload})
  });
  if (d && d.ok) {
    showToast(t('linked') + ' ' + d.linked + ' customers to ALSO', 'success', 3000);
    if (btn) { btn.textContent = '✓ ' + d.linked + ' linked'; btn.style.background = 'var(--green)'; }
  } else {
    showToast(d && d.error ? d.error : 'Linking failed', 'error');
    if (btn) { btn.disabled = false; btn.textContent = t('btn_link_all','Link all'); }
  }
}

// ── Uniweb Hosting ──────────────────────────────────────────────────────────

async function uniwebSaveConfig() {
  var msg = document.getElementById('uniweb-config-msg');
  var email = document.getElementById('input-uniweb-email').value.trim();
  var password = document.getElementById('input-uniweb-password').value.trim();
  if (!email || !password) {
    msg.innerHTML = '<span style="color:var(--red);">' + t('e_post_og_passord_er') + '</span>';
    return;
  }
  var d = await apiFetch('/api/uniweb/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({email: email, password: password}),
  });
  if (d && d.ok) {
    msg.innerHTML = '<span style="color:var(--green);">' + t('lagret_2') + '</span>';
    _integPaint('uniweb', 'ok');
  } else {
    msg.innerHTML = '<span style="color:var(--red);">' + esc(d && d.error ? d.error : t('integ_error','Feil')) + '</span>';
  }
}

// Sync styles live in app.css so the application CSP can load them.


var _uniwebSyncStart = null;

function _uniwebFormatDuration(ms) {
  var secs = Math.floor(ms / 1000);
  if (secs < 60) return secs + 's';
  var mins = Math.floor(secs / 60);
  secs = secs % 60;
  return mins + 'm ' + (secs < 10 ? '0' : '') + secs + 's';
}

async function uniwebSync() {
  var msg = document.getElementById('uniweb-config-msg');
  var btn = document.getElementById('uniweb-sync-btn');
  msg.innerHTML = '<span style="color:var(--text-muted);">' + t('starter_synkronisering') + '</span>';
  if (btn) { btn.disabled = true; btn.textContent = t('msg_syncing','Synchronising …'); }
  _uniwebSyncStart = Date.now();

  var d = await apiFetch('/api/uniweb/sync', {method: 'POST'});
  if (d && d.ok) {
    uniwebPollStatus();
  } else {
    msg.innerHTML = '<span style="color:var(--red);">' + esc(d && d.error ? d.error : t('integ_error','Feil')) + '</span>';
    if (btn) { btn.disabled = false; btn.textContent = t('integ_sync','Synkroniser'); }
    _uniwebSyncStart = null;
  }
}

async function uniwebPollStatus() {
  var msg = document.getElementById('uniweb-config-msg');
  var btn = document.getElementById('uniweb-sync-btn');
  var d = await apiFetch('/api/uniweb/status');
  if (!d) return;

  if (d.running) {
    // Derive timing
    var startTime = d.sync_start_time ? new Date(d.sync_start_time).getTime() : (_uniwebSyncStart || Date.now());
    if (!_uniwebSyncStart) _uniwebSyncStart = startTime;
    var elapsed = Date.now() - startTime;
    var elapsedStr = _uniwebFormatDuration(elapsed);

    var synced = Number(d.accounts_synced) || 0;
    var total = Number(d.total_accounts) || 0;
    var pct = total > 0 ? Math.round((synced / total) * 100) : 0;

    // Estimate remaining time
    var etaStr = '—';
    if (synced > 0 && total > 0 && synced < total) {
      var msPerAccount = elapsed / synced;
      var remaining = (total - synced) * msPerAccount;
      etaStr = t('uniweb_approx').replace('{time}', _uniwebFormatDuration(remaining));
    }

    var accountLabel = d.current_account ? esc(d.current_account) : '...';

    var html = '<div class="uniweb-sync-panel uniweb-sync-active">';
    html += '<div class="uniweb-sync-row" style="margin-bottom:4px;">';
    html += '<span style="font-weight:600;color:var(--blue);">' + t('synkroniserer_uniweb') + '</span>';
    html += '<span class="uniweb-sync-value">' + t('uniweb_accounts_progress').replace('{done}', synced).replace('{total}', total || '?') + '</span>';
    html += '</div>';

    // Progress bar
    html += '<div class="uniweb-progress-track"><div class="uniweb-progress-fill" style="width:' + Math.max(pct, 2) + '%;"></div></div>';

    // Current account
    html += '<div class="uniweb-sync-row" style="margin-top:4px;">';
    html += '<span class="uniweb-sync-label">' + t('behandler') + ' <span style="color:var(--text-primary);">' + accountLabel + '</span></span>';
    html += '<span class="uniweb-sync-value">' + pct + '%</span>';
    html += '</div>';

    // Timing row
    html += '<div class="uniweb-sync-row" style="margin-top:4px;">';
    html += '<span class="uniweb-sync-label">' + t('uniweb_elapsed').replace('{time}', elapsedStr) + '</span>';
    html += '<span class="uniweb-sync-label">' + t('uniweb_remaining').replace('{time}', etaStr) + '</span>';
    html += '</div>';

    // Domains found so far
    if (d.domains_found > 0) {
      html += '<div class="uniweb-sync-row" style="margin-top:4px;">';
      html += '<span class="uniweb-sync-label">' + t('uniweb_domains_found').replace('{count}', Number(d.domains_found)) + '</span>';
      if (d.errors_count > 0) {
        html += '<span class="uniweb-sync-label" style="color:var(--orange);">' + t('integ_error','Feil') + ': ' + Number(d.errors_count) + '</span>';
      }
      html += '</div>';
    }

    html += '</div>';
    msg.innerHTML = html;

    setTimeout(uniwebPollStatus, 2000);
  } else {
    // Sync finished
    var totalElapsed = _uniwebSyncStart ? _uniwebFormatDuration(Date.now() - _uniwebSyncStart) : '';
    _uniwebSyncStart = null;

    if (d.last_error) {
      msg.innerHTML = '<div class="uniweb-sync-panel" style="border-color:var(--red);">'
        + '<span style="color:var(--red);font-weight:600;">' + t('synkronisering_feilet') + '</span>'
        + '<div style="margin-top:4px;color:var(--red);font-size:11px;">' + esc(d.last_error) + '</div>'
        + '</div>';
    } else {
      let html = '<div class="uniweb-sync-panel" style="border-color:var(--green);">';
      html += '<span style="color:var(--green);font-weight:600;">' + t('synkronisering_fullfort') + '</span>';
      if (totalElapsed) {
        html += '<span class="uniweb-sync-label" style="margin-left:8px;">(' + totalElapsed + ')</span>';
      }

      // Summary cards
      html += '<div class="uniweb-summary">';
      html += '<div class="uniweb-summary-card"><div class="val">' + (Number(d.total_accounts) || 0) + '</div><div class="lbl">' + t('kontoer') + '</div></div>';
      html += '<div class="uniweb-summary-card"><div class="val">' + (Number(d.domains_found) || 0) + '</div><div class="lbl">' + t('domener_2') + '</div></div>';
      if (d.errors_count > 0) {
        html += '<div class="uniweb-summary-card" style="border:1px solid var(--orange);"><div class="val" style="color:var(--orange);">' + Number(d.errors_count) + '</div><div class="lbl">' + t('feil') + '</div></div>';
      }
      html += '</div>';
      html += '</div>';
      msg.innerHTML = html;
    }

    if (btn) { btn.disabled = false; btn.textContent = t('integ_sync','Synkroniser'); }
    if (d.last_sync) {
      document.getElementById('uniweb-last-sync').textContent = t('lbl_last_synced','Last synced') + ': ' + new Date(d.last_sync).toLocaleString(_lang === 'en' ? 'en-GB' : 'nb-NO');
    }
    uniwebLoadAccounts();
  }
}

async function uniwebLoadAccounts() {
  var container = document.getElementById('uniweb-accounts-container');
  if (!container) return;

  var d = await apiFetch('/api/uniweb/accounts');
  if (!d || !d.accounts || d.accounts.length === 0) {
    container.innerHTML = '';
    return;
  }

  // Count unmatched accounts and show warning badge
  var unmatchedCount = d.accounts.filter(function(a) { return !a.customer_name; }).length;
  var unmatchedBadge = '';
  if (unmatchedCount > 0) {
    unmatchedBadge = ' <span style="display:inline-block;background:var(--orange);color:#fff;font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;margin-left:6px;">' + unmatchedCount + ' ' + t('integ_of','av') + ' ' + Number(d.total) + ' ' + t('integ_customers_unlinked','kunder ikke koblet') + '</span>';
  }

  var html = '<div style="font-size:12px;font-weight:600;margin-bottom:8px;">' + t('kontoer') + ' (' + Number(d.total) + ')' + unmatchedBadge + '</div>';
  html += '<div class="uniweb-accounts-scroll" role="region" aria-label="' + esc(t('uniweb_accounts_label')) + '" tabindex="0">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:11px;">';
  html += '<thead><tr style="background:var(--bg-tertiary);border-bottom:1px solid var(--border);">';
  html += '<th style="text-align:left;padding:6px 8px;">' + t('konto_4') + '</th>';
  html += '<th style="text-align:left;padding:6px 8px;">' + t('msp_kunde') + '</th>';
  html += '<th style="text-align:center;padding:6px 8px;">' + t('domener_2') + '</th>';
  html += '<th style="text-align:center;padding:6px 8px;">' + t('abo') + '</th>';
  html += '<th style="text-align:right;padding:6px 8px;">' + t('kr_mnd_2') + '</th>';
  html += '<th style="text-align:center;padding:6px 8px;">' + t('fornyelse_2') + '</th>';
  html += '</tr></thead><tbody>';

  d.accounts.forEach(function(a) {
    var customerCol = '';
    if (a.customer_name) {
      customerCol = '<span style="color:var(--green);">' + esc(a.customer_name) + '</span>';
    } else {
      customerCol = '<button class="btn btn-ghost" data-write data-click-handler="uniwebShowMatch" data-id="' + esc(a.id) + '" style="padding:2px 8px;font-size:10px;color:var(--orange);">' + t('ikke_koblet') + '</button>';
    }

    html += '<tr style="border-bottom:1px solid var(--border);">';
    html += '<td style="padding:6px 8px;"><a href="#" data-click-handler="uniwebShowDetail" data-id="' + esc(a.id) + '" style="color:var(--blue);text-decoration:none;">' + esc(a.name) + '</a></td>';
    html += '<td style="padding:6px 8px;">' + customerCol + '</td>';
    html += '<td style="text-align:center;padding:6px 8px;">' + Number(a.domain_count) + '</td>';
    html += '<td style="text-align:center;padding:6px 8px;">' + Number(a.subscription_count) + '</td>';
    html += '<td style="text-align:right;padding:6px 8px;font-family:var(--mono);">' + (a.monthly_total > 0 ? a.monthly_total.toFixed(0) : '-') + '</td>';
    html += '<td style="text-align:center;padding:6px 8px;">' + esc(a.earliest_renewal || '-') + '</td>';
    html += '</tr>';
  });

  html += '</tbody></table></div>';

  // Add "Importer kunder" button if there are unmatched accounts
  if (unmatchedCount > 0) {
    html += '<div style="margin-top:10px;">';
    html += '<button class="btn btn-primary" data-write data-click-handler="uniwebShowImport" style="padding:6px 14px;font-size:12px;">' + t('integ_import_from_uniweb','Importer kunder fra Uniweb') + ' (' + unmatchedCount + ')</button>';
    html += '</div>';
  }

  container.innerHTML = html;
}

async function uniwebShowMatch(accountId) {
  var d = await apiFetch('/api/uniweb/matches');
  if (!d) return;

  var customers = d.available_customers || [];
  var html = '<div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;" id="uniweb-match-modal" data-click-handler="removeOnBackdrop">';
  html += '<div class="card" style="width:400px;max-height:500px;padding:20px;" data-click-handler="stopPropagation">';
  html += '<div style="font-weight:600;font-size:14px;margin-bottom:12px;">' + t('koble_uniweb_konto_til_msp') + '</div>';
  html += '<select id="uniweb-match-select" class="field-input" style="margin-bottom:12px;">';
  html += '<option value="">' + t('velg_kunde') + '</option>';
  customers.forEach(function(c) {
    html += '<option value="' + esc(c.id) + '">' + esc(c.name) + '</option>';
  });
  html += '</select>';
  html += '<div style="display:flex;gap:8px;">';
  html += '<button class="btn btn-primary" data-write data-click-handler="uniwebDoMatch" data-id="' + esc(accountId) + '">' + t('koble') + '</button>';
  html += '<button class="btn btn-ghost" data-click-handler="removeElement" data-target="uniweb-match-modal">' + t('avbryt_2') + '</button>';
  html += '</div></div></div>';
  document.body.insertAdjacentHTML('beforeend', html);
}

async function uniwebDoMatch(accountId) {
  var select = document.getElementById('uniweb-match-select');
  var customerId = select ? select.value : '';
  if (!customerId) { showToast(t('velg_en_kunde'), 'warning'); return; }

  var d = await apiFetch('/api/uniweb/match', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({uniweb_account_id: accountId, customer_id: customerId}),
  });
  if (d && d.ok) {
    showToast(t('konto_koblet'), 'success');
    var modal = document.getElementById('uniweb-match-modal');
    if (modal) modal.remove();
    uniwebLoadAccounts();
  } else {
    showToast(d && d.error ? d.error : t('integ_error','Feil'), 'error');
  }
}

async function uniwebShowDetail(accountId) {
  var d = await apiFetch('/api/uniweb/account/' + encodeURIComponent(accountId));
  if (!d) return;

  var html = '<div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;" id="uniweb-detail-modal" data-click-handler="removeOnBackdrop">';
  html += '<div class="card" style="width:700px;max-height:80vh;padding:20px;overflow-y:auto;" data-click-handler="stopPropagation">';
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">';
  html += '<div style="font-weight:600;font-size:16px;">' + esc(d.name) + '</div>';
  html += '<button class="btn btn-ghost" data-click-handler="removeElement" data-target="uniweb-detail-modal" style="padding:4px 8px;">X</button>';
  html += '</div>';

  if (d.customer_name) {
    html += '<div style="margin-bottom:12px;font-size:12px;color:var(--green);">' + t('integ_linked_to','Koblet til') + ': ' + esc(d.customer_name) + '</div>';
  }

  // Domains
  if (d.domains && d.domains.length > 0) {
    html += '<div style="font-weight:600;font-size:13px;margin:12px 0 6px;">' + t('domener') + ' (' + d.domains.length + ')</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:12px;">';
    html += '<thead><tr style="background:var(--bg-tertiary);"><th style="text-align:left;padding:4px 6px;">' + t('domene_3') + '</th><th style="text-align:center;padding:4px 6px;">' + t('utloper') + '</th><th style="text-align:center;padding:4px 6px;">' + t('status_2') + '</th></tr></thead><tbody>';
    d.domains.forEach(function(dom) {
      html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px 6px;">' + esc(dom.domain) + '</td><td style="text-align:center;padding:4px 6px;">' + esc(dom.expiry || '-') + '</td><td style="text-align:center;padding:4px 6px;">' + esc(dom.status || '-') + '</td></tr>';
    });
    html += '</tbody></table>';
  }

  // Subscriptions
  if (d.subscriptions && d.subscriptions.length > 0) {
    html += '<div style="font-weight:600;font-size:13px;margin:12px 0 6px;">' + t('abonnementer') + ' (' + d.subscriptions.length + ')</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:12px;">';
    html += '<thead><tr style="background:var(--bg-tertiary);"><th style="text-align:left;padding:4px 6px;">' + t('tjeneste_2') + '</th><th style="text-align:left;padding:4px 6px;">' + t('bruker_domene_2') + '</th><th style="text-align:right;padding:4px 6px;">' + t('pris_mnd_2') + '</th><th style="text-align:center;padding:4px 6px;">' + t('fornyelse_2') + '</th></tr></thead><tbody>';
    d.subscriptions.forEach(function(sub) {
      html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px 6px;">' + esc(sub.service_type || sub.Service || '-') + '</td><td style="padding:4px 6px;">' + esc(sub.username_domain || sub.Username || '-') + '</td><td style="text-align:right;padding:4px 6px;font-family:var(--mono);">' + esc(sub.price_monthly || sub['Price per month'] || '-') + '</td><td style="text-align:center;padding:4px 6px;">' + esc(sub.renewal_date || sub['Renewed until'] || '-') + '</td></tr>';
    });
    html += '</tbody></table>';
  }

  // SSL
  if (d.ssl && d.ssl.length > 0) {
    html += '<div style="font-weight:600;font-size:13px;margin:12px 0 6px;">' + t('uniweb_ssl_certificates') + ' (' + d.ssl.length + ')</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:12px;">';
    html += '<thead><tr style="background:var(--bg-tertiary);"><th style="text-align:left;padding:4px 6px;">' + t('domene_3') + '</th><th style="text-align:left;padding:4px 6px;">' + t('type_2') + '</th><th style="text-align:center;padding:4px 6px;">' + t('utloper') + '</th></tr></thead><tbody>';
    d.ssl.forEach(function(cert) {
      html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px 6px;">' + esc(cert.domain) + '</td><td style="padding:4px 6px;">' + esc(cert.type || '-') + '</td><td style="text-align:center;padding:4px 6px;">' + esc(cert.expiry || '-') + '</td></tr>';
    });
    html += '</tbody></table>';
  }

  // Email
  if (d.email && d.email.length > 0) {
    html += '<div style="font-weight:600;font-size:13px;margin:12px 0 6px;">' + t('uniweb_email_accounts') + ' (' + d.email.length + ')</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:12px;">';
    html += '<thead><tr style="background:var(--bg-tertiary);"><th style="text-align:left;padding:4px 6px;">' + t('adresse_2') + '</th><th style="text-align:center;padding:4px 6px;">' + t('kvote_2') + '</th><th style="text-align:center;padding:4px 6px;">' + t('brukt') + '</th></tr></thead><tbody>';
    d.email.forEach(function(em) {
      html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px 6px;">' + esc(em.address || em[''] || '-') + '</td><td style="text-align:center;padding:4px 6px;">' + esc(em.quota || '-') + '</td><td style="text-align:center;padding:4px 6px;">' + esc(em.used || '-') + '</td></tr>';
    });
    html += '</tbody></table>';
  }

  // Hosting
  if (d.hosting && d.hosting.length > 0) {
    html += '<div style="font-weight:600;font-size:13px;margin:12px 0 6px;">Webhosting (' + d.hosting.length + ')</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:12px;">';
    html += '<thead><tr style="background:var(--bg-tertiary);"><th style="text-align:left;padding:4px 6px;">' + t('domene_3') + '</th><th style="text-align:left;padding:4px 6px;">' + t('pakke') + '</th><th style="text-align:center;padding:4px 6px;">' + t('status_2') + '</th></tr></thead><tbody>';
    d.hosting.forEach(function(h) {
      html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px 6px;">' + esc(h.domain || '-') + '</td><td style="padding:4px 6px;">' + esc(h.plan || '-') + '</td><td style="text-align:center;padding:4px 6px;">' + esc(h.status || '-') + '</td></tr>';
    });
    html += '</tbody></table>';
  }

  html += '<div style="font-size:10px;color:var(--text-dim);margin-top:12px;">Sist synkronisert: ' + (d.last_sync ? new Date(d.last_sync).toLocaleString('nb-NO') : '-') + '</div>';
  html += '</div></div>';

  document.body.insertAdjacentHTML('beforeend', html);
}

// ── Uniweb Import ────────────────────────────────────────────────────────────

async function uniwebShowImport() {
  var d = await apiFetch('/api/uniweb/matches');
  if (!d) return;

  var unmatched = d.unmatched || [];
  if (unmatched.length === 0) {
    showToast(t('alle_kontoer_er_allerede_koblet'), 'success');
    return;
  }

  // Check if any accounts have parent info (sub-customers)
  var hasParents = unmatched.some(function(u) { return !!u.parent_name; });

  var html = '<div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;padding:16px;" id="uniweb-import-modal" data-click-handler="uniwebCloseImportOnBackdrop">';
  html += '<div class="card" style="width:650px;max-width:100%;max-height:80vh;padding:20px;display:flex;flex-direction:column;" data-click-handler="stopPropagation">';

  // Header with title and selection counter
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">';
  html += '<div style="font-weight:600;font-size:16px;">' + t('importer_kunder_fra_uniweb') + '</div>';
  html += '<button class="btn btn-ghost" data-click-handler="uniwebCloseImport" style="padding:4px 8px;font-size:14px;">X</button>';
  html += '</div>';
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">';
  html += '<div style="font-size:12px;color:var(--text-muted);">' + unmatched.length + ' ' + t('integ_unmatched_hint','Uniweb-kontoer som ikke er koblet til en MSP-kunde. Valgte kontoer opprettes som nye kunder.') + '</div>';
  html += '</div>';
  html += '<div id="uniweb-import-counter" style="font-size:12px;font-weight:500;color:var(--text-muted);margin-bottom:10px;">0 ' + t('integ_of','av') + ' ' + unmatched.length + ' ' + t('integ_selected','valgt') + '</div>';

  // Search + select all
  html += '<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">';
  html += '<input type="text" id="uniweb-import-search" class="field-input" placeholder="' + t('integ_search','Søk ...') + '" style="flex:1;min-width:150px;padding:6px 12px;font-size:12px;" data-input-handler="uniwebFilterImport">';
  html += '<label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer;white-space:nowrap;"><input type="checkbox" id="uniweb-import-select-all" data-change-handler="uniwebToggleAllImport"> ' + t('velg_alle') + '</label>';
  html += '</div>';

  // Table
  html += '<div style="flex:1;overflow-y:auto;border:1px solid var(--border);border-radius:6px;max-height:400px;min-height:0;">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:11px;"><thead><tr style="background:var(--bg-tertiary);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:1;">';
  html += '<th style="width:32px;padding:6px;background:var(--bg-tertiary);"></th>';
  html += '<th style="text-align:left;padding:6px 8px;background:var(--bg-tertiary);">' + t('kontonavn') + '</th>';
  if (hasParents) {
    html += '<th style="text-align:left;padding:6px 8px;background:var(--bg-tertiary);">' + t('overordnet_konto') + '</th>';
  }
  html += '<th style="text-align:left;padding:6px 8px;font-family:var(--mono);background:var(--bg-tertiary);">' + t('uniweb_id') + '</th>';
  html += '</tr></thead><tbody>';

  unmatched.sort(function(a, b) { return a.uniweb_name.localeCompare(b.uniweb_name); });

  for (var i = 0; i < unmatched.length; i++) {
    var u = unmatched[i];
    html += '<tr class="uniweb-import-row" data-name="' + esc(u.uniweb_name.toLowerCase()) + '" style="border-bottom:1px solid var(--border);">';
    html += '<td style="text-align:center;padding:6px;"><input type="checkbox" class="uniweb-import-cb" data-id="' + esc(u.uniweb_id) + '" data-account-name="' + esc(u.uniweb_name) + '" data-change-handler="uniwebUpdateImportBtn" style="width:15px;height:15px;cursor:pointer;"></td>';
    html += '<td style="padding:6px 8px;font-weight:500;">' + esc(u.uniweb_name) + '</td>';
    if (hasParents) {
      html += '<td style="padding:6px 8px;color:var(--text-muted);font-size:10px;">' + (u.parent_name ? esc(u.parent_name) : '-') + '</td>';
    }
    html += '<td style="padding:6px 8px;font-family:var(--mono);color:var(--text-muted);">' + esc(u.uniweb_id) + '</td>';
    html += '</tr>';
  }

  html += '</tbody></table></div>';

  // Error display area (hidden initially)
  html += '<div id="uniweb-import-errors" style="display:none;margin-top:10px;max-height:120px;overflow-y:auto;border:1px solid var(--red);border-radius:6px;padding:10px;background:rgba(255,0,0,0.05);font-size:11px;"></div>';

  // Buttons
  html += '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px;flex-wrap:wrap;">';
  html += '<button class="btn btn-ghost" data-click-handler="uniwebCloseImport">' + t('avbryt_2') + '</button>';
  html += '<button class="btn btn-primary" id="uniweb-import-btn" disabled data-write data-click-handler="uniwebDoImport">' + t('importer_valgte') + '</button>';
  html += '</div>';

  html += '</div></div>';
  document.body.insertAdjacentHTML('beforeend', html);

  // Store total count for counter updates
  window._uniwebImportTotal = unmatched.length;

  // Keyboard support — Escape to close
  window._uniwebImportKeyHandler = function(e) {
    if (e.key === 'Escape') {
      uniwebCloseImport();
    }
  };
  document.addEventListener('keydown', window._uniwebImportKeyHandler);
}

function uniwebCloseImport() {
  var modal = document.getElementById('uniweb-import-modal');
  if (modal) modal.remove();
  if (window._uniwebImportKeyHandler) {
    document.removeEventListener('keydown', window._uniwebImportKeyHandler);
    window._uniwebImportKeyHandler = null;
  }
}

function uniwebFilterImport() {
  var q = (document.getElementById('uniweb-import-search') || {}).value || '';
  q = q.toLowerCase();
  document.querySelectorAll('.uniweb-import-row').forEach(function(row) {
    row.style.display = row.dataset.name.indexOf(q) >= 0 ? '' : 'none';
  });
  uniwebUpdateImportBtn();
}

function uniwebToggleAllImport(checked) {
  document.querySelectorAll('.uniweb-import-cb').forEach(function(cb) {
    // Only toggle visible rows
    if (cb.closest('.uniweb-import-row').style.display !== 'none') {
      cb.checked = checked;
    }
  });
  uniwebUpdateImportBtn();
}

function uniwebUpdateImportBtn() {
  var checked = document.querySelectorAll('.uniweb-import-cb:checked').length;
  var total = window._uniwebImportTotal || 0;
  var btn = document.getElementById('uniweb-import-btn');
  if (btn) {
    btn.disabled = checked === 0;
    btn.textContent = checked > 0 ? t('importer_valgte','Importer valgte') + ' (' + checked + ')' : t('importer_valgte','Importer valgte');
  }
  // Update selection counter
  var counter = document.getElementById('uniweb-import-counter');
  if (counter) {
    counter.textContent = checked + ' ' + t('integ_of','av') + ' ' + total + ' ' + t('integ_selected','valgt');
    counter.style.color = checked > 0 ? 'var(--blue)' : 'var(--text-muted)';
  }
}

async function uniwebDoImport() {
  var ids = [];
  var names = [];
  document.querySelectorAll('.uniweb-import-cb:checked').forEach(function(cb) {
    ids.push(cb.dataset.id);
    names.push(cb.dataset.accountName || cb.dataset.id);
  });
  if (ids.length === 0) return;

  // Confirmation step
  var confirmMsg = t('integ_confirm_import','Er du sikker på at du vil importere') + ' ' + ids.length + ' ' + (ids.length > 1 ? t('integ_customers_lc','kunder') : t('integ_customer_lc','kunde')) + '?';
  if (!confirm(confirmMsg)) return;

  var btn = document.getElementById('uniweb-import-btn');
  if (btn) { btn.disabled = true; btn.textContent = t('msg_importing','Importing …'); }

  // Hide any previous errors
  var errBox = document.getElementById('uniweb-import-errors');
  if (errBox) errBox.style.display = 'none';

  try {
    var d = await apiFetch('/api/uniweb/import-customers', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({account_ids: ids}),
    });
    if (!d) return;
    if (d.error) {
      showToast(t('feil_3') + ' ' + d.error, 'error');
      return;
    }

    // Show per-account errors if any
    if (d.errors && d.errors.length > 0) {
      if (errBox) {
        var errHtml = '<div style="font-weight:600;margin-bottom:6px;color:var(--red);">' + d.errors.length + ' ' + t('integ_accounts_failed','konto(er) kunne ikke importeres') + ':</div>';
        d.errors.forEach(function(err) {
          if (typeof err === 'object') {
            errHtml += '<div style="padding:2px 0;">&bull; <strong>' + esc(err.name) + '</strong>: ' + esc(err.reason) + '</div>';
          } else {
            errHtml += '<div style="padding:2px 0;">&bull; ' + esc(err) + '</div>';
          }
        });
        errBox.innerHTML = errHtml;
        errBox.style.display = 'block';
      }
    }

    if (d.imported > 0) {
      showToast(t('importerte') + ' ' + d.imported + ' ' + t('integ_customers_from_uniweb','kunde(r) fra Uniweb'), 'success', 5000);

      // Refresh the main customer list if available
      if (typeof loadCustomers === 'function') {
        try { loadCustomers(); } catch(e) { /* ignore */ }
      }
    }

    if (!d.errors || d.errors.length === 0) {
      // All succeeded — close modal
      uniwebCloseImport();
    } else if (d.imported > 0) {
      // Partial success — keep modal open to show errors, but refresh accounts table
      showToast(d.errors.length + ' ' + t('integ_accounts_failed_detail','konto(er) feilet, se detaljer i dialogen'), 'warning', 5000);
    } else {
      // All failed
      showToast(t('ingen_kontoer_ble_importert'), 'error');
    }

    uniwebLoadAccounts();
  } catch (e) {
    showToast(t('feil_3') + ' ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = t('btn_import_selected','Import selected'); }
  }
}

// ── Task Scheduler (Planlagte oppgaver) ─────────────────────────────────────

async function taskSchedRefresh() {
  var container = document.getElementById('task-scheduler-table');
  if (!container) return;
  try {
    var d = await apiFetch('/api/scheduler/tasks');
    if (!d || !d.tasks) { container.innerHTML = '<div style="padding:16px;color:var(--red);">' + t('status_error','Error') + '</div>'; return; }
    taskSchedRender(d.tasks);
  } catch(e) {
    container.innerHTML = '<div style="padding:16px;color:var(--red);">' + esc(e.message) + '</div>';
  }
}

// The API sends the schedule as fields and as an English summary ("daily
// 02:00", "every 6h", "sunday 03:00"). The summary was printed as it came, in
// English in a Norwegian table; the label is built from the fields instead.
function _taskSchedLabel(task) {
  var time = task.time || '';
  if (task.type === 'interval') {
    var hours = Number(task.interval_hours) || 0;
    return hours === 1 ? t('sched_every_hour') : t('sched_every_n_hours').replace('{n}', String(hours));
  }
  if (task.type === 'weekly') {
    var days = {
      monday: t('day_monday'), tuesday: t('day_tuesday'), wednesday: t('day_wednesday'),
      thursday: t('day_thursday'), friday: t('day_friday'), saturday: t('day_saturday'),
      sunday: t('day_sunday')
    };
    var day = String(task.day || '').toLowerCase();
    return t('sched_weekly').replace('{day}', days[day] || day).replace('{time}', time);
  }
  if (task.type === 'daily') return t('sched_daily').replace('{time}', time);
  return task.schedule || '';
}

function taskSchedRender(tasks) {
  var container = document.getElementById('task-scheduler-table');
  if (!container) return;
  var lang = (typeof _lang !== 'undefined' ? _lang : 'no');

  var html = '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="background:var(--bg-tertiary);border-bottom:1px solid var(--border);">';
  html += '<th style="text-align:left;padding:10px 12px;">' + t('col_task','Oppgave') + '</th>';
  html += '<th style="text-align:left;padding:10px 12px;">' + t('col_schedule','Tidsplan') + '</th>';
  html += '<th style="text-align:center;padding:10px 12px;">' + t('col_last_run','Siste kjoring') + '</th>';
  html += '<th style="text-align:center;padding:10px 12px;">' + t('col_next_run','Neste kjoring') + '</th>';
  html += '<th style="text-align:center;padding:10px 12px;">' + t('col_status','Status') + '</th>';
  html += '<th style="text-align:center;padding:10px 12px;">' + t('col_enabled','Aktiv') + '</th>';
  html += '<th style="text-align:center;padding:10px 12px;"></th>';
  html += '</tr></thead><tbody>';

  tasks.forEach(function(task) {
    var label = lang === 'en' ? task.label_en : task.label_no;

    // Format last run
    var lastRun = task.last_run ? new Date(task.last_run).toLocaleString('nb-NO') : '-';

    // Format next run
    var nextRun = task.next_run ? new Date(task.next_run).toLocaleString('nb-NO') : '-';

    // Status indicator
    var statusHtml;
    if (task.last_error) {
      statusHtml = '<span style="color:var(--red);font-size:11px;" title="' + esc(task.last_error) + '">' + t('feil') + '</span>';
    } else if (task.last_result) {
      statusHtml = '<span style="color:var(--green);font-size:11px;" title="' + esc(task.last_result) + '">OK</span>';
    } else {
      statusHtml = '<span style="color:var(--text-dim);font-size:11px;">-</span>';
    }

    // Schedule display
    var schedHtml = esc(_taskSchedLabel(task));

    // Toggle
    var toggleChecked = task.enabled ? 'checked' : '';

    html += '<tr style="border-bottom:1px solid var(--border);">';
    html += '<td style="padding:10px 12px;font-weight:500;">' + esc(label) + '</td>';
    html += '<td style="padding:10px 12px;font-family:var(--mono);font-size:11px;color:var(--text-muted);">' + schedHtml + '</td>';
    html += '<td style="text-align:center;padding:10px 12px;font-size:11px;">' + lastRun + '</td>';
    html += '<td style="text-align:center;padding:10px 12px;font-size:11px;">' + nextRun + '</td>';
    html += '<td style="text-align:center;padding:10px 12px;">' + statusHtml + '</td>';
    html += '<td style="text-align:center;padding:10px 12px;">';
    html += '<label style="position:relative;display:inline-block;width:36px;height:20px;cursor:pointer;">';
    html += '<input type="checkbox" ' + toggleChecked + ' data-change-handler="taskSchedToggle" data-id="' + esc(task.id) + '" style="opacity:0;width:0;height:0;">';
    html += '<span style="position:absolute;top:0;left:0;right:0;bottom:0;background:' + (task.enabled ? 'var(--green)' : 'var(--border)') + ';border-radius:10px;transition:background .2s;"></span>';
    html += '<span style="position:absolute;top:2px;left:' + (task.enabled ? '18px' : '2px') + ';width:16px;height:16px;background:#fff;border-radius:50%;transition:left .2s;"></span>';
    html += '</label>';
    html += '</td>';
    html += '<td style="text-align:center;padding:10px 12px;">';
    html += '<button class="btn btn-ghost" data-write data-click-handler="taskSchedRunNow" data-id="' + esc(task.id) + '" style="padding:4px 10px;font-size:11px;white-space:nowrap;">' + t('btn_run_now','Kjor na') + '</button>';
    html += '</td>';
    html += '</tr>';
  });

  html += '</tbody></table>';
  container.innerHTML = html;
}

async function taskSchedToggle(taskId, enabled) {
  var body = {};
  body[taskId] = {enabled: enabled};
  try {
    await apiFetch('/api/scheduler/tasks/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    showToast(enabled ? t('msg_task_enabled','Oppgave aktivert') : t('msg_task_disabled','Oppgave deaktivert'), 'success', 2000);
    setTimeout(taskSchedRefresh, 500);
  } catch(e) {
    showToast(e.message, 'error');
    taskSchedRefresh();
  }
}

async function taskSchedRunNow(taskId, btn) {
  if (btn) { btn.disabled = true; btn.textContent = '...'; }
  try {
    var d = await apiFetch('/api/scheduler/tasks/' + encodeURIComponent(taskId) + '/run', {method: 'POST'});
    if (d && d.ok) {
      showToast(t('msg_task_completed','Oppgave fullfort') + (d.result ? ': ' + d.result : ''), 'success', 4000);
    } else {
      showToast(t('msg_task_failed','Oppgave feilet') + (d && d.error ? ': ' + d.error : ''), 'error');
    }
  } catch(e) {
    showToast(e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = t('btn_run_now','Kjor na'); }
    taskSchedRefresh();
  }
}

// ── Automatic Alerts ────────────────────────────────────────────────────────

var _alertSaveTimeout = null;

async function alertLoadConfig() {
  var d = await apiFetch('/api/alerts/config');
  if (!d) return;

  var toggle = document.getElementById('alert-master-toggle');
  var dot = document.getElementById('alert-status-dot');
  if (toggle) toggle.checked = !!d.enabled;
  if (dot) dot.style.background = d.enabled ? 'var(--green)' : 'var(--text-dim)';

  var teamsCheck = document.getElementById('alert-notify-teams');
  var emailCheck = document.getElementById('alert-notify-email');
  var emailInput = document.getElementById('alert-email-recipient');
  if (teamsCheck) teamsCheck.checked = !!d.notify_teams;
  if (emailCheck) emailCheck.checked = !!d.notify_email;
  if (emailInput) emailInput.value = d.email_recipient || '';

  var rules = d.rules || {};
  var ruleMap = {
    'rule-ssl-expiry': ['ssl_expiry', 'rule-ssl-days', 'days'],
    'rule-domain-expiry': ['domain_expiry', 'rule-domain-days', 'days'],
    'rule-fortigate-threats': ['fortigate_threats', 'rule-fg-threshold', 'threshold'],
    'rule-firmware-outdated': ['firmware_outdated', null, null],
    'rule-also-license': ['also_license_expiry', 'rule-also-days', 'days'],
    'rule-mfa-coverage': ['mfa_coverage', 'rule-mfa-threshold', 'threshold'],
    'rule-pentest-critical': ['pentest_critical', null, null],
  };

  Object.keys(ruleMap).forEach(function(checkId) {
    var cfg = ruleMap[checkId];
    var ruleKey = cfg[0], valId = cfg[1], valField = cfg[2];
    var rule = rules[ruleKey] || {};
    var el = document.getElementById(checkId);
    if (el) el.checked = !!rule.enabled;
    if (valId && valField && rule[valField] !== undefined) {
      var valEl = document.getElementById(valId);
      if (valEl) valEl.value = rule[valField];
    }
  });

  alertLoadHistory();
}

function alertToggleMaster(enabled) {
  var dot = document.getElementById('alert-status-dot');
  if (dot) dot.style.background = enabled ? 'var(--green)' : 'var(--text-dim)';
  alertSaveConfig();
}

function alertSaveConfig() {
  if (_alertSaveTimeout) clearTimeout(_alertSaveTimeout);
  _alertSaveTimeout = setTimeout(function() { _alertDoSave(); }, 400);
}

async function _alertDoSave() {
  var body = {
    enabled: !!document.getElementById('alert-master-toggle').checked,
    notify_teams: !!document.getElementById('alert-notify-teams').checked,
    notify_email: !!document.getElementById('alert-notify-email').checked,
    email_recipient: (document.getElementById('alert-email-recipient').value || '').trim(),
    rules: {
      ssl_expiry: {
        enabled: !!document.getElementById('rule-ssl-expiry').checked,
        days: parseInt(document.getElementById('rule-ssl-days').value) || 14,
      },
      domain_expiry: {
        enabled: !!document.getElementById('rule-domain-expiry').checked,
        days: parseInt(document.getElementById('rule-domain-days').value) || 14,
      },
      fortigate_threats: {
        enabled: !!document.getElementById('rule-fortigate-threats').checked,
        threshold: parseInt(document.getElementById('rule-fg-threshold').value) || 50,
      },
      firmware_outdated: {
        enabled: !!document.getElementById('rule-firmware-outdated').checked,
      },
      also_license_expiry: {
        enabled: !!document.getElementById('rule-also-license').checked,
        days: parseInt(document.getElementById('rule-also-days').value) || 14,
      },
      mfa_coverage: {
        enabled: !!document.getElementById('rule-mfa-coverage').checked,
        threshold: parseInt(document.getElementById('rule-mfa-threshold').value) || 80,
      },
      // The dashboard's rule list switched this one too; it lives here now.
      pentest_critical: {
        enabled: !!document.getElementById('rule-pentest-critical').checked,
      },
    },
  };

  var result = await apiFetch('/api/alerts/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  // Confirm save visibly. apiFetch returns null on error (and already shows
  // its own error toast), so only cheer on explicit success.
  if (result) {
    showToast(t('msg_saved', '✓ Lagret'), 'success', 1500);
  }
}

async function alertRunCheckNow() {
  var resultEl = document.getElementById('alert-check-result');
  if (resultEl) resultEl.innerHTML = '<span style="color:var(--text-muted);">' + t('msg_checking','Sjekker...') + '</span>';

  try {
    var d = await apiFetch('/api/alerts/check-now', {method: 'POST'});
    if (!d) { if (resultEl) resultEl.innerHTML = '<span style="color:var(--red);">' + t('status_error','Feil') + '</span>'; return; }

    var html = '<div style="padding:10px;background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-md);">';
    html += '<div style="font-weight:600;margin-bottom:6px;">' + t('lbl_check_result','Sjekkresultat') + '</div>';
    html += '<div style="display:flex;gap:16px;font-size:12px;">';
    html += '<span>' + t('lbl_found','Funnet') + ': <strong>' + Number(d.total_found) + '</strong></span>';
    html += '<span>' + t('lbl_new_alerts','Nye') + ': <strong style="color:' + (d.new_alerts > 0 ? 'var(--red)' : 'var(--green)') + ';">' + Number(d.new_alerts) + '</strong></span>';
    html += '<span>' + t('lbl_deduplicated','Deduplisert') + ': ' + Number(d.deduplicated) + '</span>';
    html += '<span>' + t('lbl_channels_notified','Kanaler varslet') + ': ' + Number(d.channels_notified) + '</span>';
    html += '</div>';

    if (d.alerts && d.alerts.length > 0) {
      html += '<div style="margin-top:8px;max-height:200px;overflow-y:auto;">';
      html += '<table style="width:100%;border-collapse:collapse;font-size:11px;">';
      d.alerts.forEach(function(a) {
        var color = a.severity === 'critical' ? 'var(--red)' : 'var(--orange)';
        var sevLabel = a.severity === 'critical' ? t('lbl_critical','Kritisk') : t('lbl_warning_sev','Advarsel');
        html += '<tr style="border-bottom:1px solid var(--border);">';
        html += '<td style="padding:4px 6px;color:' + color + ';font-weight:600;">' + sevLabel + '</td>';
        html += '<td style="padding:4px 6px;">' + esc(a.customer) + '</td>';
        html += '<td style="padding:4px 6px;">' + esc(a.item) + '</td>';
        html += '<td style="padding:4px 6px;color:var(--text-muted);">' + esc(a.detail) + '</td>';
        html += '</tr>';
      });
      html += '</table></div>';
    } else {
      html += '<div style="margin-top:6px;color:var(--green);">&#10003; ' + t('msg_no_alerts','Ingen varsler funnet') + '</div>';
    }

    html += '</div>';
    if (resultEl) resultEl.innerHTML = html;

    alertLoadHistory();
  } catch(e) {
    if (resultEl) resultEl.innerHTML = '<span style="color:var(--red);">' + esc(e.message) + '</span>';
  }
}

async function alertLoadHistory() {
  var container = document.getElementById('alert-history-container');
  if (!container) return;

  var d = await apiFetch('/api/alerts/history?limit=50');
  if (!d || !d.entries || d.entries.length === 0) {
    container.innerHTML = '<div style="font-size:12px;color:var(--text-muted);padding:8px;">' + t('msg_no_alert_history','Ingen varselhistorikk enna') + '</div>';
    return;
  }

  var html = '<table style="width:100%;border-collapse:collapse;font-size:11px;">';
  html += '<thead><tr style="background:var(--bg-tertiary);border-bottom:1px solid var(--border);">';
  html += '<th style="text-align:left;padding:6px;">' + t('col_time','Tidspunkt') + '</th>';
  html += '<th style="text-align:left;padding:6px;">' + t('col_severity','Alvorlighet') + '</th>';
  html += '<th style="text-align:left;padding:6px;">' + t('col_customer','Kunde') + '</th>';
  html += '<th style="text-align:left;padding:6px;">' + t('col_item','Element') + '</th>';
  html += '<th style="text-align:left;padding:6px;">' + t('col_detail_lbl','Detaljer') + '</th>';
  html += '</tr></thead><tbody>';

  d.entries.forEach(function(h) {
    var color = h.severity === 'critical' ? 'var(--red)' : 'var(--orange)';
    var sevLabel = h.severity === 'critical' ? t('lbl_critical','Kritisk') : t('lbl_warning_sev','Advarsel');
    var timeStr = h.sent_at ? new Date(h.sent_at).toLocaleString('nb-NO') : '';
    html += '<tr style="border-bottom:1px solid var(--border);">';
    html += '<td style="padding:4px 6px;font-family:var(--mono);font-size:10px;">' + esc(timeStr) + '</td>';
    html += '<td style="padding:4px 6px;color:' + color + ';font-weight:600;">' + sevLabel + '</td>';
    html += '<td style="padding:4px 6px;">' + esc(h.customer || '') + '</td>';
    html += '<td style="padding:4px 6px;">' + esc(h.item || '') + '</td>';
    html += '<td style="padding:4px 6px;color:var(--text-muted);">' + esc(h.detail || '') + '</td>';
    html += '</tr>';
  });
  html += '</tbody></table>';
  container.innerHTML = html;
}

// Load Uniweb status on integrations view
async function uniwebCheckStatus() {
  var d = await apiFetch('/api/uniweb/status');
  if (!d) return;
  if (d.configured) {
    _integPaint('uniweb', 'ok');
    // Load settings into fields
    var settings = await apiFetch('/api/settings');
    if (settings) {
      var emailField = document.getElementById('input-uniweb-email');
      var passField = document.getElementById('input-uniweb-password');
      if (emailField && settings.uniweb_email) emailField.value = settings.uniweb_email;
      if (passField && settings.uniweb_password_set) passField.value = '••••••';
    }
    if (d.last_sync) {
      document.getElementById('uniweb-last-sync').textContent = t('lbl_last_synced','Last synced') + ': ' + new Date(d.last_sync).toLocaleString(_lang === 'en' ? 'en-GB' : 'nb-NO');
    }
    uniwebLoadAccounts();
  }
}

// ── IT Glue Documentation Sync ─────────────────────────────────────────────

async function itglueSyncAllDocumentation() {
  var btn = document.getElementById('itglue-sync-doc-btn');
  var status = document.getElementById('itglue-sync-status');
  if (!btn || !status) return;

  btn.disabled = true;
  btn.textContent = t('msg_itglue_syncing', 'Synkroniserer dokumentasjon...');
  status.style.display = 'block';
  status.innerHTML = '<span style="color:var(--text-muted);">' + t('msg_itglue_syncing', 'Synkroniserer dokumentasjon...') + '</span>';

  try {
    var d = await apiFetch('/api/itglue/sync-all', {method: 'POST'});
    if (!d) {
      status.innerHTML = '<span style="color:var(--red);">' + t('status_error', 'Error') + '</span>';
      return;
    }
    if (d.error) {
      status.innerHTML = '<span style="color:var(--red);">' + esc(d.error) + '</span>';
      return;
    }

    var resultMsg = t('msg_itglue_sync_result', '{synced} kunder synkronisert, {errors} feil')
      .replace('{synced}', d.synced || 0)
      .replace('{errors}', d.errors || 0);

    var html = '<div style="padding:8px 0;">';
    html += '<span style="color:var(--green);font-weight:600;">&#10003; ' + t('msg_itglue_sync_done', 'Synkronisering fullfort') + '</span>';
    html += '<div style="margin-top:4px;color:var(--text-muted);">' + esc(resultMsg) + '</div>';

    // Show per-customer details
    if (d.results && d.results.length > 0) {
      html += '<details style="margin-top:8px;font-size:11px;"><summary style="cursor:pointer;color:var(--text-muted);">' + t('lbl_details', 'Detaljer') + ' (' + d.results.length + ')</summary>';
      html += '<div style="max-height:200px;overflow-y:auto;margin-top:4px;">';
      d.results.forEach(function(r) {
        var icon = r.synced && r.synced.length > 0 ? '&#10003;' : '&#10007;';
        var color = r.synced && r.synced.length > 0 ? 'var(--green)' : 'var(--red)';
        var types = (r.synced || []).map(function(s) { return s.type; }).join(', ');
        var errCount = (r.errors || []).length;
        html += '<div style="padding:3px 0;display:flex;gap:6px;">';
        html += '<span style="color:' + color + ';">' + icon + '</span>';
        html += '<span style="flex:1;">' + esc(r.customer_name || r.customer_id) + '</span>';
        if (types) html += '<span style="color:var(--text-dim);">' + esc(types) + '</span>';
        if (errCount > 0) html += '<span style="color:var(--orange);">' + errCount + ' ' + t('status_error', 'feil') + '</span>';
        html += '</div>';
      });
      html += '</div></details>';
    }
    html += '</div>';
    status.innerHTML = html;
    showToast(resultMsg, d.errors > 0 ? 'warning' : 'success', 4000);
  } catch (e) {
    status.innerHTML = '<span style="color:var(--red);">' + esc(e.message) + '</span>';
    showToast(e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = t('btn_sync_documentation', 'Synkroniser dokumentasjon');
  }
}

// ═══════════════════════════════════════════════════════════════════
// INTEGRATIONS + GDAP — carved out of app.js
// ═══════════════════════════════════════════════════════════════════

// ── Integrations ──────────────────────────────────────────────────────────────

function toggleIntegConfig(id) {
  const el = document.getElementById(id);
  if (!el) return;
  // Computed, not inline. A panel whose hidden state comes from a stylesheet
  // class has an empty el.style.display, which read as "open" and made the
  // first click close everything and open nothing.
  const isOpen = getComputedStyle(el).display !== 'none';
  // One open configuration gets the full grid width, including its tables.
  document.querySelectorAll('#integ-active [id$="-config"]').forEach(function(panel) {
    panel.style.display = 'none';
    const card = panel.closest('.card');
    if (card) card.classList.remove('integ-expanded');
  });
  if (!isOpen) {
    el.style.display = 'block';
    const card = el.closest('.card');
    if (card) card.classList.add('integ-expanded');
  }
}

// ── Card status ─────────────────────────────────────────────────────────────
// One look per state on every card: green for working, orange for stored but
// known not to work, grey for not set up, red for a check that failed. "Not
// configured" was red on most cards and grey on FortiGate and Sybrt AI; it is
// not an error, so it is grey everywhere.
var _INTEG_STATE_COLOR = {ok: 'var(--green)', warn: 'var(--orange)', off: 'var(--text-dim)', error: 'var(--red)'};

function _integPaint(prefix, state, text) {
  var dot = document.getElementById(prefix + '-integ-dot');
  var label = document.getElementById(prefix + '-integ-label');
  if (!dot || !label) return;
  dot.style.background = _INTEG_STATE_COLOR[state];
  label.style.color = state === 'off' ? 'var(--text-muted)' : _INTEG_STATE_COLOR[state];
  label.textContent = text || (state === 'off' ? t('status_not_configured') : t('status_configured'));
  // A failed check says nothing about whether credentials are stored.
  if (state !== 'error') _integGateActions(prefix, state !== 'off');
}

function setStatus(dotId, labelId, ok, okText, noText) {
  _integPaint(dotId.replace(/-integ-dot$/, ''), ok ? 'ok' : 'off', ok ? okText : noText);
}

// The state between configured and not: something is stored, and we know it
// did not work. Kept apart from setStatus's boolean because collapsing it into
// "ok" is what let a rejected credential show as green. Both live out here
// rather than inside loadIntegrationStatus: gdapSaveConfig calls them too, and
// as nested functions that call was a ReferenceError after every save.
function setStatusWarn(dotId, labelId, text) {
  _integPaint(dotId.replace(/-integ-dot$/, ''), 'warn', text);
}

// Actions that only work once credentials are stored. They were enabled from
// the start and answered with an error; now they wait, with the reason beside
// them.
var _INTEG_GATED = {
  itglue: {actions: '[data-click-handler="openITGlueImport"], #itglue-sync-doc-btn', reason: 'integ_itglue_needs_key'},
  also: {actions: '[data-click-handler="alsoSyncCustomers"]', reason: 'integ_needs_credentials'},
  uniweb: {actions: '#uniweb-sync-btn', reason: 'integ_needs_credentials'}
};

function _integGateActions(prefix, configured) {
  var gate = _INTEG_GATED[prefix];
  var status = gate && document.getElementById(prefix + '-integ-status');
  var card = status && status.closest('.card');
  if (!card) return;
  var buttons = card.querySelectorAll(gate.actions);
  if (!buttons.length) return;
  var hintId = prefix + '-needs-config';
  var hint = document.getElementById(hintId);
  if (!hint) {
    hint = document.createElement('div');
    hint.id = hintId;
    hint.className = 'integ-needs-config';
    // A read-only account does not see write actions, so not their reason either.
    if (buttons[0].hasAttribute('data-write')) hint.setAttribute('data-write', '');
    buttons[buttons.length - 1].parentElement.insertAdjacentElement('afterend', hint);
  }
  hint.textContent = t(gate.reason);
  hint.hidden = configured;
  buttons.forEach(function(btn) {
    btn.disabled = !configured;
    if (configured) btn.removeAttribute('aria-describedby');
    else btn.setAttribute('aria-describedby', hintId);
  });
}

// The alert settings sit on the same view, so they are loaded with it. This
// used to be done by reassigning loadIntegrationStatus at the bottom of the
// file, which hid from every reader of this function that it did more.
async function loadIntegrationStatus() {
  await _loadIntegrationCards();
  alertLoadConfig();
}

async function _loadIntegrationCards() {
  function _setVal(id, value) {
    // Tolerant of a missing element, like setStatus above: this function
    // populates several cards and a view that has not rendered one of them
    // must not stop the rest being filled in.
    const el = document.getElementById(id);
    if (el) el.value = value;
  }
  try {
    const d = await apiFetch('/api/settings');
    if (!d) return;
    // IT Glue status + populate
    var _integCount = 0, _integActive = 0;
    // A card whose module is off is hidden, so it does not count either.
    function _countInteg(configured, module) {
      if (module && !hasModule(module)) return;
      _integCount++;
      if (configured) _integActive++;
    }
    setStatus('itglue-integ-dot', 'itglue-integ-label', !!d.itglue_api_key); _countInteg(!!d.itglue_api_key);
    document.getElementById('input-itglue-key').value = d.itglue_api_key || '';
    document.getElementById('input-itglue-region').value = d.itglue_region || 'eu';
    // Autotask status + populate. The two secrets come back masked, so the
    // *_set booleans are what say whether one is stored — writing the mask
    // into the field and saving it back would store the bullets.
    setStatus('autotask-integ-dot', 'autotask-integ-label', !!d.autotask_secret_set);
    _countInteg(!!d.autotask_secret_set);
    _setVal('input-autotask-code', d.autotask_integration_code_set ? '••••••' : '');
    _setVal('input-autotask-user', d.autotask_username || '');
    _setVal('input-autotask-secret', d.autotask_secret_set ? '••••••' : '');
    _setVal('input-autotask-queue', d.autotask_default_queue_id == null ? '' : d.autotask_default_queue_id);
    _setVal('input-autotask-priority', d.autotask_default_priority == null ? '' : d.autotask_default_priority);
    _setVal('input-autotask-status', d.autotask_default_status == null ? '' : d.autotask_default_status);
    // myITprocess status + populate
    setStatus('myitprocess-integ-dot', 'myitprocess-integ-label', !!d.myitprocess_api_key_set);
    _countInteg(!!d.myitprocess_api_key_set);
    _setVal('input-myitprocess-key', d.myitprocess_api_key_set ? '••••••' : '');
    _setVal('input-myitprocess-base', d.myitprocess_base_url || '');
    // Email status + populate
    setStatus('email-integ-dot', 'email-integ-label', !!d.smtp_server); _countInteg(!!d.smtp_server);
    // ALSO status + populate
    setStatus('also-integ-dot', 'also-integ-label', !!d.also_password_set); _countInteg(!!d.also_password_set, 'billing');
    var _alsoU = document.getElementById('input-also-username');
    var _alsoP = document.getElementById('input-also-password');
    var _alsoC = document.getElementById('input-also-country');
    if (_alsoU) _alsoU.value = d.also_username || '';
    if (_alsoP) _alsoP.value = d.also_password || '';
    if (_alsoC) _alsoC.value = d.also_country || 'no';
    // UniFi Site Manager status. It was absent from this block entirely, so it
    // never counted towards "n/m configured" and its card was left on whatever
    // unifiSmLoadSaved() painted — blue "key saved" rather than the green every
    // other integration shows for a stored credential. A key that is stored is
    // configured here, exactly as it is for IT Glue and the rest.
    setStatus('unifi-sm-integ-dot', 'unifi-sm-integ-label', !!d.unifi_site_manager_api_key_set); _countInteg(!!d.unifi_site_manager_api_key_set);
    // Tailscale status + populate
    setStatus('ts-integ-dot', 'ts-integ-label', !!d.tailscale_api_key_set); _countInteg(!!d.tailscale_api_key_set, 'tailscale');
    var _tsKey = document.getElementById('input-ts-api-key');
    var _tsTailnet = document.getElementById('input-ts-tailnet');
    if (_tsKey) _tsKey.value = d.tailscale_api_key || '';
    if (_tsTailnet) _tsTailnet.value = d.tailscale_tailnet || '-';
    // GDAP / Partner Center status + populate
    // Three states. Credentials stored is not the same claim as credentials
    // that work: a client secret Partner Center had just rejected still went
    // green and stayed green, because this card is repainted from the stored
    // config and the config recorded only that a setup had been attempted.
    // gdap_validated is null for configs written before it was recorded — that
    // is "we do not know", not "broken", so those keep their old appearance.
    if (d.gdap_configured && d.gdap_validated === false) {
      setStatusWarn('gdap-integ-dot', 'gdap-integ-label',
        t('gdap_status_unverified', 'Lagret, ikke verifisert'));
    } else {
      setStatus('gdap-integ-dot', 'gdap-integ-label', !!d.gdap_configured);
    }
    _countInteg(!!(d.gdap_configured && d.gdap_validated !== false));
    if (d.gdap_configured) {
      var _gdapBtn = document.getElementById('gdap-discover-btn');
      if (_gdapBtn) _gdapBtn.style.display = 'block';
      var _gdapCount = document.getElementById('gdap-customer-count');
      if (_gdapCount && d.gdap_customer_count) _gdapCount.textContent = d.gdap_customer_count + ' ' + t('gdap_customers_linked', 'kunder koblet');
    }
    var _gdapTenant = document.getElementById('input-gdap-tenant');
    var _gdapClient = document.getElementById('input-gdap-client');
    if (_gdapTenant) _gdapTenant.value = d.gdap_partner_tenant_id || '';
    if (_gdapClient) _gdapClient.value = d.gdap_client_id || '';
    // Uniweb status + populate
    setStatus('uniweb-integ-dot', 'uniweb-integ-label', !!d.uniweb_password_set); _countInteg(!!d.uniweb_password_set, 'billing');
    var _uwEmail = document.getElementById('input-uniweb-email');
    var _uwPass = document.getElementById('input-uniweb-password');
    if (_uwEmail) _uwEmail.value = d.uniweb_email || '';
    if (_uwPass) _uwPass.value = d.uniweb_password || '';
    if (d.uniweb_password_set && typeof uniwebCheckStatus === 'function') uniwebCheckStatus();
    // Update summary. The dot is green only when something is set up; a green
    // dot beside "0 of 9" read as all clear.
    var sumEl = document.getElementById('integ-summary');
    if (sumEl) sumEl.innerHTML = '<span style="color:' + (_integActive ? 'var(--green)' : 'var(--text-dim)') + ';">&#9679;</span> '
      + esc(t('integ_summary').replace('{active}', String(_integActive)).replace('{total}', String(_integCount)));
    document.getElementById('input-smtp-server').value = d.smtp_server || '';
    document.getElementById('input-smtp-port').value = d.smtp_port || 587;
    document.getElementById('input-smtp-user').value = d.smtp_user || '';
    document.getElementById('input-smtp-password').value = d.smtp_password || '';
    document.getElementById('input-smtp-from').value = d.smtp_from || '';
    document.getElementById('input-email-recipient').value = d.email_default_recipient || '';
    document.getElementById('input-email-auto-send').checked = d.email_auto_send || false;
  } catch(e) {
    _integPaint('itglue', 'error', t('err_check_failed'));
  }
  // Webhook / scheduler status + populate
  try {
    const sched = await apiFetch('/api/scheduler');
    if (!sched) return;
    setStatus('webhook-integ-dot', 'webhook-integ-label', !!sched.webhook_url);
    document.getElementById('input-webhook-url').value = sched.webhook_url || '';
    const ao = sched.alert_on || {};
    document.getElementById('alert-audit-completed').checked = ao.audit_completed !== false;
    document.getElementById('alert-risk-score-drop').checked = ao.risk_score_drop !== false && ao.risk_score_drop !== 0;
    document.getElementById('alert-risk-score-drop-threshold').value = (typeof ao.risk_score_drop === 'number' ? ao.risk_score_drop : 5);
    document.getElementById('alert-new-risky-users').checked = ao.new_risky_users !== false;
    document.getElementById('alert-expired-credentials').checked = ao.expired_credentials !== false;
    document.getElementById('alert-secure-score-drop').checked = ao.secure_score_drop !== false && ao.secure_score_drop !== 0;
    document.getElementById('alert-secure-score-drop-threshold').value = (typeof ao.secure_score_drop === 'number' ? ao.secure_score_drop : 5);
    document.getElementById('alert-new-nsg-warnings').checked = ao.new_nsg_warnings !== false;
    document.getElementById('alert-mfa-below-threshold').checked = ao.mfa_below_threshold !== false && ao.mfa_below_threshold !== 0;
    document.getElementById('alert-mfa-threshold').value = (typeof ao.mfa_below_threshold === 'number' ? ao.mfa_below_threshold : 80);
  } catch(e) { console.warn('Alert options init failed:', e); }
}

async function testMyITProcess() {
  const out = document.getElementById('myitprocess-test-result');
  out.textContent = t('msg_testing', 'Tester…');
  out.style.color = 'var(--text-muted)';

  // Save first, same as the Autotask card. The endpoint can test an unsaved
  // key, but this button is the only thing on the card that writes — testing
  // without saving would leave an operator who saw "OK" with nothing stored.
  const saved = await _saveMyITProcessSettings();
  if (!saved) { out.textContent = t('msg_save_failed', 'Kunne ikke lagre'); out.style.color = 'var(--red)'; return; }

  const d = await apiFetch('/api/myitprocess/test', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}',
  });
  if (d && d.ok) {
    // The field names are the point of this test — nothing in the client has
    // met a real server, so what came back is what corrects it.
    const fields = (d.sample_fields || []).join(', ');
    out.textContent = t('status_ok', 'OK') + (fields ? ' · ' + fields : '');
    out.style.color = 'var(--green)';
  } else {
    out.textContent = (d && d.error) || t('msg_failed', 'Feilet');
    out.style.color = 'var(--red)';
  }
}

async function _saveMyITProcessSettings() {
  const val = function(id) { const el = document.getElementById(id); return el ? el.value.trim() : ''; };
  const body = {myitprocess_base_url: val('input-myitprocess-base')};
  // The mask means "unchanged". Sending it back would store the bullets.
  const key = val('input-myitprocess-key');
  if (key && key !== '••••••') body.myitprocess_api_key = key;

  const d = await apiFetch('/api/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  return !!(d && !d.error);
}

async function testAutotask() {
  const out = document.getElementById('autotask-test-result');
  out.textContent = t('msg_testing', 'Tester…');
  out.style.color = 'var(--text-muted)';

  // Save first. Zone discovery and the query both run server-side from stored
  // settings, so testing what is on screen means storing it — otherwise the
  // operator tests the previous credentials and is told they work.
  const saved = await _saveAutotaskSettings();
  if (!saved) { out.textContent = t('msg_save_failed', 'Kunne ikke lagre'); out.style.color = 'var(--red)'; return; }

  const d = await apiFetch('/api/autotask/test', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}',
  });
  if (d && d.ok) {
    out.textContent = t('status_ok', 'OK');
    out.style.color = 'var(--green)';
    _integPaint('autotask', 'ok');
  } else {
    out.textContent = (d && d.error) || t('msg_failed', 'Feilet');
    out.style.color = 'var(--red)';
  }
}

async function _saveAutotaskSettings() {
  const val = function(id) { const el = document.getElementById(id); return el ? el.value.trim() : ''; };
  const body = {
    autotask_username: val('input-autotask-user'),
    autotask_default_queue_id: val('input-autotask-queue'),
    autotask_default_priority: val('input-autotask-priority'),
    autotask_default_status: val('input-autotask-status'),
  };
  // The mask means "unchanged". Sending it back would store the bullets as the
  // secret, which is the classic way a settings form destroys a credential.
  const code = val('input-autotask-code');
  const secret = val('input-autotask-secret');
  if (code && code !== '••••••') body.autotask_integration_code = code;
  if (secret && secret !== '••••••') body.autotask_secret = secret;

  const d = await apiFetch('/api/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  return !!(d && !d.error);
}

async function saveITGlueSettings() {
  const msg = document.getElementById('itglue-save-msg');
  msg.textContent = t('btn_saving'); msg.style.color = 'var(--text-muted)';
  const d = await apiFetch('/api/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      itglue_api_key: document.getElementById('input-itglue-key').value.trim(),
      itglue_region: document.getElementById('input-itglue-region').value,
    })
  });
  if (d && !d.error) {
    msg.textContent = t('msg_saved'); msg.style.color = 'var(--green)';
    _integPaint('itglue', document.getElementById('input-itglue-key').value.trim() ? 'ok' : 'off');
  } else {
    msg.textContent = t('msg_error'); msg.style.color = 'var(--red)';
  }
  setTimeout(() => { msg.textContent = ''; }, 3000);
}

// ── GDAP / Partner Center ─────────────────────────────────────────────────
async function gdapSaveConfig() {
  var msg = document.getElementById('gdap-config-msg');
  msg.textContent = t('btn_saving'); msg.style.color = 'var(--text-muted)';
  var tenant = document.getElementById('input-gdap-tenant').value.trim();
  var client = document.getElementById('input-gdap-client').value.trim();
  var secret = document.getElementById('input-gdap-secret').value.trim();
  if (!tenant || !client) {
    msg.textContent = t('gdap_err_missing_fields', 'Partner Tenant ID og Client ID er paakrevd');
    msg.style.color = 'var(--red)';
    return;
  }
  var d = await apiFetch('/api/gdap/setup', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ partner_tenant_id: tenant, client_id: client, client_secret: secret })
  });
  if (d && d.ok) {
    if (d.validated) {
      msg.innerHTML = '<span style="color:var(--green);">' + t('msg_saved') + ' · ' + Number(d.customer_count) + ' ' + t('gdap_customers_found', 'kunder funnet') + '</span>';
    } else {
      msg.innerHTML = '<span style="color:var(--orange);">' + t('msg_saved') + ' · ' + esc(d.warning || '') + '</span>';
    }
    if (d.validated) {
      setStatus('gdap-integ-dot', 'gdap-integ-label', true);
    } else {
      setStatusWarn('gdap-integ-dot', 'gdap-integ-label',
        t('gdap_status_unverified', 'Lagret, ikke verifisert'));
    }
    document.getElementById('gdap-discover-btn').style.display = 'block';
    if (d.customer_count) {
      var cc = document.getElementById('gdap-customer-count');
      if (cc) cc.textContent = d.customer_count + ' ' + t('gdap_customers_linked', 'kunder koblet');
    }
  } else {
    msg.textContent = t('msg_error'); msg.style.color = 'var(--red)';
  }
}

async function gdapTestConnection() {
  var msg = document.getElementById('gdap-config-msg');
  msg.textContent = t('msg_checking'); msg.style.color = 'var(--text-muted)';
  // Save first (in case credentials changed)
  await gdapSaveConfig();
}

async function gdapDiscoverCustomers() {
  var panel = document.getElementById('gdap-discover-panel');
  var list = document.getElementById('gdap-discover-list');
  panel.style.display = 'block';
  list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;">' + t('msg_loading', 'Laster...') + '</div>';
  var d = await apiFetch('/api/gdap/customers');
  if (!d || !d.customers) {
    list.innerHTML = '<div style="color:var(--red);font-size:12px;">' + t('msg_error') + '</div>';
    return;
  }
  if (d.customers.length === 0) {
    list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;">' + t('gdap_no_customers', 'Ingen kunder funnet i Partner Center') + '</div>';
    return;
  }
  var html = '';
  d.customers.forEach(function(c) {
    var imported = c.already_imported;
    var gdapBadge = c.gdap_status === 'active' ? '<span style="background:var(--green);color:#fff;padding:1px 6px;border-radius:8px;font-size:10px;margin-left:6px;">GDAP</span>' : '';
    var importedBadge = imported ? '<span style="background:var(--blue);color:#fff;padding:1px 6px;border-radius:8px;font-size:10px;margin-left:6px;">' + (c.local_auth_mode === 'gdap' ? 'GDAP' : 'Legacy') + '</span>' : '';
    html += '<label style="display:flex;align-items:center;gap:8px;padding:6px 4px;border-bottom:1px solid var(--border);cursor:pointer;font-size:13px;">';
    html += '<input type="checkbox" class="gdap-import-cb" value="' + esc(c.tenant_id) + '" ' + (imported ? 'checked disabled' : '') + ' style="flex-shrink:0;">';
    html += '<div style="flex:1;min-width:0;">';
    html += '<div style="font-weight:600;">' + esc(c.company_name) + gdapBadge + importedBadge + '</div>';
    html += '<div style="font-size:11px;color:var(--text-dim);font-family:var(--mono);">' + esc(c.domain || c.tenant_id) + '</div>';
    if (c.gdap_roles && c.gdap_roles.length) {
      html += '<div style="font-size:10px;color:var(--text-muted);margin-top:2px;">' + t('gdap_roles', 'Roller') + ': ' + esc(c.gdap_roles.join(', ')) + '</div>';
    }
    html += '</div></label>';
  });
  list.innerHTML = html;
}

async function gdapImportSelected() {
  var cbs = document.querySelectorAll('.gdap-import-cb:checked:not(:disabled)');
  var tenantIds = [];
  cbs.forEach(function(cb) { tenantIds.push(cb.value); });
  if (tenantIds.length === 0) {
    showToast(t('gdap_select_customers', 'Velg minst en kunde'), 'warning');
    return;
  }
  var msg = document.getElementById('gdap-import-msg');
  msg.textContent = t('gdap_importing', 'Importerer...'); msg.style.color = 'var(--text-muted)';
  var d = await apiFetch('/api/gdap/import', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ tenant_ids: tenantIds })
  });
  if (d && d.imported) {
    var created = d.imported.filter(function(i) { return i.action === 'created'; }).length;
    var converted = d.imported.filter(function(i) { return i.action === 'converted'; }).length;
    msg.innerHTML = '<span style="color:var(--green);">' + created + ' ' + t('gdap_created', 'opprettet') + ', ' + converted + ' ' + t('gdap_converted', 'konvertert til GDAP') + '</span>';
    // Refresh the customer list. This called refreshCustomerList, which no
    // script defines, behind a typeof guard, so the imported customers only
    // appeared after the user reloaded the page.
    loadCustomers();
    showToast(t('gdap_import_success', 'Kunder importert fra Partner Center'), 'success');
  } else {
    msg.textContent = t('msg_error'); msg.style.color = 'var(--red)';
  }
}

async function saveEmailSettings() {
  const msg = document.getElementById('email-save-msg');
  msg.textContent = t('btn_saving'); msg.style.color = 'var(--text-muted)';
  const d = await apiFetch('/api/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      smtp_server: document.getElementById('input-smtp-server').value.trim(),
      smtp_port: parseInt(document.getElementById('input-smtp-port').value) || 587,
      smtp_user: document.getElementById('input-smtp-user').value.trim(),
      smtp_password: document.getElementById('input-smtp-password').value.trim(),
      smtp_from: document.getElementById('input-smtp-from').value.trim(),
      email_default_recipient: document.getElementById('input-email-recipient').value.trim(),
      email_auto_send: document.getElementById('input-email-auto-send').checked,
    })
  });
  if (d && !d.error) {
    msg.textContent = t('msg_saved'); msg.style.color = 'var(--green)';
    _integPaint('email', document.getElementById('input-smtp-server').value.trim() ? 'ok' : 'off');
  } else {
    msg.textContent = t('msg_error'); msg.style.color = 'var(--red)';
  }
  setTimeout(() => { msg.textContent = ''; }, 3000);
}

async function saveWebhookSettings() {
  const msg = document.getElementById('webhook-save-msg');
  msg.textContent = t('btn_saving'); msg.style.color = 'var(--text-muted)';
  const d = await apiFetch('/api/scheduler', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      webhook_url: document.getElementById('input-webhook-url').value.trim(),
      alert_on: {
        audit_completed: document.getElementById('alert-audit-completed').checked,
        risk_score_drop: document.getElementById('alert-risk-score-drop').checked ? (parseInt(document.getElementById('alert-risk-score-drop-threshold').value) || 5) : false,
        new_risky_users: document.getElementById('alert-new-risky-users').checked,
        expired_credentials: document.getElementById('alert-expired-credentials').checked,
        secure_score_drop: document.getElementById('alert-secure-score-drop').checked ? (parseInt(document.getElementById('alert-secure-score-drop-threshold').value) || 5) : false,
        new_nsg_warnings: document.getElementById('alert-new-nsg-warnings').checked,
        mfa_below_threshold: document.getElementById('alert-mfa-below-threshold').checked ? (parseInt(document.getElementById('alert-mfa-threshold').value) || 80) : false,
      },
    })
  });
  if (d && !d.error) {
    msg.textContent = t('msg_saved'); msg.style.color = 'var(--green)';
    _integPaint('webhook', document.getElementById('input-webhook-url').value.trim() ? 'ok' : 'off');
  } else {
    msg.textContent = t('msg_error'); msg.style.color = 'var(--red)';
  }
  setTimeout(() => { msg.textContent = ''; }, 3000);
}
