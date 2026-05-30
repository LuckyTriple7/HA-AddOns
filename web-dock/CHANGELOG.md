# Changelog

## 0.0.4

- Bugfix: Icon wird jetzt immer vom Zieldienst geladen (war vorher nur aktiv wenn `icon:` manuell gesetzt)
- Icon-Fetch robuster: mehr Fallback-Pfade (`apple-touch-icon`, `/favicon.png`, `/favicon.svg`, ...)
- Icon-Response: direkter `Response(data)` statt `send_file(BytesIO(...))` (stabiler)

## 0.0.3

- Icons werden automatisch von der Zielseite geladen (Favicon / Apple-Touch-Icon, 1h Cache)
- Manueller Override: PNG-Datei in `/addon_configs/web-dock/` ablegen und `icon: "datei.png"` setzen

## 0.0.2

- Port von 17771 auf 17780 geändert

## 0.0.1

- Erstveröffentlichung
- Passwortgeschützter Startportal für bis zu 10 interne Web-Dienste
- Online-Status (grüner Punkt) per TCP-Port-Check
- PNG-Icons aus dem addon_config-Ordner
- Reverse-Proxy mit nginx, WebSocket-Unterstützung
- Zurück-zum-Portal-Button in jeder Proxy-Seite (drag-fähig)
- Dark/Light-Mode, DE/EN Sprachauswahl
- PWA-Unterstützung (installierbar als App)
- Rate Limiting für Login-Seite
