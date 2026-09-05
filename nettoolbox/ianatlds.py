"""IANA's own list of every top-level domain, for the domain-availability
picker: validates a typed TLD before it ever reaches Cloudflare/DENIC/EURid,
and backs the search field so a wrong guess is caught before the request goes
out at all.

Public-domain registry data, not a licensed dataset like the tech-detection
add-on (wapimport.py) -- no toggle needed, on by default. Still fetched at
runtime and cached in the data directory rather than shipped in the image:
the list changes (new gTLDs, the odd retirement) and baking in a snapshot
would just go stale. Refreshed at most once a day; a few hundred KB of text,
nothing that needs finer-grained staleness than that.
"""

import json
import logging
import os
import threading
import time

from netcore import Context, ProbeError, http_get

log = logging.getLogger(__name__)

SOURCE_URL = 'https://data.iana.org/TLD/tlds-alpha-by-domain.txt'
MAX_BYTES = 512 * 1024
STALE_AFTER = 24 * 3600  # einmal täglich reicht -- neue TLDs sind kein Minutentakt

_path = ''
_lock = threading.Lock()
_cache: dict = {'tlds': [], 'fetched': 0.0, 'error': ''}


def init(data_dir: str) -> None:
    global _path
    _path = os.path.join(data_dir, 'iana_tlds.json')
    _load_from_disk()


def _load_from_disk() -> None:
    try:
        with open(_path, encoding='utf-8') as f:
            data = json.load(f)
        with _lock:
            _cache['tlds'] = data.get('tlds') or []
            _cache['fetched'] = float(data.get('fetched') or 0.0)
    except FileNotFoundError:
        pass
    except Exception:
        log.warning("iana_tlds.json could not be read")


def needs_update() -> bool:
    with _lock:
        return (time.time() - _cache['fetched']) > STALE_AFTER


def get_tlds() -> list:
    with _lock:
        return list(_cache['tlds'])


def is_valid(tld: str) -> bool:
    """True if the list is unavailable too -- an empty cache (offline first
    boot) must not block every check; it only means nothing gets validated
    yet, same as before this existed."""
    with _lock:
        tlds = _cache['tlds']
    return (not tlds) or tld.lower() in tlds


def status() -> dict:
    with _lock:
        return {'count': len(_cache['tlds']), 'fetched': _cache['fetched'],
                'error': _cache['error']}


def fetch() -> bool:
    """One synchronous download+parse. Returns whether it succeeded --
    called from a background thread, so nothing here talks to the request
    that happened to trigger it."""
    ctx = Context(http_timeout=15.0, user_agent='NetToolbox')
    try:
        resp = http_get(ctx, SOURCE_URL, max_bytes=MAX_BYTES, accept='text/plain,*/*')
    except ProbeError as e:
        with _lock:
            _cache['error'] = e.code
        log.warning("IANA TLD list fetch failed: %s", e.code)
        return False
    if resp.get('status') != 200:
        with _lock:
            _cache['error'] = f"http_{resp.get('status')}"
        return False

    # One TLD per line, uppercase, a leading "# Version ..." comment line.
    # Kept lowercase and as-is otherwise -- including the xn-- (IDN) entries;
    # dropping them would just make a Cyrillic/CJK TLD unfindable in the
    # search box, and check_availability() never sees more than what the
    # user actually typed or picked.
    tlds = sorted({line.strip().lower() for line in resp.get('body', '').splitlines()
                  if line.strip() and not line.startswith('#')})
    if not tlds:
        with _lock:
            _cache['error'] = 'empty_list'
        return False

    with _lock:
        _cache['tlds'] = tlds
        _cache['fetched'] = time.time()
        _cache['error'] = ''
    try:
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        with open(_path, 'w', encoding='utf-8') as f:
            json.dump({'tlds': tlds, 'fetched': _cache['fetched']}, f)
    except Exception:
        log.warning("iana_tlds.json could not be saved")
    log.info("IANA TLD list refreshed: %d entries", len(tlds))
    return True
