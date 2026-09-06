#!/usr/bin/with-contenv bash
# Tailscale-Client: startet tailscaled und meldet den Container am Tailnet an.
#
# Laeuft absichtlich VOR 45-smb-mounts / 47-nfs-mounts, damit Freigaben ueber
# Tailnet-Adressen gemountet werden koennen.
#
# Persistenz: der komplette Tailscale-State liegt unter /config/tailscale
# (app_config-Mount). Er ueberlebt damit Add-on-Neustart, Update und
# "Neu Aufbauen" — nach der ersten Anmeldung wird nie wieder ein Auth-Key
# gebraucht, der Knoten bleibt derselbe.

OPTIONS=/data/options.json
STATE_DIR=/config/tailscale
SOCKET=/run/tailscale/tailscaled.sock
LOGFILE="${STATE_DIR}/tailscaled.log"
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

log() { echo "[tailscale] [$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

ts() { /usr/local/bin/tailscale --socket="$SOCKET" "$@"; }

ENABLED=$(jq -r '.tailscale_enabled // false' "$OPTIONS" 2>/dev/null || echo "false")
if [ "$ENABLED" != "true" ]; then
    log "Deaktiviert (tailscale_enabled=false) — uebersprungen."
    exit 0
fi

AUTHKEY=$(jq -r '.tailscale_authkey // empty'         "$OPTIONS" 2>/dev/null)
TS_HOSTNAME=$(jq -r '.tailscale_hostname // empty'    "$OPTIONS" 2>/dev/null)
LOGIN_SERVER=$(jq -r '.tailscale_login_server // empty' "$OPTIONS" 2>/dev/null)
ACCEPT_ROUTES=$(jq -r 'if has("tailscale_accept_routes") then .tailscale_accept_routes else true end' "$OPTIONS" 2>/dev/null)
ACCEPT_DNS=$(jq -r 'if has("tailscale_accept_dns") then .tailscale_accept_dns else false end' "$OPTIONS" 2>/dev/null)
EXIT_NODE=$(jq -r '.tailscale_exit_node // empty'     "$OPTIONS" 2>/dev/null)

[ -z "$TS_HOSTNAME" ] && TS_HOSTNAME="ha-webtop"
case "$ACCEPT_ROUTES" in true|false) ;; *) ACCEPT_ROUTES=true ;; esac
case "$ACCEPT_DNS"    in true|false) ;; *) ACCEPT_DNS=false ;; esac

mkdir -p "$STATE_DIR" /run/tailscale
# 750 + Desktop-Gruppe: Log und Anmelde-Link sind aus dem Desktop lesbar,
# die Schluesseldatei tailscaled.state legt tailscaled selbst mit 0600 an.
chgrp "$PGID" "$STATE_DIR" 2>/dev/null || true
chmod 750 "$STATE_DIR"

# --- TUN-Geraet ---------------------------------------------------------
# HA reicht /dev/net/tun per "devices:" durch. Fehlt es (alter Supervisor,
# Kernmodul nicht geladen), legen wir es selbst an. Klappt auch das nicht,
# laeuft tailscaled im Userspace-Modus — dann ist das Tailnet nur ueber den
# lokalen Proxy 127.0.0.1:1055 erreichbar, nicht transparent fuer alle Apps.
TUN_ARGS=()
if [ ! -c /dev/net/tun ]; then
    mkdir -p /dev/net
    if mknod /dev/net/tun c 10 200 2>/dev/null; then
        chmod 600 /dev/net/tun
        log "/dev/net/tun war nicht vorhanden - selbst angelegt."
    fi
fi

if [ -c /dev/net/tun ]; then
    log "TUN-Geraet vorhanden - Kernel-Netzwerkmodus (transparent fuer alle Programme)."
else
    log "WARNUNG: /dev/net/tun fehlt - Userspace-Modus."
    log "WARNUNG: Tailnet nur ueber Proxy 127.0.0.1:1055 (SOCKS5/HTTP), nicht systemweit."
    TUN_ARGS=(--tun=userspace-networking
              --socks5-server=localhost:1055
              --outbound-http-proxy-listen=localhost:1055)
fi

# netfilter nur einschalten, wenn ein Exit-Node benutzt wird - sonst
# produziert tailscaled im Container nur iptables-Fehler.
NETFILTER="off"
[ -n "$EXIT_NODE" ] && NETFILTER="on"

# --- Daemon mit Neustart-Schleife starten -------------------------------
nohup /usr/local/bin/tailscaled-supervise \
    "$STATE_DIR" "$SOCKET" "$NETFILTER" "$LOGFILE" "${TUN_ARGS[@]}" \
    >/dev/null 2>&1 &

log "tailscaled gestartet (State: ${STATE_DIR}, Log: ${LOGFILE})"

# --- Auf den Daemon warten ----------------------------------------------
DAEMON_OK=false
for _ in $(seq 1 30); do
    if ts status --json >/dev/null 2>&1; then
        DAEMON_OK=true
        break
    fi
    sleep 1
done

if [ "$DAEMON_OK" != "true" ]; then
    log "FEHLER: tailscaled antwortet nicht — $(tail -3 "$LOGFILE" 2>/dev/null)"
    exit 0
fi

# Socket fuer den Desktop-Benutzer freigeben, damit "tailscale status" im
# XFCE-Terminal ohne sudo funktioniert.
chgrp "$PGID" "$SOCKET" 2>/dev/null || true
chmod 660 "$SOCKET" 2>/dev/null || true

BACKEND=$(ts status --json 2>/dev/null | jq -r '.BackendState // "Unknown"')
log "Backend-Status: ${BACKEND}"

UP_ARGS=(--hostname="$TS_HOSTNAME"
         --accept-routes="$ACCEPT_ROUTES"
         --accept-dns="$ACCEPT_DNS"
         --exit-node="$EXIT_NODE")
[ -n "$LOGIN_SERVER" ] && UP_ARGS+=(--login-server="$LOGIN_SERVER")

if [ "$BACKEND" = "NeedsLogin" ] || [ "$BACKEND" = "NoState" ]; then
    if [ -n "$AUTHKEY" ]; then
        log "Melde am Tailnet an (Auth-Key)…"
        UP_OUT=$(ts up --authkey="$AUTHKEY" --timeout=60s "${UP_ARGS[@]}" 2>&1)
        UP_RC=$?
        [ -n "$UP_OUT" ] && echo "$UP_OUT" | sed 's/^/[tailscale] /'
        if [ "$UP_RC" -eq 0 ]; then
            log "Anmeldung erfolgreich."
        else
            log "FEHLER: Anmeldung mit Auth-Key fehlgeschlagen — Key abgelaufen oder schon benutzt?"
        fi
    else
        log "Kein Auth-Key gesetzt — starte interaktive Anmeldung."
        nohup /usr/local/bin/tailscale --socket="$SOCKET" up "${UP_ARGS[@]}" \
            >>"$LOGFILE" 2>&1 &
        AUTH_URL=""
        for _ in $(seq 1 20); do
            AUTH_URL=$(ts status --json 2>/dev/null | jq -r '.AuthURL // empty')
            [ -n "$AUTH_URL" ] && break
            sleep 1
        done
        if [ -n "$AUTH_URL" ]; then
            echo "$AUTH_URL" > "${STATE_DIR}/login-url.txt"
            chown "${PUID}:${PGID}" "${STATE_DIR}/login-url.txt" 2>/dev/null || true
            log "===================================================================="
            log "ANMELDUNG NOETIG — diesen Link im Browser oeffnen:"
            log "  ${AUTH_URL}"
            log "(steht auch in ${STATE_DIR}/login-url.txt)"
            log "===================================================================="
        else
            log "WARNUNG: Keine Anmelde-URL erhalten — siehe ${LOGFILE}"
        fi
    fi
else
    # Bereits angemeldet: Einstellungen ohne Neu-Anmeldung nachziehen.
    ts set --hostname="$TS_HOSTNAME" \
           --accept-routes="$ACCEPT_ROUTES" \
           --accept-dns="$ACCEPT_DNS" \
           --exit-node="$EXIT_NODE" 2>&1 | sed 's/^/[tailscale] /' || true
    ts up --timeout=30s "${UP_ARGS[@]}" >/dev/null 2>&1 || true
fi

# --- Ergebnis protokollieren --------------------------------------------
for _ in $(seq 1 15); do
    BACKEND=$(ts status --json 2>/dev/null | jq -r '.BackendState // "Unknown"')
    [ "$BACKEND" = "Running" ] && break
    sleep 1
done

if [ "$BACKEND" = "Running" ]; then
    TS_IP=$(ts ip -4 2>/dev/null | head -1)
    TS_NAME=$(ts status --json 2>/dev/null | jq -r '.Self.DNSName // empty' | sed 's/\.$//')
    log "Verbunden — IP: ${TS_IP:-unbekannt}${TS_NAME:+, Name: ${TS_NAME}}"
    [ -n "$EXIT_NODE" ] && log "Exit-Node: ${EXIT_NODE}"
else
    log "Status: ${BACKEND} (noch nicht verbunden) — Details in ${LOGFILE}"
fi
