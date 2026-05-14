#!/bin/bash
# Startet XFCE-Komponenten direkt, ohne xfce4-session.
# xfce4-session bricht in HA-Containern wegen fehlender systemd-Dienste ab.

export DISPLAY="${DISPLAY:-:1}"

# D-Bus Session-Bus starten.
# Normalerweise startet xfce4-session den Session-Bus – da wir xfce4-session
# umgehen, müssen wir ihn selbst starten. Neuere xfdesktop-Versionen brauchen
# ihn zwingend, sonst crashen sie sofort (invalid NULL pointer instance).
if command -v dbus-launch >/dev/null 2>&1; then
    eval "$(dbus-launch --sh-syntax 2>/dev/null)" || true
    export DBUS_SESSION_BUS_ADDRESS
fi

# Fenstermanager ohne Compositor (verhindert schwarzen Bildschirm in virtuellen Umgebungen)
xfwm4 --compositor=off &

# Kurz warten bis WM registriert ist
sleep 2

# Desktop-Hintergrund und Icons
xfdesktop &

# Panel (taskbar)
xfce4-panel &

# Thunar-Daemon für Datei-Assoziation und Desktop-Integration
thunar --daemon &

# Vordergrundprozess – hält den s6-Service am Leben
exec sleep infinity
