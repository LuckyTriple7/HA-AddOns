# Changelog

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
