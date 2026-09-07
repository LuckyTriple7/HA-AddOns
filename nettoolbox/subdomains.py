"""Subdomain-Suche über Certificate-Transparency-Logs (api.ctlogs.dev).

Wer eine Domain betreibt, kennt selten alle Namen darunter: ein Zertifikat
für vpn.example.com legt diesen Namen öffentlich und dauerhaft in den
CT-Logs ab, auch wenn er in keiner Zonendatei steht, die man gerade zur Hand
hat. Genau das listet dieser Aufruf -- eine Bestandsaufnahme dessen, was
über die eigene Domain öffentlich bekannt ist.

Warum ein fremder Dienst und keine eigene Auswertung: die CT-Logs selbst
sind Merkle-Bäume mit Millionen Einträgen pro Tag; sie nach einer Domain zu
durchsuchen heißt, sie vorher komplett zu indizieren. api.ctlogs.dev tut
genau das und beantwortet die Frage in ~50 ms, ohne Schlüssel und ohne
Registrierung. Die Alternative crt.sh liefert dieselben Daten, aber je
Zertifikat statt je Name, ohne Auflösungsstatus und mit deutlich mehr
Zeitüberschreitungen.

Grenzen, die im Ergebnis auch benannt werden:
  * Ohne Schlüssel deckt die Antwort die letzten 90 Tage ab (gültige plus
    kürzlich abgelaufene Zertifikate), nicht das ganze Archiv seit 2013.
  * Namen ohne Zertifikat tauchen nie auf. Ein interner Host, der nie ein
    öffentliches Zertifikat bekam, bleibt unsichtbar -- das hier ist keine
    Zonendatei und ersetzt keine.
  * Der Dienst taktet anonyme Aufrufer auf eine Anfrage je Sekunde; die
    Seitenfolge unten hält sich daran, statt in ein 429 zu laufen.
"""

import logging
import time
import urllib.parse

import requests

from netcore import Context, ProbeError

log = logging.getLogger(__name__)

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'

API_BASE = 'https://api.ctlogs.dev/v1/hosts/'
REQUEST_TIMEOUT = 20
# 100 Zeilen je Seite. Fünf Seiten sind bei einer Anfrage je Sekunde rund
# fünf Sekunden Wartezeit -- darüber hinaus gehört die Frage in ein Werkzeug
# mit Schlüssel, nicht in eine Weboberfläche, die auf eine Antwort wartet.
MAX_PAGES = 5
PAGE_PAUSE = 1.1
# Der Dienst nennt bei 429 selbst die Wartezeit. Gedeckelt, damit eine
# unglückliche Antwort die Prüfung nicht minutenlang festhält.
RETRY_AFTER_MAX = 5.0

# Auflösungsstatus, den der Dienst mitliefert. 'ok' heißt: der Name zeigt
# gerade irgendwohin. Alles andere heißt es nicht -- und das ist der
# interessante Teil, siehe _findings.
LIVE_DNS = 'ok'


def _finding(level: str, code: str, **args) -> dict:
    return {'level': level, 'code': code, 'args': args}


def _worst(findings: list) -> str:
    for level in (FAIL, WARN):
        if any(f['level'] == level for f in findings):
            return level
    return OK


def _fetch_page(domain: str, cursor: str, api_key: str) -> dict:
    """Eine Seite. Der Schlüssel geht als Kopfzeile raus, nicht als
    Abfrageparameter: sonst stünde er in jeder Protokollzeile über diesen
    Abruf -- auch in der Konsole des Add-ons."""
    url = API_BASE + urllib.parse.quote(domain, safe='')
    headers = {'Accept': 'application/json'}
    if api_key:
        headers['Authorization'] = 'Bearer ' + api_key
    params = {'after': cursor} if cursor else None

    for attempt in (1, 2):
        try:
            resp = requests.get(url, headers=headers, params=params,
                                timeout=REQUEST_TIMEOUT)
        except requests.exceptions.Timeout:
            raise ProbeError('ctlogs_timeout', domain)
        except requests.exceptions.RequestException as e:
            raise ProbeError('ctlogs_unreachable', type(e).__name__)

        if resp.status_code == 429 and attempt == 1:
            # Taktbremse, keine Ablehnung: der Dienst sagt selbst, wie lange
            # zu warten ist, und berechnet diesen Versuch nicht.
            try:
                wait = float(resp.headers.get('retry-after', '1'))
            except (TypeError, ValueError):
                wait = 1.0
            time.sleep(min(max(wait, 0.5), RETRY_AFTER_MAX))
            continue
        break

    if resp.status_code == 429:
        raise ProbeError('ctlogs_rate_limited', domain)
    if resp.status_code == 401:
        raise ProbeError('ctlogs_bad_key')
    if resp.status_code == 503:
        # Ohne Schlüssel teilen sich alle anonymen Aufrufer einen kleinen
        # Pool; ist er voll, kommt nach zehn Sekunden Wartezeit ein 503.
        raise ProbeError('ctlogs_busy')
    if resp.status_code != 200:
        raise ProbeError('ctlogs_error', str(resp.status_code))
    try:
        data = resp.json()
    except ValueError:
        raise ProbeError('ctlogs_bad_response', str(resp.status_code))
    if not isinstance(data, dict):
        raise ProbeError('ctlogs_bad_response', 'shape')
    return data


def _row(raw: dict) -> dict:
    """Nur die Felder, die angezeigt werden -- der Rest der Antwort geht
    weder in den Verlauf noch in einen Schnappschuss."""
    host = str(raw.get('host') or '')[:253]
    addresses = [str(a)[:45] for a in (raw.get('a') or [])][:4]
    return {
        'host': host,
        'wildcard': host.startswith('*.'),
        'certs': int(raw.get('certs') or 0),
        'first_seen': str(raw.get('first_seen') or '')[:10],
        'last_seen': str(raw.get('last_seen') or '')[:10],
        'last_not_after': str(raw.get('last_not_after') or '')[:10],
        'dns': str(raw.get('dns') or '')[:20],
        'a': addresses,
    }


def _findings(hosts: list, truncated: bool, window_days: int,
              keyed: bool) -> list:
    findings = []
    if not hosts:
        # Kein Fehler: eine Domain ohne öffentliches Zertifikat im Fenster
        # ist ein gültiges Ergebnis, nur eben ein leeres.
        findings.append(_finding(INFO, 'sub_none', days=window_days))
        return findings

    findings.append(_finding(OK, 'sub_found', count=len(hosts)))

    wildcards = [h for h in hosts if h['wildcard']]
    if wildcards:
        findings.append(_finding(INFO, 'sub_wildcards', count=len(wildcards)))

    # Namen, für die ein Zertifikat ausgestellt wurde, die aber gerade
    # nirgendwohin zeigen. Bewusst als Hinweis und nicht als Mangel: das ist
    # regelmäßig ein vergessener Host oder ein abgeschalteter Dienst, aber
    # ebenso regelmäßig ein Name, der nur intern aufgelöst wird (Split-DNS).
    # Was hier steht, ist die Beobachtung -- die Bewertung bleibt beim Leser.
    dark = [h for h in hosts if not h['wildcard'] and h['dns'] and h['dns'] != LIVE_DNS]
    if dark:
        findings.append(_finding(INFO, 'sub_unresolved', count=len(dark),
                                 names=', '.join(h['host'] for h in dark[:5])))

    if truncated:
        findings.append(_finding(INFO, 'sub_truncated', count=len(hosts)))
    findings.append(_finding(INFO, 'sub_window' if keyed else 'sub_window_anon',
                             days=window_days))
    return findings


def check_subdomains(ctx: Context, domain: str) -> dict:
    """Alle Namen unter einer Domain, die je in einem Zertifikat standen."""
    domain = (domain or '').strip().lower().strip('.')
    if not domain:
        raise ProbeError('empty_target')

    api_key = str(getattr(ctx, 'ctlogs_api_key', '') or '')
    started = time.monotonic()
    hosts, cursor, truncated = [], '', False
    window_days = 0
    pages = 0

    for page in range(MAX_PAGES):
        if page:
            # Takt einhalten, statt sich das 429 abzuholen und nachzufassen.
            time.sleep(PAGE_PAUSE)
        data = _fetch_page(domain, cursor, api_key)
        pages += 1
        window_days = int(data.get('history_window_days') or window_days)
        for raw in (data.get('hosts') or []):
            if isinstance(raw, dict) and raw.get('host'):
                hosts.append(_row(raw))
        cursor = str(data.get('next_cursor') or '')
        if not data.get('has_next') or not cursor:
            break
    else:
        truncated = True

    ms = int((time.monotonic() - started) * 1000)
    live = sum(1 for h in hosts if h['dns'] == LIVE_DNS)
    findings = _findings(hosts, truncated, window_days, bool(api_key))
    log.info("subdomains %s: %d hosts on %d page(s), %d live (%d ms)",
             domain, len(hosts), pages, live, ms)
    return {
        'domain': domain, 'hosts': hosts, 'count': len(hosts),
        'live': live, 'wildcards': sum(1 for h in hosts if h['wildcard']),
        'truncated': truncated, 'window_days': window_days,
        'keyed': bool(api_key), 'pages': pages, 'ms': ms,
        'findings': findings, 'level': _worst(findings),
    }
