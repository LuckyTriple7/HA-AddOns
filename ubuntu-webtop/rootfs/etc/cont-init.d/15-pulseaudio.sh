#!/bin/sh
# Ab 2.0.0 (Selkies-Basis) startet das Base-Image PulseAudio über svc-pulseaudio
# mit der System-Konfiguration; svc-selkies legt danach die Sinks "output" und
# "input" per pactl an (Socket unter PULSE_RUNTIME_PATH=/defaults).
#
# Bis 1.8.x (KasmVNC) haben wir eine eigene default.pa/client.conf unter
# /config/.config/pulse geschrieben (Sink auto_null, Socket /tmp/pulse-runtime).
# Liegt die noch im persistenten /config, lädt PulseAudio sie statt der
# System-Konfiguration: pactl findet keinen Socket, Selkies startet ohne Ton.
# Deshalb nur unsere eigenen Dateien (erkennbar an auto_null) beiseitelegen,
# nicht löschen; fremde/eigene Anpassungen des Nutzers bleiben unangetastet.

PULSE_CFG=/config/.config/pulse

for f in default.pa client.conf; do
    if [ -f "${PULSE_CFG}/${f}" ] && grep -q "auto_null" "${PULSE_CFG}/${f}"; then
        mv "${PULSE_CFG}/${f}" "${PULSE_CFG}/${f}.v1-kasmvnc.bak"
        echo "[pulse] Alte KasmVNC-Konfiguration ${f} nach ${f}.v1-kasmvnc.bak verschoben"
    fi
done
