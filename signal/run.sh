#!/bin/bash
set -e

export PHONE_NUMBER=$(jq -r '.phone_number // ""' /data/options.json)
export WEBHOOK_INCOMING=$(jq -r '.webhook_incoming // ""' /data/options.json)
export NATIVE_MODE=$(jq -r 'if .native_mode == false then "false" else "true" end' /data/options.json)
export DARK_MODE=$(jq -r 'if .dark_mode == true then "true" else "false" end' /data/options.json)
export SIGNAL_API_URL=http://localhost:8080
export GIN_MODE=release

export SIGNAL_CLI_CONFIG_DIR=/data/signal-cli
mkdir -p /data/signal-cli

if [ "$NATIVE_MODE" = "true" ]; then
  export MODE=native
  echo "[INFO] Mode: native (niedrige CPU-Last)"
else
  echo "[INFO] Mode: default (Java pro API-Aufruf)"
fi

start_signal_api() {
  /entrypoint.sh &
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
