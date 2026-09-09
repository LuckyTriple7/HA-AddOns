"""Wächter-Zustände als Entitäten in Home Assistant.

Über die Core-API des Supervisors (`homeassistant_api: true` in der
config.yaml). Geschrieben wird direkt in den Zustandsspeicher — dieselbe
Technik, mit der Home Assistant selbst Zustände von Integrationen ablegt.
Solche Entitäten überleben einen Neustart von Home Assistant nicht; sie
entstehen beim nächsten Durchlauf von selbst neu, weshalb hier bewusst
regelmäßig geschrieben wird statt nur bei Änderungen.

Kein MQTT, keine Discovery: das würde einen Broker voraussetzen, den nicht
jede Installation hat, und dieses Add-on läuft ohnehin unter dem Supervisor.
"""

import logging
import os
import re
import unicodedata

import requests

log = logging.getLogger('nettoolbox.ha')

SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN', '')
CORE_API = 'http://supervisor/core/api'
TIMEOUT = 10

# Zustandsstufe -> (Symbol, Anzeigetext). Die Texte sind wie im übrigen
# Monitoring-Modul deutsch und bewusst nicht übersetzt: sie landen in Home
# Assistant, nicht in der Oberfläche dieses Add-ons.
_LEVEL_ICON = {
    'ok': 'mdi:check-circle',
    'info': 'mdi:information',
    'warn': 'mdi:alert',
    'fail': 'mdi:alert-circle',
    '': 'mdi:help-circle',
}
_PROBE_NAME = {
    'tls': 'TLS-Zertifikat', 'blacklist': 'Sperrlisten',
    'mail_health': 'Mail-Gesundheit', 'aaaa_guard': 'AAAA-Wächter',
    'whois': 'Domain-Ablauf', 'http': 'Erreichbarkeit', 'seo': 'SEO',
    'http_status': 'HTTP-Statuscode',
}


def available() -> bool:
    return bool(SUPERVISOR_TOKEN)


def slug(text: str) -> str:
    """Entitäts-tauglicher Name: nur Kleinbuchstaben, Ziffern, Unterstrich."""
    text = unicodedata.normalize('NFKD', text or '')
    text = text.encode('ascii', 'ignore').decode('ascii').lower()
    text = re.sub(r'[^a-z0-9]+', '_', text).strip('_')
    return text[:48] or 'monitor'


def _post(session: requests.Session, entity: str, payload: dict) -> bool:
    try:
        response = session.post(f'{CORE_API}/states/{entity}',
                                headers={'Authorization': f'Bearer {SUPERVISOR_TOKEN}'},
                                json=payload, timeout=TIMEOUT)
        return response.status_code < 300
    except requests.RequestException as e:
        log.warning("HA-Entität %s nicht geschrieben: %s", entity, type(e).__name__)
        return False


def push(monitors: list) -> int:
    """Ein Sensor je Wächter plus zwei Sammelentitäten. Gibt zurück, wie
    viele Entitäten geschrieben wurden.

    Scheitert der Zugriff, ist das eine Protokollzeile und kein Fehler: das
    Monitoring selbst hängt nicht daran.
    """
    if not available():
        return 0

    written = 0
    seen = set()
    session = requests.Session()
    for m in monitors:
        name = slug(m.get('name') or f"monitor_{m.get('id')}")
        # Zwei Wächter mit gleichem Namen ergäben dieselbe Entität -- die ID
        # hängt nur im Konfliktfall dran, damit die Namen sonst lesbar bleiben.
        if name in seen:
            name = f"{name}_{m.get('id')}"
        seen.add(name)
        level = m.get('last_level') or ''
        state = level or 'unknown'
        attributes = {
            'friendly_name': f"NetToolbox {m.get('name') or name}",
            'icon': _LEVEL_ICON.get(level, _LEVEL_ICON['']),
            'pruefung': _PROBE_NAME.get(m.get('probe'), m.get('probe') or ''),
            'ziel': m.get('target') or '',
            'zusammenfassung': m.get('last_summary') or '',
            'intervall_stunden': m.get('interval_hours') or 0,
            'aktiv': bool(m.get('enabled', 1)),
            'letzter_fehler': m.get('last_error') or '',
        }
        if m.get('last_run_ts'):
            attributes['zuletzt_geprueft'] = int(m['last_run_ts'])
        if _post(session, f'sensor.nettoolbox_{name}',
                 {'state': state, 'attributes': attributes}):
            written += 1

    problems = [m for m in monitors
                if (m.get('last_level') or '') in ('warn', 'fail')]
    if _post(session, 'sensor.nettoolbox_probleme',
             {'state': len(problems),
              'attributes': {'friendly_name': 'NetToolbox Probleme',
                             'icon': 'mdi:alert-decagram',
                             'unit_of_measurement': 'Wächter',
                             'betroffen': [m.get('name') for m in problems],
                             'waechter_gesamt': len(monitors)}}):
        written += 1
    if _post(session, 'binary_sensor.nettoolbox_problem',
             {'state': 'on' if problems else 'off',
              'attributes': {'friendly_name': 'NetToolbox Problem',
                             'icon': 'mdi:lan-connect',
                             'device_class': 'problem'}}):
        written += 1
    return written
