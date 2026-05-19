#!/bin/sh
VSCODE_CFG=/config/.config/Code/User
mkdir -p "${VSCODE_CFG}"
chown -R abc:abc /config/.config/Code 2>/dev/null || true

if [ ! -f "${VSCODE_CFG}/settings.json" ]; then
    cat > "${VSCODE_CFG}/settings.json" << 'EOF'
{
    "update.mode": "none",
    "telemetry.telemetryLevel": "off"
}
EOF
    chown abc:abc "${VSCODE_CFG}/settings.json"
    echo "[vscode] Standard-Einstellungen erstellt: ${VSCODE_CFG}/settings.json"
else
    echo "[vscode] Einstellungen bereits vorhanden: ${VSCODE_CFG}/settings.json"
fi
