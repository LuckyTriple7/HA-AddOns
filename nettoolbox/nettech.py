"""Welche Technik hinter einer Adresse steckt.

Das ist die ehrliche Variante dessen, was Dienste wie BuiltWith anbieten:
*ein* Ziel, live gemessen, aus dem, was der Server tatsächlich ausliefert --
Antwort-Header, Cookies, das HTML mit seinen eingebundenen Dateien, dazu die
DNS-Seite (Nameserver, MX, SPF). Keine Datenbank über Millionen Domains,
keine Historie, keine Marktanteile: das ist gecrawltes Fremdwissen und mit
einer Einzelabfrage nicht zu haben.

Zwei Grenzen, die im Ergebnis auch so benannt werden:

* Kein JavaScript. Beurteilt wird das gelieferte Dokument, nicht das, was ein
  Browser daraus baut. Eine Seite, die ihre halbe Technik erst im Client
  nachlaedt, zeigt hier entsprechend wenig -- dasselbe Bild, das ein Crawler
  ohne Browser sieht.
* Ein Fingerabdruck ist ein Indiz, kein Beweis. Header lassen sich frei
  setzen, Pfade umschreiben. Jeder Treffer traegt deshalb seine Fundstelle
  und eine Sicherheitsangabe mit sich und faerbt nie eine Ampel.

Gefunden wird ueber die Tabelle in techrules.py; die Auswertung hier kennt
keine einzige Technik beim Namen. Das HTML wird mit dem Parser aus seocheck
gelesen, damit es nur einen gibt, der Tag-Suppe verdauen muss.
"""

import re
import time
from urllib.parse import urljoin, urlparse

import httpcheck
import mailprovider
import seocheck
import techrules
from netcore import Context, ProbeError, http_get, mx_hosts, query, txt_strings

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'

MAX_HTML_BYTES = 384 * 1024
MAX_RESOURCES = 400
HIGH, MEDIUM, LOW = 'high', 'medium', 'low'

# Wie sicher ein Treffer ist, haengt an der Fundstelle: ein eigener Header oder
# ein Cookie-Name kommt vom Server selbst, ein Pfad zu einer mitgelieferten
# Datei ebenso. Ein Muster irgendwo im Fliesstext kann dagegen auch nur ein
# zitierter Klassenname sein -- deshalb nur "mittel".
CONFIDENCE = {
    'header': HIGH, 'meta': HIGH, 'cookie': HIGH, 'script': HIGH,
    'url': HIGH, 'html': MEDIUM, 'dns': HIGH, 'implied': LOW,
}
CONFIDENCE_ORDER = {HIGH: 3, MEDIUM: 2, LOW: 1}

# Version im Server-Header und in x-powered-by: verraet Angreifern, welche
# Luecken sich zu probieren lohnen, und wird deshalb als Hinweis gemeldet.
_VERSION_IN_HEADER = re.compile(r'/\d+\.\d')
_SPF_INCLUDE_RE = re.compile(r'\b(?:include|redirect)[:=]([A-Za-z0-9._-]+)')
_SPA_ROOT_RE = re.compile(
    r'<div[^>]+id="(?:root|app|__next|__nuxt)"[^>]*>\s*</div>', re.I)


def _finding(level: str, code: str, **args) -> dict:
    return {'level': level, 'code': code, 'args': args}


def _worst(findings: list) -> str:
    for level in (FAIL, WARN):
        if any(f['level'] == level for f in findings):
            return level
    return OK


# ── Mustervergleich ──────────────────────────────────────────────────────────

_CACHE = {}


def _compiled(pattern: str):
    """Die Muster stehen fest in techrules.py -- kompiliert wird jedes genau
    einmal, egal wie oft geprueft wird."""
    hit = _CACHE.get(pattern)
    if hit is None:
        hit = _CACHE[pattern] = re.compile(pattern, re.I)
    return hit


def _match(pattern: str, text: str) -> dict:
    """{'text': <Fundstelle>, 'version': <falls die Gruppe v traf>} oder {}."""
    if not text:
        return {}
    found = _compiled(pattern).search(text)
    if not found:
        return {}
    version = ''
    try:
        version = (found.groupdict().get('v') or '').strip()
    except IndexError:
        version = ''
    return {'text': found.group(0)[:120], 'version': version}


class _Hits:
    """Sammelt Treffer je Technik, ohne dieselbe Fundstelle doppelt zu zaehlen."""

    def __init__(self):
        self.by_name = {}

    def add(self, rule: dict, kind: str, detail: str, version: str = '') -> None:
        entry = self.by_name.setdefault(rule['name'], {
            'name': rule['name'], 'cat': rule.get('cat', 'misc'),
            'site': rule.get('site', ''), 'version': '',
            'confidence': LOW, 'evidence': [],
        })
        confidence = CONFIDENCE.get(kind, LOW)
        if CONFIDENCE_ORDER[confidence] > CONFIDENCE_ORDER[entry['confidence']]:
            entry['confidence'] = confidence
        if version and not entry['version']:
            entry['version'] = version[:24]
        row = {'kind': kind, 'detail': detail[:160]}
        if row not in entry['evidence'] and len(entry['evidence']) < 6:
            entry['evidence'].append(row)


def _scan_rule(rule: dict, hits: _Hits, headers: dict, metas: dict,
               cookies: list, resources: list, body: str, url: str) -> bool:
    """Alle Fundstellen einer Regel. True, sobald irgendetwas passte."""
    found = False
    for name, pattern in rule.get('headers', ()):
        value = headers.get(name, '')
        m = _match(pattern, value)
        if m:
            hits.add(rule, 'header', f'{name}: {value[:80]}', m['version'])
            found = True
    for name, pattern in rule.get('meta', ()):
        m = _match(pattern, metas.get(name, ''))
        if m:
            hits.add(rule, 'meta', f'{name}: {m["text"]}', m['version'])
            found = True
    for pattern in rule.get('cookie', ()):
        for cookie in cookies:
            m = _match(pattern, cookie)
            if m:
                hits.add(rule, 'cookie', cookie, m['version'])
                found = True
                break
    for pattern in rule.get('script', ()):
        for ref in resources:
            m = _match(pattern, ref)
            if m:
                hits.add(rule, 'script', ref, m['version'])
                found = True
                break
    for pattern in rule.get('url', ()):
        m = _match(pattern, url)
        if m:
            hits.add(rule, 'url', m['text'], m['version'])
            found = True
    for pattern in rule.get('html', ()):
        m = _match(pattern, body)
        if m:
            hits.add(rule, 'html', m['text'], m['version'])
            found = True
    return found


def _apply_implies(hits: _Hits) -> None:
    """Was eine erkannte Technik zwingend voraussetzt, wird mit aufgenommen --
    aber als abgeleitet und mit niedriger Sicherheit, nie als eigener Fund."""
    by_rule = {r['name']: r for r in techrules.RULES}
    queue = list(hits.by_name)
    seen = set(queue)
    while queue:
        name = queue.pop()
        rule = by_rule.get(name)
        if not rule:
            continue
        for implied in rule.get('implies', ()):
            target = by_rule.get(implied)
            if target is None or implied in hits.by_name:
                continue
            hits.add(target, 'implied', name)
            if implied not in seen:
                seen.add(implied)
                queue.append(implied)


# ── DNS-Seite ────────────────────────────────────────────────────────────────

def _suffix_match(host: str, table) -> str:
    """Immer auf das Ende geprueft, nie als Teilstring: sonst wuerde
    'awsdns.com.angreifer.net' als Route 53 durchgehen."""
    host = (host or '').strip().strip('.').lower()
    best_name, best_len = '', 0
    for suffix, name in table:
        if (host == suffix or host.endswith('.' + suffix)) and len(suffix) > best_len:
            best_name, best_len = name, len(suffix)
    return best_name


def _zone_of(ctx: Context, host: str) -> tuple:
    """Die Zone ueber dem Host, samt ihrer Nameserver.

    Gefragt wird nach der Adresse, auf der die Seite am Ende landet -- und die
    heisst meist www.beispiel.de. Dort steht kein NS-, MX- oder SPF-Eintrag;
    der gehoert der Zone darueber. Also wird Label fuer Label nach oben
    gegangen, bis Nameserver antworten, hoechstens drei Schritte weit.
    """
    parts = [p for p in (host or '').split('.') if p]
    for index in range(min(3, max(0, len(parts) - 1)) + 1):
        candidate = '.'.join(parts[index:])
        if candidate.count('.') < 1:
            break
        try:
            records = query(ctx, candidate, 'NS').records
        except ProbeError:
            continue
        if records:
            return candidate, [n.strip('.').lower() for n in records]
    return host, []


def _dns_side(ctx: Context, host: str, hits: _Hits) -> dict:
    """Nameserver, Mailanbieter und die Dienste aus dem SPF-Eintrag.

    Ein Fehlschlag ist hier nie ein Abbruch: die Technik-Erkennung der Seite
    steht fuer sich, die DNS-Seite ist eine Zugabe.
    """
    domain, nameservers = _zone_of(ctx, host)
    info = {'ns': nameservers, 'ns_provider': '', 'mail_provider': [],
            'spf_services': [], 'domain': domain}
    for host in info['ns']:
        name = _suffix_match(host, techrules.NS_SUFFIXES)
        if name:
            info['ns_provider'] = name
            hits.add({'name': name, 'cat': 'dns', 'site': ''}, 'dns', host)
            break
    try:
        provider = mailprovider.detect_provider([h for _p, h in mx_hosts(ctx, domain)])
    except ProbeError:
        provider = {}
    for name in provider.get('names', []):
        info['mail_provider'].append(name)
        hosts = [row['host'] for row in provider.get('hosts', [])
                 if row['name'] == name]
        hits.add({'name': name, 'cat': 'mail', 'site': ''}, 'dns',
                 'MX ' + (hosts[0] if hosts else domain))
    try:
        spf = [t for t in txt_strings(ctx, domain) if t.lower().startswith('v=spf1')]
    except ProbeError:
        spf = []
    for record in spf:
        for target in _SPF_INCLUDE_RE.findall(record):
            name = _suffix_match(target, techrules.SPF_INCLUDES)
            if name and name not in info['spf_services']:
                info['spf_services'].append(name)
                hits.add({'name': name, 'cat': 'mail', 'site': ''}, 'dns',
                         'SPF include:' + target)
    return info


# ── Hauptpruefung ────────────────────────────────────────────────────────────

def check_tech(ctx: Context, target: str) -> dict:
    start_url = httpcheck.normalise_url(target)
    chain = httpcheck.follow_redirects(ctx, start_url)
    final_url = chain[-1]['url']

    started = time.monotonic()
    resp = http_get(ctx, final_url, max_bytes=MAX_HTML_BYTES,
                    accept='text/html,application/xhtml+xml,*/*')
    ms = int((time.monotonic() - started) * 1000)
    headers = resp['headers']
    body = resp['body']
    truncated = resp['bytes'] >= MAX_HTML_BYTES

    page = seocheck._Page()
    try:
        page.feed(body)
        page.close()
    except Exception:
        # Kaputtes Markup ist der Normalfall im Web; was bis dahin gelesen
        # wurde, reicht fuer die Erkennung.
        pass

    # Relative Pfade werden aufgeloest, damit eine Regel auf einen fremden
    # Host (cdn.shopify.com) nicht daran scheitert, dass die Seite ihn nur
    # protokollrelativ (//cdn...) einbindet.
    resources = []
    for ref in page.resources[:MAX_RESOURCES]:
        try:
            resources.append(urljoin(final_url, ref))
        except ValueError:
            resources.append(ref)

    # Set-Cookie kommt als Liste, nicht als ein zusammengeklebter Header --
    # sonst waere bei mehreren Cookies nur der erste Name auswertbar.
    cookies = [c.split('=', 1)[0].strip() for c in resp.get('cookies', []) if c]

    hits = _Hits()
    for rule in techrules.RULES:
        _scan_rule(rule, hits, headers, page.metas, cookies, resources,
                   body, final_url)
    _apply_implies(hits)

    parsed = urlparse(final_url)
    dns_info = {}
    if not parsed.hostname or not parsed.hostname.replace('.', '').isdigit():
        try:
            dns_info = _dns_side(ctx, (parsed.hostname or '').lower(), hits)
        except ProbeError:
            dns_info = {}

    technologies = sorted(
        hits.by_name.values(),
        key=lambda t: (-CONFIDENCE_ORDER[t['confidence']], t['cat'], t['name'].lower()))

    groups = {}
    for tech in technologies:
        groups.setdefault(tech['cat'], []).append(tech['name'])

    # ── Hinweise ─────────────────────────────────────────────────────────

    findings = []
    server = headers.get('server', '')
    powered = headers.get('x-powered-by', '')
    if _VERSION_IN_HEADER.search(server):
        findings.append(_finding(WARN, 'tech_server_version', value=server[:60]))
    if powered:
        findings.append(_finding(WARN, 'tech_powered_by', value=powered[:60]))
    if headers.get('x-aspnet-version'):
        findings.append(_finding(WARN, 'tech_aspnet_version',
                                 value=headers['x-aspnet-version'][:40]))
    generator = page.metas.get('generator', '')
    if re.search(r'\d+\.\d', generator):
        findings.append(_finding(WARN, 'tech_generator_version',
                                 value=generator[:60]))

    counts = {}
    for tech in technologies:
        counts[tech['cat']] = counts.get(tech['cat'], 0) + 1
    if counts.get('analytics') or counts.get('marketing'):
        findings.append(_finding(
            INFO, 'tech_trackers',
            count=counts.get('analytics', 0) + counts.get('marketing', 0)))
        if not counts.get('consent'):
            # Kein Urteil ueber die Rechtslage -- nur der Befund, dass Messung
            # da ist und eine Einwilligungsloesung nicht erkannt wurde.
            findings.append(_finding(INFO, 'tech_no_consent'))
    if _SPA_ROOT_RE.search(body):
        findings.append(_finding(INFO, 'tech_spa'))
    if not technologies:
        findings.append(_finding(INFO, 'tech_nothing'))
    else:
        findings.append(_finding(OK, 'tech_found', count=len(technologies)))
    if truncated:
        findings.append(_finding(INFO, 'tech_truncated',
                                 kb=MAX_HTML_BYTES // 1024))

    return {
        'start_url': start_url, 'final_url': final_url,
        'status': resp['status'], 'ms': ms, 'bytes': resp['bytes'],
        'truncated': truncated, 'redirects': len(chain) - 1,
        'server': server, 'powered_by': powered,
        'generator': generator,
        'title': ' '.join(page.title.split())[:160],
        'technologies': technologies,
        'groups': groups,
        'counts': counts,
        'cookies': cookies[:20],
        'headers': {k: v[:200] for k, v in headers.items()},
        'dns': dns_info,
        'findings': findings, 'level': _worst(findings),
    }
