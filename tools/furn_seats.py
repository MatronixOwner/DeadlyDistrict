# -*- coding: utf-8 -*-
"""Где у мебели сиденье: высота подушки, её передний край и передняя сторона спинки — полосами поперёк предмета.

Сидящих расставляют по этим числам (game/interiors.py), поэтому человек всегда сидит на стуле, а не сквозь него.
Числа снимаются с самой модели: по треугольникам строится карта высот, по ней — профиль сиденья.

    python tools/furn_seats.py            дописать раздел "seat" в assets/models/furn/furn.json
    python tools/furn_seats.py show       только напечатать

Предметы в furn.bam стоят спинкой в +Y (лицом в -Y), серединой в начале координат.
"""
from __future__ import print_function

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'assets', 'models', 'furn')
SEATS = ('chair', 'armchair', 'sofa', 'pouf', 'stool')
CELL = 0.01


def triangles(np_):
    """Все треугольники предмета в его осях: массив (n, 3, 3)."""
    from panda3d.core import GeomVertexReader
    out = []
    for gp in np_.findAllMatches('**/+GeomNode'):
        m = gp.getMat(np_)
        for i in range(gp.node().getNumGeoms()):
            geom = gp.node().getGeom(i).decompose()
            vd = geom.getVertexData()
            r = GeomVertexReader(vd, 'vertex')
            pts = []
            while not r.isAtEnd():
                v = m.xformPoint(r.getData3())
                pts.append((v.x, v.y, v.z))
            for k in range(geom.getNumPrimitives()):
                prim = geom.getPrimitive(k)
                for t in range(prim.getNumPrimitives()):
                    a, b = prim.getPrimitiveStart(t), prim.getPrimitiveEnd(t)
                    idx = [prim.getVertex(j) for j in range(a, b)]
                    if len(idx) == 3:
                        out.append([pts[idx[0]], pts[idx[1]], pts[idx[2]]])
    return np.array(out, dtype=float)


def height_map(tri):
    """Карта высот: над каждой клеткой CELL x CELL — самая высокая поверхность предмета."""
    lo = tri.reshape(-1, 3).min(0)
    hi = tri.reshape(-1, 3).max(0)
    nx = int(np.ceil((hi[0] - lo[0]) / CELL)) + 1
    ny = int(np.ceil((hi[1] - lo[1]) / CELL)) + 1
    hm = np.zeros((nx, ny))
    xs = lo[0] + (np.arange(nx) + 0.5) * CELL
    ys = lo[1] + (np.arange(ny) + 0.5) * CELL
    for t in tri:
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = t
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-10:
            continue                                    # отвесная грань: сверху её не видно
        i0 = max(0, int((min(x0, x1, x2) - lo[0]) / CELL) - 1)
        i1 = min(nx, int((max(x0, x1, x2) - lo[0]) / CELL) + 2)
        j0 = max(0, int((min(y0, y1, y2) - lo[1]) / CELL) - 1)
        j1 = min(ny, int((max(y0, y1, y2) - lo[1]) / CELL) + 2)
        gx, gy = np.meshgrid(xs[i0:i1], ys[j0:j1], indexing='ij')
        a = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / den
        b = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / den
        c = 1.0 - a - b
        inside = (a >= -1e-6) & (b >= -1e-6) & (c >= -1e-6)
        z = a * z0 + b * z1 + c * z2
        sub = hm[i0:i1, j0:j1]
        np.maximum(sub, np.where(inside, z, 0.0), out=sub)
    return hm, xs, ys


def lane_of(hm, xs, ys, u):
    """Профиль сиденья в полосе вокруг бокового смещения u: (h, yf, yb) или None, если сесть тут нельзя."""
    cols = np.abs(xs - u) < 0.12
    if cols.sum() < 8:
        return None
    prof = hm[cols].max(0)                              # вдоль глубины, от переда (-Y) к спинке (+Y)
    top = hm.max()
    solid = np.where(prof > 0.2)[0]
    if len(solid) < 8:
        return None
    yf_i = int(solid[0])                                # передний край подушки
    lip = prof[yf_i + 2:yf_i + int(0.16 / CELL)]
    if len(lip) < 6:
        return None
    h0 = float(np.median(lip))
    # спинка: первая клетка за серединой сиденья, где профиль уходит выше подушки больше чем на ладонь
    yb_i = None
    if top > h0 + 0.25:
        up = np.where((prof > h0 + 0.10) & (np.arange(len(prof)) > yf_i + int(0.2 / CELL)))[0]
        if not len(up):
            return None                                 # у предмета спинка есть, а в этой полосе нет: это край
        yb_i = int(up[0])
    end = yb_i - 2 if yb_i is not None else int(solid[-1]) - 1
    zone = prof[yf_i + 2:min(end, yf_i + int(0.42 / CELL))]      # здесь лежат бёдра
    if len(zone) < 12:
        return None
    h = float(np.median(zone))
    if not (0.3 <= h <= 0.66) or zone.max() - zone.min() > 0.09:
        return None                                     # подлокотник, думка или вовсе не сиденье
    # человек шире полосы: по бокам от него на высоте бёдер не должно быть подлокотника
    mid = yf_i + (min(end, yf_i + int(0.42 / CELL)) - yf_i) // 2
    wide = hm[np.abs(xs - u) < 0.21][:, mid - 4:mid + 5]
    if wide.max() > h + 0.12:
        return None
    return round(h, 3), round(float(ys[yf_i]), 3), (round(float(ys[yb_i]), 3) if yb_i is not None else None)


def seat_of(tri):
    """Сиденье предмета: dict(h — высота подушки, yf — её передний край, yb — передняя сторона спинки
    (у табурета и пуфа вместо неё ye — задний край), u0..u1 — где поперёк предмета можно сидеть)."""
    hm, xs, ys = height_map(tri)
    w = xs[-1] - xs[0]
    lanes = []
    n = int(max(0.0, w * 0.5 - 0.25) / 0.05 + 1e-6)     # человек не свешивается за край
    for k in range(-n, n + 1):
        u = k * 0.05
        r = lane_of(hm, xs, ys, u)
        if r is not None:
            lanes.append([round(u, 2)] + list(r))
    if not lanes:
        return None
    # оставить только настоящую подушку: полосы на одной высоте с серединой и с такой же спинкой,
    # идущие подряд от середины
    mid = min(lanes, key=lambda q: abs(q[0]))
    ok = dict((q[0], q) for q in lanes if abs(q[1] - mid[1]) <= 0.03 and (q[3] is None) == (mid[3] is None) and
              (q[3] is None or abs(q[3] - mid[3]) <= 0.05))
    u0 = u1 = mid[0]
    while round(u0 - 0.05, 2) in ok:
        u0 = round(u0 - 0.05, 2)
    while round(u1 + 0.05, 2) in ok:
        u1 = round(u1 + 0.05, 2)
    keep = [q for q in lanes if u0 <= q[0] <= u1 and q[0] in ok]
    out = dict(h=round(float(np.median([q[1] for q in keep])), 3), yf=round(float(np.median([q[2] for q in keep])), 3),
               u0=u0, u1=u1)
    if mid[3] is not None:
        out['yb'] = round(float(np.min([q[3] for q in keep])), 3)
    else:
        cols = np.abs(xs - mid[0]) < 0.12
        solid = np.where(hm[cols].max(0) > 0.2)[0]
        out['ye'] = round(float(ys[int(solid[-1])]), 3)
    return out


def measure(root, path, show=False):
    """Снять сиденья с предметов под узлом root и дописать их в furn.json."""
    with open(path, encoding='utf-8') as f:
        meta = json.load(f)
    for name in sorted(meta['items']):
        it = meta['items'][name]
        it.pop('seat', None)
        if not name.startswith(SEATS) or name == 'sofa_corner':
            continue
        src = root.find('**/' + name)
        if src.isEmpty():
            continue
        s = seat_of(triangles(src))
        if s is None:
            print('%-16s нет сиденья' % name)
            continue
        it['seat'] = s
        print('%-16s %.2f x %.2f x %.2f   сиденье на %.2f, перед %+.2f, %s, поперёк от %+.2f до %+.2f' % (
            name, it['w'], it['d'], it['h'], s['h'], s['yf'],
            ('спинка %+.2f' % s['yb']) if 'yb' in s else ('без спинки, зад %+.2f' % s['ye']), s['u0'], s['u1']))
    if not show:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=0, sort_keys=True)
        print('записано', path)


def main():
    show = len(sys.argv) > 1 and sys.argv[1] == 'show'
    from panda3d.core import loadPrcFileData, Filename
    loadPrcFileData('', 'window-type none\naudio-library-name null')
    from direct.showbase.ShowBase import ShowBase
    base = ShowBase()
    root = base.loader.loadModel(Filename.fromOsSpecific(os.path.join(OUT, 'furn.bam')))
    measure(root, os.path.join(OUT, 'furn.json'), show)


if __name__ == '__main__':
    main()
