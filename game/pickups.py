# -*- coding: utf-8 -*-
"""Маркеры на земле, подбираемые предметы и стрелки над целями."""
import math
import random

from panda3d.core import NodePath, CardMaker, TransparencyAttrib, ColorBlendAttrib

from .meshbuilder import MeshBuilder
from .defs import WEAPONS, W_BAT, W_PISTOL, W_UZI, W_SHOTGUN, W_AK, W_ROCKET, W_GRENADE, W_MOLOTOV

PINK = (1.0, 0.35, 0.7)
YELLOW = (1.0, 0.85, 0.25)
BLUE = (0.35, 0.65, 1.0)
GREEN = (0.4, 1.0, 0.5)
RED = (1.0, 0.3, 0.25)

_marker_proto = [None]
_cards = {}


def _marker_template(assets):
    if _marker_proto[0] is None:
        mb = MeshBuilder()
        n = 14
        key = ('marker', 'add_c')
        for i in range(n):
            a0, a1 = i * 2 * math.pi / n, (i + 1) * 2 * math.pi / n
            p0 = (math.cos(a0), math.sin(a0), 0.0)
            p1 = (math.cos(a1), math.sin(a1), 0.0)
            p2 = (math.cos(a1), math.sin(a1), 1.0)
            p3 = (math.cos(a0), math.sin(a0), 1.0)
            mb.quad2(key, p0, p1, p2, p3, (0.0, 0.0, 1.0, 1.0), (1, 1, 1, 0.5))
        np_ = mb.build('marker', assets.apply_state)
        np_.setTwoSided(True)
        _marker_proto[0] = np_
    return _marker_proto[0]


def _card(assets, tex, add=False):
    key = (tex, add)
    c = _cards.get(key)
    if c is None:
        cm = CardMaker(tex)
        cm.setFrame(-0.5, 0.5, -0.5, 0.5)
        c = NodePath(cm.generate())
        c.setTexture(assets.tex(tex, clamp=True))
        if add:
            c.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha,
                                              ColorBlendAttrib.OOne))
            c.setDepthWrite(False)
            c.setBin('fixed', 24)
        else:
            c.setTransparency(TransparencyAttrib.MBinary)
        c.setLightOff(1)
        c.setTwoSided(True)
        _cards[key] = c
    return c


class Marker(object):
    """Светящийся столб-метка: сюда нужно прийти или приехать."""

    def __init__(self, world, x, y, r=1.6, color=PINK, h=1.7):
        self.w = world
        self.x, self.y, self.r = x, y, r
        self.z = max(0.0, world.city.ground_z(x, y))
        self.np = _marker_template(world.assets).copyTo(world.fx.root)
        self.np.setPos(x, y, self.z + 0.02)
        self.np.setScale(r, r, h)
        self.np.setColorScale(color[0], color[1], color[2], 1.0)
        self.h = h
        self.removed = False
        self.need_foot = None
        self.t = random.random() * 6.0

    def update(self, dt):
        self.t += dt
        k = 1.0 + 0.06 * math.sin(self.t * 4.0)
        self.np.setScale(self.r * k, self.r * k, self.h)
        self.np.setH(self.t * 40.0)

    def inside(self, x, y, extra=0.0):
        dx, dy = x - self.x, y - self.y
        r = self.r + extra
        return dx * dx + dy * dy <= r * r

    def player_inside(self, on_foot=None, extra=0.0):
        pl = self.w.player
        if on_foot is True and pl.vehicle is not None:
            return False
        if on_foot is False and pl.vehicle is None:
            return False
        if pl.state in ('dead', 'busted'):
            return False
        x, y = pl.pos()
        return self.inside(x, y, extra)

    def show(self, on=True):
        if on:
            self.np.show()
        else:
            self.np.hide()

    def remove(self):
        if not self.removed:
            self.removed = True
            self.np.removeNode()


class Arrow(object):
    """Стрелка, парящая над целью (человеком, машиной или точкой)."""

    def __init__(self, world, obj=None, x=0.0, y=0.0, z=2.4, color=YELLOW):
        self.w = world
        self.obj = obj
        self.x, self.y, self.z = x, y, z
        self.np = _card(world.assets, 'arrow').copyTo(world.fx.root)
        self.np.setBillboardAxis()
        self.np.setScale(0.9)
        self.np.setColorScale(color[0], color[1], color[2], 1.0)
        self.removed = False
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        o = self.obj
        if o is not None:
            if getattr(o, 'removed', False):
                self.np.hide()
                return
            v = getattr(o, 'vehicle', None)
            if v is not None:
                x, y, z = v.x, v.y, v.z + v.spec.H + 1.2
            elif hasattr(o, 'spec'):
                x, y, z = o.x, o.y, o.z + max(o.spec.H, o.spec.box[1] if o.spec.box else 0.0) + 1.2
            else:
                x, y, z = o.x, o.y, o.z + 2.5
        else:
            x, y, z = self.x, self.y, self.z
        self.np.show()
        self.np.setPos(x, y, z + 0.25 * math.sin(self.t * 5.0))

    def remove(self):
        if not self.removed:
            self.removed = True
            self.np.removeNode()


ICONS = {'health': 'hud_heart', 'armor': 'hud_armor', 'bribe': 'hud_star', 'package': 'package', 'money': 'money',
         'item': 'package'}
TINT = {'health': (1, 1, 1), 'armor': (1, 1, 1), 'bribe': (0.6, 0.8, 1.0), 'package': (1, 1, 1),
        'money': (1, 1, 1), 'item': (1.0, 0.8, 0.5)}


class Pickup(object):

    def __init__(self, world, kind, x, y, wid=None, amount=0, respawn=None, z=None):
        self.w = world
        self.kind = kind                  # weapon | health | armor | bribe | package | money | item
        self.x, self.y = x, y
        self.z = (max(0.0, world.city.ground_z(x, y)) if z is None else z)
        self.wid = wid
        self.amount = amount
        self.respawn = respawn            # None — одноразовый
        self.hidden_t = 0.0
        self.removed = False
        self.life = None                  # для выпавших денег/оружия: время жизни
        self.index = None
        self.on_take = None
        self.t = random.random() * 6.0
        tex = WEAPONS[wid].icon if kind == 'weapon' else ICONS[kind]
        root = world.fx.root.attachNewNode('pickup')
        root.setPos(x, y, self.z + 0.85)
        self.np = root
        model = None
        if kind == 'weapon':
            mdl = getattr(world, 'models', None)
            t = mdl.weapon(wid) if mdl is not None else None
            if t is not None:
                # настоящая модель оружия вместо плоского значка
                model = root.attachNewNode('spin')
                g = t.copyTo(model)
                g.setScale(1.7)
                mn, mx = g.getTightBounds(model)
                g.setPos(-(mn.x + mx.x) * 0.5, -(mn.y + mx.y) * 0.5, -(mn.z + mx.z) * 0.5)
                model.setP(18.0)
        if model is not None:
            self.card = model
        else:
            self.card = _card(world.assets, tex).copyTo(root)
            if kind == 'money':
                self.card.setScale(0.6, 1, 0.3)
            elif kind == 'weapon':
                self.card.setScale(0.95)
            else:
                self.card.setScale(0.62)
            c = TINT.get(kind, (1, 1, 1))
            self.card.setColorScale(c[0], c[1], c[2], 1)
        self.glow = _card(world.assets, 'glow', True).copyTo(root)
        self.glow.setBillboardPointEye()
        gc = {'weapon': (0.4, 0.6, 1.0), 'health': (1.0, 0.3, 0.3), 'armor': (0.3, 0.6, 1.0),
              'bribe': (0.5, 0.7, 1.0), 'package': (1.0, 0.8, 0.3), 'money': (0.4, 1.0, 0.4),
              'item': (1.0, 0.7, 0.3)}[kind]
        self.glow.setColorScale(gc[0], gc[1], gc[2], 0.55)
        self.glow.setScale(1.7)
        self.far = False

    def update(self, dt, px, py, on_foot):
        """Возвращает True, если предмет подобран."""
        if self.hidden_t > 0.0:
            self.hidden_t -= dt
            if self.hidden_t <= 0.0:
                self.np.show()
            return False
        if self.life is not None:
            self.life -= dt
            if self.life <= 0.0:
                self.remove()
                return False
        dx, dy = self.x - px, self.y - py
        d2 = dx * dx + dy * dy
        if d2 > 90.0 * 90.0:
            if not self.far:
                self.far = True
                self.np.hide()
            return False
        if self.far:
            self.far = False
            self.np.show()
        self.t += dt
        self.card.setH(self.t * 110.0)
        self.np.setZ(self.z + 0.85 + 0.12 * math.sin(self.t * 3.0))
        if on_foot and d2 < 1.25 * 1.25:
            return True
        return False

    def taken(self):
        if self.respawn is None:
            self.remove()
        else:
            self.hidden_t = self.respawn
            self.np.hide()

    def remove(self):
        if not self.removed:
            self.removed = True
            self.np.removeNode()


def spot_pickup(index, hint):
    """Что лежит в данной точке города: (kind, wid, amount) или None, если там пусто.

    Аптечек и бронежилетов на улицах нет: здоровье восстанавливается в убежище,
    броня продаётся в оружейном магазине.
    """
    res = _spot_pickup(index, hint)
    if res[0] in ('health', 'armor'):
        return None
    return res


def _spot_pickup(index, hint):
    r = random.Random(4242 + index * 97)
    v = r.random()
    if hint == 'alley':
        if v < 0.3:
            return ('weapon', W_BAT, 1)
        if v < 0.6:
            return ('weapon', W_PISTOL, 34)
        if v < 0.8:
            return ('weapon', W_MOLOTOV, 4)
        return ('health', None, 0)
    if hint == 'yard':
        if v < 0.3:
            return ('weapon', W_PISTOL, 34)
        if v < 0.55:
            return ('weapon', W_UZI, 60)
        if v < 0.8:
            return ('health', None, 0)
        return ('armor', None, 0)
    if hint == 'lot':
        if v < 0.35:
            return ('armor', None, 0)
        if v < 0.7:
            return ('weapon', W_SHOTGUN, 12)
        return ('bribe', None, 0)
    if hint == 'beach':
        if v < 0.4:
            return ('health', None, 0)
        if v < 0.7:
            return ('bribe', None, 0)
        return ('weapon', W_GRENADE, 4)
    if hint == 'pier':
        if v < 0.5:
            return ('weapon', W_ROCKET, 4)
        return ('weapon', W_AK, 60)
    if v < 0.5:
        return ('health', None, 0)
    return ('weapon', W_BAT, 1)
