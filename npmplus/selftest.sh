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
    ok "journald-Identifier für die CrowdSec-Acquisition: app_${OWN_HOST//-/_}"
else
    warn "Hostname nicht lesbar — Identifier für die Acquisition unbekannt"
fi

if [ -f "$OPTIONS" ]; then
    ok "Optionen gelesen: ${OPTIONS}"
else
    fail "${OPTIONS} fehlt — läuft das Skript im richtigen Container?"
fi

###############################################################################
head_ "Ports und Oberfläche"
###############################################################################
ADMIN_PORT=$(opt admin_port 81)
UI_CODE=$(curl -sk -o /dev/null -m 5 -w '%{http_code}' "https://127.0.0.1:${ADMIN_PORT}/api/" 2>/dev/null || true)
case "${UI_CODE:-000}" in
    000) fail "Oberfläche auf Port ${ADMIN_PORT} antwortet nicht" ;;
    200) ok "Oberfläche auf Port ${ADMIN_PORT} antwortet (HTTP 200)" ;;
    *)   warn "Oberfläche auf Port ${ADMIN_PORT} antwortet mit HTTP ${UI_CODE}" ;;
esac

###############################################################################
head_ "Logs"
###############################################################################
if [ -L "$LOG_DIR" ]; then
    ok "Logs verlinkt nach $(readlink "$LOG_DIR") (share_logs an)"
elif [ -d "$LOG_DIR" ]; then
    ok "Logs liegen in ${LOG_DIR} (share_logs aus)"
else
    fail "${LOG_DIR} existiert nicht"
fi

if [ -f "$LOG_DIR/access.log" ]; then
    AGE=$(( $(date +%s) - $(stat -c %Y "$LOG_DIR/access.log" 2>/dev/null || echo 0) ))
    if [ "$AGE" -lt 3600 ]; then
        ok "access.log wurde vor ${AGE} s zuletzt beschrieben"
    else
        warn "access.log seit ${AGE} s unverändert — kommt überhaupt Verkehr an?"
    fi
else
    warn "access.log fehlt — ohne Zugriffslog sieht CrowdSec nichts"
fi

###############################################################################
head_ "Vertrauenswürdige Proxys"
###############################################################################
TRUST_IP=$(opt trust_ip "")
TRUST_CF=$(opt trust_cloudflare false)
[ -n "$TRUST_IP" ] && ok "trust_ip: ${TRUST_IP}" || ok "trust_ip: nicht gesetzt"
ok "trust_cloudflare: ${TRUST_CF}"

###############################################################################
head_ "CrowdSec"
###############################################################################
CS_ENABLED_OPT=$(opt crowdsec_enabled false)
if [ "$CS_ENABLED_OPT" != "true" ]; then
    ok "crowdsec_enabled ist aus — CrowdSec-Prüfungen übersprungen"
else
    if [ ! -f "$CS_CONF" ]; then
        fail "${CS_CONF} fehlt, obwohl crowdsec_enabled an ist"
    else
        CS_ON=$(conf ENABLED || echo "")
        CS_URL=$(conf API_URL || echo "")
        CS_KEY=$(conf API_KEY || echo "")
        CS_APPSEC=$(conf APPSEC_URL || echo "")
        CS_FALLBACK=$(conf FALLBACK_REMEDIATION || echo "")
        CS_CAPTCHA=$(conf CAPTCHA_PROVIDER || echo "")

        if [ "$CS_ON" = "true" ]; then
            ok "Bouncer aktiv laut ${CS_CONF}"
        else
            fail "Bouncer steht in ${CS_CONF} auf ENABLED=${CS_ON:-<leer>} — die Startprüfung hat ihn abgeschaltet, siehe Add-on-Protokoll"
        fi

        if [ "${#CS_KEY}" -eq 0 ]; then
            fail "API_KEY ist leer"
        elif [ "${#CS_KEY}" -eq 44 ]; then
            ok "API_KEY hat 44 Zeichen (Länge von cscli)"
        else
            warn "API_KEY hat ${#CS_KEY} Zeichen — cscli erzeugt 44. Eigene Schlüssel über 'bouncers add -k' sind kürzer und in Ordnung"
        fi

        for pair in "API_URL:${CS_URL}" "APPSEC_URL:${CS_APPSEC}"; do
            name="${pair%%:*}"
            url="${pair#*:}"
            [ -n "$url" ] || continue
            h=$(host_of_url "$url")
            if is_container_ip "$h"; then
                warn "${name} zeigt auf die Container-IP ${h} — die wechselt beim nächsten Start. Container-Hostname eintragen oder die Option auf \"auto\" setzen"
            else
                ok "${name}: ${url}"
            fi
        done

        if [ -n "$CS_URL" ]; then
            LAPI_CODE=$(curl -s -o /dev/null -m 5 -w '%{http_code}' \
                -H "X-Api-Key: ${CS_KEY}" -A "npmplus-selftest/1.0" \
                "${CS_URL%/}/v1/decisions?ip=127.0.0.1" 2>/dev/null || true)
            case "${LAPI_CODE:-000}" in
                200|404) ok "LAPI antwortet und akzeptiert den Schlüssel (HTTP ${LAPI_CODE})" ;;
                401|403) fail "LAPI lehnt den Schlüssel ab (HTTP ${LAPI_CODE}) — Bouncer steckt vermutlich in der falschen Datenbank, cscli braucht -c" ;;
                000)     fail "LAPI unter ${CS_URL} nicht erreichbar" ;;
                *)       warn "LAPI antwortet mit HTTP ${LAPI_CODE}" ;;
            esac
        else
            fail "API_URL ist leer"
        fi

        if [ -n "$CS_APPSEC" ]; then
            APPSEC_CODE=$(curl -s -o /dev/null -m 5 -w '%{http_code}' \
                -A "npmplus-selftest/1.0" "${CS_APPSEC%/}/" 2>/dev/null || true)
            if [ "${APPSEC_CODE:-000}" = "000" ]; then
                fail "AppSec unter ${CS_APPSEC} antwortet nicht — WAF-Prüfung fällt aus"
            else
                ok "AppSec antwortet (HTTP ${APPSEC_CODE}; ohne Schlüssel ist 401 normal)"
            fi
        else
            ok "AppSec nicht konfiguriert"
        fi

        ok "CAPTCHA_PROVIDER: ${CS_CAPTCHA:-<leer, Captcha aus>}"
        ok "FALLBACK_REMEDIATION: ${CS_FALLBACK:-<Vorgabe des Images>}"
    fi
fi

###############################################################################
head_ "Zertifikate"
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
            warn "${NAME}: Ablaufdatum nicht auswertbar (${END})"
            continue
        fi
        DAYS=$(( (END_TS - $(date +%s)) / 86400 ))
        if [ "$DAYS" -lt 0 ]; then
            fail "${NAME}: abgelaufen seit $(( -DAYS )) Tagen"
        elif [ "$DAYS" -lt 3 ]; then
            warn "${NAME}: läuft in ${DAYS} Tagen ab"
        else
            ok "${NAME}: noch ${DAYS} Tage gültig"
        fi
    done < <(find /data/tls -name fullchain.pem 2>/dev/null)
    [ "$FOUND" -eq 1 ] || ok "keine Zertifikate unter /data/tls gefunden"
else
    warn "openssl nicht im Image — Zertifikatslaufzeiten nicht prüfbar"
fi

###############################################################################
printf '\n'
if [ "$FAILED" -eq 0 ]; then
    printf 'Ergebnis: nichts fehlgeschlagen.\n'
    exit 0
fi
printf 'Ergebnis: %s Prüfung(en) fehlgeschlagen.\n' "$FAILED"
exit 1
