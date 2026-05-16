#!/bin/bash
set -e

export PHONE_NUMBER=$(jq -r '.phone_number // ""' /data/options.json)
export WEBHOOK_INCOMING=$(jq -r '.webhook_incoming // ""' /data/options.json)
export SIGNAL_API_URL=http://localhost:8080

# Tell signal-cli-rest-api to store data directly in /data/signal-cli (HA persistent storage)
# This overrides the default /home/.local/share/signal-cli without needing a symlink
export SIGNAL_CLI_CONFIG_DIR=/data/signal-cli
export MODE=native
mkdir -p /data/signal-cli

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

echo "[INFO] Starting signal-cli-rest-api (data: $SIGNAL_CLI_CONFIG)..."
start_signal_api


export PORT=3002
echo "[INFO] Starting Signal UI on port $PORT..."
cd /ui
exec node server.js
