"""Kombinierte Flugziel-Suche über alle vier Flugpläne (STR/FRA/MUC/FKB) —
eigenständiges Blueprint neben str_/fra_/muc_/fkb_flights_routes.py.

Bewusst **kein** vereinheitlichtes Datenmodell: die Flugpläne bleiben so
unterschiedlich wie in ihren eigenen Clients (STR/MUC/FKB: Saisonstrecken mit
Wochentagsraster, FRA: Einzelflüge je Datum) — eine gemeinsame Row-Form würde
das verbiegen (siehe fra_flights_client.py-Kommentar). Diese Route ruft nur
alle parallel ab und reicht ihre jeweils eigene Antwortform unverändert
unter `str`/`fra`/`muc`/`fkb` durch; das Frontend rendert jede Sektion mit den
bestehenden render*Flights()-Funktionen der Einzelpläne.

Nur Abflüge (Ziel-Perspektive „wohin komme ich von hier") — für Ankünfte
bleiben die Einzelpläne da, ein kombinierter Filter für beide Richtungen über
vier Flughäfen wäre unübersichtlich.
"""
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, jsonify, request

import app as A
import str_flights_client
import fra_flights_client
import fra_board_client
import muc_flights_client
import fkb_flights_client

bp = Blueprint('all_flights_routes', __name__)

# `/api/flights/destinations` (Übersichtstabelle) mischt eine weitere, andere
# Quelle mit ein: fra_board_client.py (Drittseiten-Tagesbord, nur genähert).
# `/api/flights/search` (gezielte Suche) bleibt bei den offiziellen
# Quellen — fra_board_client wird dort bewusst NICHT verwendet.


@bp.route('/api/flights/search', methods=['GET'])
def api_flights_search():
    if (err := A._require_api()):
        return err
    cfg = A.load_config()
    enabled = {
        'str': bool(cfg.get('enable_str_flights', False)),
        'fra': bool(cfg.get('enable_fra_flights', False)),
        'muc': bool(cfg.get('enable_muc_flights', False)),
        'fkb': bool(cfg.get('enable_fkb_flights', False)),
    }
    if not any(enabled.values()):
        return jsonify({'error': 'disabled'}), 404
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({'error': 'bad_request'}), 400
    date_from = (request.args.get('from') or '').strip()
    date_till = (request.args.get('till') or '').strip()
    verbose = A._verbose()

    # Parallel statt nacheinander: die Quellen sind unabhängig (Azure-API,
    # JSON, PDF-Parse-Cache, WordPress-AJAX) und blockieren sich sonst
    # gegenseitig — v. a. MUC kann beim ersten Aufruf ~15 s für den PDF-Import
    # brauchen.
    with ThreadPoolExecutor(max_workers=4) as ex:
        jobs = {}
        if enabled['str']:
            jobs['str'] = ex.submit(str_flights_client.search_connections, q,
                                    flight_type='Departure', date_from=date_from,
                                    date_till=date_till, verbose=verbose)
        if enabled['fra']:
            jobs['fra'] = ex.submit(fra_flights_client.search_flights, q,
                                    flight_type='departures', date_from=date_from,
                                    date_till=date_till, verbose=verbose)
        if enabled['muc']:
            jobs['muc'] = ex.submit(muc_flights_client.search, q,
                                    direction='departure', date_from=date_from,
                                    date_till=date_till, verbose=verbose)
        if enabled['fkb']:
            jobs['fkb'] = ex.submit(fkb_flights_client.search, q,
                                    direction='departure', date_from=date_from,
                                    date_till=date_till, verbose=verbose)
        results = {k: f.result() for k, f in jobs.items()}

    out = {}
    for k in ('str', 'fra', 'muc', 'fkb'):
        if not enabled[k]:
            continue
        res = results.get(k)
        if res is None:
            out[k] = {'error': True}
        elif k == 'str':
            out[k] = {'rows': res}  # search_connections liefert nackte Liste
        else:
            out[k] = res            # search_flights/search liefern schon dict
    return jsonify(out)


@bp.route('/api/flights/destinations', methods=['GET'])
def api_flights_destinations():
    """Gesamtliste aller tatsächlich angeflogenen Ziele — für die
    Flugziel-Tabelle im Auswahldialog (Zeile anklicken = Suche).

    **STR + MUC + FKB vollständig**: alle drei halten die komplette Saison im
    Speicher-Cache (Azure-API, PDF bzw. WordPress-AJAX), eine Gesamtliste ist da
    ein billiger Cache-Scan. **FRA nur genähert**: die offizielle Flug-API liefert keine
    Gesamtliste (123.289 Abflüge auf 4.854 Seiten ohne Zielfilter, siehe
    SCRAPING_FRA.md) — stattdessen liest fra_board_client.py das Tagesbord
    einer Drittseite und akkumuliert über ein rollierendes Fenster (siehe
    dortige Kommentare zu den Grenzen). Für die gezielte Suche
    (`/api/flights/search`) bleibt weiter die offizielle FRA-API zuständig,
    unverändert."""
    if (err := A._require_api()):
        return err
    cfg = A.load_config()
    enabled_str = bool(cfg.get('enable_str_flights', False))
    enabled_fra = bool(cfg.get('enable_fra_flights', False))
    enabled_muc = bool(cfg.get('enable_muc_flights', False))
    enabled_fkb = bool(cfg.get('enable_fkb_flights', False))
    if not (enabled_str or enabled_fra or enabled_muc or enabled_fkb):
        return jsonify({'error': 'disabled'}), 404
    verbose = A._verbose()

    with ThreadPoolExecutor(max_workers=4) as ex:
        jobs = {}
        if enabled_str:
            jobs['str'] = ex.submit(str_flights_client.list_destinations, verbose=verbose)
        if enabled_fra:
            jobs['fra'] = ex.submit(fra_board_client.list_destinations, verbose=verbose)
        if enabled_muc:
            jobs['muc'] = ex.submit(muc_flights_client.list_destinations, verbose=verbose)
        if enabled_fkb:
            jobs['fkb'] = ex.submit(fkb_flights_client.list_destinations, verbose=verbose)
        results = {k: f.result() for k, f in jobs.items()}

    # Über den IATA-Code zusammenführen (global eindeutig) — ein Ziel, das
    # von mehreren Flughäfen angeflogen wird, taucht nur einmal auf, mit allen
    # Flughäfen in `airports`. Der FKB-Saisonplan nennt kein Land; leer
    # gelassene Felder füllen sich hier aus den anderen Quellen.
    merged: dict[str, dict] = {}
    for src, rows in results.items():
        if rows is None:
            continue
        for d in rows:
            entry = merged.setdefault(d['code'], {'code': d['code'], 'name': d['name'],
                                                   'country': d['country'], 'airports': []})
            if not entry['name']:
                entry['name'] = d['name']
            if not entry['country']:
                entry['country'] = d['country']
            entry['airports'].append(src)
    return jsonify({'destinations': sorted(merged.values(), key=lambda d: d['name'])})
