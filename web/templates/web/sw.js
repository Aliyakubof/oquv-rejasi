{% load static %}
const CACHE_NAME = "oquv-yuklamasi-offline-v1";
const OFFLINE_URL = "{% url 'offline_sahifa' %}";
const PRECACHE_URLS = [
  OFFLINE_URL,
  "{% static 'web/css/app.css' %}?v=64",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith("oquv-yuklamasi-offline-") && k !== CACHE_NAME)
            .map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(async () => {
        const cachedOffline = await caches.match(OFFLINE_URL);
        if (cachedOffline) return cachedOffline;
        return new Response(
          "<!DOCTYPE html><html lang='uz'><meta charset='UTF-8'><title>Oflayn</title><body style='font-family:sans-serif;text-align:center;padding:48px'><h1>Internet aloqasi uzildi</h1></body></html>",
          { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } }
        );
      })
    );
    return;
  }

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      fetch(req)
        .then((resp) => {
          if (resp && resp.ok) {
            const copy = resp.clone();
            caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
          }
          return resp;
        })
        .catch(() => caches.match(req))
    );
  }
});
