# Ideen — weitere Kartenspiele für MyPage

Sammlung möglicher Kartenspiele, die sich in die bestehende MyPage-Spielearchitektur
integrieren lassen (server-autoritativ, pro Mitglied vs. KI).

## Warum der Aufwand meist klein ist

Komplett wiederverwendbar pro neuem Spiel:

- Startbildschirm (Schwierigkeitswahl, „Fortsetzen", Zurück-Button)
- Cross-Device-Session-Schutz (claim / heartbeat / release)
- Persistenz pro Mitglied (`<spiel>_<uid>.json`)
- Verlauf + Statistik (Startbildschirm-Panel)
- HA-Sensoren (Live-Spielstatus)
- Knoll-Karten-Rendering, DE/EN-Lokalisierung, Dockerfile-Muster
- Mitgliederbereich-Kachel + `openGame(slug)`

Neu pro Spiel ist nur:

1. `game_<slug>.py` (Regel-Engine + KI)
2. Template (zu ~80 % aus `game_20ab.html` / `game_schwimmen.html` klonbar)
3. Routen in `app.py`, Locales, Regel-MD (DE/EN), Kachel in `member.html`

**Wichtigster „Gratis"-Faktor:** Das Knoll-Deck hat genau **32 Karten** (7–A, 4 Farben).
Alles, was damit auskommt, braucht **keine neuen Karten-Assets**. 36-Karten-Spiele
(Sechser) oder 52-Karten-Spiele bräuchten neue SVGs.

## Bereits umgesetzt

- **66 (Sechsundsechzig)**
- **20 AB (Zwanzig ab)**
- **Schwimmen (31)**

## Kandidaten nach Aufwand

### 🟢 Geringster Aufwand / bester Fit

- **Mau-Mau** — *Top-Empfehlung.* Nutzt exakt das 32er-Deck, Regeln simpel &
  deterministisch, KI trivial gut (greedy + Heuristiken), in DE extrem bekannt.
  Einziges Neue ggü. den Stich-Spielen: Ablage-/Nachziehstapel statt Stich
  (die „play-area" ist dafür flexibel). Sonderkarten: 7 = zwei ziehen,
  8 = aussetzen, Bube = Wunsch, Ass = nochmal.
- **Sedma** (tschechisches „Siebener-Stechen") — 32 Karten, Stich-Mechanik
  praktisch identisch zu 20AB/Schwimmen → Template fast 1:1. Regeln minimal
  (gleicher Rang oder 7 sticht), KI einfach. „Schnellschuss".

### 🟡 Mittlerer Aufwand, hoher Spaßfaktor

- **Durak** — 32 Karten spielbar, Angreifen/Verteidigen-Mechanik, sehr beliebt.
  KI moderat, UI etwas eigener (mehrere Karten gleichzeitig auf dem Tisch).

### 🟠 Passt aufs Deck, aber spürbar mehr Arbeit

- **Skat** — passt aufs 32er-Deck, *das* deutsche Kartenspiel, aber 3-Hand +
  Reizen + anständige KI = deutlich größeres Projekt.
- **Watten** — Sonderrangfolgen/Weli, mehr Regel-Edgecases.

### 🔴 Eher nicht „ohne Aufwand"

- **Jass / Schieber** — braucht 36 Karten (4 neue Sechser-SVGs) + komplexe KI.
- **Hearts / Herzeln** — 52-Karten-Deck → komplett neue Assets.

## Empfehlung

Wenn als Nächstes eins gebaut wird: **Mau-Mau** zuerst (höchster Spaß-pro-Aufwand,
kein neues Material), optional **Sedma** als schnelle Ergänzung, weil es das
vorhandene Stich-Template fast unverändert wiederverwendet.
