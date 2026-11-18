# -*- coding: utf-8 -*-
"""Импорт готовых моделей транспорта, которых нет в основном наборе машин: семь автомобилей в стиле PS1,
два мотоцикла, два велосипеда, карт и детали тюнинга.

Нужен только тому, кто пересобирает модели: игра читает готовые файлы из assets/models/veh.

    pip install panda3d numpy pillow blender-asset-tracer
    python tools/import_vehicles.py fetch         # скачать исходники в .cache/model_src/new
    python tools/import_vehicles.py all           # машины, двухколёсные, детали
    python tools/import_vehicles.py cars cab      # только одна машина (так же: bikes chop)

Откуда что берётся (лицензии и авторы — в assets/models/CREDITS.md):
  * «Ястреб» (купе) — «PSX Car — 2 Seater Coupe» (boggle): копия .obj в репозитории KopiOCoder/FormulaCyber;
  * «Гольф» (хэтчбек VW Golf Mk2 GTI) — «PS1 / Pixel Art style car» (designersoup, CC0): копия в репозитории
    Soursop-Pop/Roadtrip;
  * «Призрак» (ретро-седан) — MoiDev, «Suspicious Car — PSX Style Car» (CC0): копия папки «Suspicious Car 01»
    в репозитории luisfillipedias/OHOMEMDEMETAS;
  * «Классик» (седан 80-х, машина главного героя) — Bricchi Games, «Retro Car With Interior» (CC BY 4.0):
    копия с маской покраски в репозитории matapao/drifting01; .fbx конвертируется в .glb через
    npx fbx2gltf (нужен Node.js);
  * такси — Yellow Taxi/Cab, PS1 Car (MoiDev); копия со Sketchfab из репозитория Langorithm/3d-models;
  * чоппер — Another PSX Style Low-poly Bike (Duhgless, CC0); копия с текстурами 256 точек из
    репозитория webbertakken/citymap;
  * мотоцикл — Kenney, Starter Kit Racing (CC0);  карт, спойлеры, бампер, колёса — Kenney, Car Kit (CC0);
  * второй велосипед, бутылка — Quaternius (CC0), репозиторий chibifire-stages/quaternius-stage.

Модели с itch.io сюда попадают через их копии на GitHub: с самого itch.io файлы скриптом не скачать.

Что делает импорт:
  * всё приводится к осям игры (Z вверх, нос — к +Y, колёса стоят на земле, середина — в начале координат)
    и к настоящим размерам в метрах;
  * колёса отделяются от кузова, у двухколёсных отдельно идёт вилка с рулём;
  * у машин с фототекстурой краска отделяется от остального (стёкла, хром, ржавчина), чтобы игра могла
    перекрашивать кузов;
  * у двухколёсных с модели снимаются точки посадки: где седло, где ручки руля, где подножки; руль
    подводится к рукам ездока (поза у него одна из четырёх готовых), недостающие мелочи — подножки,
    педали, седло велосипеда — достраиваются.
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
    ('M3-org/retro3d-assets', None, [
        ('Vehicles/bike_vintage (unfinished).blend', 'm3/bike_vintage.blend'),
        ('Vehicles/Materials/bike_vintage.png', 'm3/bike_vintage.png'),
    ]),
    # boggle, PSX Car — 2 Seater Coupe (https://boggle.itch.io/2-seater-coupe): копия .obj в репозитории
    # KopiOCoder/FormulaCyber (там же лежат .glb и варианты окраски; игра перекрашивает кузов сама)
    ('KopiOCoder/FormulaCyber', 'main', [
        ('cars/japanese_2_seater_coupe/2_seater_coupe.obj', 'boggle_coupe/2_seater_coupe.obj'),
        ('cars/japanese_2_seater_coupe/wheel.obj', 'boggle_coupe/wheel.obj'),
        ('cars/japanese_2_seater_coupe/textures/crystal_white.png', 'boggle_coupe/textures/crystal_white.png'),
    ]),
    # designersoup, PS1 / Pixel Art style car — VW Golf Mk2 GTI (CC0),
    # (https://designersoup.itch.io/ps1-pixel-art-style-car): копия в репозитории Soursop-Pop/Roadtrip
    ('Soursop-Pop/Roadtrip', 'main', [
        ('Assets/Prefabs/car/red_golf.obj', 'designersoup_golf/red_golf.obj'),
        ('Assets/Prefabs/car/red_golf.mtl', 'designersoup_golf/red_golf.mtl'),
        ('Assets/Prefabs/car/pixel art golf final.png', 'designersoup_golf/pixel_art_golf_final.png'),
    ]),
    # MoiDev, Suspicious Car — PSX Style Car (https://moidev.itch.io/a-suspicious-car-for-your-projects, CC0):
    # копия полной папки («Suspicious Car 01», шесть окрасок и Color Mask) в репозитории luisfillipedias/OHOMEMDEMETAS
    ('luisfillipedias/OHOMEMDEMETAS', 'main', [
        ('assets/models/car/psx/Suspicious Car 01/Suspicious Car.obj', 'moidev_suspicious/Suspicious Car.obj'),
        ('assets/models/car/psx/Suspicious Car 01/Texture Black.png', 'moidev_suspicious/Texture Black.png'),
        ('assets/models/car/psx/Suspicious Car 01/Color Mask.png', 'moidev_suspicious/Color Mask.png'),
    ]),
    # Bricchi Games, Retro Car With Interior (https://bricchi-games.itch.io/retro-car-with-interior, CC BY 4.0):
    # «машину главного героя» автор перепаковал с маской покраски; копия лежит в репозитории matapao/drifting01
    ('matapao/drifting01', 'main', [
        ('src/assets/car/retro-car.fbx', 'bricchi_retro/retro-car.fbx'),
        ('src/assets/car/car-paint-base.jpg', 'bricchi_retro/car-paint-base.jpg'),
        ('src/assets/car/car-paint-mask.png', 'bricchi_retro/car-paint-mask.png'),
        ('src/assets/car/car-emissive.png', 'bricchi_retro/car-emissive.png'),
    ]),
    ('KenneyNL/Starter-Kit-Racing', None, [
        ('models/vehicle-motorcycle.glb', 'kenney_racing/vehicle-motorcycle.glb'),
        ('models/Textures/colormap.png', 'kenney_racing/Textures/colormap.png'),
        ('README.md', 'kenney_racing/README.md'),
    ]),
    ('0xKoller/starter-kit-racing-studio', None, [
        ('kenney_car-kit/License.txt', 'kenney_carkit/License.txt'),
        ('kenney_car-kit/Models/OBJ format/Textures/colormap.png', 'kenney_carkit/Textures/colormap.png'),
    ] + [('kenney_car-kit/Models/OBJ format/%s.%s' % (n, e), 'kenney_carkit/%s.%s' % (n, e))
         for n in ('debris-spoiler-a', 'debris-spoiler-b', 'debris-bumper', 'wheel-racing', 'wheel-dark',
                   'wheel-default', 'kart-oobi') for e in ('obj', 'mtl')]),
    ('chibifire-stages/quaternius-stage', None, [
        ('models/PublicTransport/S_Bicycle.usda', 'quat/S_Bicycle.usda'),
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
# автомобили с фототекстурой
# ---------------------------------------------------------------------------
GLASS = (46, 56, 66)        # стекло там, где у исходника был просто серый материал
DARK_INSIDE = (30, 30, 32)

# имя -> описание
#   parts    — какие детали исходника составляют кузов; wheels — колёса (или None: искать в кузове)
#   turn     — как повернуть исходник, чтобы нос смотрел на +Y: 'x+' — нос исходника смотрит на +X, …
#   width    — настоящая ширина кузова, м (по ней ставится масштаб)
#   paint    — правило «что здесь краска» (по цвету точек текстуры, занятых кузовом):
#                hue, sat, val — оттенок от и до, насыщенность от и до, яркость от (кузов своего цвета);
#                white=(насыщенность до, яркость от) — ещё и белёсое (иней на капоте и крыше);
#                tint=(насыщенность до, яркость от) — всё, кроме тёмного и ярко-цветного (белый кузов);
#                keep=[(x0, y0, x1, y1), …] — прямоугольники текстуры 256x256, где краски нет (стёкла, фары)
#   flat     — материалы без текстуры: имя -> цвет (None — грани убрать)
#   head/tail — высота фар и задних фонарей в долях высоты кузова, и разнос в долях полуширины
CARS = {
    # купе боggle: белёсая текстура 128 точек, кузов красится (правило «белёсое»)
    'coupe': dict(
        file=('boggle_coupe', '2_seater_coupe.obj'), tex=('boggle_coupe', 'textures', 'crystal_white.png'),
        parts=('2_seater_coupe',), wheels=('_wheel0', '_wheel1', '_wheel2', '_wheel3'),
        wheel_file=('boggle_coupe', 'wheel.obj'),
        wheel_hubs_raw=((0.63, 0.473, 1.22), (-0.63, 0.473, 1.22), (0.63, 0.473, -1.20), (-0.63, 0.473, -1.20)),
        yup=True, turn='y+', width=1.72,
        paint=dict(tint=(0.30, 0.62)),
        flat={},
        head=(0.55, 0.70), tail=(0.60, 0.72)),
    # Volkswagen Golf Mk2 GTI, красная «заводская» окраска (фиксированная, стёкла не трогаем)
    'golf': dict(
        file=('designersoup_golf', 'red_golf.obj'), tex=('designersoup_golf', 'pixel_art_golf_final.png'),
        parts=('baseShape',), wheels=('lRWheel', 'rRWheel', 'lFWheel', 'lFWheel.001'),
        yup=True, turn='y+', width=1.80, fixed=True, flat={},
        head=(0.42, 0.72), tail=(0.46, 0.70)),
    # «Подозрительная машина»: body красится по Color Mask (красный — кузов, чёрный — стёкла и хром)
    'phantom': dict(
        file=('moidev_suspicious', 'Suspicious Car.obj'), tex=('moidev_suspicious', 'Texture Black.png'),
        parts=('Body_Cube.001',),
        wheels=('Wheel_FR_Cylinder', 'Wheels_RL_Cylinder.001', 'Wheels_FL_Cylinder.002', 'Wheels_RR_Cylinder.003'),
        mask_file=('moidev_suspicious', 'Color Mask.png'), mask_min=0.05,
        yup=True, turn='y+', width=1.82, flat={},
        head=(0.44, 0.70), tail=(0.48, 0.72)),
    # «Классик»: машина главного героя (bricchi-games): маска покраски из перепаковки автора
    'classic': dict(
        file=('bricchi_retro', 'retro-car.glb'), tex=('bricchi_retro', 'car-paint-base.jpg'),
        parts=('Car_Base', 'car_hood', 'trunk', 'R_Door_Front', 'R_Door_Back', 'L_Door_Front', 'L_Door_Back',
               'Car_Base.011'),
        wheels=('R_Tire_Front', 'L_Tire_front', 'R_Tire_Back', 'L_Tire_Back'),
        mask_file=('bricchi_retro', 'car-paint-mask.png'), mask_min=0.30,
        yup=True, turn='y+', width=1.80, flat={},
        head=(0.50, 0.70), tail=(0.55, 0.72)),
    # такси MoiDev: текстура как есть (жёлтый кузов с «шашечками»), не перекрашивается
    'cab': dict(
        file=('moidev_taxi', 'scene.gltf'), tex=('moidev_taxi', 'textures', 'Taxi_baseColor.png'),
        parts=('Object_4', 'Object_6'), wheels=('Object_8', 'Object_10', 'Object_12', 'Object_14'),
        yup=True, turn='y+', width=1.86, fixed=True, flat={},
        head=(0.47, 0.74), tail=(0.50, 0.80)),
}
TEX_SIZE = 256


def _turn(parts, how):
    """Повернуть вокруг вертикали так, чтобы нос смотрел на +Y."""
    m = {'y+': np.eye(3), 'y-': np.array([[-1.0, 0, 0], [0, -1.0, 0], [0, 0, 1.0]]),
         'x+': np.array([[0, -1.0, 0], [1.0, 0, 0], [0, 0, 1.0]]),
         'x-': np.array([[0, 1.0, 0], [-1.0, 0, 0], [0, 0, 1.0]])}[how]
    for p in parts:
        p.transform(m)


def car_texture(name, d, body, wheels, flat_uv):
    """Фототекстура -> два слоя, как у остальных машин: <имя>.png (RGBA: всё, что не красится; на месте
    краски — прозрачно) и <имя>_shade.png (светотень краски).  Краска находится по цвету: у каждого кузова
    он свой, а стёкла, шины, хром, ржавчина и грязь от него отличаются.  Для машин с готовой маской
    (mask_file, белый/яркий = кузов) правило по цвету не нужно: маска старше любого эвристического правила."""
    from PIL import Image
    img = Image.open(src(*d['tex'])).convert('RGB')
    if d.get('fixed'):
        # текстура идёт как есть: её рисовали точка в точку, и сглаживание при пересчёте размера её портит
        if img.size != (TEX_SIZE, TEX_SIZE):
            img = img.resize((TEX_SIZE, TEX_SIZE), Image.NEAREST)
        img.save(os.path.join(VEH, name + '.png'), optimize=True)
        return 0.0
    img = img.resize((TEX_SIZE, TEX_SIZE), Image.LANCZOS)
    a = np.asarray(img).copy()
    # гладкие материалы (стекло): закрашиваем квадратик в свободном углу, грани смотрят в него
    for (u, v), col in flat_uv:
        x, y = int(u * TEX_SIZE), int((1.0 - v) * TEX_SIZE)
        a[y - 4:y + 4, x - 4:x + 4] = col
    used = uv_mask(body, TEX_SIZE)
    if d.get('mask_file'):
        # готовая маска покраски: яркое = кузов, чёрное = стёкла/хром/шины
        mimg = Image.open(src(*d['mask_file'])).convert('L').resize((TEX_SIZE, TEX_SIZE), Image.LANCZOS)
        m = np.asarray(mimg).astype(np.float64) > float(d.get('mask_min', 0.5)) * 255.0
        m &= dilate(used, 2)
        m &= ~uv_mask(wheels, TEX_SIZE)
    else:
        h, s, v = hsv(a)
        rule = d['paint']
        m = np.zeros(h.shape, dtype=bool)
        if 'hue' in rule:
            h0, h1 = rule['hue']
            m |= (h >= h0) & (h <= h1) & (s >= rule['sat'][0]) & (s <= rule['sat'][1]) & (v >= rule['val'])
        if 'white' in rule:
            m |= (s <= rule['white'][0]) & (v >= rule['white'][1])
        if 'tint' in rule:
            m |= (s <= rule['tint'][0]) & (v >= rule['tint'][1])
        for (x0, y0, x1, y1) in rule.get('keep', ()):
            m[y0:y1 + 1, x0:x1 + 1] = False
        m &= dilate(used, 2)
        m &= ~uv_mask(wheels, TEX_SIZE)
    for (u, vv), col in flat_uv:
        x, y = int(u * TEX_SIZE), int((1.0 - vv) * TEX_SIZE)
        m[y - 5:y + 5, x - 5:x + 5] = False
    # одиночные точки краски среди деталей и дырки в краске убираем
    m = dilate(erode(m, 1), 1) | (m & erode(dilate(m, 2), 2) & dilate(erode(m, 1), 2))
    L = lum(a.astype(np.float64))
    ref = float(np.median(L[m])) if m.any() else 128.0
    shade = np.where(m, np.clip(L / ref * 127.5, 0, 255), 128.0)
    rgba = np.zeros((TEX_SIZE, TEX_SIZE, 4), np.uint8)
    rgba[..., :3] = np.where(m[..., None], shade[..., None], a).astype(np.uint8)
    rgba[..., 3] = np.where(m, 0, 255)
    Image.fromarray(rgba, 'RGBA').save(os.path.join(VEH, name + '.png'), optimize=True)
    Image.fromarray(shade.astype(np.uint8), 'L').save(os.path.join(VEH, name + '_shade.png'), optimize=True)
    return float(m.sum()) / max(1.0, float(np.asarray(used, dtype=bool).sum()))


def free_spot(parts, size=TEX_SIZE, block=14):
    """Свободное место на текстуре (не занятое развёрткой) под квадратики гладких материалов."""
    used = dilate(uv_mask(parts, size), 2)
    spots = []
    for y in range(block, size - block, block):
        for x in range(block, size - block, block):
            if not used[y - block // 2:y + block // 2, x - block // 2:x + block // 2].any():
                spots.append(((x + 0.5) / size, 1.0 - (y + 0.5) / size))
    return spots


def _fbx_to_glb(fbx):
    """FBX -> GLB рядом с исходником (нужен Node.js с npm)."""
    glb = fbx[:-4] + '.glb'
    if os.path.isfile(glb):
        return
    import platform
    npm_dir = os.path.join(SRC, 'npm')
    plat = {'Linux': 'Linux', 'Darwin': 'Darwin', 'Windows': 'Windows_NT'}[platform.system()]
    exe = os.path.join(npm_dir, 'node_modules', 'fbx2gltf', 'bin', plat, 'FBX2glTF')
    if not os.path.isfile(exe):
        subprocess.check_call(['npm', 'install', '--prefix', npm_dir, 'fbx2gltf@0.9.7-p1'])
    subprocess.check_call([exe, fbx, '--binary', '--output', glb])


def convert_car(name, d):
    from panda3d.core import NodePath
    _panda()
    src_file = src(*d['file'])
    if d['file'][-1].endswith('.glb') and not os.path.isfile(src_file):
        fbx = src_file[:-4] + '.fbx'                  # автор выложил только .FBX: конвертируем
        if os.path.isfile(fbx):
            _fbx_to_glb(fbx)
    allp = named(ms.read(src_file))
    if d.get('wheel_file'):
        # колесо одно на все четыре: ставим его копии в системе координат исходника
        one = named(ms.read(src(*d['wheel_file'])))
        base_wheel = list(one.values())[0]
        for k, (hx, hy, hz) in enumerate(d['wheel_hubs_raw']):
            q = base_wheel.copy('_wheel%d' % k)
            q.verts = q.verts + np.array([hx, hy, hz], dtype=np.float64)
            allp['_wheel%d' % k] = q
    if d.get('yup'):                                # у glTF вверх смотрит Y, нос — на +Z
        for p in allp.values():
            p.transform(YUP)
    body = [allp[n].copy() for n in d['parts']]
    wheels = [allp[n].copy() for n in d['wheels']] if d.get('wheels') else []
    if d.get('mirror'):
        body = body + [p.copy(p.name + '_m').transform(np.diag([-1.0, 1.0, 1.0])) for p in body]
    _turn(body + wheels, d['turn'])
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
    cx = (pts[:, 0].max() + pts[:, 0].min()) * 0.5
    cy = (pts[:, 1].max() + pts[:, 1].min()) * 0.5
    z0 = min(tri_points(w)[:, 2].min() for w in wheels)
    for p in body + wheels:
        p.verts = (p.verts - (cx, cy, z0)) * k
    pts = np.concatenate([tri_points(p) for p in body])
    # гладкие материалы: их грани на картинку не опираются (развёртка у них от других текстур набора)
    skin = [p.select([p.mats[m] not in d['flat'] for m in p.mat]) for p in body]
    spots = free_spot(skin + wheels)
    flat_uv = []
    out = Out()
    dropped = 0
    for p in body:
        for i in range(len(p.tris)):
            mat = p.mats[p.mat[i]]
            if mat in d['flat']:
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
    share = car_texture(name, d, skin, wheels, flat_uv)
    root = NodePath('car')
    b = root.attachNewNode('body')
    b.attachNewNode(out.node('skin'))
    info = dict(W=round(float(pts[:, 0].max() - pts[:, 0].min()), 3), L=round(float(pts[:, 1].max() - pts[:, 1].min()), 3),
                H=round(float(pts[:, 2].max()), 3), tex=True, wheels=[])
    if d.get('fixed'):
        info['fixed'] = True
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
    print('  %-7s Ш %.2f  Д %.2f  В %.2f  треугольников %d (убрано салона %d), колесо r %.2f, краски на кузове %d%%' % (
        name, info['W'], info['L'], info['H'], len(out), dropped, info['wheels'][0]['r'], round(share * 100)))
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
SEAT = (0.07, 0.06, 0.06)
STEEL = (0.70, 0.71, 0.74)
LAMP = (1.0, 0.96, 0.82)
RED = (0.78, 0.08, 0.06)
YUP = np.array([[-1.0, 0, 0], [0, 0, 1.0], [0, 1.0, 0]])        # (x, y, z) -> (-x, z, y): Y вверх -> Z вверх
YUP_BACK = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])   # то же, но нос исходника смотрел на -Z


def poses():
    sys.path.insert(0, ROOT)
    from game import bikes
    return bikes.POSES, bikes.PELVIS_UP, bikes.SOLE


def fit_rider(seat_z, seat_y, grips, prefer):
    """Подобрать посадку: какая из готовых поз ездока ближе всего к модели.

    seat_z — высота поверхности седла, seat_y — (от, до) где на нём можно сидеть, grips — (y, z) ручек руля.
    Возвращает (имя позы, y таза, z таза, на сколько сдвинуть ручки: (dy, dz))."""
    P, up, sole = poses()
    best = None
    for name in prefer:
        fwd, hup = P[name]['hand']
        pz = seat_z + up
        py = min(seat_y[1], max(seat_y[0], grips[0] - 0.06 - fwd))
        dy = py + 0.06 + fwd - grips[0]
        dz = pz + hup - 0.02 - grips[1]
        err = abs(dy) + abs(dz)
        if best is None or err < best[0] - 0.03:        # при почти равных — та, что названа раньше
            best = (err, name, py, pz, (dy, dz))
    return best[1:]


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


def bike_moto():
    """Мотоцикл Kenney (Starter Kit Racing): круизер.  У исходника «игрушечные» пропорции — очень широкие
    шины и руль; приводим к настоящим: шины 15 и 19 см, руль 76 см.  Сам руль — рога толщиной 12 см с
    ручками по 20 см — заменяем трубой с ручками настоящей толщины."""
    from PIL import Image
    parts, _ = ms.read_glb(src('kenney_racing', 'vehicle-motorcycle.glb'))
    pal = np.asarray(Image.open(src('kenney_racing', 'Textures', 'colormap.png')).convert('RGB'))
    ph, pw = pal.shape[:2]
    P = named(parts)
    for p in P.values():
        p.transform(YUP)
    R = 0.32                                            # радиус колеса в игре
    k = R / 0.30

    def color(p, i):
        uv = p.uvs[i].mean(0)
        c = pal[min(ph - 1, max(0, int((1.0 - uv[1]) * ph))), min(pw - 1, max(0, int(uv[0] * pw)))].astype(int)
        return c

    def kind(c):
        r, g, bl = c
        mx, mn = max(c), min(c)
        if mx < 90:
            return 'dark'
        if g > r + 40 and g > bl + 15:
            return 'paint'
        if r > 200 and g < 180 and bl < 120:
            return 'red'
        if mx > 220 and mx - mn < 30:
            return 'lamp'
        return 'metal'

    def flat(c, what):
        if what == 'dark':
            return DARK
        if what == 'red':
            return RED
        if what == 'lamp':
            return LAMP
        if what == 'paint':                              # белый с той же светотенью, что на палитре
            s = float(lum(c.astype(np.float64))) / 104.0
            return (min(1.0, s), min(1.0, s), min(1.0, s))
        g = float(lum(c.astype(np.float64))) / 255.0 * 1.04
        return (min(1.0, g * 0.98), min(1.0, g * 0.985), min(1.0, g))
    fy, ry = 0.86, -0.66                                # оси колёс исходника
    mid = (fy + ry) * 0.5
    b = Bike('moto')
    # --- колёса: уже и строго круглые; зелёные «колпаки» — в цвет металла
    for name, node, cy, width in (('wheel-front', 'wheel_f', fy, 0.15), ('wheel-back', 'wheel_r', ry, 0.19)):
        p = P[name]
        kx = width / (0.45 * k)
        o = b.out(node)
        for i in range(len(p.tris)):
            c = color(p, i)
            what = kind(c)
            col = flat(c, 'metal' if what == 'paint' else what)
            pts = (p.verts[p.tris[i]] - (0.0, cy, 0.30)) * (k * kx, k, k)
            o.tri(pts, color=col)
    # --- кузов
    body = P['body']
    BX = 0.86                                           # кузов чуть уже: двигатель с трубами был шире руля
    seat_top = None
    seat_y = [1e9, -1e9]
    tail = []
    for i in range(len(body.tris)):
        c = color(body, i)
        what = kind(c)
        pts = (body.verts[body.tris[i]] - (0.0, mid, 0.0)) * (k * BX, k, k)
        b.out('paint' if what == 'paint' else 'body').tri(pts, color=flat(c, what))
        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        if what == 'dark' and n[2] > 0.5 * np.linalg.norm(n) and pts[:, 2].max() > 0.7 * k:
            seat_top = max(seat_top or 0.0, float(pts[:, 2].max()))
            seat_y = [min(seat_y[0], float(pts[:, 1].min())), max(seat_y[1], float(pts[:, 1].max()))]
        if what == 'red':
            tail.append(pts.mean(0))
    # --- вилка: руль уже; ручки — к рукам ездока
    fork = P['fork']
    FX = 0.73
    fpts = (fork.verts - (0.0, mid, 0.0)) * (k * FX, k, k)
    grip = []
    gidx = set()
    head = []
    kinds = []
    for i in range(len(fork.tris)):
        c = color(fork, i)
        what = kind(c)
        kinds.append((what, c))
        if what == 'dark' and fpts[fork.tris[i]][:, 2].min() > 1.0 * k:
            grip.append(fpts[fork.tris[i]])
            gidx.update(int(j) for j in fork.tris[i])
        if what == 'lamp':
            head.append(fpts[fork.tris[i]].mean(0))
    grip = np.concatenate(grip)
    gy, gz = float(grip[:, 1].mean()), float(grip[:, 2].mean())
    gx = float(np.abs(grip[:, 0]).mean())
    pose, py, pz, (dy, dz) = fit_rider(seat_top, (seat_y[0] + 0.14, seat_y[1] - 0.06), (gy, gz), ('chair', 'cruise'))
    z1 = float(grip[:, 2].min())
    fpts = bend(fpts, z1 - 0.30, z1, dy, dz)
    axle_f = (fy - mid) * k
    # --- руль.  У исходника это два висящих над траверсой «рога» с ручками-бочонками: кисти ездока в них тонут.
    #     Находим ось каждой ручки, выбрасываем всё, что лежит вдоль неё, и ставим трубу со стойками от траверсы
    gidx = np.array(sorted(gidx))
    drop = np.zeros(len(fork.tris), bool)
    bars = []
    for side in (-1.0, 1.0):
        q = fpts[gidx[fpts[gidx, 0] * side > 0.0]]
        q = np.unique(np.round(q, 4), axis=0)
        q = q[np.argsort(q[:, 0] * side)]
        cin, cout = q[:len(q) // 2].mean(0), q[len(q) // 2:].mean(0)
        ax = cout - cin
        ax /= np.linalg.norm(ax)
        rel = fpts - cin
        t = rel @ ax
        far = np.linalg.norm(rel - np.outer(t, ax), axis=1)
        rad = float(far[gidx[fpts[gidx, 0] * side > 0.0]].max())
        along = (far < rad * 1.12) & (t > -0.30) & (fpts[:, 0] * side > 0.0)
        drop |= along[fork.tris].all(axis=1)
        bars.append((side, (cin + cout) * 0.5, ax))
    assert 40 <= int(drop.sum()) <= 120, drop.sum()
    left = fpts[fork.tris[~drop]]
    BAR_R, GRIP_R, GRIP_L = 0.019, 0.029, 0.135
    o = b.out('fork')
    off = np.array((0.0, axle_f, 0.0))
    yoke = None
    for side, palm, ax in bars:
        g0, g1 = palm - ax * GRIP_L * 0.5, palm + ax * GRIP_L * 0.5
        elbow = palm - ax * 0.20
        cy = palm[1] + 0.22                              # стойка — на верхней грани траверсы
        cz = top_z(left, side * 0.085, cy)
        assert cz is not None and palm[2] - 0.22 < cz < palm[2] - 0.05, cz
        clamp = np.array((side * 0.085, cy, cz - 0.012))
        yoke = (float(cy), float(cz))                    # верх вилки: через него идёт ось поворота руля
        up = (elbow - clamp) / np.linalg.norm(elbow - clamp)
        o.tube(clamp - off, elbow + up * BAR_R * 0.6 - off, BAR_R, STEEL, 6)
        o.tube(elbow - ax * BAR_R * 0.6 - off, g0 - off, BAR_R, STEEL, 6)
        o.tube(g0 - off, g1 - off, GRIP_R, DARK, 6)
        o.tube(g1 - off, g1 + ax * 0.012 - off, GRIP_R + 0.004, STEEL, 6)            # заглушка-грузик
        fwd = np.cross((0.0, 0.0, 1.0), ax) * side       # рычаг тормоза (сцепления) перед ручкой
        fwd /= np.linalg.norm(fwd)
        o.tube(g0 - ax * 0.02 + fwd * 0.012 - off, g0 + ax * 0.012 + fwd * 0.05 - off, 0.009, STEEL, 4)
        o.tube(g0 + ax * 0.012 + fwd * 0.05 - off, g0 + ax * 0.125 + fwd * 0.058 - off, 0.008, STEEL, 4)
    for i in range(len(fork.tris)):
        if drop[i]:
            continue
        what, c = kinds[i]
        pts = fpts[fork.tris[i]] - (0.0, axle_f, 0.0)
        b.out('fork_paint' if what == 'paint' else 'fork').tri(pts, color=flat(c, what))
    POS, up, sole = poses()
    fx, ff, fu = POS[pose]['foot']
    foot = (fx, py + ff, pz + fu - sole)
    _pegs(b, foot)
    allp = np.concatenate([np.array([r[0] for r in o.rows]) for nd in ('body', 'paint') for o in b.nodes[nd].values()])
    fk = np.concatenate([np.array([r[0] for r in o.rows]) for nd in ('fork', 'fork_paint') for o in b.nodes[nd].values()])
    b.info.update(
        wheel_f=[round(axle_f, 3), R, 0.15], wheel_r=[round((ry - mid) * k, 3), R, 0.19],
        pose=pose, seat=[round(py, 3), round(pz, 3)], grips=[round(gx, 3), round(gy + dy, 3), round(gz + dz, 3)],
        foot=[round(v, 3) for v in foot], seat_top=round(seat_top, 3), seat_y=[round(seat_y[0], 3), round(seat_y[1], 3)],
        head=[0.0, round(float(np.mean([h[1] for h in head])) + 0.03, 3), round(float(np.mean([h[2] for h in head])), 3)],
        tail=[0.0, round(float(np.mean([t[1] for t in tail])) - 0.03, 3), round(float(np.mean([t[2] for t in tail])), 3)],
        L=round(float(max(allp[:, 1].max(), fk[:, 1].max() + axle_f) - allp[:, 1].min()), 3),
        y0=round(float(allp[:, 1].min()), 3), y1=round(float(max(allp[:, 1].max(), fk[:, 1].max() + axle_f)), 3),
        W=round(float(np.abs(fk[:, 0]).max() * 2.0), 3), H=round(float(fk[:, 2].max()), 3), bend=[round(dy, 3), round(dz, 3)],
        axis=[round(yoke[0], 3), round(yoke[1], 3)])
    return b.write()


def _saddle(b, y, z, k=1.0):
    """Седло велосипеда — из набора Quaternius (у городского велосипеда исходник без седла)."""
    parts = named(ms.read(src('quat', 'S_Bicycle.usda')))
    p = parts['Mesh'].copy()
    p.transform(YUP_BACK)
    lo, hi = p.bounds()
    s = 0.29 * k / (hi[1] - lo[1])                     # длина седла 29 см
    c = np.array(((lo[0] + hi[0]) * 0.5, (lo[1] + hi[1]) * 0.5, hi[2]))
    b.out('body').part(p, color=SEAT, uv=False, xf=lambda q: (q - c) * s + (0.0, y, z))
    return s * (hi[2] - lo[2])


def _pedals(b, bb, foot):
    """Шатуны с педалями: от каретки к стопам ездока."""
    o = b.out('body')
    fx, fy, fz = foot
    d = np.array((fy - bb[0], fz - bb[1]))
    ln = float(np.linalg.norm(d))
    d = d / ln * min(ln, 0.175)                         # шатун — 17,5 см
    py, pz = bb[0] + d[0], bb[1] + d[1]
    o.tube((-0.09, bb[0], bb[1]), (0.09, bb[0], bb[1]), 0.016, STEEL, 4)
    for sx in (-1, 1):
        o.tube((sx * 0.09, bb[0], bb[1]), (sx * 0.09, py, pz), 0.012, STEEL, 4)
        o.box(sx * 0.09 + (0.0 if sx > 0 else -0.10), py - 0.045, pz - 0.022, sx * 0.09 + (0.10 if sx > 0 else 0.0), py + 0.045, pz - 0.002, DARK)
    return (max(fx, 0.14), py, pz)


def bike_cycle():
    """Городской велосипед из сборника M3 (bike_vintage): рама красится, хром и колёса со своей текстурой."""
    from PIL import Image
    P = named(ms.read(src('m3', 'bike_vintage.blend')))
    img = Image.open(src('m3', 'bike_vintage.png')).convert('RGBA').resize((256, 256), Image.LANCZOS)
    img.save(os.path.join(VEH, 'b_cycle.png'), optimize=True)
    R = 0.34                                            # колесо исходника — в самый раз
    z0 = -0.34                                          # земля в исходнике
    fy, ry = 1.17, 0.0
    mid = (fy + ry) * 0.5
    off = np.array((0.0, mid, z0))
    b = Bike('cycle')
    for p in P.values():
        p.verts = p.verts - off
    for name, node, cy in (('bike_vintage_wheel.001', 'wheel_f', fy - mid), ('bike_vintage_wheel.000', 'wheel_r', ry - mid)):
        p = P[name]
        b.out(node, 't').part(p, xf=lambda q, cy=cy: q - (0.0, cy, R))
    # что поворачивается вместе с рулём: передние перья и крыло (куски рамы впереди), вынос и руль (хром)
    frame, chrome = P['bike_vintage_frame'], P['bike_vintage_chrome']
    head_y = 1.0 - mid                                  # ось рулевой колонки по длине
    fork_f, body_f = [], []
    for comp in components(frame):
        v = tri_points(frame, comp)
        (fork_f if v[:, 1].min() > head_y + 0.02 - 0.22 and v[:, 1].max() > fy - mid - 0.2 else body_f).extend(comp)
    fork_c, body_c = [], []
    for comp in components(chrome):
        v = tri_points(chrome, comp)
        (fork_c if v[:, 1].mean() > 0.2 else body_c).extend(comp)
    grip = np.concatenate([chrome.verts[chrome.tris[i]] for i in fork_c if np.abs(chrome.verts[chrome.tris[i]][:, 0]).min() > 0.16])
    gy, gz, gx = float(grip[:, 1].mean()), float(grip[:, 2].mean()), float(np.abs(grip[:, 0]).mean())
    post = tri_points(chrome, body_c)                   # верх подседельной трубы
    post_y, post_z = float(post[:, 1].mean()), float(post[:, 2].max())
    seat_top = post_z + 0.075
    pose, py, pz, (dy, dz) = fit_rider(seat_top, (post_y - 0.02, post_y + 0.10), (gy, gz), ('std', 'cruise'))
    axle_f = fy - mid
    z1 = float(grip[:, 2].min())
    cv = bend(chrome.verts, z1 - 0.22, z1, dy, dz)
    for i in fork_c:
        b.out('fork', 't').tri(cv[chrome.tris[i]] - (0.0, axle_f, 0.0), chrome.uvs[i])
    for i in body_c:
        b.out('body', 't').tri(chrome.verts[chrome.tris[i]], chrome.uvs[i])
    for i in fork_f:
        b.out('fork_paint').tri(frame.verts[frame.tris[i]] - (0.0, axle_f, 0.0))
    for i in body_f:
        b.out('paint').tri(frame.verts[frame.tris[i]])
    b.out('body', 't').part(P['bike_vintage_gears'])
    # седло (его в исходнике нет) и стойка под ним, педали
    th = _saddle(b, py - 0.03, seat_top)
    b.out('body').tube((0.0, post_y, post_z - 0.02), (0.0, py - 0.03, seat_top - th * 0.6), 0.014, STEEL, 5)
    gears = tri_points(P['bike_vintage_gears'], components(P['bike_vintage_gears'])[0])
    bb = (float(gears[:, 1].mean()), float(gears[:, 2].mean()))
    POS, up, sole = poses()
    fx, ff, fu = POS[pose]['foot']
    foot = _pedals(b, bb, (fx, py + ff, pz + fu - sole))
    allp = np.concatenate([frame.verts, chrome.verts])
    b.info.update(
        wheel_f=[round(axle_f, 3), R, 0.04], wheel_r=[round(ry - mid, 3), R, 0.04], tex='b_cycle',
        pose=pose, seat=[round(py, 3), round(pz, 3)], grips=[round(gx, 3), round(gy + dy, 3), round(gz + dz, 3)],
        foot=[round(v, 3) for v in foot], seat_top=round(seat_top, 3), bend=[round(dy, 3), round(dz, 3)],
        L=round(float(R * 2 + fy - ry), 3), y0=round(float(ry - mid - R), 3), y1=round(float(fy - mid + R), 3),
        W=round(gx * 2 + 0.1, 3), H=round(float(max(gz + dz, seat_top) + 0.06), 3))
    return b.write()


def bike_bmx():
    """Второй велосипед — Quaternius (Public Transport): колёса меньше, руль выше — «трюковой»."""
    P = named(ms.read(src('quat', 'S_Bicycle.usda')))
    for p in P.values():
        p.transform(YUP_BACK)
    R = 0.26
    k = R / 0.95
    fy, ry = 1.68, -2.25
    mid = (fy + ry) * 0.5
    b = Bike('bmx')
    for p in P.values():
        p.verts = (p.verts - (0.0, mid, -0.95)) * k
    fy, ry = (fy - mid) * k, (ry - mid) * k
    for name, node, cy in (('Cylinder_002', 'wheel_f', fy), ('Cylinder_001', 'wheel_r', ry)):
        p = P[name]
        # шина тёмная, обод и втулка — металл: что дальше 80 % радиуса от оси, то шина
        cols = []
        for t in p.tris:
            c = p.verts[t].mean(0)
            cols.append(DARK if math.hypot(c[1] - cy, c[2] - R) > R * 0.80 else STEEL)
        b.out(node).part(p, colors=cols, uv=False, xf=lambda q, cy=cy: q - (0.0, cy, R))
    fork = P['Cube_000']
    handle = fork.mat == fork.mats.index('Handle')
    grip = fork.verts[np.unique(fork.tris[handle])]
    gy, gz, gx = float(grip[:, 1].mean()), float(grip[:, 2].mean()), float(np.abs(grip[:, 0]).max()) - 0.05
    sad = P['Mesh']
    lo, hi = sad.bounds()
    seat_top = float(hi[2])
    pose, py, pz, (dy, dz) = fit_rider(seat_top, (float(lo[1]) + 0.10, float(hi[1]) - 0.06), (gy, gz), ('std', 'cruise'))
    z1 = float(grip[:, 2].min())
    fv = bend(fork.verts, z1 - 0.16, z1, dy, dz)
    # руль уже: у исходника он полтора метра в пересчёте на рост
    bar = 0.31 / (float(np.abs(grip[:, 0]).max()))
    fv[:, 0] = np.where(fv[:, 2] > z1 - 0.02, fv[:, 0] * bar, fv[:, 0])
    gx = float(np.abs(grip[:, 0]).max()) * bar - 0.05
    for i in range(len(fork.tris)):
        pts = fv[fork.tris[i]] - (0.0, fy, 0.0)
        if handle[i]:
            b.out('fork').tri(pts, color=DARK)
        else:
            b.out('fork_paint').tri(pts)
    b.out('paint').part(P['Cube_005'], uv=False)
    b.out('body').part(sad, color=SEAT, uv=False)
    # каретка — нижняя точка рамы между колёсами
    fr = P['Cube_005'].verts
    low = fr[(np.abs(fr[:, 1]) < 0.25)]
    bb = (float(low[low[:, 2] < low[:, 2].min() + 0.05][:, 1].mean()), float(low[:, 2].min()) + 0.03)
    POS, up, sole = poses()
    fx, ff, fu = POS[pose]['foot']
    foot = _pedals(b, bb, (fx, py + ff, pz + fu - sole))
    b.info.update(
        wheel_f=[round(fy, 3), R, 0.07], wheel_r=[round(ry, 3), R, 0.07],
        pose=pose, seat=[round(py, 3), round(pz, 3)], grips=[round(gx, 3), round(gy + dy, 3), round(gz + dz, 3)],
        foot=[round(v, 3) for v in foot], seat_top=round(seat_top, 3), bend=[round(dy, 3), round(dz, 3)],
        L=round(float(R * 2 + fy - ry), 3), y0=round(float(ry - R), 3), y1=round(float(fy + R), 3),
        W=round(gx * 2 + 0.1, 3), H=round(float(max(gz + dz, seat_top) + 0.06), 3))
    return b.write()


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


BIKES = {'moto': bike_moto, 'cycle': bike_cycle, 'bmx': bike_bmx, 'chop': bike_chop}


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
