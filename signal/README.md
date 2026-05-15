# Signal Messenger Add-on

Signal Messenger direkt in Home Assistant — bestehendes Signal-Konto verknüpfen, Nachrichten senden und empfangen, Webhook für Automatisierungen.

## Voraussetzungen

- Ein aktives Signal-Konto auf deinem Handy
- amd64 oder aarch64 Hardware

## Einrichtung

1. Add-on installieren und starten
2. In der HA-Sidebar "Signal" öffnen
3. QR-Code mit Signal-App scannen: **Einstellungen → Verknüpfte Geräte → Gerät hinzufügen**
4. Fertig — die Session bleibt über Neustarts erhalten

## Konfiguration

| Option | Beschreibung |
|---|---|
| `phone_number` | Deine Signal-Nummer (optional, wird automatisch erkannt) |
| `webhook_incoming` | URL für eingehende Nachrichten (HA-Webhook-Trigger) |

## REST-API

| Endpoint | Methode | Beschreibung |
|---|---|---|
| `/api/status` | GET | Status und verknüpfte Nummer |
| `/api/chats` | GET | Liste der Chats |
| `/api/messages/:id` | GET | Nachrichten eines Chats |
| `/api/send` | POST | Nachricht senden |

### Nachricht senden

```bash
curl -X POST http://<HA-IP>:3000/api/send \
  -H "Content-Type: application/json" \
  -d '{"to": "+49123456789", "message": "Hallo!"}'
```

### Webhook-Format

```json
{
  "from": "+49123456789",
  "name": "Max Mustermann",
  "message": "Hallo!",
  "timestamp": 1716123456789
}
```

## HA-Automatisierung (Nachricht senden)

```yaml
service: rest_command.signal_send
data:
  message: "Bewegung erkannt!"
  to: "+49123456789"
```

```yaml
rest_command:
  signal_send:
    url: "http://localhost:3000/api/send"
    method: POST
    content_type: "application/json"
    payload: '{"to": "{{ to }}", "message": "{{ message }}"}'
```

## Hinweise

- Basiert auf [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api)
- Das Konto wird als verknüpftes Gerät hinzugefügt, nicht als Primärgerät registriert
- Zum Abmelden: Button "Abmelden" in der UI, danach auch in Signal unter Verknüpfte Geräte entfernen

---

# Signal Messenger Add-on (English)

Signal Messenger directly in Home Assistant — link your existing Signal account, send and receive messages, webhook for automations.

## Requirements

- An active Signal account on your phone
- amd64 or aarch64 hardware

## Setup

1. Install and start the add-on
2. Open "Signal" in the HA sidebar
3. Scan the QR code with the Signal app: **Settings → Linked Devices → Link a Device**
4. Done — the session persists across restarts

## Configuration

| Option | Description |
|---|---|
| `phone_number` | Your Signal number (optional, auto-detected) |
| `webhook_incoming` | URL for incoming messages (HA webhook trigger) |

## REST API

| Endpoint | Method | Description |
|---|---|---|
| `/api/status` | GET | Status and linked number |
| `/api/chats` | GET | List of chats |
| `/api/messages/:id` | GET | Messages of a chat |
| `/api/send` | POST | Send a message |

→ [Changelog](CHANGELOG.md)
