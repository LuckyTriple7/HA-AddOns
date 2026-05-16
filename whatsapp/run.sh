#!/bin/bash
set -e

export WEBHOOK_URL=$(jq -r '.webhook_url // ""' /data/options.json)
export WEBHOOK_INCOMING=$(jq -r '.webhook_incoming // ""' /data/options.json)
export INITIAL_CHATS=$(jq -r '.initial_chats // 30' /data/options.json)
export INITIAL_MESSAGES=$(jq -r '.initial_messages // 20' /data/options.json)
export DARK_MODE=$(jq -r 'if .dark_mode == false then "false" else "true" end' /data/options.json)
export SESSION_DIR=/data/session
export PORT=3000

mkdir -p "$SESSION_DIR"

# Remove Chromium lock files left over from unclean shutdown (process.exit kills
# Node before Chromium can clean up, leaving SingletonLock which blocks next start)
rm -f "$SESSION_DIR/chromium/SingletonLock"
rm -f "$SESSION_DIR/chromium/SingletonCookie"
rm -f "$SESSION_DIR/chromium/SingletonSocket"

echo "[INFO] Starting WhatsApp add-on..."
cd /app
exec node server.js
