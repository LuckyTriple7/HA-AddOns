# MessengerPortal

Zentrale, passwortgeschützte Startseite für deine Messenger-Add-ons (WhatsApp, Telegram, Signal).

## Konfiguration

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `username` | string | `admin` | Benutzername für den Login |
| `password` | string | `secret` | Passwort für den Login |
| `session_hours` | int | `24` | Gültigkeitsdauer der Session in Stunden |
| `trusted_proxies` | string | – | Adresse des vorgeschalteten Reverse-Proxys (Komma-getrennt, CIDR erlaubt). Nur von dort übernimmt das Portal die echte Aufrufer-Adresse für die Anmeldesperre. Leer: es zählt die Adresse, die direkt ankommt |
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
- Unter Windows erscheint das Portal im „Freigeben“-Dialog nur bei Installation über Edge, mit Chrome nicht
- **Mein Status**: Oberster Eintrag der Chatliste postet in den eigenen Status bzw. die eigene Story statt in einen Chat. WhatsApp: Text, Bilder und Videos. Telegram: nur Bilder, sichtbar für Kontakte (braucht Telegram 1.7.31). Signal: Bilder oder Videos ohne Text, „Meine Story“ (braucht Signal 1.7.5). Mehrere Dateien werden mehrere Statusmeldungen
- Ohne Teilen-Menü: Knopf mit dem Papierflieger („Senden an …“) in der Kopfzeile des Portals. Dort Text eintippen, Dateien wählen, hineinziehen oder aus der Zwischenablage einfügen

## Status-Spiegel (WhatsApp → Signal/Telegram)

Knopf mit den zwei Pfeilen in der Kopfzeile des Portals: Dort lässt sich je Ziel einschalten, dass neue eigene WhatsApp-Statusmeldungen zusätzlich als Signal- bzw. Telegram-Story gepostet werden. Egal ob am Handy oder im Add-on gepostet. Das Fenster zeigt auch, wann zuletzt gespiegelt wurde und ob etwas schiefging. Der Knopf erscheint nur, wenn WhatsApp und mindestens eines der Ziele als Messenger eingetragen sind.

- Abfrage alle 5 Minuten, der Spiegel kommt also etwas später
- Was beim Einschalten schon läuft, wird nicht gespiegelt
- Text-Status kommen als Bild an (grüner Hintergrund, weiße Schrift). Emojis fallen dabei weg
- Bilder und Videos brauchen im WhatsApp-Add-on `download_media: true`, sonst gibt es keine Datei zum Weiterreichen
- Signal: Bilder und Videos, ohne Bildunterschrift. Braucht Signal 1.7.5
- Telegram: Bilder mit Bildunterschrift, Videos werden übersprungen, sichtbar für Kontakte. Braucht Telegram 1.7.31
- Zurückziehen in WhatsApp löscht die gespiegelte Story nicht; sie läuft nach 24 Stunden ab
- Was passiert, steht im Portal-Log unter „Status-Spiegel“

## Sicherheitshinweis

Das Add-on läuft über HTTP. Für den Zugriff aus dem Internet wird ein vorgeschalteter NGINX-Reverse-Proxy mit HTTPS empfohlen.
