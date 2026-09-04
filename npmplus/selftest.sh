#!/usr/bin/env bash
###############################################################################
# Selbsttest des Add-ons.
#
# Fasst die Prüfbefehle aus der Dokumentation zusammen, die sich im Container
# selbst beantworten lassen: Optionen, Bouncer-Konfiguration, Erreichbarkeit von
# LAPI und AppSec, Logs, Zertifikatslaufzeiten. Aufruf von außen:
#
#   docker exec <npmplus-container> /selftest.sh
#
# Rückgabewert: 0 wenn nichts fehlschlägt, sonst 1. Warnungen allein ändern den
# Rückgabewert nicht — sie beschreiben Zustände, die gewollt sein können.
#
# Die Ausgabe ist englisch, wie das Add-on-Protokoll auch. Kommentare im
# Quelltext bleiben deutsch.
###############################################################################
set -uo pipefail

OPTIONS=/data/options.json
CS_CONF=/data/crowdsec/crowdsec.conf
LOG_DIR=/data/nginx/logs

FAILED=0

ok()   { printf '[ ok ] %s\n' "$*"; }
warn() { printf '[warn] %s\n' "$*"; }
fail() { printf '[FAIL] %s\n' "$*"; FAILED=$((FAILED + 1)); }
head_() { printf '\n== %s\n' "$*"; }

opt() {
    [ -f "$OPTIONS" ] || { printf '%s' "$2"; return; }
    jq -r --arg k "$1" --arg d "$2" \
        'if has($k) and (.[$k] != null) then .[$k] else $d end' "$OPTIONS" 2>/dev/null \
        || printf '%s' "$2"
}

conf() {
    [ -f "$CS_CONF" ] || return 1
    local v
    v=$(grep -m1 "^${1}=" "$CS_CONF" 2>/dev/null) || return 1
    printf '%s' "${v#*=}"
}

host_of_url() {
    local u="${1#*://}"
    u="${u%%/*}"
    printf '%s' "${u%%:*}"
}

is_container_ip() {
    [[ "$1" =~ ^172\.(1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+$ ]]
}

###############################################################################
head_ "Container"
###############################################################################
OWN_HOST=$(cat /etc/hostname 2>/dev/null | tr -d '\r\n')
if [ -n "$OWN_HOST" ]; then
    ok "Hostname: ${OWN_HOST}"
    ok "journald identifier for the CrowdSec acquisition: app_${OWN_HOST//-/_}"
else
    warn "hostname not readable — identifier for the acquisition unknown"
fi

if [ -f "$OPTIONS" ]; then
    ok "options read: ${OPTIONS}"
else
    fail "${OPTIONS} is missing — is this the right container?"
fi

###############################################################################
head_ "Ports and web interface"
###############################################################################
ADMIN_PORT=$(opt admin_port 81)
UI_CODE=$(curl -sk -o /dev/null -m 5 -w '%{http_code}' "https://127.0.0.1:${ADMIN_PORT}/api/" 2>/dev/null || true)
case "${UI_CODE:-000}" in
    000) fail "web interface on port ${ADMIN_PORT} does not answer" ;;
    200) ok "web interface on port ${ADMIN_PORT} answers (HTTP 200)" ;;
    *)   warn "web interface on port ${ADMIN_PORT} answers with HTTP ${UI_CODE}" ;;
esac

###############################################################################
head_ "Logs"
###############################################################################
if [ -L "$LOG_DIR" ]; then
    ok "logs linked to $(readlink "$LOG_DIR") (share_logs on)"
elif [ -d "$LOG_DIR" ]; then
    ok "logs kept in ${LOG_DIR} (share_logs off)"
else
    fail "${LOG_DIR} does not exist"
fi

if [ -f "$LOG_DIR/access.log" ]; then
    AGE=$(( $(date +%s) - $(stat -c %Y "$LOG_DIR/access.log" 2>/dev/null || echo 0) ))
    if [ "$AGE" -lt 3600 ]; then
        ok "access.log last written ${AGE} s ago"
    else
        warn "access.log unchanged for ${AGE} s — is any traffic arriving?"
    fi
else
    warn "access.log is missing — without an access log CrowdSec sees nothing"
fi

###############################################################################
head_ "Trusted proxies"
###############################################################################
TRUST_IP=$(opt trust_ip "")
TRUST_CF=$(opt trust_cloudflare false)
[ -n "$TRUST_IP" ] && ok "trust_ip: ${TRUST_IP}" || ok "trust_ip: not set"
ok "trust_cloudflare: ${TRUST_CF}"

###############################################################################
head_ "CrowdSec"
###############################################################################
CS_ENABLED_OPT=$(opt crowdsec_enabled false)
if [ "$CS_ENABLED_OPT" != "true" ]; then
    ok "crowdsec_enabled is off — CrowdSec checks skipped"
else
    if [ ! -f "$CS_CONF" ]; then
        fail "${CS_CONF} is missing although crowdsec_enabled is on"
    else
        CS_ON=$(conf ENABLED || echo "")
        CS_URL=$(conf API_URL || echo "")
        CS_KEY=$(conf API_KEY || echo "")
        CS_APPSEC=$(conf APPSEC_URL || echo "")
        CS_FALLBACK=$(conf FALLBACK_REMEDIATION || echo "")
        CS_CAPTCHA=$(conf CAPTCHA_PROVIDER || echo "")
        CS_APPSEC_FAIL=$(conf APPSEC_FAILURE_ACTION || echo "")

        if [ "$CS_ON" = "true" ]; then
            ok "bouncer active according to ${CS_CONF}"
        else
            fail "${CS_CONF} says ENABLED=${CS_ON:-<empty>} — the startup check turned the bouncer off, see the add-on log"
        fi

        if [ "${#CS_KEY}" -eq 0 ]; then
            fail "API_KEY is empty"
        elif [ "${#CS_KEY}" -eq 44 ]; then
            ok "API_KEY is 44 characters long (the length cscli generates)"
        else
            warn "API_KEY is ${#CS_KEY} characters long — cscli generates 44. Own keys via 'bouncers add -k' are shorter and fine"
        fi

        for pair in "API_URL:${CS_URL}" "APPSEC_URL:${CS_APPSEC}"; do
            name="${pair%%:*}"
            url="${pair#*:}"
            [ -n "$url" ] || continue
            h=$(host_of_url "$url")
            if is_container_ip "$h"; then
                warn "${name} points at the container IP ${h} — that changes on the next start. Use the container hostname or set the option to \"auto\""
            else
                ok "${name}: ${url}"
            fi
        done

        if [ -n "$CS_URL" ]; then
            LAPI_CODE=$(curl -s -o /dev/null -m 5 -w '%{http_code}' \
                -H "X-Api-Key: ${CS_KEY}" -A "npmplus-selftest/1.0" \
                "${CS_URL%/}/v1/decisions?ip=127.0.0.1" 2>/dev/null || true)
            case "${LAPI_CODE:-000}" in
                200|404) ok "LAPI answers and accepts the key (HTTP ${LAPI_CODE})" ;;
                401|403) fail "LAPI rejects the key (HTTP ${LAPI_CODE}) — the bouncer is probably in the wrong database, cscli needs -c" ;;
                000)     fail "LAPI at ${CS_URL} is unreachable" ;;
                *)       warn "LAPI answers with HTTP ${LAPI_CODE}" ;;
            esac
        else
            fail "API_URL is empty"
        fi

        if [ -n "$CS_APPSEC" ]; then
            APPSEC_CODE=$(curl -s -o /dev/null -m 5 -w '%{http_code}' \
                -A "npmplus-selftest/1.0" "${CS_APPSEC%/}/" 2>/dev/null || true)
            if [ "${APPSEC_CODE:-000}" = "000" ]; then
                fail "AppSec at ${CS_APPSEC} does not answer — the WAF check is skipped"
            else
                ok "AppSec answers (HTTP ${APPSEC_CODE}; 401 without a key is normal)"
            fi
        else
            ok "AppSec not configured"
        fi

        ok "CAPTCHA_PROVIDER: ${CS_CAPTCHA:-<empty, captcha off>}"
        ok "FALLBACK_REMEDIATION: ${CS_FALLBACK:-<image default>} (what the bouncer does if the LAPI fails)"
        case "${CS_APPSEC_FAIL:-}" in
            passthrough) ok "APPSEC_FAILURE_ACTION: passthrough (AppSec down = request goes through unchecked)" ;;
            deny)        warn "APPSEC_FAILURE_ACTION: deny — while AppSec is unreachable EVERY request is blocked. A restart of the CrowdSec add-on takes all services behind the proxy down with it" ;;
            *)           warn "APPSEC_FAILURE_ACTION: ${CS_APPSEC_FAIL:-<image default, deny>} — restart the add-on so it writes the value" ;;
        esac
    fi
fi

###############################################################################
head_ "Certificates"
###############################################################################
if command -v openssl >/dev/null 2>&1; then
    FOUND=0
    while IFS= read -r cert; do
        [ -n "$cert" ] || continue
        FOUND=1
        END=$(openssl x509 -enddate -noout -in "$cert" 2>/dev/null | cut -d= -f2)
        [ -n "$END" ] || continue
        END_TS=$(date -d "$END" +%s 2>/dev/null || echo 0)
        NAME=$(basename "$(dirname "$cert")")
        if [ "$END_TS" -eq 0 ]; then
            warn "${NAME}: expiry date not parsable (${END})"
            continue
        fi
        DAYS=$(( (END_TS - $(date +%s)) / 86400 ))
        if [ "$DAYS" -lt 0 ]; then
            DAYS_ABS=$(( -DAYS ))
            fail "${NAME}: expired ${DAYS_ABS} days ago"
        elif [ "$DAYS" -lt 3 ]; then
            warn "${NAME}: expires in ${DAYS} days"
        else
            ok "${NAME}: valid for another ${DAYS} days"
        fi
    done < <(find /data/tls -name fullchain.pem 2>/dev/null)
    [ "$FOUND" -eq 1 ] || ok "no certificates found under /data/tls"
else
    warn "openssl not in the image — certificate lifetimes cannot be checked"
fi

###############################################################################
printf '\n'
if [ "$FAILED" -eq 0 ]; then
    printf 'Result: nothing failed.\n'
    exit 0
fi
printf 'Result: %s check(s) failed.\n' "$FAILED"
exit 1
