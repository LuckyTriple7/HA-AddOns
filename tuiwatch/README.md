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
| `ai_provider` | KI-Anbieter für alle KI-Features: `anthropic` (Standard), `gemini` oder `perplexity` |
| `gemini_api_key` / `gemini_model` | Nur relevant bei `ai_provider: gemini` |
| `perplexity_api_key` / `perplexity_model` | Nur relevant bei `ai_provider: perplexity` |
| `verbose_log` | Ausführlichere Logs |

Es gibt weitere Optionen für **Benachrichtigungen** (Preisänderung, günstigerer
Termin, „günstiger als gebucht", API-Ausfall, Wochenüberblick), **Home-Assistant-
Sensoren** (`ha_sensors`) sowie **Telegram** und **SMTP/E-Mail** — Details in
[DOCS.md](DOCS.md).

## KI-Fazit (optional)

> ⚠️ Die Anthropic-/Gemini-/Perplexity-API ist **kostenpflichtig** (eigener
> API-Key, eigenes Konto beim jeweiligen Anbieter). Bei jedem KI-Aufruf
> entstehen reale Kosten nach der Preisliste des gewählten Anbieters —
> TUIWatch zeigt geschätzte Kosten pro Aufruf und eine laufende Gesamtsumme
> an, bucht aber selbst nichts ab und kennt dein echtes Guthaben nicht.

Mit hinterlegtem API-Key bewertet Claude (oder wahlweise Gemini/Perplexity,
siehe `ai_provider`) einzelne Suchtreffer ausführlich (Lage, Zimmer, Restaurants,
Pool, Klima zur Reisezeit) oder vergleicht bis zu 5 Hotels nebeneinander —
inkl. Token-/Kosten-Anzeige, PDF-Export und dauerhaftem Verlauf. Zu jedem
Ergebnis lässt sich außerdem eine **Folgefrage** stellen (echte Konversation,
auch nachträglich aus dem Verlauf). Details:
[DOCS.md](DOCS.md#ki-fazit--vergleich--verlauf).

## 🗺️ TripPilot (optional)

Geführter Klick-Fragebogen (Zielregion, Interessen, Budget, Reisezeit,
Wetter, Hotelwünsche, Flug/eigene Anreise u. v. m., inkl. eigenem
Tagesausflug-Modus) — Claude schlägt danach 3 passende Reiseziele plus eine
Alternative und eine Überraschung außerhalb der gewählten Region vor.
Berechnet nebenbei ein persönliches Präferenzprofil („Reise-DNA"), ganz ohne
Zusatzkosten. Prompts für TripPilot, Hotelvergleich und KI-Fazit lassen sich
über **⚙ KI-Prompts** im Footer auch selbst anpassen. Die Fragen selbst stehen
in `/config/trippilot/questions.json` und sind frei editierbar — Fragetext,
Reihenfolge, Antwortmöglichkeiten und wann eine Frage erscheint; ein
Add-on-Update überschreibt die Datei nicht.
Details: [DOCS.md](DOCS.md#-trippilot).

## Preiskalender

Der Kalender-Button zeigt den Preis für **jeden Abreisetag** eines Angebots in
einem Monatsraster (Heatmap günstig→teuer) — inklusive **Trend-Ansicht** (welche
Tage seit dem letzten Abruf teurer/günstiger geworden sind), Preisverlauf-
Mini-Diagramm je Tag und einer Liste der größten Bewegungen. Ändert sich ein
bereits bekannter Preis, pulsiert der Kalender-Button und optional kommt eine
Benachrichtigung über HA/Telegram/Wochenüberblick. Ein KI-Button fasst die
Kalenderpreise zusammen und empfiehlt günstige/teure Monate (funktioniert mit
jedem konfigurierten KI-Anbieter). Details: [DOCS.md](DOCS.md#preiskalender).

## Markttrend

Preistrend für **deine** Reisetermine (14-Tage-Fenster + Index seit
Aufzeichnungsbeginn). Breite Basis: einmal pro Tag läuft jede deiner gespeicherten
Suchen erneut, verglichen wird jedes Hotel mit sich selbst vom Vortag (Median über
alle Treffer). Zusätzlich der schmalere Trend aus den eigenen getrackten Angeboten —
der überlebt auch das Löschen einzelner Angebote. Details:
[DOCS.md](DOCS.md#markttrend).

## KI-Buchungsscore ("Orakel")

0–100-Score, ob jetzt ein guter Zeitpunkt zum Buchen ist — pro Angebot oder pro
Destination, aus Preisverlauf, Markttrend und (falls vorhanden) Kalender-
Saisonalität berechnet, mit klarer Kennzeichnung Daten vs. Annahme. Details:
[DOCS.md](DOCS.md#ki-buchungsscore-orakel).

## Hinweise

- Ändert TUI seine APIs, erkennt der **API-Selbsttest** das (Ampel im Footer) und
  TUIWatch weicht auf den Browser-Fallback aus. Bricht auch dieser (Layout-Änderung),
  hilft die Neukalibrierung in [SCRAPING.md](SCRAPING.md).
- Bitte ein faires Prüfintervall lassen (nicht im Minutentakt).
- Tipp: Doppelklick auf das **TUIWatch**-Logo öffnet eine Konsole mit den
  Hintergrund-Logs, Rechtsklick zeigt die nächsten Läufe der Hintergrund-Aufgaben.
