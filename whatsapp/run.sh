#!/bin/bash
set -e

export WEBHOOK_URL=$(jq -r '.webhook_url // ""' /data/options.json)
export WEBHOOK_INCOMING=$(jq -r '.webhook_incoming // ""' /data/options.json)
export SESSION_DIR=/addon_config/session

mkdir -p "$SESSION_DIR"

echo "[INFO] Starting WhatsApp add-on..."
cd /app
exec node server.js
