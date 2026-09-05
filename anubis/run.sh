#!/usr/bin/env bash
# Add-on-Entrypoint: übersetzt /data/options.json in die Environment-Variablen
# von Anubis und startet das mitgebrachte Binary.
set -e

OPTIONS=/data/options.json

log()  { echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

opt() { jq -r --arg k "$1" --arg d "$2" 'if has($k) and (.[$k] != null) then .[$k] else $d end' "$OPTIONS"; }

TZ_OPT=$(opt TZ "Europe/Berlin")
LOG_LEVEL_OPT=$(opt log_level "info")
ALLOW_SEARCH_ENGINES_OPT=$(opt allow_search_engines "true")
ALLOW_MONITORING_SERVICES_OPT=$(opt allow_monitoring_services "true")
AI_BOT_POLICY_OPT=$(opt ai_bot_policy "off")

export TZ="$TZ_OPT"

###############################################################################
# Policy-Datei
#
# Die eingebaute Standard-Policy von Anubis importiert Snippets aus
# (data)/..., die nur im Original-Image eingebettet liegen. Eine einzelne,
# gemountete Policy-Datei ohne diese Importe scheitert deshalb mit
# "invalid source file: (data)/...". Das Add-on liefert daher eine
# eigenständige, importfreie Policy mit (siehe policy.default.yaml) und legt
# sie beim ersten Start nach /data — danach frei editierbar, das Add-on
# schreibt sie nie wieder komplett darüber.
###############################################################################
POLICY_FILE=/data/policy.yaml
mkdir -p /data
if [ ! -f "$POLICY_FILE" ]; then
    cp /policy.default.yaml "$POLICY_FILE"
    log "Default policy written to $POLICY_FILE — edit and restart the add-on to customize"
fi

###############################################################################
# Verwaltete Regel-Blöcke
#
# Jeder Block lebt zwischen einem eigenen Marker-Paar in /data/policy.yaml und
# wird bei jedem Start komplett neu geschrieben — eigene Regeln zwischen den
# Markern gehen beim nächsten Neustart verloren, alles außerhalb bleibt
# unangetastet (gleiches Muster wie die Ländersperre in NPMplus).
#
# apply_managed_block <name> <snippet-datei-oder-leer>
#   1. entfernt den vorhandenen Block dieses Namens, egal wo er gerade steht
#   2. ist eine Snippet-Datei angegeben: fügt sie direkt nach dem Ende des
#      zuletzt verwalteten Blocks wieder ein (bzw. direkt nach "bots:", wenn
#      es noch keinen gibt) — ruft man alle Blöcke in fester Reihenfolge auf,
#      stehen sie danach unabhängig vom Vorzustand auch in dieser Reihenfolge
#   Alle so verwalteten Regeln stehen damit vor generic-browser/catch-all in
#   policy.default.yaml und werden entsprechend zuerst ausgewertet.
###############################################################################
apply_managed_block() {
    local name="$1" snippet="$2"
    local b="  # >>> anubis-addon ${name} >>>"
    local e="  # <<< anubis-addon ${name} <<<"

    awk -v b="$b" -v e="$e" '
        $0 == b { skip = 1; next }
        $0 == e { skip = 0; next }
        skip == 1 { next }
        { print }
    ' "$POLICY_FILE" > "${POLICY_FILE}.tmp"
    mv "${POLICY_FILE}.tmp" "$POLICY_FILE"

    [ -n "$snippet" ] || return 0

    local anchor
    anchor=$(grep -n '^  # <<< anubis-addon .* <<<$' "$POLICY_FILE" | tail -1 | cut -d: -f1)
    [ -n "$anchor" ] || anchor=$(grep -n '^bots:$' "$POLICY_FILE" | head -1 | cut -d: -f1)

    awk -v b="$b" -v e="$e" -v snip="$snippet" -v anchor="$anchor" '
        { print }
        NR == anchor {
            print b
            while ((getline line < snip) > 0) print line
            close(snip)
            print e
        }
    ' "$POLICY_FILE" > "${POLICY_FILE}.tmp"
    mv "${POLICY_FILE}.tmp" "$POLICY_FILE"
}

# --- Suchmaschinen (Google, Bing, DuckDuckGo, Qwant, Internet Archive, Kagi,
#     Marginalia, Mojeek, Common Crawl, Wikimedia, Arquivo.pt) ---------------
if [ "$ALLOW_SEARCH_ENGINES_OPT" = "true" ]; then
    apply_managed_block "search-engines" /policy.search-engines.yaml
    log "allow_search_engines is on — known search/archive crawlers are exempt from the challenge"
else
    apply_managed_block "search-engines" ""
    log "allow_search_engines is off — every client, including search engines, gets challenged"
fi

# --- Monitoring-Dienste (UptimeRobot, updown.io) ----------------------------
if [ "$ALLOW_MONITORING_SERVICES_OPT" = "true" ]; then
    apply_managed_block "monitoring" /policy.monitoring.yaml
    log "allow_monitoring_services is on — UptimeRobot and updown.io are exempt from the challenge"
else
    apply_managed_block "monitoring" ""
    log "allow_monitoring_services is off — monitoring services get challenged like anyone else"
fi

# --- KI-Bot-Stufe (aus, aggressiv, moderat, permissiv) ----------------------
case "$AI_BOT_POLICY_OPT" in
    aggressive)
        apply_managed_block "ai-bot-policy" /policy.ai-aggressive.yaml
        log "ai_bot_policy is aggressive — all known AI/LLM clients are denied, including on-demand fetches"
        ;;
    moderate)
        apply_managed_block "ai-bot-policy" /policy.ai-moderate.yaml
        log "ai_bot_policy is moderate — AI training crawlers denied, documented on-demand fetches allowed"
        ;;
    permissive)
        apply_managed_block "ai-bot-policy" /policy.ai-permissive.yaml
        log "ai_bot_policy is permissive — documented AI/LLM clients allowed, including training crawlers"
        ;;
    *)
        apply_managed_block "ai-bot-policy" ""
        log "ai_bot_policy is off — no AI-specific rules, the generic catch-all challenge applies"
        ;;
esac

# --- Frei eingetragene, vertraute IP-Bereiche (Option trusted_ip_ranges) ---
# Reines IP-ALLOW ohne User-Agent-Prüfung — bewusst so, das ist eine eigene,
# vom Betreiber selbst gewählte Freigabe (z.B. eigene Infrastruktur), keine
# Drittanbieter-Verifikation wie bei Suchmaschinen/Monitoring/KI-Bots oben.
TRUSTED_IPS_JSON=$(jq -c '.trusted_ip_ranges // []' "$OPTIONS")
TRUSTED_IPS_COUNT=$(echo "$TRUSTED_IPS_JSON" | jq 'length')
if [ "$TRUSTED_IPS_COUNT" -gt 0 ]; then
    {
        echo "  - name: trusted-ip-ranges"
        echo "    action: ALLOW"
        printf '    remote_addresses: %s\n' "$TRUSTED_IPS_JSON"
    } > /tmp/policy.trusted-ip-ranges.yaml
    apply_managed_block "trusted-ip-ranges" /tmp/policy.trusted-ip-ranges.yaml
    log "trusted_ip_ranges is set — ${TRUSTED_IPS_COUNT} range(s) are exempt from the challenge, no user-agent check"
else
    apply_managed_block "trusted-ip-ranges" ""
fi

# TARGET bleibt absichtlich ein einzelnes Leerzeichen: Anubis läuft damit im
# reinen Auth-Request-Modus für nginx' auth_request-Modul (kein eigenes
# Weiterreichen an ein Backend) — genau das Muster, das NPMplus über
# AUTH_REQUEST_ANUBIS_UPSTREAM erwartet.
export BIND=":8923"
export TARGET=" "
export POLICY_FNAME="$POLICY_FILE"
export SLOG_LEVEL="$LOG_LEVEL_OPT"

log "Anubis is starting on :8923 (policy=$POLICY_FILE, log_level=$LOG_LEVEL_OPT)"

exec /usr/local/bin/anubis
