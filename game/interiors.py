# -*- coding: utf-8 -*-
"""Интерьеры: комнаты за дверями важных зданий — дом героя, гараж, бар, кабинет, магазины, участок,
больница, банк, сарай лодочника и чайная.

Как это устроено.  Физика игры двумерная, с одной высотой земли в каждой точке, поэтому комнаты не вырезаны
внутри домов, а стоят отдельно, далеко за краем карты.  Игрок подходит к двери с жёлтой стрелкой, экран
гаснет — и он уже внутри; выход такой же, через дверь.

Пока игрок в помещении, улица «замирает»: транспорт, прохожие и полиция не обновляются (World.update),
город и небо не рисуются, свет заменён комнатным (Sky.indoor).  Камера ведёт себя как на улице, но стены ей
не мешают: они односторонние, и стена, за которую ушла камера, просто не видна — получается вид
«кукольного домика».  Высокая мебель, оказавшаяся между камерой и героем, на это время прячется.

Комната описывается функцией room_*(b): она вызывает методы «строителя» (стены, двери, окна, мебель, жильцы,
точки для дел).  Координаты — в метрах от юго-западного угла комнаты: x на восток, y на север; входная дверь
всегда в южной стене.  Мебель из набора ставится командой put(имя, x, y, поворот): при повороте 0 предмет
смотрит на юг (к двери), 90 — на восток, 180 — на север, 270 — на запад.
"""
import math
import random

from panda3d.core import NodePath

from .collision import F_PED, F_BULLET, F_SIGHT
from .defs import make_look, cop_look, medic_look, gang_look, W_FIST
from .meshbuilder import MeshBuilder
from .pickups import Arrow
from . import city as city_mod

INT_X0 = 9000.0             # комнаты стоят в ряд далеко на востоке, за краем карты
INT_Y0 = 0.0
SLOT = 90.0
PAD = 14.0                  # ровная площадка шире комнаты: камера свободно выходит за стены
TALL = 1.32                 # предмет выше — может заслонить героя, прячем по необходимости
# Сидячая поза (клипы sit, sit_talk, write), снято с моделей: фигура стоит своей опорной точкой под коленями.
SIT_H = 0.46                # низ бёдер над полом: на такой высоте должна быть подушка
SIT_BACK = 0.44             # от опорной точки назад до спины
SIT_PELVIS = 0.34           # от опорной точки назад до таза
SIT_SHIN = 0.02             # от опорной точки вперёд до задней стороны голеней
SIT_CLIPS = ('sit', 'sit_talk', 'write')


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)
WALL_FLAGS = F_PED | F_BULLET | F_SIGHT
YELLOW = (1.0, 0.86, 0.2, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)
WOOD = (0.40, 0.28, 0.19, 1.0)
DARKWOOD = (0.24, 0.17, 0.12, 1.0)
BLACK = (0.10, 0.10, 0.11, 1.0)
STEEL = (0.56, 0.58, 0.62, 1.0)

# свет: (рассеянный, основной сверху-спереди, встречный)
LIGHTS = {
    'warm': ((0.60, 0.56, 0.50), (0.56, 0.50, 0.40), (0.20, 0.18, 0.16)),
    'cold': ((0.60, 0.62, 0.66), (0.48, 0.50, 0.54), (0.18, 0.19, 0.21)),
    'dim': ((0.44, 0.36, 0.36), (0.52, 0.38, 0.30), (0.16, 0.12, 0.14)),
    'work': ((0.54, 0.54, 0.52), (0.50, 0.48, 0.44), (0.18, 0.18, 0.18)),
}


class Room(object):
    """Готовая комната: где стоит, что в ней и как в неё попасть."""

    def __init__(self, name, index):
        self.name = name
        self.index = index
        self.ox = INT_X0 + index * SLOT
        self.oy = INT_Y0
        self.w = self.d = 8.0
        self.h = 3.0
        self.title = ''
        self.light = 'warm'
        self.landmark = name
        self.node = None
        self.win_np = None
        self.tall = []              # [(узел, x, y, радиус)] в координатах мира
        self.spots = {}             # имя -> (x, y, курс)
        self.people = []            # описания жильцов
        self.seats = []             # на чём можно сидеть: (x, y, поворот, масштаб, сиденье) в координатах комнаты
        self.cars = []              # (тип, x, y, курс, цвет)
        self.door_x = 1.5
        self.exit = (0.0, 0.0)      # точка у двери внутри
        self.entry = (0.0, 0.0, 0.0)
        self.out = None             # точка у двери снаружи (на улице)
        self.out_pos = None         # где герой оказывается, выйдя
        self.wall_y = 0.0
        self.arrow = None
        self.arrow_in = None

    def pos(self, x, y):
        return self.ox + x, self.oy + y

    def contains(self, x, y, m=0.6):
        return self.ox - m <= x <= self.ox + self.w + m and self.oy - m <= y <= self.oy + self.d + m


class Builder(object):
    """Строитель одной комнаты."""

    def __init__(self, world, room):
        self.world = world
        self.room = room
        self.mb = MeshBuilder()
        self.cur = self.mb
        self.win = MeshBuilder()
        self.pieces = []            # [(MeshBuilder, x, y, r)]
        self._piece = None
        self.items = []             # (имя, x, y, z, поворот, масштаб)
        self.seats = []             # на чём можно сидеть: (x, y, поворот, масштаб, сиденье)
        self.sitters = []           # (описание жильца, x, y, курс): рассаживаются в finish()
        self.solids = []            # (x0, y0, x1, y1, z1)
        self.rounds = []            # (x, y, r, z1)
        self.holes = {'s': [], 'n': [], 'w': [], 'e': []}
        self.floor = ('int_parquet', 2.0, WHITE)
        self.wall = ('int_wall', 1.6, WHITE)
        self.ceil = ('int_ceil', 1.2, WHITE)
        self.wainscot = None
        self.base = DARKWOOD

    # ------------------------------------------------------------------
    # коробка комнаты
    # ------------------------------------------------------------------
    def shell(self, w, d, h, floor, wall, wainscot=None, ceil=None, base=DARKWOOD, light='warm', title=''):
        r = self.room
        r.w, r.d, r.h = float(w), float(d), float(h)
        r.light = light
        r.title = title
        self.floor = floor
        self.wall = wall
        self.wainscot = wainscot
        if ceil is not None:
            self.ceil = ceil
        self.base = base

    def _span(self, side):
        return self.room.w if side in 'sn' else self.room.d

    def _wq(self, key, side, u0, u1, z0, z1, uv=(0.0, 0.0, 1.0, 1.0), color=WHITE, off=0.0, mb=None):
        """Прямоугольник на стене лицом в комнату.  u — координата вдоль стены (x для северной и южной,
        y для западной и восточной), off — отступ от стены внутрь."""
        r = self.room
        mb = mb or self.cur
        if side == 'n':
            mb.wall(key, u0, r.d - off, u1, r.d - off, z0, z1, uv, color)
        elif side == 's':
            mb.wall(key, u1, off, u0, off, z0, z1, uv, color)
        elif side == 'w':
            mb.wall(key, off, u0, off, u1, z0, z1, uv, color)
        else:
            mb.wall(key, r.w - off, u1, r.w - off, u0, z0, z1, uv, color)

    def _wall_rect(self, side, u0, u1, z0, z1):
        ws = self.wainscot
        if ws is not None and z0 < ws[3] - 1e-6 and z1 > ws[3] + 1e-6:
            self._wall_rect(side, u0, u1, z0, ws[3])
            self._wall_rect(side, u0, u1, ws[3], z1)
            return
        if ws is not None and z1 <= ws[3] + 1e-6:
            tex, tile, col = ws[0], ws[1], ws[2]
        else:
            tex, tile, col = self.wall
        if side in ('n', 'w'):
            ua, ub = u0 / tile, u1 / tile
        else:
            ua, ub = -u1 / tile, -u0 / tile
        self._wq(tex, side, u0, u1, z0, z1, (ua, z0 / tile, ub, z1 / tile), col, mb=self.mb)

    def _walls(self):
        h = self.room.h
        for side in 'snwe':
            length = self._span(side)
            u = 0.0
            for (a, b, z0, z1) in sorted(self.holes[side]):
                if a > u + 1e-6:
                    self._wall_rect(side, u, a, 0.0, h)
                    self._wq(None, side, u, a, 0.0, 0.10, color=self.base, off=0.02, mb=self.mb)
                if z0 > 1e-6:
                    self._wall_rect(side, a, b, 0.0, z0)
                    self._wq(None, side, a, b, 0.0, 0.10, color=self.base, off=0.02, mb=self.mb)
                if z1 < h - 1e-6:
                    self._wall_rect(side, a, b, z1, h)
                u = b
            if u < length - 1e-6:
                self._wall_rect(side, u, length, 0.0, h)
                self._wq(None, side, u, length, 0.0, 0.10, color=self.base, off=0.02, mb=self.mb)
            ws = self.wainscot
            if ws is not None:                           # рейка над панелями
                u = 0.0
                for (a, b, z0, z1) in sorted(self.holes[side]) + [(length, length, 0.0, 0.0)]:
                    if a > u + 1e-6:
                        self._wq(None, side, u, a, ws[3] - 0.03, ws[3] + 0.04, color=self.base, off=0.025,
                                 mb=self.mb)
                    if z0 > ws[3] + 0.05 or z1 < ws[3] - 0.05:
                        self._wq(None, side, a, b, ws[3] - 0.03, ws[3] + 0.04, color=self.base, off=0.025,
                                 mb=self.mb)
                    u = b

    def _frame(self, side, u0, u1, z0, z1, color, t=0.07):
        mb = self.mb
        self._wq(None, side, u0 - t, u0, z0, z1 + t, color=color, off=0.03, mb=mb)
        self._wq(None, side, u1, u1 + t, z0, z1 + t, color=color, off=0.03, mb=mb)
        self._wq(None, side, u0, u1, z1, z1 + t, color=color, off=0.03, mb=mb)
        if z0 > 0.05:
            self._wq(None, side, u0 - t, u1 + t, z0 - t, z0, color=color, off=0.03, mb=mb)

    def door(self, side, u, tex='int_door', w=1.0, h=2.1, main=False, frame=DARKWOOD):
        """Дверь в стене.  main=True — это выход на улицу (он всегда в южной стене)."""
        self.holes[side].append((u - w * 0.5, u + w * 0.5, 0.0, h))
        self._wq(tex, side, u - w * 0.5, u + w * 0.5, 0.0, h, mb=self.mb)
        self._frame(side, u - w * 0.5, u + w * 0.5, 0.0, h, frame)
        if main:
            r = self.room
            r.door_x = u
            r.exit = r.pos(u, 0.45)
            r.entry = r.pos(u, 1.7) + (math.pi / 2,)
            self._wq('int_sign_exit', side, u - 0.32, u + 0.32, h + 0.14, h + 0.30, off=0.03, mb=self.win)

    def window(self, side, u, w=1.2, h=1.4, sill=0.9, tex='int_window', frame=(0.9, 0.9, 0.86, 1.0), tile=None):
        z1 = min(self.room.h - 0.15, sill + h)
        self.holes[side].append((u - w * 0.5, u + w * 0.5, sill, z1))
        uv = (0.0, 0.0, 1.0, 1.0) if tile is None else (0.0, 0.0, w / tile[0], (z1 - sill) / tile[1])
        self._wq((tex, 'unlit'), side, u - w * 0.5, u + w * 0.5, sill, z1, uv, mb=self.win)
        self._frame(side, u - w * 0.5, u + w * 0.5, sill, z1, frame, 0.06)

    def picture(self, side, u, z, w, h, tex, frame=DARKWOOD, unlit=False, t=0.05):
        """Картина, плакат, вывеска, карта: низ на высоте z, середина в точке u."""
        if frame is not None:
            self._wq(None, side, u - w * 0.5 - t, u + w * 0.5 + t, z - t, z + h + t, color=frame, off=0.03)
        key = (tex, 'unlit') if unlit else tex
        self._wq(key, side, u - w * 0.5, u + w * 0.5, z, z + h, off=0.045, mb=self.win if unlit else None)

    def rug(self, x, y, w, d, tex='int_rug', color=WHITE, rot=0):
        self.mb.flat((tex, 'decal'), x - w * 0.5, y - d * 0.5, x + w * 0.5, y + d * 0.5, 0.015, color=color, rot=rot)

    # ------------------------------------------------------------------
    # предметы
    # ------------------------------------------------------------------
    def begin(self, x, y, r):
        """Дальше — высокий предмет: он получит свой узел и сможет прятаться, когда заслоняет героя."""
        self._piece = MeshBuilder()
        self.cur = self._piece
        self.pieces.append((self._piece, x, y, r))

    def end(self):
        self.cur = self.mb
        self._piece = None

    def solid(self, x0, y0, x1, y1, z1=1.0):
        self.solids.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1), z1))

    def _turned(self, x, y, yaw, w, d):
        """Границы прямоугольника w x d с серединой (x, y), повёрнутого на yaw градусов."""
        a = math.radians(yaw)
        c, s = abs(math.cos(a)), abs(math.sin(a))
        hw, hd = (w * c + d * s) * 0.5, (w * s + d * c) * 0.5
        return x - hw, y - hd, x + hw, y + hd

    def put(self, name, x, y, yaw=0.0, z=0.0, solid=True, scale=1.0):
        """Предмет из набора мебели."""
        size = self.world.models.furn_size(name)
        if size is None:
            return
        self.items.append((name, x, y, z, yaw, scale))
        seat = self.world.models.furn_seat(name)
        if seat is not None and z < 0.05:
            self.seats.append((x, y, yaw, scale, seat))
        if solid and z < 0.3:
            x0, y0, x1, y1 = self._turned(x, y, yaw, size[0] * scale, size[1] * scale)
            self.solid(x0 + 0.04, y0 + 0.04, x1 - 0.04, y1 - 0.04, size[2] * scale)

    def box(self, x0, y0, x1, y1, z0, z1, key=None, color=WHITE, uv_m=None, solid=True, faces='xXyYZ',
            top_key=None, top_color=None):
        tall = z1 > TALL and self._piece is None
        if tall:
            self.begin((x0 + x1) * 0.5, (y0 + y1) * 0.5, 0.5 * math.hypot(x1 - x0, y1 - y0))
        self.cur.box(key, x0, y0, z0, x1, y1, z1, color, faces, uv_m, top_key, top_color)
        if tall:
            self.end()
        if solid and z0 < 0.5:
            self.solid(x0, y0, x1, y1, z1)

    def cabinet(self, x, y, yaw, w, d, h, front, body=DARKWOOD, uv=(0.0, 0.0, 1.0, 1.0), z0=0.0, solid=True,
                unlit=False, top=None):
        """Шкаф, автомат, стеллаж: коробка с картинкой на лицевой стороне (лицом на юг при повороте 0)."""
        tall = z0 + h > TALL and self._piece is None
        if tall:
            self.begin(x, y, 0.5 * math.hypot(w, d))
        mb = self.cur
        mb.set_xform(x, y, 0.0, math.radians(yaw))
        mb.box(None, -w * 0.5, -d * 0.5, z0, w * 0.5, d * 0.5, z0 + h, body, 'xXYZ' + ('z' if z0 > 0.3 else ''),
               top_color=top)
        key = (front, 'unlit') if unlit else front
        tgt = self.win if unlit else mb
        tgt.set_xform(x, y, 0.0, math.radians(yaw))
        tgt.quad(key, (-w * 0.5, -d * 0.5, z0), (w * 0.5, -d * 0.5, z0), (w * 0.5, -d * 0.5, z0 + h),
                 (-w * 0.5, -d * 0.5, z0 + h), uv)
        tgt.clear_xform()
        mb.clear_xform()
        if tall:
            self.end()
        if solid and z0 < 0.5:
            x0, y0, x1, y1 = self._turned(x, y, yaw, w, d)
            self.solid(x0, y0, x1, y1, z0 + h)

    def shelf(self, side, u0, u1, z0, z1, tex, tile, depth=0.35, body=DARKWOOD, solid=True):
        """Стеллаж у стены во всю длину u0..u1 с повторяющейся картинкой (книги, бутылки)."""
        r = self.room
        if side == 'n':
            x0, y0, x1, y1 = u0, r.d - depth, u1, r.d
        elif side == 's':
            x0, y0, x1, y1 = u0, 0.0, u1, depth
        elif side == 'w':
            x0, y0, x1, y1 = 0.0, u0, depth, u1
        else:
            x0, y0, x1, y1 = r.w - depth, u0, r.w, u1
        tall = z1 > TALL
        if tall:
            self.begin((x0 + x1) * 0.5, (y0 + y1) * 0.5, 0.5 * (u1 - u0))
        skip = {'n': 'yY', 's': 'yY', 'w': 'xX', 'e': 'xX'}[side]
        faces = ''.join(f for f in 'xXyYZ' if f not in skip) + ('z' if z0 > 0.3 else '')
        self.cur.box(None, x0, y0, z0, x1, y1, z1, body, faces)
        self._wq(tex, side, u0, u1, z0, z1, (0.0, 0.0, (u1 - u0) / tile[0], (z1 - z0) / tile[1]), off=depth)
        if tall:
            self.end()
        if solid and z0 < 0.5:
            self.solid(x0, y0, x1, y1, z1)

    def counter(self, x0, y0, x1, y1, h=1.05, side='int_wooddark', top='int_marble', color=WHITE):
        mb = self.mb
        mb.box(side, x0, y0, 0.0, x1, y1, h - 0.05, color, 'xXyY', 1.2)
        mb.box(top, x0 - 0.04, y0 - 0.04, h - 0.05, x1 + 0.04, y1 + 0.04, h, WHITE, 'xXyYZ', 1.0)
        self.solid(x0, y0, x1, y1, h)

    def desk(self, x, y, yaw=0.0, w=1.6, d=0.75, h=0.76, tex='int_wooddark', color=WHITE):
        """Письменный стол: хозяин сидит с северной стороны (при повороте 0) лицом на юг."""
        mb = self.mb
        mb.set_xform(x, y, 0.0, math.radians(yaw))
        mb.box(tex, -w * 0.5, -d * 0.5, h - 0.05, w * 0.5, d * 0.5, h, color, 'xXyYZz', 1.0)
        mb.box(tex, -w * 0.5 + 0.03, -d * 0.5 + 0.04, 0.0, -w * 0.5 + 0.08, d * 0.5 - 0.04, h - 0.05, color, 'xXyY', 1.0)
        mb.box(tex, w * 0.5 - 0.08, -d * 0.5 + 0.04, 0.0, w * 0.5 - 0.03, d * 0.5 - 0.04, h - 0.05, color, 'xXyY', 1.0)
        mb.box(tex, -w * 0.5 + 0.08, -d * 0.5 + 0.06, 0.22, w * 0.5 - 0.08, -d * 0.5 + 0.09, h - 0.05, color, 'yY', 1.0)
        mb.clear_xform()
        x0, y0, x1, y1 = self._turned(x, y, yaw, w, d)
        self.solid(x0, y0, x1, y1, h)

    def table(self, x, y, w=1.0, d=0.7, h=0.74, tex='int_wooddark', color=WHITE):
        mb = self.mb
        mb.box(tex, x - w * 0.5, y - d * 0.5, h - 0.04, x + w * 0.5, y + d * 0.5, h, color, 'xXyYZz', 1.0)
        for sx in (-1, 1):
            for sy in (-1, 1):
                cx, cy = x + sx * (w * 0.5 - 0.06), y + sy * (d * 0.5 - 0.06)
                mb.box(None, cx - 0.03, cy - 0.03, 0.0, cx + 0.03, cy + 0.03, h - 0.04, DARKWOOD, 'xXyY')
        self.solid(x - w * 0.5 + 0.05, y - d * 0.5 + 0.05, x + w * 0.5 - 0.05, y + d * 0.5 - 0.05, h)

    def bench(self, x, y, yaw=0.0, w=2.0, color=WOOD):
        mb = self.mb
        mb.set_xform(x, y, 0.0, math.radians(yaw))
        mb.box(None, -w * 0.5, -0.2, 0.40, w * 0.5, 0.2, 0.46, color, 'xXyYZz')
        mb.box(None, -w * 0.5, 0.17, 0.46, w * 0.5, 0.22, 0.92, color, 'xXyYZ')
        for sx in (-1, 1):
            mb.box(None, sx * (w * 0.5 - 0.1) - 0.03, -0.18, 0.0, sx * (w * 0.5 - 0.1) + 0.03, 0.2, 0.40, BLACK, 'xXyY')
        mb.clear_xform()
        x0, y0, x1, y1 = self._turned(x, y, yaw, w, 0.44)
        self.solid(x0, y0, x1, y1, 0.9)
        self.seats.append((x, y, yaw, 1.0, dict(h=0.46, yf=-0.2, yb=0.17, u0=-(w * 0.5 - 0.3), u1=w * 0.5 - 0.3)))

    def stool(self, x, y, color=(0.5, 0.1, 0.12, 1.0), h=0.78):
        """Барный табурет на ножке.  Круглый: сидящий на нём смотрит туда, куда ему велено."""
        mb = self.mb
        mb.cylinder(None, x, y, 0.0, 0.04, 0.2, 8, STEEL)
        mb.cylinder(None, x, y, 0.04, h - 0.08, 0.035, 6, STEEL, cap_top=False)
        mb.cylinder('int_leather', x, y, h - 0.08, h, 0.19, 10, color)
        # подножка-кольцо: на высоком табурете ноги не висят в воздухе
        if h > 0.6:
            mb.cylinder(None, x, y, h - 0.50, h - 0.47, 0.17, 10, STEEL)
        self.rounds.append((x, y, 0.2, h))
        self.seats.append((x, y, None, 1.0, dict(h=h, yf=-0.19, ye=0.19, u0=0.0, u1=0.0)))

    def barrel(self, x, y, color=(0.3, 0.42, 0.6, 1.0), h=0.9, r=0.29):
        self.mb.cylinder('metal_paint', x, y, 0.0, h, r, 10, color, uv_wrap=2.0)
        self.rounds.append((x, y, r, h))

    def crate(self, x, y, s=0.8, yaw=0.0, z=0.0, color=WHITE):
        mb = self.mb
        mb.set_xform(x, y, z, math.radians(yaw))
        mb.box('crate', -s * 0.5, -s * 0.5, 0.0, s * 0.5, s * 0.5, s, color, 'xXyYZ')
        mb.clear_xform()
        if z < 0.3:
            x0, y0, x1, y1 = self._turned(x, y, yaw, s, s)
            self.solid(x0, y0, x1, y1, s)

    def tyres(self, x, y, n=3):
        for k in range(n):
            self.mb.cylinder(None, x, y, k * 0.2, k * 0.2 + 0.19, 0.31, 10, (0.09, 0.09, 0.10, 1.0),
                             top_color=(0.16, 0.16, 0.17, 1.0))
        self.rounds.append((x, y, 0.31, n * 0.2))

    def column(self, x, y, s=0.5, tex='int_marble', color=WHITE):
        self.begin(x, y, s * 0.7)
        self.cur.box(tex, x - s * 0.5, y - s * 0.5, 0.0, x + s * 0.5, y + s * 0.5, self.room.h, color, 'xXyY', 1.0)
        self.end()
        self.solid(x - s * 0.5, y - s * 0.5, x + s * 0.5, y + s * 0.5, self.room.h)

    def lamp(self, x, y, kind='pendant', color=(1.0, 0.9, 0.7), pool=3.2, power=0.5):
        """Светильник на потолке и пятно света под ним."""
        h = self.room.h
        if kind == 'tube':
            self.put('lamp_tube', x, y, 0.0, h - 0.08, solid=False)
            z = h - 0.1
            s = 0.75
        elif kind == 'bulb':
            self.mb.box(None, x - 0.012, y - 0.012, h - 0.7, x + 0.012, y + 0.012, h, BLACK, 'xXyY')
            self.mb.cylinder(None, x, y, h - 0.86, h - 0.7, 0.07, 6, (1.0, 0.95, 0.75, 1.0), cap_bottom=True)
            z = h - 0.88
            s = 0.55
        else:
            size = self.world.models.furn_size('lamp_pendant') or (0.3, 0.3, 0.8)
            self.put('lamp_pendant', x, y, 0.0, h - size[2], solid=False)
            z = h - size[2] - 0.02
            s = 0.6
        c = (color[0], color[1], color[2], 0.8)
        self.win.quad(('glow', 'add'), (x - s, y + s, z), (x + s, y + s, z), (x + s, y - s, z), (x - s, y - s, z),
                      color=c)
        if pool:
            self.win.flat(('lightpool', 'add'), x - pool, y - pool, x + pool, y + pool, 0.03,
                          color=(color[0], color[1], color[2], power))

    def tv(self, x, y, yaw, z=0.75, w=0.95, h=0.6, tex='int_tv'):
        self.cabinet(x, y, yaw, w, 0.1, h, tex, BLACK, z0=z, solid=False, unlit=True)

    def bars(self, x0, y0, x1, y1, step=0.14, h=None):
        """Решётка от (x0, y0) до (x1, y1) — по прямой вдоль оси."""
        h = h or self.room.h
        self.begin((x0 + x1) * 0.5, (y0 + y1) * 0.5, 0.0)
        mb = self.cur
        n = max(1, int(round(max(abs(x1 - x0), abs(y1 - y0)) / step)))
        for k in range(n + 1):
            x = x0 + (x1 - x0) * k / n
            y = y0 + (y1 - y0) * k / n
            mb.box(None, x - 0.018, y - 0.018, 0.0, x + 0.018, y + 0.018, h, (0.22, 0.23, 0.25, 1.0), 'xXyY')
        for z in (0.15, h * 0.5, h - 0.15):
            mb.box(None, min(x0, x1) - 0.02, min(y0, y1) - 0.02, z - 0.025, max(x0, x1) + 0.02, max(y0, y1) + 0.02,
                   z + 0.025, (0.22, 0.23, 0.25, 1.0), 'xXyYZz')
        self.end()
        self.solid(min(x0, x1) - 0.05, min(y0, y1) - 0.05, max(x0, x1) + 0.05, max(y0, y1) + 0.05, h)

    # ------------------------------------------------------------------
    # люди и точки
    # ------------------------------------------------------------------
    def person(self, key, look, x, y, yaw, clips=('idle',), name=None, lines=None, sit=False):
        """Жилец комнаты.  yaw — курс в градусах (0 — на восток, 90 — на север).  clips — позы, которые он
        меняет время от времени; lines — что говорит, когда герой подходит."""
        r = self.room
        wx, wy = r.pos(x, y)
        if sit:
            # сидящий остаётся сидеть: стоячие позы (например «пьёт») подняли бы его прямо сквозь стул
            clips = [c if c in SIT_CLIPS else 'sit_talk' for c in clips]
        info = dict(key=key, look=look, x=wx, y=wy, yaw=math.radians(yaw), clips=tuple(clips), name=name,
                    lines=lines, sit=sit, dz=0.0)
        r.people.append(info)
        if sit:
            self.sitters.append((info, x, y, yaw))

    def seat_pose(self, x, y, yaw):
        """Куда посадить человека, которого хотят видеть сидящим около (x, y): (x, y, курс в градусах, подъём).

        Берётся ближайшее сиденье комнаты.  Человек встаёт так, чтобы спина пришлась к спинке, бёдра легли на
        подушку, а голени оказались перед её краем; смотрит он туда же, куда стул.  None — сесть не на что."""
        best = None
        for seat in self.seats:
            d = math.hypot(seat[0] - x, seat[1] - y)
            if d < 1.3 and (best is None or d < best[0]):
                best = (d, seat)
        if best is None:
            return None
        sx, sy, syaw, sc, m = best[1]
        if syaw is None:
            # круглый табурет: таз над серединой
            a = math.radians(yaw)
            return (sx + math.cos(a) * SIT_PELVIS, sy + math.sin(a) * SIT_PELVIS, yaw, max(-0.02, m['h'] * sc - SIT_H))
        a = math.radians(syaw)
        c, sn = math.cos(a), math.sin(a)
        # поперёк предмета — как можно ближе к запрошенному месту
        u = clamp(((x - sx) * c + (y - sy) * sn) / sc, m['u0'], m['u1']) * sc
        if 'yb' in m:
            v = min(m['yb'] * sc - SIT_BACK, m['yf'] * sc + SIT_SHIN)
        else:
            v = (m['yf'] + m['ye']) * 0.5 * sc - SIT_PELVIS
        return (sx + u * c - v * sn, sy + u * sn + v * c, syaw - 90.0, max(-0.02, m['h'] * sc - SIT_H))

    def spot(self, name, x, y, yaw=90.0):
        r = self.room
        r.spots[name] = r.pos(x, y) + (math.radians(yaw),)

    def car(self, kind, x, y, yaw, paint=0):
        r = self.room
        r.cars.append((kind,) + r.pos(x, y) + (math.radians(yaw), paint))

    # ------------------------------------------------------------------
    def finish(self, assets, static, parent):
        r = self.room
        models = self.world.models
        r.seats = list(self.seats)
        for (info, x, y, yaw) in self.sitters:
            pose = self.seat_pose(x, y, yaw)
            if pose is None:
                info['sit'] = False
                continue
            info['x'], info['y'] = r.pos(pose[0], pose[1])
            info['yaw'] = math.radians(pose[2])
            info['dz'] = pose[3]
        mb = self.mb
        tex, tile, col = self.floor
        mb.flat(tex, 0.0, 0.0, r.w, r.d, 0.0, tile=(tile, tile), color=col)
        tex, tile, col = self.ceil
        mb.quad(tex, (0.0, r.d, r.h), (r.w, r.d, r.h), (r.w, 0.0, r.h), (0.0, 0.0, r.h),
                (0.0, r.d / tile, r.w / tile, 0.0), col)
        self._walls()
        node = parent.attachNewNode('room_' + r.name)
        node.setPos(r.ox, r.oy, 0.0)
        shell = mb.build('shell', assets.apply_state)
        shell.flattenStrong()
        shell.reparentTo(node)
        win = self.win.build('glow', assets.apply_state)
        win.reparentTo(node)
        r.win_np = win
        for (pmb, x, y, rad) in self.pieces:
            np_ = pmb.build('piece', assets.apply_state)
            np_.flattenStrong()
            np_.reparentTo(node)
            r.tall.append((np_, r.ox + x, r.oy + y, rad))
        low = node.attachNewNode('low')
        for (name, x, y, z, yaw, scale) in self.items:
            proto = models.furn(name)
            if proto is None:
                continue
            size = models.furn_size(name)
            if z + size[2] * scale > TALL and z < 1.0:
                np_ = proto.copyTo(node)
                r.tall.append((np_, r.ox + x, r.oy + y, 0.5 * math.hypot(size[0], size[1]) * scale))
            else:
                np_ = proto.copyTo(low)
            np_.setPosHprScale(x, y, z, yaw, 0, 0, scale, scale, scale)
        low.flattenStrong()
        # стены и мебель для столкновений
        ox, oy = r.ox, r.oy
        t = 0.4
        static.add_box(ox - t, oy - t, ox + r.w + t, oy, 0.0, r.h, WALL_FLAGS, None)
        static.add_box(ox - t, oy + r.d, ox + r.w + t, oy + r.d + t, 0.0, r.h, WALL_FLAGS, None)
        static.add_box(ox - t, oy, ox, oy + r.d, 0.0, r.h, WALL_FLAGS, None)
        static.add_box(ox + r.w, oy, ox + r.w + t, oy + r.d, 0.0, r.h, WALL_FLAGS, None)
        for (x0, y0, x1, y1, z1) in self.solids:
            if x1 - x0 > 0.02 and y1 - y0 > 0.02:
                static.add_box(ox + x0, oy + y0, ox + x1, oy + y1, 0.0, z1, F_PED, None)
        for (x, y, rad, z1) in self.rounds:
            static.add_circle(ox + x, oy + y, rad, z1, F_PED, None)
        node.hide()
        r.node = node
        return r


# ---------------------------------------------------------------------------
# комнаты
# ---------------------------------------------------------------------------
def room_safehouse(b):
    """Дом Макса на Сосновой: кровать, диван, кухонный угол."""
    b.shell(7.0, 5.6, 2.8, ('int_parquet', 2.0, (0.9, 0.86, 0.8, 1.0)), ('int_paper', 1.2, (0.80, 0.78, 0.62, 1.0)),
            base=DARKWOOD, light='warm', title='Дом Макса')
    b.door('s', 1.2, 'int_door_old', main=True)
    b.window('n', 2.0)
    b.window('n', 4.2)
    b.put('bed_single', 6.3, 4.45)
    b.put('nightstand', 5.35, 5.3)
    b.put('lamp_table', 5.35, 5.3, 0, 0.7, solid=False)
    b.rug(3.4, 2.9, 2.0, 3.0)
    b.put('sofa_old', 0.5, 3.3, 90)
    b.put('table_side', 0.45, 1.75)
    b.cabinet(6.72, 1.9, 270, 1.3, 0.5, 0.62, 'int_panel', DARKWOOD, (0, 0, 2, 0.6))
    b.tv(6.6, 1.9, 270, 0.64, 0.9, 0.56)
    # кухонный угол вдоль южной стены
    b.put('fridge', 2.96, 0.45, 180)
    b.put('stove_old', 3.67, 0.4, 180)
    b.counter(3.95, 0.0, 5.5, 0.6, 0.9, 'int_panel')
    b.put('microwave', 4.4, 0.3, 180, 0.9, solid=False)
    b.put('pot', 5.1, 0.3, 0, 0.9, solid=False)
    b.picture('s', 4.7, 1.45, 1.5, 0.5, 'int_panel', None)
    b.table(3.1, 4.9, 1.1, 0.7, 0.72, 'int_planks')
    b.put('chair_wood', 2.25, 4.9, 90)
    b.put('chair_wood', 3.95, 4.9, 270)
    b.put('cup', 3.3, 4.95, 0, 0.72, solid=False)
    b.cabinet(0.33, 5.0, 90, 1.1, 0.6, 2.0, 'int_panel', DARKWOOD, (0, 0, 2, 2))
    b.picture('w', 3.3, 1.45, 0.7, 0.9, 'int_poster_a')
    b.picture('e', 3.2, 1.3, 1.0, 1.0, 'map', DARKWOOD)
    b.put('plant_b', 0.5, 0.5)
    b.lamp(3.5, 2.8, 'bulb')
    b.spot('bed', 5.3, 4.2, 0.0)
    b.spot('wake', 5.45, 3.6, -90.0)


def room_vano(b):
    """Гараж Вано: машина на ремонте, верстак, конторка в углу."""
    b.shell(13.0, 9.5, 4.2, ('int_garage', 4.0, WHITE), ('int_wall', 2.0, (0.80, 0.80, 0.76, 1.0)),
            wainscot=('brick', 2.4, (0.62, 0.56, 0.52, 1.0), 1.5), base=BLACK, light='work', title='Гараж Вано',
            ceil=('corrugated', 3.0, (0.5, 0.52, 0.55, 1.0)))
    b.door('s', 1.3, 'int_door_metal', main=True, frame=BLACK)
    b.picture('s', 7.0, 0.0, 4.4, 3.2, 'corrugated', BLACK, t=0.12)          # закрытые ворота
    for u in (2.6, 6.5, 10.4):
        b.window('n', u, 2.4, 1.2, 2.5, 'int_window_ind', (0.2, 0.2, 0.22, 1.0))
    b.car('sports', 7.0, 4.6, -90.0, 0)
    # верстак и инструмент вдоль западной стены
    b.counter(0.0, 3.2, 0.75, 6.6, 0.92, 'int_panel', 'int_planks')
    b.picture('w', 4.9, 1.25, 2.6, 1.3, 'int_tools', BLACK)
    b.cabinet(0.36, 7.3, 90, 0.9, 0.55, 1.0, 'metal_paint', (0.62, 0.10, 0.08, 1.0), (0, 0, 1, 1))
    b.tyres(0.5, 8.9, 4)
    b.tyres(1.2, 9.0, 2)
    b.barrel(2.2, 9.0, (0.2, 0.36, 0.56, 1.0))
    b.barrel(2.9, 9.05, (0.6, 0.16, 0.1, 1.0))
    b.crate(4.1, 8.95, 0.8, 8)
    b.crate(4.1, 8.95, 0.6, 30, 0.8)
    b.shelf('n', 5.2, 8.4, 0.0, 2.1, 'crate', (0.7, 0.7), 0.5, (0.3, 0.32, 0.36, 1.0))
    # конторка
    b.desk(11.6, 7.6, 270, 1.5, 0.75)
    b.put('chair_office', 12.4, 7.6, 270)
    b.put('chair_wood', 10.6, 7.6, 90)
    b.cabinet(12.7, 8.95, 0, 0.5, 0.6, 1.3, 'int_filing', (0.3, 0.32, 0.34, 1.0))
    b.cabinet(12.15, 8.95, 0, 0.5, 0.6, 1.3, 'int_filing', (0.3, 0.32, 0.34, 1.0))
    b.picture('e', 7.6, 1.5, 0.9, 1.1, 'int_poster_b')
    b.picture('n', 11.2, 1.5, 1.3, 1.0, 'int_board', None)
    b.put('sofa_old', 12.45, 3.0, 270)
    b.put('table_dark', 11.5, 3.0)
    b.put('fridge_black', 12.5, 0.5, 180)
    b.put('coffee', 11.55, 7.25, 90, 0.76, solid=False, scale=0.8)
    for (x, y) in ((3.5, 3.0), (9.5, 3.0), (3.5, 7.0), (9.5, 7.0)):
        b.lamp(x, y, 'tube', (0.9, 0.95, 1.0), 4.2, 0.4)
    b.person('vano', None, 5.4, 4.3, 0.0, ('fix', 'fix', 'idle', 'arms'), 'Вано',
             ['Вано: Карбюратор — это тебе не шаурма, Макс. Тут думать надо.',
              'Вано: Гога опять ключ на семнадцать посеял.',
              'Вано: Будет дело — скажу. Пока гуляй.'])
    b.person('goga', make_look(model='m_grey_h2b', scale=0.98), 1.15, 5.0, 180.0, ('idle', 'arms', 'texting'), 'Гога',
             ['Гога: Не стой над душой, а?', 'Гога: Вано сегодня злой. Запчасти не привезли.'])
    b.spot('talk', 4.3, 3.3, 30.0)


def room_rosa(b):
    """Бар «У Розы»."""
    b.shell(11.0, 8.2, 3.2, ('int_checker', 1.2, (0.86, 0.82, 0.8, 1.0)), ('int_wall', 1.8, (0.50, 0.16, 0.18, 1.0)),
            wainscot=('int_panel', 1.2, (0.62, 0.5, 0.46, 1.0), 1.1), light='dim', title='Бар «У Розы»',
            ceil=('int_wooddark', 2.0, (0.5, 0.45, 0.42, 1.0)))
    b.door('s', 1.5, 'int_door_shop', main=True)
    b.window('s', 4.2, 1.6, 1.1, 1.2, 'int_window_ind', (0.2, 0.14, 0.12, 1.0))
    b.window('s', 7.4, 1.6, 1.1, 1.2, 'int_window_ind', (0.2, 0.14, 0.12, 1.0))
    # стойка и полки с бутылками
    b.counter(3.2, 5.7, 9.6, 6.3, 1.1)
    b.shelf('n', 3.2, 9.8, 0.0, 0.95, 'int_wooddark', (1.2, 1.2), 0.45)
    b.shelf('n', 3.2, 9.8, 1.15, 2.55, 'int_bottles', (1.6, 0.7), 0.3)
    b.picture('n', 6.5, 2.62, 2.6, 0.5, 'sign_rosa', None, True)
    for x in (3.8, 4.7, 7.3, 8.2, 9.1):
        b.stool(x, 5.25)
    b.put('coffee', 9.2, 6.0, 180, 1.1, solid=False, scale=0.8)
    b.put('cup', 4.4, 5.95, 0, 1.1, solid=False)
    b.put('cup', 7.6, 6.0, 0, 1.1, solid=False)
    # столики
    for (x, y) in ((1.4, 3.6), (4.6, 2.6), (7.6, 2.9)):
        b.put('table_round', x, y)
    b.put('chair_slat', 0.7, 3.6, 90)
    b.put('chair_slat', 2.1, 3.6, 270)
    b.put('chair_slat', 4.6, 3.3, 0)
    b.put('chair_slat', 3.9, 2.6, 90)
    b.put('chair_slat', 7.6, 2.2, 180)
    b.put('chair_slat', 8.3, 2.9, 270)
    b.put('sofa_brown', 0.5, 6.4, 90)
    b.put('table_dark', 1.35, 6.4)
    # бильярд
    b.box(9.0, 0.9, 10.3, 3.3, 0.0, 0.82, 'int_wooddark', WHITE, 1.0, top_key='int_carpet',
          top_color=(0.16, 0.5, 0.26, 1.0))
    b.cabinet(10.7, 4.6, 270, 0.9, 0.6, 1.5, 'int_drinks', (0.5, 0.12, 0.3, 1.0), (0, 0.45, 1, 1))
    b.picture('w', 2.2, 1.4, 0.8, 1.0, 'int_poster_b')
    b.picture('w', 4.9, 1.5, 0.7, 0.9, 'int_poster_a')
    b.picture('e', 6.6, 1.6, 1.2, 0.5, 'sign_beer', BLACK, True)
    for (x, y) in ((2.6, 3.0), (6.4, 4.4), (9.6, 2.1)):
        b.lamp(x, y, 'pendant', (1.0, 0.72, 0.45), 2.6, 0.55)
    b.person('rosa', None, 6.0, 6.95, -90.0, ('arms', 'idle', 'listen'), 'Роза',
             ['Роза: Наливать не буду — тебе ещё за руль.', 'Роза: Тихо сегодня. Не люблю, когда тихо.',
              'Роза: Заходи, когда будут новости, красавчик.'])
    b.person('guest1', make_look(model='m_grey_h4'), 0.7, 3.6, 0.0, ('sit', 'sit_talk'), sit=True)
    b.person('guest2', make_look(model='f_black', female=True), 2.1, 3.6, 180.0, ('sit', 'sit'), sit=True)
    b.person('guest3', make_look(model='m_red_h2c'), 9.6, 4.0, -90.0, ('dance_a', 'dance_b', 'drink'))
    b.spot('talk', 6.0, 4.9, 90.0)


def room_prof(b):
    """Кабинет Профа на верхнем этаже башни."""
    b.shell(10.5, 8.5, 3.3, ('int_parquet', 2.2, (0.78, 0.7, 0.64, 1.0)), ('int_paper', 1.4, (0.30, 0.42, 0.36, 1.0)),
            wainscot=('int_panel', 1.2, (0.52, 0.42, 0.38, 1.0), 1.2), light='warm', title='Кабинет Профа')
    b.door('s', 5.25, 'int_door', main=True)
    for u in (2.2, 5.25, 8.3):
        b.window('n', u, 2.0, 1.9, 0.7)
    b.rug(5.25, 4.4, 3.4, 5.0, 'int_rug', (0.8, 0.85, 1.0, 1.0))
    b.desk(5.25, 6.3, 0, 2.2, 0.95, 0.78)
    b.put('armchair_tall', 5.25, 7.25, 0)
    b.put('chair_soft', 4.5, 5.2, 180)
    b.put('chair_soft', 6.0, 5.2, 180)
    b.put('lamp_table', 6.1, 6.35, 0, 0.78, solid=False)
    b.cabinet(4.5, 6.4, 20, 0.42, 0.06, 0.32, 'int_screen', BLACK, z0=0.8, solid=False, unlit=True)
    b.shelf('w', 2.4, 7.6, 0.0, 2.4, 'int_books', (0.8, 0.8), 0.38)
    b.put('sofa_black', 9.9, 4.2, 270)
    b.put('armchair_dark', 8.6, 2.5, 30)
    b.put('table_dark', 8.9, 4.2)
    b.put('lamp_floor', 9.9, 6.1)
    b.put('plant_tall', 0.6, 0.6)
    b.put('plant_tall', 9.9, 0.6)
    b.picture('e', 2.4, 1.4, 1.2, 0.9, 'int_notice', DARKWOOD)
    b.picture('s', 2.4, 1.35, 1.7, 1.7, 'map', DARKWOOD)
    b.picture('s', 8.3, 1.4, 1.1, 1.1, 'int_vault', BLACK)
    b.put('painting_wide', 10.44, 4.2, 270, 1.5, solid=False, scale=0.8)
    b.lamp(5.25, 4.2, 'pendant', (1.0, 0.86, 0.62), 3.6, 0.45)
    b.person('prof', None, 5.25, 7.2, -90.0, ('sit', 'write', 'sit'), 'Проф',
             ['Проф: У меня мало времени, молодой человек.', 'Проф: Аккуратность — вежливость профессионалов.'],
             sit=True)
    b.person('guard', make_look(model='m_leather_c', scale=1.05), 6.6, 0.8, 110.0, ('arms', 'idle'), 'Охранник',
             ['Охранник: Руки на виду. И без резких движений.'])
    b.spot('talk', 5.25, 4.6, 90.0)


def room_boss(b):
    """Казино «Фортуна»: игорный зал, стойка и угол босса с охраной."""
    b.shell(13.0, 9.6, 3.4, ('int_carpet', 2.4, (0.42, 0.14, 0.16, 1.0)), ('int_paper', 1.4, (0.26, 0.20, 0.30, 1.0)),
            wainscot=('int_wooddark', 1.4, WHITE, 1.2), light='dim', title='Казино «Фортуна»',
            ceil=('int_wooddark', 2.0, (0.45, 0.42, 0.40, 1.0)))
    b.door('s', 6.5, 'int_door_shop', main=True)
    # игорные столы: зелёное сукно
    for (x, y) in ((2.6, 3.2), (2.6, 6.2)):
        # тумба уже столешницы: под свесом помещаются колени игроков
        b.box(x - 0.8, y - 0.4, x + 0.8, y + 0.4, 0.0, 0.7, 'int_wooddark', WHITE, 1.0, solid=False)
        b.box(x - 1.15, y - 0.75, x + 1.15, y + 0.75, 0.7, 0.8, 'int_wooddark', WHITE, 1.0, top_key='int_carpet',
              top_color=(0.14, 0.46, 0.24, 1.0), solid=False, faces='xXyYZz')
        b.solid(x - 1.15, y - 0.75, x + 1.15, y + 0.75, 0.8)
        b.stool(x - 0.6, y - 1.15, h=0.5)
        b.stool(x + 0.6, y - 1.15, h=0.5)
        b.stool(x - 0.6, y + 1.15, h=0.5)
        b.put('cup', x + 0.4, y + 0.1, 0, 0.8, solid=False)
    # стойка с бутылками у восточной стены
    b.counter(10.3, 1.4, 10.9, 5.2, 1.1)
    b.shelf('e', 1.4, 5.2, 0.0, 0.95, 'int_wooddark', (1.2, 1.2), 0.45)
    b.shelf('e', 1.4, 5.2, 1.15, 2.55, 'int_bottles', (1.6, 0.7), 0.3)
    for y in (2.0, 3.3, 4.6):
        b.stool(9.68, y)
    # угол босса: диван, столик, кресла напротив
    b.rug(6.5, 7.3, 3.2, 4.6, 'int_rug', (1.0, 0.82, 0.7, 1.0))
    b.put('sofa_black', 6.5, 8.9, 0)
    b.put('table_dark', 6.5, 7.6)
    b.put('armchair_dark', 4.9, 7.2, 60)
    b.put('armchair_dark', 8.1, 7.2, -60)
    b.put('lamp_floor', 8.6, 9.0)
    b.put('plant_tall', 0.6, 9.0)
    b.put('plant_tall', 12.4, 9.0)
    b.put('plant_tall', 12.4, 0.6)
    b.cabinet(0.33, 0.9, 90, 1.0, 0.6, 1.9, 'int_drinks', (0.4, 0.12, 0.32, 1.0), (0, 0.45, 1, 1))
    b.picture('n', 2.6, 1.6, 1.6, 1.0, 'int_vault', BLACK)
    b.picture('n', 10.6, 1.6, 1.4, 1.0, 'int_poster_b')
    b.picture('w', 4.8, 1.5, 1.2, 0.5, 'sign_casino', BLACK, True)
    for (x, y) in ((2.6, 3.2), (2.6, 6.2), (6.5, 7.4), (9.6, 3.3)):
        b.lamp(x, y, 'pendant', (1.0, 0.8, 0.5), 2.6, 0.5)
    b.person('boss', None, 6.5, 8.75, -90.0, ('sit', 'sit_talk', 'sit'), 'Босс',
             ['Босс: Без дела сюда не ходят.', 'Босс: Время — деньги. Мои деньги.'], sit=True)
    b.person('guard_a', make_look(model='m_leather_b', scale=1.06), 4.4, 8.9, -70.0, ('arms', 'idle'), 'Охранник',
             ['Охранник: Близко не подходи.'])
    b.person('guard_b', make_look(model='m_shirt_h3b', scale=1.04), 8.9, 8.2, -110.0, ('arms', 'idle'), 'Охранник',
             ['Охранник: Смотри, но руками не трогай.'])
    b.person('dealer', make_look(model='m_shirt_c'), 2.6, 4.25, -90.0, ('idle', 'arms', 'listen'), 'Крупье',
             ['Крупье: Ставки сделаны.', 'Крупье: Заведение всегда в плюсе.'])
    b.person('player1', make_look(model='m_old_h3'), 2.0, 2.05, 90.0, ('sit', 'sit_talk'), sit=True)
    b.person('player2', make_look(model='f_goth', female=True), 9.68, 3.3, 0.0, ('sit', 'sit'), sit=True)
    b.spot('talk', 6.5, 5.9, 90.0)
    b.spot('side', 5.5, 6.1, 80.0)


def room_guns(b):
    """Оружейный магазин."""
    b.shell(8.0, 6.6, 3.0, ('int_tile', 1.0, (0.78, 0.76, 0.72, 1.0)), ('int_wall', 1.6, (0.50, 0.54, 0.46, 1.0)),
            wainscot=('int_panel', 1.2, (0.46, 0.4, 0.36, 1.0), 1.0), light='work', title='Оружейный магазин')
    b.door('s', 1.3, 'int_door_shop', main=True)
    b.window('s', 4.6, 2.4, 1.3, 1.0, 'int_window_ind', (0.2, 0.2, 0.22, 1.0))
    b.counter(1.4, 3.9, 8.0, 4.5, 1.02, 'int_panel')
    b.picture('n', 2.3, 1.1, 2.6, 1.3, 'int_gunwall', BLACK)
    b.picture('n', 5.7, 1.1, 2.6, 1.3, 'int_gunwall', BLACK)
    b.shelf('n', 0.6, 7.4, 0.0, 0.95, 'crate', (0.6, 0.6), 0.4, (0.24, 0.26, 0.22, 1.0))
    b.picture('e', 5.5, 1.3, 1.2, 0.6, 'sign_guns', BLACK)
    b.picture('w', 2.2, 1.3, 0.8, 1.0, 'int_poster_a')
    b.crate(7.2, 0.7, 0.8, 5)
    b.crate(7.25, 0.7, 0.55, 40, 0.8)
    b.crate(6.2, 0.6, 0.6, 0)
    b.barrel(0.5, 3.2, (0.25, 0.3, 0.2, 1.0))
    b.cabinet(0.35, 5.6, 90, 1.0, 0.5, 1.9, 'int_panel', (0.2, 0.22, 0.2, 1.0), (0, 0, 2, 2))
    b.put('microwave_steel', 6.9, 4.2, 180, 1.02, solid=False, scale=0.7)
    for (x, y) in ((2.6, 2.2), (5.6, 2.2), (4.0, 5.4)):
        b.lamp(x, y, 'tube', (0.92, 0.95, 1.0), 3.0, 0.38)
    b.person('seller', make_look(model='m_shirt_h3b', scale=1.02), 4.6, 5.2, -90.0, ('arms', 'idle'), 'Продавец',
             ['Продавец: Смотри, выбирай. Руками не лапать.', 'Продавец: Товар проверенный. Жалоб не поступало.'])
    b.spot('shop', 4.6, 3.1, 90.0)


def room_police(b):
    """Дежурная часть."""
    b.shell(11.0, 8.0, 3.2, ('int_tilew', 1.0, (0.72, 0.74, 0.78, 1.0)), ('int_wall', 1.6, (0.86, 0.84, 0.76, 1.0)),
            wainscot=('int_wall', 1.6, (0.34, 0.44, 0.60, 1.0), 1.3), base=BLACK, light='cold',
            title='Полицейский участок')
    b.door('s', 5.5, 'int_door', main=True)
    b.window('s', 2.2, 1.4, 1.3, 1.0, 'int_window_ind', (0.25, 0.27, 0.3, 1.0))
    b.window('s', 8.8, 1.4, 1.3, 1.0, 'int_window_ind', (0.25, 0.27, 0.3, 1.0))
    b.counter(2.6, 5.0, 7.4, 5.6, 1.1, 'int_panel')
    b.picture('n', 5.0, 2.3, 2.6, 0.5, 'int_sign_duty', None)
    b.cabinet(4.2, 5.3, 180, 0.42, 0.06, 0.32, 'int_screen', BLACK, z0=1.12, solid=False, unlit=True)
    b.desk(5.0, 6.9, 0, 1.5, 0.7)
    b.put('chair_office', 5.0, 7.5, 0)
    for k in range(4):
        b.cabinet(0.33, 5.9 + k * 0.52, 90, 0.5, 0.6, 1.3, 'int_filing', (0.3, 0.32, 0.34, 1.0))
    b.bench(0.35, 2.4, 90, 2.4)
    b.picture('w', 4.4, 1.3, 1.3, 1.3, 'int_wanted', None)
    b.picture('e', 1.6, 1.3, 1.2, 0.9, 'int_board', None)
    b.picture('s', 7.0, 1.4, 0.9, 0.8, 'int_notice', BLACK)
    # камера
    b.bars(8.2, 4.6, 11.0, 4.6)
    b.bars(8.2, 4.6, 8.2, 8.0)
    b.put('bed_cot', 10.4, 6.8, 0)
    b.put('toilet', 8.75, 7.55, 0)
    b.put('chair_plastic', 9.6, 0.5, 180)
    b.put('chair_plastic', 10.2, 0.5, 180)
    b.put('plant_a', 0.6, 0.6)
    for (x, y) in ((3.0, 2.6), (8.0, 2.6), (5.0, 6.4)):
        b.lamp(x, y, 'tube', (0.9, 0.95, 1.0), 3.4, 0.36)
    b.person('duty', cop_look(), 5.0, 6.15, -90.0, ('arms', 'idle', 'write'), 'Дежурный',
             ['Дежурный: Заявление — в письменном виде, в трёх экземплярах.',
              'Дежурный: Гражданин, не задерживайте. Следующий!',
              'Дежурный: Машину угнали? У всех угнали.'])
    b.person('jail', gang_look('reds'), 9.4, 6.0, -100.0, ('angry', 'arms', 'tired'), 'Задержанный',
             ['Задержанный: Начальник, я вообще мимо шёл!', 'Задержанный: Эй, брат, закурить есть?'])
    b.person('cop2', cop_look(), 9.3, 3.2, 150.0, ('idle', 'phone'), 'Сержант',
             ['Сержант: Проходим, не толпимся.'])
    b.spot('desk', 5.0, 4.2, 90.0)


def room_hospital(b):
    """Приёмный покой больницы."""
    b.shell(10.0, 7.6, 3.2, ('int_tilew', 1.0, WHITE), ('int_wall', 1.6, (0.92, 0.93, 0.90, 1.0)),
            wainscot=('int_wall', 1.6, (0.62, 0.80, 0.72, 1.0), 1.2), base=(0.5, 0.5, 0.5, 1.0), light='cold',
            title='Больница')
    b.door('s', 5.0, 'int_door', main=True)
    b.window('s', 2.0, 1.4, 1.4, 0.9)
    b.window('s', 8.0, 1.4, 1.4, 0.9)
    b.counter(0.9, 4.9, 4.6, 5.5, 1.1, 'int_panel', 'int_marble', (0.8, 0.9, 0.86, 1.0))
    b.picture('n', 2.7, 2.2, 2.6, 0.5, 'int_sign_reg', None)
    b.picture('n', 6.4, 1.5, 0.9, 0.9, 'emblem_cross', (0.8, 0.8, 0.8, 1.0))
    b.cabinet(2.0, 5.2, 180, 0.42, 0.06, 0.32, 'int_screen', BLACK, z0=1.12, solid=False, unlit=True)
    b.shelf('n', 0.5, 4.6, 0.0, 1.9, 'int_filing', (0.5, 0.95), 0.4, (0.8, 0.82, 0.8, 1.0))
    for k in range(4):
        b.put('chair_plastic', 9.55, 2.0 + k * 0.62, 270)
    b.put('table_small', 9.5, 4.9)
    b.put('plant_a', 9.4, 6.9)
    b.put('plant_c', 0.6, 0.6)
    b.cabinet(9.2, 0.42, 180, 0.9, 0.7, 1.9, 'int_drinks', (0.8, 0.1, 0.1, 1.0))
    b.cabinet(6.9, 0.42, 180, 0.9, 0.7, 1.9, 'int_snacks', (0.2, 0.3, 0.6, 1.0))
    b.put('bed_cot', 7.4, 6.4, 90)
    b.picture('e', 5.6, 1.3, 1.0, 0.9, 'int_notice', (0.8, 0.8, 0.8, 1.0))
    b.picture('w', 2.6, 1.3, 1.1, 0.9, 'int_board', None)
    for (x, y) in ((3.0, 2.6), (7.0, 2.6), (5.0, 5.8)):
        b.lamp(x, y, 'tube', (0.92, 0.97, 1.0), 3.4, 0.36)
    b.person('nurse', medic_look(), 2.9, 6.1, -90.0, ('write', 'idle', 'arms'), 'Медсестра',
             ['Медсестра: Полис, паспорт, бахилы.', 'Медсестра: Доктор принимает до шести. Но перевязать могу.'])
    b.person('patient', make_look(model='m_old_h3'), 9.55, 2.62, 180.0, ('sit', 'sit'), sit=True)
    b.person('patient2', make_look(model='f_old_b', female=True), 9.55, 3.86, 180.0, ('sit', 'sit_talk'), sit=True)
    b.spot('heal', 2.9, 4.2, 90.0)


def room_bank(b):
    """Операционный зал банка."""
    b.shell(12.0, 8.6, 3.6, ('int_marble', 2.0, (0.92, 0.9, 0.86, 1.0)), ('int_wall', 1.8, (0.88, 0.84, 0.72, 1.0)),
            wainscot=('int_wooddark', 1.4, WHITE, 1.25), light='warm', title='Городской банк')
    b.door('s', 6.0, 'int_door_shop', 1.2, 2.2, main=True)
    b.window('s', 2.4, 1.6, 1.8, 0.8)
    b.window('s', 9.6, 1.6, 1.8, 0.8)
    b.counter(0.0, 5.6, 12.0, 6.2, 1.15, 'int_wooddark')
    # стекло над стойкой
    b.begin(6.0, 5.9, 0.0)
    for k in range(6):
        x0 = k * 2.0
        b.cur.box(None, x0 - 0.03, 5.87, 1.15, x0 + 0.03, 5.93, 2.3, DARKWOOD, 'xXyY')
        b.cur.quad2(('white', 'glass'), (x0 + 0.03, 5.9, 1.45), (x0 + 1.97, 5.9, 1.45), (x0 + 1.97, 5.9, 2.3),
                    (x0 + 0.03, 5.9, 2.3), color=(0.7, 0.86, 0.9, 0.22))
    b.cur.box(None, 0.0, 5.86, 2.3, 12.0, 5.94, 2.38, DARKWOOD, 'xXyYZz')
    b.end()
    for u in (3.0, 9.0):
        b.picture('n', u, 2.5, 1.6, 0.4, 'int_sign_cash', None)
    b.picture('n', 6.0, 0.6, 1.9, 1.9, 'int_vault', BLACK)
    for x in (2.2, 9.8):
        b.desk(x, 7.4, 0, 1.4, 0.6)
    b.column(3.6, 3.2)
    b.column(8.4, 3.2)
    b.put('sofa_light', 0.5, 2.6, 90)
    b.put('table_small', 1.4, 2.6)
    b.put('sofa_light', 11.5, 2.6, 270)
    b.put('plant_tall', 0.6, 0.6)
    b.put('plant_tall', 11.4, 0.6)
    b.put('plant_tall', 0.6, 5.0)
    b.put('plant_tall', 11.4, 5.0)
    b.picture('w', 4.0, 1.5, 1.2, 0.9, 'int_notice', DARKWOOD)
    b.put('painting_c', 11.94, 3.9, 270, 1.6, solid=False)
    b.rug(6.0, 3.0, 2.2, 4.4, 'int_rug', (0.75, 0.9, 0.8, 1.0))
    for (x, y) in ((3.0, 2.8), (9.0, 2.8), (6.0, 4.6)):
        b.lamp(x, y, 'pendant', (1.0, 0.9, 0.7), 3.6, 0.42)
    b.person('teller1', make_look(model='f_old', female=True), 3.0, 6.75, -90.0, ('write', 'idle'), 'Кассир',
             ['Кассир: Окно закрыто на технический перерыв.', 'Кассир: Вклад «Надёжный»: три процента и наше слово.'])
    b.person('teller2', make_look(model='m_shirt_h4'), 9.0, 6.75, -90.0, ('idle', 'write', 'arms'), 'Кассир',
             ['Кассир: Без паспорта не обслуживаем.'])
    b.person('guard', make_look(model='m_shirt_c', scale=1.04), 7.4, 0.9, 100.0, ('arms', 'idle'), 'Охранник',
             ['Охранник: Проходите, не задерживайтесь у дверей.'])
    b.person('client1', make_look(model='m_shirt_b'), 3.0, 4.9, 90.0, ('arms', 'phone', 'idle'))
    b.person('client2', make_look(model='f_goth', female=True), 9.0, 4.9, 90.0, ('texting', 'idle'))
    b.spot('teller', 6.0, 4.8, 90.0)


def room_zakhar(b):
    """Лодочный сарай Захара в Нефтегавани."""
    b.shell(11.0, 8.5, 4.0, ('int_planks', 2.4, (0.62, 0.6, 0.58, 1.0)), ('int_panel', 1.6, (0.50, 0.46, 0.42, 1.0)),
            base=BLACK, light='dim', title='Сарай Захара', ceil=('corrugated', 3.0, (0.42, 0.42, 0.44, 1.0)))
    b.door('s', 1.3, 'int_door_old', main=True)
    b.picture('s', 6.6, 0.0, 4.2, 3.0, 'corrugated', BLACK, t=0.12)
    b.window('n', 2.5, 2.0, 1.0, 2.6, 'int_window_ind', (0.2, 0.2, 0.22, 1.0))
    b.window('n', 8.5, 2.0, 1.0, 2.6, 'int_window_ind', (0.2, 0.2, 0.22, 1.0))
    # лодка на козлах: корпус из досок
    mb = b.mb
    hull = (0.30, 0.42, 0.50, 1.0)
    for (x0, x1, w0, w1) in ((4.6, 6.0, 0.25, 0.75), (6.0, 8.6, 0.75, 0.8), (8.6, 9.2, 0.8, 0.62)):
        mb.quad('int_planks', (x0, 4.3 - w0 * 0.4, 0.55), (x1, 4.3 - w1 * 0.4, 0.55), (x1, 4.3 - w1, 1.3),
                (x0, 4.3 - w0, 1.3), color=hull)
        mb.quad('int_planks', (x1, 4.3 + w1 * 0.4, 0.55), (x0, 4.3 + w0 * 0.4, 0.55), (x0, 4.3 + w0, 1.3),
                (x1, 4.3 + w1, 1.3), color=hull)
        mb.quad('int_planks', (x0, 4.3 - w0 * 0.4, 0.55), (x0, 4.3 + w0 * 0.4, 0.55), (x1, 4.3 + w1 * 0.4, 0.55),
                (x1, 4.3 - w1 * 0.4, 0.55), color=(0.2, 0.22, 0.24, 1.0))
        mb.quad('int_planks', (x1, 4.3 - w1 * 0.4, 0.6), (x1, 4.3 + w1 * 0.4, 0.6), (x0, 4.3 + w0 * 0.4, 0.6),
                (x0, 4.3 - w0 * 0.4, 0.6), color=(0.5, 0.44, 0.36, 1.0))
    mb.quad('int_planks', (9.2, 4.3 + 0.62, 1.3), (9.2, 4.3 - 0.62, 1.3), (9.2, 4.3 - 0.25, 0.55),
            (9.2, 4.3 + 0.25, 0.55), color=hull)
    for x in (5.6, 8.2):
        mb.box('int_planks', x - 0.06, 3.5, 0.0, x + 0.06, 5.1, 0.55, (0.5, 0.42, 0.32, 1.0), 'xXyYZ', 1.0)
    b.solid(4.7, 3.55, 9.2, 5.05, 1.3)
    b.counter(0.0, 3.4, 0.8, 6.4, 0.9, 'int_panel', 'int_planks')
    b.picture('w', 4.9, 1.2, 2.4, 1.2, 'int_tools', BLACK)
    b.barrel(0.5, 7.9, (0.5, 0.2, 0.12, 1.0))
    b.barrel(1.2, 8.0, (0.16, 0.3, 0.4, 1.0))
    b.crate(2.3, 7.95, 0.8, 10)
    b.crate(3.2, 7.9, 0.7, -8)
    b.crate(2.6, 7.95, 0.55, 25, 0.8)
    b.tyres(10.4, 0.6, 3)
    # жилой угол
    b.table(9.0, 7.3, 1.2, 0.8, 0.74, 'int_planks')
    b.put('chair_wood', 9.0, 8.05, 0)
    b.put('chair_wood', 8.0, 7.3, 90)
    b.put('cup', 9.2, 7.3, 0, 0.74, solid=False)
    b.put('lamp_table', 8.7, 7.45, 0, 0.74, solid=False)
    b.put('sofa_old', 10.5, 5.2, 270)
    b.put('stove_old', 10.5, 3.4, 270)
    b.picture('e', 7.3, 1.4, 1.5, 1.5, 'map', DARKWOOD)
    b.picture('n', 5.5, 1.4, 0.8, 1.0, 'int_poster_a')
    for (x, y) in ((3.2, 3.0), (7.2, 3.2), (8.8, 6.6)):
        b.lamp(x, y, 'bulb', (1.0, 0.8, 0.5), 3.0, 0.5)
    b.person('zakhar', None, 9.0, 8.0, -90.0, ('sit', 'drink', 'sit'), 'Захар',
             ['Захар: Море, оно всё помнит. И я помню.', 'Захар: Чаю хочешь? Другого не держу. Теперь.'], sit=True)
    b.spot('talk', 8.1, 6.1, 55.0)


def room_grom(b):
    """Чайная в Заречье, где принимает майор Гром."""
    b.shell(9.5, 7.2, 3.0, ('int_checker', 1.0, (0.9, 0.86, 0.78, 1.0)), ('int_paper', 1.2, (0.86, 0.72, 0.52, 1.0)),
            wainscot=('int_panel', 1.2, (0.7, 0.6, 0.52, 1.0), 1.0), light='warm', title='Чайная «Заречье»')
    b.door('s', 1.3, 'int_door_shop', main=True)
    b.window('s', 4.0, 1.6, 1.4, 0.9)
    b.window('s', 7.0, 1.6, 1.4, 0.9)
    b.counter(0.0, 4.9, 3.4, 5.5, 1.05, 'int_panel')
    b.shelf('n', 0.3, 3.4, 0.0, 0.9, 'int_panel', (1.0, 1.0), 0.4)
    b.shelf('n', 0.3, 3.4, 1.1, 2.3, 'int_bottles', (1.6, 0.7), 0.28)
    b.mb.cylinder(None, 0.9, 5.2, 1.05, 1.5, 0.16, 10, (0.86, 0.66, 0.24, 1.0), r_top=0.13)       # самовар
    b.mb.cylinder(None, 0.9, 5.2, 1.5, 1.66, 0.06, 8, (0.86, 0.66, 0.24, 1.0))
    b.put('cup', 1.5, 5.2, 0, 1.05, solid=False)
    b.put('cup', 2.2, 5.15, 0, 1.05, solid=False)
    for (x, y) in ((5.2, 2.4), (8.0, 1.9), (5.2, 5.4)):
        b.table(x, y, 0.9, 0.9, 0.74, 'int_planks')
        b.put('chair_wood', x, y + 0.85, 0)
        b.put('chair_wood', x, y - 0.85, 180)
    b.table(8.2, 5.7, 1.3, 0.9, 0.74, 'int_planks')
    b.put('chair_soft', 8.2, 6.6, 0)
    b.put('cup', 8.4, 5.7, 0, 0.74, solid=False)
    b.put('dish', 8.0, 5.75, 0, 0.74, solid=False)
    b.tv(9.4, 3.6, 270, 1.7, 1.0, 0.62)
    b.picture('w', 2.6, 1.3, 1.0, 0.8, 'int_notice', DARKWOOD)
    b.put('painting_a', 4.8, 7.14, 0, 1.4, solid=False, scale=0.8)
    b.put('plant_b', 9.0, 0.5)
    b.put('plant_a', 0.5, 0.5)
    for (x, y) in ((2.2, 2.6), (6.6, 2.6), (6.6, 5.4)):
        b.lamp(x, y, 'pendant', (1.0, 0.86, 0.6), 3.0, 0.45)
    b.person('grom', None, 8.2, 6.55, -90.0, ('sit', 'drink', 'sit_talk'), 'Майор Гром',
             ['Гром: Сядь, не маячь. Чай тут хороший.', 'Гром: В этом городе всё решается за этим столом.'], sit=True)
    b.person('waitress', make_look(model='f_old_c', female=True), 1.8, 6.2, -90.0, ('idle', 'arms', 'write'),
             'Буфетчица', ['Буфетчица: Пирожки с капустой кончились. С повидлом берите.'])
    b.person('tea1', make_look(model='m_shirt_h4b'), 5.2, 3.2, -90.0, ('sit', 'drink'), sit=True)
    b.person('tea2', make_look(model='m_shirt_h3'), 5.2, 1.6, 90.0, ('sit_talk', 'sit'), sit=True)
    b.spot('talk', 8.2, 4.35, 90.0)


# имя комнаты -> (функция, особое место на карте)
ROOMS = [
    ('safehouse', room_safehouse, 'safehouse'),
    ('vano', room_vano, 'vano'),
    ('rosa', room_rosa, 'rosa'),
    ('prof', room_prof, 'prof'),
    ('guns', room_guns, 'guns'),
    ('guns2', room_guns, 'guns2'),
    ('police', room_police, 'police'),
    ('hospital', room_hospital, 'hospital'),
    ('bank', room_bank, 'bank'),
    ('zakhar', room_zakhar, 'zakhar'),
    ('grom', room_grom, 'grom'),
    ('boss', room_boss, 'boss'),
]
DOOR_TEX = {'safehouse': 'int_door_old', 'vano': 'int_door_metal', 'rosa': 'int_door_shop', 'prof': 'int_door',
            'guns': 'int_door_shop', 'guns2': 'int_door_metal', 'police': 'int_door', 'hospital': 'int_door',
            'bank': 'int_door_shop', 'zakhar': 'int_door_old', 'grom': 'int_door_shop', 'boss': 'int_door_shop'}


class Interiors(object):

    def __init__(self, world):
        self.w = world
        self.root = world.render.attachNewNode('interiors')
        self.rooms = {}
        self.order = []
        self.current = None
        self.trans = None               # идёт переход через дверь: [вид, комната, время, сделано]
        self.msg_cd = 0.0
        self.cinema = False             # идёт сценка: стрелки у дверей не показываем
        self.people = []                # жильцы всех комнат
        self.cars = []
        self.talk_cd = 0.0
        self._act_t = 0.0
        self.doors_np = None
        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        w = self.w
        c = w.city
        dmb = MeshBuilder()
        k = 0
        for (name, fn, lmk) in ROOMS:
            lm = c.landmarks.get(lmk)
            if lm is None or lm.get('facing', 's') != 's':
                continue
            room = Room(name, k)
            k += 1
            room.landmark = lmk
            b = Builder(w, room)
            fn(b)
            b.finish(w.assets, w.static, self.root)
            zone = 'int_' + name
            city_mod.ZONE_NAMES[zone] = room.title
            c._pad(room.ox - PAD, room.oy - PAD, room.ox + room.w + PAD, room.oy + room.d + PAD, 0.0, zone)
            # дверь на улице
            x0, y0, x1, y1 = lm['rect']
            ex = lm['door'][0]
            if lm.get('yard') is not None:                      # склад: дверь между воротами
                n = max(1, int((x1 - x0) // 14))
                ex = x0 + (x1 - x0) / n if n > 1 else (x0 + x1) * 0.5 + 4.6
            room.wall_y = y0
            room.out = (ex, y0 - 0.6)
            room.out_pos = (ex, y0 - 1.5, -math.pi / 2)
            gz = c.ground_z(ex, y0 - 0.6)
            tex = DOOR_TEX.get(name, 'int_door')
            bay = c.entry_bay(lmk) if lm.get('yard') is None else None
            bld = c.landmark_building(lmk)
            if bay is not None:
                self._entrance(dmb, bay[2], bay[1], bld, ex, y0, gz, tex)
            else:
                self._door(dmb, tex, ex, y0, gz, 0.6, 2.2)
                if bld is not None and bld.gf_h > 0.01:
                    # дверь в глухой стене склада: навес над ней
                    dmb.box(None, ex - 1.0, y0 - 0.8, gz + 2.42, ex + 1.0, y0, gz + 2.5, (0.2, 0.22, 0.26, 1.0), 'xXyZz')
            dmb.box('concrete', ex - 0.9, y0 - 0.5, gz - 0.1, ex + 0.9, y0, gz + 0.04, (0.7, 0.7, 0.7, 1.0), 'xXyZ', 1.0)
            self.rooms[name] = room
            self.order.append(room)
        self.doors_np = dmb.build('doors', w.assets.apply_state)
        self.doors_np.reparentTo(w.citymesh.root)

    @staticmethod
    def _door(dmb, tex, ex, y0, gz, hw, h, frame=(0.16, 0.14, 0.13, 1.0), t=0.12):
        """Дверь в раме на южной стене: полотно шириной 2*hw и высотой h."""
        dmb.box(None, ex - hw - t, y0 - 0.10, gz, ex + hw + t, y0 + 0.02, gz + h + t, frame, 'xXyZ')
        dmb.quad(tex, (ex - hw, y0 - 0.11, gz), (ex + hw, y0 - 0.11, gz), (ex + hw, y0 - 0.11, gz + h),
                 (ex - hw, y0 - 0.11, gz + h))

    def _entrance(self, dmb, ent, bw, bld, ex, y0, gz, tex):
        """Вход в проёме, нарисованном на плитке первого этажа (см. city.ENTRY_TILES)."""
        kind, _u, hwf, hf = ent
        hw = hwf * bw                               # полуширина проёма
        top = gz + hf * bld.gf_h                    # верх проёма
        dark = (0.15, 0.15, 0.17, 1.0)
        glass = (0.19, 0.25, 0.31, 1.0)
        if kind == 'shop':
            # стеклянная дверь витрины: рама во весь нарисованный проём, полотно и фрамуга над ним
            dmb.box(None, ex - hw, y0 - 0.10, gz, ex + hw, y0 + 0.02, top, dark, 'xXyZ')
            lw = hw - 0.07
            dmb.quad(tex, (ex - lw, y0 - 0.11, gz), (ex + lw, y0 - 0.11, gz), (ex + lw, y0 - 0.11, gz + 2.2),
                     (ex - lw, y0 - 0.11, gz + 2.2))
            dmb.quad(None, (ex - lw, y0 - 0.11, gz + 2.27), (ex + lw, y0 - 0.11, gz + 2.27),
                     (ex + lw, y0 - 0.11, top - 0.07), (ex - lw, y0 - 0.11, top - 0.07), color=glass)
        elif kind == 'office':
            # дверь на месте нижнего среднего стекла: рама в цвет переплётов и навес над входом
            metal = (0.62, 0.66, 0.72, 1.0)
            dmb.box(None, ex - hw, y0 - 0.10, gz, ex + hw, y0 + 0.02, top + 0.03, metal, 'xXyZ')
            lw = hw - 0.07
            dmb.quad(tex, (ex - lw, y0 - 0.11, gz), (ex + lw, y0 - 0.11, gz), (ex + lw, y0 - 0.11, top - 0.05),
                     (ex - lw, y0 - 0.11, top - 0.05))
            dmb.box(None, ex - hw - 0.5, y0 - 1.1, top + 0.2, ex + hw + 0.5, y0, top + 0.3, (0.24, 0.26, 0.3, 1.0),
                    'xXyZz')
            for sx in (-1, 1):                      # тяги навеса
                xa = ex + sx * (hw + 0.42)
                dmb.quad2(None, (xa, y0 - 1.05, top + 0.3), (xa, y0 - 0.02, top + 0.95), (xa + 0.03, y0 - 0.02, top + 0.95),
                          (xa + 0.03, y0 - 1.05, top + 0.3), color=dark)
        else:
            # гараж: ворота этой секции заложены кирпичом, в кладке — железная дверь, над ней фонарь
            w2 = hw * 2.0
            hgt = top - gz
            dmb.quad(bld.blank_tex, (ex - hw, y0 - 0.05, gz), (ex + hw, y0 - 0.05, gz), (ex + hw, y0 - 0.05, top),
                     (ex - hw, y0 - 0.05, top), (0, 0, w2 / 4.0, hgt / 4.0),
                     tuple(bld.blank_tint) + (1.0,) if len(bld.blank_tint) == 3 else bld.blank_tint)
            for (xa, xb) in ((ex - hw, ex - hw + 0.02), (ex + hw - 0.02, ex + hw)):
                dmb.box(None, xa, y0 - 0.05, gz, xb, y0, top, dark, 'xXy')
            dmb.box('concrete', ex - hw, y0 - 0.09, top - 0.22, ex + hw, y0, top, (0.62, 0.62, 0.6, 1.0), 'xXyZz', 2.0)
            self._door(dmb, tex, ex, y0, gz, 0.6, 2.2)
            dmb.box(None, ex - 0.13, y0 - 0.26, gz + 2.5, ex + 0.13, y0 - 0.05, gz + 2.62, dark, 'xXyZz')
            dmb.box((None, 'unlit'), ex - 0.1, y0 - 0.24, gz + 2.44, ex + 0.1, y0 - 0.07, gz + 2.5,
                    (1.0, 0.9, 0.62, 1.0), 'xXyz')

    def reset(self):
        """Новая игра: расставить жильцов, машины-декорации и стрелки у дверей."""
        w = self.w
        if self.current is not None:
            self._switch(None)
        self.trans = None
        self.cinema = False
        for p in self.people:
            if not p.removed:
                p.keep = False
                w.remove_ped(p)
        for v in self.cars:
            if not v.removed:
                v.keep = False
                w.remove_vehicle(v)
        self.people = []
        self.cars = []
        from .vehicle import Vehicle
        for room in self.order:
            for info in room.people:
                self._settle(room, info)
            for (kind, x, y, yaw, paint) in room.cars:
                v = w.spawn_vehicle(kind, x, y, yaw, paint)
                v.keep = True
                v.locked = True
                v.room = room.name
                v.mode = Vehicle.PARKED
                self.cars.append(v)
            for a in (room.arrow, room.arrow_in):
                if a is not None:
                    a.remove()
            room.arrow = Arrow(w, None, room.out[0], room.out[1], w.city.ground_z(*room.out) + 2.75, YELLOW)
            room.arrow.np.setScale(0.7)
            room.arrow_in = Arrow(w, None, room.exit[0], room.exit[1], 2.45, YELLOW)
            room.arrow_in.np.setScale(0.55)
            room.arrow_in.np.hide()

    def _settle(self, room, info):
        """Поставить жильца комнаты на его место."""
        from .missions import contact_look
        look = info['look'] or contact_look(info['key'])
        p = self.w.spawn_ped(info['x'], info['y'], info['yaw'], look, 'civ')
        p.keep = True
        p.fixed = True
        p.room = room.name
        p.resident = info
        p.money = 0
        p.set_state('stand')
        p.seat_dz = info.get('dz', 0.0)
        p.idle_clip = info['clips'][0]
        p.home = (info['x'], info['y'], info['yaw'])
        p._act_t = random.uniform(3.0, 9.0)
        self.people.append(p)
        return p

    def resident(self, key):
        for p in self.people:
            if p.resident['key'] == key and not p.removed:
                return p
        return None

    def ensure_resident(self, key):
        """Вернуть жильца на место, если его убрали (меню тестера переигрывает задания, где он ещё нужен)."""
        p = self.resident(key)
        if p is not None and not p.dead:
            return p
        if p is not None:
            p.keep = False
            self.w.remove_ped(p)
        for room in self.order:
            for info in room.people:
                if info['key'] == key:
                    return self._settle(room, info)
        return None

    # ------------------------------------------------------------------
    def room_at(self, x, y):
        if x < INT_X0 - 50.0:
            return None
        for r in self.order:
            if r.contains(x, y):
                return r
        return None

    def map_pos(self):
        """Где герой «на карте города»: у двери здания, внутри которого он находится."""
        r = self.current
        if r is None:
            return None
        return r.out[0], r.out[1]

    def _switch(self, room):
        """Вошли в комнату или вышли: поменять свет, скрыть или показать город."""
        w = self.w
        old = self.current
        if old is room:
            return
        self.current = room
        pl = w.player
        if old is not None:
            old.node.hide()
            old.arrow_in and old.arrow_in.np.hide()
            for (np_, x, y, r) in old.tall:
                np_.show()
        if room is not None:
            room.node.show()
            if room.arrow_in is not None:
                room.arrow_in.np.show()
            w.citymesh.root.hide()
            if w.sky is not None:
                w.sky.indoor = LIGHTS[room.light]
            pl.indoors = True
            pl.aiming = False
            pl.ped.set_weapon(W_FIST)
            k = 1.0 - 0.86 * (w.sky.night if w.sky is not None else 0.0)
            room.win_np.setColorScale(k, k, min(1.0, k * 1.25), 1.0)
            if w.hud is not None:
                w.hud.zone_name = None
        else:
            w.citymesh.root.show()
            if w.sky is not None:
                w.sky.indoor = None
            pl.indoors = False
            pl.ped.set_weapon(pl.weapon_id)
        if w.sky is not None:
            w.sky._apply(0.0)
        self.talk_cd = 2.0

    def locked_reason(self):
        """Почему сейчас нельзя войти (None — можно)."""
        w = self.w
        ms = w.missions
        if ms is not None and ms.active is not None:
            return 'Сейчас не до этого: сначала закончи дело.'
        if w.police.level > 0:
            return 'С полицией на хвосте в дверь не войдёшь. Сначала оторвись.'
        return None

    def enter(self, name, instant=False, spot=None):
        """Перенести героя в комнату (instant — сразу, без затемнения)."""
        room = self.rooms.get(name)
        if room is None:
            return False
        if instant:
            self._inside(room, spot)
        else:
            self._begin('enter', room)
        return True

    def leave(self, instant=False):
        room = self.current
        if room is None:
            return False
        if instant:
            self._outside(room)
        else:
            self._begin('leave', room)
        return True

    def _begin(self, kind, room):
        w = self.w
        self.trans = [kind, room, 0.0, False]
        w.player.freeze = True
        w.hud.fade(1.0, 4.5)
        w.audio.play('door', 0.6, 0.9)

    def _inside(self, room, spot=None):
        w = self.w
        x, y, yaw = room.spots[spot] if spot else room.entry
        w.player.teleport(x, y, yaw)
        self._switch(room)
        w.cam.pitch = -0.30
        w.cam.snap()

    def _outside(self, room):
        w = self.w
        x, y, yaw = room.out_pos
        self._switch(None)
        w.player.teleport(x, y, yaw)
        w.cam.pitch = -0.2

    # ------------------------------------------------------------------
    def update(self, dt):
        w = self.w
        pl = w.player
        p = pl.ped
        hud = w.hud
        on_foot = pl.vehicle is None and pl.state == 'foot'
        room = self.room_at(p.x, p.y) if pl.vehicle is None else None
        if room is not self.current:
            self._switch(room)                   # героя перенесли сценарием — подстраиваемся
        if self.msg_cd > 0.0:
            self.msg_cd -= dt
        tr = self.trans
        if tr is not None:
            tr[2] += dt
            if tr[2] >= 0.3 and not tr[3]:
                tr[3] = True
                if tr[0] == 'enter':
                    self._inside(tr[1])
                else:
                    self._outside(tr[1])
                hud.fade(0.0, 3.5)
            if tr[2] >= 0.5:
                self.trans = None
                pl.freeze = False
            return
        cur = self.current
        if cur is None:
            for r in self.order:
                a = r.arrow
                if a is None:
                    continue
                if abs(r.out[0] - p.x) < 90.0 and abs(r.out[1] - p.y) < 90.0 and not self.cinema:
                    a.update(dt)
                    if on_foot and not pl.freeze and abs(p.x - r.out[0]) < 0.8 and -1.3 < p.y - r.wall_y < 0.3:
                        why = self.locked_reason()
                        if why is None:
                            self._begin('enter', r)
                        elif self.msg_cd <= 0.0:
                            self.msg_cd = 4.0
                            hud.help(why, 3.5)
                else:
                    a.np.hide()
            return
        cur.arrow_in.update(dt)
        if self.cinema or (w.cam.x - cur.exit[0]) ** 2 + (w.cam.y - cur.exit[1]) ** 2 < 9.0:
            cur.arrow_in.np.hide()                  # вплотную к камере стрелка закрыла бы пол-экрана
        if on_foot and not pl.freeze and abs(p.x - cur.exit[0]) < 0.62 and p.y - cur.oy < 0.72:
            self._begin('leave', cur)
            return
        self._hide_tall(cur)
        self._people(cur, dt)

    def _hide_tall(self, room):
        """Спрятать высокие предметы, которые сейчас заслоняют героя от камеры."""
        w = self.w
        cam = w.cam
        p = w.player.ped
        ax, ay = cam.x, cam.y
        bx, by = p.x, p.y
        if cam.override is not None:
            for (np_, x, y, r) in room.tall:
                np_.show()
            return
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        for (np_, x, y, r) in room.tall:
            hide = False
            if l2 > 0.01:
                t = ((x - ax) * dx + (y - ay) * dy) / l2
                if -0.15 < t < 0.93:
                    t = min(1.0, max(0.0, t))
                    ex, ey = ax + dx * t - x, ay + dy * t - y
                    hide = ex * ex + ey * ey < (r + 0.3) ** 2
            if hide:
                np_.hide()
            else:
                np_.show()

    def _people(self, room, dt):
        """Жильцы меняют позы и подают голос, когда герой подходит."""
        w = self.w
        pl = w.player
        p = pl.ped
        self.talk_cd -= dt
        near = None
        for q in self.people:
            if q.room != room.name or q.removed or q.dead:
                continue
            info = q.resident
            q._act_t -= dt
            if q._act_t <= 0.0 and q.act is None:
                q._act_t = random.uniform(5.0, 11.0)
                q.idle_clip = random.choice(info['clips'])
            if info['lines'] and (q.x - p.x) ** 2 + (q.y - p.y) ** 2 < 4.4:
                near = q
        ms = w.missions
        busy = pl.freeze or (ms is not None and ms.active is not None)
        if near is not None and self.talk_cd <= 0.0 and not busy and not w.hud.sub_queue and w.hud.sub_t <= 0.0:
            self.talk_cd = 9.0
            w.hud.subtitle(random.choice(near.resident['lines']), 3.2, clear=True)
