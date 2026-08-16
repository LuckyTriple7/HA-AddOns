"""PDF-Import für Rechtstexte — aus einem PDF wird Markdown.

Reine Logik ohne Flask: die Route liegt in app.py, damit dieses Modul keine
Abhängigkeit zurück auf die App braucht.

Zwei Wege, in dieser Reihenfolge:

1. **Formularfeld.** Generatoren wie e-Recht24 legen den fertigen HTML-Quelltext
   als AcroForm-Feld ins PDF (Feldname z. B. `privacy_html_de`). Das ist die
   verlässliche Quelle: echte Überschriftenebenen, echte Listen, echte Links —
   nichts muss geraten werden. Sichtbar ist das Feld im PDF nicht.
2. **Seitenlayout.** Gibt es kein solches Feld, wird aus Schriftgröße und
   -schnitt geschlossen: die häufigste Größe ist Fließtext, alles Größere eine
   Überschrift, fett in Fließtextgröße wird `**fett**`. Das ist eine Schätzung
   und liefert je nach PDF unterschiedlich saubere Ergebnisse.

Beide Wege liefern Markdown, weil die Rechtstexte in MyPage als Markdown
gespeichert und mit `render_md` ausgegeben werden.
"""
import re
from collections import Counter
from html import unescape
from html.parser import HTMLParser

import pdfplumber
from pdfminer.pdftypes import resolve1

# Obergrenze für die erzeugte Textmenge. Die Rechtstexte werden in site.json mit
# 20 000 Zeichen begrenzt; etwas Luft nach oben, damit die Vorschau zeigt, dass
# es zu viel ist, statt vorher abzuschneiden.
MAX_CHARS = 60_000
MAX_PAGES = 200

# Nur diese Schemata werden als Link übernommen — `javascript:` und Konsorten
# haben in einem importierten Rechtstext nichts zu suchen.
_SAFE_SCHEMES = ('http://', 'https://', 'mailto:', 'tel:')

# Feldnamen der bekannten Generatoren: privacy_html_de, imprint_html_en, …
_FIELD_RE = re.compile(r'(privacy|datenschutz|imprint|impressum)[_-]?html[_-]?(de|en)?', re.I)
_KIND_MAP = {'privacy': 'privacy', 'datenschutz': 'privacy',
             'imprint': 'impressum', 'impressum': 'impressum'}

# Fußzeilen wie „3 / 14" oder „Seite 3 von 14"
_PAGENUM_RE = re.compile(r'^\s*(seite\s*)?\d+\s*(/|von|of)\s*\d+\s*$', re.I)
# Inhaltsverzeichnis-Zeilen mit Punktführung: „Kapitel .......... 3"
_DOTFILL_RE = re.compile(r'\.{6,}')


# ── PDF öffnen ───────────────────────────────────────────────────────────────

def extract(data: bytes) -> dict:
    """PDF-Bytes → `{markdown, source, kind, lang, pages, chars, warnings}`.

    `source` ist `'html'` (Formularfeld) oder `'layout'` (geschätzt) — die
    Oberfläche sagt das dazu, damit klar ist, wie sehr man dem Ergebnis trauen
    darf. Wirft ValueError, wenn sich gar kein Text gewinnen lässt.
    """
    warnings = []
    with pdfplumber.open(_as_stream(data)) as pdf:
        pages = len(pdf.pages)
        if pages > MAX_PAGES:
            raise ValueError('too_many_pages')
        html, field = _acroform_html(pdf)
        if html:
            md = html_to_markdown(html)
            source, kind, lang = 'html', *_kind_from_field(field)
        else:
            md = layout_to_markdown(pdf)
            source, kind, lang = 'layout', '', ''
            warnings.append('layout')

    md = md.strip()
    if not md:
        raise ValueError('no_text')
    if len(md) > MAX_CHARS:
        md = md[:MAX_CHARS].rstrip()
        warnings.append('truncated')
    return {'markdown': md, 'source': source, 'kind': kind, 'lang': lang,
            'pages': pages, 'chars': len(md), 'warnings': warnings}


def _as_stream(data: bytes):
    import io
    return io.BytesIO(data)


def _kind_from_field(field: str) -> tuple:
    """Aus `privacy_html_de` wird ('privacy', 'de') — für die Zielauswahl."""
    m = _FIELD_RE.search(field or '')
    if not m:
        return '', ''
    return _KIND_MAP.get(m.group(1).lower(), ''), (m.group(2) or '').lower()


def _acroform_html(pdf) -> tuple:
    """HTML-Quelltext aus einem Formularfeld holen — ('', '') wenn keins passt."""
    try:
        acro = resolve1(pdf.doc.catalog.get('AcroForm'))
        fields = resolve1(acro.get('Fields')) if acro else None
    except Exception:
        return '', ''
    best = ('', '')
    for ref in (fields or []):
        try:
            fo = resolve1(ref)
            name = _pdf_text(fo.get('T'))
            value = _pdf_text(resolve1(fo.get('V')))
        except Exception:
            continue
        if not value or '<' not in value:
            continue
        # Ein passend benanntes Feld schlägt jedes andere; sonst das längste.
        if _FIELD_RE.search(name or ''):
            return value, name
        if len(value) > len(best[0]):
            best = (value, name or '')
    return best


def _pdf_text(v) -> str:
    """PDF-Strings kommen als bytes, wahlweise UTF-16 mit BOM oder PDFDocEncoding."""
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    if isinstance(v, bytes):
        if v[:2] in (b'\xfe\xff', b'\xff\xfe'):
            return v.decode('utf-16', 'replace')
        try:
            return v.decode('utf-8')
        except UnicodeDecodeError:
            return v.decode('latin-1', 'replace')
    return str(v)


# ── Weg 1: HTML → Markdown ───────────────────────────────────────────────────

class _MdWriter(HTMLParser):
    """Übersetzt den kleinen Tag-Satz der Generatoren nach Markdown.

    Bewusst kein allgemeiner Konverter: erzeugt wird nur, was in Rechtstexten
    vorkommt (Überschriften, Absätze, Listen, Links, Fett/Kursiv). Alles andere
    fällt auf seinen Textinhalt zurück, statt als Rohtext im Ergebnis zu landen.
    """

    _HEAD = {'h1': '# ', 'h2': '## ', 'h3': '### ',
             'h4': '#### ', 'h5': '##### ', 'h6': '###### '}
    _SKIP = {'script', 'style', 'head', 'title', 'meta', 'link'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []          # fertige Blöcke
        self.buf = []          # laufender Block
        self.skip = 0
        self.list_stack = []   # 'ul' | ['ol', laufende Nummer]
        self.link = None
        self.pre_head = ''

    # -- Hilfen --
    def _flush(self, prefix=''):
        text = _tidy(''.join(self.buf))
        self.buf = []
        if text:
            self.out.append(prefix + text)

    def _push(self, s):
        if self.skip:
            return
        self.buf.append(s)

    # -- Ereignisse --
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self._SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        a = dict(attrs)
        if tag in self._HEAD:
            self._flush(self.pre_head)
            self.pre_head = self._HEAD[tag]
        elif tag == 'p':
            self._flush(self.pre_head)
            self.pre_head = ''
        elif tag == 'br':
            self._push('  \n')
        elif tag in ('ul', 'ol'):
            self._flush(self.pre_head)
            self.pre_head = ''
            self.list_stack.append([tag, 0])
        elif tag == 'li':
            self._flush(self.pre_head)
            self.pre_head = ''
            if self.list_stack:
                lst = self.list_stack[-1]
                lst[1] += 1
                indent = '  ' * (len(self.list_stack) - 1)
                self.pre_head = f'{indent}{lst[1]}. ' if lst[0] == 'ol' else f'{indent}- '
            else:
                self.pre_head = '- '
        elif tag in ('strong', 'b'):
            self._push('**')
        elif tag in ('em', 'i'):
            self._push('*')
        elif tag == 'a':
            href = (a.get('href') or '').strip()
            self.link = href if href.lower().startswith(_SAFE_SCHEMES) else None
            if self.link:
                self._push('[')
        elif tag == 'hr':
            self._flush(self.pre_head)
            self.pre_head = ''
            self.out.append('---')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self._SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in self._HEAD or tag in ('p', 'li'):
            self._flush(self.pre_head)
            self.pre_head = ''
        elif tag in ('ul', 'ol'):
            self._flush(self.pre_head)
            self.pre_head = ''
            if self.list_stack:
                self.list_stack.pop()
        elif tag in ('strong', 'b'):
            self._push('**')
        elif tag in ('em', 'i'):
            self._push('*')
        elif tag == 'a' and self.link:
            # Nackte Adressen nicht doppeln: aus [https://x](https://x) wird <https://x>
            label = ''.join(self.buf).rsplit('[', 1)[-1].strip()
            if label == self.link:
                self.buf[-len(self.buf):] = [''.join(self.buf).rsplit('[', 1)[0] + f'<{self.link}>']
            else:
                self._push(f']({self.link})')
            self.link = None

    def handle_data(self, data):
        self._push(data)

    def close_out(self) -> str:
        self.close()
        self._flush(self.pre_head)
        return '\n\n'.join(b for b in self.out if b)


def html_to_markdown(html: str) -> str:
    """HTML eines Rechtstext-Generators nach Markdown übersetzen."""
    p = _MdWriter()
    p.feed(html or '')
    return _dedupe_blank(p.close_out())


def _tidy(s: str) -> str:
    """Weiche Trennstriche und Mehrfach-Leerraum aus einem Block räumen."""
    s = unescape(s).replace('­', '').replace(' ', ' ')
    # Zeilenumbrüche innerhalb eines Absatzes sind Layout, keine Bedeutung, und
    # werden zu einem Leerzeichen. Ein <br> hat oben „zwei Leerzeichen + \n"
    # hinterlassen — das ist in Markdown der harte Umbruch und muss samt seiner
    # beiden Leerzeichen überleben, sonst ist es keiner mehr.
    s = re.sub(r'[ \t]*\n(?!\n)',
               lambda m: '  \n' if m.group(0).endswith('  \n') else ' ', s)
    s = re.sub(r'[ \t]{2,}(?!\n)', ' ', s)
    return s.strip()


def _dedupe_blank(s: str) -> str:
    return re.sub(r'\n{3,}', '\n\n', s).strip()


# ── Weg 2: Seitenlayout → Markdown ───────────────────────────────────────────

def layout_to_markdown(pdf) -> str:
    """Ohne Formularfeld: aus Schriftgröße und -schnitt auf Struktur schließen."""
    lines = []
    for page in pdf.pages:
        lines.extend(_page_lines(page))
    if not lines:
        return ''

    body = Counter(round(l['size']) for l in lines).most_common(1)[0][0]
    # Alles deutlich Größere ist eine Überschrift; die Rangfolge der Größen
    # bestimmt die Ebene (größte = ##, danach ###, …).
    bigger = sorted({round(l['size']) for l in lines if round(l['size']) > body}, reverse=True)
    level = {s: min(i + 2, 6) for i, s in enumerate(bigger)}

    out, para = [], []

    def flush():
        if para:
            out.append(' '.join(para))
            para.clear()

    for l in lines:
        text, size = l['text'], round(l['size'])
        if not text or _PAGENUM_RE.match(text):
            continue
        if size < body - 1:
            continue                     # Kopf- und Fußzeilen
        if size in level:
            flush()
            out.append('#' * level[size] + ' ' + text)
            continue
        m = re.match(r'^[•‣●▪\-–]\s+(.*)', text)
        if m:
            flush()
            out.append('- ' + m.group(1))
            continue
        if l['bold'] and len(text) < 90 and not text.endswith(('.', ':', ',', ';')):
            flush()
            out.append('**' + text + '**')
            continue
        if l['gap']:
            flush()
        para.append(text)
    flush()
    return _dedupe_blank('\n\n'.join(out))


def _page_lines(page) -> list:
    """Zeichen einer Seite zu Zeilen bündeln, mit Größe, Fettung und Abstand.

    `gap` markiert einen Absatzwechsel. Der Maßstab dafür ist der übliche
    Zeilenabstand dieser Seite, nicht die Schriftgröße: normaler Durchschuss
    ist bereits größer als die Schrift, sonst würde jede einzelne Zeile als
    eigener Absatz gelten.
    """
    rows = {}
    for c in page.chars:
        rows.setdefault(round(c['top'] / 2) * 2, []).append(c)
    tops = sorted(rows)
    steps = [b - a for a, b in zip(tops, tops[1:]) if b - a > 0]
    normal = sorted(steps)[len(steps) // 2] if steps else 0

    out, prev = [], None
    for top in tops:
        cs = sorted(rows[top], key=lambda c: c['x0'])
        text = ''.join(c['text'] for c in cs).strip()
        if not text or _DOTFILL_RE.search(text):
            continue                     # Inhaltsverzeichnis mit Punktführung
        size = Counter(round(c['size'], 1) for c in cs).most_common(1)[0][0]
        bold = sum(1 for c in cs if 'bold' in (c.get('fontname') or '').lower()) > len(cs) * 0.6
        gap = prev is not None and normal and (top - prev) > normal * 1.6
        out.append({'text': text, 'size': size, 'bold': bold, 'gap': gap})
        prev = top
    return out
