#!/bin/sh
set -e
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] MyPage startet — öffentliche Seite auf Port 17760, Admin auf 17761..."
exec python /app/app.py
