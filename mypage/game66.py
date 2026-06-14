"""66 / Schnapsen — server-autoritatives Regelwerk + heuristische KI.

20-Karten-Variante (ohne 9er): A, 10(=T), K, D(=Q), B(=J) in 4 Farben.
Kartenwerte: A=11, T=10, K=4, Q=3, J=2  → 120 Punkte gesamt.
Je 5 Karten Hand, 10 Karten Talon (unterste Karte = aufgedeckter Trumpf).
Ziel: 66 Augen ausmelden. Match (Bummerl) bis 7 Spielpunkte.

Der State ist ein reines dict (JSON-serialisierbar) und enthält die *volle*
Information (auch KI-Hand + verdeckter Talon). Für den Client liefert
``public_view`` eine redigierte Sicht ohne Geheiminfos (Anti-Cheat).

Spieler-IDs: 'p' = menschlicher Spieler, 'a' = KI.
"""
from __future__ import annotations

import copy
import random

SUITS = ['c', 'd', 'h', 's']          # clubs, diamonds, hearts, spades
RANKS = ['A', 'T', 'K', 'Q', 'J']     # Ass, Zehn, König, Dame, Bube
VALUES = {'A': 11, 'T': 10, 'K': 4, 'Q': 3, 'J': 2}
# Farb-Rangfolge fürs Auslosen (Kreuz < Karo < Herz < Pik)
SUIT_ORDER = {'c': 0, 'd': 1, 'h': 2, 's': 3}
WIN_SCORE = 66                         # Augen zum Ausmelden
MATCH_SCORE = 7                        # Spielpunkte (Bummerl) zum Matchsieg
LOG_MAX = 40

STATE_VERSION = 1


def suit(card: str) -> str:
    return card[1]


def rank(card: str) -> str:
    return card[0]


def val(card: str) -> int:
    return VALUES[card[0]]


def other(who: str) -> str:
    return 'a' if who == 'p' else 'p'


def full_deck() -> list:
    return [r + s for s in SUITS for r in RANKS]


# ── State-Aufbau ──────────────────────────────────────────────────────────────

RULESETS = ('standard', 'oma')


def new_match(first_dealer: str | None = None, rng: random.Random | None = None,
              rules: str = 'standard') -> dict:
    """Neuen Match-State (Bummerl) erzeugen und erste Partie austeilen.

    rules='standard': mit vorzeitigem Ausmelden bei 66.
    rules='oma' ("Andys Oma"): kein Ausmelden — erst zählen, wenn alle Karten
    weg sind; Sieger hat 66+, sonst gewinnt der letzte Stich.
    """
    rng = rng or random.Random()
    state = {
        'v': STATE_VERSION,
        'rules': rules if rules in RULESETS else 'standard',
        'bummerl': {'p': 0, 'a': 0},
        'deal_no': 0,
        'status': 'playing',
        'log': [],
    }
    if first_dealer:
        state['cut'] = None
        dealer = first_dealer
    else:
        # Auslosen: jeder zieht eine Karte, die höhere führt aus (Geber ist der andere)
        cut = _cut_for_lead(rng)
        state['cut'] = cut
        dealer = other(cut['leader'])
    _new_deal(state, dealer, rng)
    return state


def _cut_key(card: str) -> tuple:
    return (VALUES[rank(card)], SUIT_ORDER[suit(card)])


def _cut_for_lead(rng: random.Random) -> dict:
    """Jeder zieht eine Karte; höhere Karte (bei Gleichrang höhere Farbe) führt aus."""
    deck = full_deck()
    rng.shuffle(deck)
    pc, ac = deck[0], deck[1]
    leader = 'p' if _cut_key(pc) > _cut_key(ac) else 'a'
    return {'p': pc, 'a': ac, 'leader': leader}


def _new_deal(state: dict, dealer: str, rng: random.Random) -> None:
    deck = full_deck()
    rng.shuffle(deck)
    state['deal_no'] = state.get('deal_no', 0) + 1
    state['hands'] = {'p': deck[0:5], 'a': deck[5:10]}
    state['stock'] = deck[10:20]               # stock[-1] = aufgedeckter Trumpf
    state['trump'] = suit(state['stock'][-1])
    state['won'] = {'p': [], 'a': []}
    state['trick_pts'] = {'p': 0, 'a': 0}
    state['marriage_pts'] = {'p': 0, 'a': 0}
    state['has_trick'] = {'p': False, 'a': False}
    state['melds'] = {'p': [], 'a': []}        # angesagte Hochzeits-Farben (Anzeige)
    state['table'] = []                        # [{'who','card'}, ...]
    state['closed'] = False
    state['closed_by'] = None
    state['closed_snap'] = 0                   # Augen des Gegners beim Zudrehen
    state['closed_opp_trick'] = False          # hatte Gegner beim Zudrehen schon Stich?
    state['phase2'] = False                    # Farb-/Stichzwang aktiv?
    state['dealer'] = dealer
    lead = other(dealer)                       # Vorhand (Nichtgeber) spielt aus
    state['lead'] = lead
    state['turn'] = lead
    state['last_trick_winner'] = None
    state['status'] = 'playing'
    state['result'] = None
    _log(state, 'deal', f'Partie {state["deal_no"]} — Trumpf {state["trump"]}',
         f'Deal {state["deal_no"]} — trump {state["trump"]}')


# ── Punkte ────────────────────────────────────────────────────────────────────

def usable(state: dict, who: str) -> int:
    """Augen, die zum Ausmelden zählen — Hochzeiten erst ab erstem Stich."""
    pts = state['trick_pts'][who]
    if state['has_trick'][who]:
        pts += state['marriage_pts'][who]
    return pts


# ── Stich-Logik ───────────────────────────────────────────────────────────────

def _beats(follow: str, led: str, trump: str) -> bool:
    """Schlägt die nachgezogene Karte die ausgespielte?"""
    if suit(follow) == suit(led):
        return val(follow) > val(led)
    return suit(follow) == trump and suit(led) != trump


def _legal_follow(state: dict, hand: list) -> list:
    """Erlaubte Karten beim Nachspielen.

    Phase 1 (Talon offen): frei. Phase 2 (zugedreht/Talon leer): Farbzwang,
    Stichzwang in der Farbe, sonst Trumpfzwang, sonst frei.
    """
    if not state['phase2']:
        return list(hand)
    led = state['table'][0]['card']
    ls = suit(led)
    trump = state['trump']
    same = [c for c in hand if suit(c) == ls]
    if same:
        higher = [c for c in same if val(c) > val(led)]
        return higher or same
    trumps = [c for c in hand if suit(c) == trump]
    return trumps or list(hand)


def _trick_winner(lead_card: str, follow_card: str, trump: str) -> str:
    """'lead' oder 'follow' — wer den Stich gewinnt."""
    return 'follow' if _beats(follow_card, lead_card, trump) else 'lead'


# ── Aktionen anwenden ─────────────────────────────────────────────────────────

class IllegalMove(ValueError):
    pass


def apply_action(state: dict, who: str, action: dict) -> dict:
    """Eine Aktion eines Spielers anwenden. Wirft IllegalMove bei Regelverstoß."""
    typ = action.get('type')
    if typ == 'next':
        return _start_next_deal(state)
    if state['status'] != 'playing':
        raise IllegalMove('Spiel nicht aktiv')
    if state['turn'] != who:
        raise IllegalMove('Nicht am Zug')

    if typ == 'exchange':
        _do_exchange(state, who)
    elif typ == 'close':
        _do_close(state, who)
    elif typ == 'play':
        _do_play(state, who, action)
    else:
        raise IllegalMove(f'Unbekannte Aktion: {typ}')
    return state


def _do_exchange(state: dict, who: str) -> None:
    if state['table']:
        raise IllegalMove('Tausch nur beim Ausspielen')
    if state['phase2'] or len(state['stock']) < 2:
        raise IllegalMove('Tausch nicht mehr möglich')
    trump = state['trump']
    jack = 'J' + trump
    hand = state['hands'][who]
    if jack not in hand:
        raise IllegalMove('Trumpf-Bube nicht auf der Hand')
    upcard = state['stock'][-1]
    if upcard == jack:
        raise IllegalMove('Nichts zu tauschen')
    hand.remove(jack)
    hand.append(upcard)
    state['stock'][-1] = jack
    _log(state, 'exchange', f'{_name(who)}: Trumpf-Bube getauscht',
         f'{_name(who, True)}: trump jack exchanged', who)
    _capture(state)


def _do_close(state: dict, who: str) -> None:
    if state['table']:
        raise IllegalMove('Zudrehen nur beim Ausspielen')
    if state['phase2'] or not state['stock']:
        raise IllegalMove('Talon kann nicht zugedreht werden')
    opp = other(who)
    state['closed'] = True
    state['closed_by'] = who
    state['phase2'] = True
    state['closed_snap'] = usable(state, opp)
    state['closed_opp_trick'] = state['has_trick'][opp]
    _log(state, 'close', f'{_name(who)} dreht den Talon zu',
         f'{_name(who, True)} closes the talon', who)
    _capture(state)


def _do_play(state: dict, who: str, action: dict) -> None:
    hand = state['hands'][who]
    card = action.get('card')
    if card not in hand:
        raise IllegalMove('Karte nicht auf der Hand')
    leading = not state['table']

    if leading:
        if action.get('marry'):
            _announce_marriage(state, who, card)
            if state['status'] != 'playing':
                return  # mit Ansage ausgemeldet
    else:
        if card not in _legal_follow(state, hand):
            raise IllegalMove('Karte nicht erlaubt (Farb-/Stichzwang)')

    hand.remove(card)
    state['table'].append({'who': who, 'card': card})
    _capture(state)  # Karte(n) auf dem Tisch sichtbar machen (bei 2 = voller Stich)
    if len(state['table']) == 2:
        _resolve_trick(state)
    else:
        state['turn'] = other(who)


def _announce_marriage(state: dict, who: str, card: str) -> None:
    s = suit(card)
    if rank(card) not in ('K', 'Q'):
        raise IllegalMove('Hochzeit nur mit König oder Dame ansagen')
    hand = state['hands'][who]
    if ('K' + s) not in hand or ('Q' + s) not in hand:
        raise IllegalMove('König und Dame nötig')
    if s in state['melds'][who]:
        raise IllegalMove('Hochzeit bereits angesagt')
    bonus = 40 if s == state['trump'] else 20
    state['marriage_pts'][who] += bonus
    state['melds'][who].append(s)
    _log(state, 'marriage', f'{_name(who)} sagt {bonus} an ({s})',
         f'{_name(who, True)} announces {bonus} ({s})', who)
    _capture(state)
    # Standard: Hochzeit kann sofort ausmelden. Oma: kein vorzeitiges Ende.
    if state.get('rules') != 'oma' and usable(state, who) >= WIN_SCORE:
        _finish_deal(state, who, 'made_66')


def _resolve_trick(state: dict) -> None:
    lc = state['table'][0]
    fc = state['table'][1]
    trump = state['trump']
    winner = lc['who'] if _trick_winner(lc['card'], fc['card'], trump) == 'lead' else fc['who']
    loser = other(winner)
    pts = val(lc['card']) + val(fc['card'])
    state['won'][winner] += [lc['card'], fc['card']]
    state['trick_pts'][winner] += pts
    state['has_trick'][winner] = True
    state['last_trick_winner'] = winner
    state['table'] = []
    _log(state, 'trick', f'{_name(winner)} gewinnt den Stich (+{pts})',
         f'{_name(winner, True)} wins the trick (+{pts})', winner)

    # Nachziehen (nur Phase 1): Stichgewinner zuerst
    if not state['phase2'] and state['stock']:
        state['hands'][winner].append(state['stock'].pop(0))
        state['hands'][loser].append(state['stock'].pop(0))
        if not state['stock']:
            state['phase2'] = True
            _log(state, 'talon', 'Talon erschöpft — ab jetzt Farbzwang',
                 'Talon exhausted — follow suit now')

    state['lead'] = winner
    state['turn'] = winner
    _check_deal_end(state)
    _capture(state)  # Tisch abgeräumt, Punkte/Nachzug aktualisiert


# ── Partie-Ende & Wertung ─────────────────────────────────────────────────────

def _tier(loser_augen: int) -> int:
    """Spielpunkte nach Augen des Verlierers: 0 → 3 (schwarz), <33 → 2 (Schneider), sonst 1."""
    if loser_augen <= 0:
        return 3
    if loser_augen < 33:
        return 2
    return 1


def _more_augen(state: dict) -> str:
    up, ua = usable(state, 'p'), usable(state, 'a')
    if up > ua:
        return 'p'
    if ua > up:
        return 'a'
    return state['last_trick_winner']


def _check_deal_end(state: dict) -> None:
    if state['status'] != 'playing':
        return
    if state['closed']:
        closer = state['closed_by']
        opp = other(closer)
        if usable(state, closer) >= WIN_SCORE:
            _finish_deal(state, closer, 'closed_made')
        elif usable(state, opp) >= WIN_SCORE or _hands_empty(state):
            _finish_deal(state, opp, 'closed_failed')
        return

    if state.get('rules') == 'oma':
        # "Andys Oma": kein vorzeitiges Ausmelden — erst zählen, wenn alle Karten weg sind
        if _hands_empty(state):
            p_ok = usable(state, 'p') >= WIN_SCORE
            a_ok = usable(state, 'a') >= WIN_SCORE
            if p_ok or a_ok:
                winner = _more_augen(state) if (p_ok and a_ok) else ('p' if p_ok else 'a')
                _finish_deal(state, winner, 'oma_made')
            else:  # niemand 66 → der letzte Stich gewinnt
                _finish_deal(state, state['last_trick_winner'], 'oma_lasttrick')
        return

    # Standard: sofort ausmelden bei 66
    for w in ('p', 'a'):
        if usable(state, w) >= WIN_SCORE:
            _finish_deal(state, w, 'made_66')
            return
    if _hands_empty(state):
        _finish_deal(state, state['last_trick_winner'], 'last_trick')


def _hands_empty(state: dict) -> bool:
    return not state['hands']['p'] and not state['hands']['a']


def _finish_deal(state: dict, winner: str, reason: str) -> None:
    loser = other(winner)
    rules = state.get('rules', 'standard')
    if reason == 'closed_failed':
        # Zudreher hat 66 verfehlt. Oma: pauschal 3. Standard: 2, bzw. 3 ohne Gegner-Stich.
        gp = 3 if rules == 'oma' else (2 if state['closed_opp_trick'] else 3)
    elif reason == 'last_trick':
        gp = 1
    elif reason == 'closed_made':
        if rules == 'oma':
            gp = _tier(usable(state, loser))
        else:  # Standard: Wertung nach Gegnerstand beim Zudrehen (Schnappschuss)
            if not state['closed_opp_trick']:
                gp = 3
            elif state['closed_snap'] < 33:
                gp = 2
            else:
                gp = 1
    else:  # made_66, oma_made, oma_lasttrick → nach Augen des Verlierers
        gp = _tier(usable(state, loser))

    state['bummerl'][winner] += gp
    state['result'] = {
        'winner': winner,
        'gp': gp,
        'reason': reason,
        'pts': {'p': usable(state, 'p'), 'a': usable(state, 'a')},
    }
    state['status'] = 'deal_over'
    _log(state, 'deal_end', f'{_name(winner)} gewinnt die Partie (+{gp})',
         f'{_name(winner, True)} wins the deal (+{gp})', winner)
    if state['bummerl'][winner] >= MATCH_SCORE:
        state['status'] = 'match_over'
        _log(state, 'match_end', f'{_name(winner)} gewinnt das Match!',
             f'{_name(winner, True)} wins the match!', winner)


def _start_next_deal(state: dict) -> dict:
    if state['status'] != 'deal_over':
        raise IllegalMove('Partie noch nicht beendet')
    loser = other(state['result']['winner'])
    state['cut'] = None  # Auslosen war nur für die erste Partie
    _new_deal(state, dealer=loser, rng=random.Random())
    return state


# ── Legale Aktionen (für Client/UI) ───────────────────────────────────────────

def legal_actions(state: dict, who: str) -> list:
    if state['status'] != 'playing' or state['turn'] != who:
        return []
    hand = state['hands'][who]
    trump = state['trump']
    acts = []
    if not state['table']:  # Ausspielen
        if not state['phase2']:
            jack = 'J' + trump
            if len(state['stock']) >= 2 and jack in hand and state['stock'][-1] != jack:
                acts.append({'type': 'exchange'})
            if state['stock']:
                acts.append({'type': 'close'})
        for s in SUITS:
            if ('K' + s) in hand and ('Q' + s) in hand and s not in state['melds'][who]:
                acts.append({'type': 'play', 'card': 'Q' + s, 'marry': True})
                acts.append({'type': 'play', 'card': 'K' + s, 'marry': True})
        for c in hand:
            acts.append({'type': 'play', 'card': c})
    else:               # Nachspielen
        for c in _legal_follow(state, hand):
            acts.append({'type': 'play', 'card': c})
    return acts


# ── KI ────────────────────────────────────────────────────────────────────────

def _capture(state: dict) -> None:
    """Zwischenbild für die Animation festhalten (nur wenn ein Sammler aktiv ist)."""
    cap = state.get('_cap')
    if cap is not None:
        cap.append(public_view(state))


def _dedupe(frames: list, state: dict) -> list:
    out = []
    for f in frames:
        if not out or out[-1] != f:
            out.append(f)
    final = public_view(state)
    if not out or out[-1] != final:
        out.append(final)
    return out


def apply_player_frames(state: dict, action: dict) -> list:
    """Spielerzug + KI anwenden und die Folge der sichtbaren Zwischenbilder liefern.

    Der Client spielt die Frames mit kurzen Pausen ab, sodass ein voller Stich
    (zwei Karten auf dem Tisch) sichtbar liegen bleibt, bevor abgeräumt wird.
    """
    frames: list = []
    state['_cap'] = frames
    try:
        apply_action(state, 'p', action)
        ai_run(state)
    finally:
        state.pop('_cap', None)
    return _dedupe(frames, state)


def deal_frames(state: dict) -> list:
    """Nur die KI laufen lassen (z. B. KI-Eröffnung) und Frames sammeln."""
    frames: list = []
    state['_cap'] = frames
    try:
        ai_run(state)
    finally:
        state.pop('_cap', None)
    return _dedupe(frames, state)


def ai_run(state: dict) -> None:
    """Lässt die KI ziehen, solange sie am Zug ist (auch Folgestiche)."""
    guard = 0
    while state['status'] == 'playing' and state['turn'] == 'a':
        guard += 1
        if guard > 50:
            raise RuntimeError('KI-Endlosschleife')
        apply_action(state, 'a', _ai_choose(state))


def _ai_choose(state: dict) -> dict:
    return _ai_lead(state) if not state['table'] else _ai_follow(state)


def _ai_lead(state: dict) -> dict:
    hand = state['hands']['a']
    trump = state['trump']
    jack = 'J' + trump

    # 1) Trumpf-Bube tauschen, wenn die offene Karte wertvoller ist
    if (not state['phase2'] and len(state['stock']) >= 2
            and jack in hand and val(state['stock'][-1]) > VALUES['J']):
        return {'type': 'exchange'}

    # 2) Hochzeit ansagen (Trumpf 40 bevorzugt)
    marriages = [s for s in SUITS
                 if ('K' + s) in hand and ('Q' + s) in hand and s not in state['melds']['a']]
    if marriages:
        marriages.sort(key=lambda s: 40 if s == trump else 20, reverse=True)
        s = marriages[0]
        return {'type': 'play', 'card': 'Q' + s, 'marry': True}

    # 3) Zudrehen, wenn der Sieg realistisch ist
    if not state['phase2'] and state['stock'] and _ai_should_close(state):
        return {'type': 'close'}

    # 4) Normal ausspielen: niedrige Nicht-Trumpf-Karte abwerfen
    return {'type': 'play', 'card': _ai_lead_card(state)}


def _ai_should_close(state: dict) -> bool:
    hand = state['hands']['a']
    trump = state['trump']
    extra = sum(val(c) for c in hand if rank(c) == 'A')
    extra += sum(val(c) for c in hand if suit(c) == trump and rank(c) in ('A', 'T'))
    return usable(state, 'a') >= 40 and usable(state, 'a') + extra >= 70


def _ai_lead_card(state: dict) -> str:
    hand = state['hands']['a']
    trump = state['trump']
    nontrump = [c for c in hand if suit(c) != trump]
    pool = nontrump or hand
    return min(pool, key=val)


def _ai_follow(state: dict) -> dict:
    hand = state['hands']['a']
    trump = state['trump']
    led = state['table'][0]['card']
    legal = _legal_follow(state, hand) if state['phase2'] else list(hand)
    winners = [c for c in legal if _beats(c, led, trump)]
    if winners:
        cheapest = min(winners, key=val)
        # Stich nehmen, wenn er sich lohnt oder der Sieg billig ist
        if val(led) >= 10 or val(cheapest) <= VALUES['K']:
            return {'type': 'play', 'card': cheapest}
    nontrump = [c for c in legal if suit(c) != trump]
    pool = nontrump or legal
    return {'type': 'play', 'card': min(pool, key=val)}


# ── Client-Sicht (ohne Geheiminformation) ─────────────────────────────────────

def public_view(state: dict) -> dict:
    """Redigierte Sicht für den Browser — keine KI-Hand, kein verdeckter Talon."""
    return {
        'v': state['v'],
        'rules': state.get('rules', 'standard'),
        'cut': state.get('cut'),
        'hand': list(state['hands']['p']),
        'ai_count': len(state['hands']['a']),
        'stock_count': len(state['stock']),
        'trump': state['trump'],
        'trump_card': state['stock'][-1] if state['stock'] else None,
        'table': list(state['table']),
        'pts': {'p': usable(state, 'p'), 'a': usable(state, 'a')},
        'tricks': {'p': len(state['won']['p']) // 2, 'a': len(state['won']['a']) // 2},
        'melds': {'p': list(state['melds']['p']), 'a': list(state['melds']['a'])},
        'closed': state['closed'],
        'closed_by': state['closed_by'],
        'phase2': state['phase2'],
        'turn': state['turn'],
        'lead': state['lead'],
        'dealer': state['dealer'],
        'deal_no': state['deal_no'],
        'status': state['status'],
        'result': state['result'],
        'bummerl': dict(state['bummerl']),
        'legal': legal_actions(state, 'p'),
        'log': state['log'][-LOG_MAX:],
    }


# ── Logging ───────────────────────────────────────────────────────────────────

def _name(who: str, en: bool = False) -> str:
    if en:
        return 'AI' if who == 'a' else 'You'
    return 'KI' if who == 'a' else 'Du'


def _log(state: dict, code: str, de: str, en: str, who: str = '') -> None:
    state.setdefault('log', []).append({'code': code, 'de': de, 'en': en, 'who': who})
    if len(state['log']) > LOG_MAX * 2:
        del state['log'][:-LOG_MAX]


# ── Validierung beim Laden (gegen manipulierte/korrupte Saves) ────────────────

def is_valid_state(state) -> bool:
    if not isinstance(state, dict) or state.get('v') != STATE_VERSION:
        return False
    try:
        for key in ('hands', 'stock', 'trump', 'bummerl', 'status', 'turn'):
            if key not in state:
                return False
        deck = set(full_deck())
        seen = []
        seen += state['hands']['p'] + state['hands']['a'] + state['stock']
        seen += state['won']['p'] + state['won']['a']
        seen += [t['card'] for t in state['table']]
        return all(c in deck for c in seen) and len(seen) == 20 == len(set(seen))
    except (KeyError, TypeError):
        return False
