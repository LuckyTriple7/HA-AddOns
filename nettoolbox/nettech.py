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

Gesucht wird mit zwei Saetzen von Fingerabdruecken: den eigenen aus
techrules.py (immer da, MIT wie das Add-on) und -- wenn der Betreiber ihn in
den Einstellungen angefordert hat -- dem weit groesseren Gemeinschafts-
Datensatz aus wapimport.py. Beide werden in dieselbe Form gebracht und in
einem Durchlauf geprueft; woher ein Treffer stammt, steht an ihm dran.

Vor jedem Muster steht sein laengstes woertliches Teilstueck. Kommt das im
Text nicht vor, laeuft das Muster gar nicht erst -- ein Textvergleich statt
mehrerer tausend Regex-Laeufe. Das ist zugleich die Absicherung gegen fremde
Muster, die auf praeparierten Seiten entgleisen koennten; darueber wacht
zusaetzlich ein Zeitbudget.

Das HTML wird mit dem Parser aus seocheck gelesen, damit es nur einen gibt,
der Tag-Suppe verdauen muss.
"""

import calendar
import re
import time
from urllib.parse import urljoin, urlparse

import httpcheck
import mailprovider
import seocheck
import techrules
import wapimport
from netcore import Context, ProbeError, http_get, mx_hosts, query, txt_strings

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'

MAX_HTML_BYTES = 384 * 1024
MAX_RESOURCES = 400
HIGH, MEDIUM, LOW = 'high', 'medium', 'low'
BUILTIN, EXTRA = 'builtin', 'extra'

# Obergrenze fuer den Musterdurchlauf. Erreicht wird sie im Normalfall nie
# (der Vorfilter laesst nur eine Handvoll Muster ueberhaupt laufen); sie
# greift, wenn eine Seite ein fremdes Muster in die Irre fuehrt.
SCAN_BUDGET_SECONDS = 6.0

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


def _score(findings: list) -> int:
    """Same idea as the mail/SEO/HTTP/TLS/domain scores. Lighter weight: what
    this check flags (an exposed version string, an insecure cookie) is a
    leak, not something broken outright."""
    score = 100
    for f in findings:
        if f['level'] == FAIL:
            score -= 15
        elif f['level'] == WARN:
            score -= 6
    return max(0, min(100, score))


# ── Mustervergleich ──────────────────────────────────────────────────────────

_CACHE = {}


def _compiled(pattern: str):
    """Jedes Muster wird genau einmal uebersetzt, egal wie oft geprueft wird."""
    hit = _CACHE.get(pattern)
    if hit is None:
        try:
            hit = re.compile(pattern, re.I)
        except (re.error, RecursionError):
            hit = False          # merken, dass es nicht geht, nicht neu probieren
        _CACHE[pattern] = hit
    return hit


def _match(test: dict, text: str) -> dict:
    """{'text': Fundstelle, 'version': ...} oder {}.

    Der Vorfilter zuerst: kommt das woertliche Teilstueck des Musters im Text
    nicht vor, kann das Muster nicht passen.
    """
    if not text:
        return {}
    literal = test.get('l')
    if literal and literal not in text.lower():
        return {}
    regex = _compiled(test['p'])
    if not regex:
        return {}
    found = regex.search(text)
    if not found:
        return {}
    spec = test.get('v') or ''
    version = ''
    if spec:
        try:
            version = (found.group(int(spec) if spec.isdigit() else spec)
                       or '').strip()
        except (IndexError, KeyError):
            version = ''
    return {'text': found.group(0)[:120], 'version': version}


_SLUG_RE = re.compile(r'[^a-z0-9]')


def _key(name: str) -> str:
    """Ein Name, unter dem derselbe Fund aus beiden Regelsaetzen zusammenfaellt.

    Der Zusatz-Datensatz schreibt "Nginx" und "Nuxt.js", wo wir "nginx" und
    "Nuxt" sagen -- ohne diesen Schluessel stuende beides nebeneinander in der
    Liste und saehe aus wie zwei Techniken.
    """
    slug = _SLUG_RE.sub('', (name or '').lower())
    if slug.endswith('js') and len(slug) > 3:
        slug = slug[:-2]
    return slug


def _confidence(kind: str, weight: int) -> str:
    """Die Fundstelle gibt die Obergrenze vor, die Angabe im Datensatz kann
    sie nur senken -- ein 'confidence: 50' im fremden Satz heisst dort
    ausdruecklich 'koennte auch etwas anderes sein'."""
    level = CONFIDENCE.get(kind, LOW)
    if weight < 50:
        return LOW
    if weight < 100 and level == HIGH:
        return MEDIUM
    return level


# ── Regeln in eine gemeinsame Form bringen ───────────────────────────────────

def _tests_from_builtin(rule: dict) -> list:
    """techrules.py -> dieselbe Testform, die auch der Zusatz-Datensatz hat.

    Die eigenen Muster holen ihre Version aus einer Gruppe namens `v`; der
    Vorfilter wird hier genauso gebaut, die eigenen Regeln profitieren also
    davon ebenso.
    """
    tests = []
    for field, pattern in rule.get('headers', ()):
        tests.append({'k': 'header', 'f': field, 'p': pattern, 'v': 'v'})
    for field, pattern in rule.get('meta', ()):
        tests.append({'k': 'meta', 'f': field, 'p': pattern, 'v': 'v'})
    for pattern in rule.get('cookie', ()):
        tests.append({'k': 'cookie', 'p': pattern, 'v': 'v'})
    for pattern in rule.get('script', ()):
        tests.append({'k': 'script', 'p': pattern, 'v': 'v'})
    for pattern in rule.get('url', ()):
        tests.append({'k': 'url', 'p': pattern, 'v': 'v'})
    for pattern in rule.get('html', ()):
        tests.append({'k': 'html', 'p': pattern, 'v': 'v'})
    for test in tests:
        test['l'] = wapimport._literal_of(test['p'])
        test['c'] = 100
    return tests


def _builtin_rules() -> list:
    global _BUILTIN
    if _BUILTIN is None:
        _BUILTIN = [{
            'name': rule['name'], 'cat': rule.get('cat', 'misc'),
            'site': rule.get('site', ''), 'source': BUILTIN,
            'implies': list(rule.get('implies', ())), 'requires': [],
            'tests': _tests_from_builtin(rule),
        } for rule in techrules.RULES]
    return _BUILTIN


_BUILTIN = None


def _extra_rules() -> list:
    return [dict(rule, source=EXTRA) for rule in wapimport.rules()]


# ── Treffer sammeln ──────────────────────────────────────────────────────────

class _Hits:
    """Sammelt Treffer je Technik, ohne dieselbe Fundstelle doppelt zu zaehlen."""

    def __init__(self):
        self.by_name = {}

    def add(self, rule: dict, kind: str, detail: str, version: str = '',
            confidence: str = '') -> None:
        entry = self.by_name.setdefault(_key(rule['name']), {
            'name': rule['name'], 'cat': rule.get('cat', 'misc'),
            'site': rule.get('site', ''), 'source': rule.get('source', BUILTIN),
            'version': '', 'confidence': LOW, 'evidence': [],
        })
        if rule.get('source', BUILTIN) == BUILTIN:
            # Eine eigene Regel gewinnt die Beschreibung: Name, Kategorie und
            # Verweis sind auf diese Oberflaeche abgestimmt.
            entry['name'] = rule['name']
            entry['cat'] = rule.get('cat', entry['cat'])
            entry['site'] = rule.get('site') or entry['site']
            entry['source'] = BUILTIN
        confidence = confidence or CONFIDENCE.get(kind, LOW)
        if CONFIDENCE_ORDER[confidence] > CONFIDENCE_ORDER[entry['confidence']]:
            entry['confidence'] = confidence
        if version and not entry['version']:
            entry['version'] = version[:24]
        row = {'kind': kind, 'detail': detail[:160]}
        if row not in entry['evidence'] and len(entry['evidence']) < 6:
            entry['evidence'].append(row)


class _Subject:
    """Alles, wogegen geprueft wird -- einmal aufbereitet, nicht je Regel."""

    def __init__(self, headers: dict, metas: dict, cookies: list,
                 resources: list, body: str, url: str):
        self.headers = headers
        self.metas = metas
        self.cookies = cookies            # [(Name, Wert)]
        self.resources = resources
        self.body = body
        self.url = url
        self.resource_blob = '\n'.join(resources)
        self.resource_blob_low = self.resource_blob.lower()


def _run_test(test: dict, subject: _Subject) -> dict:
    """Ein Test gegen die passende Stelle. {} = kein Treffer."""
    kind = test.get('k')
    field = test.get('f')
    if kind == 'header':
        return _match(test, subject.headers.get(field, '')) if field else {}
    if kind == 'meta':
        return _match(test, subject.metas.get(field, '')) if field else {}
    if kind == 'cookie':
        for name, value in subject.cookies:
            if field:
                # Fremdes Schema: der Schluessel ist der Cookie-Name, das
                # Muster prueft den Wert (leeres Muster = blosses Vorhandensein).
                if name.lower() != field.lower():
                    continue
                if not test['p'] or _match(test, value):
                    return {'text': name, 'version': ''}
            else:
                hit = _match(test, name)
                if hit:
                    return hit
        return {}
    if kind == 'script':
        # Erst gegen alle Pfade am Stueck -- ein Textvergleich statt vieler
        # Einzellaeufe; nur bei einem Treffer wird die Fundstelle gesucht.
        literal = test.get('l')
        if literal and literal not in subject.resource_blob_low:
            return {}
        for ref in subject.resources:
            hit = _match(test, ref)
            if hit:
                hit['text'] = ref[:160]
                return hit
        return {}
    if kind == 'url':
        return _match(test, subject.url)
    if kind == 'html':
        return _match(test, subject.body)
    return {}


def _scan(rules: list, subject: _Subject, hits: _Hits, deadline: float) -> bool:
    """Alle Regeln durchgehen. False, wenn das Zeitbudget abgelaufen ist."""
    for index, rule in enumerate(rules):
        if not index % 50 and time.monotonic() > deadline:
            return False
        for test in rule['tests']:
            found = _run_test(test, subject)
            if not found:
                continue
            detail = found['text']
            if test.get('f') and test.get('k') in ('header', 'meta'):
                detail = '%s: %s' % (test['f'], detail)
            hits.add(rule, test['k'], detail, found.get('version', ''),
                     _confidence(test['k'], test.get('c', 100)))
    return True


def _drop_unmet_requirements(rules: list, hits: _Hits) -> None:
    """Der Zusatz-Datensatz kennt Regeln, die nur zaehlen, wenn eine andere
    Technik bereits erkannt wurde (ein Plugin ohne sein CMS ist keins)."""
    for rule in rules:
        requires = rule.get('requires') or []
        key = _key(rule['name'])
        if not requires or key not in hits.by_name:
            continue
        if not any(_key(other) in hits.by_name for other in requires):
            hits.by_name.pop(key, None)


def _apply_implies(rules: list, hits: _Hits) -> None:
    """Was eine erkannte Technik zwingend voraussetzt, wird mit aufgenommen --
    aber als abgeleitet und mit niedriger Sicherheit, nie als eigener Fund."""
    # Eigene Regeln zuerst eintragen, damit ein abgeleiteter Fund unter
    # unserem Namen und in unserer Kategorie landet, wenn es ihn bei uns gibt.
    by_key = {}
    for rule in rules:
        key = _key(rule['name'])
        if key not in by_key or rule.get('source', BUILTIN) == BUILTIN:
            by_key[key] = rule
    queue = list(hits.by_name)
    seen = set(queue)
    while queue:
        key = queue.pop()
        rule = by_key.get(key)
        if not rule:
            continue
        for implied in rule.get('implies') or ():
            target_key = _key(implied)
            target = by_key.get(target_key)
            if target is None or target_key in hits.by_name:
                continue
            hits.add(target, 'implied', rule['name'], confidence=LOW)
            if target_key not in seen:
                seen.add(target_key)
                queue.append(target_key)


# ── Cookies ──────────────────────────────────────────────────────────────────

# Chrome kappt seit 2022 jede Lebensdauer bei 400 Tagen; alles darueber ist
# ohnehin Wunschdenken und wird als solches gemeldet.
COOKIE_MAX_DAYS = 400
_COOKIE_DATE_FORMATS = (
    '%a, %d-%b-%Y %H:%M:%S %Z', '%a, %d %b %Y %H:%M:%S %Z',
    '%A, %d-%b-%y %H:%M:%S %Z', '%a %b %d %H:%M:%S %Y',
)


def _cookie_lifetime(attrs: dict) -> int:
    """Lebensdauer in Tagen; -1 heisst Sitzungscookie (faellt beim Schliessen weg).

    Max-Age geht laut RFC 6265 vor Expires, auch wenn beides dasteht.
    """
    if 'max-age' in attrs:
        try:
            return max(0, int(attrs['max-age'])) // 86400
        except ValueError:
            return -1
    raw = attrs.get('expires', '')
    if not raw:
        return -1
    for shape in _COOKIE_DATE_FORMATS:
        try:
            when = time.strptime(raw.strip(), shape)
        except ValueError:
            continue
        seconds = calendar.timegm(when) - time.time()
        return max(0, int(seconds // 86400))
    return -1


def _parse_cookies(raw_headers: list) -> list:
    """Jedes Set-Cookie in seine Bestandteile.

    Der Wert selbst wird nie mitgenommen -- er ist bei einer Sitzung genau das
    Geheimnis, das niemand in einem Bericht oder Schnappschuss haben will.
    Gemeldet wird nur seine Laenge.
    """
    rows = []
    for raw in raw_headers or []:
        parts = str(raw).split(';')
        name, _sep, value = parts[0].partition('=')
        name = name.strip()
        if not name:
            continue
        attrs = {}
        for piece in parts[1:]:
            key, _sep2, attr_value = piece.partition('=')
            attrs[key.strip().lower()] = attr_value.strip()
        days = _cookie_lifetime(attrs)
        rows.append({
            'name': name[:80],
            'value_length': len(value.strip()),
            'secure': 'secure' in attrs,
            'http_only': 'httponly' in attrs,
            'same_site': (attrs.get('samesite') or '').title()[:8],
            'path': (attrs.get('path') or '')[:60],
            'domain': (attrs.get('domain') or '').lstrip('.')[:80],
            'session': days < 0,
            'days': days,
        })
    return rows


def _cookie_findings(rows: list, https: bool) -> list:
    """Was an gesetzten Cookies auffaellt.

    Alles nur ueber die Cookies *dieser einen Antwort*: was JavaScript spaeter
    im Browser setzt, steht in keinem Header und ist von hier aus unsichtbar.
    """
    findings = []
    if not rows:
        return findings
    insecure = [c['name'] for c in rows if https and not c['secure']]
    if insecure:
        findings.append(_finding(WARN, 'tech_cookie_insecure',
                                 count=len(insecure), names=insecure[:5]))
    open_to_js = [c['name'] for c in rows if not c['http_only']]
    if open_to_js:
        findings.append(_finding(INFO, 'tech_cookie_no_httponly',
                                 count=len(open_to_js), names=open_to_js[:5]))
    no_samesite = [c['name'] for c in rows if not c['same_site']]
    if no_samesite:
        findings.append(_finding(INFO, 'tech_cookie_no_samesite',
                                 count=len(no_samesite), names=no_samesite[:5]))
    long_lived = [c for c in rows if c['days'] > COOKIE_MAX_DAYS]
    if long_lived:
        findings.append(_finding(INFO, 'tech_cookie_long_lived',
                                 count=len(long_lived),
                                 days=max(c['days'] for c in long_lived),
                                 max=COOKIE_MAX_DAYS))
    return findings


def _registrable(host: str) -> str:
    """Grob die Domain hinter einem Host -- die letzten zwei Labels, bei den
    bekannten zweistufigen Endungen drei. Reicht, um "eigener Auftritt" von
    "fremder Anbieter" zu unterscheiden; eine vollstaendige Liste aller
    oeffentlichen Suffixe waere ein eigener Datensatz mit eigener Pflege."""
    parts = [p for p in (host or '').lower().split('.') if p]
    if len(parts) < 3:
        return '.'.join(parts)
    if parts[-2] in ('co', 'com', 'org', 'net', 'gov', 'ac') and len(parts[-1]) == 2:
        return '.'.join(parts[-3:])
    return '.'.join(parts[-2:])


# Adressen, die im Markup stehen, aber nie abgerufen werden: Namensraeume in
# SVG und XHTML. Sie als "fremder Host" zu melden waere schlicht falsch.
NON_FETCHED_HOSTS = frozenset({'www.w3.org', 'w3.org', 'schema.org',
                               'www.schema.org', 'purl.org', 'ogp.me'})


def _third_party(resources: list, own_host: str) -> list:
    """Fremde Hosts, von denen die Seite etwas nachlaedt -- jeder davon kann
    beim Abruf eigene Cookies setzen, die hier nicht sichtbar sind."""
    own = _registrable(own_host)
    seen = {}
    for ref in resources:
        if '://' not in ref:
            continue
        host = ref.split('://', 1)[1].split('/', 1)[0].split(':', 1)[0].lower()
        if not host or host in NON_FETCHED_HOSTS or _registrable(host) == own:
            continue
        seen[host] = seen.get(host, 0) + 1
    return [{'host': host, 'count': count}
            for host, count in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))][:30]


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
    for ns_host in nameservers:
        name = _suffix_match(ns_host, techrules.NS_SUFFIXES)
        if name:
            info['ns_provider'] = name
            hits.add({'name': name, 'cat': 'dns', 'site': '',
                      'source': BUILTIN}, 'dns', ns_host)
            break
    try:
        provider = mailprovider.detect_provider([h for _p, h in mx_hosts(ctx, domain)])
    except ProbeError:
        provider = {}
    for name in provider.get('names', []):
        info['mail_provider'].append(name)
        hosts = [row['host'] for row in provider.get('hosts', [])
                 if row['name'] == name]
        hits.add({'name': name, 'cat': 'mail', 'site': '', 'source': BUILTIN},
                 'dns', 'MX ' + (hosts[0] if hosts else domain))
    try:
        spf = [t for t in txt_strings(ctx, domain) if t.lower().startswith('v=spf1')]
    except ProbeError:
        spf = []
    for record in spf:
        for target in _SPF_INCLUDE_RE.findall(record):
            name = _suffix_match(target, techrules.SPF_INCLUDES)
            if name and name not in info['spf_services']:
                info['spf_services'].append(name)
                hits.add({'name': name, 'cat': 'mail', 'site': '',
                          'source': BUILTIN}, 'dns', 'SPF include:' + target)
    return info


# ── Hauptpruefung ────────────────────────────────────────────────────────────

def check_tech(ctx: Context, target: str, extra_rules: bool = False) -> dict:
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
    cookies = []
    for raw in resp.get('cookies', []):
        name, _sep, rest = str(raw).partition('=')
        name = name.strip()
        if name:
            cookies.append((name, rest.split(';', 1)[0].strip()))

    cookie_rows = _parse_cookies(resp.get('cookies', []))
    subject = _Subject(headers, page.metas, cookies, resources, body, final_url)

    rules = list(_builtin_rules())
    extra = _extra_rules() if extra_rules else []
    rules.extend(extra)

    hits = _Hits()
    deadline = time.monotonic() + SCAN_BUDGET_SECONDS
    complete = _scan(rules, subject, hits, deadline)
    _drop_unmet_requirements(rules, hits)
    _apply_implies(rules, hits)

    parsed = urlparse(final_url)
    third_party = _third_party(resources, parsed.hostname or '')
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
    findings.extend(_cookie_findings(cookie_rows, parsed.scheme == 'https'))
    if _SPA_ROOT_RE.search(body):
        findings.append(_finding(INFO, 'tech_spa'))
    if not technologies:
        findings.append(_finding(INFO, 'tech_nothing'))
    else:
        findings.append(_finding(OK, 'tech_found', count=len(technologies)))
    if not complete:
        findings.append(_finding(INFO, 'tech_budget',
                                 seconds=int(SCAN_BUDGET_SECONDS)))
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
        'cookies': [name for name, _value in cookies][:20],
        'cookie_details': cookie_rows[:40],
        'third_party': third_party,
        'headers': {k: v[:200] for k, v in headers.items()},
        'dns': dns_info,
        'rules_used': {'builtin': len(_builtin_rules()), 'extra': len(extra)},
        'scan_complete': complete,
        'findings': findings, 'level': _worst(findings), 'score': _score(findings),
    }
