#!/usr/bin/with-contenv bash
# Setzt Firefox als Standard-Browser und deutsche Locale für den XFCE-Desktop.

CONFIG_DIR="/config/.config"
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
mkdir -p "${CONFIG_DIR}/xfce4"
chown -R "${PUID}:${PGID}" "${CONFIG_DIR}" 2>/dev/null || true

# Firefox als Standard-Browser (XFCE preferred-applications)
HELPERS_RC="${CONFIG_DIR}/xfce4/helpers.rc"
if [ ! -f "${HELPERS_RC}" ]; then
    cat > "${HELPERS_RC}" << 'EOF'
WebBrowser=firefox
MailReader=
FileManager=Thunar
TerminalEmulator=xfce4-terminal
EOF
    echo "[ubuntu-webtop] Firefox als Standard-Browser gesetzt"
fi

# MIME-Zuordnung für HTTP/HTTPS → Firefox
MIMEAPPS="${CONFIG_DIR}/mimeapps.list"
if [ ! -f "${MIMEAPPS}" ]; then
    cat > "${MIMEAPPS}" << 'EOF'
[Default Applications]
x-scheme-handler/http=firefox.desktop
x-scheme-handler/https=firefox.desktop
text/html=firefox.desktop
application/xhtml+xml=firefox.desktop
EOF
    echo "[ubuntu-webtop] MIME-Zuordnung für Firefox gesetzt"
fi

# Locale für XFCE-Sitzung setzen
LOCALE_CONF="${CONFIG_DIR}/locale.conf"
if [ ! -f "${LOCALE_CONF}" ]; then
    echo "LANG=de_DE.UTF-8" > "${LOCALE_CONF}"
fi

# Chromium-Panel-Launcher durch Firefox ersetzen (immer, nicht nur beim Erststart)
# Die Panel-Konfig bleibt persistent in /config/.config/xfce4/panel/
PANEL_DIR="${CONFIG_DIR}/xfce4/panel"
if [ -d "${PANEL_DIR}" ]; then
    while IFS= read -r -d '' desktop_file; do
        if grep -qi "chromium" "${desktop_file}"; then
            cat > "${desktop_file}" << 'DESKTOP'
[Desktop Entry]
Version=1.0
Type=Application
Name=Firefox
Comment=Webbrowser
TryExec=firefox
Exec=firefox %u
Icon=firefox
Categories=Network;WebBrowser;
DESKTOP
            echo "[ubuntu-webtop] Panel-Launcher: Chromium → Firefox ersetzt in ${desktop_file}"
        fi
    done < <(find "${PANEL_DIR}" -name "*.desktop" -print0 2>/dev/null)
fi
