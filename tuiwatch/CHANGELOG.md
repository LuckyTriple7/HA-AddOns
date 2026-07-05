# Changelog

## [0.41.3] - 2026-07-05

### Added
- **Zielregion jetzt Mehrfachauswahl:** Balearen, Italien, Frankreich,
  Griechische Inseln, Adriaküste, Algarve, Zypern ergänzt (Klammer-Texte bei
  bestehenden Chips entfernt). Mehrere Regionen gleichzeitig wählbar (z. B.
  Balearen + Griechische Inseln), „Tagesausflug in der Nähe" bleibt dabei
  exklusiv — schließt automatisch alle anderen Regionen aus und umgekehrt.
  Neue generische „exklusive Option"-Logik in der Wizard-Engine, direkt auch
  für „Kein Gewässer nötig" (Meer/See-Frage) genutzt, das bisher fälschlich
  mit Meer/See kombinierbar war.

### Changed
- **Länder-Ausschluss nur noch bei „Weltweit"/„Egal" sichtbar** — bei einer
  konkreten Zielregion (z. B. Balearen) ergibt die Frage keinen Sinn und
  wird jetzt übersprungen.

## [0.41.2] - 2026-07-05

### Fixed
- **Kosten-Anzeige rundete auf $0.00:** bei kleinen Beträgen (z. B. Gemini
  Flash mit wenigen Tokens) wurden die Preise korrekt berechnet, aber mit
  nur 2 Nachkommastellen angezeigt und damit unsichtbar. Zeigt jetzt bei
  Beträgen unter $0.01 automatisch 4 Nachkommastellen.
- Veralteten Hinweis „Anthropic-Listenpreis" entfernt (gilt jetzt auch für
  Gemini-Preise).

## [0.41.1] - 2026-07-05

### Added
- **KI-Anbieter im Footer umschaltbar:** sind beide API-Keys (Anthropic +
  Gemini) hinterlegt, zeigt der Footer den aktiven Anbieter an — Klick
  wechselt sofort zum anderen, ohne die Add-on-Konfiguration zu öffnen. Ist
  nur ein Key gesetzt, läuft alles automatisch über diesen (kein
  Umschalter nötig, `ai_provider` wird dann ignoriert).

### Fixed
- **Auto-Tags mit Gemini kaputt:** `additionalProperties` im Tag-Schema
  wurde von der echten Gemini-API mit 400 „Unknown name
  additional_properties" abgelehnt (obwohl das lokale SDK es klaglos
  akzeptierte) — wird jetzt vor jedem Gemini-Aufruf mit
  Structured-Output rekursiv aus dem Schema entfernt.
- **`ai_enabled`** berücksichtigte bisher nur `anthropic_api_key` — war nur
  `gemini_api_key` gesetzt, blieben alle KI-Buttons unsichtbar.

## [0.41.0] - 2026-07-05

### Added
- **Google Gemini als zweiter KI-Anbieter:** neue Option `ai_provider`
  (`anthropic`/`gemini`) schaltet global für alle KI-Features (KI-Fazit,
  Vergleich, TripPilot/Tagesausflug, Auto-Tags, Portfolio-Frage) um.
  Eigener API-Key (`gemini_api_key`) und Modellwahl (`gemini_model`:
  gemini-3.1-pro/3.5-flash/2.5-flash). Websuche über Google-Search-
  Grounding statt Anthropics `web_search`-Tool — `ai_max_web_searches`
  gilt weiterhin nur bei Anthropic, Gemini kennt kein Suchlimit.

## [0.40.8] - 2026-07-05

### Added
- **Anzahl Websuchen in der Antwort sichtbar:** zeigt jetzt „🔍 N Websuchen"
  neben Tokens/Kosten unter jedem KI-Ergebnis (Anthropic liefert die Zahl
  direkt in der Nutzungsstatistik mit).

## [0.40.7] - 2026-07-05

### Added
- **Neue Option `ai_max_web_searches`** (Standard 12, 1-50): deckelt, wie oft
  Claude pro KI-Aufruf selbst das Web durchsuchen darf. War bisher
  unbegrenzt, was bei umfangreichen Anfragen (z. B. Reiseberater mit 3
  Zielen + Unterkünften) zu sehr hohen Input-Token-Zahlen/Kosten führen
  konnte. Niedriger spart Tokens/Kosten, höher liefert gründlichere
  Antworten.

## [0.40.6] - 2026-07-05

### Fixed
- **Tagesausflug prüfte sinnlos auf Reisewarnungen** (KI narrierte das sogar
  im Ergebnis) — Reisewarnungs-Check ist jetzt nur noch Teil des normalen
  Urlaubsmodus, nicht mehr beim Tagesausflug.

## [0.40.5] - 2026-07-05

### Changed
- **Tagesausflug schlanker:** „Was ist dir im Urlaub wichtig?" (deckt sich
  mit „Welche Aktivitäten interessieren dich?") und „Wie warm soll es
  sein?" (Zielwahl über allgemeine Temperaturvorliebe ergibt bei einem
  50-600-km-Radius keinen Sinn) werden jetzt übersprungen. Aktivitäten um
  Chip „Natur" ergänzt.

## [0.40.4] - 2026-07-05

### Added
- Tagesausflug: Entfernungs-Chip „bis 50 km" ergänzt.

### Changed
- **„Weiter" ohne Auswahl:** Startort (PLZ/Ort) ist jetzt Pflichtfeld, sobald
  der Schritt angezeigt wird (Auto/Bus/Bahn/Tagesausflug) — „Weiter" bleibt
  deaktiviert bis eine Eingabe da ist, sonst würde die KI eine
  Entfernungsvorgabe ohne Startpunkt bekommen. Unterkunftsart hat jetzt eine
  „egal"-Option (war als einziges Single-Select ohne Escape-Option).

## [0.40.3] - 2026-07-05

### Changed
- **Reiseberater heißt jetzt TripPilot:** neuer Name + Icon (🗺️) in Button,
  Modal, Ergebnis-Titel, KI-Verlauf, „⚙ KI-Prompts" und Doku. Rein
  kosmetisch — interne IDs/Funktionsnamen unverändert.

## [0.40.2] - 2026-07-05

### Changed
- **„Meer?"-Frage aufgeteilt:** neue Frage „Meer oder See?" (Mehrfachauswahl,
  auch beides möglich) vor der Wassertemperatur-Frage. „Kein Gewässer nötig"
  blendet die Temperaturfrage aus.

## [0.40.1] - 2026-07-05

### Fixed
- **Hotelgröße-Frage überflüssig bei anderer Unterkunftsart:** „Wie groß
  darf das Hotel sein?" erscheint jetzt nur noch, wenn bei der
  Unterkunftsart „Hotel" gewählt wurde.

## [0.40.0] - 2026-07-05

### Added
- **Tagesausflug-Modus im Reiseberater:** bei der ersten Frage „Tagesausflug
  in der Nähe" wählbar. Blendet Länder-Ausschluss, Reiseart, Mitreisende,
  Budget, Unterkunft, Flug/Anreiseart und die Freitext-Felder aus, fragt
  stattdessen Startort/max. Entfernung und verfügbare Zeit (Vormittag/
  Nachmittag/Ganzer Tag/inkl. Abend) ab. Eigener KI-Instruktionstext (3
  Tagesausflugsziele mit Aktivität, Anfahrt, groben Öffnungszeiten/Eintritt,
  Einkehr-Tipp, keine Übernachtungsempfehlung), editierbar über „⚙
  KI-Prompts" (4. Sektion). Keine Reise-DNA-Erfassung für Tagesausflüge.
- Aktivitäten-Chips um Zoo/Tierpark, Therme/Wellness-Tag, Sehenswürdigkeit/
  Schloss, Kletterpark, Escape Room, Minigolf, Flohmarkt/Markt ergänzt.

### Fixed
- **Übersicht im Reiseberater-Ergebnis:** zeigte die gewählte Anreiseart
  (Auto/Bus/Bahn/…) nicht an, jetzt ergänzt.

## [0.39.32] - 2026-07-05

### Added
- **Eigene Anreise im Reiseberater:** neue Frage „Wie möchtest du anreisen?"
  (Flugzeug/Auto/Bus/Bahn/Ist mir egal). Bei Auto/Bus/Bahn werden Flugzeit/
  Abflughafen übersprungen, stattdessen Startort (PLZ/Ort) und maximale
  Entfernung abgefragt. Die KI schlägt dann nur noch Ziele in Fahrdistanz
  vor — gilt auch für den Alternative-Vorschlag; der Überraschungs-Vorschlag
  bleibt dabei ebenfalls in Fahrdistanz statt einen anderen Kontinent
  vorzuschlagen.

## [0.39.31] - 2026-07-05

### Added
- **Berge-Details:** wie schon bei Strand — wählt man ⛰️ Berge bei den
  Interessen, fragt der Reiseberater jetzt nach (sanfte Wanderwege,
  anspruchsvolle Gipfeltouren, Skigebiet, Aussicht/Panorama,
  Alm-/Hüttenromantik, Seilbahn/Gondel, ruhig/wenig Tourismus).
- **Aktivitäten-Chips erweitert:** Reiten, Segeln, Angeln, Klettern, Yoga,
  Tennis, Kajak/SUP, Bootsausflüge.
- **JS-Engine-Test:** `tuiwatch/tests/test_wizard_engine.js` prüft die
  `showIf`-Logik der bedingten Wizard-Schritte ohne npm-Dependency, läuft
  jetzt auch in der CI (`test-tuiwatch.yml`).

### Fixed
- **Temperatur-Schritt:** Option „egal" fehlte, jetzt ergänzt.

## [0.39.30] - 2026-07-05

### Fixed
- **Auto-Tags kaputt:** Anthropic lehnte den Structured-Output-Schema mit
  `"Error code: 400 ... maxItems is not supported"` ab. `maxItems` aus dem
  Tags-Schema entfernt, Kappung auf max. 4 Tags jetzt serverseitig nach der
  Antwort.

## [0.39.29] - 2026-07-05

### Changed
- **Strand-Details präzisiert:** „Langer Sandstrand"/„Felsen/gut zum
  Schnorcheln" durch feinere Optionen ersetzt (Feinsandig, Kies/Felsen,
  Naturstrand unberührt, Weitläufig kilometerlang, Flach abfallend,
  Schattenplätze/Palmen, Gut zum Schnorcheln als eigene Option).

## [0.39.28] - 2026-07-05

### Added
- **Reiseberater: Strand-Details:** wählt man bei „Was ist dir im Urlaub
  wichtig?" 🌴 Strand aus, erscheint jetzt ein Folge-Schritt zur genaueren
  Strandart (langer Sandstrand, kleine ruhige Bucht, belebt mit Beach-Bars,
  Felsen/Schnorcheln, direkt am Hotel, Fußweg/Promenade OK) — fließt in
  Zielwahl, Unterkunftsvorschläge und Reise-DNA mit ein. Der Wizard
  unterstützt intern jetzt generisch bedingte Folge-Schritte (`showIf`).

## [0.39.27] - 2026-07-05

### Fixed
- **Reiseberater: Unterkünfte passten nicht zum Ziel:** die KI nannte z. B.
  bei „Teneriffa Süd" Hotels auf Fuerteventura/Gran Canaria. Prompt verlangt
  jetzt explizit, dass alle genannten Unterkünfte in genau dem Ziel/der
  Teilregion aus der Überschrift liegen müssen.

## [0.39.26] - 2026-07-05

### Changed
- **Reiseberater empfiehlt jetzt konkrete Unterkünfte:** je Hauptvorschlag
  Budget/Mittelklasse/Gehoben mit je 2-3 Nennungen, passend zur gewählten
  Unterkunftsart (echte Namen bei Hotel/Apartment/Villa, konkrete
  Wohngegenden bei Ferienwohnung/Airbnb/Camping/Hostel). Nur überwiegend gut
  bewertete Unterkünfte laut Websuche; Hinweis, dass Verfügbarkeit/
  Buchbarkeit (bei TUI auch im Katalog) selbst live zu prüfen ist.

## [0.39.25] - 2026-07-05

### Fixed
- **Abgelaufene Session wird jetzt erkannt:** Lief die Login-Session ab
  (z. B. über Nacht bei offenem Browser-Tab), blieb die Seite scheinbar
  normal sichtbar, aber jeder Klick schlug fehl und die Konsole zeigte nur
  ein schwarzes Fenster. Jetzt wird bei abgelaufener Session automatisch
  neu geladen und die Login-Seite angezeigt. (Betrifft nur den direkten
  Zugriff, nicht HA Ingress.)

## [0.39.24] - 2026-07-04

### Changed
- Footer-Tagline „— verfolgt TUI-Reisepreise" entfernt, steht jetzt nur
  noch „TUIWatch vX.X.X · Prüfintervall: …".

## [0.39.23] - 2026-07-04

### Changed
- **Reiseberater-Fragebogen verfeinert:** Meer-Schritt jetzt mit konkreten
  Temperaturstufen (28°C+, 24–27°C, 20–24°C, egal, kein Meer nötig) statt
  vagem „badewarm wichtig". Unterkunftsart um „Ferienwohnung"/„Airbnb"
  ergänzt. Hotelgröße um „mittelgroß" zwischen Boutique und riesiger
  Clubanlage ergänzt.
- Footer zeigt jetzt die Add-on-Version („TUIWatch v0.39.23 — …").

## [0.39.22] - 2026-07-04

### Added
- **KI-Kosten pro Tag & Monat**, zusätzlich zur Gesamtsumme — neue Anzeige
  im Footer („🔢 KI heute … · Monat … · gesamt …"), auch im KI-Ergebnis-
  Fenster ergänzt. Alle drei Zähler liegen dauerhaft in der Datenbank
  (Label „seit Add-on-Start" war irreführend — die Gesamtsumme hat schon
  vorher jeden Neustart überlebt).
- **KI-Verlauf, Reise-DNA, Kosten-Zähler und eigene KI-Prompts sind jetzt
  Teil von Backup/Restore.** Bisher gingen sie bei einer Wiederherstellung
  verloren. Restore ist wie gehabt nicht-destruktiv: Einstellungen/Zähler
  werden nur übernommen, wenn lokal noch nichts hinterlegt ist — laufende
  Zähler werden nie durch ältere Backup-Werte überschrieben.

## [0.39.21] - 2026-07-04

### Fixed
- **Du-Anrede fehlte noch bei Hotelvergleich, KI-Fazit, Frag dein Portfolio
  und Wochenüberblick** — nur der Reiseberater hatte die Anweisung, die
  anderen KI-Antworten fielen auf Claudes Standard („Sie") zurück. Jetzt
  überall explizit „Du" vorgegeben.
- Hotelvergleich/KI-Fazit gaben teils Rechercheerzählung aus („Ich werde
  jetzt recherchieren…", „Lassen Sie mich noch prüfen…") statt direkt der
  fertigen Antwort — jetzt explizit im Prompt unterbunden.

## [0.39.20] - 2026-07-04

### Docs
- README/DOCS weisen jetzt deutlich darauf hin, dass die Anthropic-API
  kostenpflichtig ist und bei jedem KI-Aufruf reale Kosten entstehen
  (eigener API-Key/eigenes Konto, keine Abbuchung durch TUIWatch selbst).

## [0.39.19] - 2026-07-04

### Docs
- README/DOCS auf aktuellen Stand: neuer Abschnitt „🧭 Reiseberater"
  (Fragebogen, Alternative/Überraschung, Sicherheitsklauseln, Wind/Klima-
  Recherche, Reise-DNA) und „Eigene KI-Prompts" (⚙-Menü im Footer für
  Reiseberater/Hotelvergleich/KI-Fazit) dokumentiert.

## [0.39.18] - 2026-07-04

### Changed
- **Wind-Vergleich im Hotelvergleich verschärft.** Wind ist jetzt ein
  eigener Kriterien-Punkt (statt im Klima-Satz versteckt): pro Hotel eine
  konkrete Zahl (km/h/Beaufort, Reisemonat, ortsgenau), keine allgemeinen
  Regionsangaben. Landet zusätzlich als eigene Zeile mit direktem
  Zahlenvergleich in der Abschluss-Tabelle statt nur als Fließtext.

## [0.39.17] - 2026-07-04

### Fixed
- **Mausrad in Modals (z. B. KI-Verlauf) scrollte die Hauptseite statt des
  Modal-Inhalts.** Modals hatten kein `overscroll-behavior: contain` —
  Scroll-Chaining zur dahinterliegenden Seite behoben, betrifft alle
  Modals.

## [0.39.16] - 2026-07-04

### Added
- Start-Telegram-Nachricht zeigt jetzt die Add-on-Version.

## [0.39.15] - 2026-07-04

### Added
- **KI-Fazit jetzt auch editierbar.** Dritter Abschnitt im „⚙ KI-Prompts"-
  Menü im Footer, gleiches Muster wie Reiseberater/Hotelvergleich
  (Checkbox „Eigenen Prompt verwenden", vorausgefüllter Standard, Cache
  berücksichtigt den aktiven Prompt).

### Changed
- Wind-Recherche jetzt auch beim Hotelvergleich und KI-Fazit: möglichst
  ortsgenau je Hotel/Küstenabschnitt statt nur fürs Land als Ganzes
  (gemeinsame Kriterienliste `_AI_SECTIONS`, wirkt auf beide Features).

## [0.39.14] - 2026-07-04

### Added
- **Eigene KI-Prompts.** Neuer „⚙ KI-Prompts"-Link im Footer: Standard-
  Instruktionstext für Reiseberater und Hotelvergleich einsehen und per
  Checkbox „Eigenen Prompt verwenden" durch eigenen Text ersetzen.
  Sicherheitskritische Klauseln (Länder-Ausschluss, Reisewarnungs-Check,
  TUI-Verfügbarkeit, Reise-DNA-Kontext) bleiben beim Reiseberater immer
  fix und sind nicht überschreibbar. Hotelvergleich-Cache berücksichtigt
  jetzt den aktiven Prompt (kein veraltetes Ergebnis nach Prompt-Änderung
  mehr aus dem 24h-Cache).
- KI-Verlauf zeigt beim Reiseberater jetzt auch den gewählten Monat.

### Changed
- Klima-Recherche im Reiseberater berücksichtigt jetzt auch Windverhältnisse
  und recherchiert möglichst auf Insel-/Teilregion-Ebene statt nur fürs
  ganze Land (z. B. Kapverden: Sal vs. Boa Vista unterscheiden sich stark
  beim Wind).

## [0.39.13] - 2026-07-04

### Added
- **Wildcard-Vorschlag im Reiseberater.** Zusätzlich zu den 3 Empfehlungen
  und der „Alternative" schlägt Claude jetzt einen Abschnitt „🎲
  Überraschung" vor — ein Ziel außerhalb der gewählten Zielregion (andere
  Weltgegend), an das man wahrscheinlich nicht von selbst gedacht hätte,
  aber weiterhin unter Beachtung aller Ausschlüsse (Länder, Reisewarnungen,
  TUI-Verfügbarkeit).

## [0.39.12] - 2026-07-04

### Added
- **Reise-DNA im Reiseberater.** Jede Anfrage berechnet zusätzlich ein
  Präferenzprofil (Strand, Kultur, Nachtleben, Aktiv, Entspannung,
  Kulinarik, Familie, Preisbewusst) direkt aus den Fragebogen-Antworten —
  ohne zusätzlichen KI-Call/Kosten. Wird als Tabelle ans Ergebnis
  angehängt, über mehrere Anfragen hinweg gespeichert (gleitender
  Mittelwert) und der KI beim nächsten Mal als Zusatzkontext mitgegeben.
- Reisedauer: „9–12 Tage" ergänzt. Budget: „2000–3000 €" ergänzt.

### Changed
- KI antwortet im Reiseberater jetzt per Du statt per Sie.

## [0.39.11] - 2026-07-04

### Fixed
- **Ursache gefunden: AdGuard blockte das Freitextfeld.** IDs/Klasse
  `adv-*` wurden von AdGuards generischen Werbeblock-Filtern erkannt
  (Präfix „adv" = advertisement) und das Feld unsichtbar gemacht — bei
  jedem anderen Werbeblocker/Browser reproduzierbar. Alle betroffenen
  IDs/Klasse auf `reiseb-*` umbenannt. Kastengröße wieder auf normales Maß
  (wie „Frag dein Portfolio") zurückgesetzt.

## [0.39.10] - 2026-07-04

### Fixed
- **Freitextfelder im Reiseberater: zweiter Anlauf.** Kasten war weiterhin
  in einem frischen Edge-Profil ohne jede Vorgeschichte unsichtbar — reiner
  Cache-/Service-Worker-Fall damit ausgeschlossen. Textarea nutzt jetzt eine
  echte CSS-Klasse (`.adv-text`, im `<style>`-Block) statt Inline-`style`-
  Attribut, deutlich größer (min. 160px, 3px blauer Rahmen) und mit fest
  codierten Farben statt CSS-Variablen — maximal robust gegenüber allem,
  was Inline-Styles oder Variablen-Auflösung stören könnte.

## [0.39.9] - 2026-07-04

### Fixed
- **Freitext-Felder im Reiseberater kaum sichtbar.** Die beiden Textarea-
  Schritte (Länder-Ausschluss-Freitext, perfekter Urlaub, frühere Reisen)
  waren bei manchen Nutzern praktisch unsichtbar. Kasten jetzt mit
  Mindesthöhe (90px), deutlichem 2px-Akzentrahmen und hellerem Hintergrund
  plus Fallback-Farbwerten (falls CSS-Variablen aus irgendeinem Grund nicht
  greifen).

## [0.39.8] - 2026-07-04

### Changed
- **Reiseart im Reiseberater: Mehrfachauswahl.** „Pauschalreise (TUI)" und
  „Badeurlaub" (o. ä.) lassen sich jetzt kombinieren statt nur eine Option
  wählbar zu haben.

## [0.39.7] - 2026-07-04

### Added
- **Länder ausschließen im Reiseberater.** Neuer Schritt: Klick-Liste
  gängiger Ausschluss-Kandidaten (Türkei, Ägypten, Tunesien, Marokko,
  Kenia, Thailand, Sri Lanka, Dominikanische Republik, Mexiko, Malediven)
  plus Freitext für weitere Länder. Unabhängig davon prüft die KI für
  jedes in Betracht gezogene Land per Websuche aktuelle Reisewarnungen/
  Sicherheitshinweise des Auswärtigen Amts und schlägt betroffene Länder
  standardmäßig nicht vor, außer sie wurden ausdrücklich als Zielregion
  gewünscht.

## [0.39.6] - 2026-07-04

### Added
- **Reiseberater erweitert.** 9 weitere Fragebogen-Schritte: Aktivitäten
  (Tauchen, Wandern, Skifahren, Golf, Safari, Kulinarik …), Unterkunftsart
  & Hotelgröße, ausführliche Hotelwünsche (Erwachsenenhotel, Swim-Up,
  Privatpool, Hausriff, Homeoffice …), Flugzeit & Abflughafen, was im
  Urlaub nervt, sowie zwei Freitext-Schritte („perfekter Urlaub" und
  frühere Urlaubserfahrungen — Claude erkennt darin Hotelketten/-typen
  und leitet ähnliche Ziele ab). Neue Reiseart „Pauschalreise (TUI)"
  schränkt die Empfehlung auf Ziele ein, die TUI tatsächlich im Programm
  hat (per Websuche geprüft). Zielregion „Makaronesien" ergänzt (Kanaren/
  Madeira/Azoren/Kapverden), da Kapverden geografisch nicht zu Europa
  zählt. Jede Antwort endet zusätzlich mit einem „🔀 Alternative"-Vorschlag
  abseits des exakten Profils.

## [0.39.5] - 2026-07-04

### Changed
- **Toolbar entschlackt.** Backup/Restore sind keine Buttons mehr in der
  Toolbar, sondern schlanke Textlinks im Footer (wie „API-Status").
- **Header-Layout korrigiert.** Kopfzeile brach bei mehreren KI-Buttons
  in zwei Zeilen um, weil Logo- und Aktionen-Spalte gleich breit erzwungen
  waren; Spalten sind jetzt inhaltsbreit, Reisen-Countdown zentriert sich
  im verbleibenden Raum statt starr auf der gesamten Kopfzeilen-Mitte.

## [0.39.4] - 2026-07-04

### Added
- **KI-Reiseberater.** Neuer „🧭 Reiseberater"-Button in der Toolbar: geführter
  Fragebogen (Zielregion, Interessen, Reiseart, Mitreisende, Budget, Dauer,
  Reisezeit, Wetterwünsche) mit Klick-Auswahl statt Freitext. Claude schlägt
  danach 3 passende, real existierende Reiseziele vor — freie Empfehlung aus
  KI-Wissen plus Websuche für aktuelle Klimadaten, unabhängig vom eigenen
  Angebots-Portfolio. Landet wie Fazit/Vergleich/Frage im KI-Verlauf und ist
  per E-Mail versendbar.

## [0.39.3] - 2026-07-04

### Added
- **PDF-Parser-Fallback per KI.** Erkennt der Regex-Parser bei einer TUI-
  Reisebestätigung Felder nicht (z. B. nach einer TUI-Layout-Änderung),
  ergänzt Claude sie aus dem PDF-Text — ausschließlich die vom Regex-Parser
  als fehlend markierten Felder, bereits erkannte Werte bleiben unangetastet.
  Structured Output, keine Websuche. Ohne hinterlegten API-Key unverändertes
  Verhalten (reiner Regex-Parser wie bisher).

## [0.39.2] - 2026-07-04

### Added
- **Frag dein Portfolio.** Neuer „❓ Frage"-Button oben: Freitext-Frage zu
  allen aktiven getrackten Angeboten (z. B. „Welches Hotel ist gerade das
  beste Schnäppchen?") — Claude antwortet anhand von Preis, Ort, Sterne/
  Weiterempfehlung, Trend, Wunschpreis und Tags. Landet wie Fazit/Vergleich
  im KI-Verlauf und ist per E-Mail versendbar.

## [0.39.1] - 2026-07-04

### Added
- **Auto-Tag.** Neuer „🤖 Auto-Tag"-Button in der Sammelaktionsleiste der
  Angebotsübersicht: vergibt automatisch 2-4 passende Schlagworte aus einer
  festen Liste (Familie, Strand, Party & Nachtleben, Ruhe & Erholung,
  Wellness & Spa, Sport & Aktiv, Luxus, Budget, Alleinreisende, Kultur &
  Sightseeing, Adults Only, Golf) — ergänzt bestehende Tags, überschreibt
  sie nicht. Structured Output, keine Websuche nötig (schnell & günstig).

## [0.39.0] - 2026-07-04

### Added
- **Wochenüberblick als Fließtext.** Mit hinterlegtem `anthropic_api_key`
  fasst Claude den wöchentlichen Digest zusätzlich in 2-4 Sätzen zusammen
  (größte Ersparnis, dringendste Gelegenheit) — steht oben in Telegram-
  Nachricht und E-Mail, vor der gewohnten Listenform. Best effort: schlägt
  die Zusammenfassung fehl, wird der Digest trotzdem ganz normal verschickt.
- **KI-Analyse per E-Mail.** Neuer „✉ E-Mail senden"-Button im KI-Fazit/
  -Vergleich (auch aus dem KI-Verlauf) — sendet die Analyse als HTML-Mail,
  inkl. Empfänger-Autocomplete aus dem Nextcloud-Adressbuch (falls
  eingebunden), genau wie beim bestehenden Angebots-Mailversand.

## [0.38.9] - 2026-07-04

### Changed
- README/DOCS auf aktuellen Stand gebracht: KI-Fazit, -Vergleich, -Verlauf,
  Token-/Kosten-Anzeige, DB-Größe im Footer dokumentiert.

## [0.38.8] - 2026-07-04

### Added
- Geschätzte Kosten (≈ $X.XX) jetzt auch pro einzelner Analyse sichtbar,
  nicht nur als Gesamtsumme — landet damit auch im KI-Verlauf (ältere,
  vor diesem Update gespeicherte Einträge zeigen sie mangels
  gespeichertem Wert nicht nachträglich an).

## [0.38.7] - 2026-07-04

### Added
- Footer zeigt jetzt die Größe der SQLite-Datenbank an (z. B. „DB: 2.3 MB"),
  aktualisiert alle 5 Minuten.

## [0.38.6] - 2026-07-04

### Added
- **KI-Verlauf.** Neuer „🤖 KI-Verlauf"-Button oben neben „Alle prüfen":
  zeigt alle bisherigen KI-Fazits/-Vergleiche (dauerhaft in der Datenbank
  gespeichert, unabhängig vom 24h-Cache, bis zu 300 Einträge), anklickbar
  zum erneuten Anzeigen, einzeln löschbar.

### Changed
- Alle KI-Buttons (Fazit, Vergleich in Suche & Angebotsübersicht,
  KI-Verlauf) sind nur noch sichtbar, wenn ein Anthropic API-Key in den
  Add-on-Einstellungen hinterlegt ist.

## [0.38.5] - 2026-07-04

### Added
- KI-Fazit/-Vergleich berücksichtigt jetzt Klima zur Reisezeit: historische
  Wassertemperatur, Wetter/Sonnenstunden und Windverhältnisse für Ort und
  Reisemonat (Klimatabellen statt Tagesvorhersage — für weit in der Zukunft
  liegende Termine ist keine echte Vorhersage möglich, nur der langjährige
  Durchschnitt). Reisezeitraum (Startdatum) wird dafür aus der Suche mit
  übergeben.

## [0.38.4] - 2026-07-04

### Added
- **KI-Vergleich auch in der Angebotsübersicht.** Die bestehende
  Mehrfachauswahl (Checkbox → Sammelaktionsleiste „Prüfen/E-Mail/
  Archivieren/Löschen") hat jetzt zusätzlich „🤖 Vergleichen" — vergleicht
  bis zu 5 markierte, bereits getrackte Angebote mit derselben KI-Logik
  wie in der Suche (nutzt zusätzlich den gespeicherten Reise-Detailtext
  des Angebots als Kontext).

## [0.38.3] - 2026-07-04

### Added
- Kumulierte KI-Nutzung seit Add-on-Start: jedes Fazit/Vergleich zeigt jetzt
  zusätzlich Gesamt-Aufrufe, Gesamt-Tokens und grob geschätzte Kosten in USD
  (Anthropic-Listenpreis je Modell) — kein echtes Guthaben (das zeigt nur
  die Anthropic-Console), aber ein Anhaltspunkt ohne zusätzlichen Admin-Key.

## [0.38.2] - 2026-07-04

### Added
- KI-Fazit/-Vergleich zeigt jetzt den Token-Verbrauch der Analyse an
  (Input-/Output-Tokens, ggf. aus Prompt-Cache bediente Tokens; auch bei
  gecachten Ergebnissen aus dem letzten Aufruf sichtbar).
- „📄 PDF exportieren" im KI-Fazit/-Vergleich: öffnet eine druckoptimierte
  Ansicht in neuem Tab, aus der sich der Browser-Druckdialog direkt als PDF
  speichern lässt (kein Server-seitiges PDF-Rendering nötig).

## [0.38.1] - 2026-07-04

### Added
- **KI-Hotelvergleich.** Checkbox je Suchergebnis zum Auswählen (max. 5);
  schwebende Leiste mit „🤖 Vergleichen" ruft Claude einmal für alle
  gewählten Hotels auf — Antwort inkl. Vergleichstabelle und Empfehlung,
  welches Hotel für wen (Familie, Paar, Ruhe, …) am besten passt. Gilt für
  Regionen-Suche und Suche aus einem Angebot gleichermaßen (gleicher Code).

### Fixed
- KI-Fazit/-Vergleich schlug mit Claude Haiku fehl (`does not support
  programmatic tool calling`) — `web_search`-Tool braucht dafür explizit
  `allowed_callers: ["direct"]`.

## [0.38.0] - 2026-07-04

### Added
- **KI-Hotel-Fazit in der Suche.** Neuer „🤖 KI-Fazit"-Button je Suchergebnis:
  Claude (mit Web-Suche) durchsucht aktuelle Bewertungen (HolidayCheck,
  Tripadvisor, Google) und liefert eine ausführliche Einschätzung zu Lage &
  Strand, Zimmern, Restaurants & Bars, Pool/Wellness, Ausstattung und
  Preis-Leistung. Ergebnis wird pro Hotel zwischengespeichert (24 Std.), damit
  erneutes Öffnen keine neue Anfrage auslöst.
- Neue Add-on-Optionen `anthropic_api_key` (Passwortfeld) und `anthropic_model`
  (Auswahl Opus/Sonnet/Haiku/Fable) — ohne hinterlegten Key bleibt die Funktion
  inaktiv und zeigt einen entsprechenden Hinweis.

## [0.37.5] - 2026-07-04

### Fixed
- Coupon-Sensor wird jetzt alle 2 Minuten erneut aus dem Cache an HA gemeldet
  (Timer statt nur einmalig beim Add-on-Start) — bleibt so auch nach einem
  reinen HA-Neustart verfügbar, ohne dass ein manueller "Suchen"-Klick nötig ist.

## [0.37.4] - 2026-07-04

### Fixed
- Teilen-Banner zeigt „Schön war's!" statt „Gute Reise!", wenn die Reise
  bereits beendet ist (Enddatum in der Vergangenheit).
- Coupon-Sensor (`binary_sensor.tuiwatch_aktionscodes`) wird beim Start sofort
  aus dem letzten gespeicherten Abruf gemeldet, statt erst nach dem nächsten
  Live-Abruf (bisher nach HA-Neustart bis zum manuellen „Suchen"-Klick weg).

### Added
- Angebots-E-Mail (manueller Versand) listet jetzt auch Hin-/Rückflugzeiten,
  falls vorhanden.

## [0.37.3] - 2026-07-03

### Added
- **Reise teilen.** Neuer „📤 Teilen"-Button in der Reisen-Detailansicht: legt
  Countdown („X Tage Y Std" bzw. „Gute Reise!" bei bereits abgeflogenen Reisen),
  Reiseziel und Hotel über ein Strand-Banner und teilt das Bild per Web Share
  API (Fallback: Download), wenn der Browser Datei-Teilen nicht unterstützt.
  Schriftgröße schrumpft automatisch bei langen Zielen/Hotelnamen.

## [0.37.2] - 2026-07-03

### Added
- Packliste-Kopfzeile zeigt jetzt zusätzlich erledigt/offen an
  (`66/70 · 24 erledigt · 42 offen`), nicht nur die Gesamtzahl.

## [0.37.1] - 2026-07-03

### Added
- **Bevorstehende Reisen im Wochen-Digest.** Die E-Mail/Telegram-Zusammenfassung
  zeigt jetzt einen Abschnitt „🧳 Bevorstehende Reisen" mit allen künftigen
  (noch nicht abgeflogenen) gebuchten Reisen inkl. Zeitraum und Countdown in
  Tagen — bisher zeigte nur der Seiten-Header die jeweils nächste Reise an.

## [0.37.0] - 2026-07-03

### Added
- **Packliste pro Reise.** Neuer Abschnitt in der Reisen-Detailansicht: beim
  ersten Öffnen wird eine Vorlage (7 Kategorien, an ein mitgebrachtes
  Strandurlaub-Packlisten-PDF angelehnt) automatisch eingespielt — Items lassen
  sich danach frei abhaken, umbenennen, umkategorisieren, löschen und ergänzen
  (begrenzt auf 70 Einträge, damit der Ausdruck auf eine A4-Seite passt). Ein
  „🖨️ Drucken"-Button öffnet eine druckoptimierte Ansicht mit TUIWatch-Kopfbereich
  und Reisedaten (Ziel/Hotel/Zeitraum), „↺ Zurücksetzen" spielt die Vorlage neu ein.
  Auch in Backup/Restore (ZIP) mitgesichert.

## [0.36.2] - 2026-07-03

### Fixed
- CodeQL Path-Injection-Alerts (#179, #181, #182, #183) bei Reise-PDF-Pfaden
  behoben: `_trip_pdf_path` nutzt jetzt `werkzeug.safe_join` statt manueller
  `resolve()`/`relative_to()`-Prüfung — CodeQL erkennt `safe_join` als
  Sanitizer, die manuelle Variante nicht.

## [0.36.1] - 2026-07-03

### Fixed
- Dockerfile kopierte `nextcloud.py` nicht ins Image → `ModuleNotFoundError` beim
  Start. Ergänzt.
- DE/EN-Übersetzungen für die drei neuen `nc_*`-Add-on-Optionen ergänzt (in
  `translations/de.yaml`/`en.yaml` vergessen).

## [0.36.0] - 2026-07-03

### Added
- **Nextcloud-Adressbuch beim E-Mail-Versand.** Der Empfänger-Dialog („Als E-Mail
  senden" / Sammelaktion „E-Mail") bietet jetzt optional ein Autocomplete aus einem
  Nextcloud-Adressbuch (CardDAV) — neue Optionen `nc_addressbook_url` (volle
  Adressbuch-URL aus der Nextcloud-Kontakte-App), `nc_user`, `nc_app_password`.
  Ersetzt den bisherigen reinen `prompt()`-Dialog durch ein Eingabefeld mit
  Autocomplete; Freitext-Adressen bleiben weiterhin möglich, ohne Konfiguration
  ändert sich nichts.

## [0.35.0] - 2026-07-03

### Added
- **Lage-Badges in der Hotelsuche.** Treffer zeigen jetzt Pillen für zutreffende
  Lage-Attribute (Direkt am Strand, Strand < 500m, Sandstrand, Ruhig, Außerhalb) —
  live aus dem hotelseitigen `globalTypes`-Katalog des Suchresponse abgeleitet und
  gegen echte Filterergebnisse verifiziert. „Meerseite" fehlt bewusst: der Code taucht
  im Suchresponse nirgends auf, nur serverseitig fürs Filtern nutzbar.

## [0.34.0] - 2026-07-03

### Added
- **Aktionscode-Hinweis in der Hotelsuche.** Die TUI-Such-API liefert je Hotel im
  `globalTypes`-Katalog den Code `GT03-COUP`, sobald tui.com für dieses Hotel gerade
  einen Aktionscode/Coupon anzeigt (live gegen mehrere Regionen verifiziert — exakter
  Codevergleich, kein Fuzzy-Match). Suchergebnisse mit diesem Flag zeigen jetzt „%
  Aktionscode möglich" unter den Angebotsdetails.

## [0.33.2] - 2026-07-03

### Changed
- Tag-Filter unter der Suchleiste erlaubt jetzt Mehrfachauswahl (ODER-Verknüpfung:
  zeigt Angebote mit mindestens einem der ausgewählten Tags) statt nur einem Tag

## [0.33.1] - 2026-07-03

### Changed
- Anhänge-Pille („＋ PDF") in der Reise-Detailansicht steht jetzt direkt unter der
  Buttonzeile (PDF öffnen/Debug/schließen), nicht mehr ganz unten nach allen
  Reisedetails — vorher leicht zu übersehen

## [0.33.0] - 2026-07-03

### Added
- **Weitere PDFs bei „Meine Reisen".** In der Detailansicht lässt sich jetzt zusätzlich
  zur Reisebestätigung ein weiteres PDF hinterlegen (z. B. der Reiseplan) — reine
  Ablage, ohne Auswertung/Parsing. Anhänge erscheinen als Pille (📎 Dateiname, öffnen/
  entfernen per Klick) unter den Reisedetails. Werden beim Löschen der Reise mit
  entfernt und im Backup/Restore mitgesichert.

## [0.32.1] - 2026-07-03

### Changed
- Tags auf der Angebotskarte: stehen jetzt in der Titelzeile neben dem Hotelnamen
  (mit Abstand) statt in einer eigenen Zeile darunter — spart Platz

## [0.32.0] - 2026-07-03

### Added
- **Tags für Angebote.** Frei vergebbare Schlagworte je Angebot (z. B. „Strand",
  „Familie") — hinzufügen über die ＋-Pille auf der Karte, entfernen per Klick auf den
  Tag. Unter der Suchleiste erscheint eine Pill-Zeile mit allen aktuell verwendeten
  Tags; Klick filtert die Liste live (wie die Textsuche, kein Neuladen), erneuter Klick
  hebt den Filter wieder auf. Tags werden im Backup/Restore mitgesichert.

## [0.31.0] - 2026-07-03

### Added
- Offline-Banner (wie SysWatch): erkennt Verbindungsabbruch über `online`/`offline`-Events,
  `navigator.onLine`-Check beim Start und fehlgeschlagene `/api/offers`-Abrufe (3 Fehlversuche
  in Folge) — abdunkelndes Overlay mit „Neu laden"-Button, verschwindet automatisch sobald
  wieder Daten ankommen

## [0.30.1] - 2026-07-03

### Changed
- Verbose-Log der Such-API (`Such-API POST ...`) zeigt jetzt alle relevanten Suchparameter
  (Zeitraum, Dauer, Reisende, Verpflegung, Lage, Flughäfen, Airlines, Operator, Direktflug)
  statt nur der Regionen-ID — erleichtert Diagnose bei Suchproblemen

## [0.30.0] - 2026-07-03

### Added
- **Lage-Filter in der Hotelsuche.** Neue Checkbox-Zeile unter „Verpflegung": Direkt
  am Strand, Sandstrand, Strand < 500m, Meerseite, Ruhig, Außerhalb — Mehrfachauswahl,
  schränkt die Trefferliste weiter ein (funktioniert in allen Suchmodi: Regionen-Suche,
  Suche aus Angebot, eingefügte TUI-URL). Wird auch in gespeicherten Suchen/Suchabos
  mitgespeichert. Intern übersetzt TUIWatch die IDs in den `logicalExpression`-Code,
  den die TUI-Such-API erwartet (per Live-Test ermittelt und verifiziert — anders als
  bei der Verpflegung reicht die einfache ID hier nicht aus).

## [0.29.0] - 2026-07-03

### Added
- **HA-Binärsensor für Aktionscodes.** Neuer `binary_sensor.tuiwatch_aktionscodes`:
  **an**, solange aktuell öffentliche TUI-Aktionscodes verfügbar sind, sonst **aus**.
  Die einzelnen Codes (Wert, Code, Art) stehen als Attribut `coupons` zur Verfügung —
  damit lassen sich Automationen in Home Assistant bauen, ohne die TUIWatch-UI zu
  öffnen. Nutzt dieselbe `ha_sensors`-Option wie die bestehenden Preis-Sensoren.

## [0.28.1] - 2026-07-03

### Fixed
- **„Exakt"-Checkbox in der Hotelsuche (endgültig behoben).** Der Fix aus 0.27.2
  reichte `duration=exact` als String statt als `["exact"]`-Array durch — ein Live-
  Test gegen die echte TUI-Such-API zeigte aber, dass **beide** Varianten
  stillschweigend ignoriert werden und die API auf 7 Nächte zurückfällt. Die
  Such-API kennt „exact" gar nicht (anders als die Angebots-Detailseite). Berechnet
  jetzt stattdessen die Nächtezahl selbst aus dem gewählten Zeitraum (von/bis) und
  sendet sie als normale Zahl — verifiziert per Live-Abfrage: 13.08.–16.08. liefert
  jetzt korrekt 3-Nächte-Treffer statt 7. Betraf auch die eingefügte TUI-Such-URL
  (`duration=exact` wurde dort zuvor sogar komplett verworfen).

## [0.28.0] - 2026-07-03

### Added
- **Reise-Countdown im Header.** Ist unter „Meine Reisen" eine bevorstehende Reise
  gespeichert, zeigt der Header mittig einen Countdown bis zum Abflug (z. B.
  „Sal / Amilcar Cabral · noch 12 Tage 4 Std"). Die Abflugzeit stammt aus dem
  geparsten Hinflug der importierten PDF; ist kein Hinflug erkannt, wird 00:00 des
  Reisebeginns angenommen. Klick auf den Countdown öffnet „Meine Reisen". Ohne
  bevorstehende Reise bleibt das Widget ausgeblendet.

## [0.27.2] - 2026-07-03

### Fixed
- **„Exakt"-Checkbox in der Hotelsuche.** Bei aktivierter Checkbox wurde die
  Reisedauer entgegen der Auswahl trotzdem als 7 Nächte gesucht, statt der
  tatsächlichen Nächte zwischen von/bis (z. B. 3 Nächte bei 13.08.–16.08.). Ursache:
  der native TUI-Wert `duration=exact` wurde beim Aufbau des Such-API-Requests
  fälschlich in ein Array (`["exact"]`) verpackt statt als reiner String
  durchgereicht — die TUI-API ignorierte den Wert dadurch und fiel auf ihren
  Standard zurück.

## [0.27.1] - 2026-07-02

### Changed
- **Toolbar passt in eine Reihe.** Buttons „🔍 Hotels suchen" → **„Suche"** und
  „⬆ Wiederherstellen" → **„Restore"** umbenannt; dadurch passen alle Toolbar-Buttons
  auch auf schmaleren Fenstern in eine Zeile.

## [0.27.0] - 2026-07-02

### Added
- **🔔 Suchabo / Sammel-Alarm** (Backlog #7). Jede **gespeicherte Suche** lässt sich
  jetzt **beobachten**: Schwellenpreis (pro Person) setzen und TUIWatch führt die Suche
  regelmäßig aus (im `poll_interval`-Takt, mindestens stündlich). Gemeldet wird per
  **Telegram/HA**, wenn ein Hotel **neu unter die Schwelle** fällt oder ein gemeldetes
  **weiter fällt** — je Hotel wird der tiefste gemeldete Preis gemerkt (kein Spam);
  steigt es über die Schwelle und fällt später erneut, wird wieder gemeldet.
  Im UI: Abo-Zeile unter den gespeicherten Suchen (Beobachten, Schwelle, „Jetzt
  prüfen"), aktive Abos mit 🔔 im Dropdown, aktuelle Treffer als normale
  Trefferliste anzeigbar (inkl. „Tracken"). Neue Endpunkte:
  `PATCH /api/searches/<id>` und `POST /api/searches/<id>/check`.

## [0.26.8] - 2026-07-02

### Added
- **PDF-Import: 🔍 Debug-Modus** (Backlog #10). In der Reise-Detailansicht zeigt „Debug"
  den **bereinigten PDF-Text**, je Feld **erkannt/leer** (Chips) und das geparste JSON —
  so lässt sich bei einer künftigen TUI-Layout-Änderung ohne Code-Runde sehen, *warum*
  ein Feld nicht erkannt wurde. Schlägt ein Import komplett fehl (422), öffnet sich die
  Debug-Ansicht automatisch für die hochgeladene PDF (ohne sie zu speichern).
  Inhalte können PII enthalten → nur für den angemeldeten Nutzer, nichts geht ins Log.

## [0.26.7] - 2026-07-02

### Added
- **Automatisches Backup.** TUIWatch legt jetzt einmal pro Woche ein vollständiges
  Backup-ZIP (Angebote inkl. Preisverlauf & Marker, Reisen inkl. PDF, gespeicherte
  Suchen) unter `/addon_config/backups/` ab — dieser Ordner übersteht auch eine
  Neuinstallation des Add-ons. Rotation über `auto_backup_keep` (Standard 5),
  abschaltbar über `auto_backup`. Wiederherstellen wie gehabt im Web-UI.
- Fehlende Options-Übersetzungen (DE/EN) für die Aktionscode-Einstellungen ergänzt.

## [0.26.6] - 2026-07-02

### Added
- **Preis-Einordnung zum 30-Tage-Schnitt.** Die Statistik-Zeile jeder Karte zeigt jetzt
  zusätzlich, wie der aktuelle Preis zum Durchschnitt der letzten 30 Tage steht
  (z. B. „8 % unter Ø 30 T", grün/rot, ab ±1 %) — hilft bei der Frage „jetzt buchen
  oder warten?". Auch als HA-Sensor-Attribut `avg_price_30d`.
- **Trend-Badge mit Prozentwert.** „↘ fällt / ↗ steigt" zeigt jetzt die Stärke der
  Tendenz (z. B. „↘ fällt −3,1 %").

## [0.26.5] - 2026-07-02

### Fixed
- **Preiskalender: Sparschwein höher gesetzt** (leicht oberhalb der Zellmitte, etwas
  kleiner/transparenter) — es verdeckte den Preis am unteren Zellrand.

## [0.26.4] - 2026-07-02

### Changed
- **User-Agent aktualisiert** (Chrome 124 → 139) für die TUI-API-Abrufe — reine
  Auffrischung; die offenen JSON-APIs brauchen keine Tarnung/Rotation.

## [0.26.3] - 2026-07-02

### Changed
- **Preiskalender: schöneres Sparschwein-Icon** (detailliertes Piggy-Bank statt des
  einfachen Symbols), grün eingefärbt, mittig hinter dem Text.

## [0.26.2] - 2026-07-02

### Added
- **Wochenüberblick listet Aktionscodes.** Die wöchentliche Zusammenfassung (Telegram &
  E-Mail) enthält jetzt die aktuellen öffentlichen TUI-Aktionscodes (Wert, Code, buchbar
  bis, Reisezeitraum).
- **Aktionscode-Button leuchtet/pulsiert**, wenn aktuell Codes verfügbar sind.

### Changed
- **Preiskalender: Sparschwein größer & mittig** (hinter dem Text, verdeckt Tag/Preis
  nicht). Zusätzlich lässt sich der Kalender jetzt **mit den Pfeiltasten ← / →** durch die
  Monate blättern (nicht nur per Maus).

## [0.26.1] - 2026-07-02

### Added
- **TUI-Aktionscode-Überwachung (🎟 Aktionscodes).** TUIWatch liest die **öffentlichen**
  Aktionscodes von tui.com (`/aktionscode/`) — **ohne Login, ohne Browser, ohne Captcha** —
  und meldet **neue** Codes (Telegram/HA). Angezeigt werden Wert (z. B. 150/250/300 €),
  „buchbar bis" und Reisezeitraum; erfasst werden myTUI-Codes (`ACMYTUI…`) und Codes ohne
  Konto (`SAVE…`). Dedup nach Wert (kein Spam durch tägliche Datumswechsel im Code),
  Wiederkehr wird erneut gemeldet. Optionen: `notify_aktionscodes`, `aktionscode_min`
  (nur ab Wert melden), `aktionscode_interval` (Standard 6 h). „Jetzt prüfen" im UI.
- Ersetzt den in 0.26.0 verworfenen MyTUI-Coupon-Login-Ansatz (Bot-Schutz/Captcha nicht
  zuverlässig automatisierbar); der zugehörige Code wurde vollständig entfernt.

## [0.26.0] - 2026-07-01

Version Bump, Revert Coupon Feature


## [0.25.17] - 2026-07-01

### Added
- **Preiskalender: Sparschwein-Icon am günstigsten Termin.** Der günstigste Termin
  insgesamt wird zusätzlich zur grünen Markierung mit einem kleinen Sparschwein-Icon
  (SVG) gekennzeichnet — auch in der Legende.

## [0.25.16] - 2026-07-01

### Added
- **„Meine Reisen": Kennzahl „Eigene Kosten".** Neben den Gesamtausgaben (Summe aller
  Reisepreise) zeigt eine neue Kachel den **eigenen Anteil** = je Reise Gesamtpreis
  geteilt durch die Anzahl Reisende, aufsummiert. Auch als Spalte in der Jahrestabelle.
  Die Kacheln „Reisen"/„Nächte" sind dafür kompakter.

## [0.25.15] - 2026-07-01

### Security
- **CodeQL (HIGH) im neuen Backup/Restore behoben.**
  - *SQL aus Nutzerquellen:* Beim Wiederherstellen wurde die Spaltenliste des
    `INSERT INTO offers` aus den Schlüsseln der Backup-Datei gebildet. Die Spalten kommen
    jetzt aus einer festen Code-Whitelist (`_OFFER_RESTORE_COLS`); Werte bleiben
    parametrisiert. Funktional identisch.
  - *Pfad aus Nutzerdaten (2×):* `_trip_pdf_path` validiert den Dateinamen nun zusätzlich
    gegen einen strikt begrenzten Zeichensatz (`[A-Za-z0-9._-]`, nur Basename), bevor ein
    Pfad gebaut wird — schließt Path-Traversal über `pdf_name` aus Backup/Import sicher aus.

## [0.25.14] - 2026-07-01

### Changed
- **Backup & Restore jetzt vollständig.** Das Backup war unvollständig (nur nackte
  Angebots-Eckdaten). Es umfasst nun als **ZIP**: alle Angebote **inkl. Preisverlauf**
  und Diagramm-Marker, **„Meine Reisen" inkl. der Original-PDFs** sowie die
  **gespeicherten Suchen**. Die Wiederherstellung akzeptiert die ZIP (altes JSON weiterhin
  möglich) und arbeitet **nicht-destruktiv** (Upsert per URL/Buchungsnummer/Name –
  nichts wird gelöscht oder doppelt angelegt). Reine Caches (Vergleich/Kalender) werden
  bewusst nicht gesichert (regenerieren automatisch).

## [0.25.13] - 2026-07-01

### Fixed
- **Preiskalender deckt die volle Spanne ab.** Der Kalender reicht jetzt vom aktuellen
  Monat bis deutlich über den Reisezeitraum hinaus (im Beispiel Juli 2026 bis Oktober
  2027) und öffnet im Reisemonat. Die TUI-Kalender-API liefert pro Aufruf nur ein
  begrenztes Fenster (~12 Monate ab Startdatum); wie die TUI-Seite selbst werden nun
  mehrere Abrufe ab fortlaufendem Startdatum zusammengeführt, statt in einem einzelnen
  Aufruf vorne oder hinten abzuschneiden.

## [0.25.12] - 2026-07-01

### Changed
- **Hotelsuche: „Exakt"-Checkbox aufgeräumt.** Das Nächte-Feld ist etwas breiter und
  die „Exakt"-Checkbox sitzt jetzt sauber rechts neben dem Label „Nächte" (statt
  darüber umzubrechen).

## [0.25.11] - 2026-07-01

### Fixed
- **Preiskalender öffnet im Reisemonat & deckt den gewählten Zeitraum ab.** Bei weit
  entfernten Reisen (z. B. Reisebeginn September 2027) startete der Kalender bei einem
  nahen Monat (Dezember 2026) und ließ sich nur bis Juni 2027 blättern – der eigentliche
  Reisemonat war unerreichbar. Ursache: Der Suchbereich der Kalender-API war fix auf
  „heute" verankert, die API liefert aber nur ein begrenztes Fenster ab dem Startdatum.
  Der Suchbereich wird jetzt am gewählten Reisezeitraum verankert (Vorlauf/Nachlauf um
  `startDate`/`endDate`), und der Kalender öffnet direkt im Reisemonat.

## [0.25.10] - 2026-07-01

### Added
- **Hotelsuche: „Exakt"-Checkbox.** Sucht Reisen mit einer Dauer, die exakt dem
  gewählten Zeitraum entspricht (TUI-nativ `duration=exact`; z. B. 01.07.–05.07. →
  4 Nächte). Bei aktivem Häkchen ist das Nächte-Feld gesperrt (die Dauer bestimmt
  TUI) und zeigt zur Info die Tagesdifferenz.
- **Hotelsuche: „Reset"-Button.** Setzt die Suchmaske auf die Standardwerte zurück
  (inkl. Reiseziel, Abflughafen, Datum, Nächte, Reisende und Filter).

### Changed
- **Hotelsuche: Plausibilitäts-Hinweis für die Nächte.** Passen die gewählten Nächte
  nicht in den Reisezeitraum (z. B. 01.07.–03.07. mit 5 Nächten), erscheint ein
  Live-Hinweis und beim Suchen zusätzlich ein Toast. Die Suche wird trotzdem
  ausgeführt.

## [0.25.9] - 2026-06-30

### Security
- **CodeQL (HIGH): SQL-Struktur nicht mehr aus request-nahen Daten ableiten.** Beim
  Reise-Import (`api_trip_import`) wurden die Spaltennamen für INSERT/UPDATE aus
  `row.keys()` gebildet. Obwohl alle Werte parametrisiert (`?`) waren, markierte CodeQL
  die aus Daten abgeleitete Query-Struktur. Spalten kommen jetzt aus einer festen
  Code-Konstante `_TRIP_COLUMNS` (Whitelist, exakte Reihenfolge); ein Assert stellt
  sicher, dass `row` keine unerwarteten Keys enthält. Funktional identisch.

## [0.25.8] - 2026-06-30

### Changed
- **PDF-Parser deutlich robuster gegen Layout-Änderungen.** Neue zentrale
  Vorreinigung (`_clean_text`) entfernt vor dem Parsen einmalig die wiederkehrenden
  Seiten-„Möbel" (Kopf-/Fußzeilen, Rechts-Boilerplate, `Seite X/Y`, wiederholte
  Tabellenköpfe), alleinstehende Fußnoten-Hochzahlen sowie die Punktelinien der
  „auf einen Blick"-Übersicht. Dadurch laufen die Feld-Regexes auf sauberem,
  lückenlosem Text — der häufigste Bruchgrund (eingeschobene Zeilen durch
  Seitenumbruch, z. B. nicht erkannte Rückflüge) entfällt. Künftige Eigenheiten
  werden an **einer** Stelle gepflegt statt in jeder Regex einzeln.

### Added
- **Golden-Test-Korpus** (`tests/fixtures/trips/`): vier echte, PII-bereinigte
  Buchungsbestätigungen (3 Layout-Generationen, 1–7 Reisende) mit erwartetem
  Parse-Ergebnis. Bricht TUI künftig das Format, zeigt der Test exakt, welches
  Feld kippt — gezielter Fix statt Raten.

## [0.25.7] - 2026-06-30

### Fixed
- **PDF-Import: Rückflug über Seitenumbruch.** Lag zwischen Zeit- und Streckenzeile
  eines Fluges ein kompletter Seitenumbruch (Footer + Folgeseiten-Kopf, z. B. bei
  Mallorca-Bestätigungen), wurde der Rückflug nicht erkannt. Der Parser überspringt
  jetzt Zwischenzeilen bis zur Streckenzeile. Zudem werden hochgestellte
  Fußnoten-Ziffern (z. B. „… (PMI) 3") aus Strecke/Flughafen entfernt.

### Added
- **Import-Hinweis bei unvollständiger Erkennung.** Werden beim PDF-Import wichtige
  Felder nicht (vollständig) erkannt (z. B. Hotel, Reisezeitraum, Gesamtpreis, Hin-/
  Rückflug), erscheint ein Hinweis-Toast und ein gelber Hinweisbalken in der
  Reise-Detailansicht mit der Liste der betroffenen Felder.

## [0.25.6] - 2026-06-30

### Added
- **Sortierung „Ort A–Z":** Neue Option im Sortier-Menü der Angebotsliste, die nach
  dem Reiseziel/Ort sortiert (z. B. „Kolymbia, Rhodos"). Angebote ohne Ort wandern ans
  Ende. Die Suche durchsucht den Ort bereits.

## [0.25.5] - 2026-06-30

### Changed
- **Flüge mit Wochentag:** In der Angebotsliste zeigen Hin- und Rückflug jetzt den
  Wochentag vor dem Datum, z. B. „Hin: **Mo** 03.05.2027, 13:30" / „Rück: **Fr**
  14.05.2027, 18:10". Erleichtert die Planung auf einen Blick.

## [0.25.4] - 2026-06-30

### Changed
- **Reisen-Statistik & Liste jetzt pro Person:** Der **€/Nacht**-Wert je Reise (Liste) sowie
  der **Ø €/Nacht** in der Gesamt- und Jahresstatistik werden **pro Person** ausgewiesen
  (Personen-Nächte = Nächte × Reisende). So sind Solo- und Gruppenreisen vergleichbar
  (z. B. Gruppenbuchung mit 7 Reisenden: 282,50 €/Nacht p. P. statt 1.977,50 € für die
  ganze Buchung). Labels mit „p. P." gekennzeichnet.

## [0.25.3] - 2026-06-30

### Fixed
- **PDF-Import:** Reisezeitraum (und damit **€/Nacht** sowie **€/Person/Nacht**) wurde nicht
  berechnet, wenn der Paket-Block die Status-Spalte direkt anhängt
  (`… – Paket (Unterkunft) bestätigt`). Betraf u. a. Buchungen mit mehreren Reisenden. Der
  Zeitraum/Hotel wird jetzt unabhängig vom Zusatztext erkannt; die Pro-Person-Berechnung
  (Division durch die Anzahl der Reisenden, 1–7) greift wieder.

## [0.25.2] - 2026-06-30

### Fixed
- **PDF-Import:** Der **Rückflug** wurde bei manchen Bestätigungen nicht erkannt, wenn die
  Status-Spalte („enthalten") als eigene Zeile zwischen Datums- und Zeitzeile steht. Der
  Flug-Parser überspringt solche Zwischenzeilen jetzt.

## [0.25.1] - 2026-06-30

### Added
- **Reisen-Datenbank:** Pro Buchung jetzt der **Reisepreis pro Nacht** (reiner
  Hotel-/Flug-/Transfer-Preis **nach Rabatt, ohne Extras**) — in der Liste je Reise und in
  der Detailansicht zusätzlich **€/Person/Nacht** (entspricht der „€/Nacht"-Spalte der
  Reisen-Übersicht).
- **Statistik pro Reisejahr** (Reisen, Nächte, Ausgaben, Ø €/Nacht) zusätzlich zur
  Gesamtstatistik.

## [0.25.0] - 2026-06-30

### Added
- **Reisen-Datenbank (PDF-Import):** Neuer Bereich **„🧳 Meine Reisen"** für **gebuchte**
  Reisen. Eine TUI-Reisebestätigung als **PDF** hochladen (oder per Drag & Drop) — die
  Eckdaten (Buchungsnummer, Reisende, Hotel, Zeitraum, Flüge, Extras, Rabatte, Zahlungen,
  Preise) werden ausgelesen. Die **PDF bleibt dauerhaft gespeichert** (unter `/data/trips`)
  und ist je Reise wieder **abrufbar** (öffnen/herunterladen). Reisen lassen sich jederzeit
  **löschen** (inkl. der gespeicherten PDF).
- **Übersichts-Statistik:** Anzahl Reisen, Summe Nächte, Gesamtausgaben und Ø €/Nacht.
- Re-Import derselben Buchungsnummer **aktualisiert** den bestehenden Eintrag (kein Duplikat).
- Der PDF-Parser liegt als eigenes Modul `tripparser.py` vor (für spätere Layout-Anpassungen)
  und ist tolerant gegenüber den bekannten TUI-Layout-Varianten sowie 1–7 Reisenden.

## [0.24.2] - 2026-06-30

### Changed
- **Bereits getrackte Hotels** lassen sich in der Suche jetzt **erneut tracken**: Der
  Button ist nicht mehr deaktiviert, sondern fügt das Hotel mit den **aktuellen
  Suchparametern** (z. B. anderer Zeitraum) als weiteres Angebot hinzu. Das „✓ getrackt"
  am Namen bleibt als Hinweis bestehen; nur exakt identische Angebote (gleiche URL) werden
  weiterhin abgelehnt.

## [0.24.1] - 2026-06-30

### Added
- **„💾 Änderungen speichern"** bei den gespeicherten Suchen: Eine geladene Suche lässt sich
  nach Anpassungen direkt überschreiben, ohne den Namen erneut eingeben zu müssen. Der
  Button ist nur aktiv, wenn eine gespeicherte Suche ausgewählt ist; „★ Speichern" legt
  weiterhin eine neue Suche (mit Namensabfrage) an.

## [0.24.0] - 2026-06-30

### Added
- **Globale Reiseziel-Suche:** Das Suchfeld im Reiseziel-Picker durchsucht jetzt **alle
  Ebenen** des TUI-Reiseziel-Baums. Tippt man z. B. „Kanarische Inseln", erscheint das Ziel
  direkt — ohne erst Spanien öffnen zu müssen. Die Treffer zeigen ihren Pfad
  (z. B. „— Spanien › Kanarische Inseln"). Grundlage ist ein flacher Index des kompletten
  Baums, der beim Start (und danach alle 14 Tage) im Hintergrund aufgebaut und in der
  Datenbank zwischengespeichert wird; manuell neu aufbaubar über `POST /api/destinations/reindex`.
- **Gespeicherte Suchen in der Datenbank:** Favoriten-Suchen liegen nicht mehr nur im
  Browser-Cache, sondern in der Add-on-Datenbank — damit sind sie **geräteübergreifend**
  verfügbar (gleiche Liste auf Handy, Tablet, PC).

## [0.23.1] - 2026-06-29

### Fixed
- **HolidayCheck-Link** trifft jetzt das richtige Hotel: Statt der HolidayCheck-Suchseite
  (die den Begriff nicht zuverlässig auswertete) öffnet der Link eine Google-Suche
  `site:holidaycheck.de <Hotel> <Region>` — der erste Treffer ist die passende
  HolidayCheck-Hotelseite.

## [0.23.0] - 2026-06-29

### Added
- **HolidayCheck-Link:** Die Bewertungszeile (Karte und E-Mail) ist jetzt anklickbar und
  öffnet die HolidayCheck-Hotelsuche zum Hotel (Name + Region). Einen exakten Deep-Link
  liefert TUI nicht — daher die Namenssuche, die zuverlässig beim Hotel landet.

## [0.22.1] - 2026-06-29

### Changed
- **Verlauf-Marker:** größere Trefferzone für den Mouseover — der Tooltip rastet auf den
  nächstgelegenen Marker ein und erscheint sofort beim Annähern (statt nur exakt auf dem
  Fähnchen).

## [0.22.0] - 2026-06-29

### Added
- **Änderungs-Marker im Verlauf-Diagramm:** Wichtige Eingriffe werden als Fähnchen auf
  der Zeitachse markiert — **Zimmerwechsel**, **gebuchter Preis**, **Wunschpreis** und
  **Zurücksetzen**; **Mouseover** zeigt Datum + Beschreibung.
- **Hotelsuche:** Nach **Tracken** eines Treffers öffnet sich direkt die **Zimmerauswahl**
  des neuen Angebots — so lässt sich gleich die gewünschte Kategorie festlegen.

## [0.21.0] - 2026-06-29

### Added
- **Buchungscodes & Flugnummern** je Angebot: **TUI-Buchungscode** (z. B. `LPA21031`),
  **Zimmer-Buchungscode** (z. B. `DZX1A`) und **GIATA-Hotel-ID** werden in der Karte und
  in der E-Mail angezeigt; die **Flugnummern** (z. B. `X3 2168`) stehen in den Hin-/Rück-
  Flugzeilen. Auch als Sensor-Attribute `booking_code`/`room_booking_code`.

## [0.20.4] - 2026-06-29

### Changed
- **Verlauf-Diagramm** zoomt jetzt auf den echten Preisverlauf (mit etwas Polster) —
  kleine Änderungen (z. B. −6 €) sind klar erkennbar. Die gestrichelte
  Vergleichspreis-Linie wurde entfernt (streckte die Achse); der Vergleichspreis steht
  weiter in der Tabellenspalte „Vergleich". Wunsch- und Buchungspreis-Linie bleiben.
- **Kartenliste:** der kleine Inline-Verlaufs-Chart (Spark) wurde entfernt — übersichtlicher
  und platzsparender; der volle Verlauf bleibt über den Button **Verlauf**.
- **Suche:** Reihenfolge der Verpflegungs-Filter zu **AI, VP, HP, Frühstück, Ohne**.

## [0.20.3] - 2026-06-29

### Added
- **Sammelaktion „E-Mail":** Die markierten Angebote lassen sich jetzt direkt als E-Mail
  versenden (Empfänger wird abgefragt, Vorbelegung wie beim normalen Versand). Es werden
  nur die ausgewählten (aktiven) Angebote gesendet.

## [0.20.2] - 2026-06-29

### Fixed
- **Suche markierte archivierte Angebote als „getrackt"**: Ein archiviertes Hotel
  erschien in der Regionssuche weiter als „✓ getrackt" und ließ sich nicht erneut
  aufnehmen. Jetzt zählt nur noch **aktiv** Getracktes (Archiv ausgenommen).

### Added
- **Suchfeld in der Region-Trefferliste**: filtert die angezeigten Treffer sofort nach
  Hotelname, Ort/Land und Verpflegung (Anzahl „X von N").

## [0.20.1] - 2026-06-29

### Fixed
- **Verpflegungsfilter in der Suche** wirkte nicht: HP/VP/Frühstück nutzten ungültige
  Codes (`HP`/`VP`/`F`) und wurden ignoriert — dadurch erschienen z. B. bei „Frühstück"
  auch „Ohne Verpflegung"-Treffer. Jetzt korrekte API-Codes (`HB`/`FB`/`BB`); `AI`
  unverändert. Die Filter schließen die jeweilige **„Plus"-Variante** automatisch ein
  (AI = inkl. „AI Plus/laut Programm", HP = inkl. Halbpension Plus, VP = inkl.
  Vollpension Plus).

### Added
- Verpflegungsfilter **„Ohne"** (ohne Verpflegung) ergänzt.

## [0.20.0] - 2026-06-29

### Added
- **Zimmerauswahl pro Angebot:** Neuer Button **„Zimmer"** zeigt die wählbaren
  Zimmerkategorien (Name + Verpflegung + Preis pro Person + Aufpreis zum günstigsten).
  Standard bleibt das **günstigste** Zimmer; per **„tracken"** lässt sich eine bestimmte
  Kategorie fixieren (dann wird deren Preis verfolgt), **„Details ↗"** öffnet das Zimmer
  mit Fotos/Beschreibung auf tui.com, **„Günstigstes automatisch"** hebt die Festlegung
  auf. Technisch über `roomTypeOpCodes` in der Angebots-URL (Quelle: Offer-API, gruppiert
  nach Zimmercode).

## [0.19.2] - 2026-06-29

### Fixed
- **Poll-Fehler `name 'date' is not defined`** behoben: `date` war in app.py nicht
  importiert, wodurch der Wochenüberblick (bei aktivem `digest_enabled`) bei jeder
  automatischen Prüfung abbrach.

## [0.19.1] - 2026-06-28

### Changed
- **Karten-Layout** mit Hotelbild aufgeräumt: das Bild sitzt jetzt **unter dem Preis**
  (rechte Spalte) statt links, und **Wunschpreis + gebuchter Preis** stehen
  **nebeneinander** (umbrechend auf schmalen Bildschirmen).

## [0.19.0] - 2026-06-28

### Added
- **Gebuchter Preis:** Pro Angebot lässt sich der **tatsächlich gezahlte Preis**
  hinterlegen (Feld „📌 Gebuchter Preis"). Das Tracking läuft weiter; angezeigt wird
  „seit Buchung ±X €" und im Preis-Diagramm eine eigene Linie. **„Günstiger als
  gebucht"-Alarm** (HA/Telegram) meldet, wenn der Preis später deutlich darunter fällt
  (Optionen `notify_booked_drop`, `booked_drop_min_diff`); nur bei neuen Tiefstwerten,
  neustart-fest. Auch als Sensor-Attribute `booked_price`/`booked_diff`.
- **Hotelbild bei getrackten Angeboten:** Beim Tracken aus der Suche wird das Bild
  übernommen; bei per URL hinzugefügten Angeboten wird es beim ersten Check einmalig über
  eine Regionssuche ermittelt (Quelle: TUI-Such-API). Anzeige als Thumbnail in der Karte;
  Sensor-Attribut `image`.

## [0.18.1] - 2026-06-28

### Fixed
- **Fluggesellschaften-Dropdown**: Checkboxen waren verrutscht (die globale Eingabefeld-
  Regel hat sie auf volle Breite gezogen) und das Panel saß versetzt — beides korrigiert
  (Checkboxen feste Größe, Panel linksbündig unter dem Feld).

### Added
- **Suche im Reiseziel-Picker**: Textfeld zum Filtern der aktuell angezeigten Liste
  (z. B. Land eintippen, dann hineinblättern).

## [0.18.0] - 2026-06-28

### Added
- **Hotelsuche: optionaler Fluggesellschaften-Filter** — Dropdown mit Mehrfachauswahl
  (leer = alle). Die Auswahl geht in die Suche und in das getrackte Angebot (dann wird
  der Preis nur mit diesen Airlines verfolgt). Kuratierte Airline-Liste über
  `GET /api/airlines`.

### Changed
- **Such-Defaults**: Sterne ≥ **3** und Weiterempfehlung ≥ **80 %** sind in der Maske
  vorbelegt (jederzeit änderbar).

## [0.17.0] - 2026-06-28

### Added
- **Regressionstests fürs Parsing** (`tuiwatch/tests/`, pytest): prüfen offline gegen
  echte, reduzierte TUI-API-Antworten, dass die Auswertung (Preis, Rabatt, Nächte,
  Verpflegung, Reisende, Flug, Rückreisedatum, Bewertung, Region, Suche, Kalender,
  Reiseziele, Abflughäfen) und die URL-/Helfer-Logik korrekt bleiben. CI-Workflow
  `test-tuiwatch.yml` führt sie bei Änderungen an `tuiwatch/*.py` aus.

### Changed
- `scraper.py` importiert **playwright nur noch lazy** (erst im Browser-Fallback) — das
  Modul ist damit ohne playwright importierbar (Voraussetzung für die Tests; erster
  Schritt zur Verschlankung des Images).

## [0.16.1] - 2026-06-28

### Fixed
- **Übersetzungen** für die neuen Optionen `notify_api_errors`, `digest_enabled` und
  `digest_weekday` (DE + EN) ergänzt — im HA-Konfig-UI wurden zuvor die rohen
  Schlüsselnamen angezeigt.

## [0.16.0] - 2026-06-28

### Added
- **API-Ausfall-Alarm**: Fällt im Selbsttest ein *kritischer* TUI-Endpunkt aus (z. B.
  weil TUI die API geändert hat), meldet TUIWatch das über HA/Telegram und gibt
  Entwarnung, sobald wieder alles läuft. Zustand übersteht Neustarts. Abschaltbar über
  `notify_api_errors`.
- **Selbsttest läuft automatisch ~1×/Tag** und jeweils **vor den Preisprüfungen**, damit
  die Footer-Ampel aktuell bleibt und ein API-Problem erkannt wird, bevor die Abfragen
  daran scheitern.
- **Wochenüberblick (Digest)**: optionale wöchentliche Zusammenfassung per Telegram/E-Mail
  (größte Rückgänge, neue Tiefstwerte, Angebote unter Wunschpreis). Aktivierung über
  `digest_enabled` + `digest_weekday` (1 = Mo … 7 = So); Sofortversand über den Button
  **„📊 Wochenüberblick"**.
- **Trend-Hinweis** je Angebot (↘ fällt / ↗ steigt / → stabil) aus dem bisherigen
  Preisverlauf — als kleines Badge neben der Preisänderung.
- **Sammelaktionen**: Angebote per Checkbox auswählen und gemeinsam **prüfen,
  archivieren oder löschen** (Aktionsleiste erscheint bei Auswahl).

## [0.15.0] - 2026-06-28

### Added
- **API-Selbsttest**: prüft beim Start des Add-ons und manuell, ob alle genutzten
  TUI-Endpunkte (Preis/Angebot, Hotelsuche, Reiseziele, Abflughäfen, Preiskalender,
  Bewertung, Breadcrumb) noch erwartungsgemäß antworten. Ergebnis im **Footer** als
  Ampel (grün/gelb/rot); Klick öffnet die Detailliste mit „Erneut prüfen".
- **Trackerliste nach Reisebeginn sortierbar** (neue Sortieroption; Angebote ohne
  festes Datum ans Ende).

### Changed
- **Günstigerer-Termin-Alarm** kommt nur noch bei einem **wirklich neuen Tiefstwert**
  (anderer Abreisetag oder nochmals tieferer Preis) und übersteht Add-on-Neustarts
  (persistenter Dedup) — keine Wiederholungen mehr bei jeder Prüfung. Abschaltbar über
  `notify_cheaper_date`.
- **Suche: Datumspicker** — „bis" springt automatisch auf „von" und kann nicht mehr
  vor dem Abreisedatum liegen.

### Fixed
- **Nächte-Vergleich für aus dem Kalender getrackte Termine**: das feste Reisefenster
  (genau N Nächte) wird beim Vergleich passend geweitet (`endDate = startDate + Dauer`),
  sodass längere Dauern nicht mehr fälschlich als „nicht abrufbar" erscheinen.

## [0.14.1] - 2026-06-28

### Fixed
- **Kalender-Icon der Datumsfelder im Dark Mode sichtbar** (aufgehellt); im Light Mode
  unverändert. Klick aufs Feld öffnet weiterhin den Kalender, Direkteingabe bleibt möglich.

## [0.14.0] - 2026-06-28

### Added
- **Suche: „Nur Direktflug"-Filter** — zeigt nur Angebote ohne Zwischenstopp
  (Such-API-Parameter `stopOver=0`; wird auch in getrackte Angebote übernommen).

### Changed
- **Fortschrittsanzeige statt Sanduhr**: Nächte-Vergleich zeigt einen echten
  Fortschrittsbalken (geprüfte Dauern X/N); Pro-Person-Vergleich, Suche und Preiskalender
  zeigen einen animierten Balken statt des ⏳-Symbols.
- Suche: Datumsfelder öffnen den Kalender beim Klick aufs ganze Feld; „Suchen"-Button
  rechtsbündig; Filter **„nur Veranstalter TUI"** kürzer als **„TUI"** beschriftet
  (mit erklärendem Tooltip).

## [0.13.0] - 2026-06-28

### Added
- **Eigene Suchmaske mit Reiseziel-Picker** — kein URL-Kopieren mehr nötig: **Reiseziel**
  per Drilldown (Land → Region → Insel) wählen, **Abflughafen** (TUI-Liste), **Zeitraum
  von–bis + Nächte**, **Reisende** und die Filter setzen → **Suchen**. Nutzt die offenen
  TUI-APIs `search-destination` (Regionen/Unterregionen) und `search-departure-airport`.
- **Such-Favoriten**: komplette Maskeneingaben unter einem Namen speichern und wieder
  laden (Dropdown + „★ Speichern" / „Löschen").
- **Sortierung der Trefferliste**: Preis, Preis/Nacht, Weiterempfehlung, Sterne.
- Die bisherigen Wege (TUI-URL einfügen, „Region" aus einem Angebot) bleiben erhalten.

## [0.12.0] - 2026-06-28

### Added
- **Regionssuche direkt aus einem Angebot**: neuer Button **„Region"** je aktivem
  Angebot listet weitere Hotels **derselben Region** (z. B. Gran Canaria) für dieselben
  Reisedaten/Dauer/Reisende/Abflughafen — ohne URL-Einfügen. Die Region kommt aus der
  Angebots-URL (`regionGiataIds`) oder per Breadcrumb über die giataId. Veranstalter und
  Verpflegung des Angebots werden als Filter **vorbelegt** (änderbar), Sterne/
  Weiterempfehlung optional.

### Changed
- **Such-Dialog breiter** (übersichtlichere Trefferliste).

## [0.11.0] - 2026-06-28

### Added
- **Hotelsuche** über **🔍 Hotels suchen**: eine TUI-Such-/Region-URL (mit
  `regionGiataIds`) einfügen → TUIWatch listet alle passenden Hotels der Region mit
  **Sternen, Ort, HolidayCheck-Weiterempfehlung, Verpflegung, Nächten und Preis p. P.**
  Filter direkt im Add-on: **nur Veranstalter TUI**, **Verpflegung** (AI/HP/VP/Frühstück),
  **Sterne ≥** und **Weiterempfehlung ≥ %**. Je Treffer **Tracken**/**Öffnen**, dazu
  **Alle tracken**. Abflughafen/Zeitraum kommen aus der eingefügten URL. Nutzt den neuen
  TUI-Such-Endpoint `hotel-offer-cards/v2/search` (siehe SCRAPING.md).

## [0.10.2] - 2026-06-28

### Fixed
- **Kein unnötiger (langsamer) Browser-Fallback bei „kein Angebot".** Liefert die
  Offer-API **HTTP 400/404/422** (z. B. beim Nächte-Vergleich für eine Dauer ohne Flüge),
  wird das jetzt als gültige Leermenge „Kein Angebot" behandelt — vorher wurde
  fälschlich der minutenlange Chromium-Fallback gestartet. Echte Serverfehler (5xx) /
  Netzwerkfehler lösen weiterhin den Fallback aus.

## [0.10.1] - 2026-06-28

### Fixed
- **Nächte-Vergleich: falsche Preise bei nicht buchbaren Dauern.** Bei Bereichs-Dauern
  wie `7-` lieferte TUI für nicht verfügbare Dauern (z. B. 8–10 Nächte) ersatzweise das
  nächstliegende Angebot (das 7-Nächte-Paket) zurück — diese Zeilen zeigten denselben
  Gesamtpreis und nur eine heruntergerechnete €/Nacht. Es wird nun geprüft, ob die
  **tatsächliche Reisedauer** der angefragten entspricht; weicht sie ab, erscheint
  korrekt „nicht abrufbar".

### Changed
- **Kleinere Buttons** in der Angebots-Fußzeile (kompaktere Schrift/Abstände), damit die
  Aktionsleiste weniger Platz braucht.

## [0.10.0] - 2026-06-28

### Added
- **Nächte-Vergleich**: neuer Button „Nächte" je Angebot öffnet einen Dialog, in dem
  sich per **− / +** eine Spanne einstellen lässt (Default 3, max ±7). Es werden live
  die Preise für **kürzere und längere Reisedauern** abgefragt (z. B. bei 10 Nächten:
  7–9 und 11–13) und als Tabelle gezeigt: **Preis p. P., € pro Nacht, Gesamt, Differenz**.
  Günstigste Zeile grün, aktuelle Dauer markiert; Dauern ohne Flug/Angebot erscheinen
  als „nicht abrufbar". Das Ergebnis wird gespeichert (mit „Neu abfragen").

## [0.9.1] - 2026-06-28

### Fixed
- **Preiskalender-Klick erzeugte ein ungültiges Datum** (HTTP 400 auf tui.com): Es wurde
  `startDate` = `endDate` = angeklickter Tag gesetzt, sodass der Reisezeitraum z. B.
  „21.05.2027 – 21.05.2027, 10 Nächte" lautete. Jetzt wird `endDate = Anreise + Nächte`
  berechnet (Hin- bis Rückreise), passend zur Reisedauer. Gilt für Links- und Rechtsklick
  (Termin öffnen / als neues Angebot speichern). Die Dauer kommt aus dem Preiskalender
  (`duration`).

## [0.9.0] - 2026-06-28

### Added
- **Archiv**: Angebote können archiviert werden — als Überblick über ältere/abgelaufene
  Reisen, ohne dass weiter live abgefragt wird.
  - **Automatisch**: sobald das Rückreisedatum in der Vergangenheit liegt, wandert ein
    Angebot ins Archiv (es ist ohnehin nicht mehr buchbar/abfragbar).
  - **Manuell**: Button „Archivieren" je Angebot (z. B. wenn ausgebucht / nicht mehr
    verfügbar) bzw. „Reaktivieren" zum Zurückholen.
  - Archivierte Angebote sind über den Schalter **„Archiv"** oben einblendbar (eigener
    Abschnitt, gedämpft dargestellt) und werden im Poller/„Alle prüfen", in der
    Übersicht (eigener Zähler + `archived_offers` am Summary-Sensor) und im E-Mail-Versand
    ausgenommen. Backup/Wiederherstellen nimmt den Archiv-Status mit.

### Fixed
- **Pauschalreise inkl. Transfer**: Offer-Abfrage nutzt jetzt `transferIncluded=true`
  (vorher `false`) — passend zur Buchung auf tui.com. Ein in der Original-URL gesetzter
  Wert hat weiterhin Vorrang.

## [0.8.1] - 2026-06-28

### Added
- **Preiskalender → Rechtsklick** auf einen Tag speichert genau diesen Termin als
  **neues, eigenständiges Angebot** (mit fixiertem Datum) und prüft ihn sofort. Linksklick
  öffnet den Termin weiterhin auf tui.com.

## [0.8.0] - 2026-06-28

### Added
- **E-Mail-Versand**: Button „Als E-Mail senden" verschickt alle Angebote als optisch
  aufbereitete HTML-Mail. Empfänger wird vor dem Senden eingegeben (Vorbelegung aus
  `smtp_to`/zuletzt genutzt). SMTP über neue Optionen `smtp_host/port/user/password/
  from/to/tls` (Muster wie MyPage). Footer mit Hinweis + GitHub-Link.
- **Backup & Wiederherstellen**: getrackte Angebote als JSON sichern und importieren
  (überspringt Duplikate, prüft neue sofort).
- **Übersicht** über der Liste: Anzahl Angebote, günstigstes Angebot, Anzahl unter
  Wunschpreis, pausierte — plus HA-**Summary-Sensor** `sensor.tuiwatch_uebersicht`
  (Wert = günstigster Preis; Attribute: günstigstes Angebot, Gesamtzahl, unter Wunschpreis).
- **Preiskalender-Heatmap**: Tage je nach Preis eingefärbt (grün→rot); **Klick auf einen
  Tag öffnet genau diesen Termin auf tui.com**.

## [0.7.2] - 2026-06-28

### Added
- **Ort öffnet Google Maps**: Klick auf den Ort (📍) öffnet das Hotel in Google Maps
  (Suchanfrage Hotelname + Ort; TUI liefert keine Koordinaten).

## [0.7.1] - 2026-06-28

### Changed
- **Konsole deutlich gesprächiger**: Prüfungen zeigen jetzt Name, Preis pro Person,
  Gesamtpreis, Verfügbarkeit und Quelle (API/Browser) sowie Preisänderungen. Zusätzlich
  protokolliert: Hinzufügen, Umbenennen, Pausieren/Fortsetzen, Wunschpreis, manuelle
  Prüfung, Vergleich-/Kalender-Start und gesendete Benachrichtigungen/Alarme.
- **Fehler werden rot markiert** (Log-Level ERROR), echte Ausfälle deutlich sichtbar;
  Ausweichen auf den Browser-Fallback erscheint gelb (WARNING). Verbose-Log zeigt die
  API-URLs zusätzlich.

## [0.7.0] - 2026-06-28

### Added
- **Tracking pausieren** je Angebot (ohne löschen): pausierte Angebote werden bei der
  automatischen Prüfung und „Alle prüfen" übersprungen; manuelles „Prüfen" bleibt
  möglich. Badge „⏸ pausiert" + abgedimmte Karte.
- **CSV-Export** der Preishistorie (Button im Verlauf-Fenster) — mit Excel-tauglichem
  Format (Semikolon, UTF-8-BOM).
- **PWA / installierbar**: Manifest, Service Worker und App-Icons (192/512) — TUIWatch
  lässt sich als App installieren (am besten über Direktzugriff/Reverse-Proxy).
- **Gesamtpreis** zusätzlich zum Preis pro Person (bei mehreren Reisenden) in der Karte
  und als HA-Sensor-Attribute `total_price` / `travellers`.

## [0.6.1] - 2026-06-28

### Fixed
- **Preiskalender bei Dauer-Bereichen** (z. B. `duration=7-` oder `9-12`) lieferte nichts.
  Der Kalender braucht eine einzelne Dauer — es wird jetzt die untere Zahl verwendet
  (wie auf der TUI-Seite).

### Changed
- **Ausführliches Logging** zeigt jetzt auch die **API-Abrufe (URLs) und Ergebnisse**
  in der Konsole (Offer-/Kalender-/Bewertungs-/Ort-Abruf), wenn `verbose_log` an ist.

## [0.6.0] - 2026-06-28

### Added
- **Günstigerer-Termin-Alarm**: Meldung (HA/Telegram), wenn der Preiskalender einen
  anderen Abreisetag deutlich günstiger zeigt als dein getrackter Preis (Schwelle per
  `cheaper_date_min_diff`, Standard 50 €). Aktualisiert nebenbei den Kalender-Cache.
- **Ausverkauft-/Fehler-Alarm**: Meldung, wenn ein Angebot mehrmals in Folge kein
  Ergebnis liefert (ausgebucht/URL veraltet), plus Entwarnung, sobald es wieder klappt.
  Optionen `notify_cheaper_date`, `cheaper_date_min_diff`, `notify_errors`.
- **Angebot umbenennen** direkt im UI (✎ neben dem Namen).
- **Sortierung** der Angebotsliste: Hinzugefügt, Preis, größte Preisänderung,
  Bewertung, Name.
- **Diagramm-Extras**: Wunschpreis-Linie, Vergleichspreis-Verlauf und grüne
  Marker für Preisrückgänge im Verlaufs-Diagramm.

## [0.5.1] - 2026-06-28

### Added
- **Zurücksetzen je Angebot**: Button löscht den kompletten Preisverlauf sowie
  Vergleichs-/Kalender-Cache und startet sofort eine frische Erstabfrage — das Tracking
  beginnt wieder bei „null". Das Angebot selbst (URL, Name, Wunschpreis) bleibt erhalten.

## [0.5.0] - 2026-06-28

### Added
- **Hotelbeschreibung als PDF**: Link je Angebot (öffnet das offizielle TUI-Hotel-PDF).
  Wird aus den Angebotsdaten gebaut und auch als HA-Sensor-Attribut `hotel_pdf` bereitgestellt.

### Changed
- **Preiskalender zeigt jetzt die volle buchbare Spanne** (heute bis ~12–14 Monate,
  inventarabhängig) statt nur des gewählten Zeitraums ±7 Tage — durch alle verfügbaren
  Monate blätterbar; der gewählte Zeitraum bleibt hervorgehoben.

## [0.4.1] - 2026-06-28

### Added
- **Ort/Region je Angebot** (z. B. „Playa del Ingles, Gran Canaria") — wird aus dem
  TUI-Breadcrumb gelesen, in der Karte unter dem Hotelnamen angezeigt, in die
  Schnellsuche aufgenommen und als HA-Sensor-Attribute ergänzt (`location`, `region`,
  `country`).

## [0.4.0] - 2026-06-28

### Added
- **Preiskalender** je Angebot (Button „Kalender"): Monats-Grid mit dem günstigsten
  Preis pro Abreisetag (wie auf tui.com). Markiert den günstigsten Termin (grün) und
  den günstigsten Termin **in deinem gewählten Zeitraum** sowie Tage außerhalb des
  Zeitraums (gedimmt); Monatsnavigation. Wird wie der Vergleich **gespeichert**
  (Zeitstempel + „Neu abfragen"). Respektiert alle Filter der Original-URL.

## [0.3.3] - 2026-06-28

### Fixed
- **Falscher Preis/falsche Verpflegung bei mehreren Verpflegungsarten**: Der
  JSON-Abruf übernahm nicht alle Filter der Original-URL — u. a. `boardTypes`,
  `operators`, `roomTypes`, `viewTypes` fehlten. Dadurch konnte die API ein anderes
  (billigeres) Angebot liefern, z. B. Halbpension statt „Alles Inklusive". Jetzt
  werden **alle Filter der Original-URL** durchgereicht, und die Verpflegungs-Codes
  werden korrekt ins API-Schema übersetzt (`AI` → `GT06-AI`).

## [0.3.2] - 2026-06-28

### Added
- **Schnellsuche**: Suchfeld über der Angebotsliste filtert die geladenen Angebote
  sofort nach Hotel, eigenem Namen, Ziel/Abflughafen und Reise-Details.

## [0.3.1] - 2026-06-28

### Changed
- **Pro-Person-Vergleich wird jetzt gespeichert** (in der Datenbank). Beim Öffnen
  wird das gespeicherte Ergebnis sofort angezeigt — kein unnötiger neuer Abruf mehr.
  Mit **Zeitstempel** („Abgefragt: …") und Button **„Neu abfragen"** für eine
  Aktualisierung auf Wunsch.

## [0.3.0] - 2026-06-28

### Changed
- **Preisabruf jetzt über die offene TUI-JSON-API** statt Seiten-Rendering — rund
  **0,5 s statt 30–60 s**, deutlich robuster (kein HTML-/Text-Parsing). Der
  Headless-Chromium-Scraper bleibt als **automatischer Fallback**, falls die API mal
  nicht erreichbar ist. Der eingegebene Reisezeitraum wird respektiert; getrackt wird
  das per `cheapest`-Flag markierte günstigste Angebot.
- Genauere Daten „gratis" aus der API: exakter Streichpreis/Rabatt, strukturierte
  Flüge (Datum/Zeit/Airline/Stopps/Route) und zuverlässige Verfügbarkeit.

### Added
- **Hotel-Sterne & HolidayCheck-Bewertung** (Ø-Note /6, Anzahl Bewertungen,
  Weiterempfehlung %) in der Karte und als HA-Sensor-Attribute (`stars`, `rating`,
  `rating_count`, `recommendation`).
- **„Kostenlos stornierbar"-Badge** (aus `cancellationType`) in der Karte und als
  Sensor-Attribut `cancellation`.

## [0.2.0] - 2026-06-28

### Added
- **Pro-Person-Vergleich**: Button „Vergleich" am Diagramm öffnet einen Live-Vergleich
  des Preises pro Person für die aktuelle Reisendenzahl gegenüber 2 Personen (bei
  aktuell 2 → 2 ↔ 1). Tabelle mit Preis p. P., Gesamt und Differenz; günstigster
  Preis pro Person grün hervorgehoben. Rein on-demand — nichts wird gespeichert.
- **Einzelzimmer-Riegel**: Bei Einzelzimmer-Angeboten („Einzelzimmer"/„Single Room")
  wird kein Vergleichs-Button angezeigt (2-Personen-Abruf nicht möglich).
- Robuster Vergleichs-Abruf: schlägt der feste Zimmercode für eine andere Belegung
  fehl, wird einmalig ohne `roomTypeOpCodes` erneut versucht.

## [0.1.6] - 2026-06-28

### Fixed
- **Neustart löste sofort eine Komplettabfrage aus**, auch wenn das Prüfintervall noch
  nicht erreicht war. Der Poller arbeitet jetzt **fälligkeitsbasiert**: ein Angebot
  wird erst wieder geprüft, wenn seit seinem letzten Check (über Neustarts hinweg) das
  Intervall verstrichen ist.

## [0.1.5] - 2026-06-28

### Added
- **Favicon** (TUI-Flugzeug-Icon) in Web-UI und Login-Seite.
- **AppArmor-Profil** (`apparmor.txt`, `tuiwatch_addon`) — schränkt das Add-on ein;
  Chromium-konform (inkl. `/dev/shm`).
- **Telegram-Startmeldung**: ist Telegram konfiguriert, kommt beim Start eine kurze
  Statusnachricht („TUIWatch gestartet — N Reisen geladen").

### Fixed
- **Preisdiagramme flackerten** alle paar Sekunden: das UI rendert jetzt nur noch bei
  tatsächlich geänderten Daten neu, statt bei jedem 5-Sekunden-Poll die Canvas neu zu
  zeichnen.

## [0.1.4] - 2026-06-27

### Added
- **Benachrichtigungen** bei Preisänderung und erreichtem Wunschpreis — über
  **Home Assistant** (persistent_notification) und/oder **Telegram** (Bot-Token +
  Chat-ID). Optionen: `notify_ha`, `notify_price_change`, `telegram_bot_token`,
  `telegram_chat_id`.
- **Wunschpreis (Zielpreis) pro Angebot** — im UI eingebbar; wird der Preis ≤ Wunsch,
  kommt eine Benachrichtigung. Auch als Sensor-Attribut `target_price`.
- **Statistik je Angebot**: niedrigster/höchster/Durchschnittspreis + „Bestpreis"-Badge
  (UI) sowie Sensor-Attribute `min_price`, `max_price`, `avg_price`.

### Changed
- **Robusterer Abruf**: bis zu 2 Versuche bei Fehlschlag; bestätigter Gesamtpreis nach
  Verfügbarkeitsprüfung; die Haupt-Angebotskarte wird zuverlässiger getroffen
  (keine „Empfehlungs"-Karte).

### Security
- Technische Exception-Texte werden nicht mehr im UI/Sensor angezeigt, sondern nur
  noch ins Log geschrieben (generische Meldung nach außen).

## [0.1.3] - 2026-06-27

### Changed
- **Getrackt wird jetzt der konkrete „Günstigster Preis"** (erste Angebotskarte,
  z. B. 1.978 €) statt des unverbindlichen „ab"-Lockpreises der Dein-Angebot-Box.
  Genauer und buchungsnah.

### Added
- **Flugdetails**: Hin- und Rückflug (Datum, Uhrzeit, Airline, Direkt/Umstieg)
  sowie Zimmer und Abflughafen werden ausgelesen, in der Karte angezeigt und als
  HA-Sensor-Attribute (`flight_outbound`, `flight_return`, `room`,
  `departure_airport`) gespeichert.
- **Verfügbarkeitsprüfung**: TUIWatch klickt „Verfügbarkeit prüfen" und erfasst,
  ob das Angebot verfügbar ist. Anzeige als Badge (✓/✗) und als HA-Sensor-Attribut
  `available` (true/false).

## [0.1.2] - 2026-06-27

### Added
- **Home-Assistant-Sensoren**: je Angebot ein Sensor `sensor.tuiwatch_<hotelname>`
  (bei gleichem Hotelnamen `_2`, `_3` …). Wert = aktueller Preis in €, bei Fehler
  `unavailable`. Attribute u. a. `description` (Reise-Eckdaten), `hotel`, `old_price`,
  `discount`, `last_checked`, `url`. Per Option `ha_sensors` abschaltbar.
  Verwaiste Sensoren werden automatisch entfernt.
- **Übersetzungen der Add-on-Konfiguration** (DE/EN) für die HA-Optionsseite.

## [0.1.1] - 2026-06-27

### Fixed
- **Konsole leer hinter Ingress**: Die Konsole hängte beim Aufruf von `/api/console`
  den Ingress-Pfad nicht an (G war nicht über `window` erreichbar) → 401, keine
  Ausgabe. `G` wird jetzt an `window` gehängt, sodass der korrekte Ingress-Pfad
  verwendet wird.

## [0.1.0] - 2026-06-27

### Added
- Erste Version: **TUIWatch — Reisepreis-Tracker** für TUI-Pauschalreisen
- Beliebig viele TUI-Angebots-URLs verfolgen (URL von tui.com einfügen)
- Preis-Auslesen per Headless-Chromium (Playwright) — liest die „Dein Angebot"-Box
- Speichert den Preisverlauf in SQLite und zeigt ihn als Diagramm
- Anzeige von aktuellem Preis, Vergleichspreis, Rabatt und **Delta** (gestiegen/gefallen)
- Automatischer Hotelname (`Riu Papayas`) und Reise-Eckdaten als Beschreibung
- Periodische Prüfung (Standard alle 6 h) + manuelles „Prüfen" / „Alle prüfen"
- Versteckte Konsole per Doppelklick auf das Logo (Hintergrund-Logs)
- Login-Schutz beim Direktzugriff; hinter HA-Ingress automatisch authentifiziert
- Oberfläche auf Deutsch
