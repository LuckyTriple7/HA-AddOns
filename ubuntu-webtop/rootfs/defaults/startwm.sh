#!/bin/bash
# Startet XFCE-Komponenten direkt, ohne xfce4-session.
# xfce4-session bricht in HA-Containern wegen fehlender systemd-Dienste
# (polkit, consolekit, logind) mit SIGABRT ab.

export DISPLAY="${DISPLAY:-:1}"

# Fenstermanager ohne Compositor (verhindert schwarzen Bildschirm in virtuellen Umgebungen)
xfwm4 --compositor=off &

# Kurz warten bis WM registriert ist
sleep 2

# Desktop-Hintergrund und Icons
xfdesktop &

# Panel (taskbar)
xfce4-panel &

# Vordergrundprozess – hält den s6-Service am Leben
# Hinweis: thunar --daemon wird NICHT gestartet, da der Thumbnailer-Dienst
# (org.freedesktop.thumbnails.Thumbnailer1) in HA-Containern nicht verfügbar ist
# und ständige D-Bus-Fehlermeldungen + CPU-Last verursacht.
exec sleep infinity
