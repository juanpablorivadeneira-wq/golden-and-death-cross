// Service worker de Cross Monitor:
// - estáticos actualizados al abrir, con respaldo sin conexión
// - API solo por red
// - notificaciones push del servidor
"use strict";

const CACHE = "cross-monitor-v10";
const STATIC_ASSETS = [
  "/",
  "/index.html",
  "/radar200.html",
  "/radar200.js",
  "/fundamentals.html",
  "/fundamentals.js",
  "/trullas.html",
  "/trullas.js",
  "/groups.js",
  "/styles.css",
  "/app.js",
  "/manifest.json",
  "/vendor/lightweight-charts.standalone.production.js",
  "/icons/icon-180.png",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;

  // Los datos autenticados siempre requieren conexión; no guardar respuestas antiguas.
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Videos: el navegador los pide por rangos (206) y Cache.put rechaza las
  // respuestas parciales -- el catch de abajo terminaría devolviendo un 503.
  // Tampoco conviene guardar decenas de MB: se dejan pasar directo a la red.
  if (url.pathname.startsWith("/media/") || event.request.headers.has("range")) return;

  // Obtener la versión vigente al abrir; no revalidar en segundo plano.
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const response = await fetch(event.request, { cache: "no-cache" });
      if (response.ok) await cache.put(event.request, response.clone());
      return response;
    } catch (error) {
      const cached = await cache.match(event.request);
      return cached || new Response("Sin conexión. Vuelve a cargar cuando haya red.", { status: 503 });
    }
  })());
});

self.addEventListener("push", (event) => {
  let data = { title: "Cross Monitor", body: "" };
  try { data = event.data.json(); } catch (e) { data.body = event.data ? event.data.text() : ""; }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      tag: data.tag || "cross-monitor-test",
      vibrate: [200, 100, 200],
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
      for (const client of list) {
        if ("focus" in client) return client.focus();
      }
      return self.clients.openWindow("/");
    })
  );
});
