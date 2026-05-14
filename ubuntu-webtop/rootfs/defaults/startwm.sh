#!/bin/bash
# Startet XFCE-Komponenten direkt, ohne xfce4-session.
# xfce4-session bricht in HA-Containern wegen fehlender systemd-Dienste
# (polkit, consolekit, logind) mit SIGABRT ab.

export DISPLAY="${DISPLAY:-:1}"

# D-Bus Session-Bus starten – von xfce4-session normalerweise gestartet.
# xfconf, xfce4-panel und xfdesktop brauchen ihn zwingend (dbus-x11 Paket).
eval "$(dbus-launch --sh-syntax)"
export DBUS_SESSION_BUS_ADDRESS

# Xvfb-Auflösung auf 1280x720 begrenzen.
# Pixelflux liest den Framebuffer bei jedem Capture-Zyklus komplett —
# kleinere Auflösung = weniger Kernel-Syscalls = weniger sy-CPU.
xrandr --fb 1280x720 2>/dev/null || true

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
