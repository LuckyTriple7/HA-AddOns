#!/bin/sh
set -e

mkdir -p /data /share

DB=/data/filebrowser.db
PORT=$(jq -r '.port // 17771' /data/options.json 2>/dev/null || echo 17771)
USERNAME=$(jq -r '.username // "admin"' /data/options.json 2>/dev/null || echo "admin")
PASSWORD=$(jq -r '.password // "admin1234567"' /data/options.json 2>/dev/null || echo "admin1234567")

# Erster Start: FileBrowser kurz im Hintergrund starten damit die DB mit
# Standardbenutzer (admin/admin) angelegt wird, dann stoppen.
if [ ! -f "$DB" ]; then
    filebrowser --database "$DB" --address 127.0.0.1 --port 19999 --root /share &
    FB_PID=$!
    sleep 3
    kill "$FB_PID" 2>/dev/null
    wait "$FB_PID" 2>/dev/null || true
fi

# Konfigurierte Zugangsdaten setzen — update nutzt ID 1 (einziger Admin-User)
filebrowser users update 1 --username "$USERNAME" --password "$PASSWORD" --database "$DB" 2>/dev/null || true

exec filebrowser \
    --database "$DB" \
    --address 0.0.0.0 \
    --port "$PORT" \
    --root /share
