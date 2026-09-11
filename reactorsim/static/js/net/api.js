// Dünne Hülle um fetch.
//
// Das Spiel muss ohne den Server laufen -- er liefert Szenarienliste,
// Spielstände und Bestenliste, aber keine Physik. Jeder Fehler hier ist
// deshalb ein Achselzucken und kein Abbruch: die Aufrufer bekommen null und
// machen weiter.

const BASE = '';

async function request(method, path, body) {
  try {
    const res = await fetch(BASE + path, {
      method,
      headers: body ? { 'Content-Type': 'application/json', Accept: 'application/json' }
                    : { Accept: 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401) {
      // Sitzung abgelaufen. Ohne diesen Zweig laufen alle weiteren Aufrufe
      // still ins Leere, und der Spieler sieht nur, dass nichts mehr
      // gespeichert wird -- ohne zu erfahren warum.
      window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
      return { ok: false, status: 401, data: null };
    }
    const data = await res.json().catch(() => null);
    if (!res.ok) return { ok: false, status: res.status, data };
    return { ok: true, status: res.status, data };
  } catch {
    // Kein Server erreichbar: offline weiterspielen.
    return { ok: false, status: 0, data: null };
  }
}

export const api = {
  meta: () => request('GET', '/api/meta'),
  listSaves: () => request('GET', '/api/saves'),
  readSave: (slot) => request('GET', `/api/saves/${encodeURIComponent(slot)}`),
  writeSave: (slot, blob) => request('PUT', `/api/saves/${encodeURIComponent(slot)}`, blob),
  deleteSave: (slot) => request('DELETE', `/api/saves/${encodeURIComponent(slot)}`),
  listScores: (reactor, scenario, limit = 20) => {
    const q = new URLSearchParams();
    if (reactor) q.set('reactor', reactor);
    if (scenario) q.set('scenario', scenario);
    q.set('limit', String(limit));
    return request('GET', `/api/highscores?${q}`);
  },
  submitScore: (name, summary) => request('POST', '/api/highscores', { name, summary }),
};
