#!/bin/bash
set -e

export PHONE_NUMBER=$(jq -r '.phone_number // ""' /data/options.json)
export WEBHOOK_INCOMING=$(jq -r '.webhook_incoming // ""' /data/options.json)
export SIGNAL_API_URL=http://localhost:8080

# Persist signal-cli data to /data (always mounted in HA)
# signal-cli-rest-api runs as user signal-api with HOME=/home → uses /home/.local/share/signal-cli
mkdir -p /data/signal-cli
mkdir -p /home/.local/share
if [ ! -L /home/.local/share/signal-cli ]; then
  rm -rf /home/.local/share/signal-cli
  ln -sf /data/signal-cli /home/.local/share/signal-cli
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

echo "[INFO] Starting signal-cli-rest-api..."
start_signal_api

# Health check: 500 on /v1/accounts means data is corrupt (e.g. left by incompatible mode)
ACCOUNTS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/v1/accounts)
if [ "$ACCOUNTS_STATUS" = "500" ]; then
  echo "[WARN] /v1/accounts returned 500 — clearing corrupt data and restarting..."
  pkill -f "signal-cli-rest-api" 2>/dev/null || true
  sleep 2
  rm -rf /data/signal-cli
  mkdir -p /data/signal-cli
  echo "[INFO] Restarting signal-cli-rest-api with clean data..."
  start_signal_api
fi

export PORT=3002
echo "[INFO] Starting Signal UI on port $PORT..."
cd /ui
exec node server.js
