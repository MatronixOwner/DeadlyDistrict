# -*- coding: utf-8 -*-
"""Генератор карт для радара и меню паузы (только для разработки).

Запуск из корня репозитория:  python tools/gen_map.py
Результат (вид сверху, север вверху):
    assets/tex/map.png          Порт-Глухов с Заречьем и восточным берегом
    assets/tex/map_north.png    Зимогорск — городок пролога

Город сначала рисуется по чертежу (прямые улицы, как его строит генератор), потом рисунок изгибается тем же
отображением «чертёж -> мир», что и сам город (game/warp.py): на карте улицы лежат так же, как в игре.
"""
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from game.city import City, INTRO_ZONES                  # noqa: E402
from game import mapinfo                                 # noqa: E402

SS = 2          # сглаживание
MARGIN = 620.0  # запас чертежа вокруг квадрата карты, м: районы города сдвинуты и повёрнуты не дальше этого
MESH = 16       # шаг сетки изгиба рисунка, пикселей

ZONE_COL = {'D': (104, 106, 116), 'O': (122, 110, 98), 'G': (112, 100, 90), 'R': (108, 124, 96),
            'I': (112, 112, 108), 'B': (128, 120, 104), 'P': (74, 128, 70), 'K': (84, 132, 76),
            'V': (126, 116, 102), 'S': (110, 128, 98), 'L': (110, 128, 98), 'H': (114, 112, 106),
            'A': (98, 128, 88), 'Y': (176, 178, 184), 'W': (214, 220, 228)}
BLD_COL = {'D': (150, 156, 172), 'O': (168, 148, 128), 'G': (150, 132, 118), 'R': (176, 160, 140),
           'I': (150, 150, 146), 'B': (182, 170, 150), 'P': (150, 150, 150),
           'V': (172, 152, 132), 'S': (178, 162, 142), 'L': (178, 162, 142), 'H': (150, 150, 146),
           'A': (160, 162, 166), 'Y': (150, 128, 112), 'W': (168, 150, 136)}
SEA = (44, 84, 118)
COVER_COL = {0: (98, 126, 84), 1: (198, 182, 134), 2: (132, 128, 122), 3: (66, 104, 66), 4: (156, 152, 96),
             5: SEA}
SNOW = (226, 232, 240)


class View(object):
    """Квадрат мира на рисунке n x n пикселей (плюс поля чертежа вокруг)."""

    def __init__(self, cx, cy, half, n):
        self.cx, self.cy, self.half, self.n = cx, cy, half, n
        self.k = n / (2.0 * half)
        self.m = int(round(MARGIN * self.k))

    def P(self, x, y):
        return ((x - (self.cx - self.half)) * self.k + self.m, ((self.cy + self.half) - y) * self.k + self.m)

    def inside(self, x0, y0, x1, y1):
        e = self.half + MARGIN
        return x1 > self.cx - e and x0 < self.cx + e and y1 > self.cy - e and y0 < self.cy + e


def terrain_layer(c, v):
    """Рельеф основной карты: цвет по покрытию, тени по склонам, мелководье светлее."""
    import numpy as np
    t = c.terrain
    size = v.n + 2 * v.m
    if not t.ok:
        return Image.new('RGB', (size, size), SEA)
    h = np.array(t.h, dtype=np.float64).reshape(t.ny, t.nx)
    cover = np.frombuffer(t.cover, dtype=np.uint8).reshape(t.ny, t.nx)
    img = np.zeros((t.ny, t.nx, 3))
    for k, col in COVER_COL.items():
        img[cover == k] = col
    gy, gx = np.gradient(h, t.step)
    shade = np.clip(1.0 + (gx - gy) * 0.8, 0.6, 1.4)
    land = cover != 5
    img[land] *= shade[land][:, None]
    depth = np.clip((-0.7 - h) / 4.0, 0.0, 1.0)
    img[~land] = np.array(SEA)[None, :] * (1.22 - 0.3 * depth[~land])[:, None]
    small = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)[::-1], 'RGB')
    # сетка рельефа -> пиксели чертежа
    a = v.P(t.x0, t.y1)
    w = int(round((t.x1 - t.x0) * v.k))
    hh = int(round((t.y1 - t.y0) * v.k))
    deep = tuple(int(q * 0.92) for q in SEA)           # за краем сетки — открытое море того же цвета
    out = Image.new('RGB', (size, size), deep)
    out.paste(small.resize((w, hh), Image.BICUBIC), (int(round(a[0])), int(round(a[1]))))
    return out


def snow_layer(c, v):
    """Снежная равнина Зимогорска: белое поле с тенями по склонам холмов."""
    import numpy as np
    f = c.snowfield
    size = v.n + 2 * v.m
    out = Image.new('RGB', (size, size), SNOW)
    if f is None:
        return out
    h = np.array(f.h, dtype=np.float64).reshape(f.ny, f.nx)
    gy, gx = np.gradient(h, f.step)
    shade = np.clip(1.0 + (gx - gy) * 0.55, 0.72, 1.06)
    img = np.array(SNOW, dtype=np.float64)[None, None, :] * shade[..., None]
    small = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)[::-1], 'RGB')
    a = v.P(f.x0, f.y1)
    w = int(round((f.x1 - f.x0) * v.k))
    hh = int(round((f.y1 - f.y0) * v.k))
    out.paste(small.resize((w, hh), Image.BICUBIC), (int(round(a[0])), int(round(a[1]))))
    return out


def bend(plan, c, v):
    """Рисунок по чертежу -> карта мира n x n: каждая клетка карты берёт свой четырёхугольник чертежа."""
    wp = c.warp
    n, m, k = v.n, v.m, v.k
    if wp is None:
        return plan.crop((m, m, m + n, m + n))
    cols = n // MESH

    def src(i, j):                                   # узел сетки карты -> точка рисунка-чертежа
        x = (v.cx - v.half) + i * MESH / k
        y = (v.cy + v.half) - j * MESH / k
        return v.P(*wp.inv_exact(x, y))
    pts = [[src(i, j) for i in range(cols + 1)] for j in range(cols + 1)]
    mesh = []
    for j in range(cols):
        for i in range(cols):
            a, b, cc, dd = pts[j][i], pts[j + 1][i], pts[j + 1][i + 1], pts[j][i + 1]      # СЗ, ЮЗ, ЮВ, СВ
            mesh.append(((i * MESH, j * MESH, (i + 1) * MESH, (j + 1) * MESH),
                         (a[0], a[1], b[0], b[1], cc[0], cc[1], dd[0], dd[1])))
    return plan.transform((n, n), Image.MESH, mesh, Image.BICUBIC)


def render(c, name, cx, cy, half, size, layer, snowy=False):
    v = View(cx, cy, half, size * SS)
    im = layer(c, v)
    d = ImageDraw.Draw(im)
    P = v.P

    def rect(x0, y0, x1, y1, col):
        a = P(x0, y1)
        b = P(x1, y0)
        d.rectangle([a[0], a[1], b[0], b[1]], fill=col)

    ROAD = (58, 58, 62)
    WALK = (190, 194, 200) if snowy else (120, 120, 118)
    PAVE = (200, 202, 206) if snowy else (158, 152, 140)
    for (x0, y0, x1, y1, z) in c.extra_land:           # причалы, пирсы
        if v.inside(x0, y0, x1, y1):
            rect(x0, y0, x1, y1, (150, 140, 124))
    # дороги и перекрёстки
    for key, s in c.segs.items():
        hw = s['width'] * 0.5
        col = (92, 84, 80) if s['bridge'] else ROAD
        if s['kind'] == 'h':
            rect(s['a'], s['c'] - hw, s['b'], s['c'] + hw, col)
        else:
            rect(s['c'] - hw, s['a'], s['c'] + hw, s['b'], col)
    for nd in c.nodes.values():
        nx_, ny_ = getattr(nd, 'lx', nd.x), getattr(nd, 'ly', nd.y)        # узел на чертеже
        rect(nx_ - nd.hw, ny_ - nd.hh, nx_ + nd.hw, ny_ + nd.hh, ROAD)
    for (x0, y0, x1, y1) in c.walk_strips:
        rect(x0, y0, x1, y1, WALK)
    for b in c.blocks:
        rect(b.x0, b.y0, b.x1, b.y1, ZONE_COL.get(b.zone, (110, 110, 110)))
    # пешеходные бульвары внутри слитых кварталов: светлая дорожка, в жилых районах — по газону
    for (x0, y0, x1, y1, zone) in c.special.get('boulevards', ()):
        green = c.zone_style(zone) == 'R'
        if zone in INTRO_ZONES:
            rect(x0, y0, x1, y1, PAVE)
            continue
        rect(x0, y0, x1, y1, (96, 132, 86) if green else PAVE)
        if green:
            if x1 - x0 > y1 - y0:
                rect(x0, (y0 + y1) * 0.5 - 2.4, x1, (y0 + y1) * 0.5 + 2.4, (168, 160, 146))
            else:
                rect((x0 + x1) * 0.5 - 2.4, y0, (x0 + x1) * 0.5 + 2.4, y1, (168, 160, 146))
    # покрытия внутри кварталов, заметные на карте: взлётная полоса, асфальт, аллеи садов-клиньев
    for (x0, y0, x1, y1, tex, tile, color, block, z, rot) in c.ground:
        if tex == 'asphalt' and (x1 - x0) * (y1 - y0) > 400.0:
            rect(x0, y0, x1, y1, (72, 72, 76))
        elif tex == 'pavers' and 0 <= block < len(c.blocks) and c.blocks[block].zone == 'K':
            rect(x0, y0, x1, y1, (172, 166, 148))
    pond = c.special.get('pond')
    if pond:
        a = P(pond['x'] - pond['rx'], pond['y'] + pond['ry'])
        b = P(pond['x'] + pond['rx'], pond['y'] - pond['ry'])
        d.ellipse([a[0], a[1], b[0], b[1]], fill=(60, 110, 150))
    for b in c.buildings:
        if not v.inside(b.x0, b.y0, b.x1, b.y1):
            continue
        zone = c.blocks[b.block].zone if 0 <= b.block < len(c.blocks) else 'I'
        col = BLD_COL.get(zone, (150, 150, 150))
        if b.name:
            col = (214, 196, 120)
        rect(b.x0, b.y0, b.x1, b.y1, col)
        a = P(b.x0, b.y1)
        bb = P(b.x1, b.y0)
        d.rectangle([a[0], a[1], bb[0], bb[1]], outline=(col[0] * 3 // 4, col[1] * 3 // 4, col[2] * 3 // 4))
    # осевые линии проспектов, трассы и мостов
    for key, s in c.segs.items():
        if not s['ave']:
            continue
        if s['kind'] == 'h':
            rect(s['a'], s['c'] - 0.45, s['b'], s['c'] + 0.45, (150, 140, 70))
        else:
            rect(s['c'] - 0.45, s['a'], s['c'] + 0.45, s['b'], (150, 140, 70))
    im = bend(im, c, v)
    im = im.resize((size, size), Image.LANCZOS)
    out = os.path.join(ROOT, 'assets', 'tex', name + '.png')
    if len(sys.argv) > 1:
        out = os.path.join(sys.argv[1], name + '.png')
    im.quantize(255, method=Image.MEDIANCUT, dither=Image.NONE).save(out, optimize=True)
    print('map written:', out, os.path.getsize(out), 'bytes')
    return out


def main():
    c = City()
    assert abs(c.intro_x0 - mapinfo.NORTH_X0) < 1.0, 'mapinfo.NORTH_X0 разошёлся с городом'
    render(c, 'map', mapinfo.MAP_CX, mapinfo.MAP_CY, mapinfo.MAP_HALF, 2048, terrain_layer)
    render(c, 'map_north', mapinfo.NORTH_CX, mapinfo.NORTH_CY, mapinfo.NORTH_HALF, 1024, snow_layer, snowy=True)


if __name__ == '__main__':
    main()
