#!/bin/bash
set -e

# Read HA options — runs as cool user, /data/options.json is world-readable (644)
NEXTCLOUD_URL=$(jq -r '.nextcloud_url // ""' /data/options.json)
ALIASGROUP1=$(jq -r '.aliasgroup1 // ""' /data/options.json)
DOMAIN1=$(jq -r '.domain1 // ""' /data/options.json)
ADMIN_USER=$(jq -r '.admin_user // "admin"' /data/options.json)
ADMIN_PASSWORD=$(jq -r '.admin_password // ""' /data/options.json)
EXTRA_PARAMS=$(jq -r '.extra_params // ""' /data/options.json)

# aliasgroup1 (explicit domain regex) takes priority over nextcloud_url
if [ -n "$ALIASGROUP1" ]; then
    DOMAIN="$ALIASGROUP1"
else
    # Extract hostname/IP from URL and escape dots for Collabora regex
    # e.g. "https://192.168.1.100:7443" -> "192\.168\.1\.100"
    DOMAIN=$(echo "$NEXTCLOUD_URL" | sed -E 's|https?://||; s|/.*||; s|:[0-9]+||; s/\./\\./g')
fi

export domain="$DOMAIN"

# domain1 = Collabora's own public hostname (server_name), needed for reverse proxy
if [ -n "$DOMAIN1" ]; then
    export server_name="$DOMAIN1"
fi

# Build extra_params — pass admin credentials as --o: command-line overrides to coolwsd
# This bypasses coolwsd.xml entirely and works regardless of file permissions
PARAMS="${EXTRA_PARAMS:---o:ssl.enable=false --o:net.proto=IPv4}"
if [ -n "$ADMIN_USER" ]; then
    PARAMS="${PARAMS} --o:admin_console.username=${ADMIN_USER}"
fi
if [ -n "$ADMIN_PASSWORD" ]; then
    PARAMS="${PARAMS} --o:admin_console.password=${ADMIN_PASSWORD}"
fi
export extra_params="$PARAMS"
echo "[INFO] Admin credentials configured for: $ADMIN_USER"

echo "[INFO] Starting Collabora Online..."
echo "[INFO] Allowed domain: $DOMAIN"
[ -n "$DOMAIN1" ] && echo "[INFO] Server name: $DOMAIN1"

exec /start-collabora-online.sh
