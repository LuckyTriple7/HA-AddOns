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
| `download_media` | `false` | Empfangene Fotos automatisch herunterladen und anzeigen (pro Chat abschaltbar, siehe unten) |
| `webhook_incoming` | — | URL für eingehende Nachrichten (z.B. HA-Webhook) |
| `initial_chats` | `30` | Anzahl Chats die beim Start geladen werden (Empfehlung: 20–50) |
| `initial_messages` | `20` | Nachrichten pro Chat beim Start (Empfehlung: 20–50) |
| `keep_deleted` | `false` | Gelöschte Nachrichten sichtbar lassen (mit 🚫-Badge) |
| `debug_mode` | `false` | Ausführliches Logging für die Fehlersuche |
| `ha_notifications` | `false` | HA-Benachrichtigung bei neuen Nachrichten |
| `ha_notifications_privacy` | `false` | Nur „WhatsApp / Neue Nachricht" — kein Absender, kein Inhalt |

### HA-Benachrichtigungen einrichten

Einfach `ha_notifications` aktivieren — sonst nichts. Das Add-on nutzt automatisch den vom Supervisor bereitgestellten Zugriff auf die Home-Assistant-API (`homeassistant_api`); ein manuell erstellter Access Token ist nicht mehr nötig.

### Medien pro Chat abschalten

`download_media` gilt fuer alle Chats. Einzelne Chats lassen sich davon ausnehmen: in der Chat-Kopfzeile auf das Bild-Symbol klicken.

- **AUS**: In diesem Chat werden keine Fotos, Sprachnachrichten und Videos mehr geladen, und vorhandene Medien bleiben ausgeblendet. **Geloescht wird nichts.**
- **Wieder AN**: Die vorhandenen Medien sind sofort wieder sichtbar, und was waehrend der abgeschalteten Zeit liegengeblieben ist, laedt das Add-on im Hintergrund nach (soweit WhatsApp es noch ausliefert).

Die Ausnahmen stehen in `/config/chatmedia.json` und ueberleben Neustarts. Ueber die API:

```bash
curl http://<HA-IP>:17786/api/chat-media -H "Authorization: Bearer <Token>"
curl -X POST http://<HA-IP>:17786/api/chat-media -H "Authorization: Bearer <Token>"   -H 'Content-Type: application/json'   -d '{"chatId":"4915112345678@c.us","enabled":false}'
```

## REST-API

### Zwei Ports, zwei Sicherheitsstufen

| Port | Was liegt dort | Schutz | Standard |
|------|----------------|--------|----------|
| 17776 | Weboberfläche **und** REST-API | keiner — wer den Port erreicht, kann mitlesen und senden | **zu** |
| 17786 | nur REST-API (`/api/*`), keine Oberfläche | Token-Pflicht | zu |

Port 17776 kennt bewusst keine Anmeldung: die Weboberfläche ruft ihre eigenen
`/api/`-Routen aus dem Browser auf, eine Token-Pflicht würde sie lahmlegen. Sein
Schutz ist deshalb, dass er **seit 1.8.31 nicht mehr freigegeben** ist. Der
Zugang zur Oberfläche läuft über HA-Ingress (Anmeldung durch Home Assistant)
oder das MessengerPortal — beides unverändert, beide gehen nicht über den
Host-Port.

Gibst du 17776 unter *Netzwerk* wieder frei, steht alles offen, was hier
beschrieben ist: mitlesen, senden, Medien holen, Kontakte blockieren, ohne
Passwort, für jedes Gerät im Netz.

Port 17786 ist der Weg für Skripte und fremde Geräte. Er braucht zwei Schalter:

1. Option **REST-API auf eigenem Port** (`api_enabled`) einschalten und einen
   **API-Token** (`api_token`) setzen — ohne Token startet der Port nicht
2. Port 17786 unter *Netzwerk* freigeben, wenn er aus dem LAN erreichbar sein soll

Jeder Aufruf braucht dann die Kopfzeile `Authorization: Bearer <Token>`; ohne sie
antwortet der Port mit `401`. Die Weboberfläche gibt es dort auch mit gültigem
Token nicht — sie wäre sonst ein zweiter, gleichwertiger Weg auf alles.

Token erzeugen:

```bash
openssl rand -hex 32
```


```
GET  /api/status                     → Verbindungsstatus (inkl. WhatsApp-Web- und Bibliotheksfassung)
GET  /api/chats                      → Liste aller Chats
GET  /api/contacts                   → Adressbuch (auch Kontakte ohne Chat), ?refresh=1 umgeht den Cache
GET  /api/messages?chat=<id>         → Nachrichten eines Chats; ?limit=n liefert die jüngsten n mit {messages,more,total}, ?before=<ts> die älteren davor
GET  /api/last-received              → Zeitpunkt der letzten empfangenen Nachricht
GET  /api/last-received?chat=<id>    → Letzte empfangene Nachricht eines bestimmten Chats
POST /api/send                       → Nachricht senden
POST /api/send-media                 → Bild/Dokument senden
GET  /api/presence-overview          → Zuletzt online aller Kontakte; ?refresh=1 startet einen Rundlauf
GET  /api/search?q=<text>            → Suche über alle Chats (eigener Verlauf + WhatsApp-Suche)
GET  /api/check-number?number=<nr>   → Ist die Rufnummer bei WhatsApp? (max. 20 Abfragen/Minute)
GET  /api/contact/:chatId/extra      → Gemeinsame Gruppen und Anzahl verknüpfter Geräte
GET  /api/blocked                    → Liste der blockierten Kontakte
POST /api/contact/:chatId/block      → Kontakt blockieren
POST /api/contact/:chatId/unblock    → Blockierung aufheben
GET  /api/presence/:chatId           → Zuletzt online eines Kontakts (online, lastSeen, denied); ?announce=1 erzwingt die Verfügbarkeitsmeldung, ?announce=0 unterdrückt sie
GET  /api/me                         → Eigenes Profil (Nummer, Name, Info-Text)
POST /api/me/about                   → Info-Text im Profil setzen
GET  /api/my-status                  → Eigene laufende Statusmeldungen (24 h)
POST /api/my-status/text             → Text-Status posten (text, backgroundColor, fontStyle 0-7)
POST /api/my-status/media            → Bild-/Video-Status posten (file oder templateFile, caption)
POST /api/my-status/revoke           → Eigenen Status zurückziehen (id)
GET  /api/status-templates           → Gespeicherte Status-Vorlagen
POST /api/status-templates           → Vorlage anlegen oder ändern (id zum Ändern)
POST /api/status-templates/:id/delete → Vorlage löschen
GET  /api/chat-media                 → Welche Chats sind vom Medien-Download ausgenommen
POST /api/chat-media                 → Medien eines Chats an-/abschalten ({chatId, enabled})
GET  /api/privacy                    → Aktuelle Datenschutzeinstellungen lesen (zuletzt online, Profilbild, Info, Status, Lesebestätigungen) samt zulässiger Werte
POST /api/privacy                    → Einstellung ändern ({name, value}); name: lastSeen, online, profilePicture, about, groupAdd, callAdd, readReceipts
GET  /api/privacy/disallowed?category=<c> → Ausnahmeliste „Meine Kontakte, außer…" lesen, mit Namen (lastSeen, about, profilePicture, groupAdd)
POST /api/privacy/disallowed         → Ausnahmeliste ändern ({category, add:[...], remove:[...]}) und die Kategorie dabei auf „Meine Kontakte, außer…" stellen
GET  /api/selfcheck                  → Selbsttest: sitzen alle WhatsApp-Web-Bausteine noch? (?run=1 prueft sofort)
GET  /api/privacy/status             → Publikum der Statusmeldungen lesen (mode: contacts/deny/allow + Kontaktliste)
POST /api/privacy/status             → Publikum setzen ({mode, ids:[...]}); bei deny/allow wird die Liste vollständig ersetzt
GET  /api/privacy/source?module=<n>  → Quelltext eines WhatsApp-Web-Moduls aus der Modulliste (Diagnose, nur lesen)
GET  /api/privacy/diag               → Diagnose: findet WhatsApp Web ein Modul für die Datenschutzeinstellungen? (?scan=1 durchsucht die Bundles nach echten Modulnamen, ?probeFound=1 probiert die Fundstellen gleich durch) — liest nur, ändert nichts
GET  /api/export/:chatId             → Chat als HTML exportieren
DELETE /api/messages/:chatId/:msgId  → Nachricht für alle löschen
POST /api/logout                     → Abmelden
POST /api/reset                      → Session zurücksetzen (neuer QR-Code)
```

### Nachricht senden

```bash
curl -X POST http://<HA-IP>:17786/api/send \
  -H "Authorization: Bearer <Token>" \
  -H "Content-Type: application/json" \
  -d '{"to": "4915123456789", "message": "Hallo aus HA!"}'
```

`to` — Telefonnummer (nur Ziffern, ohne `+`) oder Chat-ID (`4915123456789@c.us`)

### HA-Automatisierung

`configuration.yaml`:
```yaml
rest_command:
  whatsapp_send:
    url: http://localhost:17786/api/send
    method: POST
    content_type: application/json
    headers:
      Authorization: !secret whatsapp_api_token
    payload: '{"to": "{{ to }}", "message": "{{ message }}"}'
```

`secrets.yaml`:
```yaml
whatsapp_api_token: "Bearer <Token>"
```

Automatisierung:
```yaml
action:
  - service: rest_command.whatsapp_send
    data:
      to: "4915123456789"
      message: "Bewegung erkannt!"
```

### HA-Sensor: Letzte empfangene Nachricht

`GET /api/last-received` gibt zurück, wann zuletzt eine Nachricht empfangen wurde — über alle Chats oder für einen bestimmten Chat:

```json
{
  "timestamp": 1748500000000,
  "iso": "2026-05-29T10:30:00.000Z",
  "chatId": "4915123456789@c.us",
  "chatName": "Max Mustermann",
  "contact": "Max Mustermann",
  "preview": "Hallo!"
}
```

`null` wenn noch keine Nachricht empfangen wurde.

**`configuration.yaml` — REST-Sensor:**
```yaml
sensor:
  - platform: rest
    name: WhatsApp letzte Nachricht
    resource: http://localhost:17786/api/last-received
    headers:
      Authorization: !secret whatsapp_api_token
    value_template: "{{ value_json.iso }}"
    json_attributes:
      - chatName
      - contact
      - preview
    scan_interval: 30
```

Attribute im Dashboard anzeigen:
```yaml
type: markdown
content: >
  **WhatsApp** — {{ state_attr('sensor.whatsapp_letzte_nachricht', 'chatName') }}
  {{ state_attr('sensor.whatsapp_letzte_nachricht', 'preview') }}
  _({{ states('sensor.whatsapp_letzte_nachricht') | as_datetime | relative_time }})_
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
| `download_media` | `false` | Automatically download and display received photos (can be turned off per chat, see below) |
| `webhook_incoming` | — | URL for incoming messages (e.g. HA webhook) |
| `initial_chats` | `30` | Number of chats loaded on startup (recommended: 20–50) |
| `initial_messages` | `20` | Messages per chat on startup (recommended: 20–50) |
| `keep_deleted` | `false` | Keep deleted messages visible (with 🚫 badge) |
| `debug_mode` | `false` | Verbose logging for troubleshooting |
| `ha_notifications` | `false` | HA notification for new incoming messages |
| `ha_notifications_privacy` | `false` | Show only "WhatsApp / New message" — no sender, no content |

### Setting up HA notifications

Just enable `ha_notifications` — nothing else. The add-on automatically uses the Home Assistant API access provided by the Supervisor (`homeassistant_api`); a manually created access token is no longer required.

### Turning media off per chat

`download_media` applies to every chat. Individual chats can be excluded: click the image icon in the chat header.

- **OFF**: no photos, voice messages or videos are downloaded for that chat any more, and existing media stay hidden. **Nothing is deleted.**
- **ON again**: existing media show up right away, and whatever was missed while it was off is fetched in the background (as far as WhatsApp still serves it).

The exceptions live in `/config/chatmedia.json` and survive restarts. Via the API:

```bash
curl http://<HA-IP>:17786/api/chat-media -H "Authorization: Bearer <token>"
curl -X POST http://<HA-IP>:17786/api/chat-media -H "Authorization: Bearer <token>"   -H 'Content-Type: application/json'   -d '{"chatId":"4915112345678@c.us","enabled":false}'
```

## REST API

### Two ports, two security levels

| Port | What it serves | Protection | Default |
|------|----------------|------------|---------|
| 17776 | web interface **and** REST API | none — anyone who reaches it can read and send | **closed** |
| 17786 | REST API only (`/api/*`), no interface | token required | closed |

Port 17776 deliberately has no login: the web interface calls its own `/api/`
routes from the browser, so requiring a token would break it. Its protection is
therefore that it is **no longer published as of 1.8.31**. The interface is
reached through HA Ingress (authenticated by Home Assistant) or the
MessengerPortal — both unchanged, neither goes through the host port.

Publish 17776 under *Network* again and everything described here is wide open:
reading, sending, fetching media, blocking contacts, without a password, for
any device on the network.

Port 17786 is the path for scripts and other machines. It needs two switches:

1. Turn on **REST API on a separate port** (`api_enabled`) and set an
   **API token** (`api_token`) — without a token the port does not start
2. Publish port 17786 under *Network* if it should be reachable from the LAN

Every call then needs the header `Authorization: Bearer <token>`; without it the
port answers `401`. The web interface is not served there even with a valid
token — it would just be a second, equally powerful way in.

Generate a token:

```bash
openssl rand -hex 32
```


```
GET  /api/status                     → Connection status (incl. WhatsApp Web and library version)
GET  /api/chats                      → List of all chats
GET  /api/messages?chat=<id>         → Messages of a chat; ?limit=n returns the newest n as {messages,more,total}, ?before=<ts> the older ones
GET  /api/last-received              → Timestamp of the last received message
GET  /api/last-received?chat=<id>    → Last received message of a specific chat
POST /api/send                       → Send a message
POST /api/send-media                 → Send image/document
GET  /api/presence-overview          → Last seen of all contacts; ?refresh=1 starts a sweep
GET  /api/search?q=<text>            → Search across all chats (local history + WhatsApp search)
GET  /api/check-number?number=<nr>   → Is this number on WhatsApp? (max. 20 requests/minute)
GET  /api/contact/:chatId/extra      → Groups in common and number of linked devices
GET  /api/blocked                    → List of blocked contacts
POST /api/contact/:chatId/block      → Block a contact
POST /api/contact/:chatId/unblock    → Unblock a contact
GET  /api/presence/:chatId           → Last seen of a contact (online, lastSeen, denied); ?announce=1 forces the availability announcement, ?announce=0 suppresses it
GET  /api/me                         → Own profile (number, name, about text)
POST /api/me/about                   → Set the about text of your profile
GET  /api/my-status                  → Your live status updates (24 h)
POST /api/my-status/text             → Post a text status (text, backgroundColor, fontStyle 0-7)
POST /api/my-status/media            → Post a photo/video status (file or templateFile, caption)
POST /api/my-status/revoke           → Revoke one of your own status updates (id)
GET  /api/status-templates           → Saved status templates
POST /api/status-templates           → Create or update a template (id to update)
POST /api/status-templates/:id/delete → Delete a template
GET  /api/chat-media                 → Which chats are excluded from media download
POST /api/chat-media                 → Turn media on/off for one chat ({chatId, enabled})
GET  /api/privacy                    → Read current privacy settings (last seen, profile photo, about, status, read receipts) plus allowed values
POST /api/privacy                    → Change one setting ({name, value}); name: lastSeen, online, profilePicture, about, groupAdd, callAdd, readReceipts
GET  /api/privacy/disallowed?category=<c> → Read the "my contacts except…" list incl. names (lastSeen, about, profilePicture, groupAdd)
POST /api/privacy/disallowed         → Change the list ({category, add:[...], remove:[...]}) and set the category to "my contacts except…"
GET  /api/selfcheck                  → Self-check: are all WhatsApp Web internals still there? (?run=1 checks now)
GET  /api/privacy/status             → Read the status audience (mode: contacts/deny/allow + contact list)
POST /api/privacy/status             → Set the audience ({mode, ids:[...]}); for deny/allow the list is replaced as a whole
GET  /api/privacy/source?module=<n>  → Source of a WhatsApp Web module from the module map (diagnostics, read-only)
GET  /api/privacy/diag               → Diagnostics: does WhatsApp Web expose a privacy-settings module? (?scan=1 searches the bundles for real module names, ?probeFound=1 probes the hits) — read-only
GET  /api/export/:chatId             → Export chat as HTML
DELETE /api/messages/:chatId/:msgId  → Delete message for everyone
POST /api/logout                     → Log out
POST /api/reset                      → Reset session (new QR code)
```

### Send a message

```bash
curl -X POST http://<HA-IP>:17786/api/send \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"to": "4915123456789", "message": "Hello from HA!"}'
```

`to` — phone number (digits only, without `+`) or chat ID (`4915123456789@c.us`)

### HA Automation

`configuration.yaml`:
```yaml
rest_command:
  whatsapp_send:
    url: http://localhost:17786/api/send
    method: POST
    content_type: application/json
    headers:
      Authorization: !secret whatsapp_api_token
    payload: '{"to": "{{ to }}", "message": "{{ message }}"}'
```

`secrets.yaml`:
```yaml
whatsapp_api_token: "Bearer <token>"
```

Automation:
```yaml
action:
  - service: rest_command.whatsapp_send
    data:
      to: "4915123456789"
      message: "Motion detected!"
```

### HA Sensor: Last received message

`GET /api/last-received` returns when the last message was received — across all chats or for a specific chat:

```json
{
  "timestamp": 1748500000000,
  "iso": "2026-05-29T10:30:00.000Z",
  "chatId": "4915123456789@c.us",
  "chatName": "Max Mustermann",
  "contact": "Max Mustermann",
  "preview": "Hello!"
}
```

Returns `null` if no message has been received yet.

**`configuration.yaml` — REST sensor:**
```yaml
sensor:
  - platform: rest
    name: WhatsApp Last Message
    resource: http://localhost:17786/api/last-received
    headers:
      Authorization: !secret whatsapp_api_token
    value_template: "{{ value_json.iso }}"
    json_attributes:
      - chatName
      - contact
      - preview
    scan_interval: 30
```

Show attributes on a dashboard card:
```yaml
type: markdown
content: >
  **WhatsApp** — {{ state_attr('sensor.whatsapp_last_message', 'chatName') }}
  {{ state_attr('sensor.whatsapp_last_message', 'preview') }}
  _({{ states('sensor.whatsapp_last_message') | as_datetime | relative_time }})_
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
