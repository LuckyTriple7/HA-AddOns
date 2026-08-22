"""Suchabo (gespeicherte Suchen mit Schwellenpreis): Prüf-Logik + Routen —
ausgelagert aus app.py (Backlog #12, 2. Tranche). Geteilte Primitiven über
`import app as A` (spät gebunden, monkeypatch-sicher); _check_search_watch wird
auch intern über A. aufgerufen, damit Test-Patches auf dem app-Namespace greifen.
"""
import json
import secrets
import time

from flask import Blueprint, jsonify, request

import app as A
import issues

bp = Blueprint('watch', __name__)


# ── Suchabo: gespeicherte Suche beobachten (Sammel-Alarm) ───────────────────────

def _search_from_fav_payload(p: dict, *, offset: int = 0) -> dict | None:
    """Führt die Suche eines gespeicherten Favoriten aus (gleiche Payload-Form wie das
    UI sie speichert) und wendet die Nachfilter Sterne/Weiterempfehlung an.
    `offset` reicht die Seitennummer der Such-API durch — das Preisbarometer
    (`market_basket`) holt darüber alle Treffer, nicht nur die erste Seite. Die
    gemeldete Gesamttrefferzahl (`total`) bleibt dabei erhalten, damit der Aufrufer
    weiß, wann er fertig ist."""
    dest = p.get('dest') or {}
    try:
        region = int(dest.get('giata'))
    except (TypeError, ValueError):
        return None
    duration = 'exact' if p.get('exact') else (p.get('dur') or 7)
    res = A.fetch_search_params(
        region=region, start=(p.get('vom') or '').strip(), end=(p.get('bis') or '').strip(),
        duration=duration, travellers=p.get('trav') or 2,
        airports=[a for a in [(p.get('airport') or '').strip()] if a],
        operator_tui=p.get('tui') is not False,
        boards=[str(b) for b in (p.get('boards') or []) if str(b).strip()],
        airlines=[str(a) for a in (p.get('airlines') or []) if str(a).strip()],
        location=[int(i) for i in (p.get('location') or []) if str(i).strip().isdigit()],
        direct=bool(p.get('direct')), adults_only=bool(p.get('adults_only')),
        offset=offset, verbose=A._verbose())
    if not res or not res.get('ok'):
        return res

    def _num(v):
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0
    min_stars, min_rec = _num(p.get('stars')), _num(p.get('rec'))
    out = [r for r in res['results']
           if (not min_stars or (r.get('stars') or 0) >= min_stars)
           and (not min_rec or (r.get('recommendation') or 0) >= min_rec)]
    return {'ok': True, 'results': out, 'total': res.get('total', len(out))}


def _esc_html(s) -> str:
    return str(s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _notify_search_watch(name: str, new: list, cheaper: list, limit: float) -> None:
    """Meldet Suchabo-Treffer per HA + Telegram — getrennt nach „neu unter der
    Schwelle" (🆕) und „weiter gefallen" (📉, mit vorher→jetzt). Vorher stand nur
    eine Mischliste da, ohne zu sehen, was sich gegenüber dem letzten Lauf getan hat."""
    parts = []
    if new:
        parts.append(f"{len(new)} neu")
    if cheaper:
        parts.append(f"{len(cheaper)} billiger")
    head = ", ".join(parts) + f" unter {A._eur(limit)}"

    def _drop(r):
        return f" (vorher {A._eur(r['prev'])}, −{A._eur(r['prev'] - r['price'])})"

    items = [('🆕', r, '') for r in new] + [('📉', r, _drop(r)) for r in cheaper]
    plain = [f"{ico} {r.get('name')}: {A._eur(r.get('price'))}{suffix}"
             + (f" — {r['location']}" if r.get('location') else '')
             for ico, r, suffix in items[:8]]
    tg = [f'{ico} <a href="{_esc_html(r.get("offer_url"))}">{_esc_html(r.get("name"))}</a>: '
          f'<b>{A._eur(r.get("price"))}</b>{_esc_html(suffix)}'
          + (f" — {_esc_html(r['location'])}" if r.get('location') else '')
          for ico, r, suffix in items[:8]]
    more = f"… und {len(items) - 8} weitere" if len(items) > 8 else ''
    A._notify_ha(f"🔎 Suchabo „{name}“: {head}",
               "\n".join(plain + ([more] if more else [])), f"watch_{A._slug(name)}")
    A._notify_telegram(f"🔎 <b>Suchabo „{_esc_html(name)}“</b>\n{head}\n"
                     + "\n".join(tg + ([more] if more else [])))


def _check_search_watch(sid: int) -> dict | None:
    """Führt EIN Suchabo aus: Suche laufen lassen, Treffer ≤ Schwellenpreis ermitteln
    und neue bzw. weiter gefallene Hotels melden. `seen` merkt je Hotel (giata) den
    tiefsten gemeldeten Preis — steigt ein Hotel über die Schwelle, wird es vergessen
    und beim nächsten Unterschreiten erneut gemeldet. Rückgabe {hits, new} oder None."""
    with A.db() as con:
        row = con.execute('SELECT * FROM saved_searches WHERE id=?', (sid,)).fetchone()
    if not row or not row['watch'] or not row['max_price']:
        return None
    try:
        payload = json.loads(row['payload'])
    except Exception:
        payload = {}
    res = _search_from_fav_payload(payload)
    ts = int(time.time())
    if not res or not res.get('ok'):
        with A.db() as con:
            con.execute('UPDATE saved_searches SET last_checked=? WHERE id=?', (ts, sid))
        note = (res or {}).get('note') or 'API-Fehler'
        A.log.warning("Suchabo „%s“: Suche fehlgeschlagen (%s)", row['name'], note)
        issues.report('search', sid, row['name'] or f"Suchabo #{sid}",
                      f"Suche fehlgeschlagen ({note})")
        return None
    issues.clear('search', sid)
    limit = float(row['max_price'])
    hits = [r for r in res['results'] if r.get('price') is not None and r['price'] <= limit]
    try:
        seen = json.loads(row['seen'] or '{}')
    except Exception:
        seen = {}
    # Diff gegen den letzten Lauf: erstmals unter der Schwelle (new) vs. schon
    # gemeldet, aber weiter gefallen (cheaper, mit Vorher-Preis)
    new, cheaper, now_seen = [], [], {}
    for r in hits:
        g = str(r.get('giata') or '')
        if not g:
            continue
        prev = seen.get(g)
        if prev is None:
            new.append(r)
        elif r['price'] < prev:
            cheaper.append({**r, 'prev': prev})
        now_seen[g] = min(prev, r['price']) if prev is not None else r['price']

    def _slim(r):
        out = {k: r.get(k) for k in ('giata', 'name', 'price', 'location', 'stars',
                                     'recommendation', 'board', 'nights', 'date',
                                     'offer_url', 'image')}
        g = str(r.get('giata') or '')
        prev = seen.get(g)
        if prev is None:
            out['is_new'] = True          # UI-Marker 🆕
        elif r.get('price') is not None and r['price'] < prev:
            out['prev'] = prev            # UI-Marker 📉 mit Vorher-Preis
        return out

    hits_slim = [_slim(r) for r in hits]
    with A.db() as con:
        con.execute('UPDATE saved_searches SET seen=?, hits=?, last_checked=? WHERE id=?',
                    (json.dumps(now_seen), json.dumps(hits_slim, ensure_ascii=False), ts, sid))
    if new or cheaper:
        try:
            _notify_search_watch(row['name'], new, cheaper, limit)
        except Exception as e:
            A.log.error("Suchabo-Benachrichtigung fehlgeschlagen: %s", e)
    A.log.info("Suchabo „%s“: %d Treffer ≤ %s, davon %d neu, %d billiger", row['name'],
             len(hits), A._eur(limit), len(new), len(cheaper))
    return {'hits': hits_slim, 'new': len(new) + len(cheaper)}


def _maybe_check_watches() -> None:
    """Prüft fällige Suchabos (höchstens 1×/poll_interval je Abo, mindestens 1 h Abstand
    — Fairness gegenüber der Such-API)."""
    try:
        interval = int(A.load_config().get('poll_interval', A.POLL_INTERVAL_DEFAULT)
                       or A.POLL_INTERVAL_DEFAULT)
    except (TypeError, ValueError):
        interval = A.POLL_INTERVAL_DEFAULT
    interval = max(3600, interval)
    now = int(time.time())
    with A.db() as con:
        due = [r['id'] for r in con.execute(
            'SELECT id FROM saved_searches WHERE COALESCE(watch,0)=1 '
            'AND COALESCE(max_price,0)>0 AND COALESCE(last_checked,0)<=? ORDER BY id',
            (now - interval,)).fetchall()]
    gap = A._poll_gap()
    for i, sid in enumerate(due):
        try:
            A._check_search_watch(sid)
        except Exception as e:
            A.log.error("Suchabo #%d fehlgeschlagen: %s", sid, e)
        # wie im Poller: Abstand zwischen zwei Abos, nicht nach dem letzten
        if gap and i < len(due) - 1:
            time.sleep(gap + secrets.randbelow(A.POLL_GAP_JITTER + 1))


@bp.route('/api/searches', methods=['GET', 'POST'])
def api_searches():
    """Gespeicherte Suchen (Favoriten) — in der DB, geräteübergreifend.
    GET → Liste; POST {name, payload} → anlegen/aktualisieren (per Name)."""
    if (err := A._require_api()):
        return err
    if request.method == 'GET':
        with A.db() as con:
            rows = con.execute(
                'SELECT id, name, payload, watch, max_price, last_checked, hits '
                'FROM saved_searches ORDER BY name COLLATE NOCASE').fetchall()
        out = []
        for r in rows:
            try:
                payload = json.loads(r['payload'])
            except Exception:
                payload = {}
            try:
                hits = json.loads(r['hits'] or '[]')
            except Exception:
                hits = []
            out.append({'id': r['id'], 'name': r['name'], 'payload': payload,
                        'watch': bool(r['watch']), 'max_price': r['max_price'],
                        'last_checked': r['last_checked'], 'hits': hits})
        return jsonify({'searches': out})
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name_required'}), 400
    payload = json.dumps(data.get('payload') or {}, ensure_ascii=False)
    ts = int(time.time())
    with A.db() as con:
        row = con.execute('SELECT id FROM saved_searches WHERE name=?', (name,)).fetchone()
        if row:
            con.execute('UPDATE saved_searches SET payload=?, ts=? WHERE id=?',
                        (payload, ts, row['id']))
            sid = row['id']
        else:
            cur = con.execute(
                'INSERT INTO saved_searches (name, payload, ts) VALUES (?,?,?)',
                (name, payload, ts))
            sid = cur.lastrowid
    return jsonify({'ok': True, 'id': sid})


@bp.route('/api/searches/<int:sid>', methods=['DELETE'])
def api_searches_delete(sid):
    """Gespeicherte Suche löschen."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        con.execute('DELETE FROM saved_searches WHERE id=?', (sid,))
    issues.clear('search', sid)
    return jsonify({'ok': True})


@bp.route('/api/searches/<int:sid>', methods=['PATCH'])
def api_searches_patch(sid):
    """Suchabo-Einstellungen einer gespeicherten Suche: {watch, max_price}."""
    if (err := A._require_api()):
        return err
    data = request.get_json(silent=True) or {}
    with A.db() as con:
        row = con.execute('SELECT id, name, watch FROM saved_searches WHERE id=?',
                          (sid,)).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        if 'max_price' in data:
            mp = data.get('max_price')
            try:
                mp = float(mp) if mp not in (None, '', 0) else None
            except (TypeError, ValueError):
                mp = None
            con.execute('UPDATE saved_searches SET max_price=? WHERE id=?', (mp, sid))
        if 'watch' in data:
            on = 1 if data.get('watch') else 0
            con.execute('UPDATE saved_searches SET watch=? WHERE id=?', (on, sid))
            if on and not row['watch']:
                # frisch aktiviert → Meldegedächtnis zurücksetzen, damit der nächste
                # Lauf den aktuellen Stand unter der Schwelle einmal komplett meldet
                con.execute("UPDATE saved_searches SET seen='{}', hits='[]', "
                            "last_checked=0 WHERE id=?", (sid,))
            A.log.info("Suchabo „%s“ %s", row['name'], "aktiviert" if on else "deaktiviert")
    return jsonify({'ok': True})


@bp.route('/api/searches/<int:sid>/check', methods=['POST'])
def api_searches_check(sid):
    """Suchabo sofort prüfen (synchron) — liefert die aktuellen Treffer zurück."""
    if (err := A._require_api()):
        return err
    if (remaining := A._cooldown_remaining(f'search_check:{sid}', 30)):
        return jsonify({'error': 'cooldown', 'retry_after': remaining}), 429
    with A.db() as con:
        row = con.execute('SELECT watch, max_price FROM saved_searches WHERE id=?',
                          (sid,)).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    if not row['watch'] or not row['max_price']:
        return jsonify({'error': 'not_watching'}), 400
    res = A._check_search_watch(sid)
    if res is None:
        return jsonify({'error': 'search_failed'}), 502
    return jsonify({'ok': True, 'hits': res['hits'], 'new': res['new']})

