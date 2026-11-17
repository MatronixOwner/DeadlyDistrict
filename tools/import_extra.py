# -*- coding: utf-8 -*-
"""Мусор для улиц и плашки интерфейса из бесплатных наборов с itch.io.

  * PSX Waste (Daniel Jurys, CC0, https://daniel-jurys.itch.io/psx-waste) — мусорный контейнер, бочка, мешок
    с мусором, картонная коробка, бутылка и мятая банка.  Модели маленькие (12–92 треугольника), поэтому
    в игру они попадают не файлами .bam, а списком треугольников в assets/models/props.json: город собирает
    уличные предметы в общие сетки кварталов (game/props.py), и модели ложатся туда же;
  * Free PSX UI (ROHHSA, CC0, https://rohhsa.itch.io/free-psx-ui) — плашки без надписей (Text-Block) нескольких
    расцветок: фон меню, рамка мини-карты, полоса больших сообщений, экран загрузки;
  * ржавый остов машины для пустырей — модель assets/models/veh/wreck.bam (набор PSX Style Cars, GGBot, CC0,
    её собирает tools/import_psx.py): раньше остов на пустыре был сложен из четырёх коробок.

    python tools/import_vehicles.py fetch     # исходники в .cache/model_src/new (нужен gh)
    python tools/import_extra.py              # всё
    python tools/import_extra.py props | ui
    python tools/import_extra.py --sheet out.png

Игре исходники не нужны.
"""
import io
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mesh_src as ms                                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, '.cache', 'model_src', 'new')
TEX = os.path.join(ROOT, 'assets', 'tex')
OUT = os.path.join(ROOT, 'assets', 'models', 'props.json')

# имя в игре -> (файл, масштаб по (ширине, длине, высоте)).  Оси игры: Y — длинная сторона контейнера, Z — вверх.
PROPS = {
    'dumpster': ('dumpster', (0.80, 0.80, 0.80)),           # 1,43 × 2,04 × 1,38 м
    'barrel': ('barrel', (0.75, 0.75, 0.90)),               # бочка на 200 л: 0,60 × 0,90 м
    'bag': ('trash-bag', (0.62, 0.62, 0.62)),               # мешок по пояс: 0,67 м
    'box': ('cardboard-box', (1.50, 1.50, 1.50)),           # 0,75 × 0,45 × 0,30 м
    'bottle': ('glass-bottle', (0.95, 0.95, 0.95)),         # 0,285 м
    'can': ('crumpled-can', (0.55, 0.55, 0.55)),            # сплющенная банка 0,17 × 0,12 м
}

# расцветки плашек: имя текстуры -> номер набора
SKINS = {'ui_panel': '05', 'ui_band': '01', 'ui_plate': '02', 'ui_alert': '08'}
UI_SIZE = (512, 128)


def bleed(a):
    """RGBA -> RGB: прозрачные точки получают цвет ближайших непрозрачных."""
    rgb = a[..., :3].astype(np.float64)
    ok = a[..., 3] > 127
    for _ in range(max(a.shape[:2])):
        if ok.all():
            break
        acc = np.zeros_like(rgb)
        cnt = np.zeros(ok.shape)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            m = np.roll(ok, (dy, dx), (0, 1))
            acc += np.roll(rgb, (dy, dx), (0, 1)) * m[..., None]
            cnt += m
        new = ~ok & (cnt > 0)
        rgb[new] = acc[new] / cnt[new][:, None]
        ok = ok | new
    return np.clip(rgb + 0.5, 0, 255).astype(np.uint8)


def wreck():
    """Остов машины: кузов из wreck.bam, длиной вдоль X (как прежний остов из коробок), 4,6 м."""
    from panda3d.core import Filename, GeomVertexReader, loadPrcFileData
    loadPrcFileData('', 'window-type none\naudio-library-name null\n')
    from panda3d.core import Loader, LoaderOptions, NodePath
    veh = os.path.join(ROOT, 'assets', 'models', 'veh')
    root = NodePath(Loader.getGlobalPtr().loadSync(Filename.fromOsSpecific(os.path.join(veh, 'wreck.bam')), LoaderOptions()))
    pts, uvs = [], []
    for gp in root.findAllMatches('**/+GeomNode'):
        mat = gp.getMat(root)
        for i in range(gp.node().getNumGeoms()):
            geom = gp.node().getGeom(i).decompose()
            vd = geom.getVertexData()
            rv, rt = GeomVertexReader(vd, 'vertex'), GeomVertexReader(vd, 'texcoord')
            vs, ts = [], []
            while not rv.isAtEnd():
                q = mat.xformPoint(rv.getData3())
                vs.append((q.x, q.y, q.z))
                t = rt.getData2()
                ts.append((t.x, t.y))
            for k in range(geom.getNumPrimitives()):
                prim = geom.getPrimitive(k)
                for f in range(prim.getNumPrimitives()):
                    for j in range(prim.getPrimitiveStart(f), prim.getPrimitiveEnd(f)):
                        pts.append(vs[prim.getVertex(j)])
                        uvs.append(ts[prim.getVertex(j)])
    v = np.array(pts)
    k = 4.6 / float(np.ptp(v[:, 1]))
    v = np.stack([v[:, 1], -v[:, 0], v[:, 2]], axis=1) * k            # нос — вдоль +X
    v[:, 2] -= v[:, 2].min()
    tv = v.reshape(-1, 3, 3)
    uv = np.array(uvs).reshape(-1, 3, 2)
    im = Image.open(os.path.join(veh, 'wreck.png')).convert('RGB')
    im.info.clear()                                                     # без цветового профиля исходника
    im.save(os.path.join(TEX, 'px_wreck.png'), optimize=True)
    return tv, uv, v


def props():
    meta = {}
    tv, uv, v = wreck()
    half = np.abs(v).max(0)
    meta['wreck'] = dict(tex='px_wreck', tris=int(len(tv)), size=[round(float(half[0]), 3), round(float(half[1]), 3),
                                                               round(float(v[:, 2].max()), 3)],
                         v=[round(float(q), 4) for q in np.concatenate([tv, uv], axis=2).reshape(-1)])
    print('  %-9s %3d треугольников  %.2f × %.2f × %.2f м' % ('wreck', len(tv), half[0] * 2, half[1] * 2, v[:, 2].max()))
    for name, (fn, scale) in PROPS.items():
        parts, imgs = ms.read_glb(os.path.join(SRC, 'psx_waste', fn + '.glb'))
        assert len(parts) == 1 and len(imgs) == 1, (name, len(parts), len(imgs))
        p = parts[0]
        # glTF: Y вверх.  Круговая перестановка осей (без зеркала): X' = Z, Y' = X, Z' = Y
        v = p.verts[:, (2, 0, 1)] * np.array(scale)
        mn, mx = v.min(0), v.max(0)
        v[:, 0] -= (mn[0] + mx[0]) * 0.5
        v[:, 1] -= (mn[1] + mx[1]) * 0.5
        v[:, 2] -= mn[2]
        tv = v[p.tris]                                                  # (n, 3, 3)
        uv = p.uvs                                                      # (n, 3, 2), V вверх
        assert uv.min() > -0.01 and uv.max() < 1.01, (name, uv.min(), uv.max())
        # вырожденные треугольники не нужны
        area = np.linalg.norm(np.cross(tv[:, 1] - tv[:, 0], tv[:, 2] - tv[:, 0]), axis=1)
        keep = area > 1e-9
        tv, uv = tv[keep], uv[keep]
        raw = list(imgs.values())[0]
        im = Image.open(io.BytesIO(raw)) if isinstance(raw, (bytes, bytearray)) else Image.open(raw)
        im = im.convert('RGBA')
        a = np.asarray(im)
        # прозрачны у исходников только пустые места развёртки; чтобы у края островков не подмешивался чужой
        # цвет (сглаживание, мип-уровни), заливаем пустоту цветом ближайших точек
        rgb = Image.fromarray(bleed(a), 'RGB')
        rgb.save(os.path.join(TEX, 'px_%s.png' % name), optimize=True)
        flat = np.concatenate([tv, uv], axis=2).reshape(-1)             # x y z u v на вершину
        half = np.abs(v).max(0)
        meta[name] = dict(tex='px_' + name, tris=int(len(tv)), size=[round(float(half[0]), 3), round(float(half[1]), 3),
                                                                     round(float(v[:, 2].max()), 3)],
                          v=[round(float(q), 4) for q in flat])
        print('  %-9s %3d треугольников  %.2f × %.2f × %.2f м  текстура %dx%d' % (
            name, len(tv), half[0] * 2, half[1] * 2, v[:, 2].max(), im.size[0], im.size[1]))
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(meta, sort_keys=True, separators=(',', ':')).replace('},"', '},\n"'))
        f.write('\n')
    print('  %s  %d байт' % (os.path.relpath(OUT, ROOT), os.path.getsize(OUT)))


def ui():
    for name, skin in SKINS.items():
        im = Image.open(os.path.join(SRC, 'rohhsa_ui', 'Skin%s-Cropped_Text-Block.png' % skin)).convert('RGB')
        box = im.getbbox()                                              # ниже плашки — чёрное поле
        assert box[0] == 0 and box[1] == 0 and box[2] == im.size[0], (name, box)
        im = im.crop(box).resize(UI_SIZE, Image.LANCZOS)
        im.info.clear()                                                 # без цветового профиля исходника
        im.save(os.path.join(TEX, name + '.png'), optimize=True)
        print('  %-9s набор %s  %dx%d' % (name, skin, im.size[0], im.size[1]))


def sheet(path):
    names = sorted(SKINS)
    W = Image.new('RGB', (UI_SIZE[0] * 2 + 30, (UI_SIZE[1] + 10) * 2 + 10 + 256), (60, 20, 60))
    for i, n in enumerate(names):
        W.paste(Image.open(os.path.join(TEX, n + '.png')), (10 + (i % 2) * (UI_SIZE[0] + 10), 10 + (i // 2) * (UI_SIZE[1] + 10)))
    for i, n in enumerate(sorted(PROPS)):
        W.paste(Image.open(os.path.join(TEX, 'px_%s.png' % n)).resize((160, 160), Image.NEAREST), (10 + i * 170, 300))
    W.save(path)


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--sheet' in args:
        sheet(args[args.index('--sheet') + 1])
    else:
        if not args or 'props' in args:
            props()
        if not args or 'ui' in args:
            ui()
