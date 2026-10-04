// ═══════════════════════════════════════════════════════════════════
// ALSO RENEWAL ACTION LIST
// ═══════════════════════════════════════════════════════════════════

import {esc} from './app-esc.js';
import {t} from './app-i18n.js';
import {icon} from './app-icons.js';
import {registerUiHandlers} from './app-handlers.js';
import {_currentUser} from './app-state.js';
import {toneClass, toneVar} from './app-format.js';
import {makeSortable, showToast} from './app-ui.js';
import {apiFetch} from './app-api.js';

// Handlers for the markup this file builds (see registerUiHandlers in app-handlers.js).
registerUiHandlers({
  renewalShowAll: function() { _renewalIntervalFilter = null; dashLoadRenewals(); },
  renewalSetFilter: function(el) { _setRenewalFilter(el.dataset.filterKey); },
  dashLoadRenewals: function() { dashLoadRenewals(); },
  alsoCombinedSync: function() { alsoCombinedSync(); },
  alsoBulkHandled: function() { alsoBulkHandled(); },
  alsoExportCSV: function() { alsoExportCSV(); },
  alsoDownloadPDF: function() { alsoDownloadPDF(); },
  alsoShowLicenseOptimization: function() { alsoShowLicenseOptimization(); },
  alsoToggleAll: function(el) { alsoToggleAll(el.checked); },
  alsoToggleHandled: function(el) { alsoToggleHandled(Number(el.dataset.id), el.checked); },
  alsoSaveNote: function(el) { alsoSaveNote(Number(el.dataset.id), el.value); },
  _loadUniwebRenewals: function() { _loadUniwebRenewals(); },
  _loadUniwebMoney: function() { _loadUniwebMoney(); },
});

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

export async function dashLoadRenewals() {
  var el = document.getElementById('dash-renewals-content');
  el.innerHTML = '<div class="loader loader-md"></div><div class="text-center text-muted text-sm">' + t('also_loading_renewals','Laster fornyelser ...') + '</div>';

  var data = await apiFetch('/api/also/renewals?days=365');
  if (!data) {
    el.innerHTML = '<div class="text-muted text-center p-6 text-sm">' + t('also_unavailable','ALSO Cloud ikke tilgjengelig') + '</div>'
      + '<div id="dash-uniweb-renewals" class="mt-4"><div class="loader mx-auto my-4"></div></div>';
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
  var mrrText = data.total_mrr > 0 ? data.total_mrr.toFixed(0) + ' ' + esc(data.currency || '') : '-';
  var af = _renewalIntervalFilter;
  var html = '<div class="grid grid-auto-sm gap-3 mb-4">';
  var kpis = [
    {label:t('kpi_cached','Cached'),     value:Number(data.all_cached),  color:'var(--blue)',   filterKey:null},
    {label:t('kpi_expired','Expired'),   value:Number(data.expired),     color:data.expired>0?'var(--red)':'var(--text-dim)',     filterKey:'expired'},
    {label:t('kpi_30d','< 30 days'),     value:Number(data.urgent_30d),  color:data.urgent_30d>0?'var(--red)':'var(--text-dim)',  filterKey:'30'},
    {label:t('kpi_30_60d','30–60 days'), value:Number(data.soon_60d), color:data.soon_60d>0?'var(--orange)':'var(--text-dim)',filterKey:'60'},
    {label:t('kpi_60_365d','60–365 days'), value:Number(data.upcoming), color:data.upcoming>0?'var(--orange)':'var(--text-dim)',filterKey:'365'},
    {label:t('kpi_1yr','> 1 year'),      value:Number(data.beyond)||0,   color:'var(--green)',  filterKey:'1yr'},
    {label:t('kpi_mrr_cached','MRR (cached)'), value:mrrText,    color:data.total_mrr>0?'var(--green)':'var(--text-dim)', filterKey:null, noClick:true},
    {label:t('kpi_priced','Priced'),     value:Number(data.priced_count)+'/'+Number(data.all_cached), color:data.priced_count>0?'var(--blue)':'var(--text-dim)', filterKey:null, noClick:true},
  ];
  kpis.forEach(function(k) {
    var isActive = (k.filterKey !== null && af === k.filterKey) || (k.filterKey === null && af === null && !k.noClick);
    var clickable = !k.noClick;
    // "Bufret" card is highlighted when no filter active (it means "all")
    if (k.filterKey === null && !k.noClick) {
      isActive = (af === null);
    }
    var clickAttrs = '';
    if (clickable) {
      if (k.filterKey === null) {
        clickAttrs = ' data-click-handler="renewalShowAll"';
      } else {
        clickAttrs = ' data-click-handler="renewalSetFilter" data-filter-key="'+esc(k.filterKey)+'"';
      }
    }
    html += '<div class="card kpi-card ' + toneVar(k.color) + (clickable ? ' cursor-pointer' : '') + (isActive ? ' is-active' : '') + '"'+clickAttrs+'>';
    html += '<div class="kpi-value ' + toneClass(k.color) + '">'+k.value+'</div>';
    html += '<div class="kpi-label">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  // ── Action bar ──
  html += '<div class="flex items-center gap-3 mb-3 flex-wrap">';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="dashLoadRenewals">'+t('btn_refresh','Refresh')+'</button>';
  html += '<button class="btn btn-primary btn-sm" data-write data-click-handler="alsoCombinedSync" id="renewal-scan-btn">'+t('btn_sync','Sync')+'</button>';
  html += '<button class="btn btn-ghost btn-sm" data-write data-click-handler="alsoBulkHandled">'+t('btn_mark_handled','Mark selected handled')+'</button>';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="alsoExportCSV">'+t('btn_export_csv','Export CSV')+'</button>';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="alsoDownloadPDF">'+icon('document',13)+' '+t('btn_pdf_report','PDF Report')+'</button>';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="alsoShowLicenseOptimization">'+t('btn_license_opt','Lisensoptimalisering')+'</button>';
  html += '<select id="renewal-filter-vendor" data-change-handler="dashLoadRenewals" class="field-input field-input-sm w-auto"><option value="">'+t('lbl_all_vendors','All vendors')+'</option></select>';
  // Show "Vis alle" link when interval filter is active
  if (_renewalIntervalFilter) {
    html += '<a href="#" data-click-handler="renewalShowAll" class="text-xs text-accent underline cursor-pointer">'+t('lbl_show_all','Show all')+'</a>';
  }
  html += '<span id="renewal-scan-msg" class="text-xs text-muted"></span>';
  html += '<span id="also-api-stats" class="text-2xs text-dim ml-auto font-mono"></span>';
  html += '</div>';

  if (!renewals.length) {
    html += '<div class="card empty-note is-compact">';
    html += '<div class="text-3xl mb-2">'+icon('document',32)+'</div>';
    if (_lastRenewals.length === 0) {
      html += '<div class="text-base fw-semibold mb-1">'+t('msg_no_renewal_data','No renewal data cached yet')+'</div>';
      html += '<div class="text-sm">'+t('msg_no_renewal_data_hint','View licenses on a customer, or click "Sync" to build the cache.')+'</div>';
    } else {
      html += '<div class="text-base fw-semibold mb-1">'+t('msg_no_renewals_filter','No renewals in this filter')+'</div>';
      html += '<div class="text-sm"><a href="#" data-click-handler="renewalShowAll" class="text-accent">'+t('lbl_show_all','Show all')+'</a></div>';
    }
    html += '</div>';
    // Still show Uniweb renewals even when ALSO has no data
    html += '<div id="dash-uniweb-renewals" class="mt-4"><div class="loader mx-auto my-4"></div></div>';
    el.innerHTML = html;
    _loadUniwebRenewals();
    return;
  }

  // ── Table ──
  html += '<div class="card p-0 overflow-x-auto">';
  html += '<table class="data-table">';
  html += '<thead><tr>';
  html += '<th class="text-center p-2 col-check"><input type="checkbox" class="checkbox" data-change-handler="alsoToggleAll" title="'+t('tip_select_all','Select all')+'"></th>';
  html += '<th class="p-2">'+t('col_customer','Customer')+'</th>';
  html += '<th class="p-2">'+t('col_product','Product')+'</th>';
  html += '<th class="p-2">'+t('col_vendor','Vendor')+'</th>';
  html += '<th class="text-center p-2">'+t('col_term','Term')+'</th>';
  html += '<th class="text-center p-2">'+t('col_qty','Qty')+'</th>';
  html += '<th class="text-right p-2">'+t('col_price','Price')+'</th>';
  html += '<th class="text-right p-2">'+t('col_monthly','Monthly')+'</th>';
  html += '<th class="text-center p-2">'+t('col_renews','Renews')+'</th>';
  html += '<th class="text-center p-2">'+t('col_days','Days')+'</th>';
  html += '<th class="text-center p-2">'+t('col_status','Status')+'</th>';
  html += '<th class="p-2">'+t('col_notes','Notes')+'</th>';
  html += '</tr></thead><tbody>';

  var lastCustomer = '';
  var customerMrr = 0;

  renewals.forEach(function(r, i) {
    var daysLeft = r.days_left;
    var daysColor = daysLeft === null ? 'var(--text-dim)' : daysLeft < 0 ? 'var(--red)' : daysLeft <= 30 ? 'var(--red)' : daysLeft <= 60 ? 'var(--orange)' : 'var(--green)';
    var daysLabel = daysLeft === null ? '-' : daysLeft < 0 ? 'UTL\u00d8PT' : Number(daysLeft) + 'd';
    var renewDate = r.contract_end ? esc(r.contract_end.slice(0,10)) : '-';

    // Customer subtotal separator
    if (r.customer_name !== lastCustomer && lastCustomer !== '' && customerMrr > 0) {
      html += '<tr class="bg-base"><td colspan="7" class="text-right text-xs fw-semibold text-muted">'+esc(lastCustomer)+' MRR:</td><td class="text-right fw-bold font-mono text-xs">'+customerMrr.toFixed(2)+'</td><td colspan="4"></td></tr>';
      customerMrr = 0;
    }
    lastCustomer = r.customer_name;
    customerMrr += (r.monthly_cost || 0);

    html += '<tr' + (r.handled ? ' class="row-success opacity-60"' : '') + '>';
    html += '<td class="text-center"><input type="checkbox" class="renewal-cb checkbox" data-id="'+Number(r.id)+'" '+(r.handled?'checked':'')+' data-change-handler="alsoToggleHandled"></td>';
    html += '<td class="fw-medium">'+esc(r.customer_name)+'</td>';
    html += '<td>'+esc(r.service_display)+'</td>';
    html += '<td class="text-muted">'+esc(r.vendor)+'</td>';

    var term = r.term || '-';
    var termLabel = term === 'Monthly' ? t('term_monthly','Monthly') : term === 'Annual' ? t('term_annual','Annual') : term === 'Quarterly' ? t('term_quarterly','Quarterly') : term;
    var termIcon = term === 'Monthly' ? '\ud83d\udd04' : term === 'Annual' ? '\ud83d\udcc6' : term === 'Quarterly' ? '\ud83d\udcc5' : term.indexOf('Year') !== -1 ? '\ud83d\udcc6' : '';
    var termColor = term === 'Monthly' ? 'var(--blue)' : term === 'Annual' ? 'var(--purple)' : 'var(--text-muted)';
    html += '<td class="text-center text-xs"><span class="' + toneClass(termColor) + ' fw-semibold">'+termIcon+' '+esc(termLabel)+'</span></td>';

    // Qty / Price / Monthly — show dash if not yet cached
    var qty = Number(r.quantity) || 0;
    var price = r.unit_price || 0;
    var monthly = r.monthly_cost || 0;
    html += '<td class="text-center fw-semibold">'+(qty > 0 ? qty : '<span class="text-dim">-</span>')+'</td>';
    html += '<td class="text-right font-mono text-xs">'+(price > 0 ? price.toFixed(2) : '<span class="text-dim">-</span>')+'</td>';
    html += '<td class="text-right font-mono fw-semibold">'+(monthly > 0 ? monthly.toFixed(2) : '<span class="text-dim">-</span>')+'</td>';

    html += '<td class="text-center text-xs">'+renewDate+'</td>';
    html += '<td class="text-center fw-bold ' + toneClass(daysColor) + '">'+daysLabel+'</td>';

    var stColor = r.account_state === 'Active' ? 'var(--green)' : 'var(--orange)';
    html += '<td class="text-center"><span class="text-2xs ' + toneClass(stColor) + ' fw-semibold">'+esc(r.account_state)+'</span></td>';

    html += '<td><input type="text" value="'+esc(r.notes||'')+'" placeholder="'+t('lbl_add_note','Add note...')+'" data-change-handler="alsoSaveNote" data-id="'+Number(r.id)+'" class="field-input field-input-sm"></td>';
    html += '</tr>';
  });

  // Final customer subtotal
  if (lastCustomer && customerMrr > 0) {
    html += '<tr class="bg-base"><td colspan="7" class="text-right text-xs fw-semibold text-muted">'+esc(lastCustomer)+' MRR:</td><td class="text-right fw-bold font-mono text-xs">'+customerMrr.toFixed(2)+'</td><td colspan="4"></td></tr>';
  }

  html += '</tbody></table></div>';

  // Uniweb renewals placeholder
  html += '<div id="dash-uniweb-renewals" class="mt-4"><div class="loader mx-auto my-4"></div></div>';

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

  // The AR money view rides alongside the renewals, as a sibling above them so
  // rebuilding the renewals list never wipes it. Admin-only, loaded in parallel.
  _loadUniwebMoney();

  try {
    var data = await apiFetch('/api/uniweb/alerts?days=365');
    if (!data || !data.items || data.items.length === 0) {
      container.innerHTML = '<div class="card p-6 text-center text-success">'
        + '<div class="text-2xl mb-2">&#10003;</div>'
        + '<div class="text-ui fw-semibold">'+t('msg_no_uniweb_renewals','Ingen Uniweb-fornyelser')+'</div>'
        + '<div class="text-sm text-muted">'+t('msg_no_uniweb_renewals_hint','Ingen domener, abonnementer eller SSL-sertifikater utløper innen ett år.')+'</div>'
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
    html += '<div class="grid grid-cols-5 gap-3 mb-4">';
    var kpis = [
      {label:t('kpi_cached','Totalt'), value:Number(data.total), color:'var(--blue)'},
      {label:t('kpi_expired','Utløpt/Kritisk')+ ' (<7d)', value:kritisk.length, color:kritisk.length>0?'var(--red)':'var(--text-dim)'},
      {label:t('kpi_30d','< 30 dager'), value:snart.length, color:snart.length>0?'var(--orange)':'var(--text-dim)'},
      {label:'30-90 '+t('col_days','dager'), value:kommende.length, color:kommende.length>0?'#c9a800':'var(--text-dim)'},
      {label:'90-365 '+t('col_days','dager'), value:langt.length, color:langt.length>0?'var(--green)':'var(--text-dim)'},
    ];
    kpis.forEach(function(k) {
      html += '<div class="card kpi-card ' + toneVar(k.color) + '">';
      html += '<div class="kpi-value ' + toneClass(k.color) + '">'+k.value+'</div>';
      html += '<div class="kpi-label">'+k.label+'</div>';
      html += '</div>';
    });
    html += '</div>';

    // Section header
    html += '<div class="flex items-center justify-between mb-3">';
    html += '<div class="text-base fw-semibold text-default">' + t('also_uniweb_renewals','Uniweb-fornyelser') + '</div>';
    html += '<button class="btn btn-ghost btn-sm" data-click-handler="_loadUniwebRenewals">' + t('also_refresh','Oppdater') + '</button>';
    html += '</div>';

    // Render each urgency group. The items stay out of the style table so
    // the table holds only our own constants.
    var groups = [
      {label:'Kritisk', subtitle:t('also_exp_7d','Utløper innen 7 dager'), color:'var(--red)'},
      {label:'Snart', subtitle:t('also_exp_30d','Utløper innen 30 dager'), color:'var(--orange)'},
      {label:'Kommende', subtitle:t('also_exp_90d','Utløper innen 90 dager'), color:'#c9a800'},
      {label:'Langsiktig', subtitle:t('also_exp_365d','90–365 dager'), color:'var(--green)'},
    ];
    var groupItems = [kritisk, snart, kommende, langt];

    groups.forEach(function(g, gi) {
      var gItems = groupItems[gi];
      if (gItems.length === 0) return;

      html += '<div class="card p-0 overflow-hidden mb-3 edge-tone ' + toneVar(g.color) + '">';
      html += '<div class="group-head">';
      html += '<div><span class="text-ui fw-bold ' + toneClass(g.color) + '">'+g.label+'</span>';
      html += '<span class="text-xs text-muted ml-2">'+g.subtitle+'</span></div>';
      html += '<span class="text-sm fw-semibold ' + toneClass(g.color) + '">'+gItems.length+' element'+(gItems.length!==1?'er':'')+'</span>';
      html += '</div>';

      html += '<table class="data-table">';
      html += '<thead><tr>';
      html += '<th class="py-2 px-3">' + t('also_col_customer','Kunde') + '</th>';
      html += '<th class="py-2 px-3">' + t('also_col_type','Type') + '</th>';
      html += '<th class="py-2 px-3">' + t('also_col_name','Navn') + '</th>';
      html += '<th class="text-center py-2 px-3">' + t('also_col_expiry','Utløpsdato') + '</th>';
      html += '<th class="text-center py-2 px-3">' + t('also_col_days_left','Dager igjen') + '</th>';
      html += '</tr></thead><tbody>';

      gItems.forEach(function(item, idx) {
        var daysColor = item.days_remaining < 0 ? 'var(--red)' : item.days_remaining < 7 ? 'var(--red)' : item.days_remaining < 14 ? 'var(--orange)' : '#c9a800';
        var daysLabel = item.days_remaining < 0 ? 'UTLOPT' : Number(item.days_remaining) + 'd';

        html += '<tr>';
        html += '<td class="fw-medium">'+esc(item.customer_name)+'</td>';
        html += '<td><span class="text-2xs fw-semibold py-0-5 px-2 rounded-full text-muted">'+esc(typeLabels[item.type] || item.type)+'</span></td>';
        html += '<td>'+esc(item.item_name)+'</td>';
        html += '<td class="text-center text-xs font-mono">'+esc(item.expiry_date)+'</td>';
        html += '<td class="text-center fw-bold ' + toneClass(daysColor) + '">'+daysLabel+'</td>';
        html += '</tr>';
      });

      html += '</tbody></table></div>';
    });

    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = '<div class="card p-4 text-center text-muted text-sm">' + t('also_uniweb_load_failed','Kunne ikke laste Uniweb-fornyelser. Sjekk at Uniweb er konfigurert.') + '</div>';
  }
}


// ═══════════════════════════════════════════════════════════════════
// UNIWEB FAKTURAER / UTESTÅENDE (AR – money view, admin only)
// ═══════════════════════════════════════════════════════════════════

function _uwKr(n) {
  return (Number(n) || 0).toLocaleString('nb-NO', {minimumFractionDigits: 0, maximumFractionDigits: 0}) + ' kr';
}

async function _loadUniwebMoney() {
  var anchor = document.getElementById('dash-uniweb-renewals');
  if (!anchor) return;

  // Partner-wide receivables are an admin view — the route is admin-only, so a
  // non-admin would only get a 403. Don't render the card for them at all.
  var isAdmin = _currentUser && _currentUser.role === 'admin';
  var card = document.getElementById('uniweb-ar-card');
  if (!isAdmin) { if (card) card.remove(); return; }

  if (!card) {
    anchor.insertAdjacentHTML('beforebegin',
      '<div id="uniweb-ar-card" class="uwar-card"><div class="uwar-loading"><div class="loader"></div></div></div>');
    card = document.getElementById('uniweb-ar-card');
  }

  try {
    var data = await apiFetch('/api/uniweb/partner/orders');
    card.innerHTML = _renderUniwebAr(data);
  } catch (e) {
    card.innerHTML = '<div class="card uwar-msg">'
      + t('uniweb_ar_failed', 'Kunne ikke laste faktura-oversikten. Sjekk at Uniweb er konfigurert.') + '</div>';
  }
}

// Rendered entirely on .uwar-* classes in app.css — no inline styles, so the
// CSP inline-style budget does not grow (see test_frontend_csp_budget).
// The partner-wide card = header (with the whole-partner refresh) + shared body.
function _renderUniwebAr(data) {
  var head = '<div class="uwar-head"><div class="uwar-title">' + t('uniweb_ar_title', 'Uniweb – utestående fakturaer') + '</div>'
    + '<button class="btn btn-ghost btn-sm" data-click-handler="_loadUniwebMoney">' + t('also_refresh', 'Oppdater') + '</button></div>';
  return head + _uwArBody(data);
}

// KPIs + aging + open-invoice table — shared by the partner card and the
// per-customer section in the Hub (app.js), so both render identically.
export function _uwArBody(data) {
  data = data || {};
  var aging = data.aging || {};
  var invoices = data.invoices || [];
  var overdueTotal = Number(data.overdue_total) || 0;
  var overdueCount = Number(data.overdue_count) || 0;

  // KPI row
  var html = '<div class="uwar-kpis">';
  var kpis = [
    {label: t('uniweb_ar_outstanding', 'Utestående'), value: _uwKr(data.total_outstanding), cls: 'uwar-blue'},
    {label: t('uniweb_ar_overdue', 'Forfalt'), value: _uwKr(overdueTotal), cls: overdueTotal > 0 ? 'uwar-red' : 'uwar-dim'},
    {label: t('uniweb_ar_open', 'Åpne fakturaer'), value: (Number(data.open_count) || 0), cls: ''},
    {label: t('uniweb_ar_overdue_count', 'Forfalte'), value: overdueCount, cls: overdueCount > 0 ? 'uwar-red' : 'uwar-dim'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="uwar-kpi ' + k.cls + '"><div class="uwar-kpi-val">' + k.value + '</div><div class="uwar-kpi-lbl">' + k.label + '</div></div>';
  });
  html += '</div>';

  // Aging buckets — the modifier class is applied only when the bucket has money in it
  var buckets = [
    {key: 'current', label: t('uniweb_ar_current', 'Ikke forfalt'), cls: 'uwar-a-green'},
    {key: 'd1_30', label: '1-30 ' + t('col_days', 'dager'), cls: 'uwar-a-amber'},
    {key: 'd31_60', label: '31-60 ' + t('col_days', 'dager'), cls: 'uwar-a-orange'},
    {key: 'd61_90', label: '61-90 ' + t('col_days', 'dager'), cls: 'uwar-a-orange'},
    {key: 'd90_plus', label: '90+ ' + t('col_days', 'dager'), cls: 'uwar-a-red'},
  ];
  html += '<div class="uwar-aging">';
  buckets.forEach(function(b) {
    var v = Number(aging[b.key]) || 0;
    html += '<div class="uwar-age ' + (v > 0 ? b.cls : '') + '"><div class="uwar-age-val">' + _uwKr(v) + '</div><div class="uwar-age-lbl">' + b.label + '</div></div>';
  });
  html += '</div>';

  // Open invoices, or a clean "nothing owed" state
  if (invoices.length === 0) {
    html += '<div class="card uwar-none"><div class="uwar-none-ico">&#10003;</div>'
      + '<div class="uwar-none-txt">' + t('uniweb_ar_none', 'Ingen utestående fakturaer') + '</div></div>';
    return html;
  }

  html += '<div class="card uwar-panel"><table class="uwar-tbl"><thead><tr>';
  html += '<th>' + t('uniweb_ar_invoice', 'Faktura') + '</th>';
  html += '<th>' + t('also_col_customer', 'Kunde') + '</th>';
  html += '<th class="uwar-c">' + t('uniweb_ar_due', 'Forfall') + '</th>';
  html += '<th class="uwar-r">' + t('uniweb_ar_amount', 'Beløp') + '</th>';
  html += '<th class="uwar-r">' + t('uniweb_ar_outstanding_col', 'Utestående') + '</th>';
  html += '<th class="uwar-c">' + t('uniweb_ar_overdue_col', 'Forfalt') + '</th>';
  html += '</tr></thead><tbody>';
  invoices.forEach(function(inv) {
    var od = Number(inv.days_overdue) || 0;
    var odCls = od <= 0 ? 'uwar-od-none' : od <= 30 ? 'uwar-od-amber' : od <= 90 ? 'uwar-od-orange' : 'uwar-od-red';
    var odLabel = od <= 0 ? '—' : od + 'd';
    var invNo = inv.invoiceNo || inv.externalInvoiceNo || inv.id || '';
    html += '<tr>';
    html += '<td class="uwar-mono">' + esc(String(invNo)) + '</td>';
    html += '<td>' + esc(inv.customer_name || '—') + '</td>';
    html += '<td class="uwar-c uwar-mono">' + esc(inv.invoiceDue || '—') + '</td>';
    html += '<td class="uwar-r uwar-mono">' + _uwKr(inv.invoiceSum) + '</td>';
    html += '<td class="uwar-r uwar-mono uwar-strong">' + _uwKr(inv.outstanding) + '</td>';
    html += '<td class="uwar-c ' + odCls + '">' + odLabel + '</td>';
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  return html;
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
    promises.push(apiFetch('/api/also/renewals/' + encodeURIComponent(cb.dataset.id) + '/handle', {
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
  await apiFetch('/api/also/renewals/' + encodeURIComponent(renewalId) + '/handle', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({handled: handled ? 1 : 0})
  });
}

// The endpoint stores the handled flag with the note, so send the row's
// checkbox as it stands. This used to test whether an input with this id in
// its onchange attribute existed, which was always true, so saving a note
// marked the renewal handled; with no onchange attributes left it would have
// marked every one unhandled instead.
async function alsoSaveNote(renewalId, notes) {
  var handledBox = document.querySelector('.renewal-cb[data-id="' + Number(renewalId) + '"]');
  await apiFetch('/api/also/renewals/' + encodeURIComponent(renewalId) + '/handle', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({handled: handledBox && handledBox.checked ? 1 : 0, notes: notes})
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
  msg.innerHTML = '<div class="mt-1">'
    + '<div class="flex items-center gap-2 mb-1">'
    + '<div class="bar flex-1">'
    + '<div id="renewal-scan-bar" class="bar-fill"></div></div>'
    + '<span id="renewal-scan-pct" class="bar-pct">0%</span></div>'
    + '<div id="renewal-scan-detail" class="text-xs text-dim">' + t('also_starting','Starter ...') + '</div></div>';

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
    var remaining = Number(d.remaining) || 0;
    var bar = document.getElementById('renewal-scan-bar');
    if (bar) bar.style.width = '100%';

    if (remaining > 0) {
      btn.textContent = t('also_scan_next_batch','Skann neste batch') + ' (' + remaining + ' ' + t('also_remaining','gjenstår') + ')';
      msg.innerHTML = '<span class="text-success">\u2713 ' + t('also_scanned','Skannet') + ' '+Number(d.scanned)+' \u00b7 '+Number(d.already_cached)+' ' + t('also_already_cached','allerede bufret') + ' \u00b7 '+remaining+' ' + t('also_remaining','gjenstår')+(d.errors?' \u00b7 <span class="text-warning">'+Number(d.errors)+' ' + t('also_errors','feil') + '</span>':'')+'</span>';
    } else {
      btn.textContent = t('btn_sync','Sync');
      msg.innerHTML = '<span class="text-success">\u2713 ' + t('also_all','Alle') + ' '+Number(d.total_linked)+' ' + t('also_customers_cached','kunder ferdig bufret') + '</span>';
    }
    return d;
  } else {
    btn.textContent = t('btn_sync','Sync');
    msg.innerHTML = '<span class="text-danger">' + esc(d && d.error || 'Skanning feilet') + '</span>';
    return null;
  }
}

async function alsoRefreshApiStats() {
  var el = document.getElementById('also-api-stats');
  if (!el) return;
  var s = await apiFetch('/api/also/api-stats');
  if (!s || !s.total_calls) { el.textContent = t('msg_api_zero_calls','API: 0 calls'); return; }
  el.innerHTML = 'API: <strong>'+Number(s.total_calls)+'</strong> kall \u00b7 '+Number(s.last_1min)+'/min \u00b7 '+Number(s.last_5min)+'/5min \u00b7 snitt '+Number(s.avg_response_ms)+'ms'
    + (s.errors > 0 ? ' \u00b7 <span class="text-danger">'+Number(s.errors)+' ' + t('also_errors','feil') + '</span>' : '');
}

var _priceScanTimer = null;

// Leaving the view stops both scans' progress polling.
export function stopAlsoScans() {
  if (_renewalScanTimer) { clearInterval(_renewalScanTimer); _renewalScanTimer = null; }
  if (_priceScanTimer) { clearInterval(_priceScanTimer); _priceScanTimer = null; }
}

async function alsoPriceScan() {
  var btn = document.getElementById('renewal-scan-btn');
  var msg = document.getElementById('renewal-scan-msg');
  btn.disabled = true;
  btn.textContent = t('also_fetching_prices','Henter priser ...');

  msg.innerHTML = '<div class="mt-1">'
    + '<div class="flex items-center gap-2 mb-1">'
    + '<div class="bar flex-1">'
    + '<div id="price-scan-bar" class="bar-fill is-success"></div></div>'
    + '<span id="price-scan-pct" class="bar-pct">0%</span></div>'
    + '<div id="price-scan-detail" class="text-xs text-dim">' + t('also_fetching_prices','Henter priser ...') + '</div></div>';

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
    var remaining = Number(d.remaining) || 0;
    var bar = document.getElementById('price-scan-bar');
    if (bar) bar.style.width = '100%';

    if (remaining > 0) {
      btn.textContent = t('also_next_price_batch','Neste prisbatch') + ' (' + remaining + ' ' + t('also_remaining','gjenstår') + ')';
      msg.innerHTML = '<span class="text-success">\u2713 ' + t('also_priced','Priset') + ' '+Number(d.scanned)+' ' + t('also_subscriptions_lc','abonnementer') + ' \u00b7 '+remaining+' ' + t('also_remaining','gjenstår')+(d.errors?' \u00b7 <span class="text-warning">'+Number(d.errors)+' ' + t('also_errors','feil') + '</span>':'')+'</span>';
    } else {
      btn.textContent = t('btn_sync','Sync');
      msg.innerHTML = '<span class="text-success">\u2713 ' + t('also_all_priced','Alle abonnementer priset') + '</span>';
    }
    return d;
  } else {
    btn.textContent = t('btn_sync','Sync');
    msg.innerHTML = '<span class="text-danger">' + esc(d && d.error || 'Prisskanning feilet') + '</span>';
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
    msg.innerHTML = '<span class="text-success">\u2713</span>';
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

async function alsoShowLicenseOptimization() {
  var el = document.getElementById('dash-renewals-content');
  el.innerHTML = '<div class="loader loader-md"></div>'
    + '<div class="text-center text-muted text-sm">'
    + t('lbl_loading_lic_opt','Loading license optimization...') + '</div>';

  var data = await apiFetch('/api/also/license-optimization');
  if (!data) {
    el.innerHTML = '<div class="text-muted text-center p-6 text-sm">'
      + t('msg_lic_opt_unavailable','Could not load license optimization data') + '</div>'
      + '<div class="text-center mt-2"><button class="btn btn-ghost btn-sm" data-click-handler="dashLoadRenewals">'
      + t('btn_back_renewals','Back to renewals') + '</button></div>';
    return;
  }
  _renderLicenseOptimization(data, el);
}

function _renderLicenseOptimization(data, el) {
  var s = data.summary || {};
  var customers = data.customers || [];
  var cur = esc(s.currency || 'NOK');
  var html = '';

  // ── Header + back button ──
  html += '<div class="flex items-center justify-between mb-4">';
  html += '<div class="text-md fw-bold">'+t('hdr_license_opt','License Optimization')+'</div>';
  html += '<button class="btn btn-ghost btn-sm" data-click-handler="dashLoadRenewals">'
    + t('btn_back_renewals','Back to renewals') + '</button>';
  html += '</div>';

  // ── KPI row ──
  html += '<div class="grid grid-auto-sm gap-3 mb-4">';
  var kpis = [
    {label:t('kpi_total_waste','Total waste/mo'), value:s.total_waste > 0 ? s.total_waste.toFixed(0)+' '+cur : '0 '+cur, color:s.total_waste>0?'var(--red)':'var(--green)'},
    {label:t('kpi_over_licensed','Over-licensed'),  value:Number(s.over_licensed_count),  color:s.over_licensed_count>0?'var(--orange)':'var(--text-dim)'},
    {label:t('kpi_under_licensed','Under-licensed'), value:Number(s.under_licensed_count), color:s.under_licensed_count>0?'var(--red)':'var(--text-dim)'},
    {label:t('kpi_optimal','Optimal'),              value:Number(s.optimal_count),        color:s.optimal_count>0?'var(--green)':'var(--text-dim)'},
  ];
  kpis.forEach(function(k) {
    html += '<div class="card kpi-card ' + toneVar(k.color) + '">';
    html += '<div class="kpi-value ' + toneClass(k.color) + '">'+k.value+'</div>';
    html += '<div class="kpi-label">'+k.label+'</div>';
    html += '</div>';
  });
  html += '</div>';

  if (customers.length === 0) {
    html += '<div class="card empty-note is-compact">';
    html += '<div class="text-base fw-semibold mb-1">'+t('msg_no_lic_opt','No license optimization data')+'</div>';
    html += '<div class="text-sm">'+t('msg_no_lic_opt_hint','Run audit on ALSO-linked customers and sync subscriptions first.')+'</div>';
    html += '</div>';
    el.innerHTML = html;
    return;
  }

  // ── Per-customer cards ──
  customers.forEach(function(c) {
    var wasteColor = c.total_monthly_waste > 0 ? 'var(--red)' : 'var(--green)';
    var borderColor = c.total_monthly_waste > 500 ? 'var(--red)' : c.total_monthly_waste > 0 ? 'var(--orange)' : 'var(--green)';

    html += '<div class="card p-0 overflow-hidden mb-3 edge-tone ' + toneVar(borderColor) + '">';

    // Customer header
    html += '<div class="py-3 px-4 border-b flex items-center justify-between">';
    html += '<div class="text-ui fw-bold">'+esc(c.customer_name)+'</div>';
    html += '<div class="flex gap-4 text-xs">';
    html += '<span class="text-muted">'+t('lbl_paid','Paid')+': <strong>'+Number(c.total_paid)+'</strong></span>';
    html += '<span class="text-muted">'+t('lbl_assigned','Assigned')+': <strong>'+Number(c.total_assigned)+'</strong></span>';
    if (c.total_monthly_waste > 0) {
      html += '<span class="' + toneClass(wasteColor) + ' fw-bold">'+t('lbl_waste','Waste')+': '+c.total_monthly_waste.toFixed(0)+' '+cur+'/'+t('lbl_mo','mo')+'</span>';
    }
    if (!c.has_audit_data) {
      html += '<span class="text-warning text-2xs">'+t('lbl_no_audit','No audit data')+'</span>';
    }
    html += '</div></div>';

    // License table
    if (c.licenses.length > 0) {
      html += '<table class="data-table">';
      html += '<thead><tr class="bg-base">';
      html += '<th class="py-2 px-3">'+t('col_product','Product')+'</th>';
      html += '<th class="text-center py-2 px-3">'+t('col_paid_qty','Paid')+'</th>';
      html += '<th class="text-center py-2 px-3">'+t('col_assigned_qty','Assigned')+'</th>';
      html += '<th class="text-center py-2 px-3">'+t('col_excess','Excess')+'</th>';
      html += '<th class="text-center py-2 px-3">'+t('col_lic_status','Status')+'</th>';
      html += '<th class="text-right py-2 px-3">'+t('col_unit_price','Unit price')+'</th>';
      html += '<th class="text-right py-2 px-3">'+t('col_monthly_waste','Waste/mo')+'</th>';
      html += '</tr></thead><tbody>';

      c.licenses.forEach(function(lic, idx) {
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
            statusColor = 'var(--text-muted)'; statusLabel = esc(lic.status); break;
        }

        html += '<tr>';
        html += '<td class="fw-medium">'+esc(lic.product)+'</td>';
        html += '<td class="text-center fw-semibold">'+Number(lic.paid_qty)+'</td>';
        html += '<td class="text-center fw-semibold">'+(lic.assigned_qty > 0 ? Number(lic.assigned_qty) : '<span class="text-dim">-</span>')+'</td>';
        html += '<td class="text-center fw-bold '+toneClass(lic.excess > 0 ? statusColor : 'var(--text-dim)')+'">'+(lic.excess > 0 ? (lic.status === 'under_licensed' ? '+' : '')+Number(lic.excess) : '-')+'</td>';
        html += '<td class="text-center"><span class="text-2xs fw-semibold py-0-5 px-2 rounded-full ' + toneClass(statusColor) + '">'+statusLabel+'</span></td>';
        html += '<td class="text-right font-mono text-xs">'+(lic.unit_price > 0 ? lic.unit_price.toFixed(2) : '-')+'</td>';
        html += '<td class="text-right font-mono fw-bold '+(lic.monthly_waste > 0 ? 'text-danger' : 'text-dim')+'">'+(lic.monthly_waste > 0 ? lic.monthly_waste.toFixed(2) : '-')+'</td>';
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
