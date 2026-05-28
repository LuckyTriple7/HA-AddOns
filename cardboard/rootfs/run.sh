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
    echo "[INFO] Keine users.yaml gefunden — Demo-Konfiguration wird angelegt ..."
    cat > "$USERS_FILE" <<'YAML'
# CardBoard Benutzerkonfiguration
# Dokumentation: siehe DOCS.md
#
# Passwort als SHA-256-Hash (empfohlen für externen Zugriff):
#   Linux/macOS:  echo -n "MeinPasswort" | sha256sum
#   Windows PS:   [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes("MeinPasswort"))).Replace("-","").ToLower()
#
users:
  - username: demo
    password: changeme
    display_name: Demo User
    lang: de
    templates:
      - file: card1.j2
        title: Übersicht
      - file: card2.j2
        title: Klima
      - file: card3.j2
        title: Status
YAML
    echo "[INFO] users.yaml angelegt unter ${USERS_FILE}"
fi

DEMO_DIR=/config/addons_config/cardboard/demo
if [ ! -d "$DEMO_DIR" ]; then
    echo "[INFO] Demo-Templates werden angelegt ..."
    mkdir -p "$DEMO_DIR"
    cp /app/demo_templates/demo/card1.j2 "$DEMO_DIR/card1.j2"
    cp /app/demo_templates/demo/card2.j2 "$DEMO_DIR/card2.j2"
    cp /app/demo_templates/demo/card3.j2 "$DEMO_DIR/card3.j2"
    echo "[INFO] Demo-Templates angelegt unter ${DEMO_DIR}"
fi

echo "[INFO] Starte CardBoard — Web: ${PORT}  Admin-API: ${ADMIN_PORT} ..."
exec python /app/server.py
