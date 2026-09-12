#!/usr/bin/env python3
"""Ablage unter /data: Spielstaende und Bestenliste.

Grundsatz: dem Browser wird nichts geglaubt, was er nicht beweisen kann.

* Der Spielstand ist fuer den Server UNDURCHSICHTIG. Er speichert ihn und gibt
  ihn zurueck, ohne hineinzusehen -- die Struktur gehoert der Simulation, und
  eine Pruefung hier waere eine zweite, stets veraltete Kopie davon. Geprueft
  wird nur, wie gross er sein darf. Beim Laden prueft der Client selbst und
  verweigert einen kaputten Stand, statt NaN in die Engine zu fuettern.
* Der Punktestand wird NIE uebernommen, sondern aus den Kennzahlen neu
  gerechnet (siehe scoring.py).
* Jeder Bezeichner, der in einen Dateipfad geht, muss vorher durch ein festes
  Muster -- niemals eine Zeichenkette aus der Anfrage ungeprueft joinen.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
import unicodedata

from werkzeug.utils import safe_join

import atomic_io

SLOT_RE = re.compile(r'^[a-z0-9_-]{1,32}$')
PLAYER_RE = re.compile(r'^[0-9a-f]{32}$')

MAX_SAVE_BYTES = 128 * 1024
MAX_SLOTS = 20
MAX_SCORES_PER_LIST = 50
MAX_NAME_CHARS = 24
MAX_PREFS_BYTES = 8 * 1024

_lock = threading.Lock()


class Store:
    def __init__(self, data_dir: str):
        self.data = data_dir
        self.players = os.path.join(data_dir, 'players')
        self.scores_path = os.path.join(data_dir, 'highscores.json')

    # ── Spieler ───────────────────────────────────────────────────────────────

    @staticmethod
    def new_player_id() -> str:
        """128 Bit aus secrets. Keine Anmeldung, keine personenbezogenen Daten --
        das Token erkennt ein Geraet wieder und sonst nichts."""
        return secrets.token_hex(16)

    @staticmethod
    def valid_player(pid) -> bool:
        return bool(pid) and bool(PLAYER_RE.match(str(pid)))

    def _player_dir(self, pid: str) -> str:
        if not self.valid_player(pid):
            raise ValueError('player')
        # safe_join statt os.path.join: das Muster oben laesst zwar keinen
        # Trenner und kein ".." zu, aber CodeQL erkennt nur `safe_join` als
        # Sanitizer fuer die Taint-Kette -- ohne den bleibt der Alert stehen.
        path = safe_join(self.players, pid)
        if path is None:
            raise ValueError('player')
        return path

    # ── Spielstaende ──────────────────────────────────────────────────────────

    def _slot_path(self, pid: str, slot: str) -> str:
        if not SLOT_RE.match(str(slot)):
            raise ValueError('slot')
        path = safe_join(self._player_dir(pid), f'{slot}.json')
        if path is None:
            raise ValueError('slot')
        return path

    def list_saves(self, pid: str) -> list:
        try:
            names = sorted(os.listdir(self._player_dir(pid)))
        except (OSError, ValueError):
            return []
        out = []
        for name in names:
            # ".prefs.json" liegt im selben Ordner (siehe unten), ist aber kein
            # Spielstand -- ein Punkt am Anfang kann nie aus einem Slot-Namen
            # entstehen (SLOT_RE laesst keinen Punkt zu), also ist der Name
            # eindeutig reserviert.
            if not name.endswith('.json') or name.startswith('.'):
                continue
            path = os.path.join(self._player_dir(pid), name)
            try:
                stat = os.stat(path)
                with open(path, 'r', encoding='utf-8') as f:
                    blob = json.load(f)
            except (OSError, ValueError):
                continue
            out.append({
                'slot': name[:-5],
                'reactor': blob.get('reactor'),
                'scenario': blob.get('scenario'),
                't_sim': blob.get('t_sim'),
                'saved_at': int(stat.st_mtime),
                'size': stat.st_size,
            })
        return out

    def read_save(self, pid: str, slot: str):
        try:
            with open(self._slot_path(pid, slot), 'r', encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def write_save(self, pid: str, slot: str, blob: dict) -> str | None:
        """@return Fehlergrund oder None."""
        raw = json.dumps(blob, separators=(',', ':'))
        if len(raw.encode('utf-8')) > MAX_SAVE_BYTES:
            return 'too_large'
        path = self._slot_path(pid, slot)
        existing = self.list_saves(pid)
        if len(existing) >= MAX_SLOTS and not os.path.exists(path):
            return 'too_many_slots'
        os.makedirs(self._player_dir(pid), exist_ok=True)
        atomic_io.write_text(path, raw)
        return None

    def delete_save(self, pid: str, slot: str) -> bool:
        try:
            os.unlink(self._slot_path(pid, slot))
            return True
        except (OSError, ValueError):
            return False

    # ── Einstellungen ─────────────────────────────────────────────────────────
    #
    # Kleine, fuer den Server ebenso undurchsichtige Ablage wie ein Spielstand
    # (siehe Modulkopf), aber eigene Datei statt eigenem Slot: ein Spielstand
    # namens "prefs" darf diese Datei nie ueberschreiben koennen.

    def _prefs_path(self, pid: str) -> str:
        return os.path.join(self._player_dir(pid), '.prefs.json')

    def read_prefs(self, pid: str) -> dict:
        try:
            with open(self._prefs_path(pid), 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def write_prefs(self, pid: str, blob: dict) -> str | None:
        """@return Fehlergrund oder None."""
        raw = json.dumps(blob, separators=(',', ':'))
        if len(raw.encode('utf-8')) > MAX_PREFS_BYTES:
            return 'too_large'
        os.makedirs(self._player_dir(pid), exist_ok=True)
        atomic_io.write_text(self._prefs_path(pid), raw)
        return None

    # ── Bestenliste ───────────────────────────────────────────────────────────

    @staticmethod
    def clean_name(raw) -> str:
        """Steuerzeichen und Unsichtbares raus, normalisieren, kuerzen."""
        text = unicodedata.normalize('NFC', str(raw or ''))
        text = ''.join(ch for ch in text
                       if unicodedata.category(ch)[0] != 'C' and ch not in '​‌‍﻿')
        text = ' '.join(text.split())
        return text[:MAX_NAME_CHARS]

    def _read_scores(self) -> dict:
        try:
            with open(self.scores_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def list_scores(self, reactor=None, scenario=None, limit=20) -> list:
        data = self._read_scores()
        out = []
        for key, entries in data.items():
            if not isinstance(entries, list):
                continue
            r, _, sc = key.partition('/')
            if reactor and r != reactor:
                continue
            if scenario and sc != scenario:
                continue
            for e in entries:
                out.append(e)
        out.sort(key=lambda e: e.get('score', 0), reverse=True)
        return out[:max(1, min(int(limit or 20), MAX_SCORES_PER_LIST))]

    def add_score(self, reactor: str, scenario: str, name: str, points: int, summary: dict) -> dict:
        entry = {
            'name': name,
            'reactor': reactor,
            'scenario': scenario,
            'score': int(points),
            'completed': bool(summary.get('completed')),
            'duration_s': summary.get('duration_s'),
            # Zeitstempel ausschliesslich serverseitig -- ein mitgeschickter
            # waere frei waehlbar und damit wertlos.
            'at': int(time.time()),
        }
        with _lock:
            data = self._read_scores()
            key = f'{reactor}/{scenario}'
            entries = data.get(key) if isinstance(data.get(key), list) else []
            entries.append(entry)
            entries.sort(key=lambda e: e.get('score', 0), reverse=True)
            data[key] = entries[:MAX_SCORES_PER_LIST]
            os.makedirs(self.data, exist_ok=True)
            atomic_io.write_json(self.scores_path, data, ensure_ascii=False)
        return entry


class RateLimit:
    """Einfache Zaehler je Schluessel und Zeitfenster.

    Zwei Schluessel je Anfrage: Spieler-Token UND Remote-Adresse. Nur das Token
    zu nehmen hiesse, dass ein geloeschter Cookie die Grenze aufhebt; nur die
    Adresse zu nehmen hiesse, dass hinter einem Proxy alle dieselbe Grenze
    teilen. (MyPage ist beim gleichen Wechsel ueber genau das gestolpert.)
    """

    def __init__(self):
        self._hits: dict[str, list] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: float) -> bool:
        """@return True, wenn die Anfrage durchgelassen wird."""
        now = time.monotonic()
        with self._lock:
            times = self._hits.setdefault(key, [])
            cutoff = now - window_s
            times[:] = [t for t in times if t > cutoff]
            if len(times) >= limit:
                return False
            times.append(now)
            # Verwaiste Schluessel aufraeumen, damit der Speicher nicht waechst.
            if len(self._hits) > 4096:
                for k in [k for k, v in self._hits.items() if not v]:
                    self._hits.pop(k, None)
            return True
