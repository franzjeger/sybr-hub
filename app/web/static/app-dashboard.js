// ═══════════════════════════════════════════════════════════════════
// ALERTS DASHBOARD — MORNING OVERVIEW
// ═══════════════════════════════════════════════════════════════════

async function dashLoadAlerts() {
  var el = document.getElementById('dash-alerts-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';

  var data = await apiFetch('/api/dashboard/alerts');
  if (!data) { el.innerHTML = '<div style="color:var(--red);text-align:center;padding:48px;">Failed</div>'; return; }

  var html = '';

  // KPI
  html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:'Total Alerts', value:data.total_alerts, color:data.total_alerts>0?'var(--red)':'var(--green)'},
    {label:'Critical', value:data.categories.critical, color:data.categories.critical>0?'var(--red)':'var(--text-dim)'},
    {label:'Warning', value:data.categories.warning, color:data.categories.warning>0?'var(--orange)':'var(--text-dim)'},
    {label:'Info', value:data.categories.info, color:data.categories.info>0?'var(--blue)':'var(--text-dim)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card" style="padding:16px 8px;text-align:center;border-top:2px solid '+k.color+';height:90px;box-sizing:border-box;">';
    html += '<div style="font-size:22px;font-weight:700;line-height:24px;color:'+k.color+';">'+k.value+'</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);line-height:16px;">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  if (data.total_alerts === 0) {
    html += '<div class="card" style="padding:32px;text-align:center;color:var(--green);"><div style="font-size:32px;margin-bottom:8px;">✓</div><div style="font-size:14px;font-weight:600;">All clear!</div><div style="font-size:12px;color:var(--text-muted);">No expiring credentials or renewals within 30 days.</div></div>';
    el.innerHTML = html;
    return;
  }

  // Credential expiry section
  if (data.credential_expiry.length) {
    html += '<div class="card" style="padding:16px;margin-bottom:16px;">';
    html += '<div style="font-size:14px;font-weight:600;margin-bottom:10px;">'+icon('lock',16)+' Credential Expiry ('+data.credential_expiry.length+')</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
    html += '<thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:6px;">Customer</th><th style="text-align:center;padding:6px;">Type</th><th style="text-align:center;padding:6px;">Expires</th><th style="text-align:center;padding:6px;">Days</th><th style="text-align:center;padding:6px;">Severity</th></tr></thead><tbody>';
    data.credential_expiry.forEach(function(i) {
      var catColor = i.category === 'critical' ? 'var(--red)' : i.category === 'warning' ? 'var(--orange)' : 'var(--blue)';
      html += '<tr style="border-bottom:1px solid var(--border);cursor:pointer;" onclick="if(typeof showCustomerDetail===\'function\')showCustomerDetail(\''+esc(i.customer_id||'')+'\',\''+esc(i.customer_name)+'\')" title="'+t('tip_click_customer','Click to view customer')+'">';
      html += '<td style="padding:6px;font-weight:500;">'+esc(i.customer_name)+'</td>';
      html += '<td style="padding:6px;text-align:center;font-size:11px;">'+esc(i.type)+'</td>';
      html += '<td style="padding:6px;text-align:center;font-size:11px;">'+esc(i.expiry_date)+'</td>';
      html += '<td style="padding:6px;text-align:center;font-weight:700;color:'+catColor+';">'+(i.days_remaining<0?'EXPIRED':i.days_remaining+'d')+'</td>';
      html += '<td style="padding:6px;text-align:center;"><span style="font-size:10px;font-weight:600;color:#fff;background:'+catColor+';padding:2px 8px;border-radius:10px;">'+esc(i.category)+'</span></td>';
      html += '</tr>';
    });
    html += '</tbody></table></div>';
  }

  // Renewal alerts section
  if (data.renewals.length) {
    html += '<div class="card" style="padding:16px;margin-bottom:16px;">';
    html += '<div style="font-size:14px;font-weight:600;margin-bottom:10px;">'+icon('refresh',16)+' License Renewals ('+data.renewals.length+')</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
    html += '<thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:6px;">Customer</th><th style="text-align:left;padding:6px;">Subscription</th><th style="text-align:center;padding:6px;">Expires</th><th style="text-align:center;padding:6px;">Days</th><th style="text-align:center;padding:6px;">Severity</th></tr></thead><tbody>';
    data.renewals.forEach(function(i) {
      var catColor = i.category === 'critical' ? 'var(--red)' : i.category === 'warning' ? 'var(--orange)' : 'var(--blue)';
      html += '<tr style="border-bottom:1px solid var(--border);cursor:pointer;'+(i.handled?'opacity:0.4;':'')+'" onclick="if(typeof showCustomerDetail===\'function\')showCustomerDetail(\''+esc(i.customer_id||'')+'\',\''+esc(i.customer_name)+'\')" title="'+t('tip_click_customer','Click to view customer')+'">';
      html += '<td style="padding:6px;font-weight:500;">'+esc(i.customer_name)+'</td>';
      html += '<td style="padding:6px;">'+esc(i.service_name)+'</td>';
      html += '<td style="padding:6px;text-align:center;font-size:11px;">'+esc(i.contract_end)+'</td>';
      html += '<td style="padding:6px;text-align:center;font-weight:700;color:'+catColor+';">'+(i.days_remaining<0?'EXPIRED':i.days_remaining+'d')+'</td>';
      html += '<td style="padding:6px;text-align:center;"><span style="font-size:10px;font-weight:600;color:#fff;background:'+catColor+';padding:2px 8px;border-radius:10px;">'+esc(i.category)+'</span></td>';
      html += '</tr>';
    });
    html += '</tbody></table></div>';
  }

  // Uniweb hosting expiry placeholder — filled async
  html += '<div id="dash-uniweb-alerts"></div>';

  el.innerHTML = html;

  // Make alert tables sortable
  el.querySelectorAll('table').forEach(function(t) { makeSortable(t); });

  // Fetch Uniweb alerts async
  _dashLoadUniwebAlerts();
}

async function _dashLoadUniwebAlerts() {
  var container = document.getElementById('dash-uniweb-alerts');
  if (!container) return;

  try {
    var data = await apiFetch('/api/uniweb/alerts');
    if (!data || !data.items || data.items.length === 0) return;

    var html = '<div class="card" style="padding:16px;">';
    html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">';
    html += '<div style="font-size:14px;font-weight:600;">'+icon('globe',16)+' Hosting / Domener (Uniweb) ('+data.total+')</div>';
    html += '<div style="font-size:12px;">';
    if (data.critical > 0) html += '<span style="color:var(--red);font-weight:600;">'+data.critical+' kritisk</span> ';
    if (data.warning > 0) html += '<span style="color:var(--orange);font-weight:600;">'+data.warning+' advarsel</span>';
    html += '</div></div>';

    html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
    html += '<thead><tr style="border-bottom:1px solid var(--border);">';
    html += '<th style="text-align:left;padding:6px;">'+t('col_customer','Kunde')+'</th>';
    html += '<th style="text-align:left;padding:6px;">'+t('col_type','Type')+'</th>';
    html += '<th style="text-align:left;padding:6px;">'+t('col_element','Element')+'</th>';
    html += '<th style="text-align:center;padding:6px;">'+t('col_expires','Utløper')+'</th>';
    html += '<th style="text-align:center;padding:6px;">'+t('col_days','Dager')+'</th>';
    html += '<th style="text-align:center;padding:6px;">'+t('col_severity','Alvor')+'</th>';
    html += '</tr></thead><tbody>';

    var typeLabels = {domain: t('lbl_type_domain','Domene'), subscription: t('lbl_type_subscription','Abonnement'), ssl: t('lbl_type_ssl','SSL')};
    data.items.forEach(function(i) {
      var catColor = i.category === 'critical' ? 'var(--red)' : i.category === 'warning' ? 'var(--orange)' : '#c9a800';
      var catLabel = i.category === 'critical' ? 'Kritisk' : i.category === 'warning' ? 'Snart' : 'Kommende';
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += '<td style="padding:6px;font-weight:500;">'+esc(i.customer_name)+'</td>';
      html += '<td style="padding:6px;font-size:11px;">'+esc(typeLabels[i.type] || i.type)+'</td>';
      html += '<td style="padding:6px;">'+esc(i.item_name)+'</td>';
      html += '<td style="padding:6px;text-align:center;font-size:11px;">'+esc(i.expiry_date)+'</td>';
      html += '<td style="padding:6px;text-align:center;font-weight:700;color:'+catColor+';">'+(i.days_remaining<0?'UTLOPT':i.days_remaining+'d')+'</td>';
      html += '<td style="padding:6px;text-align:center;"><span style="font-size:10px;font-weight:600;color:#fff;background:'+catColor+';padding:2px 8px;border-radius:10px;">'+catLabel+'</span></td>';
      html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;
    var uniTable = container.querySelector('table');
    if (uniTable) makeSortable(uniTable);
  } catch (e) {
    // Silently ignore — Uniweb may not be configured
  }
}

// ═══════════════════════════════════════════════════════════════════
// CUSTOMER HEALTH SCORES
// ═══════════════════════════════════════════════════════════════════

async function dashLoadHealth() {
  var el = document.getElementById('dash-health-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';

  // Fetch security report and domain-email chain in parallel
  var results = await Promise.all([
    apiFetch('/api/dashboard/security-report'),
    apiFetch('/api/dashboard/domain-email-chain')
  ]);
  var secData = results[0];
  var chainData = results[1];

  if (!secData) { el.innerHTML = '<div style="color:var(--red);text-align:center;padding:48px;">Failed</div>'; return; }

  var customers = secData.customers || [];
  var summary = secData.summary || {};
  var html = '';

  // ── Security Report KPIs ──
  html += '<div style="font-size:15px;font-weight:700;margin-bottom:10px;">'+icon('shield',16)+' '+t('hdr_security_report','Security Report')+'</div>';
  html += '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:t('lbl_avg_score','Average'), value:(summary.avg_score||0)+'%', color:'var(--blue)'},
    {label:t('lbl_grade_a','Grade A'), value:summary.grade_a||0, color:'var(--green)'},
    {label:t('lbl_grade_b','Grade B'), value:summary.grade_b||0, color:'#6bcb77'},
    {label:t('lbl_grade_c','Grade C'), value:summary.grade_c||0, color:'var(--orange)'},
    {label:t('lbl_grade_d','Grade D'), value:summary.grade_d||0, color:'var(--red)'}
  ];
  kpis.forEach(function(k) {
    html += '<div class="card" style="padding:16px 8px;text-align:center;border-top:2px solid '+k.color+';height:90px;box-sizing:border-box;">';
    html += '<div style="font-size:22px;font-weight:700;line-height:24px;color:'+k.color+';">'+k.value+'</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);line-height:16px;">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // ── Security Report Table ──
  var chkY = '<span style="color:var(--green);font-weight:700;font-size:14px;">&#10003;</span>';
  var chkN = '<span style="color:var(--red);font-weight:700;font-size:14px;">&#10007;</span>';
  var chkDash = '<span style="color:var(--text-dim);">—</span>';

  html += '<div class="card" style="padding:0;overflow:hidden;margin-bottom:20px;">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="background:var(--bg-tertiary);border-bottom:2px solid var(--border);">';
  html += '<th style="text-align:left;padding:8px;">'+t('col_customer','Customer')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_mfa_pct','MFA%')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_spf','SPF')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_dkim','DKIM')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_dmarc','DMARC')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_firmware','Firmware')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_threats','Threats')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_grade','Grade')+'</th>';
  html += '</tr></thead><tbody>';

  customers.forEach(function(c, i) {
    var gradeColors = {A:'var(--green)',B:'#6bcb77',C:'var(--orange)',D:'var(--red)'};
    var gColor = gradeColors[c.security_grade] || 'var(--text-dim)';
    var rowBg = i % 2 === 0 ? 'transparent' : 'var(--bg-tertiary)';

    // MFA cell
    var mfaHtml = chkDash;
    if (c.mfa_pct !== null && c.mfa_pct !== undefined) {
      var mfaColor = c.mfa_pct >= 100 ? 'var(--green)' : c.mfa_pct >= 80 ? 'var(--orange)' : 'var(--red)';
      mfaHtml = '<span style="color:'+mfaColor+';font-weight:600;">'+c.mfa_pct+'%</span>';
    }

    // Firmware cell
    var fwHtml = chkDash;
    if (c.firmware === 'offline') {
      fwHtml = '<span style="color:var(--red);font-size:10px;">'+t('lbl_offline','Offline')+'</span>';
    } else if (c.firmware) {
      var fwColor = c.firmware_outdated ? 'var(--orange)' : 'var(--green)';
      var fwLabel = c.firmware_outdated ? t('lbl_fw_outdated','Outdated') : '';
      fwHtml = '<span style="color:'+fwColor+';font-size:10px;" title="'+esc(c.firmware)+'">'+esc(c.firmware)+(fwLabel?' ('+fwLabel+')':'')+'</span>';
    }

    // Threat cell
    var threatHtml = chkDash;
    if (c.threat_count !== null && c.threat_count !== undefined) {
      var thColor = c.threat_count > 0 ? 'var(--red)' : 'var(--green)';
      threatHtml = '<span style="color:'+thColor+';font-weight:600;">'+c.threat_count+'</span>';
    }

    html += '<tr style="background:'+rowBg+';border-bottom:1px solid var(--border);cursor:pointer;" onclick="if(typeof showCustomerDetail===\'function\')showCustomerDetail(\''+esc(c.customer_id||'')+'\',\''+esc(c.customer_name)+'\')" title="'+t('tip_click_customer','Click to view customer')+'">';
    html += '<td style="padding:6px 8px;font-weight:500;">'+esc(c.customer_name)+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;">'+mfaHtml+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;">'+(c.has_spf ? chkY : chkN)+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;">'+(c.has_dkim ? chkY : chkN)+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;">'+(c.has_dmarc ? chkY : chkN)+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;">'+fwHtml+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;">'+threatHtml+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;"><span style="display:inline-block;width:28px;height:28px;line-height:28px;border-radius:50%;background:'+gColor+';color:#fff;font-weight:700;font-size:13px;">'+c.security_grade+'</span></td>';
    html += '</tr>';
  });

  html += '</tbody></table></div>';

  // ── Domain-Email Chain Alerts ──
  html += _buildChainSection(chainData);

  el.innerHTML = html;

  // Make tables sortable
  el.querySelectorAll('table').forEach(function(tbl) { makeSortable(tbl); });

  // Wire up collapsible sections
  el.querySelectorAll('[data-collapse-toggle]').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var target = document.getElementById(btn.getAttribute('data-collapse-toggle'));
      if (target) {
        var hidden = target.style.display === 'none';
        target.style.display = hidden ? '' : 'none';
        btn.querySelector('.collapse-arrow').textContent = hidden ? '\u25BC' : '\u25B6';
      }
    });
  });
}

// ── VPN Status section builder ──

function _buildVpnSection(vpnData) {
  var html = '';
  html += '<div style="margin-bottom:20px;">';
  html += '<div data-collapse-toggle="vpn-section-body" style="cursor:pointer;display:flex;align-items:center;gap:8px;font-size:15px;font-weight:700;margin-bottom:10px;user-select:none;">';
  html += icon('link',16)+' '+t('hdr_vpn_status','VPN Status');

  if (vpnData && vpnData.total_tunnels > 0) {
    // Field backward-compat: prefer new customers_with_vpn; fall back to the
    // repurposed total_customers in case this UI runs against an older API.
    var vpnCustCount = (vpnData.customers_with_vpn !== undefined)
      ? vpnData.customers_with_vpn
      : vpnData.total_customers;
    html += ' <span style="font-size:12px;font-weight:400;color:var(--text-muted);">('+vpnData.total_tunnels+' '+t('lbl_total_tunnels','tunnels')+', '+vpnCustCount+' '+t('lbl_customers_with_vpn','customers with VPN')+')</span>';
  }
  html += ' <span class="collapse-arrow" style="font-size:11px;color:var(--text-muted);">&#9654;</span>';
  html += '</div>';

  html += '<div id="vpn-section-body" style="display:none;">';

  if (!vpnData || !vpnData.customers || vpnData.customers.length === 0) {
    html += '<div class="card" style="padding:16px;text-align:center;color:var(--text-muted);font-size:12px;">'+t('msg_no_vpn_data','No VPN data available.')+'</div>';
  } else {
    vpnData.customers.forEach(function(cust) {
      html += '<div class="card" style="padding:12px;margin-bottom:8px;">';
      html += '<div style="font-size:13px;font-weight:600;margin-bottom:6px;">'+esc(cust.customer_name);
      if (cust.status === 'error') {
        html += ' <span style="color:var(--red);font-size:11px;font-weight:400;">('+esc(cust.error || 'Error')+')</span>';
      }
      html += '</div>';

      if (cust.tunnels && cust.tunnels.length > 0) {
        html += '<table style="width:100%;border-collapse:collapse;font-size:11px;">';
        html += '<thead><tr style="border-bottom:1px solid var(--border);">';
        html += '<th style="text-align:left;padding:4px 6px;">'+t('col_tunnel_name','Tunnel')+'</th>';
        html += '<th style="text-align:center;padding:4px 6px;">'+t('col_type','Type')+'</th>';
        html += '<th style="text-align:center;padding:4px 6px;">'+t('col_status','Status')+'</th>';
        html += '<th style="text-align:right;padding:4px 6px;">'+t('col_bytes_in','In')+'</th>';
        html += '<th style="text-align:right;padding:4px 6px;">'+t('col_bytes_out','Out')+'</th>';
        html += '</tr></thead><tbody>';
        cust.tunnels.forEach(function(tun) {
          var sColor = tun.status === 'up' ? 'var(--green)' : 'var(--red)';
          var sLabel = tun.status === 'up' ? t('lbl_up','Up') : t('lbl_down','Down');
          html += '<tr style="border-bottom:1px solid var(--border);">';
          html += '<td style="padding:3px 6px;">'+esc(tun.name)+'</td>';
          html += '<td style="padding:3px 6px;text-align:center;"><span style="font-size:10px;background:var(--bg-tertiary);padding:1px 6px;border-radius:8px;">'+esc(tun.type)+'</span></td>';
          html += '<td style="padding:3px 6px;text-align:center;color:'+sColor+';font-weight:600;">'+sLabel+'</td>';
          html += '<td style="padding:3px 6px;text-align:right;color:var(--text-muted);">'+_fmtBytes(tun.bytes_in)+'</td>';
          html += '<td style="padding:3px 6px;text-align:right;color:var(--text-muted);">'+_fmtBytes(tun.bytes_out)+'</td>';
          html += '</tr>';
        });
        html += '</tbody></table>';
      } else if (cust.status !== 'error') {
        html += '<div style="font-size:11px;color:var(--text-muted);">'+t('lbl_no_data','No data')+'</div>';
      }
      html += '</div>';
    });
  }
  html += '</div></div>';
  return html;
}

// ── Domain-Email Chain section builder ──

function _buildChainSection(chainData) {
  var html = '';
  html += '<div style="margin-bottom:20px;">';
  html += '<div style="font-size:15px;font-weight:700;margin-bottom:10px;">'+icon('mail',16)+' '+t('hdr_domain_email_chain','Domain-Email-License')+'</div>';

  if (!chainData || !chainData.items || chainData.items.length === 0) {
    html += '<div class="card" style="padding:16px;text-align:center;color:var(--green);font-size:12px;">';
    html += '<div style="font-size:24px;margin-bottom:4px;">&#10003;</div>';
    html += t('msg_no_chain_alerts','No domain-email mismatches found.')+'</div>';
    html += '</div>';
    return html;
  }

  var s = chainData.summary || {};

  // KPI badges
  html += '<div style="display:flex;gap:12px;margin-bottom:10px;font-size:12px;">';
  if (s.double_paying > 0) html += '<span style="background:var(--orange);color:#fff;padding:3px 10px;border-radius:10px;font-weight:600;">'+s.double_paying+' '+t('lbl_double_paying','Double Paying')+'</span>';
  if (s.missing_m365 > 0) html += '<span style="background:var(--red);color:#fff;padding:3px 10px;border-radius:10px;font-weight:600;">'+s.missing_m365+' '+t('lbl_missing_m365','Missing M365')+'</span>';
  if (s.unused_m365 > 0) html += '<span style="background:var(--blue);color:#fff;padding:3px 10px;border-radius:10px;font-weight:600;">'+s.unused_m365+' '+t('lbl_unused_m365','Unused M365')+'</span>';
  html += '</div>';

  // Table
  html += '<div class="card" style="padding:0;overflow:hidden;">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="background:var(--bg-tertiary);border-bottom:2px solid var(--border);">';
  html += '<th style="text-align:left;padding:8px;">'+t('col_customer','Customer')+'</th>';
  html += '<th style="text-align:left;padding:8px;">'+t('col_domain','Domain')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_mx_exchange','MX Exchange')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_has_m365','M365')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_uniweb_email','Uniweb Email')+'</th>';
  html += '<th style="text-align:left;padding:8px;">'+t('col_alert','Alert')+'</th>';
  html += '</tr></thead><tbody>';

  var chkY = '<span style="color:var(--green);font-weight:700;font-size:14px;">&#10003;</span>';
  var chkN = '<span style="color:var(--red);font-weight:700;font-size:14px;">&#10007;</span>';

  chainData.items.forEach(function(item, i) {
    var rowBg = i % 2 === 0 ? 'transparent' : 'var(--bg-tertiary)';
    var alertHtml = '';
    item.alerts.forEach(function(a) {
      var sevColors = {critical:'var(--red)', warning:'var(--orange)', info:'var(--blue)'};
      var sevLabels = {critical:t('lbl_severity_critical','Critical'), warning:t('lbl_severity_warning','Warning'), info:t('lbl_severity_info','Info')};
      alertHtml += '<div style="margin-bottom:2px;"><span style="font-size:10px;font-weight:600;color:#fff;background:'+(sevColors[a.severity]||'var(--text-dim)')+';padding:1px 6px;border-radius:8px;">'+esc(sevLabels[a.severity]||a.severity)+'</span> <span style="font-size:11px;">'+esc(a.message)+'</span></div>';
    });

    html += '<tr style="background:'+rowBg+';border-bottom:1px solid var(--border);">';
    html += '<td style="padding:6px 8px;font-weight:500;">'+esc(item.customer_name)+'</td>';
    html += '<td style="padding:6px 8px;">'+esc(item.domain)+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;">'+(item.mx_exchange ? chkY : chkN)+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;">'+(item.has_m365 ? chkY : chkN)+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;">'+(item.has_uniweb_email ? chkY : chkN)+'</td>';
    html += '<td style="padding:6px 8px;">'+alertHtml+'</td>';
    html += '</tr>';
  });

  html += '</tbody></table></div>';
  html += '</div>';
  return html;
}

function _fmtBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
  return (bytes / 1073741824).toFixed(2) + ' GB';
}

// ═══════════════════════════════════════════════════════════════════
// UNIFIED COST OVERVIEW — ALSO MRR + UNIWEB HOSTING
// ═══════════════════════════════════════════════════════════════════

async function dashLoadCosts() {
  var el = document.getElementById('dash-costs-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';

  var data = await apiFetch('/api/dashboard/costs');
  if (!data) { el.innerHTML = '<div style="color:var(--red);text-align:center;padding:48px;">Kunne ikke laste kostnadsdata</div>'; return; }

  var customers = data.customers || [];
  var totals = data.totals || {};

  if (customers.length === 0) {
    el.innerHTML = '<div class="card" style="padding:32px;text-align:center;color:var(--text-muted);"><div style="font-size:14px;font-weight:600;margin-bottom:4px;">Ingen kostnadsdata</div><div style="font-size:12px;">Synkroniser ALSO-fornyelser eller Uniweb-kontoer for a se kostnader her.</div></div>';
    return;
  }

  var html = '';

  // ── KPI row ──
  html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:'Total MRR',           value:_fmtNOK(totals.total_monthly),  color:'var(--blue)'},
    {label:'ALSO MRR',            value:_fmtNOK(totals.also_mrr),       color:'#7c5cfc'},
    {label:'Uniweb manedlig',     value:_fmtNOK(totals.uniweb_monthly), color:'#e67e22'},
    {label:'Antall kunder',       value:totals.customer_count,           color:'var(--text)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card" style="padding:16px 8px;text-align:center;border-top:2px solid '+k.color+';height:90px;box-sizing:border-box;">';
    html += '<div style="font-size:20px;font-weight:700;line-height:24px;color:'+k.color+';">'+k.value+'</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);line-height:16px;">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // ── Customer cost table ──
  html += '<div class="card" style="padding:0;overflow:hidden;">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="background:var(--bg-tertiary);border-bottom:2px solid var(--border);">';
  html += '<th style="text-align:left;padding:8px;">'+t('col_customer','Kunde')+'</th>';
  html += '<th style="text-align:right;padding:8px;">'+t('col_also_mrr','ALSO MRR')+'</th>';
  html += '<th style="text-align:right;padding:8px;">'+t('col_uniweb_cost','Uniweb')+'</th>';
  html += '<th style="text-align:right;padding:8px;">'+t('col_total_cost','Total')+'</th>';
  html += '<th style="text-align:center;padding:8px;width:180px;">'+t('col_distribution','Fordeling')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_subs','Abb.')+'</th>';
  html += '</tr></thead><tbody>';

  var maxTotal = customers.length ? customers[0].total_monthly : 1;

  customers.forEach(function(c, i) {
    var rowBg = i % 2 === 0 ? 'transparent' : 'var(--bg-tertiary)';
    var alsoPct = c.total_monthly > 0 ? (c.also_mrr / c.total_monthly * 100) : 0;
    var uniwebPct = c.total_monthly > 0 ? (c.uniweb_monthly / c.total_monthly * 100) : 0;
    var barWidth = maxTotal > 0 ? Math.max((c.total_monthly / maxTotal * 100), 2) : 0;

    html += '<tr style="background:'+rowBg+';border-bottom:1px solid var(--border);">';
    html += '<td style="padding:6px 8px;font-weight:500;">'+esc(c.customer_name)+'</td>';
    html += '<td style="padding:6px 8px;text-align:right;color:#7c5cfc;font-weight:600;">'+_fmtNOK(c.also_mrr)+'</td>';
    html += '<td style="padding:6px 8px;text-align:right;color:#e67e22;font-weight:600;">'+_fmtNOK(c.uniweb_monthly)+'</td>';
    html += '<td style="padding:6px 8px;text-align:right;font-weight:700;">'+_fmtNOK(c.total_monthly)+'</td>';

    // Stacked bar
    html += '<td style="padding:6px 8px;">';
    html += '<div style="display:flex;height:14px;border-radius:3px;overflow:hidden;background:var(--bg-tertiary);width:'+barWidth+'%;">';
    if (alsoPct > 0)   html += '<div style="width:'+alsoPct+'%;background:#7c5cfc;" title="ALSO '+Math.round(alsoPct)+'%"></div>';
    if (uniwebPct > 0) html += '<div style="width:'+uniwebPct+'%;background:#e67e22;" title="Uniweb '+Math.round(uniwebPct)+'%"></div>';
    html += '</div></td>';

    // Subscription counts
    html += '<td style="padding:6px 8px;text-align:center;font-size:11px;color:var(--text-muted);">';
    if (c.also_subscriptions) html += '<span style="color:#7c5cfc;" title="ALSO">'+c.also_subscriptions+'</span>';
    if (c.also_subscriptions && c.uniweb_subscriptions) html += ' / ';
    if (c.uniweb_subscriptions) html += '<span style="color:#e67e22;" title="Uniweb">'+c.uniweb_subscriptions+'</span>';
    if (!c.also_subscriptions && !c.uniweb_subscriptions) html += '-';
    html += '</td>';

    html += '</tr>';
  });

  // ── Total row ──
  html += '<tr style="background:var(--bg-tertiary);border-top:2px solid var(--border);font-weight:700;">';
  html += '<td style="padding:8px;">Totalt ('+totals.customer_count+' kunder)</td>';
  html += '<td style="padding:8px;text-align:right;color:#7c5cfc;">'+_fmtNOK(totals.also_mrr)+'</td>';
  html += '<td style="padding:8px;text-align:right;color:#e67e22;">'+_fmtNOK(totals.uniweb_monthly)+'</td>';
  html += '<td style="padding:8px;text-align:right;">'+_fmtNOK(totals.total_monthly)+'</td>';
  html += '<td style="padding:8px;"></td>';
  html += '<td style="padding:8px;"></td>';
  html += '</tr>';

  html += '</tbody></table></div>';

  // ── Legend ──
  html += '<div style="display:flex;gap:16px;margin-top:8px;font-size:11px;color:var(--text-muted);">';
  html += '<span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#7c5cfc;margin-right:4px;vertical-align:middle;"></span>ALSO Cloud</span>';
  html += '<span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#e67e22;margin-right:4px;vertical-align:middle;"></span>Uniweb Hosting</span>';
  html += '</div>';

  el.innerHTML = html;
}

function _fmtNOK(val) {
  if (val === null || val === undefined || val === 0) return '0 kr';
  return val.toLocaleString('nb-NO', {minimumFractionDigits: 0, maximumFractionDigits: 0}) + ' kr';
}

// ═══════════════════════════════════════════════════════════════════
// DOMAIN HEALTH DASHBOARD
// ═══════════════════════════════════════════════════════════════════

async function dashLoadDomains() {
  var el = document.getElementById('dash-domains-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>' +
    '<div style="text-align:center;color:var(--text-muted);font-size:12px;margin-top:8px;">Sjekker TLS-sertifikater for alle domener...</div>';

  var data = await apiFetch('/api/dashboard/domains');
  if (!data) {
    el.innerHTML = '<div style="color:var(--red);text-align:center;padding:48px;">Kunne ikke laste domenedata</div>';
    return;
  }

  var domains = data.domains || [];
  var s = data.summary || {};
  var html = '';

  // KPI cards
  html += '<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:'Totalt domener', value:s.total||0, color:'var(--blue)'},
    {label:'Friske', value:s.healthy||0, color:'var(--green)'},
    {label:'Advarsel', value:s.warning||0, color:s.warning>0?'var(--orange)':'var(--text-dim)'},
    {label:'Kritisk', value:s.critical||0, color:s.critical>0?'var(--red)':'var(--text-dim)'},
    {label:'Mangler SPF', value:s.missing_spf||0, color:s.missing_spf>0?'var(--orange)':'var(--text-dim)'},
    {label:'Mangler DMARC', value:s.missing_dmarc||0, color:s.missing_dmarc>0?'var(--orange)':'var(--text-dim)'}
  ];
  kpis.forEach(function(k) {
    html += '<div class="card" style="padding:16px 8px;text-align:center;border-top:2px solid ' + k.color + ';height:90px;box-sizing:border-box;">';
    html += '<div style="font-size:22px;font-weight:700;line-height:24px;color:' + k.color + ';">' + k.value + '</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);line-height:16px;">' + k.label + '</div>';
    html += '</div>';
  });
  html += '</div>';

  if (s.ssl_expiring_30d > 0) {
    html += '<div class="card" style="padding:10px 16px;margin-bottom:16px;border-left:3px solid var(--orange);background:rgba(255,165,0,0.05);font-size:12px;color:var(--orange);font-weight:600;">';
    html += s.ssl_expiring_30d + ' SSL-sertifikat utloper innen 30 dager';
    html += '</div>';
  }

  if (domains.length === 0) {
    html += '<div class="card" style="padding:32px;text-align:center;color:var(--text-muted);">';
    html += '<div style="font-size:14px;">Ingen domener funnet</div>';
    html += '<div style="font-size:12px;margin-top:4px;">Synkroniser Uniweb-data for a se domener her.</div>';
    html += '</div>';
    el.innerHTML = html;
    return;
  }

  // Domain table
  html += '<div class="card" style="padding:0;overflow:hidden;">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="background:var(--bg-tertiary);border-bottom:2px solid var(--border);">';
  html += '<th style="text-align:center;padding:8px;width:30px;">'+t('col_health','Helse')+'</th>';
  html += '<th style="text-align:left;padding:8px;">'+t('col_domain','Domene')+'</th>';
  html += '<th style="text-align:left;padding:8px;">'+t('col_customer','Kunde')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_ssl','SSL')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_spf','SPF')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_dkim','DKIM')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_dmarc','DMARC')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_dns','DNS')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_expires','Utløper')+'</th>';
  html += '</tr></thead><tbody>';

  domains.forEach(function(d, i) {
    var healthColors = {good:'var(--green)', warning:'var(--orange)', critical:'var(--red)', unknown:'var(--text-dim)'};
    var healthLabels = {good:'OK', warning:'!', critical:'X', unknown:'?'};
    var hColor = healthColors[d.health] || 'var(--text-dim)';
    var rowBg = i % 2 === 0 ? 'transparent' : 'var(--bg-tertiary)';

    // SSL cell
    var sslHtml = '';
    if (d.ssl && d.ssl.days_remaining !== null && d.ssl.days_remaining !== undefined) {
      var sslColor = 'var(--green)';
      if (d.ssl.days_remaining < 0) sslColor = 'var(--red)';
      else if (d.ssl.days_remaining < 30) sslColor = 'var(--orange)';
      var sslLabel = d.ssl.days_remaining < 0 ? 'Utlopt' : d.ssl.days_remaining + 'd';
      var gradeStr = d.ssl.grade ? ' ' + d.ssl.grade : '';
      sslHtml = '<span style="color:' + sslColor + ';font-weight:600;" title="' + esc(d.ssl.issuer || '') + ' — gyldig til ' + esc(d.ssl.valid_until || '') + '">' + sslLabel + gradeStr + '</span>';
    } else {
      sslHtml = '<span style="color:var(--text-dim);">—</span>';
    }

    // Check/X helper
    var chkY = '<span style="color:var(--green);font-weight:700;font-size:14px;">&#10003;</span>';
    var chkN = '<span style="color:var(--red);font-weight:700;font-size:14px;">&#10007;</span>';

    // Expiry cell
    var expiryHtml = '';
    if (d.days_until_expiry !== null && d.days_until_expiry !== undefined) {
      var expColor = 'var(--text)';
      if (d.days_until_expiry < 0) expColor = 'var(--red)';
      else if (d.days_until_expiry < 90) expColor = 'var(--orange)';
      expiryHtml = '<span style="color:' + expColor + ';" title="' + esc(d.expiry) + '">' + (d.days_until_expiry < 0 ? 'Utlopt' : d.days_until_expiry + 'd') + '</span>';
    } else {
      expiryHtml = '<span style="color:var(--text-dim);">—</span>';
    }

    html += '<tr style="background:' + rowBg + ';border-bottom:1px solid var(--border);">';
    html += '<td style="padding:6px 8px;text-align:center;"><span style="display:inline-block;width:22px;height:22px;line-height:22px;border-radius:50%;background:' + hColor + ';color:#fff;font-weight:700;font-size:11px;">' + healthLabels[d.health] + '</span></td>';
    html += '<td style="padding:6px 8px;font-weight:500;">' + esc(d.domain) + '</td>';
    html += '<td style="padding:6px 8px;">' + esc(d.customer_name) + '</td>';
    html += '<td style="padding:6px 8px;text-align:center;">' + sslHtml + '</td>';
    html += '<td style="padding:6px 8px;text-align:center;">' + (d.has_spf ? chkY : chkN) + '</td>';
    html += '<td style="padding:6px 8px;text-align:center;">' + (d.has_dkim ? chkY : chkN) + '</td>';
    html += '<td style="padding:6px 8px;text-align:center;">' + (d.has_dmarc ? chkY : chkN) + '</td>';
    html += '<td style="padding:6px 8px;text-align:center;color:var(--text-muted);">' + d.dns_records + '</td>';
    html += '<td style="padding:6px 8px;text-align:center;font-size:11px;">' + expiryHtml + '</td>';
    html += '</tr>';
  });

  html += '</tbody></table></div>';
  el.innerHTML = html;
}


// ═══════════════════════════════════════════════════════════════════
// DASHBOARD AUTO-REFRESH
// ═══════════════════════════════════════════════════════════════════

var _dashRefreshInterval = null;
var _dashRefreshSeconds = 120; // 2 minutes

function dashToggleAutoRefresh(btn) {
  if (_dashRefreshInterval) {
    clearInterval(_dashRefreshInterval);
    _dashRefreshInterval = null;
    if (btn) { btn.textContent = t('btn_auto_refresh_off','Auto-refresh: Off'); btn.style.opacity = '0.5'; }
    return;
  }
  _dashRefreshInterval = setInterval(function() {
    var active = document.querySelector('.dash-tab-btn.active');
    if (active) active.click();
  }, _dashRefreshSeconds * 1000);
  if (btn) { btn.textContent = t('btn_auto_refresh_on','Auto-refresh: 2m'); btn.style.opacity = '1'; }
}


// ═══════════════════════════════════════════════════════════════════
// CSV EXPORT FOR DASHBOARD TABLES
// ═══════════════════════════════════════════════════════════════════

function _dashExportTableCSV(containerId, filename) {
  var el = document.getElementById(containerId);
  if (!el) return;
  var table = el.querySelector('table');
  if (!table) { showToast(t('err_no_data','No data to export'), 'error'); return; }

  var rows = [];
  table.querySelectorAll('tr').forEach(function(tr) {
    var cells = [];
    tr.querySelectorAll('th, td').forEach(function(td) {
      var text = td.textContent.trim().replace(/"/g, '""');
      cells.push('"' + text + '"');
    });
    if (cells.length) rows.push(cells.join(';'));
  });

  var csv = '\uFEFF' + rows.join('\n'); // BOM for Excel
  var blob = new Blob([csv], {type: 'text/csv;charset=utf-8;'});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = (filename || 'export') + '_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
  URL.revokeObjectURL(url);
  showToast(t('msg_exported','Exported') + ' ' + a.download, 'success', 2000);
}

function dashExportAlerts() { _dashExportTableCSV('dash-alerts-content', 'alerts'); }
function dashExportHealth() { _dashExportTableCSV('dash-health-content', 'health_scores'); }
function dashExportCosts() { _dashExportTableCSV('dash-costs-content', 'costs'); }
function dashExportDomains() { _dashExportTableCSV('dash-domains-content', 'domains'); }

// Navigate to customer detail view from dashboard tables
function showCustomerDetail(customerId, customerName) {
  if (!customerId) return;
  if (typeof overviewSelectCustomer === 'function') {
    overviewSelectCustomer(customerId);
  }
}

function dashExportCurrentTab() {
  var active = document.querySelector('.dash-tab-content[style*="display: block"], .dash-tab-content[style*="display:block"]');
  if (!active) return;
  var id = active.id;
  if (id === 'dash-alerts') dashExportAlerts();
  else if (id === 'dash-health') dashExportHealth();
  else if (id === 'dash-costs') dashExportCosts();
  else if (id === 'dash-domains') dashExportDomains();
  else if (id === 'dash-renewals') _dashExportTableCSV('dash-renewals-content', 'renewals');
  else if (id === 'dash-customers') _dashExportTableCSV('overview-content', 'customers');
  else if (id === 'dash-archive') showToast(t('err_no_export','Export not available for this tab'), 'info');
  else showToast(t('err_no_export','Export not available for this tab'), 'info');
}


// ═══════════════════════════════════════════════════════════════════
// REPORT ARCHIVE
// ═══════════════════════════════════════════════════════════════════

async function dashLoadArchive() {
  var el = document.getElementById('dash-archive-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>';

  var data = await apiFetch('/api/reports/archive');
  if (!data) { el.innerHTML = '<div style="color:var(--red);text-align:center;padding:48px;">Failed</div>'; return; }

  var html = '';

  // KPI
  html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:t('lbl_total_reports','Rapporter'), value:data.total_reports, color:'var(--blue)'},
    {label:t('lbl_customers','Kunder'), value:data.customers.length, color:'var(--text)'},
    {label:t('lbl_total_size','Størrelse'), value:data.total_size_mb + ' MB', color:'var(--text-muted)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card" style="padding:16px 8px;text-align:center;border-top:2px solid '+k.color+';height:90px;box-sizing:border-box;">';
    html += '<div style="font-size:22px;font-weight:700;line-height:24px;color:'+k.color+';">'+k.value+'</div>';
    html += '<div style="font-size:11px;color:var(--text-muted);line-height:16px;">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // Cleanup button
  html += '<div style="display:flex;gap:8px;margin-bottom:16px;">';
  html += '<button class="btn btn-ghost" onclick="dashArchiveCleanup(3)" style="font-size:12px;">'+t('btn_cleanup_3m','Delete older than 3 months')+'</button>';
  html += '<button class="btn btn-ghost" onclick="dashArchiveCleanup(6)" style="font-size:12px;">'+t('btn_cleanup_6m','Delete older than 6 months')+'</button>';
  html += '<button class="btn btn-ghost" onclick="dashArchiveCleanup(12)" style="font-size:12px;">'+t('btn_cleanup_12m','Delete older than 12 months')+'</button>';
  html += '</div>';

  if (data.customers.length === 0) {
    html += '<div class="card" style="padding:32px;text-align:center;color:var(--text-muted);">'+t('msg_no_reports','No reports found.')+'</div>';
    el.innerHTML = html;
    return;
  }

  // Customer list with collapsible runs
  data.customers.forEach(function(c, idx) {
    html += '<div class="card" style="padding:0;margin-bottom:8px;">';
    html += '<div onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\';this.querySelector(\'.chevron\').classList.toggle(\'open\')" style="padding:12px 16px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;">';
    html += '<div><span style="font-weight:600;">'+esc(c.customer_name)+'</span> <span style="font-size:12px;color:var(--text-muted);">('+c.run_count+' '+t('lbl_reports','reports')+', '+c.total_size_mb+' MB)</span></div>';
    html += '<span class="chevron" style="font-size:10px;color:var(--text-dim);transition:transform 0.2s;">&#9660;</span>';
    html += '</div>';
    html += '<div style="display:none;border-top:1px solid var(--border);">';
    html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
    html += '<thead><tr style="border-bottom:1px solid var(--border);"><th style="text-align:left;padding:6px 16px;">'+t('lbl_date','Date')+'</th><th style="text-align:center;padding:6px;">'+t('lbl_files','Files')+'</th><th style="text-align:center;padding:6px;">'+t('lbl_size','Size')+'</th><th style="text-align:center;padding:6px;">PDF</th><th style="text-align:center;padding:6px;">HTML</th><th style="text-align:right;padding:6px 16px;"></th></tr></thead><tbody>';
    c.runs.forEach(function(r) {
      html += '<tr style="border-bottom:1px solid var(--border);">';
      html += '<td style="padding:6px 16px;">'+esc(r.date || r.name)+'</td>';
      html += '<td style="padding:6px;text-align:center;">'+r.file_count+'</td>';
      html += '<td style="padding:6px;text-align:center;">'+r.size_mb+' MB</td>';
      html += '<td style="padding:6px;text-align:center;">'+(r.has_pdf ? '<span style="color:var(--green);">&#10003;</span>' : '<span style="color:var(--text-dim);">-</span>')+'</td>';
      html += '<td style="padding:6px;text-align:center;">'+(r.has_html ? '<span style="color:var(--green);">&#10003;</span>' : '<span style="color:var(--text-dim);">-</span>')+'</td>';
      html += '<td style="padding:6px 16px;text-align:right;"><button class="btn btn-ghost" onclick="dashArchiveDelete(\''+esc(r.path)+'\')" style="font-size:11px;color:var(--red);padding:2px 8px;">'+t('btn_delete','Delete')+'</button></td>';
      html += '</tr>';
    });
    html += '</tbody></table></div></div>';
  });

  el.innerHTML = html;
}

async function dashArchiveDelete(path) {
  if (!confirm(t('confirm_delete_report','Delete this report permanently?'))) return;
  var d = await apiFetch('/api/reports/archive/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({path:path})});
  if (d && d.ok) {
    showToast(t('msg_deleted','Deleted'), 'success', 2000);
    dashLoadArchive();
  } else {
    showToast((d && d.error) || t('status_error'), 'error');
  }
}

async function generateQBR() {
  showToast(t('msg_generating','Generating...'), 'info', 2000);
  try {
    var r = await apiFetch('/api/reports/batch-summary', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({})});
    if (!r) { showToast(t('status_error'), 'error'); return; }
    if (r.error) { showToast(r.error, 'error'); return; }
    var html = r._raw || '';
    if (!html) { showToast(t('err_no_data','No data'), 'error'); return; }
    var blob = new Blob([html], {type:'text/html'});
    var url = URL.createObjectURL(blob);
    window.open(url, '_blank');
    showToast(t('msg_qbr_generated','QBR report opened — use Ctrl+P to save as PDF'), 'success', 5000);
  } catch(e) { showToast(t('status_error') + ': ' + e.message, 'error'); }
}

async function dashArchiveCleanup(months) {
  if (!confirm(t('confirm_cleanup_reports','Delete all reports older than') + ' ' + months + ' ' + t('lbl_months','months') + '?')) return;
  var d = await apiFetch('/api/reports/archive/cleanup', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({months:months})});
  if (d && d.ok) {
    showToast(d.deleted + ' ' + t('msg_reports_deleted','reports deleted') + ' (' + d.freed_mb + ' MB)', 'success', 3000);
    dashLoadArchive();
  } else {
    showToast((d && d.error) || t('status_error'), 'error');
  }
}

