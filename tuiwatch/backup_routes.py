"""Flask-Blueprint: Backup & Restore (ZIP mit data.json + Reise-PDFs) inkl.
automatischem Wochen-Backup — ausgelagert aus app.py (Backlog #12, Wartbarkeit).

Geteilte Primitiven laufen über `import app as A` mit spätem Attribut-Zugriff
(monkeypatch-sicher, kein Import-Zyklus — Registrierung am Ende von app.py).
BACKUP_DIR bleibt bewusst in app.py (Tests patchen m.BACKUP_DIR).
"""
import io
import json
import os
import re
import sqlite3
import time
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, make_response, request

import app as A

bp = Blueprint('backup', __name__)


_BACKUP_META_KEYS = (
    'travel_dna', 'ai_usage_totals', 'ai_usage_today', 'ai_usage_month',
    'custom_prompt_advisor_enabled', 'custom_prompt_advisor_text',
    'custom_prompt_compare_enabled', 'custom_prompt_compare_text',
    'custom_prompt_summary_enabled', 'custom_prompt_summary_text',
    'custom_prompt_daytrip_enabled', 'custom_prompt_daytrip_text',
    'ai_provider_active', 'packing_template',
)


def _build_backup_zip() -> bytes:
    """Baut das vollständige Backup-ZIP: data.json (Angebote inkl. Preisverlauf & Marker,
    gebuchte Reisen, gespeicherte Suchen, KI-Verlauf & KI-Einstellungen) + die Reise-PDFs
    unter trips/. Genutzt vom Download-Endpoint und vom automatischen Backup."""
    with A.db() as con:
        ocols = [c for c in A._table_columns(con, 'offers') if c != 'id']
        offers = []
        for r in con.execute('SELECT * FROM offers ORDER BY id').fetchall():
            o = {c: r[c] for c in ocols}
            oid = r['id']
            o['history'] = [{c: h[c] for c in A._HISTORY_COLS} for h in con.execute(
                'SELECT ts, price, old_price, discount, available, ok, note '
                'FROM price_history WHERE offer_id=? ORDER BY ts', (oid,)).fetchall()]
            o['events'] = [{c: e[c] for c in A._EVENT_COLS} for e in con.execute(
                'SELECT ts, type, text FROM offer_events WHERE offer_id=? ORDER BY ts',
                (oid,)).fetchall()]
            o['calendar_history'] = [{'travel_date': h['travel_date'], 'ts': h['ts'],
                                      'price': h['price']} for h in con.execute(
                'SELECT travel_date, ts, price FROM calendar_history '
                'WHERE offer_id=? ORDER BY travel_date, ts', (oid,)).fetchall()]
            offers.append(o)
        trips = [{c: t[c] for c in A._TRIP_COLUMNS} for t in con.execute(
            f"SELECT {', '.join(A._TRIP_COLUMNS)} FROM trips ORDER BY id").fetchall()]
        searches = [{c: s[c] for c in ('name', 'payload', 'ts')} for s in con.execute(
            'SELECT name, payload, ts FROM saved_searches ORDER BY id').fetchall()]
        # Zusatz-PDFs je Reise nur über booking_code referenzierbar sichern (Trip-IDs
        # ändern sich beim Restore) — Reisen ohne Buchungsnummer werden ausgelassen.
        attachments = []
        for a in con.execute(
                'SELECT trip_attachments.filename, trip_attachments.orig_name, '
                'trip_attachments.created, trips.booking_code '
                'FROM trip_attachments JOIN trips ON trips.id = trip_attachments.trip_id '
                'WHERE trips.booking_code IS NOT NULL ORDER BY trip_attachments.id').fetchall():
            attachments.append(dict(a))
        # Packliste je Reise nur über booking_code referenzierbar sichern (wie Anhänge) —
        # Reisen ohne Buchungsnummer werden ausgelassen.
        packing_items = []
        for pi in con.execute(
                'SELECT trip_packing_items.category, trip_packing_items.label, '
                'trip_packing_items.checked, trips.booking_code '
                'FROM trip_packing_items JOIN trips ON trips.id = trip_packing_items.trip_id '
                'WHERE trips.booking_code IS NOT NULL ORDER BY trip_packing_items.id').fetchall():
            packing_items.append(dict(pi))
        ai_analyses = [dict(r) for r in con.execute(
            'SELECT kind, title, model, summary, usage, ts, prompt, conversation '
            'FROM ai_analyses ORDER BY id').fetchall()]
        meta_rows = con.execute(
            f"SELECT key, value FROM meta WHERE key IN ({','.join('?' for _ in _BACKUP_META_KEYS)})",
            _BACKUP_META_KEYS).fetchall()
        meta = {r['key']: r['value'] for r in meta_rows}
        # Markttrend-Datenpunkte: bewusst NICHT an offer_id gebunden, daher hier separat
        # (nicht je Angebot) gesichert — überlebt so auch ein Restore ohne die
        # ursprünglichen Angebote.
        price_moves = [{'ts': r['ts'], 'region': r['region'], 'country': r['country'],
                         'months_out': r['months_out'], 'pct_change': r['pct_change']}
                        for r in con.execute(
                            'SELECT ts, region, country, months_out, pct_change '
                            'FROM price_moves ORDER BY ts').fetchall()]
        # Warenkorb-Tagesbewegungen (Regions-Markttrend): nur die verdichteten Werte,
        # nicht die Roh-Snapshots — die sind groß, werden ohnehin nach 120 Tagen
        # verworfen und entstehen täglich neu. Der Index seit Aufzeichnungsbeginn
        # hängt dagegen allein an diesen Zeilen, deshalb gehören sie ins Backup.
        basket_moves = [dict(r) for r in con.execute(
            'SELECT ts, day, region, prev_day, gap_days, pct_median, n_matched, n_total '
            'FROM basket_moves ORDER BY day').fetchall()]
    data = {'tuiwatch_backup': 6, 'created': datetime.now().isoformat(),
            'offers': offers, 'trips': trips, 'saved_searches': searches,
            'trip_attachments': attachments, 'trip_packing_items': packing_items,
            'ai_analyses': ai_analyses, 'meta': meta, 'price_moves': price_moves,
            'basket_moves': basket_moves}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('data.json', json.dumps(data, ensure_ascii=False, indent=2))
        seen = set()
        for t in trips:
            name = (t.get('pdf_name') or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            p = A._trip_pdf_path(name)
            if p and p.exists():
                z.write(str(p), f'trips/{Path(name).name}')
        seen_att = set()
        for a in attachments:
            name = (a.get('filename') or '').strip()
            if not name or name in seen_att:
                continue
            seen_att.add(name)
            p = A._trip_pdf_path(name)
            if p and p.exists():
                z.write(str(p), f'attachments/{Path(name).name}')
    return buf.getvalue()


@bp.route('/api/backup', methods=['GET'])
def api_backup():
    """Vollständiges Backup als ZIP herunterladen."""
    if (err := A._require_api()):
        return err
    resp = make_response(_build_backup_zip())
    resp.headers['Content-Type'] = 'application/zip'
    resp.headers['Content-Disposition'] = (
        f'attachment; filename="tuiwatch-backup-{datetime.now().strftime("%Y%m%d")}.zip"')
    return resp


AUTO_BACKUP_INTERVAL = 7 * 86400   # wöchentlich
_AUTO_BACKUP_RE = re.compile(r'^tuiwatch-backup-\d{8}-\d{6}\.zip$')

def _run_auto_backup(keep: int) -> None:
    """Schreibt ein Backup-ZIP nach A.BACKUP_DIR und behält nur die letzten `keep`.
    So überlebt die Historie (Angebote, Reisen, Suchen) auch eine Neuinstallation
    des Add-ons — /addon_config wird dabei nicht gelöscht."""
    base = Path(A.BACKUP_DIR)
    base.mkdir(parents=True, exist_ok=True)
    target = base / f"tuiwatch-backup-{datetime.now():%Y%m%d-%H%M%S}.zip"
    target.write_bytes(_build_backup_zip())
    keep = max(1, keep)
    # Rotation: nur eigene, exakt passende Backup-Dateien anfassen
    old = sorted(p for p in base.glob('tuiwatch-backup-*.zip')
                 if _AUTO_BACKUP_RE.match(p.name))
    for p in old[:-keep]:
        try:
            p.unlink()
        except OSError as e:
            A.log.warning("Altes Auto-Backup %s nicht löschbar: %s", p.name, e)
    A.log.info("Auto-Backup geschrieben: %s (%d behalten)", target.name, min(len(old), keep))


def _maybe_auto_backup() -> None:
    """Legt höchstens 1×/Woche ein Backup unter /addon_config/backups ab (falls aktiviert).
    War das Add-on am Stichtag aus, wird beim nächsten Poll nachgeholt."""
    cfg = A.load_config()
    if not cfg.get('auto_backup', True):
        return
    try:
        last = int(A._meta_get('last_auto_backup', 0) or 0)
    except (TypeError, ValueError):
        last = 0
    if time.time() - last < AUTO_BACKUP_INTERVAL:
        return
    try:
        keep = int(cfg.get('auto_backup_keep', 5) or 5)
    except (TypeError, ValueError):
        keep = 5
    try:
        _run_auto_backup(keep)
        A._meta_set('last_auto_backup', str(int(time.time())))
    except Exception as e:
        A.log.error("Auto-Backup fehlgeschlagen: %s", e)


def _restore_offer(con, it: dict, ocols: set, existing_urls: set) -> str:
    """Ein Angebot aus dem Backup einspielen (nicht-destruktiv, Upsert per URL).
    Rückgabe: 'added' | 'skipped'; bei 'added' werden Verlauf & Marker mitgeschrieben."""
    def _price(v):
        try:
            return float(v) if v not in (None, '', 0) else None
        except (TypeError, ValueError):
            return None
    url = (it.get('url') or '').strip()
    if not A._valid_tui_url(url) or url in existing_urls:
        return 'skipped'
    # Werte NUR aus der festen Spalten-Whitelist übernehmen (Spaltennamen sind Code-
    # Konstanten, nie aus den Daten), sicherheitskritische Felder bereinigen.
    row = {c: it.get(c) for c in A._OFFER_RESTORE_COLS if c in ocols}
    row['url'] = url
    row['label'] = (it.get('label') or '').strip()
    row['hotel'] = (it.get('hotel') or A.hotel_from_url(url) or '')
    if 'target_price' in row:
        row['target_price'] = _price(it.get('target_price'))
    if 'booked_price' in row:
        row['booked_price'] = _price(it.get('booked_price'))
    if 'image_url' in row:
        img = (it.get('image_url') or '').strip()
        row['image_url'] = img if A._valid_img_url(img) else ''
    row['paused'] = 1 if it.get('paused') else 0
    row['archived'] = 1 if it.get('archived') else 0
    row['created'] = int(it.get('created') or time.time())
    # Spaltenliste ausschließlich aus der Konstante (feste Reihenfolge, keine Nutzerdaten)
    cols = [c for c in A._OFFER_RESTORE_COLS if c in row]
    try:
        cur = con.execute(
            f"INSERT INTO offers ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            [row[c] for c in cols])
    except sqlite3.IntegrityError:
        return 'skipped'
    oid = cur.lastrowid
    existing_urls.add(url)
    for h in (it.get('history') or []):
        if not isinstance(h, dict):
            continue
        con.execute(
            'INSERT INTO price_history (offer_id, ts, price, old_price, discount, '
            'available, ok, note) VALUES (?,?,?,?,?,?,?,?)',
            (oid, int(h.get('ts') or 0), h.get('price'), h.get('old_price'),
             h.get('discount'), h.get('available'),
             1 if h.get('ok') else 0, (h.get('note') or '')))
    for e in (it.get('events') or []):
        if not isinstance(e, dict) or not e.get('type'):
            continue
        con.execute('INSERT INTO offer_events (offer_id, ts, type, text) VALUES (?,?,?,?)',
                    (oid, int(e.get('ts') or 0), str(e.get('type')), (e.get('text') or '')))
    for c in (it.get('calendar_history') or []):
        if not isinstance(c, dict) or not c.get('travel_date') or c.get('price') is None:
            continue
        con.execute(
            'INSERT INTO calendar_history (offer_id, travel_date, ts, price) VALUES (?,?,?,?)',
            (oid, str(c['travel_date']), int(c.get('ts') or 0), c['price']))
    return oid


@bp.route('/api/restore', methods=['POST'])
def api_restore():
    """Wiederherstellung aus einem Backup — akzeptiert die ZIP (vollständig) oder das
    alte JSON (nur Angebote). Nicht-destruktiv: bestehende Angebote/Reisen/Suchen bleiben,
    fehlende werden ergänzt (Upsert per URL / Buchungsnummer / Name)."""
    if (err := A._require_api()):
        return err
    up = request.files.get('file')
    raw = up.read() if up is not None else None
    pdfs: dict[str, bytes] = {}
    att_pdfs: dict[str, bytes] = {}
    data = None
    if raw:
        if raw[:2] == b'PK':                       # ZIP-Archiv
            try:
                zf = zipfile.ZipFile(io.BytesIO(raw))
                data = json.loads(zf.read('data.json').decode('utf-8'))
            except (zipfile.BadZipFile, KeyError, ValueError, UnicodeDecodeError):
                return jsonify({'error': 'invalid'}), 400
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if info.filename.startswith('trips/'):
                    base = Path(info.filename).name
                    if base.lower().endswith('.pdf') and 0 < info.file_size <= A.MAX_PDF_BYTES:
                        pdfs[base] = zf.read(info)
                elif info.filename.startswith('attachments/'):
                    base = Path(info.filename).name
                    if base.lower().endswith('.pdf') and 0 < info.file_size <= A.MAX_PDF_BYTES:
                        att_pdfs[base] = zf.read(info)
        else:                                       # hochgeladene JSON-Datei
            try:
                data = json.loads(raw.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                return jsonify({'error': 'invalid'}), 400
    else:
        data = request.get_json(silent=True)

    if isinstance(data, list):                      # ganz altes Format = reine Angebotsliste
        data = {'offers': data}
    if not isinstance(data, dict) or not isinstance(data.get('offers', []), list):
        return jsonify({'error': 'invalid'}), 400

    offers = data.get('offers') or []
    trips = data.get('trips') or []
    searches = data.get('saved_searches') or []
    trip_attachments = data.get('trip_attachments') or []
    packing_items = data.get('trip_packing_items') or []
    ai_analyses = data.get('ai_analyses') or []
    meta = data.get('meta') or {}
    price_moves = data.get('price_moves') or []
    basket_moves = data.get('basket_moves') or []   # erst ab Backup-Version 6
    added, skipped, new_ids = 0, 0, []
    trips_n, searches_n, attachments_n, packing_n, ai_n, settings_n, moves_n = 0, 0, 0, 0, 0, 0, 0
    basket_n = 0
    with A.db() as con:
        ocols = set(A._table_columns(con, 'offers'))
        existing_urls = {r['url'] for r in con.execute('SELECT url FROM offers').fetchall()}
        for it in offers:
            if not isinstance(it, dict):
                skipped += 1
                continue
            res = _restore_offer(con, it, ocols, existing_urls)
            if res == 'skipped':
                skipped += 1
            else:
                added += 1
                if not it.get('archived'):
                    new_ids.append(res)             # archivierte nicht sofort prüfen
        if isinstance(trips, list) and trips:
            Path(A.TRIPS_DIR).mkdir(parents=True, exist_ok=True)
            for t in trips:
                if not isinstance(t, dict):
                    continue
                pdf_name = (t.get('pdf_name') or '').strip()
                if pdf_name and pdf_name in pdfs:
                    p = A._trip_pdf_path(pdf_name)
                    if p:
                        p.write_bytes(pdfs[pdf_name])
                vals = [int(t.get(c) or time.time()) if c == 'created' else t.get(c)
                        for c in A._TRIP_COLUMNS]
                booking = (t.get('booking_code') or '').strip()
                ex = (con.execute('SELECT id FROM trips WHERE booking_code=?', (booking,)).fetchone()
                      if booking else None)
                if ex:
                    con.execute('UPDATE trips SET '
                                + ', '.join(f'{c}=?' for c in A._TRIP_COLUMNS)
                                + ' WHERE id=?', vals + [ex['id']])
                    trips_n += 1
                    continue
                try:
                    con.execute(
                        f"INSERT INTO trips ({', '.join(A._TRIP_COLUMNS)}) "
                        f"VALUES ({', '.join('?' for _ in A._TRIP_COLUMNS)})", vals)
                    trips_n += 1
                except sqlite3.IntegrityError:
                    pass
        if isinstance(trip_attachments, list) and trip_attachments:
            Path(A.TRIPS_DIR).mkdir(parents=True, exist_ok=True)
            for a in trip_attachments:
                if not isinstance(a, dict):
                    continue
                booking = (a.get('booking_code') or '').strip()
                filename = (a.get('filename') or '').strip()
                orig_name = (a.get('orig_name') or '').strip()
                if not booking or not filename or not orig_name:
                    continue
                trip_row = con.execute(
                    'SELECT id FROM trips WHERE booking_code=?', (booking,)).fetchone()
                if not trip_row:
                    continue
                exists = con.execute(
                    'SELECT id FROM trip_attachments WHERE trip_id=? AND filename=?',
                    (trip_row['id'], filename)).fetchone()
                if exists:
                    continue
                if filename in att_pdfs:
                    p = A._trip_pdf_path(filename)
                    if p:
                        p.write_bytes(att_pdfs[filename])
                con.execute(
                    'INSERT INTO trip_attachments (trip_id, filename, orig_name, created) '
                    'VALUES (?,?,?,?)',
                    (trip_row['id'], filename, orig_name, int(a.get('created') or time.time())))
                attachments_n += 1
        if isinstance(packing_items, list) and packing_items:
            for pi in packing_items:
                if not isinstance(pi, dict):
                    continue
                booking = (pi.get('booking_code') or '').strip()
                category = (pi.get('category') or '').strip()
                label = (pi.get('label') or '').strip()
                if not booking or not category or not label:
                    continue
                trip_row = con.execute(
                    'SELECT id FROM trips WHERE booking_code=?', (booking,)).fetchone()
                if not trip_row:
                    continue
                exists = con.execute(
                    'SELECT id FROM trip_packing_items WHERE trip_id=? AND category=? AND label=?',
                    (trip_row['id'], category, label)).fetchone()
                if exists:
                    continue
                con.execute(
                    'INSERT INTO trip_packing_items (trip_id, category, label, checked, created) '
                    'VALUES (?,?,?,?,?)',
                    (trip_row['id'], category, label, 1 if pi.get('checked') else 0, int(time.time())))
                con.execute('UPDATE trips SET packing_seeded=1 WHERE id=?', (trip_row['id'],))
                packing_n += 1
        if isinstance(searches, list):
            for s in searches:
                if not isinstance(s, dict):
                    continue
                name = (s.get('name') or '').strip()
                if not name:
                    continue
                payload = s.get('payload')
                if not isinstance(payload, str):
                    payload = json.dumps(payload or {}, ensure_ascii=False)
                ts = int(s.get('ts') or time.time())
                ex = con.execute('SELECT id FROM saved_searches WHERE name=?', (name,)).fetchone()
                if ex:
                    con.execute('UPDATE saved_searches SET payload=?, ts=? WHERE id=?',
                                (payload, ts, ex['id']))
                else:
                    con.execute('INSERT INTO saved_searches (name, payload, ts) VALUES (?,?,?)',
                                (name, payload, ts))
                    searches_n += 1
        if isinstance(ai_analyses, list) and ai_analyses:
            for a in ai_analyses:
                if not isinstance(a, dict):
                    continue
                kind = (a.get('kind') or '').strip()
                title = (a.get('title') or '').strip()
                ts = a.get('ts')
                if not kind or not title or ts is None:
                    continue
                exists = con.execute(
                    'SELECT id FROM ai_analyses WHERE kind=? AND title=? AND ts=?',
                    (kind, title, ts)).fetchone()
                if exists:
                    continue
                con.execute(
                    'INSERT INTO ai_analyses (kind, title, model, summary, usage, ts, prompt, '
                    'conversation) VALUES (?,?,?,?,?,?,?,?)',
                    (kind, title, a.get('model'), a.get('summary'), a.get('usage'), ts,
                     a.get('prompt') or '', a.get('conversation') or ''))
                ai_n += 1
            con.execute('DELETE FROM ai_analyses WHERE id NOT IN '
                        '(SELECT id FROM ai_analyses ORDER BY id DESC LIMIT ?)', (A._AI_HISTORY_MAX,))
        if isinstance(price_moves, list) and price_moves:
            # Markttrend-Datenpunkte sind an keine offer_id gebunden (kein natürlicher
            # Fremdschlüssel für ein Upsert) — Dedup daher über den vollen Wertesatz,
            # damit ein wiederholtes Einspielen desselben Backups nichts verdoppelt.
            existing_moves = {
                (r['ts'], r['region'], r['country'], r['months_out'], r['pct_change'])
                for r in con.execute(
                    'SELECT ts, region, country, months_out, pct_change FROM price_moves'
                ).fetchall()}
            for pm in price_moves:
                if not isinstance(pm, dict) or pm.get('pct_change') is None:
                    continue
                key = (int(pm.get('ts') or 0), pm.get('region') or '', pm.get('country') or '',
                       pm.get('months_out'), pm.get('pct_change'))
                if key in existing_moves:
                    continue
                con.execute(
                    'INSERT INTO price_moves (ts, region, country, months_out, pct_change) '
                    'VALUES (?,?,?,?,?)', key)
                existing_moves.add(key)
                moves_n += 1
        if isinstance(basket_moves, list) and basket_moves:
            # (region, day) ist eindeutig — vorhandene Tage bleiben unangetastet
            # (nicht-destruktiv wie der übrige Restore), fehlende kommen dazu.
            existing_days = {(r['region'], r['day']) for r in con.execute(
                'SELECT region, day FROM basket_moves').fetchall()}
            for bm in basket_moves:
                if not isinstance(bm, dict) or bm.get('pct_median') is None:
                    continue
                key = (bm.get('region') or '', bm.get('day') or '')
                if not key[1] or key in existing_days:
                    continue
                con.execute(
                    'INSERT INTO basket_moves (ts, day, region, prev_day, gap_days, '
                    'pct_median, n_matched, n_total) VALUES (?,?,?,?,?,?,?,?)',
                    (int(bm.get('ts') or 0), key[1], key[0], bm.get('prev_day') or '',
                     bm.get('gap_days') or 1, bm['pct_median'],
                     int(bm.get('n_matched') or 0), int(bm.get('n_total') or 0)))
                existing_days.add(key)
                basket_n += 1
        if isinstance(meta, dict):
            # Nicht-destruktiv wie der Rest des Restores: nur setzen, wenn lokal noch
            # nichts hinterlegt ist — laufende Zaehler/Einstellungen werden nie mit
            # (moeglicherweise aelteren) Backup-Werten ueberschrieben.
            for k in _BACKUP_META_KEYS:
                if k not in meta:
                    continue
                if con.execute('SELECT 1 FROM meta WHERE key=?', (k,)).fetchone():
                    continue
                con.execute('INSERT INTO meta (key, value) VALUES (?,?)', (k, str(meta[k])))
                settings_n += 1
    for oid in new_ids:
        A._spawn(A.check_offer, oid)
    A.log.info("Wiederherstellung: %d Angebote (+%d übersprungen), %d Reisen, %d Suchen, "
             "%d Reise-Anhänge, %d Packliste-Items, %d KI-Verlauf, %d KI-Einstellungen, "
             "%d Markttrend-Datenpunkte, %d Warenkorb-Tage",
             added, skipped, trips_n, searches_n, attachments_n, packing_n, ai_n, settings_n,
             moves_n, basket_n)
    return jsonify({'added': added, 'skipped': skipped, 'trips': trips_n, 'searches': searches_n,
                    'attachments': attachments_n, 'packing_items': packing_n,
                    'ai_history': ai_n, 'settings': settings_n, 'market_trend': moves_n,
                    'market_basket': basket_n})

