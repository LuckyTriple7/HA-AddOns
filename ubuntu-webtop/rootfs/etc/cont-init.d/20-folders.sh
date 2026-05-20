#!/usr/bin/with-contenv bash
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

chmod 755 /config 2>/dev/null || true
chown "${PUID}:${PGID}" /config 2>/dev/null || true

# Besitzer von .config rekursiv korrigieren – wird von cont-init.d als root erstellt
# und muss für den abc-User (PUID) beschreibbar sein
if [ -d /config/.config ]; then
    chown -R "${PUID}:${PGID}" /config/.config 2>/dev/null || true
fi

echo "[ubuntu-webtop] /config bereit (addon_config-Mount, Besitzer: ${PUID}:${PGID})"

# /share/webtop anlegen falls nicht vorhanden
mkdir -p /share/webtop
chown "${PUID}:${PGID}" /share/webtop 2>/dev/null || true
echo "[ubuntu-webtop] /share/webtop bereit"

# Optionen lesen
OPTIONS=/data/options.json
SHOW_MEDIA=$(jq -r '.show_media // false' "$OPTIONS" 2>/dev/null || echo "false")
SHOW_BACKUP=$(jq -r '.show_backup // false' "$OPTIONS" 2>/dev/null || echo "false")

echo "[ubuntu-webtop] Shares: media=${SHOW_MEDIA} backup=${SHOW_BACKUP}"

# Thunar-Bookmarks: nur hinzufügen, nie löschen
BOOKMARKS=/config/.config/gtk-3.0/bookmarks
mkdir -p "$(dirname "$BOOKMARKS")"
touch "$BOOKMARKS"

add_bookmark() {
    local URI=$1 NAME=$2
    if ! grep -qF "$URI" "$BOOKMARKS"; then
        echo "$URI $NAME" >> "$BOOKMARKS"
        echo "[ubuntu-webtop] Bookmark hinzugefügt: $NAME"
    fi
}

add_bookmark "file:///share/webtop" "HA Share"

if [ "$SHOW_MEDIA" = "true" ] && [ -d /media ]; then
    add_bookmark "file:///media" "HA Media"
    echo "[ubuntu-webtop] /media sichtbar"
fi

if [ "$SHOW_BACKUP" = "true" ] && [ -d /backup ]; then
    add_bookmark "file:///backup" "HA Backup"
    echo "[ubuntu-webtop] /backup sichtbar"
fi

chown "${PUID}:${PGID}" "$BOOKMARKS" 2>/dev/null || true
