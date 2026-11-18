# -*- coding: utf-8 -*-
"""Мотоцикл: чоппер «Ворон», и посадки людей в седле и в салоне машины.

«Ворон» — готовая модель (см. bikemodels.py).  Здесь лежит запасной вариант — тот же чоппер, собранный кодом
из труб, колёс и обтекаемых деталей: он строится, если файлы моделей не загрузились.  Остальная двухколёсная
техника (скутеры, мопед, велосипеды, квадроцикл, трайк, мотоцикл с коляской, карт, гольф-кар) из игры убрана.

Модель строится вокруг ездока.  Сначала выбирается посадка — как человек сидит в седле (POSES); по ней
ставятся седло, руль и подножки, а уже вокруг них — бак, двигатель, рама.  Поэтому руки ездока лежат на руле,
а ноги стоят на подножках, кто бы ни сидел в седле.

Модель состоит из «кузова» (всё неподвижное), «вилки» (руль, перья, переднее крыло — поворачиваются
вместе с передним колесом) и колёс.  Краска — цвет бака и крыльев.
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
WHITE = (0.92, 0.92, 0.90, 1.0)
PLATE = (0.90, 0.90, 0.86, 1.0)

# Посадки.  mix — доля клипа «верхом» (остальное — «за рулём»), lean — наклон корпуса вперёд, градусы.
# Дальше — где при такой посадке оказываются кисти, стопы и колени относительно таза (метры; вперёд и вверх),
# снятые с самой анимации: по этим числам ставятся руль и подножки.
POSES = {
    'chair': dict(mix=0.0, lean=0.0, hand=(0.48, 0.33), foot=(0.20, 0.44, -0.44), knee=(0.22, 0.45, -0.01)),
    'cruise': dict(mix=0.2, lean=0.0, hand=(0.48, 0.27), foot=(0.24, 0.36, -0.48), knee=(0.23, 0.445, -0.055)),
    # пассажир за спиной ездока — верхом, руки на бёдрах
    'pillion': dict(clips=(('sit', 0.55), ('ride', 0.45)), lean=4.0),
    # салон автомобиля: водитель — руки на баранке, спинка сиденья откинута; пассажир — руки на коленях
    'car': dict(clips=(('drive', 1.0),), lean=-3.0),
    'seat': dict(clips=(('sit', 0.7), ('drive', 0.3)), lean=-16.0),
}
PELVIS_UP = 0.10            # таз сидящего — на столько выше поверхности седла
SOLE = 0.09                 # подошва — на столько ниже кости стопы
# Плечо сидящего ездока относительно таза (вбок, вперёд, вверх), высота поясницы над тазом и длина руки от плеча
# до запястья — сняты со скелета в позе «chair».  По ним импорт считает, достанет ли ездок до высокого руля.
SHOULDER = (0.147, -0.057, 0.495)
WAIST = 0.10
ARM = 0.654

# вид -> размеры.  wb — база; rf, rr — радиусы колёс; wf, wr — ширина шин; seat — высота седла;
# rake — вынос оси переднего колеса вперёд от верха вилки; cb — на сколько ручки ближе к ездоку, чем верх вилки;
# cr — на сколько ручки выше верха вилки; bar — полуширина руля
KINDS = {
    'chopper': dict(wb=1.78, rf=0.34, rr=0.31, wf=0.09, wr=0.20, seat=0.66, pose='chair', rake=0.52, cb=0.30,
                    cr=0.22, bar=0.33, wheel='wire', wheel_r='cast'),
}
_cache = {}
_wheels = {}
_models = None              # загрузчик готовых моделей (models.Models): ставит use_models()


def use_models(models):
    """Подключить готовые модели: виды, для которых они есть, будут собираться из них."""
    global _models
    from . import bikemodels
    _models = models
    _cache.clear()
    bikemodels.clear()


def modelled(kind):
    """Собирается ли этот вид из готовой модели."""
    from . import bikemodels
    return bikemodels.has(_models, kind)


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
def _vtwin(k, y, z0, x=0.0):
    """Двигатель «вилкой» с рёбрами и круглым воздушным фильтром."""
    k.box(x - 0.14, y - 0.17, z0, x + 0.14, y + 0.17, z0 + 0.22, ENGINE)
    for dy in (-0.11, 0.11):
        top = (x, y + dy * 1.9, z0 + 0.48)
        k.tube([(x, y + dy * 0.6, z0 + 0.20), top], 0.078, FIN, 6)
        k.tube([(top[0], top[1] - dy * 0.1, top[2] - 0.02), (top[0], top[1] + dy * 0.2, top[2] + 0.03)], 0.06, STEEL, 6)
    k.mb.cylinder_x(None, x + 0.14, x + 0.19, y, z0 + 0.36, 0.085, 8, STEEL, cap_color=STEEL)
    k.box(x - 0.17, y - 0.20, z0 + 0.02, x - 0.14, y + 0.12, z0 + 0.20, STEEL)


def _chopper(g, paint, p2, k, f):
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


BUILDERS = {
    'chopper': _chopper,
}


def geo(kind):
    from . import bikemodels
    if bikemodels.has(_models, kind):
        return bikemodels.Geo(_models, kind)
    return Geo(KINDS[kind])


def light_points(kind):
    """Где у модели фара и задний фонарь (и маячки, если есть)."""
    from . import bikemodels
    if bikemodels.has(_models, kind):
        return bikemodels.light_points(_models, kind)
    g = geo(kind)
    res = BUILDERS[kind](g, WHITE, WHITE, Kit(), Kit())
    return [res['head']], [res['tail']], res.get('siren')


def build(assets, kind, paint):
    """Детали модели: body, fork, wheels=[(x, y, r, как поворачивает, узел колеса)], посадка ездока и пассажира."""
    from . import bikemodels
    if bikemodels.has(_models, kind):
        return bikemodels.build(assets, _models, kind, paint)
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
    wheels = [(0.0, g.fy, g.rf, 'fork', wf), (0.0, g.ry, g.rr, None, wr)]
    seat2 = (0.0, g.sy - 0.42, g.pz + 0.08, 'pillion')
    # grips — середины ручек руля (полуширина, y, z): за них держится ездок; axis — верх вилки: через него и
    # ось переднего колеса идёт ось, вокруг которой поворачивается руль
    res = dict(body=k.build('body', assets), fork=f.build('fork', assets), wheels=wheels,
               seat=(g.x, g.sy, g.pz), pose=K['pose'], seat2=seat2, steer=(g.x, g.fy),
               head=info['head'], tail=info['tail'], siren=info.get('siren'),
               grips=(g.bar - 0.05, g.gy, g.gz), axis=(g.cy, g.cz))
    _cache[key] = res
    return res
