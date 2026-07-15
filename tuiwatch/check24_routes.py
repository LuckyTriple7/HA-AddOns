"""Check24-Vergleichs-Routen — ausgelagert aus app.py, analog zu offers_routes.py
(kompaktes Blueprint-Modul, geteilte Primitiven über `import app as A`)."""
from flask import Blueprint, jsonify

import app as A

bp = Blueprint('check24_routes', __name__)


@bp.route('/api/check24/<int:offer_id>', methods=['POST'])
def api_check24_start(offer_id: int):
    if (err := A._require_api()):
        return err
    if not bool(A.load_config().get('enable_check24_compare', False)):
        return jsonify({'error': 'disabled'}), 404
    with A.db() as con:
        o = con.execute('SELECT check24_hotel_id FROM offers WHERE id=?',
                        (offer_id,)).fetchone()
    if not o:
        return jsonify({'error': 'not_found'}), 404
    if not o['check24_hotel_id']:
        return jsonify({'error': 'not_linked'}), 409
    if (remaining := A._cooldown_remaining(f'check24:{offer_id}', 120)):
        return jsonify({'error': 'cooldown', 'retry_after': remaining}), 429
    with A._check24_lock:
        if A._check24_state.get(offer_id, {}).get('status') == 'running':
            return jsonify({'started': True, 'already': True})
        A._check24_state[offer_id] = {'status': 'running'}
    A.log.info("Check24-Vergleich gestartet: Angebot #%d", offer_id)
    A._spawn(A._run_check24_compare, offer_id)
    return jsonify({'started': True})


@bp.route('/api/check24/<int:offer_id>', methods=['GET'])
def api_check24_get(offer_id: int):
    if (err := A._require_api()):
        return err
    return jsonify(A._check24_payload(offer_id))
