/* MoveDefense service worker — conservative offline shell.
 *
 * Strategy:
 *   - navigations        : network-first, fall back to cached page, then "/"
 *                          and treat Render 502/503/504 like offline
 *   - /static/ assets    : cache-first, then network (and cache the result)
 *   - everything else    : left entirely to the network
 *
 * It deliberately never touches POST requests, auth, billing/checkout, or
 * socket.io traffic, so it cannot break the live app's dynamic behaviour.
 */
const VERSION = "md-v2";
const STATIC_CACHE = "md-static-" + VERSION;
const PAGE_CACHE = "md-pages-" + VERSION;
const DEPLOY_ERROR_STATUSES = new Set([502, 503, 504]);
const PRECACHE = [
  "/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/apple-touch-icon.png",
];
const PRECACHE_PAGES = ["/"];

function isDeployError(response) {
  return response && DEPLOY_ERROR_STATUSES.has(response.status);
}

function isCacheable(response) {
  return response && response.ok && response.type === "basic";
}

async function warmCache(cacheName, url) {
  try {
    const response = await fetch(url, { cache: "reload" });
    if (isCacheable(response)) {
      const cache = await caches.open(cacheName);
      await cache.put(url, response);
    }
  } catch (_) {
    // Keep install resilient when Render is cycling or an optional icon is down.
  }
}

async function cachedNavigation(request) {
  return (await caches.match(request)) || (await caches.match("/"));
}

function deploymentFallbackResponse(status) {
  const detail = status ? "Gateway " + status : "Network unavailable";
  return new Response(
    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">" +
      "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">" +
      "<meta name=\"theme-color\" content=\"#04060C\"><title>MoveDefense updating</title>" +
      "<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#04060C;color:#EEF2FB;font:16px system-ui,sans-serif}" +
      "main{max-width:24rem;padding:2rem}h1{font-size:1.35rem;margin:0 0 .6rem}p{color:#A6B2CB;line-height:1.45}</style></head>" +
      "<body><main><h1>MoveDefense is updating</h1><p>The app will reconnect automatically. Your saved driver records stay on this device.</p>" +
      "<p>" + detail + "</p></main></body></html>",
    {
      status: 503,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
      },
    }
  );
}

async function handleNavigation(request) {
  try {
    const response = await fetch(request);
    if (isDeployError(response)) {
      return (await cachedNavigation(request)) || deploymentFallbackResponse(response.status);
    }
    if (isCacheable(response)) {
      const cache = await caches.open(PAGE_CACHE);
      await cache.put(request, response.clone());
      if (new URL(request.url).pathname === "/") {
        await cache.put("/", response.clone());
      }
    }
    return response;
  } catch (_) {
    return (await cachedNavigation(request)) || deploymentFallbackResponse();
  }
}

async function handleStaticAsset(request) {
  const hit = await caches.match(request);
  if (hit) return hit;

  const response = await fetch(request);
  if (isCacheable(response)) {
    const cache = await caches.open(STATIC_CACHE);
    await cache.put(request, response.clone());
  }
  return response;
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    Promise.all([
      ...PRECACHE.map((url) => warmCache(STATIC_CACHE, url)),
      ...PRECACHE_PAGES.map((url) => warmCache(PAGE_CACHE, url)),
    ]).then(() => self.skipWaiting())
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
  // fall back to the cached copy (or the home shell) when offline or Render
  // returns a transient gateway/deploy error.
  if (request.mode === "navigate") {
    event.respondWith(handleNavigation(request));
    return;
  }

  // Static assets: cache-first for speed, then fill the cache from network.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(handleStaticAsset(request));
  }
});
