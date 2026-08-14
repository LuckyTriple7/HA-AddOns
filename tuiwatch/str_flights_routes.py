"""STR-Flugplan-Routen — ausgelagert aus app.py, analog zu check24_routes.py
(kompaktes Blueprint-Modul, geteilte Primitiven über `import app as A`)."""
from flask import Blueprint, jsonify, request

import app as A
import str_flights_client

bp = Blueprint('str_flights_routes', __name__)


@bp.route('/api/strflights', methods=['GET'])
def api_str_flights():
    if (err := A._require_api()):
        return err
    if not bool(A.load_config().get('enable_str_flights', False)):
        return jsonify({'error': 'disabled'}), 404
    q = (request.args.get('q') or '').strip()
    flight_type = (request.args.get('type') or '').strip()
    if flight_type not in ('', 'Departure', 'Arrival'):
        return jsonify({'error': 'bad_type'}), 400
    date_from = (request.args.get('from') or '').strip()
    date_till = (request.args.get('till') or '').strip()
    rows = str_flights_client.search_connections(
        q, flight_type=flight_type, date_from=date_from, date_till=date_till, verbose=A._verbose())
    if rows is None:
        return jsonify({'error': 'fetch_failed'}), 502
    return jsonify({'rows': rows})


@bp.route('/api/strflights/callsign', methods=['GET'])
def api_str_flights_callsign():
    if (err := A._require_api()):
        return err
    if not bool(A.load_config().get('enable_str_flights', False)):
        return jsonify({'error': 'disabled'}), 404
    airline = (request.args.get('airline') or '').strip()
    no = (request.args.get('no') or '').strip()
    if not airline or not no:
        return jsonify({'error': 'bad_request'}), 400
    result = str_flights_client.lookup_callsign(airline + no, verbose=A._verbose())
    if result is None:
        return jsonify({'error': 'fetch_failed'}), 502
    return jsonify(result)
