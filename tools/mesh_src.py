# -*- coding: utf-8 -*-
"""Чтение исходных моделей разных форматов в один простой вид — список деталей (Part).

Нужен только импорту (tools/import_vehicles.py): игра читает готовые .bam.  Форматы: .blend (через
tools/blend_read.py), Collada .dae, Wavefront .obj, glTF (.glb и .gltf с отдельным .bin), OpenUSD .usda (текстовый).

    python tools/mesh_src.py файл [имена деталей…]        # список деталей и их габариты
"""
import json
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET

import numpy as np


class Part(object):
    """Деталь модели: вершины (n, 3), треугольники (m, 3) по вершинам, развёртка (m, 3, 2) или None,
    материал каждого треугольника (m,) — индекс в списке имён mats."""

    def __init__(self, name, verts, tris, uvs=None, mat=None, mats=None, color=None):
        self.name = name
        self.verts = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
        self.tris = np.asarray(tris, dtype=np.int64).reshape(-1, 3)
        self.uvs = None if uvs is None else np.asarray(uvs, dtype=np.float64).reshape(-1, 3, 2)
        self.mat = np.zeros(len(self.tris), dtype=np.int64) if mat is None else np.asarray(mat, dtype=np.int64)
        self.mats = list(mats or [''])
        self.color = color              # {имя материала: (r, g, b)} — если у исходника цвета, а не текстуры

    def bounds(self):
        return self.verts.min(0), self.verts.max(0)

    def copy(self, name=None):
        p = Part(name or self.name, self.verts.copy(), self.tris.copy(),
                 None if self.uvs is None else self.uvs.copy(), self.mat.copy(), list(self.mats), self.color)
        return p

    def transform(self, m):
        """Умножить вершины на матрицу 3x3 или 4x4 (вектор-столбец)."""
        m = np.asarray(m, dtype=np.float64)
        if m.shape == (4, 4):
            self.verts = self.verts.dot(m[:3, :3].T) + m[:3, 3]
            flip = np.linalg.det(m[:3, :3]) < 0
        else:
            self.verts = self.verts.dot(m.T)
            flip = np.linalg.det(m) < 0
        if flip:                                    # отражение выворачивает грани — возвращаем обход
            self.tris = self.tris[:, ::-1].copy()
            if self.uvs is not None:
                self.uvs = self.uvs[:, ::-1].copy()
        return self

    def select(self, mask, name=None):
        mask = np.asarray(mask, dtype=bool)
        return Part(name or self.name, self.verts, self.tris[mask], None if self.uvs is None else self.uvs[mask],
                    self.mat[mask], list(self.mats), self.color)


def merge(parts, name):
    """Склеить детали в одну (материалы объединяются по именам)."""
    verts, tris, uvs, mat, mats = [], [], [], [], []
    color = {}
    base = 0
    has_uv = all(p.uvs is not None for p in parts)
    for p in parts:
        idx = []
        for n in p.mats:
            if n not in mats:
                mats.append(n)
            idx.append(mats.index(n))
        verts.append(p.verts)
        tris.append(p.tris + base)
        mat.append(np.array(idx, dtype=np.int64)[p.mat] if len(p.tris) else p.mat)
        if has_uv:
            uvs.append(p.uvs)
        if p.color:
            color.update(p.color)
        base += len(p.verts)
    return Part(name, np.concatenate(verts), np.concatenate(tris), np.concatenate(uvs) if has_uv else None,
                np.concatenate(mat), mats, color or None)


def _fan(face):
    return [(face[0], face[k], face[k + 1]) for k in range(1, len(face) - 1)]


# ---------------------------------------------------------------------------
def read_blend(path):
    """Сетки из .blend.  Модификаторы (зеркало) не применяются — половинки зеркалит импорт."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import blend_read
    out = []
    for m in blend_read.read(path):
        tris, uvs, mat = [], [], []
        for i, face in enumerate(m.faces):
            for (a, b, c) in _fan(list(range(len(face)))):
                tris.append((face[a], face[b], face[c]))
                if m.uvs:
                    uvs.append((m.uvs[i][a], m.uvs[i][b], m.uvs[i][c]))
                mat.append(m.mats[i])
        names = list(m.mat_names) or ['']
        mat = [min(k, len(names) - 1) for k in mat]
        out.append(Part(m.name, m.verts, tris, uvs if m.uvs else None, mat, names))
    return out


def read_dae(path, only=None):
    """Детали из Collada (как пишет Blender): узлы с instance_geometry, матрицы узлов применены."""
    ns = {'c': 'http://www.collada.org/2005/11/COLLADASchema'}
    root = ET.parse(path).getroot()
    geoms = dict((g.get('id'), g) for g in root.findall('.//c:library_geometries/c:geometry', ns))
    out = []

    def floats(el):
        return np.array((el.text or '').split(), dtype=np.float64)

    def geometry(g):
        mesh = g.find('c:mesh', ns)
        src = {}
        for s in mesh.findall('c:source', ns):
            fa = s.find('c:float_array', ns)
            acc = s.find('c:technique_common/c:accessor', ns)
            if fa is None or acc is None or not (fa.text or '').strip():
                continue
            src['#' + s.get('id')] = floats(fa).reshape(-1, int(acc.get('stride')))
        vmap = {}
        for v in mesh.findall('c:vertices', ns):
            vmap['#' + v.get('id')] = v.find("c:input[@semantic='POSITION']", ns).get('source')
        pos = None
        tris, uvs, mat, mats = [], [], [], []
        for prim in list(mesh.findall('c:triangles', ns)) + list(mesh.findall('c:polylist', ns)):
            inputs = prim.findall('c:input', ns)
            stride = max(int(i.get('offset')) for i in inputs) + 1
            off = dict((i.get('semantic'), (int(i.get('offset')), i.get('source'))) for i in inputs)
            pe = prim.find('c:p', ns)
            if pe is None or not (pe.text or '').strip() or vmap[off['VERTEX'][1]] not in src:
                continue
            p = np.array(pe.text.split(), dtype=np.int64).reshape(-1, stride)
            pos = src[vmap[off['VERTEX'][1]]]
            uv = src.get(off['TEXCOORD'][1]) if 'TEXCOORD' in off else None
            vc = prim.find('c:vcount', ns)
            counts = [3] * (len(p) // 3) if vc is None else [int(v) for v in vc.text.split()]
            name = prim.get('material') or ''
            if name not in mats:
                mats.append(name)
            k = 0
            for n in counts:
                for (a, b, c) in _fan(list(range(n))):
                    tris.append((p[k + a][off['VERTEX'][0]], p[k + b][off['VERTEX'][0]], p[k + c][off['VERTEX'][0]]))
                    if uv is not None:
                        o = off['TEXCOORD'][0]
                        uvs.append((uv[p[k + a][o]][:2], uv[p[k + b][o]][:2], uv[p[k + c][o]][:2]))
                    mat.append(mats.index(name))
                k += n
        return pos, tris, (uvs if len(uvs) == len(tris) else None), mat, mats

    def walk(node, m):
        mx = node.find('c:matrix', ns)
        if mx is not None:
            m = m.dot(floats(mx).reshape(4, 4))
        ig = node.find('c:instance_geometry', ns)
        name = node.get('name') or node.get('id')
        if ig is not None and (only is None or name in only):
            pos, tris, uvs, mat, mats = geometry(geoms[ig.get('url')[1:]])
            if pos is not None and len(tris):
                p = Part(name, pos[:, :3], tris, uvs, mat, [n.replace('-material', '') for n in mats])
                out.append(p.transform(m))
        for ch in node.findall('c:node', ns):
            walk(ch, m)

    for n in root.findall('.//c:library_visual_scenes/c:visual_scene/c:node', ns):
        walk(n, np.eye(4))
    return out


def read_obj(path):
    """Детали из OBJ: по одной на объект (o) или группу (g)."""
    V, VT = [], []
    parts = []
    cur = None
    mats = []

    def start(name):
        d = dict(name=name, tris=[], uvs=[], mat=[], has_uv=True)
        parts.append(d)
        return d
    mi = 0
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            s = line.split()
            if not s:
                continue
            if s[0] == 'v':
                V.append([float(x) for x in s[1:4]])
            elif s[0] == 'vt':
                VT.append([float(s[1]), float(s[2]) if len(s) > 2 else 0.0])
            elif s[0] in ('o', 'g'):
                cur = start(' '.join(s[1:]) or 'part')
            elif s[0] == 'usemtl':
                name = ' '.join(s[1:])
                if name not in mats:
                    mats.append(name)
                mi = mats.index(name)
            elif s[0] == 'f':
                if cur is None:
                    cur = start('part')
                idx = []
                for tok in s[1:]:
                    a = tok.split('/')
                    vi = int(a[0])
                    ti = int(a[1]) if len(a) > 1 and a[1] else 0
                    idx.append((vi - 1 if vi > 0 else len(V) + vi, ti - 1 if ti > 0 else (len(VT) + ti if ti < 0 else -1)))
                for (a, b, c) in _fan(idx):
                    cur['tris'].append((a[0], b[0], c[0]))
                    if a[1] < 0 or b[1] < 0 or c[1] < 0:
                        cur['has_uv'] = False
                        cur['uvs'].append(((0, 0), (0, 0), (0, 0)))
                    else:
                        cur['uvs'].append((VT[a[1]], VT[b[1]], VT[c[1]]))
                    cur['mat'].append(mi)
    V = np.array(V, dtype=np.float64).reshape(-1, 3)
    out = []
    for d in parts:
        if not d['tris']:
            continue
        tris = np.array(d['tris'], dtype=np.int64)
        used = np.unique(tris)
        remap = np.full(len(V), -1, dtype=np.int64)
        remap[used] = np.arange(len(used))
        out.append(Part(d['name'], V[used], remap[tris], d['uvs'] if d['has_uv'] else None, d['mat'], mats or ['']))
    return out


def obj_colors(path):
    """Цвета материалов из .mtl рядом с .obj: {имя: (r, g, b)}."""
    mtl = os.path.splitext(path)[0] + '.mtl'
    out = {}
    if not os.path.isfile(mtl):
        return out
    name = None
    with open(mtl, encoding='utf-8', errors='replace') as f:
        for line in f:
            s = line.split()
            if not s:
                continue
            if s[0] == 'newmtl':
                name = ' '.join(s[1:])
            elif s[0] == 'Kd' and name is not None:
                out[name] = tuple(float(x) for x in s[1:4])
    return out


def read_glb(path, nodes=False):
    """Детали из .glb или .gltf: по одной на узел с сеткой, матрицы узлов применены.  Возвращает
    (детали, картинки): картинки — {номер материала: байты PNG/JPEG/WebP или путь к внешнему файлу}.
    nodes=True — третьим идёт словарь {имя узла: его место в мире} (узлы-метки без сетки: седло, ручки руля)."""
    with open(path, 'rb') as f:
        data = f.read()
    if data[:4] == b'glTF':
        magic, ver, total = struct.unpack('<4sII', data[:12])
        pos = 12
        js = blob = None
        while pos < total:
            n, kind = struct.unpack('<I4s', data[pos:pos + 8])
            chunk = data[pos + 8:pos + 8 + n]
            if kind == b'JSON':
                js = json.loads(chunk.decode('utf-8'))
            elif kind == b'BIN\x00':
                blob = chunk
            pos += 8 + n
        blobs = [blob]
    else:                                           # .gltf: описание текстом, данные — в соседних файлах
        js = json.loads(data.decode('utf-8'))
        blobs = []
        for b in js.get('buffers', []):
            with open(os.path.join(os.path.dirname(path), b['uri'].replace('%20', ' ')), 'rb') as f:
                blobs.append(f.read())
    CT = {5120: 'b', 5121: 'B', 5122: 'h', 5123: 'H', 5125: 'I', 5126: 'f'}
    NC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}

    def acc(i):
        a = js['accessors'][i]
        bv = js['bufferViews'][a['bufferView']]
        blob = blobs[bv.get('buffer', 0)]
        dt = np.dtype('<' + CT[a['componentType']])
        k = NC[a['type']]
        off = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
        stride = bv.get('byteStride') or dt.itemsize * k
        if stride == dt.itemsize * k:
            arr = np.frombuffer(blob, dtype=dt, count=a['count'] * k, offset=off).reshape(a['count'], k)
        else:
            arr = np.stack([np.frombuffer(blob, dtype=dt, count=k, offset=off + j * stride) for j in range(a['count'])])
        arr = arr.astype(np.float64)
        if a.get('normalized'):
            arr /= float(np.iinfo(dt).max)
        return arr
    images = {}
    mats = []
    for mi, m in enumerate(js.get('materials', [])):
        mats.append(m.get('name') or 'mat%d' % mi)
        tex = m.get('pbrMetallicRoughness', {}).get('baseColorTexture')
        if tex is not None:
            t = js['textures'][tex['index']]
            source = t.get('source')
            if source is None:                      # картинка в WebP: её номер лежит в расширении
                source = t.get('extensions', {}).get('EXT_texture_webp', {}).get('source')
            if source is None:
                continue
            img = js['images'][source]
            if 'bufferView' in img:
                bv = js['bufferViews'][img['bufferView']]
                blob = blobs[bv.get('buffer', 0)]
                images[mi] = blob[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']]
            elif 'uri' in img:
                images[mi] = os.path.join(os.path.dirname(path), img['uri'].replace('%20', ' '))
    out = []
    marks = {}

    def local(n):
        if 'matrix' in n:
            return np.array(n['matrix'], dtype=np.float64).reshape(4, 4).T
        m = np.eye(4)
        if 'scale' in n:
            m = np.diag(list(n['scale']) + [1.0])
        if 'rotation' in n:
            x, y, z, w = n['rotation']
            r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
                          [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
                          [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0], [0, 0, 0, 1.0]])
            m = r.dot(m)
        if 'translation' in n:
            t = np.eye(4)
            t[:3, 3] = n['translation']
            m = t.dot(m)
        return m

    def walk(ni, m):
        n = js['nodes'][ni]
        m = m.dot(local(n))
        if n.get('name'):
            marks[n['name']] = m[:3, 3].copy()
        if 'mesh' in n:
            verts, tris, uvs, mat = [], [], [], []
            base = 0
            has_uv = True
            for prim in js['meshes'][n['mesh']]['primitives']:
                p = acc(prim['attributes']['POSITION'])[:, :3]
                idx = acc(prim['indices']).astype(np.int64).reshape(-1, 3) if 'indices' in prim else np.arange(len(p)).reshape(-1, 3)
                if 'TEXCOORD_0' in prim['attributes']:
                    uv = acc(prim['attributes']['TEXCOORD_0'])[:, :2]
                    uv = np.c_[uv[:, 0], 1.0 - uv[:, 1]]            # в glTF v идёт сверху вниз
                    uvs.append(uv[idx])
                else:
                    has_uv = False
                verts.append(p)
                tris.append(idx + base)
                mat.append(np.full(len(idx), prim.get('material', 0), dtype=np.int64))
                base += len(p)
            part = Part(n.get('name') or 'node%d' % ni, np.concatenate(verts), np.concatenate(tris),
                        np.concatenate(uvs) if has_uv and uvs else None, np.concatenate(mat), mats or [''])
            out.append(part.transform(m))
        for c in n.get('children', []):
            walk(c, m)
    for r in js['scenes'][js.get('scene', 0)]['nodes']:
        walk(r, np.eye(4))
    if nodes:
        return out, images, marks
    return out, images


def read_usda(path):
    """Детали из текстового OpenUSD (как в сборнике quaternius-stage): по одной на Mesh; материал грани —
    из GeomSubset, цвета материалов — diffuseColor.  Матрицы Xform применены."""
    text = open(path, encoding='utf-8').read()
    tok = re.compile(r'"(?:[^"\\]|\\.)*"|[{}()\[\]=,]|[^\s{}()\[\]=,"]+')
    toks = tok.findall(text)
    n = len(toks)
    out = []
    colors = {}
    pos = [0]

    def value(i):
        """Значение после '=': число, строка, кортеж или список.  Возвращает (значение, следующий индекс)."""
        t = toks[i]
        if t == '[' or t == '(':
            close = ']' if t == '[' else ')'
            items = []
            i += 1
            while toks[i] != close:
                if toks[i] == ',':
                    i += 1
                    continue
                v, i = value(i)
                items.append(v)
            return items, i + 1
        if t.startswith('"'):
            return t[1:-1], i + 1
        if t.startswith('<'):
            return t, i + 1
        try:
            return float(t), i + 1
        except ValueError:
            return t, i + 1

    def block(i, m, mesh, depth):
        """Разобрать тело { … } начиная с индекса i (после '{').  Возвращает индекс после '}'."""
        props = {}
        while i < n and toks[i] != '}':
            t = toks[i]
            if t in ('def', 'over', 'class'):
                kind = toks[i + 1] if not toks[i + 1].startswith('"') else ''
                j = i + (2 if kind else 1)
                name = toks[j][1:-1]
                j += 1
                if toks[j] == '(':                           # метаданные
                    d = 1
                    j += 1
                    while d:
                        d += toks[j] == '('
                        d -= toks[j] == ')'
                        j += 1
                assert toks[j] == '{', (path, name, toks[j])
                sub = dict(kind=kind, name=name, props={}, subsets=[], children=[])
                j = block(j + 1, m, sub, depth + 1)
                mesh.setdefault('children', []).append(sub)
                i = j
                continue
            # свойство: [custom] [uniform] тип[[]] имя[:…] [= значение] [( метаданные )]
            j = i
            words = []
            while j < n and toks[j] not in ('=', '}', '(') and toks[j] not in ('def', 'over', 'class'):
                words.append(toks[j])
                j += 1
                if len(words) >= 2 and not words[-1] in ('custom', 'uniform', 'varying', 'prepend', 'append', 'delete', 'add', 'rel') \
                        and not words[-2] in ('custom', 'uniform', 'varying', 'prepend', 'append', 'delete', 'add') and toks[j] not in ('=', '(', '[', ']'):
                    break
            name = words[-1] if words else ''
            val = None
            if j < n and toks[j] == '[' and toks[j + 1] == ']':    # «тип[] имя»
                j += 2
                name = toks[j]
                j += 1
            if j < n and toks[j] == '=':
                val, j = value(j + 1)
            if j < n and toks[j] == '(':
                d = 1
                j += 1
                while d:
                    d += toks[j] == '('
                    d -= toks[j] == ')'
                    j += 1
            if name:
                mesh.setdefault('props', {})[name] = val
            i = max(j, i + 1)
        return i + 1

    top = dict(children=[], props={})
    i = 0
    while i < n:
        if toks[i] in ('def', 'over', 'class'):
            i = block(i, None, top, 0) if False else i
            # разбираем как тело верхнего уровня
            j = i
            fake = toks[:]
            break
        i += 1
    # верхний уровень — та же грамматика, что и тело блока: добавим закрывающую скобку
    toks.append('}')
    n = len(toks)
    block(i, None, top, 0)

    def xform(props, m):
        order = props.get('xformOpOrder') or []
        for op in order:
            v = props.get(op)
            if v is None:
                continue
            if op.startswith('xformOp:transform'):
                m = m.dot(np.array(v, dtype=np.float64).reshape(4, 4).T)
            elif op.startswith('xformOp:translate'):
                t = np.eye(4)
                t[:3, 3] = v
                m = m.dot(t)
            elif op.startswith('xformOp:scale'):
                m = m.dot(np.diag(list(v) + [1.0]))
            elif op.startswith('xformOp:rotateXYZ'):
                rx, ry, rz = [np.radians(a) for a in v]
                cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
                X = np.array([[1, 0, 0, 0], [0, cx, -sx, 0], [0, sx, cx, 0], [0, 0, 0, 1.0]])
                Y = np.array([[cy, 0, sy, 0], [0, 1, 0, 0], [-sy, 0, cy, 0], [0, 0, 0, 1.0]])
                Z = np.array([[cz, -sz, 0, 0], [sz, cz, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1.0]])
                m = m.dot(Z).dot(Y).dot(X)
            elif op.startswith('xformOp:orient'):
                w, x, y, z = v[0], v[1], v[2], v[3]
                r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
                              [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
                              [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0], [0, 0, 0, 1.0]])
                m = m.dot(r)
        return m

    def visit(node, m):
        props = node.get('props', {})
        m = xform(props, m)
        kind = node.get('kind')
        if kind == 'Shader':
            c = props.get('inputs:diffuseColor')
            if isinstance(c, list) and len(c) == 3:
                colors[node['_mat']] = tuple(float(x) for x in c)
        if kind == 'Mesh' and props.get('points'):
            pts = np.array(props['points'], dtype=np.float64).reshape(-1, 3)
            counts = [int(v) for v in props.get('faceVertexCounts') or []]
            idx = [int(v) for v in props.get('faceVertexIndices') or []]
            st = props.get('primvars:st') or props.get('primvars:UVMap') or props.get('primvars:st0')
            sti = props.get('primvars:st:indices') or props.get('primvars:UVMap:indices')
            mats = []
            face_mat = np.zeros(len(counts), dtype=np.int64)
            bind = props.get('material:binding')
            if bind:
                mats.append(str(bind).strip('<>').split('/')[-1])
            for ch in node.get('children', []):
                if ch.get('kind') == 'GeomSubset':
                    b = ch['props'].get('material:binding')
                    name = str(b).strip('<>').split('/')[-1] if b else ch['name']
                    if name not in mats:
                        mats.append(name)
                    for fi in ch['props'].get('indices') or []:
                        face_mat[int(fi)] = mats.index(name)
            tris, uvs, mat = [], [], []
            k = 0
            for fi, c in enumerate(counts):
                for (a, b, cc) in _fan(list(range(c))):
                    tris.append((idx[k + a], idx[k + b], idx[k + cc]))
                    if st:
                        if sti:
                            uvs.append((st[int(sti[k + a])], st[int(sti[k + b])], st[int(sti[k + cc])]))
                        elif len(st) == len(idx):
                            uvs.append((st[k + a], st[k + b], st[k + cc]))
                        else:
                            uvs.append((st[idx[k + a]], st[idx[k + b]], st[idx[k + cc]]))
                    mat.append(face_mat[fi])
                k += c
            p = Part(node['name'], pts, tris, uvs if st else None, mat, mats or [''])
            out.append(p.transform(m))
        for ch in node.get('children', []):
            if ch.get('kind') == 'Material':
                for s in ch.get('children', []):
                    s['_mat'] = ch['name']
            visit(ch, m)
    visit(top, np.eye(4))
    for p in out:
        p.color = colors
    return out


def read(path, **kw):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.blend':
        return read_blend(path)
    if ext == '.dae':
        return read_dae(path, **kw)
    if ext == '.obj':
        parts = read_obj(path)
        col = obj_colors(path)
        for p in parts:
            p.color = col or None
        return parts
    if ext in ('.glb', '.gltf'):
        return read_glb(path)[0]
    if ext == '.usda':
        return read_usda(path)
    raise ValueError(path)


if __name__ == '__main__':
    only = set(sys.argv[2:]) or None
    for p in read(sys.argv[1]):
        if only and p.name not in only:
            continue
        lo, hi = p.bounds()
        print('%-28s вершин %5d треуг. %5d uv %-3s материалы %s  x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f' % (
            p.name, len(p.verts), len(p.tris), 'да' if p.uvs is not None else 'нет', p.mats,
            lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
