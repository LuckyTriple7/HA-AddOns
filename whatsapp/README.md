# WhatsApp

WhatsApp Web als persistente Session direkt in Home Assistant — mit Web-UI, REST-API und Webhook-Support.

## Funktionen

- **QR-Login**: Einmalig QR-Code scannen, Session bleibt dauerhaft erhalten
- **Web-UI**: Chat-Liste, Konversationen, Nachrichten senden/empfangen direkt in der HA-Sidebar
- **Fotos**: Empfangene Bilder anzeigen (optional, siehe `download_media`)
- **Nachrichten löschen**: Nachricht für alle entfernen (Hover → ✕)
- **Ungelesene-Badge**: Grüner Punkt in der Sidebar bei neuen Nachrichten
- **Emoji-Tastatur**: 😊-Button in der Eingabe
- **REST-API**: Nachrichten aus Automatisierungen heraus senden
- **Webhook**: Eingehende Nachrichten an eine URL weiterleiten

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `dark_mode` | `true` | `true` = dunkles Theme, `false` = helles Theme |
| `download_media` | `false` | Empfangene Fotos automatisch herunterladen und anzeigen (funktioniert nur zuverlässig bei neu eingehenden Nachrichten, nicht für historische Nachrichten) |
| `webhook_url` | — | URL für Bestätigung gesendeter Nachrichten |
| `webhook_incoming` | — | URL für eingehende Nachrichten (HA-Webhook-Trigger) |
| `initial_chats` | `30` | Anzahl Chats die beim Start geladen werden |
| `initial_messages` | `20` | Nachrichten pro Chat die beim Start geladen werden |
| `debug_mode` | `false` | Ausführliches Logging für die Fehlersuche |

## REST-API

```
GET  /api/status                     → { status, phone }
GET  /api/chats                      → [ { id, name, lastMsg, lastTime } ]
GET  /api/messages?chat=<id>         → [ { id, body, type, timestamp, fromMe } ]
POST /api/send                       → { to, message }
DELETE /api/messages/:chatId/:msgId  → Nachricht für alle löschen
POST /api/logout                     → Abmelden
POST /api/reset                      → Session zurücksetzen (neuer QR-Code)
```

### Nachricht senden

```bash
curl -X POST http://<HA-IP>:3000/api/send \
  -H "Content-Type: application/json" \
  -d '{"to": "4915123456789", "message": "Hallo aus HA!"}'
```

`to` kann eine Telefonnummer (nur Ziffern, ohne `+`) oder eine vollständige Chat-ID (`4915123456789@c.us`) sein.

### Webhook-Format (eingehende Nachrichten)

```json
{
  "from": "4915123456789@c.us",
  "body": "Nachrichtentext",
  "type": "chat",
  "timestamp": 1716123456
}
```

## HA-Automatisierung (Beispiel)

`configuration.yaml`:
```yaml
rest_command:
  whatsapp_send:
    url: http://localhost:3000/api/send
    method: POST
    content_type: application/json
    payload: '{"to": "{{ to }}", "message": "{{ message }}"}'
```

Automatisierung:
```yaml
action:
  - service: rest_command.whatsapp_send
    data:
      to: "4915123456789"
      message: "Bewegung erkannt!"
```

## Hinweise

- Erfordert ein WhatsApp-Konto auf einem Smartphone
- Basiert auf [whatsapp-web.js](https://github.com/pedroslopez/whatsapp-web.js) (inoffiziell, für den persönlichen Gebrauch)
- Session überlebt Add-on-Updates und Neustarts
- Medien werden in `/data/media/` gespeichert

→ [Changelog](CHANGELOG.md)
