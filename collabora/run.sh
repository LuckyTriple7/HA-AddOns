#!/bin/sh
set -e

# Read HA options
ADMIN_USER=$(jq -r '.admin_user // "admin"' /data/options.json)
ADMIN_PASSWORD=$(jq -r '.admin_password // ""' /data/options.json)
NEXTCLOUD_URL=$(jq -r '.nextcloud_url // ""' /data/options.json)
ALIASGROUP1=$(jq -r '.aliasgroup1 // ""' /data/options.json)
DOMAIN1=$(jq -r '.domain1 // ""' /data/options.json)
EXTRA_PARAMS=$(jq -r '.extra_params // ""' /data/options.json)
TZ=$(jq -r '.TZ // "Europe/Berlin"' /data/options.json)

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] admin_user='${ADMIN_USER}' password_set=$([ -n "$ADMIN_PASSWORD" ] && echo yes || echo NO)"

# Domain ermitteln
if [ -n "$ALIASGROUP1" ]; then
    DOMAIN="$ALIASGROUP1"
else
    DOMAIN=$(echo "$NEXTCLOUD_URL" | sed -E 's|https?://||; s|/.*||; s|:[0-9]+||; s/\./\\./g')
fi
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] domain='${DOMAIN}'"

# coolwsd.xml nach /config persistieren
# Seit collabora/code 26.04.2.2 (Nix-Image) ist /etc/coolwsd/ selbst nicht mehr
# beschreibbar (root-owned, User läuft als nonroot/1001) — ein Symlink-Austausch
# wie früher geht daher nicht mehr. Die Datei coolwsd.xml selbst gehört aber 1001,
# ist also direkt überschreibbar (Inhalt kopieren statt verlinken).
COOL_CONFIG="/etc/coolwsd/coolwsd.xml"
CONFIG_DEST="/config/coolwsd.xml"
if [ -f "${CONFIG_DEST}" ]; then
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Restoring coolwsd.xml from /config..."
    cp "${CONFIG_DEST}" "${COOL_CONFIG}" \
        || echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] coolwsd.xml restore fehlgeschlagen"
else
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Copying coolwsd.xml to /config..."
    cp "${COOL_CONFIG}" "${CONFIG_DEST}" \
        || echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] coolwsd.xml seed fehlgeschlagen"
fi

# systemplate DNS-Dateien kopieren → eliminiert WRN-Spam ("systemplate is read-only")
# systemplate ist im Nix-Image root-owned -> schlägt i.d.R. lautlos fehl, kein Problem
cp /etc/hosts /opt/cool/systemplate/etc/hosts 2>/dev/null || true
cp /etc/resolv.conf /opt/cool/systemplate/etc/resolv.conf 2>/dev/null || true

# WOPI proof key generieren falls nicht vorhanden
# coolconfig gibt es im Nix-Image nicht mehr -> per openssl (im Image vorhanden) selbst
# erzeugen. /etc/coolwsd/ ist meist nicht beschreibbar (neue Datei anlegen scheitert dann) —
# WOPI-Signierung bleibt in dem Fall deaktiviert (nur ein WRN im Log, kein Fehlschlag).
if [ ! -f /etc/coolwsd/proof_key ]; then
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Generating WOPI proof key..."
    openssl genrsa -out /etc/coolwsd/proof_key 2048 2>/dev/null \
        && echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] proof key generated" \
        || echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] proof key generation failed (read-only /etc/coolwsd?)"
fi

# Zeitzone setzen und in systemplate kopieren
# /etc/ ist im Nix-Image root-owned -> /etc/timezone kann nicht neu angelegt werden,
# TZ-Env-Var reicht für coolwsd selbst; systemplate-Kopie bleibt best effort.
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Timezone: ${TZ}"
export TZ
echo "$TZ" > /opt/cool/systemplate/etc/timezone 2>/dev/null || true

# Admin-Zugangsdaten + Domain: offizieller Docker-Mechanismus über Env-Vars + --use-env-vars
# (coolconfig set-admin-password gibt es im Nix-Image nicht mehr, ist aber auch nicht nötig)
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
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] ttyd gestartet (PID $TTYD_PID)"
else
    echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] ttyd konnte nicht gestartet werden"
fi

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Starting Collabora Online..."

# SIGTERM-Handler: sauber beenden statt exit 143
_term() {
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] SIGTERM empfangen, stoppe Collabora..."
    kill -TERM "$COOLWSD_PID" 2>/dev/null || true
    kill -TERM "$TTYD_PID"    2>/dev/null || true
    wait "$COOLWSD_PID" 2>/dev/null || true
    exit 0
}
trap _term SIGTERM SIGINT

# Kein "cool"-User/su mehr nötig — Container läuft im Nix-Image bereits als nonroot (1001).
# Flags entsprechen dem Original-Entrypoint des Base-Images, ergänzt um
# mount_jail_tree=false (Bind-Mount im Container nicht möglich).
/usr/bin/coolwsd \
    --use-env-vars \
    --o:sys_template_path=/opt/cool/systemplate \
    --o:child_root_path=/opt/cool/child-roots \
    --o:file_server_root_path=/usr/share/coolwsd \
    --o:cache_files.path=/opt/cool/cache \
    --o:logging.color=false \
    --o:stop_on_config_change=true \
    --o:mount_jail_tree=false &
COOLWSD_PID=$!
wait $COOLWSD_PID
