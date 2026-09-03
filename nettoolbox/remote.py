"""Where a probe actually runs.

At home the add-on sits behind a consumer line: port 25 is usually blocked and
the big blocklists refuse questions coming through a public resolver. On a root
server with a fixed address none of that applies. So the same image can either
run a probe itself or hand it to a second instance that acts as a worker — the
front end never knows the difference.
"""

import time

import requests

import probes
from netcore import Context, ProbeError

PROTOCOL = 1
TOKEN_HEADER = 'X-Nettoolbox-Token'


class LocalBackend:
    """Runs the probe in this process."""

    kind = 'local'
    label = ''

    def __init__(self, ctx: Context):
        self.ctx = ctx

    def run(self, name: str, params: dict) -> dict:
        started = time.monotonic()
        result = probes.run(name, params, self.ctx)
        return {'result': result, 'backend': 'local',
                'ms': int((time.monotonic() - started) * 1000)}

    def ping(self) -> dict:
        return {'ok': True, 'kind': 'local'}


class RemoteBackend:
    """Hands the probe to a worker over HTTP."""

    kind = 'remote'

    def __init__(self, url: str, token: str, verify: bool = True,
                 timeout: float = 60.0):
        self.url = url.rstrip('/')
        self.token = token
        self.verify = verify
        self.timeout = timeout
        self.label = self.url

    def same_as(self, url: str, token: str, verify: bool) -> bool:
        return (self.url == (url or '').rstrip('/') and self.token == token
                and self.verify == verify)

    def _post(self, path: str, payload: dict) -> dict:
        try:
            resp = requests.post(self.url + path, json=payload,
                                 timeout=self.timeout, verify=self.verify,
                                 headers={TOKEN_HEADER: self.token,
                                          'Content-Type': 'application/json'})
        except requests.exceptions.SSLError:
            raise ProbeError('worker_tls')
        except requests.exceptions.Timeout:
            raise ProbeError('worker_timeout')
        except requests.RequestException:
            raise ProbeError('worker_unreachable')
        if resp.status_code in (401, 403):
            raise ProbeError('worker_auth')
        try:
            data = resp.json()
        except ValueError:
            raise ProbeError('worker_bad_response')
        if resp.status_code != 200 or not data.get('ok'):
            raise ProbeError(str(data.get('error') or 'worker_error')[:40],
                             str(data.get('detail') or '')[:200])
        return data

    def run(self, name: str, params: dict) -> dict:
        started = time.monotonic()
        data = self._post('/worker/probe', {'probe': name, 'params': params,
                                            'protocol': PROTOCOL})
        return {'result': data.get('result') or {}, 'backend': 'remote',
                'worker': data.get('worker') or {},
                'ms': int((time.monotonic() - started) * 1000)}

    def ping(self) -> dict:
        started = time.monotonic()
        try:
            data = self._post('/worker/info', {'protocol': PROTOCOL})
        except ProbeError as e:
            return {'ok': False, 'kind': 'remote', 'url': self.url,
                    'error': e.code}
        info = data.get('worker') or {}
        info.update({'ok': True, 'kind': 'remote', 'url': self.url,
                     'ms': int((time.monotonic() - started) * 1000)})
        return info
