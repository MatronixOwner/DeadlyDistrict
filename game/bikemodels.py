# -*- coding: utf-8 -*-
"""Двухколёсные с готовыми моделями: мотоцикл-круизер и два велосипеда.

Модели лежат в assets/models/veh/b_*.bam (импорт — tools/import_vehicles.py): кузов, вилка с рулём и колёса
идут отдельными узлами, окрашиваемые части — своими (paint, fork_paint).  Вместе с моделью импорт сохраняет
посадку ездока: какая из готовых поз к ней подходит и где при этом таз, ручки руля и стопы.
"""
from panda3d.core import NodePath, TransparencyAttrib

KINDS = {
    'chopper': ('moto', None),
    'bicycle': ('cycle', None),
    'bmx': ('bmx', None),
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
    """Опорные точки модели: оси колёс, седло, таз ездока, ручки руля."""

    def __init__(self, models, kind):
        model, _ = KINDS[kind]
        m = models.meta['bikes'][model]
        self.x = 0.0
        self.fy, self.rf, self.wf = m['wheel_f']
        self.ry, self.rr, self.wr = m['wheel_r']
        self.sy, self.pz = m['seat']
        self.sz = m['seat_top']
        self.bar, self.gy, self.gz = m['grips']
        self.foot = tuple(m['foot'])


def _texture(models, name):
    t = _tex.get(name)
    if t is None:
        t = _tex[name] = models.loader.loadTexture(models.path('veh', name + '.png'))
        models.assets.setup_filter(t)
    return t


def _part(models, src, name, parent, tex, paint=None):
    n = src.find(name)
    if n.isEmpty():
        return None
    c = n.copyTo(parent)
    g = c.find('g')
    if not g.isEmpty():
        g.setTexture(_texture(models, 'grain'), 1)
    t = c.find('t')
    if not t.isEmpty() and tex:
        t.setTexture(_texture(models, tex), 1)
        t.setTransparency(TransparencyAttrib.MBinary)
        t.setTwoSided(True)
    if paint is not None:
        c.setColorScale(paint[0], paint[1], paint[2], 1.0)
    return c


def _wheel(models, src, name, tex):
    key = (id(src), name)
    w = _cache.get(key)
    if w is None:
        w = NodePath('wheel')
        _part(models, src, name, w, tex)
        w.flattenStrong()
        _cache[key] = w
    return w


def build(assets, models, kind, paint):
    """Детали модели, колёса, посадка ездока и пассажира, точки огней."""
    key = (kind, int(paint[0] * 255), int(paint[1] * 255), int(paint[2] * 255))
    res = _cache.get(key)
    if res is not None:
        return res
    model, _ = KINDS[kind]
    m = models.meta['bikes'][model]
    src = models._load('veh', 'b_%s.bam' % model)
    tex = m.get('tex')
    fy, rf, wf = m['wheel_f']
    ry, rr, wr = m['wheel_r']
    py, pz = m['seat']
    body = NodePath('body')
    _part(models, src, 'body', body, tex)
    _part(models, src, 'paint', body, tex, paint)
    fork = NodePath('fork')
    _part(models, src, 'fork', fork, tex)
    _part(models, src, 'fork_paint', fork, tex, paint)
    head = (0.0, m['head'][1], m['head'][2]) if 'head' in m else None
    tail = (0.0, m['tail'][1], m['tail'][2]) if 'tail' in m else None
    wf_node = _wheel(models, src, 'wheel_f', tex)
    wr_node = _wheel(models, src, 'wheel_r', tex)
    wheels = [(0.0, fy, rf, 'fork', wf_node), (0.0, ry, rr, None, wr_node)]
    seat2 = (0.0, py - 0.42, pz + 0.07, 'pillion') if model == 'moto' else None
    body.flattenStrong()
    fork.flattenStrong()
    res = dict(body=body, fork=fork, wheels=wheels, seat=(0.0, py, pz), pose=m['pose'], seat2=seat2,
               steer=(0.0, fy), head=head, tail=tail, siren=None)
    _cache[key] = res
    return res


def light_points(models, kind):
    """Фара и задний фонарь (в осях машины)."""
    model, _ = KINDS[kind]
    m = models.meta['bikes'][model]
    if 'head' not in m:
        return [], [], None
    return [(0.0, m['head'][1], m['head'][2])], [(0.0, m['tail'][1], m['tail'][2])], None


def clear():
    _cache.clear()
    _tex.clear()
