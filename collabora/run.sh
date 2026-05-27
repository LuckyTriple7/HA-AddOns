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

# coolwsd.xml nach /config persistieren (mv + symlink wie alexbelgium)
COOL_CONFIG="/etc/coolwsd/coolwsd.xml"
CONFIG_DEST="/config/coolwsd.xml"
if [ ! -f "${CONFIG_DEST}" ]; then
    echo "[DEBUG] Kopiere coolwsd.xml nach /config..."
    cp "${COOL_CONFIG}" "${CONFIG_DEST}"
fi
ln -sf "${CONFIG_DEST}" "${COOL_CONFIG}"

# Credentials direkt in coolwsd.xml schreiben — garantiert zuverlässig
echo "[DEBUG] Schreibe Credentials in coolwsd.xml..."
xmlstarlet ed -L \
    -u "//admin_console/username" -v "$ADMIN_USER" \
    -u "//admin_console/password" -v "$ADMIN_PASSWORD" \
    "${CONFIG_DEST}"

# Verifikation — muss im HA Add-on Log erscheinen
XML_USER=$(xmlstarlet sel -t -v "//admin_console/username" "${CONFIG_DEST}" 2>/dev/null || echo "FEHLER")
XML_PASS_SET=$(xmlstarlet sel -t -v "//admin_console/password" "${CONFIG_DEST}" 2>/dev/null | grep -q . && echo "ja" || echo "NEIN")
echo "[DEBUG] XML username='${XML_USER}' password_gesetzt=${XML_PASS_SET}"

# Env-Vars zusätzlich setzen (offizielle Methode, Fallback)
export domain="$DOMAIN"
export username="$ADMIN_USER"
export password="$ADMIN_PASSWORD"
[ -n "$DOMAIN1" ] && export server_name="$DOMAIN1"
[ -n "$EXTRA_PARAMS" ] && export extra_params="$EXTRA_PARAMS"

echo "[INFO] Starte Collabora Online..."

exec /start-collabora-online.sh
