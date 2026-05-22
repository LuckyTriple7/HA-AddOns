#!/bin/sh
# s6-overlay supervises dieses Script als Longrun.
# KEIN set -e — zu viele Seiteneffekte; Fehler werden manuell geprüft.

OPTIONS=/data/options.json

echo "=== options.json ==="
jq 'to_entries | map(if (.key | test("password")) then .value = "***" else . end) | from_entries' \
    "$OPTIONS" 2>/dev/null || echo "FEHLER: $OPTIONS nicht gefunden"
echo "===================="

PUID=$(jq -r '.PUID // 1000' "$OPTIONS" 2>/dev/null || echo 1000)
PGID=$(jq -r '.PGID // 1000' "$OPTIONS" 2>/dev/null || echo 1000)
TZ=$(jq -r '.TZ // "Europe/Berlin"' "$OPTIONS" 2>/dev/null || echo "Europe/Berlin")
TRUSTED_DOMAINS=$(jq -r '.trusted_domains // ""' "$OPTIONS" 2>/dev/null || echo "")
DEFAULT_PHONE_REGION=$(jq -r '.default_phone_region // "DE"' "$OPTIONS" 2>/dev/null || echo "DE")
ENABLE_THUMBNAILS=$(jq -r '.enable_thumbnails // true' "$OPTIONS" 2>/dev/null || echo "true")
MEMORY_LIMIT=$(jq -r '.memory_limit // "512M"' "$OPTIONS" 2>/dev/null || echo "512M")
UPLOAD_MAX=$(jq -r '.upload_max_filesize // "512M"' "$OPTIONS" 2>/dev/null || echo "512M")
POST_MAX=$(jq -r '.post_max_size // "512M"' "$OPTIONS" 2>/dev/null || echo "512M")
DISABLE_UPDATES=$(jq -r '.disable_updates // false' "$OPTIONS" 2>/dev/null || echo "false")
MARIADB_DISCOVERY=$(jq -r '.mariadb_discovery // false' "$OPTIONS" 2>/dev/null || echo "false")

echo "[INFO] PUID=$PUID PGID=$PGID TZ=$TZ"
export PUID PGID TZ

# --- /config/data früh anlegen damit der Web-Installer schreiben kann ---
mkdir -p /config/data
chown -R "${PUID}:${PGID}" /config/data
chmod 770 /config/data

# --- MariaDB Autodiscovery ---
DB_TYPE="sqlite"
DB_HOST="" DB_PORT="3306" DB_NAME="nextcloud" DB_USER="" DB_PASS=""

if [ "$MARIADB_DISCOVERY" = "true" ] && [ -n "$SUPERVISOR_TOKEN" ]; then
    echo "[INFO] Prüfe MariaDB-Service via Supervisor API ..."
    MYSQL_SVC=$(curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        "http://supervisor/services/mysql" 2>/dev/null || echo '{"result":"error"}')
    if [ "$(echo "$MYSQL_SVC" | jq -r '.result')" = "ok" ]; then
        DB_HOST=$(echo "$MYSQL_SVC" | jq -r '.data.host // "core-mariadb"')
        DB_PORT=$(echo "$MYSQL_SVC" | jq -r '.data.port // 3306')
        DB_USER=$(echo "$MYSQL_SVC" | jq -r '.data.username // empty')
        DB_PASS=$(echo "$MYSQL_SVC" | jq -r '.data.password // empty')
        DB_TYPE="mysql"
        echo "[OK]   MariaDB gefunden: ${DB_HOST}:${DB_PORT}"
        mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" \
            -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;" \
            2>/dev/null && echo "[OK]   Datenbank '${DB_NAME}' bereit" || true
    else
        echo "[INFO] Kein MariaDB-Service — nutze SQLite"
    fi
elif [ "$MARIADB_DISCOVERY" != "true" ]; then
    echo "[INFO] MariaDB Discovery deaktiviert — nutze SQLite"
fi

# --- PHP-Limits ---
mkdir -p /config/php
cat > /config/php/php-local.ini << EOF
memory_limit = ${MEMORY_LIMIT}
upload_max_filesize = ${UPLOAD_MAX}
post_max_size = ${POST_MAX}
max_execution_time = 300
max_input_time = 300
EOF
echo "[INFO] PHP-Limits: memory=${MEMORY_LIMIT} upload=${UPLOAD_MAX} post=${POST_MAX}"

# --- SMB-Mounts ---
do_mount() {
    SERVER=$1 SHARE=$2 USER=$3 PASS=$4 MOUNTPOINT=$5
    mkdir -p "$MOUNTPOINT"
    umount "$MOUNTPOINT" 2>/dev/null || true
    if ! nc -z -w 5 "$SERVER" 445 2>/dev/null; then
        echo "[FAIL] Port 445 auf ${SERVER} nicht erreichbar"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
        return
    fi
    OPTS="vers=3.0,uid=${PUID},gid=${PGID},file_mode=0755,dir_mode=0755,noperm,sec=ntlmssp,nodfs"
    [ -n "$USER" ] && OPTS="${OPTS},username=${USER}" || OPTS="${OPTS},guest"
    [ -n "$PASS" ] && OPTS="${OPTS},password=${PASS}"
    ERR_FILE="/tmp/mount_err_$$"
    if mount -t cifs "//${SERVER}/${SHARE}" "$MOUNTPOINT" -o "$OPTS" >"$ERR_FILE" 2>&1; then
        rm -f "$ERR_FILE"
        echo "[OK]   //${SERVER}/${SHARE} → ${MOUNTPOINT}"
    else
        echo "[FAIL] Mount //${SERVER}/${SHARE}: $(cat "$ERR_FILE" 2>/dev/null)"
        rm -f "$ERR_FILE"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
    fi
}

mount_smb() {
    INDEX=$1
    SERVER=$(jq -r ".smb_${INDEX}_server // empty" "$OPTIONS" 2>/dev/null)
    SHARE=$(jq -r  ".smb_${INDEX}_share // empty"  "$OPTIONS" 2>/dev/null)
    USER=$(jq -r   ".smb_${INDEX}_user // empty"   "$OPTIONS" 2>/dev/null)
    PASS=$(jq -r   ".smb_${INDEX}_password // empty" "$OPTIONS" 2>/dev/null)
    [ -z "$SERVER" ] && echo "[INFO] SMB-${INDEX}: nicht konfiguriert" && return
    [ -z "$SHARE"  ] && echo "[WARN] SMB-${INDEX}: kein Share" && return
    do_mount "$SERVER" "$SHARE" "$USER" "$PASS" "/mnt/smb${INDEX}"
}

echo "--- SMB-Mounts ---"
mount_smb 1; mount_smb 2; mount_smb 3
echo "------------------"

# --- Warte auf linuxservers Init ---
OCC_BIN=/app/www/src/occ

if [ ! -f "$OCC_BIN" ]; then
    echo "[INFO] Warte auf linuxserver Init ..."
    TRIES=0
    while [ ! -f "$OCC_BIN" ] && [ $TRIES -lt 60 ]; do
        sleep 5
        TRIES=$((TRIES + 1))
    done
    if [ ! -f "$OCC_BIN" ]; then
        echo "[WARN] occ nicht gefunden: $(find /app /config/www -name 'occ' 2>/dev/null | tr '\n' ' ')"
        exec tail -f /dev/null
    fi
fi

echo "[INFO] occ gefunden: ${OCC_BIN}"

# OC_CONFIG_PATH zeigt occ auf die persistente config.php (identisch mit dem
# Pfad den der Webserver nutzt: /app/www/public/config → /config/www/nextcloud/config)
export OC_CONFIG_PATH=/config/www/nextcloud/config/
echo "[INFO] OC_CONFIG_PATH=${OC_CONFIG_PATH}"

# --- occ-Wrapper ---
occ() {
    ALLOW_ROOT=1 php "$OCC_BIN" "$@" || true
}

# --- Konfiguration (idempotent, läuft bei jedem Start) ---
apply_config() {
    echo "[INFO] Wende Konfiguration an ..."
    occ config:system:set trusted_domains 0 --value="localhost"
    occ config:system:set trusted_domains 1 --value="homeassistant.local"
    IDX=2
    if [ -n "$TRUSTED_DOMAINS" ]; then
        echo "$TRUSTED_DOMAINS" | tr ',' '\n' | while IFS= read -r D; do
            D=$(echo "$D" | tr -d ' \r'); [ -z "$D" ] && continue
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

# --- Installations-Check ---
NC_INSTALLED=$(ALLOW_ROOT=1 php "$OCC_BIN" status --output=json 2>/dev/null \
    | jq -r '.installed // false' 2>/dev/null || echo "false")
echo "[INFO] NC installed: ${NC_INSTALLED}"

if [ "$NC_INSTALLED" != "true" ]; then
    echo "[INFO] Nextcloud nicht installiert."
    echo "[INFO] Bitte Web-Installer aufrufen: http://<HA-IP>:7780"
    echo "[INFO] Datenverzeichnis im Installer eintragen: /config/data"
    echo "[INFO] Warte auf Abschluss der Web-Installation ..."

    while true; do
        sleep 15
        NC_INSTALLED=$(ALLOW_ROOT=1 php "$OCC_BIN" status --output=json 2>/dev/null \
            | jq -r '.installed // false' 2>/dev/null || echo "false")
        if [ "$NC_INSTALLED" = "true" ]; then
            break
        fi
    done

    echo "[OK]   Web-Installation abgeschlossen — wende Konfiguration an"
    apply_config

    # SMB-Shares als externen Speicher einbinden (nur einmalig nach Erstinstall)
    FLAG=/config/data/.smb_registered
    if [ ! -f "$FLAG" ]; then
        occ app:enable files_external
        for IDX in 1 2 3; do
            if mountpoint -q "/mnt/smb${IDX}" 2>/dev/null; then
                SHARE=$(jq -r ".smb_${IDX}_share // empty" "$OPTIONS" 2>/dev/null)
                echo "[INFO] Binde SMB-${IDX} (${SHARE}) als externen Speicher ein ..."
                occ files_external:create "SMB-${IDX} ${SHARE}" local null::null \
                    --config datadir="/mnt/smb${IDX}"
            fi
        done
        touch "$FLAG"
    fi

    echo "[INFO] Ersteinrichtung abgeschlossen"
else
    echo "[INFO] Nextcloud installiert — aktualisiere Konfiguration"
    apply_config
fi

echo "[INFO] Konfiguration fertig — halte Prozess am Leben (s6 Supervision)"
exec tail -f /dev/null
