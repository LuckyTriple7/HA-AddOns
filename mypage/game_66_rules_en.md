# 66 (Sixty-Six) — Rules

As implemented in the MyPage add-on (20-card variant against the AI).
For technical details see [66.md](66.md).

## Cards & Values

- **20 cards** (no nines): Ace, Ten, King, Queen, Jack in 4 suits.
- Points: **Ace 11 · Ten 10 · King 4 · Queen 3 · Jack 2** → **120 points** in total.
- Important: the **Ten is the second-highest card** (above King/Queen/Jack).

## Start of play (the cut)

- Before the first deal **each player draws a card**. Whoever draws the **higher**
  card **leads** (plays first); the other deals.
- On an **equal rank** the **suit** decides:
  **Clubs < Diamonds < Hearts < Spades** (Spades highest).

## Dealing & the lead

- Each player gets **5 cards**. The remaining 10 form the **talon**; the
  **bottom card is turned face up** and sets the **trump suit**.
- The first deal is led by the **winner of the cut**. In **subsequent deals**
  the **winner of the previous game** leads (the loser deals).

## Phase 1 — talon open

- **No obligation to follow suit, no obligation to win.** You may play **any
  card**, even if you hold the suit that was led.
- Winning a trick: a higher card of the same suit; **trump beats** any
  non-trump card; a different suit without trump loses automatically.
- Whoever wins the trick **draws first** from the talon, then the loser.
  The winner of the trick leads again.

## Special actions (only while **you are leading**)

- **Declaring a marriage (20 / 40):** King **and** Queen of the same suit in
  hand → when leading one of the two, declare it: **20 points** (normal) or
  **40 points** (trump suit).
  - ⚠️ The points **only count once you have won at least one trick**.
- **Exchanging the trump Jack:** swap the **Jack of the trump suit** for the
  face-up trump card (as long as **at least 2 cards** remain in the talon).
  Here (without nines) the Jack is the lowest trump card.
- **Closing the talon:** close the talon → **Phase 2** starts immediately,
  **no more drawing**.

## Phase 2 — talon closed **or** played out

When following now, obligations apply, in this order:

1. **Follow suit** — serve the suit that was led.
2. **Must win** — if you can go **higher** in the suit, you **must**.
3. No card of the suit? **Must trump** — you have to play trump.
4. Neither suit nor trump? Any card.

## Winning a game (66 points)

- If you reach **66 points** (tricks + counting marriages) **and have won at
  least one trick**, the game ends immediately in your favour.
- This is **detected automatically** — no need to call "66!", no miscounting.

## Scoring a game → game points (1 / 2 / 3)

| Situation | Points for the winner |
|---|---|
| Opponent has **33–65** points | **1** |
| Opponent has **1–32** points (*Schneider*) | **2** |
| Opponent has **no trick** (*Schwarz*) | **3** |
| Nobody reaches 66, talon empty → **winner of the last trick** | **1** |

**When the talon is closed**, additionally:

- **Closer reaches 66:** scored by the **opponent's point total at the moment
  of closing** (snapshot) → 1 / 2 / 3 per the table above.
- **Closer misses 66:** the opponent gets **2** points — or **3** if the
  opponent had **not yet won a trick** when the talon was closed.

## Match (Bummerl)

- The first to reach **7 game points** wins the match.
- Afterwards the loser of the game deals, the other (the winner) leads.

## AI difficulty

Selectable via the **🎚 menu** (changing it starts a new match):

- **Easy** — the AI makes mistakes more often and plays carelessly.
- **Medium** — solid play with the occasional blunder.
- **Hard** — full strength, consistently the best strategy.
- **Adaptive** — adjusts itself: if you win, the AI gets stronger; if you lose,
  weaker. The current strength is shown at the top as a percentage.

---

# "Andy's Grandma" variant

Toggled in the game via the ⚖ menu. Changing the rules **starts a new
match**. Differences from the standard rules:

- **No early going-out.** The game is **always played to the end** (all cards
  gone), only then are the points counted. Even a marriage that takes you past
  66 does **not** end the game immediately.
- **Winner of the game:** whoever has **66+ points** at the end wins. If
  **nobody** does (e.g. 65:55), the **winner of the last trick** wins.
- **Game points** as usual, by the loser's points: 0 → **3**, < 33 → **2**,
  ≥ 33 → **1**.
- **Closing the talon** is still possible; the closer must **reach 66**,
  otherwise the opponent gets **3** points. If they succeed, it scores
  **1/2/3** by the opponent's current points.

Phases (follow-suit only after closing / empty talon), values, marriages,
the trump exchange and the cut remain unchanged.

---

## Common deviations to keep in mind

1. **Phase 1 with no follow-suit obligation at all** — obligations only after
   closing / empty talon.
2. **5 cards each** (because there are no nines) instead of 6.
3. **A marriage only counts once you have your own trick** (standard).
4. **Snapshot scoring when closing the talon** (standard).
5. The trump exchange uses the **Jack** (instead of Seven / Nine).
6. **"Andy's Grandma"** as a variant: no going-out, always played to the end.
