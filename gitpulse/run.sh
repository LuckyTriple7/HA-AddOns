#!/bin/sh
set -e
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] GitPulse startet auf Port 17792..."
exec python /app/app.py
