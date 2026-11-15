# -*- coding: utf-8 -*-
"""Интерфейс: радар, здоровье, деньги, звёзды розыска, сообщения."""
import math

from panda3d.core import (NodePath, CardMaker, TextNode, TransparencyAttrib, TextureStage, TransformState,
                          LVecBase2, SamplerState, PandaNode, ClockObject)
from direct.gui.OnscreenText import OnscreenText

from .meshbuilder import MeshBuilder
from .mapinfo import MAP_CX, MAP_CY, MAP_HALF
from .mathutil import clamp, DEG
from .defs import WEAPONS

RADAR_R = 0.215
GOLD = (1.0, 0.82, 0.2, 1.0)
WHITE = (1, 1, 1, 1)


class Blip(object):
    __slots__ = ('x', 'y', 'obj', 'tex', 'color', 'scale', 'edge', 'np', 'visible', 'removed', 'map_np', 'rng')


class Hud(object):

    def __init__(self, world):
        self.w = world
        base = world.base
        self.base = base
        self.assets = world.assets
        a = self.assets
        self.root = base.aspect2d.attachNewNode(PandaNode('hud'), sort=0)
        self.msg = base.aspect2d.attachNewNode(PandaNode('hud_msg'), sort=10)
        self.msg_br = self.msg.attachNewNode('br')
        self.f_num = a.font('RussoOne.ttf', 64, outline=2.2)
        self.f_txt = a.font('RussoOne.ttf', 56, outline=2.0)
        self.f_big = a.font('DelaGothicOne.ttf', 96, outline=3.0)
        self.tr = self.root.attachNewNode('tr')
        self.bl = self.root.attachNewNode('bl')
        self.br = self.root.attachNewNode('br')
        self.tl = self.root.attachNewNode('tl')
        self.aspect = 0.0
        # --- правый верхний угол
        self.weapon_icon = self._img('w_fist', self.tr, -0.17, -0.15, 0.115)
        self.ammo_text = self._text(self.tr, -0.17, -0.285, 0.05, WHITE, TextNode.ACenter)
        self.clock_text = self._text(self.tr, -0.32, -0.125, 0.07, WHITE, TextNode.ARight)
        self.money_text = self._text(self.tr, -0.05, -0.375, 0.075, (0.42, 0.85, 0.36, 1), TextNode.ARight)
        self.heart = self._img('hud_heart', self.tr, -0.60, -0.185, 0.035)
        self.health_text = self._text(self.tr, -0.32, -0.21, 0.07, (0.95, 0.35, 0.3, 1), TextNode.ARight)
        self.armor_img = self._img('hud_armor', self.tr, -0.60, -0.27, 0.035)
        self.armor_text = self._text(self.tr, -0.32, -0.295, 0.07, (0.5, 0.7, 0.98, 1), TextNode.ARight)
        self.stars = []
        for i in range(6):
            on = self._img('hud_star', self.tr, -0.085 - i * 0.082, -0.455, 0.038)
            off = self._img('hud_star_off', self.tr, -0.085 - i * 0.082, -0.455, 0.038)
            on.hide()
            off.hide()
            self.stars.append((on, off))
        self.timer_text = self._text(self.tr, -0.05, -0.58, 0.07, (0.95, 0.9, 0.6, 1), TextNode.ARight)
        self.counter_text = self._text(self.tr, -0.05, -0.67, 0.06, (0.8, 0.9, 1.0, 1), TextNode.ARight)
        # --- радар
        self.radar = self.bl.attachNewNode('radar')
        self.radar.setPos(RADAR_R + 0.06, 0, RADAR_R + 0.06)
        mb = MeshBuilder()
        n = 36
        for i in range(n):
            a0, a1 = i * 2 * math.pi / n, (i + 1) * 2 * math.pi / n
            c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)
            mb.tri('m', (0, 0, 0), (c0 * RADAR_R, 0, s0 * RADAR_R), (c1 * RADAR_R, 0, s1 * RADAR_R),
                   (0, 0), (c0, s0), (c1, s1))
        self.map_disc = mb.build('disc')
        self.map_disc.reparentTo(self.radar)
        self.map_disc.setTwoSided(True)
        self.map_tex = a.tex('map', clamp=True, smooth=True)
        self.map_disc.setTexture(self.map_tex)
        self.map_disc.setColorScale(1, 1, 1, 0.92)
        self.map_disc.setTransparency(TransparencyAttrib.MAlpha)
        self.blip_root = self.radar.attachNewNode('blips')
        ring = self._img('radar_ring', self.radar, 0, 0, RADAR_R * 1.09)
        self.north = self._img('blip_north', self.radar, 0, 0, 0.026)
        self.me = self._img('blip_player', self.radar, 0, 0, 0.03)
        self.blips = []
        self.radar_range = 110.0
        # --- сообщения
        # субтитры: нижняя строка всегда на одной высоте (над чёрной полосой сценок),
        # длинные реплики растут вверх
        self.sub_scale = 0.056
        self.sub_base = -0.735
        self.sub_text = OnscreenText(text='', parent=self.msg, pos=(0, self.sub_base), scale=self.sub_scale, fg=WHITE,
                                     font=self.f_txt, align=TextNode.ACenter, wordwrap=40, mayChange=True)
        self.help_text = OnscreenText(text='', parent=self.tl, pos=(0.06, -0.12), scale=0.052, fg=WHITE,
                                      font=self.f_txt, align=TextNode.ALeft, wordwrap=17, mayChange=True,
                                      bg=(0, 0, 0, 0.62))
        self.help_text.hide()
        self.big_text = OnscreenText(text='', parent=self.msg, pos=(0, 0.16), scale=0.17, fg=GOLD, font=self.f_big,
                                     align=TextNode.ACenter, mayChange=True)
        self.big_sub = OnscreenText(text='', parent=self.msg, pos=(0, 0.0), scale=0.085, fg=WHITE, font=self.f_txt,
                                    align=TextNode.ACenter, mayChange=True)
        self.title_text = OnscreenText(text='', parent=self.msg_br, pos=(-0.06, 0.36), scale=0.115, fg=GOLD,
                                       font=self.f_big, align=TextNode.ARight, mayChange=True)
        self.zone_text = OnscreenText(text='', parent=self.br, pos=(-0.06, 0.07), scale=0.085,
                                      fg=(0.75, 0.88, 1.0, 1), font=self.f_big, align=TextNode.ARight, mayChange=True)
        self.veh_text = OnscreenText(text='', parent=self.br, pos=(-0.06, 0.2), scale=0.075,
                                     fg=(0.6, 0.9, 0.5, 1), font=self.f_big, align=TextNode.ARight, mayChange=True)
        self.radio_text = OnscreenText(text='', parent=self.root, pos=(0, 0.86), scale=0.07, fg=(1.0, 0.75, 0.3, 1),
                                       font=self.f_txt, align=TextNode.ACenter, mayChange=True)
        self.fps_text = self._text(self.tl, 0.04, -0.06, 0.045, (0.6, 1.0, 0.6, 1), TextNode.ALeft)
        self.cross = self._img('crosshair', self.root, 0, 0, 0.035)
        self.cross.hide()
        # затемнение и вспышка урона
        cm = CardMaker('fade')
        cm.setFrame(-5, 5, -1.5, 1.5)
        self.fade_np = base.aspect2d.attachNewNode(cm.generate(), sort=5)
        self.fade_np.setColor(0, 0, 0, 1)
        self.fade_np.setTransparency(TransparencyAttrib.MAlpha)
        self.fade_np.hide()
        self.fade_a = 0.0
        self.fade_target = 0.0
        self.fade_speed = 1.5
        cm = CardMaker('dmg')
        cm.setFrame(-1, 1, -1, 1)
        self.dmg_np = base.aspect2d.attachNewNode(cm.generate(), sort=4)
        self.dmg_np.setTexture(a.tex('vignette', clamp=True, smooth=True))
        self.dmg_np.setTransparency(TransparencyAttrib.MAlpha)
        self.dmg_np.setColor(0.8, 0.0, 0.0, 1)
        self.dmg_np.hide()
        self.dmg_a = 0.0
        self._cache = {}
        self.sub_queue = []
        self.sub_t = 0.0
        self.help_t = 0.0
        self.big_t = 0.0
        self.title_t = 0.0
        self.zone_t = 0.0
        self.veh_t = 0.0
        self.radio_t = 0.0
        self.money_show = 0
        self.zone_name = None
        self.zone_check = 0.0
        self.t = 0.0
        self.fps_t = 0.0
        self.visible = True
        self.weapon_changed()
        self.layout(force=True)

    # ------------------------------------------------------------------
    def _img(self, tex, parent, x, z, size, sy=None):
        cm = CardMaker(tex)
        cm.setFrame(-1, 1, -1, 1)
        np_ = parent.attachNewNode(cm.generate())
        np_.setTexture(self.assets.tex(tex, clamp=True))
        np_.setTransparency(TransparencyAttrib.MAlpha)
        np_.setPos(x, 0, z)
        np_.setScale(size, 1, sy if sy is not None else size)
        return np_

    def _text(self, parent, x, z, scale, fg, align):
        return OnscreenText(text='', parent=parent, pos=(x, z), scale=scale, fg=fg, font=self.f_num, align=align,
                            mayChange=True)

    def _set(self, node, key, text):
        if self._cache.get(key) != text:
            self._cache[key] = text
            node.setText(text)

    def layout(self, force=False):
        """Привязать углы интерфейса к краям окна (при любом соотношении сторон)."""
        asp = self.base.getAspectRatio()
        if not force and abs(asp - self.aspect) < 1e-3:
            return
        self.aspect = asp
        self.tr.setPos(asp, 0, 1)
        self.tl.setPos(-asp, 0, 1)
        self.bl.setPos(-asp, 0, -1)
        self.br.setPos(asp, 0, -1)
        self.msg_br.setPos(asp, 0, -1)
        self.dmg_np.setScale(asp, 1, 1)

    def stash(self, on):
        """Полностью убрать интерфейс с экрана (пока открыто меню)."""
        # unstash() без аргумента сбрасывает порядок отрисовки в 0 — тогда надписи
        # оказываются ПОД затемнением и чёрными полосами, поэтому порядок задаём явно
        for n, sort in ((self.root, 0), (self.msg, 10)):
            if on and not n.isStashed():
                n.stash()
            elif not on and n.isStashed():
                n.unstash(sort)

    def show(self, on):
        self.visible = on
        if on:
            self.root.show()
        else:
            self.root.hide()

    # ------------------------------------------------------------------
    # сообщения
    # ------------------------------------------------------------------
    def subtitle(self, text, dur=None, clear=False):
        if dur is None:
            dur = 1.6 + len(text) * 0.055
        if clear:
            self.sub_queue = []
            self.sub_t = 0.0
        self.sub_queue.append((text, dur))

    def clear_subtitles(self):
        self.sub_queue = []
        self.sub_t = 0.0
        self.sub_text.setText('')

    def help(self, text, dur=6.0):
        self.help_text.setText(text)
        self.help_text.show()
        self.help_t = dur

    def big(self, text, color=GOLD, dur=4.0, sub=''):
        self.big_text.setText(text)
        self.big_text.setFg(color)
        self.big_sub.setText(sub)
        self.big_t = dur

    def mission_title(self, text):
        if not text:
            self.title_text.setText('')
            self.title_t = 0.0
            return
        self.title_text.setText('«' + text + '»')
        self.title_t = 4.5

    def vehicle_name(self, text):
        self.veh_text.setText(text)
        self.veh_t = 3.0

    def radio_changed(self, text):
        self.radio_text.setText('♪ ' + text if False else text)
        self.radio_t = 2.5

    def set_timer(self, text):
        self._set(self.timer_text, 'timer', text or '')

    def set_counter(self, text):
        self._set(self.counter_text, 'counter', text or '')

    def weapon_changed(self):
        pl = self.w.player
        self.weapon_icon.setTexture(self.assets.tex(pl.weapon.icon, clamp=True), 1)

    def money_changed(self, delta):
        pass

    def wanted_changed(self, lv, old):
        pass

    def damage_flash(self, amount):
        self.dmg_a = min(0.85, self.dmg_a + 0.25 + amount * 0.012)

    def fade(self, target, speed=1.5, instant=False):
        self.fade_target = target
        self.fade_speed = speed
        if instant:
            self.fade_a = target
            self._apply_fade()

    def _apply_fade(self):
        if self.fade_a <= 0.003:
            self.fade_np.hide()
        else:
            self.fade_np.show()
            self.fade_np.setColor(0, 0, 0, self.fade_a)

    # ------------------------------------------------------------------
    # метки на радаре
    # ------------------------------------------------------------------
    def add_blip(self, tex, x=0.0, y=0.0, obj=None, color=WHITE, scale=1.0, edge=True, rng=None):
        b = Blip()
        b.x, b.y, b.obj = x, y, obj
        b.tex = tex
        b.color = color
        b.scale = scale
        b.edge = edge
        b.rng = rng
        b.visible = True
        b.removed = False
        b.map_np = None
        b.np = self._img(tex, self.blip_root, 0, 0, 0.024 * scale)
        b.np.setColorScale(*color)
        self.blips.append(b)
        return b

    def remove_blip(self, b):
        if b is None or b.removed:
            return
        b.removed = True
        b.np.removeNode()
        if b.map_np is not None:
            b.map_np.removeNode()
            b.map_np = None
        if b in self.blips:
            self.blips.remove(b)

    def blip_pos(self, b):
        o = b.obj
        if o is not None:
            v = getattr(o, 'vehicle', None)
            if v is not None:
                return v.x, v.y
            return o.x, o.y
        return b.x, b.y

    # ------------------------------------------------------------------
    def update(self, dt):
        w = self.w
        pl = w.player
        p = pl.ped
        self.t += dt
        self.layout()
        # затемнение работает даже при скрытом интерфейсе
        if self.fade_a != self.fade_target:
            d = self.fade_speed * dt
            if self.fade_a < self.fade_target:
                self.fade_a = min(self.fade_target, self.fade_a + d)
            else:
                self.fade_a = max(self.fade_target, self.fade_a - d)
            self._apply_fade()
        if self.dmg_a > 0.0:
            self.dmg_a = max(0.0, self.dmg_a - dt * 0.9)
            if self.dmg_a > 0.01:
                self.dmg_np.show()
                self.dmg_np.setAlphaScale(self.dmg_a)
            else:
                self.dmg_np.hide()
        self._messages(dt)
        if not self.visible:
            return
        # числа
        self._set(self.clock_text, 'clock', w.sky.clock_text())
        if self.money_show != pl.money:
            diff = pl.money - self.money_show
            step = max(1, int(abs(diff) * min(1.0, dt * 6.0)))
            self.money_show += step if diff > 0 else -step
            if abs(pl.money - self.money_show) < 2:
                self.money_show = pl.money
        self._set(self.money_text, 'money', '$%08d' % self.money_show)
        hp = int(math.ceil(max(0.0, p.health)))
        self._set(self.health_text, 'hp', '%03d' % hp)
        if hp < 25 and int(self.t * 4) % 2:
            self.health_text.hide()
        else:
            self.health_text.show()
        ar = int(p.armor)
        if ar > 0:
            self.armor_img.show()
            self.armor_text.show()
            self._set(self.armor_text, 'ar', '%03d' % ar)
        else:
            self.armor_img.hide()
            self.armor_text.hide()
        am = pl.ammo.get(pl.weapon_id, 0)
        self._set(self.ammo_text, 'ammo', '' if am < 0 else str(am))
        # звёзды розыска
        pol = w.police
        lv = pol.level
        blink = (pol.cool_t > 2.0 or pol.flash > 0.0) and int(self.t * 5) % 2 == 0
        for i, (on, off) in enumerate(self.stars):
            if lv <= 0:
                on.hide()
                off.hide()
            elif i < lv and not blink:
                on.show()
                off.hide()
            else:
                on.hide()
                off.show()
        # прицел
        if pl.state == 'foot' and pl.weapon.kind != 'melee' and pl.controls and not pl.freeze:
            self.cross.show()
        else:
            self.cross.hide()
        self._radar(dt)
        # название района
        self.zone_check -= dt
        if self.zone_check <= 0.0:
            self.zone_check = 1.0
            px, py = pl.pos()
            name = w.city.zone_name(px, py)
            if name and name != self.zone_name:
                self.zone_name = name
                self.zone_text.setText(name)
                self.zone_t = 4.0
        if w.settings.get('show_fps'):
            self.fps_t -= dt
            if self.fps_t <= 0.0:
                self.fps_t = 0.5
                self.fps_text.setText('%d FPS' % int(ClockObject.getGlobalClock().getAverageFrameRate() + 0.5))
        elif self._cache.get('fps') != '':
            self._cache['fps'] = ''
            self.fps_text.setText('')

    def _fade_text(self, node, t, dur_in=0.3):
        if t <= 0.0:
            node.hide()
            return
        node.show()
        a = clamp(t / 0.6, 0.0, 1.0)
        node.setAlphaScale(a)

    def _messages(self, dt):
        if self.sub_t > 0.0:
            self.sub_t -= dt
            if self.sub_t <= 0.0 and not self.sub_queue:
                self.sub_text.setText('')
        if self.sub_t <= 0.0 and self.sub_queue:
            text, dur = self.sub_queue.pop(0)
            self.sub_text.setText(text)
            tn = self.sub_text.textNode
            rows = max(1, tn.getNumRows())
            self.sub_text.setPos(0, self.sub_base + (rows - 1) * tn.getLineHeight() * self.sub_scale)
            self.sub_t = dur
        if self.help_t > 0.0:
            self.help_t -= dt
            if self.help_t <= 0.0:
                self.help_text.hide()
        for node, attr in ((self.big_text, 'big_t'), (self.title_text, 'title_t'), (self.zone_text, 'zone_t'),
                           (self.veh_text, 'veh_t'), (self.radio_text, 'radio_t')):
            t = getattr(self, attr)
            if t > -1.0:
                t -= dt
                setattr(self, attr, t)
                self._fade_text(node, t)
                if node is self.big_text:
                    self._fade_text(self.big_sub, t)

    def _radar(self, dt):
        w = self.w
        pl = w.player
        cam = w.cam
        px, py = pl.pos()
        sp = pl.speed()
        want = 105.0 + min(70.0, sp * 3.2)
        self.radar_range += (want - self.radar_range) * min(1.0, dt * 1.5)
        R = self.radar_range
        yaw = cam.yaw
        u = (px - (MAP_CX - MAP_HALF)) / (2.0 * MAP_HALF)
        v = (py - (MAP_CY - MAP_HALF)) / (2.0 * MAP_HALF)
        s = R / (2.0 * MAP_HALF)
        ts = TransformState.makePosRotateScale2d(LVecBase2(u, v), (yaw * DEG) - 90.0, LVecBase2(s, s))
        self.map_disc.setTexTransform(TextureStage.getDefault(), ts)
        fx, fy = math.cos(yaw), math.sin(yaw)
        rx, ry = fy, -fx
        k = RADAR_R / R
        for b in self.blips:
            if not b.visible:
                b.np.hide()
                continue
            o = b.obj
            if o is not None and getattr(o, 'removed', False):
                b.np.hide()
                continue
            bx, by = self.blip_pos(b)
            dx, dy = bx - px, by - py
            if b.rng is not None and (dx * dx + dy * dy) > b.rng * b.rng:
                b.np.hide()
                continue
            lx = (dx * rx + dy * ry) * k
            lz = (dx * fx + dy * fy) * k
            d = math.hypot(lx, lz)
            if d > RADAR_R * 0.97:
                if not b.edge:
                    b.np.hide()
                    continue
                lx, lz = lx / d * RADAR_R * 0.97, lz / d * RADAR_R * 0.97
            b.np.show()
            b.np.setPos(lx, 0, lz)
        # стрелка игрока и север
        heading = pl.vehicle.yaw if pl.vehicle is not None else pl.ped.yaw
        self.me.setR(-(heading - yaw) * DEG)
        nx, nz = (0 * rx + 1 * ry), (0 * fx + 1 * fy)
        self.north.setPos(nx * RADAR_R * 1.02, 0, nz * RADAR_R * 1.02)
