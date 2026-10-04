// Sybr HUB service worker
//
// Served from /static/sw.js and registered with scope '/' (its route sends
// Service-Worker-Allowed: /), so it controls the interface. Registered with
// the default scope, /static/, it controlled no page at all.
//
// What it does with a request from a page it controls:
//
//   /api/, /audit_data/, /guacamole/   nothing: the browser fetches them as if
//                    there were no worker. Live data, sign-in and tokens,
//                    reports decrypted per request and the RDP/VNC tunnel
//                    never touch the cache, and offline means they fail.
//   a page load      the network, every time, and the response is not kept.
//                    The shell names the asset versions, so a kept shell
//                    would hand the next deploy's browsers the old assets.
//                    When the network fails, the offline page.
//   /static/...?v=   cache first. The server versions every asset URL by
//                    content and marks a response immutable only when the
//                    version is the file's own, and only such a response is
//                    kept: a plain 200 from this origin, not reached through
//                    a redirect, with Cache-Control: immutable. An error, a
//                    sign-in page or an old version under a new URL is not.
//   other /static/   the network; the copy kept at install (the offline
//                    page's own files) when it fails.
//   anything else    nothing.
//
// CACHE_VERSION below is a placeholder and is never served as written.
// app/web/routes/frontend.py rewrites it with the live version plus a digest
// of the static assets, so a changed file purges old caches in the activate
// handler on its own. Do not hand-bump it: this file is only read directly
// when serving the raw asset in development.

const CACHE_VERSION = 'msptoolkit-vdev';
const CACHE_PREFIX = 'msptoolkit-';
const OFFLINE_PAGE = '/static/offline.html';
const PRECACHE = [OFFLINE_PAGE, '/static/offline.css', '/static/offline.js'];
const UNTOUCHED = ['/api/', '/audit_data/', '/guacamole/'];

// No skipWaiting() here. A new worker waits until the operator accepts the
// "new version" toast (the message handler below) or every tab is closed.
// Taking over on install reloaded every open tab on each deploy, which ended
// any terminal or RDP session running in them.
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) =>
      // Past the HTTP cache, so a new version stores the files as they are now.
      cache.addAll(PRECACHE.map((url) => new Request(url, { cache: 'reload' })))
    )
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    Promise.all([
      caches.keys().then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith(CACHE_PREFIX) && k !== CACHE_VERSION)
            .map((k) => caches.delete(k))
        )
      ),
      // The first worker also takes the page that installed it, so that page
      // is controlled without a reload. The page knows this is not an update.
      self.clients.claim(),
    ])
  );
});

// Accept a "skipWaiting" postMessage from the page so a new SW can take
// over without the usual reload-twice dance. The UI sends it when the
// operator clicks the "new version" toast.
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

function keepable(resp) {
  return (
    resp.status === 200 &&
    resp.type === 'basic' &&
    !resp.redirected &&
    /\bimmutable\b/.test(resp.headers.get('Cache-Control') || '')
  );
}

function cacheFirst(event) {
  const req = event.request;
  return caches.open(CACHE_VERSION).then((cache) =>
    cache.match(req).then(
      (cached) =>
        cached ||
        fetch(req).then((resp) => {
          if (keepable(resp)) event.waitUntil(cache.put(req, resp.clone()));
          return resp;
        })
    )
  );
}

function offlinePage() {
  return caches.match(OFFLINE_PAGE).then((page) => page || Response.error());
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (UNTOUCHED.some((prefix) => url.pathname.startsWith(prefix))) return;

  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(offlinePage));
    return;
  }
  if (!url.pathname.startsWith('/static/')) return;
  if (url.searchParams.has('v')) {
    event.respondWith(cacheFirst(event));
    return;
  }
  event.respondWith(
    fetch(req).catch(() => caches.match(req).then((kept) => kept || Response.error()))
  );
});
