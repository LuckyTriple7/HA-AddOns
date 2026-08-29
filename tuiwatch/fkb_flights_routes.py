"""FKB-Flugplan-Routen — eigenständiges Blueprint neben str_/fra_/muc_flights_routes.py.

Vierter Flughafen (Karlsruhe/Baden-Baden), wieder mit eigener Quelle
(Saisonflugplan der Website, siehe SCRAPING_FKB.md) und eigenem Schalter
`enable_fkb_flights`; gemeinsam ist nur der ✈️-Einstieg im Frontend.
"""
from flask import Blueprint, jsonify, request

import app as A
import fkb_flights_client

bp = Blueprint('fkb_flights_routes', __name__)


def _guard():
    if (err := A._require_api()):
        return err
    if not bool(A.load_config().get('enable_fkb_flights', False)):
        return jsonify({'error': 'disabled'}), 404
    return None


@bp.route('/api/fkbflights', methods=['GET'])
def api_fkb_flights():
    """Verbindungen ab/nach FKB aus dem Saisonflugplan."""
    if (err := _guard()):
        return err
    direction = (request.args.get('type') or '').strip()
    if direction not in ('', 'departure', 'arrival'):
        return jsonify({'error': 'bad_type'}), 400
    res = fkb_flights_client.search(
        (request.args.get('q') or '').strip(), direction=direction,
        date_from=(request.args.get('from') or '').strip(),
        date_till=(request.args.get('till') or '').strip(),
        verbose=A._verbose())
    if res is None:
        return jsonify({'error': 'fetch_failed'}), 502
    return jsonify(res)


@bp.route('/api/fkbflights/refresh', methods=['POST'])
def api_fkb_refresh():
    """Erzwingt Neuladen des Saisonplans (sonst passiert das automatisch,
    sobald der Cache älter als CACHE_TTL ist)."""
    if (err := _guard()):
        return err
    if not fkb_flights_client.refresh(verbose=A._verbose()):
        return jsonify({'error': 'fetch_failed'}), 502
    return jsonify({'ok': True, 'fetched_ts': fkb_flights_client.last_fetch_ts()})
