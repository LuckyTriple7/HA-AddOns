"""Ping and traceroute.

Shells out to the system binaries (iputils ping, the "Modern traceroute for
Linux" package) instead of opening raw ICMP sockets directly -- the
container's default capabilities already cover what the binaries need
(verified live: works even unprivileged here), and there is no reason to
reimplement ICMP framing when a well-tested binary already does it. The
argument list is always fixed and passed as a list (never a shell string),
and the target goes through the same guard_target() every other probe uses
before either binary ever runs.
"""

import re
import subprocess

from netcore import Context, ProbeError, clean_host_or_ip, guard_target, query

OK, WARN, FAIL = 'ok', 'warn', 'fail'

PING_COUNT = 4
PING_TIMEOUT_S = 2
TRACEROUTE_MAX_HOPS = 20
TRACEROUTE_TIMEOUT_S = 2

_PING_LINE_RE = re.compile(r'from .*?: icmp_seq=(\d+) ttl=(\d+) time=([\d.]+) ms')
_PING_SUMMARY_RE = re.compile(
    r'(\d+) packets transmitted, (\d+) (?:packets )?received,'
    r'(?:\s*\+\d+ errors,)?\s*([\d.]+)% packet loss')
_PING_RTT_RE = re.compile(r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms')
_TRACE_HOP_RE = re.compile(r'^\s*(\d+)\s+(.*)$')


def _finding(level: str, code: str, **args) -> dict:
    return {'level': level, 'code': code, 'args': args}


def _worst(findings: list) -> str:
    for level in (FAIL, WARN, OK):
        if any(f['level'] == level for f in findings):
            return level
    return OK


def _resolved_ip(ctx: Context, host: str) -> str:
    """The address a hop is compared against for "did we arrive" -- host
    may be a domain name, traceroute -n only ever prints numeric IPs."""
    try:
        import ipaddress
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    try:
        addresses = query(ctx, host, 'A').records
        return addresses[0] if addresses else ''
    except ProbeError:
        return ''


def check_ping(ctx: Context, target: str) -> dict:
    host = clean_host_or_ip((target or '').strip())
    guard_target(ctx, host)
    try:
        proc = subprocess.run(
            ['ping', '-c', str(PING_COUNT), '-W', str(PING_TIMEOUT_S), host],
            capture_output=True, text=True,
            timeout=PING_COUNT * PING_TIMEOUT_S + 5)
    except subprocess.TimeoutExpired:
        raise ProbeError('ping_timeout', host)
    except FileNotFoundError:
        raise ProbeError('ping_unavailable', host)

    output = proc.stdout
    replies = [{'seq': int(m.group(1)), 'ttl': int(m.group(2)), 'ms': float(m.group(3))}
               for m in _PING_LINE_RE.finditer(output)]
    summary = _PING_SUMMARY_RE.search(output)
    sent = int(summary.group(1)) if summary else PING_COUNT
    received = int(summary.group(2)) if summary else len(replies)
    loss_pct = float(summary.group(3)) if summary else (0.0 if replies else 100.0)
    rtt_m = _PING_RTT_RE.search(output)
    rtt = ({'min': float(rtt_m.group(1)), 'avg': float(rtt_m.group(2)),
           'max': float(rtt_m.group(3)), 'mdev': float(rtt_m.group(4))}
           if rtt_m else None)

    findings = []
    if received == 0:
        findings.append(_finding(FAIL, 'ping_no_reply'))
    elif loss_pct > 0:
        findings.append(_finding(WARN, 'ping_partial_loss', loss=loss_pct))
    else:
        findings.append(_finding(OK, 'ping_ok', avg=rtt['avg'] if rtt else 0))

    return {
        'host': host, 'sent': sent, 'received': received, 'loss_pct': loss_pct,
        'replies': replies, 'rtt': rtt, 'raw': output.strip(),
        'findings': findings, 'level': _worst(findings),
    }


def check_traceroute(ctx: Context, target: str) -> dict:
    host = clean_host_or_ip((target or '').strip())
    guard_target(ctx, host)
    target_ip = _resolved_ip(ctx, host)

    try:
        proc = subprocess.run(
            ['traceroute', '-n', '-w', str(TRACEROUTE_TIMEOUT_S),
             '-m', str(TRACEROUTE_MAX_HOPS), '-q', '1', host],
            capture_output=True, text=True,
            timeout=TRACEROUTE_MAX_HOPS * TRACEROUTE_TIMEOUT_S + 15)
    except subprocess.TimeoutExpired:
        raise ProbeError('traceroute_timeout', host)
    except FileNotFoundError:
        raise ProbeError('traceroute_unavailable', host)

    hops = []
    for line in proc.stdout.splitlines()[1:]:  # line 0 is the "traceroute to ..." header
        m = _TRACE_HOP_RE.match(line)
        if not m:
            continue
        rest = m.group(2).strip()
        if rest.startswith('*'):
            hops.append({'hop': int(m.group(1)), 'address': '', 'ms': None})
            continue
        parts = rest.split()
        address = parts[0] if parts else ''
        # "4.633 ms" is two whitespace-separated tokens, not one -- the
        # number always comes immediately before a bare "ms" token.
        ms = None
        for i, token in enumerate(parts):
            if token == 'ms' and i > 0:
                try:
                    ms = float(parts[i - 1])
                except ValueError:
                    pass
                break
        hops.append({'hop': int(m.group(1)), 'address': address, 'ms': ms})

    reached = bool(target_ip) and any(h['address'] == target_ip for h in hops)
    findings = []
    if reached:
        findings.append(_finding(OK, 'traceroute_reached', hops=len(hops)))
    elif hops:
        findings.append(_finding(WARN, 'traceroute_incomplete', hops=len(hops)))
    else:
        findings.append(_finding(FAIL, 'traceroute_no_hops'))

    return {
        'host': host, 'target_ip': target_ip, 'hops': hops, 'reached': reached,
        'raw': proc.stdout.strip(), 'findings': findings, 'level': _worst(findings),
    }
