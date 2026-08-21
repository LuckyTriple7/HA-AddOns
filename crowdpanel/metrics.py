#!/usr/bin/env python3
"""CrowdSec Prometheus metrics — reader and grouping.

CrowdSec exposes its internal counters in the Prometheus text format, by
default on ``http://127.0.0.1:6060/metrics``. The LAPI does not offer any of
this, so `cscli metrics` reads the very same endpoint and only rearranges the
numbers into tables. CrowdPanel does the same here.

Everything is grouped into generic tables — an id, a list of column keys and
rows of plain values. The front-end renders them without knowing a single
metric name, so a CrowdSec version that drops or adds a counter changes the
tables, never the code that draws them.

Counters are cumulative since CrowdSec started; they are not rates.
"""

import logging
import re
import threading
import time
from collections import defaultdict
from urllib.parse import urlsplit

import requests as http

from lapi import LapiError

log = logging.getLogger(__name__)

# Default port of CrowdSec's Prometheus listener. Only reachable from another
# container when `prometheus.listen_addr` is not left at 127.0.0.1.
DEFAULT_PORT = 6060

# A busy installation answers with a few hundred kilobytes. The caps are here
# so a wrong URL pointing at something huge cannot fill the add-on's memory.
MAX_BYTES = 8 * 1024 * 1024
MAX_SAMPLES = 200_000

# Long enough that the auto-refresh does not hammer CrowdSec, short enough that
# the page still feels live.
CACHE_TTL = 10

# Rows per table. The parser and scenario tables can hold hundreds of entries
# on a full hub install; nobody reads past the first screen.
MAX_ROWS = 200

_SAMPLE_RE = re.compile(
    r'^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)'
    r'(?P<labels>\{.*\})?'
    r'[ \t]+(?P<value>[^ \t]+)'
    r'(?:[ \t]+-?[0-9.]+)?$')
_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')
_ESCAPES = {'\\\\': '\\', '\\"': '"', '\\n': '\n'}


def _unescape(raw: str) -> str:
    if '\\' not in raw:
        return raw
    out, i = [], 0
    while i < len(raw):
        pair = raw[i:i + 2]
        if pair in _ESCAPES:
            out.append(_ESCAPES[pair])
            i += 2
        else:
            out.append(raw[i])
            i += 1
    return ''.join(out)


def parse_text(text: str) -> dict:
    """Prometheus text format to ``{metric_name: [(labels, value), ...]}``.

    Unparsable lines are skipped rather than raising: the endpoint is a
    debugging surface and a single odd line should not blank the whole page.
    """
    out: dict = defaultdict(list)
    seen = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] == '#':
            continue
        match = _SAMPLE_RE.match(line)
        if not match:
            continue
        raw = match.group('value')
        try:
            value = float(raw)
        except ValueError:
            continue                      # NaN/Inf and friends carry no meaning here
        if value != value or value in (float('inf'), float('-inf')):
            continue
        labels = {}
        block = match.group('labels')
        if block:
            for key, val in _LABEL_RE.findall(block):
                labels[key] = _unescape(val)
        out[match.group('name')].append((labels, value))
        seen += 1
        if seen >= MAX_SAMPLES:
            log.warning("metrics: stopped after %d samples", seen)
            break
    return dict(out)


# ── Grouping helpers ──────────────────────────────────────────────────────────

def _by(samples: dict, name: str, *keys: str) -> dict:
    """Sum one metric into a dict keyed by the given labels."""
    out: dict = defaultdict(float)
    for labels, value in samples.get(name, ()):
        out[tuple(labels.get(k, '') for k in keys)] += value
    return out


def _num(value: float) -> float | int:
    """Counters are whole numbers; only gauges and averages need decimals."""
    return int(value) if float(value).is_integer() else round(value, 3)


def _table(tid: str, cols: tuple, rows: list, sort_key: str | None = None) -> dict | None:
    """One rendered table, or None when this CrowdSec has nothing to show."""
    if not rows:
        return None
    if sort_key:
        rows.sort(key=lambda r: (-float(r.get(sort_key) or 0),
                                 str(r.get(cols[0]) or '')))
    total = len(rows)
    return {'id': tid, 'cols': list(cols), 'rows': rows[:MAX_ROWS],
            'total': total, 'truncated': total > MAX_ROWS}


def _keyed_rows(keys: tuple, columns: dict) -> list:
    """Build rows from several metrics that share the same label keys.

    ``columns`` maps a column name to a ``{labelkey: value}`` dict. A row is
    emitted for every key any of them knows, missing numbers count as zero.
    """
    known: set = set()
    for values in columns.values():
        known.update(values)
    rows = []
    for key in known:
        row = {name: key[i] for i, name in enumerate(keys)}
        for col, values in columns.items():
            row[col] = _num(values.get(key, 0))
        rows.append(row)
    return rows


def _histogram(samples: dict, name: str, *keys: str) -> list:
    """Average duration per label set, from the histogram's _sum and _count."""
    sums = _by(samples, name + '_sum', *keys)
    counts = _by(samples, name + '_count', *keys)
    rows = []
    for key, count in counts.items():
        if count <= 0:
            continue
        row = {'metric': name, 'label': ' / '.join(p for p in key if p) or '-',
               'avg_ms': round(sums.get(key, 0.0) / count * 1000, 3),
               'count': _num(count)}
        rows.append(row)
    return rows


def build_tables(samples: dict) -> list:
    """cscli-style tables, in the order the page shows them."""
    tables = []

    # -- Acquisition: what came in, and how far it got ------------------------
    read = _by(samples, 'cs_parser_hits_total', 'source', 'type')
    parsed = _by(samples, 'cs_parser_hits_ok_total', 'source', 'type')
    unparsed = _by(samples, 'cs_parser_hits_ko_total', 'source', 'type')
    # Poured and whitelisted carry no "type" label, so they are matched on the
    # source alone and spread over that source's rows.
    poured_src = _by(samples, 'cs_bucket_poured_total', 'source')
    white_src = _by(samples, 'cs_node_wl_hits_ok_total', 'source')
    rows = _keyed_rows(('source', 'type'),
                       {'read': read, 'parsed': parsed, 'unparsed': unparsed})
    for row in rows:
        key = (row['source'],)
        row['poured'] = _num(poured_src.get(key, 0))
        row['whitelisted'] = _num(white_src.get(key, 0))
    tables.append(_table('acquisition',
                         ('source', 'type', 'read', 'parsed', 'unparsed',
                          'poured', 'whitelisted'), rows, 'read'))

    # -- Parsers --------------------------------------------------------------
    keys = ('name', 'stage')
    rows = _keyed_rows(keys, {
        'hits': _by(samples, 'cs_node_hits_total', *keys),
        'parsed': _by(samples, 'cs_node_hits_ok_total', *keys),
        'unparsed': _by(samples, 'cs_node_hits_ko_total', *keys),
    })
    tables.append(_table('parsers', ('name', 'stage', 'hits', 'parsed',
                                     'unparsed'), rows, 'hits'))

    # -- Scenarios (buckets) --------------------------------------------------
    rows = _keyed_rows(('name',), {
        'current': _by(samples, 'cs_buckets', 'name'),
        'overflows': _by(samples, 'cs_bucket_overflowed_total', 'name'),
        'instantiated': _by(samples, 'cs_bucket_instantiation_total', 'name'),
        'poured': _by(samples, 'cs_bucket_poured_total', 'name'),
        'expired': _by(samples, 'cs_bucket_underflowed_total', 'name'),
    })
    tables.append(_table('scenarios',
                         ('name', 'current', 'overflows', 'instantiated',
                          'poured', 'expired'), rows, 'overflows'))

    # -- Whitelists -----------------------------------------------------------
    keys = ('name', 'reason')
    rows = _keyed_rows(keys, {
        'hits': _by(samples, 'cs_node_wl_hits_total', *keys),
        'whitelisted': _by(samples, 'cs_node_wl_hits_ok_total', *keys),
    })
    tables.append(_table('whitelists', ('name', 'reason', 'hits',
                                        'whitelisted'), rows, 'whitelisted'))

    # -- Local API ------------------------------------------------------------
    rows = _keyed_rows(('route', 'method'),
                       {'count': _by(samples, 'cs_lapi_route_requests_total',
                                     'route', 'method')})
    tables.append(_table('lapi_routes', ('route', 'method', 'count'),
                         rows, 'count'))

    rows = _keyed_rows(('machine', 'route', 'method'),
                       {'count': _by(samples, 'cs_lapi_machine_requests_total',
                                     'machine', 'route', 'method')})
    tables.append(_table('lapi_machines',
                         ('machine', 'route', 'method', 'count'), rows, 'count'))

    # Bouncer view: requests plus how often the answer actually carried
    # decisions. A bouncer with only empty answers is not seeing any bans.
    rows = _keyed_rows(('bouncer',), {
        'requests': _by(samples, 'cs_lapi_bouncer_requests_total', 'bouncer'),
        'with_decisions': _by(samples, 'cs_lapi_decisions_ok_total', 'bouncer'),
        'empty': _by(samples, 'cs_lapi_decisions_ko_total', 'bouncer'),
    })
    tables.append(_table('lapi_bouncers',
                         ('bouncer', 'requests', 'with_decisions', 'empty'),
                         rows, 'requests'))

    # -- AppSec ---------------------------------------------------------------
    keys = ('appsec_engine', 'source')
    rows = _keyed_rows(keys, {
        'requests': _by(samples, 'cs_appsec_reqs_total', *keys),
        'blocked': _by(samples, 'cs_appsec_block_total', *keys),
    })
    tables.append(_table('appsec', ('appsec_engine', 'source', 'requests',
                                    'blocked'), rows, 'requests'))

    keys = ('rule_name', 'appsec_engine', 'type')
    rows = _keyed_rows(keys, {'hits': _by(samples, 'cs_appsec_rule_hits', *keys)})
    tables.append(_table('appsec_rules',
                         ('rule_name', 'appsec_engine', 'type', 'hits'),
                         rows, 'hits'))

    # -- Decisions and alerts, as CrowdSec itself counts them ------------------
    keys = ('reason', 'origin', 'action')
    rows = _keyed_rows(keys, {'count': _by(samples, 'cs_active_decisions', *keys)})
    tables.append(_table('active_decisions',
                         ('reason', 'origin', 'action', 'count'), rows, 'count'))

    rows = _keyed_rows(('reason',), {'count': _by(samples, 'cs_alerts', 'reason')})
    tables.append(_table('alerts', ('reason', 'count'), rows, 'count'))

    # -- Latency --------------------------------------------------------------
    rows = (_histogram(samples, 'cs_parsing_time_seconds', 'type', 'source')
            + _histogram(samples, 'cs_bucket_pour_seconds', 'type', 'source')
            + _histogram(samples, 'cs_lapi_request_duration_seconds',
                         'endpoint', 'method')
            + _histogram(samples, 'cs_appsec_parsing_time_seconds',
                         'appsec_engine', 'source'))
    tables.append(_table('latency', ('metric', 'label', 'avg_ms', 'count'),
                         rows, 'avg_ms'))

    # -- Caches ---------------------------------------------------------------
    rows = _keyed_rows(('name', 'type'),
                       {'size': _by(samples, 'cs_cache_size', 'name', 'type')})
    rows += _keyed_rows(('name',),
                        {'size': _by(samples, 'cs_regexp_cache_size', 'name')})
    for row in rows:
        row.setdefault('type', 'regexp')
    tables.append(_table('cache', ('name', 'type', 'size'), rows, 'size'))

    return [t for t in tables if t]


def build_summary(samples: dict) -> dict:
    """The handful of numbers that belong above the tables."""
    def total(name: str) -> int:
        return int(sum(v for _, v in samples.get(name, ())))

    return {
        'lines_read': total('cs_parser_hits_total'),
        'lines_unparsed': total('cs_parser_hits_ko_total'),
        'overflows': total('cs_bucket_overflowed_total'),
        'active_decisions': total('cs_active_decisions'),
        'lapi_requests': total('cs_lapi_route_requests_total'),
        'appsec_blocked': total('cs_appsec_block_total'),
    }


def read_version(samples: dict) -> str:
    for labels, _ in samples.get('cs_info', ()):
        version = labels.get('version') or ''
        if version:
            return version
    return ''


# ── Client ────────────────────────────────────────────────────────────────────

class MetricsClient:
    """Fetches and groups CrowdSec's Prometheus output.

    Errors are raised as LapiError so the API layer maps them to the same
    status codes and translated messages the rest of the add-on already uses.
    """

    def __init__(self, url: str, verify: bool = True, timeout: int = 10):
        self.url = (url or '').strip().rstrip('/')
        self.verify = bool(verify)
        self.timeout = timeout
        self._lock = threading.Lock()
        self._cached: dict | None = None
        self._cached_at = 0.0

    def same_as(self, url: str, verify: bool) -> bool:
        return ((url or '').strip().rstrip('/') == self.url
                and bool(verify) == self.verify)

    def configured(self) -> bool:
        return bool(self.url) and self.url_ok()

    def url_ok(self) -> bool:
        parts = urlsplit(self.url)
        return parts.scheme in ('http', 'https') and bool(parts.netloc)

    def endpoint(self) -> str:
        """A URL without a path means the standard /metrics of that host."""
        parts = urlsplit(self.url)
        return self.url if parts.path.strip('/') else self.url + '/metrics'

    def _fetch(self) -> str:
        try:
            r = http.get(self.endpoint(), timeout=self.timeout,
                         verify=self.verify, stream=True,
                         headers={'User-Agent': 'crowdpanel/1.0'})
        except http.RequestException:
            raise LapiError('unreachable') from None
        with r:
            if r.status_code in (401, 403):
                raise LapiError('auth_failed', r.status_code)
            if r.status_code >= 400:
                raise LapiError('http_error', r.status_code)
            chunks, size = [], 0
            try:
                for chunk in r.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise LapiError('bad_response', r.status_code)
                    chunks.append(chunk)
            except http.RequestException:
                raise LapiError('unreachable') from None
        text = b''.join(chunks).decode('utf-8', 'replace')
        # An HTML login page or a JSON error answers with 200 just as happily
        # as the real endpoint does; a metrics body always has comment lines.
        if '# HELP' not in text and '# TYPE' not in text:
            raise LapiError('bad_response')
        return text

    def snapshot(self, force: bool = False) -> dict:
        if not self.url:
            raise LapiError('not_configured')
        if not self.url_ok():
            raise LapiError('bad_url')
        with self._lock:
            fresh = self._cached is not None and time.time() - self._cached_at < CACHE_TTL
            if fresh and not force:
                return self._cached
            samples = parse_text(self._fetch())
            tables = build_tables(samples)
            data = {'available': True,
                    'url': self.endpoint(),
                    'version': read_version(samples),
                    'metrics': len(samples),
                    'summary': build_summary(samples),
                    'tables': tables,
                    'fetched': time.time()}
            self._cached = data
            self._cached_at = time.time()
            return data

    def drop_cache(self) -> None:
        with self._lock:
            self._cached = None
            self._cached_at = 0.0
