#!/usr/bin/with-contenv bash
OPTIONS=/data/options.json

# Laeuft das Ziel ueber Tailscale, sieht der NFS-Server die 100.x-Tailnet-IP
# als Absender und weist IP-gefilterte Exporte mit "access denied by server"
# ab. Das steht sonst nirgends im Log — hier den konkreten Fix ausgeben.
diag_route() {
    ORIG=$1
    SRV=$ORIG
    case "$SRV" in
        *[!0-9.]*)             # Hostname — erst aufloesen, ip route get will eine IP
            SRV=$(getent ahostsv4 "$ORIG" 2>/dev/null | awk '{print $1; exit}')
            [ -n "$SRV" ] || return
            ;;
    esac
    case "$SRV" in
        100.*)                 # 100.64.0.0/10 ist Tailscales eigener Bereich —
            O2=${SRV#100.}     # dort ist der Weg über tailscale0 richtig so.
            O2=${O2%%.*}
            [ "$O2" -ge 64 ] 2>/dev/null && [ "$O2" -le 127 ] 2>/dev/null && return
            ;;
    esac
    DEV=$(ip route get "$SRV" 2>/dev/null | sed -n 's/.*[[:space:]]dev[[:space:]]\([^[:space:]]*\).*/\1/p' | head -1)
    [ "$DEV" = "tailscale0" ] || return
    NET=$(echo "$SRV" | cut -d. -f1-3)
    WHO=$ORIG
    [ "$ORIG" = "$SRV" ] || WHO="${ORIG} (${SRV})"
    echo "[nfs] Grund: ${WHO} wird über Tailscale geroutet (dev tailscale0) — der Server sieht die 100.x-Tailnet-IP als Absender."
    echo "[nfs] Fix: \"${NET}.0/24\" in die Add-on-Option \"tailscale_exclude_routes\" eintragen und Add-on neu starten."
}

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
        diag_route "$SERVER"
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
