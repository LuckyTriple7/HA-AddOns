#!/usr/bin/env python3
import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

from flask import (Flask, render_template, request, redirect,
                   url_for, make_response, jsonify, abort, send_from_directory)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

logging.basicConfig(
    format='[%(levelname)s] [%(asctime)s] %(message)s',
    level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S', force=True
)
log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# In-App Console: Log-Buffer (max 300 Einträge)
from collections import deque as _deque
_log_buffer: _deque = _deque(maxlen=300)

class _BufferHandler(logging.Handler):
    _fmt = logging.Formatter('[%(levelname)s] [%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    def emit(self, record):
        try:
            _log_buffer.append({'ts': int(record.created * 1000), 'level': record.levelname, 'msg': self._fmt.format(record)})
        except Exception:
            pass

_buf_h = _BufferHandler()
_buf_h.setLevel(logging.DEBUG)
# Root-Level auf DEBUG damit Debug-Records Handler erreichen können —
# bestehender StreamHandler (HA Log) wird explizit auf INFO gesetzt,
# sodass nur _buf_h die DEBUG-Meldungen sieht.
_root = logging.getLogger()
_root.setLevel(logging.DEBUG)
for _h in _root.handlers:
    if _h.level == logging.NOTSET:
        _h.setLevel(logging.INFO)
_root.addHandler(_buf_h)

app = Flask(__name__, template_folder='/app/templates', static_folder='/app/static')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

MEDIA_DIR     = Path('/media/mediagrab')
META_PATH     = MEDIA_DIR / '.mediagrab_meta.json'
CONFIG_PATH   = '/data/options.json'
SESSIONS_PATH = '/data/sessions.json'
JOBS_PATH     = '/data/jobs.json'
COOKIES_PATH  = '/data/cookies.txt'
LOCALES_PATH  = '/app/locales'
PORT          = 17791

RATE_LIMIT_MAX    = 5
RATE_LIMIT_WINDOW = 900

_config_cache: dict | None = None
_config_mtime: float = 0.0
sessions: dict[str, float] = {}
_failed: dict[str, list[float]] = defaultdict(list)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_meta_lock = threading.Lock()

_ytdlp_ver_cache: dict = {'ver': None, 'ts': 0.0}  # cached for 1h

# ── Platform detection ────────────────────────────────────────────────────────

PLATFORMS = ['YouTube', 'TikTok', 'Instagram', 'X', 'Vimeo', 'SoundCloud', 'Twitch', 'Reddit', 'Dailymotion', 'Sonstiges']

def _detect_platform(url: str) -> str:
    try:
        host = (urllib.parse.urlparse(url).hostname or '').lower()
    except Exception:
        host = ''
    def _is_host(domain: str) -> bool:
        return host == domain or host.endswith('.' + domain)
    if _is_host('youtube.com') or _is_host('youtu.be'): return 'YouTube'
    if _is_host('tiktok.com'):                           return 'TikTok'
    if _is_host('instagram.com'):                        return 'Instagram'
    if _is_host('twitter.com') or _is_host('x.com'):    return 'X'
    if _is_host('vimeo.com'):                            return 'Vimeo'
    if _is_host('soundcloud.com'):                       return 'SoundCloud'
    if _is_host('twitch.tv'):                            return 'Twitch'
    if _is_host('reddit.com'):                           return 'Reddit'
    if _is_host('dailymotion.com'):                      return 'Dailymotion'
    return 'Sonstiges'

def _load_meta() -> dict:
    try:
        if META_PATH.exists():
            return json.loads(META_PATH.read_text())
    except Exception:
        pass
    return {}

def _save_meta(meta: dict) -> None:
    try:
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        META_PATH.write_text(json.dumps(meta))
    except Exception as e:
        log.warning('Meta-Datei konnte nicht gespeichert werden: %s', e)

# ── Config ─────────────────────────────────────────────────────────────────────

def get_config() -> dict:
    global _config_cache, _config_mtime
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
        if mtime != _config_mtime:
            with open(CONFIG_PATH) as f:
                _config_cache = json.load(f)
            _config_mtime = mtime
    except Exception as e:
        log.warning('Config konnte nicht gelesen werden: %s', e)
        if _config_cache is None:
            _config_cache = {}
    return _config_cache  # type: ignore[return-value]

# ── Locale ─────────────────────────────────────────────────────────────────────

_locale_cache: dict[str, dict] = {}

def get_locale(lang: str) -> dict:
    if lang not in _locale_cache:
        try:
            with open(f'{LOCALES_PATH}/{lang}.json', encoding='utf-8') as f:
                _locale_cache[lang] = json.load(f)
        except Exception:
            _locale_cache[lang] = {}
    return _locale_cache[lang]

def get_lang(req) -> str:
    lang = req.cookies.get('mg_lang', 'de')
    return lang if lang in ('de', 'en') else 'de'

# ── Sessions ───────────────────────────────────────────────────────────────────

def save_sessions() -> None:
    now = time.time()
    try:
        with open(SESSIONS_PATH, 'w') as f:
            json.dump({k: v for k, v in sessions.items() if v > now}, f)
    except Exception as e:
        log.warning('Sessions konnten nicht gespeichert werden: %s', e)

def load_sessions() -> None:
    global sessions
    now = time.time()
    try:
        with open(SESSIONS_PATH) as f:
            data = json.load(f)
        sessions = {k: v for k, v in data.items() if v > now}
        if sessions:
            log.info('Sessions geladen: %d aktive(s)', len(sessions))
    except Exception:
        sessions = {}

def create_session(hours: int) -> tuple[str, float]:
    token = secrets.token_hex(32)
    expires = time.time() + hours * 3600
    sessions[token] = expires
    save_sessions()
    return token, expires

def is_valid_session(token: str | None) -> bool:
    if not token or token not in sessions:
        return False
    if time.time() > sessions[token]:
        del sessions[token]
        return False
    return True

# ── Brute-force protection ─────────────────────────────────────────────────────

def is_rate_limited(ip: str) -> bool:
    now = time.time()
    _failed[ip] = [t for t in _failed[ip] if now - t < RATE_LIMIT_WINDOW]
    return len(_failed[ip]) >= RATE_LIMIT_MAX

def record_failed(ip: str) -> None:
    _failed[ip].append(time.time())
    log.warning('Login fehlgeschlagen: ip=%s (%d Versuche)', ip, len(_failed[ip]))

def clear_failed(ip: str) -> None:
    _failed.pop(ip, None)

# ── Jobs persistence ───────────────────────────────────────────────────────────

def save_jobs() -> None:
    try:
        with _jobs_lock:
            data = [{k: v for k, v in j.items() if k != 'proc'} for j in _jobs.values()]
        with open(JOBS_PATH, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        log.warning('Jobs konnten nicht gespeichert werden: %s', e)

def load_jobs() -> None:
    global _jobs
    try:
        with open(JOBS_PATH) as f:
            data = json.load(f)
        restored: dict[str, dict] = {}
        for j in data:
            j['proc'] = None
            if j.get('status') in ('pending', 'running'):
                j['status'] = 'error'
                j['error']  = 'err_interrupted'
            restored[j['id']] = j
        with _jobs_lock:
            _jobs = restored
        if restored:
            log.info('Jobs wiederhergestellt: %d Einträge', len(restored))
    except Exception:
        pass

# ── Auto-clear background thread ───────────────────────────────────────────────

def _auto_clear_worker() -> None:
    while True:
        time.sleep(60)
        config = get_config()
        hours = int(config.get('auto_clear_hours', 0))
        if hours <= 0:
            continue
        cutoff = time.time() - hours * 3600
        with _jobs_lock:
            to_remove = [
                jid for jid, j in _jobs.items()
                if j['status'] not in ('pending', 'running') and j.get('created_at', 0) < cutoff
            ]
            for jid in to_remove:
                del _jobs[jid]
        if to_remove:
            log.info('Auto-Clear: %d Jobs entfernt (älter als %dh)', len(to_remove), hours)
            save_jobs()

# ── Error parsing ──────────────────────────────────────────────────────────────

_ERROR_PATTERNS = [
    (r'Sign in to confirm your age|age.restricted',     'err_age_restricted'),
    (r'Private video|This video is private',             'err_private'),
    (r'Video unavailable|This video is not available',   'err_unavailable'),
    (r'has been removed',                                'err_removed'),
    (r'Requested format is not available',               'err_format'),
    (r'HTTP Error 429|Too Many Requests',                'err_rate_limited'),
    (r'urlopen error',                                   'err_network'),
    (r'Unable to extract',                               'err_extract'),
    (r'No such channel',                                 'err_not_found'),
    (r'is not a valid URL',                              'err_invalid_url'),
    (r'Unsupported URL',                                 'err_unsupported'),
]

def _parse_error(lines: list[str]) -> str:
    text = '\n'.join(lines)
    for pattern, key in _ERROR_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return key
    return 'err_unknown'

# ── yt-dlp download logic ──────────────────────────────────────────────────────

VALID_FORMATS = {'best_video', '1080p', '720p', '480p', '360p', 'mp3', 'm4a'}

_PROG_RE    = re.compile(r'^MGPROG\|([\s\d.]+)%\|(.+)\|(.+)$')
_DEST_RE    = re.compile(r'\[download\] Destination:\s+(.+)')
_MERGE_RE   = re.compile(r'\[Merger\] Merging formats into "(.+)"')
_ALREADY_RE = re.compile(r'\[download\] (.+) has already been downloaded')

def _build_cmd(url: str, fmt: str, subtitles: bool, playlist: bool, use_cookies: bool = True) -> list[str]:
    config = get_config()
    cmd = [
        'yt-dlp',
        '--no-color', '--newline', '--progress',
        '--progress-template', 'download:MGPROG|%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s',
        '-o', '/media/mediagrab/%(title)s.%(ext)s',
    ]
    if not playlist:
        cmd.append('--no-playlist')
    if subtitles:
        cmd += ['--write-sub', '--write-auto-sub', '--sub-langs', 'de,en']

    speed = config.get('speed_limit', '').strip()
    if speed:
        cmd += ['--limit-rate', speed]

    if use_cookies and Path(COOKIES_PATH).exists():
        cmd += ['--cookies', COOKIES_PATH]

    if fmt == 'mp3':
        cmd += ['-x', '--audio-format', 'mp3', '--audio-quality', '0']
    elif fmt == 'm4a':
        cmd += ['-x', '--audio-format', 'm4a']
    elif fmt == '1080p':
        cmd += ['-f', 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
                '--merge-output-format', 'mp4']
    elif fmt == '720p':
        cmd += ['-f', 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best',
                '--merge-output-format', 'mp4']
    elif fmt == '480p':
        cmd += ['-f', 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]/best',
                '--merge-output-format', 'mp4']
    elif fmt == '360p':
        cmd += ['-f', 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]/best',
                '--merge-output-format', 'mp4']
    else:  # best_video
        cmd += ['-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
                '--merge-output-format', 'mp4']

    cmd += ['--', url]
    return cmd

def _run_download(job_id: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job['status'] = 'running'
    save_jobs()

    cmd = _build_cmd(job['url'], job['fmt'], job['subtitles'], job['playlist'], job.get('use_cookies', True))
    log.info('Download startet: job=%s fmt=%s url=%s', job_id, job['fmt'], job['url'])

    output_lines: list[str] = []
    try:
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'

        for attempt in range(2):
            output_lines = []
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=env
            )
            with _jobs_lock:
                _jobs[job_id]['proc'] = proc

            _needs_retry = False

            while True:
                line = proc.stdout.readline()  # type: ignore[union-attr]
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                line = line.rstrip()
                output_lines.append(line)
                log.debug('[yt-dlp] %s', line)
                if get_config().get('verbose_log'):
                    log.info('[yt-dlp] %s', line)

                m = _PROG_RE.match(line)
                if m:
                    try:
                        pct = float(m.group(1).strip())
                    except ValueError:
                        pct = 0.0
                    with _jobs_lock:
                        _jobs[job_id]['progress'] = pct
                        _jobs[job_id]['speed']    = m.group(2).strip()
                        _jobs[job_id]['eta']      = m.group(3).strip()
                    continue

                m = _DEST_RE.search(line)
                if m:
                    with _jobs_lock:
                        _jobs[job_id]['filename'] = Path(m.group(1).strip()).name
                    continue

                m = _MERGE_RE.search(line)
                if m:
                    with _jobs_lock:
                        _jobs[job_id]['filename'] = Path(m.group(1).strip()).name
                    continue

                m = _ALREADY_RE.search(line)
                if m:
                    _needs_retry = True
                    with _jobs_lock:
                        _jobs[job_id]['filename'] = Path(m.group(1).strip()).name

            proc.wait()

            with _jobs_lock:
                cancelled = _jobs[job_id]['status'] == 'cancelled'

            if cancelled:
                log.info('Download abgebrochen: job=%s', job_id)
                break

            if _needs_retry and attempt == 0:
                # New file gets timestamp suffix; existing file (with its tags) stays untouched
                ts = time.strftime('%Y%m%d_%H%M%S')
                cmd = [a.replace('/%(title)s.%(ext)s', f'/%(title)s_{ts}.%(ext)s')
                       if a.endswith('/%(title)s.%(ext)s') else a for a in cmd]
                with _jobs_lock:
                    _jobs[job_id]['progress'] = 0.0
                    _jobs[job_id]['filename'] = ''
                log.info('Download-Retry mit Zeitstempel-Suffix: job=%s ts=%s', job_id, ts)
                continue

            with _jobs_lock:
                if proc.returncode == 0:
                    _jobs[job_id]['status']   = 'done'
                    _jobs[job_id]['progress'] = 100.0
                    _jobs[job_id]['eta']      = ''
                    fname   = _jobs[job_id].get('filename', '')
                    job_url = _jobs[job_id].get('url', '')
                    log.info('Download fertig: job=%s file=%s', job_id, fname)
                    if fname:
                        with _meta_lock:
                            meta = _load_meta()
                            meta[fname] = {'platform': _detect_platform(job_url)}
                            _save_meta(meta)
                else:
                    err = _parse_error(output_lines)
                    _jobs[job_id]['status'] = 'error'
                    _jobs[job_id]['error']  = err
                    log.warning('Download Fehler: job=%s rc=%d err=%s', job_id, proc.returncode, err)
            break

    except Exception as e:
        log.error('Download Exception: job=%s err=%s', job_id, e)
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]['status'] = 'error'
                _jobs[job_id]['error']  = str(e)
    finally:
        save_jobs()
        _cleanup_temp_files()

# ── Temp file cleanup ──────────────────────────────────────────────────────────

TEMP_SUFFIXES = ('.part', '.ytdl', '.part-Frag0', '.part-Frag1', '.part-Frag2', '.part-Frag3')

def _is_stream_tmp(p: Path) -> bool:
    return bool(re.search(r'\.f\d+$', p.stem))

def _safe_rename_existing(p: Path) -> None:
    if not p.exists() or _is_stream_tmp(p):
        return
    ts = time.strftime('%Y%m%d_%H%M%S')
    candidate = p.parent / f'{p.stem}_{ts}{p.suffix}'
    try:
        p.rename(candidate)
        log.info('Dateikonflikt: "%s" → "%s" umbenannt', p.name, candidate.name)
    except Exception as e:
        log.warning('Umbenennen bei Konflikt fehlgeschlagen: %s — %s', p.name, e)

def _cleanup_temp_files() -> None:
    """Remove .part/.ytdl leftovers not belonging to an active download."""
    if not MEDIA_DIR.exists():
        return
    with _jobs_lock:
        active_filenames = {
            j.get('filename', '')
            for j in _jobs.values()
            if j['status'] in ('pending', 'running') and j.get('filename')
        }
    removed = []
    for p in MEDIA_DIR.iterdir():
        if not p.is_file():
            continue
        name = p.name
        is_temp = any(name.endswith(s) for s in TEMP_SUFFIXES) or name.endswith('.ytdl')
        if not is_temp:
            continue
        # Keep if an active download uses this base file
        base = name
        for s in TEMP_SUFFIXES:
            if base.endswith(s):
                base = base[:-len(s)]
                break
        if base in active_filenames:
            continue
        try:
            p.unlink()
            removed.append(name)
        except Exception as e:
            log.warning('Temp-Datei konnte nicht gelöscht werden: %s — %s', name, e)
    if removed:
        log.info('Temp-Dateien aufgeräumt: %s', ', '.join(removed))

# ── Auth helpers ───────────────────────────────────────────────────────────────

def _require_auth() -> bool:
    return not is_valid_session(request.cookies.get('mg_session'))

def _safe_next(url: str) -> str:
    if url and url.startswith('/') and not url.startswith('//'):
        return url
    return ''

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/set-lang/<lang>')
def set_lang(lang):
    cookie_lang = 'en' if lang == 'en' else 'de'
    resp = make_response(redirect(request.referrer or '/'))
    resp.set_cookie('mg_lang', cookie_lang, max_age=60 * 60 * 24 * 365, samesite='Lax')
    return resp

@app.route('/login', methods=['GET', 'POST'])
def login():
    lang    = get_lang(request)
    t       = get_locale(lang)
    config  = get_config()
    error   = None
    next_url = request.args.get('next', '')

    if is_valid_session(request.cookies.get('mg_session')):
        return redirect(_safe_next(next_url) or url_for('index'))

    if request.method == 'POST':
        ip = request.remote_addr
        if is_rate_limited(ip):
            log.warning('Login blockiert (Rate Limit): ip=%s', ip)
            error = t.get('error_locked', 'Too many failed attempts. Please wait 15 minutes.')
        else:
            uname = request.form.get('username', '')
            pw    = request.form.get('password', '')
            if uname == config.get('username') and pw == config.get('password'):
                clear_failed(ip)
                log.info('Login erfolgreich: ip=%s user=%s', ip, uname)
                hours = int(config.get('session_hours', 24))
                token, expires = create_session(hours)
                target = _safe_next(request.form.get('next', '')) or url_for('index')
                resp = make_response(redirect(target))
                resp.set_cookie(
                    'mg_session', token,
                    httponly=True, samesite='Lax',
                    max_age=int(expires - time.time())
                )
                return resp
            else:
                record_failed(ip)
                error = t.get('error_credentials', 'Invalid credentials.')

    return render_template('login.html', t=t, lang=lang, error=error, next_url=next_url)

@app.route('/logout')
def logout():
    token = request.cookies.get('mg_session')
    if token and token in sessions:
        del sessions[token]
        save_sessions()
    resp = make_response(redirect(url_for('login')))
    resp.delete_cookie('mg_session')
    return resp

@app.route('/')
def index():
    if _require_auth():
        return redirect(url_for('login'))
    lang = get_lang(request)
    t    = get_locale(lang)
    return render_template('index.html', t=t, lang=lang)

@app.route('/share')
def share():
    shared_url = (request.args.get('url') or request.args.get('text') or '').strip()
    if _require_auth():
        next_path = '/share?' + urllib.parse.urlencode({'url': shared_url})
        return redirect(url_for('login') + '?next=' + urllib.parse.quote(next_path))
    return redirect('/?url=' + urllib.parse.quote(shared_url, safe=''))

@app.route('/health')
def health():
    return 'ok'


@app.route('/api/logs')
def api_logs():
    since = int(request.args.get('since', 0))
    entries = [e for e in _log_buffer if e['ts'] > since]
    return jsonify(entries)

def _get_ytdlp_version() -> str:
    now = time.time()
    if _ytdlp_ver_cache['ver'] and now - _ytdlp_ver_cache['ts'] < 3600:
        return _ytdlp_ver_cache['ver']
    try:
        ver = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        ver = 'unknown'
    _ytdlp_ver_cache['ver'] = ver
    _ytdlp_ver_cache['ts']  = now
    return ver


@app.route('/api/status')
def api_status():
    config  = get_config()
    api_key = config.get('api_key', '').strip()
    if not api_key:
        return jsonify({'error': 'api_disabled'}), 403
    provided = (request.args.get('api_key') or request.headers.get('X-API-Key', '')).strip()
    if not provided or provided != api_key:
        log.warning('API /status: ungültiger API-Key von %s', request.remote_addr)
        return jsonify({'error': 'unauthorized'}), 401

    if config.get('verbose_log'):
        log.info('API /status: Zugriff von %s', request.remote_addr)

    try:
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        with _jobs_lock:
            jobs = list(_jobs.values())

        active   = sum(1 for j in jobs if j['status'] in ('pending', 'running'))
        done     = sum(1 for j in jobs if j['status'] == 'done')
        errors   = sum(1 for j in jobs if j['status'] == 'error')

        files = [p for p in MEDIA_DIR.iterdir() if p.is_file() and p.name != '.mediagrab_meta.json'] if MEDIA_DIR.exists() else []
        files_count = len(files)
        folder_size = sum(f.stat().st_size for f in files)
        last_file   = max(files, key=lambda f: f.stat().st_mtime).name if files else ''

        usage    = shutil.disk_usage(str(MEDIA_DIR))
        disk_pct = round(usage.used / usage.total * 100, 1) if usage.total else 0

        return jsonify({
            'active_downloads':  active,
            'done_downloads':    done,
            'error_downloads':   errors,
            'files_count':       files_count,
            'folder_size_mb':    round(folder_size / 1048576, 1),
            'disk_free_gb':      round(usage.free / 1073741824, 2),
            'disk_used_pct':     disk_pct,
            'last_file':         last_file,
            'ytdlp_version':     _get_ytdlp_version(),
        })
    except Exception as e:
        log.error('API /status: Fehler — %s', e)
        return jsonify({'error': 'internal_error'}), 500

# ── API ────────────────────────────────────────────────────────────────────────

@app.route('/api/download', methods=['POST'])
def api_download():
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    data = request.json or {}

    urls = [l.strip() for l in (data.get('url') or '').splitlines() if l.strip()]
    if not urls:
        return jsonify({'error': 'no_url'}), 400
    if not all(_is_safe_external_media_url(_u) for _u in urls):
        return jsonify({'error': 'invalid_url'}), 400

    fmt = data.get('fmt', 'best_video')
    if fmt not in VALID_FORMATS:
        fmt = 'best_video'

    config = get_config()
    max_concurrent = int(config.get('max_concurrent', 3))

    job_ids = []
    for url in urls:
        with _jobs_lock:
            running = sum(1 for j in _jobs.values() if j['status'] in ('pending', 'running'))
        if running >= max_concurrent:
            return jsonify({'error': 'queue_full', 'started': job_ids}), 429

        job_id = secrets.token_hex(8)
        job: dict = {
            'id':         job_id,
            'url':        url,
            'fmt':        fmt,
            'subtitles':  bool(data.get('subtitles', False)),
            'playlist':   bool(data.get('playlist', False)),
            'use_cookies': bool(data.get('use_cookies', True)),
            'status':     'pending',
            'progress':   0.0,
            'speed':      '',
            'eta':        '',
            'filename':   '',
            'error':      '',
            'proc':       None,
            'created_at': time.time(),
        }
        with _jobs_lock:
            _jobs[job_id] = job
        job_ids.append(job_id)
        threading.Thread(target=_run_download, args=(job_id,), daemon=True).start()

    save_jobs()
    return jsonify({'job_ids': job_ids})

def _is_safe_external_media_url(url: str) -> bool:
    if not url:
        return False
    if any(ch.isspace() for ch in url) or any(ord(ch) < 32 for ch in url):
        return False
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local or ip.is_multicast:
            return False
    except ValueError:
        host_l = host.lower().strip('.')
        if host_l in ('localhost',):
            return False
    return True

def _safe_media_path(filename: str) -> 'Path | None':
    """Returns resolved path only if within MEDIA_DIR — rejects traversal attempts."""
    raw = (filename or '').strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.name != raw or any(part == '..' for part in candidate.parts):
        return None
    base_resolved = MEDIA_DIR.resolve()
    resolved = (base_resolved / raw).resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        return None
    return resolved

@app.route('/api/info', methods=['POST'])
def api_info():
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    data = request.json or {}
    url  = (data.get('url') or '').strip()
    if not url:
        return jsonify({'error': 'no_url'}), 400
    if not _is_safe_external_media_url(url):
        return jsonify({'error': 'invalid_url'}), 400
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            return jsonify({'error': 'invalid_url'}), 400
        if parsed.username is not None or parsed.password is not None:
            return jsonify({'error': 'invalid_url'}), 400
        if parsed.fragment:
            return jsonify({'error': 'invalid_url'}), 400
        canonical_url = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.query, '')
        )
        if any(ord(ch) < 32 for ch in canonical_url):
            return jsonify({'error': 'invalid_url'}), 400
    except Exception:
        return jsonify({'error': 'invalid_url'}), 400

    cmd = ['yt-dlp', '--dump-json', '--no-playlist', '--no-download', '--no-warnings']
    if Path(COOKIES_PATH).exists():
        cmd += ['--cookies', COOKIES_PATH]
    cmd += ['--', canonical_url]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return jsonify({'error': 'fetch_failed'}), 400
        info = json.loads(result.stdout.splitlines()[0])
        duration = info.get('duration')
        dur_str  = ''
        if duration:
            m, s = divmod(int(duration), 60)
            h, m = divmod(m, 60)
            dur_str = f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'
        return jsonify({
            'title':     info.get('title', ''),
            'uploader':  info.get('uploader') or info.get('channel', ''),
            'duration':  dur_str,
            'thumbnail': info.get('thumbnail', ''),
            'extractor': info.get('extractor_key', ''),
        })
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'timeout'}), 504
    except Exception:
        log.exception("Video-Info Fehler")
        return jsonify({'error': 'internal error'}), 500

@app.route('/api/jobs')
def api_jobs():
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    with _jobs_lock:
        result = [{k: v for k, v in j.items() if k != 'proc'} for j in _jobs.values()]
    result.sort(key=lambda j: j['created_at'], reverse=True)
    return jsonify(result)

@app.route('/api/cancel/<job_id>', methods=['POST'])
def api_cancel(job_id):
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return jsonify({'error': 'not_found'}), 404
        job['status'] = 'cancelled'
        proc = job.get('proc')
    if proc:
        proc.terminate()
        # Give process a moment to release file handles before cleanup
        threading.Thread(target=lambda: (time.sleep(1), _cleanup_temp_files()), daemon=True).start()
    save_jobs()
    return jsonify({'ok': True})

@app.route('/api/remove/<job_id>', methods=['POST'])
def api_remove(job_id):
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    with _jobs_lock:
        _jobs.pop(job_id, None)
    save_jobs()
    return jsonify({'ok': True})

@app.route('/api/jobs/clear', methods=['POST'])
def api_jobs_clear():
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    with _jobs_lock:
        finished = [jid for jid, j in _jobs.items() if j['status'] not in ('pending', 'running')]
        for jid in finished:
            del _jobs[jid]
    save_jobs()
    return jsonify({'ok': True, 'removed': len(finished)})

@app.route('/api/diskspace')
def api_diskspace():
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    usage  = shutil.disk_usage(str(MEDIA_DIR))
    folder = sum(f.stat().st_size for f in MEDIA_DIR.rglob('*') if f.is_file())
    return jsonify({'total': usage.total, 'used': usage.used, 'free': usage.free, 'folder': folder})

@app.route('/api/ytdlp/version')
def api_ytdlp_version():
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    try:
        r = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True, timeout=10)
        return jsonify({'version': r.stdout.strip()})
    except Exception:
        log.exception("yt-dlp Version Fehler")
        return jsonify({'error': 'internal error'}), 500

@app.route('/api/ytdlp/update', methods=['POST'])
def api_ytdlp_update():
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    try:
        current = _get_ytdlp_version()
        latest = ''
        try:
            with urllib.request.urlopen('https://pypi.org/pypi/yt-dlp/json', timeout=8) as resp:
                latest = json.loads(resp.read())['info']['version']
        except Exception as e:
            log.warning('PyPI-Versionsabfrage fehlgeschlagen: %s', e)
        def _norm_ver(v: str) -> str:
            parts = v.split('.')
            try:
                return '.'.join(str(int(x)) for x in parts) if len(parts) == 3 else v
            except ValueError:
                return v
        if latest and _norm_ver(latest) == _norm_ver(current):
            log.info('yt-dlp bereits aktuell: %s', current)
            return jsonify({'ok': True, 'up_to_date': True, 'version': current})
        subprocess.run(['pip', 'install', '--upgrade', 'yt-dlp'],
                       capture_output=True, text=True, timeout=120, check=True)
        _ytdlp_ver_cache['ver'] = None  # cache invalidieren
        new_ver = _get_ytdlp_version()
        log.info('yt-dlp aktualisiert auf %s', new_ver)
        return jsonify({'ok': True, 'up_to_date': False, 'version': new_ver})
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'timeout'}), 504
    except Exception:
        log.exception("yt-dlp Update Fehler")
        return jsonify({'error': 'internal error'}), 500

@app.route('/api/cookies/status')
def api_cookies_status():
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    p = Path(COOKIES_PATH)
    if not p.exists():
        return jsonify({'loaded': False, 'size': 0, 'domains': []})
    domains: set[str] = set()
    try:
        with open(p, encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('\t')
                if len(parts) >= 6:
                    domain = parts[0].lstrip('.')
                    # Keep only the main domain (e.g. instagram.com from auth.instagram.com)
                    parts2 = domain.split('.')
                    if len(parts2) >= 2:
                        domain = '.'.join(parts2[-2:])
                    domains.add(domain)
    except Exception:
        pass
    return jsonify({'loaded': True, 'size': p.stat().st_size, 'domains': sorted(domains)})

@app.route('/api/cookies/upload', methods=['POST'])
def api_cookies_upload():
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    if 'file' not in request.files:
        return jsonify({'error': 'no_file'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'no_file'}), 400
    content = f.read()
    if len(content) < 10:
        return jsonify({'error': 'invalid_file'}), 400
    # Append to existing file so multiple cookie files (e.g. Instagram + TikTok) are merged
    with open(COOKIES_PATH, 'ab') as out:
        if out.tell() > 0:
            out.write(b'\n')  # separator between files
        out.write(content)
    total = Path(COOKIES_PATH).stat().st_size
    log.info('Cookies hinzugefügt: +%d bytes, gesamt %d bytes', len(content), total)
    return jsonify({'ok': True, 'size': total})

@app.route('/api/cookies/delete', methods=['POST'])
def api_cookies_delete():
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    Path(COOKIES_PATH).unlink(missing_ok=True)
    log.info('Cookies gelöscht')
    return jsonify({'ok': True})

@app.route('/api/files')
def api_files():
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    with _meta_lock:
        meta = _load_meta()
    files = []
    for p in sorted(MEDIA_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_file() and p.name != '.mediagrab_meta.json':
            st = p.stat()
            entry    = meta.get(p.name, {})
            files.append({'name': p.name, 'size': st.st_size, 'mtime': int(st.st_mtime),
                          'platform': entry.get('platform', ''), 'tag': entry.get('tag', '')})
    return jsonify(files)

@app.route('/api/file/delete/<filename>', methods=['POST'])
def api_file_delete(filename):
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    p = _safe_media_path(filename)
    if not p:
        return jsonify({'error': 'invalid_path'}), 400
    safe_name = p.name
    if not p.exists():
        return jsonify({'error': 'not_found'}), 404
    if not p.is_file():
        return jsonify({'error': 'invalid_path'}), 400
    p.unlink()
    with _meta_lock:
        meta = _load_meta()
        if safe_name in meta:
            meta.pop(safe_name)
            _save_meta(meta)
    log.info('Datei gelöscht: %s', safe_name)
    return jsonify({'ok': True})

@app.route('/api/file/platform/<filename>', methods=['POST'])
def api_file_platform(filename):
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    data     = request.json or {}
    platform = data.get('platform', '').strip()
    p = _safe_media_path(filename)
    if not p:
        return jsonify({'error': 'invalid_path'}), 400
    safe_name = p.name
    if not p.exists():
        return jsonify({'error': 'not_found'}), 404
    with _meta_lock:
        meta = _load_meta()
        entry = meta.get(safe_name, {})
        if platform:
            entry['platform'] = platform
        else:
            entry.pop('platform', None)
        if entry:
            meta[safe_name] = entry
        else:
            meta.pop(safe_name, None)
        _save_meta(meta)
    return jsonify({'ok': True, 'platform': platform})

@app.route('/api/file/tag/<filename>', methods=['POST'])
def api_file_tag(filename):
    if _require_auth():
        return jsonify({'error': 'unauthorized'}), 401
    data = request.json or {}
    tag  = data.get('tag', '').strip()
    if len(tag) > 50:
        return jsonify({'error': 'tag_too_long'}), 400
    p = _safe_media_path(filename)
    if not p:
        return jsonify({'error': 'invalid_path'}), 400
    safe_name = p.name
    if not p.exists():
        return jsonify({'error': 'not_found'}), 404
    with _meta_lock:
        meta = _load_meta()
        entry = meta.get(safe_name, {})
        if tag:
            entry['tag'] = tag
        else:
            entry.pop('tag', None)
        if entry:
            meta[safe_name] = entry
        else:
            meta.pop(safe_name, None)
        _save_meta(meta)
    return jsonify({'ok': True, 'tag': tag})

@app.route('/stream/<path:filename>')
def stream_file(filename):
    if _require_auth():
        return redirect(url_for('login'))
    p = _safe_media_path(filename)
    if not p:
        abort(400)
    return send_from_directory(str(MEDIA_DIR), p.name, as_attachment=False)

@app.route('/files/<path:filename>')
def serve_file(filename):
    if _require_auth():
        return redirect(url_for('login'))
    p = _safe_media_path(filename)
    if not p:
        abort(400)
    return send_from_directory(str(MEDIA_DIR), p.name, as_attachment=True)

@app.route('/manifest.json')
def manifest():
    return send_from_directory('/app/static', 'manifest.json')

@app.route('/sw.js')
def service_worker():
    resp = make_response(send_from_directory('/app/static', 'sw.js'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

if __name__ == '__main__':
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    load_sessions()
    load_jobs()
    _cleanup_temp_files()
    threading.Thread(target=_auto_clear_worker, daemon=True).start()
    log.info('MediaGrab startet auf Port %d ...', PORT)
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
