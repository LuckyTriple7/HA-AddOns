# Signal Messenger

Signal Messenger direkt in Home Assistant — bestehendes Konto verknüpfen, Nachrichten senden und empfangen, Webhook für Automatisierungen.

## Einrichtung

1. Add-on installieren und starten
2. In der HA-Sidebar **Signal** öffnen
3. QR-Code mit der Signal-App scannen: **Einstellungen → Verknüpfte Geräte → Gerät hinzufügen**
4. Die Session bleibt über Neustarts erhalten

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `phone_number` | — | Deine Signal-Nummer (optional, wird automatisch erkannt) |
| `dark_mode` | `false` | `true` = dunkles Theme, `false` = helles Theme |
| `native_mode` | `true` | `true` = nativer Modus (niedrige CPU-Last), `false` = Java-Modus |
| `webhook_incoming` | — | URL für eingehende Nachrichten (HA-Webhook-Trigger) |
| `debug_mode` | `false` | Ausführliches Logging für die Fehlersuche |
| `ha_notifications` | `false` | Persistente HA-Benachrichtigung bei neuen Nachrichten |
| `ha_notifications_privacy` | `false` | Nur „Signal / Neue Nachricht" — kein Absender, kein Inhalt |

### HA-Benachrichtigungen einrichten

Einfach `ha_notifications` aktivieren — sonst nichts. Das Add-on nutzt automatisch den vom Supervisor bereitgestellten Zugriff auf die Home-Assistant-API (`homeassistant_api`); ein manuell erstellter Access Token ist nicht mehr nötig.

## REST-API

Das Add-on ist über Port 17777 erreichbar (`http://<HA-IP>:17777`).

```
GET  /api/status                  → Verbindungsstatus
GET  /api/chats                   → Liste aller Chats
GET  /api/messages/:id            → Nachrichten eines Chats
GET  /api/last-received           → Zeitpunkt der letzten empfangenen Nachricht
GET  /api/last-received?chat=<id> → Letzte empfangene Nachricht eines bestimmten Chats
POST /api/send                    → Nachricht senden
POST /api/send-media              → Bild/Dokument senden
GET  /api/export/:id              → Chat als HTML exportieren
POST /api/logout                  → Abmelden
```

### HA-Sensor: Letzte empfangene Nachricht

`GET /api/last-received` gibt zurück, wann zuletzt eine Nachricht empfangen wurde:

```json
{
  "timestamp": 1748500000000,
  "iso": "2026-05-29T10:30:00.000Z",
  "chatId": "+4915123456789",
  "chatName": "Max Mustermann",
  "contact": "Max Mustermann",
  "preview": "Hallo!"
}
```

**`configuration.yaml`:**
```yaml
sensor:
  - platform: rest
    name: Signal letzte Nachricht
    resource: http://localhost:17777/api/last-received
    value_template: "{{ value_json.iso }}"
    json_attributes:
      - chatName
      - contact
      - preview
    scan_interval: 30
```

### Nachricht senden

```bash
curl -X POST http://<HA-IP>:17777/api/send \
  -H "Content-Type: application/json" \
  -d '{"to": "+4915123456789", "message": "Hallo aus HA!"}'
```

## Webhook (eingehende Nachrichten)

**Add-on konfigurieren:**
```
webhook_incoming: http://homeassistant:8123/api/webhook/signal
```

**Automatisierung in HA** (`local_only: false` ist wichtig):
```yaml
alias: Signal eingehend
triggers:
  - trigger: webhook
    webhook_id: signal
    allowed_methods: [POST]
    local_only: false
actions:
  - action: notify.persistent_notification
    data:
      title: "Signal von {{ trigger.json.name }}"
      message: "{{ trigger.json.message }}"
```

**Webhook-Variablen:**

| Variable | Inhalt |
|----------|--------|
| `trigger.json.from` | Absender (Telefonnummer) |
| `trigger.json.name` | Name des Absenders |
| `trigger.json.message` | Nachrichtentext |
| `trigger.json.timestamp` | Unix-Zeitstempel (ms) |

## HA-Automatisierung

`configuration.yaml`:
```yaml
rest_command:
  signal_send:
    url: http://localhost:17777/api/send
    method: POST
    content_type: application/json
    payload: '{"to": "{{ to }}", "message": "{{ message }}"}'
```

## Updates

Falls Signal nach einem Update nicht mehr funktioniert:
**Einstellungen → Add-ons → Signal → Neu aufbauen**

---

# Signal Messenger (English)

Signal Messenger directly in Home Assistant — link your existing account, send and receive messages, webhook for automations.

## Setup

1. Install and start the add-on
2. Open **Signal** in the HA sidebar
3. Scan the QR code with the Signal app: **Settings → Linked Devices → Add Device**
4. The session persists across restarts

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `phone_number` | — | Your Signal number (optional, detected automatically) |
| `dark_mode` | `false` | `true` = dark theme, `false` = light theme |
| `native_mode` | `true` | `true` = native mode (low CPU), `false` = Java mode |
| `webhook_incoming` | — | URL for incoming messages (HA webhook trigger) |
| `debug_mode` | `false` | Verbose logging for troubleshooting |
| `ha_notifications` | `false` | Persistent HA notification for new incoming messages |
| `ha_notifications_privacy` | `false` | Show only "Signal / New message" — no sender, no content |

### Setting up HA Notifications

Just enable `ha_notifications` — nothing else. The add-on automatically uses the Home Assistant API access provided by the Supervisor (`homeassistant_api`); a manually created access token is no longer required.

## REST API

The add-on is available on port 17777 (`http://<HA-IP>:17777`).

```
GET  /api/status                  → Connection status
GET  /api/chats                   → List of all chats
GET  /api/messages/:id            → Messages of a chat
GET  /api/last-received           → Timestamp of the last received message
GET  /api/last-received?chat=<id> → Last received message of a specific chat
POST /api/send                    → Send a message
POST /api/send-media              → Send image/document
GET  /api/export/:id              → Export chat as HTML
POST /api/logout                  → Log out
```

### HA Sensor: Last received message

`GET /api/last-received` returns when the last message was received:

```json
{
  "timestamp": 1748500000000,
  "iso": "2026-05-29T10:30:00.000Z",
  "chatId": "+4915123456789",
  "chatName": "Max Mustermann",
  "contact": "Max Mustermann",
  "preview": "Hello!"
}
```

**`configuration.yaml`:**
```yaml
sensor:
  - platform: rest
    name: Signal Last Message
    resource: http://localhost:17777/api/last-received
    value_template: "{{ value_json.iso }}"
    json_attributes:
      - chatName
      - contact
      - preview
    scan_interval: 30
```

### Send a Message

```bash
curl -X POST http://<HA-IP>:17777/api/send \
  -H "Content-Type: application/json" \
  -d '{"to": "+4915123456789", "message": "Hello from HA!"}'
```

## Webhook (Incoming Messages)

**Configure the add-on:**
```
webhook_incoming: http://homeassistant:8123/api/webhook/signal
```

**Automation in HA** (`local_only: false` is required):
```yaml
alias: Signal incoming
triggers:
  - trigger: webhook
    webhook_id: signal
    allowed_methods: [POST]
    local_only: false
actions:
  - action: notify.persistent_notification
    data:
      title: "Signal from {{ trigger.json.name }}"
      message: "{{ trigger.json.message }}"
```

**Webhook variables:**

| Variable | Content |
|----------|---------|
| `trigger.json.from` | Sender (phone number) |
| `trigger.json.name` | Sender name |
| `trigger.json.message` | Message text |
| `trigger.json.timestamp` | Unix timestamp (ms) |

## Updates

If Signal stops working after an update:
**Settings → Add-ons → Signal → Rebuild**
