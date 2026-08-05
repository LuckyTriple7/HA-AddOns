"""Flask-Blueprint: Tracking-Statistik (📊) — Kennzahlen über alle Angebote und
den gesamten Preisverlauf: Ersparnis gegenüber Höchstpreis, größte Einzelbewegungen,
Preisänderungen nach Wochentag, empirischer Tiefstpreis-Zeitpunkt.

Geteilte Primitiven über `import app as A` (spät gebunden, monkeypatch-sicher),
gleiches Muster wie trips_routes/watch (Backlog #12).
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify

import app as A

bp = Blueprint('stats', __name__)

_WEEKDAYS = ('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So')


def _collect_stats() -> dict:
    with A.db() as con:
        offers = [dict(o) for o in con.execute('SELECT * FROM offers ORDER BY id')]
        first_ts = con.execute(
            'SELECT MIN(ts) t FROM price_history').fetchone()['t']
        points = con.execute(
            'SELECT COUNT(*) c FROM price_history WHERE ok=1 AND price IS NOT NULL'
        ).fetchone()['c']

        # Preisbewegungen nach Wochentag (aus price_moves — jede echte Änderung
        # zwischen zwei Polls, überlebt gelöschte Angebote)
        weekday = [{'name': _WEEKDAYS[i], 'n': 0, 'drops': 0, 'rises': 0, 'sum_pct': 0.0}
                   for i in range(7)]
        for r in con.execute('SELECT ts, pct_change FROM price_moves'):
            w = weekday[datetime.fromtimestamp(r['ts']).weekday()]
            pct = r['pct_change'] or 0.0
            if not pct:
                continue
            w['n'] += 1
            w['sum_pct'] += pct
            if pct < 0:
                w['drops'] += 1
            else:
                w['rises'] += 1
        for w in weekday:
            w['avg_pct'] = round(w['sum_pct'] / w['n'], 2) if w['n'] else None
            del w['sum_pct']

        saved_rows, top_drops, top_rises, low_days = [], [], [], []
        booked_diffs = []
        for o in offers:
            name = o.get('label') or o.get('hotel') or f"#{o['id']}"
            hist = con.execute(
                'SELECT ts, price FROM price_history WHERE offer_id=? AND ok=1 '
                'AND price IS NOT NULL ORDER BY ts', (o['id'],)).fetchall()
            if not hist:
                continue
            prices = [h['price'] for h in hist]
            cur, peak, low = prices[-1], max(prices), min(prices)
            # Ersparnis ggü. Höchstpreis — nur aktive Angebote (bei archivierten
            # ist "sparen" vorbei)
            if not o.get('archived') and peak > cur:
                saved_rows.append({'name': name, 'saved': round(peak - cur),
                                   'peak': round(peak), 'price': round(cur)})
            # größte Einzelbewegung zwischen zwei aufeinanderfolgenden Messungen
            for a, b in zip(hist, hist[1:]):
                d = b['price'] - a['price']
                if d < 0:
                    top_drops.append({'name': name, 'delta': round(d),
                                      'ts': b['ts'], 'price': round(b['price'])})
                elif d > 0:
                    top_rises.append({'name': name, 'delta': round(d),
                                      'ts': b['ts'], 'price': round(b['price'])})
            # gebucht vs. aktueller Preis (nur aktiv + Buchungspreis hinterlegt)
            if o.get('booked_price') and not o.get('archived'):
                booked_diffs.append({'name': name,
                                     'diff': round(cur - o['booked_price'])})
            # Rückschau (nur abgeschlossene = archivierte Angebote): wie viele Tage
            # vor Abreise lag der Tiefstpreis?
            if o.get('archived') and o.get('return_date'):
                nights = A._offer_nights(o.get('details') or '') or 0
                try:
                    start = date.fromisoformat(o['return_date'][:10]) - timedelta(days=nights)
                    ts_low = min(hist, key=lambda h: h['price'])['ts']
                    days = (start - datetime.fromtimestamp(ts_low).date()).days
                    if days >= 0:
                        low_days.append(days)
                except ValueError:
                    pass

        top_drops.sort(key=lambda x: x['delta'])
        top_rises.sort(key=lambda x: -x['delta'])
        saved_rows.sort(key=lambda x: -x['saved'])
        return {
            'offers_total': len(offers),
            'offers_active': sum(1 for o in offers if not o.get('archived')),
            'points': points,
            'since_ts': first_ts,
            'saved_total': round(sum(r['saved'] for r in saved_rows)),
            'saved_rows': saved_rows[:10],
            'top_drops': top_drops[:5],
            'top_rises': top_rises[:5],
            'weekday': weekday,
            'booked': booked_diffs,
            'low_days_median': (sorted(low_days)[len(low_days) // 2]
                                if low_days else None),
            'low_days_n': len(low_days),
        }


@bp.route('/api/stats', methods=['GET'])
def api_stats():
    """Tracking-Statistik fürs 📊-Fenster."""
    if (err := A._require_api()):
        return err
    return jsonify(_collect_stats())
