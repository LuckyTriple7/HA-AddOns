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
    'custom_prompt_region_compare_enabled', 'custom_prompt_region_compare_text',
    'custom_prompt_climate_enabled', 'custom_prompt_climate_text',
    'custom_prompt_guide_enabled', 'custom_prompt_guide_text',
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
                f"SELECT {', '.join(A._HISTORY_COLS)} "
                'FROM price_history WHERE offer_id=? ORDER BY ts', (oid,)).fetchall()]
            o['events'] = [{c: e[c] for c in A._EVENT_COLS} for e in con.execute(
                'SELECT ts, type, text FROM offer_events WHERE offer_id=? ORDER BY ts',
                (oid,)).fetchall()]
            o['calendar_history'] = [{'travel_date': h['travel_date'], 'ts': h['ts'],
                                      'price': h['price']} for h in con.execute(
                'SELECT travel_date, ts, price FROM calendar_history '
                'WHERE offer_id=? ORDER BY travel_date, ts', (oid,)).fetchall()]
            offers.append(o)
        trip_rows = con.execute(
            f"SELECT id, {', '.join(A._TRIP_COLUMNS)} FROM trips ORDER BY id").fetchall()
        trips = [{c: t[c] for c in A._TRIP_COLUMNS} for t in trip_rows]
        booking_by_id = {t['id']: (t['booking_code'] or None) for t in trip_rows}
        # Ein Suchabo ist mehr als Name und Suchparameter: `watch` (beobachten?),
        # `max_price` (Schwelle), `seen` (bereits gemeldete Hotels) und `hits` (letzte
        # Treffer) fehlten im Backup — nach einem Restore war das Abo aus und die
        # Schwelle weg, ohne dass es jemandem auffiel.
        searches = [{c: s[c] for c in A._SEARCH_BACKUP_COLS} for s in con.execute(
            f"SELECT {', '.join(A._SEARCH_BACKUP_COLS)} FROM saved_searches "
            'ORDER BY id').fetchall()]
        # Anhänge und Packliste hängen an einer Trip-ID, die den Restore nicht
        # überlebt. Bisher lief die Zuordnung allein über `booking_code` — Reisen
        # ohne Buchungsnummer (Handanlage, Import ohne Nummer) verloren dabei
        # kommentarlos ihre Anhänge und Packlisten. Zusätzlich wandert deshalb
        # `trip_ref` mit: die Position der Reise in der `trips`-Liste desselben
        # Backups. Der Restore baut daraus eine Zuordnung auf die neu vergebenen
        # IDs, `booking_code` bleibt als Rückfallweg für ältere Backups.
        trip_ref_by_id = {t['id']: i for i, t in enumerate(trip_rows)}
        attachments = []
        for a in con.execute(
                'SELECT trip_id, filename, orig_name, created '
                'FROM trip_attachments ORDER BY id').fetchall():
            row = dict(a)
            row['trip_ref'] = trip_ref_by_id.get(row.pop('trip_id'))
            row['booking_code'] = booking_by_id.get(a['trip_id'])
            if row['trip_ref'] is None:
                continue                      # Waise: Reise gibt es nicht (mehr)
            attachments.append(row)
        packing_items = []
        for pi in con.execute(
                'SELECT trip_id, category, label, checked '
                'FROM trip_packing_items ORDER BY id').fetchall():
            row = dict(pi)
            row['trip_ref'] = trip_ref_by_id.get(row.pop('trip_id'))
            row['booking_code'] = booking_by_id.get(pi['trip_id'])
            if row['trip_ref'] is None:
                continue
            packing_items.append(row)
        # `offer_id` als URL mitsichern: die ID wird beim Restore neu vergeben, die
        # URL ist der Schlüssel, über den Angebote ohnehin wiedererkannt werden.
        # Ohne sie verlor der Buchungsscore-Verlauf seine Zuordnung zum Angebot.
        ai_analyses = [dict(r) for r in con.execute(
            'SELECT ai_analyses.kind, ai_analyses.title, ai_analyses.model, '
            'ai_analyses.summary, ai_analyses.usage, ai_analyses.ts, ai_analyses.prompt, '
            'ai_analyses.conversation, offers.url AS offer_url '
            'FROM ai_analyses LEFT JOIN offers ON offers.id = ai_analyses.offer_id '
            'ORDER BY ai_analyses.id').fetchall()]
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
        # Barometer-Tagesbewegungen (Markttrend je gespeicherter Suche): nur die
        # verdichteten Werte, nicht die Roh-Snapshots — die sind groß, werden ohnehin
        # nach 120 Tagen verworfen und entstehen täglich neu. Der Index seit
        # Aufzeichnungsbeginn hängt dagegen allein an diesen Zeilen, deshalb gehören
        # sie ins Backup.
        basket_moves = [dict(r) for r in con.execute(
            'SELECT ts, day, basket, prev_day, gap_days, pct_median, n_matched, n_total '
            'FROM basket_moves ORDER BY day').fetchall()]
        # Klimatabellen und Reiseführer sind KI-Ergebnisse, die je Reiseziel einmal
        # erzeugt und dann dauerhaft behalten werden — sie neu zu erzeugen kostet
        # bares Geld beim KI-Anbieter. Sie gehören damit zu den Nutzdaten, nicht zum
        # Cache (anders als calendar_cache/compare_cache/nights_cache, die sich beim
        # nächsten Abruf von selbst wieder füllen).
        climate = [dict(r) for r in con.execute(
            'SELECT giata, label, ts, model, data FROM climate ORDER BY giata').fetchall()]
        guide = [dict(r) for r in con.execute(
            'SELECT giata, label, ts, model, data FROM guide ORDER BY giata').fetchall()]
        # Öffentliche Angebots-Links samt Besucherkommentaren: nicht rekonstruierbar
        # (der Token steckt in bereits verschickten Links) und fremde Beiträge.
        shares = [dict(r) for r in con.execute(
            'SELECT token, title, note, payload, created_ts, expires_ts, views, '
            'last_view_ts, comments_seen_ts, comments_enabled FROM shares '
            'ORDER BY created_ts').fetchall()]
        share_comments = [dict(r) for r in con.execute(
            'SELECT token, author, text, ts, ip FROM share_comments ORDER BY id').fetchall()]
    data = {'tuiwatch_backup': 8, 'created': datetime.now().isoformat(),
            'offers': offers, 'trips': trips, 'saved_searches': searches,
            'trip_attachments': attachments, 'trip_packing_items': packing_items,
            'ai_analyses': ai_analyses, 'meta': meta, 'price_moves': price_moves,
            'basket_moves': basket_moves, 'climate': climate, 'guide': guide,
            'shares': shares, 'share_comments': share_comments}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('data.json', json.dumps(data, ensure_ascii=False, indent=2))
        # Einstellungen mitnehmen, den Schlüssel dazu bewusst NICHT: Tokens und
        # Passwörter stehen im Backup dadurch nur verschlüsselt. Preis: nach
        # einem Restore auf einer frischen Installation müssen sie einmal neu
        # eingetragen werden.
        sp = Path(A.SETTINGS_PATH)
        if sp.is_file():
            z.write(str(sp), 'settings.json')
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


# Obergrenzen für ein hochgeladenes Restore-Archiv. `MAX_CONTENT_LENGTH` begrenzt
# nur die **komprimierte** Uploadgröße — ein stark komprimiertes ZIP im erlaubten
# Rahmen kann sich beim Entpacken auf ein Vielfaches aufblähen und den Add-on-
# Container über den Speicher abschießen. Die Werte sind großzügig gegenüber einem
# echten Backup (dessen Inhalt ist selbst unkomprimiert nur wenige zehn MB, weil
# schon der Upload bei 16 MB gedeckelt ist) und trotzdem eine harte Schranke.
_RESTORE_MAX_MEMBERS = 2000                     # Dateien im Archiv
_RESTORE_MAX_TOTAL_BYTES = 256 * 1024 * 1024    # entpackt, über alle Mitglieder
_RESTORE_MAX_JSON_BYTES = 32 * 1024 * 1024      # data.json bzw. settings.json einzeln


def _zip_member_bytes(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int,
                      budget: list):
    """Ein ZIP-Mitglied lesen, begrenzt auf `limit` Bytes und auf das verbleibende
    Gesamtbudget. Rückgabe `(blob, grund)`:

    - `(bytes, None)` — gelesen, `budget` ist um die gelesene Menge verringert.
    - `(None, 'member')` — nur diese Datei sprengt ihr Einzel-Limit. Der Aufrufer
      überspringt sie; der Rest der Wiederherstellung bleibt brauchbar.
    - `(None, 'total')` — das Gesamtbudget ist erschöpft. Dann stimmt etwas mit dem
      Archiv als Ganzem nicht und der Aufrufer bricht ab. Welche der beiden Grenzen
      zuerst gegriffen hat, entscheidet `limit <= budget[0]`.
    - `(None, 'unreadable')` — defektes Mitglied, wird übersprungen.

    `info.file_size` wird bewusst **nicht** als Prüfung benutzt: der Wert steht im
    Archiv-Header und ist damit vom Hochladenden gesetzt. Stattdessen wird hart
    `cap + 1` Bytes gelesen und bei Überlänge verworfen — was tatsächlich im
    Speicher landet, ist so unabhängig von den Angaben im Archiv gedeckelt.

    `budget` ist eine Ein-Element-Liste mit den noch erlaubten Gesamt-Bytes. Ohne
    diese Summe könnte ein Archiv das Einzel-Limit beliebig oft ausschöpfen."""
    cap = max(min(limit, budget[0]), 0)
    try:
        with zf.open(info) as fh:
            blob = fh.read(cap + 1)
    except (zipfile.BadZipFile, OSError, EOFError, ValueError) as e:
        A.log.warning("Wiederherstellung: %s nicht lesbar (%s)", info.filename, e)
        return None, 'unreadable'
    if len(blob) > cap:
        return None, ('member' if limit <= budget[0] else 'total')
    budget[0] -= len(blob)
    return blob, None


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
        # Preis-Split und vac_ok kommen erst ab Backup-Version 8 mit; ältere
        # Backups liefern dort schlicht None, was der Spalten-Semantik entspricht
        # („nicht erhoben" bzw. „unbekannt").
        con.execute(
            'INSERT INTO price_history (offer_id, ts, price, old_price, discount, '
            'available, ok, note, price_hotel, price_flight_out, price_flight_ret, '
            'vac_ok) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (oid, int(h.get('ts') or 0), h.get('price'), h.get('old_price'),
             h.get('discount'), h.get('available'),
             1 if h.get('ok') else 0, (h.get('note') or ''),
             h.get('price_hotel'), h.get('price_flight_out'), h.get('price_flight_ret'),
             h.get('vac_ok')))
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
    settings_raw: bytes | None = None
    data = None
    if raw:
        if raw[:2] == b'PK':                       # ZIP-Archiv
            budget = [_RESTORE_MAX_TOTAL_BYTES]
            try:
                zf = zipfile.ZipFile(io.BytesIO(raw))
                members = [i for i in zf.infolist() if not i.is_dir()]
                if len(members) > _RESTORE_MAX_MEMBERS:
                    A.log.warning("Wiederherstellung abgelehnt: %d Dateien im Archiv "
                                  "(erlaubt: %d)", len(members), _RESTORE_MAX_MEMBERS)
                    return jsonify({'error': 'too_large'}), 413
                blob, why = _zip_member_bytes(zf, zf.getinfo('data.json'),
                                              _RESTORE_MAX_JSON_BYTES, budget)
                if blob is None:
                    A.log.warning("Wiederherstellung abgelehnt: data.json zu groß (%s)", why)
                    return jsonify({'error': 'too_large'}), 413
                data = json.loads(blob.decode('utf-8'))
            except (zipfile.BadZipFile, KeyError, ValueError, UnicodeDecodeError):
                return jsonify({'error': 'invalid'}), 400
            for info in members:
                name = info.filename
                if name.startswith('trips/') or name.startswith('attachments/'):
                    base = Path(name).name
                    if not base.lower().endswith('.pdf'):
                        continue
                    blob, why = _zip_member_bytes(zf, info, A.MAX_PDF_BYTES, budget)
                elif name == 'settings.json':
                    blob, why = _zip_member_bytes(zf, info, _RESTORE_MAX_JSON_BYTES, budget)
                else:
                    continue
                if why == 'total':
                    # Nicht nur diese Datei ist zu groß, das Archiv sprengt insgesamt
                    # den Rahmen. Weiterlesen hieße, dem Archiv beim Vollaufen des
                    # Speichers zuzusehen — hier ist Schluss.
                    A.log.warning("Wiederherstellung abgelehnt: entpackter Inhalt über "
                                  "%d Bytes (bei %s)", _RESTORE_MAX_TOTAL_BYTES, name)
                    return jsonify({'error': 'too_large'}), 413
                if blob is None:
                    # Einzelne zu große oder defekte Datei: überspringen statt das
                    # ganze Backup zu verwerfen — der Rest ist weiterhin brauchbar.
                    A.log.warning("Wiederherstellung: %s übersprungen (%s)", name, why)
                    continue
                if name == 'settings.json':
                    settings_raw = blob
                elif name.startswith('trips/'):
                    pdfs[Path(name).name] = blob
                else:
                    att_pdfs[Path(name).name] = blob
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
    basket_moves = data.get('basket_moves') or []   # erst ab Backup-Version 7 nutzbar
    climate = data.get('climate') or []             # erst ab Backup-Version 8
    guide = data.get('guide') or []
    shares = data.get('shares') or []
    share_comments = data.get('share_comments') or []
    added, skipped, new_ids = 0, 0, []
    trips_n, searches_n, attachments_n, packing_n, ai_n, settings_n, moves_n = 0, 0, 0, 0, 0, 0, 0
    basket_n = shares_n = comments_n = 0
    climate_n = {'climate': 0, 'guide': 0}
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
        # Position der Reise im Backup -> ihre ID in dieser Datenbank. Anhänge und
        # Packlisten hängen daran; ohne diese Zuordnung wären sie nur über die
        # Buchungsnummer zu finden und Reisen ohne Nummer gingen leer aus.
        trip_id_by_ref: dict[int, int] = {}
        if isinstance(trips, list) and trips:
            Path(A.TRIPS_DIR).mkdir(parents=True, exist_ok=True)
            for ref, t in enumerate(trips):
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
                    trip_id_by_ref[ref] = ex['id']
                    trips_n += 1
                    continue
                try:
                    cur = con.execute(
                        f"INSERT INTO trips ({', '.join(A._TRIP_COLUMNS)}) "
                        f"VALUES ({', '.join('?' for _ in A._TRIP_COLUMNS)})", vals)
                    trip_id_by_ref[ref] = cur.lastrowid
                    trips_n += 1
                except sqlite3.IntegrityError:
                    pass

        def _trip_id_for(row: dict):
            """Reise zu einem Anhang/Packlisten-Eintrag finden: erst über die
            Position im selben Backup (ab Version 8, funktioniert auch ohne
            Buchungsnummer), sonst über die Buchungsnummer wie in älteren
            Backups."""
            ref = row.get('trip_ref')
            if isinstance(ref, int) and ref in trip_id_by_ref:
                return trip_id_by_ref[ref]
            booking = (row.get('booking_code') or '').strip()
            if not booking:
                return None
            hit = con.execute('SELECT id FROM trips WHERE booking_code=?',
                              (booking,)).fetchone()
            return hit['id'] if hit else None
        if isinstance(trip_attachments, list) and trip_attachments:
            Path(A.TRIPS_DIR).mkdir(parents=True, exist_ok=True)
            for a in trip_attachments:
                if not isinstance(a, dict):
                    continue
                filename = (a.get('filename') or '').strip()
                orig_name = (a.get('orig_name') or '').strip()
                if not filename or not orig_name:
                    continue
                trip_id = _trip_id_for(a)
                if trip_id is None:
                    continue
                exists = con.execute(
                    'SELECT id FROM trip_attachments WHERE trip_id=? AND filename=?',
                    (trip_id, filename)).fetchone()
                if exists:
                    continue
                if filename in att_pdfs:
                    p = A._trip_pdf_path(filename)
                    if p:
                        p.write_bytes(att_pdfs[filename])
                con.execute(
                    'INSERT INTO trip_attachments (trip_id, filename, orig_name, created) '
                    'VALUES (?,?,?,?)',
                    (trip_id, filename, orig_name, int(a.get('created') or time.time())))
                attachments_n += 1
        if isinstance(packing_items, list) and packing_items:
            for pi in packing_items:
                if not isinstance(pi, dict):
                    continue
                category = (pi.get('category') or '').strip()
                label = (pi.get('label') or '').strip()
                if not category or not label:
                    continue
                trip_id = _trip_id_for(pi)
                if trip_id is None:
                    continue
                exists = con.execute(
                    'SELECT id FROM trip_packing_items WHERE trip_id=? AND category=? AND label=?',
                    (trip_id, category, label)).fetchone()
                if exists:
                    continue
                con.execute(
                    'INSERT INTO trip_packing_items (trip_id, category, label, checked, created) '
                    'VALUES (?,?,?,?,?)',
                    (trip_id, category, label, 1 if pi.get('checked') else 0, int(time.time())))
                con.execute('UPDATE trips SET packing_seeded=1 WHERE id=?', (trip_id,))
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
                watch = 1 if s.get('watch') else 0
                max_price = s.get('max_price')
                try:
                    max_price = float(max_price) if max_price not in (None, '') else None
                except (TypeError, ValueError):
                    max_price = None
                seen = s.get('seen') if isinstance(s.get('seen'), str) else '{}'
                hits = s.get('hits') if isinstance(s.get('hits'), str) else '[]'
                last_checked = s.get('last_checked')
                ex = con.execute('SELECT id, watch FROM saved_searches WHERE name=?',
                                 (name,)).fetchone()
                if ex:
                    con.execute('UPDATE saved_searches SET payload=?, ts=? WHERE id=?',
                                (payload, ts, ex['id']))
                    # Ein hier bereits laufendes Abo bleibt unangetastet: `seen` aus
                    # einem älteren Backup würde sonst schon gemeldete Hotels erneut
                    # melden. Nur ein lokal abgeschaltetes Abo nimmt die Einstellung
                    # aus dem Backup an — sonst wäre das Abo nach einem Restore auf
                    # einer frischen Installation stillschweigend aus.
                    if not ex['watch'] and watch:
                        con.execute('UPDATE saved_searches SET watch=?, max_price=?, '
                                    'last_checked=?, seen=?, hits=? WHERE id=?',
                                    (watch, max_price, last_checked, seen, hits, ex['id']))
                else:
                    con.execute('INSERT INTO saved_searches (name, payload, ts, watch, '
                                'max_price, last_checked, seen, hits) VALUES (?,?,?,?,?,?,?,?)',
                                (name, payload, ts, watch, max_price, last_checked, seen, hits))
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
                # Die offer_id aus dem Backup ist wertlos (IDs werden neu vergeben);
                # die mitgesicherte URL ist der Schlüssel. Findet sich das Angebot
                # hier nicht, bleibt der Eintrag ohne Zuordnung erhalten statt
                # verworfen zu werden — der Text ist auch allein noch etwas wert.
                offer_url = (a.get('offer_url') or '').strip()
                offer_row = (con.execute('SELECT id FROM offers WHERE url=?',
                                         (offer_url,)).fetchone() if offer_url else None)
                con.execute(
                    'INSERT INTO ai_analyses (kind, title, model, summary, usage, ts, prompt, '
                    'conversation, offer_id) VALUES (?,?,?,?,?,?,?,?,?)',
                    (kind, title, a.get('model'), a.get('summary'), a.get('usage'), ts,
                     a.get('prompt') or '', a.get('conversation') or '',
                     offer_row['id'] if offer_row else None))
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
            # (basket, day) ist eindeutig — vorhandene Tage bleiben unangetastet
            # (nicht-destruktiv wie der übrige Restore), fehlende kommen dazu.
            # Backup-Version 6 schlüsselte noch nach `region` (Preisbarometer je Region,
            # konstante Vorlaufzeit). Diese Werte haben eine andere Preisbasis und
            # dürfen nicht mit den heutigen verkettet werden — sie werden ignoriert.
            existing_days = {(r['basket'], r['day']) for r in con.execute(
                'SELECT basket, day FROM basket_moves').fetchall()}
            skipped_v6 = 0
            for bm in basket_moves:
                if not isinstance(bm, dict) or bm.get('pct_median') is None:
                    continue
                if 'basket' not in bm:
                    skipped_v6 += 1
                    continue
                key = (bm.get('basket') or '', bm.get('day') or '')
                if not key[1] or key in existing_days:
                    continue
                con.execute(
                    'INSERT INTO basket_moves (ts, day, basket, prev_day, gap_days, '
                    'pct_median, n_matched, n_total) VALUES (?,?,?,?,?,?,?,?)',
                    (int(bm.get('ts') or 0), key[1], key[0], bm.get('prev_day') or '',
                     bm.get('gap_days') or 1, bm['pct_median'],
                     int(bm.get('n_matched') or 0), int(bm.get('n_total') or 0)))
                existing_days.add(key)
                basket_n += 1
            if skipped_v6:
                A.log.info("Wiederherstellung: %d Barometer-Tage aus einem älteren "
                           "Backup übersprungen (andere Preisbasis)", skipped_v6)
        # Klimatabellen/Reiseführer: je Reiseziel ein Datensatz. Nicht-destruktiv —
        # ein lokal vorhandener (womöglich frischerer) Eintrag bleibt stehen.
        for table, rows in (('climate', climate), ('guide', guide)):
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict) or row.get('giata') is None or not row.get('data'):
                    continue
                try:
                    giata = int(row['giata'])
                except (TypeError, ValueError):
                    continue
                if con.execute(f'SELECT 1 FROM {table} WHERE giata=?', (giata,)).fetchone():
                    continue
                con.execute(
                    f'INSERT INTO {table} (giata, label, ts, model, data) VALUES (?,?,?,?,?)',
                    (giata, row.get('label') or '', int(row.get('ts') or 0),
                     row.get('model') or '', str(row['data'])))
                climate_n[table] += 1
        # Share-Links: der Token steckt in bereits verschickten Links und lässt sich
        # nicht neu erzeugen — ein vorhandener Token bleibt deshalb unangetastet.
        if isinstance(shares, list):
            for sh in shares:
                if not isinstance(sh, dict):
                    continue
                token = (sh.get('token') or '').strip()
                if not token or not sh.get('payload'):
                    continue
                if con.execute('SELECT 1 FROM shares WHERE token=?', (token,)).fetchone():
                    continue
                con.execute(
                    'INSERT INTO shares (token, title, note, payload, created_ts, expires_ts, '
                    'views, last_view_ts, comments_seen_ts, comments_enabled) '
                    'VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (token, sh.get('title') or '', sh.get('note') or '', str(sh['payload']),
                     int(sh.get('created_ts') or 0), int(sh.get('expires_ts') or 0),
                     int(sh.get('views') or 0), sh.get('last_view_ts'),
                     int(sh.get('comments_seen_ts') or 0),
                     0 if sh.get('comments_enabled') == 0 else 1))
                shares_n += 1
        # Kommentare nur zu Links, die es hier gibt — sonst wären sie unerreichbar.
        # Dedup über (token, ts, text): fremde Beiträge haben keine stabile eigene ID.
        if isinstance(share_comments, list) and share_comments:
            known_tokens = {r['token'] for r in con.execute(
                'SELECT token FROM shares').fetchall()}
            existing_comments = {(r['token'], r['ts'], r['text']) for r in con.execute(
                'SELECT token, ts, text FROM share_comments').fetchall()}
            for cm in share_comments:
                if not isinstance(cm, dict):
                    continue
                token = (cm.get('token') or '').strip()
                text = cm.get('text') or ''
                if not token or not text or token not in known_tokens:
                    continue
                key = (token, int(cm.get('ts') or 0), text)
                if key in existing_comments:
                    continue
                con.execute(
                    'INSERT INTO share_comments (token, author, text, ts, ip) '
                    'VALUES (?,?,?,?,?)',
                    (token, cm.get('author') or '', text, key[1], cm.get('ip') or ''))
                existing_comments.add(key)
                comments_n += 1
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
    # Einstellungen: wie der übrige Restore nicht-destruktiv — eine vorhandene
    # settings.json bleibt unangetastet. Die geheimen Felder aus dem Backup sind
    # nur lesbar, wenn settings.key noch derselbe ist (er liegt bewusst nicht im
    # Backup); andernfalls stehen sie danach leer da und müssen neu eingetragen
    # werden. Das meldet settings.py beim Entschlüsseln im Log.
    settings_restored = False
    if settings_raw and not A.settings_store.exists():
        try:
            json.loads(settings_raw.decode('utf-8'))   # muss valides JSON sein
            with open(A.SETTINGS_PATH, 'wb') as f:
                f.write(settings_raw)
            A.settings_store.reset_cache()
            A._settings_changed()
            settings_restored = True
            A.log.info("Wiederherstellung: Einstellungen aus dem Backup übernommen")
        except (ValueError, UnicodeDecodeError, OSError) as e:
            A.log.warning("Einstellungen aus dem Backup nicht übernommen: %s", e)

    for oid in new_ids:
        A._spawn(A.check_offer, oid)
    A.log.info("Wiederherstellung: %d Angebote (+%d übersprungen), %d Reisen, %d Suchen, "
             "%d Reise-Anhänge, %d Packliste-Items, %d KI-Verlauf, %d KI-Einstellungen, "
             "%d Markttrend-Datenpunkte, %d Barometer-Tage, %d Klimatabellen, "
             "%d Reiseführer, %d Share-Links, %d Kommentare",
             added, skipped, trips_n, searches_n, attachments_n, packing_n, ai_n, settings_n,
             moves_n, basket_n, climate_n['climate'], climate_n['guide'], shares_n, comments_n)
    return jsonify({'added': added, 'skipped': skipped, 'trips': trips_n, 'searches': searches_n,
                    'attachments': attachments_n, 'packing_items': packing_n,
                    'ai_history': ai_n, 'settings': settings_n, 'market_trend': moves_n,
                    'market_basket': basket_n, 'climate': climate_n['climate'],
                    'guide': climate_n['guide'], 'shares': shares_n, 'share_comments': comments_n,
                    'options_restored': settings_restored})

