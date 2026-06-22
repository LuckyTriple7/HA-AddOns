"""Gemeinsame Würfel-Grundengine für die Würfelspiele (Kniffel, später Chicago).

Server-seitiges, aus dem Spiel-Seed deterministisches Würfeln (manipulationssicher
und beim Fortsetzen reproduzierbar) plus ein paar Auswertungs-Primitive.
"""
from __future__ import annotations

import random


def roll(n: int, seed: int, step: int) -> list[int]:
    """n Würfel (1–6), deterministisch aus (seed, step).

    Jeder Wurf erhöht ``step`` → andere Augen; gleicher (seed, step) → gleiche Augen.
    """
    rng = random.Random(((int(seed) & 0xFFFFFFFF) * 1000003) ^ (int(step) * 2654435761))
    return [rng.randint(1, 6) for _ in range(n)]


def counts(dice: list[int]) -> list[int]:
    """Häufigkeit je Augenzahl als Liste der Länge 7 (Index 1..6 genutzt)."""
    c = [0] * 7
    for d in dice:
        if 1 <= d <= 6:
            c[d] += 1
    return c


def has_n_of_a_kind(dice: list[int], n: int) -> bool:
    return any(k >= n for k in counts(dice))


def has_straight(dice: list[int], length: int) -> bool:
    present = {d for d in dice if 1 <= d <= 6}
    runs = {4: [{1, 2, 3, 4}, {2, 3, 4, 5}, {3, 4, 5, 6}],
            5: [{1, 2, 3, 4, 5}, {2, 3, 4, 5, 6}]}.get(length, [])
    return any(r <= present for r in runs)
