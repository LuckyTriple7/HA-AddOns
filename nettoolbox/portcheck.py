"""Gezielter Portcheck und die IPv4/IPv6-Gegenüberstellung.

Kein Scanner: geprüft wird eine feste, kurze Liste bekannter Dienste auf
genau dem Host, den jemand eingibt — keine Netzbereiche, keine Portbereiche,
keine Bannergrabber. Das reicht für die Frage, die hier zählt ("läuft da,
was ich erwarte, und ist offen, was nicht offen sein sollte"), und es ist
kein Werkzeug, mit dem sich fremde Netze durchharken lassen.

Unterschieden werden drei Zustände, nicht zwei: **offen** (Verbindung kam
zustande), **geschlossen** (aktiv abgelehnt — es antwortet jemand) und
**gefiltert** (keine Antwort bis zum Zeitlimit — dazwischen steht eine
Firewall). Der Unterschied zwischen den letzten beiden ist bei der
Fehlersuche der ganze Punkt.

Die IPv4/IPv6-Gegenüberstellung prüft dieselben Dienste über beide
Adressfamilien nebeneinander. Ein Dienst, der nur über IPv4 antwortet,
fällt sonst nur sporadisch auf — nämlich immer dann, wenn ein Client IPv6
bevorzugt.
"""

import concurrent.futures
import socket

from netcore import Context, ProbeError, clean_host_or_ip, guard_target

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'

CONNECT_TIMEOUT = 3.0
MAX_WORKERS = 10

# Eigene Portangabe: mehr Verbindungen gleichzeitig und ein knapperes
# Zeitlimit, sonst dauert eine Reihe von 200 Ports quälend lange. Die Grenze
# hält das Ganze bei einer überschaubaren Wartezeit -- und verhindert, dass
# aus dem Werkzeug ein Vollscanner wird.
MANUAL_MAX_PORTS = 256
MANUAL_WORKERS = 40
MANUAL_TIMEOUT = 2.0

OPEN, CLOSED, FILTERED = 'open', 'closed', 'filtered'

# (Port, Dienst, gehört-hier-hin). Das dritte Feld sagt, ob ein offener Port
# bei einem Server im Internet erwartbar ist -- Datenbanken und Fernwartung
# sind es nicht, und genau die tauchen in Einbruchsberichten auf.
PORTS = (
    (21, 'FTP', False),
    (22, 'SSH', True),
    (25, 'SMTP', True),
    (53, 'DNS', True),
    (80, 'HTTP', True),
    (110, 'POP3', True),
    (143, 'IMAP', True),
    (443, 'HTTPS', True),
    (465, 'SMTPS', True),
    (587, 'Submission', True),
    (993, 'IMAPS', True),
    (995, 'POP3S', True),
    (1352, 'Notes NRPC', False),
    (3306, 'MySQL', False),
    (3389, 'RDP', False),
    (5432, 'PostgreSQL', False),
    (5900, 'VNC', False),
    (6379, 'Redis', False),
    (8080, 'HTTP alternativ', True),
    (27017, 'MongoDB', False),
)

# Dienste, die in der IPv4/IPv6-Gegenüberstellung zählen: was ein Client
# tatsächlich anspricht, wenn er sich für eine Familie entscheidet.
DUALSTACK_PORTS = ((80, 'HTTP'), (443, 'HTTPS'), (25, 'SMTP'), (587, 'Submission'))


# Namen für eigene Portangaben, damit in der Tabelle nicht nur Zahlen stehen.
WELL_KNOWN = {
    20: 'FTP-Daten', 21: 'FTP', 22: 'SSH', 23: 'Telnet', 25: 'SMTP',
    53: 'DNS', 67: 'DHCP', 69: 'TFTP', 80: 'HTTP', 88: 'Kerberos',
    110: 'POP3', 111: 'RPC', 119: 'NNTP', 123: 'NTP', 135: 'RPC/DCOM',
    139: 'NetBIOS', 143: 'IMAP', 161: 'SNMP', 389: 'LDAP', 443: 'HTTPS',
    445: 'SMB', 465: 'SMTPS', 514: 'Syslog', 587: 'Submission', 636: 'LDAPS',
    873: 'rsync', 989: 'FTPS-Daten', 990: 'FTPS', 993: 'IMAPS', 995: 'POP3S',
    1194: 'OpenVPN', 1352: 'Notes NRPC', 1433: 'MSSQL', 1521: 'Oracle',
    1723: 'PPTP', 1883: 'MQTT', 2049: 'NFS', 2375: 'Docker', 2376: 'Docker TLS',
    3000: 'HTTP alternativ', 3128: 'Proxy', 3306: 'MySQL', 3389: 'RDP',
    4444: 'Metasploit', 5000: 'HTTP alternativ', 5060: 'SIP', 5222: 'XMPP',
    5432: 'PostgreSQL', 5601: 'Kibana', 5900: 'VNC', 6379: 'Redis',
    8000: 'HTTP alternativ', 8006: 'Proxmox', 8080: 'HTTP alternativ',
    8083: 'HTTP alternativ', 8086: 'InfluxDB', 8123: 'Home Assistant',
    8443: 'HTTPS alternativ', 8883: 'MQTT TLS', 9000: 'HTTP alternativ',
    9090: 'HTTP alternativ', 9200: 'Elasticsearch', 11211: 'Memcached',
    27017: 'MongoDB', 51820: 'WireGuard',
}


def parse_ports(spec: str) -> list:
    """"80, 443, 8000-8010" -> [80, 443, 8000 ... 8010].

    Leere Eingabe bedeutet: die Standardliste. Eine unsinnige Eingabe wird
    abgelehnt statt stillschweigend zu etwas anderem zu werden.
    """
    text = (spec or '').replace(';', ',').replace(' ', ',')
    if not text.strip(','):
        return []
    ports = set()
    for part in text.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            first, _, last = part.partition('-')
            try:
                start, end = int(first), int(last)
            except ValueError:
                raise ProbeError('bad_port', part[:20])
            if start > end:
                start, end = end, start
            if not (1 <= start <= 65535 and 1 <= end <= 65535):
                raise ProbeError('bad_port', part[:20])
            if end - start + 1 > MANUAL_MAX_PORTS:
                raise ProbeError('too_many_ports', str(MANUAL_MAX_PORTS))
            ports.update(range(start, end + 1))
        else:
            try:
                port = int(part)
            except ValueError:
                raise ProbeError('bad_port', part[:20])
            if not 1 <= port <= 65535:
                raise ProbeError('bad_port', part[:20])
            ports.add(port)
        if len(ports) > MANUAL_MAX_PORTS:
            raise ProbeError('too_many_ports', str(MANUAL_MAX_PORTS))
    return sorted(ports)


def _finding(level: str, code: str, **args) -> dict:
    return {'level': level, 'code': code, 'args': args}


def _worst(findings: list) -> str:
    for level in (FAIL, WARN):
        if any(f['level'] == level for f in findings):
            return level
    return OK


def _family_const(family: str):
    if family == '4':
        return socket.AF_INET
    if family == '6':
        return socket.AF_INET6
    return socket.AF_UNSPEC


def _addresses(host: str, family: str) -> list:
    try:
        infos = socket.getaddrinfo(host, None, _family_const(family),
                                   socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    seen, out = set(), []
    for info in infos:
        address = info[4][0]
        if address not in seen:
            seen.add(address)
            out.append((info[0], address))
    return out


def _probe_port(family_const, address: str, port: int,
                timeout: float = CONNECT_TIMEOUT) -> str:
    sock = socket.socket(family_const, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((address, port))
        return OPEN
    except socket.timeout:
        return FILTERED
    except ConnectionRefusedError:
        return CLOSED
    except OSError as e:
        # Kein Weg dorthin (kein Netz, keine Route) ist etwas anderes als
        # eine Firewall, sieht von hier aus aber gleich aus.
        return CLOSED if e.errno in (111, 61) else FILTERED
    finally:
        sock.close()


def check_ports(ctx: Context, target: str, family: str = '',
                ports: str = '') -> dict:
    host = clean_host_or_ip((target or '').strip())
    guard_target(ctx, host)
    addresses = _addresses(host, family)
    if not addresses:
        raise ProbeError('host_unresolvable', host)
    family_const, address = addresses[0]

    manual = parse_ports(ports)
    if manual:
        # Bei eigener Angabe sagt "erwartet" nichts mehr aus -- wer 8006
        # eintippt, weiß selbst, was dort laufen soll.
        wanted = [(p, WELL_KNOWN.get(p, ''), True) for p in manual]
        workers, timeout = MANUAL_WORKERS, MANUAL_TIMEOUT
    else:
        wanted = list(PORTS)
        workers, timeout = MAX_WORKERS, CONNECT_TIMEOUT

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_probe_port, family_const, address, port, timeout):
                   (port, service, expected)
                   for port, service, expected in wanted}
        for future in concurrent.futures.as_completed(futures):
            port, service, expected = futures[future]
            rows.append({'port': port, 'service': service,
                         'expected': expected, 'state': future.result()})
    rows.sort(key=lambda r: r['port'])

    open_ports = [r for r in rows if r['state'] == OPEN]
    unexpected = [r for r in open_ports if not r['expected']]
    findings = []
    if open_ports:
        findings.append(_finding(OK, 'ports_open',
                                 count=len(open_ports),
                                 list=', '.join(f"{r['port']} ({r['service']})"
                                                for r in open_ports)))
    else:
        findings.append(_finding(INFO, 'ports_none_open'))
    if unexpected:
        findings.append(_finding(WARN, 'ports_unexpected',
                                 list=', '.join(f"{r['port']} ({r['service']})"
                                                for r in unexpected)))
    filtered = [r for r in rows if r['state'] == FILTERED]
    if len(filtered) == len(rows):
        # Alles gefiltert heißt meist: dazwischen steht eine Firewall, die
        # gar nichts durchlässt -- kein Ergebnis über die Dienste dahinter.
        findings.append(_finding(INFO, 'ports_all_filtered'))

    return {'host': host, 'address': address,
            'family': '6' if ':' in address else '4',
            'manual': bool(manual),
            'checked': len(rows), 'rows': rows,
            'open_count': len(open_ports),
            'findings': findings, 'level': _worst(findings)}


def check_dualstack(ctx: Context, target: str) -> dict:
    """Dieselben Dienste über IPv4 und IPv6 nebeneinander."""
    host = clean_host_or_ip((target or '').strip())
    guard_target(ctx, host)
    v4 = _addresses(host, '4')
    v6 = _addresses(host, '6')

    rows = []
    jobs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for port, service in DUALSTACK_PORTS:
            row = {'port': port, 'service': service, 'v4': '', 'v6': ''}
            rows.append(row)
            if v4:
                jobs.append((row, 'v4',
                             pool.submit(_probe_port, v4[0][0], v4[0][1], port)))
            if v6:
                jobs.append((row, 'v6',
                             pool.submit(_probe_port, v6[0][0], v6[0][1], port)))
        for row, key, future in jobs:
            row[key] = future.result()

    findings = []
    if not v4:
        findings.append(_finding(WARN, 'dual_no_v4'))
    if not v6:
        findings.append(_finding(INFO, 'dual_no_v6'))
    if v4 and v6:
        # Der Fall, um den es geht: über eine Familie erreichbar, über die
        # andere nicht. Genau das führt zu "manchmal geht es nicht".
        broken = [r for r in rows
                  if r['v4'] == OPEN and r['v6'] in (CLOSED, FILTERED)]
        reverse = [r for r in rows
                   if r['v6'] == OPEN and r['v4'] in (CLOSED, FILTERED)]
        if broken:
            findings.append(_finding(FAIL, 'dual_v6_missing',
                                     list=', '.join(f"{r['port']} ({r['service']})"
                                                    for r in broken)))
        if reverse:
            findings.append(_finding(WARN, 'dual_v4_missing',
                                     list=', '.join(f"{r['port']} ({r['service']})"
                                                    for r in reverse)))
        if not broken and not reverse:
            findings.append(_finding(OK, 'dual_symmetric'))

    return {'host': host,
            'v4_address': v4[0][1] if v4 else '',
            'v6_address': v6[0][1] if v6 else '',
            'rows': rows, 'findings': findings, 'level': _worst(findings)}
