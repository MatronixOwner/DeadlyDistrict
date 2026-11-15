# -*- coding: utf-8 -*-
"""Снимки для README (папка docs/).  Игра запускается без окна, на программном рендере.

    python tools/make_screenshots.py

Нужен pillow.  Настоящая видеокарта рисует чётче: здесь нет сглаживания краёв и анизотропной фильтрации.
"""
import math
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

    def in_view(cyaw, x, y, r, half=0.42):
        px, py = w.player.pos()
        d = math.hypot(x - px, y - py)
        if d < 4.0 or d > r:
            return False
        a = math.atan2(y - py, x - px)
        return abs((a - cyaw + math.pi) % (2.0 * math.pi) - math.pi) < half

    def lively(cyaw, cars=1, peds=2, tmax=25.0):
        """Подождать, пока перед камерой окажутся машины и прохожие."""
        t = 0.0
        while t < tmax:
            harness.run(g, 0.5)
            t += 0.5
            nc = sum(1 for v in w.vehicles if not v.removed and in_view(cyaw, v.x, v.y, 75.0))
            np_ = sum(1 for p in w.peds if not p.removed and p is not w.player.ped and in_view(cyaw, p.x, p.y, 60.0))
            if nc >= cars and np_ >= peds:
                break

    def chase(car, y_line, x_end, tmax=50.0, cruise=17.0):
        """Ехать по улице на восток, держась полосы, пока полиция не сядет на хвост."""
        t = 0.0
        while t < tmax and car.x < x_end:
            steer = -(car.y - y_line) * 0.10 - ((car.yaw + math.pi) % (2.0 * math.pi) - math.pi) * 1.2
            ahead = 1e9
            for v in w.vehicles:
                if v is not car and not v.removed and 0.0 < v.x - car.x < 30.0 and abs(v.y - car.y) < 2.2:
                    ahead = min(ahead, v.x - car.x)
            keys = []
            if ahead < 9.0 + car.speed * 0.9:
                keys.append('s' if car.speed > 3.0 else 'space')
            elif car.speed < cruise:
                keys.append('w')
            if steer > 0.04:
                keys.append('a')
            elif steer < -0.04:
                keys.append('d')
            harness.run(g, 0.2, keys=tuple(keys))
            t += 0.2
            if w.police.seen and any(not u.removed and not u.dead and 6.0 < car.x - u.x < 30.0 and abs(u.y - car.y) < 8.0
                                     for u in w.police.units):
                return True
        return False

    def view(x, y, z, tx, ty, tz, hud=False):
        """Свободная камера (без героя в кадре).  Сам герой ждёт на ближайшем к камере тротуаре:
        под камерой может оказаться море, а в море он тонет."""
        n = w.roadnet.nearest_ped_node(x, y, 2000.0)
        w.player.teleport(n.x, n.y)
        w.cam.override = (x, y, z, tx, ty, tz)
        harness.run(g, 0.3)
        w.hud.show(hud)
        for n in ('big_text', 'title_text', 'zone_text'):
            getattr(w.hud, n).setText('')
        harness.run(g, 0.05)

    harness.run(g, 2.0)
    snap('menu')

    # пролог: автобус привёз Макса на конечную
    g.new_game()
    t = 0.0
    while w.missions.intro is not None and t < 26.2:
        g.step(1.0 / 30.0)
        t += 1.0 / 30.0
    snap('prologue')
    while w.missions.intro is not None and t < 31.5:
        g.step(1.0 / 30.0)
        t += 1.0 / 30.0
    snap('prologue_call')
    harness.press(g, 'escape')
    harness.run(g, 0.5)
    pl = w.player

    # комната Макса: здесь игра начинается и сохраняется
    w.sky.set_time(9.0)
    room = w.interiors.rooms['safehouse']
    pl.teleport(room.ox + 3.3, room.oy + 2.2, 0.9)
    w.cam.yaw = 0.75
    w.cam.pitch = -0.28
    harness.run(g, 1.2)
    nohelp()
    snap('room')

    # бар Розы
    w.interiors.enter('rosa', instant=True)
    room = w.interiors.rooms['rosa']
    x, y, yaw = room.spots['talk']
    pl.teleport(x - 0.6, y - 2.6, 1.3)
    w.cam.yaw = 1.25
    w.cam.pitch = -0.2
    harness.run(g, 1.0)
    nohelp()
    w.hud.clear_subtitles()
    harness.run(g, 0.05)
    snap('bar')
    w.interiors.leave(instant=True)
    harness.run(g, 0.3)
    pl.teleport(*w.city.landmarks['safehouse']['door'])
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
    # материк: Заречье за проливом, холмы и трасса
    w.sky.set_time(17.6)
    view(250.0, 560.0, 70.0, -40.0, 900.0, 0.0)
    snap('mainland')
    w.sky.set_time(11.0)
    lm = w.city.landmarks['zakhar']
    view(lm['door'][0] - 46.0, lm['door'][1] - 58.0, 26.0, lm['door'][0] + 30.0, lm['door'][1] + 40.0, 0.0)
    snap('harbour')
    w.cam.override = None
    w.hud.show(True)
    w.sky.set_time(8.2)
    w.sky.time_scale = 1.0
    pl.teleport(*w.city.landmarks['safehouse']['door'])
    harness.run(g, 1.0)
    assert not pl.ped.dead and pl.ped.health > 99, 'героя задело, пока снимались виды города'

    # улица у парка: герой, прохожие и машины.  Ждём кадра, где в поле зрения есть и те и другие
    w.sky.set_time(12.3)
    b = w.city.block_grid[(4, 2)]
    pl.teleport(8.0, b.y1 - 1.7, 0.0)
    harness.run(g, 6.0)
    w.cam.yaw = 2.3
    w.cam.pitch = -0.1
    w.cam.snap()
    lively(2.3)
    harness.run(g, 1.6, keys=('w', 'a'))
    nohelp()
    snap('street')
    lane = w.roadnet.lane_index[('h', 2, 2, 'e', 0)]

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

    # Большой мост: с материка в город
    seg = next(sg for sg in w.city.bridges if sg['bridge']['name'] == 'north')
    lanes = [l for l in w.roadnet.lanes_near(seg['c'], (seg['a'] + seg['b']) * 0.5, 0.0, 40.0)
             if l.turn is None and l.y1 < l.y0 and abs(l.length - (seg['b'] - seg['a'])) < 1.0]
    bl = lanes[0]
    for v in list(w.vehicles):
        if v is not car and not v.keep and abs(v.x - seg['c']) < 12.0 and seg['a'] - 40.0 < v.y < seg['b'] + 40.0:
            w.remove_vehicle(v)
    car.x, car.y, car.yaw = bl.x0, bl.y0 - 40.0, -1.5708
    car.vx, car.vy, car.speed = 0.0, -14.0, 14.0
    car.sync()
    w.cam.yaw = -1.5708
    w.cam.snap()
    w.sky.set_time(16.5)
    harness.run(g, 3.2, keys=('w',))
    nohelp()
    snap('bridge')
    car.x, car.y, car.yaw = x, y, yaw
    car.vx = car.vy = car.speed = 0.0
    car.sync()
    w.cam.yaw = yaw
    w.cam.snap()
    harness.run(g, 2.5, keys=('w',))

    # ночная погоня: три звезды, едем по улице, пока патрульная машина не окажется позади
    w.sky.set_time(22.5)
    w.police.set_level(3)
    pl.invincible = True
    if not chase(car, y, 420.0):
        print('внимание: полиция не догнала, кадр «chase» без погони')
    w.cam.free_t = 0.0
    w.cam.yaw = car.yaw + 2.6
    w.cam.pitch = -0.12
    harness.run(g, 0.2, keys=('w',))
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
    harness.run(g, 1.6)
    snap('mission')
    # карта в меню паузы
    for _ in range(12):
        if not pl.freeze:
            break
        harness.press(g, 'enter')
        harness.run(g, 0.5)
    w.missions.active and w.missions._finish(False, '', True)
    w.missions.done |= {'v1', 'r1', 'z1', 'r2', 'g1'}
    w.missions.refresh_contacts()
    harness.run(g, 0.5)
    g.pause()
    g.open_map()
    for _ in range(4):
        g.step(1.0 / 30.0)
    snap('map')
    print('снимки:', ', '.join(done), '->', DOCS)
    rows = (len(done) + 3) // 4
    sheet = Image.new('RGB', (640 * 4, 360 * rows))
    for i, n in enumerate(done):
        im = Image.open(os.path.join(DOCS, n + '.jpg')).resize((640, 360), Image.LANCZOS)
        sheet.paste(im, ((i % 4) * 640, (i // 4) * 360))
    sheet.save(os.path.join(TMP, 'sheet.png'))
    print('общий лист:', os.path.join(TMP, 'sheet.png'))


if __name__ == '__main__':
    main()
