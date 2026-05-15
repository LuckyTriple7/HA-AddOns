# Changelog

## [1.0.0] - 2026-05-15

### Erstveröffentlichung

- WhatsApp Web Session mit persistentem Login (QR-Code einmal scannen)
- Web-UI direkt in der HA-Sidebar (QR-Anzeige, Status, Nachricht senden)
- REST-API: `GET /api/status`, `POST /api/send`, `GET /api/qr`, `POST /api/logout`
- Webhook für eingehende Nachrichten (konfigurierbare URL)
- Webhook für gesendete Nachrichten (konfigurierbare URL)
- Session-Persistenz über Add-on-Updates hinweg
