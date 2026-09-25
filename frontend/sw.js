/* Service worker: caches the app shell so the PWA opens instantly and can be
   installed to the home screen. Diagnosis itself still needs the server — the
   CNN runs there, not in the browser. */

const CACHE = "plant-disease-v4";
const SHELL = [
  "/",
  "/app/css/styles.css",
  "/app/js/app.js",
  "/app/js/i18n.js",
  "/app/js/heatmap.js",
  "/app/js/camera.js",
  "/app/js/history.js",
  "/app/js/weather.js",
  "/app/js/map.js",
  "/manifest.webmanifest",
  "/app/icons/icon-192.png",
  "/app/icons/icon-512.png",
];

// Fonts, icons and Leaflet come from these CDNs. They are versioned and never
// change under the same URL, so cache-first is safe and makes them work offline.
const CDN_HOSTS = ["fonts.googleapis.com", "fonts.gstatic.com", "cdnjs.cloudflare.com"];

// Advisory text is static per class and language: worth keeping for offline
// reopening of saved scans. Predictions, AI and weather are never cached.
const CACHEABLE_API = ["/api/advisory/", "/api/classes"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      // addAll rejects if any single file 404s, which would leave the SW
      // permanently uninstalled; cache each file independently instead.
      .then((cache) => Promise.all(SHELL.map((url) => cache.add(url).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function networkFirst(request) {
  return fetch(request)
    .then((response) => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE).then((c) => c.put(request, copy));
      }
      return response;
    })
    .catch(() => caches.match(request).then((cached) => cached || caches.match("/")));
}

function cacheFirst(request) {
  return caches.match(request).then((cached) =>
    cached ||
    fetch(request).then((response) => {
      // Cross-origin font responses can be opaque (status 0); still cacheable.
      if (response.ok || response.type === "opaque") {
        const copy = response.clone();
        caches.open(CACHE).then((c) => c.put(request, copy));
      }
      return response;
    })
  );
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (CDN_HOSTS.includes(url.hostname)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  if (url.origin !== self.location.origin) return; // map tiles, weather: always live

  if (url.pathname.startsWith("/api/")) {
    // Never cache predictions or health checks — a stale diagnosis is worse
    // than no diagnosis.
    if (CACHEABLE_API.some((p) => url.pathname.startsWith(p))) event.respondWith(networkFirst(request));
    return;
  }

  // Network first, cache as the offline fallback. Cache-first would pin
  // phones to whatever app.js they saw first, so updates would never arrive.
  event.respondWith(networkFirst(request));
});
