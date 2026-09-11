#!/usr/bin/env python3
"""Anmeldung: ohne Sitzung kommt niemand rein.

Der wichtigste Test hier ist der erste. Ein Dienst, der im Internet steht, darf
keinen Pfad haben, der ohne Anmeldung Inhalte liefert -- ausser dem
Healthcheck, den der Container selbst abfragt.
"""

import os
import re
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

USER = 'operator'
PASSWORD = 'sehr-geheim-123'


def _fresh(tmp_path, monkeypatch, user=USER, password=PASSWORD):
    monkeypatch.setenv('REACTORSIM_BASE', _ROOT)
    monkeypatch.setenv('REACTORSIM_DATA', str(tmp_path))
    monkeypatch.setenv('REACTORSIM_USER', user)
    if password is None:
        monkeypatch.delenv('REACTORSIM_PASSWORD', raising=False)
    else:
        monkeypatch.setenv('REACTORSIM_PASSWORD', password)
    for mod in ('app', 'auth', 'persist', 'scoring', 'atomic_io'):
        sys.modules.pop(mod, None)
    import app as appmod
    appmod.app.config['TESTING'] = True
    return appmod


@pytest.fixture()
def client(tmp_path, monkeypatch):
    return _fresh(tmp_path, monkeypatch).app.test_client()


def _csrf(client):
    html = client.get('/login').get_data(as_text=True)
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    assert m, 'kein CSRF-Token im Formular'
    return m.group(1)


def _login(client, user=USER, password=PASSWORD, **extra):
    data = {'user': user, 'password': password, 'csrf': _csrf(client), 'next': '/'}
    data.update(extra)
    return client.post('/login', data=data)


@pytest.mark.parametrize('path', [
    '/', '/api/meta', '/api/saves', '/api/highscores',
    '/s/0.0.1/js/main.js', '/s/0.0.1/css/base.css',
    '/static/js/main.js',
])
def test_nothing_is_reachable_without_login(client, path):
    r = client.get(path)
    assert r.status_code in (302, 401), f'{path} antwortet {r.status_code}'
    if r.status_code == 302:
        assert '/login' in r.headers['Location']


def test_health_stays_open(client):
    # Der Healthcheck laeuft im Container ohne Cookie -- waere er geschuetzt,
    # meldete Docker den Container dauerhaft als krank.
    r = client.get('/health')
    assert r.status_code == 200
    assert r.get_json()['status'] == 'ok'


def test_login_page_is_self_contained(client):
    html = client.get('/login').get_data(as_text=True)
    # Sie darf nichts nachladen, was selbst hinter der Anmeldung liegt.
    assert '<link' not in html
    assert '<script' not in html
    assert 'noindex' in html


def test_correct_credentials_open_everything(client):
    r = _login(client)
    assert r.status_code == 302
    assert r.headers['Location'].endswith('/')
    assert client.get('/').status_code == 200
    assert client.get('/api/meta').status_code == 200


@pytest.mark.parametrize('user,password', [
    (USER, 'falsch'),
    ('admin', PASSWORD),
    ('', ''),
    (USER, PASSWORD + ' '),
])
def test_wrong_credentials_rejected(client, user, password):
    r = _login(client, user=user, password=password)
    assert r.status_code == 401
    assert client.get('/api/meta').status_code == 401


def test_csrf_required(client):
    r = client.post('/login', data={'user': USER, 'password': PASSWORD, 'next': '/'})
    assert r.status_code == 401
    assert client.get('/api/meta').status_code == 401


def test_open_redirect_blocked(client):
    for target in ('https://evil.example', '//evil.example', '\\\\evil.example',
                   'javascript:alert(1)'):
        r = _login(client, next=target)
        assert r.status_code == 302
        assert 'evil' not in r.headers['Location']
        assert 'javascript' not in r.headers['Location']


def test_logout_ends_the_session(client):
    _login(client)
    assert client.get('/api/meta').status_code == 200
    client.get('/logout')
    assert client.get('/api/meta').status_code == 401


def test_session_cookie_is_httponly(client):
    r = _login(client)
    cookie = r.headers.get('Set-Cookie', '')
    assert 'HttpOnly' in cookie
    assert 'SameSite=Lax' in cookie


def test_brute_force_is_limited(client):
    for _ in range(10):
        _login(client, password='falsch')
    r = _login(client, password='falsch')
    html = r.get_data(as_text=True)
    assert 'Versuche' in html or 'attempts' in html


def test_forged_session_cookie_rejected(client):
    client.set_cookie('rs_session', 'ich-bin-angemeldet')
    assert client.get('/api/meta').status_code == 401


def test_generated_password_when_none_configured(tmp_path, caplog):
    """Ohne gesetztes Passwort wird eines erzeugt -- und nur als Hash abgelegt.

    Geprueft wird direkt am Modul, nicht ueber die App: app.py ruft beim Import
    logging.basicConfig(force=True) und raeumt dabei jeden Testmitschnitt weg.
    """
    import logging
    sys.modules.pop('auth', None)
    sys.modules.pop('atomic_io', None)
    import auth as authmod

    caplog.set_level(logging.WARNING, logger='auth')
    a = authmod.Auth(str(tmp_path), 'operator', None)
    m = re.search(r'Passwort:\s+(\S+)', caplog.text)
    assert m, f'kein erzeugtes Passwort im Protokoll: {caplog.text!r}'
    generated = m.group(1)
    assert len(generated) == 16
    assert a.check('operator', generated)
    assert not a.check('operator', 'falsch')

    stored = (tmp_path / 'auth.json').read_text(encoding='utf-8')
    assert generated not in stored, 'Klartextpasswort auf der Platte'
    assert 'password_hash' in stored
    assert oct(os.stat(tmp_path / 'auth.json').st_mode)[-3:] == '600'
    assert oct(os.stat(tmp_path / 'secret.key').st_mode)[-3:] == '600'

    # Neustart ohne gesetztes Passwort: der gespeicherte Hash gilt weiter,
    # es wird kein zweites erzeugt.
    caplog.clear()
    b = authmod.Auth(str(tmp_path), 'operator', None)
    assert b.check('operator', generated)
    assert 'Passwort:' not in caplog.text


def test_app_without_configured_password_still_requires_login(tmp_path, monkeypatch):
    mod = _fresh(tmp_path, monkeypatch, password=None)
    c = mod.app.test_client()
    assert c.get('/api/meta').status_code == 401
    assert c.get('/').status_code == 302


def test_configured_password_wins_over_stored(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, password=None)          # erzeugt und speichert
    mod = _fresh(tmp_path, monkeypatch, password='neues-passwort')
    c = mod.app.test_client()
    html = c.get('/login').get_data(as_text=True)
    csrf = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
    r = c.post('/login', data={'user': USER, 'password': 'neues-passwort', 'csrf': csrf, 'next': '/'})
    assert r.status_code == 302


def test_session_survives_restart(tmp_path, monkeypatch):
    mod = _fresh(tmp_path, monkeypatch)
    c = mod.app.test_client()
    html = c.get('/login').get_data(as_text=True)
    csrf = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
    r = c.post('/login', data={'user': USER, 'password': PASSWORD, 'csrf': csrf, 'next': '/'})
    token = r.headers['Set-Cookie'].split('rs_session=')[1].split(';')[0]

    # Neustart: derselbe Datenordner, also derselbe Signierschluessel.
    mod2 = _fresh(tmp_path, monkeypatch)
    c2 = mod2.app.test_client()
    c2.set_cookie('rs_session', token)
    assert c2.get('/api/meta').status_code == 200
