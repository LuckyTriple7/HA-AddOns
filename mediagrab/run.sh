#!/bin/sh
set -e
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] MediaGrab startet auf Port 17791..."
exec python /app/app.py
