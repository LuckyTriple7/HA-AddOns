# Signal Messenger Add-on

Signal Messenger direkt in Home Assistant — bestehendes Signal-Konto verknüpfen, Nachrichten senden und empfangen, Webhook für Automatisierungen.

## Funktionen

- **QR-Login**: Einmalig QR-Code scannen, Session bleibt dauerhaft erhalten
- **Web-UI**: Chat-Liste, Konversationen, Nachrichten senden/empfangen direkt in der HA-Sidebar
- **Nachrichten löschen**: Lokal sofort entfernt; platform-seitiges "Für alle löschen" wird im Hintergrund versucht (erfordert aktuelle signal-cli-rest-api)
- **Ungelesene-Badge**: Grüner Punkt in der Sidebar bei neuen Nachrichten
- **Emoji-Tastatur**: 😊-Button in der Eingabe
- **Persistente Session**: Kein erneutes Verknüpfen nach Neustart
- **REST-API**: Nachrichten aus Automatisierungen heraus senden
- **Webhook**: Eingehende Nachrichten an eine URL weiterleiten

## Voraussetzungen

- Ein aktives Signal-Konto auf deinem Handy
- amd64 oder aarch64 Hardware

## Einrichtung

1. Add-on installieren und starten
2. In der HA-Sidebar "Signal" öffnen
3. QR-Code mit Signal-App scannen: **Einstellungen → Verknüpfte Geräte → Gerät hinzufügen**
4. Fertig — die Session bleibt über Neustarts erhalten

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `phone_number` | — | Deine Signal-Nummer (optional, wird automatisch erkannt) |
| `dark_mode` | `false` | `true` = dunkles Theme, `false` = helles Theme |
| `native_mode` | `true` | `true` = nativer Modus (niedrige CPU-Last), `false` = Java-Modus |
| `webhook_incoming` | — | URL für eingehende Nachrichten (HA-Webhook-Trigger) |
| `debug_mode` | `false` | Ausführliches Logging inkl. GIN-Access-Logs für die Fehlersuche |

## REST-API

```
GET  /api/status                     → { status, phone }
GET  /api/chats                      → [ { id, name, lastMsg, lastTime } ]
GET  /api/messages/:chatId           → [ { id, body, timestamp, fromMe } ]
POST /api/send                       → { to, message }
DELETE /api/messages/:chatId/:msgId  → Nachricht lokal löschen (+ Versuch "Für alle")
POST /api/logout                     → Abmelden
```

### Nachricht senden

```bash
curl -X POST http://<HA-IP>:17777/api/send \
  -H "Content-Type: application/json" \
  -d '{"to": "+4915123456789", "message": "Hallo aus HA!"}'
```

`to` ist die Telefonnummer im Format `+49...`.

### Webhook-Format (eingehende Nachrichten)

```json
{
  "from": "+4915123456789",
  "name": "Max Mustermann",
  "message": "Hallo!",
  "timestamp": 1716123456789
}
```

## HA-Automatisierung (Beispiel)

`configuration.yaml`:
```yaml
rest_command:
  signal_send:
    url: http://localhost:17777/api/send
    method: POST
    content_type: application/json
    payload: '{"to": "{{ to }}", "message": "{{ message }}"}'
```

Automatisierung:
```yaml
action:
  - service: rest_command.signal_send
    data:
      to: "+4915123456789"
      message: "Bewegung erkannt!"
```

## Updates

Dieses Add-on wird von Home Assistant **lokal gebaut** — es gibt kein vorgefertigtes Image. Als Basis dient immer `signal-cli-rest-api:latest`, das beim Rebuild automatisch aktualisiert wird.

Falls Signal sein Protokoll ändert und das Add-on nicht mehr funktioniert:

**Einstellungen → Add-ons → Signal → Neu aufbauen**

Das reicht aus, um die aktuelle Version der Bibliothek zu laden.

## Hinweise

- Basiert auf [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api)
- Das Konto wird als verknüpftes Gerät hinzugefügt, nicht als Primärgerät registriert
- Zum Abmelden: Button "Abmelden" in der UI, danach auch in Signal unter Verknüpfte Geräte entfernen
- "Für alle löschen" erfordert eine aktuelle Version von signal-cli-rest-api; ältere Versionen löschen nur lokal

→ [Changelog](CHANGELOG.md)

---

# Signal Messenger Add-on (English)

Signal Messenger directly in Home Assistant — link your existing Signal account, send and receive messages, webhook for automations.

## Features

- **QR login**: Scan the QR code once, session persists permanently
- **Web UI**: Chat list, conversations, send/receive messages directly in the HA sidebar
- **Delete messages**: Removed locally immediately; platform-side "delete for everyone" is attempted in the background (requires a recent signal-cli-rest-api)
- **Unread badge**: Green dot in the sidebar for new messages
- **Emoji keyboard**: 😊 button in the input field
- **Persistent session**: No re-linking after restart
- **REST API**: Send messages from automations
- **Webhook**: Forward incoming messages to a URL

## Requirements

- An active Signal account on your phone
- amd64 or aarch64 hardware

## Setup

1. Install and start the add-on
2. Open "Signal" in the HA sidebar
3. Scan the QR code with the Signal app: **Settings → Linked devices → Add device**
4. Done — the session persists across restarts

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `phone_number` | — | Your Signal number (optional, detected automatically) |
| `dark_mode` | `false` | `true` = dark theme, `false` = light theme |
| `native_mode` | `true` | `true` = native mode (low CPU usage), `false` = Java mode |
| `webhook_incoming` | — | URL for incoming messages (HA webhook trigger) |
| `debug_mode` | `false` | Verbose logging including GIN access logs for troubleshooting |

## REST API

```
GET  /api/status                     → { status, phone }
GET  /api/chats                      → [ { id, name, lastMsg, lastTime } ]
GET  /api/messages/:chatId           → [ { id, body, timestamp, fromMe } ]
POST /api/send                       → { to, message }
DELETE /api/messages/:chatId/:msgId  → Delete message locally (+ attempt "for everyone")
POST /api/logout                     → Log out
```

### Send a message

```bash
curl -X POST http://<HA-IP>:17777/api/send \
  -H "Content-Type: application/json" \
  -d '{"to": "+4915123456789", "message": "Hello from HA!"}'
```

`to` is the phone number in the format `+49...`.

### Webhook payload (incoming messages)

```json
{
  "from": "+4915123456789",
  "name": "John Doe",
  "message": "Hello!",
  "timestamp": 1716123456789
}
```

## HA Automation (example)

`configuration.yaml`:
```yaml
rest_command:
  signal_send:
    url: http://localhost:17777/api/send
    method: POST
    content_type: application/json
    payload: '{"to": "{{ to }}", "message": "{{ message }}"}'
```

Automation:
```yaml
action:
  - service: rest_command.signal_send
    data:
      to: "+4915123456789"
      message: "Motion detected!"
```

## Updates

This add-on is **built locally** by Home Assistant — there is no pre-built image. The base image `signal-cli-rest-api:latest` is automatically updated on every rebuild.

If Signal changes its protocol and the add-on stops working:

**Settings → Add-ons → Signal → Rebuild**

That's all it takes to pull the current library version.

## Notes

- Based on [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api)
- The account is added as a linked device, not registered as a primary device
- To log out: use the "Log out" button in the UI, then also remove the device in Signal under Linked Devices
- "Delete for everyone" requires a recent version of signal-cli-rest-api; older versions only delete locally
