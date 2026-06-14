# 66 (Sechsundsechzig) — Spielregeln

So, wie das Spiel im MyPage-Add-on umgesetzt ist (20-Karten-Variante gegen die KI).
Technische Details siehe [66.md](66.md).

## Karten & Werte

- **20 Karten** (ohne Neuner): Ass, Zehn, König, Dame, Bube in 4 Farben.
- Augen: **Ass 11 · Zehn 10 · König 4 · Dame 3 · Bube 2** → zusammen **120 Augen**.
- Wichtig: Die **Zehn ist die zweithöchste Karte** (über König/Dame/Bube).

## Geben & Anspiel

- Jeder bekommt **5 Karten**. Die restlichen 10 bilden den **Talon**; die
  **unterste Karte wird aufgedeckt** und bestimmt die **Trumpffarbe**.
- Der **Nichtgeber (Vorhand) spielt aus**.

## Phase 1 — Talon offen

- **Kein Farbzwang, kein Stichzwang.** Du darfst **jede beliebige Karte**
  spielen, auch wenn du die angespielte Farbe hättest.
- Stich gewinnen: höhere Karte derselben Farbe; **Trumpf schlägt** jede
  Nicht-Trumpf-Karte; eine andere Farbe ohne Trumpf verliert automatisch.
- Wer den Stich gewinnt, **zieht zuerst** vom Talon, dann der Verlierer.
  Der Stichgewinner spielt neu aus.

## Sonderaktionen (nur wenn **du am Ausspielen** bist)

- **Hochzeit ansagen (20 / 40):** König **und** Dame derselben Farbe auf der
  Hand → beim Ausspielen einer der beiden ansagen: **20 Augen** (normal) bzw.
  **40 Augen** (Trumpf-Farbe).
  - ⚠️ Die Punkte **zählen erst, wenn du mindestens einen Stich** gemacht hast.
- **Trumpf-Buben tauschen:** den **Buben der Trumpffarbe** gegen die offen
  liegende Trumpfkarte tauschen (solange noch **mindestens 2 Karten** im Talon
  liegen). Der Bube ist hier (ohne Neuner) die niedrigste Trumpfkarte.
- **Zudrehen:** den Talon schließen → ab sofort **Phase 2**, es wird **nicht
  mehr nachgezogen**.

## Phase 2 — Talon zugedreht **oder** leergespielt

Beim Nachspielen gelten jetzt Zwänge, der Reihe nach:

1. **Farbzwang** — die angespielte Farbe bedienen.
2. **Stichzwang** — kannst du in der Farbe **höher** stechen, **musst** du.
3. Keine Farbe? **Trumpfzwang** — du musst trumpfen.
4. Weder Farbe noch Trumpf? Beliebige Karte.

## Partie gewinnen (66 Augen)

- Erreichst du **66 Augen** (Stiche + zählende Hochzeiten) **und hast mindestens
  einen Stich**, endet die Partie sofort zu deinen Gunsten.
- Das wird **automatisch erkannt** — kein „66!"-Ruf nötig, kein Verzählen.

## Wertung der Partie → Spielpunkte (1 / 2 / 3)

| Situation | Punkte für den Sieger |
|---|---|
| Gegner hat **33–65** Augen | **1** |
| Gegner hat **1–32** Augen (*Schneider*) | **2** |
| Gegner hat **keinen Stich** (*Schwarz*) | **3** |
| Niemand erreicht 66, Talon leer → **Sieger des letzten Stichs** | **1** |

**Beim Zudrehen** zusätzlich:

- **Zudreher erreicht 66:** Wertung nach dem **Augenstand des Gegners im Moment
  des Zudrehens** (Schnappschuss) → 1 / 2 / 3 nach obiger Tabelle.
- **Zudreher verfehlt 66:** Gegner bekommt **2** Punkte — bzw. **3**, wenn der
  Gegner beim Zudrehen **noch keinen Stich** hatte.

## Match (Bummerl)

- Wer zuerst **7 Spielpunkte** erreicht, gewinnt das Match.
- Danach gibt der Verlierer der Partie, der andere spielt aus.

---

## Häufige Abweichungen zur Erinnerung

1. **Phase 1 ganz ohne Farbzwang** — Zwang erst nach Zudrehen / leerem Talon.
2. **Je 5 Karten** (weil ohne Neuner) statt 6.
3. **Hochzeit zählt erst mit eigenem Stich.**
4. **Schnappschuss-Wertung beim Zudrehen.**
5. Trumpf-Tausch mit dem **Buben** (statt Sieben / Neun).
