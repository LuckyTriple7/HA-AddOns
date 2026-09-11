#!/bin/sh
set -e
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] ReactorSim is starting on port 17779..."
exec python /app/app.py
