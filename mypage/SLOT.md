# Slot Machine — Gewinntabelle & Spiellogik

Stand: v0.6.42 · Referenz für spätere Anpassungen.
Code: [`templates/public.html`](templates/public.html) → Funktion `gameSlot()` · Jackpot-Backend: [`app.py`](app.py) → `/api/slot`.

## Symbole (8)

| Symbol | Name |
|--------|------|
| 7️⃣ | Sieben |
| 🍒 | Kirsche |
| 🍋 | Zitrone |
| 🔔 | Glocke |
| ⭐ | Stern |
| 💎 | Diamant |
| 🍉 | Melone |
| 🚫 | Niete (zahlt nie) |

Jede der 3 Walzen zieht **gleichverteilt zufällig** (`Math.random`) eines der 8 Symbole → **8³ = 512 Kombinationen**. Das Dreh-Geflacker ist nur Optik; das Ergebnis steht beim Klick fest.

## Gewinntabelle

- **Paar (2×)** = Walze 1 **und** Walze 2 gleich (von links). Walze 3 zählt für das Paar nicht.
- **Drilling (3×)** = alle drei Walzen gleich.
- Einsatz: **10** pro Spin.

| Symbol | Paar (2×) | Drilling (3×) |
|--------|-----------|---------------|
| 🍒 Kirsche | 20 | 50 |
| 🍋 Zitrone | 20 | 50 |
| 🍉 Melone | 30 | 80 |
| 🔔 Glocke | 40 | 100 |
| ⭐ Stern | 40 | 100 |
| 💎 Diamant | 50 | 200 |
| 7️⃣ Sieben | 100 | **Jackpot** |
| 🚫 Niete | – | – |

Im Code als Maps hinterlegt:

```js
const PAIR   = { '7️⃣': 100, '💎': 50, '🔔': 40, '⭐': 40, '🍉': 30, '🍒': 20, '🍋': 20 };
const TRIPLE = { '💎': 200, '🔔': 100, '⭐': 100, '🍉': 80, '🍒': 50, '🍋': 50 }; // 7️⃣ = Jackpot
```

## Jackpot (progressiv, serverweit geteilt)

- Gemeinsamer Zähler für **alle** Besucher, in `site.json` (`slot_jackpot`), per `threading.Lock` abgesichert.
- **Jeder Spin** erhöht ihn um **+1** (gedeckelt bei 100 Mio.).
- **3× 7️⃣** zahlt den **exakt aktuellen** Betrag aus und setzt auf **500** zurück.
- Startwert: **500**.

## Wahrscheinlichkeiten

| Treffer | Anzahl Kombis | Wahrscheinlichkeit |
|---------|---------------|--------------------|
| bestimmter Drilling (z. B. 3× 💎) | 1 | 1/512 ≈ 0,195 % |
| bestimmtes Paar (Walze 1+2, von links) | 7 | 7/512 ≈ 1,367 % |

## Auszahlquote (RTP)

Brute-Force über alle 512 Kombinationen (Niete zahlt nie):

| Jackpot-Stand | EV/Spin | RTP |
|---------------|---------|-----|
| 500 (Minimum) | 6,21 | **62,1 %** |
| 1.000 | 7,19 | 71,9 % |
| 2.000 | 9,14 | 91,4 % |

Basis-RTP also **~62 %**, steigt mit wachsendem Jackpot → im Mittel um die angepeilten **~65 %**.

### Stellschrauben für die RTP

- **7️⃣-Paar (100)** ist der größte Einzel-Hebel (~10 Prozentpunkte).
- **Niete-Häufigkeit**: weitere Niete-/Blank-Symbole senken die RTP weiter (mehr Kombinationen ohne Gewinn).
- **Paar-Regel**: würde man Paare auch rechts/überall zählen, steigt die RTP deutlich (aktuell bewusst nur „von links").
