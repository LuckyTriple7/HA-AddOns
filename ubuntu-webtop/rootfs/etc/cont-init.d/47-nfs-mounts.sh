#!/usr/bin/with-contenv bash
OPTIONS=/data/options.json

do_mount() {
    SERVER=$1
    SHARE=$2
    MOUNTPOINT=$3
    LABEL=$4

    mkdir -p "$MOUNTPOINT"
    umount "$MOUNTPOINT" 2>/dev/null || true

    if ! nc -z -w 5 "$SERVER" 2049 2>/dev/null; then
        echo "[nfs] FAIL: Port 2049 auf ${SERVER} nicht erreichbar — übersprungen"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
        return
    fi

    if mount -t nfs "${SERVER}:${SHARE}" "$MOUNTPOINT" -o "soft,timeo=30,retrans=3,nfsvers=4" 2>/tmp/nfs_err; then
        echo "[nfs] OK: ${SERVER}:${SHARE} → ${MOUNTPOINT} (${LABEL})"

        BOOKMARKS=/config/.config/gtk-3.0/bookmarks
        mkdir -p "$(dirname "$BOOKMARKS")"
        touch "$BOOKMARKS"
        if ! grep -qF "file://${MOUNTPOINT}" "$BOOKMARKS"; then
            echo "file://${MOUNTPOINT} ${LABEL}" >> "$BOOKMARKS"
            echo "[nfs] Bookmark hinzugefügt: ${LABEL}"
        fi
    else
        echo "[nfs] FAIL: ${SERVER}:${SHARE} — $(cat /tmp/nfs_err 2>/dev/null)"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
    fi
}

mount_slot() {
    INDEX=$1
    SERVER=$(jq -r ".nfs_${INDEX}_server // empty" "$OPTIONS" 2>/dev/null)
    SHARE=$(jq -r ".nfs_${INDEX}_share // empty" "$OPTIONS" 2>/dev/null)

    [ -z "$SERVER" ] && return
    [ -z "$SHARE" ] && echo "[nfs] NFS-${INDEX}: Share-Pfad fehlt — übersprungen" && return

    LABEL="NFS-${INDEX} ${SHARE}"
    MNTPOINT="/mnt/nfs${INDEX}"
    do_mount "$SERVER" "$SHARE" "$MNTPOINT" "$LABEL"
}

echo "--- NFS-Mounts ---"
mount_slot 1
mount_slot 2
mount_slot 3
echo "------------------"
