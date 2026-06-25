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

---

# Multiplayer (Mensch gegen Mensch, live)

Idee: die bestehenden Kartenspiele (und Jeopardy) live gegen andere **menschliche
Mitglieder** spielbar machen. Ehrliche Einordnung: **machbar, aber ein eigenes
Projekt** – das aktuelle Modell ist fundamental Einzelspieler (server-autoritativ
**pro Mitglied** vs. KI).

## Was schon trägt (wiederverwendbar)

- Engines sind **server-autoritativ und mehrsitzig** (MauMau/Präsident = 3 Spieler,
  nur eben 1 Mensch + KI) → ~70 % der Spiellogik steht.
- Mitglieder-Auth, Karten-Rendering, Statistik/HA-Sensoren, Regeln, Persistenz-
  und Session-Muster.

## Die eigentlichen Kostentreiber (neu)

1. **Geteilter Spielzustand** statt pro Mitglied. Heute hat jedes Mitglied seine
   eigene `<spiel>_<uid>.json`; Multiplayer braucht **einen** geteilten Tisch →
   Raum-/Tisch-Verwaltung (anlegen, beitreten, Sitze, Lebenszyklus).
2. **Echtzeit-Übertragung.** Heute „ich ziehe → ich pulle die KI-Schritte". Gegen
   Menschen müssen **fremde Züge zu dir gepusht** werden. Optionen:
   - **Short-Polling (alle 1–2 s)** – *Empfehlung*: keine neue Abhängigkeit, läuft
     über HA-Ingress **und** Cloudflare-Tunnel ([[project_pwa_cloudflare]]); für
     rundenbasierte Kartenspiele ist 1–2 s Latenz völlig ok.
   - SSE/Long-Polling – flüssiger, mehr Plumbing.
   - WebSockets – am saubersten, aber neue Abhängigkeit und über HA-Ingress fummelig.
3. **Per-Spieler-Sicht.** `public_view` redigiert heute für *einen* Zuschauer
   ('p'); für N Menschen braucht es einen `viewer`-Parameter pro Engine (jeder
   sieht nur seine Hand) – moderater Umbau je Spiel.
4. **Sitz↔Mitglied + Zug-Autorisierung.** Jeder Zug prüft: ist dieses Mitglied am
   Zug auf diesem Sitz?
5. **Disconnect/Timeout – der eigentliche Brocken.** Ein Mensch verschwindet
   mitten im Spiel: Timeout, KI-Übernahme oder Pause, Reconnect, Abbruch. Macht
   Multiplayer *deutlich* schwerer als Singleplayer.
6. **Client-Schleife & UI** pro Template: Lobby, „warte auf Spieler X", echte
   Gegnernamen, Reconnect-Zustand. Die KI-Pull-Schleife entfällt.

## Aufwand

| Umfang | Was | Aufwand |
|---|---|---|
| 🟡 **Pilot** | **1 Spiel** (MauMau – simpelste, schon 3-Sitz-Engine), Short-Polling, einfache Lobby, Zug-Auth, Per-Spieler-Sicht, Disconnect grob (Timeout → KI übernimmt) | mittel-groß |
| 🟠 **Voll** | Alle 5 Spiele, sauberes Reconnect/Disconnect, Matchmaking/Einladungen, evtl. SSE/WS, Chat | groß (mehrere Bauabschnitte) |

Die **Raum-/Lobby-/Polling-Schicht baut man einmal generisch** und hängt die
Spiele dann nacheinander rein (wie beim Spiele-Import-Rezept). Der Pilot ist die
eigentliche Investition, Spiel 2–5 danach sind günstig.

## Empfehlung (Multiplayer)

**MauMau als Pilot mit Short-Polling.** Beweist die ganze Architektur (Raum,
geteilter State, Per-Spieler-Sicht, Zug-Auth, Disconnect-Grundfall) mit dem
geringsten Spiel-Risiko und ist robust gegenüber Ingress/Cloudflare. Der ehrliche
Mehraufwand steckt nicht im „Zug machen", sondern in **Lobby + Disconnect-
Robustheit**.

---

# Produkt-Verbesserungen (keine Spiele)

Ideen abseits der Spiele. Bereits umgesetzt (v0.7.63): **Lesezeit & ähnliche
Beiträge**, **Speicher-Balken mit Warnfarben**, **wöchentlicher Statistik-
Rückblick**, **DSGVO-Self-Service** (Datenexport + Konto-Selbstlöschung).

## 🟢 Schnelle Gewinne

- **Auto-OG-Image pro Blog-Beitrag** — Hat ein Beitrag kein Titelbild, ein
  Share-Vorschaubild aus Titel + Akzentfarbe rendern (Pillow ist schon im Stack).
  Bessere Teilen-Vorschau ohne manuelle Arbeit. *Kleiner, abgegrenzter Umfang.*

## 🟡 Mittlerer Aufwand

- **Web-Push-Benachrichtigungen** — *Höchster Nutzer-Effekt.* Die PWA-
  Infrastruktur (Service Worker, Cloudflare, siehe [[project_pwa_cloudflare]])
  steht bereits; nur E-Mail-Newsletter wird genutzt. Push für „neuer Blog-
  Beitrag" / „neue DM" wäre ein großer Bindungs-Hebel (VAPID-Keys +
  `pushManager`). Funktioniert über den Cloudflare-Tunnel; bei HA-Ingress
  eingeschränkt. **Empfehlung, wenn als Nächstes _ein_ Feature gebaut wird.**
- **Öffentliche Freigabe-Links für Mitglieder-Dateien** — Mitglied teilt eine
  Datei aus seinem Bereich per Einmal-/Ablauf-Link (optional passwortgeschützt)
  mit Externen. Macht aus dem Dateibereich ein „WeTransfer light". Nutzt die
  vorhandene Quota-/Speicher-Schicht.

## 🟠 Strategisch (kein User-Feature, zahlt sich aber aus)

- **`app.py` refaktorieren** — Die Datei ist inzwischen **~8.300 Zeilen**. Eine
  Aufteilung in Flask-Blueprints (`public`, `admin`, `member`, `games`) würde
  Wartbarkeit und Testbarkeit deutlich verbessern und CodeQL-/Autofix-Risiken
  entschärfen (siehe [[feedback_codeql_autofix_danger]]). Zahlt sich bei jedem
  weiteren Spiel/Feature aus.
- **Test-Abdeckung erhöhen** — Aktuell nur `test_game66.py`. Ein paar Tests für
  die sicherheits­kritischen Auth-/Redirect-Pfade (siehe
  [[feedback_security_patterns]]) fangen Regressionen früh — passt zu „nicht
  blind iterieren" ([[feedback_no_blind_iteration]]).

## Bewusst nicht umgesetzt (existiert bereits)

- **RSS/Atom-Feed**, **OpenGraph-/Twitter-Cards**, **Datei-Vorschau im
  Mitglieder­bereich** — sind im Code schon vorhanden, daher keine neuen Ideen.
