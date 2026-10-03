// ═══════════════════════════════════════════════════════════════════
// UI HANDLERS: controls name a registered handler, never inline JS
// ═══════════════════════════════════════════════════════════════════

// The CSP has script-src-attr 'none': the browser runs no inline event-handler
// attribute (onclick and the rest). A control names its handler in a data
// attribute instead:
//
//   <button data-click-handler="showView" data-view="audit">…</button>
//   <select data-change-handler="setLanguage">…</select>
//
// One listener per event type, on document in the capture phase, looks the
// name up in the map below and calls it as handler(element, event). Arguments
// come from the element's own data-* attributes; an attribute is never
// evaluated, and only names registered here can be called — this is not a way
// to reach any global function from markup.
//
// Each script registers the handlers its own markup uses with
// registerUiHandlers({...}), once, at load. A name can be registered only once
// and the map is frozen when the document has loaded.
//
// Dispatch mirrors how inline handlers bubbled: from the event target outwards,
// every element with a handler for this event type runs it, until one calls
// event.stopPropagation(). Because it runs in the capture phase, that call also
// stops the document-level listeners (click-outside-to-close and the like),
// just as stopPropagation() in an inline handler did. It also stops listeners
// added with addEventListener on elements *inside* the one whose handler made
// the call, which an inline handler on that element did not: inside a
// container that stops clicks (the shared stopPropagation handler on a dialog),
// give controls data-*-handler attributes rather than their own listeners.
var UI_HANDLER_EVENTS = Object.freeze(['click', 'dblclick', 'input', 'change', 'keydown', 'submit', 'dragover', 'dragleave', 'drop']);
var _uiHandlers = Object.create(null);

function registerUiHandlers(handlers) {
  Object.keys(handlers).forEach(function(name) {
    if (Object.isFrozen(_uiHandlers)) throw new Error('UI handler registered after load: ' + name);
    if (name in _uiHandlers) throw new Error('UI handler registered twice: ' + name);
    if (typeof handlers[name] !== 'function') throw new TypeError('UI handler is not a function: ' + name);
    _uiHandlers[name] = handlers[name];
  });
}

function _dispatchUiEvent(event) {
  var attribute = 'data-' + event.type + '-handler';
  // The elements with a handler, innermost first, fixed before any handler runs
  // as the browser fixes an event's path: a handler that removes part of the
  // page does not stop the ancestors that were there from getting the event.
  var path = [];
  var node = event.target;
  if (node && node.nodeType !== 1) node = node.parentElement;
  for (; node && node.nodeType === 1; node = node.parentElement) {
    // A disabled control never ran its inline handler either.
    if (node.hasAttribute(attribute) && !node.matches(':disabled')) path.push(node);
  }
  for (var i = 0; i < path.length; i++) {
    var name = path[i].getAttribute(attribute);
    var handler = _uiHandlers[name];
    if (!handler) { console.error('No UI handler registered as "' + name + '" (' + attribute + ')'); continue; }
    // <a href="#"> with a click handler is a button that looks like a link.
    // Following the "#" would change the route; inline handlers ended in
    // `return false` for the same reason.
    if (event.type === 'click' && path[i].tagName === 'A' && path[i].getAttribute('href') === '#') event.preventDefault();
    handler(path[i], event);
    if (event.cancelBubble) break;
  }
}

UI_HANDLER_EVENTS.forEach(function(type) { document.addEventListener(type, _dispatchUiEvent, true); });
document.addEventListener('DOMContentLoaded', function() { Object.freeze(_uiHandlers); });

// Handlers shared by markup in several scripts.
registerUiHandlers({
  // data-target names an element by id.
  hideElement: function(el) { var target = document.getElementById(el.dataset.target); if (target) target.style.display = 'none'; },
  removeElement: function(el) { var target = document.getElementById(el.dataset.target); if (target) target.remove(); },
  // On a modal's backdrop: a click on the backdrop itself, not on the dialog.
  hideOnBackdrop: function(el, event) { if (event.target === el) el.style.display = 'none'; },
  removeOnBackdrop: function(el, event) { if (event.target === el) el.remove(); },
  // On a container whose clicks must not reach a clickable row or card behind it.
  stopPropagation: function(el, event) { event.stopPropagation(); },
});
