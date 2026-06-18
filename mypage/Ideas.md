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

## Empfehlung (Kartenspiele)

Wenn als Nächstes eins gebaut wird: **Mau-Mau** zuerst (höchster Spaß-pro-Aufwand,
kein neues Material), optional **Sedma** als schnelle Ergänzung, weil es das
vorhandene Stich-Template fast unverändert wiederverwendet.

---

# Würfelspiele

Sind ebenfalls gut machbar — eher **einfacher** als Kartenspiele:

- Dasselbe Gerüst ist wiederverwendbar (server-autoritativ pro Mitglied,
  Startbildschirm, Resume, Session-Schutz, Verlauf/Statistik, HA-Sensoren,
  DE/EN, Dockerfile).
- **Kein Asset-Aufwand:** Würfelaugen als reine CSS-Punkte oder Unicode
  (⚀⚁⚂⚃⚄⚅) darstellbar — kein Bildmaterial nötig.
- Neu pro Spiel: eigenes Template (Würfel + Wertungsblock statt Hand/Tisch) und
  die Regel-/KI-Logik. Würfel-KI ist meist simpler als Karten-KI (nur eine
  Strategie „behalten / neu würfeln / stoppen", kein Gegnerhand-Tracking).

## Kandidaten nach Aufwand

### 🟢 Schnellschüsse

- **Schwein (Pig)** — 1 Würfel, „weiter oder sichern", trivial. Ideales Mini-Spiel.
- **Zehntausend / Farkle** — 6 Würfel, Kombi-Wertung, Push-your-luck. Einfache
  KI (Risiko-Schwelle), wenig Code, hoher Suchtfaktor.

### 🟢/🟡 Top-Empfehlung

- **Kniffel (Yahtzee)** — *der Klassiker in DE.* 5 Würfel, 3 Würfe,
  Wertungsblock. Wertungslogik deterministisch, KI heuristisch machbar
  (optimal bräuchte Erwartungswerte). Hauptarbeit = Wertungsblock im UI.
  Klar abgegrenzter Umfang, sehr bekannt.

### 🟡 Mit Reiz: versteckte Information

- **Mäxchen / Mia (Meiern)** — Bluff-Spiel, 2 Würfel, Lügen-Mechanik. Passt
  perfekt zum server-autoritativen Modell (Server kennt den echten Wurf,
  Spieler blufft). KI-Bluff moderat.
- **Schocken** — beliebtes Kneipenspiel, 3 Würfel, eigene Rangfolge, etwas
  mehr Regel-Edgecases.

## Einordnung

- Template-Wiederverwendung etwas geringer als bei Kartenspielen (Würfel-UI
  statt Hand/Tisch), dafür **kein Asset-Aufwand**.
- Statistik/HA-Sensoren funktionieren unverändert (Sieg/Niederlage vs. KI). Bei
  einem reinen Solo-Highscore-Spiel müsste „Sieg" anders definiert werden — bei
  „vs. KI" bleibt alles wie gehabt.

## Empfehlung (Würfelspiele)

**Kniffel** als Flaggschiff, **Schwein** oder **Farkle** als schnelle Ergänzung.

---

# Quizspiele

Bereits umgesetzt: **Fangfragen** (Mini-Game, 50 Scherz-/Fangfragen, Multiple
Choice, DE/EN). Quizspiele sind code-seitig meist günstig — **der eigentliche
Aufwand ist der Fragen-Pool**: Pflege, Kategorien, saubere DE/EN-Trennung und
das Vermeiden veraltender „richtiger" Antworten. Das ist das entscheidende
Kriterium für die Einordnung unten.

## 🟢 Mini-Game-Liga (clientseitig, über Footer-Link — wie Fangfragen)

- **Wahr oder Falsch** — *Top-Empfehlung für klein.* Eine Aussage, zwei Buttons,
  Streak-Zähler („7 in Folge!"). Schnell gebaut, hoher Suchtfaktor, Pool trivial
  erweiterbar.
- **Schätzfragen** — „Wie hoch ist der Eiffelturm?" → je näher dran, desto mehr
  Punkte. Charmant, weil nie „falsch", nur „knapp". Kein Multiple-Choice nötig.
- **Flaggen-/Hauptstädte-Quiz** — Flaggen als Emoji (🇫🇷🇯🇵 → **kein
  Asset-Aufwand**), Antworten als Multiple Choice. Zeitloser, riesiger Pool.
- **Emoji-Rätsel** — 🦁👑 → „König der Löwen". Sehr lustig, aber DE/EN-Antworten
  müssen sauber getrennt sein (Filmtitel etc. unterscheiden sich).

## 🟡 Mittlerer Aufwand, eigener Modus

- **„Wer wird Millionär"-Style** (Solo-Highscore) — 15 Fragen mit steigender
  Schwierigkeit, Joker (50:50, Publikum, Zufall), Sicherheitsstufen,
  Gewinnstufe = Score. In DE extrem bekannt, klar abgegrenzter Umfang. Braucht
  einen **geschichteten** Fragen-Pool (leicht → schwer).

## 🟠 Die „großen" — passen in die Mitglieder-Spielarchitektur

Höchster Wiederverwendungsgrad: server-autoritativ, Persistenz pro Mitglied,
Verlauf/Statistik, HA-Sensoren, Fortsetzen, DE/EN — alles vorhanden.

- **🏆 Quiz-Duell gegen die KI** — *Top-Empfehlung für „größer".* Exakt das
  Muster der Kartenspiele, nur mit Wissensfragen: Runden, Kategorie-Wahl, die KI
  „antwortet" mit schwierigkeitsabhängiger Trefferquote (Level easy/mittel/
  schwer). Sieg/Niederlage vs. KI → **Statistik & HA-Sensoren ohne
  Zusatzarbeit**. Server kennt die richtige Antwort (kein clientseitiges
  Cheating) — passt perfekt zum server-autoritativen Modell.
- **📅 Tägliches Quiz / Daily Challenge** — jeden Tag dieselben Fragen für alle,
  Mitglieder-Bestenliste, HA-Sensor „Heutiger Tagessieger". Bindung an die Seite,
  wenig Code, lebt vom Pool.
- **🤓 Personalisiertes „Über mich/diese Seite"-Quiz** — *origineller Sonderweg
  mit nahezu null Pflegeaufwand:* Fragen werden **automatisch aus den eigenen
  Inhalten generiert** (Projekte, importierte GitHub-Repos, Sprachen, Sterne),
  z. B. „Welches Projekt ist in Python?", „Wie viele Repos hat …?". Einzigartig
  für die jeweilige Seite, weil es bestehende Daten wiederverwendet.

## Einordnung (Pool-Pflege)

- **Niedrigster Pflegeaufwand:** Seiten-Quiz (generiert sich selbst) und
  Fangfragen/Schätzfragen (zeitlose Antworten).
- **Höchster Pflegeaufwand:** Quiz-Duell, „Millionär", Daily Challenge — leben
  von einem großen, korrekten, zweisprachigen Pool, der altern kann.
- HA-Sensoren/Statistik passen unverändert bei allem „vs. KI". Bei reinen
  Solo-Highscore-Varianten muss „Sieg" anders definiert werden (wie bei den
  Würfelspielen).

## Empfehlung (Quizspiele)

Klein: **Wahr oder Falsch** (Streak ist sofort befriedigend). Groß:
**Quiz-Duell gegen die KI** (maximaler Wiederverwendungsgrad der Infrastruktur)
oder, als cleverer Low-Maintenance-Hit, das **automatisch generierte
Seiten-Quiz**.
