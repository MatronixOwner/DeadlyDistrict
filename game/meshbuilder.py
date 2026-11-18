# -*- coding: utf-8 -*-
"""Быстрый сборщик статической геометрии.

Вся графика мира (дома, дороги, машины, люди) строится из кода.
MeshBuilder копит треугольники, сгруппированные по ключу (обычно это имя
текстуры), и одним вызовом превращает их в узлы Panda3D.

Формат вершины: позиция(3f) + нормаль(3f) + цвет(4 байта RGBA) + UV(2f).
Затенение — плоское (нормаль на грань), как на PS1/PS2.
"""
import math
import struct

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData,
                          GeomVertexFormat, GeomVertexWriter, NodePath)

_VSTRUCT = '3f3f4B2f'
_VSIZE = struct.calcsize('<' + _VSTRUCT)        # 36

_format_ok = None


def _check_format():
    """Убедиться, что раскладка V3n3c4t2 совпадает с нашей упаковкой."""
    global _format_ok
    if _format_ok is None:
        fmt = GeomVertexFormat.getV3n3c4t2()
        arr = fmt.getArray(0)
        ok = (fmt.getNumArrays() == 1 and arr.getStride() == _VSIZE and arr.getNumColumns() == 4)
        if ok:
            starts = [arr.getColumn(i).getStart() for i in range(4)]
            ok = (starts == [0, 12, 24, 28])
        _format_ok = ok
    return _format_ok


def _c8(c):
    r = int(c[0] * 255.0 + 0.5)
    g = int(c[1] * 255.0 + 0.5)
    b = int(c[2] * 255.0 + 0.5)
    a = int(c[3] * 255.0 + 0.5) if len(c) > 3 else 255
    return (0 if r < 0 else 255 if r > 255 else r,
            0 if g < 0 else 255 if g > 255 else g,
            0 if b < 0 else 255 if b > 255 else b,
            0 if a < 0 else 255 if a > 255 else a)


WHITE = (1.0, 1.0, 1.0, 1.0)


class MeshBuilder(object):
    CELL = 5.0               # при изгибе длинные грани режутся по общей решётке с таким шагом, м

    def __init__(self, warp=None):
        """warp — изгиб города (game/warp.py): координаты задаются по чертежу, в сетку попадают
        уже изогнутыми.  Мелкие грани просто сдвигаются по вершинам, длинные (дорога, крыша, газон)
        сначала режутся на куски не длиннее CELL: иначе прямая грань не ляжет на кривую улицу.
        Режутся они по общей решётке, поэтому у соседних граней швы приходятся на одни и те же точки.
        То, что ставится через set_xform (фонарь, дерево, скамейка), не гнётся, а ставится целиком:
        в изогнутую точку и с поворотом, какой там у чертежа."""
        self.groups = {}
        self._xf = None          # (x, y, z, cos, sin, scale)
        self.built = {}          # key -> GeomNode (после build)
        self.warp = warp
        self._rots = {}

    def mark(self):
        """Запомнить текущее число вершин в каждой группе."""
        return dict((k, len(v) // 12) for k, v in self.groups.items())

    def ranges_since(self, mark):
        """Диапазоны вершин, добавленных после mark(): [(key, start, count)]."""
        out = []
        for k, v in self.groups.items():
            n0 = mark.get(k, 0)
            n1 = len(v) // 12
            if n1 > n0:
                out.append((k, n0, n1 - n0))
        return out

    # ------------------------------------------------------------------
    def set_xform(self, x=0.0, y=0.0, z=0.0, yaw=0.0, scale=1.0):
        """Все последующие примитивы будут повёрнуты/сдвинуты."""
        if x == 0.0 and y == 0.0 and z == 0.0 and yaw == 0.0 and scale == 1.0:
            self._xf = None
        else:
            wp = self.warp
            if wp is not None:
                yaw += wp.rot(x, y)
                x, y = wp.fwd(x, y)
            self._xf = (x, y, z, math.cos(yaw), math.sin(yaw), scale)

    def clear_xform(self):
        self._xf = None

    def empty(self):
        return not any(self.groups.values())

    def vertex_count(self):
        return sum(len(v) for v in self.groups.values()) // 12

    # ------------------------------------------------------------------
    def tri(self, key, p0, p1, p2, uv0=(0.0, 0.0), uv1=(1.0, 0.0), uv2=(1.0, 1.0),
            color=WHITE, normals=None, c1=None, c2=None):
        xf = self._xf
        if xf is not None:
            tx, ty, tz, c, s, sc = xf
            p0 = (tx + (p0[0] * c - p0[1] * s) * sc, ty + (p0[0] * s + p0[1] * c) * sc, tz + p0[2] * sc)
            p1 = (tx + (p1[0] * c - p1[1] * s) * sc, ty + (p1[0] * s + p1[1] * c) * sc, tz + p1[2] * sc)
            p2 = (tx + (p2[0] * c - p2[1] * s) * sc, ty + (p2[0] * s + p2[1] * c) * sc, tz + p2[2] * sc)
        elif self.warp is not None:
            wp = self.warp
            ax, ay = p0[0], p0[1]
            bx, by = p1[0], p1[1]
            cx, cy = p2[0], p2[1]
            L = self.CELL
            if ((ax if ax > bx else bx) if (ax if ax > bx else bx) > cx else cx) - \
                    ((ax if ax < bx else bx) if (ax if ax < bx else bx) < cx else cx) > L or \
                    ((ay if ay > by else by) if (ay if ay > by else by) > cy else cy) - \
                    ((ay if ay < by else by) if (ay if ay < by else by) < cy else cy) > L:
                self._split_tri(key, p0, p1, p2, uv0, uv1, uv2, color, normals, c1, c2)
                return
            f = wp.fwd_memo
            if normals is not None:
                normals = (self._rot_n(normals[0], ax, ay), self._rot_n(normals[1], bx, by),
                           self._rot_n(normals[2], cx, cy))
            q = f(ax, ay)
            p0 = (q[0], q[1], p0[2])
            q = f(bx, by)
            p1 = (q[0], q[1], p1[2])
            q = f(cx, cy)
            p2 = (q[0], q[1], p2[2])
        if normals is None:
            ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            ln = math.sqrt(nx * nx + ny * ny + nz * nz)
            if ln < 1e-12:
                return
            nx, ny, nz = nx / ln, ny / ln, nz / ln
            n0 = n1 = n2 = (nx, ny, nz)
        else:
            n0, n1, n2 = normals
            if xf is not None:
                c, s = xf[3], xf[4]
                n0 = (n0[0] * c - n0[1] * s, n0[0] * s + n0[1] * c, n0[2])
                n1 = (n1[0] * c - n1[1] * s, n1[0] * s + n1[1] * c, n1[2])
                n2 = (n2[0] * c - n2[1] * s, n2[0] * s + n2[1] * c, n2[2])
        col0 = _c8(color)
        col1 = col0 if c1 is None else _c8(c1)
        col2 = col0 if c2 is None else _c8(c2)
        g = self.groups.get(key)
        if g is None:
            g = self.groups[key] = []
        g.extend((p0[0], p0[1], p0[2], n0[0], n0[1], n0[2], col0[0], col0[1], col0[2], col0[3], uv0[0], uv0[1],
                  p1[0], p1[1], p1[2], n1[0], n1[1], n1[2], col1[0], col1[1], col1[2], col1[3], uv1[0], uv1[1],
                  p2[0], p2[1], p2[2], n2[0], n2[1], n2[2], col2[0], col2[1], col2[2], col2[3], uv2[0], uv2[1]))

    # ------------------------------------------------------------------
    # изгиб: поворот нормалей и разрезание длинных граней
    # ------------------------------------------------------------------
    def _rot_n(self, n, x, y):
        """Нормаль, повёрнутая так же, как повёрнут чертёж в этой точке (поворот берётся по клетке 8 м)."""
        key = (x // 8.0, y // 8.0)
        r = self._rots.get(key)
        if r is None:
            a = self.warp.rot(key[0] * 8.0 + 4.0, key[1] * 8.0 + 4.0)
            r = self._rots[key] = (math.cos(a), math.sin(a))
        return (n[0] * r[0] - n[1] * r[1], n[0] * r[1] + n[1] * r[0], n[2])

    @staticmethod
    def _cut(a, b, axis, c):
        """Точка ребра a-b на линии решётки (координата axis равна c).  Считается всегда от конца
        с меньшей координатой: у двух граней с общим ребром точка выходит одна и та же, бит в бит."""
        if a[axis] > b[axis]:
            a, b = b, a
        t = (c - a[axis]) / (b[axis] - a[axis])
        v = [a[i] + (b[i] - a[i]) * t for i in range(len(a))]
        v[axis] = c
        return tuple(v)

    def _split_tri(self, key, p0, p1, p2, uv0, uv1, uv2, color, normals, c1, c2):
        """Разрезать длинную грань по решётке и отдать куски обратно в tri()."""
        col0 = tuple(color) if len(color) > 3 else (color[0], color[1], color[2], 1.0)
        col1 = col0 if c1 is None else (tuple(c1) if len(c1) > 3 else (c1[0], c1[1], c1[2], 1.0))
        col2 = col0 if c2 is None else (tuple(c2) if len(c2) > 3 else (c2[0], c2[1], c2[2], 1.0))
        if normals is None:
            v0 = (p0[0], p0[1], p0[2], uv0[0], uv0[1]) + col0
            v1 = (p1[0], p1[1], p1[2], uv1[0], uv1[1]) + col1
            v2 = (p2[0], p2[1], p2[2], uv2[0], uv2[1]) + col2
        else:
            v0 = (p0[0], p0[1], p0[2], uv0[0], uv0[1]) + col0 + tuple(normals[0])
            v1 = (p1[0], p1[1], p1[2], uv1[0], uv1[1]) + col1 + tuple(normals[1])
            v2 = (p2[0], p2[1], p2[2], uv2[0], uv2[1]) + col2 + tuple(normals[2])
        L = self.CELL
        todo = [(v0, v1, v2)]
        done = []
        cut = self._cut
        while todo:
            t = todo.pop()
            for axis in (0, 1):
                a, b, c = t[0][axis], t[1][axis], t[2][axis]
                lo = min(a, b, c)
                hi = max(a, b, c)
                if hi - lo <= L:
                    continue
                line = round((lo + hi) * 0.5 / L) * L          # линия решётки поближе к середине
                if not lo < line < hi:
                    line = (math.floor(lo / L) + 1.0) * L
                    if not lo < line < hi:
                        continue
                side = [(-1 if v[axis] < line else (1 if v[axis] > line else 0)) for v in t]
                on = side.count(0)
                if on == 1:
                    # линия проходит через вершину: два куска
                    i = side.index(0)
                    A, B, C = t[i], t[(i + 1) % 3], t[(i + 2) % 3]
                    P = cut(B, C, axis, line)
                    todo.append((A, B, P))
                    todo.append((A, P, C))
                else:
                    # одна вершина по одну сторону, две по другую: треугольник и четырёхугольник
                    i = 0 if side[0] != side[1] and side[0] != side[2] else (1 if side[1] != side[0] else 2)
                    A, B, C = t[i], t[(i + 1) % 3], t[(i + 2) % 3]
                    P = cut(A, B, axis, line)
                    Q = cut(A, C, axis, line)
                    todo.append((A, P, Q))
                    todo.append((P, B, C))
                    todo.append((P, C, Q))
                break
            else:
                done.append(t)
        tri = self.tri
        hold = self.CELL
        self.CELL = 1e9                    # куски уже нужной длины: второй раз не резать
        try:
            for (a, b, c) in done:
                if normals is None:
                    ns = None
                else:
                    ns = []
                    for v in (a, b, c):
                        ln = math.sqrt(v[9] * v[9] + v[10] * v[10] + v[11] * v[11]) or 1.0
                        ns.append((v[9] / ln, v[10] / ln, v[11] / ln))
                tri(key, a, b, c, (a[3], a[4]), (b[3], b[4]), (c[3], c[4]), a[5:9], ns, b[5:9], c[5:9])
        finally:
            self.CELL = hold

    def quad(self, key, p0, p1, p2, p3, uv=(0.0, 0.0, 1.0, 1.0), color=WHITE, uvs=None, colors=None):
        """Четырёхугольник p0..p3 против часовой стрелки (если смотреть с лицевой стороны).

        uv = (u0, v0, u1, v1): p0=(u0,v0) p1=(u1,v0) p2=(u1,v1) p3=(u0,v1),
        либо uvs = четыре явные пары.
        """
        if uvs is None:
            u0, v0, u1, v1 = uv
            uvs = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
        if colors is None:
            self.tri(key, p0, p1, p2, uvs[0], uvs[1], uvs[2], color)
            self.tri(key, p0, p2, p3, uvs[0], uvs[2], uvs[3], color)
        else:
            self.tri(key, p0, p1, p2, uvs[0], uvs[1], uvs[2], colors[0], None, colors[1], colors[2])
            self.tri(key, p0, p2, p3, uvs[0], uvs[2], uvs[3], colors[0], None, colors[2], colors[3])

    def quad2(self, key, p0, p1, p2, p3, uv=(0.0, 0.0, 1.0, 1.0), color=WHITE):
        """Двусторонний четырёхугольник."""
        self.quad(key, p0, p1, p2, p3, uv, color)
        u0, v0, u1, v1 = uv
        self.quad(key, p1, p0, p3, p2, (u1, v0, u0, v1), color)

    # ------------------------------------------------------------------
    def wall(self, key, ax, ay, bx, by, z0, z1, uv=(0.0, 0.0, 1.0, 1.0), color=WHITE):
        """Вертикальная стена от A к B, лицом вправо от направления A->B."""
        self.quad(key, (ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1), uv, color)

    def flat(self, key, x0, y0, x1, y1, z, uv=None, color=WHITE, tile=None, rot=0):
        """Горизонтальный прямоугольник лицом вверх.

        tile=(w,h): UV повторяются каждые w x h метров (в мировых координатах).
        rot: поворот UV на rot*90 градусов.
        """
        if tile is not None:
            uv = (x0 / tile[0], y0 / tile[1], x1 / tile[0], y1 / tile[1])
        elif uv is None:
            uv = (0.0, 0.0, 1.0, 1.0)
        u0, v0, u1, v1 = uv
        uvs = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        if rot:
            rot %= 4
            uvs = uvs[rot:] + uvs[:rot]
        self.quad(key, (x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z), uvs=uvs, color=color)

    def box(self, key, x0, y0, z0, x1, y1, z1, color=WHITE, faces='xXyYzZ', uv_m=None,
            top_key=None, top_color=None, shade=True):
        """Параллелепипед по осям.  faces: x/X = -X/+X, y/Y = -Y/+Y, z/Z = низ/верх.

        uv_m: размер одного повтора текстуры в метрах (None = растянуть 0..1).
        shade: слегка затемнить боковые грани (дёшево добавляет объём).
        """
        if top_key is None:
            top_key = key
        if top_color is None:
            top_color = color
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
        if uv_m:
            ux, uy, uz = dx / uv_m, dy / uv_m, dz / uv_m
        else:
            ux = uy = uz = 1.0
        if shade:
            cx = (color[0] * 0.90, color[1] * 0.90, color[2] * 0.90, color[3] if len(color) > 3 else 1.0)
            cy = (color[0] * 0.80, color[1] * 0.80, color[2] * 0.80, color[3] if len(color) > 3 else 1.0)
        else:
            cx = cy = color
        if 'X' in faces:
            self.quad(key, (x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1), (0, 0, uy, uz), cx)
        if 'x' in faces:
            self.quad(key, (x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (0, 0, uy, uz), cx)
        if 'Y' in faces:
            self.quad(key, (x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (0, 0, ux, uz), cy)
        if 'y' in faces:
            self.quad(key, (x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), (0, 0, ux, uz), cy)
        if 'Z' in faces:
            self.quad(top_key, (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), (0, 0, ux, uy), top_color)
        if 'z' in faces:
            self.quad(key, (x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0), (0, 0, ux, uy), cy)

    def cbox(self, key, cx, cy, cz, sx, sy, sz, color=WHITE, faces='xXyYzZ', **kw):
        """Параллелепипед по центру и размерам."""
        self.box(key, cx - sx * 0.5, cy - sy * 0.5, cz - sz * 0.5,
                 cx + sx * 0.5, cy + sy * 0.5, cz + sz * 0.5, color, faces, **kw)

    def cylinder(self, key, cx, cy, z0, z1, r, n=8, color=WHITE, r_top=None, cap_top=True,
                 cap_bottom=False, smooth=True, top_color=None, uv_wrap=1.0, phase=0.0):
        """Вертикальный цилиндр / усечённый конус."""
        if r_top is None:
            r_top = r
        if top_color is None:
            top_color = color
        pts = []
        for i in range(n + 1):
            a = phase + i * (2.0 * math.pi / n)
            pts.append((math.cos(a), math.sin(a)))
        for i in range(n):
            c0, s0 = pts[i]
            c1, s1 = pts[i + 1]
            p0 = (cx + c0 * r, cy + s0 * r, z0)
            p1 = (cx + c1 * r, cy + s1 * r, z0)
            p2 = (cx + c1 * r_top, cy + s1 * r_top, z1)
            p3 = (cx + c0 * r_top, cy + s0 * r_top, z1)
            u0 = i / float(n) * uv_wrap
            u1 = (i + 1) / float(n) * uv_wrap
            if smooth:
                n0 = (c0, s0, 0.0)
                n1 = (c1, s1, 0.0)
                self.tri(key, p0, p1, p2, (u0, 0), (u1, 0), (u1, 1), color, (n0, n1, n1))
                self.tri(key, p0, p2, p3, (u0, 0), (u1, 1), (u0, 1), color, (n0, n1, n0))
            else:
                self.quad(key, p0, p1, p2, p3, (u0, 0, u1, 1), color)
            if cap_top and r_top > 1e-6:
                self.tri(key, (cx, cy, z1), p3, p2, (0.5, 0.5), (0.5 + c0 * 0.5, 0.5 + s0 * 0.5),
                         (0.5 + c1 * 0.5, 0.5 + s1 * 0.5), top_color)
            if cap_bottom:
                self.tri(key, (cx, cy, z0), p1, p0, (0.5, 0.5), (0.5 + c1 * 0.5, 0.5 + s1 * 0.5),
                         (0.5 + c0 * 0.5, 0.5 + s0 * 0.5), color)

    def cylinder_x(self, key, x0, x1, cy, cz, r, n=8, color=WHITE, cap_color=None, cap0=True, cap1=True,
                   phase=0.0):
        """Цилиндр с осью вдоль X (колёса: машина смотрит в +Y, ось колеса — X)."""
        if cap_color is None:
            cap_color = color
        pts = []
        for i in range(n + 1):
            a = phase + i * (2.0 * math.pi / n)
            pts.append((math.cos(a), math.sin(a)))
        for i in range(n):
            c0, s0 = pts[i]
            c1, s1 = pts[i + 1]
            a0 = (x0, cy + c0 * r, cz + s0 * r)
            a1 = (x0, cy + c1 * r, cz + s1 * r)
            b0 = (x1, cy + c0 * r, cz + s0 * r)
            b1 = (x1, cy + c1 * r, cz + s1 * r)
            self.quad(key, a0, a1, b1, b0, (0, 0, 1, 1), color)
            if cap1:
                self.tri(key, (x1, cy, cz), b0, b1, (0.5, 0.5), (0.5 + c0 * 0.5, 0.5 + s0 * 0.5),
                         (0.5 + c1 * 0.5, 0.5 + s1 * 0.5), cap_color)
            if cap0:
                self.tri(key, (x0, cy, cz), a1, a0, (0.5, 0.5), (0.5 + c1 * 0.5, 0.5 + s1 * 0.5),
                         (0.5 + c0 * 0.5, 0.5 + s0 * 0.5), cap_color)

    def blob(self, key, cx, cy, cz, rx, ry, rz, color=WHITE, seed=0, jitter=0.18):
        """Низкополигональный «шарик» (крона дерева, куст, камень)."""
        import random
        rnd = random.Random(seed)
        rings = ((-0.9, 0.45), (-0.25, 0.98), (0.45, 0.82))
        n = 6
        layers = []
        for (h, k) in rings:
            ring = []
            off = rnd.random() * 6.28
            for i in range(n):
                a = off + i * (2.0 * math.pi / n)
                j = 1.0 + (rnd.random() - 0.5) * 2.0 * jitter
                ring.append((cx + math.cos(a) * rx * k * j, cy + math.sin(a) * ry * k * j, cz + h * rz))
            layers.append(ring)
        top = (cx, cy, cz + rz)
        bot = (cx, cy, cz - rz)
        dark = (color[0] * 0.62, color[1] * 0.62, color[2] * 0.62, 1.0)
        mid = (color[0] * 0.82, color[1] * 0.82, color[2] * 0.82, 1.0)
        for i in range(n):
            j = (i + 1) % n
            self.tri(key, bot, layers[0][j], layers[0][i], color=dark)
            self.quad(key, layers[0][i], layers[0][j], layers[1][j], layers[1][i], color=mid)
            self.quad(key, layers[1][i], layers[1][j], layers[2][j], layers[2][i], color=color)
            self.tri(key, top, layers[2][i], layers[2][j], color=color)

    # ------------------------------------------------------------------
    def build(self, name='mesh', state_fn=None, dynamic=False):
        """Собрать NodePath.  state_fn(node_path, key) настраивает текстуру и т.п."""
        root = NodePath(name)
        usage = Geom.UHDynamic if dynamic else Geom.UHStatic
        fmt = GeomVertexFormat.getV3n3c4t2()
        fast = _check_format()
        for key in sorted(self.groups.keys(), key=lambda k: str(k)):
            vals = self.groups[key]
            n = len(vals) // 12
            if n == 0:
                continue
            vdata = GeomVertexData(str(key), fmt, usage)
            if fast:
                vdata.uncleanSetNumRows(n)
                data = struct.pack('<' + _VSTRUCT * n, *vals)
                vdata.modifyArrayHandle(0).copyDataFrom(data)
            else:                                   # запасной медленный путь
                vdata.setNumRows(n)
                wv = GeomVertexWriter(vdata, 'vertex')
                wn = GeomVertexWriter(vdata, 'normal')
                wc = GeomVertexWriter(vdata, 'color')
                wt = GeomVertexWriter(vdata, 'texcoord')
                for i in range(n):
                    o = i * 12
                    wv.addData3(vals[o], vals[o + 1], vals[o + 2])
                    wn.addData3(vals[o + 3], vals[o + 4], vals[o + 5])
                    wc.addData4(vals[o + 6] / 255.0, vals[o + 7] / 255.0, vals[o + 8] / 255.0, vals[o + 9] / 255.0)
                    wt.addData2(vals[o + 10], vals[o + 11])
            prim = GeomTriangles(usage)
            prim.addNextVertices(n)
            prim.closePrimitive()
            geom = Geom(vdata)
            geom.addPrimitive(prim)
            gn = GeomNode(str(key))
            gn.addGeom(geom)
            np_ = root.attachNewNode(gn)
            self.built[key] = gn
            if state_fn is not None:
                state_fn(np_, key)
        return root


def erase_vertices(geom_node, start, count):
    """Схлопнуть диапазон вершин в точку (так «удаляются» сломанные объекты)."""
    try:
        geom = geom_node.modifyGeom(0)
        vdata = geom.modifyVertexData()
        handle = vdata.modifyArrayHandle(0)
        handle.setSubdata(start * _VSIZE, count * _VSIZE, b'\x00' * (count * _VSIZE))
    except Exception:
        pass
