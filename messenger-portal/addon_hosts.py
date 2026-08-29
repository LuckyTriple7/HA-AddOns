#!/usr/bin/env python3
"""Loest Add-on-Slugs in ihre Container-Hostnamen auf (Supervisor-API).

Warum nicht einfach die IP: Container-IPs (172.30.33.x) wechseln bei jedem
Start, und sobald ein Add-on seinen Host-Port nicht mehr veroeffentlicht, ist
der Umweg ueber den HA-Host ohnehin zu. Der Hostname (z. B. 424ccef4-whatsapp)
bleibt stabil und funktioniert im internen hassio-Netz ohne Port-Mapping.

Gefragt wird nur GET /addons/self/info. Daraus laesst sich der
Repository-Praefix des Portals ableiten ("424ccef4-messenger-portal" minus dem
eigenen Slug) und damit der Hostname der Geschwister-Add-ons bilden - sie
stammen aus demselben Repository.

GET /addons waere die genauere Auskunft, listet naemlich jedes Add-on mit
seinem Hostnamen. Die Rolle "default" darf ihn aber nicht, und jeder Versuch
hinterlaesst zwei Zeilen im Supervisor-Log:

    WARNING [supervisor.api.middleware.security] /addons no role for <slug>
    ERROR   [supervisor.api.middleware.security] Invalid token for access /addons

Dem Portal dafuer hassio_role: manager zu geben (duerfte dann Add-ons starten,
stoppen, installieren) waere ein schlechter Tausch. Wer ein Messenger-Add-on
aus einem anderen Repository betreibt, traegt den Host von Hand in
internal_host ein.

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

# (Zeitpunkt, Praefix oder '')
_cache: tuple[float, str] | None = None


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


def _own_prefix() -> str:
    """Repository-Praefix aus dem eigenen Hostnamen, z. B. "424ccef4"."""
    info = _get('/addons/self/info').get('data') or {}
    hostname = str(info.get('hostname') or '')
    own = _short(str(info.get('slug') or ''))
    if not hostname or not own:
        return ''
    suffix = '-' + own.replace('_', '-')
    return hostname[:-len(suffix)] if hostname.endswith(suffix) else ''


def lookup(force: bool = False) -> str:
    """Repository-Praefix des Portals, oder '' wenn nicht ermittelbar."""
    global _cache
    now = time.time()
    if not force and _cache is not None:
        ts, prefix = _cache
        if now - ts < (_CACHE_TTL_OK if prefix else _CACHE_TTL_ERR):
            return prefix
    try:
        prefix = _own_prefix()
    except Exception:
        prefix = ''
    _cache = (now, prefix)
    return prefix


def resolve_host(slug: str, fallback: str, override: str = '') -> str:
    """Zielhost fuer ein Add-on.

    Reihenfolge: ausdruecklich gesetzter internal_host, aus dem eigenen
    Praefix gebildeter Container-Name, HA-Host als Notnagel.
    """
    if override:
        return override
    slug = slug.lower()
    if not slug:
        return fallback
    prefix = lookup()
    return f'{prefix}-{slug}' if prefix else fallback


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
