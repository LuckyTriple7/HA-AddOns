#!/usr/bin/env python3
"""CrowdSec Local API client — machine (watcher) credentials only.

cscli is itself a watcher: it lists active decisions through
``GET /v1/alerts?has_active_decision=true`` and flattens the decisions
embedded in each alert. CrowdPanel does the same, so a single machine
account covers reading, banning and unbanning — no bouncer API key needed.

Auth map of the endpoints used here:
    GET    /v1/alerts                JWT (machine)
    POST   /v1/alerts                JWT (machine)
    GET    /v1/alerts/{id}           JWT (machine)
    DELETE /v1/decisions             JWT (machine)
    DELETE /v1/decisions/{id}        JWT (machine)
    GET    /v1/allowlists            no auth
    GET    /v1/allowlists/check/{ip} no auth
"""

import ipaddress
import logging
import re
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import requests as http

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SCOPES = ('Ip', 'Range', 'Country', 'AS')
DECISION_TYPES = ('ban', 'captcha')

# Preset durations offered in the UI. Go duration syntax — CrowdSec has no
# "forever", so the longest preset is simply a very long ban.
DURATION_PRESETS = ('1h', '4h', '12h', '24h', '168h', '720h', '8760h')

# Go duration: one or more <number><unit> groups, units h/m/s.
_DURATION_RE = re.compile(r'^(?:[0-9]+(?:\.[0-9]+)?[hms])+$')
_CC_RE = re.compile(r'^[A-Za-z]{2}$')
_AS_RE = re.compile(r'^[0-9]{1,10}$')

# Decisions are created with origin "cscli" on purpose: bouncers and the
# console may filter unknown origins away. CrowdPanel identifies itself in
# the scenario and message text instead.
ORIGIN = 'cscli'
ACTOR = 'crowdpanel'

_LOGIN_LEEWAY = 60      # renew the token this many seconds before it expires
_FALLBACK_TTL = 3300    # CrowdSec hands out 1h tokens; stay below that

# One alert can carry thousands of decisions, so a full read is a multi-megabyte
# payload — on a busy installation that is a second per request. Overview and
# decisions ask for the same thing, so the answer is held briefly and shared;
# every write drops the cache so a lifted ban never lingers on screen.
ALERT_CACHE_TTL = 15
ALERT_FETCH_LIMIT = 1000


# ── Errors ────────────────────────────────────────────────────────────────────

class ValidationError(ValueError):
    """Bad user input. ``code`` is a stable slug safe to return to the client."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class LapiError(Exception):
    """LAPI could not be reached or refused the request.

    ``code`` is a stable slug; ``status`` is the HTTP status when there was one.
    Neither carries any server text, so nothing leaks into a response.
    """

    def __init__(self, code: str, status: int | None = None):
        super().__init__(code)
        self.code = code
        self.status = status


# ── Input validation ──────────────────────────────────────────────────────────

def normalize_scope(raw: str) -> str:
    want = (raw or '').strip().lower()
    for s in SCOPES:
        if s.lower() == want:
            return s
    raise ValidationError('bad_scope')


def normalize_type(raw: str) -> str:
    want = (raw or '').strip().lower()
    if want in DECISION_TYPES:
        return want
    raise ValidationError('bad_type')


def normalize_duration(raw: str) -> str:
    want = (raw or '').strip().replace(' ', '')
    if not want or len(want) > 24 or not _DURATION_RE.match(want):
        raise ValidationError('bad_duration')
    return want


def normalize_value(scope: str, raw: str) -> str:
    """Validate the ban target for its scope and return it in canonical form."""
    want = (raw or '').strip()
    if not want or len(want) > 64:
        raise ValidationError('bad_value')
    if scope == 'Ip':
        try:
            return str(ipaddress.ip_address(want))
        except ValueError:
            raise ValidationError('bad_ip') from None
    if scope == 'Range':
        try:
            return str(ipaddress.ip_network(want, strict=False))
        except ValueError:
            raise ValidationError('bad_range') from None
    if scope == 'Country':
        if not _CC_RE.match(want):
            raise ValidationError('bad_country')
        return want.upper()
    if scope == 'AS':
        want = want.upper().removeprefix('AS')
        if not _AS_RE.match(want):
            raise ValidationError('bad_as')
        return want
    raise ValidationError('bad_scope')


def is_ip_or_range(raw: str) -> tuple[str, str] | None:
    """Classify a lookup term. Returns ('ip'|'range', canonical) or None."""
    want = (raw or '').strip()
    if not want or len(want) > 64:
        return None
    try:
        return 'ip', str(ipaddress.ip_address(want))
    except ValueError:
        pass
    try:
        return 'range', str(ipaddress.ip_network(want, strict=False))
    except ValueError:
        return None


def _source_for(scope: str, value: str) -> dict:
    src = {'scope': scope, 'value': value}
    if scope == 'Ip':
        src['ip'] = value
    elif scope == 'Range':
        src['range'] = value
    elif scope == 'Country':
        src['cn'] = value
    elif scope == 'AS':
        src['as_number'] = value
    return src


def _parse_expire(raw: str) -> float:
    """RFC3339 timestamp from the login response → epoch seconds."""
    txt = (raw or '').strip()
    if not txt:
        return 0.0
    txt = txt.replace('Z', '+00:00')
    # CrowdSec emits more than six fractional digits; datetime rejects those.
    txt = re.sub(r'(\.[0-9]{6})[0-9]+', r'\1', txt)
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


# ── Client ────────────────────────────────────────────────────────────────────

class LapiClient:
    # 30s, not 15: right after a burst of writes CrowdSec re-evaluates its
    # decisions and a full read can take noticeably longer than usual.
    def __init__(self, url: str, machine_id: str, password: str,
                 verify: bool = True, timeout: int = 30):
        self.url = (url or '').strip().rstrip('/')
        self.machine_id = (machine_id or '').strip()
        self.password = password or ''
        self.verify = bool(verify)
        self.timeout = timeout
        self._lock = threading.Lock()
        self._jwt = ''
        self._jwt_exp = 0.0
        self._cache: dict = {}
        self._cache_lock = threading.Lock()

    # -- state ---------------------------------------------------------------

    def url_ok(self) -> bool:
        parts = urlsplit(self.url)
        return parts.scheme in ('http', 'https') and bool(parts.netloc)

    def configured(self) -> bool:
        return bool(self.url and self.machine_id and self.password) and self.url_ok()

    def same_as(self, url: str, machine_id: str, password: str,
                verify: bool) -> bool:
        """True when the add-on options still match this client."""
        return ((url or '').strip().rstrip('/') == self.url
                and (machine_id or '').strip() == self.machine_id
                and (password or '') == self.password
                and bool(verify) == self.verify)

    # -- plumbing ------------------------------------------------------------

    def _api(self, path: str) -> str:
        return f'{self.url}/v1{path}'

    def _login(self) -> str:
        body = {'machine_id': self.machine_id,
                'password': self.password,
                'scenarios': []}
        try:
            r = http.post(self._api('/watchers/login'), json=body,
                          timeout=self.timeout, verify=self.verify)
        except http.RequestException:
            raise LapiError('unreachable') from None
        if r.status_code in (401, 403):
            raise LapiError('auth_failed', r.status_code)
        if r.status_code != 200:
            raise LapiError('http_error', r.status_code)
        try:
            data = r.json()
        except ValueError:
            raise LapiError('bad_response', r.status_code) from None
        token = (data or {}).get('token') or ''
        if not token:
            raise LapiError('bad_response', r.status_code)
        exp = _parse_expire((data or {}).get('expire') or '')
        self._jwt = token
        self._jwt_exp = exp if exp > time.time() else time.time() + _FALLBACK_TTL
        return token

    def _token(self, force: bool = False) -> str:
        if not self.configured():
            raise LapiError('not_configured')
        with self._lock:
            if force or not self._jwt or time.time() >= self._jwt_exp - _LOGIN_LEEWAY:
                return self._login()
            return self._jwt

    def _invalidate(self) -> None:
        with self._lock:
            self._jwt = ''
            self._jwt_exp = 0.0

    def _call(self, method: str, path: str, params: dict | None = None,
              body=None, auth: bool = True):
        if auth and not self.configured():
            raise LapiError('not_configured')
        if not self.url_ok():
            raise LapiError('bad_url')

        attempts = 2 if auth else 1
        for attempt in range(attempts):
            headers = {'User-Agent': 'crowdpanel/1.0'}
            if auth:
                headers['Authorization'] = 'Bearer ' + self._token(force=attempt > 0)
            try:
                r = http.request(method, self._api(path), params=params, json=body,
                                 headers=headers, timeout=self.timeout,
                                 verify=self.verify)
            except http.RequestException:
                raise LapiError('unreachable') from None

            if auth and r.status_code in (401, 403) and attempt == 0:
                self._invalidate()
                continue
            if r.status_code in (401, 403):
                raise LapiError('auth_failed', r.status_code)
            if r.status_code == 404:
                return None
            if r.status_code >= 400:
                raise LapiError('http_error', r.status_code)
            if r.status_code == 204 or not (r.content or b'').strip():
                return None
            try:
                return r.json()
            except ValueError:
                raise LapiError('bad_response', r.status_code) from None
        raise LapiError('auth_failed')

    # -- reads ---------------------------------------------------------------

    # The two endpoints filter asymmetrically, verified against a live LAPI:
    #   GET    /v1/alerts     honours scope+value and origin; ip= and range=
    #                         are ignored and quietly return everything.
    #   DELETE /v1/decisions  honours ip= and range=; scope+value answers 500.
    # Hence reads go through scope+value, deletes through ip/range or an id.
    _ALERT_FILTERS = ('scope', 'value', 'scenario', 'since', 'until',
                      'simulated', 'decision_type', 'origin',
                      'has_active_decision')

    def _alert_params(self, filters: dict, limit: int) -> dict:
        params: dict = {'limit': max(1, min(int(limit or 100), 1000))}
        for key in self._ALERT_FILTERS:
            val = filters.get(key)
            if val not in (None, ''):
                params[key] = val
        return params

    def _cache_get(self, key: str):
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry and time.time() - entry[0] < ALERT_CACHE_TTL:
                return entry[1]
            self._cache.pop(key, None)
        return None

    def _cache_put(self, key: str, value) -> None:
        with self._cache_lock:
            if len(self._cache) > 16:
                self._cache.clear()
            self._cache[key] = (time.time(), value)

    def drop_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def list_alerts(self, limit: int = 100, **filters) -> list:
        params = self._alert_params(filters, limit)
        key = repr(sorted(params.items()))
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        data = self._call('GET', '/alerts', params=params)
        rows = data if isinstance(data, list) else []
        self._cache_put(key, rows)
        return rows

    def get_alert(self, alert_id) -> dict | None:
        try:
            ident = int(alert_id)
        except (TypeError, ValueError):
            raise ValidationError('bad_id') from None
        data = self._call('GET', f'/alerts/{ident}')
        return data if isinstance(data, dict) else None

    def list_decisions(self, limit: int = 100, **filters) -> list:
        """Active decisions, flattened out of the alerts that carry them."""
        filters = dict(filters)
        filters['has_active_decision'] = 'true'
        rows = []
        for alert in self.list_alerts(limit=limit, **filters):
            if not isinstance(alert, dict):
                continue
            src = alert.get('source') or {}
            for dec in (alert.get('decisions') or []):
                if not isinstance(dec, dict):
                    continue
                rows.append({
                    'id': dec.get('id'),
                    'value': dec.get('value') or '',
                    'scope': dec.get('scope') or '',
                    'type': dec.get('type') or '',
                    'duration': dec.get('duration') or '',
                    'until': dec.get('until') or '',
                    'origin': dec.get('origin') or '',
                    'scenario': dec.get('scenario') or alert.get('scenario') or '',
                    'simulated': bool(dec.get('simulated')),
                    'alert_id': alert.get('id'),
                    'created_at': alert.get('created_at') or alert.get('start_at') or '',
                    'country': src.get('cn') or '',
                    'as_name': src.get('as_name') or '',
                    'as_number': src.get('as_number') or '',
                    'source_ip': src.get('ip') or src.get('value') or '',
                })
        return rows

    def decisions_for(self, term: str, limit: int = 1000) -> tuple[tuple, list]:
        """Every active decision that applies to an address or range.

        The LAPI matches scope+value literally and runs no containment test, so
        a covering range has to be found here — the same result cscli shows for
        `decisions list --ip`.
        """
        kind = is_ip_or_range(term)
        if not kind:
            raise ValidationError('bad_ip')
        scope = 'Ip' if kind[0] == 'ip' else 'Range'
        rows = self.list_decisions(limit=limit, scope=scope, value=kind[1])
        seen = {r.get('id') for r in rows}

        net = ipaddress.ip_network(kind[1], strict=False)
        for row in self.list_decisions(limit=limit, scope='Range'):
            if row.get('id') in seen:
                continue
            try:
                covering = ipaddress.ip_network(row['value'], strict=False)
            except ValueError:
                continue
            if covering.version == net.version and net.subnet_of(covering):
                rows.append(row)
                seen.add(row.get('id'))
        return kind, rows

    # The swagger marks the allowlist routes as unauthenticated, but a running
    # CrowdSec answers 401 without a token — so they get the JWT like the rest.
    def decision_stats(self, limit: int = ALERT_FETCH_LIMIT) -> dict:
        """Counts over every active decision, without building a row per entry."""
        from collections import Counter
        by_type, by_country = Counter(), Counter()
        by_scenario, by_origin = Counter(), Counter()
        total = 0
        for alert in self.list_alerts(limit=limit, has_active_decision='true'):
            if not isinstance(alert, dict):
                continue
            country = (alert.get('source') or {}).get('cn') or ''
            fallback = alert.get('scenario') or ''
            for dec in (alert.get('decisions') or []):
                if not isinstance(dec, dict):
                    continue
                total += 1
                if dec.get('type'):
                    by_type[dec['type']] += 1
                if dec.get('origin'):
                    by_origin[dec['origin']] += 1
                scenario = dec.get('scenario') or fallback
                if scenario:
                    by_scenario[scenario] += 1
                if country:
                    by_country[country] += 1
        return {
            'total': total,
            'by_type': by_type.most_common(),
            'by_origin': by_origin.most_common(10),
            'top_countries': by_country.most_common(10),
            'top_scenarios': by_scenario.most_common(10),
        }

    def allowlists(self) -> list:
        data = self._call('GET', '/allowlists', params={'with_content': 'true'})
        if isinstance(data, dict):
            data = data.get('items') or data.get('allowlists') or []
        return data if isinstance(data, list) else []

    def allowlist_check(self, ip: str) -> dict | None:
        kind = is_ip_or_range(ip)
        if not kind:
            raise ValidationError('bad_ip')
        data = self._call('GET', '/allowlists/check/' + quote(kind[1], safe=''))
        return data if isinstance(data, dict) else None

    def allowlist_status(self, term: str) -> dict:
        """Is this address exempt from decisions, and through which list?

        /allowlists/check answers an empty object on some versions, which says
        nothing. Then the lists are walked directly, so the answer is always a
        real yes or no instead of a shrug.
        """
        kind = is_ip_or_range(term)
        if not kind:
            raise ValidationError('bad_ip')
        raw = self.allowlist_check(kind[1])
        if isinstance(raw, dict):
            for key in ('allowed', 'Allowed'):
                if isinstance(raw.get(key), bool):
                    return {'allowed': raw[key], 'lists': []}

        net = ipaddress.ip_network(kind[1], strict=False)
        hits = []
        for entry in self.allowlists():
            if not isinstance(entry, dict):
                continue
            name = entry.get('name') or entry.get('Name') or ''
            for item in (entry.get('items') or entry.get('Items') or []):
                value = item.get('value') if isinstance(item, dict) else item
                try:
                    allowed = ipaddress.ip_network(str(value), strict=False)
                except (ValueError, TypeError):
                    continue
                if allowed.version == net.version and net.subnet_of(allowed):
                    hits.append(name or str(value))
                    break
        return {'allowed': bool(hits), 'lists': hits}

    def ping(self) -> dict:
        """Status for the header pill. Never raises."""
        if not self.url:
            return {'ok': False, 'code': 'no_url'}
        if not self.url_ok():
            return {'ok': False, 'code': 'bad_url'}
        if not self.configured():
            return {'ok': False, 'code': 'not_configured'}
        started = time.time()
        try:
            self.list_alerts(limit=1)
        except LapiError as e:
            return {'ok': False, 'code': e.code, 'status': e.status}
        return {'ok': True, 'code': 'ok', 'ms': int((time.time() - started) * 1000)}

    # -- writes --------------------------------------------------------------

    def add_decision(self, scope: str, value: str, dtype: str,
                     duration: str, reason: str = '') -> dict:
        scope = normalize_scope(scope)
        value = normalize_value(scope, value)
        dtype = normalize_type(dtype)
        duration = normalize_duration(duration)
        reason = (reason or '').strip()[:200]

        now = datetime.now(timezone.utc).isoformat()
        label = f"manual '{dtype}' from '{ACTOR}'"
        alert = {
            'scenario': label,
            'scenario_hash': '',
            'scenario_version': '',
            'message': reason or label,
            'events_count': 1,
            'start_at': now,
            'stop_at': now,
            'capacity': 0,
            'leakspeed': '0',
            'simulated': False,
            'events': [],
            'labels': None,
            'source': _source_for(scope, value),
            'decisions': [{
                'duration': duration,
                'origin': ORIGIN,
                'scenario': label,
                'scope': scope,
                'type': dtype,
                'value': value,
            }],
        }
        result = self._call('POST', '/alerts', body=[alert])
        self.drop_cache()
        log.info("decision added: %s %s %s for %s", dtype, scope, value, duration)
        return {'scope': scope, 'value': value, 'type': dtype,
                'duration': duration, 'result': result}

    # scope+value is deliberately absent: the LAPI answers 500 for it on every
    # scope. Use ip/range, or delete the decision by its id.
    _DELETE_FILTERS = ('type', 'ip', 'range', 'scenario', 'origin')

    def delete_decisions(self, **filters) -> int:
        params = {k: v for k, v in filters.items()
                  if k in self._DELETE_FILTERS and v not in (None, '')}
        if not params:
            raise ValidationError('no_filter')
        data = self._call('DELETE', '/decisions', params=params)
        self.drop_cache()
        count = _deleted_count(data)
        log.info("decisions deleted: %d (%s)", count,
                 ', '.join(f'{k}={v}' for k, v in sorted(params.items())))
        return count

    def delete_by_target(self, scope: str, value: str) -> int:
        """Lift every decision for one exact target, translated to the filters
        the delete endpoint actually accepts."""
        scope = normalize_scope(scope)
        value = normalize_value(scope, value)
        if scope == 'Ip':
            return self.delete_decisions(ip=value)
        if scope == 'Range':
            return self.delete_decisions(range=value)
        # Country and AS have no working filter — the caller must pass a
        # decision id, which every listed row carries.
        raise ValidationError('unsupported_filter')

    def delete_decision(self, decision_id) -> int:
        try:
            ident = int(decision_id)
        except (TypeError, ValueError):
            raise ValidationError('bad_id') from None
        data = self._call('DELETE', f'/decisions/{ident}')
        self.drop_cache()
        count = _deleted_count(data)
        log.info("decision %d deleted (%d)", ident, count)
        return count


def _deleted_count(data) -> int:
    """LAPI answers with {"nbDeleted": "3"} — a string."""
    if isinstance(data, dict):
        try:
            return int(data.get('nbDeleted') or 0)
        except (TypeError, ValueError):
            return 0
    return 0
