# WhatsApp

WhatsApp Web als persistente Session direkt in Home Assistant — mit Web-UI, REST-API und Webhook-Support.

## Einrichtung

1. Add-on starten
2. In der HA-Sidebar auf **WhatsApp** klicken
3. QR-Code mit der WhatsApp-App scannen (**Verknüpfte Geräte → Gerät verknüpfen**)
4. Die Session bleibt dauerhaft erhalten — auch nach Neustarts

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `dark_mode` | `true` | Dunkles Theme in der Web-UI |
| `download_media` | `false` | Empfangene Fotos automatisch herunterladen und anzeigen |
| `webhook_incoming` | — | URL für eingehende Nachrichten (z.B. HA-Webhook) |
| `initial_chats` | `30` | Anzahl Chats die beim Start geladen werden (Empfehlung: 20–50) |
| `initial_messages` | `20` | Nachrichten pro Chat beim Start (Empfehlung: 20–50) |
| `keep_deleted` | `false` | Gelöschte Nachrichten sichtbar lassen (mit 🚫-Badge) |
| `debug_mode` | `false` | Ausführliches Logging für die Fehlersuche |
| `ha_notifications` | `false` | HA-Benachrichtigung bei neuen Nachrichten |
| `ha_notifications_privacy` | `false` | Nur „WhatsApp / Neue Nachricht" — kein Absender, kein Inhalt |
| `ha_token` | — | Long-Lived Access Token für HA-Benachrichtigungen |

### HA-Benachrichtigungen einrichten

1. HA-Benutzerprofil öffnen (Benutzerbild unten links)
2. Ganz nach unten → **Langlebige Zugangstokens** → Token erstellen
3. Token unter `ha_token` in der Konfiguration eintragen

## REST-API

Das Add-on ist über Port 3000 erreichbar (`http://<HA-IP>:17776`).

```
GET  /api/status                     → Verbindungsstatus
GET  /api/chats                      → Liste aller Chats
GET  /api/messages?chat=<id>         → Nachrichten eines Chats
POST /api/send                       → Nachricht senden
POST /api/send-media                 → Bild/Dokument senden
GET  /api/export/:chatId             → Chat als HTML exportieren
DELETE /api/messages/:chatId/:msgId  → Nachricht für alle löschen
POST /api/logout                     → Abmelden
POST /api/reset                      → Session zurücksetzen (neuer QR-Code)
```

### Nachricht senden

```bash
curl -X POST http://<HA-IP>:17776/api/send \
  -H "Content-Type: application/json" \
  -d '{"to": "4915123456789", "message": "Hallo aus HA!"}'
```

`to` — Telefonnummer (nur Ziffern, ohne `+`) oder Chat-ID (`4915123456789@c.us`)

### HA-Automatisierung

`configuration.yaml`:
```yaml
rest_command:
  whatsapp_send:
    url: http://localhost:17776/api/send
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

## Webhook (eingehende Nachrichten)

**1. Add-on konfigurieren:**
```
webhook_incoming: http://homeassistant:8123/api/webhook/whatsapp
```

**2. Automatisierung in HA:**

> **Wichtig:** `local_only: false` setzen — Docker-Netzwerk-Anfragen werden sonst blockiert.

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

**Webhook-Variablen:**

| Variable | Inhalt |
|----------|--------|
| `trigger.json.from` | Absender (z.B. `4915123456789@c.us`) |
| `trigger.json.body` | Nachrichtentext |
| `trigger.json.type` | Typ (`chat`, `image`, …) |
| `trigger.json.timestamp` | Unix-Zeitstempel |

## Updates

Das Add-on wird **lokal gebaut** — bei jedem Build wird die neueste Version von whatsapp-web.js installiert.

Falls WhatsApp nach einem Update nicht mehr funktioniert:

**Einstellungen → Add-ons → WhatsApp → Neu aufbauen**

---

# WhatsApp (English)

WhatsApp Web as a persistent session directly in Home Assistant — with Web UI, REST API and webhook support.

## Setup

1. Start the add-on
2. Click **WhatsApp** in the HA sidebar
3. Scan the QR code with the WhatsApp app (**Linked Devices → Link a Device**)
4. The session persists permanently — even after restarts

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `dark_mode` | `true` | Dark theme in the Web UI |
| `download_media` | `false` | Automatically download and display received photos |
| `webhook_incoming` | — | URL for incoming messages (e.g. HA webhook) |
| `initial_chats` | `30` | Number of chats loaded on startup (recommended: 20–50) |
| `initial_messages` | `20` | Messages per chat on startup (recommended: 20–50) |
| `keep_deleted` | `false` | Keep deleted messages visible (with 🚫 badge) |
| `debug_mode` | `false` | Verbose logging for troubleshooting |
| `ha_notifications` | `false` | HA notification for new incoming messages |
| `ha_notifications_privacy` | `false` | Show only "WhatsApp / New message" — no sender, no content |
| `ha_token` | — | Long-lived access token for HA notifications |

### Setting up HA notifications

1. Open your HA user profile (user icon, bottom left)
2. Scroll to the bottom → **Long-lived access tokens** → Create token
3. Enter the token under `ha_token` in the configuration

## REST API

The add-on is available on port 3000 (`http://<HA-IP>:17776`).

```
GET  /api/status                     → Connection status
GET  /api/chats                      → List of all chats
GET  /api/messages?chat=<id>         → Messages of a chat
POST /api/send                       → Send a message
POST /api/send-media                 → Send image/document
GET  /api/export/:chatId             → Export chat as HTML
DELETE /api/messages/:chatId/:msgId  → Delete message for everyone
POST /api/logout                     → Log out
POST /api/reset                      → Reset session (new QR code)
```

### Send a message

```bash
curl -X POST http://<HA-IP>:17776/api/send \
  -H "Content-Type: application/json" \
  -d '{"to": "4915123456789", "message": "Hello from HA!"}'
```

`to` — phone number (digits only, without `+`) or chat ID (`4915123456789@c.us`)

### HA Automation

`configuration.yaml`:
```yaml
rest_command:
  whatsapp_send:
    url: http://localhost:17776/api/send
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

## Webhook (incoming messages)

**1. Configure the add-on:**
```
webhook_incoming: http://homeassistant:8123/api/webhook/whatsapp
```

**2. Automation in HA:**

> **Important:** Set `local_only: false` — requests from the Docker network are otherwise blocked.

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

**Webhook variables:**

| Variable | Content |
|----------|---------|
| `trigger.json.from` | Sender (e.g. `4915123456789@c.us`) |
| `trigger.json.body` | Message text |
| `trigger.json.type` | Type (`chat`, `image`, …) |
| `trigger.json.timestamp` | Unix timestamp |

## Updates

The add-on is **built locally** — every build installs the latest version of whatsapp-web.js.

If WhatsApp stops working after an update:

**Settings → Add-ons → WhatsApp → Rebuild**
