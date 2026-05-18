#!/bin/sh
set -e

DB=/data/filebrowser.db
ROOT=/data/filebox-root

echo "=== options.json ==="
cat /data/options.json 2>/dev/null || echo "FEHLER: /data/options.json nicht gefunden"
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

# SMB-Shares mounten
mount_smb() {
    INDEX=$1
    SERVER=$(jq -r ".smb_${INDEX}_server // empty" /data/options.json 2>/dev/null)
    SHARE=$(jq -r ".smb_${INDEX}_share // empty" /data/options.json 2>/dev/null)
    USER=$(jq -r ".smb_${INDEX}_user // empty" /data/options.json 2>/dev/null)
    PASS=$(jq -r ".smb_${INDEX}_password // empty" /data/options.json 2>/dev/null)
    MOUNTPOINT="/mnt/smb${INDEX}"

    if [ -z "$SERVER" ]; then
        echo "[INFO] SMB-${INDEX}: nicht konfiguriert — übersprungen"
        rm -f "$ROOT/SMB-${INDEX}"*
        return
    fi

    echo "[INFO] SMB-${INDEX}: Verbinde mit ${SERVER} ..."
    mkdir -p "$MOUNTPOINT"
    umount "$MOUNTPOINT" 2>/dev/null || true

    # Mount-Optionen
    OPTS="uid=0,gid=0,file_mode=0755,dir_mode=0755,noperm"
    if [ -n "$USER" ]; then
        OPTS="${OPTS},username=${USER}"
    else
        OPTS="${OPTS},guest"
        echo "[INFO] SMB-${INDEX}: Kein Benutzer angegeben — versuche Gastzugang"
    fi
    if [ -n "$PASS" ]; then
        OPTS="${OPTS},password=${PASS}"
    fi

    # UNC-Pfad aufbauen
    if [ -n "$SHARE" ]; then
        UNC="//${SERVER}/${SHARE}"
        LINKNAME="SMB-${INDEX} (${SHARE})"
    else
        echo "[INFO] SMB-${INDEX}: Kein Share-Name angegeben — ermittle ersten Share auf ${SERVER} ..."
        FIRST_SHARE=$(smbclient -L "$SERVER" -U "${USER}%${PASS}" -g 2>/dev/null \
            | awk -F'|' '/^Disk\|/ {print $2; exit}')
        if [ -z "$FIRST_SHARE" ]; then
            echo "[WARN] SMB-${INDEX}: Kein Share auf ${SERVER} gefunden — Mount übersprungen"
            rm -f "$ROOT/SMB-${INDEX}"*
            return
        fi
        echo "[INFO] SMB-${INDEX}: Erster Share gefunden: ${FIRST_SHARE}"
        UNC="//${SERVER}/${FIRST_SHARE}"
        LINKNAME="SMB-${INDEX} (${FIRST_SHARE})"
    fi

    echo "[INFO] SMB-${INDEX}: Mounte ${UNC} ..."
    MOUNT_ERR=$(mount -t cifs "$UNC" "$MOUNTPOINT" -o "$OPTS" 2>&1)
    if [ $? -eq 0 ]; then
        echo "[OK]   SMB-${INDEX}: ${UNC} erfolgreich gemountet → ${MOUNTPOINT}"
        rm -f "$ROOT/SMB-${INDEX}"*
        ln -sfn "$MOUNTPOINT" "$ROOT/${LINKNAME}"
        echo "[OK]   SMB-${INDEX}: In FileBrowser sichtbar als '${LINKNAME}'"
    else
        echo "[FAIL] SMB-${INDEX}: Mount von ${UNC} fehlgeschlagen"
        echo "[FAIL] SMB-${INDEX}: Fehler: ${MOUNT_ERR}"
        rm -f "$ROOT/SMB-${INDEX}"*
    fi
}

echo "--- SMB-Mounts ---"
mount_smb 1
mount_smb 2
mount_smb 3
mount_smb 4
mount_smb 5
echo "------------------"

# Erster Start: FileBrowser kurz im Hintergrund starten damit die DB angelegt wird
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
