#!/bin/bash
set -e

export API_ID=$(jq -r '.api_id // 0' /data/options.json)
export API_HASH=$(jq -r '.api_hash // ""' /data/options.json)
export PHONE_NUMBER=$(jq -r '.phone_number // ""' /data/options.json)
export WEBHOOK_INCOMING=$(jq -r '.webhook_incoming // ""' /data/options.json)
export DARK_MODE=$(jq -r 'if .dark_mode == false then "false" else "true" end' /data/options.json)
export PORT=17778

mkdir -p /data

echo "[INFO] Starting Telegram add-on (API_ID: $API_ID)..."
cd /ui
exec node server.js
