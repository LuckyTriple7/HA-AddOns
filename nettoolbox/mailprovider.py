"""Who runs this mail server, and with what software.

Two independent questions, answered from data the other probes already
fetched -- this module never touches the network:

* the *operator* comes from the MX host names, because those are fixed per
  product (anything under mail.protection.outlook.com is Microsoft 365, no
  matter whose domain sits in front of it),
* the *software* comes from the SMTP greeting and the EHLO feature list.

Both are best-effort identification, not proof: a banner can be edited to
say anything, and a self-hosted server matches no MX pattern at all. That
is why an unmatched result is reported as "not recognised" rather than as a
finding -- nothing here ever colours a traffic light.
"""

import re

# Matched against the end of an MX host name, longest suffix first, so
# "mx.foo.protection.outlook.com" cannot be stolen by a shorter
# "outlook.com" entry. Suffixes only -- never a substring search, or
# "google.com.attacker.net" would match.
MX_SUFFIXES = (
    ('l.google.com', 'Google Workspace'),
    ('googlemail.com', 'Google Workspace'),
    ('psmtp.com', 'Google Workspace (Postini)'),
    ('smtp.google.com', 'Google'),
    ('google.com', 'Google'),
    ('mail.protection.outlook.com', 'Microsoft 365'),
    ('olc.protection.outlook.com', 'Microsoft 365'),
    ('protection.outlook.com', 'Microsoft 365'),
    ('mail.eo.outlook.com', 'Microsoft 365'),
    ('hotmail.com', 'Microsoft Outlook.com'),
    ('outlook.com', 'Microsoft Outlook.com'),
    ('kundenserver.de', 'IONOS'),
    ('ionos.de', 'IONOS'),
    ('ui-mx.com', 'IONOS'),
    ('schlund.de', 'IONOS'),
    ('perfora.net', 'IONOS'),
    ('gmx.net', 'GMX (United Internet)'),
    ('web.de', 'WEB.DE (United Internet)'),
    ('rzone.de', 'STRATO'),
    ('strato.de', 'STRATO'),
    ('kasserver.com', 'ALL-INKL'),
    ('your-server.de', 'Hetzner'),
    ('netcup.net', 'Netcup'),
    ('netcup-mail.de', 'Netcup'),
    ('mailbox.org', 'mailbox.org'),
    ('heinlein-support.de', 'mailbox.org / Heinlein'),
    ('posteo.de', 'Posteo'),
    ('mailgun.org', 'Mailgun'),
    ('sendgrid.net', 'SendGrid'),
    ('amazonses.com', 'Amazon SES'),
    ('awsapps.com', 'Amazon WorkMail'),
    ('mx.cloudflare.net', 'Cloudflare Email Routing'),
    ('mimecast.com', 'Mimecast'),
    ('mimecast.co.za', 'Mimecast'),
    ('pphosted.com', 'Proofpoint'),
    ('ppe-hosted.com', 'Proofpoint Essentials'),
    ('barracudanetworks.com', 'Barracuda'),
    ('messagelabs.com', 'Broadcom / Symantec.cloud'),
    ('hornetsecurity.com', 'Hornetsecurity'),
    ('antispameurope.com', 'Hornetsecurity'),
    ('nospamproxy.de', 'NoSpamProxy'),
    ('securence.com', 'Securence'),
    ('emailsrvr.com', 'Rackspace Email'),
    ('messagingengine.com', 'Fastmail'),
    ('fastmail.com', 'Fastmail'),
    ('zoho.com', 'Zoho Mail'),
    ('zoho.eu', 'Zoho Mail'),
    ('protonmail.ch', 'Proton Mail'),
    ('proton.me', 'Proton Mail'),
    ('tutanota.de', 'Tuta'),
    ('tutamail.com', 'Tuta'),
    ('migadu.com', 'Migadu'),
    ('purelymail.com', 'Purelymail'),
    ('icloud.com', 'Apple iCloud'),
    ('me.com', 'Apple iCloud'),
    ('yandex.net', 'Yandex 360'),
    ('yandex.ru', 'Yandex 360'),
    ('mail.ru', 'VK / Mail.ru'),
    ('yahoodns.net', 'Yahoo'),
    ('t-online.de', 'Telekom'),
    ('telekom.de', 'Telekom'),
    ('vodafone.de', 'Vodafone'),
    ('arcor.de', 'Vodafone (Arcor)'),
    ('freenet.de', 'freenet'),
    ('1blu.de', '1blu'),
    ('df.eu', 'domainFACTORY'),
    ('mittwald.de', 'Mittwald'),
    ('hosteurope.de', 'Host Europe'),
    ('open-xchange.com', 'Open-Xchange'),
    ('titan.email', 'Titan Mail'),
    ('improvmx.com', 'ImprovMX'),
    ('forwardemail.net', 'Forward Email'),
    ('secureserver.net', 'GoDaddy'),
    ('registrar-servers.com', 'Namecheap Private Email'),
    ('ovh.net', 'OVHcloud'),
    ('mail.gandi.net', 'Gandi'),
    ('gandi.net', 'Gandi'),
    ('infomaniak.ch', 'Infomaniak'),
    ('antispamcloud.com', 'SpamExperts'),
    ('spamexperts.com', 'SpamExperts'),
    ('hostedemail.com', 'Openwave / Rackspace'),
    ('qq.com', 'Tencent Exmail'),
    ('aliyun.com', 'Alibaba Mail'),
    ('nsatc.net', 'Microsoft (Legacy FOPE)'),
)

# Greeting lines carry the product name far more often than not. The
# optional trailing group picks up a version when one is printed.
BANNER_PATTERNS = (
    (r'\bpostfix\b(?:[\s/-]*v?(\d+(?:\.\d+)+))?', 'Postfix'),
    (r'\bexim\b[\s/-]*v?(\d+(?:\.\d+)+)?', 'Exim'),
    (r'\bsendmail\b[\s/-]*v?(\d+(?:\.\d+)+)?', 'Sendmail'),
    (r'microsoft esmtp mail service(?:.*?version:?\s*(\d+(?:\.\d+)+))?',
     'Microsoft Exchange'),
    (r'\bmicrosoft smtp\b', 'Microsoft Exchange'),
    (r'\bgsmtp\b', 'Google Mail (gsmtp)'),
    (r'\bopensmtpd\b', 'OpenSMTPD'),
    (r'\bstalwart\b', 'Stalwart'),
    (r'\bharaka\b[\s/-]*v?(\d+(?:\.\d+)+)?', 'Haraka'),
    (r'\bqmail\b', 'qmail'),
    (r'\bzimbra\b', 'Zimbra'),
    (r'\bmdaemon\b', 'MDaemon'),
    (r'\bkerio\b', 'Kerio Connect'),
    (r'\bicewarp\b', 'IceWarp'),
    (r'\bcommunigate\b', 'CommuniGate Pro'),
    (r'\bhalon\b', 'Halon'),
    (r'\bpowermta\b', 'PowerMTA'),
    (r'\bmomentum\b', 'Momentum'),
    (r'\brzmta\b[\s/-]*v?(\d+(?:\.\d+)+)?', 'RZmta (STRATO)'),
    (r'\bcyrus\b', 'Cyrus'),
    (r'\bapache james\b', 'Apache James'),
    (r'\bmailcow\b', 'mailcow'),
    # mailcow setzt mail_name auf "Postcow", das Banner nennt also nie
    # "Postfix" -- obwohl genau das darunter laeuft.
    (r'\bpostcow\b', 'Postfix (mailcow)'),
    (r'\bmailu\b', 'Mailu'),
    (r'\bsmtpd\b', 'smtpd'),
    (r'\bmaddy\b', 'maddy'),
    (r'\bysmtp\b', 'Yahoo (YSmtp)'),
    (r'\bmailenable\b', 'MailEnable'),
    (r'\bhmailserver\b', 'hMailServer'),
    (r'\bproofpoint\b', 'Proofpoint'),
    (r'\bmimecast\b', 'Mimecast'),
    (r'\bbarracuda\b', 'Barracuda'),
)

# Only used when the banner said nothing: these ESMTP extensions are
# non-standard and effectively vendor-specific.
FEATURE_HINTS = (
    ('XEXCH50', 'Microsoft Exchange'),
    ('XRDST', 'Microsoft Exchange'),
    ('XSHADOW', 'Microsoft Exchange'),
    ('XCLIENT', 'Postfix'),
    ('XFORWARD', 'Postfix'),
    ('XVERP', 'qmail / Postfix'),
    ('XPROXYFROM', 'Yahoo'),
)


def _norm_host(host: str) -> str:
    return (host or '').strip().strip('.').lower()


def provider_for_host(host: str) -> dict:
    """{'name': ..., 'matched': <suffix>} for one MX host, or {} if unknown."""
    host = _norm_host(host)
    if not host:
        return {}
    best = {}
    for suffix, name in MX_SUFFIXES:
        if host == suffix or host.endswith('.' + suffix):
            # Longest suffix wins: protection.outlook.com beats outlook.com.
            if len(suffix) > len(best.get('matched', '')):
                best = {'name': name, 'matched': suffix}
    return best


def detect_provider(hosts) -> dict:
    """The operator behind a set of MX host names.

    A domain whose MX records point at two different products (a migration
    in progress, or a filtering service in front of a mailbox host) reports
    both rather than picking one.
    """
    names, matched, unknown = [], [], []
    for host in hosts or []:
        hit = provider_for_host(host)
        if hit:
            if hit['name'] not in names:
                names.append(hit['name'])
            matched.append({'host': _norm_host(host), 'name': hit['name']})
        else:
            unknown.append(_norm_host(host))
    return {'names': names, 'hosts': matched, 'unknown': unknown,
            'known': bool(names)}


def detect_software(banner: str, features=None) -> dict:
    """The MTA software behind a greeting line.

    Trusts nothing: the banner is free text the operator controls, so the
    raw line is returned alongside the guess and the caller shows both.
    """
    text = (banner or '').lower()
    for pattern, name in BANNER_PATTERNS:
        m = re.search(pattern, text)
        if not m:
            continue
        version = ''
        if m.groups():
            version = next((g for g in m.groups() if g), '') or ''
        return {'name': name, 'version': version, 'source': 'banner',
                'known': True}
    upper = [str(f).upper() for f in (features or [])]
    for feature, name in FEATURE_HINTS:
        if feature in upper:
            return {'name': name, 'version': '', 'source': 'ehlo',
                    'known': True}
    return {'name': '', 'version': '', 'source': '', 'known': False}
