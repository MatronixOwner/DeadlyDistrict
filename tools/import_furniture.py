# -*- coding: utf-8 -*-
"""Мебель и бытовая техника для интерьеров.

Источник — «Pack of low poly psx style models» (Elbolilloduro): кресла и диваны, стулья, кровати, столы, лампы,
цветы, кухонная техника, сантехника.  Берётся из открытого сборника M3-org/retro3d-assets (он же
Miziziziz/Retro3DGraphicsCollection), где набор лежит готовыми файлами .glb.

    python tools/import_furniture.py fetch            скачать исходники в .cache/model_src/m3
    python tools/import_furniture.py all              собрать assets/models/furn/ (furn.bam, furn.json, текстуры)
    python tools/import_furniture.py sheet out.png [набор]   лист со всеми предметами набора и их именами

В исходных файлах предметы расставлены рядами, а дверцы, ящики и подушки — отдельные объекты.  Сборщик склеивает
соприкасающиеся объекты в один предмет, ставит его на пол серединой в начало координат и приводит оси к игровым
(Z вверх, лицом в -Y).  Текстуры материалов уменьшаются и складываются рядом с моделью.
"""
import hashlib
import io
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from import_psx import glb_read, acc_data, world_mats, ROOT, SRC          # noqa: E402

OUT = os.path.join(ROOT, 'assets', 'models', 'furn')
M3 = os.path.join(SRC, 'm3')
PACKS = ('armchair', 'chairs', 'deds_others', 'electronics_kitchen', 'bath_hygiene')
SKIP_MATS = ('Trans', 'Glass', 'Vidrio')            # прозрачные вставки: без них предметы выглядят так же
TEX_MAX = 128                                       # сторона текстуры материала, пикселей

# Предметы, которые нужны игре: имя в игре -> (набор, имя в наборе, поворот на 90° x N, чтобы лицо смотрело в -Y)
PICK = {
    # диваны и кресла
    'sofa_grey': ('armchair', 'Armchair_15', 0), 'sofa_brown': ('armchair', 'Armchair_11', 0),
    'sofa_black': ('armchair', 'Armchair_05', 0), 'sofa_beige': ('armchair', 'Armchair_08', 0),
    'sofa_blue': ('armchair', 'Armchair_10', 0), 'sofa_corner': ('armchair', 'Armchair_17', 0),
    'sofa_old': ('armchair', 'Armchair_22', 0), 'sofa_light': ('armchair', 'Armchair', 0),
    'armchair_grey': ('armchair', 'Armchair_07', 0), 'armchair_dark': ('armchair', 'Armchair_03', 0),
    'armchair_yellow': ('armchair', 'Armchair_06', 0), 'armchair_tall': ('armchair', 'Armchair_01', 0),
    'pouf': ('armchair', 'Armchair_14', 0),
    # стулья
    'chair_wood': ('chairs', 'Chair_03', 0), 'chair_slat': ('chairs', 'Chair_14', 0),
    'chair_soft': ('chairs', 'Chair_04', 0), 'chair_office': ('chairs', 'Chair_10', 0),
    'chair_metal': ('chairs', 'Chair_08', 0), 'chair_swivel': ('chairs', 'Chair_17', 0),
    'chair_plastic': ('chairs', 'Chair_18', 0), 'stool': ('chairs', 'Chair_21', 0),
    # кровати, тумбы, столы
    'bed_single': ('deds_others', 'Bed_03', 0), 'bed_grey': ('deds_others', 'Bed_04', 0),
    'bed_double': ('deds_others', 'Bed_09', 0), 'bed_cot': ('deds_others', 'Bed_08', 0),
    'bed_bunk': ('deds_others', 'Bed_06', 0), 'bed_wide': ('deds_others', 'Bed_02', 0),
    'nightstand': ('deds_others', 'Cajonera_01.001', 0), 'dresser': ('deds_others', 'Cajonera', 0),
    'table_wood': ('deds_others', 'Table_36', 0), 'table_small': ('deds_others', 'Table_37', 0),
    'table_orange': ('deds_others', 'Table_38', 0), 'table_round': ('deds_others', 'Table_40', 0),
    'table_dark': ('deds_others', 'Table_41', 0), 'table_side': ('deds_others', 'Table_42', 0),
    # свет, картины, цветы
    'lamp_table': ('deds_others', 'Lamps', 0), 'lamp_floor': ('deds_others', 'Lamps_01', 0),
    'lamp_pendant': ('deds_others', 'Lamps_05', 0), 'lamp_tube': ('deds_others', 'Lamps_06', 0),
    'painting_wide': ('deds_others', 'Paintings', 0), 'painting_a': ('deds_others', 'Paintings_01', 0),
    'painting_b': ('deds_others', 'Paintings_02', 0), 'painting_c': ('deds_others', 'Paintings_03', 0),
    'painting_d': ('deds_others', 'Paintings_04', 0), 'painting_e': ('deds_others', 'Paintings_05', 0),
    'painting_f': ('deds_others', 'Paintings_07', 0), 'painting_g': ('deds_others', 'Paintings_08', 0),
    'plant_tall': ('deds_others', 'Plants', 0), 'plant_a': ('deds_others', 'Plants_02', 0),
    'plant_b': ('deds_others', 'Plants_04', 0), 'plant_c': ('deds_others', 'Plants_05', 0),
    # кухня
    'fridge': ('electronics_kitchen', 'Refrigerator', 0), 'fridge_black': ('electronics_kitchen', 'Refrigerator_03', 0),
    'fridge_big': ('electronics_kitchen', 'Refrigerator_01', 0),
    'stove': ('electronics_kitchen', 'Stove_01', 0), 'stove_black': ('electronics_kitchen', 'Stove_02', 0),
    'stove_old': ('electronics_kitchen', 'Stove_05', 0),
    'microwave': ('electronics_kitchen', 'Microwave_02', 0), 'microwave_steel': ('electronics_kitchen', 'Microwave_03', 0),
    'coffee': ('electronics_kitchen', 'Coffee_maker_01', 0), 'pot': ('electronics_kitchen', 'Cooking_pot_01', 0),
    'toaster': ('electronics_kitchen', 'Toaster', 0), 'blender': ('electronics_kitchen', 'Blender_02', 0),
    'dish': ('electronics_kitchen', 'Dish_01', 0), 'cup': ('electronics_kitchen', 'Vaso_01', 0),
    # сантехника и хозяйство
    'toilet': ('bath_hygiene', 'Toilet', 0), 'washbasin': ('bath_hygiene', 'Washbasin_06', 0),
    'washbasin_cab': ('bath_hygiene', 'Washbasin_07', 0), 'washer': ('bath_hygiene', 'Washing_machine_03', 0),
    'trash': ('bath_hygiene', 'Trash_can_01', 0), 'basket': ('bath_hygiene', 'Dirty _clothes_01', 0),
    'mop': ('bath_hygiene', 'Mop', 0), 'broom': ('bath_hygiene', 'Broom', 0), 'bucket': ('bath_hygiene', 'Bote', 0),
}
SCALE = 0.85                    # набор сделан крупнее настоящей мебели: стул в нём выше метра двадцати
ALPHA_MATS = ('Plants',)        # листья: текстура с прозрачностью


def fetch():
    if not os.path.isdir(M3):
        raise SystemExit('сначала: python tools/gen_city.py fetch')
    subprocess.check_call(['git', 'sparse-checkout', 'add', '/Furniture/*.glb'], cwd=M3)


class Part(object):
    __slots__ = ('mat', 'pos', 'nrm', 'uv', 'idx')


def load_pack(name):
    """-> (предметы: имя -> [Part], картинки: материал -> bytes)."""
    g, b = glb_read(os.path.join(M3, 'Furniture', name + '.glb'))
    mats = world_mats(g)
    nodes = g['nodes']
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get('children', []):
            parent[c] = i
    images = {}
    mat_names = []
    for m in g.get('materials', []):
        mn = m.get('name', 'mat')
        mat_names.append(mn)
        t = m.get('pbrMetallicRoughness', {}).get('baseColorTexture')
        col = m.get('pbrMetallicRoughness', {}).get('baseColorFactor', [1, 1, 1, 1])
        if t is not None:
            im = g['images'][g['textures'][t['index']]['source']]
            bv = g['bufferViews'][im['bufferView']]
            off = bv.get('byteOffset', 0)
            images[mn] = bytes(b[off:off + bv['byteLength']])
        else:
            images[mn] = tuple(col[:3])
    objs = {}
    for i, n in enumerate(nodes):
        if 'mesh' not in n:
            continue
        p = parent.get(i)
        oname = nodes[p].get('name', 'obj%d' % p) if p is not None else n.get('name', 'obj%d' % i)
        M = mats[i]
        R = M[:3, :3]
        N = np.linalg.inv(R).T
        for prim in g['meshes'][n['mesh']]['primitives']:
            mn = mat_names[prim['material']] if 'material' in prim else 'mat'
            if mn in SKIP_MATS:
                continue
            at = prim['attributes']
            pos = acc_data(g, b, at['POSITION'])
            pos = pos @ R.T + M[:3, 3]
            nrm = acc_data(g, b, at['NORMAL']) @ N.T if 'NORMAL' in at else np.zeros_like(pos)
            ln = np.linalg.norm(nrm, axis=1)
            nrm = nrm / np.maximum(ln, 1e-9)[:, None]
            uv = acc_data(g, b, at['TEXCOORD_0']) if 'TEXCOORD_0' in at else np.zeros((len(pos), 2))
            idx = acc_data(g, b, prim['indices'], False).reshape(-1).astype(np.int64) if 'indices' in prim \
                else np.arange(len(pos))
            if np.linalg.det(R) < 0:
                idx = idx.reshape(-1, 3)[:, ::-1].reshape(-1)
            pt = Part()
            pt.mat = mn
            # glTF: Y вверх, предметы набора стоят лицом в -Z  ->  игра: Z вверх, лицо в -Y
            pt.pos = np.stack([-pos[:, 0], pos[:, 2], pos[:, 1]], 1)
            pt.nrm = np.stack([-nrm[:, 0], nrm[:, 2], nrm[:, 1]], 1)
            pt.uv = np.stack([uv[:, 0], 1.0 - uv[:, 1]], 1)
            pt.idx = idx
            objs.setdefault(oname, []).append(pt)
    return objs, images


def bbox(parts):
    lo = np.min([p.pos.min(0) for p in parts], 0)
    hi = np.max([p.pos.max(0) for p in parts], 0)
    return lo, hi


def group(objs, margin=0.02):
    """Склеить соприкасающиеся объекты (дверцы, ящики, подушки) в предметы.  -> имя -> [Part]"""
    names = sorted(objs)
    boxes = [bbox(objs[n]) for n in names]
    par = list(range(len(names)))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = boxes[i], boxes[j]
            if np.all(a[0] - margin <= b[1]) and np.all(b[0] - margin <= a[1]):
                par[find(i)] = find(j)
    res = {}
    for i, n in enumerate(names):
        res.setdefault(find(i), []).append(i)
    out = {}
    for members in res.values():
        vol = [float(np.prod(boxes[i][1] - boxes[i][0])) for i in members]
        main = names[members[int(np.argmax(vol))]]
        parts = []
        for i in members:
            parts += objs[names[i]]
        out[main] = parts
    return out


def settle(parts, turns=0):
    """Поставить предмет на пол серединой в начало координат; turns — повороты на 90° против часовой."""
    lo, hi = bbox(parts)
    c = np.array([(lo[0] + hi[0]) * 0.5, (lo[1] + hi[1]) * 0.5, lo[2]])
    res = []
    for p in parts:
        q = Part()
        q.mat, q.uv, q.idx = p.mat, p.uv, p.idx
        pos = p.pos - c
        nrm = p.nrm
        for _ in range(turns % 4):
            pos = np.stack([-pos[:, 1], pos[:, 0], pos[:, 2]], 1)
            nrm = np.stack([-nrm[:, 1], nrm[:, 0], nrm[:, 2]], 1)
        q.pos, q.nrm = pos, nrm
        res.append(q)
    return res


def geom_node(name, parts):
    """Предмет -> узел: по одному GeomNode на материал (имя узла = имя материала)."""
    from panda3d.core import (GeomVertexFormat, GeomVertexData, Geom, GeomTriangles, GeomNode, NodePath)
    root = NodePath(name)
    by_mat = {}
    for p in parts:
        by_mat.setdefault(p.mat, []).append(p)
    for mat in sorted(by_mat):
        vd = GeomVertexData(mat, GeomVertexFormat.getV3n3t2(), Geom.UHStatic)
        n = sum(len(p.pos) for p in by_mat[mat])
        vd.uncleanSetNumRows(n)
        arr = np.zeros((n, 8), dtype=np.float32)
        tr = GeomTriangles(Geom.UHStatic)
        base = 0
        for p in by_mat[mat]:
            k = len(p.pos)
            arr[base:base + k, 0:3] = p.pos
            arr[base:base + k, 3:6] = p.nrm
            arr[base:base + k, 6:8] = p.uv
            for a, b, c in (p.idx.reshape(-1, 3) + base):
                tr.addVertices(int(a), int(b), int(c))
            base += k
        vd.modifyArrayHandle(0).copyDataFrom(arr.tobytes())
        g = Geom(vd)
        g.addPrimitive(tr)
        gn = GeomNode(mat)
        gn.addGeom(g)
        root.attachNewNode(gn)
    return root


def tex_image(data, alpha=False):
    if isinstance(data, tuple):
        im = Image.new('RGB', (8, 8), tuple(int(max(0.0, min(1.0, c)) ** (1 / 2.2) * 255) for c in data))
        return im
    im = Image.open(io.BytesIO(data))
    im = im.convert('RGBA' if alpha and im.mode in ('RGBA', 'LA', 'P') else 'RGB')
    if max(im.size) > TEX_MAX:
        k = TEX_MAX / float(max(im.size))
        im = im.resize((max(8, int(im.size[0] * k)), max(8, int(im.size[1] * k))), Image.LANCZOS)
    return im


def packs():
    res = {}
    for name in PACKS:
        objs, images = load_pack(name)
        res[name] = (group(objs), images)
    return res


def listing():
    for name, (items, images) in packs().items():
        print('==', name, len(items))
        for k in sorted(items):
            lo, hi = bbox(items[k])
            s = hi - lo
            print('   %-28s %.2f x %.2f x %.2f  %s' % (k, s[0], s[1], s[2], ','.join(sorted(set(p.mat for p in items[k])))))


def build():
    """Собрать assets/models/furn: furn.bam (каждый предмет — узел со своим именем), furn.json, текстуры."""
    from panda3d.core import NodePath, loadPrcFileData
    loadPrcFileData('', 'window-type none\naudio-library-name null\n')
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))
    all_packs = packs()
    root = NodePath('furn')
    meta = {}
    used = {}                           # имя материала в игре -> (набор, материал)
    digests = {}                        # содержимое картинки -> имя материала в игре
    total = 0
    for name in sorted(PICK):
        pack, item, turns = PICK[name]
        items, images = all_packs[pack]
        if item not in items:
            raise SystemExit('в наборе %s нет предмета %s' % (pack, item))
        parts = settle(items[item], turns)
        for p in parts:
            p.pos = p.pos * SCALE
            data = images[p.mat]
            h = hashlib.md5(repr(data).encode() if isinstance(data, tuple) else data).hexdigest()
            tex = digests.get(h)
            if tex is None:
                tex = p.mat.lower().replace('.', '_').replace(' ', '_')
                while tex in used:
                    tex += 'x'
                digests[h] = tex
                used[tex] = (pack, p.mat)
            p.mat = tex
            total += len(p.idx) // 3
        lo, hi = bbox(parts)
        node = geom_node(name, parts)
        node.reparentTo(root)
        meta[name] = dict(w=round(float(hi[0] - lo[0]), 3), d=round(float(hi[1] - lo[1]), 3),
                          h=round(float(hi[2]), 3), tex=sorted(set(p.mat for p in parts)))
    size = 0
    alpha = []
    for tex, (pack, mat) in sorted(used.items()):
        im = tex_image(all_packs[pack][1][mat], mat in ALPHA_MATS)
        path = os.path.join(OUT, tex + '.png')
        if im.mode == 'RGBA':
            alpha.append(tex)
            im.save(path, optimize=True)
        else:
            im.quantize(96, method=Image.MEDIANCUT, dither=Image.NONE).save(path, optimize=True)
        size += os.path.getsize(path)
    root.writeBamFile(os.path.join(OUT, 'furn.bam'))
    with open(os.path.join(OUT, 'furn.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(items=meta, alpha=alpha), f, ensure_ascii=False, indent=0, sort_keys=True)
    print('мебель: %d предметов, %d треугольников, %d текстур (%d КБ), furn.bam %d КБ' % (
        len(meta), total, len(used), size // 1024, os.path.getsize(os.path.join(OUT, 'furn.bam')) // 1024))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if cmd == 'fetch':
        fetch()
    elif cmd == 'list':
        listing()
    elif cmd == 'all':
        build()


def sheet(out, only=None, cols=7, size=(1900, 1300)):
    """Контактный лист: все предметы набора рядами, подписи — имена в наборе (вид спереди-сверху, лицо в -Y)."""
    from panda3d.core import (loadPrcFileData, Filename, AmbientLight, DirectionalLight, LColor, TextNode, Texture,
                              OrthographicLens, PNMImage, StringStream)
    loadPrcFileData('', 'window-type offscreen\nload-display p3tinydisplay\nwin-size %d %d\naudio-library-name null\n'
                        'sync-video 0\ntextures-power-2 none\nnotify-level warning\n' % size)
    from direct.showbase.ShowBase import ShowBase
    base = ShowBase()
    base.disableMouse()
    al = AmbientLight('a')
    al.setColor(LColor(0.66, 0.66, 0.68, 1))
    dl = DirectionalLight('d')
    dl.setColor(LColor(0.7, 0.68, 0.64, 1))
    alp = base.render.attachNewNode(al)
    dlp = base.render.attachNewNode(dl)
    dlp.setHpr(-30, -50, 0)
    base.render.setLight(alp)
    base.render.setLight(dlp)
    base.setBackgroundColor(0.80, 0.80, 0.82)
    base.win.setClearColor(LColor(0.80, 0.80, 0.82, 1))
    n = 0
    for name, (items, images) in packs().items():
        if only and name != only:
            continue
        root = base.render.attachNewNode(name)
        texs = {}
        keys = sorted(items)
        big = [k for k in keys if max(bbox(items[k])[1] - bbox(items[k])[0]) > 0.3]
        step = 3.4 if name in ('armchair', 'deds_others') else 1.7
        for i, k in enumerate(big):
            np_ = geom_node(k, settle(items[k]))
            np_.reparentTo(root)
            cx, cy = (i % cols) * step, -(i // cols) * step * 1.25
            np_.setPos(cx, cy, 0)
            for gn in np_.getChildren():
                m = gn.getName()
                t = texs.get(m)
                if t is None:
                    im = tex_image(images[m])
                    buf = io.BytesIO()
                    im.save(buf, 'PNG')
                    pn = PNMImage()
                    pn.read(StringStream(buf.getvalue()), 'x.png')
                    t = texs[m] = Texture(m)
                    t.load(pn)
                gn.setTexture(t)
            tn = TextNode('t')
            tn.setText(k.replace('Armchair', 'A').replace('Refrigerator', 'Fridge'))
            tn.setTextColor(0.05, 0.05, 0.05, 1)
            tn.setAlign(TextNode.ACenter)
            tp = root.attachNewNode(tn)
            tp.setScale(step * 0.085)
            tp.setPos(cx, cy - step * 0.52, 0.02)
            tp.setHpr(0, -50, 0)
            tp.setLightOff()
        rows = (len(big) + cols - 1) // cols
        lens = OrthographicLens()
        w = cols * step + 0.6
        lens.setFilmSize(w, w * size[1] / size[0])
        lens.setNearFar(1, 200)
        base.cam.node().setLens(lens)
        cxm, cym = (cols - 1) * step * 0.5, -(rows - 1) * step * 1.25 * 0.5
        base.cam.setPos(cxm, cym - 40, 34)
        base.cam.lookAt(cxm, cym - 0.3, 0.3)
        base.graphicsEngine.renderFrame()
        base.graphicsEngine.renderFrame()
        p = out.replace('.png', '_%s.png' % name)
        base.win.saveScreenshot(Filename(p))
        print('saved', p, len(big))
        root.removeNode()
        n += 1


if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'sheet':
    sheet(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
