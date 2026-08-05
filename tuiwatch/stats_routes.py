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


# ── Preisprognose (heuristisch, ohne KI) ───────────────────────────────────────
#
# Idee: die Kalender-Historie desselben Angebots enthält für viele Reisetermine,
# wie sich deren Preis mit schrumpfender Vorlaufzeit entwickelt hat. Daraus wird
# eine Vorlaufzeit-Kurve gebaut (Median des normierten Preises je 7-Tage-Bucket
# "Tage vor Abreise") und auf den eigenen Termin angewendet; der regionale
# Markttrend (letzte 14 Tage) fließt als Drift mit ein. Ausdrücklich eine
# ANNAHME auf Erfahrungsbasis, keine Garantie — das sagt auch das UI dazu.

_FORECAST_HORIZONS = (7, 14, 30)
_MIN_BUCKET_SAMPLES = 3


def _lead_curve(cal_rows) -> tuple[dict, int]:
    """Vorlaufzeit-Kurve aus calendar_history-Zeilen (travel_date, ts, price):
    {bucket(=Tage-vor-Abreise // 7): Median des auf den Termin-Median normierten
    Preises}. Zweiter Rückgabewert: Anzahl verwendeter Reisetermine."""
    by_date: dict[str, list] = {}
    for r in cal_rows:
        by_date.setdefault(r['travel_date'], []).append(r)
    buckets: dict[int, list] = {}
    used = 0
    for tdate, rows in by_date.items():
        if len(rows) < 2:
            continue
        try:
            t = date.fromisoformat(tdate[:10])
        except ValueError:
            continue
        prices = sorted(r['price'] for r in rows)
        base = prices[len(prices) // 2]
        if not base:
            continue
        used += 1
        for r in rows:
            days_out = (t - datetime.fromtimestamp(r['ts']).date()).days
            if days_out < 0:
                continue
            buckets.setdefault(days_out // 7, []).append(r['price'] / base)
    curve = {}
    for b, vals in buckets.items():
        if len(vals) >= _MIN_BUCKET_SAMPLES:
            vals.sort()
            curve[b] = vals[len(vals) // 2]
    return curve, used


def _forecast(offer_id: int) -> dict:
    with A.db() as con:
        o = con.execute('SELECT * FROM offers WHERE id=?', (offer_id,)).fetchone()
        if not o:
            return {'ok': False, 'note': 'unbekanntes Angebot'}
        o = dict(o)
        last = con.execute(
            'SELECT ts, price FROM price_history WHERE offer_id=? AND ok=1 '
            'AND price IS NOT NULL ORDER BY ts DESC LIMIT 1', (offer_id,)).fetchone()
        cal = con.execute(
            'SELECT travel_date, ts, price FROM calendar_history WHERE offer_id=?',
            (offer_id,)).fetchall()
        market = A._market_trend(con, region=o.get('region') or None)
    if not last:
        return {'ok': False, 'note': 'noch kein Preis'}
    nights = A._offer_nights(o.get('details') or '') or 0
    try:
        start = date.fromisoformat((o.get('return_date') or '')[:10]) - timedelta(days=nights)
    except ValueError:
        return {'ok': False, 'note': 'Abreisedatum unbekannt'}
    d0 = (start - date.today()).days
    if d0 <= 0:
        return {'ok': False, 'note': 'Reise hat begonnen oder liegt zurück'}

    curve, n_dates = _lead_curve(cal)
    f0 = curve.get(d0 // 7)
    drift_daily = (market['pct'] / 100 / 14) if market else 0.0
    price = float(last['price'])
    now = int(datetime.now().timestamp())
    points = []
    for h in _FORECAST_HORIZONS:
        if d0 - h < 0:
            continue
        f1 = curve.get((d0 - h) // 7)
        season = (f1 / f0) if (f0 and f1) else None
        if season is None and not market:
            continue                      # weder Saisonkurve noch Markttrend → raten wäre Lüge
        est = price * (season if season is not None else 1.0) * (1 + drift_daily * h)
        points.append({'days': h, 'ts': now + h * 86400, 'price': round(est),
                       'season': (round(season, 3) if season is not None else None)})
    if not points:
        return {'ok': False,
                'note': 'zu wenig Kalenderhistorie und kein Markttrend — Prognose braucht Daten'}
    return {'ok': True, 'price': round(price), 'days_to_departure': d0,
            'points': points, 'basis': {'calendar_dates': n_dates,
                                        'market_pct': market['pct'] if market else None,
                                        'market_n': market['n'] if market else 0}}


@bp.route('/api/forecast/<int:offer_id>', methods=['GET'])
def api_forecast(offer_id: int):
    """Heuristische Preisprognose fürs Verlauf-Fenster (gestrichelte Kurve)."""
    if (err := A._require_api()):
        return err
    return jsonify(_forecast(offer_id))
