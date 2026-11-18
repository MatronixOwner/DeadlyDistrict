# -*- coding: utf-8 -*-
"""Построение геометрии города и статических столкновений по данным City."""
import math
import random

from panda3d.core import NodePath, TextureStage, TransparencyAttrib

from .meshbuilder import MeshBuilder, erase_vertices
from . import props as P
from . import props as P_
from .facade import Facades
from .city import (CURB, SIDEWALK, AVE_W, ST_W, CAP_LEN, BAY_W, FLOOR_H, GF_H, WATER_Z, ROAD_X_AVE, ROAD_Y_AVE)
from .collision import (F_CAR, F_PED, F_SIGHT, F_BULLET, F_BREAK, F_CAM, F_SOLID, F_WALL)
from .terrain import FLAT as TERRAIN_FLAT

W4 = (1.0, 1.0, 1.0, 1.0)
ROAD_UNDER = 0.25               # на столько полотно дороги заходит под бордюр (город изогнут: см. _road_quad)
SHOULDER = 2.2                  # обочина трассы: ширина, высота, цвет
SHOULDER_Z = -0.04
SHOULDER_C = (0.80, 0.78, 0.74, 1.0)

# мягкие тени на земле: пятно под каждым предметом и затемнение вдоль стен домов
SHADE = ('shadow', 'decal_c')
NO_SHADE = frozenset(['litter', 'roadpost', 'windsock', 'plane', 'crane', 'cone'])
WALL_SHADE_W = 1.7              # ширина полосы у стены, м
WALL_SHADE_K = 0.90             # её сила (1 — как тень под машиной)


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


def sign_place(b, s, canopy=()):
    """Где висит вывеска s дома b: (высота середины, ширина, высота, вынос от стены).

    Вывеска магазина помещается между витриной и вторым этажом: выше начинаются балконы и окна.
    Над плоским козырьком её ставят на его край — иначе снизу, с тротуара, козырёк её закрывает."""
    z, w, h, dep = s['z'], s['w'], s['h'], 0.26
    if s.get('shop'):
        if s['side'] in canopy:
            dep = 1.34
            z = b.z0 + 3.2 + h * 0.5
        elif b.fac in ('fac_balcony_a', 'fac_balcony_b'):
            h = 0.84
            w = min(w, h * 4.15)
            z = b.z0 + b.gf_h - 0.10 - h * 0.5      # верх — под плитой первого балкона (она на 8 см ниже перекрытия)
    return z, w, h, dep


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

        steps = [self._terrain, self._roads, self._bridges, self._ground, self._buildings, self._boxes,
                 self._walls, self._props, self._special, self._signals, self._finish]
        for i, fn in enumerate(steps):
            fn()
            if progress:
                progress((i + 1) / float(len(steps)))

    # ------------------------------------------------------------------
    def _mb(self, chunk):
        m = self._mbs.get(chunk)
        if m is None:
            m = self._mbs[chunk] = MeshBuilder(self.city.warp)
        return m

    def _brk(self, chunk):
        m = self._brks.get(chunk)
        if m is None:
            m = self._brks[chunk] = MeshBuilder(self.city.warp)
        return m

    def _night(self, chunk):
        m = self._nights.get(chunk)
        if m is None:
            m = self._nights[chunk] = MeshBuilder(self.city.warp)
        return m

    def _road_chunk(self, x, y):
        return ('road', int(x // 230.0), int(y // 175.0))

    # ------------------------------------------------------------------
    # рельеф
    # ------------------------------------------------------------------
    def _terrain(self):
        """Готовая геометрия рельефа (tools/gen_terrain.py) и края мира."""
        from panda3d.core import Filename
        import os
        c = self.city
        t = c.terrain
        self.terrain_root = None
        if not t.ok:
            return
        path = os.path.join(self.assets.root, 'assets', 'terrain', 'terrain.bam')
        try:
            root = self.assets.loader.loadModel(Filename.fromOsSpecific(path))
        except Exception:
            root = None
        if root is None or root.isEmpty():
            return
        root = root.copyTo(self.root)
        root.setName('terrain')
        self._warp_model(root)
        for gnp in root.findAllMatches('**/+GeomNode'):
            name = gnp.getName()
            key = tuple(name.split('|')) if '|' in name else name
            self.assets.apply_state(gnp, key)
        self.terrain_root = root
        # край мира: дальше рельефа нет — невидимая стена по границе сетки
        m = 24.0
        x0, y0, x1, y1 = t.x0 + m, t.y0 + m, t.x1 - m, t.y1 - m
        st = self.static
        flags = F_CAR | F_PED
        st.add_box(x0 - 6.0, y0, x0, y1, 0.0, 99.0, flags, None)
        st.add_box(x1, y0, x1 + 6.0, y1, 0.0, 99.0, flags, None)
        st.add_box(x0, y0 - 6.0, x1, y0, 0.0, 99.0, flags, None)
        st.add_box(x0, y1, x1, y1 + 6.0, 0.0, 99.0, flags, None)

    def _warp_model(self, root):
        """Готовая модель (рельеф) сделана по чертежу: изогнуть её вершины вместе с городом."""
        wp = self.city.warp
        if wp is None:
            return
        from panda3d.core import GeomVertexRewriter
        f = wp.fwd_memo
        for gnp in root.findAllMatches('**/+GeomNode'):
            gn = gnp.node()
            for i in range(gn.getNumGeoms()):
                vd = gn.modifyGeom(i).modifyVertexData()
                rw = GeomVertexRewriter(vd, 'vertex')
                while not rw.isAtEnd():
                    p = rw.getData3()
                    x, y = f(p[0], p[1])
                    rw.setData3(x, y, p[2])
            gn.markInternalBoundsStale()

    # ------------------------------------------------------------------
    # мосты
    # ------------------------------------------------------------------
    def _bridges(self):
        c = self.city
        T = c.terrain
        steel_red = (0.55, 0.2, 0.16, 1.0)
        steel_grey = (0.40, 0.44, 0.48, 1.0)
        conc = (0.62, 0.62, 0.62, 1.0)
        self.bridge_lamps = []
        for seg in c.bridges:
            br = seg['bridge']
            a, b, cc = seg['a'], seg['b'], seg['c']
            L = b - a
            hw = seg['width'] * 0.5
            if seg['kind'] == 'h':
                ox, oy, dx, dy = a, cc, 1.0, 0.0
            else:
                ox, oy, dx, dy = cc, a, 0.0, 1.0
            rx, ry = dy, -dx                           # вправо от направления

            def P(t, u, z):
                return (ox + dx * t + rx * u, oy + dy * t + ry * u, z)

            def chunk(t):
                x, y, _ = P(t, 0.0, 0.0)
                return c.outer_chunk(x, y)

            tex = 'road4' if seg['ave'] else 'road2'
            n = max(8, int(round(L / 6.0)))
            ew = 1.1                                   # ширина бортика
            zs = [c.bridge_z(seg, L * k / n) for k in range(n + 1)]
            water = []                                 # участки над водой (для опор)
            for k in range(n):
                t0, t1 = L * k / n, L * (k + 1) / n
                z0, z1 = zs[k], zs[k + 1]
                mb = self._mb(chunk((t0 + t1) * 0.5))
                # полотно
                mb.quad(tex, P(t0, -hw, z0), P(t0, hw, z0), P(t1, hw, z1), P(t1, -hw, z1),
                        uvs=((0, t0 / 8.0), (1, t0 / 8.0), (1, t1 / 8.0), (0, t1 / 8.0)))
                # низ и балки по краям
                th = 1.1
                mb.quad(None, P(t0, hw + ew, z0 - th), P(t0, -hw - ew, z0 - th), P(t1, -hw - ew, z1 - th),
                        P(t1, hw + ew, z1 - th), color=(0.3, 0.3, 0.32, 1))
                for sgn in (-1.0, 1.0):
                    ui, uo = sgn * hw, sgn * (hw + ew)
                    zt0, zt1 = z0 + 0.95, z1 + 0.95
                    side = [P(t0, uo, z0 - th), P(t1, uo, z1 - th), P(t1, uo, zt1), P(t0, uo, zt0)]
                    inner = [P(t1, ui, z1), P(t0, ui, z0), P(t0, ui, zt0), P(t1, ui, zt1)]
                    top = [P(t0, ui, zt0), P(t0, uo, zt0), P(t1, uo, zt1), P(t1, ui, zt1)]
                    if sgn < 0:
                        side.reverse()
                        inner.reverse()
                        top.reverse()
                    mb.quad('concrete', side[0], side[1], side[2], side[3], (t0 / 4.0, 0, t1 / 4.0, 0.5), conc)
                    mb.quad('concrete', inner[0], inner[1], inner[2], inner[3], (t0 / 4.0, 0, t1 / 4.0, 0.25),
                            (0.7, 0.7, 0.7, 1))
                    mb.quad(None, top[0], top[1], top[2], top[3], color=(0.78, 0.78, 0.76, 1))
                    # на суше под въездом — насыпь: стенка до земли
                    g0 = T.height(*P(t0, uo, 0)[:2])
                    g1 = T.height(*P(t1, uo, 0)[:2])
                    if (g0 > WATER_Z or g1 > WATER_Z) and (z0 - th > g0 + 0.05 or z1 - th > g1 + 0.05):
                        w0 = [P(t0, uo, min(g0, z0 - th) - 0.3), P(t1, uo, min(g1, z1 - th) - 0.3),
                              P(t1, uo, z1 - th), P(t0, uo, z0 - th)]
                        if sgn < 0:
                            w0.reverse()
                        mb.quad('concrete', w0[0], w0[1], w0[2], w0[3], (t0 / 4.0, 0, t1 / 4.0, 1.0), (0.56, 0.56, 0.56, 1))
                gm = T.height(*P((t0 + t1) * 0.5, 0.0, 0.0)[:2])
                water.append(gm < WATER_Z)
            # торцы насыпи не нужны: полотно начинается от перекрёстка на уровне земли
            # борта: не съехать и не сойти с моста
            for sgn in (-1.0, 1.0):
                p0 = P(0.0, sgn * (hw + 0.1), 0.0)
                p1 = P(L, sgn * (hw + ew), 0.0)
                self.static.add_box(min(p0[0], p1[0]), min(p0[1], p1[1]), max(p0[0], p1[0]), max(p0[1], p1[1]),
                                    0.0, 30.0, F_CAR | F_PED, None)
            # опоры над водой
            first = next((k for k, wv in enumerate(water) if wv), None)
            last = next((k for k in range(n - 1, -1, -1) if water[k]), None)
            if first is None:
                continue
            tw0, tw1 = L * first / n, L * (last + 1) / n
            span = tw1 - tw0
            if br['style'] == 'suspension':
                towers = [tw0 + span * 0.22, tw0 + span * 0.78]
                TH = br['height'] + 46.0
                for tt in towers:
                    mb = self._mb(chunk(tt))
                    night = self._night(chunk(tt))
                    zt = c.bridge_z(seg, tt)
                    for sgn in (-1.0, 1.0):
                        u = sgn * (hw + ew + 1.2)
                        self._pbox(mb, P, tt - 1.5, u - 1.2, tt + 1.5, u + 1.2, WATER_Z - 4.0, TH, steel_red)
                        x, y, _ = P(tt, u, 0)
                        P_.glow(night, x, y, TH + 1.0, 4.0, (1.0, 0.15, 0.1, 1.0))
                    for zz in (TH - 6.0, zt + (TH - zt) * 0.5):
                        self._pbox(mb, P, tt - 1.1, -hw - ew - 2.4, tt + 1.1, hw + ew + 2.4, zz, zz + 2.6, steel_red)
                    self._pbox(mb, P, tt - 2.4, -hw - ew - 3.0, tt + 2.4, hw + ew + 3.0, WATER_Z - 4.0, WATER_Z + 1.2, conc)
                # тросы: берег — пилон — пилон — берег
                cable = (0.5, 0.18, 0.14, 1.0)
                pts = [(max(4.0, tw0 - 46.0), None), (towers[0], TH), (towers[1], TH), (min(L - 4.0, tw1 + 46.0), None)]
                for sgn in (-1.0, 1.0):
                    u = sgn * (hw + ew + 1.2)
                    for k in range(3):
                        (ta, za), (tb, zb_) = pts[k], pts[k + 1]
                        za = c.bridge_z(seg, ta) + 1.2 if za is None else za
                        zb_ = c.bridge_z(seg, tb) + 1.2 if zb_ is None else zb_
                        segs = 12
                        prev = None
                        for i in range(segs + 1):
                            f = i / float(segs)
                            tt = ta + (tb - ta) * f
                            deck = c.bridge_z(seg, tt)
                            if k == 1:
                                zz = za - (4.0 * f * (1.0 - f)) * (za - deck - 5.0)
                            else:
                                lo, hi = (za, zb_) if za < zb_ else (zb_, za)
                                g_ = f if za < zb_ else 1.0 - f
                                zz = lo + (hi - lo) * g_ * g_
                            mb = self._mb(chunk(tt))
                            if prev is not None:
                                a0, a1 = P(prev[0], u, prev[1] - 0.25), P(tt, u, zz - 0.25)
                                a2, a3 = P(tt, u, zz + 0.25), P(prev[0], u, prev[1] + 0.25)
                                mb.quad2(None, a0, a1, a2, a3, color=cable)
                                if i < segs and zz > deck + 2.0:
                                    h0, h1 = P(tt - 0.06, u, deck + 0.95), P(tt + 0.06, u, deck + 0.95)
                                    h2, h3 = P(tt + 0.06, u, zz), P(tt - 0.06, u, zz)
                                    mb.quad2(None, h0, h1, h2, h3, color=cable)
                            prev = (tt, zz)
            else:
                # балочный мост: опоры через равные промежутки
                k = max(2, int(round(span / 34.0)))
                for i in range(k + 1):
                    tt = tw0 + span * i / k
                    zt = c.bridge_z(seg, tt)
                    mb = self._mb(chunk(tt))
                    self._pbox(mb, P, tt - 1.2, -hw + 1.0, tt + 1.2, hw - 1.0, WATER_Z - 4.0, zt - 1.1, conc)
                    self._pbox(mb, P, tt - 1.8, -hw - ew, tt + 1.8, hw + ew, zt - 2.0, zt - 1.1, (0.55, 0.55, 0.56, 1))
                # стальные перила поверх бортиков
                for k2 in range(n):
                    t0, t1 = L * k2 / n, L * (k2 + 1) / n
                    z0, z1 = zs[k2] + 0.95, zs[k2 + 1] + 0.95
                    mb = self._mb(chunk((t0 + t1) * 0.5))
                    for sgn in (-1.0, 1.0):
                        u = sgn * (hw + ew * 0.5)
                        mb.quad2(None, P(t0, u, z0 + 0.5), P(t1, u, z1 + 0.5), P(t1, u, z1 + 0.62), P(t0, u, z0 + 0.62),
                                 color=steel_grey)
                        mb.quad2(None, P(t0 - 0.05, u, z0), P(t0 + 0.05, u, z0), P(t0 + 0.05, u, z0 + 0.6),
                                 P(t0 - 0.05, u, z0 + 0.6), color=steel_grey)
            # фонари вдоль всего моста
            tt = 15.0
            while tt < L - 10.0:
                zt = c.bridge_z(seg, tt)
                mb = self._mb(chunk(tt))
                night = self._night(chunk(tt))
                for sgn in (-1.0, 1.0):
                    u = sgn * (hw + ew * 0.5)
                    x, y, _ = P(tt, u, 0)
                    mb.cylinder(None, x, y, zt + 0.95, zt + 6.2, 0.09, 5, P_.METAL, cap_top=False)
                    xi, yi, _ = P(tt, sgn * (hw - 1.4), 0)
                    mb.box(None, min(x, xi) - 0.05, min(y, yi) - 0.05, zt + 6.1, max(x, xi) + 0.05, max(y, yi) + 0.05,
                           zt + 6.22, P_.METAL)
                    P_.glow(night, xi, yi, zt + 6.0, 2.6)
                    P_.pool(night, xi - 5.0, yi - 5.0, xi + 5.0, yi + 5.0, zt + 0.05, k=0.35)
                tt += 28.0

    @staticmethod
    def _pbox(mb, P, t0, u0, t1, u1, z0, z1, color):
        """Параллелепипед в системе моста (вдоль t, поперёк u)."""
        a, b = P(t0, u0, 0.0), P(t1, u1, 0.0)
        mb.box(None, min(a[0], b[0]), min(a[1], b[1]), z0, max(a[0], b[0]), max(a[1], b[1]), z1, color)

    # ------------------------------------------------------------------
    # дороги
    # ------------------------------------------------------------------
    def _road_quad(self, mb, key, cx, cy, dx, dy, half_w, t0, t1, v0, v1, flip=False, z=0.0):
        """Кусок дороги вдоль направления (dx, dy) от t0 до t1 (от точки cx, cy).

        Улицы изогнуты, поэтому полотно кладётся короткими полосами во всю ширину: швы — по общей решётке,
        там же, где режутся тротуар и бордюр.  Поперёк полоса не режется (ровному полотну это не нужно),
        зато она на ладонь шире проезжей части и уходит под бордюр: щели у бордюра быть не может."""
        rx, ry = dy, -dx            # вправо от направления
        hw = half_w + (ROAD_UNDER if mb.warp is not None else 0.0)
        if mb.warp is not None and mb._xf is None and (dx == 0.0 or dy == 0.0) and not mb._rigid_rect(
                cx + dx * t0 - rx * half_w, cy + dy * t0 - ry * half_w, cx + dx * t1 + rx * half_w,
                cy + dy * t1 + ry * half_w):
            base = cx if dy == 0.0 else cy
            sgn = dx if dy == 0.0 else dy
            lo, hi = base + sgn * t0, base + sgn * t1
            ts = [(q - base) / sgn for q in mb._lattice(min(lo, hi), max(lo, hi))]
            if sgn < 0.0:
                ts.reverse()
        else:
            ts = [t0, t1]
        hold = mb.nosplit
        mb.nosplit = True
        try:
            for i in range(len(ts) - 1):
                ta, tb = ts[i], ts[i + 1]
                va = v0 + (v1 - v0) * (ta - t0) / (t1 - t0)
                vb = v0 + (v1 - v0) * (tb - t0) / (t1 - t0)
                a = (cx + dx * ta - rx * hw, cy + dy * ta - ry * hw, z)     # лево-начало
                b = (cx + dx * ta + rx * hw, cy + dy * ta + ry * hw, z)     # право-начало
                c = (cx + dx * tb + rx * hw, cy + dy * tb + ry * hw, z)
                d = (cx + dx * tb - rx * hw, cy + dy * tb - ry * hw, z)
                if not flip:
                    uvs = ((0, va), (1, va), (1, vb), (0, vb))
                else:
                    uvs = ((1, v1 + v0 - va), (0, v1 + v0 - va), (0, v1 + v0 - vb), (1, v1 + v0 - vb))
                mb.quad(key, a, b, c, d, uvs=uvs)
        finally:
            mb.nosplit = hold

    def _roads(self):
        c = self.city
        for key in sorted(c.segs):
            seg = c.segs[key]
            if seg['bridge'] is not None:
                continue                            # мост строится отдельно (см. _bridges)
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
            if seg['rural']:
                # трасса: разметка без «зебр», по краям — обочина
                n = max(1, int(round(L / 8.0)))
                self._road_quad(mb, tex, ox, oy, dx, dy, hw, 0.0, L, 0.0, float(n))
                sh = hw + SHOULDER
                if seg['kind'] == 'h':
                    mb.flat('dirt', a, cc - sh, b, cc + sh, SHOULDER_Z, tile=(4.0, 4.0), color=SHOULDER_C)
                else:
                    mb.flat('dirt', cc - sh, a, cc + sh, b, SHOULDER_Z, tile=(4.0, 4.0), color=SHOULDER_C)
                continue
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
        for key in sorted(c.nodes):
            n = c.nodes[key]
            mb = self._mb(self._road_chunk(n.x, n.y))
            if n.rural:
                mb.flat('dirt', n.x - n.hw - SHOULDER, n.y - n.hh - SHOULDER, n.x + n.hw + SHOULDER,
                        n.y + n.hh + SHOULDER, SHOULDER_Z, tile=(4.0, 4.0), color=SHOULDER_C)
            if n.through and n.rural:
                # трасса идёт насквозь: разметка не прерывается
                if 'e' in n.exits:
                    tex = 'road4' if ROAD_Y_AVE[n.j] else 'road2'
                    self._road_quad(mb, tex, n.x - n.hw, n.y, 1.0, 0.0, n.hh, 0.0, 2 * n.hw, 0.0, n.hw / 4.0)
                else:
                    tex = 'road4' if ROAD_X_AVE[n.i] else 'road2'
                    self._road_quad(mb, tex, n.x, n.y - n.hh, 0.0, 1.0, n.hw, 0.0, 2 * n.hh, 0.0, n.hh / 4.0)
                continue
            # перекрёсток — одним куском, на ладонь шире и на волос ниже дорог: заходит под их концы и под бордюр
            u = ROAD_UNDER if mb.warp is not None else 0.0
            hold, mb.nosplit = mb.nosplit, True
            mb.flat('asphalt', n.x - n.hw - u, n.y - n.hh - u, n.x + n.hw + u, n.y + n.hh + u,
                    -0.006 if u else 0.0, tile=(8.0, 8.0))
            mb.nosplit = hold

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
        # тротуары с внешней стороны улиц (там, где город кончается) и их бордюры
        zb = TERRAIN_FLAT - 0.06
        for (x0, y0, x1, y1) in c.walk_strips:
            mb = self._mb(c.outer_chunk((x0 + x1) * 0.5, (y0 + y1) * 0.5))
            mb.flat('sidewalk', x0, y0, x1, y1, CURB, tile=(3.0, 3.0))
            mb.wall('concrete', x0, y0, x1, y0, zb, CURB, (0, 0, (x1 - x0) / 2.0, 0.1), curb_c)
            mb.wall('concrete', x1, y0, x1, y1, zb, CURB, (0, 0, (y1 - y0) / 2.0, 0.1), curb_c)
            mb.wall('concrete', x1, y1, x0, y1, zb, CURB, (0, 0, (x1 - x0) / 2.0, 0.1), curb_c)
            mb.wall('concrete', x0, y1, x0, y0, zb, CURB, (0, 0, (y1 - y0) / 2.0, 0.1), curb_c)

    # ------------------------------------------------------------------
    # здания
    # ------------------------------------------------------------------
    def _sign(self, mb, night, x0, y0, x1, y1, side, off, z, w, h, tex, lit=True, back=False, depth=0.26, stand=False):
        """Вывеска-короб на стене.  stand — короб стоит отдельно (на краю козырька): у него своя толщина и задник."""
        ax, ay, dx, dy, nx, ny, L = side_frame(x0, y0, x1, y1, side)
        o = depth
        if stand:
            # тонкий короб на краю козырька: лицо, задняя стенка и торцы
            th = 0.2
            cx, cy = ax + dx * off + nx * o, ay + dy * off + ny * o
            a = (cx - dx * w * 0.5, cy - dy * w * 0.5, z - h * 0.5)
            b = (cx + dx * w * 0.5, cy + dy * w * 0.5, z - h * 0.5)
            c = (b[0], b[1], z + h * 0.5)
            d = (a[0], a[1], z + h * 0.5)
            mb.quad((tex, 'unlit') if lit else tex, a, b, c, d, (0, 0, 1, 1), (0.92, 0.92, 0.92, 1.0))
            a0, b0 = (a[0] - nx * th, a[1] - ny * th, a[2]), (b[0] - nx * th, b[1] - ny * th, b[2])
            c0, d0 = (b0[0], b0[1], c[2]), (a0[0], a0[1], d[2])
            edge = (0.16, 0.16, 0.18, 1.0)
            mb.quad(None, a0, a, d, d0, color=edge)
            mb.quad(None, b, b0, c0, c, color=edge)
            mb.quad(None, d, c, c0, d0, color=(0.24, 0.24, 0.26, 1.0))
            mb.quad(None, b0, a0, d0, c0, color=(0.12, 0.12, 0.14, 1.0))
            if lit and night is not None and tex.startswith('sign_'):
                P.pool(night, min(a[0], b[0]) - 2 + nx * 2.5, min(a[1], b[1]) - 2 + ny * 2.5,
                       max(a[0], b[0]) + 2 + nx * 2.5, max(a[1], b[1]) + 2 + ny * 2.5,
                       CURB + 0.06, color=(0.9, 0.85, 1.0, 1.0), k=0.16)
            return
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

    # ------------------------------------------------------------------
    # мягкие тени: пятна под предметами и затемнение земли у стен
    # ------------------------------------------------------------------
    def _blob(self, mb, x, y, hx, hy, yaw=0.0, k=1.0, n=1):
        """Пятно тени на земле: hx, hy — полуразмеры.

        В городе земля ровная, но со ступенькой бордюра: пятно обрезается по ступеньке (тень предмета на тротуаре
        не висит над дорогой).  За городом пятно ложится по рельефу (n — на сколько частей делить сторону)."""
        c = self.city
        gz = c.ground_z
        ca, sa = math.cos(yaw), math.sin(yaw)
        z0 = gz(x, y)
        col = (0.0, 0.0, 0.0, k)
        steps = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1)
        if c.where(x, y)[0] is not None:
            ext = []
            for (dx, dy, h) in ((1.0, 0.0, hx), (-1.0, 0.0, hx), (0.0, 1.0, hy), (0.0, -1.0, hy)):
                e = 0.0
                for q in steps:
                    lx, ly = dx * h * q, dy * h * q
                    if abs(gz(x + lx * ca - ly * sa, y + lx * sa + ly * ca) - z0) < 0.02:
                        e = h * q
                        break
                ext.append(e)
            x1, x0, y1, y0 = ext[0], -ext[1], ext[2], -ext[3]
            if x1 - x0 < 0.05 or y1 - y0 < 0.05:
                return
            pts, uvs = [], []
            for (lx, ly) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                pts.append((x + lx * ca - ly * sa, y + lx * sa + ly * ca, z0 + 0.03))
                uvs.append((lx / hx * 0.5 + 0.5, ly / hy * 0.5 + 0.5))
            mb.quad(SHADE, pts[0], pts[1], pts[2], pts[3], uvs=uvs, color=col)
            return
        rows = []
        for j in range(n + 1):
            row = []
            for i in range(n + 1):
                u, v = i / float(n), j / float(n)
                lx, ly = (u * 2.0 - 1.0) * hx, (v * 2.0 - 1.0) * hy
                wx, wy = x + lx * ca - ly * sa, y + lx * sa + ly * ca
                row.append(((wx, wy, gz(wx, wy) + 0.03), (u, v)))
            rows.append(row)
        for j in range(n):
            for i in range(n):
                a, b, cc, d = rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]
                mb.quad(SHADE, a[0], b[0], cc[0], d[0], uvs=(a[1], b[1], cc[1], d[1]), color=col)

    def _prop_shade(self, mb, kind, p, x, y, yaw, col):
        """Тень под уличным предметом: по его очертанию, у деревьев — по кроне."""
        if kind in NO_SHADE:
            return
        hold, mb.nosplit = mb.nosplit, True          # пятно маленькое и мягкое: резать его по решётке незачем
        try:
            self._prop_shade_(mb, kind, p, x, y, yaw, col)
        finally:
            mb.nosplit = hold

    def _prop_shade_(self, mb, kind, p, x, y, yaw, col):
        if kind == 'tree':
            r = 3.0 * p.get('size', 1.0)
            self._blob(mb, x, y, r, r, 0.0, 1.0, 2)
        elif kind == 'palm':
            r = 2.1 * p.get('size', 1.0)
            self._blob(mb, x, y, r, r, 0.0, 0.7, 2)
        elif col is None:
            return
        elif col[0] == 'c':
            r = max(0.45, col[1] * 1.6 + 0.2)
            self._blob(mb, x, y, r, r, 0.0, 1.0)
        elif col[0] == 'b':
            self._blob(mb, x, y, col[1] * 1.22 + 0.22, col[2] * 1.22 + 0.22, yaw, 1.0, 2 if max(col[1], col[2]) > 2.5 else 1)
        elif col[0] == 'legs':
            hx = max(abs(q[0]) for q in col[1]) + 0.5
            hy = max(abs(q[1]) for q in col[1]) + 0.5
            self._blob(mb, x, y, hx, hy, yaw, 0.8)

    def _wall_shade(self, mb, b, near):
        """Затемнение земли вдоль стен здания: полоса у каждой стены и четверть круга у каждого угла."""
        gz = self.city.ground_z
        W = WALL_SHADE_W
        col = (0.0, 0.0, 0.0, WALL_SHADE_K)
        x0, y0, x1, y1 = b.x0, b.y0, b.x1, b.y1

        city = self.city.where((x0 + x1) * 0.5, (y0 + y1) * 0.5)[0] is not None
        zb = gz((x0 + x1) * 0.5, (y0 + y1) * 0.5) + 0.03

        def pt(x, y):
            # в городе земля у дома ровная: полоса лежит на высоте его подножия (и не «сползает» с бордюра)
            return (x, y, zb if city else gz(x, y) + 0.03)

        def inside(x, y):
            for o in near:
                if o is not b and o.x0 < x < o.x1 and o.y0 < y < o.y1:
                    return True
            return False
        e = 0.04                                                    # полоса чуть заходит под стену: без щели
        # стены: ближний край — середина пятна (самое тёмное), дальний — его край
        for (ax, ay, bx, by, nx, ny) in ((x0, y0, x1, y0, 0.0, -1.0), (x1, y0, x1, y1, 1.0, 0.0),
                                         (x1, y1, x0, y1, 0.0, 1.0), (x0, y1, x0, y0, -1.0, 0.0)):
            L = math.hypot(bx - ax, by - ay)
            n = max(1, int(L // 14.0))                              # длинные стены — частями: по рельефу
            if city:
                # дом у самой дороги: за бордюром полосы нет
                mx_, my_ = (ax + bx) * 0.5 + nx * W, (ay + by) * 0.5 + ny * W
                if abs(gz(mx_, my_) + 0.03 - zb) > 0.02:
                    continue
            for i in range(n):
                t0, t1 = i / float(n), (i + 1) / float(n)
                px, py = ax + (bx - ax) * t0, ay + (by - ay) * t0
                qx, qy = ax + (bx - ax) * t1, ay + (by - ay) * t1
                mb.quad(SHADE, pt(px - nx * e, py - ny * e), pt(px + nx * W, py + ny * W), pt(qx + nx * W, qy + ny * W),
                        pt(qx - nx * e, qy - ny * e), uvs=((0.5, 0.5), (0.5, 1.0), (0.5, 1.0), (0.5, 0.5)), color=col)
        # углы; если вплотную стоит соседний дом, у его стены уже есть своя полоса — угол не нужен
        for (cx, cy, sx, sy) in ((x0, y0, -1.0, -1.0), (x1, y0, 1.0, -1.0), (x1, y1, 1.0, 1.0), (x0, y1, -1.0, 1.0)):
            if inside(cx + sx * 0.5, cy - sy * 0.5) or inside(cx - sx * 0.5, cy + sy * 0.5):
                continue
            if city and abs(gz(cx + sx * W, cy + sy * W) + 0.03 - zb) > 0.02:
                continue
            pa, pb, pc, pd = pt(cx, cy), pt(cx + sx * W, cy), pt(cx + sx * W, cy + sy * W), pt(cx, cy + sy * W)
            uv = ((0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (0.5, 1.0))
            if sx * sy > 0:
                mb.quad(SHADE, pa, pb, pc, pd, uvs=uv, color=col)
            else:                                                   # обход против часовой стрелки
                mb.quad(SHADE, pa, pd, pc, pb, uvs=(uv[0], uv[3], uv[2], uv[1]), color=col)

    def _buildings(self):
        c = self.city
        fac = Facades(self)
        by_block = {}
        for b in c.buildings:
            by_block.setdefault(b.block, []).append(b)
        for b in c.buildings:
            mb = self._mb(b.block)
            night = self._night(b.block)
            rnd = random.Random(int(b.x0 * 7 + b.y0 * 13) & 0xffff)
            # дом строится в своей сетке: стены прямые от угла до угла (или гранёные, если дом длинный)
            mb.begin_local(b.x0, b.y0, b.x1, b.y1)
            night.begin_local(b.x0, b.y0, b.x1, b.y1)
            top = fac.build(b, mb, night, rnd)
            self._wall_shade(mb, b, by_block[b.block])
            canopy = fac.canopy.get(id(b), ())
            # вывески
            for s in b.signs:
                z, w, h, dep = sign_place(b, s, canopy)
                self._sign(mb, night, b.x0, b.y0, b.x1, b.y1, s['side'], s['off'], z, w, h, s['tex'], depth=dep,
                           stand=dep > 1.0)
            mb.end_local()
            night.end_local()
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
            mb = self._mb(bx['block'])
            mb.begin_local(bx['x0'], bx['y0'], bx['x1'], bx['y1'])      # коробка остаётся коробкой
            if bx['tex'] == 'container':
                self._container(mb, bx)
            elif bx['faces']:
                col = _c4(bx['color'])
                mb.box(bx['tex'], bx['x0'], bx['y0'], bx['z0'], bx['x1'], bx['y1'], bx['z1'], col,
                       faces=bx['faces'], uv_m=bx['uv_m'], top_key=bx.get('top_tex'),
                       top_color=_c4(bx['top_color']) if bx.get('top_color') else None)
            mb.end_local()
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
            mb.begin_local(x0, y0, x1, y1, 10.0)          # забор: прямыми пролётами по десять метров
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
            elif kind == 'rail':
                # поручень: стойки и две перекладины — сквозь него видно, но не пройти и не проехать
                np_ = max(1, int(L // 2.0))
                for k in range(np_ + 1):
                    px = x0 + (x1 - x0) * k / np_
                    py = y0 + (y1 - y0) * k / np_
                    mb.box(None, px - 0.04, py - 0.04, z0, px + 0.04, py + 0.04, z0 + h, col)
                for zz in (z0 + h, z0 + h * 0.5):
                    if horiz:
                        mb.box(None, x0, y0 - 0.03, zz - 0.035, x1, y0 + 0.03, zz + 0.035, col)
                    else:
                        mb.box(None, x0 - 0.03, y0, zz - 0.035, x0 + 0.03, y1, zz + 0.035, col)
                flags = F_CAR | F_PED
                bx0, by0, bx1, by1 = (x0, y0 - 0.10, x1, y0 + 0.10) if horiz else (x0 - 0.10, y0, x0 + 0.10, y1)
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
            mb.end_local()
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
            self._prop_shade(mb, kind, p, x, y, yaw, col)
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
        # причалы: стенка набережной до дна
        dk = sp.get('docks')
        if dk:
            zb = WATER_Z - 3.0
            x0, y0, x1, y1 = dk['x0'], dk['y0'], dk['x1'], dk['y1']
            n = 6
            for k in range(n):
                ya = y0 + (y1 - y0) * k / n
                yb = y0 + (y1 - y0) * (k + 1) / n
                self._mb(oc(x1 - 1, (ya + yb) / 2)).wall('concrete', x1, ya, x1, yb, zb, CURB, (0, 0, 20, 1), stone)
            self._mb(oc(x1 - 1, y0)).wall('concrete', x0, y0, x1, y0, zb, CURB, (0, 0, 12, 1), stone)
            self._mb(oc(x1 - 1, y1)).wall('concrete', x1, y1, x0, y1, zb, CURB, (0, 0, 12, 1), stone)
        # корабль
        ship = sp.get('ship')
        if ship:
            mb = self._mb(ship['chunk'])
            x0, y0, x1, y1 = ship['x0'], ship['y0'], ship['x1'], ship['y1']
            dz = ship['deck']
            hull = (0.10, 0.11, 0.14, 1)
            deck_c = (0.36, 0.33, 0.30, 1)
            mb.box(None, x0, y0, WATER_Z - 2.0, x1, y1, 0.9, (0.42, 0.12, 0.10, 1))
            mb.box(None, x0, y0, 0.9, x1, y1, dz, hull, top_color=deck_c)
            # разметка проезда на палубе
            cy = ship['cy']
            for k in range(8):
                xa = x0 + 6.0 + k * 4.4
                mb.quad(None, (xa, cy - 2.75, dz + 0.02), (xa + 2.2, cy - 2.75, dz + 0.02),
                        (xa + 2.2, cy - 2.6, dz + 0.02), (xa, cy - 2.6, dz + 0.02), color=(0.85, 0.72, 0.2, 1))
                mb.quad(None, (xa, cy + 2.6, dz + 0.02), (xa + 2.2, cy + 2.6, dz + 0.02),
                        (xa + 2.2, cy + 2.75, dz + 0.02), (xa, cy + 2.75, dz + 0.02), color=(0.85, 0.72, 0.2, 1))
            # нос
            mb.tri(None, (x1, y0, dz), (x1 + 12.0, cy, dz), (x1, y1, dz), color=deck_c)
            mb.quad(None, (x1, y0, WATER_Z - 2), (x1 + 12.0, cy, WATER_Z - 2), (x1 + 12.0, cy, dz + 1.0), (x1, y0, dz + 1.0),
                    color=hull)
            mb.quad(None, (x1 + 12.0, cy, WATER_Z - 2), (x1, y1, WATER_Z - 2), (x1, y1, dz + 1.0), (x1 + 12.0, cy, dz + 1.0),
                    color=(0.09, 0.10, 0.12, 1))
            # надстройка — на носу
            hx0, hy0, hx1, hy1 = ship['house']
            mb.box('fac_conc_a', hx0, hy0, dz, hx1, hy1, dz + 9.6, (1, 1, 1, 1), uv_m=3.5, top_key='roof_gravel')
            hcx = (hx0 + hx1) * 0.5
            mb.cylinder(None, hcx, cy, dz + 9.6, dz + 14.0, 1.6, 8, (0.8, 0.2, 0.15, 1), top_color=(0.05, 0.05, 0.05, 1))
            # контейнеры на палубе
            for (cx0, cy0, cx1, cy1, lv, ci) in ship['containers']:
                rnd = random.Random(int(cx0 * 7 + cy0 * 13))
                for s_ in range(lv):
                    col = c.CONTAINER_COLORS[(ci + s_ * 3) % len(c.CONTAINER_COLORS)]
                    if col[0] > 0.8 and col[1] > 0.6 and col[2] < 0.3:
                        col = (0.2, 0.55, 0.3)          # жёлтый на этом корабле один — тот самый
                    mb.box('corrugated', cx0, cy0, dz + s_ * 2.6, cx1, cy1, dz + 2.6 + s_ * 2.6, _c4(col), uv_m=2.6)
            # жёлтый контейнер: пол, три стенки и крыша (ворота — отдельный подвижный узел, см. missions)
            yx0, yy0, yx1, yy1 = ship['yellow']
            yel = (0.93, 0.74, 0.12, 1)
            t = 0.16
            mb.box('corrugated', yx0, yy0 - t, dz, yx1, yy0, dz + 3.0, yel, uv_m=2.6)
            mb.box('corrugated', yx0, yy1, dz, yx1, yy1 + t, dz + 3.0, yel, uv_m=2.6)
            mb.box('corrugated', yx1, yy0 - t, dz, yx1 + t, yy1 + t, dz + 3.0, yel, uv_m=2.6)
            mb.box('corrugated', yx0, yy0 - t, dz + 3.0, yx1 + t, yy1 + t, dz + 3.14, yel, uv_m=2.6)
            mb.quad(None, (yx0, yy0, dz + 0.03), (yx1, yy0, dz + 0.03), (yx1, yy1, dz + 0.03), (yx0, yy1, dz + 0.03),
                    color=(0.30, 0.26, 0.20, 1))
            # аппарель: наклонная плита с причала на корму
            rx0, ry0, rx1, ry1 = ship['ramp']
            mb.quad('metal_paint', (rx0, ry0, CURB + 0.02), (rx1, ry0, dz + 0.02), (rx1, ry1, dz + 0.02),
                    (rx0, ry1, CURB + 0.02), uv=(0.0, 0.0, 8.0, 2.0), color=(0.34, 0.35, 0.38, 1))
            railc = (0.78, 0.66, 0.16, 1)
            for yy in (ry0, ry1):                        # боковины плиты и низкий жёлтый отбойник над ними
                mb.tri(None, (rx0, yy, CURB), (rx1, yy, CURB), (rx1, yy, dz), color=(0.20, 0.21, 0.24, 1))
                mb.tri(None, (rx1, yy, CURB), (rx0, yy, CURB), (rx1, yy, dz), color=(0.20, 0.21, 0.24, 1))
                for (ya, yb) in ((yy - 0.07, yy + 0.07),):
                    xa = rx0 + 2.5
                    za = CURB + (dz - CURB) * (xa - rx0) / (rx1 - rx0)
                    for sgn in (ya, yb):
                        mb.quad2(None, (xa, sgn, za), (rx1, sgn, dz), (rx1, sgn, dz + 0.45), (xa, sgn, za + 0.45),
                                 color=railc)
                    mb.quad(None, (xa, ya, za + 0.45), (rx1, ya, dz + 0.45), (rx1, yb, dz + 0.45), (xa, yb, za + 0.45),
                            color=railc)
            # трап: ступени вдоль борта и площадка наверху
            gx0, gy0, gx1, gy1 = ship['stairs']
            n = 17
            for k in range(n):
                xa = gx0 + (gx1 - gx0) * k / n
                xb = gx0 + (gx1 - gx0) * (k + 1) / n
                za = CURB + (dz - CURB) * (k + 1) / n
                mb.box(None, xa, gy0, za - 0.22, xb, gy1, za, (0.42, 0.43, 0.46, 1), top_color=(0.55, 0.56, 0.58, 1))
            lx0, ly0, lx1, ly1 = ship['landing']
            mb.box(None, lx0, ly0, dz - 0.2, lx1, ly1, dz, (0.42, 0.43, 0.46, 1), top_color=(0.55, 0.56, 0.58, 1))
            # перила трапа: стойки и поручень вдоль наклона (со стороны пирса), ограждение площадки
            pc = (0.72, 0.72, 0.74, 1)

            def zs(x):
                return CURB + (dz - CURB) * min(1.0, max(0.0, (x - gx0) / (gx1 - gx0)))
            xa = gx0 + 1.3
            while xa <= lx1 + 0.01:
                mb.box(None, xa - 0.03, gy0 - 0.03, zs(xa), xa + 0.03, gy0 + 0.03, zs(xa) + 1.0, pc)
                xa += 1.45
            mb.box(None, lx1 - 0.03, ly1 - 0.03, dz, lx1 + 0.03, ly1 + 0.03, dz + 1.0, pc)
            for hz in (1.0, 0.55):
                mb.quad2(None, (gx0 + 1.3, gy0, zs(gx0 + 1.3) + hz - 0.05), (gx1, gy0, dz + hz - 0.05),
                         (gx1, gy0, dz + hz), (gx0 + 1.3, gy0, zs(gx0 + 1.3) + hz), color=pc)
                mb.quad2(None, (gx1, gy0, dz + hz - 0.05), (lx1, gy0, dz + hz - 0.05), (lx1, gy0, dz + hz),
                         (gx1, gy0, dz + hz), color=pc)
                mb.quad2(None, (lx1, ly0, dz + hz - 0.05), (lx1, ly1, dz + hz - 0.05), (lx1, ly1, dz + hz),
                         (lx1, ly0, dz + hz), color=pc)
            night = self._night(ship['chunk'])
            P.glow(night, hcx, cy, dz + 15.0, 3.0, (1.0, 0.2, 0.15, 1.0))
            P.glow(night, x1 + 11.0, cy, dz + 2.0, 2.4, (0.3, 1.0, 0.4, 1.0))
            for k in range(4):
                P.glow(night, hx0 - 0.2, y0 + 3.5 + k * 3.0, dz + 6.0, 2.0, (1.0, 0.9, 0.6, 0.9))
            for k in range(5):                           # фонари вдоль проезда: ночью палубу видно
                P.glow(night, x0 + 8.0 + k * 9.0, cy, dz + 5.5, 2.6, (1.0, 0.92, 0.7, 0.8))

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
                wp = self.city.warp
                grp = self._sig_mbs[key] = {'r': MeshBuilder(wp), 'y': MeshBuilder(wp), 'g': MeshBuilder(wp)}
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
        # море — плитками: огромный одиночный квадрат плохо режется по краям экрана
        T = 14.0 * 30                                  # кратно шагу текстуры: швов не видно
        wx, wy = (c.grid_x0 + c.grid_x1) * 0.5, (c.grid_y0 + c.grid_y1) * 0.5
        n = 9
        for ix in range(-n, n):
            for iy in range(-n, n):
                x0, y0 = wx + ix * T, wy + iy * T
                mb.quad('water', (x0, y0, WATER_Z), (x0 + T, y0, WATER_Z), (x0 + T, y0 + T, WATER_Z),
                        (x0, y0 + T, WATER_Z), (0.0, 0.0, 30.0, 30.0), (0.85, 0.95, 1.0, 1.0))
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
