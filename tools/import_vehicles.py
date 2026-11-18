# -*- coding: utf-8 -*-
"""Импорт готовых моделей транспорта, которых нет в основном наборе машин: такси и ещё четыре автомобиля
в стиле PS1 с itch.io (среди них машина героя с салоном), чоппер и детали тюнинга.

Нужен только тому, кто пересобирает модели: игра читает готовые файлы из assets/models/veh.

    pip install panda3d numpy pillow scipy potracer     # potracer (GPL) — только для текстуры «Катаны»
    python tools/import_vehicles.py fetch         # скачать исходники в .cache/model_src/new
    python tools/import_vehicles.py all           # машины, чоппер, детали
    python tools/import_vehicles.py cars cab      # только одна машина (так же: bikes chop)

Откуда что берётся (лицензии и авторы — в assets/models/CREDITS.md):
  * такси — Yellow Taxi/Cab, PS1 Car (MoiDev); копия со Sketchfab из репозитория Langorithm/3d-models;
  * седан «Тень» — Suspicious Car, PSX Style Car (MoiDev, CC0); копия из muricristino/walking-simulator-paulista;
  * хэтчбек «Зажигалка» — PS1 / Pixel Art style car (designersoup); копия из Soursop-Pop/Roadtrip;
  * купе «Катана» — PSX Car, 2 Seater Coupe (boggle); копия из KopiOCoder/FormulaCyber;
  * машина героя «Ласточка» — Retro Car With Interior (Bricchi Games, CC BY 4.0: автора нужно называть);
    копия из Alekssandher/The-Gandmas-House;
  * чоппер — Another PSX Style Low-poly Bike (Duhgless, CC0); копия с текстурами 256 точек из
    репозитория webbertakken/citymap;
  * спойлеры, бампер — Kenney, Car Kit (CC0);
  * бутылка — Quaternius (CC0), репозиторий chibifire-stages/quaternius-stage.

Модели с itch.io сюда попадают через их копии на GitHub: с самого itch.io файлы скриптом не скачать.
Какой репозиторий и какая его версия — в таблице SOURCES.

Что делает импорт:
  * всё приводится к осям игры (Z вверх, нос — к +Y, колёса стоят на земле, середина — в начале координат)
    и к настоящим размерам в метрах;
  * колёса отделяются от кузова, у двухколёсных отдельно идёт вилка с рулём;
  * краска отделяется от остального (стёкла, хром, фары, шины), чтобы игра могла перекрашивать кузов:
    краска — то, что меняется от окраски к окраске набора, а если окраска одна — то, что подходит по цвету;
  * у машины с салоном стёкла и рулевое колесо идут отдельными узлами (стёкла игра делает прозрачными, руль
    поворачивает), а в описание модели записываются места сидящих;
  * у чоппера отдельно идёт вилка с рулём, а с модели снимаются точки посадки: где седло, где ручки руля,
    где подножки; недостающие подножки достраиваются.
"""
import colorsys
import json
import math
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mesh_src as ms                                                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, '.cache', 'model_src', 'new')
OUT = os.path.join(ROOT, 'assets', 'models')
VEH = os.path.join(OUT, 'veh')

# исходники: (репозиторий, ревизия, [(путь в репозитории, куда положить в .cache/model_src/new)])
SOURCES = [
    ('0xKoller/starter-kit-racing-studio', None, [
        ('kenney_car-kit/License.txt', 'kenney_carkit/License.txt'),
        ('kenney_car-kit/Models/OBJ format/Textures/colormap.png', 'kenney_carkit/Textures/colormap.png'),
    ] + [('kenney_car-kit/Models/OBJ format/%s.%s' % (n, e), 'kenney_carkit/%s.%s' % (n, e))
         for n in ('debris-spoiler-a', 'debris-spoiler-b', 'debris-bumper') for e in ('obj', 'mtl')]),
    ('chibifire-stages/quaternius-stage', None, [
        ('models/Survival/S_WaterBottle_1.usda', 'quat/S_WaterBottle_1.usda'),
    ]),
    # MoiDev, Yellow Taxi/Cab — PS1 Car (https://moidev.itch.io/yellow-taxicab-ps1-style): выгрузка со Sketchfab
    ('Langorithm/3d-models', 'e24d7f517d6fa275053a34ab5b3c5164d8ef6952', [
        ('yellow_taxicab_-_ps1_car/scene.gltf', 'moidev_taxi/scene.gltf'),
        ('yellow_taxicab_-_ps1_car/scene.bin', 'moidev_taxi/scene.bin'),
        ('yellow_taxicab_-_ps1_car/textures/Taxi_baseColor.png', 'moidev_taxi/textures/Taxi_baseColor.png'),
        ('yellow_taxicab_-_ps1_car/license.txt', 'moidev_taxi/license.txt'),
    ]),
    # Duhgless, Another PSX Style Low-poly Bike (https://duhgless.itch.io/another-psx-style-low-poly-bike):
    # тот же Bike3.glb, но с текстурами 256 точек (WebP) и названными деталями
    ('webbertakken/citymap', '575fefa7fa4643dd4adcc60ab87f09e1fff5eecf', [
        ('apps/web/public/models/vehicles/motorbike.glb', 'duhgless/motorbike.glb'),
        ('apps/web/public/models/CREDITS.md', 'duhgless/CREDITS.md'),
        ('LICENSE', 'duhgless/LICENSE'),
    ]),
    # Daniel Jurys, PSX Waste (https://daniel-jurys.itch.io/psx-waste, CC0): уличный мусор — tools/import_extra.py
    ('morganholly/bike-bullet-delivery', '70f9927c760d6880ed9ba2957da3fbb428e5c22e', [
        ('enviroment/PSX-Waste/PSX-Waste/glb/%s.glb' % n, 'psx_waste/%s.glb' % n)
        for n in ('dumpster', 'barrel', 'trash-bag', 'cardboard-box', 'glass-bottle', 'crumpled-can')]),
    # boggle, PSX Car — 2 Seater Coupe (https://boggle.itch.io/2-seater-coupe): кузов, колесо и десять окрасок
    ('KopiOCoder/FormulaCyber', '7b1febc5d758141ffd9d7fbc0c6569cd690e806d', [
        ('cars/japanese_2_seater_coupe/%s' % n, 'boggle_coupe/%s' % n)
        for n in ('2_seater_coupe.glb', 'wheel.glb', '2_seater_coupe.obj', '2_seater_coupe.mtl', 'wheel.obj',
                  'wheel.mtl')
    ] + [('cars/japanese_2_seater_coupe/textures/%s.png' % n, 'boggle_coupe/textures/%s.png' % n)
         for n in ('bright_yellow', 'crystal_white', 'laser_blue', 'marina_blue', 'merlot_red', 'noble_green',
                   'shade_green', 'silver_tornado_silver', 'sunlight_yellow', 'sunrise_red')]),
    # MoiDev, Suspicious Car — PSX Style Car (https://moidev.itch.io/a-suspicious-car-for-your-projects, CC0):
    # Suspicious Car.obj (в копии назван sedan.obj) и шесть окрасок
    ('muricristino/walking-simulator-paulista', 'f9cd9794f917f9cc17d63c275cf6c6cbe3aeba31', [
        ('CREDITS.md', 'moidev_sus/CREDITS.md'),
    ] + [('assets/cars/moidev/%s' % n, 'moidev_sus/%s' % n)
         for n in ('sedan.obj', 'sedan.mtl', 'sedan_black.png', 'sedan_blue.png', 'sedan_brown.png',
                   'sedan_persian_blue.png', 'sedan_red.png', 'sedan_white.png')]),
    # designersoup, PS1 / Pixel Art style car (https://designersoup.itch.io/ps1-pixel-art-style-car):
    # golfps1.fbx, сохранённый владельцем копии в OBJ, и его текстура
    ('Soursop-Pop/Roadtrip', '3894f678acc9c03ccf6c3b20fe0e28ca5a6d9e29', [
        ('Assets/Prefabs/car/red_golf.obj', 'designersoup_golf/red_golf.obj'),
        ('Assets/Prefabs/car/red_golf.mtl', 'designersoup_golf/red_golf.mtl'),
        ('Assets/Prefabs/car/pixel art golf final.png', 'designersoup_golf/pixel art golf final.png'),
    ]),
    # Bricchi Games, Retro Car With Interior (https://bricchi-games.itch.io/retro-car-with-interior, CC BY):
    # набор Retro Car-1.0 целиком
    ('Alekssandher/The-Gandmas-House', 'a76e2897d2f449255c8459fc6349004ac64dce8f', [
        ('assets/Retro Car-1.0/Car.fbx', 'bricchi_car/Car.fbx'),
        ('assets/Retro Car-1.0/Car Asset.blend', 'bricchi_car/Car Asset.blend'),
        ('assets/Retro Car-1.0/Emissive Texture.png', 'bricchi_car/Emissive Texture.png'),
        ('assets/Retro Car-1.0/Black Car Texture.png', 'bricchi_car/Black Car Texture.png'),
        ('assets/Retro Car-1.0/Blue Texture/Blue Car Texture.png', 'bricchi_car/Blue Car Texture.png'),
        ('assets/Retro Car-1.0/Red Texture/Red Car Texture.png', 'bricchi_car/Red Car Texture.png'),
        ('assets/Retro Car-1.0/White Texture/White Car Texture.png', 'bricchi_car/White Car Texture.png'),
    ]),
]


def fetch():
    """Скачать исходники (через gh api: нужен установленный и вошедший в GitHub клиент gh)."""
    import urllib.parse
    for repo, ref, files in SOURCES:
        for path, dst in files:
            out = os.path.join(SRC, dst)
            if os.path.isfile(out) and os.path.getsize(out) > 0:
                continue
            os.makedirs(os.path.dirname(out), exist_ok=True)
            url = 'repos/%s/contents/%s' % (repo, urllib.parse.quote(path))
            if ref:
                url += '?ref=' + ref
            with open(out, 'wb') as f:
                subprocess.check_call(['gh', 'api', '-H', 'Accept: application/vnd.github.raw', url], stdout=f)
            print('  %-60s %7d' % (dst, os.path.getsize(out)))


def src(*p):
    return os.path.join(SRC, *p)


# ---------------------------------------------------------------------------
# общее
# ---------------------------------------------------------------------------
def _panda():
    from panda3d.core import loadPrcFileData
    loadPrcFileData('', 'window-type none\naudio-library-name null\nmodel-cache-dir\n')
    from direct.showbase.ShowBase import ShowBase
    import builtins
    if not hasattr(builtins, 'base'):
        ShowBase()
    return builtins.base


def named(parts):
    """Детали по именам; одноимённые (так пишет OBJ с группами) склеиваются."""
    out = {}
    for p in parts:
        out.setdefault(p.name, []).append(p)
    return dict((k, v[0] if len(v) == 1 else ms.merge(v, k)) for k, v in out.items())


def components(p, tol=1e-4):
    """Связные куски детали: списки номеров треугольников (вершины склеиваются по положению)."""
    key = {}
    vid = np.array([key.setdefault(tuple(np.round(v / tol).astype(np.int64)), len(key)) for v in p.verts])
    parent = list(range(len(key)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for t in p.tris:
        a, b, c = find(vid[t[0]]), find(vid[t[1]]), find(vid[t[2]])
        parent[b] = a
        parent[c] = a
    groups = {}
    for i, t in enumerate(p.tris):
        groups.setdefault(find(vid[t[0]]), []).append(i)
    return sorted(groups.values(), key=lambda g: -len(g))


def tri_points(p, idx=None):
    t = p.tris if idx is None else p.tris[idx]
    return p.verts[np.unique(t)]


class Out(object):
    """Накопитель треугольников: вершина, нормаль грани, цвет, текстурные координаты -> GeomNode."""

    def __init__(self):
        self.rows = []

    def tri(self, pts, uv=None, color=(1.0, 1.0, 1.0)):
        a, b, c = [np.asarray(q, dtype=np.float64) for q in pts]
        n = np.cross(b - a, c - a)
        ln = np.linalg.norm(n)
        if ln < 1e-12:
            return
        n /= ln
        for k, q in enumerate((a, b, c)):
            if uv is None:
                t = box_uv(q, n)
            else:
                t = uv[k]
            self.rows.append((q, n, color, t))

    def part(self, p, idx=None, color=None, colors=None, uv=True, xf=None):
        """Добавить треугольники детали.  color — один цвет на все; colors — по цвету на треугольник;
        uv=False — развёртку не брать (ляжет общая «зернистая» текстура); xf — функция точки."""
        ids = range(len(p.tris)) if idx is None else idx
        for i in ids:
            pts = p.verts[p.tris[i]]
            if xf is not None:
                pts = [xf(q) for q in pts]
            col = color if colors is None else colors[i]
            self.tri(pts, p.uvs[i] if (uv and p.uvs is not None) else None, col or (1.0, 1.0, 1.0))

    def box(self, x0, y0, z0, x1, y1, z1, color):
        c = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        for (a, b, cc, d) in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (3, 0, 4, 7)):
            self.tri((c[a], c[b], c[cc]), color=color)
            self.tri((c[a], c[cc], c[d]), color=color)

    def tube(self, a, b, r, color, n=5):
        """Трубка между точками a и b."""
        a = np.asarray(a, dtype=np.float64)
        b = np.asarray(b, dtype=np.float64)
        d = b - a
        ln = np.linalg.norm(d)
        if ln < 1e-9:
            return
        d /= ln
        u = np.cross(d, (0.0, 0.0, 1.0) if abs(d[2]) < 0.9 else (1.0, 0.0, 0.0))
        u /= np.linalg.norm(u)
        v = np.cross(d, u)
        ring = [u * math.cos(2 * math.pi * k / n) * r + v * math.sin(2 * math.pi * k / n) * r for k in range(n)]
        for k in range(n):
            p0, p1 = ring[k], ring[(k + 1) % n]
            self.tri((a + p0, a + p1, b + p1), color=color)
            self.tri((a + p0, b + p1, b + p0), color=color)
        for k in range(1, n - 1):
            self.tri((a + ring[0], a + ring[k + 1], a + ring[k]), color=color)
            self.tri((b + ring[0], b + ring[k], b + ring[k + 1]), color=color)

    def node(self, name):
        from panda3d.core import GeomVertexFormat, GeomVertexData, Geom, GeomTriangles, GeomVertexWriter, GeomNode
        vd = GeomVertexData(name, GeomVertexFormat.getV3n3c4t2(), Geom.UHStatic)
        vd.setNumRows(len(self.rows))
        vw, nw = GeomVertexWriter(vd, 'vertex'), GeomVertexWriter(vd, 'normal')
        cw, tw = GeomVertexWriter(vd, 'color'), GeomVertexWriter(vd, 'texcoord')
        for q, n, c, t in self.rows:
            vw.addData3(float(q[0]), float(q[1]), float(q[2]))
            nw.addData3(float(n[0]), float(n[1]), float(n[2]))
            cw.addData4(float(c[0]), float(c[1]), float(c[2]), 1.0)
            tw.addData2(float(t[0]), float(t[1]))
        tr = GeomTriangles(Geom.UHStatic)
        for k in range(0, len(self.rows), 3):
            tr.addVertices(k, k + 1, k + 2)
        g = Geom(vd)
        g.addPrimitive(tr)
        gn = GeomNode(name)
        gn.addGeom(g)
        return gn

    def __len__(self):
        return len(self.rows) // 3


GRAIN_M = 0.55              # сторона «зернистой» текстуры на модели, м


def box_uv(q, n):
    """Развёртка «коробкой» для деталей без своей текстуры: проекция вдоль главной оси нормали."""
    ax = int(np.argmax(np.abs(n)))
    if ax == 0:
        return (q[1] / GRAIN_M, q[2] / GRAIN_M)
    if ax == 1:
        return (q[0] / GRAIN_M, q[2] / GRAIN_M)
    return (q[0] / GRAIN_M, q[1] / GRAIN_M)


def grain_texture(path):
    """Общая текстура деталей без своей картинки: серая «зернистость» с потёртостями, как на текстурах
    остальной техники.  Средняя яркость — белый: цвет детали она не меняет, только оживляет плоскость."""
    from PIL import Image
    rng = np.random.RandomState(7)
    n = 64
    a = rng.normal(0.0, 1.0, (n, n))
    for _ in range(2):                                   # сгладить: зерно в 2–3 точки
        a = (a + np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 5.0
    a = a / a.std()
    img = 232.0 + a * 9.0
    for _ in range(26):                                  # потёртости: короткие тёмные и светлые штрихи
        x, y, ln = rng.randint(0, n), rng.randint(0, n), rng.randint(3, 11)
        d = rng.choice([-1.0, 1.0]) * rng.uniform(8.0, 20.0)
        for k in range(ln):
            img[(y + (k // 3 if rng.rand() < 0.5 else 0)) % n, (x + k) % n] += d
    Image.fromarray(np.clip(img, 150, 255).astype(np.uint8), 'L').save(path, optimize=True)


def hsv(img):
    """RGB (h, w, 3) 0..255 -> оттенок (градусы), насыщенность, яркость (0..1)."""
    a = img.astype(np.float64) / 255.0
    mx = a.max(2)
    mn = a.min(2)
    d = mx - mn
    s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0.0)
    h = np.zeros(mx.shape)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = d > 1e-6
    hr = (((g - b) / np.maximum(d, 1e-6)) % 6.0)
    hg = ((b - r) / np.maximum(d, 1e-6)) + 2.0
    hb = ((r - g) / np.maximum(d, 1e-6)) + 4.0
    h = np.where(mx == r, hr, np.where(mx == g, hg, hb)) * 60.0
    h = np.where(m, h % 360.0, 0.0)
    return h, s, mx


def lum(a):
    return a[..., 0] * 0.30 + a[..., 1] * 0.59 + a[..., 2] * 0.11


def dilate(mask, n):
    m = mask.copy()
    for _ in range(n):
        g = m.copy()
        g[1:, :] |= m[:-1, :]
        g[:-1, :] |= m[1:, :]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        m = g
    return m


def erode(mask, n):
    return ~dilate(~mask, n)


def uv_mask(parts, size):
    """Какие точки текстуры заняты гранями этих деталей (растеризация развёртки)."""
    from PIL import Image, ImageDraw
    im = Image.new('L', (size, size), 0)
    d = ImageDraw.Draw(im)
    for p in parts:
        if p.uvs is None:
            continue
        for uv in p.uvs:
            d.polygon([(float(u % 1.0 if not 0.0 <= u <= 1.0 else u) * size, (1.0 - float(v % 1.0 if not 0.0 <= v <= 1.0 else v)) * size)
                       for u, v in uv], fill=255, outline=255)
    return np.asarray(im) > 0


# ---------------------------------------------------------------------------
# автомобили
# ---------------------------------------------------------------------------
GLASS = (46, 56, 66)        # стекло там, где у исходника был просто серый материал
DARK_INSIDE = (30, 30, 32)

# имя -> описание
#   file     — файл модели; parts — какие его детали составляют кузов; wheels — колёса
#   wheel_file, wheel_at — колесо лежит отдельным файлом: одно на все четыре места; места — (x, y) правого
#              переднего и правого заднего в единицах исходника (после поворота носом к +Y)
#   mirror   — в файле половина кузова: вторая получается отражением
#   yup      — у исходника вверх смотрит Y (glTF, FBX, OBJ из Blender)
#   turn     — как повернуть исходник, чтобы нос смотрел на +Y: 'x+' — нос исходника смотрит на +X, …
#   width    — настоящая ширина кузова, м (по ней ставится масштаб)
#   tex      — текстура; size — её размер в игре; pixel — нарисована по точкам (размер меняется без сглаживания)
#   fixed    — текстура идёт как есть, кузов не перекрашивается
#   variants — та же текстура в других окрасках: краска — это то, что от окраски к окраске меняется
#              (сильнее, чем на spread; у купе порог низкий — тёмные тени у стёкол там тоже крашеные)
#   vector   — увеличить текстуру во столько раз, обводя края заново (tools/vector_tex.py): levels — пороги
#              яркости для слоёв некрашеного, shades — пороги светотени для слоёв краски
#   paint    — правило «что здесь краска» для единственной окраски (по цвету точек текстуры, занятых кузовом):
#                hue, sat, val — оттенок от и до (через ноль тоже: 345..12), насыщенность от и до, яркость от;
#                keep=[(x0, y0, x1, y1), …] — прямоугольники текстуры (в точках исходника), где краски нет
#   cut      — прозрачные места текстуры вырезаются (колёсные арки, нарисованные на бортах)
#   flat     — материалы без текстуры: имя -> цвет (None — грани убрать)
#   glass    — материал стёкол: они идут отдельным узлом, игра делает их прозрачными (виден салон)
#   steer    — деталь «рулевое колесо»: отдельный узел, поворачивается вместе с колёсами
#   seats    — места в салоне: (x, y, z) таза сидящего в метрах от середины машины на земле; первое — водитель
#   feet     — куда сидящий ставит ноги, для каждого места: (y, z) лодыжек и половина расстояния между ними.
#              Пол салона у «Ласточки» на высоте 0,42 м — в 13 см под тазом, место для ног только впереди
#   head/tail — высота фар и задних фонарей в долях высоты кузова, и разнос в долях полуширины
CARS = {
    # такси MoiDev: текстура как есть (жёлтый кузов с «шашечками»), не перекрашивается
    'cab': dict(
        file=('moidev_taxi', 'scene.gltf'), tex=('moidev_taxi', 'textures', 'Taxi_baseColor.png'),
        parts=('Object_4', 'Object_6'), wheels=('Object_8', 'Object_10', 'Object_12', 'Object_14'),
        yup=True, turn='y+', width=1.86, fixed=True, pixel=True, flat={},
        head=(0.47, 0.74), tail=(0.50, 0.80)),
    # «подозрительный» седан MoiDev: шесть окрасок, арки колёс вырезаны прозрачностью текстуры
    'sus': dict(
        file=('moidev_sus', 'sedan.obj'), tex=('moidev_sus', 'sedan_white.png'),
        variants=[('moidev_sus', 'sedan_%s.png' % c) for c in ('black', 'blue', 'brown', 'persian_blue', 'red')],
        parts=('Body_Cube.001',),
        wheels=('Wheel_FR_Cylinder', 'Wheels_RL_Cylinder.001', 'Wheels_FL_Cylinder.002', 'Wheels_RR_Cylinder.003'),
        yup=True, turn='y+', width=1.74, pixel=True, cut=True, flat={},
        head=(0.52, 0.74), tail=(0.56, 0.74)),
    # хэтчбек designersoup: окраска одна (красная), краска находится по оттенку; зеркала — гладкий чёрный материал
    'golf': dict(
        file=('designersoup_golf', 'red_golf.obj'), tex=('designersoup_golf', 'pixel art golf final.png'),
        parts=('baseShape',), wheels=('rRWheel', 'lFWheel.001', 'lFWheel', 'lRWheel'),
        yup=True, turn='y+', width=1.79, size=512, pixel=True,
        paint=dict(hue=(340.0, 14.0), sat=(0.45, 1.0), val=0.30,
                   keep=[(366, 60, 386, 94), (366, 140, 386, 174)]),
        flat={'Material.001': (22, 22, 24)},
        head=(0.50, 0.70), tail=(0.62, 0.78)),
    # двухместное купе boggle: в файле половина кузова, колесо — отдельным файлом; десять окрасок.
    # Текстура у него 128×128: вблизи край лобового стекла шёл ступеньками, швы — зубцами.  Поэтому она
    # увеличивается «векторно» (tools/vector_tex.py): стёкла, швы и тени обводятся заново, уже без ступенек.
    # Некрашеное берётся из цветной окраски (в белой задние фонари и поворотники — серые), белая не нужна:
    # игра красит кузов сама
    'coupe': dict(
        file=('boggle_coupe', '2_seater_coupe.glb'), tex=('boggle_coupe', 'textures', 'bright_yellow.png'),
        variants=[('boggle_coupe', 'textures', c + '.png') for c in (
            'laser_blue', 'marina_blue', 'merlot_red', 'noble_green', 'shade_green',
            'silver_tornado_silver', 'sunlight_yellow', 'sunrise_red')],
        parts=('2_seater_coupe',), mirror=True,
        wheel_file=('boggle_coupe', 'wheel.glb'), wheel_at=((0.735, 1.294), (0.735, -1.135)),
        yup=True, turn='y+', width=1.76, size=128, pixel=True, flat={},
        vector=4, levels=(85, 160), shades=(0.85, 0.45), spread=6,
        head=(0.50, 0.66), tail=(0.62, 0.62)),
    # машина героя — Bricchi Games: кузов с дверями, капотом и багажником, салон, рулевое колесо; четыре окраски
    'retro': dict(
        file=('bricchi_car', 'Car.fbx'), tex=('bricchi_car', 'White Car Texture.png'),
        variants=[('bricchi_car', c + ' Car Texture.png') for c in ('Black', 'Blue', 'Red')],
        parts=('Car_Base', 'car_hood', 'trunk', 'L_Door_Front', 'L_Door_Back', 'R_Door_Front', 'R_Door_Back',
               'Car_Base.011'),
        wheels=('L_Tire_front', 'R_Tire_Front', 'L_Tire_Back', 'R_Tire_Back'),
        steer='Steering_wheel', glass='carwindows',
        seats=((-0.43, 0.225, 0.547), (0.43, 0.147, 0.556), (-0.40, -0.473, 0.566), (0.40, -0.473, 0.566)),
        feet=((0.70, 0.50, 0.11), (0.66, 0.50, 0.11), (-0.12, 0.50, 0.10), (-0.12, 0.50, 0.10)),
        yup=True, turn='y+', width=1.71, size=512, flat={},
        head=(0.44, 0.76), tail=(0.47, 0.70)),
}
TEX_SIZE = 256


def _turn(parts, how):
    """Повернуть вокруг вертикали так, чтобы нос смотрел на +Y."""
    m = {'y+': np.eye(3), 'y-': np.array([[-1.0, 0, 0], [0, -1.0, 0], [0, 0, 1.0]]),
         'x+': np.array([[0, -1.0, 0], [1.0, 0, 0], [0, 0, 1.0]]),
         'x-': np.array([[0, 1.0, 0], [-1.0, 0, 0], [0, 0, 1.0]])}[how]
    for p in parts:
        p.transform(m)


def _picture(path, size, pixel):
    """Картинка нужного размера: (RGB, прозрачность или None)."""
    from PIL import Image
    im = Image.open(path)
    alpha = im.getchannel('A') if 'A' in im.getbands() else None
    im = im.convert('RGB')
    how = Image.NEAREST if pixel else Image.LANCZOS
    if im.size != (size, size):
        im = im.resize((size, size), how)
        if alpha is not None:
            alpha = alpha.resize((size, size), how)
    return im, alpha


def _save(img, path):
    img.info.clear()                                # без цветового профиля исходника
    img.save(path, optimize=True)


def car_texture(name, d, body, wheels, flat_uv):
    """Текстура исходника -> слои, как у остальных машин: <имя>.png (RGBA: всё, что не красится; на месте
    краски — прозрачно) и <имя>_shade.png (светотень краски).  Краска находится по окраскам набора (то, что
    от окраски к окраске меняется), а если окраска одна — по цвету: у кузова он свой, а стёкла, шины, хром
    от него отличаются.  Если у текстуры есть вырезы (cut), они уходят в <имя>_cut.png.  Возвращает долю
    краски на кузове."""
    from PIL import Image
    size = d.get('size', TEX_SIZE)
    pixel = bool(d.get('pixel'))
    img, alpha = _picture(src(*d['tex']), size, pixel)
    used = uv_mask(body, size)
    if d.get('cut') and alpha is not None:
        # вырез оставляем там, где он действительно попадает на грани кузова
        hole = (np.asarray(alpha) < 128) & dilate(used, 1)
        _save(Image.fromarray(np.where(hole, 0, 255).astype(np.uint8), 'L'), os.path.join(VEH, name + '_cut.png'))
    if d.get('fixed'):
        # текстура идёт как есть
        _save(img, os.path.join(VEH, name + '.png'))
        return 0.0
    a = np.asarray(img).copy()
    # гладкие материалы (стекло): закрашиваем квадратик в свободном углу, грани смотрят в него
    q = max(2, size // 64)
    for (u, v), col in flat_uv:
        x, y = int(u * size), int((1.0 - v) * size)
        a[y - q:y + q, x - q:x + q] = col
    if d.get('variants'):
        stack = np.stack([a] + [np.asarray(_picture(src(*v), size, pixel)[0]) for v in d['variants']]).astype(np.int16)
        m = (stack.max(0) - stack.min(0)).max(2) > d.get('spread', 30)
        clean = False
    else:
        h, s, v = hsv(a)
        rule = d['paint']
        m = np.zeros(h.shape, dtype=bool)
        if 'hue' in rule:
            h0, h1 = rule['hue']
            hue = ((h >= h0) & (h <= h1)) if h0 <= h1 else ((h >= h0) | (h <= h1))
            m |= hue & (s >= rule['sat'][0]) & (s <= rule['sat'][1]) & (v >= rule['val'])
        if 'white' in rule:
            m |= (s <= rule['white'][0]) & (v >= rule['white'][1])
        if 'tint' in rule:
            m |= (s <= rule['tint'][0]) & (v >= rule['tint'][1])
        k = size / float(Image.open(src(*d['tex'])).size[0])
        for (x0, y0, x1, y1) in rule.get('keep', ()):
            m[int(y0 * k):int(y1 * k) + 1, int(x0 * k):int(x1 * k) + 1] = False
        clean = not pixel
        m &= dilate(used, 2)                        # по цвету краску ищем только там, куда смотрят грани кузова
    m &= ~uv_mask(wheels, size)
    for (u, vv), col in flat_uv:
        x, y = int(u * size), int((1.0 - vv) * size)
        m[y - q - 1:y + q + 1, x - q - 1:x + q + 1] = False
    if clean:
        # одиночные точки краски среди деталей и дырки в краске убираем
        m = dilate(erode(m, 1), 1) | (m & erode(dilate(m, 2), 2) & dilate(erode(m, 1), 2))
    L = lum(a.astype(np.float64))
    ref = float(np.median(L[m])) if m.any() else 128.0
    shade = np.where(m, np.clip(L / ref * 127.5, 0, 255), 128.0)
    share = float(m.sum()) / max(1.0, float(used.sum()))
    if d.get('vector'):
        # мелкая пиксельная текстура: увеличиваем, обводя края заново; колесо остаётся пиксельным
        import vector_tex
        big, bshade = vector_tex.upscale(a, m, shade, int(d['vector']), d.get('levels', ()), d.get('shades', ()),
                                         dilate(uv_mask(wheels, size), 1))
        _save(Image.fromarray(big, 'RGBA'), os.path.join(VEH, name + '.png'))
        _save(Image.fromarray(bshade, 'L'), os.path.join(VEH, name + '_shade.png'))
        return share
    rgba = np.zeros((size, size, 4), np.uint8)
    rgba[..., :3] = np.where(m[..., None], shade[..., None], a).astype(np.uint8)
    rgba[..., 3] = np.where(m, 0, 255)
    _save(Image.fromarray(rgba, 'RGBA'), os.path.join(VEH, name + '.png'))
    _save(Image.fromarray(shade.astype(np.uint8), 'L'), os.path.join(VEH, name + '_shade.png'))
    return share


def free_spot(parts, size=TEX_SIZE, block=14):
    """Свободное место на текстуре (не занятое развёрткой) под квадратики гладких материалов."""
    used = dilate(uv_mask(parts, size), 2)
    block = max(block, size // 18)
    spots = []
    for y in range(block, size - block, block):
        for x in range(block, size - block, block):
            if not used[y - block // 2:y + block // 2, x - block // 2:x + block // 2].any():
                spots.append(((x + 0.5) / size, 1.0 - (y + 0.5) / size))
    return spots


def convert_car(name, d):
    from panda3d.core import NodePath
    _panda()
    allp = named(ms.read(src(*d['file'])))
    if d.get('yup'):                                # у glTF, FBX и OBJ вверх смотрит Y, нос — на +Z
        for p in allp.values():
            p.transform(YUP)
    body = [allp[n].copy() for n in d['parts']]
    wheels = [allp[n].copy() for n in d['wheels']] if d.get('wheels') else []
    steer = allp[d['steer']].copy() if d.get('steer') else None
    if d.get('mirror'):
        body = body + [p.copy(p.name + '_m').transform(np.diag([-1.0, 1.0, 1.0])) for p in body]
    _turn(body + wheels + ([steer] if steer is not None else []), d['turn'])
    if d.get('wheel_file'):
        # колесо лежит отдельным файлом: ставим его на четыре места, шиной на землю
        wp = named(ms.read(src(*d['wheel_file'])))
        w0 = list(wp.values())[0]
        if d.get('yup'):
            w0.transform(YUP)
        lo, hi = w0.bounds()
        w0.verts = w0.verts - (lo + hi) * 0.5
        r = float(hi[2] - lo[2]) * 0.5
        for (wx, wy) in d['wheel_at']:
            for sx in (1.0, -1.0):
                w = w0.copy('wheel')
                if sx < 0:
                    w.transform(np.diag([-1.0, 1.0, 1.0]))
                w.verts = w.verts + (wx * sx, wy, r)
                wheels.append(w)
    if not wheels:
        # колёса — круглые куски у земли
        zmin = min(p.verts[:, 2].min() for p in body)
        nb = []
        for p in body:
            keep = np.ones(len(p.tris), dtype=bool)
            for comp in components(p):
                pts = tri_points(p, comp)
                lo, hi = pts.min(0), pts.max(0)
                ext = hi - lo
                if abs(ext[1] - ext[2]) < 0.14 * max(ext[1], ext[2]) and ext[0] < ext[1] * 0.8 and lo[2] < zmin + 0.08 * ext[2] \
                        and 6 <= len(comp) <= 80:
                    wheels.append(p.select(np.isin(np.arange(len(p.tris)), comp), 'wheel'))
                    keep[comp] = False
            nb.append(p.select(keep))
        body = nb
    assert len(wheels) == 4, (name, len(wheels))
    # масштаб по ширине кузова, середина — в начало координат, колёса — на землю
    pts = np.concatenate([tri_points(p) for p in body])
    width = pts[:, 0].max() - pts[:, 0].min()
    k = d['width'] / width
    # середина по ширине — между колёсами: кузов исходника бывает сдвинут (зеркала, открытая дверь)
    wc = np.array([(tri_points(w).min(0) + tri_points(w).max(0)) * 0.5 for w in wheels])
    cx = float(wc[:, 0].mean())
    cy = (pts[:, 1].max() + pts[:, 1].min()) * 0.5
    z0 = min(tri_points(w)[:, 2].min() for w in wheels)
    for p in body + wheels + ([steer] if steer is not None else []):
        p.verts = (p.verts - (cx, cy, z0)) * k
    pts = np.concatenate([tri_points(p) for p in body])
    # гладкие материалы: их грани на картинку не опираются (развёртка у них от других текстур набора)
    glass_mat = d.get('glass')
    skin = [p.select([p.mats[m] not in d['flat'] and p.mats[m] != glass_mat for m in p.mat]) for p in body]
    size = d.get('size', TEX_SIZE)
    spots = free_spot(skin + wheels + ([steer] if steer is not None else []), size)
    flat_uv = []
    out = Out()
    glass = Out()
    dropped = 0
    for p in body:
        for i in range(len(p.tris)):
            mat = p.mats[p.mat[i]]
            if mat == glass_mat:
                glass.tri(p.verts[p.tris[i]], ((0.5, 0.5),) * 3)
            elif mat in d['flat']:
                col = d['flat'][mat]
                if col is None:
                    dropped += 1
                    continue
                uv = None
                for (u, c) in flat_uv:
                    if c == col:
                        uv = u
                if uv is None:
                    uv = spots[len(flat_uv)]
                    flat_uv.append((uv, col))
                out.tri(p.verts[p.tris[i]], (uv, uv, uv))
            else:
                out.tri(p.verts[p.tris[i]], p.uvs[i])
    share = car_texture(name, d, skin + ([steer] if steer is not None else []), wheels, flat_uv)
    root = NodePath('car')
    b = root.attachNewNode('body')
    sk = b.attachNewNode('skin')
    sk.attachNewNode(out.node('shell'))
    info = dict(W=round(float(pts[:, 0].max() - pts[:, 0].min()), 3), L=round(float(pts[:, 1].max() - pts[:, 1].min()), 3),
                H=round(float(pts[:, 2].max()), 3), tex=True, wheels=[])
    if d.get('fixed'):
        info['fixed'] = True
    if d.get('cut') and os.path.isfile(os.path.join(VEH, name + '_cut.png')):
        info['cut'] = True
    if len(glass):
        b.attachNewNode(glass.node('glass'))
        info['glass'] = True
    if steer is not None:
        # рулевое колесо: узел стоит в середине обода, его ось Y смотрит вдоль рулевой колонки (на водителя)
        sp = tri_points(steer)
        c0 = sp.mean(0)
        q = sp - c0
        ev, evec = np.linalg.eigh(q.T.dot(q))
        ax = evec[:, 0]                              # обод плоский: ось — направление наименьшего разброса
        if ax[1] > 0:
            ax = -ax                                 # колонка смотрит назад, на водителя
        rad = float(np.linalg.norm(q - np.outer(q.dot(ax), ax), axis=1).max())
        so = Out()
        so.part(steer, xf=lambda v: v - c0)
        sn = sk.attachNewNode(so.node('swheel'))
        sn.setPos(float(c0[0]), float(c0[1]), float(c0[2]))
        info['steer'] = dict(pos=[round(float(v), 3) for v in c0], axis=[round(float(v), 4) for v in ax],
                             r=round(rad, 3))
    if d.get('seats'):
        info['seats'] = [[round(float(v), 3) for v in sxyz] for sxyz in d['seats']]
    if d.get('feet'):
        info['feet'] = [[round(float(v), 3) for v in f] for f in d['feet']]
    ws = []
    for w in wheels:
        wp = tri_points(w)
        lo, hi = wp.min(0), wp.max(0)
        ws.append((w, (lo + hi) * 0.5, float((hi[1] - lo[1] + hi[2] - lo[2]) * 0.25)))
    # колесо-образец: правое переднее, наружной стороной к +X
    w, c, r = sorted(ws, key=lambda q: (0 if q[1][0] > 0 else 1, -q[1][1]))[0]
    wo = Out()
    wo.part(w, xf=lambda q: q - c)
    root.attachNewNode(wo.node('wheel'))
    for w, c, r in sorted(ws, key=lambda q: (0 if q[1][1] > 0 else 1, q[1][0])):
        info['wheels'].append(dict(x=round(float(c[0]), 3), y=round(float(c[1]), 3), r=round(r, 3)))
    hw, hl, H = info['W'] * 0.5, info['L'] * 0.5, info['H']
    info['head'] = [[-hw * d['head'][1], round(hl - 0.03, 3), round(H * d['head'][0], 3)],
                    [hw * d['head'][1], round(hl - 0.03, 3), round(H * d['head'][0], 3)]]
    info['tail'] = [[-hw * d['tail'][1], round(-hl + 0.03, 3), round(H * d['tail'][0], 3)],
                    [hw * d['tail'][1], round(-hl + 0.03, 3), round(H * d['tail'][0], 3)]]
    root.writeBamFile(os.path.join(VEH, name + '.bam'))
    print('  %-7s Ш %.2f  Д %.2f  В %.2f  треугольников %d (стёкол %d, убрано %d), колесо r %.2f, краски на кузове %d%%' % (
        name, info['W'], info['L'], info['H'], len(out), len(glass), dropped, info['wheels'][0]['r'], round(share * 100)))
    return info


def do_cars(meta, only=None):
    os.makedirs(VEH, exist_ok=True)
    for name in sorted(CARS):
        if only and name not in only:
            continue
        meta['vehicles'][name] = convert_car(name, CARS[name])


# ---------------------------------------------------------------------------
# двухколёсные
# ---------------------------------------------------------------------------
DARK = (0.10, 0.10, 0.11)
STEEL = (0.70, 0.71, 0.74)
YUP = np.array([[-1.0, 0, 0], [0, 0, 1.0], [0, 1.0, 0]])        # (x, y, z) -> (-x, z, y): Y вверх -> Z вверх


def poses():
    sys.path.insert(0, ROOT)
    from game import bikes
    return bikes.POSES, bikes.PELVIS_UP, bikes.SOLE


def bend(pts, z0, z1, dy, dz):
    """Сдвинуть верх вилки (руль) на (dy, dz): ниже z0 всё на месте, выше z1 — сдвиг полный, между — плавно."""
    out = pts.copy()
    t = np.clip((pts[:, 2] - z0) / max(1e-6, z1 - z0), 0.0, 1.0)
    out[:, 1] += dy * t
    out[:, 2] += dz * t
    return out


class Bike(object):
    """Собирает модель двухколёсного: узлы body, paint, fork, fork_paint, wheel_f, wheel_r; в каждом —
    сетка «g» (цвет вершин и общая зернистая текстура) и, если нужно, «t» (своя текстура модели)."""

    def __init__(self, name):
        self.name = name
        self.nodes = {}
        self.info = dict()

    def out(self, node, kind='g'):
        return self.nodes.setdefault(node, {}).setdefault(kind, Out())

    def write(self):
        from panda3d.core import NodePath
        _panda()
        root = NodePath('bike')
        tris = 0
        for node in ('body', 'paint', 'fork', 'fork_paint', 'wheel_f', 'wheel_r'):
            np_ = root.attachNewNode(node)
            # «g» — зернистая текстура, «t» — своя текстура модели, «p» — текстура с краской (бак чоппера)
            for kind, o in sorted(self.nodes.get(node, {}).items()):
                if len(o):
                    np_.attachNewNode(o.node(kind))
                    tris += len(o)
        root.writeBamFile(os.path.join(VEH, 'b_%s.bam' % self.name))
        self.info['tris'] = tris
        return self.info


def _pegs(b, foot, col=DARK, bar=True):
    """Подножки под стопами ездока (на модели их нет): поперечина и две площадки."""
    fx, fy, fz = foot
    o = b.out('body')
    if bar:
        o.tube((-fx - 0.02, fy, fz - 0.015), (fx + 0.02, fy, fz - 0.015), 0.014, STEEL, 4)
    for sx in (-1, 1):
        o.box(sx * fx - 0.055, fy - 0.07, fz - 0.03, sx * fx + 0.055, fy + 0.07, fz, col)


def top_z(tris, x, y):
    """Высота поверхности сетки над точкой (x, y): tris — массив (n, 3, 3).  None, если под точкой пусто."""
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    ok = np.abs(d) > 1e-12
    d = np.where(ok, d, 1.0)
    u = ((b[:, 1] - c[:, 1]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y - c[:, 1])) / d
    v = ((c[:, 1] - a[:, 1]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y - c[:, 1])) / d
    w = 1.0 - u - v
    hit = ok & (u >= 0.0) & (v >= 0.0) & (w >= 0.0)
    if not hit.any():
        return None
    return float((u * a[:, 2] + v * b[:, 2] + w * c[:, 2])[hit].max())


CHOP_K = 0.45               # масштаб чоппера: исходник в 2,2 раза крупнее настоящего мотоцикла
CHOP_LEAN = 14.0            # ездок тянется к высокому рулю: корпус подан вперёд, градусы
CHOP_REACH = 0.665          # от плеча до середины ладони при почти прямой руке, м


def bike_chop():
    """Чоппер Duhgless (Another PSX Style Low-poly Bike): рама, вилка и колёса со своими текстурами.

    Четыре текстуры исходника сведены на один лист 512x512 (рама, вилка, переднее и заднее колесо).  Спицы у
    модели настоящие — отдельные полоски, между ними видно насквозь.  Бак вынесен отдельно: его чёрная краска
    заменяется цветом мотоцикла, пламя остаётся (b_chop_tank.png — что не красится, b_chop_tank_shade.png —
    светотень краски).

    Руль высокий и далёкий: ездок достаёт до него почти прямыми руками, подав корпус вперёд (CHOP_LEAN);
    сколько не хватает — на столько ручки сдвигаются к ездоку.  Подножки исходника вынесены вперёд дальше,
    чем достают ноги, поэтому под стопами ставятся свои, как у остальных мотоциклов."""
    from PIL import Image, ImageDraw
    import io
    parts, images, marks = ms.read_glb(src('duhgless', 'motorbike.glb'), nodes=True)
    P = named(parts)
    turn = np.array([[0.0, 0, 1.0], [1.0, 0, 0], [0, 1.0, 0]])      # исходник: нос на +X, вверх Y, вправо Z
    for p in P.values():
        p.transform(turn)
    marks = dict((k, turn.dot(v)) for k, v in marks.items())
    frame, fork = P['motorbike_frame'], P['motorbike_fork']
    wf, wr = P['motorbike_wheel_front'], P['motorbike_wheel_back']
    K = CHOP_K

    def axle(p):
        lo, hi = p.bounds()
        return (lo + hi) * 0.5, float(hi[2] - lo[2]) * 0.5, float(hi[0] - lo[0])
    cf, rf, wfw = axle(wf)
    cr, rr, wrw = axle(wr)
    ground = 0.5 * ((cf[2] - rf) + (cr[2] - rr))
    mid = (cf[1] + cr[1]) * 0.5
    off = np.array((0.0, mid, ground))
    for p in (frame, fork, wf, wr):
        p.verts = (p.verts - off) * K
    marks = dict((k, (v - off) * K) for k, v in marks.items())
    fy, ry = float((cf[1] - mid) * K), float((cr[1] - mid) * K)
    rf, rr, wfw, wrw = rf * K, rr * K, wfw * K, wrw * K

    # --- лист текстур: рама и вилка сверху, колёса снизу
    SZ = 256
    tex = dict((mi, Image.open(io.BytesIO(data)).convert('RGB')) for mi, data in images.items())
    for im in tex.values():
        assert im.size == (SZ, SZ), im.size
    atlas = np.zeros((SZ * 2, SZ * 2, 3), np.uint8)
    src_uv = {}
    for part, (cx, cy) in ((frame, (0, 0)), (fork, (1, 0)), (wf, (0, 1)), (wr, (1, 1))):
        assert len(set(part.mat.tolist())) == 1 and part.uvs.min() >= 0.0 and part.uvs.max() <= 1.0, part.name
        atlas[cy * SZ:(cy + 1) * SZ, cx * SZ:(cx + 1) * SZ] = np.asarray(tex[int(part.mat[0])])
        src_uv[part.name] = part.uvs.copy()
        part.uvs = np.stack([(part.uvs[..., 0] + cx) * 0.5, (part.uvs[..., 1] + (1 - cy)) * 0.5], axis=-1)
    Image.fromarray(atlas, 'RGB').save(os.path.join(VEH, 'b_chop.png'), optimize=True)

    def raster(uvs, size):
        im = Image.new('L', (size, size), 0)
        d = ImageDraw.Draw(im)
        for uv in uvs:
            d.polygon([(float(u) * size, (1.0 - float(v)) * size) for u, v in uv], fill=255, outline=255)
        return np.asarray(im) > 0

    b = Bike('chop')
    for part, node, cy, r in ((wf, 'wheel_f', fy, rf), (wr, 'wheel_r', ry, rr)):
        b.out(node, 't').part(part, xf=lambda q, cy=cy, r=r: q - (0.0, cy, r))

    # --- бак: грани над двигателем, у которых на текстуре чёрная краска с пламенем (а не металл)
    ft = np.asarray(tex[int(frame.mat[0])]).astype(np.float64)
    orange = (ft[..., 0] > 90.0) & (ft[..., 0] - ft[..., 2] > 45.0) & (ft[..., 0] >= ft[..., 1])
    edge = (ft[..., 0] > 50.0) & (ft[..., 0] - ft[..., 2] > 22.0) & (ft[..., 0] >= ft[..., 1])
    fl = lum(ft)
    cen = frame.verts[frame.tris].mean(1)
    fuv = src_uv[frame.name]
    y0, y1, z0 = (-0.36 - mid) * K, (0.56 - mid) * K, (1.62 - ground) * K
    tank = np.zeros(len(frame.tris), bool)
    for i in np.where((cen[:, 1] > y0) & (cen[:, 1] < y1) & (cen[:, 2] > z0) & (np.abs(cen[:, 0]) < 0.33 * K))[0]:
        m = raster(fuv[i:i + 1], SZ)
        if m.any() and float(fl[m & ~edge].mean() if (m & ~edge).any() else 0.0) < 46.0:
            tank[i] = True
    assert 120 <= int(tank.sum()) <= 420, tank.sum()
    tm = raster(fuv[tank], SZ) & ~raster(fuv[~tank], SZ)
    paint = tm & ~edge                                  # краска: всё на баке, кроме пламени
    rgba = np.zeros((SZ, SZ, 4), np.uint8)
    rgba[..., :3] = ft.astype(np.uint8)
    rgba[..., 3] = np.where(paint, 0, 255)
    Image.fromarray(rgba, 'RGBA').save(os.path.join(VEH, 'b_chop_tank.png'), optimize=True)
    shade = np.where(paint, np.clip(104.0 + fl * 1.5, 0.0, 255.0), 128.0)
    Image.fromarray(shade.astype(np.uint8), 'L').save(os.path.join(VEH, 'b_chop_tank_shade.png'), optimize=True)
    o_t, o_p = b.out('body', 't'), b.out('body', 'p')
    for i in range(len(frame.tris)):
        if tank[i]:
            o_p.tri(frame.verts[frame.tris[i]], fuv[i])
        else:
            o_t.tri(frame.verts[frame.tris[i]], frame.uvs[i])

    # --- посадка: таз — в ложбине седла, стопы — как в позе, руки тянутся к рулю
    POS, up, sole = poses()
    pose = 'chair'
    ftris = frame.verts[frame.tris]
    sy = float(marks['motorbike_seat'][1])
    seat_top = top_z(ftris, 0.0, sy)
    assert seat_top is not None and 0.55 < seat_top < 0.80, seat_top
    py, pz = sy, seat_top + up
    v = fork.verts
    ends = v[np.abs(v[:, 0]) > 0.44 * K]                 # концы руля — ручки
    gx, gy, gz = float(np.abs(ends[:, 0]).mean()), float(ends[:, 1].mean()), float(ends[:, 2].mean())
    from game import bikes as B
    sx, sf, su = B.SHOULDER
    a = math.radians(CHOP_LEAN)
    sh_y = py + sf * math.cos(a) + (su - B.WAIST) * math.sin(a)
    sh_z = pz + B.WAIST + (su - B.WAIST) * math.cos(a) - sf * math.sin(a)
    need = math.sqrt(max(0.0, CHOP_REACH ** 2 - (gx - sx) ** 2 - (gz - sh_z) ** 2))
    dy = min(0.0, sh_y + need - gy)
    dz = 0.0
    bar0 = float(v[np.abs(v[:, 0]) > 0.12 * K][:, 2].min())          # руль — всё, что шире вилки…
    bar0 = max(bar0, (2.28 - ground) * K)                             # …и выше её верха
    fv = bend(v, bar0 - 0.05, bar0 + 0.02, dy, dz)
    o = b.out('fork', 't')
    for i in range(len(fork.tris)):
        o.tri(fv[fork.tris[i]] - (0.0, fy, 0.0), fork.uvs[i])
    fx, ff, fu = POS[pose]['foot']
    foot = (fx, py + ff, pz + fu - sole)
    _pegs(b, foot)
    head = marks['motorbike_head']
    lamp = v[(np.abs(v[:, 0]) < 0.12 * K) & (v[:, 2] > (1.75 - ground) * K) & (v[:, 2] < (2.2 - ground) * K)]
    hy = float(lamp[:, 1].max())
    hz = float(lamp[lamp[:, 1] > hy - 0.06][:, 2].mean())
    fpts = frame.verts
    rear = fpts[np.argmin(fpts[:, 1])]
    b.info.update(
        wheel_f=[round(fy, 3), round(rf, 3), round(wfw, 3)], wheel_r=[round(ry, 3), round(rr, 3), round(wrw, 3)],
        tex='b_chop', ptex='b_chop_tank', pose=pose, lean=CHOP_LEAN,
        seat=[round(py, 3), round(pz, 3)], seat2=[round(py - 0.33, 3), round(pz + 0.06, 3)],
        grips=[round(gx, 3), round(gy + dy, 3), round(gz + dz, 3)], foot=[round(q, 3) for q in foot],
        seat_top=round(seat_top, 3), seat_y=[round(sy - 0.06, 3), round(sy + 0.04, 3)], bend=[round(dy, 3), round(dz, 3)],
        head=[0.0, round(hy + 0.02, 3), round(hz, 3)], tail=[0.0, round(float(rear[1]) - 0.02, 3), round(float(rear[2]), 3)],
        L=round(float(fy + rf - (ry - rr)), 3), y0=round(float(ry - rr), 3), y1=round(float(fy + rf), 3),
        W=round(float(np.abs(fv[:, 0]).max() * 2.0), 3), H=round(float(fv[:, 2].max()), 3),
        axis=[round(float(head[1]), 3), round(float(head[2]), 3)])
    return b.write()


BIKES = {'chop': bike_chop}


def do_bikes(meta, only=None):
    os.makedirs(VEH, exist_ok=True)
    if not only:
        grain_texture(os.path.join(VEH, 'grain.png'))
        meta['bikes'] = {}
    for name in sorted(BIKES):
        if only and name not in only:
            continue
        info = BIKES[name]()
        meta['bikes'][name] = info
        print('  %-6s поза %-6s таз (%.2f, %.2f)  ручки (±%.2f, %.2f, %.2f), руль сдвинут на (%+.2f, %+.2f)  Д %.2f Ш %.2f В %.2f  '
              'оси %+.2f / %+.2f  колёса r %.2f / %.2f  треугольников %d' % (
                  name, info['pose'], info['seat'][0], info['seat'][1], info['grips'][0], info['grips'][1], info['grips'][2],
                  info['bend'][0], info['bend'][1], info['L'], info['W'], info['H'], info['wheel_f'][0], info['wheel_r'][0],
                  info['wheel_f'][1], info['wheel_r'][1], info['tris']))


# ---------------------------------------------------------------------------
# детали тюнинга (Kenney, Car Kit)
# ---------------------------------------------------------------------------
PARTS = {'spoiler_a': 'debris-spoiler-a', 'spoiler_b': 'debris-spoiler-b', 'bumper': 'debris-bumper'}


def do_parts(meta):
    """veh/parts.bam: спойлеры и бампер.  У каждой детали узел paint (то, что красится в цвет кузова) и
    узел g (стойки, металл).  Ширина приведена к 1 м — игра растягивает деталь под машину; низ — на z = 0."""
    from PIL import Image
    from panda3d.core import NodePath
    _panda()
    pal = np.asarray(Image.open(src('kenney_carkit', 'Textures', 'colormap.png')).convert('RGB'))
    ph, pw = pal.shape[:2]
    root = NodePath('parts')
    meta['parts'] = {}
    for name, fname in sorted(PARTS.items()):
        p = ms.merge(ms.read(src('kenney_carkit', fname + '.obj')), name)
        p.transform(YUP)
        lo, hi = p.bounds()
        k = 1.0 / (hi[0] - lo[0])
        c = np.array(((lo[0] + hi[0]) * 0.5, (lo[1] + hi[1]) * 0.5, lo[2]))
        paint, rest = Out(), Out()
        for i in range(len(p.tris)):
            uv = p.uvs[i].mean(0)
            col = pal[min(ph - 1, max(0, int((1.0 - uv[1]) * ph))), min(pw - 1, max(0, int(uv[0] * pw)))].astype(np.float64)
            pts = (p.verts[p.tris[i]] - c) * k
            if col[0] > 190 and col[1] < 150:             # красно-оранжевое в наборе — «краска»
                s = float(lum(col)) / 140.0
                paint.tri(pts, color=(min(1.0, s), min(1.0, s), min(1.0, s)))
            elif max(col) < 90:
                rest.tri(pts, color=DARK)
            else:
                g = float(lum(col)) / 255.0 * 1.25
                rest.tri(pts, color=(min(1.0, g), min(1.0, g), min(1.0, g * 1.02)))
        n = root.attachNewNode(name)
        if len(paint):
            n.attachNewNode(paint.node('paint'))
        if len(rest):
            n.attachNewNode(rest.node('g'))
        size = (hi - lo) * k
        meta['parts'][name] = dict(depth=round(float(size[1]), 3), height=round(float(size[2]), 3), tris=len(paint) + len(rest))
        print('  %-10s глубина %.2f  высота %.2f (при ширине 1 м)  треугольников %d, из них красится %d' % (
            name, size[1], size[2], len(paint) + len(rest), len(paint)))
    root.writeBamFile(os.path.join(VEH, 'parts.bam'))


# ---------------------------------------------------------------------------
# бутылка с зажигательной смесью
# ---------------------------------------------------------------------------
def do_bottle(meta):
    """weapons/molotov.bam: бутылка (Quaternius, Survival) с тряпкой в горлышке.  Раньше «коктейлем» служила
    модель зажигательной гранаты — красный баллон с чекой."""
    from panda3d.core import NodePath, ModelRoot
    _panda()
    p = named(ms.read(src('quat', 'S_WaterBottle_1.usda')))['Cylinder_001']
    lo, hi = p.bounds()
    L = 0.25
    k = L / (hi[1] - lo[1])
    grip = lo[1] + (hi[1] - lo[1]) * 0.80                 # держат за горлышко: бутылка висит донышком вниз
    c = np.array(((lo[0] + hi[0]) * 0.5, grip, (lo[2] + hi[2]) * 0.5))
    glass, rag = (0.20, 0.33, 0.14), (0.82, 0.80, 0.74)
    o = Out()
    cap = p.mats.index('Grey')
    flip = np.array((-1.0, -1.0, 1.0))                    # донышко — к +Y («вперёд» у оружия; у опущенной руки это вниз)
    for i in range(len(p.tris)):
        pts = (p.verts[p.tris[i]] - c) * k * flip
        o.tri(pts, color=rag if p.mat[i] == cap else glass)
    top = -(hi[1] - grip) * k
    # тряпка-фитиль: торчит из горлышка и свисает вбок, чтобы её было видно из-за кулака
    o.box(-0.012, top - 0.035, -0.006, 0.012, top + 0.012, 0.006, rag)
    o.box(-0.012, top - 0.045, 0.004, 0.012, top - 0.025, 0.060, rag)
    o.box(-0.011, top - 0.040, 0.050, 0.011, top + 0.030, 0.062, rag)
    root = NodePath(ModelRoot('molotov'))
    root.attachNewNode(o.node('molotov'))
    root.writeBamFile(os.path.join(OUT, 'weapons', 'molotov.bam'))
    pts = np.array([r[0] for r in o.rows])
    meta['weapons']['molotov'] = dict(length=round(float(pts[:, 1].max() - pts[:, 1].min()), 3),
                                      muzzle=[0.0, round(float(pts[:, 1].max()), 3), 0.0])
    print('  бутылка: длина %.2f м, толщина %.3f м, треугольников %d' % (
        pts[:, 1].max() - pts[:, 1].min(), pts[:, 0].max() - pts[:, 0].min(), len(o)))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if cmd == 'fetch':
        fetch()
        return
    mpath = os.path.join(OUT, 'models.json')
    with open(mpath, encoding='utf-8') as f:
        meta = json.load(f)
    only = set(sys.argv[2:]) or None                 # «cars cab», «bikes chop»: пересобрать только названное
    if cmd in ('all', 'cars'):
        do_cars(meta, only)
    if cmd in ('all', 'bikes'):
        do_bikes(meta, only)
    if cmd in ('all', 'parts'):
        do_parts(meta)
    if cmd in ('all', 'bottle'):
        do_bottle(meta)
    with open(mpath, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1, sort_keys=True, ensure_ascii=False)
    print('готово:', os.path.relpath(mpath, ROOT))


if __name__ == '__main__':
    main()
