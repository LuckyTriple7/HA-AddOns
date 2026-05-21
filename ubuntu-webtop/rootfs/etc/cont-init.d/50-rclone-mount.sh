#!/usr/bin/with-contenv bash

RCLONE_CONF="/config/.config/rclone/rclone.conf"
BOOKMARKS_FILE="/config/.config/gtk-3.0/bookmarks"
PUID=${PUID:-1000}
PGID=${PGID:-1000}

# Kein rclone.conf → nichts zu tun
if [ ! -f "$RCLONE_CONF" ]; then
    echo "[rclone] Keine rclone.conf gefunden — überspringe."
    exit 0
fi

mkdir -p "$BOOKMARKS_FILE" 2>/dev/null; rmdir "$BOOKMARKS_FILE" 2>/dev/null || true
mkdir -p "$(dirname "$BOOKMARKS_FILE")"
touch "$BOOKMARKS_FILE"

# Alle konfigurierten Remotes einlesen
REMOTES=$(RCLONE_CONFIG="$RCLONE_CONF" rclone listremotes 2>/dev/null | sed 's/:$//')

if [ -z "$REMOTES" ]; then
    echo "[rclone] Keine Remotes in rclone.conf — überspringe."
    exit 0
fi

for REMOTE in $REMOTES; do
    MOUNT_POINT="/config/${REMOTE}"
    mkdir -p "$MOUNT_POINT"

    # Alten Mount aushängen falls vorhanden
    if mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
        fusermount3 -uz "$MOUNT_POINT" 2>/dev/null || umount -l "$MOUNT_POINT" 2>/dev/null || true
        sleep 1
    fi

    echo "[rclone] Mounte ${REMOTE}: → ${MOUNT_POINT}"
    RCLONE_CONFIG="$RCLONE_CONF" rclone mount "${REMOTE}:" "$MOUNT_POINT" \
        --vfs-cache-mode minimal \
        --vfs-cache-max-age 1h \
        --allow-other \
        --uid "$PUID" \
        --gid "$PGID" \
        --dir-cache-time 5m \
        --poll-interval 15s \
        --daemon \
        --log-level ERROR \
        2>/dev/null

    # Kurz warten und prüfen ob Mount erfolgreich war
    sleep 2
    if mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
        chown "${PUID}:${PGID}" "$MOUNT_POINT" 2>/dev/null || true
        echo "[rclone] ${REMOTE}: erfolgreich gemountet auf ${MOUNT_POINT}"

        # Thunar-Lesezeichen eintragen
        BOOKMARK="file://${MOUNT_POINT} ${REMOTE}"
        if ! grep -qF "$BOOKMARK" "$BOOKMARKS_FILE" 2>/dev/null; then
            echo "$BOOKMARK" >> "$BOOKMARKS_FILE"
        fi
    else
        echo "[rclone] WARNUNG: Mount von ${REMOTE}: fehlgeschlagen — Konfiguration prüfen."
    fi
done

chown "${PUID}:${PGID}" "$BOOKMARKS_FILE" 2>/dev/null || true
