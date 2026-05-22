# Changelog

## [1.1.13] - 2026-05-22

### Geändert
- **signal-cli-rest-api Version** — Binary direkt per `grep -a` nach eingebetteter Versionsnummer durchsucht (Go-Binaries enthalten die Version als lesbare Zeichenkette)

## [1.1.12] - 2026-05-22

### Geändert
- **signal-cli-rest-api Version im Log** — stdout+stderr werden gecaptured, Versionsmuster (`v0.0.0`) per grep extrahiert; falls kein Muster gefunden: „version unknown"

## [1.1.11] - 2026-05-22

### Geändert
- **signal-cli-rest-api Version im Log** — wird jetzt in `run.sh` direkt vom Binary abgefragt (`signal-cli-rest-api --version`); REST-API liefert keine Build-Versionsnummer

## [1.1.10] - 2026-05-22

### Geändert
- **signal-cli-rest-api Log** — zeigt echte Build-Version wenn vorhanden, sonst nur „bereit" (das Image liefert kein `build.version`)

## [1.1.9] - 2026-05-22

### Geändert
- **signal-cli-rest-api Version im Log** — Ausgabe verbessert: zeigt `build.version` wenn vorhanden, sonst `(API: v1, v2)` statt rohem Array-Join

## [1.1.8] - 2026-05-22

### Neu
- **signal-cli-rest-api Version im Log** — beim Start wird die API-Version geloggt: `[INFO] signal-cli-rest-api v0.x.x`

## [1.1.7] - 2026-05-22

### Neu
- **Sprachauswahl Deutsch / Englisch** — `🌐 DE` / `🌐 EN` Button in der Topbar; Einstellung wird im Browser gespeichert (Standard: Deutsch)
- Alle UI-Texte übersetzt: Buttons, Tooltips, Modals, Spinner, Datum/Uhrzeit-Format, Fehlermeldungen

## [1.1.6] - 2026-05-21

### Neu
- URLs in Nachrichten (`https://`, `http://`, `www.`) werden automatisch als anklickbare Hyperlinks dargestellt (öffnen im neuen Tab)

## [1.1.5] - 2026-05-20

### Neu
- **📥 Fotos nachladen**-Button im Chat-Header — lädt fehlende Bilder nach einem Neustart nach (nur sichtbar wenn `download_media: true`)

### Behoben
- `attId` wird jetzt im Message-Objekt gespeichert — Grundlage für das Nachladen nach Neustart
- Race Condition: `scheduleSave()` fehlte beim Early-Return in `downloadAttachment()` wenn die Datei bereits existierte

## [1.1.4] - 2026-05-20

### Behoben
- Gesendete Nachricht erschien verzögert — Poll läuft jetzt fire-and-forget im Hintergrund, `loadMessages()` wird sofort danach aufgerufen

## [1.1.3] - 2026-05-20

### Geändert
- Nach dem Senden einer Nachricht wird sofort ein Poll ausgelöst (statt auf den nächsten 10s-Zyklus zu warten) — ACK-Bestätigungen und Antworten erscheinen schneller

## [1.1.2] - 2026-05-20

### Behoben
- Unread-Dot erschien auch für den aktuell geöffneten Chat — Race Condition in `renderChats()` behoben: `lastSeenTime` wird beim jeden Poll-Zyklus für den aktiven Chat aktualisiert

## [1.1.1] - 2026-05-20

### Behoben
- Unread-Dot erschien nach eigenen gesendeten Nachrichten — `lastSeenTime` wird jetzt auch nach dem Senden aktualisiert
- Foto-Toggle-Button zeigt jetzt 📷 / 🚫 statt Text (wie WhatsApp und Telegram)

## [1.1.0] - 2026-05-20

### Neu
- **ACK-Status** für gesendete Nachrichten: ✓ gesendet, ✓✓ zugestellt (grau), ✓✓ gelesen (blau) — `receiptMessage`-Envelopes werden beim Polling ausgewertet, funktioniert in beiden Modi (native und default)
- **HA Notifications**: bei eingehenden Nachrichten wird eine persistente HA-Benachrichtigung erstellt (neue Optionen: `ha_notifications`, `ha_notifications_privacy`, `ha_token`)
- **Unread-Dots**: blauer Punkt in der Chat-Liste für Chats mit ungelesenen Nachrichten — bleibt über Seitenreloads erhalten (localStorage)
- **Media Cleanup**: 🗑️-Button in der Topbar löscht verwaiste Mediendateien (nur sichtbar wenn `download_media: true`)

### Behoben
- "Invalid Date" bei gesendeten Nachrichten — Timestamp aus signal-cli-REST-API wird jetzt immer als Number behandelt

## [1.0.39] - 2026-05-17

### Neu
- Speicheranzeige in der Topbar — zeigt den belegten Speicher des Add-on-Datenverzeichnisses in MB (💾 12.3 MB); aktualisiert sich automatisch alle 60 Sekunden

## [1.0.38] - 2026-05-17

### Neu
- Option `download_media` (Standard: aus) — empfangene Fotos werden heruntergeladen und in der Chat-Ansicht angezeigt; Klick vergrößert das Bild; ohne Option erscheint `📷 Foto` als Text
- „Fotos AN/AUS"-Schalter in der Topbar — blendet Fotos aus; Zustand wird im Browser gespeichert; erscheint nur wenn `download_media` aktiv
- Scroll-Buttons ↑ ↓ in der Topbar — springt direkt an den Anfang oder das Ende der Nachrichten
- Abmelden-Button als ⏻-Symbol (wie WhatsApp und Telegram)

### Geändert
- Topbar-Hintergrund auf Signal-Blau (#2c6bed) — passt zum Signal-Branding

## [1.0.37] - 2026-05-16

### Behoben
- Log-Format: Uhrzeit stand am Ende statt nach `[LEVEL]` — Regex trennt jetzt `[LEVEL]` vom Rest und fügt `[HH:MM:SS]` korrekt dazwischen ein

## [1.0.36] - 2026-05-16

### Geändert
- Log-Format einheitlich: alle Meldungen folgen `[LEVEL] [HH:MM:SS] Nachricht`

## [1.0.35] - 2026-05-16

### Geändert
- README aktualisiert — alle aktuellen Konfigurationsoptionen, REST-API-Endpunkte und Funktionen dokumentiert

## [1.0.34] - 2026-05-16

### Neu
- Option `debug_mode` (Standard: aus) — einschalten für ausführliches Logging: empfangene Envelopes mit Quelle/Inhalt, Duplikat-Erkennung, gespeicherte Nachrichten, Webhook-Aufrufe, gesendete und gelöschte Nachrichten; im Debug-Modus werden auch die GIN-Access-Logs von signal-cli-rest-api ungefiltert ausgegeben

## [1.0.33] - 2026-05-16

### Behoben
- GIN-Access-Logs vollständig unterdrückt — Output von signal-cli-rest-api wird durch grep gefiltert; `[GIN]`-Zeilen und `level=info`-Meldungen erscheinen nicht mehr im Log; Warnungen und Fehler bleiben sichtbar

## [1.0.32] - 2026-05-16

### Behoben
- Log-Spam reduziert — `GIN_MODE=release` unterdrückt die GIN-HTTP-Access-Logs von signal-cli-rest-api; periodische „Loaded X contacts/groups"-Meldungen entfernt

## [1.0.31] - 2026-05-16

### Behoben
- Löschen-Button wurde beim Hovern nicht rot — CSS-Spezifität von `html.dark .del-btn` überschrieb `.del-btn:hover`; `!important` behebt den Vorrang

## [1.0.30] - 2026-05-16

### Geändert
- Löschen funktioniert jetzt immer lokal (Nachricht verschwindet sofort aus der UI); plattformseitiges "Für alle löschen" wird im Hintergrund versucht — ältere signal-cli-rest-api-Versionen unterstützen das nicht, der lokale Delete läuft aber immer durch

## [1.0.29] - 2026-05-16

### Behoben
- Löschen-Symbol im Dark Mode nicht sichtbar — Emoji 🗑 ignoriert CSS `color`; ersetzt durch `✕` mit expliziter Farbsteuerung (grau im Ruhezustand, rot beim Hovern)

## [1.0.28] - 2026-05-16

### Behoben
- Dieselbe Person erschien nach Neustart in einem zweiten Chat — Telefonnummer wurde mal mit, mal ohne `+` gespeichert; `normPhone()` normalisiert jetzt einheitlich auf `+Prefix` und mergt bestehende Duplikate beim Start

## [1.0.27] - 2026-05-16

### Geändert
- Löschen-Button erscheint jetzt seitlich neben der Sprechblase (links bei gesendeten, rechts bei empfangenen Nachrichten) statt innerhalb der Blase

## [1.0.26] - 2026-05-16

### Neu
- Nachrichten löschen — Mülleimer-Symbol erscheint beim Hovern über eine Nachricht; sendet "deleteForEveryone" via signal-cli-rest-api

### Behoben
- "Abmelden"-Button tat nichts — `window.confirm()` in HA Ingress blockiert; Bestätigungsdialog entfernt

## [1.0.25] - 2026-05-16

### Geändert
- Sidebar-Icon auf `phu:signal` geändert

## [1.0.24] - 2026-05-16

### Geändert
- Sidebar-Icon auf `mdi:message-text` geändert

## [1.0.23] - 2026-05-16

### Geändert
- Sidebar-Icon auf `phu:signal` geändert (passend zum installierten Icon-Pack)

## [1.0.22] - 2026-05-16

### Behoben
- `dark_mode`/`native_mode` false hatte keinen Effekt — jq `//`-Operator behandelt `false` als leer; explizites `if`-Statement verwendet

## [1.0.21] - 2026-05-16

### Neu
- Option `dark_mode` (Standard: aus = heller Hintergrund) in den Add-on-Einstellungen — einschalten für dunkles Theme

## [1.0.20] - 2026-05-16

### Neu
- Emoji-Tastatur in der Chat-Eingabe — 😊-Button öffnet Picker mit ~100 Emojis; Klick fügt Emoji an der Cursor-Position ein

## [1.0.19] - 2026-05-16

### Geändert
- Port von 3002 auf 17777 geändert (3002 auf diesem System bereits belegt)

## [1.0.18] - 2026-05-16

### Neu
- Option `native_mode` (Standard: ein) in den Add-on-Einstellungen — ausschalten für den Java-Modus falls native Probleme macht
- Chat-Liste und Nachrichtenverlauf werden in `/data/chats.json` und `/data/messages.json` gespeichert und nach Neustart wiederhergestellt

### Behoben
- Chats nach Neustart leer — `chatMap` und `messagesByChatId` waren nur im Arbeitsspeicher; jetzt persistent auf der Disk

## [1.0.17] - 2026-05-16

### Behoben
- Session nicht persistent — falsche Umgebungsvariable `SIGNAL_CLI_CONFIG` statt `SIGNAL_CLI_CONFIG_DIR`; entrypoint.sh ignorierte den Pfad und schrieb immer nach `/home/.local/share/signal-cli`

## [1.0.16] - 2026-05-16

### Behoben
- Session nach Neustart verloren — Health-Check in run.sh erkannte /v1/accounts 500 (native mode braucht länger) als Datenfehler und löschte `/data/signal-cli`; Auto-Wipe entfernt

## [1.0.15] - 2026-05-16

### Geändert
- `MODE=native` wieder aktiviert für niedrige CPU-Auslastung; funktioniert jetzt korrekt da `SIGNAL_CLI_CONFIG` den richtigen Datenpfad setzt

## [1.0.14] - 2026-05-16

### Behoben
- QR-Code schlägt mit 400 fehl wenn Symlink auf `/home` gesetzt war — Ursache: Symlink verändert das Verhalten von signal-cli; stattdessen wird jetzt `SIGNAL_CLI_CONFIG=/data/signal-cli` als Umgebungsvariable gesetzt (kein Symlink mehr nötig)

## [1.0.13] - 2026-05-16

### Behoben
- Korrupte Daten in `/data/signal-cli` (von inkompatiblem Modus) führen zu 500/400 — beim Start wird `/v1/accounts` geprüft; bei 500 werden die Daten automatisch gelöscht und signal-cli neu gestartet

## [1.0.12] - 2026-05-16

### Behoben
- `MODE=native` gibt 400/500 zurück weil es kein Konto-Linking unterstützt — zurück auf Standard-Modus; reduzierte Polling-Intervalle bleiben zur CPU-Entlastung

## [1.0.11] - 2026-05-16

### Behoben
- QR-Code erscheint nicht — Timeout von 30s auf 120s erhöht (native-Modus braucht länger); automatischer Retry nach 5s; Fehlermeldung wird angezeigt statt stummes Warten

## [1.0.10] - 2026-05-16

### Behoben
- Session überlebt Neustart nicht — Symlink zeigte auf `/root/.local/share/signal-cli`, signal-cli schreibt aber als User `signal-api` nach `/home/.local/share/signal-cli`; Symlink korrigiert

## [1.0.9] - 2026-05-16

### Behoben
- Hohe CPU-Auslastung (~37%) — signal-cli läuft jetzt im `native`-Modus als Daemon (einmalig starten statt bei jedem API-Aufruf neu); Polling-Intervalle reduziert (checkStatus 60s wenn gelinkt, pollMessages 10s)

## [1.0.8] - 2026-05-16

### Neu
- Kontakte und Gruppen werden nach dem Verknüpfen automatisch geladen (`/v1/contacts`, `/v1/groups`) und in der Chat-Liste angezeigt
- Kontakte/Gruppen werden alle 60 Sekunden aktualisiert

## [1.0.7] - 2026-05-16

### Behoben
- `/v1/qrcodelink` gibt ein PNG-Bild zurück, kein Text-URI — Bild wird jetzt direkt als Data-URL angezeigt statt als QR-Code neu generiert zu werden

## [1.0.6] - 2026-05-16

### Behoben
- QR-Code: SVG wird jetzt direkt ins DOM injiziert statt als Base64-Data-URL — kein Skalierungsartefakt mehr
- QR-Code zeigt jetzt die rohe `sgnl://`-URI als Text (zur Kontrolle)
- Neuer "QR-Code neu laden"-Button zum Erzwingen eines frischen Codes

## [1.0.5] - 2026-05-16

### Behoben
- QR-Code immer noch unlesbar — PNG durch SVG ersetzt (vektorbasiert, immer scharf), Darstellungsgröße auf 320px erhöht

## [1.0.4] - 2026-05-16

### Behoben
- QR-Code zu klein und zu dicht zum Scannen — Fehlerkorrektur auf Stufe L gesenkt, Ausgabegröße auf 512px erhöht, Darstellung auf 280px vergrößert

## [1.0.3] - 2026-05-16

### Geändert
- Port von 3001 auf 3002 geändert (3001 auf manchen HA-Systemen bereits belegt)

## [1.0.2] - 2026-05-16

### Behoben
- signal-cli-rest-api band auf Port 3001 statt 8080 — `PORT` wird jetzt erst nach dem Start von `/entrypoint.sh` gesetzt
- Readiness-Check schlug bei HTTP 404 fehl — `curl -f` durch `curl -s` ersetzt

## [1.0.1] - 2026-05-16

### Geändert
- Port von 3000 auf 3001 geändert (Konflikt mit WhatsApp Add-on)

## [1.0.0] - 2026-05-16

### Erstveröffentlichung

- Signal Messenger Session via QR-Code verknüpfen (bestehendes Signal-Konto)
- Web-UI direkt in der HA-Sidebar (QR-Anzeige, Chat-Liste, Konversation)
- Chat-Liste mit letzter Nachricht und Zeitstempel
- Nachrichten senden und empfangen in Echtzeit
- Responsives Design für Desktop und Handy
- REST-API: `GET /api/status`, `GET /api/chats`, `GET /api/messages/:id`, `POST /api/send`
- Webhook für eingehende Nachrichten (konfigurierbare URL)
- Session-Persistenz unter `/data/signal-cli` (überlebt Neustarts)
- Basiert auf [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api)
