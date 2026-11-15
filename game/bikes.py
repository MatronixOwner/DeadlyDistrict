# -*- coding: utf-8 -*-
"""Двухколёсный транспорт и квадроцикл: модели собираются кодом из простых деталей.

Готового набора мотоциклов в стиле остальных машин в открытых источниках не нашлось, поэтому рама,
бак, сиденье, вилка и колёса строятся здесь — грубовато и угловато, как на первой PlayStation.
Каждая модель состоит из трёх частей: «кузов» (всё неподвижное), «вилка» (руль с передним крылом —
поворачивается вместе с передним колесом) и колесо.  Краска — цвет бака и обтекателей.
"""
import math

from .meshbuilder import MeshBuilder

TYRE = (0.055, 0.055, 0.06, 1.0)
RIM = (0.62, 0.63, 0.66, 1.0)
DARK = (0.10, 0.10, 0.11, 1.0)
ENGINE = (0.30, 0.31, 0.33, 1.0)
STEEL = (0.70, 0.71, 0.74, 1.0)
SEAT = (0.06, 0.05, 0.05, 1.0)
LAMP = (1.0, 0.96, 0.82, 1.0)
RED = (0.75, 0.08, 0.06, 1.0)

# вид -> размеры: wb база, r радиус колеса, tw ширина шины, seat (y, z) сиденье, bars (y, z, полуширина) руль
KINDS = {
    'bike': dict(wb=1.40, r=0.31, tw=0.14, seat=(-0.28, 0.80), bars=(0.42, 1.00, 0.30), rake=0.26),
    'chopper': dict(wb=1.72, r=0.33, tw=0.17, seat=(-0.42, 0.64), bars=(0.30, 1.14, 0.36), rake=0.50),
    'scooter': dict(wb=1.26, r=0.22, tw=0.12, seat=(-0.30, 0.76), bars=(0.44, 1.04, 0.28), rake=0.12),
    'dirt': dict(wb=1.44, r=0.34, tw=0.11, seat=(-0.22, 0.90), bars=(0.44, 1.16, 0.38), rake=0.30),
    'bicycle': dict(wb=1.10, r=0.34, tw=0.045, seat=(-0.30, 0.92), bars=(0.36, 1.02, 0.26), rake=0.16),
    'quad': dict(wb=1.26, r=0.29, tw=0.24, seat=(-0.22, 0.84), bars=(0.34, 1.06, 0.36), rake=0.12, track=0.46),
}
_cache = {}


def _tube(mb, p0, p1, r, color, n=4):
    """Пруток между двумя точками: призма без торцов."""
    dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    ln = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    ax = (dx / ln, dy / ln, dz / ln)
    ref = (1.0, 0.0, 0.0) if abs(ax[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = (ax[1] * ref[2] - ax[2] * ref[1], ax[2] * ref[0] - ax[0] * ref[2], ax[0] * ref[1] - ax[1] * ref[0])
    ul = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2) or 1.0
    u = (u[0] / ul, u[1] / ul, u[2] / ul)
    v = (ax[1] * u[2] - ax[2] * u[1], ax[2] * u[0] - ax[0] * u[2], ax[0] * u[1] - ax[1] * u[0])
    ring = []
    for k in range(n):
        a = (k + 0.5) * 2.0 * math.pi / n
        ca, sa = math.cos(a) * r, math.sin(a) * r
        ring.append((u[0] * ca + v[0] * sa, u[1] * ca + v[1] * sa, u[2] * ca + v[2] * sa))
    for k in range(n):
        a, b = ring[k], ring[(k + 1) % n]
        mb.quad(None, (p0[0] + a[0], p0[1] + a[1], p0[2] + a[2]), (p0[0] + b[0], p0[1] + b[1], p0[2] + b[2]),
                (p1[0] + b[0], p1[1] + b[1], p1[2] + b[2]), (p1[0] + a[0], p1[1] + a[1], p1[2] + a[2]), color=color)


def _wheel(r, tw, spokes=False):
    mb = MeshBuilder()
    if spokes:
        # велосипедное колесо: обод из коротких брусков и спицы
        n = 12
        for k in range(n):
            a0, a1 = k * 2 * math.pi / n, (k + 1) * 2 * math.pi / n
            _tube(mb, (0, math.cos(a0) * r, math.sin(a0) * r), (0, math.cos(a1) * r, math.sin(a1) * r), tw * 0.5, TYRE)
        for k in range(6):
            a = k * math.pi / 6.0
            _tube(mb, (0, -math.cos(a) * r, -math.sin(a) * r), (0, math.cos(a) * r, math.sin(a) * r), 0.006, STEEL, 3)
        mb.cylinder_x(None, -tw, tw, 0.0, 0.0, 0.035, 6, DARK, cap_color=DARK)
    else:
        mb.cylinder_x(None, -tw * 0.5, tw * 0.5, 0.0, 0.0, r, 12, TYRE, cap_color=TYRE)
        mb.cylinder_x(None, -tw * 0.5 - 0.006, tw * 0.5 + 0.006, 0.0, 0.0, r * 0.62, 8, RIM, cap_color=RIM)
        mb.cylinder_x(None, -tw * 0.5 - 0.012, tw * 0.5 + 0.012, 0.0, 0.0, r * 0.18, 6, DARK, cap_color=DARK)
    return mb


def _fork(kind, K, paint):
    """Руль, вилка и переднее крыло — в осях, где переднее колесо стоит в начале координат по X и Y."""
    mb = MeshBuilder()
    r = K['r']
    by, bz, bw = K['bars']
    wy = K['wb'] * 0.5
    top = (0.0, by - wy, bz - 0.06)
    track = K.get('track', 0.0)
    if kind == 'quad':
        # рулевая колонка и руль; колёса висят на рычагах, которые нарисованы в кузове
        _tube(mb, (0.0, 0.02, r + 0.20), top, 0.03, DARK)
    else:
        for sx in (-0.085, 0.085):
            _tube(mb, (sx, 0.0, r), (sx * 0.7, top[1], top[2]), 0.022 if kind != 'bicycle' else 0.012, STEEL)
        # крыло над колесом
        if kind in ('dirt',):
            mb.box(None, -0.07, -0.20, r + 0.26, 0.07, 0.40, r + 0.30, paint)
        elif kind != 'bicycle':
            mb.box(None, -0.075, -0.24, r + 0.04, 0.075, 0.22, r + 0.09, paint if kind != 'chopper' else STEEL)
    # руль
    if kind == 'chopper':
        for sx in (-1, 1):
            _tube(mb, (sx * 0.06, top[1], top[2]), (sx * bw, top[1] - 0.10, bz + 0.10), 0.016, STEEL)
            _tube(mb, (sx * bw, top[1] - 0.10, bz + 0.10), (sx * (bw + 0.02), top[1] - 0.26, bz + 0.06), 0.022, DARK)
    else:
        _tube(mb, (-bw, top[1] - 0.04, bz), (bw, top[1] - 0.04, bz), 0.016, STEEL if kind != 'scooter' else DARK)
        for sx in (-1, 1):
            _tube(mb, (sx * (bw - 0.10), top[1] - 0.04, bz), (sx * (bw + 0.01), top[1] - 0.05, bz), 0.024, DARK)
    # фара
    if kind == 'bicycle':
        pass
    elif kind == 'scooter':
        mb.box(None, -0.13, top[1] + 0.02, bz - 0.20, 0.13, top[1] + 0.14, bz + 0.02, paint)
        mb.box(None, -0.07, top[1] + 0.14, bz - 0.16, 0.07, top[1] + 0.16, bz - 0.04, LAMP)
    elif kind == 'bike':
        pass                                            # фара у спортивного — в обтекателе
    else:
        mb.box(None, -0.09, top[1] + 0.03, bz - 0.26, 0.09, top[1] + 0.17, bz - 0.08, DARK if kind != 'chopper' else STEEL)
        mb.box(None, -0.07, top[1] + 0.17, bz - 0.24, 0.07, top[1] + 0.185, bz - 0.10, LAMP)
    return mb


def _body(kind, K, paint):
    mb = MeshBuilder()
    r = K['r']
    wb = K['wb']
    fy, ry = wb * 0.5, -wb * 0.5
    sy, sz = K['seat']
    p2 = (paint[0] * 0.72, paint[1] * 0.72, paint[2] * 0.72, 1.0)
    if kind == 'bike':
        mb.box(None, -0.15, -0.26, 0.26, 0.15, 0.36, 0.60, ENGINE)                 # двигатель
        mb.box(None, -0.17, 0.02, 0.60, 0.17, 0.50, 0.80, paint)                  # бак
        mb.box(None, -0.13, 0.06, 0.80, 0.13, 0.44, 0.88, paint)
        mb.box(None, -0.14, -0.56, 0.70, 0.14, 0.04, sz, SEAT)                    # сиденье
        mb.box(None, -0.12, -0.86, 0.74, 0.12, -0.54, 0.90, paint)                # хвост
        mb.box(None, -0.07, -0.875, 0.78, 0.07, -0.86, 0.86, RED)
        mb.box(None, -0.20, 0.46, 0.56, 0.20, 0.78, 0.98, paint)                  # обтекатель
        mb.box(None, -0.21, 0.10, 0.30, 0.21, 0.50, 0.62, p2)
        mb.quad(None, (-0.15, 0.60, 1.00), (0.15, 0.60, 1.00), (0.12, 0.48, 1.16), (-0.12, 0.48, 1.16),
                color=(0.10, 0.14, 0.16, 1.0))                                    # стекло
        mb.quad(None, (0.15, 0.60, 1.00), (-0.15, 0.60, 1.00), (-0.12, 0.48, 1.16), (0.12, 0.48, 1.16),
                color=(0.10, 0.14, 0.16, 1.0))
        mb.box(None, -0.10, 0.78, 0.74, 0.10, 0.795, 0.86, LAMP)
        _tube(mb, (0.16, 0.10, 0.34), (0.19, -0.70, 0.52), 0.04, STEEL, 5)        # выхлоп
        _tube(mb, (0.19, -0.70, 0.52), (0.20, -0.95, 0.58), 0.06, DARK, 6)
        for sx in (-0.09, 0.09):
            _tube(mb, (sx, -0.20, 0.42), (sx, ry, r), 0.025, DARK)                 # маятник
    elif kind == 'chopper':
        mb.box(None, -0.17, -0.34, 0.24, 0.17, 0.30, 0.58, ENGINE)
        for sx in (-0.10, 0.10):                                                  # цилиндры «вилкой»
            _tube(mb, (sx * 0.2, -0.02, 0.50), (sx * 0.2, -0.16, 0.74), 0.07, STEEL, 6)
            _tube(mb, (sx * 0.2, 0.06, 0.50), (sx * 0.2, 0.20, 0.74), 0.07, STEEL, 6)
        mb.box(None, -0.15, 0.10, 0.70, 0.15, 0.62, 0.86, paint)                  # бак-капля
        mb.box(None, -0.11, 0.16, 0.86, 0.11, 0.52, 0.92, paint)
        mb.box(None, -0.17, -0.62, 0.54, 0.17, -0.04, sz, SEAT)
        mb.box(None, -0.11, -0.98, 0.56, 0.11, -0.60, 0.62, paint)                # заднее крыло
        for sx in (-0.10, 0.10):
            _tube(mb, (sx, -0.92, 0.60), (sx, -0.98, 1.02), 0.012, STEEL)          # дуга за спиной
        _tube(mb, (-0.10, -0.98, 1.02), (0.10, -0.98, 1.02), 0.012, STEEL)
        mb.box(None, -0.06, -0.995, 0.62, 0.06, -0.98, 0.70, RED)
        for sx in (-0.20, 0.20):
            _tube(mb, (sx, 0.22, 0.36), (sx, -0.92, 0.34), 0.045, STEEL, 6)       # трубы по обе стороны
            _tube(mb, (sx * 0.5, -0.30, 0.40), (sx * 0.5, ry, r), 0.025, DARK)
        _tube(mb, (0.0, 0.52, 0.80), (0.0, fy - 0.46, 0.94), 0.03, DARK)          # хребет рамы к рулевой
    elif kind == 'scooter':
        mb.box(None, -0.20, -0.20, 0.20, 0.20, 0.42, 0.27, DARK)                  # площадка под ноги
        mb.box(None, -0.21, -0.74, 0.24, 0.21, -0.16, 0.66, paint)                # корпус под сиденьем
        mb.box(None, -0.17, -0.70, 0.66, 0.17, -0.10, sz, SEAT)
        mb.box(None, -0.21, 0.36, 0.22, 0.21, 0.46, 0.94, paint)                  # передний щиток
        mb.box(None, -0.16, 0.30, 0.50, 0.16, 0.37, 0.90, p2)
        mb.box(None, -0.08, -0.755, 0.50, 0.08, -0.74, 0.58, RED)
        _tube(mb, (0.21, -0.20, 0.30), (0.24, -0.72, 0.34), 0.05, STEEL, 5)
        mb.box(None, -0.11, ry - 0.20, r + 0.03, 0.11, ry + 0.22, r + 0.08, paint)
    elif kind == 'dirt':
        mb.box(None, -0.12, -0.22, 0.34, 0.12, 0.28, 0.64, ENGINE)
        mb.box(None, -0.13, 0.00, 0.64, 0.13, 0.44, 0.92, paint)                  # бак с накладками
        mb.box(None, -0.16, 0.18, 0.58, 0.16, 0.46, 0.80, p2)
        mb.box(None, -0.10, -0.66, 0.80, 0.10, 0.04, sz, SEAT)                    # длинное узкое сиденье
        mb.box(None, -0.09, -0.98, 0.82, 0.09, -0.62, 0.90, paint)                # высокое заднее крыло
        mb.box(None, -0.13, -0.66, 0.60, 0.13, -0.30, 0.80, paint)                # боковые номера
        mb.box(None, -0.05, -0.99, 0.84, 0.05, -0.98, 0.89, RED)
        _tube(mb, (0.12, 0.10, 0.60), (0.15, -0.80, 0.78), 0.035, STEEL, 5)       # высокий выхлоп
        for sx in (-0.07, 0.07):
            _tube(mb, (sx, -0.18, 0.46), (sx, ry, r), 0.022, STEEL)
        _tube(mb, (0.0, 0.40, 0.84), (0.0, fy - 0.36, 1.04), 0.03, DARK)
    elif kind == 'bicycle':
        head = (0.0, fy - 0.20, 0.98)
        bb = (0.0, -0.08, 0.30)                                                   # каретка
        st = (0.0, sy + 0.06, sz - 0.04)
        for a, b in ((head, bb), (head, st), (st, bb)):
            _tube(mb, a, b, 0.018, paint)
        for sx in (-0.05, 0.05):
            _tube(mb, (sx * 0.4, bb[1], bb[2]), (sx, ry, r), 0.012, paint)
            _tube(mb, (sx * 0.4, st[1], st[2]), (sx, ry, r), 0.010, paint)
        mb.box(None, -0.07, sy - 0.12, sz - 0.03, 0.07, sy + 0.14, sz + 0.02, SEAT)
        mb.cylinder_x(None, -0.012, 0.012, bb[1], bb[2], 0.09, 8, STEEL, cap_color=STEEL)     # звёздочка
        for sx, dz in ((-0.09, -0.15), (0.09, 0.15)):                             # педали
            _tube(mb, (sx * 0.3, bb[1], bb[2]), (sx, bb[1] + 0.02, bb[2] + dz), 0.010, STEEL)
            mb.box(None, sx - 0.04, bb[1] - 0.03, bb[2] + dz - 0.012, sx + 0.04, bb[1] + 0.07, bb[2] + dz + 0.012, DARK)
    elif kind == 'quad':
        tr = K['track']
        mb.box(None, -0.20, -0.44, 0.30, 0.20, 0.46, 0.60, ENGINE)
        mb.box(None, -0.22, -0.02, 0.60, 0.22, 0.46, 0.86, paint)                 # бак и «морда»
        mb.box(None, -0.18, 0.44, 0.52, 0.18, 0.74, 0.80, paint)
        mb.box(None, -0.12, 0.74, 0.60, 0.12, 0.755, 0.72, LAMP)
        mb.box(None, -0.19, -0.66, 0.66, 0.19, 0.00, sz, SEAT)
        for sx in (-1, 1):                                                        # крылья над колёсами
            mb.box(None, sx * (tr - 0.16), fy - 0.34, r + 0.30, sx * (tr + 0.14), fy + 0.34, r + 0.36, paint)
            mb.box(None, sx * (tr - 0.16), ry - 0.36, r + 0.30, sx * (tr + 0.14), ry + 0.34, r + 0.36, paint)
            _tube(mb, (sx * 0.16, fy - 0.05, 0.40), (sx * tr, fy, r), 0.03, DARK)  # рычаги
            _tube(mb, (sx * 0.16, ry + 0.05, 0.40), (sx * tr, ry, r), 0.03, DARK)
        for yy in (fy + 0.32, ry - 0.46):                                         # багажные решётки
            for sx in (-0.26, 0.0, 0.26):
                _tube(mb, (sx, yy - 0.16, 0.94 if yy > 0 else 0.90), (sx, yy + 0.16, 0.94 if yy > 0 else 0.90), 0.012, STEEL)
            _tube(mb, (-0.28, yy, 0.94 if yy > 0 else 0.90), (0.28, yy, 0.94 if yy > 0 else 0.90), 0.012, STEEL)
        mb.box(None, -0.20, ry - 0.36, 0.62, 0.20, ry - 0.345, 0.70, RED)
    return mb


def build(assets, kind, paint):
    """Детали модели: dict(body, fork, wheel, wheels=[(x, y, r, передние?)], seat, bars)."""
    key = (kind, int(paint[0] * 255), int(paint[1] * 255), int(paint[2] * 255))
    res = _cache.get(key)
    if res is not None:
        return res
    K = KINDS[kind]
    col = (paint[0], paint[1], paint[2], 1.0)
    body = _body(kind, K, col).build('body', assets.apply_state)
    fork = _fork(kind, K, col).build('fork', assets.apply_state)
    wheel = _wheel(K['r'], K['tw'], spokes=(kind == 'bicycle')).build('wheel', assets.apply_state)
    fy, ry = K['wb'] * 0.5, -K['wb'] * 0.5
    if kind == 'quad':
        t = K['track']
        wheels = [(-t, fy, K['r'], True), (t, fy, K['r'], True), (-t, ry, K['r'], False), (t, ry, K['r'], False)]
    else:
        wheels = [(0.0, fy, K['r'], True), (0.0, ry, K['r'], False)]
    res = dict(body=body, fork=fork, wheel=wheel, wheels=wheels, seat=K['seat'], bars=K['bars'], front_y=fy)
    _cache[key] = res
    return res
