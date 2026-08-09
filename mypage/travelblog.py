"""Reiseblog — Datenmodell und Prompt-Bau.

Reine Logik ohne Flask: Normalisieren der Formulardaten und das Bauen des
Prompts. Die Routen liegen in app.py, damit dieses Modul keine Abhängigkeit
zurück auf die App braucht.

Der Gedanke hinter dem Aufbau: Unterwegs will niemand dreißig Pflichtfelder
ausfüllen. Verpflichtend sind deshalb nur Datum und Reisetag — alles andere
darf leer bleiben, und was leer ist, taucht im Prompt gar nicht erst auf.
Sonst stünde dort „Wetter: —" und das Modell dichtet etwas dazu.
"""
from datetime import date

# ── Auswahllisten ────────────────────────────────────────────────────────────
# Reihenfolge = Reihenfolge im Formular. Die Werte werden so gespeichert, wie
# sie hier stehen, und wandern unverändert in den Prompt: das Modell versteht
# „leicht bewölkt" besser als einen Schlüssel wie `partly_cloudy`.

WEATHER_CONDITIONS = ('sonnig', 'leicht bewölkt', 'bewölkt', 'regnerisch',
                      'wechselhaft', 'stürmisch')
WIND_STRENGTHS = ('windstill', 'leicht', 'mäßig', 'stark', 'sehr stark')
EXPERIENCE_TYPES = ('Ausflug', 'Strand', 'Pool', 'Sehenswürdigkeit', 'Spaziergang',
                    'Wanderung', 'Shopping', 'Restaurant', 'Café / Bar', 'Aktivität',
                    'Hotel', 'Nachtleben', 'Fahrt / Transport', 'Sonstiges')
RECOMMENDATIONS = ('Ja, unbedingt', 'Ja', 'Vielleicht', 'Eher nicht', 'Nein',
                   'Keine Einschätzung')
TRANSPORTS = ('Zu Fuß', 'Bus', 'Taxi', 'Mietwagen', 'Fahrrad', 'Boot',
              'Ausflug/Transfer', 'ÖPNV', 'Sonstiges')
MEAL_TYPES = ('Frühstück', 'Mittagessen', 'Abendessen', 'Snack', 'Café', 'Bar',
              'Sonstiges')
MOMENT_CATEGORIES = ('Highlight', 'Lustiger Moment', 'Überraschung', 'Ärgernis',
                     'Begegnung', 'Natur', 'Sonnenaufgang', 'Sonnenuntergang',
                     'Tier', 'Sonstiges')
EXPENSE_CATEGORIES = ('Transport', 'Essen', 'Getränke', 'Eintritt', 'Shopping',
                      'Souvenir', 'Hotel', 'Ausflug', 'Sonstiges')
CURRENCIES = ('EUR', 'CHF', 'USD', 'GBP', 'DKK', 'NOK', 'SEK', 'PLN', 'CZK',
              'HUF', 'TRY', 'THB', 'Sonstige')

WRITING_STYLES = {
    'persoenlich_locker': 'persönlich und locker, wie einem Freund erzählt',
    'persoenlich_humorvoll': 'persönlich und humorvoll, mit Augenzwinkern',
    'reisetagebuch': 'wie ein Reisetagebuch, ruhig und beobachtend',
    'sachlich_persoenlich': 'sachlich, aber mit persönlicher Note',
}
PERSPECTIVES = {'ich': 'Ich-Form (Singular)', 'wir': 'Wir-Form (Plural)',
                'neutral': 'neutral, ohne Ich oder Wir'}
LENGTHS = {'kurz': 350, 'mittel': 700, 'lang': 1200}

MAX_ITEMS = 40          # je Liste (Erlebnisse, Essen, Momente, Ausgaben, Fotos)
MAX_DAYS = 400          # je Reise
MAX_TRIPS = 100
PROMPT_PREV_DAYS = 4    # so viele Vortage kommen als Kontext mit


# ── Normalisieren ────────────────────────────────────────────────────────────

def _s(value, limit: int = 200) -> str:
    """String säubern und kürzen. Nicht-Strings werden zu ''."""
    if value is None or isinstance(value, (dict, list, bool)):
        return ''
    text = str(value).replace('\x00', '').strip()
    return text[:limit]


def _num(value, lo: float, hi: float, decimals: int = 2):
    """Zahl im Bereich oder None. None heißt „nicht angegeben" und wird später
    im Prompt weggelassen — anders als 0, das eine Aussage ist: Eintritt frei,
    null Grad, nichts bezahlt.

    Die Prüfung steht bewusst so ausgeschrieben: `value in (None, '', False)`
    würde die 0 mit verschlucken, weil `0 == False` in Python wahr ist.
    """
    if value is None or value == '' or isinstance(value, bool):
        return None
    try:
        n = round(float(value), decimals)
    except (TypeError, ValueError):
        return None
    if not lo <= n <= hi:
        return None
    return int(n) if decimals == 0 else n


def _pick(value, allowed, default: str = '') -> str:
    v = _s(value, 60)
    return v if v in allowed else default


def _rating(value):
    return _num(value, 1, 5, 0)


def _time(value) -> str:
    """HH:MM oder ''. Bewusst streng: ein krummer Wert im Prompt wirkt wie eine
    Angabe, die es nicht gibt."""
    v = _s(value, 5)
    if len(v) == 5 and v[2] == ':' and v[:2].isdigit() and v[3:].isdigit():
        if 0 <= int(v[:2]) <= 23 and 0 <= int(v[3:]) <= 59:
            return v
    return ''


def _date(value) -> str:
    v = _s(value, 10)
    try:
        date.fromisoformat(v)
    except ValueError:
        return ''
    return v


def normalize_trip(raw: dict, existing: dict | None = None) -> dict:
    """Reise aus Formulardaten. `existing` erhält Felder, die das Formular nicht
    schickt (vor allem die Tage)."""
    t = dict(existing or {})
    t['name'] = _s(raw.get('name'), 120)
    t['destination'] = _s(raw.get('destination'), 120)
    t['hotel'] = _s(raw.get('hotel'), 160)
    t['travel_start'] = _date(raw.get('travel_start'))
    t['travel_end'] = _date(raw.get('travel_end'))
    # Der Slug wird in app.py gesetzt (nur dort ist bekannt, welche schon
    # vergeben sind). Ein leerer Wert im Formular heißt „neu ableiten", ein
    # fehlendes Feld dagegen „unverändert lassen" — sonst verlöre ein Aufruf
    # ohne Slug-Feld die Adresse, unter der die Reise schon verlinkt ist.
    t['slug'] = _s(raw.get('slug'), 60) or _s((existing or {}).get('slug'), 60)
    t['members_only'] = bool(raw.get('members_only'))
    s = raw.get('settings') if isinstance(raw.get('settings'), dict) else {}
    t['settings'] = {
        'writing_style': _pick(s.get('writing_style'), WRITING_STYLES, 'persoenlich_locker'),
        'perspective': _pick(s.get('perspective'), PERSPECTIVES, 'wir'),
        'length': _pick(s.get('length'), LENGTHS, 'mittel'),
        'humor': bool(s.get('humor')),
        'include_prices': bool(s.get('include_prices', True)),
        'include_practical_info': bool(s.get('include_practical_info', True)),
        'include_ratings': bool(s.get('include_ratings', True)),
        'langs': [lg for lg in ('de', 'en') if lg in (s.get('langs') or ['de'])] or ['de'],
    }
    t.setdefault('days', [])
    return t


def _norm_experience(raw: dict) -> dict:
    return {
        'type': _pick(raw.get('type'), EXPERIENCE_TYPES, EXPERIENCE_TYPES[0]),
        'title': _s(raw.get('title'), 160),
        'start_time': _time(raw.get('start_time')),
        'end_time': _time(raw.get('end_time')),
        'description': _s(raw.get('description'), 3000),
        'rating': _rating(raw.get('rating')),
        'positive': _s(raw.get('positive'), 1000),
        'negative': _s(raw.get('negative'), 1000),
        'highlight': _s(raw.get('highlight'), 1000),
        'recommendation': _pick(raw.get('recommendation'), RECOMMENDATIONS),
        'entry_fee': _num(raw.get('entry_fee'), 0, 100000),
        'currency': _pick(raw.get('currency'), CURRENCIES),
        'transport': _pick(raw.get('transport'), TRANSPORTS),
        'travel_time': _num(raw.get('travel_time'), 0, 10000, 0),
        'distance': _num(raw.get('distance'), 0, 100000),
        'opening_hours': _s(raw.get('opening_hours'), 200),
        'practical_info': _s(raw.get('practical_info'), 2000),
    }


def _norm_meal(raw: dict) -> dict:
    return {
        'meal_type': _pick(raw.get('meal_type'), MEAL_TYPES, MEAL_TYPES[0]),
        'restaurant': _s(raw.get('restaurant'), 160),
        'location': _s(raw.get('location'), 160),
        'food': _s(raw.get('food'), 1000),
        'drinks': _s(raw.get('drinks'), 500),
        'price': _num(raw.get('price'), 0, 100000),
        'currency': _pick(raw.get('currency'), CURRENCIES),
        'rating': _rating(raw.get('rating')),
        'taste': _s(raw.get('taste'), 500),
        'comment': _s(raw.get('comment'), 1000),
    }


def _norm_moment(raw: dict) -> dict:
    return {
        'category': _pick(raw.get('category'), MOMENT_CATEGORIES, MOMENT_CATEGORIES[0]),
        'time': _time(raw.get('time')),
        'title': _s(raw.get('title'), 160),
        'description': _s(raw.get('description'), 2000),
    }


def _norm_expense(raw: dict) -> dict:
    return {
        'category': _pick(raw.get('category'), EXPENSE_CATEGORIES, EXPENSE_CATEGORIES[0]),
        'description': _s(raw.get('description'), 160),
        'amount': _num(raw.get('amount'), 0, 1000000),
        'currency': _pick(raw.get('currency'), CURRENCIES, 'EUR'),
    }


def _norm_photo(raw: dict) -> dict:
    return {'url': _s(raw.get('url'), 300), 'photo_note': _s(raw.get('photo_note'), 300),
            'caption_de': _s(raw.get('caption_de'), 300),
            'caption_en': _s(raw.get('caption_en'), 300)}


def _list(raw, key, fn) -> list:
    items = raw.get(key)
    if not isinstance(items, list):
        return []
    return [fn(x) for x in items[:MAX_ITEMS] if isinstance(x, dict)]


def normalize_day(raw: dict, existing: dict | None = None) -> dict:
    """Ein Reisetag. Alles außer Datum und Tagesnummer darf leer sein."""
    d = dict(existing or {})
    d['day_number'] = _num(raw.get('day_number'), 1, 999, 0) or 1
    d['date'] = _date(raw.get('date'))
    # Ein Tag ist erst online, wenn er ausdrücklich freigegeben wurde. Ohne
    # diesen Schalter stünde jeder halbfertige Tag in dem Moment im Netz, in
    # dem er gespeichert wird — und gespeichert wird unterwegs ständig.
    d['published'] = bool(raw.get('published'))
    d['slug'] = _s(raw.get('slug'), 60) or _s((existing or {}).get('slug'), 60)
    d['location'] = _s(raw.get('location'), 160)
    d['hotel'] = _s(raw.get('hotel'), 160)
    w = raw.get('weather') if isinstance(raw.get('weather'), dict) else {}
    d['weather'] = {
        'mention': bool(w.get('mention')),
        'condition': _pick(w.get('condition'), WEATHER_CONDITIONS),
        'temperature': _num(w.get('temperature'), -60, 60, 0),
        'wind': _pick(w.get('wind'), WIND_STRENGTHS),
        'comment': _s(w.get('comment'), 1000),
    }
    d['experiences'] = _list(raw, 'experiences', _norm_experience)
    d['meals'] = _list(raw, 'meals', _norm_meal)
    d['special_moments'] = _list(raw, 'special_moments', _norm_moment)
    d['expenses'] = _list(raw, 'expenses', _norm_expense)
    d['photos'] = _list(raw, 'photos', _norm_photo)
    p = raw.get('personal') if isinstance(raw.get('personal'), dict) else {}
    d['personal'] = {
        'day_highlight': _s(p.get('day_highlight'), 1000),
        'day_positive': _s(p.get('day_positive'), 1000),
        'day_negative': _s(p.get('day_negative'), 1000),
        'funny_moment': _s(p.get('funny_moment'), 1000),
        'unexpected': _s(p.get('unexpected'), 1000),
        'day_summary': _s(p.get('day_summary'), 2000),
        'overall_rating': _rating(p.get('overall_rating')),
    }
    d['additional_notes'] = _s(raw.get('additional_notes'), 4000)
    d['important'] = _s(raw.get('important'), 1000)
    d['exclude'] = _s(raw.get('exclude'), 1000)
    # Der erzeugte Artikel wird getrennt gespeichert und beim Bearbeiten der
    # Rohdaten nicht angefasst — sonst wäre eine Korrektur am Text nach jedem
    # Nachtragen einer Ausgabe verloren.
    art = raw.get('article') if isinstance(raw.get('article'), dict) else None
    if art is not None or 'article' not in d:
        d['article'] = normalize_article(art or {})
    return d


def normalize_article(raw: dict) -> dict:
    out = {}
    for lg in ('de', 'en'):
        out[lg] = {
            'title': _s(raw.get(lg, {}).get('title') if isinstance(raw.get(lg), dict) else '', 200),
            'teaser': _s(raw.get(lg, {}).get('teaser') if isinstance(raw.get(lg), dict) else '', 300),
            'body': _s(raw.get(lg, {}).get('body') if isinstance(raw.get(lg), dict) else '', 40000),
        }
    tags = raw.get('tags') if isinstance(raw.get('tags'), list) else []
    out['tags'] = [_s(t, 40) for t in tags[:8] if _s(t, 40)]
    caps = raw.get('captions') if isinstance(raw.get('captions'), list) else []
    out['captions'] = [{'de': _s((c or {}).get('de'), 300), 'en': _s((c or {}).get('en'), 300)}
                       for c in caps[:MAX_ITEMS] if isinstance(c, dict)]
    return out


def expense_total(day: dict) -> dict:
    """Summe je Währung. Getrennt statt umgerechnet: einen Wechselkurs zu raten
    wäre eine erfundene Zahl in einem Bericht, der keine enthalten soll."""
    totals: dict[str, float] = {}
    for e in day.get('expenses') or []:
        if e.get('amount') is None:
            continue
        cur = e.get('currency') or 'EUR'
        totals[cur] = round(totals.get(cur, 0) + e['amount'], 2)
    return totals


# ── Prompt ───────────────────────────────────────────────────────────────────

def _money(amount, currency: str = '') -> str:
    """Betrag deutsch formatiert. Die Regel im Systemprompt lautet „Preise exakt
    übernehmen" — dann muss auch exakt dastehen, was gemeint ist: 2,80 statt 2.8."""
    text = f'{amount:.2f}'.replace('.', ',')
    return f'{text} {currency}'.strip()


def _fmt_date(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime('%d.%m.%Y')
    except ValueError:
        return iso


def _block(title: str, lines: list) -> str:
    """Abschnitt nur ausgeben, wenn er Inhalt hat. Leere Abschnitte wären eine
    Einladung, sie mit Erfundenem zu füllen."""
    body = [x for x in lines if x]
    return f"{title}\n" + '\n'.join(body) if body else ''


def build_prompt(trip: dict, day: dict, previous: list | None = None) -> str:
    """Baut den Prompt aus Reise und Tag. Leere Felder fallen komplett weg."""
    s = trip.get('settings') or {}
    parts = []

    parts.append(_block('REISE', [
        f"Reiseziel: {trip.get('destination')}" if trip.get('destination') else '',
        f"Reise: {trip.get('name')}" if trip.get('name') else '',
        f"Unterkunft: {day.get('hotel') or trip.get('hotel')}"
        if (day.get('hotel') or trip.get('hotel')) else '',
        f"Reisetag: {day.get('day_number')}",
        f"Datum: {_fmt_date(day.get('date') or '')}" if day.get('date') else '',
        f"Ort: {day.get('location')}" if day.get('location') else '',
    ]))

    parts.append(_block('SCHREIBSTIL', [
        f"Perspektive: {PERSPECTIVES.get(s.get('perspective'), PERSPECTIVES['wir'])}",
        f"Stil: {WRITING_STYLES.get(s.get('writing_style'), WRITING_STYLES['persoenlich_locker'])}",
        f"Zielumfang: rund {LENGTHS.get(s.get('length'), 700)} Wörter",
        'Humor ist erwünscht, aber dezent.' if s.get('humor') else '',
    ]))

    w = day.get('weather') or {}
    if w.get('mention'):
        parts.append(_block('WETTER', [
            w.get('condition') or '',
            f"{w['temperature']} °C" if w.get('temperature') is not None else '',
            f"Wind: {w['wind']}" if w.get('wind') else '',
            f"Eindruck: {w['comment']}" if w.get('comment') else '',
        ]))

    for i, e in enumerate(day.get('experiences') or [], 1):
        zeit = ' bis '.join(x for x in (e.get('start_time'), e.get('end_time')) if x)
        lines = [
            e.get('title') or '',
            f"Art: {e.get('type')}" if e.get('type') else '',
            f"Uhrzeit: {zeit} Uhr" if zeit else '',
            e.get('description') or '',
        ]
        if s.get('include_practical_info', True):
            lines += [
                f"Anreise: {e['transport']}" if e.get('transport') else '',
                f"Fahrzeit: {e['travel_time']} Minuten" if e.get('travel_time') else '',
                f"Entfernung: {e['distance']} km" if e.get('distance') else '',
                f"Öffnungszeiten: {e['opening_hours']}" if e.get('opening_hours') else '',
                e.get('practical_info') or '',
            ]
        if s.get('include_prices', True) and e.get('entry_fee') is not None:
            lines.append('Eintritt frei' if e['entry_fee'] == 0 else
                         f"Eintritt: {_money(e['entry_fee'], e.get('currency') or 'EUR')}")
        if s.get('include_ratings', True):
            lines += [
                f"Bewertung: {e['rating']} von 5" if e.get('rating') else '',
                f"Gut gefallen: {e['positive']}" if e.get('positive') else '',
                f"Weniger gut: {e['negative']}" if e.get('negative') else '',
                f"Highlight: {e['highlight']}" if e.get('highlight') else '',
                f"Empfehlung: {e['recommendation']}" if e.get('recommendation') else '',
            ]
        parts.append(_block(f'ERLEBNIS {i}', lines))

    for m in day.get('meals') or []:
        wo = ' — '.join(x for x in (m.get('restaurant'), m.get('location')) if x)
        lines = [
            f"{m.get('meal_type')}{': ' + wo if wo else ''}",
            f"Gegessen: {m['food']}" if m.get('food') else '',
            f"Getrunken: {m['drinks']}" if m.get('drinks') else '',
            m.get('taste') or '',
            m.get('comment') or '',
        ]
        if s.get('include_prices', True) and m.get('price') is not None:
            lines.append(f"Preis: {_money(m['price'], m.get('currency') or 'EUR')}")
        if s.get('include_ratings', True) and m.get('rating'):
            lines.append(f"Bewertung: {m['rating']} von 5")
        parts.append(_block('ESSEN & TRINKEN', lines))

    for mo in day.get('special_moments') or []:
        parts.append(_block('BESONDERER MOMENT', [
            f"{mo.get('category')}{' um ' + mo['time'] + ' Uhr' if mo.get('time') else ''}",
            mo.get('title') or '',
            mo.get('description') or '',
        ]))

    p = day.get('personal') or {}
    parts.append(_block('PERSÖNLICHE EINDRÜCKE', [
        f"Highlight des Tages: {p['day_highlight']}" if p.get('day_highlight') else '',
        f"Besonders gut gefallen: {p['day_positive']}" if p.get('day_positive') else '',
        f"Nicht gefallen: {p['day_negative']}" if p.get('day_negative') else '',
        f"Lustig oder kurios: {p['funny_moment']}" if p.get('funny_moment') else '',
        f"Unerwartet: {p['unexpected']}" if p.get('unexpected') else '',
        f"Der Tag insgesamt: {p['day_summary']}" if p.get('day_summary') else '',
        f"Gesamtbewertung: {p['overall_rating']} von 5"
        if (p.get('overall_rating') and s.get('include_ratings', True)) else '',
    ]))

    if s.get('include_prices', True):
        totals = expense_total(day)
        parts.append(_block('AUSGABEN', [
            f"{e.get('category')}: {e.get('description') or ''} "
            f"{_money(e['amount'], e.get('currency') or 'EUR')}".replace('  ', ' ')
            for e in (day.get('expenses') or []) if e.get('amount') is not None
        ] + ([', '.join(f'Summe: {_money(v, k)}' for k, v in totals.items())]
             if totals else [])))

    notes = [f"Fotohinweis {i}: {ph['photo_note']}"
             for i, ph in enumerate(day.get('photos') or [], 1) if ph.get('photo_note')]
    parts.append(_block('FOTOS', notes))

    parts.append(_block('FREIE ERGÄNZUNGEN', [day.get('additional_notes') or '']))
    parts.append(_block('BESONDERS HERVORHEBEN', [day.get('important') or '']))
    parts.append(_block('NICHT ERWÄHNEN', [day.get('exclude') or '']))

    # Vortage als Kontext: ohne sie kann das Modell die Regel „keine
    # Wiederholungen" nicht einhalten, es kennt die anderen Tage ja nicht.
    prev_lines = []
    for d in (previous or [])[-PROMPT_PREV_DAYS:]:
        art = (d.get('article') or {}).get('de') or {}
        title = art.get('title') or d.get('location') or ''
        summary = (d.get('personal') or {}).get('day_summary') or ''
        if title or summary:
            prev_lines.append(f"Tag {d.get('day_number')}: {title}"
                              + (f" — {summary}" if summary else ''))
    parts.append(_block('BEREITS GESCHRIEBENE TAGE (nicht wiederholen)', prev_lines))

    return '\n\n'.join(x for x in parts if x)


SYSTEM_PROMPT = (
    "Du bist der Autor eines persönlichen Reiseblogs und schreibst den Tagesbericht "
    "für den Reisenden selbst.\n"
    "REGELN:\n"
    "- Verwende ausschließlich die gelieferten Angaben. Erfinde nichts dazu: keine "
    "Sehenswürdigkeiten, keine Öffnungszeiten, keine Geschichte des Ortes, keine "
    "Zahlen, keine Namen.\n"
    "- Steht etwas nicht in den Daten, lass es weg statt es zu ergänzen.\n"
    "- Preise und Bewertungen exakt übernehmen.\n"
    "- Persönliche Eindrücke als Eindruck formulieren, nicht als Tatsache.\n"
    "- Nicht werblich, keine übertriebenen Superlative, keine Reiseführer-Floskeln.\n"
    "- Erzähle die Erlebnisse chronologisch.\n"
    "- Was unter NICHT ERWÄHNEN steht, kommt im Text nicht vor.\n"
    "- Antworte ausschließlich im vorgegebenen JSON-Schema.\n"
    "FELDER: 'title' = Überschrift ohne Markdown-Zeichen; 'teaser' = Anrisstext, "
    "höchstens 250 Zeichen; 'body' = der Bericht in Markdown mit Einstieg, Verlauf, "
    "persönlichen Eindrücken und kurzem Fazit, Zwischenüberschriften ab '##'; "
    "'tags' = drei bis fünf Schlagwörter; 'captions' = je Fotohinweis eine kurze "
    "Bildunterschrift, in derselben Reihenfolge."
)
