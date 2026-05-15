#!/usr/bin/env python3
"""
CDP proxy for the Playwright Browser Home Assistant add-on.

Problem: Chromium returns ws://localhost:INTERNAL_PORT/... in CDP responses.
External clients (other containers) cannot resolve 'localhost' to this container.

Solution: proxy all CDP traffic, rewrite localhost in JSON responses to the
container hostname so WebSocket URLs are externally reachable.

WebSocket connections (/devtools/*) are forwarded transparently as raw bytes.
"""
import http.client
import http.server
import os
import socket
import sys
import threading

INTERNAL_HOST = '127.0.0.1'
INTERNAL_PORT = int(os.environ.get('INTERNAL_PORT', '9223'))
EXTERNAL_PORT = int(os.environ.get('EXTERNAL_PORT', '9222'))
EXTERNAL_HOST = socket.gethostname()

_SRCS = [
    f'localhost:{INTERNAL_PORT}'.encode(),
    f'127.0.0.1:{INTERNAL_PORT}'.encode(),
]
_DST = f'{EXTERNAL_HOST}:{EXTERNAL_PORT}'.encode()


def rewrite(body: bytes) -> bytes:
    for src in _SRCS:
        body = body.replace(src, _DST)
    return body


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.headers.get('Upgrade', '').lower() == 'websocket':
            self._proxy_ws()
        else:
            self._proxy_http()

    def _proxy_http(self):
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
        backend = None
        try:
            backend = socket.create_connection((INTERNAL_HOST, INTERNAL_PORT), timeout=10)

            lines = [f'GET {self.path} HTTP/1.1']
            for k, v in self.headers.items():
                lines.append('Host: localhost' if k.lower() == 'host' else f'{k}: {v}')
            lines += ['', '']
            backend.sendall('\r\n'.join(lines).encode())

            client = self.connection

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
            sys.stderr.write(f'WS error: {e}\n')
            sys.stderr.flush()
        finally:
            if backend:
                try:
                    backend.close()
                except Exception:
                    pass


if __name__ == '__main__':
    srv = http.server.ThreadingHTTPServer(('0.0.0.0', EXTERNAL_PORT), Handler)
    print(f'CDP proxy :{EXTERNAL_PORT} -> {INTERNAL_HOST}:{INTERNAL_PORT} (hostname: {EXTERNAL_HOST})', flush=True)
    srv.serve_forever()
