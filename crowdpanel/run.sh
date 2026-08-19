#!/bin/sh
set -e
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] CrowdPanel is starting on port 17797..."
exec python /app/app.py
