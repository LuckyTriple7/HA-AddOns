# Changelog

## 0.0.9
- Option `session_lifetime` (Tage, Default: 7) für die Gültigkeit des Login-Cookies

## 0.0.8
- HA-Startzeit aus `sensor.uptime` (konfigurierbar via Option `uptime_sensor`, Default: `sensor.uptime`)
- Timestamp wird im Browser in lokaler Zeitzone formatiert
- Kein falscher Timestamp mehr wenn der Sensor nicht vorhanden oder `unavailable` ist

## 0.0.7
- HA-Status: `online seit` wird nur noch angezeigt wenn CardBoard tatsächlich einen Ausfall → Wiederkommen-Übergang beobachtet hat (kein falscher Timestamp beim ersten Start)

## 0.0.6
- HA-Status-Anzeige auf der Login-Seite (🟢/🔴 Punkt, Version, online seit)
- HA-Status-Badge im Footer der View-Seite (wird jede Minute aktualisiert)
- Neuer öffentlicher Endpunkt `/api/public/ha-status` (kein Login erforderlich, Cache 30 s)

## 0.0.5
- port/admin_port vollständig aus Schema entfernt (verhindert doppelte Anzeige in HA UI)

## 0.0.4
- Persönliche Begrüßungsnachricht auf der Login-Seite (Add-on Option `login_message`)
- Default HA-URL auf `homeassistant.local:8123` geändert
- Port-Konfiguration aus den Optionen entfernt (Supervisor übernimmt Mapping)
- `/api/public/config` Endpunkt für öffentliche Login-Seiten-Daten

## 0.0.3
- Dark/Light-Mode Toggle mit localStorage-Persistenz
- Manueller Refresh-Button mit Dreh-Animation
- HA Token-Validierung beim Start im Log

## 0.0.2
- Demo-User mit drei Beispiel-Karten (Übersicht, Klima, Status)
- users.yaml und Demo-Templates werden beim ersten Start automatisch angelegt

## 0.0.1
- Erste Version
- Jinja2-Templates werden via HA `/api/template` gerendert
- Multi-User-Unterstützung mit Cookie-Session (7 Tage)
- 1–3 Karten nebeneinander je Benutzer (automatisch aus Template-Anzahl)
- Markdown-Rendering mit marked.js
- Konfigurierbares Refresh-Intervall
- Responsive Layout (Mobile: Karten untereinander)
