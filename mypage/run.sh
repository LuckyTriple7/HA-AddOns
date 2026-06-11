#!/bin/sh
set -e
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] MyPage startet — öffentliche Seite auf Port 17760, Admin auf 17761..."

# Optionaler SMB-Speicher für Mitglieder-Dateien: run.sh setzt nur den Pfad,
# der Mount selbst passiert in app.py (Zugangsdaten landen so nie auf der Platte).
# Bewusst KEIN Fallback auf lokalen Speicher — ist der Server weg, geht der
# Dateibereich offline und der Watchdog verbindet automatisch neu.
SMB_SERVER=$(jq -r '.smb_server // empty' /data/options.json 2>/dev/null)
SMB_SHARE=$(jq -r '.smb_share // empty' /data/options.json 2>/dev/null)

if [ -n "$SMB_SERVER" ] && [ -n "$SMB_SHARE" ]; then
    export MYPAGE_USERFILES="/mnt/userfiles"
    mkdir -p "$MYPAGE_USERFILES"
fi

exec python /app/app.py
