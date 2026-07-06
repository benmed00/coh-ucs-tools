const CACHE = "coh-ucs-v12";
const ASSET_PATHS = [
  "/",
  "/static/css/fonts.css",
  "/static/css/app.css",
  "/static/css/motion.css",
  "/static/js/config.js",
  "/static/js/router.js",
  "/static/js/routeScope.js",
  "/static/js/motion.js",
  "/static/js/seo.js",
  "/static/js/i18n.js",
  "/static/js/app.js",
  "/static/js/core.js",
  "/static/js/features.js",
  "/static/js/hero.js",
  "/static/manifest.json",
  "/static/icons/favicon.svg",
  "/static/icons/icon-192.png",
  "/static/icons/apple-touch-icon.png",
  "/static/icons/og-image.png",
  "/static/fonts/inter-400-latin.woff2",
  "/static/fonts/inter-500-latin.woff2",
  "/static/i18n/en.json",
  "/static/i18n/fr.json",
  "/static/i18n/ar.json",
];

function assetUrls() {
  return ASSET_PATHS.map((p) => new URL(p, self.location.origin).href);
}
function shellUrl() {
  return new URL("/", self.location.origin).href;
}

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then(async (cache) => {
      const urls = assetUrls();
      const results = await Promise.allSettled(urls.map((url) => cache.add(url)));
      results.forEach((r, i) => {
        if (r.status === "rejected") console.warn("SW precache skipped:", urls[i]);
      });
      await self.skipWaiting();
    })
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  if (!e.request.url.startsWith(self.location.origin)) return;
  if (e.request.url.includes("/api/")) return;
  e.respondWith(
    caches.match(e.request).then((cached) =>
      cached || fetch(e.request).then((res) => {
        if (res.ok && e.request.method === "GET") {
          const clone = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, clone));
        }
        return res;
      }).catch(() => caches.match(shellUrl()))
    )
  );
});
