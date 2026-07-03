"""Kontakte aus einem Nextcloud-Adressbuch (CardDAV) auslesen — nur Name + E-Mail,
keine volle vCard-Fidelity, daher kein `vobject`/`caldav`, nur `requests` + Stdlib-XML.

Die Adressbuch-URL kommt komplett vom Nutzer (Nextcloud zeigt sie in der Kontakte-App
zum Kopieren an) — kein Zusammenbauen aus Server/Nutzername/Adressbuchname hier.
"""
import logging
import re
import xml.etree.ElementTree as ET

import requests

log = logging.getLogger("tuiwatch")

_NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:carddav"}
_REPORT_BODY = (
    '<c:addressbook-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
    '<d:prop><d:getetag/><c:address-data/></d:prop>'
    '</c:addressbook-query>'
)
_EMAIL_RE = re.compile(r"^EMAIL[^:]*:(.+)$", re.MULTILINE)
_FN_RE = re.compile(r"^FN:(.+)$", re.MULTILINE)


def _unfold(vcard: str) -> str:
    """vCard-Zeilenumbrüche auflösen: Fortsetzungszeilen beginnen mit Leerzeichen/Tab
    und gehören zur vorherigen Zeile (RFC 6350 Line Folding)."""
    out = []
    for line in vcard.splitlines():
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return "\n".join(out)


def _parse_vcard(vcard: str) -> list:
    """Ein vCard-Text → Liste von {name, email} (ein Eintrag je E-Mail-Adresse)."""
    text = _unfold(vcard)
    m = _FN_RE.search(text)
    name = (m.group(1).strip() if m else "") or ""
    return [{"name": name, "email": e.strip()} for e in _EMAIL_RE.findall(text) if e.strip()]


def parse_carddav_response(xml_bytes: bytes) -> list:
    """CardDAV-Multistatus-XML → Kontaktliste [{name, email}], alphabetisch nach Name."""
    root = ET.fromstring(xml_bytes)
    contacts = []
    for resp in root.findall("d:response", _NS):
        for data in resp.findall("d:propstat/d:prop/c:address-data", _NS):
            if data.text:
                contacts.extend(_parse_vcard(data.text))
    contacts.sort(key=lambda c: c["name"].lower())
    return contacts


def fetch_contacts(addressbook_url: str, user: str, app_password: str,
                   *, verbose: bool = False) -> list:
    """Kontakte eines Nextcloud-Adressbuchs holen. Bei Netzwerk-/Parse-Fehler: leere
    Liste (kein Crash — der E-Mail-Versand per Freitext bleibt davon unberührt)."""
    if not addressbook_url or not user:
        return []
    try:
        resp = requests.request(
            "REPORT", addressbook_url, auth=(user, app_password), data=_REPORT_BODY,
            headers={"Content-Type": "application/xml; charset=utf-8", "Depth": "1"},
            timeout=20)
        if resp.status_code not in (200, 207):
            if verbose:
                log.warning("Nextcloud-Kontakte: HTTP %s", resp.status_code)
            return []
        contacts = parse_carddav_response(resp.content)
    except Exception as e:
        if verbose:
            log.warning("Nextcloud-Kontakte-Fehler: %s: %s", type(e).__name__, e)
        return []
    if verbose:
        log.info("Nextcloud-Kontakte: %d gefunden", len(contacts))
    return contacts
