# -*- coding: utf-8 -*-
"""Текстуры интерьеров: полы, стены, потолок, двери, окна, плакаты, полки с бутылками и книгами, стенды.

    python tools/gen_interior.py [--sheet лист.png]

Материалы берутся из того же открытого сборника, что и фасады города (см. tools/gen_city.py), остальное
рисуется здесь.  Все файлы называются assets/tex/int_*.png.
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_city as gc                                   # noqa: E402
from gen_city import src, tone, tiled, resize, img, arr, box, shade, grime, smooth_noise, _grey     # noqa: E402

OUT = gc.OUT
FONTS = os.path.join(gc.ROOT, 'assets', 'fonts')
made = []


def save(a, name, colors=64, w=None, h=None):
    im = a if isinstance(a, Image.Image) else img(a)
    if w:
        im = im.resize((w, h), Image.LANCZOS)
    pw, ph = pot(im.size[0]), pot(im.size[1])        # стороны — степени двойки: так текстуру примет любая видеокарта
    if (pw, ph) != im.size:
        im = im.resize((pw, ph), Image.LANCZOS)
    if colors and im.mode == 'RGB':
        im = im.quantize(colors, method=Image.MEDIANCUT, dither=Image.NONE)
    im.save(os.path.join(OUT, name + '.png'), optimize=True)
    made.append(name)


def pot(n):
    """Ближайшая степень двойки."""
    p = 1
    while p * 2 <= n:
        p *= 2
    return p * 2 if n - p > p * 2 - n else p


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def canvas(w, h, color):
    a = np.zeros((h, w, 3), np.float32)
    a[:] = color
    return a


def noise(a, amount, seed):
    r = np.random.RandomState(seed)
    a += (r.rand(a.shape[0], a.shape[1], 1).astype(np.float32) - 0.5) * 2.0 * amount


def frame(a, x0, y0, x1, y1, color, t=1):
    box(a, x0, y0, x1, y0 + t, color)
    box(a, x0, y1 - t, x1, y1, color)
    box(a, x0, y0, x0 + t, y1, color)
    box(a, x1 - t, y0, x1, y1, color)


def gen_materials():
    save(_grey(tiled(src('Walls/wall_stucco_03.jpg'), 64, 64, 1, 1), 214.0, 1.25), 'int_wall', 32)
    # обои в полоску (красятся)
    a = canvas(64, 64, (214, 214, 214))
    for x in range(0, 64, 16):
        a[:, x:x + 6] *= 0.90
        a[:, x + 9:x + 10] *= 0.94
    a *= (0.96 + 0.08 * smooth_noise(64, 64, 5, 4)[..., None])
    noise(a, 3, 6)
    save(a, 'int_paper', 32)
    p = arr(gc.src_rgba('Wood/wood_planks_tan.png').convert('RGB'))
    save(tone(resize(p[:128], 64, 64), mul=(0.86, 0.72, 0.56), contrast=1.2), 'int_panel', 48)
    save(tone(resize(src('Wood/wood_planks_fancy_01.jpg'), 128, 128), mul=(1.0, 0.94, 0.86)), 'int_parquet', 64)
    save(tone(resize(src('Wood/wood_fancy_02.jpg'), 128, 128), mul=(0.88, 0.84, 0.80)), 'int_planks', 64)
    save(tone(resize(src('Wood/wood_fancy_04.jpg'), 64, 64), mul=(0.78, 0.70, 0.64)), 'int_wooddark', 48)
    save(resize(src('Tiles/tile_clean_tan.png'), 64, 64), 'int_tile', 32)
    save(tone(resize(src('Tiles/tile_modern_white.png'), 64, 64), mul=(0.96, 0.98, 1.0)), 'int_tilew', 32)
    save(_grey(resize(arr(gc.src_rgba('Floor/carpet_darkgray_01.png').convert('RGB')), 64, 64), 190.0, 1.3),
         'int_carpet', 32)
    c = arr(gc.src_rgba('Tiles/tiles_ceiling.png').convert('RGB'))
    save(tone(resize(c, 64, 64), mul=(0.97, 0.97, 0.95)), 'int_ceil', 32)
    save(resize(src('Misc/marbel_01.jpg'), 64, 64), 'int_marble', 48)
    save(_grey(resize(src('Misc/leather_01.jpg'), 64, 64), 190.0, 1.3), 'int_leather', 32)
    # шахматная плитка
    a = canvas(64, 64, (226, 222, 212))
    box(a, 0, 0, 32, 32, (44, 42, 44))
    box(a, 32, 32, 64, 64, (44, 42, 44))
    a *= (0.9 + 0.14 * smooth_noise(64, 64, 9, 4)[..., None])
    for k in (0, 32):
        a[k:k + 1] *= 0.8
        a[:, k:k + 1] *= 0.8
    save(a, 'int_checker', 32)
    # бетонный пол мастерской с масляными пятнами
    a = _grey(tiled(arr(gc.src_rgba('Concrete/concrete_01.png').convert('RGB')), 128, 128, 2, 2), 150.0, 1.2)
    n = smooth_noise(128, 128, 21, 3)
    a *= (1.0 - 0.45 * np.clip((n - 0.56) * 6.0, 0, 1))[..., None]
    for k in (0, 64):
        a[k:k + 1] *= 0.7
        a[:, k:k + 1] *= 0.7
    save(a, 'int_garage', 32)


def gen_doors():
    for name, s in (('int_door', 'Doors/door_professional_01.png'), ('int_door_metal', 'Doors/door_industral_01.jpg'),
                    ('int_door_old', 'Doors/door_old_01.jpg'), ('int_door_shop', 'Doors/door_business_01.jpg')):
        if s.endswith('.png'):
            a = arr(gc.src_rgba(s).convert('RGB'))
        else:
            a = src(s)
        save(resize(a, 64, 128), name, 64)
    # окно: рама и светлое небо за стеклом (рисуется без освещения, ночью темнеет)
    a = canvas(64, 96, (236, 234, 226))
    for (x0, x1) in ((5, 30), (34, 59)):
        for (y0, y1) in ((5, 44), (48, 91)):
            for y in range(y0, y1):
                t = (y - 5) / 86.0
                a[y, x0:x1] = (150 + 80 * t, 190 + 50 * t, 236 + 14 * t)
            a[y0:y0 + 2, x0:x1] *= 0.78
            a[y0:y1, x0:x0 + 1] *= 0.84
    n = smooth_noise(64, 96, 3, 3)
    a[5:91, 5:59] += (n[5:91, 5:59, None] - 0.5) * 34
    save(a, 'int_window', 48)
    # занавешенное окно бара / закрашенное окно гаража
    a = canvas(64, 48, (64, 70, 76))
    for x in range(0, 64, 16):
        box(a, x + 1, 1, x + 15, 47, (148, 172, 184))
        a[1:47, x + 1:x + 15] *= (0.74 + 0.4 * smooth_noise(14, 46, 30 + x, 2))[..., None]
    box(a, 0, 23, 64, 25, (64, 70, 76))
    save(a, 'int_window_ind', 32)


def gen_wall_things():
    save(resize(src('Art/art_vintage_01.jpg'), 64, 80), 'int_poster_a', 48)
    save(resize(src('Art/art_vintage_02.jpg'), 64, 108), 'int_poster_b', 48)
    save(resize(arr(gc.src_rgba('Art/poster_infomation.png').convert('RGB')), 70, 64), 'int_notice', 48)
    save(resize(src('Misc/filingcabinet_01.jpg'), 64, 124), 'int_filing', 48)
    save(resize(src('Doors/door_store_drinks_01.jpg'), 64, 144), 'int_drinks', 64)
    save(resize(src('Doors/door_store_food_01.jpg'), 64, 147), 'int_snacks', 64)

    # полка бара: бутылки на фоне зеркала
    r = np.random.RandomState(4)
    a = canvas(128, 64, (40, 30, 26))
    for row in range(2):
        y1 = 30 + row * 32
        box(a, 0, y1 - 28, 128, y1, (66, 78, 84))
        a[y1 - 28:y1] *= (0.8 + 0.4 * smooth_noise(128, 28, 40 + row, 3))[..., None]
        box(a, 0, y1, 128, y1 + 3, (96, 64, 40))
        x = 3
        while x < 122:
            w = int(r.choice((5, 6, 6, 7)))
            h = int(r.randint(15, 25))
            col = np.array(r.choice(len(BOTTLES)))
            col = np.array(BOTTLES[int(col)], np.float32)
            box(a, x, y1 - h + 6, x + w, y1, col)
            box(a, x + w // 2 - 1, y1 - h, x + w // 2 + 1, y1 - h + 6, col * 0.8)
            box(a, x, y1 - h // 2 - 2, x + w, y1 - h // 2 + 3, col * 0.35 + 150)
            a[y1 - h + 6:y1, x:x + 1] *= 1.35
            x += w + int(r.randint(1, 4))
    save(a, 'int_bottles', 64)

    # книжная полка: корешки
    r = np.random.RandomState(8)
    a = canvas(64, 64, (58, 40, 28))
    for row in range(2):
        y1 = 29 + row * 32
        box(a, 0, y1 - 27, 64, y1, (30, 22, 18))
        box(a, 0, y1, 64, y1 + 3, (96, 66, 44))
        x = 1
        while x < 61:
            w = int(r.randint(2, 6))
            h = int(r.randint(18, 27))
            col = np.array(BOOKS[int(r.randint(len(BOOKS)))], np.float32) * r.uniform(0.75, 1.1)
            box(a, x, y1 - h, min(63, x + w), y1, col)
            if w > 3:
                box(a, x + 1, y1 - h + 3, x + w - 1, y1 - h + 5, col * 0.4 + 140)
            a[y1 - h:y1, x:x + 1] *= 0.8
            x += w
    save(a, 'int_books', 64)

    # стена оружейного магазина: перфорированный щит и товар
    a = canvas(128, 64, (118, 100, 76))
    a[::4, ::4] *= 0.62
    a *= (0.92 + 0.14 * smooth_noise(128, 64, 12, 3)[..., None])
    icons = ('w_ak', 'w_shotgun', 'w_uzi', 'w_pistol', 'w_rocket', 'w_bat')
    slots = ((4, 4, 58, 26), (66, 4, 58, 26), (4, 36, 36, 24), (46, 36, 30, 24), (80, 34, 44, 26))
    im = img(a).convert('RGBA')
    for k, (x, y, w, h) in enumerate(slots):
        ic = Image.open(os.path.join(OUT, icons[k] + '.png')).convert('RGBA')
        bb = ic.getbbox()
        if bb:
            ic = ic.crop(bb)
        ic.thumbnail((w, h), Image.LANCZOS)
        sh = Image.new('RGBA', ic.size, (0, 0, 0, 0))
        sh.paste((20, 16, 12, 150), (0, 0), ic.split()[3])
        im.alpha_composite(sh, (x + (w - ic.size[0]) // 2 + 2, y + (h - ic.size[1]) // 2 + 2))
        im.alpha_composite(ic, (x + (w - ic.size[0]) // 2, y + (h - ic.size[1]) // 2))
    save(im.convert('RGB'), 'int_gunwall', 64)

    # щит с инструментом
    im = img(canvas(128, 64, (104, 110, 116)))
    d = ImageDraw.Draw(im)
    for x in range(0, 128, 4):
        for y in range(0, 64, 4):
            d.point((x, y), fill=(70, 74, 80))
    steel, red, dark = (196, 200, 206), (190, 40, 30), (40, 40, 44)
    for i in range(6):                                      # ключи по росту
        x = 6 + i * 9
        h = 40 - i * 4
        d.line([(x, 8), (x, 8 + h)], fill=steel, width=2)
        d.ellipse([x - 3, 4, x + 3, 10], outline=steel, width=2)
        d.ellipse([x - 2, 6 + h, x + 2, 11 + h], outline=steel, width=1)
    d.rectangle([64, 8, 67, 44], fill=(150, 104, 60))        # молоток
    d.rectangle([58, 6, 74, 13], fill=dark)
    d.line([(82, 8), (82, 40)], fill=steel, width=2)         # отвёртки
    d.rectangle([80, 40, 84, 52], fill=red)
    d.line([(90, 8), (90, 34)], fill=steel, width=2)
    d.rectangle([88, 34, 92, 46], fill=(230, 180, 30))
    d.arc([98, 6, 122, 30], 200, 520, fill=dark, width=3)    # ремень / шланг
    d.rectangle([100, 36, 120, 56], outline=red, width=2)    # ножовка
    d.line([(100, 56), (120, 56)], fill=steel, width=1)
    save(im, 'int_tools', 48)

    # пробковая доска с бумагами
    a = canvas(64, 48, (170, 128, 84))
    noise(a, 12, 2)
    frame(a, 0, 0, 64, 48, (92, 62, 40), 2)
    r = np.random.RandomState(3)
    paper = resize(arr(gc.src_rgba('Papers/paper_log_1.png').convert('RGB')), 14, 18)
    for (x, y) in ((5, 5), (24, 7), (44, 4), (8, 27), (30, 28), (46, 26)):
        p = paper * r.uniform(0.9, 1.04)
        if r.rand() < 0.4:
            p = canvas(18, 14, (244, 226, 120))
        gc.paste(a, p, x, y)
        box(a, x + 5, y, x + 7, y + 2, (200, 40, 40))
    save(a, 'int_board', 48)

    # стенд «Их разыскивает полиция»
    im = img(canvas(64, 64, (226, 226, 216)))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 63, 63], outline=(40, 60, 110), width=2)
    d.rectangle([2, 2, 61, 13], fill=(40, 60, 110))
    f = font('OswaldBold.ttf', 10)
    d.text((32, 7), 'РОЗЫСК', font=f, fill=(250, 250, 250), anchor='mm')
    r = np.random.RandomState(6)
    for i in range(6):
        x, y = 5 + (i % 3) * 19, 17 + (i // 3) * 23
        d.rectangle([x, y, x + 15, y + 19], fill=(200, 200, 196), outline=(90, 90, 90))
        c = tuple(int(v) for v in r.randint(40, 110, 3))
        d.ellipse([x + 4, y + 3, x + 11, y + 10], fill=c)
        d.rectangle([x + 2, y + 11, x + 13, y + 16], fill=c)
        d.line([(x + 2, y + 18), (x + 13, y + 18)], fill=(60, 60, 60))
    save(im, 'int_wanted', 48)

    # экран телевизора: прогноз погоды
    im = img(canvas(64, 48, (30, 60, 120)))
    d = ImageDraw.Draw(im)
    for y in range(48):
        d.line([(0, y), (64, y)], fill=(24 + y, 60 + y * 2, 130 + y))
    d.polygon([(6, 30), (14, 16), (26, 12), (40, 18), (52, 14), (58, 26), (50, 38), (30, 42), (14, 40)],
              fill=(70, 150, 80))
    d.ellipse([40, 6, 50, 16], fill=(250, 220, 80))
    d.ellipse([14, 20, 26, 27], fill=(236, 236, 240))
    d.rectangle([0, 40, 64, 48], fill=(190, 30, 30))
    d.text((32, 44), 'ПОГОДА', font=font('OswaldBold.ttf', 8), fill=(255, 255, 255), anchor='mm')
    a = arr(im)
    a[::2] *= 0.86
    save(a, 'int_tv', 48)

    # монитор с текстом
    a = canvas(32, 24, (10, 26, 16))
    r = np.random.RandomState(10)
    for y in range(3, 21, 3):
        box(a, 2, y, 2 + int(r.randint(8, 28)), y + 1, (80, 230, 120))
    save(a, 'int_screen', 16)

    # ковёр
    a = canvas(64, 96, (150, 40, 36))
    frame(a, 0, 0, 64, 96, (36, 24, 30), 3)
    frame(a, 5, 5, 59, 91, (214, 180, 110), 2)
    for cy in (26, 48, 70):
        for k in range(12):
            box(a, 32 - k, cy - 12 + k, 32 + k, cy - 11 + k, (214, 180, 110))
            box(a, 32 - k, cy + 11 - k, 32 + k, cy + 12 - k, (214, 180, 110))
        box(a, 29, cy - 3, 35, cy + 3, (30, 50, 90))
    a *= (0.9 + 0.16 * smooth_noise(64, 96, 14, 5)[..., None])
    noise(a, 7, 15)
    save(a, 'int_rug', 48)

    # дверь банковского хранилища
    im = img(canvas(96, 96, (120, 124, 130)))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 95, 95], outline=(60, 62, 66), width=3)
    d.ellipse([8, 8, 88, 88], fill=(168, 172, 178), outline=(70, 72, 78), width=3)
    d.ellipse([18, 18, 78, 78], outline=(110, 114, 120), width=2)
    for k in range(12):
        a_ = k * math.pi / 6
        d.ellipse([48 + math.cos(a_) * 35 - 2, 48 + math.sin(a_) * 35 - 2, 48 + math.cos(a_) * 35 + 2,
                   48 + math.sin(a_) * 35 + 2], fill=(84, 86, 92))
    for k in range(4):
        a_ = k * math.pi / 4
        d.line([(48 - math.cos(a_) * 16, 48 - math.sin(a_) * 16), (48 + math.cos(a_) * 16, 48 + math.sin(a_) * 16)],
               fill=(60, 62, 66), width=3)
    d.ellipse([42, 42, 54, 54], fill=(200, 170, 80), outline=(60, 50, 30))
    a = arr(im)
    a *= (0.88 + 0.2 * smooth_noise(96, 96, 31, 3)[..., None])
    save(a, 'int_vault', 48)

    # таблички
    for name, text, bg, fg in (('int_sign_cash', 'КАССА', (30, 80, 56), (240, 214, 120)),
                               ('int_sign_reg', 'РЕГИСТРАТУРА', (240, 240, 236), (200, 30, 30)),
                               ('int_sign_duty', 'ДЕЖУРНАЯ ЧАСТЬ', (24, 50, 130), (250, 250, 250)),
                               ('int_sign_exit', 'ВЫХОД', (30, 130, 60), (250, 250, 250))):
        im = Image.new('RGB', (256, 64), bg)
        d = ImageDraw.Draw(im)
        size = 44
        while size > 8:
            f = font('OswaldBold.ttf', size)
            l, t, r_, b = d.textbbox((0, 0), text, font=f)
            if r_ - l < 236:
                break
            size -= 2
        d.text((128, 30), text, font=f, fill=fg, anchor='mm')
        d.rectangle([0, 0, 255, 63], outline=fg, width=3)
        save(im.resize((64, 16), Image.LANCZOS), name, 16)


BOTTLES = ((40, 110, 60), (150, 90, 30), (190, 150, 60), (120, 30, 40), (60, 90, 150), (200, 200, 190), (30, 60, 40),
           (170, 60, 30))
BOOKS = ((120, 30, 30), (30, 60, 110), (40, 90, 50), (150, 110, 50), (60, 40, 30), (90, 30, 80), (30, 30, 34),
         (170, 150, 120), (140, 60, 30))


def main():
    gc.fetch()
    gen_materials()
    gen_doors()
    gen_wall_things()
    size = sum(os.path.getsize(os.path.join(OUT, n + '.png')) for n in made)
    print('текстур интерьеров: %d, %d КБ' % (len(made), size // 1024))
    if '--sheet' in sys.argv:
        cell = 132
        cols = 10
        rows = (len(made) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * cell, rows * cell), (24, 24, 24))
        for i, n in enumerate(made):
            im = Image.open(os.path.join(OUT, n + '.png')).convert('RGB')
            k = 128.0 / max(im.size)
            im = im.resize((max(1, int(im.size[0] * k)), max(1, int(im.size[1] * k))), Image.NEAREST)
            sheet.paste(im, ((i % cols) * cell + 2, (i // cols) * cell + 2))
        sheet.save(sys.argv[sys.argv.index('--sheet') + 1])


if __name__ == '__main__':
    main()
