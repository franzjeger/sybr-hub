import {_currentUser} from './app-state.js';

var _editedSettingsFields = new WeakSet();
var _settingsFieldUser = '';
function _fieldTrackingUser() {
  var id = (_currentUser && _currentUser.id) || '';
  if (id !== _settingsFieldUser) { _editedSettingsFields = new WeakSet(); _settingsFieldUser = id; }
}
['input', 'change'].forEach(function(kind) {
  document.addEventListener(kind, function(event) {
    _fieldTrackingUser();
    if (event.target && event.target.matches('input, select, textarea')) _editedSettingsFields.add(event.target);
  }, true);
});

// Background settings reads may populate an untouched field, including a
// checkbox, but never replace a value the person has already changed.
export function integrationSetField(id, value, checked) {
  _fieldTrackingUser();
  var el = document.getElementById(id);
  if (!el || _editedSettingsFields.has(el)) return;
  if (checked) el.checked = !!value;
  else el.value = value;
}


export function toggleIntegConfig(id) {
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
