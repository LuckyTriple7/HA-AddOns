#!/usr/bin/env python3
"""Loest Add-on-Slugs in ihre Container-Hostnamen auf (Supervisor-API).

Warum nicht einfach die IP: Container-IPs (172.30.33.x) wechseln bei jedem
Start, und sobald ein Add-on seinen Host-Port nicht mehr veroeffentlicht, ist
der Umweg ueber den HA-Host ohnehin zu. Der Hostname (z. B. 424ccef4-whatsapp)
bleibt stabil und funktioniert im internen hassio-Netz ohne Port-Mapping.

Zwei Wege, absichtlich in dieser Reihenfolge:

1. GET /addons listet alle installierten Add-ons mit ihrem Hostnamen. Das ist
   die genaue Auskunft, verlangt aber je nach Supervisor-Fassung eine hoehere
   Rolle als die Voreinstellung. Scheitert der Aufruf, ist das kein Fehler.
2. GET /addons/self/info darf die Default-Rolle immer. Daraus laesst sich der
   Repository-Praefix des Portals ableiten ("424ccef4-messenger-portal" minus
   dem eigenen Slug) und damit der Hostname der Geschwister-Add-ons bilden.
   Gilt, solange sie aus demselben Repository stammen - hier der Fall.

Der Praefix ist der Hash des Repositories und unterscheidet sich pro
Installation. Er darf nirgends fest verdrahtet werden.
"""
import json
import os
import time
import urllib.request

SUPERVISOR = 'http://supervisor'
_CACHE_TTL_OK = 600.0   # Hostnamen aendern sich praktisch nie
_CACHE_TTL_ERR = 30.0   # Fehlschlag: bald erneut versuchen

# (Zeitpunkt, {slug: hostname}, Praefix oder '')
_cache: tuple[float, dict[str, str], str] | None = None


def _get(path: str) -> dict:
    token = os.environ.get('SUPERVISOR_TOKEN', '')
    if not token:
        return {}
    req = urllib.request.Request(
        SUPERVISOR + path, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read()) or {}


def _short(slug: str) -> str:
    """Supervisor-Slug ist "<repo-hash>_<slug>" - der hintere Teil zaehlt."""
    return (slug.split('_', 1)[1] if '_' in slug else slug).lower()


def _from_list() -> dict[str, str]:
    data = (_get('/addons').get('data') or {}).get('addons') or []
    hosts: dict[str, str] = {}
    for addon in data:
        slug = str(addon.get('slug') or '')
        hostname = str(addon.get('hostname') or '')
        if slug and hostname:
            hosts.setdefault(_short(slug), hostname)
    return hosts


def _own_prefix() -> str:
    """Repository-Praefix aus dem eigenen Hostnamen, z. B. "424ccef4"."""
    info = _get('/addons/self/info').get('data') or {}
    hostname = str(info.get('hostname') or '')
    own = _short(str(info.get('slug') or ''))
    if not hostname or not own:
        return ''
    suffix = '-' + own.replace('_', '-')
    return hostname[:-len(suffix)] if hostname.endswith(suffix) else ''


def _load() -> tuple[dict[str, str], str]:
    hosts: dict[str, str] = {}
    prefix = ''
    try:
        hosts = _from_list()
    except Exception:
        pass
    try:
        prefix = _own_prefix()
    except Exception:
        pass
    return hosts, prefix


def lookup(force: bool = False) -> tuple[dict[str, str], str]:
    """({Kurz-Slug: Hostname}, Repository-Praefix). Beides kann leer sein."""
    global _cache
    now = time.time()
    if not force and _cache is not None:
        ts, hosts, prefix = _cache
        ttl = _CACHE_TTL_OK if (hosts or prefix) else _CACHE_TTL_ERR
        if now - ts < ttl:
            return hosts, prefix
    hosts, prefix = _load()
    _cache = (now, hosts, prefix)
    return hosts, prefix


def resolve_host(slug: str, fallback: str, override: str = '') -> str:
    """Zielhost fuer ein Add-on.

    Reihenfolge: ausdruecklich gesetzter internal_host, exakter Hostname aus
    der Add-on-Liste, aus dem eigenen Praefix gebildeter Name, HA-Host.
    """
    if override:
        return override
    slug = slug.lower()
    if not slug:
        return fallback
    hosts, prefix = lookup()
    if slug in hosts:
        return hosts[slug]
    if prefix:
        return f'{prefix}-{slug}'
    return fallback


def nameservers(default: str = '172.30.32.3') -> str:
    """Nameserver aus /etc/resolv.conf fuer die nginx-resolver-Direktive."""
    found = []
    try:
        with open('/etc/resolv.conf') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == 'nameserver' and ':' not in parts[1]:
                    found.append(parts[1])
    except Exception:
        pass
    return ' '.join(found) if found else default
