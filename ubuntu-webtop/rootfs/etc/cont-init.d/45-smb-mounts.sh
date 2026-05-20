#!/bin/sh
OPTIONS=/data/options.json

do_mount() {
    SERVER=$1
    SHARE=$2
    USER=$3
    PASS=$4
    MOUNTPOINT=$5
    LABEL=$6

    mkdir -p "$MOUNTPOINT"
    umount "$MOUNTPOINT" 2>/dev/null || true

    if ! nc -z -w 5 "$SERVER" 445 2>/dev/null; then
        echo "[smb] FAIL: Port 445 auf ${SERVER} nicht erreichbar — übersprungen"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
        return
    fi

    OPTS="vers=3.0,uid=0,gid=0,file_mode=0755,dir_mode=0755,noperm,sec=ntlmssp,nodfs"
    [ -n "$USER" ] && OPTS="${OPTS},username=${USER}" || OPTS="${OPTS},guest"
    [ -n "$PASS" ] && OPTS="${OPTS},password=${PASS}"

    if mount -t cifs "//${SERVER}/${SHARE}" "$MOUNTPOINT" -o "$OPTS" 2>/tmp/smb_err; then
        echo "[smb] OK: //${SERVER}/${SHARE} → ${MOUNTPOINT} (${LABEL})"

        BOOKMARKS=/config/.config/gtk-3.0/bookmarks
        mkdir -p "$(dirname "$BOOKMARKS")"
        touch "$BOOKMARKS"
        if ! grep -qF "file://${MOUNTPOINT}" "$BOOKMARKS"; then
            echo "file://${MOUNTPOINT} ${LABEL}" >> "$BOOKMARKS"
            echo "[smb] Bookmark hinzugefügt: ${LABEL}"
        fi
    else
        echo "[smb] FAIL: //${SERVER}/${SHARE} — $(cat /tmp/smb_err 2>/dev/null)"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
    fi
}

mount_slot() {
    INDEX=$1
    SERVER=$(jq -r ".smb_${INDEX}_server // empty" "$OPTIONS" 2>/dev/null)
    SHARE=$(jq -r ".smb_${INDEX}_share // empty" "$OPTIONS" 2>/dev/null)
    USER=$(jq -r ".smb_${INDEX}_user // empty" "$OPTIONS" 2>/dev/null)
    PASS=$(jq -r ".smb_${INDEX}_password // empty" "$OPTIONS" 2>/dev/null)

    [ -z "$SERVER" ] && return
    [ -z "$SHARE" ] && echo "[smb] SMB-${INDEX}: Share-Name fehlt — übersprungen" && return

    LABEL="SMB-${INDEX} ${SHARE}"
    MNTPOINT="/mnt/smb${INDEX}"
    do_mount "$SERVER" "$SHARE" "$USER" "$PASS" "$MNTPOINT" "$LABEL"
}

echo "--- SMB-Mounts ---"
mount_slot 1
mount_slot 2
mount_slot 3
mount_slot 4
mount_slot 5
echo "------------------"
