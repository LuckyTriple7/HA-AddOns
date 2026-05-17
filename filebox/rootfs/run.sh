#!/bin/sh
set -e

mkdir -p /data /share

PORT=$(jq -r '.port // 17771' /data/options.json 2>/dev/null || echo 17771)

filebrowser config init --database /data/filebrowser.db 2>/dev/null || true

filebrowser config set \
    --database /data/filebrowser.db \
    --address 0.0.0.0 \
    --port "$PORT" \
    --root /share \
    --auth.method noauth

exec filebrowser --database /data/filebrowser.db
