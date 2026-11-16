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
from .terrain import Terrain, C_FOREST, C_ROCK, C_GRASS

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
# Где на плитке первого этажа проём для двери: вид входа, середина проёма, его полуширина (в долях секции)
# и высота (в долях высоты первого этажа).  Снято с самих текстур.
ENTRY_TILES = {
    'gf_shop_a': ('shop', 0.826, 0.135, 0.742), 'gf_shop_b': ('shop', 0.826, 0.135, 0.742),
    'gf_shop_c': ('shop', 0.826, 0.135, 0.742), 'gf_shop_d': ('shop', 0.826, 0.135, 0.742),
    'gf_office': ('office', 0.502, 0.158, 0.549),
    'gf_garage': ('garage', 0.496, 0.402, 0.777),
}
FLOOR_H = 3.2          # высота этажа
GF_H = 4.0             # высота первого этажа
WATER_Z = -0.7

# ---------------------------------------------------------------------------
# раскладка мира
# ---------------------------------------------------------------------------
# Мир — узор из «клеток» между линиями дорог.  Линии общие на весь мир (xs, ys), но дороги идут
# только там, где к линии примыкает квартал, и там, где они проложены явно (трасса, мосты).
# Клетка — либо квартал с зоной, либо пусто: море или дикая земля, это решает рельеф.
#
# зоны:  G трущобы, R спальный, I промзона/порт, O старый город, D деловой центр, P парк,
#        B набережная — остров, сам Порт-Глухов;
#        V центр Заречья, S слобода (частные дома) — северный берег, за Большим мостом;
#        H нефтебаза, A аэродром, L посёлок Маячный — восточный берег, за Портовым мостом.
CELLS = [               # сверху — север (j = 13), слева — запад (i = 0)
    '....SSS........',
    '..SSSVVSS......',
    '..SVVVVVS......',
    '..SSVVVS.......',
    '...SSVS........',
    '...............',
    '.GGRRRRII...AAA',
    'GGGRRRRIII..AAA',
    'OOODDDRRII.HH..',
    'OODDPPDDII.HH..',
    'OODDPPDDII..LL.',
    'OOODDDDDII.....',
    'BBBBBBBBB......',
    '.BBBBBBB.......',
]
X0, Y0 = -459.0, -350.0                     # юго-западный угол сетки (край самой западной и самой южной дороги)
BLOCK_W = [72, 72, 72, 86, 72, 72, 86, 72, 86, 86, 250, 84, 96, 84, 110]     # i = 0..14 (запад -> восток)
BLOCK_H = [64, 72, 72, 80, 80, 72, 72, 72, 290, 70, 80, 72, 84, 70]          # j = 0..13 (юг -> север)
ROAD_X_AVE = [True, False, False, True, False, False, True, False, True, False, True,
              False, True, False, False, False]
ROAD_Y_AVE = [True, False, True, False, False, True, False, False, True,
              True, False, True, False, False, False]
# большие кварталы из нескольких клеток: (i0, j0, i1, j1)
PARK_I0, PARK_I1, PARK_J0, PARK_J1 = 4, 5, 3, 4               # парк занимает 2x2 клетки
SUPER = [(PARK_I0, PARK_J0, PARK_I1, PARK_J1), (12, 6, 14, 7)]
# дороги вне кварталов: трасса вокруг залива и два моста
#   ('h', i, j) — отрезок от узла (i, j) к (i + 1, j);  ('v', i, j) — от узла (i, j) к (i, j + 1)
EXTRA_SEGS = [('h', 9, 11), ('h', 10, 11), ('h', 11, 11), ('v', 12, 10), ('v', 12, 9), ('v', 12, 8)]
BRIDGES = {
    ('v', 6, 8): dict(name='north', height=9.0, ramp=95.0, style='suspension'),
    ('h', 10, 5): dict(name='east', height=7.0, ramp=80.0, style='girder'),
}
DOCK_W = 52.0           # ширина бетонных причалов к востоку от порта
BEACH_W = 56.0          # ширина городского пляжа
# на что похожа зона (жители, машины, звуки): новые зоны ведут себя как знакомые
ZONE_STYLE = {'V': 'O', 'S': 'R', 'L': 'R', 'H': 'I', 'A': 'I'}

ZONE_NAMES = {
    'G': 'Ржавый квартал',
    'R': 'Сосновка',
    'I': 'Порт',
    'O': 'Старый город',
    'D': 'Деловой центр',
    'P': 'Центральный парк',
    'B': 'Набережная',
    'V': 'Заречье',
    'S': 'Слобода',
    'H': 'Нефтегавань',
    'A': 'Аэродром',
    'L': 'Маячный',
    'beach': 'Городской пляж',
    'docks': 'Причалы',
    'ship': 'Сухогруз «Арктур»',
    'coast': 'Побережье',
    'sea': 'Залив',
    'road': 'Трасса',
    'wild': 'Предгорья',
    'bridge_north': 'Большой мост',
    'bridge_east': 'Портовый мост',
}

# Названия улиц: линии сетки с запада на восток и с юга на север.  Проспекты — широкие (см. ROAD_*_AVE).
STREETS_X = ['Западная набережная', 'Кузнечная улица', 'Гончарная улица', 'Адмиральский проспект', 'Садовая улица',
             'Театральная улица', 'проспект Мира', 'Якорная улица', 'Портовое шоссе', 'Канатная улица',
             'Причальный проезд', 'Заводская улица', 'Нефтяное шоссе', 'Маячная улица', 'Лётная улица',
             'Восточная улица']
STREETS_Y = ['Морской проспект', 'Пляжная улица', 'Полицейский проспект', 'Банковская улица', 'Парковая улица',
             'Портовый проспект', 'Сосновая улица', 'Ржавая улица', 'Северная набережная',
             'Речной проспект', 'Чайная улица', 'Заречный проспект', 'Слободская улица', 'Огородная улица',
             'Дальняя улица']
# номера домов для сюжета: место -> (улица, дом)
ADDRESS = {'safehouse': ('Сосновая', 12), 'bruce': ('Сосновая', 31), 'boss': ('Банковская', 21)}

# корабль у среднего пирса: высота палубы над причалом
SHIP_DECK = 3.4

# особые здания:  (i, j) квартала -> (имя, подсказка)
LANDMARKS = {
    (1, 3): 'terminal',         # общага у конечной автобуса: здесь Макс выходит в начале игры
    (3, 6): 'safehouse',        # дом Макса с гаражом на Сосновой
    (6, 6): 'bruce',            # дом Брюса, брата Макса
    (6, 3): 'boss',             # казино, где сидит босс
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
    (12, 5): 'zakhar',          # лодочный сарай в Нефтегавани
    (5, 10): 'grom',            # чайная в Заречье
}

LANDMARK_SIGNS = {
    'terminal': 'sign_safehouse', 'boss': 'sign_casino', 'vano': 'sign_garage', 'spray': 'sign_spray', 'spray2': 'sign_spray',
    'guns': 'sign_guns', 'guns2': 'sign_guns', 'rosa': 'sign_rosa', 'hospital': 'sign_hospital',
    'police': 'sign_police', 'bank': 'sign_bank', 'prof': 'sign_club', 'taxi': 'sign_taxi',
    'gas': 'sign_gas', 'port': 'sign_port', 'zakhar': 'sign_boats', 'grom': 'sign_tea',
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
    __slots__ = ('i', 'j', 'x', 'y', 'hw', 'hh', 'exits', 'phase', 'rural', 'through')
    # exits: dict  'e'/'w'/'n'/'s' -> (ni, nj)
    # rural: перекрёсток за городом (без тротуаров и светофоров)
    # through: дорога просто проходит насквозь (два выезда друг напротив друга)


def _split(length, target, minimum=1):
    n = max(minimum, int(round(length / float(target))))
    return [length / n] * n


def _axis(v, lines, widths):
    """Где точка относительно линий дорог вдоль одной оси.

    ('l', i) — на линии i (в полосе её дороги);  ('b', i) — между линиями i и i + 1;
    (None, 0) — за пределами сетки."""
    i = bisect_right(lines, v) - 1
    if i < 0:
        return ('l', 0) if v >= lines[0] - widths[0] * 0.5 else (None, 0)
    if v <= lines[i] + widths[i] * 0.5:
        return ('l', i)
    if i + 1 < len(lines):
        if v >= lines[i + 1] - widths[i + 1] * 0.5:
            return ('l', i + 1)
        return ('b', i)
    return (None, 0)


class City(object):

    def __init__(self, seed=1337, terrain=None, root=None):
        """terrain — готовый Terrain;  root — папка игры (рельеф читается из assets/terrain).
        С пустым Terrain() город тоже строится: земля вокруг считается плоской — так его строит
        tools/gen_terrain.py, которому как раз и нужно узнать раскладку."""
        self.seed = seed
        self.rng = Rng(seed)
        if terrain is None:
            if root is None:
                from .settings import find_root
                root = find_root()
            terrain = Terrain(root)
        self.terrain = terrain

        # --- сетка линий -------------------------------------------------
        self.nx = len(BLOCK_W)
        self.ny = len(BLOCK_H)
        self.wx = [AVE_W if a else ST_W for a in ROAD_X_AVE]      # ширины вертикальных дорог
        self.wy = [AVE_W if a else ST_W for a in ROAD_Y_AVE]
        self.xs = []
        x = X0
        for i in range(self.nx + 1):
            x += self.wx[i] * 0.5
            self.xs.append(x)
            x += self.wx[i] * 0.5
            if i < self.nx:
                x += BLOCK_W[i]
        self.ys = []
        y = Y0
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
        # клетки: (i, j) -> зона
        self.cells = {}
        for row, line in enumerate(CELLS):
            j = self.ny - 1 - row
            for i, ch in enumerate(line):
                if ch != '.':
                    self.cells[(i, j)] = ch
        # остров — прежний город: по нему считаются пляж и причалы
        self.isle_i1, self.isle_j1 = 9, 7

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
        self.pads = []                # ровные площадки вне кварталов: (x0, y0, x1, y1, z, зона)
        self._pad_grid = {}
        self.extra_land = []          # то же для карты: (x0, y0, x1, y1, z)
        self.bridges = []             # отрезки-мосты (dict отрезка)
        self.walk_strips = []         # внешние тротуары: (x0, y0, x1, y1)
        self.covered = []             # крытые места, куда можно въехать: (x0, y0, x1, y1, высота потолка)
        self.ramps = []               # наклонные площадки: индексы в self.pads
        self._chunk_ids = {}
        self.n_chunks = 0

        self._make_roads()
        self._make_blocks()
        self._outer_sidewalks()
        for b in self.blocks:
            self._gen_block(b)
        self._gen_coast()
        self._gen_country()
        self._gen_extras()
        self._align_doors()
        self._clear_driveways()
        self.n_chunks = self._outer_chunk_base + len(self._chunk_ids)

    def landmark_building(self, name):
        """Здание особого места (по его прямоугольнику) или None."""
        lm = self.landmarks.get(name)
        if lm is None:
            return None
        x0, y0, x1, y1 = lm['rect']
        for b in self.buildings:
            if abs(b.x0 - x0) < 0.01 and abs(b.y0 - y0) < 0.01 and abs(b.x1 - x1) < 0.01 and abs(b.y1 - y1) < 0.01:
                return b
        return None

    def entry_bay(self, name):
        """Секция первого этажа, в которой стоит дверь особого места: (x0 секции, ширина секции, вид входа).

        Дверь ставится не посреди здания, а туда, где на плитке первого этажа нарисован проём: в дверь витрины,
        в среднее стекло офисной стены, на место ворот гаража.  None — у здания такой плитки нет."""
        lm = self.landmarks.get(name)
        b = self.landmark_building(name)
        if lm is None or b is None or lm.get('facing') != 's' or b.gf_h <= 0.01 or 's' not in b.sides_gf:
            return None
        ent = ENTRY_TILES.get(b.gf_tex)
        if ent is None:
            return None
        L = b.x1 - b.x0
        n = max(1, int(round(L / b.gf_bay)))
        bw = L / n
        k = min(n - 1, max(0, int(((b.x0 + b.x1) * 0.5 - b.x0) / bw)))
        return b.x0 + k * bw, bw, ent

    def _align_doors(self):
        """Двери особых мест — в проёмы, нарисованные на фасаде; перед дверью на тротуаре ничего не стоит."""
        for name, lm in self.landmarks.items():
            if lm.get('facing') != 's':
                continue
            bay = self.entry_bay(name)
            if bay is not None:
                x = bay[0] + bay[2][1] * bay[1]
                lm['door'] = (x, lm['door'][1])
                lm['road'] = (x, lm['road'][1])
            dx, wy = lm['door'][0], lm['rect'][1]
            # до самого бордюра: у отодвинутых от дороги домов деревья стоят в четырёх метрах от стены
            self.props = [p for p in self.props
                          if not (abs(p["x"] - dx) < (2.6 if p["kind"] == "tree" else 1.5) and
                                  wy - SIDEWALK - 2.5 < p["y"] < wy + 0.2)]

    def _clear_driveways(self):
        """Перед воротами гаража на тротуаре ничего не стоит: ни дерева, ни урны, ни фонаря."""
        g = self.special.get('garage')
        if g is None:
            return
        x0, y0, x1, y1 = g['rect']
        fy = g['front'][1]
        self.props = [p for p in self.props
                      if not (x0 - 0.8 < p['x'] < x1 + 0.8 and fy - 1.5 < p['y'] < y0 and p['kind'] != 'mailbox')]

    def signature(self):
        """Подпись раскладки: рельеф построен под конкретные дороги и кварталы."""
        import hashlib
        h = hashlib.md5()
        h.update(repr((X0, Y0, BLOCK_W, BLOCK_H, ROAD_X_AVE, ROAD_Y_AVE, CELLS, SUPER, EXTRA_SEGS,
                       sorted((k, sorted(v.items())) for k, v in BRIDGES.items()), DOCK_W, BEACH_W)).encode())
        return h.hexdigest()[:16]

    # ------------------------------------------------------------------
    # дороги
    # ------------------------------------------------------------------
    def _seg_exists_h(self, i, j):
        """горизонтальный отрезок между узлами (i, j) и (i+1, j)"""
        return ('h', i, j) in self.segs

    def _seg_exists_v(self, i, j):
        """вертикальный отрезок между узлами (i, j) и (i, j+1)"""
        return ('v', i, j) in self.segs

    def _make_roads(self):
        cells = self.cells
        keys = set()
        for (i, j) in cells:
            keys.add(('h', i, j))
            keys.add(('h', i, j + 1))
            keys.add(('v', i, j))
            keys.add(('v', i + 1, j))
        for (i0, j0, i1, j1) in SUPER:                 # внутри большого квартала дорог нет
            for i in range(i0, i1 + 1):
                for j in range(j0 + 1, j1 + 1):
                    keys.discard(('h', i, j))
            for i in range(i0 + 1, i1 + 1):
                for j in range(j0, j1 + 1):
                    keys.discard(('v', i, j))
        keys.update(EXTRA_SEGS)
        keys.update(BRIDGES)
        # отрезки дорог: ('h'|'v', i, j) -> dict
        self.segs = {}
        for key in sorted(keys):
            kind, i, j = key
            if kind == 'h':
                sides = {'n': (i, j) in cells, 's': (i, j - 1) in cells}
                seg = dict(kind='h', i=i, j=j, width=self.wy[j], ave=ROAD_Y_AVE[j],
                           a=self.xs[i] + self.wx[i] * 0.5, b=self.xs[i + 1] - self.wx[i + 1] * 0.5,
                           c=self.ys[j])
            else:
                sides = {'e': (i, j) in cells, 'w': (i - 1, j) in cells}
                seg = dict(kind='v', i=i, j=j, width=self.wx[i], ave=ROAD_X_AVE[i],
                           a=self.ys[j] + self.wy[j] * 0.5, b=self.ys[j + 1] - self.wy[j + 1] * 0.5,
                           c=self.xs[i])
            seg['key'] = key
            seg['sides'] = sides
            seg['bridge'] = BRIDGES.get(key)
            seg['rural'] = not any(sides.values())      # за городом: ни тротуаров, ни «зебр»
            self.segs[key] = seg
            if seg['bridge']:
                self.bridges.append(seg)
        self.nodes = {}

        def node(i, j):
            n = self.nodes.get((i, j))
            if n is None:
                n = RoadNode()
                n.i, n.j = i, j
                n.x, n.y = self.xs[i], self.ys[j]
                n.hw, n.hh = self.wx[i] * 0.5, self.wy[j] * 0.5
                n.exits = {}
                n.phase = ((i * 7 + j * 13) % 10) * 3.1
                n.rural = True
                n.through = False
                self.nodes[(i, j)] = n
            return n
        for (kind, i, j), seg in sorted(self.segs.items()):
            if kind == 'h':
                a, b = node(i, j), node(i + 1, j)
                a.exits['e'] = (i + 1, j)
                b.exits['w'] = (i, j)
            else:
                a, b = node(i, j), node(i, j + 1)
                a.exits['n'] = (i, j + 1)
                b.exits['s'] = (i, j)
            if not seg['rural'] and not seg['bridge']:
                a.rural = b.rural = False
        for n in self.nodes.values():
            ex = set(n.exits)
            n.through = ex in ({'e', 'w'}, {'n', 's'})

    def bridge_z(self, seg, t):
        """Высота полотна моста на расстоянии t от начала отрезка."""
        br = seg['bridge']
        d = min(t, (seg['b'] - seg['a']) - t)
        if d <= 0.0:
            return 0.0
        r = br['ramp']
        if d >= r:
            return br['height']
        u = d / r
        return br['height'] * u * u * (3.0 - 2.0 * u)

    def _make_blocks(self):
        supers = {}
        for sb in SUPER:
            for ii in range(sb[0], sb[2] + 1):
                for jj in range(sb[1], sb[3] + 1):
                    supers[(ii, jj)] = sb
        for j in range(self.ny):
            for i in range(self.nx):
                zone = self.cells.get((i, j))
                if zone is None:
                    continue
                sb = supers.get((i, j))
                if sb is not None and (i, j) != (sb[0], sb[1]):
                    continue
                b = Block()
                b.id = len(self.blocks)
                b.i, b.j = i, j
                b.i1, b.j1 = (sb[2], sb[3]) if sb is not None else (i, j)
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

    def _outer_sidewalks(self):
        """Тротуары с той стороны улицы, где квартала нет (край города).

        Каждая полоса — ещё и ровная площадка: по ней ходят на высоте бордюра."""
        sw = SIDEWALK
        strips = self.walk_strips
        for seg in self.segs.values():
            if seg['rural'] or seg['bridge']:
                continue
            hw = seg['width'] * 0.5
            a, b, c = seg['a'], seg['b'], seg['c']
            if seg['kind'] == 'h':
                if not seg['sides']['n']:
                    strips.append((a, c + hw, b, c + hw + sw))
                if not seg['sides']['s']:
                    strips.append((a, c - hw - sw, b, c - hw))
            else:
                if not seg['sides']['e']:
                    strips.append((c + hw, a, c + hw + sw, b))
                if not seg['sides']['w']:
                    strips.append((c - hw - sw, a, c - hw, b))
        for (i, j), n in self.nodes.items():
            if n.rural:
                continue
            x, y, hw, hh = n.x, n.y, n.hw, n.hh
            # стороны перекрёстка, с которых нет выезда и нет квартала
            if 'n' not in n.exits and (i, j) not in self.block_grid and (i - 1, j) not in self.block_grid:
                strips.append((x - hw, y + hh, x + hw, y + hh + sw))
            if 's' not in n.exits and (i, j - 1) not in self.block_grid and (i - 1, j - 1) not in self.block_grid:
                strips.append((x - hw, y - hh - sw, x + hw, y - hh))
            if 'e' not in n.exits and (i, j) not in self.block_grid and (i, j - 1) not in self.block_grid:
                strips.append((x + hw, y - hh, x + hw + sw, y + hh))
            if 'w' not in n.exits and (i - 1, j) not in self.block_grid and (i - 1, j - 1) not in self.block_grid:
                strips.append((x - hw - sw, y - hh, x - hw, y + hh))
            # углы
            for (ci, cj, sx, sy) in ((i, j, 1, 1), (i - 1, j, -1, 1), (i, j - 1, 1, -1), (i - 1, j - 1, -1, -1)):
                if (ci, cj) in self.block_grid:
                    continue
                # за городской чертой угол нужен, только если к нему подходит хотя бы одна городская улица
                ex_x = 'e' if sx > 0 else 'w'
                ex_y = 'n' if sy > 0 else 's'
                x0 = x + hw if sx > 0 else x - hw - sw
                y0 = y + hh if sy > 0 else y - hh - sw
                strips.append((x0, y0, x0 + sw, y0 + sw))
        for (x0, y0, x1, y1) in strips:
            self._pad(x0, y0, x1, y1, CURB, None)

    # ------------------------------------------------------------------
    # площадки
    # ------------------------------------------------------------------
    def _pad(self, x0, y0, x1, y1, z, zone=None, on_map=False, slope=None):
        """Ровная площадка вне кварталов (причал, пирс, палуба, внешний тротуар).

        slope=(ось, z_начала, z_конца) делает площадку наклонной: высота меняется вдоль оси 'x' или 'y'
        от меньшей координаты к большей (трап, аппарель).  z в этом случае — её наибольшая высота."""
        k = len(self.pads)
        self.pads.append((x0, y0, x1, y1, z, zone, slope))
        if slope is not None:
            self.ramps.append(k)
        for cx in range(int(x0 // 40.0), int(x1 // 40.0) + 1):
            for cy in range(int(y0 // 40.0), int(y1 // 40.0) + 1):
                self._pad_grid.setdefault((cx, cy), []).append(k)
        if on_map:
            self.extra_land.append((x0, y0, x1, y1, z))

    def pad_at(self, x, y):
        """Площадка под точкой: (x0, y0, x1, y1, z, зона) или None.  Из нескольких — самая высокая."""
        lst = self._pad_grid.get((int(x // 40.0), int(y // 40.0)))
        if not lst:
            return None
        best = None
        bz = 0.0
        pads = self.pads
        for k in lst:
            p = pads[k]
            if p[0] <= x <= p[2] and p[1] <= y <= p[3]:
                z = self.pad_z(p, x, y)
                if best is None or z > bz:
                    best = p
                    bz = z
        return best

    @staticmethod
    def pad_z(p, x, y):
        """Высота площадки в точке (у наклонной зависит от места)."""
        s = p[6]
        if s is None:
            return p[4]
        if s[0] == 'x':
            t = (x - p[0]) / (p[2] - p[0])
        else:
            t = (y - p[1]) / (p[3] - p[1])
        return s[1] + (s[2] - s[1]) * (0.0 if t < 0.0 else (1.0 if t > 1.0 else t))

    def ceiling(self, x, y):
        """Высота потолка над точкой, если она под крышей гаража или покрасочной (иначе None)."""
        for (x0, y0, x1, y1, z) in self.covered:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return z
        return None

    def street_name(self, x, y, reach=17.0):
        """Название улицы, на которой или рядом с которой стоит точка (None — улицы рядом нет)."""
        kind, obj = self.where(x, y)
        if kind == 'seg':
            if obj['bridge'] is not None:
                return None                              # у мостов свои названия — как у районов
            return STREETS_Y[obj['j']] if obj['kind'] == 'h' else STREETS_X[obj['i']]
        best = None
        bd = reach
        i, j = self.cell_at(x, y)
        for jj in (j, j + 1):
            if 0 <= jj < len(self.ys) and abs(self.ys[jj] - y) < bd and (self._seg_exists_h(i, jj) if 0 <= i < self.nx
                                                                           else False):
                bd = abs(self.ys[jj] - y)
                best = STREETS_Y[jj]
        for ii in (i, i + 1):
            if 0 <= ii < len(self.xs) and abs(self.xs[ii] - x) < bd and (self._seg_exists_v(ii, j) if 0 <= j < self.ny
                                                                           else False):
                bd = abs(self.xs[ii] - x)
                best = STREETS_X[ii]
        return best

    def address(self, name):
        """Адрес сюжетного места строкой: «Сосновая, 12»."""
        a = ADDRESS.get(name)
        return '%s, %d' % a if a else ''

    # ------------------------------------------------------------------
    # запросы
    # ------------------------------------------------------------------
    def cell_at(self, x, y):
        """Индексы клетки (i, j) для точки (могут быть вне сетки: -1 / nx)."""
        i = bisect_right(self.xs, x) - 1
        j = bisect_right(self.ys, y) - 1
        return i, j

    def block_at(self, x, y):
        i, j = self.cell_at(x, y)
        b = self.block_grid.get((i, j))
        if b is not None and b.x0 <= x <= b.x1 and b.y0 <= y <= b.y1:
            return b
        return None

    def where(self, x, y):
        """Что в точке: ('block', Block), ('seg', отрезок), ('node', узел) или (None, None)."""
        kx, i = _axis(x, self.xs, self.wx)
        if kx is None:
            return None, None
        ky, j = _axis(y, self.ys, self.wy)
        if ky is None:
            return None, None
        bg = self.block_grid
        if kx == 'b':
            if ky == 'b':
                b = bg.get((i, j))
                return ('block', b) if b is not None else (None, None)
            seg = self.segs.get(('h', i, j))
            if seg is not None:
                return 'seg', seg
            b = bg.get((i, j))                      # линия внутри большого квартала (парк, аэродром)
            if b is not None and bg.get((i, j - 1)) is b:
                return 'block', b
            return None, None
        if ky == 'b':
            seg = self.segs.get(('v', i, j))
            if seg is not None:
                return 'seg', seg
            b = bg.get((i, j))
            if b is not None and bg.get((i - 1, j)) is b:
                return 'block', b
            return None, None
        n = self.nodes.get((i, j))
        if n is not None:
            return 'node', n
        b = bg.get((i, j))
        if b is not None and bg.get((i - 1, j - 1)) is b:
            return 'block', b
        return None, None

    def on_road(self, x, y):
        """Точка на проезжей части?"""
        return self.where(x, y)[0] in ('seg', 'node')

    def in_water(self, x, y):
        kind, obj = self.where(x, y)
        if kind is not None:
            return False
        if self.pad_at(x, y) is not None:
            return False
        return self.terrain.height(x, y) < WATER_Z

    def ground_z(self, x, y):
        kind, obj = self.where(x, y)
        if kind == 'block':
            return CURB
        if kind == 'node':
            return 0.0
        if kind == 'seg':
            if obj['bridge'] is None:
                return 0.0
            return self.bridge_z(obj, (x if obj['kind'] == 'h' else y) - obj['a'])
        p = self.pad_at(x, y)
        if p is not None:
            return p[4] if p[6] is None else self.pad_z(p, x, y)
        return self.terrain.height(x, y)

    def zone_at(self, x, y):
        kind, obj = self.where(x, y)
        if kind == 'block':
            return obj.zone
        if kind == 'seg':
            if obj['bridge'] is not None:
                return 'bridge_' + obj['bridge']['name']
            i, j = obj['i'], obj['j']
            near = ((i, j), (i, j - 1)) if obj['kind'] == 'h' else ((i, j), (i - 1, j))
            for c in near:
                z = self.cells.get(c)
                if z is not None:
                    return z
            return 'road'
        if kind == 'node':
            i, j = obj.i, obj.j
            for c in ((i, j), (i - 1, j), (i, j - 1), (i - 1, j - 1)):
                z = self.cells.get(c)
                if z is not None:
                    return z
            return 'road'
        p = self.pad_at(x, y)
        if p is not None and p[5]:
            return p[5]
        if self.terrain.height(x, y) < WATER_Z:
            return 'sea'
        # суша вне кварталов: чей это берег
        ix1 = self.xs[self.isle_i1 + 1] + 80.0
        iy1 = self.ys[self.isle_j1 + 1] + 80.0
        if x < ix1 and y < iy1:
            if y < self.ys[1]:
                return 'beach'
            return 'coast'
        return 'wild'

    def zone_style(self, zone):
        """Знакомая зона, на которую эта похожа жителями и машинами (для новых районов)."""
        if zone in ZONE_STYLE:
            return ZONE_STYLE[zone]
        if zone in ('road', 'wild') or zone.startswith('bridge'):
            return 'R'
        if zone in ('beach', 'coast', 'sea'):
            return 'B'
        if zone == 'docks':
            return 'I'
        return zone

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
        """Номер «чанка» для объектов за пределами кварталов (плитка 160 x 160 м)."""
        key = (int(x // 160.0), int(y // 160.0))
        k = self._chunk_ids.get(key)
        if k is None:
            k = self._chunk_ids[key] = self._outer_chunk_base + len(self._chunk_ids)
        return k

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
                                h=1.35, tex=r.pick(pool), shop=True))

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
    def _block_seed(self, b):
        """Число, от которого зависит застройка квартала.  У кварталов острова оно такое же, каким было,
        когда город состоял из одного острова 10 x 8: там всё выверено, и вид меняться не должен."""
        if b.i <= self.isle_i1 and b.j <= self.isle_j1:
            k = b.j * 10 + b.i
            return k - (k > 35) - (k > 44) - (k > 45)       # три клетки парка своих номеров не имели
        return 500 + b.j * 37 + b.i

    def _gen_block(self, b):
        r = Rng(self.seed * 1000 + self._block_seed(b) * 17 + 5)
        R = b.interior()
        z = b.zone
        if z == 'P':
            self._gen_park(b, R, r)
        elif z == 'D':
            self._gen_downtown(b, R, r)
        elif z == 'O':
            self._gen_old(b, R, r)
        elif z == 'V':
            self._gen_old(b, R, r, floors=(1, 2))       # Заречье — городок в два этажа
        elif z == 'G':
            self._gen_ghetto(b, R, r)
        elif z in ('R', 'S', 'L'):
            self._gen_resid(b, R, r)
        elif z in ('I', 'H'):
            self._gen_indust(b, R, r)
        elif z == 'A':
            self._gen_airfield(b, R, r)
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
        elif name == 'boss':
            # казино: невысокое здание в духе ар-деко, перед входом — стоянка для «своих»
            bld = Building(fx0, fy0, fx1, fy1, GF_H + 4 * FLOOR_H, 'fac_deco_b', b.id, gf_tex='gf_office',
                           tint=(1.0, 0.93, 0.86), sides_gf='s', name=name, blank_tex='concrete',
                           roof_tex='roof_gravel')
            for cx in (fx0 + 2.5, fx1 - 2.5):
                self.cyls.append(dict(x=cx, y=fy0 - 0.8, z0=CURB, z1=CURB + GF_H, r=0.4, tex='concrete',
                                      color=(0.95, 0.9, 0.8), block=b.id, solid=True, n=8))
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
        if name == 'boss':
            # куда ставят машину, привезённую боссу: у тротуара правее входа
            lm['park'] = (lm['road'][0] + 9.0, b.y0 - PARK_STRIP * 0.5 if not ROAD_Y_AVE[b.j] else b.y0 - 1.9)

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

    def _gen_old(self, b, R, r, floors=(2, 5)):
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
            nfl = r.randint(floors[0], floors[1])
            win = side + {'s': 'n', 'n': 's', 'w': 'e', 'e': 'w'}[side] + corner
            bld = Building(bx0, by0, bx1, by1, GF_H + nfl * FLOOR_H, fac, b.id, gf_tex=r.pick(shops),
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
                if lm == 'terminal':
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
        self.covered.append((cx - bay, y0, cx + bay, y0 + depth, CURB + h - 0.5))
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
                if lm == 'safehouse' and row == 0 and len(widths) >= 4 and k in (1, 2):
                    if k == 1:
                        self._home_estate(b, r, lx0, y0, lx0 + w * 2.0, ymid)
                    continue
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
                if lm == 'bruce' and row == 0 and k == len(widths) // 2:
                    bld.h = 2 * FLOOR_H
                    bld.tint = (0.80, 0.90, 1.0)
                    bld.name = 'bruce'
                    self._register_landmark('bruce', bld, 's', b)
                # подъездная дорожка + машина
                dx0 = lx0 + 0.8 if drive_left else lx1 - 0.8 - dw
                if row == 0:
                    self.ground.append((dx0, y0, dx0 + dw, hy0 + hd, 'concrete', (4.0, 4.0), (0.86, 0.86, 0.86), b.id,
                                        CURB + 0.02, 0))
                    if r.chance(0.6):
                        self._spot(dx0 + dw * 0.5, y0 + setback + 2.0, math.pi / 2, b.zone, block=b.id)
                    self._prop('mailbox', dx0 - 0.6 if drive_left else dx0 + dw + 0.6, y0 + 0.5, math.pi / 2, b.id)
                else:
                    self.ground.append((dx0, hy0, dx0 + dw, y1, 'concrete', (4.0, 4.0), (0.86, 0.86, 0.86), b.id,
                                        CURB + 0.02, 0))
                    if r.chance(0.6):
                        self._spot(dx0 + dw * 0.5, y1 - setback - 2.0, -math.pi / 2, b.zone, block=b.id)
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

    def _home_estate(self, b, r, x0, y0, x1, ymid):
        """Дом Макса: двухэтажный дом и гараж на три машины с въездом с улицы.

        Гараж — три стены и плоская крыша; крыша не мешает проезду (она только нарисована),
        ворота рисует и двигает garage.py."""
        hw, hd = 13.0, 10.0
        hx0, hy0 = x0 + 3.0, y0 + 7.5
        bld = Building(hx0, hy0, hx0 + hw, hy0 + hd, 2 * FLOOR_H, 'fac_siding', b.id, gf_h=0.0,
                       tint=(0.98, 0.92, 0.78), roof_type='gable', roof_tex='roof_tiles',
                       roof_color=(0.62, 0.5, 0.46), blank_tex='fac_siding', name='safehouse')
        bld.open_sides = 's'
        self.buildings.append(bld)
        lm = self._register_landmark('safehouse', bld, 's', b)
        # дорожка от тротуара к двери
        cx = hx0 + hw * 0.5
        self.ground.append((cx - 1.0, y0, cx + 1.0, hy0, 'pavers', (2.0, 2.0), (0.9, 0.9, 0.9), b.id, CURB + 0.02, 0))
        self._prop('mailbox', cx - 1.6, y0 + 0.5, math.pi / 2, b.id)
        # гараж: внутри 10.2 x 7.2 м, ворота во всю ширину смотрят на улицу
        gw, gd, t, gh = 10.2, 7.2, 0.4, 3.0
        gx0 = x1 - 3.0 - gw - 2 * t
        gy0 = y0 + 9.0
        ix0, iy0, ix1, iy1 = gx0 + t, gy0, gx0 + t + gw, gy0 + gd
        tint = (0.92, 0.9, 0.86)
        for (px0, py0, px1, py1) in ((gx0, gy0, ix0, iy1 + t), (ix1, gy0, ix1 + t, iy1 + t), (ix0, iy1, ix1, iy1 + t)):
            w_ = Building(px0, py0, px1, py1, gh, 'fac_siding', b.id, gf_h=0.0, tint=tint, roof_tex='roof_tar',
                          blank_tex='fac_siding', sides_win='', name='garage')
            w_.night = False
            self.buildings.append(w_)
        self._box(gx0 - 0.3, gy0 - 0.5, CURB + gh, ix1 + t + 0.3, iy1 + t + 0.3, CURB + gh + 0.35, 'roof_tar', b.id,
                  color=(0.5, 0.5, 0.52), solid=False, faces='xXyYZz')
        self.ground.append((ix0, iy0, ix1, iy1, 'concrete', (4.0, 4.0), (0.74, 0.74, 0.76), b.id, CURB + 0.03, 0))
        # площадка перед воротами и выезд на улицу
        self.ground.append((ix0, y0, ix1, iy0, 'concrete', (4.0, 4.0), (0.86, 0.86, 0.86), b.id, CURB + 0.02, 0))
        slots = [(ix0 + gw * (k + 0.5) / 3.0, iy0 + gd * 0.5 + 0.2) for k in range(3)]
        self.special['garage'] = dict(rect=(ix0, iy0, ix1, iy1), door_y=iy0, z=CURB, h=gh, slots=slots, yaw=math.pi / 2,
                                      front=(ix0 + gw * 0.5, y0 - 1.6), block=b.id)
        self.covered.append((ix0 - t, iy0 - 0.5, ix1 + t, iy1 + t, CURB + gh))
        lm['garage'] = (ix0 + gw * 0.5, iy0 + gd * 0.5)
        # живая изгородь по бокам участка и пара деревьев
        self._wall(x0 + 0.4, y0 + 2.0, x0 + 0.4, ymid, 1.1, 'hedge', b.id, thick=0.7, kind='hedge')
        self._wall(x1 - 0.4, y0 + 2.0, x1 - 0.4, ymid, 1.1, 'hedge', b.id, thick=0.7, kind='hedge')
        self._prop('tree', hx0 + hw + 3.2, hy0 + hd + 3.0, 0.0, b.id, seed=77, size=1.2)
        self._prop('tree', hx0 - 1.0, hy0 + hd + 5.0, 0.0, b.id, seed=78, size=1.0)
        self._prop('bench', hx0 + hw * 0.5, hy0 + hd + 2.0, 0.0, b.id)

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
                            self._box(xx, y_, CURB + s * ch, xx + cl, y_ + cw, CURB + (s + 1) * ch, 'container', b.id,
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
                            self._box(x_, yy, CURB + s * ch, x_ + cw, yy + cl, CURB + (s + 1) * ch, 'container', b.id,
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
        if lm:
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
    # АЭРОДРОМ
    # ------------------------------------------------------------------
    def _gen_airfield(self, b, R, r):
        x0, y0, x1, y1 = R
        w, h = x1 - x0, y1 - y0
        self._ground(x0, y0, x1, y1, 'grass', b.id, tile=6.0, color=(0.92, 0.95, 0.86))
        # взлётная полоса вдоль южного края
        ry = y0 + 30.0
        rw = 24.0
        rx0, rx1 = x0 + 12.0, x1 - 12.0
        z1 = CURB + 0.02
        self.ground.append((rx0, ry - rw / 2, rx1, ry + rw / 2, 'asphalt', (8.0, 8.0), (0.78, 0.78, 0.8), b.id, z1, 0))
        white = (0.95, 0.95, 0.95)
        t = rx0 + 26.0
        while t < rx1 - 30.0:                        # осевая
            self.ground.append((t, ry - 0.4, t + 9.0, ry + 0.4, 'white', (1.0, 1.0), white, b.id, z1 + 0.02, 0))
            t += 18.0
        for ex in (rx0 + 4.0, rx1 - 16.0):           # «зебра» порогов
            for k in range(6):
                yy = ry - rw / 2 + 2.2 + k * 3.6
                self.ground.append((ex, yy, ex + 12.0, yy + 1.6, 'white', (1.0, 1.0), white, b.id, z1 + 0.02, 0))
        for side in (-1, 1):                         # кромки
            yy = ry + side * (rw / 2 - 0.6)
            self.ground.append((rx0, yy - 0.2, rx1, yy + 0.2, 'white', (1.0, 1.0), white, b.id, z1 + 0.02, 0))
        # перрон и рулёжка
        ay0 = ry + rw / 2 + 22.0
        ax0, ax1 = x0 + w * 0.22, x1 - w * 0.12
        self.ground.append((ax0, ay0, ax1, y1 - 6.0, 'concrete', (5.0, 5.0), (0.8, 0.8, 0.8), b.id, z1, 0))
        tx = x0 + w * 0.5
        self.ground.append((tx - 7.0, ry + rw / 2, tx + 7.0, ay0, 'asphalt', (8.0, 8.0), (0.78, 0.78, 0.8), b.id, z1, 0))
        # здание аэровокзала — лицом к северной улице
        bw = 30.0
        bx0 = x0 + w * 0.42
        bld = Building(bx0, y1 - 20.0, bx0 + bw, y1 - 7.0, GF_H + FLOOR_H, 'fac_glass_b', b.id, gf_tex='gf_office',
                       sides_gf='n', blank_tex='concrete', roof_tex='roof_gravel', name='airfield')
        self.buildings.append(bld)
        self._big_sign(bld, 'n', 'sign_airfield', w=12.0, h=2.4, z=CURB + bld.h - 1.6)
        self._register_landmark('airfield', bld, 'n', b)
        self.landmarks['airfield']['runway'] = (rx0 + 30.0, ry, rx1 - 30.0, ry)
        self.landmarks['airfield']['apron'] = ((ax0 + ax1) * 0.5, ay0 + 12.0)
        # диспетчерская вышка
        vx, vy = bx0 + bw + 10.0, y1 - 14.0
        self._box(vx - 2.6, vy - 2.6, CURB, vx + 2.6, vy + 2.6, CURB + 15.0, 'concrete', b.id, color=(0.86, 0.86, 0.84),
                  uv_m=4.0)
        self._box(vx - 4.0, vy - 4.0, CURB + 15.0, vx + 4.0, vy + 4.0, CURB + 18.2, 'fac_glass_b', b.id,
                  color=(1.0, 1.0, 1.0), uv_m=3.5, solid=False, top_tex='roof_gravel')
        # ангары
        hx = ax0 + 4.0
        for k in range(2):
            self._warehouse(b, r, hx, y1 - 34.0, hx + 26.0, y1 - 8.0, 's')
            hx += 31.0
        # самолёты на перроне и один у полосы
        for k in range(3):
            self._prop('plane', ax0 + 22.0 + k * 34.0, ay0 + 12.0, math.pi / 2 + r.rangef(-0.25, 0.25), b.id,
                       color=r.randint(0, 3))
        self._prop('plane', rx0 + 40.0, ry + rw / 2 + 12.0, 0.2, b.id, color=1)
        self._prop('windsock', x1 - 18.0, ry + rw / 2 + 8.0, 0.0, b.id)
        # топливо, ящики, служебные машины
        for k in range(2):
            self.cyls.append(dict(x=ax1 - 9.0, y=ay0 + 9.0 + k * 13.0, z0=CURB, z1=CURB + 6.0, r=4.4, tex='corrugated',
                                  color=(0.92, 0.92, 0.9), block=b.id, solid=True, n=12, cap=True))
        self._prop('crate', ax1 - 20.0, ay0 + 4.0, 0.3, b.id)
        self._prop('crate', ax1 - 21.6, ay0 + 4.4, 1.0, b.id)
        self._spot(ax0 + 8.0, y1 - 40.0, 0.0, 'A', kind='van', block=b.id)
        self._spot(ax1 - 22.0, y1 - 12.0, math.pi, 'A', kind='pickup', block=b.id)
        # забор с воротами на север
        self._fence_lot(b, r, x0, y0, x1, y1, 'sew', gaps=False, h=2.4, inset=0.3)
        gx = bx0 - 14.0
        self._wall(x0 + 0.3, y1 - 0.3, gx, y1 - 0.3, 2.4, 'chainlink', b.id, thick=0.12, kind='fence')
        self._wall(gx + 9.0, y1 - 0.3, bx0, y1 - 0.3, 2.4, 'chainlink', b.id, thick=0.12, kind='fence')
        self._wall(bx0 + bw, y1 - 0.3, x1 - 0.3, y1 - 0.3, 2.4, 'chainlink', b.id, thick=0.12, kind='fence')
        self.ground.append((gx, y1 - 8.0, gx + 9.0, b.y1, 'asphalt', (8.0, 8.0), (0.78, 0.78, 0.8), b.id, z1, 0))
        self.ground.append((gx, ay0 + 20.0, gx + 9.0, y1 - 8.0, 'asphalt', (8.0, 8.0), (0.78, 0.78, 0.8), b.id, z1, 0))
        self.landmarks['airfield']['gate'] = (gx + 4.5, b.y1 + 2.0)
        for k in range(8):
            self._prop('lamp', rx0 + 20.0 + k * ((rx1 - rx0 - 40.0) / 7.0), ry + rw / 2 + 3.0, -math.pi / 2, b.id, park=True)
        self.packages.append((x0 + 6.0, y0 + 6.0))
        self.pickup_spots.append((ax1 - 4.0, y1 - 10.0, 'lot'))

    # ------------------------------------------------------------------
    # побережье: пляж, причалы
    # ------------------------------------------------------------------
    def _dry(self, x, y, margin=0.3):
        """Сухое место вне дорог и кварталов (для зонтиков, деревьев и прочего)."""
        if self.where(x, y)[0] is not None or self.pad_at(x, y) is not None:
            return False
        return self.terrain.height(x, y) > WATER_Z + margin

    def _gen_coast(self):
        r = Rng(self.seed * 77 + 3)
        oc = self.outer_chunk
        sw = SIDEWALK
        xs, ys = self.xs, self.ys

        # ---- городской пляж: к югу от набережной
        gy0 = ys[0] - self.wy[0] * 0.5                 # южный край самой южной улицы
        edge = gy0 - sw                                # за тротуаром — песок
        bx0 = xs[1] - self.wx[1] * 0.5 - 24.0
        bx1 = xs[8] + self.wx[8] * 0.5 + 24.0
        ly0 = gy0 - BEACH_W                            # здесь песок уходит в воду
        self.special['beach'] = dict(x0=bx0, y0=ly0, x1=bx1, y1=edge)
        for k in range(40):
            x = bx0 + 12 + k * ((bx1 - bx0 - 24) / 39.0) + r.rangef(-4, 4)
            y = edge - r.rangef(2.0, 7.0)
            if self._dry(x, y):
                self._prop('palm', x, y, 0.0, oc(x, y), seed=r.randint(0, 9999), size=r.rangef(0.9, 1.3))
        for k in range(70):
            x = r.rangef(bx0 + 10, bx1 - 10)
            y = r.rangef(ly0 + 14, edge - 10)
            if self._dry(x, y, 0.45):
                self._prop('umbrella', x, y, r.rangef(0, 6.28), oc(x, y), color=r.randint(0, 5))
        for k in range(4):
            x = bx0 + 90 + k * ((bx1 - bx0 - 180) / 3.0)
            if self._dry(x, ly0 + 20.0):
                self._prop('lifeguard', x, ly0 + 20.0, -math.pi / 2, oc(x, ly0 + 20))
        pier_x = xs[4]
        pier = (pier_x - 4.0, ly0 - 62.0, pier_x + 4.0, ly0 + 12.0)
        self._pad(pier[0], pier[1], pier[2], pier[3], CURB + 0.25, 'beach', on_map=True)
        self.special['pier'] = dict(x0=pier[0], y0=pier[1], x1=pier[2], y1=pier[3], z=CURB + 0.25,
                                    chunk=oc(pier_x, ly0))
        self.packages.append((pier_x, ly0 - 58.0))
        self.pickup_spots.append((pier_x + 2.0, ly0 - 40.0, 'pier'))
        for k in range(7):
            self.pickup_spots.append((bx0 + 60 + k * 110.0, ly0 + 26.0, 'beach'))
        # фонари вдоль набережной
        k = 0
        while bx0 + 30 + k * 30.0 < bx1 - 30:
            x = bx0 + 30 + k * 30.0
            self._prop('lamp', x, gy0 - 0.65, math.pi / 2, oc(x, gy0 - 5))
            k += 1

        # ---- причалы: к востоку от порта
        gx1 = xs[self.isle_i1 + 1] + self.wx[self.isle_i1 + 1] * 0.5     # восточный край кольцевой дороги
        dy0 = ys[2] - self.wy[2] * 0.5
        dy1 = ys[7] + self.wy[7] * 0.5
        dx0, dx1 = gx1 + sw, gx1 + DOCK_W
        self._pad(dx0, dy0, dx1, dy1, CURB, 'docks', on_map=True)
        self.special['docks'] = dict(x0=dx0, y0=dy0, x1=dx1, y1=dy1)
        n = 6
        for k in range(n):
            ya = dy0 + (dy1 - dy0) * k / n
            yb = dy0 + (dy1 - dy0) * (k + 1) / n
            self._ground(dx0, ya, dx1, yb, 'concrete', oc(dx0 + 20, (ya + yb) * 0.5), tile=5.0, color=(0.8, 0.8, 0.8))
        bridge_y = ys[5]                               # Портовый мост проходит над причалами
        piers = [(ys[2] + ys[3]) * 0.5, ys[4], (ys[6] + ys[7]) * 0.5]
        wall_c = (0.74, 0.74, 0.72)
        # парапет вдоль воды: с проёмами у пирсов и там, где над причалами идёт мост
        gaps = [(py - 9.0, py + 9.0) for py in piers]
        ship_cy = piers[1] + 9.0 + 2.0 + 8.0           # ось сухогруза: напротив неё в парапете въезд на аппарель
        gaps.append((ship_cy - 3.4, ship_cy + 3.4))
        for seg in self.bridges:
            if seg['kind'] == 'h' and seg['a'] < dx1 < seg['b']:
                hw = seg['width'] * 0.5 + 1.1
                gaps.append((seg['c'] - hw, seg['c'] + hw))
        gaps.sort()
        prev = dy0
        for g0, g1 in gaps:
            if g0 > prev + 0.5:
                self._wall_run(dx1 - 0.3, prev, dx1 - 0.3, g0, 0.9, wall_c)
            prev = max(prev, g1)
        self._wall_run(dx1 - 0.3, prev, dx1 - 0.3, dy1, 0.9, wall_c)
        self._wall_run(dx0, dy0 + 0.3, dx1 - 0.3, dy0 + 0.3, 0.9, wall_c)
        self._wall_run(dx0, dy1 - 0.3, dx1 - 0.3, dy1 - 0.3, 0.9, wall_c)
        self.special['piers'] = []
        for py in piers:
            pr = (dx1, py - 9.0, dx1 + 46.0, py + 9.0)
            self._pad(pr[0], pr[1], pr[2], pr[3], CURB, 'docks', on_map=True)
            ch = oc(dx1 + 20, py)
            self.special['piers'].append(dict(x0=pr[0], y0=pr[1], x1=pr[2], y1=pr[3], chunk=ch))
            for kx in range(4):                         # кнехты и ящики
                self._prop('bollard', dx1 + 6 + kx * 11.0, py - 8.2, 0.0, ch)
                self._prop('bollard', dx1 + 6 + kx * 11.0, py + 8.2, 0.0, ch)
            self._prop('crate', dx1 + 30.0, py + 3.0, 0.4, ch)
            self._prop('crate', dx1 + 31.6, py + 3.4, 1.0, ch)
        self.packages.append((dx1 + 43.0, piers[1]))
        self.pickup_spots.append((dx1 + 40.0, piers[0], 'pier'))
        self.pickup_spots.append((dx1 + 40.0, piers[2], 'pier'))
        # краны и контейнеры между пирсами; под мостом — проезд
        fake = Block()
        yards = [(piers[0] + 14.0, piers[1] - 12.0), (piers[1] + 30.0, bridge_y - 14.0),
                 (bridge_y + 14.0, piers[2] - 12.0)]
        for (ya, yb) in yards:
            if yb - ya < 20.0:
                continue
            cy = (ya + yb) * 0.5
            fake.id = oc(dx0 + 20, cy)
            self._prop('crane', dx1 - 9.0, ya + 8.0, math.pi, fake.id)
            self._containers(fake, r, dx0 + 8.0, ya + 2.0, dx1 - 18.0, yb - 2.0, along_x=False, density=0.6)
        # ---- сухогруз у среднего пирса.  На палубу можно подняться: по трапу с пирса и по аппарели с причала.
        py = piers[1]
        sx0, sx1 = dx1 + 5.0, dx1 + 75.0
        sy0, sy1 = py + 11.0, py + 27.0
        cy = (sy0 + sy1) * 0.5
        deck = CURB + SHIP_DECK
        chunk = oc(dx1 + 40, cy)
        self._pad(sx0, sy0, sx1, sy1, deck, 'ship')
        # аппарель: с причала на корму, по оси корабля (по ней съезжает машина)
        rx0 = dx1 - 17.0
        ramp = (rx0, cy - 2.7, sx0 + 0.4, cy + 2.7)
        self._pad(ramp[0], ramp[1], ramp[2], ramp[3], deck, 'ship', slope=('x', CURB, deck))
        # трап: вдоль борта в просвете между пирсом и корпусом, наверху — площадка у разрыва фальшборта
        gx0, gx1 = sx0 + 9.0, sx0 + 18.0
        gy0, gy1 = py + 8.9, sy0 + 0.1
        self._pad(gx0, gy0, gx1, gy1, deck, 'ship', slope=('x', CURB, deck))
        self._pad(gx1, gy0, gx1 + 2.2, gy1, deck, 'ship')
        bw = (0.16, 0.17, 0.20)

        def fence(x0_, y0_, x1_, y1_):
            # невидимая преграда: сами перила наклонные, их рисует citymesh
            self.boxes.append(dict(x0=x0_, y0=y0_, z0=CURB, x1=x1_, y1=y1_, z1=deck + 1.0, tex=None, block=chunk,
                                   color=(0, 0, 0), uv_m=3.0, solid=True, top_tex=None, top_color=None, faces='',
                                   stack_h=6.0))
        # перила трапа со стороны пирса и торец площадки: с пирса на трап можно зайти только снизу
        fence(gx0 + 1.3, gy0 - 0.07, gx1 + 2.2, gy0 + 0.07)
        fence(gx1 + 2.13, gy0, gx1 + 2.27, gy1)
        # между пирсом и бортом — полоса воды, а герой не плавает: по краю пирса идёт поручень с разрывом
        # у нижней ступени трапа, а сама ступень с торца закрыта
        rail_c = (0.80, 0.66, 0.14)
        edge = py + 9.0 - 0.12
        self._wall(dx1 + 0.4, edge, gx0 - 0.05, edge, 1.0, 'metal_paint', chunk, color=rail_c, thick=0.12, kind='rail')
        self._wall(gx1 + 2.3, edge, dx1 + 46.0 - 0.4, edge, 1.0, 'metal_paint', chunk, color=rail_c, thick=0.12,
                   kind='rail')
        self._wall(gx0 - 0.05, edge, gx0 - 0.05, gy1, 1.0, 'metal_paint', chunk, color=rail_c, thick=0.12, kind='rail')
        # борта аппарели
        for yy in (ramp[1], ramp[3]):
            fence(rx0 + 2.5, yy - 0.08, sx0, yy + 0.08)
        # фальшборт вокруг палубы: разрывы у площадки трапа и у аппарели
        self._wall(sx0, sy0, gx1, sy0, 1.0, 'metal_paint', chunk, color=bw, thick=0.2, z0=deck)
        self._wall(gx1 + 2.2, sy0, sx1, sy0, 1.0, 'metal_paint', chunk, color=bw, thick=0.2, z0=deck)
        self._wall(sx0, sy1, sx1, sy1, 1.0, 'metal_paint', chunk, color=bw, thick=0.2, z0=deck)
        self._wall(sx1, sy0, sx1, sy1, 1.0, 'metal_paint', chunk, color=bw, thick=0.2, z0=deck)
        self._wall(sx0, sy0, sx0, ramp[1], 1.0, 'metal_paint', chunk, color=bw, thick=0.2, z0=deck)
        self._wall(sx0, ramp[3], sx0, sy1, 1.0, 'metal_paint', chunk, color=bw, thick=0.2, z0=deck)

        def solid(x0_, y0_, x1_, y1_, z1_):
            self.boxes.append(dict(x0=x0_, y0=y0_, z0=deck, x1=x1_, y1=y1_, z1=z1_, tex=None, block=chunk,
                                   color=(0, 0, 0), uv_m=3.0, solid=True, top_tex=None, top_color=None, faces='',
                                   stack_h=6.0))
        # надстройка — на носу: корма свободна, на неё выходит аппарель
        house = (sx1 - 17.0, sy0 + 2.0, sx1 - 5.0, sy1 - 2.0)
        solid(house[0], house[1], house[2], house[3], deck + 9.6)
        # контейнеры двумя рядами вдоль бортов; посередине — проезд от жёлтого контейнера к аппарели
        rr = Rng(self.seed * 31 + 5)
        cont = []
        for row, yy in enumerate((sy0 + 1.7, sy1 - 1.7 - 2.44)):
            for n in range(6):
                if (row, n) in ((0, 1), (1, 0), (1, 3)):
                    continue                            # проходы между контейнерами
                cx0 = sx0 + 9.5 + n * 6.9
                if row == 0 and gx1 - 1.0 < cx0 + 6.1 and cx0 < gx1 + 3.4:
                    continue                            # у выхода с трапа пусто
                lv = 1 if rr.chance(0.55) else 2
                cont.append((cx0, yy, cx0 + 6.1, yy + 2.44, lv, rr.randint(0, len(self.CONTAINER_COLORS) - 1)))
                solid(cx0, yy, cx0 + 6.1, yy + 2.44, deck + 2.6 * lv)
        # жёлтый контейнер: в конце проезда, воротами к корме; три стенки — преграда, ворота — отдельно
        yx0, yx1 = sx0 + 40.0, sx0 + 48.0
        yy0, yy1 = cy - 1.8, cy + 1.8
        t = 0.16
        solid(yx0, yy0 - t, yx1, yy0, deck + 3.0)
        solid(yx0, yy1, yx1, yy1 + t, deck + 3.0)
        solid(yx1, yy0 - t, yx1 + t, yy1 + t, deck + 3.0)
        self.special['ship'] = dict(
            x0=sx0, y0=sy0, x1=sx1, y1=sy1, chunk=chunk, deck=deck, cy=cy, ramp=ramp, house=house,
            stairs=(gx0, gy0, gx1, gy1), landing=(gx1, gy0, gx1 + 2.2, gy1), containers=cont,
            yellow=(yx0, yy0, yx1, yy1), yellow_door=(yx0, cy), yellow_car=((yx0 + yx1) * 0.5 + 0.3, cy, math.pi),
            stairs_foot=(gx0 - 1.5, py + 6.5), ramp_foot=(rx0 - 6.0, cy))
        self.packages.append((sx1 - 2.5, sy0 + 1.2))          # тайник на баке, за надстройкой
        # стоянка грузовиков у южного края
        fake.id = oc(dx0 + 20, dy0 + 20)
        for k in range(5):
            self._spot(dx0 + 10.0 + k * 5.0, dy0 + 12.0, math.pi / 2, 'I',
                       kind=r.pick(['truck', 'van', 'pickup', 'truck']), block=fake.id)
        self.packages.append((dx0 + 2.0, dy1 - 3.0))

    # ------------------------------------------------------------------
    # загород: лес, камни, трасса
    # ------------------------------------------------------------------
    def _gen_country(self):
        T = self.terrain
        oc = self.outer_chunk
        r = Rng(self.seed * 91 + 11)
        if T.ok:
            step = T.step
            nx, ny = T.nx, T.ny
            cover = T.cover
            for iy in range(1, ny - 1):
                for ix in range(1, nx - 1):
                    c = cover[iy * nx + ix]
                    if c == C_FOREST:
                        n = 1 if r.chance(0.30) else 0
                        kind = 'tree'
                    elif c == C_ROCK:
                        n = 1 if r.chance(0.10) else 0
                        kind = 'rock'
                    elif c == C_GRASS:
                        n = 1 if r.chance(0.022) else 0
                        kind = 'tree' if r.chance(0.75) else 'rock'
                    else:
                        continue
                    for _ in range(n):
                        x = T.x0 + (ix + r.rangef(-0.45, 0.45)) * step
                        y = T.y0 + (iy + r.rangef(-0.45, 0.45)) * step
                        if not self._dry(x, y, 0.5) or self._near_road(x, y, 7.0):
                            continue
                        self._prop(kind, x, y, r.rangef(0, 6.28), oc(x, y), seed=r.randint(0, 9999),
                                   size=r.rangef(1.2, 2.1) if kind == 'tree' else r.rangef(0.8, 1.9))
        # трасса: столбики-отражатели и щиты
        k = 0
        for key in sorted(self.segs):
            seg = self.segs[key]
            if not seg['rural'] or seg['bridge'] is not None:
                continue
            a, b, c = seg['a'], seg['b'], seg['c']
            hw = seg['width'] * 0.5
            t = a + 20.0
            while t < b - 10.0:
                for sgn in (-1, 1):
                    if seg['kind'] == 'h':
                        x, y = t, c + sgn * (hw + 1.2)
                    else:
                        x, y = c + sgn * (hw + 1.2), t
                    self._prop('roadpost', x, y, 0.0, oc(x, y))
                t += 40.0
            k += 1
            mid = (a + b) * 0.5
            if k % 2 == 1 and b - a > 70.0:
                if seg['kind'] == 'h':
                    x, y, side = mid, c + hw + 5.0, 's'
                else:
                    x, y, side = c + hw + 5.0, mid, 'w'
                self.special.setdefault('free_signs', []).append(
                    dict(x=x, y=y, z=5.4, w=9.0, h=4.5, tex=r.pick(BILLBOARDS), side=side, block=oc(x, y), post=True,
                         lit=False))
        self.packages.append((self.xs[12] + 14.0, self.ys[11] + 16.0))

    def _near_road(self, x, y, d):
        """Ближе d метров к дороге или кварталу?"""
        w = self.where
        return (w(x + d, y)[0] is not None or w(x - d, y)[0] is not None or
                w(x, y + d)[0] is not None or w(x, y - d)[0] is not None)

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
        for (i, j), n in sorted(self.nodes.items()):
            if len(n.exits) < 3 or n.rural:
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
        sh = self.landmarks.get('terminal')              # игра начинается у конечной автобуса
        if sh:
            self.start_pos = (sh['door'][0], sh['door'][1], math.pi / 2 * -1)
        else:
            self.start_pos = (0.0, 0.0, 0.0)
