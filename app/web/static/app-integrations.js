// ═══════════════════════════════════════════════════════════════════
// SHOW VIEW — add new views to the switch
// ═══════════════════════════════════════════════════════════════════
// Map sub-views to their parent nav dropdown
var _navParentMap = {
  'home': 'customers', 'customers': 'customers', 'history': 'customers',
  'hosts': 'remote', 'terminal': 'remote', 'rdp': 'remote',
  'network': 'network', 'vpn': 'network', 'tls': 'network', 'tailscale': 'network',
  'ssh': 'tools', 'browser': 'tools', 'provision': 'tools', 'policy-deploy': 'tools',
};

var _origShowView = showView;
showView = function(name) {
  _origShowView(name);

  // Parent-dropdown highlighting is already done by _origShowView via the
  // .active CSS class (see _remoteViews/_customerViews/etc. maps). An older
  // version of this override did the same work plus set an inline
  // style.borderBottom on the parent button. Problem: the clearing loop
  // used the selector ".nav-dropdown > .nav-btn", which did not match
  // #nav-remote (it's a flat button, not wrapped in .nav-dropdown). Result:
  // once you visited a Fjernaksess sub-view, the inline underline stayed
  // forever, even after navigating to unrelated views. Dropped the
  // redundant work; CSS ".nav-btn.active" renders the same underline.

  if (name === 'hosts') hostsLoad();
  else if (name === 'ssh') sshShowKeys();
  else if (name === 'vpn') vpnLoadProfiles();
  else if (name === 'live') livePollNow();
  else if (name === 'terminal') {
    var ts = document.getElementById('term-screen');
    if (ts) ts.focus();
  }
  else if (name === 'tls') tlsLoadView();
  else if (name === 'policy-deploy') policyDeployLoad();
  else if (name === 'assessments') assessmentsLoad();
  else if (name === 'tailscale') tsLoadView();
  else if (name === 'browser') browserInit();
  else if (name === 'rdp') rdpInit();
  else if (name === 'docs') docsRepoLoad();
  else if (name === 'ai') {
    aiLoadCustomers();
    var el = document.getElementById('ai-status');
    apiFetch('/api/claude/status').then(function(d) {
      if (el && d) el.textContent = d.available ? d.model : t('msg_not_configured_setup_api_key','Not configured — set up API key in Settings');
    });
  }
};


// Hook alert config load into integration status load
var _origLoadIntegrationStatus = typeof loadIntegrationStatus === 'function' ? loadIntegrationStatus : null;
if (_origLoadIntegrationStatus) {
  loadIntegrationStatus = async function() {
    await _origLoadIntegrationStatus();
    if (typeof alertLoadConfig === 'function') alertLoadConfig();
  };
}


// ── Docs tab switching ───────────────────────────────────────────────────────
function switchDocsTab(btn, paneId) {
  document.querySelectorAll('.docs-tab-btn').forEach(function(b) {
    b.classList.remove('active');
    b.style.borderBottomColor = 'transparent';
  });
  btn.classList.add('active');
  btn.style.borderBottomColor = 'var(--blue)';
  document.querySelectorAll('.docs-tab-pane').forEach(function(p) { p.style.display = 'none'; });
  var pane = document.getElementById(paneId);
  if (pane) pane.style.display = 'block';
}

// ── In-app docs viewer ───────────────────────────────────────────────────
// Renders the markdown files shipped under docs/ in the repo. Tree pulled
// from /api/docs/list, individual files from /api/docs/file?path=…, then
// rendered client-side with marked.js + sanitised through DOMPurify so a
// future contributor can't sneak <script> into a doc and run it in our
// origin.

var _docsRepoTreeLoaded = false;

async function docsRepoLoad() {
  if (_docsRepoTreeLoaded) return;
  var treeBox = document.getElementById('docs-repo-tree');
  if (!treeBox) return;
  treeBox.innerHTML = '<div style="color:var(--text-muted);">' + t('laster') + '</div>';
  try {
    var data = await apiFetch('/api/docs/list');
    if (!data || !data.root) throw new Error('no tree');
    treeBox.innerHTML = _docsRenderTree(data.root, 0);
    _docsRepoTreeLoaded = true;
    // Auto-open a sensible default so the right pane isn't empty — chosen
    // from what the tree actually offers. It used to name USER_GUIDE.md, or
    // no/HURTIGSTART.md on a Norwegian UI, and docs/ holds neither: every
    // visit to this tab opened on "Could not open the document", with a
    // working list of files beside it.
    var offered = _docsFileList(data.root);
    var preferred = (typeof _lang !== 'undefined' && _lang === 'no')
      ? ['no/HURTIGSTART.md', 'README.md']
      : ['USER_GUIDE.md', 'README.md'];
    var defaultDoc = null;
    for (var i = 0; i < preferred.length && !defaultDoc; i++) {
      if (offered.indexOf(preferred[i]) !== -1) defaultDoc = preferred[i];
    }
    if (!defaultDoc && offered.length) defaultDoc = offered[0];
    if (defaultDoc) docsRepoOpen(defaultDoc);
  } catch (e) {
    treeBox.innerHTML = '<div style="color:var(--color-danger);">' + t('integ_docs_load_failed','Kunne ikke laste dokumentasjon') + ': ' + esc(String(e)) + '</div>';
  }
}

// Every file path in the tree, depth-first, in the order the tree shows them.
function _docsFileList(node) {
  if (!node) return [];
  if (node.type === 'file') return [node.path];
  var out = [];
  (node.children || []).forEach(function(c) {
    out = out.concat(_docsFileList(c));
  });
  return out;
}

function _docsRenderTree(node, depth) {
  if (node.type === 'file') {
    var pretty = node.name.replace(/\.md$/i, '').replace(/_/g, ' ');
    var safePath = esc(node.path);
    return '<div class="docs-tree-file" data-docs-path="' + safePath + '" style="padding:4px 6px;cursor:pointer;border-radius:var(--radius-sm);font-family:var(--mono);font-size:12px;color:var(--text);" onclick="docsRepoOpen(\'' + safePath.replace(/'/g, "\\'") + '\')">' + esc(pretty) + '</div>';
  }
  // dir
  var label = depth === 0 ? '' : (
    '<div style="font-weight:600;margin-top:8px;color:var(--blue);font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">' + esc(node.name) + '/</div>'
  );
  var indent = depth === 0 ? '' : 'margin-left:12px;border-left:1px dashed var(--border);padding-left:8px;';
  var children = (node.children || []).map(function(c) { return _docsRenderTree(c, depth + 1); }).join('');
  return label + '<div style="' + indent + '">' + children + '</div>';
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
    content.innerHTML = window.DOMPurify.sanitize(rendered, { USE_PROFILES: { html: true } });
    content.scrollTop = 0;
    // Highlight selected file in the tree
    document.querySelectorAll('.docs-tree-file').forEach(function(el) {
      el.style.background = el.getAttribute('data-docs-path') === path ? 'rgba(77,159,181,0.18)' : '';
    });
  } catch (e) {
    content.innerHTML = '<div style="color:var(--color-danger);">' + t('integ_doc_open_failed','Kunne ikke åpne dokumentet') + ': ' + esc(String(e)) + '</div>';
  }
}

// ── Wiki / Integration Guide: render every card from markdown ───────────────
// Every card in the `integ-wiki` tab is a shell that loads its content from
// `docs/api/<slug>/WIKI[.<lang>].md` on first Wiki-tab activation. Single
// source of truth per integration, one pattern for all cards, language-
// aware: probe `.<lang>.md` first, fall back to the canonical `.md`.
//
// GDAP uses the pre-existing `INTEGRATION.md` under `partner-center/` so the
// Wiki tab and the Docs tab share one file for that integration.
//
// The language-variant probe uses raw fetch() rather than apiFetch() so a
// 404 (no translation yet) is a quiet fall-through, not a user-visible
// error toast. apiFetch is still used for the canonical fetch so genuine
// failures (network, 5xx) surface normally.
var WIKI_CARDS = [
  { slug: 'itglue',          base: 'api/itglue/WIKI' },
  { slug: 'vpn',             base: 'api/vpn/WIKI' },
  { slug: 'guacamole',       base: 'api/guacamole/WIKI' },
  { slug: 'unifi',           base: 'api/unifi/WIKI' },
  { slug: 'fortigate',       base: 'api/fortigate/WIKI' },
  { slug: 'tailscale',       base: 'api/tailscale/WIKI' },
  { slug: 'also-cloud',      base: 'api/also-cloud/WIKI' },
  { slug: 'uniweb',          base: 'api/uniweb/WIKI' },
  { slug: 'tls-monitor',     base: 'api/tls-monitor/WIKI' },
  { slug: 'microsoft-graph', base: 'api/microsoft-graph/WIKI' },
  { slug: 'gdap',            base: 'api/partner-center/INTEGRATION' },
  { slug: 'claude',          base: 'api/claude/WIKI' },
  { slug: 'autotask-datto',  base: 'api/autotask-datto/WIKI' },
  { slug: 'connectwise',     base: 'api/connectwise/WIKI' },
  { slug: 'halo-psa',        base: 'api/halo-psa/WIKI' },
  { slug: 'teams-webhook',   base: 'api/teams-webhook/WIKI' },
  { slug: 'smtp',            base: 'api/smtp/WIKI' },
  { slug: 'power-bi',        base: 'api/power-bi/WIKI' },
  { slug: 'rest-api',        base: 'api/rest-api/WIKI' },
];

var _wikiLoadedLang = null;

async function _wikiProbeDoc(path) {
  try {
    var r = await fetch('/api/docs/file?path=' + encodeURIComponent(path));
    if (!r.ok) return null;
    var data = await r.json();
    return (data && data.content) ? data : null;
  } catch (_) {
    return null;
  }
}

function _wikiRenderInto(body, content) {
  if (typeof window.marked === 'undefined' || typeof window.DOMPurify === 'undefined') {
    body.innerHTML = '<pre style="white-space:pre-wrap;font-family:var(--mono);font-size:12px;">' + esc(content) + '</pre>';
    return;
  }
  var rendered = window.marked.parse(content, { gfm: true, breaks: false });
  body.innerHTML = window.DOMPurify.sanitize(rendered, { USE_PROFILES: { html: true } });
}

async function _wikiLoadOneCard(card, lang) {
  var body = document.getElementById('wiki-' + card.slug + '-body');
  if (!body) return;
  var data = await _wikiProbeDoc(card.base + '.' + lang + '.md');
  if (!data) data = await _wikiProbeDoc(card.base + '.md');
  if (!data) {
    body.innerHTML = '<div style="color:var(--color-danger);">' +
      esc(t('err_could_not_load_doc','Kunne ikke laste dokumentasjon')) +
      ': <code style="font-size:11px;">' + esc(card.base) + '</code></div>';
    return;
  }
  _wikiRenderInto(body, data.content);
}

async function wikiLoadAllCards() {
  var lang = (typeof _lang !== 'undefined' && _lang) ? _lang : 'no';
  if (_wikiLoadedLang === lang) return;
  await Promise.all(WIKI_CARDS.map(function(c) { return _wikiLoadOneCard(c, lang); }));
  _wikiLoadedLang = lang;
}

// Backwards-compatible alias — older call sites (switchIntegTab) may still
// invoke wikiLoadGdap by name until their next reload.
async function wikiLoadGdap() { return wikiLoadAllCards(); }

// ── ALSO Cloud Marketplace ───────────────────────────────────────────────────
async function alsoTestConnection() {
  var msg = document.getElementById('also-config-msg');
  msg.innerHTML = '<span style="color:var(--text-muted);">' + t('msg_testing','Testing...') + '</span>';
  try {
    var d = await apiFetch('/api/also/test', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        username: document.getElementById('input-also-username').value.trim(),
        password: document.getElementById('input-also-password').value.trim(),
        country: document.getElementById('input-also-country').value,
      })
    });
    if (d && d.ok) {
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
      + '<div style="margin-bottom:var(--space-2);"><strong>' + t('also') + '</strong> ' + d.also_total + ' | <span style="color:var(--green);">Matched: ' + d.matched + '</span> | <span style="color:var(--blue);">New: ' + d.new + '</span></div>';

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
      html += '<button class="btn btn-primary btn-sm" data-write onclick="alsoDoImport()">' + t('btn_import','Import') + ' ' + newC.length + ' ' + t('nav_customers').toLowerCase() + '</button>';
    } else {
      html += '<div style="color:var(--green);">' + t('all_also_customers_already_matched') + '</div>';
    }

    if (matched.length > 0) {
      // Check how many are NOT yet linked (missing AlsoAccountId)
      var unlinked = matched.filter(function(c){return c.also_id && c.match && c.match.toolkit_id;});
      if (unlinked.length > 0) {
        html += '<div style="margin-top:var(--space-3);padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-md);display:flex;align-items:center;gap:var(--space-3);">';
        html += '<span style="font-size:var(--font-sm);flex:1;">' + unlinked.length + ' matched customers can be linked to ALSO for license viewing</span>';
        html += '<button class="btn btn-primary btn-sm" data-write onclick="alsoLinkMatched()" id="also-link-btn">' + t('link_all') + '</button>';
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
    document.getElementById('also-config-msg').innerHTML = '<span style="color:var(--green);">&#10003; ' + d.imported + ' imported</span>';
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
    document.getElementById('uniweb-integ-dot').style.background = 'var(--green)';
    document.getElementById('uniweb-integ-label').textContent = t('integ_configured','Konfigurert');
    document.getElementById('uniweb-integ-label').style.color = 'var(--green)';
  } else {
    msg.innerHTML = '<span style="color:var(--red);">' + esc(d && d.error ? d.error : t('integ_error','Feil')) + '</span>';
  }
}

// ── Uniweb sync progress CSS (injected once) ───────────────────────────────
(function() {
  if (document.getElementById('uniweb-sync-styles')) return;
  var style = document.createElement('style');
  style.id = 'uniweb-sync-styles';
  style.textContent = [
    '@keyframes uniweb-pulse { 0%,100% { opacity:1; } 50% { opacity:.55; } }',
    '.uniweb-sync-active { animation: uniweb-pulse 1.8s ease-in-out infinite; }',
    '.uniweb-progress-track { width:100%; height:8px; background:var(--bg-tertiary); border-radius:4px; overflow:hidden; margin:6px 0; }',
    '.uniweb-progress-fill { height:100%; background:linear-gradient(90deg,var(--blue),#6ec6e6); border-radius:4px; transition:width .6s ease; min-width:2%; }',
    '.uniweb-sync-panel { background:var(--bg-secondary); border:1px solid var(--border); border-radius:var(--radius-md); padding:12px 14px; margin-top:8px; font-size:12px; }',
    '.uniweb-sync-row { display:flex; justify-content:space-between; align-items:center; }',
    '.uniweb-sync-label { color:var(--text-muted); font-size:11px; }',
    '.uniweb-sync-value { font-family:var(--mono); font-size:11px; }',
    '.uniweb-summary { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:8px; margin-top:8px; }',
    '.uniweb-summary-card { background:var(--bg-tertiary); border-radius:var(--radius-md); padding:10px 12px; text-align:center; }',
    '.uniweb-summary-card .val { font-size:18px; font-weight:700; font-family:var(--mono); }',
    '.uniweb-summary-card .lbl { font-size:10px; color:var(--text-muted); margin-top:2px; }',
  ].join('\n');
  document.head.appendChild(style);
})();

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

    var synced = d.accounts_synced || 0;
    var total = d.total_accounts || 0;
    var pct = total > 0 ? Math.round((synced / total) * 100) : 0;

    // Estimate remaining time
    var etaStr = '—';
    if (synced > 0 && total > 0 && synced < total) {
      var msPerAccount = elapsed / synced;
      var remaining = (total - synced) * msPerAccount;
      etaStr = 'ca. ' + _uniwebFormatDuration(remaining);
    }

    var accountLabel = d.current_account ? esc(d.current_account) : '...';

    var html = '<div class="uniweb-sync-panel uniweb-sync-active">';
    html += '<div class="uniweb-sync-row" style="margin-bottom:4px;">';
    html += '<span style="font-weight:600;color:var(--blue);">' + t('synkroniserer_uniweb') + '</span>';
    html += '<span class="uniweb-sync-value">' + synced + ' av ' + (total || '?') + ' kontoer</span>';
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
    html += '<span class="uniweb-sync-label">Forlopt tid: ' + elapsedStr + '</span>';
    html += '<span class="uniweb-sync-label">Gjenstaaende: ' + etaStr + '</span>';
    html += '</div>';

    // Domains found so far
    if (d.domains_found > 0) {
      html += '<div class="uniweb-sync-row" style="margin-top:4px;">';
      html += '<span class="uniweb-sync-label">Domener funnet: ' + d.domains_found + '</span>';
      if (d.errors_count > 0) {
        html += '<span class="uniweb-sync-label" style="color:var(--orange);">' + t('integ_error','Feil') + ': ' + d.errors_count + '</span>';
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
      var html = '<div class="uniweb-sync-panel" style="border-color:var(--green);">';
      html += '<span style="color:var(--green);font-weight:600;">' + t('synkronisering_fullfort') + '</span>';
      if (totalElapsed) {
        html += '<span class="uniweb-sync-label" style="margin-left:8px;">(' + totalElapsed + ')</span>';
      }

      // Summary cards
      html += '<div class="uniweb-summary">';
      html += '<div class="uniweb-summary-card"><div class="val">' + (d.total_accounts || 0) + '</div><div class="lbl">' + t('kontoer') + '</div></div>';
      html += '<div class="uniweb-summary-card"><div class="val">' + (d.domains_found || 0) + '</div><div class="lbl">' + t('domener_2') + '</div></div>';
      if (d.errors_count > 0) {
        html += '<div class="uniweb-summary-card" style="border:1px solid var(--orange);"><div class="val" style="color:var(--orange);">' + d.errors_count + '</div><div class="lbl">' + t('feil') + '</div></div>';
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
  var matchedCount = d.total - unmatchedCount;
  var unmatchedBadge = '';
  if (unmatchedCount > 0) {
    unmatchedBadge = ' <span style="display:inline-block;background:var(--orange);color:#fff;font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;margin-left:6px;">' + unmatchedCount + ' ' + t('integ_of','av') + ' ' + d.total + ' ' + t('integ_customers_unlinked','kunder ikke koblet') + '</span>';
  }

  var html = '<div style="font-size:12px;font-weight:600;margin-bottom:8px;">Kontoer (' + d.total + ')' + unmatchedBadge + '</div>';
  html += '<div style="max-height:400px;overflow-y:auto;border:1px solid var(--border);border-radius:var(--radius-md);">';
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
      customerCol = '<button class="btn btn-ghost" data-write onclick="uniwebShowMatch(\'' + esc(a.id) + '\')" style="padding:2px 8px;font-size:10px;color:var(--orange);">' + t('ikke_koblet') + '</button>';
    }

    html += '<tr style="border-bottom:1px solid var(--border);">';
    html += '<td style="padding:6px 8px;"><a href="#" onclick="uniwebShowDetail(\'' + esc(a.id) + '\');return false;" style="color:var(--blue);text-decoration:none;">' + esc(a.name) + '</a></td>';
    html += '<td style="padding:6px 8px;">' + customerCol + '</td>';
    html += '<td style="text-align:center;padding:6px 8px;">' + a.domain_count + '</td>';
    html += '<td style="text-align:center;padding:6px 8px;">' + a.subscription_count + '</td>';
    html += '<td style="text-align:right;padding:6px 8px;font-family:var(--mono);">' + (a.monthly_total > 0 ? a.monthly_total.toFixed(0) : '-') + '</td>';
    html += '<td style="text-align:center;padding:6px 8px;">' + (a.earliest_renewal || '-') + '</td>';
    html += '</tr>';
  });

  html += '</tbody></table></div>';

  // Add "Importer kunder" button if there are unmatched accounts
  if (unmatchedCount > 0) {
    html += '<div style="margin-top:10px;">';
    html += '<button class="btn btn-primary" data-write onclick="uniwebShowImport()" style="padding:6px 14px;font-size:12px;">' + t('integ_import_from_uniweb','Importer kunder fra Uniweb') + ' (' + unmatchedCount + ')</button>';
    html += '</div>';
  }

  container.innerHTML = html;
}

async function uniwebShowMatch(accountId) {
  var d = await apiFetch('/api/uniweb/matches');
  if (!d) return;

  var customers = d.available_customers || [];
  var html = '<div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;" id="uniweb-match-modal" onclick="if(event.target===this)this.remove()">';
  html += '<div class="card" style="width:400px;max-height:500px;padding:20px;" onclick="event.stopPropagation()">';
  html += '<div style="font-weight:600;font-size:14px;margin-bottom:12px;">' + t('koble_uniweb_konto_til_msp') + '</div>';
  html += '<select id="uniweb-match-select" class="field-input" style="margin-bottom:12px;">';
  html += '<option value="">' + t('velg_kunde') + '</option>';
  customers.forEach(function(c) {
    html += '<option value="' + esc(c.id) + '">' + esc(c.name) + '</option>';
  });
  html += '</select>';
  html += '<div style="display:flex;gap:8px;">';
  html += '<button class="btn btn-primary" data-write onclick="uniwebDoMatch(\'' + esc(accountId) + '\')">' + t('koble') + '</button>';
  html += '<button class="btn btn-ghost" onclick="document.getElementById(\'uniweb-match-modal\').remove()">' + t('avbryt_2') + '</button>';
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
  var d = await apiFetch('/api/uniweb/account/' + accountId);
  if (!d) return;

  var html = '<div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;" id="uniweb-detail-modal" onclick="if(event.target===this)this.remove()">';
  html += '<div class="card" style="width:700px;max-height:80vh;padding:20px;overflow-y:auto;" onclick="event.stopPropagation()">';
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">';
  html += '<div style="font-weight:600;font-size:16px;">' + esc(d.name) + '</div>';
  html += '<button class="btn btn-ghost" onclick="document.getElementById(\'uniweb-detail-modal\').remove()" style="padding:4px 8px;">X</button>';
  html += '</div>';

  if (d.customer_name) {
    html += '<div style="margin-bottom:12px;font-size:12px;color:var(--green);">' + t('integ_linked_to','Koblet til') + ': ' + esc(d.customer_name) + '</div>';
  }

  // Domains
  if (d.domains && d.domains.length > 0) {
    html += '<div style="font-weight:600;font-size:13px;margin:12px 0 6px;">Domener (' + d.domains.length + ')</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:12px;">';
    html += '<thead><tr style="background:var(--bg-tertiary);"><th style="text-align:left;padding:4px 6px;">' + t('domene_3') + '</th><th style="text-align:center;padding:4px 6px;">' + t('utloper') + '</th><th style="text-align:center;padding:4px 6px;">' + t('status_2') + '</th></tr></thead><tbody>';
    d.domains.forEach(function(dom) {
      html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px 6px;">' + esc(dom.domain) + '</td><td style="text-align:center;padding:4px 6px;">' + esc(dom.expiry || '-') + '</td><td style="text-align:center;padding:4px 6px;">' + esc(dom.status || '-') + '</td></tr>';
    });
    html += '</tbody></table>';
  }

  // Subscriptions
  if (d.subscriptions && d.subscriptions.length > 0) {
    html += '<div style="font-weight:600;font-size:13px;margin:12px 0 6px;">Abonnementer (' + d.subscriptions.length + ')</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:12px;">';
    html += '<thead><tr style="background:var(--bg-tertiary);"><th style="text-align:left;padding:4px 6px;">' + t('tjeneste_2') + '</th><th style="text-align:left;padding:4px 6px;">' + t('bruker_domene_2') + '</th><th style="text-align:right;padding:4px 6px;">' + t('pris_mnd_2') + '</th><th style="text-align:center;padding:4px 6px;">' + t('fornyelse_2') + '</th></tr></thead><tbody>';
    d.subscriptions.forEach(function(sub) {
      html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px 6px;">' + esc(sub.service_type || '-') + '</td><td style="padding:4px 6px;">' + esc(sub.username_domain || '-') + '</td><td style="text-align:right;padding:4px 6px;font-family:var(--mono);">' + esc(sub.price_monthly || '-') + '</td><td style="text-align:center;padding:4px 6px;">' + esc(sub.renewal_date || '-') + '</td></tr>';
    });
    html += '</tbody></table>';
  }

  // SSL
  if (d.ssl && d.ssl.length > 0) {
    html += '<div style="font-weight:600;font-size:13px;margin:12px 0 6px;">SSL-sertifikater (' + d.ssl.length + ')</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:12px;">';
    html += '<thead><tr style="background:var(--bg-tertiary);"><th style="text-align:left;padding:4px 6px;">' + t('domene_3') + '</th><th style="text-align:left;padding:4px 6px;">' + t('type_2') + '</th><th style="text-align:center;padding:4px 6px;">' + t('utloper') + '</th></tr></thead><tbody>';
    d.ssl.forEach(function(cert) {
      html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px 6px;">' + esc(cert.domain) + '</td><td style="padding:4px 6px;">' + esc(cert.type || '-') + '</td><td style="text-align:center;padding:4px 6px;">' + esc(cert.expiry || '-') + '</td></tr>';
    });
    html += '</tbody></table>';
  }

  // Email
  if (d.email && d.email.length > 0) {
    html += '<div style="font-weight:600;font-size:13px;margin:12px 0 6px;">E-postkontoer (' + d.email.length + ')</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:12px;">';
    html += '<thead><tr style="background:var(--bg-tertiary);"><th style="text-align:left;padding:4px 6px;">' + t('adresse_2') + '</th><th style="text-align:center;padding:4px 6px;">' + t('kvote_2') + '</th><th style="text-align:center;padding:4px 6px;">' + t('brukt') + '</th></tr></thead><tbody>';
    d.email.forEach(function(em) {
      html += '<tr style="border-bottom:1px solid var(--border);"><td style="padding:4px 6px;">' + esc(em.address) + '</td><td style="text-align:center;padding:4px 6px;">' + esc(em.quota || '-') + '</td><td style="text-align:center;padding:4px 6px;">' + esc(em.used || '-') + '</td></tr>';
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

  var html = '<div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;padding:16px;" id="uniweb-import-modal" onclick="if(event.target===this)uniwebCloseImport()">';
  html += '<div class="card" style="width:650px;max-width:100%;max-height:80vh;padding:20px;display:flex;flex-direction:column;" onclick="event.stopPropagation()">';

  // Header with title and selection counter
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">';
  html += '<div style="font-weight:600;font-size:16px;">' + t('importer_kunder_fra_uniweb') + '</div>';
  html += '<button class="btn btn-ghost" onclick="uniwebCloseImport()" style="padding:4px 8px;font-size:14px;">X</button>';
  html += '</div>';
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">';
  html += '<div style="font-size:12px;color:var(--text-muted);">' + unmatched.length + ' ' + t('integ_unmatched_hint','Uniweb-kontoer som ikke er koblet til en MSP-kunde. Valgte kontoer opprettes som nye kunder.') + '</div>';
  html += '</div>';
  html += '<div id="uniweb-import-counter" style="font-size:12px;font-weight:500;color:var(--text-muted);margin-bottom:10px;">0 ' + t('integ_of','av') + ' ' + unmatched.length + ' ' + t('integ_selected','valgt') + '</div>';

  // Search + select all
  html += '<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">';
  html += '<input type="text" id="uniweb-import-search" class="field-input" placeholder="' + t('integ_search','Søk ...') + '" style="flex:1;min-width:150px;padding:6px 12px;font-size:12px;" oninput="uniwebFilterImport()">';
  html += '<label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer;white-space:nowrap;"><input type="checkbox" id="uniweb-import-select-all" onchange="uniwebToggleAllImport(this.checked)"> ' + t('velg_alle') + '</label>';
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
    html += '<td style="text-align:center;padding:6px;"><input type="checkbox" class="uniweb-import-cb" data-id="' + esc(u.uniweb_id) + '" data-account-name="' + esc(u.uniweb_name) + '" onchange="uniwebUpdateImportBtn()" style="width:15px;height:15px;cursor:pointer;"></td>';
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
  html += '<button class="btn btn-ghost" onclick="uniwebCloseImport()">' + t('avbryt_2') + '</button>';
  html += '<button class="btn btn-primary" id="uniweb-import-btn" disabled data-write onclick="uniwebDoImport()">' + t('importer_valgte') + '</button>';
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
    btn.textContent = checked > 0 ? 'Importer valgte (' + checked + ')' : 'Importer valgte';
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
    var schedHtml = esc(task.schedule);

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
    html += '<input type="checkbox" ' + toggleChecked + ' onchange="taskSchedToggle(\'' + esc(task.id) + '\',this.checked)" style="opacity:0;width:0;height:0;">';
    html += '<span style="position:absolute;top:0;left:0;right:0;bottom:0;background:' + (task.enabled ? 'var(--green)' : 'var(--border)') + ';border-radius:10px;transition:background .2s;"></span>';
    html += '<span style="position:absolute;top:2px;left:' + (task.enabled ? '18px' : '2px') + ';width:16px;height:16px;background:#fff;border-radius:50%;transition:left .2s;"></span>';
    html += '</label>';
    html += '</td>';
    html += '<td style="text-align:center;padding:10px 12px;">';
    html += '<button class="btn btn-ghost" data-write onclick="taskSchedRunNow(\'' + esc(task.id) + '\',this)" style="padding:4px 10px;font-size:11px;white-space:nowrap;">' + t('btn_run_now','Kjor na') + '</button>';
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
    var d = await apiFetch('/api/scheduler/tasks/' + taskId + '/run', {method: 'POST'});
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

// Load task scheduler on integrations view
(function() {
  var origSwitchIntegTab = window.switchIntegTab;
  if (!window._taskSchedInitDone) {
    window._taskSchedInitDone = true;
    // Auto-load when integrations view is shown
    var origShowView2 = showView;
    showView = function(name) {
      origShowView2(name);
      if (name === 'integrations') {
        taskSchedRefresh();
      }
    };
  }
})();

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
    html += '<span>' + t('lbl_found','Funnet') + ': <strong>' + d.total_found + '</strong></span>';
    html += '<span>' + t('lbl_new_alerts','Nye') + ': <strong style="color:' + (d.new_alerts > 0 ? 'var(--red)' : 'var(--green)') + ';">' + d.new_alerts + '</strong></span>';
    html += '<span>' + t('lbl_deduplicated','Deduplisert') + ': ' + d.deduplicated + '</span>';
    html += '<span>' + t('lbl_channels_notified','Kanaler varslet') + ': ' + d.channels_notified + '</span>';
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
    document.getElementById('uniweb-integ-dot').style.background = 'var(--green)';
    document.getElementById('uniweb-integ-label').textContent = t('integ_configured','Konfigurert');
    document.getElementById('uniweb-integ-label').style.color = 'var(--green)';
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

// Inject "Push to IT Glue" button into customer detail header when it renders
(function() {
  var detailBox = document.getElementById('customer-detail-content');
  if (!detailBox) return;
  var observer = new MutationObserver(function() {
    // Look for the action button row in the customer detail header
    var header = detailBox.querySelector('div[style*="justify-content:space-between"]');
    if (!header) return;
    // Avoid duplicate injection
    if (header.querySelector('[data-itglue-push]')) return;
    // Find the customer ID from the audit button's onclick
    var auditBtn = header.querySelector('button[onclick*="quickSwitchAndAudit"]');
    if (!auditBtn) return;
    var match = auditBtn.getAttribute('onclick').match(/quickSwitchAndAudit\('([^']+)'\)/);
    if (!match) return;
    var customerId = match[1];
    var pushBtn = document.createElement('button');
    pushBtn.className = 'btn btn-ghost';
    pushBtn.setAttribute('data-itglue-push', customerId);
    pushBtn.onclick = function() { itgluePushCustomer(customerId); };
    pushBtn.style.cssText = 'font-size:12px;';
    pushBtn.innerHTML = t('btn_push_to_itglue', 'Push til IT Glue');
    header.appendChild(pushBtn);
  });
  observer.observe(detailBox, {childList: true, subtree: true});
})();

async function itgluePushCustomer(customerId) {
  // Push documentation for a single customer to IT Glue
  var btn = document.querySelector('[data-itglue-push="' + customerId + '"]');
  if (btn) { btn.disabled = true; btn.textContent = t('msg_itglue_syncing', 'Synkroniserer...'); }

  try {
    var d = await apiFetch('/api/itglue/sync-documentation/' + encodeURIComponent(customerId), {method: 'POST'});
    if (!d) {
      showToast(t('status_error', 'Error'), 'error');
      return;
    }
    if (d.error) {
      showToast(d.error, 'error');
      return;
    }

    var synced = d.synced || [];
    var errors = d.errors || [];
    if (synced.length > 0) {
      var types = synced.map(function(s) { return s.type; }).join(', ');
      showToast(t('msg_itglue_sync_customer_ok', 'Dokumentasjon pushet til IT Glue') + ' (' + types + ')', 'success', 4000);
    }
    if (errors.length > 0) {
      showToast(t('msg_itglue_sync_customer_fail', 'Kunne ikke synkronisere til IT Glue') + ': ' + errors.length + ' ' + t('integ_errors_lc','feil'), 'warning', 4000);
    }
    if (synced.length === 0 && errors.length === 0) {
      showToast(t('msg_itglue_no_org_mapped', 'Ingen IT Glue-organisasjon koblet til denne kunden'), 'warning');
    }
  } catch (e) {
    showToast(t('msg_itglue_sync_customer_fail', 'Kunne ikke synkronisere') + ': ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = t('btn_push_to_itglue', 'Push til IT Glue'); }
  }
}
