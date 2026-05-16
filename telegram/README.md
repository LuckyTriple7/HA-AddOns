# Telegram Add-on für Home Assistant

Telegram als vollwertiger Client direkt in Home Assistant — mit Chat-UI, REST-API und Webhook-Support.

## Einrichtung

### 1. API-Credentials besorgen

1. Auf [my.telegram.org](https://my.telegram.org) einloggen
2. → **API development tools**
3. App erstellen (Name und Plattform beliebig)
4. **App api_id** und **App api_hash** notieren

### 2. Add-on konfigurieren

| Option | Beschreibung |
|--------|-------------|
| `api_id` | Numerische API-ID von my.telegram.org |
| `api_hash` | API-Hash von my.telegram.org |
| `phone_number` | Telefonnummer mit Ländervorwahl, z.B. `+4917612345678` |
| `dark_mode` | `true` = dunkel (Standard), `false` = hell |
| `webhook_incoming` | URL für eingehende Nachrichten (optional) |

### 3. Ersten Start

Nach dem Start des Add-ons erscheint ein Code-Eingabefeld in der Web-UI. Telegram sendet einen Code per App-Benachrichtigung oder SMS — diesen Code eingeben, fertig.

Bei aktivierter 2-Faktor-Authentifizierung wird danach das Cloud-Passwort abgefragt.

## REST-API

```
GET  /api/status              → { status, name, id }
GET  /api/chats               → [ { id, name, lastMsg, lastTime } ]
GET  /api/messages/:chatId    → [ { id, body, timestamp, fromMe } ]
POST /api/send                → { to, message }
POST /api/logout              → Session löschen und neu verbinden
```

## Webhook

Eingehende Nachrichten werden als POST an die konfigurierte URL gesendet:

```json
{
  "from": "chatId",
  "name": "Kontaktname",
  "message": "Nachrichtentext",
  "timestamp": 1716000000000
}
```

→ [Changelog](CHANGELOG.md)
