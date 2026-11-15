# -*- coding: utf-8 -*-
"""Чтение моделей из файлов Blender (.blend) без самого Blender.

Нужен только для импорта наборов, которые выложены в .blend (версии 2.79–2.9x): файл разбирается по своему
описанию структур (DNA) библиотекой blender-asset-tracer, отсюда берутся сетки объектов — вершины, грани,
развёртка, номера материалов — и матрицы объектов.

    pip install blender-asset-tracer numpy
    python tools/blend_read.py файл.blend            # список объектов
    python tools/blend_read.py файл.blend out.obj    # все сетки в один OBJ (для проверки глазами)
"""
import struct
import sys
from pathlib import Path

import numpy as np


def _array(block, path, fmt, count=None):
    """Поле path у всех элементов массива структур block -> numpy (n, k).  fmt: '3f', 'I', 'i', 'h', '2f'."""
    bf = block.bfile
    st = block.dna_type
    field, off = st.field_from_path(bf.header.pointer_size, path)
    n = block.count if count is None else count
    k = int(fmt[:-1] or 1)
    e = bf.header.endian_str
    e = e.decode() if isinstance(e, bytes) else e
    dt = np.dtype(e + fmt[-1])
    bf.fileobj.seek(block.file_offset)
    raw = np.frombuffer(bf.fileobj.read(st.size * n), dtype=np.uint8).reshape(n, st.size)
    return np.frombuffer(raw[:, off:off + dt.itemsize * k].tobytes(), dtype=dt).reshape(n, k).copy()


class Mesh(object):
    """Сетка одного объекта в мировых координатах Blender (Z вверх, -Y — вперёд у большинства моделей)."""

    def __init__(self, name, parent, matrix, verts, faces, uvs, mats, mat_names):
        self.name = name
        self.parent = parent
        self.matrix = matrix            # 4x4, строки как в Blender (вектор-строка * матрица)
        self.verts = verts              # (n, 3) в мировых координатах
        self.local = None
        self.faces = faces              # список граней: индексы вершин
        self.uvs = uvs                  # список граней: [(u, v), ...] или None
        self.mats = mats                # номер материала для каждой грани
        self.mat_names = mat_names


def read(path):
    from blender_asset_tracer import blendfile
    bf = blendfile.open_cached(Path(path))
    out = []
    for ob in bf.find_blocks_from_code(b'OB'):
        if ob[b'type'] != 1:
            continue
        me = ob.get_pointer(b'data')
        if me is None or not me[b'totvert'] or not me[b'totpoly']:
            continue
        name = ob[b'id', b'name'].decode()[2:]
        par = ob.get_pointer(b'parent')
        m = np.array(ob[b'obmat'], dtype=np.float64).reshape(4, 4)
        nv, nl, np_ = me[b'totvert'], me[b'totloop'], me[b'totpoly']
        co = _array(me.get_pointer(b'mvert'), b'co', '3f', nv).astype(np.float64)
        lv = _array(me.get_pointer(b'mloop'), b'v', 'I', nl)[:, 0]
        mp = me.get_pointer(b'mpoly')
        ls = _array(mp, b'loopstart', 'i', np_)[:, 0]
        lt = _array(mp, b'totloop', 'i', np_)[:, 0]
        mn = _array(mp, b'mat_nr', 'h', np_)[:, 0]
        uvb = me.get_pointer(b'mloopuv')
        uv = _array(uvb, b'uv', '2f', nl) if uvb is not None else None
        world = np.c_[co, np.ones(nv)].dot(m)[:, :3]
        faces = [[int(lv[s + k]) for k in range(t)] for s, t in zip(ls, lt)]
        uvs = [[(float(uv[s + k][0]), float(uv[s + k][1])) for k in range(t)] for s, t in zip(ls, lt)] if uv is not None else None
        names = []
        if me[b'totcol']:
            try:
                for mat in me.iter_array_of_pointers(b'mat', me[b'totcol']):
                    names.append(mat[b'id', b'name'].decode()[2:] if mat is not None else '')
            except Exception:
                names = []
        mesh = Mesh(name, par[b'id', b'name'].decode()[2:] if par else None, m, world, faces, uvs,
                    [int(v) for v in mn], names)
        mesh.local = co
        out.append(mesh)
    return out


def write_obj(meshes, path):
    with open(path, 'w') as f:
        vo = 1
        to = 1
        for m in meshes:
            f.write('o %s\n' % m.name.replace(' ', '_'))
            for v in m.verts:
                f.write('v %.5f %.5f %.5f\n' % tuple(v))
            if m.uvs:
                for fu in m.uvs:
                    for (u, v) in fu:
                        f.write('vt %.5f %.5f\n' % (u, v))
            k = 0
            for i, face in enumerate(m.faces):
                if m.uvs:
                    f.write('f ' + ' '.join('%d/%d' % (vi + vo, to + k + j) for j, vi in enumerate(face)) + '\n')
                    k += len(face)
                else:
                    f.write('f ' + ' '.join(str(vi + vo) for vi in face) + '\n')
            vo += len(m.verts)
            to += k


if __name__ == '__main__':
    ms = read(sys.argv[1])
    for m in ms:
        mn, mx = m.verts.min(0), m.verts.max(0)
        print('%-28s родитель %-14s вершин %4d граней %4d uv %s материалы %s  размеры %.2f x %.2f x %.2f  центр %.2f %.2f %.2f' % (
            m.name, m.parent or '-', len(m.verts), len(m.faces), 'да' if m.uvs else 'нет', m.mat_names or sorted(set(m.mats)),
            mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2], (mx[0] + mn[0]) / 2, (mx[1] + mn[1]) / 2, (mx[2] + mn[2]) / 2))
    if len(sys.argv) > 2:
        write_obj(ms, sys.argv[2])
        print('записан', sys.argv[2])
