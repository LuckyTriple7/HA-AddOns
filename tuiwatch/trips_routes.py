"""Flask-Blueprint: Reisen-Datenbank (gebuchte Reisen via PDF-Import) — Routen +
reisen-spezifische Helfer, ausgelagert aus app.py (Backlog #12, Wartbarkeit).

Geteilte Primitiven (db, log, KI-Client, PDF-Parser, Pfade) werden bewusst über
`import app as A` mit SPÄTEM Attribut-Zugriff genutzt: so bleiben die
Test-Monkeypatches auf dem app-Namespace wirksam (z. B. m.parse_tui_pdf,
m._ai_request, m.extract_pdf_text) und es gibt keinen Import-Zyklus — app.py
importiert dieses Modul erst ganz am Ende und registriert dann das Blueprint.
"""
import io
import json
import re
import secrets
import time
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

import app as A

bp = Blueprint('trips', __name__)


@bp.route('/api/trips/next', methods=['GET'])
def api_trips_next():
    """Nächste bevorstehende Reise fürs Header-Countdown (ohne PII wie Reisende/Preise)."""
    if (err := A._require_api()):
        return err
    return jsonify({'trip': A._next_trip()})


@bp.route('/api/trips', methods=['GET'])
def api_trips():
    """Liste gebuchter Reisen + aggregierte Statistik."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        rows = con.execute(
            'SELECT id, booking_code, booking_date, title, destination, hotel, '
            'hotel_code, start_date, end_date, nights, travellers, total_price, '
            'package_price, net_per_night, meal, pdf_name, orig_name FROM trips '
            'ORDER BY start_date DESC, id DESC').fetchall()
    trips = [dict(r) for r in rows]
    for t in trips:
        t['has_pdf'] = bool(t.get('pdf_name'))
    nights_sum = sum((t['nights'] or 0) for t in trips)
    total_sum = sum((t['total_price'] or 0.0) for t in trips)
    package_sum = sum((t['package_price'] or 0.0) for t in trips)
    # Eigener Anteil je Reise = Gesamtpreis / Anzahl Reisende, aufsummiert.
    own_sum = sum((t['total_price'] or 0.0) / (t['travellers'] or 1) for t in trips)
    # Personen-Nächte (Nächte × Reisende) → Ø-Preis pro Person und Nacht, damit Solo- und
    # Gruppenreisen vergleichbar sind.
    pers_nights = sum((t['nights'] or 0) * (t['travellers'] or 1) for t in trips)
    stats = {
        'count': len(trips),
        'nights_sum': nights_sum,
        'total_sum': round(total_sum, 2),
        'own_sum': round(own_sum, 2),
        'package_sum': round(package_sum, 2),
        'avg_per_night': round(total_sum / pers_nights, 2) if pers_nights else 0.0,
    }
    # Aufschlüsselung pro Reisejahr (nach Reisebeginn)
    years: dict = {}
    for t in trips:
        y = (t['start_date'] or '')[:4]
        if not y:
            continue
        a = years.setdefault(y, {'year': y, 'count': 0, 'nights_sum': 0,
                                 'total_sum': 0.0, 'own_sum': 0.0, '_pn': 0})
        a['count'] += 1
        a['nights_sum'] += t['nights'] or 0
        a['total_sum'] += t['total_price'] or 0.0
        a['own_sum'] += (t['total_price'] or 0.0) / (t['travellers'] or 1)
        a['_pn'] += (t['nights'] or 0) * (t['travellers'] or 1)
    by_year = []
    for y in sorted(years, reverse=True):
        a = years[y]
        pn = a.pop('_pn')
        a['total_sum'] = round(a['total_sum'], 2)
        a['own_sum'] = round(a['own_sum'], 2)
        a['avg_per_night'] = round(a['total_sum'] / pn, 2) if pn else 0.0
        by_year.append(a)
    return jsonify({'trips': trips, 'stats': stats, 'by_year': by_year})


@bp.route('/api/trips/<int:tid>', methods=['GET'])
def api_trip_detail(tid):
    """Vollständige Detaildaten einer Reise (geparstes JSON)."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        row = con.execute('SELECT * FROM trips WHERE id=?', (tid,)).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    trip = dict(row)
    try:
        trip['data'] = json.loads(trip.get('data') or '{}')
    except Exception:
        trip['data'] = {}
    trip['has_pdf'] = bool(trip.get('pdf_name'))
    trip['warnings'] = A.check_fields(trip['data'])
    with A.db() as con:
        atts = con.execute(
            'SELECT id, orig_name, created FROM trip_attachments WHERE trip_id=? ORDER BY id',
            (tid,)).fetchall()
        if not row['packing_seeded']:
            con.executemany(
                'INSERT INTO trip_packing_items '
                '(trip_id, category, label, checked, created) VALUES (?,?,?,?,?)',
                [(tid,) + r for r in A.default_packing_rows(int(time.time()), _packing_template())])
            con.execute('UPDATE trips SET packing_seeded=1 WHERE id=?', (tid,))
        packing = con.execute(
            'SELECT id, category, label, checked FROM trip_packing_items '
            'WHERE trip_id=? ORDER BY id', (tid,)).fetchall()
    trip['attachments'] = [dict(a) for a in atts]
    trip['packing'] = [dict(p) for p in packing]
    return jsonify(trip)


# Alle Feld-Labels, die check_fields() melden kann — für die „erkannt/leer"-Übersicht
# im Debug-Modus (feste Reihenfolge wie im PDF).
_TRIP_FIELD_LABELS = ('Buchungsnummer', 'Buchungsdatum', 'Reiseziel', 'Hotel',
                      'Reisezeitraum', 'Nächte', 'Verpflegung', 'Gesamtpreis',
                      'Reisende', 'Flüge', 'Hinflug', 'Rückflug')

# Label → Manual-Override-Key(s) für die ✍️-Markierung der Feld-Chips in der
# Debug-Ansicht (Flüge/Hinflug/Rückflug sind nicht manuell setzbar → kein Eintrag).
_TRIP_LABEL_MANUAL_KEYS = {
    'Buchungsnummer': ('buchungsnummer',), 'Buchungsdatum': ('buchungsdatum',),
    'Reiseziel': ('reiseziel',), 'Hotel': ('hotel_name',),
    'Reisezeitraum': ('reisezeitraum_von', 'reisezeitraum_bis'),
    'Nächte': ('naechte',), 'Verpflegung': ('verpflegung',),
    'Gesamtpreis': ('gesamtpreis',), 'Reisende': ('reisende_anzahl',),
}


def _trip_debug_payload(raw: bytes, manual: dict | None = None) -> dict:
    """Debug-Sicht auf eine Reise-PDF: bereinigter Volltext (Basis der Feld-Regexes),
    geparstes JSON, Warnungen und je Feld erkannt/leer/manuell. Inhalte können PII
    enthalten — sie gehen nur an den (authentifizierten) Aufrufer, nichts ins Log."""
    try:
        full = A.extract_pdf_text(io.BytesIO(raw))
    except Exception:
        return {'ok': False, 'error': 'text_failed'}
    cleaned = A._clean_text(full)
    data, parse_error = None, None
    try:
        data = A.parse_tui_text(full)
    except Exception as exc:
        parse_error = type(exc).__name__
    if data is not None and manual:
        data['_manual'] = dict(manual)
        _apply_manual_overrides(data)
    warnings = A.check_fields(data) if data else list(_TRIP_FIELD_LABELS)
    fields = [{'label': lbl, 'ok': lbl not in warnings,
               'manual': any(k in (manual or {}) for k in _TRIP_LABEL_MANUAL_KEYS.get(lbl, ()))}
              for lbl in _TRIP_FIELD_LABELS]
    return {'ok': True, 'cleaned_text': cleaned, 'data': data,
            'parse_error': parse_error, 'warnings': warnings, 'fields': fields,
            'manual': manual or {}}


@bp.route('/api/trips/<int:tid>/debug', methods=['GET'])
def api_trip_debug(tid):
    """Debug-Modus zu einer gespeicherten Reise-PDF (bereinigter Text + Parse-Ergebnis).
    Hilft, bei einer TUI-Layout-Änderung zu sehen, WARUM ein Feld nicht erkannt wurde."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        row = con.execute('SELECT pdf_name, data FROM trips WHERE id=?', (tid,)).fetchone()
    if not row or not row['pdf_name']:
        return jsonify({'error': 'not_found'}), 404
    p = A._trip_pdf_path(row['pdf_name'])
    if p is None or not p.exists():
        return jsonify({'error': 'not_found'}), 404
    return jsonify(_trip_debug_payload(p.read_bytes(), manual=_trip_manual(row['data'])))


@bp.route('/api/trips/debug', methods=['POST'])
def api_trip_debug_upload():
    """Debug-Modus für eine hochgeladene PDF, OHNE sie zu speichern — z. B. wenn der
    Import mit „nicht lesbar" fehlschlägt."""
    if (err := A._require_api()):
        return err
    file = request.files.get('pdf')
    if file is None or not file.filename:
        return jsonify({'error': 'no_file'}), 400
    raw = file.read()
    if not raw:
        return jsonify({'error': 'empty'}), 400
    if len(raw) > A.MAX_PDF_BYTES:
        return jsonify({'error': 'too_large'}), 413
    return jsonify(_trip_debug_payload(raw))


_AI_TRIP_FIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "buchungsnummer": {"type": ["string", "null"]},
        "buchungsdatum": {"type": ["string", "null"]},
        "reiseziel": {"type": ["string", "null"]},
        "hotel_name": {"type": ["string", "null"]},
        "reisezeitraum_von": {"type": ["string", "null"],
                              "description": "Anreisedatum, Format TT.MM.JJJJ"},
        "reisezeitraum_bis": {"type": ["string", "null"],
                              "description": "Abreisedatum, Format TT.MM.JJJJ"},
        "naechte": {"type": ["integer", "null"]},
        "verpflegung": {"type": ["string", "null"]},
        "gesamtpreis": {"type": ["string", "null"],
                       "description": "Format '1.234,56' (deutsches Zahlenformat, ohne €)"},
        "reisende_anzahl": {"type": ["integer", "null"]},
    },
    "required": ["buchungsnummer", "buchungsdatum", "reiseziel", "hotel_name",
                "reisezeitraum_von", "reisezeitraum_bis", "naechte", "verpflegung",
                "gesamtpreis", "reisende_anzahl"],
    "additionalProperties": False,
}


def _ai_fill_trip_fields(data: dict, warnings: list, cleaned_text: str,
                         api_key: str, model: str) -> tuple[dict, list]:
    """Ergänzt NUR die von `check_fields()` als fehlend markierte Top-Level-Felder
    per KI aus dem PDF-Text — überschreibt nie bereits vom Regex-Parser erkannte
    Werte (der bleibt die primäre, vertrauenswürdigere Quelle). Fällt TUI-Text ohne
    Key/Fehler auf die unveränderten Regex-Daten zurück. Rückgabe: (data, filled_labels)."""
    if not warnings or not api_key:
        return data, []
    prompt = (
        "Extrahiere aus folgendem Text einer TUI-Reisebestätigung NUR diese Felder "
        "als JSON. Fehlt eine Information wirklich, gib null zurück statt zu raten "
        "oder zu erfinden.\n\n" + cleaned_text[:6000]
    )
    try:
        text, usage, code = A._ai_request(api_key, model, prompt, max_tokens=800,
                                        log_ctx="PDF-Fallback", use_web_search=False,
                                        output_schema=_AI_TRIP_FIELD_SCHEMA)
        if code or not text:
            return data, []
        ai = json.loads(text)
        usage['estimated_usd'] = A._ai_call_cost(model, usage)
        A._record_ai_usage(model, usage)
    except Exception as e:
        A.log.warning("PDF-Fallback (KI) fehlgeschlagen: %s", e)
        return data, []

    filled = []
    _AI_FILL_MAP = (("Buchungsnummer", 'buchungsnummer'), ("Buchungsdatum", 'buchungsdatum'),
                    ("Reiseziel", 'reiseziel'), ("Hotel", 'hotel_name'),
                    ("Nächte", 'naechte'), ("Verpflegung", 'verpflegung'),
                    ("Gesamtpreis", 'gesamtpreis'), ("Reisende", 'reisende_anzahl'))
    for label, key in _AI_FILL_MAP:
        if label in warnings and ai.get(key):
            _set_trip_field(data, key, ai[key])
            filled.append(label)
    if "Reisezeitraum" in warnings and ai.get('reisezeitraum_von') and ai.get('reisezeitraum_bis'):
        _set_trip_field(data, 'reisezeitraum_von', ai['reisezeitraum_von'])
        _set_trip_field(data, 'reisezeitraum_bis', ai['reisezeitraum_bis'])
        filled.append("Reisezeitraum")
    return data, filled


# Manuell überschreibbare Felder (Debug-Ansicht „Felder manuell zuordnen"):
# die Schema-Keys des KI-Fallbacks + Zahlungsfelder + Extras-/Rabatte-Listen +
# rabatt_inklusive (Rabatt steckt schon im Reisepreis, siehe apply_derived_fields).
_MANUAL_TRIP_KEYS = frozenset({
    'buchungsnummer', 'buchungsdatum', 'reiseziel', 'hotel_name',
    'reisezeitraum_von', 'reisezeitraum_bis', 'naechte', 'verpflegung',
    'gesamtpreis', 'reisende_anzahl', 'anzahlung_betrag', 'anzahlung_faelligkeit',
    'restzahlung_betrag', 'restzahlung_faelligkeit', 'extras', 'rabatte',
    'rabatt_inklusive',
})


def _set_trip_field(data: dict, key: str, value) -> None:
    """DIE eine Mapping-Stelle Schema-Key → data-Dict-Struktur — von KI-Fallback
    (`_ai_fill_trip_fields`) und manuellen Overrides (`_apply_manual_overrides`)
    gemeinsam genutzt, damit das Mapping nicht auseinanderläuft."""
    if key == 'hotel_name':
        data.setdefault('hotel', {})['name'] = value
    elif key == 'reisezeitraum_von':
        data.setdefault('reisezeitraum', {})['von'] = value
    elif key == 'reisezeitraum_bis':
        data.setdefault('reisezeitraum', {})['bis'] = value
    elif key == 'anzahlung_betrag':
        data.setdefault('anzahlung', {})['betrag'] = value
    elif key == 'anzahlung_faelligkeit':
        data.setdefault('anzahlung', {})['faelligkeit'] = value
    elif key == 'restzahlung_betrag':
        data.setdefault('restzahlung', {})['betrag'] = value
    elif key == 'restzahlung_faelligkeit':
        data.setdefault('restzahlung', {})['faelligkeit'] = value
    elif key == 'reisende_anzahl':
        # nur die Anzahl zählt für `travellers` beim Import — keine synthetischen Namen
        data['reisende'] = [{} for _ in range(int(value))]
    else:
        # buchungsnummer, buchungsdatum, reiseziel, naechte, verpflegung,
        # gesamtpreis, extras, rabatte, rabatt_inklusive
        data[key] = value


def _apply_manual_overrides(data: dict) -> dict:
    """Wendet die in data['_manual'] gespeicherten manuellen Feld-Overrides an und
    berechnet die abgeleiteten Felder neu. Overrides schlagen Parser-Ergebnis —
    Ausnahme `reisende_anzahl`: nie echte, vom Parser erkannte Reisende (Namen/
    Geburtsdaten) durch anonyme Platzhalter ersetzen."""
    for key, val in (data.get('_manual') or {}).items():
        if key not in _MANUAL_TRIP_KEYS or val in (None, '', []):
            continue
        if key == 'reisende_anzahl' and data.get('reisende'):
            continue
        _set_trip_field(data, key, val)
    return A.apply_derived_fields(data)


def _trip_manual(data_json) -> dict:
    """Extrahiert das Manual-Override-Dict aus der gespeicherten data-JSON einer
    Reise (Whitelist-gefiltert; robust gegen kaputtes/leeres JSON)."""
    try:
        manual = (json.loads(data_json or '{}') or {}).get('_manual') or {}
    except (ValueError, TypeError):
        return {}
    return {k: v for k, v in manual.items() if k in _MANUAL_TRIP_KEYS}


def _parse_trip_pdf_bytes(raw: bytes, manual: dict | None = None, use_ai: bool = True):
    """Parst Reise-PDF-Bytes: Regex-Parser → manuelle Overrides (falls vorhanden;
    schlagen Parser-Ergebnis) → KI-Fallback nur für danach noch fehlende Felder
    (überschreibt nie erkannte/manuelle Werte; best effort — ohne Key oder bei
    Fehlern bleiben die Daten unverändert). Rückgabe: (data, ai_filled);
    Parser-Exceptions propagieren zum Aufrufer."""
    data = A.parse_tui_pdf(io.BytesIO(raw))
    data.pop('_manual', None)   # frisch geparst kennt keine Overrides — nur `manual` zählt
    if manual:
        data['_manual'] = dict(manual)
        _apply_manual_overrides(data)
    ai_filled = []
    pre_warnings = A.check_fields(data)
    ai_key, ai_model = A._ai_config()
    if use_ai and pre_warnings and ai_key:
        try:
            cleaned = A._clean_text(A.extract_pdf_text(io.BytesIO(raw)))
            data, ai_filled = _ai_fill_trip_fields(data, pre_warnings, cleaned, ai_key, ai_model)
        except Exception as e:
            A.log.warning("PDF-Fallback (KI) fehlgeschlagen: %s", e)
        if ai_filled:
            A.log.info("Reise-Import: KI-Fallback ergänzte %s", ", ".join(ai_filled))
            A.apply_derived_fields(data)   # z. B. Paketpreis nach KI-Gesamtpreis
    return data, ai_filled


def _trip_row(data: dict, pdf_name: str, orig_name: str, created: int) -> dict:
    """Baut die trips-Zeile (Spalten = _TRIP_COLUMNS) aus dem Parse-Ergebnis."""
    booking = (data.get('buchungsnummer') or '').strip()
    return {
        'booking_code': booking or None,
        'booking_date': data.get('buchungsdatum'),
        'title': A._trip_title(data),
        'destination': data.get('reiseziel'),
        'hotel': (data.get('hotel') or {}).get('name'),
        'hotel_code': (data.get('hotel') or {}).get('code'),
        'start_date': A._iso_date((data.get('reisezeitraum') or {}).get('von')),
        'end_date': A._iso_date((data.get('reisezeitraum') or {}).get('bis')),
        'nights': data.get('naechte'),
        'travellers': len(data.get('reisende') or []) or None,
        'total_price': A._parse_eur_num(data.get('gesamtpreis')),
        'package_price': A._parse_eur_num(data.get('paketpreis')),
        'net_per_night': A._parse_eur_num(data.get('preis_pro_person_nacht_paket')),
        'meal': data.get('verpflegung'),
        'data': json.dumps(data, ensure_ascii=False),
        'pdf_name': pdf_name,
        'orig_name': orig_name,
        'created': created,
    }


@bp.route('/api/trips/import', methods=['POST'])
def api_trip_import():
    """TUI-Reisebestätigungs-PDF hochladen, parsen, dauerhaft speichern (Upsert
    per Buchungsnummer)."""
    if (err := A._require_api()):
        return err
    file = request.files.get('pdf')
    if file is None or not file.filename:
        return jsonify({'error': 'no_file'}), 400
    if Path(file.filename).suffix.lower() != '.pdf':
        return jsonify({'error': 'not_pdf'}), 400

    raw = file.read()
    if not raw:
        return jsonify({'error': 'empty'}), 400
    if len(raw) > A.MAX_PDF_BYTES:
        return jsonify({'error': 'too_large'}), 413

    try:
        data, ai_filled = _parse_trip_pdf_bytes(raw)
    except Exception as exc:
        A.log.warning("PDF-Import fehlgeschlagen: %s", exc)
        return jsonify({'error': 'parse_failed'}), 422

    booking = (data.get('buchungsnummer') or '').strip()
    ts = int(time.time())
    pdf_name = f"{booking or ('trip_' + str(ts))}.pdf"
    target = A._trip_pdf_path(pdf_name)
    if target is None:
        return jsonify({'error': 'bad_name'}), 400

    Path(A.TRIPS_DIR).mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(raw)
    except OSError as exc:
        A.log.warning("PDF speichern fehlgeschlagen: %s", exc)
        return jsonify({'error': 'store_failed'}), 500

    existing = None
    if booking:
        with A.db() as con:
            existing = con.execute(
                'SELECT id, pdf_name, data FROM trips WHERE booking_code=?',
                (booking,)).fetchone()
    if existing:
        # Manuelle Feld-Overrides des bestehenden Datensatzes überleben den
        # Re-Import (Upsert): erneut anwenden — sie schlagen das Parser-Ergebnis.
        manual = _trip_manual(existing['data'])
        if manual:
            data['_manual'] = manual
            _apply_manual_overrides(data)
    row = _trip_row(data, pdf_name, Path(file.filename).name, ts)
    # Feste Whitelist der Spalten (konstant im Code, NICHT aus row.keys() abgeleitet),
    # damit die SQL-Struktur nicht von request-nahen Daten abhängt. Reihenfolge fix.
    cols = A._TRIP_COLUMNS
    assert set(row) == set(cols), "row weicht von der erlaubten Spaltenliste ab"
    values = [row[c] for c in cols]
    with A.db() as con:
        if existing:
            # ggf. alte PDF mit abweichendem Namen entfernen
            old = existing['pdf_name']
            if old and old != pdf_name:
                op = A._trip_pdf_path(old)
                if op and op.exists():
                    try:
                        op.unlink()
                    except OSError:
                        pass
            setclause = ', '.join(f'{c}=?' for c in cols)
            con.execute(f'UPDATE trips SET {setclause} WHERE id=?',
                        values + [existing['id']])
            tid = existing['id']
        else:
            placeholders = ', '.join('?' for _ in cols)
            cur = con.execute(
                f'INSERT INTO trips ({", ".join(cols)}) VALUES ({placeholders})',
                values)
            tid = cur.lastrowid
    warnings = A.check_fields(data)
    if warnings:
        A.log.warning("Reise-Import #%s: nicht erkannte Felder: %s",
                    booking or tid, ", ".join(warnings))
    A.log.info("Reise importiert: %s (#%s)", row['title'], booking or tid)
    return jsonify({'ok': True, 'id': tid, 'data': data, 'warnings': warnings,
                    'ai_filled': ai_filled})


@bp.route('/api/trips/<int:tid>/rescan', methods=['POST'])
def api_trip_rescan(tid):
    """Gespeicherte Reise-PDF neu parsen — z. B. nach einem Parser-Update wegen
    TUI-Layout-Änderung — ohne Löschen und Neu-Upload. Aktualisiert dieselbe Reise
    (gleiche id; PDF-Datei, Original-Dateiname und Erstellungsdatum bleiben),
    Anhänge und Packliste bleiben unberührt."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        old = con.execute('SELECT pdf_name, orig_name, created, data FROM trips WHERE id=?',
                          (tid,)).fetchone()
    if not old:
        return jsonify({'error': 'not_found'}), 404
    path = A._trip_pdf_path(old['pdf_name'] or '')
    if path is None or not path.exists():
        return jsonify({'error': 'no_pdf'}), 404
    try:
        raw = path.read_bytes()
        data, ai_filled = _parse_trip_pdf_bytes(raw, manual=_trip_manual(old['data']))
    except Exception as exc:
        A.log.warning("PDF-Rescan #%d fehlgeschlagen: %s", tid, exc)
        return jsonify({'error': 'parse_failed'}), 422
    row = _trip_row(data, old['pdf_name'], old['orig_name'], old['created'])
    cols = A._TRIP_COLUMNS
    assert set(row) == set(cols), "row weicht von der erlaubten Spaltenliste ab"
    with A.db() as con:
        setclause = ', '.join(f'{c}=?' for c in cols)
        con.execute(f'UPDATE trips SET {setclause} WHERE id=?',
                    [row[c] for c in cols] + [tid])
    warnings = A.check_fields(data)
    if warnings:
        A.log.warning("Reise-Rescan #%d: nicht erkannte Felder: %s", tid, ", ".join(warnings))
    A.log.info("Reise neu eingelesen: %s (#%d)", row['title'], tid)
    return jsonify({'ok': True, 'id': tid, 'data': data, 'warnings': warnings,
                    'ai_filled': ai_filled})


_MANUAL_DATE_KEYS = frozenset({'buchungsdatum', 'reisezeitraum_von', 'reisezeitraum_bis',
                               'anzahlung_faelligkeit', 'restzahlung_faelligkeit'})
_MANUAL_PRICE_KEYS = frozenset({'gesamtpreis', 'anzahlung_betrag', 'restzahlung_betrag'})
_EUR_INPUT_RE = re.compile(r'\d{1,7}(?:\.\d{3})*(?:,\d{1,2})?')


def _normalize_manual_extras(val):
    """Validiert/normalisiert die manuelle Extras-Liste ({typ, details?, anzahl?,
    preis?}). Rückgabe: bereinigte Liste oder None bei ungültiger Eingabe."""
    if not isinstance(val, list) or len(val) > 30:
        return None
    out = []
    for e in val:
        if not isinstance(e, dict):
            return None
        typ = str(e.get('typ') or '').strip()
        if not typ or len(typ) > 60:
            return None
        item = {'typ': typ}
        det = str(e.get('details') or '').strip()
        if len(det) > 120:
            return None
        if det:
            item['details'] = det
        anz = e.get('anzahl')
        if anz not in (None, ''):
            try:
                anz = int(anz)
            except (TypeError, ValueError):
                return None
            if not 1 <= anz <= 99:
                return None
            item['anzahl'] = anz
        p = str(e.get('preis') or '').strip()
        if p == 'inkl.':
            item['preis'] = 'inkl.'
        elif p:
            s = p.replace('€', '').strip()
            if not _EUR_INPUT_RE.fullmatch(s):
                return None
            item['preis'] = A._fmt_eur(A._parse_eur(s))
        out.append(item)
    return out


def _normalize_manual_rabatte(val):
    """Validiert/normalisiert die manuelle Rabatte-Liste ({code, betrag}). Beträge
    werden immer als negativer deutscher Betrag gespeichert (Konvention des
    Parsers), egal ob mit/ohne Minus eingegeben. Rückgabe: Liste oder None."""
    if not isinstance(val, list) or len(val) > 20:
        return None
    out = []
    for r in val:
        if not isinstance(r, dict):
            return None
        code = str(r.get('code') or '').strip()
        if not code or len(code) > 60:
            return None
        b = str(r.get('betrag') or '').replace('€', '').strip().lstrip('-').strip()
        if not b or not _EUR_INPUT_RE.fullmatch(b):
            return None
        out.append({'code': code, 'betrag': '-' + A._fmt_eur(A._parse_eur(b))})
    return out


def _normalize_manual_value(key, val):
    """Validiert/normalisiert EINEN manuellen Override-Wert (Preise ins deutsche
    Format, Datums-Keys TT.MM.JJJJ, Zahlen mit Grenzen). Rückgabe: normalisierter
    Wert oder None bei ungültiger Eingabe."""
    if key == 'extras':
        return _normalize_manual_extras(val)
    if key == 'rabatte':
        return _normalize_manual_rabatte(val)
    if key == 'rabatt_inklusive':
        return True if val in (True, 'true', '1', 1) else None
    if key in ('naechte', 'reisende_anzahl'):
        try:
            n = int(val)
        except (TypeError, ValueError):
            return None
        return n if 1 <= n <= (365 if key == 'naechte' else 20) else None
    if not isinstance(val, str):
        return None
    val = val.strip()
    if not val or len(val) > 120:
        return None
    if key in _MANUAL_DATE_KEYS:
        return val if re.fullmatch(r'\d{2}\.\d{2}\.\d{4}', val) else None
    if key in _MANUAL_PRICE_KEYS:
        s = val.replace('€', '').strip()
        if not _EUR_INPUT_RE.fullmatch(s):
            return None
        return A._fmt_eur(A._parse_eur(s))
    return val


@bp.route('/api/trips/<int:tid>/fields', methods=['PATCH'])
def api_trip_fields(tid):
    """Manuelle Feld-Zuordnung aus der Debug-Ansicht: setzt/löscht Overrides
    (data['_manual']) für Felder, die der Parser nicht (korrekt) erkannt hat —
    funktioniert aber für ALLE Whitelist-Felder, auch bereits erkannte.
    null/'' löscht einen Override (Parser-Wert kommt zurück). Overrides überleben
    Rescan und Re-Import (werden dort nach dem Parsen erneut angewendet). Die
    gespeicherte PDF wird ohne KI-Fallback neu geparst — beim manuellen Zuordnen
    ist der Nutzer selbst der Fallback (kein Kosten-/Latenz-Overhead)."""
    if (err := A._require_api()):
        return err
    body = request.get_json(silent=True) or {}
    fields = body.get('fields')
    if not isinstance(fields, dict) or not fields:
        return jsonify({'error': 'invalid'}), 400
    with A.db() as con:
        old = con.execute('SELECT data, pdf_name, orig_name, created FROM trips WHERE id=?',
                          (tid,)).fetchone()
    if not old:
        return jsonify({'error': 'not_found'}), 404
    manual = _trip_manual(old['data'])
    for key, val in fields.items():
        if key not in _MANUAL_TRIP_KEYS:
            return jsonify({'error': 'invalid_field', 'field': key}), 400
        if val in (None, '', []) or val is False:
            manual.pop(key, None)
            continue
        norm = _normalize_manual_value(key, val)
        if norm is None:
            return jsonify({'error': 'invalid_value', 'field': key}), 400
        manual[key] = norm
    path = A._trip_pdf_path(old['pdf_name'] or '')
    data = None
    if path is not None and path.exists():
        # sauberer Re-Parse mit den neuen Overrides — nur so liefert auch das
        # LÖSCHEN eines Overrides wieder den echten Parser-Wert.
        try:
            data, _ = _parse_trip_pdf_bytes(path.read_bytes(), manual=manual, use_ai=False)
        except Exception as exc:
            A.log.warning("Feld-Zuordnung #%d: Re-Parse fehlgeschlagen (%s) — "
                        "Overrides werden auf die gespeicherten Daten angewendet", tid, exc)
    if data is None:
        data = A._json_loads_safe(old['data'], {})
        data.pop('_manual', None)
        if manual:
            data['_manual'] = manual
        _apply_manual_overrides(data)
    row = _trip_row(data, old['pdf_name'], old['orig_name'], old['created'])
    cols = A._TRIP_COLUMNS
    assert set(row) == set(cols), "row weicht von der erlaubten Spaltenliste ab"
    with A.db() as con:
        setclause = ', '.join(f'{c}=?' for c in cols)
        con.execute(f'UPDATE trips SET {setclause} WHERE id=?',
                    [row[c] for c in cols] + [tid])
    warnings = A.check_fields(data)
    A.log.info("Reise #%d: manuelle Feld-Zuordnung gespeichert (%s)",
             tid, ", ".join(sorted(fields)))
    return jsonify({'ok': True, 'id': tid, 'data': data, 'warnings': warnings,
                    'manual': manual})


@bp.route('/api/trips/<int:tid>/fields/suggest', methods=['POST'])
def api_trip_fields_suggest(tid):
    """KI-Vorschläge für die manuelle Feld-Zuordnung: extrahiert die Standard-Felder
    aus dem gespeicherten PDF-Text (gleiches Schema wie der Import-Fallback), gibt
    sie aber NUR als Vorschlag zurück — der Nutzer prüft die Werte im Editor und
    speichert selbst (kein automatisches Override, anders als der stille
    KI-Fallback beim Import)."""
    if (err := A._require_api()):
        return err
    api_key, model = A._ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key'}), 400
    with A.db() as con:
        row = con.execute('SELECT pdf_name FROM trips WHERE id=?', (tid,)).fetchone()
    if not row or not row['pdf_name']:
        return jsonify({'error': 'not_found'}), 404
    p = A._trip_pdf_path(row['pdf_name'])
    if p is None or not p.exists():
        return jsonify({'error': 'no_pdf'}), 404
    try:
        cleaned = A._clean_text(A.extract_pdf_text(io.BytesIO(p.read_bytes())))
    except Exception:
        return jsonify({'error': 'text_failed'}), 422
    prompt = (
        "Extrahiere aus folgendem Text einer TUI-Reisebestätigung NUR diese Felder "
        "als JSON. Fehlt eine Information wirklich, gib null zurück statt zu raten "
        "oder zu erfinden.\n\n" + cleaned[:6000]
    )
    text, usage, code = A._ai_request(api_key, model, prompt, max_tokens=800,
                                    log_ctx=f"Feld-Vorschlag #{tid}", use_web_search=False,
                                    output_schema=_AI_TRIP_FIELD_SCHEMA)
    if code or not text:
        return jsonify({'error': 'ai_failed'}), 502
    try:
        ai = json.loads(text)
    except ValueError:
        return jsonify({'error': 'ai_failed'}), 502
    usage['estimated_usd'] = A._ai_call_cost(model, usage)
    A._record_ai_usage(model, usage)
    suggestions = {k: v for k, v in ai.items()
                   if v not in (None, '') and k in _MANUAL_TRIP_KEYS}
    A.log.info("Feld-Vorschlag #%d: KI schlägt %d Feld(er) vor", tid, len(suggestions))
    return jsonify({'ok': True, 'suggestions': suggestions, 'usage': usage})


@bp.route('/api/trips/<int:tid>/pdf', methods=['GET'])
def api_trip_pdf(tid):
    """Gespeicherte Reise-PDF ausliefern (öffnen/herunterladen)."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        row = con.execute('SELECT pdf_name, orig_name FROM trips WHERE id=?',
                          (tid,)).fetchone()
    if not row or not row['pdf_name']:
        return jsonify({'error': 'not_found'}), 404
    p = A._trip_pdf_path(row['pdf_name'])
    if p is None or not p.exists():
        return jsonify({'error': 'not_found'}), 404
    return send_file(str(p), mimetype='application/pdf',
                     download_name=row['orig_name'] or 'reise.pdf')


@bp.route('/api/trips/<int:tid>/attachments', methods=['POST'])
def api_trip_attachment_upload(tid):
    """Weiteres PDF zu einer Reise hochladen (z. B. Reiseplan) — reine Ablage,
    kein Parsing/Auswertung."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        if not con.execute('SELECT id FROM trips WHERE id=?', (tid,)).fetchone():
            return jsonify({'error': 'not_found'}), 404
    file = request.files.get('pdf')
    if file is None or not file.filename:
        return jsonify({'error': 'no_file'}), 400
    if Path(file.filename).suffix.lower() != '.pdf':
        return jsonify({'error': 'not_pdf'}), 400
    raw = file.read()
    if not raw:
        return jsonify({'error': 'empty'}), 400
    if len(raw) > A.MAX_PDF_BYTES:
        return jsonify({'error': 'too_large'}), 413

    filename = f"att_{tid}_{secrets.token_hex(8)}.pdf"
    target = A._trip_pdf_path(filename)
    if target is None:
        return jsonify({'error': 'bad_name'}), 400
    Path(A.TRIPS_DIR).mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(raw)
    except OSError as exc:
        A.log.warning("Anhang speichern fehlgeschlagen: %s", exc)
        return jsonify({'error': 'store_failed'}), 500

    orig = Path(file.filename).name
    ts = int(time.time())
    with A.db() as con:
        cur = con.execute(
            'INSERT INTO trip_attachments (trip_id, filename, orig_name, created) '
            'VALUES (?,?,?,?)', (tid, filename, orig, ts))
        aid = cur.lastrowid
    A.log.info("Anhang zu Reise #%d gespeichert: %s", tid, orig)
    return jsonify({'ok': True, 'id': aid, 'orig_name': orig, 'created': ts})


@bp.route('/api/trips/<int:tid>/attachments/<int:aid>', methods=['GET'])
def api_trip_attachment_get(tid, aid):
    """Gespeichertes Zusatz-PDF ausliefern (öffnen/herunterladen)."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        row = con.execute(
            'SELECT filename, orig_name FROM trip_attachments WHERE id=? AND trip_id=?',
            (aid, tid)).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    p = A._trip_pdf_path(row['filename'])
    if p is None or not p.exists():
        return jsonify({'error': 'not_found'}), 404
    return send_file(str(p), mimetype='application/pdf',
                     download_name=row['orig_name'] or 'anhang.pdf')


@bp.route('/api/trips/<int:tid>/attachments/<int:aid>', methods=['DELETE'])
def api_trip_attachment_delete(tid, aid):
    """Zusatz-PDF wieder entfernen."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        row = con.execute(
            'SELECT filename FROM trip_attachments WHERE id=? AND trip_id=?',
            (aid, tid)).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        con.execute('DELETE FROM trip_attachments WHERE id=?', (aid,))
    p = A._trip_pdf_path(row['filename'])
    if p and p.exists():
        try:
            p.unlink()
        except OSError as exc:
            A.log.warning("Anhang löschen fehlgeschlagen: %s", exc)
    return jsonify({'ok': True})


# Obergrenze für Packliste-Items je Reise — die Vorlage hat 66 Einträge und füllt eine
# gedruckte A4-Seite zweispaltig bereits gut; 70 lässt ein paar eigene Ergänzungen zu,
# ohne dass das Druckblatt umbricht.
MAX_PACKING_ITEMS = 70


def _packing_item_owned(con, tid, iid):
    return con.execute(
        'SELECT id FROM trip_packing_items WHERE id=? AND trip_id=?', (iid, tid)).fetchone()


@bp.route('/api/trips/<int:tid>/packing', methods=['POST'])
def api_trip_packing_add(tid):
    """Eigenes Item zur Packliste hinzufügen."""
    if (err := A._require_api()):
        return err
    body = request.get_json(silent=True) or {}
    category = (body.get('category') or '').strip()
    label = (body.get('label') or '').strip()
    if not category or not label or len(category) > 60 or len(label) > 200:
        return jsonify({'error': 'invalid'}), 400
    with A.db() as con:
        if not con.execute('SELECT id FROM trips WHERE id=?', (tid,)).fetchone():
            return jsonify({'error': 'not_found'}), 404
        count = con.execute(
            'SELECT COUNT(*) c FROM trip_packing_items WHERE trip_id=?', (tid,)).fetchone()['c']
        if count >= MAX_PACKING_ITEMS:
            return jsonify({'error': 'limit_reached'}), 409
        cur = con.execute(
            'INSERT INTO trip_packing_items (trip_id, category, label, checked, created) '
            'VALUES (?,?,?,0,?)', (tid, category, label, int(time.time())))
    return jsonify({'ok': True, 'id': cur.lastrowid})


@bp.route('/api/trips/<int:tid>/packing/<int:iid>', methods=['PATCH'])
def api_trip_packing_update(tid, iid):
    """Item abhaken/umbenennen/umkategorisieren — nur mitgeschickte Felder ändern."""
    if (err := A._require_api()):
        return err
    body = request.get_json(silent=True) or {}
    fields, params = [], []
    if 'checked' in body:
        fields.append('checked=?')
        params.append(1 if body.get('checked') else 0)
    if 'label' in body:
        label = (body.get('label') or '').strip()
        if not label or len(label) > 200:
            return jsonify({'error': 'invalid'}), 400
        fields.append('label=?')
        params.append(label)
    if 'category' in body:
        category = (body.get('category') or '').strip()
        if not category or len(category) > 60:
            return jsonify({'error': 'invalid'}), 400
        fields.append('category=?')
        params.append(category)
    if not fields:
        return jsonify({'error': 'invalid'}), 400
    with A.db() as con:
        if not _packing_item_owned(con, tid, iid):
            return jsonify({'error': 'not_found'}), 404
        con.execute(f'UPDATE trip_packing_items SET {", ".join(fields)} WHERE id=?',
                    params + [iid])
    return jsonify({'ok': True})


@bp.route('/api/trips/<int:tid>/packing/<int:iid>', methods=['DELETE'])
def api_trip_packing_delete(tid, iid):
    """Packliste-Item entfernen."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        if not _packing_item_owned(con, tid, iid):
            return jsonify({'error': 'not_found'}), 404
        con.execute('DELETE FROM trip_packing_items WHERE id=?', (iid,))
    return jsonify({'ok': True})


@bp.route('/api/trips/<int:tid>/packing/reset', methods=['POST'])
def api_trip_packing_reset(tid):
    """Packliste auf die Vorlage zurücksetzen — eigene Einträge/Haken gehen verloren."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        if not con.execute('SELECT id FROM trips WHERE id=?', (tid,)).fetchone():
            return jsonify({'error': 'not_found'}), 404
        con.execute('DELETE FROM trip_packing_items WHERE trip_id=?', (tid,))
        con.executemany(
            'INSERT INTO trip_packing_items '
            '(trip_id, category, label, checked, created) VALUES (?,?,?,?,?)',
            [(tid,) + r for r in A.default_packing_rows(int(time.time()), _packing_template())])
        con.execute('UPDATE trips SET packing_seeded=1 WHERE id=?', (tid,))
    return jsonify({'ok': True})


def _validate_packing_template(t):
    """Validiert eine Nutzer-Packlisten-Vorlage: {Kategorie: [Items]} mit
    vernünftigen Grenzen (Gesamt <= 70 Items, damit der Ausdruck auf eine
    A4-Seite passt — wie das Limit der Reise-Packlisten). Rückgabe: bereinigtes
    Dict oder None bei ungültiger Eingabe."""
    if not isinstance(t, dict) or not 1 <= len(t) <= 20:
        return None
    out, total = {}, 0
    for cat, items in t.items():
        cat = str(cat).strip()
        if not cat or len(cat) > 40 or not isinstance(items, list) or not items:
            return None
        labels = []
        for label in items:
            label = str(label).strip()
            if not label or len(label) > 80:
                return None
            labels.append(label)
        total += len(labels)
        out[cat] = labels
    return out if total <= 70 else None


def _packing_template() -> dict:
    """Aktive Packlisten-Vorlage: die vom Nutzer angepasste (meta
    `packing_template`, JSON) — sonst die eingebaute A.PACKING_TEMPLATE."""
    custom = _validate_packing_template(A._json_loads_safe(A._meta_get('packing_template'), None))
    return custom or A.PACKING_TEMPLATE


@bp.route('/api/packing-template', methods=['GET'])
def api_packing_template_get():
    if (err := A._require_api()):
        return err
    tpl = _packing_template()
    return jsonify({'template': tpl, 'custom': tpl is not A.PACKING_TEMPLATE})


@bp.route('/api/packing-template', methods=['POST'])
def api_packing_template_set():
    """Nutzer-Vorlage speichern (gilt für neue Packlisten und „Zurücksetzen";
    bestehende Reise-Packlisten bleiben unverändert). `template: null` stellt
    die eingebaute Standard-Vorlage wieder her."""
    if (err := A._require_api()):
        return err
    body = request.get_json(silent=True) or {}
    tpl = body.get('template')
    if tpl is None:
        A._meta_set('packing_template', '')
        A.log.info("Packlisten-Vorlage auf Standard zurückgesetzt")
        return jsonify({'ok': True, 'template': A.PACKING_TEMPLATE, 'custom': False})
    cleaned = _validate_packing_template(tpl)
    if cleaned is None:
        return jsonify({'error': 'invalid'}), 400
    A._meta_set('packing_template', json.dumps(cleaned, ensure_ascii=False))
    n = sum(len(v) for v in cleaned.values())
    A.log.info("Packlisten-Vorlage gespeichert: %d Kategorien, %d Items", len(cleaned), n)
    return jsonify({'ok': True, 'template': cleaned, 'custom': True})


@bp.route('/api/trips/<int:tid>', methods=['DELETE'])
def api_trip_delete(tid):
    """Reise löschen — inkl. der dauerhaft gespeicherten PDF und aller Anhänge."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        row = con.execute('SELECT pdf_name FROM trips WHERE id=?', (tid,)).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        atts = con.execute(
            'SELECT filename FROM trip_attachments WHERE trip_id=?', (tid,)).fetchall()
        con.execute('DELETE FROM trip_attachments WHERE trip_id=?', (tid,))
        con.execute('DELETE FROM trip_packing_items WHERE trip_id=?', (tid,))
        con.execute('DELETE FROM trips WHERE id=?', (tid,))
    for a in atts:
        p = A._trip_pdf_path(a['filename'])
        if p and p.exists():
            try:
                p.unlink()
            except OSError as exc:
                A.log.warning("Anhang löschen fehlgeschlagen: %s", exc)
    if row['pdf_name']:
        p = A._trip_pdf_path(row['pdf_name'])
        if p and p.exists():
            try:
                p.unlink()
            except OSError as exc:
                A.log.warning("PDF löschen fehlgeschlagen: %s", exc)
    return jsonify({'ok': True})

