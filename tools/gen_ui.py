# -*- coding: utf-8 -*-
"""Значки интерфейса: метки карты, звёзды розыска, прицел, оптика, телефон.

    pip install pillow
    python tools/gen_ui.py [--sheet лист.png]

Всё рисуется здесь, в одной манере: плоские формы без градиентов и свечения, круглая метка с тёмным
ободком, внутри — буква шрифтом интерфейса или простой знак.  Картинки рисуются вчетверо крупнее и
уменьшаются, поэтому края гладкие.  Значки оружия делает tools/import_weapons.py icons — это силуэты
самих моделей.
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'tex')
FONTS = os.path.join(ROOT, 'assets', 'fonts')
K = 4                                           # во сколько раз крупнее рисуем

INK = (14, 15, 18, 255)
PAPER = (240, 237, 230, 255)
ACCENT = (245, 189, 46, 255)
made = []


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), int(size))


def canvas(w, h=None):
    h = h or w
    img = Image.new('RGBA', (w * K, h * K), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def save(img, name, w, h=None):
    h = h or w
    img = img.resize((w, h), Image.LANCZOS)
    img.save(os.path.join(OUT, name + '.png'), optimize=True)
    made.append((name, img))


def badge(name, fill, draw=None, letter=None, fg=PAPER, size=64):
    """Круглая метка: тёмный ободок, заливка, внутри буква или знак."""
    img, d = canvas(size)
    s = size * K
    d.ellipse([s * 0.04, s * 0.04, s * 0.96, s * 0.96], fill=INK)
    d.ellipse([s * 0.10, s * 0.10, s * 0.90, s * 0.90], fill=fill)
    if letter:
        f = font('Inter-Bold.ttf', s * 0.52)
        l, t, r, b = d.textbbox((0, 0), letter, font=f)
        d.text(((s - (r - l)) / 2 - l, (s - (b - t)) / 2 - t), letter, font=f, fill=fg)
    if draw:
        draw(d, s, fg)
    save(img, name, size)


def dot(name, fill, size=32, shape='circle'):
    img, d = canvas(size)
    s = size * K
    if shape == 'circle':
        d.ellipse([s * 0.14, s * 0.14, s * 0.86, s * 0.86], fill=INK)
        d.ellipse([s * 0.24, s * 0.24, s * 0.76, s * 0.76], fill=fill)
    else:                                       # ромб
        c = s * 0.5
        d.polygon([(c, s * 0.08), (s * 0.92, c), (c, s * 0.92), (s * 0.08, c)], fill=INK)
        d.polygon([(c, s * 0.22), (s * 0.78, c), (c, s * 0.78), (s * 0.22, c)], fill=fill)
    save(img, name, size)


def star_points(cx, cy, r1, r2, n=5, rot=-math.pi / 2):
    pts = []
    for i in range(n * 2):
        r = r1 if i % 2 == 0 else r2
        a = rot + i * math.pi / n
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


# ---------------------------------------------------------------------------
# знаки внутри меток
# ---------------------------------------------------------------------------
def g_house(d, s, fg):
    d.polygon([(s * 0.5, s * 0.24), (s * 0.76, s * 0.47), (s * 0.24, s * 0.47)], fill=fg)
    d.rectangle([s * 0.31, s * 0.47, s * 0.69, s * 0.72], fill=fg)
    d.rectangle([s * 0.45, s * 0.56, s * 0.55, s * 0.72], fill=(0, 0, 0, 0))


def g_garage(d, s, fg):
    d.polygon([(s * 0.5, s * 0.25), (s * 0.78, s * 0.42), (s * 0.22, s * 0.42)], fill=fg)
    d.rectangle([s * 0.26, s * 0.42, s * 0.74, s * 0.73], fill=fg)
    for k in range(3):
        z = s * (0.50 + k * 0.075)
        d.rectangle([s * 0.34, z, s * 0.66, z + s * 0.035], fill=(0, 0, 0, 0))


def g_cross(d, s, fg):
    d.rectangle([s * 0.42, s * 0.26, s * 0.58, s * 0.74], fill=fg)
    d.rectangle([s * 0.26, s * 0.42, s * 0.74, s * 0.58], fill=fg)


def g_star(d, s, fg):
    d.polygon(star_points(s * 0.5, s * 0.52, s * 0.27, s * 0.115), fill=fg)


def g_gun(d, s, fg):
    d.rectangle([s * 0.24, s * 0.36, s * 0.76, s * 0.48], fill=fg)
    d.polygon([(s * 0.27, s * 0.48), (s * 0.45, s * 0.48), (s * 0.40, s * 0.72), (s * 0.25, s * 0.72)], fill=fg)
    d.rectangle([s * 0.47, s * 0.48, s * 0.52, s * 0.56], fill=fg)


def g_spray(d, s, fg):
    d.rounded_rectangle([s * 0.37, s * 0.42, s * 0.60, s * 0.76], radius=s * 0.03, fill=fg)
    d.rectangle([s * 0.43, s * 0.32, s * 0.54, s * 0.42], fill=fg)
    for (x, y) in ((0.66, 0.30), (0.74, 0.24), (0.74, 0.37), (0.80, 0.31)):
        d.ellipse([s * (x - 0.025), s * (y - 0.025), s * (x + 0.025), s * (y + 0.025)], fill=fg)


def g_wrench(d, s, fg):
    # ключ наискось: рукоять и разомкнутая головка
    d.line([(s * 0.30, s * 0.72), (s * 0.60, s * 0.42)], fill=fg, width=int(s * 0.10))
    d.ellipse([s * 0.50, s * 0.24, s * 0.76, s * 0.50], fill=fg)
    d.polygon([(s * 0.66, s * 0.20), (s * 0.82, s * 0.36), (s * 0.70, s * 0.36), (s * 0.63, s * 0.29)],
              fill=(0, 0, 0, 0))
    d.ellipse([s * 0.24, s * 0.66, s * 0.36, s * 0.78], fill=fg)


def g_flag(d, s, fg):
    q = s * 0.11
    for i in range(4):
        for j in range(4):
            if (i + j) % 2 == 0:
                d.rectangle([s * 0.28 + i * q, s * 0.28 + j * q, s * 0.28 + (i + 1) * q, s * 0.28 + (j + 1) * q],
                            fill=fg)


def g_phone(d, s, fg):
    d.rounded_rectangle([s * 0.37, s * 0.24, s * 0.63, s * 0.76], radius=s * 0.05, fill=fg)
    d.rectangle([s * 0.41, s * 0.31, s * 0.59, s * 0.64], fill=(0, 0, 0, 0))


def g_ship(d, s, fg):
    d.polygon([(s * 0.22, s * 0.56), (s * 0.78, s * 0.56), (s * 0.69, s * 0.72), (s * 0.31, s * 0.72)], fill=fg)
    d.rectangle([s * 0.40, s * 0.38, s * 0.58, s * 0.56], fill=fg)
    d.rectangle([s * 0.46, s * 0.26, s * 0.52, s * 0.38], fill=fg)


def g_car(d, s, fg):
    # машина сбоку: кузов, крыша, два колеса
    d.rounded_rectangle([s * 0.20, s * 0.47, s * 0.80, s * 0.64], radius=s * 0.04, fill=fg)
    d.polygon([(s * 0.33, s * 0.47), (s * 0.40, s * 0.33), (s * 0.62, s * 0.33), (s * 0.70, s * 0.47)], fill=fg)
    for x in (0.34, 0.66):
        d.ellipse([s * (x - 0.075), s * 0.57, s * (x + 0.075), s * 0.72], fill=fg)
        d.ellipse([s * (x - 0.03), s * 0.615, s * (x + 0.03), s * 0.675], fill=(0, 0, 0, 0))


def blips():
    # заказчики: буква на своём цвете
    for name, letter, col in (('bruce', 'Б', (214, 96, 44)), ('boss', 'К', (120, 60, 150)),
                              ('vano', 'В', (48, 112, 190)), ('rosa', 'Р', (190, 52, 108)),
                              ('prof', 'П', (62, 140, 78)), ('zakhar', 'З', (40, 140, 150)),
                              ('grom', 'Г', (176, 116, 40))):
        badge('blip_' + name, col + (255,), letter=letter)
    badge('blip_taxi', ACCENT, letter='T', fg=INK)
    # службы: знак на светлом или тёмном
    badge('blip_save', PAPER, g_house, fg=INK)
    badge('blip_garage', PAPER, g_garage, fg=INK)
    badge('blip_hospital', PAPER, g_cross, fg=(206, 48, 44, 255))
    badge('blip_station', (44, 78, 160, 255), g_star, fg=PAPER)
    badge('blip_guns', (44, 46, 52, 255), g_gun, fg=PAPER)
    badge('blip_spray', (44, 46, 52, 255), g_spray, fg=ACCENT)
    badge('blip_tune', (44, 46, 52, 255), g_wrench, fg=ACCENT)
    badge('blip_race', PAPER, g_flag, fg=INK)
    badge('blip_phone', (44, 46, 52, 255), g_phone, fg=PAPER)
    badge('blip_ship', (44, 46, 52, 255), g_ship, fg=PAPER)
    badge('blip_car', (40, 84, 170, 255), g_car, fg=PAPER)          # машина героя
    # цели и люди
    dot('blip_dest', ACCENT, shape='diamond')
    dot('blip_enemy', (224, 62, 54, 255))
    dot('blip_friend', (84, 160, 240, 255))
    dot('blip_pickup', (120, 208, 120, 255))
    dot('blip_police', (70, 120, 250, 255))
    # игрок: стрелка
    img, d = canvas(64)
    s = 64 * K
    arrow = [(s * 0.5, s * 0.08), (s * 0.84, s * 0.88), (s * 0.5, s * 0.68), (s * 0.16, s * 0.88)]
    d.polygon(arrow, fill=INK)
    c = (s * 0.5, s * 0.60)
    inner = [(c[0] + (x - c[0]) * 0.74, c[1] + (y - c[1]) * 0.74) for x, y in arrow]
    d.polygon(inner, fill=PAPER)
    save(img, 'blip_player', 64)
    # север
    img, d = canvas(32)
    s = 32 * K
    f = font('Inter-Bold.ttf', s * 0.74)
    l, t, r, b = d.textbbox((0, 0), 'N', font=f)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            d.text(((s - (r - l)) / 2 - l + dx * K * 1.2, (s - (b - t)) / 2 - t + dy * K * 1.2), 'N', font=f, fill=INK)
    d.text(((s - (r - l)) / 2 - l, (s - (b - t)) / 2 - t), 'N', font=f, fill=PAPER)
    save(img, 'blip_north', 32)


def hud():
    # звёзды розыска
    for name, fill, rim in (('hud_star', PAPER, INK), ('hud_star_off', (0, 0, 0, 0), None)):
        img, d = canvas(64)
        s = 64 * K
        if rim:
            d.polygon(star_points(s * 0.5, s * 0.53, s * 0.47, s * 0.20), fill=rim)
            d.polygon(star_points(s * 0.5, s * 0.53, s * 0.39, s * 0.165), fill=fill)
        else:
            d.polygon(star_points(s * 0.5, s * 0.53, s * 0.47, s * 0.20), fill=(14, 15, 18, 150))
            d.polygon(star_points(s * 0.5, s * 0.53, s * 0.39, s * 0.165), fill=(240, 237, 230, 70))
        save(img, name, 64)
    # прицел: точка и четыре штриха; светлое с тёмной каймой — видно и на асфальте, и на небе.
    # На экране он вдвое меньше текстуры, поэтому штрихи толстые: тонкие при уменьшении пропадают
    img, d = canvas(64)
    s = 64 * K
    c = s // 2
    for grow, col in ((K * 2, (14, 15, 18, 215)), (0, PAPER)):
        hw = K * 2 + grow                           # полутолщина штриха
        r = K * 3 + grow
        a, b = K * 11 - grow, K * 25 + grow         # штрих — от a до b от центра
        d.ellipse([c - r, c - r, c + r - 1, c + r - 1], fill=col)
        d.rectangle([c + a, c - hw, c + b - 1, c + hw - 1], fill=col)
        d.rectangle([c - b, c - hw, c - a - 1, c + hw - 1], fill=col)
        d.rectangle([c - hw, c + a, c + hw - 1, c + b - 1], fill=col)
        d.rectangle([c - hw, c - b, c + hw - 1, c - a - 1], fill=col)
    save(img, 'crosshair', 64)
    # оптика: чёрное поле с круглым окном и тонким перекрестием
    n = 512
    img = Image.new('RGBA', (n, n), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    r = n * 0.47
    d.ellipse([n / 2 - r, n / 2 - r, n / 2 + r, n / 2 + r], fill=(0, 0, 0, 0))
    d.ellipse([n / 2 - r, n / 2 - r, n / 2 + r, n / 2 + r], outline=(0, 0, 0, 255), width=5)
    for a, b in (((n * 0.03, n / 2), (n * 0.44, n / 2)), ((n * 0.56, n / 2), (n * 0.97, n / 2)),
                 ((n / 2, n * 0.03), (n / 2, n * 0.44)), ((n / 2, n * 0.56), (n / 2, n * 0.97))):
        d.line([a, b], fill=(0, 0, 0, 255), width=3)
    d.line([(n * 0.44, n / 2), (n * 0.56, n / 2)], fill=(0, 0, 0, 255), width=1)
    d.line([(n / 2, n * 0.44), (n / 2, n * 0.56)], fill=(0, 0, 0, 255), width=1)
    img.save(os.path.join(OUT, 'scope.png'), optimize=True)
    made.append(('scope', img.resize((64, 64))))
    # кулак — «оружия нет»
    img, d = canvas(128, 64)
    w, h = 128 * K, 64 * K
    d.rounded_rectangle([w * 0.30, h * 0.26, w * 0.62, h * 0.84], radius=h * 0.10, fill=PAPER)     # ладонь
    for k in range(4):                                                                             # костяшки
        y0 = h * (0.20 + k * 0.16)
        d.rounded_rectangle([w * 0.22, y0, w * 0.40, y0 + h * 0.15], radius=h * 0.07, fill=PAPER)
    d.rounded_rectangle([w * 0.40, h * 0.12, w * 0.60, h * 0.34], radius=h * 0.09, fill=PAPER)     # большой палец
    d.rectangle([w * 0.60, h * 0.36, w * 0.82, h * 0.78], fill=PAPER)                              # запястье
    for k in range(1, 4):
        y0 = h * (0.20 + k * 0.16) - h * 0.008
        d.rectangle([w * 0.22, y0, w * 0.40, y0 + h * 0.016], fill=(0, 0, 0, 0))
    save(img, 'w_fist', 128, 64)
    # телефон: корпус со скруглёнными углами и экран
    img, d = canvas(128, 224)
    w, h = 128 * K, 224 * K
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=w * 0.13, fill=(22, 23, 27, 255))
    d.rounded_rectangle([w * 0.05, h * 0.045, w * 0.95, h * 0.955], radius=w * 0.08, fill=(36, 38, 44, 255))
    d.rounded_rectangle([w * 0.38, h * 0.018, w * 0.62, h * 0.032], radius=h * 0.007, fill=(60, 62, 70, 255))
    save(img, 'ui_phone', 128, 256)
    # круг — аватар звонящего, точки
    img, d = canvas(64)
    s = 64 * K
    d.ellipse([s * 0.03, s * 0.03, s * 0.97, s * 0.97], fill=(255, 255, 255, 255))
    save(img, 'ui_disc', 64)


def main():
    blips()
    hud()
    print('значков: %d -> %s' % (len(made), OUT))
    if '--sheet' in sys.argv:
        path = sys.argv[sys.argv.index('--sheet') + 1]
        cols = 9
        rows = (len(made) + cols - 1) // cols
        sh = Image.new('RGB', (cols * 76, rows * 76), (70, 96, 78))
        for i, (name, img) in enumerate(made):
            t = img.copy()
            t.thumbnail((64, 64))
            sh.paste(t, ((i % cols) * 76 + 6 + (64 - t.size[0]) // 2, (i // cols) * 76 + 6 + (64 - t.size[1]) // 2), t)
        sh.save(path)
        print('лист:', path)


if __name__ == '__main__':
    main()
