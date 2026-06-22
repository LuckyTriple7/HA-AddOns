"""Präsident — Kartenspiel für 3 Spieler (1 Mensch + 2 KI).

Regeln:
- 32 Karten (Französisches Blatt, 7 bis Ass)
- 3 Spieler, jeder bekommt 10 Karten (2 in den Talon)
- Karten ablegen: 1–4 Karten gleichen Rangs
- Nächster muss gleiche Anzahl mit höherem Rang spielen oder passen
- Wer passt ist für den Stich raus
- Erster ohne Karten = Präsident, Zweiter = Bürger, Letzter = Bettler
- Ab Runde 2: Kartentausch (Bettler gibt 2 beste an Präsident)
- Revolution: 4 gleiche kehren Rangfolge um
- Match: Erster mit X Siegen als Präsident gewinnt
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

ROLE_PRAESIDENT = 'praesident'
ROLE_BUERGER = 'buerger'
ROLE_BETTLER = 'bettler'
ROLE_ORDER = (ROLE_PRAESIDENT, ROLE_BUERGER, ROLE_BETTLER)


class IllegalMove(Exception):
    pass


def suit(c: str) -> str:
    return c[0]


def rank(c: str) -> str:
    return c[1]


def rval(c: str) -> int:
    return RANK_VAL[c[1]]


def rank_val(r: str) -> int:
    return RANK_VAL[r]


def card_name(c: str) -> str:
    return f'{RANK_NAME[rank(c)]} {SUIT_SYM[suit(c)]}'


def full_deck() -> list[str]:
    return [s + r for s in SUITS for r in RANKS]


def _sort_hand(hand: list[str]) -> None:
    hand.sort(key=lambda c: (rval(c), SUITS.index(suit(c))))


def _group_by_rank(hand: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for c in hand:
        r = rank(c)
        groups.setdefault(r, []).append(c)
    return groups


def _rank_beats(rank_a: str, rank_b: str, revolution: bool = False) -> bool:
    if revolution:
        return RANK_VAL[rank_a] < RANK_VAL[rank_b]
    return RANK_VAL[rank_a] > RANK_VAL[rank_b]


def _two_highest_cards(hand: list[str], revolution: bool = False) -> list[str]:
    if revolution:
        s = sorted(hand, key=lambda c: rval(c))
    else:
        s = sorted(hand, key=lambda c: -rval(c))
    return s[:2]


# ── Spiel erstellen ──────────────────────────────────────────────

def new_game(level: str = 'medium', wins_target: int = 3,
             seed: int | None = None) -> dict:
    if seed is None:
        seed = random.randint(0, 2**31)
    state = {
        'level': level,
        'wins_target': wins_target,
        'wins': {'p': 0, 'a1': 0, 'a2': 0},
        'round_nr': 0,
        'seed': seed,
        'status': 'dealing',
        'hands': {},
        'talon': [],
        'trick_cards': [],
        'trick_rank': None,
        'trick_count': 0,
        'passed': [],
        'finished': [],
        'roles': {},
        'revolution': False,
        'turn': None,
        'round_result': None,
        'last_play': None,
        'winner': None,
        'swap_giving': None,
        'swap_receiving': None,
    }
    deal_round(state)
    return state


def deal_round(state: dict) -> None:
    state['round_nr'] += 1
    rng = random.Random(state['seed'] + state['round_nr'] * 997)
    deck = full_deck()
    rng.shuffle(deck)

    state['hands'] = {p: deck[i*10:(i+1)*10] for i, p in enumerate(PLAYERS)}
    for p in PLAYERS:
        _sort_hand(state['hands'][p])
    state['talon'] = deck[30:]

    state['trick_cards'] = []
    state['trick_rank'] = None
    state['trick_count'] = 0
    state['passed'] = []
    state['finished'] = []
    state['revolution'] = False
    state['round_result'] = None
    state['last_play'] = None
    state['winner'] = state.get('winner')
    state['swap_giving'] = None
    state['swap_receiving'] = None

    if state['round_nr'] == 1 or not state.get('roles'):
        starter = _find_kreuz7_holder(state)
        state['turn'] = starter
        state['status'] = 'playing'
    else:
        state['status'] = 'swap_show'
        bettler = _role_player(state, ROLE_BETTLER)
        praesident = _role_player(state, ROLE_PRAESIDENT)
        state['swap_giving'] = bettler
        state['swap_receiving'] = praesident


def _find_kreuz7_holder(state: dict) -> str:
    for p in PLAYERS:
        if 'c7' in state['hands'][p]:
            return p
    return PLAYERS[0]


def _role_player(state: dict, role: str) -> str | None:
    for p, r in state['roles'].items():
        if r == role:
            return p
    return None


# ── Legale Züge ─────────────────────────────────────────────────

def legal_plays(state: dict, player: str) -> list[list[str]]:
    hand = state['hands'][player]
    groups = _group_by_rank(hand)
    trick_count = state['trick_count']
    trick_rank = state['trick_rank']
    revolution = state['revolution']
    plays: list[list[str]] = []

    if trick_rank is None:
        for r, cards in groups.items():
            for count in range(1, len(cards) + 1):
                plays.append(cards[:count])
    else:
        for r, cards in groups.items():
            if len(cards) >= trick_count and _rank_beats(r, trick_rank, revolution):
                plays.append(cards[:trick_count])
    return plays


def can_pass(state: dict) -> bool:
    return state['trick_rank'] is not None


# ── Züge anwenden ────────────────────────────────────────────────

def apply_action(state: dict, player: str, action: dict) -> list:
    t = action.get('type', '')
    if t == 'play':
        return _apply_play(state, player, action.get('cards', []))
    if t == 'pass':
        return _apply_pass(state, player)
    if t == 'collect':
        return _apply_collect(state)
    if t == 'swap_give':
        return _apply_swap_give(state)
    if t == 'swap_choose':
        return _apply_swap_choose(state, player, action.get('cards', []))
    if t == 'next_round':
        return _apply_next_round(state)
    if t == 'new_game':
        return _apply_new_game(state, action)
    raise IllegalMove(f'Unbekannter Aktionstyp: {t}')


def _apply_play(state: dict, player: str, cards: list[str]) -> list:
    if state['status'] != 'playing':
        raise IllegalMove('Nicht im Spielstatus')
    if state['turn'] != player:
        raise IllegalMove('Nicht dein Zug')
    if not cards:
        raise IllegalMove('Keine Karten gewählt')

    hand = state['hands'][player]
    for c in cards:
        if c not in hand:
            raise IllegalMove(f'Karte {c} nicht auf der Hand')

    ranks_played = set(rank(c) for c in cards)
    if len(ranks_played) != 1:
        raise IllegalMove('Alle Karten müssen gleichen Rang haben')
    played_rank = ranks_played.pop()

    if state['trick_rank'] is not None:
        if len(cards) != state['trick_count']:
            raise IllegalMove(f'Genau {state["trick_count"]} Karten erforderlich')
        if not _rank_beats(played_rank, state['trick_rank'], state['revolution']):
            raise IllegalMove('Muss höheren Rang spielen')
    else:
        state['trick_count'] = len(cards)

    for c in cards:
        hand.remove(c)

    state['trick_cards'].append({'who': player, 'cards': list(cards)})
    state['trick_rank'] = played_rank
    state['passed'] = []
    state['last_play'] = {'who': player, 'cards': list(cards), 'type': 'play'}

    is_revolution = len(cards) == 4
    if is_revolution:
        state['revolution'] = not state['revolution']
        state['last_play']['revolution'] = True

    if not hand:
        state['finished'].append(player)
        state['last_play']['finished'] = True
        if _check_round_end(state):
            return []

    nxt = _next_active_turn(state, player)
    if nxt is None or _check_trick_done(state, player):
        state['status'] = 'trick_done'
        state['last_play']['trick_done'] = True
    else:
        state['turn'] = nxt

    return []


def _apply_pass(state: dict, player: str) -> list:
    if state['status'] != 'playing':
        raise IllegalMove('Nicht im Spielstatus')
    if state['turn'] != player:
        raise IllegalMove('Nicht dein Zug')
    if state['trick_rank'] is None:
        raise IllegalMove('Kann nicht passen beim Eröffnen')

    state['passed'].append(player)
    state['last_play'] = {'who': player, 'type': 'pass'}

    if _check_trick_done(state, None):
        state['status'] = 'trick_done'
        state['last_play']['trick_done'] = True
    else:
        nxt = _next_active_turn(state, player)
        if nxt is None:
            state['status'] = 'trick_done'
            state['last_play']['trick_done'] = True
        else:
            state['turn'] = nxt

    return []


def _apply_collect(state: dict) -> list:
    if state['status'] != 'trick_done':
        raise IllegalMove('Stich nicht beendet')

    last_player = state['trick_cards'][-1]['who'] if state['trick_cards'] else state['turn']

    state['trick_cards'] = []
    state['trick_rank'] = None
    state['trick_count'] = 0
    state['passed'] = []

    active = [p for p in PLAYERS if p not in state['finished']]
    if len(active) <= 1:
        if active:
            state['finished'].append(active[0])
        _check_round_end(state)
        return []

    if last_player in state['finished']:
        nxt = _next_active_turn(state, last_player)
        state['turn'] = nxt if nxt else active[0]
    else:
        state['turn'] = last_player

    state['status'] = 'playing'
    state['last_play'] = {'type': 'collect', 'who': state['turn']}
    return []


def _apply_swap_give(state: dict) -> list:
    if state['status'] != 'swap_show':
        raise IllegalMove('Nicht im Tausch-Status')

    bettler = state['swap_giving']
    praesident = state['swap_receiving']
    if not bettler or not praesident:
        raise IllegalMove('Kein Tauschpartner')

    best_cards = _two_highest_cards(state['hands'][bettler], state.get('prev_revolution', False))
    for c in best_cards:
        state['hands'][bettler].remove(c)
    state['hands'][praesident].extend(best_cards)
    _sort_hand(state['hands'][praesident])

    state['status'] = 'swap_choose'
    state['last_play'] = {
        'type': 'swap_give',
        'who': bettler,
        'to': praesident,
        'cards': best_cards,
    }
    return []


def _apply_swap_choose(state: dict, player: str, cards: list[str]) -> list:
    if state['status'] != 'swap_choose':
        raise IllegalMove('Nicht im Tausch-Wahl-Status')

    praesident = state['swap_receiving']
    bettler = state['swap_giving']
    if player != praesident:
        raise IllegalMove('Nur der Präsident wählt')
    if len(cards) != 2:
        raise IllegalMove('Genau 2 Karten wählen')
    for c in cards:
        if c not in state['hands'][praesident]:
            raise IllegalMove(f'Karte {c} nicht auf der Hand')

    for c in cards:
        state['hands'][praesident].remove(c)
    state['hands'][bettler].extend(cards)
    _sort_hand(state['hands'][bettler])
    _sort_hand(state['hands'][praesident])

    state['last_play'] = {
        'type': 'swap_choose',
        'who': praesident,
        'to': bettler,
        'cards': cards,
    }

    starter = bettler
    state['turn'] = starter
    state['status'] = 'playing'
    state['swap_giving'] = None
    state['swap_receiving'] = None
    return []


def _apply_next_round(state: dict) -> list:
    if state['status'] not in ('round_over', 'game_over'):
        raise IllegalMove('Runde nicht beendet')
    if state['status'] == 'game_over':
        return []
    state['prev_revolution'] = state.get('revolution', False)
    deal_round(state)
    return []


def _apply_new_game(state: dict, action: dict) -> list:
    level = action.get('level', state['level'])
    wins_target = action.get('wins_target', state.get('wins_target', 3))
    new = new_game(level=level, wins_target=wins_target)
    state.clear()
    state.update(new)
    return []


# ── Hilfsfunktionen für Zuglogik ────────────────────────────────

def _active_players(state: dict) -> list[str]:
    return [p for p in PLAYERS if p not in state['finished']]


def _next_active_turn(state: dict, current: str) -> str | None:
    active = _active_players(state)
    if not active:
        return None
    if current not in PLAYERS:
        return active[0] if active else None
    idx = list(PLAYERS).index(current)
    for i in range(1, len(PLAYERS)):
        candidate = PLAYERS[(idx + i) % len(PLAYERS)]
        if candidate not in state['finished'] and candidate not in state['passed']:
            return candidate
    return None


def _check_trick_done(state: dict, last_actor: str | None) -> bool:
    active = _active_players(state)
    not_passed = [p for p in active if p not in state['passed']]

    if len(not_passed) <= 1:
        return True

    if state['trick_cards']:
        last_player = state['trick_cards'][-1]['who']
        if not_passed == [last_player]:
            return True

    return False


def _check_round_end(state: dict) -> bool:
    if len(state['finished']) < len(PLAYERS) - 1:
        return False

    remaining = [p for p in PLAYERS if p not in state['finished']]
    state['finished'].extend(remaining)

    state['roles'] = {}
    for i, p in enumerate(state['finished']):
        state['roles'][p] = ROLE_ORDER[i]

    praesident = state['finished'][0]
    state['wins'][praesident] += 1

    state['round_result'] = {
        'finished': list(state['finished']),
        'roles': dict(state['roles']),
        'hands': {p: list(state['hands'][p]) for p in PLAYERS},
    }

    if state['wins'][praesident] >= state['wins_target']:
        state['status'] = 'game_over'
        state['winner'] = praesident
    else:
        state['status'] = 'round_over'
    return True


# ── Öffentliche Sicht ──────────────────────────────────────────

def public_view(state: dict) -> dict:
    v = copy.deepcopy(state)

    for ai in ('a1', 'a2'):
        if isinstance(v['hands'].get(ai), list):
            v['hands'][ai] = len(v['hands'][ai])

    v.pop('seed', None)
    v.pop('talon', None)
    v.pop('prev_revolution', None)

    if v['status'] == 'playing' and v['turn'] == 'p':
        v['legal_plays'] = legal_plays(state, 'p')
        v['can_pass'] = can_pass(state)
    elif v['status'] == 'swap_choose' and v.get('swap_receiving') == 'p':
        v['must_choose'] = 2

    return v


# ── KI ──────────────────────────────────────────────────────────

_LEVEL_STR = {'easy': 30, 'medium': 60, 'hard': 100}
_CAPS = {
    'smart_play': 40,
    'save_high': 45,
    'pair_awareness': 45,
    'pass_strategy': 50,
    'count_cards': 60,
    'opponent_aware': 65,
    'endgame': 70,
    'revolution_aware': 75,
    'swap_optimize': 55,
}


def _caps(level: str) -> dict:
    strength = _LEVEL_STR.get(level, 60)
    return {k: strength >= v for k, v in _CAPS.items()}


def _rank_sort_key(r: str, revolution: bool) -> int:
    v = RANK_VAL[r]
    return -v if revolution else v


def ai_step(state: dict, who: str) -> dict:
    if state['status'] == 'swap_show':
        return {'type': 'swap_give'}
    if state['status'] == 'swap_choose':
        cards = ai_swap_choose(state, who)
        return {'type': 'swap_choose', 'cards': cards}
    if state['status'] == 'trick_done':
        return {'type': 'collect'}
    if state['status'] == 'playing':
        return ai_play(state, who)
    return {}


def ai_play(state: dict, who: str) -> dict:
    caps = _caps(state['level'])
    plays = legal_plays(state, who)
    revolution = state['revolution']

    if not plays and state['trick_rank'] is not None:
        return {'type': 'pass'}
    if not plays:
        return {'type': 'pass'}

    if not caps['smart_play']:
        play = random.choice(plays)
        if state['trick_rank'] is not None and random.random() < 0.3:
            return {'type': 'pass'}
        return {'type': 'play', 'cards': play}

    def play_value(cards: list[str]) -> int:
        r = rank(cards[0])
        v = RANK_VAL[r]
        return -v if revolution else v

    plays_sorted = sorted(plays, key=play_value)

    if state['trick_rank'] is None:
        if caps['revolution_aware']:
            fours = [p for p in plays if len(p) == 4]
            if fours:
                fours.sort(key=play_value)
                return {'type': 'play', 'cards': fours[0]}

        if caps['endgame'] and len(state['hands'][who]) <= 3:
            for p in plays:
                if len(p) == len(state['hands'][who]):
                    return {'type': 'play', 'cards': p}

        if caps['save_high']:
            if caps['pair_awareness']:
                singles = [p for p in plays_sorted if len(p) == 1]
                if singles:
                    return {'type': 'play', 'cards': singles[0]}
            return {'type': 'play', 'cards': plays_sorted[0]}

        return {'type': 'play', 'cards': plays_sorted[0]}

    if caps['revolution_aware']:
        groups = _group_by_rank(state['hands'][who])
        four_ranks = {r for r, cards in groups.items() if len(cards) == 4}
        if four_ranks:
            safe_plays = [p for p in plays_sorted if rank(p[0]) not in four_ranks]
            if safe_plays:
                plays_sorted = safe_plays
            else:
                return {'type': 'pass'}

    if caps['pass_strategy']:
        active = _active_players(state)
        if caps['opponent_aware']:
            opp_counts = {p: len(state['hands'][p])
                          for p in active if p != who}
            min_opp = min(opp_counts.values()) if opp_counts else 99
            if min_opp <= 2:
                return {'type': 'play', 'cards': plays_sorted[0]}

        lowest_rank_val = RANK_VAL[rank(plays_sorted[0][0])]
        effective_val = (7 - lowest_rank_val) if revolution else lowest_rank_val
        if effective_val >= 5 and len(active) > 2:
            return {'type': 'pass'}

    return {'type': 'play', 'cards': plays_sorted[0]}


def ai_swap_choose(state: dict, who: str) -> list[str]:
    caps = _caps(state['level'])
    hand = state['hands'][who]
    revolution = state.get('prev_revolution', False)

    if not caps['swap_optimize']:
        return hand[:2]

    sorted_hand = sorted(hand, key=lambda c: _rank_sort_key(rank(c), revolution))
    if caps['pair_awareness']:
        groups = _group_by_rank(sorted_hand)
        give = []
        for c in sorted_hand:
            r = rank(c)
            if len(groups[r]) == 1 or len(give) == 0:
                give.append(c)
            elif len(give) < 2:
                give.append(c)
            if len(give) == 2:
                break
        return give

    return sorted_hand[:2]


def hint_for_player(state: dict) -> dict | None:
    """Konkreter, erklärender Tipp für den Menschen.

    Folgt der Standard-Strategie: kleine Karten zuerst loswerden, beim
    Ausspielen Paare/Drillinge legen um Gegner zum Passen zu zwingen,
    günstig überbieten statt zu passen, hohe Karten für die Endphase
    aufsparen und Gegner blockieren, die kurz vorm Ausspielen stehen.
    Jeder Tipp enthält ein ``reason`` zur Erklärung.
    """
    if state['status'] == 'swap_choose' and state.get('swap_receiving') == 'p':
        saved = state.get('level')
        state['level'] = 'hard'
        try:
            cards = ai_swap_choose(state, 'p')
        finally:
            state['level'] = saved
        return {'type': 'swap_choose', 'cards': cards, 'reason': 'swap'}

    if not (state['status'] == 'playing' and state['turn'] == 'p'):
        return None

    plays = legal_plays(state, 'p')
    revolution = state['revolution']
    hand = state['hands']['p']

    if not plays:
        return {'type': 'pass', 'reason': 'no_play'}

    def play_value(cards: list[str]) -> int:
        v = RANK_VAL[rank(cards[0])]
        return -v if revolution else v

    plays_sorted = sorted(plays, key=play_value)

    # Endphase: lassen sich alle restlichen Karten in einem Zug ablegen?
    finishers = sorted((p for p in plays if len(p) == len(hand)), key=play_value)
    if finishers:
        return {'type': 'play', 'cards': finishers[0], 'reason': 'endgame'}

    # Ausspielen (Kontrolle): kleine Karten zuerst, Paare/Drillinge bevorzugt
    if state['trick_rank'] is None:
        low_rank = rank(plays_sorted[0][0])
        multi = [p for p in plays if rank(p[0]) == low_rank and len(p) > 1]
        if multi:
            multi.sort(key=len, reverse=True)
            return {'type': 'play', 'cards': multi[0], 'reason': 'lead_multi'}
        return {'type': 'play', 'cards': plays_sorted[0], 'reason': 'lead_low'}

    # Auf einen Stich reagieren
    active = _active_players(state)
    opp_counts = [len(state['hands'][p]) for p in active if p != 'p']
    min_opp = min(opp_counts) if opp_counts else 99

    # Gegner kurz vorm Ausspielen -> jetzt blockieren
    if min_opp <= 2:
        return {'type': 'play', 'cards': plays_sorted[0], 'reason': 'block'}

    # Günstige Karte (7–10) zum Überbieten -> Karten abbauen
    lowest_val = RANK_VAL[rank(plays_sorted[0][0])]
    effective = (RANK_VAL['A'] - lowest_val) if revolution else lowest_val
    if effective <= RANK_VAL['T']:
        return {'type': 'play', 'cards': plays_sorted[0], 'reason': 'beat_low'}

    # sonst: hohe Karten für später aufsparen
    return {'type': 'pass', 'reason': 'save_high'}
