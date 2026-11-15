# -*- coding: utf-8 -*-
"""Снимки для README (папка docs/).  Игра запускается без окна, на программном рендере.

    python tools/make_screenshots.py

Нужен pillow.  Настоящая видеокарта рисует чётче: здесь нет сглаживания краёв и анизотропной фильтрации.
"""
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
os.environ.setdefault('DD_USER_DIR', tempfile.mkdtemp(prefix='dd_shots_'))     # не трогаем настройки игрока

import harness                                                                  # noqa: E402
from PIL import Image                                                           # noqa: E402
from game import missions as M                                                  # noqa: E402
from game.defs import W_PISTOL, W_FIST, WEAPONS                                 # noqa: E402

DOCS = os.path.join(ROOT, 'docs')
TMP = tempfile.mkdtemp(prefix='dd_png_')


def main():
    random.seed(7)
    g = harness.make_game(1280, 720)
    w = g.world
    done = []

    def snap(name):
        png = os.path.join(TMP, name + '.png')
        harness.shot(g, png)
        Image.open(png).convert('RGB').save(os.path.join(DOCS, name + '.jpg'), quality=88)
        done.append(name)

    def nohelp():
        w.hud.help_t = 0.01
        w.hud.title_t = 0.01
        harness.run(g, 0.1)

    def view(x, y, z, tx, ty, tz, hud=False):
        """Свободная камера (без героя в кадре)."""
        w.player.teleport(x, y - 30.0)
        w.cam.override = (x, y, z, tx, ty, tz)
        harness.run(g, 0.3)
        w.hud.show(hud)
        for n in ('big_text', 'title_text', 'zone_text'):
            getattr(w.hud, n).setText('')
        harness.run(g, 0.05)

    harness.run(g, 2.0)
    snap('menu')
    harness.start_game(g)
    pl = w.player
    harness.run(g, 6.0)

    # виды города без героя
    w.sky.set_time(10.5)
    w.sky.time_scale = 0.0
    b = w.city.block_grid[(1, 3)]
    view(b.x0 - 6, b.y0 - 6, 1.7, b.x0 + 12, b.y0 + 10, 7.5)
    snap('oldtown')
    view(-300, -330, 110, 60, -20, 30)
    snap('skyline')
    w.sky.set_time(23.5)
    view(-300, -330, 110, 60, -20, 30)
    snap('night')
    w.cam.override = None
    w.hud.show(True)
    w.sky.set_time(8.2)
    w.sky.time_scale = 1.0
    pl.teleport(*w.city.landmarks['safehouse']['door'])
    harness.run(g, 1.0)

    # улица: герой со спины, прохожие и машины
    lane = w.roadnet.lane_index[('h', 2, 2, 'e', 0)]
    x, y, yaw = lane.pos(22.0)
    pl.teleport(x, y - 4.3)
    w.cam.yaw = 0.25
    w.cam.pitch = -0.1
    harness.run(g, 3.0, keys=('w',))
    nohelp()
    snap('street')

    # прицеливание
    pl.give_weapon(W_PISTOL, 50)
    harness.run(g, 0.3)
    g.inp._dn('mouse3')
    harness.run(g, 0.8)
    nohelp()
    snap('aim')
    g.inp._up('mouse3')
    harness.run(g, 0.2)

    # за рулём
    x, y, yaw = lane.pos(5.0)
    car = w.spawn_vehicle('sports', x, y, yaw, paint=0)
    pl.teleport(x, y - 3)
    pl.enter_vehicle(car, silent=True)
    w.cam.yaw = yaw
    harness.run(g, 4.5, keys=('w',))
    nohelp()
    snap('drive')

    # ночная погоня
    w.sky.set_time(22.5)
    w.police.set_level(3)
    pl.invincible = True
    harness.run(g, 9.0, keys=('w',))
    w.cam.free_t = 0.0
    w.cam.yaw = car.yaw + 2.6
    w.cam.pitch = -0.12
    harness.run(g, 0.2)
    nohelp()
    snap('chase')
    w.police.clear()
    pl.invincible = False

    # задание (в руках ничего нет)
    if pl.vehicle is not None:
        pl.leave_vehicle(force=True)
        harness.run(g, 1.5)
    pl.weapon_id = W_FIST
    pl.weapon = WEAPONS[W_FIST]
    pl.ped.set_weapon(W_FIST)
    w.sky.set_time(9.5)
    x, y = w.city.landmarks['vano']['door']
    pl.teleport(x, y - 2.0)
    w.missions.start(M.MISSIONS[0])
    harness.run(g, 1.2)
    snap('mission')
    print('снимки:', ', '.join(done), '->', DOCS)
    sheet = Image.new('RGB', (1280 * 3, 720 * 3))
    for i, n in enumerate(done):
        sheet.paste(Image.open(os.path.join(DOCS, n + '.jpg')), ((i % 3) * 1280, (i // 3) * 720))
    sheet.resize((1920, 1080), Image.LANCZOS).save(os.path.join(TMP, 'sheet.png'))
    print('общий лист:', os.path.join(TMP, 'sheet.png'))


if __name__ == '__main__':
    main()
