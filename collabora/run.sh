#!/bin/bash
# Root-Init des Add-ons. Bereitet Config, systemplate und Rechte vor und startet
# coolwsd anschließend abgesenkt als uid 1001 über /usr/local/bin/collabora-run.sh.
set -e

log()  { echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
warn() { echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Read HA options
ADMIN_USER=$(jq -r '.admin_user // "admin"' /data/options.json)
ADMIN_PASSWORD=$(jq -r '.admin_password // ""' /data/options.json)
NEXTCLOUD_URL=$(jq -r '.nextcloud_url // ""' /data/options.json)
ALIASGROUP1=$(jq -r '.aliasgroup1 // ""' /data/options.json)
DOMAIN1=$(jq -r '.domain1 // ""' /data/options.json)
EXTRA_PARAMS=$(jq -r '.extra_params // ""' /data/options.json)
TZ=$(jq -r '.TZ // "Europe/Berlin"' /data/options.json)

log "admin_user='${ADMIN_USER}' password_set=$([ -n "$ADMIN_PASSWORD" ] && echo yes || echo NO)"

# coolwsd wertet storage.wopi.alias_groups als reguläre Ausdrücke aus, jeder Punkt
# muss also genau einmal escaped sein. Der Wert wird aber von Hand in die Add-on-
# Optionen getippt, wo gar keine oder doppelte Backslashes leicht passieren — und
# ein falsches Muster matcht stillschweigend nie. Alle drei Schreibweisen
# akzeptieren und coolwsd immer die kanonische Form geben.
normalise_wopi_host() {
    local value="$1"
    # Enthält der Wert Regex-Metazeichen, wusste jemand was er tut — unverändert lassen.
    if [[ "$value" == *[\]\[\(\)\{\}\|\*\+\?\^\$]* ]]; then
        printf '%s' "$value"
        return
    fi
    value="${value//\\/}"   # vorhandenes Escaping in beliebiger Tiefe entfernen
    value="${value//./\\.}" # jeden Punkt genau einmal escapen
    printf '%s' "$value"
}

# server_name ist ein literaler "hostname[:port]", keine Regex und keine URL.
normalise_server_name() {
    local value="$1"
    value="${value//\\/}"
    value="${value#*://}"
    value="${value%%/*}"
    printf '%s' "$value"
}

# Erlaubten WOPI-Host ermitteln: aliasgroup1 schlägt nextcloud_url.
# aliasgroup1 erwartet eine vollständige URL (scheme://host[:port]), das ältere
# domain-Env dagegen nur den Hostnamen — beides aus derselben Eingabe ableiten.
RAW_HOST="${ALIASGROUP1:-$NEXTCLOUD_URL}"
ALIASGROUP=""
DOMAIN=""

if [ -z "$RAW_HOST" ]; then
    warn "Weder nextcloud_url noch aliasgroup1 gesetzt — Collabora akzeptiert keinen WOPI-Host"
elif [[ "$RAW_HOST" == *[\]\[\(\)\{\}\|\*\+\?\^\$]* ]]; then
    # Handgeschriebene Regex: unverändert durchreichen.
    ALIASGROUP="$RAW_HOST"
    DOMAIN="$RAW_HOST"
else
    [[ "$RAW_HOST" != *://* ]] && RAW_HOST="https://${RAW_HOST}"
    SCHEME="${RAW_HOST%%://*}"
    HOST_ONLY=$(normalise_server_name "$RAW_HOST")
    ALIASGROUP="${SCHEME}://$(normalise_wopi_host "$HOST_ONLY")"
    DOMAIN=$(normalise_wopi_host "${HOST_ONLY%%:*}")
fi
log "aliasgroup1='${ALIASGROUP}' domain='${DOMAIN}'"

###############################################################################
# coolwsd.xml nach /config persistieren
#
# Die Config gehört zum Image: nach einem Collabora-Update passt eine alte, aus
# einer früheren Version persistierte coolwsd.xml womöglich nicht mehr zum neuen
# coolwsd. Deshalb die unberührte Referenz aus dem Image (coolwsd.xml.dist) per
# Prüfsumme verfolgen und die persistierte Kopie rotieren, sobald sie sich ändert.
###############################################################################
COOL_CONFIG="/etc/coolwsd/coolwsd.xml"
CONFIG_DEST="/config/coolwsd.xml"
PRISTINE="/etc/coolwsd/coolwsd.xml.dist"
STAMP="/config/.coolwsd-xml-dist.sha256"

mkdir -p /config
DIST_SUM=$(sha256sum "$PRISTINE" | cut -d' ' -f1)

if [ -f "$CONFIG_DEST" ] && [ "$(cat "$STAMP" 2>/dev/null)" != "$DIST_SUM" ]; then
    BACKUP="${CONFIG_DEST}.bak-$(date '+%Y%m%d-%H%M%S')"
    mv "$CONFIG_DEST" "$BACKUP"
    warn "Image bringt eine neue coolwsd.xml mit — bisherige Config gesichert nach ${BACKUP}"
    warn "Eigene Anpassungen ggf. von Hand aus dem Backup übernehmen."
fi

if [ ! -f "$CONFIG_DEST" ]; then
    log "Kopiere coolwsd.xml nach /config..."
    cp "$PRISTINE" "$CONFIG_DEST"
fi
chown root:root "$CONFIG_DEST"
chmod 644 "$CONFIG_DEST"
echo "$DIST_SUM" > "$STAMP"

rm -f "$COOL_CONFIG"
ln -sf "$CONFIG_DEST" "$COOL_CONFIG"

# Bind-Mount im Container nicht möglich (HA-Add-ons bekommen kein CAP_SYS_ADMIN),
# mount_jail_tree dauerhaft deaktivieren -> coolwsd kopiert die Child-Roots.
sed -i 's|<mount_jail_tree\([^>]*\)>true</mount_jail_tree>|<mount_jail_tree\1>false</mount_jail_tree>|' "$CONFIG_DEST" \
    && log "mount_jail_tree=false" \
    || warn "mount_jail_tree konnte nicht gesetzt werden"

# Zeitzone setzen
log "Timezone: ${TZ}"
echo "$TZ" > /etc/timezone
ln -sf "/usr/share/zoneinfo/${TZ}" /etc/localtime 2>/dev/null || true
export TZ

# systemplate: DNS-/Host-Dateien und Zeitzone hineinkopieren, sonst spammt
# coolwsd WRN-Zeilen und die Kit-Prozesse haben keine Namensauflösung.
SYSTEMPLATE_DIR="/opt/cool/systemplate/etc"
if [ -d "$SYSTEMPLATE_DIR" ]; then
    cp /etc/hosts       "${SYSTEMPLATE_DIR}/hosts"       2>/dev/null || true
    cp /etc/hostname    "${SYSTEMPLATE_DIR}/hostname"    2>/dev/null || true
    cp /etc/resolv.conf "${SYSTEMPLATE_DIR}/resolv.conf" 2>/dev/null || true
    cp /etc/timezone    "${SYSTEMPLATE_DIR}/timezone"    2>/dev/null || true
else
    warn "/opt/cool/systemplate/etc fehlt — Jail-Setup könnte scheitern"
fi
chown -R 1001 /opt/cool/systemplate /etc/coolwsd
chmod -R 755 /opt/cool/systemplate

# Env-Vars für coolwsd --use-env-vars. "domain" ist der Legacy-Name, aliasgroup1
# der aktuelle — beide setzen, damit es über Collabora-Versionen hinweg greift.
export domain="$DOMAIN"
export aliasgroup1="$ALIASGROUP"
export username="$ADMIN_USER"
export password="$ADMIN_PASSWORD"
[ -n "$DOMAIN1" ] && export server_name="$(normalise_server_name "$DOMAIN1")"
[ -n "$EXTRA_PARAMS" ] && export extra_params="$EXTRA_PARAMS"

# ttyd Web-Terminal im Hintergrund starten (Ingress)
/usr/local/bin/ttyd --port 7682 --writable --ping-interval 30 bash &
TTYD_PID=$!
sleep 1
if kill -0 $TTYD_PID 2>/dev/null; then
    log "ttyd gestartet (PID $TTYD_PID)"
else
    warn "ttyd konnte nicht gestartet werden"
fi

log "Starting Collabora Online..."

# SIGTERM-Handler: sauber beenden statt exit 143
_term() {
    log "SIGTERM empfangen, stoppe Collabora..."
    kill -TERM "$COOLWSD_PID" 2>/dev/null || true
    kill -TERM "$TTYD_PID"    2>/dev/null || true
    wait "$COOLWSD_PID" 2>/dev/null || true
    exit 0
}
trap _term SIGTERM SIGINT

# coolwsd verweigert den Betrieb als root. Das offizielle Image lieferte früher
# /start-collabora-online.sh; seit dem Distroless-Umbau gibt es das nicht mehr,
# deshalb bringt das Add-on seinen eigenen Launcher mit. su -p erhält die Umgebung.
export HOME=/opt/cool
su -p -s /bin/bash cool -c /usr/local/bin/collabora-run.sh &
COOLWSD_PID=$!
wait $COOLWSD_PID
