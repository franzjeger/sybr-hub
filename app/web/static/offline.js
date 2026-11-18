// The offline page's script (offline.html), a module of its own: it imports
// nothing and shares nothing with the interface.
//
// The worker shows this page in two cases: the browser has no network, or it
// has one and the hub does not answer (a proxy's 502, 503 or 504 while the
// hub restarts, or no answer at all). The second is not "you are offline",
// so the page says which, and that it comes back on its own.
//
// The strings live here, not in ui_i18n.json: when this page shows, the hub
// may not answer a request for them. Norwegian is the default, as in the
// interface; the language is the one the interface stored (ui_lang).

var STRINGS = {
  no: {
    offline: {
      doc: 'Frakoblet: Sybr HUB',
      title: 'Du er offline',
      text: 'Sybr HUB krever kontakt med serveren for å vise live data. Siden vil prøve å laste på nytt når nettverket er tilbake.',
      status: 'Venter på forbindelse…',
    },
    unreachable: {
      doc: 'Huben svarer ikke: Sybr HUB',
      title: 'Huben svarer ikke',
      text: 'Sybr HUB svarer ikke akkurat nå, kanskje fordi den starter på nytt. Siden laster seg selv inn igjen så snart huben svarer.',
      status: 'Venter på svar fra huben…',
    },
    retry: 'Prøv igjen',
  },
  en: {
    offline: {
      doc: 'Offline: Sybr HUB',
      title: 'You are offline',
      text: 'Sybr HUB needs a connection to the server to show live data. The page will reload when the network is back.',
      status: 'Waiting for a connection…',
    },
    unreachable: {
      doc: 'Not answering: Sybr HUB',
      title: 'The hub is not answering',
      text: 'Sybr HUB is not answering right now, perhaps because it is restarting. The page reloads on its own as soon as the hub answers.',
      status: 'Waiting for the hub to answer…',
    },
    retry: 'Try again',
  },
};

function language() {
  try {
    return localStorage.getItem('ui_lang') === 'en' ? 'en' : 'no';
  } catch (error) {
    return 'no';   // storage denied (private mode): the default
  }
}

function reload() {
  window.location.reload();
}

function setText(id, text) {
  var el = document.getElementById(id);
  if (el) el.textContent = text;
}

function paint() {
  var lang = language();
  var strings = STRINGS[lang];
  var state = navigator.onLine ? strings.unreachable : strings.offline;
  document.documentElement.lang = lang;
  document.title = state.doc;
  setText('offline-title', state.title);
  setText('offline-text', state.text);
  setText('status', state.status);
  setText('offline-retry', strings.retry);
}

var retry = document.getElementById('offline-retry');
if (retry) retry.addEventListener('click', reload);
window.addEventListener('online', reload);
window.addEventListener('online', paint);
window.addEventListener('offline', paint);
paint();

// The online event can be missed, and a restarting hub sends none, so ask
// the hub itself periodically too.
window.setInterval(function () {
  fetch('/api/health', { cache: 'no-store' })
    .then(function (response) { if (response.ok) reload(); })
    .catch(function () {});
}, 15000);
