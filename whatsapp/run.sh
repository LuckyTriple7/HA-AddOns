#!/bin/sh
set -e

export WEBHOOK_URL=$(jq -r '.webhook_url // ""' /data/options.json)
export WEBHOOK_INCOMING=$(jq -r '.webhook_incoming // ""' /data/options.json)
export INITIAL_CHATS=$(jq -r '.initial_chats // 30' /data/options.json)
export INITIAL_MESSAGES=$(jq -r '.initial_messages // 20' /data/options.json)
export KEEP_DELETED=$(jq -r 'if .keep_deleted == true then "true" else "false" end' /data/options.json)
export DARK_MODE=$(jq -r 'if .dark_mode == false then "false" else "true" end' /data/options.json)
export DOWNLOAD_MEDIA=$(jq -r 'if .download_media == true then "true" else "false" end' /data/options.json)
export MEDIA_MAX_MB=$(jq -r '.media_max_mb // 500' /data/options.json)
export VIDEO_MAX_MB=$(jq -r '.video_max_mb // 50' /data/options.json)
export DEBUG_MODE=$(jq -r 'if .debug_mode == true then "true" else "false" end' /data/options.json)
export HA_NOTIFICATIONS=$(jq -r 'if .ha_notifications == true then "true" else "false" end' /data/options.json)
export HA_NOTIFICATIONS_PRIVACY=$(jq -r 'if .ha_notifications_privacy == true then "true" else "false" end' /data/options.json)
export HA_TOKEN=$(jq -r '.ha_token // ""' /data/options.json)
export SESSION_DIR=/config/session
export PORT=17776

mkdir -p "$SESSION_DIR"

# Migration: /data/session → /config/session (einmalig)
if [ -d /data/session ] && [ ! -f /config/session/.migrated ]; then
    cp -a /data/session/. /config/session/ 2>/dev/null || true
    touch /config/session/.migrated
fi

# Remove Chromium lock files left over from unclean shutdown (process.exit kills
# Node before Chromium can clean up, leaving SingletonLock which blocks next start)
rm -f "$SESSION_DIR/chromium/SingletonLock"
rm -f "$SESSION_DIR/chromium/SingletonCookie"
rm -f "$SESSION_DIR/chromium/SingletonSocket"

# Chromium cache bereinigen (wächst unbegrenzt, enthält keine Session-Daten)
rm -rf "$SESSION_DIR/chromium/Default/Cache"
rm -rf "$SESSION_DIR/chromium/Default/Cache2"
rm -rf "$SESSION_DIR/chromium/Default/Code Cache"
rm -rf "$SESSION_DIR/chromium/Default/GPUCache"

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Starting WhatsApp add-on..."
cd /app
exec node server.js
