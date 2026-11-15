# -*- coding: utf-8 -*-
"""Объёмные здания: карнизы, пилястры, балконы, козырьки, пожарные лестницы, мансарды, башни сложной формы.

Данные города (game/city.py) описывают дом одним прямоугольником.  Здесь по этому описанию строится
геометрия «с рельефом»: вместо гладкой коробки — выступающие детали и разные силуэты крыш, а в деловом
центре — башни с подиумом, срезанными углами, круглые, со шпилями и скатными верхушками.

Столкновения остаются прежними (прямоугольник участка), поэтому игровая логика не меняется.
Все случайные решения берутся из генератора, привязанного к координатам дома: город каждый раз одинаков.
"""
import math

from . import props as P

W4 = (1.0, 1.0, 1.0, 1.0)

# вид дома по текстуре фасада
KIND = {
    'fac_brick_a': 'brick', 'fac_brick_b': 'brick', 'fac_brick_c': 'brick', 'fac_brick_d': 'brick',
    'fac_conc_b': 'stucco', 'fac_conc_a': 'panel',
    'fac_balcony_a': 'balcony', 'fac_balcony_b': 'balcony',
    'fac_glass_a': 'glass', 'fac_glass_b': 'glass', 'fac_glass_c': 'glass', 'fac_glass_d': 'glass',
    'fac_glass_e': 'glass',
    'fac_deco_a': 'deco', 'fac_deco_b': 'deco', 'fac_deco_c': 'deco',
    'fac_ghetto_a': 'ghetto', 'fac_ghetto_b': 'ghetto',
    'fac_siding': 'house', 'fac_wh': 'box', 'fac_wh_win': 'shed',
}

# цвет каменных деталей (карниз, пояс, пилястры)
TRIM = {
    'fac_brick_a': (0.80, 0.77, 0.71), 'fac_brick_b': (0.66, 0.60, 0.50), 'fac_brick_c': (0.86, 0.83, 0.76),
    'fac_brick_d': (0.56, 0.56, 0.58), 'fac_conc_b': (0.62, 0.58, 0.52), 'fac_conc_a': (0.66, 0.66, 0.66),
    'fac_balcony_a': (0.74, 0.70, 0.62), 'fac_balcony_b': (0.66, 0.70, 0.76),
    'fac_ghetto_a': (0.50, 0.48, 0.46), 'fac_ghetto_b': (0.46, 0.42, 0.40),
    'fac_deco_a': (0.97, 0.95, 0.91), 'fac_deco_b': (0.97, 0.97, 0.95), 'fac_deco_c': (0.98, 0.97, 0.95),
}

# стеклянные башни: цвет переплётов и цвет верхушки
GLASS = {
    'fac_glass_a': ((0.16, 0.21, 0.28), (0.30, 0.42, 0.52)),
    'fac_glass_b': ((0.07, 0.08, 0.10), (0.16, 0.17, 0.20)),
    'fac_glass_c': ((0.86, 0.87, 0.84), (0.34, 0.56, 0.50)),
    'fac_glass_d': ((0.25, 0.18, 0.10), (0.50, 0.36, 0.16)),
    'fac_glass_e': ((0.74, 0.76, 0.78), (0.40, 0.46, 0.52)),
    'fac_conc_a': ((0.60, 0.60, 0.60), (0.36, 0.38, 0.42)),
}

AWNINGS = {'gf_shop_a': 'awning_a', 'gf_shop_b': 'awning_b', 'gf_shop_c': 'awning_c', 'gf_shop_d': 'awning_d'}
ROOF_METAL = [(0.50, 0.24, 0.20), (0.30, 0.42, 0.34), (0.40, 0.41, 0.44), (0.52, 0.34, 0.24), (0.34, 0.36, 0.42)]
PANELS = [(0.62, 0.70, 0.80), (0.86, 0.82, 0.70), (0.60, 0.74, 0.64), (0.80, 0.80, 0.80), (0.76, 0.58, 0.50)]
DARK_METAL = (0.13, 0.13, 0.15, 1.0)
PREV = {'s': 'w', 'e': 's', 'n': 'e', 'w': 'n'}
NEXT = {'s': 'e', 'e': 'n', 'n': 'w', 'w': 's'}


def _c4(c, k=1.0):
    return (c[0] * k, c[1] * k, c[2] * k, 1.0)


class Frame(object):
    """Система координат стены: u — вдоль стены (вправо, если смотреть снаружи), d — наружу, z — вверх."""
    __slots__ = ('ax', 'ay', 'dx', 'dy', 'nx', 'ny', 'L', 'side')

    def __init__(self, ax, ay, bx, by, side=''):
        L = math.hypot(bx - ax, by - ay)
        self.ax, self.ay, self.L, self.side = ax, ay, L, side
        if L > 1e-9:
            self.dx, self.dy = (bx - ax) / L, (by - ay) / L
        else:
            self.dx, self.dy = 1.0, 0.0
        self.nx, self.ny = self.dy, -self.dx

    def p(self, u, d, z):
        return (self.ax + self.dx * u + self.nx * d, self.ay + self.dy * u + self.ny * d, z)


def rect_frames(x0, y0, x1, y1):
    return [Frame(x0, y0, x1, y0, 's'), Frame(x1, y0, x1, y1, 'e'), Frame(x1, y1, x0, y1, 'n'),
            Frame(x0, y1, x0, y0, 'w')]


def rect_pts(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def poly_frames(pts):
    n = len(pts)
    return [Frame(pts[i][0], pts[i][1], pts[(i + 1) % n][0], pts[(i + 1) % n][1]) for i in range(n)]


def scale_poly(pts, k, cx=None, cy=None):
    if cx is None:
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
    return [(cx + (p[0] - cx) * k, cy + (p[1] - cy) * k) for p in pts]


def poly_bbox(pts):
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def fbox(mb, key, F, u0, u1, d0, d1, z0, z1, color, faces='ftblr', uv_m=None, top_color=None, top_key=-1,
         k_side=0.84, k_bot=0.6):
    """Брусок в системе координат стены.  faces: f перед, t верх, b низ, l/r торцы, k зад."""
    p = F.p
    c = color
    cs = (c[0] * k_side, c[1] * k_side, c[2] * k_side, 1.0)
    if uv_m:
        m = 1.0 / uv_m
        fu = (u0 * m, z0 * m, u1 * m, z1 * m)
        su = (d0 * m, z0 * m, d1 * m, z1 * m)
        tu = ((u0 * m, d0 * m), (u0 * m, d1 * m), (u1 * m, d1 * m), (u1 * m, d0 * m))
        bu = ((u0 * m, d0 * m), (u1 * m, d0 * m), (u1 * m, d1 * m), (u0 * m, d1 * m))
    else:
        fu = su = (0.0, 0.0, 1.0, 1.0)
        tu = bu = ((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0))
    if 'f' in faces:
        mb.quad(key, p(u0, d1, z0), p(u1, d1, z0), p(u1, d1, z1), p(u0, d1, z1), fu, c)
    if 'l' in faces:
        mb.quad(key, p(u0, d0, z0), p(u0, d1, z0), p(u0, d1, z1), p(u0, d0, z1), su, cs)
    if 'r' in faces:
        mb.quad(key, p(u1, d1, z0), p(u1, d0, z0), p(u1, d0, z1), p(u1, d1, z1), su, cs)
    if 't' in faces:
        mb.quad(key if top_key == -1 else top_key, p(u0, d0, z1), p(u0, d1, z1), p(u1, d1, z1), p(u1, d0, z1),
                uvs=tu, color=top_color or c)
    if 'b' in faces:
        mb.quad(key, p(u0, d0, z0), p(u1, d0, z0), p(u1, d1, z0), p(u0, d1, z0), uvs=bu,
                color=(c[0] * k_bot, c[1] * k_bot, c[2] * k_bot, 1.0))
    if 'k' in faces:
        mb.quad(key, p(u1, d0, z0), p(u0, d0, z0), p(u0, d0, z1), p(u1, d0, z1), fu, cs)


def ring(mb, key, frames, sel, z0, z1, d0, d1, color, uv_m=3.0, back=False, top_color=None):
    """Пояс вокруг прямоугольного дома на сторонах sel (карниз, парапет, цоколь)."""
    for F in frames:
        if F.side not in sel:
            continue
        pv = PREV[F.side] in sel
        nx = NEXT[F.side] in sel
        ua = -d1 if pv else 0.0
        ub = F.L + d1 if nx else F.L
        faces = 'ftb' + ('' if pv else 'l') + ('' if nx else 'r') + ('k' if back else '')
        fbox(mb, key, F, ua, ub, d0, d1, z0, z1, color, faces, uv_m, top_color)


def poly_ring(mb, key, frames, z0, z1, d0, d1, color, uv_m=3.0):
    """Парапет по контуру многоугольника."""
    for F in frames:
        if F.L < 0.05:
            continue
        fbox(mb, key, F, 0.0, F.L, d0, d1, z0, z1, color, 'ftk', uv_m)


def poly_cap(mb, key, pts, z, color, tile=4.0):
    """Плоская крышка выпуклого многоугольника (веером от центра)."""
    n = len(pts)
    if n == 4 and abs(pts[0][1] - pts[1][1]) < 1e-6 and abs(pts[1][0] - pts[2][0]) < 1e-6:
        mb.flat(key, pts[0][0], pts[0][1], pts[2][0], pts[2][1], z, tile=(tile, tile), color=color)
        return
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        mb.tri(key, (cx, cy, z), (a[0], a[1], z), (b[0], b[1], z), (cx / tile, cy / tile),
               (a[0] / tile, a[1] / tile), (b[0] / tile, b[1] / tile), color)


class Facades(object):
    """Строит здания города.  cm — CityMesh (нужен доступ к городу)."""

    def __init__(self, cm):
        self.cm = cm
        self.city = cm.city

    # ------------------------------------------------------------------
    # стены
    # ------------------------------------------------------------------
    def wall(self, mb, night, b, F, z0, z1, win, gf, rnd):
        """Стена: первый этаж (gf: None — нет, 'gf' — витрины, 'blank' — глухой, 'party' — брандмауэр)
        и этажи с окнами над ним.  Возвращает (z низа верхних этажей, число секций, число этажей)."""
        if F.L < 0.05:
            return z0, 0, 0
        p = F.p
        L = F.L
        tint = _c4(b.tint)
        zb = z0
        if gf is not None and b.gf_h > 0.01:
            zg = z0 + b.gf_h
            n = max(1, int(round(L / b.gf_bay)))
            if gf == 'gf':
                key = b.gf_tex
                mb.quad(key, p(0, 0, z0), p(L, 0, z0), p(L, 0, zg), p(0, 0, zg), (0, 0, n, 1),
                        tint if key.startswith('fac_') else W4)
            elif gf == 'blank':
                mb.quad('gf_blank', p(0, 0, z0), p(L, 0, z0), p(L, 0, zg), p(0, 0, zg), (0, 0, n, 1), tint)
            else:
                mb.quad(b.blank_tex, p(0, 0, z0), p(L, 0, z0), p(L, 0, zg), p(0, 0, zg),
                        (0, 0, L / 4.0, b.gf_h / 4.0), _c4(b.blank_tint))
            zb = zg
        if z1 - zb < 0.5:
            return zb, 0, 0
        if not win:
            mb.quad(b.blank_tex, p(0, 0, zb), p(L, 0, zb), p(L, 0, z1), p(0, 0, z1),
                    (0, 0, L / 4.0, (z1 - zb) / 4.0), _c4(b.blank_tint))
            return zb, 0, 0
        n = max(1, int(round(L / b.bay_w)))
        fl = max(1, int(round((z1 - zb) / b.floor_h)))
        mb.quad(b.fac, p(0, 0, zb), p(L, 0, zb), p(L, 0, z1), p(0, 0, z1), (0, 0, n, fl), tint)
        if b.night:
            uo = rnd.randint(0, 3) * 0.25
            vo = rnd.randint(0, 3) * 0.25
            night.quad((b.fac + '_n', 'addc'), p(0, 0, zb), p(L, 0, zb), p(L, 0, z1), p(0, 0, z1),
                       (uo, vo, uo + n / 4.0, vo + fl / 4.0))
        return zb, n, fl

    def rect_walls(self, mb, night, b, x0, y0, x1, y1, z0, z1, rnd, is_base):
        """Четыре стены прямоугольного объёма.  Возвращает {сторона: (frame, zb, секций, этажей)}."""
        out = {}
        for F in rect_frames(x0, y0, x1, y1):
            win = F.side in b.sides_win
            gf = None
            if is_base and b.gf_h > 0.01:
                gf = 'gf' if (win and F.side in b.sides_gf) else ('blank' if win else 'party')
            zb, n, fl = self.wall(mb, night, b, F, z0, z1, win, gf, rnd)
            out[F.side] = (F, zb, n, fl)
        return out

    # ------------------------------------------------------------------
    # детали
    # ------------------------------------------------------------------
    def awning(self, mb, F, u0, u1, z, key, depth=1.15, drop=0.56, val=0.2):
        """Матерчатый козырёк над витриной."""
        p = F.p
        zo = z - drop
        a, bb = p(u0, 0.03, z), p(u1, 0.03, z)
        c, d = p(u1, depth, zo), p(u0, depth, zo)
        w = (u1 - u0)
        dark = (0.5, 0.5, 0.52, 1.0)
        mb.quad(key, d, c, bb, a, (0, 0, w, 1), W4)
        mb.quad(key, c, d, a, bb, (0, 0, w, 1), dark)
        e, g = p(u0, depth, zo - val), p(u1, depth, zo - val)
        mb.quad(key, e, g, c, d, (0, 0, w, 0.25), (0.9, 0.9, 0.9, 1.0))
        mb.quad(key, g, e, d, c, (0, 0, w, 0.25), dark)
        side = (0.74, 0.74, 0.74, 1.0)
        mb.tri(key, a, p(u0, 0.03, zo), d, (0, 1), (0, 0), (0.12, 0), side)
        mb.tri(key, a, d, p(u0, 0.03, zo), (0, 1), (0.12, 0), (0, 0), dark)
        mb.tri(key, bb, c, p(u1, 0.03, zo), (0, 1), (0.12, 0), (0, 0), side)
        mb.tri(key, bb, p(u1, 0.03, zo), c, (0, 1), (0, 0), (0.12, 0), dark)

    def balcony(self, mb, F, u0, u1, z, col, depth=0.95, glazed=False):
        p = F.p
        fbox(mb, 'concrete', F, u0, u1, 0.0, depth, z - 0.13, z, (0.72, 0.72, 0.70, 1.0), 'ftblr', 3.0)
        h = 1.02
        c = _c4(col)
        dk = _c4(col, 0.6)
        w = u1 - u0
        key = 'corrugated'
        mb.quad(key, p(u0, depth, z), p(u1, depth, z), p(u1, depth, z + h), p(u0, depth, z + h), (0, 0, w / 1.6, 0.5), c)
        mb.quad(key, p(u1, depth, z), p(u0, depth, z), p(u0, depth, z + h), p(u1, depth, z + h), (0, 0, w / 1.6, 0.5), dk)
        cs = _c4(col, 0.84)
        mb.quad(key, p(u0, 0, z), p(u0, depth, z), p(u0, depth, z + h), p(u0, 0, z + h), (0, 0, 0.6, 0.5), cs)
        mb.quad(key, p(u0, depth, z), p(u0, 0, z), p(u0, 0, z + h), p(u0, depth, z + h), (0, 0, 0.6, 0.5), dk)
        mb.quad(key, p(u1, depth, z), p(u1, 0, z), p(u1, 0, z + h), p(u1, depth, z + h), (0, 0, 0.6, 0.5), cs)
        mb.quad(key, p(u1, 0, z), p(u1, depth, z), p(u1, depth, z + h), p(u1, 0, z + h), (0, 0, 0.6, 0.5), dk)
        if glazed:
            # застеклённый балкон: рама и стёкла до потолка
            zt = z + 2.5
            g = (0.55, 0.68, 0.76, 0.5)
            gk = (None, 'glass')
            mb.quad(gk, p(u0, depth, z + h), p(u1, depth, z + h), p(u1, depth, zt), p(u0, depth, zt), color=g)
            mb.quad(gk, p(u0, 0, z + h), p(u0, depth, z + h), p(u0, depth, zt), p(u0, 0, zt), color=g)
            mb.quad(gk, p(u1, depth, z + h), p(u1, 0, z + h), p(u1, 0, zt), p(u1, depth, zt), color=g)
            fbox(mb, None, F, u0 - 0.04, u1 + 0.04, 0.0, depth + 0.04, zt, zt + 0.1, (0.86, 0.86, 0.84, 1.0), 'ftblr')
            for uu in (u0, u1 - 0.06):
                fbox(mb, None, F, uu, uu + 0.06, depth - 0.06, depth, z + h, zt, (0.9, 0.9, 0.88, 1.0), 'flr')

    def ac_unit(self, mb, F, uc, z):
        fbox(mb, None, F, uc - 0.38, uc + 0.38, 0.0, 0.46, z, z + 0.44, (0.74, 0.75, 0.76, 1.0), 'tblr')
        p = F.p
        mb.quad('ac_unit', p(uc - 0.38, 0.46, z), p(uc + 0.38, 0.46, z), p(uc + 0.38, 0.46, z + 0.44),
                p(uc - 0.38, 0.46, z + 0.44), (0, 0, 1, 1), W4)

    def fire_escape(self, mb, F, u0, u1, zb, floors, floor_h, z_ground):
        """Пожарная лестница зигзагом: площадки на каждом этаже, марши между ними, спуск до первого этажа."""
        p = F.p
        dep = 1.15
        rail = ('rail', 'a')
        w = u1 - u0
        for f in range(floors):
            z = zb + f * floor_h + 0.05
            fbox(mb, None, F, u0, u1, 0.0, dep, z - 0.07, z, DARK_METAL, 'ftblr')
            hr = 0.95
            mb.quad(rail, p(u0, dep, z), p(u1, dep, z), p(u1, dep, z + hr), p(u0, dep, z + hr), (0, 0, w, 1), W4)
            mb.quad(rail, p(u0, 0, z), p(u0, dep, z), p(u0, dep, z + hr), p(u0, 0, z + hr), (0, 0, dep, 1), W4)
            mb.quad(rail, p(u1, dep, z), p(u1, 0, z), p(u1, 0, z + hr), p(u1, dep, z + hr), (0, 0, dep, 1), W4)
            # подкосы под площадкой
            for uu in (u0 + 0.04, u1 - 0.1):
                mb.quad2(None, p(uu, 0.0, z - 0.75), p(uu, dep - 0.05, z - 0.07), p(uu + 0.06, dep - 0.05, z - 0.07),
                         p(uu + 0.06, 0.0, z - 0.75), color=DARK_METAL)
            if f + 1 < floors:
                # марш на следующий этаж (чередуем направление)
                ua, ub = (u0 + 0.45, u1 - 0.45) if f % 2 == 0 else (u1 - 0.45, u0 + 0.45)
                z2 = z + floor_h
                a, bb = p(ua, dep - 0.1, z), p(ua, dep - 0.62, z)
                c, d = p(ub, dep - 0.62, z2), p(ub, dep - 0.1, z2)
                mb.quad2(None, a, bb, c, d, color=(0.17, 0.17, 0.19, 1.0))
                mb.quad(rail, p(ua, dep - 0.08, z), p(ub, dep - 0.08, z2), p(ub, dep - 0.08, z2 + 0.9),
                        p(ua, dep - 0.08, z + 0.9), (0, 0, abs(ub - ua), 1), W4)
        # спусковая лестница
        zl = zb + 0.05
        ul = u0 + 0.35
        mb.quad(('ladder', 'a'), p(ul, dep - 0.2, z_ground + 2.5), p(ul + 0.5, dep - 0.2, z_ground + 2.5),
                p(ul + 0.5, dep - 0.2, zl), p(ul, dep - 0.2, zl), (0, 0, 1, (zl - z_ground - 2.5) / 0.9), W4)

    def chimney(self, mb, x, y, z, h=1.5, w=0.7, d=0.55):
        mb.box('brick', x - w * 0.5, y - d * 0.5, z, x + w * 0.5, y + d * 0.5, z + h, (0.82, 0.78, 0.76, 1.0),
               faces='xXyY', uv_m=2.0)
        mb.box(None, x - w * 0.5 - 0.06, y - d * 0.5 - 0.06, z + h, x + w * 0.5 + 0.06, y + d * 0.5 + 0.06,
               z + h + 0.1, (0.32, 0.30, 0.29, 1.0))

    def dormer(self, mb, F, uc, z, rise, run, over, col):
        """Слуховое окно на скате мансарды."""
        p = F.p
        hw = 0.62
        df = -0.32
        zf = z + rise * (over - df) / (run + over)
        zt = min(zf + 1.2, z + rise - 0.02)
        db = -((zt - z) / rise * (run + over) - over)
        u0, u1 = uc - hw, uc + hw
        mb.quad('dormer', p(u0, df, zf), p(u1, df, zf), p(u1, df, zt), p(u0, df, zt), (0, 0, 1, 1), W4)
        cs = _c4(col, 0.8)
        mb.tri('roof_metal', p(u0, df, zf), p(u0, df, zt), p(u0, db, zt), (0, 0), (0, 0.5), (0.5, 0.5), cs)
        mb.tri('roof_metal', p(u1, df, zf), p(u1, db, zt), p(u1, df, zt), (0, 0), (0.5, 0.5), (0, 0.5), cs)
        mb.quad('roof_metal', p(u0 - 0.08, db, zt), p(u0 - 0.08, df + 0.12, zt), p(u1 + 0.08, df + 0.12, zt),
                p(u1 + 0.08, db, zt), (0, 0, 0.6, 0.6), _c4(col))

    def frustum(self, mb, b, x0, y0, x1, y1, z, rise, run, sloped, over, key, col, min_top=1.0, um=2.0,
                blank=None, two_sided=False):
        """Скатная крыша: наклонные скаты на сторонах sloped, остальные стороны — вертикальные (брандмауэры).
        Возвращает прямоугольник плоской верхушки."""
        nxs = ('w' in sloped) + ('e' in sloped)
        nys = ('s' in sloped) + ('n' in sloped)
        if nxs:
            run = min(run, (x1 - x0 - min_top) / nxs)
        if nys:
            run = min(run, (y1 - y0 - min_top) / nys)
        run = max(run, 0.05)
        sw, se, ss, sn = ('w' in sloped), ('e' in sloped), ('s' in sloped), ('n' in sloped)
        bx0, bx1 = x0 - over * sw, x1 + over * se
        by0, by1 = y0 - over * ss, y1 + over * sn
        tx0, tx1 = x0 + run * sw, x1 - run * se
        ty0, ty1 = y0 + run * ss, y1 - run * sn
        zt = z + rise
        B = {'sw': (bx0, by0, z), 'se': (bx1, by0, z), 'ne': (bx1, by1, z), 'nw': (bx0, by1, z)}
        T = {'sw': (tx0, ty0, zt), 'se': (tx1, ty0, zt), 'ne': (tx1, ty1, zt), 'nw': (tx0, ty1, zt)}
        sl = math.hypot(run + over, rise)
        bkey, bcol = blank if blank else (b.blank_tex, _c4(b.blank_tint))
        for side, c0, c1 in (('s', 'sw', 'se'), ('e', 'se', 'ne'), ('n', 'ne', 'nw'), ('w', 'nw', 'sw')):
            p0, p1, p2, p3 = B[c0], B[c1], T[c1], T[c0]
            ax = 0 if side in 'sn' else 1
            if side in sloped:
                uvs = ((p0[ax] / um, 0.0), (p1[ax] / um, 0.0), (p2[ax] / um, sl / um), (p3[ax] / um, sl / um))
                mb.quad(key, p0, p1, p2, p3, uvs=uvs, color=col)
                if two_sided:
                    mb.quad(key, p1, p0, p3, p2, uvs=(uvs[1], uvs[0], uvs[3], uvs[2]), color=_c4(col, 0.5))
            else:
                uvs = ((p0[ax] / 4.0, 0.0), (p1[ax] / 4.0, 0.0), (p2[ax] / 4.0, rise / 4.0), (p3[ax] / 4.0, rise / 4.0))
                mb.quad(bkey, p0, p1, p2, p3, uvs=uvs, color=bcol)
        return (tx0, ty0, tx1, ty1), zt

    # ------------------------------------------------------------------
    # крыши
    # ------------------------------------------------------------------
    def flat_roof(self, mb, b, x0, y0, x1, y1, z, sides_out='', out=0.0, ph=0.6, key='concrete', col=None,
                  thick=0.28):
        """Плоская крыша с толстым парапетом."""
        col = col or _c4(b.tint, 0.62)
        mb.flat(b.roof_tex, x0, y0, x1, y1, z, tile=(4.0, 4.0), color=_c4(b.roof_color))
        frames = rect_frames(x0, y0, x1, y1)
        for F in frames:
            o = out if F.side in sides_out else 0.0
            fbox(mb, key, F, 0.0, F.L, -thick, o, z, z + ph, col, 'ftk' + ('b' if o > 0.01 else ''), 3.0,
                 top_color=_c4(col, 1.18))
        return z + ph

    def gable_roof(self, mb, b, x0, y0, x1, y1, z, pitch=0.36, o=0.45, gable_key=None, gable_col=None):
        """Двускатная крыша со свесами; конёк вдоль длинной стороны.  Возвращает высоту конька."""
        col = _c4(b.roof_color)
        under = _c4(b.roof_color, 0.45)
        gcol = gable_col or _c4(b.tint, 0.94)
        wx, wy = x1 - x0, y1 - y0
        key = b.roof_tex
        if wx >= wy:
            cy = (y0 + y1) * 0.5
            rh = wy * pitch
            zr = z + rh
            ze = z - o * (rh / (wy * 0.5))
            nu = (wx + 2 * o) / 3.0
            nv = max(1.0, round(math.hypot(wy * 0.5 + o, rh + (z - ze)) / 2.4))
            q1 = ((x0 - o, y0 - o, ze), (x1 + o, y0 - o, ze), (x1 + o, cy, zr), (x0 - o, cy, zr))
            q2 = ((x1 + o, y1 + o, ze), (x0 - o, y1 + o, ze), (x0 - o, cy, zr), (x1 + o, cy, zr))
            for q in (q1, q2):
                mb.quad(key, q[0], q[1], q[2], q[3], (0, 0, nu, nv), col)
                mb.quad(key, q[1], q[0], q[3], q[2], (0, 0, nu, nv), under)
            mb.tri(gable_key, (x1, y0, z), (x1, y1, z), (x1, cy, zr), (0, 0), (wy / 3.5, 0), (wy / 7.0, rh / 3.2), gcol)
            mb.tri(gable_key, (x0, y1, z), (x0, y0, z), (x0, cy, zr), (0, 0), (wy / 3.5, 0), (wy / 7.0, rh / 3.2), gcol)
            return zr
        cx = (x0 + x1) * 0.5
        rh = wx * pitch
        zr = z + rh
        ze = z - o * (rh / (wx * 0.5))
        nu = (wy + 2 * o) / 3.0
        nv = max(1.0, round(math.hypot(wx * 0.5 + o, rh + (z - ze)) / 2.4))
        q1 = ((x1 + o, y0 - o, ze), (x1 + o, y1 + o, ze), (cx, y1 + o, zr), (cx, y0 - o, zr))
        q2 = ((x0 - o, y1 + o, ze), (x0 - o, y0 - o, ze), (cx, y0 - o, zr), (cx, y1 + o, zr))
        for q in (q1, q2):
            mb.quad(key, q[0], q[1], q[2], q[3], (0, 0, nu, nv), col)
            mb.quad(key, q[1], q[0], q[3], q[2], (0, 0, nu, nv), under)
        mb.tri(gable_key, (x0, y0, z), (x1, y0, z), (cx, y0, zr), (0, 0), (wx / 3.5, 0), (wx / 7.0, rh / 3.2), gcol)
        mb.tri(gable_key, (x1, y1, z), (x0, y1, z), (cx, y1, zr), (0, 0), (wx / 3.5, 0), (wx / 7.0, rh / 3.2), gcol)
        return zr

    def roof_props(self, mb, night, b, props, z, rect, rnd, allow=('stair', 'ac', 'tank', 'antenna', 'billboard',
                                                                   'helipad')):
        """Предметы на крыше; координаты поджимаются внутрь прямоугольника rect."""
        x0, y0, x1, y1 = rect
        top = z
        for rp in props:
            kind = rp[0]
            if kind not in allow:
                continue
            if kind in ('billboard', 'helipad'):
                self.cm._roof_prop(mb, night, rp, z, b, rnd)
                top = max(top, z + 7.0 if kind == 'billboard' else z)
                continue
            m = {'stair': 2.0, 'ac': 1.2, 'tank': 1.8, 'antenna': 1.0}.get(kind, 1.5)
            if x1 - x0 < 2 * m + 0.5 or y1 - y0 < 2 * m + 0.5:
                if kind != 'antenna':
                    continue
                x, y = (x0 + x1) * 0.5, (y0 + y1) * 0.5
            else:
                x = min(max(rp[1], x0 + m), x1 - m)
                y = min(max(rp[2], y0 + m), y1 - m)
            self.cm._roof_prop(mb, night, (kind, x, y) + tuple(rp[3:]), z, b, rnd)
            top = max(top, z + {'stair': 2.7, 'ac': 1.2, 'tank': 5.1}.get(kind, 0.0))
        return top

    # ------------------------------------------------------------------
    # главный вход
    # ------------------------------------------------------------------
    def build(self, b, mb, night, rnd):
        """Строит дом; возвращает высоту для столкновений."""
        kind = KIND.get(b.fac, 'plain')
        blocks = self.city.blocks
        zone = blocks[b.block].zone if 0 <= b.block < len(blocks) else '?'
        if b.roof_type == 'gable':
            return self._house(b, mb, night, rnd)
        if kind == 'shed':
            return self._shed(b, mb, night, rnd)
        if kind == 'glass' or (kind == 'panel' and zone == 'D'):
            return self._tower(b, mb, night, rnd)
        return self._block(b, mb, night, rnd, kind, zone)

    # ------------------------------------------------------------------
    # рядовая застройка: старый город, трущобы, набережная
    # ------------------------------------------------------------------
    def _block(self, b, mb, night, rnd, kind, zone):
        x0, y0, x1, y1 = b.x0, b.y0, b.x1, b.y1
        z0 = b.z0
        top = z0 + b.h
        walls = self.rect_walls(mb, night, b, x0, y0, x1, y1, z0, top, rnd, True)
        frames = [walls[s][0] for s in 'senw']
        win = ''.join(s for s in 'senw' if s in b.sides_win and walls[s][0].L > 0.05)
        trim = _c4(TRIM.get(b.fac, (0.7, 0.7, 0.7)))
        named = b.name is not None
        has_board = any(rp[0] in ('billboard', 'helipad') for rp in b.roof_props)
        fl_total = max((walls[s][3] for s in 'senw'), default=0)
        storeys = fl_total > 0 and b.gf_h > 0.01
        roof_rect = (x0, y0, x1, y1)
        roof_z = top
        relief = kind in ('brick', 'stucco', 'ghetto', 'balcony', 'deco', 'panel')

        # ---- крыша
        variant = 'flat'
        if kind in ('brick', 'stucco') and storeys and not has_board and not b.tiers and win:
            v = rnd.random()
            if named:
                variant = 'flat'
            elif v < 0.36 and min(x1 - x0, y1 - y0) > 7.0:
                variant = 'mansard'
            elif v < 0.56:
                variant = 'attic'
        if not relief:
            roof_z = self.flat_roof(mb, b, x0, y0, x1, y1, top)
        elif kind == 'balcony':
            # плоская плита со свесом
            mb.flat(b.roof_tex, x0, y0, x1, y1, top + 0.3, tile=(4.0, 4.0), color=_c4(b.roof_color))
            ring(mb, 'concrete', frames, win, top - 0.05, top + 0.3, 0.0, 0.55, _c4((0.78, 0.77, 0.74)))
            rest = ''.join(s for s in 'senw' if s not in win)
            ring(mb, 'concrete', frames, rest, top, top + 0.3, 0.0, 0.02, _c4(b.blank_tint, 0.9))
            roof_z = top + 0.3
        elif kind == 'deco':
            roof_z = self.flat_roof(mb, b, x0, y0, x1, y1, top, win, 0.12, 0.7, 'concrete', _c4(b.tint, 0.98))
            ring(mb, 'concrete', frames, win, top + 0.7, top + 0.86, -0.34, 0.2, trim)
            roof_z = top + 0.86
        elif variant == 'mansard':
            mcol = _c4(rnd.choice(ROOF_METAL))
            rise, run, over = 2.3, 1.3, 0.3
            ring(mb, 'concrete', frames, win, top - 0.50, top - 0.32, 0.0, 0.16, trim)
            ring(mb, 'concrete', frames, win, top - 0.32, top + 0.14, 0.0, 0.38, trim)
            roof_rect, roof_z = self.frustum(mb, b, x0, y0, x1, y1, top + 0.14, rise, run, win, over,
                                             'roof_metal', mcol)
            mb.flat(b.roof_tex, roof_rect[0], roof_rect[1], roof_rect[2], roof_rect[3], roof_z, tile=(4.0, 4.0),
                    color=_c4(b.roof_color))
            # брандмауэры чуть выше ската
            for F in rect_frames(*roof_rect):
                if F.side not in win and F.L > 0.3:
                    fbox(mb, b.blank_tex, F, 0.0, F.L, -0.3, 0.0, roof_z, roof_z + 0.35, _c4(b.blank_tint, 0.9),
                         'ftklr', 4.0)
            for s in win:
                F, zb, n, fl = walls[s]
                if n <= 0:
                    continue
                for k in range(n):
                    if n > 2 and rnd.random() < 0.3:
                        continue
                    self.dormer(mb, F, F.L * (k + 0.5) / n, top + 0.14, rise, run, over, mcol)
        else:
            ph = 0.62 if kind != 'ghetto' else 0.5
            pcol = _c4(b.blank_tint, 0.95) if kind in ('brick', 'ghetto') else _c4(b.tint, 0.8)
            pkey = b.blank_tex if kind in ('brick', 'ghetto') else 'concrete'
            if kind != 'ghetto':
                ring(mb, 'concrete', frames, win, top - 0.50, top - 0.32, 0.0, 0.16, trim)
                ring(mb, 'concrete', frames, win, top - 0.32, top + 0.14, 0.0, 0.38, trim)
                zp = top + 0.14
            else:
                ring(mb, 'concrete', frames, win, top - 0.2, top + 0.02, 0.0, 0.12, trim)
                zp = top
            mb.flat(b.roof_tex, x0, y0, x1, y1, top, tile=(4.0, 4.0), color=_c4(b.roof_color))
            for F in frames:
                fbox(mb, pkey, F, 0.0, F.L, -0.3, 0.0, zp if F.side in win else top, top + 0.14 + ph, pcol, 'ftk',
                     4.0, top_color=_c4((0.62, 0.61, 0.59)), top_key='concrete')
            roof_z = top + 0.14 + ph
            if variant == 'attic':
                # аттик посередине главного фасада
                F = walls[win[0]][0]
                wa = min(F.L * 0.5, max(3.2, F.L * 0.34))
                fbox(mb, pkey, F, F.L * 0.5 - wa * 0.5, F.L * 0.5 + wa * 0.5, -0.3, 0.06, roof_z, roof_z + 1.0, pcol,
                     'ftklr', 4.0, top_color=trim, top_key='concrete')
                fbox(mb, 'concrete', F, F.L * 0.5 - wa * 0.5 - 0.15, F.L * 0.5 + wa * 0.5 + 0.15, -0.36, 0.2,
                     roof_z + 1.0, roof_z + 1.18, trim, 'ftblrk', 3.0)

        # ---- ярусы (если есть)
        for (tx0, ty0, tx1, ty1, tz0, tz1) in b.tiers:
            self.rect_walls(mb, night, b, tx0, ty0, tx1, ty1, z0 + tz0, z0 + tz1, rnd, False)
            roof_z = self.flat_roof(mb, b, tx0, ty0, tx1, ty1, z0 + tz1)
            roof_rect = (tx0, ty0, tx1, ty1)

        # ---- рельеф фасадов
        if relief and storeys:
            zb = z0 + b.gf_h
            for s in win:
                F, _zb, n, fl = walls[s]
                if n <= 0:
                    continue
                L = F.L
                bay = L / n
                shop = (s in b.sides_gf) and b.gf_tex in AWNINGS
                # пояс над первым этажом
                if kind != 'ghetto':
                    pv, nx = PREV[s] in win, NEXT[s] in win
                    fbox(mb, 'concrete', F, -0.16 if pv else 0.0, L + 0.16 if nx else L, 0.0, 0.16, zb - 0.06,
                         zb + 0.2, trim, 'ftb' + ('' if pv else 'l') + ('' if nx else 'r'), 3.0)
                # пилястры по краям дома
                if kind in ('brick', 'stucco') and L > 6.0:
                    ztop = top - 0.5
                    for (ua, ub) in ((0.0, 0.42), (L - 0.42, L)):
                        fbox(mb, 'concrete', F, ua, ub, 0.0, 0.13, zb + 0.2, ztop, trim, 'flr', 3.0)
                    for (ua, ub) in ((0.0, 0.15), (L - 0.15, L)):
                        fbox(mb, 'concrete', F, ua, ub, 0.0, 0.13, z0, zb - 0.06, trim, 'flr', 3.0)
                # козырьки над витринами
                if shop and not named and rnd.random() < 0.8:
                    key = AWNINGS[b.gf_tex]
                    ng = max(1, int(round(L / b.gf_bay)))
                    gb = L / ng
                    if b.gf_tex == 'gf_shop_c':
                        fbox(mb, None, F, 0.15, L - 0.15, 0.0, 1.25, z0 + 3.02, z0 + 3.16, (0.16, 0.24, 0.46, 1.0),
                             'ftblr')
                        fbox(mb, None, F, 0.15, L - 0.15, 1.25, 1.3, z0 + 2.9, z0 + 3.2, (0.80, 0.82, 0.86, 1.0),
                             'ftblrk')
                    else:
                        for k in range(ng):
                            if rnd.random() < 0.12:
                                continue
                            self.awning(mb, F, gb * k + 0.06, gb * k + gb * 0.69, z0 + 3.2, key)
                # балконы
                if kind == 'balcony':
                    pc = rnd.choice(PANELS)
                    for f in range(fl):
                        for k in range(n):
                            self.balcony(mb, F, bay * k + bay * 0.05, bay * k + bay * 0.56, zb + f * b.floor_h + 0.05,
                                         pc, glazed=(rnd.random() < 0.16))
                # «брови» и рёбра ар-деко
                elif kind == 'deco':
                    for f in range(fl):
                        zz = zb + f * b.floor_h + 2.66
                        if zz > top - 0.4:
                            break
                        fbox(mb, None, F, 0.0, L, 0.0, 0.5, zz, zz + 0.1, trim, 'ftblr')
                    for (ua, ub) in ((0.0, 0.3), (L - 0.3, L)):
                        fbox(mb, None, F, ua, ub, 0.0, 0.5, zb + 0.2, top + 0.86, trim, 'flrt')
                # кондиционеры под окнами
                if kind in ('brick', 'stucco', 'ghetto', 'panel'):
                    for f in range(fl):
                        for k in range(n):
                            if rnd.random() < (0.14 if kind != 'ghetto' else 0.08):
                                self.ac_unit(mb, F, bay * (k + 0.5), zb + f * b.floor_h + 0.82)
            # пожарная лестница на главном фасаде
            if kind in ('brick', 'ghetto') and not named and win:
                F, _zb, n, fl = walls[win[0]]
                if n >= 3 and fl >= 2 and rnd.random() < (0.42 if kind == 'brick' else 0.8):
                    k = rnd.randint(1, n - 2)
                    bay = F.L / n
                    self.fire_escape(mb, F, bay * k + 0.2, bay * (k + 1) - 0.2, zb, fl, b.floor_h, z0)
            # пилон с названием на гостиницах набережной
            if kind == 'deco' and not named and fl_total >= 3 and win:
                F = walls[win[0]][0]
                uc = F.L * (0.5 if rnd.random() < 0.5 else 0.22)
                acc = _c4(b.tint, 0.72) if b.fac != 'fac_deco_c' else (0.30, 0.62, 0.66, 1.0)
                fbox(mb, None, F, uc - 0.7, uc + 0.7, 0.0, 0.75, zb + 0.2, top + 3.6, trim, 'flrt')
                fbox(mb, None, F, uc - 0.32, uc + 0.32, 0.75, 0.84, zb + 1.0, top + 3.0, acc, 'flrtb')
                for kz in (0.25, 0.5, 0.75):
                    hx, hy, hz = F.p(uc, 1.1, zb + 1.0 + (top + 2.0 - zb) * kz)
                    P.glow(night, hx, hy, hz, 2.6, (1.0, 0.45, 0.75, 1.0) if b.fac != 'fac_deco_b'
                           else (0.4, 1.0, 0.9, 1.0))
                roof_z = max(roof_z, top + 0.9)

        # ---- хозяйство на крыше
        if variant == 'mansard':
            deck = roof_z
            allow = ('ac', 'antenna', 'tank')
        else:
            deck = top + 0.3 if (kind == 'balcony' and relief) else top
            allow = ('stair', 'ac', 'tank', 'antenna', 'billboard', 'helipad')
        if b.tiers:
            deck = z0 + b.tiers[-1][5]
        top_all = max(roof_z, self.roof_props(mb, night, b, b.roof_props, deck,
                                              (roof_rect[0] + 0.4, roof_rect[1] + 0.4, roof_rect[2] - 0.4,
                                               roof_rect[3] - 0.4), rnd, allow))
        if kind in ('brick', 'stucco', 'ghetto') and not named and not b.tiers:
            rx0, ry0, rx1, ry1 = roof_rect
            zc = deck
            for s in 'senw':
                if s in win or rnd.random() < 0.35:
                    continue
                F = walls[s][0]
                if F.L < 6.0:
                    continue
                for k in range(rnd.randint(1, 2)):
                    u = F.L * rnd.uniform(0.2, 0.8)
                    cx, cy, _ = F.p(u, -0.75, 0.0)
                    if not (rx0 + 0.5 < cx < rx1 - 0.5 and ry0 + 0.5 < cy < ry1 - 0.5):
                        continue
                    hx = 0.7 if s in 'sn' else 0.55
                    hy = 0.55 if s in 'sn' else 0.7
                    self.chimney(mb, cx, cy, zc, 1.5 + rnd.random() * 0.5, hx, hy)
        return top_all

    # ------------------------------------------------------------------
    # частные дома
    # ------------------------------------------------------------------
    def _house(self, b, mb, night, rnd):
        x0, y0, x1, y1 = b.x0, b.y0, b.x1, b.y1
        z0 = b.z0
        top = z0 + b.h
        walls = self.rect_walls(mb, night, b, x0, y0, x1, y1, z0, top, rnd, True)
        frames = [walls[s][0] for s in 'senw']
        white = (0.93, 0.92, 0.88, 1.0)
        # цоколь
        ring(mb, 'concrete', frames, 'senw', z0, z0 + 0.34, 0.0, 0.06, (0.60, 0.59, 0.57, 1.0))
        # крыша: двускатная или вальмовая
        hip = rnd.random() < 0.32
        if hip:
            wmin = min(x1 - x0, y1 - y0)
            rise = wmin * 0.33
            run = wmin * 0.5
            over = 0.45
            ze = top - over * rise / run
            self.frustum(mb, b, x0, y0, x1, y1, ze, rise + (top - ze), run + over * 0.0, 'senw', over, b.roof_tex,
                         _c4(b.roof_color), min_top=0.0, um=2.4, two_sided=True)
            zr = top + rise
            # подшивка свеса
            ring(mb, None, frames, 'senw', ze - 0.02, ze + 0.1, 0.0, over, white)
        else:
            zr = self.gable_roof(mb, b, x0, y0, x1, y1, top, gable_key='siding', gable_col=_c4(b.tint, 0.96))
        # дверь и крыльцо
        side = b.open_sides[:1] if b.open_sides else 's'
        F = walls[side][0]
        m = F.L * 0.5
        p = F.p
        mb.quad('gf_house', p(m - 1.75, 0.04, z0), p(m + 1.75, 0.04, z0), p(m + 1.75, 0.04, z0 + 3.2),
                p(m - 1.75, 0.04, z0 + 3.2), (0, 0, 1, 1), _c4(b.tint))
        ud = m - 0.49                       # ось двери
        u0, u1 = ud - 1.05, ud + 1.05
        dep = 1.35
        fbox(mb, 'concrete', F, u0, u1, 0.0, dep, z0, z0 + 0.2, (0.74, 0.73, 0.71, 1.0), 'ftlr', 2.0)
        fbox(mb, 'concrete', F, u0 + 0.25, u1 - 0.25, dep, dep + 0.3, z0, z0 + 0.1, (0.70, 0.69, 0.67, 1.0), 'ftlr',
             2.0)
        za, zo = z0 + 2.95, z0 + 2.62
        rc = _c4(b.roof_color)
        a, bb = p(u0 - 0.12, 0.05, za), p(u1 + 0.12, 0.05, za)
        c, d = p(u1 + 0.12, dep + 0.2, zo), p(u0 - 0.12, dep + 0.2, zo)
        mb.quad(b.roof_tex, d, c, bb, a, (0, 0, 1.0, 0.6), rc)
        mb.quad(None, c, d, a, bb, color=_c4(white, 0.7))
        fbox(mb, None, F, u0 - 0.12, u1 + 0.12, dep + 0.12, dep + 0.2, zo - 0.14, zo, white, 'fbk')
        for uu in (u0, u1 - 0.1):
            fbox(mb, None, F, uu, uu + 0.1, dep - 0.02, dep + 0.08, z0 + 0.2, zo - 0.1, white, 'flrk')
        # труба
        if rnd.random() < 0.8:
            wx, wy = x1 - x0, y1 - y0
            t = rnd.choice((0.24, 0.76))
            if wx >= wy:
                cx, cy = x0 + wx * t, (y0 + y1) * 0.5 + rnd.choice((-1.0, 1.0)) * wy * 0.16
            else:
                cx, cy = (x0 + x1) * 0.5 + rnd.choice((-1.0, 1.0)) * wx * 0.16, y0 + wy * t
            self.chimney(mb, cx, cy, top - 0.2, (zr - top) + 1.0, 0.7, 0.7)
        return zr

    # ------------------------------------------------------------------
    # склады
    # ------------------------------------------------------------------
    def _shed(self, b, mb, night, rnd):
        x0, y0, x1, y1 = b.x0, b.y0, b.x1, b.y1
        z0 = b.z0
        top = z0 + b.h
        walls = self.rect_walls(mb, night, b, x0, y0, x1, y1, z0, top, rnd, True)
        frames = [walls[s][0] for s in 'senw']
        tint = _c4(b.tint)
        zr = self.gable_roof(mb, b, x0, y0, x1, y1, top, pitch=0.13, o=0.35, gable_key='fac_wh',
                             gable_col=_c4(b.tint, 0.92))
        # цоколь и отлив под кровлей
        ring(mb, 'concrete', frames, 'senw', z0, z0 + 0.5, 0.0, 0.08, (0.52, 0.52, 0.52, 1.0))
        # вентиляционные фонари на коньке
        wx, wy = x1 - x0, y1 - y0
        n = max(1, int(max(wx, wy) // 9))
        for k in range(n):
            t = (k + 0.5) / n
            if wx >= wy:
                cx, cy, sx, sy = x0 + wx * t, (y0 + y1) * 0.5, 1.6, 1.0
            else:
                cx, cy, sx, sy = (x0 + x1) * 0.5, y0 + wy * t, 1.0, 1.6
            mb.box('louver', cx - sx, cy - sy, zr - 0.35, cx + sx, cy + sy, zr + 0.7, _c4(b.tint, 0.9),
                   faces='xXyY', uv_m=1.2)
            mb.box(None, cx - sx - 0.15, cy - sy - 0.15, zr + 0.7, cx + sx + 0.15, cy + sy + 0.15, zr + 0.82,
                   (0.36, 0.37, 0.40, 1.0))
        # водосточные трубы по углам
        for F in frames:
            if F.L > 8:
                fbox(mb, None, F, 0.2, 0.36, 0.0, 0.16, z0, top - 0.1, _c4(b.tint, 0.62), 'flr')
        return zr + 0.9

    # ------------------------------------------------------------------
    # башни делового центра
    # ------------------------------------------------------------------
    def _prism(self, mb, night, b, pts, za, zb_, rnd, fins=None, ledges=None, key_cap=True):
        """Объём-призма над подиумом: стены с окнами по всем граням."""
        frames = poly_frames(pts)
        for F in frames:
            _z, n, fl = self.wall(mb, night, b, F, za, zb_, True, None, rnd)
            if n <= 0:
                continue
            if fins is not None and F.L >= 5.0:
                for k in range(n + 1):
                    u = F.L * k / n
                    fbox(mb, None, F, u - 0.09, u + 0.09, 0.0, 0.26, za, zb_, fins, 'flr')
            if ledges is not None:
                for f in range(1, fl + 1):
                    zz = za + f * (zb_ - za) / fl
                    fbox(mb, None, F, -0.3, F.L + 0.3, 0.0, 0.3, zz - 0.09, zz + 0.07, ledges, 'ftb')
        return frames

    def _crown(self, mb, night, b, pts, z, rnd, crown, colors, props):
        """Верхушка башни.  Возвращает высоту для столкновений."""
        mull, ccol = colors
        x0, y0, x1, y1 = poly_bbox(pts)
        cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
        wmin = min(x1 - x0, y1 - y0)
        n = len(pts)
        frames = poly_frames(pts)
        cc = _c4(ccol)
        top = z
        if crown == 'pyramid':
            hp = min(16.0, wmin * rnd.uniform(0.45, 0.7))
            poly_ring(mb, 'concrete', frames, z, z + 0.5, -0.3, 0.0, _c4(mull))
            for i in range(n):
                a, bb = pts[i], pts[(i + 1) % n]
                w = math.hypot(bb[0] - a[0], bb[1] - a[1])
                mb.tri('roof_metal', (a[0], a[1], z + 0.5), (bb[0], bb[1], z + 0.5), (cx, cy, z + 0.5 + hp),
                       (0, 0), (w / 2.4, 0), (w / 4.8, hp / 2.4), cc)
            mb.cylinder(None, cx, cy, z + hp, z + hp + 5.0, 0.14, 4, (0.8, 0.8, 0.82, 1.0), cap_top=False)
            P.glow(night, cx, cy, z + hp + 5.2, 3.2, (1.0, 0.15, 0.1, 1.0))
            return z + 0.5 + hp
        if crown == 'spire':
            hf = max(2.5, wmin * 0.22)
            inner = scale_poly(pts, 0.42, cx, cy)
            for i in range(n):
                a, bb = pts[i], pts[(i + 1) % n]
                c, d = inner[(i + 1) % n], inner[i]
                w = math.hypot(bb[0] - a[0], bb[1] - a[1])
                mb.quad('roof_metal', (a[0], a[1], z), (bb[0], bb[1], z), (c[0], c[1], z + hf), (d[0], d[1], z + hf),
                        uvs=((0, 0), (w / 2.4, 0), (w / 2.4 * 0.71, hf / 2.0), (w / 2.4 * 0.29, hf / 2.0)), color=cc)
            poly_cap(mb, None, inner, z + hf, _c4(ccol, 0.7))
            hm = rnd.uniform(10.0, 20.0)
            mb.cylinder(None, cx, cy, z + hf, z + hf + hm * 0.45, 0.45, 6, (0.72, 0.73, 0.76, 1.0), r_top=0.2)
            mb.cylinder(None, cx, cy, z + hf + hm * 0.45, z + hf + hm, 0.12, 4, (0.8, 0.8, 0.82, 1.0), cap_top=False)
            P.glow(night, cx, cy, z + hf + hm + 0.2, 3.4, (1.0, 0.15, 0.1, 1.0))
            return z + hf
        if crown == 'slant' and n == 4:
            rise = wmin * rnd.uniform(0.28, 0.42)
            k = rnd.randint(0, 3)                       # грань, у которой верх остаётся низким
            q = [pts[(k + i) % 4] for i in range(4)]    # q0-q1 низкая грань, q2-q3 высокая
            lo0, lo1, hi1, hi0 = q[0], q[1], q[2], q[3]
            w = math.hypot(lo1[0] - lo0[0], lo1[1] - lo0[1])
            dd = math.hypot(hi1[0] - lo1[0], hi1[1] - lo1[1])
            sl = math.hypot(dd, rise)
            mb.quad('roof_metal', (lo0[0], lo0[1], z), (lo1[0], lo1[1], z), (hi1[0], hi1[1], z + rise),
                    (hi0[0], hi0[1], z + rise), (0, 0, w / 2.4, sl / 2.4), cc)
            side = _c4(mull)
            mb.tri(None, (lo1[0], lo1[1], z), (hi1[0], hi1[1], z), (hi1[0], hi1[1], z + rise), color=side)
            mb.tri(None, (hi0[0], hi0[1], z), (lo0[0], lo0[1], z), (hi0[0], hi0[1], z + rise), color=side)
            Fh = Frame(hi1[0], hi1[1], hi0[0], hi0[1])
            nb = max(1, int(round(Fh.L / b.bay_w)))
            nf = max(1, int(round(rise / b.floor_h)))
            mb.quad(b.fac, Fh.p(0, 0, z), Fh.p(Fh.L, 0, z), Fh.p(Fh.L, 0, z + rise), Fh.p(0, 0, z + rise),
                    (0, 0, nb, nf), _c4(b.tint))
            return z + rise
        if crown == 'steps':
            cur = pts
            zz = z
            for k, sc in enumerate((0.74, 0.66)):
                poly_cap(mb, b.roof_tex, cur, zz, _c4(b.roof_color))
                poly_ring(mb, 'concrete', poly_frames(cur), zz, zz + 0.45, -0.25, 0.0, _c4(mull))
                cur = scale_poly(cur, sc, cx, cy)
                hh = b.floor_h * rnd.randint(2, 3)
                self._prism(mb, night, b, cur, zz, zz + hh, rnd)
                zz += hh
            poly_cap(mb, b.roof_tex, cur, zz, _c4(b.roof_color))
            poly_ring(mb, 'concrete', poly_frames(cur), zz, zz + 0.45, -0.25, 0.0, _c4(mull))
            hm = rnd.uniform(8.0, 16.0)
            mb.cylinder(None, cx, cy, zz, zz + hm, 0.16, 4, (0.8, 0.8, 0.82, 1.0), cap_top=False)
            P.glow(night, cx, cy, zz + hm + 0.2, 3.2, (1.0, 0.15, 0.1, 1.0))
            return zz + 0.45
        # плоская крыша: парапет, машинное отделение, хозяйство
        poly_cap(mb, b.roof_tex, pts, z, _c4(b.roof_color))
        poly_ring(mb, 'concrete', frames, z, z + 0.9, -0.3, 0.0, _c4(mull))
        top = z + 0.9
        sx, sy = (x1 - x0) * 0.2, (y1 - y0) * 0.2
        if min(sx, sy) > 1.6:
            hm = rnd.uniform(2.6, 4.0)
            ox, oy = rnd.uniform(-0.3, 0.3) * sx, rnd.uniform(-0.3, 0.3) * sy
            mb.box('louver', cx + ox - sx, cy + oy - sy, z, cx + ox + sx, cy + oy + sy, z + hm,
                   (0.78, 0.79, 0.80, 1.0), faces='xXyY', uv_m=1.6)
            mb.box(None, cx + ox - sx - 0.1, cy + oy - sy - 0.1, z + hm, cx + ox + sx + 0.1, cy + oy + sy + 0.1,
                   z + hm + 0.15, (0.40, 0.41, 0.43, 1.0))
            top = z + hm
        safe = (cx - (x1 - x0) * 0.33, cy - (y1 - y0) * 0.33, cx + (x1 - x0) * 0.33, cy + (y1 - y0) * 0.33)
        top = max(top, self.roof_props(mb, night, b, props, z, safe, rnd))
        return top

    def _tower(self, b, mb, night, rnd):
        x0, y0, x1, y1 = b.x0, b.y0, b.x1, b.y1
        z0 = b.z0
        top = z0 + b.h
        w, h = x1 - x0, y1 - y0
        fl = max(1, int(round((b.h - b.gf_h) / b.floor_h)))
        colors = GLASS.get(b.fac, ((0.3, 0.3, 0.32), (0.3, 0.32, 0.36)))
        mull = _c4(colors[0])
        named = b.name is not None
        special = any(rp[0] in ('billboard', 'helipad') for rp in b.roof_props)
        detail = rnd.random()
        fins = mull if detail < 0.5 else None
        ledges = mull if 0.5 <= detail < 0.72 else None
        if b.fac == 'fac_conc_a':
            fins, ledges = mull, None
        props = [rp for rp in b.roof_props]

        # ---- форма
        shape = 'box'
        if not (named or special or b.tiers) and fl >= 8 and min(w, h) >= 15.0:
            v = rnd.random()
            ratio = max(w, h) / min(w, h)
            if v < 0.22:
                shape = 'box'
            elif v < 0.46:
                shape = 'podium'
            elif v < 0.66:
                shape = 'cross'
            elif v < 0.84:
                shape = 'octagon'
            else:
                shape = 'round' if ratio < 1.5 else 'octagon'
        crowns = ['flat', 'flat', 'pyramid', 'spire', 'steps', 'slant']
        if named or special:
            crown = 'flat'
        else:
            crown = rnd.choice(crowns)
            if fl < 10 and crown in ('steps', 'spire'):
                crown = 'flat'

        zb = z0 + b.gf_h
        if shape == 'box':
            walls = self.rect_walls(mb, night, b, x0, y0, x1, y1, z0, top, rnd, True)
            base_frames = [walls[s][0] for s in 'senw']
            self._tower_relief(mb, b, walls, zb, top, fins, ledges)
            cur = rect_pts(x0, y0, x1, y1)
            zc = top
            if b.tiers:
                self.flat_roof(mb, b, x0, y0, x1, y1, top, col=mull, ph=0.7)
                for i, (tx0, ty0, tx1, ty1, tz0, tz1) in enumerate(b.tiers):
                    tw = self.rect_walls(mb, night, b, tx0, ty0, tx1, ty1, z0 + tz0, z0 + tz1, rnd, False)
                    self._tower_relief(mb, b, tw, z0 + tz0, z0 + tz1, fins, ledges)
                    cur = rect_pts(tx0, ty0, tx1, ty1)
                    zc = z0 + tz1
                    if i + 1 < len(b.tiers):
                        self.flat_roof(mb, b, tx0, ty0, tx1, ty1, zc, col=mull, ph=0.7)
            if crown == 'slant' and (b.tiers or min(w, h) < 12):
                crown = 'pyramid'
            top_all = self._crown(mb, night, b, cur, zc, rnd, crown, colors, props)
        else:
            # подиум во весь участок, над ним — башня другой формы
            pf = 2 if fl < 14 else 3
            zp = zb + pf * b.floor_h
            walls = self.rect_walls(mb, night, b, x0, y0, x1, y1, z0, zp, rnd, True)
            base_frames = [walls[s][0] for s in 'senw']
            self.flat_roof(mb, b, x0, y0, x1, y1, zp, col=mull, ph=0.8)
            ring(mb, None, base_frames, 'senw', zp + 0.8, zp + 0.95, -0.34, 0.12, _c4(colors[0], 1.25))
            m = rnd.uniform(1.4, 2.6)
            X0, Y0, X3, Y3 = x0 + m, y0 + m, x1 - m, y1 - m
            if shape == 'podium':
                ins = [rnd.uniform(0.0, 2.2) for _ in range(4)]
                pts = rect_pts(X0 + ins[0], Y0 + ins[1], X3 - ins[2], Y3 - ins[3])
            elif shape == 'cross':
                c = min(X3 - X0, Y3 - Y0) * rnd.uniform(0.16, 0.24)
                X1, X2, Y1, Y2 = X0 + c, X3 - c, Y0 + c, Y3 - c
                pts = [(X1, Y0), (X2, Y0), (X2, Y1), (X3, Y1), (X3, Y2), (X2, Y2), (X2, Y3), (X1, Y3), (X1, Y2),
                       (X0, Y2), (X0, Y1), (X1, Y1)]
            elif shape == 'octagon':
                c = min(X3 - X0, Y3 - Y0) * rnd.uniform(0.22, 0.3)
                pts = [(X0 + c, Y0), (X3 - c, Y0), (X3, Y0 + c), (X3, Y3 - c), (X3 - c, Y3), (X0 + c, Y3),
                       (X0, Y3 - c), (X0, Y0 + c)]
            else:
                r = min(X3 - X0, Y3 - Y0) * 0.5
                cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
                ns = 16
                pts = [(cx + r * math.cos(2 * math.pi * (i + 0.5) / ns), cy + r * math.sin(2 * math.pi * (i + 0.5) / ns))
                       for i in range(ns)]
            convex = shape != 'cross'
            # верхняя часть высоких башен сужается
            zs = None
            n_up = fl - pf
            if n_up >= 12 and rnd.random() < 0.6 and crown != 'steps':
                zs = zp + int(n_up * rnd.uniform(0.55, 0.75)) * b.floor_h
            f_sh = fins if shape != 'round' else None
            self._prism(mb, night, b, pts, zp, zs or top, rnd, f_sh, ledges)
            cur = pts
            zc = top
            if zs is not None:
                self._cap(mb, b, pts, zs, convex, mull)
                cur = scale_poly(pts, rnd.uniform(0.72, 0.84))
                self._prism(mb, night, b, cur, zs, top, rnd, f_sh, ledges)
            if not convex:
                # верхушка «креста» — по вписанному прямоугольнику, остальное закрываем плоской крышей
                self._cap(mb, b, cur, zc, False, mull)
                bx0, by0, bx1, by1 = poly_bbox(cur)
                k = 0.2
                cur = rect_pts(bx0 + (bx1 - bx0) * k, by0 + (by1 - by0) * k, bx1 - (bx1 - bx0) * k,
                               by1 - (by1 - by0) * k)
                if crown == 'flat':
                    props = [rp for rp in props if rp[0] == 'antenna']
            if crown == 'slant' and len(cur) != 4:
                crown = 'pyramid'
            if not convex and crown in ('slant', 'pyramid', 'spire', 'steps'):
                # на крестообразной башне фигурная верхушка стоит на невысоком барабане
                self._prism(mb, night, b, cur, zc, zc + b.floor_h, rnd)
                zc += b.floor_h
            top_all = self._crown(mb, night, b, cur, zc, rnd, crown, colors, props)
        # ---- козырёк над входом
        side = None
        for s in b.sides_gf:
            if s in b.sides_win:
                side = s
                break
        if side and b.gf_tex == 'gf_office' and b.gf_h > 3.0:
            F = [f for f in base_frames if f.side == side][0]
            wc = min(9.0, F.L * 0.42)
            u0, u1 = F.L * 0.5 - wc * 0.5, F.L * 0.5 + wc * 0.5
            fbox(mb, None, F, u0, u1, 0.0, 2.6, z0 + 3.42, z0 + 3.62, _c4(colors[0], 0.9), 'ftblr')
            fbox(mb, None, F, u0 - 0.05, u1 + 0.05, 2.6, 2.68, z0 + 3.34, z0 + 3.7, (0.82, 0.83, 0.86, 1.0), 'ftblrk')
            for uu in (u0 + 0.3, u1 - 0.4):
                mb.quad2(None, F.p(uu, 0.02, z0 + 5.2), F.p(uu, 2.3, z0 + 3.62), F.p(uu + 0.08, 2.3, z0 + 3.62),
                         F.p(uu + 0.08, 0.02, z0 + 5.2), color=(0.7, 0.71, 0.74, 1.0))
        return top_all

    def _cap(self, mb, b, pts, z, convex, mull):
        """Плоская крыша уступа с парапетом."""
        if convex:
            poly_cap(mb, b.roof_tex, pts, z, _c4(b.roof_color))
        else:
            # крест: три прямоугольника
            xs = sorted(set(round(p[0], 4) for p in pts))
            ys = sorted(set(round(p[1], 4) for p in pts))
            col = _c4(b.roof_color)
            mb.flat(b.roof_tex, xs[1], ys[0], xs[2], ys[3], z, tile=(4.0, 4.0), color=col)
            mb.flat(b.roof_tex, xs[0], ys[1], xs[1], ys[2], z, tile=(4.0, 4.0), color=col)
            mb.flat(b.roof_tex, xs[2], ys[1], xs[3], ys[2], z, tile=(4.0, 4.0), color=col)
        poly_ring(mb, 'concrete', poly_frames(pts), z, z + 0.6, -0.28, 0.0, mull)

    def _tower_relief(self, mb, b, walls, za, zt, fins, ledges):
        for s in 'senw':
            F, _zb, n, fl = walls[s]
            if n <= 0:
                continue
            if fins is not None and F.L >= 5.0:
                for k in range(n + 1):
                    u = F.L * k / n
                    fbox(mb, None, F, u - 0.09, u + 0.09, 0.0, 0.26, za, zt, fins, 'flr')
            if ledges is not None:
                for f in range(1, fl + 1):
                    zz = za + f * (zt - za) / fl
                    fbox(mb, None, F, -0.3, F.L + 0.3, 0.0, 0.3, zz - 0.09, zz + 0.07, ledges, 'ftb')
