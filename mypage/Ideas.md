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
- **Mau-Mau**
- **Präsident**
- Würfel: **Kniffel**, **Chicago** · Quiz: **Jeopardy vs. KI**, **Glücksrad**

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
Umgesetzt in v0.8.0: **Umfrage-Sektion**, **Spiele-Bestenliste**,
**Erfolge/Abzeichen**. Umgesetzt in v0.8.8–0.8.10: **atomare Schreibvorgänge +
Korruptionsschutz**, **automatische Tages-Backups mit Rotation**,
**Waitress statt Flask-Entwicklungsserver**.

## 🟢 Schnelle Gewinne

- **Auto-OG-Image pro Blog-Beitrag** — Hat ein Beitrag kein Titelbild, ein
  Share-Vorschaubild aus Titel + Akzentfarbe rendern (Pillow ist schon im Stack).
  Bessere Teilen-Vorschau ohne manuelle Arbeit. *Kleiner, abgegrenzter Umfang.*
- **Zwei-Faktor auch für Mitglieder** — Der Admin hat seit v0.7.21 TOTP samt
  Backup-Codes und „Gerät merken" (v0.8.4–0.8.7). Mitglieder haben nur ein
  Passwort, obwohl in ihrem Bereich private Dateien, verschlüsselte
  Direktnachrichten und Anhänge liegen. Die komplette Maschinerie ist da
  (`totp_verify`, QR-Erzeugung, `_gen_backup_codes`, Trusted-Device-Muster) —
  für Mitglieder wiederverwenden statt neu bauen, freiwillig pro Konto
  aktivierbar im Profil. *Überwiegend Wiederverwendung.*
- **vCard-Download & QR-Code der Seitenadresse** — `.vcf` aus den Profildaten
  erzeugen, dazu ein QR-Code zum Teilen der Adresse. `qrcode` liegt bereits für
  die 2FA-Einrichtung im Stack, das Profil hat alle Felder. Zwei kleine,
  abgegrenzte Häppchen mit sichtbarem Nutzen.

## 🟡 Mittlerer Aufwand

- **🏠 Home-Assistant-Daten auf der Seite anzeigen** — *Der eigentliche
  Alleinstellungs-Hebel.* Die HA-Anbindung ist heute eine **Einbahnstraße**:
  `push_ha_sensors()` / `push_ha_games()` melden Besucher- und Spielzahlen an HA,
  aber es wird nie etwas zurückgelesen. Dabei sind `homeassistant_api: true`,
  `SUPERVISOR_TOKEN` und die HTTP-Schicht längst vorhanden.
  Neue Sektion „Smart Home" mit frei wählbaren Entitäten: Außentemperatur,
  PV-Ertrag heute, Ladestand des Autos, „zu Hause / unterwegs". Wahlweise
  öffentlich oder **nur für Mitglieder** — bei diesen Daten ist die
  Privatsphäre-Umschaltung Pflicht; die Sektions-Mechanik (anordnen, ausblenden,
  nur-Mitglieder) gibt es schon.
  Das kann kein WordPress und kein Baukasten. Es ist der Punkt, an dem
  „Homepage als HA-Add-on" mehr wird als „Homepage, die zufällig in HA läuft".
  Zu beachten: Polling mit Cache (nicht bei jedem Seitenaufruf abfragen),
  Entitäts-Whitelist im Admin, sinnvolle Formatierung je Gerätetyp.
- **💾 Backups aus dem Haus schaffen** — Die automatischen Backups (v0.8.9)
  liegen unter `addon_configs/<slug>_mypage/autobackup/`, also auf **demselben
  Datenträger wie die Daten**. Stirbt die SD-Karte/SSD, sind beide weg — der
  klassische Fehler. Das tägliche ZIP zusätzlich per **WebDAV zur Nextcloud**
  (läuft als eigenes Add-on) oder auf eine **SMB-Freigabe** schieben; die
  Mount-Logik für die FritzBox existiert bereits
  ([[project_fritzbox_smb_noserverino]]). Erst damit wird aus „Backup vorhanden"
  ein echtes Backup. Rotation ist schon gebaut; neu sind Upload, Zugangsdaten in
  den Optionen und Fehlerbehandlung mit HA-Benachrichtigung.
  **Empfehlung: das zuerst — Absicherung vor Schmuck.**
- **Web-Push-Benachrichtigungen** — *Höchster reiner Nutzer-Effekt.* Die PWA-
  Infrastruktur (Service Worker, Manifest) steht bereits; genutzt wird bisher nur
  der E-Mail-Newsletter. Push für „neuer Blog-Beitrag" / „neue DM" wäre ein
  großer Bindungs-Hebel (VAPID-Keys + `pushManager`).
  *Achtung:* Frühere Fassung dieses Eintrags behauptete, das laufe „über den
  Cloudflare-Tunnel" — **MyPage läuft nicht hinter Cloudflare**, der öffentliche
  Port hängt hinter einem Reverse-Proxy (siehe
  [[project_mypage_deployment_topology]]). Web-Push braucht lediglich HTTPS auf
  der öffentlichen Adresse, das liefert der Proxy. Über HA-Ingress bleibt es
  eingeschränkt. Die Cloudflare-Notiz [[project_pwa_cloudflare]] ist eine reine
  Technik-Referenz, keine Aussage über dieses Deployment.
- **Öffentliche Freigabe-Links für Mitglieder-Dateien** — Mitglied teilt eine
  Datei aus seinem Bereich per Einmal-/Ablauf-Link (optional passwortgeschützt)
  mit Externen. Macht aus dem Dateibereich ein „WeTransfer light". Nutzt die
  vorhandene Quota-/Speicher-Schicht.

## 🟠 Strategisch (kein User-Feature, zahlt sich aber aus)

- **`app.py` refaktorieren** — siehe detaillierten Backlog-Eintrag
  „app.py → Flask-Blueprints" ganz unten.
- **Test-Abdeckung erhöhen** — Aktuell nur `test_game66.py` (306 Zeilen) bei rund
  14.800 Zeilen Python. Ein paar Tests für die sicherheits­kritischen Auth-/
  Redirect-Pfade (siehe [[feedback_security_patterns]]) fangen Regressionen früh —
  passt zu „nicht blind iterieren" ([[feedback_no_blind_iteration]]).
  **Priorität allerdings anders setzen:** zuerst ein **Smoke-Test über alle ~212
  Routen** (Flask `test_client`, erwarteter Status-Code je Route). Der ist
  Voraussetzung fürs Blueprint-Refactoring unten *und* fängt genau die Klasse von
  Fehlern ab, die v0.7.33 gebrochen hat (vergessener `COPY` im Dockerfile,
  [[project_mypage_dockerfile_copy]]) — die merkt man sonst erst im laufenden
  Container. Danach die Auth-Pfade vertiefen.

## Bewusst nicht umgesetzt (existiert bereits)

- **RSS/Atom-Feed**, **OpenGraph-/Twitter-Cards**, **Datei-Vorschau im
  Mitglieder­bereich** — sind im Code schon vorhanden, daher keine neuen Ideen.
- **Geplante Blog-Veröffentlichung** — existiert bereits: Beiträge kennen neben
  „Entwurf"/„Veröffentlicht" den Status `scheduled` (Datum in der Zukunft).

---

# Backlog: `app.py` → Flask-Blueprints (Refactoring)

*Stand der Analyse: 2026-07-02, app.py = 8.342 Zeilen, ~212 Routen.*
*Nachgemessen 2026-08-02: 8.887 Zeilen, 218 Routen — die Datei wächst weiter,
das Argument wird also mit jedem Monat stärker, nicht schwächer.*

## Warum

1. **Jede Änderung berührt dieselbe Riesendatei** — jeder Diff, jeder
   Merge-Konflikt zwischen dev und main landet in app.py. Genau das
   Autofix-Risiko aus [[feedback_codeql_autofix_danger]]: ein automatischer
   Fix auf einer 8.000-Zeilen-Datei kann still eine alte Version drüberbügeln.
   Kleine Dateien begrenzen den Schaden auf einen Bereich.
2. **Suchkosten** — jede Session muss erst die richtige von vielen fast
   identischen Stellen finden (9 Spiele mit gleichem Routen-Muster).
3. **Nicht testbar** — Routen hängen an Import-Seiteneffekten; nach der
   Aufteilung kann ein Test gezielt ein Blueprint auf eine Test-App registrieren.

## Ist-Zustand (Routen-Verteilung)

| Bereich | Routen | Anmerkung |
|---|---|---|
| Spiele-APIs (`/api/<spiel>/…`) | ~84 | 9 Spiele + Slot; Muster fast identisch (state/claim/heartbeat/release/action) |
| Mitgliederbereich (`/bereich/…`) | ~29 | Login, Dateien, DMs, Profil, DSGVO |
| Admin (`admin_app`, eigener Port 17761) | ~66 | Site-Config, Newsletter, 2FA, Kommentare |
| Öffentlich (Blog, Suche, Feeds, Formulare, …) | ~33 | |

Wichtig: Die **Spiel-Engines sind schon getrennt** (`game_<slug>.py`) — nur
deren HTTP-Schicht liegt in app.py. Es gibt bereits **zwei** Flask-Apps
(`public_app` und `admin_app`) in einer Datei.

## Zielstruktur

```
mypage/
  app.py            ← nur noch: App-Setup, Config/Storage-Pfade, HA-Sensoren,
                       Blueprint-Registrierungen (~1.000 Z.)
  routes_public.py  ← Startseite, Blog, Suche, Feeds, Formulare
  routes_member.py  ← /bereich/* (Login, Dateien, DMs, Profil, DSGVO)
  routes_admin.py   ← alle admin_app-Routen
  routes_games.py   ← Spiele-Routen (oder je Spiel eine Datei, passend zum
                       game_<slug>.py-Muster)
  helpers.py        ← load_site/save_site, _safe_next, _clean_str,
                       current_member/_require_member, loc/i18n, …
```

Extra-Gewinn bei den Spielen: Die 9 Routen-Blöcke sind fast identisch → beim
Umzug eine **generische Blueprint-Factory** bauen („registriere Spiel X mit
Engine Y"). Neues Spiel braucht dann kaum noch Routen-Code; verkürzt die
Checkliste [[project_mypage_new_game_checklist]].

## Vorgehen (schrittweise, jede Stufe einzeln releasebar)

1. **Vorher: Smoke-Tests** — ein Test, der alle Routen mit erwartetem
   Status-Code anpingt (Flask test_client, ohne echten Server). Objektives
   „nichts abgefallen" nach jedem Schritt.
2. **Stufe 1: Spiele-Routen** raus (größter Block, klarste Grenze).
3. **Stufe 2: Admin-Routen** (eigene App, wenig Verflechtung mit public).
4. **Stufe 3: Mitgliederbereich**, dann Rest-Public.
5. Geteilte Helfer erst bei Bedarf nach `helpers.py` ziehen (nicht auf Vorrat).

## Stolperfallen

- **Zirkuläre Imports** — Helfer zuerst herauslösen, Blueprints importieren
  nur helpers, nie app.
- **Globale Zustände** — Modul-Level-Threads (HA-Push), In-Memory-Session-Dicts
  (`_game_sessions`, `user_sessions`) müssen in ein gemeinsames Modul.
- **Dockerfile:** jede neue Datei einzeln per `COPY` eintragen
  ([[project_mypage_dockerfile_copy]] — vergessen brach v0.7.33).
- Vorher Zombie-Dev-Server killen, sonst testet man alten Code
  ([[feedback_zombie_dev_servers]]).

## Wann

Am besten **vor** dem Multiplayer-Piloten (der bringt Lobby-/Raum-Routen mit,
die sonst wieder in app.py landen). Kein User-Feature — als eigene
Version ohne Funktionsänderung releasen.
