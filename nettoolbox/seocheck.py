"""On-page SEO inspection of a single URL.

Looks at exactly what the server delivers: the HTML as it arrives, plus
robots.txt and the sitemap it points at. Parsing runs on the standard
library's html.parser -- no BeautifulSoup, no lxml, nothing new in the
image for a feature that needs a tag soup walked once.

Deliberately *not* covered, because it cannot be done honestly from here:
Core Web Vitals (needs a real browser or Google's PageSpeed API with a key),
rankings and backlinks (paid services), and anything a JavaScript framework
only renders in the client -- what is judged is the delivered HTML. A page
that ships an empty <div id="root"> is reported as thin content, which is
exactly what a crawler without JavaScript sees too.
"""

import html.parser
import json
import re
import time
from urllib.parse import urljoin, urlparse

import httpcheck
from netcore import Context, ProbeError, http_get

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'

MAX_HTML_BYTES = 512 * 1024
MAX_ROBOTS_BYTES = 64 * 1024
MAX_SITEMAP_BYTES = 512 * 1024

# Google truncates around these widths; the numbers are pixel-based in
# reality, so these are the usual character rules of thumb, not a law.
TITLE_MIN, TITLE_MAX = 30, 60
DESC_MIN, DESC_MAX = 70, 160
THIN_CONTENT_WORDS = 300
SLOW_MS = 1500

_LOC_RE = re.compile(r'<loc>\s*([^<\s]+)\s*</loc>', re.I)
_WORD_RE = re.compile(r'[^\s]+')
_SKIP_TEXT_TAGS = frozenset(('script', 'style', 'noscript', 'template', 'svg'))


def _finding(level: str, code: str, **args) -> dict:
    return {'level': level, 'code': code, 'args': args}


def _worst(findings: list) -> str:
    for level in (FAIL, WARN):
        if any(f['level'] == level for f in findings):
            return level
    return OK


def _score(findings: list) -> int:
    """One headline number, same idea as the mail health score.

    Informational findings never cost anything -- they describe the page,
    they do not judge it.
    """
    score = 100
    for f in findings:
        if f['level'] == FAIL:
            score -= 15
        elif f['level'] == WARN:
            score -= 7
    return max(0, min(100, score))


class _Page(html.parser.HTMLParser):
    """Everything the checks below need, gathered in one pass."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ''
        self.metas = {}          # name/property (lower) -> content
        self.canonical = ''
        self.icon = ''
        self.hreflang = []       # [{'lang': ..., 'href': ...}]
        self.headings = []       # [(level, text)]
        self.images_total = 0
        self.images_no_alt = 0
        self.jsonld = []         # raw strings
        self.html_lang = ''
        self.charset = ''
        self.resources = []      # every src/href that fetches something
        self.text_parts = []
        self._stack = []
        self._grab = None        # 'title' | 'jsonld' | None

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _attr(attrs, name):
        for key, value in attrs:
            if key.lower() == name:
                return (value or '').strip()
        return ''

    # -- parser callbacks ---------------------------------------------------

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        self._stack.append(tag)
        if tag == 'html':
            self.html_lang = self._attr(attrs, 'lang')
        elif tag == 'title' and not self.title:
            self._grab = 'title'
        elif tag == 'meta':
            key = (self._attr(attrs, 'name') or self._attr(attrs, 'property')).lower()
            if key:
                self.metas.setdefault(key, self._attr(attrs, 'content'))
            if self._attr(attrs, 'charset'):
                self.charset = self._attr(attrs, 'charset')
            elif self._attr(attrs, 'http-equiv').lower() == 'content-type':
                m = re.search(r'charset=([\w-]+)', self._attr(attrs, 'content'), re.I)
                if m:
                    self.charset = m.group(1)
        elif tag == 'link':
            rel = self._attr(attrs, 'rel').lower()
            href = self._attr(attrs, 'href')
            if 'canonical' in rel and not self.canonical:
                self.canonical = href
            if 'icon' in rel and not self.icon:
                self.icon = href
            if 'alternate' in rel and self._attr(attrs, 'hreflang'):
                self.hreflang.append({'lang': self._attr(attrs, 'hreflang'),
                                      'href': href})
            if href and rel in ('stylesheet', 'preload'):
                self.resources.append(href)
        elif tag == 'img':
            self.images_total += 1
            # An empty alt="" is a deliberate "decorative" marker and correct;
            # a missing attribute is the actual defect.
            if not any(k.lower() == 'alt' for k, _v in attrs):
                self.images_no_alt += 1
            src = self._attr(attrs, 'src')
            if src:
                self.resources.append(src)
        elif tag in ('script', 'iframe', 'source', 'video', 'audio', 'embed'):
            src = self._attr(attrs, 'src')
            if src:
                self.resources.append(src)
            if tag == 'script' and self._attr(attrs, 'type').lower() == 'application/ld+json':
                self._grab = 'jsonld'
                self.jsonld.append('')
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.headings.append([int(tag[1]), ''])

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._stack and tag in self._stack:
            while self._stack:
                if self._stack.pop() == tag:
                    break
        if tag in ('title', 'script'):
            self._grab = None

    def handle_data(self, data):
        if self._grab == 'title':
            self.title += data
        elif self._grab == 'jsonld' and self.jsonld:
            self.jsonld[-1] += data
        current = self._stack[-1] if self._stack else ''
        if current in _SKIP_TEXT_TAGS:
            return
        if self.headings and current.startswith('h') and current[1:2].isdigit():
            self.headings[-1][1] += data
        self.text_parts.append(data)


def _fetch_text(ctx: Context, url: str, max_bytes: int, accept: str) -> dict:
    try:
        return http_get(ctx, url, max_bytes=max_bytes, accept=accept)
    except ProbeError:
        return {}


def _robots(ctx: Context, origin: str) -> dict:
    """robots.txt as far as it matters here: does it exist, does it block
    everything, and does it name a sitemap."""
    resp = _fetch_text(ctx, origin + '/robots.txt', MAX_ROBOTS_BYTES, 'text/plain,*/*')
    info = {'found': False, 'status': resp.get('status', 0), 'sitemaps': [],
            'disallow_all': False, 'lines': 0}
    if not resp or resp.get('status') != 200:
        return info
    body = resp.get('body', '')
    # A server answering 200 with an HTML error page is not a robots.txt.
    if '<html' in body[:400].lower():
        return info
    info['found'] = True
    info['lines'] = len(body.splitlines())
    agent_all = False
    for raw in body.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line or ':' not in line:
            continue
        field, _, value = line.partition(':')
        field, value = field.strip().lower(), value.strip()
        if field == 'user-agent':
            agent_all = value == '*'
        elif field == 'sitemap' and value:
            info['sitemaps'].append(value)
        elif field == 'disallow' and agent_all and value == '/':
            info['disallow_all'] = True
    return info


def _sitemap(ctx: Context, origin: str, from_robots: list) -> dict:
    """The first reachable sitemap, and how many URLs it lists.

    A sitemap index counts as found too -- its <loc> entries are the child
    sitemaps, which is still the answer to "is there one".
    """
    # Gzipped sitemaps are skipped: http_get hands back decoded text, so the
    # original bytes needed for gunzip are already gone by then -- and the
    # well-known default below answers the question anyway. The default is
    # always tried last, never crowded out by a long Sitemap: list in
    # robots.txt (heise.de names seven, six of them .gz).
    candidates = [u for u in from_robots if not u.lower().endswith('.gz')][:4]
    candidates.append(origin + '/sitemap.xml')
    seen = set()
    for url in [u for u in candidates if not (u in seen or seen.add(u))]:
        resp = _fetch_text(ctx, url, MAX_SITEMAP_BYTES, 'application/xml,text/xml,*/*')
        if not resp or resp.get('status') != 200:
            continue
        body = resp.get('body', '')
        if '<urlset' not in body.lower() and '<sitemapindex' not in body.lower():
            continue
        return {'found': True, 'url': url, 'urls': len(_LOC_RE.findall(body)),
                'index': '<sitemapindex' in body.lower(),
                'truncated': resp.get('bytes', 0) >= MAX_SITEMAP_BYTES}
    return {'found': False, 'url': '', 'urls': 0, 'index': False,
            'truncated': False}


def _jsonld_types(blocks: list) -> list:
    types = []
    for raw in blocks:
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            for entry in (item.get('@graph') if isinstance(item.get('@graph'), list)
                          else [item]):
                if isinstance(entry, dict):
                    value = entry.get('@type')
                    for name in (value if isinstance(value, list) else [value]):
                        if isinstance(name, str) and name not in types:
                            types.append(name)
    return types


def check_seo(ctx: Context, target: str) -> dict:
    start_url = httpcheck.normalise_url(target)
    chain = httpcheck.follow_redirects(ctx, start_url)
    final_url = chain[-1]['url']

    started = time.monotonic()
    resp = http_get(ctx, final_url, max_bytes=MAX_HTML_BYTES,
                    accept='text/html,application/xhtml+xml,*/*')
    ms = int((time.monotonic() - started) * 1000)
    headers = resp['headers']
    truncated = resp['bytes'] >= MAX_HTML_BYTES
    content_type = headers.get('content-type', '')

    findings = []
    parsed = urlparse(final_url)
    origin = f'{parsed.scheme}://{parsed.netloc}'

    if resp['status'] != 200:
        findings.append(_finding(FAIL, 'seo_bad_status', status=resp['status']))
    if 'html' not in content_type.lower():
        # Nothing below applies to a PDF or a JSON endpoint.
        raise ProbeError('not_html', content_type[:40] or '?')

    page = _Page()
    try:
        page.feed(resp['body'])
        page.close()
    except Exception:
        # A malformed document is normal on the web; whatever was parsed
        # before the parser gave up is still worth judging.
        pass

    title = ' '.join(page.title.split())
    description = ' '.join((page.metas.get('description') or '').split())
    robots_meta = (page.metas.get('robots') or '').lower()
    text = ' '.join(''.join(page.text_parts).split())
    words = len(_WORD_RE.findall(text))
    h1s = [h[1].strip() for h in page.headings if h[0] == 1]
    jsonld_types = _jsonld_types(page.jsonld)
    og = {k: v for k, v in page.metas.items() if k.startswith('og:')}
    twitter = {k: v for k, v in page.metas.items() if k.startswith('twitter:')}

    robots = _robots(ctx, origin)
    sitemap = _sitemap(ctx, origin, robots['sitemaps'])

    mixed = []
    if parsed.scheme == 'https':
        for ref in page.resources:
            absolute = urljoin(final_url, ref)
            if absolute.lower().startswith('http://') and absolute not in mixed:
                mixed.append(absolute)

    # ── Findings ─────────────────────────────────────────────────────────

    if 'noindex' in robots_meta:
        findings.append(_finding(FAIL, 'seo_noindex'))
    if 'nofollow' in robots_meta:
        findings.append(_finding(INFO, 'seo_nofollow'))

    if not title:
        findings.append(_finding(FAIL, 'seo_title_missing'))
    elif len(title) < TITLE_MIN:
        findings.append(_finding(WARN, 'seo_title_short', length=len(title)))
    elif len(title) > TITLE_MAX:
        findings.append(_finding(WARN, 'seo_title_long', length=len(title)))
    else:
        findings.append(_finding(OK, 'seo_title_ok', length=len(title)))

    if not description:
        findings.append(_finding(WARN, 'seo_desc_missing'))
    elif len(description) < DESC_MIN:
        findings.append(_finding(WARN, 'seo_desc_short', length=len(description)))
    elif len(description) > DESC_MAX:
        findings.append(_finding(WARN, 'seo_desc_long', length=len(description)))
    else:
        findings.append(_finding(OK, 'seo_desc_ok', length=len(description)))

    if not h1s:
        findings.append(_finding(FAIL, 'seo_h1_missing'))
    elif len(h1s) > 1:
        findings.append(_finding(WARN, 'seo_h1_multiple', count=len(h1s)))
    else:
        findings.append(_finding(OK, 'seo_h1_ok'))

    previous = 0
    for level, _text in page.headings:
        if previous and level > previous + 1:
            findings.append(_finding(WARN, 'seo_heading_skip',
                                     **{'from': previous, 'to': level}))
            break
        previous = level

    if not page.canonical:
        findings.append(_finding(INFO, 'seo_canonical_missing'))
    else:
        canonical_abs = urljoin(final_url, page.canonical)
        if canonical_abs.rstrip('/') != final_url.rstrip('/'):
            findings.append(_finding(INFO, 'seo_canonical_other',
                                     url=canonical_abs))
        else:
            findings.append(_finding(OK, 'seo_canonical_ok'))

    if not page.html_lang:
        findings.append(_finding(WARN, 'seo_lang_missing'))
    if not page.metas.get('viewport'):
        findings.append(_finding(WARN, 'seo_viewport_missing'))
    if not page.charset:
        findings.append(_finding(INFO, 'seo_charset_missing'))

    if page.images_no_alt:
        findings.append(_finding(WARN, 'seo_images_no_alt',
                                 count=page.images_no_alt,
                                 total=page.images_total))
    elif page.images_total:
        findings.append(_finding(OK, 'seo_images_alt_ok', total=page.images_total))

    if words < THIN_CONTENT_WORDS:
        findings.append(_finding(WARN, 'seo_thin_content', words=words))
    else:
        findings.append(_finding(OK, 'seo_words_ok', words=words))

    if og.get('og:title') and og.get('og:description') and og.get('og:image'):
        findings.append(_finding(OK, 'seo_og_ok'))
    elif og:
        findings.append(_finding(INFO, 'seo_og_partial', count=len(og)))
    else:
        findings.append(_finding(INFO, 'seo_og_missing'))

    if jsonld_types:
        findings.append(_finding(OK, 'seo_jsonld_ok',
                                 types=', '.join(jsonld_types[:6])))
    else:
        findings.append(_finding(INFO, 'seo_jsonld_missing'))

    if robots['disallow_all']:
        findings.append(_finding(FAIL, 'seo_robots_disallow_all'))
    elif robots['found']:
        findings.append(_finding(OK, 'seo_robots_ok'))
    else:
        findings.append(_finding(WARN, 'seo_robots_missing'))

    if sitemap['found']:
        findings.append(_finding(OK, 'seo_sitemap_ok', urls=sitemap['urls']))
    else:
        findings.append(_finding(WARN, 'seo_sitemap_missing'))

    if page.hreflang:
        findings.append(_finding(INFO, 'seo_hreflang', count=len(page.hreflang)))

    if mixed:
        findings.append(_finding(WARN, 'seo_mixed_content', count=len(mixed)))

    if parsed.scheme != 'https':
        findings.append(_finding(WARN, 'seo_not_https'))
    if not headers.get('content-encoding'):
        findings.append(_finding(INFO, 'seo_no_compression'))
    if ms > SLOW_MS:
        findings.append(_finding(WARN, 'seo_slow', ms=ms))
    if not page.icon:
        findings.append(_finding(INFO, 'seo_favicon_missing'))
    if truncated:
        # Gesagt, nicht verschwiegen: alles unterhalb der Grenze wurde nicht
        # angesehen, ein "fehlt" weiter oben kann daran liegen.
        findings.append(_finding(INFO, 'seo_html_truncated',
                                 kb=MAX_HTML_BYTES // 1024))

    return {
        'start_url': start_url, 'final_url': final_url,
        'status': resp['status'], 'ms': ms, 'bytes': resp['bytes'],
        'truncated': truncated,
        'redirects': len(chain) - 1,
        'title': title, 'title_length': len(title),
        'description': description, 'description_length': len(description),
        'canonical': page.canonical, 'robots_meta': robots_meta,
        'lang': page.html_lang, 'charset': page.charset,
        'viewport': page.metas.get('viewport', ''),
        'headings': [{'level': lvl, 'text': ' '.join(txt.split())[:120]}
                     for lvl, txt in page.headings[:40]],
        'h1': h1s, 'words': words,
        'images_total': page.images_total, 'images_no_alt': page.images_no_alt,
        'og': og, 'twitter': twitter, 'jsonld_types': jsonld_types,
        'hreflang': page.hreflang[:20],
        'robots_txt': robots, 'sitemap': sitemap,
        'mixed_content': mixed[:20],
        'compression': headers.get('content-encoding', ''),
        'cache_control': headers.get('cache-control', ''),
        'favicon': page.icon,
        'findings': findings, 'level': _worst(findings),
        'score': _score(findings),
    }
