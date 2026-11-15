#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор текстур для Deadly District.

Все текстуры игры рисуются кодом (пиксель-арт в духе PS1/PS2), поэтому
в проекте нет ни одного чужого файла графики.  Скрипт нужен только при
разработке: готовые PNG уже лежат в assets/tex.

    python tools/gen_textures.py            # пересоздать assets/tex/*.png
    python tools/gen_textures.py --sheet x.png   # + обзорный лист

Зависимости (только для разработки): pillow, numpy.
"""
import os
import sys
import math
import argparse

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'tex')
FONT_DIR = os.path.join(ROOT, 'assets', 'fonts')

_written = []


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def rng(seed):
    return np.random.RandomState(seed)


def canvas(w, h, color, alpha=None):
    """float32 array (h, w, 3|4) in 0..255"""
    ch = 3 if alpha is None else 4
    a = np.zeros((h, w, ch), np.float32)
    a[..., :3] = color[:3]
    if ch == 4:
        a[..., 3] = alpha
    return a


def noise(a, amount, seed, mono=True, grain=1):
    r = rng(seed)
    h, w = a.shape[:2]
    gh, gw = max(1, h // grain), max(1, w // grain)
    if mono:
        n = r.uniform(-amount, amount, (gh, gw, 1))
    else:
        n = r.uniform(-amount, amount, (gh, gw, 3))
    if grain > 1:
        n = np.repeat(np.repeat(n, grain, 0), grain, 1)[:h, :w]
    a[..., :3] += n
    return a


def smooth_noise(w, h, seed, octaves=3, base=8):
    """tileable value noise in 0..1"""
    r = rng(seed)
    out = np.zeros((h, w), np.float32)
    amp = 1.0
    tot = 0.0
    for o in range(octaves):
        cells = max(1, base * (2 ** o))
        g = r.rand(cells, cells).astype(np.float32)
        img = Image.fromarray((g * 255).astype(np.uint8))
        # wrap pad so that resizing stays tileable
        big = Image.new('L', (cells * 3, cells * 3))
        for i in range(3):
            for j in range(3):
                big.paste(img, (i * cells, j * cells))
        big = big.resize((w * 3, h * 3), Image.BICUBIC)
        arr = np.asarray(big, np.float32)[h:2 * h, w:2 * w] / 255.0
        out += arr * amp
        tot += amp
        amp *= 0.5
    return out / tot


def rect(a, x0, y0, x1, y1, color, alpha=None):
    h, w = a.shape[:2]
    x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))
    if x1 <= x0 or y1 <= y0:
        return
    a[y0:y1, x0:x1, :3] = color[:3]
    if a.shape[2] == 4:
        a[y0:y1, x0:x1, 3] = 255 if alpha is None else alpha


def frame(a, x0, y0, x1, y1, color, t=1):
    rect(a, x0, y0, x1, y0 + t, color)
    rect(a, x0, y1 - t, x1, y1, color)
    rect(a, x0, y0, x0 + t, y1, color)
    rect(a, x1 - t, y0, x1, y1, color)


def vgrad(a, x0, y0, x1, y1, ctop, cbot):
    for y in range(int(y0), int(y1)):
        t = (y - y0) / max(1, (y1 - y0 - 1))
        c = [ctop[i] * (1 - t) + cbot[i] * t for i in range(3)]
        rect(a, x0, y, x1, y + 1, c)


def shade(a, x0, y0, x1, y1, mul):
    h, w = a.shape[:2]
    x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))
    a[y0:y1, x0:x1, :3] *= mul


def to_img(a):
    arr = np.clip(a, 0, 255).astype(np.uint8)
    mode = 'RGBA' if arr.shape[2] == 4 else 'RGB'
    return Image.fromarray(arr, mode)


def from_img(img):
    return np.asarray(img, np.float32).copy()


_photo = None


def photo_names():
    """Имена текстур, которые делает tools/gen_city.py из фотоматериалов: их не перезаписываем."""
    global _photo
    if _photo is None:
        try:
            import json
            with open(os.path.join(OUT, '_photo.json'), encoding='utf-8') as f:
                _photo = set(json.load(f).get('textures', []))
        except Exception:
            _photo = set()
    return _photo


def save(a, name):
    img = a if isinstance(a, Image.Image) else to_img(a)
    if name in photo_names():
        return img
    path = os.path.join(OUT, name + '.png')
    img.save(path, optimize=True)
    _written.append((name, img))
    return img


def font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def posterize(a, levels=24):
    """Немного «PS1»: уменьшаем число оттенков"""
    q = 255.0 / (levels - 1)
    a[..., :3] = np.round(a[..., :3] / q) * q
    return a


# --------------------------------------------------------------------------
# ground
# --------------------------------------------------------------------------
ASPHALT = (60, 61, 66)


def asphalt_base(w, h, seed):
    a = canvas(w, h, ASPHALT)
    n = smooth_noise(w, h, seed, 3, 4)[..., None]
    a[..., :3] += (n - 0.5) * 14
    noise(a, 7, seed + 1)
    r = rng(seed + 2)
    for _ in range(w * h // 90):
        x, y = r.randint(0, w), r.randint(0, h)
        a[y, x, :3] += r.choice([-16, 14, 22])
    return a


def gen_ground():
    save(posterize(asphalt_base(64, 64, 1), 40), 'asphalt')

    # --- street (2 lanes, 8 m wide) : U across, V along (8 m per tile)
    a = asphalt_base(64, 64, 3)
    shade(a, 0, 0, 3, 64, 0.82)
    shade(a, 61, 0, 64, 64, 0.82)
    rect(a, 31, 6, 33, 34, (214, 190, 70))          # dashed centre line
    noise(a, 4, 30)
    save(a, 'road2')

    # --- avenue (4 lanes, 14 m wide)
    a = asphalt_base(128, 64, 4)
    shade(a, 0, 0, 3, 64, 0.82)
    shade(a, 125, 0, 128, 64, 0.82)
    rect(a, 61, 0, 63, 64, (214, 190, 70))          # double yellow
    rect(a, 65, 0, 67, 64, (214, 190, 70))
    rect(a, 31, 6, 33, 32, (220, 220, 215))         # lane dashes
    rect(a, 95, 6, 97, 32, (220, 220, 215))
    noise(a, 4, 31)
    save(a, 'road4')

    # --- caps (6 m long): stop line + zebra at the intersection end (top)
    def cap(w, lanes, seed):
        a = asphalt_base(w, 64, seed)
        shade(a, 0, 0, 3, 64, 0.82)
        shade(a, w - 3, 0, w, 64, 0.82)
        white = (222, 222, 216)
        # zebra: bars run along the driving direction, top part of image
        bar = 5
        x = 3
        while x + bar <= w - 2:
            rect(a, x, 4, x + bar, 30, white)
            x += bar * 2
        # stop line for the incoming half (right half when looking "up")
        rect(a, w // 2 + 1, 37, w - 3, 41, white)
        # centre line(s) up to the stop line
        if lanes == 2:
            rect(a, w // 2 - 1, 42, w // 2 + 1, 64, (214, 190, 70))
        else:
            rect(a, w // 2 - 3, 37, w // 2 - 1, 64, (214, 190, 70))
            rect(a, w // 2 + 1, 37, w // 2 + 3, 64, (214, 190, 70))
            rect(a, w * 3 // 4 - 1, 42, w * 3 // 4 + 1, 64, white)
            rect(a, w // 4 - 1, 42, w // 4 + 1, 64, white)
        noise(a, 5, seed + 9)
        # wear
        n = smooth_noise(w, 64, seed + 5, 2, 6)[..., None]
        a[..., :3] = a[..., :3] * (0.86 + 0.14 * n) + (1 - (0.86 + 0.14 * n)) * ASPHALT[0]
        return a
    save(cap(64, 2, 5), 'road2_cap')
    save(cap(128, 4, 6), 'road4_cap')

    # --- sidewalk slabs (tile = 3 m)
    a = canvas(64, 64, (150, 148, 142))
    n = smooth_noise(64, 64, 8, 3, 4)[..., None]
    a[..., :3] += (n - 0.5) * 20
    r = rng(9)
    for by in range(2):
        for bx in range(2):
            d = r.uniform(-8, 8)
            a[by * 32:(by + 1) * 32, bx * 32:(bx + 1) * 32, :3] += d
    for k in (0, 32):
        rect(a, k, 0, k + 1, 64, (104, 102, 98))
        rect(a, 0, k, 64, k + 1, (104, 102, 98))
    noise(a, 6, 10)
    for _ in range(26):
        x, y = r.randint(0, 64), r.randint(0, 64)
        a[y, x, :3] -= 30
    save(a, 'sidewalk')

    # --- plain concrete
    a = canvas(64, 64, (132, 130, 126))
    n = smooth_noise(64, 64, 11, 3, 4)[..., None]
    a[..., :3] += (n - 0.5) * 26
    noise(a, 6, 12)
    rect(a, 0, 0, 64, 1, (108, 106, 102))
    rect(a, 0, 0, 1, 64, (108, 106, 102))
    save(a, 'concrete')

    # --- pavers (plaza)
    a = canvas(64, 64, (160, 120, 100))
    r = rng(13)
    for row in range(8):
        off = 0 if row % 2 == 0 else 8
        for col in range(-1, 5):
            x0 = col * 16 + off
            d = r.uniform(-14, 14)
            c = (160 + d, 120 + d * 0.8, 100 + d * 0.7)
            rect(a, x0, row * 8, x0 + 15, row * 8 + 7, c)
            rect(a, x0 + 15, row * 8, x0 + 16, row * 8 + 8, (110, 86, 74))
        rect(a, 0, row * 8 + 7, 64, row * 8 + 8, (110, 86, 74))
    noise(a, 6, 14)
    save(a, 'pavers')

    # --- grass
    a = canvas(64, 64, (58, 112, 48))
    n = smooth_noise(64, 64, 15, 3, 4)[..., None]
    a[..., :3] += (n - 0.5) * np.array([26, 44, 22], np.float32)
    r = rng(16)
    for _ in range(520):
        x, y = r.randint(0, 64), r.randint(0, 64)
        d = r.choice([-22, -12, 16, 26])
        a[y, x, :3] += (d * 0.6, d, d * 0.4)
        if d > 0 and y > 0:
            a[y - 1, x, :3] += (d * 0.3, d * 0.5, d * 0.2)
    save(a, 'grass')

    # --- dirt
    a = canvas(64, 64, (112, 90, 64))
    n = smooth_noise(64, 64, 17, 3, 4)[..., None]
    a[..., :3] += (n - 0.5) * 34
    noise(a, 9, 18)
    r = rng(19)
    for _ in range(40):
        x, y = r.randint(0, 63), r.randint(0, 63)
        a[y:y + 2, x:x + 2, :3] -= 22
    save(a, 'dirt')

    # --- sand
    a = canvas(64, 64, (214, 196, 146))
    n = smooth_noise(64, 64, 20, 3, 4)[..., None]
    a[..., :3] += (n - 0.5) * 22
    noise(a, 7, 21)
    yy = np.arange(64)[:, None]
    xx = np.arange(64)[None, :]
    ripple = np.sin((yy + np.sin(xx / 64 * 2 * math.pi) * 3) / 64 * 2 * math.pi * 6)
    a[..., :3] += ripple[..., None] * 5
    save(a, 'sand')

    # --- gravel roof / tar roof
    a = canvas(64, 64, (96, 94, 92))
    noise(a, 20, 22)
    n = smooth_noise(64, 64, 23, 2, 4)[..., None]
    a[..., :3] += (n - 0.5) * 20
    save(a, 'roof_gravel')
    a = canvas(64, 64, (52, 52, 56))
    n = smooth_noise(64, 64, 24, 3, 4)[..., None]
    a[..., :3] += (n - 0.5) * 18
    noise(a, 5, 25)
    rect(a, 0, 31, 64, 32, (40, 40, 44))
    rect(a, 31, 0, 32, 64, (44, 44, 48))
    save(a, 'roof_tar')

    # --- clay roof tiles
    a = canvas(64, 64, (158, 70, 48))
    r = rng(26)
    for row in range(8):
        off = 0 if row % 2 == 0 else 4
        for col in range(-1, 9):
            x0 = col * 8 + off
            d = r.uniform(-16, 16)
            rect(a, x0, row * 8, x0 + 7, row * 8 + 8, (158 + d, 70 + d * 0.5, 48 + d * 0.4))
            rect(a, x0 + 7, row * 8, x0 + 8, row * 8 + 8, (104, 44, 32))
        rect(a, 0, row * 8 + 7, 64, row * 8 + 8, (96, 40, 30))
        shade(a, 0, row * 8, 64, row * 8 + 2, 1.14)
    noise(a, 5, 27)
    save(a, 'roof_tiles')

    # --- water (tileable)
    a = canvas(64, 64, (34, 84, 128))
    n1 = smooth_noise(64, 64, 28, 3, 4)
    n2 = smooth_noise(64, 64, 29, 2, 8)
    a[..., 0] += (n1 - 0.5) * 30
    a[..., 1] += (n1 - 0.5) * 46
    a[..., 2] += (n1 - 0.5) * 40
    crest = (n2 > 0.66)
    a[crest, :3] += (40, 54, 52)
    crest2 = (n2 > 0.76)
    a[crest2, :3] += (40, 44, 40)
    save(posterize(a, 28), 'water')

    # --- wood planks
    a = canvas(64, 64, (124, 88, 54))
    r = rng(32)
    for col in range(8):
        d = r.uniform(-16, 16)
        rect(a, col * 8, 0, col * 8 + 8, 64, (124 + d, 88 + d * 0.8, 54 + d * 0.6))
        rect(a, col * 8, 0, col * 8 + 1, 64, (70, 48, 30))
        ky = r.randint(0, 64)
        rect(a, col * 8 + 1, ky, col * 8 + 8, ky + 1, (78, 54, 34))
    noise(a, 7, 33)
    save(a, 'wood')

    # --- corrugated metal (light, for tinting)
    a = canvas(32, 32, (206, 208, 212))
    for x in range(32):
        k = (x % 4)
        m = (0.80, 0.96, 1.06, 0.92)[k]
        a[:, x, :3] *= m
    noise(a, 5, 34)
    rect(a, 0, 15, 32, 16, (150, 152, 156))
    r = rng(35)
    for _ in range(14):
        x, y = r.randint(0, 32), r.randint(0, 32)
        a[y:y + 3, x, :3] -= (26, 44, 60)      # rust streaks
    save(a, 'corrugated')

    # --- plain brick wall (party walls)
    save(brick_wall(64, 64, (140, 66, 52), 40), 'brick')

    # --- parking stall (2.6 m wide tile, white line on the left)
    a = asphalt_base(32, 64, 41)
    a[..., :3] *= 0.94
    rect(a, 0, 0, 2, 64, (214, 214, 208))
    noise(a, 4, 42)
    save(a, 'parking')

    # --- chainlink fence (alpha)
    a = canvas(32, 32, (150, 154, 160), alpha=0)
    for y in range(32):
        for x in range(32):
            if (x + y) % 8 == 0 or (x - y) % 8 == 0:
                a[y, x] = (158, 162, 170, 255)
    rect(a, 0, 0, 32, 2, (120, 124, 130), 255)
    rect(a, 0, 30, 32, 32, (120, 124, 130), 255)
    save(a, 'chainlink')

    # --- hedge / foliage
    a = canvas(32, 32, (40, 92, 40))
    r = rng(43)
    for _ in range(300):
        x, y = r.randint(0, 32), r.randint(0, 32)
        d = r.choice([-20, -10, 14, 24])
        a[y, x, :3] += (d * 0.5, d, d * 0.4)
    save(a, 'hedge')

    # --- palm leaf (alpha)
    img = Image.new('RGBA', (64, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(0, 16), (20, 4), (63, 14), (63, 18), (20, 28)], fill=(52, 128, 52, 255))
    d.line([(0, 16), (63, 16)], fill=(34, 92, 40, 255), width=1)
    for x in range(8, 62, 6):
        d.line([(x, 16), (x + 5, 5 + x // 9)], fill=(34, 96, 40, 255))
        d.line([(x, 16), (x + 5, 27 - x // 9)], fill=(34, 96, 40, 255))
    for x in range(10, 64, 6):
        d.polygon([(x, 0), (x + 3, 0), (x + 2, 9)], fill=(0, 0, 0, 0))
        d.polygon([(x, 31), (x + 3, 31), (x + 2, 23)], fill=(0, 0, 0, 0))
    save(img, 'palm_leaf')


def brick_wall(w, h, base, seed, bw=8, bh=4, mortar=(176, 170, 160)):
    a = canvas(w, h, mortar)
    r = rng(seed)
    row = 0
    for y in range(0, h, bh):
        off = 0 if row % 2 == 0 else bw // 2
        for x in range(-bw, w + bw, bw):
            d = r.uniform(-20, 20)
            c = (base[0] + d, base[1] + d * 0.7, base[2] + d * 0.6)
            xa = x + off
            for xx in range(xa, xa + bw - 1):
                rect(a, xx % w, y, xx % w + 1, y + bh - 1, c)
        row += 1
    noise(a, 6, seed + 1)
    return a


# --------------------------------------------------------------------------
# facades:  one tile = one bay (3.5 m) x one floor (3.2 m),  64 x 64 px
# --------------------------------------------------------------------------
GLASS_DAY_TOP = (58, 80, 104)
GLASS_DAY_BOT = (30, 42, 60)


def glass(a, x0, y0, x1, y1, top=GLASS_DAY_TOP, bot=GLASS_DAY_BOT, streak=True, seed=0):
    vgrad(a, x0, y0, x1, y1, top, bot)
    if streak:
        w = x1 - x0
        for y in range(int(y0), int(y1)):
            sx = int(x0 + (y - y0) * 0.6 + w * 0.15)
            for k in range(max(2, w // 6)):
                xx = sx + k
                if x0 <= xx < x1:
                    a[y, xx, :3] += 22
    # blinds / curtain hint
    r = rng(seed + 77)
    if r.rand() < 0.5:
        hh = int((y1 - y0) * r.uniform(0.2, 0.45))
        shade(a, x0, y0, x1, y0 + hh, 1.0)
        a[int(y0):int(y0) + hh, int(x0):int(x1), :3] = \
            a[int(y0):int(y0) + hh, int(x0):int(x1), :3] * 0.45 + np.array((150, 146, 134)) * 0.55


# registry of window rectangles for night-light generation
#   name -> list of (x0, y0, x1, y1) in 64x64 tile coordinates
WINDOW_RECTS = {}


def fac_brick(name, base, seed, trim=(214, 208, 196), arched=False, ac=False, dirty=0.0):
    a = brick_wall(64, 64, base, seed)
    wx0, wy0, wx1, wy1 = 20, 14, 44, 50
    rect(a, wx0 - 2, wy0 - 2, wx1 + 2, wy1 + 3, trim)
    glass(a, wx0, wy0, wx1, wy1, seed=seed)
    rect(a, wx0, (wy0 + wy1) // 2, wx1, (wy0 + wy1) // 2 + 1, trim)
    rect(a, (wx0 + wx1) // 2, wy0, (wx0 + wx1) // 2 + 1, wy1, trim)
    rect(a, wx0 - 4, wy1 + 3, wx1 + 4, wy1 + 5, tuple(c * 0.8 for c in trim))     # sill
    shade(a, wx0 - 4, wy1 + 5, wx1 + 4, wy1 + 7, 0.8)
    if arched:
        rect(a, wx0 - 2, wy0 - 5, wx1 + 2, wy0 - 2, tuple(c * 0.92 for c in base))
        rect(a, wx0, wy0 - 4, wx1, wy0 - 3, trim)
    if ac:
        rect(a, 26, 44, 38, 52, (170, 172, 170))
        rect(a, 27, 46, 37, 50, (110, 112, 112))
    if dirty:
        n = smooth_noise(64, 64, seed + 5, 3, 4)[..., None]
        a[..., :3] *= (1.0 - dirty * n)
        # streaks under the sill
        shade(a, wx0, wy1 + 7, wx0 + 3, 64, 0.78)
        shade(a, wx1 - 5, wy1 + 7, wx1 - 3, 64, 0.82)
    # floor band
    shade(a, 0, 62, 64, 64, 0.84)
    WINDOW_RECTS[name] = [(wx0, wy0, wx1, wy1)]
    save(a, name)


def fac_concrete(name, base, seed, band=True):
    a = canvas(64, 64, base)
    n = smooth_noise(64, 64, seed, 3, 4)[..., None]
    a[..., :3] += (n - 0.5) * 16
    noise(a, 4, seed + 1)
    if band:
        wx0, wy0, wx1, wy1 = 6, 16, 58, 44
    else:
        wx0, wy0, wx1, wy1 = 18, 14, 46, 46
    rect(a, wx0 - 1, wy0 - 1, wx1 + 1, wy1 + 1, tuple(c * 0.62 for c in base))
    glass(a, wx0, wy0, wx1, wy1, seed=seed)
    for mx in range(wx0 + (wx1 - wx0) // (3 if band else 2), wx1 - 2, (wx1 - wx0) // (3 if band else 2)):
        rect(a, mx, wy0, mx + 1, wy1, (60, 60, 64))
    # panel seams
    rect(a, 0, 0, 64, 1, tuple(c * 0.8 for c in base))
    rect(a, 0, 0, 1, 64, tuple(c * 0.86 for c in base))
    shade(a, wx0, wy1 + 1, wx1, wy1 + 3, 0.86)
    WINDOW_RECTS[name] = [(wx0, wy0, wx1, wy1)]
    save(a, name)


def fac_balcony(name, base, seed):
    a = canvas(64, 64, base)
    n = smooth_noise(64, 64, seed, 3, 4)[..., None]
    a[..., :3] += (n - 0.5) * 14
    noise(a, 4, seed + 1)
    # window + door
    rect(a, 9, 15, 29, 45, tuple(c * 0.7 for c in base))
    glass(a, 10, 16, 28, 44, seed=seed)
    rect(a, 19, 16, 20, 44, (220, 220, 214))
    rect(a, 35, 13, 53, 55, tuple(c * 0.7 for c in base))
    glass(a, 36, 14, 52, 54, seed=seed + 1)
    # balcony slab + railing
    rect(a, 4, 54, 60, 58, tuple(c * 0.78 for c in base))
    shade(a, 4, 58, 60, 61, 0.78)
    for x in range(5, 60, 4):
        rect(a, x, 42, x + 1, 54, (70, 72, 78))
    rect(a, 4, 41, 60, 43, (70, 72, 78))
    rect(a, 0, 0, 64, 1, tuple(c * 0.84 for c in base))
    WINDOW_RECTS[name] = [(10, 16, 28, 41), (36, 14, 52, 41)]
    save(a, name)


def fac_glass(name, top, bot, mull, seed, spandrel=None, cols=2, bright=1.0):
    a = canvas(64, 64, bot)
    vgrad(a, 0, 0, 64, 64, top, bot)
    n = smooth_noise(64, 64, seed, 2, 2)[..., None]
    a[..., :3] *= (0.86 + 0.28 * n) * bright
    # diagonal reflection
    for y in range(64):
        for k in range(10):
            x = (y // 2 + 14 + k) % 64
            a[y, x, :3] += 16
    wins = []
    cw = 64 // cols
    sp_h = 14 if spandrel else 0
    if spandrel:
        rect(a, 0, 64 - sp_h, 64, 64, spandrel)
        noise(a[64 - sp_h:], 4, seed + 3)
    for c in range(cols):
        rect(a, c * cw, 0, c * cw + 2, 64, mull)
        wins.append((c * cw + 2, 2, (c + 1) * cw, 64 - sp_h))
    rect(a, 0, 0, 64, 2, mull)
    WINDOW_RECTS[name] = wins
    save(a, name)


def fac_siding(name, seed):
    a = canvas(64, 64, (226, 224, 216))
    for y in range(0, 64, 6):
        rect(a, 0, y, 64, y + 1, (168, 166, 160))
        shade(a, 0, y + 1, 64, y + 2, 1.05)
    noise(a, 4, seed)
    rect(a, 18, 14, 46, 48, (250, 250, 246))
    glass(a, 21, 17, 43, 45, seed=seed)
    rect(a, 31, 17, 33, 45, (250, 250, 246))
    rect(a, 21, 30, 43, 32, (250, 250, 246))
    # shutters
    rect(a, 12, 14, 18, 48, (150, 150, 150))
    rect(a, 46, 14, 52, 48, (150, 150, 150))
    for y in range(16, 48, 3):
        rect(a, 12, y, 18, y + 1, (118, 118, 118))
        rect(a, 46, y, 52, y + 1, (118, 118, 118))
    WINDOW_RECTS[name] = [(21, 17, 43, 45)]
    save(a, name)


def fac_warehouse(name, seed, windows):
    a = canvas(64, 64, (206, 208, 212))
    for x in range(64):
        a[:, x, :3] *= (0.82, 0.96, 1.05, 0.93)[x % 4]
    noise(a, 5, seed)
    r = rng(seed + 1)
    for _ in range(20):
        x, y = r.randint(0, 64), r.randint(0, 60)
        a[y:y + r.randint(3, 9), x, :3] -= (22, 40, 56)
    rect(a, 0, 0, 64, 2, (130, 132, 136))
    if windows:
        rect(a, 13, 9, 51, 25, (96, 98, 102))
        glass(a, 14, 10, 50, 24, top=(84, 104, 116), bot=(52, 66, 78), seed=seed)
        for x in (26, 38):
            rect(a, x, 10, x + 1, 24, (96, 98, 102))
        WINDOW_RECTS[name] = [(14, 10, 50, 24)]
    save(a, name)


def fac_ghetto(name, seed, graffiti):
    base = (118, 74, 60)
    a = brick_wall(64, 64, base, seed)
    n = smooth_noise(64, 64, seed + 3, 3, 4)[..., None]
    a[..., :3] *= (0.62 + 0.42 * n)
    wx0, wy0, wx1, wy1 = 20, 14, 44, 50
    rect(a, wx0 - 2, wy0 - 2, wx1 + 2, wy1 + 2, (120, 116, 104))
    if graffiti:
        # boarded up window
        rect(a, wx0, wy0, wx1, wy1, (26, 26, 30))
        for i, y in enumerate(range(wy0 + 2, wy1 - 4, 9)):
            rect(a, wx0 - 1, y + (i % 2), wx1 + 1, y + 6 + (i % 2), (128 - i * 6, 96 - i * 4, 60))
            rect(a, wx0 - 1, y + 6 + (i % 2), wx1 + 1, y + 7 + (i % 2), (70, 50, 30))
        img = to_img(a).convert('RGBA')
        d = ImageDraw.Draw(img)
        r = rng(seed + 8)
        cols = [(230, 60, 160), (60, 210, 230), (240, 220, 60), (120, 230, 90)]
        c = cols[seed % 4]
        d.line([(3, 58), (9, 52), (13, 59), (18, 51)], fill=c, width=2)
        d.arc([46, 50, 60, 62], 20, 320, fill=cols[(seed + 1) % 4], width=2)
        a = from_img(img.convert('RGB'))
        WINDOW_RECTS[name] = []
    else:
        glass(a, wx0, wy0, wx1, wy1, top=(48, 60, 70), bot=(24, 30, 40), seed=seed)
        rect(a, wx0, 31, wx1, 32, (120, 116, 104))
        rect(a, 31, wy0, 32, wy1, (120, 116, 104))
        # window bars
        for x in range(wx0 + 3, wx1, 5):
            rect(a, x, wy0, x + 1, wy1, (40, 40, 44))
        WINDOW_RECTS[name] = [(wx0, wy0, wx1, wy1)]
    shade(a, 0, 56, 64, 64, 0.86)
    save(a, name)


def fac_deco(name, base, trim, seed):
    a = canvas(64, 64, base)
    n = smooth_noise(64, 64, seed, 3, 4)[..., None]
    a[..., :3] += (n - 0.5) * 12
    noise(a, 3, seed + 1)
    rect(a, 0, 56, 64, 60, trim)
    rect(a, 0, 60, 64, 62, tuple(c * 0.86 for c in trim))
    img = to_img(a)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([15, 11, 48, 47], radius=7, fill=tuple(int(c) for c in trim))
    a = from_img(img)
    glass(a, 18, 14, 46, 45, top=(70, 110, 128), bot=(36, 60, 80), seed=seed)
    rect(a, 31, 14, 33, 45, trim)
    WINDOW_RECTS[name] = [(18, 14, 46, 45)]
    save(a, name)


def gen_facades():
    fac_brick('fac_brick_a', (146, 66, 52), 100)
    fac_brick('fac_brick_b', (112, 78, 60), 101, trim=(196, 186, 160), arched=True)
    fac_brick('fac_brick_c', (176, 150, 104), 102, trim=(232, 226, 210), ac=True)
    fac_brick('fac_brick_d', (96, 92, 98), 103, trim=(200, 200, 204), dirty=0.25)
    fac_concrete('fac_conc_a', (150, 150, 146), 110, band=True)
    fac_concrete('fac_conc_b', (176, 164, 140), 111, band=False)
    fac_balcony('fac_balcony_a', (188, 176, 150), 112)
    fac_balcony('fac_balcony_b', (150, 160, 172), 113)
    fac_glass('fac_glass_a', (84, 132, 176), (40, 76, 120), (30, 44, 62), 120)
    fac_glass('fac_glass_b', (48, 60, 74), (22, 28, 38), (14, 16, 20), 121, spandrel=(34, 36, 42))
    fac_glass('fac_glass_c', (92, 150, 136), (44, 92, 86), (226, 228, 222), 122, spandrel=(214, 216, 210), cols=2)
    fac_glass('fac_glass_d', (176, 136, 70), (110, 76, 34), (60, 44, 24), 123, cols=4)
    fac_glass('fac_glass_e', (120, 150, 170), (70, 96, 120), (190, 196, 200), 124, spandrel=(120, 126, 132), cols=1)
    fac_siding('fac_siding', 130)
    fac_warehouse('fac_wh', 131, False)
    fac_warehouse('fac_wh_win', 132, True)
    fac_ghetto('fac_ghetto_a', 133, False)
    fac_ghetto('fac_ghetto_b', 134, True)
    fac_deco('fac_deco_a', (236, 172, 160), (250, 244, 232), 135)
    fac_deco('fac_deco_b', (150, 214, 208), (250, 250, 244), 136)
    fac_deco('fac_deco_c', (244, 222, 150), (250, 250, 250), 137)

    # ---- night light overlays: 4x4 bays, additive
    for i, (name, rects) in enumerate(sorted(WINDOW_RECTS.items())):
        if not rects:
            continue
        r = rng(900 + i)
        a = canvas(256, 256, (0, 0, 0))
        is_glass = 'glass' in name
        for by in range(4):
            for bx in range(4):
                for (x0, y0, x1, y1) in rects:
                    p = r.rand()
                    lit_prob = 0.42 if not is_glass else 0.5
                    if p > lit_prob:
                        continue
                    kind = r.rand()
                    if is_glass:
                        col = (150, 190, 220) if kind < 0.6 else (230, 220, 170)
                    elif kind < 0.62:
                        col = (255, 214, 120)
                    elif kind < 0.86:
                        col = (255, 236, 190)
                    else:
                        col = (150, 190, 255)        # TV glow
                    k = r.uniform(0.55, 1.0)
                    col = tuple(c * k for c in col)
                    ox, oy = bx * 64, by * 64
                    rect(a, ox + x0, oy + y0, ox + x1, oy + y1, col)
                    # darker lower part (furniture silhouettes)
                    shade(a, ox + x0, oy + y0 + (y1 - y0) * 0.72, ox + x1, oy + y1, 0.72)
        save(a, name + '_n')


# --------------------------------------------------------------------------
# ground floors:  one tile = 3.5 m x 4.0 m,  64 x 64 px
# --------------------------------------------------------------------------
def gf_shop(name, awning, wall, seed, stripes=True):
    a = canvas(64, 64, wall)
    noise(a, 5, seed)
    # awning
    for x in range(64):
        c = awning if (not stripes or (x // 6) % 2 == 0) else (236, 232, 222)
        rect(a, x, 4, x + 1, 16, c)
    shade(a, 0, 14, 64, 16, 0.7)
    shade(a, 0, 16, 64, 19, 0.62)
    # display window
    rect(a, 3, 20, 39, 56, (40, 40, 44))
    glass(a, 4, 21, 38, 55, top=(96, 126, 140), bot=(46, 62, 76), seed=seed)
    r = rng(seed + 2)
    for k in range(4):                      # goods silhouettes
        x = 6 + k * 8
        hh = r.randint(5, 13)
        rect(a, x, 55 - hh, x + 5, 55, tuple(r.randint(60, 200, 3)))
    # door
    rect(a, 43, 20, 61, 62, (40, 40, 44))
    glass(a, 45, 22, 59, 60, top=(84, 108, 120), bot=(40, 54, 66), seed=seed + 1)
    rect(a, 57, 40, 58, 46, (220, 210, 150))
    # plinth
    rect(a, 0, 58, 42, 64, tuple(c * 0.6 for c in wall))
    rect(a, 0, 62, 64, 64, tuple(c * 0.5 for c in wall))
    save(a, name)


def gen_groundfloors():
    gf_shop('gf_shop_a', (190, 44, 44), (120, 110, 100), 200)
    gf_shop('gf_shop_b', (40, 120, 70), (150, 140, 124), 201)
    gf_shop('gf_shop_c', (46, 80, 170), (100, 104, 112), 202, stripes=False)
    gf_shop('gf_shop_d', (214, 160, 40), (132, 96, 84), 203)

    # office lobby
    a = canvas(64, 64, (70, 74, 82))
    noise(a, 4, 210)
    rect(a, 0, 0, 64, 10, (150, 152, 156))
    rect(a, 0, 9, 64, 10, (90, 92, 96))
    glass(a, 2, 12, 62, 62, top=(110, 150, 170), bot=(50, 76, 100), seed=210)
    for x in (2, 21, 42, 61):
        rect(a, x, 12, x + 1, 62, (190, 194, 198))
    rect(a, 2, 36, 62, 37, (190, 194, 198))
    rect(a, 0, 62, 64, 64, (60, 60, 64))
    save(a, 'gf_office')

    # brick + apartment door
    a = brick_wall(64, 64, (130, 70, 56), 211)
    rect(a, 22, 16, 44, 62, (60, 44, 34))
    rect(a, 24, 18, 42, 62, (96, 62, 40))
    rect(a, 27, 22, 39, 34, (40, 56, 70))
    rect(a, 38, 42, 40, 44, (220, 200, 120))
    rect(a, 20, 12, 46, 16, (190, 184, 170))
    rect(a, 4, 30, 14, 46, (190, 184, 170))
    glass(a, 5, 31, 13, 45, seed=3)
    rect(a, 0, 60, 64, 64, (80, 78, 76))
    save(a, 'gf_door')

    # roll-up garage door
    a = canvas(64, 64, (120, 118, 112))
    noise(a, 5, 212)
    rect(a, 5, 9, 59, 64, (60, 60, 62))
    for y in range(11, 64, 4):
        rect(a, 7, y, 57, y + 3, (156, 160, 164))
        rect(a, 7, y + 3, 57, y + 4, (104, 108, 112))
    rect(a, 0, 0, 64, 6, (90, 88, 84))
    save(a, 'gf_garage')

    # blank wall base
    a = canvas(64, 64, (128, 124, 118))
    n = smooth_noise(64, 64, 213, 3, 4)[..., None]
    a[..., :3] += (n - 0.5) * 18
    noise(a, 5, 214)
    rect(a, 0, 52, 64, 64, (92, 90, 86))
    rect(a, 0, 0, 64, 2, (100, 98, 94))
    save(a, 'gf_blank')

    # shuttered ghetto front
    a = canvas(64, 64, (96, 84, 76))
    noise(a, 8, 215)
    rect(a, 4, 12, 60, 60, (50, 50, 54))
    for y in range(14, 60, 3):
        rect(a, 6, y, 58, y + 2, (112, 116, 112))
    img = to_img(a).convert('RGBA')
    d = ImageDraw.Draw(img)
    d.line([(10, 50), (18, 30), (26, 50), (34, 28), (44, 48)], fill=(230, 60, 160), width=2)
    d.ellipse([40, 20, 54, 34], outline=(60, 210, 230), width=2)
    a = from_img(img.convert('RGB'))
    rect(a, 0, 60, 64, 64, (60, 56, 52))
    save(a, 'gf_ghetto')

    # house front (siding + door)
    a = canvas(64, 64, (226, 224, 216))
    for y in range(0, 64, 6):
        rect(a, 0, y, 64, y + 1, (168, 166, 160))
    noise(a, 4, 216)
    rect(a, 22, 12, 44, 64, (250, 250, 246))
    rect(a, 24, 14, 42, 64, (120, 60, 44))
    rect(a, 27, 18, 39, 30, (60, 80, 96))
    rect(a, 38, 40, 40, 42, (230, 210, 120))
    rect(a, 0, 60, 22, 64, (130, 128, 122))
    rect(a, 44, 60, 64, 64, (130, 128, 122))
    save(a, 'gf_house')


# --------------------------------------------------------------------------
# signs & billboards
# --------------------------------------------------------------------------
SIGNS = [
    # name, text, bg, fg, font
    ('sign_shawarma', 'ШАУРМА', (200, 40, 30), (255, 230, 90), 'RussoOne.ttf'),
    ('sign_beer', 'ПИВО', (236, 190, 40), (60, 30, 10), 'RussoOne.ttf'),
    ('sign_pawn', 'ЛОМБАРД', (30, 30, 34), (240, 200, 60), 'RussoOne.ttf'),
    ('sign_pharm', 'АПТЕКА', (240, 240, 236), (30, 150, 70), 'RussoOne.ttf'),
    ('sign_food', 'ПРОДУКТЫ 24', (40, 120, 60), (250, 250, 240), 'OswaldBold.ttf'),
    ('sign_tattoo', 'ТАТУ', (20, 20, 24), (240, 60, 160), 'RussoOne.ttf'),
    ('sign_cafe', 'КАФЕ', (110, 60, 30), (250, 230, 190), 'RussoOne.ttf'),
    ('sign_pizza', 'ПИЦЦА', (30, 110, 50), (250, 250, 250), 'RussoOne.ttf'),
    ('sign_hotel', 'HOTEL', (20, 40, 110), (250, 250, 250), 'RussoOne.ttf'),
    ('sign_casino', 'КАЗИНО', (120, 20, 110), (255, 220, 80), 'RussoOne.ttf'),
    ('sign_gym', 'КАЧАЛКА', (40, 40, 44), (250, 120, 30), 'RussoOne.ttf'),
    ('sign_laundry', 'ПРАЧЕЧНАЯ', (60, 150, 200), (250, 250, 250), 'OswaldBold.ttf'),
    ('sign_flowers', 'ЦВЕТЫ', (230, 120, 170), (250, 250, 250), 'RussoOne.ttf'),
    ('sign_phone', 'РЕМОНТ ТЕЛЕФОНОВ', (250, 220, 40), (20, 20, 20), 'OswaldBold.ttf'),
    ('sign_barber', 'БАРБЕРШОП', (24, 24, 28), (240, 240, 240), 'OswaldBold.ttf'),
    ('sign_sushi', 'СУШИ', (230, 230, 226), (200, 30, 30), 'RussoOne.ttf'),
    ('sign_club', 'КЛУБ «НОЧЬ»', (30, 10, 60), (90, 220, 255), 'OswaldBold.ttf'),
    ('sign_auto', 'АВТОЗАПЧАСТИ', (30, 60, 130), (250, 230, 60), 'OswaldBold.ttf'),
    # landmarks
    ('sign_hospital', 'БОЛЬНИЦА', (244, 244, 240), (200, 30, 30), 'RussoOne.ttf'),
    ('sign_police', 'ПОЛИЦИЯ', (24, 50, 130), (250, 250, 250), 'RussoOne.ttf'),
    ('sign_spray', 'ПОКРАСКА', (250, 210, 40), (200, 30, 40), 'RussoOne.ttf'),
    ('sign_guns', 'ОРУЖИЕ', (40, 40, 40), (240, 60, 40), 'RussoOne.ttf'),
    ('sign_garage', 'ГАРАЖ ВАНО', (30, 90, 160), (250, 250, 250), 'OswaldBold.ttf'),
    ('sign_rosa', 'БАР «РОЗА»', (130, 20, 60), (255, 200, 220), 'OswaldBold.ttf'),
    ('sign_bank', 'БАНК', (20, 70, 50), (240, 210, 110), 'RussoOne.ttf'),
    ('sign_taxi', 'ТАКСИ', (250, 200, 30), (20, 20, 20), 'RussoOne.ttf'),
    ('sign_safehouse', 'ОБЩАГА', (90, 90, 96), (250, 250, 250), 'RussoOne.ttf'),
    ('sign_closed', 'МОСТ ЗАКРЫТ', (250, 140, 30), (20, 20, 20), 'OswaldBold.ttf'),
    ('sign_gas', 'БЕНЗИН', (220, 30, 30), (250, 250, 250), 'RussoOne.ttf'),
    ('sign_port', 'ПОРТ', (30, 60, 100), (250, 250, 250), 'RussoOne.ttf'),
]


def fit_text(d, text, fname, box_w, box_h, start=64):
    size = start
    while size > 6:
        f = font(fname, size)
        l, t, r, b = d.textbbox((0, 0), text, font=f)
        if (r - l) <= box_w and (b - t) <= box_h:
            return f, (l, t, r, b)
        size -= 1
    return f, (l, t, r, b)


def make_sign(text, bg, fg, fname, w=128, h=32, border=True):
    S = 4
    img = Image.new('RGB', (w * S, h * S), bg)
    d = ImageDraw.Draw(img)
    if border:
        d.rectangle([0, 0, w * S - 1, h * S - 1], outline=tuple(int(c * 0.55) for c in bg), width=S * 2)
        d.rectangle([S * 2, S * 2, w * S - 1 - S * 2, h * S - 1 - S * 2], outline=fg, width=S)
    f, (l, t, r, b) = fit_text(d, text, fname, (w - 14) * S, (h - 10) * S, start=h * S)
    x = (w * S - (r - l)) // 2 - l
    y = (h * S - (b - t)) // 2 - t
    d.text((x + S, y + S), text, font=f, fill=tuple(int(c * 0.45) for c in bg))
    d.text((x, y), text, font=f, fill=fg)
    img = img.resize((w, h), Image.LANCZOS)
    a = from_img(img)
    noise(a, 5, len(text) * 7)
    return a


def gen_signs():
    for name, text, bg, fg, fname in SIGNS:
        save(make_sign(text, bg, fg, fname), name)

    # billboards 128 x 64 (10 m x 5 m)
    def bb(name, lines, bg1, bg2, seed):
        S = 4
        w, h = 128, 64
        img = Image.new('RGB', (w * S, h * S), bg1)
        d = ImageDraw.Draw(img)
        for y in range(h * S):
            t = y / (h * S - 1)
            c = tuple(int(bg1[i] * (1 - t) + bg2[i] * t) for i in range(3))
            d.line([(0, y), (w * S, y)], fill=c)
        y = 4 * S
        for (text, fname, hh, col) in lines:
            f, (l, t, r, b) = fit_text(d, text, fname, (w - 10) * S, hh * S, start=hh * S * 2)
            x = (w * S - (r - l)) // 2 - l
            d.text((x + S, y - t + S), text, font=f, fill=(0, 0, 0))
            d.text((x, y - t), text, font=f, fill=col)
            y += (b - t) + 3 * S
        d.rectangle([0, 0, w * S - 1, h * S - 1], outline=(30, 30, 30), width=S * 2)
        img = img.resize((w, h), Image.LANCZOS)
        a = from_img(img)
        noise(a, 5, seed)
        save(a, name)

    bb('bb_shawarma', [('ШАУРМА 24', 'DelaGothicOne.ttf', 22, (255, 230, 60)),
                       ('ВКУС, КОТОРЫЙ', 'OswaldBold.ttf', 12, (255, 255, 255)),
                       ('НЕ ЗАБЫТЬ', 'OswaldBold.ttf', 12, (255, 255, 255))], (200, 50, 20), (110, 20, 10), 301)
    bb('bb_credit', [('КРЕДИТ', 'DelaGothicOne.ttf', 22, (255, 255, 255)),
                     ('ЗА 5 МИНУТ', 'RussoOne.ttf', 14, (250, 230, 80)),
                     ('банк «Честное слово»', 'OswaldBold.ttf', 9, (220, 240, 255))], (20, 80, 160), (10, 30, 80), 302)
    bb('bb_radio', [('РАДИО ВОЛНА', 'RussoOne.ttf', 18, (255, 90, 200)),
                    ('101.5 FM', 'DelaGothicOne.ttf', 20, (90, 230, 255)),
                    ('музыка твоих погонь', 'OswaldBold.ttf', 9, (255, 255, 255))], (40, 10, 70), (10, 0, 30), 303)
    bb('bb_cola', [('КОЛА-ЛОЛА', 'DelaGothicOne.ttf', 22, (255, 255, 255)),
                   ('пузырьки свободы', 'OswaldBold.ttf', 12, (255, 220, 220))], (210, 20, 30), (120, 0, 10), 304)
    bb('bb_lawyer', [('АДВОКАТ', 'RussoOne.ttf', 18, (250, 220, 90)),
                     ('ОТМАЖЕМ ВСЕХ!', 'DelaGothicOne.ttf', 16, (255, 255, 255)),
                     ('звони: 555-0199', 'OswaldBold.ttf', 10, (220, 220, 220))], (30, 30, 36), (70, 60, 40), 305)
    bb('bb_mayor', [('ГОЛОСУЙ', 'RussoOne.ttf', 16, (255, 255, 255)),
                    ('ЗА МЭРА!', 'DelaGothicOne.ttf', 22, (250, 220, 60)),
                    ('он почти не ворует', 'OswaldBold.ttf', 10, (230, 230, 255))], (30, 60, 150), (150, 30, 40), 306)
    bb('bb_game', [('DEADLY', 'DelaGothicOne.ttf', 22, (255, 200, 40)),
                   ('DISTRICT', 'DelaGothicOne.ttf', 22, (255, 255, 255)),
                   ('город, который тебя любит', 'OswaldBold.ttf', 8, (255, 220, 200))], (240, 110, 40), (120, 30, 80), 307)
    bb('bb_gym', [('КАЧАЛКА «ТИТАН»', 'RussoOne.ttf', 14, (255, 140, 30)),
                  ('СТАНЬ ШИРЕ ДВЕРИ', 'DelaGothicOne.ttf', 14, (255, 255, 255))], (30, 30, 34), (10, 10, 12), 308)

    # red cross / police badge emblems for walls (32x32)
    a = canvas(32, 32, (244, 244, 240))
    rect(a, 12, 4, 20, 28, (210, 30, 30))
    rect(a, 4, 12, 28, 20, (210, 30, 30))
    save(a, 'emblem_cross')


# --------------------------------------------------------------------------
# sprites / fx
# --------------------------------------------------------------------------
def radial(size, inner=0.0, power=2.0):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2.0
    d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / c
    v = np.clip(1.0 - (d - inner) / (1.0 - inner), 0, 1) ** power
    return v


def gen_fx():
    # soft additive glow (alpha = intensity)
    v = radial(64, 0.0, 2.2)
    a = canvas(64, 64, (255, 255, 255), alpha=0)
    a[..., 3] = v * 255
    save(a, 'glow')

    # light pool on the ground
    v = radial(64, 0.1, 1.6)
    a = canvas(64, 64, (255, 255, 255), alpha=0)
    a[..., 3] = v * 200
    save(a, 'lightpool')

    # headlight beam on ground: U across, V forward (bottom = car)
    yy, xx = np.mgrid[0:64, 0:64].astype(np.float32)
    v = yy / 63.0                    # 0 top (far) .. 1 bottom (near)
    width = 0.20 + (1 - v) * 0.30
    d = np.abs(xx / 63.0 - 0.5) / width
    inten = np.clip(1 - d, 0, 1) ** 1.5 * np.clip(v * 1.6, 0, 1) ** 0.8 * np.clip((1 - v) * 9, 0, 1)
    a = canvas(64, 64, (255, 250, 230), alpha=0)
    a[..., 3] = inten * 230
    save(a, 'beam')

    # blob shadow
    v = radial(32, 0.25, 1.3)
    a = canvas(32, 32, (0, 0, 0), alpha=0)
    a[..., 3] = v * 150
    save(a, 'shadow')

    # smoke puff
    n = smooth_noise(64, 64, 500, 3, 3)
    v = radial(64, 0.0, 1.4) * (0.55 + 0.75 * n)
    a = canvas(64, 64, (255, 255, 255), alpha=0)
    a[..., :3] = (200 + 55 * n)[..., None]
    a[..., 3] = np.clip(v, 0, 1) * 255
    save(a, 'smoke')

    # fire puff
    n = smooth_noise(64, 64, 501, 3, 3)
    v = radial(64, 0.0, 1.2) * (0.5 + 0.9 * n)
    a = canvas(64, 64, (255, 160, 40), alpha=0)
    core = radial(64, 0.0, 3.0)
    a[..., 0] = 255
    a[..., 1] = 120 + 130 * core
    a[..., 2] = 20 + 180 * core ** 2
    a[..., 3] = np.clip(v, 0, 1) * 255
    save(a, 'fire')

    # spark / star
    a = canvas(32, 32, (255, 240, 180), alpha=0)
    v = radial(32, 0.0, 3.0)
    yy, xx = np.mgrid[0:32, 0:32].astype(np.float32)
    c = 15.5
    cross = np.clip(1 - np.abs(xx - c) / 2.0, 0, 1) * np.clip(1 - np.abs(yy - c) / 15.5, 0, 1) + \
        np.clip(1 - np.abs(yy - c) / 2.0, 0, 1) * np.clip(1 - np.abs(xx - c) / 15.5, 0, 1)
    a[..., 3] = np.clip(v + cross, 0, 1) * 255
    save(a, 'spark')

    # muzzle flash
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pts = []
    for i in range(14):
        ang = i / 14 * 2 * math.pi
        rr = 30 if i % 2 == 0 else 12
        pts.append((32 + math.cos(ang) * rr, 32 + math.sin(ang) * rr))
    d.polygon(pts, fill=(255, 190, 60, 255))
    pts = []
    for i in range(14):
        ang = i / 14 * 2 * math.pi + 0.2
        rr = 18 if i % 2 == 0 else 8
        pts.append((32 + math.cos(ang) * rr, 32 + math.sin(ang) * rr))
    d.polygon(pts, fill=(255, 250, 210, 255))
    save(img, 'muzzle')

    # blood splat
    img = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = rng(502)
    d.ellipse([8, 8, 24, 24], fill=(150, 10, 10, 255))
    for _ in range(12):
        x, y = r.randint(2, 28, 2)
        s = r.randint(1, 5)
        d.ellipse([x, y, x + s, y + s], fill=(150 - r.randint(0, 40), 10, 10, 255))
    save(img, 'blood')

    # white pixel & soft round dot
    save(canvas(4, 4, (255, 255, 255)), 'white')
    v = radial(16, 0.6, 1.0)
    a = canvas(16, 16, (255, 255, 255), alpha=0)
    a[..., 3] = np.clip(v * 4, 0, 1) * 255
    save(a, 'dot')

    # debris chunk
    a = canvas(8, 8, (90, 90, 96), alpha=255)
    noise(a, 30, 503)
    save(a, 'debris')

    # rain streak
    a = canvas(4, 32, (200, 215, 235), alpha=0)
    a[:, 1:3, 3] = np.linspace(0, 170, 32)[:, None]
    save(a, 'rain')

    # stars (night sky)
    a = canvas(128, 128, (0, 0, 0))
    r = rng(504)
    for _ in range(170):
        x, y = r.randint(0, 128, 2)
        b = r.randint(110, 256)
        a[y, x, :3] = (b, b, min(255, b + r.randint(0, 30)))
    save(a, 'stars')

    # cloud
    n = smooth_noise(128, 64, 505, 4, 3)
    yy, xx = np.mgrid[0:64, 0:128].astype(np.float32)
    env = np.clip(1 - ((xx - 64) / 64) ** 2 - ((yy - 32) / 32) ** 2, 0, 1)
    v = np.clip((n * env - 0.22) * 3.0, 0, 1)
    a = canvas(128, 64, (255, 255, 255), alpha=0)
    a[..., :3] = (225 + 30 * n)[..., None]
    a[..., 3] = v * 235
    save(a, 'cloud')

    # sun / moon discs
    v = radial(64, 0.45, 1.0)
    a = canvas(64, 64, (255, 244, 200), alpha=0)
    a[..., 3] = np.clip(v * 3, 0, 1) * 255
    save(a, 'sun')
    a = canvas(64, 64, (226, 232, 246), alpha=0)
    a[..., 3] = np.clip(radial(64, 0.5, 1.0) * 8, 0, 1) * 255
    img = to_img(a)
    d = ImageDraw.Draw(img)
    for (x, y, s) in ((22, 24, 7), (38, 34, 5), (30, 42, 4), (40, 20, 3)):
        d.ellipse([x, y, x + s, y + s], fill=(196, 204, 222, 255))
    save(img, 'moon')

    # tyre track
    a = canvas(16, 16, (20, 20, 22), alpha=0)
    a[:, 3:6, 3] = 150
    a[:, 10:13, 3] = 150
    save(a, 'skid')

    # scorch
    n = smooth_noise(64, 64, 506, 3, 3)
    v = radial(64, 0.0, 1.0) * (0.6 + 0.7 * n)
    a = canvas(64, 64, (16, 14, 12), alpha=0)
    a[..., 3] = np.clip(v, 0, 1) * 220
    save(a, 'scorch')

    # mission marker gradient ring (U around, V up): alpha fades to the top
    a = canvas(8, 32, (255, 255, 255), alpha=0)
    a[..., 3] = (np.linspace(0, 1, 32) ** 1.5 * 255)[:, None]      # top row = transparent
    save(a, 'marker')

    # money note
    a = canvas(32, 16, (70, 150, 80))
    frame(a, 0, 0, 32, 16, (40, 100, 50), 1)
    frame(a, 2, 2, 30, 14, (190, 230, 190), 1)
    img = to_img(a)
    d = ImageDraw.Draw(img)
    d.ellipse([11, 3, 21, 13], outline=(210, 240, 210))
    d.text((13, 2), '$', font=font('RussoOne.ttf', 10), fill=(230, 250, 230))
    save(img, 'money')

    # hidden package wrap
    a = canvas(32, 32, (230, 226, 210))
    noise(a, 8, 507)
    rect(a, 14, 0, 18, 32, (200, 40, 40))
    rect(a, 0, 14, 32, 18, (200, 40, 40))
    save(a, 'package')

    # crate
    a = canvas(32, 32, (150, 110, 64))
    for x in range(0, 32, 8):
        rect(a, x, 0, x + 1, 32, (100, 72, 40))
    noise(a, 8, 508)
    frame(a, 0, 0, 32, 32, (96, 68, 38), 3)
    img = to_img(a)
    d = ImageDraw.Draw(img)
    d.line([(3, 3), (28, 28)], fill=(96, 68, 38), width=3)
    save(img, 'crate')

    # licence plate
    a = canvas(32, 8, (236, 236, 230))
    frame(a, 0, 0, 32, 8, (40, 40, 44), 1)
    img = to_img(a)
    d = ImageDraw.Draw(img)
    d.text((4, -2), 'DD 777', font=font('OswaldBold.ttf', 9), fill=(30, 30, 60))
    save(img, 'plate')


# --------------------------------------------------------------------------
# characters
# --------------------------------------------------------------------------
def gen_peds():
    # faces: white = skin (tinted by vertex colour).  32x32 covers the head front
    def face(name, brow=(60, 40, 30), eye=(30, 30, 40), mouth=(150, 80, 70), beard=None, glasses=False,
             stache=False, female=False, mask=False):
        a = canvas(32, 32, (255, 255, 255))
        # subtle shading
        shade(a, 0, 26, 32, 32, 0.9)
        shade(a, 0, 0, 3, 32, 0.92)
        shade(a, 29, 0, 32, 32, 0.92)
        if mask:
            rect(a, 0, 0, 32, 32, (40, 40, 44))
            rect(a, 6, 10, 13, 15, (255, 255, 255))
            rect(a, 19, 10, 26, 15, (255, 255, 255))
            rect(a, 8, 11, 11, 14, eye)
            rect(a, 21, 11, 24, 14, eye)
            rect(a, 11, 23, 21, 25, (255, 255, 255))
            save(a, name)
            return
        # eyes
        rect(a, 7, 11, 13, 15, (250, 250, 250))
        rect(a, 19, 11, 25, 15, (250, 250, 250))
        rect(a, 9, 11, 12, 15, eye)
        rect(a, 21, 11, 24, 15, eye)
        rect(a, 6, 8, 14, 10, brow)
        rect(a, 18, 8, 26, 10, brow)
        if female:
            rect(a, 6, 10, 14, 11, (30, 30, 30))
            rect(a, 18, 10, 26, 11, (30, 30, 30))
        # nose
        shade(a, 15, 13, 17, 20, 0.86)
        rect(a, 14, 19, 18, 20, (214, 190, 180))
        # mouth
        rect(a, 11, 24, 21, 26, mouth)
        if female:
            rect(a, 12, 23, 20, 24, (200, 60, 70))
            rect(a, 11, 24, 21, 26, (190, 50, 60))
        if stache:
            rect(a, 10, 21, 22, 23, brow)
        if beard:
            rect(a, 4, 22, 28, 32, beard)
            rect(a, 11, 24, 21, 26, mouth)
            rect(a, 0, 16, 5, 32, beard)
            rect(a, 27, 16, 32, 32, beard)
        if glasses:
            rect(a, 5, 9, 15, 17, (20, 20, 24))
            rect(a, 17, 9, 27, 17, (20, 20, 24))
            rect(a, 15, 11, 17, 13, (20, 20, 24))
            rect(a, 6, 10, 14, 16, (60, 70, 90))
            rect(a, 18, 10, 26, 16, (60, 70, 90))
            rect(a, 7, 11, 10, 13, (130, 150, 170))
            rect(a, 19, 11, 22, 13, (130, 150, 170))
        save(a, name)

    face('face_0')
    face('face_1', brow=(30, 24, 20), stache=True)
    face('face_2', brow=(120, 90, 50), eye=(40, 80, 120))
    face('face_3', beard=(70, 50, 36), brow=(70, 50, 36))
    face('face_4', glasses=True)
    face('face_5', female=True, brow=(70, 40, 30))
    face('face_6', female=True, brow=(150, 110, 50), eye=(40, 110, 90))
    face('face_7', brow=(150, 150, 150), stache=True, beard=(170, 170, 170))
    face('face_mask', mask=True)

    # torsos (front), white = cloth colour.  32x32
    def torso(name, kind):
        a = canvas(32, 32, (255, 255, 255))
        shade(a, 0, 26, 32, 32, 0.9)
        shade(a, 0, 0, 2, 32, 0.9)
        shade(a, 30, 0, 32, 32, 0.9)
        if kind == 'tee':
            rect(a, 11, 0, 21, 3, (226, 190, 160))
            shade(a, 10, 3, 22, 4, 0.8)
        elif kind == 'jacket':
            rect(a, 11, 0, 21, 22, (240, 240, 240))          # shirt
            rect(a, 14, 2, 18, 20, (150, 30, 40))            # tie
            for y in range(0, 22):
                w = 5 - y // 5
                shade(a, 11, 0 + y, 11 + max(0, 0), y + 1, 1)
            img = to_img(a)
            d = ImageDraw.Draw(img)
            d.polygon([(11, 0), (16, 22), (11, 22)], fill=(150, 150, 150))
            d.polygon([(21, 0), (16, 22), (21, 22)], fill=(150, 150, 150))
            d.line([(16, 22), (16, 31)], fill=(110, 110, 110))
            a = from_img(img)
            rect(a, 15, 25, 17, 27, (90, 90, 90))
        elif kind == 'stripes':
            for y in range(4, 32, 6):
                rect(a, 0, y, 32, y + 3, (150, 150, 150))
            rect(a, 11, 0, 21, 3, (226, 190, 160))
        elif kind == 'vest':
            rect(a, 0, 0, 32, 32, (255, 255, 255))
            rect(a, 0, 12, 32, 16, (190, 190, 190))
            rect(a, 0, 22, 32, 26, (190, 190, 190))
            rect(a, 15, 0, 17, 32, (120, 120, 120))
        elif kind == 'police':
            rect(a, 15, 0, 17, 32, (200, 200, 200))
            rect(a, 5, 6, 11, 12, (250, 220, 90))            # badge
            rect(a, 20, 8, 27, 14, (190, 190, 190))          # pocket
            rect(a, 0, 28, 32, 32, (60, 60, 60))             # belt
            rect(a, 13, 28, 19, 32, (230, 200, 90))
            rect(a, 11, 0, 21, 2, (140, 160, 220))
        elif kind == 'tank':
            rect(a, 0, 0, 8, 10, (226, 190, 160))
            rect(a, 24, 0, 32, 10, (226, 190, 160))
            rect(a, 11, 0, 21, 6, (226, 190, 160))
        elif kind == 'hoodie':
            rect(a, 9, 0, 23, 5, (200, 200, 200))
            rect(a, 13, 4, 14, 14, (230, 230, 230))
            rect(a, 18, 4, 19, 14, (230, 230, 230))
            rect(a, 8, 20, 24, 28, (214, 214, 214))
            rect(a, 8, 20, 24, 21, (170, 170, 170))
        elif kind == 'armor':
            rect(a, 3, 2, 29, 26, (120, 120, 120))
            rect(a, 6, 8, 26, 12, (230, 230, 230))
            rect(a, 6, 16, 14, 23, (90, 90, 90))
            rect(a, 18, 16, 26, 23, (90, 90, 90))
            rect(a, 0, 28, 32, 32, (60, 60, 60))
        save(a, name)

    for k in ('tee', 'jacket', 'stripes', 'vest', 'police', 'tank', 'hoodie', 'armor'):
        torso('torso_' + k, k)


# --------------------------------------------------------------------------
# HUD / UI
# --------------------------------------------------------------------------
def outline_img(img, color=(0, 0, 0, 255), r=2):
    """add a hard outline around the non-transparent pixels"""
    a = img.split()[3]
    big = a.filter(ImageFilter.MaxFilter(r * 2 + 1))
    base = Image.new('RGBA', img.size, color)
    base.putalpha(big)
    base.alpha_composite(img)
    return base


def star_points(cx, cy, ro, ri, n=5, rot=-math.pi / 2):
    pts = []
    for i in range(n * 2):
        ang = rot + i * math.pi / n
        rr = ro if i % 2 == 0 else ri
        pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
    return pts


def gen_ui():
    S = 4

    def hi(w, h):
        return Image.new('RGBA', (w * S, h * S), (0, 0, 0, 0))

    def lo(img, w, h, outline=True):
        img = img.resize((w, h), Image.LANCZOS)
        if outline:
            img = outline_img(img, r=1)
        return img

    # wanted stars
    img = hi(32, 32)
    d = ImageDraw.Draw(img)
    d.polygon([(x * S, y * S) for x, y in star_points(16, 17, 13, 5.6)], fill=(255, 196, 30, 255))
    d.polygon([(x * S, y * S) for x, y in star_points(16, 17, 8, 3.4)], fill=(255, 232, 110, 255))
    save(lo(img, 32, 32), 'hud_star')
    img = hi(32, 32)
    d = ImageDraw.Draw(img)
    d.polygon([(x * S, y * S) for x, y in star_points(16, 17, 13, 5.6)], fill=(40, 40, 46, 170))
    save(lo(img, 32, 32, outline=False), 'hud_star_off')

    # heart
    img = hi(32, 32)
    d = ImageDraw.Draw(img)
    d.ellipse([4 * S, 5 * S, 17 * S, 18 * S], fill=(230, 40, 50, 255))
    d.ellipse([15 * S, 5 * S, 28 * S, 18 * S], fill=(230, 40, 50, 255))
    d.polygon([(4.6 * S, 14 * S), (27.4 * S, 14 * S), (16 * S, 28 * S)], fill=(230, 40, 50, 255))
    d.ellipse([7 * S, 8 * S, 12 * S, 12 * S], fill=(255, 150, 150, 255))
    save(lo(img, 32, 32), 'hud_heart')

    # armor
    img = hi(32, 32)
    d = ImageDraw.Draw(img)
    d.polygon([(16 * S, 3 * S), (28 * S, 7 * S), (26 * S, 20 * S), (16 * S, 29 * S), (6 * S, 20 * S), (4 * S, 7 * S)],
              fill=(60, 140, 230, 255))
    d.polygon([(16 * S, 6 * S), (16 * S, 26 * S), (8 * S, 19 * S), (7 * S, 9 * S)], fill=(120, 190, 255, 255))
    save(lo(img, 32, 32), 'hud_armor')

    # crosshair
    img = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for (x0, y0, x1, y1) in ((15, 3, 16, 11), (15, 20, 16, 28), (3, 15, 11, 16), (20, 15, 28, 16)):
        d.rectangle([x0 - 1, y0 - 1, x1 + 1, y1 + 1], fill=(0, 0, 0, 200))
    for (x0, y0, x1, y1) in ((15, 3, 16, 11), (15, 20, 16, 28), (3, 15, 11, 16), (20, 15, 28, 16)):
        d.rectangle([x0, y0, x1, y1], fill=(255, 255, 255, 255))
    d.rectangle([15, 15, 16, 16], fill=(255, 60, 60, 255))
    save(img, 'crosshair')

    # weapon icons 64x64 (hi-res polygons)
    def wicon(name, draw):
        img = hi(64, 64)
        d = ImageDraw.Draw(img)

        def P(pts, col):
            d.polygon([(x * S, y * S) for x, y in pts], fill=col)

        def R(x0, y0, x1, y1, col):
            d.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)

        def E(x0, y0, x1, y1, col):
            d.ellipse([x0 * S, y0 * S, x1 * S, y1 * S], fill=col)
        draw(P, R, E)
        img = img.resize((64, 64), Image.LANCZOS)
        img = outline_img(img, r=2)
        save(img, name)

    steel = (70, 74, 84, 255)
    steel_l = (120, 126, 140, 255)
    woodc = (140, 92, 50, 255)
    black = (34, 34, 40, 255)

    def fist(P, R, E):
        skin = (236, 190, 150, 255)
        R(14, 24, 44, 48, skin)
        for i in range(4):
            E(13 + i * 8, 16, 22 + i * 8, 28, skin)
        P([(36, 30), (52, 26), (54, 36), (42, 44)], skin)
        R(14, 46, 40, 56, (220, 220, 230, 255))
        for i in range(1, 4):
            R(13 + i * 8, 20, 13.6 + i * 8, 34, (190, 140, 110, 255))
    wicon('w_fist', fist)

    def bat(P, R, E):
        P([(8, 52), (12, 56), (52, 18), (56, 10), (48, 8), (44, 14)], woodc)
        P([(8, 52), (12, 56), (20, 49), (16, 45)], black)
        P([(46, 12), (52, 10), (50, 16)], (190, 140, 90, 255))
    wicon('w_bat', bat)

    def pistol(P, R, E):
        R(10, 20, 54, 30, steel)
        R(10, 20, 54, 23, steel_l)
        P([(14, 30), (28, 30), (24, 52), (12, 52)], black)
        R(28, 30, 36, 32, steel)
        P([(28, 31), (36, 31), (34, 40), (30, 40)], (0, 0, 0, 0))
        R(50, 17, 53, 20, black)
        R(40, 23, 50, 25, black)
    wicon('w_pistol', pistol)

    def uzi(P, R, E):
        R(8, 20, 48, 32, steel)
        R(8, 20, 48, 23, steel_l)
        R(48, 23, 60, 28, black)
        P([(24, 32), (34, 32), (33, 56), (25, 56)], black)
        P([(8, 22), (4, 22), (4, 44), (8, 44), (8, 40), (6, 40), (6, 26), (8, 26)], steel)
        R(36, 32, 42, 38, steel)
        R(14, 16, 18, 20, black)
    wicon('w_uzi', uzi)

    def shotgun(P, R, E):
        R(18, 24, 62, 28, steel)
        R(24, 29, 60, 32, steel_l)
        R(30, 28, 44, 35, woodc)
        P([(2, 30), (20, 23), (20, 32), (4, 42)], woodc)
        R(18, 28, 24, 34, black)
    wicon('w_shotgun', shotgun)

    def ak(P, R, E):
        R(16, 22, 46, 30, steel)
        R(46, 24, 62, 27, black)
        R(56, 20, 58, 24, black)
        R(30, 18, 50, 22, woodc)
        P([(2, 26), (16, 22), (16, 30), (2, 36)], woodc)
        P([(30, 30), (38, 30), (44, 48), (36, 50)], black)
        P([(20, 30), (26, 30), (24, 42), (18, 42)], woodc)
    wicon('w_ak', ak)

    def rocket(P, R, E):
        R(6, 24, 50, 32, (70, 90, 60, 255))
        R(6, 24, 50, 26, (110, 130, 90, 255))
        P([(50, 20), (62, 28), (50, 36)], (120, 60, 50, 255))
        P([(2, 20), (8, 24), (8, 32), (2, 36)], (50, 64, 44, 255))
        R(24, 32, 30, 44, black)
        R(36, 32, 40, 40, black)
        R(28, 18, 36, 24, black)
    wicon('w_rocket', rocket)

    def grenade(P, R, E):
        E(18, 22, 46, 56, (60, 90, 50, 255))
        R(27, 14, 37, 24, steel)
        P([(37, 14), (48, 18), (46, 30), (42, 30), (43, 20), (37, 18)], steel_l)
        E(18, 8, 28, 18, (0, 0, 0, 0))
        for i in range(3):
            R(20, 30 + i * 8, 44, 31 + i * 8, (40, 64, 34, 255))
        R(31, 24, 32.2, 54, (40, 64, 34, 255))
    wicon('w_grenade', grenade)

    def molotov(P, R, E):
        P([(24, 28), (40, 28), (42, 56), (22, 56)], (60, 130, 80, 255))
        R(28, 16, 36, 28, (60, 130, 80, 255))
        R(26, 36, 38, 46, (230, 220, 190, 255))
        P([(30, 16), (34, 16), (40, 6), (30, 10)], (230, 230, 220, 255))
        P([(36, 8), (44, 2), (42, 10), (46, 12), (38, 14)], (255, 150, 30, 255))
    wicon('w_molotov', molotov)

    # radar blips (32x32: степень двойки нужна старым видеокартам) --------------------------------------------------
    def blip(name, draw, size=32, outline=True):
        img = hi(size, size)
        d = ImageDraw.Draw(img)
        draw(d, size * S)
        img = img.resize((size, size), Image.LANCZOS)
        if outline:
            img = outline_img(img, r=1)
        save(img, name)

    def b_player(d, s):
        d.polygon([(s * 0.5, s * 0.06), (s * 0.86, s * 0.9), (s * 0.5, s * 0.68), (s * 0.14, s * 0.9)],
                  fill=(255, 255, 255, 255))
    blip('blip_player', b_player)

    def b_square(col):
        def f(d, s):
            d.rectangle([s * 0.24, s * 0.24, s * 0.76, s * 0.76], fill=col)
        return f
    blip('blip_dest', b_square((255, 220, 40, 255)))
    blip('blip_enemy', b_square((240, 50, 50, 255)))
    blip('blip_friend', b_square((70, 170, 255, 255)))
    blip('blip_pickup', b_square((90, 230, 110, 255)))

    def b_police(d, s):
        d.ellipse([s * 0.22, s * 0.22, s * 0.78, s * 0.78], fill=(60, 110, 255, 255))
    blip('blip_police', b_police)

    def b_letter(letter, bg, fg=(255, 255, 255, 255)):
        def f(d, s):
            d.rounded_rectangle([s * 0.08, s * 0.08, s * 0.92, s * 0.92], radius=s * 0.16, fill=bg)
            fnt = font('RussoOne.ttf', int(s * 0.7))
            l, t, r, b = d.textbbox((0, 0), letter, font=fnt)
            d.text(((s - (r - l)) / 2 - l, (s - (b - t)) / 2 - t), letter, font=fnt, fill=fg)
        return f
    blip('blip_vano', b_letter('В', (40, 110, 200, 255)))
    blip('blip_rosa', b_letter('Р', (200, 40, 110, 255)))
    blip('blip_prof', b_letter('П', (60, 160, 70, 255)))
    blip('blip_save', b_letter('S', (240, 240, 240, 255), (30, 30, 30, 255)))
    blip('blip_taxi', b_letter('T', (250, 200, 30, 255), (20, 20, 20, 255)))

    def b_hospital(d, s):
        d.rounded_rectangle([s * 0.08, s * 0.08, s * 0.92, s * 0.92], radius=s * 0.16, fill=(250, 250, 250, 255))
        d.rectangle([s * 0.4, s * 0.2, s * 0.6, s * 0.8], fill=(220, 30, 30, 255))
        d.rectangle([s * 0.2, s * 0.4, s * 0.8, s * 0.6], fill=(220, 30, 30, 255))
    blip('blip_hospital', b_hospital)

    def b_cop(d, s):
        d.rounded_rectangle([s * 0.08, s * 0.08, s * 0.92, s * 0.92], radius=s * 0.16, fill=(30, 60, 150, 255))
        d.polygon(star_points(s * 0.5, s * 0.52, s * 0.34, s * 0.15), fill=(250, 210, 60, 255))
    blip('blip_station', b_cop)

    def b_spray(d, s):
        d.rounded_rectangle([s * 0.08, s * 0.08, s * 0.92, s * 0.92], radius=s * 0.16, fill=(250, 210, 40, 255))
        d.rectangle([s * 0.36, s * 0.38, s * 0.66, s * 0.84], fill=(200, 30, 40, 255))
        d.rectangle([s * 0.44, s * 0.22, s * 0.58, s * 0.38], fill=(60, 60, 60, 255))
        d.ellipse([s * 0.62, s * 0.14, s * 0.82, s * 0.34], fill=(250, 250, 250, 255))
    blip('blip_spray', b_spray)

    def b_gun(d, s):
        d.rounded_rectangle([s * 0.08, s * 0.08, s * 0.92, s * 0.92], radius=s * 0.16, fill=(40, 40, 44, 255))
        d.rectangle([s * 0.2, s * 0.32, s * 0.82, s * 0.5], fill=(230, 230, 230, 255))
        d.polygon([(s * 0.24, s * 0.5), (s * 0.46, s * 0.5), (s * 0.4, s * 0.82), (s * 0.22, s * 0.82)],
                  fill=(230, 230, 230, 255))
    blip('blip_guns', b_gun)

    def b_north(d, s):
        d.ellipse([s * 0.06, s * 0.06, s * 0.94, s * 0.94], fill=(20, 20, 24, 255))
        fnt = font('RussoOne.ttf', int(s * 0.62))
        l, t, r, b = d.textbbox((0, 0), 'N', font=fnt)
        d.text(((s - (r - l)) / 2 - l, (s - (b - t)) / 2 - t), 'N', font=fnt, fill=(255, 255, 255, 255))
    blip('blip_north', b_north, outline=False)

    def b_race(d, s):
        d.rounded_rectangle([s * 0.08, s * 0.08, s * 0.92, s * 0.92], radius=s * 0.16, fill=(250, 250, 250, 255))
        q = s * 0.21
        for i in range(4):
            for j in range(4):
                if (i + j) % 2 == 0:
                    d.rectangle([s * 0.08 + i * q, s * 0.08 + j * q, s * 0.08 + (i + 1) * q, s * 0.08 + (j + 1) * q],
                                fill=(20, 20, 20, 255))
    blip('blip_race', b_race)

    # radar ring 128x128
    img = Image.new('RGBA', (128 * S, 128 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2 * S, 2 * S, 126 * S, 126 * S], outline=(10, 10, 12, 255), width=5 * S)
    d.ellipse([4 * S, 4 * S, 124 * S, 124 * S], outline=(120, 124, 132, 255), width=S)
    save(img.resize((128, 128), Image.LANCZOS), 'radar_ring')

    # vignette for menus / low health
    v = 1 - radial(128, 0.25, 1.0)
    a = canvas(128, 128, (0, 0, 0), alpha=0)
    a[..., 3] = np.clip(v, 0, 1) ** 1.6 * 230
    save(a, 'vignette')

    # arrow (3d marker above targets is geometry; this is a 2d hint arrow)
    img = hi(32, 32)
    d = ImageDraw.Draw(img)
    d.polygon([(16 * S, 30 * S), (2 * S, 12 * S), (10 * S, 12 * S), (10 * S, 2 * S),
               (22 * S, 2 * S), (22 * S, 12 * S), (30 * S, 12 * S)], fill=(255, 220, 40, 255))
    save(lo(img, 32, 32), 'arrow')

    # app icon -----------------------------------------------------------
    def icon(size):
        s = 256 * 2
        img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([8, 8, s - 8, s - 8], radius=90, fill=(20, 18, 26, 255))
        # sunset gradient disc
        for y in range(60, 330):
            t = (y - 60) / 270
            c = (int(255 - 20 * t), int(200 - 150 * t), int(60 + 70 * t), 255)
            half = math.sqrt(max(0, 135 ** 2 - (y - 195) ** 2))
            if half > 0:
                d.line([(s / 2 - half, y), (s / 2 + half, y)], fill=c)
        # skyline
        r = rng(4242)
        x = 40
        while x < s - 40:
            w = r.randint(28, 60)
            h = r.randint(60, 200)
            d.rectangle([x, 350 - h, x + w, 352], fill=(20, 18, 26, 255))
            for wy in range(350 - h + 8, 344, 14):
                for wx in range(x + 6, x + w - 6, 12):
                    if r.rand() < 0.35:
                        d.rectangle([wx, wy, wx + 5, wy + 6], fill=(255, 210, 110, 255))
            x += w + 4
        d.rectangle([8, 350, s - 8, 356], fill=(20, 18, 26, 255))
        f = font('DelaGothicOne.ttf', 150)
        l, t, r2, b = d.textbbox((0, 0), 'DD', font=f)
        tx = (s - (r2 - l)) / 2 - l
        ty = 342 - t
        for dx in range(-7, 8):
            for dy in range(-7, 8):
                if dx * dx + dy * dy <= 49:
                    d.text((tx + dx, ty + dy), 'DD', font=f, fill=(0, 0, 0, 255))
        d.text((tx, ty), 'DD', font=f, fill=(255, 255, 255, 255))
        d.polygon(star_points(s / 2, 96, 34, 14), fill=(255, 196, 30, 255))
        return img.resize((size, size), Image.LANCZOS)

    icon_dir = os.path.join(ROOT, 'assets', 'icon')
    os.makedirs(icon_dir, exist_ok=True)
    for sz in (256, 128, 64, 48, 32, 16):
        icon(sz).save(os.path.join(icon_dir, 'icon-%d.png' % sz))
    icon(256).save(os.path.join(icon_dir, 'icon.ico'), sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


# --------------------------------------------------------------------------
def contact_sheet(path):
    cell = 100
    cols = 12
    rows = (len(_written) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell, rows * cell), (70, 40, 90))
    d = ImageDraw.Draw(sheet)
    f = font('OswaldBold.ttf', 10)
    for i, (name, img) in enumerate(_written):
        x, y = (i % cols) * cell, (i // cols) * cell
        im = img.convert('RGBA')
        scale = min(84 / im.width, 78 / im.height)
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.NEAREST)
        sheet.paste(im, (x + 4, y + 4), im)
        d.text((x + 3, y + 86), name[:18], font=f, fill=(255, 255, 255))
    sheet.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sheet', default=None)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    gen_ground()
    gen_facades()
    gen_groundfloors()
    gen_signs()
    gen_fx()
    gen_peds()
    gen_ui()
    print('textures written:', len(_written), '->', OUT)
    if args.sheet:
        contact_sheet(args.sheet)
        print('sheet:', args.sheet)


if __name__ == '__main__':
    main()
