"""Jeopardy-Board — Quiz-Duell gegen eine KI (1 Mensch + 1 KI).

Server-autoritativ: Der Server kennt die richtigen Antworten, der Client nie
(public_view entfernt die Lösung, bis ein Clue aufgelöst ist). Die KI „weiß"
nichts — sie simuliert einen Gegner mit schwierigkeitsabhängiger Buzzer-Zeit
und Trefferquote.

Ablauf:
- Board 6 Kategorien x 5 Werte (200–1000). Wert ⇒ Schwierigkeit
  (200/400 = leicht, 600 = mittel, 800/1000 = schwer).
- Wer „Kontrolle" hat, wählt den nächsten Clue. Normaler Clue = Buzzer-Rennen:
  Spieler klickt den Buzzer, die KI hat eine ausgewürfelte Buzzer-Zeit.
- Daily Double (1 verstecktes Feld): nur der Wählende spielt, setzt einen Einsatz.
- Ist das Board leer, folgt Final Jeopardy: beide setzen geheim auf einen letzten
  Clue.

Statusse: select, clue, answer, daily_double, reveal, final_wager, final_answer,
game_over.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

VALUES = (200, 400, 600, 800, 1000)
VALUE_DIFF = {200: 'easy', 400: 'easy', 600: 'medium', 800: 'hard', 1000: 'hard'}
CATEGORIES = ('general', 'history', 'geo', 'science', 'sport', 'film')

# KI-Trefferquote je Level, plus Aufschlag/Abschlag nach Clue-Schwierigkeit.
_LEVEL_ACC = {'easy': 0.55, 'medium': 0.72, 'hard': 0.85}
_DIFF_ADJ = {'easy': 0.12, 'medium': 0.0, 'hard': -0.12}
# Buzzer-Zeitfenster der KI je Level (ms, min/max). Höheres Level = schneller.
_KI_BUZZ_MS = {'easy': (1600, 4200), 'medium': (1100, 3200), 'hard': (700, 2300)}
BUZZ_WINDOW_MS = 6000  # so lange darf der Spieler buzzern (Client-Countdown)

_POOL_PATH = Path(__file__).parent / 'data' / 'quiz_pool.json'
_POOL_CACHE: dict | None = None


class IllegalMove(Exception):
    pass


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _load_pool() -> dict:
    global _POOL_CACHE
    if _POOL_CACHE is None:
        with open(_POOL_PATH, encoding='utf-8') as f:
            _POOL_CACHE = json.load(f)
    return _POOL_CACHE


def _ki_correct_prob(level: str, diff: str) -> float:
    return _clamp(_LEVEL_ACC.get(level, 0.72) + _DIFF_ADJ.get(diff, 0.0), 0.15, 0.97)


# ── Board-Aufbau ────────────────────────────────────────────────────────────

def _shuffle_clue(q: dict) -> dict:
    """Wählt eine zufällige Options-Permutation (gleich für DE/EN) und merkt den
    korrekten Index."""
    order = list(range(4))
    random.shuffle(order)
    de = [q['opts_de'][i] for i in order]
    en = [q['opts_en'][i] for i in order]
    correct = order.index(q['c'])
    return {'q_de': q['q_de'], 'q_en': q['q_en'],
            'opts_de': de, 'opts_en': en, 'c': correct}


def _pick_clues(level: str) -> tuple[dict, dict]:
    """Baut die Board-Struktur (sichtbar) und die Clue-Daten (geheim) auf."""
    pool = _load_pool()
    by_cd: dict = {}
    for q in pool['questions']:
        by_cd.setdefault((q['cat'], q['diff']), []).append(q)
    for v in by_cd.values():
        random.shuffle(v)

    cats_meta = pool['categories']
    board_cats = list(CATEGORIES)
    random.shuffle(board_cats)

    board = []        # sichtbare Struktur
    clues = {}        # cellId -> geheime Clue-Daten (inkl. korrektem Index)
    for ci, cat in enumerate(board_cats):
        used_q: set = set()
        cells = []
        for vi, value in enumerate(VALUES):
            diff = VALUE_DIFF[value]
            q = _take(by_cd, cat, diff, used_q)
            cells.append({'value': value, 'used': False, 'dd': False})
            clues[f'{ci}-{vi}'] = {**_shuffle_clue(q), 'value': value,
                                   'cat': cat, 'diff': diff}
        board.append({'cat': cat,
                      'label_de': cats_meta[cat]['de'],
                      'label_en': cats_meta[cat]['en'],
                      'cells': cells})

    # Ein Daily Double auf einem nicht-untersten Feld.
    ci = random.randrange(len(board))
    vi = random.randint(1, len(VALUES) - 1)
    board[ci]['cells'][vi]['dd'] = True
    return board, clues


def _take(by_cd: dict, cat: str, diff: str, used: set) -> dict:
    """Holt eine noch ungenutzte Frage (cat, diff); fällt auf andere Stufen der
    Kategorie zurück, falls eine Stufe leer ist."""
    for d in (diff, 'medium', 'easy', 'hard'):
        for q in by_cd.get((cat, d), []):
            key = id(q)
            if key not in used:
                used.add(key)
                return q
    raise IllegalMove('quiz pool zu klein')


def _final_clue(st: dict) -> dict:
    """Wählt einen Clue für Final Jeopardy, der nicht im Board war."""
    pool = _load_pool()
    used_text = {c['q_de'] for c in st['clues'].values()}
    cands = [q for q in pool['questions']
             if q['diff'] in ('medium', 'hard') and q['q_de'] not in used_text]
    if not cands:
        cands = pool['questions']
    q = random.choice(cands)
    cat = q['cat']
    meta = pool['categories'][cat]
    return {**_shuffle_clue(q), 'cat': cat, 'diff': q['diff'],
            'label_de': meta['de'], 'label_en': meta['en']}


def new_game(level: str = 'medium') -> dict:
    level = level if level in ('easy', 'medium', 'hard') else 'medium'
    board, clues = _pick_clues(level)
    return {
        'status': 'select',
        'level': level,
        'board': board,
        'clues': clues,
        'scores': {'p': 0, 'a': 0},
        'control': 'p',          # wer wählt
        'current': None,         # cellId des offenen Clues
        'active': None,          # öffentlicher Clue (ohne Lösung)
        'turn': None,            # wer gerade antwortet ('p'/'a')
        'rebuttal': False,       # zweite Chance nach falscher Antwort
        'ki_buzz_ms': None,      # geheim: Buzzer-Zeit der KI (oder None)
        'remaining': len(VALUES) * len(CATEGORIES),
        'last_result': None,     # für die reveal-Anzeige
        'final': None,
        'winner': None,
    }


# ── Hilfen ──────────────────────────────────────────────────────────────────

def _cell(st: dict, cell_id: str) -> dict | None:
    try:
        ci, vi = (int(x) for x in cell_id.split('-'))
    except (ValueError, AttributeError):
        return None
    if 0 <= ci < len(st['board']) and 0 <= vi < len(VALUES):
        return st['board'][ci]['cells'][vi]
    return None


def _active_public(st: dict, clue: dict, lang_both: bool = True) -> dict:
    return {'cat': clue['cat'], 'value': clue['value'], 'dd': st.get('_dd', False),
            'q_de': clue['q_de'], 'q_en': clue['q_en'],
            'opts_de': clue['opts_de'], 'opts_en': clue['opts_en']}


def _ki_roll_buzz(st: dict, clue: dict) -> None:
    """Würfelt aus, ob/wann die KI buzzert (geheim im State)."""
    prob = _clamp(_ki_correct_prob(st['level'], clue['diff']) + 0.05, 0.2, 0.95)
    if random.random() < prob:
        lo, hi = _KI_BUZZ_MS[st['level']]
        st['ki_buzz_ms'] = random.randint(lo, hi)
    else:
        st['ki_buzz_ms'] = None


def _ki_answers_correctly(st: dict, confident: bool) -> bool:
    clue = st['clues'][st['current']]
    p = _ki_correct_prob(st['level'], clue['diff'])
    if confident:
        p = _clamp(p + 0.15, 0.2, 0.98)
    return random.random() < p


def _to_reveal(st: dict, winner: str | None, player_picked: int | None = None) -> None:
    """Schließt den Clue ab und merkt das Ergebnis für die Anzeige."""
    clue = st['clues'][st['current']]
    cell = _cell(st, st['current'])
    if cell:
        cell['used'] = True
    before = st.get('_score_before') or {'p': 0, 'a': 0}
    delta = {'p': st['scores']['p'] - before.get('p', 0),
             'a': st['scores']['a'] - before.get('a', 0)}
    st['last_result'] = {
        'cat': clue['cat'], 'value': clue['value'], 'dd': st.get('_dd', False),
        'q_de': clue['q_de'], 'q_en': clue['q_en'],
        'opts_de': clue['opts_de'], 'opts_en': clue['opts_en'],
        'correct': clue['c'], 'picked': player_picked, 'winner': winner,
        'delta': delta, 'scores': dict(st['scores']),
    }
    st['status'] = 'reveal'
    st['turn'] = None
    st['active'] = None
    st['ki_buzz_ms'] = None
    st['rebuttal'] = False
    st.pop('_dd', None)
    if winner in ('p', 'a'):
        st['control'] = winner


def _award(st: dict, who: str, delta: int) -> None:
    st['scores'][who] += delta


# ── Spieleraktionen (apply_action) ──────────────────────────────────────────

def apply_action(st: dict, who: str, act: dict) -> None:
    if who != 'p':
        raise IllegalMove('only player moves here')
    typ = act.get('type')

    if typ == 'pick':
        if st['status'] != 'select' or st['control'] != 'p':
            raise IllegalMove('not your pick')
        cell_id = act.get('cell', '')
        cell = _cell(st, cell_id)
        if cell is None or cell['used']:
            raise IllegalMove('bad cell')
        _open_cell(st, cell_id)
        return

    if typ == 'buzz':
        if st['status'] != 'clue':
            raise IllegalMove('not buzzable')
        elapsed = _clamp_int(act.get('elapsed_ms'), 120, BUZZ_WINDOW_MS)
        ki = st.get('ki_buzz_ms')
        if ki is not None and ki <= elapsed:
            # KI war schneller → KI beantwortet.
            st['status'] = 'answer'
            st['turn'] = 'a'
            st['rebuttal'] = False
        else:
            st['status'] = 'answer'
            st['turn'] = 'p'
            st['rebuttal'] = False
        return

    if typ == 'pass':
        if st['status'] != 'clue':
            raise IllegalMove('nothing to pass')
        if st.get('ki_buzz_ms') is not None:
            st['status'] = 'answer'
            st['turn'] = 'a'
            st['rebuttal'] = False
        else:
            _to_reveal(st, None)
        return

    if typ == 'answer':
        if st['status'] != 'answer' or st['turn'] != 'p':
            raise IllegalMove('not your answer')
        idx = _clamp_int(act.get('idx'), 0, 3)
        clue = st['clues'][st['current']]
        value = _wager_or_value(st)
        if idx == clue['c']:
            _award(st, 'p', value)
            _to_reveal(st, 'p', idx)
        else:
            _award(st, 'p', -value)
            if st.get('_dd'):
                _to_reveal(st, None, idx)            # Daily Double: keine Rebuttal
            elif not st['rebuttal'] and st.get('ki_buzz_ms') is not None:
                st['turn'] = 'a'                     # KI bekommt zweite Chance
                st['rebuttal'] = True
                st['_player_picked'] = idx
            else:
                _to_reveal(st, None, idx)
        return

    if typ == 'wager':
        if st['status'] != 'daily_double':
            raise IllegalMove('no wager now')
        st['_wager'] = _clean_wager(act.get('amount'), st['scores']['p'])
        st['status'] = 'answer'
        st['turn'] = 'p'
        st['rebuttal'] = False
        return

    if typ == 'final_wager':
        if st['status'] != 'final_wager':
            raise IllegalMove('no final wager now')
        st['final']['wager_p'] = _clean_wager(act.get('amount'), st['scores']['p'])
        st['status'] = 'final_answer'
        return

    if typ == 'final_answer':
        if st['status'] != 'final_answer':
            raise IllegalMove('no final answer now')
        idx = _clamp_int(act.get('idx'), 0, 3)
        _resolve_final(st, idx)
        return

    if typ == 'continue':
        if st['status'] != 'reveal':
            raise IllegalMove('nothing to continue')
        _advance(st)
        return

    raise IllegalMove(f'unknown action {typ}')


def _open_cell(st: dict, cell_id: str) -> None:
    st['current'] = cell_id
    cell = _cell(st, cell_id)
    clue = st['clues'][cell_id]
    st['_score_before'] = dict(st['scores'])   # für die Punkte-Differenz im Reveal
    st['_dd'] = bool(cell and cell['dd'])
    st['active'] = _active_public(st, clue)
    if st['_dd'] and st['control'] == 'p':
        st['status'] = 'daily_double'      # nur der Spieler setzt + antwortet
        st['turn'] = 'p'
    elif st['_dd'] and st['control'] == 'a':
        # KI hat ein Daily Double getroffen → KI setzt + antwortet (via /ai).
        st['status'] = 'answer'
        st['turn'] = 'a'
    else:
        st['status'] = 'clue'
        st['turn'] = None
        _ki_roll_buzz(st, clue)


def _wager_or_value(st: dict) -> int:
    if st.get('_dd') and '_wager' in st:
        return st['_wager']
    return st['clues'][st['current']]['value']


def _advance(st: dict) -> None:
    """Nach reveal: nächster Clue oder Final Jeopardy oder Spielende."""
    if _count_unused(st) > 0:
        st['remaining'] = _count_unused(st)
        st['status'] = 'select'
        st['current'] = None
        st['last_result'] = None
        st.pop('_wager', None)
        st.pop('_player_picked', None)
        st.pop('_score_before', None)
    else:
        _start_final(st)


def _count_unused(st: dict) -> int:
    return sum(1 for col in st['board'] for c in col['cells'] if not c['used'])


def _start_final(st: dict) -> None:
    st['remaining'] = 0
    st['last_result'] = None
    st.pop('_wager', None)
    st.pop('_player_picked', None)
    clue = _final_clue(st)
    st['final'] = {'clue': clue, 'wager_p': None, 'wager_a': None,
                   'picked_p': None, 'ki_correct': None}
    st['status'] = 'final_wager'
    st['current'] = None
    st['active'] = None
    st['turn'] = 'p'


def _resolve_final(st: dict, player_idx: int) -> None:
    fin = st['final']
    clue = fin['clue']
    fin['picked_p'] = player_idx
    # KI: Einsatz + Antwort auswürfeln
    fin['wager_a'] = _ki_final_wager(st)
    ki_ok = _ki_answers_correctly_final(st, clue)
    fin['ki_correct'] = ki_ok
    # Spieler werten
    if player_idx == clue['c']:
        _award(st, 'p', fin['wager_p'])
    else:
        _award(st, 'p', -fin['wager_p'])
    # KI werten
    if ki_ok:
        _award(st, 'a', fin['wager_a'])
    else:
        _award(st, 'a', -fin['wager_a'])
    fin['correct'] = clue['c']
    _finish(st)


def _finish(st: dict) -> None:
    st['status'] = 'game_over'
    p, a = st['scores']['p'], st['scores']['a']
    st['winner'] = 'p' if p > a else ('a' if a > p else 'tie')
    st['turn'] = None
    st['active'] = None


def _ki_final_wager(st: dict) -> int:
    p, a = st['scores']['p'], st['scores']['a']
    if a <= 0:
        return 0
    if a <= p:                       # im Rückstand → aggressiv (genug zum Überholen)
        return int(_clamp(p - a + 200, 0, a))
    return int(a * 0.25)             # in Führung → vorsichtig


def _ki_answers_correctly_final(st: dict, clue: dict) -> bool:
    return random.random() < _ki_correct_prob(st['level'], clue['diff'])


# ── KI-Schritt (ai_step) ────────────────────────────────────────────────────

def ai_step(st: dict) -> dict | None:
    """Führt den nächsten KI-Zug aus und liefert ein Event für die Anzeige."""
    # 1) KI wählt einen Clue
    if st['status'] == 'select' and st['control'] == 'a':
        unused = [(ci, vi)
                  for ci, col in enumerate(st['board'])
                  for vi, c in enumerate(col['cells']) if not c['used']]
        if not unused:
            _start_final(st)
            return {'type': 'final_start'}
        ci, vi = random.choice(unused)
        cell_id = f'{ci}-{vi}'
        _open_cell(st, cell_id)
        clue = st['clues'][cell_id]
        return {'type': 'pick', 'who': 'a', 'cat': clue['cat'],
                'value': clue['value'], 'dd': st.get('_dd', False)}

    # 2) KI beantwortet (sie hat gebuzzert oder bekommt eine Rebuttal)
    if st['status'] == 'answer' and st['turn'] == 'a':
        clue = st['clues'][st['current']]
        value = _wager_or_value(st)
        if st.get('_dd'):                      # Daily Double der KI: erst Einsatz
            st['_wager'] = _ki_dd_wager(st)
            value = st['_wager']
        confident = not st['rebuttal']
        correct = _ki_answers_correctly(st, confident)
        if correct:
            _award(st, 'a', value)
            _to_reveal(st, 'a', st.get('_player_picked'))
            return {'type': 'answer', 'who': 'a', 'correct': True,
                    'value': value, 'wager': st.get('_wager')}
        _award(st, 'a', -value)
        if not st.get('_dd') and not st['rebuttal']:
            # KI hatte zuerst gebuzzert und lag falsch → Spieler-Rebuttal
            st['turn'] = 'p'
            st['rebuttal'] = True
            return {'type': 'answer', 'who': 'a', 'correct': False,
                    'value': value, 'rebuttal_to': 'p'}
        _to_reveal(st, None, st.get('_player_picked'))
        return {'type': 'answer', 'who': 'a', 'correct': False, 'value': value}

    # 3) Final Jeopardy: KI-Einsatz ist Teil von _resolve_final → hier nichts.
    return None


def _ki_dd_wager(st: dict) -> int:
    a = st['scores']['a']
    base = st['clues'][st['current']]['value']
    return int(_clamp(max(base, a if a > 0 else base), 5, max(base, a, 1000)))


# ── Eingabe-Säuberung ───────────────────────────────────────────────────────

def _clamp_int(raw, lo: int, hi: int) -> int:
    try:
        return int(_clamp(int(raw), lo, hi))
    except (TypeError, ValueError):
        return lo


def _clean_wager(raw, score: int) -> int:
    cap = max(1000, score)
    try:
        return int(_clamp(int(raw), 0 if score <= 0 else 5, cap))
    except (TypeError, ValueError):
        return 0


# ── Öffentliche Sicht (ohne Lösungen) ───────────────────────────────────────

def public_view(st: dict) -> dict:
    """Entfernt alle geheimen Felder (Lösungen, KI-Buzzerzeit)."""
    board = [{'cat': col['cat'], 'label_de': col['label_de'],
              'label_en': col['label_en'],
              'cells': [{'value': c['value'], 'used': c['used']} for c in col['cells']]}
             for col in st['board']]
    out = {
        'status': st['status'],
        'level': st['level'],
        'board': board,
        'scores': dict(st['scores']),
        'control': st['control'],
        'turn': st.get('turn'),
        'remaining': _count_unused(st),
        'buzz_window_ms': BUZZ_WINDOW_MS,
        'winner': st.get('winner'),
    }
    # Aktiver Clue (ohne Lösung), inkl. Daily-Double-Flag
    if st.get('active') and st['status'] in ('clue', 'answer', 'daily_double'):
        a = dict(st['active'])
        a['dd'] = st.get('_dd', False)
        a['rebuttal'] = st.get('rebuttal', False)
        out['active'] = a
        if st['status'] == 'daily_double':
            out['wager_cap'] = max(1000, st['scores']['p'])
    if st.get('last_result') is not None and st['status'] == 'reveal':
        out['result'] = st['last_result']
    if st.get('final') is not None:
        fin = st['final']
        f_out = {'label_de': fin['clue']['label_de'], 'label_en': fin['clue']['label_en']}
        if st['status'] == 'final_wager':
            f_out['wager_cap'] = max(0, st['scores']['p'])
        if st['status'] in ('final_answer',):
            f_out['q_de'] = fin['clue']['q_de']
            f_out['q_en'] = fin['clue']['q_en']
            f_out['opts_de'] = fin['clue']['opts_de']
            f_out['opts_en'] = fin['clue']['opts_en']
            f_out['wager_p'] = fin['wager_p']
        if st['status'] == 'game_over':
            f_out.update({'q_de': fin['clue']['q_de'], 'q_en': fin['clue']['q_en'],
                          'opts_de': fin['clue']['opts_de'], 'opts_en': fin['clue']['opts_en'],
                          'correct': fin['clue']['c'], 'picked_p': fin.get('picked_p'),
                          'wager_p': fin.get('wager_p'), 'wager_a': fin.get('wager_a'),
                          'ki_correct': fin.get('ki_correct')})
        out['final'] = f_out
    return out
