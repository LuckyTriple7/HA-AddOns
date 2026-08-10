"""Guard: HTML-Attribute in templates/*.html müssen mit geraden Anführungszeichen
(`"`) gequotet sein, nicht mit typografischen (`” “ „ ‟`).

Hintergrund (v0.89.4, live): beim Einfügen des STR-Flugplan-Blocks in
index.html wandelte ein Editor/Autocorrect die Attribut-Quotes von
`id="strf-body"` zu `id="strf-body"` (typografisch) um. Browser parsen das
nicht als Attribut-Grenze — `getElementById()` fand die Elemente nicht mehr,
app.js crashte beim Start (`Cannot read properties of null`), SVG-Icons
rendern kaputt (`viewBox` bricht). Die Seite war komplett zerschossen, lokal
wie live, kein Python-Test hatte index.html je angefasst. Dieser Test schließt
genau diese Lücke — ohne Browser, nur Regex, läuft in <1s.

Deutscher Fließtext mit echten typografischen Anführungszeichen (z. B.
`title="… zu „Meine Reisen“"`) bleibt erlaubt — nur die Zeichen direkt nach
einem `=` (also an der Attribut-Delimiter-Position) sind verboten.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = sorted((ROOT / "templates").glob("*.html"))

# Attribut-Wert beginnt direkt nach '=' mit einem typografischen Anführungszeichen
# statt einem geraden " oder '.
_SMART_QUOTE_DELIMITER = re.compile(r'=[“”„‟]')


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_no_smart_quote_attribute_delimiters(path):
    text = path.read_text(encoding="utf-8")
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _SMART_QUOTE_DELIMITER.finditer(line):
            hits.append(f"  Zeile {lineno}, Spalte {m.start() + 1}: …{line[max(0, m.start()-20):m.start()+20]}…")
    assert not hits, (
        f"{path.relative_to(ROOT)}: typografisches Anführungszeichen als Attribut-Delimiter "
        f"(bricht das HTML-Parsing):\n" + "\n".join(hits)
    )
