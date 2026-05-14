#!/bin/bash
# Wird als erstes ausgeführt – liest HA-Optionen aus options.json
# und übergibt sie als Umgebungsvariablen an LinuxServer's s6-init.

OPTIONS_FILE="/data/options.json"

# Standardwerte
PUID=1000
PGID=1000
TZ="UTC"

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
    export PUID PGID TZ
    echo "[ubuntu-webtop] Warnung: ${OPTIONS_FILE} nicht gefunden, benutze Standardwerte."
fi

# XDG_RUNTIME_DIR wird normalerweise von logind beim Login erstellt.
# Ohne dieses Verzeichnis bricht xfce4-session sofort mit SIGABRT ab.
XDG_RUNTIME_DIR="/run/user/${PUID}"
mkdir -p "${XDG_RUNTIME_DIR}"
chown "${PUID}:${PGID}" "${XDG_RUNTIME_DIR}"
chmod 700 "${XDG_RUNTIME_DIR}"
export XDG_RUNTIME_DIR

# /tmp/.X11-unix vorab als root erstellen damit X11-Clients (die als abc/uid 1000 laufen)
# nicht selbst versuchen das Verzeichnis anzulegen (schlägt fehl wegen euid!=0).
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix

# An LinuxServer's s6-overlay übergeben (PID-Übergabe mit exec)
exec /init
