# WhatsApp

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Last Commit](https://img.shields.io/github/last-commit/LuckyTriple7/HA-AddOns?style=flat-square)

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
| `webhook_incoming` | — | URL für eingehende Nachrichten (HA-Webhook-Trigger) |
| `initial_chats` | `30` | Anzahl Chats die beim Start geladen werden |
| `initial_messages` | `20` | Nachrichten pro Chat die beim Start geladen werden |
| `debug_mode` | `false` | Ausführliches Logging für die Fehlersuche |
| `ha_notifications` | `false` | Persistente HA-Benachrichtigung bei neuen Nachrichten (ein pro Chat, wird überschrieben) |
| `ha_notifications_privacy` | `false` | Nur „WhatsApp / Neue Nachricht" anzeigen — kein Absender, kein Inhalt |
| `ha_token` | — | Long-Lived Access Token für HA-Benachrichtigungen (siehe unten) |

### HA-Benachrichtigungen einrichten

1. In HA das **Benutzerprofil** öffnen (Benutzerbild unten links)
2. Ganz nach unten scrollen → **Langlebige Zugangstokens** → Token erstellen
3. Den Token in der Add-on-Konfiguration unter `ha_token` eintragen

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

### Nachricht senden aus einer Automatisierung

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

### Webhook — auf eingehende Nachrichten reagieren

**1. Add-on konfigurieren:**
```
webhook_incoming: http://homeassistant:8123/api/webhook/whatsapp
```

**2. Automatisierung in HA anlegen:**

> **Wichtig:** `local_only: false` setzen — Anfragen aus dem Docker-Netzwerk werden sonst blockiert.

Benachrichtigung bei jeder eingehenden Nachricht:
```yaml
alias: WhatsApp eingehend
triggers:
  - trigger: webhook
    webhook_id: whatsapp
    allowed_methods:
      - POST
    local_only: false
actions:
  - action: notify.persistent_notification
    data:
      title: "WhatsApp"
      message: "{{ trigger.json.from }}: {{ trigger.json.body }}"
```

Auf ein Schlüsselwort reagieren (z.B. „Licht an"):
```yaml
alias: WhatsApp Licht steuern
triggers:
  - trigger: webhook
    webhook_id: whatsapp
    local_only: false
conditions:
  - condition: template
    value_template: "{{ 'licht an' in (trigger.json.body | lower) }}"
actions:
  - action: light.turn_on
    target:
      entity_id: light.wohnzimmer
```

**Verfügbare Variablen im Webhook:**

| Variable | Inhalt |
|----------|--------|
| `trigger.json.from` | Absender (z.B. `4915123456789@c.us`) |
| `trigger.json.body` | Nachrichtentext |
| `trigger.json.type` | Typ (`chat`, `image`, …) |
| `trigger.json.timestamp` | Unix-Zeitstempel (Sekunden) |

## Updates

Dieses Add-on wird von Home Assistant **lokal gebaut** — es gibt kein vorgefertigtes Image. Bei jedem Build wird automatisch die neueste kompatible Version von whatsapp-web.js installiert.

Falls WhatsApp sein Protokoll ändert und das Add-on nicht mehr funktioniert:

**Einstellungen → Add-ons → WhatsApp → Neu aufbauen**

Das reicht aus, um die aktuelle Bibliotheksversion zu laden.

## Hinweise

- Erfordert ein WhatsApp-Konto auf einem Smartphone
- Basiert auf [whatsapp-web.js](https://github.com/pedroslopez/whatsapp-web.js) (inoffiziell, für den persönlichen Gebrauch)
- Session überlebt Add-on-Updates und Neustarts
- Medien werden in `/data/media/` gespeichert

→ [Changelog](CHANGELOG.md)

---

# WhatsApp (English)

WhatsApp Web as a persistent session directly in Home Assistant — with Web UI, REST API and webhook support.

## Features

- **QR Login**: Scan the QR code once, session persists permanently
- **Web UI**: Chat list, conversations, send/receive messages directly in the HA sidebar
- **Photos**: Display received images (optional, see `download_media`)
- **Delete messages**: Remove a message for everyone (hover → ✕)
- **Unread badge**: Green dot in the sidebar for new messages
- **Emoji keyboard**: 😊 button in the input field
- **REST API**: Send messages from automations
- **Webhook**: Forward incoming messages to a URL

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `dark_mode` | `true` | `true` = dark theme, `false` = light theme |
| `download_media` | `false` | Automatically download and display received photos (only works reliably for newly incoming messages, not for historical ones) |
| `webhook_incoming` | — | URL for incoming messages (HA webhook trigger) |
| `initial_chats` | `30` | Number of chats loaded on startup |
| `initial_messages` | `20` | Messages per chat loaded on startup |
| `debug_mode` | `false` | Verbose logging for troubleshooting |
| `ha_notifications` | `false` | Persistent HA notification for new incoming messages (one per chat, overwritten by newer messages) |
| `ha_notifications_privacy` | `false` | Show only "WhatsApp / New message" — no sender name, no content |
| `ha_token` | — | Long-lived access token for HA notifications (see below) |

### Setting up HA notifications

1. Open your **user profile** in HA (user icon, bottom left)
2. Scroll to the bottom → **Long-lived access tokens** → Create token
3. Enter the token in the add-on configuration under `ha_token`

## REST API

```
GET  /api/status                     → { status, phone }
GET  /api/chats                      → [ { id, name, lastMsg, lastTime } ]
GET  /api/messages?chat=<id>         → [ { id, body, type, timestamp, fromMe } ]
POST /api/send                       → { to, message }
DELETE /api/messages/:chatId/:msgId  → Delete message for everyone
POST /api/logout                     → Log out
POST /api/reset                      → Reset session (new QR code)
```

### Send a message

```bash
curl -X POST http://<HA-IP>:3000/api/send \
  -H "Content-Type: application/json" \
  -d '{"to": "4915123456789", "message": "Hello from HA!"}'
```

`to` can be a phone number (digits only, without `+`) or a full chat ID (`4915123456789@c.us`).

### Webhook payload (incoming messages)

```json
{
  "from": "4915123456789@c.us",
  "body": "Message text",
  "type": "chat",
  "timestamp": 1716123456
}
```

## HA Automation (example)

### Send a message from an automation

`configuration.yaml`:
```yaml
rest_command:
  whatsapp_send:
    url: http://localhost:3000/api/send
    method: POST
    content_type: application/json
    payload: '{"to": "{{ to }}", "message": "{{ message }}"}'
```

Automation:
```yaml
action:
  - service: rest_command.whatsapp_send
    data:
      to: "4915123456789"
      message: "Motion detected!"
```

### Webhook — react to incoming messages

**1. Configure the add-on:**
```
webhook_incoming: http://homeassistant:8123/api/webhook/whatsapp
```

**2. Create an automation in HA:**

> **Important:** Set `local_only: false` — requests from the Docker network are otherwise blocked.

Notification on every incoming message:
```yaml
alias: WhatsApp incoming
triggers:
  - trigger: webhook
    webhook_id: whatsapp
    allowed_methods:
      - POST
    local_only: false
actions:
  - action: notify.persistent_notification
    data:
      title: "WhatsApp"
      message: "{{ trigger.json.from }}: {{ trigger.json.body }}"
```

React to a keyword (e.g. "lights on"):
```yaml
alias: WhatsApp control lights
triggers:
  - trigger: webhook
    webhook_id: whatsapp
    local_only: false
conditions:
  - condition: template
    value_template: "{{ 'lights on' in (trigger.json.body | lower) }}"
actions:
  - action: light.turn_on
    target:
      entity_id: light.living_room
```

**Available variables in the webhook:**

| Variable | Content |
|----------|---------|
| `trigger.json.from` | Sender (e.g. `4915123456789@c.us`) |
| `trigger.json.body` | Message text |
| `trigger.json.type` | Type (`chat`, `image`, …) |
| `trigger.json.timestamp` | Unix timestamp (seconds) |

## Updates

This add-on is **built locally** by Home Assistant — there is no pre-built image. Every build automatically installs the latest compatible version of whatsapp-web.js.

If WhatsApp changes its protocol and the add-on stops working:

**Settings → Add-ons → WhatsApp → Rebuild**

That's all it takes to pull the current library version.

## Notes

- Requires a WhatsApp account on a smartphone
- Based on [whatsapp-web.js](https://github.com/pedroslopez/whatsapp-web.js) (unofficial, for personal use)
- Session survives add-on updates and restarts
- Media files are stored in `/data/media/`
