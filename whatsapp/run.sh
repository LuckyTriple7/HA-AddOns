#!/bin/bash
set -e

export WEBHOOK_URL=$(jq -r '.webhook_url // ""' /data/options.json)
export WEBHOOK_INCOMING=$(jq -r '.webhook_incoming // ""' /data/options.json)
export INITIAL_CHATS=$(jq -r '.initial_chats // 30' /data/options.json)
export INITIAL_MESSAGES=$(jq -r '.initial_messages // 20' /data/options.json)
export SESSION_DIR=/addon_config/session
export PORT=3000

mkdir -p "$SESSION_DIR"

echo "[INFO] Starting WhatsApp add-on..."
cd /app
exec node server.js
