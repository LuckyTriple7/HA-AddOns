#!/usr/bin/with-contenv bash
# systemd-logind ist in HA-Containern nicht lauffähig. Wenn dbus versucht es zu starten,
# schlägt die Aktivierung fehl → xfce4-session stürzt ab → s6 startet neu → Dauerschleife.
# Lösung: Die dbus-Aktivierungsdatei entfernen, damit dbus logind gar nicht erst startet.

LOGIND_ACTIVATION="/usr/share/dbus-1/system-services/org.freedesktop.login1.service"
if [ -f "${LOGIND_ACTIVATION}" ]; then
    rm -f "${LOGIND_ACTIVATION}"
    echo "[ubuntu-webtop] logind dbus-Aktivierung deaktiviert (nicht benötigt in HA)"
fi

# Polkit-Aktionen die logind benötigen ebenfalls deaktivieren
POLKIT_LOGIND="/usr/share/polkit-1/actions/org.freedesktop.login1.policy"
if [ -f "${POLKIT_LOGIND}" ]; then
    rm -f "${POLKIT_LOGIND}"
fi
