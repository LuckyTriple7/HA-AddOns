"""Status-Ablage: Bilder, Videos und Text ueber den Tag sammeln und als
Status/Story an WhatsApp, Telegram und Signal posten — sofort oder geplant.

Hochgeladene Dateien werden beim Eingang verkleinert: Fotos auf hoechstens
1920 px als JPEG (nach der Lage im Handy gedreht), Videos mit ffmpeg auf
720p/H.264 und hoechstens 60 s. Signal bekommt beim Posten die ersten 30 s.

Ein Hintergrund-Thread postet faellige geplante Eintraege. Postet die Ablage
selbst nach WhatsApp und an weitere Ziele, sagt sie dem Status-Spiegel
Bescheid, damit der denselben Status nicht ein zweites Mal weiterreicht.
"""
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

import status_mirror

log = logging.getLogger(__name__)

QUEUE_DIR = '/data/status_queue'
INDEX_PATH = '/data/status_queue.json'
TARGETS = ('whatsapp', 'telegram', 'signal')
TICK_S = 15
KEEP_POSTED_S = 7 * 24 * 3600
IMG_MAX = 1920
THUMB_MAX = 360
VIDEO_MAX_S = 60
SIGNAL_VIDEO_MAX_S = 30
MAX_ITEMS = 200
ID_RE = re.compile(r'^q[0-9a-f]{16}$')
COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')

_lock = threading.Lock()
_wake = threading.Event()
_base_url_for = None
_get_config = None


# ── Speicher ──────────────────────────────────────────────────────────────────
def _load() -> list:
    try:
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(items: list) -> None:
    tmp = INDEX_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(items, f)
    os.replace(tmp, INDEX_PATH)


def _path(name: str) -> str | None:
    if not name or not re.match(r'^[\w.-]+$', name):
        return None
    p = os.path.realpath(os.path.join(QUEUE_DIR, name))
    return p if p.startswith(os.path.realpath(QUEUE_DIR) + os.sep) else None


def _update(item_id: str, **changes) -> dict | None:
    with _lock:
        items = _load()
        for it in items:
            if it['id'] == item_id:
                it.update(changes)
                _save(items)
                return dict(it)
    return None


def get(item_id: str) -> dict | None:
    if not ID_RE.match(item_id or ''):
        return None
    return next((it for it in _load() if it['id'] == item_id), None)


def file_path(item_id: str, which: str) -> str | None:
    it = get(item_id)
    if not it:
        return None
    return _path(it.get('thumb' if which == 'thumb' else 'file') or '')


def public(it: dict) -> dict:
    keys = ('id', 'kind', 'caption', 'text', 'color', 'state', 'targets', 'scheduledAt', 'results',
            'created', 'postedAt', 'width', 'height', 'duration', 'size', 'trimmed', 'origSize')
    out = {k: it.get(k) for k in keys}
    out['hasThumb'] = bool(it.get('thumb'))
    return out


def list_items() -> list:
    return [public(it) for it in sorted(_load(), key=lambda x: x.get('created', 0))]


def _default_targets() -> list:
    cfg = _get_config() if _get_config else {}
    icons = {str(m.get('icon', '')).lower() for m in cfg.get('messengers', [])
             if m.get('enabled', True) and m.get('port')}
    return [t for t in TARGETS if t in icons]


def _new_item(kind: str, **extra) -> dict:
    return {'id': 'q' + secrets.token_hex(8), 'kind': kind, 'caption': '', 'text': '', 'color': '#0a5f55',
            'state': 'processing', 'targets': _default_targets(), 'scheduledAt': None, 'results': {},
            'created': int(time.time() * 1000), 'postedAt': None, **extra}


def _insert(item: dict) -> None:
    with _lock:
        items = _load()
        if len(items) >= MAX_ITEMS:
            raise ValueError('too_many')
        items.append(item)
        _save(items)


# ── Eingang ───────────────────────────────────────────────────────────────────
def add_text(text: str, color: str) -> dict:
    text = (text or '').strip()[:700]
    if not text:
        raise ValueError('empty')
    item = _new_item('text', text=text, color=color if COLOR_RE.match(color or '') else '#0a5f55', state='ready')
    _insert(item)
    return public(item)


def add_upload(src_path: str, mimetype: str, caption: str) -> dict:
    """src_path: temporaere Datei, gehoert ab hier diesem Modul."""
    if mimetype.startswith('image/'):
        kind = 'image'
    elif mimetype.startswith('video/'):
        kind = 'video'
    else:
        os.remove(src_path)
        raise ValueError('unsupported')
    os.makedirs(QUEUE_DIR, exist_ok=True)
    item = _new_item(kind, caption=(caption or '').strip()[:700], origSize=os.path.getsize(src_path))
    try:
        _insert(item)
    except ValueError:
        os.remove(src_path)
        raise
    threading.Thread(target=_process, args=(item['id'], kind, src_path), daemon=True).start()
    return public(item)


def _process(item_id: str, kind: str, src: str) -> None:
    try:
        if kind == 'image':
            meta = _process_image(item_id, src)
        else:
            meta = _process_video(item_id, src)
        _update(item_id, state='ready', **meta)
        log.info('Status-Ablage: %s aufbereitet (%d KB)', kind, meta['size'] // 1024)
    except Exception as e:
        log.warning('Status-Ablage: Aufbereiten fehlgeschlagen: %s', e)
        _update(item_id, state='error')
    finally:
        try:
            os.remove(src)
        except OSError:
            pass


def _process_image(item_id: str, src: str) -> dict:
    from PIL import Image, ImageOps
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ('RGB', 'L'):
            bg = Image.new('RGB', im.size, (255, 255, 255))
            bg.paste(im, mask=im.convert('RGBA').split()[-1])
            im = bg
        im = im.convert('RGB')
        im.thumbnail((IMG_MAX, IMG_MAX))
        name = item_id + '.jpg'
        im.save(_path(name), 'JPEG', quality=85, optimize=True, progressive=True)
        w, h = im.size
        th = im.copy()
        th.thumbnail((THUMB_MAX, THUMB_MAX))
        th.save(_path(item_id + '_t.jpg'), 'JPEG', quality=80)
    return {'file': name, 'thumb': item_id + '_t.jpg', 'width': w, 'height': h,
            'size': os.path.getsize(_path(name))}


def _probe(path: str) -> dict:
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                          'stream=width,height:format=duration', '-of', 'json', path],
                         capture_output=True, text=True, timeout=60, check=True).stdout
    data = json.loads(out)
    st = (data.get('streams') or [{}])[0]
    return {'width': int(st.get('width') or 0), 'height': int(st.get('height') or 0),
            'duration': float((data.get('format') or {}).get('duration') or 0)}


def _process_video(item_id: str, src: str) -> dict:
    name = item_id + '.mp4'
    dst = _path(name)
    src_info = _probe(src)
    # Kurze Seite auf hoechstens 720 px; ffmpeg dreht dabei nach der Handy-Lage
    scale = "scale='if(gt(iw,ih),-2,min(720,iw))':'if(gt(iw,ih),min(720,ih),-2)'"
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', src, '-t', str(VIDEO_MAX_S), '-vf', scale,
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26', '-maxrate', '2500k',
                    '-bufsize', '5000k', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
                    '-movflags', '+faststart', dst],
                   capture_output=True, timeout=1800, check=True)
    info = _probe(dst)
    thumb = item_id + '_t.jpg'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', str(min(1.0, info['duration'] / 2)), '-i', dst,
                    '-frames:v', '1', '-vf', f'scale={THUMB_MAX}:-2', _path(thumb)],
                   capture_output=True, timeout=120, check=False)
    return {'file': name, 'thumb': thumb if os.path.exists(_path(thumb)) else None,
            'width': info['width'], 'height': info['height'], 'duration': round(info['duration'], 1),
            'size': os.path.getsize(dst), 'trimmed': src_info['duration'] > VIDEO_MAX_S + 0.5}


# ── Bearbeiten ────────────────────────────────────────────────────────────────
def update(item_id: str, data: dict) -> dict | None:
    it = get(item_id)
    if not it or it['state'] in ('processing', 'posting'):
        return None
    changes = {}
    if isinstance(data.get('caption'), str):
        changes['caption'] = data['caption'].strip()[:700]
    if isinstance(data.get('text'), str) and it['kind'] == 'text' and data['text'].strip():
        changes['text'] = data['text'].strip()[:700]
    if isinstance(data.get('color'), str) and COLOR_RE.match(data['color']):
        changes['color'] = data['color']
    if isinstance(data.get('targets'), list):
        changes['targets'] = [t for t in TARGETS if t in data['targets']]
    if 'scheduledAt' in data:
        at = data['scheduledAt']
        if at is None:
            changes['scheduledAt'] = None
            if it['state'] == 'scheduled':
                changes['state'] = 'ready'
        elif isinstance(at, (int, float)) and at > 0:
            changes['scheduledAt'] = int(at)
            changes['state'] = 'scheduled'
            _wake.set()
    return public(_update(item_id, **changes)) if changes else public(it)


def delete(item_id: str) -> bool:
    with _lock:
        items = _load()
        it = next((x for x in items if x['id'] == item_id), None)
        if not it or it['state'] == 'posting':
            return False
        items.remove(it)
        _save(items)
    for key in ('file', 'thumb'):
        p = _path(it.get(key) or '')
        if p:
            try:
                os.remove(p)
            except OSError:
                pass
    return True


def post_now(item_id: str, only_failed: bool = False) -> dict | None:
    it = get(item_id)
    if not it or it['state'] in ('processing', 'posting', 'error'):
        return None
    targets = it['targets']
    if only_failed:
        targets = [t for t in targets if not (it.get('results') or {}).get(t, {}).get('ok')]
    if not targets:
        return public(it)
    it = _update(item_id, state='posting', scheduledAt=None, postedAt=int(time.time() * 1000))
    if not it:
        return None
    threading.Thread(target=_post, args=(item_id, targets), daemon=True).start()
    return public(it)


# ── Posten ────────────────────────────────────────────────────────────────────
def _multipart(url: str, fields: dict, file_field: tuple | None) -> dict:
    boundary = 'mp' + secrets.token_hex(12)
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    if file_field:
        fname, mime, data = file_field
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\n'
                     f'Content-Type: {mime}\r\n\r\n'.encode() + data + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    req = urllib.request.Request(url, data=b''.join(parts), method='POST',
                                 headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    return _send(req)


def _json(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST',
                                 headers={'Content-Type': 'application/json'})
    return _send(req)


def _send(req) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read() or b'{}')
    except urllib.error.HTTPError as e:
        detail = ''
        try:
            detail = str(json.loads(e.read()).get('error', ''))[:200]
        except Exception:
            pass
        raise RuntimeError(f'HTTP {e.code} {detail}'.strip()) from None


def _signal_cut(src: str) -> str:
    fd, out = tempfile.mkstemp(suffix='.mp4')
    os.close(fd)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', src, '-t', str(SIGNAL_VIDEO_MAX_S), '-c', 'copy',
                    '-movflags', '+faststart', out], capture_output=True, timeout=300, check=True)
    return out


def _post_one(target: str, base: str, it: dict) -> None:
    kind, caption = it['kind'], it.get('caption') or ''
    if kind == 'text':
        if target == 'whatsapp':
            _json(base + 'api/my-status/text', {'text': it['text'], 'backgroundColor': it.get('color')})
        else:
            png = status_mirror.render_text(it['text'], it.get('color'))
            _multipart(base + 'api/my-status/media', {}, ('status.png', 'image/png', png))
        return
    src = _path(it['file'])
    if not src or not os.path.exists(src):
        raise RuntimeError('file missing')
    fields = {}
    if caption and target in ('whatsapp', 'telegram'):
        fields['caption'] = caption
    if kind == 'image':
        with open(src, 'rb') as f:
            _multipart(base + 'api/my-status/media', fields, (it['file'], 'image/jpeg', f.read()))
        return
    if target == 'telegram':
        fields.update(duration=str(it.get('duration') or 1), w=str(it.get('width') or 720), h=str(it.get('height') or 1280))
    path, tmp = src, None
    if target == 'signal' and (it.get('duration') or 0) > SIGNAL_VIDEO_MAX_S + 0.5:
        path = tmp = _signal_cut(src)
    try:
        with open(path, 'rb') as f:
            _multipart(base + 'api/my-status/media', fields, (it['file'], 'video/mp4', f.read()))
    finally:
        if tmp:
            os.remove(tmp)


def _post(item_id: str, targets: list) -> None:
    it = get(item_id)
    if not it:
        return
    cfg = _get_config() if _get_config else {}
    by_icon = {str(m.get('icon', '')).lower(): m for m in cfg.get('messengers', [])
               if m.get('enabled', True) and m.get('port')}
    results = dict(it.get('results') or {})
    now = int(time.time() * 1000)
    # Erst die Ziele ausser WhatsApp dem Spiegel melden, damit er den gleich
    # entstehenden WhatsApp-Status nicht noch einmal dorthin weiterreicht
    if 'whatsapp' in targets:
        mirror_kind = {'image': 'photo', 'video': 'video', 'text': 'text'}[it['kind']]
        for t in targets:
            if t != 'whatsapp':
                status_mirror.suppress(t, mirror_kind, now)
    for t in targets:
        m = by_icon.get(t)
        if not m:
            results[t] = {'ok': False, 'code': 'not_configured', 'at': now}
            continue
        try:
            _post_one(t, _base_url_for(m), it)
            results[t] = {'ok': True, 'code': '', 'at': int(time.time() * 1000)}
            log.info('Status-Ablage: %s nach %s gepostet', it['kind'], t)
        except Exception as e:
            log.warning('Status-Ablage: %s nach %s fehlgeschlagen: %s', it['kind'], t, e)
            code = 'unreachable' if isinstance(e, urllib.error.URLError) or 'timed out' in str(e) else 'rejected'
            results[t] = {'ok': False, 'code': code, 'at': int(time.time() * 1000)}
    all_ok = all(results.get(t, {}).get('ok') for t in it['targets'])
    _update(item_id, state='posted' if all_ok else 'failed', results=results, postedAt=int(time.time() * 1000))


# ── Planer ────────────────────────────────────────────────────────────────────
def _tick() -> None:
    now_ms = int(time.time() * 1000)
    items = _load()
    for it in items:
        if it['state'] == 'scheduled' and it.get('scheduledAt') and it['scheduledAt'] <= now_ms:
            post_now(it['id'])
        elif it['state'] == 'posting' and now_ms - (it.get('postedAt') or it['created']) > 3600 * 1000:
            # Nach einem Neustart mitten im Posten haengengeblieben
            _update(it['id'], state='failed')
    # Gepostete Eintraege nach einer Woche aufraeumen
    for it in items:
        if it['state'] == 'posted' and now_ms - (it.get('postedAt') or 0) > KEEP_POSTED_S * 1000:
            delete(it['id'])


def start(get_config, base_url_for) -> None:
    global _get_config, _base_url_for
    _get_config, _base_url_for = get_config, base_url_for
    os.makedirs(QUEUE_DIR, exist_ok=True)
    # Nach einem Neustart: angefangene Aufbereitungen und Postings ehrlich als
    # gescheitert markieren statt sie ewig "laufen" zu lassen
    with _lock:
        items = _load()
        for it in items:
            if it['state'] == 'processing':
                it['state'] = 'error'
            elif it['state'] == 'posting':
                it['state'] = 'failed'
        _save(items)

    def loop():
        while True:
            try:
                _tick()
            except Exception as e:
                log.warning('Status-Ablage: Planer: %s', e)
            _wake.wait(TICK_S)
            _wake.clear()

    threading.Thread(target=loop, name='status-queue', daemon=True).start()
    if shutil.which('ffmpeg') is None:
        log.warning('Status-Ablage: ffmpeg fehlt – Videos lassen sich nicht aufbereiten')
