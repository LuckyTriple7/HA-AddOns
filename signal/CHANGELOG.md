# Changelog

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
