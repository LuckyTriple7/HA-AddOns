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

# /config/data VOR dem Start von /init erstellen und mit korrekten Rechten versehen.
# Wichtig: LinuxServer's Init-Skripte erwarten dieses Verzeichnis bereits beim Start.
DATA_DIR="/config/data"
mkdir -p "${DATA_DIR}"
chown "${PUID}:${PGID}" "${DATA_DIR}"
chmod 750 "${DATA_DIR}"

# /tmp/.X11-unix vorab erstellen (als root), damit xfce4-session (läuft als abc/uid 1000)
# keinen eigenen Erstellungsversuch unternimmt – der wegen euid!=0 scheitern würde.
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix

# An LinuxServer's s6-overlay übergeben (PID-Übergabe mit exec)
exec /init
