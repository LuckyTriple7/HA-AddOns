#!/bin/sh
set -e

mkdir -p /data /share

filebrowser config init --database /data/filebrowser.db 2>/dev/null || true

filebrowser config set \
    --database /data/filebrowser.db \
    --address 0.0.0.0 \
    --port 8080 \
    --root /share \
    --noauth

exec filebrowser --database /data/filebrowser.db
