#!/usr/bin/env bash
# Add-on-Entrypoint: übersetzt /data/options.json in die Environment-Variablen
# von Anubis und startet das mitgebrachte Binary.
set -e

OPTIONS=/data/options.json

log()  { echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

opt() { jq -r --arg k "$1" --arg d "$2" 'if has($k) and (.[$k] != null) then .[$k] else $d end' "$OPTIONS"; }

TZ_OPT=$(opt TZ "Europe/Berlin")
LOG_LEVEL_OPT=$(opt log_level "info")

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
# schreibt sie nie wieder darüber.
###############################################################################
POLICY_FILE=/data/policy.yaml
mkdir -p /data
if [ ! -f "$POLICY_FILE" ]; then
    cp /policy.default.yaml "$POLICY_FILE"
    log "Default policy written to $POLICY_FILE — edit and restart the add-on to customize"
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
