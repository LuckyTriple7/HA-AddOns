#!/bin/sh
set -e

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Generating nginx proxy config..."
python /app/gen_nginx.py

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Testing nginx config..."
nginx -t

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Starting nginx (Ingress 8099, LAN 17770)..."
nginx

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Starting MessengerPortal Flask app on port 5000..."
exec python /app/app.py
