const R2_BINDING = "MD_R2_FALLBACK";
const FALLBACK_STATUSES = new Set([502, 503, 504, 522, 523, 524]);
const SHELL_PATHS = new Set(["/", "/app"]);
const STATIC_PATHS = new Set([
  "/manifest.webmanifest",
  "/sw.js",
  "/static/icons/apple-touch-icon.png",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/icon-maskable-512.png",
]);

function snapshotKey(request) {
  if (!["GET", "HEAD"].includes(request.method)) return null;

  const url = new URL(request.url);
  if (url.pathname.startsWith("/api/")) return null;
  if (url.pathname.startsWith("/socket.io")) return null;

  if (SHELL_PATHS.has(url.pathname)) {
    return url.pathname === "/" ? "snapshots/welcome.html" : "snapshots/app.html";
  }
  if (STATIC_PATHS.has(url.pathname)) {
    return "snapshots" + url.pathname;
  }
  return null;
}

function isSnapshotSource(response) {
  return response && response.status === 200 && !response.headers.has("set-cookie");
}

function shouldUseFallback(response) {
  return response && FALLBACK_STATUSES.has(response.status);
}

function contentTypeForKey(key) {
  if (key.endsWith(".html")) return "text/html; charset=utf-8";
  if (key.endsWith(".js")) return "text/javascript; charset=utf-8";
  if (key.endsWith(".webmanifest")) return "application/manifest+json";
  if (key.endsWith(".png")) return "image/png";
  return "application/octet-stream";
}

async function saveSnapshot(bucket, key, response) {
  if (!bucket || !isSnapshotSource(response)) return;

  const body = await response.clone().arrayBuffer();
  await bucket.put(key, body, {
    httpMetadata: {
      contentType: response.headers.get("content-type") || contentTypeForKey(key),
      cacheControl: "no-store",
    },
    customMetadata: {
      source: "movedefense-origin",
      updated_at: new Date().toISOString(),
    },
  });
}

async function readSnapshot(bucket, key, request) {
  if (!bucket) return null;

  const object = await bucket.get(key);
  if (!object) return null;

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  if (!headers.has("content-type")) {
    headers.set("content-type", contentTypeForKey(key));
  }
  headers.set("cache-control", "no-store");
  headers.set("x-movedefense-fallback", "r2");

  return new Response(request.method === "HEAD" ? null : object.body, {
    status: 200,
    headers,
  });
}

function updatingResponse(key) {
  const isHtml = key && key.endsWith(".html");
  const body = isHtml
    ? "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>MoveDefense updating</title></head><body><main><h1>MoveDefense is updating</h1><p>Please retry in a moment.</p></main></body></html>"
    : "MoveDefense is updating. Please retry in a moment.";

  return new Response(body, {
    status: 503,
    headers: {
      "content-type": isHtml ? "text/html; charset=utf-8" : "text/plain; charset=utf-8",
      "cache-control": "no-store",
      "x-movedefense-fallback": "miss",
    },
  });
}

function withWorkerHeader(response) {
  if (!response) return response;

  const forwarded = new Response(response.body, response);
  forwarded.headers.set("x-movedefense-worker", "r2-fallback");
  return forwarded;
}

export default {
  async fetch(request, env, ctx) {
    const key = snapshotKey(request);
    if (!key) return fetch(request);

    const bucket = env[R2_BINDING];
    let originResponse;

    try {
      originResponse = await fetch(request);
    } catch (_) {
      return (await readSnapshot(bucket, key, request)) || updatingResponse(key);
    }

    if (isSnapshotSource(originResponse) && request.method === "GET") {
      ctx.waitUntil(saveSnapshot(bucket, key, originResponse));
    }

    if (shouldUseFallback(originResponse)) {
      return (await readSnapshot(bucket, key, request)) || updatingResponse(key);
    }

    return withWorkerHeader(originResponse);
  },
};
