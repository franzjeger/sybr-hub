// MSP Toolkit — service worker
//
// Strategy:
//   /api/*           network-only (MSP operators must not act on stale
//                    security audit data; offline means fail, not guess)
//   navigation (HTML) network-first, fall back to cached '/' and finally
//                    to /static/offline.html
//   /audit_data/*    network-only — reports are encrypted per-request
//                    and must not be cached by the SW
//   /guacamole/*     network-only — live RDP/VNC proxy
//   other static     cache-first with network fallback, runtime-populated
//
// Bump CACHE_VERSION on every release so old cached JS/CSS/HTML gets
// purged in the activate handler.

const CACHE_VERSION = 'msptoolkit-v1.0.0';
const PRECACHE = [
  '/',
  '/static/offline.html',
  '/static/offline.css',
  '/static/offline.js',
  '/static/ui_i18n.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(PRECACHE))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Accept a "skipWaiting" postMessage from the page so a new SW can take
// over without the usual reload-twice dance. The UI can use this when the
// user clicks an "Update available" toast.
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

function isStaticAsset(url) {
  return (
    url.pathname.startsWith('/static/') ||
    url.pathname.startsWith('/branding/') ||
    url.pathname === '/favicon.ico'
  );
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Same-origin only — never touch cross-origin CDN fetches etc.
  if (url.origin !== self.location.origin) return;

  // Never cache live/secret paths
  if (
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/audit_data/') ||
    url.pathname.startsWith('/guacamole/')
  ) {
    return; // let the browser do its normal thing
  }

  // Navigation requests (HTML page loads) — network-first with offline fallback
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((resp) => {
          // Keep '/' fresh in the cache
          if (resp.ok && (url.pathname === '/' || url.pathname === '')) {
            const clone = resp.clone();
            caches.open(CACHE_VERSION).then((c) => c.put('/', clone));
          }
          return resp;
        })
        .catch(() =>
          caches.match('/').then((r) => r || caches.match('/static/offline.html'))
        )
    );
    return;
  }

  // Static assets — cache-first, then network, then populate cache
  if (isStaticAsset(url)) {
    event.respondWith(
      caches.match(req).then((cached) =>
        cached ||
        fetch(req).then((resp) => {
          if (resp.ok && resp.type === 'basic') {
            const clone = resp.clone();
            caches.open(CACHE_VERSION).then((c) => c.put(req, clone));
          }
          return resp;
        })
      )
    );
    return;
  }

  // Default: pass through to the network
});
