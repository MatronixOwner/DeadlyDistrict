# -*- coding: utf-8 -*-
"""Мотоциклы, скутер, мопед, велосипеды, квадроцикл, трайк и мотоцикл с коляской: модели собираются кодом.

Готового набора двухколёсной техники в стиле остальных машин и с понятной лицензией в открытых источниках
не нашлось (что и где искали — в assets/models/CREDITS.md), поэтому всё строится здесь.

Каждая модель строится вокруг ездока.  Сначала выбирается посадка — как человек сидит в седле (POSES);
по ней ставятся седло, руль и подножки, а уже вокруг них — бак, обтекатели, двигатель, рама.  Поэтому
руки ездока лежат на руле, а ноги стоят на подножках, кто бы ни сидел в седле.

Модель состоит из «кузова» (всё неподвижное), «вилки» (руль, перья, переднее крыло — поворачиваются
вместе с передним колесом) и колёс.  Краска — цвет бака, обтекателей и крыльев.
"""
import math

from .meshbuilder import MeshBuilder

TYRE = (0.07, 0.07, 0.075, 1.0)
RIM = (0.66, 0.67, 0.70, 1.0)
DARK = (0.11, 0.11, 0.12, 1.0)
ENGINE = (0.30, 0.31, 0.33, 1.0)
FIN = (0.50, 0.51, 0.54, 1.0)
STEEL = (0.76, 0.77, 0.80, 1.0)
SEAT = (0.07, 0.06, 0.06, 1.0)
LAMP = (1.0, 0.96, 0.82, 1.0)
RED = (0.78, 0.08, 0.06, 1.0)
AMBER = (0.95, 0.55, 0.08, 1.0)
GLASS = (0.17, 0.24, 0.30, 1.0)
WHITE = (0.92, 0.92, 0.90, 1.0)
BLUE = (0.10, 0.22, 0.66, 1.0)
PLATE = (0.90, 0.90, 0.86, 1.0)
COURIER = (0.96, 0.80, 0.10, 1.0)   # короб доставки
CRATE = (0.56, 0.42, 0.24, 1.0)
CRATE2 = (0.36, 0.46, 0.30, 1.0)

# Посадки.  mix — доля клипа «верхом» (остальное — «за рулём»), lean — наклон корпуса вперёд, градусы.
# Дальше — где при такой посадке оказываются кисти, стопы и колени относительно таза (метры; вперёд и вверх),
# снятые с самой анимации: по этим числам ставятся руль и подножки.
POSES = {
    'chair': dict(mix=0.0, lean=0.0, hand=(0.48, 0.33), foot=(0.20, 0.44, -0.44), knee=(0.22, 0.45, -0.01)),
    'cruise': dict(mix=0.2, lean=0.0, hand=(0.48, 0.27), foot=(0.24, 0.36, -0.48), knee=(0.23, 0.445, -0.055)),
    'std': dict(mix=0.35, lean=10.0, hand=(0.51, 0.135), foot=(0.28, 0.21, -0.54), knee=(0.24, 0.415, -0.16)),
    'bike': dict(mix=0.5, lean=20.0, hand=(0.505, 0.0), foot=(0.32, 0.05, -0.545), knee=(0.255, 0.36, -0.25)),
    # пассажиры: за спиной ездока — верхом, руки на бёдрах; в коляске — ноги вперёд, руки по бокам
    'pillion': dict(clips=(('sit', 0.55), ('ride', 0.45)), lean=4.0),
    'tub': dict(clips=(('sit', 0.6), ('sit_ground', 0.4)), lean=0.0),
    'bench': dict(clips=(('sit', 1.0),), lean=0.0),
    # карт: сидят низко, ноги вытянуты вперёд, руки на руле перед коленями
    'kart': dict(clips=(('drive', 0.6), ('sit_ground', 0.4)), lean=0.0, hand=(0.305, 0.09), foot=(0.20, 0.58, -0.275),
                 knee=(0.21, 0.445, 0.13)),
}
PELVIS_UP = 0.10            # таз сидящего — на столько выше поверхности седла
SOLE = 0.09                 # подошва — на столько ниже кости стопы

# вид -> размеры.  wb — база; rf, rr — радиусы колёс; wf, wr — ширина шин; seat — высота седла;
# rake — вынос оси переднего колеса вперёд от верха вилки; cb — на сколько ручки ближе к ездоку, чем верх вилки;
# cr — на сколько ручки выше верха вилки; bar — полуширина руля
KINDS = {
    'bike': dict(wb=1.40, rf=0.30, rr=0.30, wf=0.12, wr=0.17, seat=0.80, pose='bike', rake=0.27, cb=0.03, cr=-0.01,
                 bar=0.27, wheel='cast'),
    'chopper': dict(wb=1.78, rf=0.34, rr=0.31, wf=0.09, wr=0.20, seat=0.66, pose='chair', rake=0.52, cb=0.30,
                    cr=0.22, bar=0.33, wheel='wire', wheel_r='cast'),
    'scooter': dict(wb=1.26, rf=0.22, rr=0.22, wf=0.11, wr=0.12, seat=0.68, pose='chair', rake=0.15, cb=0.03,
                    cr=0.05, bar=0.27, wheel='solid'),
    'dirt': dict(wb=1.46, rf=0.36, rr=0.33, wf=0.09, wr=0.12, seat=0.92, pose='std', rake=0.40, cb=0.10, cr=0.10,
                 bar=0.37, wheel='wire'),
    'bicycle': dict(wb=1.08, rf=0.34, rr=0.34, wf=0.045, wr=0.045, seat=0.93, pose='std', rake=0.20, cb=0.10,
                    cr=0.06, bar=0.27, wheel='thin'),
    'quad': dict(wb=1.26, rf=0.29, rr=0.29, wf=0.24, wr=0.26, seat=0.82, pose='cruise', rake=0.10, cb=0.06, cr=0.08,
                 bar=0.36, wheel='fat', track=0.47),
    'moped': dict(wb=1.18, rf=0.28, rr=0.28, wf=0.065, wr=0.07, seat=0.80, pose='std', rake=0.24, cb=0.08, cr=0.07,
                  bar=0.28, wheel='wire'),
    'copbike': dict(wb=1.54, rf=0.31, rr=0.31, wf=0.12, wr=0.15, seat=0.78, pose='cruise', rake=0.34, cb=0.16,
                    cr=0.10, bar=0.33, wheel='cast'),
    'sidecar': dict(wb=1.46, rf=0.32, rr=0.32, wf=0.11, wr=0.12, seat=0.78, pose='std', rake=0.34, cb=0.10, cr=0.06,
                    bar=0.33, wheel='wire', x=-0.40),
    'trike': dict(wb=1.86, rf=0.34, rr=0.31, wf=0.09, wr=0.26, seat=0.66, pose='chair', rake=0.54, cb=0.30, cr=0.22,
                  bar=0.34, wheel='wire', wheel_r='fat', track=0.52),
    'bmx': dict(wb=0.94, rf=0.26, rr=0.26, wf=0.055, wr=0.055, seat=0.72, pose='cruise', rake=0.16, cb=0.08, cr=0.20,
                bar=0.30, wheel='thin'),
    'tourer': dict(wb=1.64, rf=0.32, rr=0.32, wf=0.12, wr=0.16, seat=0.76, pose='cruise', rake=0.36, cb=0.16,
                   cr=0.10, bar=0.34, wheel='cast'),
    'courier': dict(wb=1.26, rf=0.22, rr=0.22, wf=0.11, wr=0.12, seat=0.68, pose='chair', rake=0.15, cb=0.03,
                    cr=0.05, bar=0.27, wheel='solid'),
    'cargo': dict(wb=1.50, rf=0.22, rr=0.24, wf=0.11, wr=0.13, seat=0.70, pose='chair', rake=0.15, cb=0.03, cr=0.05,
                  bar=0.28, wheel='solid', track=0.47, layout='trike'),
    'kart': dict(wb=1.06, rf=0.14, rr=0.15, wf=0.13, wr=0.19, seat=0.32, pose='kart', rake=0.30, cb=0.03, cr=0.0,
                 bar=0.33, wheel='solid', track=0.46, layout='quad'),
    'caddy': dict(wb=1.56, rf=0.21, rr=0.21, wf=0.16, wr=0.16, seat=0.66, pose='chair', rake=0.22, cb=0.02, cr=0.0,
                  bar=0.19, wheel='solid', track=0.47, layout='quad', x=-0.25),
}
KINDS['quad']['layout'] = 'quad'
KINDS['trike']['layout'] = 'trike'
_cache = {}
_wheels = {}


class Geo(object):
    """Опорные точки модели, выведенные из посадки ездока."""

    def __init__(self, K):
        P = POSES[K['pose']]
        self.K = K
        self.P = P
        self.x = K.get('x', 0.0)                    # сдвиг самого мотоцикла вбок (у мотоцикла с коляской)
        self.fy, self.ry = K['wb'] * 0.5, -K['wb'] * 0.5
        self.rf, self.rr = K['rf'], K['rr']
        self.wf, self.wr = K['wf'], K['wr']
        self.sz = K['seat']                         # поверхность седла
        self.pz = self.sz + PELVIS_UP               # таз
        self.cy = self.fy - K['rake']               # верх вилки
        self.gy = self.cy - K['cb']                 # ручки руля
        self.sy = self.gy - 0.06 - P['hand'][0]     # таз (и середина седла)
        self.gz = self.pz + P['hand'][1] - 0.02
        self.cz = self.gz - K['cr']
        self.bar = K['bar']
        fx, ff, fu = P['foot']
        self.foot = (fx, self.sy + ff, self.pz + fu - SOLE)
        kx, kf, ku = P['knee']
        self.knee = (kx, self.sy + kf, self.pz + ku)


# ---------------------------------------------------------------------------
# набор для лепки
# ---------------------------------------------------------------------------
def _norm(v):
    ln = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / ln, v[1] / ln, v[2] / ln)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


class Kit(object):
    """Сборщик деталей: бруски, трубы по ломаной, поверхности по сечениям, крылья-дуги."""

    def __init__(self, ox=0.0, oy=0.0):
        self.mb = MeshBuilder()
        if ox or oy:
            self.mb.set_xform(-ox, -oy, 0.0)

    def box(self, x0, y0, z0, x1, y1, z1, col):
        self.mb.box(None, min(x0, x1), min(y0, y1), min(z0, z1), max(x0, x1), max(y0, y1), max(z0, z1), col)

    def loft(self, rings, col, cap0=True, cap1=True, cap_col=None):
        """Поверхность по сечениям.  Кольца обходятся против часовой стрелки, если смотреть им вслед."""
        q = self.mb.quad
        n = len(rings[0])
        for a, b in zip(rings, rings[1:]):
            for i in range(n):
                j = (i + 1) % n
                q(None, a[i], b[i], b[j], a[j], color=col)
        cc = cap_col or col
        for ring, back in ((rings[0], True), (rings[-1], False)):
            if (back and not cap0) or (not back and not cap1):
                continue
            c = (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n, sum(p[2] for p in ring) / n)
            for i in range(n):
                j = (i + 1) % n
                if back:
                    self.mb.tri(None, c, ring[i], ring[j], color=cc)
                else:
                    self.mb.tri(None, c, ring[j], ring[i], color=cc)

    @staticmethod
    def ring(y, zc, hw, hh, n=8, x=0.0, e=1.0):
        """Сечение поперёк машины (плоскость XZ) на отметке y: n-угольник с плоскими верхом, низом и боками."""
        out = []
        k = 1.0 / math.cos(math.pi / n)
        for i in range(n):
            a = (i + 0.5) * 2.0 * math.pi / n
            c, s = math.cos(a) * k, math.sin(a) * k
            if e != 1.0:
                c = math.copysign(abs(c) ** e, c)
                s = math.copysign(abs(s) ** e, s)
            out.append((x + hw * max(-1.0, min(1.0, c)), y, zc + hh * max(-1.0, min(1.0, s))))
        return out

    @staticmethod
    def ring_z(z, yc, hy, hx, n=8, x=0.0):
        """Сечение в горизонтальной плоскости (для деталей, которые тянутся вверх)."""
        out = []
        k = 1.0 / math.cos(math.pi / n)
        for i in range(n):
            a = (i + 0.5) * 2.0 * math.pi / n
            c, s = math.cos(a) * k, math.sin(a) * k
            out.append((x + hx * max(-1.0, min(1.0, s)), yc + hy * max(-1.0, min(1.0, c)), z))
        return out

    def body(self, secs, col, n=8, x=0.0, e=1.0, cap_col=None):
        """Обтекаемая деталь вдоль машины: secs — [(y, середина по высоте, полуширина, полувысота), ...]."""
        self.loft([self.ring(y, zc, hw, hh, n, x, e) for (y, zc, hw, hh) in secs], col, cap_col=cap_col)

    def tube(self, pts, r, col, n=5, caps=True, r1=None):
        """Труба по ломаной; r1 — радиус на дальнем конце (конус)."""
        m = len(pts)
        rings = []
        u = None
        for i, p in enumerate(pts):
            a = pts[max(0, i - 1)]
            b = pts[min(m - 1, i + 1)]
            d = _norm((b[0] - a[0], b[1] - a[1], b[2] - a[2]))
            if u is None:
                ref = (0.0, 0.0, 1.0) if abs(d[2]) < 0.9 else (0.0, 1.0, 0.0)
                u = _norm(_cross(d, ref))
            else:                                   # переносим прежнюю ось: труба на изгибах не перекручивается
                k = u[0] * d[0] + u[1] * d[1] + u[2] * d[2]
                u = _norm((u[0] - d[0] * k, u[1] - d[1] * k, u[2] - d[2] * k))
            v = _cross(u, d)
            rr = r if r1 is None else r + (r1 - r) * i / float(m - 1)
            ring = []
            for j in range(n):
                ang = (j + 0.5) * 2.0 * math.pi / n
                ca, sa = math.cos(ang) * rr, math.sin(ang) * rr
                ring.append((p[0] + u[0] * ca + v[0] * sa, p[1] + u[1] * ca + v[1] * sa, p[2] + u[2] * ca + v[2] * sa))
            rings.append(ring)
        self.loft(rings, col, caps, caps)

    def pair(self, pts, r, col, n=5, x=0.0, **kw):
        """Две одинаковые трубы по обе стороны от оси."""
        self.tube([(x + p[0], p[1], p[2]) for p in pts], r, col, n, **kw)
        self.tube([(x - p[0], p[1], p[2]) for p in pts], r, col, n, **kw)

    def fender(self, yc, zc, R, a0, a1, hw, col, x=0.0, n=6, lip=0.035):
        """Крыло — дуга вокруг колеса.  Углы в градусах: 0 — вперёд, 90 — вверх, 180 — назад."""
        rows = []
        for i in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * i / float(n))
            c, s = math.cos(a), math.sin(a)
            rows.append([(x + sx * hw * kx, yc + (R - dl) * c, zc + (R - dl) * s)
                         for (sx, kx, dl) in ((-1, 1.0, lip), (-1, 0.72, 0.0), (1, 0.72, 0.0), (1, 1.0, lip))])
        for ra, rb in zip(rows, rows[1:]):
            for j in range(3):
                self.mb.quad2(None, ra[j], ra[j + 1], rb[j + 1], rb[j], color=col)

    def disc(self, y0, y1, zc, r, col, n=8, x=0.0, r1=None, cap_col=None):
        """Короткий цилиндр вдоль машины (фара, глушитель)."""
        r1 = r if r1 is None else r1
        self.loft([self.ring(y0, zc, r, r, n, x), self.ring(y1, zc, r1, r1, n, x)], col, cap_col=cap_col)

    def panel(self, p0, p1, p2, p3, col):
        self.mb.quad2(None, p0, p1, p2, p3, color=col)

    def build(self, name, assets):
        return self.mb.build(name, assets.apply_state)


# ---------------------------------------------------------------------------
# колёса
# ---------------------------------------------------------------------------
def _wheel(R, W, style):
    """Колесо с центром в начале координат, ось — X.

    style: 'cast' — литой диск с пятью спицами, 'wire' — спицованное, 'thin' — велосипедное,
    'solid' — маленькое со сплошным диском, 'fat' — широкое внедорожное."""
    mb = MeshBuilder()
    n = 14 if style in ('thin', 'wire') else 12
    hw = W * 0.5
    if style == 'fat':
        prof = [(-hw, R * 0.70), (-hw * 0.94, R * 0.93), (-hw * 0.5, R), (hw * 0.5, R), (hw * 0.94, R * 0.93), (hw, R * 0.70)]
        ri = R * 0.52
    elif style == 'thin':
        prof = [(-hw, R * 0.935), (-hw * 0.6, R * 0.99), (0.0, R), (hw * 0.6, R * 0.99), (hw, R * 0.935)]
        ri = R * 0.90
    else:
        prof = [(-hw, R * 0.80), (-hw * 0.70, R * 0.955), (0.0, R), (hw * 0.70, R * 0.955), (hw, R * 0.80)]
        ri = R * (0.74 if style == 'wire' else 0.66)
    cs = [(math.cos(i * 2.0 * math.pi / n), math.sin(i * 2.0 * math.pi / n)) for i in range(n + 1)]
    for i in range(n):
        (c0, s0), (c1, s1) = cs[i], cs[i + 1]
        for (xa, ra), (xb, rb) in zip(prof, prof[1:]):
            mb.quad(None, (xa, ra * c0, ra * s0), (xa, ra * c1, ra * s1), (xb, rb * c1, rb * s1), (xb, rb * c0, rb * s0),
                    color=TYRE)
        ro = prof[0][1]
        # боковины шины
        mb.quad(None, (-hw, ro * c0, ro * s0), (-hw, ri * c0, ri * s0), (-hw, ri * c1, ri * s1), (-hw, ro * c1, ro * s1),
                color=TYRE)
        mb.quad(None, (hw, ro * c0, ro * s0), (hw, ro * c1, ro * s1), (hw, ri * c1, ri * s1), (hw, ri * c0, ri * s0),
                color=TYRE)
    if style in ('wire', 'thin'):
        # обод и спицы
        rw = hw * (0.8 if style == 'thin' else 0.62)
        for i in range(n):
            (c0, s0), (c1, s1) = cs[i], cs[i + 1]
            mb.quad(None, (-rw, ri * c0, ri * s0), (rw, ri * c0, ri * s0), (rw, ri * c1, ri * s1), (-rw, ri * c1, ri * s1),
                    color=RIM)
        k = Kit()
        k.mb = mb
        ns = 8 if style == 'thin' else 10
        for i in range(ns):
            a = i * 2.0 * math.pi / ns
            sx = rw * 0.6 * (1 if i % 2 else -1)
            k.tube([(sx, 0.0, 0.0), (0.0, math.cos(a) * ri, math.sin(a) * ri)], 0.0055 if style == 'thin' else 0.008,
                   STEEL, 3, caps=False)
        mb.cylinder_x(None, -rw - 0.02, rw + 0.02, 0.0, 0.0, 0.03 if style == 'thin' else 0.055, 6, RIM if style == 'wire' else DARK,
                      cap_color=DARK)
        if style == 'wire':
            mb.cylinder_x(None, rw + 0.02, rw + 0.03, 0.0, 0.0, R * 0.40, 10, STEEL, cap_color=STEEL)     # тормозной диск
    else:
        xi = hw * (0.55 if style == 'fat' else 0.72)
        face = (0.20, 0.20, 0.22, 1.0)
        mb.cylinder_x(None, -xi, xi, 0.0, 0.0, ri, n, RIM, cap_color=face if style == 'cast' else RIM)
        if style == 'cast':
            for sx in (-1, 1):
                x = sx * (xi + 0.004)
                for i in range(5):
                    a = i * 2.0 * math.pi / 5.0 + 0.3
                    c, s = math.cos(a), math.sin(a)
                    tx, ty = -s * R * 0.085, c * R * 0.085
                    p = [(x, c * R * 0.10 + tx, s * R * 0.10 + ty), (x, c * ri + tx * 0.7, s * ri + ty * 0.7),
                         (x, c * ri - tx * 0.7, s * ri - ty * 0.7), (x, c * R * 0.10 - tx, s * R * 0.10 - ty)]
                    if sx > 0:
                        p = p[::-1]
                    mb.quad(None, p[0], p[1], p[2], p[3], color=RIM)
            mb.cylinder_x(None, xi + 0.012, xi + 0.022, 0.0, 0.0, R * 0.44, 10, STEEL, cap_color=STEEL)       # тормозной диск
        mb.cylinder_x(None, -xi - 0.012, xi + 0.03, 0.0, 0.0, R * 0.16, 6, DARK, cap_color=DARK)
    return mb


def wheel_node(assets, R, W, style):
    key = (round(R, 3), round(W, 3), style)
    np_ = _wheels.get(key)
    if np_ is None:
        np_ = _wheels[key] = _wheel(R, W, style).build('wheel', assets.apply_state)
    return np_


# ---------------------------------------------------------------------------
# общие детали
# ---------------------------------------------------------------------------
def _engine(k, y0, y1, z0, z1, hw, fins=True):
    """Блок двигателя с цилиндром в рёбрах."""
    k.box(-hw, y0, z0, hw, y1, z0 + (z1 - z0) * 0.55, ENGINE)
    ya, yb = y0 + (y1 - y0) * 0.30, y0 + (y1 - y0) * 0.85
    zc = z0 + (z1 - z0) * 0.55
    k.box(-hw * 0.78, ya, zc, hw * 0.78, yb, z1, ENGINE)
    if fins:
        for i in range(3):
            zz = zc + (z1 - zc) * (i + 0.5) / 3.0
            k.box(-hw * 0.92, ya - 0.015, zz - 0.012, hw * 0.92, yb + 0.015, zz + 0.012, FIN)
    k.box(-hw - 0.02, y0 + 0.03, z0 + 0.03, -hw, y0 + (y1 - y0) * 0.6, zc - 0.02, FIN)        # крышка сцепления


def _seat(k, y0, y1, z, hw0, hw1, col=SEAT, x=0.0, th=0.07):
    k.body([(y0, z - th * 0.5, hw0, th * 0.5), ((y0 + y1) * 0.5, z - th * 0.5 - 0.005, (hw0 + hw1) * 0.5 + 0.01, th * 0.5),
            (y1, z - th * 0.5 - 0.012, hw1, th * 0.5)], col, x=x)


def _tank(k, y0, y1, zb, zt, hw, col, x=0.0):
    """Бак-капля: узкий у седла, широкий посередине, сходится к рулевой колонке."""
    h = (zt - zb) * 0.5
    zc = zb + h
    L = y1 - y0
    k.body([(y0, zc - h * 0.25, hw * 0.55, h * 0.62), (y0 + L * 0.30, zc, hw, h), (y0 + L * 0.72, zc + h * 0.06, hw * 0.96, h),
            (y1, zc - h * 0.10, hw * 0.52, h * 0.66)], col, x=x)


def _tail(k, y, z, hw=0.05, x=0.0):
    """Задний фонарь, поворотники и номер."""
    k.box(x - hw, y - 0.02, z - 0.03, x + hw, y, z + 0.03, RED)
    for sx in (-1, 1):
        k.box(x + sx * (hw + 0.07), y - 0.02, z - 0.02, x + sx * (hw + 0.03), y + 0.01, z + 0.02, AMBER)
    k.panel((x - 0.09, y - 0.03, z - 0.21), (x + 0.09, y - 0.03, z - 0.21), (x + 0.09, y - 0.01, z - 0.08),
            (x - 0.09, y - 0.01, z - 0.08), PLATE)


def _pegs(k, g, inner=0.10, col=DARK, x=0.0, board=False):
    fx, fy_, fz = g.foot
    if board:                                       # площадки под всю стопу
        for sx in (-1, 1):
            k.box(x + sx * (fx - 0.08), fy_ - 0.14, fz - 0.03, x + sx * (fx + 0.08), fy_ + 0.16, fz, col)
            k.tube([(x + sx * inner, fy_, fz - 0.015), (x + sx * (fx - 0.08), fy_, fz - 0.015)], 0.015, col, 4)
    else:
        for sx in (-1, 1):
            k.tube([(x + sx * inner, fy_, fz - 0.012), (x + sx * (fx + 0.06), fy_, fz - 0.012)], 0.018, col, 4)


def _swingarm(k, g, yp, zp, hw, col, x=0.0, r=0.028):
    k.pair([(hw, yp, zp), (hw, g.ry, g.rr)], r, col, 4, x=x)


def _mirrors(k, g, col=DARK, stalk=STEEL, x=0.0, up=0.20):
    for sx in (-1, 1):
        a = (x + sx * (g.bar - 0.08), g.gy + 0.01, g.gz)
        b = (x + sx * (g.bar - 0.02), g.gy + 0.03, g.gz + up)
        k.tube([a, b], 0.008, stalk, 3)
        k.box(b[0] - 0.055, b[1] - 0.012, b[2] - 0.035, b[0] + 0.055, b[1] + 0.012, b[2] + 0.035, col)


def _fork(k, g, hw=0.085, leg=STEEL, lower=None, r=0.024, clamp=True):
    """Перья вилки от оси колеса к верху вилки."""
    x = g.x
    ax, top = (0.0, g.fy, g.rf), (0.0, g.cy, g.cz)
    for sx in (-1, 1):
        k.tube([(x + sx * hw, ax[1], ax[2]), (x + sx * hw, top[1], top[2])], r, leg, 5)
        if lower is not None:
            mid = (x + sx * hw, ax[1] + (top[1] - ax[1]) * 0.42, ax[2] + (top[2] - ax[2]) * 0.42)
            k.tube([(x + sx * hw, ax[1], ax[2]), mid], r + 0.012, lower, 5)
    if clamp:
        k.box(x - hw - 0.03, g.cy - 0.035, g.cz - 0.035, x + hw + 0.03, g.cy + 0.035, g.cz + 0.005, DARK)
        dy, dz = g.fy - g.cy, g.rf - g.cz
        t = 0.24
        k.box(x - hw - 0.03, g.cy + dy * t - 0.03, g.cz + dz * t - 0.02, x + hw + 0.03, g.cy + dy * t + 0.03,
              g.cz + dz * t + 0.02, DARK)


def _bars(k, g, style='flat', col=STEEL, r=0.014):
    """Руль от верха вилки к ручкам; ручки стоят там, где у ездока кисти."""
    x = g.x
    for sx in (-1, 1):
        gx = x + sx * g.bar
        if style == 'clipon':
            pts = [(x + sx * 0.085, g.cy, g.cz - 0.01), (gx, g.gy, g.gz)]
        elif style == 'ape':
            pts = [(x + sx * 0.06, g.cy, g.cz), (x + sx * 0.10, g.cy - 0.03, g.gz + 0.03),
                   (x + sx * g.bar * 0.80, g.gy + 0.12, g.gz + 0.03), (gx, g.gy, g.gz)]
        elif style == 'riser':
            pts = [(x + sx * 0.05, g.cy, g.cz), (x + sx * 0.06, g.cy - 0.01, g.gz - 0.03),
                   (x + sx * g.bar * 0.62, g.gy + 0.05, g.gz), (gx, g.gy, g.gz)]
        else:
            pts = [(x + sx * 0.03, g.cy, g.cz + 0.01), (x + sx * g.bar * 0.55, g.cy - 0.01, g.gz), (gx, g.gy, g.gz)]
        k.tube(pts, r, col, 4)
        k.tube([(x + sx * (g.bar - 0.11), pts[-2][1] + (g.gy - pts[-2][1]) * 0.6, g.gz), (gx + sx * 0.01, g.gy, g.gz)],
               r + 0.008, DARK, 5)
    if style == 'riser':
        k.tube([(x - g.bar * 0.55, g.gy + 0.045, g.gz - 0.005), (x + g.bar * 0.55, g.gy + 0.045, g.gz - 0.005)], r * 0.8, col, 4)


def _headlight(k, y, z, r, shell=STEEL, x=0.0, depth=0.12):
    k.disc(y - depth, y, z, r * 0.82, shell, 8, x=x, r1=r)
    k.disc(y, y + 0.012, z, r * 0.9, LAMP, 8, x=x)


# ---------------------------------------------------------------------------
# сами модели
# ---------------------------------------------------------------------------
def _sport(g, paint, p2, k, f):
    sy, sz = g.sy, g.sz
    _engine(k, sy + 0.06, sy + 0.50, 0.27, 0.66, 0.14, fins=False)
    # обтекатель: брюхо, борта и «морда» одной оболочкой
    k.body([(sy + 0.00, 0.36, 0.13, 0.10), (sy + 0.22, 0.42, 0.185, 0.19), (g.cy - 0.06, 0.52, 0.20, 0.27),
            (g.cy + 0.10, 0.62, 0.17, 0.24)], p2, e=0.8)
    k.body([(g.cy - 0.10, g.cz - 0.13, 0.20, 0.17), (g.cy + 0.10, g.cz - 0.14, 0.17, 0.15),
            (g.cy + 0.30, g.cz - 0.19, 0.075, 0.075)], paint, e=0.85, cap_col=LAMP)
    k.panel((-0.13, g.cy + 0.15, g.cz - 0.01), (0.13, g.cy + 0.15, g.cz - 0.01), (0.095, g.cy - 0.03, g.cz + 0.17),
            (-0.095, g.cy - 0.03, g.cz + 0.17), GLASS)
    _tank(k, sy + 0.13, g.cy - 0.10, sz - 0.10, sz + 0.075, 0.165, paint)
    _seat(k, sy - 0.25, sy + 0.15, sz, 0.135, 0.12)
    # хвост задран, под ним фонарь
    k.body([(sy - 0.20, sz - 0.07, 0.135, 0.06), (sy - 0.46, sz + 0.02, 0.11, 0.065), (sy - 0.74, sz + 0.09, 0.045, 0.04)],
           paint, e=0.85)
    k.box(-0.085, sy - 0.50, sz + 0.07, 0.085, sy - 0.27, sz + 0.11, SEAT)
    _tail(k, sy - 0.755, sz + 0.09, 0.04)
    for sx in (-1, 1):
        k.tube([(sx * 0.115, g.cy - 0.05, g.cz - 0.10), (sx * 0.125, sy + 0.02, 0.45)], 0.032, STEEL, 4)     # рама-балка
    _swingarm(k, g, sy + 0.02, 0.44, 0.10, DARK, r=0.03)
    k.fender(g.ry, g.rr, g.rr + 0.04, 55.0, 150.0, g.wr * 0.5 + 0.02, DARK)
    k.tube([(0.14, sy + 0.42, 0.30), (0.17, sy + 0.04, 0.30), (0.19, g.ry + 0.26, 0.43)], 0.034, STEEL, 5)
    k.tube([(0.19, g.ry + 0.26, 0.43), (0.205, g.ry - 0.14, 0.57)], 0.062, STEEL, 6, r1=0.068)
    _pegs(k, g, 0.12)
    for sx in (-1, 1):
        a, b = (sx * 0.17, g.cy + 0.10, g.cz - 0.02), (sx * 0.33, g.cy + 0.04, g.cz + 0.10)
        k.tube([a, b], 0.008, DARK, 3)
        k.box(b[0] - 0.05, b[1] - 0.012, b[2] - 0.03, b[0] + 0.05, b[1] + 0.012, b[2] + 0.03, paint)
        k.box(sx * 0.18, g.cy + 0.16, g.cz - 0.20, sx * 0.20, g.cy + 0.21, g.cz - 0.16, AMBER)
    _fork(f, g, 0.085, STEEL, DARK, 0.025)
    _bars(f, g, 'clipon', DARK)
    f.fender(g.fy, g.rf, g.rf + 0.035, 25.0, 150.0, g.wf * 0.5 + 0.02, paint)
    return dict(head=(0.0, g.cy + 0.31, g.cz - 0.19), tail=(0.0, sy - 0.76, sz + 0.09))


def _vtwin(k, y, z0, x=0.0):
    """Двигатель «вилкой» с рёбрами и круглым воздушным фильтром."""
    k.box(x - 0.14, y - 0.17, z0, x + 0.14, y + 0.17, z0 + 0.22, ENGINE)
    for dy in (-0.11, 0.11):
        top = (x, y + dy * 1.9, z0 + 0.48)
        k.tube([(x, y + dy * 0.6, z0 + 0.20), top], 0.078, FIN, 6)
        k.tube([(top[0], top[1] - dy * 0.1, top[2] - 0.02), (top[0], top[1] + dy * 0.2, top[2] + 0.03)], 0.06, STEEL, 6)
    k.mb.cylinder_x(None, x + 0.14, x + 0.19, y, z0 + 0.36, 0.085, 8, STEEL, cap_color=STEEL)
    k.box(x - 0.17, y - 0.20, z0 + 0.02, x - 0.14, y + 0.12, z0 + 0.20, STEEL)


def _chopper(g, paint, p2, k, f, trike=False):
    sy, sz = g.sy, g.sz
    ey = sy + 0.40
    _vtwin(k, ey, 0.20)
    # рама: хребет от рулевой колонки к седлу, нижняя труба под двигатель
    k.tube([(0, g.cy - 0.03, g.cz - 0.10), (0, sy + 0.26, sz + 0.07), (0, sy - 0.10, sz - 0.08)], 0.028, DARK, 5)
    k.tube([(0, g.cy - 0.02, g.cz - 0.16), (0, ey + 0.26, 0.22), (0, sy + 0.02, 0.19)], 0.026, DARK, 5)
    _tank(k, sy + 0.20, g.cy - 0.12, sz + 0.07, sz + 0.27, 0.155, paint)
    _seat(k, sy - 0.24, sy + 0.17, sz, 0.17, 0.12, th=0.08)
    # выхлоп: две трубы по правому борту, срезанные наискось
    k.tube([(0.12, ey - 0.14, 0.52), (0.17, ey - 0.30, 0.31), (0.19, g.ry - 0.10, 0.29)], 0.034, STEEL, 6)
    k.tube([(0.12, ey + 0.16, 0.52), (0.20, ey + 0.02, 0.24), (0.22, g.ry - 0.24, 0.21)], 0.034, STEEL, 6)
    if not trike:
        k.pair([(0.10, sy - 0.02, 0.32), (0.11, g.ry, g.rr)], 0.026, DARK, 4)
        k.pair([(0.07, sy - 0.14, sz - 0.08), (0.11, g.ry, g.rr)], 0.02, DARK, 4)
        k.fender(g.ry, g.rr, g.rr + 0.045, 40.0, 178.0, g.wr * 0.5 + 0.03, paint)
        k.box(-0.11, sy - 0.50, sz + 0.05, 0.11, sy - 0.24, sz + 0.11, SEAT)                 # подушка пассажира
        k.pair([(0.10, sy - 0.47, sz + 0.04), (0.10, sy - 0.56, sz + 0.50)], 0.012, STEEL, 4)   # дуга за спиной
        k.tube([(-0.10, sy - 0.56, sz + 0.50), (0.10, sy - 0.56, sz + 0.50)], 0.012, STEEL, 4)
        k.box(-0.09, sy - 0.565, sz + 0.26, 0.09, sy - 0.535, sz + 0.44, SEAT)
        _tail(k, g.ry - g.rr - 0.02, g.rr + 0.10, 0.045)
    _pegs(k, g, 0.03, STEEL)
    _fork(f, g, 0.09, STEEL, None, 0.022)
    _bars(f, g, 'ape', STEEL, 0.015)
    _headlight(f, g.cy + 0.14 + (g.fy - g.cy) * 0.12, g.cz - 0.16, 0.085)
    f.fender(g.fy, g.rf, g.rf + 0.035, 60.0, 135.0, g.wf * 0.5 + 0.025, STEEL)
    return dict(head=(0.0, g.cy + 0.22, g.cz - 0.16), tail=(0.0, g.ry - g.rr - 0.03, g.rr + 0.10))


def _trike(g, paint, p2, k, f):
    res = _chopper(g, paint, p2, k, f, trike=True)
    sy, sz, t = g.sy, g.sz, g.K['track']
    # задний мост и кузов-диван между широкими колёсами
    k.tube([(-t, g.ry, g.rr), (t, g.ry, g.rr)], 0.04, DARK, 5)
    k.pair([(0.10, sy - 0.02, 0.30), (0.26, g.ry, g.rr)], 0.028, DARK, 4)
    k.body([(g.ry - 0.40, 0.56, 0.30, 0.10), (g.ry - 0.05, 0.56, 0.33, 0.17), (sy - 0.20, 0.52, 0.22, 0.13)], paint, e=0.8)
    _seat(k, sy - 0.62, sy - 0.22, sz + 0.10, 0.24, 0.20, th=0.09)
    k.box(-0.24, sy - 0.70, sz + 0.08, 0.24, sy - 0.62, sz + 0.42, SEAT)
    for sx in (-1, 1):
        k.fender(g.ry, g.rr, g.rr + 0.05, 20.0, 170.0, g.wr * 0.5 + 0.04, paint, x=sx * t)
        k.box(sx * (t - 0.06), g.ry - g.rr - 0.07, g.rr + 0.04, sx * (t + 0.06), g.ry - g.rr - 0.05, g.rr + 0.10, RED)
    k.panel((-0.09, g.ry - 0.41, 0.48), (0.09, g.ry - 0.41, 0.48), (0.09, g.ry - 0.41, 0.60), (-0.09, g.ry - 0.41, 0.60), PLATE)
    res['tail'] = (0.0, g.ry - g.rr - 0.07, g.rr + 0.08)
    return res


def _scooter(g, paint, p2, k, f, box=False):
    sy, sz = g.sy, g.sz
    fl = g.foot[2]
    # площадка под ноги и щиток
    k.box(-0.19, sy + 0.16, fl - 0.04, 0.19, g.cy + 0.02, fl, DARK)
    k.box(-0.13, sy + 0.10, fl - 0.11, 0.13, g.cy - 0.04, fl - 0.04, ENGINE)
    k.loft([Kit.ring_z(fl - 0.02, g.cy + 0.06, 0.045, 0.20, 8), Kit.ring_z(fl + 0.34, g.cy + 0.02, 0.05, 0.21, 8),
            Kit.ring_z(g.cz - 0.14, g.cy - 0.03, 0.055, 0.15, 8)], paint)
    k.box(-0.15, g.cy - 0.04, fl + 0.10, 0.15, g.cy - 0.02, fl + 0.30, p2)                   # бардачок
    # корпус под седлом сходится к хвосту
    k.body([(g.ry - 0.30, sz - 0.14, 0.10, 0.09), (g.ry + 0.04, sz - 0.21, 0.20, 0.17), (sy + 0.10, sz - 0.25, 0.205, 0.20),
            (sy + 0.22, sz - 0.30, 0.17, 0.15)], paint, e=0.8)
    _seat(k, sy - 0.36, sy + 0.17, sz, 0.155, 0.13, th=0.08)
    k.tube([(-0.13, g.ry - 0.20, sz - 0.02), (-0.14, g.ry - 0.36, sz + 0.03), (0.14, g.ry - 0.36, sz + 0.03),
            (0.13, g.ry - 0.20, sz - 0.02)], 0.012, STEEL, 4)
    _tail(k, g.ry - 0.31, sz - 0.14, 0.05)
    k.tube([(0.20, g.ry + 0.30, 0.25), (0.22, g.ry - 0.16, 0.30)], 0.05, STEEL, 6, r1=0.055)
    k.box(0.10, g.ry - 0.05, 0.14, 0.19, g.ry + 0.26, 0.34, ENGINE)
    # перед: колонка, рычаг, крыло, руль с фарой
    f.tube([(0, g.fy, g.rf + 0.02), (0, g.cy, g.cz)], 0.028, DARK, 5)
    f.tube([(0.075, g.fy, g.rf), (0.06, g.fy - 0.03, g.rf + 0.26)], 0.022, STEEL, 4)
    f.fender(g.fy, g.rf, g.rf + 0.04, 15.0, 165.0, g.wf * 0.5 + 0.035, paint)
    f.body([(g.cy - 0.10, g.cz + 0.00, 0.15, 0.075), (g.cy + 0.06, g.cz - 0.02, 0.12, 0.085), (g.cy + 0.13, g.cz - 0.04, 0.07, 0.06)],
           paint, e=0.8, cap_col=LAMP)
    _bars(f, g, 'flat', DARK, 0.016)
    _mirrors(f, g, DARK, STEEL)
    if box:
        # короб доставки на багажнике: яркий, с тёмной крышкой и полосой
        y0, y1, z0 = g.ry - 0.30, g.ry + 0.14, sz + 0.02
        k.box(-0.22, y0, z0, 0.22, y1, z0 + 0.40, COURIER)
        k.box(-0.225, y0 - 0.005, z0 + 0.36, 0.225, y1 + 0.005, z0 + 0.42, DARK)
        for sx in (-1, 1):
            k.box(sx * 0.221, y0 + 0.04, z0 + 0.14, sx * 0.224, y1 - 0.04, z0 + 0.24, WHITE)
        k.box(-0.16, y0 - 0.004, z0 + 0.12, 0.16, y0, z0 + 0.26, WHITE)
        k.pair([(0.16, y0 + 0.06, z0), (0.13, g.ry - 0.10, sz - 0.10)], 0.012, STEEL, 3)
    return dict(head=(0.0, g.cy + 0.14, g.cz - 0.04), tail=(0.0, g.ry - 0.32, sz - 0.14))


def _cargo(g, paint, p2, k, f):
    """Грузовой мотороллер: перед от скутера, сзади — кузов между двумя колёсами."""
    sy, sz, t = g.sy, g.sz, g.K['track']
    fl = g.foot[2]
    k.box(-0.20, sy + 0.10, fl - 0.04, 0.20, g.cy + 0.02, fl, DARK)                          # площадка под ноги
    k.box(-0.13, sy - 0.10, fl - 0.12, 0.13, g.cy - 0.04, fl - 0.04, ENGINE)
    k.loft([Kit.ring_z(fl - 0.02, g.cy + 0.06, 0.045, 0.21, 8), Kit.ring_z(fl + 0.36, g.cy + 0.02, 0.05, 0.22, 8),
            Kit.ring_z(g.cz - 0.14, g.cy - 0.03, 0.055, 0.15, 8)], paint)                    # щиток
    # тумба с двигателем под седлом
    k.body([(sy - 0.30, sz - 0.24, 0.20, 0.19), (sy + 0.06, sz - 0.24, 0.21, 0.20), (sy + 0.22, sz - 0.30, 0.17, 0.15)],
           paint, e=0.75)
    _seat(k, sy - 0.26, sy + 0.18, sz, 0.17, 0.14, th=0.08)
    # кузов: пол, борта, стойки; в кузове — пара ящиков
    y0, y1 = g.ry - 0.40, sy - 0.32
    z0, z1 = g.rr + 0.27, g.rr + 0.55
    k.box(-t - 0.05, y0, z0 - 0.04, t + 0.05, y1, z0, DARK)
    for sx in (-1, 1):
        k.box(sx * (t + 0.05), y0, z0, sx * (t + 0.02), y1, z1, p2)
        k.box(sx * (t + 0.055), y0, z1 - 0.03, sx * (t + 0.015), y1, z1, paint)
        k.box(sx * (t - 0.05), g.ry - g.rr - 0.02, z0 - 0.16, sx * (t + 0.05), g.ry - g.rr - 0.045, z0 - 0.07, RED)
        k.tube([(sx * 0.10, sy - 0.20, 0.30), (sx * (t - 0.10), g.ry, g.rr)], 0.026, DARK, 4)
    k.box(-t - 0.05, y0, z0, t + 0.05, y0 + 0.03, z1, p2)
    k.box(-t - 0.05, y1 - 0.03, z0, t + 0.05, y1, z1 + 0.10, p2)
    k.box(-t - 0.055, y1 - 0.035, z1 + 0.07, t + 0.055, y1 + 0.005, z1 + 0.10, paint)
    k.tube([(-t, g.ry, g.rr), (t, g.ry, g.rr)], 0.035, DARK, 5)                              # мост
    k.box(-0.30, y0 + 0.10, z0, -0.02, y0 + 0.46, z0 + 0.24, CRATE)
    k.box(0.04, y0 + 0.16, z0, 0.34, y0 + 0.50, z0 + 0.20, CRATE2)
    k.panel((-0.09, y0 - 0.005, z0 + 0.03), (0.09, y0 - 0.005, z0 + 0.03), (0.09, y0 - 0.005, z0 + 0.15),
            (-0.09, y0 - 0.005, z0 + 0.15), PLATE)
    # перед: колонка, рычаг, крыло, руль с фарой
    f.tube([(0, g.fy, g.rf + 0.02), (0, g.cy, g.cz)], 0.028, DARK, 5)
    f.tube([(0.075, g.fy, g.rf), (0.06, g.fy - 0.03, g.rf + 0.26)], 0.022, STEEL, 4)
    f.fender(g.fy, g.rf, g.rf + 0.04, 15.0, 165.0, g.wf * 0.5 + 0.035, paint)
    f.body([(g.cy - 0.10, g.cz + 0.00, 0.15, 0.075), (g.cy + 0.06, g.cz - 0.02, 0.12, 0.085), (g.cy + 0.13, g.cz - 0.04, 0.07, 0.06)],
           paint, e=0.8, cap_col=LAMP)
    _bars(f, g, 'flat', DARK, 0.016)
    _mirrors(f, g, DARK, STEEL)
    return dict(head=(0.0, g.cy + 0.14, g.cz - 0.04), tail=(0.0, g.ry - g.rr - 0.05, z0 - 0.11))


def _wheel_ring(k, c, r, tilt, col, x=0.0, n=10, th=0.016):
    """Рулевое колесо: кольцо радиуса r с центром c, плоскость наклонена назад на tilt градусов."""
    ca, sa = math.cos(math.radians(tilt)), math.sin(math.radians(tilt))
    pts = []
    for i in range(n + 1):
        a = i * 2.0 * math.pi / n
        u, v = math.cos(a) * r, math.sin(a) * r             # u — вбок, v — «вверх» в плоскости колеса
        pts.append((x + c[0] + u, c[1] - v * sa, c[2] + v * ca))
    k.tube(pts, th, col, 4, caps=False)
    for a in (0.0, math.pi, -math.pi / 2):
        u, v = math.cos(a) * r, math.sin(a) * r
        k.tube([(x + c[0], c[1], c[2]), (x + c[0] + u, c[1] - v * sa, c[2] + v * ca)], th * 0.8, col, 3)


def _kart(g, paint, p2, k, f):
    """Карт: рама-поддон, сиденье-ковш, мотор сбоку, обтекатели."""
    sy, sz, t = g.sy, g.sz, g.K['track']
    fl = g.foot[2]
    k.box(-0.24, g.ry + 0.06, fl - 0.025, 0.24, g.fy + 0.16, fl, DARK)                       # поддон
    for sx in (-1, 1):
        k.tube([(sx * 0.25, g.ry + 0.02, fl + 0.03), (sx * 0.25, g.fy + 0.10, fl + 0.03)], 0.02, STEEL, 4)
        # боковые обтекатели между колёсами
        k.body([(g.ry + 0.26, fl + 0.09, 0.085, 0.07), (sy + 0.20, fl + 0.10, 0.10, 0.08), (g.fy - 0.22, fl + 0.09, 0.085, 0.07)],
               paint, x=sx * (t - 0.06), e=0.8)
        k.tube([(sx * 0.20, g.fy - 0.02, fl + 0.05), (sx * (t - 0.07), g.fy, g.rf)], 0.016, STEEL, 4)     # рычаги
    k.tube([(-t + 0.06, g.ry, g.rr), (t - 0.06, g.ry, g.rr)], 0.022, STEEL, 5)               # задняя ось
    # нос с номером и передний бампер
    k.body([(g.fy - 0.06, fl + 0.13, 0.19, 0.10), (g.fy + 0.16, fl + 0.11, 0.17, 0.08), (g.fy + 0.30, fl + 0.07, 0.10, 0.04)],
           paint, e=0.8)
    k.panel((-0.09, g.fy - 0.02, fl + 0.235), (0.09, g.fy - 0.02, fl + 0.235), (0.08, g.fy + 0.14, fl + 0.195),
            (-0.08, g.fy + 0.14, fl + 0.195), WHITE)
    k.tube([(-t + 0.02, g.fy + 0.20, fl + 0.05), (-0.20, g.fy + 0.31, fl + 0.05), (0.20, g.fy + 0.31, fl + 0.05),
            (t - 0.02, g.fy + 0.20, fl + 0.05)], 0.02, DARK, 4)
    # сиденье-ковш
    k.body([(sy - 0.20, sz - 0.03, 0.20, 0.035), (sy + 0.16, sz - 0.05, 0.18, 0.035)], SEAT, n=6)
    k.body([(sy - 0.24, sz + 0.20, 0.20, 0.24), (sy - 0.17, sz + 0.18, 0.21, 0.22)], SEAT, n=6)
    for sx in (-1, 1):
        k.box(sx * 0.19, sy - 0.20, sz - 0.06, sx * 0.215, sy + 0.10, sz + 0.10, SEAT)
        k.tube([(sx * 0.12, sy - 0.10, sz - 0.07), (sx * 0.14, sy - 0.10, fl)], 0.014, STEEL, 3)
    # мотор справа от сиденья, бак под рулём, глушитель, задний бампер
    k.box(0.24, sy - 0.26, fl + 0.02, 0.40, sy + 0.02, fl + 0.20, ENGINE)
    k.tube([(0.32, sy - 0.12, fl + 0.20), (0.32, sy - 0.16, fl + 0.32)], 0.05, FIN, 6)
    k.tube([(0.36, sy - 0.24, fl + 0.12), (0.36, g.ry - 0.06, fl + 0.14)], 0.035, STEEL, 6)
    k.box(-0.40, sy - 0.24, fl + 0.02, -0.25, sy - 0.02, fl + 0.14, DARK)
    k.body([(sy + 0.24, fl + 0.13, 0.10, 0.07), (sy + 0.42, fl + 0.12, 0.085, 0.06)], p2, n=6)
    k.tube([(-t + 0.04, g.ry - 0.20, g.rr + 0.02), (t - 0.04, g.ry - 0.20, g.rr + 0.02)], 0.022, DARK, 4)
    for sx in (-1, 1):
        k.tube([(sx * 0.22, g.ry + 0.04, fl + 0.03), (sx * 0.30, g.ry - 0.20, g.rr + 0.02)], 0.016, DARK, 3)
    k.box(-0.06, g.ry - 0.225, g.rr - 0.01, 0.06, g.ry - 0.215, g.rr + 0.05, RED)
    # рулевая колонка и руль — там, где у ездока кисти
    k.tube([(0, g.fy - 0.04, fl + 0.06), (0, g.gy + 0.03, g.gz - 0.03)], 0.016, STEEL, 4)
    _wheel_ring(k, (0.0, g.gy, g.gz), g.bar - 0.05, 62.0, DARK, n=8, th=0.018)
    for sx in (-1, 1):                                                                       # педали
        k.box(sx * 0.16, g.foot[1] + 0.13, fl, sx * 0.24, g.foot[1] + 0.15, fl + 0.12, STEEL)
    return dict(head=(0.0, g.fy + 0.28, fl + 0.08), tail=(0.0, g.ry - 0.23, g.rr + 0.02))


def _caddy(g, paint, p2, k, f):
    """Гольф-кар: открытая тележка с диваном на двоих и крышей на стойках."""
    sy, sz, t, x = g.sy, g.sz, g.K['track'], g.x
    fl = g.foot[2]
    hw = t + 0.07
    cream = (0.90, 0.88, 0.80, 1.0)
    k.box(-hw, g.ry - 0.30, fl - 0.05, hw, g.fy + 0.26, fl, DARK)                            # пол
    # капот со скруглённым носом и фарами
    k.body([(g.fy - 0.14, fl + 0.21, hw, 0.21), (g.fy + 0.16, fl + 0.19, hw - 0.01, 0.19), (g.fy + 0.34, fl + 0.13, hw - 0.10, 0.12)],
           paint, e=0.7)
    k.box(-hw + 0.02, g.fy - 0.20, fl + 0.30, hw - 0.02, g.fy - 0.13, fl + 0.50, DARK)       # панель приборов
    for sx in (-1, 1):
        k.box(sx * (hw - 0.26), g.fy + 0.335, fl + 0.14, sx * (hw - 0.12), g.fy + 0.35, fl + 0.24, LAMP)
        k.box(sx * (hw - 0.02), g.ry - 0.305, fl + 0.22, sx * (hw - 0.16), g.ry - 0.29, fl + 0.30, RED)
    k.tube([(-hw + 0.04, g.fy + 0.36, fl + 0.02), (hw - 0.04, g.fy + 0.36, fl + 0.02)], 0.03, DARK, 4)      # бампер
    # диван и тумба под ним
    k.box(-hw + 0.03, sy - 0.26, fl, hw - 0.03, sy + 0.16, sz - 0.09, paint)
    k.body([(sy - 0.24, sz - 0.045, hw - 0.05, 0.045), (sy + 0.20, sz - 0.055, hw - 0.05, 0.045)], cream, n=6, e=0.6)
    k.body([(sy - 0.30, sz + 0.22, hw - 0.05, 0.20), (sy - 0.22, sz + 0.22, hw - 0.05, 0.20)], cream, n=6, e=0.6)
    # задняя площадка под сумки
    k.body([(g.ry - 0.30, fl + 0.18, hw, 0.18), (sy - 0.30, fl + 0.20, hw, 0.20)], paint, e=0.7)
    k.box(-hw + 0.06, g.ry - 0.24, fl + 0.38, hw - 0.06, sy - 0.36, fl + 0.40, DARK)
    for sx in (-0.22, 0.20):                                                                 # сумки с клюшками
        k.tube([(sx, g.ry - 0.04, fl + 0.40), (sx, g.ry - 0.12, fl + 1.02)], 0.085, p2 if sx < 0 else CRATE, 6)
        for dx in (-0.03, 0.03):
            k.tube([(sx + dx, g.ry - 0.12, fl + 1.02), (sx + dx * 1.6, g.ry - 0.14, fl + 1.16)], 0.008, STEEL, 3)
    # крыша на четырёх стойках
    top = g.pz + 0.92
    for sx in (-1, 1):
        k.tube([(sx * (hw - 0.05), g.fy - 0.16, fl + 0.44), (sx * (hw - 0.07), g.fy - 0.30, top)], 0.018, DARK, 4)
        k.tube([(sx * (hw - 0.05), sy - 0.34, fl + 0.40), (sx * (hw - 0.07), sy - 0.38, top)], 0.018, DARK, 4)
    k.body([(sy - 0.52, top + 0.02, hw - 0.01, 0.03), (g.fy - 0.20, top + 0.02, hw - 0.01, 0.03)], cream, n=6, e=0.5)
    # руль перед водителем
    k.tube([(x, g.fy - 0.14, fl + 0.44), (x, g.gy + 0.03, g.gz - 0.04)], 0.018, DARK, 4)
    _wheel_ring(k, (0.0, g.gy, g.gz), g.bar, 55.0, DARK, x=x, n=10, th=0.016)
    return dict(head=(0.0, g.fy + 0.35, fl + 0.19), tail=(0.0, g.ry - 0.30, fl + 0.26),
                seat2=(-x, sy, g.pz, 'bench'))


def _dirt(g, paint, p2, k, f):
    sy, sz = g.sy, g.sz
    _engine(k, sy + 0.10, sy + 0.46, 0.36, 0.68, 0.11)
    k.box(-0.13, sy + 0.04, 0.31, 0.13, sy + 0.52, 0.34, STEEL)                               # защита картера
    k.tube([(0, g.cy - 0.03, g.cz - 0.14), (0, sy + 0.56, 0.38)], 0.026, DARK, 5)
    k.tube([(0, g.cy - 0.03, g.cz - 0.10), (0, sy + 0.16, sz - 0.07), (0, sy - 0.30, sz - 0.09)], 0.026, DARK, 5)
    # бак с накладками, длинное плоское седло, высокое заднее крыло
    k.body([(sy + 0.13, sz - 0.03, 0.10, 0.06), (sy + 0.33, sz - 0.02, 0.15, 0.10), (g.cy - 0.13, sz - 0.05, 0.165, 0.13),
            (g.cy - 0.03, sz - 0.14, 0.085, 0.08)], paint, e=0.85)
    _seat(k, sy - 0.50, sy + 0.17, sz, 0.09, 0.10)
    k.body([(g.ry - 0.40, sz + 0.03, 0.07, 0.012), (sy - 0.42, sz - 0.07, 0.10, 0.025)], paint, n=4)
    for sx in (-1, 1):
        k.box(sx * 0.105, sy - 0.44, sz - 0.27, sx * 0.125, sy - 0.12, sz - 0.07, WHITE)     # номерные щитки
    k.box(-0.04, g.ry - 0.41, sz - 0.01, 0.04, g.ry - 0.39, sz + 0.04, RED)
    k.tube([(0.10, sy + 0.44, 0.56), (0.14, sy + 0.18, 0.72), (0.15, sy - 0.20, sz - 0.12)], 0.028, STEEL, 5)
    k.tube([(0.15, sy - 0.20, sz - 0.12), (0.155, sy - 0.48, sz - 0.07)], 0.048, STEEL, 6)
    _swingarm(k, g, sy + 0.02, 0.46, 0.075, STEEL, r=0.024)
    k.tube([(0, sy - 0.02, sz - 0.12), (0, g.ry + 0.26, g.rr + 0.10)], 0.03, AMBER, 5)        # амортизатор
    _pegs(k, g, 0.10, STEEL)
    _fork(f, g, 0.09, STEEL, DARK, 0.022)
    _bars(f, g, 'riser', STEEL, 0.014)
    f.body([(g.fy - 0.24, g.rf + 0.31, 0.085, 0.014), (g.fy + 0.40, g.rf + 0.27, 0.07, 0.012)], paint, n=4)   # высокое крыло
    f.box(g.x - 0.10, g.cy + 0.035, g.cz - 0.24, g.x + 0.10, g.cy + 0.055, g.cz - 0.02, WHITE)
    f.box(g.x - 0.05, g.cy + 0.055, g.cz - 0.20, g.x + 0.05, g.cy + 0.062, g.cz - 0.10, LAMP)
    return dict(head=(0.0, g.cy + 0.07, g.cz - 0.15), tail=(0.0, g.ry - 0.41, sz + 0.02))


def _pedals(k, g, bb, col=STEEL, x=0.0):
    """Каретка, шатуны и широкие педали — под стопы ездока."""
    fx = g.foot[0]
    k.mb.cylinder_x(None, x + 0.045, x + 0.055, bb[1], bb[2], 0.085, 8, col, cap_color=col)   # звёздочка
    for sx, dy in ((-1, -0.15), (1, 0.15)):
        k.tube([(x + sx * 0.07, bb[1], bb[2]), (x + sx * 0.09, bb[1] + dy, bb[2])], 0.011, col, 4)
        k.box(x + sx * 0.09, bb[1] + dy - 0.05, bb[2] - 0.012, x + sx * (fx + 0.07), bb[1] + dy + 0.05, bb[2] + 0.012, DARK)


def _bicycle(g, paint, p2, k, f, bmx=False):
    sy, sz = g.sy, g.sz
    fx, fy_, fz = g.foot
    bb = (0.0, fy_, fz - 0.02)                                                              # каретка — под стопами
    head = (0.0, g.cy, g.cz - (0.10 if not bmx else 0.26))
    head_lo = (0.0, g.cy + 0.05, head[2] - 0.16)
    st = (0.0, sy - 0.04, sz - 0.05)
    r = 0.019 if not bmx else 0.022
    k.tube([head, st], r, paint, 5)                                                         # верхняя труба
    k.tube([head_lo, bb], r + 0.003, paint, 5)                                              # нижняя
    k.tube([st, bb], r, paint, 5)                                                           # подседельная
    k.tube([head, head_lo], r + 0.006, paint, 5)
    k.pair([(0.02, bb[1], bb[2]), (0.06, g.ry, g.rr)], 0.012, paint, 4)
    k.pair([(0.02, st[1], st[2] - 0.04), (0.06, g.ry, g.rr)], 0.011, paint, 4)
    k.tube([(0, st[1], st[2]), (0, sy - 0.02, sz - 0.02)], 0.014, STEEL, 4)
    k.body([(sy - 0.16, sz - 0.02, 0.075, 0.022), (sy + 0.02, sz - 0.022, 0.06, 0.022), (sy + 0.13, sz - 0.03, 0.025, 0.018)], SEAT, n=6)
    _pedals(k, g, bb)
    if not bmx:
        k.fender(g.ry, g.rr, g.rr + 0.025, 70.0, 185.0, 0.035, STEEL, lip=0.012)
        k.box(-0.025, g.ry - g.rr - 0.045, g.rr + 0.02, 0.025, g.ry - g.rr - 0.035, g.rr + 0.07, RED)
        # багажник
        k.pair([(0.05, g.ry + 0.30, g.rr + 0.38), (0.05, g.ry - 0.20, g.rr + 0.38)], 0.008, STEEL, 3)
        k.pair([(0.05, g.ry - 0.10, g.rr + 0.38), (0.06, g.ry, g.rr)], 0.007, STEEL, 3)
    else:
        k.pair([(0.07, g.ry, g.rr), (0.16, g.ry, g.rr)], 0.02, STEEL, 5)                     # пеги
    # вилка и руль
    f.pair([(0.05, g.fy, g.rf), (0.035, head_lo[1], head_lo[2])], 0.013, paint if bmx else STEEL, 4, x=g.x)
    f.tube([(g.x, head[1], head[2]), (g.x, g.cy - 0.02, g.cz)], 0.014, STEEL, 4)
    if bmx:
        f.pair([(0.03, g.cy - 0.02, g.cz), (0.14, g.cy - 0.04, g.gz - 0.02), (g.bar, g.gy, g.gz)], 0.013, STEEL, 4, x=g.x)
        f.tube([(g.x - 0.13, g.cy - 0.04, g.gz - 0.07), (g.x + 0.13, g.cy - 0.04, g.gz - 0.07)], 0.011, STEEL, 4)
        f.pair([(0.07, g.fy, g.rf), (0.16, g.fy, g.rf)], 0.02, STEEL, 5, x=g.x)
    else:
        f.pair([(0.02, g.cy - 0.02, g.cz), (g.bar * 0.6, g.cy - 0.02, g.gz), (g.bar, g.gy, g.gz)], 0.012, STEEL, 4, x=g.x)
        f.fender(g.fy, g.rf, g.rf + 0.025, 50.0, 150.0, 0.035, STEEL, lip=0.012)
        f.box(g.x - 0.035, g.cy + 0.03, g.cz - 0.10, g.x + 0.035, g.cy + 0.07, g.cz - 0.03, DARK)
        f.box(g.x - 0.028, g.cy + 0.07, g.cz - 0.092, g.x + 0.028, g.cy + 0.076, g.cz - 0.038, LAMP)
    for sx in (-1, 1):
        f.tube([(g.x + sx * (g.bar - 0.10), g.gy + 0.012, g.gz), (g.x + sx * (g.bar + 0.01), g.gy, g.gz)], 0.019, DARK, 5)
    return dict(head=(0.0, g.cy + 0.08, g.cz - 0.06), tail=(0.0, g.ry - g.rr - 0.04, g.rr + 0.05))


def _moped(g, paint, p2, k, f):
    sy, sz = g.sy, g.sz
    fx, fy_, fz = g.foot
    bb = (0.0, fy_, fz - 0.02)
    # рама из труб, маленький бак на верхней трубе, моторчик у каретки
    k.tube([(0, g.cy - 0.02, g.cz - 0.12), (0, sy + 0.16, sz - 0.10), (0, sy - 0.20, sz - 0.07)], 0.026, paint, 5)
    k.tube([(0, g.cy, g.cz - 0.20), bb], 0.026, paint, 5)
    k.tube([(0, sy - 0.02, sz - 0.07), bb], 0.022, paint, 5)
    _tank(k, sy + 0.20, g.cy - 0.10, sz - 0.07, sz + 0.07, 0.095, paint)
    k.box(-0.075, bb[1] - 0.02, bb[2] - 0.07, 0.075, bb[1] + 0.20, bb[2] + 0.07, ENGINE)
    k.tube([(0, bb[1] + 0.12, bb[2] + 0.05), (0, bb[1] + 0.25, bb[2] + 0.20)], 0.055, FIN, 6)
    k.tube([(0.07, bb[1] + 0.20, bb[2] + 0.12), (0.10, bb[1] - 0.05, bb[2] - 0.05), (0.11, g.ry + 0.05, g.rr - 0.02)], 0.018, STEEL, 4)
    k.tube([(0.11, g.ry + 0.30, g.rr - 0.04), (0.115, g.ry - 0.05, g.rr - 0.01)], 0.035, STEEL, 6)
    _pedals(k, g, bb)
    _seat(k, sy - 0.34, sy + 0.16, sz, 0.10, 0.09, th=0.06)
    k.pair([(0.06, sy - 0.10, sz - 0.08), (0.07, g.ry, g.rr)], 0.014, STEEL, 4)             # амортизаторы
    k.pair([(0.03, bb[1], bb[2]), (0.07, g.ry, g.rr)], 0.014, paint, 4)
    k.fender(g.ry, g.rr, g.rr + 0.03, 40.0, 185.0, g.wr * 0.5 + 0.03, paint, lip=0.02)
    k.pair([(0.07, sy - 0.30, sz - 0.03), (0.07, g.ry - 0.24, sz - 0.03)], 0.009, STEEL, 3)  # багажник
    k.tube([(-0.07, g.ry - 0.24, sz - 0.03), (0.07, g.ry - 0.24, sz - 0.03)], 0.009, STEEL, 3)
    k.box(-0.07, bb[1] - 0.05, bb[2] + 0.03, -0.055, g.ry + 0.10, bb[2] + 0.11, paint)       # кожух цепи
    _tail(k, g.ry - g.rr - 0.035, g.rr + 0.12, 0.035)
    _fork(f, g, 0.065, STEEL, None, 0.016)
    _bars(f, g, 'riser', STEEL, 0.012)
    f.fender(g.fy, g.rf, g.rf + 0.03, 40.0, 160.0, g.wf * 0.5 + 0.03, paint, lip=0.02)
    _headlight(f, g.cy + 0.13, g.cz - 0.12, 0.07, STEEL, x=g.x, depth=0.10)
    return dict(head=(0.0, g.cy + 0.15, g.cz - 0.12), tail=(0.0, g.ry - g.rr - 0.04, g.rr + 0.12))


def _tourer(g, paint, p2, k, f, police=False):
    sy, sz = g.sy, g.sz
    body = WHITE if police else paint
    trim = BLUE if police else p2
    _engine(k, sy + 0.08, sy + 0.56, 0.24, 0.62, 0.15)
    for sx in (-1, 1):                                                                      # дуги безопасности
        k.tube([(sx * 0.15, sy + 0.56, 0.56), (sx * 0.29, sy + 0.46, 0.44), (sx * 0.15, sy + 0.36, 0.28)], 0.015, STEEL, 4)
    k.tube([(0, g.cy - 0.03, g.cz - 0.12), (0, sy + 0.20, sz + 0.02), (0, sy - 0.30, sz - 0.08)], 0.03, DARK, 5)
    _tank(k, sy + 0.17, g.cy - 0.10, sz - 0.02, sz + 0.22, 0.175, body)
    # большой обтекатель с высоким стеклом
    k.body([(g.cy - 0.16, g.cz - 0.20, 0.27, 0.21), (g.cy + 0.08, g.cz - 0.20, 0.25, 0.19), (g.cy + 0.26, g.cz - 0.24, 0.17, 0.14),
            (g.cy + 0.36, g.cz - 0.27, 0.08, 0.075)], body, e=0.8, cap_col=LAMP)
    k.panel((-0.21, g.cy + 0.20, g.cz - 0.05), (0.21, g.cy + 0.20, g.cz - 0.05), (0.15, g.cy + 0.02, g.cz + 0.33),
            (-0.15, g.cy + 0.02, g.cz + 0.33), GLASS)
    for sx in (-1, 1):
        k.box(sx * 0.255, g.cy - 0.14, g.cz - 0.23, sx * 0.275, g.cy + 0.10, g.cz - 0.18, trim)
        b = (sx * 0.34, g.cy + 0.06, g.cz + 0.03)
        k.tube([(sx * 0.25, g.cy + 0.08, g.cz - 0.06), b], 0.009, DARK, 3)
        k.box(b[0] - 0.055, b[1] - 0.012, b[2] - 0.035, b[0] + 0.055, b[1] + 0.012, b[2] + 0.035, body)
    _seat(k, sy - 0.24, sy + 0.17, sz, 0.17, 0.13, th=0.09)
    _swingarm(k, g, sy + 0.02, 0.40, 0.10, DARK, r=0.03)
    k.fender(g.ry, g.rr, g.rr + 0.045, 45.0, 175.0, g.wr * 0.5 + 0.03, body)
    # кофры по бокам и верхний за седлом
    for sx in (-1, 1):
        k.box(sx * 0.16, g.ry - 0.20, g.rr + 0.02, sx * 0.37, g.ry + 0.34, g.rr + 0.36, body)
        k.box(sx * 0.372, g.ry - 0.20, g.rr + 0.17, sx * 0.378, g.ry + 0.34, g.rr + 0.22, trim)
    for sx in (-1, 1):
        k.tube([(sx * 0.16, sy + 0.40, 0.30), (sx * 0.19, sy - 0.10, 0.27), (sx * 0.20, g.ry - 0.30, 0.30)], 0.036, STEEL, 5)
    _pegs(k, g, 0.12, DARK, board=True)
    if police:
        k.box(-0.14, sy - 0.62, sz + 0.02, 0.14, sy - 0.28, sz + 0.24, WHITE)                # ящик с рацией
        k.tube([(0.10, sy - 0.58, sz + 0.24), (0.10, sy - 0.60, sz + 0.84)], 0.006, DARK, 3)
        for sx, col in ((-1, RED), (1, BLUE)):                                              # маячки на штангах и в обтекателе
            k.tube([(sx * 0.20, g.ry - 0.12, g.rr + 0.36), (sx * 0.20, g.ry - 0.14, sz + 0.44)], 0.012, STEEL, 4)
            k.box(sx * 0.16, g.ry - 0.18, sz + 0.44, sx * 0.24, g.ry - 0.10, sz + 0.54, col)
            k.box(sx * 0.13, g.cy + 0.30, g.cz - 0.19, sx * 0.21, g.cy + 0.33, g.cz - 0.13, col)
    else:
        k.box(-0.13, sy - 0.52, sz + 0.05, 0.13, sy - 0.25, sz + 0.12, SEAT)                 # место пассажира
        k.box(-0.20, sy - 0.86, sz + 0.10, 0.20, sy - 0.54, sz + 0.40, body)                 # верхний кофр
        k.box(-0.16, sy - 0.545, sz + 0.14, 0.16, sy - 0.525, sz + 0.36, SEAT)               # спинка
        k.box(-0.203, sy - 0.86, sz + 0.24, 0.203, sy - 0.54, sz + 0.28, trim)
    _tail(k, g.ry - g.rr - 0.06, g.rr + 0.16, 0.06)
    _fork(f, g, 0.09, STEEL, DARK, 0.026)
    _bars(f, g, 'riser', STEEL, 0.015)
    f.fender(g.fy, g.rf, g.rf + 0.04, 20.0, 160.0, g.wf * 0.5 + 0.03, body)
    return dict(head=(0.0, g.cy + 0.37, g.cz - 0.27), tail=(0.0, g.ry - g.rr - 0.07, g.rr + 0.16),
                siren=[(-0.20, g.ry - 0.14, sz + 0.56), (0.20, g.ry - 0.14, sz + 0.56)] if police else None)


def _quad(g, paint, p2, k, f):
    sy, sz, t = g.sy, g.sz, g.K['track']
    _engine(k, sy - 0.10, sy + 0.42, 0.30, 0.60, 0.17, fins=False)
    k.box(-0.20, g.ry - 0.10, 0.26, 0.20, g.fy + 0.12, 0.31, DARK)                           # рама-поддон
    # «морда», бак, хвост
    k.body([(sy + 0.22, sz - 0.07, 0.15, 0.10), (g.cy - 0.10, sz - 0.03, 0.22, 0.14), (g.fy + 0.06, sz - 0.12, 0.21, 0.12),
            (g.fy + 0.30, sz - 0.21, 0.15, 0.07)], paint, e=0.8)
    k.body([(g.ry - 0.34, sz - 0.12, 0.17, 0.07), (g.ry + 0.04, sz - 0.11, 0.21, 0.10), (sy - 0.18, sz - 0.13, 0.19, 0.10)],
           paint, e=0.8)
    _seat(k, sy - 0.40, sy + 0.24, sz, 0.17, 0.13, th=0.09)
    for sx in (-1, 1):
        k.box(sx * 0.07, g.fy + 0.30, sz - 0.24, sx * 0.15, g.fy + 0.315, sz - 0.17, LAMP)
        k.fender(g.fy, g.rf, g.rf + 0.06, 15.0, 165.0, g.wf * 0.5 + 0.03, paint, x=sx * t)
        k.fender(g.ry, g.rr, g.rr + 0.06, 15.0, 165.0, g.wr * 0.5 + 0.03, paint, x=sx * t)
        k.tube([(sx * 0.17, g.fy - 0.04, 0.38), (sx * t, g.fy, g.rf)], 0.026, DARK, 4)       # рычаги
        k.tube([(sx * 0.17, g.ry + 0.04, 0.38), (sx * t, g.ry, g.rr)], 0.026, DARK, 4)
        k.box(sx * 0.17, g.foot[1] - 0.16, g.foot[2] - 0.03, sx * 0.38, g.foot[1] + 0.18, g.foot[2], DARK)   # подножки
        k.box(sx * 0.11, g.ry - 0.345, sz - 0.14, sx * 0.17, g.ry - 0.335, sz - 0.08, RED)
    # багажные решётки и бампер
    for yy, zz in ((g.fy + 0.14, sz + 0.03), (g.ry - 0.12, sz - 0.01)):
        for sx in (-0.24, 0.0, 0.24):
            k.tube([(sx, yy - 0.16, zz), (sx, yy + 0.16, zz)], 0.011, STEEL, 3)
        for dy in (-0.16, 0.16):
            k.tube([(-0.26, yy + dy, zz), (0.26, yy + dy, zz)], 0.011, STEEL, 3)
        for sx in (-0.2, 0.2):
            k.tube([(sx, yy, zz), (sx, yy, zz - 0.09)], 0.011, STEEL, 3)
    k.tube([(-0.24, g.fy + 0.22, 0.36), (-0.22, g.fy + 0.40, 0.42), (0.22, g.fy + 0.40, 0.42), (0.24, g.fy + 0.22, 0.36)],
           0.018, STEEL, 4)
    f.tube([(0, g.fy - 0.02, 0.50), (0, g.cy, g.cz)], 0.028, DARK, 5)
    _bars(f, g, 'riser', STEEL, 0.015)
    return dict(head=(0.0, g.fy + 0.32, sz - 0.20), tail=(0.0, g.ry - 0.35, sz - 0.11))


def _sidecar(g, paint, p2, k, f):
    sy, sz, x = g.sy, g.sz, g.x
    # сам мотоцикл: оппозитный двигатель, круглый бак, два седла
    k.box(x - 0.13, sy + 0.14, 0.26, x + 0.13, sy + 0.52, 0.52, ENGINE)
    for sx in (-1, 1):
        k.mb.cylinder_x(None, x + sx * 0.13, x + sx * 0.30, sy + 0.38, 0.40, 0.075, 8, FIN, cap_color=STEEL)
        k.tube([(x + sx * 0.26, sy + 0.44, 0.36), (x + sx * 0.20, sy + 0.10, 0.27), (x + sx * 0.18, g.ry - 0.20, 0.30)], 0.03, STEEL, 5)
    k.tube([(x, g.cy - 0.03, g.cz - 0.12), (x, sy + 0.18, sz + 0.0), (x, sy - 0.26, sz - 0.08)], 0.028, DARK, 5)
    k.tube([(x, g.cy - 0.02, g.cz - 0.18), (x, sy + 0.56, 0.30), (x, sy, 0.26)], 0.026, DARK, 5)
    _tank(k, sy + 0.16, g.cy - 0.10, sz - 0.04, sz + 0.20, 0.165, paint, x=x)
    _seat(k, sy - 0.20, sy + 0.16, sz, 0.15, 0.12, x=x, th=0.08)
    _seat(k, sy - 0.62, sy - 0.26, sz + 0.03, 0.14, 0.13, x=x, th=0.08)
    k.pair([(0.09, sy - 0.02, 0.36), (0.09, g.ry, g.rr)], 0.026, DARK, 4, x=x)
    k.pair([(0.09, sy - 0.40, sz - 0.08), (0.09, g.ry, g.rr)], 0.02, STEEL, 4, x=x)
    k.fender(g.ry, g.rr, g.rr + 0.045, 35.0, 185.0, g.wr * 0.5 + 0.035, paint, x=x)
    _tail(k, g.ry - g.rr - 0.045, g.rr + 0.12, 0.04, x=x)
    _pegs(k, g, 0.10, DARK, x=x)
    # коляска: «лодка» с местом пассажира, своим колесом и ветровым щитком
    cx = x + 0.80
    k.body([(g.ry - 0.44, 0.50, 0.13, 0.10), (g.ry - 0.06, 0.43, 0.31, 0.32), (sy + 0.44, 0.42, 0.32, 0.33),
            (sy + 0.90, 0.45, 0.26, 0.27), (sy + 1.18, 0.50, 0.10, 0.09)], paint, x=cx, e=0.8)
    k.box(cx - 0.24, sy - 0.46, 0.745, cx + 0.24, sy + 0.44, 0.758, SEAT)                    # проём кабины
    k.box(cx - 0.22, sy - 0.56, 0.66, cx + 0.22, sy - 0.46, 0.92, SEAT)                      # спинка
    k.panel((cx - 0.24, sy + 0.50, 0.745), (cx + 0.24, sy + 0.50, 0.745), (cx + 0.20, sy + 0.42, 0.97),
            (cx - 0.20, sy + 0.42, 0.97), GLASS)
    wx = cx + 0.40
    k.fender(g.ry + 0.22, g.rr, g.rr + 0.045, 20.0, 170.0, g.wr * 0.5 + 0.035, paint, x=wx)
    k.box(wx - 0.04, g.ry + 0.22 + g.rr + 0.03, g.rr + 0.10, wx + 0.04, g.ry + 0.22 + g.rr + 0.05, g.rr + 0.16, LAMP)
    k.box(wx - 0.04, g.ry + 0.22 - g.rr - 0.05, g.rr + 0.10, wx + 0.04, g.ry + 0.22 - g.rr - 0.03, g.rr + 0.16, RED)
    for yy in (sy + 0.56, sy - 0.30):                                                       # тяги к мотоциклу
        k.tube([(x + 0.06, yy, 0.42), (cx - 0.20, yy, 0.42)], 0.02, DARK, 4)
    k.tube([(cx - 0.10, g.ry + 0.22, g.rr), (wx, g.ry + 0.22, g.rr)], 0.03, DARK, 4)
    _fork(f, g, 0.09, STEEL, DARK, 0.024)
    _bars(f, g, 'riser', STEEL, 0.014)
    f.fender(g.fy, g.rf, g.rf + 0.04, 30.0, 165.0, g.wf * 0.5 + 0.035, paint, x=x)
    _headlight(f, g.cy + 0.15, g.cz - 0.12, 0.085, DARK, x=x)
    return dict(head=(x, g.cy + 0.17, g.cz - 0.12), tail=(x, g.ry - g.rr - 0.05, g.rr + 0.12),
                seat2=(cx, sy - 0.22, 0.56, 'tub'), side_wheel=(wx, g.ry + 0.22))


BUILDERS = {
    'bike': _sport, 'chopper': _chopper, 'scooter': _scooter, 'dirt': _dirt, 'bicycle': _bicycle, 'quad': _quad,
    'moped': _moped, 'copbike': lambda g, p, p2, k, f: _tourer(g, p, p2, k, f, police=True), 'sidecar': _sidecar,
    'trike': _trike, 'bmx': lambda g, p, p2, k, f: _bicycle(g, p, p2, k, f, bmx=True), 'tourer': _tourer,
    'courier': lambda g, p, p2, k, f: _scooter(g, p, p2, k, f, box=True), 'cargo': _cargo, 'kart': _kart,
    'caddy': _caddy,
}


def geo(kind):
    return Geo(KINDS[kind])


def light_points(kind):
    """Где у модели фара и задний фонарь (и маячки, если есть)."""
    g = geo(kind)
    res = BUILDERS[kind](g, WHITE, WHITE, Kit(), Kit())
    head = [] if kind in ('bicycle', 'bmx') else [res['head']]
    tail = [] if kind in ('bicycle', 'bmx') else [res['tail']]
    return head, tail, res.get('siren')


def build(assets, kind, paint):
    """Детали модели: body, fork, wheels=[(x, y, r, как поворачивает, узел колеса)], посадка ездока и пассажира."""
    key = (kind, int(paint[0] * 255), int(paint[1] * 255), int(paint[2] * 255))
    res = _cache.get(key)
    if res is not None:
        return res
    K = KINDS[kind]
    g = Geo(K)
    col = (paint[0], paint[1], paint[2], 1.0)
    p2 = (paint[0] * 0.70, paint[1] * 0.70, paint[2] * 0.70, 1.0)
    k = Kit()
    f = Kit(g.x, g.fy)                              # вилка лепится в осях машины, а хранится от оси поворота
    info = BUILDERS[kind](g, col, p2, k, f)
    wf = wheel_node(assets, g.rf, g.wf, K['wheel'])
    wr = wheel_node(assets, g.rr, g.wr, K.get('wheel_r', K['wheel']))
    t = K.get('track')
    lay = K.get('layout')
    if lay == 'quad':
        wheels = [(-t, g.fy, g.rf, 'self', wf), (t, g.fy, g.rf, 'self', wf), (-t, g.ry, g.rr, None, wr), (t, g.ry, g.rr, None, wr)]
    elif lay == 'trike':
        wheels = [(0.0, g.fy, g.rf, 'fork', wf), (-t, g.ry, g.rr, None, wr), (t, g.ry, g.rr, None, wr)]
    elif kind == 'sidecar':
        sx, sy_ = info['side_wheel']
        wheels = [(g.x, g.fy, g.rf, 'fork', wf), (g.x, g.ry, g.rr, None, wr), (sx, sy_, g.rr, None, wr)]
    else:
        wheels = [(0.0, g.fy, g.rf, 'fork', wf), (0.0, g.ry, g.rr, None, wr)]
    seat2 = info.get('seat2')
    if seat2 is None and kind in ('tourer', 'chopper', 'trike'):
        seat2 = (0.0, g.sy - (0.50 if kind == 'trike' else 0.42), g.pz + (0.12 if kind == 'trike' else 0.08), 'pillion')
    res = dict(body=k.build('body', assets), fork=f.build('fork', assets), wheels=wheels,
               seat=(g.x, g.sy, g.pz), pose=K['pose'], seat2=seat2, steer=(g.x, g.fy),
               head=info['head'], tail=info['tail'], siren=info.get('siren'))
    _cache[key] = res
    return res
