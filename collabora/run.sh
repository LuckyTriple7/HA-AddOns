#!/bin/bash
set -e

NEXTCLOUD_URL=$(jq -r '.nextcloud_url // ""' /data/options.json)
ADMIN_USER=$(jq -r '.admin_user // "admin"' /data/options.json)
ADMIN_PASSWORD=$(jq -r '.admin_password // ""' /data/options.json)
EXTRA_PARAMS=$(jq -r '.extra_params // ""' /data/options.json)

# Extract hostname/IP from URL and escape dots for Collabora regex
# e.g. "https://192.168.1.100:7443" -> "192\.168\.1\.100"
DOMAIN=$(echo "$NEXTCLOUD_URL" | sed -E 's|https?://||; s|/.*||; s|:[0-9]+||; s/\./\\./g')

export domain="$DOMAIN"
export username="$ADMIN_USER"
export password="$ADMIN_PASSWORD"
export extra_params="${EXTRA_PARAMS:---o:ssl.enable=false --o:net.proto=IPv4}"

echo "[INFO] Starting Collabora Online..."
echo "[INFO] Allowed domain: $DOMAIN"

exec /start-collabora-online.sh
