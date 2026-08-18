// ═══════════════════════════════════════════════════════════════════
// ALSO RENEWAL ACTION LIST
// ═══════════════════════════════════════════════════════════════════

// Store last renewals data for export/filter
var _lastRenewals = [];
var _renewalIntervalFilter = null; // null = no filter

function _renewalFilterFn(r) {
  var f = _renewalIntervalFilter;
  if (!f) return true;
  var d = r.days_left;
  if (d === null || d === undefined) return false;
  if (f === 'expired') return d < 0;
  if (f === '30')  return d >= 0 && d <= 30;
  if (f === '60')  return d > 30 && d <= 60;
  if (f === '365') return d > 60 && d <= 365;
  if (f === '1yr') return d > 365;
  return true;
}

function _setRenewalFilter(key) {
  if (_renewalIntervalFilter === key) {
    _renewalIntervalFilter = null;
  } else {
    _renewalIntervalFilter = key;
  }
  dashLoadRenewals();
}

async function dashLoadRenewals() {
  var el = document.getElementById('dash-renewals-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div><div style="text-align:center;color:var(--text-muted);font-size:12px;">' + t('also_loading_renewals','Laster fornyelser ...') + '</div>';

  var data = await apiFetch('/api/also/renewals?days=365');
  if (!data) {
    el.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:24px;font-size:12px;">' + t('also_unavailable','ALSO Cloud ikke tilgjengelig') + '</div>'
      + '<div id="dash-uniweb-renewals" style="margin-top:16px;"><div class="loader" style="width:16px;height:16px;margin:16px auto;"></div></div>';
    _loadUniwebRenewals();
    return;
  }

  var renewals = data.renewals || [];
  _lastRenewals = renewals;

  // Apply interval filter FIRST
  if (_renewalIntervalFilter) {
    renewals = renewals.filter(_renewalFilterFn);
  }

  // Apply vendor filter
  var vendorFilter = document.getElementById('renewal-filter-vendor');
  var vf = vendorFilter ? vendorFilter.value : '';
  if (vf) renewals = renewals.filter(function(r) { return r.vendor === vf; });

  // ── KPI row ──
  var mrrText = data.total_mrr > 0 ? data.total_mrr.toFixed(0) + ' ' + (data.currency || '') : '-';
  var af = _renewalIntervalFilter;
  var html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:t('kpi_cached','Cached'),     value:data.all_cached,  color:'var(--blue)',   filterKey:null},
    {label:t('kpi_expired','Expired'),   value:data.expired,     color:data.expired>0?'var(--red)':'var(--text-dim)',     filterKey:'expired'},
    {label:t('kpi_30d','< 30 days'),     value:data.urgent_30d,  color:data.urgent_30d>0?'var(--red)':'var(--text-dim)',  filterKey:'30'},
    {label:t('kpi_30_60d','30–60 days'), value:data.soon_60d, color:data.soon_60d>0?'var(--orange)':'var(--text-dim)',filterKey:'60'},
    {label:t('kpi_60_365d','60–365 days'), value:data.upcoming, color:data.upcoming>0?'var(--orange)':'var(--text-dim)',filterKey:'365'},
    {label:t('kpi_1yr','> 1 year'),      value:data.beyond||0,   color:'var(--green)',  filterKey:'1yr'},
    {label:t('kpi_mrr_cached','MRR (cached)'), value:mrrText,    color:data.total_mrr>0?'var(--green)':'var(--text-dim)', filterKey:null, noClick:true},
    {label:t('kpi_priced','Priced'),     value:data.priced_count+'/'+data.all_cached, color:data.priced_count>0?'var(--blue)':'var(--text-dim)', filterKey:null, noClick:true},
  ];
  kpis.forEach(function(k) {
    var isActive = (k.filterKey !== null && af === k.filterKey) || (k.filterKey === null && af === null && !k.noClick);
    var clickable = !k.noClick;
    var borderWidth = isActive && k.filterKey !== null ? '4px' : (af === null && k.filterKey === null && !k.noClick) ? '4px' : '2px';
    // "Bufret" card is highlighted when no filter active (it means "all")
    if (k.filterKey === null && !k.noClick) {
      isActive = (af === null);
      borderWidth = isActive ? '4px' : '2px';
    }
    var brightness = isActive ? 'filter:brightness(1.2);' : '';
    var cursor = clickable ? 'cursor:pointer;' : '';
    var onclick = '';
    if (clickable) {
      if (k.filterKey === null) {
        onclick = ' onclick="_renewalIntervalFilter=null;dashLoadRenewals();"';
      } else {
        onclick = ' onclick="_setRenewalFilter(\''+k.filterKey+'\')"';
      }
    }
    html += '<div class="card" style="padding:12px 8px;text-align:center;border-top:'+borderWidth+' solid '+k.color+';height:80px;box-sizing:border-box;'+cursor+brightness+'"'+onclick+'>';
    html += '<div style="font-size:18px;font-weight:700;line-height:22px;color:'+k.color+';">'+k.value+'</div>';
    html += '<div style="font-size:10px;color:var(--text-muted);line-height:14px;">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // ── Action bar ──
  html += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap;">';
  html += '<button class="btn btn-ghost" onclick="dashLoadRenewals()" style="padding:4px 12px;font-size:11px;">'+t('btn_refresh','Refresh')+'</button>';
  html += '<button class="btn btn-primary" data-write onclick="alsoCombinedSync()" id="renewal-scan-btn" style="padding:4px 12px;font-size:11px;">'+t('btn_sync','Sync')+'</button>';
  html += '<button class="btn btn-ghost" data-write onclick="alsoBulkHandled()" style="padding:4px 12px;font-size:11px;">'+t('btn_mark_handled','Mark selected handled')+'</button>';
  html += '<button class="btn btn-ghost" onclick="alsoExportCSV()" style="padding:4px 12px;font-size:11px;">'+t('btn_export_csv','Export CSV')+'</button>';
  html += '<button class="btn btn-ghost" onclick="alsoDownloadPDF()" style="padding:4px 12px;font-size:11px;">'+icon('document',13)+' '+t('btn_pdf_report','PDF Report')+'</button>';
  html += '<button class="btn btn-ghost" onclick="alsoShowLicenseOptimization()" style="padding:4px 12px;font-size:11px;">'+t('btn_license_opt','Lisensoptimalisering')+'</button>';
  html += '<select id="renewal-filter-vendor" onchange="dashLoadRenewals()" style="padding:3px 8px;font-size:11px;background:var(--bg-input);border:1px solid var(--border);border-radius:4px;color:var(--text);"><option value="">'+t('lbl_all_vendors','All vendors')+'</option></select>';
  // Show "Vis alle" link when interval filter is active
  if (_renewalIntervalFilter) {
    html += '<a href="#" onclick="_renewalIntervalFilter=null;dashLoadRenewals();return false;" style="font-size:11px;color:var(--blue);text-decoration:underline;cursor:pointer;">'+t('lbl_show_all','Show all')+'</a>';
  }
  html += '<span id="renewal-scan-msg" style="font-size:11px;color:var(--text-muted);"></span>';
  html += '<span id="also-api-stats" style="font-size:10px;color:var(--text-dim);margin-left:auto;font-family:var(--mono);"></span>';
  html += '</div>';

  if (!renewals.length) {
    html += '<div class="card" style="padding:32px;text-align:center;color:var(--text-muted);">';
    html += '<div style="font-size:32px;margin-bottom:8px;">'+icon('document',32)+'</div>';
    if (_lastRenewals.length === 0) {
      html += '<div style="font-size:14px;font-weight:600;margin-bottom:4px;">'+t('msg_no_renewal_data','No renewal data cached yet')+'</div>';
      html += '<div style="font-size:12px;">'+t('msg_no_renewal_data_hint','View licenses on a customer, or click "Sync" to build the cache.')+'</div>';
    } else {
      html += '<div style="font-size:14px;font-weight:600;margin-bottom:4px;">'+t('msg_no_renewals_filter','No renewals in this filter')+'</div>';
      html += '<div style="font-size:12px;"><a href="#" onclick="_renewalIntervalFilter=null;dashLoadRenewals();return false;" style="color:var(--blue);">'+t('lbl_show_all','Show all')+'</a></div>';
    }
    html += '</div>';
    // Still show Uniweb renewals even when ALSO has no data
    html += '<div id="dash-uniweb-renewals" style="margin-top:16px;"><div class="loader" style="width:16px;height:16px;margin:16px auto;"></div></div>';
    el.innerHTML = html;
    _loadUniwebRenewals();
    return;
  }

  // ── Table ──
  html += '<div class="card" style="padding:0;overflow-x:auto;">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="background:var(--bg-tertiary);border-bottom:2px solid var(--border);">';
  html += '<th style="text-align:center;padding:8px;width:40px;"><input type="checkbox" onchange="alsoToggleAll(this.checked)" title="'+t('tip_select_all','Select all')+'"></th>';
  html += '<th style="text-align:left;padding:8px;">'+t('col_customer','Customer')+'</th>';
  html += '<th style="text-align:left;padding:8px;">'+t('col_product','Product')+'</th>';
  html += '<th style="text-align:left;padding:8px;">'+t('col_vendor','Vendor')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_term','Term')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_qty','Qty')+'</th>';
  html += '<th style="text-align:right;padding:8px;">'+t('col_price','Price')+'</th>';
  html += '<th style="text-align:right;padding:8px;">'+t('col_monthly','Monthly')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_renews','Renews')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_days','Days')+'</th>';
  html += '<th style="text-align:center;padding:8px;">'+t('col_status','Status')+'</th>';
  html += '<th style="text-align:left;padding:8px;">'+t('col_notes','Notes')+'</th>';
  html += '</tr></thead><tbody>';

  var lastCustomer = '';
  var customerMrr = 0;

  renewals.forEach(function(r, i) {
    var daysLeft = r.days_left;
    var daysColor = daysLeft === null ? 'var(--text-dim)' : daysLeft < 0 ? 'var(--red)' : daysLeft <= 30 ? 'var(--red)' : daysLeft <= 60 ? 'var(--orange)' : 'var(--green)';
    var daysLabel = daysLeft === null ? '-' : daysLeft < 0 ? 'UTL\u00d8PT' : daysLeft + 'd';
    var rowBg = r.handled ? 'rgba(0,200,0,0.04)' : i % 2 === 0 ? 'transparent' : 'var(--bg-tertiary)';
    var renewDate = r.contract_end ? r.contract_end.slice(0,10) : '-';

    // Customer subtotal separator
    if (r.customer_name !== lastCustomer && lastCustomer !== '' && customerMrr > 0) {
      html += '<tr style="background:var(--bg);border-bottom:2px solid var(--border);"><td colspan="7" style="padding:4px 8px;text-align:right;font-size:11px;font-weight:600;color:var(--text-muted);">'+esc(lastCustomer)+' MRR:</td><td style="padding:4px 8px;text-align:right;font-weight:700;font-family:var(--mono);font-size:11px;">'+customerMrr.toFixed(2)+'</td><td colspan="4"></td></tr>';
      customerMrr = 0;
    }
    lastCustomer = r.customer_name;
    customerMrr += (r.monthly_cost || 0);

    html += '<tr style="background:'+rowBg+';border-bottom:1px solid var(--border);'+(r.handled?'opacity:0.6;':'')+'">';
    html += '<td style="padding:6px 8px;text-align:center;"><input type="checkbox" class="renewal-cb" data-id="'+r.id+'" '+(r.handled?'checked':'')+' onchange="alsoToggleHandled('+r.id+',this.checked)" style="cursor:pointer;"></td>';
    html += '<td style="padding:6px 8px;font-weight:500;">'+esc(r.customer_name)+'</td>';
    html += '<td style="padding:6px 8px;">'+esc(r.service_display)+'</td>';
    html += '<td style="padding:6px 8px;color:var(--text-muted);">'+esc(r.vendor)+'</td>';

    var term = r.term || '-';
    var termLabel = term === 'Monthly' ? t('term_monthly','Monthly') : term === 'Annual' ? t('term_annual','Annual') : term === 'Quarterly' ? t('term_quarterly','Quarterly') : term;
    var termIcon = term === 'Monthly' ? '\ud83d\udd04' : term === 'Annual' ? '\ud83d\udcc6' : term === 'Quarterly' ? '\ud83d\udcc5' : term.indexOf('Year') !== -1 ? '\ud83d\udcc6' : '';
    var termColor = term === 'Monthly' ? 'var(--blue)' : term === 'Annual' ? 'var(--purple)' : 'var(--text-muted)';
    html += '<td style="padding:6px 8px;text-align:center;font-size:11px;"><span style="color:'+termColor+';font-weight:600;">'+termIcon+' '+esc(termLabel)+'</span></td>';

    // Qty / Price / Monthly — show dash if not yet cached
    var qty = r.quantity || 0;
    var price = r.unit_price || 0;
    var monthly = r.monthly_cost || 0;
    html += '<td style="padding:6px 8px;text-align:center;font-weight:600;">'+(qty > 0 ? qty : '<span style="color:var(--text-dim);">-</span>')+'</td>';
    html += '<td style="padding:6px 8px;text-align:right;font-family:var(--mono);font-size:11px;">'+(price > 0 ? price.toFixed(2) : '<span style="color:var(--text-dim);">-</span>')+'</td>';
    html += '<td style="padding:6px 8px;text-align:right;font-family:var(--mono);font-weight:600;">'+(monthly > 0 ? monthly.toFixed(2) : '<span style="color:var(--text-dim);">-</span>')+'</td>';

    html += '<td style="padding:6px 8px;text-align:center;font-size:11px;">'+renewDate+'</td>';
    html += '<td style="padding:6px 8px;text-align:center;font-weight:700;color:'+daysColor+';">'+daysLabel+'</td>';

    var stColor = r.account_state === 'Active' ? 'var(--green)' : 'var(--orange)';
    html += '<td style="padding:6px 8px;text-align:center;"><span style="font-size:10px;color:'+stColor+';font-weight:600;">'+esc(r.account_state)+'</span></td>';

    html += '<td style="padding:6px 8px;"><input type="text" value="'+esc(r.notes||'')+'" placeholder="'+t('lbl_add_note','Add note...')+'" onchange="alsoSaveNote('+r.id+',this.value)" style="width:100%;padding:2px 6px;background:var(--bg-input);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;"></td>';
    html += '</tr>';
  });

  // Final customer subtotal
  if (lastCustomer && customerMrr > 0) {
    html += '<tr style="background:var(--bg);border-bottom:2px solid var(--border);"><td colspan="7" style="padding:4px 8px;text-align:right;font-size:11px;font-weight:600;color:var(--text-muted);">'+esc(lastCustomer)+' MRR:</td><td style="padding:4px 8px;text-align:right;font-weight:700;font-family:var(--mono);font-size:11px;">'+customerMrr.toFixed(2)+'</td><td colspan="4"></td></tr>';
  }

  html += '</tbody></table></div>';

  // Uniweb renewals placeholder
  html += '<div id="dash-uniweb-renewals" style="margin-top:16px;"><div class="loader" style="width:16px;height:16px;margin:16px auto;"></div></div>';

  el.innerHTML = html;

  // Make renewals table sortable
  var renewalTable = el.querySelector('table');
  if (renewalTable) makeSortable(renewalTable);

  // Refresh API stats
  alsoRefreshApiStats();

  // Populate vendor filter
  var vendors = {};
  _lastRenewals.forEach(function(r) { if (r.vendor) vendors[r.vendor] = true; });
  var vSel = document.getElementById('renewal-filter-vendor');
  if (vSel) {
    var curV = vSel.value;
    vSel.innerHTML = '<option value="">'+t('lbl_all_vendors','All vendors')+'</option>';
    Object.keys(vendors).sort().forEach(function(v) { vSel.innerHTML += '<option value="'+esc(v)+'"'+(v===curV?' selected':'')+'>'+esc(v)+'</option>'; });
  }

  // Load Uniweb renewals async
  _loadUniwebRenewals();
}


// ═══════════════════════════════════════════════════════════════════
// UNIWEB FORNYELSER (Hosting / Domener / SSL)
// ═══════════════════════════════════════════════════════════════════

async function _loadUniwebRenewals() {
  var container = document.getElementById('dash-uniweb-renewals');
  if (!container) return;

  try {
    var data = await apiFetch('/api/uniweb/alerts?days=365');
    if (!data || !data.items || data.items.length === 0) {
      container.innerHTML = '<div class="card" style="padding:24px;text-align:center;color:var(--green);">'
        + '<div style="font-size:28px;margin-bottom:6px;">&#10003;</div>'
        + '<div style="font-size:13px;font-weight:600;">'+t('msg_no_uniweb_renewals','Ingen Uniweb-fornyelser')+'</div>'
        + '<div style="font-size:12px;color:var(--text-muted);">'+t('msg_no_uniweb_renewals_hint','Ingen domener, abonnementer eller SSL-sertifikater utløper innen ett år.')+'</div>'
        + '</div>';
      return;
    }

    var typeLabels = {domain: t('lbl_domain','Domene'), subscription: t('lbl_subscription','Abonnement'), ssl: t('lbl_ssl_cert','SSL-sertifikat')};
    var items = data.items;

    // Group by urgency
    var kritisk = items.filter(function(i) { return i.days_remaining < 7; });
    var snart = items.filter(function(i) { return i.days_remaining >= 7 && i.days_remaining < 30; });
    var kommende = items.filter(function(i) { return i.days_remaining >= 30 && i.days_remaining < 90; });
    var langt = items.filter(function(i) { return i.days_remaining >= 90; });

    var html = '';

    // KPI row
    html += '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px;">';
    var kpis = [
      {label:t('kpi_cached','Totalt'), value:data.total, color:'var(--blue)'},
      {label:t('kpi_expired','Utløpt/Kritisk')+ ' (<7d)', value:kritisk.length, color:kritisk.length>0?'var(--red)':'var(--text-dim)'},
      {label:t('kpi_30d','< 30 dager'), value:snart.length, color:snart.length>0?'var(--orange)':'var(--text-dim)'},
      {label:'30\u201390 '+t('col_days','dager'), value:kommende.length, color:kommende.length>0?'#c9a800':'var(--text-dim)'},
      {label:'90\u2013365 '+t('col_days','dager'), value:langt.length, color:langt.length>0?'var(--green)':'var(--text-dim)'},
    ];
    kpis.forEach(function(k) {
      html += '<div class="card" style="padding:12px 8px;text-align:center;border-top:2px solid '+k.color+';height:80px;box-sizing:border-box;">';
      html += '<div style="font-size:18px;font-weight:700;line-height:22px;color:'+k.color+';">'+k.value+'</div>';
      html += '<div style="font-size:10px;color:var(--text-muted);line-height:14px;">'+k.label+'</div>';
      html += '</div>';
    });
    html += '</div>';

    // Section header
    html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">';
    html += '<div style="font-size:14px;font-weight:600;color:var(--text);">' + t('also_uniweb_renewals','Uniweb-fornyelser') + '</div>';
    html += '<button class="btn btn-ghost" onclick="_loadUniwebRenewals()" style="padding:4px 12px;font-size:11px;">' + t('also_refresh','Oppdater') + '</button>';
    html += '</div>';

    // Render each urgency group
    var groups = [
      {label:'Kritisk', subtitle:t('also_exp_7d','Utløper innen 7 dager'), items:kritisk, color:'var(--red)', bgTint:'rgba(255,59,48,0.06)'},
      {label:'Snart', subtitle:t('also_exp_30d','Utløper innen 30 dager'), items:snart, color:'var(--orange)', bgTint:'rgba(255,149,0,0.06)'},
      {label:'Kommende', subtitle:t('also_exp_90d','Utløper innen 90 dager'), items:kommende, color:'#c9a800', bgTint:'rgba(201,168,0,0.06)'},
      {label:'Langsiktig', subtitle:t('also_exp_365d','90–365 dager'), items:langt, color:'var(--green)', bgTint:'rgba(59,185,80,0.06)'},
    ];

    groups.forEach(function(g) {
      if (g.items.length === 0) return;

      html += '<div class="card" style="padding:0;overflow:hidden;margin-bottom:12px;border-left:3px solid '+g.color+';">';
      html += '<div style="padding:12px 16px;background:'+g.bgTint+';border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;">';
      html += '<div><span style="font-size:13px;font-weight:700;color:'+g.color+';">'+g.label+'</span>';
      html += '<span style="font-size:11px;color:var(--text-muted);margin-left:8px;">'+g.subtitle+'</span></div>';
      html += '<span style="font-size:12px;font-weight:600;color:'+g.color+';">'+g.items.length+' element'+(g.items.length!==1?'er':'')+'</span>';
      html += '</div>';

      html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
      html += '<thead><tr style="background:var(--bg-tertiary);border-bottom:1px solid var(--border);">';
      html += '<th style="text-align:left;padding:7px 10px;">' + t('also_col_customer','Kunde') + '</th>';
      html += '<th style="text-align:left;padding:7px 10px;">' + t('also_col_type','Type') + '</th>';
      html += '<th style="text-align:left;padding:7px 10px;">' + t('also_col_name','Navn') + '</th>';
      html += '<th style="text-align:center;padding:7px 10px;">' + t('also_col_expiry','Utløpsdato') + '</th>';
      html += '<th style="text-align:center;padding:7px 10px;">' + t('also_col_days_left','Dager igjen') + '</th>';
      html += '</tr></thead><tbody>';

      g.items.forEach(function(item, idx) {
        var daysColor = item.days_remaining < 0 ? 'var(--red)' : item.days_remaining < 7 ? 'var(--red)' : item.days_remaining < 14 ? 'var(--orange)' : '#c9a800';
        var daysLabel = item.days_remaining < 0 ? 'UTLOPT' : item.days_remaining + 'd';
        var rowBg = idx % 2 === 0 ? 'transparent' : 'var(--bg-tertiary)';

        html += '<tr style="background:'+rowBg+';border-bottom:1px solid var(--border);">';
        html += '<td style="padding:6px 10px;font-weight:500;">'+esc(item.customer_name)+'</td>';
        html += '<td style="padding:6px 10px;"><span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;background:var(--bg-tertiary);color:var(--text-muted);">'+esc(typeLabels[item.type] || item.type)+'</span></td>';
        html += '<td style="padding:6px 10px;">'+esc(item.item_name)+'</td>';
        html += '<td style="padding:6px 10px;text-align:center;font-size:11px;font-family:var(--mono);">'+esc(item.expiry_date)+'</td>';
        html += '<td style="padding:6px 10px;text-align:center;font-weight:700;color:'+daysColor+';">'+daysLabel+'</td>';
        html += '</tr>';
      });

      html += '</tbody></table></div>';
    });

    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = '<div class="card" style="padding:16px;text-align:center;color:var(--text-muted);font-size:12px;">' + t('also_uniweb_load_failed','Kunne ikke laste Uniweb-fornyelser. Sjekk at Uniweb er konfigurert.') + '</div>';
  }
}

async function alsoDownloadPDF() {
  showToast(t('also_generating_pdf','Genererer PDF ...'), 'info', 3000);
  try {
    var resp = await fetch('/api/also/renewals/report?days=365');
    if (!resp.ok) { showToast(t('also_pdf_failed','PDF-generering feilet') + ': ' + resp.status, 'error'); return; }
    var blob = await resp.blob();
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'renewal_report_' + new Date().toISOString().slice(0,10) + '.pdf';
    a.click();
    URL.revokeObjectURL(a.href);
  } catch(e) { showToast(t('also_pdf_error','PDF-feil') + ': ' + e.message, 'error'); }
}

function alsoToggleAll(checked) {
  document.querySelectorAll('.renewal-cb').forEach(function(cb) { cb.checked = checked; });
}

async function alsoBulkHandled() {
  var cbs = document.querySelectorAll('.renewal-cb:checked');
  if (!cbs.length) { showToast(t('also_nothing_selected','Ingenting valgt'), 'warning'); return; }
  var promises = [];
  cbs.forEach(function(cb) {
    promises.push(apiFetch('/api/also/renewals/' + cb.dataset.id + '/handle', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({handled:1})
    }));
  });
  await Promise.all(promises);
  showToast(cbs.length + ' ' + t('also_marked_handled','markert som håndtert'), 'success');
  dashLoadRenewals();
}

function alsoExportCSV() {
  var data = _lastRenewals;
  if (!data || !data.length) { showToast(t('also_nothing_to_export','Ingen data å eksportere'), 'warning'); return; }
  // CSV headers kept in English for data processing
  var lines = ['Customer,Product,Vendor,Term,Qty,Unit Price,Monthly,Renewal Date,Days Left,Status,Handled,Notes'];
  data.forEach(function(r) {
    lines.push([
      '"'+(r.customer_name||'').replace(/"/g,'""')+'"',
      '"'+(r.service_display||'').replace(/"/g,'""')+'"',
      '"'+(r.vendor||'')+'"',
      '"'+(r.term||'')+'"',
      r.quantity||0,
      r.unit_price ? r.unit_price.toFixed(2) : '',
      r.monthly_cost ? r.monthly_cost.toFixed(2) : '',
      r.contract_end ? r.contract_end.slice(0,10) : '',
      r.days_left != null ? r.days_left : '',
      r.account_state||'',
      r.handled ? 'Yes' : 'No',
      '"'+(r.notes||'').replace(/"/g,'""')+'"',
    ].join(','));
  });
  var blob = new Blob([lines.join('\n')], {type:'text/csv'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'renewals_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
  showToast(t('also_csv_exported','CSV eksportert'), 'success', 1500);
}

async function alsoToggleHandled(renewalId, handled) {
  await apiFetch('/api/also/renewals/' + renewalId + '/handle', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({handled: handled ? 1 : 0})
  });
}

async function alsoSaveNote(renewalId, notes) {
  await apiFetch('/api/also/renewals/' + renewalId + '/handle', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({handled: document.querySelector('input[onchange*="'+renewalId+'"]') ? 1 : 0, notes: notes})
  });
  showToast(t('also_note_saved','Notat lagret'), 'success', 1500);
}

var _renewalScanTimer = null;

async function alsoRenewalScan() {
  var btn = document.getElementById('renewal-scan-btn');
  var msg = document.getElementById('renewal-scan-msg');
  btn.disabled = true;
  btn.textContent = t('msg_scanning','Scanning …');

  // Show progress bar
  msg.innerHTML = '<div style="margin-top:4px;">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
    + '<div style="flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden;">'
    + '<div id="renewal-scan-bar" style="width:0%;height:100%;background:var(--blue);border-radius:3px;transition:width 0.5s;"></div></div>'
    + '<span id="renewal-scan-pct" style="font-size:11px;color:var(--text-muted);min-width:40px;">0%</span></div>'
    + '<div id="renewal-scan-detail" style="font-size:11px;color:var(--text-dim);">' + t('also_starting','Starter ...') + '</div></div>';

  // Start polling progress
  _renewalScanTimer = setInterval(async function() {
    var p = await apiFetch('/api/also/renewal-scan/progress');
    if (!p) return;
    var pct = p.total > 0 ? Math.round((p.scanned / p.total) * 100) : 0;
    var bar = document.getElementById('renewal-scan-bar');
    var pctEl = document.getElementById('renewal-scan-pct');
    var detail = document.getElementById('renewal-scan-detail');
    if (bar) bar.style.width = pct + '%';
    if (pctEl) pctEl.textContent = pct + '%';
    if (detail) detail.textContent = p.current ? t('also_scanning','Skanner') + ': ' + p.current + ' (' + (p.scanned+1) + '/' + p.total + ')' : (p.done ? t('also_done','Ferdig') : t('also_starting','Starter ...'));
    if (p.done && _renewalScanTimer) { clearInterval(_renewalScanTimer); _renewalScanTimer = null; }
  }, 1500);

  var d = await apiFetch('/api/also/renewal-scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({batch_size: 25, delay: 1.5})});
  if (_renewalScanTimer) { clearInterval(_renewalScanTimer); _renewalScanTimer = null; }
  btn.disabled = false;

  if (d && d.ok) {
    var remaining = d.remaining || 0;
    var bar = document.getElementById('renewal-scan-bar');
    if (bar) bar.style.width = '100%';

    if (remaining > 0) {
      btn.textContent = t('also_scan_next_batch','Skann neste batch') + ' (' + remaining + ' ' + t('also_remaining','gjenstår') + ')';
      msg.innerHTML = '<span style="color:var(--green);">\u2713 ' + t('also_scanned','Skannet') + ' '+d.scanned+' \u00b7 '+d.already_cached+' ' + t('also_already_cached','allerede bufret') + ' \u00b7 '+remaining+' ' + t('also_remaining','gjenstår')+(d.errors?' \u00b7 <span style="color:var(--orange);">'+d.errors+' ' + t('also_errors','feil') + '</span>':'')+'</span>';
    } else {
      btn.textContent = t('btn_sync','Sync');
      msg.innerHTML = '<span style="color:var(--green);">\u2713 ' + t('also_all','Alle') + ' '+d.total_linked+' ' + t('also_customers_cached','kunder ferdig bufret') + '</span>';
    }
    return d;
  } else {
    btn.textContent = t('btn_sync','Sync');
    msg.innerHTML = '<span style="color:var(--red);">' + esc(d && d.error || 'Skanning feilet') + '</span>';
    return null;
  }
}

async function alsoRefreshApiStats() {
  var el = document.getElementById('also-api-stats');
  if (!el) return;
  var s = await apiFetch('/api/also/api-stats');
  if (!s || !s.total_calls) { el.textContent = t('msg_api_zero_calls','API: 0 calls'); return; }
  el.innerHTML = 'API: <strong>'+s.total_calls+'</strong> kall \u00b7 '+s.last_1min+'/min \u00b7 '+s.last_5min+'/5min \u00b7 snitt '+s.avg_response_ms+'ms'
    + (s.errors > 0 ? ' \u00b7 <span style="color:var(--red);">'+s.errors+' ' + t('also_errors','feil') + '</span>' : '');
}

var _priceScanTimer = null;

async function alsoPriceScan() {
  var btn = document.getElementById('renewal-scan-btn');
  var msg = document.getElementById('renewal-scan-msg');
  btn.disabled = true;
  btn.textContent = t('also_fetching_prices','Henter priser ...');

  msg.innerHTML = '<div style="margin-top:4px;">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
    + '<div style="flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden;">'
    + '<div id="price-scan-bar" style="width:0%;height:100%;background:var(--green);border-radius:3px;transition:width 0.5s;"></div></div>'
    + '<span id="price-scan-pct" style="font-size:11px;color:var(--text-muted);min-width:40px;">0%</span></div>'
    + '<div id="price-scan-detail" style="font-size:11px;color:var(--text-dim);">' + t('also_fetching_prices','Henter priser ...') + '</div></div>';

  _priceScanTimer = setInterval(async function() {
    var p = await apiFetch('/api/also/price-scan/progress');
    if (!p) return;
    var pct = p.total > 0 ? Math.round((p.scanned / p.total) * 100) : 0;
    var bar = document.getElementById('price-scan-bar');
    var pctEl = document.getElementById('price-scan-pct');
    var detail = document.getElementById('price-scan-detail');
    if (bar) bar.style.width = pct + '%';
    if (pctEl) pctEl.textContent = pct + '%';
    if (detail) detail.textContent = p.current ? '\ud83d\udcb0 ' + p.current + ' (' + (p.scanned+1) + '/' + p.total + ')' : (p.done ? t('also_done','Ferdig') : t('also_starting','Starter ...'));
    if (p.done && _priceScanTimer) { clearInterval(_priceScanTimer); _priceScanTimer = null; }
  }, 1500);

  var d = await apiFetch('/api/also/price-scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({batch_size: 25, delay: 1.5})});
  if (_priceScanTimer) { clearInterval(_priceScanTimer); _priceScanTimer = null; }
  btn.disabled = false;

  if (d && d.ok) {
    var remaining = d.remaining || 0;
    var bar = document.getElementById('price-scan-bar');
    if (bar) bar.style.width = '100%';

    if (remaining > 0) {
      btn.textContent = t('also_next_price_batch','Neste prisbatch') + ' (' + remaining + ' ' + t('also_remaining','gjenstår') + ')';
      msg.innerHTML = '<span style="color:var(--green);">\u2713 ' + t('also_priced','Priset') + ' '+d.scanned+' ' + t('also_subscriptions_lc','abonnementer') + ' \u00b7 '+remaining+' ' + t('also_remaining','gjenstår')+(d.errors?' \u00b7 <span style="color:var(--orange);">'+d.errors+' ' + t('also_errors','feil') + '</span>':'')+'</span>';
    } else {
      btn.textContent = t('btn_sync','Sync');
      msg.innerHTML = '<span style="color:var(--green);">\u2713 ' + t('also_all_priced','Alle abonnementer priset') + '</span>';
    }
    return d;
  } else {
    btn.textContent = t('btn_sync','Sync');
    msg.innerHTML = '<span style="color:var(--red);">' + esc(d && d.error || 'Prisskanning feilet') + '</span>';
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════════
// Combined sync: scan licenses then cache prices
// ═══════════════════════════════════════════════════════════════════

async function alsoCombinedSync() {
  var btn = document.getElementById('renewal-scan-btn');
  var msg = document.getElementById('renewal-scan-msg');

  // Phase 1: Scan licenses
  btn.disabled = true;
  btn.textContent = ''+t('lbl_syncing_licenses','Syncing... (1/2 Licenses)')+'';

  var scanResult = await alsoRenewalScan();

  // If scan failed or has remaining batches, stop here
  if (!scanResult) {
    btn.disabled = false;
    btn.textContent = t('btn_sync','Sync');
    return;
  }
  if (scanResult.remaining > 0) {
    // There are more batches to scan — let user click again
    btn.disabled = false;
    btn.textContent = t('btn_sync','Sync') + ' (' + scanResult.remaining + ')';
    return;
  }

  // Phase 2: Cache prices
  btn.textContent = ''+t('lbl_syncing_prices','Syncing... (2/2 Prices)')+'';
  var priceResult = await alsoPriceScan();

  btn.disabled = false;

  if (priceResult && (!priceResult.remaining || priceResult.remaining === 0)) {
    btn.textContent = t('btn_sync','Sync');
    msg.innerHTML = '<span style="color:var(--green);">\u2713</span>';
    dashLoadRenewals();
  } else if (priceResult && priceResult.remaining > 0) {
    btn.textContent = t('btn_sync','Sync') + ' (' + priceResult.remaining + ')';
    dashLoadRenewals();
  }
  // If priceResult is null, error message is already shown by alsoPriceScan
}


// ═══════════════════════════════════════════════════════════════════
// LICENSE OPTIMIZATION — Compare ALSO paid vs audit assigned
// ═══════════════════════════════════════════════════════════════════

var _licOptData = null;

async function alsoShowLicenseOptimization() {
  var el = document.getElementById('dash-renewals-content');
  el.innerHTML = '<div class="loader" style="width:20px;height:20px;margin:24px auto;"></div>'
    + '<div style="text-align:center;color:var(--text-muted);font-size:12px;">'
    + t('lbl_loading_lic_opt','Loading license optimization...') + '</div>';

  var data = await apiFetch('/api/also/license-optimization');
  if (!data) {
    el.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:24px;font-size:12px;">'
      + t('msg_lic_opt_unavailable','Could not load license optimization data') + '</div>'
      + '<div style="text-align:center;margin-top:8px;"><button class="btn btn-ghost" onclick="dashLoadRenewals()" style="font-size:11px;">'
      + t('btn_back_renewals','Back to renewals') + '</button></div>';
    return;
  }
  _licOptData = data;
  _renderLicenseOptimization(data, el);
}

function _renderLicenseOptimization(data, el) {
  var s = data.summary || {};
  var customers = data.customers || [];
  var cur = s.currency || 'NOK';
  var html = '';

  // ── Header + back button ──
  html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">';
  html += '<div style="font-size:16px;font-weight:700;">'+t('hdr_license_opt','License Optimization')+'</div>';
  html += '<button class="btn btn-ghost" onclick="dashLoadRenewals()" style="padding:4px 12px;font-size:11px;">'
    + t('btn_back_renewals','Back to renewals') + '</button>';
  html += '</div>';

  // ── KPI row ──
  html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:16px;">';
  var kpis = [
    {label:t('kpi_total_waste','Total waste/mo'), value:s.total_waste > 0 ? s.total_waste.toFixed(0)+' '+cur : '0 '+cur, color:s.total_waste>0?'var(--red)':'var(--green)'},
    {label:t('kpi_over_licensed','Over-licensed'),  value:s.over_licensed_count,  color:s.over_licensed_count>0?'var(--orange)':'var(--text-dim)'},
    {label:t('kpi_under_licensed','Under-licensed'), value:s.under_licensed_count, color:s.under_licensed_count>0?'var(--red)':'var(--text-dim)'},
    {label:t('kpi_optimal','Optimal'),              value:s.optimal_count,        color:s.optimal_count>0?'var(--green)':'var(--text-dim)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card" style="padding:12px 8px;text-align:center;border-top:3px solid '+k.color+';height:80px;box-sizing:border-box;">';
    html += '<div style="font-size:18px;font-weight:700;line-height:22px;color:'+k.color+';">'+k.value+'</div>';
    html += '<div style="font-size:10px;color:var(--text-muted);line-height:14px;">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  if (customers.length === 0) {
    html += '<div class="card" style="padding:32px;text-align:center;color:var(--text-muted);">';
    html += '<div style="font-size:14px;font-weight:600;margin-bottom:4px;">'+t('msg_no_lic_opt','No license optimization data')+'</div>';
    html += '<div style="font-size:12px;">'+t('msg_no_lic_opt_hint','Run audit on ALSO-linked customers and sync subscriptions first.')+'</div>';
    html += '</div>';
    el.innerHTML = html;
    return;
  }

  // ── Per-customer cards ──
  customers.forEach(function(c) {
    var wasteColor = c.total_monthly_waste > 0 ? 'var(--red)' : 'var(--green)';
    var borderColor = c.total_monthly_waste > 500 ? 'var(--red)' : c.total_monthly_waste > 0 ? 'var(--orange)' : 'var(--green)';

    html += '<div class="card" style="padding:0;overflow:hidden;margin-bottom:12px;border-left:3px solid '+borderColor+';">';

    // Customer header
    html += '<div style="padding:12px 16px;background:var(--bg-tertiary);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;">';
    html += '<div style="font-size:13px;font-weight:700;">'+esc(c.customer_name)+'</div>';
    html += '<div style="display:flex;gap:16px;font-size:11px;">';
    html += '<span style="color:var(--text-muted);">'+t('lbl_paid','Paid')+': <strong>'+c.total_paid+'</strong></span>';
    html += '<span style="color:var(--text-muted);">'+t('lbl_assigned','Assigned')+': <strong>'+c.total_assigned+'</strong></span>';
    if (c.total_monthly_waste > 0) {
      html += '<span style="color:'+wasteColor+';font-weight:700;">'+t('lbl_waste','Waste')+': '+c.total_monthly_waste.toFixed(0)+' '+cur+'/'+t('lbl_mo','mo')+'</span>';
    }
    if (!c.has_audit_data) {
      html += '<span style="color:var(--orange);font-size:10px;">'+t('lbl_no_audit','No audit data')+'</span>';
    }
    html += '</div></div>';

    // License table
    if (c.licenses.length > 0) {
      html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
      html += '<thead><tr style="background:var(--bg);border-bottom:1px solid var(--border);">';
      html += '<th style="text-align:left;padding:7px 10px;">'+t('col_product','Product')+'</th>';
      html += '<th style="text-align:center;padding:7px 10px;">'+t('col_paid_qty','Paid')+'</th>';
      html += '<th style="text-align:center;padding:7px 10px;">'+t('col_assigned_qty','Assigned')+'</th>';
      html += '<th style="text-align:center;padding:7px 10px;">'+t('col_excess','Excess')+'</th>';
      html += '<th style="text-align:center;padding:7px 10px;">'+t('col_lic_status','Status')+'</th>';
      html += '<th style="text-align:right;padding:7px 10px;">'+t('col_unit_price','Unit price')+'</th>';
      html += '<th style="text-align:right;padding:7px 10px;">'+t('col_monthly_waste','Waste/mo')+'</th>';
      html += '</tr></thead><tbody>';

      c.licenses.forEach(function(lic, idx) {
        var rowBg = idx % 2 === 0 ? 'transparent' : 'var(--bg-tertiary)';
        var statusColor, statusLabel;
        switch (lic.status) {
          case 'over_licensed':
            statusColor = 'var(--orange)'; statusLabel = t('status_over','Over-licensed'); break;
          case 'under_licensed':
            statusColor = 'var(--red)'; statusLabel = t('status_under','Under-licensed'); break;
          case 'optimal':
            statusColor = 'var(--green)'; statusLabel = t('status_optimal','Optimal'); break;
          case 'unused':
            statusColor = 'var(--red)'; statusLabel = t('status_unused','Unused'); break;
          case 'no_audit_data':
            statusColor = 'var(--text-dim)'; statusLabel = t('status_no_audit','No audit'); break;
          default:
            statusColor = 'var(--text-muted)'; statusLabel = lic.status; break;
        }

        html += '<tr style="background:'+rowBg+';border-bottom:1px solid var(--border);">';
        html += '<td style="padding:6px 10px;font-weight:500;">'+esc(lic.product)+'</td>';
        html += '<td style="padding:6px 10px;text-align:center;font-weight:600;">'+lic.paid_qty+'</td>';
        html += '<td style="padding:6px 10px;text-align:center;font-weight:600;">'+(lic.assigned_qty > 0 ? lic.assigned_qty : '<span style="color:var(--text-dim);">-</span>')+'</td>';
        html += '<td style="padding:6px 10px;text-align:center;font-weight:700;color:'+(lic.excess > 0 ? statusColor : 'var(--text-dim)')+';">'+(lic.excess > 0 ? (lic.status === 'under_licensed' ? '+' : '')+lic.excess : '-')+'</td>';
        html += '<td style="padding:6px 10px;text-align:center;"><span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;background:var(--bg-tertiary);color:'+statusColor+';">'+statusLabel+'</span></td>';
        html += '<td style="padding:6px 10px;text-align:right;font-family:var(--mono);font-size:11px;">'+(lic.unit_price > 0 ? lic.unit_price.toFixed(2) : '-')+'</td>';
        html += '<td style="padding:6px 10px;text-align:right;font-family:var(--mono);font-weight:700;color:'+(lic.monthly_waste > 0 ? 'var(--red)' : 'var(--text-dim)')+';">'+(lic.monthly_waste > 0 ? lic.monthly_waste.toFixed(2) : '-')+'</td>';
        html += '</tr>';
      });

      html += '</tbody></table>';
    }
    html += '</div>';
  });

  el.innerHTML = html;

  // Make tables sortable
  el.querySelectorAll('table').forEach(function(tbl) { makeSortable(tbl); });
}
