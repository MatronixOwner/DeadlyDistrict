# -*- coding: utf-8 -*-
"""Двухколёсные с готовыми моделями: чоппер, мотоцикл (круизер) и два велосипеда.

Модели лежат в assets/models/veh/b_*.bam (импорт — tools/import_vehicles.py): кузов, вилка с рулём и колёса
идут отдельными узлами, окрашиваемые части — своими (paint, fork_paint).  Вместе с моделью импорт сохраняет
посадку ездока: какая из готовых поз к ней подходит и где при этом таз, ручки руля и стопы.

«Ворон» — чоппер Duhgless с пламенем на баке: красится у него бак (краска подставляется в текстуру, пламя
остаётся).  На круизере собрано четыре вида техники: «Странник», патрульный, трайк и «Тайга» получают своё
оборудование — кофры и ветровое стекло, маячки, задний мост с двумя колёсами, коляску.
Это оборудование достраивается здесь из простых деталей (как раньше строились все мотоциклы целиком).

Видов, для которых готовой модели не нашлось (спортивный и кроссовый мотоциклы, скутеры, мопед, квадроцикл,
грузовой мотороллер, гольф-кар, карт), здесь нет: их по-прежнему собирает bikes.py.
"""
from panda3d.core import NodePath, TransparencyAttrib, PNMImage, Texture

# вид техники -> (модель, оборудование)
KINDS = {
    'chopper': ('chop', None),
    'tourer': ('moto', 'tourer'),
    'copbike': ('moto', 'police'),
    'trike': ('moto', 'trike'),
    'sidecar': ('moto', 'sidecar'),
    'bicycle': ('cycle', None),
    'bmx': ('bmx', None),
}
TRIKE_TRACK = 0.52          # полуколея задних колёс трайка
SIDECAR_X = -0.40           # сам мотоцикл сдвинут влево: справа коляска
_cache = {}
_tex = {}


def has(models, kind):
    """Есть ли для этого вида готовая модель (и загружены ли модели вообще)."""
    if models is None or not getattr(models, 'ok', False) or kind not in KINDS:
        return False
    return KINDS[kind][0] in models.meta.get('bikes', {})


def info(models, kind):
    return models.meta['bikes'][KINDS[kind][0]]


class Geo(object):
    """Опорные точки модели — те же поля, что у bikes.Geo: оси колёс, седло, таз ездока, ручки руля."""

    def __init__(self, models, kind):
        model, extra = KINDS[kind]
        m = models.meta['bikes'][model]
        self.x = SIDECAR_X if extra == 'sidecar' else 0.0
        self.fy, self.rf, self.wf = m['wheel_f']
        self.ry, self.rr, self.wr = m['wheel_r']
        self.sy, self.pz = m['seat']
        self.sz = m['seat_top']
        self.bar, self.gy, self.gz = m['grips']
        self.foot = tuple(m['foot'])


def _texture(models, name, alpha=False):
    t = _tex.get(name)
    if t is None:
        t = _tex[name] = models.loader.loadTexture(models.path('veh', name + '.png'))
        models.assets.setup_filter(t)
    return t


def _painted(models, name, paint):
    """Текстура с краской: цвет × светотень, сверху всё, что не красится (у чоппера — пламя на баке).
    Слои те же, что у автомобилей: <имя>.png с прозрачностью на месте краски и <имя>_shade.png."""
    from .models import PAINT_GAIN, PAINT_SAT
    key = (name, int(paint[0] * 255), int(paint[1] * 255), int(paint[2] * 255))
    t = _tex.get(key)
    if t is None:
        detail = models._pnm(name)
        w, h = detail.getXSize(), detail.getYSize()
        g = paint[0] * 0.30 + paint[1] * 0.59 + paint[2] * 0.11
        img = PNMImage(w, h, 3)
        img.fill(min(1.0, (g + (paint[0] - g) * PAINT_SAT) * PAINT_GAIN), min(1.0, (g + (paint[1] - g) * PAINT_SAT) * PAINT_GAIN),
                 min(1.0, (g + (paint[2] - g) * PAINT_SAT) * PAINT_GAIN))
        img.multSubImage(models._pnm(name + '_shade'), 0, 0, 0, 0, w, h, 2.0)
        img.blendSubImage(detail, 0, 0, 0, 0, w, h)
        t = _tex[key] = Texture('bike-%s' % '-'.join(str(q) for q in key))
        t.load(img)
        models.assets.setup_filter(t)
    return t


def _part(models, src, name, parent, tex, paint=None, x=0.0, ptex=None):
    """Скопировать узел модели: зернистая текстура на гладкие детали, своя — на детали с развёрткой;
    окрашиваемым — цвет.  ptex — готовая текстура с краской для деталей «p» (бак чоппера)."""
    n = src.find(name)
    if n.isEmpty():
        return None
    c = n.copyTo(parent)
    g = c.find('g')
    if not g.isEmpty():
        g.setTexture(_texture(models, 'grain'), 1)
    pt = c.find('p')
    if not pt.isEmpty() and ptex is not None:
        pt.setTexture(ptex, 1)
        pt.setTwoSided(True)
    t = c.find('t')
    if not t.isEmpty() and tex:
        t.setTexture(_texture(models, tex), 1)
        t.setTransparency(TransparencyAttrib.MBinary)
        t.setTwoSided(True)                         # спицы — плоский диск с прозрачными промежутками
    if paint is not None:
        c.setColorScale(paint[0], paint[1], paint[2], 1.0)
    if x:
        c.setX(x)
    return c


def _wheel(models, src, name, tex, width=None):
    key = (id(src), name, width)
    w = _cache.get(key)
    if w is None:
        w = NodePath('wheel')
        c = _part(models, src, name, w, tex)
        if width is not None:
            c.setSx(width)
        w.flattenStrong()
        _cache[key] = w
    return w


def build(assets, models, kind, paint):
    """То же, что bikes.build: детали модели, колёса, посадка ездока и пассажира, точки огней."""
    from . import bikes as B
    key = (kind, int(paint[0] * 255), int(paint[1] * 255), int(paint[2] * 255))
    res = _cache.get(key)
    if res is not None:
        return res
    model, extra = KINDS[kind]
    m = models.meta['bikes'][model]
    src = models._load('veh', 'b_%s.bam' % model)
    tex = m.get('tex')
    x = SIDECAR_X if extra == 'sidecar' else 0.0
    fy, rf, wf = m['wheel_f']
    ry, rr, wr = m['wheel_r']
    py, pz = m['seat']
    col = (paint[0], paint[1], paint[2], 1.0)
    p2 = (paint[0] * 0.70, paint[1] * 0.70, paint[2] * 0.70, 1.0)
    body = NodePath('body')
    ptex = _painted(models, m['ptex'], paint) if m.get('ptex') else None
    _part(models, src, 'body', body, tex, x=x, ptex=ptex)
    _part(models, src, 'paint', body, tex, WHITE_POLICE if extra == 'police' else paint, x=x)
    fork = NodePath('fork')
    _part(models, src, 'fork', fork, tex)
    _part(models, src, 'fork_paint', fork, tex, WHITE_POLICE if extra == 'police' else paint)
    k = B.Kit()                                         # оборудование кузова — в осях машины
    f = B.Kit(0.0, fy)                                  # оборудование вилки — от оси поворота
    head = (x, m['head'][1], m['head'][2]) if 'head' in m else None
    tail = (x, m['tail'][1], m['tail'][2]) if 'tail' in m else None
    siren = None
    seat2 = None
    wf_node = _wheel(models, src, 'wheel_f', tex)
    wr_node = _wheel(models, src, 'wheel_r', tex)
    wheels = [(x, fy, rf, 'fork', wf_node), (x, ry, rr, None, wr_node)]
    gx, gy, gz = m['grips']
    if model == 'moto':
        seat2 = (x, py - 0.42, pz + 0.07, 'pillion')
    elif 'seat2' in m:
        seat2 = (x, m['seat2'][0], m['seat2'][1], 'pillion')
    if extra == 'tourer':
        _luggage(B, k, col, p2, ry, rr, py, pz, top=True)
        _screen(B, f, fy, gy, gz, col)
    elif extra == 'police':
        white = (0.92, 0.92, 0.94, 1.0)
        _luggage(B, k, white, B.BLUE, ry, rr, py, pz, top=False)
        _screen(B, f, fy, gy, gz, white)
        k.box(-0.14, py - 0.72, pz - 0.02, 0.14, py - 0.40, pz + 0.18, B.WHITE)              # ящик с рацией
        k.tube([(0.10, py - 0.68, pz + 0.18), (0.10, py - 0.70, pz + 0.68)], 0.006, B.DARK, 3)
        for sx, c in ((-1, B.RED), (1, B.BLUE)):                                            # маячки на штангах
            k.tube([(sx * 0.21, ry + 0.02, rr + 0.34), (sx * 0.21, ry, pz + 0.40)], 0.012, B.STEEL, 4)
            k.box(sx * 0.17, ry - 0.04, pz + 0.40, sx * 0.25, ry + 0.04, pz + 0.50, c)
        siren = [(-0.21, ry, pz + 0.52), (0.21, ry, pz + 0.52)]
        seat2 = None
    elif extra == 'trike':
        t = TRIKE_TRACK
        k.tube([(-t, ry, rr), (t, ry, rr)], 0.04, B.DARK, 5)                                 # задний мост
        k.body([(ry - 0.42, rr + 0.25, 0.30, 0.10), (ry - 0.05, rr + 0.25, 0.33, 0.16), (py - 0.30, rr + 0.22, 0.22, 0.12)],
               col, e=0.8)
        B._seat(k, py - 0.70, py - 0.30, pz - 0.04, 0.24, 0.20, th=0.09)                     # диван пассажира
        k.box(-0.24, py - 0.78, pz - 0.06, 0.24, py - 0.70, pz + 0.30, B.SEAT)
        for sx in (-1, 1):
            k.fender(ry, rr, rr + 0.05, 20.0, 170.0, 0.13, col, x=sx * t)
            k.box(sx * (t - 0.06), ry - rr - 0.07, rr + 0.04, sx * (t + 0.06), ry - rr - 0.05, rr + 0.10, B.RED)
        wide = _wheel(models, src, 'wheel_r', tex, 1.25)
        wheels = [(0.0, fy, rf, 'fork', wf_node), (-t, ry, rr, None, wide), (t, ry, rr, None, wide)]
        seat2 = (0.0, py - 0.50, pz + 0.06, 'pillion')
        tail = (0.0, ry - rr - 0.07, rr + 0.08)
    elif extra == 'sidecar':
        # коляска: «лодка» с местом пассажира, своим колесом и ветровым щитком
        cx = x + 0.80
        k.body([(ry - 0.44, 0.50, 0.13, 0.10), (ry - 0.06, 0.43, 0.31, 0.32), (py + 0.44, 0.42, 0.32, 0.33),
                (py + 0.90, 0.45, 0.26, 0.27), (py + 1.18, 0.50, 0.10, 0.09)], col, x=cx, e=0.8)
        k.box(cx - 0.24, py - 0.46, 0.745, cx + 0.24, py + 0.44, 0.758, B.SEAT)              # проём кабины
        k.box(cx - 0.22, py - 0.56, 0.66, cx + 0.22, py - 0.46, 0.92, B.SEAT)                # спинка
        k.panel((cx - 0.24, py + 0.50, 0.745), (cx + 0.24, py + 0.50, 0.745), (cx + 0.20, py + 0.42, 0.97),
                (cx - 0.20, py + 0.42, 0.97), B.GLASS)
        wx = cx + 0.40
        k.fender(ry + 0.22, rr, rr + 0.045, 20.0, 170.0, wr * 0.5 + 0.035, col, x=wx)
        k.box(wx - 0.04, ry + 0.22 + rr + 0.03, rr + 0.10, wx + 0.04, ry + 0.22 + rr + 0.05, rr + 0.16, B.LAMP)
        k.box(wx - 0.04, ry + 0.22 - rr - 0.05, rr + 0.10, wx + 0.04, ry + 0.22 - rr - 0.03, rr + 0.16, B.RED)
        for yy in (py + 0.56, py - 0.30):                                                   # тяги к мотоциклу
            k.tube([(x + 0.06, yy, 0.42), (cx - 0.20, yy, 0.42)], 0.02, B.DARK, 4)
        k.tube([(cx - 0.10, ry + 0.22, rr), (wx, ry + 0.22, rr)], 0.03, B.DARK, 4)
        wheels.append((wx, ry + 0.22, rr, None, wr_node))
        seat2 = (cx, py - 0.22, 0.56, 'tub')
    k.build('extra', assets).reparentTo(body)
    f.build('extra', assets).reparentTo(fork)
    body.flattenStrong()                                # краска и сдвиг — прямо в вершины; узлов остаётся два-три
    fork.flattenStrong()
    # lean — на сколько градусов корпус ездока подан вперёд (к далёкому рулю чоппера)
    res = dict(body=body, fork=fork, wheels=wheels, seat=(x, py, pz), pose=m['pose'], seat2=seat2, steer=(x, fy),
               head=head, tail=tail, siren=siren, grips=(gx, gy, gz), axis=tuple(m['axis']) if 'axis' in m else (gy, gz),
               lean=float(m.get('lean', 0.0)))
    _cache[key] = res
    return res


WHITE_POLICE = (0.92, 0.92, 0.94)


def _luggage(B, k, body, trim, ry, rr, py, pz, top):
    """Кофры по бокам заднего колеса; у «Странника» ещё верхний кофр со спинкой для пассажира."""
    for sx in (-1, 1):
        k.box(sx * 0.17, ry - 0.22, rr + 0.02, sx * 0.38, ry + 0.30, rr + 0.34, body)
        k.box(sx * 0.382, ry - 0.22, rr + 0.16, sx * 0.388, ry + 0.30, rr + 0.21, trim)
    if top:
        k.box(-0.20, py - 0.98, pz - 0.02, 0.20, py - 0.66, pz + 0.28, body)                 # верхний кофр
        k.box(-0.16, py - 0.665, pz + 0.02, 0.16, py - 0.645, pz + 0.24, B.SEAT)             # спинка
        k.box(-0.203, py - 0.98, pz + 0.12, 0.203, py - 0.66, pz + 0.16, trim)


def _screen(B, f, fy, gy, gz, body):
    """Ветровое стекло на руле с невысоким обтекателем под ним."""
    y = gy + 0.30
    f.panel((-0.24, y + 0.06, gz - 0.16), (0.24, y + 0.06, gz - 0.16), (0.17, y - 0.06, gz + 0.30), (-0.17, y - 0.06, gz + 0.30),
            B.GLASS)
    f.box(-0.25, y + 0.03, gz - 0.24, 0.25, y + 0.08, gz - 0.15, body)
    for sx in (-1, 1):
        f.tube([(sx * 0.20, gy + 0.02, gz - 0.03), (sx * 0.21, y + 0.04, gz - 0.14)], 0.009, B.DARK, 3)


def light_points(models, kind):
    """Фара, задний фонарь и маячки (в осях машины)."""
    model, extra = KINDS[kind]
    m = models.meta['bikes'][model]
    if 'head' not in m:
        return [], [], None
    x = SIDECAR_X if extra == 'sidecar' else 0.0
    ry, rr = m['wheel_r'][0], m['wheel_r'][1]
    py, pz = m['seat']
    head = [(x, m['head'][1], m['head'][2])]
    tail = [(x, m['tail'][1], m['tail'][2])]
    siren = None
    if extra == 'police':
        siren = [(-0.21, ry, pz + 0.52), (0.21, ry, pz + 0.52)]
    elif extra == 'trike':
        tail = [(0.0, ry - rr - 0.07, rr + 0.08)]
    return head, tail, siren


def clear():
    _cache.clear()
    _tex.clear()
