const CACHE = "basket-platform-offline-v7";
const CORE = [
  "/static/css/design-system.css",
  "/static/css/basket-stats.css",
  "/static/js/basket-stats.js",
  "/static/img/favicon-plataforma.svg",
];
self.addEventListener("install", event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(CORE)).then(() => self.skipWaiting())));
self.addEventListener("activate", event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())));
self.addEventListener("message", event => {
  if (event.data?.type !== "CACHE_STATS_PAGE" || !event.data.url) return;
  const url = new URL(event.data.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith("/estatisticas/jogos/")) return;
  event.waitUntil(fetch(url.href, {credentials: "include"}).then(response => {
    if (!response.ok) return;
    return caches.open(CACHE).then(cache => cache.put(url.href, response));
  }).catch(() => undefined));
});
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request).then(response => { const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy));return response; })));
    return;
  }
  if (event.request.mode === "navigate" && url.pathname.startsWith("/estatisticas/jogos/")) {
    event.respondWith(fetch(event.request).then(response => { if(response.ok){const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy));}return response; }).catch(() => caches.match(event.request)));
  }
});
