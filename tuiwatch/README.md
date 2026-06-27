# TUIWatch — Reisepreis-Tracker

Verfolgt den Preis konkreter **TUI-Pauschalreisen** über die Zeit und zeigt dir,
ob er **gestiegen oder gefallen** ist — inklusive Preisverlauf-Diagramm.

## Wie es funktioniert

TUI bietet keine öffentliche Preis-API, und der Preis wird auf der Webseite erst
per JavaScript geladen. TUIWatch rendert die Angebotsseite daher mit einem
echten (Headless-)Browser und liest den Preis der **„Dein Angebot"-Box** aus —
also genau das Angebot, das zu deiner Suche (Datum, Personen, Zimmer,
Abflughafen) passt.

## Benutzung

1. Auf [tui.com](https://www.tui.com) die gewünschte Reise mit allen Details suchen
   (Reisezeitraum, Personen, Abflughafen …).
2. Die **Adresszeile (URL)** dieser Angebotsseite kopieren.
3. Im TUIWatch-Web-UI oben einfügen und **Hinzufügen** klicken — optional einen
   eigenen Namen vergeben.
4. TUIWatch prüft den Preis regelmäßig (Standard alle 6 Stunden) und zeigt
   aktuellen Preis, Vergleichspreis, Rabatt, Verlauf und die Veränderung an.

> Getrackt wird immer **genau diese eine Konfiguration**. Für eine andere
> Reisedauer/Belegung einfach eine zweite URL hinzufügen.

## Optionen

| Option | Bedeutung |
|---|---|
| `username` / `password` | Login beim Direktzugriff (über Ingress nicht nötig) |
| `session_hours` | Gültigkeit der Anmeldung in Stunden |
| `poll_interval` | Prüfintervall in Sekunden (Standard 21600 = 6 h, min. 600) |
| `verbose_log` | Ausführlichere Logs |

## Hinweise

- Scraping kann brechen, wenn TUI das Seitenlayout ändert — dann zur
  Neukalibrierung [SCRAPING.md](SCRAPING.md) folgen.
- Bitte ein faires Prüfintervall lassen (nicht im Minutentakt).
- Tipp: Doppelklick auf das **TUIWatch**-Logo öffnet eine Konsole mit den
  Hintergrund-Logs.
