// The audit runs independently of the customer page. The entry wires its presenter.
var _auditPresentation = null;
export function configureAuditPresentation(actions) {
  if (_auditPresentation) throw new Error('Audit presentation is already configured');
  ['custAuditTabOpen', 'custPageAuditFinished', 'custReportFromRun', 'custSyncReportButton', 'setCustReportRun', 'setCustRuns'].forEach(function(name) { if (typeof actions[name] !== 'function') throw new Error('Missing audit presentation: ' + name); });
  _auditPresentation = Object.freeze(actions);
}
export function presentCustAuditTabOpen(...args) { if (!_auditPresentation) throw new Error('Audit presentation is not configured'); return _auditPresentation.custAuditTabOpen(...args); }
export function presentCustPageAuditFinished(...args) { if (!_auditPresentation) throw new Error('Audit presentation is not configured'); return _auditPresentation.custPageAuditFinished(...args); }
export function presentCustReportFromRun(...args) { if (!_auditPresentation) throw new Error('Audit presentation is not configured'); return _auditPresentation.custReportFromRun(...args); }
export function presentCustSyncReportButton(...args) { if (!_auditPresentation) throw new Error('Audit presentation is not configured'); return _auditPresentation.custSyncReportButton(...args); }
export function presentSetCustReportRun(...args) { if (!_auditPresentation) throw new Error('Audit presentation is not configured'); return _auditPresentation.setCustReportRun(...args); }
export function presentSetCustRuns(...args) { if (!_auditPresentation) throw new Error('Audit presentation is not configured'); return _auditPresentation.setCustRuns(...args); }
