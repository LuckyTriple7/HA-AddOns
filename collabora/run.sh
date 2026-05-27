#!/bin/bash
set -e

echo "[DEBUG] run.sh gestartet als: $(id)"

# Read HA options
NEXTCLOUD_URL=$(jq -r '.nextcloud_url // ""' /data/options.json)
ALIASGROUP1=$(jq -r '.aliasgroup1 // ""' /data/options.json)
DOMAIN1=$(jq -r '.domain1 // ""' /data/options.json)
ADMIN_USER=$(jq -r '.admin_user // "admin"' /data/options.json)
ADMIN_PASSWORD=$(jq -r '.admin_password // ""' /data/options.json)
EXTRA_PARAMS=$(jq -r '.extra_params // ""' /data/options.json)

echo "[DEBUG] ADMIN_USER='${ADMIN_USER}' PASSWORD_GESETZT=$([ -n "$ADMIN_PASSWORD" ] && echo ja || echo NEIN)"

if [ -n "$ALIASGROUP1" ]; then
    DOMAIN="$ALIASGROUP1"
else
    DOMAIN=$(echo "$NEXTCLOUD_URL" | sed -E 's|https?://||; s|/.*||; s|:[0-9]+||; s/\./\\./g')
fi

echo "[DEBUG] domain='${DOMAIN}'"

# coolwsd.xml nach /config persistieren
COOL_CONFIG="/etc/coolwsd/coolwsd.xml"
CONFIG_DEST="/config/coolwsd.xml"
if [ ! -f "${CONFIG_DEST}" ]; then
    echo "[DEBUG] Kopiere coolwsd.xml nach /config..."
    cp "${COOL_CONFIG}" "${CONFIG_DEST}"
fi
ln -sf "${CONFIG_DEST}" "${COOL_CONFIG}"

# Diagnostik: admin_console Sektion zeigen
echo "[DEBUG] admin_console in XML (vor Update):"
xmlstarlet sel -t -c "//admin_console" "${CONFIG_DEST}" 2>/dev/null || echo "  [xmlstarlet: //admin_console nicht gefunden — Fallback grep:]" && grep -A6 "admin_console" "${CONFIG_DEST}" 2>/dev/null | head -10 || true

# Credentials via xmlstarlet in XML schreiben
xmlstarlet ed -L \
    -u "//admin_console/username" -v "$ADMIN_USER" \
    -u "//admin_console/password" -v "$ADMIN_PASSWORD" \
    "${CONFIG_DEST}" 2>/dev/null && echo "[DEBUG] xmlstarlet OK" || echo "[DEBUG] xmlstarlet FEHLER"

echo "[DEBUG] admin_console/username nach Update: '$(xmlstarlet sel -t -v "//admin_console/username" "${CONFIG_DEST}" 2>/dev/null)'"

# Env-Vars (offizielle Methode, Fallback)
export domain="$DOMAIN"
export username="$ADMIN_USER"
export password="$ADMIN_PASSWORD"
[ -n "$DOMAIN1" ] && export server_name="$DOMAIN1"
[ -n "$EXTRA_PARAMS" ] && export extra_params="$EXTRA_PARAMS"

echo "[INFO] Starte Collabora Online mit --o:admin_console.username=${ADMIN_USER}"

# --o: Args via $@ → erscheinen garantiert in coolwsd (non-default values) Log
exec /start-collabora-online.sh \
    --o:admin_console.username="$ADMIN_USER" \
    --o:admin_console.password="$ADMIN_PASSWORD"
