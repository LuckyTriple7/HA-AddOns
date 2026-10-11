const CACHE = 'mp-v1';
const SHARE_CACHE = 'mp-share';
const PRECACHE = ['/', '/login'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE && k !== SHARE_CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// "Teilen"-Ziel: das Betriebssystem schickt den geteilten Inhalt als POST.
// Er bleibt im Browser liegen (Cache API) und geht nicht an den Server —
// so uebersteht er auch den Umweg ueber die Anmeldung. Die Seite /share
// liest ihn dort wieder aus.
async function handleShare(request) {
  const target = new URL('share', request.url).href;
  try {
    const form = await request.formData();
    const files = form.getAll('files').filter(f => f && typeof f !== 'string' && f.size > 0);
    await caches.delete(SHARE_CACHE);
    const cache = await caches.open(SHARE_CACHE);
    for (let i = 0; i < files.length; i++) {
      await cache.put('/__share/file/' + i, new Response(files[i], {
        headers: { 'Content-Type': files[i].type || 'application/octet-stream' },
      }));
    }
    const meta = {
      ts: Date.now(),
      title: String(form.get('title') || ''),
      text: String(form.get('text') || ''),
      url: String(form.get('url') || ''),
      files: files.map(f => ({ name: f.name || 'file', type: f.type || 'application/octet-stream', size: f.size })),
    };
    await cache.put('/__share/meta', new Response(JSON.stringify(meta), {
      headers: { 'Content-Type': 'application/json' },
    }));
  } catch (err) {
    return Response.redirect(target + '?lost=1', 303);
  }
  return Response.redirect(target, 303);
}

self.addEventListener('fetch', e => {
  if (e.request.method === 'POST' && new URL(e.request.url).pathname.endsWith('/share-target')) {
    e.respondWith(handleShare(e.request));
    return;
  }
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request)
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
