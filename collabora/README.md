# Collabora Online

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Commits](https://img.shields.io/github/commit-activity/t/LuckyTriple7/HA-AddOns?style=flat-square&label=commits)
![Last Commit](https://img.shields.io/github/last-commit/LuckyTriple7/HA-AddOns?path=collabora&style=flat-square)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

Collabora Online Office-Server für Nextcloud — bearbeite `.docx`, `.xlsx`, `.pptx` und ODF-Dateien direkt im Browser, ohne Download.

## Zugriff

| Dienst | URL |
|--------|-----|
| Collabora Online | `https://<HA-IP>:9980` |
| Admin-Panel | `https://<HA-IP>:9980/browser/dist/admin/admin.html` |
| Web-Terminal | HA-Seitenleiste → „Collabora Terminal" oder direkt `http://<HA-IP>:7682` |

## Funktionen

- **Collabora Online**: Vollständiger Office-Server auf Basis des offiziellen `collabora/code`-Images
- **Nextcloud-Integration**: Dokumente direkt in Nextcloud öffnen und bearbeiten
- **Domain-Beschränkung**: Nur deine Nextcloud-Instanz darf den Server nutzen
- **Persistente Konfiguration**: `coolwsd.xml` wird in `/config` gespeichert und überlebt Rebuilds
- **Admin-Panel**: Zugangsdaten werden coolwsd per `--use-env-vars` übergeben
- **Web-Terminal**: coolwsd-Konfiguration direkt im Browser einsehbar (HA Ingress)

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `nextcloud_url` | — | URL deiner Nextcloud-Instanz (z.B. `https://192.168.178.100:7443`) |
| `admin_user` | `admin` | Benutzername für das Collabora-Admin-Panel |
| `admin_password` | — | Passwort für das Collabora-Admin-Panel |
| `aliasgroup1` | — | Erlaubte Domain als Regex — überschreibt die automatische Erkennung aus `nextcloud_url` |
| `domain1` | — | Externer Hostname des Collabora-Servers — nur für Reverse-Proxy-Setups |
| `extra_params` | — | Zusätzliche coolwsd-Parameter |

## Einrichtung

1. Add-on konfigurieren: `nextcloud_url` und `admin_password` setzen
2. Add-on starten
3. In Nextcloud: **Apps → Office & Text → Nextcloud Office** installieren
4. **Einstellungen → Verwaltung → Nextcloud Office → Eigenen Server verwenden**
5. URL eintragen: `https://<HA-IP>:9980` — grüner Haken bestätigt die Verbindung
6. WOPI-Allowlist im Nextcloud-Terminal setzen:
   ```sh
   ALLOW_ROOT=1 php /app/www/public/occ config:app:set richdocuments wopi_allowlist --value="172.30.0.0/16"
   ```

## Web-Terminal

Über die HA-Seitenleiste erreichbar. Nützliche Befehle:

```sh
# Konfiguration prüfen
cat /config/coolwsd.xml

# Laufende coolwsd-Parameter ansehen
ps aux | grep coolwsd
```

## Hinweise

- Collabora speichert keine Dateien — alle Daten verbleiben in Nextcloud
- SSL ist für lokale Nutzung deaktiviert (HTTP zwischen Nextcloud und Collabora)
- Die Domain-Beschränkung verhindert, dass fremde Nextcloud-Instanzen den Server nutzen
- Reverse-Proxy muss WebSocket-Verbindungen durchleiten

→ [Changelog](CHANGELOG.md)

---

# Collabora Online (English)

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

Collabora Online office server for Nextcloud — edit `.docx`, `.xlsx`, `.pptx` and ODF files directly in the browser, without downloading.

## Access

| Service | URL |
|---------|-----|
| Collabora Online | `https://<HA-IP>:9980` |
| Admin Panel | `https://<HA-IP>:9980/browser/dist/admin/admin.html` |
| Web Terminal | HA sidebar → "Collabora Terminal", or directly at `http://<HA-IP>:7682` |

## Features

- **Collabora Online**: Full office server based on the official `collabora/code` image
- **Nextcloud integration**: Open and edit documents directly in Nextcloud
- **Domain restriction**: Only your Nextcloud instance can use the server
- **Persistent configuration**: `coolwsd.xml` is stored in `/config` and survives rebuilds
- **Admin panel**: Credentials are handed to coolwsd via `--use-env-vars`
- **Web terminal**: Inspect coolwsd configuration directly in the browser (HA Ingress)

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `nextcloud_url` | — | URL of your Nextcloud instance (e.g. `https://192.168.178.100:7443`) |
| `admin_user` | `admin` | Username for the Collabora admin panel |
| `admin_password` | — | Password for the Collabora admin panel |
| `aliasgroup1` | — | Allowed domain as regex — overrides automatic detection from `nextcloud_url` |
| `domain1` | — | External hostname of the Collabora server — only needed for reverse proxy setups |
| `extra_params` | — | Additional coolwsd parameters |

## Setup

1. Configure the add-on: set `nextcloud_url` and `admin_password`
2. Start the add-on
3. In Nextcloud: **Apps → Office & Text → Nextcloud Office** install
4. **Settings → Administration → Nextcloud Office → Use your own server**
5. Enter URL: `https://<HA-IP>:9980` — green checkmark confirms the connection
6. Set the WOPI allowlist in the Nextcloud Terminal:
   ```sh
   ALLOW_ROOT=1 php /app/www/public/occ config:app:set richdocuments wopi_allowlist --value="172.30.0.0/16"
   ```

## Web Terminal

Accessible via the HA sidebar. Useful commands:

```sh
# Check configuration
cat /config/coolwsd.xml

# Inspect the running coolwsd parameters
ps aux | grep coolwsd
```

## Notes

- Collabora does not store files — all data stays in Nextcloud
- SSL is disabled for local use (HTTP between Nextcloud and Collabora)
- The domain restriction prevents other Nextcloud instances from using the server
- Reverse proxy must forward WebSocket connections

→ [Changelog](CHANGELOG.md)
