# ReactorSim

Kernkraftwerks-Leitstand als Browser-Spiel. Du bist Reaktorfahrer: Anlage im
Fahrbereich halten, der Netzanforderung folgen, Störungen beherrschen.

Drei Reaktortypen mit echten physikalischen Eigenheiten:

| Typ | Leistung | Charakter |
|---|---|---|
| **DWR** — Druckwasserreaktor | 3850 MWth / 1400 MWe | Zwei Kreisläufe, 158 bar, kein Sieden im Kern. Steuerstäbe schnell, Borsäure langsam. Alle Rückkopplungen negativ — verzeiht viel. |
| **SWR** — Siedewasserreaktor | 3840 MWth / 1344 MWe | Ein Kreislauf, Dampf direkt zur Turbine. Leistung über den Umwälzstrom in Sekunden. Bei wenig Durchsatz und viel Leistung droht die Dichtewelleninstabilität. |
| **RBMK-1000** | 3200 MWth / 1000 MWe | Graphitmoderiert, Druckröhren. Bei kleiner Leistung wird der Dampfblasenkoeffizient positiv, und die Abschaltreserve ORM entscheidet, ob die Schnellabschaltung abschaltet — oder zündet. |

> Physikalisch nachgebildet, aber ein Spiel. Kein Ausbildungssimulator.

## Betrieb

Kein Home-Assistant-Add-on — der Ordner enthält bewusst keine `config.yaml`.
Betrieb über Docker (Dockge, Portainer, `docker compose`):

```bash
docker compose up -d
```

Danach `http://<server>:17779` öffnen. Der Dienst hört im Container fest auf
17779; willst du einen anderen Port, ändere nur die linke Seite der
Portzuordnung in der `docker-compose.yml`.

Unter `./data` landen Spielstände und Bestenliste. Es gibt keine Anmeldung und
keine personenbezogenen Daten — der Spieler wird über ein zufälliges Token im
Cookie wiedererkannt.

## Szenarien

Neben dem freien Spiel gibt es Schichten mit Auftrag: eine Bedarfskurve, die du
einhalten sollst, geplante Störungen und eine Wertung am Ende. Gewertet werden
gelieferte Energie, Abweichung vom Bedarf, unquittierte Alarmsekunden,
Grenzwertüberschreitungen nach Schwere, Schnellabschaltungen und
Brennstoffschaden.

| Szenario | Typ | Dauer |
|---|---|---|
| Lastfolge über vier Stunden | DWR | 240 min |
| Turbinenschnellschluss | DWR | 60 min |
| Lastfolge über den Umwälzstrom | SWR | 180 min |
| Frischdampf-Absperrung | SWR | 45 min |
| Nachtschicht | RBMK | 180 min |

Ein Szenario ist eine Datendatei unter `static/data/scenarios/`. Störungs-
zeitpunkte dürfen `"rand(6000,8400)"` sein und werden über den Startwert des
Szenarios aufgelöst — derselbe Startwert ergibt dieselbe Schicht.

## Schnittstelle

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/health` | Healthcheck |
| GET | `/api/meta` | Version und Szenarienliste |
| GET/PUT/DELETE | `/api/saves[/<slot>]` | Spielstände |
| GET/POST | `/api/highscores` | Bestenliste |

Der Server rechnet den Punktestand aus den gemeldeten Kennzahlen **selbst** —
ein mitgeschicktes `score`-Feld wird nicht gelesen. Die Kennzahlen werden auf
Plausibilität geprüft (mehr Energie, als die Anlage in der Zeit liefern kann,
längere Schicht als das Szenario dauert, negative Abweichungen). Der Spielstand
selbst ist für den Server undurchsichtig: er speichert ihn und gibt ihn zurück,
ohne hineinzusehen — geprüft wird er beim Laden im Browser.

Ehrliche Einordnung: solange die Simulation im Browser läuft, sind Bestenlisten
nicht fälschungssicher. Die Prüfung verschiebt die Angriffsfläche von „eine
beliebige Zahl" auf „ein Satz physikalisch begrenzter Größen". Der saubere Weg
wäre Replay-Verifikation; der gesäte Zufall und die DOM-freien `sim/`-Module
halten diese Tür offen.

## Bedienung

- **Zeitraffer** 1× / 4× / 16× / 60×. Der Rechenschritt bleibt dabei konstant,
  der Zeitraffer verändert die Genauigkeit also nicht. Bei einer Schnell-
  abschaltung schaltet das Spiel selbst auf 1× zurück.
- **SCRAM** braucht zwei Tipper: der erste scharf, der zweite löst aus.
- **Hochformat** zeigt die Panels als Reiter, breite Bildschirme als Raster mit
  dem Fließbild in der Mitte.
- **Sprache** DE/EN über den Startbildschirm.

## Entwicklung

```bash
python3 dev_run.py          # http://127.0.0.1:17779, Daten in dev_data/
node --test tests/          # Physik, Spielschicht, Determinismus
python3 -m pytest tests/    # Schnittstelle, Wertung, Struktur, Sprachdateien
```

Die gesamte Simulation läuft im Browser in reinen ES-Modulen — kein npm, kein
Bundler, kein Framework. Die Module unter `static/js/sim/` haben bewusst keinen
DOM-Bezug: dadurch sind sie unter `node --test` direkt importierbar und können
später ohne Umbau in einen Web Worker wandern.

Aufbau in Kürze:

```
app.py              Flask: Seite, /health, Sprache, versionierte Statics, API
static/js/sim/      Physik (Punktkinetik, Rückkopplungen, Xenon, Thermohydraulik)
static/js/plants/   je Reaktortyp ein Datenobjekt plus kleines Hook-Modul
static/js/game/     Szenarien, Störungen, Wertung
static/js/ui/       Instrumente, Trends, Fließbild, Meldetafel
```

Version und Build: die Datei `VERSION` ist die einzige Versionsquelle und
zugleich der Auslöser des GitHub-Workflows, der das Image nach GHCR baut.

## Lizenz

MIT — siehe [LICENSE.md](LICENSE.md).
