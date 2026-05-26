# HA-AddOns

Eigene Home Assistant Apps von [LuckyTriple7](https://github.com/LuckyTriple7).

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

> Ich bin kein klassischer Programmierer — aber mit Claude Code als KI-Assistenten entwickle und pflege ich diese Apps selbst. Feedback und Fragen gerne als [GitHub Issue](https://github.com/LuckyTriple7/HA-AddOns/issues).

## Installation

[![Add repository to my HA](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FLuckyTriple7%2FHA-AddOns)

Oder manuell in Home Assistant:

**Einstellungen → Apps → App-Store → ⋮ → Repositories**

```
https://github.com/LuckyTriple7/HA-AddOns
```

## Apps

### [Claude Code](claudecode/)

KI-Assistent direkt in Home Assistant — zum Erstellen von Automatisierungen, Debuggen und Verwalten der Konfiguration. Fork von [apbb2/robsonfelix-hass-addons](https://github.com/apbb2/robsonfelix-hass-addons/tree/main/claudecode) mit Playwright-Fix.

- Web-Terminal direkt in der HA-Sidebar
- Vollständige Integration mit Home Assistant (MCP-Server)
- Playwright-Browser-Automatisierung über CDP
- Automatische Claude Code Updates beim Start

→ [Dokumentation & Changelog](claudecode/README.md)

### [Playwright Browser](playwright-browser/)

Headless-Chromium-Browser mit CDP-Endpoint für Browser-Automatisierung. Wird von der **Claude Code App** verwendet, um Websites aufzurufen und zu steuern.

- Chrome DevTools Protocol (CDP) auf Port 9222
- Automatisch erkannt von der Claude Code App
- Unterstützung für amd64 und aarch64

→ [Dokumentation & Changelog](playwright-browser/README.md)

### [FileBox](filebox/)

Web-Oberfläche zum Hoch- und Herunterladen von Dateien direkt in Home Assistant.

- Dateien hochladen, herunterladen und verwalten
- Standardmäßig Zugriff auf `/share/filebox`
- Optionaler Zugriff auf `/media`, `/config`, `/backup`
- Konfigurierbarer Benutzername und Passwort (werden aus den App-Optionen übernommen)
- Deutsche Benutzeroberfläche, weitere Benutzer im UI anlegbar

→ [Dokumentation & Changelog](filebox/README.md)

### [Firefox DE](firefox/)

Firefox ESR direkt in der HA-Seitenleiste via noVNC — deutschsprachig, mit persistentem Profil.

- Vollständiger Firefox-Browser ohne externen VNC-Client
- Deutsche Sprache voreingestellt
- Persistentes Profil in `/data/profile` — bleibt über Neustarts erhalten
- Downloads in `/share/firefox`
- Clipboard-Sync über HA-Ingress (HTTPS)
- Optionale RAM-Begrenzung via `memory_limit_mb`

→ [Dokumentation & Changelog](firefox/README.md)

### [Webtop XFCE](ubuntu-webtop/)

Vollständiger XFCE-Desktop im Webbrowser, direkt in Home Assistant integriert.

- KasmVNC-Streaming (CPU-effizient, delta-basiert)
- Systemsprache Deutsch (de_DE.UTF-8)
- Firefox, Thunderbird, Geany, VLC, Thunar mit SMB-Netzwerkzugriff und mehr
- Persistente Konfiguration über Updates hinweg

| | |
|---|---|
| **Zugriff HTTP** | `http://<HA-IP>:7776` |
| **Zugriff HTTPS** | `https://<HA-IP>:7777` |
| **Benutzername** | `abc` |

→ [Dokumentation & Changelog](ubuntu-webtop/README.md)

### [WhatsApp](whatsapp/)

WhatsApp Web als persistente Session direkt in Home Assistant — mit Chat-UI, REST-API und Webhook-Support.

- QR-Code einmalig scannen, Session bleibt über Neustarts erhalten
- Chat-Liste mit Kontaktnamen und Nachrichtenvorschau (wie WhatsApp Web)
- Nachrichten senden und empfangen direkt in der HA-Sidebar
- REST-API für Automatisierungen (`POST /api/send`)
- Webhook für eingehende Nachrichten (HA-Webhook-Trigger)
- Responsives Design für Desktop und Handy

→ [Dokumentation & Changelog](whatsapp/README.md)

### [Telegram](telegram/)

Telegram als vollwertiger Client direkt in Home Assistant — mit Chat-UI, REST-API und Webhook-Support.

- Anmelden mit bestehendem Telegram-Konto (Telefonnummer + Code, kein QR)
- Zugriff auf alle persönlichen Chats, Gruppen und Kanäle
- Nachrichten senden und empfangen direkt in der HA-Sidebar
- REST-API für Automatisierungen (`POST /api/send`)
- Webhook für eingehende Nachrichten (HA-Webhook-Trigger)
- Session bleibt nach Neustart erhalten

→ [Dokumentation & Changelog](telegram/README.md)

### [Signal](signal/)

Signal Messenger als verknüpftes Gerät direkt in Home Assistant — mit Chat-UI, REST-API und Webhook-Support.

- Bestehendes Signal-Konto via QR-Code verknüpfen, Session bleibt erhalten
- Chat-Liste mit Konversationen und Nachrichtenvorschau
- Nachrichten senden und empfangen direkt in der HA-Sidebar
- REST-API für Automatisierungen (`POST /api/send`)
- Webhook für eingehende Nachrichten (HA-Webhook-Trigger)
- Responsives Design für Desktop und Handy

→ [Dokumentation & Changelog](signal/README.md)

### [MariaDB 2](mariadb2/)

Zweite unabhängige MariaDB-Instanz — parallel zur offiziellen MariaDB-App betreibbar, ohne Konflikte.

- Vollständig isoliert (eigener Container, Port 3307, eigene Daten)
- Gleiche Konfigurationsstruktur wie die offizielle MariaDB-App
- Option: Nextcloud-Datenbank automatisch anlegen
- Ideal als dedizierte Datenbank für Nextcloud

→ [Dokumentation & Changelog](mariadb2/README.md)

### [Collabora Online](collabora/)

Office-Server für Nextcloud — öffne und bearbeite Dokumente direkt im Browser, ohne Download.

- Bearbeite `.docx`, `.xlsx`, `.pptx` und ODF-Dateien direkt in Nextcloud
- Kollaboratives Bearbeiten mit mehreren Nutzern gleichzeitig
- Kein separater Cloud-Dienst nötig — läuft lokal auf dem NUC
- Einfache Einrichtung: URL eintragen, fertig

→ [Dokumentation & Changelog](collabora/README.md)

### [Nextcloud](nextcloud/)

Nextcloud direkt in Home Assistant — private Cloud mit Web-UI und SMB-Netzwerkspeicher-Unterstützung.

- Vollständige Nextcloud-Instanz auf Basis des linuxserver.io-Images
- Zugriff über HTTPS (`https://<HA-IP>:7443`)
- SMB-Netzwerklaufwerke direkt in der Konfiguration einbindbar (bis zu 3 Shares)
- Web-Terminal für occ-Befehle direkt in der HA-Sidebar
- Automatische Updates via GitHub Actions
- MariaDB Auto-Discovery (alternativ SQLite)

→ [Dokumentation & Changelog](nextcloud/README.md)

---

# HA-AddOns (English)

Custom Home Assistant apps by [LuckyTriple7](https://github.com/LuckyTriple7).

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

> I'm not a traditional programmer — but with Claude Code as my AI assistant I develop and maintain these apps myself. Feedback and questions welcome as a [GitHub Issue](https://github.com/LuckyTriple7/HA-AddOns/issues).

## Installation

[![Add repository to my HA](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FLuckyTriple7%2FHA-AddOns)

Or manually in Home Assistant:

**Settings → Apps → App Store → ⋮ → Repositories**

```
https://github.com/LuckyTriple7/HA-AddOns
```

## Apps

### [Claude Code](claudecode/)

AI assistant directly in Home Assistant — for creating automations, debugging and managing your configuration. Forked from [apbb2/robsonfelix-hass-addons](https://github.com/apbb2/robsonfelix-hass-addons/tree/main/claudecode) with a Playwright fix.

- Web terminal directly in the HA sidebar
- Full Home Assistant integration (MCP server)
- Playwright browser automation via CDP
- Automatic Claude Code updates on startup

→ [Documentation & Changelog](claudecode/README.md)

### [Playwright Browser](playwright-browser/)

Headless Chromium browser with CDP endpoint for browser automation. Used by the **Claude Code app** to browse and control websites.

- Chrome DevTools Protocol (CDP) on port 9222
- Automatically detected by the Claude Code app
- Supports amd64 and aarch64

→ [Documentation & Changelog](playwright-browser/README.md)

### [FileBox](filebox/)

Web UI for uploading and downloading files directly in Home Assistant.

- Upload, download and manage files
- Default access to `/share/filebox`
- Optional access to `/media`, `/config`, `/backup`
- Configurable username and password (always taken from app options)
- German UI, additional users can be created in the UI

→ [Documentation & Changelog](filebox/README.md)

### [Firefox DE](firefox/)

Firefox ESR directly in the HA sidebar via noVNC — German language, persistent profile.

- Full Firefox browser without an external VNC client
- German language preset
- Persistent profile in `/data/profile` — survives restarts
- Downloads in `/share/firefox`
- Clipboard sync via HA ingress (HTTPS)
- Optional RAM limit via `memory_limit_mb`

→ [Documentation & Changelog](firefox/README.md)

### [Webtop XFCE](ubuntu-webtop/)

Full XFCE desktop in the browser, directly integrated into Home Assistant.

- KasmVNC streaming (CPU-efficient, delta-based)
- System language German (de_DE.UTF-8)
- Firefox, Thunderbird, Geany, VLC, Thunar with SMB network access and more
- Persistent configuration across updates

| | |
|---|---|
| **HTTP access** | `http://<HA-IP>:7776` |
| **HTTPS access** | `https://<HA-IP>:7777` |
| **Username** | `abc` |

→ [Documentation & Changelog](ubuntu-webtop/README.md)

### [WhatsApp](whatsapp/)

WhatsApp Web as a persistent session directly in Home Assistant — with chat UI, REST API and webhook support.

- Scan QR code once, session persists across restarts
- Chat list with contact names and message preview (like WhatsApp Web)
- Send and receive messages directly in the HA sidebar
- REST API for automations (`POST /api/send`)
- Webhook for incoming messages (HA webhook trigger)
- Responsive design for desktop and mobile

→ [Documentation & Changelog](whatsapp/README.md)

### [Telegram](telegram/)

Telegram as a full client directly in Home Assistant — with chat UI, REST API and webhook support.

- Log in with your existing Telegram account (phone number + code, no QR)
- Access all personal chats, groups and channels
- Send and receive messages directly in the HA sidebar
- REST API for automations (`POST /api/send`)
- Webhook for incoming messages (HA webhook trigger)
- Session persists across restarts

→ [Documentation & Changelog](telegram/README.md)

### [Signal](signal/)

Signal Messenger as a linked device directly in Home Assistant — with chat UI, REST API and webhook support.

- Link your existing Signal account via QR code, session persists across restarts
- Chat list with conversations and message preview
- Send and receive messages directly in the HA sidebar
- REST API for automations (`POST /api/send`)
- Webhook for incoming messages (HA webhook trigger)
- Responsive design for desktop and mobile

→ [Documentation & Changelog](signal/README.md)

### [MariaDB 2](mariadb2/)

A second independent MariaDB instance — runs alongside the official MariaDB app without any conflicts.

- Fully isolated (own container, port 3307, own data)
- Same configuration structure as the official MariaDB app
- Option: auto-create Nextcloud database
- Ideal as a dedicated database for Nextcloud

→ [Documentation & Changelog](mariadb2/README.md)

### [Collabora Online](collabora/)

Office server for Nextcloud — open and edit documents directly in the browser, without downloading.

- Edit `.docx`, `.xlsx`, `.pptx` and ODF files directly in Nextcloud
- Collaborative editing with multiple users simultaneously
- No external cloud service needed — runs locally on the NUC
- Easy setup: enter URL, done

→ [Documentation & Changelog](collabora/README.md)

### [Nextcloud](nextcloud/)

Nextcloud directly in Home Assistant — private cloud with web UI and SMB network storage support.

- Full Nextcloud instance based on the linuxserver.io image
- Access via HTTPS (`https://<HA-IP>:7443`)
- SMB network drives configurable directly in the app settings (up to 3 shares)
- Web terminal for occ commands directly in the HA sidebar
- Automatic updates via GitHub Actions
- MariaDB auto-discovery (alternatively SQLite)

→ [Documentation & Changelog](nextcloud/README.md)
