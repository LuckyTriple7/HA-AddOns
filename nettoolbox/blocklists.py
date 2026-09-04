"""DNSBL / RBL blacklist checks.

A DNSBL is queried by reversing the IP's octets under the list's zone, e.g.
2.0.0.127.zen.spamhaus.org for 127.0.0.2. Per RFC 5782, any A record in
127.0.0.0/8 means "listed"; NXDOMAIN means "not listed". 127.0.0.2 is the
standard always-listed test address every compliant list must answer for —
used here only to verify the zone list against the real internet, not at
runtime.

A few providers hand back specific 127.255.255.x codes that mean something
else entirely (the query itself was rejected, rate-limited, or malformed) —
not "this address is spam". Reported separately instead of as a false
listing. Live-tested against real zones (see PROBES.md-style comments below):
some sub-zones (Spamhaus SBL/XBL/PBL standalone) return that code so often
from ordinary public resolvers that they were dropped in favour of ZEN, which
already combines all three and answers reliably. SORBS was removed outright:
the service shut down, sorbs.net no longer resolves, and its zone now answers
every query -- including the RFC 5782 test address -- with the same fixed
non-127.x address, so it can never produce a real result.
"""

import concurrent.futures

from netcore import Context, ProbeError, clean_ip, query

# Well-documented, still-operating public DNSBLs commonly used for mail-server
# reputation checks. Not the ~100 lists a commercial checker polls — every one
# here was verified live against the RFC 5782 test address before being added.
# Add more by appending a (label, zone) pair.
# Third entry is the operator's own lookup/removal page, {ip} substituted --
# a listing is only half the answer, getting off the list is the other half.
# Every URL here was fetched before being added; the ones whose page could
# not be confirmed are left empty rather than guessed at, and the interface
# then simply shows no link.
RBL_ZONES = (
    ('Spamhaus ZEN', 'zen.spamhaus.org',
     'https://check.spamhaus.org/results/?query={ip}'),
    ('Barracuda', 'b.barracudacentral.org',
     'https://www.barracudacentral.org/rbl/removal-request'),
    ('SpamCop', 'bl.spamcop.net',
     'https://www.spamcop.net/w3m?action=checkblock&ip={ip}'),
    ('UCEPROTECT L1', 'dnsbl-1.uceprotect.net',
     'https://www.uceprotect.net/en/rblcheck.php?ipr={ip}'),
    ('UCEPROTECT L2', 'dnsbl-2.uceprotect.net',
     'https://www.uceprotect.net/en/rblcheck.php?ipr={ip}'),
    ('UCEPROTECT L3', 'dnsbl-3.uceprotect.net',
     'https://www.uceprotect.net/en/rblcheck.php?ipr={ip}'),
    ('PSBL', 'psbl.surriel.com', 'https://psbl.org/listing?ip={ip}'),
    ('CBL', 'cbl.abuseat.org',
     'https://check.spamhaus.org/results/?query={ip}'),
    ('Blocklist.de', 'bl.blocklist.de',
     'https://www.blocklist.de/en/search.html?ip={ip}'),
    ('Mailspike BL', 'bl.mailspike.net',
     'https://mailspike.org/iprep.html?query={ip}'),
    ('Mailspike Z', 'z.mailspike.net',
     'https://mailspike.org/iprep.html?query={ip}'),
    # gbudb.com was unreachable when this was checked; the DNS zone itself
    # answers the RFC 5782 test address correctly, so the list stays and only
    # the link is left out.
    ('GBUdb', 'truncate.gbudb.net', ''),
    ('JustSpam', 'dnsbl.justspam.org', 'http://www.justspam.org/'),
    ('SpamEatingMonkey', 'bl.spameatingmonkey.net',
     'https://spameatingmonkey.com/lookup?query={ip}'),
)

# Meta return codes seen across several providers (Spamhaus documents these
# explicitly; CBL — a separate operator whose feed Spamhaus XBL consumes —
# was observed handing back the same "open resolver" code live). Checked
# against every zone's answer, not just Spamhaus-named ones.
_PROVIDER_CODES = {
    '127.255.255.252': 'typo',
    '127.255.255.253': 'excluded',
    '127.255.255.254': 'open_resolver',
    '127.255.255.255': 'rate_limited',
}

MAX_WORKERS = 12


def _reverse_octets(ip: str) -> str:
    return '.'.join(reversed(ip.split('.')))


def _check_one(ctx: Context, ip: str, label: str, zone: str,
               lookup: str = '') -> dict:
    name = f'{_reverse_octets(ip)}.{zone}'
    row = {'label': label, 'zone': zone, 'listed': False, 'records': [],
           'reason': '', 'error': '', 'provider_code': '',
           'lookup_url': lookup.replace('{ip}', ip) if lookup else ''}
    try:
        answer = query(ctx, name, 'A')
    except ProbeError as e:
        if e.code != 'nxdomain':
            row['error'] = e.code
        return row
    # Only 127.0.0.0/8 is the documented "listed" convention. An operator
    # answering something else entirely -- an informational or parking
    # address rather than a per-IP result -- is not a hit. SORBS did exactly
    # that after it shut down, which is why it is no longer in the list
    # above at all.
    listed_records = [r for r in answer.records if r.startswith('127.')]
    if not listed_records:
        if answer.records:
            row['error'] = 'unexpected_response'
        return row
    provider_hit = next((r for r in listed_records if r in _PROVIDER_CODES),
                        None)
    if provider_hit:
        row['provider_code'] = _PROVIDER_CODES[provider_hit]
        return row
    row['records'] = listed_records
    row['listed'] = True
    try:
        txt = query(ctx, name, 'TXT').records
        row['reason'] = txt[0] if txt else ''
    except ProbeError:
        pass
    return row


def check_blacklist(ctx: Context, ip: str) -> dict:
    ip = clean_ip(ip)
    if ':' in ip:
        # Nearly every public DNSBL only indexes IPv4 space.
        raise ProbeError('ipv6_unsupported', ip)

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_check_one, ctx, ip, label, zone, lookup)
                   for label, zone, lookup in RBL_ZONES]
        for fut in concurrent.futures.as_completed(futures):
            rows.append(fut.result())
    rows.sort(key=lambda r: r['label'])

    listed = [r for r in rows if r['listed']]
    blocked = [r for r in rows if r['provider_code']]
    errors = [r for r in rows if r['error']]

    findings = []
    if listed:
        findings.append({'level': 'fail', 'code': 'rbl_listed',
                         'args': {'count': len(listed),
                                  'lists': [r['label'] for r in listed]}})
    else:
        findings.append({'level': 'ok', 'code': 'rbl_clean',
                         'args': {'count': len(rows)}})
    if blocked:
        findings.append({'level': 'info', 'code': 'rbl_provider_blocked',
                         'args': {'count': len(blocked),
                                  'lists': [r['label'] for r in blocked]}})
    if errors:
        findings.append({'level': 'info', 'code': 'rbl_errors',
                         'args': {'count': len(errors)}})

    level = 'fail' if listed else ('info' if (blocked or errors) else 'ok')
    return {'ip': ip, 'rows': rows, 'listed_count': len(listed),
            'blocked_count': len(blocked), 'error_count': len(errors),
            'checked': len(rows), 'findings': findings, 'level': level}
