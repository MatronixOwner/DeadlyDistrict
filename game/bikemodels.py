# -*- coding: utf-8 -*-
"""Мотоцикл из готовой модели: чоппер «Ворон».

Модель лежит в assets/models/veh/b_chop.bam (импорт — tools/import_vehicles.py): кузов, вилка с рулём и колёса
идут отдельными узлами, окрашиваемые части — своими (paint, fork_paint).  Вместе с моделью импорт сохраняет
посадку ездока: какая из готовых поз к ней подходит и где при этом таз, ручки руля и стопы.

«Ворон» — чоппер Duhgless с пламенем на баке: красится у него бак (краска подставляется в текстуру, пламя
остаётся).  Другой двухколёсной техники в игре больше нет.
"""
from panda3d.core import NodePath, TransparencyAttrib, PNMImage, Texture

# вид техники -> (модель, оборудование)
KINDS = {
    'chopper': ('chop', None),
}
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
        self.x = 0.0
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
    key = (kind, int(paint[0] * 255), int(paint[1] * 255), int(paint[2] * 255))
    res = _cache.get(key)
    if res is not None:
        return res
    model, extra = KINDS[kind]
    m = models.meta['bikes'][model]
    src = models._load('veh', 'b_%s.bam' % model)
    tex = m.get('tex')
    x = 0.0
    fy, rf, wf = m['wheel_f']
    ry, rr, wr = m['wheel_r']
    py, pz = m['seat']
    body = NodePath('body')
    ptex = _painted(models, m['ptex'], paint) if m.get('ptex') else None
    _part(models, src, 'body', body, tex, x=x, ptex=ptex)
    _part(models, src, 'paint', body, tex, paint, x=x)
    fork = NodePath('fork')
    _part(models, src, 'fork', fork, tex)
    _part(models, src, 'fork_paint', fork, tex, paint)
    head = (x, m['head'][1], m['head'][2]) if 'head' in m else None
    tail = (x, m['tail'][1], m['tail'][2]) if 'tail' in m else None
    seat2 = None
    wf_node = _wheel(models, src, 'wheel_f', tex)
    wr_node = _wheel(models, src, 'wheel_r', tex)
    wheels = [(x, fy, rf, 'fork', wf_node), (x, ry, rr, None, wr_node)]
    gx, gy, gz = m['grips']
    if 'seat2' in m:
        seat2 = (x, m['seat2'][0], m['seat2'][1], 'pillion')
    body.flattenStrong()                                # краска и сдвиг — прямо в вершины; узлов остаётся два-три
    fork.flattenStrong()
    # lean — на сколько градусов корпус ездока подан вперёд (к далёкому рулю чоппера)
    res = dict(body=body, fork=fork, wheels=wheels, seat=(x, py, pz), pose=m['pose'], seat2=seat2, steer=(x, fy),
               head=head, tail=tail, siren=None, grips=(gx, gy, gz), axis=tuple(m['axis']) if 'axis' in m else (gy, gz),
               lean=float(m.get('lean', 0.0)))
    _cache[key] = res
    return res


def light_points(models, kind):
    """Фара и задний фонарь (в осях машины); третьим — маячки, их у мотоцикла нет."""
    model, extra = KINDS[kind]
    m = models.meta['bikes'][model]
    if 'head' not in m:
        return [], [], None
    return [(0.0, m['head'][1], m['head'][2])], [(0.0, m['tail'][1], m['tail'][2])], None


def clear():
    _cache.clear()
    _tex.clear()
