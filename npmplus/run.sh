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
ACME_PROFILE_OPT=$(opt_trim acme_profile "shortlived")
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
GOA_LOCALHOST_OPT=$(opt goaccess_listen_localhost "true")
TRUST_IP_OPT=$(opt trust_ip "")
TRUST_CLOUDFLARE_OPT=$(opt trust_cloudflare "false")
CS_ENABLED_OPT=$(opt crowdsec_enabled "false")
CS_LAPI_OPT=$(opt_trim crowdsec_lapi_url "http://127.0.0.1:8080")
CS_KEY_OPT=$(opt_trim crowdsec_api_key "")
CS_APPSEC_OPT=$(opt_trim crowdsec_appsec_url "http://127.0.0.1:7422")
CS_FALLBACK_OPT=$(opt_trim crowdsec_fallback_remediation "default")
CS_APPSEC_FAIL_OPT=$(opt_trim crowdsec_appsec_failure_action "passthrough")
CS_RETRY_OPT=$(opt crowdsec_retry_minutes "15")
CS_RETRY_RESTART_OPT=$(opt crowdsec_retry_restart "true")
CS_CAPTCHA_PROVIDER_OPT=$(opt_trim crowdsec_captcha_provider "off")

# Die Auswahllisten in der Add-on-Konfiguration brauchen für "nichts tun" einen
# sichtbaren Eintrag — ein leerer Wert erschiene dort als Radiobutton ohne
# Beschriftung. Intern bleibt es beim leeren String.
# Kein "[ .. ] && ..": schlägt die Prüfung fehl, beendet set -e das Skript.
if [ "$CS_FALLBACK_OPT" = "default" ]; then
    CS_FALLBACK_OPT=""
fi
if [ "$CS_CAPTCHA_PROVIDER_OPT" = "off" ]; then
    CS_CAPTCHA_PROVIDER_OPT=""
fi
CS_CAPTCHA_SITE_OPT=$(opt_trim crowdsec_captcha_site_key "")
CS_CAPTCHA_SECRET_OPT=$(opt_trim crowdsec_captcha_secret_key "")
GEO_MODE_OPT=$(opt_trim geo_mode "off")
GEO_PRESET_OPT=$(opt_trim geo_preset "none")
GEO_REFRESH_OPT=$(opt geo_refresh_hours "24")
GEO_DENY_ACTION_OPT=$(opt_trim geo_deny_action "403")
GEO_LOG_COUNTRY_OPT=$(opt geo_log_country "true")
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
export GOA_LISTEN_LOCALHOST="$GOA_LOCALHOST_OPT"
export NGINX_WORKER_PROCESSES="$WORKER_PROCESSES_OPT"
export NGINX_WORKER_CONNECTIONS="$WORKER_CONNECTIONS_OPT"
export LOGROTATIONS="$LOGROTATIONS_OPT"

export_if_set ACME_EMAIL "$ACME_EMAIL_OPT"
export_if_set ACME_PROFILE "$ACME_PROFILE_OPT"
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

# Hinweis erst nach extra_env: wer GOA_LISTEN_LOCALHOST dort selbst setzt, soll
# auch die passende Adresse genannt bekommen.
#
# GoAccess läuft in dieser NPMplus-Version auf einem eigenen HTTPS-Port (91) und
# nicht unter /goaccess der Oberfläche — und dieser Port kennt keine Anmeldung.
# Das Dashboard zeigt Besucher-IPs und alle angefragten URLs, deshalb bindet das
# Add-on es standardmäßig nur an localhost.
if [ "$GOA" = "true" ]; then
    if [ "$GOA_LISTEN_LOCALHOST" = "true" ]; then
        log "GoAccess enabled on 127.0.0.1:91 (HTTPS). Not reachable from the LAN — put a NPMplus proxy host with an access list in front of it, or set goaccess_listen_localhost to false."
    else
        warn "GoAccess enabled on 0.0.0.0:91 (HTTPS) WITHOUT authentication — everyone on the LAN can read visitor IPs and requested URLs. Never forward port 91 in your router."
    fi
fi

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
    # Home Assistant benennt jeden Add-on-Container "app_<repo>_<slug>", der
    # Hostname ist derselbe Name mit Bindestrichen. Genau dieser Wert gehört in
    # den journalctl_filter der CrowdSec-Acquisition — hier ausgeben, damit ihn
    # niemand per docker inspect suchen muss.
    OWN_HOST=$(cat /etc/hostname 2>/dev/null | tr -d '\r\n')
    if [ -n "$OWN_HOST" ]; then
        log "CrowdSec acquisition filter: SYSLOG_IDENTIFIER=app_${OWN_HOST//-/_}"
    fi
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
# Adressen von CrowdSec bestimmen
#
# Container-IPs (172.16.0.0/12) vergibt Docker bei jedem Start neu — nach einem
# Neustart von Home Assistant zeigt eine eingetragene IP ins Leere und der
# Bouncer geht still aus. Der Container-Hostname bleibt dagegen gleich.
###############################################################################

# Host-Teil einer URL, ohne Schema, Port und Pfad.
host_of_url() {
    local u="${1#*://}"
    u="${u%%/*}"
    printf '%s' "${u%%:*}"
}

warn_if_container_ip() {
    local name="$1" host
    host=$(host_of_url "$2")
    if [[ "$host" =~ ^172\.(1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+$ ]]; then
        warn "${name} points at the container IP ${host}. Docker hands out a new one on every"
        warn "start — after a Home Assistant restart this address is dead. Use the container"
        warn "hostname instead: docker inspect -f '{{.Config.Hostname}}' <crowdsec-container>"
        warn "or set the option to \"auto\" and let the add-on look it up."
    fi
}

# Den Hostnamen des CrowdSec-Add-ons beim Supervisor erfragen. Der Slug eines
# Add-ons ist "<repo>_<slug>", der Container-Hostname derselbe Name mit
# Bindestrich. Der Firewall-Bouncer endet auf "-firewall-bouncer" und wird von
# der Suche nach "_crowdsec" am Ende deshalb nicht getroffen.
discover_crowdsec_host() {
    [ -n "${SUPERVISOR_TOKEN:-}" ] || return 1
    local slug
    slug=$(curl -s -m 5 -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        "http://supervisor/addons" 2>/dev/null \
        | jq -r '[.data.addons[]?.slug | select(test("_crowdsec$"))] | first // empty' 2>/dev/null)
    [ -n "$slug" ] || return 1
    printf '%s' "${slug//_/-}"
}

CS_AUTO_HOST=""
if [ "$CS_LAPI_OPT" = "auto" ] || [ "$CS_APPSEC_OPT" = "auto" ]; then
    CS_AUTO_HOST=$(discover_crowdsec_host || true)
    if [ -n "$CS_AUTO_HOST" ]; then
        log "CrowdSec add-on found: ${CS_AUTO_HOST}"
    else
        warn "crowdsec_lapi_url/crowdsec_appsec_url is set to \"auto\", but no installed add-on"
        warn "whose slug ends in _crowdsec was found. Enter the address by hand."
    fi
fi
if [ "$CS_LAPI_OPT" = "auto" ]; then
    if [ -n "$CS_AUTO_HOST" ]; then
        CS_LAPI_OPT="http://${CS_AUTO_HOST}:8080"
    else
        CS_LAPI_OPT=""
    fi
fi
if [ "$CS_APPSEC_OPT" = "auto" ]; then
    if [ -n "$CS_AUTO_HOST" ]; then
        CS_APPSEC_OPT="http://${CS_AUTO_HOST}:7422"
    else
        CS_APPSEC_OPT=""
    fi
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

# AppSec antwortet ohne Bouncer-Schlüssel mit 401 — jede HTTP-Antwort beweist
# also, dass der Endpunkt lebt. Nur "000" heißt: niemand da.
check_appsec() {
    local url="$1" code
    code=$(curl -s -o /dev/null -m 5 -w '%{http_code}' \
        -A "npmplus-addon/1.0" "${url%/}/" 2>/dev/null || true)
    printf '%s' "${code:-000}"
}

# Alle Schlüssel schreiben, die dem Add-on gehören. Steht in einer eigenen
# Funktion, weil derselbe Block zweimal gebraucht wird: einmal beim Start und
# noch einmal aus dem Hintergrund-Wiederholer, wenn CrowdSec zum Startzeitpunkt
# noch nicht lief.
cs_apply_conf() {
    set_conf ENABLED true
    set_conf API_URL "$CS_LAPI_OPT"
    set_conf API_KEY "$CS_KEY_OPT"
    set_conf APPSEC_URL "$CS_APPSEC_OPT"
    # Captcha statt harter Sperre. Wirkt nur bei Entscheidungen vom Typ
    # "captcha" — die muss CrowdSec über seine profiles.yaml ausstellen, sonst
    # bleibt ein Ban ein Ban.
    if [ -n "$CS_CAPTCHA_PROVIDER_OPT" ]; then
        if [ -n "$CS_CAPTCHA_SITE_OPT" ] && [ -n "$CS_CAPTCHA_SECRET_OPT" ]; then
            set_conf CAPTCHA_PROVIDER "$CS_CAPTCHA_PROVIDER_OPT"
            set_conf SITE_KEY "$CS_CAPTCHA_SITE_OPT"
            set_conf SECRET_KEY "$CS_CAPTCHA_SECRET_OPT"
            log "Captcha enabled (${CS_CAPTCHA_PROVIDER_OPT})"
        else
            set_conf CAPTCHA_PROVIDER ""
            warn "crowdsec_captcha_provider is set but site key or secret key is missing — captcha disabled"
        fi
    else
        set_conf CAPTCHA_PROVIDER ""
    fi
    # Der Bouncer meldet eine tote AppSec-Adresse im Betrieb nicht, er lässt die
    # Prüfung dann einfach ausfallen. Deshalb hier.
    if [ -n "$CS_APPSEC_OPT" ]; then
        if [ "$(check_appsec "$CS_APPSEC_OPT")" = "000" ]; then
            warn "AppSec at ${CS_APPSEC_OPT} does not answer — requests will not be"
            warn "checked by the WAF. Either the appsec source is missing from the"
            warn "CrowdSec acquisition, or the address is wrong. Leave"
            warn "crowdsec_appsec_url empty if AppSec is not in use."
        fi
    fi
    # Verhalten, wenn die AppSec-Anfrage selbst scheitert (Zeitüberschreitung,
    # Host nicht erreichbar). Die Vorgabe des Images ist "deny" — und "deny"
    # heißt: jede Anfrage wird gesperrt, solange AppSec nicht antwortet. Genau
    # das passiert beim Neustart oder Update des CrowdSec-Add-ons: NPMplus läuft
    # weiter, AppSec ist für ein bis zwei Minuten weg, und der Proxy beantwortet
    # in dieser Zeit ALLES mit einer Sperre ("denied ... by appsec" im Log).
    # Deshalb schreibt das Add-on den Schlüssel selbst, Vorgabe "passthrough":
    # kein AppSec = keine WAF-Prüfung, aber auch keine Sperre.
    set_conf APPSEC_FAILURE_ACTION "$CS_APPSEC_FAIL_OPT"
    if [ "$CS_APPSEC_FAIL_OPT" = "deny" ]; then
        warn "crowdsec_appsec_failure_action is \"deny\" — while AppSec is unreachable"
        warn "(restart or update of the CrowdSec add-on) every request is blocked."
    fi
    # Ersatz-Maßnahme, wenn der Bouncer eine Entscheidung nicht anwenden kann:
    # unbekannter Entscheidungstyp, oder Captcha ist eingestellt aber nicht
    # nutzbar. Greift außerdem bei einer gescheiterten AppSec-Anfrage, sofern
    # APPSEC_FAILURE_ACTION auf "deny" steht.
    # NICHT das Verhalten bei Ausfall der LAPI — dort lässt der Bouncer im
    # live-Modus jede Anfrage durch. Leer gelassen bleibt der Wert aus
    # crowdsec.conf unangetastet.
    if [ -n "$CS_FALLBACK_OPT" ]; then
        set_conf FALLBACK_REMEDIATION "$CS_FALLBACK_OPT"
        log "Fallback remediation: ${CS_FALLBACK_OPT}"
    fi
}

# Wird auf true gesetzt, wenn der Bouncer nur deshalb aus bleibt, weil die LAPI
# beim Start nicht antwortete — dann lohnt es sich, später noch einmal zu fragen.
CS_RETRY_WANTED=false

if [ "$CS_ENABLED_OPT" = "true" ]; then
    warn_if_container_ip "crowdsec_lapi_url" "$CS_LAPI_OPT"
    # Kein "[ -n .. ] && ..": mit set -e beendet die fehlschlagende Prüfung das
    # Skript, sobald crowdsec_appsec_url leer ist.
    if [ -n "$CS_APPSEC_OPT" ]; then
        warn_if_container_ip "crowdsec_appsec_url" "$CS_APPSEC_OPT"
    fi
    if [ -z "$CS_KEY_OPT" ]; then
        warn "crowdsec_enabled is on but crowdsec_api_key is empty — bouncer stays OFF"
        set_conf ENABLED false
    elif [ -z "$CS_LAPI_OPT" ]; then
        warn "crowdsec_enabled is on but no LAPI address is known — bouncer stays OFF"
        set_conf ENABLED false
    else
        CS_CODE=$(check_lapi "$CS_LAPI_OPT" "$CS_KEY_OPT")
        case "$CS_CODE" in
            200|404)
                cs_apply_conf
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
                CS_RETRY_WANTED=true
                warn "CrowdSec unreachable at ${CS_LAPI_OPT} — bouncer stays OFF for now."
                warn "If CrowdSec runs in its own container, 127.0.0.1 is wrong:"
                warn "use its container hostname (docker inspect -f '{{.Config.Hostname}}')"
                warn "or an address published on the host instead."
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
# Ländersperre
#
# Ohne MaxMind: die CIDR-Listen von ipverse/country-ip-blocks stammen aus den
# Delegationsdateien der Regional Internet Registries und lassen sich direkt in
# das eingebaute geo-Modul von nginx laden — kein Konto, kein Lizenzschlüssel,
# kein zusätzliches Modul.
#
# Die Prüfung greift damit schon beim ersten Paket, während CrowdSec erst nach
# der Auswertung der ersten Anfrage entscheidet. Beides schließt sich nicht aus.
#
# Eingehängt wird über /data/custom_nginx: http_top.conf gilt einmal für den
# gesamten http-Block, server_http.conf bindet NPMplus in jeden Proxy-, Weiter-
# leitungs- und Dead-Host ein. Beide Dateien können eigene Einträge des Nutzers
# enthalten, deshalb schreibt das Add-on nur zwischen seine Marker und lässt
# alles andere unberührt.
###############################################################################
GEO_DIR=/data/geoip
GEO_RANGES="$GEO_DIR/ranges.conf"
GEO_COUNTRY_CONF="$GEO_DIR/countries.conf"
GEO_HTTP="$GEO_DIR/http.conf"
GEO_META="$GEO_DIR/lists.meta"
GEO_PAGE="$GEO_DIR/blocked.html"
GEO_BLOCK_LOG=/data/nginx/logs/blocked.log
CUSTOM_NGINX=/data/custom_nginx
GEO_MARK_BEGIN="# >>> npmplus-addon geoip >>>"
GEO_MARK_END="# <<< npmplus-addon geoip <<<"
GEO_IPVERSE_BASE="https://raw.githubusercontent.com/ipverse/country-ip-blocks/master/country"

# Nur den eigenen Abschnitt aus einer Datei entfernen. Ohne diesen Schritt
# würden sich die Blöcke bei jedem Start stapeln.
geo_strip() {
    local file="$1"
    [ -f "$file" ] || return 0
    awk -v b="$GEO_MARK_BEGIN" -v e="$GEO_MARK_END" '
        $0 == b { skip = 1 }
        skip == 0 { print }
        $0 == e { skip = 0 }
    ' "$file" > "${file}.tmp" && mv "${file}.tmp" "$file"
}

geo_include() {
    local file="$1" line="$2"
    geo_strip "$file"
    printf '%s\n%s\n%s\n' "$GEO_MARK_BEGIN" "$line" "$GEO_MARK_END" >> "$file"
}

# Listen holen und in geo-Syntax umschreiben. Rückgabe 1, wenn kein einziges
# Land geladen werden konnte — dann bleibt die alte Datei stehen.
#
# Bewusst kein "curl | awk" in einem Rutsch: der Rückgabewert einer Pipeline ist
# der des letzten Glieds, awk wäre also auch nach einem 404 zufrieden und ein
# fehlendes Land fiele niemandem auf.
geo_fetch() {
    local mark="$1" target="$2"; shift 2
    local tmp tmpc raw cc file url code total=0 failed=0 count before start
    tmp=$(mktemp); tmpc=$(mktemp); raw=$(mktemp)
    start=$(date +%s)
    log "Downloading country lists for $# countries from ipverse..."
    for cc in "$@"; do
        count=0
        for file in ipv4-aggregated ipv6-aggregated; do
            url="${GEO_IPVERSE_BASE}/${cc}/${file}.txt"
            code=$(curl -sL -m 30 -o "$raw" -w '%{http_code}' "$url" 2>/dev/null || true)
            case "${code:-000}" in
                200)
                    # Vor und nach dem Anhängen zählen. Die Rohdatei zu zählen
                    # wäre daneben: Leerzeilen fallen im awk-Filter weg, und die
                    # Zahl im Protokoll passte dann nicht zur fertigen Datei.
                    before=$(wc -l < "$tmp")
                    awk -v m="$mark" 'NF && $1 !~ /^#/ { print "    " $1 " " m ";" }' "$raw" >> "$tmp"
                    count=$((count + $(wc -l < "$tmp") - before))
                    # Dieselben Bereiche ein zweites Mal, diesmal mit dem
                    # Ländercode als Wert. Nur für die Protokollspalte.
                    if [ "$GEO_LOG_COUNTRY_OPT" = "true" ]; then
                        awk -v c="$cc" 'NF && $1 !~ /^#/ { print "    " $1 " " c ";" }' "$raw" >> "$tmpc"
                    fi
                    ;;
                404)
                    # Kein Fehler: Nordkorea etwa hat gar keine IPv6-Zuteilung,
                    # ipverse veröffentlicht dann keine Datei.
                    log "  ${cc}/${file}: not published by ipverse, skipped"
                    ;;
                *)
                    failed=$((failed + 1))
                    warn "Country list ${cc}/${file} could not be downloaded (HTTP ${code:-000})"
                    ;;
            esac
        done
        total=$((total + count))
        log "  ${cc}: ${count} ranges"
    done
    rm -f "$raw"
    if [ ! -s "$tmp" ]; then
        rm -f "$tmp" "$tmpc"
        warn "No country list could be downloaded"
        return 1
    fi
    mv "$tmp" "$target"
    chmod 644 "$target"
    if [ "$GEO_LOG_COUNTRY_OPT" = "true" ]; then
        mv "$tmpc" "$GEO_COUNTRY_CONF"
        chmod 644 "$GEO_COUNTRY_CONF"
    else
        rm -f "$tmpc" "$GEO_COUNTRY_CONF"
    fi
    # Fingerabdruck der Auswahl mitschreiben. Beim nächsten Start entscheidet
    # er darüber, ob die vorhandenen Dateien noch zur Konfiguration passen.
    printf '%s' "$GEO_SIG" > "$GEO_META"
    log "Country lists ready: ${total} ranges in $(( $(date +%s) - start ))s"
    [ "$failed" = "0" ] || warn "${failed} country list(s) could not be downloaded — the filter works, but is incomplete"
    return 0
}

# Einzeladressen aus einer Options-Liste in geo-Zeilen umschreiben. Die Werte
# landen unverändert in einer nginx-Konfiguration, deshalb hier eine strenge
# Prüfung: nur Ziffern, Punkte, Doppelpunkte, Hex und ein optionales Präfix.
# Alles andere wird verworfen statt eingebaut — ein Anführungszeichen oder
# Semikolon in der Option würde sonst die Konfiguration zerlegen.
geo_ip_lines() {
    local key="$1" mark="$2" entry
    while IFS= read -r entry; do
        entry=$(trim "$entry")
        [ -n "$entry" ] || continue
        case "$entry" in
            *[!0-9a-fA-F.:/]*)
                warn "Ignoring ${key} entry '${entry}' — not an IP address or CIDR range"
                continue ;;
        esac
        printf '    %s %s;\n' "$entry" "$mark"
    done < <(jq -r --arg k "$key" '.[$k] // [] | .[]' "$OPTIONS")
}

# Hostnamen ebenso prüfen, gleiche Begründung.
geo_host_lines() {
    local host
    while IFS= read -r host; do
        host=$(trim "$host")
        [ -n "$host" ] || continue
        case "$host" in
            *[!0-9a-zA-Z.*_-]*)
                warn "Ignoring geo_exempt_hosts entry '${host}' — not a hostname"
                continue ;;
        esac
        printf '    "%s" 1;\n' "$host"
    done < <(jq -r '.geo_exempt_hosts // [] | .[]' "$OPTIONS")
}

# geo/map-Block bauen.
#
#   $npmplus_geo_ban    1 = Adresse steht auf der eigenen Sperrliste
#   $npmplus_geo_hit    1 = Land soll gesperrt werden
#   $npmplus_geo_exempt 1 = dieser Hostname ist von der Ländersperre ausgenommen
#   $npmplus_geo_acme   1 = ACME-Challenge, nie sperren
#
# Der letzte map fasst die Ländersperre zu einer Entscheidung zusammen: nur die
# Kombination "gesperrtes Land, kein Ausnahme-Host, keine Challenge" führt zu
# 403. Die Sperrliste einzelner Adressen läuft bewusst daran vorbei und gilt
# auch auf ausgenommenen Hostnamen.
#
# $1 leer = keine Ländersperre, nur die Sperrliste einzelner Adressen.
geo_write_conf() {
    local default_hit="$1"
    {
        printf 'geo $npmplus_geo_ban {\n'
        printf '    default 0;\n'
        geo_ip_lines geo_deny_ips 1
        printf '}\n\n'

        if [ -n "$default_hit" ]; then
            # Reihenfolge egal: im geo-Modul gewinnt immer der genauere
            # Eintrag. Eine einzelne Adresse schlägt damit den Länderblock,
            # in dem sie liegt.
            printf 'geo $npmplus_geo_hit {\n'
            printf '    default %s;\n' "$default_hit"
            printf '    include %s;\n' "$GEO_RANGES"
            geo_ip_lines geo_allow_ips 0
            printf '}\n\n'
            printf 'map $host $npmplus_geo_exempt {\n'
            printf '    default 0;\n'
            geo_host_lines
            printf '}\n\n'
            # Let's Encrypt validiert aus den USA. Ohne diese Ausnahme wären
            # Erstausstellung und Verlängerung im Erlaubnismodus tot.
            printf 'map $uri $npmplus_geo_acme {\n'
            printf '    default 0;\n'
            printf '    "~^/\\.well-known/acme-challenge/" 1;\n'
            printf '}\n\n'
            printf 'map "$npmplus_geo_hit$npmplus_geo_exempt$npmplus_geo_acme" $npmplus_geo_deny {\n'
            printf '    default 0;\n'
            printf '    "100" 1;\n'
            printf '}\n\n'
        else
            # Ohne Ländersperre muss die Variable trotzdem existieren, damit
            # server_http.conf in beiden Fällen gleich aussehen kann.
            printf 'map $npmplus_geo_ban $npmplus_geo_deny {\n'
            printf '    default 0;\n'
            printf '}\n\n'
        fi

        # Zweiter Baum, diesmal mit dem Ländercode als Wert. Kostet denselben
        # Speicher noch einmal und dient allein der Protokollspalte.
        #
        # Im Erlaubnismodus stehen dort nur die freigegebenen Länder — für eine
        # gesperrte Anfrage bleibt deshalb "-" übrig. Das ist keine Panne: die
        # Listen der übrigen 200 Länder wurden nie geladen.
        if [ "$GEO_LOG_COUNTRY_OPT" = "true" ] && [ -s "$GEO_COUNTRY_CONF" ]; then
            printf 'geo $npmplus_geo_country {\n'
            printf '    default "-";\n'
            printf '    include %s;\n' "$GEO_COUNTRY_CONF"
            printf '}\n\n'
        else
            printf 'map $npmplus_geo_ban $npmplus_geo_country {\n'
            printf '    default "-";\n'
            printf '}\n\n'
        fi

        printf 'map "$npmplus_geo_ban$npmplus_geo_deny" $npmplus_geo_blocked {\n'
        printf '    default 1;\n'
        printf '    "00" 0;\n'
        printf '}\n\n'
        # Bewusst $time_iso8601 statt $time_local: letzteres enthält ein
        # Leerzeichen vor der Zeitzone und verschiebt damit jede Spaltennummer
        # in awk um eins. So steht das Land verlässlich in Spalte 4.
        printf 'log_format npmplus_geo '"'"'$time_iso8601 $host $remote_addr $npmplus_geo_country "$request" $status "$http_user_agent"'"'"';\n'
    } > "$GEO_HTTP"
}

# Vorlage für die Sperrseite. Wird nur angelegt, wenn es noch keine gibt —
# eigene Änderungen an der Datei bleiben damit über Updates hinweg erhalten.
geo_write_page() {
    [ -s "$GEO_PAGE" ] && return 0
    cat > "$GEO_PAGE" <<'HTML'
<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zugriff gesperrt / Access denied</title>
<style>
  :root { color-scheme: light dark; }
  body {
    margin: 0; min-height: 100vh; display: flex; align-items: center;
    justify-content: center; padding: 2rem;
    font: 16px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif;
    background: #f4f4f5; color: #18181b;
  }
  @media (prefers-color-scheme: dark) {
    body { background: #18181b; color: #e4e4e7; }
    .card { background: #27272a !important; border-color: #3f3f46 !important; }
    .hint { color: #a1a1aa !important; }
  }
  .card {
    max-width: 34rem; background: #fff; border: 1px solid #e4e4e7;
    border-radius: .75rem; padding: 2rem;
  }
  h1 { margin: 0 0 .25rem; font-size: 1.35rem; }
  h2 { margin: 1.75rem 0 .25rem; font-size: 1.1rem; font-weight: 600; }
  p { margin: .5rem 0; }
  .hint { color: #52525b; font-size: .9rem; margin-top: 1.75rem; }
</style>
</head>
<body>
  <div class="card">
    <h1>Zugriff gesperrt</h1>
    <p>Diese Seite nimmt derzeit keine Anfragen aus deiner Region entgegen.</p>
    <p>Wenn du meinst, dass das ein Versehen ist, wende dich bitte an den Betreiber der Seite und nenne ihm den Zeitpunkt sowie deine IP-Adresse.</p>

    <h2>Access denied</h2>
    <p>This site currently does not accept requests from your region.</p>
    <p>If you believe this is a mistake, please contact the site owner and mention the time of your visit and your IP address.</p>

    <p class="hint">HTTP 403</p>
  </div>
</body>
</html>
HTML
    chmod 644 "$GEO_PAGE"
    log "Block page created at ${GEO_PAGE} — edit it to your liking, it is never overwritten"
}

# Passen die vorhandenen Listen noch zur Konfiguration und sind sie jung genug?
# Dann sparen wir den Download und starten sofort. Der Hintergrundlauf holt
# frische Listen ohnehin.
geo_cache_valid() {
    [ -s "$GEO_RANGES" ] || return 1
    [ -f "$GEO_META" ] || return 1
    [ "$(cat "$GEO_META" 2>/dev/null)" = "$GEO_SIG" ] || return 1
    if [ "$GEO_LOG_COUNTRY_OPT" = "true" ] && [ ! -s "$GEO_COUNTRY_CONF" ]; then
        return 1
    fi
    # Auffrischen abgeschaltet: dann gilt die vorhandene Liste ohne Altersgrenze.
    [ "${GEO_REFRESH_OPT:-0}" -gt 0 ] 2>/dev/null || return 0
    find "$GEO_RANGES" -mmin "-$((GEO_REFRESH_OPT * 60))" 2>/dev/null | grep -q . || return 1
    return 0
}

mkdir -p "$GEO_DIR" "$CUSTOM_NGINX"

# Fertige Länderauswahl. Nur eine Abkürzung für geo_countries — was hier
# herauskommt, landet in derselben Liste und lässt sich dort ergänzen.
#
# high_risk: Herkunftsländer, aus denen bei einem privaten Server praktisch
# nur automatisierte Zugriffe kommen. Bewusst NICHT enthalten sind die großen
# Internetländer mit vielen echten Nutzern (IN, BR, MX, ID, TR) — der Schaden
# durch ausgesperrte Besucher wiegt dort schwerer als der Gewinn. Wer sie
# trotzdem will, trägt sie zusätzlich in geo_countries ein.
geo_preset_countries() {
    case "$1" in
        high_risk)
            printf '%s' "cn ru kp ir pk bd vn my th ph ng gh za ar co eg" ;;
        *)
            printf '' ;;
    esac
}

GEO_COUNTRIES=""
geo_add_country() {
    local cc
    cc=$(trim "$1" | tr 'A-Z' 'a-z')
    [ -n "$cc" ] || return 0
    case "$cc" in
        [a-z][a-z]) ;;
        *) warn "Ignoring country entry '${cc}' — expected a two-letter country code like 'cn'"; return 0 ;;
    esac
    # Doppelte vermeiden: Vorauswahl und eigene Liste überschneiden sich leicht,
    # ein Land zweimal im geo-Block wäre nur unnötige Arbeit für nginx.
    case " ${GEO_COUNTRIES}" in
        *" ${cc} "*) return 0 ;;
    esac
    GEO_COUNTRIES="${GEO_COUNTRIES}${cc} "
}

case "$GEO_PRESET_OPT" in
    none|"") ;;
    high_risk)
        case "$GEO_MODE_OPT" in
            allow)
                warn "geo_preset '${GEO_PRESET_OPT}' is meant for geo_mode 'block' — ignoring it, otherwise it would be an allow list"
                ;;
            off)
                # Häufigster Bedienfehler: Vorauswahl gesetzt, Schalter vergessen.
                warn "geo_preset '${GEO_PRESET_OPT}' is set, but geo_mode is 'off' — nothing is blocked. Set geo_mode to 'block' to activate it"
                ;;
            *)
                for cc in $(geo_preset_countries "$GEO_PRESET_OPT"); do
                    geo_add_country "$cc"
                done
                log "Country preset '${GEO_PRESET_OPT}' adds $(printf '%s' "$GEO_COUNTRIES" | wc -w) countries"
                ;;
        esac
        ;;
    *)
        warn "Unknown geo_preset '${GEO_PRESET_OPT}' — ignoring it" ;;
esac

while IFS= read -r cc; do
    geo_add_country "$cc"
done < <(jq -r '.geo_countries // [] | .[]' "$OPTIONS")

if [ "$GEO_MODE_OPT" = "off" ] && [ -n "$GEO_COUNTRIES" ]; then
    warn "geo_countries is filled, but geo_mode is 'off' — nothing is blocked. Set geo_mode to 'block' to activate it"
fi

GEO_ACTIVE=false
case "$GEO_MODE_OPT" in
    block|allow)
        if [ -z "$GEO_COUNTRIES" ]; then
            warn "geo_mode is '${GEO_MODE_OPT}' but no country is selected — set geo_preset or geo_countries. Country filter stays OFF"
        else
            # block: alles erlaubt, gelistete Länder sperren.
            # allow: alles gesperrt, gelistete Länder freigeben.
            if [ "$GEO_MODE_OPT" = "block" ]; then
                GEO_DEFAULT=0; GEO_MARK=1
            else
                GEO_DEFAULT=1; GEO_MARK=0
            fi
            GEO_SIG="mode=${GEO_MODE_OPT} mark=${GEO_MARK} country_log=${GEO_LOG_COUNTRY_OPT} countries=${GEO_COUNTRIES}"
            # shellcheck disable=SC2086
            if geo_cache_valid; then
                log "Country lists on disk are still current ($(grep -c ';' "$GEO_RANGES") ranges) — skipping download"
                GEO_ACTIVE=true
            elif geo_fetch "$GEO_MARK" "$GEO_RANGES" $GEO_COUNTRIES; then
                GEO_ACTIVE=true
            elif [ -s "$GEO_RANGES" ]; then
                warn "Country lists could not be downloaded — keeping the previous lists"
                GEO_ACTIVE=true
            else
                warn "Country lists could not be downloaded and none are cached — country filter stays OFF"
            fi
        fi
        ;;
    off)
        ;;
    *)
        warn "Unknown geo_mode '${GEO_MODE_OPT}' — country filter stays OFF"
        ;;
esac

# Die Sperrliste einzelner Adressen ist von der Ländersperre unabhängig und
# funktioniert auch bei geo_mode "off".
GEO_DENY_COUNT=$(jq -r '[.geo_deny_ips // [] | .[] | select(. != "")] | length' "$OPTIONS")

if [ "$GEO_ACTIVE" = "true" ] || [ "$GEO_DENY_COUNT" -gt 0 ]; then
    if [ "$GEO_ACTIVE" = "true" ]; then
        geo_write_conf "$GEO_DEFAULT"
        log "Country filter active (${GEO_MODE_OPT}): $(printf '%s' "$GEO_COUNTRIES" | tr ' ' ',' | sed 's/,$//'), $(grep -c ';' "$GEO_RANGES") ranges"
    else
        geo_write_conf ""
    fi
    [ "$GEO_DENY_COUNT" -gt 0 ] && log "IP deny list active: ${GEO_DENY_COUNT} entries"

    # Gesperrte Anfragen in eine eigene Datei protokollieren. Das reguläre
    # Access-Log von NPMplus bleibt daneben unangetastet.
    GEO_SERVER_CONF="access_log ${GEO_BLOCK_LOG} npmplus_geo if=\$npmplus_geo_blocked;"

    if [ "$GEO_DENY_ACTION_OPT" = "444" ]; then
        # 444 ist nginx-eigen: Verbindung schließen, ohne eine einzige Zeile zu
        # antworten. Eine Seite gibt es dann naturgemäß nicht.
        GEO_SERVER_CONF="${GEO_SERVER_CONF}
if (\$npmplus_geo_ban) { return 444; }
if (\$npmplus_geo_deny) { return 444; }"
    else
        geo_write_page
        # Umweg über einen eigenen Code statt direkt 403: ein "error_page 403"
        # würde auch die 403 von CrowdSec und von Zugriffslisten abfangen und
        # deren Seiten durch unsere ersetzen. 460 gehört dagegen nur uns.
        GEO_SERVER_CONF="${GEO_SERVER_CONF}
if (\$npmplus_geo_ban) { return 460; }
if (\$npmplus_geo_deny) { return 460; }
error_page 460 =403 /npmplus-geo-blocked.html;
location = /npmplus-geo-blocked.html { internal; alias ${GEO_PAGE}; }"
    fi

    geo_include "$CUSTOM_NGINX/http_top.conf" "include ${GEO_HTTP};"
    geo_include "$CUSTOM_NGINX/server_http.conf" "$GEO_SERVER_CONF"
    log "Blocked requests are logged to ${GEO_BLOCK_LOG} (response: ${GEO_DENY_ACTION_OPT})"
else
    # Auch im ausgeschalteten Zustand aufräumen, sonst bliebe eine einmal
    # gesetzte Sperre nach dem Umstellen auf "off" weiter aktiv.
    geo_strip "$CUSTOM_NGINX/http_top.conf"
    geo_strip "$CUSTOM_NGINX/server_http.conf"
    rm -f "$GEO_HTTP"
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

# Die Registries verschieben laufend Adressblöcke. Ohne Auffrischung sperrt die
# Liste nach einigen Monaten die Falschen aus. Erst nach dem Start, damit ein
# hängender Download den Start des Proxys nicht verzögert.
if [ "$GEO_ACTIVE" = "true" ] && [ "${GEO_REFRESH_OPT:-0}" -gt 0 ] 2>/dev/null; then
    (
        while sleep "$((GEO_REFRESH_OPT * 3600))"; do
            before=$(md5sum "$GEO_RANGES" 2>/dev/null | cut -d' ' -f1)
            # shellcheck disable=SC2086
            geo_fetch "$GEO_MARK" "$GEO_RANGES" $GEO_COUNTRIES || continue
            after=$(md5sum "$GEO_RANGES" 2>/dev/null | cut -d' ' -f1)
            # Ein Reload wirft alle Worker neu an — nur bei echter Änderung.
            if [ "$before" != "$after" ]; then
                nginx -s reload 2>/dev/null \
                    && log "Country lists updated, nginx reloaded" \
                    || warn "Country lists updated, but nginx reload failed"
            fi
        done
    ) &
    GEO_PID=$!
    log "Country lists are refreshed every ${GEO_REFRESH_OPT} h"
fi

###############################################################################
# CrowdSec-Nachzügler
#
# Der Supervisor startet alle Add-ons der Stufe "services" ohne feste
# Reihenfolge. Kommt NPMplus vor CrowdSec dran, antwortet die LAPI bei der
# Vorflugkontrolle noch nicht — der Bouncer bliebe dann bis zum nächsten
# Add-on-Neustart aus, obwohl CrowdSec kurz darauf läuft. Genau das passiert
# nach jedem Neustart von Home Assistant OS.
#
# Deshalb hier im Hintergrund weiterfragen. Bewusst erst nach dem Start des
# Proxys: das Warten darf nginx nicht aufhalten, sonst ist die gesamte
# Weiterleitung minutenlang tot.
#
# Scharfgeschaltet wird per Add-on-Neustart, NICHT per "nginx -s reload".
# Gemessen am laufenden System: nach dem Reload holte der Bouncer keine einzige
# Entscheidung ab, erst ein Neustart des Add-ons von Hand brachte ihn zum
# Leben. Das Add-on meldete den Reload trotzdem als Erfolg.
#
# An fehlenden Hooks liegt es nicht — conf.d/crowdsec.conf mit cs.init() steckt
# unabhängig von ENABLED in der nginx-Konfiguration. Wo genau der alte Zustand
# den Reload übersteht (init_by_lua, das shared dict crowdsec_cache, oder die
# noch offenen alten Worker), ist nicht ermittelt. Für das Ergebnis egal: nur
# der Neustart ist nachweislich wirksam, also wird neu gestartet.
###############################################################################

# Neustart über die Supervisor-API. /addons/self/restart ist mit dem eigenen
# Token erreichbar, hassio_api: true steht in config.yaml.
cs_restart_addon() {
    [ -n "${SUPERVISOR_TOKEN:-}" ] || return 1
    curl -s -m 30 -X POST         -H "Authorization: Bearer ${SUPERVISOR_TOKEN}"         "http://supervisor/addons/self/restart" >/dev/null 2>&1
}
if [ "$CS_RETRY_WANTED" = "true" ] && [ "${CS_RETRY_OPT:-0}" -gt 0 ] 2>/dev/null; then
    (
        CS_DEADLINE=$(( $(date +%s) + CS_RETRY_OPT * 60 ))
        while [ "$(date +%s)" -lt "$CS_DEADLINE" ]; do
            sleep 30
            case "$(check_lapi "$CS_LAPI_OPT" "$CS_KEY_OPT")" in
                200|404)
                    cs_apply_conf
                    if [ "$CS_RETRY_RESTART_OPT" != "true" ]; then
                        warn "CrowdSec is up now and crowdsec.conf was written, but"
                        warn "crowdsec_retry_restart is off — the bouncer stays inactive until"
                        warn "the add-on is restarted by hand. A reload is not enough."
                        exit 0
                    fi
                    # Schleifenbremse: flackert CrowdSec, würde sich das Add-on
                    # sonst im Minutentakt selbst neu starten. Ein Stempel je
                    # Neustart, frühestens alle 10 Minuten wieder.
                    CS_STAMP=/data/crowdsec/.retry_restart
                    CS_NOW=$(date +%s)
                    CS_LAST=$(cat "$CS_STAMP" 2>/dev/null || echo 0)
                    case "$CS_LAST" in *[!0-9]*|"") CS_LAST=0 ;; esac
                    if [ "$(( CS_NOW - CS_LAST ))" -lt 600 ]; then
                        warn "CrowdSec is up now, but the add-on already restarted for this"
                        warn "less than 10 min ago — not restarting again. If CrowdSec keeps"
                        warn "flapping, restart the add-on by hand once it is stable."
                        exit 0
                    fi
                    echo "$CS_NOW" > "$CS_STAMP" 2>/dev/null || true
                    log "CrowdSec is up now — restarting the add-on to activate the bouncer"
                    if cs_restart_addon; then
                        # Der Supervisor schickt gleich SIGTERM. Hier nichts mehr tun.
                        exit 0
                    fi
                    warn "CrowdSec is up now and crowdsec.conf was written, but the restart"
                    warn "via the Supervisor failed. Restart the add-on by hand — without it"
                    warn "the bouncer fetches no decisions at all."
                    exit 0
                    ;;
            esac
        done
        warn "CrowdSec still unreachable after ${CS_RETRY_OPT} min — bouncer stays OFF."
        warn "Check the address in crowdsec_lapi_url and whether the CrowdSec add-on is running."
    ) &
    CS_RETRY_PID=$!
    log "CrowdSec was not reachable at start — retrying every 30 s for up to ${CS_RETRY_OPT} min"
fi

_term() {
    log "SIGTERM received, stopping NPMplus..."
    kill -TERM "$APP_PID" 2>/dev/null || true
    [ -n "${TAIL_PID:-}" ] && kill -TERM "$TAIL_PID" 2>/dev/null || true
    [ -n "${GEO_PID:-}" ] && kill -TERM "$GEO_PID" 2>/dev/null || true
    [ -n "${CS_RETRY_PID:-}" ] && kill -TERM "$CS_RETRY_PID" 2>/dev/null || true
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
[ -n "${GEO_PID:-}" ] && kill -TERM "$GEO_PID" 2>/dev/null || true
[ -n "${CS_RETRY_PID:-}" ] && kill -TERM "$CS_RETRY_PID" 2>/dev/null || true
exit "$APP_EXIT"
