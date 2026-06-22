"""Chicago (Tschigg) — Würfelspiel für 1 Mensch + 2–3 KI.

Aufbau wie die anderen Mitglieder-Spiele: server-autoritativer, seed-deterministischer
Zustand (Würfeln über game_dice), KI-Schritte einzeln abrufbar (animationsgetrieben).

── Digitale Modell-Entscheidungen (bewusst, ggf. anpassbar) ──────────────────────
* 3 Würfel, pro Zug bis zu 3 Würfe. Der VORLEGER bestimmt mit seiner Wurfzahl das
  Wurf-Limit der Runde (steht er nach Wurf k, dürfen alle nur k-mal werfen) und legt
  beim Stehenbleiben die WERTUNG fest: Einser/Sechser = 100/60 ("gross"), 1/6
  ("klein") oder "ohne1" (6→60, die 1 zählt nur 1 — Chicago/drei 1er bleibt davon
  ausgenommen), sowie Richtung "hoch" (höher gewinnt) oder "tief" (tiefer gewinnt).
* Bewertung eines Wurfs = Tupel der Würfelwerte (gross: 1→100, 6→60, sonst Augen;
  klein: 1→1, 6→6, sonst Augen), absteigend sortiert, lexikografisch verglichen.
  Drei Einser = "Chicago". "Fish" (keine 1, keine 6) ergibt sich automatisch als
  niedrigstes Tupel.
* "Mit ist Shit": Gleichstand schlägt nicht — bei Gleichstand ist der SPÄTERE Spieler
  in der Reihe "tief". Umgesetzt über Tie-Break = spätere Position.
* Bierfilze (Variante „Deutsch", n+1): Phase 1 bekommt pro Runde der SCHLECHTESTE
  einen Filz, bis alle n+1 verteilt sind; er legt die nächste Runde vor. Phase 2
  („Runterspielen") spielen nur Spieler mit ≥1 Filz; der BESTE darf je Runde einen
  Filz abwerfen; wer 0 Filze hat, ist raus (gerettet). Letzter mit Filz(en) verliert.
* Becher-Tricks: zwei 6er können (Wahl-Aktion 'convert6') in eine 1 umgewandelt
  werden — eine 6 wird zur gehaltenen 1, die andere kommt zurück in den Becher und
  muss neu geworfen werden (nur mit verbleibendem Wurf). Drei 6er werden automatisch
  zu zwei gehaltenen 1ern, der dritte Würfel kommt zurück in den Becher (bzw. bleibt
  6, falls kein Wurf mehr übrig). "Chicago" (drei 1er) in einem Wurf nimmt den
  Spieler sofort gerettet aus dem Spiel.
"""
from __future__ import annotations

import itertools
import random

import game_dice


class IllegalMove(Exception):
    pass


# ── Bewertung ────────────────────────────────────────────────────────────────

def _die_value(d: int, valuation: str) -> int:
    if valuation == 'klein':
        return d                       # 1→1, 6→6, sonst Augen
    if valuation == 'ohne1':
        return 60 if d == 6 else d     # „Ohne 1": 6→60, 1 zählt nur 1, sonst Augen
    if d == 1:                         # „gross": 1→100, 6→60, sonst Augen
        return 100
    if d == 6:
        return 60
    return d


def roll_key(dice: list[int], valuation: str) -> tuple:
    """Vergleichsschlüssel: Werte absteigend, lexikografisch vergleichbar."""
    return tuple(sorted((_die_value(d, valuation) for d in dice), reverse=True))


def is_chicago(dice: list[int]) -> bool:
    return sorted(dice) == [1, 1, 1]


def is_fish(dice: list[int]) -> bool:
    return all(d not in (1, 6) for d in dice)


def label(dice: list[int], valuation: str, rolls: int) -> str:
    if is_chicago(dice):
        return f'Chicago auf {rolls}'
    total = sum(_die_value(d, valuation) for d in dice)
    return f'{total} auf {rolls}'


# ── Spiel erstellen ──────────────────────────────────────────────────────────

def new_game(level: str = 'medium', humans: int = 1, ai: int = 2,
             names: dict | None = None, seed: int | None = None) -> dict:
    if seed is None:
        seed = random.randint(0, 2 ** 31)
    if level not in ('easy', 'medium', 'hard'):
        level = 'medium'
    # 1–3 Menschen, 0–2 KI, mind. 2 und max 5 Spieler gesamt
    humans = max(1, min(3, int(humans or 1)))
    ai = max(0, min(2, int(ai or 0)))
    if humans + ai < 2:
        ai = 2 - humans
    if humans + ai > 5:
        ai = 5 - humans
    human_ids = ['p', 'h2', 'h3'][:humans]
    ai_ids = [f'a{i}' for i in range(1, ai + 1)]
    players = human_ids + ai_ids       # Sitzreihenfolge: Menschen, dann KI
    # Namen der menschlichen Spieler (bereinigt, leer erlaubt → Client zeigt
    # „Du"/„Spieler N" und wählt 2./3. Person). Statistik bleibt nur für 'p'.
    src = names or {}
    pnames = {hid: str(src.get(hid, '') or '').strip()[:20] for hid in human_ids}
    rng = random.Random(seed)
    opener = rng.choice(players)
    state = {
        'status': 'opener_roll',
        'phase': 1,
        'round_no': 1,
        'level': level,
        'opponents': ai,
        'humans': human_ids,
        'names': pnames,
        'seed': seed,
        'roll_step': 0,
        'players': players,           # Sitzreihenfolge
        'active': players[:],         # noch im Spiel
        'mats': {p: 0 for p in players},
        'mats_target': len(players) + 1,   # n+1
        'opener': opener,
        'turn': opener,
        'order': _round_order(players, players, opener),
        'order_pos': 0,
        'valuation': 'gross',
        'direction': 'hoch',
        'roll_cap': 3,
        'dice': [0, 0, 0],
        'held': [False, False, False],
        'locked': [False, False, False],   # über einen Wurf gehalten → fix
        'rolls_used': 0,
        'results': {},                # pid -> {key,label,chic,rolls}
        'tief': None,                 # aktuell „tief" (zu schlagen)
        'round_loser': None,
        'round_winner': None,
        'winner': None,               # Sieger des Spiels = gerettet; Verlierer = loser
        'loser': None,
        'last': None,
    }
    return state


def _round_order(players: list[str], active: list[str], opener: str) -> list[str]:
    act = [p for p in players if p in active]
    i = act.index(opener)
    return act[i:] + act[:i]


# ── Würfeln / Stehenbleiben ──────────────────────────────────────────────────

def apply_action(state: dict, player: str, action: dict) -> None:
    if state['status'] in ('game_over',):
        raise IllegalMove('game over')
    t = action.get('type', '')
    if t == 'roll':
        _do_roll(state, player, action.get('held'))
    elif t == 'convert6':
        _do_convert6(state, player)
    elif t == 'stand':
        _do_stand(state, player, action)
    else:
        raise IllegalMove('unknown action')


def _do_roll(state: dict, player: str, held=None) -> None:
    if state['turn'] != player or state['status'] not in ('opener_roll', 'follower_roll'):
        raise IllegalMove('not your roll')
    if state['rolls_used'] >= state['roll_cap']:
        raise IllegalMove('no rolls left')
    # Halten NUR für 1 und 6 erlaubt (2–5 müssen zurück in den Becher); bereits über
    # einen Wurf gehaltene (locked) bleiben fix; zurückgelegte (0) immer neu werfen
    locked = state.get('locked', [False, False, False])
    if state['rolls_used'] > 0 and isinstance(held, list) and len(held) == 3:
        state['held'] = [(locked[i] or bool(held[i])) and state['dice'][i] in (1, 6)
                         for i in range(3)]
    mask = state['held'] if state['rolls_used'] > 0 else [False, False, False]
    state['roll_step'] += 1
    fresh = game_dice.roll(3, state['seed'], state['roll_step'])
    dice = state['dice'][:]
    for i in range(3):
        if not (state['rolls_used'] > 0 and mask[i]):
            dice[i] = fresh[i]
    state['dice'] = dice
    state['rolls_used'] += 1
    # Was bei diesem Wurf gehalten wurde, ist nun „gelegt" → nicht mehr abwählbar
    state['locked'] = [locked[i] or mask[i] for i in range(3)]
    state['last'] = {'type': 'roll', 'who': player, 'dice': dice[:], 'held': mask[:],
                     'rolls_used': state['rolls_used']}
    # Drei Sechser → automatisch zwei (gehaltene) Einser, dritter zurück in den Becher
    if dice.count(6) == 3:
        dice[0] = 1
        dice[1] = 1
        if state['rolls_used'] < state['roll_cap']:
            dice[2] = 0
            state['held'] = [True, True, False]
        else:
            dice[2] = 6                      # kein Wurf mehr → bleibt 6 (1,1,6)
            state['held'] = [True, True, True]
        state['dice'] = dice
        state['last'] = {'type': 'triple6', 'who': player, 'dice': dice[:]}


def _do_convert6(state: dict, player: str) -> None:
    """Zwei 6er → eine gehaltene 1; die andere 6 kommt zurück in den Becher (Neuwurf)."""
    if state['turn'] != player or state['status'] not in ('opener_roll', 'follower_roll'):
        raise IllegalMove('cannot convert')
    if state['rolls_used'] < 1 or state['rolls_used'] >= state['roll_cap']:
        raise IllegalMove('no roll left to return a die')
    dice = state['dice']
    six_idx = [i for i, d in enumerate(dice) if d == 6]
    if len(six_idx) != 2 or 0 in dice:
        raise IllegalMove('need exactly two sixes')
    a, b = six_idx
    dice[a] = 1
    state['held'][a] = True                  # eine 6 → 1, gehalten
    dice[b] = 0
    state['held'][b] = False                 # andere 6 → zurück (muss neu geworfen werden)
    state['dice'] = dice
    state['last'] = {'type': 'convert6', 'who': player, 'dice': dice[:]}


def _do_stand(state: dict, player: str, action: dict) -> None:
    if state['turn'] != player or state['status'] not in ('opener_roll', 'follower_roll'):
        raise IllegalMove('cannot stand')
    if state['rolls_used'] < 1:
        raise IllegalMove('must roll first')
    if 0 in state['dice']:
        raise IllegalMove('must reroll returned die')

    if state['status'] == 'opener_roll':
        val = action.get('valuation')
        direc = action.get('direction')
        state['valuation'] = val if val in ('gross', 'klein', 'ohne1') else 'gross'
        state['direction'] = direc if direc in ('hoch', 'tief') else 'hoch'
        state['roll_cap'] = state['rolls_used']      # Wurf-Limit der Runde

    res = {
        'key': roll_key(state['dice'], state['valuation']),
        'dice': state['dice'][:],
        'label': label(state['dice'], state['valuation'], state['rolls_used']),
        'chic': is_chicago(state['dice']),
        'rolls': state['rolls_used'],
    }
    state['results'][player] = res
    if res['chic'] and player == 'p':
        state['human_chicago'] = True        # für die „Chicago"-Statistik
    state['last'] = {'type': 'stand', 'who': player, 'result': res}

    state['order_pos'] += 1
    if state['order_pos'] >= len(state['order']):
        _resolve_round(state)
    else:
        _begin_turn(state, state['order'][state['order_pos']], opener=False)


def _begin_turn(state: dict, who: str, opener: bool) -> None:
    state['turn'] = who
    state['status'] = 'opener_roll' if opener else 'follower_roll'
    state['dice'] = [0, 0, 0]
    state['held'] = [False, False, False]
    state['locked'] = [False, False, False]
    state['rolls_used'] = 0


# ── Rundenauflösung ──────────────────────────────────────────────────────────

def _worst_player(state: dict) -> str:
    """Schlechtester gemäß Richtung; bei Gleichstand der SPÄTERE (Mit ist Shit)."""
    order = state['order']
    direc = state['direction']
    best = None
    for pos, pid in enumerate(order):
        r = state['results'].get(pid)
        if r is None or r['chic']:
            continue
        k = tuple(r['key'])              # JSON-Roundtrip macht aus Tuple eine Liste
        # „schlechter" = bei hoch kleiner Key, bei tief größerer Key
        worse_key = k if direc == 'hoch' else tuple(-x for x in k)
        # kleinster Wert = schlechtester; bei Gleichstand der SPÄTERE (Mit ist Shit) →
        # größere Position muss „schlechter" zählen, daher -pos
        cand = (worse_key, -pos)
        if best is None or cand < best[0]:
            best = (cand, pid)
    return best[1] if best else order[-1]


def _best_player(state: dict) -> str:
    order = state['order']
    direc = state['direction']
    best = None
    for pos, pid in enumerate(order):
        r = state['results'].get(pid)
        if r is None or r.get('chic'):
            continue
        k = tuple(r['key'])
        better_key = k if direc == 'hoch' else tuple(-x for x in k)
        cand = (better_key, -pos)        # größter better_key = bester; Tie → frühere pos
        if best is None or cand > best[0]:
            best = (cand, pid)
    return best[1] if best else order[0]


def _resolve_round(state: dict) -> None:
    # Chicago (drei 1er) = sofort gewonnen → Spieler ist gerettet und raus,
    # die Übrigen spielen die Runde regulär zu Ende ("Mit ist Shit").
    chics = [p for p, r in state['results'].items() if r['chic']]
    for p in chics:
        _remove_player(state, p, saved=True)

    # Bleibt nur noch ≤1 Spieler übrig (z. B. durch Chicago) → Spielende
    if len(state['active']) <= 1:
        _finish_game(state)
        return

    if state['phase'] == 1:
        loser = _worst_player(state)
        state['mats'][loser] = state['mats'].get(loser, 0) + 1
        state['round_loser'] = loser
        state['round_winner'] = None
        state['last'] = {'type': 'round', 'phase': 1, 'loser': loser,
                         'mats': dict(state['mats'])}
        # Phasenübergang, wenn alle n+1 Filze verteilt
        if sum(state['mats'][p] for p in state['active']) >= state['mats_target']:
            _enter_phase2(state)
            return
        _setup_round(state, opener=loser)
    else:
        if chics:
            # Chicago-Spieler war der Beste und ist bereits gerettet → kein
            # zusätzlicher regulärer Abwurf in dieser Runde
            state['round_winner'] = chics[0]
            state['round_loser'] = None
            state['last'] = {'type': 'round', 'phase': 2, 'winner': chics[0],
                             'mats': dict(state['mats'])}
        else:
            winner = _best_player(state)
            if state['mats'].get(winner, 0) > 0:
                state['mats'][winner] -= 1
            state['round_winner'] = winner
            state['round_loser'] = None
            state['last'] = {'type': 'round', 'phase': 2, 'winner': winner,
                             'mats': dict(state['mats'])}
        # Spieler ohne Filze sind gerettet → raus
        for p in list(state['active']):
            if state['mats'].get(p, 0) <= 0:
                _remove_player(state, p, saved=True)
        if _check_game_over(state):
            return
        _setup_round(state, opener=_most_mats(state))


def _enter_phase2(state: dict) -> None:
    state['phase'] = 2
    # nur Spieler mit Filzen bleiben aktiv
    for p in list(state['active']):
        if state['mats'].get(p, 0) <= 0:
            _remove_player(state, p, saved=True)
    if _check_game_over(state):
        return
    _setup_round(state, opener=_most_mats(state))


def _most_mats(state: dict) -> str:
    return max(state['active'], key=lambda p: (state['mats'].get(p, 0),
                                               -state['players'].index(p)))


def _remove_player(state: dict, pid: str, saved: bool) -> None:
    if pid in state['active']:
        state['active'].remove(pid)
    state['mats'][pid] = 0


def _finish_game(state: dict) -> None:
    state['status'] = 'game_over'
    holders = [p for p in state['active'] if state['mats'].get(p, 0) > 0]
    if holders:
        state['loser'] = holders[0]
    elif state['active']:
        state['loser'] = state['active'][0]
    else:
        state['loser'] = None
    # Sieger = der Mensch, falls er nicht der Verlierer ist
    state['winner'] = 'p' if state['loser'] != 'p' else None
    state['turn'] = None


def human_chicago_won(state: dict) -> bool:
    """Hat IRGENDEIN menschlicher Spieler in dieser Runde durch Chicago gewonnen
    (→ gerettet)? (Banner/Beenden erlaubt auch für Spieler 2/3.)"""
    for h in state.get('humans', ['p']):
        r = state.get('results', {}).get(h)
        if (r is not None and r.get('chic')) or (h not in state['active']):
            return True
    return False


def set_names(state: dict, names: dict) -> None:
    """Namen menschlicher Spieler jederzeit ändern (leer erlaubt)."""
    src = names or {}
    for hid in state.get('humans', ['p']):
        if hid in src:
            state.setdefault('names', {})[hid] = str(src.get(hid) or '').strip()[:20]


def end_after_human_chicago(state: dict) -> None:
    """Ein Mensch hat per Chicago gewonnen und möchte das Spiel sofort beenden.
    Verlierer = aktuell meiste Bierfilze unter den Aktiven (sonst keiner). Die
    „Chicago"-Statistik (`human_chicago`) wird nur in _do_stand für 'p' gesetzt."""
    state['status'] = 'game_over'
    holders = [p for p in state['active'] if state['mats'].get(p, 0) > 0]
    state['loser'] = _most_mats(state) if holders else None
    state['winner'] = 'p' if state['loser'] != 'p' else None
    state['turn'] = None
    state['last'] = {'type': 'human_chicago_win', 'round_no': state.get('round_no', 1)}


def _check_game_over(state: dict) -> bool:
    holders = [p for p in state['active'] if state['mats'].get(p, 0) > 0]
    if state['phase'] == 2 and len(holders) <= 1:
        _finish_game(state)
        return True
    return False


def _setup_round(state: dict, opener: str) -> None:
    state['round_no'] = state.get('round_no', 1) + 1
    state['opener'] = opener
    state['order'] = _round_order(state['players'], state['active'], opener)
    state['order_pos'] = 0
    state['results'] = {}
    state['tief'] = None
    state['roll_cap'] = 3
    _begin_turn(state, opener, opener=True)


# ── KI ───────────────────────────────────────────────────────────────────────

# Erwartungswert eines neu geworfenen Würfels je Wertung (für die Halte-Logik)
_EXP = {
    'gross': (100 + 2 + 3 + 4 + 5 + 60) / 6,   # 29.0
    'ohne1': (1 + 2 + 3 + 4 + 5 + 60) / 6,     # 12.5
    'klein': (1 + 2 + 3 + 4 + 5 + 6) / 6,      # 3.5
}


# Alle 216 möglichen Würfe + vorberechnete Vergleichsschlüssel je Wertung
_ALL_ROLLS = [list(r) for r in itertools.product(range(1, 7), repeat=3)]
_ROLL_KEYS = {v: [roll_key(r, v) for r in _ALL_ROLLS]
              for v in ('gross', 'klein', 'ohne1')}
_ROLL_CHIC = [is_chicago(r) for r in _ALL_ROLLS]

def _beat_count(dice: list[int], valuation: str, direction: str) -> int:
    """Wie viele der 216 Gegner-Einzelwürfe schlagen diese Hand?

    Der Vorleger gewinnt Gleichstände (Mit ist Shit → spätere Position verliert),
    daher nur ECHTES Schlagen zählen. Chicago (drei 1er) schlägt immer.
    """
    ai_key = roll_key(dice, valuation)
    keys = _ROLL_KEYS[valuation]
    beaten = 0
    for i, ok in enumerate(keys):
        if _ROLL_CHIC[i]:
            beaten += 1
        elif (ok > ai_key) if direction == 'hoch' else (ok < ai_key):
            beaten += 1
    return beaten


def _ai_plan(dice: list[int]) -> tuple:
    """Plan des KI-Vorlegers: Wertung + Richtung, die am schwersten zu schlagen
    sind. Bewertet alle Kombinationen über die Gegner-Schlagwahrscheinlichkeit
    (z. B. 1·1·2 → „klein tief" = 4, nur durch Chicago schlagbar, statt „gross
    hoch" = 202).

    Bei Gleichstand der Chance entscheidet eine 6-bewusste Vorliebe: mit einer 6
    lieber „ohne 1" (z. B. 6·2·4 → „66 hoch") als „klein"; ohne 6 lieber „klein"
    (dann ist „ohne 1" identisch und nur verwirrend). „gross" zuerst, „hoch" vor
    „tief"."""
    valrank = ({'gross': 0, 'ohne1': 1, 'klein': 2} if 6 in dice
               else {'gross': 0, 'klein': 1, 'ohne1': 2})
    best = None
    for val in ('gross', 'klein', 'ohne1'):
        for direc in ('hoch', 'tief'):
            cand = (_beat_count(dice, val, direc), valrank[val],
                    0 if direc == 'hoch' else 1)
            if best is None or cand < best[0]:
                best = (cand, (val, direc))
    return best[1]


def _keep_mask(dice: list[int], valuation: str, direction: str) -> list[bool]:
    """Würfel halten, die den Neuwurf-Erwartungswert in die gewünschte Richtung
    schlagen (hoch → höher behalten, tief → tiefer behalten). Regel: NUR 1 und 6
    dürfen stehen bleiben — 2–5 müssen immer zurück in den Becher."""
    exp = _EXP.get(valuation, _EXP['gross'])
    mask = []
    for d in dice:
        if d not in (1, 6):
            mask.append(False)         # nur 1 und 6 dürfen gehalten werden
            continue
        v = _die_value(d, valuation)
        mask.append(v >= exp if direction == 'hoch' else v <= exp)
    return mask


def ai_step(state: dict) -> dict:
    is_opener = (state['status'] == 'opener_roll')
    dice = state['dice']

    if state['rolls_used'] == 0:
        return {'type': 'roll'}

    val, direc = (_ai_plan(dice) if is_opener
                  else (state['valuation'], state['direction']))

    # Nach einer Transformation liegt ein zurückgelegter Würfel (0) → neu werfen
    if 0 in dice:
        return {'type': 'roll', 'held': _keep_mask(dice, val, direc)}

    cap = 3 if is_opener else state['roll_cap']

    # Chicago (drei 1er) ist immer das Beste → sofort stehenbleiben
    if is_chicago(dice):
        if is_opener:
            return {'type': 'stand', 'valuation': 'gross', 'direction': 'hoch'}
        return {'type': 'stand'}

    # Zwei 6er → eine 1: nur sinnvoll, wenn die 1 hoch zählt und hoch gespielt wird
    if (dice.count(6) == 2 and 1 not in dice and state['rolls_used'] < cap
            and state['level'] == 'hard' and val == 'gross' and direc == 'hoch'):
        return {'type': 'convert6'}

    mask = _keep_mask(dice, val, direc)
    want_more = state['rolls_used'] < cap and not all(mask)
    if state['level'] == 'easy':
        want_more = state['rolls_used'] < cap and random.random() < 0.45
    elif state['level'] == 'medium' and want_more and random.random() < 0.25:
        want_more = False          # mittel reizt nicht immer das Maximum aus

    if want_more:
        return {'type': 'roll', 'held': mask}

    if is_opener:
        return {'type': 'stand', 'valuation': val, 'direction': direc}
    return {'type': 'stand'}


# ── Sicht für den Client ─────────────────────────────────────────────────────

def public_view(state: dict) -> dict:
    return {
        'status': state['status'],
        'phase': state['phase'],
        'round_no': state.get('round_no', 1),
        'level': state['level'],
        'opponents': state['opponents'],
        'humans': state.get('humans', ['p']),
        'names': state.get('names', {}),
        'players': state['players'],
        'active': state['active'],
        'mats': state['mats'],
        'mats_target': state['mats_target'],
        'opener': state['opener'],
        'turn': state['turn'],
        'order': state['order'],
        'order_pos': state['order_pos'],
        'valuation': state['valuation'],
        'direction': state['direction'],
        'roll_cap': state['roll_cap'],
        'dice': state['dice'],
        'held': state['held'],
        'locked': state.get('locked', [False, False, False]),
        'rolls_used': state['rolls_used'],
        'can_convert6': (state['status'] in ('opener_roll', 'follower_roll')
                         and 1 <= state['rolls_used'] < state['roll_cap']
                         and state['dice'].count(6) == 2 and 0 not in state['dice']),
        'results': {p: {'label': r['label'], 'dice': r['dice'], 'chic': r['chic'],
                        'rolls': r['rolls']}
                    for p, r in state['results'].items()},
        'round_loser': state['round_loser'],
        'round_winner': state['round_winner'],
        'winner': state['winner'],
        'loser': state['loser'],
        'last': state.get('last'),
    }
