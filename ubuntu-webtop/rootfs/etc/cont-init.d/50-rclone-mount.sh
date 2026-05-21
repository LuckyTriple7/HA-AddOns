#!/usr/bin/with-contenv bash

RCLONE_CONF="/config/.config/rclone/rclone.conf"
BOOKMARKS_FILE="/config/.config/gtk-3.0/bookmarks"
PUID=${PUID:-1000}
PGID=${PGID:-1000}
BASE_PORT=8800

if [ ! -f "$RCLONE_CONF" ]; then
    echo "[rclone] Keine rclone.conf gefunden — überspringe."
    exit 0
fi

mkdir -p "$(dirname "$BOOKMARKS_FILE")"
touch "$BOOKMARKS_FILE"

REMOTES=$(RCLONE_CONFIG="$RCLONE_CONF" rclone listremotes 2>/dev/null | sed 's/:$//')

if [ -z "$REMOTES" ]; then
    echo "[rclone] Keine Remotes in rclone.conf — überspringe."
    exit 0
fi

PORT=$BASE_PORT
for REMOTE in $REMOTES; do
    echo "[rclone] Starte WebDAV-Server für ${REMOTE}: auf Port ${PORT}"

    nohup rclone serve webdav "${REMOTE}:" \
        --config "$RCLONE_CONF" \
        --addr "127.0.0.1:${PORT}" \
        --log-level ERROR \
        >/tmp/rclone_webdav_${REMOTE}.log 2>&1 &

    sleep 2

    if curl -sf "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
        echo "[rclone] ${REMOTE}: WebDAV-Server läuft auf Port ${PORT}"

        BOOKMARK="dav://localhost:${PORT}/ ${REMOTE}"
        if ! grep -qF "dav://localhost:${PORT}/" "$BOOKMARKS_FILE" 2>/dev/null; then
            echo "$BOOKMARK" >> "$BOOKMARKS_FILE"
        fi
    else
        ERR=$(cat "/tmp/rclone_webdav_${REMOTE}.log" 2>/dev/null | tail -3)
        echo "[rclone] FEHLER: WebDAV für ${REMOTE}: konnte nicht gestartet werden${ERR:+ — $ERR}"
    fi

    PORT=$((PORT + 1))
done

chown "${PUID}:${PGID}" "$BOOKMARKS_FILE" 2>/dev/null || true
