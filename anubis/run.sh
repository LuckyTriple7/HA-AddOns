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
SE_SNIPPET=/policy.search-engines.yaml
SE_MARK_BEGIN="  # >>> anubis-addon search-engines >>>"
SE_MARK_END="  # <<< anubis-addon search-engines <<<"
mkdir -p /data
if [ ! -f "$POLICY_FILE" ]; then
    cp /policy.default.yaml "$POLICY_FILE"
    log "Default policy written to $POLICY_FILE — edit and restart the add-on to customize"
fi

###############################################################################
# Suchmaschinen-Freigabe (Option allow_search_engines)
#
# Googlebot & Bingbot lösen keine JavaScript-Proof-of-Work — ohne Ausnahme
# challenged die catch-all-Regel auch sie, und eine aktivierte Domain
# verschwindet schleichend aus der Suche. Der Block zwischen den Markern
# unten in /data/policy.yaml wird bei jedem Start neu geschrieben: eigene
# Regeln dort gehen beim nächsten Neustart verloren, alles außerhalb der
# Marker bleibt unangetastet. Kein (data)/-Import (siehe policy.default.yaml)
# — die Regeln liegen wörtlich in policy.search-engines.yaml im Image.
###############################################################################
awk -v b="$SE_MARK_BEGIN" -v e="$SE_MARK_END" '
    $0 == b { skip = 1; next }
    $0 == e { skip = 0; next }
    skip == 1 { next }
    { print }
' "$POLICY_FILE" > "${POLICY_FILE}.tmp"

if [ "$ALLOW_SEARCH_ENGINES_OPT" = "true" ]; then
    awk -v b="$SE_MARK_BEGIN" -v e="$SE_MARK_END" -v snip="$SE_SNIPPET" '
        { print }
        $0 == "bots:" {
            print b
            while ((getline line < snip) > 0) print line
            close(snip)
            print e
        }
    ' "${POLICY_FILE}.tmp" > "$POLICY_FILE"
    rm -f "${POLICY_FILE}.tmp"
    log "allow_search_engines is on — Googlebot and Bingbot are exempt from the challenge"
else
    mv "${POLICY_FILE}.tmp" "$POLICY_FILE"
    log "allow_search_engines is off — every client, including search engines, gets challenged"
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
