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
