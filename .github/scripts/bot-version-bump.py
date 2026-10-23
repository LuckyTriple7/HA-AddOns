#!/usr/bin/env python3
"""Hebt die Version der Add-ons an, die ein Bot-PR (Dependabot, Renovate) geändert hat.

Ohne neue Version in config.yaml baut der Build-Workflow kein Image, und Home
Assistant bietet kein Update an. Bot-PRs ändern aber nur requirements.txt,
package.json oder das Dockerfile.

Aufruf: geänderte Pfade auf stdin, PR-Titel in der Umgebungsvariable PR_TITLE.
Ausgabe: die angehobenen Add-ons, eins pro Zeile, als "<slug> <alt> <neu>".

Regel (siehe Versionierung im Repo): an eine dreistellige Version wird .1
angehängt (1.0.25 -> 1.0.25.1), eine vierstellige zählt die vierte Stelle hoch
(1.0.25.1 -> 1.0.25.2).
"""
import datetime
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Stellen außerhalb von config.yaml, die die Version mitführen.
EXTRA_VERSION_PATTERNS = [
    ("*.py", r'^(APP_VERSION\s*=\s*")({old})(")'),
    ("Dockerfile", r'^(\s*io\.hass\.version=")({old})(")'),
]


def next_version(old: str) -> str:
    parts = old.split(".")
    if len(parts) >= 4:
        parts[3] = str(int(parts[3]) + 1)
        return ".".join(parts[:4])
    return old + ".1"


def changelog_line(title: str) -> str:
    title = re.sub(r"^[a-z]+(\([^)]*\))?!?:\s*", "", title.strip())
    title = re.sub(r"^⬆️\s*", "", title)
    m = re.search(r"bump (.+?) from (\S+) to (\S+?)(?: in /\S+)?$", title, re.I)
    if m:
        return f"Abhängigkeit aktualisiert: {m.group(1)} {m.group(2)} → {m.group(3)}"
    title = re.sub(r"^(bump|update)\s+", "", title, flags=re.I)
    title = re.sub(r"\s+in /\S+$", "", title)
    return f"Abhängigkeit aktualisiert: {title}"


def read(path: Path) -> tuple[str, str]:
    text = path.read_bytes().decode("utf-8")
    return text, ("\r\n" if "\r\n" in text else "\n")


def write(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def bump_config(slug: str) -> tuple[str, str] | None:
    cfg = ROOT / slug / "config.yaml"
    text, _ = read(cfg)
    m = re.search(r'^version:\s*"?([0-9][0-9.]*)"?\s*$', text, re.M)
    if not m:
        print(f"::warning::{slug}: keine Version in config.yaml gefunden", file=sys.stderr)
        return None
    old = m.group(1)
    new = next_version(old)
    text = text[: m.start()] + f'version: "{new}"' + text[m.end():]
    write(cfg, text)
    return old, new


def bump_extras(slug: str, old: str, new: str) -> None:
    for glob, pattern in EXTRA_VERSION_PATTERNS:
        regex = re.compile(pattern.format(old=re.escape(old)), re.M)
        for path in (ROOT / slug).rglob(glob):
            if any(p in path.parts for p in (".venv", "node_modules", "_pwtest")):
                continue
            text, _ = read(path)
            text2 = regex.sub(lambda m: m.group(1) + new + m.group(3), text)
            if text2 != text:
                write(path, text2)


def add_changelog(slug: str, version: str, line: str) -> None:
    path = ROOT / slug / "CHANGELOG.md"
    if not path.exists():
        return
    text, nl = read(path)
    lines = text.split(nl)
    idx = next((i for i, l in enumerate(lines) if l.startswith("## ")), None)
    # Stil des bisher obersten Eintrags übernehmen: Leerzeile nach der Überschrift?
    blank = idx is not None and idx + 1 < len(lines) and lines[idx + 1].strip() == ""
    today = datetime.date.today().isoformat()
    top = lines[idx] if idx is not None else "## [x] - "
    if not top.startswith("## ["):
        heading = f"## {version}"  # Stil "## 1.2.3" ohne Klammern und Datum
    elif " — " in top:
        heading = f"## [{version}] — {today}"
    else:
        heading = f"## [{version}] - {today}"
    entry = [heading]
    if blank:
        entry.append("")
    entry += [f"- {line}", ""]
    if idx is None:
        lines += [""] + entry
    else:
        lines[idx:idx] = entry
    write(path, nl.join(lines))


def main() -> int:
    title = os.environ.get("PR_TITLE", "")
    files = [l.strip() for l in sys.stdin if l.strip()]
    touched: dict[str, set[str]] = {}
    for f in files:
        parts = f.split("/")
        if len(parts) > 1 and (ROOT / parts[0] / "config.yaml").exists():
            touched.setdefault(parts[0], set()).add("/".join(parts[1:]))

    for slug, paths in sorted(touched.items()):
        if "config.yaml" in paths:
            print(f"{slug}: config.yaml schon im PR geändert, kein Bump", file=sys.stderr)
            continue
        res = bump_config(slug)
        if not res:
            continue
        old, new = res
        bump_extras(slug, old, new)
        add_changelog(slug, new, changelog_line(title))
        print(f"{slug} {old} {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
