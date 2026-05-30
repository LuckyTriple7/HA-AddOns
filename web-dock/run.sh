#!/bin/sh
set -e

echo "[INFO] Generating nginx proxy config..."
python /app/gen_nginx.py

echo "[INFO] Testing nginx config..."
nginx -t

echo "[INFO] Starting nginx on port 17780..."
nginx

echo "[INFO] Starting WebDock Flask app on port 5000..."
exec python /app/app.py
