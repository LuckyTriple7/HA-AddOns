#!/bin/sh
set -e

QDIR=/data/quantum
QCONFIG=$QDIR/config.yaml
QDB=$QDIR/filebox.sqlite
ROOT=/data/filebox-root

echo "=== options.json ==="
jq 'to_entries | map(if (.key | test("password")) then .value = "***" else . end) | from_entries' \
    /data/options.json 2>/dev/null || echo "FEHLER: /data/options.json nicht gefunden"
echo "===================="

PORT=$(jq -r '.port // 17771' /data/options.json 2>/dev/null || echo 17771)
USERNAME=$(jq -r '.username // "admin"' /data/options.json 2>/dev/null || echo "admin")
PASSWORD=$(jq -r '.password // "admin1234567"' /data/options.json 2>/dev/null || echo "admin1234567")
SHOW_MEDIA=$(jq -r '.show_media // false' /data/options.json 2>/dev/null || echo "false")
SHOW_CONFIG=$(jq -r '.show_config // false' /data/options.json 2>/dev/null || echo "false")
SHOW_BACKUP=$(jq -r '.show_backup // false' /data/options.json 2>/dev/null || echo "false")

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] PORT=$PORT SHOW_MEDIA=$SHOW_MEDIA SHOW_CONFIG=$SHOW_CONFIG SHOW_BACKUP=$SHOW_BACKUP"

mkdir -p "$ROOT"

# HA-Shares als Bind-Mounts — FileBrowser folgt Symlinks außerhalb von ROOT nicht
# Alte Symlinks aus früheren Versionen entfernen, dann als echtes Verzeichnis anlegen
mkdir -p /share/filebox
[ -L "$ROOT/FileBox" ] && rm -f "$ROOT/FileBox"
mkdir -p "$ROOT/FileBox"
umount "$ROOT/FileBox" 2>/dev/null || true
mount --bind /share/filebox "$ROOT/FileBox"

if [ "$SHOW_MEDIA" = "true" ]; then
    [ -L "$ROOT/Media" ] && rm -f "$ROOT/Media"
    mkdir -p "$ROOT/Media"
    umount "$ROOT/Media" 2>/dev/null || true
    mount --bind /media "$ROOT/Media"
else
    umount "$ROOT/Media" 2>/dev/null || true
    [ -L "$ROOT/Media" ] && rm -f "$ROOT/Media"
    rmdir "$ROOT/Media" 2>/dev/null || true
fi

if [ "$SHOW_CONFIG" = "true" ]; then
    [ -L "$ROOT/Config" ] && rm -f "$ROOT/Config"
    mkdir -p "$ROOT/Config"
    umount "$ROOT/Config" 2>/dev/null || true
    mount --bind /homeassistant "$ROOT/Config"
else
    umount "$ROOT/Config" 2>/dev/null || true
    [ -L "$ROOT/Config" ] && rm -f "$ROOT/Config"
    rmdir "$ROOT/Config" 2>/dev/null || true
fi

if [ "$SHOW_BACKUP" = "true" ]; then
    [ -L "$ROOT/Backup" ] && rm -f "$ROOT/Backup"
    mkdir -p "$ROOT/Backup"
    umount "$ROOT/Backup" 2>/dev/null || true
    mount --bind /backup "$ROOT/Backup"
else
    umount "$ROOT/Backup" 2>/dev/null || true
    [ -L "$ROOT/Backup" ] && rm -f "$ROOT/Backup"
    rmdir "$ROOT/Backup" 2>/dev/null || true
fi

# SMB-Share direkt in ROOT mounten (kein /mnt-Zwischenpfad + Symlink)
do_mount() {
    SERVER=$1
    SHARE=$2
    USER=$3
    PASS=$4
    LINKNAME=$5

    MOUNTPOINT="$ROOT/${LINKNAME}"
    [ -L "$MOUNTPOINT" ] && rm -f "$MOUNTPOINT"  # Symlink aus alter Version entfernen
    mkdir -p "$MOUNTPOINT"
    umount "$MOUNTPOINT" 2>/dev/null || true

    if ! nc -z -w 5 "$SERVER" 445 2>/dev/null; then
        echo "[FAIL] [$(date '+%Y-%m-%d %H:%M:%S')] Port 445 auf ${SERVER} nicht erreichbar — übersprungen"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
        return
    fi

    OPTS="vers=3.0,uid=0,gid=0,file_mode=0755,dir_mode=0755,noperm,sec=ntlmssp,nodfs"
    if [ -n "$USER" ]; then
        OPTS="${OPTS},username=${USER}"
    else
        OPTS="${OPTS},guest"
    fi
    if [ -n "$PASS" ]; then
        OPTS="${OPTS},password=${PASS}"
    fi

    UNC="//${SERVER}/${SHARE}"
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Mounte ${UNC} → ${MOUNTPOINT} ..."

    ERR_FILE="/tmp/mount_err_$$"
    if mount -t cifs "$UNC" "$MOUNTPOINT" -o "$OPTS" >"$ERR_FILE" 2>&1; then
        rm -f "$ERR_FILE"
        echo "[OK] [$(date '+%Y-%m-%d %H:%M:%S')] ${UNC} erfolgreich gemountet"
        echo "[OK] [$(date '+%Y-%m-%d %H:%M:%S')] In FileBrowser sichtbar als '${LINKNAME}'"
    else
        MOUNT_ERR=$(cat "$ERR_FILE" 2>/dev/null)
        rm -f "$ERR_FILE"
        echo "[FAIL] [$(date '+%Y-%m-%d %H:%M:%S')] Mount von ${UNC} fehlgeschlagen: ${MOUNT_ERR}"
        rmdir "$MOUNTPOINT" 2>/dev/null || true
    fi
}

mount_server() {
    INDEX=$1
    SERVER=$(jq -r ".smb_${INDEX}_server // empty" /data/options.json 2>/dev/null)
    SHARE=$(jq -r ".smb_${INDEX}_share // empty" /data/options.json 2>/dev/null)
    USER=$(jq -r ".smb_${INDEX}_user // empty" /data/options.json 2>/dev/null)
    PASS=$(jq -r ".smb_${INDEX}_password // empty" /data/options.json 2>/dev/null)

    if [ -z "$SERVER" ]; then
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] SMB-${INDEX}: nicht konfiguriert — übersprungen"
        return
    fi

    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] SMB-${INDEX}: Server ${SERVER}"

    # Alte Mounts für diesen Slot umounten und entfernen
    for d in "$ROOT"/SMB-${INDEX}*; do
        [ -e "$d" ] || continue
        umount "$d" 2>/dev/null || true
        rmdir "$d" 2>/dev/null || true
    done

    if [ -n "$SHARE" ]; then
        do_mount "$SERVER" "$SHARE" "$USER" "$PASS" \
            "SMB-${INDEX} ${SHARE}"
    else
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] SMB-${INDEX}: Ermittle alle Shares auf ${SERVER} ..."
        if [ -n "$USER" ]; then
            SMB_LIST_CMD="smbclient -L $SERVER -U ${USER}%${PASS} -g"
        else
            SMB_LIST_CMD="smbclient -L $SERVER -N -g"
        fi
        SMB_LIST_OUT=$(eval "$SMB_LIST_CMD" 2>&1)
        echo "[DEBUG] [$(date '+%Y-%m-%d %H:%M:%S')] SMB-${INDEX}: smbclient Ausgabe: ${SMB_LIST_OUT}"
        SHARES=$(echo "$SMB_LIST_OUT" | awk -F'|' '/^Disk\|/ {print $2}')

        if [ -z "$SHARES" ]; then
            echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] SMB-${INDEX}: Keine Shares auf ${SERVER} gefunden"
            return
        fi

        echo "$SHARES" | while IFS= read -r S; do
            S=$(echo "$S" | tr -d '\r')
            [ -z "$S" ] && continue
            do_mount "$SERVER" "$S" "$USER" "$PASS" \
                "SMB-${INDEX} ${S}"
        done
        echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] SMB-${INDEX}: Auto-Discovery abgeschlossen"
    fi
}

echo "--- SMB-Mounts ---"
mount_server 1
mount_server 2
mount_server 3
mount_server 4
mount_server 5
echo "------------------"
# FileBrowser Quantum: Konfiguration bei jedem Start neu schreiben.
# Das Admin-Passwort kommt per Umgebungsvariable, nicht in die Datei.
# Quantum übernimmt es bei jedem Start, außer es lautet "admin" oder ist leer.
mkdir -p "$QDIR"
cat > "$QCONFIG" <<CFG
server:
  disableUpdateCheck: true
  cacheDir: "/tmp/filebox-cache"
  database:
    path: "${QDB}"
  sources:
    - path: "${ROOT}"
      name: "FileBox"
      config:
        defaultEnabled: true
auth:
  adminUsername: $(jq -n --arg v "$USERNAME" '$v')
  methods:
    password:
      enabled: true
frontend:
  name: "FileBox"
userDefaults:
  ui:
    locale: "de"
  account:
    disableUpdateNotifications: true
http:
  port: ${PORT}
  listen: "0.0.0.0"
  baseURL: "/"
CFG

if [ "$PASSWORD" = "admin" ]; then
    echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] Passwort 'admin' wird von FileBrowser Quantum nicht übernommen — bitte ein anderes Passwort setzen"
fi

export FILEBROWSER_ADMIN_PASSWORD="$PASSWORD"
export FILEBROWSER_DISABLE_AUTOMATIC_BACKUP=true

cd "$QDIR"

# Admin-Konto anlegen oder aktualisieren (greift auch nach Umbenennung in den Optionen).
# Passwort über stdin, damit es nicht in der Prozessliste steht.
if printf '%s' "$PASSWORD" | filebrowser -c "$QCONFIG" user set "$USERNAME" --password --admin >/tmp/userset.log 2>&1; then
    echo "[OK] [$(date '+%Y-%m-%d %H:%M:%S')] Admin-Konto '${USERNAME}' übernommen"
else
    echo "[FAIL] [$(date '+%Y-%m-%d %H:%M:%S')] Admin-Konto konnte nicht gesetzt werden:"
    cat /tmp/userset.log
fi
rm -f /tmp/userset.log

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Starte FileBrowser Quantum auf Port ${PORT} ..."
exec filebrowser -c "$QCONFIG"
