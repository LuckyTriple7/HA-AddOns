"""Spiegelt den eigenen WhatsApp-Status als Signal- und/oder Telegram-Story.

Laeuft als Hintergrund-Thread im Portal. Alle paar Minuten fragt er beim
WhatsApp-Add-on die laufenden eigenen Statusmeldungen ab (/api/my-status) und
postet neue davon ueber /api/my-status/media der Ziel-Add-ons (Signal ab
1.7.5, Telegram ab 1.7.31). Beide nehmen nur Medien: Text-Status werden als
Bild gerendert. Signal traegt keine Bildunterschrift, Telegram keine Videos.

Beim ersten Lauf werden nur die schon laufenden Meldungen als bekannt
vermerkt — gespiegelt wird erst, was danach neu dazukommt.
"""
import io
import json
import logging
import os
import secrets
import threading
import textwrap
import time
import urllib.error
import urllib.request
from urllib.parse import quote

log = logging.getLogger(__name__)

STATE_PATH = '/data/status_mirror.json'   # {ziel: {initialized, seen, tries, last_ok, last_error}}
SETTINGS_PATH = '/data/status_mirror_settings.json'   # {ziel: an/aus}, gesetzt in der Oberflaeche
INTERVAL_S = 300
# Medien laedt das WhatsApp-Add-on erst beim Abfragen herunter; fehlt die Datei
# so lange nach dem Posten noch, kommt sie nicht mehr (download_media aus)
MEDIA_GRACE_S = 15 * 60
MAX_TRIES = 3
KEEP_S = 48 * 3600

TEXT_BG = (0x0a, 0x5f, 0x55)   # Standardfarbe der WhatsApp-Text-Status
FONT_PATH = '/usr/share/fonts/dejavu/DejaVuSans.ttf'
MIME_BY_EXT = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
               'webp': 'image/webp', 'mp4': 'video/mp4', 'webm': 'video/webm'}


def _load_state() -> dict:
    try:
        with open(STATE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_state(state: dict) -> None:
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f)
    os.replace(tmp, STATE_PATH)


def _get(url: str, timeout: float = 60.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def _post_file(url: str, filename: str, mime: str, data: bytes, caption: str = '') -> None:
    boundary = 'mp' + secrets.token_hex(12)
    head = b''
    if caption:
        head = (f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n'
                f'{caption}\r\n').encode()
    body = head + b''.join([
        f'--{boundary}\r\n'.encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        f'Content-Type: {mime}\r\n\r\n'.encode(),
        data,
        f'\r\n--{boundary}--\r\n'.encode(),
    ])
    req = urllib.request.Request(url, data=body, method='POST', headers={
        'Content-Type': f'multipart/form-data; boundary={boundary}'})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = ''
        try:
            detail = json.loads(e.read()).get('error', '')
        except Exception:
            pass
        raise RuntimeError(f'HTTP {e.code} {detail}'.strip()) from None


def render_text(text: str) -> bytes:
    """Text-Status als Hochkant-Bild (1080x1920), Text zentriert."""
    from PIL import Image, ImageDraw, ImageFont
    w, h = 1080, 1920
    # Zeichen ohne Glyphe (v. a. Emojis) weglassen statt Kaestchen zu malen:
    # sie ergeben dieselbe Maske wie ein sicher fehlendes Zeichen
    try:
        probe = ImageFont.truetype(FONT_PATH, 40)
        tofu = bytes(probe.getmask('\U0010FFFD'))
        known: dict = {}

        def has_glyph(ch: str) -> bool:
            if ch.isspace() or ord(ch) < 0x250:
                return True
            if ch not in known:
                known[ch] = bytes(probe.getmask(ch)) != tofu
            return known[ch]
        text = '\n'.join(' '.join(''.join(c for c in line if has_glyph(c)).split())
                         for line in text.splitlines()).strip() or text
    except OSError:
        pass
    img = Image.new('RGB', (w, h), TEXT_BG)
    draw = ImageDraw.Draw(img)
    # Lange Texte kleiner setzen, damit sie aufs Bild passen
    for size in (84, 72, 60, 50, 42, 36):
        try:
            font = ImageFont.truetype(FONT_PATH, size)
        except OSError:
            font = ImageFont.load_default(size)
        width = max(10, int(w * 0.84 / (size * 0.55)))
        lines = []
        for para in text.splitlines() or ['']:
            lines.extend(textwrap.wrap(para, width) or [''])
        spacing = int(size * 0.35)
        block = draw.multiline_textbbox((0, 0), '\n'.join(lines), font=font,
                                        spacing=spacing, align='center')
        if block[3] - block[1] <= h * 0.8:
            break
    draw.multiline_text((w / 2, h / 2), '\n'.join(lines), font=font, fill='white',
                        anchor='mm', spacing=spacing, align='center')
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()


# Ziele: Name fuer das Log, nimmt Videos an?, uebernimmt Bildunterschrift?
TARGETS = {
    'signal':   {'label': 'Signal',   'video': True,  'caption': False},
    'telegram': {'label': 'Telegram', 'video': False, 'caption': True},
}

_wake = threading.Event()
_last_error = ''   # letzter Fehler beim Abfragen von WhatsApp


def get_settings() -> dict:
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}
    return {icon: bool(data.get(icon)) for icon in TARGETS}


def set_settings(new: dict) -> dict:
    cur = get_settings()
    cur.update({icon: bool(new[icon]) for icon in TARGETS if icon in new})
    tmp = SETTINGS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cur, f)
    os.replace(tmp, SETTINGS_PATH)
    log.info('Status-Spiegel: %s', ', '.join(f"{TARGETS[i]['label']} {'an' if v else 'aus'}"
                                             for i, v in cur.items()))
    _wake.set()   # sofort einen Lauf anstossen statt bis zu 5 Minuten zu warten
    return cur


def info() -> dict:
    """Schalter und letzter Stand je Ziel, fuer die Oberflaeche."""
    settings, state = get_settings(), _load_state()
    return {
        'error': _last_error,
        'targets': {icon: {'enabled': settings[icon],
                           'last_ok': (state.get(icon) or {}).get('last_ok'),
                           'last_error': (state.get(icon) or {}).get('last_error', '')}
                    for icon in TARGETS},
    }


def mirror_once(wa_base: str, targets: dict) -> None:
    """targets: {icon: Basis-URL} der eingeschalteten Ziele."""
    raw = json.loads(_get(wa_base + 'api/my-status'))
    msgs = sorted(raw.get('msgs') or [], key=lambda m: m.get('timestamp') or 0)
    state = _load_state()
    now = time.time()
    for icon, base in targets.items():
        _mirror_target(wa_base, icon, base, msgs, state.setdefault(icon, {}), now)
        _save_state(state)


def _mirror_target(wa_base: str, icon: str, base: str, msgs: list, st: dict, now: float) -> None:
    spec = TARGETS[icon]
    label = spec['label']
    seen: dict = st.setdefault('seen', {})
    tries: dict = st.setdefault('tries', {})

    if not st.get('initialized'):
        for m in msgs:
            seen[m['id']] = m.get('timestamp') or 0
        st['initialized'] = True
        log.info('Status-Spiegel %s: eingeschaltet, %d laufende Meldung(en) bleiben außen vor', label, len(msgs))
        return

    for m in msgs:
        mid = m.get('id')
        if not mid or mid in seen:
            continue
        kind = m.get('type')
        ts = m.get('timestamp') or 0
        age = now - ts / 1000
        caption = (m.get('body') or '').strip() if spec['caption'] else ''
        try:
            if kind == 'text':
                text = (m.get('body') or '').strip()
                if not text:
                    seen[mid] = ts
                    continue
                payload, name, mime, caption = render_text(text), 'status.png', 'image/png', ''
            elif kind == 'video' and not spec['video']:
                log.info('Status-Spiegel %s: Video übersprungen (nimmt nur Bilder)', label)
                seen[mid] = ts
                continue
            else:
                fname = m.get('mediaFile')
                if not fname:
                    if age < MEDIA_GRACE_S:
                        continue   # Datei kommt vielleicht noch
                    log.warning('Status-Spiegel %s: %s ohne Mediendatei übersprungen '
                                '(download_media im WhatsApp-Add-on an?)', label, kind)
                    st['last_error'] = 'no_media'
                    seen[mid] = ts
                    continue
                ext = fname.rsplit('.', 1)[-1].lower()
                payload = _get(wa_base + 'api/media/' + quote(fname))
                name, mime = fname, MIME_BY_EXT.get(ext, 'image/jpeg')
            _post_file(base + 'api/my-status/media', name, mime, payload, caption)
            seen[mid] = ts
            tries.pop(mid, None)
            st['last_ok'] = int(now * 1000)
            st['last_error'] = ''
            log.info('Status-Spiegel %s: WhatsApp-%s als Story gepostet', label, kind)
        except Exception as e:
            n = tries.get(mid, 0) + 1
            tries[mid] = n
            st['last_error'] = str(e)[:200]
            if n >= MAX_TRIES:
                seen[mid] = ts
                tries.pop(mid, None)
                log.warning('Status-Spiegel %s: %s nach %d Versuchen aufgegeben: %s', label, kind, n, e)
            else:
                log.warning('Status-Spiegel %s: %s fehlgeschlagen (Versuch %d): %s', label, kind, n, e)

    cutoff = (now - KEEP_S) * 1000
    st['seen'] = {k: v for k, v in seen.items() if not v or v >= cutoff}


def start(get_config, base_url_for) -> None:
    """get_config() liefert die Add-on-Optionen, base_url_for(m) die interne
    Basis-URL eines Messenger-Eintrags (mit Slash am Ende)."""
    def loop():
        global _last_error
        while True:
            try:
                settings = get_settings()
                on = [icon for icon in TARGETS if settings[icon]]
                # Ausgeschaltete Ziele vergessen: beim Wiedereinschalten nichts Altes nachholen
                state = _load_state()
                if any(icon in state for icon in TARGETS if icon not in on):
                    _save_state({k: v for k, v in state.items() if k in on})
                if on:
                    by_icon = {str(m.get('icon', '')).lower(): m
                               for m in get_config().get('messengers', [])
                               if m.get('enabled', True) and m.get('port')}
                    targets = {icon: base_url_for(by_icon[icon]) for icon in on if icon in by_icon}
                    if 'whatsapp' in by_icon and targets:
                        mirror_once(base_url_for(by_icon['whatsapp']), targets)
                _last_error = ''
            except Exception as e:
                _last_error = str(e)[:200]
                log.warning('Status-Spiegel: Abfrage fehlgeschlagen: %s', e)
            _wake.wait(INTERVAL_S)
            _wake.clear()

    threading.Thread(target=loop, name='status-mirror', daemon=True).start()
