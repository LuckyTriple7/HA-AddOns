#!/bin/bash
set -e

# Read HA options (runs as root)
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

# Persist coolwsd.xml to /config — wie alexbelgium
if [ ! -f /config/coolwsd.xml ]; then
    cp /etc/coolwsd/coolwsd.xml /config/coolwsd.xml
    chown cool:cool /config/coolwsd.xml
fi
ln -sf /config/coolwsd.xml /etc/coolwsd/coolwsd.xml

# Env vars für coolwsd --use-env-vars (COOLWSD.cpp: initializeEnvOptions)
# username -> admin_console.username, password -> admin_console.password
export domain="$DOMAIN"
export username="$ADMIN_USER"
export password="$ADMIN_PASSWORD"
export extra_params="${EXTRA_PARAMS:---o:ssl.enable=false --o:net.proto=IPv4}"

[ -n "$DOMAIN1" ] && export server_name="$DOMAIN1"

echo "[INFO] Starting Collabora Online (as cool user via gosu)..."
echo "[INFO] Admin user: $ADMIN_USER"
echo "[INFO] Allowed domain: $DOMAIN"
[ -n "$DOMAIN1" ] && echo "[INFO] Server name: $DOMAIN1"

# Wechsel zu cool (uid 1001) mit erhaltenen Env-Vars — wie alexbelgium
exec gosu cool /start-collabora-online.sh
