# -*- coding: utf-8 -*-
"""Импорт моделей из свободных (CC0) наборов Quaternius в формат игры (assets/models/*.bam).

Нужен только разработчику, который хочет заменить или добавить модели; сама игра
читает уже готовые .bam и ни от чего из перечисленного ниже не зависит.

    pip install panda3d-gltf usd-core numpy pillow
    python tools/import_models.py fetch            # скачать исходники в .cache/model_src (git)
    python tools/import_models.py all              # персонажи, анимации, машины, оружие

Исходники (оба набора — работы Quaternius, лицензия CC0 1.0):
  * персонажи со скелетом и анимациями — «Ultimate Modular Men / Women» в glTF;
  * машины и оружие — пакеты Cars, Public Transport, Zombie Apocalypse Kit,
    Toon Shooter Game Kit, Ultimate Gun в OpenUSD (репозиторий quaternius-stage).

Что делает импорт:
  * сваривает вершины персонажей (в исходниках каждая грань хранит свои вершины —
    это вчетверо больше работы для скелетной анимации на процессоре);
  * заменяет материалы на простые цвета, а детали одежды и кузова раскладывает по
    именованным узлам, чтобы игра могла перекрашивать их на лету;
  * приводит всё к осям игры (Z вверх, нос машины и взгляд персонажа — к +Y).
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, '.cache', 'model_src')
OUT = os.path.join(ROOT, 'assets', 'models')

CHAR_REPO = ('https://github.com/HamaDler/sami-park-mayhem', 'assets/characters/crowd')
USD_REPO = ('https://github.com/chibifire-stages/quaternius-stage',
            'models/Cars models/PublicTransport models/ZombieApocalypseKit models/ToonShooterGameKit '
            'models/UltimateGun')

# какие анимации из набора нужны игре
ANIMS = ['Idle', 'Idle_Neutral', 'Walk', 'Run', 'Run_Back', 'Punch_Left', 'Punch_Right', 'Kick_Right',
         'Sword_Slash', 'Idle_Gun', 'Idle_Gun_Pointing', 'Idle_Gun_Shoot', 'Gun_Shoot', 'Run_Shoot',
         'HitRecieve', 'HitRecieve_2', 'Death', 'Interact', 'Wave', 'Roll']

# персонажи: имя в игре -> (папка, файл)
CHARS = {
    'm_casual': ('men', 'Casual_2'), 'm_hoodie': ('men', 'Casual_Hoodie'), 'm_beach': ('men', 'Beach'),
    'm_punk': ('men', 'Punk'), 'm_suit': ('men', 'Suit'), 'm_worker': ('men', 'Worker'),
    'm_farmer': ('men', 'Farmer'), 'm_jacket': ('men', 'Adventurer'), 'm_swat': ('men', 'Swat'),
    'f_casual': ('women', 'Casual'), 'f_formal': ('women', 'Formal'), 'f_punk': ('women', 'Punk'),
    'f_suit': ('women', 'Suit'), 'f_worker': ('women', 'Worker'), 'f_soldier': ('women', 'Soldier'),
    'f_jacket': ('women', 'Adventurer'),
}
DROP_PARTS = ('Backpack', 'Sword')        # рюкзак и меч в городе ни к чему


def srgb(v):
    v = max(0.0, min(1.0, float(v)))
    return 12.92 * v if v <= 0.0031308 else 1.055 * (v ** (1 / 2.4)) - 0.055


def run(cmd, **kw):
    print('  $', ' '.join(cmd))
    subprocess.check_call(cmd, **kw)


# ---------------------------------------------------------------------------
def fetch():
    os.makedirs(SRC, exist_ok=True)
    for name, (url, paths) in (('chars', CHAR_REPO), ('usd', USD_REPO)):
        dst = os.path.join(SRC, name)
        if os.path.isdir(dst):
            print(dst, '— уже скачано')
            continue
        run(['git', 'clone', '--depth', '1', '--filter=blob:none', '--sparse', url, dst])
        run(['git', 'sparse-checkout', 'set'] + paths.split(), cwd=dst)


def chars_dir():
    return os.path.join(SRC, 'chars', CHAR_REPO[1])


def usd_dir():
    return os.path.join(SRC, 'usd', 'models')


# ---------------------------------------------------------------------------
# персонажи
# ---------------------------------------------------------------------------
def _panda():
    from panda3d.core import loadPrcFileData
    loadPrcFileData('', 'window-type none\naudio-library-name null\nmodel-cache-dir\n')
    from direct.showbase.ShowBase import ShowBase
    import builtins
    if not hasattr(builtins, 'base'):
        ShowBase()
    return builtins.base


def weld_geom(geom, name):
    """Сварить совпадающие вершины скелетного меша и пересчитать сглаженные нормали."""
    import numpy as np
    from panda3d.core import (GeomVertexReader, GeomVertexFormat, GeomVertexArrayFormat, GeomVertexData, Geom,
                              GeomTriangles, GeomVertexWriter, InternalName, GeomVertexAnimationSpec,
                              TransformBlendTable, TransformBlend, SparseArray)
    vd = geom.getVertexData()
    tbt = vd.getTransformBlendTable()
    n = vd.getNumRows()
    rv = GeomVertexReader(vd, 'vertex')
    rb = GeomVertexReader(vd, 'transform_blend')
    pos = np.empty((n, 3))
    blend = np.empty(n, dtype=np.int64)
    for i in range(n):
        p = rv.getData3()
        pos[i] = (p[0], p[1], p[2])
        blend[i] = rb.getData1i()
    g2 = geom.decompose()
    idx = []
    for k in range(g2.getNumPrimitives()):
        prim = g2.getPrimitive(k)
        for t in range(prim.getNumPrimitives()):
            for j in range(prim.getPrimitiveStart(t), prim.getPrimitiveEnd(t)):
                idx.append(prim.getVertex(j))
    idx = np.array(idx, dtype=np.int64).reshape(-1, 3)
    key = {}
    remap = np.empty(n, dtype=np.int64)
    new_pos = []
    new_blend = []
    for i in range(n):
        k = (round(pos[i, 0], 4), round(pos[i, 1], 4), round(pos[i, 2], 4), int(blend[i]))
        j = key.get(k)
        if j is None:
            j = key[k] = len(new_pos)
            new_pos.append(pos[i])
            new_blend.append(int(blend[i]))
        remap[i] = j
    tri = remap[idx]
    # выбрасываем выродившиеся треугольники
    ok = (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
    tri = tri[ok]
    P = np.array(new_pos)
    nrm = np.zeros_like(P)
    fn = np.cross(P[tri[:, 1]] - P[tri[:, 0]], P[tri[:, 2]] - P[tri[:, 0]])      # длина = удвоенная площадь
    for c in range(3):
        np.add.at(nrm, tri[:, c], fn)
    ln = np.linalg.norm(nrm, axis=1)
    ln[ln < 1e-12] = 1.0
    nrm /= ln[:, None]

    a0 = GeomVertexArrayFormat()
    a0.addColumn(InternalName.getVertex(), 3, Geom.NTFloat32, Geom.CPoint)
    a0.addColumn(InternalName.getNormal(), 3, Geom.NTFloat32, Geom.CNormal)
    a1 = GeomVertexArrayFormat()
    a1.addColumn(InternalName.getTransformBlend(), 1, Geom.NTUint16, Geom.CIndex)
    fmt = GeomVertexFormat()
    fmt.addArray(a0)
    fmt.addArray(a1)
    spec = GeomVertexAnimationSpec()
    spec.setPanda()
    fmt.setAnimation(spec)
    # выравнивание по 16 байт включает в движке быстрый (SSE) путь пересчёта вершин
    fmt.alignColumnsForAnimation()
    fmt = GeomVertexFormat.registerFormat(fmt)
    # таблица смешивания костей: только те сочетания, что нужны этим вершинам,
    # и с правильным числом строк (иначе движок читает за пределами массива)
    # В исходнике почти у каждой вершины свой набор весов, а движок на каждом кадре
    # пересчитывает матрицу для КАЖДОГО набора — это и есть основная цена анимации.
    # Оставляем две главные кости и округляем вес до четверти: наборов становится
    # в десятки раз меньше, а сгибы суставов остаются плавными.
    ntbt = TransformBlendTable()
    bmap = {}
    for i, b in enumerate(new_blend):
        j = bmap.get(b)
        if j is None:
            ob = tbt.getBlend(b)
            infl = sorted(((ob.getWeight(k), k) for k in range(ob.getNumTransforms())), reverse=True)[:2]
            nb = TransformBlend()
            if len(infl) == 1 or infl[0][0] <= 0.0:
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
        new_blend[i] = j
    weld_geom.blends += ntbt.getNumBlends()
    ntbt.setRows(SparseArray.range(0, len(P)))
    nvd = GeomVertexData(name, fmt, Geom.UHStatic)
    nvd.setTransformBlendTable(ntbt)
    nvd.setNumRows(len(P))
    wv = GeomVertexWriter(nvd, 'vertex')
    wn = GeomVertexWriter(nvd, 'normal')
    wb = GeomVertexWriter(nvd, 'transform_blend')
    for i in range(len(P)):
        wv.setData3(float(P[i, 0]), float(P[i, 1]), float(P[i, 2]))
        wn.setData3(float(nrm[i, 0]), float(nrm[i, 1]), float(nrm[i, 2]))
        wb.setData1i(new_blend[i])
    prim = GeomTriangles(Geom.UHStatic)
    for a, b, c in tri:
        prim.addVertices(int(a), int(b), int(c))
    prim.closePrimitive()
    ng = Geom(nvd)
    ng.addPrimitive(prim)
    return ng, n, len(P)


weld_geom.blends = 0
WEIGHT_STEPS = 4
# где у оружия точка хвата: доля длины от казённой части и доля высоты от низа рукояти
HAND_GRIP = (0.22, 0.20)


def convert_character(name, folder, fname, tmp):
    """glTF -> assets/models/chars/<name>.bam (без анимаций).  Возвращает сведения для models.json."""
    from panda3d.core import NodePath, GeomNode, MaterialAttrib, Filename, PandaNode, AnimBundleNode
    base = _panda()
    src = os.path.join(chars_dir(), folder, fname + '.gltf')
    tb = os.path.join(tmp, name + '.bam')
    subprocess.check_call([os.path.join(os.path.dirname(sys.executable), 'gltf2bam'), '--animations', 'skip', src, tb],
                          stdout=subprocess.DEVNULL)
    root = base.loader.loadModel(Filename.fromOsSpecific(tb), noCache=True)
    char = root.find('**/+Character')
    info = {'parts': {}, 'verts': 0}
    before = after = 0
    new_nodes = []
    for part_np in char.getChildren():
        if isinstance(part_np.node(), AnimBundleNode):
            continue
        pname = part_np.getName()
        part = pname.split('_')[-1]
        if part == 'Pants':
            part = 'Legs'
        if part in DROP_PARTS:
            continue
        for gnp in part_np.findAllMatches('**/+GeomNode'):
            gn = gnp.node()
            for i in range(gn.getNumGeoms()):
                st = gn.getGeomState(i)
                mat = st.getAttrib(MaterialAttrib).getMaterial()
                c = mat.getBaseColor() if mat.hasBaseColor() else mat.getDiffuse()
                col = (srgb(c[0]), srgb(c[1]), srgb(c[2]))
                node_name = '%s|%s' % (part, mat.getName())
                g, n0, n1 = weld_geom(gn.getGeom(i), node_name)
                before += n0
                after += n1
                ngn = GeomNode(node_name)
                ngn.addGeom(g)
                nnp = NodePath(ngn)
                nnp.setColor(col[0], col[1], col[2], 1.0)
                new_nodes.append(nnp)
                info['parts'][node_name] = [round(v, 3) for v in col]
    for part_np in char.getChildren():
        if not isinstance(part_np.node(), AnimBundleNode):
            part_np.removeNode()
    for nnp in new_nodes:
        nnp.reparentTo(char)
    info['verts'] = after
    os.makedirs(os.path.join(OUT, 'chars'), exist_ok=True)
    out = os.path.join(OUT, 'chars', name + '.bam')
    root.setName(name)
    root.writeBamFile(Filename.fromOsSpecific(out))
    print('  %-10s %-20s вершин %5d -> %5d, наборов весов %4d, %3d КБ' % (
        name, folder + '/' + fname, before, after, weld_geom.blends, os.path.getsize(out) // 1024))
    weld_geom.blends = 0
    return info


def convert_anims(sex, folder, fname, tmp):
    from panda3d.core import NodePath, Filename, AnimBundleNode, ModelRoot
    base = _panda()
    src = os.path.join(chars_dir(), folder, fname + '.gltf')
    tb = os.path.join(tmp, 'anims_%s.bam' % sex)
    subprocess.check_call([os.path.join(os.path.dirname(sys.executable), 'gltf2bam'), src, tb],
                          stdout=subprocess.DEVNULL)
    root = base.loader.loadModel(Filename.fromOsSpecific(tb), noCache=True)
    os.makedirs(os.path.join(OUT, 'anims'), exist_ok=True)
    res = {}
    total = 0
    for anp in root.findAllMatches('**/+AnimBundleNode'):
        b = anp.node().getBundle()
        if b.getName() not in ANIMS:
            continue
        holder = NodePath(ModelRoot(b.getName()))
        anp.copyTo(holder)
        out = os.path.join(OUT, 'anims', '%s_%s.bam' % (sex, b.getName()))
        holder.writeBamFile(Filename.fromOsSpecific(out))
        total += os.path.getsize(out)
        res[b.getName()] = dict(frames=b.getNumFrames(), fps=round(b.getBaseFrameRate(), 2))
    missing = [a for a in ANIMS if a not in res]
    print('  анимации %s: %d клипов, %d КБ%s' % (sex, len(res), total // 1024,
                                                  (', нет: %s' % missing) if missing else ''))
    return res


def hand_frame(sex, folder, fname, tmp):
    """Как держать оружие.  У «костюма» из набора в руке уже есть пистолет.  Ставим персонажа в позу
    прицеливания (ствол в ней смотрит строго вперёд) и запоминаем в системе кости запястья точку хвата,
    направление ствола и «верх».  Так же игра вкладывает в руку любое своё оружие."""
    import numpy as np
    from panda3d.core import Filename, GeomVertexReader, LPoint3, LVector3, Thread
    from direct.actor.Actor import Actor
    base = _panda()
    src = os.path.join(chars_dir(), folder, fname + '.gltf')
    tb = os.path.join(tmp, 'hand_%s.bam' % sex)
    subprocess.check_call([os.path.join(os.path.dirname(sys.executable), 'gltf2bam'), src, tb],
                          stdout=subprocess.DEVNULL)
    a = Actor(Filename.fromOsSpecific(tb))
    a.reparentTo(base.render)
    joint = 'Wrist.R'
    hand = a.exposeJoint(None, 'modelRoot', joint)
    a.pose('Idle_Gun_Pointing', 0)
    a.update()
    pts = []
    th = Thread.getCurrentThread()
    for pnp in a.findAllMatches('**/*Pistol*'):
        for gnp in pnp.findAllMatches('**/+GeomNode'):
            gn = gnp.node()
            for i in range(gn.getNumGeoms()):
                vd = gn.getGeom(i).getVertexData().animateVertices(True, th)
                rv = GeomVertexReader(vd, 'vertex')
                for k in range(vd.getNumRows()):
                    q = rv.getData3()
                    pts.append((q[0], q[1], q[2]))
    P = np.array(pts)
    mn, mx = P.min(0), P.max(0)
    # модель смотрит в -Y: дуло — у минимального y, казённая часть — у максимального
    length, height = mx[1] - mn[1], mx[2] - mn[2]
    org = LPoint3(float((mn[0] + mx[0]) * 0.5), float(mx[1] - HAND_GRIP[0] * length),
                  float(mn[2] + HAND_GRIP[1] * height))
    o = hand.getRelativePoint(a, org)
    b = hand.getRelativeVector(a, LVector3(0, -1, 0))
    u = hand.getRelativeVector(a, LVector3(0, 0, 1))
    r = hand.getRelativeVector(a, LVector3(-1, 0, 0))
    a.cleanup()
    a.removeNode()
    print('  хват %s: кость %s, пистолет набора %.2f x %.2f м' % (sex, joint, length, height))
    rnd = lambda v: [round(float(c), 4) for c in v]
    return dict(joint=joint, origin=rnd(o), right=rnd(r), barrel=rnd(b), up=rnd(u))


def do_chars(meta):
    tmp = tempfile.mkdtemp(prefix='dd_models_')
    try:
        meta['chars'] = {}
        for name, (folder, fname) in sorted(CHARS.items()):
            meta['chars'][name] = convert_character(name, folder, fname, tmp)
        meta['anims'] = {'m': convert_anims('m', 'men', 'Casual_2', tmp),
                         'f': convert_anims('f', 'women', 'Casual', tmp)}
        # у женских моделей пистолет не привязан к кости, а скелеты одинаковы — хват общий
        hf = hand_frame('m', 'men', 'Suit', tmp)
        meta['hand'] = {'m': hf, 'f': hf}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# статичные модели из USD: машины и оружие
# ---------------------------------------------------------------------------
GLASS = (0.13, 0.19, 0.26)
TYRE = (0.07, 0.07, 0.08)

# имя в игре -> (файл USD, параметры)
#   paint  — материалы кузова, которые игра перекрашивает ('auto' — самый распространённый цвет палитры)
#   trim   — материалы второго цвета (полосы скорой, борт фургона)
#   colors — замена цветов по имени материала (в части пакетов цвета при конвертации потерялись)
#   siren  — материалы проблесковых маячков
VEHICLES = {
    'sedan': ('Cars/S_NormalCar1', dict(paint=['Blue'])),
    'hatch': ('Cars/S_NormalCar2', dict(paint=['LightBlue'], colors={'Material_007': (0.80, 0.80, 0.82)})),
    'coupe': ('Cars/S_SportsCar', dict(paint=['Orange', 'DarkOrange'])),
    'sport4': ('Cars/S_SportsCar2', dict(paint=['White'])),
    'suv': ('Cars/S_SUV', dict(paint=['White'])),
    'taxi': ('Cars/S_Taxi', dict(paint=['Yellow'])),
    'police': ('Cars/S_Cop', dict(paint=['White'], siren=['BlueLights', 'WhiteLights'],
                                  colors={'WhiteLights': (0.85, 0.10, 0.08), 'Black': (0.07, 0.08, 0.10)})),
    'box': ('PublicTransport/S_Ambulance', dict(
        paint=['White'], trim=['Red'], siren=['Lights'], siren_at=(0.66, 1.0),
        colors={'Windows': GLASS, 'Grey': (0.42, 0.43, 0.46), 'Lights': (0.92, 0.80, 0.42),
                'Bumper': (0.17, 0.17, 0.19), 'Material': TYRE})),
    'bus': ('PublicTransport/S_Bus', dict(
        paint=['Top'], trim=['Bottom'],
        colors={'Windows': GLASS, 'Details': (0.70, 0.70, 0.73), 'Lights': (0.95, 0.85, 0.50),
                'Bumper': (0.17, 0.17, 0.19), 'Material': TYRE})),
    'pickup': ('ZombieApocalypseKit/S_VehiclePickup', dict(paint='auto')),
    'muscle': ('ZombieApocalypseKit/S_VehicleSports', dict(paint='auto')),
    'truck': ('ZombieApocalypseKit/S_VehicleTruck', dict(paint='auto')),
}


def read_usd(path):
    """-> (меши, материалы).  Меш: dict(name, parent, points Nx3, faces, fv_start, fmat, uvs)."""
    import numpy as np
    from pxr import Usd, UsdGeom, UsdShade
    st = Usd.Stage.Open(path)
    mats = {}
    for prim in st.Traverse():
        if prim.GetTypeName() == 'Material':
            mat = UsdShade.Material(prim)
            sh = mat.ComputeSurfaceSource()[0]
            dc = None
            tex = None
            if sh:
                inp = sh.GetInput('diffuseColor')
                if inp:
                    if inp.HasConnectedSource():
                        src = inp.GetConnectedSource()[0]
                        f = UsdShade.Shader(src.GetPrim()).GetInput('file')
                        if f and f.Get() is not None:
                            tex = f.Get().resolvedPath or f.Get().path
                    else:
                        dc = inp.Get()
            mats[prim.GetName()] = dict(color=tuple(dc) if dc is not None else None, tex=tex)
    out = []
    for prim in st.Traverse():
        if prim.GetTypeName() != 'Mesh':
            continue
        m = UsdGeom.Mesh(prim)
        pts = np.array(m.GetPointsAttr().Get(), dtype=np.float64)
        M = np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
        pts = (np.c_[pts, np.ones(len(pts))] @ M)[:, :3]
        cnt = list(m.GetFaceVertexCountsAttr().Get())
        idx = list(m.GetFaceVertexIndicesAttr().Get())
        faces, fv_start, k = [], [], 0
        for c in cnt:
            faces.append(idx[k:k + c])
            fv_start.append(k)
            k += c
        bind = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
        fmat = [bind.GetPath().name if bind else None] * len(faces)
        for sub in UsdGeom.Subset.GetAllGeomSubsets(m):
            b = UsdShade.MaterialBindingAPI(sub.GetPrim()).ComputeBoundMaterial()[0]
            nm = b.GetPath().name if b else sub.GetPrim().GetName()
            for fi in sub.GetIndicesAttr().Get():
                fmat[fi] = nm
        uvs = None
        pv = UsdGeom.PrimvarsAPI(prim).GetPrimvar('st')
        if pv and pv.HasValue():
            vals = pv.ComputeFlattened()
            if vals is not None:
                vals = np.array(vals, dtype=np.float64)
                if pv.GetInterpolation() == 'faceVarying' and len(vals) == len(idx):
                    uvs = vals
                elif len(vals) == len(pts):
                    uvs = vals[np.array(idx)]
        # USD: Y вверх, правая система.  Игра: Z вверх.  (x, y, z) -> (-x, z, y) — это поворот, не отражение.
        q = np.empty_like(pts)
        q[:, 0], q[:, 1], q[:, 2] = -pts[:, 0], pts[:, 2], pts[:, 1]
        out.append(dict(name=prim.GetName(), parent=prim.GetParent().GetName(), points=q, faces=faces,
                        fv_start=fv_start, fmat=fmat, uvs=uvs))
    return out, mats


def face_colors(mesh, mats, overrides=None):
    """Цвет каждой грани (sRGB): из материала либо из текстуры-палитры по центру UV грани."""
    from PIL import Image
    cache = face_colors.cache
    cols = []
    for fi, f in enumerate(mesh['faces']):
        name = mesh['fmat'][fi]
        mat = mats.get(name) or {}
        if overrides and name in overrides:
            c = overrides[name]
        elif mat.get('tex') and mesh['uvs'] is not None:
            tp = mat['tex']
            im = cache.get(tp)
            if im is None:
                im = cache[tp] = Image.open(tp).convert('RGB')
            k = mesh['fv_start'][fi]
            uv = mesh['uvs'][k:k + len(f)].mean(0)
            x = min(im.width - 1, max(0, int((uv[0] % 1.0) * im.width)))
            y = min(im.height - 1, max(0, int((1.0 - (uv[1] % 1.0)) * im.height)))
            px = im.getpixel((x, y))
            c = (px[0] / 255.0, px[1] / 255.0, px[2] / 255.0)
        elif mat.get('color') is not None:
            c = tuple(srgb(v) for v in mat['color'][:3])
        else:
            c = (0.8, 0.0, 0.8)
        cols.append((round(c[0], 3), round(c[1], 3), round(c[2], 3)))
    return cols


face_colors.cache = {}


def triangulate(pts):
    """Триангуляция плоского (возможно, невыпуклого) многоугольника отрезанием «ушей»."""
    import numpy as np
    n = len(pts)
    if n < 3:
        return []
    if n == 3:
        return [(0, 1, 2)]
    P = np.asarray(pts, dtype=np.float64)
    nrm = np.zeros(3)
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        nrm += ((a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1]))
    ln = np.linalg.norm(nrm)
    if ln < 1e-12:
        return [(0, i, i + 1) for i in range(1, n - 1)]
    nrm /= ln
    ax = int(np.argmax(np.abs(nrm)))
    u, v = [(1, 2), (2, 0), (0, 1)][ax]
    Q = P[:, [u, v]].copy()
    if nrm[ax] < 0:
        Q[:, 0] = -Q[:, 0]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    idx = list(range(n))
    tris = []
    while len(idx) > 3:
        m = len(idx)
        done = False
        for k in range(m):
            i0, i1, i2 = idx[(k - 1) % m], idx[k], idx[(k + 1) % m]
            a, b, c = Q[i0], Q[i1], Q[i2]
            if cross(a, b, c) <= 1e-12:
                continue
            ok = True
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                pt = Q[j]
                if cross(a, b, pt) >= -1e-12 and cross(b, c, pt) >= -1e-12 and cross(c, a, pt) >= -1e-12:
                    ok = False
                    break
            if ok:
                tris.append((i0, i1, i2))
                idx.pop(k)
                done = True
                break
        if not done:
            tris.extend((idx[0], idx[k], idx[k + 1]) for k in range(1, len(idx) - 1))
            idx = []
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


class MeshOut(object):
    """Накопитель треугольников с цветом вершин и плоскими нормалями -> GeomNode."""

    def __init__(self, name):
        self.name = name
        self.v = []
        self.n = []
        self.c = []
        self.t = []

    def face(self, pts, color):
        import numpy as np
        P = np.asarray(pts, dtype=np.float64)
        k = len(P)
        nrm = np.zeros(3)
        for i in range(k):
            a, b = P[i], P[(i + 1) % k]
            nrm += ((a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1]))
        ln = np.linalg.norm(nrm)
        if ln < 1e-12:
            return
        nrm /= ln
        base = len(self.v)
        for pt in P:
            self.v.append((float(pt[0]), float(pt[1]), float(pt[2])))
            self.n.append((float(nrm[0]), float(nrm[1]), float(nrm[2])))
            self.c.append(color)
        for (a, b, c) in triangulate(P):
            self.t.append((base + a, base + b, base + c))

    def node(self):
        from panda3d.core import (GeomVertexFormat, GeomVertexData, Geom, GeomTriangles, GeomVertexWriter,
                                  GeomNode, NodePath)
        if not self.t:
            return None
        vd = GeomVertexData(self.name, GeomVertexFormat.getV3n3c4(), Geom.UHStatic)
        vd.setNumRows(len(self.v))
        wv, wn, wc = (GeomVertexWriter(vd, 'vertex'), GeomVertexWriter(vd, 'normal'),
                      GeomVertexWriter(vd, 'color'))
        for i in range(len(self.v)):
            wv.setData3(*self.v[i])
            wn.setData3(*self.n[i])
            c = self.c[i]
            wc.setData4(c[0], c[1], c[2], 1.0)
        prim = GeomTriangles(Geom.UHStatic)
        for a, b, c in self.t:
            prim.addVertices(a, b, c)
        prim.closePrimitive()
        g = Geom(vd)
        g.addPrimitive(prim)
        gn = GeomNode(self.name)
        gn.addGeom(g)
        return NodePath(gn)


def _lum(c):
    return 0.30 * c[0] + 0.59 * c[1] + 0.11 * c[2]


def convert_vehicle(name, usd, opt):
    import numpy as np
    from panda3d.core import NodePath, ModelRoot, Filename
    _panda()
    meshes, mats = read_usd(os.path.join(usd_dir(), usd + '.usda'))
    wheels = [m for m in meshes if 'wheel' in m['parent'].lower()]
    bodies = [m for m in meshes if m not in wheels]
    # --- ориентация: длинная ось — вдоль Y, передние колёса — к +Y, колёса стоят на z = 0
    allp = np.vstack([m['points'] for m in meshes])
    ext = allp.max(0) - allp.min(0)
    if ext[0] > ext[1]:
        for m in meshes:
            p = m['points']
            m['points'] = np.c_[-p[:, 1], p[:, 0], p[:, 2]]
    front = [m for m in wheels if 'front' in m['parent'].lower()]
    back = [m for m in wheels if 'back' in m['parent'].lower() or 'rear' in m['parent'].lower()]
    fy = np.mean([m['points'][:, 1].mean() for m in front])
    by = np.mean([m['points'][:, 1].mean() for m in back])
    if fy < by:
        for m in meshes:
            p = m['points']
            m['points'] = np.c_[-p[:, 0], -p[:, 1], p[:, 2]]
    allp = np.vstack([m['points'] for m in meshes])
    bodyp = np.vstack([m['points'] for m in bodies])
    off = np.array([(bodyp[:, 0].max() + bodyp[:, 0].min()) * 0.5, (allp[:, 1].max() + allp[:, 1].min()) * 0.5,
                    np.vstack([m['points'] for m in wheels])[:, 2].min()])
    for m in meshes:
        m['points'] = m['points'] - off
    allp = np.vstack([m['points'] for m in meshes])
    dims = allp.max(0) - allp.min(0)
    # --- цвета граней и разбор по группам
    over = opt.get('colors')
    paint = opt.get('paint')
    trim = opt.get('trim') or []
    siren = opt.get('siren') or []
    groups = {'paint': MeshOut('paint'), 'trim': MeshOut('trim'), 'fixed': MeshOut('fixed'),
              'siren': MeshOut('siren')}
    lights = {'head': [], 'tail': [], 'siren': []}
    cols_by_mesh = [face_colors(m, mats, over) for m in bodies]
    primary = None
    if paint == 'auto':
        # основной цвет кузова — тот, что занимает наибольшую площадь среди не серых граней
        area = {}
        for m, cols in zip(bodies, cols_by_mesh):
            for fi, f in enumerate(m['faces']):
                P = m['points'][f]
                a = 0.0
                for i in range(1, len(f) - 1):
                    a += 0.5 * np.linalg.norm(np.cross(P[i] - P[0], P[i + 1] - P[0]))
                c = cols[fi]
                if max(c) - min(c) > 0.12:
                    area[c] = area.get(c, 0.0) + a
        primary = max(area.items(), key=lambda kv: kv[1])[0]
    else:
        ref = []
        for m, cols in zip(bodies, cols_by_mesh):
            for fi in range(len(m['faces'])):
                if m['fmat'][fi] in paint:
                    ref.append(cols[fi])
        primary = max(ref, key=_lum)

    def is_paint(mat, c):
        if paint == 'auto':
            if max(c) - min(c) <= 0.12:
                return False
            # тот же оттенок, что у основного цвета (разница только в яркости)
            k = _lum(c) / max(1e-6, _lum(primary))
            return all(abs(c[i] - primary[i] * k) < 0.09 for i in range(3)) and 0.45 < k < 1.6
        return mat in paint
    shades = []
    for m, cols in zip(bodies, cols_by_mesh):
        for fi, f in enumerate(m['faces']):
            mat = m['fmat'][fi]
            c = cols[fi]
            P = m['points'][f]
            lname = (mat or '').lower()
            if is_paint(mat, c):
                shades.append(_lum(c))
    top = max(shades) if shades else 1.0
    for m, cols in zip(bodies, cols_by_mesh):
        for fi, f in enumerate(m['faces']):
            mat = m['fmat'][fi]
            c = cols[fi]
            P = m['points'][f]
            lname = (mat or '').lower()
            cen = P.mean(0)
            if is_paint(mat, c):
                k = min(1.0, _lum(c) / top)
                groups['paint'].face(P, (k, k, k))
                continue
            if mat in trim:
                groups['trim'].face(P, (1.0, 1.0, 1.0))
                continue
            if mat in siren:
                # маячки — только то, что на крыше (на «скорой» этим же материалом сделаны фары);
                # они лежат в отдельном узле, чтобы у обычного фургона их можно было убрать
                if cen[2] > dims[2] * 0.8:
                    lights['siren'].append(cen)
                    groups['siren'].face(P, c)
                    continue
                elif cen[1] > 0:
                    lights['head'].append(cen)
                else:
                    lights['tail'].append(cen)
                    c = (0.75, 0.10, 0.08)
            elif lname == 'lights':
                # общий материал «огни»: спереди фары, сзади стоп-сигналы
                if cen[1] > 0:
                    lights['head'].append(cen)
                    c = (0.98, 0.93, 0.72)
                else:
                    lights['tail'].append(cen)
                    c = (0.75, 0.10, 0.08)
            elif 'headlight' in lname:
                lights['head'].append(cen)
                c = (0.98, 0.93, 0.72)
            elif 'taillight' in lname or 'brakelight' in lname:
                lights['tail'].append(cen)
                c = (0.75, 0.10, 0.08)
            elif lname in ('windows', 'window', 'glass'):
                c = GLASS
            groups['fixed'].face(P, c)
    root = NodePath(ModelRoot(name))
    body = root.attachNewNode('body')
    for key in ('paint', 'trim', 'fixed', 'siren'):
        nd = groups[key].node()
        if nd is not None:
            nd.reparentTo(body)
    # --- колёса: шаблон — правое переднее (внешняя сторона смотрит в +X), с центром в начале координат
    winfo = []
    tmpl = None
    for m in wheels:
        p = m['points']
        cols = face_colors(m, mats, over)
        for side in (-1, 1):
            sel = [fi for fi, f in enumerate(m['faces']) if (p[f][:, 0].mean() > 0) == (side > 0)]
            if not sel:
                continue
            vid = sorted(set(i for fi in sel for i in m['faces'][fi]))
            q = p[vid]
            c0 = (q.max(0) + q.min(0)) * 0.5
            r = (q[:, 2].max() - q[:, 2].min()) * 0.5
            wd = q[:, 0].max() - q[:, 0].min()
            winfo.append(dict(x=round(float(c0[0]), 3), y=round(float(c0[1]), 3), z=round(float(c0[2]), 3),
                              r=round(float(r), 3), w=round(float(wd), 3)))
            if tmpl is None and side > 0 and m in front:
                mo = MeshOut('wheel')
                for fi in sel:
                    c = cols[fi]
                    if _lum(c) < 0.12:
                        c = TYRE
                    mo.face(p[m['faces'][fi]] - c0, c)
                tmpl = mo.node()
    if tmpl is not None:
        tmpl.reparentTo(root)

    def cluster(pts, front):
        """Грани фар -> по одной точке слева и справа (симметрично), только у самого носа или кормы."""
        if not pts:
            return []
        half = dims[1] * 0.5
        sel = [q for q in pts if (q[1] > half * 0.6 if front else q[1] < -half * 0.6) and abs(q[0]) > 0.15]
        if not sel:
            sel = [q for q in pts if (q[1] > 0) == front]
        if not sel:
            return []
        x = float(np.mean([abs(q[0]) for q in sel]))
        y = float(np.mean([q[1] for q in sel]))
        z = float(np.mean([q[2] for q in sel]))
        return [[round(-x, 3), round(y, 3), round(z, 3)], [round(x, 3), round(y, 3), round(z, 3)]]
    info = dict(L=round(float(dims[1]), 3), W=round(float(dims[0]), 3), H=round(float(dims[2]), 3),
                wheels=sorted(winfo, key=lambda d: (-d['y'], d['x'])), head=cluster(lights['head'], True),
                tail=cluster(lights['tail'], False),
                siren=([[0.0] + [round(float(v), 3) for v in np.mean(lights['siren'], axis=0)[1:]]]
                       if lights['siren'] else
                       ([[0.0, round(float(dims[1] * 0.5 * opt['siren_at'][0]), 3),
                          round(float(dims[2] * opt['siren_at'][1]), 3)]] if opt.get('siren_at') else [])),
                primary=[round(v, 3) for v in primary], has_trim=groups['trim'].node() is not None)
    os.makedirs(os.path.join(OUT, 'veh'), exist_ok=True)
    out = os.path.join(OUT, 'veh', name + '.bam')
    root.writeBamFile(Filename.fromOsSpecific(out))
    tris = sum(len(g.t) for g in groups.values())
    print('  %-8s %-40s %.2f x %.2f x %.2f м, %5d треуг., колёс %d, фар %d/%d, %3d КБ' % (
        name, usd, info['L'], info['W'], info['H'], tris, len(winfo), len(info['head']), len(info['tail']),
        os.path.getsize(out) // 1024))
    return info


def do_vehicles(meta):
    meta['vehicles'] = {}
    for name, (usd, opt) in sorted(VEHICLES.items()):
        meta['vehicles'][name] = convert_vehicle(name, usd, opt)


# оружие: имя -> (файл USD, длина в метрах, развернуть ствол, перевернуть, где хват: доля длины от казённой
# части и смещение вниз в долях высоты)
WEAPONS = {
    'bat': ('ZombieApocalypseKit/S_WoodenBatBarbed', 0.86, False, False, 0.10, 0.0),
    'pistol': ('UltimateGun/S_Pistol_1', 0.24, True, False, 0.22, 0.30),
    'uzi': ('UltimateGun/S_SubmachineGun_1', 0.42, True, False, 0.28, 0.30),
    'shotgun': ('UltimateGun/S_Shotgun_1', 0.98, True, False, 0.30, 0.15),
    'ak': ('ToonShooterGameKit/S_AK', 0.90, False, False, 0.32, 0.22),
    'rocket': ('ToonShooterGameKit/S_RocketLauncher', 1.05, False, False, 0.40, 0.25),
    'grenade': ('ToonShooterGameKit/S_Grenade', 0.13, False, False, 0.5, 0.0),
    'molotov': ('ToonShooterGameKit/S_FireGrenade', 0.20, False, False, 0.5, 0.0),
}


def convert_weapon(name, usd, length, flip_y, flip_z, grip_y, grip_z):
    import numpy as np
    from panda3d.core import NodePath, ModelRoot, Filename
    _panda()
    meshes, mats = read_usd(os.path.join(usd_dir(), usd + '.usda'))
    allp = np.vstack([m['points'] for m in meshes])
    ext = allp.max(0) - allp.min(0)
    order = np.argsort(ext)                 # [самая тонкая ось, средняя, самая длинная]
    ax_x, ax_z, ax_y = int(order[0]), int(order[1]), int(order[2])
    R = np.zeros((3, 3))
    R[0, ax_x] = 1.0
    R[1, ax_y] = 1.0
    R[2, ax_z] = 1.0
    if np.linalg.det(R) < 0:
        R[0, ax_x] = -1.0
    if flip_y:
        R[1] *= -1.0
        R[0] *= -1.0
    if flip_z:
        R[2] *= -1.0
        R[0] *= -1.0
    k = length / float(ext[ax_y])
    mo = MeshOut(name)
    pts_all = []
    for m in meshes:
        m['points'] = (m['points'] @ R.T) * k
        pts_all.append(m['points'])
    allp = np.vstack(pts_all)
    mn, mx = allp.min(0), allp.max(0)
    org = np.array([(mn[0] + mx[0]) * 0.5, mn[1] + (mx[1] - mn[1]) * grip_y, (mn[2] + mx[2]) * 0.5 -
                    (mx[2] - mn[2]) * grip_z])
    for m in meshes:
        cols = face_colors(m, mats)
        for fi, f in enumerate(m['faces']):
            mo.face(m['points'][f] - org, cols[fi])
    root = NodePath(ModelRoot(name))
    mo.node().reparentTo(root)
    os.makedirs(os.path.join(OUT, 'weapons'), exist_ok=True)
    out = os.path.join(OUT, 'weapons', name + '.bam')
    root.writeBamFile(Filename.fromOsSpecific(out))
    mn, mx = mn - org, mx - org
    print('  %-8s %-42s %4d треуг., %.2f x %.2f x %.2f м, дуло y=%.2f, %3d КБ' % (
        name, usd, len(mo.t), mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2], mx[1], os.path.getsize(out) // 1024))
    return dict(muzzle=[0.0, round(float(mx[1]), 3), round(float((mn[2] + mx[2]) * 0.5 + (mx[2] - mn[2]) * 0.15), 3)],
                length=round(float(mx[1] - mn[1]), 3))


def do_weapons(meta):
    meta['weapons'] = {}
    for name, cfg in sorted(WEAPONS.items()):
        meta['weapons'][name] = convert_weapon(name, *cfg)


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
    if cmd in ('all', 'vehicles'):
        do_vehicles(meta)
    if cmd in ('all', 'weapons'):
        do_weapons(meta)
    with open(mpath, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1, sort_keys=True, ensure_ascii=False)
    print('готово:', os.path.relpath(mpath, ROOT))


if __name__ == '__main__':
    main()
