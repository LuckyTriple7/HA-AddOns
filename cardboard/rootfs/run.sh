#!/bin/sh
set -e

echo "=== CardBoard Optionen ==="
jq 'to_entries | map(if .key == "ha_token" then .value = "***" else . end) | from_entries' \
    /data/options.json 2>/dev/null || echo "FEHLER: /data/options.json nicht gefunden"
echo "=========================="

PORT=$(jq -r '.port // 17772' /data/options.json 2>/dev/null || echo 17772)
ADMIN_PORT=$(jq -r '.admin_port // 17773' /data/options.json 2>/dev/null || echo 17773)

mkdir -p /config/addons_config/cardboard

echo "[INFO] Starte CardBoard — Web: ${PORT}  Admin-API: ${ADMIN_PORT} ..."
exec python /app/server.py
