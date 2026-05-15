#!/bin/bash
# Startet XFCE-Komponenten direkt, ohne xfce4-session.
# xfce4-session bricht in HA-Containern wegen fehlender systemd-Dienste
# (polkit, consolekit, logind) mit SIGABRT ab.

export DISPLAY="${DISPLAY:-:1}"

# D-Bus Session-Bus starten – von xfce4-session normalerweise gestartet.
# xfconf, xfce4-panel und xfdesktop brauchen ihn zwingend (dbus-x11 Paket).
eval "$(dbus-launch --sh-syntax)"
export DBUS_SESSION_BUS_ADDRESS

# GNOME Keyring starten – speichert SMB-Passwörter für Thunar/gvfs
eval "$(gnome-keyring-daemon --start --components=secrets)"
export GNOME_KEYRING_CONTROL GNOME_KEYRING_PID SSH_AUTH_SOCK

# XDG_RUNTIME_DIR setzen – normalerweise von systemd-logind erledigt, fehlt in HA-Containern.
# Ohne diese Variable findet GIO den GVFS-FUSE-Mount nicht → g_file_get_path() gibt NULL
# zurück → Thunar übergibt keinen Dateipfad an externe Apps wie Geany.
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 0700 "$XDG_RUNTIME_DIR"

# GVFS-Daemon + FUSE-Bridge:
# gvfsd-fuse hängt den GVFS-Namespace (SMB …) als echtes Dateisystem unter
# $XDG_RUNTIME_DIR/gvfs ein, damit Apps wie Geany normale open()-Aufrufe nutzen können.
# Pfad ist Multiarch-abhängig (Debian Bookworm: /usr/lib/<arch>/gvfs/).
GVFSD_FUSE=$(ls /usr/lib/*/gvfs/gvfsd-fuse /usr/lib/gvfs/gvfsd-fuse 2>/dev/null | head -1)
/usr/lib/gvfs/gvfsd &
sleep 1
if [ -n "$GVFSD_FUSE" ]; then
    mkdir -p "$XDG_RUNTIME_DIR/gvfs"
    "$GVFSD_FUSE" "$XDG_RUNTIME_DIR/gvfs" &
fi

# Avahi-Daemon starten – verhindert GVFS-Warnungen beim DNS-SD-Backend
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
