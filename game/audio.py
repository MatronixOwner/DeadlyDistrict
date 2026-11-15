# -*- coding: utf-8 -*-
"""Звук: эффекты с затуханием по расстоянию, петли (мотор, сирена), радио."""
import math
import random

STATIONS = [
    ('Ретро FM', 'retro'),
    ('Бит FM', 'beat'),
    ('Рок-Волна', 'rock'),
    ('Шансон-плюс', 'chanson'),
    ('Радио выключено', None),
]

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
    def music(self, name, gain=1.0, random_start=True):
        """Включить музыкальную дорожку (None — тишина)."""
        if name == self.music_name:
            self.music_gain = gain
            self._apply_music_volume()
            return
        if self.music_snd is not None:
            try:
                self.music_snd.stop()
            except Exception:
                pass
            self.music_snd = None
        self.music_name = name
        self.music_gain = gain
        if name is None:
            return
        try:
            s = self.base.loader.loadMusic(self.assets.path('music', name + '.ogg'))
        except Exception:
            s = None
        if s is None:
            return
        try:
            s.setLoop(True)
            self.music_snd = s
            self._apply_music_volume()
            if random_start:
                ln = s.length()
                if ln > 5.0:
                    s.setTime(random.uniform(0.0, ln - 2.0))
            s.play()
        except Exception:
            self.music_snd = None

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
