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
| `disable_foreign_key_checks` | `false` | FK-Checks deaktivieren — nur für Migration aktivieren, danach wieder auf `false` |

## Nextcloud-Datenbank einrichten

Datenbank, Benutzer und Passwort direkt in den App-Optionen setzen — MariaDB 2 legt alles beim Start automatisch an.

Beim Nextcloud-Webinstaller dann folgende Werte eintragen:
```
Datenbankbenutzer:  nextcloud
Datenbankpasswort:  <wie in den Optionen gesetzt>
Datenbankname:      nextcloud
Datenbankhost:      <Hostname aus MariaDB 2 LOG>:3306
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

1. **MariaDB 2** installieren, Datenbank/Benutzer/Passwort in den Optionen setzen
2. Option `disable_foreign_key_checks: true` setzen — verhindert FK-Fehler während der Migration (s.u.)
3. MariaDB 2 starten, **Hostname aus dem LOG ablesen:**
   ```
   [INFO] Hostname (for Nextcloud migration): abc123-mariadb2
   ```

### Migration (im Nextcloud Web-Terminal)

```sh
alias occ='ALLOW_ROOT=1 php /app/www/public/occ'

# 1. Verwaiste Datenbank-Referenzen in SQLite bereinigen
#    (verhindert FK-Fehler bei Mail-Tabellen)
DATA=$(occ config:system:get datadirectory)
php -r "
\$db = new SQLite3('\$DATA/nextcloud.db');
\$db->exec('UPDATE oc_mail_accounts SET drafts_mailbox_id = NULL WHERE drafts_mailbox_id IS NOT NULL AND drafts_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
\$db->exec('UPDATE oc_mail_accounts SET sent_mailbox_id = NULL WHERE sent_mailbox_id IS NOT NULL AND sent_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
\$db->exec('UPDATE oc_mail_accounts SET trash_mailbox_id = NULL WHERE trash_mailbox_id IS NOT NULL AND trash_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
\$db->exec('UPDATE oc_mail_accounts SET archive_mailbox_id = NULL WHERE archive_mailbox_id IS NOT NULL AND archive_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
echo 'Fertig' . PHP_EOL;
"

# 2. utf8mb4 aktivieren — verhindert Emoji-Fehler bei Kalender-Einträgen
occ config:system:set mysql.utf8mb4 --type boolean --value="true"

# 3. Wartungsmodus aktivieren
occ maintenance:mode --on

# 4. Datenbank migrieren
#    Hostname: aus MariaDB 2 LOG (z.B. c4d39aca-mariadb2)
#    Port:     3306 (interner Container-Port, NICHT 3307)
#    Passwort in EINFACHEN Anführungszeichen — Sonderzeichen wie & $ @ sonst Shell-Fehler
occ db:convert-type \
  --all-apps \
  --password='PASSWORT_HIER' \
  mysql \
  nextcloud \
  HOSTNAME_HIER:3306 \
  nextcloud

# 5. Wartungsmodus deaktivieren
occ maintenance:mode --off
```

### Nach der Migration

In den **MariaDB 2 Optionen** `disable_foreign_key_checks` wieder auf `false` setzen und das Add-on neu starten — danach sind FK-Constraints wieder aktiv.

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
| `disable_foreign_key_checks` | `false` | Disable FK checks — enable only for migration, then set back to `false` |

## Setting up the Nextcloud database

Set database, user and password directly in the add-on options — MariaDB 2 creates everything automatically on startup.

In the Nextcloud web installer, enter:
```
Database user:     nextcloud
Database password: <as set in options>
Database name:     nextcloud
Database host:     <hostname from MariaDB 2 log>:3306
```

## Connection details

| | Value |
|---|---|
| Host (internal, add-on to add-on) | Hostname from HA Supervisor |
| Host (external, from host system) | `<HA-IP>:3307` |
| Port (internal) | `3306` |
| Port (host) | `3307` |

## Migration: Nextcloud from SQLite to MariaDB 2

### Preparation

1. Install **MariaDB 2**, set database/user/password in the options
2. Set option `disable_foreign_key_checks: true` — prevents FK errors during migration (see below)
3. Start MariaDB 2 and **read the hostname from the log:**
   ```
   [INFO] Hostname (for Nextcloud migration): abc123-mariadb2
   ```

### Migration (in Nextcloud Web Terminal)

```sh
alias occ='ALLOW_ROOT=1 php /app/www/public/occ'

# 1. Clean up orphaned database references in SQLite
#    (prevents FK constraint errors on mail tables)
DATA=$(occ config:system:get datadirectory)
php -r "
\$db = new SQLite3('\$DATA/nextcloud.db');
\$db->exec('UPDATE oc_mail_accounts SET drafts_mailbox_id = NULL WHERE drafts_mailbox_id IS NOT NULL AND drafts_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
\$db->exec('UPDATE oc_mail_accounts SET sent_mailbox_id = NULL WHERE sent_mailbox_id IS NOT NULL AND sent_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
\$db->exec('UPDATE oc_mail_accounts SET trash_mailbox_id = NULL WHERE trash_mailbox_id IS NOT NULL AND trash_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
\$db->exec('UPDATE oc_mail_accounts SET archive_mailbox_id = NULL WHERE archive_mailbox_id IS NOT NULL AND archive_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
echo 'Done' . PHP_EOL;
"

# 2. Enable utf8mb4 — prevents emoji errors in calendar entries
occ config:system:set mysql.utf8mb4 --type boolean --value="true"

# 3. Enable maintenance mode
occ maintenance:mode --on

# 4. Convert database
#    Hostname: from MariaDB 2 log (e.g. c4d39aca-mariadb2)
#    Port:     3306 (internal container port, NOT 3307)
#    Password: wrap in SINGLE quotes — special chars like & $ @ cause shell errors otherwise
occ db:convert-type \
  --all-apps \
  --password='YOUR_PASSWORD' \
  mysql \
  nextcloud \
  YOUR_HOSTNAME:3306 \
  nextcloud

# 5. Disable maintenance mode
occ maintenance:mode --off
```

### After migration

In the **MariaDB 2 options**, set `disable_foreign_key_checks` back to `false` and restart the add-on — FK constraints will then be active again.

> **Note:** Migration may take a few minutes depending on data size. After completion, Nextcloud uses MariaDB 2 — the SQLite file is kept but no longer used.

→ [Changelog](CHANGELOG.md)
