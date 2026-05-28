# Changelog

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
