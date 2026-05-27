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

# Runtime-Berechtigungen setzen (wie alexbelgium — läuft als root)
chown -R 1001 /opt/cool/systemplate
chown -R 1001 /etc/coolwsd

# Netzwerk-Dateien in Systemplate aktualisieren (wie alexbelgium)
if [ -d "/opt/cool/systemplate/etc" ]; then
    cp /etc/hosts /opt/cool/systemplate/etc/hosts
    cp /etc/resolv.conf /opt/cool/systemplate/etc/resolv.conf
    cp /etc/hostname /opt/cool/systemplate/etc/hostname 2>/dev/null || true
fi

# coolwsd.xml nach /config persistieren (wie alexbelgium: mv + symlink)
COOL_CONFIG="/etc/coolwsd/coolwsd.xml"
CONFIG_DEST="/config/coolwsd.xml"
if [ ! -f "${CONFIG_DEST}" ]; then
    mv "${COOL_CONFIG}" "${CONFIG_DEST}"
else
    rm -f "${COOL_CONFIG}"
fi
ln -sf "${CONFIG_DEST}" "${COOL_CONFIG}"

# Env-Vars setzen — exakt wie docker run -e domain=... -e username=... -e password=...
export domain="$DOMAIN"
export username="$ADMIN_USER"
export password="$ADMIN_PASSWORD"
[ -n "$DOMAIN1" ] && export server_name="$DOMAIN1"
[ -n "$EXTRA_PARAMS" ] && export extra_params="$EXTRA_PARAMS"

echo "[DEBUG] domain='${domain}' username='${username}' password_gesetzt=$([ -n "$password" ] && echo ja || echo NEIN)"
echo "[INFO] Starte Collabora Online..."

# su -p: preserve env-vars beim Wechsel zu cool (uid 1001) — wie alexbelgium
su -p -s /bin/bash "$(getent passwd 1001 | cut -d: -f1)" -c "/start-collabora-online.sh"
