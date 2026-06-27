#!/bin/sh
set -e
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] TUIWatch startet auf Port 17794..."
exec python3 /app/app.py
