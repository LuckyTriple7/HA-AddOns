"""MUC-Flugplan-Routen — eigenständiges Blueprint neben str_/fra_flights_routes.py.

Dritter Flughafen, wieder mit eigener Quelle (Saison-PDF) und eigenem Schalter
`enable_muc_flights`; gemeinsam ist nur der ✈️-Einstieg im Frontend.
"""
from flask import Blueprint, jsonify, request

import app as A
import muc_flights_client

bp = Blueprint('muc_flights_routes', __name__)


def _guard():
    if (err := A._require_api()):
        return err
    if not bool(A.load_config().get('enable_muc_flights', False)):
        return jsonify({'error': 'disabled'}), 404
    return None


@bp.route('/api/mucflights', methods=['GET'])
def api_muc_flights():
    """Verbindungen ab/nach MUC aus dem Saison-Flugplan."""
    if (err := _guard()):
        return err
    direction = (request.args.get('type') or '').strip()
    if direction not in ('', 'departure', 'arrival'):
        return jsonify({'error': 'bad_type'}), 400
    res = muc_flights_client.search(
        (request.args.get('q') or '').strip(), direction=direction,
        date_from=(request.args.get('from') or '').strip(),
        date_till=(request.args.get('till') or '').strip(),
        verbose=A._verbose())
    if res is None:
        return jsonify({'error': 'fetch_failed'}), 502
    return jsonify(res)


@bp.route('/api/mucflights/refresh', methods=['POST'])
def api_muc_refresh():
    """Erzwingt Neuladen des PDF (sonst passiert das automatisch alle paar
    Stunden, sobald sich Adresse oder Dateigröße geändert haben)."""
    if (err := _guard()):
        return err
    ok = muc_flights_client.refresh(force=True, verbose=A._verbose())
    if not ok:
        return jsonify({'error': 'fetch_failed'}), 502
    return jsonify({'ok': True, **muc_flights_client.status()})
