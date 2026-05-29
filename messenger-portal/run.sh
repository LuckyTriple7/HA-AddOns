#!/bin/sh
set -e

echo "[INFO] Generating nginx proxy config..."
python /app/gen_nginx.py

echo "[INFO] Testing nginx config..."
nginx -t

echo "[INFO] Starting nginx on port 17770..."
nginx

echo "[INFO] Starting MessengerPortal Flask app on port 5000..."
exec python /app/app.py
