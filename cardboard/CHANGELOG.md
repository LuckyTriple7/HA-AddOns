# Changelog

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
