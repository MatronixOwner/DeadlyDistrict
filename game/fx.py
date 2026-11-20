# -*- coding: utf-8 -*-
"""Эффекты: частицы, трассеры, следы на земле."""
import math
import random

from panda3d.core import NodePath, CardMaker, TransparencyAttrib, ColorBlendAttrib, DepthOffsetAttrib

from .masks import NO_SHADOW

MAX_PARTICLES = 260


class _P(object):
    __slots__ = ('np', 'x', 'y', 'z', 'vx', 'vy', 'vz', 'life', 'max', 's0', 's1', 'r', 'g', 'b', 'a', 'grav',
                 'drag', 'kind', 'fade_in')


class Fx(object):

    def __init__(self, world):
        self.world = world
        self.assets = world.assets
        self.root = world.render.attachNewNode('fx')
        self.root.hide(NO_SHADOW)           # дым, искры, метки: тени не отбрасывают (см. masks.py)
        self.root.setLightOff(1)
        self.active = []
        self.pools = {}
        self.protos = {}
        self._proto('smoke', 'smoke', 'blend')
        self._proto('fire', 'fire', 'add')
        self._proto('spark', 'spark', 'add')
        self._proto('blood', 'blood', 'blend')
        self._proto('debris', 'debris', 'blend')
        self._proto('glow', 'glow', 'add')
        self._proto('muzzle', 'muzzle', 'add')
        self._proto('money', 'money', 'blend')
        # трассеры
        self.tracers = []
        self.tracer_pool = []
        cm = CardMaker('tr')
        cm.setFrame(-0.5, 0.5, 0.0, 1.0)
        self.tracer_proto = NodePath(cm.generate())
        self.tracer_proto.setTexture(self.assets.tex('beam', clamp=True, smooth=True))
        self.tracer_proto.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha,
                                                          ColorBlendAttrib.OOne))
        self.tracer_proto.setDepthWrite(False)
        self.tracer_proto.setTwoSided(True)
        self.tracer_proto.setBin('fixed', 30)
        self.tracer_proto.setFogOff(1)
        # следы на земле
        self.decals = []
        self.max_decals = 48
        self.decal_protos = {}
        for name in ('scorch', 'blood', 'skid', 'lightpool'):
            cm = CardMaker('d_' + name)
            cm.setFrame(-0.5, 0.5, -0.5, 0.5)
            np_ = NodePath(cm.generate())
            np_.setP(-90)
            np_.setTexture(self.assets.tex(name, clamp=True, smooth=True))
            np_.setTransparency(TransparencyAttrib.MAlpha)
            np_.setDepthWrite(False)
            np_.setAttrib(DepthOffsetAttrib.make(1))
            np_.setBin('fixed', 3)
            self.decal_protos[name] = np_
        self.shake = 0.0

    def _proto(self, kind, tex, mode):
        cm = CardMaker(kind)
        cm.setFrame(-0.5, 0.5, -0.5, 0.5)
        np_ = NodePath(cm.generate())
        np_.setTexture(self.assets.tex(tex, clamp=True, smooth=True))
        if mode == 'add':
            np_.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha,
                                                ColorBlendAttrib.OOne))
            np_.setFogOff(1)
            np_.setBin('fixed', 25)
        else:
            np_.setTransparency(TransparencyAttrib.MAlpha)
            np_.setBin('fixed', 22)
        np_.setDepthWrite(False)
        np_.setBillboardPointEye()
        self.protos[kind] = np_
        self.pools[kind] = []

    # ------------------------------------------------------------------
    def spawn(self, kind, x, y, z, vx=0.0, vy=0.0, vz=0.0, life=1.0, s0=0.5, s1=1.0, color=(1, 1, 1), alpha=1.0,
              grav=0.0, drag=0.0, fade_in=0.0):
        if len(self.active) >= MAX_PARTICLES:
            return None
        pool = self.pools[kind]
        if pool:
            p = pool.pop()
            p.np.show()
        else:
            p = _P()
            p.np = self.protos[kind].copyTo(self.root)
            p.kind = kind
        p.x, p.y, p.z = x, y, z
        p.vx, p.vy, p.vz = vx, vy, vz
        p.life = p.max = life
        p.s0, p.s1 = s0, s1
        p.r, p.g, p.b = color
        p.a = alpha
        p.grav = grav
        p.drag = drag
        p.fade_in = fade_in
        p.np.setPos(x, y, z)
        p.np.setScale(s0)
        p.np.setColorScale(p.r, p.g, p.b, 0.0 if fade_in > 0 else alpha)
        self.active.append(p)
        return p

    def update(self, dt):
        act = self.active
        i = 0
        n = len(act)
        while i < n:
            p = act[i]
            p.life -= dt
            if p.life <= 0.0:
                p.np.hide()
                self.pools[p.kind].append(p)
                n -= 1
                act[i] = act[n]
                act.pop()
                continue
            if p.grav:
                p.vz -= p.grav * dt
            if p.drag:
                k = 1.0 - p.drag * dt
                if k < 0.0:
                    k = 0.0
                p.vx *= k
                p.vy *= k
                p.vz *= k
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.z += p.vz * dt
            if p.grav and p.z < 0.05:
                p.z = 0.05
                p.vz = -p.vz * 0.3
                p.vx *= 0.5
                p.vy *= 0.5
            t = 1.0 - p.life / p.max
            a = p.a * (1.0 - t * t)
            if p.fade_in > 0.0 and t < p.fade_in:
                a *= t / p.fade_in
            np_ = p.np
            np_.setPos(p.x, p.y, p.z)
            np_.setScale(p.s0 + (p.s1 - p.s0) * t)
            np_.setColorScale(p.r, p.g, p.b, a)
            i += 1
        # трассеры
        if self.tracers:
            keep = []
            for tr in self.tracers:
                tr[1] -= dt
                if tr[1] <= 0.0:
                    tr[0].hide()
                    self.tracer_pool.append(tr[0])
                else:
                    tr[0].setColorScale(tr[2][0], tr[2][1], tr[2][2], tr[1] / tr[3])
                    keep.append(tr)
            self.tracers = keep
        if self.decals:
            for d in self.decals:
                if d[1] > 0.0:
                    d[1] -= dt
                    if d[1] < 3.0:
                        d[0].setAlphaScale(max(0.0, d[1] / 3.0) * d[2])
            if self.decals[0][1] <= 0.0 and self.decals[0][3]:
                d = self.decals.pop(0)
                d[0].removeNode()
        if self.shake > 0.0:
            self.shake = max(0.0, self.shake - dt * 1.6)

    # ------------------------------------------------------------------
    def smoke(self, x, y, z, size=1.0, dark=False, life=1.6):
        c = 0.12 if dark else 0.62
        c += random.uniform(-0.05, 0.05)
        self.spawn('smoke', x + random.uniform(-0.15, 0.15), y + random.uniform(-0.15, 0.15), z,
                   random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3), random.uniform(0.9, 1.7),
                   life * random.uniform(0.8, 1.2), 0.5 * size, 2.2 * size, (c, c, c), 0.6, drag=0.4, fade_in=0.15)

    def fire(self, x, y, z, size=1.0):
        self.spawn('fire', x + random.uniform(-0.2, 0.2) * size, y + random.uniform(-0.2, 0.2) * size, z,
                   random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3), random.uniform(1.2, 2.6),
                   random.uniform(0.35, 0.7), 1.2 * size, 0.3 * size, (1.0, 0.75, 0.4), 0.9)

    def sparks(self, x, y, z, n=4, nx=0.0, ny=0.0, nz=1.0, color=(1.0, 0.85, 0.45)):
        for _ in range(n):
            self.spawn('spark', x, y, z, nx * 3 + random.uniform(-3, 3), ny * 3 + random.uniform(-3, 3),
                       nz * 3 + random.uniform(0, 4), random.uniform(0.15, 0.4), 0.22, 0.05, color, 1.0, grav=14.0)

    def dust(self, x, y, z, n=2, color=(0.6, 0.58, 0.54)):
        for _ in range(n):
            self.spawn('smoke', x, y, z, random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6),
                       random.uniform(0.2, 0.9), random.uniform(0.4, 0.8), 0.2, 0.9, color, 0.5, drag=1.5)

    def blood(self, x, y, z, n=4, dx=0.0, dy=0.0):
        for _ in range(n):
            self.spawn('blood', x, y, z, dx * 2 + random.uniform(-1.5, 1.5), dy * 2 + random.uniform(-1.5, 1.5),
                       random.uniform(0.5, 3.0), random.uniform(0.3, 0.6), 0.16, 0.34, (0.75, 0.05, 0.05), 0.95,
                       grav=12.0)

    def debris(self, x, y, z, n=6, color=(0.5, 0.5, 0.5), power=5.0, size=0.3):
        for _ in range(n):
            a = random.uniform(0, 6.283)
            s = random.uniform(0.3, 1.0) * power
            self.spawn('debris', x, y, z, math.cos(a) * s, math.sin(a) * s, random.uniform(2.0, 7.0),
                       random.uniform(0.7, 1.4), size, size * 0.7, color, 1.0, grav=16.0)

    def money(self, x, y, z, n=5):
        for _ in range(n):
            self.spawn('money', x, y, z, random.uniform(-2, 2), random.uniform(-2, 2), random.uniform(2, 5),
                       random.uniform(0.8, 1.3), 0.35, 0.3, (1, 1, 1), 1.0, grav=7.0, drag=0.8)

    def muzzle(self, x, y, z, size=0.5):
        self.spawn('muzzle', x, y, z, 0, 0, 0, 0.05, size, size * 1.3, (1.0, 0.9, 0.6), 1.0)

    def flash(self, x, y, z, size=6.0, color=(1.0, 0.8, 0.5), life=0.25):
        self.spawn('glow', x, y, z, 0, 0, 0, life, size * 0.4, size, color, 1.0)

    def splash(self, x, y, z, size=1.0):
        for _ in range(8):
            a = random.uniform(0, 6.283)
            s = random.uniform(0.5, 2.5) * size
            self.spawn('smoke', x, y, z, math.cos(a) * s, math.sin(a) * s, random.uniform(3, 7) * size,
                       random.uniform(0.6, 1.0), 0.5 * size, 1.6 * size, (0.8, 0.9, 1.0), 0.7, grav=12.0)

    def explosion(self, x, y, z, size=1.0):
        self.flash(x, y, z + 1.0, 14.0 * size)
        for _ in range(int(9 * size) + 3):
            a = random.uniform(0, 6.283)
            s = random.uniform(0.5, 5.0) * size
            self.spawn('fire', x, y, z + random.uniform(0.2, 1.5), math.cos(a) * s, math.sin(a) * s,
                       random.uniform(1.0, 6.0), random.uniform(0.4, 0.9), 2.0 * size, 4.5 * size,
                       (1.0, 0.7, 0.35), 1.0, drag=1.5)
        for _ in range(int(7 * size) + 2):
            a = random.uniform(0, 6.283)
            s = random.uniform(0.5, 3.0) * size
            c = random.uniform(0.08, 0.22)
            self.spawn('smoke', x, y, z + random.uniform(0.5, 2.0), math.cos(a) * s, math.sin(a) * s,
                       random.uniform(1.5, 4.0), random.uniform(1.6, 3.0), 2.0 * size, 6.5 * size, (c, c, c), 0.75,
                       drag=0.8, fade_in=0.1)
        self.debris(x, y, z + 0.5, int(8 * size) + 2, (0.16, 0.15, 0.14), 9.0 * size, 0.4)
        self.sparks(x, y, z + 0.6, 8)
        self.decal('scorch', x, y, 5.5 * size, life=70.0)

    # ------------------------------------------------------------------
    def tracer(self, x0, y0, z0, x1, y1, z1, color=(1.0, 0.9, 0.6), width=0.07, life=0.07):
        if self.tracer_pool:
            np_ = self.tracer_pool.pop()
            np_.show()
        else:
            if len(self.tracers) > 40:
                return
            np_ = self.tracer_proto.copyTo(self.root)
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
        L = math.sqrt(dx * dx + dy * dy + dz * dz)
        if L < 0.01:
            np_.hide()
            self.tracer_pool.append(np_)
            return
        np_.setPos(x0, y0, z0)
        # карточка лежит в плоскости XZ: ось Z вытягиваем вдоль луча
        h = math.degrees(math.atan2(dy, dx)) - 90.0
        p = math.degrees(math.asin(max(-1.0, min(1.0, dz / L))))
        np_.setHpr(h, p - 90.0, 0)
        np_.setScale(width, 1.0, L)
        np_.setColorScale(color[0], color[1], color[2], 1.0)
        self.tracers.append([np_, life, color, life])

    def decal(self, name, x, y, size, life=40.0, alpha=1.0, yaw=None, z=None, sy=None):
        if z is None:
            z = self.world.city.ground_z(x, y)
            if z < -0.4:
                return None
        np_ = self.decal_protos[name].copyTo(self.root)
        np_.setPos(x, y, z + 0.03)
        np_.setH(random.uniform(0, 360) if yaw is None else math.degrees(yaw) - 90.0)
        np_.setScale(size, 1.0, sy if sy is not None else size)
        if alpha < 1.0:
            np_.setAlphaScale(alpha)
        self.decals.append([np_, life, alpha, True])
        if len(self.decals) > self.max_decals:
            d = self.decals.pop(0)
            d[0].removeNode()
        return np_

    def add_shake(self, amount):
        self.shake = min(1.5, self.shake + amount)

    def clear(self):
        for p in self.active:
            p.np.hide()
            self.pools[p.kind].append(p)
        self.active = []
        for d in self.decals:
            d[0].removeNode()
        self.decals = []
        for tr in self.tracers:
            tr[0].hide()
            self.tracer_pool.append(tr[0])
        self.tracers = []
