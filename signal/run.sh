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
export HA_NOTIFICATIONS=$(jq -r 'if .ha_notifications == true then "true" else "false" end' /data/options.json)
export HA_NOTIFICATIONS_PRIVACY=$(jq -r 'if .ha_notifications_privacy == true then "true" else "false" end' /data/options.json)
export HA_TOKEN=$(jq -r '.ha_token // ""' /data/options.json)

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

if [ "$NATIVE_MODE" = "true" ]; then
  export MODE=native
  echo "[INFO] Mode: native (niedrige CPU-Last)"
else
  echo "[INFO] Mode: default (Java pro API-Aufruf)"
fi

start_signal_api() {
  if [ "$DEBUG_MODE" = "true" ]; then
    # Debug-Modus: ungefilterte Ausgabe inkl. GIN-Access-Logs
    /entrypoint.sh &
  else
    # Normal: GIN-Access-Logs und signal-cli-Info-Meldungen unterdrücken
    /entrypoint.sh 2>&1 | grep -Ev '^\[GIN\] |level=info' &
  fi
  echo "[INFO] Waiting for signal-cli-rest-api on :8080..."
  for i in $(seq 1 60); do
    if curl -s --max-time 2 -o /dev/null http://localhost:8080/v1/about; then
      echo "[INFO] signal-cli-rest-api ready"
      return 0
    fi
    sleep 2
  done
}

echo "[INFO] Starting signal-cli-rest-api (data: $SIGNAL_CLI_CONFIG_DIR)..."
start_signal_api


export PORT=17777
echo "[INFO] Starting Signal UI on port $PORT..."
cd /ui
exec node server.js
