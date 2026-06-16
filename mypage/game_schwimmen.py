"""Schwimmen (31) — Kartenspiel für 3 Spieler (1 Mensch + 2 KI).

Regeln:
- 32 Karten (Französisches Blatt, 7 bis Ass)
- 3 Spieler, jeder startet mit 3 Leben
- Ziel: Karten einer Farbe mit höchstem Wert sammeln (max 31)
- Jede Runde: 3 Handkarten + 3 offene Tischkarten
- Aktionen: 1 Karte tauschen, alle tauschen, passen, oder klopfen
- Niedrigste Hand verliert ein Leben
- Schwimmen = 0 Leben, letzte Chance
- Feuer (3 Asse) = alle anderen verlieren 1 Leben
"""
from __future__ import annotations

import copy
import random

# ── Konstanten ─────────────────────────────────────────
SUITS = ('h', 'd', 's', 'c')
RANKS = ('7', '8', '9', 'T', 'J', 'Q', 'K', 'A')
PLAYERS = ('p', 'a1', 'a2')

SUIT_SYM = {'h': '♥', 'd': '♦', 's': '♠', 'c': '♣'}
SUIT_NAME = {'h': 'Herz', 'd': 'Karo', 's': 'Pik', 'c': 'Kreuz'}
RANK_NAME = {
    '7': '7', '8': '8', '9': '9', 'T': '10',
    'J': 'Bube', 'Q': 'Dame', 'K': 'König', 'A': 'Ass',
}
CARD_VAL = {
    '7': 7, '8': 8, '9': 9, 'T': 10,
    'J': 10, 'Q': 10, 'K': 10, 'A': 11,
}


# ── Karten-Hilfsfunktionen ────────────────────────────
def suit(c: str) -> str:
    return c[0]


def rank(c: str) -> str:
    return c[1]


def card_value(c: str) -> int:
    return CARD_VAL[c[1]]


def card_name(c: str) -> str:
    return f"{RANK_NAME[rank(c)]} {SUIT_SYM[suit(c)]}"


def full_deck() -> list[str]:
    return [s + r for s in SUITS for r in RANKS]


def next_alive(current: str, alive: list[str]) -> str:
    idx = PLAYERS.index(current)
    for i in range(1, 4):
        p = PLAYERS[(idx + i) % 3]
        if p in alive:
            return p
    return current


def _skey(c: str):
    return (SUITS.index(suit(c)), CARD_VAL.get(rank(c), 0))


# ── Handwert berechnen ────────────────────────────────
def hand_value(cards: list[str]) -> float:
    if len(cards) != 3:
        return 0
    # Drilling = 30.5
    if rank(cards[0]) == rank(cards[1]) == rank(cards[2]):
        return 30.5
    by_suit: dict[str, float] = {}
    for c in cards:
        s = suit(c)
        by_suit[s] = by_suit.get(s, 0) + card_value(c)
    return max(by_suit.values())


def is_feuer(cards: list[str]) -> bool:
    return len(cards) == 3 and all(rank(c) == 'A' for c in cards)


def is_31(cards: list[str]) -> bool:
    return hand_value(cards) == 31


# ── Spielzustand ───────────────────────────────────────
def new_game(level: str = 'medium') -> dict:
    state = {
        'lives': {p: 3 for p in PLAYERS},
        'alive': list(PLAYERS),
        'eliminated': [],
        'dealer': 'p',
        'level': level,
        'status': 'playing',
        'round_nr': 0,
        'seed': random.randint(0, 2**31),
    }
    deal_round(state)
    return state


def deal_round(state: dict) -> None:
    state['round_nr'] += 1
    rng = random.Random(state['seed'] + state['round_nr'] * 997)
    deck = full_deck()
    rng.shuffle(deck)

    alive = state['alive']
    state['hands'] = {}
    idx = 0
    for p in PLAYERS:
        if p in alive:
            state['hands'][p] = sorted(deck[idx:idx + 3], key=_skey)
            idx += 3
        else:
            state['hands'][p] = []

    state['table_cards'] = sorted(deck[idx:idx + 3], key=_skey)
    idx += 3
    state['deck'] = deck[idx:]
    state['turn'] = next_alive(state['dealer'], alive)
    state['status'] = 'playing'
    state['knocked_by'] = None
    state['pass_count'] = 0
    state['round_result'] = None
    state['turn_count'] = 0
    state['swap_log'] = []
    state['move_log'] = []

    # Sofort 31 oder Feuer in der Hand?
    for p in alive:
        if is_31(state['hands'][p]) or is_feuer(state['hands'][p]):
            state['instant_winner'] = p
            _score_round(state)
            return


# ── Rundenauswertung ──────────────────────────────────
def _score_round(state: dict) -> None:
    alive = state['alive']
    values = {p: hand_value(state['hands'][p]) for p in alive}

    result = {
        'values': {p: values[p] for p in alive},
        'hands': {p: list(state['hands'][p]) for p in alive},
    }

    instant = state.get('instant_winner')

    if instant and is_feuer(state['hands'][instant]):
        result['feuer'] = instant
        result['losers'] = {p: 1 for p in alive if p != instant}
    else:
        if instant and is_31(state['hands'][instant]):
            result['thirty_one'] = instant
        min_val = min(values.values())
        result['losers'] = {p: 1 for p in alive if values[p] == min_val}

    newly_eliminated = []
    newly_swimming = []
    for p, loss in result['losers'].items():
        old = state['lives'][p]
        if old == 0:
            newly_eliminated.append(p)
        else:
            state['lives'][p] = max(0, old - loss)
            if state['lives'][p] == 0:
                newly_swimming.append(p)

    result['newly_eliminated'] = newly_eliminated
    result['newly_swimming'] = newly_swimming

    for p in newly_eliminated:
        if p in state['alive']:
            state['alive'].remove(p)
        if p not in state['eliminated']:
            state['eliminated'].append(p)

    state['round_result'] = result

    if len(state['alive']) <= 1:
        state['winner'] = state['alive'][0] if state['alive'] else None
        state['status'] = 'game_over'
    else:
        state['status'] = 'round_over'


# ── Aktionen ───────────────────────────────────────────
class IllegalMove(Exception):
    pass


def apply_action(state: dict, player: str, action: dict) -> list:
    t = action['type']
    if t == 'swap_one':
        return _apply_swap_one(state, player,
                               action['hand_card'], action['table_card'])
    if t == 'swap_all':
        return _apply_swap_all(state, player)
    if t == 'pass':
        return _apply_pass(state, player)
    if t == 'knock':
        return _apply_knock(state, player)
    if t == 'next_round':
        return _apply_next_round(state)
    if t == 'new_game':
        ns = new_game(action.get('level', state.get('level', 'medium')))
        state.clear()
        state.update(ns)
        return []
    raise IllegalMove(f'Unbekannter Aktionstyp: {t}')


def _after_action(state: dict) -> None:
    current = state['turn']
    hand = state['hands'].get(current, [])

    if hand and (is_31(hand) or is_feuer(hand)):
        state['instant_winner'] = current
        _score_round(state)
        return

    alive = state['alive']
    nxt = next_alive(current, alive)

    if state['knocked_by'] is not None and nxt == state['knocked_by']:
        _score_round(state)
        return

    state['turn'] = nxt
    state['turn_count'] += 1


def _apply_swap_one(state: dict, player: str,
                    hand_card: str, table_card: str) -> list:
    if state['status'] != 'playing' or state['turn'] != player:
        raise IllegalMove('Nicht dein Zug')
    hand = state['hands'][player]
    table = state['table_cards']
    if hand_card not in hand:
        raise IllegalMove(f'Karte {hand_card} nicht auf der Hand')
    if table_card not in table:
        raise IllegalMove(f'Karte {table_card} nicht auf dem Tisch')

    hi = hand.index(hand_card)
    ti = table.index(table_card)
    hand[hi] = table_card
    table[ti] = hand_card
    hand.sort(key=_skey)
    table.sort(key=_skey)

    state.setdefault('swap_log', []).append({
        'who': player, 'took': table_card, 'gave': hand_card,
    })
    state.setdefault('move_log', []).append({
        'who': player, 'action': 'swap_one',
        'took': table_card, 'gave': hand_card,
    })
    state['pass_count'] = 0
    state['table_refreshed'] = False
    _after_action(state)
    return []


def _apply_swap_all(state: dict, player: str) -> list:
    if state['status'] != 'playing' or state['turn'] != player:
        raise IllegalMove('Nicht dein Zug')
    old_hand = list(state['hands'][player])
    old_table = list(state['table_cards'])
    state['hands'][player] = sorted(old_table, key=_skey)
    state['table_cards'] = sorted(old_hand, key=_skey)

    state.setdefault('swap_log', []).append({
        'who': player, 'took_all': old_table, 'gave_all': old_hand,
    })
    state.setdefault('move_log', []).append({
        'who': player, 'action': 'swap_all',
    })
    state['pass_count'] = 0
    state['table_refreshed'] = False
    _after_action(state)
    return []


def _apply_pass(state: dict, player: str) -> list:
    if state['status'] != 'playing' or state['turn'] != player:
        raise IllegalMove('Nicht dein Zug')

    state['pass_count'] += 1
    state.setdefault('move_log', []).append({
        'who': player, 'action': 'pass',
    })

    if state['knocked_by'] is None and state['pass_count'] >= len(state['alive']):
        deck = state.get('deck', [])
        if len(deck) >= 3:
            state['table_cards'] = sorted(deck[:3], key=_skey)
            state['deck'] = deck[3:]
            state['pass_count'] = 0
            state['table_refreshed'] = True
            state['move_log'][-1]['table_refreshed'] = True
        else:
            _score_round(state)
            return []

    _after_action(state)
    return []


def _apply_knock(state: dict, player: str) -> list:
    if state['status'] != 'playing' or state['turn'] != player:
        raise IllegalMove('Nicht dein Zug')
    if state['knocked_by'] is not None:
        raise IllegalMove('Es wurde bereits geklopft')

    state['knocked_by'] = player
    state['pass_count'] = 0
    state.setdefault('move_log', []).append({
        'who': player, 'action': 'knock',
    })

    nxt = next_alive(player, state['alive'])
    if nxt == player:
        _score_round(state)
        return []

    state['turn'] = nxt
    state['turn_count'] += 1
    return []


def _apply_next_round(state: dict) -> list:
    if state['status'] != 'round_over':
        raise IllegalMove('Runde nicht vorbei')
    state['dealer'] = next_alive(state['dealer'], state['alive'])
    state.pop('instant_winner', None)
    deal_round(state)
    return []


# ── KI ─────────────────────────────────────────────────
_LEVEL_STR = {'easy': 30, 'medium': 60, 'hard': 100}

_CAPS = {
    'smart_swap': 40,
    'value_aware': 50,
    'knock_smart': 55,
    'table_analysis': 60,
    'life_aware': 60,
    'card_memory': 65,
    'bluff_pass': 65,
    'defensive_play': 70,
    'opponent_aware': 70,
    'optimal_play': 80,
}


def _caps(state: dict) -> dict:
    s = _LEVEL_STR.get(state.get('level', 'medium'), 60)
    return {k: s >= v for k, v in _CAPS.items()}


def _best_suit_val(hand: list[str]) -> tuple[str, float]:
    by_suit: dict[str, float] = {}
    for c in hand:
        s = suit(c)
        by_suit[s] = by_suit.get(s, 0) + card_value(c)
    if not by_suit:
        return 'h', 0
    best_s = max(by_suit, key=lambda s: by_suit[s])
    return best_s, by_suit[best_s]


def _infer_opponent_suits(state: dict, who: str) -> dict:
    """Aus dem Tausch-Log ableiten, welche Farbe jeder Gegner sammelt."""
    scores: dict[str, dict[str, float]] = {}
    for p in state['alive']:
        if p == who:
            continue
        scores[p] = {s: 0.0 for s in SUITS}

    for entry in state.get('swap_log', []):
        p = entry['who']
        if p == who or p not in scores:
            continue
        if 'took' in entry:
            scores[p][suit(entry['took'])] += 2
        if 'gave' in entry:
            scores[p][suit(entry['gave'])] -= 1
        for c in entry.get('gave_all', []):
            scores[p][suit(c)] -= 1
        for c in entry.get('took_all', []):
            scores[p][suit(c)] += 1

    result = {}
    for p, ss in scores.items():
        best = max(ss, key=lambda s: ss[s])
        if ss[best] > 0:
            result[p] = best
    return result


def _defensive_penalty(card: str, opponent_suits: dict) -> float:
    """Strafwert: wie sehr hilft diese Karte auf dem Tisch den Gegnern."""
    penalty = 0.0
    s = suit(card)
    v = card_value(card)
    for _, opp_suit in opponent_suits.items():
        if s == opp_suit:
            penalty += v * 0.5
    return penalty


def _smart_swap_all(hand: list[str], table: list[str], val: float) -> bool:
    """Prüft ob alle-tauschen sinnvoll ist (Farbkonzentration + Wert)."""
    table_val = hand_value(table)
    if table_val > val + 5:
        return True
    t_best = max(sum(1 for c in table if suit(c) == s) for s in SUITS)
    h_best = max(sum(1 for c in hand if suit(c) == s) for s in SUITS)
    if t_best == 3 and h_best < 3 and table_val > val:
        return True
    if t_best > h_best and table_val > val + 2:
        return True
    return False


def _knock_threshold(state: dict, who: str, caps: dict) -> float:
    """Dynamische Klopf-Schwelle basierend auf Lebenstand."""
    if not caps.get('life_aware'):
        return 25
    lives = state['lives'].get(who, 3)
    if lives == 0:
        return 20
    if lives == 1:
        return 22
    if lives == 2:
        return 25
    return 27


def ai_play(state: dict, who: str) -> dict:
    caps = _caps(state)
    hand = state['hands'][who]
    table = state['table_cards']
    val = hand_value(hand)

    # ── Easy: weitgehend zufällig ──────────────────────
    if not caps['smart_swap']:
        r = random.random()
        if val >= 28 and state['knocked_by'] is None:
            return {'type': 'knock'}
        if r < 0.15:
            return {'type': 'pass'}
        if r < 0.3:
            return {'type': 'swap_all'}
        hc = random.choice(hand)
        tc = random.choice(table)
        return {'type': 'swap_one', 'hand_card': hc, 'table_card': tc}

    # ── Medium+: intelligent ───────────────────────────
    opponent_suits: dict = {}
    if caps.get('card_memory'):
        opponent_suits = _infer_opponent_suits(state, who)

    k_thresh = _knock_threshold(state, who, caps)

    # Sehr gute Hand → sofort klopfen
    if val >= 30 and state['knocked_by'] is None:
        return {'type': 'knock'}

    # Alle tauschen — Farbkonzentration + Wert prüfen
    if caps.get('value_aware') and _smart_swap_all(hand, table, val):
        return {'type': 'swap_all'}

    # Besten Einzeltausch finden (mit defensivem Bewusstsein)
    best_swap = None
    best_score = 0.0
    for hc in hand:
        for tc in table:
            new_hand = list(hand)
            new_hand[new_hand.index(hc)] = tc
            new_val = hand_value(new_hand)
            gain = new_val - val
            if caps.get('defensive_play') and opponent_suits:
                gain -= _defensive_penalty(hc, opponent_suits)
            if gain > best_score:
                best_score = gain
                best_swap = (hc, tc)

    if best_swap and best_score > 0:
        return {'type': 'swap_one',
                'hand_card': best_swap[0], 'table_card': best_swap[1]}

    # Farbfokus: neutrale Tausche die Farbkonzentration verbessern
    if caps.get('table_analysis'):
        best_s, _ = _best_suit_val(hand)
        off_suit = [c for c in hand if suit(c) != best_s]
        on_suit_table = [c for c in table if suit(c) == best_s]
        if off_suit and on_suit_table:
            worst_off = min(off_suit, key=card_value)
            best_on = max(on_suit_table, key=card_value)
            new_hand = list(hand)
            new_hand[new_hand.index(worst_off)] = best_on
            if hand_value(new_hand) >= val:
                d_pen = 0.0
                if caps.get('defensive_play') and opponent_suits:
                    d_pen = _defensive_penalty(worst_off, opponent_suits)
                if d_pen < 4:
                    return {'type': 'swap_one',
                            'hand_card': worst_off, 'table_card': best_on}

    # Klopfen bei dynamischer Schwelle (Spielstand-Bewusstsein)
    if caps.get('knock_smart') and val >= k_thresh and state['knocked_by'] is None:
        return {'type': 'knock'}

    # Gegen Schwimmer noch aggressiver klopfen
    if caps.get('opponent_aware') and state['knocked_by'] is None:
        swimming = sum(1 for p in state['alive']
                       if p != who and state['lives'][p] == 0)
        if swimming > 0 and val >= max(k_thresh - 3, 18):
            return {'type': 'knock'}

    # Hard: aggressives Klopfen
    if caps.get('optimal_play') and val >= 27 and state['knocked_by'] is None:
        return {'type': 'knock'}

    # Bluff-Passen: Tischkarten schlecht → schieben um neue zu erzwingen
    if caps.get('bluff_pass') and state['knocked_by'] is None:
        table_max = max(card_value(c) for c in table)
        if table_max <= 9 and val >= 18:
            return {'type': 'pass'}

    return {'type': 'pass'}


# ── Public View ────────────────────────────────────────
def public_view(state: dict) -> dict:
    v = copy.deepcopy(state)
    for p in ('a1', 'a2'):
        if p in v.get('hands', {}) and isinstance(v['hands'][p], list):
            v['hands'][p] = len(v['hands'][p])
    v.pop('seed', None)
    if isinstance(v.get('hands', {}).get('p'), list):
        v['hand_value_p'] = hand_value(state['hands']['p'])
    if state.get('move_log'):
        v['move_log'] = state['move_log']
    return v


def hint_for_player(state: dict) -> dict | None:
    """Besten Zug für den Spieler berechnen (Hard-KI-Logik)."""
    if state['status'] != 'playing' or state['turn'] != 'p':
        return None
    saved = state.get('level')
    state['level'] = 'hard'
    try:
        return ai_play(state, 'p')
    finally:
        state['level'] = saved
