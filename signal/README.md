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

## Hinweise

- Basiert auf [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api)
- Das Konto wird als verknüpftes Gerät hinzugefügt, nicht als Primärgerät registriert
- Zum Abmelden: Button "Abmelden" in der UI, danach auch in Signal unter Verknüpfte Geräte entfernen
- "Für alle löschen" erfordert eine aktuelle Version von signal-cli-rest-api; ältere Versionen löschen nur lokal

→ [Changelog](CHANGELOG.md)
