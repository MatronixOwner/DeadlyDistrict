# -*- coding: utf-8 -*-
"""Небо, смена дня и ночи, погода."""
import math
import random

from panda3d.core import (AmbientLight, DirectionalLight, Fog, LColor, NodePath, CardMaker, TransparencyAttrib,
                          ColorBlendAttrib, TextureStage)

from .meshbuilder import MeshBuilder
from .mathutil import clamp, lerp, DEG
from .settings import DRAW_DIST

# час: (зенит, горизонт, рассеянный свет, солнце)
KEYS = [
    (0.0, (0.02, 0.03, 0.09), (0.06, 0.08, 0.16), (0.30, 0.33, 0.46), (0.14, 0.16, 0.26)),
    (4.8, (0.02, 0.03, 0.09), (0.06, 0.08, 0.16), (0.30, 0.33, 0.46), (0.14, 0.16, 0.26)),
    (6.2, (0.22, 0.30, 0.55), (0.90, 0.58, 0.42), (0.48, 0.44, 0.46), (0.62, 0.42, 0.30)),
    (8.0, (0.22, 0.48, 0.88), (0.62, 0.78, 0.95), (0.66, 0.67, 0.70), (0.56, 0.54, 0.48)),
    (17.0, (0.22, 0.48, 0.88), (0.62, 0.78, 0.95), (0.66, 0.67, 0.70), (0.56, 0.54, 0.48)),
    (19.3, (0.24, 0.24, 0.52), (0.95, 0.52, 0.30), (0.50, 0.42, 0.42), (0.62, 0.38, 0.24)),
    (20.8, (0.04, 0.05, 0.14), (0.14, 0.12, 0.22), (0.32, 0.34, 0.46), (0.14, 0.16, 0.26)),
    (24.0, (0.02, 0.03, 0.09), (0.06, 0.08, 0.16), (0.30, 0.33, 0.46), (0.14, 0.16, 0.26)),
]
WEATHERS = [('clear', 0.56), ('cloudy', 0.22), ('rain', 0.14), ('fog', 0.08)]
WEATHER_NAMES = {'clear': 'ясно', 'cloudy': 'облачно', 'rain': 'дождь', 'fog': 'туман'}


def _mix(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def set_lens_range(base, far):
    """Ближняя и дальняя плоскости камеры.

    Программный рендерер (запасной вариант для ПК без OpenGL) неточно отсекает геометрию у дальней
    плоскости: далёкие предметы «просвечивают» сквозь стены.  Для него плоскость отодвигается, а всё
    дальнее и так скрыто туманом."""
    try:
        if base.pipe is not None and base.pipe.getInterfaceName() == 'TinyPanda':
            far = max(far * 5.0, 4600.0)            # дальше любого края мира
    except Exception:
        pass
    base.camLens.setNearFar(0.35, far)


class Sky(object):

    def __init__(self, world):
        self.w = world
        base = world.base
        self.base = base
        self.hour = 8.0
        self.day = 1
        self.night = 0.0
        self.rain = 0.0
        self.clouds_k = 0.0
        self.fog_k = 0.0
        self.weather = 'clear'
        self.next_weather = 'clear'
        self.weather_t = 150.0
        self.time_scale = 1.0
        self.fog_color = (0.6, 0.75, 0.9)
        dd = DRAW_DIST[int(clamp(world.settings.get('draw_distance'), 0, 2))]
        self.fog_start, self.far = dd
        set_lens_range(base, self.far)
        # свет
        self.amb = AmbientLight('amb')
        self.sun = DirectionalLight('sun')
        self.fill = DirectionalLight('fill')
        self.amb_np = world.root.attachNewNode(self.amb)
        self.sun_np = world.root.attachNewNode(self.sun)
        self.fill_np = world.root.attachNewNode(self.fill)
        world.root.setLight(self.amb_np)
        world.root.setLight(self.sun_np)
        world.root.setLight(self.fill_np)
        self.fog = Fog('fog')
        self.fog.setLinearRange(self.fog_start, self.far)
        world.root.setFog(self.fog)
        # купол неба
        self.root = base.render.attachNewNode('sky')
        self.root.setLightOff(1)
        self.root.setFogOff(1)
        self.root.setDepthWrite(False)
        self.root.setDepthTest(False)
        self.root.setBin('background', 0)
        R = 100.0
        mb = MeshBuilder()
        n = 16
        rings = [(0.0, 0.0), (0.12, 0.45), (0.3, 0.85), (0.6, 1.0), (1.0, 1.0)]     # (доля высоты, альфа)
        for i in range(n):
            a0, a1 = i * 2 * math.pi / n, (i + 1) * 2 * math.pi / n
            for k in range(len(rings) - 1):
                e0, al0 = rings[k]
                e1, al1 = rings[k + 1]
                e0 *= math.pi / 2
                e1 *= math.pi / 2
                p00 = (math.cos(a0) * math.cos(e0) * R, math.sin(a0) * math.cos(e0) * R, math.sin(e0) * R)
                p10 = (math.cos(a1) * math.cos(e0) * R, math.sin(a1) * math.cos(e0) * R, math.sin(e0) * R)
                p01 = (math.cos(a0) * math.cos(e1) * R, math.sin(a0) * math.cos(e1) * R, math.sin(e1) * R)
                p11 = (math.cos(a1) * math.cos(e1) * R, math.sin(a1) * math.cos(e1) * R, math.sin(e1) * R)
                c0 = (1, 1, 1, al0)
                c1 = (1, 1, 1, al1)
                mb.quad('dome', p10, p00, p01, p11, colors=(c0, c0, c1, c1))
        self.dome = mb.build('dome')
        self.dome.reparentTo(self.root)
        self.dome.setTransparency(TransparencyAttrib.MAlpha)
        self.dome.setTwoSided(True)
        self.stars_two = True
        self.dome.setBin('background', 1)
        # звёзды
        mb = MeshBuilder()
        for i in range(n):
            a0, a1 = i * 2 * math.pi / n, (i + 1) * 2 * math.pi / n
            for k, (e0, e1) in enumerate(((0.12, 0.45), (0.45, 0.8), (0.8, 1.0))):
                e0 *= math.pi / 2
                e1 *= math.pi / 2
                p00 = (math.cos(a0) * math.cos(e0) * R, math.sin(a0) * math.cos(e0) * R, math.sin(e0) * R)
                p10 = (math.cos(a1) * math.cos(e0) * R, math.sin(a1) * math.cos(e0) * R, math.sin(e0) * R)
                p01 = (math.cos(a0) * math.cos(e1) * R, math.sin(a0) * math.cos(e1) * R, math.sin(e1) * R)
                p11 = (math.cos(a1) * math.cos(e1) * R, math.sin(a1) * math.cos(e1) * R, math.sin(e1) * R)
                u0, u1 = i * 0.5, (i + 1) * 0.5
                mb.quad('stars', p10, p00, p01, p11, uvs=((u1, k), (u0, k), (u0, k + 1), (u1, k + 1)),
                        colors=((1, 1, 1, 0.0 if k == 0 else 1.0),) * 2 + ((1, 1, 1, 1),) * 2)
        self.stars = mb.build('stars')
        self.stars.reparentTo(self.root)
        self.stars.setTexture(world.assets.tex('stars'))
        self.stars.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha,
                                                   ColorBlendAttrib.OOne))
        self.stars.setBin('background', 2)
        self.stars.setTwoSided(True)
        self.stars.hide()
        self.sun_card = self._card('sun', 16.0, True)
        self.moon_card = self._card('moon', 9.0, False)
        # облака
        self.clouds = []
        rnd = random.Random(7)
        for i in range(16):
            c = self._card('cloud', 1.0, False)
            c.setTransparency(TransparencyAttrib.MAlpha)
            az = i * 2 * math.pi / 16 + rnd.uniform(-0.15, 0.15)
            el = rnd.uniform(0.14, 0.75)
            sc = rnd.uniform(38.0, 78.0)
            c.setScale(sc, 1, sc * 0.42)
            c.setBin('background', 4)
            self.clouds.append([c, az, el, rnd.uniform(0.6, 1.4)])
        # дождь
        self.rain_np = self._build_rain()
        self.rain_z = 0.0
        self.lights_on = False
        self.night_on = False
        self.w.citymesh.night_root.hide()
        self.w.citymesh.night_root.setLightOff(1)
        self._apply(0.0)

    def _card(self, tex, size, add):
        cm = CardMaker(tex)
        cm.setFrame(-0.5, 0.5, -0.5, 0.5)
        np_ = self.root.attachNewNode(cm.generate())
        np_.setTexture(self.w.assets.tex(tex, clamp=True, smooth=True))
        np_.setScale(size)
        np_.setBillboardPointEye()
        if add:
            np_.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha,
                                                ColorBlendAttrib.OOne))
        else:
            np_.setTransparency(TransparencyAttrib.MAlpha)
        np_.setBin('background', 3)
        return np_

    def _build_rain(self):
        mb = MeshBuilder()
        rnd = random.Random(11)
        self.rain_h = 14.0
        for i in range(420):
            x, y = rnd.uniform(-13, 13), rnd.uniform(-13, 13)
            if abs(x) < 0.8 and abs(y) < 0.8:
                continue
            z = rnd.uniform(0, self.rain_h)
            a = rnd.uniform(0, math.pi)
            w2 = 0.011 + 0.0012 * math.hypot(x, y)       # дальние струи чуть толще, чтобы не пропадали
            h = rnd.uniform(0.7, 1.3)
            dx, dy = math.cos(a) * w2, math.sin(a) * w2
            # слегка наклонённые струи
            mb.quad2(('rain', 'blend_c'), (x - dx, y - dy, z), (x + dx, y + dy, z), (x + dx + 0.08, y + dy, z + h),
                     (x - dx + 0.08, y - dy, z + h), color=(0.82, 0.88, 0.97, 0.62))
        root = NodePath('rain')
        a = mb.build('r1', self.w.assets.apply_state)
        a.reparentTo(root)
        b = a.copyTo(root)
        b.setZ(self.rain_h)
        root.reparentTo(self.base.render)
        root.setLightOff(1)
        root.setFogOff(1)
        root.setDepthWrite(False)
        root.setBin('fixed', 40)
        root.hide()
        return root

    # ------------------------------------------------------------------
    def set_time(self, hour):
        self.hour = hour % 24.0
        self._apply(0.0)

    def advance(self, hours):
        self.hour += hours
        while self.hour >= 24.0:
            self.hour -= 24.0
            self.day += 1
        self._apply(0.0)

    def set_weather(self, name, instant=True):
        self.next_weather = name
        self.weather = name
        self.weather_t = 120.0 + random.random() * 120.0
        if instant:
            self.rain = 1.0 if name == 'rain' else 0.0
            self.clouds_k = 1.0 if name in ('rain', 'cloudy', 'fog') else 0.0
            self.fog_k = 1.0 if name == 'fog' else 0.0

    def clock_text(self):
        h = int(self.hour)
        m = int((self.hour - h) * 60.0)
        return '%02d:%02d' % (h, m)

    # ------------------------------------------------------------------
    def update(self, dt):
        self.hour += dt / 60.0 * self.time_scale
        if self.hour >= 24.0:
            self.hour -= 24.0
            self.day += 1
        # погода
        self.weather_t -= dt
        if self.weather_t <= 0.0:
            self.weather_t = 100.0 + random.random() * 160.0
            r = random.random()
            for name, p in WEATHERS:
                r -= p
                if r <= 0.0:
                    self.weather = name
                    break
        wth = self.weather
        k = min(1.0, dt * 0.07)
        self.rain += ((1.0 if wth == 'rain' else 0.0) - self.rain) * k
        self.clouds_k += ((1.0 if wth in ('rain', 'cloudy', 'fog') else 0.0) - self.clouds_k) * k
        self.fog_k += ((1.0 if wth == 'fog' else 0.0) - self.fog_k) * k
        self._apply(dt)

    def _apply(self, dt):
        h = self.hour
        k0 = KEYS[0]
        k1 = KEYS[-1]
        for i in range(len(KEYS) - 1):
            if KEYS[i][0] <= h <= KEYS[i + 1][0]:
                k0, k1 = KEYS[i], KEYS[i + 1]
                break
        t = (h - k0[0]) / max(1e-6, (k1[0] - k0[0]))
        zen = _mix(k0[1], k1[1], t)
        hor = _mix(k0[2], k1[2], t)
        amb = _mix(k0[3], k1[3], t)
        sun = _mix(k0[4], k1[4], t)
        # ночь: 0 днём, 1 ночью
        if h < 4.8 or h > 20.8:
            night = 1.0
        elif h < 6.4:
            night = 1.0 - (h - 4.8) / 1.6
        elif h > 19.2:
            night = (h - 19.2) / 1.6
        else:
            night = 0.0
        self.night = night
        # погода: пасмурно — серее и темнее
        ck = self.clouds_k
        if ck > 0.01:
            lum = (hor[0] + hor[1] + hor[2]) / 3.0
            grey = (lum * 0.78, lum * 0.80, lum * 0.84)
            zen = _mix(zen, (grey[0] * 0.8, grey[1] * 0.8, grey[2] * 0.82), ck * 0.85)
            hor = _mix(hor, grey, ck * 0.85)
            amb = _mix(amb, (amb[0] * 0.95, amb[1] * 0.96, amb[2] * 1.0), ck)
            sun = _mix(sun, (sun[0] * 0.35, sun[1] * 0.36, sun[2] * 0.4), ck)
        self.fog_color = hor
        base = self.base
        base.setBackgroundColor(hor[0], hor[1], hor[2])
        self.dome.setColorScale(zen[0], zen[1], zen[2], 1.0)
        self.amb.setColor(LColor(amb[0], amb[1], amb[2], 1))
        self.sun.setColor(LColor(sun[0], sun[1], sun[2], 1))
        self.fill.setColor(LColor(sun[0] * 0.38, sun[1] * 0.38, sun[2] * 0.42, 1))
        self.fog.setColor(hor[0], hor[1], hor[2])
        fs, fe = self.fog_start, self.far
        fk = self.fog_k
        rk = self.rain
        fs = fs * (1.0 - 0.9 * fk) * (1.0 - 0.45 * rk)
        fe = fe * (1.0 - 0.72 * fk) * (1.0 - 0.3 * rk)
        self.fog.setLinearRange(fs, fe)
        # положение солнца и луны
        day_t = (h - 6.0) / 14.0                   # 0 на восходе (6:00), 1 на закате (20:00)
        if 0.0 <= day_t <= 1.0:
            az = math.pi * day_t                   # восход на востоке (+X), закат на западе
            el = math.sin(day_t * math.pi) * 1.05
            sx, sy, sz = math.cos(az) * math.cos(el), -0.35 * math.cos(el), math.sin(el)
            self.sun_card.show()
            self.sun_card.setPos(sx * 92, sy * 92, sz * 92 + 2)
            a = clamp(math.sin(day_t * math.pi) * 3.0, 0.0, 1.0) * (1.0 - ck * 0.9)
            self.sun_card.setColorScale(1.0, 0.9 + 0.1 * a, 0.7 + 0.3 * a, a)
            lx, ly, lz = sx, sy, max(0.25, sz)
        else:
            self.sun_card.hide()
            nt = ((h - 20.0) % 24.0) / 10.0
            az = math.pi * nt
            el = math.sin(clamp(nt, 0, 1) * math.pi) * 0.9
            sx, sy, sz = math.cos(az) * math.cos(el), 0.3 * math.cos(el), math.sin(el)
            lx, ly, lz = sx, sy, max(0.3, sz)
        if night > 0.05:
            nt = ((h - 20.0) % 24.0) / 10.0
            az = math.pi * nt
            el = math.sin(clamp(nt, 0, 1) * math.pi) * 0.9
            mx, my, mz = math.cos(az) * math.cos(el), 0.3 * math.cos(el), math.sin(el)
            self.moon_card.show()
            self.moon_card.setPos(mx * 92, my * 92, mz * 92 + 2)
            self.moon_card.setColorScale(1, 1, 1, night * (1.0 - ck * 0.8))
            self.stars.show()
            self.stars.setColorScale(1, 1, 1, night * (1.0 - ck))
        else:
            self.moon_card.hide()
            self.stars.hide()
        # направление света: lookAt от источника к началу координат
        self.sun_np.setPos(lx * 10, ly * 10, lz * 10)
        self.sun_np.lookAt(0, 0, 0)
        self.fill_np.setPos(-lx * 10, -ly * 10, 6)
        self.fill_np.lookAt(0, 0, 0)
        # облака
        cl = (0.42 + 0.58 * (1.0 - night)) * (1.0 - 0.3 * ck)
        ccol = _mix((cl, cl, cl), hor, 0.25)
        for c in self.clouds:
            c[1] += dt * 0.004 * c[3]
            az, el = c[1], c[2]
            c[0].setPos(math.cos(az) * math.cos(el) * 95, math.sin(az) * math.cos(el) * 95, math.sin(el) * 95)
            c[0].setColorScale(ccol[0], ccol[1], ccol[2], (0.85 + 0.15 * ck) * (1.0 - 0.45 * night))
        # ночные огни города
        cmesh = self.w.citymesh
        if night > 0.3 and not self.night_on:
            self.night_on = True
            cmesh.night_root.show()
        elif night < 0.25 and self.night_on:
            self.night_on = False
            cmesh.night_root.hide()
        if self.night_on:
            g = clamp((night - 0.25) / 0.4, 0.0, 1.0)
            cmesh.night_root.setColorScale(g, g, g, 1.0)
        lights = night > 0.4 or rk > 0.5 or fk > 0.5
        if lights != self.lights_on:
            self.lights_on = lights
            for v in self.w.vehicles:
                if not v.dead and v.mode != 0:
                    v.set_lights(lights)

    def follow(self, cam, dt):
        """Небо и дождь следуют за камерой."""
        self.root.setPos(cam.x, cam.y, cam.z - 4.0)
        if self.rain > 0.03:
            self.rain_np.show()
            self.rain_z = (self.rain_z + dt * 22.0) % self.rain_h
            self.rain_np.setPos(cam.x, cam.y, max(0.0, cam.z - 6.0) - self.rain_z)
            self.rain_np.setAlphaScale(min(1.0, self.rain * 1.3))
            if random.random() < self.rain * 0.6:
                a = random.uniform(0, 6.283)
                r = random.uniform(2, 14)
                x, y = cam.x + math.cos(a) * r, cam.y + math.sin(a) * r
                gz = self.w.city.ground_z(x, y)
                if gz > -0.5:
                    self.w.fx.spawn('spark', x, y, gz + 0.06, 0, 0, 0.6, 0.18, 0.1, 0.3, (0.8, 0.9, 1.0), 0.5)
        else:
            self.rain_np.hide()
