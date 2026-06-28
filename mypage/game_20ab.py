"""20 AB — Stichspiel für 3 Spieler (1 Mensch + 2 KI).

Regeln:
- 32 Karten (Französisches Blatt, 7 bis Ass)
- 3 Spieler, jeder startet mit 20 Punkten
- Ziel: als erster genau 0 Punkte erreichen
- Jede Runde: Startspieler wählt Trumpf → Reizen → 5 Stiche
- Kreuz als Trumpf: alle müssen mitspielen
- "Nächste Karte" als Trumpf: nur wenn Kreuz gezogen wird müssen alle mitspielen,
  sonst darf normal gereizt (ausgestiegen) werden
- Herz als Trumpf: alle Punkte doppelt
- Überschuss prallt zurück (Bounce-Regel)
- Wer in einer Runde aussteigt, muss in der nächsten Runde mitspielen
- Wer weniger als 6 Punkte hat, darf nicht mehr aussteigen
"""
from __future__ import annotations

import copy
import random

# ── Konstanten ─────────────────────────────────────────
SUITS = ('h', 'd', 's', 'c')
RANKS = ('7', '8', '9', 'T', 'J', 'Q', 'K', 'A')
RANK_VAL = {r: i for i, r in enumerate(RANKS)}
PLAYERS = ('p', 'a1', 'a2')

SUIT_SYM = {'h': '♥', 'd': '♦', 's': '♠', 'c': '♣'}
SUIT_NAME = {'h': 'Herz', 'd': 'Karo', 's': 'Pik', 'c': 'Kreuz'}
RANK_NAME = {
    '7': '7', '8': '8', '9': '9', 'T': '10',
    'J': 'Bube', 'Q': 'Dame', 'K': 'König', 'A': 'Ass',
}


# ── Karten-Hilfsfunktionen ────────────────────────────
def suit(c: str) -> str:
    return c[0]


def rank(c: str) -> str:
    return c[1]


def rval(c: str) -> int:
    return RANK_VAL[c[1]]


def card_name(c: str) -> str:
    return f"{RANK_NAME[rank(c)]} {SUIT_SYM[suit(c)]}"


def full_deck() -> list[str]:
    return [s + r for s in SUITS for r in RANKS]


def next_p(p: str) -> str:
    return PLAYERS[(PLAYERS.index(p) + 1) % 3]


def play_order(leader: str) -> list[str]:
    i = PLAYERS.index(leader)
    return [PLAYERS[(i + j) % 3] for j in range(3)]


def active_order(leader: str, active: list) -> list[str]:
    i = PLAYERS.index(leader)
    return [PLAYERS[(i + j) % 3] for j in range(3) if PLAYERS[(i + j) % 3] in active]


# ── Spielzustand ───────────────────────────────────────
def new_game(level: str = 'medium', seed: int | None = None) -> dict:
    state = {
        'scores': {p: 20 for p in PLAYERS},
        'starter': None,
        'level': level,
        'status': 'cutting',
        'round_nr': 0,
        'seed': seed if seed is not None else random.randint(0, 2**31),
    }
    _do_cutting(state)
    return state


def _do_cutting(state: dict) -> None:
    """Wer fängt an: jeder zieht eine Karte, höchste gewinnt."""
    rng = random.Random(state['seed'] * 31)
    deck = full_deck()
    rng.shuffle(deck)
    cuts = {}
    for i, p in enumerate(PLAYERS):
        cuts[p] = deck[i]

    def cut_power(p):
        c = cuts[p]
        return (RANK_VAL[rank(c)], SUITS.index(suit(c)))

    winner = max(PLAYERS, key=cut_power)
    state['cut_cards'] = cuts
    state['starter'] = winner


def deal_round(state: dict) -> None:
    state['round_nr'] += 1
    rng = random.Random(state['seed'] + state['round_nr'] * 997)
    deck = full_deck()
    rng.shuffle(deck)

    skey = lambda c: (SUITS.index(suit(c)), RANK_VAL[rank(c)])
    state['hands'] = {
        'p':  sorted(deck[0:2], key=skey),
        'a1': sorted(deck[2:4], key=skey),
        'a2': sorted(deck[4:6], key=skey),
    }
    state['extra_cards'] = {
        'p':  deck[6:9],
        'a1': deck[9:12],
        'a2': deck[12:15],
    }
    state['exchange_deck'] = deck[15:]
    state['exchange_done'] = {}
    state['exchange_turn'] = None
    state['dealt_full'] = False
    state['trump'] = None
    state['trump_card'] = None
    state['trump_chooser'] = state['starter']
    state['bids'] = {}
    state['bid_order'] = play_order(state['starter'])
    state['bid_turn'] = None
    state['active'] = []
    state['forced'] = False
    # Wer letzte Runde ausgestiegen ist, muss diese Runde mitspielen
    state['must_play'] = list(state.get('passed_last', []))
    state['table'] = []
    state['tricks'] = {p: 0 for p in PLAYERS}
    state['trick_nr'] = 0
    state['lead'] = None
    state['turn'] = None
    state['played'] = []
    state['round_result'] = None
    state['last_trick'] = None
    state['trick_result'] = None
    state['herz_blind'] = False
    state['status'] = 'herz_blind_ask'


# ── Legale Karten ──────────────────────────────────────
def legal_cards(state: dict, player: str) -> list[str]:
    hand = state['hands'][player]
    if not state['table']:
        return list(hand)
    lead_s = suit(state['table'][0]['card'])
    follow = [c for c in hand if suit(c) == lead_s]
    return follow if follow else list(hand)


# ── Aussteige-Regeln ──────────────────────────────────
def can_pass(state: dict, player: str) -> bool:
    """Darf der Spieler beim Reizen aussteigen (passen)?

    Nein, wenn er weniger als 6 Punkte hat oder letzte Runde schon
    ausgestiegen ist (dann muss er diese Runde mitspielen).
    """
    if state['scores'].get(player, 0) < 6:
        return False
    if player in state.get('must_play', []):
        return False
    return True


# ── Stich-Auswertung ──────────────────────────────────
def trick_winner(table: list[dict], trump: str) -> str:
    lead_s = suit(table[0]['card'])

    def power(entry):
        c = entry['card']
        if suit(c) == trump:
            return (2, rval(c))
        if suit(c) == lead_s:
            return (1, rval(c))
        return (0, rval(c))

    return max(table, key=power)['who']


# ── Aktionen ───────────────────────────────────────────
class IllegalMove(Exception):
    pass


def apply_action(state: dict, player: str, action: dict) -> list:
    t = action['type']
    if t == 'proceed':
        return _apply_proceed(state)
    if t == 'herz_blind':
        return _apply_herz_blind(state, player, action['value'])
    if t == 'choose_trump':
        return _apply_trump(state, player, action['suit'])
    if t == 'bid':
        return _apply_bid(state, player, action['value'])
    if t == 'exchange':
        return _apply_exchange(state, player, action.get('cards', []))
    if t == 'play':
        return _apply_play(state, player, action['card'])
    if t == 'collect':
        return _apply_collect(state)
    if t == 'next_round':
        state['starter'] = next_p(state['starter'])
        deal_round(state)
        return []
    if t == 'new_game':
        ns = new_game(action.get('level', state.get('level', 'medium')))
        state.clear()
        state.update(ns)
        return []
    raise IllegalMove(f'Unbekannter Aktionstyp: {t}')


def _apply_proceed(state: dict) -> list:
    if state['status'] != 'cutting':
        raise IllegalMove('Kein Kartenziehen aktiv')
    deal_round(state)
    return []


def _apply_herz_blind(state: dict, player: str, value: str) -> list:
    if state['status'] != 'herz_blind_ask' or state['trump_chooser'] != player:
        raise IllegalMove('Nicht dein Zug für Herz Blind')
    if value not in ('yes', 'no'):
        raise IllegalMove('Ungültige Wahl')

    if value == 'yes':
        state['herz_blind'] = True
        state['trump'] = 'h'
        state['bids'][player] = 'play'
        state['active'].append(player)
        for p in PLAYERS:
            if p not in state['active']:
                state['active'].append(p)
                state['bids'][p] = 'play'
        _deal_extra(state)
        _start_exchange(state)
    else:
        state['status'] = 'trump_sel'
    return []


def _apply_trump(state: dict, player: str, chosen: str) -> list:
    if state['status'] != 'trump_sel' or state['trump_chooser'] != player:
        raise IllegalMove('Du darfst keinen Trumpf wählen')
    if chosen not in SUITS and chosen != 'next':
        raise IllegalMove('Ungültige Farbe')

    state['bids'][player] = 'play'
    state['active'].append(player)

    if chosen == 'next':
        edeck = state['exchange_deck']
        drawn = edeck[0]
        state['exchange_deck'] = edeck[1:]
        state['trump'] = suit(drawn)
        state['trump_card'] = drawn
        # Trumpfkarte geht an den Wähler, dafür eine Extra-Karte zurück
        state['hands'][player].append(drawn)
        extras = state.get('extra_cards', {}).get(player, [])
        if extras:
            returned = extras.pop(0)
            state['extra_cards'][player] = extras
            state['exchange_deck'].append(returned)
        if suit(drawn) == 'c':
            # Kreuz gezogen → alle müssen mitspielen
            for p in PLAYERS:
                if p not in state['active']:
                    state['active'].append(p)
                    state['bids'][p] = 'play'
            _deal_extra(state)
            _start_exchange(state)
        else:
            # Kein Kreuz → normal reizen, man darf aussteigen
            order = state['bid_order']
            state['bid_turn'] = order[1]
            state['status'] = 'bidding'
    elif chosen == 'c':
        state['trump'] = chosen
        for p in PLAYERS:
            if p not in state['active']:
                state['active'].append(p)
                state['bids'][p] = 'play'
        _deal_extra(state)
        _start_exchange(state)
    else:
        state['trump'] = chosen
        order = state['bid_order']
        state['bid_turn'] = order[1]
        state['status'] = 'bidding'
    return []


def _apply_bid(state: dict, player: str, value: str) -> list:
    if state['status'] != 'bidding' or state['bid_turn'] != player:
        raise IllegalMove('Nicht dein Zug zum Reizen')
    if value not in ('play', 'pass'):
        raise IllegalMove('Ungültiges Gebot')
    if value == 'pass' and not can_pass(state, player):
        raise IllegalMove('Du musst in dieser Runde mitspielen')

    state['bids'][player] = value
    if value == 'play':
        state['active'].append(player)

    order = state['bid_order']
    idx = order.index(player)

    if idx == 1:
        if value == 'pass':
            forced_p = order[2]
            state['bids'][forced_p] = 'play'
            state['active'].append(forced_p)
            state['forced'] = True
            _finish_bidding(state)
        else:
            state['bid_turn'] = order[2]
    else:
        _finish_bidding(state)

    return []


def _deal_extra(state: dict) -> None:
    if state.get('dealt_full'):
        return
    skey = lambda c: (SUITS.index(suit(c)), RANK_VAL[rank(c)])
    extra = state.pop('extra_cards', {})
    for p in PLAYERS:
        if p in state.get('active', PLAYERS):
            state['hands'][p].extend(extra.get(p, []))
            state['hands'][p].sort(key=skey)
    state['dealt_full'] = True


def _finish_bidding(state: dict) -> None:
    _deal_extra(state)
    for p in PLAYERS:
        if p not in state['active']:
            state['hands'][p] = []
    _start_exchange(state)


def _start_exchange(state: dict) -> None:
    order = active_order(state['starter'], state['active'])
    state['exchange_turn'] = order[0]
    state['status'] = 'exchanging'


def _apply_exchange(state: dict, player: str, cards: list) -> list:
    if state['status'] != 'exchanging' or state['exchange_turn'] != player:
        raise IllegalMove('Nicht dein Zug zum Tauschen')
    if len(cards) > 3:
        raise IllegalMove('Maximal 3 Karten tauschen')
    hand = state['hands'][player]
    for c in cards:
        if c not in hand:
            raise IllegalMove(f'Karte {c} nicht auf der Hand')

    skey = lambda c: (SUITS.index(suit(c)), RANK_VAL[rank(c)])
    for c in cards:
        hand.remove(c)
    edeck = state['exchange_deck']
    drawn = edeck[:len(cards)]
    state['exchange_deck'] = edeck[len(cards):]
    hand.extend(drawn)
    hand.sort(key=skey)

    state['exchange_done'][player] = len(cards)

    order = active_order(state['starter'], state['active'])
    idx = order.index(player)
    if idx + 1 < len(order):
        state['exchange_turn'] = order[idx + 1]
    else:
        _start_playing(state)
    return []


def _start_playing(state: dict) -> None:
    state['status'] = 'playing'
    state['lead'] = state['starter']
    state['turn'] = state['starter']


def _apply_play(state: dict, player: str, card: str) -> list:
    if state['status'] != 'playing' or state['turn'] != player:
        raise IllegalMove('Nicht dein Zug')
    legal = legal_cards(state, player)
    if card not in legal:
        raise IllegalMove(f'Karte {card} ist nicht erlaubt')

    state['hands'][player].remove(card)
    state['table'].append({'who': player, 'card': card})
    state['played'].append(card)

    if len(state['table']) == len(state['active']):
        winner = trick_winner(state['table'], state['trump'])
        state['tricks'][winner] += 1
        state['trick_nr'] += 1
        state['trick_result'] = winner
        state['last_trick'] = list(state['table'])
        state['status'] = 'trick_done'
    else:
        order = active_order(state['lead'], state['active'])
        ci = order.index(player)
        state['turn'] = order[ci + 1]

    return []


def _apply_collect(state: dict) -> list:
    if state['status'] != 'trick_done':
        raise IllegalMove('Kein Stich zum Einsammeln')

    winner = state['trick_result']
    state['table'] = []
    state['trick_result'] = None

    if state['trick_nr'] >= 5:
        _score_round(state)
    else:
        state['lead'] = winner
        state['turn'] = winner
        state['status'] = 'playing'

    return []


# ── Rundenauswertung ──────────────────────────────────
def _score_round(state: dict) -> None:
    is_hearts = state['trump'] == 'h'
    is_blind = state.get('herz_blind', False)
    mult = 4 if is_blind else (2 if is_hearts else 1)
    result = {'hearts': is_hearts, 'herz_blind': is_blind, 'trump': state['trump']}

    for p in PLAYERS:
        old = state['scores'][p]
        if p not in state['active']:
            result[p] = {
                'old': old, 'new': old, 'change': 0,
                'tricks': state['tricks'][p], 'active': False, 'bounced': False,
            }
            continue

        tricks = state['tricks'][p]
        if tricks == 0:
            change = 5 * mult
        else:
            change = -(tricks * mult)

        new_score = old + change
        bounced = False
        if new_score < 0:
            new_score = -new_score
            bounced = True

        state['scores'][p] = new_score
        result[p] = {
            'old': old, 'new': new_score, 'change': change,
            'tricks': tricks, 'active': True, 'bounced': bounced,
        }

    state['round_result'] = result

    # Wer ausgestiegen ist, muss nächste Runde mitspielen
    state['passed_last'] = [p for p in PLAYERS if p not in state['active']]

    winners = [p for p in PLAYERS if state['scores'][p] == 0]
    if winners:
        if state['trump_chooser'] in winners:
            state['winner'] = state['trump_chooser']
        else:
            for p in state['bid_order']:
                if p in winners:
                    state['winner'] = p
                    break
        state['status'] = 'game_over'
    else:
        state['status'] = 'round_over'


# ── KI ─────────────────────────────────────────────────
_LEVEL_STR = {'easy': 30, 'medium': 60, 'hard': 100}

_CAPS = {
    'smart_bid': 45,
    'smart_trump': 45,
    'smart_play': 40,
    'score_aware': 55,
    'card_counting': 70,
    'aggressive_bid': 75,
    'optimal_lead': 70,
}


def _caps(state: dict) -> dict:
    s = _LEVEL_STR.get(state.get('level', 'medium'), 60)
    return {k: s >= v for k, v in _CAPS.items()}


def ai_herz_blind(state: dict, who: str) -> str:
    caps = _caps(state)
    score = state['scores'][who]
    others_min = min(state['scores'][p] for p in PLAYERS if p != who)

    if not caps.get('smart_bid', False):
        return 'yes' if score >= 16 and random.random() < 0.15 else 'no'

    # Hohe Punktzahl + Gegner nah an 0 → verzweifelter Versuch
    if score >= 15 and others_min <= 5:
        return 'yes' if random.random() < 0.4 else 'no'
    if score >= 18:
        return 'yes' if random.random() < 0.25 else 'no'

    return 'no'


def ai_bid(state: dict, who: str) -> str:
    caps = _caps(state)
    hand = state['hands'][who]

    # Aussteigen verboten (< 6 Punkte oder letzte Runde gepasst) → spielen
    if not can_pass(state, who):
        return 'play'

    if not caps['smart_bid']:
        return 'play' if random.random() < 0.5 else 'pass'

    trump = state.get('trump')
    aces = sum(1 for c in hand if rank(c) == 'A')
    high = sum(1 for c in hand if rval(c) >= 5)
    trump_cards = sum(1 for c in hand if suit(c) == trump) if trump else 0

    if aces >= 1:
        return 'play'
    if high >= 2:
        return 'play'
    if trump_cards >= 1 and high >= 1:
        return 'play'

    if caps['score_aware']:
        score = state['scores'][who]
        if score >= 15 and high >= 1:
            return 'play'
        if score <= 3:
            return 'pass'

    if caps.get('aggressive_bid'):
        hand_str = sum(rval(c) for c in hand)
        if trump_cards >= 1 and hand_str >= 8:
            return 'play'
        score = state['scores'][who]
        is_blind = state.get('herz_blind', False)
        mult = 4 if is_blind else (2 if trump == 'h' else 1)
        target = score // mult if mult else score
        if target <= 2 and high >= 1:
            return 'play'

    return 'pass'


def ai_exchange(state: dict, who: str) -> list[str]:
    caps = _caps(state)
    hand = state['hands'][who]
    trump = state['trump']

    non_trump = [c for c in hand if suit(c) != trump]
    if not caps.get('smart_play', False):
        weak = sorted(non_trump, key=rval)
        count = min(len(weak), random.randint(0, 2))
        return weak[:count]

    is_blind = state.get('herz_blind', False)
    mult = 4 if is_blind else (2 if trump == 'h' else 1)
    score = state['scores'][who]
    target = score // mult if mult else score

    if caps.get('score_aware') and target <= 2:
        # Brauche wenige Stiche → nur ganz schwache tauschen, starke behalten
        weak = sorted([c for c in non_trump if rval(c) < 2], key=rval)
        return weak[:2]

    if caps.get('score_aware') and target >= 4:
        # Brauche viele Stiche → aggressiv tauschen, alles Schwache weg
        weak = sorted([c for c in non_trump if rval(c) < 5], key=rval)
        return weak[:3]

    if caps.get('card_counting'):
        played = set(state.get('played', []))
        def card_strength(c):
            s = suit(c)
            higher_remaining = sum(1 for r in RANKS
                                   if RANK_VAL[r] > RANK_VAL[rank(c)]
                                   and s + r not in played)
            return rval(c) - higher_remaining
        weak = sorted([c for c in non_trump if card_strength(c) < 2], key=card_strength)
        return weak[:3]

    weak = sorted([c for c in non_trump if rval(c) < 4], key=rval)
    return weak[:3]


def ai_trump(state: dict, who: str) -> str:
    caps = _caps(state)
    hand = state['hands'][who]

    if not caps['smart_trump']:
        suits_in = list(set(suit(c) for c in hand))
        return random.choice(suits_in) if suits_in else random.choice(SUITS)

    best_suit = 'h'
    best_val = -1
    for s in SUITS:
        cards = [c for c in hand if suit(c) == s]
        val = sum(rval(c) for c in cards) + len(cards) * 4
        if val > best_val:
            best_val = val
            best_suit = s

    # Schwache Hand: 2 verschiedene Farben, keine hohe Karte → "nächste Karte"
    suits_in = set(suit(c) for c in hand)
    high = sum(1 for c in hand if rval(c) >= 5)
    if len(suits_in) >= 2 and high == 0 and best_val < 8:
        return 'next'

    # Score-bewusst: Herz bevorzugen wenn Score durch 2 teilbar und Herz-Karten vorhanden
    if caps.get('score_aware'):
        score = state['scores'][who]
        herz_cards = [c for c in hand if suit(c) == 'h']
        herz_val = sum(rval(c) for c in herz_cards) + len(herz_cards) * 4
        # Genau passend mit ×2? Herz wählen!
        if score % 2 == 0 and score <= 10 and herz_val >= best_val * 0.7:
            return 'h'
        # Hoher Score → aggressiv, Herz für ×2
        if score >= 12 and herz_val >= 6:
            return 'h'

    return best_suit


def ai_play(state: dict, who: str) -> str:
    caps = _caps(state)
    legal = legal_cards(state, who)

    if len(legal) == 1:
        return legal[0]

    if who not in state['active']:
        return min(legal, key=rval)

    if not caps['smart_play']:
        return random.choice(legal)

    trump = state['trump']

    if caps['score_aware']:
        score = state['scores'][who]
        is_hearts = trump == 'h'
        is_blind = state.get('herz_blind', False)
        mult = 4 if is_blind else (2 if is_hearts else 1)
        my_tricks = state['tricks'][who]
        target = score // mult if mult else score
        if target > 0 and my_tricks >= target:
            return _try_lose(legal, trump)

    if not state['table']:
        return _ai_lead(legal, trump, state)
    return _ai_follow(state, legal, trump)


def _try_lose(legal: list[str], trump: str) -> str:
    non_trump = [c for c in legal if suit(c) != trump]
    pool = non_trump if non_trump else legal
    return min(pool, key=rval)


def _ai_lead(legal: list[str], trump: str, state: dict | None = None) -> str:
    caps = _caps(state) if state else {}

    aces = [c for c in legal if rank(c) == 'A' and suit(c) != trump]
    if aces:
        return aces[0]

    if caps.get('optimal_lead') and state:
        played = set(state.get('played', []))
        best_card = None
        best_score = -1
        for c in legal:
            s = suit(c)
            if s == trump:
                continue
            remaining = [r for r in RANKS if s + r not in played and s + r != c]
            higher = sum(1 for r in remaining if RANK_VAL[r] > RANK_VAL[rank(c)])
            score = rval(c) * 10 - higher * 5
            if score > best_score:
                best_score = score
                best_card = c
        if best_card and best_score > 20:
            return best_card

    trumps = [c for c in legal if suit(c) == trump]
    if len(trumps) >= 3:
        return max(trumps, key=rval)

    non_trump = [c for c in legal if suit(c) != trump]
    if non_trump:
        return max(non_trump, key=rval)

    return max(legal, key=rval)


def _ai_follow(state: dict, legal: list[str], trump: str) -> str:
    table = state['table']
    lead_s = suit(table[0]['card'])
    caps = _caps(state)

    def power(c):
        if suit(c) == trump:
            return (2, rval(c))
        if suit(c) == lead_s:
            return (1, rval(c))
        return (0, rval(c))

    best_power = max(power(t['card']) for t in table)
    winners = [c for c in legal if power(c) > best_power]
    losers = [c for c in legal if power(c) <= best_power]

    if winners:
        if caps.get('card_counting') and len(table) < 2:
            played = set(state.get('played', []))
            for w in sorted(winners, key=rval):
                s = suit(w)
                higher_out = [s + r for r in RANKS
                              if RANK_VAL[r] > RANK_VAL[rank(w)]
                              and s + r not in played
                              and not any(t['card'] == s + r for t in table)]
                if not higher_out:
                    return w
        return min(winners, key=rval)

    nt = [c for c in losers if suit(c) != trump]
    return min(nt, key=rval) if nt else min(losers, key=rval)


# ── Public View ────────────────────────────────────────
def public_view(state: dict) -> dict:
    v = copy.deepcopy(state)
    if state.get('status') == 'herz_blind_ask':
        for p in PLAYERS:
            if 'hands' in v and p in v['hands']:
                v['hands'][p] = len(state['hands'][p]) if p != 'p' else []
    else:
        for p in ('a1', 'a2'):
            if 'hands' in v and p in v['hands']:
                v['hands'][p] = len(state['hands'][p])
    v.pop('seed', None)
    v.pop('extra_cards', None)
    v.pop('dealt_full', None)
    v.pop('exchange_deck', None)
    if state.get('status') == 'playing' and state.get('turn') == 'p':
        v['legal'] = legal_cards(state, 'p')
    if state.get('status') == 'bidding' and state.get('bid_turn') == 'p':
        v['can_pass'] = can_pass(state, 'p')
    return v
