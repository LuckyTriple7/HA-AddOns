#!/bin/bash
set -e

export PHONE_NUMBER=$(jq -r '.phone_number // ""' /data/options.json)
export WEBHOOK_INCOMING=$(jq -r '.webhook_incoming // ""' /data/options.json)
export NATIVE_MODE=$(jq -r 'if .native_mode == false then "false" else "true" end' /data/options.json)
export DARK_MODE=$(jq -r 'if .dark_mode == true then "true" else "false" end' /data/options.json)
export SIGNAL_API_URL=http://localhost:8080
export GIN_MODE=release
export DEBUG_MODE=$(jq -r 'if .debug_mode == true then "true" else "false" end' /data/options.json)
export DOWNLOAD_MEDIA=$(jq -r 'if .download_media == true then "true" else "false" end' /data/options.json)
export MEDIA_MAX_MB=$(jq -r '.media_max_mb // 500' /data/options.json)
export HA_NOTIFICATIONS=$(jq -r 'if .ha_notifications == true then "true" else "false" end' /data/options.json)
export HA_NOTIFICATIONS_PRIVACY=$(jq -r 'if .ha_notifications_privacy == true then "true" else "false" end' /data/options.json)

export SIGNAL_CLI_CONFIG_DIR=/config/signal-cli
mkdir -p /config/signal-cli

if [ -d /data/signal-cli ] && [ ! -f /config/signal-cli/.migrated ]; then
  cp -a /data/signal-cli/. /config/signal-cli/ 2>/dev/null || true
  touch /config/signal-cli/.migrated
fi
if [ -f /data/chats.json ] && [ ! -f /config/chats.json ]; then
  cp /data/chats.json /config/chats.json 2>/dev/null || true
fi
if [ -f /data/messages.json ] && [ ! -f /config/messages.json ]; then
  cp /data/messages.json /config/messages.json 2>/dev/null || true
fi
if [ -d /data/media ] && [ ! -d /config/media ]; then
  cp -a /data/media /config/media 2>/dev/null || true
fi

# signal-cli laeuft als Daemon (json-rpc): ein Dauerprozess statt eines neuen
# Prozesses pro REST-Aufruf. Der fruehere Modus "native" startete signal-cli
# rund 10.000-mal am Tag; jeder Start entpackte libsignal nach /tmp und schrieb
# account.db — gemessen 26 MB/s bzw. 2,2 TB Schreiblast pro Tag.
if [ "$NATIVE_MODE" = "true" ]; then
  export MODE=json-rpc-native
  echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Mode: json-rpc-native (Daemon, natives Binary)"
else
  export MODE=json-rpc
  echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Mode: json-rpc (Daemon, Java)"
fi

# Empfangene Nachrichten schickt signal-cli-rest-api per POST an server.js.
# Das Geheimnis im Pfad wird bei jedem Start neu gewuerfelt (siehe server.js).
export RECEIVE_TOKEN=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
export RECEIVE_WEBHOOK_URL="http://127.0.0.1:17777/internal/receive/$RECEIVE_TOKEN"

# Seit bbernhard 0.101 gibt es kein /entrypoint.sh mehr (s6-overlay statt dessen).
# Wie das alte entrypoint.sh: Datenordner an signal-api (1000) geben und Daemon
# und API ohne Capabilities als dieser Benutzer starten.
as_signal_api() {
  local caps
  caps="-cap_$(seq -s ',-cap_' 0 "$(cat /proc/sys/kernel/cap_last_cap)")"
  HOME=/home setpriv --reuid=1000 --regid=1000 --init-groups --inh-caps="$caps" "$@"
}

# jsonrpc2-helper schreibt jsonrpc2.yml und wird per exec zu "signal-cli daemon"
# (TCP 127.0.0.1:6001). Die JSON-Ausgabe auf stdout verwirft auch upstream.
run_signal_daemon() {
  as_signal_api jsonrpc2-helper >/dev/null
}

run_signal_api() {
  HOST_IP=$(hostname -I | awk '{print $1}') as_signal_api signal-cli-rest-api -signal-cli-config="$SIGNAL_CLI_CONFIG_DIR"
}

# Ersetzt die s6-Aufsicht des Basis-Images: faellt ein Prozess aus, startet er neu.
supervise() {
  local name="$1"
  while true; do
    if [ "$DEBUG_MODE" = "true" ]; then
      # Debug-Modus: ungefilterte Ausgabe inkl. GIN-Access-Logs
      "run_$name" || true
    else
      # Normal: GIN-Access-Logs und Info-Meldungen unterdruecken
      "run_$name" 2>&1 | grep --line-buffered -Ev '^\[GIN\] |level=info' || true
    fi
    echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] $name beendet, Neustart in 5 s"
    sleep 5
  done
}

chown -R 1000:1000 "$SIGNAL_CLI_CONFIG_DIR"

# Daemon und API erst starten, wenn server.js lauscht: der Daemon holt beim
# Start sofort die wartenden Nachrichten ab, und was dann nicht zugestellt
# werden kann, ist weg. Die Subshell wird vor "export PORT=17777" abgezweigt,
# damit signal-cli-rest-api bei PORT=8080 aus dem Basis-Image bleibt.
(
  until curl -s --max-time 2 -o /dev/null http://127.0.0.1:17777/api/status; do sleep 1; done
  echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Starting signal-cli daemon and signal-cli-rest-api (data: $SIGNAL_CLI_CONFIG_DIR)..."
  supervise signal_daemon &
  supervise signal_api &
  wait
) &

export PORT=17777
# Zweiter Listener: nur /api/*, nur mit Token (siehe server.js)
export API_PORT=17787
export API_ENABLED=$(jq -r 'if .api_enabled == true then "true" else "false" end' /data/options.json)
export API_TOKEN=$(jq -r '.api_token // ""' /data/options.json)
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Starting Signal UI on port $PORT..."
cd /ui
exec node server.js
