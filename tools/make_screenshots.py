# -*- coding: utf-8 -*-
"""Снимки для README (папка docs/).  Игра запускается без окна, на программном рендере.

    python tools/make_screenshots.py
    python tools/make_screenshots.py --tester     только снимок меню тестера (docs/tester.jpg)
    python tools/make_screenshots.py --gfx        только сравнение наборов качества графики (docs/gfx_*.jpg)

Обычный программный рендер (TinyDisplay) шейдеров не умеет: снимки выходят в наборе «Минимум».  Чтобы снять
игру с шейдерами — «Среднее», как она выглядит на видеокарте, — нужен OpenGL без окна:

    DD_TEST_DISPLAY=p3headlessgl python tools/make_screenshots.py

Годится программная Mesa (llvmpipe), но с ней один кадр рисуется секунд десять, а все снимки — около часа.

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
from bot import Bot                                                             # noqa: E402

DOCS = os.path.join(ROOT, 'docs')
TMP = tempfile.mkdtemp(prefix='dd_png_')


def main():
    random.seed(int(os.environ.get('DD_SHOT_SEED', '1')))
    g = harness.make_game(1280, 720)
    w = g.world
    done = []

    def snap(name, keys=()):
        # кости персонажей пересчитываются при отрисовке, а руки на оружии и на руле ведёт игра по этим костям:
        # за несколько кадров «шаг — отрисовка» поза доходит до той, что видит игрок
        for _ in range(3):
            g.base.graphicsEngine.renderFrame()
            harness.run(g, 1.0 / 30.0, keys=keys)
        # звёзды розыска мигают, когда уровень только что вырос: снимаем в тот кадр, где они горят
        pol = w.police
        for _ in range(8):
            if not (g.state == 'play' and pol.level > 0 and (pol.cool_t > 2.0 or pol.flash > 0.0)
                    and int(w.hud.t * 5) % 2 == 0):
                break
            g.base.graphicsEngine.renderFrame()
            harness.run(g, 1.0 / 30.0, keys=keys)
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

    def chase(car, goal, tmax=70.0, cruise=17.0):
        """Ехать по улицам к перекрёстку goal, пока полиция не сядет на хвост на прямом участке.
        Улицы города изогнуты, поэтому машина идёт не «по оси», а от перекрёстка к перекрёстку."""
        nodes = w.city.nodes
        start = min(nodes, key=lambda k: math.hypot(nodes[k].x - car.x, nodes[k].y - car.y))
        pts = [(nodes[k].x, nodes[k].y) for k in w.roadnet.route(start, goal)]
        i = 1 if len(pts) > 1 else 0
        t = 0.0
        while t < tmax and pts:
            while i < len(pts) - 1 and math.hypot(pts[i][0] - car.x, pts[i][1] - car.y) < 13.0:
                i += 1
            tx, ty = pts[i]
            if i == len(pts) - 1 and math.hypot(tx - car.x, ty - car.y) < 13.0:
                break
            d = (math.atan2(ty - car.y, tx - car.x) - car.yaw + math.pi) % (2.0 * math.pi) - math.pi
            fx, fy = math.cos(car.yaw), math.sin(car.yaw)
            ahead = 1e9
            for v in w.vehicles:
                if v is not car and not v.removed and not getattr(v, 'police', False):
                    a = (v.x - car.x) * fx + (v.y - car.y) * fy
                    if 0.0 < a < 30.0 and abs((v.y - car.y) * fx - (v.x - car.x) * fy) < 2.2:
                        ahead = min(ahead, a)
            keys = []
            sp = math.hypot(car.vx, car.vy)
            if ahead < 9.0 + sp * 0.9:
                keys.append('s' if sp > 3.0 else 'space')
            elif sp < (cruise if abs(d) < 0.25 else 9.0):
                keys.append('w')
            elif sp > cruise + 4.0:
                keys.append('s')
            if d > 0.05:
                keys.append('a')
            elif d < -0.05:
                keys.append('d')
            harness.run(g, 0.2, keys=tuple(keys))
            t += 0.2
            if abs(d) < 0.12 and sp > 9.0 and w.police.seen:
                for u in w.police.units:
                    if u.removed or u.dead:
                        continue
                    back = (car.x - u.x) * fx + (car.y - u.y) * fy
                    if 6.0 < back < 30.0 and abs((u.y - car.y) * fx - (u.x - car.x) * fy) < 8.0:
                        return True
        return False

    def cruise(car, seconds, speed=15.0):
        """Ехать по своей полосе: улицы изогнуты, и «прямо» — значит вдоль полосы, а не по оси мира."""
        t = 0.0
        while t < seconds:
            lane, s, dist = w.roadnet.nearest_lane(car.x, car.y, 30.0)
            keys = ['w'] if math.hypot(car.vx, car.vy) < speed else []
            if lane is not None:
                tx, ty, _ = lane.pos(min(lane.length, s + 10.0))
                d = (math.atan2(ty - car.y, tx - car.x) - car.yaw + math.pi) % (2.0 * math.pi) - math.pi
                if d > 0.04:
                    keys.append('a')
                elif d < -0.04:
                    keys.append('d')
            harness.run(g, 0.1, keys=tuple(keys))
            t += 0.1

    def pview(u, v, z, tu, tv, tz, hud=False):
        """Свободная камера, заданная по чертежу города (улицы в мире изогнуты)."""
        c_ = w.city
        x, y = c_.to_world(u, v)
        tx, ty = c_.to_world(tu, tv)
        view(x, y, z, tx, ty, tz, hud)

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

    # пролог: ограбление три года назад в заснеженном Зимогорске, погоня, заслон на тракте — и автобус,
    # который привозит Макса на конечную
    g.new_game()
    ms = w.missions
    pl = w.player

    def intro_wait(start, extra, tmax=60.0):
        """Дождаться в прологе реплики, которая начинается со start, и ещё extra секунд."""
        t = 0.0
        while ms.intro is not None and t < tmax and not w.hud.sub_plain.startswith(start):
            g.step(1.0 / 30.0)
            t += 1.0 / 30.0
        assert ms.intro is not None and w.hud.sub_plain.startswith(start), 'в прологе нет реплики «%s»' % start
        harness.run(g, extra)

    intro_wait('Седой: Гони', 1.0)
    snap('robbery')
    # погоня: машину ведёт игрок
    t = 0.0
    while ms.intro is not None and not ms.intro['play'] and t < 20.0:
        harness.run(g, 0.2)
        t += 0.2
    it = ms.intro
    assert it is not None and it['play'], 'погоня пролога не началась'
    harness.run(g, 3.2, keys=('w',))
    snap('getaway', ('w',))
    # подъезжаем к метке на Зимогорском тракте: там заслон
    car, mk = it['car'], it['marker']
    car.x, car.y, car.yaw = w.city.frame(mk.x, mk.y).at(0.0, -26.0, math.pi / 2)
    car.vx = car.vy = car.speed = car.omega = 0.0
    car.sync()
    t = 0.0
    while it['end'] is None and t < 10.0:
        harness.run(g, 0.2, keys=('w',))
        t += 0.2
    assert it['end'] == 'tract', 'до заслона в прологе не доехали: %s' % it['end']
    intro_wait('Тракт перекрыли', 3.0)
    snap('roadblock')
    # три года спустя: конечная
    intro_wait('Водитель:', 1.2)
    snap('prologue')
    harness.press(g, 'escape')
    harness.run(g, 0.5)
    assert ms.intro is None and w.hero_car.alive(), 'после пролога «Ласточка» должна стоять в гараже'
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
    pview(b.x0 - 6, b.y0 - 6, 1.7, b.x0 + 12, b.y0 + 10, 7.5)
    snap('oldtown')
    pview(-300, -330, 110, 60, -20, 30)
    snap('skyline')
    w.sky.set_time(23.5)
    pview(-300, -330, 110, 60, -20, 30)
    snap('night')
    # улицы города изогнуты: вид сверху на Старый город и Сосновку
    w.sky.set_time(13.0)
    pview(-420.0, -260.0, 190.0, -200.0, -40.0, 0.0)
    snap('streets')
    # материк: Заречье за проливом, холмы и трасса
    w.sky.set_time(17.6)
    pview(250.0, 560.0, 70.0, -40.0, 900.0, 0.0)
    snap('mainland')
    w.sky.set_time(11.0)
    lm = w.city.landmarks['zakhar']
    view(*w.city.frame(*lm['door']).cam(-46.0, -58.0, 26.0, 30.0, 40.0, 0.0))
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
    F = w.city.plan_frame(8.0, b.y1 - 1.7)
    pl.teleport(*F.at(0.0, 0.0, 0.0))
    harness.run(g, 6.0)
    w.cam.yaw = F.h(2.3)
    w.cam.pitch = -0.1
    w.cam.snap()
    lively(F.h(2.3))
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
    pl.teleport(*harness.side(x, y, yaw, right=3.0))
    pl.enter_vehicle(car, silent=True)
    w.cam.yaw = yaw
    cruise(car, 4.5)
    nohelp()
    snap('drive', ('w',))

    # Большой мост: с материка в город
    seg = next(sg for sg in w.city.bridges if sg['bridge']['name'] == 'north')
    BF = w.city.plan_frame(seg['c'], (seg['a'] + seg['b']) * 0.5)        # середина моста
    mx, my = BF()
    south = BF.h(-math.pi / 2)

    def heads_south(l):
        return math.cos(math.atan2(l.y1 - l.y0, l.x1 - l.x0) - south) > 0.95

    lanes = [l for l in w.roadnet.lanes_near(mx, my, 0.0, 60.0) if l.turn is None and heads_south(l) and l.length > 80.0]
    lanes.sort(key=lambda l: -l.length)
    bl = lanes[0]
    for v in list(w.vehicles):
        if v is not car and not v.keep and math.hypot(v.x - mx, v.y - my) < bl.length * 0.5 + 60.0:
            w.remove_vehicle(v)
    car.x, car.y, car.yaw = bl.pos(40.0)
    car.vx, car.vy, car.speed = math.cos(car.yaw) * 14.0, math.sin(car.yaw) * 14.0, 14.0
    car.sync()
    w.cam.yaw = car.yaw
    w.cam.snap()
    w.sky.set_time(16.5)
    harness.run(g, 3.2, keys=('w',))
    nohelp()
    snap('bridge', ('w',))
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
    far = max(w.city.nodes, key=lambda k: (w.city.nodes[k].x - car.x) if not w.city.in_north(w.city.nodes[k].x, w.city.nodes[k].y) and abs(w.city.nodes[k].y - car.y) < 60.0 else -1e9)
    if not chase(car, far):
        print('внимание: полиция не догнала, кадр «chase» без погони')
    w.cam.free_t = 0.0
    w.cam.yaw = car.yaw + 2.6
    w.cam.pitch = -0.12
    harness.run(g, 0.2, keys=('w',))
    nohelp()
    snap('chase', ('w',))
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

    w.sky.set_time(13.0)
    w.sky.time_scale = 0.0
    ap = c.landmarks['airfield']['apron']
    bx, by = c.frame(*ap)(-60.0, -8.0)

    # чоппер «Ворон» крупно, с ездоком и пассажиром.  Камера — спереди сбоку
    from game.defs import random_look
    cx, cy = bx + 4.0, by
    yaw = -0.33
    fx, fy = math.cos(yaw), math.sin(yaw)
    moto = w.spawn_vehicle('chopper', cx, cy, yaw, paint=1)
    moto.keep = True
    pl.teleport(moto.x, moto.y - 3.0)
    pl.enter_vehicle(moto, silent=True)
    q = w.spawn_ped(moto.x, moto.y - 4.0, 0.0, random_look(random.Random(21), 'G'))
    q.keep = True
    w.put_in_vehicle(q, moto)
    harness.run(g, 0.5, keys=('space',))
    w.cam.override = (cx + math.cos(yaw + 0.7) * 5.3, cy + math.sin(yaw + 0.7) * 5.3, 1.75, cx + fx * 0.1, cy + fy * 0.1, 0.8)
    nohelp(('space',))
    w.hud.show(False)
    harness.run(g, 0.2, keys=('space',))
    snap('chopper', ('space',))
    w.cam.override = None
    pl.leave_vehicle(force=True)
    harness.run(g, 0.6)
    w.take_out(q, 1)
    w.remove_ped(q)
    w.remove_vehicle(moto)

    # три новые машины — седан «Тень», хэтчбек «Зажигалка» и купе «Катана» — в двух окрасках, носом к камере
    row = []
    yaw = -0.25
    fx, fy = math.cos(yaw), math.sin(yaw)
    cx, cy = bx + 6.0, by
    for kind, paint, f, l in (('shade', 3, 0.0, 0.0), ('gti', 0, 0.4, 3.3), ('coupe', 9, -0.1, -3.3),
                              ('coupe', 1, -5.4, 1.8), ('gti', 10, -5.7, -1.6), ('shade', 5, -5.2, 5.2)):
        v = w.spawn_vehicle(kind, cx + fx * f - fy * l, cy + fy * f + fx * l, yaw, paint=paint)
        v.keep = True
        row.append(v)
    view(cx + math.cos(yaw - 0.45) * 8.2, cy + math.sin(yaw - 0.45) * 8.2, 3.1, cx - fx * 2.4, cy - fy * 2.4, 0.5)
    snap('cars')
    for v in row:
        w.remove_vehicle(v)

    # машина героя: у «Ласточки» есть салон — за стёклами видно Макса за рулём и брата рядом
    v = w.spawn_vehicle('retro', cx, cy, yaw, paint=0)
    v.keep = True
    pl.teleport(cx, cy - 3.0)
    pl.enter_vehicle(v, silent=True)
    q = w.spawn_ped(cx, cy - 4.0, 0.0, story.person_look('bruce'))
    q.keep = True
    w.put_in_vehicle(q, v)
    harness.run(g, 0.6, keys=('space',))
    w.cam.override = (cx + fx * 3.9 - fy * 1.3, cy + fy * 3.9 + fx * 1.3, 1.6, cx + fx * 0.6, cy + fy * 0.6, 0.98)
    nohelp(('space',))
    w.hud.show(False)
    harness.run(g, 0.2, keys=('space',))
    snap('hero', ('space',))
    w.cam.override = None
    pl.leave_vehicle(force=True)
    harness.run(g, 0.6)
    w.take_out(q, 1)
    w.remove_ped(q)
    w.remove_vehicle(v)

    # такси — жёлтый кэб с шашечками: стоянка таксопарка
    lot = c.landmarks['taxi']['lot']
    pl.teleport(*c.frame(*lot)(2.0, 9.0))
    harness.run(g, 1.0)
    for v in list(w.vehicles):
        if math.hypot(v.x - lot[0], v.y - lot[1]) < 30.0 and v is not pl.vehicle:
            w.remove_vehicle(v)
    row = []
    TF = c.frame(*lot)                              # разметка стоянки повёрнута вместе с улицей
    for dx, dyaw in ((-6.8, 0.0), (-3.4, 0.0), (0.0, 0.0), (5.2, math.pi - 0.5)):
        v = w.spawn_vehicle('taxi', *TF.at(dx, 1.6 if dyaw else 0.0, math.pi / 2 + dyaw))
        v.keep = True
        row.append(v)
    w.sky.set_time(16.5)
    view(*TF.cam(6.4, 8.6, 2.1, -1.6, 0.4, 0.75))
    snap('taxi')
    for v in row:
        w.remove_vehicle(v)

    # мусор у контейнера во дворе и остов машины на пустыре; под предметами и вдоль стен — мягкие тени
    w.sky.set_time(11.0)
    pview(-49.6, -117.6, 2.3, -55.8, -121.6, 0.45)
    snap('yard')
    pview(-404.5, 191.5, 2.1, -396.0, 198.2, 0.55)
    snap('lot')
    w.cam.override = None
    w.hud.show(True)

    # тюнинг: три машины у дома и меню ателье
    gi = c.special['garage']
    gx0, gy0, gx1, gy1 = gi['rect']
    fx, fy = gi['front']
    GF = c.frame(fx, fy)                            # всё у гаража — в его осях: улица здесь изогнута
    pl.teleport(*GF(-6.0, -3.0))
    harness.run(g, 1.0)
    tunes = [('sports', 0, {'spoiler': 3, 'rims': 3, 'neon': 1, 'bumper': 1, 'susp': 1, 'exhaust': 2, 'xenon': 2}),
             ('sedan', 2, {'spoiler': 2, 'rims': 2, 'neon': 3, 'roof': 1, 'susp': 3}),
             ('suv', 4, {'spoiler': 1, 'rims': 4, 'neon': 2, 'roof': 2, 'bumper': 1})]
    cars = []
    for i, (kind, paint, tune) in enumerate(tunes):
        v = w.spawn_vehicle(kind, *GF.at(-8.0 + i * 5.5, -7.5, math.pi / 2 + 0.5), paint=paint)
        v.keep = True                               # иначе игра уберёт «ничью» машину, пока герой далеко
        v.apply_tune(tune)
        cars.append(v)
    w.sky.set_time(21.6)
    view(*GF.cam(-7.5, -17.0, 3.0, -2.5, -7.0, 0.7))
    snap('tuned')
    w.cam.override = None
    w.hud.show(True)
    w.sky.set_time(12.0)
    pl.teleport(*harness.side(cars[0].x, cars[0].y, cars[0].yaw, right=3.0))
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
    # гараж: в первой клетке — «Ласточка», в двух других — машины с тюнингом; ворота открыты
    w.remove_vehicle(cars.pop())
    for v, sl in zip(cars, w.garage.slots[1:]):
        v.x, v.y, v.yaw = sl[0], sl[1], w.garage.yaw
        v.vx = v.vy = v.speed = 0.0
        v.sync()
    pl.teleport(*GF(3.6, 5.0))
    harness.run(g, 2.0)
    gcx, gcy = c.to_world((gx0 + gx1) / 2 + 0.6, (gy0 + gy1) / 2)
    cxy = GF(-5.0, -2.5)
    view(cxy[0], cxy[1], 2.7, gcx, gcy, 1.2, hud=True)
    pl.teleport(*GF(3.6, 5.0))                      # ворота открыты, пока герой рядом
    pl.ped.yaw = GF.h(math.pi / 2)
    harness.run(g, 1.5)
    nohelp()
    snap('garage')
    w.cam.override = None
    w.hud.show(True)
    assert w.hero_car.v in w.garage.cars and len(w.garage.cars) == 3
    for v in cars:                                  # «Ласточка» остаётся в гараже
        w.remove_vehicle(v)

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
        w.cam.override = c.plan_frame(sx, sy).cam(-4.6, -3.6, 2.0, 0.8, 0.1, 0.85)
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
        w.cam.override = c.to_world(500.0, -14.0) + (13.0,) + c.to_world(552.0, 15.0) + (3.6,)
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


def tester_shot():
    """Меню тестера (F9) для README: docs/tester.jpg."""
    import game
    from panda3d.core import ClockObject
    game.TESTER = True                              # как в сборке для тестера: игра создаётся уже с меню
    random.seed(int(os.environ.get('DD_SHOT_SEED', '1')))
    g = harness.make_game(1280, 720)
    clock = ClockObject.getGlobalClock()            # игра шагает вручную: счётчик кадров показал бы скорость
    clock.setMode(ClockObject.MNonRealTime)         # программного рендера, а не игры
    clock.setDt(1.0 / 60.0)
    w = harness.start_game(g, story=True)
    t = g.tester
    by = dict((m['id'], m) for m in M.MISSIONS)
    harness.run(g, 0.5)
    t.open()
    t.spawn('sports')
    harness.run(g, 0.5)
    t.open()
    t.set_god(True)
    t.start_mission(by['s2'])
    for i in range(900):                            # звонок брата: реплики листает пробел
        g.inp._dn('space') if i % 6 == 0 else g.inp._up('space')
        g.step(1.0 / 30.0)
        if i > 30 and not w.player.freeze and w.cam.override is None and not w.hud.phone_on:
            break
    g.inp._up('space')
    harness.run(g, 1.0)
    t.open()
    t.set_wanted(2)
    t.set_hold(True)
    t.heal()
    main_menu = g.ui.current()
    main_menu.sel = [it.label for it in main_menu.items].index('Бессмертие')
    g.ui.refresh()
    for _ in range(40):                             # строка сведений обновляется пять раз в секунду
        clock.tick()
        g.step(1.0 / 30.0)
    png = os.path.join(TMP, 'tester.png')
    harness.shot(g, png)
    Image.open(png).convert('RGB').save(os.path.join(DOCS, 'tester.jpg'), quality=88)
    print('снимок: tester ->', DOCS, '|', t.line.getText())


def gfx_shots():
    """Наборы качества графики для README: один и тот же кадр на «Минимуме», «Среднем» и «Ультре»
    (docs/gfx_min.jpg, gfx_med.jpg, gfx_ultra.jpg), ночная улица и ночной дождь на «Ультре».

    Нужен OpenGL (DD_TEST_DISPLAY=p3headlessgl).  На «Ультре» сглаживание здесь — FXAA, а не MSAA 4×, как
    в самом наборе: программная Mesa рисует кадр с MSAA десятки минут, а на снимке разницы почти не видно."""
    from game import gfx as G
    random.seed(int(os.environ.get('DD_SHOT_SEED', '5')))
    g = harness.make_game(1280, 720)
    if not g.gfx.supported:
        sys.exit('шейдеры недоступны: запустите с DD_TEST_DISPLAY=p3headlessgl (нужен OpenGL без окна)')
    s = g.settings
    G.set_preset(s, G.PRESET_MIN)                   # пока сцена расставляется, рисуем по-простому: так быстрее
    g.gfx.apply()
    w = harness.start_game(g)
    c = w.city
    pl = w.player
    harness.quiet(w)

    def snap(name, preset):
        G.set_preset(s, preset)
        if preset == G.PRESET_ULTRA:
            s.set('msaa', 1)
        g.gfx.apply()
        w.hud.help_t = 0.01
        w.hud.title_t = 0.01
        w.hud.big_t = 0.01
        for _ in range(2):
            g.base.graphicsEngine.renderFrame()
            harness.run(g, 1.0 / 30.0)
        png = os.path.join(TMP, name + '.png')
        harness.shot(g, png)
        bad = [sh for sh in g.gfx._shaders if sh.getErrorFlag()]
        assert not bad and (g.gfx.active or preset == G.PRESET_MIN), 'шейдеры не собрались: %s' % name
        Image.open(png).convert('RGB').save(os.path.join(DOCS, name + '.jpg'), quality=90)
        print('снимок:', name, flush=True)

    # день: проспект в Деловом центре, «Ласточка» и такси — тени, блеск кузова, затенение под машинами
    w.sky.set_weather('clear')
    w.sky.set_time(16.5)
    w.sky.time_scale = 0.0
    F = c.plan_frame(20.0, -181.0)
    pl.teleport(*F.at(0.0, 0.0, 0.0))
    w.cam.face(*F.at(0.0, 0.0, 0.0))
    for kind, du, dv, yaw, paint in (('retro', 3.5, -2.6, 0.5, 1), ('taxi', 7.0, 3.0, -0.3, 0)):
        v = w.spawn_vehicle(kind, *F.at(du, dv, yaw), paint=paint)
        v.keep = True
    harness.run(g, 2.0)
    z = c.ground_z(*F())
    w.cam.override = F.cam(-3.5, -1.5, z + 1.5, 4.0, -1.0, z + 0.6)
    harness.run(g, 0.3)
    for name, preset in (('gfx_min', G.PRESET_MIN), ('gfx_med', G.PRESET_MED), ('gfx_ultra', G.PRESET_ULTRA)):
        snap(name, preset)
    w.cam.override = None
    # ночь в Старом городе: фонари, фары «Ласточки», маячки патрульной машины, свечение огней
    G.set_preset(s, G.PRESET_MIN)
    g.gfx.apply()
    w.sky.set_time(23.5)
    b = c.block_grid[(1, 3)]
    lane, s0, _ = w.roadnet.nearest_lane(*c.to_world(b.x0 + 30.0, b.y0 - 8.0), 40.0)
    x, y, yaw = lane.pos(min(lane.length - 30.0, max(8.0, s0)))
    car = w.spawn_vehicle('retro', x, y, yaw, paint=1)
    car.keep = True
    pl.teleport(*harness.side(x, y, yaw, right=3.0))
    harness.run(g, 0.3)
    pl.enter_vehicle(car, silent=True)
    harness.run(g, 1.0)
    cop = w.spawn_vehicle('police', *harness.side(x, y, yaw, right=-3.4, fwd=22.0), yaw + math.pi + 0.35)
    cop.keep = True
    cop.siren = True
    cop.set_lights(True)
    w.cam.yaw = yaw
    w.cam.snap()
    harness.run(g, 0.6)
    snap('gfx_night', G.PRESET_ULTRA)
    # та же улица под дождём: мокрый асфальт и лужи отражают огни
    G.set_preset(s, G.PRESET_MIN)
    g.gfx.apply()
    cop.siren = False
    w.sky.set_weather('rain')
    harness.run(g, 1.5)
    snap('gfx_rain', G.PRESET_ULTRA)
    # меню «Графика»: набор качества, ограничение кадров, счётчик кадров — и подробные настройки
    w.sky.set_weather('clear')
    w.sky.set_time(12.0)
    if pl.vehicle is not None:
        pl.leave_vehicle(force=True)
    harness.run(g, 1.5)
    g.pause()
    g.ui.open(g.settings_menu())
    harness.press(g, 'enter')                       # «Графика и экран»
    for name in ('gfx_menu', 'gfx_details'):
        harness.run(g, 0.2)
        png = os.path.join(TMP, name + '.png')
        harness.shot(g, png)
        Image.open(png).convert('RGB').save(os.path.join(DOCS, name + '.jpg'), quality=90)
        print('снимок:', name, flush=True)
        m = g.ui.stack[-1]
        m.sel = [it.label for it in m.items].index('Подробные настройки') if name == 'gfx_menu' else m.sel
        if name == 'gfx_menu':
            harness.press(g, 'enter')
    g.ui.close_all()
    g.resume()
    print('снимки графики ->', DOCS)


if __name__ == '__main__':
    if '--tester' in sys.argv:
        tester_shot()
    elif '--gfx' in sys.argv:
        gfx_shots()
    else:
        main()
