#!/bin/sh
set -e

export API_ID=$(jq -r '.api_id // 0' /data/options.json)
export API_HASH=$(jq -r '.api_hash // ""' /data/options.json)
export PHONE_NUMBER=$(jq -r '.phone_number // ""' /data/options.json)
export WEBHOOK_INCOMING=$(jq -r '.webhook_incoming // ""' /data/options.json)
export DARK_MODE=$(jq -r 'if .dark_mode == false then "false" else "true" end' /data/options.json)
export DOWNLOAD_MEDIA=$(jq -r 'if .download_media == true then "true" else "false" end' /data/options.json)
export MEDIA_MAX_MB=$(jq -r '.media_max_mb // 500' /data/options.json)
export FETCH_LIMIT=$(jq -r '.fetch_messages_limit // 50' /data/options.json)
export DEBUG_MODE=$(jq -r 'if .debug_mode == true then "true" else "false" end' /data/options.json)
export HA_NOTIFICATIONS=$(jq -r 'if .ha_notifications == true then "true" else "false" end' /data/options.json)
export HA_NOTIFICATIONS_PRIVACY=$(jq -r 'if .ha_notifications_privacy == true then "true" else "false" end' /data/options.json)
export HA_NOTIFY_SKIP_BOTS=$(jq -r 'if .ha_notifications_skip_bots == true then "true" else "false" end' /data/options.json)
export HA_TOKEN=$(jq -r '.ha_token // ""' /data/options.json)
export PORT=17778

mkdir -p /config

if [ -f /data/session.txt ] && [ ! -f /config/session.txt ]; then
  cp /data/session.txt /config/session.txt 2>/dev/null || true
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

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Starting Telegram add-on (API_ID: $API_ID)..."
cd /ui
exec node server.js
