/* Minimal service worker — enables installability where secure context allows. */
const CACHE = "bt-speaker-shell-v11";
const PRECACHE = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/apple-touch-icon.png",
  "/manifest.webmanifest",
];

function shouldCache(url) {
  return (
    url.pathname.startsWith("/static/") ||
    url.pathname === "/" ||
    url.pathname.endsWith(".webmanifest")
  );
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // Never cache API — always network
  if (url.pathname.startsWith("/api/")) return;

  // Network-first so a phone PWA picks up server updates; cache is offline fallback.
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok && shouldCache(url)) {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req).then((cached) => cached || caches.match("/"))),
  );
});
