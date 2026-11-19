# -*- coding: utf-8 -*-
"""Зимние текстуры для Зимогорска — городка пролога (только для разработки).

Запуск из корня репозитория:  python tools/gen_snow.py
Результат: assets/tex/snow*.png, *_snow.png, snowflake.png.

Ничего не скачивает: снег кладётся поверх уже готовых текстур города (асфальт, дороги с разметкой, тротуар,
кровля, изгородь, листва), так что развёртки совпадают и геометрию менять не нужно — citymesh.py просто берёт
для чанков городка зимние варианты (см. CityMesh.SNOW_SWAP).
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(ROOT, 'assets', 'tex')
SNOW_RGB = np.array([236.0, 241.0, 248.0])
SHADE_RGB = np.array([192.0, 205.0, 226.0])        # снег в ложбинках: голубее и темнее


def load(name):
    return np.asarray(Image.open(os.path.join(TEX, name + '.png')).convert('RGBA'), dtype=np.float64)


def noise(w, h, seed, cells=6, octaves=4, gain=0.5):
    """Гладкий шум 0..1, который бесшовно повторяется (текстуры кладутся плиткой)."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w))
    amp, total = 1.0, 0.0
    for o in range(octaves):
        n = cells * (2 ** o)
        g = rng.random((n, n))
        ys = np.arange(h) * n / float(h)
        xs = np.arange(w) * n / float(w)
        y0 = np.floor(ys).astype(int) % n
        x0 = np.floor(xs).astype(int) % n
        y1 = (y0 + 1) % n
        x1 = (x0 + 1) % n
        fy = ys - np.floor(ys)
        fx = xs - np.floor(xs)
        fy = fy * fy * (3 - 2 * fy)
        fx = fx * fx * (3 - 2 * fx)
        a = g[np.ix_(y0, x0)] * (1 - fx)[None, :] + g[np.ix_(y0, x1)] * fx[None, :]
        b = g[np.ix_(y1, x0)] * (1 - fx)[None, :] + g[np.ix_(y1, x1)] * fx[None, :]
        out += (a * (1 - fy)[:, None] + b * fy[:, None]) * amp
        total += amp
        amp *= gain
    out /= total
    return (out - out.min()) / max(1e-9, out.max() - out.min())


def snow_color(w, h, seed, dirty=0.0):
    """Сам снег: белый с голубыми тенями в ложбинках и редкими искрами."""
    n = noise(w, h, seed, 5, 4)
    fine = noise(w, h, seed + 1, 24, 2)
    k = np.clip(0.25 + 0.75 * n + 0.18 * (fine - 0.5), 0.0, 1.0)
    rgb = SHADE_RGB[None, None, :] * (1 - k[..., None]) + SNOW_RGB[None, None, :] * k[..., None]
    rng = np.random.default_rng(seed + 2)
    sp = rng.random((h, w)) > 0.9965
    rgb[sp] = 255.0
    if dirty > 0.0:
        d = np.clip((noise(w, h, seed + 3, 7, 3) - 0.45) * 3.0, 0.0, 1.0) * dirty
        mud = np.array([150.0, 142.0, 132.0])
        rgb = rgb * (1 - d[..., None]) + mud[None, None, :] * d[..., None]
    return rgb


def cover(base, mask, seed, wet=0.82):
    """Положить снег на текстуру: mask 0..1 — доля снега; открытое покрытие темнеет (мокрое)."""
    h, w = base.shape[:2]
    s = snow_color(w, h, seed)
    rgb = base[..., :3] * wet
    m = mask[..., None]
    out = base.copy()
    out[..., :3] = rgb * (1 - m) + s * m
    return out


def save(a, name, colors=255):
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGBA')
    path = os.path.join(TEX, name + '.png')
    if a[..., 3].min() >= 254.5:
        im.convert('RGB').quantize(colors, method=Image.MEDIANCUT, dither=Image.NONE).save(path, optimize=True)
    else:
        im.save(path, optimize=True)
    print('%-22s %4dx%-4d %7d bytes' % (name, im.size[0], im.size[1], os.path.getsize(path)))


def patches(w, h, seed, amount, cells=6, soft=0.12):
    """Маска снега пятнами: amount — какая доля площади под снегом."""
    n = noise(w, h, seed, cells, 4)
    thr = np.quantile(n, 1.0 - amount)
    return np.clip((n - thr) / soft + 0.5, 0.0, 1.0)


def road(name, lanes, seed):
    """Дорога с разметкой: снег у бордюров и валиком между полосами, в колеях — мокрый асфальт."""
    a = load(name)
    h, w = a.shape[:2]
    x = (np.arange(w) + 0.5) / w                    # поперёк дороги
    edge = np.clip(1.0 - np.minimum(x, 1.0 - x) / 0.085, 0.0, 1.0)             # сугробы у бордюров
    prof = edge ** 0.7
    for k in range(1, lanes):                       # валики между полосами
        prof = np.maximum(prof, np.clip(1.0 - np.abs(x - k / float(lanes)) / 0.022, 0.0, 1.0) * 0.8)
    for k in range(lanes):                          # между колеями одной полосы — тонкий снежок
        c = (k + 0.5) / lanes
        prof = np.maximum(prof, np.clip(1.0 - np.abs(x - c) / (0.05 / lanes * 2.0), 0.0, 1.0) * 0.42)
    n = noise(w, h, seed, 8, 4)
    fine = noise(w, h, seed + 5, 40, 2)
    m = np.clip(prof[None, :] * 1.5 + (n - 0.55) * 1.1 + (fine - 0.5) * 0.25, 0.0, 1.0)
    m = np.clip((m - 0.35) / 0.4, 0.0, 1.0)
    save(cover(a, m, seed + 9, wet=0.72), name + '_snow')


def main():
    T = 256
    a = np.zeros((T, T, 4))
    a[..., 3] = 255.0
    a[..., :3] = snow_color(T, T, 11)
    save(a, 'snow')
    a[..., :3] = snow_color(T, T, 21, dirty=0.75)
    save(a, 'snow_dirt')
    # тротуар, плитка и бетон: покрытие проглядывает на протоптанных местах
    save(cover(load('sidewalk'), patches(T, T, 31, 0.62, 5), 32, wet=0.78), 'sidewalk_snow')
    b = load('pavers')
    save(cover(b, patches(b.shape[1], b.shape[0], 35, 0.66, 5), 36, wet=0.78), 'pavers_snow')
    save(cover(load('concrete'), patches(T, T, 41, 0.72, 5), 42, wet=0.78), 'concrete_snow')
    save(cover(load('asphalt'), patches(T, T, 51, 0.40, 7), 52, wet=0.70), 'asphalt_snow')
    road('road2', 2, 61)
    road('road2_cap', 2, 62)
    road('road4', 4, 63)
    road('road4_cap', 4, 64)
    # скатная кровля: снег лежит почти сплошь, черепица видна у конька и карниза
    b = load('roof_tiles')
    save(cover(b, patches(b.shape[1], b.shape[0], 71, 0.965, 3, 0.25), 72, wet=0.9), 'roof_snow')
    # изгородь и листва: иней и шапки снега сверху
    b = load('hedge')
    h, w = b.shape[:2]
    top = np.clip(1.0 - np.arange(h) / (h * 0.55), 0.0, 1.0)[:, None]           # верх текстуры — верх изгороди
    m = np.clip(top * 1.2 + (noise(w, h, 81, 6, 3) - 0.5) * 1.0, 0.0, 1.0)
    grey = b.copy()
    lum = b[..., :3].mean(axis=2, keepdims=True)
    grey[..., :3] = lum * 0.55 + b[..., :3] * 0.25 + 38.0
    save(cover(grey, m, 82, wet=1.0), 'hedge_snow')
    for i, name in enumerate(('foliage_a', 'foliage_b')):
        b = load(name)
        h, w = b.shape[:2]
        lum = b[..., :3].mean(axis=2, keepdims=True)
        frost = b.copy()
        # зимняя крона: тёмные ветви, сверху на комках листвы — снег (светлые места фотографии)
        frost[..., :3] = lum * 0.50 + b[..., :3] * 0.12 + 30.0
        ln = (lum[..., 0] - lum[..., 0][b[..., 3] > 128].mean()) / 60.0
        m = np.clip(0.52 + ln * 1.1 + (noise(w, h, 91 + i, 10, 3) - 0.5) * 0.8, 0.0, 1.0)
        save(cover(frost, m, 93 + i, wet=1.0), name + '_snow')
    # снежинка для метели
    n = 16
    yy, xx = np.mgrid[0:n, 0:n]
    d = np.hypot(xx - (n - 1) / 2.0, yy - (n - 1) / 2.0) / (n / 2.0)
    fl = np.zeros((n, n, 4))
    fl[..., :3] = 255.0
    fl[..., 3] = np.clip(1.0 - d, 0.0, 1.0) ** 1.4 * 255.0
    save(fl, 'snowflake')
    return 0


if __name__ == '__main__':
    sys.exit(main())
