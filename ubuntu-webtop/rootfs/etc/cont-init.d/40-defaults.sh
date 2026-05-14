#!/usr/bin/with-contenv bash
# Setzt Firefox als Standard-Browser und deutsche Locale für den XFCE-Desktop.
# Wird nur gesetzt wenn noch keine Benutzer-Konfiguration existiert (Erststart).

CONFIG_DIR="/config/.config"
mkdir -p "${CONFIG_DIR}/xfce4" "${CONFIG_DIR}"

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

# Locale für XFCE-Sitzung setzen (ergänzt die Umgebungsvariablen aus ha_entrypoint.sh)
LOCALE_CONF="${CONFIG_DIR}/locale.conf"
if [ ! -f "${LOCALE_CONF}" ]; then
    echo "LANG=de_DE.UTF-8" > "${LOCALE_CONF}"
fi
