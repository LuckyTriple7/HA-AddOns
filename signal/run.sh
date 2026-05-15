#!/bin/bash
set -e

export PHONE_NUMBER=$(jq -r '.phone_number // ""' /data/options.json)
export WEBHOOK_INCOMING=$(jq -r '.webhook_incoming // ""' /data/options.json)
export SIGNAL_API_URL=http://localhost:8080

# Persist signal-cli data to /data (always mounted in HA)
mkdir -p /data/signal-cli
mkdir -p /root/.local/share
if [ ! -L /root/.local/share/signal-cli ]; then
  rm -rf /root/.local/share/signal-cli
  ln -sf /data/signal-cli /root/.local/share/signal-cli
fi

# Start signal-cli-rest-api BEFORE setting PORT
# (entrypoint.sh reads PORT and would bind to our UI port otherwise)
echo "[INFO] Starting signal-cli-rest-api..."
/entrypoint.sh &

# Wait for signal-cli-rest-api to respond on :8080 (up to 120 seconds)
echo "[INFO] Waiting for signal-cli-rest-api on :8080..."
for i in $(seq 1 60); do
  if curl -s --max-time 2 -o /dev/null http://localhost:8080/v1/about; then
    echo "[INFO] signal-cli-rest-api ready"
    break
  fi
  sleep 2
done

export PORT=3001
echo "[INFO] Starting Signal UI on port $PORT..."
cd /ui
exec node server.js
