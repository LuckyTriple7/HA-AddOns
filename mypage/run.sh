#!/bin/sh
set -e
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] MyPage startet — öffentliche Seite auf Port 17760, Admin auf 17761..."

# Optionaler SMB-Speicher für Mitglieder-Dateien: run.sh setzt nur den Pfad,
# der Mount selbst passiert in app.py (Zugangsdaten landen so nie auf der Platte).
# Bewusst KEIN Fallback auf lokalen Speicher — ist der Server weg, geht der
# Dateibereich offline und der Watchdog verbindet automatisch neu.
# Die Einstellungen kommen aus settings.json (Oberfläche); options.json dient nur
# noch als Fallback, solange die Migration beim ersten Start noch nicht lief.
# Wichtig: `set -e` ist aktiv. jq beendet sich auf einer fehlenden oder kaputten
# Datei mit Code 2 — ohne die Prüfung auf Existenz und das `|| true` würde das
# ganze Skript daran sterben, bevor MyPage überhaupt startet.
read_opt() {   # $1 = Datei, $2 = Schlüssel
    [ -f "$1" ] || return 0
    jq -r --arg k "$2" '.[$k] // empty' "$1" 2>/dev/null || true
}

SETTINGS="${MYPAGE_DATA:-/config}/settings.json"
SMB_SERVER=$(read_opt "$SETTINGS" smb_server)
SMB_SHARE=$(read_opt "$SETTINGS" smb_share)
if [ -z "$SMB_SERVER" ] || [ -z "$SMB_SHARE" ]; then
    SMB_SERVER=$(read_opt /data/options.json smb_server)
    SMB_SHARE=$(read_opt /data/options.json smb_share)
fi

if [ -n "$SMB_SERVER" ] && [ -n "$SMB_SHARE" ]; then
    export MYPAGE_USERFILES="/mnt/userfiles"
    mkdir -p "$MYPAGE_USERFILES"
fi

exec python /app/app.py
