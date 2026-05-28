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

---

# CardBoard *(English)*

Home Assistant Add-on – displays HA sensor data as Markdown cards in the browser.

## Features

- Jinja2 templates rendered directly via the HA API
- Multiple users with individual views (read-only)
- 1–3 cards side by side (automatically determined by template count)
- Markdown rendering (headings, bold, tables, …)
- Whitespace alignment preserved (monospace font)
- Cookie session (7 days)
- Configurable refresh interval
- Responsive layout

## Quick Start

1. Install and start the add-on
2. Enter your HA Long-Lived Access Token in the options
3. Create `/config/addons_config/cardboard/users.yaml`
4. Place template files under `/config/addons_config/cardboard/<username>/`
5. Open the web interface at `http://<HA-IP>:17772`

Full documentation: see **DOCS.en.md**
