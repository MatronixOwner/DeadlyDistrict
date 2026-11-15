# -*- coding: utf-8 -*-
"""Тюнинг: что можно поставить на машину, сколько это стоит и что меняет.

Тюнинг машины — словарь «деталь -> номер варианта» (0 или отсутствие — заводское состояние).
Он лежит в Vehicle.tune, сохраняется вместе с машиной в гараже и применяется функцией apply().
Ходовые детали меняют множители разгона, скорости, тормозов, сцепления и запас прочности;
внешние — добавляют к кузову свои детали (спойлер, багажник, кенгурятник, неон и так далее).
"""
import math

from panda3d.core import TransparencyAttrib, ColorBlendAttrib, NodePath

from .meshbuilder import MeshBuilder

# (ключ, название раздела, [(название варианта, цена), ...])
PARTS = [
    ('engine', 'Двигатель', [('Чип-тюнинг', 1200), ('Форсированный', 2600), ('Гоночный', 4800)]),
    ('turbo', 'Турбина', [('Турбонаддув', 3000)]),
    ('gearbox', 'Коробка передач', [('Короткая пара', 1400), ('Спортивная', 2800)]),
    ('brakes', 'Тормоза', [('Усиленные', 800), ('Спортивные', 1600), ('Керамика', 3000)]),
    ('susp', 'Подвеска', [('Заниженная', 900), ('Спортивная', 2000), ('Раллийная', 2000)]),
    ('tyres', 'Шины', [('Спортивные', 1000), ('Слики', 2200)]),
    ('armor', 'Броня', [('Лёгкая', 1500), ('Средняя', 3500), ('Тяжёлая', 7000)]),
    ('nitro', 'Закись азота', [('Баллон', 4000)]),
    ('spoiler', 'Спойлер', [('Утиный хвост', 500), ('На стойках', 900), ('Антикрыло', 1500)]),
    ('rims', 'Диски', [('Хром', 600), ('Чёрные', 600), ('Золотые', 900), ('Белые', 600)]),
    ('neon', 'Неон', [('Синий', 800), ('Зелёный', 800), ('Красный', 800), ('Фиолетовый', 800), ('Белый', 800)]),
    ('xenon', 'Фары', [('Белый ксенон', 500), ('Синий ксенон', 700), ('Жёлтые', 400)]),
    ('horn', 'Сигнал', [('Воздушный', 300), ('Мелодия', 500), ('Крякалка', 700)]),
    ('exhaust', 'Выхлоп', [('Прямоток', 700), ('Двойной', 1200)]),
    ('roof', 'Крыша', [('Багажник', 400), ('Люстра', 900)]),
    ('bumper', 'Бампер', [('Кенгурятник', 800)]),
]
PART = dict((k, (title, opts)) for k, title, opts in PARTS)
TOTAL = sum(len(opts) for _, _, opts in PARTS)

# что годится не всякой машине: ключ -> для каких не годится
BIKE_SKIP = ('spoiler', 'roof', 'bumper', 'armor', 'susp')
NO_TUNE = ('police', 'enforcer', 'fbi', 'army', 'ambulance', 'bus')        # служебные и автобус

RIMS = [(1.0, 1.0, 1.0), (1.22, 1.22, 1.28), (0.34, 0.34, 0.36), (1.25, 0.98, 0.36), (1.5, 1.5, 1.5)]
NEON = [None, (0.2, 0.45, 1.0), (0.2, 1.0, 0.35), (1.0, 0.15, 0.12), (0.75, 0.2, 1.0), (1.0, 1.0, 1.0)]
XENON = [None, (0.92, 0.97, 1.16), (0.68, 0.84, 1.36), (1.12, 1.0, 0.58)]
HORNS = [None, 'horn_truck', 'horn_tune', 'horn_quack']
_profiles = {}


def parts_for(v):
    """Разделы тюнинга, доступные этой машине."""
    if v.kind in NO_TUNE:
        return []
    bike = getattr(v.spec, 'bike', False)
    return [(k, title, opts) for k, title, opts in PARTS if not (bike and k in BIKE_SKIP)]


def clean(tune):
    """Оставить в словаре только известные детали с допустимыми вариантами."""
    out = {}
    for k, val in (tune or {}).items():
        if k in PART:
            try:
                n = int(val)
            except (TypeError, ValueError):
                continue
            if 0 < n <= len(PART[k][1]):
                out[k] = n
    return out


def describe(tune):
    """Короткий перечень поставленного: «Двигатель: Гоночный, Неон: Синий»."""
    return ', '.join('%s: %s' % (PART[k][0], PART[k][1][n - 1][0]) for k, n in sorted(clean(tune).items()))


def value(tune):
    """Сколько стоит всё, что стоит на машине."""
    return sum(PART[k][1][n - 1][1] for k, n in clean(tune).items())


# ---------------------------------------------------------------------------
def apply(v, tune=None):
    """Применить тюнинг к машине: множители ходовых качеств, прочность, внешние детали."""
    if tune is not None:
        v.tune = clean(tune)
    t = v.tune
    spec = v.spec
    e, tb, gb = t.get('engine', 0), t.get('turbo', 0), t.get('gearbox', 0)
    v.k_acc = 1.0 + 0.09 * e + 0.12 * tb + 0.05 * gb
    v.k_top = 1.0 + 0.045 * e + 0.03 * tb + 0.035 * gb
    v.k_brake = 1.0 + 0.2 * t.get('brakes', 0)
    s = t.get('susp', 0)
    v.k_grip = 1.0 + (0.03, 0.03, 0.10, 0.05)[s] + 0.08 * t.get('tyres', 0)
    v.ride = (0.0, -0.07, -0.04, 0.11)[s]
    a = t.get('armor', 0)
    frac = v.health / v.max_health if v.max_health > 0 else 1.0
    v.max_health = spec.health * (1.0, 1.25, 1.55, 2.0)[a]
    v.health = v.max_health * min(1.0, frac)
    v.nitro = bool(t.get('nitro', 0))
    if not v.nitro:
        v.nitro_k = 0.0
    v.horn = HORNS[t.get('horn', 0)]
    v.snd_pitch = (1.0, 0.86, 0.92)[t.get('exhaust', 0)]
    v.snd_gain = (1.0, 1.3, 1.15)[t.get('exhaust', 0)]
    _visuals(v)


def _profile(v):
    """Высоты кузова, по которым ставятся детали: крыша, крышка багажника, передок."""
    key = v.kind
    p = _profiles.get(key)
    if p is not None:
        return p
    spec = v.spec
    hl, hw = spec.L * 0.5, spec.W * 0.5
    roof = rear = front = 0.0
    try:
        from panda3d.core import GeomVertexReader
        for gnp in v.body.findAllMatches('**/+GeomNode'):
            m = gnp.getMat(v.tilt)
            gn = gnp.node()
            for i in range(gn.getNumGeoms()):
                vd = gn.getGeom(i).getVertexData()
                rd = GeomVertexReader(vd, 'vertex')
                while not rd.isAtEnd():
                    q = m.xformPoint(rd.getData3())
                    if abs(q.x) > hw * 0.62:
                        continue
                    if abs(q.y) < spec.L * 0.16 and q.z > roof:
                        roof = q.z
                    if q.y < -hl + 0.5 and q.z > rear:
                        rear = q.z
                    if q.y > hl - 0.4 and q.z > front:
                        front = q.z
    except Exception:
        pass
    if roof < 0.5:
        roof = spec.H
    if rear < 0.3:
        rear = spec.belt + 0.1
    if front < 0.3:
        front = spec.belt
    p = _profiles[key] = dict(roof=roof, rear=min(rear, roof), front=min(front, roof))
    return p


def _visuals(v):
    """Собрать заново внешние детали тюнинга."""
    old = getattr(v, 'tune_np', None)
    if old is not None:
        old.removeNode()
    old = getattr(v, 'neon_np', None)
    if old is not None:
        old.removeNode()
    v.tune_np = None
    v.neon_np = None
    t = v.tune
    w = v.world
    spec = v.spec
    hl, hw = spec.L * 0.5, spec.W * 0.5
    bike = getattr(spec, 'bike', False)
    # диски: оттенок колёс (шина тёмная — она почти не меняется)
    rc = RIMS[t.get('rims', 0)]
    for piv, wn in v.wheels:
        if t.get('rims', 0):
            wn.setColorScale(rc[0], rc[1], rc[2], 1.0)
        else:
            wn.clearColorScale()
    # фары
    xc = XENON[t.get('xenon', 0)]
    v.light_tint = xc
    if v.lights is not None:
        if xc is not None:
            v.lights.setColorScale(xc[0], xc[1], xc[2], 1.0)
        else:
            v.lights.clearColorScale()
    # высота посадки
    v.tilt.setZ(v.ride)
    mb = MeshBuilder()
    used = False
    dark = (0.07, 0.07, 0.08, 1)
    steel = (0.62, 0.63, 0.66, 1)
    paint = v._paint_rgb()
    body = (paint[0] * 0.8, paint[1] * 0.8, paint[2] * 0.8, 1)
    if not bike:
        pr = _profile(v)
        sp = t.get('spoiler', 0)
        if sp == 1:
            mb.box(None, -hw * 0.82, -hl + 0.04, pr['rear'] - 0.01, hw * 0.82, -hl + 0.34, pr['rear'] + 0.07, body)
            used = True
        elif sp in (2, 3):
            h = 0.22 if sp == 2 else 0.40
            span = hw * (0.86 if sp == 2 else 0.98)
            for sx in (-hw * 0.5, hw * 0.5):
                mb.box(None, sx - 0.03, -hl + 0.16, pr['rear'] - 0.02, sx + 0.03, -hl + 0.26, pr['rear'] + h, dark)
            mb.box(None, -span, -hl + 0.04, pr['rear'] + h, span, -hl + 0.36, pr['rear'] + h + 0.035,
                   body if sp == 2 else dark)
            if sp == 3:
                for sx in (-span, span):
                    mb.box(None, sx - 0.02, -hl + 0.0, pr['rear'] + h - 0.10, sx + 0.02, -hl + 0.40,
                           pr['rear'] + h + 0.10, dark)
            used = True
        rf = t.get('roof', 0)
        if rf:
            z = pr['roof'] + 0.02
            x1, y0, y1 = hw * 0.62, -spec.L * 0.13, spec.L * 0.13
            for sx in (-x1, x1):
                mb.box(None, sx - 0.02, y0, z, sx + 0.02, y1, z + 0.09, steel)
            for yy in (y0, 0.0, y1):
                mb.box(None, -x1, yy - 0.02, z + 0.07, x1, yy + 0.02, z + 0.10, steel)
            if rf == 2:
                # «люстра»: четыре фары над лобовым стеклом
                yb = y1 + 0.04
                mb.box(None, -x1, yb - 0.03, z + 0.08, x1, yb + 0.03, z + 0.13, dark)
                for k in range(4):
                    cx = -x1 + (k + 0.5) * (2 * x1) / 4.0
                    mb.box(None, cx - 0.11, yb - 0.02, z + 0.13, cx + 0.11, yb + 0.10, z + 0.33, dark)
                    mb.quad(None, (cx - 0.09, yb + 0.105, z + 0.15), (cx + 0.09, yb + 0.105, z + 0.15),
                            (cx + 0.09, yb + 0.105, z + 0.31), (cx - 0.09, yb + 0.105, z + 0.31),
                            color=(1.0, 0.96, 0.8, 1))
            used = True
        if t.get('bumper', 0):
            y = hl + 0.10
            z0, z1 = max(0.28, spec.clear + 0.06), min(pr['front'], spec.clear + 0.72)
            for sx in (-hw * 0.48, hw * 0.48):
                mb.box(None, sx - 0.03, y - 0.03, z0, sx + 0.03, y + 0.03, z1, dark)
                mb.box(None, sx - 0.03, hl - 0.05, z0 + 0.10, sx + 0.03, y, z0 + 0.16, dark)
            for zz in (z0 + 0.08, (z0 + z1) * 0.5, z1 - 0.04):
                mb.box(None, -hw * 0.62, y - 0.03, zz, hw * 0.62, y + 0.03, zz + 0.05, dark)
            used = True
    ex = t.get('exhaust', 0)
    if ex:
        z = max(0.16, spec.clear + 0.02)
        xs = (hw * 0.45,) if ex == 1 else (-hw * 0.45, hw * 0.45)
        r = 0.06 if ex == 1 else 0.045
        if bike:
            xs = (0.16,)
            z = 0.34
        for sx in xs:
            mb.cylinder_x(None, 0.0, 0.26, 0.0, 0.0, r, 6, steel, cap_color=dark)
            # цилиндр строится вдоль X — поворачиваем его «вручную» коробкой: короткая труба вдоль Y
            mb.box(None, sx - r, -hl - 0.14, z - r, sx + r, -hl + 0.10, z + r, steel)
            mb.box(None, sx - r * 0.6, -hl - 0.145, z - r * 0.6, sx + r * 0.6, -hl - 0.14, z + r * 0.6, dark)
        used = True
    if used:
        np_ = mb.build('tune', w.assets.apply_state)
        np_.reparentTo(v.tilt)
        v.tune_np = np_
    # неон: цветное пятно света под днищем
    nc = NEON[t.get('neon', 0)]
    if nc is not None:
        nb = MeshBuilder()
        sx, sy = hw + 0.75, hl + 0.55
        nb.quad(('glow', 'add'), (-sx, -sy, 0.045), (sx, -sy, 0.045), (sx, sy, 0.045), (-sx, sy, 0.045),
                color=(nc[0], nc[1], nc[2], 1.0))
        np_ = nb.build('neon', w.assets.apply_state)
        np_.reparentTo(v.node)
        np_.setDepthWrite(False)
        v.neon_np = np_
        v.neon_c = nc
