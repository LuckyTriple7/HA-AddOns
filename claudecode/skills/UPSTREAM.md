# Herkunft der gebündelten Skills

Diese Skills und die Agents in `../agents/` sind unverändert aus dem Upstream-Projekt kopiert
(vendored, weil der Docker-Build-Context nur das Add-on-Verzeichnis umfasst).

| | |
|---|---|
| Quelle | https://github.com/JuliusBrussee/caveman |
| Stand | Tag `v1.10.0` (2026-08-03) |
| Lizenz | MIT, siehe `LICENSE` |

## Aktualisieren

```bash
curl -fsSL https://github.com/JuliusBrussee/caveman/archive/refs/tags/<TAG>.tar.gz | tar -xz
cp -a caveman-<TAG>/skills/. claudecode/skills/
cp -a caveman-<TAG>/agents/. claudecode/agents/
```

Danach diese Datei auf den neuen Tag setzen, `LICENSE` mitziehen und die Add-on-Version bumpen.

## Bewusst nicht übernommen

- `src/hooks/` — die Hooks müssten in `settings.json` verdrahtet werden. Ohne sie liefert
  `/caveman-stats` keine Zahlen (die Ausgabe kommt beim Upstream aus dem Hook, nicht vom Modell).
- `commands/` — die Slash-Befehle richten sich an andere Harnesses (Codex, Gemini). In Claude Code
  sind die Skills ohnehin direkt als `/caveman`, `/caveman-review` usw. aufrufbar.
