#!/bin/sh
set -e
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] HA SysWatch startet auf Port 17790..."
exec python /app/app.py
