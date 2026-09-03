"""Real HTTP/3 (QUIC) connectivity check.

An actual QUIC handshake and HTTP/3 GET request over UDP -- not just the
Alt-Svc advertisement httpcheck.py looks at. Built on aioquic; that
dependency was skipped earlier over a musllinux/Python-3.14 wheel worry that
turned out to be wrong once actually checked against PyPI (aioquic and
cryptography both ship abi3 + musllinux wheels), so it was added properly
instead. Every method used here (H3Connection, QuicConnectionProtocol,
get_next_available_stream_id, ...) was checked against the installed
package's real signatures before writing this, not recalled from memory.
"""

import asyncio
import ssl
import time

from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import DataReceived, HeadersReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ConnectionTerminated, ProtocolNegotiated

from netcore import Context, ProbeError, clean_host_or_ip, guard_target, query

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'
DEFAULT_PORT = 443
MAX_RESPONSE_BYTES = 16 * 1024


def _finding(level: str, code: str, **args) -> dict:
    return {'level': level, 'code': code, 'args': args}


def _worst(findings: list) -> str:
    for level in (FAIL, WARN, INFO, OK):
        if any(f['level'] == level for f in findings):
            return level
    return OK


def _parse_target(raw: str) -> tuple:
    raw = (raw or '').strip()
    if not raw:
        raise ProbeError('empty_target')
    if raw.count(':') == 1:
        host, port_part = raw.split(':', 1)
        try:
            port = int(port_part)
        except ValueError:
            raise ProbeError('bad_port', port_part)
        if not (1 <= port <= 65535):
            raise ProbeError('bad_port', port_part)
    else:
        host, port = raw, DEFAULT_PORT
    return clean_host_or_ip(host), port


class _H3ClientProtocol(QuicConnectionProtocol):
    """Sends one GET / and waits for the response to finish."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.h3 = H3Connection(self._quic)
        self.headers = None
        self.body = b''
        self.alpn = ''
        self.close_reason = ''
        self.finished = asyncio.Event()

    def quic_event_received(self, event):
        if isinstance(event, ProtocolNegotiated):
            self.alpn = event.alpn_protocol or ''
            return
        if isinstance(event, ConnectionTerminated):
            self.close_reason = event.reason_phrase or str(event.error_code)
            self.finished.set()
            return
        for h3_event in self.h3.handle_event(event):
            if isinstance(h3_event, HeadersReceived):
                self.headers = h3_event.headers
                if h3_event.stream_ended:
                    self.finished.set()
            elif isinstance(h3_event, DataReceived):
                if len(self.body) < MAX_RESPONSE_BYTES:
                    self.body += h3_event.data
                if h3_event.stream_ended:
                    self.finished.set()

    async def get(self, authority: str, path: str = '/') -> None:
        stream_id = self._quic.get_next_available_stream_id()
        self.h3.send_headers(stream_id, [
            (b':method', b'GET'), (b':scheme', b'https'),
            (b':authority', authority.encode()), (b':path', path.encode()),
            (b'user-agent', b'NetToolbox'),
        ], end_stream=True)
        self.transmit()


async def _run_inner(connect_host: str, host: str, port: int, timeout: float) -> dict:
    config = QuicConfiguration(is_client=True, alpn_protocols=H3_ALPN,
                               server_name=host, idle_timeout=timeout)
    started = time.monotonic()
    async with connect(connect_host, port, configuration=config,
                       create_protocol=_H3ClientProtocol) as protocol:
        handshake_ms = int((time.monotonic() - started) * 1000)
        await protocol.get(host)
        try:
            await asyncio.wait_for(protocol.finished.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise ProbeError('quic_response_timeout', f'{host}:{port}')

        status = ''
        for key, value in (protocol.headers or ()):
            if key == b':status':
                status = value.decode('ascii', 'replace')
                break

        return {
            'handshake_ms': handshake_ms,
            'alpn': protocol.alpn,
            'close_reason': protocol.close_reason,
            'status': status,
            'body_bytes': len(protocol.body),
        }


async def _run(connect_host: str, host: str, port: int, timeout: float) -> dict:
    # QuicConfiguration(idle_timeout=...) is meant to bound the handshake
    # too, but relying on aioquic's own internal timer as the *only* limit
    # is a hard thing to be fully certain of from the outside -- a UDP path
    # that is completely silent (no packet at all comes back, common with
    # firewalls that drop rather than reject) must not be able to hang this
    # coroutine, and by extension the request thread serving it, forever.
    # A hard outer bound is cheap insurance regardless of whether the inner
    # one is reliable.
    try:
        return await asyncio.wait_for(_run_inner(connect_host, host, port, timeout),
                                      timeout=timeout + 3)
    except asyncio.TimeoutError:
        raise ProbeError('quic_unreachable', f'{host}:{port}')


def _resolve_ipv4_first(ctx: Context, host: str) -> str:
    """The address aioquic's connect() is handed.

    aioquic resolves the host itself via a bare getaddrinfo() and connects
    to whichever address comes back first -- no Happy-Eyeballs, no IPv4
    preference (checked against its source, not assumed). Where a system
    resolver happens to list AAAA before A, that silently sends every QUIC
    attempt out over IPv6; on a host or container without a real IPv6
    route, that hangs or fails while an ordinary HTTPS request (which most
    HTTP client stacks make Happy-Eyeballs-aware, or which simply prefer
    IPv4) keeps working fine -- the exact "definitely does HTTP/3, still no
    answer" symptom this resolves. A record looked up through our own DNS
    layer first, falling back to AAAA only if the name truly has none.
    """
    try:
        import ipaddress
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    a_records = query(ctx, host, 'A').records
    if a_records:
        return a_records[0]
    aaaa_records = query(ctx, host, 'AAAA').records
    if aaaa_records:
        return aaaa_records[0]
    raise ProbeError('quic_unreachable', f'{host}: no A/AAAA record')


def check_quic(ctx: Context, target: str) -> dict:
    host, port = _parse_target(target)
    guard_target(ctx, host)
    connect_host = _resolve_ipv4_first(ctx, host)

    findings = []
    result = {
        'host': host, 'port': port, 'connected': False, 'handshake_ms': None,
        'alpn': '', 'close_reason': '', 'status': '', 'body_bytes': 0,
        'findings': findings,
    }

    try:
        outcome = asyncio.run(_run(connect_host, host, port, ctx.http_timeout))
    except ProbeError:
        raise
    except (ssl.SSLError,) as e:
        raise ProbeError('quic_tls_error', str(e))
    except OSError as e:
        # aioquic raises a bare ConnectionError() with no message at all
        # when the handshake never completes (live-verified: no HTTP/3
        # support and a UDP port that never answers looks identical from
        # here, no ICMP came back either) -- str(e) is empty in exactly
        # that, the single most common real-world case, so it is not
        # relied on for the detail text.
        raise ProbeError('quic_unreachable', str(e) or f'{host}:{port}')
    except Exception as e:
        # aioquic raises its own connection/handshake errors that don't
        # share one common base worth enumerating one by one; surfaced
        # as a plain failure with whatever it said, not silently retried.
        raise ProbeError('quic_error', str(e))

    result.update(outcome)
    result['connected'] = outcome['alpn'] == 'h3'

    if result['connected']:
        findings.append(_finding(OK, 'quic_connected', ms=result['handshake_ms']))
        if result['status']:
            findings.append(_finding(OK, 'quic_response_ok', status=result['status']))
    elif result['close_reason']:
        findings.append(_finding(FAIL, 'quic_closed', reason=result['close_reason']))
    else:
        findings.append(_finding(WARN, 'quic_alpn_mismatch', alpn=result['alpn'] or '?'))

    result['level'] = _worst(findings)
    return result
