// CardBoard Service Worker — Network-first für alle dynamischen Inhalte
const CACHE = 'cardboard-v1';

self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll([
      '/static/favicon.png',
      '/static/icon-192.png',
    ]).catch(() => {}))
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE).map(k => caches.delete(k))
      ))
      .then(() => clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const path = new URL(e.request.url).pathname;
  // Dynamische Routen immer direkt vom Netzwerk (keine veralteten HA-Daten)
  if (path.startsWith('/api/') ||
      path === '/login' || path === '/view' ||
      path === '/logout' || path === '/change-password') return;
  // Statische Assets: Cache-first
  e.respondWith(
    caches.match(e.request).then(hit => hit || fetch(e.request).then(resp => {
      if (resp.ok && path.startsWith('/static/')) {
        caches.open(CACHE).then(c => c.put(e.request, resp.clone()));
      }
      return resp;
    }))
  );
});
