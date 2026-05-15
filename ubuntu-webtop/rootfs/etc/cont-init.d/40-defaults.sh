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

# MIME-Zuordnung: nur beim Erststart anlegen, danach nicht mehr überschreiben.
# Enthält alle wichtigen Defaults (Firefox, Geany für Code/Text).
# Benutzerdefinierte Änderungen bleiben so über Neustarts erhalten.
MIMEAPPS="${CONFIG_DIR}/mimeapps.list"
if [ ! -f "${MIMEAPPS}" ]; then
    cat > "${MIMEAPPS}" << 'EOF'
[Default Applications]
x-scheme-handler/http=firefox.desktop
x-scheme-handler/https=firefox.desktop
text/html=firefox.desktop
application/xhtml+xml=firefox.desktop
text/x-yaml=geany.desktop
application/x-yaml=geany.desktop
application/yaml=geany.desktop
text/x-shellscript=geany.desktop
text/x-python=geany.desktop
text/x-csrc=geany.desktop
text/x-chdr=geany.desktop
text/plain=geany.desktop
EOF
    echo "[ubuntu-webtop] MIME-Zuordnungen initialisiert (Erststart)"
fi

# Geany: Benutzer-Override damit Dateien aus SMB-Shares über geany-gio geöffnet werden.
# geany-gio kopiert die Datei lokal (gio copy, kein FUSE nötig) und synct beim Speichern zurück.
# Überschreibt das System-geany.desktop (%F, nur lokale Pfade) mit %U (URIs).
LOCAL_APPS="/config/.local/share/applications"
mkdir -p "$LOCAL_APPS"
if [ -f /usr/share/applications/geany.desktop ]; then
    sed 's|^Exec=geany.*|Exec=geany-gio %U|' /usr/share/applications/geany.desktop \
        > "$LOCAL_APPS/geany.desktop"
    chown "${PUID}:${PGID}" "$LOCAL_APPS/geany.desktop"
    echo "[ubuntu-webtop] geany.desktop Override gesetzt (geany-gio)"
fi
chown -R "${PUID}:${PGID}" /config/.local 2>/dev/null || true

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
