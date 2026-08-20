#!/bin/sh
set -e

echo "=== CardBoard Optionen ==="
jq 'to_entries | map(if (.key == "admin_password") and (.value != "") then .value = "***" else . end) | from_entries' \
    /data/options.json 2>/dev/null || echo "FEHLER: /data/options.json nicht gefunden"
echo "=========================="

PORT=17772
ADMIN_PORT=17773

# SUPERVISOR_TOKEN wird vom Supervisor automatisch injiziert (homeassistant_api: true) —
# kein manuell eingetragener Token mehr nötig.
echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Prüfe Home-Assistant-API ..."
if [ -n "$SUPERVISOR_TOKEN" ]; then
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time 5 \
        -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        "http://supervisor/core/api/" 2>/dev/null || echo "000")
    if [ "$HTTP_STATUS" = "200" ]; then
        echo "[OK] [$(date '+%Y-%m-%d %H:%M:%S')] Home-Assistant-API erreichbar (Supervisor-Token)"
    else
        echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] Home-Assistant-API antwortet mit HTTP ${HTTP_STATUS}"
    fi
else
    echo "[WARN] [$(date '+%Y-%m-%d %H:%M:%S')] SUPERVISOR_TOKEN nicht verfügbar — läuft 'homeassistant_api: true' und das Add-on im Supervisor?"
fi

mkdir -p /homeassistant/addons_config/cardboard

USERS_FILE=/homeassistant/addons_config/cardboard/users.yaml
if [ ! -f "$USERS_FILE" ]; then
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Keine users.yaml gefunden — Demo-Konfiguration wird angelegt ..."
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
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] users.yaml angelegt unter ${USERS_FILE}"
fi

DEMO_DIR=/homeassistant/addons_config/cardboard/demo
if [ ! -d "$DEMO_DIR" ]; then
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Demo-Templates werden angelegt ..."
    mkdir -p "$DEMO_DIR"
    cp /app/demo_templates/demo/card1.j2 "$DEMO_DIR/card1.j2"
    cp /app/demo_templates/demo/card2.j2 "$DEMO_DIR/card2.j2"
    cp /app/demo_templates/demo/card3.j2 "$DEMO_DIR/card3.j2"
    echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Demo-Templates angelegt unter ${DEMO_DIR}"
fi

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] Starte CardBoard — Web: ${PORT}  Admin-API: ${ADMIN_PORT} ..."
exec python /app/server.py
