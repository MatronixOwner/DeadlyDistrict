# -*- coding: utf-8 -*-
"""Генератор карты города для радара и меню паузы (только для разработки).

Запуск из корня репозитория:  python tools/gen_map.py
Результат: assets/tex/map.png (вид сверху, север вверху).
"""
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from game.city import City                      # noqa: E402
from game.mapinfo import MAP_CX, MAP_CY, MAP_HALF        # noqa: E402

SIZE = 1024
SS = 2          # сглаживание

ZONE_COL = {'D': (104, 106, 116), 'O': (122, 110, 98), 'G': (112, 100, 90), 'R': (108, 124, 96),
            'I': (112, 112, 108), 'B': (128, 120, 104), 'P': (74, 128, 70)}
BLD_COL = {'D': (150, 156, 172), 'O': (168, 148, 128), 'G': (150, 132, 118), 'R': (176, 160, 140),
           'I': (150, 150, 146), 'B': (182, 170, 150), 'P': (150, 150, 150)}


def main():
    c = City()
    n = SIZE * SS
    im = Image.new('RGB', (n, n), (44, 84, 118))
    d = ImageDraw.Draw(im)
    k = n / (2.0 * MAP_HALF)

    def P(x, y):
        return ((x - (MAP_CX - MAP_HALF)) * k, ((MAP_CY + MAP_HALF) - y) * k)

    def rect(x0, y0, x1, y1, col):
        a = P(x0, y1)
        b = P(x1, y0)
        d.rectangle([a[0], a[1], b[0], b[1]], fill=col)

    # суша: песок по краю, дальше трава
    rect(c.land_x0, c.land_y0, c.land_x1, c.land_y1, (196, 180, 132))
    rect(c.land_x0 + 4, c.land_y0 + 26, c.land_x1 - 4, c.land_y1 - 4, (98, 122, 84))
    for (x0, y0, x1, y1, z) in c.extra_land:
        rect(x0, y0, x1, y1, (150, 132, 104))
    br = c.special.get('bridge')
    if br:
        rect(br['x'] - br['w'] / 2, br['y0'], br['x'] + br['w'] / 2, br['y1'], (70, 70, 74))
    # дороги
    rect(c.grid_x0, c.grid_y0, c.grid_x1, c.grid_y1, (58, 58, 62))
    for b in c.blocks:
        rect(b.x0, b.y0, b.x1, b.y1, ZONE_COL.get(b.zone, (110, 110, 110)))
    pond = c.special.get('pond')
    if pond:
        a = P(pond['x'] - pond['rx'], pond['y'] + pond['ry'])
        b = P(pond['x'] + pond['rx'], pond['y'] - pond['ry'])
        d.ellipse([a[0], a[1], b[0], b[1]], fill=(60, 110, 150))
    for b in c.buildings:
        zone = c.blocks[b.block].zone if 0 <= b.block < len(c.blocks) else 'I'
        col = BLD_COL.get(zone, (150, 150, 150))
        if b.name:
            col = (214, 196, 120)
        rect(b.x0, b.y0, b.x1, b.y1, col)
        a = P(b.x0, b.y1)
        bb = P(b.x1, b.y0)
        d.rectangle([a[0], a[1], bb[0], bb[1]], outline=(col[0] * 3 // 4, col[1] * 3 // 4, col[2] * 3 // 4))
    # осевые линии проспектов
    for key, s in c.segs.items():
        if not s['ave']:
            continue
        if s['kind'] == 'h':
            rect(s['a'], s['c'] - 0.35, s['b'], s['c'] + 0.35, (150, 140, 70))
        else:
            rect(s['c'] - 0.35, s['a'], s['c'] + 0.35, s['b'], (150, 140, 70))
    im = im.resize((SIZE, SIZE), Image.LANCZOS)
    out = os.path.join(ROOT, 'assets', 'tex', 'map.png')
    im.save(out, optimize=True)
    print('map written:', out, os.path.getsize(out), 'bytes')
    return out


if __name__ == '__main__':
    main()
