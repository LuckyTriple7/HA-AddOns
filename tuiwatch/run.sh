#!/bin/sh
set -e
# TUIWatch bedient Anfragen mit vielen Threads (waitress 32 + Share-Server 8 +
# Hintergrund-Aufgaben). glibc legt pro Thread eigene Speicher-Arenen an und gibt
# sie nicht wieder her — gemessen stand die Anzeige des Add-ons dauerhaft bei rund
# 700 MB, obwohl weder ein Browser lief noch die Datenbank gross war. Zwei Arenen
# reichen fuer diese Last und halten den Verbrauch bei dem, was wirklich belegt ist.
export MALLOC_ARENA_MAX=2
# Pythons Kleinobjekt-Allocator (pymalloc) gibt einen 1-MB-Block erst zurueck, wenn
# er ganz leer ist. Nach einer Spitze auf 1 GB hielten verstreute Ueberlebende 401 MB
# freien Speicher fest, an den malloc_trim nicht herankommt (Speicher-Analyse,
# 0.113.30). Mit glibc-malloc gibt der Trim auch Luecken mitten im Heap zurueck:
# im Nachbau 750 MB -> 148 MB nach dem Aufraeumen.
export PYTHONMALLOC=malloc

echo "[INFO] [$(date '+%Y-%m-%d %H:%M:%S')] TUIWatch startet auf Port 17794..."
exec python3 /app/app.py
