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
from game.defs import W_M4, W_FIST, WEAPONS                                     # noqa: E402
from game import story                                                          # noqa: E402
from game.vehicle import BIKES                                                  # noqa: E402
from bot import Bot                                                             # noqa: E402

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

    def nohelp(keys=()):
        w.hud.help_t = 0.01
        w.hud.title_t = 0.01
        w.hud.big_t = 0.01
        harness.run(g, 0.1, keys=keys)

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
        nohelp()

    harness.run(g, 2.0)
    snap('menu')
    for old in ('prologue_call', 'mission'):        # снимки прежних версий
        f = os.path.join(DOCS, old + '.jpg')
        if os.path.isfile(f):
            os.remove(f)

    # пролог: автобус привёз Макса на конечную
    g.new_game()
    ms = w.missions
    t = 0.0
    while ms.intro is not None and t < 26.2:
        g.step(1.0 / 30.0)
        t += 1.0 / 30.0
    snap('prologue')
    harness.press(g, 'escape')
    harness.run(g, 0.5)
    pl = w.player
    # сюжет начинается со звонка брата: телефон на экране, реплики — субтитрами
    t = 0.0
    while t < 40.0 and not (ms.active is not None and w.hud.phone_on):
        harness.run(g, 0.25)
        t += 0.25
    for _ in range(3):
        harness.run(g, 1.6)
        harness.press(g, 'enter')
    harness.run(g, 1.2)
    snap('call')
    if ms.active is not None:
        ms._finish(False, '', True)
    w.hud.phone_hide()
    w.hud.clear_subtitles()
    ms.done |= M.STORY_IDS                          # дальше снимаем свободный город: брат больше не звонит
    ms.call_t = 1e9
    ms.refresh_contacts()
    ms.sync_story()
    harness.run(g, 0.5)

    # комната Макса: здесь игра сохраняется
    w.sky.set_time(9.0)
    w.interiors.enter('safehouse', instant=True)
    room = w.interiors.rooms['safehouse']
    pl.teleport(room.ox + 3.3, room.oy + 2.2, 0.9)
    w.cam.yaw = 0.75
    w.cam.pitch = -0.28
    harness.run(g, 1.2)
    nohelp()
    snap('room')
    w.interiors.leave(instant=True)
    harness.run(g, 0.3)

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
    pl.give_weapon(W_M4, 90)
    pl.select(W_M4)
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

    if pl.vehicle is not None:
        pl.leave_vehicle(force=True)
        harness.run(g, 1.5)
    pl.weapon_id = W_FIST
    pl.weapon = WEAPONS[W_FIST]
    pl.ped.set_weapon(W_FIST)
    harness.quiet(w)
    for v in list(w.vehicles):
        if not v.keep and v is not pl.vehicle:
            w.remove_vehicle(v)
    w.traffic.enabled = True
    c = w.city

    # мотоцикл с коляской: брат едет пассажиром
    w.sky.set_time(15.0)
    w.sky.time_scale = 0.0
    x, y, yaw = lane.pos(5.0)
    side = w.spawn_vehicle('sidecar', x, y, yaw, paint=1)
    pl.teleport(x, y - 3)
    pl.enter_vehicle(side, silent=True)
    bruce = w.spawn_ped(x, y - 4.0, 0.0, story.person_look('bruce'))
    bruce.keep = True
    w.put_in_vehicle(bruce, side)
    w.cam.yaw = yaw
    harness.run(g, 3.0, keys=('w',))
    harness.run(g, 2.5, keys=('space',))            # остановились: камера встаёт спереди сбоку
    side.vx = side.vy = side.speed = side.omega = 0.0
    fx, fy = math.cos(side.yaw), math.sin(side.yaw)
    w.cam.override = (side.x + fx * 3.3 - fy * 2.7, side.y + fy * 3.3 + fx * 2.7, 1.75, side.x - fx * 0.2 + fy * 0.4,
                      side.y - fy * 0.2 - fx * 0.4, 0.9)
    nohelp(('space',))
    harness.run(g, 0.1, keys=('space',))
    snap('sidecar')
    w.cam.override = None
    pl.leave_vehicle(force=True)
    harness.run(g, 1.0)
    w.remove_ped(bruce)
    w.remove_vehicle(side)

    # весь двух-, трёх- и четырёхколёсный парк в ряд на лётном поле
    ap = c.landmarks['airfield']['apron']
    bx, by = ap[0] - 60.0, ap[1] - 8.0
    row = []
    order = ['bike', 'tourer', 'chopper', 'copbike', 'dirt', 'sidecar', 'trike', 'quad', 'scooter', 'courier', 'cargo',
             'moped', 'kart', 'caddy', 'bicycle', 'bmx']
    assert set(order) == set(BIKES)
    for i, kind in enumerate(order):
        r, k = (0, i) if i < 6 else ((1, i - 6) if i < 11 else (2, i - 11))
        v = w.spawn_vehicle(kind, bx + k * 2.5 + r * 1.25, by + r * 3.4, math.pi / 2 + 0.6, paint=i % 4)
        v.keep = True
        row.append(v)
    w.sky.set_time(13.0)
    view(bx + 6.9, by - 10.6, 4.9, bx + 6.9, by + 2.4, 0.5)
    snap('bikes')
    for v in row:
        w.remove_vehicle(v)
    w.cam.override = None
    w.hud.show(True)

    # тюнинг: три машины у дома и меню ателье
    gi = c.special['garage']
    gx0, gy0, gx1, gy1 = gi['rect']
    fx, fy = gi['front']
    pl.teleport(fx - 6.0, fy - 3.0)
    harness.run(g, 1.0)
    tunes = [('sports', 0, {'spoiler': 3, 'rims': 3, 'neon': 1, 'bumper': 1, 'susp': 1, 'exhaust': 2, 'xenon': 2}),
             ('sedan', 2, {'spoiler': 2, 'rims': 2, 'neon': 3, 'roof': 1, 'susp': 3}),
             ('suv', 4, {'spoiler': 1, 'rims': 4, 'neon': 2, 'roof': 2, 'bumper': 1})]
    cars = []
    for i, (kind, paint, tune) in enumerate(tunes):
        v = w.spawn_vehicle(kind, fx - 8.0 + i * 5.5, fy - 7.5, math.pi / 2 + 0.5, paint=paint)
        v.keep = True                               # иначе игра уберёт «ничью» машину, пока герой далеко
        v.apply_tune(tune)
        cars.append(v)
    w.sky.set_time(21.6)
    mx = fx - 2.5
    view(mx - 5.0, fy - 17.0, 3.0, mx, fy - 7.0, 0.7)
    snap('tuned')
    w.cam.override = None
    w.hud.show(True)
    w.sky.set_time(12.0)
    pl.teleport(cars[0].x, cars[0].y - 3.0)
    pl.enter_vehicle(cars[0], silent=True)
    harness.run(g, 1.0)
    g.open_tuning(cars[0], 'spray')
    harness.run(g, 0.7)
    snap('tuning')
    for _ in range(4):                              # выходим из ателье так же, как игрок: клавишей Esc
        if g.state == 'play':
            break
        harness.press(g, 'escape')
        harness.run(g, 0.4)
    assert g.state == 'play', 'меню ателье не закрылось'
    harness.run(g, 0.3)
    pl.leave_vehicle(force=True)
    # гараж: машины стоят в клетках, ворота открыты
    for v, sl in zip(cars, gi['slots']):
        v.x, v.y, v.yaw = sl[0], sl[1], gi['yaw']
        v.vx = v.vy = v.speed = 0.0
        v.sync()
    pl.teleport(fx + 3.6, fy + 5.0)
    harness.run(g, 2.0)
    view(fx - 5.0, fy - 2.5, 2.7, (gx0 + gx1) / 2 + 0.6, (gy0 + gy1) / 2, 1.2, hud=True)
    pl.teleport(fx + 3.6, fy + 5.0)                 # ворота открыты, пока герой рядом
    pl.ped.yaw = math.pi / 2
    harness.run(g, 1.5)
    nohelp()
    snap('garage')
    w.cam.override = None
    w.hud.show(True)
    w.garage.reset()

    # сюжет: ведёт бот из автотестов, снимаем нужные сцены
    def story_run(mid, stops):
        spec = next(m for m in M.MISSIONS if m['id'] == mid)
        ms.call_t = 1e9                             # следующее дело начинаем сами, а не по звонку
        if ms.active is not None:
            ms._finish(False, '', True)
            harness.run(g, 0.5)
        w.hud.phone_hide()
        w.hud.clear_subtitles()
        ms.done -= M.STORY_IDS
        ms.done |= set(spec['req'])
        ms.ckpt.clear()
        ms.sync_story()
        pl.invincible = True
        w.sky.set_time(11.0)
        assert ms.start(spec)
        bot = Bot(g, verbose=False)
        t = 0.0
        while ms.active is not None and t < 400.0:
            for test, fn in list(stops):
                if test():
                    stops.remove((test, fn))
                    fn()
            bot.step(1.0 / 30.0)
            g.step(1.0 / 30.0)
            t += 1.0 / 30.0
        pl.invincible = False
        w.cam.override = None
        w.hud.show(True)
        ms.call_t = 1e9
        harness.run(g, 4.0)

    def obj(text):
        return lambda: ms.active is not None and text in (ms.active.objective or '')

    def shot_pier():
        pier = c.special['piers'][0]
        px0, py0, px1, py1 = pier['x0'], pier['y0'], pier['x1'], pier['y1']
        sx, sy = px0 + 26.0, (py0 + py1) / 2            # здесь бандиты держат Брюса на коленях
        w.cam.override = (sx - 4.6, sy - 3.6, 2.0, sx + 0.8, sy + 0.1, 0.85)
        harness.run(g, 1.2)                             # герой ещё в пути: бандиты стоят над пленником
        w.hud.help_t = 0.01
        harness.run(g, 0.05)
        snap('pier')
        w.cam.override = None

    def shot_boss():
        harness.run(g, 2.4)
        snap('boss')

    def shot_ship():
        sh = c.special['ship']
        w.cam.override = (500.0, -14.0, 13.0, 552.0, 15.0, 3.6)
        harness.run(g, 0.3)
        nohelp()
        snap('ship')
        w.cam.override = None

    story_run('s1', [(obj('Гони в порт'), shot_pier)])
    story_run('s2', [(lambda: w.interiors.current is not None and w.interiors.current.name == 'boss'
                      and bool(w.hud.sub_text.getText()), shot_boss),
                     (obj('Уберите охрану'), shot_ship)])
    ms.done |= M.STORY_IDS
    ms.call_t = 1e9
    ms.refresh_contacts()
    ms.sync_story()
    # карта в меню паузы
    w.sky.set_time(9.5)
    pl.teleport(*c.landmarks['safehouse']['door'])
    harness.run(g, 1.0)
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
