# -*- coding: utf-8 -*-
"""Рельеф мира: берега, пляжи, холмы — всё, что лежит за пределами кварталов и дорог.

    pip install numpy scipy pillow
    python tools/gen_terrain.py            # -> assets/terrain/{terrain.json, height.bin, terrain.bam}
    python tools/gen_terrain.py --png out.png   # ещё и картинка для проверки глазами

Раскладка города (дороги, кварталы, причалы) берётся из game/city.py; рельеф под неё подгоняется:
под дорогами и кварталами он плоский и лежит чуть ниже них, дальше — берег, пляж или холмы.
Если раскладка меняется, рельеф нужно пересобрать: в terrain.json записана её подпись,
и тест сверяет подпись с городом.

Игре для работы нужны только готовые файлы; numpy и scipy ей не требуются.
"""
import json
import os
import struct
import sys

import numpy as np
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game.city import City, CURB, SIDEWALK, WATER_Z, BEACH_W, WEDGE_COLS, WEDGE_J1         # noqa: E402
from game.terrain import Terrain, FLAT, C_GRASS, C_SAND, C_ROCK, C_FOREST, C_FIELD, C_SEA   # noqa: E402

OUT = os.path.join(ROOT, 'assets', 'terrain')
STEP = 10.0             # шаг сетки высот, м
FINE = 2                # во сколько раз мельче сетка, на которой всё считается
CHUNK = 16              # клеток в куске геометрии по стороне
X_MIN, X_MAX = -850.0, 1520.0
Y_MIN, Y_MAX = -660.0, 1340.0
SEED = 20260


def fbm(shape, cell, rng, octaves=3, gain=0.5):
    """Плавный шум 0..1: сумма сглаженных случайных решёток (cell — размер пятна в узлах)."""
    out = np.zeros(shape)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        c = max(2.0, cell / (2 ** o))
        gy, gx = int(shape[0] / c) + 3, int(shape[1] / c) + 3
        g = rng.random((gy, gx))
        z = ndimage.zoom(g, (shape[0] / (gy - 2.0), shape[1] / (gx - 2.0)), order=3)
        oy, ox = (z.shape[0] - shape[0]) // 2, (z.shape[1] - shape[1]) // 2
        out += amp * z[oy:oy + shape[0], ox:ox + shape[1]]
        tot += amp
        amp *= gain
    out /= tot
    lo, hi = out.min(), out.max()
    return (out - lo) / (hi - lo)


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class Grid(object):
    """Мелкая сетка, на которой считаются маски и высоты."""

    def __init__(self):
        self.h = STEP / FINE
        self.nx = int(round((X_MAX - X_MIN) / self.h)) + 1
        self.ny = int(round((Y_MAX - Y_MIN) / self.h)) + 1
        self.x = X_MIN + np.arange(self.nx) * self.h
        self.y = Y_MIN + np.arange(self.ny) * self.h
        self.X, self.Y = np.meshgrid(self.x, self.y)

    def rect(self, mask, x0, y0, x1, y1, value=True, grow=0.0):
        i0 = int(np.ceil((x0 - grow - X_MIN) / self.h))
        i1 = int(np.floor((x1 + grow - X_MIN) / self.h))
        j0 = int(np.ceil((y0 - grow - Y_MIN) / self.h))
        j1 = int(np.floor((y1 + grow - Y_MIN) / self.h))
        i0, j0 = max(0, i0), max(0, j0)
        i1, j1 = min(self.nx - 1, i1), min(self.ny - 1, j1)
        if i1 >= i0 and j1 >= j0:
            mask[j0:j1 + 1, i0:i1 + 1] = value


def build(city):
    g = Grid()
    rng = np.random.default_rng(SEED)
    shape = (g.ny, g.nx)
    sw = SIDEWALK

    # ------------------------------------------------------------------ маски застройки
    urban = np.zeros(shape, bool)       # дороги, кварталы, площадки: тут рельеф плоский
    covered = np.zeros(shape, bool)     # целиком закрыто геометрией города: рельеф не рисуем
    isle = np.zeros(shape, bool)        # застройка острова
    main = np.zeros(shape, bool)        # застройка на материке
    seed_kind = np.zeros(shape, np.uint8)       # 1 обычный берег, 2 пляж, 3 причал

    def is_isle(i, j):
        return i <= city.isle_i1 and j <= city.isle_j1

    for b in city.blocks:
        g.rect(urban, b.x0, b.y0, b.x1, b.y1, grow=6.0)
        g.rect(covered, b.x0, b.y0, b.x1, b.y1)
        m = isle if is_isle(b.i, b.j) else main
        g.rect(m, b.x0, b.y0, b.x1, b.y1, grow=6.0)
    for key, s in city.segs.items():
        hw = s['width'] * 0.5
        if s['kind'] == 'h':
            r = (s['a'], s['c'] - hw, s['b'], s['c'] + hw)
        else:
            r = (s['c'] - hw, s['a'], s['c'] + hw, s['b'])
        if s['bridge'] is not None:
            continue                    # под мостом — что получится: берег и вода
        grow = 14.0 if s['rural'] else sw + 5.0
        g.rect(urban, *r, grow=grow)
        g.rect(covered, *r)
        m = isle if is_isle(s['i'], s['j']) and not s['rural'] else main
        g.rect(m, *r, grow=grow)
    for (i, j), n in city.nodes.items():
        r = (n.x - n.hw, n.y - n.hh, n.x + n.hw, n.y + n.hh)
        grow = 14.0 if n.rural else sw + 5.0
        g.rect(urban, *r, grow=grow)
        g.rect(covered, *r)
        m = isle if (i <= city.isle_i1 + 1 and j <= city.isle_j1 + 1) and not n.rural else main
        g.rect(m, *r, grow=grow)
    for (x0, y0, x1, y1) in city.walk_strips:
        g.rect(covered, x0, y0, x1, y1)
    seed_kind[isle] = 1
    # причалы: бетон до самой воды, дальше — обрыв
    dk = city.special['docks']
    g.rect(urban, dk['x0'], dk['y0'], dk['x1'], dk['y1'], grow=1.0)
    g.rect(covered, dk['x0'], dk['y0'], dk['x1'], dk['y1'])
    g.rect(isle, dk['x0'], dk['y0'], dk['x1'], dk['y1'])
    g.rect(seed_kind, dk['x0'], dk['y0'], dk['x1'], dk['y1'], value=3)
    # городской пляж: широкая ровная полоса песка
    bc = city.special['beach']
    beach = np.zeros(shape, bool)
    g.rect(beach, bc['x0'], bc['y0'] + 14.0, bc['x1'], bc['y1'])
    isle |= beach
    seed_kind[beach] = 2

    d_urban = ndimage.distance_transform_edt(~urban) * g.h

    # ------------------------------------------------------------------ суша
    n_coast = fbm(shape, 46, rng, 3)                    # изрезанность берега
    n_big = fbm(shape, 150, rng, 2)
    # остров: застройка плюс полоса берега (ширина зависит от того, какой это берег)
    d_isle, idx = ndimage.distance_transform_edt(~isle, return_indices=True)
    d_isle *= g.h
    kind = seed_kind[idx[0], idx[1]]
    margin = np.where(kind == 3, 1.5, np.where(kind == 2, 16.0, 16.0 + 70.0 * n_coast * n_coast + 34.0 * n_big))
    land_isle = d_isle < margin
    xs, ys = city.xs, city.ys
    ix1 = xs[city.isle_i1 + 1] + 7.0            # восточный и северный края застройки острова
    iy1 = ys[city.isle_j1 + 1] + 7.0
    # мысы и косы: без них остров — прямоугольник с закруглёнными углами
    for (cx, cy, rad) in ((xs[0] - 30.0, iy1 + 20.0, 95.0),         # северо-западный мыс
                          (xs[0] - 95.0, ys[3] + 30.0, 80.0),        # западный полуостров
                          (xs[0] - 60.0, ys[6], 60.0),
                          (xs[11] + 30.0, ys[0] + 10.0, 70.0),        # коса у портового ковша
                          (xs[4], iy1 + 45.0, 55.0)):                 # северная отмель
        land_isle |= np.hypot(g.X - cx, g.Y - cy) < rad * (0.7 + 0.6 * n_coast)
    # пролив и протока должны остаться открытыми
    land_isle &= (g.Y < iy1 + 78.0) & ((g.X < ix1 + 62.0) | (kind == 3))
    # Ковши: клинья между лопастями острова севернее садов — вода до самого пролива.  На чертеже это
    # узкий канал между двумя улицами, на местности он раскрывается веером (см. game/warp.py)
    for wc in WEDGE_COLS:
        ax = xs[wc] + city.wx[wc] * 0.5 + sw + 7.0
        bx = xs[wc + 1] - city.wx[wc + 1] * 0.5 - sw - 7.0
        ay = ys[WEDGE_J1 + 1] + city.wy[WEDGE_J1 + 1] * 0.5 + sw + 7.0
        land_isle &= ~((g.X > ax) & (g.X < bx) & (g.Y > ay))
    # материк: север (за проливом) и восток (за протокой), с общим углом на северо-востоке
    y_n = ys[9] - 7.0 - sw - 34.0               # северный берег пролива
    x_w = xs[2] - 6.0 - 230.0                   # западный берег материка
    x_e = xs[13] - 6.0 - sw - 38.0              # восточный берег протоки
    y_s = ys[3] - 6.0 - 150.0                   # южный берег восточной земли
    n_mid = fbm(shape, 84, rng, 2)
    wob = (n_coast - 0.5) * 100.0 + (n_big - 0.5) * 190.0 + (n_mid - 0.5) * 70.0
    north = np.minimum(g.Y - y_n, g.X - x_w)
    east = np.minimum(g.X - x_e, g.Y - y_s)
    sd_main = np.maximum(north, east) + wob
    # материк не подходит к острову ближе этого: пролив и протока остаются водой
    sd_main = np.minimum(sd_main, np.where(g.X < ix1 + 150.0, g.Y - (iy1 + 125.0), 1e9))
    sd_main = np.minimum(sd_main, np.where(g.Y < iy1 + 80.0, g.X - (ix1 + 150.0), 1e9))
    # бухта у Заречья и мыс с маяком на юго-востоке
    cove = np.hypot((g.X - (xs[10] + 70.0)) / 1.5, g.Y - (y_n - 10.0))
    sd_main -= 60.0 * np.exp(-(cove / 70.0) ** 2)
    cape = np.hypot(g.X - (xs[14] + 40.0), (g.Y - (y_s - 40.0)) / 1.2)
    sd_main += 95.0 * np.exp(-(cape / 60.0) ** 2)
    d_main = ndimage.distance_transform_edt(~main) * g.h
    land_main = (sd_main > 0.0) | (d_main < 30.0 + 16.0 * n_coast)
    land = land_isle | land_main
    # мелкие острова-огрызки и лужи убираем
    lab, n = ndimage.label(land)
    if n > 1:
        sizes = ndimage.sum(land, lab, range(1, n + 1))
        for k, sz in enumerate(sizes):
            if sz * g.h * g.h < 2500.0:
                land[lab == k + 1] = False
    lab, n = ndimage.label(~land)
    if n > 1:
        sizes = ndimage.sum(~land, lab, range(1, n + 1))
        for k, sz in enumerate(sizes):
            if sz * g.h * g.h < 6000.0:
                land[lab == k + 1] = True

    sd = (ndimage.distance_transform_edt(land) - ndimage.distance_transform_edt(~land)) * g.h   # >0 — суша
    on_main = land & ~land_isle
    is_beach = ndimage.distance_transform_edt(~beach) * g.h < 20.0

    # ------------------------------------------------------------------ высоты
    slope = np.where(is_beach, 0.035, 0.085)
    h_land = np.minimum(FLAT, WATER_Z + 0.02 + np.maximum(sd, 0.0) * slope)
    h_sea = WATER_Z - 0.35 - np.clip(-sd, 0.0, 90.0) * 0.05
    h = np.where(land, h_land, h_sea)
    # холмы: только на материке, вдали от дорог и от берега
    inland = smoothstep((d_urban - 32.0) / 130.0) * smoothstep((sd - 18.0) / 110.0) * on_main
    n_hill = fbm(shape, 62, rng, 4, 0.55)
    n_ridge = fbm(shape, 120, rng, 3)
    x_edge = xs[-1] + 6.0
    y_edge = ys[-1] + 6.0
    border = np.maximum(smoothstep((g.X - (x_edge + 20.0)) / 170.0), smoothstep((g.Y - (y_edge + 20.0)) / 170.0))
    amp = 7.0 + 16.0 * n_ridge + 46.0 * border
    hills = amp * (0.25 + 0.75 * n_hill)
    # отдельные горки: между Заречьем и трассой, у маяка, за аэродромом
    for (cx, cy, rad, top) in ((xs[12] + 108.0, 730.0, 120.0, 20.0), (xs[14] - 180.0, ys[9] + 40.0, 110.0, 16.0),
                               (xs[1] - 60.0, ys[12], 130.0, 18.0), (xs[12] + 60.0, ys[13] + 60.0, 150.0, 26.0)):
        hills += top * np.exp(-(np.hypot(g.X - cx, g.Y - cy) / rad) ** 2)
    h = h + inland * hills
    # лёгкая волнистость равнины
    plain = smoothstep((d_urban - 20.0) / 60.0) * smoothstep((sd - 12.0) / 40.0) * land
    h = h + plain * (fbm(shape, 30, rng, 2) - 0.35) * 1.3 * (1.0 - 0.6 * is_beach)
    # сгладить и вернуть плоскость под городом
    hs = ndimage.gaussian_filter(h, 1.2)
    h = np.where(land, hs, h)
    flat = smoothstep((d_urban - 6.0) / 18.0)
    h = np.where(land, FLAT + (h - FLAT) * flat, h)
    h[urban] = np.where(land[urban], FLAT, h[urban])
    # берег не должен «всплывать» из-за сглаживания
    h = np.where(~land, np.minimum(h, WATER_Z - 0.3), h)
    # край мира: гладкий подъём у границы сетки, чтобы за ним ничего не было видно
    h = np.maximum(h, np.where(on_main, 0.0, -99.0) * 0 + h)

    # ------------------------------------------------------------------ покрытие
    gy_, gx_ = np.gradient(h, g.h)
    steep = np.hypot(gx_, gy_)
    n_forest = fbm(shape, 44, rng, 3)
    n_field = fbm(shape, 70, rng, 2)
    cover = np.full(shape, C_GRASS, np.uint8)
    sand_w = np.where(is_beach, 60.0, 9.0 + 8.0 * n_coast)
    sand = land & (sd < sand_w) & (steep < 0.35) & (kind != 3)
    cover[sand] = C_SAND
    forest = land & ~sand & (d_urban > 26.0) & (steep < 0.75) & (sd > 20.0) & \
        (n_forest > np.where(on_main, 0.46, 0.60))
    cover[forest] = C_FOREST
    field = land & ~sand & ~forest & on_main & (steep < 0.08) & (n_field > 0.62) & (d_urban > 14.0)
    cover[field] = C_FIELD
    rock = land & (steep > 0.62)
    cover[rock] = C_ROCK
    cover[~land] = C_SEA

    return dict(grid=g, h=h, cover=cover, land=land, sd=sd, steep=steep, urban=urban, covered=covered,
                d_urban=d_urban, is_beach=is_beach, on_main=on_main, noise=fbm(shape, 26, rng, 3),
                noise2=fbm(shape, 90, rng, 2))


def write_bin(res, city):
    os.makedirs(OUT, exist_ok=True)
    h = res['h'][::FINE, ::FINE]
    cover = res['cover'][::FINE, ::FINE]
    ny, nx = h.shape
    cm = np.clip(np.round(h * 100.0), -32000, 32000).astype('<i2')
    with open(os.path.join(OUT, 'height.bin'), 'wb') as f:
        f.write(cm.tobytes())
        f.write(cover.astype(np.uint8).tobytes())
    meta = dict(x0=X_MIN, y0=Y_MIN, step=STEP, nx=int(nx), ny=int(ny), signature=city.signature(),
                chunk=CHUNK, flat=FLAT, max_height=round(float(h.max()), 2))
    with open(os.path.join(OUT, 'terrain.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1, sort_keys=True)
    return cm.astype(np.float64) * 0.01, cover, meta


def write_bam(res, hq, cover):
    """Готовая геометрия: куски CHUNK x CHUNK клеток; в каждом — трава и поверх неё песок и камень."""
    from panda3d.core import (loadPrcFileData, GeomVertexFormat, GeomVertexData, Geom, GeomTriangles, GeomNode,
                              NodePath, Filename, BoundingBox, LPoint3)
    loadPrcFileData('', 'window-type none\naudio-library-name null\n')
    ny, nx = hq.shape
    f2 = FINE
    covered = res['covered']
    # клетка закрыта городом, если закрыты все её мелкие узлы
    cov_cell = np.ones((ny - 1, nx - 1), bool)
    for dy in range(f2 + 1):
        for dx in range(f2 + 1):
            cov_cell &= covered[dy:dy + (ny - 1) * f2:f2, dx:dx + (nx - 1) * f2:f2]
    # нормали
    gy_, gx_ = np.gradient(hq, STEP)
    nrm = np.dstack([-gx_, -gy_, np.ones_like(hq)])
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    steep = np.hypot(gx_, gy_)
    noise = res['noise'][::f2, ::f2]
    noise2 = res['noise2'][::f2, ::f2]
    sd = res['sd'][::f2, ::f2]
    is_beach = res['is_beach'][::f2, ::f2]
    X = X_MIN + np.arange(nx) * STEP
    Y = Y_MIN + np.arange(ny) * STEP
    XX, YY = np.meshgrid(X, Y)

    # --- цвет травы: оттенок от шума, темнее в лесу, желтее на полях
    base = np.empty((ny, nx, 4))
    k = 0.80 + 0.30 * noise
    base[..., 0] = k * (0.94 + 0.14 * noise2)
    base[..., 1] = k * 1.0
    base[..., 2] = k * (0.86 + 0.10 * noise2)
    fo = ndimage.gaussian_filter((cover == C_FOREST).astype(float), 0.8)
    fi = ndimage.gaussian_filter((cover == C_FIELD).astype(float), 0.8)
    for c, (fr, fg, fb) in enumerate(((0.70, 0.80, 0.66), (1.18, 1.04, 0.62))):
        m = (fo, fi)[c]
        base[..., 0] = base[..., 0] * (1 - m) + base[..., 0] * fr * m
        base[..., 1] = base[..., 1] * (1 - m) + base[..., 1] * fg * m
        base[..., 2] = base[..., 2] * (1 - m) + base[..., 2] * fb * m
    base[..., 3] = 1.0
    base = np.clip(base, 0.0, 1.0)
    # --- песок: у воды и на пляже; под водой — темнее
    sand_a = ndimage.gaussian_filter((cover == C_SAND).astype(float), 0.7)
    sand_a = np.maximum(sand_a, smoothstep((WATER_Z + 0.5 - hq) / 0.6))        # у самой воды и под ней
    sand_a = np.clip(sand_a * 1.25, 0.0, 1.0)
    sand = np.empty((ny, nx, 4))
    wet = smoothstep((WATER_Z + 0.15 - hq) / 0.5)
    sk = (0.92 + 0.14 * noise) * (1.0 - 0.28 * wet)
    sand[..., 0] = sk
    sand[..., 1] = sk * 0.98
    sand[..., 2] = sk * 0.94
    sand[..., 3] = sand_a
    # --- камень: на крутых склонах
    rock_a = smoothstep((steep - 0.42) / 0.3)
    rock = np.empty((ny, nx, 4))
    rk = 0.78 + 0.3 * noise
    rock[..., 0] = rk
    rock[..., 1] = rk
    rock[..., 2] = rk
    rock[..., 3] = rock_a

    fmt = GeomVertexFormat.getV3n3c4t2()
    root = NodePath('terrain')
    layers = (('grass', 6.0, base, None), ('sand|decal', 7.0, sand, sand_a), ('rock|decal', 9.0, rock, rock_a))
    ntri = 0
    for cy in range(0, ny - 1, CHUNK):
        for cx in range(0, nx - 1, CHUNK):
            y1, x1 = min(ny - 1, cy + CHUNK), min(nx - 1, cx + CHUNK)
            sub_h = hq[cy:y1 + 1, cx:x1 + 1]
            if sub_h.max() < WATER_Z + 0.02:
                continue                            # целиком под водой — не нужен
            chunk = root.attachNewNode('c_%d_%d' % (cx // CHUNK, cy // CHUNK))
            sy, sx = sub_h.shape
            pos = np.dstack([XX[cy:y1 + 1, cx:x1 + 1], YY[cy:y1 + 1, cx:x1 + 1], sub_h]).reshape(-1, 3)
            nr = nrm[cy:y1 + 1, cx:x1 + 1].reshape(-1, 3)
            # клетки, целиком лежащие под водой, не нужны: море непрозрачное
            vis = (np.maximum.reduce([sub_h[:-1, :-1], sub_h[1:, :-1], sub_h[:-1, 1:], sub_h[1:, 1:]]) > WATER_Z + 0.02)
            vis &= ~cov_cell[cy:y1, cx:x1]
            for name, tile, col, alpha in layers:
                use = vis
                if alpha is not None:
                    a = alpha[cy:y1 + 1, cx:x1 + 1]
                    use = vis & (np.maximum.reduce([a[:-1, :-1], a[1:, :-1], a[:-1, 1:], a[1:, 1:]]) > 0.03)
                jj, ii = np.nonzero(use)
                if len(jj) == 0:
                    continue
                v00 = jj * sx + ii
                v10 = v00 + 1
                v01 = v00 + sx
                v11 = v01 + 1
                # диагональ 00-11 (как в Terrain.height)
                tris = np.stack([v00, v10, v11, v00, v11, v01], axis=1).reshape(-1).astype('<u2')
                c8 = np.clip(col[cy:y1 + 1, cx:x1 + 1].reshape(-1, 4) * 255.0 + 0.5, 0, 255).astype(np.uint8)
                uv = pos[:, :2] / tile
                n = len(pos)
                buf = np.zeros(n, dtype=[('p', '<f4', 3), ('n', '<f4', 3), ('c', 'u1', 4), ('t', '<f4', 2)])
                buf['p'] = pos
                buf['n'] = nr
                buf['c'] = c8
                buf['t'] = uv
                vd = GeomVertexData(name, fmt, Geom.UHStatic)
                vd.uncleanSetNumRows(n)
                vd.modifyArrayHandle(0).copyDataFrom(buf.tobytes())
                prim = GeomTriangles(Geom.UHStatic)
                prim.setIndexType(Geom.NTUint16)
                va = prim.modifyVertices()
                va.uncleanSetNumRows(len(tris))
                va.modifyHandle().copyDataFrom(tris.tobytes())
                prim.closePrimitive() if False else None
                geom = Geom(vd)
                geom.addPrimitive(prim)
                gn = GeomNode(name)
                gn.addGeom(geom)
                chunk.attachNewNode(gn)
                ntri += len(tris) // 3
    path = os.path.join(OUT, 'terrain.bam')
    root.writeBamFile(Filename.fromOsSpecific(path))
    return ntri, os.path.getsize(path)


def write_png(res, city, path):
    from PIL import Image, ImageDraw
    h = res['h'][::FINE, ::FINE]
    cover = res['cover'][::FINE, ::FINE]
    ny, nx = h.shape
    pal = {C_GRASS: (104, 150, 86), C_SAND: (214, 196, 140), C_ROCK: (140, 136, 130), C_FOREST: (58, 104, 60),
           C_FIELD: (176, 168, 96), C_SEA: (52, 96, 140)}
    img = np.zeros((ny, nx, 3), np.float64)
    for c, col in pal.items():
        img[cover == c] = col
    gy_, gx_ = np.gradient(h, STEP)
    shade = np.clip(1.0 + (gx_ - gy_) * 0.9, 0.55, 1.5)
    img *= shade[..., None]
    img[cover == C_SEA] *= np.clip(1.0 + (h[cover == C_SEA] - WATER_Z) * 0.08, 0.6, 1.0)[..., None]
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)[::-1]).resize((nx * 4, ny * 4), Image.NEAREST)
    d = ImageDraw.Draw(im)
    k = 4.0 / STEP

    def P(x, y):
        return ((x - X_MIN) * k, (Y_MAX - y) * k)

    def rect(x0, y0, x1, y1, col):
        a, b = P(x0, y1), P(x1, y0)
        d.rectangle([a[0], a[1], b[0], b[1]], fill=col)
    for b in city.blocks:
        rect(b.x0, b.y0, b.x1, b.y1, (150, 150, 156))
    for s in city.segs.values():
        hw = s['width'] * 0.5
        col = (40, 40, 44) if s['bridge'] is None else (200, 60, 50)
        if s['kind'] == 'h':
            rect(s['a'], s['c'] - hw, s['b'], s['c'] + hw, col)
        else:
            rect(s['c'] - hw, s['a'], s['c'] + hw, s['b'], col)
    for n in city.nodes.values():
        rect(n.x - n.hw, n.y - n.hh, n.x + n.hw, n.y + n.hh, (40, 40, 44))
    for p in city.pads:
        if p[5]:
            rect(p[0], p[1], p[2], p[3], (170, 160, 150))
    im.save(path)


def main():
    city = City(terrain=Terrain())          # раскладка без рельефа
    res = build(city)
    hq, cover, meta = write_bin(res, city)
    ntri, size = write_bam(res, hq, cover)
    land = (cover != C_SEA).mean()
    print('рельеф: %dx%d узлов, шаг %.0f м, суши %.0f %%, высота до %.1f м; геометрия %d треугольников, %d КБ' % (
        meta['nx'], meta['ny'], STEP, land * 100.0, meta['max_height'], ntri, size // 1024))
    if '--png' in sys.argv:
        write_png(res, city, sys.argv[sys.argv.index('--png') + 1])


if __name__ == '__main__':
    main()
