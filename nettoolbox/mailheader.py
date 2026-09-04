"""Analyse eines eingefügten Mail-Kopfes.

Beantwortet die zwei Fragen, die man einem fremden Mailserver nicht stellen
kann: *welchen Weg ist diese Mail gegangen, und wo hat sie gehangen?* sowie
*was hat die Gegenseite zu SPF, DKIM und DMARC festgestellt?*

Rein lokal — hier wird nichts abgefragt und nichts gesendet. Der Kopf, den
jemand einfügt, kann Adressen, interne Hostnamen und Betreffzeilen
enthalten; er wird verarbeitet und wieder vergessen, nicht gespeichert.

Gelesen wird mit dem `email`-Paket der Standardbibliothek, also demselben
Parser, den Python-Mailsoftware ohnehin benutzt.
"""

import re
from email import message_from_string, utils
from email.policy import default as default_policy

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'

MAX_HEADER_BYTES = 256 * 1024
# Ein Sprung, der länger als das dauert, ist die Verzögerung, nach der man
# sucht, wenn eine Mail "erst Stunden später" ankam.
SLOW_HOP_SECONDS = 60
VERY_SLOW_HOP_SECONDS = 600

_RECEIVED_FROM = re.compile(r'\bfrom\s+([^\s;]+)', re.I)
_RECEIVED_BY = re.compile(r'\bby\s+([^\s;]+)', re.I)
_RECEIVED_WITH = re.compile(r'\bwith\s+([A-Za-z0-9/._-]+)', re.I)
_RECEIVED_FOR = re.compile(r'\bfor\s+<([^>]+)>', re.I)
_RECEIVED_IP = re.compile(r'[\[(]((?:\d{1,3}\.){3}\d{1,3}|[0-9a-f:]{6,})[\])]', re.I)
_AUTH_METHOD = re.compile(r'\b(spf|dkim|dmarc|arc|compauth)\s*=\s*([a-z]+)', re.I)
_DKIM_TAG = re.compile(r'\b([a-z]+)\s*=\s*([^;]+)')


def _finding(level: str, code: str, **args) -> dict:
    return {'level': level, 'code': code, 'args': args}


def _worst(findings: list) -> str:
    for level in (FAIL, WARN):
        if any(f['level'] == level for f in findings):
            return level
    return OK


def _domain_of(address: str) -> str:
    address = (address or '').strip().strip('<>')
    return address.rsplit('@', 1)[1].lower().strip('>') if '@' in address else ''


def _parse_received(value: str) -> dict:
    """Ein Received-Kopf in seine Bestandteile.

    Das Format ist in RFC 5321 nur lose vorgegeben, und jeder Mailserver
    schreibt es etwas anders — deshalb wird gesucht, nicht streng geparst.
    Was fehlt, bleibt leer, statt den ganzen Sprung zu verwerfen.
    """
    text = ' '.join(value.split())
    head, _, stamp = text.rpartition(';')
    hop = {'from': '', 'by': '', 'with': '', 'for': '', 'ip': '',
           'date': stamp.strip(), 'ts': None, 'raw': text}
    for key, pattern in (('from', _RECEIVED_FROM), ('by', _RECEIVED_BY),
                         ('with', _RECEIVED_WITH), ('for', _RECEIVED_FOR)):
        m = pattern.search(head or text)
        if m:
            hop[key] = m.group(1).strip().rstrip(',')
    m = _RECEIVED_IP.search(head or text)
    if m:
        hop['ip'] = m.group(1)
    if hop['date']:
        try:
            parsed = utils.parsedate_to_datetime(hop['date'])
            hop['ts'] = parsed.timestamp()
            hop['date'] = parsed.isoformat()
        except (TypeError, ValueError):
            hop['ts'] = None
    return hop


def _parse_auth_results(values: list) -> dict:
    """{'spf': 'pass', 'dkim': 'fail', ...} über alle Authentication-Results."""
    out = {}
    for value in values:
        for method, verdict in _AUTH_METHOD.findall(value or ''):
            # Die erste Nennung gewinnt: Kopfzeilen stehen in umgekehrter
            # Reihenfolge, die oberste stammt vom letzten (empfangenden)
            # Server -- und dessen Urteil ist das, was gezählt hat.
            out.setdefault(method.lower(), verdict.lower())
    return out


def _dkim_signatures(values: list) -> list:
    out = []
    for value in values:
        tags = {k.strip().lower(): v.strip()
                for k, v in _DKIM_TAG.findall(' '.join((value or '').split()))}
        out.append({'domain': tags.get('d', ''), 'selector': tags.get('s', ''),
                    'algorithm': tags.get('a', ''),
                    'canonicalisation': tags.get('c', '')})
    return out


def analyse(raw: str) -> dict:
    text = (raw or '').strip()
    if not text:
        raise ValueError('empty_header')
    if len(text.encode('utf-8', 'ignore')) > MAX_HEADER_BYTES:
        raise ValueError('header_too_large')

    message = message_from_string(text, policy=default_policy)

    def header(name: str) -> str:
        try:
            value = message.get(name, '')
        except Exception:  # noqa: BLE001 — beschädigte Kopfzeilen sind normal
            return ''
        return ' '.join(str(value).split())

    def headers(name: str) -> list:
        try:
            return [str(v) for v in message.get_all(name, [])]
        except Exception:  # noqa: BLE001
            return []

    hops = [_parse_received(v) for v in headers('Received')]
    # Received-Kopfzeilen stehen neueste zuerst; für einen Weg von A nach B
    # ist die umgekehrte Reihenfolge die, die man lesen will.
    hops.reverse()
    for index, hop in enumerate(hops):
        previous = hops[index - 1]['ts'] if index else None
        hop['delay'] = (round(hop['ts'] - previous, 1)
                        if hop['ts'] and previous else None)

    auth = _parse_auth_results(headers('Authentication-Results'))
    if 'spf' not in auth:
        received_spf = header('Received-SPF')
        if received_spf:
            auth['spf'] = received_spf.split()[0].lower()

    from_addr = header('From')
    return_path = header('Return-Path')
    reply_to = header('Reply-To')
    from_domain = _domain_of(utils.parseaddr(from_addr)[1])
    return_domain = _domain_of(utils.parseaddr(return_path)[1])
    signatures = _dkim_signatures(headers('DKIM-Signature'))

    total = None
    stamped = [h['ts'] for h in hops if h['ts']]
    if len(stamped) >= 2:
        total = round(max(stamped) - min(stamped), 1)

    result = {
        'from': from_addr, 'to': header('To'), 'cc': header('Cc'),
        'subject': header('Subject'), 'date': header('Date'),
        'message_id': header('Message-ID'), 'return_path': return_path,
        'reply_to': reply_to, 'from_domain': from_domain,
        'return_domain': return_domain,
        'mailer': header('X-Mailer') or header('User-Agent'),
        'list_unsubscribe': header('List-Unsubscribe'),
        'spam_status': header('X-Spam-Status') or header('X-Spam-Level'),
        'auth': auth, 'dkim_signatures': signatures,
        'hops': hops, 'hop_count': len(hops), 'total_seconds': total,
        'findings': [],
    }
    findings = result['findings']

    for method, label in (('spf', 'SPF'), ('dkim', 'DKIM'), ('dmarc', 'DMARC')):
        verdict = auth.get(method)
        if not verdict:
            findings.append(_finding(INFO, 'hdr_auth_missing', method=label))
        elif verdict == 'pass':
            findings.append(_finding(OK, 'hdr_auth_pass', method=label))
        elif verdict in ('fail', 'permerror', 'hardfail'):
            findings.append(_finding(FAIL, 'hdr_auth_fail', method=label,
                                     verdict=verdict))
        elif verdict in ('none', 'neutral'):
            findings.append(_finding(INFO, 'hdr_auth_none', method=label,
                                     verdict=verdict))
        else:
            findings.append(_finding(WARN, 'hdr_auth_other', method=label,
                                     verdict=verdict))

    if from_domain and return_domain and from_domain != return_domain:
        # Genau die Abweichung, die DMARC als fehlende Ausrichtung wertet.
        findings.append(_finding(WARN, 'hdr_return_path_mismatch',
                                 sender=from_domain, envelope=return_domain))
    if reply_to and _domain_of(utils.parseaddr(reply_to)[1]) not in ('', from_domain):
        findings.append(_finding(WARN, 'hdr_reply_to_differs',
                                 reply=_domain_of(utils.parseaddr(reply_to)[1])))
    if not result['message_id']:
        findings.append(_finding(WARN, 'hdr_no_message_id'))
    if not hops:
        findings.append(_finding(WARN, 'hdr_no_received'))
    else:
        slow = [h for h in hops
                if h['delay'] is not None and h['delay'] >= SLOW_HOP_SECONDS]
        worst = max((h['delay'] for h in slow), default=0)
        if worst >= VERY_SLOW_HOP_SECONDS:
            findings.append(_finding(WARN, 'hdr_hop_very_slow',
                                     seconds=int(worst), count=len(slow)))
        elif slow:
            findings.append(_finding(INFO, 'hdr_hop_slow', seconds=int(worst),
                                     count=len(slow)))
        else:
            findings.append(_finding(OK, 'hdr_transit_ok',
                                     hops=len(hops),
                                     seconds=int(total or 0)))
    if signatures and not any(s['domain'] for s in signatures):
        findings.append(_finding(INFO, 'hdr_dkim_unparsed'))

    result['level'] = _worst(findings)
    return result
