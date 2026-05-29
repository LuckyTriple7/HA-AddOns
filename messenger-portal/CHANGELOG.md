# Changelog – MessengerPortal

## [0.0.2] – 2026-05-29

### Added
- Brute-Force-Schutz: nach 5 Fehlversuchen wird die IP für 15 Minuten gesperrt (Log-Ausgabe)
- X-Forwarded-For-Unterstützung via ProxyFix – echte Client-IP wird auch hinter NGINX erkannt
- Fehlermeldung bei gesperrter IP (DE/EN)

## [0.0.1] – 2026-05-29

### Added
- Initiales Release
- Passwortgeschützte Login-Seite
- Zentrale Startseite mit Messenger-Karten (WhatsApp, Telegram, Signal)
- Konfigurierbare Session-Dauer
- Dark Mode / Light Mode mit automatischer Erkennung via `prefers-color-scheme`
- Manuelle Umschaltung und persistente Speicherung im Browser
- Mehrsprachige UI: Deutsch und Englisch, automatische Spracherkennung via `Accept-Language`
- Responsive Design / Mobile-optimiert
- PWA-Unterstützung (Manifest + Service Worker)
- Konfigurierbare Messenger: Name, Icon, Port, aktiviert/deaktiviert
