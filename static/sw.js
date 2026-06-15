/* MoveDefense service worker — conservative offline shell.
 *
 * Strategy:
 *   - navigations        : network-first, fall back to cached page, then "/"
 *   - /static/ assets    : cache-first, then network (and cache the result)
 *   - everything else    : left entirely to the network
 *
 * It deliberately never touches POST requests, auth, billing/checkout, or
 * socket.io traffic, so it cannot break the live app's dynamic behaviour.
 */
const VERSION = "md-v1";
const STATIC_CACHE = "md-static-" + VERSION;
const PAGE_CACHE = "md-pages-" + VERSION;
const PRECACHE = [
  "/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== STATIC_CACHE && key !== PAGE_CACHE)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Only same-origin GETs are eligible. Leave POSTs (login, billing, forms),
  // cross-origin requests (Google fonts/maps), and realtime sockets alone.
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/socket.io")) return;

  // Page navigations: network-first so online users always get fresh data;
  // fall back to the cached copy (or the home shell) when offline.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(PAGE_CACHE).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() =>
          caches.match(request).then((hit) => hit || caches.match("/"))
        )
    );
    return;
  }

  // Static assets: cache-first for speed, then fill the cache from network.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((response) => {
            const copy = response.clone();
            caches.open(STATIC_CACHE).then((cache) => cache.put(request, copy));
            return response;
          })
      )
    );
  }
});
