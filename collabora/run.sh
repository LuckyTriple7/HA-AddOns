#!/bin/bash
set -e

# Read HA options
NEXTCLOUD_URL=$(jq -r '.nextcloud_url // ""' /data/options.json)
ALIASGROUP1=$(jq -r '.aliasgroup1 // ""' /data/options.json)
DOMAIN1=$(jq -r '.domain1 // ""' /data/options.json)
ADMIN_USER=$(jq -r '.admin_user // "admin"' /data/options.json)
ADMIN_PASSWORD=$(jq -r '.admin_password // ""' /data/options.json)
EXTRA_PARAMS=$(jq -r '.extra_params // ""' /data/options.json)

if [ -n "$ALIASGROUP1" ]; then
    DOMAIN="$ALIASGROUP1"
else
    # Extract hostname/IP from URL and escape dots for Collabora regex
    DOMAIN=$(echo "$NEXTCLOUD_URL" | sed -E 's|https?://||; s|/.*||; s|:[0-9]+||; s/\./\\./g')
fi

# coolwsd.xml nach /config persistieren und per Symlink einbinden
if [ ! -f /config/coolwsd.xml ]; then
    cp /etc/coolwsd/coolwsd.xml /config/coolwsd.xml
fi
ln -sf /config/coolwsd.xml /etc/coolwsd/coolwsd.xml

# Env vars für --use-env-vars (Ansatz 1)
export domain="$DOMAIN"
export username="$ADMIN_USER"
export password="$ADMIN_PASSWORD"
export extra_params="${EXTRA_PARAMS:---o:ssl.enable=false --o:net.proto=IPv4}"
[ -n "$DOMAIN1" ] && export server_name="$DOMAIN1"

echo "[INFO] Starting Collabora Online..."
echo "[INFO] Admin user: $ADMIN_USER"
echo "[INFO] Allowed domain: $DOMAIN"
[ -n "$DOMAIN1" ] && echo "[INFO] Server name: $DOMAIN1"

# Credentials via $@ (Ansatz 2): start script leitet "$@" direkt an coolwsd weiter
# Damit sind wir unabhängig davon ob extra_params im neuen Image funktioniert
exec /start-collabora-online.sh \
    --o:admin_console.username="${ADMIN_USER}" \
    --o:admin_console.password="${ADMIN_PASSWORD}"
