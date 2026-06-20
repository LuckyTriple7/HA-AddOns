"""Mau Mau — Kartenspiel für 3 Spieler (1 Mensch + 2 KI).

Regeln:
- 32 Karten (Französisches Blatt, 7 bis Ass)
- 3 Spieler, jeder startet mit 5 Karten
- Karte spielen die zu Farbe ODER Rang der Ablage passt
- Kann nicht spielen → 1 Karte ziehen (sofort spielbar wenn passend)
- Sonderkarten: 7 (ziehe 2, stapelbar), 8 (aussetzen), Bube (Farbwunsch), Ass (Richtungswechsel)
- Erste leere Hand gewinnt die Runde
- Match: Erster mit X Rundensiegen gewinnt
"""
from __future__ import annotations

import copy
import random

SUITS = ('h', 'd', 's', 'c')
RANKS = ('7', '8', '9', 'T', 'J', 'Q', 'K', 'A')
RANK_VAL = {r: i for i, r in enumerate(RANKS)}
PLAYERS = ('p', 'a1', 'a2')
SUIT_SYM = {'h': '♥', 'd': '♦', 's': '♠', 'c': '♣'}
SUIT_NAME = {'h': 'Herz', 'd': 'Karo', 's': 'Pik', 'c': 'Kreuz'}
RANK_NAME = {'7': '7', '8': '8', '9': '9', 'T': '10',
             'J': 'Bube', 'Q': 'Dame', 'K': 'König', 'A': 'Ass'}
CARD_POINTS = {'7': 7, '8': 8, '9': 9, 'T': 10, 'J': 20, 'Q': 10, 'K': 10, 'A': 11}


class IllegalMove(Exception):
    pass


def suit(c: str) -> str:
    return c[0]


def rank(c: str) -> str:
    return c[1]


def rval(c: str) -> int:
    return RANK_VAL[c[1]]


def card_name(c: str) -> str:
    return f'{RANK_NAME[rank(c)]} {SUIT_SYM[suit(c)]}'


def card_points(c: str) -> int:
    return CARD_POINTS[rank(c)]


def full_deck() -> list[str]:
    return [s + r for s in SUITS for r in RANKS]


def _next_player(current: str, direction: int, skip: bool = False) -> str:
    idx = PLAYERS.index(current)
    step = direction * (2 if skip else 1)
    return PLAYERS[(idx + step) % 3]


# ── Spiel erstellen ──────────────────────────────────────────────

def new_game(level: str = 'medium', wins_target: int = 3,
             seed: int | None = None) -> dict:
    if seed is None:
        seed = random.randint(0, 2**31)
    rng = random.Random(seed * 31)
    starter = PLAYERS[rng.randint(0, 2)]
    state = {
        'level': level,
        'wins_target': wins_target,
        'wins': {'p': 0, 'a1': 0, 'a2': 0},
        'round_nr': 0,
        'starter': starter,
        'seed': seed,
        'status': 'playing',
        'hands': {}, 'discard': [], 'draw_pile': [],
        'direction': 1, 'turn': None,
        'draw_pending': 0, 'wished_suit': None,
        'round_result': None, 'last_play': None,
        'can_play_drawn': None,
    }
    deal_round(state)
    return state


def deal_round(state: dict) -> None:
    state['round_nr'] += 1
    rng = random.Random(state['seed'] + state['round_nr'] * 997)
    deck = full_deck()
    rng.shuffle(deck)

    state['hands'] = {p: sorted(deck[i*5:(i+1)*5], key=lambda c: (SUITS.index(suit(c)), rval(c)))
                      for i, p in enumerate(PLAYERS)}
    remaining = deck[15:]

    first_card = None
    for i, c in enumerate(remaining):
        if rank(c) != 'J':
            first_card = remaining.pop(i)
            break
    if first_card is None:
        first_card = remaining.pop(0)

    state['discard'] = [first_card]
    state['draw_pile'] = remaining
    state['direction'] = 1
    state['turn'] = state['starter']
    state['draw_pending'] = 0
    state['wished_suit'] = None
    state['round_result'] = None
    state['last_play'] = None
    state['can_play_drawn'] = None
    state['status'] = 'playing'

    if rank(first_card) == '7':
        state['draw_pending'] = 2
    elif rank(first_card) == '8':
        state['turn'] = _next_player(state['starter'], state['direction'])
    elif rank(first_card) == 'A':
        state['direction'] = -1


# ── Legale Karten ────────────────────────────────────────────────

def legal_cards(state: dict, player: str) -> list[str]:
    hand = state['hands'][player]
    top = state['discard'][-1]
    wished = state['wished_suit']
    pending = state['draw_pending']

    legal = []
    for c in hand:
        if pending > 0:
            if rank(c) == '7':
                legal.append(c)
        elif rank(c) == 'J':
            legal.append(c)
        elif wished:
            if suit(c) == wished or rank(c) == 'J':
                legal.append(c)
        else:
            if suit(c) == suit(top) or rank(c) == rank(top):
                legal.append(c)
    return legal


def _can_play_card(state: dict, card: str) -> bool:
    top = state['discard'][-1]
    wished = state['wished_suit']
    pending = state['draw_pending']

    if pending > 0:
        return rank(card) == '7'
    if rank(card) == 'J':
        return True
    if wished:
        return suit(card) == wished
    return suit(card) == suit(top) or rank(card) == rank(top)


# ── Nachziehstapel auffüllen ─────────────────────────────────────

def _refill_draw_pile(state: dict) -> None:
    if state['draw_pile']:
        return
    if len(state['discard']) <= 1:
        return
    top = state['discard'][-1]
    reshuffled = state['discard'][:-1]
    rng = random.Random(state['seed'] + state['round_nr'] * 113 + len(reshuffled))
    rng.shuffle(reshuffled)
    state['draw_pile'] = reshuffled
    state['discard'] = [top]


def _draw_cards(state: dict, player: str, count: int) -> list[str]:
    drawn = []
    for _ in range(count):
        _refill_draw_pile(state)
        if not state['draw_pile']:
            break
        card = state['draw_pile'].pop()
        state['hands'][player].append(card)
        drawn.append(card)
    state['hands'][player].sort(key=lambda c: (SUITS.index(suit(c)), rval(c)))
    return drawn


# ── Züge anwenden ────────────────────────────────────────────────

def apply_action(state: dict, player: str, action: dict) -> list:
    t = action.get('type', '')
    if t == 'play':
        return _apply_play(state, player, action.get('card', ''))
    if t == 'draw':
        return _apply_draw(state, player)
    if t == 'play_drawn':
        return _apply_play_drawn(state, player)
    if t == 'pass_drawn':
        return _apply_pass_drawn(state, player)
    if t == 'wish':
        return _apply_wish(state, player, action.get('suit', ''))
    if t == 'next_round':
        return _apply_next_round(state)
    if t == 'new_game':
        return _apply_new_game(state, action)
    raise IllegalMove(f'Unbekannter Aktionstyp: {t}')


def _apply_play(state: dict, player: str, card: str) -> list:
    if state['status'] != 'playing':
        raise IllegalMove('Nicht im Spielstatus')
    if state['turn'] != player:
        raise IllegalMove('Nicht dein Zug')
    if card not in state['hands'][player]:
        raise IllegalMove('Karte nicht auf der Hand')
    if card not in legal_cards(state, player):
        raise IllegalMove('Karte nicht spielbar')

    state['hands'][player].remove(card)
    state['discard'].append(card)
    state['last_play'] = {'who': player, 'card': card, 'type': 'play'}
    state['wished_suit'] = None

    if not state['hands'][player]:
        _end_round(state, player)
        return []

    if rank(card) == 'J':
        state['status'] = 'wish_suit'
        return []

    skip = False
    if rank(card) == '7':
        state['draw_pending'] += 2
    elif rank(card) == '8':
        skip = True
    elif rank(card) == 'A':
        state['direction'] *= -1

    state['turn'] = _next_player(player, state['direction'], skip=skip)
    return []


def _apply_draw(state: dict, player: str) -> list:
    if state['status'] != 'playing':
        raise IllegalMove('Nicht im Spielstatus')
    if state['turn'] != player:
        raise IllegalMove('Nicht dein Zug')

    if state['draw_pending'] > 0:
        count = state['draw_pending']
        drawn = _draw_cards(state, player, count)
        state['draw_pending'] = 0
        state['last_play'] = {'who': player, 'type': 'draw', 'count': len(drawn)}
        state['turn'] = _next_player(player, state['direction'])
        return []

    drawn = _draw_cards(state, player, 1)
    if not drawn:
        state['last_play'] = {'who': player, 'type': 'pass'}
        state['turn'] = _next_player(player, state['direction'])
        return []

    drawn_card = drawn[0]
    if _can_play_card(state, drawn_card):
        state['can_play_drawn'] = drawn_card
        state['status'] = 'drawn'
        state['last_play'] = {'who': player, 'type': 'draw', 'count': 1,
                              'can_play': True, 'drawn_card': drawn_card}
    else:
        state['last_play'] = {'who': player, 'type': 'draw', 'count': 1}
        state['turn'] = _next_player(player, state['direction'])
    return []


def _apply_play_drawn(state: dict, player: str) -> list:
    if state['status'] != 'drawn':
        raise IllegalMove('Nicht im Drawn-Status')
    if state['turn'] != player:
        raise IllegalMove('Nicht dein Zug')

    card = state['can_play_drawn']
    if not card or card not in state['hands'][player]:
        raise IllegalMove('Gezogene Karte nicht spielbar')

    state['hands'][player].remove(card)
    state['discard'].append(card)
    state['can_play_drawn'] = None
    state['status'] = 'playing'
    state['last_play'] = {'who': player, 'card': card, 'type': 'play_drawn'}

    if not state['hands'][player]:
        _end_round(state, player)
        return []

    if rank(card) == 'J':
        state['status'] = 'wish_suit'
        return []

    skip = False
    if rank(card) == '7':
        state['draw_pending'] += 2
    elif rank(card) == '8':
        skip = True
    elif rank(card) == 'A':
        state['direction'] *= -1

    state['turn'] = _next_player(player, state['direction'], skip=skip)
    return []


def _apply_pass_drawn(state: dict, player: str) -> list:
    if state['status'] != 'drawn':
        raise IllegalMove('Nicht im Drawn-Status')
    if state['turn'] != player:
        raise IllegalMove('Nicht dein Zug')

    state['can_play_drawn'] = None
    state['status'] = 'playing'
    state['last_play'] = {'who': player, 'type': 'pass_drawn'}
    state['turn'] = _next_player(player, state['direction'])
    return []


def _apply_wish(state: dict, player: str, wished: str) -> list:
    if state['status'] != 'wish_suit':
        raise IllegalMove('Nicht im Wunsch-Status')
    if state['turn'] != player:
        raise IllegalMove('Nicht dein Zug')
    if wished not in SUITS:
        raise IllegalMove(f'Ungültige Farbe: {wished}')

    state['wished_suit'] = wished
    state['status'] = 'playing'
    state['last_play'] = {'who': player, 'type': 'wish', 'suit': wished}
    state['turn'] = _next_player(player, state['direction'])
    return []


def _apply_next_round(state: dict) -> list:
    if state['status'] not in ('round_over', 'game_over'):
        raise IllegalMove('Runde nicht beendet')
    if state['status'] == 'game_over':
        return []
    state['starter'] = _next_player(state['starter'], 1)
    deal_round(state)
    return []


def _apply_new_game(state: dict, action: dict) -> list:
    level = action.get('level', state['level'])
    wins_target = action.get('wins_target', state.get('wins_target', 3))
    new = new_game(level=level, wins_target=wins_target)
    state.clear()
    state.update(new)
    return []


# ── Rundenende ───────────────────────────────────────────────────

def _end_round(state: dict, winner: str) -> None:
    result = {
        'winner': winner,
        'hands': {p: list(state['hands'][p]) for p in PLAYERS},
        'points': {},
    }
    for p in PLAYERS:
        pts = sum(card_points(c) for c in state['hands'][p])
        result['points'][p] = pts

    state['wins'][winner] += 1
    state['round_result'] = result

    if state['wins'][winner] >= state['wins_target']:
        state['status'] = 'game_over'
        state['winner'] = winner
    else:
        state['status'] = 'round_over'


# ── Öffentliche Sicht ───────────────────────────────────────────

def public_view(state: dict) -> dict:
    v = copy.deepcopy(state)

    for ai in ('a1', 'a2'):
        if isinstance(v['hands'].get(ai), list):
            v['hands'][ai] = len(v['hands'][ai])

    v['draw_count'] = len(v.get('draw_pile', []))
    v.pop('draw_pile', None)
    v.pop('seed', None)

    if v.get('can_play_drawn') and v['turn'] != 'p':
        v['can_play_drawn'] = True

    if v['status'] == 'playing' and v['turn'] == 'p':
        v['legal'] = legal_cards(state, 'p')
        v['can_draw'] = True
    elif v['status'] == 'drawn' and v['turn'] == 'p':
        v['legal'] = [state['can_play_drawn']] if state.get('can_play_drawn') else []
    elif v['status'] == 'wish_suit' and v['turn'] == 'p':
        v['legal'] = []

    return v


# ── KI ───────────────────────────────────────────────────────────

_LEVEL_STR = {'easy': 30, 'medium': 60, 'hard': 100}
_CAPS = {
    'smart_play': 40,
    'save_jacks': 45,
    'stack_sevens': 45,
    'suit_preference': 50,
    'score_aware': 55,
    'count_cards': 70,
    'opponent_aware': 75,
    'endgame': 80,
}


def _caps(level: str) -> dict:
    strength = _LEVEL_STR.get(level, 60)
    return {k: strength >= v for k, v in _CAPS.items()}


def ai_play(state: dict, who: str) -> dict:
    caps = _caps(state['level'])
    hand = state['hands'][who]
    legal = legal_cards(state, who)

    if state['draw_pending'] > 0:
        if legal:
            if caps['stack_sevens']:
                return {'type': 'play', 'card': legal[0]}
            return {'type': 'play', 'card': random.choice(legal)}
        return {'type': 'draw'}

    if not legal:
        return {'type': 'draw'}

    if not caps['smart_play']:
        return {'type': 'play', 'card': random.choice(legal)}

    non_jack = [c for c in legal if rank(c) != 'J']
    jacks = [c for c in legal if rank(c) == 'J']

    if caps['opponent_aware']:
        opp_min = min(len(state['hands'][p]) for p in PLAYERS if p != who)
        if opp_min <= 2:
            specials = [c for c in legal if rank(c) in ('7', '8')]
            if specials:
                return {'type': 'play', 'card': specials[0]}

    if caps['endgame'] and len(hand) <= 3:
        for c in legal:
            if rank(c) != 'J':
                return {'type': 'play', 'card': c}

    if non_jack:
        if caps['suit_preference']:
            suit_counts = {}
            for c in hand:
                s = suit(c)
                suit_counts[s] = suit_counts.get(s, 0) + 1

            special_priority = []
            normal = []
            for c in non_jack:
                if rank(c) in ('7', '8', 'A'):
                    special_priority.append(c)
                else:
                    normal.append(c)

            if normal:
                best = max(normal, key=lambda c: suit_counts.get(suit(c), 0))
                return {'type': 'play', 'card': best}
            if special_priority:
                return {'type': 'play', 'card': special_priority[0]}
        else:
            return {'type': 'play', 'card': non_jack[0]}

    if jacks and caps['save_jacks'] and len(hand) > 2:
        return {'type': 'draw'}

    if jacks:
        return {'type': 'play', 'card': jacks[0]}

    return {'type': 'draw'}


def ai_play_drawn(state: dict, who: str) -> dict:
    return {'type': 'play_drawn'}


def ai_wish(state: dict, who: str) -> dict:
    caps = _caps(state['level'])
    hand = state['hands'][who]

    if not caps['suit_preference']:
        suits = [suit(c) for c in hand if rank(c) != 'J']
        if suits:
            return {'type': 'wish', 'suit': random.choice(suits)}
        return {'type': 'wish', 'suit': random.choice(SUITS)}

    suit_counts = {}
    for c in hand:
        if rank(c) != 'J':
            s = suit(c)
            suit_counts[s] = suit_counts.get(s, 0) + 1

    if suit_counts:
        best = max(suit_counts, key=suit_counts.get)
        return {'type': 'wish', 'suit': best}
    return {'type': 'wish', 'suit': random.choice(SUITS)}


def ai_step(state: dict, who: str) -> dict:
    if state['status'] == 'playing':
        return ai_play(state, who)
    if state['status'] == 'drawn':
        return ai_play_drawn(state, who)
    if state['status'] == 'wish_suit':
        return ai_wish(state, who)
    return {}
