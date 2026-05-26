#!/bin/bash
set -e

# Read HA options
NEXTCLOUD_URL=$(jq -r '.nextcloud_url // ""' /data/options.json)
ALIASGROUP1=$(jq -r '.aliasgroup1 // ""' /data/options.json)
DOMAIN1=$(jq -r '.domain1 // ""' /data/options.json)
ADMIN_USER=$(jq -r '.admin_user // "admin"' /data/options.json)
ADMIN_PASSWORD=$(jq -r '.admin_password // ""' /data/options.json)
EXTRA_PARAMS=$(jq -r '.extra_params // ""' /data/options.json)

# aliasgroup1 takes priority over nextcloud_url
if [ -n "$ALIASGROUP1" ]; then
    DOMAIN="$ALIASGROUP1"
else
    # Extract hostname/IP from URL and escape dots for Collabora regex
    # e.g. "https://192.168.1.100:7443" -> "192\.168\.1\.100"
    DOMAIN=$(echo "$NEXTCLOUD_URL" | sed -E 's|https?://||; s|/.*||; s|:[0-9]+||; s/\./\\./g')
fi

# These env vars are read by coolwsd --use-env-vars (COOLWSD.cpp: initializeEnvOptions)
# username -> admin_console.username, password -> admin_console.password
export domain="$DOMAIN"
export username="$ADMIN_USER"
export password="$ADMIN_PASSWORD"

if [ -n "$DOMAIN1" ]; then
    export server_name="$DOMAIN1"
fi

# Also pass credentials via --o: override as belt-and-suspenders
PARAMS="${EXTRA_PARAMS:---o:ssl.enable=false --o:net.proto=IPv4}"
[ -n "$ADMIN_USER" ]     && PARAMS="$PARAMS --o:admin_console.username=$ADMIN_USER"
[ -n "$ADMIN_PASSWORD" ] && PARAMS="$PARAMS --o:admin_console.password=$ADMIN_PASSWORD"
export extra_params="$PARAMS"

echo "[INFO] Starting Collabora Online..."
echo "[INFO] Allowed domain: $DOMAIN"
echo "[INFO] Admin user: $ADMIN_USER"
[ -n "$DOMAIN1" ] && echo "[INFO] Server name: $DOMAIN1"

exec /start-collabora-online.sh
