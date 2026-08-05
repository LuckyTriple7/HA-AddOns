"""Wochen-Digest (Zusammenfassung per Telegram/E-Mail) — ausgelagert aus app.py
(Backlog #12, Wartbarkeit). Geteilte Primitiven und die Sende-Funktionen laufen
über `import app as A` mit spätem Attribut-Zugriff — Test-Monkeypatches auf dem
app-Namespace (m._notify_telegram, m.send_email, ...) bleiben dadurch wirksam.
"""
import json
import re
import time
from datetime import date, datetime

import app as A


_TREND_WORDS = {'up': ('▲', 'gestiegen'), 'down': ('▼', 'gefallen'), 'flat': ('→', 'stabil')}


def _market_section(con) -> dict | None:
    """Markttrend für den Wochenüberblick. Quelle ist bevorzugt die Messreihe (die
    gespeicherten Suchen, täglich neu ausgeführt — alle Hotels für die eigenen
    Reisetermine), erst ersatzweise der schmalere Trend aus den getrackten Angeboten;
    dieselbe Rangfolge wie beim HA-Sensor. Fenster 7 Tage statt der 14 aus der UI: der
    Digest berichtet über die vergangene Woche, ein 14-Tage-Fenster würde die Vorwoche
    mit hineinziehen."""
    glob = A.basket_trend(con, window_days=7)
    src = 'basket' if glob else 'offers'
    if not glob:
        glob = A._market_trend(con, window_days=7)
    if not glob:
        return None
    # Fester Query-Text je Quelle (kein zur Laufzeit zusammengebautes SQL) — die
    # Tabelle steht hier fest, nicht der Filterwert.
    q = ("SELECT DISTINCT basket AS name FROM basket_moves WHERE basket!=''" if src == 'basket'
         else "SELECT DISTINCT region AS name FROM price_moves WHERE region!=''")
    regions = []
    for name in sorted(r['name'] for r in con.execute(q).fetchall()):
        t = (A.basket_trend(con, basket=name, window_days=7) if src == 'basket'
             else A._market_trend(con, region=name, window_days=7))
        if t:
            regions.append((name, t))
    return {'src': src, 'global': glob, 'regions': regions}


def _market_line(t: dict) -> str:
    """„▼ gefallen (−2,4 %)" — Vorzeichen als Minuszeichen (U+2212), wie in der UI."""
    arrow, word = _TREND_WORDS.get(t['dir'], ('→', 'stabil'))
    pct = abs(t['pct'])
    sign = '+' if t['pct'] > 0 else ('−' if t['pct'] < 0 else '')
    return f"{arrow} {word}" + (f" ({sign}{pct:.1f} %)".replace('.', ',') if pct >= 0.5 else '')


def _build_digest() -> dict | None:
    """Baut die wöchentliche Zusammenfassung (größte Rückgänge, neue Tiefstwerte, unter
    Wunschpreis). Rückgabe {subject, html, text} oder None, wenn es nichts zu melden gibt."""
    offers = [o for o in A._collect_offers() if not o['archived'] and o.get('price') is not None]
    if not offers:
        return None
    with A.db() as con:
        for o in offers:
            o['_wk'] = A._week_change(con, o['id'], o['price'])
        since = int(time.time()) - 7 * 86400
        cal_moves = []
        for o in offers:
            months = A._calendar_moves_since(con, o['id'], since)
            if months:
                cal_moves.append({'name': o.get('label') or o.get('hotel') or f"Angebot #{o['id']}",
                                   'url': o['url'], 'months': A._format_month_list_de(months)})
        market = _market_section(con)
    drops = sorted([o for o in offers if o['_wk'] is not None and o['_wk'] < 0],
                   key=lambda o: o['_wk'])
    rises = sorted([o for o in offers if o['_wk'] is not None and o['_wk'] > 0],
                   key=lambda o: -o['_wk'])
    lows = [o for o in offers if o.get('min_price') is not None
            and o.get('samples', 0) > 2 and o['price'] <= o['min_price']]
    under = [o for o in offers if o.get('target_price') and o['price'] <= o['target_price']]
    trips = A._upcoming_trips()

    try:                                             # aktuelle öffentliche Aktionscodes
        _aktion = json.loads(A._meta_get('aktion_last', '') or '{}')
    except Exception:
        _aktion = {}
    akc = _aktion.get('codes') or []
    ai_summary = A._ai_digest_summary(offers, drops, rises, lows, under, trips, akc)

    def nm(o):
        return o.get('label') or o.get('hotel') or f"Angebot #{o['id']}"

    # ── Text (Telegram) ──
    tl = [f"📊 <b>TUIWatch — Wochenüberblick</b> ({datetime.now():%d.%m.%Y})",
          f"{len(offers)} aktive Reise(n) beobachtet."]
    if ai_summary:
        tl.append(f"\n🤖 {ai_summary}")
    if market:
        _basis = ("alle Hotels für deine gespeicherten Suchen" if market['src'] == 'basket'
                  else "deine getrackten Angebote")
        tl.append(f"\n📈 <b>Markttrend (7 Tage):</b> {_market_line(market['global'])}"
                  f"\n<i>Basis: {_basis}</i>")
        tl += [f"• {name}: {_market_line(t)}" for name, t in market['regions'][:8]]
    if trips:
        tl.append("\n🧳 <b>Bevorstehende Reisen:</b>")
        for t in trips:
            rng = f"{t['start_date']} – {t['end_date']}" if t.get('end_date') else t['start_date']
            tl.append(f"• {t['destination']}: {rng} (in {t['days_until']} Tagen)")
    if under:
        tl.append("\n🎯 <b>Unter Wunschpreis:</b>")
        tl += [f"• {nm(o)}: <b>{A._eur(o['price'])}</b> (Ziel {A._eur(o['target_price'])})" for o in under[:8]]
    if lows:
        tl.append("\n📉 <b>Neuer Tiefstwert:</b>")
        tl += [f"• {nm(o)}: <b>{A._eur(o['price'])}</b>" for o in lows[:8]]
    if drops:
        tl.append("\n▼ <b>Größte Rückgänge (7 Tage):</b>")
        tl += [f"• {nm(o)}: {A._eur(o['price'])} ({A._eur(o['_wk'])})" for o in drops[:8]]
    if rises:
        tl.append("\n▲ <b>Gestiegen (7 Tage):</b>")
        tl += [f"• {nm(o)}: {A._eur(o['price'])} (+{A._eur(abs(o['_wk']))})" for o in rises[:5]]
    if cal_moves:
        tl.append("\n📅 <b>Kalenderpreise geändert:</b>")
        tl += [f"• {c['name']}: {c['months']}" for c in cal_moves]
    if akc:
        tl.append("\n🎟 <b>TUI-Aktionscodes:</b>")
        tl += [f"• {c.get('value')} € — {c.get('code')}"
               + (f" ({c['kind']})" if c.get('kind') else '') for c in akc]
        _ctx = ([f"buchbar bis {_aktion['booking_until']}"] if _aktion.get('booking_until') else []) \
            + ([f"Reisezeitraum {_aktion['travel_period']}"] if _aktion.get('travel_period') else [])
        if _ctx:
            tl.append(" · ".join(_ctx))
    text = "\n".join(tl)

    # ── HTML (E-Mail) ──
    def esc(s):
        return (str(s or '')).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def section(title, items, fmt):
        if not items:
            return ''
        rows = ''.join(f'<li style="margin:4px 0">{fmt(o)}</li>' for o in items)
        return (f'<h3 style="margin:18px 0 6px;color:#10243e;font-size:15px">{title}</h3>'
                f'<ul style="margin:0;padding-left:18px;color:#333;font-size:14px">{rows}</ul>')

    def link(o):
        return f'<a href="{esc(o["url"])}" style="color:#0b65d8;text-decoration:none">{esc(nm(o))}</a>'

    akc_html = ''
    if akc:
        _ctxh = ' · '.join(
            ([f'buchbar bis {esc(_aktion["booking_until"])}'] if _aktion.get('booking_until') else [])
            + ([f'Reisezeitraum {esc(_aktion["travel_period"])}'] if _aktion.get('travel_period') else []))
        _rows = ''.join(
            f'<li style="margin:4px 0"><b>{esc(c.get("value"))} €</b> — {esc(c.get("code"))}'
            + (f' <span style="color:#777">({esc(c["kind"])})</span>' if c.get('kind') else '') + '</li>'
            for c in akc)
        akc_html = ('<h3 style="margin:18px 0 6px;color:#10243e;font-size:15px">🎟 TUI-Aktionscodes</h3>'
                    + (f'<p style="margin:0 0 6px;color:#777;font-size:13px">{_ctxh}</p>' if _ctxh else '')
                    + f'<ul style="margin:0;padding-left:18px;color:#333;font-size:14px">{_rows}</ul>')

    market_html = ''
    if market:
        _basis = ('alle Hotels für deine gespeicherten Suchen (täglicher Preisbarometer)'
                  if market['src'] == 'basket' else 'deine getrackten Angebote')
        _color = {'up': '#cf222e', 'down': '#1a7f37'}.get(market['global']['dir'], '#555')
        _rows = ''.join(
            f'<li style="margin:4px 0">{esc(name)}: {esc(_market_line(t))}</li>'
            for name, t in market['regions'][:8])
        market_html = (
            '<h3 style="margin:18px 0 6px;color:#10243e;font-size:15px">📈 Markttrend (7 Tage)</h3>'
            f'<p style="margin:0;color:{_color};font-size:14px;font-weight:600">'
            f'{esc(_market_line(market["global"]))}</p>'
            f'<p style="margin:2px 0 6px;color:#777;font-size:13px">Basis: {_basis}</p>'
            + (f'<ul style="margin:0;padding-left:18px;color:#333;font-size:14px">{_rows}</ul>'
               if _rows else ''))

    ai_html = ''
    if ai_summary:
        _ai_inline = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', esc(ai_summary)).replace('\n', '<br>')
        ai_html = (f'<div style="background:#f0f4fa;border-radius:8px;padding:12px 14px;'
                  f'color:#10243e;font-size:14px;margin:0 0 16px;line-height:1.5">'
                  f'🤖 {_ai_inline}</div>')

    html = (
        '<div style="font-family:system-ui,Arial,sans-serif;max-width:640px;margin:0 auto">'
        f'<h2 style="color:#10243e">📊 TUIWatch — Wochenüberblick</h2>'
        f'<p style="color:#555;font-size:13px">{datetime.now():%d.%m.%Y} · {len(offers)} aktive Reise(n) beobachtet.</p>'
        + ai_html
        + market_html
        + section('🧳 Bevorstehende Reisen', trips,
                  lambda t: f'<b>{esc(t["destination"])}</b> — {esc(t["start_date"])}'
                            + (f' – {esc(t["end_date"])}' if t.get('end_date') else '')
                            + f' <span style="color:#777">(in {t["days_until"]} Tagen)</span>')
        + section('🎯 Unter Wunschpreis', under,
                  lambda o: f'{link(o)}: <b>{A._eur(o["price"])}</b> <span style="color:#777">(Ziel {A._eur(o["target_price"])})</span>')
        + section('📉 Neuer Tiefstwert', lows,
                  lambda o: f'{link(o)}: <b>{A._eur(o["price"])}</b>')
        + section('▼ Größte Rückgänge (7 Tage)', drops[:8],
                  lambda o: f'{link(o)}: {A._eur(o["price"])} <span style="color:#1a7f37;font-weight:600">({A._eur(o["_wk"])})</span>')
        + section('▲ Gestiegen (7 Tage)', rises[:5],
                  lambda o: f'{link(o)}: {A._eur(o["price"])} <span style="color:#cf222e">(+{A._eur(abs(o["_wk"]))})</span>')
        + section('📅 Kalenderpreise geändert', cal_moves,
                  lambda c: f'<a href="{esc(c["url"])}" style="color:#0b65d8;text-decoration:none">'
                            f'{esc(c["name"])}</a>: {esc(c["months"])}')
        + akc_html
        + '</div>'
    )
    return {'subject': f'TUIWatch — Wochenüberblick {datetime.now():%d.%m.%Y}',
            'html': html, 'text': text}


def send_digest_now() -> bool:
    """Baut und verschickt den Digest sofort über alle konfigurierten Kanäle
    (Telegram + E-Mail). True, wenn mindestens ein Kanal bedient wurde."""
    digest = _build_digest()
    if not digest:
        A.log.info("Digest: nichts zu berichten")
        return False
    sent = False
    cfg = A.load_config()
    if (cfg.get('telegram_bot_token') or '').strip() and (cfg.get('telegram_chat_id') or '').strip():
        A._notify_telegram(digest['text'])
        sent = True
    to = (cfg.get('smtp_to') or '').strip()
    if A.smtp_configured() and to:
        try:
            A.send_email(digest['subject'], digest['html'], to)
            sent = True
        except Exception as e:
            A.log.error("Digest-E-Mail fehlgeschlagen: %s", e)
    if sent:
        A.log.info("Digest verschickt")
    else:
        A.log.info("Digest: kein Kanal konfiguriert (Telegram/SMTP)")
    return sent


def _maybe_send_digest() -> None:
    """Verschickt den Wochen-Digest am eingestellten Wochentag, höchstens 1×/ISO-Woche.
    War das Add-on am Stichtag aus, wird später in der Woche nachgeholt."""
    cfg = A.load_config()
    if not cfg.get('digest_enabled'):
        return
    today = date.today()
    target = min(7, max(1, int(cfg.get('digest_weekday', 1) or 1)))
    if today.isoweekday() < target:
        return
    y, w, _ = today.isocalendar()
    wk = f"{y}-W{w:02d}"
    if A._meta_get('last_digest') == wk:
        return
    if send_digest_now():
        A._meta_set('last_digest', wk)
    else:
        # Kein Kanal konfiguriert → nicht jede Runde neu versuchen
        A._meta_set('last_digest', wk)

