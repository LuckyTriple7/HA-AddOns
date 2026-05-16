# Telegram

Telegram als vollwertiger Client direkt in Home Assistant — mit Chat-UI, REST-API und Webhook-Support.

## Funktionen

- **MTProto-Login**: Telefonnummer + SMS/App-Code, 2FA unterstützt
- **Web-UI**: Chat-Liste, Konversationen, Nachrichten senden/empfangen direkt in der HA-Sidebar
- **Fotos**: Empfangene Bilder anzeigen (optional, siehe `download_media`)
- **Nachrichten löschen**: Nachricht für alle entfernen (Hover → ✕)
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

## Hinweise

- Basiert auf [GramJS](https://github.com/gram-js/gramjs) (offizielle MTProto-Implementierung für JavaScript)
- Session wird in `/data/session.txt` gespeichert und überlebt Neustarts
- Chats und Nachrichten werden in `/data/chats.json` und `/data/messages.json` gespeichert
- Medien werden in `/data/media/` gespeichert

→ [Changelog](CHANGELOG.md)
