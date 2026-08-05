# Changelog

## [1.0.10.5] - 2026-08-05

chore(deps): bump fastapi from 0.140.0 to 0.141.1 in /cardboard/rootfs/app
chore(deps): bump uvicorn from 0.51.0 to 0.52.0 in /cardboard/rootfs/app


## [1.0.10.4] - 2026-07-27

chore(deps): bump fastapi from 0.139.2 to 0.140.0 in /cardboard/rootfs/app


## [1.0.10.3] - 2026-07-13

chore(deps): bump uvicorn from 0.49.0 to 0.51.0 in /cardboard/rootfs/app


## [1.0.10.2] - 2026-07-09

### Fixed
- Add-on beendete sich bei jedem Stop/Update mit Exit-Code 137 (SIGKILL statt
  sauberem Stop): `Dockerfile` basiert auf `python:3.14-alpine` ohne eigenes
  Init-System, `run.sh` macht den Python-Prozess per `exec` zu PID 1 — ohne
  eigenen Signal-Handler ignoriert der Kernel bei PID 1 unbehandelte Signale wie
  SIGTERM (Linux-Sonderfall), der Supervisor musste nach Timeout hart killen.
  `init: false` → `init: true` in `config.yaml` allein hätte nicht gereicht
  (Supervisor stellt dann zwar ein Mini-Init als echte PID 1, das Signale korrekt
  durchreicht, aber Python selbst hatte weiterhin keinen eigenen SIGTERM-Handler
  → Default-Handler killt den Prozess mit exit 143). Eigener `SIGTERM`-Handler
  ergänzt (`os._exit(0)` — der Server läuft rein async ohne eigene Threads,
  DB-Zugriffe committen bereits pro Verbindung, kein Cleanup nötig).

## [1.0.10.1] - 2026-06-29

chore(deps): bump fastapi from 0.138.0 to 0.138.1 in /cardboard/rootfs/app


## [1.0.10] - 2026-06-23

- Admin-Panel über HA-Ingress ohne Passwort: Da Home Assistant beim Ingress-Zugriff bereits authentifiziert, entfällt die Passwort-Abfrage (wie MyPage). Das gesetzte `admin_password` schützt weiterhin den direkten LAN-Zugriff auf Port 17773. Der Ingress-Port 17774 ist nicht im LAN gemappt → `x-ingress-path` kann nicht von außen gefälscht werden
- Logout-Button im Admin-Panel wird über Ingress ausgeblendet


## [1.0.9] - 2026-06-23

- HA-Zugriff ohne manuellen Token: `homeassistant_api: true` ergänzt, alle HA-API-Aufrufe (`/api/template`, `/api/config`, `/api/states`, `persistent_notification`) laufen jetzt über den Supervisor-Proxy `http://supervisor/core/api` mit dem automatisch bereitgestellten `SUPERVISOR_TOKEN` — wie MyPage. Der Supervisor-Token hat die für `/api/template` nötigen Admin-Rechte
- Optionen `ha_token` und `ha_url` entfernt
- Session-Signing-Secret nicht mehr aus `ha_token` abgeleitet, sondern als zufälliges Secret in `/config/addons_config/cardboard/.session_secret` persistiert (überlebt Neustarts)


## [1.0.8.4] - 2026-06-22

build(deps): Bump fastapi from 0.137.0 to 0.138.0 in /cardboard/rootfs/app


## [1.0.8.3] - 2026-06-09

chore(deps): Bump pyyaml from 6.0.1 to 6.0.3 in /cardboard/rootfs/app
chore(deps): Bump httpx from 0.27.0 to 0.28.1 in /cardboard/rootfs/app
chore(deps): Bump python-multipart from 0.0.27 to 0.0.32 in /cardboard/rootfs/app
chore(deps): Bump fastapi from 0.111.0 to 0.136.3 in /cardboard/rootfs/app


## [1.0.8.2] - 2026-06-09

chore(deps): Bump uvicorn from 0.30.1 to 0.49.0 in /cardboard/rootfs/app
chore(deps): Bump python from 3.11-alpine to 3.14-alpine in /cardboard
chore(deps): Bump python-multipart from 0.0.9 to 0.0.27 in /cardboard/rootfs/app


## [1.0.8.1] - 2026-06-08

### Dependencies
- Dependabot: Abhaengigkeiten aktualisiert

## [1.0.8] - 2026-06-08

### Security
- Information Exposure: Exception-Details (`str(e)`) nicht mehr in HTTP-Responses zurückgegeben; stattdessen generische Fehlermeldung + internes `log.exception()` (CodeQL #22–#25)

## [1.0.7] - 2026-06-07

### Security
- Path Traversal: `safe_child()` verwendet `m.group(0)` aus Regex-Match statt Rohwert — Taint-Chain für CodeQL korrekt unterbrochen (py/path-injection #117, #118)
- Path Traversal: Admin-Funktionen rufen `safe_child(CONFIG_DIR, username, ...)` statt `safe_child(CONFIG_DIR / username, ...)` — `username` durchläuft jetzt die Regex-Validierung in `safe_child` (#65–#71)
- Schwaches Hashing: PBKDF2-HMAC-SHA256 (260.000 Iterationen, Random-Salt) für alle neuen Passwörter; Legacy-SHA256-Verifikation bleibt für bestehende Hashes erhalten (py/weak-sensitive-data-hashing #2, #3, #4)

---

## [1.0.6] - 2026-06-07
### Security
- `safe_child()` überarbeitet: Regex-Validierung (`^[a-zA-Z0-9_\-][a-zA-Z0-9._\-]{0,254}$`) jedes Pfadsegments vor dem Zusammenbauen — CodeQL erkennt Regex als Sanitizer und kann den Taint-Flow in `joinpath().resolve()` korrekt bewerten (py/path-injection)

---

## [1.0.5] - 2026-06-07
### Security
- Path-Traversal-Schwachstelle behoben: `safe_child()` prüft jetzt explizit auf absolute Pfade und `..`-Segmente **vor** dem `resolve()`-Aufruf — CodeQL-anerkanntes Sanitizer-Pattern (CodeQL: py/path-injection)
- `shutil.rmtree` und `user_dir.mkdir` in Admin-Endpunkten verwenden jetzt `safe_child()` statt direkter Pfadkonstruktion

---

## [1.0.4] - 2026-06-07
### Added
- Disconnect-Erkennung: `visibilitychange` (Tab/Laptop-Aufklappen), `online`/`offline`-Events, `navigator.onLine`-Check beim Start
- Offline-Banner: abdunkelndes Overlay mit animiertem 📡, lokalisierten Texten (DE/EN) und „Neu laden"-Button

## [1.0.3] - 2026-06-04
- fix: Log-Zeitstempel vollständig in allen Ausgaben (force=True / UVICORN_LOG_CONFIG)

## [1.0.2] - 2026-06-04
- Log-Ausgaben mit Datum und Uhrzeit: `[INFO] [YYYY-MM-DD HH:MM:SS] Nachricht`

## 1.0.1
- Translations DE/EN für alle Optionen ergänzt (Anzeigenamen und Beschreibungen in der HA Add-on UI)

## 1.0.0
- Erste stabile Produktivversion

## 0.0.41
- Admin-Panel: Login-Verlauf-Modal breiter (780px statt 560px)

## 0.0.40
- run.sh: `admin_password` wird im Startlog ebenfalls als `***` maskiert (war bisher Klartext)

## 0.0.39
- Login-Verlauf: Browser und OS werden jetzt gespeichert und angezeigt (z.B. „Chrome 124 · Windows")
- DB-Migration: Spalte `user_agent` wird automatisch zur bestehenden Datenbank hinzugefügt
- User-Agent-Parser (pure Python, keine externe Bibliothek): erkennt Chrome, Firefox, Safari, Edge, Opera + Windows, macOS, Linux, Android, iPhone, iPad

## 0.0.38
- Neue Option `cards_per_row` (1–6, Standard: 3) — steuert wie viele Karten nebeneinander erscheinen
- View-Seite: Layout auf CSS Grid umgestellt (war Flexbox)
- Mobile (≤800px): immer eine Karte pro Zeile, unabhängig von `cards_per_row`

## 0.0.37
- Admin-Panel: Neue Sektion „Verwaiste Verzeichnisse" — zeigt Ordner die keinem Benutzer mehr gehören
- Admin-Panel: Einzeln oder alle verwaisten Verzeichnisse per Klick bereinigen (mit Bestätigungsdialog)
- API: `GET /admin/api/orphaned` und `POST /admin/api/orphaned/cleanup` (beide Apps + Ingress)

## 0.0.36
- View-Seite: Footer auf Mobile einzeilig gestapelt (kein unabhängiges Umbrechen beider Seiten)
- View-Seite: Auto-Reconnect via Page Visibility API — sofortiger Refresh wenn App wieder in den Vordergrund kommt

## 0.0.35
- View-Seite: Karten auf Mobile jetzt einheitlich gleich breit (align-items: stretch)

## 0.0.34
- View-Seite: Abmelden-Icon als SVG (war ⏻ Unicode — kein Rendering auf Android)
- View-Seite: 📋-Logo neben „CardBoard" auf Mobile (≤600px) ausgeblendet

## 0.0.33
- View-Seite: Uhrzeit wird bei schmalen Bildschirmen (≤600px) ausgeblendet
- View-Seite: „Abmelden"-Schaltfläche zeigt auf mobilen Geräten nur das ⏻-Symbol
- PWA: Eigene Icons (icon-192.png, icon-512.png) werden direkt gebündelt statt generiert

## 0.0.32
- Login-Seite: Hinweis "Sitzung abgelaufen" wenn Session durch Timeout beendet wurde (grünes Info-Banner statt roter Fehler)
- View-Seite: Redirect bei 401 verwendet `?reason=expired` statt `?error=1`

## 0.0.31
- PWA (Progressive Web App): CardBoard kann auf Android/iOS als App installiert werden
- `manifest.json` mit App-Name, Icons und Vollbild-Modus (`standalone`)
- Service Worker (`sw.js`): ermöglicht Install-Prompt, kein Caching von HA-Daten
- Icons (192×192, 512×512): werden beim ersten Start automatisch generiert (pure Python)
- Theme-Color der Statusleiste wechselt mit Dark/Light-Mode
- iOS: "Teilen → Zum Homebildschirm" funktioniert sofort
- Android/Chrome: Install-Banner erscheint automatisch (setzt HTTPS voraus)

## 0.0.30
- Rate Limiting: Lokale/private IPs (LAN) sind von der Sperre ausgenommen — kein versehentliches Aussperren von Admins
- Admin-Panel: Neue Sektion "Gesperrte IPs" zeigt aktuell gesperrte IPs mit verbleibender Sperrzeit und Versuchen
- Admin-Panel: "Entsperren"-Button pro IP hebt die Rate-Limit-Sperre sofort auf
- Neue API-Endpunkte: `GET /admin/api/rate-limits` und `POST /admin/api/rate-limits/unblock`

## 0.0.29
- Rate Limiting: IP wird nach 5 fehlgeschlagenen Logins innerhalb von 10 Minuten für 15 Minuten gesperrt
- Login-Seite zeigt eigene Meldung bei gesperrter IP (`?error=locked`)
- Admin-Login-Seite: Dark/Light-Mode Toggle + Sprach-Toggle (🇩🇪/🇬🇧)
- Template-Editor: Ctrl+S speichert das aktuelle Template
- Template-Liste: ↑/↓-Buttons zum Umsortieren der Karten-Reihenfolge
- Template-Liste: Warnung wenn mehr als 3 Templates vorhanden (nur erste 3 werden angezeigt)
- Admin-Panel: 📊-Button pro Benutzer öffnet Login-Verlauf (Modal, letzte 50 Ereignisse)
- View-Seite: Auto-Reconnect bei Verbindungsfehler (stiller Wiederverbindungsindikator)
- Neue Option `max_cards` (int, Default: 3) — konfigurierbare maximale Kartenanzahl pro Benutzer

## 0.0.28
- Admin-Panel: Sprach-Toggle (🇩🇪 DE / 🇬🇧 EN) im Header — Einstellung wird in localStorage gespeichert

## 0.0.27
- Template-Editor: Live-Vorschau (Toggle-Button, automatische Aktualisierung 600ms nach Eingabe)
- Vorschau rendert das Template über die HA-API und zeigt die Karte im selben Look wie die View-Seite

## 0.0.26
- Admin-Panel: Template-Editor (neue Seite /admin/templates/{username})
- Templates anlegen, bearbeiten und löschen direkt im Browser
- Split-Layout: Templateliste links, Editor rechts
- Titel pro Template einstellbar
- Fehlende Template-Dateien werden in der Liste markiert
- 📝-Button in der Benutzertabelle öffnet den Template-Editor

## 0.0.25
- Admin-Panel: Footer zeigt zusätzlich die Anzahl fehlgeschlagener Logins der letzten 24h

## 0.0.24
- Bugfix: Logout, Login-Fehler und Panel-Redirect im Ingress verwenden relative URLs (kein 404 mehr nach Abmelden)

## 0.0.23
- Admin-Panel: Uhr im Header (live, Sekundenanzeige)
- Admin-Panel: Header-Buttons (Reload, Theme, Abmelden) einheitlich wie in der View-Seite

## 0.0.22
- Admin-Panel: Footer mit letztem erfolgreichen und fehlgeschlagenen Login (Benutzer, Zeitstempel, IP)

## 0.0.21
- Admin-Panel: Letzter Login (Zeitstempel + IP) pro Benutzer in der Übersicht
- Admin-Panel: Reload-Button mit Dreh-Animation
- Admin-Panel: Dark/Light-Mode Toggle (teilt Theme-Einstellung mit der View-Seite)
- Admin-Panel: i18n DE/EN (Browsersprache)
- Bugfix: Edit-Button im Admin-Panel funktioniert jetzt korrekt
- Bugfix: Ingress-Redirect und Root-Redirect auf Port 17773

## 0.0.20
- Admin-Panel: Benutzerverwaltung (anlegen, bearbeiten, löschen, Passwort zurücksetzen)
- Admin-Panel über HA Ingress erreichbar (Sidebar) und direkt auf Port 17773 (/admin/)
- Option `admin_password` (optional) — schützt das Admin-Panel mit Passwort
- Beim Anlegen eines Benutzers wird das Benutzerverzeichnis automatisch erstellt
- `force_pw_change: true` wird beim Anlegen und bei Passwort-Reset automatisch gesetzt
- Dritter uvicorn-Server auf Port 17774 für HA Ingress

## 0.0.19
- Doku: REST-Sensor für letzten erfolgreichen Login (username, Zeitstempel, IP)
- Doku: REST-Sensor für letzten fehlgeschlagenen Login um Username ergänzt

## 0.0.18
- Doku: localhost:17773 durch homeassistant.local:17773 ersetzt (HA läuft in eigenem Docker-Container)
- Erklärung warum localhost nicht funktioniert und welche Adresse stattdessen zu verwenden ist

## 0.0.17
- Footer-Schrift im Dark Mode heller (#9ca3af)

## 0.0.16
- nginx Reverse-Proxy Dokumentation (DE + EN) mit Beispielkonfiguration
- Footer-Schrift im Light Mode dunkler (#6b7280)

## 0.0.15
- Initiales Passwort ändern: `force_pw_change: true` in users.yaml erzwingt Passwortänderung beim ersten Login
- /view gesperrt solange Flag gesetzt — direkter Zugriff leitet zur Passwortänderung um
- Hinweismeldung im Dialog, kein "Zurück"-Link, Weiterleitung nach Erfolg
- force_pw_change wird nach Änderung automatisch aus users.yaml entfernt

## 0.0.14
- Option `pw_min_length` (int, Default: 8) — Mindestlänge für neue Passwörter
- Option `pw_require_special` (bool, Default: true) — Zahl oder Sonderzeichen erforderlich
- Passwort-Anforderungen werden im Ändern-Dialog unterhalb des Feldes angezeigt
- Validierung client- und serverseitig

## 0.0.13
- client_ip() liest X-Forwarded-For Header aus — echte Client-IP statt Docker-Netzwerk-IP hinter nginx

## 0.0.12
- Login erfolgreich im Log: user, IP (INFO)
- Login fehlgeschlagen im Log: user, IP (WARNING)
- Logout im Log: user (INFO)
- Admin-API Zugriff verweigert im Log: IP, Pfad (WARNING)
- Passwörter erscheinen in keiner Log-Ausgabe

## 0.0.11
- Passwort-Ändern-Funktion für eingeloggte Benutzer (/change-password)
- Altes Passwort, neues Passwort, Bestätigung — neues Passwort wird als SHA-256 in users.yaml gespeichert
- Fehlermeldungen: falsches Passwort, Passwörter stimmen nicht überein, leeres Passwort
- 🔑-Button im Header der View-Seite, respektiert Dark/Light-Mode und Sprache

## 0.0.10
- Persistente HA-Benachrichtigung bei fehlgeschlagenem Login (Benutzername, IP, Zeitstempel)
- Option `notify_failed_login` (bool, Default: `true`) zum Ein-/Ausschalten
- Benachrichtigung wird asynchron gesendet — kein Einfluss auf Login-Geschwindigkeit
- Verwendet den vorhandenen `ha_token` und `ha_url` — kein separater Token nötig

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
