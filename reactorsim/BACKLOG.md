# Backlog

Offene, bewusst zurückgestellte Punkte -- kein Anspruch auf Vollständigkeit,
nur was beim Arbeiten aufgefallen ist und noch nicht dran war.

## RBMK-Startszenario mit Kaltstart

Der `cold`-Modus (engine.js `ctx.cold`, siehe `trim()` je Typ in
`static/js/plants/*.js`) lässt den Kern mit allen Stabbänken voll
eingefahren spürbar unterkritisch stehen, statt ihn auf Kritikalität
einzuschwingen -- Startbildschirm-Häkchen "Kalt starten". Läuft bisher nur
im freien Spiel: `boot()` in `static/js/main.js` erzwingt
`isColdStart = false`, sobald ein Szenario oder ein Spielstand im Spiel ist
(beide bringen eigene/gespeicherte Startwerte mit, die der Kaltstart nur
kurz überschreiben würde).

Ein echtes Szenario ("Nachtschicht-Anfahren", Gefahr durch den positiven
Void-Koeffizienten bei niedriger Leistung -- passend zum RBMK) bräuchte
eine von zwei Routen:

1. Die Szenario-Definition (`static/data/scenarios/*.json`) bekommt ein
   `cold: true`-Feld, das `boot()`/`Session` bis zu `createEngine()`
   durchreicht. Sauberer Weg, nutzt die vorhandene `trim()`-Logik direkt.
2. `start_overrides` müsste von Hand Stäbe, Bor/Referenzwerte auf den
   Kaltstart-Zustand ziehen. Fragiler, weil es `trim()`s ganze Rechnung
   (Temperaturen, Blasenanteil-Referenz beim SWR) nachbauen müsste.

Variante 1 empfohlen.

## Zwei bekannte Windows-Testartefakte

Beide real nachgeprüft als reine Windows-Dev-Umgebungslücke, nicht als
echter Bug -- unter Linux (Docker-Build, CI) laufen sie durch:

- `tests/test_auth.py::test_generated_password_when_none_configured` prüft
  `chmod 600` auf die generierte `auth.json`. NTFS kennt keine POSIX-Rechte,
  `os.stat(...).st_mode` liefert unter Windows immer `666`. Fix: Check unter
  `sys.platform == 'win32'` überspringen oder nur auf `os.name == 'posix'`
  ausführen.
- `tests/test_dockerfile.py::test_every_reachable_module_is_copied`
  vergleicht `os.path.relpath(...)` (liefert unter Windows Backslash-Pfade)
  gegen die Dockerfile-COPY-Ziele (Forward-Slash). Mit einem manuellen
  Forward-Slash-Vergleich bestätigt: `static/js/game/events.js` ist über
  `COPY static/ static/` tatsächlich abgedeckt, der Test scheitert nur am
  Trennzeichen. Fix: Pfade vor dem Vergleich normalisieren, z.B.
  `rel.replace(os.sep, '/')`.
