#!/usr/bin/env bash
# Add-on-Entrypoint: übersetzt /data/options.json in die Environment-Variablen
# von NPMplus, bereitet Logs und CrowdSec-Bouncer vor und übergibt dann an das
# Original-Init des Upstream-Images.
set -e

OPTIONS=/data/options.json

log()  { echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
warn() { echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Bewusst nicht `.key // $default`: in jq ist `false // x` gleich `x`, ein auf
# false gesetzter Schalter käme damit als sein eigener Standardwert zurück.
opt() { jq -r --arg k "$1" --arg d "$2" 'if has($k) and (.[$k] != null) then .[$k] else $d end' "$OPTIONS"; }

# Zeilenenden und Leerraum entfernen. Wer einen Schlüssel oder eine URL aus
# einer Datei oder einem Terminal kopiert, hat schnell ein \r oder ein
# abschließendes Leerzeichen mit im Wert — im HTTP-Header macht das den
# Schlüssel ungültig, ohne dass man es irgendwo sehen könnte.
trim() {
    local v="${1//$'\r'/}"
    v="${v//$'\n'/}"
    v="${v#"${v%%[![:space:]]*}"}"
    v="${v%"${v##*[![:space:]]}"}"
    printf '%s' "$v"
}
opt_trim() { trim "$(opt "$1" "$2")"; }

# Nur exportieren, wenn der Wert nicht leer ist. NPMplus prüft viele Envs auf
# "gesetzt oder nicht" und nicht auf den Inhalt — ein leerer String ist dort
# etwas anderes als eine fehlende Variable.
export_if_set() {
    [ -n "$2" ] || return 0
    export "$1=$2"
}

###############################################################################
# Optionen einlesen
###############################################################################
TZ_OPT=$(opt TZ "Europe/Berlin")
ACME_EMAIL_OPT=$(opt acme_email "")
INITIAL_ADMIN_EMAIL_OPT=$(opt initial_admin_email "")
INITIAL_ADMIN_PASSWORD_OPT=$(opt initial_admin_password "")
HTTP_PORT_OPT=$(opt http_port "80")
HTTPS_PORT_OPT=$(opt https_port "443")
ADMIN_PORT_OPT=$(opt admin_port "81")
DISABLE_IPV6_OPT=$(opt disable_ipv6 "false")
DISABLE_H3_QUIC_OPT=$(opt disable_h3_quic "false")
ENABLE_MPTCP_OPT=$(opt enable_mptcp "false")
LOGROTATE_OPT=$(opt logrotate "true")
LOGROTATIONS_OPT=$(opt logrotations "3")
ERROR_LOG_LEVEL_OPT=$(opt error_log_level "warn")
SHARE_LOGS_OPT=$(opt share_logs "true")
LOG_TO_STDOUT_OPT=$(opt log_to_stdout "true")
GOA_OPT=$(opt goaccess "false")
TRUST_IP_OPT=$(opt trust_ip "")
TRUST_CLOUDFLARE_OPT=$(opt trust_cloudflare "false")
CS_ENABLED_OPT=$(opt crowdsec_enabled "false")
CS_LAPI_OPT=$(opt_trim crowdsec_lapi_url "http://127.0.0.1:8080")
CS_KEY_OPT=$(opt_trim crowdsec_api_key "")
CS_APPSEC_OPT=$(opt_trim crowdsec_appsec_url "http://127.0.0.1:7422")
WORKER_PROCESSES_OPT=$(opt nginx_worker_processes "auto")
WORKER_CONNECTIONS_OPT=$(opt nginx_worker_connections "512")
COOKIE_SECRET_OPT=$(opt cookie_secret "")

###############################################################################
# Environment für NPMplus setzen
###############################################################################
export TZ="$TZ_OPT"
export HTTP_PORT="$HTTP_PORT_OPT"
export HTTPS_PORT="$HTTPS_PORT_OPT"
export NPM_PORT="$ADMIN_PORT_OPT"
export DISABLE_IPV6="$DISABLE_IPV6_OPT"
export DISABLE_H3_QUIC="$DISABLE_H3_QUIC_OPT"
export ENABLE_MPTCP="$ENABLE_MPTCP_OPT"
export TRUST_CLOUDFLARE="$TRUST_CLOUDFLARE_OPT"
export GOA="$GOA_OPT"
export NGINX_WORKER_PROCESSES="$WORKER_PROCESSES_OPT"
export NGINX_WORKER_CONNECTIONS="$WORKER_CONNECTIONS_OPT"
export LOGROTATIONS="$LOGROTATIONS_OPT"

export_if_set ACME_EMAIL "$ACME_EMAIL_OPT"
export_if_set INITIAL_ADMIN_EMAIL "$INITIAL_ADMIN_EMAIL_OPT"
export_if_set INITIAL_ADMIN_PASSWORD "$INITIAL_ADMIN_PASSWORD_OPT"
export_if_set TRUST_IP "$TRUST_IP_OPT"
export_if_set COOKIE_SECRET "$COOKIE_SECRET_OPT"

# GoAccess und die Weitergabe an CrowdSec brauchen beide geschriebene Access-Logs.
LOGROTATE_EFFECTIVE="$LOGROTATE_OPT"
if [ "$LOG_TO_STDOUT_OPT" = "true" ] && [ "$LOGROTATE_EFFECTIVE" != "true" ]; then
    warn "log_to_stdout is on — enabling logrotate as well, otherwise nginx writes no access logs"
    LOGROTATE_EFFECTIVE="true"
fi
if [ "$CS_ENABLED_OPT" = "true" ] && [ "$LOGROTATE_EFFECTIVE" != "true" ]; then
    warn "CrowdSec is on — enabling logrotate as well, otherwise CrowdSec has no logs to read"
    LOGROTATE_EFFECTIVE="true"
fi
export LOGROTATE="$LOGROTATE_EFFECTIVE"

# Alles, was das Add-on nicht als eigene Option anbietet, kommt über extra_env.
# Erwartetes Format je Eintrag: KEY=VALUE
while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    case "$entry" in
        *=*)
            key="${entry%%=*}"
            value="${entry#*=}"
            export "$key=$value"
            log "extra_env: ${key} set"
            ;;
        *)
            warn "ignoring extra_env entry without '=': ${entry}"
            ;;
    esac
done < <(jq -r '.extra_env // [] | .[]' "$OPTIONS")

###############################################################################
# Logs
#
# NPMplus schreibt Access-/Error-Logs nach /data/nginx/logs. /data gehört dem
# Add-on allein — kein anderes Add-on kann dort hineinsehen. Für CrowdSec gibt
# es deshalb zwei Wege, beide sind unabhängig voneinander schaltbar:
#
#   share_logs    -> /data/nginx/logs zeigt per Symlink nach /share/npmplus/logs,
#                    lesbar für jedes Add-on mit share-Mapping (Datei-Acquisition)
#   log_to_stdout -> die Logzeilen laufen zusätzlich in die Container-Ausgabe und
#                    landen damit in journald (journald-Acquisition)
###############################################################################
LOG_DIR=/data/nginx/logs
SHARED_LOG_DIR=/share/npmplus/logs

if [ "$SHARE_LOGS_OPT" = "true" ]; then
    mkdir -p "$SHARED_LOG_DIR"
    if [ -d "$LOG_DIR" ] && [ ! -L "$LOG_DIR" ]; then
        # Bereits vorhandene Logs mitnehmen, statt sie unerreichbar zu machen.
        find "$LOG_DIR" -mindepth 1 -maxdepth 1 -exec mv -n {} "$SHARED_LOG_DIR"/ \; 2>/dev/null || true
        rm -rf "$LOG_DIR"
    fi
    mkdir -p /data/nginx
    ln -sfn "$SHARED_LOG_DIR" "$LOG_DIR"
    log "Logs in ${SHARED_LOG_DIR} (readable by other add-ons)"
else
    if [ -L "$LOG_DIR" ]; then
        rm -f "$LOG_DIR"
        log "Log sharing to /share disabled — logs stay in /data"
    fi
    mkdir -p "$LOG_DIR"
fi

if [ "$LOG_TO_STDOUT_OPT" = "true" ]; then
    touch "$LOG_DIR/access.log" 2>/dev/null || true
    # Bewusst nur das Access-Log: das Error-Log ist die Quelle für CrowdSec
    # nicht nötig und flutet das Add-on-Protokoll (siehe error_log_level).
    # -F statt -f: die Dateien werden von logrotate ersetzt, tail muss dem
    # Namen folgen und nicht dem alten Filedeskriptor.
    tail -qn0 -F "$LOG_DIR/access.log" 2>/dev/null &
    TAIL_PID=$!
    log "Mirroring access log to stdout as well (journald)"
fi

###############################################################################
# Ausführlichkeit des Error-Logs
#
# Mit LOGROTATE=true kommentiert das Upstream-Init die Zeile
# "#error_log /data/nginx/logs/error.log info;" in seiner nginx.conf ein.
# Level "info" protokolliert jeden Worker-Wechsel und jedes SIGCHLD — das
# füllt Protokoll und Datenträger. Deshalb die noch auskommentierte Vorlage
# hier vorab auf das gewünschte Level setzen, bevor das Init sie aktiviert.
###############################################################################
NGINX_CONF=/usr/local/nginx/conf/nginx.conf
if [ -f "$NGINX_CONF" ]; then
    sed -i "s|^#error_log /data/nginx/logs/error.log .*;|#error_log /data/nginx/logs/error.log ${ERROR_LOG_LEVEL_OPT};|" "$NGINX_CONF"
    log "Error log level: ${ERROR_LOG_LEVEL_OPT}"
else
    warn "${NGINX_CONF} not found — keeping the image default for the error log level"
fi

###############################################################################
# CrowdSec-Bouncer
#
# NPMplus liest seine Bouncer-Konfiguration aus /data/crowdsec/crowdsec.conf.
# Die Datei legt das Upstream-Init normalerweise selbst an — hier vorziehen,
# damit die Add-on-Optionen hineingeschrieben werden können, bevor nginx die
# Config auswertet. Von Hand gesetzte Werte bleiben erhalten, nur die vier
# Schlüssel unten gehören dem Add-on.
###############################################################################
CS_CONF=/data/crowdsec/crowdsec.conf

set_conf() {
    local key="$1" value="$2"
    if grep -q "^${key}=" "$CS_CONF"; then
        # Trennzeichen ~, damit URLs und Keys mit / oder | nicht stören.
        sed -i "s~^${key}=.*~${key}=${value}~" "$CS_CONF"
    else
        echo "${key}=${value}" >> "$CS_CONF"
    fi
}

mkdir -p /data/crowdsec
if [ ! -s "$CS_CONF" ]; then
    cp -n /etc/crowdsec.conf.example "$CS_CONF"
fi

# Vorflugkontrolle: LAPI mit dem konfigurierten Schlüssel abfragen.
#
# Ohne diese Prüfung ist ein Tippfehler im Schlüssel fatal: die LAPI antwortet
# mit 403, AppSec ebenso — und ein 403 bedeutet im AppSec-Protokoll "sperren".
# Der Bouncer würde also jede einzelne Anfrage blockieren und sämtliche Dienste
# hinter dem Proxy unerreichbar machen. Deshalb lieber ungeschützt starten und
# laut warnen, als alles auszusperren.
check_lapi() {
    local url="$1" key="$2" code
    for path in "/v1/decisions?ip=127.0.0.1" "/v1/decisions/stream?startup=true"; do
        # curl schreibt bei Verbindungsfehlern selbst "000" — kein zusätzliches
        # echo im Fehlerfall, sonst stünde dort "000000".
        code=$(curl -s -o /dev/null -m 5 -w '%{http_code}' \
            -H "X-Api-Key: ${key}" \
            -A "npmplus-addon/1.0" \
            "${url%/}${path}" 2>/dev/null || true)
        case "${code:-000}" in
            200|404) printf '%s' "$code"; return 0 ;;
        esac
    done
    printf '%s' "${code:-000}"
}

if [ "$CS_ENABLED_OPT" = "true" ]; then
    if [ -z "$CS_KEY_OPT" ]; then
        warn "crowdsec_enabled is on but crowdsec_api_key is empty — bouncer stays OFF"
        set_conf ENABLED false
    else
        CS_CODE=$(check_lapi "$CS_LAPI_OPT" "$CS_KEY_OPT")
        case "$CS_CODE" in
            200|404)
                set_conf ENABLED true
                set_conf API_URL "$CS_LAPI_OPT"
                set_conf API_KEY "$CS_KEY_OPT"
                set_conf APPSEC_URL "$CS_APPSEC_OPT"
                log "CrowdSec bouncer active against ${CS_LAPI_OPT} (AppSec: ${CS_APPSEC_OPT:-off})"
                ;;
            403|401)
                set_conf ENABLED false
                warn "CrowdSec rejected the bouncer key (HTTP ${CS_CODE}) — bouncer stays OFF."
                warn "Configured key is ${#CS_KEY_OPT} characters long (cscli generates 44)."
                warn "Create a new key: cscli -c <addon-config> bouncers add npmplus -o raw"
                ;;
            000)
                set_conf ENABLED false
                warn "CrowdSec unreachable at ${CS_LAPI_OPT} — bouncer stays OFF."
                warn "If CrowdSec runs in its own container, 127.0.0.1 is wrong:"
                warn "use its container IP or an address published on the host instead."
                ;;
            *)
                set_conf ENABLED false
                warn "Unexpected reply from CrowdSec (HTTP ${CS_CODE}) — bouncer stays OFF."
                ;;
        esac
    fi
else
    set_conf ENABLED false
fi

###############################################################################
# An das Original-Init übergeben
#
# Bewusst kein exec: dieses Skript bleibt PID 1 und fängt SIGTERM selbst ab.
# Mit exec wäre tini PID 1 und stürbe am Signal — der Container endete dann mit
# Exit-Code 143, was der Supervisor als "App hat SIGTERM nicht behandelt"
# meldet. Außerdem bekäme der tail-Prozess für die Log-Spiegelung so nie ein
# Signal, weil tini nur an sein eigenes Kind weiterreicht.
#
# tini läuft mit -g, damit das Signal an die ganze Prozessgruppe von NPMplus
# geht und nicht nur an entrypoint.sh. Dazu -s: da tini hier nicht PID 1 ist,
# muss es sich als child subreaper registrieren, sonst landen verwaiste
# Prozesse bei diesem Skript und werden nicht abgeräumt.
###############################################################################
log "Starting NPMplus — UI at https://<HA-IP>:${ADMIN_PORT_OPT}"

TINI=$(command -v tini || true)
if [ -n "$TINI" ]; then
    "$TINI" -s -g -- entrypoint.sh &
else
    warn "tini not found — starting entrypoint.sh directly"
    entrypoint.sh &
fi
APP_PID=$!

_term() {
    log "SIGTERM received, stopping NPMplus..."
    kill -TERM "$APP_PID" 2>/dev/null || true
    [ -n "${TAIL_PID:-}" ] && kill -TERM "$TAIL_PID" 2>/dev/null || true
    # nginx braucht einen Moment, um offene Verbindungen zu schließen.
    wait "$APP_PID" 2>/dev/null || true
    log "NPMplus stopped"
    exit 0
}
trap _term SIGTERM SIGINT

# errexit hier aus: ein Exit-Code ungleich 0 soll ausgewertet und nicht
# stillschweigend durchgereicht werden, bevor die Warnung im Log steht.
set +e
wait "$APP_PID"
APP_EXIT=$?
set -e

# Ohne Signal hierher zu kommen heißt: NPMplus ist von sich aus gestorben.
# Den Exit-Code durchreichen, damit der Watchdog des Supervisors greift.
warn "NPMplus exited without a stop request (exit code ${APP_EXIT})"
[ -n "${TAIL_PID:-}" ] && kill -TERM "$TAIL_PID" 2>/dev/null || true
exit "$APP_EXIT"
