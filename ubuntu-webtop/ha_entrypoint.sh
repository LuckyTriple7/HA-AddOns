#!/bin/bash
# Wird als erstes ausgeführt – liest HA-Optionen aus options.json
# und übergibt sie als Umgebungsvariablen an LinuxServer's s6-init.

set -e

OPTIONS_FILE="/data/options.json"

if [ -f "${OPTIONS_FILE}" ]; then
    PUID=$(jq -r '.PUID // "1000"' "${OPTIONS_FILE}")
    PGID=$(jq -r '.PGID // "1000"' "${OPTIONS_FILE}")
    TZ=$(jq -r '.TZ // "UTC"' "${OPTIONS_FILE}")
    PASSWORD=$(jq -r '.PASSWORD // ""' "${OPTIONS_FILE}")
    KEYBOARD=$(jq -r '.KEYBOARD // ""' "${OPTIONS_FILE}")
    DRINODE=$(jq -r '.DRINODE // ""' "${OPTIONS_FILE}")

    export PUID PGID TZ

    [ -n "${PASSWORD}" ]  && export PASSWORD
    [ -n "${KEYBOARD}" ]  && export KEYBOARD
    [ -n "${DRINODE}" ]   && export DRINODE
else
    echo "[ubuntu-webtop] Warnung: ${OPTIONS_FILE} nicht gefunden, benutze Standardwerte."
fi

# An LinuxServer's s6-overlay übergeben (PID-Übergabe mit exec)
exec /init
