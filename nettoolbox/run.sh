#!/bin/sh
set -e
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] NetToolbox is starting on port 17798..."
exec python /app/app.py
