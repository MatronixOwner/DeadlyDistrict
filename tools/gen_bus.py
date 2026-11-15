# -*- coding: utf-8 -*-
"""Городской автобус — своя модель в стиле остальных машин (низкополигональная, с пиксельной текстурой).

В наборе «PSX Style Cars» автобуса нет, поэтому он собирается здесь: кузов — из двух десятков
граней, текстура рисуется программно в той же манере (тёмные стёкла с градиентом, швы панелей,
приглушённые цвета), колёса взяты от фургона из набора.  Как и у остальных машин, краска вынесена
в отдельный слой, так что автобус красится в любой цвет.

    python tools/gen_bus.py        # пишет assets/models/veh/bus.* и запись в models.json
(обычно вызывается из tools/import_psx.py cars)
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'models')

S = 24.0                    # пикселей текстуры на метр
T = 256                     # размер текстуры

# габариты, м
L, W = 10.5, 2.5
HL, HW = L * 0.5, W * 0.5
Z0 = 0.40                   # низ кузова
ZB = 1.32                   # низ окон
ZT = 2.46                   # верх окон
Z3 = 2.76                   # верх бортов
Z4 = 3.00                   # крыша
XR = 0.86                   # полуширина плоской части крыши
YF = HL - 0.24              # куда «заваливается» лобовое стекло наверху
YR = -HL + 0.10
AXLE_F, AXLE_R = 3.30, -2.90
WHEEL_R, WHEEL_W = 0.50, 0.30

# куски текстуры: (x, y) левого верхнего угла, пиксели
SIDE_R = (2, 2)             # правый борт: 252 x 57
SIDE_L = (2, 62)            # левый борт
ROOF = (2, 122)             # крыша: 252 x 42
EDGE = (2, 167)             # скос между бортом и крышей: 252 x 6
FRONT = (2, 177)            # перед: 60 x 63
REAR = (66, 177)            # зад
WHEEL = (130, 177)          # колесо от фургона (48 x 48)
DARK = (182, 177)           # тёмное днище и бамперы: 24 x 12
CHROME = (182, 192)

GLASS_TOP = (47, 53, 53)
GLASS_BOT = (22, 28, 28)
FRAME = (21, 21, 21)
RUBBER = (30, 30, 31)
STEEL = (150, 152, 156)
SKIRT = (58, 58, 60)
ROOF_C = (196, 194, 186)


class Canvas(object):
    """Три слоя текстуры: цвет неокрашенных деталей, маска краски и её светотень."""

    def __init__(self):
        self.rgb = np.zeros((T, T, 3), np.float32)
        self.rgb[:] = (40, 40, 42)
        self.paint = np.zeros((T, T), bool)
        self.shade = np.ones((T, T), np.float32)

    def rect(self, x0, y0, x1, y1, color):
        """Прямоугольник [x0, x1) x [y0, y1) неокрашенной детали."""
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        self.rgb[y0:y1, x0:x1] = color
        self.paint[y0:y1, x0:x1] = False

    def painted(self, x0, y0, x1, y1, shade=1.0):
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        self.paint[y0:y1, x0:x1] = True
        self.shade[y0:y1, x0:x1] = shade

    def darken(self, x0, y0, x1, y1, k):
        """Тень или шов: краска темнее в k раз, детали тоже."""
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        self.shade[y0:y1, x0:x1] *= k
        self.rgb[y0:y1, x0:x1] *= k

    def glass(self, x0, y0, x1, y1, frame=FRAME):
        """Стекло как у машин набора: тёмное, сверху светлее, в тонкой чёрной рамке."""
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        self.rect(x0, y0, x1, y1, frame)
        h = max(1, y1 - y0 - 2)
        for y in range(y0 + 1, y1 - 1):
            k = (y - y0 - 1) / float(h)
            c = [GLASS_TOP[i] + (GLASS_BOT[i] - GLASS_TOP[i]) * min(1.0, k * 1.25) for i in range(3)]
            self.rgb[y, x0 + 1:x1 - 1] = c
        self.paint[y0:y1, x0:x1] = False

    def dot(self, x, y, color, r=1):
        self.rect(x, y, x + r, y + r, color)


def draw_side(c, org, right):
    """Борт.  u — вдоль автобуса (нос справа), v — сверху вниз от верха борта."""
    ox, oy = org
    n = int(round(L * S))                       # 252
    h = int(round((Z3 - Z0) * S))               # 57

    def px(y):
        return ox + (y + HL) * S

    def pz(z):
        return oy + (Z3 - z) * S
    c.painted(ox, oy, ox + n, oy + h)
    # светотень: к низу темнее, у самого верха — блик
    for r in range(h):
        k = 1.06 - 0.20 * (r / float(h)) ** 1.5
        c.shade[oy + r, ox:ox + n] = k
    c.shade[oy:oy + 2, ox:ox + n] *= 1.10
    # чёрная полоса остекления во всю длину
    c.rect(ox, pz(ZT) - 1, ox + n, pz(ZB) + 1, RUBBER)
    # юбка понизу
    c.rect(ox, pz(0.60), ox + n, oy + h, SKIRT)
    c.rgb[int(pz(0.60)), ox:ox + n] = (88, 88, 90)
    # светлая полоса под окнами
    c.rect(ox, pz(ZB) + 2, ox + n, pz(ZB) + 4, (206, 204, 196))
    doors = [(3.92, 4.92), (-0.86, 0.44)] if right else []
    # окна между дверями и стойками
    spans = []
    edges = [-HL + 0.30]
    for d0, d1 in sorted(doors):
        edges += [d0 - 0.10, d1 + 0.10]
    edges.append(HL - 0.42 if right else HL - 1.52)
    for i in range(0, len(edges), 2):
        spans.append((edges[i], edges[i + 1]))
    for a, b in spans:
        if b - a < 0.5:
            continue
        k = max(1, int(round((b - a) / 1.36)))
        wdt = (b - a) / k
        for j in range(k):
            x0 = px(a + j * wdt) + 1
            x1 = px(a + (j + 1) * wdt) - 1
            c.glass(x0, pz(ZT), x1, pz(ZB))
            # форточка: тонкая перемычка в верхней трети
            yy = int(pz(ZT) + (pz(ZB) - pz(ZT)) * 0.30)
            c.rgb[yy, int(x0) + 1:int(x1) - 1] = (64, 66, 68)
    if not right:
        # окно водителя — пониже остальных
        c.glass(px(HL - 1.42), pz(ZT), px(HL - 0.46), pz(ZB - 0.22))
    # двери: две створки со стёклами, порог
    for d0, d1 in doors:
        x0, x1 = int(px(d0)), int(px(d1))
        c.rect(x0 - 1, pz(ZT + 0.10), x1 + 1, pz(0.46), FRAME)
        c.painted(x0, pz(ZT + 0.10) + 1, x1, pz(0.46) - 1, 0.90)
        mid = (x0 + x1) // 2
        c.rect(mid, pz(ZT + 0.10) + 1, mid + 1, pz(0.46) - 1, FRAME)
        for a, b in ((x0 + 1, mid - 1), (mid + 2, x1 - 1)):
            c.glass(a, pz(ZT) + 1, b, pz(1.02))
            c.glass(a, pz(0.94), b, pz(0.58))
        c.rect(x0, pz(0.46) - 1, x1, pz(0.46) + 1, STEEL)
    # колёсные арки
    for ay in (AXLE_F, AXLE_R):
        cx, cz = px(ay), pz(0.50)
        r = 0.66 * S
        for yy in range(int(cz - r), oy + h):
            for xx in range(int(cx - r), int(cx + r) + 1):
                d = ((xx + 0.5 - cx) ** 2 + (yy + 0.5 - cz) ** 2) ** 0.5
                if d <= r:
                    c.rgb[yy, xx] = (16, 16, 17) if d < r - 1.5 else (70, 70, 72)
                    c.paint[yy, xx] = False
    # швы панелей под окнами
    for y in np.arange(-HL + 1.2, HL - 0.6, 1.36):
        x = int(px(y))
        if c.paint[int(pz(1.0)), x]:
            c.darken(x, pz(ZB) + 5, x + 1, pz(0.60), 0.80)
    # габаритные огоньки и лючок
    c.dot(px(HL - 0.12), pz(1.02), (232, 140, 30), 2)
    c.dot(px(-HL + 0.08), pz(1.02), (200, 30, 24), 2)
    if right:
        c.rect(px(-3.9), pz(1.0), px(-3.9) + 5, pz(1.0) + 5, (0, 0, 0))
        c.painted(px(-3.9) + 1, pz(1.0) + 1, px(-3.9) + 4, pz(1.0) + 4, 0.86)
    else:
        # решётка моторного отсека
        x0, x1 = int(px(-4.9)), int(px(-3.7))
        for yy in range(int(pz(1.16)), int(pz(0.70)), 2):
            c.darken(x0, yy, x1, yy + 1, 0.55)


def draw_roof(c):
    ox, oy = ROOF
    n = int(round(L * S))
    h = int(round(2 * XR * S)) + 1
    c.rect(ox, oy, ox + n, oy + h, ROOF_C)
    for x in range(ox + 14, ox + n - 6, 21):                    # рёбра жёсткости
        c.darken(x, oy, x + 1, oy + h, 0.86)
    for cx in (ox + 70, ox + 176):                              # люки
        c.rect(cx - 9, oy + h // 2 - 8, cx + 9, oy + h // 2 + 8, (120, 120, 118))
        c.rect(cx - 8, oy + h // 2 - 7, cx + 8, oy + h // 2 + 7, (168, 166, 160))
    c.darken(ox, oy, ox + n, oy + 2, 0.90)
    c.darken(ox, oy + h - 2, ox + n, oy + h, 0.90)
    # скос между бортом и крышей — в цвет кузова, с бликом
    ex, ey = EDGE
    c.painted(ex, ey, ex + n, ey + 6, 1.12)
    c.shade[ey + 4:ey + 6, ex:ex + n] = 0.98


def draw_front(c):
    ox, oy = FRONT
    w = int(round(W * S))                       # 60
    h = int(round((Z4 - Z0) * S)) + 1           # 63

    def px(x):
        return ox + (x + HW) * S

    def pz(z):
        return oy + (Z4 - z) * S
    c.painted(ox, oy, ox + w, oy + h)
    for r in range(h):
        c.shade[oy + r, ox:ox + w] = 1.05 - 0.16 * (r / float(h))
    # маршрутный указатель над стеклом
    c.rect(px(-0.95), pz(2.96), px(0.95), pz(2.62), (12, 12, 12))
    amber = (236, 170, 40)
    for (dx, rows) in ((-17, ('###', '  #', ' # ', ' # ', ' # ')),            # «7»
                       (-9, ('###', '# #', '# #', '# #', '# #')),               # «ПОРТ»
                       (-5, ('###', '# #', '# #', '# #', '###')),
                       (-1, ('###', '# #', '###', '#  ', '#  ')),
                       (3, ('###', ' # ', ' # ', ' # ', ' # '))):
        for ry, row in enumerate(rows):
            for rx, ch in enumerate(row):
                if ch == '#':
                    c.dot(px(0) + dx + rx + (0 if dx < -10 else 4), pz(2.90) + ry, amber)
    # лобовое стекло из двух половин
    c.glass(px(-1.16), pz(2.56), px(-0.02), pz(1.36))
    c.glass(px(0.02), pz(2.56), px(1.16), pz(1.36))
    for sx in (-1, 1):                                                           # дворники
        for k in range(7):
            c.dot(px(sx * 0.55) + sx * k, pz(1.40) - k, (10, 10, 10))
    # решётка, фары, поворотники
    c.rect(px(-0.52), pz(1.10), px(0.52), pz(0.80), (24, 24, 25))
    for yy in range(int(pz(1.10)) + 1, int(pz(0.80)), 2):
        c.rect(px(-0.50), yy, px(0.50), yy + 1, (64, 64, 66))
    for sx in (-1, 1):
        cx, cz = px(sx * 0.86), pz(0.96)
        c.rect(cx - 3, cz - 3, cx + 3, cz + 3, STEEL)
        c.rect(cx - 2, cz - 2, cx + 2, cz + 2, (236, 236, 222))
        c.dot(cx - 1, cz - 1, (255, 255, 250))
        c.rect(px(sx * 1.14) - 1, cz - 2, px(sx * 1.14) + 1, cz + 2, (232, 140, 30))
    # бампер и номер
    c.rect(ox, pz(0.66), ox + w, oy + h, (52, 52, 54))
    c.rgb[int(pz(0.66)), ox:ox + w] = (96, 96, 98)
    c.rect(px(-0.26), pz(0.62), px(0.26), pz(0.46), (224, 224, 216))
    for k in range(-4, 5, 2):
        c.dot(px(0) + k, pz(0.56), (30, 30, 30))


def draw_rear(c):
    ox, oy = REAR
    w = int(round(W * S))
    h = int(round((Z4 - Z0) * S)) + 1

    def px(x):
        return ox + (x + HW) * S

    def pz(z):
        return oy + (Z4 - z) * S
    c.painted(ox, oy, ox + w, oy + h)
    for r in range(h):
        c.shade[oy + r, ox:ox + w] = 1.02 - 0.18 * (r / float(h))
    c.glass(px(-1.0), pz(2.50), px(1.0), pz(1.62))
    # крышка моторного отсека с жалюзи
    c.rect(px(-0.86), pz(1.42), px(0.86), pz(0.74), (0, 0, 0))
    c.painted(px(-0.86) + 1, pz(1.42) + 1, px(0.86) - 1, pz(0.74) - 1, 0.90)
    for yy in range(int(pz(1.36)), int(pz(0.82)), 2):
        c.darken(px(-0.70), yy, px(0.70), yy + 1, 0.55)
    # фонари: красный, оранжевый, белый
    for sx in (-1, 1):
        x = px(sx * 1.08)
        c.rect(x - 2, pz(1.40), x + 2, pz(0.80), (20, 20, 20))
        c.rect(x - 1, pz(1.38), x + 1, pz(1.18), (214, 28, 22))
        c.rect(x - 1, pz(1.16), x + 1, pz(1.00), (232, 140, 30))
        c.rect(x - 1, pz(0.98), x + 1, pz(0.84), (226, 226, 216))
    c.rect(ox, pz(0.66), ox + w, oy + h, (52, 52, 54))
    c.rgb[int(pz(0.66)), ox:ox + w] = (96, 96, 98)
    c.rect(px(-0.26), pz(0.62), px(0.26), pz(0.46), (224, 224, 216))
    for k in range(-4, 5, 2):
        c.dot(px(0) + k, pz(0.56), (30, 30, 30))
    c.rect(px(-0.3), pz(2.90), px(0.3), pz(2.66), (12, 12, 12))
    for ry, row in enumerate(('###', '  #', ' # ', ' # ', ' # ')):
        for rx, ch in enumerate(row):
            if ch == '#':
                c.dot(px(0) - 1 + rx, pz(2.88) + ry, (236, 170, 40))


def build(cars_src):
    """Собирает автобус; cars_src — папка набора машин (оттуда берётся колесо).  Возвращает запись для
    models.json."""
    from PIL import Image
    from panda3d.core import NodePath
    import import_psx as ip
    ip._panda()
    c = Canvas()
    draw_side(c, SIDE_R, True)
    draw_side(c, SIDE_L, False)
    draw_roof(c)
    draw_front(c)
    draw_rear(c)
    c.rect(DARK[0], DARK[1], DARK[0] + 24, DARK[1] + 12, (30, 30, 32))
    c.rect(CHROME[0], CHROME[1], CHROME[0] + 24, CHROME[1] + 6, (58, 58, 60))
    c.rect(CHROME[0], CHROME[1] + 6, CHROME[0] + 24, CHROME[1] + 12, (20, 20, 21))
    # «ручная» неровность краски и лёгкая грязь понизу
    rng = np.random.RandomState(3)
    noise = 1.0 + (rng.rand(T, T).astype(np.float32) - 0.5) * 0.07
    c.shade *= noise
    c.rgb *= (1.0 + (rng.rand(T, T, 1).astype(np.float32) - 0.5) * 0.05)

    # --- колесо от фургона: копируем его кусок текстуры и геометрию
    V, VT, faces = ip.read_obj(os.path.join(cars_src, 'Car 08', 'Car8.obj'))
    comps = ip.components(V, faces)
    zmin = V[:, 2].min()
    wheel = None
    for comp in comps:
        pts = np.array([V[vi] for fi in comp for vi, _ in faces[fi]])
        a, b = pts.min(0), pts.max(0)
        if len(comp) == 16 and a[2] < zmin + 0.06 and a[0] > 0 and a[1] > 0:
            wheel = (comp, (a + b) * 0.5, (b[1] - a[1] + b[2] - a[2]) * 0.25, b[0] - a[0])
    comp, wc, wr, ww = wheel
    uv = np.array([VT[ti] for fi in comp for _, ti in faces[fi]])
    u0, v0, u1, v1 = uv[:, 0].min(), uv[:, 1].min(), uv[:, 0].max(), uv[:, 1].max()
    src = np.asarray(Image.open(os.path.join(cars_src, 'Car 08', 'Car8.png')).convert('RGB')).astype(np.float32)
    sz = src.shape[0]
    sx0, sx1 = int(np.floor(u0 * sz)), int(np.ceil(u1 * sz))
    sy0, sy1 = int(np.floor((1.0 - v1) * sz)), int(np.ceil((1.0 - v0) * sz))
    wx, wy = WHEEL
    tile = src[sy0:sy1, sx0:sx1].copy()
    hh, ww_ = tile.shape[:2]
    yy, xx = np.mgrid[0:hh, 0:ww_]
    far = ((xx - ww_ * 0.5) ** 2 + (yy - min(hh, ww_) * 0.5) ** 2) ** 0.5 > min(hh, ww_) * 0.47
    tile[far & (tile[..., 0] > 100) & (yy < ww_)] = (32, 32, 32)     # уголки вокруг шины — в цвет резины
    c.rgb[wy:wy + (sy1 - sy0), wx:wx + (sx1 - sx0)] = tile
    c.paint[wy:wy + (sy1 - sy0), wx:wx + (sx1 - sx0)] = False

    def wheel_uv(t):
        return ((wx + (t[0] * sz - sx0)) / T, 1.0 - (wy + ((1.0 - t[1]) * sz - sy0)) / T)

    rgba = np.zeros((T, T, 4), np.uint8)
    sh = np.clip(c.shade * 127.5, 0, 255)
    rgba[..., :3] = np.where(c.paint[..., None], sh[..., None], np.clip(c.rgb, 0, 255)).astype(np.uint8)
    rgba[..., 3] = np.where(c.paint, 0, 255)
    vdir = os.path.join(OUT, 'veh')
    Image.fromarray(rgba, 'RGBA').save(os.path.join(vdir, 'bus.png'), optimize=True)
    Image.fromarray(np.where(c.paint, sh, 128.0).astype(np.uint8), 'L').save(os.path.join(vdir, 'bus_shade.png'),
                                                                               optimize=True)

    # --- кузов
    out = ip.GeomOut()

    def uv_side(org):
        return lambda p: ((org[0] + (p[1] + HL) * S) / T, 1.0 - (org[1] + (Z3 - p[2]) * S) / T)

    def uv_front(p):                            # спереди правый борт автобуса — слева от зрителя
        return ((FRONT[0] + (HW - p[0]) * S) / T, 1.0 - (FRONT[1] + (Z4 - p[2]) * S) / T)

    def uv_rear(p):
        return ((REAR[0] + (p[0] + HW) * S) / T, 1.0 - (REAR[1] + (Z4 - p[2]) * S) / T)

    def uv_roof(p):
        return ((ROOF[0] + (p[1] + HL) * S) / T, 1.0 - (ROOF[1] + (p[0] + XR) * S) / T)

    def uv_edge(p):
        k = (p[2] - Z3) / (Z4 - Z3)
        return ((EDGE[0] + (p[1] + HL) * S) / T, 1.0 - (EDGE[1] + 5.5 - k * 5.0) / T)

    def uv_flat(org, w=20, h=10):
        return lambda p: ((org[0] + 2 + (p[0] + HW) / W * w) / T, 1.0 - (org[1] + 1 + (p[1] + HL) / L * h) / T)

    def face(pts, fn):
        out.face(pts, [fn(p) for p in pts])

    yw = HL                                     # у лобового стекла борт чуть короче наверху
    # борта (обход — против часовой стрелки, если смотреть снаружи)
    face([(HW, -HL, Z0), (HW, HL, Z0), (HW, HL, ZB), (HW, YF, Z3), (HW, -HL, Z3)], uv_side(SIDE_R))
    face([(-HW, HL, Z0), (-HW, -HL, Z0), (-HW, -HL, Z3), (-HW, YF, Z3), (-HW, HL, ZB)], uv_side(SIDE_L))
    # скосы и крыша
    face([(HW, -HL, Z3), (HW, YF, Z3), (XR, YF - 0.16, Z4), (XR, YR, Z4)], uv_edge)
    face([(-HW, YF, Z3), (-HW, -HL, Z3), (-XR, YR, Z4), (-XR, YF - 0.16, Z4)], uv_edge)
    face([(-XR, YR, Z4), (XR, YR, Z4), (XR, YF - 0.16, Z4), (-XR, YF - 0.16, Z4)], uv_roof)
    # перед: низ, лобовое стекло, козырёк
    face([(HW, HL, Z0), (-HW, HL, Z0), (-HW, HL, ZB), (HW, HL, ZB)], uv_front)
    face([(HW, HL, ZB), (-HW, HL, ZB), (-HW, YF, Z3), (HW, YF, Z3)], uv_front)
    face([(HW, YF, Z3), (-HW, YF, Z3), (-XR, YF - 0.16, Z4), (XR, YF - 0.16, Z4)], uv_front)
    # зад
    face([(-HW, -HL, Z0), (HW, -HL, Z0), (HW, -HL, Z3), (-HW, -HL, Z3)], uv_rear)
    face([(-HW, -HL, Z3), (HW, -HL, Z3), (XR, YR, Z4), (-XR, YR, Z4)], uv_rear)
    # днище
    face([(-HW, HL, Z0), (HW, HL, Z0), (HW, -HL, Z0), (-HW, -HL, Z0)], uv_flat(DARK))

    def box(x0, x1, y0, y1, z0, z1, org):
        fn = uv_flat(org)
        face([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], fn)
        face([(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)], fn)
        face([(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)], fn)
        face([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], fn)
        face([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], fn)
        face([(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)], fn)
    # бамперы и зеркала
    box(-HW - 0.03, HW + 0.03, HL - 0.02, HL + 0.10, 0.42, 0.66, CHROME)
    box(-HW - 0.03, HW + 0.03, -HL - 0.10, -HL + 0.02, 0.42, 0.66, CHROME)
    for sx in (-1, 1):
        x = sx * (HW + 0.16)
        box(min(x, x - sx * 0.07), max(x, x - sx * 0.07), HL - 0.30, HL - 0.20, 1.86, 2.36, DARK)
        box(min(sx * HW, x), max(sx * HW, x), HL - 0.28, HL - 0.24, 2.24, 2.30, DARK)

    root = NodePath('car')
    body = root.attachNewNode('body')
    body.attachNewNode(out.node('skin'))
    # колесо
    k = WHEEL_R / wr
    wo = ip.GeomOut()
    for fi in comp:
        f = faces[fi]
        wo.face([((V[vi] - wc) * (WHEEL_W / ww if False else k)) for vi, _ in f], [wheel_uv(VT[ti]) for _, ti in f])
    root.attachNewNode(wo.node('wheel'))
    root.writeBamFile(os.path.join(vdir, 'bus.bam'))
    wxp = HW + 0.03 - ww * k * 0.5              # колёса чуть выступают из арок
    info = dict(W=W, L=L, H=Z4, tex=True,
                wheels=[dict(x=-wxp, y=AXLE_F, r=WHEEL_R), dict(x=wxp, y=AXLE_F, r=WHEEL_R),
                        dict(x=-wxp, y=AXLE_R, r=WHEEL_R), dict(x=wxp, y=AXLE_R, r=WHEEL_R)],
                head=[[-0.86, HL, 0.96], [0.86, HL, 0.96]], tail=[[-1.08, -HL, 1.28], [1.08, -HL, 1.28]])
    return info


if __name__ == '__main__':
    import import_psx as ip
    info = build(ip.cars_dir())
    mpath = os.path.join(OUT, 'models.json')
    with open(mpath, encoding='utf-8') as f:
        meta = json.load(f)
    meta['vehicles']['bus'] = info
    with open(mpath, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1, sort_keys=True, ensure_ascii=False)
    print('автобус готов')
