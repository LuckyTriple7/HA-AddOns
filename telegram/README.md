# Telegram

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Commits](https://img.shields.io/github/commit-activity/t/LuckyTriple7/HA-AddOns?style=flat-square&label=commits)

Telegram als vollwertiger Client direkt in Home Assistant — mit Chat-UI, REST-API und Webhook-Support.

## Funktionen

- **MTProto-Login**: Telefonnummer + SMS/App-Code, 2FA unterstützt
- **Web-UI**: Chat-Liste, Konversationen, Nachrichten senden/empfangen direkt in der HA-Sidebar
- **Fotos**: Empfangene Bilder anzeigen (optional, siehe `download_media`)
- **Nachrichten löschen**: Nachricht für alle entfernen (Hover → ✕)
- **Lesebestätigungen**: ✓ gesendet (grau), ✓✓ gelesen (blau) bei eigenen Nachrichten
- **Ungelesene-Badge**: Blauer Punkt in der Sidebar bei neuen Nachrichten
- **Emoji-Tastatur**: 😊-Button in der Eingabe
- **Persistente Session**: Kein erneutes Anmelden nach Neustart
- **REST-API**: Nachrichten aus Automatisierungen heraus senden
- **Webhook**: Eingehende Nachrichten an eine URL weiterleiten

## Einrichtung

### 1. API-Credentials besorgen

1. Auf [my.telegram.org](https://my.telegram.org) einloggen
2. → **API development tools**
3. App erstellen (Name und Plattform beliebig)
4. **App api_id** und **App api_hash** notieren

### 2. Add-on konfigurieren und starten

Nach dem Start erscheint ein Code-Eingabefeld in der Web-UI. Telegram sendet einen Code per App-Benachrichtigung oder SMS — diesen Code eingeben, fertig.

Bei aktivierter 2-Faktor-Authentifizierung wird danach das Cloud-Passwort abgefragt.

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `api_id` | — | Numerische API-ID von my.telegram.org |
| `api_hash` | — | API-Hash von my.telegram.org |
| `phone_number` | — | Telefonnummer mit Ländervorwahl, z.B. `+4917612345678` |
| `dark_mode` | `true` | `true` = dunkles Theme, `false` = helles Theme |
| `download_media` | `false` | Empfangene Fotos automatisch herunterladen und anzeigen (funktioniert nur zuverlässig bei neu eingehenden Nachrichten, nicht für historische Nachrichten) |
| `fetch_messages_limit` | `50` | Nachrichten die beim ersten Öffnen eines Chats geladen werden (max. 300) |
| `webhook_incoming` | — | URL für eingehende Nachrichten (HA-Webhook-Trigger) |
| `debug_mode` | `false` | Ausführliches Logging für die Fehlersuche |
| `ha_notifications` | `false` | Persistente HA-Benachrichtigung bei neuen Nachrichten (ein pro Chat, wird überschrieben) |
| `ha_notifications_privacy` | `false` | Nur „Telegram / Neue Nachricht" anzeigen — kein Absender, kein Inhalt |
| `ha_notifications_skip_bots` | `false` | Keine HA-Benachrichtigung für Nachrichten von Bots |
| `ha_token` | — | Long-Lived Access Token für HA-Benachrichtigungen (siehe unten) |

### HA-Benachrichtigungen einrichten

1. In HA das **Benutzerprofil** öffnen (Benutzerbild unten links)
2. Ganz nach unten scrollen → **Langlebige Zugangstokens** → Token erstellen
3. Den Token in der Add-on-Konfiguration unter `ha_token` eintragen

## REST-API

```
GET  /api/status                     → { status, name, id }
GET  /api/chats                      → [ { id, name, lastMsg, lastTime } ]
GET  /api/messages/:chatId           → [ { id, body, type, timestamp, fromMe } ]
POST /api/send                       → { to, message }
DELETE /api/messages/:chatId/:msgId  → Nachricht für alle löschen
POST /api/submit-code                → { code } — Login-Code einreichen
POST /api/submit-password            → { password } — 2FA-Passwort einreichen
POST /api/logout                     → Abmelden und Session löschen
```

### Nachricht senden

```bash
curl -X POST http://<HA-IP>:17778/api/send \
  -H "Content-Type: application/json" \
  -d '{"to": "123456789", "message": "Hallo aus HA!"}'
```

`to` ist die numerische Chat-ID (aus `/api/chats` → Feld `id`).

### Webhook-Format (eingehende Nachrichten)

```json
{
  "from": "123456789",
  "name": "Max Mustermann",
  "message": "Nachrichtentext",
  "timestamp": 1716123456000
}
```

## HA-Automatisierung (Beispiel)

### Nachricht senden aus einer Automatisierung

`configuration.yaml`:
```yaml
rest_command:
  telegram_send:
    url: http://localhost:17778/api/send
    method: POST
    content_type: application/json
    payload: '{"to": "{{ to }}", "message": "{{ message }}"}'
```

Automatisierung:
```yaml
action:
  - service: rest_command.telegram_send
    data:
      to: "123456789"
      message: "Bewegung erkannt!"
```

### Webhook — auf eingehende Nachrichten reagieren

**1. Add-on konfigurieren:**
```
webhook_incoming: http://homeassistant:8123/api/webhook/telegram
```

**2. Automatisierung in HA anlegen:**

> **Wichtig:** `local_only: false` setzen — Anfragen aus dem Docker-Netzwerk werden sonst blockiert.

Benachrichtigung bei jeder eingehenden Nachricht:
```yaml
alias: Telegram eingehend
triggers:
  - trigger: webhook
    webhook_id: telegram
    allowed_methods:
      - POST
    local_only: false
actions:
  - action: notify.persistent_notification
    data:
      title: "Telegram von {{ trigger.json.name }}"
      message: "{{ trigger.json.message }}"
```

Auf ein Schlüsselwort reagieren (z.B. „Licht an"):
```yaml
alias: Telegram Licht steuern
triggers:
  - trigger: webhook
    webhook_id: telegram
    local_only: false
conditions:
  - condition: template
    value_template: "{{ 'licht an' in (trigger.json.message | lower) }}"
actions:
  - action: light.turn_on
    target:
      entity_id: light.wohnzimmer
```

**Verfügbare Variablen im Webhook:**

| Variable | Inhalt |
|----------|--------|
| `trigger.json.from` | Absender (Chat-ID, z.B. `123456789`) |
| `trigger.json.name` | Name des Absenders |
| `trigger.json.message` | Nachrichtentext |
| `trigger.json.timestamp` | Unix-Zeitstempel (Millisekunden) |

## Updates

Dieses Add-on wird von Home Assistant **lokal gebaut** — es gibt kein vorgefertigtes Image. Bei jedem Build wird automatisch die neueste kompatible Version von GramJS installiert.

Falls Telegram sein Protokoll ändert und das Add-on nicht mehr funktioniert:

**Einstellungen → Add-ons → Telegram → Neu aufbauen**

Das reicht aus, um die aktuelle Bibliotheksversion zu laden.

## Hinweise

- Basiert auf [GramJS](https://github.com/gram-js/gramjs) (offizielle MTProto-Implementierung für JavaScript)
- Session wird in `/data/session.txt` gespeichert und überlebt Neustarts
- Chats und Nachrichten werden in `/data/chats.json` und `/data/messages.json` gespeichert
- Medien werden in `/data/media/` gespeichert

→ [Changelog](CHANGELOG.md)

---

# Telegram (English)

Telegram as a full client directly in Home Assistant — with chat UI, REST API and webhook support.

## Features

- **MTProto login**: Phone number + SMS/app code, 2FA supported
- **Web UI**: Chat list, conversations, send/receive messages directly in the HA sidebar
- **Photos**: Display received images (optional, see `download_media`)
- **Delete messages**: Remove a message for everyone (hover → ✕)
- **Read receipts**: ✓ sent (grey), ✓✓ read (blue) on outgoing messages
- **Unread badge**: Blue dot in the sidebar for new messages
- **Emoji keyboard**: 😊 button in the input field
- **Persistent session**: No re-login after restart
- **REST API**: Send messages from automations
- **Webhook**: Forward incoming messages to a URL

## Setup

### 1. Get API credentials

1. Log in at [my.telegram.org](https://my.telegram.org)
2. → **API development tools**
3. Create an app (name and platform are arbitrary)
4. Note the **App api_id** and **App api_hash**

### 2. Configure and start the add-on

After starting, a code input field appears in the Web UI. Telegram sends a code via app notification or SMS — enter this code and you're done.

If two-factor authentication is enabled, the cloud password will be requested afterwards.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `api_id` | — | Numeric API ID from my.telegram.org |
| `api_hash` | — | API hash from my.telegram.org |
| `phone_number` | — | Phone number with country code, e.g. `+4917612345678` |
| `dark_mode` | `true` | `true` = dark theme, `false` = light theme |
| `download_media` | `false` | Automatically download and display received photos (only works reliably for newly incoming messages, not for historical ones) |
| `fetch_messages_limit` | `50` | Messages loaded when a chat is first opened (max. 300) |
| `webhook_incoming` | — | URL for incoming messages (HA webhook trigger) |
| `debug_mode` | `false` | Verbose logging for troubleshooting |
| `ha_notifications` | `false` | Persistent HA notification for new incoming messages (one per chat, overwritten by newer messages) |
| `ha_notifications_privacy` | `false` | Show only "Telegram / New message" — no sender name, no content |
| `ha_notifications_skip_bots` | `false` | Skip HA notifications for messages from bots |
| `ha_token` | — | Long-lived access token for HA notifications (see below) |

### Setting up HA notifications

1. Open your **user profile** in HA (user icon, bottom left)
2. Scroll to the bottom → **Long-lived access tokens** → Create token
3. Enter the token in the add-on configuration under `ha_token`

## REST API

```
GET  /api/status                     → { status, name, id }
GET  /api/chats                      → [ { id, name, lastMsg, lastTime } ]
GET  /api/messages/:chatId           → [ { id, body, type, timestamp, fromMe } ]
POST /api/send                       → { to, message }
DELETE /api/messages/:chatId/:msgId  → Delete message for everyone
POST /api/submit-code                → { code } — Submit login code
POST /api/submit-password            → { password } — Submit 2FA password
POST /api/logout                     → Log out and delete session
```

### Send a message

```bash
curl -X POST http://<HA-IP>:17778/api/send \
  -H "Content-Type: application/json" \
  -d '{"to": "123456789", "message": "Hello from HA!"}'
```

`to` is the numeric chat ID (from `/api/chats` → field `id`).

### Webhook payload (incoming messages)

```json
{
  "from": "123456789",
  "name": "John Doe",
  "message": "Message text",
  "timestamp": 1716123456000
}
```

## HA Automation (example)

### Send a message from an automation

`configuration.yaml`:
```yaml
rest_command:
  telegram_send:
    url: http://localhost:17778/api/send
    method: POST
    content_type: application/json
    payload: '{"to": "{{ to }}", "message": "{{ message }}"}'
```

Automation:
```yaml
action:
  - service: rest_command.telegram_send
    data:
      to: "123456789"
      message: "Motion detected!"
```

### Webhook — react to incoming messages

**1. Configure the add-on:**
```
webhook_incoming: http://homeassistant:8123/api/webhook/telegram
```

**2. Create an automation in HA:**

> **Important:** Set `local_only: false` — requests from the Docker network are otherwise blocked.

Notification on every incoming message:
```yaml
alias: Telegram incoming
triggers:
  - trigger: webhook
    webhook_id: telegram
    allowed_methods:
      - POST
    local_only: false
actions:
  - action: notify.persistent_notification
    data:
      title: "Telegram from {{ trigger.json.name }}"
      message: "{{ trigger.json.message }}"
```

React to a keyword (e.g. "lights on"):
```yaml
alias: Telegram control lights
triggers:
  - trigger: webhook
    webhook_id: telegram
    local_only: false
conditions:
  - condition: template
    value_template: "{{ 'lights on' in (trigger.json.message | lower) }}"
actions:
  - action: light.turn_on
    target:
      entity_id: light.living_room
```

**Available variables in the webhook:**

| Variable | Content |
|----------|---------|
| `trigger.json.from` | Sender (chat ID, e.g. `123456789`) |
| `trigger.json.name` | Sender name |
| `trigger.json.message` | Message text |
| `trigger.json.timestamp` | Unix timestamp (milliseconds) |

## Updates

This add-on is **built locally** by Home Assistant — there is no pre-built image. Every build automatically installs the latest compatible version of GramJS.

If Telegram changes its protocol and the add-on stops working:

**Settings → Add-ons → Telegram → Rebuild**

That's all it takes to pull the current library version.

## Notes

- Based on [GramJS](https://github.com/gram-js/gramjs) (official MTProto implementation for JavaScript)
- Session is stored in `/data/session.txt` and survives restarts
- Chats and messages are stored in `/data/chats.json` and `/data/messages.json`
- Media files are stored in `/data/media/`
