# WhatsApp

WhatsApp Web als persistente Session direkt in Home Assistant — mit Web-UI, REST-API und Webhook-Support.

## Funktionen

- **QR-Login**: Einmalig QR-Code scannen, Session bleibt dauerhaft erhalten
- **Web-UI**: Status, QR-Anzeige und Nachrichten senden direkt in der HA-Sidebar
- **REST-API**: Nachrichten aus Automatisierungen heraus senden
- **Webhook**: Eingehende Nachrichten an eine URL weiterleiten (z.B. HA Webhook-Trigger)

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `webhook_url` | — | URL für Bestätigung gesendeter Nachrichten |
| `webhook_incoming` | — | URL für eingehende Nachrichten (HA-Webhook-Trigger) |
| `initial_chats` | 30 | Anzahl Chats die beim Start geladen werden |
| `initial_messages` | 20 | Nachrichten pro Chat die beim Start geladen werden |

## REST-API

### Status abfragen
```
GET /api/status
→ {"status": "connected", "phone": "4915123456789"}
```

### Nachricht senden
```
POST /api/send
{"to": "4915123456789", "message": "Hallo aus HA!"}
→ {"success": true, "id": "..."}
```

### Abmelden
```
POST /api/logout
```

## HA-Automatisierung (Beispiel)

```yaml
action:
  - service: rest_command.whatsapp_send
    data:
      to: "4915123456789"
      message: "Bewegung erkannt!"
```

`configuration.yaml`:
```yaml
rest_command:
  whatsapp_send:
    url: http://localhost:3000/api/send
    method: POST
    content_type: application/json
    payload: '{"to": "{{ to }}", "message": "{{ message }}"}'
```

## Hinweise

- Erfordert ein WhatsApp-Konto auf einem Smartphone
- Inoffizielle API (whatsapp-web.js) — für den persönlichen Gebrauch
- Session überlebt Add-on-Updates und Neustarts
