# -*- coding: utf-8 -*-
"""Прохожие: появление, исчезновение и общая реакция на происходящее."""
import math
import random

from .ped import Ped
from .defs import random_look, cop_look, gang_look, W_PISTOL, W_BAT, W_UZI
from .mathutil import clamp
from .settings import TRAFFIC_LEVELS

SPAWN_MIN = 34.0
SPAWN_MAX = 80.0
DESPAWN = 112.0


class Crowd(object):

    def __init__(self, world):
        self.w = world
        self.rn = world.roadnet
        lv = TRAFFIC_LEVELS[int(clamp(world.settings.get('traffic'), 0, 2))]
        self.max_peds = lv[1]
        self.density = 1.0
        self.enabled = True
        self.spawn_t = 0.0
        self.think_t = 0.0
        self.scream_cd = 0.0
        self.n_civ = 0
        self.gangs_hostile = False

    # ------------------------------------------------------------------
    def update(self, dt):
        w = self.w
        px, py = w.player.pos()
        n = 0
        far2 = 46.0 * 46.0
        for p in w.peds:
            if p.is_player or p.removed:
                continue
            dx, dy = p.x - px, p.y - py
            d2 = dx * dx + dy * dy
            p.lod_far = d2 > far2
            if p.keep:
                continue
            if p.kind in ('civ', 'gang', 'cop') and p.spawned:
                n += 1
            if p.vehicle is not None:
                continue
            if d2 > DESPAWN * DESPAWN:
                w.remove_ped(p)
                continue
            if p.state == 'dead':
                if p.despawn_t > 40.0 or (p.despawn_t > 12.0 and not w.visible(p.x, p.y, 1.0)):
                    w.remove_ped(p)
                continue
            if d2 > 58.0 * 58.0:
                if w.visible(p.x, p.y, 1.5):
                    p.unseen_t = 0.0
                else:
                    p.unseen_t += dt
                    if p.unseen_t > 4.0:
                        w.remove_ped(p)
        self.n_civ = n
        if self.scream_cd > 0.0:
            self.scream_cd -= dt
        if self.enabled:
            self.spawn_t -= dt
            if self.spawn_t <= 0.0:
                self.spawn_t = 0.16
                if n < self.max_peds * self.density * self._time_factor():
                    self._spawn(px, py, False)
        self.think_t -= dt
        if self.think_t <= 0.0:
            self.think_t = 0.3
            self._react(px, py)

    def _time_factor(self):
        """Ночью и в дождь людей на улицах меньше."""
        sky = self.w.sky
        k = 1.0
        if sky is not None:
            h = sky.hour
            if h < 5.5 or h > 23.0:
                k = 0.4
            elif h < 7.0 or h > 21.0:
                k = 0.7
            if sky.rain > 0.5:
                k *= 0.6
        return k

    def populate(self):
        px, py = self.w.player.pos()
        target = int(self.max_peds * self.density * self._time_factor())
        for _ in range(target * 6):
            n = sum(1 for p in self.w.peds if p.spawned)
            if n >= target:
                break
            self._spawn(px, py, True)

    # ------------------------------------------------------------------
    def _spawn(self, px, py, initial):
        w = self.w
        vx, vy = w.player.velocity()
        cx, cy = px + vx * 1.5, py + vy * 1.5
        nodes = self.rn.ped_nodes_near(cx, cy, SPAWN_MAX)
        if not nodes:
            return None
        for _ in range(8):
            a = nodes[int(random.random() * len(nodes))]
            if not a.edges:
                continue
            b, kind, info = a.edges[int(random.random() * len(a.edges))]
            if kind == 'cross':
                continue
            t = random.random()
            x = a.x + (b.x - a.x) * t
            y = a.y + (b.y - a.y) * t
            d = math.hypot(x - px, y - py)
            if initial:
                if d < 9.0 or d > SPAWN_MAX:
                    continue
            else:
                if d < SPAWN_MIN or d > SPAWN_MAX:
                    continue
                if d < 62.0 and w.visible(x, y, 1.0):
                    continue
            zone = w.city.zone_at(x, y)
            if zone == 'P':
                zone = 'R'
            if zone not in 'DOGRIB':
                zone = 'B' if zone == 'beach' else 'D'
            p = self.make_ped(x, y, zone)
            p.spawned = True
            # идём к узлу b по ребру a-b
            dx, dy = b.x - a.x, b.y - a.y
            L = math.hypot(dx, dy) or 1.0
            p.x -= dy / L * p.lat
            p.y += dx / L * p.lat
            p.yaw = math.atan2(dy, dx)
            p.pn = b
            p.pn_prev = a
            p.tx = b.x - dy / L * p.lat
            p.ty = b.y + dx / L * p.lat
            p.set_state('walk')
            p.sync()
            return p
        return None

    def make_ped(self, x, y, zone='D'):
        w = self.w
        r = random.random()
        if zone == 'G' and r < 0.26:
            p = w.spawn_ped(x, y, 0.0, gang_look('reds'), 'gang')
            p.gang = 'reds'
            p.set_weapon(W_PISTOL if random.random() < 0.45 else W_BAT)
            p.health = p.max_health = 120.0
            p.accuracy = 0.35
            p.brave = 1.0
            p.money = random.randint(30, 120)
        elif zone in 'DOBR' and r < 0.045:
            p = w.spawn_ped(x, y, 0.0, cop_look(), 'cop')
            p.set_weapon(W_PISTOL)
            p.health = p.max_health = 120.0
            p.accuracy = 0.4
            p.brave = 1.0
            p.money = 0
        else:
            p = w.spawn_ped(x, y, 0.0, random_look(random, zone), 'civ')
        return p

    # ------------------------------------------------------------------
    def _react(self, px, py):
        """Периодические реакции прохожих на игрока."""
        w = self.w
        pl = w.player
        pp = pl.ped
        armed_aim = pl.aiming and pl.weapon.kind != 'melee' and pl.vehicle is None
        if armed_aim:
            cyaw = pl.aim_yaw
            ax, ay = math.cos(cyaw), math.sin(cyaw)
        veh = pl.vehicle
        fast = veh is not None and abs(veh.speed) > 7.0
        if fast:
            vx, vy = veh.vx, veh.vy
            sp = math.hypot(vx, vy) or 1.0
            vx, vy = vx / sp, vy / sp
        for p in w.peds:
            if p.is_player or p.dead or p.vehicle is not None or p.lod_far:
                continue
            st = p.state
            if st not in ('walk', 'wait', 'idle'):
                continue
            if p.kind != 'civ':
                continue
            dx, dy = p.x - px, p.y - py
            d2 = dx * dx + dy * dy
            if armed_aim and d2 < 15.0 * 15.0:
                d = math.sqrt(d2) or 1.0
                if (dx * ax + dy * ay) / d > 0.93:
                    if random.random() < 0.5:
                        p.threat = (px, py)
                        p.set_state('cower', 1.5 + random.random() * 2.0)
                    else:
                        p.flee_from(px, py, 8.0)
                    self.scream(p)
                    continue
            if fast and d2 < 22.0 * 22.0:
                # машина несётся на прохожего — отпрыгнуть
                f = dx * vx + dy * vy
                l = dy * vx - dx * vy
                if 0.0 < f < sp * 1.3 and abs(l) < 2.4:
                    side = 1.0 if l >= 0 else -1.0
                    p.flee_dir = math.atan2(vx * side, -vy * side)
                    p.threat = (px, py)
                    p.set_state('flee', 2.5)
                    if random.random() < 0.4:
                        self.scream(p)

    def scream(self, p):
        if self.scream_cd > 0.0:
            return
        self.scream_cd = 0.5 + random.random() * 0.8
        self.w.audio.play_at('scream_f' if p.look.female else 'scream_m', p.x, p.y, 0.8,
                             0.9 + random.random() * 0.25, 60.0)

    def panic(self, x, y, radius, source=None):
        """Выстрелы/взрыв: прохожие разбегаются, водители давят на газ."""
        w = self.w
        r2 = radius * radius
        n = 0
        for p in w.peds:
            if p.is_player or p.dead or p.vehicle is not None:
                continue
            dx, dy = p.x - x, p.y - y
            if dx * dx + dy * dy > r2:
                continue
            if p.kind == 'civ':
                if p.state in ('walk', 'wait', 'idle', 'cower', 'return'):
                    p.flee_from(x, y, 9.0 + random.random() * 6.0)
                    n += 1
            elif p.kind == 'gang' and source is not None and p.target is None and p.state in ('walk', 'wait', 'idle'):
                if source.is_player and (dx * dx + dy * dy) < 30.0 * 30.0 and random.random() < 0.5:
                    p.attack(source)
        if n and random.random() < 0.7:
            for p in w.peds:
                if p.state == 'flee' and not p.is_player:
                    self.scream(p)
                    break
        cr2 = (radius * 0.8) ** 2
        tr = w.traffic
        for v in w.vehicles:
            if v.npc and not v.dead and v.owner is None:
                dx, dy = v.x - x, v.y - y
                if dx * dx + dy * dy < cr2 and random.random() < 0.7:
                    tr.scare(v)
