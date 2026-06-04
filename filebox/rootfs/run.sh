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

mkdir -p "$ROOT"

# HA-Shares als Bind-Mounts — FileBrowser 2.63.12+ folgt Symlinks außerhalb von ROOT nicht mehr
mkdir -p /share/filebox "$ROOT/FileBox"
umount "$ROOT/FileBox" 2>/dev/null || true
mount --bind /share/filebox "$ROOT/FileBox"

if [ "$SHOW_MEDIA" = "true" ]; then
    mkdir -p "$ROOT/Media"
    umount "$ROOT/Media" 2>/dev/null || true
    mount --bind /media "$ROOT/Media"
else
    umount "$ROOT/Media" 2>/dev/null || true
    rmdir "$ROOT/Media" 2>/dev/null || true
fi

if [ "$SHOW_CONFIG" = "true" ]; then
    mkdir -p "$ROOT/Config"
    umount "$ROOT/Config" 2>/dev/null || true
    mount --bind /config "$ROOT/Config"
else
    umount "$ROOT/Config" 2>/dev/null || true
    rmdir "$ROOT/Config" 2>/dev/null || true
fi

if [ "$SHOW_BACKUP" = "true" ]; then
    mkdir -p "$ROOT/Backup"
    umount "$ROOT/Backup" 2>/dev/null || true
    mount --bind /backup "$ROOT/Backup"
else
    umount "$ROOT/Backup" 2>/dev/null || true
    rmdir "$ROOT/Backup" 2>/dev/null || true
fi

# SMB-Share direkt in ROOT mounten (kein /mnt-Zwischenpfad + Symlink)
do_mount() {
    SERVER=$1
    SHARE=$2
    USER=$3
    PASS=$4
    LINKNAME=$5

    MOUNTPOINT="$ROOT/${LINKNAME}"
    mkdir -p "$MOUNTPOINT"
    umount "$MOUNTPOINT" 2>/dev/null || true

    if ! nc -z -w 5 "$SERVER" 445 2>/dev/null; then
        echo "[FAIL] Port 445 auf ${SERVER} nicht erreichbar — übersprungen"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
        return
    fi

    OPTS="vers=3.0,uid=0,gid=0,file_mode=0755,dir_mode=0755,noperm,sec=ntlmssp,nodfs"
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
        echo "[OK]   In FileBrowser sichtbar als '${LINKNAME}'"
    else
        MOUNT_ERR=$(cat "$ERR_FILE" 2>/dev/null)
        rm -f "$ERR_FILE"
        echo "[FAIL] Mount von ${UNC} fehlgeschlagen: ${MOUNT_ERR}"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
    fi
}

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

    # Alte Mounts für diesen Slot umounten und entfernen
    for d in "$ROOT"/SMB-${INDEX}*; do
        [ -e "$d" ] || continue
        umount "$d" 2>/dev/null || true
        rmdir "$d" 2>/dev/null || true
    done

    if [ -n "$SHARE" ]; then
        do_mount "$SERVER" "$SHARE" "$USER" "$PASS" \
            "SMB-${INDEX} ${SHARE}"
    else
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

        echo "$SHARES" | while IFS= read -r S; do
            S=$(echo "$S" | tr -d '\r')
            [ -z "$S" ] && continue
            do_mount "$SERVER" "$S" "$USER" "$PASS" \
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
    --root "$ROOT" \
    --baseURL "/"
