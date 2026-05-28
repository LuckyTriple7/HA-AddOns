# CardBoard

Home Assistant Add-on – zeigt HA-Sensordaten als gerenderte Markdown-Karten im Browser.

## Features

- Jinja2-Templates werden direkt über die HA-API gerendert
- Mehrere Benutzer mit eigenen Ansichten
- Konfigurierbares Kartenlayout (1–`max_cards` Karten nebeneinander)
- Markdown-Rendering (Überschriften, Fett, Tabellen, …)
- **Admin-Panel** – Benutzerverwaltung und Template-Editor direkt im Browser
- Template-Editor mit Live-Vorschau
- Dark / Light Mode
- Sprache umschaltbar (🇩🇪 / 🇬🇧)
- Rate Limiting – IP-Sperre nach zu vielen Fehlversuchen
- PWA-fähig – auf iOS/Android als App installierbar
- Cookie-Session (konfigurierbar, Standard: 7 Tage)
- Konfigurierbares Refresh-Intervall
- Responsives Layout (Mobile: Karten untereinander)

## Schnellstart

1. Add-on installieren und starten
2. HA Long-Lived Access Token in den Optionen hinterlegen
3. Web-Oberfläche unter `http://<HA-IP>:17772` aufrufen
4. Admin-Panel unter `http://<HA-IP>:17773/admin/` öffnen
5. Ersten Benutzer anlegen und Templates erstellen

Ausführliche Dokumentation: siehe **DOCS.md**

---

# CardBoard *(English)*

Home Assistant Add-on – displays HA sensor data as Markdown cards in the browser.

## Features

- Jinja2 templates rendered directly via the HA API
- Multiple users with individual views
- Configurable card layout (1–`max_cards` cards side by side)
- Markdown rendering (headings, bold, tables, …)
- **Admin Panel** – user management and template editor directly in the browser
- Template editor with live preview
- Dark / Light mode
- Switchable language (🇩🇪 / 🇬🇧)
- Rate limiting – IP block after too many failed attempts
- PWA-ready – installable as an app on iOS/Android
- Cookie session (configurable, default: 7 days)
- Configurable refresh interval
- Responsive layout (mobile: cards stacked vertically)

## Quick Start

1. Install and start the add-on
2. Enter your HA Long-Lived Access Token in the options
3. Open the web interface at `http://<HA-IP>:17772`
4. Open the Admin Panel at `http://<HA-IP>:17773/admin/`
5. Create your first user and set up templates

Full documentation: see **DOCS.en.md**
