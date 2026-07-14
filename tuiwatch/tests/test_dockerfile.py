"""Guard: jede lokale Python-Datei, die von app.py (direkt oder über die
Route-Module) importiert wird, MUSS im Dockerfile per COPY ins Image gelangen.

Hintergrund (v0.48.1, live): die Modularisierung legte trips_routes.py &
backup_routes.py an, das Dockerfile kopierte aber nur eine feste Dateiliste —
das Add-on crashte beim Start mit ModuleNotFoundError, während alle Tests grün
waren (lokal liegen die Dateien ja nebeneinander). Dieser Test schließt genau
diese Lücke, ohne Docker zu brauchen."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _local_imports(py_file: Path, local_names: set) -> set:
    """Namen lokaler Module, die `py_file` importiert (import X / from X import)."""
    found = set()
    for line in py_file.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", line)
        if m and m.group(1) in local_names:
            found.add(m.group(1))
    return found


def test_dockerfile_copies_all_imported_local_modules():
    local_names = {p.stem for p in ROOT.glob("*.py")}
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    needed, queue, seen = set(), ["app"], set()
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        needed.add(name)
        for dep in _local_imports(ROOT / f"{name}.py", local_names):
            queue.append(dep)

    missing = [f"{n}.py" for n in sorted(needed) if f"{n}.py" not in dockerfile]
    assert not missing, (
        f"Im Dockerfile fehlen COPY-Einträge für: {', '.join(missing)} — "
        "das Add-on würde beim Start mit ModuleNotFoundError crashen."
    )
