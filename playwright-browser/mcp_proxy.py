"""
Built-in Playwright MCP for the Playwright Browser Home Assistant add-on.

Runs @playwright/mcp on a loopback port and connects it to Chromium through the
lazy CDP proxy, so Chromium still only starts when a browser tool is used.
A small reverse proxy on MCP_PORT puts a bearer-token check in front of it,
because Playwright MCP itself has no authentication and add-on ports are
reachable from the whole LAN.
"""
import hmac
import http.client
import http.server
import os
import subprocess
import threading
import time

MCP_PORT = int(os.environ.get('MCP_PORT', '0'))
MCP_TOKEN = os.environ.get('MCP_TOKEN', '')
MCP_INTERNAL_PORT = int(os.environ.get('MCP_INTERNAL_PORT', '8931'))
MCP_IDLE_MS = int(os.environ.get('MCP_IDLE_MINUTES', '5')) * 60 * 1000
NODE_BIN = os.environ.get('NODE_BIN', 'node')
MCP_CLI = os.environ.get('MCP_CLI', '/opt/playwright-mcp/node_modules/@playwright/mcp/cli.js')
MCP_OUTPUT_DIR = os.environ.get('MCP_OUTPUT_DIR', '/tmp/playwright-mcp')
MIN_TOKEN_LENGTH = 16

# Hop-by-hop headers and the ones the proxy sets itself
_SKIP_REQUEST = {'host', 'authorization', 'connection', 'content-length', 'keep-alive',
                 'proxy-connection', 'te', 'trailer', 'transfer-encoding', 'upgrade'}
_SKIP_RESPONSE = {'connection', 'content-length', 'keep-alive', 'transfer-encoding'}

_log = print
_stopping = False
_node_proc = None
_node_lock = threading.Lock()


def _node_cmd(cdp_endpoint):
    return [
        NODE_BIN, MCP_CLI,
        '--cdp-endpoint', cdp_endpoint,
        '--host', '127.0.0.1',
        '--port', str(MCP_INTERNAL_PORT),
        # Only reachable via loopback from this proxy, which rewrites Host anyway
        '--allowed-hosts', '*',
        '--output-dir', MCP_OUTPUT_DIR,
        # Drop the CDP connection when idle so the CDP proxy can stop Chromium
        '--idle-timeout', str(MCP_IDLE_MS),
    ]


def _node_supervisor(cdp_endpoint):
    """Keep the Node MCP server running; restart with backoff if it exits."""
    global _node_proc
    delay = 5
    while not _stopping:
        started = time.monotonic()
        with _node_lock:
            if _stopping:
                return
            _node_proc = subprocess.Popen(_node_cmd(cdp_endpoint))
        _log('INFO', f'Playwright MCP started (pid {_node_proc.pid}, internal port {MCP_INTERNAL_PORT}).')
        code = _node_proc.wait()
        if _stopping:
            return
        _log('ERROR', f'Playwright MCP exited with code {code}, restarting in {delay}s.')
        time.sleep(delay)
        # Reset the backoff after a run that lasted a while
        delay = 5 if time.monotonic() - started > 300 else min(delay * 2, 300)


class McpHandler(http.server.BaseHTTPRequestHandler):
    # HTTP/1.0: the response body ends when the connection closes, so streamed
    # (SSE) responses can be passed through without re-chunking them.
    protocol_version = 'HTTP/1.0'

    def log_message(self, *args):
        pass

    def do_GET(self):
        self._forward()

    def do_POST(self):
        self._forward()

    def do_DELETE(self):
        self._forward()

    def _authorized(self):
        auth = self.headers.get('Authorization', '')
        if not auth.lower().startswith('bearer '):
            return False
        return hmac.compare_digest(auth[7:].strip().encode(), MCP_TOKEN.encode())

    def _forward(self):
        if not self._authorized():
            _log('WARNING', f'MCP request without valid token from {self.client_address[0]} rejected.')
            try:
                self.send_response(401)
                self.send_header('WWW-Authenticate', 'Bearer')
                self.send_header('Content-Length', '0')
                self.end_headers()
            except Exception:
                pass
            return

        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in _SKIP_REQUEST}
        headers['Host'] = f'127.0.0.1:{MCP_INTERNAL_PORT}'
        if body is not None:
            headers['Content-Length'] = str(len(body))

        conn = http.client.HTTPConnection('127.0.0.1', MCP_INTERNAL_PORT, timeout=None)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status, resp.reason)
            for name, value in resp.getheaders():
                if name.lower() not in _SKIP_RESPONSE:
                    self.send_header(name, value)
            self.send_header('Connection', 'close')
            self.end_headers()
            while True:
                chunk = resp.read1(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            _log('ERROR', f'MCP proxy error: {e}')
            try:
                self.send_error(502, 'Playwright MCP unavailable')
            except Exception:
                pass
        finally:
            conn.close()


def start(cdp_endpoint, log):
    """Start the token proxy and the Node MCP server. Returns False if disabled."""
    global _log
    _log = log
    if not MCP_PORT:
        return False
    if len(MCP_TOKEN) < MIN_TOKEN_LENGTH:
        _log('ERROR', f'Playwright MCP not started: mcp_token must be at least {MIN_TOKEN_LENGTH} characters.')
        return False
    os.makedirs(MCP_OUTPUT_DIR, exist_ok=True)
    threading.Thread(target=_node_supervisor, args=(cdp_endpoint,), daemon=True).start()
    srv = http.server.ThreadingHTTPServer(('0.0.0.0', MCP_PORT), McpHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _log('INFO', f'Playwright MCP endpoint on port {MCP_PORT} (/mcp, bearer token required).')
    return True


def stop():
    global _stopping
    with _node_lock:
        _stopping = True
        proc = _node_proc
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
