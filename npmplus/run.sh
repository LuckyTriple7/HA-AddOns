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
CS_CAPTCHA_PROVIDER_OPT=$(opt_trim crowdsec_captcha_provider "")
CS_CAPTCHA_SITE_OPT=$(opt_trim crowdsec_captcha_site_key "")
CS_CAPTCHA_SECRET_OPT=$(opt_trim crowdsec_captcha_secret_key "")
GEO_MODE_OPT=$(opt_trim geo_mode "off")
GEO_PRESET_OPT=$(opt_trim geo_preset "none")
GEO_REFRESH_OPT=$(opt geo_refresh_hours "24")
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
                # Captcha statt harter Sperre. Wirkt nur bei Entscheidungen vom
                # Typ "captcha" — die muss CrowdSec über seine profiles.yaml
                # ausstellen, sonst bleibt ein Ban ein Ban.
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
GEO_HTTP="$GEO_DIR/http.conf"
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
    local tmp raw cc file url code total=0 failed=0 count start
    tmp=$(mktemp); raw=$(mktemp)
    start=$(date +%s)
    log "Downloading country lists for $# countries from ipverse..."
    for cc in "$@"; do
        count=0
        for file in ipv4-aggregated ipv6-aggregated; do
            url="${GEO_IPVERSE_BASE}/${cc}/${file}.txt"
            code=$(curl -sL -m 30 -o "$raw" -w '%{http_code}' "$url" 2>/dev/null || true)
            case "${code:-000}" in
                200)
                    awk -v m="$mark" 'NF && $1 !~ /^#/ { print "    " $1 " " m ";" }' "$raw" >> "$tmp"
                    count=$((count + $(wc -l < "$raw")))
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
        rm -f "$tmp"
        warn "No country list could be downloaded"
        return 1
    fi
    mv "$tmp" "$target"
    chmod 644 "$target"
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
            printf '}\n'
        else
            # Ohne Ländersperre muss die Variable trotzdem existieren, damit
            # server_http.conf in beiden Fällen gleich aussehen kann.
            printf 'map $npmplus_geo_ban $npmplus_geo_deny {\n'
            printf '    default 0;\n'
            printf '}\n'
        fi
    } > "$GEO_HTTP"
}

mkdir -p "$GEO_DIR" "$CUSTOM_NGINX"

# Fertige Länderauswahl. Nur eine Abkürzung für geo_countries — was hier
# herauskommt, landet in derselben Liste und lässt sich dort ergänzen.
#
# high_risk: Herkunftsländer, aus denen im Betrieb eines privaten Servers
# nahezu ausschließlich automatisierte Angriffe kommen, plus die großen
# Bot-Netz-Regionen. Die Auswahl ist grob und trifft auch echte Besucher —
# wer Bekannte oder Dienste in einem dieser Länder hat, nimmt sie besser
# einzeln über geo_countries.
geo_preset_countries() {
    case "$1" in
        high_risk)
            printf '%s' "cn ru kp ir in pk bd vn id my th ph ng gh za br ar co mx tr eg" ;;
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
        if [ "$GEO_MODE_OPT" = "allow" ]; then
            warn "geo_preset '${GEO_PRESET_OPT}' is meant for geo_mode 'block' — ignoring it, otherwise it would be an allow list"
        else
            for cc in $(geo_preset_countries "$GEO_PRESET_OPT"); do
                geo_add_country "$cc"
            done
            log "Country preset '${GEO_PRESET_OPT}' adds $(printf '%s' "$GEO_COUNTRIES" | wc -w) countries"
        fi
        ;;
    *)
        warn "Unknown geo_preset '${GEO_PRESET_OPT}' — ignoring it" ;;
esac

while IFS= read -r cc; do
    geo_add_country "$cc"
done < <(jq -r '.geo_countries // [] | .[]' "$OPTIONS")

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
            # shellcheck disable=SC2086
            if geo_fetch "$GEO_MARK" "$GEO_RANGES" $GEO_COUNTRIES; then
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
    geo_include "$CUSTOM_NGINX/http_top.conf" "include ${GEO_HTTP};"
    geo_include "$CUSTOM_NGINX/server_http.conf" \
        'if ($npmplus_geo_ban) { return 403; }
if ($npmplus_geo_deny) { return 403; }'
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

_term() {
    log "SIGTERM received, stopping NPMplus..."
    kill -TERM "$APP_PID" 2>/dev/null || true
    [ -n "${TAIL_PID:-}" ] && kill -TERM "$TAIL_PID" 2>/dev/null || true
    [ -n "${GEO_PID:-}" ] && kill -TERM "$GEO_PID" 2>/dev/null || true
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
exit "$APP_EXIT"
