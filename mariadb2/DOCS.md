# MariaDB 2

Zweite unabhängige MariaDB-Instanz für Home Assistant — läuft parallel zur offiziellen MariaDB-App ohne Konflikte.

| | Offizielle MariaDB | MariaDB 2 |
|---|---|---|
| Port (Host) | 3306 | **3307** |
| Slug | `mariadb` | `mariadb2` |
| Konflikt? | — | Nein — vollständig isoliert |

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `databases` | `[nextcloud]` | Liste der anzulegenden Datenbanken |
| `logins` | `[{username: nextcloud, password: ""}]` | Zugangsdaten |
| `rights` | `[{database: nextcloud, username: nextcloud}]` | Berechtigungen (ALL PRIVILEGES) |
| `disable_foreign_key_checks` | `false` | FK-Checks deaktivieren — nur für Migration aktivieren, danach wieder auf `false` setzen |

## Nextcloud-Datenbank einrichten

Datenbank, Benutzer und Passwort in den Add-on-Optionen setzen — alles wird beim Start automatisch angelegt.

Beim Nextcloud-Webinstaller (`https://<HA-IP>:7443`) eintragen:
```
Datenbankbenutzer:  nextcloud
Datenbankpasswort:  <wie in den Optionen gesetzt>
Datenbankname:      nextcloud
Datenbankhost:      <Hostname aus MariaDB 2 LOG>:3306
```

> Der Hostname steht im LOG des Add-ons: `[INFO] Hostname (for Nextcloud migration): abc123-mariadb2`

## Verbindungsdetails

| | Wert |
|---|---|
| Host (Add-on zu Add-on, intern) | Hostname aus HA Supervisor LOG |
| Host (vom Host-System) | `<HA-IP>:3307` |
| Port (intern) | `3306` |
| Port (Host) | `3307` |

## Migration: Nextcloud von SQLite auf MariaDB 2

### Vorbereitung

1. MariaDB 2 installieren, Datenbank/Benutzer/Passwort in den Optionen setzen
2. `disable_foreign_key_checks: true` setzen
3. MariaDB 2 starten, **Hostname aus dem LOG ablesen**

### Migration (im Nextcloud Web-Terminal)

```sh
alias occ='ALLOW_ROOT=1 php /app/www/public/occ'

# 1. Verwaiste Referenzen in SQLite bereinigen (verhindert FK-Fehler)
DATA=$(occ config:system:get datadirectory)
php -r "
\$db = new SQLite3('\$DATA/nextcloud.db');
\$db->exec('UPDATE oc_mail_accounts SET drafts_mailbox_id = NULL WHERE drafts_mailbox_id IS NOT NULL AND drafts_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
\$db->exec('UPDATE oc_mail_accounts SET sent_mailbox_id = NULL WHERE sent_mailbox_id IS NOT NULL AND sent_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
\$db->exec('UPDATE oc_mail_accounts SET trash_mailbox_id = NULL WHERE trash_mailbox_id IS NOT NULL AND trash_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
\$db->exec('UPDATE oc_mail_accounts SET archive_mailbox_id = NULL WHERE archive_mailbox_id IS NOT NULL AND archive_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
echo 'Fertig' . PHP_EOL;
"

# 2. utf8mb4 aktivieren (verhindert Emoji-Fehler)
occ config:system:set mysql.utf8mb4 --type boolean --value="true"

# 3. Wartungsmodus aktivieren
occ maintenance:mode --on

# 4. Migration durchführen (Passwort in einfachen Anführungszeichen!)
occ db:convert-type --all-apps --password='PASSWORT' mysql nextcloud HOSTNAME:3306 nextcloud

# 5. Wartungsmodus deaktivieren
occ maintenance:mode --off
```

### Nach der Migration

`disable_foreign_key_checks` wieder auf `false` setzen und Add-on neu starten.

---

# MariaDB 2 (English)

A second independent MariaDB instance for Home Assistant — runs alongside the official MariaDB app without conflicts.

| | Official MariaDB | MariaDB 2 |
|---|---|---|
| Port (host) | 3306 | **3307** |
| Slug | `mariadb` | `mariadb2` |
| Conflict? | — | No — fully isolated |

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `databases` | `[nextcloud]` | List of databases to create |
| `logins` | `[{username: nextcloud, password: ""}]` | Login credentials |
| `rights` | `[{database: nextcloud, username: nextcloud}]` | Permissions (ALL PRIVILEGES) |
| `disable_foreign_key_checks` | `false` | Disable FK checks — enable only for migration, then set back to `false` |

## Setting up the Nextcloud Database

Set database, user and password in the add-on options — everything is created automatically on startup.

In the Nextcloud web installer (`https://<HA-IP>:7443`) enter:
```
Database user:     nextcloud
Database password: <as set in options>
Database name:     nextcloud
Database host:     <hostname from MariaDB 2 log>:3306
```

> The hostname appears in the add-on log: `[INFO] Hostname (for Nextcloud migration): abc123-mariadb2`

## Connection Details

| | Value |
|---|---|
| Host (add-on to add-on, internal) | Hostname from HA Supervisor log |
| Host (from host system) | `<HA-IP>:3307` |
| Port (internal) | `3306` |
| Port (host) | `3307` |

## Migration: Nextcloud from SQLite to MariaDB 2

### Preparation

1. Install MariaDB 2, set database/user/password in options
2. Set `disable_foreign_key_checks: true`
3. Start MariaDB 2 and **read the hostname from the log**

### Migration (in Nextcloud Web Terminal)

```sh
alias occ='ALLOW_ROOT=1 php /app/www/public/occ'

# 1. Clean up orphaned references in SQLite (prevents FK errors)
DATA=$(occ config:system:get datadirectory)
php -r "
\$db = new SQLite3('\$DATA/nextcloud.db');
\$db->exec('UPDATE oc_mail_accounts SET drafts_mailbox_id = NULL WHERE drafts_mailbox_id IS NOT NULL AND drafts_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
\$db->exec('UPDATE oc_mail_accounts SET sent_mailbox_id = NULL WHERE sent_mailbox_id IS NOT NULL AND sent_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
\$db->exec('UPDATE oc_mail_accounts SET trash_mailbox_id = NULL WHERE trash_mailbox_id IS NOT NULL AND trash_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
\$db->exec('UPDATE oc_mail_accounts SET archive_mailbox_id = NULL WHERE archive_mailbox_id IS NOT NULL AND archive_mailbox_id NOT IN (SELECT id FROM oc_mail_mailboxes)');
echo 'Done' . PHP_EOL;
"

# 2. Enable utf8mb4 (prevents emoji errors)
occ config:system:set mysql.utf8mb4 --type boolean --value="true"

# 3. Enable maintenance mode
occ maintenance:mode --on

# 4. Run migration (password in single quotes!)
occ db:convert-type --all-apps --password='PASSWORD' mysql nextcloud HOSTNAME:3306 nextcloud

# 5. Disable maintenance mode
occ maintenance:mode --off
```

### After Migration

Set `disable_foreign_key_checks` back to `false` and restart the add-on.
