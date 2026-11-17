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

# исходные модели: имя -> файл Mesh2Motion (static/assets/human/variations/<файл>.glb)
# В наборе есть ещё «убийцы» в масках и монстры — в игре про город им не место, мы их не берём.
CHARS = {
    'm_shirt': 'psx-05', 'm_red': 'psx-06', 'm_grey': 'psx-10', 'm_leather': 'psx-15', 'm_old': 'psx-32',
    'f_goth': 'psx-female-08', 'f_black': 'psx-female-09', 'f_old': 'psx-31-female',
    'cop_m': 'psx-18-police', 'cop_f': 'psx-17-female-police', 'swat': 'psx-21-police',
    'medic': 'psx-26-doctor', 'army': 'psx-28-hm',
}
REFERENCE = 'psx-05'            # к его скелету приводятся все остальные
# Эти модели целиком в игре не ходят — от них берутся только части:
#   m_red — его лицо досталось главному герою и больше никому; m_grey — нужна только одежда.
PARTS_ONLY = ('m_red', 'm_grey')

# Сборные персонажи: тело одной модели, голова другой.  имя -> (тело, голова)
# Так у героя своё лицо, а на улицах больше разных людей.  Текстуры у частей свои (тело и голова
# красятся отдельно), поэтому новая пара не стоит ни одного лишнего файла текстуры.
COMBOS = {
    'hero': ('m_leather', 'm_red'),             # Макс: кожаная куртка и спокойное лицо
    'm_leather_b': ('m_leather', 'cop_m'),
    'm_leather_c': ('m_leather', 'm_old'),
    'm_red_h2': ('m_red', 'cop_m'),
    'm_red_h3': ('m_red', 'medic'),
    'm_red_h4': ('m_red', 'm_shirt'),
    'm_shirt_h3': ('m_shirt', 'medic'),
    'm_shirt_h4': ('m_shirt', 'cop_m'),
    'm_grey_h2': ('m_grey', 'cop_m'),
    'm_grey_h3': ('m_grey', 'm_old'),
    'm_grey_h4': ('m_grey', 'm_leather'),
    'm_old_h3': ('m_old', 'medic'),
}

# Штаны.  У модели psx-06 они песочные, почти в цвет кожи: в игре человек в красной футболке выглядел
# так, будто вышел из дома без штанов.  Красим их целиком — по «островам» развёртки, в которые попадают
# эти точки (координаты для текстуры 512x512); по цвету отделить ткань от кожи нельзя, оттенки слишком близки.
LEGS = {
    'm_red': ((385, 120), (240, 120), (200, 330), (60, 380), (370, 430), (425, 430)),
}
JEANS = dict(hue=216, sat=0.42, val=0.50)           # тёмно-синие джинсы — штаны по умолчанию
DARK = dict(hue=30, sat=0.06, val=0.36)             # чёрные брюки
GREY = dict(hue=215, sat=0.08, val=0.62)            # серые
BROWN = dict(hue=24, sat=0.42, val=0.46)            # коричневые рабочие

# Перекрашенная одежда: имя текстуры -> (исходная текстура, что красим, как)
#   что:  'red' — насыщенно-красное, 'blue' — синее и голубое
#   как:  hue — новый оттенок (градусы), sat и val — множители насыщенности и яркости;
#         legs — цвет штанов (если у модели они перекрашиваются, см. LEGS)
RECOLORS = {
    'red_blue': ('m_red', 'red', dict(hue=215, sat=0.80, val=0.85, legs=DARK)),
    'red_green': ('m_red', 'red', dict(hue=125, sat=0.60, val=0.70, legs=BROWN)),
    'red_yellow': ('m_red', 'red', dict(hue=48, sat=0.75, val=1.0, legs=JEANS)),
    'red_orange': ('m_red', 'red', dict(hue=26, sat=0.9, val=1.0, legs=GREY)),
    'red_purple': ('m_red', 'red', dict(hue=282, sat=0.75, val=0.8, legs=DARK)),
    'red_black': ('m_red', 'red', dict(sat=0.0, val=0.32, legs=JEANS)),
    'red_white': ('m_red', 'red', dict(sat=0.0, val=1.25, legs=DARK)),
    'shirt_pink': ('m_shirt', 'blue', dict(hue=345, sat=1.1, val=1.0)),
    'shirt_grey': ('m_shirt', 'blue', dict(sat=0.0, val=1.06)),
    'shirt_green': ('m_shirt', 'blue', dict(hue=140, sat=0.8, val=0.85)),
    'shirt_dark': ('m_shirt', 'blue', dict(sat=0.25, val=0.45)),
    'grey_dark': ('m_grey', 'blue', dict(sat=0.3, val=0.42)),
    'f_old_pink': ('f_old', 'blue', dict(hue=335, sat=1.0, val=1.0)),
    'f_old_green': ('f_old', 'blue', dict(hue=95, sat=0.8, val=0.9)),
}

# Ещё облики: имя -> (модель, текстура одежды)
VARIANTS = {
    'm_shirt_b': ('m_shirt', 'shirt_pink'), 'm_shirt_c': ('m_shirt', 'shirt_grey'),
    'm_red_h2b': ('m_red_h2', 'red_blue'), 'm_red_h2c': ('m_red_h2', 'red_green'),
    'm_red_h2p': ('m_red_h2', 'red_purple'),
    'm_red_h3b': ('m_red_h3', 'red_orange'), 'm_red_h3c': ('m_red_h3', 'red_black'),
    'm_red_h3g': ('m_red_h3', 'red_green'), 'm_red_h3p': ('m_red_h3', 'red_purple'),
    'm_red_h4b': ('m_red_h4', 'red_yellow'), 'm_red_h4c': ('m_red_h4', 'red_white'),
    'm_shirt_h3b': ('m_shirt_h3', 'shirt_dark'), 'm_shirt_h4b': ('m_shirt_h4', 'shirt_green'),
    'm_shirt_h4c': ('m_shirt_h4', 'shirt_grey'),
    'm_grey_h2b': ('m_grey_h2', 'grey_dark'), 'm_grey_h4b': ('m_grey_h4', 'grey_dark'),
    'f_old_b': ('f_old', 'f_old_pink'), 'f_old_c': ('f_old', 'f_old_green'),
}


def recolor(img, what, hue=None, sat=1.0, val=1.0):
    a = np.asarray(img.convert('HSV'), dtype=np.float32)
    h, s_, v = a[..., 0] * (360.0 / 255.0), a[..., 1] / 255.0, a[..., 2] / 255.0
    if what == 'red':
        mask = (s_ > 0.6) & ((h < 14.0) | (h > 340.0)) & (v > 0.12)
        # кромка ткани: точки на границе с кожей уже не такие красные, но ещё и не кожа.  Без них у
        # перекрашенной футболки по вороту и рукавам шла красная кайма.
        soft = (s_ > 0.48) & ((h < 19.0) | (h > 335.0)) & (v > 0.12)
        near = mask.copy()
        for _ in range(2):
            grown = near.copy()
            grown[1:, :] |= near[:-1, :]
            grown[:-1, :] |= near[1:, :]
            grown[:, 1:] |= near[:, :-1]
            grown[:, :-1] |= near[:, 1:]
            near = grown
        mask = mask | (soft & near)
    else:
        mask = (s_ > 0.10) & (h > 170.0) & (h < 265.0) & (v > 0.10)
    if hue is not None:
        h = np.where(mask, float(hue), h)
    s2 = np.where(mask, np.clip(s_ * sat, 0.0, 1.0), s_)
    v2 = np.where(mask, np.clip(v * val, 0.0, 1.0), v)
    out = np.stack([h * (255.0 / 360.0), s2 * 255.0, v2 * 255.0], axis=-1).astype(np.uint8)
    from PIL import Image
    return Image.fromarray(out, 'HSV').convert('RGB')


def dye(img, seeds, hue=216.0, sat=0.42, val=0.5):
    """Красит «острова» развёртки, в которые попадают точки seeds: оттенок и насыщенность задаются,
    яркость умножается на val (складки и тени ткани остаются)."""
    from PIL import Image, ImageDraw
    img = img.convert('RGB')
    k = img.size[0] / 512.0
    solid = (np.asarray(img).max(-1) > 15).astype(np.uint8) * 255
    m = Image.fromarray(solid, 'L').copy()         # копия: картинку поверх массива numpy заливка не меняет
    for (sx, sy) in seeds:
        xy = (int(sx * k), int(sy * k))
        if m.getpixel(xy) == 255:
            ImageDraw.floodfill(m, xy, 128)
    mask = np.asarray(m) == 128
    if not mask.any():
        raise RuntimeError('dye: ни одна точка не попала на развёртку')
    a = np.asarray(img.convert('HSV'), dtype=np.float32)
    h = np.where(mask, hue * (255.0 / 360.0), a[..., 0])
    s_ = np.where(mask, sat * 255.0, a[..., 1])
    v = np.where(mask, np.clip(a[..., 2] * val, 0.0, 255.0), a[..., 2])
    out = np.stack([h, s_, v], axis=-1).astype(np.uint8)
    return Image.fromarray(out, 'HSV').convert('RGB'), int(mask.sum())


# клипы анимации: имя в игре -> файл Mesh2Motion (static/assets/human/animations/<файл>.glb)
ANIMS = {
    # ходьба, бег
    'idle': 'idle-subtle', 'idle_wide': 'idle-a', 'walk': 'walk', 'walk_f': 'walk-female', 'jog': 'jog',
    'sprint': 'sprint', 'run_f': 'run-female', 'walk_back': 'walk-backwards', 'walk_relaxed': 'walk-relaxed',
    'walk_formal': 'walk-formal', 'walk_hurt': 'walk-injured', 'air': 'jump-air',
    # драка и оружие
    'punch_a': 'punch-jab', 'punch_b': 'punch-cross', 'kick': 'kick-front', 'swing': 'two-handed-horizontal-swing',
    'pistol_idle': 'pistol-idle', 'pistol_aim': 'pistol-idle-aim', 'pistol_shoot': 'pistol-shoot',
    'pistol_walk': 'pistol-walk',
    'rifle_idle': 'rifle-idle', 'rifle_fire': 'rifle-fire', 'rifle_walk': 'rifle-walk', 'rifle_run': 'rifle-run',
    'throw': 'grenade-throw', 'hit_a': 'hit-chest', 'hit_b': 'hit-head', 'knockback': 'hit-knockback',
    'death_a': 'death-b', 'death_b': 'death-c', 'death_c': 'death-d', 'getup': 'laytoidle', 'cower': 'defend',
    # разговоры и жесты
    'talk': 'idle-talking', 'listen': 'idle-listening', 'arms': 'idle-foldarms', 'phone': 'idle-talkingphone',
    'texting': 'texting-walk', 'greet': 'greeting', 'nod': 'head-nod', 'no': 'reject', 'angry': 'angry',
    'confused': 'confused', 'victory': 'victory', 'clap': 'clapping',
    # сидя и лёжа
    'drive': 'driving', 'ride': 'mount-idle', 'sit': 'sitting-idle',
    'sit_talk': 'sitting-talking', 'sit_down': 'sitting-enter',
    'sit_up': 'sitting-exit', 'write': 'sitting-writing', 'sit_ground': 'sit-ground-idle', 'sleep': 'sleeping',
    # действия
    'door': 'open-door', 'interact': 'interact', 'pickup': 'pick-up', 'push': 'push', 'knock': 'knock',
    'kneel': 'kneel', 'tired': 'tired-hunched', 'hurt': 'idle-hurt', 'dizzy': 'dizzy', 'drink': 'consume',
    'dance_a': 'dance-simple', 'dance_b': 'dance-arm-pump', 'fix': 'fixing-kneeling', 'crouch': 'crouch-idle',
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


FINGERS = ('index', 'middle', 'ring', 'pinky')


def mitten(ch):
    """Кисть как «варежка»: четыре пальца двигаются одним куском.

    У моделей набора пальцы не разделены — это один блок с нарисованными пальцами.  Автоматическая
    привязка раздала его вершины костям разных пальцев, и в движении блок рвало веером.  Здесь все
    такие вершины перепривязываются к костям среднего пальца: какой сустав — зависит от того,
    как далеко вершина от костяшек.  Большой палец остаётся отдельным.
    """
    names = ch.jnames
    idx = dict((n, k) for k, n in enumerate(names))
    bind = np.linalg.inv(ch.ibm)                    # кости в позе привязки, в системе сетки
    w = ch.jw / ch.jw.sum(1, keepdims=True)
    nv = len(ch.pos)
    infl = []
    for v in range(nv):
        d = {}
        for k in range(4):
            if w[v, k] > 0.0:
                d[int(ch.ji[v, k])] = d.get(int(ch.ji[v, k]), 0.0) + float(w[v, k])
        infl.append(d)
    for side in ('l', 'r'):
        fset = set(k for k, n in enumerate(names) if n.split('_')[0] in FINGERS and n.endswith('_' + side))
        chain = [idx['middle_0%d_%s' % (k, side)] for k in (1, 2, 3)]
        p = [bind[j][:3, 3] for j in chain]
        tip = bind[idx['middle_04_leaf_' + side]][:3, 3]
        axis = tip - p[0]
        length = float(np.linalg.norm(axis))
        axis /= length
        t1 = float((p[1] - p[0]) @ axis)
        t2 = float((p[2] - p[0]) @ axis)
        bw = 0.22 * length                         # ширина плавного перехода между суставами
        for v in range(nv):
            d = infl[v]
            wf = sum(x for j, x in d.items() if j in fset)
            if wf <= 0.0:
                continue
            for j in [j for j in d if j in fset]:
                del d[j]
            t = float((ch.pos[v] - p[0]) @ axis)
            w0 = min(1.0, max(0.0, (t1 + bw * 0.5 - t) / bw))
            w2 = min(1.0, max(0.0, (t - (t2 - bw * 0.5)) / bw))
            w1 = max(0.0, 1.0 - w0 - w2)
            for j, x in zip(chain, (w0, w1, w2)):
                if x > 0.0:
                    d[j] = d.get(j, 0.0) + wf * x
    ji = np.zeros((nv, 4), dtype=np.int64)
    jw = np.zeros((nv, 4), dtype=np.float64)
    for v, d in enumerate(infl):
        top = sorted(d.items(), key=lambda kv: -kv[1])[:4]
        tot = sum(x for _, x in top)
        for k, (j, x) in enumerate(top):
            ji[v, k] = j
            jw[v, k] = x / tot
    ch.ji, ch.jw = ji, jw


# ---------------------------------------------------------------------------
# сборные персонажи: тело одной модели, голова другой
# ---------------------------------------------------------------------------
# У моделей набора шея короткая: воротник кончается почти у подбородка.  Поэтому шея целиком остаётся телу,
# а голова отрезается под самым подбородком — наклонной плоскостью: спереди она проходит под подбородком,
# сзади — над воротником, под линией волос.  Плоскость у каждой модели своя (ищется по самой модели);
# при сборке голова переносится так, чтобы срезы совпали, а верх шеи тела подгоняется к кольцу головы.
NECK_TILT = math.radians(14.0)
NECK_N = np.array([0.0, math.cos(NECK_TILT), math.sin(NECK_TILT)])      # нормаль среза: y — вверх, z — вперёд
NECK_R = 0.2                            # режем только около оси шеи (плечи и руки не трогаем)
NECK_FIT = 0.035                        # на такой глубине под срезом шея тела подгоняется к кольцу головы
NECK_SKIRT = 0.03                       # «юбка» под срезом головы: уходит внутрь шеи тела, щели не видно
NECK_PLANES = {}                        # ручные поправки: модель -> положение плоскости (n·p)
HEAD_U = 4.0                            # сдвиг u, которым помечены вершины головы


LIPS = {'m_red': ((54, 192, 74, 212), (462, 174, 482, 194))}       # текстура -> где на ней губы (x0, y0, x1, y1)


def soften_lips(img, boxes, k=0.5):
    """Губы на фото-текстуре слишком яркие — у героя они смотрелись как помада.  Подводим их к цвету кожи
    вокруг (на долю k); тёмная линия рта остаётся."""
    from PIL import Image
    a = np.asarray(img.convert('RGB')).astype(np.float64)
    for (x0, y0, x1, y1) in boxes:
        part = a[y0:y1 + 1, x0:x1 + 1]
        r, g, b = part[..., 0], part[..., 1], part[..., 2]
        painted = part.max(2) > 2
        lips = painted & (r > 110) & (r > g * 1.3) & (r > b * 1.25)
        skin = painted & ~lips & (r > 150) & (g > 105)
        if not lips.any() or not skin.any():
            continue
        tone = part[skin].mean(0)
        lum = part[lips].mean(1, keepdims=True) / max(1.0, float(tone.mean()))
        part[lips] = part[lips] * (1.0 - k) + (tone[None, :] * np.clip(lum, 0.55, 1.0)) * k
    return Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8), 'RGB')


def pad_islands(img, steps=8):
    """Раздвинуть «острова» развёртки на несколько точек в чёрный фон.

    У пары моделей треугольники у горла заходят за край нарисованного острова — на шее получался чёрный
    клин.  Заодно на уменьшенной текстуре (вдали) чёрный фон больше не подмешивается в швы лица и одежды."""
    from PIL import Image
    a = np.asarray(img.convert('RGB')).astype(np.float64)
    h, w = a.shape[:2]
    filled = a.max(2) > 2
    for _ in range(steps):
        acc = np.zeros((h + 2, w + 2, 3))
        cnt = np.zeros((h + 2, w + 2))
        src = a * filled[..., None]
        for dy in (0, 1, 2):
            for dx in (0, 1, 2):
                if dy == 1 and dx == 1:
                    continue
                acc[dy:dy + h, dx:dx + w] += src
                cnt[dy:dy + h, dx:dx + w] += filled
        acc, cnt = acc[1:-1, 1:-1], cnt[1:-1, 1:-1]
        new = ~filled & (cnt > 0)
        if not new.any():
            break
        a[new] = acc[new] / cnt[new][:, None]
        filled = filled | new
    return Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8), 'RGB')


def is_skin(c):
    """Похож ли цвет точки текстуры на кожу (а не на ткань, волосы или тень)."""
    r, g, b = float(c[0]), float(c[1]), float(c[2])
    return (r > 95.0 and g > 40.0 and b > 20.0 and r > g > b * 0.95 and r - g > 12.0 and r - b > 25.0 and
            g > r * 0.52 and b > r * 0.33)


def neck_axis(ref, s):
    """Точка оси шеи (от сустава шеи к суставу головы) на плоскости среза n·p = s."""
    a = ref.world[ref.jnames.index('neck_01')][:3, 3]
    b = ref.world[ref.jnames.index('head')][:3, 3]
    k = (s - a @ NECK_N) / ((b - a) @ NECK_N)
    return a + (b - a) * k


def neck_section(part, tex_px, ref, s):
    """Сечение сетки плоскостью среза около оси шеи: [(p0, p1, uv0, uv1)], длина кольца, доля кожи, цвет кожи."""
    pos, nrm, uv, ji, jw, idx = part
    c = neck_axis(ref, s)
    d = pos @ NECK_N - s
    th, tw = tex_px.shape[:2]
    segs = []
    total = 0.0
    skin_len = 0.0
    cols = []
    for t in idx.reshape(-1, 3):
        dt = d[t]
        if (dt > 0).all() or (dt <= 0).all():
            continue
        pts = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            if (dt[a] > 0) != (dt[b] > 0):
                k = dt[a] / (dt[a] - dt[b])
                pts.append((pos[t[a]] + (pos[t[b]] - pos[t[a]]) * k, uv[t[a]] + (uv[t[b]] - uv[t[a]]) * k))
        if len(pts) != 2:
            continue
        mid = (pts[0][0] + pts[1][0]) * 0.5
        if math.hypot(mid[0] - c[0], mid[2] - c[2]) > NECK_R:
            continue
        ln = float(np.linalg.norm(pts[1][0] - pts[0][0]))
        segs.append((pts[0][0], pts[1][0], pts[0][1], pts[1][1]))
        n = max(1, int(ln / 0.004))
        for i in range(n):
            u = pts[0][1] + (pts[1][1] - pts[0][1]) * ((i + 0.5) / n)
            col = tex_px[min(th - 1, max(0, int(u[1] * th))), min(tw - 1, max(0, int(u[0] * tw)))]
            total += ln / n
            if is_skin(col):
                skin_len += ln / n
                cols.append(col)
    skin = np.median(np.array(cols), axis=0) if cols else None
    return segs, total, (skin_len / total if total > 0 else 0.0), skin


def neck_plane(name, part, tex, ref, log=None):
    """Положение плоскости среза шеи у модели: самое низкое кольцо чистой кожи — сразу над воротником."""
    if name in NECK_PLANES:
        return NECK_PLANES[name]
    px = np.asarray(tex.convert('RGB'), dtype=np.float64)
    a = ref.world[ref.jnames.index('neck_01')][:3, 3]
    b = ref.world[ref.jnames.index('head')][:3, 3]
    s0 = (a + (b - a) * 0.45) @ NECK_N
    s1 = (a + (b - a) * 1.55) @ NECK_N
    rows = []
    for s in np.arange(s0, s1, 0.0025):
        segs, total, frac, skin = neck_section(part, px, ref, s)
        if segs:
            rows.append((float(s), total, frac))
    lmin = min(r[1] for r in rows)
    ok = [r for r in rows if r[1] <= lmin * 1.3]
    fmax = max(r[2] for r in ok)
    best = min(r[0] for r in ok if r[2] >= fmax - 0.015)
    if log is not None:
        log('  %-10s срез шеи: n·p = %.4f (кольцо %.0f мм, кожи %.0f%%)' % (
            name, best + 0.003, [r[1] for r in rows if r[0] == best][0] * 1000.0, fmax * 100.0))
    return best + 0.003


def mix_weights(ja, wa, jb, wb, k):
    """Веса костей между двумя вершинами (доля k от второй): не больше четырёх костей, сумма 1."""
    d = {}
    for j, x in zip(ja, wa):
        if x > 0.0:
            d[int(j)] = d.get(int(j), 0.0) + float(x) * (1.0 - k)
    for j, x in zip(jb, wb):
        if x > 0.0:
            d[int(j)] = d.get(int(j), 0.0) + float(x) * k
    top = sorted(d.items(), key=lambda kv: -kv[1])[:4]
    tot = sum(x for _, x in top) or 1.0
    ji = np.zeros(len(ja), dtype=np.int64)
    jw = np.zeros(len(ja), dtype=np.float64)
    for i, (j, x) in enumerate(top):
        ji[i] = j
        jw[i] = x / tot
    return ji, jw


def clip_mesh(part, s, above, center):
    """Разрезать сетку плоскостью среза n·p = s около оси шеи.

    above=True — оставить только то, что выше плоскости (голова); above=False — убрать то, что выше (тело
    без головы; всё, что далеко от оси, не трогается).  Треугольники, которые плоскость пересекает,
    режутся по ней, так что край получается ровным кольцом.
    Возвращает (сетка, рёбра кольца [(i, j)] в порядке обхода оставшихся треугольников)."""
    pos, nrm, uv, ji, jw, idx = part
    d = pos @ NECK_N - s
    P_, N_, U_, J_, W_ = list(pos), list(nrm), list(uv), list(ji), list(jw)
    cache = {}

    def cut(a, b):
        key = (a, b) if a < b else (b, a)
        v = cache.get(key)
        if v is None:
            k = float(d[a] / (d[a] - d[b]))
            nn = nrm[a] + (nrm[b] - nrm[a]) * k
            j_, w_ = mix_weights(ji[a], jw[a], ji[b], jw[b], k)
            v = cache[key] = len(P_)
            P_.append(pos[a] + (pos[b] - pos[a]) * k)
            N_.append(nn / max(1e-9, float(np.linalg.norm(nn))))
            U_.append(uv[a] + (uv[b] - uv[a]) * k)
            J_.append(j_)
            W_.append(w_)
        return v
    tris = []
    rim = []
    for t in idx.reshape(-1, 3):
        t = [int(v) for v in t]
        mid = (pos[t[0]] + pos[t[1]] + pos[t[2]]) / 3.0
        near = math.hypot(mid[0] - center[0], mid[2] - center[2]) < NECK_R
        if not near:
            if not above:
                tris.append(t)
            continue
        keep = [(d[v] > 0.0) == above for v in t]
        n = sum(keep)
        if n == 3:
            tris.append(t)
        elif n == 1:
            i = keep.index(True)
            a, b, c = t[i], t[(i + 1) % 3], t[(i + 2) % 3]
            p, q = cut(a, b), cut(a, c)
            tris.append([a, p, q])
            rim.append((p, q))
        elif n == 2:
            i = keep.index(False)
            a, b, c = t[i], t[(i + 1) % 3], t[(i + 2) % 3]
            p, q = cut(a, b), cut(c, a)
            tris.append([p, b, c])
            tris.append([p, c, q])
            rim.append((q, p))
    tris = np.array(tris, dtype=np.int64)
    used = np.unique(tris.reshape(-1))
    remap = np.full(len(P_), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    out = (np.array(P_)[used], np.array(N_)[used], np.array(U_)[used], np.array(J_)[used], np.array(W_)[used],
           remap[tris].reshape(-1))
    return out, [(int(remap[i]), int(remap[j])) for i, j in rim if i != j]


def combine(ref, body, head, body_tex, head_tex, s_body, s_head):
    """Тело одной модели и голова другой.  body и head — (pos, nrm, uv, ji, jw, idx) на скелете ref,
    s_body и s_head — плоскости среза шеи у этих моделей (neck_plane).

    Тело обрезается сразу над воротником, голова — там же у своей модели, так что видимая шея целиком
    принадлежит голове: цвет кожи лица и шеи один.  Голова переносится на срез тела, верх тела подгоняется
    к её кольцу и получает те же веса костей — в движении шов не расходится.  Под срезом у головы «юбка»,
    уходящая внутрь тела.  Текстуры у частей свои: вершины головы помечаются сдвигом u на HEAD_U и при
    записи модели уходят в отдельный узел «head».
    Возвращает (pos, nrm, uv, ji, jw, idx, поправка цвета головы под кожу тела)."""
    e1 = np.array([1.0, 0.0, 0.0])
    e2 = np.array([0.0, -NECK_N[2], NECK_N[1]])
    (bpos, bnrm, buv, bji, bjw, bidx), brim = clip_mesh(body, s_body, False, neck_axis(ref, s_body))
    (hpos, hnrm, huv, hji, hjw, hidx), hrim = clip_mesh(head, s_head, True, neck_axis(ref, s_head))

    def centre(pos, rim):
        a = pos[[i for i, j in rim]]
        b = pos[[j for i, j in rim]]
        ln = np.linalg.norm(b - a, axis=1)
        return ((a + b) * 0.5 * ln[:, None]).sum(0) / ln.sum()

    def hit(pos, rim, c, ang):
        """Дальнее пересечение луча из центра кольца под углом ang: (расстояние, ребро, доля вдоль ребра)."""
        dx, dy = math.cos(ang), math.sin(ang)
        best = None
        for (i, j) in rim:
            a, b = pos[i] - c, pos[j] - c
            ax, ay = float(a @ e1), float(a @ e2)
            ex, ey = float(b @ e1) - ax, float(b @ e2) - ay
            den = dx * ey - dy * ex
            if abs(den) < 1e-12:
                continue
            t = (ax * ey - ay * ex) / den
            u = (ax * dy - ay * dx) / den
            if t > 0.0 and -1e-6 <= u <= 1.0 + 1e-6 and (best is None or t > best[0]):
                best = (t, (i, j), min(1.0, max(0.0, u)))
        return best
    cb = centre(bpos, brim)
    hpos = hpos + (cb - centre(hpos, hrim))             # голова — на срез тела
    hring = sorted(set(i for e in hrim for i in e))
    # --- верх тела подгоняется к кольцу головы
    was = bpos                                          # мерить нужно по исходному кольцу, а не по уже сдвинутому
    bpos = bpos.copy()
    bnrm = bnrm.copy()
    bji = bji.copy()
    bjw = bjw.copy()
    depth = bpos @ NECK_N - cb @ NECK_N                  # 0 на срезе, ниже — отрицательная
    for v in np.where(depth > -NECK_FIT)[0]:
        q = was[v] - cb
        x, y = float(q @ e1), float(q @ e2)
        r = math.hypot(x, y)
        if r < 1e-5 or r > NECK_R:
            continue
        ang = math.atan2(y, x)
        hb_ = hit(was, brim, cb, ang)
        hh_ = hit(hpos, hrim, cb, ang)
        if hb_ is None or hh_ is None:
            continue
        f = 1.0 + depth[v] / NECK_FIT                   # 1 на срезе, 0 на глубине NECK_FIT
        f = f * f * (3.0 - 2.0 * f)
        g = min(1.0, max(0.0, 1.0 - (r - hb_[0]) / 0.04))       # плечи и концы воротника не тянем
        k = f * g
        if k <= 0.0:
            continue
        scale = min(1.4, max(0.7, hh_[0] / hb_[0]))
        bpos[v] = bpos[v] + (e1 * x + e2 * y) * ((scale - 1.0) * k)
        (i, j), u = hh_[1], hh_[2]
        wj, ww = mix_weights(hji[i], hjw[i], hji[j], hjw[j], u)
        bji[v], bjw[v] = mix_weights(bji[v], bjw[v], wj, ww, k)
        if depth[v] > -1e-4:
            out = (e1 * x + e2 * y) / r
            bnrm[v] = out
    # --- кольцо головы: нормали наружу, как у края тела, и «юбка» вниз, внутрь тела
    hnrm = hnrm.copy()
    add_pos, add_nrm, add_uv, add_ji, add_jw, add_tri = [], [], [], [], [], []
    low = {}
    base = len(hpos)
    for v in hring:
        q = hpos[v] - cb
        x, y = float(q @ e1), float(q @ e2)
        r = math.hypot(x, y) or 1.0
        hnrm[v] = (e1 * x + e2 * y) / r
        low[v] = base + len(add_pos)
        add_pos.append(cb + (e1 * x + e2 * y) * 0.78 - NECK_N * NECK_SKIRT)
        add_nrm.append(hnrm[v])
        add_uv.append(huv[v])
        add_ji.append(hji[v])
        add_jw.append(hjw[v])
    for (i, j) in hrim:
        add_tri.append((j, i, low[i]))
        add_tri.append((j, low[i], low[j]))
    hpos = np.r_[hpos, np.array(add_pos)]
    hnrm = np.r_[hnrm, np.array(add_nrm)]
    huv = np.r_[huv, np.array(add_uv)]
    hji = np.r_[hji, np.array(add_ji)]
    hjw = np.r_[hjw, np.array(add_jw)]
    ht = np.r_[hidx.reshape(-1, 3), np.array(add_tri, dtype=np.int64)]
    # --- цвет: кожа головы подводится под кожу тела (шея, руки), чтобы шов в вырезе ворота не был виден
    bskin = neck_section(body, np.asarray(body_tex.convert('RGB'), dtype=np.float64), ref, s_body + 0.002)[3]
    hskin = neck_section(head, np.asarray(head_tex.convert('RGB'), dtype=np.float64), ref, s_head + 0.004)[3]
    gain = [1.0, 1.0, 1.0]
    if bskin is not None and hskin is not None:
        # не до конца (степень 0.75) и в разумных пределах: лицо должно остаться узнаваемым и не выгореть
        gain = [round(float(min(1.22, max(0.8, (b / max(1.0, h)) ** 0.75))), 3) for b, h in zip(bskin, hskin)]
    huv = huv + np.array([HEAD_U, 0.0])                 # пометка «это голова»: у неё своя текстура
    pos = np.r_[bpos, hpos]
    nrm = np.r_[bnrm, hnrm]
    uv = np.r_[buv, huv]
    ji = np.r_[bji, hji]
    jw = np.r_[bjw, hjw]
    idx = np.r_[bidx, ht.reshape(-1) + len(bpos)]
    return pos, nrm, uv, ji, jw, idx, gain


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
    is_head = [False] * n
    for i in range(n):
        wv.setData3(rv.getData3())
        wn.setData3(rn.getData3())
        uv = rt.getData2()
        if uv[0] > HEAD_U * 0.5:
            is_head[i] = True
            wt.setData2(uv[0] - HEAD_U, uv[1])
        else:
            wt.setData2(uv)
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
    prims = [GeomTriangles(Geom.UHStatic), GeomTriangles(Geom.UHStatic)]       # тело, голова
    for k in range(g2.getNumPrimitives()):
        p = g2.getPrimitive(k)
        for t in range(p.getNumPrimitives()):
            s, e = p.getPrimitiveStart(t), p.getPrimitiveEnd(t)
            v0 = p.getVertex(s)
            prims[1 if is_head[v0] else 0].addVertices(v0, p.getVertex(s + 1), p.getVertex(s + 2))
    out = []
    for prim in prims:
        if prim.getNumVertices() == 0:
            out.append(None)
            continue
        prim.closePrimitive()
        ng = Geom(nvd)
        ng.addPrimitive(prim)
        out.append(ng)
    return out[0], out[1], n, ntbt.getNumBlends()


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
        parts = {}                                  # имя -> (pos, nrm, uv, ji, jw, idx) на общем скелете

        def save_tex(name, img):
            img = img.convert('RGB')
            if name in LIPS and img.size == (512, 512):
                img = soften_lips(img, LIPS[name])
            img = pad_islands(img)
            # 256 цветов с подобранной палитрой: вдвое меньше файл, на глаз разницы нет.  Палитру уточняем
            # (kmeans): без этого редкие оттенки попадали в «чужую» ячейку — губы на лице человека в красной
            # футболке становились ярко-красными, как сама футболка.
            # (Красные штрихи у края «острова» головы в этой текстуре — губы в профиль, а не метки шва:
            # раньше они закрашивались кожей, и от рта оставались две красные точки.)
            img.quantize(256, method=Image.MEDIANCUT, dither=Image.NONE, kmeans=3).save(
                os.path.join(cdir, name + '.png'), optimize=True)

        def write_char(name, src, pos, nrm, uv, ji, jw, idx):
            gp = os.path.join(tmp, name + '.glb')
            char_gltf(ref, pos, nrm, uv, ji, jw, idx, gp)
            bp = os.path.join(tmp, name + '.bam')
            gltf2bam(gp, bp)
            root = base.loader.loadModel(Filename.fromOsSpecific(bp), noCache=True)
            char = root.find('**/+Character')
            new_nodes = []
            verts = blends = 0
            for gnp in char.findAllMatches('**/+GeomNode'):
                gn = gnp.node()
                body_gn, head_gn = GeomNode('skin'), GeomNode('head')
                for i in range(gn.getNumGeoms()):
                    gb, gh, n, nb = simplify_skin(gn.getGeom(i), name)
                    verts += n
                    blends += nb
                    if gb is not None:
                        body_gn.addGeom(gb)
                    if gh is not None:
                        head_gn.addGeom(gh)
                new_nodes.append(NodePath(body_gn))
                if head_gn.getNumGeoms():
                    new_nodes.append(NodePath(head_gn))
            for c in char.getChildren():
                if not isinstance(c.node(), AnimBundleNode):
                    c.removeNode()
            for nnp in new_nodes:
                nnp.reparentTo(char)
            root.setName(name)
            out = os.path.join(cdir, name + '.bam')
            root.writeBamFile(Filename.fromOsSpecific(out))
            mn, mx = pos.min(0), pos.max(0)
            print('  %-12s %-28s вершин %4d, наборов весов %3d, рост %.2f м' % (name, src, verts, blends,
                                                                                mx[1] - mn[1]))
            return dict(verts=verts, height=round(float(mx[1] - mn[1]), 3), source=src, model=name)

        textures = {}
        raw = {}                                    # текстуры как в исходнике (до перекраски штанов)
        for name, src in sorted(CHARS.items()):
            ch = Skinned(os.path.join(m2m_dir(), 'variations', src + '.glb'))
            mitten(ch)
            pos, nrm, ji, jw = retarget(ch, ref)
            textures[name] = raw[name] = Image.open(io.BytesIO(ch.image)).convert('RGB')
            if name in LEGS:
                textures[name], n = dye(raw[name], LEGS[name], **JEANS)
                print('  %-12s штаны перекрашены: %d точек развёртки' % (name, n))
            save_tex(name, textures[name])
            parts[name] = (pos, nrm, ch.uv, ji, jw, ch.idx)
            if name not in PARTS_ONLY:
                meta['chars'][name] = dict(write_char(name, src, pos, nrm, ch.uv, ji, jw, ch.idx), tex=name)
        planes = {}
        for name in sorted(set(n for pair in COMBOS.values() for n in pair)):
            planes[name] = neck_plane(name, parts[name], raw[name], ref, print)
        for name, (body, head) in sorted(COMBOS.items()):
            pos, nrm, uv, ji, jw, idx, gain = combine(ref, parts[body], parts[head], raw[body], raw[head],
                                                      planes[body], planes[head])
            info = write_char(name, '%s + %s' % (CHARS[body], CHARS[head]), pos, nrm, uv, ji, jw, idx)
            meta['chars'][name] = dict(info, tex=body, head_tex=head, head_gain=gain)
            print('  %-12s цвет головы под кожу тела: x%.2f x%.2f x%.2f' % ((name,) + tuple(gain)))
        for name, (model, what, op) in sorted(RECOLORS.items()):
            op = dict(op)
            legs = op.pop('legs', None)
            img = recolor(raw[model], what, **op)
            if model in LEGS:
                img = dye(img, LEGS[model], **(legs or JEANS))[0]
            save_tex(name, img)
        for name, (model, tex) in sorted(VARIANTS.items()):
            meta['chars'][name] = dict(meta['chars'][model], tex=tex)
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


# ---------------------------------------------------------------------------
# машины
# ---------------------------------------------------------------------------
# имя в игре -> (папка, файл модели, варианты окраски, по которым ищем окрашенные места)
CARS = {
    'wagon': ('Car 01', 'Car.obj', ['car.png', 'car_blue.png', 'car_gray.png', 'car_red.png']),
    'sleek': ('Car 02', 'Car2.obj', ['car2.png', 'car2_black.png', 'car2_red.png']),
    'hatch': ('Car 03', 'Car3.obj', ['car3.png', 'car3_red.png', 'car3_yellow.png']),
    'minivan': ('Car 04', 'Car4.obj', ['car4.png', 'car4_grey.png', 'car4_lightgrey.png', 'car4_lightorange.png']),
    'caprice': ('Car 05', 'Car5.obj', ['car5.png', 'car5_green.png', 'car5_grey.png']),
    'vintage': ('Car 07', 'Car7.obj', ['car7.png', 'car7_black.png', 'car7_brown.png', 'car7_green.png',
                                       'car7_grey.png', 'car7_red.png']),
    'stepvan': ('Car 08', 'Car8.obj', ['Car8.png', 'Car8_grey.png', 'Car8_purple.png']),
}
# модели с готовой раскраской: имя -> (папка, файл модели, текстура)
CARS_FIXED = {
    'police': ('Car 05', 'Car5_Police.obj', 'car5_police.png'),
    'wreck': ('Car 06', 'Car6.obj', 'car6.png'),
}
# фары и задние фонари (в единицах модели, для правого борта): (x, y, z)
CAR_LIGHTS = {
    'wagon': dict(head=(0.80, 2.96, 0.96), tail=(0.92, -2.98, 1.00)),
    'sleek': dict(head=(0.86, 3.20, 0.97), tail=(0.90, -3.30, 1.14)),
    'hatch': dict(head=(0.78, 2.78, 1.00), tail=(0.72, -2.74, 0.98)),
    'minivan': dict(head=(0.92, 3.12, 1.18), tail=(1.30, -2.98, 1.34)),
    'caprice': dict(head=(0.86, 3.66, 1.02), tail=(0.80, -3.64, 1.00)),
    'vintage': dict(head=(0.57, 2.44, 1.44), tail=(0.99, -2.70, 1.28)),
    'stepvan': dict(head=(0.95, 3.00, 1.06), tail=(1.20, -3.78, 0.86)),
}
CAR_LIGHTS['police'] = dict(CAR_LIGHTS['caprice'], siren=(0.52, -0.28, 2.26))
CAR_LIGHTS['stepvan']['siren'] = (0.62, 1.72, 3.36)


def read_obj(path):
    """Вершины, текстурные координаты и грани OBJ; оси сразу переводятся в игровые (Z вверх, нос к +Y)."""
    V, VT, faces = [], [], []
    with open(path, encoding='utf-8', errors='ignore') as f:
        for line in f:
            p = line.split()
            if not p:
                continue
            if p[0] == 'v':
                x, y, z = float(p[1]), float(p[2]), float(p[3])
                V.append((-x, z, y))                    # поворот, а не отражение: обход граней сохраняется
            elif p[0] == 'vt':
                VT.append((float(p[1]), float(p[2])))
            elif p[0] == 'f':
                face = []
                for tok in p[1:]:
                    a = tok.split('/')
                    vi = int(a[0])
                    ti = int(a[1]) if len(a) > 1 and a[1] else 1
                    face.append((vi - 1 if vi > 0 else len(V) + vi, ti - 1 if ti > 0 else len(VT) + ti))
                faces.append(face)
    return np.array(V), np.array(VT if VT else [(0.0, 0.0)]), faces


def components(V, faces):
    """Связные части модели (списки номеров граней): так находятся колёса, зеркала, бамперы."""
    key = {}
    rep = [key.setdefault(tuple(np.round(v, 4)), i) for i, v in enumerate(V)]
    parent = list(range(len(V)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for f in faces:
        r0 = find(rep[f[0][0]])
        for vi, _ in f[1:]:
            r = find(rep[vi])
            if r != r0:
                parent[r] = r0
    comps = {}
    for fi, f in enumerate(faces):
        comps.setdefault(find(rep[f[0][0]]), []).append(fi)
    return sorted(comps.values(), key=lambda c: -len(c))


def face_normal(pts):
    n = np.zeros(3)
    for k in range(len(pts)):
        a, b = pts[k], pts[(k + 1) % len(pts)]
        n += ((a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1]))
    l = np.linalg.norm(n)
    return n / l if l > 1e-12 else np.array((0.0, 0.0, 1.0))


class GeomOut(object):
    """Накопитель треугольников с нормалями и текстурными координатами (или цветом) -> GeomNode."""

    def __init__(self, colored=False):
        self.colored = colored
        self.v = []
        self.tris = []

    def face(self, pts, uvs=None, color=None, two_sided=False):
        n = face_normal(np.asarray(pts, float))
        base = len(self.v)
        for k, p in enumerate(pts):
            self.v.append((tuple(float(c) for c in p), tuple(float(c) for c in n),
                           tuple(uvs[k]) if uvs is not None else color))
        for k in range(1, len(pts) - 1):
            self.tris.append((base, base + k, base + k + 1))
        if two_sided:
            base = len(self.v)
            for k, p in enumerate(pts):
                self.v.append((tuple(float(c) for c in p), tuple(float(-c) for c in n),
                               tuple(uvs[k]) if uvs is not None else color))
            for k in range(1, len(pts) - 1):
                self.tris.append((base, base + k + 1, base + k))

    def box(self, x0, x1, y0, y1, z0, z1, color, top=None):
        c = color
        t = top or color
        self.face([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], color=c)
        self.face([(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)], color=c)
        self.face([(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)], color=c)
        self.face([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], color=c)
        self.face([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], color=t)

    def node(self, name):
        from panda3d.core import (GeomVertexFormat, GeomVertexData, Geom, GeomTriangles, GeomVertexWriter,
                                  GeomNode)
        fmt = GeomVertexFormat.getV3n3c4() if self.colored else GeomVertexFormat.getV3n3t2()
        vd = GeomVertexData(name, fmt, Geom.UHStatic)
        vd.setNumRows(len(self.v))
        vw = GeomVertexWriter(vd, 'vertex')
        nw = GeomVertexWriter(vd, 'normal')
        xw = GeomVertexWriter(vd, 'color' if self.colored else 'texcoord')
        for p, n, x in self.v:
            vw.addData3(*p)
            nw.addData3(*n)
            if self.colored:
                xw.addData4(x[0], x[1], x[2], 1.0)
            else:
                xw.addData2(x[0], x[1])
        tr = GeomTriangles(Geom.UHStatic)
        for a, b, c in self.tris:
            tr.addVertices(a, b, c)
        g = Geom(vd)
        g.addPrimitive(tr)
        gn = GeomNode(name)
        gn.addGeom(g)
        return gn


def convert_car(name, obj_path, lights):
    """OBJ -> veh/<имя>.bam: узел body/skin (кузов) и узел wheel (одно колесо в начале координат)."""
    from panda3d.core import NodePath
    _panda()
    V, VT, faces = read_obj(obj_path)
    comps = components(V, faces)
    zmin = V[:, 2].min()
    wheels = []
    body_faces = []
    for comp in comps:
        pts = np.array([V[vi] for fi in comp for vi, _ in faces[fi]])
        a, b = pts.min(0), pts.max(0)
        ext = b - a
        round_ = abs(ext[1] - ext[2]) < 0.12 * max(ext[1], ext[2])
        if len(comp) == 16 and round_ and ext[0] < ext[1] * 0.8 and a[2] < zmin + 0.06:
            wheels.append((comp, (a + b) * 0.5, (ext[1] + ext[2]) * 0.25))
        else:
            body_faces += comp
    main = np.array([V[vi] for fi in comps[0] for vi, _ in faces[fi]])
    allp = np.array([V[vi] for fi in body_faces for vi, _ in faces[fi]])
    if name == 'vintage':
        main = allp                                     # у «старинной» самая большая часть — рама с крыльями
    width = max(main[:, 0].max(), -main[:, 0].min()) * 2.0
    y0, y1 = allp[:, 1].min(), allp[:, 1].max()
    yc = (y0 + y1) * 0.5
    off = np.array((0.0, -yc, -zmin))                   # середина длины — в начало координат, колёса — на земле
    out = GeomOut()
    for fi in body_faces:
        f = faces[fi]
        out.face([V[vi] + off for vi, _ in f], [VT[ti] for _, ti in f])
    root = NodePath('car')
    body = root.attachNewNode('body')
    body.attachNewNode(out.node('skin'))
    info = dict(W=round(float(width), 3), L=round(float(y1 - y0), 3), H=round(float(allp[:, 2].max() - zmin), 3),
                tex=True, wheels=[])
    if wheels:
        # колесо-образец: правое переднее, наружной стороной к +X
        comp, c, r = sorted(wheels, key=lambda w: (0 if w[1][0] > 0 else 1, -w[1][1]))[0]
        wo = GeomOut()
        for fi in comp:
            f = faces[fi]
            wo.face([V[vi] - c for vi, _ in f], [VT[ti] for _, ti in f])
        root.attachNewNode(wo.node('wheel'))
        # порядок: переднее левое, переднее правое, заднее левое, заднее правое
        for comp, c, r in sorted(wheels, key=lambda w: (0 if w[1][1] > yc else 1, w[1][0])):
            info['wheels'].append(dict(x=round(float(c[0]), 3), y=round(float(c[1] - yc), 3), r=round(float(r), 3)))
    for key in ('head', 'tail', 'siren'):
        p = lights.get(key)
        if p:
            info[key] = [[-p[0], round(p[1] - yc, 3), round(p[2] - zmin, 3)],
                         [p[0], round(p[1] - yc, 3), round(p[2] - zmin, 3)]]
    if name == 'stepvan':
        # маячки на крыше для «скорой» и спецназа (узел siren; у обычных фургонов игра его убирает)
        bar = GeomOut(colored=True)
        sx, sy, sz = lights['siren']
        y, z = sy - yc, sz - zmin - 0.16
        bar.box(-0.95, 0.95, y - 0.16, y + 0.16, z - 0.07, z, (0.10, 0.10, 0.11))
        bar.box(-0.92, -0.30, y - 0.13, y + 0.13, z, z + 0.16, (0.85, 0.08, 0.06))
        bar.box(0.30, 0.92, y - 0.13, y + 0.13, z, z + 0.16, (0.10, 0.22, 0.90))
        bar.box(-0.30, 0.30, y - 0.13, y + 0.13, z, z + 0.12, (0.80, 0.80, 0.82))
        body.attachNewNode(bar.node('siren'))
    dst = os.path.join(OUT, 'veh', name + '.bam')
    root.writeBamFile(dst)
    return info


def texel_map(V, VT, faces, size):
    """Для каждого текселя — точка на модели и нормаль грани (чтобы рисовать на текстуре «по месту»)."""
    pos = np.zeros((size, size, 3))
    nrm = np.zeros((size, size, 3))
    ok = np.zeros((size, size), bool)
    ys, xs = np.mgrid[0:size, 0:size]
    cx, cy = xs + 0.5, ys + 0.5
    for f in faces:
        pts = np.array([V[vi] for vi, _ in f])
        uv = np.array([VT[ti] for _, ti in f])
        n = face_normal(pts)
        for k in range(1, len(f) - 1):
            t3 = pts[[0, k, k + 1]]
            tu = uv[[0, k, k + 1]] * size
            tu[:, 1] = size - tu[:, 1]
            d = (tu[1, 0] - tu[0, 0]) * (tu[2, 1] - tu[0, 1]) - (tu[2, 0] - tu[0, 0]) * (tu[1, 1] - tu[0, 1])
            if abs(d) < 1e-9:
                continue
            w1 = ((cx - tu[0, 0]) * (tu[2, 1] - tu[0, 1]) - (tu[2, 0] - tu[0, 0]) * (cy - tu[0, 1])) / d
            w2 = ((tu[1, 0] - tu[0, 0]) * (cy - tu[0, 1]) - (cx - tu[0, 0]) * (tu[1, 1] - tu[0, 1])) / d
            w0 = 1.0 - w1 - w2
            m = (w0 >= -0.02) & (w1 >= -0.02) & (w2 >= -0.02) & ~ok
            if m.any():
                ok |= m
                pos[m] = w0[m][:, None] * t3[0] + w1[m][:, None] * t3[1] + w2[m][:, None] * t3[2]
                nrm[m] = n
    return pos, nrm, ok


def _lum(a):
    return a[..., 0] * 0.30 + a[..., 1] * 0.59 + a[..., 2] * 0.11


def car_textures(name, folder, variants):
    """Раскладывает раскраску на два слоя, чтобы игра красила кузов в любой цвет:

      veh/<имя>.png        RGBA: всё, что не красится (стёкла, шины, фары, хром); на месте краски — прозрачно
      veh/<имя>_shade.png  оттенки серого: светотень краски (128 — «как есть», светлее — блик, темнее — тень)
    Окрашенные места — те, что различаются у вариантов набора."""
    from PIL import Image
    arrs = [np.asarray(Image.open(os.path.join(folder, v)).convert('RGB')).astype(float) for v in variants]
    diff = np.zeros(arrs[0].shape[:2])
    for a in arrs[1:]:
        diff = np.maximum(diff, np.abs(a - arrs[0]).sum(2))
    mask = diff > 24
    shade = np.zeros(mask.shape)
    wsum = 0.0
    for a in arrs:
        ref = np.median(a[mask], axis=0)
        l = float(_lum(ref))
        if l < 40.0:
            continue                                    # на чёрном варианте светотени почти не видно
        shade += _lum(a) / l
        wsum += 1.0
    shade /= wsum
    sh = np.where(mask, np.clip(shade * 127.5, 0, 255), 128.0)
    rgba = np.zeros(mask.shape + (4,), np.uint8)
    rgba[..., :3] = np.where(mask[..., None], np.clip(sh, 0, 255)[..., None], arrs[0]).astype(np.uint8)
    rgba[..., 3] = np.where(mask, 0, 255)
    Image.fromarray(rgba, 'RGBA').save(os.path.join(OUT, 'veh', name + '.png'), optimize=True)
    Image.fromarray(sh.astype(np.uint8), 'L').save(os.path.join(OUT, 'veh', name + '_shade.png'), optimize=True)
    return mask


def do_cars(meta):
    from PIL import Image
    src = cars_dir()
    vdir = os.path.join(OUT, 'veh')
    if os.path.isdir(vdir):
        shutil.rmtree(vdir)
    os.makedirs(vdir)
    veh = {}
    masks = {}
    for name, (folder, obj, variants) in CARS.items():
        veh[name] = convert_car(name, os.path.join(src, folder, obj), CAR_LIGHTS.get(name, {}))
        masks[name] = car_textures(name, os.path.join(src, folder), variants)
    for name, (folder, obj, tex) in CARS_FIXED.items():
        veh[name] = convert_car(name, os.path.join(src, folder, obj), CAR_LIGHTS.get(name, {}))
        veh[name]['fixed'] = True
        Image.open(os.path.join(src, folder, tex)).convert('RGB').save(os.path.join(vdir, name + '.png'),
                                                                        optimize=True)
    car_overlays(src, masks)
    import gen_bus                                      # автобуса в наборе нет — он свой, в том же стиле
    veh['bus'] = gen_bus.build(src)
    meta['vehicles'] = veh
    # остальная техника (ещё три машины, двухколёсные, детали тюнинга) лежит в той же папке — её собирает
    # tools/import_vehicles.py; раз папку пересоздали, собираем заново и её (если исходники скачаны)
    try:
        import import_vehicles
        import_vehicles.do_cars(meta)
        import_vehicles.do_bikes(meta)
        import_vehicles.do_parts(meta)
        veh = meta['vehicles']
    except Exception as e:                              # noqa: BLE001
        print('  остальная техника не пересобрана (%s): запустите tools/import_vehicles.py fetch, затем all' % e)
    size = sum(os.path.getsize(os.path.join(vdir, f)) for f in os.listdir(vdir))
    print('  машины: %d моделей, %d КБ' % (len(veh), size // 1024))
    for name in sorted(veh):
        v = veh[name]
        print('    %-8s Ш %.2f  Д %.2f  В %.2f  колёс %d' % (name, v['W'], v['L'], v['H'], len(v['wheels'])))


def car_overlays(src, masks):
    """Накладки поверх краски (RGBA): ржавчина, почтовая и медицинская раскраска фургона."""
    from PIL import Image
    vdir = os.path.join(OUT, 'veh')
    rng = np.random.RandomState(7)
    # --- ржавчина для «Ржавчины»: настоящая ржавая текстура из набора, пятнами, гуще — понизу
    V, VT, faces = read_obj(os.path.join(src, 'Car 01', 'Car.obj'))
    pos, nrm, ok = texel_map(V, VT, faces, 128)
    rust = np.asarray(Image.open(os.path.join(src, 'Car 06', 'car6.png')).convert('RGB')).astype(float)
    rust = rust[90:122, 0:64]
    rust = np.tile(rust, (4, 2, 1))[:128, :128]
    n = rng.rand(16, 16)
    n = np.asarray(Image.fromarray((n * 255).astype(np.uint8)).resize((128, 128), Image.BICUBIC)).astype(float) / 255
    n = n * 0.75 + rng.rand(128, 128) * 0.25
    z = pos[..., 2] - V[:, 2].min()
    low = np.clip(1.25 - z / 1.0, 0.25, 1.0)
    alpha = np.clip((n * low - 0.30) * 5.0, 0.0, 1.0) * 0.92
    alpha = np.where(masks['wagon'] & ok, alpha, 0.0)
    out = np.zeros((128, 128, 4), np.uint8)
    out[..., :3] = np.clip(rust * 0.9, 0, 255).astype(np.uint8)
    out[..., 3] = (alpha * 255).astype(np.uint8)
    Image.fromarray(out, 'RGBA').save(os.path.join(vdir, 'wagon_rust.png'), optimize=True)
    # --- фургон: почта (как в наборе) и «скорая» (красные полосы и крест)
    base = np.asarray(Image.open(os.path.join(src, 'Car 08', 'Car8.png')).convert('RGB')).astype(int)
    mail = np.asarray(Image.open(os.path.join(src, 'Car 08', 'Car8_mail.png')).convert('RGB')).astype(int)
    d = np.abs(base - mail).sum(2) > 30
    out = np.zeros((128, 128, 4), np.uint8)
    out[..., :3] = mail.astype(np.uint8)
    out[..., 3] = np.where(d, 255, 0)
    Image.fromarray(out, 'RGBA').save(os.path.join(vdir, 'stepvan_mail.png'), optimize=True)
    red = (200, 24, 24)
    amb = np.zeros((128, 128, 4), np.uint8)
    ys, xs = np.nonzero(d)
    stripe = d & (np.arange(128)[:, None] >= 100)
    small = d & (np.arange(128)[:, None] < 40)
    for m in (stripe, small):
        amb[m, :3] = red
        amb[m, 3] = 255
    # крест на месте конверта
    cx, cy = 43, 89
    for y in range(128):
        for x in range(128):
            dx, dy = abs(x - cx), abs(y - cy)
            if (dx <= 2 and dy <= 7) or (dy <= 2 and dx <= 7):
                amb[y, x, :3] = red
                amb[y, x, 3] = 255
    Image.fromarray(amb, 'RGBA').save(os.path.join(vdir, 'stepvan_ambulance.png'), optimize=True)


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
