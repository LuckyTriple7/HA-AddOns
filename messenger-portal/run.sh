#!/bin/sh
set -e

echo "[INFO] [$(date +%H:%M:%S)] Generating nginx proxy config..."
python /app/gen_nginx.py

echo "[INFO] [$(date +%H:%M:%S)] Testing nginx config..."
nginx -t

echo "[INFO] [$(date +%H:%M:%S)] Starting nginx on port 17770..."
nginx

echo "[INFO] [$(date +%H:%M:%S)] Starting MessengerPortal Flask app on port 5000..."
exec python /app/app.py
