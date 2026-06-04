#!/bin/bash
set -e

# Read HA options
ADMIN_USER=$(jq -r '.admin_user // "admin"' /data/options.json)
ADMIN_PASSWORD=$(jq -r '.admin_password // ""' /data/options.json)
NEXTCLOUD_URL=$(jq -r '.nextcloud_url // ""' /data/options.json)
ALIASGROUP1=$(jq -r '.aliasgroup1 // ""' /data/options.json)
DOMAIN1=$(jq -r '.domain1 // ""' /data/options.json)
EXTRA_PARAMS=$(jq -r '.extra_params // ""' /data/options.json)
TZ=$(jq -r '.TZ // "Europe/Berlin"' /data/options.json)

echo "[INFO] [$(date +%H:%M:%S)] admin_user='${ADMIN_USER}' password_set=$([ -n "$ADMIN_PASSWORD" ] && echo yes || echo NO)"

# Domain ermitteln
if [ -n "$ALIASGROUP1" ]; then
    DOMAIN="$ALIASGROUP1"
else
    DOMAIN=$(echo "$NEXTCLOUD_URL" | sed -E 's|https?://||; s|/.*||; s|:[0-9]+||; s/\./\\./g')
fi
echo "[INFO] [$(date +%H:%M:%S)] domain='${DOMAIN}'"

# coolwsd.xml nach /config persistieren
COOL_CONFIG="/etc/coolwsd/coolwsd.xml"
CONFIG_DEST="/config/coolwsd.xml"
if [ ! -f "${CONFIG_DEST}" ]; then
    echo "[INFO] [$(date +%H:%M:%S)] Copying coolwsd.xml to /config..."
    cp "${COOL_CONFIG}" "${CONFIG_DEST}"
fi
ln -sf "${CONFIG_DEST}" "${COOL_CONFIG}"

# systemplate DNS-Dateien kopieren → eliminiert WRN-Spam ("systemplate is read-only")
cp /etc/hosts /opt/cool/systemplate/etc/hosts 2>/dev/null || true
cp /etc/resolv.conf /opt/cool/systemplate/etc/resolv.conf 2>/dev/null || true

# WOPI proof key generieren falls nicht vorhanden
if [ ! -f /etc/coolwsd/proof_key ]; then
    echo "[INFO] [$(date +%H:%M:%S)] Generating WOPI proof key..."
    coolconfig generate-proof-key 2>/dev/null || echo "[WARN] [$(date +%H:%M:%S)] proof key generation failed"
fi

# Zeitzone setzen und in systemplate kopieren
echo "[INFO] [$(date +%H:%M:%S)] Timezone: ${TZ}"
echo "$TZ" > /etc/timezone
export TZ
cp /etc/timezone /opt/cool/systemplate/etc/timezone 2>/dev/null || true

# Bind-Mount im Container nicht möglich → mount_jail_tree dauerhaft deaktivieren
sed -i 's|<mount_jail_tree\([^>]*\)>true</mount_jail_tree>|<mount_jail_tree\1>false</mount_jail_tree>|' "${CONFIG_DEST}" \
    && echo "[INFO] [$(date +%H:%M:%S)] mount_jail_tree=false" \
    || echo "[WARN] [$(date +%H:%M:%S)] mount_jail_tree konnte nicht gesetzt werden"

# Admin-Passwort via coolconfig setzen — hasht das Passwort korrekt (Klartext funktioniert nicht)
# Username-Prompt konsumiert erste Zeile → leere Zeile voranstellen damit Default (arg) genommen wird
if [ -n "$ADMIN_PASSWORD" ]; then
    echo "[INFO] [$(date +%H:%M:%S)] Setting admin credentials via coolconfig..."
    printf '\n%s\n%s\n' "$ADMIN_PASSWORD" "$ADMIN_PASSWORD" | coolconfig set-admin-password "$ADMIN_USER" \
        && echo "[INFO] [$(date +%H:%M:%S)] coolconfig: credentials set OK" \
        || echo "[WARN] [$(date +%H:%M:%S)] coolconfig failed"
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
    echo "[INFO] [$(date +%H:%M:%S)] ttyd gestartet (PID $TTYD_PID)"
else
    echo "[WARN] [$(date +%H:%M:%S)] ttyd konnte nicht gestartet werden"
fi

echo "[INFO] [$(date +%H:%M:%S)] Starting Collabora Online..."

# SIGTERM-Handler: sauber beenden statt exit 143
_term() {
    echo "[INFO] [$(date +%H:%M:%S)] SIGTERM empfangen, stoppe Collabora..."
    kill -TERM "$COOLWSD_PID" 2>/dev/null || true
    kill -TERM "$TTYD_PID"    2>/dev/null || true
    wait "$COOLWSD_PID" 2>/dev/null || true
    exit 0
}
trap _term SIGTERM SIGINT

su -p -s /bin/sh cool -c "exec /start-collabora-online.sh" &
COOLWSD_PID=$!
wait $COOLWSD_PID
