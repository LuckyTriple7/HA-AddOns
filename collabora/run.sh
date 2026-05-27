#!/bin/bash
set -e

# Read HA options
ADMIN_USER=$(jq -r '.admin_user // "admin"' /data/options.json)
ADMIN_PASSWORD=$(jq -r '.admin_password // ""' /data/options.json)
NEXTCLOUD_URL=$(jq -r '.nextcloud_url // ""' /data/options.json)
ALIASGROUP1=$(jq -r '.aliasgroup1 // ""' /data/options.json)
DOMAIN1=$(jq -r '.domain1 // ""' /data/options.json)
EXTRA_PARAMS=$(jq -r '.extra_params // ""' /data/options.json)

echo "[INFO] admin_user='${ADMIN_USER}' password_set=$([ -n "$ADMIN_PASSWORD" ] && echo yes || echo NO)"

# Domain ermitteln
if [ -n "$ALIASGROUP1" ]; then
    DOMAIN="$ALIASGROUP1"
else
    DOMAIN=$(echo "$NEXTCLOUD_URL" | sed -E 's|https?://||; s|/.*||; s|:[0-9]+||; s/\./\\./g')
fi
echo "[INFO] domain='${DOMAIN}'"

# coolwsd.xml nach /config persistieren
COOL_CONFIG="/etc/coolwsd/coolwsd.xml"
CONFIG_DEST="/config/coolwsd.xml"
if [ ! -f "${CONFIG_DEST}" ]; then
    echo "[INFO] Copying coolwsd.xml to /config..."
    cp "${COOL_CONFIG}" "${CONFIG_DEST}"
fi
ln -sf "${CONFIG_DEST}" "${COOL_CONFIG}"

# Admin-Passwort via coolconfig setzen — hasht das Passwort korrekt (Klartext funktioniert nicht)
# Username-Prompt konsumiert erste Zeile → leere Zeile voranstellen damit Default (arg) genommen wird
if [ -n "$ADMIN_PASSWORD" ]; then
    echo "[INFO] Setting admin credentials via coolconfig..."
    printf '\n%s\n%s\n' "$ADMIN_PASSWORD" "$ADMIN_PASSWORD" | coolconfig set-admin-password "$ADMIN_USER" \
        && echo "[INFO] coolconfig: credentials set OK" \
        || echo "[WARN] coolconfig failed"
fi

# Env-Vars für domain (offizielle Docker-Methode)
export domain="$DOMAIN"
export username="$ADMIN_USER"
export password="$ADMIN_PASSWORD"
[ -n "$DOMAIN1" ] && export server_name="$DOMAIN1"
[ -n "$EXTRA_PARAMS" ] && export extra_params="$EXTRA_PARAMS"

# ttyd Web-Terminal im Hintergrund starten (Ingress)
/usr/local/bin/ttyd --port 7682 --writable --ping-interval 30 sh &
TTYD_PID=$!
sleep 1
if kill -0 $TTYD_PID 2>/dev/null; then
    echo "[INFO] ttyd gestartet (PID $TTYD_PID)"
else
    echo "[WARN] ttyd konnte nicht gestartet werden"
fi

echo "[INFO] Starting Collabora Online..."
exec su -p -s /bin/sh cool -c "exec /start-collabora-online.sh"
