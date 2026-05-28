# CardBoard

Home Assistant Add-on – zeigt HA-Sensordaten als Markdown-Karten im Browser.

## Features

- Jinja2-Templates werden direkt über die HA-API gerendert
- Mehrere Benutzer mit eigenen Ansichten (read-only)
- 1–3 Karten nebeneinander (automatisch aus Template-Anzahl)
- Markdown-Rendering (Überschriften, Fett, Tabellen, …)
- Leerzeichen-Ausrichtung bleibt erhalten (Monospace)
- Cookie-Session (7 Tage)
- Konfigurierbares Refresh-Intervall
- Responsives Layout

## Schnellstart

1. Add-on installieren und starten
2. HA Long-Lived Access Token in den Optionen hinterlegen
3. `/config/addons_config/cardboard/users.yaml` anlegen
4. Template-Dateien unter `/config/addons_config/cardboard/<username>/` ablegen
5. Web-Oberfläche unter `http://<HA-IP>:17772` aufrufen

Ausführliche Dokumentation: siehe **DOCS.md**
