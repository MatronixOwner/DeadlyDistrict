# -*- coding: utf-8 -*-
"""Модели уличных объектов (фонари, деревья, скамейки...).

Каждая функция рисует объект в локальных координатах: +X — «перёд»
объекта, Z вверх, начало координат на земле.  Возвращает описание
столкновения:  None | ('c', r, h, flags) | ('b', hx, hy, h, flags)
(для 'b' — полуразмеры вдоль локальных X и Y).

Мусорный контейнер, бочка и мелкий мусор (мешки, коробки, бутылки, банки) — готовые модели набора PSX Waste
(Daniel Jurys): их треугольники лежат в assets/models/props.json (tools/import_extra.py) и добавляются в те же
общие сетки кварталов, что и всё остальное.  Нет файла — контейнер и бочку рисует код, как раньше.
"""
import json
import math
import os
import random

from . import settings
from .collision import F_CAR, F_PED, F_BULLET, F_BREAK, F_SIGHT, F_CAM, F_SOLID

GLOW = ('glow', 'add')
POOL = ('lightpool', 'add')
LAMP_COLOR = (1.0, 0.82, 0.52, 1.0)

BREAK_SOFT = F_CAR | F_BREAK                    # машина сносит, пешеход проходит
BREAK_HARD = F_CAR | F_PED | F_BULLET | F_BREAK   # машина сносит, пешеход обходит

METAL = (0.26, 0.28, 0.31, 1.0)
WOOD = (0.50, 0.34, 0.20, 1.0)

_models = None


def models():
    """Готовые модели мелких предметов: имя -> (текстура, [треугольник: три вершины (точка, uv)], полуразмеры)."""
    global _models
    if _models is None:
        _models = {}
        try:
            with open(os.path.join(settings.find_root(), 'assets', 'models', 'props.json'), 'rb') as f:
                raw = json.loads(f.read().decode('utf-8'))
            for name, m in raw.items():
                v = m['v']
                tris = []
                for i in range(0, len(v), 15):
                    tris.append(((v[i], v[i + 1], v[i + 2]), (v[i + 5], v[i + 6], v[i + 7]), (v[i + 10], v[i + 11], v[i + 12]),
                                 (v[i + 3], v[i + 4]), (v[i + 8], v[i + 9]), (v[i + 13], v[i + 14])))
                _models[name] = (m['tex'], tris, tuple(m['size']))
        except (IOError, OSError, ValueError, KeyError):
            _models = {}
    return _models


def model(mb, name, color=(1.0, 1.0, 1.0, 1.0), x=0.0, y=0.0, z=0.0, yaw=0.0, tip=0.0):
    """Добавить готовую модель в сетку.  yaw — поворот вокруг вертикали, tip — завалить набок (вокруг оси Y).
    Возвращает полуразмеры модели или None, если такой модели нет."""
    m = models().get(name)
    if m is None:
        return None
    tex, tris, size = m
    ca, sa = math.cos(yaw), math.sin(yaw)
    ct, st = math.cos(tip), math.sin(tip)

    def tr(q):
        px, pz = q[0] * ct + q[2] * st, -q[0] * st + q[2] * ct
        return (x + px * ca - q[1] * sa, y + px * sa + q[1] * ca, z + pz)
    for a, b, c, ua, ub, uc in tris:
        mb.tri(tex, tr(a), tr(b), tr(c), ua, ub, uc, color)
    return size


def glow(night, x, y, z, size, color=LAMP_COLOR):
    h = size * 0.5
    night.quad(GLOW, (x - h, y, z - h), (x + h, y, z - h), (x + h, y, z + h), (x - h, y, z + h), color=color)
    night.quad(GLOW, (x, y - h, z - h), (x, y + h, z - h), (x, y + h, z + h), (x, y - h, z + h), color=color)


def pool(night, x0, y0, x1, y1, z, uv=(0, 0, 1, 1), color=LAMP_COLOR, k=0.5):
    c = (color[0] * k, color[1] * k, color[2] * k, 1.0)
    night.quad(POOL, (x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z), uv, c)


# ---------------------------------------------------------------------------
def lamp(mb, night, p, rnd):
    if p.get('park'):
        mb.cylinder(None, 0, 0, 0, 3.6, 0.07, 5, METAL, cap_top=False)
        mb.cylinder(None, 0, 0, 0, 0.5, 0.13, 6, METAL, r_top=0.08, cap_top=False)
        mb.box(None, -0.22, -0.22, 3.6, 0.22, 0.22, 4.0, (0.96, 0.92, 0.72, 1), shade=False)
        mb.box(None, -0.3, -0.3, 4.0, 0.3, 0.3, 4.08, METAL)
        glow(night, 0, 0, 3.8, 2.0)
        pool(night, -5, -5, 5, 5, 0.05, k=0.42)
        return ('c', 0.14, 4.0, BREAK_HARD)
    mb.cylinder(None, 0, 0, 0, 6.5, 0.085, 5, METAL, cap_top=False)
    mb.cylinder(None, 0, 0, 0, 0.7, 0.16, 6, METAL, r_top=0.09, cap_top=False)
    mb.box(None, 0.0, -0.05, 6.42, 1.5, 0.05, 6.52, METAL)
    mb.box(None, 1.3, -0.2, 6.26, 2.1, 0.2, 6.42, METAL)
    mb.quad(None, (1.35, 0.16, 6.25), (2.05, 0.16, 6.25), (2.05, -0.16, 6.25), (1.35, -0.16, 6.25),
            color=(1.0, 0.95, 0.7, 1))
    glow(night, 1.7, 0, 6.2, 2.6)
    # световое пятно: часть на тротуаре (z=0), часть на дороге (ниже на высоту бордюра)
    curb = p.get('curb', 0.15)
    t0, tc, t1 = -3.6, 0.65, 7.0
    h = 5.3
    um = (tc - t0) / (t1 - t0)
    pool(night, t0, -h, tc, h, 0.05, (0, 0, um, 1))
    pool(night, tc, -h, t1, h, 0.05 - curb, (um, 0, 1, 1))
    return ('c', 0.16, 6.5, BREAK_HARD)


UP3 = ((0.0, 0.0, 1.0),) * 3
LEAF_TINTS = [(0.96, 1.0, 0.94), (0.86, 0.96, 0.84), (1.0, 1.0, 0.9), (0.9, 0.92, 0.86)]


def leaf_card(mb, key, p0, p1, p2, p3, cb, ct, uv=(0.0, 0.0, 1.0, 1.0)):
    """«Карточка» листвы (рисуется с двух сторон).  Нормали смотрят вверх, чтобы крона была освещена
    ровно, а не пятнами по плоскостям; cb/ct — цвет снизу и сверху."""
    u0, v0, u1, v1 = uv
    mb.tri(key, p0, p1, p2, (u0, v0), (u1, v0), (u1, v1), cb, UP3, c1=cb, c2=ct)
    mb.tri(key, p0, p2, p3, (u0, v0), (u1, v1), (u0, v1), cb, UP3, c1=ct, c2=ct)


def tree(mb, night, p, rnd):
    """Дерево: ствол с корой и крона из перекрещенных плоскостей с фотографией листвы."""
    s = p.get('size', 1.0)
    seed = p.get('seed', 0)
    r2 = random.Random(seed * 7 + 3)
    key = ('foliage_b' if seed % 3 == 1 else 'foliage_a', 'a')
    tint = r2.choice(LEAF_TINTS)
    ct = tint + (1.0,)
    cb = (tint[0] * 0.56, tint[1] * 0.58, tint[2] * 0.56, 1.0)
    cm = (tint[0] * 0.78, tint[1] * 0.80, tint[2] * 0.78, 1.0)
    th = (2.3 + r2.random() * 0.5) * s
    mb.cylinder('bark', 0, 0, 0, th + 1.6 * s, 0.23 * s, 6, (0.84, 0.78, 0.72, 1.0), r_top=0.08 * s, cap_top=False,
                uv_wrap=2.0)
    R = (2.3 + r2.random() * 0.6) * s
    z0 = th - 0.9 * s
    z1 = z0 + (4.6 + r2.random() * 0.9) * s
    zm = (z0 + z1) * 0.5
    a0 = r2.random() * math.pi
    for k in range(3):
        a = a0 + k * math.pi / 3.0
        ca, sa = math.cos(a) * R, math.sin(a) * R
        leaf_card(mb, key, (-ca, -sa, z0), (ca, sa, z0), (ca, sa, z1), (-ca, -sa, z1), cb, ct)
    # наклонные плоскости: крона не «исчезает» при взгляде сверху и снизу
    for k in range(2):
        a = a0 + 0.6 + k * math.pi / 2.0
        ca, sa = math.cos(a), math.sin(a)
        r = R * 0.92
        dz = r * 0.38
        zc = zm + (0.5 - k) * 0.9 * s
        leaf_card(mb, key, (-ca * r + sa * r, -sa * r - ca * r, zc - dz), (ca * r + sa * r, sa * r - ca * r, zc + dz),
                  (ca * r - sa * r, sa * r + ca * r, zc + dz), (-ca * r - sa * r, -sa * r + ca * r, zc - dz), cm, ct)
    # боковые «шапки» листвы
    for k in range(4):
        a = a0 + k * math.pi / 2.0 + r2.random() * 0.7
        d = R * (0.42 + r2.random() * 0.2)
        cx, cy = math.cos(a) * d, math.sin(a) * d
        cz = zm + (r2.random() - 0.35) * 1.5 * s
        r = R * (0.5 + r2.random() * 0.14)
        for j in range(2):
            aa = a + j * math.pi / 2.0 + 0.4
            ca, sa = math.cos(aa) * r, math.sin(aa) * r
            leaf_card(mb, key, (cx - ca, cy - sa, cz - r), (cx + ca, cy + sa, cz - r), (cx + ca, cy + sa, cz + r),
                      (cx - ca, cy - sa, cz + r), cm, ct)
    return ('c', 0.3 * s, 6.0 * s, F_SOLID | F_CAM)


def palm(mb, night, p, rnd):
    s = p.get('size', 1.0)
    lean_a = rnd.random() * 6.28
    lean = 0.5 + rnd.random() * 0.7
    segs = 5
    hgt = 6.2 * s
    px = py = 0.0
    for i in range(segs):
        t0 = i / float(segs)
        t1 = (i + 1) / float(segs)
        nx = math.cos(lean_a) * lean * t1 * t1
        ny = math.sin(lean_a) * lean * t1 * t1
        r0 = 0.22 - 0.08 * t0
        r1 = 0.22 - 0.08 * t1
        z0, z1 = hgt * t0, hgt * t1
        c = (1.0 - 0.08 * (i % 2), 0.9 - 0.07 * (i % 2), 0.72, 1.0)
        n = 5
        for k in range(n):
            a0 = k * 2 * math.pi / n
            a1 = (k + 1) * 2 * math.pi / n
            mb.quad('bark', (px + math.cos(a0) * r0, py + math.sin(a0) * r0, z0),
                    (px + math.cos(a1) * r0, py + math.sin(a1) * r0, z0),
                    (nx + math.cos(a1) * r1, ny + math.sin(a1) * r1, z1),
                    (nx + math.cos(a0) * r1, ny + math.sin(a0) * r1, z1), (k * 0.4, 0, k * 0.4 + 0.4, 1), c)
        px, py = nx, ny
    leaves = 8
    for k in range(leaves):
        a = k * 2 * math.pi / leaves + rnd.random() * 0.4
        ln = (2.6 + rnd.random() * 0.8) * s
        droop = 0.9 + rnd.random() * 0.9
        ca, sa = math.cos(a), math.sin(a)
        w = 0.62 * s
        mid = (px + ca * ln * 0.5, py + sa * ln * 0.5, hgt + 0.55 * s)
        tip = (px + ca * ln, py + sa * ln, hgt - droop * s)
        ox, oy = -sa * w, ca * w
        g = (0.9 + rnd.random() * 0.1,) * 3 + (1.0,)
        key = ('palm_leaf', 'a')
        mb.quad(key, (px - ox, py - oy, hgt), (px + ox, py + oy, hgt),
                (mid[0] + ox, mid[1] + oy, mid[2]), (mid[0] - ox, mid[1] - oy, mid[2]),
                uvs=((0, 0), (0, 1), (0.5, 1), (0.5, 0)), color=g)
        mb.quad(key, (mid[0] - ox, mid[1] - oy, mid[2]), (mid[0] + ox, mid[1] + oy, mid[2]),
                (tip[0] + ox * 0.6, tip[1] + oy * 0.6, tip[2]), (tip[0] - ox * 0.6, tip[1] - oy * 0.6, tip[2]),
                uvs=((0.5, 0), (0.5, 1), (1, 1), (1, 0)), color=g)
    mb.blob(None, px, py, hgt - 0.1, 0.35, 0.35, 0.3, (0.42, 0.30, 0.16, 1.0), seed=1)
    return ('c', 0.26, 6.0, F_SOLID | F_CAM)


def bench(mb, night, p, rnd):
    # сиденье вытянуто вдоль локальной Y, спинка сзади (-X)
    wood = rnd.choice([(0.62, 0.40, 0.24, 1.0), (0.30, 0.44, 0.30, 1.0), (0.56, 0.34, 0.22, 1.0)])
    mb.box('planks', -0.22, -0.85, 0.40, 0.24, 0.85, 0.47, wood, uv_m=0.5)
    mb.box('planks', -0.28, -0.85, 0.56, -0.21, 0.85, 0.95, wood, uv_m=0.5)
    for y in (-0.75, 0.75):
        mb.box(None, -0.26, y - 0.04, 0.0, 0.22, y + 0.04, 0.40, METAL)
        mb.box(None, -0.29, y - 0.04, 0.40, -0.22, y + 0.04, 0.9, METAL)
    return ('c', 0.55, 0.9, BREAK_HARD)


def bin_(mb, night, p, rnd):
    c = rnd.choice([(0.18, 0.38, 0.22, 1), (0.30, 0.32, 0.34, 1), (0.20, 0.30, 0.46, 1)])
    c = (min(1.0, c[0] * 1.5), min(1.0, c[1] * 1.5), min(1.0, c[2] * 1.5), 1.0)
    mb.cylinder('metal_paint', 0, 0, 0, 0.85, 0.27, 8, c, top_color=(0.05, 0.05, 0.05, 1), uv_wrap=2.0)
    mb.cylinder(None, 0, 0, 0.85, 0.92, 0.30, 8, METAL, cap_top=False)
    return ('c', 0.3, 0.9, BREAK_HARD)


def hydrant(mb, night, p, rnd):
    red = (0.78, 0.12, 0.10, 1)
    mb.cylinder(None, 0, 0, 0, 0.55, 0.13, 6, red, r_top=0.11)
    mb.cylinder(None, 0, 0, 0.55, 0.68, 0.09, 6, red, r_top=0.03)
    mb.box(None, -0.2, -0.05, 0.34, 0.2, 0.05, 0.44, (0.7, 0.7, 0.72, 1))
    return ('c', 0.17, 0.7, BREAK_SOFT | F_PED)


def newsbox(mb, night, p, rnd):
    c = rnd.choice([(0.16, 0.30, 0.70, 1), (0.74, 0.14, 0.12, 1), (0.86, 0.70, 0.10, 1), (0.14, 0.5, 0.26, 1)])
    mb.box(None, -0.22, -0.24, 0.0, 0.22, 0.24, 1.0, c)
    mb.quad(None, (0.225, -0.18, 0.5), (0.225, 0.18, 0.5), (0.225, 0.18, 0.92), (0.225, -0.18, 0.92),
            color=(0.80, 0.84, 0.86, 1))
    return ('c', 0.3, 1.0, BREAK_HARD)


def mailbox(mb, night, p, rnd):
    mb.box(None, -0.04, -0.04, 0.0, 0.04, 0.04, 1.0, WOOD)
    c = rnd.choice([(0.82, 0.82, 0.84, 1), (0.2, 0.2, 0.22, 1), (0.6, 0.12, 0.1, 1)])
    mb.box(None, -0.22, -0.11, 1.0, 0.22, 0.11, 1.24, c)
    mb.box(None, 0.0, 0.11, 1.12, 0.02, 0.13, 1.34, (0.85, 0.1, 0.1, 1))
    return ('c', 0.14, 1.2, BREAK_SOFT)


def cone(mb, night, p, rnd):
    o = (0.95, 0.42, 0.08, 1)
    mb.box(None, -0.2, -0.2, 0.0, 0.2, 0.2, 0.04, o)
    mb.cylinder(None, 0, 0, 0.04, 0.30, 0.15, 6, o, r_top=0.10, cap_top=False)
    mb.cylinder(None, 0, 0, 0.30, 0.44, 0.10, 6, (0.95, 0.95, 0.95, 1), r_top=0.065, cap_top=False)
    mb.cylinder(None, 0, 0, 0.44, 0.62, 0.065, 6, o, r_top=0.02)
    return ('c', 0.2, 0.6, BREAK_SOFT)


def busstop(mb, night, p, rnd):
    # навес: длина вдоль Y, открыт в сторону +X (к дороге)
    mb.box(None, -0.65, -1.7, 2.35, 0.75, 1.7, 2.45, (0.20, 0.36, 0.56, 1))
    for y in (-1.6, 1.6):
        mb.box(None, -0.62, y - 0.05, 0.0, -0.52, y + 0.05, 2.35, METAL)
    mb.box(None, -0.5, -1.2, 0.42, -0.1, 1.2, 0.48, WOOD)
    mb.box(None, -0.48, -1.1, 0.0, -0.42, -1.0, 0.42, METAL)
    mb.box(None, -0.48, 1.0, 0.0, -0.42, 1.1, 0.42, METAL)
    g = (0.62, 0.78, 0.86, 0.38)
    key = (None, 'glass')
    mb.quad2(key, (-0.58, -1.55, 0.35), (-0.58, 1.55, 0.35), (-0.58, 1.55, 2.2), (-0.58, -1.55, 2.2), color=g)
    mb.quad2(key, (-0.58, 1.62, 0.35), (0.5, 1.62, 0.35), (0.5, 1.62, 2.2), (-0.58, 1.62, 2.2), color=g)
    glow(night, 0.0, 0.0, 2.2, 1.6, (0.8, 0.9, 1.0, 0.7))
    return ('b', 0.7, 1.7, 2.4, F_SOLID | F_CAM)


DUMPSTER_TINTS = [(1.0, 1.0, 1.0, 1.0), (0.84, 0.92, 1.0, 1.0), (1.0, 0.92, 0.78, 1.0), (0.88, 0.88, 0.88, 1.0)]


def dumpster(mb, night, p, rnd):
    c = rnd.choice([(0.14, 0.32, 0.20, 1), (0.16, 0.24, 0.40, 1), (0.36, 0.20, 0.14, 1)])
    size = model(mb, 'dumpster', DUMPSTER_TINTS[rnd.randrange(len(DUMPSTER_TINTS))])
    if size is not None:
        return ('b', size[0], size[1], size[2], F_SOLID)
    c = (min(1.0, c[0] * 1.7), min(1.0, c[1] * 1.7), min(1.0, c[2] * 1.7), 1.0)
    mb.box('metal_paint', -0.55, -0.95, 0.12, 0.55, 0.95, 1.2, c, uv_m=1.6)
    mb.box(None, -0.6, -1.0, 1.2, 0.6, 1.0, 1.28, (0.1, 0.1, 0.1, 1))
    mb.box(None, -0.62, -0.5, 0.86, -0.55, 0.5, 0.94, METAL)
    mb.box(None, 0.55, -0.5, 0.86, 0.62, 0.5, 0.94, METAL)
    for y in (-0.8, 0.8):
        for x in (-0.45, 0.45):
            mb.box(None, x - 0.06, y - 0.06, 0.0, x + 0.06, y + 0.06, 0.12, METAL)
    return ('b', 0.6, 1.0, 1.3, F_SOLID)


def crate(mb, night, p, rnd):
    s = 0.5 + rnd.random() * 0.12
    mb.box('crate', -s, -s, 0.0, s, s, s * 2, (1, 1, 1, 1))
    return ('c', s * 1.15, s * 2, BREAK_HARD)


BARREL_TINTS = [(1.0, 1.0, 1.0, 1.0), (1.0, 0.86, 0.66, 1.0), (0.72, 0.80, 0.92, 1.0), (0.86, 0.86, 0.80, 1.0)]


def barrel(mb, night, p, rnd):
    c = rnd.choice([(0.40, 0.22, 0.14, 1), (0.16, 0.26, 0.42, 1), (0.5, 0.42, 0.12, 1)])
    if model(mb, 'barrel', BARREL_TINTS[rnd.randrange(len(BARREL_TINTS))], yaw=rnd.random() * 6.28) is None:
        c = (min(1.0, c[0] * 1.6), min(1.0, c[1] * 1.6), min(1.0, c[2] * 1.6), 1.0)
        mb.cylinder('metal_paint', 0, 0, 0, 0.9, 0.3, 8, c, top_color=(0.07, 0.06, 0.05, 1), uv_wrap=2.0)
    if p.get('fire'):
        glow(night, 0, 0, 1.1, 2.4, (1.0, 0.55, 0.15, 0.9))
        pool(night, -3.5, -3.5, 3.5, 3.5, 0.05, color=(1.0, 0.5, 0.15, 1.0), k=0.5)
        k = ('fire', 'add')
        night.quad(k, (-0.4, 0, 0.8), (0.4, 0, 0.8), (0.4, 0, 1.7), (-0.4, 0, 1.7))
        night.quad(k, (0, -0.4, 0.8), (0, 0.4, 0.8), (0, 0.4, 1.7), (0, -0.4, 1.7))
    return ('c', 0.32, 0.9, BREAK_HARD)


BAG_TINTS = [(1.0, 1.0, 1.0, 1.0), (0.80, 0.84, 0.95, 1.0), (0.78, 0.78, 0.78, 1.0), (1.0, 0.96, 0.86, 1.0)]


def trashbag(mb, night, p, rnd):
    """Мешки с мусором: один или кучка из двух-трёх."""
    n = int(p.get('n', 1))
    r = 0.0
    for k in range(n):
        ang = k * 2.4 + rnd.random()
        d = 0.0 if n == 1 else 0.30 + 0.08 * k
        s = model(mb, 'bag', BAG_TINTS[rnd.randrange(len(BAG_TINTS))], x=math.cos(ang) * d, y=math.sin(ang) * d,
                  yaw=rnd.random() * 6.28)
        if s is None:
            mb.cylinder(None, 0, 0, 0, 0.5, 0.28, 6, (0.10, 0.10, 0.11, 1))
            return ('c', 0.3, 0.5, BREAK_HARD)
        r = max(r, d + 0.30)
    return ('c', r, 0.6, BREAK_HARD)                    # машина раскидывает, пешком — обходить


def boxes(mb, night, p, rnd):
    """Картонные коробки: одна, стопка или россыпь."""
    n = int(p.get('n', 1))
    z = 0.0
    for k in range(n):
        if model(mb, 'box', (1.0, 1.0, 1.0, 1.0) if rnd.random() < 0.6 else (0.86, 0.80, 0.72, 1.0),
                 x=(rnd.random() - 0.5) * 0.12, y=(rnd.random() - 0.5) * 0.12, z=z, yaw=rnd.random() * 0.7 - 0.35) is None:
            mb.box(None, -0.22, -0.37, z, 0.22, 0.37, z + 0.30, (0.62, 0.50, 0.36, 1))
        z += 0.30
    return ('c', 0.42, z, BREAK_HARD)


def litter(mb, night, p, rnd):
    """Мелкий мусор под ногами: бутылки и мятые банки.  Не мешает ни пройти, ни проехать."""
    for k in range(int(p.get('n', 3))):
        ang = rnd.random() * 6.28
        d = float(p.get('r0', 0.15)) + rnd.random() * float(p.get('r', 0.9))
        x, y = math.cos(ang) * d, math.sin(ang) * d
        q = rnd.random()
        if q < 0.45:
            model(mb, 'can', x=x, y=y, z=0.004, yaw=rnd.random() * 6.28)
        elif q < 0.72:
            model(mb, 'bottle', x=x, y=y, yaw=rnd.random() * 6.28)                              # стоит
        else:
            model(mb, 'bottle', x=x, y=y, z=0.048, yaw=rnd.random() * 6.28, tip=math.pi / 2)    # лежит на боку
    return None


def tires(mb, night, p, rnd):
    for i in range(3):
        mb.cylinder(None, (i % 2) * 0.06, 0, i * 0.24, i * 0.24 + 0.22, 0.36, 8, (0.09, 0.09, 0.10, 1),
                    top_color=(0.05, 0.05, 0.05, 1))
    return ('c', 0.38, 0.72, BREAK_HARD)


WRECK_TINTS = [(1.0, 1.0, 1.0, 1.0), (0.80, 0.78, 0.76, 1.0), (0.62, 0.60, 0.60, 1.0)]


def wreck(mb, night, p, rnd):
    """Брошенный остов машины на пустыре: ржавый кузов без колёс, стёкол и дверных ручек."""
    size = model(mb, 'wreck', WRECK_TINTS[rnd.randrange(len(WRECK_TINTS))], z=-0.04, tip=(rnd.random() - 0.5) * 0.05)
    if size is not None:
        return ('b', size[0], size[1], size[2], F_SOLID)
    rust = (0.30, 0.17, 0.10, 1)
    dark = (0.12, 0.10, 0.09, 1)
    mb.box(None, -2.1, -0.85, 0.15, 2.1, 0.85, 0.7, rust)
    mb.box(None, -1.0, -0.78, 0.7, 0.7, 0.78, 1.25, dark)
    mb.box(None, -2.1, -0.85, 0.0, -1.5, 0.85, 0.15, dark)
    mb.box(None, 1.3, -0.85, 0.0, 1.9, 0.85, 0.15, dark)
    return ('b', 2.1, 0.9, 1.25, F_SOLID)


def hoop(mb, night, p, rnd):
    mb.cylinder(None, 0, 0, 0, 3.4, 0.09, 5, METAL, cap_top=False)
    mb.box(None, 0.0, -0.04, 3.0, 0.7, 0.04, 3.1, METAL)
    mb.box(None, 0.68, -0.9, 2.7, 0.74, 0.9, 3.8, (0.92, 0.92, 0.92, 1))
    mb.box(None, 0.74, -0.25, 2.92, 1.2, 0.25, 2.96, (0.9, 0.35, 0.1, 1))
    return ('c', 0.15, 3.4, F_SOLID)


def fountain(mb, night, p, rnd):
    R = 5.0 if p.get('big') else 3.0
    stone = (0.70, 0.69, 0.66, 1)
    mb.cylinder('concrete', 0, 0, 0, 0.6, R, 12, stone, uv_wrap=8.0, top_color=(0.62, 0.61, 0.58, 1))
    n = 12
    for i in range(n):
        a0, a1 = i * 2 * math.pi / n, (i + 1) * 2 * math.pi / n
        r = R - 0.4
        mb.tri('water', (0, 0, 0.62), (math.cos(a0) * r, math.sin(a0) * r, 0.62),
               (math.cos(a1) * r, math.sin(a1) * r, 0.62),
               (0.5, 0.5), (0.5 + math.cos(a0) * 0.5, 0.5 + math.sin(a0) * 0.5),
               (0.5 + math.cos(a1) * 0.5, 0.5 + math.sin(a1) * 0.5), (0.8, 0.95, 1.0, 1))
    mb.cylinder(None, 0, 0, 0.6, 1.9, 0.45, 8, stone, r_top=0.3)
    mb.cylinder(None, 0, 0, 1.9, 2.05, 1.1, 8, stone, r_top=1.25, cap_bottom=True,
                top_color=(0.55, 0.75, 0.9, 1))
    w = (0.75, 0.9, 1.0, 0.5)
    key = (None, 'glass')
    for a in range(4):
        ca, sa = math.cos(a * math.pi / 4), math.sin(a * math.pi / 4)
        mb.quad2(key, (-ca * 0.5, -sa * 0.5, 2.0), (ca * 0.5, sa * 0.5, 2.0),
                 (ca * 0.12, sa * 0.12, 3.6), (-ca * 0.12, -sa * 0.12, 3.6), color=w)
    glow(night, 0, 0, 2.2, 5.0, (0.5, 0.8, 1.0, 0.6))
    return ('c', R, 2.0, F_SOLID)


def statue(mb, night, p, rnd):
    stone = (0.66, 0.65, 0.62, 1)
    bronze = (0.36, 0.42, 0.34, 1)
    mb.box('concrete', -1.0, -1.0, 0, 1.0, 1.0, 0.4, stone, uv_m=2.0)
    mb.box('concrete', -0.7, -0.7, 0.4, 0.7, 0.7, 2.2, stone, uv_m=2.0)
    mb.box(None, -0.22, -0.3, 2.2, 0.0, -0.06, 3.1, bronze)
    mb.box(None, -0.22, 0.06, 2.2, 0.0, 0.3, 3.1, bronze)
    mb.box(None, -0.26, -0.36, 3.1, 0.06, 0.36, 4.0, bronze)
    mb.box(None, -0.2, -0.16, 4.0, 0.06, 0.16, 4.36, bronze)
    mb.box(None, -0.1, 0.36, 3.5, 0.9, 0.5, 3.66, bronze)
    return ('c', 1.25, 4.0, F_SOLID | F_CAM)


def gazebo(mb, night, p, rnd):
    white = (0.92, 0.9, 0.86, 1)
    R = 3.2
    n = 6
    mb.cylinder('wood', 0, 0, 0, 0.25, R + 0.3, n, (0.9, 0.9, 0.9, 1), uv_wrap=6.0)
    for i in range(n):
        a = i * 2 * math.pi / n
        mb.cylinder(None, math.cos(a) * R, math.sin(a) * R, 0.25, 2.9, 0.1, 5, white, cap_top=False)
    mb.cylinder('roof_tiles', 0, 0, 2.9, 4.4, R + 0.6, n, (1, 1, 1, 1), r_top=0.05, uv_wrap=6.0, smooth=False,
                cap_bottom=True)
    glow(night, 0, 0, 2.7, 3.0)
    return None


def pump(mb, night, p, rnd):
    mb.box(None, -0.3, -0.25, 0.0, 0.3, 0.25, 1.5, (0.86, 0.14, 0.12, 1))
    mb.box(None, -0.32, -0.27, 1.5, 0.32, 0.27, 1.62, (0.92, 0.92, 0.92, 1))
    mb.quad(None, (0.305, -0.18, 0.95), (0.305, 0.18, 0.95), (0.305, 0.18, 1.35), (0.305, -0.18, 1.35),
            color=(0.1, 0.12, 0.14, 1))
    mb.quad(None, (-0.305, 0.18, 0.95), (-0.305, -0.18, 0.95), (-0.305, -0.18, 1.35), (-0.305, 0.18, 1.35),
            color=(0.1, 0.12, 0.14, 1))
    return ('c', 0.4, 1.6, F_SOLID)


UMBRELLA_COLORS = [((0.9, 0.2, 0.2), (0.95, 0.95, 0.9)), ((0.2, 0.4, 0.85), (0.95, 0.95, 0.9)),
                   ((0.95, 0.75, 0.15), (0.9, 0.3, 0.2)), ((0.2, 0.7, 0.4), (0.95, 0.95, 0.9)),
                   ((0.9, 0.4, 0.7), (0.3, 0.8, 0.85)), ((0.95, 0.5, 0.1), (0.2, 0.3, 0.6))]


def umbrella(mb, night, p, rnd):
    ca, cb = UMBRELLA_COLORS[p.get('color', 0) % len(UMBRELLA_COLORS)]
    mb.cylinder(None, 0, 0, 0, 2.2, 0.035, 4, (0.9, 0.9, 0.9, 1), cap_top=False)
    n = 8
    for i in range(n):
        a0, a1 = i * 2 * math.pi / n, (i + 1) * 2 * math.pi / n
        c = (ca if i % 2 == 0 else cb) + (1.0,)
        p0 = (math.cos(a0) * 1.5, math.sin(a0) * 1.5, 1.85)
        p1 = (math.cos(a1) * 1.5, math.sin(a1) * 1.5, 1.85)
        mb.tri(None, (0, 0, 2.3), p0, p1, color=c)
        mb.tri(None, (0, 0, 2.3), p1, p0, color=(c[0] * 0.6, c[1] * 0.6, c[2] * 0.6, 1))
    # полотенце / лежак
    tc = rnd.choice([(0.9, 0.9, 0.3, 1), (0.3, 0.6, 0.9, 1), (0.9, 0.4, 0.4, 1), (0.95, 0.95, 0.95, 1)])
    mb.box(None, 0.5, -0.4, 0.0, 2.3, 0.4, 0.04, tc)
    return ('c', 0.1, 2.2, BREAK_SOFT)


def lifeguard(mb, night, p, rnd):
    white = (0.94, 0.93, 0.9, 1)
    red = (0.82, 0.16, 0.12, 1)
    for x in (-1.2, 1.2):
        for y in (-1.2, 1.2):
            mb.box(None, x - 0.08, y - 0.08, 0, x + 0.08, y + 0.08, 2.2, WOOD)
    mb.box('wood', -1.6, -1.6, 2.2, 1.9, 1.6, 2.35, (0.9, 0.9, 0.9, 1), uv_m=3.0)
    mb.box(None, -1.5, -1.3, 2.35, 0.7, 1.3, 4.3, white)
    mb.box(None, -1.7, -1.5, 4.3, 1.2, 1.5, 4.45, red)
    mb.quad(None, (0.71, -0.8, 3.0), (0.71, 0.8, 3.0), (0.71, 0.8, 3.9), (0.71, -0.8, 3.9),
            color=(0.2, 0.3, 0.4, 1))
    # пандус
    mb.quad2('wood', (1.9, -0.5, 2.3), (4.6, -0.5, 0.0), (4.6, 0.5, 0.0), (1.9, 0.5, 2.3),
             color=(0.85, 0.85, 0.85, 1))
    return ('b', 1.7, 1.6, 4.4, F_SOLID | F_CAM)


def crane(mb, night, p, rnd):
    y_ = (0.92, 0.72, 0.12, 1)
    H = 30.0
    for x in (-5.0, 5.0):
        for y in (-9.0, 9.0):
            mb.box(None, x - 0.6, y - 0.6, 0, x + 0.6, y + 0.6, H, y_)
    for y in (-9.0, 9.0):
        mb.box(None, -5.6, y - 0.5, H * 0.45, 5.6, y + 0.5, H * 0.45 + 1.0, y_)
    mb.box(None, -5.6, -9.6, H, 5.6, 9.6, H + 1.6, y_)
    # стрела над водой (+X) и противовес
    mb.box(None, -16.0, -1.4, H + 1.6, 42.0, 1.4, H + 3.4, y_)
    mb.box(None, -16.0, -2.4, H - 0.4, -11.0, 2.4, H + 1.6, (0.3, 0.3, 0.32, 1))
    mb.box(None, 14.0, -1.8, H - 1.2, 18.0, 1.8, H + 1.6, (0.86, 0.86, 0.86, 1))
    mb.box(None, 23.9, -0.06, H - 14.0, 24.1, 0.06, H + 1.6, (0.1, 0.1, 0.1, 1))
    mb.box(None, 21.0, -1.3, H - 16.6, 27.0, 1.3, H - 14.0, (0.7, 0.2, 0.16, 1))
    for (x, y) in ((-5.0, -9.0), (5.0, 9.0), (42.0, 0.0)):
        glow(night, x, y, H + 3.8, 3.0, (1.0, 0.2, 0.15, 1.0))
    return ('legs', [(-5.0, -9.0), (5.0, -9.0), (-5.0, 9.0), (5.0, 9.0)], 0.9, H)


def bollard(mb, night, p, rnd):
    mb.cylinder(None, 0, 0, 0, 0.55, 0.26, 7, (0.12, 0.12, 0.13, 1), r_top=0.2)
    mb.cylinder(None, 0, 0, 0.55, 0.7, 0.3, 7, (0.9, 0.75, 0.1, 1), r_top=0.26)
    return ('c', 0.3, 0.7, F_SOLID)


def rock(mb, night, p, rnd):
    s = p.get('size', 1.0)
    g = 0.42 + rnd.random() * 0.12
    mb.blob(None, 0, 0, 0.35 * s, 1.0 * s, 0.8 * s, 0.6 * s, (g, g, g * 0.96, 1), seed=p.get('seed', 0), jitter=0.3)
    return ('c', 0.85 * s, 0.9 * s, F_SOLID)


PLANE_COLORS = ((0.92, 0.92, 0.94), (0.86, 0.2, 0.16), (0.2, 0.36, 0.7), (0.95, 0.78, 0.2))


def plane(mb, night, p, rnd):
    """Лёгкий самолёт на стоянке: нос — в сторону +X."""
    body = (0.93, 0.93, 0.95, 1.0)
    cr, cg, cb = PLANE_COLORS[p.get('color', 0) % len(PLANE_COLORS)]
    stripe = (cr, cg, cb, 1.0)
    dark = (0.12, 0.13, 0.15, 1.0)
    # фюзеляж: три секции, сужается к хвосту
    mb.box(None, -1.2, -0.62, 0.9, 2.2, 0.62, 2.1, body)
    mb.box(None, 2.2, -0.5, 1.0, 3.3, 0.5, 1.9, stripe)                 # капот
    mb.box(None, -4.6, -0.36, 1.25, -1.2, 0.36, 2.0, body)
    mb.box(None, -1.2, -0.63, 1.38, 2.2, 0.63, 1.52, stripe)             # полоса по борту
    # кабина
    mb.box(None, -0.4, -0.56, 2.1, 1.5, 0.56, 2.66, (0.5, 0.68, 0.8, 1.0), top_color=body)
    # крыло сверху и стойки шасси
    mb.box(None, 0.0, -5.4, 2.66, 1.5, 5.4, 2.82, body, top_color=body)
    mb.box(None, 0.1, -5.4, 2.60, 1.4, -4.6, 2.67, stripe)
    mb.box(None, 0.1, 4.6, 2.60, 1.4, 5.4, 2.67, stripe)
    for y in (-1.25, 1.25):
        mb.box(None, 0.55, y - 0.05, 0.42, 0.75, y + 0.05, 1.0, dark)
        mb.cylinder_x(None, 0.3, 0.3 + 0.0001, y, 0.3, 0.0001, 4, dark)
        mb.box(None, 0.38, y - 0.12, 0.0, 0.92, y + 0.12, 0.56, dark)
    mb.box(None, 2.5, -0.1, 0.0, 2.9, 0.1, 0.9, dark)                    # носовая стойка
    # хвост
    mb.box(None, -4.7, -1.9, 1.7, -3.7, 1.9, 1.82, body)
    mb.box(None, -4.7, -0.07, 1.9, -3.5, 0.07, 3.3, stripe)
    # винт
    mb.box(None, 3.3, -0.12, 1.33, 3.5, 0.12, 1.57, dark)
    mb.box(None, 3.42, -0.06, 0.55, 3.48, 0.06, 2.35, dark)
    glow(night, 0.75, -5.4, 2.74, 1.2, (1.0, 0.15, 0.1, 1.0))
    glow(night, 0.75, 5.4, 2.74, 1.2, (0.15, 1.0, 0.3, 1.0))
    return ('b', 3.9, 1.0, 2.8, F_SOLID | F_CAM)


def windsock(mb, night, p, rnd):
    mb.cylinder(None, 0, 0, 0, 6.0, 0.07, 5, METAL, cap_top=False)
    for k in range(4):
        x0, x1 = 0.1 + k * 0.6, 0.1 + (k + 1) * 0.6
        r0, r1 = 0.42 - k * 0.07, 0.42 - (k + 1) * 0.07
        col = (0.95, 0.4, 0.1, 1.0) if k % 2 == 0 else (0.95, 0.95, 0.95, 1.0)
        mb.quad2(None, (x0, 0, 5.7 - r0), (x1, 0, 5.7 - r1 - 0.12 * (k + 1)), (x1, 0, 5.7 + r1 - 0.12 * (k + 1)),
                 (x0, 0, 5.7 + r0), color=col)
    return ('c', 0.12, 6.0, F_SOLID)


def roadpost(mb, night, p, rnd):
    """Сигнальный столбик у края трассы."""
    mb.box(None, -0.06, -0.06, 0.0, 0.06, 0.06, 0.9, (0.92, 0.92, 0.92, 1.0))
    mb.box(None, -0.065, -0.065, 0.62, 0.065, 0.065, 0.8, (0.1, 0.1, 0.1, 1.0))
    mb.box(None, -0.07, -0.07, 0.68, 0.07, 0.07, 0.75, (0.9, 0.3, 0.1, 1.0))
    return ('c', 0.09, 0.9, BREAK_SOFT)


BUILDERS = {
    'lamp': lamp, 'tree': tree, 'palm': palm, 'bench': bench, 'bin': bin_, 'hydrant': hydrant,
    'newsbox': newsbox, 'mailbox': mailbox, 'cone': cone, 'busstop': busstop, 'dumpster': dumpster,
    'crate': crate, 'barrel': barrel, 'tires': tires, 'wreck': wreck, 'hoop': hoop, 'fountain': fountain,
    'statue': statue, 'gazebo': gazebo, 'pump': pump, 'umbrella': umbrella, 'lifeguard': lifeguard,
    'crane': crane, 'bollard': bollard, 'rock': rock, 'plane': plane, 'windsock': windsock,
    'roadpost': roadpost, 'trashbag': trashbag, 'boxes': boxes, 'litter': litter,
}

# объекты, которые можно снести машиной
BREAKABLE = set(['lamp', 'bench', 'bin', 'hydrant', 'newsbox', 'mailbox', 'cone', 'crate', 'barrel', 'tires',
                 'umbrella', 'roadpost', 'trashbag', 'boxes'])
