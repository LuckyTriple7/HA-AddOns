# Changelog

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
