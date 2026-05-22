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

echo "[INFO] PUID=$PUID PGID=$PGID TZ=$TZ"

# Umgebungsvariablen für linuxserver
export PUID PGID TZ

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

# Ersten-Start-Erkennung: Nextcloud-Installation via occ
NC_CONFIG=/config/www/nextcloud/config/config.php
if [ ! -f "$NC_CONFIG" ]; then
    echo "[INFO] Erster Start — warte auf Nextcloud-Initialisierung durch linuxserver ..."
    # linuxserver initialisiert Nextcloud in /config/www/nextcloud beim ersten Start
    # Wir starten /init zuerst im Hintergrund und warten dann
    /init &
    INIT_PID=$!

    echo "[INFO] Warte auf Nextcloud-Installation ..."
    TRIES=0
    while [ ! -f "$NC_CONFIG" ] && [ $TRIES -lt 120 ]; do
        sleep 5
        TRIES=$((TRIES + 1))
    done

    if [ ! -f "$NC_CONFIG" ]; then
        echo "[WARN] Nextcloud-Config nach 10 Minuten noch nicht vorhanden"
        wait $INIT_PID
        exit 1
    fi

    echo "[INFO] Nextcloud-Installation abgeschlossen, konfiguriere ..."

    OCC="php /config/www/nextcloud/occ"

    # Admin-Passwort setzen (linuxserver setzt default admin/admin)
    if [ -n "$ADMIN_PASS" ]; then
        echo "[INFO] Setze Admin-Passwort ..."
        sudo -u abc "$OCC" user:resetpassword --password-from-env admin <<< "$ADMIN_PASS" 2>/dev/null || true
        # Admin-User umbenennen falls gewünscht
        if [ "$ADMIN_USER" != "admin" ]; then
            echo "[INFO] Admin-User: admin → ${ADMIN_USER}"
            sudo -u abc "$OCC" user:modify admin --display-name "$ADMIN_USER" 2>/dev/null || true
        fi
    fi

    # Datenpfad konfigurieren
    sudo -u abc "$OCC" config:system:set datadirectory --value="/config/data" 2>/dev/null || true

    # Trusted Domains
    sudo -u abc "$OCC" config:system:set trusted_domains 0 --value="localhost" 2>/dev/null || true
    sudo -u abc "$OCC" config:system:set trusted_domains 1 --value="homeassistant.local" 2>/dev/null || true
    IDX=2
    if [ -n "$TRUSTED_DOMAINS" ]; then
        echo "$TRUSTED_DOMAINS" | tr ',' '\n' | while IFS= read -r D; do
            D=$(echo "$D" | tr -d ' \r')
            [ -z "$D" ] && continue
            sudo -u abc "$OCC" config:system:set trusted_domains $IDX --value="$D" 2>/dev/null || true
            IDX=$((IDX + 1))
        done
    fi

    # Telefon-Region
    sudo -u abc "$OCC" config:system:set default_phone_region --value="$DEFAULT_PHONE_REGION" 2>/dev/null || true

    # Thumbnails
    if [ "$ENABLE_THUMBNAILS" = "true" ]; then
        sudo -u abc "$OCC" config:system:set enable_previews --value=true --type=boolean 2>/dev/null || true
    else
        sudo -u abc "$OCC" config:system:set enable_previews --value=false --type=boolean 2>/dev/null || true
    fi

    # Updates deaktivieren
    if [ "$DISABLE_UPDATES" = "true" ]; then
        sudo -u abc "$OCC" config:system:set upgrade.disable-web --value=true --type=boolean 2>/dev/null || true
    fi

    # SMB-Shares als externe Speicher einbinden (falls gemountet)
    sudo -u abc "$OCC" app:enable files_external 2>/dev/null || true
    for IDX in 1 2 3; do
        if mountpoint -q "/mnt/smb${IDX}" 2>/dev/null; then
            SHARE=$(jq -r ".smb_${IDX}_share // empty" "$OPTIONS" 2>/dev/null)
            echo "[INFO] Binde SMB-${IDX} (${SHARE}) als externen Speicher ein ..."
            sudo -u abc "$OCC" files_external:create "SMB-${IDX} ${SHARE}" local null::null \
                --config datadir="/mnt/smb${IDX}" 2>/dev/null || true
        fi
    done

    sudo -u abc "$OCC" maintenance:mode --off 2>/dev/null || true
    echo "[INFO] Konfiguration abgeschlossen"

    wait $INIT_PID
else
    # Folgestarts: nur PHP-Config anpassen, dann /init starten
    echo "[INFO] Nextcloud bereits installiert — starte normal"

    OCC="php /config/www/nextcloud/occ"

    # Trusted Domains aktualisieren
    sudo -u abc "$OCC" config:system:set trusted_domains 0 --value="localhost" 2>/dev/null || true
    sudo -u abc "$OCC" config:system:set trusted_domains 1 --value="homeassistant.local" 2>/dev/null || true
    IDX=2
    if [ -n "$TRUSTED_DOMAINS" ]; then
        echo "$TRUSTED_DOMAINS" | tr ',' '\n' | while IFS= read -r D; do
            D=$(echo "$D" | tr -d ' \r')
            [ -z "$D" ] && continue
            sudo -u abc "$OCC" config:system:set trusted_domains $IDX --value="$D" 2>/dev/null || true
            IDX=$((IDX + 1))
        done
    fi

    sudo -u abc "$OCC" config:system:set default_phone_region --value="$DEFAULT_PHONE_REGION" 2>/dev/null || true

    if [ "$ENABLE_THUMBNAILS" = "true" ]; then
        sudo -u abc "$OCC" config:system:set enable_previews --value=true --type=boolean 2>/dev/null || true
    else
        sudo -u abc "$OCC" config:system:set enable_previews --value=false --type=boolean 2>/dev/null || true
    fi

    if [ "$DISABLE_UPDATES" = "true" ]; then
        sudo -u abc "$OCC" config:system:set upgrade.disable-web --value=true --type=boolean 2>/dev/null || true
    fi

    exec /init
fi
