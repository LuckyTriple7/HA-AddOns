# MessengerPortal

Zentrale, passwortgeschützte Startseite für deine Messenger-Add-ons (WhatsApp, Telegram, Signal).

## Konfiguration

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `username` | string | `admin` | Benutzername für den Login |
| `password` | string | `secret` | Passwort für den Login |
| `session_hours` | int | `24` | Gültigkeitsdauer der Session in Stunden |
| `messengers[].name` | string | – | Anzeigename des Messengers |
| `messengers[].icon` | string | – | Icon-Typ: `whatsapp`, `telegram` oder `signal` |
| `messengers[].port` | int | – | Port des jeweiligen Messenger-Add-ons |
| `messengers[].enabled` | bool | `true` | Messenger anzeigen oder ausblenden |

## Verwendung

1. Add-on starten
2. Web-UI öffnen: `http://<ha-host>:17770`
3. Mit konfiguriertem Benutzernamen und Passwort anmelden
4. Gewünschten Messenger per Klick öffnen

## PWA

Die Seite kann als Progressive Web App zum Home-Screen hinzugefügt werden:
- **iOS/Safari**: Teilen → „Zum Home-Bildschirm"
- **Android/Chrome**: Menü → „App installieren"

## Teilen / Senden an

Ist das Portal als App installiert, taucht es im Teilen-Menü des Geräts auf (Android mit Chrome, Windows mit Edge). Ablauf: Inhalt teilen → MessengerPortal → Messenger wählen → Chat wählen → senden.

- Unterstützt: Text, Links, Bilder, Videos, Audio, PDF, Textdateien, Office-Dokumente, ZIP – bis 64 MB je Datei
- Voraussetzung: Zugriff über HTTPS und installierte App. Über Home-Assistant-Ingress gibt es kein Teilen-Ziel
- Nach einem Update, das das Teilen-Ziel ändert, die App einmal neu installieren
- Der geteilte Inhalt liegt bis zum Senden nur im Browser, nicht auf dem Server

## Sicherheitshinweis

Das Add-on läuft über HTTP. Für den Zugriff aus dem Internet wird ein vorgeschalteter NGINX-Reverse-Proxy mit HTTPS empfohlen.
