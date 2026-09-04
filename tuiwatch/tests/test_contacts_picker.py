"""Der E-Mail-Dialog muss die Nextcloud-Kontakte als eigene Liste zeigen.

Anlass: mit `<datalist>` war das Adressbuch in Firefox praktisch unsichtbar —
Firefox zeigt dort nur den `value` (die Adresse), nie den Namen aus dem
Option-Text, und blendet die Vorschlaege ganz aus, sobald im Feld schon ein
Standard-Empfaenger steht. Dazu legen Passwortmanager (Bitwarden) ihr Overlay
ueber das Feld. Diese Tests halten den Umbau fest; die Darstellung selbst
laesst sich statisch nicht pruefen.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
# Kommentare raus: sie erwaehnen `<datalist>` als Begruendung des Umbaus
HTML_CODE = re.sub(r"<!--.*?-->", "", HTML, flags=re.S)
JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")


def test_kein_datalist_mehr():
    assert "<datalist" not in HTML_CODE
    assert 'list="nc-contacts"' not in HTML_CODE


def test_eingabefeld_meidet_passwortmanager_overlay():
    feld = re.search(r'<input[^>]*id="email-to"[^>]*>', HTML, re.S).group(0)
    assert 'autocomplete="off"' in feld
    assert 'data-bwignore="true"' in feld          # Bitwarden
    assert "data-1p-ignore" in feld                # 1Password
    assert 'data-lpignore="true"' in feld          # LastPass


def test_liste_und_bedienelemente_vorhanden():
    for marker in ('id="nc-box"', 'id="nc-list"', 'id="nc-toggle"',
                   'onclick="ncToggle()"', 'onclick="ncReload()"',
                   'oninput="ncFilter()"', 'onkeydown="ncKey(event)"'):
        assert marker in HTML, marker


def test_js_funktionen_definiert():
    for fn in ("ncLoad", "ncReload", "ncToggle", "ncFilter", "ncRender", "ncPick", "ncKey"):
        assert re.search(r"function %s\s*\(" % fn, JS), fn


def test_auswahl_per_delegation_und_index():
    """Adresse nie als Text im onclick (bricht bei Anfuehrungszeichen im Namen),
    sondern data-nc mit dem Index plus ein delegierter Zuhoerer."""
    assert 'data-nc="${i}"' in JS
    assert "closest('#nc-list .nc-row')" in JS
    assert "onclick=\"ncPick(" not in JS and "onclick='ncPick(" not in JS


def test_filter_prueft_name_und_adresse():
    block = JS[JS.index("function ncFilter"):JS.index("function ncRender")]
    assert "k.name" in block and "k.email" in block


def test_leeres_adressbuch_bleibt_sichtbar_wenn_konfiguriert():
    """Konfiguriert, aber nichts geladen: Block bleibt stehen und sagt es —
    sonst sieht ein fehlgeschlagener Abruf aus wie 'kein Adressbuch'."""
    block = JS[JS.index("async function ncLoad"):JS.index("async function ncReload")]
    assert "box.hidden = !ncConfigured" in block


def test_enter_waehlt_markierten_kontakt_sonst_senden():
    block = JS[JS.index("function ncKey"):]
    block = block[:block.index("document.addEventListener")]
    assert "ncOpen && ncSel >= 0" in block and "submitEmail()" in block
