# Backlog

Offene, bewusst zurückgestellte Punkte -- kein Anspruch auf Vollständigkeit,
nur was beim Arbeiten aufgefallen ist und noch nicht dran war.

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
