// ═══════════════════════════════════════════════════════════════════
// FORMATTING: figures, run names, dates and sizes as a person reads them
// ═══════════════════════════════════════════════════════════════════

import {_lang, t} from './app-i18n.js';

// A metric that was never measured is null, not undefined — SQLite NULL comes
// through JSON as null, and `null !== undefined` is true. Every guard here
// used that test, so an unmeasured figure reached .toFixed and threw "Cannot
// read properties of null". That became reachable the moment sections started
// reporting "not measured" instead of a zero, which is the whole point of
// them: intune_compliance_pct is null on any tenant without Intune.
export function metricPct(value, digits) {
  if (value === null || value === undefined || value === '' || isNaN(value)) return null;
  return Number(value).toFixed(digits === undefined ? 0 : digits);
}

// The same rule for counts. A run that did not count users without MFA has
// no such key in its metrics, and `Number(undefined) || 0` turned that into a
// reassuring zero printed right under a finding about an admin without MFA.
// Unmeasured reads "ukjent" on every card that shows the figure.
export function metricKnown(value) {
  return !(value === null || value === undefined || value === '' || isNaN(value));
}
export function metricCount(value) {
  return metricKnown(value) ? String(Number(value)) : t('lbl_unknown_value', 'ukjent');
}

// Run folders are named "YYYY-MM-DD_HHMMSS" (older ones "YYYY-MM-DD_HHMM",
// some with a suffix after). That name is for the file system; a person reads
// the date and time. Returns the input unchanged when it is not a run name.
// `short` gives the date alone in a compact form, for tables and lists.
export function formatRunName(name, short) {
  var m = /^(\d{4})-(\d{2})-(\d{2})(?:[_T ](\d{2}):?(\d{2}))?/.exec(String(name || ''));
  if (!m) return String(name || '');
  var locale = _lang === 'en' ? 'en-GB' : 'nb-NO';
  var date = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  if (isNaN(date.getTime())) return String(name);
  if (short) return date.toLocaleDateString(locale, {day: 'numeric', month: 'short', year: 'numeric'});
  var day = date.toLocaleDateString(locale, {day: 'numeric', month: 'long', year: 'numeric'});
  if (!m[4]) return day;
  return t('fmt_run_date_time', '{date} kl. {time}').replace('{date}', day).replace('{time}', m[4] + ':' + m[5]);
}

export function timeAgo(dateStr) {
  if (!dateStr) return '';
  try {
    var d = new Date(dateStr);
    var now = Date.now();
    var diff = Math.floor((now - d.getTime()) / 1000);
    if (diff < 60) return t('time_just_now','just now');
    if (diff < 3600) return Math.floor(diff/60) + ' ' + t('time_min_ago','min ago');
    if (diff < 86400) return Math.floor(diff/3600) + ' ' + t('time_hours_ago','hours ago');
    if (diff < 604800) return Math.floor(diff/86400) + ' ' + t('time_days_ago','days ago');
    return d.toLocaleDateString(_lang === 'en' ? 'en-GB' : 'nb-NO', {day:'2-digit',month:'short'});
  } catch(e) { return dateStr; }
}

// app-customer-detail.js used to declare a second _formatBytes; this is the
// one kept.
export function _formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  var units = ['B','KB','MB','GB','TB'];
  var i = Math.floor(Math.log(bytes) / Math.log(1024));
  if (i >= units.length) i = units.length - 1;
  return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
}

// ── Tones ───────────────────────────────────────────────────────────────────
// Many scripts still decide a colour by its token ('var(--green)') or by the
// hex value of one. The markup takes the class that paints it, never a style
// attribute: toneClass gives the text colour (a .dot takes it too, it is
// drawn in currentColor), badgeClass the tinted badge for the same meaning.
var _TONES = {
  'var(--green)': 'success', 'var(--green-deep)': 'success', 'var(--color-success)': 'success', '#3fb950': 'success',
  'var(--red)': 'danger', 'var(--red-deep)': 'danger', 'var(--red-btn)': 'danger', 'var(--color-danger)': 'danger',
  '#f85149': 'danger', '#8b0000': 'danger', '#d0021b': 'danger',
  'var(--orange)': 'warning', 'var(--orange-deep)': 'warning', 'var(--color-warning)': 'warning',
  '#d29922': 'warning', '#e67e22': 'warning', '#f5a623': 'warning', '#eab308': 'warning', '#c9a800': 'warning',
  'var(--blue)': 'accent', 'var(--blue-deep)': 'accent', '#4d9fb5': 'accent',
  'var(--info)': 'info', 'var(--color-info)': 'info',
  'var(--purple)': 'purple', '#7c5cfc': 'purple',
  'var(--text)': 'default', 'var(--text-muted)': 'muted', 'var(--text-dim)': 'dim', '#888': 'dim'
};
export function toneName(color) { return _TONES[String(color || '').trim()] || ''; }
export function toneClass(color) {
  var name = toneName(color);
  return name ? 'text-' + name : '';
}
// The tone as a custom property (--tone) for a component that draws an edge
// or a fill in it: .kpi-card's top edge.
export function toneVar(color) {
  if (String(color || '').trim() === 'var(--border)') return 'tone-border';
  return 'tone-' + (toneName(color) || 'dim');
}
export function badgeClass(color) {
  var name = toneName(color);
  var badge = {success: 'badge-success', danger: 'badge-danger', warning: 'badge-warning',
    accent: 'badge-info', info: 'badge-info', purple: 'badge-purple'}[name];
  return 'badge' + (badge ? ' ' + badge : '');
}

export function _notifDays(n) {
  if (n === null || n === undefined) return '';
  return n < 0 ? t('lbl_expired', 'Utløpt') : n + ' ' + t('lbl_days_short', 'd');
}

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

export function _activityLabel(key) {
  // Named here so the used-key check sees them; the rest are found by prefix.
  var labels = {
    fortigate_save: t('activity_fortigate_save'),
    fortigate_removed: t('activity_fortigate_removed'),
    fortigate_bootstrapped: t('activity_fortigate_bootstrapped'),
    fortigate_key_deployed: t('activity_fortigate_key_deployed'),
    fortigate_token_generated: t('activity_fortigate_token_generated'),
  };
  if (labels[key]) return labels[key];
  return t('activity_' + key, key.replace(/_/g, ' '));
}

export function _taskSchedLabel(task) {
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

export function _reason(prefix, code, params) {
  var out = t(prefix + code, '');
  if (!out) return '';
  Object.keys(params || {}).forEach(function(k) {
    // A run is named to a person by its date, not its folder.
    out = out.split('{' + k + '}').join(String(k === 'run' ? formatRunName(params[k]) : params[k]));
  });
  return out;
}

var _BASELINE_SECTIONS = ['mfa', 'admin_roles', 'ca', 'secure_score', 'entra_devices', 'intune',
  'exchange', 'backup_coverage', 'sharepoint', 'usage'];

function _baselineValue(v) {
  if (v === true) return t('lbl_yes', 'Ja');
  if (v === false) return t('lbl_no', 'Nei');
  if (v === null || v === undefined) return t('lbl_unknown_value', 'ukjent');
  return String(v);
}

export function baselineReason(c) {
  var p = c.params || {};
  var code = c.reason_code;
  if (code === 'guard_unset') {
    var section = String(p.guard || '').split('.')[0];
    if (section === 'drift') return t('bl_guard_unset_drift', 'Ikke vurdert: det finnes ingen tidligere kjøring å sammenligne policyene med.');
    var name = _BASELINE_SECTIONS.indexOf(section) >= 0
      ? t('bl_section_' + section, '') : '';
    return t('bl_guard_unset', 'Ikke vurdert: {section} ble ikke samlet inn i denne kjøringen.')
      .replace('{section}', name || t('bl_section_unknown', 'grunnlaget for dette kravet'));
  }
  if (!code) return '';
  var out = t('bl_' + code, '');
  return out
    .split('{actual}').join(_baselineValue(p.actual))
    .split('{expected}').join(_baselineValue(p.expected))
    .split('{op}').join(String(p.op || ''));
}
