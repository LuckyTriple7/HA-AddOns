#!/bin/sh
set -e

echo "=== LogPulse Optionen ==="
jq 'to_entries | map(if (.key == "password") and (.value != "") then .value = "***" else . end) | from_entries' \
    /data/options.json 2>/dev/null || echo "FEHLER: /data/options.json nicht gefunden"
echo "=========================="

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Starte LogPulse — Web-UI: 17795 ..."
exec python3 /app/app.py
