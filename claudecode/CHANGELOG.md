# Changelog

## [1.3.16] - 2026-08-16

### Changed
- **`.env.example` sagt jetzt, was zu tun ist.** Die Beispieldatei listete zwei auskommentierte Variablen (`GITHUB_PERSONAL_ACCESS_TOKEN` und `GITHUB_TOKEN`), ohne zu sagen, welche gebraucht wird — und die Raute davor blieb beim Ausfüllen leicht stehen, womit der Token stumm ignoriert wurde. Übrig bleibt jetzt nur `GITHUB_PERSONAL_ACCESS_TOKEN`, mit nummerierter Anleitung, ausdrücklichem Hinweis auf die zu löschende Raute und der Logzeile, an der sich der Erfolg ablesen lässt.
- **Der Befehl zum Anlegen des GitHub-MCP-Servers steht jetzt in der Doku** — in `.env.example` und in DOCS.md, DE wie EN. Ein Token allein legt keinen Server an, er füllt nur den Platzhalter in dessen Konfiguration; dieser Zwischenschritt fehlte bisher komplett und ohne ihn bleibt es bei den zwei Servern, die das Add-on selbst einrichtet.

### Fixed
- Enthält die `.env` keine einzige aktive Zeile, steht im Log nicht mehr nur `Loaded 0 variable(s)`, sondern eine Warnung samt Ursache: alle Zeilen sind Kommentare, die Raute vor dem Token muss weg.
- Ein UTF-8-BOM am Dateianfang wird abgeschnitten. Manche Windows-Editoren schreiben es ungefragt; der erste Schlüssel wäre sonst als ungültiger Variablenname verworfen worden.


## [1.3.15] - 2026-08-16

### Added
- **Eigene Umgebungsvariablen über `/homeassistant/.claudecode/.env`.** MCP-Server, die sich mit einem Token anmelden, lesen ihn aus der Umgebung des laufenden `claude`-Prozesses — das offizielle GitHub-Plugin etwa als `${GITHUB_PERSONAL_ACCESS_TOKEN}`. Bisher gab es keinen Weg, so einen Wert dorthin zu bekommen: Das Add-on hatte kein Feld dafür, und ein `export` im Terminal wirkt nur auf die eigene Shell, nie zurück auf den bereits gestarteten Elternprozess. Der Server meldete `Header values reference unset environment variables` und HTTP 400 (Issue #251).

  Neu legt das Add-on `.env.example` in `/homeassistant/.claudecode/` ab. Nach dem Umbenennen in `.env` wird jede `KEY=VALUE`-Zeile exportiert, bevor das Terminal startet — Claude Code und alle MCP-Server sehen die Werte damit ab dem nächsten Start. Anführungszeichen und ein vorangestelltes `export ` sind erlaubt, `#` leitet einen Kommentar ein, Windows-Zeilenenden (CRLF) werden abgeschnitten. Die Datei wird nicht ausgeführt, sondern Zeile für Zeile gelesen; `$(…)` darin bleibt Text. `PATH`, `HOME`, `IFS`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, `SUPERVISOR_TOKEN`, `HA_TOKEN` und `HA_URL` werden ignoriert, weil ein Überschreiben das Add-on lahmlegen würde. Ins Log gehen nur die Namen der geladenen Variablen, nie die Werte.

  Zu beachten: `/homeassistant` liegt in jedem HA-Backup, das Token damit auch — entsprechend knappe Rechte vergeben.

### Fixed
- **Git-Konfiguration und Zugangsdaten überleben jetzt einen Rebuild.** `~/.gitconfig` und `~/.git-credentials` liegen unter `/root` und damit im Container-Image, das bei jedem Update neu entsteht — Name, E-Mail und hinterlegte Zugangsdaten waren danach weg, `git push` scheiterte mit `could not read Username for 'https://github.com'`. Beides liegt jetzt in `/homeassistant/.claudecode/` (`gitconfig` und `.git-credentials`) und wird nach `/root` verlinkt; eine bereits vorhandene `~/.gitconfig` wird beim ersten Start übernommen, nicht überschrieben. Als Credential-Helper ist `store` mit Ziel in diesem Verzeichnis voreingestellt — aber nur, wenn keiner konfiguriert ist, ein eigener Helper bleibt unangetastet.

### Changed
- `protect_internal_config` sperrt zusätzlich das **Lesen** von `.claudecode/.env` und `.claudecode/.git-credentials`. Die Token stehen dort, wo Claude sie braucht, nämlich in der Umgebung; sie von der Platte zu lesen bringt nichts und kann sie in einer Sitzung sichtbar machen. Wie bisher gilt: Die Sperre greift bei den Datei-Werkzeugen, nicht bei Umwegen über die Shell, und wer sie nicht will, schaltet die Option ab.


## [1.3.14] - 2026-08-14

### Changed
- Rebuild für Claude Code 2.1.223


## [1.3.13] - 2026-08-14

### Fixed
- Der Schreibschutz aus 1.3.12 schrieb je Pfad zwei Regeln, `Edit(...)` und `Write(...)`. Bei Datei-Prüfungen greifen aber nur `Edit`-Regeln — die decken bereits alle datei-ändernden Werkzeuge ab, `Write` inklusive. Die `Write`-Regeln blieben wirkungslos und Claude Code meldete beim Start für jede von ihnen eine Warnung. Sie werden jetzt bei jedem Start entfernt, unabhängig davon, ob die Option an oder aus ist, damit auch bereits geschriebene `settings.json` sauber werden. Die Schutzwirkung ändert sich dadurch nicht.


## [1.3.12] - 2026-08-14

### Added
- Neue Option `protect_internal_config` (Standard: aktiviert). Trägt Sperrregeln in die `settings.json` ein, mit denen Claude Code Schreibzugriffe auf `.storage/`, `.cloud/`, `deps/`, `tts/` und die Recorder-Datenbank selbst ablehnt — anders als die Hinweise in der CLAUDE.md wirkt das unabhängig davon, was gerade im Kontext steht. Lesen bleibt erlaubt, Fehlersuche in diesen Verzeichnissen funktioniert also weiter.

  Wer dort bewusst eingreifen will, schaltet die Option ab; die Regeln werden bei jedem Start neu geschrieben, das Umschalten wirkt also sofort. Eigene Einträge unter `permissions.deny` bleiben in beide Richtungen erhalten, und eine von Hand kaputt editierte `settings.json` wird nicht angefasst, sondern nur als Warnung ins Log geschrieben.

  Nicht abgedeckt: Umwege über die Shell — `Bash`-Aufrufe wie `sed -i` auf denselben Pfaden erfasst die Sperre nicht.


## [1.3.11] - 2026-08-14

### Added
- **Schutzregeln in der CLAUDE.md.** Die Datei enthielt bisher nur Pfad-Mapping, Werkzeug-Hinweise und Log-Rezepte — keine einzige Regel darüber, was Claude *nicht* anfassen darf. Neu ist ein Abschnitt ganz oben mit einer Sperrliste für die internen HA-Verzeichnisse (`.storage/`, `.cloud/`, `deps/`, `tts/`, `home-assistant_v2.db`) samt der Erklärung, warum: dort liegt alles UI-Erstellte inklusive Entity- und Device-Registry, das Format ist nicht stabil, und eine von Hand geänderte Datei in `.storage/` kann Home Assistant am Starten hindern. Jede Zeile der Tabelle nennt das Werkzeug, das stattdessen zu benutzen ist. Dazu: `secrets.yaml` wird nie ausgegeben, Dateiänderungen erst nach ausdrücklicher Zustimmung, keine ungefragten Aufräumarbeiten, `ha core check` nach YAML-Änderungen und ein Hinweis auf Reload- vs. Neustart-Bedarf.
- **`CLAUDE.local.md` für eigene Anweisungen.** Die CLAUDE.md wird bei jedem Start überschrieben, eigene Ergänzungen waren also nach dem nächsten Neustart weg. Das Add-on legt jetzt `CLAUDE.local.md.example` in `/homeassistant/.claudecode/` ab; nach dem Umbenennen in `CLAUDE.local.md` wird die Datei in jeder Session mitgeladen und vom Add-on nie wieder angefasst — auch Updates schreiben nicht hinein. Bei Widersprüchen gewinnt die CLAUDE.md, die Schutzregeln bleiben unangetastet.

### Changed
- Kopieren aus dem Web-Terminal in die Browser-Zwischenablage funktioniert jetzt auch für Text, den Claude Code selbst kopiert. tmux verwarf die dafür nötigen OSC-52-Sequenzen bisher gleich zweifach: die DCS-Hülle, in die Claude Code sie packt, braucht `allow-passthrough on` (seit tmux 3.3 standardmäßig aus), und `set-clipboard` ignoriert in der Voreinstellung Clipboard-Schreibzugriffe aus inneren Anwendungen.


## [1.3.10] - 2026-08-14

### Fixed
- Tippen im Web-Terminal wirkte über langsame Verbindungen (Nabu Casa Cloud, Zugriff von unterwegs) ruckelig — Zeichen erschienen schubweise statt einzeln. Ursache: tmux' Paste-Erkennung (`assume-paste-time`, Standard 1 ms) hielt normal getippten Text für einen Einfügevorgang, weil die Tastendrücke über eine Verbindung mit hoher Latenz gebündelt ankommen, und reichte sie als Block weiter. Die Erkennung ist jetzt aus; echtes Einfügen funktioniert unverändert, weil der Browser dafür eigene Bracketed-Paste-Sequenzen schickt, die tmux durchreicht.
- Pfeiltasten und Alt-Kombinationen reagieren schneller: tmux wartete nach jedem ESC 500 ms auf eine mögliche Folgetaste (`escape-time`), jetzt 10 ms.

Hinweis: Der größere Teil der spürbaren Verzögerung liegt außerhalb des Add-ons. Ein Terminal hat kein lokales Echo, jeder Tastendruck läuft komplett zum Server und zurück, bevor das Zeichen erscheint. Über Nabu Casa Cloud geht dieser Weg zusätzlich über das Relay. Wer zuhause ist, tippt über die lokale HA-Adresse spürbar flüssiger.


## [1.3.9] - 2026-08-14

### Changed
- Das ttyd-Binary wird beim Image-Build jetzt per SHA256 geprüft, bevor es ausführbar wird. Bisher lud der Build die Datei aus dem Netz und setzte direkt das Execute-Bit — ein manipulierter Download wäre unbemerkt als Prozess mit vollem Host-Zugriff gestartet (`full_access`, `docker_api`). Der Download landet nun in `/tmp`, wird gegen die Prüfsumme aus dem Upstream-Release verglichen und erst danach nach `/usr/bin/ttyd` installiert. Die ttyd-Version steht als `ARG TTYD_VERSION` oben im Dockerfile; wer sie ändert, muss die Prüfsummen mitziehen.
- Unbekannte Ziel-Architekturen brechen den Build jetzt mit klarer Meldung ab, statt still das x86_64-Binary zu installieren.


## [1.3.8] - 2026-08-09

### Added
- `enable_caveman_skill` installiert jetzt alle sieben Skills des Upstream-Projekts statt nur `caveman`: `/caveman-commit`, `/caveman-review`, `/caveman-compress`, `/caveman-help`, `/caveman-stats` und `/cavecrew` kommen dazu, samt der drei `cavecrew-*`-Subagenten nach `/root/.claude/agents/`. Beim Ausschalten entfernt das Add-on genau diese Namen wieder — eigene Skills und Agents bleiben unberührt.

### Changed
- Gebündelte Caveman-Skills von Stand 2026-07-03 auf Upstream-Tag `v1.10.0` aktualisiert. Enthält u. a. den Fix "nie Verneinungen droppen" (weggekürzte `not`/`never` kehrten Anweisungen um), Härtung gegen Sprach-Drift und die Regel, dass dauerhafter Text (Doku, Issues, PR-Texte, Memory-Dateien) normal geschrieben wird. Herkunft und Update-Rezept stehen jetzt in `skills/UPSTREAM.md`, Upstream-`LICENSE` (MIT) liegt bei.
- Doku: eigener Abschnitt zu den Caveman-Skills (DE/EN) und Hinweis, dass Claude-Code-Updates nur noch dem npm-Tag `stable` folgen — Image-Build, stündlicher Check, `claude-update` und der GitHub-Workflow gleichermaßen.


## [1.3.7] - 2026-08-09

### Added
- Scrollen per Wischgeste und zwei Scroll-Knöpfe im Web-Terminal auf Touch-Geräten (Handy, Tablet, HA Companion App) — neue Option `mobile_scroll_ui` (Standard: aktiviert), Desktop-Browser bleiben unverändert. Hintergrund: xterm.js besitzt zwar eigenes Touch-Scrollen, steigt aber in `touchstart`/`touchmove` sofort aus, sobald eine Anwendung die Maus-Erfassung aktiviert (`coreMouseService.areMouseEventsActive`) — im Scroll-Modus `tmux` (`set -g mouse on`) also immer. Die neue Gestenerkennung greift in der Capture-Phase (kein doppeltes Scrollen) und reicht die Bewegung als synthetisches `wheel`-Event an xterm zurück, das damit je nach Modus das Browser-Scrollback scrollt oder Wheel-Reports an tmux schickt.

### Changed
- ttyd liefert die Client-Seite als eine einzige inline-`index.html` aus; sie wird jetzt beim Image-Build von einer Wegwerf-ttyd-Instanz abgeholt, um das Skript ergänzt und über `ttyd --index` ausgeliefert. Ändert ttyd sein Seiten-Layout, bricht der Build hörbar ab statt still eine kaputte Seite auszuliefern.


## [1.3.6] - 2026-08-06

### Changed
- Rebuild für Claude Code 2.1.220


## [1.3.5] - 2026-08-05

### Changed
- Rebuild für Claude Code 2.1.222


## [1.3.4] - 2026-08-05

### Changed
- Claude Code wird jetzt über den npm-Tag `stable` statt `latest`/`next` installiert und aktualisiert (Build, `auto_update_claude`, `claude update`, `claude-update`) — deutlich seltenere Updates, da `stable` erst nach zusätzlicher Prüfung durch Anthropic gesetzt wird. Installierte Version kann dadurch niedriger sein als vorher (aktuell 2.1.220 statt 2.1.222).
- Update-Check-Workflow (`check-claude-update.yml`) folgt ebenfalls `dist-tags.stable` statt `version` (= `latest`)


## [1.3.3] - 2026-08-05

### Security
- Der lebende Supervisor-Token wurde bei jedem `c`/`cc` und beim MCP-Setup als `HASS_TOKEN` in `settings.json` geschrieben — eine persistierte Kopie im HA-Config-Verzeichnis, die in jedem HA-Backup landet. Totes Feld: `hass-mcp` liest ausschließlich `HA_TOKEN` aus der Umgebung (bereits per `export` gesetzt), nie `HASS_TOKEN` aus der Config. `update_mcp_token()` entfernt, Write beim MCP-Setup entfernt, bereits persistierte Tokens werden beim ersten Start nach Update aus `settings.json` gelöscht.


## [1.3.2] - 2026-08-05

### Changed
- Rebuild für Claude Code 2.1.222


## [1.3.1] - 2026-08-04

### Changed
- Rebuild für Claude Code 2.1.221


## [1.3.0] - 2026-07-31

### Added
- Home-Context-Briefing: CLAUDE.md bekommt beim Start automatisch einen Abschnitt mit `hab overview` — Floors/Areas/Devices/Entities/Automationen etc. der laufenden HA-Installation, statt nur statischem Pfad-Mapping. Best-effort mit 10s-Timeout, falls HA Core noch startet.


## [1.2.1] - 2026-07-31

### Fixed
- `hab` war nicht ausführbar (`cannot execute: required file not found`) — das Binary ist glibc-dynamisch gelinkt, das Image basiert aber auf Alpine/musl; `gcompat` (musl→glibc-Kompat-Shim) ergänzt


## [1.2.0] - 2026-07-31

### Added
- `hab` CLI (Home Assistant Builder, github.com/balloob/home-assistant-build-cli) im Image — LLM-orientiertes Tool für Dashboard-CRUD, Area/Floor/Label-Management, Helper-Erstellung und Backup/Restore; authentifiziert automatisch über den Supervisor-Token
- CLAUDE.md-Kontext erweitert: verweist Claude auf `hab` für Admin-Operationen statt roher REST/WebSocket-Aufrufe

### Changed
- map: `addon_config` → `app_config` (Home-Assistant-Supervisor hat `addon_config` seit 2026.07 als Legacy-Name markiert, neuer Name ist `app_config`).

## [1.1.17] - 2026-07-26

### Changed
- Modellauswahl: `claude-opus-5` ersetzt `claude-opus-4-8`, `claude-sonnet-4-6` entfernt (Standard bleibt `claude-sonnet-5`)


## [1.1.16] - 2026-07-25

### Changed
- Rebuild für Claude Code 2.1.220


## [1.1.15] - 2026-07-23

### Changed
- Rebuild für Claude Code 2.1.218


## [1.1.14] - 2026-07-21

### Changed
- Rebuild für Claude Code 2.1.216


## [1.1.13] - 2026-07-19

### Fixed
- Ungültige `Glob(...)`/`Grep(...)` Permission-Regeln entfernt (Warnung "not matched by file permission checks"); `Read(...)` deckt alle Datei-Lese-Tools bereits ab
- Bestehende Installationen: alte fehlerhafte Regeln werden beim Start aus persistierter settings.json bereinigt


## [1.1.12] - 2026-07-19

### Changed
- Rebuild für Claude Code 2.1.215


## [1.1.11] - 2026-07-16

### Changed
- Rebuild für Claude Code 2.1.211


## [1.1.10] - 2026-07-15

### Changed
- Rebuild für Claude Code 2.1.210


## [1.1.9] - 2026-07-14

### Changed
- Rebuild für Claude Code 2.1.209


## [1.1.8] - 2026-07-11

### Changed
- Rebuild für Claude Code 2.1.207


## [1.1.7] - 2026-07-10

### Changed
- Rebuild für Claude Code 2.1.206


## [1.1.6] - 2026-07-09

### Changed
- Doku (DE/EN) und Options-Beschreibungen: Hinweis auf tmux-Copy-Mode-Falle im `tmux`-Scroll-Modus — erstes Scrollen öffnet Copy-Mode, Eingabe wirkt blockiert, `q` verlässt ihn

## [1.1.5] - 2026-07-09

### Fixed
- Web-Terminal-Scrollback: Die tmux-Statuszeile ließ tmux in einer Scroll-Region (DECSTBM) scrollen, wodurch gescrollte Zeilen nie das Browser-Scrollback erreichten — nur wenige Zeilen waren scrollbar (#162)

### Added
- Neue Option `tmux_scroll_mode` (`browser`|`tmux`, Standard: `browser`): `browser` = natives Browser-Scrollen, Touch (iPad) und normales Kopieren/Einfügen; `tmux` = Mausrad scrollt tmux-Historie, überlebt Browser-Reloads

## [1.1.4] - 2026-07-09

### Changed
- Rebuild für Claude Code 2.1.205


## [1.1.3] - 2026-07-08

### Changed
- Rebuild für Claude Code 2.1.204


## [1.1.2] - 2026-07-07

### Changed
- Rebuild für Claude Code 2.1.202


## [1.1.1] - 2026-07-04

### Changed
- Rebuild für Claude Code 2.1.201


## [1.1.0] - 2026-07-03

### Added
- Optionaler "Caveman"-Skill für Claude Code (`enable_caveman_skill`, Standard: deaktiviert) — knappe, technisch präzise Antworten ohne Füllwörter. Wird bei aktivierter Option bei jedem Start nach `/root/.claude/skills/caveman` synchronisiert.


## [1.0.47] - 2026-07-02

### Changed
- Rebuild für Claude Code 2.1.198


## [1.0.46] - 2026-07-01

### Added
- Neues Modell `claude-sonnet-5` zur Auswahl hinzugefügt und als Standard gesetzt


## [1.0.45] - 2026-07-01

### Changed
- Rebuild für Claude Code 2.1.197


## [1.0.44] - 2026-06-30

### Changed
- Rebuild für Claude Code 2.1.196


## [1.0.43] - 2026-06-27

### Changed
- Rebuild für Claude Code 2.1.195


## [1.0.42] - 2026-06-26

### Changed
- Rebuild für Claude Code 2.1.193


## [1.0.41] - 2026-06-25

Update Claude Code 2.1.191 (Add-on v1.0.40)


## [1.0.40] - 2026-06-25

### Changed
- Rebuild für Claude Code 2.1.191


## [1.0.39] - 2026-06-22

### Changed
- Rebuild für Claude Code 2.1.185


## [1.0.38] - 2026-06-20

### Changed
- Rebuild für Claude Code 2.1.183


## [1.0.37] - 2026-06-16

### Changed
- Rebuild für Claude Code 2.1.178


## [1.0.36] - 2026-06-13

### Changed
- Rebuild für Claude Code 2.1.177


## [1.0.35] - 2026-06-12

### Changed
- Rebuild für Claude Code 2.1.175


## [1.0.34] - 2026-06-11

### Changed
- Rebuild für Claude Code 2.1.173


## [1.0.33] - 2026-06-10

### Added
- Neues Modell `claude-fable-5` in der Modellauswahl (Anthropics leistungsstärkstes Modell, bis 22.06.2026 ohne Credit-Verbrauch auf bezahlten Plänen)

### Changed
- Doku: veraltete Modellbezeichnung `claude-opus-4-7` durch `claude-opus-4-8` ersetzt


## [1.0.32] - 2026-06-10

### Changed
- Rebuild für Claude Code 2.1.170


## [1.0.31] - 2026-06-09

### Changed
- Rebuild für Claude Code 2.1.169


## [1.0.30.1] - 2026-06-08

Bump python from 3.13-alpine3.21 to 3.14-alpine3.21


## [1.0.30] - 2026-06-07

### Changed
- Rebuild für Claude Code 2.1.168


## [1.0.29] - 2026-06-06

### Fixed
- `notify_on_update`, `auto_update_claude`, `enable_mcp`, `session_persistence`: jq `//`-Operator behandelte `false` als falsy und lieferte immer den Standardwert `true` — Option auf `false` hatte keinen Effekt

## [1.0.28] - 2026-06-06

### Changed
- Rebuild für Claude Code 2.1.167


## [1.0.27] - 2026-06-05

### Changed
- Rebuild für Claude Code 2.1.165


## [1.0.26] - 2026-06-05

### Changed
- Rebuild für Claude Code 2.1.163


## [1.0.25] - 2026-06-04
- Log-Ausgaben mit Datum und Uhrzeit: `[INFO] [YYYY-MM-DD HH:MM:SS] Nachricht`

## [1.0.24] - 2026-06-04

### Added
- Neue Option `notify_on_update` (Standard: aktiviert): HA-Persistent-Notification bei Update kann deaktiviert werden, ohne den Update-Check selbst abzuschalten.

## [1.0.23] - 2026-06-04

### Changed
- Rebuild für Claude Code 2.1.162

## [1.0.22] - 2026-06-03

### Changed
- Build: Image wird jetzt via GitHub Actions auf GHCR gebaut (ghcr.io/luckytriple7/claudecode)
- Build: Basis-Image auf python:3.13-alpine3.21 umgestellt, TARGETARCH statt BUILD_ARCH

## [1.0.21] - 2026-06-03

### Changed
- Rebuild für Claude Code 2.1.161

## [1.0.20] - 2026-06-02

### Changed
- Rebuild für Claude Code 2.1.160

## [1.0.19] - 2026-06-01

### Changed
- Rebuild für Claude Code 2.1.159

## [1.0.18] - 2026-05-30

### Changed
- Rebuild für Claude Code 2.1.158

## [1.0.17] - 2026-05-29

### Changed
- claude-opus-4-7 durch claude-opus-4-8 ersetzt

## [1.0.16] - 2026-05-29

### Changed
- Rebuild für Claude Code 2.1.156

## [1.0.15] - 2026-05-28

### Changed
- Rebuild für Claude Code 2.1.153

## [1.0.14] - 2026-05-27

### Changed
- Rebuild für Claude Code 2.1.152

## [1.0.13] - 2026-05-26

### Fixed
- `claude update` wird abgefangen und via npm ausgeführt (verhindert Fehler auf read-only Docker-Layern)

## [1.0.12] - 2026-05-25

### Changed
- Konfigurationsblock beim Start ins LOG: alle gesetzten Optionen auf einen Blick
- Update-Checker loggt Start und jeden stündlichen Check-Vorgang
- Memory-Backup loggt Start und jeden geplanten Backup-Lauf
- Alle Options-Reads zusammengeführt (saubere Struktur in run.sh)

## [1.0.11] - 2026-05-25

### Fixed
- Background-Update-Checker läuft jetzt nur noch wenn `auto_update_claude` aktiviert ist; war bisher immer aktiv und schickte HA-Benachrichtigungen auch bei deaktiviertem Auto-Update

## [1.0.10] - 2026-05-25

### Added
- Option `export_memory_interval`: zeitgesteuerter Memory-Export im Hintergrund (in Minuten). 0 = nur beim Start, Standard: 60 (stündlich). Nur aktiv wenn `export_memory` aktiviert ist.

## [1.0.9] - 2026-05-25

### Added
- Option `export_memory`: kopiert beim Add-on-Start Memory-Dateien, Memory-Index und eigene Befehle in den Add-on-Konfigurationsordner (`/config/memory/` und `/config/commands/`). Standard: deaktiviert.

## [1.0.8] - 2026-05-24

### Added
- Option `claude_autostart`: Claude Code startet automatisch beim Öffnen des Terminals; nach dem Beenden öffnet sich eine normale Bash-Shell

## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150

## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148

## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146

## [1.0.4] - 2026-05-20

### Changed
- Rebuild für Claude Code 2.1.145

## [1.0.3] - 2026-05-19

### Changed
- Rebuild für Claude Code 2.1.144

## [1.0.2] - 2026-05-15

### Changed
- Rebuild für Claude Code 2.1.143

## [1.0.1] - 2026-05-15

### Fixed
- Deprecated `build.yaml` entfernt — Build-Parameter direkt ins Dockerfile verschoben
- Deutsche Übersetzung hinzugefügt

## [1.0.0] - 2026-05-15

Forked from [apbb2/robsonfelix-hass-addons](https://github.com/apbb2/robsonfelix-hass-addons).

### Fixed
- Playwright MCP: socat forwards port 80 → Playwright Browser add-on port 9222,
  so the CDP endpoint is reliably reachable without manual workarounds.
