#!/bin/sh
set -e

DB=/data/filebrowser.db
ROOT=/data/filebox-root

PORT=$(jq -r '.port // 17771' /data/options.json 2>/dev/null || echo 17771)
USERNAME=$(jq -r '.username // "admin"' /data/options.json 2>/dev/null || echo "admin")
PASSWORD=$(jq -r '.password // "admin1234567"' /data/options.json 2>/dev/null || echo "admin1234567")
SHOW_MEDIA=$(jq -r '.show_media // false' /data/options.json 2>/dev/null || echo "false")
SHOW_CONFIG=$(jq -r '.show_config // false' /data/options.json 2>/dev/null || echo "false")
SHOW_BACKUP=$(jq -r '.show_backup // false' /data/options.json 2>/dev/null || echo "false")

# Standard-Ordner anlegen
echo "Erstelle /share/filebox ..."
mkdir -p /share/filebox && echo "OK: /share/filebox erstellt" || echo "FEHLER: /share/filebox konnte nicht erstellt werden"
mkdir -p "$ROOT" && echo "OK: $ROOT erstellt" || echo "FEHLER: $ROOT konnte nicht erstellt werden"
ls -la /share/ || echo "FEHLER: ls /share fehlgeschlagen"

# Symlinks im FileBrowser-Root setzen
ln -sfn /share/filebox "$ROOT/FileBox" && echo "OK: Symlink FileBox -> /share/filebox" || echo "FEHLER: Symlink FileBox"

if [ "$SHOW_MEDIA" = "true" ]; then
    ln -sfn /media "$ROOT/Media" && echo "OK: Symlink Media" || echo "FEHLER: Symlink Media"
else
    rm -f "$ROOT/Media"
fi

if [ "$SHOW_CONFIG" = "true" ]; then
    ln -sfn /config "$ROOT/Config" && echo "OK: Symlink Config" || echo "FEHLER: Symlink Config"
else
    rm -f "$ROOT/Config"
fi

if [ "$SHOW_BACKUP" = "true" ]; then
    ln -sfn /backup "$ROOT/Backup" && echo "OK: Symlink Backup" || echo "FEHLER: Symlink Backup"
else
    rm -f "$ROOT/Backup"
fi

# Erster Start: FileBrowser kurz im Hintergrund starten damit die DB angelegt wird
if [ ! -f "$DB" ]; then
    filebrowser --database "$DB" --address 127.0.0.1 --port 19999 --root "$ROOT" &
    FB_PID=$!
    sleep 3
    kill "$FB_PID" 2>/dev/null
    wait "$FB_PID" 2>/dev/null || true
fi

# Sprache, Zugangsdaten und Root aktualisieren
filebrowser config set --defaults.locale de --database "$DB" 2>/dev/null || true
filebrowser users update 1 \
    --username "$USERNAME" \
    --password "$PASSWORD" \
    --locale de \
    --database "$DB" 2>/dev/null || true

exec filebrowser \
    --database "$DB" \
    --address 0.0.0.0 \
    --port "$PORT" \
    --root "$ROOT"
