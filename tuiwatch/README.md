# TUIWatch — Reisepreis-Tracker

Verfolgt den Preis konkreter **TUI-Pauschalreisen** über die Zeit und zeigt dir,
ob er **gestiegen oder gefallen** ist — inklusive Preisverlauf-Diagramm.

## Wie es funktioniert

TUIWatch liest den Preis **direkt aus den offenen TUI-JSON-APIs** (schnell und
robust). Es ermittelt die **günstigste konkrete Angebotskarte** — den buchbaren
„Günstigster Preis" inkl. **Flugdetails** (Hin-/Rückflug), Zimmer und
**Verfügbarkeit**, passend zu deiner Suche (Datum, Personen, Zimmer, Abflughafen).
Fällt eine API aus, schaltet TUIWatch automatisch auf das langsamere Auslesen per
**Headless-Browser** um (Fallback). Details: [SCRAPING.md](SCRAPING.md).

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
| `anthropic_api_key` | Anthropic API-Key — aktiviert das KI-Fazit (leer = aus) |
| `anthropic_model` | Claude-Modell fürs KI-Fazit (Opus/Sonnet/Haiku/Fable) |
| `verbose_log` | Ausführlichere Logs |

Es gibt weitere Optionen für **Benachrichtigungen** (Preisänderung, günstigerer
Termin, „günstiger als gebucht", API-Ausfall, Wochenüberblick), **Home-Assistant-
Sensoren** (`ha_sensors`) sowie **Telegram** und **SMTP/E-Mail** — Details in
[DOCS.md](DOCS.md).

## KI-Fazit (optional)

Mit hinterlegtem `anthropic_api_key` bewertet Claude einzelne Suchtreffer
ausführlich (Lage, Zimmer, Restaurants, Pool, Klima zur Reisezeit) oder
vergleicht bis zu 5 Hotels nebeneinander — inkl. Token-/Kosten-Anzeige, PDF-
Export und dauerhaftem Verlauf. Details: [DOCS.md](DOCS.md#ki-fazit--vergleich--verlauf).

## Hinweise

- Ändert TUI seine APIs, erkennt der **API-Selbsttest** das (Ampel im Footer) und
  TUIWatch weicht auf den Browser-Fallback aus. Bricht auch dieser (Layout-Änderung),
  hilft die Neukalibrierung in [SCRAPING.md](SCRAPING.md).
- Bitte ein faires Prüfintervall lassen (nicht im Minutentakt).
- Tipp: Doppelklick auf das **TUIWatch**-Logo öffnet eine Konsole mit den
  Hintergrund-Logs.
