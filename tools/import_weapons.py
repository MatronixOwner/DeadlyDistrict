# -*- coding: utf-8 -*-
"""Оружие в стиле PS1 — из открытого сборника M3-org/retro3d-assets (папка Weapons).

    pip install blender-asset-tracer numpy pillow panda3d
    python tools/import_psx.py fetch                 # заодно скачивает и сборник (в .cache/model_src/m3)
    python tools/import_weapons.py fetch             # докачать папку Weapons
    python tools/import_weapons.py all               # assets/models/weapons/*.bam, *.png и запись в models.json
    python tools/import_weapons.py sheet out.png     # все модели сбоку, с линейкой (для подбора точки хвата)

Исходники лежат в .blend (Blender 2.8–2.9) и .glb; .blend читается напрямую (tools/blend_read.py).
Каждая модель приводится к осям игры: ствол вдоль +Y, верх +Z, начало координат — там, где рукоять
лежит в ладони; длина — настоящая, в метрах.  Где у модели рукоять и дуло, записано в таблице WEAPONS
долями длины и высоты модели (их удобно читать с листа `sheet`).
"""
import json
import math
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blend_read                                                         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, '.cache', 'model_src', 'm3')
OUT = os.path.join(ROOT, 'assets', 'models', 'weapons')
REPO = 'https://github.com/M3-org/retro3d-assets'

# имя в игре -> описание
#   src      файл в папке Weapons сборника
#   objs     объекты из файла (None — все)
#   tex      текстура (путь от папки Weapons)
#   fwd      куда в исходнике смотрит ствол: '+x', '-x', '+y', '-y'
#   up       где у исходника верх: '+z' по умолчанию
#   length   настоящая длина, м
#   grip     точка хвата: (доля длины от приклада к дулу, доля высоты снизу вверх)
#   muzzle   дуло: (доля длины, доля высоты)
#   tex_size сторона текстуры в игре
def suppressor(length=0.15, radius=0.017):
    """Глушитель на дуло: шестигранная труба.  Красится тёмной точкой текстуры самого пистолета."""
    def make(parts, total, height, spec):
        mz = ((spec['muzzle'][0] - spec['grip'][0]) * total, (spec['muzzle'][1] - spec['grip'][1]) * height)
        y0, y1, zc = mz[0] - 0.012, mz[0] + length, mz[1]
        ring = [(math.cos(k * math.pi / 3.0) * radius, math.sin(k * math.pi / 3.0) * radius) for k in range(6)]
        v = []
        for y in (y0, y1):
            for (x, z) in ring:
                v.append((x, y, zc + z))
        faces = [[k, (k + 1) % 6, 6 + (k + 1) % 6, 6 + k] for k in range(6)]
        faces.append([5, 4, 3, 2, 1, 0])
        faces.append([6, 7, 8, 9, 10, 11])
        uv = spec.get('dark_uv', (0.5, 0.5))
        return [(np.array(v), faces, [[uv] * len(f) for f in faces])]
    return make


# Таблица моделей.  Доли (grip, muzzle) считаются от приклада к дулу и снизу вверх — как на листе `sheet`.
WEAPONS = {
    'pistol': dict(src='low-poly-glock/glock.glb', objs=None, tex='low-poly-glock/glock.png',
                   fwd='-x', length=0.205, grip=(0.17, 0.36), muzzle=(1.0, 0.86)),
    'silenced': dict(src='low-poly-glock/glock.glb', objs=None, tex='low-poly-glock/glock.png',
                     fwd='-x', length=0.205, grip=(0.17, 0.36), muzzle=(1.0, 0.86), extra=[suppressor()],
                     dark_uv=(0.30, 0.85), muzzle_add=0.15),
    'uzi': dict(src='Heavy Weapons Pack/weaponPack.blend', objs=['Mauser', 'MauserClip'], tex='Heavy Weapons Pack/mauser.png',
                fwd='+x', length=0.42, grip=(0.10, 0.45), muzzle=(1.0, 0.95)),
    'shotgun': dict(src='Guns/You see Ivan Pack/weapon pack.blend', objs=['Cube.003'],
                    tex='Guns/You see Ivan Pack/textures/shotgun.png',
                    fwd='+x', length=0.98, grip=(0.31, 0.62), muzzle=(1.0, 0.88)),
    'double': dict(src='DoubleBarrelShotgun/DoubleBarrelShotgun.blend', objs=['Barrel', 'Base', 'Trigger'],
                   tex='DoubleBarrelShotgun/DoubleBarrel.png', fwd='-y', length=1.06, grip=(0.28, 0.62),
                   muzzle=(1.0, 0.88), tex_size=128),
    'ak': dict(src='Guns/You see Ivan Pack/weapon pack.blend', objs=['Cube.001'], tex='Guns/You see Ivan Pack/textures/ak74.png',
               fwd='+x', length=0.94, grip=(0.37, 0.36), muzzle=(1.0, 0.72)),
    'm4': dict(src='M4A1/M4A1.blend', objs=None, tex='M4A1/M4A1Diffuse.png',
               fwd='+y', length=0.85, grip=(0.27, 0.34), muzzle=(1.0, 0.70), tex_size=256),
    'sniper': dict(src='Guns/You see Ivan Pack/weapon pack.blend', objs=['Cube'],
                   tex='Guns/You see Ivan Pack/textures/sniper.png',
                   fwd='+x', length=1.22, grip=(0.37, 0.30), muzzle=(1.0, 0.60)),
    'rocket': dict(src='Heavy Weapons Pack/weaponPack.blend', objs=['Bazooka'], tex='Heavy Weapons Pack/bazooka.png',
                   fwd='-x', length=1.02, grip=(0.46, 0.28), muzzle=(1.0, 0.55)),
    'knife': dict(src='Heavy Weapons Pack/weaponPack.blend', objs=['Cylinder'], tex='Heavy Weapons Pack/knife.png',
                  fwd='+x', length=0.30, grip=(0.24, 0.55), muzzle=(1.0, 0.45)),
}


def run(cmd, **kw):
    print('  $', ' '.join(cmd))
    subprocess.check_call(cmd, **kw)


def fetch():
    if not os.path.isdir(os.path.join(SRC, '.git')):
        os.makedirs(os.path.dirname(SRC), exist_ok=True)
        run(['git', 'clone', '--depth', '1', '--filter=blob:none', '--sparse', REPO, SRC])
    run(['git', 'sparse-checkout', 'add', '/Weapons/'], cwd=SRC)


AX = {'+x': (0, 1), '-x': (0, -1), '+y': (1, 1), '-y': (1, -1), '+z': (2, 1), '-z': (2, -1)}


def load_source(spec):
    """-> список (вершины (n,3), грани, uv граней) в исходных осях."""
    path = os.path.join(SRC, 'Weapons', spec['src'])
    out = []
    if path.endswith('.blend'):
        for m in blend_read.read(path):
            if spec.get('objs') and m.name not in spec['objs']:
                continue
            out.append((np.array(m.verts), m.faces, m.uvs))
    else:
        from import_psx import glb_read, acc_data, world_mats
        g, b = glb_read(path)
        mats = world_mats(g)
        for ni, node in enumerate(g['nodes']):
            if 'mesh' not in node:
                continue
            if spec.get('objs') and node.get('name') not in spec['objs']:
                continue
            for prim in g['meshes'][node['mesh']]['primitives']:
                pos = acc_data(g, b, prim['attributes']['POSITION']).astype(np.float64)
                uv = acc_data(g, b, prim['attributes']['TEXCOORD_0']).astype(np.float64)
                idx = acc_data(g, b, prim['indices'], as_float=False).reshape(-1, 3)
                w = np.c_[pos, np.ones(len(pos))].dot(mats[ni].T)[:, :3]
                # glTF: Y вверх, -Z вперёд  ->  Blender: Z вверх
                w = np.c_[w[:, 0], -w[:, 2], w[:, 1]]
                faces = [[int(i) for i in tri] for tri in idx]
                uvs = [[(float(uv[i][0]), 1.0 - float(uv[i][1])) for i in tri] for tri in idx]
                out.append((w, faces, uvs))
    if not out:
        raise RuntimeError('нет объектов: %s' % spec['src'])
    return out


def to_game(spec, parts):
    """Привести к осям игры и настоящему размеру.  -> (parts, длина, высота)"""
    fa, fs = AX[spec['fwd']]
    ua, us = AX[spec.get('up', '+z')]
    ra = 3 - fa - ua
    allv = np.concatenate([p[0] for p in parts])
    f = allv[:, fa] * fs
    u = allv[:, ua] * us
    f0, f1, u0, u1 = f.min(), f.max(), u.min(), u.max()
    k = spec['length'] / (f1 - f0)
    gx = f0 + (f1 - f0) * spec['grip'][0]
    gz = u0 + (u1 - u0) * spec['grip'][1]
    r_mid = (allv[:, ra].min() + allv[:, ra].max()) * 0.5
    # правая тройка: right = fwd x up
    e = [np.zeros(3), np.zeros(3), np.zeros(3)]
    e[1][fa] = fs
    e[2][ua] = us
    e[0] = np.cross(e[1], e[2])
    flip = 1.0
    res = []
    for (v, faces, uvs) in parts:
        x = (v.dot(e[0]) - r_mid * float(e[0][ra])) * k
        y = (v[:, fa] * fs - gx) * k
        z = (v[:, ua] * us - gz) * k
        res.append((np.c_[x, y, z], faces, uvs))
    return res, (f1 - f0) * k, (u1 - u0) * k


def pot(n):
    """Ближайшая степень двойки: текстуры с другими сторонами принимает не всякая видеокарта."""
    p = 1
    while p * 2 <= n * 1.42:
        p *= 2
    return p


def build_node(name, parts, tex_path, tex_size=None):
    from panda3d.core import (GeomVertexFormat, GeomVertexData, GeomVertexWriter, Geom, GeomTriangles, GeomNode,
                              NodePath, Texture, SamplerState, Filename, PNMImage)
    vd = GeomVertexData(name, GeomVertexFormat.getV3n3t2(), Geom.UHStatic)
    vw, nw, tw = (GeomVertexWriter(vd, n) for n in ('vertex', 'normal', 'texcoord'))
    tris = GeomTriangles(Geom.UHStatic)
    n = 0
    for (v, faces, uvs) in parts:
        for fi, face in enumerate(faces):
            pts = [v[i] for i in face]
            # нормаль грани (по Ньюэллу — годится и для невыпуклых)
            nx = ny = nz = 0.0
            for i in range(len(pts)):
                a, b = pts[i], pts[(i + 1) % len(pts)]
                nx += (a[1] - b[1]) * (a[2] + b[2])
                ny += (a[2] - b[2]) * (a[0] + b[0])
                nz += (a[0] - b[0]) * (a[1] + b[1])
            ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            for i, p in enumerate(pts):
                vw.addData3(float(p[0]), float(p[1]), float(p[2]))
                nw.addData3(nx / ln, ny / ln, nz / ln)
                uv = uvs[fi][i] if uvs else (0.0, 0.0)
                tw.addData2(float(uv[0]), float(uv[1]))
            for i in range(1, len(pts) - 1):
                tris.addVertices(n, n + i, n + i + 1)
            n += len(pts)
    geom = Geom(vd)
    geom.addPrimitive(tris)
    gn = GeomNode('skin')
    gn.addGeom(geom)
    root = NodePath(name)
    np_ = root.attachNewNode(gn)
    np_.setTwoSided(True)                        # у части моделей грани вывернуты, а оружие маленькое
    if tex_path:
        tex = Texture(name)
        img = PNMImage()
        img.read(Filename.fromOsSpecific(tex_path))
        pw, ph = pot(img.getXSize()), pot(img.getYSize())
        if (pw, ph) != (img.getXSize(), img.getYSize()):
            big = PNMImage(pw, ph, img.getNumChannels())
            big.quickFilterFrom(img)
            img = big
        tex.load(img)
        tex.setMagfilter(SamplerState.FTNearest)
        tex.setMinfilter(SamplerState.FTNearest)
        np_.setTexture(tex)
    return root


def measure(spec):
    parts = load_source(spec)
    return to_game(spec, parts)


def _panda(w=1500, h=420):
    from panda3d.core import loadPrcFileData
    loadPrcFileData('', 'window-type offscreen\nload-display p3tinydisplay\nwin-size %d %d\naudio-library-name null\n'
                        'sync-video 0\ntextures-power-2 none\nnotify-level warning\nmodel-cache-dir\n' % (w, h))
    from direct.showbase.ShowBase import ShowBase
    base = ShowBase()
    base.disableMouse()
    return base


def sheet(out, names=None):
    """Все модели сбоку: слева приклад, справа дуло; сетка — десятые доли длины и высоты."""
    from panda3d.core import OrthographicLens, Filename
    from PIL import Image, ImageDraw
    base = _panda()
    lens = OrthographicLens()
    base.cam.node().setLens(lens)
    base.setBackgroundColor(0.5, 0.52, 0.56)
    tiles = []
    for name in (names or sorted(WEAPONS)):
        spec = WEAPONS[name]
        raw = dict(spec, grip=(0.0, 0.0))
        parts, length, height = to_game(dict(raw, length=1.0), load_source(spec))
        node = build_node(name, parts, os.path.join(SRC, 'Weapons', spec['tex']) if spec.get('tex') else None)
        node.reparentTo(base.render)
        node.setLightOff()
        W, H = 1500, 420
        film = max(1.25, (height + 0.12) * W / H)
        lens.setFilmSize(film, film * H / W)
        cx, cz = 0.5, height * 0.5
        base.cam.setPos(-5.0, cx, cz)                # с левого борта: дуло (+Y) на картинке справа
        base.cam.lookAt(0.0, cx, cz)
        base.graphicsEngine.renderFrame()
        base.graphicsEngine.renderFrame()
        tmp = os.path.join(os.environ.get('TMPDIR', '/tmp'), '_wpn.png')
        base.win.saveScreenshot(Filename.fromOsSpecific(tmp))
        im = Image.open(tmp).convert('RGB')
        d = ImageDraw.Draw(im)
        sx = W / film

        def px(y, z):
            return (W * 0.5 + (y - cx) * sx, H * 0.5 - (z - cz) * sx)
        for i in range(11):
            a = px(i / 10.0, 0.0)
            b = px(i / 10.0, height)
            d.line([a, b], fill=(255, 255, 0) if i % 5 == 0 else (255, 255, 255), width=1)
            d.text((a[0] - 6, a[1] + 4), '%.1f' % (i / 10.0), fill=(255, 255, 0))
        for i in range(11):
            a = px(0.0, height * i / 10.0)
            b = px(1.0, height * i / 10.0)
            d.line([a, b], fill=(120, 255, 120) if i % 5 == 0 else (200, 200, 200), width=1)
            d.text((a[0] - 26, a[1] - 5), '%.1f' % (i / 10.0), fill=(120, 255, 120))
        g = px(spec['grip'][0], height * spec['grip'][1])
        m = px(spec['muzzle'][0], height * spec['muzzle'][1])
        d.ellipse([g[0] - 6, g[1] - 6, g[0] + 6, g[1] + 6], outline=(255, 0, 0), width=2)
        d.ellipse([m[0] - 5, m[1] - 5, m[0] + 5, m[1] + 5], outline=(0, 200, 255), width=2)
        d.text((8, 6), '%s   %s   %.2f m, fwd %s' % (name, spec['src'].split('/')[-1], spec['length'], spec['fwd']), fill=(255, 255, 255))
        tiles.append(im)
        node.removeNode()
    sh = Image.new('RGB', (1500, 420 * len(tiles)))
    for i, t in enumerate(tiles):
        sh.paste(t, (0, 420 * i))
    sh.save(out)
    print('лист:', out)


def do_all():
    from panda3d.core import Filename
    from PIL import Image
    base = _panda(64, 64)
    os.makedirs(OUT, exist_ok=True)
    meta_path = os.path.join(ROOT, 'assets', 'models', 'models.json')
    with open(meta_path, encoding='utf-8') as f:
        meta = json.load(f)
    wm = meta.setdefault('weapons', {})
    for name in sorted(WEAPONS):
        spec = WEAPONS[name]
        parts, length, height = to_game(spec, load_source(spec))
        tex_out = None
        if spec.get('tex'):
            im = Image.open(os.path.join(SRC, 'Weapons', spec['tex'])).convert('RGB')
            size = spec.get('tex_size', 256)
            tw = min(size, pot(im.size[0]))
            th = min(size, pot(im.size[1]))
            if (tw, th) != im.size:
                im = im.resize((tw, th), Image.LANCZOS if (tw < im.size[0] or th < im.size[1]) else Image.NEAREST)
            tex_out = os.path.join(OUT, name + '.png')
            im.quantize(64, method=Image.MEDIANCUT, dither=Image.NONE).save(tex_out, optimize=True)
        for extra in spec.get('extra', ()):
            parts = parts + extra(parts, length, height, spec)
        node = build_node(name, parts, tex_out)
        tex = node.find('**/skin').getTexture()
        if tex is not None:
            tex.setFilename(Filename(name + '.png'))         # путь рядом с моделью
            tex.setFullpath(Filename(name + '.png'))
        node.writeBamFile(Filename.fromOsSpecific(os.path.join(OUT, name + '.bam')))
        mz = ((spec['muzzle'][0] - spec['grip'][0]) * length + spec.get('muzzle_add', 0.0),
              (spec['muzzle'][1] - spec['grip'][1]) * height)
        wm[name] = dict(length=round(length + spec.get('muzzle_add', 0.0), 3),
                        muzzle=[0.0, round(mz[0], 3), round(mz[1], 3)], tex=bool(tex_out))
        tris = sum(len(f) - 2 for p in parts for f in p[1])
        print('  %-10s длина %.2f м, высота %.2f м, треугольников %d' % (name, length, height, tris))
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1, sort_keys=True)
    print('готово:', OUT)


# значки оружия для интерфейса: имя значка -> файл модели в assets/models/weapons
ICONS = {'w_pistol': 'pistol', 'w_silenced': 'silenced', 'w_uzi': 'uzi', 'w_shotgun': 'shotgun', 'w_double': 'double',
         'w_ak': 'ak', 'w_m4': 'm4', 'w_sniper': 'sniper', 'w_rocket': 'rocket', 'w_knife': 'knife', 'w_bat': 'bat',
         'w_grenade': 'grenade', 'w_molotov': 'molotov'}
ICON_W, ICON_H = 128, 64


def icons():
    """Значки оружия — белые силуэты самих моделей (вид сбоку), assets/tex/w_*.png."""
    from panda3d.core import OrthographicLens, Filename, NodePath
    from PIL import Image
    W, H = 1024, 512
    base = _panda(W, H)
    lens = OrthographicLens()
    base.cam.node().setLens(lens)
    base.setBackgroundColor(0, 0, 0)
    out_dir = os.path.join(ROOT, 'assets', 'tex')
    for icon, name in sorted(ICONS.items()):
        m = base.loader.loadModel(Filename.fromOsSpecific(os.path.join(OUT, name + '.bam')), noCache=True)
        root = NodePath('r')
        m.reparentTo(root)
        if name in ('bat', 'knife'):
            m.setP(-20.0)                           # холодное оружие — наискось, как его рисуют на значках
        elif name in ('grenade', 'molotov'):
            m.setP(90.0)                            # граната и бутылка стоят вертикально
        root.reparentTo(base.render)
        root.setLightOff()
        root.setTextureOff(10)
        root.setColor(1, 1, 1, 1, 10)
        mn, mx = root.getTightBounds()
        cy, cz = (mn.y + mx.y) * 0.5, (mn.z + mx.z) * 0.5
        sy, sz = (mx.y - mn.y) * 1.12, (mx.z - mn.z) * 1.12
        film = max(sy, sz * W / H)
        lens.setFilmSize(film, film * H / W)
        lens.setNearFar(0.1, 50.0)
        base.cam.setPos(-10.0, cy, cz)              # с левого борта: дуло смотрит вправо
        base.cam.lookAt(0.0, cy, cz)
        base.graphicsEngine.renderFrame()
        base.graphicsEngine.renderFrame()
        tmp = os.path.join(os.environ.get('TMPDIR', '/tmp'), '_icon.png')
        base.win.saveScreenshot(Filename.fromOsSpecific(tmp))
        a = Image.open(tmp).convert('L').resize((ICON_W, ICON_H), Image.LANCZOS)
        im = Image.new('RGBA', (ICON_W, ICON_H), (255, 255, 255, 0))
        im.putalpha(a)
        im.save(os.path.join(out_dir, icon + '.png'), optimize=True)
        root.removeNode()
    print('значки: %d -> %s' % (len(ICONS), out_dir))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if cmd == 'fetch':
        fetch()
    elif cmd == 'sheet':
        sheet(sys.argv[2], sys.argv[3:] or None)
    elif cmd == 'icons':
        icons()
    else:
        do_all()
