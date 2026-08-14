"""FRA-Flugplan-Routen — eigenständiges Blueprint neben str_flights_routes.py.

Bewusst getrennt vom STR-Flugplan (anderes Datenmodell, anderer Anbieter, eigener
Schalter `enable_fra_flights`); gemeinsam ist nur der ✈️-Einstieg im Frontend.
"""
from flask import Blueprint, jsonify, request

import app as A
import fra_flights_client

bp = Blueprint('fra_flights_routes', __name__)


def _guard():
    if (err := A._require_api()):
        return err
    if not bool(A.load_config().get('enable_fra_flights', False)):
        return jsonify({'error': 'disabled'}), 404
    return None


@bp.route('/api/fraflights', methods=['GET'])
def api_fra_flights():
    """Flüge ab/nach FRA zu einem Ziel (IATA-Code oder Freitext)."""
    if (err := _guard()):
        return err
    q = (request.args.get('q') or '').strip()
    flight_type = (request.args.get('type') or 'departures').strip()
    if flight_type not in ('departures', 'arrivals'):
        return jsonify({'error': 'bad_type'}), 400
    date_from = (request.args.get('from') or '').strip()
    date_till = (request.args.get('till') or '').strip()
    res = fra_flights_client.search_flights(
        q, flight_type=flight_type, date_from=date_from, date_till=date_till,
        verbose=A._verbose())
    if res is None:
        return jsonify({'error': 'fetch_failed'}), 502
    return jsonify(res)


@bp.route('/api/fraflights/airports', methods=['GET'])
def api_fra_airports():
    """Flughafen-Vorschläge zu einem Suchbegriff (Ort, Land, IATA-Code)."""
    if (err := _guard()):
        return err
    rows = fra_flights_client.search_airports((request.args.get('q') or '').strip(),
                                              verbose=A._verbose())
    if rows is None:
        return jsonify({'error': 'fetch_failed'}), 502
    return jsonify({'airports': rows})
