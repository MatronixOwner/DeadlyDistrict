# -*- coding: utf-8 -*-
"""Звук: эффекты с затуханием по расстоянию, петли (мотор, сирена), радио."""
import math
import os
import random
import time

from panda3d.core import Filename

# Радиостанции: (название, что играет).  'user' — песни игрока из папки music,
# строка — зацикленная дорожка из assets/music, None — тишина.
STATIONS = [
    ('Астрахань FM', 'user'),
    ('Ретро FM', 'retro'),
    ('Бит FM', 'beat'),
    ('Рок-Волна', 'rock'),
    ('Шансон-плюс', 'chanson'),
    ('Радио выключено', None),
]
USER_STATION = 0
RADIO_OFF = len(STATIONS) - 1
# что умеет читать движок (mp3, m4a, wma — через встроенный ffmpeg)
MUSIC_EXT = ('.mp3', '.ogg', '.oga', '.opus', '.wav', '.flac', '.m4a', '.aac', '.wma', '.mp2')
RADIO_GAIN = 1.7            # радио громче остальной музыки: его должно быть слышно за мотором


def music_dirs():
    """Папки, из которых «Астрахань FM» берёт песни: рядом с игрой и в папке пользователя."""
    from . import settings
    res = []
    for d in (os.path.join(settings.find_root(), 'music'), os.path.join(settings.user_dir(), 'music')):
        if d not in res:
            res.append(d)
    return res


def user_music_dir():
    """Папка для песен, которую игра может создать сама (и показать игроку)."""
    from . import settings
    root = os.path.join(settings.find_root(), 'music')
    for d in (root, os.path.join(settings.user_dir(), 'music')):
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, '.write_test')
            with open(probe, 'w'):
                pass
            os.remove(probe)
            return d
        except Exception:
            continue
    return root


def scan_tracks():
    """Все музыкальные файлы игрока (с подпапками), по алфавиту."""
    found = []
    seen = set()
    for d in music_dirs():
        if not os.path.isdir(d):
            continue
        for base, dirs, files in os.walk(d):
            dirs.sort()
            for f in sorted(files):
                if f.lower().endswith(MUSIC_EXT) and not f.startswith('.'):
                    full = os.path.join(base, f)
                    key = os.path.normcase(os.path.abspath(full))
                    if key not in seen:
                        seen.add(key)
                        found.append(full)
            if len(found) > 2000:
                break
    return found


def track_title(path):
    """«Глюкоза - Швайне.mp3» -> «Глюкоза — Швайне»."""
    name = os.path.splitext(os.path.basename(path))[0]
    name = name.replace('_', ' ').strip()
    # номер дорожки в начале: «03. Песня», «03 - Песня»
    i = 0
    while i < len(name) and name[i].isdigit():
        i += 1
    if 0 < i <= 3 and i < len(name) and name[i] in '. -)':
        rest = name[i:].lstrip('. -)')
        if rest:
            name = rest
    name = name.replace(' - ', ' — ')
    return name[:60]


_POLY = {'pistol': 3, 'uzi': 4, 'ak': 4, 'shotgun': 2, 'crash1': 3, 'crash2': 2, 'punch': 2, 'explosion': 3,
         'ricochet': 2, 'scream_m': 2, 'scream_f': 2, 'break': 2, 'glass': 2, 'horn': 2, 'step': 2, 'money': 2}


class Audio(object):

    def __init__(self, base, assets, settings):
        self.base = base
        self.assets = assets
        self.settings = settings
        self.sfx_vol = float(settings.get('sfx_volume'))
        self.music_vol = float(settings.get('music_volume'))
        self.sounds = {}          # name -> [instances], next index
        self.loops = {}           # channel -> [sound, name]
        self.lx = self.ly = 0.0
        self.music_name = None
        self.music_snd = None
        self.music_gain = 1.0
        self.enabled = True
        self._missing = set()
        self.muted = False
        # радио
        self.station = -1
        self.playlist = []          # [(путь, название)]
        self.track_i = 0
        self.track_on = False       # дорожка запущена и должна играть
        self.user_tracks = 0        # сколько своих песен нашлось
        self._order_key = None
        self._resume = {}           # станция -> (номер дорожки, секунда, когда выключили)
        self._fails = 0
        self._new_title = None

    # ------------------------------------------------------------------
    def _load(self, name):
        if name in self._missing:
            return None
        try:
            s = self.base.loader.loadSfx(self.assets.path('sfx', name + '.wav'))
        except Exception:
            s = None
        if s is None:
            self._missing.add(name)
        return s

    def _instance(self, name):
        ent = self.sounds.get(name)
        if ent is None:
            first = self._load(name)
            if first is None:
                return None
            ent = self.sounds[name] = [[first], 0]
        lst = ent[0]
        want = _POLY.get(name, 1)
        idx = ent[1]
        if len(lst) < want:
            s = self._load(name)
            if s is not None:
                lst.append(s)
                idx = len(lst) - 1
        else:
            idx = (idx + 1) % len(lst)
        ent[1] = idx
        return lst[idx]

    def play(self, name, vol=1.0, rate=1.0):
        if not self.enabled or self.muted:
            return None
        v = vol * self.sfx_vol
        if v <= 0.004:
            return None
        s = self._instance(name)
        if s is None:
            return None
        try:
            s.setVolume(min(1.0, v))
            s.setPlayRate(rate)
            s.play()
        except Exception:
            pass
        return s

    def play_at(self, name, x, y, vol=1.0, rate=1.0, maxd=110.0):
        dx, dy = x - self.lx, y - self.ly
        d2 = dx * dx + dy * dy
        if d2 >= maxd * maxd:
            return None
        k = 1.0 - math.sqrt(d2) / maxd
        return self.play(name, vol * k * k, rate)

    def set_listener(self, x, y):
        self.lx, self.ly = x, y

    # ------------------------------------------------------------------
    def loop(self, channel, name, vol=1.0, rate=1.0):
        """Запустить/обновить зацикленный звук на канале (name=None — остановить)."""
        ent = self.loops.get(channel)
        if name is None or vol <= 0.003 or self.muted:
            if ent is not None and ent[2]:
                try:
                    ent[0].stop()
                except Exception:
                    pass
                ent[2] = False
            return
        if ent is None or ent[1] != name:
            if ent is not None:
                try:
                    ent[0].stop()
                except Exception:
                    pass
            s = self._load(name)
            if s is None:
                return
            try:
                s.setLoop(True)
            except Exception:
                pass
            ent = self.loops[channel] = [s, name, False]
        s = ent[0]
        try:
            s.setVolume(min(1.0, vol * self.sfx_vol))
            s.setPlayRate(rate)
            if not ent[2]:
                s.play()
                ent[2] = True
        except Exception:
            pass

    def stop_loops(self):
        for ch in list(self.loops.keys()):
            self.loop(ch, None)

    # ------------------------------------------------------------------
    def _stop_music(self):
        if self.music_snd is not None:
            try:
                self.music_snd.stop()
            except Exception:
                pass
            self.music_snd = None

    def _start(self, filename, loop, gain, start=0.0):
        """Запустить музыкальный файл.  Возвращает True, если он действительно заиграл."""
        self._stop_music()
        self.music_gain = gain
        try:
            s = self.base.loader.loadMusic(filename)
        except Exception:
            s = None
        if s is None:
            return False
        try:
            ln = s.length()
            if ln <= 0.05:
                return False
            s.setLoop(bool(loop))
            self.music_snd = s
            self._apply_music_volume()
            if start > 0.0 and ln > start + 2.0:
                s.setTime(start)
            s.play()
        except Exception:
            self.music_snd = None
            return False
        return True

    def music(self, name, gain=1.0, random_start=True):
        """Включить зацикленную дорожку из assets/music (None — тишина).  Это не радио: заставка меню."""
        self._leave_station()
        if name == self.music_name:
            self.music_gain = gain
            self._apply_music_volume()
            return
        self._stop_music()
        self.music_name = name
        self.music_gain = gain
        if name is None:
            return
        fn = self.assets.path('music', name + '.ogg')
        start = 0.0
        if random_start:
            start = random.uniform(0.0, 30.0)
        self._start(fn, True, gain, start)

    # ------------------------------------------------------------------
    # радио
    # ------------------------------------------------------------------
    def _leave_station(self):
        st = self.station
        if st >= 0 and self.music_snd is not None and self.track_on:
            try:
                t = self.music_snd.getTime()
            except Exception:
                t = 0.0
            self._resume[st] = (self.track_i, t, time.time())
        self.station = -1
        self.track_on = False

    def set_station(self, idx):
        """Переключить радио (-1 или «Радио выключено» — тишина)."""
        if idx == self.station:
            return
        self._leave_station()
        self._stop_music()
        self.music_name = None
        if idx < 0 or idx >= len(STATIONS) or STATIONS[idx][1] is None:
            return
        self.station = idx
        kind = STATIONS[idx][1]
        if kind == 'user':
            self._build_playlist()
        else:
            self.playlist = [(self.assets.path('music', kind + '.ogg'), None)]
        self._fails = 0
        i, t = 0, 0.0
        r = self._resume.get(idx)
        if r is not None and r[0] < len(self.playlist):
            # радио «играло», пока нас не было
            i, t = r[0], r[1] + (time.time() - r[2])
        self.track_i = i
        self._play_track(t)

    def _build_playlist(self):
        files = scan_tracks()
        self.user_tracks = len(files)
        if files:
            key = tuple(files)
            if key != self._order_key:
                self._order_key = key
                order = list(files)
                random.shuffle(order)
                self._order = order
                self._resume.pop(USER_STATION, None)
            self.playlist = [(Filename.fromOsSpecific(f), track_title(f)) for f in self._order]
        else:
            # своих песен нет — в эфире сборная программа из музыки игры
            self._order_key = None
            self.playlist = [(self.assets.path('music', n + '.ogg'), t) for n, t in (
                ('chanson', 'Дворовая'), ('retro', 'Ночной проспект'), ('rock', 'Гаражный рок'),
                ('beat', 'Бит с окраины'), ('theme', 'Порт-Глухов'))]

    def _play_track(self, start=0.0):
        """Запустить текущую дорожку станции; битые файлы пропускаются."""
        n = len(self.playlist)
        single = n == 1                     # единственную дорожку просто зацикливаем
        while n and self._fails < n:
            fn, title = self.playlist[self.track_i % n]
            if self._start(fn, single, RADIO_GAIN, start):
                self._fails = 0
                self.track_on = True
                if title is not None:
                    self._new_title = title
                return True
            self._fails += 1
            self.track_i = (self.track_i + 1) % n
            start = 0.0
        self.track_on = False
        return False

    def next_track(self):
        """Следующая песня на текущей станции."""
        if self.station < 0 or len(self.playlist) < 2:
            return False
        self.track_i = (self.track_i + 1) % len(self.playlist)
        self._fails = 0
        return self._play_track(0.0)

    def update_radio(self):
        """Вызывать каждый кадр.  Возвращает название песни, если только что началась новая."""
        if self.station >= 0 and self.track_on and len(self.playlist) > 1:
            snd = self.music_snd
            playing = False
            if snd is not None:
                try:
                    playing = snd.status() == snd.PLAYING
                except Exception:
                    playing = False
            if not playing:
                self.track_i = (self.track_i + 1) % len(self.playlist)
                self._play_track(0.0)
        t = self._new_title
        self._new_title = None
        return t

    def radio_playing(self):
        return self.station >= 0 and self.track_on

    def _apply_music_volume(self):
        if self.music_snd is not None:
            try:
                self.music_snd.setVolume(max(0.0, min(1.0, self.music_vol * self.music_gain)))
            except Exception:
                pass

    def set_volumes(self, sfx, music):
        self.sfx_vol = float(sfx)
        self.music_vol = float(music)
        self._apply_music_volume()

    def pause_all(self, paused):
        """На паузе глушим петли (музыка продолжает играть тише)."""
        self.muted = paused
        if paused:
            self.stop_loops()
