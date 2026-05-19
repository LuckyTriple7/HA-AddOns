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

# Thunar-Bookmark für /share/webtop eintragen (Seitenleiste)
BOOKMARKS=/config/.config/gtk-3.0/bookmarks
mkdir -p "$(dirname "$BOOKMARKS")"
touch "$BOOKMARKS"
if ! grep -q "file:///share/webtop" "$BOOKMARKS"; then
    echo "file:///share/webtop HA Share" >> "$BOOKMARKS"
    chown "${PUID}:${PGID}" "$BOOKMARKS" 2>/dev/null || true
    echo "[ubuntu-webtop] Thunar-Bookmark für /share/webtop eingetragen"
fi
