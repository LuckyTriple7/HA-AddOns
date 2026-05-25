# MariaDB 2

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Last Commit](https://img.shields.io/github/last-commit/LuckyTriple7/HA-AddOns?path=mariadb2&style=flat-square)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

Zweite unabhängige MariaDB-Instanz für Home Assistant — läuft parallel zur offiziellen MariaDB-App ohne Konflikte.

## Warum MariaDB 2?

Die offizielle MariaDB-App wird von Home Assistant und anderen Apps (z.B. als Core-Datenbank) genutzt. Um Nextcloud oder andere Dienste **isoliert** auf einer eigenen Datenbankinstanz zu betreiben, ohne die bestehende Datenbank zu berühren, bietet sich MariaDB 2 an.

| | Offizielle MariaDB | MariaDB 2 |
|---|---|---|
| Port (Host) | 3306 | **3307** |
| Daten | `/data/databases/` | `/data/databases/` (eigene App-Partition) |
| Slug | `mariadb` | `mariadb2` |
| Konflikt? | — | **Nein** — vollständig isoliert |

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `databases` | `[nextcloud]` | Liste der anzulegenden Datenbanken |
| `logins` | `[{username: nextcloud, password: ""}]` | Zugangsdaten |
| `rights` | `[{database: nextcloud, username: nextcloud}]` | Berechtigungen (ALL PRIVILEGES) |
| `create_nextcloud_db` | `false` | Nextcloud-Datenbank automatisch anlegen (Zufallspasswort) |

## Nextcloud-Datenbank automatisch anlegen

Option `create_nextcloud_db: true` aktivieren. Beim ersten Start wird:
- Datenbank `nextcloud` angelegt (UTF-8, unicode_ci)
- Benutzer `nextcloud` mit Zufallspasswort erstellt
- Zugangsdaten im Add-on-LOG ausgegeben
- Datei `nextcloud_db_credentials.txt` im Add-on-Konfigurationsordner gespeichert → in HA unter **Einstellungen → System → Speicher → Add-on-Konfigurationsordner** einsehbar

Beim Nextcloud-Webinstaller dann folgende Werte eintragen:
```
Datenbankbenutzer:  nextcloud
Datenbankpasswort:  <aus /data/nextcloud_db_password.txt>
Datenbankname:      nextcloud
Datenbankhost:      <Hostname der MariaDB-2-App>:3306
```

## Verbindungsdetails

| | Wert |
|---|---|
| Host (intern, Add-on zu Add-on) | Hostname aus HA Supervisor |
| Host (extern, vom Host-System) | `<HA-IP>:3307` |
| Port (intern) | `3306` |
| Port (Host) | `3307` |

## Migration: Nextcloud von SQLite auf MariaDB 2

### Vorbereitung

1. **MariaDB 2** installieren, `create_nextcloud_db: true` setzen, starten
2. Passwort aus `addon_config/nextcloud_db_credentials.txt` notieren
3. Im **MariaDB 2 LOG** den Hostname ablesen:
   ```
   [INFO] Hostname (für Nextcloud-Migration): abc123-mariadb2
   ```

### Migration (im Nextcloud Web-Terminal)

```sh
# Alias setzen — erspart den langen Präfix bei jedem Befehl
alias occ='ALLOW_ROOT=1 php /app/www/public/occ'

# 1. Wartungsmodus aktivieren
occ maintenance:mode --on

# 2. Datenbank migrieren (Passwort aus nextcloud_db_credentials.txt)
occ db:convert-type \
  --all-apps \
  --password=PASSWORT_HIER \
  mysql \
  nextcloud \
  HOSTNAME_HIER:3306 \
  nextcloud

# 3. Wartungsmodus deaktivieren
occ maintenance:mode --off
```

> **Hinweis:** Die Migration kann je nach Datenmenge einige Minuten dauern. Danach verwendet Nextcloud MariaDB 2 — die SQLite-Datei bleibt erhalten, wird aber nicht mehr genutzt.

→ [Changelog](CHANGELOG.md)

---

# MariaDB 2 (English)

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

A second independent MariaDB instance for Home Assistant — runs alongside the official MariaDB app without any conflicts.

## Why MariaDB 2?

The official MariaDB app is used by Home Assistant and other apps (e.g. as the core database). To run Nextcloud or other services on their **own isolated database instance** without touching the existing database, MariaDB 2 is the right choice.

| | Official MariaDB | MariaDB 2 |
|---|---|---|
| Port (host) | 3306 | **3307** |
| Data | `/data/databases/` | `/data/databases/` (own app partition) |
| Slug | `mariadb` | `mariadb2` |
| Conflict? | — | **No** — fully isolated |

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `databases` | `[nextcloud]` | List of databases to create |
| `logins` | `[{username: nextcloud, password: ""}]` | Login credentials |
| `rights` | `[{database: nextcloud, username: nextcloud}]` | Permissions (ALL PRIVILEGES) |
| `create_nextcloud_db` | `false` | Auto-create Nextcloud database (random password) |

## Auto-create Nextcloud Database

Enable `create_nextcloud_db: true`. On first start:
- Database `nextcloud` is created (UTF-8, unicode_ci)
- User `nextcloud` is created with a random password
- Credentials shown in the add-on log
- File `nextcloud_db_credentials.txt` saved in the add-on config folder → accessible in HA under **Settings → System → Storage → Add-on config folder**

In the Nextcloud web installer, enter:
```
Database user:     nextcloud
Database password: <from /data/nextcloud_db_password.txt>
Database name:     nextcloud
Database host:     <MariaDB 2 app hostname>:3306
```

## Migration: Nextcloud from SQLite to MariaDB 2

### Preparation

1. Install **MariaDB 2**, set `create_nextcloud_db: true`, start it
2. Note the password from `addon_config/nextcloud_db_credentials.txt`
3. Read the hostname from the **MariaDB 2 log**:
   ```
   [INFO] Hostname (for Nextcloud migration): abc123-mariadb2
   ```

### Migration (in Nextcloud Web Terminal)

```sh
# Set alias — saves typing the long prefix for every command
alias occ='ALLOW_ROOT=1 php /app/www/public/occ'

# 1. Enable maintenance mode
occ maintenance:mode --on

# 2. Convert database (password from nextcloud_db_credentials.txt)
occ db:convert-type \
  --all-apps \
  --password=YOUR_PASSWORD \
  mysql \
  nextcloud \
  YOUR_HOSTNAME:3306 \
  nextcloud

# 3. Disable maintenance mode
occ maintenance:mode --off
```

> **Note:** Migration may take a few minutes depending on data size. After completion, Nextcloud uses MariaDB 2 — the SQLite file is kept but no longer used.

→ [Changelog](CHANGELOG.md)
