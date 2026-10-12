// v2: der Cache haelt nur noch eigene statische Dateien. v1 legte jede
// GET-Antwort ab — auch Status, Logs und alles unter /proxy/ (Chats, Medien
// der Messenger). Der neue Name sorgt dafuer, dass activate den Altbestand
// loescht.
const CACHE = 'mp-v2';
const SHARE_CACHE = 'mp-share';

self.addEventListener('install', e => {
  e.waitUntil(self.skipWaiting());
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

// Nur die eigenen Symbole unter /static/ — nichts, was eine Anmeldung
// braucht, und nichts von den durchgereichten Messengern.
function isOwnStatic(url) {
  return url.origin === self.location.origin
    && !url.pathname.includes('/proxy/')
    && /\/static\/[^/]+$/.test(url.pathname);
}

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method === 'POST' && url.pathname.endsWith('/share-target')) {
    e.respondWith(handleShare(e.request));
    return;
  }
  if (e.request.method !== 'GET' || !isOwnStatic(url)) return;
  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
