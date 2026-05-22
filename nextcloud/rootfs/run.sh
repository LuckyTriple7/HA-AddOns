#!/bin/sh
set -e

OPTIONS=/data/options.json

echo "=== options.json ==="
jq 'to_entries | map(if (.key | test("password")) then .value = "***" else . end) | from_entries' \
    "$OPTIONS" 2>/dev/null || echo "FEHLER: $OPTIONS nicht gefunden"
echo "===================="

PUID=$(jq -r '.PUID // 1000' "$OPTIONS" 2>/dev/null || echo 1000)
PGID=$(jq -r '.PGID // 1000' "$OPTIONS" 2>/dev/null || echo 1000)
TZ=$(jq -r '.TZ // "Europe/Berlin"' "$OPTIONS" 2>/dev/null || echo "Europe/Berlin")
ADMIN_USER=$(jq -r '.admin_user // "admin"' "$OPTIONS" 2>/dev/null || echo "admin")
ADMIN_PASS=$(jq -r '.admin_password // ""' "$OPTIONS" 2>/dev/null || echo "")
TRUSTED_DOMAINS=$(jq -r '.trusted_domains // ""' "$OPTIONS" 2>/dev/null || echo "")
DEFAULT_PHONE_REGION=$(jq -r '.default_phone_region // "DE"' "$OPTIONS" 2>/dev/null || echo "DE")
ENABLE_THUMBNAILS=$(jq -r '.enable_thumbnails // true' "$OPTIONS" 2>/dev/null || echo "true")
MEMORY_LIMIT=$(jq -r '.memory_limit // "512M"' "$OPTIONS" 2>/dev/null || echo "512M")
UPLOAD_MAX=$(jq -r '.upload_max_filesize // "512M"' "$OPTIONS" 2>/dev/null || echo "512M")
POST_MAX=$(jq -r '.post_max_size // "512M"' "$OPTIONS" 2>/dev/null || echo "512M")
DISABLE_UPDATES=$(jq -r '.disable_updates // false' "$OPTIONS" 2>/dev/null || echo "false")
MARIADB_DISCOVERY=$(jq -r '.mariadb_discovery // false' "$OPTIONS" 2>/dev/null || echo "false")

echo "[INFO] PUID=$PUID PGID=$PGID TZ=$TZ"

# Umgebungsvariablen für linuxserver
export PUID PGID TZ

# --- MariaDB Autodiscovery via HA Supervisor API ---
DB_TYPE="sqlite"
DB_HOST=""
DB_PORT="3306"
DB_NAME="nextcloud"
DB_USER=""
DB_PASS=""

if [ "$MARIADB_DISCOVERY" = "true" ] && [ -n "$SUPERVISOR_TOKEN" ]; then
    echo "[INFO] Prüfe MariaDB-Service via Supervisor API ..."
    MYSQL_SVC=$(curl -sf \
        -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        "http://supervisor/services/mysql" 2>/dev/null || echo '{"result":"error"}')
    MYSQL_RESULT=$(echo "$MYSQL_SVC" | jq -r '.result // "error"')

    if [ "$MYSQL_RESULT" = "ok" ]; then
        DB_HOST=$(echo "$MYSQL_SVC" | jq -r '.data.host // "core-mariadb"')
        DB_PORT=$(echo "$MYSQL_SVC" | jq -r '.data.port // 3306')
        DB_USER=$(echo "$MYSQL_SVC" | jq -r '.data.username // empty')
        DB_PASS=$(echo "$MYSQL_SVC" | jq -r '.data.password // empty')
        DB_TYPE="mysql"
        echo "[OK]   MariaDB gefunden: ${DB_HOST}:${DB_PORT} — nutze MySQL"
    else
        echo "[INFO] Kein MariaDB-Service gefunden — nutze SQLite"
    fi
elif [ "$MARIADB_DISCOVERY" != "true" ]; then
    echo "[INFO] MariaDB Discovery deaktiviert — nutze SQLite"
else
    echo "[INFO] SUPERVISOR_TOKEN nicht gesetzt — nutze SQLite"
fi

# MariaDB: Nextcloud-Datenbank anlegen falls nicht vorhanden
if [ "$DB_TYPE" = "mysql" ]; then
    echo "[INFO] Stelle Nextcloud-Datenbank '${DB_NAME}' in MariaDB sicher ..."
    mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" \
        -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;" \
        2>/dev/null && echo "[OK]   Datenbank '${DB_NAME}' bereit" \
        || echo "[WARN] Konnte Datenbank nicht prüfen — eventuell bereits vorhanden"
fi

# Nextcloud-Datenpfad im addon_config-Ordner
NC_DATA=/config/data
mkdir -p "$NC_DATA" /config/www /config/log /config/cron

# PHP-Limits setzen (linuxserver: /config/php/php-local.ini)
PHP_INI=/config/php/php-local.ini
mkdir -p /config/php
cat > "$PHP_INI" << EOF
memory_limit = ${MEMORY_LIMIT}
upload_max_filesize = ${UPLOAD_MAX}
post_max_size = ${POST_MAX}
max_execution_time = 300
max_input_time = 300
EOF
echo "[INFO] PHP-Limits: memory=${MEMORY_LIMIT} upload=${UPLOAD_MAX} post=${POST_MAX}"

# SMB-Mount-Funktion
do_mount() {
    SERVER=$1
    SHARE=$2
    USER=$3
    PASS=$4
    MOUNTPOINT=$5

    mkdir -p "$MOUNTPOINT"
    umount "$MOUNTPOINT" 2>/dev/null || true

    if ! nc -z -w 5 "$SERVER" 445 2>/dev/null; then
        echo "[FAIL] Port 445 auf ${SERVER} nicht erreichbar — übersprungen"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
        return
    fi

    OPTS="vers=3.0,uid=${PUID},gid=${PGID},file_mode=0755,dir_mode=0755,noperm,sec=ntlmssp,nodfs"
    if [ -n "$USER" ]; then
        OPTS="${OPTS},username=${USER}"
    else
        OPTS="${OPTS},guest"
    fi
    if [ -n "$PASS" ]; then
        OPTS="${OPTS},password=${PASS}"
    fi

    UNC="//${SERVER}/${SHARE}"
    echo "[INFO] Mounte ${UNC} → ${MOUNTPOINT} ..."

    ERR_FILE="/tmp/mount_err_$$"
    if mount -t cifs "$UNC" "$MOUNTPOINT" -o "$OPTS" >"$ERR_FILE" 2>&1; then
        rm -f "$ERR_FILE"
        echo "[OK]   ${UNC} erfolgreich gemountet"
    else
        MOUNT_ERR=$(cat "$ERR_FILE" 2>/dev/null)
        rm -f "$ERR_FILE"
        echo "[FAIL] Mount von ${UNC} fehlgeschlagen: ${MOUNT_ERR}"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
    fi
}

mount_smb() {
    INDEX=$1
    SERVER=$(jq -r ".smb_${INDEX}_server // empty" "$OPTIONS" 2>/dev/null)
    SHARE=$(jq -r ".smb_${INDEX}_share // empty" "$OPTIONS" 2>/dev/null)
    USER=$(jq -r ".smb_${INDEX}_user // empty" "$OPTIONS" 2>/dev/null)
    PASS=$(jq -r ".smb_${INDEX}_password // empty" "$OPTIONS" 2>/dev/null)

    if [ -z "$SERVER" ]; then
        echo "[INFO] SMB-${INDEX}: nicht konfiguriert — übersprungen"
        return
    fi

    if [ -z "$SHARE" ]; then
        echo "[WARN] SMB-${INDEX}: Kein Share angegeben — übersprungen"
        return
    fi

    do_mount "$SERVER" "$SHARE" "$USER" "$PASS" "/mnt/smb${INDEX}"
}

echo "--- SMB-Mounts ---"
mount_smb 1
mount_smb 2
mount_smb 3
echo "------------------"

# occ-Hilfsfunktion
OCC_BIN=/config/www/nextcloud/occ
occ() {
    sudo -u abc php "$OCC_BIN" "$@" 2>/dev/null || true
}

# occ-Konfiguration (Erst- und Folgestarts)
apply_config() {
    echo "[INFO] Wende Nextcloud-Konfiguration an ..."

    occ config:system:set trusted_domains 0 --value="localhost"
    occ config:system:set trusted_domains 1 --value="homeassistant.local"
    IDX=2
    if [ -n "$TRUSTED_DOMAINS" ]; then
        echo "$TRUSTED_DOMAINS" | tr ',' '\n' | while IFS= read -r D; do
            D=$(echo "$D" | tr -d ' \r')
            [ -z "$D" ] && continue
            occ config:system:set trusted_domains "$IDX" --value="$D"
            IDX=$((IDX + 1))
        done
    fi

    occ config:system:set default_phone_region --value="$DEFAULT_PHONE_REGION"

    if [ "$ENABLE_THUMBNAILS" = "true" ]; then
        occ config:system:set enable_previews --value=true --type=boolean
    else
        occ config:system:set enable_previews --value=false --type=boolean
    fi

    if [ "$DISABLE_UPDATES" = "true" ]; then
        occ config:system:set upgrade.disable-web --value=true --type=boolean
    fi
}

# Ersten-Start-Erkennung
NC_OCC=/config/www/nextcloud/occ
NC_CONFIG=/config/www/nextcloud/config/config.php

if [ ! -f "$NC_CONFIG" ]; then
    echo "[INFO] Erster Start — starte linuxserver /init im Hintergrund ..."
    /init &
    INIT_PID=$!

    # Warte bis Nextcloud-Dateien bereitgestellt wurden (occ ist das früheste Zeichen)
    echo "[INFO] Warte auf Nextcloud-Dateien ..."
    TRIES=0
    while [ ! -f "$NC_OCC" ] && [ $TRIES -lt 120 ]; do
        sleep 5
        TRIES=$((TRIES + 1))
    done

    if [ ! -f "$NC_OCC" ]; then
        echo "[WARN] Nextcloud nicht bereitgestellt nach 10 Minuten — Abbruch"
        wait $INIT_PID
        exit 1
    fi

    echo "[INFO] Nextcloud-Dateien bereit — führe Installation aus ..."

    # occ maintenance:install je nach Datenbanktyp
    if [ "$DB_TYPE" = "mysql" ]; then
        echo "[INFO] Installation mit MariaDB (${DB_HOST}:${DB_PORT}) ..."
        sudo -u abc php "$OCC_BIN" maintenance:install \
            --database mysql \
            --database-name "$DB_NAME" \
            --database-host "$DB_HOST" \
            --database-port "$DB_PORT" \
            --database-user "$DB_USER" \
            --database-pass "$DB_PASS" \
            --admin-user "$ADMIN_USER" \
            --admin-pass "$ADMIN_PASS" \
            --data-dir "$NC_DATA" 2>/dev/null || true
        echo "[OK]   Nextcloud mit MariaDB installiert"
    else
        echo "[INFO] Installation mit SQLite ..."
        sudo -u abc php "$OCC_BIN" maintenance:install \
            --database sqlite \
            --database-name oc_nextcloud \
            --admin-user "$ADMIN_USER" \
            --admin-pass "$ADMIN_PASS" \
            --data-dir "$NC_DATA" 2>/dev/null || true
        echo "[OK]   Nextcloud mit SQLite installiert"
    fi

    apply_config

    # SMB-Shares als externe Speicher einbinden
    occ app:enable files_external
    for IDX in 1 2 3; do
        if mountpoint -q "/mnt/smb${IDX}" 2>/dev/null; then
            SHARE=$(jq -r ".smb_${IDX}_share // empty" "$OPTIONS" 2>/dev/null)
            echo "[INFO] Binde SMB-${IDX} (${SHARE}) als externen Speicher ein ..."
            occ files_external:create "SMB-${IDX} ${SHARE}" local null::null \
                --config datadir="/mnt/smb${IDX}"
        fi
    done

    occ maintenance:mode --off
    echo "[INFO] Ersteinrichtung abgeschlossen — Nextcloud läuft"

    wait $INIT_PID
else
    echo "[INFO] Nextcloud bereits installiert — starte normal"
    apply_config
    exec /init
fi
