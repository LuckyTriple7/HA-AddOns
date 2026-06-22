"""Kniffel — Würfelspiel für 1 Mensch + 1–2 KI.

Server-autoritativer Zustand wie die Kartenspiele (66/20AB): der Server würfelt,
der Client ruft KI-Schritte einzeln ab (animationsgetrieben). Offizielle Regeln
inkl. 63er-Bonus (+35), Kniffel (50) und Kniffel-Bonus (+100, mit Joker).
"""
from __future__ import annotations

import random

import game_dice

CATS = ['ones', 'twos', 'threes', 'fours', 'fives', 'sixes',
        'three_kind', 'four_kind', 'full_house', 'small_straight',
        'large_straight', 'kniffel', 'chance']
UPPER = ['ones', 'twos', 'threes', 'fours', 'fives', 'sixes']
JOKER_FIXED = {'full_house': 25, 'small_straight': 30, 'large_straight': 40}


class IllegalMove(Exception):
    pass


# ── Wertung ──────────────────────────────────────────────────────────────────

def score(cat: str, dice: list[int], joker: bool = False) -> int:
    c = game_dice.counts(dice)
    total = sum(dice)
    if cat in UPPER:
        v = UPPER.index(cat) + 1
        return c[v] * v
    if cat == 'three_kind':
        return total if any(n >= 3 for n in c) else 0
    if cat == 'four_kind':
        return total if any(n >= 4 for n in c) else 0
    if cat == 'full_house':
        if joker:
            return 25
        return 25 if (3 in c and 2 in c) or (5 in c) else 0
    if cat == 'small_straight':
        return 30 if joker or game_dice.has_straight(dice, 4) else 0
    if cat == 'large_straight':
        return 40 if joker or game_dice.has_straight(dice, 5) else 0
    if cat == 'kniffel':
        return 50 if any(n >= 5 for n in c) else 0
    if cat == 'chance':
        return total
    return 0


def _is_kniffel(dice: list[int]) -> bool:
    return any(n >= 5 for n in game_dice.counts(dice))


def upper_sum(sheet: dict) -> int:
    return sum(sheet.get(c, 0) for c in UPPER)


def upper_bonus(sheet: dict) -> int:
    return 35 if upper_sum(sheet) >= 63 else 0


def total_score(state: dict, who: str) -> int:
    sheet = state['sheets'][who]
    base = sum(sheet.get(c, 0) for c in CATS)
    return base + upper_bonus(sheet) + state['kbonus'].get(who, 0)


# ── Spiel erstellen ──────────────────────────────────────────────────────────

def new_game(level: str = 'medium', opponents: int = 2, seed: int | None = None) -> dict:
    if seed is None:
        seed = random.randint(0, 2 ** 31)
    if opponents not in (1, 2):
        opponents = 2
    if level not in ('easy', 'medium', 'hard'):
        level = 'medium'
    players = ['p', 'a1'] + (['a2'] if opponents == 2 else [])
    return {
        'status': 'playing',
        'level': level,
        'opponents': opponents,
        'seed': seed,
        'roll_step': 0,
        'players': players,
        'turn': 'p',
        'dice': [0, 0, 0, 0, 0],     # 0 = noch nicht geworfen
        'held': [False] * 5,
        'rolls_left': 3,
        'rolled': False,
        'sheets': {p: {} for p in players},
        'kbonus': {p: 0 for p in players},   # Kniffel-Bonus (+100 je Zusatz-Kniffel)
        'winner': None,
        'last': None,                # Info für Animation/Anzeige
    }


# ── Züge anwenden ────────────────────────────────────────────────────────────

def apply_action(state: dict, player: str, action: dict) -> None:
    if state['status'] != 'playing':
        raise IllegalMove('game over')
    t = action.get('type', '')
    if t == 'roll':
        _do_roll(state, player, action.get('held'))
    elif t == 'hold':
        _do_hold(state, player, action.get('held'))
    elif t == 'score':
        _do_score(state, player, action.get('cat'))
    else:
        raise IllegalMove('unknown action')


def _do_roll(state: dict, player: str, held=None) -> None:
    if state['turn'] != player or state['rolls_left'] <= 0:
        raise IllegalMove('cannot roll')
    if state['rolled'] and isinstance(held, list) and len(held) == 5:
        state['held'] = [bool(x) for x in held]
    mask = state['held'] if state['rolled'] else [False] * 5
    state['roll_step'] += 1
    fresh = game_dice.roll(5, state['seed'], state['roll_step'])
    dice = state['dice'][:]
    for i in range(5):
        if not (state['rolled'] and mask[i]):
            dice[i] = fresh[i]
    state['dice'] = dice
    state['rolled'] = True
    state['rolls_left'] -= 1
    state['last'] = {'type': 'roll', 'who': player, 'dice': dice[:], 'held': mask[:]}


def _do_hold(state: dict, player: str, held) -> None:
    if state['turn'] != player or not state['rolled'] or state['rolls_left'] <= 0:
        raise IllegalMove('cannot hold')
    if not isinstance(held, list) or len(held) != 5:
        raise IllegalMove('bad held')
    state['held'] = [bool(x) for x in held]


def _do_score(state: dict, player: str, cat: str) -> None:
    if state['turn'] != player or not state['rolled']:
        raise IllegalMove('cannot score')
    if cat not in CATS or cat in state['sheets'][player]:
        raise IllegalMove('bad category')
    joker = _is_kniffel(state['dice']) and state['sheets'][player].get('kniffel') == 50
    val = score(cat, state['dice'], joker=(joker and cat in JOKER_FIXED))
    if joker:
        state['kbonus'][player] = state['kbonus'].get(player, 0) + 100
    state['sheets'][player][cat] = val
    state['last'] = {'type': 'score', 'who': player, 'cat': cat, 'value': val,
                     'joker_bonus': 100 if joker else 0}
    _advance(state, player)


def _advance(state: dict, player: str) -> None:
    players = state['players']
    nxt = players[(players.index(player) + 1) % len(players)]
    state['dice'] = [0, 0, 0, 0, 0]
    state['held'] = [False] * 5
    state['rolls_left'] = 3
    state['rolled'] = False
    state['turn'] = nxt
    if all(len(state['sheets'][p]) >= len(CATS) for p in players):
        state['status'] = 'game_over'
        state['turn'] = None
        totals = {p: total_score(state, p) for p in players}
        best = max(totals.values())
        winners = [p for p in players if totals[p] == best]
        state['winner'] = 'p' if 'p' in winners else winners[0]


# ── KI (ein Teilschritt pro Aufruf, wie 20AB) ────────────────────────────────

def ai_step(state: dict) -> dict:
    """Liefert die nächste KI-Teilaktion für den aktuellen KI-Spieler."""
    who = state['turn']
    sheet = state['sheets'][who]
    if not state['rolled']:
        return {'type': 'roll'}
    if state['rolls_left'] > 0 and _ai_wants_roll(state):
        return {'type': 'roll', 'held': _ai_holds(state['dice'], sheet, state['level'])}
    return {'type': 'score', 'cat': _ai_category(state['dice'], sheet, state['level'])}


def _ai_wants_roll(state: dict) -> bool:
    if state['rolls_left'] <= 0:
        return False
    dice = state['dice']
    c = game_dice.counts(dice)
    if any(n >= 5 for n in c):                 # Kniffel — stehen lassen
        return False
    if game_dice.has_straight(dice, 5):        # große Straße
        return False
    if 3 in c and 2 in c:                       # Full House
        return False
    if state['level'] == 'easy':
        return random.random() < 0.6           # hört oft (zu) früh auf → schwächer
    return True


def _ai_holds(dice: list[int], sheet: dict, level: str) -> list[bool]:
    c = game_dice.counts(dice)
    # Easy: würfelt meist alles neu (kein Plan) → schwächer
    if level == 'easy':
        best = max((v for v in range(1, 7) if c[v] >= 2), default=0)
        return [d == best for d in dice] if (best and random.random() < 0.5) else [False] * 5

    # Straßen-Ansatz (mittel/schwer): vorhandene Folge behalten
    for run in ([1, 2, 3, 4, 5], [2, 3, 4, 5, 6], [1, 2, 3, 4], [2, 3, 4, 5], [3, 4, 5, 6]):
        if all(x in dice for x in run):
            keep, seen = [False] * 5, set()
            for i, d in enumerate(dice):
                if d in run and d not in seen:
                    keep[i] = True
                    seen.add(d)
            if sum(keep) >= 4:
                return keep

    # größte Gruppe behalten (bei Gleichstand höherer Wert)
    best = None
    for v in range(6, 0, -1):
        if c[v] >= 2 and (best is None or c[v] > c[best]):
            best = v
    keep = [False] * 5
    if best:
        keep = [d == best for d in dice]
    elif level == 'hard':
        # keine Gruppe: höchsten Würfel als Anker behalten (Richtung Oberteil/Kombi)
        mx = max(dice)
        anchored = False
        for i, d in enumerate(dice):
            if d == mx and not anchored:
                keep[i] = True
                anchored = True
    else:  # medium
        keep = [d >= 5 for d in dice]
    return keep


# typischer „voller" Wert je Kategorie — für die wertorientierte KI (schwer)
MAXVAL = {'ones': 5, 'twos': 10, 'threes': 15, 'fours': 20, 'fives': 25, 'sixes': 30,
          'three_kind': 22, 'four_kind': 26, 'full_house': 25, 'small_straight': 30,
          'large_straight': 40, 'kniffel': 50, 'chance': 25}


def _ai_category(dice: list[int], sheet: dict, level: str) -> str:
    open_cats = [c for c in CATS if c not in sheet]
    joker = _is_kniffel(dice) and sheet.get('kniffel') == 50
    sc = {c: score(c, dice, joker=(joker and c in JOKER_FIXED)) for c in open_cats}
    best = max(sc.values())

    if level == 'hard':
        # Sofortpunkte minus „verschenktem Potenzial" (so bleiben Premium-Felder frei,
        # bis sie wirklich getroffen werden). Nullen landen im günstigsten Feld.
        nonzero = [c for c in open_cats if sc[c] > 0]
        pool = nonzero if nonzero else open_cats
        def rank(c):
            return sc[c] - 0.35 * (MAXVAL[c] - sc[c])
        return sorted(pool, key=lambda c: (-rank(c), CATS.index(c)))[0]

    if level == 'easy' or best > 0:
        # höchster Sofortwert; bei Gleichstand festes Kategorie-Ranking
        return sorted(open_cats, key=lambda c: (-sc[c], CATS.index(c)))[0]

    # alles 0 → möglichst verlustarm streichen
    scratch_pref = ['ones', 'twos', 'three_kind', 'four_kind', 'kniffel',
                    'small_straight', 'large_straight', 'full_house', 'chance',
                    'threes', 'fours', 'fives', 'sixes']
    for c in scratch_pref:
        if c in open_cats:
            return c
    return open_cats[0]


# ── Sicht für den Client ─────────────────────────────────────────────────────

def public_view(state: dict) -> dict:
    players = state['players']
    return {
        'status': state['status'],
        'level': state['level'],
        'opponents': state['opponents'],
        'players': players,
        'turn': state['turn'],
        'dice': state['dice'],
        'held': state['held'],
        'rolls_left': state['rolls_left'],
        'rolled': state['rolled'],
        'sheets': state['sheets'],
        'kbonus': state['kbonus'],
        'totals': {p: total_score(state, p) for p in players},
        'upper_sum': {p: upper_sum(state['sheets'][p]) for p in players},
        'upper_bonus': {p: upper_bonus(state['sheets'][p]) for p in players},
        'winner': state['winner'],
        'last': state.get('last'),
    }
