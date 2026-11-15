# -*- coding: utf-8 -*-
"""Процедурный генератор города (только данные, без графики).

Город — остров с прямоугольной сеткой улиц.  Генератор детерминирован:
один и тот же seed всегда даёт один и тот же город, поэтому миссии могут
ссылаться на фиксированные места (гараж Вано, больница и т.д.).

Координаты: X — восток, Y — север, Z — вверх, единица = 1 метр.
"""
import math
from bisect import bisect_right

from .mathutil import Rng, clamp

# ---------------------------------------------------------------------------
# размеры
# ---------------------------------------------------------------------------
CURB = 0.15            # высота бордюра
SIDEWALK = 3.0         # ширина тротуара
LANE_W = 3.5           # ширина полосы
AVE_W = 14.0           # проспект: 4 полосы
ST_W = 12.0            # улица: 2 полосы + 2 парковочных кармана
PARK_STRIP = 2.5       # ширина парковочного кармана
CAP_LEN = 6.0          # участок с «зеброй» перед перекрёстком
BAY_W = 3.5            # ширина секции фасада (одна текстура)
FLOOR_H = 3.2          # высота этажа
GF_H = 4.0             # высота первого этажа
WATER_Z = -0.7

# зоны:  G трущобы, R спальный, I промзона/порт, O старый город,
#        D деловой центр, P парк, B набережная
ZONE_MAP = [            # сверху — север (j = 7)
    'GGGRRRRIII',
    'GGGRRRRIII',
    'OOODDDRRII',
    'OODDPPDDII',
    'OODDPPDDII',
    'OOODDDDDII',
    'BBBBBBBBBI',
    'BBBBBBBBBI',
]
BLOCK_W = [72, 72, 72, 86, 72, 72, 86, 72, 86, 86]            # i = 0..9 (запад -> восток)
BLOCK_H = [64, 72, 72, 80, 80, 72, 72, 72]                    # j = 0..7 (юг -> север)
ROAD_X_AVE = [True, False, False, True, False, False, True, False, True, False, True]
ROAD_Y_AVE = [True, False, True, False, False, True, False, False, True]
PARK_I0, PARK_I1, PARK_J0, PARK_J1 = 4, 5, 3, 4               # парк занимает 2x2 квартала

MARGIN_W, MARGIN_E, MARGIN_S, MARGIN_N = 28.0, 52.0, 56.0, 28.0

ZONE_NAMES = {
    'G': 'Ржавый квартал',
    'R': 'Сосновка',
    'I': 'Порт',
    'O': 'Старый город',
    'D': 'Деловой центр',
    'P': 'Центральный парк',
    'B': 'Набережная',
    'beach': 'Городской пляж',
    'docks': 'Причалы',
    'coast': 'Побережье',
    'sea': 'Залив',
}

# особые здания:  (i, j) квартала -> (имя, подсказка)
LANDMARKS = {
    (1, 3): 'safehouse',
    (0, 4): 'vano',
    (2, 2): 'spray',
    (1, 5): 'guns',
    (1, 6): 'rosa',
    (5, 5): 'hospital',
    (6, 2): 'police',
    (3, 3): 'bank',
    (7, 4): 'prof',
    (4, 1): 'taxi',
    (6, 5): 'gas',
    (8, 3): 'port',
    (7, 0): 'spray2',
    (8, 6): 'guns2',
}

LANDMARK_SIGNS = {
    'safehouse': 'sign_safehouse', 'vano': 'sign_garage', 'spray': 'sign_spray', 'spray2': 'sign_spray',
    'guns': 'sign_guns', 'guns2': 'sign_guns', 'rosa': 'sign_rosa', 'hospital': 'sign_hospital',
    'police': 'sign_police', 'bank': 'sign_bank', 'prof': 'sign_club', 'taxi': 'sign_taxi',
    'gas': 'sign_gas', 'port': 'sign_port',
}

GENERIC_SIGNS = ['sign_shawarma', 'sign_beer', 'sign_pawn', 'sign_pharm', 'sign_food', 'sign_tattoo',
                 'sign_cafe', 'sign_pizza', 'sign_gym', 'sign_laundry', 'sign_flowers', 'sign_phone',
                 'sign_barber', 'sign_sushi', 'sign_auto']
BEACH_SIGNS = ['sign_hotel', 'sign_casino', 'sign_cafe', 'sign_sushi', 'sign_club', 'sign_pizza', 'sign_beer']
BILLBOARDS = ['bb_shawarma', 'bb_credit', 'bb_radio', 'bb_cola', 'bb_lawyer', 'bb_mayor', 'bb_game', 'bb_gym']

NIGHT_FACADES = set([
    'fac_brick_a', 'fac_brick_b', 'fac_brick_c', 'fac_brick_d', 'fac_conc_a', 'fac_conc_b',
    'fac_balcony_a', 'fac_balcony_b', 'fac_glass_a', 'fac_glass_b', 'fac_glass_c', 'fac_glass_d',
    'fac_glass_e', 'fac_siding', 'fac_wh_win', 'fac_ghetto_a', 'fac_deco_a', 'fac_deco_b', 'fac_deco_c'])


class Block(object):
    __slots__ = ('id', 'i', 'j', 'i1', 'j1', 'x0', 'y0', 'x1', 'y1', 'zone')

    def interior(self):
        return (self.x0 + SIDEWALK, self.y0 + SIDEWALK, self.x1 - SIDEWALK, self.y1 - SIDEWALK)

    def center(self):
        return ((self.x0 + self.x1) * 0.5, (self.y0 + self.y1) * 0.5)


class Building(object):
    __slots__ = ('x0', 'y0', 'x1', 'y1', 'h', 'gf_h', 'gf_tex', 'gf_bay', 'fac', 'bay_w', 'floor_h',
                 'tint', 'roof_tex', 'roof_type', 'roof_color', 'tiers', 'sides_win', 'sides_gf',
                 'blank_tex', 'blank_tint', 'signs', 'night', 'block', 'name', 'roof_props', 'solid',
                 'z0', 'open_sides')

    def __init__(self, x0, y0, x1, y1, h, fac, block, **kw):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.h = h
        self.fac = fac
        self.block = block
        self.gf_h = kw.get('gf_h', GF_H)
        self.gf_tex = kw.get('gf_tex', 'gf_blank')
        self.gf_bay = kw.get('gf_bay', BAY_W)
        self.bay_w = kw.get('bay_w', BAY_W)
        self.floor_h = kw.get('floor_h', FLOOR_H)
        self.tint = kw.get('tint', (1.0, 1.0, 1.0))
        self.roof_tex = kw.get('roof_tex', 'roof_tar')
        self.roof_type = kw.get('roof_type', 'flat')
        self.roof_color = kw.get('roof_color', (1.0, 1.0, 1.0))
        self.tiers = kw.get('tiers', [])
        self.sides_win = kw.get('sides_win', 'nsew')
        self.sides_gf = kw.get('sides_gf', 'nsew')
        self.blank_tex = kw.get('blank_tex', 'brick')
        self.blank_tint = kw.get('blank_tint', (0.8, 0.8, 0.8))
        self.signs = kw.get('signs', [])
        self.night = kw.get('night', fac in NIGHT_FACADES)
        self.name = kw.get('name', None)
        self.roof_props = kw.get('roof_props', [])
        self.solid = kw.get('solid', True)
        self.z0 = kw.get('z0', CURB)
        self.open_sides = kw.get('open_sides', '')


class RoadNode(object):
    __slots__ = ('i', 'j', 'x', 'y', 'hw', 'hh', 'exits', 'phase')
    # exits: dict  'e'/'w'/'n'/'s' -> (ni, nj)


def _split(length, target, minimum=1):
    n = max(minimum, int(round(length / float(target))))
    return [length / n] * n


class City(object):

    def __init__(self, seed=1337):
        self.seed = seed
        self.rng = Rng(seed)

        # --- сетка дорог ------------------------------------------------
        self.nx = len(BLOCK_W)
        self.ny = len(BLOCK_H)
        self.wx = [AVE_W if a else ST_W for a in ROAD_X_AVE]      # ширины вертикальных дорог
        self.wy = [AVE_W if a else ST_W for a in ROAD_Y_AVE]
        total_w = sum(BLOCK_W) + sum(self.wx)
        total_h = sum(BLOCK_H) + sum(self.wy)
        self.xs = []
        x = -total_w * 0.5
        for i in range(self.nx + 1):
            x += self.wx[i] * 0.5
            self.xs.append(x)
            x += self.wx[i] * 0.5
            if i < self.nx:
                x += BLOCK_W[i]
        self.ys = []
        y = -total_h * 0.5
        for j in range(self.ny + 1):
            y += self.wy[j] * 0.5
            self.ys.append(y)
            y += self.wy[j] * 0.5
            if j < self.ny:
                y += BLOCK_H[j]
        self.grid_x0 = self.xs[0] - self.wx[0] * 0.5
        self.grid_x1 = self.xs[-1] + self.wx[-1] * 0.5
        self.grid_y0 = self.ys[0] - self.wy[0] * 0.5
        self.grid_y1 = self.ys[-1] + self.wy[-1] * 0.5
        # суша
        self.land_x0 = self.grid_x0 - MARGIN_W
        self.land_x1 = self.grid_x1 + MARGIN_E
        self.land_y0 = self.grid_y0 - MARGIN_S
        self.land_y1 = self.grid_y1 + MARGIN_N
        self.extra_land = []          # пирсы и мост: (x0, y0, x1, y1, z)

        # --- контейнеры данных -----------------------------------------
        self.blocks = []
        self.block_grid = {}          # (i, j) -> Block
        self.buildings = []
        self.ground = []              # (x0, y0, x1, y1, tex, tile(w,h), color, block, z, rot)
        self.boxes = []               # dict
        self.cyls = []                # dict
        self.walls = []               # dict: тонкие стены/заборы
        self.props = []               # dict: kind, x, y, yaw, block, ...
        self.parking = []             # dict: x, y, yaw, zone, kind
        self.landmarks = {}           # name -> dict
        self.packages = []            # (x, y)
        self.pickup_spots = []        # (x, y, hint)
        self.ped_extra_nodes = []     # дополнительные узлы пешеходного графа (парк)
        self.special = {}             # прочее (мост, понд, ...)
        self.n_chunks = 0

        self._make_roads()
        self._make_blocks()
        for b in self.blocks:
            self._gen_block(b)
        self._gen_outer()
        self._gen_extras()
        self.n_chunks = self._outer_chunk_base + 16

    # ------------------------------------------------------------------
    # дороги
    # ------------------------------------------------------------------
    def _seg_exists_h(self, i, j):
        """горизонтальный отрезок между узлами (i, j) и (i+1, j)"""
        if not (0 <= i < self.nx and 0 <= j <= self.ny):
            return False
        if j == PARK_J1 and PARK_I0 <= i <= PARK_I1:
            return False
        return True

    def _seg_exists_v(self, i, j):
        """вертикальный отрезок между узлами (i, j) и (i, j+1)"""
        if not (0 <= i <= self.nx and 0 <= j < self.ny):
            return False
        if i == PARK_I1 and PARK_J0 <= j <= PARK_J1:
            return False
        return True

    def _make_roads(self):
        self.nodes = {}
        for i in range(self.nx + 1):
            for j in range(self.ny + 1):
                if i == PARK_I1 and j == PARK_J1:
                    continue
                n = RoadNode()
                n.i, n.j = i, j
                n.x, n.y = self.xs[i], self.ys[j]
                n.hw, n.hh = self.wx[i] * 0.5, self.wy[j] * 0.5
                n.exits = {}
                if self._seg_exists_h(i, j):
                    n.exits['e'] = (i + 1, j)
                if self._seg_exists_h(i - 1, j):
                    n.exits['w'] = (i - 1, j)
                if self._seg_exists_v(i, j):
                    n.exits['n'] = (i, j + 1)
                if self._seg_exists_v(i, j - 1):
                    n.exits['s'] = (i, j - 1)
                n.phase = ((i * 7 + j * 13) % 10) * 3.1
                self.nodes[(i, j)] = n
        # отрезки дорог: ('h'|'v', i, j) -> dict
        self.segs = {}
        for i in range(self.nx):
            for j in range(self.ny + 1):
                if self._seg_exists_h(i, j):
                    self.segs[('h', i, j)] = dict(
                        kind='h', i=i, j=j, width=self.wy[j], ave=ROAD_Y_AVE[j],
                        a=self.xs[i] + self.wx[i] * 0.5, b=self.xs[i + 1] - self.wx[i + 1] * 0.5,
                        c=self.ys[j])
        for i in range(self.nx + 1):
            for j in range(self.ny):
                if self._seg_exists_v(i, j):
                    self.segs[('v', i, j)] = dict(
                        kind='v', i=i, j=j, width=self.wx[i], ave=ROAD_X_AVE[i],
                        a=self.ys[j] + self.wy[j] * 0.5, b=self.ys[j + 1] - self.wy[j + 1] * 0.5,
                        c=self.xs[i])

    def _make_blocks(self):
        for j in range(self.ny):
            for i in range(self.nx):
                zone = ZONE_MAP[self.ny - 1 - j][i]
                if zone == 'P' and not (i == PARK_I0 and j == PARK_J0):
                    continue
                b = Block()
                b.id = len(self.blocks)
                b.i, b.j = i, j
                b.i1, b.j1 = i, j
                if zone == 'P':
                    b.i1, b.j1 = PARK_I1, PARK_J1
                b.x0 = self.xs[b.i] + self.wx[b.i] * 0.5
                b.x1 = self.xs[b.i1 + 1] - self.wx[b.i1 + 1] * 0.5
                b.y0 = self.ys[b.j] + self.wy[b.j] * 0.5
                b.y1 = self.ys[b.j1 + 1] - self.wy[b.j1 + 1] * 0.5
                b.zone = zone
                self.blocks.append(b)
                for ii in range(b.i, b.i1 + 1):
                    for jj in range(b.j, b.j1 + 1):
                        self.block_grid[(ii, jj)] = b
        self._outer_chunk_base = len(self.blocks)

    # ------------------------------------------------------------------
    # запросы
    # ------------------------------------------------------------------
    def cell_at(self, x, y):
        """Индексы квартала (i, j) для точки (могут быть вне сетки: -1 / nx)."""
        i = bisect_right(self.xs, x) - 1
        j = bisect_right(self.ys, y) - 1
        return i, j

    def block_at(self, x, y):
        i, j = self.cell_at(x, y)
        b = self.block_grid.get((i, j))
        if b is not None and b.x0 <= x <= b.x1 and b.y0 <= y <= b.y1:
            return b
        return None

    def on_road(self, x, y):
        """Точка на проезжей части?"""
        if not (self.grid_x0 <= x <= self.grid_x1 and self.grid_y0 <= y <= self.grid_y1):
            return False
        return self.block_at(x, y) is None

    def in_water(self, x, y):
        if self.land_x0 <= x <= self.land_x1 and self.land_y0 <= y <= self.land_y1:
            return False
        for (x0, y0, x1, y1, z) in self.extra_land:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return False
        return True

    def ground_z(self, x, y):
        if self.grid_x0 <= x <= self.grid_x1 and self.grid_y0 <= y <= self.grid_y1:
            if self.block_at(x, y) is None:
                return 0.0
            return CURB
        if self.land_x0 <= x <= self.land_x1 and self.land_y0 <= y <= self.land_y1:
            # пляж плавно уходит в воду
            if y < self.land_y0 + 10.0:
                t = (y - self.land_y0) / 10.0
                return CURB + (WATER_Z - 0.3 - CURB) * (1.0 - t)
            return CURB
        for (x0, y0, x1, y1, z) in self.extra_land:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return z
        return WATER_Z - 1.2

    def zone_at(self, x, y):
        b = self.block_at(x, y)
        if b is not None:
            return b.zone
        if self.grid_x0 <= x <= self.grid_x1 and self.grid_y0 <= y <= self.grid_y1:
            # на дороге: берём ближайший квартал
            i, j = self.cell_at(x, y)
            i = clamp(i, 0, self.nx - 1)
            j = clamp(j, 0, self.ny - 1)
            return ZONE_MAP[self.ny - 1 - j][i]
        if self.in_water(x, y):
            return 'sea'
        if y < self.grid_y0:
            return 'beach'
        if x > self.grid_x1:
            return 'docks'
        return 'coast'

    def zone_name(self, x, y):
        return ZONE_NAMES.get(self.zone_at(x, y), '')

    def nearest_node(self, x, y):
        best = None
        bd = 1e18
        i0 = clamp(bisect_right(self.xs, x) - 1, 0, self.nx)
        j0 = clamp(bisect_right(self.ys, y) - 1, 0, self.ny)
        for i in (i0, i0 + 1):
            for j in (j0, j0 + 1):
                n = self.nodes.get((i, j))
                if n is None:
                    continue
                d = (n.x - x) ** 2 + (n.y - y) ** 2
                if d < bd:
                    bd = d
                    best = n
        if best is None:
            for n in self.nodes.values():
                d = (n.x - x) ** 2 + (n.y - y) ** 2
                if d < bd:
                    bd = d
                    best = n
        return best

    def outer_chunk(self, x, y):
        """Номер «чанка» для объектов за пределами кварталов."""
        if y < self.grid_y0:
            side = 0
            t = (x - self.land_x0) / (self.land_x1 - self.land_x0)
        elif y > self.grid_y1:
            side = 1
            t = (x - self.land_x0) / (self.land_x1 - self.land_x0)
        elif x < self.grid_x0:
            side = 2
            t = (y - self.land_y0) / (self.land_y1 - self.land_y0)
        else:
            side = 3
            t = (y - self.land_y0) / (self.land_y1 - self.land_y0)
        return self._outer_chunk_base + side * 4 + int(clamp(t, 0.0, 0.999) * 4)

    # ------------------------------------------------------------------
    # помощники генерации
    # ------------------------------------------------------------------
    def _ground(self, x0, y0, x1, y1, tex, block, tile=3.0, color=(1, 1, 1), z=CURB, rot=0):
        if x1 - x0 < 0.01 or y1 - y0 < 0.01:
            return
        if not isinstance(tile, tuple):
            tile = (tile, tile)
        self.ground.append((x0, y0, x1, y1, tex, tile, color, block, z, rot))

    def _prop(self, kind, x, y, yaw, block, **kw):
        d = dict(kind=kind, x=x, y=y, yaw=yaw, block=block)
        d.update(kw)
        self.props.append(d)
        return d

    def _box(self, x0, y0, z0, x1, y1, z1, tex, block, color=(1, 1, 1), uv_m=3.0, solid=True, top_tex=None,
             top_color=None, faces='xXyYZ'):
        self.boxes.append(dict(x0=x0, y0=y0, z0=z0, x1=x1, y1=y1, z1=z1, tex=tex, block=block, color=color,
                               uv_m=uv_m, solid=solid, top_tex=top_tex, top_color=top_color, faces=faces))

    def _wall(self, x0, y0, x1, y1, h, tex, block, color=(1, 1, 1), thick=0.3, kind='wall', z0=CURB):
        """Стена/забор вдоль отрезка (только по осям)."""
        self.walls.append(dict(x0=min(x0, x1), y0=min(y0, y1), x1=max(x0, x1), y1=max(y0, y1), h=h, tex=tex,
                               block=block, color=color, thick=thick, kind=kind, z0=z0))

    def _spot(self, x, y, yaw, zone, kind=None, block=-1):
        self.parking.append(dict(x=x, y=y, yaw=yaw, zone=zone, kind=kind, block=block))

    def _roof_props(self, r, x0, y0, x1, y1, z, tall=False):
        props = []
        w, h = x1 - x0, y1 - y0
        if w < 7 or h < 7:
            return props
        if r.chance(0.7):
            props.append(('stair', r.rangef(x0 + 2.5, x1 - 2.5), r.rangef(y0 + 2.5, y1 - 2.5)))
        for _ in range(r.randint(0, 3)):
            props.append(('ac', r.rangef(x0 + 2, x1 - 2), r.rangef(y0 + 2, y1 - 2)))
        if r.chance(0.3) and not tall:
            props.append(('tank', r.rangef(x0 + 3, x1 - 3), r.rangef(y0 + 3, y1 - 3)))
        if tall and r.chance(0.6):
            props.append(('antenna', (x0 + x1) * 0.5 + r.rangef(-2, 2), (y0 + y1) * 0.5 + r.rangef(-2, 2),
                          r.rangef(8, 22)))
        return props

    def _shop_signs(self, r, b, side, pool, every=2):
        """Добавить вывески над витринами на стороне side."""
        if side in ('s', 'n'):
            length = b.x1 - b.x0
        else:
            length = b.y1 - b.y0
        n = int(length // (BAY_W * every))
        if n <= 0:
            return
        step = length / n
        for k in range(n):
            if r.chance(0.28):
                continue
            b.signs.append(dict(side=side, off=step * (k + 0.5), z=b.z0 + b.gf_h - 0.15, w=min(5.6, step - 0.6),
                                h=1.35, tex=r.pick(pool)))

    def _register_landmark(self, name, bld, facing, block):
        """Запомнить особое место: точку у двери и точку на дороге перед зданием."""
        cx = (bld.x0 + bld.x1) * 0.5
        cy = (bld.y0 + bld.y1) * 0.5
        if facing == 's':
            door = (cx, block.y0 + SIDEWALK * 0.5)
            road = (cx, block.y0 - 1.6)
            yaw = -math.pi / 2
        elif facing == 'n':
            door = (cx, block.y1 - SIDEWALK * 0.5)
            road = (cx, block.y1 + 1.6)
            yaw = math.pi / 2
        elif facing == 'w':
            door = (block.x0 + SIDEWALK * 0.5, cy)
            road = (block.x0 - 1.6, cy)
            yaw = math.pi
        else:
            door = (block.x1 - SIDEWALK * 0.5, cy)
            road = (block.x1 + 1.6, cy)
            yaw = 0.0
        self.landmarks[name] = dict(name=name, door=door, road=road, yaw=yaw, facing=facing,
                                    rect=(bld.x0, bld.y0, bld.x1, bld.y1), block=block.id,
                                    center=(cx, cy))
        return self.landmarks[name]

    def _big_sign(self, bld, side, tex, w=9.0, h=2.2, z=None):
        if side in ('s', 'n'):
            length = bld.x1 - bld.x0
        else:
            length = bld.y1 - bld.y0
        w = min(w, length - 0.6)
        h = w / 4.0 if w < 8.8 else h
        bld.signs.append(dict(side=side, off=length * 0.5, z=(bld.z0 + bld.gf_h + 0.9) if z is None else z,
                              w=w, h=h, tex=tex))

    # ------------------------------------------------------------------
    def _gen_block(self, b):
        r = Rng(self.seed * 1000 + b.id * 17 + 5)
        R = b.interior()
        z = b.zone
        if z == 'P':
            self._gen_park(b, R, r)
        elif z == 'D':
            self._gen_downtown(b, R, r)
        elif z == 'O':
            self._gen_old(b, R, r)
        elif z == 'G':
            self._gen_ghetto(b, R, r)
        elif z == 'R':
            self._gen_resid(b, R, r)
        elif z == 'I':
            self._gen_indust(b, R, r)
        else:
            self._gen_beach(b, R, r)
        self._gen_street_furniture(b, r)

    @staticmethod
    def _lots(R, nx, ny):
        x0, y0, x1, y1 = R
        lots = []
        for jy in range(ny):
            for ix in range(nx):
                lx0 = x0 + (x1 - x0) * ix / nx
                lx1 = x0 + (x1 - x0) * (ix + 1) / nx
                ly0 = y0 + (y1 - y0) * jy / ny
                ly1 = y0 + (y1 - y0) * (jy + 1) / ny
                faces = ''
                if ix == 0:
                    faces += 'w'
                if ix == nx - 1:
                    faces += 'e'
                if jy == 0:
                    faces += 's'
                if jy == ny - 1:
                    faces += 'n'
                lots.append((lx0, ly0, lx1, ly1, faces))
        return lots

    # ------------------------------------------------------------------
    # ДЕЛОВОЙ ЦЕНТР
    # ------------------------------------------------------------------
    def _gen_downtown(self, b, R, r):
        x0, y0, x1, y1 = R
        nx = 2 if (x1 - x0) >= 56 else 1
        ny = 2 if (y1 - y0) >= 56 else 1
        lots = self._lots(R, nx, ny)
        lm = LANDMARKS.get((b.i, b.j))
        pcx = (self.xs[PARK_I0] + self.xs[PARK_I1 + 1]) * 0.5
        pcy = (self.ys[PARK_J0] + self.ys[PARK_J1 + 1]) * 0.5
        for k, (lx0, ly0, lx1, ly1, faces) in enumerate(lots):
            if lm and k == 0:
                self._downtown_landmark(b, r, lm, lx0, ly0, lx1, ly1, faces)
                continue
            p = r.random()
            if p < 0.09:
                self._plaza(b, r, lx0, ly0, lx1, ly1)
                continue
            if p < 0.19:
                self._parking_lot(b, r, lx0, ly0, lx1, ly1, 'D')
                continue
            self._ground(lx0, ly0, lx1, ly1, 'pavers', b.id)
            ins = {}
            for s in 'nsew':
                ins[s] = r.rangef(1.5, 4.5) if s in faces else 2.6
            fx0, fy0, fx1, fy1 = lx0 + ins['w'], ly0 + ins['s'], lx1 - ins['e'], ly1 - ins['n']
            d = math.hypot((fx0 + fx1) * 0.5 - pcx, (fy0 + fy1) * 0.5 - pcy)
            base = 30 - d / 300.0 * 22
            floors = int(clamp(base + r.rangef(-7, 9), 6, 38))
            fac = r.pick(['fac_glass_a', 'fac_glass_a', 'fac_glass_b', 'fac_glass_c', 'fac_glass_d',
                          'fac_glass_e', 'fac_conc_a'])
            h = GF_H + floors * FLOOR_H
            tiers = []
            tx0, ty0, tx1, ty1, tz = fx0, fy0, fx1, fy1, h
            if floors >= 12 and r.chance(0.65):
                for _ in range(r.randint(1, 2)):
                    ti = r.rangef(2.5, 5.0)
                    if tx1 - tx0 - 2 * ti < 9 or ty1 - ty0 - 2 * ti < 9:
                        break
                    tx0, ty0, tx1, ty1 = tx0 + ti, ty0 + ti, tx1 - ti, ty1 - ti
                    th = r.randint(3, 9) * FLOOR_H
                    tiers.append((tx0, ty0, tx1, ty1, tz, tz + th))
                    tz += th
            bld = Building(fx0, fy0, fx1, fy1, h, fac, b.id, gf_tex=r.pick(['gf_office', 'gf_office', 'gf_shop_c']),
                           sides_gf=faces, tiers=tiers, roof_tex='roof_gravel', blank_tex='concrete')
            bld.roof_props = self._roof_props(r, tx0, ty0, tx1, ty1, tz, tall=True)
            if r.chance(0.16) and not tiers:
                bld.roof_props.append(('billboard', (fx0 + fx1) * 0.5, (fy0 + fy1) * 0.5,
                                       r.pick('nsew'), r.pick(BILLBOARDS)))
            self.buildings.append(bld)
            # служебный проезд: мусорка / ящик в переулке
            if r.chance(0.5):
                self._prop('dumpster', lx1 - 1.3 if 'e' not in faces else lx0 + 1.3,
                           r.rangef(ly0 + 4, ly1 - 4), math.pi / 2, b.id)
            if r.chance(0.25):
                self.pickup_spots.append((lx0 + 1.2 if 'w' not in faces else lx1 - 1.2,
                                          ly1 - 1.2 if 'n' not in faces else ly0 + 1.2, 'alley'))

    def _downtown_landmark(self, b, r, name, lx0, ly0, lx1, ly1, faces):
        self._ground(lx0, ly0, lx1, ly1, 'pavers', b.id)
        fx0, fy0, fx1, fy1 = lx0 + 3.0, ly0 + 2.0, lx1 - 2.6, ly1 - 2.6
        if name == 'hospital':
            bld = Building(fx0, fy0, fx1, fy1, GF_H + 6 * FLOOR_H, 'fac_conc_b', b.id, gf_tex='gf_office',
                           tint=(1.0, 1.0, 1.0), sides_gf='s', name=name, blank_tex='concrete',
                           roof_tex='roof_gravel')
            bld.roof_props = [('stair', fx0 + 4, fy1 - 4), ('helipad', (fx0 + fx1) * 0.5, (fy0 + fy1) * 0.5)]
            bld.signs.append(dict(side='s', off=5.0, z=CURB + GF_H + 3 * FLOOR_H, w=3.2, h=3.2, tex='emblem_cross'))
        elif name == 'police':
            bld = Building(fx0, fy0, fx1, fy1, GF_H + 4 * FLOOR_H, 'fac_conc_a', b.id, gf_tex='gf_office',
                           tint=(0.74, 0.80, 0.95), sides_gf='s', name=name, blank_tex='concrete',
                           roof_tex='roof_gravel')
            bld.roof_props = [('antenna', fx1 - 4, fy1 - 4, 16.0), ('stair', fx0 + 4, fy1 - 5)]
        elif name == 'bank':
            bld = Building(fx0, fy0, fx1, fy1, GF_H + 5 * FLOOR_H, 'fac_conc_b', b.id, gf_tex='gf_office',
                           tint=(1.0, 0.95, 0.84), sides_gf='s', name=name, blank_tex='concrete',
                           roof_tex='roof_gravel')
            # колонны
            for cx in (fx0 + 3, fx0 + 9, fx1 - 9, fx1 - 3):
                self.cyls.append(dict(x=cx, y=fy0 - 0.9, z0=CURB, z1=CURB + GF_H + FLOOR_H, r=0.55, tex='concrete',
                                      color=(1.0, 0.97, 0.9), block=b.id, solid=True, n=8))
        else:       # prof: клуб/офис
            bld = Building(fx0, fy0, fx1, fy1, GF_H + 18 * FLOOR_H, 'fac_glass_b', b.id, gf_tex='gf_office',
                           sides_gf='s', name=name, blank_tex='concrete', roof_tex='roof_gravel')
            bld.roof_props = [('antenna', (fx0 + fx1) * 0.5, (fy0 + fy1) * 0.5, 24.0)]
        self._big_sign(bld, 's', LANDMARK_SIGNS[name])
        self.buildings.append(bld)
        lm = self._register_landmark(name, bld, 's', b)
        if name == 'police':
            for k in range(3):
                self._spot(lm['road'][0] - 12 + k * 7.0, b.y0 - PARK_STRIP * 0.5 if not ROAD_Y_AVE[b.j] else b.y0 + 1.3,
                           0.0, 'D', kind='police', block=b.id)
        if name == 'hospital':
            self._spot(lm['road'][0] + 10, b.y0 - PARK_STRIP * 0.5 if not ROAD_Y_AVE[b.j] else b.y0 + 1.3, 0.0,
                       'D', kind='ambulance', block=b.id)

    def _plaza(self, b, r, lx0, ly0, lx1, ly1):
        self._ground(lx0, ly0, lx1, ly1, 'pavers', b.id)
        cx, cy = (lx0 + lx1) * 0.5, (ly0 + ly1) * 0.5
        self._prop('fountain' if r.chance(0.6) else 'statue', cx, cy, 0.0, b.id)
        for (dx, dy, yaw) in ((0, 6.5, -math.pi / 2), (0, -6.5, math.pi / 2), (6.5, 0, math.pi), (-6.5, 0, 0.0)):
            self._prop('bench', cx + dx, cy + dy, yaw, b.id)
        for (sx, sy) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            self._prop('tree', cx + sx * (lx1 - lx0) * 0.32, cy + sy * (ly1 - ly0) * 0.32, 0.0, b.id,
                       seed=r.randint(0, 9999), size=r.rangef(0.9, 1.2))
        self._prop('lamp', cx - 9, cy - 9, math.pi / 4, b.id, park=True)
        self._prop('lamp', cx + 9, cy + 9, math.pi * 1.25, b.id, park=True)
        self.packages.append((cx + 3.2, cy + 3.2))

    def _parking_lot(self, b, r, lx0, ly0, lx1, ly1, zone, occupancy=0.5, kind=None):
        """Парковка: два ряда мест вдоль длинных сторон."""
        self._ground(lx0, ly0, lx1, ly1, 'asphalt', b.id, tile=8.0, color=(0.92, 0.92, 0.92))
        w, h = lx1 - lx0, ly1 - ly0
        stall_w, stall_d = 2.9, 5.6
        if w >= h:
            n = int((w - 4.0) // stall_w)
            sx = lx0 + (w - n * stall_w) * 0.5
            for k in range(n):
                x = sx + (k + 0.5) * stall_w
                for (yy, yaw) in ((ly0 + 1.0 + stall_d * 0.5, math.pi / 2), (ly1 - 1.0 - stall_d * 0.5, -math.pi / 2)):
                    self.ground.append((x - stall_w * 0.5, yy - stall_d * 0.5, x + stall_w * 0.5, yy + stall_d * 0.5,
                                        'parking', (stall_w, stall_d), (1, 1, 1), b.id, CURB + 0.02, 0))
                    if r.chance(occupancy):
                        self._spot(x, yy, yaw, zone, kind=kind, block=b.id)
        else:
            n = int((h - 4.0) // stall_w)
            sy = ly0 + (h - n * stall_w) * 0.5
            for k in range(n):
                y = sy + (k + 0.5) * stall_w
                for (xx, yaw) in ((lx0 + 1.0 + stall_d * 0.5, 0.0), (lx1 - 1.0 - stall_d * 0.5, math.pi)):
                    self.ground.append((xx - stall_d * 0.5, y - stall_w * 0.5, xx + stall_d * 0.5, y + stall_w * 0.5,
                                        'parking', (stall_w, stall_d), (1, 1, 1), b.id, CURB + 0.02, 1))
                    if r.chance(occupancy):
                        self._spot(xx, y, yaw, zone, kind=kind, block=b.id)
        self._prop('lamp', (lx0 + lx1) * 0.5, (ly0 + ly1) * 0.5, 0.0, b.id, park=True)

    # ------------------------------------------------------------------
    # СТАРЫЙ ГОРОД: дома по периметру квартала + двор
    # ------------------------------------------------------------------
    def _row_widths(self, r, length):
        out = []
        rem = length
        while rem > 0.01:
            w = r.pick([10.5, 14.0, 14.0, 17.5])
            if rem - w < 8.5:
                w = rem
            out.append(w)
            rem -= w
        return out

    def _gen_old(self, b, R, r):
        x0, y0, x1, y1 = R
        D = 15.0
        lm = LANDMARKS.get((b.i, b.j))
        styles = ['fac_brick_a', 'fac_brick_b', 'fac_brick_c', 'fac_brick_d', 'fac_conc_b', 'fac_balcony_a',
                  'fac_balcony_b', 'fac_brick_a', 'fac_brick_c']
        shops = ['gf_shop_a', 'gf_shop_b', 'gf_shop_c', 'gf_shop_d', 'gf_shop_a', 'gf_door']
        self._ground(x0, y0, x1, y1, 'concrete', b.id, tile=4.0, color=(0.82, 0.82, 0.82))
        # двор
        cx0, cy0, cx1, cy1 = x0 + D, y0 + D, x1 - D, y1 - D
        yard_tex = 'asphalt' if r.chance(0.7) else 'dirt'
        self.ground.append((cx0, cy0, cx1, cy1, yard_tex, (6.0, 6.0), (0.9, 0.9, 0.9), b.id, CURB + 0.02, 0))

        def make(bx0, by0, bx1, by1, side, corner=''):
            fac = r.pick(styles)
            floors = r.randint(2, 5)
            win = side + {'s': 'n', 'n': 's', 'w': 'e', 'e': 'w'}[side] + corner
            bld = Building(bx0, by0, bx1, by1, GF_H + floors * FLOOR_H, fac, b.id, gf_tex=r.pick(shops),
                           sides_win=win, sides_gf=side + corner,
                           blank_tex='brick', blank_tint=(0.72, 0.70, 0.68),
                           roof_tex=r.pick(['roof_tar', 'roof_gravel']))
            bld.roof_props = self._roof_props(r, bx0, by0, bx1, by1, bld.h)
            if bld.gf_tex != 'gf_door':
                self._shop_signs(r, bld, side, GENERIC_SIGNS)
                for c in corner:
                    self._shop_signs(r, bld, c, GENERIC_SIGNS)
            self.buildings.append(bld)
            return bld

        lm_side = 's'
        rows = []
        # южный и северный ряды (во всю ширину)
        for side in ('s', 'n'):
            widths = self._row_widths(r, x1 - x0)
            xx = x0
            blds = []
            for k, w in enumerate(widths):
                corner = ''
                if k == 0:
                    corner += 'w'
                if k == len(widths) - 1:
                    corner += 'e'
                if side == 's':
                    blds.append(make(xx, y0, xx + w, y0 + D, 's', corner))
                else:
                    blds.append(make(xx, y1 - D, xx + w, y1, 'n', corner))
                xx += w
            rows.append(blds)
        # западный и восточный ряды (между ними), с проездом во двор
        gap_side = r.pick(['w', 'e'])
        for side in ('w', 'e'):
            length = (y1 - D) - (y0 + D)
            gap_at = None
            if side == gap_side:
                gap_at = r.rangef(0.25, 0.6) * length
            yy = y0 + D
            rem = length
            while rem > 0.01:
                if gap_at is not None and (yy - (y0 + D)) >= gap_at - 0.01:
                    gw = 5.5
                    # проезд
                    if side == 'w':
                        self.ground.append((x0, yy, x0 + D, yy + gw, yard_tex, (6.0, 6.0), (0.9, 0.9, 0.9), b.id,
                                            CURB + 0.02, 0))
                    else:
                        self.ground.append((x1 - D, yy, x1, yy + gw, yard_tex, (6.0, 6.0), (0.9, 0.9, 0.9), b.id,
                                            CURB + 0.02, 0))
                    yy += gw
                    rem -= gw
                    gap_at = None
                    continue
                w = r.pick([10.5, 14.0, 14.0])
                if gap_at is not None:
                    w = min(w, gap_at - (yy - (y0 + D)))
                    if w < 6.0:
                        w = gap_at - (yy - (y0 + D))
                if rem - w < 8.0:
                    w = rem
                if w < 1.0:
                    break
                if side == 'w':
                    make(x0, yy, x0 + D, yy + w, 'w')
                else:
                    make(x1 - D, yy, x1, yy + w, 'e')
                yy += w
                rem -= w
        # двор: парковка, мусорки, тайник
        yw, yh = cx1 - cx0, cy1 - cy0
        if yw > 10 and yh > 10:
            n = r.randint(1, 3)
            for k in range(n):
                self._spot(cx0 + 2.4 + k * 3.2, cy0 + 3.6, math.pi / 2, 'O', block=b.id)
            self._prop('dumpster', cx1 - 1.4, cy1 - 3.0, math.pi / 2, b.id)
            if r.chance(0.6):
                self._prop('crate', cx1 - 2.0, cy0 + 1.6, r.rangef(0, 1.5), b.id)
                self._prop('crate', cx1 - 3.4, cy0 + 1.4, r.rangef(0, 1.5), b.id)
            if r.chance(0.5):
                self._prop('tree', (cx0 + cx1) * 0.5, (cy0 + cy1) * 0.5, 0.0, b.id, seed=r.randint(0, 9999), size=1.0)
            if r.chance(0.45):
                self.packages.append((cx0 + 1.5, cy1 - 1.5))
            else:
                self.pickup_spots.append((cx0 + 1.5, cy1 - 1.5, 'yard'))
        # особое здание: переделываем дом в середине южного ряда
        if lm:
            blds = rows[0]
            bld = blds[len(blds) // 2] if len(blds) > 2 else blds[0]
            bld.name = lm
            bld.signs = []
            if lm in ('spray', 'spray2'):
                self._make_spray(b, bld, r, lm)
            elif lm == 'vano':
                bld.h = GF_H + 1 * FLOOR_H
                bld.fac = 'fac_brick_d'
                bld.gf_tex = 'gf_garage'
                bld.roof_props = []
                self._big_sign(bld, 's', LANDMARK_SIGNS[lm], z=CURB + GF_H + 1.6)
                self._register_landmark(lm, bld, 's', b)
            else:
                if lm == 'safehouse':
                    bld.fac = 'fac_brick_c'
                    bld.gf_tex = 'gf_door'
                    bld.h = GF_H + 4 * FLOOR_H
                elif lm in ('guns', 'guns2'):
                    bld.fac = 'fac_brick_d'
                    bld.gf_tex = 'gf_shop_c'
                    bld.h = GF_H + 2 * FLOOR_H
                self._big_sign(bld, 's', LANDMARK_SIGNS[lm])
                self._register_landmark(lm, bld, 's', b)

    def _make_spray(self, b, bld, r, name):
        """Покрасочная: П-образное здание с въездом с улицы."""
        self.buildings.remove(bld)
        x0, y0, x1, y1 = bld.x0, bld.y0, bld.x1, bld.y1
        cx = (x0 + x1) * 0.5
        bay = 3.4            # половина ширины въезда
        depth = 10.5
        h = GF_H + 1.2
        tint = (1.0, 0.86, 0.3)
        parts = [(x0, y0, cx - bay, y1), (cx + bay, y0, x1, y1), (cx - bay, y0 + depth, cx + bay, y1)]
        for (px0, py0, px1, py1) in parts:
            if px1 - px0 < 0.5 or py1 - py0 < 0.5:
                continue
            p = Building(px0, py0, px1, py1, h, 'fac_wh', b.id, gf_h=h, gf_tex='fac_wh', gf_bay=4.0, tint=tint,
                         sides_win='nsew', sides_gf='nsew', blank_tex='fac_wh', blank_tint=tint, roof_tex='roof_tar',
                         name=name)
            p.night = False
            self.buildings.append(p)
        # крыша над въездом и пол
        self._box(cx - bay, y0, CURB + h - 0.5, cx + bay, y0 + depth, CURB + h, 'fac_wh', b.id, color=tint,
                  solid=False, faces='xXyYZz')
        self.ground.append((cx - bay, y0, cx + bay, y0 + depth, 'concrete', (4.0, 4.0), (0.7, 0.7, 0.72), b.id,
                            CURB + 0.03, 0))
        fake = Building(x0, y0, x1, y1, h, 'fac_wh', b.id)
        lm = self._register_landmark(name, fake, 's', b)
        lm['bay'] = (cx, y0 + depth * 0.5)           # точка внутри бокса
        lm['bay_rect'] = (cx - bay, y0, cx + bay, y0 + depth)
        # вывеска над въездом
        self.special.setdefault('free_signs', []).append(
            dict(x=cx, y=y0 - 0.12, z=CURB + h + 1.4, w=8.8, h=2.2, tex='sign_spray', side='s', block=b.id))

    # ------------------------------------------------------------------
    # ТРУЩОБЫ
    # ------------------------------------------------------------------
    def _gen_ghetto(self, b, R, r):
        x0, y0, x1, y1 = R
        lots = self._lots(R, 2, 2)
        lm = LANDMARKS.get((b.i, b.j))
        for k, (lx0, ly0, lx1, ly1, faces) in enumerate(lots):
            p = r.random()
            if lm and k == 0:
                p = 0.0
            if p < 0.56:
                self._ground(lx0, ly0, lx1, ly1, 'dirt' if r.chance(0.4) else 'concrete', b.id, tile=4.0,
                             color=(0.8, 0.8, 0.8))
                ins = {s: (r.rangef(0.0, 3.0) if s in faces else r.rangef(2.6, 5.0)) for s in 'nsew'}
                fx0, fy0, fx1, fy1 = lx0 + ins['w'], ly0 + ins['s'], lx1 - ins['e'], ly1 - ins['n']
                floors = r.randint(2, 4)
                bld = Building(fx0, fy0, fx1, fy1, GF_H + floors * FLOOR_H,
                               r.pick(['fac_ghetto_a', 'fac_ghetto_a', 'fac_ghetto_b', 'fac_brick_d']), b.id,
                               gf_tex=r.pick(['gf_ghetto', 'gf_ghetto', 'gf_door']), sides_gf=faces,
                               blank_tex='brick', blank_tint=(0.6, 0.56, 0.54),
                               roof_tex='roof_tar', tint=(0.92, 0.9, 0.88))
                bld.roof_props = self._roof_props(r, fx0, fy0, fx1, fy1, bld.h)
                if lm and k == 0:
                    bld.name = lm
                    bld.gf_tex = 'gf_shop_a'
                    bld.sides_gf = 's'
                    self._big_sign(bld, 's', LANDMARK_SIGNS[lm])
                    self._register_landmark(lm, bld, 's', b)
                elif r.chance(0.3):
                    self._shop_signs(r, bld, faces[0], GENERIC_SIGNS, every=3)
                self.buildings.append(bld)
                if r.chance(0.5):
                    self._prop('barrel', fx1 + 1.2 if 'e' not in faces else fx0 - 1.2, fy0 + 2.0, 0.0, b.id,
                               fire=r.chance(0.5))
            elif p < 0.76:
                # пустырь
                self._ground(lx0, ly0, lx1, ly1, 'dirt', b.id, tile=5.0)
                cx, cy = (lx0 + lx1) * 0.5, (ly0 + ly1) * 0.5
                self._prop('wreck', cx + r.rangef(-5, 5), cy + r.rangef(-5, 5), r.rangef(0, 6.28), b.id)
                for _ in range(r.randint(2, 5)):
                    self._prop(r.pick(['crate', 'tires', 'barrel']), r.rangef(lx0 + 2, lx1 - 2),
                               r.rangef(ly0 + 2, ly1 - 2), r.rangef(0, 6.28), b.id)
                self._fence_lot(b, r, lx0, ly0, lx1, ly1, faces, gaps=True)
                self.pickup_spots.append((cx, cy + 6.0, 'lot'))
                if r.chance(0.5):
                    self.packages.append((lx0 + 2.0 if 'w' not in faces else lx1 - 2.0, cy))
            elif p < 0.90:
                # баскетбольная площадка
                self._ground(lx0, ly0, lx1, ly1, 'concrete', b.id, tile=4.0, color=(0.74, 0.78, 0.74))
                cx, cy = (lx0 + lx1) * 0.5, (ly0 + ly1) * 0.5
                self._prop('hoop', cx, ly0 + 3.0, math.pi / 2, b.id)
                self._prop('hoop', cx, ly1 - 3.0, -math.pi / 2, b.id)
                self._fence_lot(b, r, lx0, ly0, lx1, ly1, faces, gaps=True)
                self._prop('bench', lx0 + 2.0, cy, 0.0, b.id)
            else:
                self._parking_lot(b, r, lx0, ly0, lx1, ly1, 'G', occupancy=0.35)

    def _fence_lot(self, b, r, lx0, ly0, lx1, ly1, faces, gaps=True, h=2.2, tex='chainlink', inset=0.4):
        """Сетчатый забор вдоль уличных сторон участка (с проходами)."""
        def run(ax, ay, bx, by):
            length = math.hypot(bx - ax, by - ay)
            if length < 4:
                return
            if gaps and length > 12:
                g0 = r.rangef(0.3, 0.6) * length
                g1 = g0 + 4.5
                t0, t1 = g0 / length, g1 / length
                self._wall(ax, ay, ax + (bx - ax) * t0, ay + (by - ay) * t0, h, tex, b.id, thick=0.12, kind='fence')
                self._wall(ax + (bx - ax) * t1, ay + (by - ay) * t1, bx, by, h, tex, b.id, thick=0.12, kind='fence')
            else:
                self._wall(ax, ay, bx, by, h, tex, b.id, thick=0.12, kind='fence')
        if 's' in faces:
            run(lx0 + inset, ly0 + inset, lx1 - inset, ly0 + inset)
        if 'n' in faces:
            run(lx0 + inset, ly1 - inset, lx1 - inset, ly1 - inset)
        if 'w' in faces:
            run(lx0 + inset, ly0 + inset, lx0 + inset, ly1 - inset)
        if 'e' in faces:
            run(lx1 - inset, ly0 + inset, lx1 - inset, ly1 - inset)

    # ------------------------------------------------------------------
    # СПАЛЬНЫЙ РАЙОН
    # ------------------------------------------------------------------
    def _gen_resid(self, b, R, r):
        x0, y0, x1, y1 = R
        lm = LANDMARKS.get((b.i, b.j))
        ymid = (y0 + y1) * 0.5
        self._ground(x0, y0, x1, y1, 'grass', b.id, tile=6.0)
        tints = [(1.0, 1.0, 1.0), (0.98, 0.92, 0.78), (0.80, 0.90, 1.0), (0.84, 0.96, 0.84), (1.0, 0.86, 0.82),
                 (0.9, 0.9, 0.92)]
        roofs = [(1.0, 1.0, 1.0), (0.62, 0.5, 0.46), (0.42, 0.44, 0.5), (0.7, 0.72, 0.66)]
        for row in (0, 1):
            if lm == 'gas' and row == 0:
                self._gas_station(b, r, x0, y0, x1, ymid)
                continue
            widths = _split(x1 - x0, 22.0)
            xx = x0
            for k, w in enumerate(widths):
                lx0, lx1 = xx, xx + w
                xx += w
                hw = r.rangef(10.0, min(13.0, w - 7.0))
                hd = r.rangef(8.0, 10.0)
                drive_left = r.chance(0.5)
                dw = 3.4
                if drive_left:
                    hx0 = lx0 + dw + 1.6
                else:
                    hx0 = lx1 - dw - 1.6 - hw
                setback = r.rangef(5.5, 7.0)
                if row == 0:
                    hy0 = y0 + setback
                    front = 's'
                else:
                    hy0 = y1 - setback - hd
                    front = 'n'
                floors = 1 if r.chance(0.45) else 2
                bld = Building(hx0, hy0, hx0 + hw, hy0 + hd, floors * FLOOR_H, 'fac_siding', b.id, gf_h=0.0,
                               tint=r.pick(tints), roof_type='gable', roof_tex='roof_tiles',
                               roof_color=r.pick(roofs), blank_tex='fac_siding')
                bld.open_sides = front           # сторона с дверью
                self.buildings.append(bld)
                # подъездная дорожка + машина
                dx0 = lx0 + 0.8 if drive_left else lx1 - 0.8 - dw
                if row == 0:
                    self.ground.append((dx0, y0, dx0 + dw, hy0 + hd, 'concrete', (4.0, 4.0), (0.86, 0.86, 0.86), b.id,
                                        CURB + 0.02, 0))
                    if r.chance(0.6):
                        self._spot(dx0 + dw * 0.5, y0 + setback + 2.0, math.pi / 2, 'R', block=b.id)
                    self._prop('mailbox', dx0 - 0.6 if drive_left else dx0 + dw + 0.6, y0 + 0.5, math.pi / 2, b.id)
                else:
                    self.ground.append((dx0, hy0, dx0 + dw, y1, 'concrete', (4.0, 4.0), (0.86, 0.86, 0.86), b.id,
                                        CURB + 0.02, 0))
                    if r.chance(0.6):
                        self._spot(dx0 + dw * 0.5, y1 - setback - 2.0, -math.pi / 2, 'R', block=b.id)
                    self._prop('mailbox', dx0 - 0.6 if drive_left else dx0 + dw + 0.6, y1 - 0.5, -math.pi / 2, b.id)
                # деревья
                for _ in range(r.randint(1, 2)):
                    tx = r.rangef(lx0 + 2.0, lx1 - 2.0)
                    ty = r.rangef(ymid - 9.0, ymid - 2.0) if row == 0 else r.rangef(ymid + 2.0, ymid + 9.0)
                    if not (hx0 - 1.5 < tx < hx0 + hw + 1.5 and hy0 - 1.5 < ty < hy0 + hd + 1.5) and \
                            not (dx0 - 1 < tx < dx0 + dw + 1):
                        self._prop('tree', tx, ty, 0.0, b.id, seed=r.randint(0, 9999), size=r.rangef(0.8, 1.25))
                # живая изгородь между участками (только задний двор)
                if k > 0:
                    if row == 0:
                        self._wall(lx0, hy0 + hd + 1.0, lx0, ymid, 1.1, 'hedge', b.id, thick=0.7, kind='hedge')
                    else:
                        self._wall(lx0, ymid, lx0, hy0 - 1.0, 1.1, 'hedge', b.id, thick=0.7, kind='hedge')
                if r.chance(0.12):
                    self.pickup_spots.append(((lx0 + lx1) * 0.5, ymid + (-2.0 if row == 0 else 2.0), 'yard'))
        # изгородь по середине квартала
        self._wall(x0 + 1.0, ymid, x1 - 1.0, ymid, 1.1, 'hedge', b.id, thick=0.7, kind='hedge')
        if r.chance(0.35):
            self.packages.append((x0 + 1.4, ymid + 1.5))

    def _gas_station(self, b, r, x0, y0, x1, y1):
        """Заправка на южной половине квартала."""
        self._ground(x0, y0, x1, y1, 'asphalt', b.id, tile=8.0, color=(0.95, 0.95, 0.95), z=CURB + 0.02)
        cx = (x0 + x1) * 0.5
        # навес
        nx0, nx1, ny0, ny1 = cx - 12, cx + 12, y0 + 5, y0 + 15
        self._box(nx0, ny0, CURB + 5.2, nx1, ny1, CURB + 5.9, 'fac_wh', b.id, color=(0.95, 0.2, 0.2), solid=False,
                  faces='xXyYZz', top_tex='roof_tar')
        for px in (nx0 + 1.5, nx1 - 1.5):
            for py in (ny0 + 1.5, ny1 - 1.5):
                self.cyls.append(dict(x=px, y=py, z0=CURB, z1=CURB + 5.2, r=0.28, tex=None, color=(0.9, 0.9, 0.9),
                                      block=b.id, solid=True, n=6))
        for px in (cx - 6, cx + 6):
            self._box(px - 2.2, ny0 + 4.2, CURB, px + 2.2, ny0 + 5.8, CURB + 0.2, 'concrete', b.id, solid=False)
            for dx in (-1.2, 1.2):
                self._prop('pump', px + dx, ny0 + 5.0, 0.0, b.id)
        # магазин
        sx0, sx1, sy0, sy1 = cx - 9, cx + 9, y1 - 11, y1 - 2
        bld = Building(sx0, sy0, sx1, sy1, GF_H + 0.6, 'fac_conc_a', b.id, gf_h=GF_H + 0.6, gf_tex='gf_shop_c',
                       sides_gf='s', name='gas', blank_tex='concrete', roof_tex='roof_gravel')
        bld.night = False
        bld.signs.append(dict(side='s', off=9.0, z=CURB + GF_H + 0.05, w=8.0, h=1.0, tex='sign_food'))
        self.buildings.append(bld)
        self.special.setdefault('free_signs', []).append(
            dict(x=cx, y=ny0 - 0.05, z=CURB + 5.55, w=8.8, h=0.66, tex='sign_gas', side='s', block=b.id))
        self.special.setdefault('free_signs', []).append(
            dict(x=cx, y=ny1 + 0.05, z=CURB + 5.55, w=8.8, h=0.66, tex='sign_gas', side='n', block=b.id))
        lm = self._register_landmark('gas', bld, 's', b)
        lm['pumps'] = (cx, ny0 + 5.0)
        self._spot(x0 + 4.0, y1 - 6.0, math.pi / 2, 'R', block=b.id)
        self._spot(x1 - 4.0, y1 - 6.0, math.pi / 2, 'R', block=b.id)
        self._prop('lamp', x0 + 3.0, y0 + 3.0, math.pi / 4, b.id, park=True)
        self._prop('lamp', x1 - 3.0, y0 + 3.0, math.pi * 0.75, b.id, park=True)

    # ------------------------------------------------------------------
    # ПРОМЗОНА / ПОРТ
    # ------------------------------------------------------------------
    CONTAINER_COLORS = [(0.75, 0.2, 0.16), (0.16, 0.36, 0.7), (0.2, 0.55, 0.3), (0.9, 0.55, 0.12),
                        (0.6, 0.6, 0.62), (0.5, 0.2, 0.5), (0.85, 0.8, 0.3)]

    def _containers(self, b, r, ax0, ay0, ax1, ay1, along_x=True, density=0.75):
        """Ряды контейнеров в прямоугольнике."""
        cl, cw, ch = 6.1, 2.44, 2.6
        if along_x:
            ny = int((ay1 - ay0 + 4.0) // (cw * 2 + 4.6))
            nx = int((ax1 - ax0 + 0.6) // (cl + 0.6))
            for jy in range(ny):
                yy = ay0 + jy * (cw * 2 + 4.6)
                for ix in range(nx):
                    xx = ax0 + ix * (cl + 0.6)
                    for kk in range(2):
                        if not r.chance(density):
                            continue
                        y_ = yy + kk * cw
                        stack = r.weighted([(1, 5), (2, 4), (3, 2)])
                        for s in range(stack):
                            self._box(xx, y_, CURB + s * ch, xx + cl, y_ + cw, CURB + (s + 1) * ch, 'corrugated', b.id,
                                      color=r.pick(self.CONTAINER_COLORS), uv_m=2.6, solid=(s == 0),
                                      top_tex='corrugated')
                        self.boxes[-stack]['stack_h'] = stack * ch
        else:
            nx = int((ax1 - ax0 + 4.0) // (cw * 2 + 4.6))
            ny = int((ay1 - ay0 + 0.6) // (cl + 0.6))
            for ix in range(nx):
                xx = ax0 + ix * (cw * 2 + 4.6)
                for jy in range(ny):
                    yy = ay0 + jy * (cl + 0.6)
                    for kk in range(2):
                        if not r.chance(density):
                            continue
                        x_ = xx + kk * cw
                        stack = r.weighted([(1, 5), (2, 4), (3, 2)])
                        for s in range(stack):
                            self._box(x_, yy, CURB + s * ch, x_ + cw, yy + cl, CURB + (s + 1) * ch, 'corrugated', b.id,
                                      color=r.pick(self.CONTAINER_COLORS), uv_m=2.6, solid=(s == 0),
                                      top_tex='corrugated')
                        self.boxes[-stack]['stack_h'] = stack * ch

    def _warehouse(self, b, r, wx0, wy0, wx1, wy1, door_side, name=None):
        tint = r.pick([(0.82, 0.84, 0.88), (0.62, 0.74, 0.86), (0.66, 0.8, 0.66), (0.86, 0.72, 0.6),
                       (0.9, 0.88, 0.8)])
        h = r.rangef(8.5, 12.0)
        bld = Building(wx0, wy0, wx1, wy1, h, 'fac_wh_win', b.id, gf_h=h - FLOOR_H, gf_tex='fac_wh', gf_bay=4.0,
                       bay_w=4.0, tint=tint, blank_tex='fac_wh', blank_tint=tint, roof_tex='corrugated',
                       roof_color=(0.6, 0.62, 0.66), name=name)
        self.buildings.append(bld)
        # ворота
        if door_side in ('s', 'n'):
            n = max(1, int((wx1 - wx0) // 14))
            for k in range(n):
                cx = wx0 + (wx1 - wx0) * (k + 0.5) / n
                self.special.setdefault('free_signs', []).append(
                    dict(x=cx, y=(wy0 - 0.06) if door_side == 's' else (wy1 + 0.06), z=CURB + 2.3, w=5.0, h=4.6,
                         tex='gf_garage', side=door_side, block=b.id, lit=True))
        else:
            n = max(1, int((wy1 - wy0) // 14))
            for k in range(n):
                cy = wy0 + (wy1 - wy0) * (k + 0.5) / n
                self.special.setdefault('free_signs', []).append(
                    dict(x=(wx0 - 0.06) if door_side == 'w' else (wx1 + 0.06), y=cy, z=CURB + 2.3, w=5.0, h=4.6,
                         tex='gf_garage', side=door_side, block=b.id, lit=True))
        return bld

    def _gen_indust(self, b, R, r):
        x0, y0, x1, y1 = R
        lm = LANDMARKS.get((b.i, b.j))
        self._ground(x0, y0, x1, y1, 'concrete', b.id, tile=5.0, color=(0.78, 0.78, 0.78))
        w, h = x1 - x0, y1 - y0
        layout = r.weighted([('wh', 4), ('wh2', 3), ('cont', 3), ('tanks', 2)])
        if lm == 'port':
            layout = 'wh'
        if layout == 'wh':
            bw, bh = w * r.rangef(0.5, 0.62), h * r.rangef(0.55, 0.7)
            wx0, wy0 = x0 + 3.0, y1 - 3.0 - bh
            bld = self._warehouse(b, r, wx0, wy0, wx0 + bw, wy0 + bh, 's', name=lm)
            if lm:
                self._big_sign(bld, 's', LANDMARK_SIGNS[lm], z=CURB + bld.h - 2.0)
                l = self._register_landmark(lm, bld, 's', b)
                l['yard'] = ((wx0 + wx0 + bw) * 0.5, wy0 - 7.0)
            self._containers(b, r, wx0 + bw + 6.0, y0 + 6.0, x1 - 3.0, y1 - 4.0, along_x=False)
            for k in range(3):
                if r.chance(0.6):
                    self._spot(x0 + 6.0 + k * 4.0, y0 + 6.0, math.pi / 2, 'I', kind=r.pick(['truck', 'van', 'pickup']),
                               block=b.id)
        elif layout == 'wh2':
            half = w * 0.5
            self._warehouse(b, r, x0 + 3.0, y0 + 14.0, x0 + half - 4.0, y1 - 3.0, 's')
            self._warehouse(b, r, x0 + half + 4.0, y0 + 3.0, x1 - 3.0, y1 - 14.0, 'n')
            self._spot(x0 + 8.0, y0 + 6.5, 0.0, 'I', kind=r.pick(['truck', 'van']), block=b.id)
            self._spot(x1 - 8.0, y1 - 6.5, math.pi, 'I', kind=r.pick(['truck', 'pickup']), block=b.id)
            self._prop('crate', x0 + half - 1.0, y0 + 8.0, 0.3, b.id)
            self._prop('crate', x0 + half + 0.6, y0 + 8.6, 1.1, b.id)
            self.pickup_spots.append((x0 + half, (y0 + y1) * 0.5, 'alley'))
        elif layout == 'cont':
            self._containers(b, r, x0 + 5.0, y0 + 6.0, x1 - 5.0, y1 - 6.0, along_x=True)
            self.packages.append((x0 + 2.0, y1 - 2.0))
        else:
            n = 0
            for ty in (y0 + h * 0.28, y0 + h * 0.72):
                for tx in (x0 + w * 0.22, x0 + w * 0.5, x0 + w * 0.78):
                    if r.chance(0.8):
                        rad = r.rangef(6.0, 8.5)
                        self.cyls.append(dict(x=tx, y=ty, z0=CURB, z1=CURB + r.rangef(9, 13), r=rad, tex='corrugated',
                                              color=r.pick([(0.92, 0.92, 0.92), (0.8, 0.82, 0.86), (0.9, 0.86, 0.7)]),
                                              block=b.id, solid=True, n=12, cap=True))
                        n += 1
            self.pickup_spots.append((x0 + w * 0.36, y0 + h * 0.5, 'lot'))
        # сетчатый забор по периметру с воротами
        self._fence_lot(b, r, x0, y0, x1, y1, 'nsew', gaps=True, h=2.4, inset=0.3)
        self._prop('lamp', x0 + 4.0, y0 + 4.0, math.pi / 4, b.id, park=True)
        self._prop('lamp', x1 - 4.0, y1 - 4.0, math.pi * 1.25, b.id, park=True)

    # ------------------------------------------------------------------
    # НАБЕРЕЖНАЯ
    # ------------------------------------------------------------------
    def _gen_beach(self, b, R, r):
        x0, y0, x1, y1 = R
        lm = LANDMARKS.get((b.i, b.j))
        lots = self._lots(R, 2, 2 if (y1 - y0) > 60 else 1)
        for k, (lx0, ly0, lx1, ly1, faces) in enumerate(lots):
            if lm == 'taxi' and k == 0:
                self._taxi_depot(b, r, lx0, ly0, lx1, ly1)
                continue
            if lm == 'spray2' and k == 0:
                self._ground(lx0, ly0, lx1, ly1, 'concrete', b.id, tile=4.0)
                bld = Building(lx0 + 4.0, ly0, lx0 + 4.0 + 17.5, ly0 + 15.0, GF_H + 1.2, 'fac_wh', b.id)
                self.buildings.append(bld)
                self._make_spray(b, bld, r, 'spray2')
                continue
            p = r.random()
            if p < 0.2:
                self._parking_lot(b, r, lx0, ly0, lx1, ly1, 'B', occupancy=0.6)
                continue
            self._ground(lx0, ly0, lx1, ly1, 'pavers', b.id, color=(1.0, 0.96, 0.9))
            ins = {s: (r.rangef(1.0, 4.0) if s in faces else 2.6) for s in 'nsew'}
            fx0, fy0, fx1, fy1 = lx0 + ins['w'], ly0 + ins['s'], lx1 - ins['e'], ly1 - ins['n']
            tall = (b.j == 1) and r.chance(0.6)
            floors = r.randint(6, 13) if tall else r.randint(1, 4)
            fac = r.pick(['fac_deco_a', 'fac_deco_b', 'fac_deco_c', 'fac_balcony_a', 'fac_balcony_b'])
            bld = Building(fx0, fy0, fx1, fy1, GF_H + floors * FLOOR_H, fac, b.id,
                           gf_tex=r.pick(['gf_shop_a', 'gf_shop_b', 'gf_shop_d', 'gf_shop_c']), sides_gf=faces,
                           blank_tex='concrete', roof_tex='roof_gravel')
            bld.roof_props = self._roof_props(r, fx0, fy0, fx1, fy1, bld.h, tall=tall)
            for s in faces:
                self._shop_signs(r, bld, s, BEACH_SIGNS, every=3)
            if tall and r.chance(0.5):
                self._big_sign(bld, faces[0], 'sign_hotel', z=CURB + bld.h - 3.0)
            if not tall and r.chance(0.3):
                bld.roof_props.append(('billboard', (fx0 + fx1) * 0.5, (fy0 + fy1) * 0.5, 's', r.pick(BILLBOARDS)))
            self.buildings.append(bld)
            for (px, py) in ((lx0 + 1.0, ly0 + 1.0), (lx1 - 1.0, ly1 - 1.0)):
                if r.chance(0.5):
                    self._prop('palm', px, py, 0.0, b.id, seed=r.randint(0, 9999), size=r.rangef(0.9, 1.2))
            if r.chance(0.2):
                self.pickup_spots.append((lx1 - 1.3 if 'e' not in faces else lx0 + 1.3,
                                          ly1 - 1.3 if 'n' not in faces else ly0 + 1.3, 'alley'))

    def _taxi_depot(self, b, r, lx0, ly0, lx1, ly1):
        self._ground(lx0, ly0, lx1, ly1, 'asphalt', b.id, tile=8.0)
        bld = Building(lx0 + 2.0, ly1 - 11.0, lx0 + 16.0, ly1 - 2.0, GF_H + 0.4, 'fac_conc_b', b.id, gf_h=GF_H + 0.4,
                       gf_tex='gf_office', sides_gf='s', name='taxi', tint=(1.0, 0.9, 0.5), blank_tex='concrete')
        bld.night = False
        bld.signs.append(dict(side='s', off=7.0, z=CURB + GF_H + 1.3, w=8.0, h=2.0, tex='sign_taxi'))
        self.buildings.append(bld)
        self._register_landmark('taxi', bld, 's', b)
        for k in range(5):
            x = lx0 + 5.0 + k * 3.4
            self.ground.append((x - 1.45, ly0 + 3.0, x + 1.45, ly0 + 8.6, 'parking', (2.9, 5.6), (1, 1, 1), b.id,
                                CURB + 0.02, 0))
            if k != 2:
                self._spot(x, ly0 + 5.8, math.pi / 2, 'B', kind='taxi', block=b.id)
        self.landmarks['taxi']['lot'] = (lx0 + 5.0 + 2 * 3.4, ly0 + 5.8)
        self._prop('lamp', lx1 - 3.0, ly0 + 3.0, math.pi * 0.75, b.id, park=True)

    # ------------------------------------------------------------------
    # ПАРК
    # ------------------------------------------------------------------
    def _gen_park(self, b, R, r):
        x0, y0, x1, y1 = R
        cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
        pw = 5.0        # ширина дорожки
        pr = 13.0       # половина центральной площади
        # газоны (4 четверти) и дорожки (крест) — без наложений
        self._ground(x0, y0, cx - pw / 2, cy - pw / 2, 'grass', b.id, tile=6.0)
        self._ground(cx + pw / 2, y0, x1, cy - pw / 2, 'grass', b.id, tile=6.0)
        self._ground(x0, cy + pw / 2, cx - pw / 2, y1, 'grass', b.id, tile=6.0)
        self._ground(cx + pw / 2, cy + pw / 2, x1, y1, 'grass', b.id, tile=6.0)
        self._ground(cx - pw / 2, y0, cx + pw / 2, y1, 'pavers', b.id, color=(0.92, 0.9, 0.84))
        self._ground(x0, cy - pw / 2, cx - pw / 2, cy + pw / 2, 'pavers', b.id, color=(0.92, 0.9, 0.84))
        self._ground(cx + pw / 2, cy - pw / 2, x1, cy + pw / 2, 'pavers', b.id, color=(0.92, 0.9, 0.84))
        # центральная площадь (поверх)
        self.ground.append((cx - pr, cy - pr, cx + pr, cy + pr, 'pavers', (3.0, 3.0), (1.0, 0.95, 0.86), b.id,
                            CURB + 0.03, 0))
        self._prop('fountain', cx, cy, 0.0, b.id, big=True)
        for a in range(8):
            ang = a * math.pi / 4 + math.pi / 8
            self._prop('bench', cx + math.cos(ang) * 10.5, cy + math.sin(ang) * 10.5, ang + math.pi, b.id)
        # пруд в северо-восточной четверти
        px, py = cx + (x1 - cx) * 0.55, cy + (y1 - cy) * 0.52
        self.special['pond'] = dict(x=px, y=py, rx=17.0, ry=12.0, block=b.id)
        # деревья
        placed = []
        tries = 0
        while len(placed) < 85 and tries < 900:
            tries += 1
            tx, ty = r.rangef(x0 + 3, x1 - 3), r.rangef(y0 + 3, y1 - 3)
            if abs(tx - cx) < pw / 2 + 2.2 or abs(ty - cy) < pw / 2 + 2.2:
                continue
            if abs(tx - cx) < pr + 2 and abs(ty - cy) < pr + 2:
                continue
            if ((tx - px) / 20.0) ** 2 + ((ty - py) / 15.0) ** 2 < 1.0:
                continue
            if any((tx - ox) ** 2 + (ty - oy) ** 2 < 30.0 for ox, oy in placed):
                continue
            placed.append((tx, ty))
            self._prop('tree', tx, ty, 0.0, b.id, seed=r.randint(0, 9999), size=r.rangef(0.9, 1.5))
        # фонари и скамейки вдоль дорожек
        for t in (-0.75, -0.45, 0.45, 0.75):
            self._prop('lamp', cx + pw / 2 + 0.8, cy + (y1 - y0) * 0.5 * t, math.pi, b.id, park=True)
            self._prop('lamp', cx + (x1 - x0) * 0.5 * t, cy + pw / 2 + 0.8, -math.pi / 2, b.id, park=True)
            self._prop('bench', cx - pw / 2 - 0.9, cy + (y1 - y0) * 0.5 * t + 4.0, 0.0, b.id)
            self._prop('bench', cx + (x1 - x0) * 0.5 * t + 4.0, cy - pw / 2 - 0.9, math.pi / 2, b.id)
        # беседка
        self._prop('gazebo', cx - (cx - x0) * 0.55, cy - (cy - y0) * 0.5, 0.0, b.id)
        self.packages.append((cx - (cx - x0) * 0.55, cy - (cy - y0) * 0.5))
        self.packages.append((px - 19.5, py + 4.0))
        self.pickup_spots.append((x0 + 6.0, y1 - 6.0, 'park'))
        self.pickup_spots.append((x1 - 6.0, y0 + 6.0, 'park'))
        # узлы пешеходного графа внутри парка
        self.special['park_paths'] = dict(cx=cx, cy=cy, x0=x0, y0=y0, x1=x1, y1=y1, block=b.id)

    # ------------------------------------------------------------------
    # уличная мебель по тротуарам квартала
    # ------------------------------------------------------------------
    def _gen_street_furniture(self, b, r):
        z = b.zone
        lamp_step = 27.0 if z != 'G' else 38.0
        off = 0.65                     # от бордюра
        sides = (
            ('s', b.x0, b.y0, b.x1, b.y0, 0.0, 1.0, -math.pi / 2),
            ('n', b.x1, b.y1, b.x0, b.y1, 0.0, -1.0, math.pi / 2),
            ('w', b.x0, b.y1, b.x0, b.y0, 1.0, 0.0, math.pi),
            ('e', b.x1, b.y0, b.x1, b.y1, -1.0, 0.0, 0.0),
        )
        for (side, ax, ay, bx, by, inx, iny, road_yaw) in sides:
            length = math.hypot(bx - ax, by - ay)
            dx, dy = (bx - ax) / length, (by - ay) / length
            n = max(1, int(length // lamp_step))
            step = length / n
            # фонари
            for k in range(n):
                t = (k + 0.5) * step
                self._prop('lamp', ax + dx * t + inx * off, ay + dy * t + iny * off, road_yaw, b.id)
            # мелочь между фонарями
            slots = int(length // 9.0)
            for k in range(slots):
                t = (k + 0.5) * (length / slots)
                # не ставим рядом с фонарями и углами
                if t < 7.0 or t > length - 7.0:
                    continue
                if abs(((t / step) % 1.0) - 0.5) < 0.12:
                    continue
                p = r.random()
                px, py = ax + dx * t + inx * off, ay + dy * t + iny * off
                if p < 0.10:
                    self._prop('hydrant', px, py, road_yaw, b.id)
                elif p < 0.24:
                    self._prop('bin', px, py, road_yaw, b.id)
                elif p < 0.31:
                    self._prop('newsbox', px, py, road_yaw + math.pi, b.id)
                elif p < 0.39 and z in ('D', 'B', 'O', 'P'):
                    self._prop('bench', ax + dx * t + inx * (SIDEWALK - 0.55), ay + dy * t + iny * (SIDEWALK - 0.55),
                               road_yaw, b.id)
                elif p < 0.60 and z in ('D', 'R', 'O', 'P'):
                    self._prop('tree', px + inx * 0.25, py + iny * 0.25, 0.0, b.id, seed=r.randint(0, 9999),
                               size=r.rangef(0.7, 0.95), pit=True)
                elif p < 0.66 and z == 'B':
                    self._prop('palm', px + inx * 0.25, py + iny * 0.25, 0.0, b.id, seed=r.randint(0, 9999),
                               size=r.rangef(0.9, 1.15))
                elif p < 0.70 and z in ('G', 'I'):
                    self._prop('cone', px, py, 0.0, b.id)
            # автобусная остановка на проспектах
            if r.chance(0.16) and length > 50 and z != 'P':
                t = length * 0.3
                self._prop('busstop', ax + dx * t + inx * (SIDEWALK - 0.75), ay + dy * t + iny * (SIDEWALK - 0.75),
                           road_yaw, b.id)

    # ------------------------------------------------------------------
    # побережье, пляж, причалы, мост
    # ------------------------------------------------------------------
    def _gen_outer(self):
        r = Rng(self.seed * 77 + 3)
        gx0, gx1, gy0, gy1 = self.grid_x0, self.grid_x1, self.grid_y0, self.grid_y1
        lx0, lx1, ly0, ly1 = self.land_x0, self.land_x1, self.land_y0, self.land_y1
        oc = self.outer_chunk
        sw = SIDEWALK

        def strip(x0, y0, x1, y1, tex, tile=6.0, color=(1, 1, 1), n=4, horiz=True):
            """Полоса земли, порезанная на куски (для отсечения по видимости)."""
            for k in range(n):
                if horiz:
                    a = x0 + (x1 - x0) * k / n
                    c = x0 + (x1 - x0) * (k + 1) / n
                    self._ground(a, y0, c, y1, tex, oc((a + c) * 0.5, (y0 + y1) * 0.5), tile=tile, color=color)
                else:
                    a = y0 + (y1 - y0) * k / n
                    c = y0 + (y1 - y0) * (k + 1) / n
                    self._ground(x0, a, x1, c, tex, oc((x0 + x1) * 0.5, (a + c) * 0.5), tile=tile, color=color)

        # внешние тротуары вдоль кольцевой дороги
        strip(gx0 - sw, gy0 - sw, gx1 + sw, gy0, 'sidewalk', 3.0)
        strip(gx0 - sw, gy1, gx1 + sw, gy1 + sw, 'sidewalk', 3.0)
        strip(gx0 - sw, gy0, gx0, gy1, 'sidewalk', 3.0, horiz=False)
        strip(gx1, gy0, gx1 + sw, gy1, 'sidewalk', 3.0, horiz=False)
        # юг: пляж
        strip(lx0, ly0, lx1, gy0 - sw, 'sand', 7.0)
        # север: трава
        strip(lx0, gy1 + sw, lx1, ly1, 'grass', 6.0)
        # запад: трава
        strip(lx0, gy0 - sw, gx0 - sw, gy1 + sw, 'grass', 6.0, horiz=False)
        # восток: бетон причалов
        strip(gx1 + sw, gy0 - sw, lx1, gy1 + sw, 'concrete', 5.0, color=(0.8, 0.8, 0.8), horiz=False)

        # фонари вдоль внешних тротуаров
        for k in range(int((gx1 - gx0) // 30)):
            x = gx0 + 15 + k * 30.0
            self._prop('lamp', x, gy0 - 0.65, math.pi / 2, oc(x, gy0 - 5))
            self._prop('lamp', x, gy1 + 0.65, -math.pi / 2, oc(x, gy1 + 5))
        for k in range(int((gy1 - gy0) // 30)):
            y = gy0 + 15 + k * 30.0
            self._prop('lamp', gx0 - 0.65, y, 0.0, oc(gx0 - 5, y))
            self._prop('lamp', gx1 + 0.65, y, math.pi, oc(gx1 + 5, y))

        # ---- пляж: пальмы, зонтики, вышки, пирс
        for k in range(46):
            x = lx0 + 12 + k * ((lx1 - lx0 - 24) / 45.0) + r.rangef(-4, 4)
            self._prop('palm', x, gy0 - sw - r.rangef(2.0, 7.0), 0.0, oc(x, gy0 - 10), seed=r.randint(0, 9999),
                       size=r.rangef(0.9, 1.3))
        for k in range(70):
            x = r.rangef(lx0 + 10, lx1 - 60)
            y = r.rangef(ly0 + 14, gy0 - sw - 10)
            self._prop('umbrella', x, y, r.rangef(0, 6.28), oc(x, y), color=r.randint(0, 5))
        for k in range(4):
            x = lx0 + 120 + k * 230.0
            self._prop('lifeguard', x, ly0 + 20.0, -math.pi / 2, oc(x, ly0 + 20))
        pier_x = self.xs[4]
        self.extra_land.append((pier_x - 4.0, ly0 - 62.0, pier_x + 4.0, ly0 + 12.0, CURB + 0.25))
        self.special['pier'] = dict(x0=pier_x - 4.0, y0=ly0 - 62.0, x1=pier_x + 4.0, y1=ly0 + 12.0, z=CURB + 0.25,
                                    chunk=oc(pier_x, ly0))
        self.packages.append((pier_x, ly0 - 58.0))
        self.pickup_spots.append((pier_x + 2.0, ly0 - 40.0, 'pier'))
        for k in range(8):
            self.pickup_spots.append((lx0 + 60 + k * 110.0, ly0 + 26.0, 'beach'))

        # ---- запад и север: деревья, камни
        for k in range(60):
            y = r.rangef(gy0, gy1)
            x = r.rangef(lx0 + 3, gx0 - sw - 3)
            self._prop('tree' if r.chance(0.8) else 'rock', x, y, r.rangef(0, 6.28), oc(x, y),
                       seed=r.randint(0, 9999), size=r.rangef(0.9, 1.5))
        for k in range(70):
            x = r.rangef(lx0 + 3, lx1 - 60)
            y = r.rangef(gy1 + sw + 3, ly1 - 3)
            if abs(x - self.xs[6]) < 14:
                continue
            self._prop('tree' if r.chance(0.8) else 'rock', x, y, r.rangef(0, 6.28), oc(x, y),
                       seed=r.randint(0, 9999), size=r.rangef(0.9, 1.5))
        self.packages.append((lx0 + 5.0, ly1 - 5.0))
        self.packages.append((lx0 + 6.0, gy0 + 120.0))

        # ---- парапет вдоль берега (запад, север, восток)
        wall_c = (0.74, 0.74, 0.72)
        bx = self.xs[6]                    # мост на проспекте i = 6
        bw = AVE_W * 0.5 + 1.0
        self._wall_run(lx0 + 0.3, gy0 - sw, lx0 + 0.3, ly1 - 0.3, 0.9, wall_c)
        self._wall_run(lx0 + 0.3, ly1 - 0.3, bx - bw, ly1 - 0.3, 0.9, wall_c)
        self._wall_run(bx + bw, ly1 - 0.3, lx1 - 0.3, ly1 - 0.3, 0.9, wall_c)
        # восток: парапет с разрывами у пирсов
        piers = []
        for k in range(3):
            py = gy0 + 110 + k * 190.0
            piers.append(py)
        prev = ly0 + 40.0
        for py in piers:
            self._wall_run(lx1 - 0.3, prev, lx1 - 0.3, py - 9.0, 0.9, wall_c)
            prev = py + 9.0
        self._wall_run(lx1 - 0.3, prev, lx1 - 0.3, ly1 - 0.3, 0.9, wall_c)
        self.special['piers'] = []
        for py in piers:
            pr = (lx1, py - 9.0, lx1 + 46.0, py + 9.0)
            self.extra_land.append((pr[0], pr[1], pr[2], pr[3], CURB))
            self.special['piers'].append(dict(x0=pr[0], y0=pr[1], x1=pr[2], y1=pr[3], chunk=oc(lx1, py)))
            ch = oc(lx1 - 5, py)
            # кнехты и ящики
            for kx in range(4):
                self._prop('bollard', lx1 + 6 + kx * 11.0, py - 8.2, 0.0, ch)
                self._prop('bollard', lx1 + 6 + kx * 11.0, py + 8.2, 0.0, ch)
            self._prop('crate', lx1 + 30.0, py + 3.0, 0.4, ch)
            self._prop('crate', lx1 + 31.6, py + 3.4, 1.0, ch)
        self.packages.append((lx1 + 43.0, piers[1]))
        self.pickup_spots.append((lx1 + 40.0, piers[0], 'pier'))
        self.pickup_spots.append((lx1 + 40.0, piers[2], 'pier'))

        # ---- причалы: краны, контейнеры, сухогруз
        fake = Block()
        fake.id = oc(gx1 + 20, 0.0)
        for k in range(2):
            cy = (piers[k] + piers[k + 1]) * 0.5
            fake.id = oc(gx1 + 20, cy)
            self._prop('crane', lx1 - 9.0, cy - 30.0, math.pi, fake.id)
            self._containers(fake, r, gx1 + sw + 8.0, cy - 56.0, lx1 - 18.0, cy + 60.0, along_x=False, density=0.6)
        # сухогруз у среднего пирса
        sy = piers[1] + 9.0 + 2.0
        self.special['ship'] = dict(x0=lx1 + 5.0, y0=sy, x1=lx1 + 75.0, y1=sy + 16.0, chunk=oc(lx1, sy + 8))
        self.boxes.append(dict(x0=lx1 + 5.0, y0=sy, z0=WATER_Z, x1=lx1 + 75.0, y1=sy + 16.0, z1=5.0, tex=None,
                               block=oc(lx1, sy + 8), color=(0, 0, 0), uv_m=3.0, solid=True, top_tex=None,
                               top_color=None, faces='', stack_h=6.0))
        # южная часть причалов: стоянка грузовиков
        fake.id = oc(gx1 + 20, gy0 + 40)
        for k in range(5):
            self._spot(gx1 + sw + 10.0 + k * 5.0, gy0 + 30.0, math.pi / 2, 'I',
                       kind=r.pick(['truck', 'van', 'pickup', 'truck']), block=fake.id)

        # ---- мост (закрыт)
        self.extra_land.append((bx - AVE_W * 0.5 - 1.5, ly1, bx + AVE_W * 0.5 + 1.5, ly1 + 320.0, 0.0))
        # подъезд к мосту: от кольцевой дороги до берега
        self.special['bridge'] = dict(x=bx, y0=gy1, y1=ly1 + 320.0, w=AVE_W, chunk=oc(bx, ly1))
        self._wall(bx - AVE_W * 0.5 - 1.0, ly1 + 6.0, bx + AVE_W * 0.5 + 1.0, ly1 + 6.0, 1.3, 'concrete',
                   oc(bx, ly1), color=(0.95, 0.55, 0.15), thick=0.9, kind='barrier', z0=0.0)
        self.special.setdefault('free_signs', []).append(
            dict(x=bx, y=ly1 + 5.4, z=2.6, w=9.0, h=2.25, tex='sign_closed', side='s', block=oc(bx, ly1), post=True))

    def _wall_run(self, x0, y0, x1, y1, h, color, seg=60.0):
        """Длинная стена, порезанная на куски по чанкам."""
        length = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(length // seg))
        for k in range(n):
            ax = x0 + (x1 - x0) * k / n
            ay = y0 + (y1 - y0) * k / n
            bx = x0 + (x1 - x0) * (k + 1) / n
            by = y0 + (y1 - y0) * (k + 1) / n
            self._wall(ax, ay, bx, by, h, 'concrete', self.outer_chunk((ax + bx) * 0.5, (ay + by) * 0.5),
                       color=color, thick=0.5, kind='wall')

    # ------------------------------------------------------------------
    def _gen_extras(self):
        """Светофоры, особые точки."""
        # светофорные столбы: для каждого въезда на перекрёсток
        self.signals = []        # dict(node=(i,j), dir=..., x, y, yaw)
        for (i, j), n in self.nodes.items():
            if len(n.exits) < 3:
                continue
            for d in n.exits:
                # d — сторона, С которой машины въезжают (они едут в противоположную сторону)
                if d == 's':          # едут на север, столб справа-снизу
                    x, y, yaw = n.x + n.hw + 0.7, n.y - n.hh - 0.7, math.pi / 2
                elif d == 'n':        # едут на юг
                    x, y, yaw = n.x - n.hw - 0.7, n.y + n.hh + 0.7, -math.pi / 2
                elif d == 'w':        # едут на восток
                    x, y, yaw = n.x - n.hw - 0.7, n.y - n.hh - 0.7, 0.0
                else:                 # едут на запад
                    x, y, yaw = n.x + n.hw + 0.7, n.y + n.hh + 0.7, math.pi
                b = self.block_at(x, y)
                chunk = b.id if b is not None else self.outer_chunk(x, y)
                self.signals.append(dict(node=(i, j), dir=d, x=x, y=y, yaw=yaw, block=chunk))
        # стартовая точка игрока
        sh = self.landmarks.get('safehouse')
        if sh:
            self.start_pos = (sh['door'][0], sh['door'][1], math.pi / 2 * -1)
        else:
            self.start_pos = (0.0, 0.0, 0.0)
