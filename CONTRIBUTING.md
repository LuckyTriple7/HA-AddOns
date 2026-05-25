# Beitragen zu HA-AddOns

Vielen Dank, dass du zu diesem Projekt beitragen möchtest! Dieses Dokument erklärt, wie du am besten vorgehst.

## Inhaltsverzeichnis

- [Verhaltenskodex](#verhaltenskodex)
- [Wie kann ich beitragen?](#wie-kann-ich-beitragen)
- [Fehler melden](#fehler-melden)
- [Feature-Vorschläge](#feature-vorschläge)
- [Pull Requests](#pull-requests)
- [Entwicklungsumgebung einrichten](#entwicklungsumgebung-einrichten)
- [Code-Stil](#code-stil)
- [Commit-Messages](#commit-messages)
- [Versionierung](#versionierung)

---

## Verhaltenskodex

Dieses Projekt folgt dem [Contributor Covenant](CODE_OF_CONDUCT.md). Durch deine Teilnahme verpflichtest du dich, diesen Kodex einzuhalten.

---

## Wie kann ich beitragen?

Es gibt viele Möglichkeiten, zum Projekt beizutragen — nicht nur durch Code:

- 🐛 **Fehler melden** — hilf uns, Probleme zu finden und zu beheben
- 💡 **Features vorschlagen** — teile deine Ideen und Verbesserungsvorschläge
- 📖 **Dokumentation verbessern** — korrigiere Tippfehler, ergänze fehlende Informationen
- 🧪 **Testen** — teste neue Versionen und gib Feedback
- ⭐ **Stern geben** — zeige deine Unterstützung mit einem GitHub-Stern

---

## Fehler melden

Bevor du ein neues Issue erstellst, bitte zuerst prüfen ob das Problem bereits gemeldet wurde.

**Ein gutes Bug-Report enthält:**

- Add-on Name und Version (z.B. `MariaDB 2 v0.1.2`)
- Home Assistant Version und Betriebssystem (z.B. `HA OS 14.2`)
- Eine klare Beschreibung des Problems
- Schritte zur Reproduktion des Fehlers
- Erwartetes vs. tatsächliches Verhalten
- Relevante LOG-Ausgaben aus dem Add-on (HA → Add-on → LOG-Tab)
- Screenshots bei UI-Problemen

**LOG-Ausgaben findest du unter:**
`Home Assistant → Einstellungen → Add-ons → [Add-on Name] → LOG`

---

## Feature-Vorschläge

Neue Feature-Ideen sind willkommen! Bitte öffne ein [Issue](https://github.com/LuckyTriple7/HA-AddOns/issues) mit:

- Einer klaren Beschreibung des gewünschten Features
- Dem Anwendungsfall — warum wäre das Feature nützlich?
- Möglichen Alternativen, die du bereits in Betracht gezogen hast
- Ob du bereit bist, das Feature selbst zu implementieren

---

## Pull Requests

### Vorbereitung

1. **Fork** das Repository auf GitHub
2. **Klone** deinen Fork lokal:
   ```bash
   git clone https://github.com/DEIN-USERNAME/HA-AddOns.git
   cd HA-AddOns
   ```
3. Erstelle einen neuen **Branch** für deine Änderungen:
   ```bash
   git checkout -b feature/mein-feature
   # oder
   git checkout -b fix/mein-bugfix
   ```

### Änderungen vornehmen

4. Nimm deine Änderungen vor
5. Teste die Änderungen gründlich in einer echten Home Assistant Umgebung
6. Aktualisiere die **Dokumentation** falls nötig (README.md)
7. Aktualisiere das **CHANGELOG.md** des betroffenen Add-ons
8. Erhöhe die **Versionsnummer** in `config.yaml` (siehe [Versionierung](#versionierung))

### Pull Request einreichen

9. **Committe** deine Änderungen:
   ```bash
   git add .
   git commit -m "Add: kurze Beschreibung der Änderung"
   ```
10. **Push** deinen Branch:
    ```bash
    git push origin feature/mein-feature
    ```
11. Öffne einen **Pull Request** gegen den `main`-Branch
12. Fülle die PR-Vorlage vollständig aus
13. Verlinke relevante Issues mit `Fixes #123` oder `Closes #123`

---

## Entwicklungsumgebung einrichten

### Voraussetzungen

- Home Assistant (OS, Container oder Supervised)
- Docker (für lokale Image-Tests)
- Git

### Lokales Testen

Add-ons können über einen lokalen Add-on Store getestet werden:

1. In HA: **Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**
2. Füge deine lokale Repository-URL hinzu (z.B. über GitHub)
3. Nach Änderungen: Add-on im HA neu installieren

### Docker-Image lokal bauen

```bash
cd mariadb2  # oder anderes Add-on Verzeichnis
docker build -t test-addon .
docker run --rm test-addon
```

---

## Code-Stil

### Shell-Scripts (`run.sh`, `*.sh`)

- Immer `#!/bin/bash` und `set -e` am Anfang
- Variablen in GROSSBUCHSTABEN für Konfigurationswerte
- LOG-Format: `echo "[INFO] Nachricht"` / `echo "[ERROR] Nachricht"`
- Keine hardcodierten Werte — Konfiguration ausschließlich über `/data/options.json`
- Kommentare nur wo wirklich nötig (nicht-offensichtliche Logik)

### Dockerfile

- Basis-Image: `alpine:3.21` (leichtgewichtig)
- Pakete in einer einzigen `RUN`-Anweisung installieren
- Keine unnötigen Pakete

### config.yaml

- Versionsnummer im Format `"MAJOR.MINOR.PATCH"`
- Alle Optionen mit sinnvollen Standardwerten
- Schema vollständig und korrekt definiert

---

## Commit-Messages

Commit-Messages sollten klar und auf Englisch oder Deutsch sein:

```
Add: neue Funktionalität
Fix: Fehlerbehebung
Update: Änderung an bestehender Funktionalität
Remove: Entfernen von Code/Dateien
Docs: nur Dokumentationsänderungen
```

**Beispiele:**
```
MariaDB 2 v0.1.2: Option disable_foreign_key_checks
Fix: MariaDB hörte nicht auf TCP Port 3306
Docs: Migration Guide aktualisiert
```

---

## Versionierung

Dieses Projekt folgt [Semantic Versioning](https://semver.org/):

| Version | Wann |
|---------|------|
| `PATCH` (0.0.x) | Bugfixes, kleine Verbesserungen |
| `MINOR` (0.x.0) | Neue Features, rückwärtskompatibel |
| `MAJOR` (x.0.0) | Breaking Changes, stabile Releases |

**Regel:** Die letzte Stelle wird erhöht, solange kein expliziter Grund für Minor/Major-Bump vorliegt.

---

---

# Contributing to HA-AddOns (English)

Thank you for your interest in contributing to this project! This document explains how to best proceed.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How can I contribute?](#how-can-i-contribute)
- [Reporting bugs](#reporting-bugs)
- [Feature requests](#feature-requests)
- [Pull requests](#pull-requests-1)
- [Setting up the development environment](#setting-up-the-development-environment)
- [Code style](#code-style)
- [Commit messages](#commit-messages-1)
- [Versioning](#versioning)

---

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

---

## How can I contribute?

There are many ways to contribute — not just through code:

- 🐛 **Report bugs** — help us find and fix issues
- 💡 **Suggest features** — share your ideas and improvement suggestions
- 📖 **Improve documentation** — fix typos, add missing information
- 🧪 **Test** — test new versions and give feedback
- ⭐ **Star the repo** — show your support with a GitHub star

---

## Reporting bugs

Before creating a new issue, please check if the problem has already been reported.

**A good bug report includes:**

- Add-on name and version (e.g. `MariaDB 2 v0.1.2`)
- Home Assistant version and OS (e.g. `HA OS 14.2`)
- A clear description of the problem
- Steps to reproduce the issue
- Expected vs. actual behavior
- Relevant log output from the add-on (HA → Add-on → Log tab)
- Screenshots for UI issues

**Log output can be found at:**
`Home Assistant → Settings → Add-ons → [Add-on Name] → Log`

---

## Feature requests

New feature ideas are welcome! Please open an [issue](https://github.com/LuckyTriple7/HA-AddOns/issues) with:

- A clear description of the desired feature
- The use case — why would this feature be useful?
- Possible alternatives you have already considered
- Whether you are willing to implement the feature yourself

---

## Pull Requests

### Preparation

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/HA-AddOns.git
   cd HA-AddOns
   ```
3. Create a new **branch** for your changes:
   ```bash
   git checkout -b feature/my-feature
   # or
   git checkout -b fix/my-bugfix
   ```

### Making changes

4. Make your changes
5. Test thoroughly in a real Home Assistant environment
6. Update **documentation** if necessary (README.md)
7. Update the **CHANGELOG.md** of the affected add-on
8. Bump the **version** in `config.yaml` (see [Versioning](#versioning))

### Submitting the pull request

9. **Commit** your changes:
   ```bash
   git add .
   git commit -m "Add: short description of the change"
   ```
10. **Push** your branch:
    ```bash
    git push origin feature/my-feature
    ```
11. Open a **pull request** against the `main` branch
12. Fill out the PR template completely
13. Link relevant issues with `Fixes #123` or `Closes #123`

---

## Setting up the development environment

### Prerequisites

- Home Assistant (OS, Container or Supervised)
- Docker (for local image testing)
- Git

### Local testing

Add-ons can be tested via a local add-on store:

1. In HA: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Add your local repository URL (e.g. via GitHub)
3. After changes: reinstall the add-on in HA

### Building Docker image locally

```bash
cd mariadb2  # or other add-on directory
docker build -t test-addon .
docker run --rm test-addon
```

---

## Code style

### Shell scripts (`run.sh`, `*.sh`)

- Always start with `#!/bin/bash` and `set -e`
- Variables in UPPERCASE for configuration values
- Log format: `echo "[INFO] message"` / `echo "[ERROR] message"`
- No hardcoded values — configuration exclusively via `/data/options.json`
- Comments only where truly necessary (non-obvious logic)

### Dockerfile

- Base image: `alpine:3.21` (lightweight)
- Install packages in a single `RUN` instruction
- No unnecessary packages

### config.yaml

- Version number in format `"MAJOR.MINOR.PATCH"`
- All options with sensible defaults
- Schema fully and correctly defined

---

## Commit messages

Commit messages should be clear, in English or German:

```
Add: new functionality
Fix: bug fix
Update: change to existing functionality
Remove: removal of code/files
Docs: documentation changes only
```

---

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

| Version | When |
|---------|------|
| `PATCH` (0.0.x) | Bug fixes, minor improvements |
| `MINOR` (0.x.0) | New features, backwards compatible |
| `MAJOR` (x.0.0) | Breaking changes, stable releases |
