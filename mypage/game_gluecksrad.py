"""Glücksrad (Wheel of Fortune) — game logic, state machine, AI."""

import json
import random
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VOWELS = set("AEIOU")
CONSONANTS = set("BCDFGHJKLMNPQRSTVWXYZ")
UMLAUT_TO_BASE = {"Ä": "A", "Ö": "O", "Ü": "U", "ß": "S"}
VOWEL_COST = 250
ROUNDS = 3

WHEEL_SEGMENTS = [
    100, 200, 300, 150, 500, "BANKROTT", 250, 400,
    600, 350, 800, "AUSSETZEN", 450, 700, 1000,
    200, 900, "RISIKO", 300, 2500, 500, 150, 5000, "EXTRALEBEN",
]

FINALE_AUTO = ["R", "S", "T", "L", "N", "E"]
FINALE_EXTRA_CONSONANTS = 3
FINALE_EXTRA_VOWEL = 1
FINALE_TIMER_SEC = 30

LETTER_FREQ_DE = list("ENISRATDHULCGMOBWFKZPVJYXQ")
LETTER_FREQ_EN = list("ETAOINSRHLDCUMFPGWYBVKXJQZ")

_pool_cache = None

# ---------------------------------------------------------------------------
# Pool loading
# ---------------------------------------------------------------------------

def _load_pool():
    global _pool_cache
    if _pool_cache is None:
        p = Path(__file__).parent / "data" / "word_pool.json"
        with open(p, encoding="utf-8") as f:
            _pool_cache = json.load(f)
    return _pool_cache


def _pick_puzzle(lang, used_indices, used_cats=None):
    pool = _load_pool()
    used_cats = used_cats if used_cats is not None else set()
    # Bevorzugt: noch nicht benutztes Rätsel UND noch nicht gespielte Kategorie,
    # damit pro Spiel keine Kategorie doppelt erscheint.
    available = [
        (i, p) for i, p in enumerate(pool["puzzles"])
        if i not in used_indices and p.get(lang) and p["cat"] not in used_cats
    ]
    if not available:
        # Keine frische Kategorie mehr (oder Pool erschöpft) → nur Rätsel-Dubletten meiden.
        available = [
            (i, p) for i, p in enumerate(pool["puzzles"])
            if i not in used_indices and p.get(lang)
        ]
    if not available:
        used_indices.clear()
        available = [(i, p) for i, p in enumerate(pool["puzzles"]) if p.get(lang)]
    idx, puzzle = random.choice(available)
    used_indices.add(idx)
    cat_key = puzzle["cat"]
    cat_labels = pool["categories"].get(cat_key, {"de": cat_key, "en": cat_key})
    return {
        "phrase": puzzle[lang],
        "category_key": cat_key,
        "category": cat_labels.get(lang, cat_labels.get("de", cat_key)),
        "pool_idx": idx,
    }

# ---------------------------------------------------------------------------
# Letter helpers
# ---------------------------------------------------------------------------

def _base_letter(ch):
    return UMLAUT_TO_BASE.get(ch, ch)


def _phrase_has_letter(phrase, letter):
    count = 0
    for ch in phrase:
        if _base_letter(ch) == letter:
            count += 1
    return count


def _build_display(phrase, revealed):
    display = []
    for ch in phrase:
        if ch == " ":
            display.append(" ")
        elif not ch.isalpha():
            display.append(ch)
        elif _base_letter(ch) in revealed:
            display.append(ch)
        else:
            display.append("_")
    return "".join(display)


def _all_revealed(phrase, revealed):
    for ch in phrase:
        if ch.isalpha() and _base_letter(ch) not in revealed:
            return False
    return True


def _available_consonants(used):
    return sorted(CONSONANTS - used)


def _available_vowels(used):
    return sorted(VOWELS - used)

# ---------------------------------------------------------------------------
# Game creation
# ---------------------------------------------------------------------------

def new_game(level="medium", lang="de"):
    state = {
        "level": level,
        "lang": lang,
        "status": "qualify_spin",
        "round": 0,
        "players": [
            {"name": "Du" if lang == "de" else "You", "type": "human",
             "total": 0, "round": 0, "extra_lives": 0},
            {"name": "Lisa", "type": "ai", "total": 0, "round": 0, "extra_lives": 0},
            {"name": "Max", "type": "ai", "total": 0, "round": 0, "extra_lives": 0},
        ],
        "current": 0,
        "puzzle": None,
        "used_letters": [],
        "wheel_result": None,
        "wheel_index": None,
        "event": None,
        "used_puzzles": [],
        "used_categories": [],
        "finale": None,
        "qualify_spins": [],
        "seed": random.randint(0, 2**31),
    }
    return state


def _start_round(state):
    lang = state["lang"]
    used_set = set(state["used_puzzles"])
    used_cats = set(state.get("used_categories", []))
    pz = _pick_puzzle(lang, used_set, used_cats)
    state["used_puzzles"] = list(used_set)
    used_cats.add(pz["category_key"])
    state["used_categories"] = list(used_cats)
    state["puzzle"] = {
        "phrase": pz["phrase"],
        "category_key": pz["category_key"],
        "category": pz["category"],
    }
    state["used_letters"] = []
    state["wheel_result"] = None
    state["wheel_index"] = None
    for p in state["players"]:
        p["round"] = 0
    state["status"] = "pre_spin"

# ---------------------------------------------------------------------------
# Public view (strips secrets)
# ---------------------------------------------------------------------------

def public_view(state):
    revealed = set(state["used_letters"])
    phrase = state["puzzle"]["phrase"] if state["puzzle"] else ""
    display = _build_display(phrase, revealed) if phrase else ""
    used = set(state["used_letters"])

    cp = state["players"][state["current"]]
    can_vowel = (
        cp["type"] == "human"
        and cp["round"] >= VOWEL_COST
        and len(_available_vowels(used)) > 0
        and state["status"] == "pre_spin"
    )

    view = {
        "status": state["status"],
        "round": state["round"],
        "max_rounds": ROUNDS,
        "players": [
            {"name": p["name"], "type": p["type"],
             "total": p["total"], "round": p["round"],
             "extra_lives": p.get("extra_lives", 0)}
            for p in state["players"]
        ],
        "current": state["current"],
        "category": state["puzzle"]["category"] if state["puzzle"] else "",
        "display": display,
        "phrase_len": len(phrase) if phrase else 0,
        "used_letters": sorted(state["used_letters"]),
        "available_consonants": _available_consonants(used),
        "available_vowels": _available_vowels(used),
        "can_buy_vowel": can_vowel,
        "wheel_result": state["wheel_result"],
        "wheel_index": state["wheel_index"],
        "wheel_segments": WHEEL_SEGMENTS,
        "event": state["event"],
        "qualify_spins": state.get("qualify_spins", []),
    }
    if state["status"] == "game_over":
        view["phrase"] = phrase
        view["winner"] = _determine_winner(state)
    if state["status"] == "round_over":
        view["phrase"] = phrase
    if state["finale"]:
        view["finale"] = {
            "player_idx": state["finale"]["player_idx"],
            "auto_letters": state["finale"]["auto_letters"],
            "extra_consonants": state["finale"].get("extra_consonants", []),
            "extra_vowel": state["finale"].get("extra_vowel"),
            "timer_sec": FINALE_TIMER_SEC,
        }
    return view

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def apply_action(state, action):
    atype = action.get("type")
    status = state["status"]
    state["event"] = None

    if atype == "risk_choice" and status == "risk_choice":
        return _do_risk_choice(state, action.get("accept", False))
    if atype == "use_life" and status == "use_life":
        return _do_use_life(state, action.get("use", False))
    if atype == "spin" and status == "qualify_spin":
        return _do_qualify_spin(state)
    if atype == "spin" and status == "pre_spin":
        return _do_spin(state)
    if atype == "pick_consonant" and status == "pick_consonant":
        return _do_pick_consonant(state, action.get("letter", "").upper())
    if atype == "buy_vowel" and status == "pre_spin":
        return _do_buy_vowel(state)
    if atype == "pick_vowel" and status == "pick_vowel":
        return _do_pick_vowel(state, action.get("letter", "").upper())
    if atype == "solve" and status in ("pre_spin", "pick_consonant", "pick_vowel"):
        return _do_solve(state, action.get("answer", ""))
    if atype == "continue" and status == "round_over":
        return _do_next_round(state)
    if atype == "finale_pick" and status == "finale_pick":
        return _do_finale_pick(state, action)
    if atype == "finale_solve" and status == "finale_solve":
        return _do_finale_solve(state, action.get("answer", ""))
    return {"error": f"Ungültige Aktion: {atype} im Status {status}"}

# --- qualify spin ---

def _do_qualify_spin(state):
    idx = random.randint(0, len(WHEEL_SEGMENTS) - 1)
    seg = WHEEL_SEGMENTS[idx]
    amount = seg if isinstance(seg, int) else 0
    state["wheel_index"] = idx
    state["qualify_spins"].append({"player": state["current"], "amount": amount})
    state["event"] = {"type": "qualify_spin", "player": state["current"],
                      "amount": amount, "segment": seg}
    nxt = state["current"] + 1
    if nxt < len(state["players"]):
        state["current"] = nxt
    else:
        spins = state["qualify_spins"]
        amounts = [s["amount"] for s in spins]
        top = max(amounts)
        winners = [s for s in spins if s["amount"] == top]
        if len(winners) > 1:
            state["qualify_spins"] = []
            state["current"] = 0
            state["event"] = {"type": "qualify_tie", "spins": spins}
        else:
            state["current"] = winners[0]["player"]
            state["round"] = 1
            state["status"] = "pre_spin"
            _start_round(state)
            state["wheel_index"] = idx
            state["event"] = {"type": "qualify_done", "spins": spins,
                              "starter": winners[0]["player"]}
    return {"ok": True}


# --- risk choice ---

def _do_risk_choice(state, accept):
    cp = state["players"][state["current"]]
    rnd = cp["round"]
    if accept:
        if random.random() < 0.5:
            cp["round"] = rnd * 2
            state["event"] = {"type": "risk_win", "player": state["current"],
                              "old": rnd, "new": rnd * 2}
        else:
            cp["round"] = 0
            state["event"] = {"type": "risk_lose", "player": state["current"],
                              "old": rnd}
            _next_player(state)
    else:
        state["event"] = {"type": "risk_decline", "player": state["current"]}
    state["status"] = "pre_spin"
    return {"ok": True}


# --- extra life ---

def _do_use_life(state, use):
    cp = state["players"][state["current"]]
    penalty = state.pop("_pending_penalty", "bankrupt")
    if use:
        cp["extra_lives"] -= 1
        state["event"] = {"type": "life_used", "player": state["current"],
                          "penalty": penalty, "lives": cp["extra_lives"]}
        state["status"] = "pre_spin"
    else:
        if penalty == "bankrupt":
            cp["round"] = 0
            state["event"] = {"type": "bankrupt", "player": state["current"]}
        else:
            state["event"] = {"type": "skip", "player": state["current"]}
        _next_player(state)
        state["status"] = "pre_spin"
    return {"ok": True}


# --- spin ---

def _do_spin(state):
    idx = random.randint(0, len(WHEEL_SEGMENTS) - 1)
    seg = WHEEL_SEGMENTS[idx]
    state["wheel_index"] = idx
    state["wheel_result"] = seg

    cp = state["players"][state["current"]]
    if seg == "EXTRALEBEN":
        if cp.get("extra_lives", 0) >= 1:
            state["event"] = {"type": "extra_life_skip", "player": state["current"]}
            state["status"] = "pre_spin"
        else:
            cp["extra_lives"] = 1
            state["event"] = {"type": "extra_life", "player": state["current"],
                              "lives": 1}
            state["status"] = "pre_spin"
    elif seg == "BANKROTT":
        if cp.get("extra_lives", 0) > 0:
            state["event"] = {"type": "bankrupt_can_save", "player": state["current"]}
            state["status"] = "use_life"
            state["_pending_penalty"] = "bankrupt"
        else:
            cp["round"] = 0
            state["event"] = {"type": "bankrupt", "player": state["current"]}
            _next_player(state)
            state["status"] = "pre_spin"
    elif seg == "AUSSETZEN":
        if cp.get("extra_lives", 0) > 0:
            state["event"] = {"type": "skip_can_save", "player": state["current"]}
            state["status"] = "use_life"
            state["_pending_penalty"] = "skip"
        else:
            state["event"] = {"type": "skip", "player": state["current"]}
            _next_player(state)
            state["status"] = "pre_spin"
    elif seg == "RISIKO":
        rnd = state["players"][state["current"]]["round"]
        if rnd == 0:
            state["event"] = {"type": "risk_skip", "player": state["current"]}
            state["status"] = "pre_spin"
        else:
            state["event"] = {"type": "risk_choice", "player": state["current"],
                              "amount": rnd}
            state["status"] = "risk_choice"
    elif not _available_consonants(set(state["used_letters"])):
        # Alle Konsonanten bereits aufgedeckt → Drehung verfällt; der Spieler
        # kann nur noch einen Vokal kaufen oder lösen.
        state["wheel_result"] = None
        state["wheel_index"] = None
        state["event"] = {"type": "no_consonants", "player": state["current"]}
        state["status"] = "pre_spin"
    else:
        state["status"] = "pick_consonant"
        state["event"] = {"type": "spin_money", "amount": seg,
                          "player": state["current"]}
    return {"ok": True}

# --- consonant ---

def _do_pick_consonant(state, letter):
    if letter not in CONSONANTS:
        return {"error": "Kein gültiger Konsonant"}
    used = set(state["used_letters"])
    if letter in used:
        return {"error": "Buchstabe bereits verwendet"}

    state["used_letters"].append(letter)
    phrase = state["puzzle"]["phrase"]
    count = _phrase_has_letter(phrase, letter)
    amount = state["wheel_result"] if isinstance(state["wheel_result"], int) else 0

    if count > 0:
        earned = amount * count
        state["players"][state["current"]]["round"] += earned
        state["event"] = {"type": "letter_hit", "letter": letter,
                          "count": count, "earned": earned,
                          "player": state["current"]}
        if _all_revealed(phrase, set(state["used_letters"])):
            return _auto_solve(state)
        state["status"] = "pre_spin"
    else:
        state["event"] = {"type": "letter_miss", "letter": letter,
                          "player": state["current"]}
        _next_player(state)
        state["status"] = "pre_spin"
    state["wheel_result"] = None
    state["wheel_index"] = None
    return {"ok": True}

# --- vowel ---

def _do_buy_vowel(state):
    cp = state["players"][state["current"]]
    used = set(state["used_letters"])
    avail = _available_vowels(used)
    if cp["round"] < VOWEL_COST:
        return {"error": "Nicht genug Geld für einen Vokal"}
    if not avail:
        return {"error": "Keine Vokale mehr verfügbar"}
    cp["round"] -= VOWEL_COST
    state["status"] = "pick_vowel"
    state["event"] = {"type": "buy_vowel", "player": state["current"],
                      "cost": VOWEL_COST}
    return {"ok": True}

def _do_pick_vowel(state, letter):
    if letter not in VOWELS:
        return {"error": "Kein gültiger Vokal"}
    used = set(state["used_letters"])
    if letter in used:
        return {"error": "Buchstabe bereits verwendet"}

    state["used_letters"].append(letter)
    phrase = state["puzzle"]["phrase"]
    count = _phrase_has_letter(phrase, letter)

    if count > 0:
        state["event"] = {"type": "vowel_hit", "letter": letter,
                          "count": count, "player": state["current"]}
        if _all_revealed(phrase, set(state["used_letters"])):
            return _auto_solve(state)
    else:
        state["event"] = {"type": "vowel_miss", "letter": letter,
                          "player": state["current"]}
        _next_player(state)
    state["status"] = "pre_spin"
    return {"ok": True}

# --- solve ---

def _normalize(text):
    t = text.upper().strip()
    for u, b in UMLAUT_TO_BASE.items():
        t = t.replace(u, b)
    t = "".join(ch for ch in t if ch.isalpha() or ch == " ")
    return " ".join(t.split())


def _do_solve(state, answer):
    phrase = state["puzzle"]["phrase"]
    if _normalize(answer) == _normalize(phrase):
        state["event"] = {"type": "solved", "player": state["current"],
                          "phrase": phrase}
        state["used_letters"] = list(set(
            _base_letter(ch) for ch in phrase if ch.isalpha()
        ))
        return _end_round(state)
    else:
        state["event"] = {"type": "solve_wrong", "player": state["current"]}
        _next_player(state)
        state["status"] = "pre_spin"
        return {"ok": True}


def _auto_solve(state):
    state["event"] = {"type": "auto_solved", "player": state["current"],
                      "phrase": state["puzzle"]["phrase"]}
    return _end_round(state)

# --- round management ---

def _end_round(state):
    winner = state["current"]
    state["players"][winner]["total"] += state["players"][winner]["round"]
    for i, p in enumerate(state["players"]):
        if i != winner:
            p["round"] = 0
    state["status"] = "round_over"
    state["event"] = state["event"] or {}
    state["event"]["round_winner"] = winner
    return {"ok": True}


def _do_next_round(state):
    if state["round"] >= ROUNDS:
        return _start_finale(state)
    # Der Gewinner der gerade beendeten Runde ist noch state["current"]
    # (von _end_round gesetzt) und fängt die nächste Runde an.
    winner = state["current"]
    state["round"] += 1
    _start_round(state)
    state["current"] = winner
    state["event"] = {"type": "new_round", "round": state["round"]}
    return {"ok": True}

# --- finale ---

def _start_finale(state):
    totals = [(i, p["total"]) for i, p in enumerate(state["players"])]
    totals.sort(key=lambda x: -x[1])
    finalist = totals[0][0]
    state["round"] = ROUNDS + 1
    _start_round(state)
    state["current"] = finalist

    revealed = set(FINALE_AUTO)
    state["used_letters"] = list(revealed)
    state["finale"] = {
        "player_idx": finalist,
        "auto_letters": list(FINALE_AUTO),
        "extra_consonants": [],
        "extra_vowel": None,
    }
    state["status"] = "finale_pick"
    state["event"] = {"type": "finale_start", "player": finalist}
    # Ist der Führende eine KI, spielt sie das Finale (Regeln: der Führende
    # spielt das Finale). Das Frontend hat keinen KI-Finale-Flow, daher löst der
    # Server es sofort auf – der Bonus verdoppelt nur den ohnehin führenden
    # Score und ändert den Sieger nicht.
    if state["players"][finalist]["type"] == "ai":
        return _ai_play_finale(state)
    return {"ok": True}


def _ai_play_finale(state):
    cfg = _LEVEL_CFG.get(state["level"], _LEVEL_CFG["medium"])
    used = set(state["used_letters"])
    freq = LETTER_FREQ_DE if state["lang"] == "de" else LETTER_FREQ_EN
    cons = [l for l in freq if l in CONSONANTS and l not in used][:FINALE_EXTRA_CONSONANTS]
    for l in CONSONANTS:
        if len(cons) >= FINALE_EXTRA_CONSONANTS:
            break
        if l not in used and l not in cons:
            cons.append(l)
    vowel = next((l for l in freq if l in VOWELS and l not in used), None)
    if vowel is None:
        vowel = next((l for l in VOWELS if l not in used), "A")
    for l in cons + [vowel]:
        used.add(l)
    state["used_letters"] = list(used)
    state["finale"]["extra_consonants"] = cons
    state["finale"]["extra_vowel"] = vowel
    phrase = state["puzzle"]["phrase"]
    if random.random() <= cfg["solve_accuracy"]:
        bonus = state["players"][state["current"]]["total"]
        state["players"][state["current"]]["total"] += bonus
        state["event"] = {"type": "finale_solved", "phrase": phrase,
                          "bonus": bonus, "ai": True,
                          "consonants": cons, "vowel": vowel}
    else:
        state["event"] = {"type": "finale_wrong", "phrase": phrase, "ai": True,
                          "consonants": cons, "vowel": vowel}
    state["status"] = "game_over"
    return {"ok": True}


def _do_finale_pick(state, action):
    cons = [c.upper() for c in action.get("consonants", [])]
    vowel = action.get("vowel", "").upper()
    used = set(state["used_letters"])

    if len(cons) != FINALE_EXTRA_CONSONANTS:
        return {"error": f"Genau {FINALE_EXTRA_CONSONANTS} Konsonanten wählen"}
    for c in cons:
        if c not in CONSONANTS or c in used:
            return {"error": f"Ungültiger Konsonant: {c}"}
        used.add(c)
    if vowel not in VOWELS or vowel in used:
        return {"error": f"Ungültiger Vokal: {vowel}"}
    used.add(vowel)

    state["used_letters"] = list(used)
    state["finale"]["extra_consonants"] = cons
    state["finale"]["extra_vowel"] = vowel
    state["finale"]["timer_start"] = time.time()
    state["status"] = "finale_solve"

    phrase = state["puzzle"]["phrase"]
    total_hits = sum(_phrase_has_letter(phrase, l) for l in cons + [vowel])
    state["event"] = {"type": "finale_reveal", "consonants": cons,
                      "vowel": vowel, "hits": total_hits}
    return {"ok": True}


def _do_finale_solve(state, answer):
    phrase = state["puzzle"]["phrase"]
    elapsed = time.time() - state["finale"].get("timer_start", time.time())
    timed_out = elapsed > FINALE_TIMER_SEC + 2

    if timed_out:
        state["event"] = {"type": "finale_timeout", "phrase": phrase}
        state["status"] = "game_over"
        return {"ok": True}

    if _normalize(answer) == _normalize(phrase):
        bonus = state["players"][state["current"]]["total"]
        state["players"][state["current"]]["total"] += bonus
        state["event"] = {"type": "finale_solved", "phrase": phrase,
                          "bonus": bonus}
    else:
        state["event"] = {"type": "finale_wrong", "phrase": phrase}

    state["status"] = "game_over"
    return {"ok": True}

# --- helpers ---

def _next_player(state):
    state["current"] = (state["current"] + 1) % len(state["players"])


def _determine_winner(state):
    best = max(state["players"], key=lambda p: p["total"])
    winners = [i for i, p in enumerate(state["players"])
               if p["total"] == best["total"]]
    if len(winners) == 1:
        return winners[0]
    return winners

# ---------------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------------

_LEVEL_CFG = {
    "easy":   {"solve_thresh": 0.60, "freq_noise": 8, "solve_chance": 0.45,
               "vowel_prob": 0.15, "solve_accuracy": 0.5},
    "medium": {"freq_noise": 4, "solve_thresh": 0.55, "solve_chance": 0.6,
               "vowel_prob": 0.25, "solve_accuracy": 0.75},
    "hard":   {"freq_noise": 1, "solve_thresh": 0.45, "solve_chance": 0.8,
               "vowel_prob": 0.35, "solve_accuracy": 0.95},
}


def ai_step(state):
    cp = state["players"][state["current"]]
    if cp["type"] != "ai":
        return {"error": "Kein KI-Spieler am Zug"}

    state["event"] = None
    status = state["status"]

    if status == "qualify_spin":
        return _do_qualify_spin(state)

    if status == "use_life":
        return _do_use_life(state, True)

    if status == "risk_choice":
        accept = cp["round"] < 500 or random.random() < 0.6
        return _do_risk_choice(state, accept)

    cfg = _LEVEL_CFG.get(state["level"], _LEVEL_CFG["medium"])
    phrase = state["puzzle"]["phrase"]
    revealed = set(state["used_letters"])

    if status == "pre_spin":
        used = set(state["used_letters"])
        # Keine Konsonanten mehr offen → drehen bringt nichts: Vokal kaufen oder lösen.
        if not _available_consonants(used):
            if cp["round"] >= VOWEL_COST and _available_vowels(used):
                # Nur kaufen; den Vokal wählt der nächste ai_step, damit der
                # "kauft einen Vokal"-Hinweis sichtbar wird (Event bleibt erhalten).
                return _do_buy_vowel(state)
            if random.random() > cfg["solve_accuracy"]:
                return _do_solve(state, phrase + "X")
            return _do_solve(state, phrase)

        revealed_ratio = _revealed_ratio(phrase, revealed)
        if (revealed_ratio >= cfg["solve_thresh"]
                and random.random() < cfg["solve_chance"]
                and _ai_can_guess(phrase, revealed, cfg)):
            if random.random() > cfg["solve_accuracy"]:
                return _do_solve(state, phrase + "X")
            return _do_solve(state, phrase)

        used = set(state["used_letters"])
        if (cp["round"] >= VOWEL_COST
                and _available_vowels(used)
                and random.random() < cfg["vowel_prob"]):
            # Nur kaufen; den Vokal wählt der nächste ai_step, damit der
            # "kauft einen Vokal"-Hinweis sichtbar wird (Event bleibt erhalten).
            return _do_buy_vowel(state)

        return _do_spin(state)

    if status == "pick_consonant":
        letter = _ai_pick_consonant(state, cfg)
        return _do_pick_consonant(state, letter)

    if status == "pick_vowel":
        letter = _ai_pick_vowel(state, cfg)
        return _do_pick_vowel(state, letter)

    return {"error": f"KI kann im Status {status} nichts tun"}


def _revealed_ratio(phrase, revealed):
    total = sum(1 for ch in phrase if ch.isalpha())
    if total == 0:
        return 1.0
    shown = sum(1 for ch in phrase if ch.isalpha() and _base_letter(ch) in revealed)
    return shown / total


def _ai_can_guess(phrase, revealed, cfg):
    unrevealed = sum(1 for ch in phrase
                     if ch.isalpha() and _base_letter(ch) not in revealed)
    # Großzügiger: die KI rät auch mit mehreren offenen Buchstaben (spannenderes
    # Aufdecken), statt das Wort erst per letztem Buchstaben zu komplettieren.
    return unrevealed <= 10 or random.random() < 0.45


def _ai_pick_consonant(state, cfg):
    used = set(state["used_letters"])
    avail = _available_consonants(used)
    if not avail:
        return avail[0] if avail else "B"
    lang = state["lang"]
    freq = LETTER_FREQ_DE if lang == "de" else LETTER_FREQ_EN
    freq_cons = [l for l in freq if l in CONSONANTS and l not in used]
    noise = cfg["freq_noise"]
    if freq_cons:
        idx = min(abs(int(random.gauss(0, noise))), len(freq_cons) - 1)
        return freq_cons[idx]
    return random.choice(avail)


def _ai_pick_vowel(state, cfg):
    used = set(state["used_letters"])
    avail = _available_vowels(used)
    if not avail:
        return "A"
    lang = state["lang"]
    freq = LETTER_FREQ_DE if lang == "de" else LETTER_FREQ_EN
    freq_vow = [l for l in freq if l in VOWELS and l not in used]
    if freq_vow:
        return freq_vow[0]
    return random.choice(avail)
