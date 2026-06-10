#!/bin/sh
set -e
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] MyPage startet — öffentliche Seite auf Port 17760, Admin auf 17761..."

# Optionaler SMB-Mount für Mitglieder-Dateien (entlastet die SD-Karte).
# Bewusst KEIN Fallback auf lokalen Speicher: Ist der Server weg, geht der
# Dateibereich offline und der Watchdog in der App verbindet automatisch neu.
SMB_SERVER=$(jq -r '.smb_server // empty' /data/options.json 2>/dev/null)
SMB_SHARE=$(jq -r '.smb_share // empty' /data/options.json 2>/dev/null)
SMB_USER=$(jq -r '.smb_user // empty' /data/options.json 2>/dev/null)
SMB_PASS=$(jq -r '.smb_password // empty' /data/options.json 2>/dev/null)

if [ -n "$SMB_SERVER" ] && [ -n "$SMB_SHARE" ]; then
    MOUNTPOINT="/mnt/userfiles"
    mkdir -p "$MOUNTPOINT"
    umount "$MOUNTPOINT" 2>/dev/null || true
    export MYPAGE_USERFILES="$MOUNTPOINT"

    OPTS="vers=3.0,uid=0,gid=0,file_mode=0755,dir_mode=0755,noperm,sec=ntlmssp,nodfs,iocharset=utf8,soft,actimeo=5"
    if [ -n "$SMB_USER" ]; then
        # Zugangsdaten über Credentials-Datei (Sonderzeichen-sicher, nicht in ps sichtbar)
        CRED_FILE="/tmp/.smbcred"
        printf 'username=%s\npassword=%s\n' "$SMB_USER" "$SMB_PASS" > "$CRED_FILE"
        chmod 600 "$CRED_FILE"
        OPTS="${OPTS},credentials=${CRED_FILE}"
    else
        OPTS="${OPTS},guest"
    fi

    if nc -z -w 5 "$SMB_SERVER" 445 2>/dev/null \
       && mount -t cifs "//${SMB_SERVER}/${SMB_SHARE}" "$MOUNTPOINT" -o "$OPTS" 2>/tmp/mount_err; then
        echo "[OK] [$(date '+%Y-%m-%d %H:%M:%S')] SMB-Share //${SMB_SERVER}/${SMB_SHARE} gemountet — Mitglieder-Dateien liegen dort"
    else
        echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] SMB-Mount fehlgeschlagen: $(cat /tmp/mount_err 2>/dev/null) — Dateibereich offline, Watchdog versucht es jede Minute erneut"
    fi
    rm -f /tmp/.smbcred /tmp/mount_err
fi

exec python /app/app.py
