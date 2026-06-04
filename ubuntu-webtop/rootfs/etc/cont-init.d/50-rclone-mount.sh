#!/usr/bin/with-contenv bash

RCLONE_CONF="/config/.config/rclone/rclone.conf"
BOOKMARKS_FILE="/config/.config/gtk-3.0/bookmarks"
PUID=${PUID:-1000}
PGID=${PGID:-1000}
BASE_PORT=8800

if [ ! -f "$RCLONE_CONF" ]; then
    echo "[rclone] [$(date +%H:%M:%S)] Keine rclone.conf gefunden — überspringe."
    exit 0
fi

mkdir -p "$(dirname "$BOOKMARKS_FILE")"
touch "$BOOKMARKS_FILE"

REMOTES=$(RCLONE_CONFIG="$RCLONE_CONF" rclone listremotes 2>/dev/null | sed 's/:$//')

if [ -z "$REMOTES" ]; then
    echo "[rclone] [$(date +%H:%M:%S)] Keine Remotes in rclone.conf — überspringe."
    exit 0
fi

# Warte bis DNS verfügbar ist (bis zu 30 Sekunden)
echo "[rclone] [$(date +%H:%M:%S)] Warte auf DNS..."
DNS_OK=false
for i in $(seq 1 15); do
    if getent hosts microsoft.com >/dev/null 2>&1 \
    || getent hosts graph.microsoft.com >/dev/null 2>&1 \
    || getent hosts graph.microsoft.de >/dev/null 2>&1; then
        DNS_OK=true
        echo "[rclone] [$(date +%H:%M:%S)] DNS verfügbar (nach ${i}x2s)"
        break
    fi
    sleep 2
done

if [ "$DNS_OK" = false ]; then
    echo "[rclone] [$(date +%H:%M:%S)] WARNUNG: DNS nach 30s nicht erreichbar — versuche trotzdem..."
fi

PORT=$BASE_PORT
for REMOTE in $REMOTES; do
    echo "[rclone] [$(date +%H:%M:%S)] Starte WebDAV-Server für ${REMOTE}: auf Port ${PORT}"

    nohup rclone serve webdav "${REMOTE}:" \
        --config "$RCLONE_CONF" \
        --addr "127.0.0.1:${PORT}" \
        --vfs-cache-mode full \
        --vfs-cache-max-size 1G \
        --buffer-size 256M \
        --no-modtime \
        --log-level ERROR \
        >/tmp/rclone_webdav_${REMOTE}.log 2>&1 &

    # Warte bis WebDAV antwortet (bis zu 15 Sekunden)
    STARTED=false
    for i in $(seq 1 15); do
        sleep 1
        if curl -sf --connect-timeout 2 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
            STARTED=true
            break
        fi
    done

    if [ "$STARTED" = true ]; then
        echo "[rclone] [$(date +%H:%M:%S)] ${REMOTE}: WebDAV-Server läuft auf Port ${PORT}"

        BOOKMARK="dav://localhost:${PORT}/ ${REMOTE}"
        if ! grep -qF "dav://localhost:${PORT}/" "$BOOKMARKS_FILE" 2>/dev/null; then
            echo "$BOOKMARK" >> "$BOOKMARKS_FILE"
        fi
    else
        ERR=$(cat "/tmp/rclone_webdav_${REMOTE}.log" 2>/dev/null | tail -3)
        echo "[rclone] [$(date +%H:%M:%S)] FEHLER: WebDAV für ${REMOTE}: konnte nicht gestartet werden${ERR:+ — $ERR}"
    fi

    PORT=$((PORT + 1))
done

chown "${PUID}:${PGID}" "$BOOKMARKS_FILE" 2>/dev/null || true
