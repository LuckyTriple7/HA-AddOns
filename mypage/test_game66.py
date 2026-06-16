"""Test-Harness fuer game66 — Regel-Invarianten + Zufalls-Playouts.

Aufruf:  python test_game66.py
Keine externe Test-Lib noetig (laeuft im Add-on-Image).
"""
import random
import sys

import game_66 as g

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print('  FAIL:', msg)


def conserve(st):
    """20 eindeutige Karten ueber Haende + Talon + Stiche + Tisch."""
    seen = (st['hands']['p'] + st['hands']['a'] + st['stock']
            + st['won']['p'] + st['won']['a'] + [t['card'] for t in st['table']])
    return len(seen) == 20 and len(set(seen)) == 20


# ── 1. Zufalls-Playouts: zufaelliger Spieler vs. Heuristik-KI ──────────────────

def random_playouts(n=3000, rules='standard', level='medium'):
    print(f'[1] {n} Zufalls-Matches ({rules}, KI={level}) ...')
    for seed in range(n):
        rng = random.Random(seed)
        st = g.new_match(rng=rng, rules=rules, level=level)
        g.ai_run(st)
        steps = 0
        while st['status'] != 'match_over':
            steps += 1
            if steps > 20000:
                check(False, f'seed {seed}: kein Match-Ende')
                break
            if not conserve(st):
                check(False, f'seed {seed}: Kartenverlust nach {steps} Schritten')
                break
            if not g.is_valid_state(st):
                check(False, f'seed {seed}: is_valid_state False')
                break

            if st['status'] == 'deal_over':
                res = st['result']
                check(res['gp'] in (1, 2, 3), f'seed {seed}: ungueltige gp {res}')
                check(res['winner'] in ('p', 'a'), f'seed {seed}: kein Sieger')
                # Oma: ohne Zudrehen endet eine Partie nur, wenn alle Karten weg sind
                if rules == 'oma' and not st['closed']:
                    check(not st['hands']['p'] and not st['hands']['a'],
                          f'seed {seed}: Oma-Partie vorzeitig beendet ({res["reason"]})')
                g.apply_action(st, 'p', {'type': 'next'})
                g.ai_run(st)
                continue

            check(st['turn'] == 'p', f'seed {seed}: KI nicht durchgelaufen (turn={st["turn"]})')
            acts = g.legal_actions(st, 'p')
            check(bool(acts), f'seed {seed}: keine legalen Zuege fuer Spieler')
            if not acts:
                break
            g.apply_action(st, 'p', rng.choice(acts))
            g.ai_run(st)
        else:
            w = 'p' if st['bummerl']['p'] >= g.MATCH_SCORE else 'a'
            check(st['bummerl'][w] >= g.MATCH_SCORE, f'seed {seed}: Match ohne 7 Punkte')


# ── 2. Stich-/Trumpf-Logik ────────────────────────────────────────────────────

def trick_logic():
    print('[2] Stich-/Trumpf-Logik ...')
    # gleiche Farbe: hoeherer Wert gewinnt
    check(g._trick_winner('Ah', 'Th', 's') == 'lead', 'A schlaegt T (gleiche Farbe)')
    check(g._trick_winner('Th', 'Ah', 's') == 'follow', 'A schlaegt T (Nachhand)')
    # Trumpf schlaegt Nicht-Trumpf
    check(g._trick_winner('Ah', 'Js', 's') == 'follow', 'Trumpf-Bube schlaegt Ass')
    # Nicht-Trumpf andere Farbe schlaegt nicht
    check(g._trick_winner('Ah', 'Kd', 's') == 'lead', 'Abwurf verliert')
    # Trumpf gegen Trumpf: hoeher gewinnt
    check(g._trick_winner('Js', 'As', 's') == 'follow', 'hoeherer Trumpf gewinnt')


# ── 3. Wertung (1/2/3 + Bummerl) ──────────────────────────────────────────────

def scoring():
    print('[3] Wertung ...')
    # made_66, Gegner 33+  -> 1
    st = g.new_match(first_dealer='a', rng=random.Random(1))
    st['trick_pts'] = {'p': 66, 'a': 40}
    st['has_trick'] = {'p': True, 'a': True}
    g._finish_deal(st, 'p', 'made_66')
    check(st['result']['gp'] == 1, 'made_66 Gegner>=33 -> 1')
    check(st['bummerl']['p'] == 1, 'Bummerl +1')

    # made_66, Gegner <33 -> 2 (Schneider)
    st = g.new_match(first_dealer='a', rng=random.Random(2))
    st['trick_pts'] = {'p': 66, 'a': 20}
    st['has_trick'] = {'p': True, 'a': True}
    g._finish_deal(st, 'p', 'made_66')
    check(st['result']['gp'] == 2, 'made_66 Gegner<33 -> 2')

    # made_66, Gegner ohne Stich -> 3 (Schwarz)
    st = g.new_match(first_dealer='a', rng=random.Random(3))
    st['trick_pts'] = {'p': 70, 'a': 0}
    st['has_trick'] = {'p': True, 'a': False}
    g._finish_deal(st, 'p', 'made_66')
    check(st['result']['gp'] == 3, 'made_66 Gegner schwarz -> 3')

    # last_trick -> 1
    st = g.new_match(first_dealer='a', rng=random.Random(4))
    g._finish_deal(st, 'p', 'last_trick')
    check(st['result']['gp'] == 1, 'last_trick -> 1')

    # closed_failed, Gegner hatte Stich -> 2 ; ohne Stich -> 3
    st = g.new_match(first_dealer='a', rng=random.Random(5))
    st['closed'] = True; st['closed_by'] = 'p'; st['closed_opp_trick'] = True
    g._finish_deal(st, 'a', 'closed_failed')
    check(st['result']['gp'] == 2, 'closed_failed Gegner-Stich -> 2')
    st = g.new_match(first_dealer='a', rng=random.Random(6))
    st['closed'] = True; st['closed_by'] = 'p'; st['closed_opp_trick'] = False
    g._finish_deal(st, 'a', 'closed_failed')
    check(st['result']['gp'] == 3, 'closed_failed Gegner ohne Stich -> 3')

    # closed_made nach Snapshot
    st = g.new_match(first_dealer='a', rng=random.Random(7))
    st['closed'] = True; st['closed_by'] = 'p'
    st['closed_opp_trick'] = True; st['closed_snap'] = 10
    st['trick_pts'] = {'p': 66, 'a': 50}  # aktueller Stand egal, Snapshot zaehlt
    st['has_trick'] = {'p': True, 'a': True}
    g._finish_deal(st, 'p', 'closed_made')
    check(st['result']['gp'] == 2, 'closed_made Snapshot<33 -> 2')


# ── 4. Hochzeit + usable ──────────────────────────────────────────────────────

def marriage():
    print('[4] Hochzeit / usable ...')
    st = g.new_match(first_dealer='a', rng=random.Random(8))
    st['trump'] = 'h'
    st['hands']['p'] = ['Kh', 'Qh', 'Kc', 'Qc', 'Ad']
    st['hands']['a'] = ['Js', 'Jd', 'Jc', 'Ts', 'Tc']
    st['stock'] = ['As', 'Ks', 'Qs', 'Ah', 'Th', 'Td', 'Kd', 'Qd', 'Ac', 'Jh']
    st['turn'] = 'p'; st['lead'] = 'p'; st['table'] = []; st['phase2'] = False
    st['won'] = {'p': [], 'a': []}; st['trick_pts'] = {'p': 0, 'a': 0}
    st['marriage_pts'] = {'p': 0, 'a': 0}; st['has_trick'] = {'p': False, 'a': False}
    st['melds'] = {'p': [], 'a': []}; st['closed'] = False
    # Trumpf-Hochzeit ansagen (40), aber ohne Stich zaehlt sie noch nicht
    g.apply_action(st, 'p', {'type': 'play', 'card': 'Qh', 'marry': True})
    check(st['marriage_pts']['p'] == 40, 'Trumpf-Hochzeit = 40')
    check(g.usable(st, 'p') == 0, 'ohne Stich zaehlt Hochzeit nicht (usable=0)')
    check('h' in st['melds']['p'], 'Meld vermerkt')


# ── 5. Phase-2 Farb-/Stichzwang ───────────────────────────────────────────────

def follow_rules():
    print('[5] Phase-2 Zwaenge ...')
    st = g.new_match(first_dealer='a', rng=random.Random(9))
    st['trump'] = 's'
    st['phase2'] = True
    st['hands']['a'] = ['Th', 'Kh', 'Jd', 'As']  # nachziehender Spieler = a
    st['table'] = [{'who': 'p', 'card': 'Qh'}]
    legal = g._legal_follow(st, st['hands']['a'])
    # Herz vorhanden -> Farbzwang; hoeher als Qh (Th, Kh) -> Stichzwang
    check(set(legal) == {'Th', 'Kh'}, f'Farb-+Stichzwang fehlerhaft: {legal}')
    # ohne Herz -> Trumpfzwang
    st['hands']['a'] = ['Jd', 'As', 'Ac']
    legal = g._legal_follow(st, st['hands']['a'])
    check(legal == ['As'], f'Trumpfzwang fehlerhaft: {legal}')
    # weder Farbe noch Trumpf -> frei
    st['hands']['a'] = ['Jd', 'Ac']
    legal = g._legal_follow(st, st['hands']['a'])
    check(set(legal) == {'Jd', 'Ac'}, f'Abwurf frei fehlerhaft: {legal}')


# ── 6. Trumpftausch ───────────────────────────────────────────────────────────

def exchange():
    print('[6] Trumpftausch ...')
    st = g.new_match(first_dealer='a', rng=random.Random(10))
    st['trump'] = 'h'
    st['hands']['p'] = ['Jh', 'Ac', 'Kc', 'Qc', 'Ad']
    st['hands']['a'] = ['As', 'Ts', 'Ks', 'Qs', 'Js']
    # 10 Karten Talon, unterste (aufgedeckt) = Herz-Ass (Trumpf)
    st['stock'] = ['Td', 'Kd', 'Qd', 'Jd', 'Th', 'Kh', 'Qh', 'Jc', 'Tc', 'Ah']
    st['turn'] = 'p'; st['lead'] = 'p'; st['table'] = []; st['phase2'] = False
    check(conserve(st), 'exchange-Setup: 20 Karten')
    up = st['stock'][-1]
    g.apply_action(st, 'p', {'type': 'exchange'})
    check('Jh' not in st['hands']['p'], 'Trumpf-Bube abgegeben')
    check(up in st['hands']['p'], 'aufgedeckte Karte erhalten')
    check(st['stock'][-1] == 'Jh', 'Trumpf-Bube liegt unten')


def cut_for_lead():
    print('[7] Auslosen (hoechste Karte beginnt) ...')
    # Rang schlaegt Rang
    check(g._cut_key('Ah') > g._cut_key('Th'), 'Ass > Zehn')
    # gleiche Rang -> Farbe entscheidet: Kreuz < Karo < Herz < Pik
    check(g._cut_key('Js') > g._cut_key('Jh') > g._cut_key('Jd') > g._cut_key('Jc'),
          'Farbreihenfolge Kreuz<Karo<Herz<Pik')
    # _cut_for_lead liefert immer eindeutigen Sieger + zwei verschiedene Karten
    for seed in range(500):
        cut = g._cut_for_lead(random.Random(seed))
        check(cut['p'] != cut['a'], f'seed {seed}: gleiche Karte gezogen')
        exp = 'p' if g._cut_key(cut['p']) > g._cut_key(cut['a']) else 'a'
        check(cut['leader'] == exp, f'seed {seed}: falscher Auslos-Sieger')
    # Sieger fuehrt die erste Partie aus
    st = g.new_match(rng=random.Random(1))
    check(st['lead'] == st['cut']['leader'], 'Auslos-Sieger spielt aus')
    check(st['dealer'] == g.other(st['cut']['leader']), 'der andere ist Geber')


def scoring_oma():
    print('[8] Wertung Oma ...')
    # oma_made: Sieger 66+, Verlierer-Augen bestimmen 1/2/3
    st = g.new_match(first_dealer='a', rng=random.Random(1))
    st['rules'] = 'oma'
    st['trick_pts'] = {'p': 70, 'a': 40}; st['has_trick'] = {'p': True, 'a': True}
    g._finish_deal(st, 'p', 'oma_made')
    check(st['result']['gp'] == 1, 'oma_made Gegner>=33 -> 1')
    st = g.new_match(first_dealer='a', rng=random.Random(2)); st['rules'] = 'oma'
    st['trick_pts'] = {'p': 70, 'a': 20}; st['has_trick'] = {'p': True, 'a': True}
    g._finish_deal(st, 'p', 'oma_made')
    check(st['result']['gp'] == 2, 'oma_made Gegner<33 -> 2')
    st = g.new_match(first_dealer='a', rng=random.Random(3)); st['rules'] = 'oma'
    st['trick_pts'] = {'p': 90, 'a': 0}; st['has_trick'] = {'p': True, 'a': False}
    g._finish_deal(st, 'p', 'oma_made')
    check(st['result']['gp'] == 3, 'oma_made Gegner schwarz -> 3')
    # oma_lasttrick: Sieger des letzten Stichs, Wertung nach Verlierer-Augen
    st = g.new_match(first_dealer='a', rng=random.Random(4)); st['rules'] = 'oma'
    st['trick_pts'] = {'p': 65, 'a': 55}; st['has_trick'] = {'p': True, 'a': True}
    g._finish_deal(st, 'p', 'oma_lasttrick')
    check(st['result']['gp'] == 1, 'oma_lasttrick Gegner>=33 -> 1')
    # closed_failed (Oma): pauschal 3
    st = g.new_match(first_dealer='a', rng=random.Random(5)); st['rules'] = 'oma'
    st['closed'] = True; st['closed_by'] = 'p'; st['closed_opp_trick'] = True
    g._finish_deal(st, 'a', 'closed_failed')
    check(st['result']['gp'] == 3, 'oma closed_failed -> 3 (pauschal)')
    # closed_made (Oma): nach aktuellen Gegner-Augen
    st = g.new_match(first_dealer='a', rng=random.Random(6)); st['rules'] = 'oma'
    st['closed'] = True; st['closed_by'] = 'p'
    st['trick_pts'] = {'p': 66, 'a': 20}; st['has_trick'] = {'p': True, 'a': True}
    g._finish_deal(st, 'p', 'closed_made')
    check(st['result']['gp'] == 2, 'oma closed_made Gegner<33 -> 2')


def levels():
    print('[9] KI-Schwierigkeitsgrade ...')
    # Epsilon je Level
    st = g.new_match(first_dealer='a', rng=random.Random(1), level='easy')
    check(g._ai_epsilon(st) == g._BASE_EPS['easy'], 'easy-Epsilon')
    st = g.new_match(first_dealer='a', rng=random.Random(1), level='hard')
    check(g._ai_epsilon(st) == 0.0, 'hard-Epsilon = 0')
    check(g._ai_strength(st) == 100, 'hard = 100% Staerke')
    # ungueltiges Level -> medium
    st = g.new_match(first_dealer='a', rng=random.Random(1), level='bogus')
    check(st['level'] == 'medium', 'ungueltiges Level -> medium')
    # Adaptiv: Start + Anpassung (Spieler gewinnt -> KI staerker, sonst schwaecher)
    st = g.new_match(first_dealer='a', rng=random.Random(1), level='adaptive')
    check(abs(st['adapt_eps'] - g._ADAPT_START) < 1e-9, 'adaptiv Start-Epsilon')
    before = st['adapt_eps']
    st['trick_pts'] = {'p': 70, 'a': 10}; st['has_trick'] = {'p': True, 'a': True}
    g._finish_deal(st, 'p', 'made_66')
    check(st['adapt_eps'] < before, 'Spieler gewinnt -> KI staerker (Epsilon faellt)')
    st2 = g.new_match(first_dealer='a', rng=random.Random(2), level='adaptive')
    before2 = st2['adapt_eps']
    st2['trick_pts'] = {'p': 10, 'a': 70}; st2['has_trick'] = {'p': True, 'a': True}
    g._finish_deal(st2, 'a', 'made_66')
    check(st2['adapt_eps'] > before2, 'KI gewinnt -> KI schwaecher (Epsilon steigt)')
    # Epsilon bleibt in den Grenzen
    st3 = g.new_match(first_dealer='a', rng=random.Random(3), level='adaptive')
    for _ in range(50):
        st3['adapt_eps'] = 0.0
        st3['trick_pts'] = {'p': 70, 'a': 10}; st3['has_trick'] = {'p': True, 'a': True}
        g._finish_deal(st3, 'p', 'made_66')
        check(g._ADAPT_MIN <= st3['adapt_eps'] <= g._ADAPT_MAX, 'adaptiv im Grenzbereich')
    # public_view enthaelt level + Staerke
    pv = g.public_view(g.new_match(first_dealer='a', rng=random.Random(4), level='easy'))
    check(pv['level'] == 'easy' and isinstance(pv['ai_strength'], int), 'public_view: level + strength')


if __name__ == '__main__':
    trick_logic()
    scoring()
    marriage()
    follow_rules()
    exchange()
    cut_for_lead()
    scoring_oma()
    levels()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    random_playouts(n, 'standard')
    random_playouts(n, 'oma')
    # Alle Schwierigkeitsgrade auf Invarianten pruefen (kleinere Stichprobe)
    for lvl in ('easy', 'hard', 'adaptive'):
        random_playouts(max(1, n // 6), 'standard', lvl)
    print()
    if FAILS:
        print(f'{len(FAILS)} FEHLER')
        sys.exit(1)
    print('ALLE TESTS OK')
