#!/bin/bash
set -e

echo "[DEBUG] run.sh gestartet, User: $(id)"

# Read HA options
NEXTCLOUD_URL=$(jq -r '.nextcloud_url // ""' /data/options.json)
ALIASGROUP1=$(jq -r '.aliasgroup1 // ""' /data/options.json)
DOMAIN1=$(jq -r '.domain1 // ""' /data/options.json)
ADMIN_USER=$(jq -r '.admin_user // "admin"' /data/options.json)
ADMIN_PASSWORD=$(jq -r '.admin_password // ""' /data/options.json)
EXTRA_PARAMS=$(jq -r '.extra_params // ""' /data/options.json)

echo "[DEBUG] ADMIN_USER='${ADMIN_USER}' ADMIN_PASSWORD_SET=$([ -n "$ADMIN_PASSWORD" ] && echo yes || echo NO)"
echo "[DEBUG] NEXTCLOUD_URL='${NEXTCLOUD_URL}'"

if [ -n "$ALIASGROUP1" ]; then
    DOMAIN="$ALIASGROUP1"
else
    DOMAIN=$(echo "$NEXTCLOUD_URL" | sed -E 's|https?://||; s|/.*||; s|:[0-9]+||; s/\./\\./g')
fi
echo "[DEBUG] DOMAIN='${DOMAIN}'"

# coolwsd.xml nach /config persistieren
if [ ! -f /config/coolwsd.xml ]; then
    echo "[DEBUG] Kopiere coolwsd.xml nach /config..."
    cp /etc/coolwsd/coolwsd.xml /config/coolwsd.xml
else
    echo "[DEBUG] /config/coolwsd.xml existiert bereits"
fi

# Admin-Credentials und SSL direkt in coolwsd.xml setzen — garantiert zuverlässig
echo "[DEBUG] Setze Credentials und SSL in /config/coolwsd.xml via xmlstarlet..."
xmlstarlet ed -L \
    -u "//admin_console/username" -v "$ADMIN_USER" \
    -u "//admin_console/password" -v "$ADMIN_PASSWORD" \
    -u "//ssl/enable" -v "false" \
    /config/coolwsd.xml
echo "[DEBUG] coolwsd.xml aktualisiert"

# Verify: Werte aus XML auslesen und loggen
XML_USER=$(xmlstarlet sel -t -v "//admin_console/username" /config/coolwsd.xml 2>/dev/null || echo "FEHLER")
XML_SSL=$(xmlstarlet sel -t -v "//ssl/enable" /config/coolwsd.xml 2>/dev/null || echo "FEHLER")
echo "[DEBUG] XML admin_console/username='${XML_USER}'"
echo "[DEBUG] XML ssl/enable='${XML_SSL}'"

# Symlink /etc/coolwsd/coolwsd.xml -> /config/coolwsd.xml
ln -sf /config/coolwsd.xml /etc/coolwsd/coolwsd.xml
echo "[DEBUG] Symlink gesetzt: /etc/coolwsd/coolwsd.xml -> /config/coolwsd.xml"

# Env vars für --use-env-vars (Fallback)
export username="$ADMIN_USER"
export password="$ADMIN_PASSWORD"
export domain="$DOMAIN"
[ -n "$DOMAIN1" ] && export server_name="$DOMAIN1"
[ -n "$EXTRA_PARAMS" ] && export extra_params="$EXTRA_PARAMS"

echo "[INFO] Starting Collabora Online..."
echo "[INFO] Admin user: ${ADMIN_USER}"
echo "[INFO] Allowed domain: ${DOMAIN}"
[ -n "$DOMAIN1" ] && echo "[INFO] Server name: ${DOMAIN1}"
echo "[DEBUG] exec /start-collabora-online.sh --o:admin_console.username=${ADMIN_USER} --o:admin_console.password=***"

exec /start-collabora-online.sh \
    --o:admin_console.username="$ADMIN_USER" \
    --o:admin_console.password="$ADMIN_PASSWORD"
