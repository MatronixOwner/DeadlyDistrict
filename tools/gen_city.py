# -*- coding: utf-8 -*-
"""Текстуры города из фотоматериалов: стены, окна, двери, асфальт, крыши.

Раньше весь город был нарисован кодом в разрешении 64 точки на секцию фасада — отсюда «мыло»
и кирпичи размером с подушку.  Здесь те же текстуры (с теми же именами) собираются заново,
вчетверо подробнее, из фотографий настоящих материалов в стиле игр конца 90-х:

  * стены, окна и двери — библиотека Classic64 (Craig Snedeker, CC0) из сборника
    github.com/M3-org/retro3d-assets;
  * разметка дорог, стеклянные фасады, витрины и вывески дорисовываются кодом.

    python tools/gen_city.py fetch      # скачать исходные материалы в .cache/model_src/m3 (git)
    python tools/gen_city.py            # собрать текстуры в assets/tex
    python tools/gen_city.py --sheet out.png

Список собранных файлов пишется в assets/tex/_photo.json: tools/gen_textures.py эти имена не трогает.
Игре исходники не нужны — она читает готовые PNG.
"""
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, '.cache', 'model_src', 'm3')
OUT = os.path.join(ROOT, 'assets', 'tex')
MANIFEST = os.path.join(OUT, '_photo.json')
REPO = 'https://github.com/M3-org/retro3d-assets'
FOLDERS = ['Bricks', 'Concrete', 'Doors', 'Windows', 'Walls', 'Roof', 'Road', 'Ground', 'Metal', 'Tiles', 'Wood',
           'Industrial', 'Misc', 'Nature']

BAY_W, FLOOR_H, GF_H = 3.5, 3.2, 4.0            # как в game/city.py
T = 256                                         # точек на секцию фасада
written = []
windows = {}                                    # имя фасада -> окна (в долях секции), для ночных огней


# ---------------------------------------------------------------------------
# инструменты
# ---------------------------------------------------------------------------
def fetch():
    if os.path.isdir(os.path.join(SRC, 'Bricks')):
        return
    os.makedirs(os.path.dirname(SRC), exist_ok=True)
    subprocess.check_call(['git', 'clone', '-q', '--filter=blob:none', '--no-checkout', '--depth', '1', REPO, SRC])
    subprocess.check_call(['git', 'sparse-checkout', 'init', '--no-cone'], cwd=SRC)
    subprocess.check_call(['git', 'sparse-checkout', 'set'] + ['/%s/Materials/' % f for f in FOLDERS], cwd=SRC)
    subprocess.check_call(['git', 'checkout', '-q'], cwd=SRC)


_cache = {}


def src(name):
    """Исходная картинка: 'Bricks/brick_red_02.jpg' -> массив RGB (float)."""
    a = _cache.get(name)
    if a is None:
        folder, fname = name.split('/')
        a = np.asarray(Image.open(os.path.join(SRC, folder, 'Materials', fname)).convert('RGB'), np.float32)
        _cache[name] = a
    return a.copy()


def img(a):
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')


def arr(im):
    return np.asarray(im.convert('RGB'), np.float32).copy()


def resize(a, w, h, how=Image.BICUBIC):
    return arr(img(a).resize((int(w), int(h)), how))


def tiled(a, w, h, nx, ny, how=Image.LANCZOS):
    """Материал, повторённый nx × ny раз на поле w × h (края стыкуются)."""
    tw, th = max(1, int(round(w / float(nx)))), max(1, int(round(h / float(ny))))
    t = resize(a, tw, th, how)
    big = np.tile(t, (int(ny) + 1, int(nx) + 1, 1))[:th * int(ny), :tw * int(nx)]
    if big.shape[0] != h or big.shape[1] != w:
        big = resize(big, w, h, Image.BILINEAR)
    return big


def tone(a, mul=(1.0, 1.0, 1.0), sat=1.0, add=0.0, contrast=1.0):
    g = (a[..., 0:1] * 0.30 + a[..., 1:2] * 0.59 + a[..., 2:3] * 0.11)
    a = g + (a - g) * sat
    m = a.mean()
    a = (a - m) * contrast + m
    return a * np.array(mul, np.float32) + add


def recolor(a, color, keep=0.35):
    """Перекрасить материал в заданный цвет, сохранив его фактуру."""
    g = (a[..., 0:1] * 0.30 + a[..., 1:2] * 0.59 + a[..., 2:3] * 0.11)
    g = g / max(1.0, float(g.mean()))
    c = np.array(color, np.float32)
    return (g * c) * (1.0 - keep) + (a / max(1.0, float(a.mean())) * c.mean() * 0.0 + g * c) * keep


def smooth_noise(w, h, seed, cells=6, octaves=3):
    """Плавный шум 0..1, который стыкуется по краям."""
    r = np.random.RandomState(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        n = cells * (2 ** o)
        g = r.rand(n, n).astype(np.float32)
        g = np.concatenate([g, g[:, :1]], 1)
        g = np.concatenate([g, g[:1, :]], 0)
        im = Image.fromarray((g * 255).astype(np.uint8)).resize((w + w // n, h + h // n), Image.BICUBIC)
        out += np.asarray(im, np.float32)[:h, :w] / 255.0 * amp
        tot += amp
        amp *= 0.5
    return out / tot


def box(a, x0, y0, x1, y1, color):
    a[int(round(y0)):int(round(y1)), int(round(x0)):int(round(x1))] = color


def shade(a, x0, y0, x1, y1, k):
    a[int(round(y0)):int(round(y1)), int(round(x0)):int(round(x1))] *= k


def paste(a, b, x0, y0):
    x0, y0 = int(round(x0)), int(round(y0))
    h, w = b.shape[:2]
    ya, xa = max(0, y0), max(0, x0)
    yb, xb = min(a.shape[0], y0 + h), min(a.shape[1], x0 + w)
    if yb > ya and xb > xa:
        a[ya:yb, xa:xb] = b[ya - y0:yb - y0, xa - x0:xb - x0]


def soft_shadow(a, x0, y0, x1, y1, r=5, k=0.55, dx=0, dy=0):
    """Мягкая тень вокруг прямоугольника — стена сразу выглядит объёмной."""
    h, w = a.shape[:2]
    m = Image.new('L', (w, h), 0)
    ImageDraw.Draw(m).rectangle([x0 + dx, y0 + dy, x1 + dx - 1, y1 + dy - 1], fill=255)
    m = np.asarray(m.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255.0
    a *= (1.0 - m[..., None] * (1.0 - k))


def streaks(a, seed, strength=0.22, x0=0, x1=None, y0=0):
    """Потёки грязи сверху вниз."""
    h, w = a.shape[:2]
    x1 = w if x1 is None else x1
    r = np.random.RandomState(seed)
    m = np.zeros((h, w), np.float32)
    for _ in range(int((x1 - x0) / 9)):
        x = r.randint(x0, x1)
        ww = r.randint(2, 7)
        ln = r.randint(h // 6, h - y0)
        col = np.linspace(1.0, 0.0, ln) ** 1.5 * r.uniform(0.3, 1.0)
        m[y0:y0 + ln, x:x + ww] = np.maximum(m[y0:y0 + ln, x:x + ww], col[:, None][:m[y0:y0 + ln, x:x + ww].shape[0]])
    m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
    a *= (1.0 - m[..., None] * strength)


def grime(a, seed, strength=0.18, cells=5):
    n = smooth_noise(a.shape[1], a.shape[0], seed, cells)
    a *= (1.0 - strength * n[..., None])


def save(a, name, colors=255, w=None, h=None):
    """Сохраняет текстуру с палитрой (как на приставках 90-х: и стиль выдержан, и файл втрое меньше)."""
    im = a if isinstance(a, Image.Image) else img(a)
    if w:
        im = im.resize((w, h), Image.LANCZOS)
    if colors and im.mode == 'RGB':
        im = im.quantize(colors, method=Image.MEDIANCUT, dither=Image.NONE)
    im.save(os.path.join(OUT, name + '.png'), optimize=True)
    written.append(name)
    return im


# ---------------------------------------------------------------------------
# материалы земли и стен
# ---------------------------------------------------------------------------
def asphalt(w, h, m_w, m_h, seed, dark=1.0):
    """Асфальт: зерно с фотографии + пятна, заплаты и трещины, чтобы плитка не повторялась на глаз."""
    a = tiled(src('Ground/gravel_05.png'), w, h, max(1, round(m_w / 0.8)), max(1, round(m_h / 0.8)))
    a = tone(a, mul=(0.60, 0.61, 0.66), sat=0.5, contrast=1.25) * dark
    n = smooth_noise(w, h, seed, 4, 4)
    a *= (0.86 + 0.26 * n[..., None])
    r = np.random.RandomState(seed + 3)
    im = img(a)
    d = ImageDraw.Draw(im)
    for _ in range(int(m_w * m_h / 9)):                 # трещины
        x, y = r.randint(0, w), r.randint(0, h)
        pts = [(x, y)]
        for _k in range(r.randint(3, 8)):
            x += r.randint(-w // 14, w // 14)
            y += r.randint(-h // 14, h // 14)
            pts.append((x, y))
        d.line(pts, fill=(34, 34, 38), width=1)
    a = arr(im)
    for _ in range(int(m_w * m_h / 14)):                # заплаты посветлее и потемнее
        x, y = r.randint(0, w - 8), r.randint(0, h - 8)
        ww, hh = r.randint(w // 16, w // 6), r.randint(h // 16, h // 6)
        a[y:y + hh, x:x + ww] *= r.choice([0.86, 0.9, 1.07])
    return a


def gen_ground():
    save(asphalt(256, 256, 6, 6, 1), 'asphalt')

    # тротуар: плиты 0.75 м, плитка текстуры — 3 м
    a = tiled(src('Concrete/concrete_tile_01.jpg'), 256, 256, 3, 3)       # плиты по полметра
    a = tone(a, mul=(0.80, 0.80, 0.79), sat=0.6, contrast=1.1)
    grime(a, 11, 0.16)
    save(a, 'sidewalk')

    a = tiled(src('Concrete/concrete_01.png'), 256, 256, 2, 2)
    a = tone(a, mul=(0.86, 0.86, 0.85), sat=0.4)
    grime(a, 12, 0.14)
    save(a, 'concrete')

    a = tiled(src('Bricks/brick_red_04.jpg'), 256, 256, 5, 5)          # глухие стены: 4 м на плитку
    grime(a, 13, 0.22)
    save(a, 'brick')

    a = tiled(src('Tiles/tile_clean_tan.png'), 256, 256, 4, 4)            # плитка на площадях
    a = tone(a, mul=(0.80, 0.76, 0.72), sat=0.8, contrast=1.3)
    grime(a, 14, 0.2)
    save(a, 'pavers')

    a = tiled(src('Ground/grass_02.png'), 256, 256, 3, 3)
    a = tone(a, mul=(0.82, 0.95, 0.74))
    n = smooth_noise(256, 256, 15, 4)
    a *= (0.84 + 0.3 * n[..., None])
    save(a, 'grass')

    a = tiled(src('Ground/dirt_0.png'), 256, 256, 3, 3)
    a = tone(a, mul=(1.05, 1.0, 0.92))
    grime(a, 16, 0.25)
    save(a, 'dirt')

    a = tiled(src('Ground/sand_02.png'), 256, 256, 2, 2)
    a = tone(a, mul=(1.06, 1.02, 0.92))
    n = smooth_noise(256, 256, 17, 5)
    a *= (0.92 + 0.14 * n[..., None])
    save(a, 'sand')

    a = tiled(src('Ground/gravel_02.png'), 256, 256, 4, 4)
    a = tone(a, mul=(1.5, 1.5, 1.52), sat=0.5)
    grime(a, 18, 0.2)
    save(a, 'roof_gravel')

    a = tiled(src('Concrete/concrete_13.png'), 256, 256, 2, 2)
    a = tone(a, mul=(0.40, 0.40, 0.43), contrast=1.6)
    for k in range(1, 4):                                              # швы рубероида
        shade(a, 0, k * 64 - 1, 256, k * 64 + 1, 0.72)
    grime(a, 19, 0.3)
    save(a, 'roof_tar')

    a = tiled(src('Roof/roof_old_2.png'), 256, 256, 6, 6)
    grime(a, 20, 0.2)
    save(a, 'roof_tiles')

    a = tiled(src('Wood/wood_planks_4.png'), 256, 256, 2, 2)
    save(a, 'wood')

    a = tiled(src('Roof/roof_metal_01.jpg'), 256, 256, 2, 2)
    a = tone(a, mul=(0.92, 0.94, 0.97), sat=0.3)
    streaks(a, 21, 0.2)
    save(a, 'corrugated')


def gen_roads():
    """Дороги: раскладка разметки берётся из tools/gen_textures.py, асфальт — подробный."""
    import gen_textures as gt
    got = {}
    flat = np.array(gt.ASPHALT, np.float32)
    keep = (gt.save, gt.asphalt_base, gt.noise, gt.smooth_noise)
    gt.save = lambda a, name: got.__setitem__(name, np.array(a if not isinstance(a, Image.Image)
                                                             else np.asarray(a.convert('RGB')), np.float32)[..., :3])
    gt.asphalt_base = lambda w, h, seed: gt.canvas(w, h, gt.ASPHALT)
    gt.noise = lambda a, *args, **kw: a
    gt.smooth_noise = lambda w, h, *args, **kw: np.full((h, w), 0.5, np.float32)
    try:
        gt.gen_ground()
    finally:
        gt.save, gt.asphalt_base, gt.noise, gt.smooth_noise = keep
    for name, m_w, m_h, K in (('road2', 8, 8, 8), ('road4', 14, 8, 8), ('road2_cap', 8, 6, 8),
                              ('road4_cap', 14, 6, 8), ('parking', 2.6, 5.2, 4)):
        lay = got[name]
        h, w = lay.shape[:2]
        W, H = w * K, h * K
        big = np.asarray(Image.fromarray(lay.astype(np.uint8)).resize((W, H), Image.NEAREST), np.float32)
        base = asphalt(W, H, m_w, m_h, 40 + len(name) + w)
        diff = np.abs(big - flat).max(axis=2)
        paint = diff > 45
        a = base * np.where(paint, 1.0, big.mean(axis=2) / flat.mean())[..., None]      # тени у бордюра
        # краска разметки — потёртая
        wear = smooth_noise(W, H, 60 + w, 10, 3)
        fine = np.random.RandomState(70 + w).rand(H, W)
        alpha = np.clip(0.55 + 0.6 * wear - 0.35 * (fine > 0.86), 0.0, 1.0) * paint
        a = a * (1 - alpha[..., None]) + (big * 0.94) * alpha[..., None]
        if name.startswith('road') and not name.endswith('cap'):
            # колеи: посередине полос асфальт темнее и глаже
            lanes = 2 if name == 'road2' else 4
            xs = (np.arange(W) + 0.5) / W
            track = np.zeros(W, np.float32)
            for i in range(lanes):
                c = (i + 0.5) / lanes
                track += np.exp(-((xs - c) / 0.06) ** 2)
            a *= (1.0 - 0.10 * track)[None, :, None]
        save(a, name)


# ---------------------------------------------------------------------------
# фасады: одна секция = 3.5 × 3.2 м = 256 × 256 точек
# ---------------------------------------------------------------------------
def wall(material, m_tile, w=T, h=T, m_w=BAY_W, m_h=FLOOR_H, **tn):
    a = tiled(src(material), w, h, max(1, int(round(m_w / m_tile))), max(1, int(round(m_h / m_tile))))
    return tone(a, **tn) if tn else a


def put_window(a, source, ww, wh, sill=0.9, cx=0.5, m_w=BAY_W, m_h=FLOOR_H, frame=None, depth=True,
               crop=None, flip=False):
    """Вставляет фотографию окна шириной ww и высотой wh метров; sill — высота подоконника.
    Возвращает прямоугольник окна в точках (x0, y0, x1, y1)."""
    H, W = a.shape[:2]
    sx, sy = W / m_w, H / m_h
    w, h = int(round(ww * sx)), int(round(wh * sy))
    x0 = int(round(cx * W - w / 2.0))
    y0 = int(round(H - (sill + wh) * sy))
    s = src(source)
    if crop:
        s = s[crop[1]:crop[3], crop[0]:crop[2]]
    if flip:
        s = s[:, ::-1]
    if depth:
        soft_shadow(a, x0 - 2, y0 - 2, x0 + w + 2, y0 + h + 2, r=5, k=0.62, dy=3)
    if frame is not None:
        box(a, x0 - 3, y0 - 3, x0 + w + 3, y0 + h + 3, frame)
    win = np.asarray(img(resize(s, w, h)).filter(ImageFilter.UnsharpMask(1.2, 90, 2)).convert('RGB'), np.float32)
    paste(a, win, x0, y0)
    return (x0, y0, x0 + w, y0 + h)


def trim(a, rect, color, lintel=7, sill=6, over=7):
    """Перемычка над окном и подоконник с тенью под ним."""
    x0, y0, x1, y1 = rect
    c = np.array(color, np.float32)
    if lintel:
        box(a, x0 - over, y0 - lintel - 2, x1 + over, y0 - 2, c)
        shade(a, x0 - over, y0 - 4, x1 + over, y0 - 2, 0.78)
    if sill:
        box(a, x0 - over - 2, y1 + 2, x1 + over + 2, y1 + 2 + sill, c * 1.04)
        shade(a, x0 - over - 2, y1 + sill, x1 + over + 2, y1 + 2 + sill, 0.7)
        soft_shadow(a, x0 - over, y1 + 2 + sill, x1 + over, y1 + 2 + sill + 7, r=3, k=0.7)


def reg(name, rects, w=T, h=T):
    windows[name] = [(x0 / float(w), y0 / float(h), x1 / float(w), y1 / float(h)) for (x0, y0, x1, y1) in rects]


def floor_line(a, k=0.86):
    shade(a, 0, a.shape[0] - 3, a.shape[1], a.shape[0], k)


def gen_facades():
    # --- красный кирпич, белые рамы, каменные перемычки
    a = wall('Bricks/brick_red_02.jpg', 0.5, contrast=0.9)
    grime(a, 100, 0.18)
    r = put_window(a, 'Windows/window_classic_01.jpg', 1.2, 1.7, 0.8)
    trim(a, r, (206, 198, 184))
    streaks(a, 101, 0.16, r[0], r[2], r[3] + 8)
    floor_line(a)
    reg('fac_brick_a', [r])
    save(a, 'fac_brick_a')

    # --- тёмно-бурый кирпич, окна с аркой
    a = wall('Bricks/brick_small_old.png', 1.1, mul=(1.25, 1.12, 1.05))
    grime(a, 102, 0.2)
    r = put_window(a, 'Windows/window_old_01.jpg', 1.15, 1.6, 0.8)
    im = img(a)
    d = ImageDraw.Draw(im)
    d.pieslice([r[0] - 9, r[1] - 26, r[2] + 9, r[1] + 30], 180, 360, fill=(176, 160, 132))
    d.pieslice([r[0] - 1, r[1] - 16, r[2] + 1, r[1] + 26], 180, 360, fill=(46, 44, 44))
    a = arr(im)
    put_window(a, 'Windows/window_old_01.jpg', 1.15, 1.6, 0.8, depth=False)
    trim(a, r, (176, 160, 132), lintel=0)
    floor_line(a)
    reg('fac_brick_b', [(r[0], r[1] - 12, r[2], r[3])])
    save(a, 'fac_brick_b')

    # --- песочный кирпич, алюминиевые рамы
    a = wall('Bricks/brick_small_rustic_brown_2.png', 0.9, mul=(1.08, 1.02, 0.9))
    grime(a, 104, 0.16)
    r = put_window(a, 'Windows/window_modern_04.jpg', 1.2, 1.6, 0.85)
    trim(a, r, (226, 220, 204), lintel=5)
    floor_line(a)
    reg('fac_brick_c', [r])
    save(a, 'fac_brick_c')

    # --- серые блоки, тёмные рамы, потёки
    a = wall('Bricks/bricks_modern_01.jpg', 1.15, mul=(0.95, 0.95, 1.0))
    grime(a, 106, 0.24)
    r = put_window(a, 'Windows/window_modern_12.jpg', 1.2, 1.7, 0.8)
    trim(a, r, (150, 150, 154), lintel=0)
    streaks(a, 107, 0.3)
    floor_line(a)
    reg('fac_brick_d', [r])
    save(a, 'fac_brick_d')

    # --- бетонные панели с ленточным окном (красится цветом здания)
    a = wall('Concrete/concrete_wall_01.jpg', 3.5, mul=(1.18, 1.18, 1.16), sat=0.3)
    x0, x1 = 18, 238
    y1 = T - int(0.95 * T / FLOOR_H)
    y0 = y1 - int(1.45 * T / FLOOR_H)
    soft_shadow(a, x0 - 3, y0 - 3, x1 + 3, y1 + 3, r=5, k=0.6, dy=3)
    box(a, x0 - 3, y0 - 3, x1 + 3, y1 + 3, (70, 72, 76))
    w3 = (x1 - x0) // 3
    for k in range(3):
        s = resize(src('Windows/window_modern_02.jpg')[6:58, 8:68], w3 - 2, y1 - y0)
        paste(a, s, x0 + k * w3 + 1, y0)
    shade(a, 0, y1 + 3, T, y1 + 9, 0.86)                            # подоконная тяга
    shade(a, 0, 0, 2, T, 0.8)                                       # шов панелей
    shade(a, 0, T - 3, T, T, 0.78)
    streaks(a, 109, 0.14, y0=y1 + 6)
    reg('fac_conc_a', [(x0, y0, x1, y1)])
    save(a, 'fac_conc_a')

    # --- штукатурка, окно пошире
    a = wall('Walls/wall_stucco_02.jpg', 1.2, mul=(1.06, 1.0, 0.9))
    grime(a, 110, 0.14)
    r = put_window(a, 'Windows/window_modern_03.jpg', 1.9, 1.5, 0.85)
    trim(a, r, (150, 140, 124), lintel=0, sill=5)
    shade(a, 0, 0, T, 5, 0.86)
    reg('fac_conc_b', [r])
    save(a, 'fac_conc_b')

    # --- дома с балконами: дверь на балкон и окно (сам балкон — объёмный, его строит игра)
    for name, mat, mul, seed in (('fac_balcony_a', 'Walls/wall_plaster_worn_2.png', (1.12, 1.04, 0.88), 112),
                                 ('fac_balcony_b', 'Walls/wall_stucco_01.jpg', (0.98, 1.06, 1.16), 113)):
        a = wall(mat, 1.6, mul=mul)
        grime(a, seed, 0.16)
        r1 = put_window(a, 'Doors/door_grungy_02.jpg', 0.85, 2.15, 0.04, cx=0.30)
        r2 = put_window(a, 'Windows/window_modern_06.jpg', 1.0, 1.5, 0.9, cx=0.70)
        trim(a, r2, tuple(c * 0.9 for c in (220, 214, 200)), lintel=0, sill=5)
        box(a, r1[0] - 3, r1[1] - 5, r1[2] + 3, r1[1] - 1, (200, 194, 180))
        streaks(a, seed + 30, 0.14)
        floor_line(a, 0.8)
        reg(name, [(r1[0] + 6, r1[1] + 8, r1[2] - 6, r1[1] + 80), r2])
        save(a, name)

    # --- сайдинг частных домов (красится цветом дома)
    a = wall('Walls/siding_white_01.jpg', 0.55)
    r = put_window(a, 'Windows/window_modern.png', 1.1, 1.6, 0.85)
    for sx_ in (-1, 1):                                             # ставни
        sh = resize(tone(src('Windows/window_shutter_black.png')[:, 6:58], add=70, contrast=0.8),
                    24, r[3] - r[1])
        soft_shadow(a, (r[0] - 27) if sx_ < 0 else (r[2] + 3), r[1], (r[0] - 3) if sx_ < 0 else (r[2] + 27),
                    r[3], r=3, k=0.75, dy=2)
        paste(a, sh, (r[0] - 27) if sx_ < 0 else (r[2] + 3), r[1])
    reg('fac_siding', [r])
    save(a, 'fac_siding')

    # --- склады: профлист (красится), секция 4 м
    def metal(seed):
        a = tiled(src('Walls/siding_metal_red_01.jpg'), T, T, 3, 2)
        a = tone(a, sat=0.0, mul=(1.5, 1.5, 1.5), contrast=0.9)
        a = np.minimum(a, 238)
        streaks(a, seed, 0.2)
        grime(a, seed + 1, 0.12)
        return a
    a = metal(131)
    shade(a, 0, T - 14, T, T, 0.72)
    save(a, 'fac_wh')
    a = metal(132)
    s = resize(src('Windows/window_wood_old_01.jpg'), 210, 62)
    soft_shadow(a, 21, 34, 235, 100, r=4, k=0.6, dy=3)
    paste(a, s, 23, 36)
    reg('fac_wh_win', [(23, 36, 233, 98)])
    save(a, 'fac_wh_win')

    # --- гетто: облупленная штукатурка, решётки, граффити
    a = wall('Walls/wall_plaster_pealing.png', 1.3, mul=(1.05, 1.0, 0.94))
    grime(a, 133, 0.3)
    r = put_window(a, 'Windows/window_old_01.jpg', 1.1, 1.5, 0.85)
    for x in range(r[0] + 6, r[2], 11):                             # решётка
        box(a, x, r[1], x + 2, r[3], (34, 32, 30))
    box(a, r[0], (r[1] + r[3]) // 2, r[2], (r[1] + r[3]) // 2 + 2, (34, 32, 30))
    streaks(a, 134, 0.34)
    floor_line(a, 0.78)
    reg('fac_ghetto_a', [r])
    save(a, 'fac_ghetto_a')

    a = wall('Bricks/brick_red_03.jpg', 0.62, mul=(0.86, 0.82, 0.8))
    grime(a, 135, 0.34)
    r = put_window(a, 'Windows/window_boarded.png', 1.1, 1.55, 0.85)
    streaks(a, 136, 0.3)
    floor_line(a, 0.78)
    windows['fac_ghetto_b'] = []
    save(a, 'fac_ghetto_b')

    # --- набережная: гладкая пастельная штукатурка, белые тяги
    for name, col, seed in (('fac_deco_a', (238, 176, 164), 137), ('fac_deco_b', (156, 214, 206), 138),
                            ('fac_deco_c', (242, 220, 150), 139)):
        a = wall('Walls/wall_stucco.png', 1.2)
        a = a / a.mean() * np.array(col, np.float32)
        grime(a, seed, 0.10)
        r = put_window(a, 'Windows/window_modern_06.jpg', 1.3, 1.65, 0.8)
        trim(a, r, (246, 242, 232), lintel=6, sill=6)
        for y in (T - 20, T - 12):                                  # горизонтальные «скоростные» полосы
            box(a, 0, y, T, y + 4, (246, 242, 232))
            shade(a, 0, y + 4, T, y + 6, 0.86)
        box(a, 0, 0, T, 6, (246, 242, 232))
        shade(a, 0, 6, T, 9, 0.84)
        reg(name, [r])
        save(a, name)

    # --- стеклянные башни
    glass('fac_glass_a', (96, 146, 190), (40, 78, 124), (36, 50, 66), 2, 0.5, 120)
    glass('fac_glass_b', (58, 70, 84), (20, 26, 36), (16, 18, 22), 2, 0.7, 121, spandrel=(30, 32, 38))
    glass('fac_glass_c', (104, 162, 148), (46, 96, 90), (226, 228, 222), 2, 0.6, 122, spandrel=(210, 212, 206))
    glass('fac_glass_d', (190, 150, 82), (112, 78, 36), (64, 46, 26), 4, 0.5, 123)
    glass('fac_glass_e', (130, 160, 180), (72, 98, 124), (192, 198, 204), 1, 0.9, 124, spandrel=(124, 130, 138))


def glass(name, top, bot, mull, cols, sp_m, seed, spandrel=None):
    """Навесной стеклянный фасад: переплёты, отражение неба, межэтажная полоса."""
    a = np.zeros((T, T, 3), np.float32)
    sp = int(sp_m * T / FLOOR_H)
    t = np.linspace(0.0, 1.0, T - sp)[:, None, None]
    a[:T - sp] = np.array(top, np.float32) * (1 - t) + np.array(bot, np.float32) * t
    # отражение облаков: плавные светлые разводы
    n = smooth_noise(T, T, seed, 3, 3)
    a[:T - sp] *= (0.84 + 0.36 * n[:T - sp, :, None])
    # косой блик
    yy, xx = np.mgrid[0:T, 0:T]
    band = np.exp(-(((xx + yy * 0.7) % 190) - 60.0) ** 2 / 500.0)
    a[:T - sp] += (band[:T - sp, :, None] * 16)
    spc = np.array(spandrel if spandrel else tuple(c * 0.62 for c in bot), np.float32)
    a[T - sp:] = spc
    a[T - sp:] *= (0.92 + 0.16 * n[T - sp:, :, None])
    shade(a, 0, T - sp, T, T - sp + 3, 0.7)
    rects = []
    cw = T // cols
    m = max(3, T // 64)
    r = np.random.RandomState(seed)
    for c in range(cols):
        x0, x1 = c * cw + m, (c + 1) * cw
        if r.rand() < 0.35:                                         # жалюзи на части окон
            hh = int((T - sp) * r.uniform(0.15, 0.4))
            a[m:m + hh, x0:x1] = a[m:m + hh, x0:x1] * 0.5 + np.array((176, 172, 160), np.float32) * 0.5
            for y in range(m, m + hh, 4):
                a[y, x0:x1] *= 0.85
        rects.append((x0, m, x1, T - sp))
    for c in range(cols):
        box(a, c * cw, 0, c * cw + m, T, mull)
        a[:, c * cw + m:c * cw + m + 2] *= 0.8
    box(a, 0, 0, T, m, mull)
    a[m:m + 2] *= 0.8
    reg(name, rects)
    save(a, name)


def gen_night():
    """Ночные окна: 4 × 4 секции, складываются с фасадом.  Свет горит не везде и разного цвета."""
    for i, name in enumerate(sorted(windows)):
        rects = windows[name]
        if not rects:
            continue
        r = np.random.RandomState(900 + i)
        N = 512
        c = N // 4
        a = np.zeros((N, N, 3), np.float32)
        is_glass = 'glass' in name
        for by in range(4):
            for bx in range(4):
                for (x0, y0, x1, y1) in rects:
                    if r.rand() > (0.5 if is_glass else 0.42):
                        continue
                    kind = r.rand()
                    if is_glass:
                        col = (150, 190, 220) if kind < 0.6 else (230, 220, 170)
                    elif kind < 0.62:
                        col = (255, 214, 120)
                    elif kind < 0.86:
                        col = (255, 236, 190)
                    else:
                        col = (150, 190, 255)                       # телевизор
                    col = np.array(col, np.float32) * r.uniform(0.55, 1.0)
                    px0, py0 = int(bx * c + x0 * c) + 1, int(by * c + y0 * c) + 1
                    px1, py1 = int(bx * c + x1 * c) - 1, int(by * c + y1 * c) - 1
                    if px1 <= px0 or py1 <= py0:
                        continue
                    a[py0:py1, px0:px1] = col
                    if not is_glass:
                        # занавески и тени от мебели
                        ww = px1 - px0
                        if r.rand() < 0.6:
                            a[py0:py1, px0:px0 + ww // 4] *= 0.6
                            a[py0:py1, px1 - ww // 4:px1] *= 0.6
                        a[py0 + int((py1 - py0) * 0.72):py1, px0:px1] *= 0.7
                        a[py0:py1, (px0 + px1) // 2:(px0 + px1) // 2 + 1] *= 0.4
        save(a, name + '_n', colors=32)


# ---------------------------------------------------------------------------
# первые этажи: секция 3.5 × 4.0 м
# ---------------------------------------------------------------------------
def store_glass(a, x0, y0, x1, y1, fill, seed, frame=(48, 48, 52)):
    """Витрина: рама, за стеклом — товар, поверх — отражение улицы."""
    soft_shadow(a, x0 - 3, y0 - 3, x1 + 3, y1 + 3, r=5, k=0.6, dy=3)
    box(a, x0 - 3, y0 - 3, x1 + 3, y1 + 3, frame)
    inner = resize(fill, x1 - x0, y1 - y0)
    t = np.linspace(0.0, 1.0, y1 - y0)[:, None, None]
    refl = np.array((150, 176, 196), np.float32) * (1 - t) + np.array((60, 72, 86), np.float32) * t
    inner = inner * 0.62 + refl * 0.38
    yy, xx = np.mgrid[0:y1 - y0, 0:x1 - x0]
    band = np.exp(-(((xx + yy * 0.8) % 150) - 40.0) ** 2 / 300.0)
    inner += band[..., None] * 22
    paste(a, inner, x0, y0)


def gen_groundfloors():
    H = T
    sy = H / GF_H
    sx = T / BAY_W

    def Y(z):
        return int(round(H - z * sy))

    def X(m):
        return int(round(m * sx))
    def hcat(*parts):
        hh = min(p.shape[0] for p in parts)
        return np.concatenate([resize(p, p.shape[1], hh) for p in parts], 1)
    goods = [hcat(src('Doors/door_store_food_01.jpg')[8:-8, 4:-4], src('Doors/door_store_drinks_01.jpg')[8:-8, 4:-4]),
             hcat(src('Windows/inside_store_1.png'), src('Windows/inside_store_1.png')[:, ::-1]),
             src('Windows/window_paintcans_01.jpg')[6:58, 6:85],
             hcat(src('Doors/door_store_drinks_02.jpg')[8:-8, 4:-4], src('Doors/door_store_food_02.jpg')[8:-8, 4:-4])]
    shops = (('gf_shop_a', (176, 40, 40), 'Bricks/brick_small_red_2.png', 0.6, (0.62, 0.58, 0.56), True),
             ('gf_shop_b', (36, 112, 64), 'Walls/wall_stucco_02.jpg', 1.2, (0.92, 0.88, 0.78), True),
             ('gf_shop_c', (40, 72, 160), 'Concrete/concrete_01.png', 1.5, (0.66, 0.68, 0.74), False),
             ('gf_shop_d', (206, 152, 36), 'Bricks/brick_small_old.png', 1.1, (1.2, 1.0, 0.9), True))
    for i, (name, awn, mat, m_tile, mul, stripes) in enumerate(shops):
        a = wall(mat, m_tile, m_h=GF_H, mul=mul)
        grime(a, 200 + i, 0.14)
        # полоса под вывеску (козырёк над витриной — объёмный, его строит игра)
        y0, y1 = Y(3.92), Y(3.22)
        a[y0:y1] = np.array(awn, np.float32) * 0.62
        a[y0:y1] *= np.linspace(1.1, 0.86, y1 - y0)[:, None, None]
        box(a, 0, y0 - 3, T, y0, (60, 58, 56))
        box(a, 0, y1, T, y1 + 3, (60, 58, 56))
        soft_shadow(a, 0, y1 + 3, T, y1 + 12, r=4, k=0.6)
        # витрина и дверь
        store_glass(a, X(0.16), Y(2.9), X(2.3), Y(0.55), goods[i], 210 + i)
        # стеклянная дверь: тёмное стекло, ручка-штанга, табличка
        dx0, dx1, dy0, dy1 = X(2.48), X(3.34), Y(2.9), Y(0.04)
        soft_shadow(a, dx0 - 3, dy0 - 3, dx1 + 3, dy1, r=4, k=0.6, dy=2)
        box(a, dx0 - 3, dy0 - 3, dx1 + 3, Y(0.0), (48, 48, 52))
        inside = np.zeros((64, 32, 3), np.float32)
        inside[:] = (54, 62, 70)
        inside[40:] = (92, 84, 72)
        store_glass(a, dx0, dy0, dx1, dy1, inside, 240 + i, frame=(40, 40, 44))
        box(a, dx0 + 3, Y(0.36), dx1 - 3, dy1 - 3, (66, 66, 70))
        box(a, dx0 + 3, Y(1.14), dx1 - 3, Y(1.14) + 4, (196, 198, 202))
        box(a, dx0 + 3, Y(1.14) + 4, dx1 - 3, Y(1.14) + 5, (30, 30, 34))
        box(a, dx0 + 9, Y(1.86), dx0 + 33, Y(1.62), (232, 228, 214))
        box(a, dx0 + 11, Y(1.86) + 2, dx0 + 31, Y(1.62) - 2, awn)
        box(a, dx0 + 14, Y(1.76), dx0 + 28, Y(1.76) + 2, (240, 236, 224))
        # цоколь
        a[Y(0.5):H, :X(2.4)] *= 0.62
        a[Y(0.12):H] *= 0.8
        save(a, name)

    # офисный вестибюль: стекло от пола до потолка
    a = np.zeros((H, T, 3), np.float32)
    a[:] = (74, 78, 86)
    box(a, 0, 0, T, Y(3.4), (150, 152, 158))
    a[:Y(3.4)] *= np.linspace(1.05, 0.85, Y(3.4))[:, None, None]
    fill = np.zeros((64, 64, 3), np.float32)
    fill[:] = (40, 48, 56)
    fill[40:] = (70, 64, 56)                                        # пол вестибюля
    fill[20:40, 8:24] = (96, 84, 60)                                # стойка
    store_glass(a, 6, Y(3.34), T - 6, Y(0.1), fill, 220, frame=(186, 190, 196))
    for x in (6, 86, 170, T - 8):
        box(a, x, Y(3.34), x + 3, Y(0.1), (186, 190, 196))
    box(a, 6, Y(2.2), T - 6, Y(2.2) + 3, (186, 190, 196))
    box(a, 0, Y(0.1), T, H, (58, 58, 62))
    save(a, 'gf_office')

    # подъезд жилого дома
    a = wall('Bricks/brick_red_04.jpg', 0.75, m_h=GF_H, mul=(0.9, 0.86, 0.84))
    grime(a, 230, 0.2)
    r = put_window(a, 'Doors/door_business_01.jpg', 1.0, 2.3, 0.04, cx=0.36, m_h=GF_H)
    box(a, r[0] - 8, r[1] - 12, r[2] + 8, r[1] - 3, (170, 160, 140))
    put_window(a, 'Windows/window_old_02.jpg', 1.2, 0.6, 2.1, cx=0.78, m_h=GF_H)
    box(a, X(2.2), Y(1.5), X(2.5), Y(1.1), (60, 64, 70))            # почтовые ящики
    a[Y(0.35):H] *= 0.7
    streaks(a, 231, 0.2)
    save(a, 'gf_door')

    # гараж
    a = wall('Concrete/concrete_blocks_painted_gray_01.jpg', 0.8, m_h=GF_H, mul=(1.0, 1.0, 1.0))
    grime(a, 240, 0.2)
    g = tiled(tone(src('Doors/door_garage.png'), mul=(0.86, 0.86, 0.88)), X(3.1) - X(0.4), Y(0.0) - Y(3.0), 2, 2)
    soft_shadow(a, X(0.4) - 4, Y(3.0) - 4, X(3.1) + 4, H, r=5, k=0.55, dy=3)
    box(a, X(0.4) - 4, Y(3.0) - 4, X(3.1) + 4, H, (52, 52, 56))
    paste(a, g, X(0.4), Y(3.0))
    streaks(a, 241, 0.2, X(0.4), X(3.1), Y(3.0))
    save(a, 'gf_garage')

    # глухой первый этаж (красится цветом здания)
    a = wall('Walls/wall_stucco_02.jpg', 1.2, m_h=GF_H, mul=(1.1, 1.1, 1.1), sat=0.2)
    grime(a, 250, 0.14)
    a[Y(0.6):H] *= 0.74
    box(a, 0, Y(0.6) - 3, T, Y(0.6), (150, 150, 150))
    box(a, X(1.4), Y(3.0), X(2.1), Y(2.6), (70, 72, 76))            # вентиляционная решётка
    for y in range(Y(3.0) + 3, Y(2.6) - 2, 5):
        box(a, X(1.4) + 3, y, X(2.1) - 3, y + 2, (36, 36, 40))
    streaks(a, 251, 0.18)
    save(a, 'gf_blank')

    # гетто: рольставни и фанера
    a = wall('Walls/wall_plaster_pealing.png', 1.3, m_h=GF_H, mul=(0.96, 0.9, 0.86))
    grime(a, 260, 0.3)
    sh = tiled(tone(src('Roof/roof_metal_01.jpg'), sat=0.2, mul=(0.7, 0.72, 0.76)), X(2.2) - X(0.2),
               Y(0.1) - Y(2.9), 1, 2)
    sh = np.rot90(sh, 1)
    sh = resize(sh, X(2.2) - X(0.2), Y(0.1) - Y(2.9))
    soft_shadow(a, X(0.2) - 3, Y(2.9) - 3, X(2.2) + 3, Y(0.1), r=4, k=0.6, dy=3)
    paste(a, sh, X(0.2), Y(2.9))
    put_window(a, 'Doors/door_grungy.png', 0.95, 2.2, 0.04, cx=0.82, m_h=GF_H)
    im = img(a)
    d = ImageDraw.Draw(im, 'RGBA')
    rr = np.random.RandomState(4)
    for col in ((240, 80, 60, 200), (90, 230, 120, 190), (250, 250, 250, 170)):
        x, y = rr.randint(16, 50), rr.randint(Y(2.4), Y(0.8))
        pts = [(x, y)]
        for _ in range(6):
            x += rr.randint(10, 26)
            y += rr.randint(-26, 26)
            pts.append((x, min(Y(0.3), max(Y(2.8), y))))
        d.line(pts, fill=col, width=4, joint='curve')
    a = arr(im)
    a[Y(0.3):H] *= 0.7
    streaks(a, 261, 0.3)
    save(a, 'gf_ghetto')

    # вход в частный дом (красится цветом дома): 3.5 × 3.2 м
    a = wall('Walls/siding_white_01.jpg', 0.55)
    r = put_window(a, 'Doors/door_grungy_03.jpg', 0.95, 2.2, 0.06, cx=0.36)
    box(a, r[0] - 6, r[1] - 9, r[2] + 6, r[1] - 3, (236, 234, 228))
    r2 = put_window(a, 'Windows/window_modern.png', 0.9, 1.3, 1.0, cx=0.78)
    box(a, r[2] + 10, r[1] + 26, r[2] + 18, r[1] + 40, (60, 60, 64))    # фонарь у двери
    box(a, r[2] + 11, r[1] + 29, r[2] + 17, r[1] + 37, (255, 236, 170))
    box(a, 0, T - 10, T, T, (120, 116, 110))
    save(a, 'gf_house')


# ---------------------------------------------------------------------------
# детали: козырьки, перила, кондиционеры, слуховые окна, кровельное железо
# ---------------------------------------------------------------------------
def gen_details():
    # полосатые маркизы: 4 полосы на плитку
    for name, col, stripes in (('awning_a', (190, 44, 44), True), ('awning_b', (40, 122, 70), True),
                               ('awning_c', (44, 80, 170), False), ('awning_d', (214, 160, 40), True)):
        a = np.zeros((64, 64, 3), np.float32)
        for x in range(64):
            a[:, x] = col if (not stripes or (x // 8) % 2 == 0) else (236, 232, 220)
        a *= np.linspace(1.08, 0.80, 64)[:, None, None]              # ткань темнее к нижнему краю
        n = np.random.RandomState(len(name) + col[0]).rand(64, 64, 1)
        a *= (0.95 + 0.1 * n)
        save(a, name, colors=48)

    # перила: прутья и поручень (прозрачный фон)
    im = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    metal = (34, 34, 38, 255)
    for x in range(0, 64, 8):
        d.rectangle([x, 0, x + 2, 63], fill=metal)
    d.rectangle([0, 0, 63, 5], fill=metal)
    d.rectangle([0, 56, 63, 63], fill=metal)
    d.rectangle([0, 28, 63, 31], fill=metal)
    save(im, 'rail')

    # пожарная лестница
    im = Image.new('RGBA', (32, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 4, 63], fill=metal)
    d.rectangle([27, 0, 31, 63], fill=metal)
    for y in range(4, 64, 8):
        d.rectangle([0, y, 31, y + 2], fill=metal)
    save(im, 'ladder')

    # кондиционер
    a = resize(src('Industrial/ac_vent_02.jpg'), 64, 64)
    a = tone(a, mul=(0.92, 0.94, 0.98), sat=0.3)
    save(a, 'ac_unit', colors=64)

    # решётка машинного отделения на крышах
    a = resize(src('Industrial/generator_vent_02.jpg')[14:114, 6:76], 64, 64)
    a = tone(a, sat=0.0, mul=(0.9, 0.9, 0.92))
    save(a, 'louver', colors=48)

    # слуховое окно
    a = np.zeros((64, 64, 3), np.float32)
    a[:] = (226, 222, 212)
    w = resize(src('Windows/window_classic_01.jpg')[6:86, 4:60], 44, 50)
    paste(a, w, 10, 9)
    shade(a, 0, 0, 64, 4, 0.8)
    save(a, 'dormer', colors=64)

    # сайдинг без окон: фронтоны частных домов (красится цветом дома), плитка 3.5 × 3.2 м
    a = wall('Walls/siding_white_01.jpg', 0.55, 128, 128)
    save(a, 'siding', colors=64)

    # кровельное железо со швами (красится цветом крыши)
    a = tiled(src('Roof/roof_metal_01.jpg'), 128, 128, 2, 1)
    a = tone(a, sat=0.0, contrast=0.8)
    a = a / a.mean() * 190.0
    streaks(a, 71, 0.22)
    grime(a, 72, 0.14, 4)
    save(a, 'roof_metal', colors=64)


# ---------------------------------------------------------------------------
# зелень: кроны деревьев, кора, живая изгородь
# ---------------------------------------------------------------------------
def src_rgba(name):
    folder, fname = name.split('/')
    return Image.open(os.path.join(SRC, folder, 'Materials', fname)).convert('RGBA')


def _fronds():
    b1 = src_rgba('Nature/bush_01.png')
    b4 = src_rgba('Nature/bush_04.png')
    b5 = src_rgba('Nature/bush_05.png')
    return [b1, b1.crop((0, 0, 80, 128)), b4.crop((0, 0, 70, 80)), b4.crop((56, 48, 128, 128)),
            b5.crop((66, 36, 128, 128)), b5.crop((66, 36, 128, 128))]


def _scatter(size, n, seed, tint, shape='disc', wrap=False, base=None):
    """Листва из фотографий веток: n веток случайного размера и поворота; дальние темнее."""
    rs = np.random.RandomState(seed)
    fr = _fronds()
    S = size
    canvas = Image.new('RGBA', (S, S), base or (0, 0, 0, 0))
    tint = np.array(tint, np.float32)
    for i in range(n):
        f = fr[rs.randint(len(fr))]
        sc = rs.uniform(0.5, 0.95) * S / 256.0
        t = f.resize((max(2, int(f.width * sc)), max(2, int(f.height * sc))), Image.BILINEAR)
        t = t.rotate(rs.uniform(0, 360), expand=True, resample=Image.BILINEAR)
        a = np.asarray(t, np.float32).copy()
        lum = a[..., :3].mean(axis=2, keepdims=True)
        k = (0.42 + 0.72 * (i / float(n))) * rs.uniform(0.86, 1.12)
        hue = tint * np.array([rs.uniform(0.85, 1.2), rs.uniform(0.92, 1.08), rs.uniform(0.8, 1.15)], np.float32)
        a[..., :3] = np.clip((0.35 + lum / 90.0) * hue * k, 0, 255)
        t = Image.fromarray(a.astype(np.uint8), 'RGBA')
        if shape == 'disc':
            r = math.sqrt(rs.uniform(0, 1)) * S * 0.37
            ang = rs.uniform(0, 2 * math.pi)
            cx = S * 0.5 + math.cos(ang) * r
            cy = S * 0.47 + math.sin(ang) * r * 0.92 - (i / float(n)) * S * 0.05
        else:
            cx, cy = rs.uniform(0, S), rs.uniform(0, S)
        x, y = int(cx - t.width * 0.5), int(cy - t.height * 0.5)
        for ox in ((-S, 0, S) if wrap else (0,)):
            for oy in ((-S, 0, S) if wrap else (0,)):
                canvas.alpha_composite(t, (max(0, x + ox), max(0, y + oy)),
                                       (max(0, -(x + ox)), max(0, -(y + oy)))) \
                    if (x + ox < S and y + oy < S and x + ox + t.width > 0 and y + oy + t.height > 0) else None
    return canvas


def _hard_alpha(im, thr=96):
    """Жёсткая альфа и заливка прозрачных точек средним цветом (иначе на мип-уровнях тёмная кайма)."""
    a = np.asarray(im, np.float32).copy()
    op = a[..., 3] > thr
    mean = a[..., :3][op].mean(axis=0) if op.any() else np.array([60, 90, 40], np.float32)
    a[..., :3][~op] = mean
    a[..., 3] = np.where(op, 255, 0)
    return Image.fromarray(a.astype(np.uint8), 'RGBA')


def gen_nature():
    save(_hard_alpha(_scatter(256, 150, 31, (74, 128, 52))), 'foliage_a')
    save(_hard_alpha(_scatter(256, 150, 47, (112, 138, 50))), 'foliage_b')
    # живая изгородь: сплошная листва, стыкуется
    h = _scatter(128, 170, 53, (62, 112, 46), shape='tile', wrap=True, base=(22, 44, 20, 255))
    save(np.asarray(h.convert('RGB'), np.float32), 'hedge', colors=64)
    # кора
    a = resize(src('Nature/bark_2.png'), 64, 64)
    save(tone(a, mul=(0.9, 0.86, 0.82), contrast=1.1), 'bark', colors=32)


# ---------------------------------------------------------------------------
# уличные предметы: контейнеры, ящики, скамейки, баки
# ---------------------------------------------------------------------------
def _grey(a, level=178.0, contrast=1.0):
    """Материал в оттенках серого со средней яркостью level — чтобы красить его цветом вершин."""
    a = tone(a, sat=0.0, contrast=contrast)
    return a / max(1.0, float(a.mean())) * level


def gen_props():
    # морской контейнер (красится): борт без надписей и торец с дверями
    side = src('Industrial/shipping_container_01_side.jpg')
    r1, r2 = side[4:120, 64:122], side[4:120, 198:256]     # участки борта без надписей и логотипа
    a = np.concatenate([r1, r2, r1[:, ::-1], r2[:, ::-1]], 1)
    a = _grey(resize(a, 256, 128), 176.0, 1.15)
    streaks(a, 301, 0.2)
    a[:5] *= 0.6
    a[-6:] *= 0.55
    for x in (0, 252):
        a[:, x:x + 4] *= 0.6
    save(a, 'container_side', colors=48)
    e = _grey(resize(src('Industrial/shipping_container_01_front.jpg'), 128, 128), 176.0, 1.15)
    box(e, 62, 6, 66, 122, (60, 60, 60))                   # створ дверей
    for x in (22, 44, 84, 106):                            # штанги запоров
        box(e, x, 8, x + 3, 120, (212, 212, 212))
        box(e, x - 3, 60, x + 6, 66, (70, 70, 70))
    e[:5] *= 0.6
    e[-6:] *= 0.55
    for x in (0, 124):
        e[:, x:x + 4] *= 0.6
    save(e, 'container_end', colors=48)

    # деревянный ящик
    c = resize(src('Misc/crate_old_01.jpg')[2:62, 4:68], 64, 64)
    save(tone(c, mul=(1.02, 0.96, 0.86), contrast=1.1), 'crate', colors=48)

    # крашеные доски скамеек (красятся)
    w = _grey(tiled(src('Wood/wood_planks_tan.png')[:, 4:124], 64, 64, 1, 1), 196.0, 1.5)
    save(w, 'planks', colors=32)

    # крашеный металл с потёками: мусорные баки, бочки (красится)
    m = _grey(resize(src('Metal/metal_rusty_02.png'), 128, 64), 170.0, 0.9)
    r = resize(src('Metal/metal_siding_01.jpg'), 128, 64)
    m = m * 0.55 + _grey(r, 170.0, 1.2) * 0.45
    streaks(m, 311, 0.2)
    save(m, 'metal_paint', colors=48)

    # крышка люка (наклейка на асфальт)
    im = src_rgba('Industrial/manhole_cover.png').resize((64, 64), Image.LANCZOS)
    a = np.asarray(im, np.float32).copy()
    yy, xx = np.mgrid[0:64, 0:64]
    rr = np.hypot(xx - 31.5, yy - 31.5)
    a[..., 3] = np.clip((28.5 - rr) * 1.6, 0, 1) * 255
    a[..., :3] *= 0.82
    save(Image.fromarray(a.astype(np.uint8), 'RGBA'), 'manhole')


# ---------------------------------------------------------------------------
def contact_sheet(path):
    names = sorted(written)
    cell = 132
    cols = 12
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell, rows * cell), (24, 24, 24))
    for i, n in enumerate(names):
        im = Image.open(os.path.join(OUT, n + '.png')).convert('RGB')
        im.thumbnail((128, 128), Image.LANCZOS)
        sheet.paste(im, ((i % cols) * cell + 2, (i // cols) * cell + 2))
    sheet.save(path)


def main():
    args = sys.argv[1:]
    if args[:1] == ['fetch']:
        fetch()
        return
    fetch()
    os.makedirs(OUT, exist_ok=True)
    gen_ground()
    gen_roads()
    gen_facades()
    gen_night()
    gen_groundfloors()
    gen_details()
    gen_nature()
    gen_props()
    with open(MANIFEST, 'w', encoding='utf-8') as f:
        json.dump({'textures': sorted(written),
                   'windows': {k: [[round(v, 4) for v in r] for r in rs] for k, rs in sorted(windows.items())}},
                  f, indent=1, sort_keys=True)
    size = sum(os.path.getsize(os.path.join(OUT, n + '.png')) for n in written)
    print('текстур города: %d, %d КБ' % (len(written), size // 1024))
    if '--sheet' in args:
        contact_sheet(args[args.index('--sheet') + 1])


if __name__ == '__main__':
    main()
