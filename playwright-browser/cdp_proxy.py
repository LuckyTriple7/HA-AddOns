#!/usr/bin/env python3
"""
CDP proxy with lazy Chromium start for the Playwright Browser Home Assistant add-on.

Chromium is started on the first incoming connection and stopped after
IDLE_TIMEOUT_MINUTES with no active WebSocket connections.
HTTP requests (e.g. /json/version health checks) do NOT reset the idle timer.
"""
import http.client
import http.server
import os
import socket
import subprocess
import sys
import threading
import time

INTERNAL_HOST = '127.0.0.1'
INTERNAL_PORT = int(os.environ.get('INTERNAL_PORT', '9223'))
EXTERNAL_PORT = int(os.environ.get('EXTERNAL_PORT', '9222'))
EXTERNAL_HOST = socket.gethostname()
CHROMIUM_BIN = os.environ.get('CHROMIUM_BIN', 'chromium')
TMPDIR = os.environ.get('CHROMIUM_TMPDIR', '/tmp/chromium-profile')
IDLE_TIMEOUT = int(os.environ.get('IDLE_TIMEOUT_MINUTES', '5')) * 60

_SRCS = [
    f'localhost:{INTERNAL_PORT}'.encode(),
    f'127.0.0.1:{INTERNAL_PORT}'.encode(),
]
_DST = f'{EXTERNAL_HOST}:{EXTERNAL_PORT}'.encode()

# State (protected by _lock)
_lock = threading.Lock()
_chromium_proc = None
_active_ws = 0
_last_activity = time.monotonic()


def log(level, msg):
    print(f'[{level}] [{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def rewrite(body: bytes) -> bytes:
    for src in _SRCS:
        body = body.replace(src, _DST)
    return body


def _chromium_cmd():
    return [
        CHROMIUM_BIN,
        '--headless',
        '--no-sandbox',
        '--disable-gpu',
        '--disable-gpu-compositing',
        '--disable-dev-shm-usage',
        '--disable-setuid-sandbox',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-background-networking',
        '--disable-client-side-phishing-detection',
        '--disable-sync',
        '--disable-translate',
        '--metrics-recording-only',
        '--safebrowsing-disable-auto-update',
        '--disable-extensions',
        '--disable-component-extensions-with-background-pages',
        '--mute-audio',
        '--no-pings',
        '--disable-features=MediaRouter,TranslateUI',
        f'--remote-debugging-port={INTERNAL_PORT}',
        f'--remote-debugging-address={INTERNAL_HOST}',
        f'--user-data-dir={TMPDIR}',
    ]


def _wait_ready(timeout=30):
    for _ in range(timeout):
        try:
            conn = http.client.HTTPConnection(INTERNAL_HOST, INTERNAL_PORT, timeout=1)
            conn.request('GET', '/json/version')
            resp = conn.getresponse()
            if resp.status == 200:
                resp.read()
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def ensure_chromium(trigger=''):
    """Start Chromium if not running. Blocks until ready. Returns True on success.
    Does NOT update _last_activity — only WS events do that."""
    global _chromium_proc, _last_activity
    with _lock:
        if _chromium_proc is not None and _chromium_proc.poll() is None:
            return True
        log('INFO', f'Chromium starting... (trigger: {trigger})')
        os.makedirs(TMPDIR, exist_ok=True)
        _chromium_proc = subprocess.Popen(
            _chromium_cmd(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # _lock held during wait — serialises concurrent connection attempts
        if not _wait_ready():
            log('ERROR', 'Chromium did not become ready in time!')
            try:
                _chromium_proc.kill()
            except Exception:
                pass
            _chromium_proc = None
            return False
        _last_activity = time.monotonic()  # reset idle timer once on startup
        log('INFO', 'Chromium ready.')
        return True


def stop_chromium():
    global _chromium_proc
    with _lock:
        if _chromium_proc is None or _chromium_proc.poll() is not None:
            return
        log('INFO', 'Chromium stopping (idle timeout reached).')
        _chromium_proc.terminate()
        try:
            _chromium_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _chromium_proc.kill()
        _chromium_proc = None
        log('INFO', 'Chromium stopped.')


def _idle_watcher():
    while True:
        time.sleep(30)
        with _lock:
            running = _chromium_proc is not None and _chromium_proc.poll() is None
            ws = _active_ws
            idle = time.monotonic() - _last_activity
        if running and ws == 0 and idle >= IDLE_TIMEOUT:
            log('INFO', f'Idle timeout reached ({int(idle)}s, limit={IDLE_TIMEOUT}s).')
            stop_chromium()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.headers.get('Upgrade', '').lower() == 'websocket':
            self._proxy_ws()
        else:
            self._proxy_http()

    def _proxy_http(self):
        if not ensure_chromium(f'HTTP {self.client_address[0]} {self.path}'):
            try:
                self.send_error(503, 'Chromium unavailable')
            except Exception:
                pass
            return
        try:
            conn = http.client.HTTPConnection(INTERNAL_HOST, INTERNAL_PORT, timeout=30)
            headers = dict(self.headers)
            headers['Host'] = 'localhost'
            conn.request('GET', self.path, headers=headers)
            resp = conn.getresponse()
            body = rewrite(resp.read())
            self.send_response(resp.status)
            for name, value in resp.getheaders():
                if name.lower() not in ('transfer-encoding', 'content-length', 'content-encoding'):
                    self.send_header(name, value)
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        except Exception as e:
            try:
                self.send_error(502, str(e))
            except Exception:
                pass

    def _proxy_ws(self):
        global _active_ws, _last_activity
        if not ensure_chromium(f'WebSocket {self.client_address[0]} {self.path}'):
            return
        backend = None
        try:
            backend = socket.create_connection((INTERNAL_HOST, INTERNAL_PORT), timeout=10)
            lines = [f'GET {self.path} HTTP/1.1']
            for k, v in self.headers.items():
                lines.append('Host: localhost' if k.lower() == 'host' else f'{k}: {v}')
            lines += ['', '']
            backend.sendall('\r\n'.join(lines).encode())

            client = self.connection
            with _lock:
                _active_ws += 1
                _last_activity = time.monotonic()
                ws_count = _active_ws
            log('INFO', f'Client connected: {self.client_address[0]} (active WebSocket connections: {ws_count})')

            def pipe(src, dst):
                try:
                    while True:
                        data = src.recv(65536)
                        if not data:
                            break
                        dst.sendall(data)
                except Exception:
                    pass
                finally:
                    try:
                        dst.shutdown(socket.SHUT_WR)
                    except Exception:
                        pass

            t = threading.Thread(target=pipe, args=(backend, client), daemon=True)
            t.start()
            pipe(client, backend)
            t.join(timeout=5)
        except Exception as e:
            sys.stderr.write(f'[ERROR] [{time.strftime("%H:%M:%S")}] WS error: {e}\n')
            sys.stderr.flush()
        finally:
            with _lock:
                _active_ws = max(0, _active_ws - 1)
                _last_activity = time.monotonic()
                ws_count = _active_ws
            log('INFO', f'Client disconnected: {self.client_address[0]} (active WebSocket connections: {ws_count})')
            if backend:
                try:
                    backend.close()
                except Exception:
                    pass


if __name__ == '__main__':
    os.makedirs(TMPDIR, exist_ok=True)
    threading.Thread(target=_idle_watcher, daemon=True).start()
    srv = http.server.ThreadingHTTPServer(('0.0.0.0', EXTERNAL_PORT), Handler)
    log('INFO', f'CDP proxy :{EXTERNAL_PORT} -> {INTERNAL_HOST}:{INTERNAL_PORT} (lazy start, idle={IDLE_TIMEOUT}s, hostname={EXTERNAL_HOST})')
    srv.serve_forever()
