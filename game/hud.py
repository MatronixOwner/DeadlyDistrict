# -*- coding: utf-8 -*-
"""Экран игры: мини-карта с полосками здоровья и брони, деньги и розыск, оружие, сообщения, телефон.

Расположение — как в играх серии после 2008 года: карта слева внизу, всё остальное по углам, середина
экрана свободна.  Облик (шрифты, цвета, плашки) описан в ui.py.
"""
import math
import re

from panda3d.core import (CardMaker, TextNode, TransparencyAttrib, TextureStage, TransformState, LVecBase2,
                          PandaNode, ClockObject, TextProperties, TextPropertiesManager, LColor)

from . import ui
from .ui import INK, PAPER, MUTE, ACCENT, CASH, HEALTH, ARMOR, DANGER, GOLD, WHITE, rgba
from .mapinfo import MAP_CX, MAP_CY, MAP_HALF
from .mathutil import clamp, DEG

M = 0.07                    # поля от краёв экрана
MAP_W = 0.52                # мини-карта: ширина и высота
MAP_H = 0.34
MAP_LOW = 0.36              # игрок стоит не в центре карты, а ниже: впереди видно дальше
BAR_H = 0.022
SPEAKER = re.compile(u'^([^:\\n]{1,26}):\\s+(.+)$', re.S)


class Blip(object):
    __slots__ = ('x', 'y', 'obj', 'tex', 'color', 'scale', 'edge', 'np', 'visible', 'removed', 'map_np', 'rng')


class Hud(object):

    def __init__(self, world):
        self.w = world
        base = world.base
        self.base = base
        self.assets = world.assets
        kit = self.kit = ui.Kit(world.assets)
        self.root = base.aspect2d.attachNewNode(PandaNode('hud'), sort=0)
        self.msg = base.aspect2d.attachNewNode(PandaNode('hud_msg'), sort=10)
        self.msg_br = self.msg.attachNewNode('br')
        self.msg_tl = self.msg.attachNewNode('tl')
        self.f_txt = kit.text                      # этим шрифтом пишут подсказки и другие модули
        self.tr = self.root.attachNewNode('tr')
        self.bl = self.root.attachNewNode('bl')
        self.br = self.root.attachNewNode('br')
        self.tl = self.root.attachNewNode('tl')
        self.aspect = 0.0
        tp = TextProperties()
        tp.setTextColor(LColor(*ACCENT))
        TextPropertiesManager.getGlobalPtr().setProperties('spk', tp)

        # --- правый верхний угол: розыск, деньги, оружие
        self.stars = []
        for i in range(6):
            x = -M - 0.03 - i * 0.068
            on = kit.image(self.tr, 'hud_star', x, -M - 0.03, 0.034)
            off = kit.image(self.tr, 'hud_star_off', x, -M - 0.03, 0.034)
            on.hide()
            off.hide()
            self.stars.append((on, off))
        self.money_text = kit.label(self.tr, '', -M, -M - 0.15, 0.066, CASH, kit.bold, 'r')
        self.delta_text = kit.label(self.tr, '', -M, -M - 0.205, 0.044, CASH, kit.bold, 'r')
        self.delta_t = 0.0
        self.weapon_icon = kit.image(self.tr, 'w_fist', -M - 0.105, -M - 0.295, 0.105, 0.0525)
        self.ammo_text = kit.label(self.tr, '', -M - 0.235, -M - 0.312, 0.05, PAPER, kit.bold, 'r')
        self.weapon_name = kit.label(self.tr, '', -M, -M - 0.385, 0.036, MUTE, kit.text, 'r')
        self.weapon_t = 0.0
        self.timer_text = kit.label(self.tr, '', -M, -M - 0.48, 0.062, PAPER, kit.bold, 'r')
        self.counter_text = kit.label(self.tr, '', -M, -M - 0.55, 0.046, PAPER, kit.text, 'r')

        # --- мини-карта и полоски под ней
        self.radar = self.bl.attachNewNode('radar')
        self.radar.setPos(M, 0, M + BAR_H + 0.012)
        kit.card(self.radar, -0.008, MAP_W + 0.008, -BAR_H - 0.020, MAP_H + 0.008, INK, 0.78)
        cm = CardMaker('map')
        cm.setFrame(0.0, MAP_W, 0.0, MAP_H)
        k = MAP_H / MAP_W * 2.0
        cm.setUvRange((-1.0, -k * MAP_LOW), (1.0, k * (1.0 - MAP_LOW)))
        self.map_card = self.radar.attachNewNode(cm.generate())
        self.map_tex = world.assets.tex('map', clamp=True, smooth=True)
        self.map_card.setTexture(self.map_tex)
        self.map_card.setColorScale(0.92, 0.92, 0.92, 1.0)
        self.origin = self.radar.attachNewNode('origin')            # точка игрока на карте
        self.origin.setPos(MAP_W * 0.5, 0, MAP_H * MAP_LOW)
        self.blip_root = self.origin.attachNewNode('blips')
        self.north = kit.image(self.origin, 'blip_north', 0, 0, 0.022)
        self.me = kit.image(self.origin, 'blip_player', 0, 0, 0.027)
        self.blips = []
        self.radar_range = 110.0
        # под картой три полоски: здоровье, броня и запас закиси азота (если на машине стоит баллон)
        bw = MAP_W
        self.hp_bar = kit.bar(self.radar, 0.0, -BAR_H - 0.008, bw * 0.50 - 0.004, BAR_H, HEALTH)
        self.ar_bar = kit.bar(self.radar, bw * 0.50 + 0.004, -BAR_H - 0.008, bw * 0.25 - 0.008, BAR_H, ARMOR)
        self.nx_bar = kit.bar(self.radar, bw * 0.75 + 0.004, -BAR_H - 0.008, bw * 0.25 - 0.004, BAR_H, ACCENT)
        self.nx_bar.setScale(0.0001, 1, 1)
        self.hp_frac = -1.0
        self.ar_frac = -1.0
        self.nx_frac = 0.0
        self.clock_text = kit.label(self.radar, '', 0.0, MAP_H + 0.03, 0.042, PAPER, kit.bold, 'l')
        self.day_text = kit.label(self.radar, '', MAP_W, MAP_H + 0.03, 0.034, MUTE, kit.text, 'r')
        # полоска задания (например, состояние чужой машины): над картой, видна только когда нужна
        self.task_root = self.radar.attachNewNode('task')
        self.task_root.setPos(0, 0, MAP_H + 0.085)
        self.task_label = kit.label(self.task_root, '', 0.0, 0.034, 0.034, PAPER, kit.text, 'l')
        self.task_bar = kit.bar(self.task_root, 0.0, 0.0, MAP_W, BAR_H * 0.8, ACCENT)
        self.task_root.hide()

        # --- правый нижний угол: улица и район, машина
        self.br_text = self.br.attachNewNode('text')                # сдвигается, когда поднят телефон
        self.street_text = kit.label(self.br_text, '', -M, M + 0.075, 0.040, MUTE, kit.text, 'r')
        self.zone_text = kit.label(self.br_text, '', -M, M, 0.066, PAPER, kit.head, 'r')
        self.veh_text = kit.label(self.br_text, '', -M, M + 0.15, 0.056, ACCENT, kit.head, 'r')

        # --- сообщения
        # субтитры: нижняя строка всегда на одной высоте (над чёрной полосой сценок), длинные растут вверх
        self.sub_scale = 0.054
        self.sub_base = -0.735
        self.sub_text = kit.label(self.msg, '', 0, self.sub_base, self.sub_scale, PAPER, kit.bold, 'c', wrap=40)
        self.sub_plain = ''
        self.help_text = kit.label(self.msg_tl, '', M + 0.03, -M - 0.065, 0.044, PAPER, kit.text, 'l', wrap=20,
                                   shadow=False)
        tn = self.help_text.textNode
        tn.setCardColor(LColor(*rgba(INK, 0.80)))
        tn.setCardAsMargin(0.55, 0.55, 0.42, 0.34)
        tn.setCardDecal(True)
        self.help_text.hide()
        # большое сообщение: полоса через экран, заголовок и строка под ним
        self.band = kit.card(self.msg, -5, 5, -0.02, 0.36, INK, 0.62)
        self.band.hide()
        self.big_text = kit.label(self.msg, '', 0, 0.165, 0.15, ACCENT, kit.title, 'c', shadow=False)
        self.big_sub = kit.label(self.msg, '', 0, 0.045, 0.056, PAPER, kit.bold, 'c', shadow=False)
        self.title_root = self.msg_br.attachNewNode('title')
        self.title_text = kit.label(self.title_root, '', -M, M + 0.27, 0.15, ACCENT, kit.script, 'r')
        self.radio_text = kit.label(self.root, '', 0, 0.87, 0.058, ACCENT, kit.head, 'c')
        self.radio_sub = kit.label(self.root, '', 0, 0.815, 0.038, PAPER, kit.text, 'c')
        self.fps_text = kit.label(self.tl, '', M, -M - 0.01, 0.036, MUTE, kit.text, 'l')
        self.cross = kit.image(self.root, 'crosshair', 0, 0, 0.034)
        self.cross.hide()

        # --- оптика: круглое окно и чёрные поля по бокам
        self.scope = base.aspect2d.attachNewNode(PandaNode('scope'), sort=3)
        kit.image(self.scope, 'scope', 0, 0, 1.0)
        kit.card(self.scope, -6.0, -0.995, -1.0, 1.0, (0, 0, 0, 1))
        kit.card(self.scope, 0.995, 6.0, -1.0, 1.0, (0, 0, 0, 1))
        self.scope.hide()
        self.scoped = False

        # --- телефон: выезжает снизу справа
        self.phone = self.msg_br.attachNewNode('phone')
        kit.image(self.phone, 'ui_phone', 0, 0, 0.165, 0.33, smooth=True)
        self.phone_disc = kit.image(self.phone, 'ui_disc', 0, 0.115, 0.075)
        self.phone_init = kit.label(self.phone, '', 0, 0.083, 0.095, PAPER, kit.title, 'c', shadow=False)
        self.phone_name = kit.label(self.phone, '', 0, -0.035, 0.046, PAPER, kit.bold, 'c', shadow=False)
        self.phone_state = kit.label(self.phone, '', 0, -0.092, 0.032, MUTE, kit.text, 'c', shadow=False)
        self.phone_hint = kit.label(self.phone, '', 0, -0.215, 0.030, ACCENT, kit.bold, 'c', shadow=False)
        self.phone.setPos(-M - 0.165, 0, -0.5)
        self.phone.hide()
        self.phone_on = False
        self.phone_y = -0.5
        self.phone_t = 0.0
        self.phone_mode = None

        # --- затемнение и вспышка урона
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
        self.dmg_np.setTexture(world.assets.tex('vignette', clamp=True, smooth=True))
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
        self.money_seen = None
        self.zone_name = None
        self.street_name = None
        self.zone_check = 0.0
        self.t = 0.0
        self.fps_t = 0.0
        self.visible = True
        self.weapon_changed(False)
        self.layout(force=True)

    # ------------------------------------------------------------------
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
        self.msg_tl.setPos(-asp, 0, 1)
        self.dmg_np.setScale(asp, 1, 1)

    def stash(self, on):
        """Полностью убрать интерфейс с экрана (пока открыто меню)."""
        # unstash() без аргумента сбрасывает порядок отрисовки в 0 — тогда надписи
        # оказываются ПОД затемнением и чёрными полосами, поэтому порядок задаём явно
        for n, sort in ((self.root, 0), (self.msg, 10), (self.scope, 3)):
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
            self.scope.hide()
            self.scoped = False

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
        self.sub_plain = ''
        self.sub_text.setText('')

    def help(self, text, dur=6.0):
        self.help_text.setText(text)
        self.help_text.show()
        self.help_t = dur

    def big(self, text, color=GOLD, dur=4.0, sub=''):
        self.big_text.setText(text.upper())
        self.big_text.setFg(color)
        self.big_sub.setText(sub)
        self.big_t = dur

    def mission_title(self, text):
        if not text:
            self.title_text.setText('')
            self.title_t = 0.0
            return
        self.title_text.setText(text)
        self.title_t = 4.5

    def vehicle_name(self, text):
        self.veh_text.setText(text.upper())
        self.veh_t = 3.0

    def radio_changed(self, station, title=None):
        """Показать название станции и, если есть, песни."""
        self.radio_text.setText(station.upper())
        self.radio_sub.setText(title or '')
        self.radio_t = 4.5 if title else 2.5

    def set_timer(self, text):
        self._set(self.timer_text, 'timer', text or '')

    def set_counter(self, text):
        self._set(self.counter_text, 'counter', text or '')

    def set_task_bar(self, label=None, frac=1.0, color=None):
        """Полоска задания над картой: label=None убирает её."""
        if label is None:
            self.task_root.hide()
            return
        self.task_root.show()
        self._set(self.task_label, 'task', label)
        self.task_bar.setScale(clamp(frac, 0.0, 1.0), 1, 1)
        if color is not None:
            self.task_bar.setColorScale(color[0] / ACCENT[0], color[1] / ACCENT[1], color[2] / ACCENT[2], 1.0)
        else:
            self.task_bar.clearColorScale()

    def weapon_changed(self, announce=True):
        pl = self.w.player
        self.weapon_icon.setTexture(self.assets.tex(pl.weapon.icon, clamp=True, smooth=True), 1)
        if announce:
            self.weapon_name.setText(pl.weapon.name)
            self.weapon_t = 2.2

    def money_changed(self, delta):
        if not delta:
            return
        self.delta_text.setText(('+' if delta > 0 else u'\u2212') + ui.money(abs(delta)))
        self.delta_text.setFg(CASH if delta > 0 else DANGER)
        self.delta_t = 2.6

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
    # телефон
    # ------------------------------------------------------------------
    def phone_show(self, name, color, mode, hint=''):
        """mode: 'ring' — входящий вызов, 'talk' — разговор."""
        self.phone_on = True
        self.phone_mode = mode
        self.phone_t = 0.0
        self.phone.show()
        self.phone_name.setText(name)
        self.phone_init.setText(name[:1].upper())
        self.phone_disc.setColorScale(color[0], color[1], color[2], 1.0)
        self.phone_hint.setText(hint)
        self._phone_state()

    def phone_hide(self):
        self.phone_on = False

    def _phone_state(self):
        if self.phone_mode == 'ring':
            self.phone_state.setText(u'входящий вызов' + '.' * (int(self.phone_t * 2.5) % 4))
        else:
            self.phone_state.setText('%d:%02d' % (int(self.phone_t) // 60, int(self.phone_t) % 60))

    # ------------------------------------------------------------------
    # метки на карте
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
        b.np = self.kit.image(self.blip_root, tex, 0, 0, 0.023 * scale)
        if tuple(color) != tuple(WHITE):
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
        self._phone(dt)
        if not self.visible:
            return
        # деньги
        if self.money_seen is None:
            self.money_seen = self.money_show = pl.money
        if self.money_show != pl.money:
            diff = pl.money - self.money_show
            step = max(1, int(abs(diff) * min(1.0, dt * 6.0)))
            self.money_show += step if diff > 0 else -step
            if abs(pl.money - self.money_show) < 2:
                self.money_show = pl.money
        self._set(self.money_text, 'money', ui.money(self.money_show))
        if self.delta_t > 0.0:
            self.delta_t -= dt
            self.delta_text.show()
            self.delta_text.setAlphaScale(clamp(self.delta_t / 0.5, 0.0, 1.0))
        else:
            self.delta_text.hide()
        # здоровье и броня
        hp = clamp(p.health / max(1.0, p.max_health), 0.0, 1.0)
        if abs(hp - self.hp_frac) > 0.004:
            self.hp_frac = hp
            self.hp_bar.setScale(max(hp, 0.0001), 1, 1)
        if hp < 0.25:
            # мало здоровья: полоска краснеет и мигает
            k = 0.55 + 0.45 * math.sin(self.t * 9.0)
            self.hp_bar.setColorScale(DANGER[0] / HEALTH[0], DANGER[1] / HEALTH[1] * k, DANGER[2] / HEALTH[2] * k, 1.0)
        else:
            self.hp_bar.clearColorScale()
        ar = clamp(p.armor / 100.0, 0.0, 1.0)
        if abs(ar - self.ar_frac) > 0.004:
            self.ar_frac = ar
            self.ar_bar.setScale(max(ar, 0.0001), 1, 1)
        veh = pl.vehicle
        nx = veh.nitro_k if (veh is not None and veh.nitro) else 0.0
        if abs(nx - self.nx_frac) > 0.004:
            self.nx_frac = nx
            self.nx_bar.setScale(max(nx, 0.0001), 1, 1)
        # часы
        self._set(self.clock_text, 'clock', w.sky.clock_text())
        self._set(self.day_text, 'day', u'день %d' % w.sky.day)
        # оружие
        am = pl.ammo.get(pl.weapon_id, 0)
        self._set(self.ammo_text, 'ammo', '' if am < 0 else str(am))
        if self.weapon_t > 0.0:
            self.weapon_t -= dt
            self.weapon_name.show()
            self.weapon_name.setAlphaScale(clamp(self.weapon_t / 0.5, 0.0, 1.0))
        else:
            self.weapon_name.hide()
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
        # прицел и оптика
        scoped = bool(w.cam.scope) and pl.controls and not pl.freeze
        if scoped != self.scoped:
            self.scoped = scoped
            if scoped:
                self.scope.show()
            else:
                self.scope.hide()
        if pl.state == 'foot' and pl.weapon.kind != 'melee' and pl.controls and not pl.freeze and not scoped and \
                not pl.indoors:
            self.cross.show()
        else:
            self.cross.hide()
        self._radar(dt)
        # улица и район
        self.zone_check -= dt
        if self.zone_check <= 0.0:
            self.zone_check = 0.7
            px, py = pl.pos()
            name = w.city.zone_name(px, py)
            street = w.city.street_name(px, py) if hasattr(w.city, 'street_name') else None
            if (name and name != self.zone_name) or (street and street != self.street_name and pl.vehicle is not None):
                self.zone_text.setText((name or self.zone_name or '').upper())
                self.zone_t = 4.0
            if name:
                self.zone_name = name
            self.street_name = street
            self.street_text.setText(street or '')
        if w.settings.get('show_fps'):
            self.fps_t -= dt
            if self.fps_t <= 0.0:
                self.fps_t = 0.5
                self._cache['fps'] = None
                self.fps_text.setText('%d FPS' % int(ClockObject.getGlobalClock().getAverageFrameRate() + 0.5))
        elif self._cache.get('fps') != '':
            self._cache['fps'] = ''
            self.fps_text.setText('')

    def _fade_text(self, node, t):
        if t <= 0.0:
            node.hide()
            return
        node.show()
        node.setAlphaScale(clamp(t / 0.6, 0.0, 1.0))

    def _messages(self, dt):
        if self.sub_t > 0.0:
            self.sub_t -= dt
            if self.sub_t <= 0.0 and not self.sub_queue:
                self.sub_plain = ''
                self.sub_text.setText('')
        if self.sub_t <= 0.0 and self.sub_queue:
            text, dur = self.sub_queue.pop(0)
            self.sub_plain = text
            m = SPEAKER.match(text)
            # имя говорящего — цветом акцента
            self.sub_text.setText(u'\1spk\1%s:\2 %s' % (m.group(1), m.group(2)) if m else text)
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
                    self._fade_text(self.band, t)
                elif node is self.zone_text:
                    self._fade_text(self.street_text, t)
                elif node is self.radio_text:
                    self._fade_text(self.radio_sub, t)

    def _phone(self, dt):
        want = 0.33 + M if self.phone_on else -0.5
        if abs(self.phone_y - want) > 0.001:
            self.phone_y += (want - self.phone_y) * min(1.0, dt * 9.0)
            self.phone.setZ(self.phone_y)
        elif not self.phone_on and not self.phone.isHidden():
            self.phone.hide()
        # телефон занимает правый нижний угол: надписи оттуда отодвигаются
        shift = -0.40 * clamp((self.phone_y + 0.35) / 0.6, 0.0, 1.0)
        self.br_text.setX(shift)
        self.title_root.setX(shift)
        if self.phone_on:
            self.phone_t += dt
            self._phone_state()
            if self.phone_mode == 'ring':
                self.phone.setR(math.sin(self.t * 38.0) * 1.4 if int(self.phone_t * 1.4) % 2 == 0 else 0.0)
            else:
                self.phone.setR(0.0)

    def _radar(self, dt):
        w = self.w
        pl = w.player
        cam = w.cam
        px, py = w.map_pos()
        sp = pl.speed()
        want = 105.0 + min(70.0, sp * 3.2)
        self.radar_range += (want - self.radar_range) * min(1.0, dt * 1.5)
        R = self.radar_range                       # сколько метров мира умещается в полуширине карты
        yaw = cam.yaw
        u = (px - (MAP_CX - MAP_HALF)) / (2.0 * MAP_HALF)
        v = (py - (MAP_CY - MAP_HALF)) / (2.0 * MAP_HALF)
        s = R / (2.0 * MAP_HALF)
        ts = TransformState.makePosRotateScale2d(LVecBase2(u, v), (yaw * DEG) - 90.0, LVecBase2(s, s))
        self.map_card.setTexTransform(TextureStage.getDefault(), ts)
        fx, fy = math.cos(yaw), math.sin(yaw)
        rx, ry = fy, -fx
        k = MAP_W * 0.5 / R
        x1 = MAP_W * 0.5 - 0.018
        z0 = -MAP_H * MAP_LOW + 0.018
        z1 = MAP_H * (1.0 - MAP_LOW) - 0.018
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
            if lx < -x1 or lx > x1 or lz < z0 or lz > z1:
                if not b.edge:
                    b.np.hide()
                    continue
                # метка за краем карты прижимается к рамке в своём направлении
                t = 1.0
                if abs(lx) > x1:
                    t = min(t, x1 / abs(lx))
                if lz > z1:
                    t = min(t, z1 / lz)
                elif lz < z0:
                    t = min(t, z0 / lz)
                lx, lz = lx * t, lz * t
            b.np.show()
            b.np.setPos(lx, 0, lz)
        # стрелка игрока и север
        heading = pl.vehicle.yaw if pl.vehicle is not None else pl.ped.yaw
        self.me.setR(-(heading - yaw) * DEG)
        nx, nz = ry, fy                             # куда на карте смотрит север
        t = min(x1 / max(abs(nx), 1e-6), (z1 if nz > 0 else -z0) / max(abs(nz), 1e-6))
        self.north.setPos(nx * t, 0, nz * t)
