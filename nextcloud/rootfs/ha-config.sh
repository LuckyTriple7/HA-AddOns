#!/bin/sh
# Läuft am Ende von linuxservers init-nextcloud-config — occ ist bereit, config.php existiert
OPTIONS=/data/options.json
OCC=/app/www/public/occ
CONFIG_PHP=/config/www/nextcloud/config/config.php

# Wie alexbelgium: nur wenn installiert
if ! grep -q "'installed' => true" "$CONFIG_PHP" 2>/dev/null; then
    echo "[ha-config] Nextcloud noch nicht installiert — bitte Web-Installer aufrufen und Add-on neu starten"
    exit 0
fi

echo "[ha-config] Nextcloud installiert — wende HA-Konfiguration an ..."

TRUSTED_DOMAINS=$(jq -r '.trusted_domains // ""' "$OPTIONS" 2>/dev/null || echo "")
DEFAULT_PHONE_REGION=$(jq -r '.default_phone_region // "DE"' "$OPTIONS" 2>/dev/null || echo "DE")
ENABLE_THUMBNAILS=$(jq -r '.enable_thumbnails // true' "$OPTIONS" 2>/dev/null || echo "true")
DISABLE_UPDATES=$(jq -r '.disable_updates // false' "$OPTIONS" 2>/dev/null || echo "false")

occ() { ALLOW_ROOT=1 php "$OCC" "$@" || true; }

# Trusted domains — wie alexbelgium
occ config:system:set trusted_domains 0 --value="localhost"
occ config:system:set trusted_domains 1 --value="homeassistant.local"
IDX=2
if [ -n "$TRUSTED_DOMAINS" ]; then
    echo "$TRUSTED_DOMAINS" | tr ',' '\n' | while IFS= read -r D; do
        D=$(echo "$D" | tr -d ' \r')
        [ -z "$D" ] && continue
        echo "[ha-config] trusted_domain ${IDX}: ${D}"
        ALLOW_ROOT=1 php "$OCC" config:system:set trusted_domains $IDX --value="$D" || true
        IDX=$((IDX + 1))
    done
fi

occ config:system:set default_phone_region --value="$DEFAULT_PHONE_REGION"

if [ "$ENABLE_THUMBNAILS" = "true" ]; then
    occ config:system:set enable_previews --value=true --type=boolean
else
    occ config:system:set enable_previews --value=false --type=boolean
fi

if [ "$DISABLE_UPDATES" = "true" ]; then
    occ config:system:set upgrade.disable-web --value=true --type=boolean
fi

echo "[ha-config] Fertig"
