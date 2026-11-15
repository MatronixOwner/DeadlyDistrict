# -*- coding: utf-8 -*-
"""Импорт моделей в стиле PS1: люди со скелетной анимацией и машины.

Нужен только тому, кто хочет пересобрать или заменить модели; игра читает готовые файлы из
assets/models и от этого скрипта не зависит.

    pip install panda3d-gltf numpy pillow
    npm install @gltf-transform/core @gltf-transform/extensions meshoptimizer   (для анимаций)
    python tools/import_psx.py fetch        # скачать исходники в .cache/model_src (git)
    python tools/import_psx.py all          # люди, анимации, машины

Откуда что берётся (лицензии — в assets/models/CREDITS.md):
  * люди — «Characters PSX» (Elbolilloduro) в виде, подготовленном проектом Mesh2Motion:
    модели уже привязаны к скелету, там же 200+ клипов анимации (CC0);
  * машины — «PSX Style Cars» (GGBot, CC0).

Что делает импорт:
  * все персонажи приводятся к ОДНОМУ скелету (у исходных моделей кости стоят чуть по-разному),
    поэтому клипы анимации общие для всех и занимают сотни килобайт, а не десятки мегабайт;
  * привязка к скелету упрощается (не больше двух костей на вершину) — анимация считается быстрее;
  * у машин колёса отделяются от кузова, чтобы они могли вращаться и поворачивать;
  * всё приводится к осям игры: Z вверх, взгляд персонажа и нос машины — к +Y.
"""
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, '.cache', 'model_src')
OUT = os.path.join(ROOT, 'assets', 'models')

M2M_REPO = ('https://github.com/Mesh2Motion/mesh2motion-app', ['static/assets/human'])
CARS_REPO = ('https://github.com/Raccoon-Formality/Parking_Ticket_Mayhem', ['assets/3d/psx_cars'])

# персонажи: имя в игре -> файл Mesh2Motion (static/assets/human/variations/<файл>.glb)
CHARS = {
    'm_shirt': 'psx-05', 'm_red': 'psx-06', 'm_grey': 'psx-10', 'm_leather': 'psx-15', 'm_old': 'psx-32',
    'f_goth': 'psx-female-08', 'f_black': 'psx-female-09', 'f_old': 'psx-31-female',
    'cop_m': 'psx-18-police', 'cop_f': 'psx-17-female-police', 'swat': 'psx-21-police',
    'medic': 'psx-26-doctor', 'army': 'psx-28-hm',
    'thug_a': 'psx-killer-04', 'thug_pig': 'psx-killer-05', 'thug_clown': 'psx-killer-07',
}
REFERENCE = 'psx-05'            # к его скелету приводятся все остальные

# Перекрашенные варианты одежды: имя -> (модель, что красим, как).  Так на улицах больше разных людей.
#   что:  'red' — насыщенно-красное, 'blue' — синее и голубое
#   как:  hue — новый оттенок (градусы), sat и val — множители насыщенности и яркости
SKINS = {
    'm_red_b': ('m_red', 'red', dict(hue=215, sat=0.80, val=0.85)),
    'm_red_c': ('m_red', 'red', dict(hue=125, sat=0.60, val=0.70)),
    'm_red_d': ('m_red', 'red', dict(hue=48, sat=0.75, val=1.0)),
    'm_shirt_b': ('m_shirt', 'blue', dict(hue=345, sat=1.1, val=1.0)),
    'm_shirt_c': ('m_shirt', 'blue', dict(sat=0.0, val=1.06)),
    'm_grey_b': ('m_grey', 'blue', dict(sat=0.3, val=0.42)),
    'f_old_b': ('f_old', 'blue', dict(hue=335, sat=1.0, val=1.0)),
    'f_old_c': ('f_old', 'blue', dict(hue=95, sat=0.8, val=0.9)),
}


def recolor(img, what, hue=None, sat=1.0, val=1.0):
    a = np.asarray(img.convert('HSV'), dtype=np.float32)
    h, s_, v = a[..., 0] * (360.0 / 255.0), a[..., 1] / 255.0, a[..., 2] / 255.0
    if what == 'red':
        mask = (s_ > 0.6) & ((h < 14.0) | (h > 340.0)) & (v > 0.12)
    else:
        mask = (s_ > 0.10) & (h > 170.0) & (h < 265.0) & (v > 0.10)
    if hue is not None:
        h = np.where(mask, float(hue), h)
    s2 = np.where(mask, np.clip(s_ * sat, 0.0, 1.0), s_)
    v2 = np.where(mask, np.clip(v * val, 0.0, 1.0), v)
    out = np.stack([h * (255.0 / 360.0), s2 * 255.0, v2 * 255.0], axis=-1).astype(np.uint8)
    from PIL import Image
    return Image.fromarray(out, 'HSV').convert('RGB')

# клипы анимации: имя в игре -> файл Mesh2Motion (static/assets/human/animations/<файл>.glb)
ANIMS = {
    'idle': 'idle-a', 'walk': 'walk', 'walk_f': 'walk-female', 'jog': 'jog', 'sprint': 'sprint',
    'run_f': 'run-female', 'walk_back': 'walk-backwards',
    'punch_a': 'punch-jab', 'punch_b': 'punch-cross', 'kick': 'kick-front', 'swing': 'two-handed-horizontal-swing',
    'pistol_idle': 'pistol-idle', 'pistol_aim': 'pistol-idle-aim', 'pistol_shoot': 'pistol-shoot',
    'pistol_walk': 'pistol-walk',
    'rifle_idle': 'rifle-idle', 'rifle_fire': 'rifle-fire', 'rifle_walk': 'rifle-walk', 'rifle_run': 'rifle-run',
    'throw': 'grenade-throw', 'hit_a': 'hit-chest', 'hit_b': 'hit-head', 'knockback': 'hit-knockback',
    'death_a': 'death-b', 'death_b': 'death-c', 'death_c': 'death-d', 'getup': 'laytoidle',
    'talk': 'idle-talking', 'listen': 'idle-listening', 'arms': 'idle-foldarms', 'phone': 'idle-talkingphone',
    'texting': 'texting-walk', 'cower': 'defend', 'drive': 'driving', 'sit': 'sitting-idle', 'air': 'jump-air',
    'victory': 'victory',
}


def run(cmd, **kw):
    print('  $', ' '.join(cmd))
    subprocess.check_call(cmd, **kw)


def fetch():
    os.makedirs(SRC, exist_ok=True)
    for name, (url, paths) in (('m2m', M2M_REPO), ('cars', CARS_REPO)):
        dst = os.path.join(SRC, name)
        if os.path.isdir(dst):
            print(dst, '— уже скачано')
            continue
        run(['git', 'clone', '--depth', '1', '--filter=blob:none', '--sparse', url, dst])
        run(['git', 'sparse-checkout', 'set'] + paths, cwd=dst)


def m2m_dir():
    return os.path.join(SRC, 'm2m', 'static', 'assets', 'human')


def cars_dir():
    return os.path.join(SRC, 'cars', 'assets', '3d', 'psx_cars')


# ---------------------------------------------------------------------------
# glTF: чтение и запись
# ---------------------------------------------------------------------------
CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def glb_read(path):
    d = open(path, 'rb').read()
    clen = struct.unpack_from('<I', d, 12)[0]
    g = json.loads(d[20:20 + clen])
    return g, d[20 + clen + 8:]


def acc_data(g, b, i, as_float=True):
    a = g['accessors'][i]
    bv = g['bufferViews'][a['bufferView']]
    dt = np.dtype(CT[a['componentType']])
    n = NC[a['type']]
    off = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    stride = bv.get('byteStride') or dt.itemsize * n
    if stride == dt.itemsize * n:
        arr = np.frombuffer(b, dtype=dt, count=a['count'] * n, offset=off).reshape(a['count'], n)
    else:
        arr = np.empty((a['count'], n), dtype=dt)
        for k in range(a['count']):
            arr[k] = np.frombuffer(b, dtype=dt, count=n, offset=off + k * stride)
    if as_float:
        arr = arr.astype(np.float64)
        if a.get('normalized'):
            arr /= {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}[a['componentType']]
            arr = np.maximum(arr, -1.0)
    return arr


class GltfOut(object):
    """Сборка glTF из json-заготовки и массивов numpy."""

    def __init__(self, g):
        self.g = g
        self.bin = bytearray()
        g['buffers'] = [{'byteLength': 0}]
        g['bufferViews'] = []
        g['accessors'] = []

    def add(self, arr, type_, ctype=5126, minmax=False):
        arr = np.ascontiguousarray(arr, dtype=CT[ctype])
        while len(self.bin) % 4:
            self.bin.append(0)
        off = len(self.bin)
        self.bin += arr.tobytes()
        self.g['bufferViews'].append({'buffer': 0, 'byteOffset': off, 'byteLength': arr.nbytes})
        acc = {'bufferView': len(self.g['bufferViews']) - 1, 'componentType': ctype, 'count': int(arr.shape[0]),
               'type': type_}
        if minmax:
            a2 = arr.reshape(arr.shape[0], -1)
            acc['min'] = [float(v) for v in a2.min(0)]
            acc['max'] = [float(v) for v in a2.max(0)]
        self.g['accessors'].append(acc)
        return len(self.g['accessors']) - 1

    def write(self, path):
        while len(self.bin) % 4:
            self.bin.append(0)
        self.g['buffers'][0]['byteLength'] = len(self.bin)
        js = json.dumps(self.g, separators=(',', ':')).encode('utf-8')
        while len(js) % 4:
            js += b' '
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        with open(path, 'wb') as f:
            f.write(struct.pack('<III', 0x46546C67, 2, total))
            f.write(struct.pack('<II', len(js), 0x4E4F534A))
            f.write(js)
            f.write(struct.pack('<II', len(self.bin), 0x004E4942))
            f.write(bytes(self.bin))


def quat_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def local_mat(n):
    if 'matrix' in n:
        return np.array(n['matrix'], dtype=np.float64).reshape(4, 4).T
    m = np.eye(4)
    m[:3, :3] = quat_mat(n.get('rotation', [0, 0, 0, 1])) * np.array(n.get('scale', [1, 1, 1]))[None, :]
    m[:3, 3] = n.get('translation', [0, 0, 0])
    return m


def world_mats(g):
    """Мировые матрицы всех узлов (векторы-столбцы)."""
    nodes = g['nodes']
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get('children', []):
            parent[c] = i
    res = {}

    def get(i):
        m = res.get(i)
        if m is None:
            m = local_mat(nodes[i])
            if i in parent:
                m = get(parent[i]) @ m
            res[i] = m
        return m
    for i in range(len(nodes)):
        get(i)
    return res


# ---------------------------------------------------------------------------
# персонажи
# ---------------------------------------------------------------------------
class Skinned(object):
    """Персонаж из GLB: сетка, веса, кости."""

    def __init__(self, path):
        g, b = glb_read(path)
        self.g, self.b = g, b
        skin = g['skins'][0]
        self.joints = skin['joints']
        self.jnames = [g['nodes'][j]['name'] for j in self.joints]
        self.ibm = acc_data(g, b, skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
        wm = world_mats(g)
        self.world = np.array([wm[j] for j in self.joints])
        mesh_node = [n for n in g['nodes'] if 'mesh' in n][0]
        prim = g['meshes'][mesh_node['mesh']]['primitives'][0]
        at = prim['attributes']
        self.pos = acc_data(g, b, at['POSITION'])
        self.nrm = acc_data(g, b, at['NORMAL'])
        self.uv = acc_data(g, b, at['TEXCOORD_0'])
        self.ji = acc_data(g, b, at['JOINTS_0'], as_float=False).astype(np.int64)
        self.jw = acc_data(g, b, at['WEIGHTS_0'])
        self.idx = acc_data(g, b, prim['indices'], as_float=False).astype(np.int64).reshape(-1)
        # текстура
        self.image = None
        mat = g['materials'][prim['material']] if 'material' in prim else None
        if mat is not None:
            ti = mat.get('pbrMetallicRoughness', {}).get('baseColorTexture')
            if ti is not None:
                im = g['images'][g['textures'][ti['index']]['source']]
                bv = g['bufferViews'][im['bufferView']]
                self.image = bytes(b[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']])

    def rest(self):
        return dict((n['name'], n) for n in self.g['nodes'] if 'name' in n)


def retarget(ch, ref):
    """Перенести сетку персонажа ch на скелет ref: вершины сдвигаются вместе со своими костями."""
    name_to_ref = dict((n, k) for k, n in enumerate(ref.jnames))
    # для кости j персонажа: матрица «поза покоя ch -> поза покоя ref»
    M = np.empty((len(ch.joints), 4, 4))
    for k, n in enumerate(ch.jnames):
        M[k] = ref.world[name_to_ref[n]] @ ch.ibm[k]
    w = ch.jw / ch.jw.sum(1, keepdims=True)
    Mv = np.einsum('vk,vkij->vij', w, M[ch.ji])
    p4 = np.c_[ch.pos, np.ones(len(ch.pos))]
    pos = np.einsum('vij,vj->vi', Mv, p4)[:, :3]
    nrm = np.einsum('vij,vj->vi', Mv[:, :3, :3], ch.nrm)
    nrm /= np.maximum(1e-9, np.linalg.norm(nrm, axis=1, keepdims=True))
    # индексы костей — в нумерации ref
    ji = np.vectorize(lambda k: name_to_ref[ch.jnames[k]])(ch.ji)
    return pos, nrm, ji, w


def char_gltf(ref, pos, nrm, uv, ji, jw, idx, path, anims=None):
    """Записать персонажа на скелете ref в GLB (без материалов); anims — список клипов."""
    g0 = ref.g
    nodes = []
    for n in g0['nodes']:
        m = dict((k, v) for k, v in n.items() if k in ('name', 'children', 'translation', 'rotation', 'scale',
                                                         'matrix'))
        if 'mesh' in n:
            m['mesh'] = 0
            m['skin'] = 0
        nodes.append(m)
    g = {'asset': {'version': '2.0', 'generator': 'deadly-district import_psx'}, 'scene': 0,
         'scenes': [{'nodes': list(g0['scenes'][g0.get('scene', 0)]['nodes'])}], 'nodes': nodes}
    out = GltfOut(g)
    a_pos = out.add(pos, 'VEC3', minmax=True)
    a_nrm = out.add(nrm, 'VEC3')
    a_uv = out.add(uv, 'VEC2')
    a_ji = out.add(ji, 'VEC4', 5123)
    a_jw = out.add(jw, 'VEC4')
    a_idx = out.add(idx.reshape(-1, 1), 'SCALAR', 5125)
    ibm = np.linalg.inv(ref.world).transpose(0, 2, 1).reshape(-1, 16)
    a_ibm = out.add(ibm, 'MAT4')
    g['meshes'] = [{'primitives': [{'attributes': {'POSITION': a_pos, 'NORMAL': a_nrm, 'TEXCOORD_0': a_uv,
                                                   'JOINTS_0': a_ji, 'WEIGHTS_0': a_jw}, 'indices': a_idx}]}]
    g['skins'] = [{'joints': list(ref.joints), 'inverseBindMatrices': a_ibm}]
    if 'skeleton' in g0['skins'][0]:
        g['skins'][0]['skeleton'] = g0['skins'][0]['skeleton']
    if anims:
        g['animations'] = []
        name_idx = dict((n.get('name'), i) for i, n in enumerate(nodes))
        for name, clip in anims:
            samplers, channels = [], []
            for (node_name, kind, times, values) in clip:
                if node_name not in name_idx:
                    continue
                a_t = out.add(np.asarray(times).reshape(-1, 1), 'SCALAR', minmax=True)
                a_v = out.add(values, 'VEC4' if kind == 'rotation' else 'VEC3')
                samplers.append({'input': a_t, 'output': a_v, 'interpolation': 'LINEAR'})
                channels.append({'sampler': len(samplers) - 1, 'target': {'node': name_idx[node_name], 'path': kind}})
            g['animations'].append({'name': name, 'samplers': samplers, 'channels': channels})
    out.write(path)


def read_clip(path, pelvis_scale):
    """Клип Mesh2Motion -> [(кость, 'rotation'|'translation', времена, значения)].

    Берём только повороты костей и перемещение таза: длины костей у каждого персонажа свои."""
    g, b = glb_read(path)
    a = g['animations'][0]
    res = []
    for ch in a['channels']:
        node = g['nodes'][ch['target']['node']]['name']
        kind = ch['target']['path']
        if kind == 'scale' or (kind == 'translation' and node != 'pelvis'):
            continue
        s = a['samplers'][ch['sampler']]
        t = acc_data(g, b, s['input']).reshape(-1)
        v = acc_data(g, b, s['output'])
        if kind == 'rotation':
            v = v / np.maximum(1e-9, np.linalg.norm(v, axis=1, keepdims=True))
        else:
            v = v * pelvis_scale
        res.append((node, kind, t, v))
    return res


def _panda():
    from panda3d.core import loadPrcFileData
    loadPrcFileData('', 'window-type none\naudio-library-name null\nmodel-cache-dir\n')
    from direct.showbase.ShowBase import ShowBase
    import builtins
    if not hasattr(builtins, 'base'):
        ShowBase()
    return builtins.base


def gltf2bam(src, dst, anims=False):
    exe = os.path.join(os.path.dirname(sys.executable), 'gltf2bam')
    cmd = [exe, '--no-srgb'] + ([] if anims else ['--animations', 'skip']) + [src, dst]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL)


WEIGHT_STEPS = 4


def simplify_skin(geom, name):
    """Упростить привязку к скелету: две главные кости на вершину, веса — с шагом в четверть.

    Движок пересчитывает матрицу для каждого уникального набора весов на каждом кадре, поэтому
    чем таких наборов меньше, тем дешевле анимация."""
    from panda3d.core import (GeomVertexReader, GeomVertexFormat, GeomVertexArrayFormat, GeomVertexData, Geom,
                              GeomTriangles, GeomVertexWriter, InternalName, GeomVertexAnimationSpec,
                              TransformBlendTable, TransformBlend, SparseArray)
    vd = geom.getVertexData()
    tbt = vd.getTransformBlendTable()
    n = vd.getNumRows()
    tc = 'texcoord.0' if vd.hasColumn('texcoord.0') else 'texcoord'
    rv, rn, rt, rb = (GeomVertexReader(vd, 'vertex'), GeomVertexReader(vd, 'normal'),
                      GeomVertexReader(vd, tc), GeomVertexReader(vd, 'transform_blend'))
    a0 = GeomVertexArrayFormat()
    a0.addColumn(InternalName.getVertex(), 3, Geom.NTFloat32, Geom.CPoint)
    a0.addColumn(InternalName.getNormal(), 3, Geom.NTFloat32, Geom.CNormal)
    a1 = GeomVertexArrayFormat()
    a1.addColumn(InternalName.getTexcoord(), 2, Geom.NTFloat32, Geom.CTexcoord)
    a2 = GeomVertexArrayFormat()
    a2.addColumn(InternalName.getTransformBlend(), 1, Geom.NTUint16, Geom.CIndex)
    fmt = GeomVertexFormat()
    fmt.addArray(a0)
    fmt.addArray(a1)
    fmt.addArray(a2)
    spec = GeomVertexAnimationSpec()
    spec.setPanda()
    fmt.setAnimation(spec)
    fmt.alignColumnsForAnimation()              # выравнивание включает быстрый (SSE) пересчёт вершин
    fmt = GeomVertexFormat.registerFormat(fmt)
    ntbt = TransformBlendTable()
    bmap = {}
    nvd = GeomVertexData(name, fmt, Geom.UHStatic)
    nvd.setNumRows(n)
    wv, wn, wt, wb = (GeomVertexWriter(nvd, 'vertex'), GeomVertexWriter(nvd, 'normal'),
                      GeomVertexWriter(nvd, 'texcoord'), GeomVertexWriter(nvd, 'transform_blend'))
    for i in range(n):
        wv.setData3(rv.getData3())
        wn.setData3(rn.getData3())
        wt.setData2(rt.getData2())
        b = rb.getData1i()
        j = bmap.get(b)
        if j is None:
            ob = tbt.getBlend(b)
            infl = sorted(((ob.getWeight(k), k) for k in range(ob.getNumTransforms())), reverse=True)[:2]
            nb = TransformBlend()
            if len(infl) == 1 or infl[1][0] <= 0.0:
                nb.addTransform(ob.getTransform(infl[0][1]), 1.0)
            else:
                w0 = infl[0][0] / (infl[0][0] + infl[1][0])
                w0 = round(w0 * WEIGHT_STEPS) / float(WEIGHT_STEPS)
                if w0 >= 1.0:
                    nb.addTransform(ob.getTransform(infl[0][1]), 1.0)
                else:
                    nb.addTransform(ob.getTransform(infl[0][1]), w0)
                    nb.addTransform(ob.getTransform(infl[1][1]), 1.0 - w0)
            j = bmap[b] = ntbt.addBlend(nb)
        wb.setData1i(j)
    ntbt.setRows(SparseArray.range(0, n))
    nvd.setTransformBlendTable(ntbt)
    g2 = geom.decompose()
    prim = GeomTriangles(Geom.UHStatic)
    for k in range(g2.getNumPrimitives()):
        p = g2.getPrimitive(k)
        for t in range(p.getNumPrimitives()):
            s, e = p.getPrimitiveStart(t), p.getPrimitiveEnd(t)
            prim.addVertices(p.getVertex(s), p.getVertex(s + 1), p.getVertex(s + 2))
    prim.closePrimitive()
    ng = Geom(nvd)
    ng.addPrimitive(prim)
    return ng, n, ntbt.getNumBlends()


def hand_frames(char_bam, adir):
    """Как оружие лежит в правой руке: точка хвата, направление ствола и «верх» в системе кости кисти.

    Пистолет: персонаж в позе прицеливания, ствол — туда, куда он смотрит.
    Длинный ствол: поза стрельбы из винтовки, ствол — от правой кисти к левой (она держит цевьё)."""
    from panda3d.core import Filename, LPoint3, LVector3
    from direct.actor.Actor import Actor
    base = _panda()
    res = {'joint': 'hand_r'}
    for kind, clip in (('pistol', 'pistol_aim'), ('rifle', 'rifle_fire')):
        a = Actor(Filename.fromOsSpecific(char_bam), {clip: Filename.fromOsSpecific(os.path.join(adir, clip + '.bam'))})
        a.reparentTo(base.render)
        j = dict((n, a.exposeJoint(None, 'modelRoot', n)) for n in ('hand_r', 'middle_01_r', 'hand_l', 'middle_01_l',
                                                                    'index_01_r', 'pinky_01_r'))
        a.pose(clip, 0)
        a.update(force=True)
        pos = dict((n, np.array(tuple(np_.getPos(a)))) for n, np_ in j.items())
        palm_r = pos['hand_r'] * 0.35 + pos['middle_01_r'] * 0.65
        palm_l = pos['hand_l'] * 0.35 + pos['middle_01_l'] * 0.65
        if kind == 'pistol':
            barrel = np.array([0.0, -1.0, 0.0])                     # модели смотрят в -Y
        else:
            barrel = palm_l - palm_r
            barrel /= np.linalg.norm(barrel)
        up = np.array([0.0, 0.0, 1.0])
        up = up - barrel * float(up @ barrel)
        up /= np.linalg.norm(up)
        right = np.cross(barrel, up)
        hand = j['hand_r']
        rnd = lambda v: [round(float(c), 4) for c in v]
        res[kind] = dict(origin=rnd(hand.getRelativePoint(a, LPoint3(*palm_r))),
                         right=rnd(hand.getRelativeVector(a, LVector3(*right))),
                         barrel=rnd(hand.getRelativeVector(a, LVector3(*barrel))),
                         up=rnd(hand.getRelativeVector(a, LVector3(*up))))
        a.cleanup()
        a.removeNode()
    return res


def do_chars(meta):
    from panda3d.core import NodePath, GeomNode, Filename, AnimBundleNode, ModelRoot
    from PIL import Image
    import io
    base = _panda()
    tmp = tempfile.mkdtemp(prefix='dd_psx_')
    cdir = os.path.join(OUT, 'chars')
    adir = os.path.join(OUT, 'anims')
    for d in (cdir, adir):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
    try:
        ref = Skinned(os.path.join(m2m_dir(), 'variations', REFERENCE + '.glb'))
        meta['chars'] = {}
        for name, src in sorted(CHARS.items()):
            ch = Skinned(os.path.join(m2m_dir(), 'variations', src + '.glb'))
            pos, nrm, ji, jw = retarget(ch, ref)
            gp = os.path.join(tmp, name + '.glb')
            char_gltf(ref, pos, nrm, ch.uv, ji, jw, ch.idx, gp)
            bp = os.path.join(tmp, name + '.bam')
            gltf2bam(gp, bp)
            root = base.loader.loadModel(Filename.fromOsSpecific(bp), noCache=True)
            char = root.find('**/+Character')
            new_nodes = []
            verts = blends = 0
            for gnp in char.findAllMatches('**/+GeomNode'):
                gn = gnp.node()
                ngn = GeomNode('skin')
                for i in range(gn.getNumGeoms()):
                    g, n, nb = simplify_skin(gn.getGeom(i), name)
                    verts += n
                    blends += nb
                    ngn.addGeom(g)
                new_nodes.append(NodePath(ngn))
            for c in char.getChildren():
                if not isinstance(c.node(), AnimBundleNode):
                    c.removeNode()
            for nnp in new_nodes:
                nnp.reparentTo(char)
            root.setName(name)
            out = os.path.join(cdir, name + '.bam')
            root.writeBamFile(Filename.fromOsSpecific(out))
            tex = Image.open(io.BytesIO(ch.image)).convert('RGB')
            tex.save(os.path.join(cdir, name + '.png'), optimize=True)
            mn, mx = pos.min(0), pos.max(0)
            meta['chars'][name] = dict(verts=verts, height=round(float(mx[1] - mn[1]), 3), tex=list(tex.size),
                                       source=src, model=name)
            print('  %-11s %-22s вершин %4d, наборов весов %3d, рост %.2f м, текстура %dx%d' % (
                name, src, verts, blends, mx[1] - mn[1], tex.size[0], tex.size[1]))
        for name, (model, what, op) in sorted(SKINS.items()):
            tex = recolor(Image.open(os.path.join(cdir, model + '.png')), what, **op)
            tex.save(os.path.join(cdir, name + '.png'), optimize=True)
            meta['chars'][name] = dict(meta['chars'][model], model=model)
        # --- анимации: один набор на всех (скелет общий)
        dec = os.path.join(tmp, 'anims')
        script = os.path.join(ROOT, 'tools', 'm2m_decode.mjs')
        node_dir = os.environ.get('DD_NODE_DIR') or os.path.join(ROOT, '.cache', 'node')
        if not os.path.isdir(os.path.join(node_dir, 'node_modules')):
            os.makedirs(node_dir, exist_ok=True)
            with open(os.path.join(node_dir, 'package.json'), 'w') as f:
                f.write('{"name":"m2m-decode","version":"1.0.0","type":"module","private":true}')
            run(['npm', 'install', '--silent', '--no-audit', '--no-fund', '@gltf-transform/core',
                 '@gltf-transform/extensions', 'meshoptimizer'], cwd=node_dir)
        shutil.copy(script, os.path.join(node_dir, 'm2m_decode.mjs'))
        run(['node', 'm2m_decode.mjs', os.path.join(m2m_dir(), 'animations'), dec] + sorted(set(ANIMS.values())),
            cwd=node_dir)
        skel, _ = glb_read(os.path.join(m2m_dir(), 'skeleton.glb'))
        base_pelvis = [n for n in skel['nodes'] if n.get('name') == 'pelvis'][0]['translation']
        ref_pelvis = ref.rest()['pelvis']['translation']
        k = float(np.linalg.norm(ref_pelvis) / np.linalg.norm(base_pelvis))
        clips = [(name, read_clip(os.path.join(dec, src + '.glb'), k)) for name, src in sorted(ANIMS.items())]
        gp = os.path.join(tmp, 'anims.glb')
        char_gltf(ref, ref.pos, ref.nrm, ref.uv, ref.ji, ref.jw / ref.jw.sum(1, keepdims=True), ref.idx, gp, clips)
        bp = os.path.join(tmp, 'anims.bam')
        gltf2bam(gp, bp, anims=True)
        root = base.loader.loadModel(Filename.fromOsSpecific(bp), noCache=True)
        meta['anims'] = {}
        total = 0
        for anp in root.findAllMatches('**/+AnimBundleNode'):
            bnd = anp.node().getBundle()
            holder = NodePath(ModelRoot(bnd.getName()))
            anp.copyTo(holder)
            out = os.path.join(adir, bnd.getName() + '.bam')
            holder.writeBamFile(Filename.fromOsSpecific(out))
            total += os.path.getsize(out)
            meta['anims'][bnd.getName()] = dict(frames=bnd.getNumFrames(), fps=round(bnd.getBaseFrameRate(), 2))
        meta['hand'] = hand_frames(os.path.join(cdir, 'm_shirt.bam'), adir)
        missing = [a for a in ANIMS if a not in meta['anims']]
        print('  анимации: %d клипов, %d КБ, масштаб таза %.3f%s' % (len(meta['anims']), total // 1024, k,
                                                                    (', НЕТ: %s' % missing) if missing else ''))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def do_cars(meta):
    pass


# ---------------------------------------------------------------------------
def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if cmd == 'fetch':
        fetch()
        return
    os.makedirs(OUT, exist_ok=True)
    mpath = os.path.join(OUT, 'models.json')
    meta = {}
    if os.path.exists(mpath):
        with open(mpath, encoding='utf-8') as f:
            meta = json.load(f)
    if cmd in ('all', 'chars'):
        do_chars(meta)
    if cmd in ('all', 'cars'):
        do_cars(meta)
    with open(mpath, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1, sort_keys=True, ensure_ascii=False)
    print('готово:', os.path.relpath(mpath, ROOT))


if __name__ == '__main__':
    main()
