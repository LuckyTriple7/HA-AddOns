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

## Lizenzen

Die Dateien dieses Repositories — Manifeste, Dockerfiles, Entrypoints, Übersetzungen, Symbole und Dokumentation — stehen unter der [MIT-Lizenz](LICENSE).

Die veröffentlichten Container-Images enthalten darüber hinaus fremde Software, die ihre eigenen Lizenzen behält, teilweise mit Copyleft. Bringt eine App solche Bestandteile mit, liegt in ihrem Verzeichnis eine `LICENSE.md` mit den Einzelheiten — für diese Images gilt dann die Lizenz der enthaltenen Anwendung, nicht die MIT-Lizenz.

## Architektur

| Add-on | amd64 | aarch64 | Linux |
|---|:---:|:---:|:---:|
| Claude Code | ✅ | ✅ | Alpine |
| Playwright Browser | ✅ | ✅ | Debian 12 |
| FileBox | ✅ | ❌ | Debian 12 |
| Firefox DE | ✅ | ❌ | Debian 12 |
| Webtop XFCE | ✅ | ✅ | Debian 12 |
| WhatsApp | ✅ | ✅ | Alpine |
| Telegram | ✅ | ✅ | Alpine |
| Signal | ✅ | ✅ | Debian 12 |
| Messenger Portal | ✅ | ✅ | Alpine |
| MariaDB 2 | ✅ | ✅ | Alpine |
| Collabora Online | ✅ | ❌ | Ubuntu |
| Nextcloud | ✅ | ❌ | Alpine |
| CardBoard | ✅ | ✅ | Alpine |
| HA SysWatch | ✅ | ✅ | Alpine |
| phpMyAdmin MariaDB 2 | ✅ | ✅ | Alpine |
| MediaGrab | ✅ | ✅ | Alpine |
| GitPulse | ✅ | ✅ | Alpine |
| MyPage | ✅ | ✅ | Alpine |
| TUIWatch | ✅ | ✅ | Debian 12 |
| LogPulse | ✅ | ✅ | Debian 12 |
| NPMplus | ✅ | ✅ | Alpine |

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

### [Messenger Portal](messenger-portal/)

Zentrale, passwortgeschützte Startseite für WhatsApp, Telegram und Signal — alle Messenger auf einen Blick.

- Übersicht aller Messenger mit Online-/Offline-Status und letzter Nachricht
- Neue-Nachricht-Badge mit pulsierendem Farbrand
- Messenger öffnen direkt im Portal (nginx-Proxy — externe Ports nicht nötig)
- PWA — als App auf Android/iOS installierbar

→ [Dokumentation & Changelog](messenger-portal/README.md)

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

### [CardBoard](cardboard/)

Jinja2-Templates mit HA-Sensordaten als gerenderte Markdown-Karten im Browser — Multi-User-Dashboard direkt in Home Assistant.

- Jinja2-Templates werden via HA `/api/template` gerendert und als Markdown-Karten angezeigt
- Multi-User-Unterstützung mit Login-System, Passwortänderung und Admin-Panel
- Admin-Panel: Benutzerverwaltung, Template-Editor mit Live-Vorschau, Login-Verlauf
- PWA — als App auf Android/iOS installierbar (Vollbildmodus, kein Browser-Tab)
- Dark/Light-Mode, mehrsprachig (DE/EN), responsives Design

→ [Dokumentation & Changelog](cardboard/README.md)

### [HA SysWatch](syswatch/)

Docker-Container-Ressourcenmonitor — CPU, RAM, Netzwerk, Disk I/O für alle Container in einer PWA-fähigen Web-UI.

- Sortierbare Tabelle mit CPU %, RAM %, NET I/O, DISK I/O, PIDs (Sortierung gespeichert)
- CPU-Sparkline-Verlauf pro Container (letzte 30 Messungen)
- System-Karten: Host-CPU %, RAM %, CPU-Takt aus `/proc`
- Aktionen: **Start, Stop, Neustart, Kill** — alle mit Passwortbestätigung
- Gestoppte HA Add-ons via Supervisor API (HA entfernt deren Docker-Container)
- Port-Übersicht als Modal mit Suche und sortierbaren Spalten
- Auto-Refresh (Browser passt Interval automatisch an Backend-Zyklus an)
- Idle-Modus bei inaktivem Browser (minimale Systemlast)
- Passwortschutz mit Brute-Force-Sperre, Light/Dark Mode, PWA, DE/EN

→ [Dokumentation & Changelog](syswatch/README.md)

### [phpMyAdmin MariaDB 2](phpmyadmin-mariadb2/)

phpMyAdmin als Web-UI für die **MariaDB 2**-Instanz — Datenbanken und Tabellen direkt im Browser verwalten.

- Vorkonfiguriert für MariaDB 2 (Port 3307)
- Kein separates Login nötig — Zugangsdaten aus den App-Optionen
- Volles phpMyAdmin-Funktionsset: SQL-Editor, Import/Export, Tabellenstruktur

→ [Dokumentation & Changelog](phpmyadmin-mariadb2/README.md)

### [MediaGrab](mediagrab/)

yt-dlp Web-GUI — Videos und Audio von YouTube, TikTok, Instagram, Vimeo, SoundCloud und hunderten weiteren Seiten herunterladen.

- Format-Auswahl: Bestes Video (MP4), 1080p/720p/480p/360p, Audio (MP3/M4A)
- Batch-Download: mehrere URLs gleichzeitig (eine pro Zeile)
- Live-Fortschrittsanzeige mit Geschwindigkeit und ETA
- Datei-Browser mit Inline-Player, Download und Löschen
- Cookies-Support für private und altersgeschützte Videos
- Web Share Target: URL direkt vom Handy-Teilen-Menü senden
- Passwortschutz mit Brute-Force-Sperre, Dark/Light Mode, DE/EN, PWA
- REST-API für HA-Sensoren (`/api/status`)

→ [Dokumentation & Changelog](mediagrab/README.md)

### [GitPulse](gitpulse/)

GitHub Control Panel direkt in Home Assistant — PRs, Issues, CI-Status, Security-Alerts und Release-Tracker auf einen Blick.

- Pull Requests und Issues aller eigenen Repos übersichten, kommentieren und mergen
- CI / GitHub Actions: Status-Übersicht, Workflow starten/stoppen, Favoriten
- Security-Alerts: Dependabot, CodeQL, Secret Scanning mit Autofix-Integration
- Release-Tracker: neue Versionen von eigenen und beobachteten Repos mit Badge
- Add-on Manager: Versions-Bump (+Major/+Minor/+Patch/+Dep) und Changelog direkt in der UI
- Branch-Sync Kachel: zeigt ↑/↓ Commits zwischen Dev- und Main-Branch je Repo
- Cherry-Pick: Commits zwischen Branches auswählen und PR erstellen
- Telegram & E-Mail Benachrichtigungen für PRs, Issues, Workflows, Releases
- Passwortschutz, PWA, Dark/Light Mode, DE/EN

→ [Dokumentation & Changelog](gitpulse/README.md)

### [MyPage](mypage/)

Homepage-Baukasten direkt in Home Assistant — eigene Webseite ohne Design-Kenntnisse, vom Portfolio bis zur Vereins- oder Dienstleisterseite.

- Inhaltsbereiche: Projekte (GitHub-Import), Blog, Leistungen, Referenzen, Team, Fotoalben, Skills, Werdegang, FAQ, Veranstaltungen, Standort — per Drag & Drop sortier- und ausblendbar
- Zweisprachig (DE/EN) mit optionaler Auto-Übersetzung, Hell/Dunkel, eigene Schriftarten & CSS
- Besucherstatistik (Länder, Browser, Referrer), Kontaktformular mit Spam-Schutz, RSS, PWA, SEO
- Mitglieder-Bereich mit Datei-Sharing (optional SMB), Termin-/Buchungs-Button, Unterstützen-Button
- Bibliothek für Markdown-Dokumente mit PDF-Erzeugung und optionalem **KI-Titelbild** (Google Gemini)
- Backup & statischer Export, Home-Assistant-Sensoren

→ [Dokumentation & Changelog](mypage/README.md)

### [TUIWatch](tuiwatch/)

Reisepreis-Tracker für TUI-Pauschalreisen — verfolgt den Preis konkreter Angebote über die Zeit und meldet, wenn er fällt oder steigt. **Nur auf Deutsch verfügbar.**

- Beliebig viele TUI-Angebote per URL verfolgen; Preisverlauf als Diagramm (mit Wunschpreis-Linie)
- Liest Preis, Flüge, Verpflegung, Sterne & HolidayCheck-Bewertung, Ort und Hotel-PDF direkt aus den TUI-JSON-APIs (Headless-Browser nur als Fallback)
- Wunschpreis, Pro-Person-Vergleich (1↔2), Preiskalender als Heatmap (klickbar → Termin auf tui.com)
- Benachrichtigungen (HA + Telegram): Preisänderung, Wunschpreis erreicht, günstigerer Termin, ausverkauft
- E-Mail-Versand aller Angebote, Backup/Wiederherstellen, CSV-Export, HA-Sensoren, PWA

→ [Dokumentation & Changelog](tuiwatch/README.md)

### [LogPulse](logpulse/)

Zentrale, durchsuchbare Log-Historie aus journald — Home Assistant Core, Supervisor und alle Add-on-Container auf einen Blick.

- Liest `/var/log/journal` direkt (kein `full_access`/`docker_api` nötig), persistiert alle Einträge dauerhaft in SQLite
- Volltextsuche, Level-Filter (DEBUG/INFO/WARNING/ERROR/CRITICAL), Quellen-Filter (HA Core/Supervisor/Add-ons/System)
- Erkennt echtes Log-Level auch bei Docker-Containern, die alles als stdout/stderr loggen
- Gespeicherte Filter-Presets, Konsole-Tab für App-Eigendiagnose
- Automatische Aufräumung (Aufbewahrungsdauer + Größenlimit), Passwortschutz, PWA, Dark/Light Mode, DE/EN

→ [Dokumentation & Changelog](logpulse/README.md)

### [NPMplus](npmplus/)

Reverse Proxy mit Weboberfläche auf Basis von [NPMplus](https://github.com/ZoeyVid/NPMplus), dem aktiv gepflegten Fork von NGINX Proxy Manager.

- HTTP/3 (QUIC), eigener nginx-Build mit aws-lc, gehärtetes TLS (ML-KEM, Encrypted Client Hello)
- Let's Encrypt inklusive automatischer Erneuerung, weitere ACME-Server über `extra_env`
- CrowdSec-Bouncer und AppSec/WAF direkt aus den Add-on-Optionen konfigurierbar
- Access-Listen pro Host und Location, mTLS, GoAccess-Statistik in der Oberfläche
- Logs wahlweise nach `/share/npmplus/logs` und/oder ins Add-on-Protokoll — passend zu beiden CrowdSec-Acquisition-Varianten

→ [Dokumentation & Changelog](npmplus/README.md)

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

## Architecture

| Add-on | amd64 | aarch64 | Linux |
|---|:---:|:---:|:---:|
| Claude Code | ✅ | ✅ | Alpine |
| Playwright Browser | ✅ | ✅ | Debian 12 |
| FileBox | ✅ | ❌ | Debian 12 |
| Firefox DE | ✅ | ❌ | Debian 12 |
| Webtop XFCE | ✅ | ✅ | Debian 12 |
| WhatsApp | ✅ | ✅ | Alpine |
| Telegram | ✅ | ✅ | Alpine |
| Signal | ✅ | ✅ | Debian 12 |
| Messenger Portal | ✅ | ✅ | Alpine |
| MariaDB 2 | ✅ | ✅ | Alpine |
| Collabora Online | ✅ | ❌ | Ubuntu |
| Nextcloud | ✅ | ❌ | Alpine |
| CardBoard | ✅ | ✅ | Alpine |
| HA SysWatch | ✅ | ✅ | Alpine |
| phpMyAdmin MariaDB 2 | ✅ | ✅ | Alpine |
| MediaGrab | ✅ | ✅ | Alpine |
| GitPulse | ✅ | ✅ | Alpine |
| MyPage | ✅ | ✅ | Alpine |
| TUIWatch | ✅ | ✅ | Debian 12 |
| LogPulse | ✅ | ✅ | Debian 12 |
| NPMplus | ✅ | ✅ | Alpine |

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

### [Messenger Portal](messenger-portal/)

Central, password-protected start page for WhatsApp, Telegram and Signal — all messengers at a glance.

- Overview of all messengers with online/offline status and latest message
- New message badge with pulsing color border
- Messengers open directly in the portal (nginx proxy — no external ports needed)
- PWA — installable as an app on Android/iOS

→ [Documentation & Changelog](messenger-portal/README.md)

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

### [CardBoard](cardboard/)

Jinja2 templates with HA sensor data rendered as Markdown cards in the browser — multi-user dashboard directly in Home Assistant.

- Jinja2 templates rendered via HA `/api/template` and displayed as Markdown cards
- Multi-user support with login system, password change, and admin panel
- Admin panel: user management, template editor with live preview, login history
- PWA — installable as an app on Android/iOS (fullscreen mode, no browser tab)
- Dark/light mode, multilingual (DE/EN), responsive design

→ [Documentation & Changelog](cardboard/README.md)

### [HA SysWatch](syswatch/)

Docker container resource monitor — CPU, RAM, Network, Disk I/O for all containers in a PWA-ready web UI.

- Sortable table with CPU %, RAM %, NET I/O, DISK I/O, PIDs (sort state persisted)
- CPU sparkline history per container (last 30 measurements)
- System cards: host CPU %, RAM %, CPU clock from `/proc`
- Actions: **Start, Stop, Restart, Kill** — all with password confirmation
- Stopped HA add-ons via Supervisor API (HA removes their Docker containers)
- Port overview modal with search and sortable columns
- Auto-refresh (browser interval calibrates automatically to the backend cycle)
- Idle mode when no browser is active (minimal system load)
- Password protection with brute-force lockout, Light/Dark mode, PWA, DE/EN

→ [Documentation & Changelog](syswatch/README.md)

### [phpMyAdmin MariaDB 2](phpmyadmin-mariadb2/)

phpMyAdmin as a web UI for the **MariaDB 2** instance — manage databases and tables directly in the browser.

- Pre-configured for MariaDB 2 (port 3307)
- No separate login required — credentials from app options
- Full phpMyAdmin feature set: SQL editor, import/export, table structure

→ [Documentation & Changelog](phpmyadmin-mariadb2/README.md)

### [MediaGrab](mediagrab/)

yt-dlp web GUI — download videos and audio from YouTube, TikTok, Instagram, Vimeo, SoundCloud and hundreds of other sites.

- Format selection: Best Video (MP4), 1080p/720p/480p/360p, Audio (MP3/M4A)
- Batch download: multiple URLs at once (one per line)
- Live progress with speed and ETA
- File browser with inline player, download and delete
- Cookie support for private and age-restricted videos
- Web Share Target: share URL directly from your phone's share sheet
- Password protection with brute-force lockout, Dark/Light mode, DE/EN, PWA
- REST API for HA sensors (`/api/status`)

→ [Documentation & Changelog](mediagrab/README.md)

### [GitPulse](gitpulse/)

GitHub Control Panel directly in Home Assistant — PRs, Issues, CI status, security alerts and release tracker at a glance.

- Overview of pull requests and issues across all your repos — comment and merge directly in the UI
- CI / GitHub Actions: status overview, trigger/stop workflows, favorites
- Security alerts: Dependabot, CodeQL, Secret Scanning with autofix integration
- Release tracker: new versions of your own and watched repos with badge indicator
- Add-on Manager: version bump (+Major/+Minor/+Patch/+Dep) and changelog entry directly in the UI
- Branch-Sync tile: shows ↑/↓ commits between dev and main branch per repo
- Cherry-Pick: select commits between branches and create a PR
- Telegram & e-mail notifications for PRs, issues, workflows and releases
- Password protection, PWA, Dark/Light mode, DE/EN

→ [Documentation & Changelog](gitpulse/README.md)

### [MyPage](mypage/)

Homepage builder directly in Home Assistant — your own website without design skills, from a portfolio to a club or service-provider page.

- Content sections: projects (GitHub import), blog, services, testimonials, team, photo albums, skills, timeline, FAQ, events, location — reorder and hide via drag & drop
- Bilingual (DE/EN) with optional auto-translation, light/dark, custom fonts & CSS
- Visitor stats (countries, browsers, referrers), contact form with spam protection, RSS, PWA, SEO
- Members area with file sharing (optional SMB), appointment/booking button, support button
- Library for Markdown documents with PDF generation and an optional **AI cover image** (Google Gemini)
- Backup & static export, Home Assistant sensors

→ [Documentation & Changelog](mypage/README.md)

### [TUIWatch](tuiwatch/)

Travel price tracker for TUI package holidays — tracks the price of specific offers over time and alerts you when it drops or rises. **German UI only.**

- Track any number of TUI offers by URL; price history chart (with target-price line)
- Reads price, flights, board, stars & HolidayCheck rating, location and hotel PDF straight from TUI's JSON APIs (headless browser only as fallback)
- Target price, per-person comparison (1↔2), price calendar as a heatmap (clickable → opens the date on tui.com)
- Notifications (HA + Telegram): price change, target reached, cheaper date, sold out
- E-mail dispatch of all offers, backup/restore, CSV export, HA sensors, PWA

→ [Documentation & Changelog](tuiwatch/README.md)

### [LogPulse](logpulse/)

Centralized, searchable log history from journald — Home Assistant Core, Supervisor and all add-on containers at a glance.

- Reads `/var/log/journal` directly (no `full_access`/`docker_api` needed), persists all entries permanently in SQLite
- Full-text search, level filter (DEBUG/INFO/WARNING/ERROR/CRITICAL), source filter (HA Core/Supervisor/Add-ons/System)
- Detects the real log level even for Docker containers that log everything as stdout/stderr
- Saved filter presets, console tab for the app's own diagnostics
- Automatic cleanup (retention period + size cap), password protection, PWA, dark/light mode, DE/EN

→ [Documentation & Changelog](logpulse/README.md)

### [NPMplus](npmplus/)

Reverse proxy with a web interface, based on [NPMplus](https://github.com/ZoeyVid/NPMplus), the actively maintained fork of NGINX Proxy Manager.

- HTTP/3 (QUIC), custom nginx build with aws-lc, hardened TLS (ML-KEM, Encrypted Client Hello)
- Let's Encrypt including automatic renewal, other ACME servers via `extra_env`
- CrowdSec bouncer and AppSec/WAF configurable straight from the add-on options
- Access lists per host and location, mTLS, GoAccess statistics inside the interface
- Logs to `/share/npmplus/logs` and/or the add-on log — matching both CrowdSec acquisition styles

→ [Documentation & Changelog](npmplus/README.en.md)
