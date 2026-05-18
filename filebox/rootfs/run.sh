#!/bin/sh
set -e

DB=/data/filebrowser.db
ROOT=/data/filebox-root

echo "=== options.json ==="
jq 'to_entries | map(if (.key | test("password")) then .value = "***" else . end) | from_entries' \
    /data/options.json 2>/dev/null || echo "FEHLER: /data/options.json nicht gefunden"
echo "===================="

PORT=$(jq -r '.port // 17771' /data/options.json 2>/dev/null || echo 17771)
USERNAME=$(jq -r '.username // "admin"' /data/options.json 2>/dev/null || echo "admin")
PASSWORD=$(jq -r '.password // "admin1234567"' /data/options.json 2>/dev/null || echo "admin1234567")
SHOW_MEDIA=$(jq -r '.show_media // false' /data/options.json 2>/dev/null || echo "false")
SHOW_CONFIG=$(jq -r '.show_config // false' /data/options.json 2>/dev/null || echo "false")
SHOW_BACKUP=$(jq -r '.show_backup // false' /data/options.json 2>/dev/null || echo "false")

echo "[INFO] PORT=$PORT SHOW_MEDIA=$SHOW_MEDIA SHOW_CONFIG=$SHOW_CONFIG SHOW_BACKUP=$SHOW_BACKUP"

# Standard-Ordner anlegen
mkdir -p /share/filebox "$ROOT"

# Symlinks für HA-Shares
ln -sfn /share/filebox "$ROOT/FileBox"

if [ "$SHOW_MEDIA" = "true" ]; then
    ln -sfn /media "$ROOT/Media"
else
    rm -f "$ROOT/Media"
fi

if [ "$SHOW_CONFIG" = "true" ]; then
    ln -sfn /config "$ROOT/Config"
else
    rm -f "$ROOT/Config"
fi

if [ "$SHOW_BACKUP" = "true" ]; then
    ln -sfn /backup "$ROOT/Backup"
else
    rm -f "$ROOT/Backup"
fi

# Einen SMB-Share mounten (mit Timeout gegen Hänger)
do_mount() {
    SERVER=$1
    SHARE=$2
    USER=$3
    PASS=$4
    MOUNTPOINT=$5
    LINKNAME=$6

    mkdir -p "$MOUNTPOINT"
    umount "$MOUNTPOINT" 2>/dev/null || true

    OPTS="vers=3.0,uid=0,gid=0,file_mode=0755,dir_mode=0755,noperm"
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
    mount -t cifs "$UNC" "$MOUNTPOINT" -o "$OPTS" >"$ERR_FILE" 2>&1 &
    MOUNT_PID=$!

    ELAPSED=0
    while [ $ELAPSED -lt 15 ]; do
        if ! kill -0 $MOUNT_PID 2>/dev/null; then break; fi
        sleep 1
        ELAPSED=$((ELAPSED + 1))
    done

    if kill -0 $MOUNT_PID 2>/dev/null; then
        kill -9 $MOUNT_PID 2>/dev/null
        echo "[FAIL] Mount timeout (15s) für ${UNC} — übersprungen"
        rm -f "$ERR_FILE"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
        return
    fi

    wait $MOUNT_PID 2>/dev/null
    MOUNT_RC=$?
    MOUNT_ERR=$(cat "$ERR_FILE" 2>/dev/null)
    rm -f "$ERR_FILE"

    if [ $MOUNT_RC -eq 0 ]; then
        echo "[OK]   ${UNC} erfolgreich gemountet"
        rm -f "$ROOT/${LINKNAME}"
        ln -sfn "$MOUNTPOINT" "$ROOT/${LINKNAME}"
        echo "[OK]   In FileBrowser sichtbar als '${LINKNAME}'"
    else
        echo "[FAIL] Mount von ${UNC} fehlgeschlagen: ${MOUNT_ERR}"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
    fi
}

# Alle Shares eines Servers mounten (Auto-Discovery oder einzelner Share)
mount_server() {
    INDEX=$1
    SERVER=$(jq -r ".smb_${INDEX}_server // empty" /data/options.json 2>/dev/null)
    SHARE=$(jq -r ".smb_${INDEX}_share // empty" /data/options.json 2>/dev/null)
    USER=$(jq -r ".smb_${INDEX}_user // empty" /data/options.json 2>/dev/null)
    PASS=$(jq -r ".smb_${INDEX}_password // empty" /data/options.json 2>/dev/null)

    if [ -z "$SERVER" ]; then
        echo "[INFO] SMB-${INDEX}: nicht konfiguriert — übersprungen"
        return
    fi

    echo "[INFO] SMB-${INDEX}: Server ${SERVER}"

    # Alten Symlinks für diesen Slot aufräumen
    rm -f "$ROOT/SMB-${INDEX}"*

    if [ -n "$SHARE" ]; then
        # Einzelner Share angegeben
        do_mount "$SERVER" "$SHARE" "$USER" "$PASS" \
            "/mnt/smb${INDEX}_${SHARE}" \
            "SMB-${INDEX} ${SHARE}"
    else
        # Auto-Discovery: alle Disk-Shares des Servers ermitteln
        echo "[INFO] SMB-${INDEX}: Ermittle alle Shares auf ${SERVER} ..."
        if [ -n "$USER" ]; then
            SMB_LIST_CMD="smbclient -L $SERVER -U ${USER}%${PASS} -g"
        else
            SMB_LIST_CMD="smbclient -L $SERVER -N -g"
        fi
        SMB_LIST_OUT=$(eval "$SMB_LIST_CMD" 2>&1)
        echo "[DEBUG] SMB-${INDEX}: smbclient Ausgabe: ${SMB_LIST_OUT}"
        SHARES=$(echo "$SMB_LIST_OUT" | awk -F'|' '/^Disk\|/ {print $2}')

        if [ -z "$SHARES" ]; then
            echo "[WARN] SMB-${INDEX}: Keine Shares auf ${SERVER} gefunden"
            return
        fi

        COUNT=0
        echo "$SHARES" | while IFS= read -r S; do
            S=$(echo "$S" | tr -d '\r')
            [ -z "$S" ] && continue
            COUNT=$((COUNT + 1))
            MNTPOINT="/mnt/smb${INDEX}_$(echo "$S" | tr ' ' '_')"
            do_mount "$SERVER" "$S" "$USER" "$PASS" \
                "$MNTPOINT" \
                "SMB-${INDEX} ${S}"
        done
        echo "[INFO] SMB-${INDEX}: Auto-Discovery abgeschlossen"
    fi
}

echo "--- SMB-Mounts ---"
mount_server 1
mount_server 2
mount_server 3
mount_server 4
mount_server 5
echo "------------------"

# Erster Start: FileBrowser DB initialisieren
if [ ! -f "$DB" ]; then
    echo "[INFO] Erste Initialisierung der FileBrowser-Datenbank ..."
    filebrowser --database "$DB" --address 127.0.0.1 --port 19999 --root "$ROOT" &
    FB_PID=$!
    sleep 3
    kill "$FB_PID" 2>/dev/null
    wait "$FB_PID" 2>/dev/null || true
fi

filebrowser config set --defaults.locale de --database "$DB" 2>/dev/null || true
filebrowser users update 1 \
    --username "$USERNAME" \
    --password "$PASSWORD" \
    --locale de \
    --database "$DB" 2>/dev/null || true

echo "[INFO] Starte FileBrowser auf Port ${PORT} ..."
exec filebrowser \
    --database "$DB" \
    --address 0.0.0.0 \
    --port "$PORT" \
    --root "$ROOT"
