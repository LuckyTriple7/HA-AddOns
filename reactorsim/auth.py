#!/usr/bin/env python3
"""Anmeldung.

Ein einziges Konto, Zugangsdaten aus der Umgebung (also aus der
Dockge-Konfiguration). Mehrbenutzerbetrieb spaeter.

Grundsaetze:

* **Ohne Passwort steht die Seite nicht offen.** Ist keines gesetzt, erzeugt
  ReactorSim beim ersten Start eines, schreibt es EINMAL ins Protokoll und legt
  nur den Hash auf der Platte ab. Ein Dienst, der im Internet steht und auf ein
  gesetztes Passwort hofft, ist ein Dienst ohne Passwort.
* Der Hash entsteht ueber werkzeug.security (scrypt). Das Klartextpasswort aus
  der Umgebung wird beim Start gehasht und danach nicht mehr angefasst.
* Die Sitzung haengt an einem signierten Token (itsdangerous), nicht an einer
  Liste im Speicher -- so ueberlebt sie einen Neustart des Containers und
  kostet keinen Zustand.
* Der Signierschluessel liegt in /data und wird beim ersten Start erzeugt.
  Faellt er weg, sind alle Sitzungen ungueltig -- mehr passiert nicht.
"""

from __future__ import annotations

import logging
import os
import secrets
import string
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

import atomic_io

log = logging.getLogger(__name__)

SESSION_COOKIE = 'rs_session'
SESSION_MAX_AGE = 30 * 24 * 3600      # 30 Tage
CSRF_MAX_AGE = 3600                    # eine Stunde fuer das Anmeldeformular

# Kein Zeichen, das sich in einer Protokollzeile oder beim Abtippen
# missverstehen laesst -- das Passwort wird genau einmal angezeigt.
_ALPHABET = string.ascii_letters.replace('l', '').replace('I', '').replace('O', '') \
    + string.digits.replace('0', '').replace('1', '')


class Auth:
    def __init__(self, data_dir: str, user: str, password: str | None):
        self._dir = Path(data_dir)
        self.user = (user or 'admin').strip() or 'admin'
        self._auth_path = self._dir / 'auth.json'
        self._key_path = self._dir / 'secret.key'
        self._hash = self._resolve_password(password)
        self._serializer = URLSafeTimedSerializer(self._secret(), salt='rs-session')
        self._csrf = URLSafeTimedSerializer(self._secret(), salt='rs-csrf')

    # ── Einrichtung ───────────────────────────────────────────────────────────

    def _resolve_password(self, password: str | None) -> str:
        """Passwort aus der Umgebung, sonst der gespeicherte Hash, sonst neu."""
        if password:
            # Gesetztes Passwort gewinnt immer. Wer es in der Dockge-Konfiguration
            # aendert, hat es beim naechsten Start geaendert -- ohne Umweg ueber
            # eine Datei, die noch das alte traegt.
            return generate_password_hash(password)

        stored = self._read_stored_hash()
        if stored:
            return stored

        generated = ''.join(secrets.choice(_ALPHABET) for _ in range(16))
        digest = generate_password_hash(generated)
        self._write_stored_hash(digest)
        log.warning('')
        log.warning('  Kein REACTORSIM_PASSWORD gesetzt -- ein Passwort wurde erzeugt:')
        log.warning('')
        log.warning('      Benutzer:  %s', self.user)
        log.warning('      Passwort:  %s', generated)
        log.warning('')
        log.warning('  Es steht NUR hier. Auf der Platte liegt nur der Hash.')
        log.warning('  Dauerhaft besser: REACTORSIM_PASSWORD in der Konfiguration setzen.')
        log.warning('')
        return digest

    def _read_stored_hash(self) -> str | None:
        try:
            import json
            with open(self._auth_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            digest = data.get('password_hash')
            return digest if isinstance(digest, str) and digest else None
        except (OSError, ValueError):
            return None

    def _write_stored_hash(self, digest: str) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            atomic_io.write_json(str(self._auth_path), {'password_hash': digest}, mode=0o600)
        except OSError as exc:
            # Nicht schreiben zu koennen ist kein Grund, die Seite offen zu
            # lassen -- das Passwort gilt dann nur bis zum naechsten Neustart.
            log.error('auth.json nicht schreibbar (%s) -- das erzeugte Passwort gilt '
                      'nur bis zum Neustart', exc.__class__.__name__)

    def _secret(self) -> bytes:
        try:
            return self._key_path.read_bytes()
        except OSError:
            pass
        key = secrets.token_bytes(32)
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            atomic_io.write_bytes(str(self._key_path), key, mode=0o600)
        except OSError:
            log.error('secret.key nicht schreibbar -- Sitzungen enden mit dem Neustart')
        return key

    # ── Anmeldung ─────────────────────────────────────────────────────────────

    def check(self, user: str, password: str) -> bool:
        """Benutzer und Passwort pruefen.

        Das Passwort wird IMMER geprueft, auch bei falschem Benutzernamen --
        sonst verraet die Antwortzeit, welcher Name existiert.
        """
        ok_user = secrets.compare_digest((user or '').strip(), self.user)
        ok_pass = check_password_hash(self._hash, password or '')
        return ok_user and ok_pass

    def issue(self) -> str:
        return self._serializer.dumps({'u': self.user})

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        try:
            data = self._serializer.loads(token, max_age=SESSION_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return False
        return isinstance(data, dict) and data.get('u') == self.user

    # ── CSRF fuer das Anmeldeformular ─────────────────────────────────────────

    def csrf_token(self) -> str:
        return self._csrf.dumps('login')

    def csrf_ok(self, token: str | None) -> bool:
        if not token:
            return False
        try:
            return self._csrf.loads(token, max_age=CSRF_MAX_AGE) == 'login'
        except (BadSignature, SignatureExpired):
            return False


def safe_next(raw: str | None) -> str:
    """Nur anwendungseigene Pfade duerfen Sprungziel nach der Anmeldung sein.

    Ohne diese Pruefung waere ?next=https://fremde.seite eine offene
    Weiterleitung: die Anmeldeseite der eigenen Anlage wuerde Besucher auf eine
    fremde schicken. Das Ergebnis wird aus den geparsten Bestandteilen per
    `urlunsplit` neu zusammengesetzt statt den Rohwert durchzureichen -- erst
    das unterbricht die Taint-Kette (CodeQL erkennt sonst auch nach den
    Pruefungen noch eine offene Weiterleitung).
    """
    value = (raw or '/').replace('\\', '/')
    if any(ord(c) < 32 for c in value):
        return '/'
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or not parts.path.startswith('/') or parts.path.startswith('//'):
        return '/'
    return urlunsplit(('', '', parts.path, parts.query, parts.fragment))
