#!/bin/sh
set -e
# TUIWatch bedient Anfragen mit vielen Threads (waitress 32 + Share-Server 8 +
# Hintergrund-Aufgaben). glibc legt pro Thread eigene Speicher-Arenen an und gibt
# sie nicht wieder her — gemessen stand die Anzeige des Add-ons dauerhaft bei rund
# 700 MB, obwohl weder ein Browser lief noch die Datenbank gross war. Zwei Arenen
# reichen fuer diese Last und halten den Verbrauch bei dem, was wirklich belegt ist.
export MALLOC_ARENA_MAX=2

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] TUIWatch startet auf Port 17794..."
exec python3 /app/app.py
