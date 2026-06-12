#!/bin/sh
# Läuft am Ende von linuxservers init-nextcloud-config — occ ist bereit, config.php existiert
OPTIONS=/data/options.json
OCC=/app/www/public/occ
CONFIG_PHP=/config/www/nextcloud/config/config.php

# Wie alexbelgium: nur wenn installiert
if ! grep -q "'installed' => true" "$CONFIG_PHP" 2>/dev/null; then
    echo "[ha-config] [$(date '+%Y-%m-%d %H:%M:%S')] Nextcloud noch nicht installiert — bitte Web-Installer aufrufen und Add-on neu starten"
    exit 0
fi

echo "[ha-config] [$(date '+%Y-%m-%d %H:%M:%S')] Nextcloud installiert — wende HA-Konfiguration an ..."

TRUSTED_DOMAINS=$(jq -r '.trusted_domains // ""' "$OPTIONS" 2>/dev/null || echo "")
TRUSTED_PROXIES=$(jq -r '.trusted_proxies // "172.30.32.0/23"' "$OPTIONS" 2>/dev/null || echo "172.30.32.0/23")
DEFAULT_PHONE_REGION=$(jq -r '.default_phone_region // "DE"' "$OPTIONS" 2>/dev/null || echo "DE")
ENABLE_THUMBNAILS=$(jq -r '.enable_thumbnails // true' "$OPTIONS" 2>/dev/null || echo "true")
DISABLE_UPDATES=$(jq -r '.disable_updates // false' "$OPTIONS" 2>/dev/null || echo "false")
LOGLEVEL=$(jq -r '.loglevel // 3' "$OPTIONS" 2>/dev/null || echo 3)
SKELETONDIR=$(jq -r '.skeletondirectory // ""' "$OPTIONS" 2>/dev/null || echo "")
TRASHBIN=$(jq -r '.trashbin_retention_obligation // "auto, 30"' "$OPTIONS" 2>/dev/null || echo "auto, 30")
VERSIONS=$(jq -r '.versions_retention_obligation // "auto, 30"' "$OPTIONS" 2>/dev/null || echo "auto, 30")

occ() { s6-setuidgid abc php "$OCC" "$@" || true; }

# Trusted domains — wie alexbelgium
occ config:system:set trusted_domains 0 --value="localhost"
occ config:system:set trusted_domains 1 --value="homeassistant.local"
IDX=2
if [ -n "$TRUSTED_DOMAINS" ]; then
    echo "$TRUSTED_DOMAINS" | tr ',' '\n' | while IFS= read -r D; do
        D=$(echo "$D" | tr -d ' \r')
        [ -z "$D" ] && continue
        echo "[ha-config] [$(date '+%Y-%m-%d %H:%M:%S')] trusted_domain ${IDX}: ${D}"
        s6-setuidgid abc php "$OCC" config:system:set trusted_domains $IDX --value="$D" || true
        IDX=$((IDX + 1))
    done
fi

# Trusted proxies (Reverse Proxy / NGINX)
occ config:system:delete trusted_proxies || true
PIDX=0
if [ -n "$TRUSTED_PROXIES" ]; then
    echo "$TRUSTED_PROXIES" | tr ',' '\n' | while IFS= read -r P; do
        P=$(echo "$P" | tr -d ' \r')
        [ -z "$P" ] && continue
        occ config:system:set trusted_proxies $PIDX --value="$P"
        PIDX=$((PIDX + 1))
    done
fi
occ config:system:set forwarded_for_headers 0 --value="HTTP_X_FORWARDED_FOR"

occ config:system:set default_phone_region --value="$DEFAULT_PHONE_REGION"
occ config:system:set default_language --value="de"
occ config:system:set default_locale --value="de_DE"
occ config:system:set loglevel --type=integer --value="$LOGLEVEL"
occ config:system:set skeletondirectory --value="$SKELETONDIR"
occ config:system:set trashbin_retention_obligation --value="$TRASHBIN"
occ config:system:set versions_retention_obligation --value="$VERSIONS"
MAINTENANCE_WINDOW=$(jq -r '.maintenance_window_start // 1' "$OPTIONS" 2>/dev/null || echo 1)
occ config:system:set maintenance_window_start --type=integer --value="$MAINTENANCE_WINDOW"
occ maintenance:repair --include-expensive

if [ "$ENABLE_THUMBNAILS" = "true" ]; then
    occ config:system:set enable_previews --value=true --type=boolean
    occ config:system:set enabledPreviewProviders 0  --value="OC\\Preview\\TXT"
    occ config:system:set enabledPreviewProviders 1  --value="OC\\Preview\\MarkDown"
    occ config:system:set enabledPreviewProviders 2  --value="OC\\Preview\\OpenDocument"
    occ config:system:set enabledPreviewProviders 3  --value="OC\\Preview\\PDF"
    occ config:system:set enabledPreviewProviders 4  --value="OC\\Preview\\MSOffice2003"
    occ config:system:set enabledPreviewProviders 5  --value="OC\\Preview\\MSOfficeDoc"
    occ config:system:set enabledPreviewProviders 6  --value="OC\\Preview\\Image"
    occ config:system:set enabledPreviewProviders 7  --value="OC\\Preview\\Photoshop"
    occ config:system:set enabledPreviewProviders 8  --value="OC\\Preview\\TIFF"
    occ config:system:set enabledPreviewProviders 9  --value="OC\\Preview\\SVG"
    occ config:system:set enabledPreviewProviders 10 --value="OC\\Preview\\Font"
    occ config:system:set enabledPreviewProviders 11 --value="OC\\Preview\\MP3"
    occ config:system:set enabledPreviewProviders 12 --value="OC\\Preview\\Movie"
    occ config:system:set enabledPreviewProviders 13 --value="OC\\Preview\\MKV"
    occ config:system:set enabledPreviewProviders 14 --value="OC\\Preview\\MP4"
    occ config:system:set enabledPreviewProviders 15 --value="OC\\Preview\\AVI"
else
    occ config:system:set enable_previews --value=false --type=boolean
    occ config:system:delete enabledPreviewProviders || true
fi

if [ "$DISABLE_UPDATES" = "true" ]; then
    occ config:system:set upgrade.disable-web --value=true --type=boolean
fi

# SMB-Shares als externen Speicher einbinden (nur einmalig nach Erstinstall)
FLAG=/config/data/.smb_registered
if [ ! -f "$FLAG" ]; then
    occ app:enable files_external
    for IDX in 1 2 3; do
        if mountpoint -q "/mnt/smb${IDX}" 2>/dev/null; then
            SHARE=$(jq -r ".smb_${IDX}_share // empty" "$OPTIONS" 2>/dev/null)
            echo "[ha-config] [$(date '+%Y-%m-%d %H:%M:%S')] Registriere SMB-${IDX} (${SHARE}) als externen Speicher ..."
            occ files_external:create "SMB-${IDX} ${SHARE}" local null::null \
                --config datadir="/mnt/smb${IDX}"
        fi
    done
    touch "$FLAG"
fi

echo "[ha-config] [$(date '+%Y-%m-%d %H:%M:%S')] Fertig"
