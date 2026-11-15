# -*- coding: utf-8 -*-
"""Построение геометрии города и статических столкновений по данным City."""
import math
import random

from panda3d.core import NodePath, TextureStage, TransparencyAttrib

from .meshbuilder import MeshBuilder, erase_vertices
from . import props as P
from .facade import Facades
from .city import (CURB, SIDEWALK, AVE_W, ST_W, CAP_LEN, BAY_W, FLOOR_H, GF_H, WATER_Z, ROAD_X_AVE, ROAD_Y_AVE)
from .collision import (F_CAR, F_PED, F_SIGHT, F_BULLET, F_BREAK, F_CAM, F_SOLID, F_WALL)

W4 = (1.0, 1.0, 1.0, 1.0)


def _c4(c, k=1.0):
    return (c[0] * k, c[1] * k, c[2] * k, 1.0)


def side_frame(x0, y0, x1, y1, side):
    """(ax, ay, dx, dy, nx, ny, length): начало стены, направление, нормаль наружу."""
    if side == 's':
        return x0, y0, 1.0, 0.0, 0.0, -1.0, x1 - x0
    if side == 'e':
        return x1, y0, 0.0, 1.0, 1.0, 0.0, y1 - y0
    if side == 'n':
        return x1, y1, -1.0, 0.0, 0.0, 1.0, x1 - x0
    return x0, y1, 0.0, -1.0, -1.0, 0.0, y1 - y0


class Breakable(object):
    __slots__ = ('kind', 'x', 'y', 'yaw', 'ranges', 'col', 'alive', 'chunk')


class CityMesh(object):

    def __init__(self, city, assets, static, parent, night_parent=None, progress=None):
        self.city = city
        self.assets = assets
        self.static = static
        self.root = parent.attachNewNode('city')
        self.night_root = (night_parent or parent).attachNewNode('city_night')
        self._mbs = {}
        self._brks = {}
        self._nights = {}
        self.breakables = []
        self._pending_break = []
        self.water = None
        self.signal_nodes = {}      # (phase_idx, axis) -> {'r': np, 'y': np, 'g': np}
        self.chunk_nodes = {}

        steps = [self._roads, self._ground, self._buildings, self._boxes, self._walls, self._props,
                 self._special, self._signals, self._finish]
        for i, fn in enumerate(steps):
            fn()
            if progress:
                progress((i + 1) / float(len(steps)))

    # ------------------------------------------------------------------
    def _mb(self, chunk):
        m = self._mbs.get(chunk)
        if m is None:
            m = self._mbs[chunk] = MeshBuilder()
        return m

    def _brk(self, chunk):
        m = self._brks.get(chunk)
        if m is None:
            m = self._brks[chunk] = MeshBuilder()
        return m

    def _night(self, chunk):
        m = self._nights.get(chunk)
        if m is None:
            m = self._nights[chunk] = MeshBuilder()
        return m

    def _road_chunk(self, x, y):
        c = self.city
        rx = int(min(3, max(0, (x - c.grid_x0) / (c.grid_x1 - c.grid_x0) * 4)))
        ry = int(min(3, max(0, (y - c.grid_y0) / (c.grid_y1 - c.grid_y0) * 4)))
        return ('road', rx, ry)

    # ------------------------------------------------------------------
    # дороги
    # ------------------------------------------------------------------
    def _road_quad(self, mb, key, cx, cy, dx, dy, half_w, t0, t1, v0, v1, flip=False, z=0.0):
        """Кусок дороги вдоль направления (dx, dy) от t0 до t1 (от точки cx, cy)."""
        rx, ry = dy, -dx            # вправо от направления
        a = (cx + dx * t0 - rx * half_w, cy + dy * t0 - ry * half_w, z)     # лево-начало
        b = (cx + dx * t0 + rx * half_w, cy + dy * t0 + ry * half_w, z)     # право-начало
        c = (cx + dx * t1 + rx * half_w, cy + dy * t1 + ry * half_w, z)
        d = (cx + dx * t1 - rx * half_w, cy + dy * t1 - ry * half_w, z)
        if not flip:
            uvs = ((0, v0), (1, v0), (1, v1), (0, v1))
        else:
            uvs = ((1, v1), (0, v1), (0, v0), (1, v0))
        mb.quad(key, a, b, c, d, uvs=uvs)

    def _roads(self):
        c = self.city
        for seg in c.segs.values():
            ave = seg['ave']
            hw = seg['width'] * 0.5
            a, b, cc = seg['a'], seg['b'], seg['c']
            L = b - a
            if seg['kind'] == 'h':
                ox, oy, dx, dy = a, cc, 1.0, 0.0
                mb = self._mb(self._road_chunk((a + b) * 0.5, cc))
            else:
                ox, oy, dx, dy = cc, a, 0.0, 1.0
                mb = self._mb(self._road_chunk(cc, (a + b) * 0.5))
            tex = 'road4' if ave else 'road2'
            cap = 'road4_cap' if ave else 'road2_cap'
            mid = L - 2 * CAP_LEN
            n = max(1, int(round(mid / 8.0)))
            # зебра у начала (текстура развёрнута) и у конца
            self._road_quad(mb, cap, ox, oy, dx, dy, hw, 0.0, CAP_LEN, 0.0, 1.0, flip=True)
            self._road_quad(mb, tex, ox, oy, dx, dy, hw, CAP_LEN, L - CAP_LEN, 0.0, float(n))
            self._road_quad(mb, cap, ox, oy, dx, dy, hw, L - CAP_LEN, L, 0.0, 1.0)
            # крышки люков
            rnd = random.Random(int(a * 3 + cc * 17) & 0xffff)
            for _ in range(rnd.randint(1, 2) if mid > 30.0 else 0):
                t = CAP_LEN + mid * rnd.uniform(0.1, 0.9)
                off = hw * rnd.choice((-0.62, -0.3, 0.3, 0.62))
                mx, my = ox + dx * t - dy * off, oy + dy * t + dx * off
                r = 0.46
                mb.quad(('manhole', 'decal'), (mx - r, my - r, 0.012), (mx + r, my - r, 0.012),
                        (mx + r, my + r, 0.012), (mx - r, my + r, 0.012), (0, 0, 1, 1), (0.9, 0.9, 0.9, 1.0))
        for n in c.nodes.values():
            mb = self._mb(self._road_chunk(n.x, n.y))
            mb.flat('asphalt', n.x - n.hw, n.y - n.hh, n.x + n.hw, n.y + n.hh, 0.0, tile=(8.0, 8.0))
            # закрыть «дыры» там, где от перекрёстка нет выезда (край города / парк)
        # заплатки под кольцевой дорогой не нужны: перекрёстки покрывают углы

    # ------------------------------------------------------------------
    # земля
    # ------------------------------------------------------------------
    def _ground(self):
        c = self.city
        sw = SIDEWALK
        curb_c = (0.62, 0.62, 0.60, 1.0)
        for b in c.blocks:
            mb = self._mb(b.id)
            x0, y0, x1, y1 = b.x0, b.y0, b.x1, b.y1
            t = (3.0, 3.0)
            mb.flat('sidewalk', x0, y0, x1, y0 + sw, CURB, tile=t)
            mb.flat('sidewalk', x0, y1 - sw, x1, y1, CURB, tile=t)
            mb.flat('sidewalk', x0, y0 + sw, x0 + sw, y1 - sw, CURB, tile=t)
            mb.flat('sidewalk', x1 - sw, y0 + sw, x1, y1 - sw, CURB, tile=t)
            # бордюр
            mb.wall('concrete', x0, y0, x1, y0, 0.0, CURB, (0, 0, (x1 - x0) / 2.0, 0.1), curb_c)
            mb.wall('concrete', x1, y0, x1, y1, 0.0, CURB, (0, 0, (y1 - y0) / 2.0, 0.1), curb_c)
            mb.wall('concrete', x1, y1, x0, y1, 0.0, CURB, (0, 0, (x1 - x0) / 2.0, 0.1), curb_c)
            mb.wall('concrete', x0, y1, x0, y0, 0.0, CURB, (0, 0, (y1 - y0) / 2.0, 0.1), curb_c)
        for (x0, y0, x1, y1, tex, tile, color, block, z, rot) in c.ground:
            mb = self._mb(block)
            col = _c4(color)
            if tex == 'sand' and abs(y0 - c.land_y0) < 0.01:
                # пляж: последние 10 м уходят под воду
                ys = y0 + 10.0
                zl = WATER_Z - 0.3
                u0, u1 = x0 / tile[0], x1 / tile[0]
                mb.quad(tex, (x0, y0, zl), (x1, y0, zl), (x1, ys, z), (x0, ys, z),
                        (u0, y0 / tile[1], u1, ys / tile[1]), col)
                # и дальше под водой
                mb.quad(tex, (x0, y0 - 30.0, zl - 1.5), (x1, y0 - 30.0, zl - 1.5), (x1, y0, zl), (x0, y0, zl),
                        (u0, (y0 - 30.0) / tile[1], u1, y0 / tile[1]), _c4(color, 0.8))
                mb.flat(tex, x0, ys, x1, y1, z, tile=tile, color=col)
                continue
            if tex == 'parking':
                # одно место = одна плитка, линия по краю
                uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]
                if rot:
                    uvs = uvs[rot:] + uvs[:rot]
                mb.quad(('parking', 'decal'), (x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z), uvs=uvs)
                continue
            if z > CURB + 0.001:
                mb.flat((tex, 'decal'), x0, y0, x1, y1, z, tile=tile, color=col)
            else:
                mb.flat(tex, x0, y0, x1, y1, z, tile=tile, color=col)
        # бордюр внешних тротуаров
        gx0, gx1, gy0, gy1 = c.grid_x0, c.grid_x1, c.grid_y0, c.grid_y1
        for k in range(4):
            xa = gx0 + (gx1 - gx0) * k / 4.0
            xb = gx0 + (gx1 - gx0) * (k + 1) / 4.0
            self._mb(c.outer_chunk((xa + xb) / 2, gy0 - 5)).wall('concrete', xb, gy0, xa, gy0, 0.0, CURB,
                                                                (0, 0, 50, 0.1), curb_c)
            self._mb(c.outer_chunk((xa + xb) / 2, gy1 + 5)).wall('concrete', xa, gy1, xb, gy1, 0.0, CURB,
                                                                (0, 0, 50, 0.1), curb_c)
            ya = gy0 + (gy1 - gy0) * k / 4.0
            yb = gy0 + (gy1 - gy0) * (k + 1) / 4.0
            self._mb(c.outer_chunk(gx0 - 5, (ya + yb) / 2)).wall('concrete', gx0, ya, gx0, yb, 0.0, CURB,
                                                                (0, 0, 50, 0.1), curb_c)
            self._mb(c.outer_chunk(gx1 + 5, (ya + yb) / 2)).wall('concrete', gx1, yb, gx1, ya, 0.0, CURB,
                                                                (0, 0, 50, 0.1), curb_c)

    # ------------------------------------------------------------------
    # здания
    # ------------------------------------------------------------------
    def _sign(self, mb, night, x0, y0, x1, y1, side, off, z, w, h, tex, lit=True, back=False, depth=0.26):
        """Вывеска-короб на стене."""
        ax, ay, dx, dy, nx, ny, L = side_frame(x0, y0, x1, y1, side)
        o = depth
        cx, cy = ax + dx * off + nx * o, ay + dy * off + ny * o
        a = (cx - dx * w * 0.5, cy - dy * w * 0.5, z - h * 0.5)
        b = (cx + dx * w * 0.5, cy + dy * w * 0.5, z - h * 0.5)
        c = (b[0], b[1], z + h * 0.5)
        d = (a[0], a[1], z + h * 0.5)
        key = (tex, 'unlit') if lit else tex
        mb.quad(key, a, b, c, d, (0, 0, 1, 1), (0.92, 0.92, 0.92, 1.0))
        if depth > 0.12 and not back:
            # боковины короба
            a0, b0 = (a[0] - nx * o, a[1] - ny * o, a[2]), (b[0] - nx * o, b[1] - ny * o, b[2])
            c0, d0 = (b0[0], b0[1], c[2]), (a0[0], a0[1], d[2])
            edge = (0.16, 0.16, 0.18, 1.0)
            mb.quad(None, a0, a, d, d0, color=edge)
            mb.quad(None, b, b0, c0, c, color=edge)
            mb.quad(None, d, c, c0, d0, color=(0.24, 0.24, 0.26, 1.0))
            mb.quad(None, a0, b0, b, a, color=(0.10, 0.10, 0.11, 1.0))
        if lit and night is not None and tex.startswith('sign_'):
            # лёгкое свечение вывески ночью
            P.pool(night, min(a[0], b[0]) - 2 + nx * 2.5, min(a[1], b[1]) - 2 + ny * 2.5,
                   max(a[0], b[0]) + 2 + nx * 2.5, max(a[1], b[1]) + 2 + ny * 2.5,
                   CURB + 0.06, color=(0.9, 0.85, 1.0, 1.0), k=0.16)
        if back:
            mb.quad(None, b, a, d, c, color=(0.2, 0.2, 0.22, 1))

    def _buildings(self):
        c = self.city
        fac = Facades(self)
        for b in c.buildings:
            mb = self._mb(b.block)
            night = self._night(b.block)
            rnd = random.Random(int(b.x0 * 7 + b.y0 * 13) & 0xffff)
            top = fac.build(b, mb, night, rnd)
            # вывески
            for s in b.signs:
                self._sign(mb, night, b.x0, b.y0, b.x1, b.y1, s['side'], s['off'], s['z'], s['w'], s['h'], s['tex'])
            # столкновения: прямоугольник участка, как и раньше
            self.static.add_box(b.x0, b.y0, b.x1, b.y1, 0.0, top + 0.1, F_WALL, ('bld', b))

    def _roof_prop(self, mb, night, rp, z, b, rnd):
        kind = rp[0]
        x, y = rp[1], rp[2]
        if kind == 'stair':
            mb.box('concrete', x - 1.6, y - 1.6, z, x + 1.6, y + 1.6, z + 2.7, (0.72, 0.72, 0.72, 1), uv_m=3.0)
        elif kind == 'ac':
            mb.box(None, x - 0.9, y - 0.7, z, x + 0.9, y + 0.7, z + 1.1, (0.62, 0.64, 0.66, 1))
            mb.box(None, x - 0.5, y - 0.5, z + 1.1, x + 0.5, y + 0.5, z + 1.2, (0.2, 0.2, 0.2, 1))
        elif kind == 'tank':
            for (dx, dy) in ((-0.8, -0.8), (0.8, -0.8), (-0.8, 0.8), (0.8, 0.8)):
                mb.box(None, x + dx - 0.08, y + dy - 0.08, z, x + dx + 0.08, y + dy + 0.08, z + 1.8,
                       (0.3, 0.25, 0.2, 1))
            mb.cylinder('wood', x, y, z + 1.8, z + 4.4, 1.3, 8, (0.75, 0.7, 0.66, 1), uv_wrap=3.0)
            mb.cylinder(None, x, y, z + 4.4, z + 5.1, 1.4, 8, (0.3, 0.26, 0.22, 1), r_top=0.05)
        elif kind == 'antenna':
            h = rp[3]
            mb.cylinder(None, x, y, z, z + h, 0.12, 4, (0.75, 0.75, 0.78, 1), cap_top=False)
            mb.box(None, x - 0.9, y - 0.05, z + h * 0.6, x + 0.9, y + 0.05, z + h * 0.6 + 0.1, (0.7, 0.7, 0.72, 1))
            mb.box(None, x - 0.05, y - 0.6, z + h * 0.8, x + 0.05, y + 0.6, z + h * 0.8 + 0.1, (0.7, 0.7, 0.72, 1))
            P.glow(night, x, y, z + h + 0.2, 3.2, (1.0, 0.15, 0.1, 1.0))
        elif kind == 'billboard':
            side, tex = rp[3], rp[4]
            w, h = 10.0, 5.0
            hz = z + 1.4 + h * 0.5
            # щит стоит у края крыши лицом наружу
            ax, ay, dx, dy, nx, ny, L = side_frame(b.x0, b.y0, b.x1, b.y1, side)
            if L < w + 1.0:
                w = max(4.0, L - 1.0)
                h = w * 0.5
                hz = z + 1.4 + h * 0.5
            cx, cy = ax + dx * L * 0.5 - nx * 0.7, ay + dy * L * 0.5 - ny * 0.7
            for k in (-0.35, 0.35):
                px, py = cx + dx * w * k, cy + dy * w * k
                mb.box(None, px - 0.12, py - 0.12, z, px + 0.12, py + 0.12, hz + h * 0.5, (0.2, 0.2, 0.22, 1))
            a = (cx - dx * w * 0.5 + nx * 0.14, cy - dy * w * 0.5 + ny * 0.14, hz - h * 0.5)
            bb = (cx + dx * w * 0.5 + nx * 0.14, cy + dy * w * 0.5 + ny * 0.14, hz - h * 0.5)
            mb.quad((tex, 'unlit'), a, bb, (bb[0], bb[1], hz + h * 0.5), (a[0], a[1], hz + h * 0.5),
                    (0, 0, 1, 1), (0.95, 0.95, 0.95, 1))
            mb.quad(None, bb, a, (a[0], a[1], hz + h * 0.5), (bb[0], bb[1], hz + h * 0.5),
                    color=(0.18, 0.18, 0.2, 1))
        elif kind == 'helipad':
            mb.cylinder(None, x, y, z, z + 0.08, 6.0, 12, (0.3, 0.3, 0.32, 1), top_color=(0.85, 0.75, 0.15, 1))
            mb.cylinder(None, x, y, z + 0.08, z + 0.1, 5.2, 12, (0.3, 0.3, 0.32, 1), top_color=(0.3, 0.3, 0.32, 1))

    # ------------------------------------------------------------------
    def _boxes(self):
        for bx in self.city.boxes:
            if bx['tex'] == 'container':
                self._container(self._mb(bx['block']), bx)
            elif bx['faces']:
                mb = self._mb(bx['block'])
                col = _c4(bx['color'])
                mb.box(bx['tex'], bx['x0'], bx['y0'], bx['z0'], bx['x1'], bx['y1'], bx['z1'], col,
                       faces=bx['faces'], uv_m=bx['uv_m'], top_key=bx.get('top_tex'),
                       top_color=_c4(bx['top_color']) if bx.get('top_color') else None)
            if bx['solid']:
                h = bx.get('stack_h')
                z1 = bx['z0'] + h if h else bx['z1']
                self.static.add_box(bx['x0'], bx['y0'], bx['x1'], bx['y1'], 0.0, z1, F_WALL, ('box', bx))
        for cy in self.city.cyls:
            mb = self._mb(cy['block'])
            mb.cylinder(cy['tex'], cy['x'], cy['y'], cy['z0'], cy['z1'], cy['r'], cy.get('n', 8), _c4(cy['color']),
                        uv_wrap=max(1.0, round(cy['r'] * 2.0)), top_color=_c4(cy['color'], 0.8))
            if cy['solid']:
                self.static.add_circle(cy['x'], cy['y'], cy['r'], cy['z1'], F_WALL, ('cyl', cy))

    def _container(self, mb, bx):
        """Морской контейнер: ребристые борта, торцы с дверями."""
        x0, y0, z0, x1, y1, z1 = bx['x0'], bx['y0'], bx['z0'], bx['x1'], bx['y1'], bx['z1']
        col = _c4(bx['color'])
        dark = _c4(bx['color'], 0.82)
        if (x1 - x0) >= (y1 - y0):
            sides = ((x0, y0, x1, y0), (x1, y1, x0, y1))
            ends = ((x1, y0, x1, y1), (x0, y1, x0, y0))
        else:
            sides = ((x1, y0, x1, y1), (x0, y1, x0, y0))
            ends = ((x0, y0, x1, y0), (x1, y1, x0, y1))
        for i, (ax, ay, bx_, by) in enumerate(sides):
            mb.quad('container_side', (ax, ay, z0), (bx_, by, z0), (bx_, by, z1), (ax, ay, z1), (0, 0, 1, 1),
                    col if i == 0 else dark)
        for i, (ax, ay, bx_, by) in enumerate(ends):
            mb.quad('container_end', (ax, ay, z0), (bx_, by, z0), (bx_, by, z1), (ax, ay, z1), (0, 0, 1, 1),
                    col if i == 0 else dark)
        mb.flat('corrugated', x0, y0, x1, y1, z1, tile=(2.6, 2.6), color=_c4(bx['color'], 0.7))

    def _walls(self):
        for w in self.city.walls:
            mb = self._mb(w['block'])
            x0, y0, x1, y1 = w['x0'], w['y0'], w['x1'], w['y1']
            h = w['h']
            z0 = w['z0']
            t = w['thick'] * 0.5
            horiz = (x1 - x0) >= (y1 - y0)
            L = (x1 - x0) if horiz else (y1 - y0)
            if L < 0.05:
                continue
            kind = w['kind']
            col = _c4(w['color'])
            if kind == 'fence':
                key = (w['tex'], 'a')
                n = L / 1.0
                if horiz:
                    mb.quad(key, (x0, y0, z0), (x1, y0, z0), (x1, y0, z0 + h), (x0, y0, z0 + h),
                            (0, 0, n, h / 1.0), col)
                else:
                    mb.quad(key, (x0, y0, z0), (x0, y1, z0), (x0, y1, z0 + h), (x0, y0, z0 + h),
                            (0, 0, n, h / 1.0), col)
                # столбы
                np_ = max(1, int(L // 3.0))
                for k in range(np_ + 1):
                    px = x0 + (x1 - x0) * k / np_
                    py = y0 + (y1 - y0) * k / np_
                    mb.box(None, px - 0.05, py - 0.05, z0, px + 0.05, py + 0.05, z0 + h + 0.1, (0.4, 0.42, 0.44, 1))
                flags = F_CAR | F_PED | F_CAM
                bx0, by0, bx1, by1 = (x0, y0 - 0.12, x1, y0 + 0.12) if horiz else (x0 - 0.12, y0, x0 + 0.12, y1)
            else:
                if horiz:
                    bx0, by0, bx1, by1 = x0, y0 - t, x1, y0 + t
                else:
                    bx0, by0, bx1, by1 = x0 - t, y0, x0 + t, y1
                uvm = 1.4 if kind == 'hedge' else 3.0
                mb.box(w['tex'], bx0, by0, z0, bx1, by1, z0 + h, col, uv_m=uvm, faces='xXyYZ')
                flags = F_SOLID | F_CAM
                if h > 1.7:
                    flags |= F_SIGHT
            self.static.add_box(bx0, by0, bx1, by1, 0.0, z0 + h, flags, ('wall', w))

    # ------------------------------------------------------------------
    def _props(self):
        c = self.city
        st = self.static
        for i, p in enumerate(c.props):
            kind = p['kind']
            fn = P.BUILDERS.get(kind)
            if fn is None:
                continue
            x, y, yaw = p['x'], p['y'], p['yaw']
            z = c.ground_z(x, y)
            chunk = p['block']
            breakable = kind in P.BREAKABLE
            mb = self._brk(chunk) if breakable else self._mb(chunk)
            night = self._night(chunk)
            rnd = random.Random(i * 7919 + 17)
            if breakable:
                m0 = mb.mark()
                n0 = night.mark()
            mb.set_xform(x, y, z, yaw)
            night.set_xform(x, y, z, yaw)
            col = fn(mb, night, p, rnd)
            mb.clear_xform()
            night.clear_xform()
            cid = None
            if col is not None:
                if col[0] == 'c':
                    cid = st.add_circle(x, y, col[1], z + col[2], col[3], ('prop', p))
                elif col[0] == 'b':
                    ca, sa = abs(math.cos(yaw)), abs(math.sin(yaw))
                    hx = col[1] * ca + col[2] * sa
                    hy = col[1] * sa + col[2] * ca
                    st.add_box(x - hx, y - hy, x + hx, y + hy, 0.0, z + col[3], col[4], ('prop', p))
                elif col[0] == 'legs':
                    ca, sa = math.cos(yaw), math.sin(yaw)
                    for (lx, ly) in col[1]:
                        st.add_circle(x + lx * ca - ly * sa, y + lx * sa + ly * ca, col[2], z + col[3], F_WALL,
                                      ('prop', p))
            if breakable:
                br = Breakable()
                br.kind = kind
                br.x, br.y, br.yaw = x, y, yaw
                br.col = cid
                br.alive = True
                br.chunk = chunk
                br.ranges = []
                self._pending_break.append((br, mb, mb.ranges_since(m0), night, night.ranges_since(n0)))
                self.breakables.append(br)
                if cid is not None:
                    st.circles[cid][5] = ('break', br)

    # ------------------------------------------------------------------
    def _special(self):
        c = self.city
        sp = c.special
        oc = c.outer_chunk
        stone = (0.5, 0.5, 0.5, 1.0)
        # вывески не на зданиях
        for s in sp.get('free_signs', []):
            mb = self._mb(s['block'])
            night = self._night(s['block'])
            w, h = s['w'], s['h']
            x, y, z = s['x'], s['y'], s['z']
            side = s['side']
            dep = 0.26 if (s['tex'].startswith('sign_') and not s.get('post')) else 0.1
            if side in ('s', 'n'):
                self._sign(mb, night, x - w / 2, y, x + w / 2, y, side, w / 2, z, w, h, s['tex'],
                           back=s.get('post', False), depth=dep)
            else:
                self._sign(mb, night, x, y - w / 2, x, y + w / 2, side, w / 2, z, w, h, s['tex'],
                           back=s.get('post', False), depth=dep)
            if s.get('post'):
                for k in (-0.4, 0.4):
                    mb.box(None, x + w * k - 0.1, y - 0.1, 0.0, x + w * k + 0.1, y + 0.1, z + h / 2,
                           (0.3, 0.3, 0.32, 1))
        # пруд
        pond = sp.get('pond')
        if pond:
            mb = self._mb(pond['block'])
            n = 14
            px, py, rx, ry = pond['x'], pond['y'], pond['rx'], pond['ry']
            for i in range(n):
                a0, a1 = i * 2 * math.pi / n, (i + 1) * 2 * math.pi / n
                p0 = (px + math.cos(a0) * rx, py + math.sin(a0) * ry)
                p1 = (px + math.cos(a1) * rx, py + math.sin(a1) * ry)
                q0 = (px + math.cos(a0) * (rx + 1.6), py + math.sin(a0) * (ry + 1.6))
                q1 = (px + math.cos(a1) * (rx + 1.6), py + math.sin(a1) * (ry + 1.6))
                mb.tri(('water', 'decal'), (px, py, CURB + 0.05), (p0[0], p0[1], CURB + 0.05),
                       (p1[0], p1[1], CURB + 0.05), (px / 9, py / 9), (p0[0] / 9, p0[1] / 9),
                       (p1[0] / 9, p1[1] / 9), (0.75, 0.95, 1.0, 1))
                mb.quad(('sand', 'decal'), (p0[0], p0[1], CURB + 0.04), (q0[0], q0[1], CURB + 0.04),
                        (q1[0], q1[1], CURB + 0.04), (p1[0], p1[1], CURB + 0.04),
                        uvs=((p0[0] / 5, p0[1] / 5), (q0[0] / 5, q0[1] / 5), (q1[0] / 5, q1[1] / 5),
                             (p1[0] / 5, p1[1] / 5)), color=(0.9, 0.9, 0.85, 1))
        # деревянный пирс на пляже
        pier = sp.get('pier')
        if pier:
            mb = self._mb(pier['chunk'])
            x0, y0, x1, y1, z = pier['x0'], pier['y0'], pier['x1'], pier['y1'], pier['z']
            mb.box('wood', x0, y0, z - 0.3, x1, y1, z, (0.9, 0.9, 0.9, 1), uv_m=3.0, faces='xXyYZz')
            yy = y0 + 2.0
            while yy < y1 - 8.0:
                for xx in (x0 + 0.5, x1 - 0.5):
                    mb.cylinder(None, xx, yy, WATER_Z - 2.0, z - 0.3, 0.22, 5, (0.32, 0.24, 0.16, 1), cap_top=False)
                yy += 8.0
            # перила (с проёмом в конце — можно нырнуть вместе с машиной)
            for xx in (x0 + 0.1, x1 - 0.1):
                mb.box(None, xx - 0.06, y0 + 6.0, z + 0.9, xx + 0.06, y1 - 4.0, z + 1.0, P.WOOD)
                yy = y0 + 6.0
                while yy < y1 - 4.0:
                    mb.box(None, xx - 0.06, yy - 0.06, z, xx + 0.06, yy + 0.06, z + 0.9, P.WOOD)
                    yy += 3.0
                self.static.add_box(xx - 0.1, y0 + 6.0, xx + 0.1, y1 - 4.0, 0.0, z + 1.0, F_CAR | F_PED, None)
            night = self._night(pier['chunk'])
            yy = y0 + 4.0
            while yy < y1 - 6:
                P.glow(night, x0 + 0.2, yy, z + 1.3, 1.6)
                P.glow(night, x1 - 0.2, yy, z + 1.3, 1.6)
                yy += 12.0
        # бетонные причалы
        for pr in sp.get('piers', []):
            mb = self._mb(pr['chunk'])
            mb.box('concrete', pr['x0'], pr['y0'], WATER_Z - 2.0, pr['x1'], pr['y1'], CURB, (0.74, 0.74, 0.74, 1),
                   uv_m=5.0, faces='XyYZ')
            # жёлтая кромка
            mb.flat((None, 'decal'), pr['x1'] - 0.5, pr['y0'], pr['x1'], pr['y1'], CURB + 0.03,
                    color=(0.85, 0.7, 0.1, 1))
        # берег: стенки
        lx0, lx1, ly0, ly1 = c.land_x0, c.land_x1, c.land_y0, c.land_y1
        zb = WATER_Z - 2.5
        seg = 4
        for k in range(seg):
            ya = ly0 + (ly1 - ly0) * k / seg
            yb = ly0 + (ly1 - ly0) * (k + 1) / seg
            self._mb(oc(lx0 + 1, (ya + yb) / 2)).wall('concrete', lx0, yb, lx0, ya, zb, CURB, (0, 0, 40, 1), stone)
            self._mb(oc(lx1 - 1, (ya + yb) / 2)).wall('concrete', lx1, ya, lx1, yb, zb, CURB, (0, 0, 40, 1), stone)
            xa = lx0 + (lx1 - lx0) * k / seg
            xb = lx0 + (lx1 - lx0) * (k + 1) / seg
            self._mb(oc((xa + xb) / 2, ly1 - 1)).wall('concrete', xb, ly1, xa, ly1, zb, CURB, (0, 0, 40, 1), stone)
        # мост
        br = sp.get('bridge')
        if br:
            mb = self._mb(br['chunk'])
            night = self._night(br['chunk'])
            bx, y0, y1, w = br['x'], br['y0'], br['y1'], br['w']
            hw = w * 0.5
            zd = CURB + 0.02
            n = int((y1 - y0) / 8.0)
            mb.quad(('road4', 'decal'), (bx - hw, y0, zd), (bx + hw, y0, zd), (bx + hw, c.land_y1, zd),
                    (bx - hw, c.land_y1, zd), (0, 0, 1, (c.land_y1 - y0) / 8.0))
            mb.quad('road4', (bx - hw, c.land_y1, zd), (bx + hw, c.land_y1, zd), (bx + hw, y1, zd),
                    (bx - hw, y1, zd), (0, 0, 1, n))
            steel = (0.55, 0.2, 0.16, 1.0)
            for sx in (-1, 1):
                ex = bx + sx * (hw + 0.75)
                mb.box('concrete', ex - 0.75, c.land_y1, zd - 1.2, ex + 0.75, y1, zd + 0.2, (0.6, 0.6, 0.6, 1),
                       uv_m=4.0, faces='xXyYZz')
                mb.box(None, ex + sx * 0.5 - 0.08, c.land_y1, zd + 1.1, ex + sx * 0.5 + 0.08, y1, zd + 1.25, steel)
                self.static.add_box(ex - 0.2 + sx * 0.5, c.land_y1, ex + 0.2 + sx * 0.5, y1, 0.0, 1.4,
                                    F_CAR | F_PED, None)
            mb.box('concrete', bx - hw, c.land_y1, zd - 1.2, bx + hw, y1, zd - 0.01, (0.5, 0.5, 0.5, 1), uv_m=4.0,
                   faces='z')
            # пилоны и тросы
            span = y1 - c.land_y1
            towers = [c.land_y1 + span * 0.2, c.land_y1 + span * 0.75]
            TH = 58.0
            for ty in towers:
                for sx in (-1, 1):
                    ex = bx + sx * (hw + 1.2)
                    mb.box(None, ex - 1.1, ty - 1.4, WATER_Z - 2, ex + 1.1, ty + 1.4, TH, steel)
                    P.glow(night, ex, ty, TH + 1.0, 4.0, (1.0, 0.15, 0.1, 1.0))
                mb.box(None, bx - hw - 2.0, ty - 1.0, TH - 6.0, bx + hw + 2.0, ty + 1.0, TH - 3.0, steel)
                mb.box(None, bx - hw - 2.0, ty - 1.0, TH * 0.55, bx + hw + 2.0, ty + 1.0, TH * 0.55 + 2.0, steel)
            cable = (0.5, 0.18, 0.14, 1.0)
            pts = [(c.land_y1 - 6.0, zd + 1.0), (towers[0], TH), (towers[1], TH), (y1, zd + 14.0)]
            for sx in (-1, 1):
                ex = bx + sx * (hw + 1.2)
                for k in range(3):
                    (ya, za), (yb, zb_) = pts[k], pts[k + 1]
                    segs = 10
                    prev = None
                    for i in range(segs + 1):
                        t = i / float(segs)
                        yy = ya + (yb - ya) * t
                        sag = (4.0 * t * (1.0 - t)) * (0.62 if k == 1 else 0.25) * min(za, zb_)
                        zz = za + (zb_ - za) * t - sag
                        zz = max(zz, zd + 3.0) if k == 1 else zz
                        if prev is not None:
                            mb.quad2(None, (ex, prev[0], prev[1] - 0.25), (ex, yy, zz - 0.25), (ex, yy, zz + 0.25),
                                     (ex, prev[0], prev[1] + 0.25), color=cable)
                            if i < segs and zz > zd + 2.0:
                                mb.quad2(None, (ex, yy - 0.06, zd + 1.2), (ex, yy + 0.06, zd + 1.2),
                                         (ex, yy + 0.06, zz), (ex, yy - 0.06, zz), color=cable)
                        prev = (yy, zz)
            # фонари на мосту
            yy = c.land_y1 + 20.0
            while yy < y1 - 10:
                for sx in (-1, 1):
                    P.glow(night, bx + sx * (hw + 0.6), yy, zd + 5.0, 2.4)
                yy += 30.0
        # корабль
        ship = sp.get('ship')
        if ship:
            mb = self._mb(ship['chunk'])
            x0, y0, x1, y1 = ship['x0'], ship['y0'], ship['x1'], ship['y1']
            mb.box(None, x0, y0, WATER_Z - 2.0, x1, y1, 1.2, (0.42, 0.12, 0.10, 1))
            mb.box(None, x0, y0, 1.2, x1, y1, 5.0, (0.10, 0.11, 0.14, 1), top_color=(0.36, 0.2, 0.16, 1))
            # нос
            cy = (y0 + y1) * 0.5
            mb.tri(None, (x1, y0, 5.0), (x1 + 12.0, cy, 5.0), (x1, y1, 5.0), color=(0.36, 0.2, 0.16, 1))
            mb.quad(None, (x1, y0, WATER_Z - 2), (x1 + 12.0, cy, WATER_Z - 2), (x1 + 12.0, cy, 5.0), (x1, y0, 5.0),
                    color=(0.10, 0.11, 0.14, 1))
            mb.quad(None, (x1 + 12.0, cy, WATER_Z - 2), (x1, y1, WATER_Z - 2), (x1, y1, 5.0), (x1 + 12.0, cy, 5.0),
                    color=(0.09, 0.10, 0.12, 1))
            # надстройка
            mb.box('fac_conc_a', x0 + 3.0, y0 + 2.0, 5.0, x0 + 14.0, y1 - 2.0, 14.6, (1, 1, 1, 1), uv_m=3.5,
                   top_key='roof_gravel')
            mb.cylinder(None, x0 + 8.0, cy, 14.6, 19.0, 1.6, 8, (0.8, 0.2, 0.15, 1), top_color=(0.05, 0.05, 0.05, 1))
            rnd = random.Random(5)
            for ix in range(7):
                for iy in range(4):
                    if rnd.random() < 0.2:
                        continue
                    for s in range(rnd.randint(1, 3)):
                        cx0 = x0 + 18.0 + ix * 6.6
                        cy0 = y0 + 2.4 + iy * 2.8
                        mb.box('corrugated', cx0, cy0, 5.0 + s * 2.6, cx0 + 6.1, cy0 + 2.44, 7.6 + s * 2.6,
                               _c4(rnd.choice(c.CONTAINER_COLORS)), uv_m=2.6)
            night = self._night(ship['chunk'])
            P.glow(night, x0 + 8.0, cy, 20.0, 3.0, (1.0, 0.2, 0.15, 1.0))
            P.glow(night, x1 + 11.0, cy, 6.0, 2.4, (0.3, 1.0, 0.4, 1.0))
            for k in range(4):
                P.glow(night, x0 + 14.2, y0 + 3.5 + k * 3.0, 11.0, 2.0, (1.0, 0.9, 0.6, 0.9))

    # ------------------------------------------------------------------
    def _signals(self):
        """Светофоры: столбы — в чанках, огни — в 20 общих группах (фаза x ось)."""
        c = self.city
        self._sig_mbs = {}
        for s in c.signals:
            n = c.nodes[s['node']]
            mb = self._mb(s['block'])
            x, y, yaw = s['x'], s['y'], s['yaw']
            z = c.ground_z(x, y)
            # yaw — направление движения машин; сигнал смотрит им навстречу
            mb.set_xform(x, y, z, yaw)
            mb.cylinder(None, 0, 0, 0, 5.2, 0.09, 5, P.METAL, cap_top=False)
            # консоль над дорогой: влево от направления движения (+Y локально)
            arm = n.hw if s['dir'] in ('n', 's') else n.hh
            arm = min(arm, 5.5)
            mb.box(None, -0.06, 0.0, 5.1, 0.06, arm, 5.22, P.METAL)
            heads = [(0.0, 0.0, 2.6), (0.0, arm - 0.3, 4.15)]
            for (hx, hy, hz) in heads:
                mb.box(None, hx - 0.14, hy - 0.17, hz, hx + 0.14, hy + 0.17, hz + 1.0, (0.08, 0.08, 0.08, 1))
            mb.clear_xform()
            st = self.static
            st.add_circle(x, y, 0.14, z + 5.2, F_SOLID, None)
            phase_idx = int(round(n.phase / 3.1)) % 10
            axis = 0 if s['dir'] in ('n', 's') else 1
            key = (phase_idx, axis)
            grp = self._sig_mbs.get(key)
            if grp is None:
                grp = self._sig_mbs[key] = {'r': MeshBuilder(), 'y': MeshBuilder(), 'g': MeshBuilder()}
            cols = {'r': (1.0, 0.12, 0.08, 1), 'y': (1.0, 0.75, 0.05, 1), 'g': (0.1, 1.0, 0.35, 1)}
            for (hx, hy, hz) in heads:
                for k, lamp in enumerate(('g', 'y', 'r')):
                    m = grp[lamp]
                    m.set_xform(x, y, z, yaw)
                    lz = hz + 0.17 + k * 0.33
                    # лицом назад (-X локально), навстречу машинам
                    m.quad(None, (hx - 0.15, hy + 0.12, lz - 0.12), (hx - 0.15, hy - 0.12, lz - 0.12),
                           (hx - 0.15, hy - 0.12, lz + 0.12), (hx - 0.15, hy + 0.12, lz + 0.12), color=cols[lamp])
                    m.quad(P.GLOW, (hx - 0.17, hy + 0.5, lz - 0.5), (hx - 0.17, hy - 0.5, lz - 0.5),
                           (hx - 0.17, hy - 0.5, lz + 0.5), (hx - 0.17, hy + 0.5, lz + 0.5),
                           color=(cols[lamp][0], cols[lamp][1], cols[lamp][2], 0.75))
                    m.clear_xform()

    # ------------------------------------------------------------------
    def _finish(self):
        apply_state = self.assets.apply_state
        for chunk, mb in self._mbs.items():
            if mb.empty():
                continue
            np_ = mb.build('chunk-%s' % str(chunk), apply_state)
            np_.reparentTo(self.root)
            self.chunk_nodes[chunk] = np_
        for chunk, mb in self._brks.items():
            if mb.empty():
                continue
            np_ = mb.build('brk-%s' % str(chunk), apply_state)
            np_.reparentTo(self.root)
        for chunk, mb in self._nights.items():
            if mb.empty():
                continue
            np_ = mb.build('night-%s' % str(chunk), apply_state)
            np_.reparentTo(self.night_root)
        for (br, mb, r1, night, r2) in self._pending_break:
            for (key, start, count) in r1:
                gn = mb.built.get(key)
                if gn is not None:
                    br.ranges.append((gn, start, count))
            for (key, start, count) in r2:
                gn = night.built.get(key)
                if gn is not None:
                    br.ranges.append((gn, start, count))
        self._pending_break = []
        # светофоры
        sig_root = self.root.attachNewNode('signals')
        sig_root.setLightOff(1)
        for key, grp in self._sig_mbs.items():
            d = {}
            for lamp, mb in grp.items():
                np_ = mb.build('sig-%d-%d-%s' % (key[0], key[1], lamp), apply_state)
                np_.reparentTo(sig_root)
                np_.hide()
                d[lamp] = np_
            self.signal_nodes[key] = d
        self._sig_state = {}
        # вода
        c = self.city
        mb = MeshBuilder()
        S = 2600.0
        mb.flat('water', -S, -S, S, S, WATER_Z, tile=(14.0, 14.0), color=(0.85, 0.95, 1.0, 1.0))
        self.water = mb.build('water', apply_state)
        self.water.reparentTo(self.root)
        self.water.setBin('background', 10)
        self.water_ts = TextureStage.getDefault()
        self._mbs = self._brks = self._nights = None
        self._sig_mbs = None

    # ------------------------------------------------------------------
    def update_signals(self, roadnet_time, light_fn):
        """Переключить огни светофоров.  light_fn(phase_idx, axis) -> 'r'|'y'|'g'."""
        for key, d in self.signal_nodes.items():
            s = light_fn(key[0], key[1])
            if self._sig_state.get(key) != s:
                self._sig_state[key] = s
                for lamp, np_ in d.items():
                    if lamp == s:
                        np_.show()
                    else:
                        np_.hide()

    def scroll_water(self, t):
        if self.water is not None:
            self.water.setTexOffset(self.water_ts, t * 0.012, t * 0.02)

    def break_prop(self, br):
        """Сломать объект: убрать модель и столкновение."""
        if not br.alive:
            return False
        br.alive = False
        for (gn, start, count) in br.ranges:
            erase_vertices(gn, start, count)
        if br.col is not None:
            self.static.remove_circle(br.col)
        return True
