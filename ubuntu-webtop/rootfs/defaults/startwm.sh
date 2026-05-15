#!/bin/bash
# Startet XFCE-Komponenten direkt, ohne xfce4-session.
# xfce4-session bricht in HA-Containern wegen fehlender systemd-Dienste
# (polkit, consolekit, logind) mit SIGABRT ab.

export DISPLAY="${DISPLAY:-:1}"

# XDG_RUNTIME_DIR setzen – von systemd-logind normalerweise gesetzt, fehlt in HA.
# Muss als erstes gesetzt werden, damit D-Bus, Keyring und GVFS ihre
# Sockets/Mounts unter dem richtigen Pfad ablegen.
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 0700 "$XDG_RUNTIME_DIR"

# D-Bus Session-Bus starten – von xfce4-session normalerweise gestartet.
# xfconf, xfce4-panel und xfdesktop brauchen ihn zwingend (dbus-x11 Paket).
eval "$(dbus-launch --sh-syntax)"
export DBUS_SESSION_BUS_ADDRESS

# GNOME Keyring starten – speichert SMB-Passwörter für Thunar/gvfs
eval "$(gnome-keyring-daemon --start --components=secrets)"
export GNOME_KEYRING_CONTROL GNOME_KEYRING_PID SSH_AUTH_SOCK

# GVFS-Daemon starten (für Thunar SMB-Zugriff über GIO).
# Hinweis: gvfsd-fuse wurde entfernt – das FUSE-Kernel-Modul ist im
# HA-Container nicht verfügbar. SMB-Dateien werden stattdessen vom
# geany-gio Wrapper via gio copy lokal kopiert.
/usr/lib/gvfs/gvfsd &
sleep 1

# Avahi-Daemon (mDNS/DNS-SD) – unterdrückt GVFS dns-sd-Warnungen im Log
avahi-daemon --no-rlimits -D 2>/dev/null || true

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
