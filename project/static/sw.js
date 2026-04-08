/* SpiralHubAI — частичный оффлайн: статика из кэша, страницы — из сети */
const CACHE_NAME = "spiralhubai-static-v1";
const ASSETS = ["/static/style.css", "/static/app.js", "/static/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = event.request.url;
  if (url.includes("/static/") && (url.endsWith(".css") || url.endsWith(".js") || url.endsWith(".json"))) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        const fetchNet = fetch(event.request)
          .then((res) => {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((c) => c.put(event.request, copy));
            return res;
          })
          .catch(() => cached);
        return cached || fetchNet;
      })
    );
  }
});
