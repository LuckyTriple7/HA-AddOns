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

# Exakt wie: docker run -e domain=... -e username=... -e password=... collabora/code
export domain="$DOMAIN"
export username="$ADMIN_USER"
export password="$ADMIN_PASSWORD"
[ -n "$DOMAIN1" ] && export server_name="$DOMAIN1"
[ -n "$EXTRA_PARAMS" ] && export extra_params="$EXTRA_PARAMS"

echo "[DEBUG] Env-Vars gesetzt: domain='${domain}' username='${username}' password_gesetzt=$([ -n "$password" ] && echo ja || echo NEIN)"
echo "[INFO] Starte Collabora Online..."

exec /start-collabora-online.sh
