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

# GPU-Beschleunigung abschalten: ohne echte GPU flutet der GPU-Prozess sonst das
# Log mit "eglGetMscRateANGLE: glXGetMscRateOML failed". argv.json greift auch,
# wenn VS Code ohne den --disable-gpu-Wrapper gestartet wird (Panel, Sitzung).
VSCODE_ARGV=/config/.vscode/argv.json
mkdir -p /config/.vscode
if [ ! -f "${VSCODE_ARGV}" ]; then
    printf '{\n\t"disable-hardware-acceleration": true\n}\n' > "${VSCODE_ARGV}"
    echo "[vscode] argv.json mit disable-hardware-acceleration erstellt"
elif ! grep -Eq '^[[:space:]]*"disable-hardware-acceleration"[[:space:]]*:[[:space:]]*true' "${VSCODE_ARGV}"; then
    sed -i -E '/^[[:space:]]*"disable-hardware-acceleration"/d' "${VSCODE_ARGV}"
    sed -i '0,/^[[:space:]]*{/s//{\n\t"disable-hardware-acceleration": true,/' "${VSCODE_ARGV}"
    echo "[vscode] disable-hardware-acceleration in argv.json aktiviert"
fi
chown -R abc:abc /config/.vscode 2>/dev/null || true
