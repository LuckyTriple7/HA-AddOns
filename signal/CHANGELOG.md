# Changelog

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
