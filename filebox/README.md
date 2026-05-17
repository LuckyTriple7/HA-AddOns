# FileBox

Web-Oberfläche zum Hoch- und Herunterladen von Dateien direkt in Home Assistant — Dateien liegen in `/share` und sind für alle Add-ons zugänglich.

## Installation

Dieses Add-on ist Teil des [LuckyTriple7 HA Add-Ons Repository](https://github.com/LuckyTriple7/HA-AddOns).

## Funktionen

- Dateien hochladen und herunterladen
- Ordner erstellen, umbenennen, löschen
- Vorschau für Bilder und Textdateien
- Direkter Zugriff auf `/share` — für alle HA Add-ons gemeinsam nutzbar

## Technischer Aufbau

- **FileBrowser** — schlankes Open-Source File-Manager-Tool (Go, einzelne Binary)
- Dateien in `/share`
- Datenbank (Einstellungen) in `/data/filebrowser.db`
- Nur amd64
