# Telegram

Telegram als vollwertiger Client direkt in Home Assistant — mit Chat-UI, REST-API und Webhook-Support.

## Einrichtung

### 1. API-Credentials besorgen

1. Auf [my.telegram.org](https://my.telegram.org) einloggen
2. → **API development tools** → App erstellen
3. **App api_id** und **App api_hash** notieren

### 2. Add-on konfigurieren und starten

Nach dem Start erscheint ein Code-Eingabefeld in der Web-UI. Den Code aus der Telegram-App oder SMS eingeben. Bei aktivierter 2FA wird danach das Cloud-Passwort abgefragt.

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `api_id` | — | Numerische API-ID von my.telegram.org |
| `api_hash` | — | API-Hash von my.telegram.org |
| `phone_number` | — | Telefonnummer mit Ländervorwahl (z.B. `+4917612345678`) |
| `dark_mode` | `true` | `true` = dunkles Theme, `false` = helles Theme |
| `download_media` | `false` | Empfangene Fotos automatisch herunterladen und anzeigen |
| `fetch_messages_limit` | `50` | Nachrichten beim ersten Öffnen eines Chats (max. 300) |
| `webhook_incoming` | — | URL für eingehende Nachrichten (HA-Webhook-Trigger) |
| `debug_mode` | `false` | Ausführliches Logging für die Fehlersuche |
| `ha_notifications` | `false` | Persistente HA-Benachrichtigung bei neuen Nachrichten |
| `ha_notifications_privacy` | `false` | Nur „Telegram / Neue Nachricht" — kein Absender, kein Inhalt |
| `ha_notifications_skip_bots` | `false` | Keine HA-Benachrichtigung für Bot-Nachrichten |

### HA-Benachrichtigungen einrichten

Einfach `ha_notifications` aktivieren — sonst nichts. Das Add-on nutzt automatisch den vom Supervisor bereitgestellten Zugriff auf die Home-Assistant-API (`homeassistant_api`); ein manuell erstellter Access Token ist nicht mehr nötig.

## REST-API

### Zwei Ports, zwei Sicherheitsstufen

| Port | Was liegt dort | Schutz | Standard |
|------|----------------|--------|----------|
| 17778 | Weboberfläche **und** REST-API | keiner — wer den Port erreicht, kann mitlesen und senden | **zu** |
| 17788 | nur REST-API (`/api/*`), keine Oberfläche | Token-Pflicht | zu |

Port 17778 kennt bewusst keine Anmeldung: die Weboberfläche ruft ihre eigenen
`/api/`-Routen aus dem Browser auf, eine Token-Pflicht würde sie lahmlegen. Sein
Schutz ist deshalb, dass er **nicht freigegeben** ist. Der Zugang zur Oberfläche
läuft über HA-Ingress (Anmeldung durch Home Assistant) oder das
MessengerPortal — beides geht nicht über den Host-Port.

Gibst du 17778 unter *Netzwerk* frei, steht alles offen, was hier beschrieben
ist: mitlesen und senden, ohne Passwort, für jedes Gerät im Netz.

Port 17788 ist der Weg für Skripte und fremde Geräte. Er braucht zwei Schalter:

1. Option **REST-API auf eigenem Port** (`api_enabled`) einschalten und einen
   **API-Token** (`api_token`) setzen — ohne Token startet der Port nicht
2. Port 17788 unter *Netzwerk* freigeben, wenn er aus dem LAN erreichbar sein soll

Jeder Aufruf braucht dann die Kopfzeile `Authorization: Bearer <Token>`; ohne sie
antwortet der Port mit `401`. Die Weboberfläche gibt es dort auch mit gültigem
Token nicht — sie wäre sonst ein zweiter, gleichwertiger Weg auf alles.

Token erzeugen:

```bash
openssl rand -hex 32
```


```
GET  /api/status                  → Verbindungsstatus
GET  /api/chats                   → Liste aller Chats
GET  /api/messages/:id            → Nachrichten eines Chats
GET  /api/last-received           → Zeitpunkt der letzten empfangenen Nachricht
GET  /api/last-received?chat=<id> → Letzte empfangene Nachricht eines bestimmten Chats
POST /api/send                    → Nachricht senden  { to, message }
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
  "chatId": "123456789",
  "chatName": "Max Mustermann",
  "contact": "Max Mustermann",
  "preview": "Hallo!"
}
```

**`configuration.yaml`:**
```yaml
sensor:
  - platform: rest
    name: Telegram letzte Nachricht
    resource: http://localhost:17788/api/last-received
    headers:
      Authorization: !secret telegram_api_token
    value_template: "{{ value_json.iso }}"
    json_attributes:
      - chatName
      - contact
      - preview
    scan_interval: 30
```

`secrets.yaml`:
```yaml
telegram_api_token: "Bearer <Token>"
```

### Nachricht senden

```bash
curl -X POST http://<HA-IP>:17788/api/send \
  -H "Authorization: Bearer <Token>" \
  -H "Content-Type: application/json" \
  -d '{"to": "123456789", "message": "Hallo aus HA!"}'
```

`to` ist die numerische Chat-ID (aus `/api/chats` → Feld `id`).

## Webhook (eingehende Nachrichten)

**Add-on konfigurieren:**
```
webhook_incoming: http://homeassistant:8123/api/webhook/telegram
```

**Automatisierung in HA** (`local_only: false` ist wichtig):
```yaml
alias: Telegram eingehend
triggers:
  - trigger: webhook
    webhook_id: telegram
    allowed_methods: [POST]
    local_only: false
actions:
  - action: notify.persistent_notification
    data:
      title: "Telegram von {{ trigger.json.name }}"
      message: "{{ trigger.json.message }}"
```

**Webhook-Variablen:**

| Variable | Inhalt |
|----------|--------|
| `trigger.json.from` | Absender (Chat-ID) |
| `trigger.json.name` | Name des Absenders |
| `trigger.json.message` | Nachrichtentext |
| `trigger.json.timestamp` | Unix-Zeitstempel (ms) |

## HA-Automatisierung

`configuration.yaml`:
```yaml
rest_command:
  telegram_send:
    url: http://localhost:17788/api/send
    headers:
      Authorization: !secret telegram_api_token
    method: POST
    content_type: application/json
    payload: '{"to": "{{ to }}", "message": "{{ message }}"}'
```

`secrets.yaml`:
```yaml
telegram_api_token: "Bearer <Token>"
```

## Updates

Falls Telegram nach einem Update nicht mehr funktioniert:
**Einstellungen → Add-ons → Telegram → Neu aufbauen**

---

# Telegram (English)

Telegram as a full client directly in Home Assistant — with chat UI, REST API and webhook support.

## Setup

### 1. Get API Credentials

1. Log in at [my.telegram.org](https://my.telegram.org)
2. → **API development tools** → Create an app
3. Note the **App api_id** and **App api_hash**

### 2. Configure and Start the Add-on

After starting, a code input field appears in the Web UI. Enter the code from the Telegram app or SMS. If 2FA is enabled, the cloud password will be requested afterwards.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `api_id` | — | Numeric API ID from my.telegram.org |
| `api_hash` | — | API hash from my.telegram.org |
| `phone_number` | — | Phone number with country code (e.g. `+4917612345678`) |
| `dark_mode` | `true` | `true` = dark theme, `false` = light theme |
| `download_media` | `false` | Automatically download and display received photos |
| `fetch_messages_limit` | `50` | Messages loaded when first opening a chat (max. 300) |
| `webhook_incoming` | — | URL for incoming messages (HA webhook trigger) |
| `debug_mode` | `false` | Verbose logging for troubleshooting |
| `ha_notifications` | `false` | Persistent HA notification for new incoming messages |
| `ha_notifications_privacy` | `false` | Show only "Telegram / New message" — no sender, no content |
| `ha_notifications_skip_bots` | `false` | Skip HA notifications for bot messages |

### Setting up HA Notifications

Just enable `ha_notifications` — nothing else. The add-on automatically uses the Home Assistant API access provided by the Supervisor (`homeassistant_api`); a manually created access token is no longer required.

## REST API

### Two ports, two security levels

| Port | What it serves | Protection | Default |
|------|----------------|------------|---------|
| 17778 | web interface **and** REST API | none — anyone who reaches it can read and send | **closed** |
| 17788 | REST API only (`/api/*`), no interface | token required | closed |

Port 17778 deliberately has no login: the web interface calls its own `/api/`
routes from the browser, so requiring a token would break it. Its protection is
therefore that it is **not published**. The interface is reached through HA
Ingress (authenticated by Home Assistant) or the MessengerPortal — neither
goes through the host port.

Publish 17778 under *Network* and everything described here is wide open:
reading and sending, without a password, for any device on the network.

Port 17788 is the path for scripts and other machines. It needs two switches:

1. Turn on **REST API on a separate port** (`api_enabled`) and set an
   **API token** (`api_token`) — without a token the port does not start
2. Publish port 17788 under *Network* if it should be reachable from the LAN

Every call then needs the header `Authorization: Bearer <token>`; without it the
port answers `401`. The web interface is not served there even with a valid
token — it would just be a second, equally powerful way in.

Generate a token:

```bash
openssl rand -hex 32
```


```
GET  /api/status                  → Connection status
GET  /api/chats                   → List of all chats
GET  /api/messages/:id            → Messages of a chat
GET  /api/last-received           → Timestamp of the last received message
GET  /api/last-received?chat=<id> → Last received message of a specific chat
POST /api/send                    → Send a message  { to, message }
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
  "chatId": "123456789",
  "chatName": "Max Mustermann",
  "contact": "Max Mustermann",
  "preview": "Hello!"
}
```

**`configuration.yaml`:**
```yaml
sensor:
  - platform: rest
    name: Telegram Last Message
    resource: http://localhost:17788/api/last-received
    headers:
      Authorization: !secret telegram_api_token
    value_template: "{{ value_json.iso }}"
    json_attributes:
      - chatName
      - contact
      - preview
    scan_interval: 30
```

`secrets.yaml`:
```yaml
telegram_api_token: "Bearer <token>"
```

### Send a Message

```bash
curl -X POST http://<HA-IP>:17788/api/send \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"to": "123456789", "message": "Hello from HA!"}'
```

`to` is the numeric chat ID (from `/api/chats` → field `id`).

## Webhook (Incoming Messages)

**Configure the add-on:**
```
webhook_incoming: http://homeassistant:8123/api/webhook/telegram
```

**Automation in HA** (`local_only: false` is required):
```yaml
alias: Telegram incoming
triggers:
  - trigger: webhook
    webhook_id: telegram
    allowed_methods: [POST]
    local_only: false
actions:
  - action: notify.persistent_notification
    data:
      title: "Telegram from {{ trigger.json.name }}"
      message: "{{ trigger.json.message }}"
```

## Updates

If Telegram stops working after an update:
**Settings → Add-ons → Telegram → Rebuild**
