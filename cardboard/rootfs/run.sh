#!/bin/sh
set -e

echo "=== CardBoard Optionen ==="
jq 'to_entries | map(if .key == "ha_token" then .value = "***" else . end) | from_entries' \
    /data/options.json 2>/dev/null || echo "FEHLER: /data/options.json nicht gefunden"
echo "=========================="

PORT=$(jq -r '.port // 17772' /data/options.json 2>/dev/null || echo 17772)
ADMIN_PORT=$(jq -r '.admin_port // 17773' /data/options.json 2>/dev/null || echo 17773)

mkdir -p /config/addons_config/cardboard

USERS_FILE=/config/addons_config/cardboard/users.yaml
if [ ! -f "$USERS_FILE" ]; then
    echo "[INFO] Keine users.yaml gefunden — Beispieldatei wird angelegt ..."
    cat > "$USERS_FILE" <<'YAML'
# CardBoard Benutzerkonfiguration
# Dokumentation: siehe DOCS.md
#
# Passwort als SHA-256-Hash (empfohlen für externen Zugriff):
#   Linux/macOS:  echo -n "MeinPasswort" | sha256sum
#   Windows PS:   [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes("MeinPasswort"))).Replace("-","").ToLower()
#
users:
  - username: admin
    password: changeme
    display_name: Administrator
    lang: de
    templates:
      - file: overview.j2
        title: Übersicht
YAML
    echo "[INFO] Beispiel-users.yaml angelegt unter ${USERS_FILE}"
fi

echo "[INFO] Starte CardBoard — Web: ${PORT}  Admin-API: ${ADMIN_PORT} ..."
exec python /app/server.py
