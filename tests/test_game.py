# -*- coding: utf-8 -*-
"""Интеграционные тесты: игра целиком запускается без окна (программный рендер)."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import harness
from bot import Bot
from game import missions as M
from game import settings as settings_mod
from game.defs import W_FIST, W_PISTOL, W_UZI, W_ROCKET, random_look
from game.collision import F_CAR
from game.vehicle import Vehicle, SPECS, ZONE_CARS

DT = 1.0 / 30.0


@pytest.fixture(scope='module')
def game():
    return harness.make_game(640, 360)


@pytest.fixture()
def world(game):
    random.seed(20240229)                    # одинаковый город и трафик в каждом прогоне
    w = harness.start_game(game)
    w.player.invincible = False
    return w


def test_menu_and_new_game(game):
    game.to_main_menu()
    assert game.state == 'menu' and game.ui.active
    harness.run(game, 1.0)
    w = harness.start_game(game)
    assert game.state == 'play' and not game.ui.active
    assert w.player.state == 'foot' and w.player.ped.health == 100
    assert len(w.vehicles) > 10 and len(w.peds) > 8


def test_authors_page_credits_the_model_authors(game):
    """Страница «Авторы» в главном меню.  Машина героя взята по лицензии CC BY: автор, работа, лицензия и
    то, что изменено, должны быть названы там, где это увидит игрок, — а ещё в титрах и во всех описаниях."""
    from game import app
    game.to_main_menu()
    menu = game.ui.current()
    labels = [i.label for i in menu.items]
    assert labels == ['Новая игра', 'Продолжить', 'Настройки', 'Управление', 'Авторы', 'Выход']
    menu.sel = labels.index('Авторы')
    harness.press(game, 'enter')
    page = game.ui.current()
    assert page.title == 'Авторы' and page.text == app.AUTHORS_TEXT
    for need in ('Bricchi Games', 'Retro Car With Interior', 'bricchi-games.itch.io/retro-car-with-interior',
                 'CC BY 4.0', 'creativecommons.org/licenses/by/4.0', 'Изменено',
                 'MoiDev', 'designersoup', 'boggle', 'GGBot', 'Duhgless', 'Kenney', 'Quaternius', 'Elbolilloduro',
                 'Mesh2Motion', 'Daniel Jurys', 'Craig Snedeker', 'Panda3D'):
        assert need in page.text, need
    # текст помещается в поле без переносов и не уходит под кнопку «Назад»
    lines = page.text.split('\n')
    assert max(len(line) for line in lines) <= 62 and len(lines) <= 22
    harness.press(game, 'escape')
    assert game.ui.current() is menu
    assert 'Bricchi Games' in app.CREDITS_TEXT and 'CC BY 4.0' in app.CREDITS_TEXT
    assert 'ROHHSA' not in app.CREDITS_TEXT + app.AUTHORS_TEXT            # плашек Free PSX UI в игре больше нет
    for rel in ('README.md', os.path.join('assets', 'models', 'CREDITS.md'), os.path.join('tools', 'make_release.py')):
        with open(os.path.join(harness.ROOT, rel), encoding='utf-8') as f:
            text = f.read()
        assert 'Bricchi Games' in text and 'Retro Car With Interior' in text, rel
        assert 'bricchi-games.itch.io/retro-car-with-interior' in text and 'creativecommons.org/licenses/by/4.0' in text, rel


def test_walk_and_collide(game, world):
    pl = world.player
    harness.quiet(world, peds=True)
    x0, y0 = pl.pos()
    world.cam.yaw = -math.pi / 2            # на юг, через дорогу
    harness.run(game, 2.0, keys=('w',))
    x1, y1 = pl.pos()
    assert y1 < y0 - 5.0
    # в стену дома пройти нельзя (в стороне от двери: в дверь-то войти можно)
    lm = world.city.landmarks['terminal']
    pl.teleport(lm['door'][0] + 4.0, lm['door'][1] - 3.0)
    world.cam.yaw = math.pi / 2
    harness.run(game, 6.0, keys=('w', 'shift'))
    assert pl.pos()[1] < lm['rect'][1] + 0.1
    assert world.interiors.current is None


def test_enter_drive_exit(game, world):
    w = world
    pl = w.player
    harness.quiet(w)
    x, y = w.city.landmarks['terminal']['road']
    car = w.spawn_vehicle('sedan', x - 8.0, y - 1.0, 0.0)
    pl.teleport(x - 8.0, y + 1.5)
    harness.press(game, 'f')
    harness.run(game, 2.0)
    assert pl.vehicle is car and pl.state == 'car'
    harness.run(game, 3.0, keys=('w',))
    assert car.speed > 8.0 and car.x > x
    harness.run(game, 3.0, keys=('s',))
    harness.press(game, 'f')
    harness.run(game, 3.0)
    assert pl.vehicle is None and pl.state == 'foot'


def test_carjack_traffic(game, world):
    w = world
    pl = w.player
    v = None
    for _ in range(600):
        # машина, которая едет не слишком быстро: на ходу из быстрой водителя не вытащить
        v = w.nearest_vehicle(pl.ped.x, pl.ped.y, 150.0,
                              lambda q: q.npc and q.mode == Vehicle.RAIL and math.hypot(q.vx, q.vy) < 4.0)
        if v is not None:
            break
        game.step(DT)
    assert v is not None
    x, y = v.door_pos(-1)
    pl.teleport(x - 0.5, y)
    harness.press(game, 'f')
    thrown = False
    for _ in range(150):
        game.step(DT)
        # водителя выбросили на дорогу (смотрим всё время: потом его может сбить поток, и обидчик сменится)
        thrown = thrown or any(p.last_attacker is pl.ped for p in w.peds if not p.is_player)
    assert pl.vehicle is v and not v.npc
    assert thrown
    assert w.stats['stolen'] == 1


def test_shooting_and_wanted(game, world):
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    pl.give_weapon(W_PISTOL, 50)
    x, y = w.city.landmarks['terminal']['road']
    pl.teleport(x, y - 3.0)
    victim = w.spawn_ped(x + 8.0, y - 3.0, math.pi, random_look(random, 'D'))
    victim.keep = True
    victim.set_state('stand')
    harness.run(game, 0.2)
    for _ in range(60):
        # целимся из точки прицеливания камеры
        ox, oy, oz, dx, dy, dz = w.cam.aim_ray()
        w.cam.yaw += math.atan2(victim.y - oy, victim.x - ox) - math.atan2(dy, dx)
        w.cam.pitch = math.atan2(victim.z + 1.1 - oz, math.hypot(victim.x - ox, victim.y - oy))
        game.inp._dn('mouse1')
        game.step(DT)
        game.inp._up('mouse1')
        game.step(DT)
        game.step(DT)
        if victim.dead:
            break
    assert victim.dead
    assert w.police.level >= 1
    assert w.stats['kills'] == 1


def test_rocket_destroys_car(game, world):
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    x, y = w.city.landmarks['terminal']['road']
    pl.teleport(x, y - 3.0)
    car = w.spawn_vehicle('hatch', x + 14.0, y - 3.3, 0.0)
    car.keep = True
    pl.give_weapon(W_ROCKET, 3)
    pl.select(W_ROCKET)
    w.cam.yaw = 0.0
    w.cam.pitch = -0.06
    harness.run(game, 0.3)
    harness.press(game, 'mouse1')
    harness.run(game, 3.0)
    assert car.dead
    assert w.stats['wrecks'] >= 1


def test_wasted_and_respawn(game, world):
    w = world
    pl = w.player
    pl.add_money(2000)
    pl.ped.hurt(500.0, None, 'bullet')
    assert pl.state == 'dead'
    harness.run(game, 7.0)
    assert pl.state == 'foot' and pl.ped.health == pl.ped.max_health
    hx, hy = w.city.landmarks['hospital']['door']
    assert math.hypot(pl.pos()[0] - hx, pl.pos()[1] - hy) < 12.0
    assert pl.money == 1500


def test_busted(game, world):
    w = world
    pl = w.player
    pl.give_weapon(W_UZI, 100)
    w.police.set_level(1)
    cop = w.police.make_cop(pl.ped.x + 1.0, pl.ped.y, 0.0)
    cop.attack(pl.ped)
    w.police.cops.append(cop)
    harness.run(game, 3.0)
    assert pl.state == 'busted'
    pl.ped.hurt(500.0, cop, 'bullet')            # арестованного добить нельзя
    assert pl.state == 'busted' and not pl.ped.dead
    harness.run(game, 6.0)
    assert pl.state == 'foot' and w.police.level == 0
    px, py = w.city.landmarks['police']['door']
    assert math.hypot(pl.pos()[0] - px, pl.pos()[1] - py) < 12.0
    assert W_UZI not in pl.ammo                  # оружие конфисковано
    assert w.stats['busted'] == 1


def test_spray_shop_clears_wanted(game, world):
    w = world
    pl = w.player
    pl.add_money(1000)
    bx, by = w.city.landmarks['spray']['bay']
    car = w.spawn_vehicle('sedan', bx, by, math.pi / 2)
    pl.teleport(bx + 3.0, by)
    pl.enter_vehicle(car, silent=True)
    car.health = 400.0
    w.police.set_level(2)
    car.set_paint(0)
    harness.run(game, 1.5)
    # заехал в бокс и остановился — открылось меню ателье; первая строка — покраска
    assert game.state == 'shop' and game.ui.stack[-1].title == 'Ателье'
    assert w.cam.override is not None
    harness.press(game, 'enter')
    assert game.ui.stack[-1].title == 'Покраска'
    harness.press(game, 'arrow_down')                        # с красного на синий
    harness.press(game, 'enter')
    assert car.paint == 1 and pl.money == 700
    assert w.police.level == 0 and car.health == car.max_health
    harness.press(game, 'escape')
    harness.press(game, 'escape')
    assert game.state == 'play' and not game.ui.active and w.cam.override is None
    harness.run(game, 1.0)
    assert game.state == 'play'                              # пока стоишь в боксе, меню не открывается заново


def test_pickups_and_packages(game, world):
    w = world
    pl = w.player
    ms = w.missions
    pk = next(p for p in ms.pickups if p.kind == 'package')
    pl.teleport(pk.x, pk.y)
    harness.run(game, 0.3)
    assert len(ms.packages) == 1 and pl.money == 500
    wp = next(p for p in ms.pickups if p.kind == 'weapon' and not p.removed)
    pl.teleport(wp.x, wp.y)
    harness.run(game, 0.3)
    assert wp.wid in pl.ammo


def test_save_and_load(game, world):
    w = world
    pl = w.player
    pl.add_money(4321)
    pl.give_weapon(W_PISTOL, 77)
    w.missions.done.add('v1')
    assert w.missions.save_game()
    data = settings_mod.load_save()
    assert data['money'] == 4321
    game.to_main_menu()
    game.continue_game()
    w = game.world
    assert game.state == 'play'
    assert w.player.money == 4321 and w.player.ammo.get(W_PISTOL) == 77
    assert 'v1' in w.missions.done
    assert w.missions.next_mission('vano')['id'] == 'v2'


def test_pause_menu_navigation(game, world):
    harness.press(game, 'escape')
    assert game.state == 'pause' and game.ui.active
    harness.press(game, 'arrow_down')
    harness.press(game, 'enter')                 # карта
    assert game.ui.extra is not None
    harness.press(game, 'escape')
    assert game.ui.extra is None
    for _ in range(3):                           # статистика, настройки, управление
        harness.press(game, 'arrow_down')
        harness.press(game, 'enter')
        harness.run(game, 0.1)
        harness.press(game, 'escape')
    harness.press(game, 'escape')
    assert game.state == 'play' and not game.ui.active


def test_safehouse_save_asks_first(game, world):
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    mk = w.missions.save_mk
    settings_mod.write_save(dict(money=1, done=[], packages=[]))        # «старое» сохранение
    pl.add_money(777)
    pl.teleport(mk.x, mk.y)
    harness.run(game, 0.3)
    assert game.state == 'shop' and game.ui.active          # вопрос, а не молчаливая перезапись
    assert settings_mod.load_save()['money'] == 1
    harness.press(game, 'escape')                            # отказались
    assert game.state == 'play'
    harness.run(game, 0.5)
    assert game.state == 'play'                              # пока стоим в маркере, вопрос не повторяется
    assert settings_mod.load_save()['money'] == 1
    pl.teleport(mk.x + 6.0, mk.y)
    harness.run(game, 0.3)
    pl.teleport(mk.x, mk.y)
    harness.run(game, 0.3)
    assert game.state == 'shop'
    hour = w.sky.hour
    harness.press(game, 'enter')                             # «Сохранить игру»
    harness.run(game, 0.3)
    assert game.state == 'play'
    assert settings_mod.load_save()['money'] == 777
    assert abs(((w.sky.hour - hour) % 24.0) - 6.0) < 0.2


def test_gun_shop_marker(game, world):
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    pl.add_money(1000)
    mk = w.missions.shop_mks[0]
    pl.teleport(mk.x, mk.y)
    harness.run(game, 0.3)
    assert game.state == 'shop'
    from game.defs import WEAPONS, WEAPON_ORDER
    goods = [wid for wid in WEAPON_ORDER if WEAPONS[wid].price > 0]
    for _ in range(goods.index(W_PISTOL)):                   # до пистолета
        harness.press(game, 'arrow_down')
    harness.press(game, 'enter')
    assert W_PISTOL in pl.ammo and pl.money == 750
    harness.press(game, 'escape')
    assert game.state == 'play'


@pytest.mark.parametrize('mid', [m['id'] for m in M.MISSIONS])
def test_story_mission(game, world, mid):
    """Каждое сюжетное задание проходится ботом от начала до конца."""
    w = world
    pl = w.player
    pl.invincible = True
    ms = w.missions
    spec = next(m for m in M.MISSIONS if m['id'] == mid)
    if spec.get('story'):
        ms.done -= M.STORY_IDS                  # сюжет ещё не пройден: задание идёт с самого начала
        ms.done |= set(spec['req'])
        ms.ckpt.clear()
        ms.sync_story()
        pl.money = 0
    else:
        x, y = w.city.landmarks[spec['contact']]['door']
        pl.teleport(x, y - 2.0)
    assert ms.start(spec)
    bot = Bot(game, verbose=False)
    t = 0.0
    while ms.active is not None and t < 300.0:
        bot.step(DT)
        game.step(DT)
        t += DT
    pl.invincible = False
    assert mid in ms.done, 'задание %s не пройдено (цель: %s)' % (mid, bot.last_obj)
    assert pl.money >= spec['reward'] * 0.25


def test_taxi_job(game, world):
    w = world
    pl = w.player
    pl.invincible = True
    lot = w.city.landmarks['taxi']['lot']
    cab = w.spawn_vehicle('taxi', lot[0], lot[1], 0.0)
    pl.teleport(lot[0] + 3.0, lot[1])
    pl.enter_vehicle(cab, silent=True)
    harness.run(game, 0.3)
    harness.press(game, 't')
    assert w.missions.active is not None and w.missions.active.spec['id'] == 'taxi'
    bot = Bot(game, verbose=False)
    t = 0.0
    while w.stats['taxi'] < 2 and t < 240.0:
        bot.step(DT)
        game.step(DT)
        t += DT
    pl.invincible = False
    assert w.stats['taxi'] >= 2 and pl.money > 0
    harness.press(game, 't')                     # конец смены
    harness.run(game, 0.5)
    assert w.missions.active is None


def test_broken_mission_script_does_not_crash(game, world):
    """Ошибка внутри сценария задания срывает задание, но не роняет игру."""
    w = world
    ms = w.missions

    def broken(m):
        yield 0.1
        raise RuntimeError('сценарий сломан')
    spec = dict(id='zz', contact='vano', title='Сбой', reward=1, fn=broken, req=[])
    assert ms.start(spec)
    harness.run(game, 1.0)
    assert ms.active is None and 'zz' not in ms.done
    assert game.state == 'play'
    path = os.path.join(settings_mod.user_dir(), 'crash.log')
    assert 'сценарий сломан' in open(path, encoding='utf-8').read()
    os.remove(path)


def test_first_mission_like_a_player(game, world):
    """Начало сюжета так, как его проходит человек: пешком в маркер, брифинг, F — и за руль."""
    w = world
    pl = w.player
    ms = w.missions
    harness.quiet(w)
    its = w.interiors
    room = its.rooms['vano']
    x, y = room.out
    pl.teleport(x, y - 4.0)
    harness.run(game, 0.3)
    assert ms.active is None
    w.cam.yaw = math.pi / 2                       # лицом к гаражу
    harness.run(game, 3.0, keys=('w',))           # в дверь с жёлтой стрелкой
    assert its.current is room and pl.indoors
    assert its.resident('vano') is not None       # хозяин на месте
    # к розовой метке возле Вано
    tx, ty = room.spots['talk'][:2]
    for _ in range(200):
        px, py = pl.pos()
        if ms.active is not None:
            break
        w.cam.yaw = math.atan2(ty - py, tx - px)
        harness.run(game, 0.1, keys=('w',))
    assert ms.active is not None and ms.active.spec['id'] == 'v1'
    harness.run(game, 0.2)
    assert pl.freeze and its.current is room      # брифинг идёт в гараже
    for _ in range(8):                            # пролистываем реплики
        if not pl.freeze:
            break
        harness.run(game, 0.6)
        harness.press(game, 'enter')
    harness.run(game, 1.2)
    assert not pl.freeze and pl.state == 'foot'    # лишний Enter после сценки не сажает в машину
    assert its.current is None and not pl.indoors   # после разговора герой снова на улице, у двери
    assert 'Волну' in ms.active.objective
    car = ms.active.vehicles[0]
    dx, dy = car.door_pos(-1)
    pl.ped.x, pl.ped.y = dx - 0.4, dy             # подошли к водительской двери
    harness.run(game, 0.2)
    harness.press(game, 'f')
    harness.run(game, 2.5)
    assert pl.vehicle is car
    harness.run(game, 0.3)
    assert 'Порт' in ms.active.objective
    # едем сами: газ в пол по прямой
    x0 = car.x
    harness.run(game, 3.0, keys=('w',))
    assert abs(car.x - x0) > 15.0
    # бросили машину Вано и уничтожили её — задание провалено, игра продолжается
    car.explode(True)
    harness.run(game, 1.0)
    assert ms.active is None and 'v1' not in ms.done
    assert ms.next_mission('vano')['id'] == 'v1'


def test_hud_layers_keep_order_after_menu(game, world):
    """После закрытия меню надписи остаются поверх затемнения и чёрных полос сценок."""
    harness.press(game, 'escape')
    harness.run(game, 0.2)
    harness.press(game, 'escape')
    harness.run(game, 0.2)
    assert game.state == 'play'
    world.missions.letterbox(True)
    order = [c.getName() for c in game.base.aspect2d.getChildren()]
    assert order.index('hud') < order.index('fade') < order.index('letterbox') < order.index('hud_msg')
    world.missions.letterbox(False)


def test_subtitles_stay_above_letterbox(game, world):
    hud = world.hud
    for text in ('Короткая реплика.', 'Очень длинная реплика, которая займёт несколько строк подряд: ' + 'слово ' * 40):
        hud.subtitle(text, 2.0, clear=True)
        harness.run(game, 0.2)
        lo, hi = hud.sub_text.getTightBounds()
        assert lo.z > -0.8                      # нижняя строка выше полосы (она начинается на -0.8)
    hud.clear_subtitles()


def test_no_floating_health_or_armor(game, world):
    assert not [p for p in world.missions.pickups if p.kind in ('health', 'armor')]
    assert [p for p in world.missions.pickups if p.kind == 'weapon']         # оружие на улицах осталось


def test_graphics_settings_menu(game, world):
    """Настройки → «Графика и экран»: фильтр текстур меняется сразу, прочее сохраняется в настройках."""
    from panda3d.core import SamplerState
    g = game
    s = g.settings
    g.pause()
    g.ui.open(g.settings_menu())
    assert g.ui.stack[-1].title == 'Настройки'
    harness.press(g, 'enter')                                   # первый пункт — «Графика и экран»
    m = g.ui.stack[-1]
    assert m.title == 'Графика'
    labels = [it.label for it in m.items]
    assert labels == ['Качество графики', 'Подробные настройки', 'Режим экрана', 'Разрешение',
                      'Вертикальная синхронизация', 'Ограничение частоты кадров', 'Счётчик кадров', 'Текстуры',
                      'Назад']
    tex = g.assets.tex('fac_brick_a')
    assert tex.getMagfilter() == SamplerState.FTNearest and tex.getAnisotropicDegree() == 16
    items = {it.label: it for it in m.items}
    items['Текстуры'].change(1)
    assert s.get('smooth_textures') is True and tex.getMagfilter() == SamplerState.FTLinear
    assert items['Текстуры'].value() == 'Сглаженные'
    items['Текстуры'].change(1)
    assert tex.getMagfilter() == SamplerState.FTNearest
    # счётчик кадров включается кнопкой (что он появляется на экране — ниже, когда меню закрыто)
    assert s.get('show_fps') is False and world.hud.fps_text.getText() == ''
    assert items['Счётчик кадров'].value() == 'Нет'
    items['Счётчик кадров'].change(1)
    assert s.get('show_fps') is True and items['Счётчик кадров'].value() == 'Да'
    # режим экрана: без настоящего окна запрос к системе ничего не меняет, но и не роняет игру
    from game import settings as S
    keep = (s.get('screen'), s.get('width'), s.get('height'))
    try:
        g.desktop = lambda: (1920, 1080)                # «экран» для проверки
        s.set('screen', S.SCREEN_WINDOW)
        items['Режим экрана'].change(1)
        assert (s.get('screen'), s.get('width'), s.get('height')) == (S.SCREEN_BORDERLESS, 1920, 1080)
        assert 'как у экрана' in items['Разрешение'].value()
        items['Разрешение'].change(1)                   # во весь экран разрешение всегда родное
        assert (s.get('width'), s.get('height')) == (1920, 1080)
        items['Режим экрана'].change(1)
        assert (s.get('screen'), s.get('width'), s.get('height')) == (S.SCREEN_EXCLUSIVE, 1920, 1080)
        items['Разрешение'].change(-1)
        assert (s.get('width'), s.get('height')) == (1600, 900)
        items['Режим экрана'].change(1)
        assert (s.get('screen'), s.get('width'), s.get('height')) == (S.SCREEN_WINDOW, 1600, 900)
        for _ in range(40):
            g._window_steps()                           # отложенные шаги (место и размер окна, проверка)
        assert not g._win_todo
        g.desktop = lambda: (0, 0)                      # экран неизвестен: «во весь экран» недоступен
        items['Режим экрана'].change(1)
        assert s.get('screen') == S.SCREEN_WINDOW
    finally:
        del g.desktop
        s.set('screen', keep[0])
        s.set('width', keep[1])
        s.set('height', keep[2])
        g._win_todo = []
    for it in m.items:
        if it.value is not None:
            assert isinstance(it.value(), str)
    harness.press(g, 'escape')
    assert g.ui.stack[-1].title == 'Настройки'
    harness.press(g, 'escape')
    g.ui.close_all()
    g.resume()
    # счётчик кадров на экране: число и «FPS» в углу; выключили — пропал
    harness.run(g, 0.7)
    txt = world.hud.fps_text.getText()
    assert txt.endswith(' FPS') and txt.split()[0].isdigit()
    s.set('show_fps', False)
    harness.run(g, 0.1)
    assert world.hud.fps_text.getText() == ''


# ----------------------------------------------------------------------
# качество графики
# ----------------------------------------------------------------------
def _gfx_keep(s):
    from game import gfx as G
    keys = G.GFX_KEYS + ('gfx_preset', 'fps_limit')
    return dict((k, s.get(k)) for k in keys)


def _gfx_restore(g, keep):
    for k, v in keep.items():
        g.settings.set(k, v)
    g.gfx.apply()


def test_gfx_presets(game):
    """Наборы «Минимум / Среднее / Ультра» записывают готовые значения; правка руками — «Пользовательские»."""
    from game import gfx as G
    from game.settings import DEFAULTS, DRAW_DIST
    g = game
    s = g.settings
    keep = _gfx_keep(s)
    try:
        assert set(G.PRESETS) == {G.PRESET_MIN, G.PRESET_MED, G.PRESET_ULTRA}
        for p, vals in G.PRESETS.items():
            assert set(vals) == set(G.GFX_KEYS)                 # каждый набор задаёт каждую настройку
            for k, v in vals.items():
                assert type(v) is type(DEFAULTS[k]), k          # иначе настройка не переживёт сохранение
        # «Минимум» — совсем без шейдеров: для компьютеров, где их нет или они слишком медленные
        lo = G.PRESETS[G.PRESET_MIN]
        assert lo['gfx_shaders'] is False and lo['gfx_shadows'] == 0 and lo['msaa'] == 0 and lo['draw_distance'] == 0
        assert lo['gfx_aniso'] == 0
        # «Ультра» включает всё, «Среднее» — без дорогой обработки кадра
        hi, mid = G.PRESETS[G.PRESET_ULTRA], G.PRESETS[G.PRESET_MED]
        assert all(hi[k] for k in ('gfx_shaders', 'gfx_bloom', 'gfx_ssao', 'gfx_gloss', 'gfx_water'))
        assert hi['gfx_shadows'] == 3 and hi['gfx_lights'] == 2 and hi['draw_distance'] == 2
        assert mid['gfx_shaders'] and not mid['gfx_bloom'] and not mid['gfx_ssao'] and 0 < mid['gfx_shadows'] < 3
        # настройки по умолчанию — это «Среднее»
        assert DEFAULTS['gfx_preset'] == G.PRESET_MED
        assert all(DEFAULTS[k] == v for k, v in mid.items())
        for p in (G.PRESET_MIN, G.PRESET_MED, G.PRESET_ULTRA):
            G.set_preset(s, p)
            g.gfx.apply()
            assert s.get('gfx_preset') == p and G.detect_preset(s) == p
            assert all(s.get(k) == v for k, v in G.PRESETS[p].items())
            # дальность прорисовки и фильтрация текстур меняются сразу
            assert (g.world.sky.fog_start, g.world.sky.far) == DRAW_DIST[G.PRESETS[p]['draw_distance']]
            assert g.assets.tex('fac_brick_a').getAnisotropicDegree() == (2 if p == G.PRESET_MIN else 16)
            harness.run(g, 0.1)
        # «Пользовательские» ничего не трогают
        before = dict((k, s.get(k)) for k in G.GFX_KEYS)
        G.set_preset(s, G.PRESET_CUSTOM)
        assert s.get('gfx_preset') == G.PRESET_CUSTOM and all(s.get(k) == v for k, v in before.items())
        s.set('gfx_bloom', False)
        assert G.detect_preset(s) == G.PRESET_CUSTOM
        s.set('gfx_bloom', True)
        assert G.detect_preset(s) == G.PRESET_ULTRA
        # на экране 4K «Ультра» берёт FXAA вместо MSAA — и всё равно остаётся «Ультрой»
        G.set_preset(s, G.PRESET_ULTRA, (3840, 2160))
        assert s.get('msaa') == 1 and G.detect_preset(s) == G.PRESET_ULTRA
        G.set_preset(s, G.PRESET_ULTRA, (1920, 1080))
        assert s.get('msaa') == 4
    finally:
        _gfx_restore(g, keep)


def test_gfx_first_run_guess():
    """Первый запуск: набор — по видеокарте, ограничение кадров — по частоте монитора."""
    from game import gfx as G
    assert G.guess_preset('NVIDIA Corporation / GeForce RTX 3060/PCIe/SSE2') == G.PRESET_ULTRA
    assert G.guess_preset('NVIDIA / GeForce GTX 1050 Ti') == G.PRESET_ULTRA
    assert G.guess_preset('ATI / AMD Radeon RX 6600 XT') == G.PRESET_ULTRA
    assert G.guess_preset('Intel / Intel(R) UHD Graphics 620') == G.PRESET_MED
    assert G.guess_preset('NVIDIA / GeForce GT 710') == G.PRESET_MED
    assert G.guess_preset('ATI / AMD Radeon(TM) RX Vega 11 Graphics') == G.PRESET_MED      # встроенная
    assert G.guess_preset('Mesa/X.org / llvmpipe (LLVM 10.0.0, 256 bits)') == G.PRESET_MIN
    assert G.guess_preset('Microsoft / GDI Generic') == G.PRESET_MIN
    assert G.guess_preset('NVIDIA / GeForce RTX 4090', supported=False) == G.PRESET_MIN
    assert G.FPS_LIMITS == (60, 120, 180, 240)
    assert [G.guess_fps_limit(h) for h in (60, 59, 75, 144, 165, 240, 360)] == [60, 60, 120, 180, 180, 240, 240]


def test_gfx_autotune_steps_down(game, world):
    """Первый запуск: набор качества выбран по названию видеокарты, а потом проверяется замером кадров.
    Мало кадров — набор понижается на ступень, и так до «Минимума»; хватает — остаётся как есть."""
    from game import gfx as G
    g = game
    s = g.settings
    gf = g.gfx
    from game.settings import TRAFFIC_LEVELS
    keep = _gfx_keep(s)
    keep['gfx_cfg'] = s.get('gfx_cfg')
    keep['traffic'] = s.get('traffic')
    assert keep['traffic'] == 1
    clock0 = gf._clock
    now = [100.0]
    gf._clock = lambda: now[0]

    def play(fps, seconds):
        """Столько секунд игра идёт с такой частотой кадров."""
        for _ in range(int(seconds * fps)):
            now[0] += 1.0 / fps
            gf.update(1.0 / fps)

    def begin(preset):
        G.set_preset(s, preset)
        s.set('gfx_cfg', 1)
        gf.apply()
        gf._tune = dict(skip=G.TUNE_SKIP, t=0.0, n=0, last=None, slow=0)

    try:
        # 60 кадров в секунду: «Ультра» остаётся, замер окончен
        begin(G.PRESET_ULTRA)
        play(60, G.TUNE_SKIP + G.TUNE_TIME + 0.5)
        assert gf._tune is None and s.get('gfx_preset') == G.PRESET_ULTRA and s.get('gfx_cfg') == 2
        # 35 кадров: для «Ультры» мало (нужно 45), для «Среднего» достаточно
        begin(G.PRESET_ULTRA)
        play(35, G.TUNE_SKIP + G.TUNE_TIME + 0.5)
        assert s.get('gfx_preset') == G.PRESET_MED and gf._tune is not None
        assert G.detect_preset(s) == G.PRESET_MED and 'понижено' in world.hud.help_text.getText()
        play(35, G.TUNE_SKIP + G.TUNE_TIME + 0.5)
        assert gf._tune is None and s.get('gfx_preset') == G.PRESET_MED and s.get('gfx_cfg') == 2
        # 15 кадров: вниз до «Минимума», то есть до рисования без шейдеров…
        begin(G.PRESET_ULTRA)
        play(15, 2 * (G.TUNE_SKIP + G.TUNE_TIME) + 1.0)
        assert gf._tune is not None and s.get('gfx_preset') == G.PRESET_MIN and s.get('gfx_shaders') is False
        assert gf.active is False and s.get('traffic') == 1
        # …а раз кадров мало и там, убавляется движение на улицах: его считает процессор
        play(15, G.TUNE_SKIP + G.TUNE_TIME + 1.0)
        assert gf._tune is None and s.get('traffic') == 0 and s.get('gfx_preset') == G.PRESET_MIN
        assert (world.traffic.max_cars, world.crowd.max_peds) == TRAFFIC_LEVELS[0]
        assert 'прохожих' in world.hud.help_text.getText()
        s.set('traffic', 1)
        g.apply_traffic()
        assert (world.traffic.max_cars, world.crowd.max_peds) == TRAFFIC_LEVELS[1]
        # подгрузка (один долгий кадр) замер не портит: он просто начинается заново
        begin(G.PRESET_MED)
        play(60, G.TUNE_SKIP + 2.0)
        now[0] += 1.5
        gf.update(0.1)
        play(60, 3.0)
        assert gf._tune is not None and s.get('gfx_preset') == G.PRESET_MED         # ещё считает
        play(60, G.TUNE_TIME)
        assert gf._tune is None and s.get('gfx_preset') == G.PRESET_MED
        # игра еле идёт (кадр в секунду): конца замера не ждём
        begin(G.PRESET_MED)
        play(1, 6.0)
        assert s.get('gfx_preset') == G.PRESET_MIN
        # на паузе кадры не считаются
        begin(G.PRESET_MED)
        g.pause()
        play(10, 20.0)
        assert s.get('gfx_preset') == G.PRESET_MED and gf._tune is not None
        g.resume()
        # игрок сам поменял настройку — подбор отменяется и больше не включится
        gf.apply(user=True)
        assert gf._tune is None and s.get('gfx_cfg') == 2
        play(10, 20.0)
        assert s.get('gfx_preset') == G.PRESET_MED
    finally:
        gf._clock = clock0
        gf._tune = None
        g.ui.close_all()
        if g.state == 'pause':
            g.resume()
        _gfx_restore(g, keep)
        g.apply_traffic()


def test_gfx_details_menu(game, world):
    """«Подробные настройки»: каждая настройка качества меняется отдельно, набор становится «Пользовательские»."""
    from game import gfx as G
    g = game
    s = g.settings
    keep = _gfx_keep(s)
    g.pause()
    try:
        g.ui.open(g.settings_menu())
        harness.press(g, 'enter')                               # «Графика и экран»
        m = g.ui.stack[-1]
        items = {it.label: it for it in m.items}
        G.set_preset(s, G.PRESET_MED)
        g.gfx.apply()
        assert items['Качество графики'].value() == 'Среднее'
        # стрелки перебирают наборы по кругу; подпись под заголовком объясняет выбранный
        seen = []
        for _ in range(4):
            items['Качество графики'].change(1)
            seen.append(items['Качество графики'].value())
            assert g.ui.stack[-1].text and isinstance(g.ui.stack[-1].text, str)
        assert seen == ['Ультра', 'Пользовательские', 'Минимум', 'Среднее']
        items['Качество графики'].change(-1)
        assert s.get('gfx_preset') == G.PRESET_MIN and s.get('gfx_shaders') is False
        items['Качество графики'].change(1)
        assert s.get('gfx_preset') == G.PRESET_MED and s.get('gfx_shaders') is True
        # ограничение частоты кадров: 60 / 120 / 180 / 240
        s.set('fps_limit', 60)
        got = []
        for _ in range(4):
            items['Ограничение частоты кадров'].change(1)
            got.append(int(s.get('fps_limit')))
        assert got == [120, 180, 240, 60]
        assert '60' in items['Ограничение частоты кадров'].value()
        items['Ограничение частоты кадров'].change(-1)
        assert s.get('fps_limit') == 240
        # подробные настройки
        m.sel = [it.label for it in m.items].index('Подробные настройки')
        harness.press(g, 'enter')
        d = g.ui.stack[-1]
        assert d.title == 'Подробные настройки'
        labels = [it.label for it in d.items]
        assert labels == ['Шейдеры: свет в каждой точке', 'Тени от солнца', 'Свет фонарей и фар',
                          'Блеск машин, мокрый асфальт', 'Вода с рябью и бликами', 'Свечение ярких мест',
                          'Затенение в углах', 'Сглаживание краёв', 'Чёткость текстур вдали',
                          'Дальность прорисовки', 'Назад']
        di = {it.label: it for it in d.items}
        for it in d.items:
            if it.value is not None:
                assert isinstance(it.value(), str) and it.value()
        di['Тени от солнца'].change(1)
        assert s.get('gfx_shadows') == 3 and s.get('gfx_preset') == G.PRESET_CUSTOM
        di['Тени от солнца'].change(-1)
        assert s.get('gfx_shadows') == 2 and s.get('gfx_preset') == G.PRESET_MED       # снова как в наборе
        di['Свечение ярких мест'].change(1)
        assert s.get('gfx_bloom') is True and s.get('gfx_preset') == G.PRESET_CUSTOM
        aa = []
        for _ in range(5):
            di['Сглаживание краёв'].change(1)
            aa.append(int(s.get('msaa')))
        assert aa == [2, 4, 8, 0, 1]
        s.set('msaa', 1)
        assert di['Сглаживание краёв'].value().startswith('FXAA')
        s.set('msaa', 4)
        assert di['Сглаживание краёв'].value().startswith('MSAA 4×')
        di['Дальность прорисовки'].change(1)
        assert s.get('draw_distance') == 2 and di['Дальность прорисовки'].value() == 'Далеко'
        assert world.sky.far == 940.0
        # чёткость текстур вдали (анизотропная фильтрация) меняется сразу, у уже загруженных текстур
        tex = g.assets.tex('fac_brick_a')
        assert di['Чёткость текстур вдали'].value() == 'Высокая' and tex.getAnisotropicDegree() == 16
        di['Чёткость текстур вдали'].change(-1)
        assert s.get('gfx_aniso') == 1 and tex.getAnisotropicDegree() == 8
        di['Чёткость текстур вдали'].change(-1)
        assert di['Чёткость текстур вдали'].value() == 'Низкая' and tex.getAnisotropicDegree() == 2
        di['Чёткость текстур вдали'].change(-1)
        assert s.get('gfx_aniso') == 2 and tex.getAnisotropicDegree() == 16
        if not g.gfx.supported:
            # видеокарта без шейдеров (так идут и эти проверки): меню честно говорит, что настройка не работает
            assert di['Тени от солнца'].value() == 'недоступно'
            assert di['Шейдеры: свет в каждой точке'].value() == 'недоступны'
            assert 'не умеет шейдеры' in d.text
        harness.press(g, 'escape')
        assert g.ui.stack[-1].title == 'Графика'
        assert g.ui.stack[-1].text == G.PRESET_HINTS[G.PRESET_CUSTOM] or not g.gfx.supported
        assert items['Качество графики'].value() == 'Пользовательские'
    finally:
        g.ui.close_all()
        g.resume()
        _gfx_restore(g, keep)


def test_gfx_fps_limit_applies(game):
    """Ограничение кадров и правда держит частоту: часы движка не дают кадрам идти чаще заданного."""
    import time
    from panda3d.core import ClockObject
    g = game
    s = g.settings
    clock = ClockObject.getGlobalClock()
    mode0, keep = clock.getMode(), s.get('fps_limit')
    g.gfx.apply_fps_limit()
    assert clock.getMode() == mode0                             # проверки идут без окна: кадры не тормозим
    g.headless = False
    try:
        for n in (60, 120, 180, 240):
            s.set('fps_limit', n)
            g.gfx.apply_fps_limit()
            assert clock.getMode() == ClockObject.MLimited and g.gfx.fps_applied == n
            clock.tick()
            t0 = time.perf_counter()
            frames = max(6, n // 10)
            for _ in range(frames):
                clock.tick()                                    # «кадр» без работы: быстрее заданного не выйдет
            took = time.perf_counter() - t0
            assert 0.8 * frames / n < took < 3.0 * frames / n + 0.05, (n, took)
        s.set('fps_limit', 77)                                  # мусор в файле настроек: берём 60
        g.gfx.apply_fps_limit()
        assert g.gfx.fps_applied == 60
    finally:
        g.headless = True
        clock.setMode(mode0)
        s.set('fps_limit', keep)


def test_gfx_without_shaders_is_safe(game, world):
    """Нет шейдеров (старая видеокарта, запасной рендерер) — любой набор качества рисует по-старому."""
    from game import gfx as G
    g = game
    if g.gfx.supported:
        pytest.skip('эта проверка — для рендерера без шейдеров')
    s = g.settings
    keep = _gfx_keep(s)
    try:
        for p in (G.PRESET_ULTRA, G.PRESET_MED, G.PRESET_MIN):
            G.set_preset(s, p)
            g.gfx.apply()
            assert g.gfx.active is False and g.gfx.cfg['on'] is False and not g.gfx.cascades and not g.gfx.post
            assert g.base.render.getShader() is None
            harness.run(g, 0.2)
        assert g.gfx.failed is False                            # «не умеет» — не то же, что «сломалось»
    finally:
        _gfx_restore(g, keep)


def test_shader_sources():
    """Тексты шейдеров: только латиница (комментарии вырезаны), директивы парные, все варианты собираются в текст."""
    import re
    from game import shaders as S
    from game import gfx as G
    combos = []
    for lv in G.SHADOW_LEVELS:
        for lights in G.LIGHT_COUNTS:
            for gloss in (0, 1):
                for hdr in (0, 1):
                    combos.append(dict(SHADOWS=1 if lv else 0, CASCADES=2 if (lv and lv['far']) else 1,
                                       PCF=lv['pcf'] if lv else 1, LIGHTS=lights, GLOSS=gloss, HDR=hdr))
    texts = []
    for c in combos:
        texts += [S.source(S.SCENE_VERT, **c), S.source(S.SCENE_FRAG, **c)]
    texts += [S.source(t) for t in (S.SHADOW_VERT, S.SHADOW_FRAG, S.POST_VERT, S.BRIGHT_FRAG, S.BLUR_FRAG,
                                    S.AOBLUR_FRAG, S.FXAA_FRAG)]
    texts += [S.source(S.WATER_VERT, HDR=h) for h in (0, 1)] + [S.source(S.WATER_FRAG, HDR=h) for h in (0, 1)]
    texts += [S.source(S.SSAO_FRAG, SSAO_TAPS=12)]
    texts += [S.source(S.COMPOSITE_FRAG, BLOOM=b, SSAO=a) for b in (0, 1) for a in (0, 1)]
    for t in texts:
        assert t.startswith('#version 120\n')
        assert all(ord(ch) < 128 for ch in t)                   # строгий драйвер не примет кириллицу
        assert '//' not in t
        assert len(re.findall(r'^#if', t, re.M)) == len(re.findall(r'^#endif', t, re.M))
        assert t.count('{') == t.count('}') and t.count('(') == t.count(')')
        assert 'void main()' in t
    # всё, что шейдер сцены ждёт от игры, игра ему передаёт (иначе — чёрный экран на настоящей видеокарте)
    import inspect
    src = inspect.getsource(G)
    full = S.SCENE_VERT + S.SCENE_FRAG + S.WATER_FRAG
    for name in sorted(set(re.findall(r'uniform\s+\w+\s+(u_\w+)', full))):
        assert name in src, name


@pytest.mark.skipif(os.environ.get('DD_TEST_DISPLAY') != 'p3headlessgl', reason='нужен OpenGL (DD_TEST_DISPLAY=p3headlessgl)')
def test_gfx_shaders_compile_and_draw(game, world):
    """С настоящим OpenGL: каждый набор качества собирает свои шейдеры без ошибок и рисует не чёрный кадр."""
    from panda3d.core import PNMImage
    from game import gfx as G
    g = game
    assert g.gfx.supported
    s = g.settings
    keep = _gfx_keep(s)
    w = world
    hour, wth = w.sky.hour, w.sky.weather
    try:
        w.sky.set_weather('clear')
        w.sky.set_time(13.0)
        seen = {}
        for p in (G.PRESET_MIN, G.PRESET_MED, G.PRESET_ULTRA):
            G.set_preset(s, p)
            g.gfx.apply()
            harness.run(g, 0.3)
            for _ in range(2):
                g.base.graphicsEngine.renderFrame()
            harness.run(g, 0.3)                                 # здесь игра сама проверяет, собрались ли шейдеры
            assert g.gfx.failed is False
            assert g.gfx.active is (p != G.PRESET_MIN)
            assert not [sh for sh in g.gfx._shaders if sh.getErrorFlag()]
            if p == G.PRESET_ULTRA:
                c = g.gfx.cfg
                assert c['shadows'] == 3 and len(g.gfx.cascades) == 2 and c['bloom'] and c['ssao'] and c['post']
            img = PNMImage()
            g.base.win.getScreenshot(img)
            n = 0
            tot = 0.0
            for x in range(8, img.getXSize(), 37):
                for y in range(8, img.getYSize(), 29):
                    tot += img.getBright(x, y)
                    n += 1
            seen[p] = tot / n
        # день, ясно: кадр не чёрный и не выбеленный ни в одном наборе, и наборы не расходятся по яркости вдвое
        assert all(0.15 < v < 0.9 for v in seen.values()), seen
        assert max(seen.values()) < 2.0 * min(seen.values()), seen
    finally:
        w.sky.set_weather(wth)
        w.sky.set_time(hour)
        _gfx_restore(g, keep)


# ----------------------------------------------------------------------
# пролог
# ----------------------------------------------------------------------
def _after_intro(g, w, errors):
    """После пролога (досмотренного или пропущенного) игра в рабочем состоянии: герой стоит на остановке,
    управление у игрока, и ему звонит брат.  От погони в городе ничего не осталось."""
    ms = w.missions
    pl = w.player
    assert ms.intro is None and g.state == 'play' and not g.ui.active
    assert w.interiors.current is None
    sx, sy, syaw = w.city.start_pos
    hx, hy = w.city.off(sx, sy, -11.5, -1.3)                     # у остановки (улица изогнута: сдвиг по чертежу)
    assert math.hypot(pl.ped.x - hx, pl.ped.y - hy) < 3.0
    assert not w.city.in_north(*pl.pos()) and w.hud.map_name == 'map'      # Зимогорск остался в прошлом
    assert w.sky.snow == 0.0
    assert not pl.freeze and pl.script_move is None and not pl.invincible
    assert not pl.ped.node.isHidden() and abs(pl.ped.z - w.city.ground_z(*pl.pos())) < 0.05
    assert w.hud.visible and w.cam.override is None and ms.letter.isHidden()
    assert w.traffic.enabled and w.sky.time_scale == 1.0 and w.scene_engine is None
    assert not w.interiors.cinema
    assert not any(v.scripted for v in w.vehicles)
    assert ms.markers and all(not mk.np.isHidden() for mk in ms.markers)
    assert abs(w.sky.hour - 8.0) < 0.3 and w.sky.weather == 'clear'
    assert g._errors_total == errors
    # розыска нет, из машины снова можно выйти, сигнализация молчит
    pol = w.police
    assert pol.level == 0 and pol.locked is None and not pl.lock_in
    assert not [u for u in pol.units if not u.removed] and not [q for q in w.peds if q.target is pl.ped]
    assert pl.vehicle is None and pl.state == 'foot' and w.respawn_kind is None
    alarm = g.audio.loops.get('alarm')
    assert alarm is None or not alarm[2]
    # «Ласточка» в городе одна — та, что ждёт в гараже у дома; машина ограбления осталась в прошлом
    retro = [v for v in w.vehicles if v.kind == 'retro']
    assert retro == [w.hero_car.v] and retro[0] in w.garage.cars
    assert not retro[0].immune and retro[0].driver is None and retro[0].rescue is None
    # пролог в статистику не идёт, денег и оружия он не оставляет
    assert not [k for k, val in w.stats.items() if val and k != 'play_time'], w.stats
    assert w.stats['play_time'] < 3.0 and pl.money == 0 and pl.weapon.id == W_FIST
    # управление вернулось: герой идёт
    x0, y0 = pl.pos()
    w.cam.yaw = math.pi
    harness.run(g, 0.8, keys=('w',))
    x1, y1 = pl.pos()
    assert math.hypot(x1 - x0, y1 - y0) > 1.0
    # ...и тут же звонит Брюс: первое задание началось
    harness.run(g, 4.0)
    assert ms.active is not None and ms.active.spec['id'] == 's1'
    assert w.hud.phone_on


def test_enter_in_a_phone_call_only_turns_lines(game):
    """Пока идёт телефонный разговор, Enter листает реплики, а не сажает героя в машину, что стоит рядом
    (иначе он угонял бы чужую машину посреди звонка); клавиша F дверцу открывает и в это время."""
    g = game
    w = harness.start_game(g, story=True)
    ms, pl = w.missions, w.player
    harness.quiet(w, peds=True)
    t = 0.0
    while not w.hud.phone_on and t < 15.0:
        harness.run(g, 0.2)
        t += 0.2
    assert w.hud.phone_on and ms.active is not None and pl.state == 'foot' and pl.controls
    x, y = pl.pos()
    car = w.spawn_vehicle('sedan', *harness.side(x, y, pl.ped.yaw, right=2.4), pl.ped.yaw)
    harness.run(g, 0.2)
    lines = set()
    n = 0
    while w.hud.phone_on and n < 40:
        harness.run(g, 0.45)
        lines.add(w.hud.sub_plain)
        harness.press(g, 'enter')
        harness.run(g, 0.1)
        n += 1
        assert pl.vehicle is None and pl.state == 'foot', n          # герой так и стоит на улице
    assert not w.hud.phone_on and len(lines) >= 3 and n < 30         # Enter листал реплики: разговор кончился быстро
    assert ms.active is not None and pl.controls
    # разговор окончен — Enter снова «сесть в машину»
    harness.run(g, 1.0)
    harness.press(g, 'enter')
    harness.run(g, 2.5)
    assert pl.vehicle is car and pl.state == 'car'
    # и новый звонок, пока герой за рулём: Enter не высаживает его, F — высаживает
    w.hud.phone_on = True
    harness.press(g, 'enter')
    harness.run(g, 1.5)
    assert pl.vehicle is car
    harness.press(g, 'f')
    harness.run(g, 2.5)
    assert pl.vehicle is None
    w.hud.phone_on = False


def _to_chase(g):
    """Пролистать сценку у банка (Enter — следующий кадр) до погони.  Возвращает число нажатий."""
    ms = g.world.missions
    n = 0
    while ms.intro is not None and not ms.intro['play'] and n < 20:
        harness.run(g, 0.4)
        harness.press(g, 'enter')
        n += 1
    assert ms.intro is not None and ms.intro['play'], n
    return n


def _watch_intro(g, limit, each=None):
    """Досмотреть пролог без нажатий.  Возвращает реплики, крупные надписи и прошедшее время."""
    w = g.world
    ms = w.missions
    lines, bigs = [], []
    t = 0.0
    while ms.intro is not None and t < limit:
        g.step(DT)
        t += DT
        text = w.hud.sub_plain
        if text and (not lines or lines[-1] != text):
            lines.append(text)
        if w.hud.big_t > 0.0:
            big = w.hud.big_text.getText()
            if not bigs or bigs[-1] != big:
                bigs.append(big)
        if each is not None and ms.intro is not None:
            each(ms.intro)
    return lines, bigs, t


def test_intro_plays_to_the_end(game):
    """Пролог без единого нажатия: банк, сигнализация, погоня (герой стоит на месте — его берут или выходит
    время), арест, «Три года спустя», автобус, остановка — и игра начинается звонком брата."""
    g = game
    random.seed(7)
    errors = g._errors_total
    g.new_game()
    w = g.world
    ms = w.missions
    pl = w.player
    assert ms.intro is not None and pl.freeze
    seen = dict(car=False, crew=False, alarm=False, chase=False, cops=False, bus=False, hidden=False, walked=False,
                room=False, paused=False)
    ends = set()

    def each(it):
        car = it['car']
        if it['play']:
            seen['chase'] = True
            seen['cops'] |= len(w.police.units) >= 2            # погоня настоящая: патрульные машины рядом
            assert w.hud.visible and w.traffic.enabled and w.police.level == 3
            if w.respawn_kind is None and it['end'] is None:
                assert not pl.freeze and pl.lock_in and pl.vehicle is car
        else:
            assert pl.freeze and not pl.lock_in
            if it['end'] is None:
                assert not w.hud.visible            # (сразу после погони HUD гаснет вместе с экраном)
        ends.add(it['end'])
        seen['car'] |= car is not None and pl.vehicle is car and car.kind == 'retro'
        seen['crew'] |= car is not None and [q.vehicle for q in it['peds']] == [car, car]
        alarm = g.audio.loops.get('alarm')
        seen['alarm'] |= bool(alarm and alarm[2])
        seen['bus'] |= it['bus'] is not None and abs(it['bus'].speed) > 5.0
        seen['hidden'] |= pl.ped.node.isHidden()
        seen['walked'] |= pl.script_move is not None and pl.ped.speed > 0.5
        seen['room'] |= w.interiors.current is not None
        seen['paused'] |= g.state != 'play'
        assert pl.ped.health == 100

    lines, bigs, t = _watch_intro(g, 260.0, each)
    assert 50.0 < t < 240.0, t
    assert lines[0].startswith('Зимогорск') and any('Сигнализация' in s_ for s_ in lines)
    assert any(s_.startswith('Седой: Гони') for s_ in lines) and any(s_.startswith('Уходи от погони') for s_ in lines)
    assert any(s_.startswith('Водитель:') for s_ in lines) and any('брат' in s_ for s_ in lines)
    assert not any('Вано' in s_ for s_ in lines)                 # старого сюжета в прологе нет
    assert ends - {None} <= {'busted', 'time'} and len(ends) == 2, ends
    assert 'АРЕСТОВАН' in bigs and bigs[-1] == 'ТРИ ГОДА СПУСТЯ', bigs
    assert seen == dict(car=True, crew=True, alarm=True, chase=True, cops=True, bus=True, hidden=True, walked=True,
                        room=False, paused=False), seen
    _after_intro(g, w, errors)


def test_intro_chase_to_the_tract(game):
    """Погоня пролога: машину ведёт игрок, выйти из неё нельзя, розыск не спадает, машине ничего не делается.
    Дело происходит в Зимогорске — отдельном заснеженном городке; на тракте за ним ждёт заслон: три
    патрульные машины поперёк дороги и полицейские с пистолетами."""
    g = game
    random.seed(23)
    errors = g._errors_total
    g.new_game()
    w = g.world
    ms = w.missions
    pl = w.player
    _to_chase(g)
    it = ms.intro
    car = it['car']
    mk = it['marker']
    assert car.kind == 'retro' and car.immune and pl.vehicle is car and pl.lock_in and not pl.freeze
    assert [q.vehicle for q in it['peds']] == [car, car]            # Седой и Клык уже в машине
    who = car.cabin['who']                                          # …и их видно за стеклом, как и Макса
    assert who[pl.ped] == 0 and sorted(who[q] for q in it['peds']) == [1, 2]
    assert not any(q.node.isHidden() for q in it['peds'] + [pl.ped])
    assert w.police.level == 3 and w.police.locked == 3 and w.hud.visible
    c = w.city
    # другой город: далеко от Порт-Глухова, под снегом, со своей картой на радаре
    assert c.in_north(car.x, car.y) and c.zone_name(car.x, car.y).startswith('Зимогорск')
    assert w.sky.weather == 'snow' and w.sky.snow > 0.9 and not w.sky.snow_np.isHidden()
    assert w.hud.map_name == 'map_north'
    assert c.street_name(car.x, car.y) == 'проспект Первопроходцев'
    lx, ly = c.landmarks['heist']['door']
    assert 6.0 < math.hypot(car.x - lx, car.y - ly) < 22.0 and c.on_road(car.x, car.y)     # напротив банка
    assert mk in ms.markers and it['blip'] in w.hud.blips
    gx, gy = c.special['intro']['goal']
    assert math.hypot(mk.x - gx, mk.y - gy) < 0.1 and c.on_road(mk.x, mk.y) and c.in_north(mk.x, mk.y)
    assert c.zone_name(mk.x, mk.y) == 'Зимогорский тракт' and math.hypot(mk.x - car.x, mk.y - car.y) > 500.0
    # машина слушается газа
    x0, y0 = car.x, car.y
    harness.run(g, 3.0, keys=('w',))
    assert math.hypot(car.x - x0, car.y - y0) > 8.0
    # выйти нельзя, машину не разбить, розыск сам не спадает
    harness.press(g, 'f')
    harness.run(g, 1.0)
    assert pl.vehicle is car and pl.state == 'car'
    w.police.cool_t = 1000.0
    harness.run(g, 0.3)
    assert w.police.level == 3
    hp = car.health
    car.damage(5000.0, cause='explosion')
    assert car.health == hp and not car.dead
    # Enter, пробел и мышь здесь — управление машиной, а не «следующий кадр»
    for key in ('enter', 'space', 'mouse1'):
        harness.press(g, key)
        harness.run(g, 0.3)
    assert ms.intro is it and it['play'] and it['end'] is None
    # подъезжаем к метке на тракте (с юга: тракт там идёт на север)
    car.x, car.y, car.yaw = c.frame(mk.x, mk.y).at(0.0, -26.0, math.pi / 2)
    car.vx = car.vy = car.speed = car.omega = 0.0
    car.sync()
    t = 0.0
    while it['end'] is None and t < 8.0:
        harness.run(g, 0.2, keys=('w',))
        t += 0.2
    assert it['end'] == 'tract', (t, car.x, car.y, mk.x, mk.y)
    harness.run(g, 1.5)
    # заслон: погоня кончилась, декорации расставлены
    assert not it['play'] and pl.freeze and not pl.lock_in and not w.hud.visible
    assert w.police.level == 0 and w.police.locked is None and it['marker'] is None and mk not in ms.markers
    block = it['cars']
    assert len(block) == 3 and all(u.kind == 'police' and u.siren and u.keep for u in block)
    cops = [q for q in it['peds'] if q.kind == 'cop']
    assert len(cops) == 4 and all(q.aiming and q.weapon.id == W_PISTOL and q.vehicle is None for q in cops)
    B = c.frame(*c.special['intro']['block'])                       # вдоль тракта: «север» чертежа
    along = lambda o: B.local(o.x, o.y)[1]
    assert pl.vehicle is car and abs(car.speed) < 0.1 and all(along(u) > along(car) + 12.0 for u in block)
    assert all(along(car) < along(q) < min(along(u) for u in block) for q in cops)      # полицейские — перед машинами
    assert all(c.on_road(u.x, u.y) and c.in_north(u.x, u.y) and abs(along(u)) < 3.0 for u in block)
    assert c.on_road(car.x, car.y) and abs(car.z - c.ground_z(car.x, car.y)) < 0.05
    assert w.hud.sub_plain.startswith('Тракт перекрыли')
    lines, bigs, t = _watch_intro(g, 80.0)
    assert bigs == ['АРЕСТОВАН', 'ТРИ ГОДА СПУСТЯ'], bigs
    assert any(s_.startswith('Водитель:') for s_ in lines)
    assert all(u.removed for u in block) and all(q.removed for q in cops) and car.removed
    _after_intro(g, w, errors)


def test_intro_arrest_in_the_chase(game):
    """Арест в погоне пролога — часть сюжета: героя не везут в участок и не штрафуют, пролог идёт дальше
    (уже без заслона на тракте)."""
    g = game
    random.seed(29)
    errors = g._errors_total
    g.new_game()
    w = g.world
    ms = w.missions
    pl = w.player
    _to_chase(g)
    it = ms.intro
    harness.run(g, 2.0, keys=('w',))
    w.on_player_busted()
    assert w.respawn_kind == 'busted' and it['play']
    t = 0.0
    while w.respawn_kind is not None and t < 8.0:
        harness.run(g, 0.2)
        t += 0.2
    assert w.respawn_kind is None and it['end'] == 'busted'
    harness.run(g, 0.5)
    assert ms.intro is it and not it['play'] and pl.freeze and pl.invincible
    assert w.police.level == 0 and not it['cars']
    assert w.hud.sub_plain.startswith('Далеко мы не ушли')
    px, py = pl.pos()
    lx, ly = w.city.landmarks['police']['door']
    assert math.hypot(px - lx, py - ly) > 30.0                      # не у участка
    lines, bigs, t = _watch_intro(g, 80.0)
    assert bigs[-1] == 'ТРИ ГОДА СПУСТЯ' and any(s_.startswith('Водитель:') for s_ in lines)
    assert not any('перекры' in s_ for s_ in lines)
    _after_intro(g, w, errors)


@pytest.mark.parametrize('when', [0.1, 3.0, 9.0, 14.0])
def test_intro_can_be_skipped_any_time(game, when):
    """Esc в любой момент сценки: декорации убраны, герой на остановке, пауза не открылась."""
    g = game
    random.seed(11)
    errors = g._errors_total
    g.new_game()
    w = g.world
    harness.run(g, when)
    assert w.missions.intro is not None and not w.missions.intro['play']
    harness.press(g, 'escape')
    harness.run(g, 0.3)
    _after_intro(g, w, errors)


@pytest.mark.parametrize('stage', ['chase', 'arrest', 'roadblock', 'bus'])
def test_intro_can_be_skipped_later(game, stage):
    """Пропуск после сценки у банка.  В погоне Esc — обычная пауза, и в ней есть «Пропустить пролог»
    (он срабатывает и на экране «АРЕСТОВАН», куда паузу приводит потеря фокуса окна); у заслона и в автобусе
    Esc снова пропускает сразу."""
    g = game
    random.seed(37)
    errors = g._errors_total
    g.new_game()
    w = g.world
    ms = w.missions
    _to_chase(g)
    it = ms.intro
    harness.run(g, 2.0, keys=('w',))
    if stage in ('chase', 'arrest'):
        if stage == 'arrest':
            w.on_player_busted()
            harness.run(g, 1.5)
            assert w.respawn_kind == 'busted'
            harness.press(g, 'escape')          # на экране ареста Esc паузу не открывает
            assert g.state == 'play'
            g.pause()
        else:
            harness.press(g, 'escape')
        assert g.state == 'pause' and ms.intro is it
        menu = g.ui.stack[-1]
        labels = [i_.label for i_ in menu.items]
        assert labels[:2] == ['Продолжить', 'Пропустить пролог']
        menu.items[1].action()
    else:
        it['end'] = 'tract'                     # как будто доехали до метки
        harness.run(g, 2.0)
        assert not it['play'] and len(it['cars']) == 3
        if stage == 'bus':
            t = 0.0
            while ms.intro is not None and it['bus'] is None and t < 40.0:
                harness.run(g, 0.2)
                t += 0.2
            assert it['bus'] is not None and not it['cars']
            harness.run(g, 1.0)
        harness.press(g, 'escape')
    harness.run(g, 0.3)
    assert g.state == 'play' and ms.intro is None
    _after_intro(g, w, errors)
    # в обычной игре пункта «Пропустить пролог» в паузе нет
    harness.press(g, 'escape')
    assert g.state == 'pause' and 'Пропустить пролог' not in [i_.label for i_ in g.ui.stack[-1].items]
    g.ui.close_all()
    g.resume()


def test_intro_enter_steps_through_shots(game):
    """Enter листает кадры пролога: несколько нажатий до погони и ещё несколько — после неё."""
    g = game
    random.seed(13)
    errors = g._errors_total
    g.new_game()
    w = g.world
    ms = w.missions
    n = _to_chase(g)
    assert 3 <= n <= 8, n
    ms.intro['end'] = 'tract'
    n = 0
    while ms.intro is not None and n < 30:
        harness.run(g, 0.5)
        harness.press(g, 'enter')
        n += 1
    assert 3 <= n < 16, n
    harness.run(g, 0.3)
    _after_intro(g, w, errors)


def test_first_call_and_hints(game):
    """После пролога звонит Брюс: его реплики, адрес дома и подсказка, как добыть машину."""
    g = game
    random.seed(17)
    g.new_game()
    w = g.world
    ms = w.missions
    said = []
    orig = w.hud.help
    w.hud.help = lambda text, dur=6.0: (said.append(text), orig(text, dur))[1]
    lines = []
    try:
        harness.run(g, 1.0)
        harness.press(g, 'escape')
        harness.quiet(w, peds=True)
        t = 0.0
        while t < 40.0 and not (ms.active is not None and ms.active.markers):
            g.step(DT)
            t += DT
            text = w.hud.sub_plain
            if text and (not lines or lines[-1] != text):
                lines.append(text)
        assert lines[0] == 'Брюс: Хей, братан, как приехал?'
        assert 'Макс: Да прекрасно добрался.' in lines and 'Брюс: Удачи.' in lines
        assert any('домик купил' in s_ and w.city.address('safehouse') in s_ for s_ in lines)
        assert ms.active.objective.startswith('Доберись до дома') and w.city.address('safehouse') in ms.active.objective
        assert not w.hud.phone_on                                # трубку положили
        assert any('F' in h for h in said)                       # как сесть в машину
    finally:
        w.hud.help = orig


@pytest.mark.parametrize('when', [6.0, 22.0])
def test_intro_interrupted_by_menu(game, when):
    """Пролог прервали (окно потеряло фокус → пауза → главное меню) — в сценке или посреди погони:
    мир не остаётся «выключенным», а розыск и запертая машина не переходят в следующую игру."""
    g = game
    random.seed(19)
    errors = g._errors_total
    g.new_game()
    w = g.world
    harness.run(g, when)
    it = w.missions.intro
    assert it is not None and it['play'] == (when > 18.0)
    assert w.traffic.enabled == it['play'] and w.player.lock_in == it['play']
    g.pause()                                   # так срабатывает потеря фокуса окна
    assert g.state == 'pause'
    g.to_main_menu()
    w = g.world
    assert w.traffic.enabled and w.sky.time_scale == 1.0 and w.scene_engine is None
    assert g.state == 'menu' and w.missions.intro is None and not w.interiors.cinema
    assert w.police.level == 0 and w.police.locked is None and not w.player.lock_in
    alarm = g.audio.loops.get('alarm')
    assert alarm is None or not alarm[2]
    harness.run(g, 1.0)
    assert not any(v.scripted or v.kind == 'retro' for v in w.vehicles)
    w = harness.start_game(g, street=False, story=True, hero=True)
    _after_intro(g, w, errors)


# ----------------------------------------------------------------------
# сюжет: цепочка заказчиков
# ----------------------------------------------------------------------
def test_story_and_jobs_structure():
    """Сюжет — задания Брюса и босса, они идут по порядку и начинаются звонком.  Остальное — подработка
    у заказчиков: она открывается после сюжета и проходима в любом порядке."""
    ids = [m['id'] for m in M.MISSIONS]
    assert len(ids) == len(set(ids)) == 20
    assert [m['id'] for m in M.STORY] == ['s1', 's2'] and M.STORY_TOTAL == 2 and M.STORY_IDS == {'s1', 's2'}
    assert all(m['contact'] is None and m.get('story') for m in M.STORY)
    assert M.STORY[0]['req'] == [] and M.STORY[1]['req'] == ['s1']
    assert [m['reward'] for m in M.STORY] == [5000, 10000]
    assert len(M.JOBS) == 18 and M.JOB_IDS == set(ids) - M.STORY_IDS
    assert set(m['contact'] for m in M.JOBS) == set(M.CONTACTS) and len(M.CONTACTS) == 5
    by_contact = {}
    for m in M.JOBS:
        prev = by_contact.get(m['contact'])
        if prev is not None:
            assert prev in m['req'], 'задания одного заказчика идут по порядку: %s' % m['id']
        by_contact[m['contact']] = m['id']
    assert set(M.ANNOUNCE) <= M.JOB_IDS
    first = [m['id'] for m in M.MISSIONS if not m['req']]
    assert first == ['s1']                                    # в начале игры одна дорога — звонок брата
    assert next(m for m in M.JOBS if m['id'] == 'v1')['req'] == ['s2']       # подработка — после сюжета

    def avail(done):
        return [m['id'] for m in M.MISSIONS if m['id'] not in done and all(r in done for r in m['req'])]
    # обход всех достижимых состояний: тупиков нет
    rnd = random.Random(5)
    for trial in range(300):
        done = set()
        while len(done) < 20:
            a = avail(done)
            assert a, 'тупик после %s' % sorted(done)
            done.add(rnd.choice(a))
    req = {m['id']: set(m['req']) for m in M.MISSIONS}
    assert req['z1'] == {'r1'} and 'z1' in req['g1'] and 'g1' in req['p1']


def test_story_announces_next_contact(game, world):
    """После задания игра подсказывает, кто открылся или у кого ещё есть работа."""
    w = world
    ms = w.missions
    said = []
    orig = w.hud.help
    w.hud.help = lambda text, dur=6.0: said.append(text)
    try:
        expect = {'v1': 'Розе', 'r1': 'Захар', 'r2': 'Грома', 'g1': 'Башня', 'g2': 'чайную', 'r4': 'Проф'}
        order = ['v1', 'r1', 'v2', 'z1', 'r2', 'g1', 'p1', 'z2', 'z3', 'g2', 'g3', 'p2', 'p3', 'v3', 'v4', 'r3',
                 'r4', 'p4']
        for mid in order:
            spec = next(m for m in M.MISSIONS if m['id'] == mid)
            assert ms.next_mission(spec['contact']) is spec, mid
            ms.done.add(mid)
            del said[:]
            ms._announce(mid)
            if mid in expect:
                assert said and expect[mid] in said[0], (mid, said)
            if said and said[0].startswith('Здесь пока всё'):
                # названы только те, у кого работа действительно есть
                for name, info in M.CONTACTS.items():
                    assert (info['title'] in said[0]) == (ms.next_mission(name) is not None and
                                                           name != spec['contact']), (mid, said[0])
        assert ms.progress() == (2, 2) and ms.jobs_progress() == (18, 18)
        assert not said                                      # после финала звать некуда
    finally:
        w.hud.help = orig


def test_zakhar_leaves_town_after_raid(game, world):
    """После «Облавы» Захара в сарае нет — и после загрузки сохранения тоже."""
    w = world
    ms = w.missions
    assert w.interiors.resident('zakhar') is not None
    ms.done |= {'v1', 'r1', 'z1', 'z2', 'z3', 'r2', 'g1', 'g2', 'g3'}
    ms.sync_story()
    assert w.interiors.resident('zakhar') is None
    assert ms.next_mission('zakhar') is None
    assert ms.save_game()
    w = harness.start_game(game)
    assert w.interiors.resident('zakhar') is not None        # новая игра — он снова на месте
    game.to_main_menu()
    game.continue_game()
    w = game.world
    assert isinstance(w.missions.done, set) and 'g3' in w.missions.done
    assert w.interiors.resident('zakhar') is None
    assert w.interiors.resident('grom') is not None


def test_mission_car_marker_follows_the_car(game, world):
    """Вышел из машины посреди задания — цель и метка ведут обратно к машине, сел — снова к точке."""
    w = world
    pl = w.player
    ms = w.missions
    harness.quiet(w, peds=True)
    spec = next(m for m in M.MISSIONS if m['id'] == 'g2')
    x, y = w.city.landmarks['grom']['door']
    pl.teleport(x, y - 2.0)
    assert ms.start(spec)
    bot = Bot(game, verbose=False)
    m = ms.active
    for _ in range(900):
        if pl.vehicle is not None and m.markers:
            break
        bot.step(DT)
        game.step(DT)
    for k in ('w', 's', 'a', 'd', 'space', 'f', 'enter'):
        game.inp._up(k)
    car = pl.vehicle
    assert car is not None and car is m.vehicles[0] and 'точка 1' in m.objective and len(m.markers) == 1
    car.vx = car.vy = 0.0
    car.speed = 0.0
    pl.leave_vehicle(force=True)
    harness.run(game, 0.5)
    assert 'Вернись' in m.objective and not m.markers          # метки точки нет, есть стрелка над машиной
    assert any(a.obj is car for a in m.arrows)
    dx, dy = car.door_pos(-1)
    pl.ped.x, pl.ped.y = dx - 0.4, dy                           # к водительской двери — и F
    harness.run(game, 0.2)
    harness.press(game, 'f')
    harness.run(game, 2.5)
    assert pl.vehicle is car
    harness.run(game, 0.4)
    assert 'точка 1' in m.objective and len(m.markers) == 1
    assert not any(a.obj is car for a in m.arrows)


def test_crate_is_loaded_by_hand(game, world):
    """Ящик-груз берут только пешком: из машины он не подбирается."""
    w = world
    pl = w.player
    ms = w.missions
    harness.quiet(w, peds=True)
    x, y = pl.pos()
    pk = ms.add_pickup('crate', x + 12.0, y - 6.0)
    harness.run(game, 0.3)
    assert not pk.removed and pk.kind == 'crate'
    v = w.spawn_vehicle('pickup', pk.x, pk.y, 0.0)
    pl.ped.x, pl.ped.y = v.door_pos(-1)
    pl.enter_vehicle(v, silent=True)
    harness.run(game, 0.5)
    assert pl.vehicle is v and not pk.removed                 # за рулём ящик не взять, хоть он и под колёсами
    pl.leave_vehicle(force=True)
    pl.teleport(pk.x + 0.3, pk.y)
    harness.run(game, 0.3)
    assert pk.removed


# ----------------------------------------------------------------------
# помещения
# ----------------------------------------------------------------------
def test_every_door_leads_in_and_back_out(game, world):
    """В каждое помещение входят пешком через дверь со стрелкой и выходят обратно к той же двери."""
    w = world
    pl = w.player
    its = w.interiors
    harness.quiet(w, peds=True)
    assert [r.name for r in its.order] == ['safehouse', 'vano', 'rosa', 'prof', 'guns', 'guns2', 'police',
                                           'hospital', 'bank', 'zakhar', 'grom', 'boss']
    for r in its.order:
        x, y = r.out
        pl.teleport(x, y - 3.0, math.pi / 2)
        w.cam.yaw = math.pi / 2
        harness.run(game, 0.3)
        assert its.current is None and not pl.indoors
        assert not r.arrow.np.isHidden()                       # жёлтая стрелка над дверью
        t = 0.0
        while its.current is not r and t < 5.0:
            harness.run(game, 0.1, keys=('w',))
            t += 0.1
        assert its.current is r, r.name
        harness.run(game, 0.8)
        assert pl.indoors and not pl.freeze and w.citymesh.root.isHidden() and not r.node.isHidden()
        px, py = pl.pos()
        assert r.ox < px < r.ox + r.w and r.oy < py < r.oy + r.d, r.name
        assert w.map_pos() == (r.out[0], r.out[1])             # на карте герой — у двери этого дома
        people = [p for p in its.people if p.room == r.name and not p.removed]
        assert len(people) == len(r.people), r.name
        for p in people:
            assert r.ox < p.x < r.ox + r.w and r.oy < p.y < r.oy + r.d and p.fixed
        w.cam.yaw = -math.pi / 2                               # развернулись — и к выходу
        t = 0.0
        while its.current is not None and t < 6.0:
            harness.run(game, 0.1, keys=('w',))
            t += 0.1
        assert its.current is None, r.name
        harness.run(game, 0.8)
        px, py = pl.pos()
        assert math.hypot(px - r.out_pos[0], py - r.out_pos[1]) < 2.5, r.name
        assert not pl.indoors and not pl.freeze and not w.citymesh.root.isHidden() and r.node.isHidden()


def test_street_is_frozen_while_indoors(game, world):
    """Пока герой в помещении, улица стоит (её не видно), а часы идут; вышел — всё на прежних местах и едет."""
    w = world
    its = w.interiors
    w.player.teleport(*w.city.landmarks['safehouse']['door'])      # у своего дома: туда же герой и выйдет
    w.traffic.populate()
    harness.run(game, 2.5)
    cars = [v for v in w.vehicles if v.mode == Vehicle.RAIL and v.npc and abs(v.speed) > 2.0]
    assert cars
    its.enter('safehouse', instant=True)
    harness.run(game, 0.1)
    pos = [(v.x, v.y) for v in cars]
    hour = w.sky.hour
    harness.run(game, 3.0)
    assert [(v.x, v.y) for v in cars] == pos
    assert w.sky.hour > hour
    its.leave(instant=True)
    harness.run(game, 2.5)
    alive = [(v, p0) for v, p0 in zip(cars, pos) if not v.removed]
    assert alive and any(math.hypot(v.x - p0[0], v.y - p0[1]) > 3.0 for v, p0 in alive)


def test_no_weapons_indoors(game, world):
    """В помещении оружие убрано и не стреляет; на улице оно снова в руках."""
    from game.defs import W_FIST
    w = world
    pl = w.player
    its = w.interiors
    pl.give_weapon(W_PISTOL, 30)
    assert pl.ped.weapon.id == W_PISTOL
    its.enter('rosa', instant=True)
    harness.run(game, 0.3)
    assert pl.indoors and pl.ped.weapon.id == W_FIST
    rosa = its.resident('rosa')
    hp = rosa.health
    harness.run(game, 1.2, keys=('mouse1',))
    assert pl.ammo[W_PISTOL] == 30 and w.police.level == 0 and rosa.health == hp and not rosa.dead
    harness.press(game, 'f')                                   # и машины тут нет: F ничего не делает
    harness.run(game, 0.3)
    assert pl.state == 'foot'
    its.leave(instant=True)
    harness.run(game, 0.3)
    assert not pl.indoors and pl.ped.weapon.id == W_PISTOL
    harness.run(game, 0.6, keys=('mouse1',))
    assert pl.ammo[W_PISTOL] < 30


def test_door_is_closed_for_wanted_and_busy(game, world):
    """С розыском или посреди задания в дверь не войти; игра объясняет почему."""
    w = world
    pl = w.player
    its = w.interiors
    ms = w.missions
    harness.quiet(w, peds=True)
    r = its.rooms['rosa']
    x, y = r.out

    def walk_in(sec=2.0):
        pl.teleport(x, y - 3.0, math.pi / 2)
        w.cam.yaw = math.pi / 2
        harness.run(game, 0.2)
        t = 0.0
        while its.current is None and t < sec:
            harness.run(game, 0.1, keys=('w',))
            t += 0.1
        return its.current is r

    w.police.locked = 1
    w.police.set_level(1)
    assert not walk_in()
    assert 'полици' in w.hud.help_text.getText().lower() and w.hud.help_t > 0.0
    w.police.locked = None
    w.police.clear()
    harness.run(game, 4.5)                                      # подсказка не повторяется чаще раза в 4 с
    spec = next(m for m in M.MISSIONS if m['id'] == 'v1')
    assert ms.start(spec)
    for _ in range(12):                                         # брифинг у Вано — пролистать
        harness.run(game, 0.5)
        if not pl.freeze:
            break
        harness.press(game, 'enter')
    harness.run(game, 1.0)
    assert ms.active is not None and not pl.freeze and its.current is None
    assert not walk_in()
    assert 'закончи дело' in w.hud.help_text.getText()
    ms._finish(False, '', True)
    harness.run(game, 0.5)
    assert walk_in(4.0)


def test_hospital_patches_up_for_money(game, world):
    """Регистратура в больнице: перевязка за $100, без денег и здоровых не лечат."""
    w = world
    pl = w.player
    ms = w.missions
    harness.quiet(w, peds=True)
    mk = ms.heal_mk
    room = w.interiors.rooms['hospital']
    ax, ay = room.entry[0], room.entry[1]                       # у входа — в стороне от метки
    assert not mk.inside(ax, ay)

    def visit():
        pl.teleport(ax, ay)
        harness.run(game, 0.3)
        pl.teleport(mk.x, mk.y)
        harness.run(game, 0.3)

    pl.ped.health = 35.0
    visit()
    assert w.interiors.current is room
    assert pl.ped.health == 35.0 and pl.money == 0
    pl.add_money(250)
    visit()
    assert pl.ped.health == pl.ped.max_health and pl.money == 150
    harness.run(game, 1.5)
    visit()
    assert pl.money == 150


# ----------------------------------------------------------------------
# дороги и мосты: проехать должен игрок, а не только трафик «на рельсах»
# ----------------------------------------------------------------------
def test_nothing_stands_on_the_roadway(game, world):
    """Ни одна стена, забор или столб не перегораживает полосу: вся дорожная сеть, шаг 2 м."""
    from game.collision import F_CAR
    w = world
    st = w.static
    blocked = []
    n = 0
    for lane in w.roadnet.lanes:
        k = 0
        while k * 2.0 <= lane.length:
            x, y, yaw = lane.pos(min(lane.length, k * 2.0))
            n += 1
            if st.overlap_circle(x, y, 1.0, F_CAR):
                blocked.append((round(x, 1), round(y, 1)))
            k += 1
    assert n > 20000
    assert not blocked, blocked[:8]


@pytest.mark.parametrize('name,back', [('east', False), ('east', True), ('north', False), ('north', True)])
def test_bridges_are_drivable(game, world, name, back):
    """Оба моста проезжаются за рулём от берега до берега в обе стороны (физика игрока, а не «рельсы»)."""
    w = world
    pl = w.player
    c = w.city
    harness.quiet(w, peds=True)
    seg = next(s for s in c.bridges if s['bridge']['name'] == name)
    # полоса нужного направления (мост — единственное в изогнутом городе, что осталось прямым)
    d = {('h', False): 'e', ('h', True): 'w', ('v', False): 'n', ('v', True): 's'}[(seg['kind'], back)]
    lane = w.roadnet.lane_index[(seg['kind'], seg['i'], seg['j'], d, 0)]
    L = lane.length
    mx, my, _ = lane.pos(L * 0.5)
    assert abs((mx - lane.x0) * (lane.y1 - lane.y0) - (my - lane.y0) * (lane.x1 - lane.x0)) / L < 0.3, 'мост прямой'
    ux, uy = (lane.x1 - lane.x0) / L, (lane.y1 - lane.y0) / L
    x0, y0 = lane.x0 - ux * 30.0, lane.y0 - uy * 30.0            # разгон с берега
    total = L + 60.0
    yaw = math.atan2(uy, ux)
    for v in list(w.vehicles):                                   # дорога свободна
        if not v.keep:
            w.remove_vehicle(v)
    car = w.spawn_vehicle('sedan', x0, y0, yaw)
    pl.teleport(x0, y0)
    pl.enter_vehicle(car, silent=True)
    t = 0.0
    zmax = 0.0
    s = 0.0
    while t < 60.0:
        s = (car.x - x0) * ux + (car.y - y0) * uy
        if s >= total - 4.0:
            break
        off = -(car.x - x0) * uy + (car.y - y0) * ux
        d = (yaw - car.yaw + math.pi) % (2 * math.pi) - math.pi
        steer = -off * 0.10 + d * 1.2
        keys = ('w', 'a') if steer > 0.04 else (('w', 'd') if steer < -0.04 else ('w',))
        harness.run(game, 0.25, keys=keys)
        t += 0.25
        zmax = max(zmax, car.z)
    assert s >= total - 4.0, 'застрял на %.0f м из %.0f (мост %s)' % (s, total, name)
    assert zmax > seg['bridge']['height'] - 0.5                  # действительно поднялись на мост
    assert car.health > 900 and pl.vehicle is car


def test_story_places_are_reachable(game, world):
    """До дверей, ящиков, фургона и самолёта можно добраться от дороги: путь ищется по карте препятствий."""
    w = world
    c = w.city
    harness.quiet(w, peds=True)
    for v in list(w.vehicles):
        if not v.keep:
            w.remove_vehicle(v)
    # места сюжета заданы по чертежу города; в мир их переводит сам город (улицы изогнуты)
    foot = [('дверь ' + r.name,) + c.off(r.out[0], r.out[1], 0.0, -0.6) for r in w.interiors.order]
    for x, y in ((1000.0, -243.0), (1161.0, 258.0), (686.0, 40.0)):                 # ящики «Улова»
        fx, fy = w.missions.free_spot(*c.to_world(x, y))
        foot.append(('ящик', fx, fy))
    ap = c.frame(*c.landmarks['airfield']['apron'])
    foot.append(('самолёт',) + ap(-11.0, 14.0))
    cars = [('самолёт',) + ap(-11.0, 14.0), ('фургон на причале',) + c.to_world(470.0, 30.0),
            ('«Комета» у участка',) + c.frame(*c.landmarks['police']['road'])(13.0, 2.9)]
    for name in ('grom', 'zakhar', 'vano', 'rosa', 'prof'):
        rx, ry = c.landmarks[name]['road']
        cars.append(('машина у ' + name, rx, ry))
    lost = [n for n, x, y in foot if not harness.reachable(w, x, y)]
    lost += [n + ' (на машине)' for n, x, y in cars if not harness.reachable(w, x, y, car=True)]
    assert not lost, lost
    # и проверка самой проверки: точка внутри здания недостижима
    assert not harness.reachable(w, *c.landmarks['bank']['center'])


def test_every_hidden_package_can_be_reached(game, world):
    """Тайник, запертый за забором или в стене, собрать нельзя — а счётчик «из 46» остался бы вечным укором."""
    w = world
    c = w.city
    harness.quiet(w, peds=True)
    for v in list(w.vehicles):
        if not v.keep:
            w.remove_vehicle(v)
    assert len(c.packages) == 47
    lost = []
    for i, pk in enumerate(c.packages):
        x, y = pk[0], pk[1]
        # сначала ищем путь рядом; если двор обнесён забором и вход далеко — по большой окрестности
        if not harness.reachable(w, x, y) and not harness.reachable(w, x, y, margin=200.0):
            lost.append((i, round(x, 1), round(y, 1), c.zone_name(x, y)))
    assert not lost, lost


# ----------------------------------------------------------------------
# гараж
# ----------------------------------------------------------------------
def test_garage_keeps_cars(game, world):
    """Загнал машину в гараж и вышел — она записана в сохранение и после загрузки стоит на месте, того же
    цвета.  Четвёртая машина в трёхместный гараж не записывается; выгнал машину — её в гараже больше нет."""
    w = world
    pl = w.player
    gar = w.garage
    harness.quiet(w, peds=True)
    assert gar.ok and gar.capacity() == 3 and not gar.cars
    sx, sy = gar.slots[0]
    off = w.city.off                                         # сдвиги — по чертежу гаража: улицы города изогнуты
    car = w.spawn_vehicle('sports', *off(sx, sy, 0.0, -12.0), gar.yaw, paint=5)
    pl.teleport(*off(sx, sy, -2.5, -12.0))
    pl.enter_vehicle(car, silent=True)
    harness.run(game, 0.5)
    assert gar.k > 0.5                                       # ворота поднялись навстречу
    # въезжаем своим ходом
    t = 0.0
    while t < 8.0 and not gar.contains(car.x, car.y, 0.6):
        harness.run(game, 0.1, keys=('w',))
        t += 0.1
    assert gar.contains(car.x, car.y, 0.3), (car.x, car.y, gar.rect)
    harness.run(game, 1.5, keys=('space',))
    assert not gar.cars                                      # пока герой за рулём, машина ещё «не оставлена»
    pl.leave_vehicle(force=True)
    harness.run(game, 1.0)
    assert gar.cars == [car] and car.keep and car.garage
    data = settings_mod.load_save()
    assert data is not None and len(data['garage']) == 1
    assert data['garage'][0]['kind'] == 'sports' and data['garage'][0]['paint'] == 5
    # ещё две — и гараж полон
    for k, kind in ((1, 'sedan'), (2, 'pickup')):
        x, y = gar.slots[k]
        w.spawn_vehicle(kind, x, y, gar.yaw, paint=k)
    harness.run(game, 0.6)
    assert len(gar.cars) == 3
    extra = w.spawn_vehicle('hatch', *gar.out(-1.6), gar.yaw - math.pi / 2, paint=3)
    said = []
    orig = w.hud.help
    w.hud.help = lambda text, dur=6.0: said.append(text)
    try:
        harness.run(game, 0.6)
    finally:
        w.hud.help = orig
    assert len(gar.cars) == 3 and extra not in gar.cars and any('полон' in t_ for t_ in said)
    w.remove_vehicle(extra)
    harness.run(game, 0.5)
    assert len(settings_mod.load_save()['garage']) == 3
    # ушёл далеко — машины никуда не делись
    pl.teleport(*w.city.landmarks['terminal']['door'])
    harness.run(game, 3.0)
    assert all(not v.removed for v in gar.cars) and gar.k == 0.0
    # загрузка: те же три машины на своих местах
    game.to_main_menu()
    game.continue_game()
    w = game.world
    gar = w.garage
    assert sorted(v.kind for v in gar.cars) == ['pickup', 'sedan', 'sports']
    sp = next(v for v in gar.cars if v.kind == 'sports')
    assert sp.paint == 5 and gar.contains(sp.x, sp.y, 0.2) and sp.keep
    # выгоняем одну: в гараже остаются две
    pl = w.player
    w.interiors.leave(instant=True)
    w.traffic.enabled = False
    pl.teleport(*w.city.off(sp.x, sp.y, -2.0, -9.0))
    pl.enter_vehicle(sp, silent=True)
    sp.x, sp.y = gar.out(14.0)
    sp.sync()
    harness.run(game, 0.5)
    assert sp not in gar.cars and len(gar.cars) == 2
    pl.leave_vehicle(force=True)
    harness.run(game, 0.6)
    assert len(settings_mod.load_save()['garage']) == 2
    # новая игра начинается с пустым гаражом
    w = harness.start_game(game)
    assert not w.garage.cars


def test_camera_stays_under_garage_roof(game, world):
    """В гараже камера не поднимается сквозь крышу: иначе вместо машины видна кровля."""
    w = world
    pl = w.player
    gar = w.garage
    harness.quiet(w, peds=True)
    pl.teleport(*gar.out(-4.6), gar.yaw)
    w.cam.yaw = gar.yaw + math.pi                            # смотрим из глубины гаража на ворота
    w.cam.pitch = -0.9
    w.cam.snap()
    harness.run(game, 0.6)
    assert gar.contains(w.cam.x, w.cam.y, -0.5)
    assert w.cam.z < w.city.ceiling(gar.cx, gar.cy) - 0.2


# ----------------------------------------------------------------------
# машина героя
# ----------------------------------------------------------------------
def _with_hero_car(game, seed):
    """Свободный город, в котором «Ласточка» на месте (обычно проверки начинают без неё)."""
    random.seed(seed)
    w = harness.start_game(game, hero=True)
    w.player.invincible = False
    harness.quiet(w, peds=True)                              # машину героя quiet() не трогает
    return w


def _leave_in_town(game, w, car, x, y):
    """Выгнать машину из гаража и оставить в точке (x, y): герой рядом с гаражом, чтобы тот это заметил."""
    gar = w.garage
    w.player.teleport(*gar.out(20.0))
    car.x, car.y = x, y
    car.vx = car.vy = car.speed = 0.0
    car.sync()
    harness.run(game, 0.5)
    assert car not in gar.cars and car.keep


def test_hero_car_waits_in_the_garage(game):
    """Новая игра: «Ласточка», машина Макса, стоит в гараже у дома и отмечена на радаре.  Она одна на весь
    город; сесть в неё — не угон; оставленная где угодно, она никуда не исчезает."""
    from game.garage import HERO_KIND
    from game.traffic import ZONE_PARKED
    w = _with_hero_car(game, 41)
    pl = w.player
    gar = w.garage
    hc = w.hero_car
    car = hc.v
    assert HERO_KIND == 'retro' and SPECS['retro'].title == 'Ласточка'
    assert car is not None and car.kind == 'retro' and car.hero and car.keep and car.owner == 'player'
    assert gar.cars == [car] and math.hypot(car.x - gar.slots[0][0], car.y - gar.slots[0][1]) < 0.1
    assert abs(car.yaw - gar.yaw) < 0.01 and car.mode == Vehicle.PARKED
    assert [v for v in w.vehicles if v.kind == 'retro'] == [car]
    # в потоке машин и на стоянках таких нет
    assert not any(k == 'retro' for cars in ZONE_CARS.values() for k, _ in cars)
    assert not any('retro' in kinds for kinds in ZONE_PARKED.values())
    # значок на радаре
    harness.run(game, 0.3)
    blip = hc.blip
    assert blip is not None and blip in w.hud.blips and blip.tex == 'blip_car' and blip.obj is car
    # ворота открываются навстречу; сел — не угон, розыска нет, значок на время убран
    pl.teleport(*gar.out(5.0))
    harness.run(game, 1.0)
    assert gar.k > 0.9
    pl.teleport(*w.city.off(car.x, car.y, -1.5, 0.0))
    stolen = w.stats['stolen']
    pl.enter_vehicle(car, silent=True)
    harness.run(game, 0.5)
    assert pl.vehicle is car and w.stats['stolen'] == stolen and w.police.level == 0
    assert hc.blip is None and blip not in w.hud.blips and gar.cars == [car]
    # выезжаем задним ходом
    t = 0.0
    while t < 8.0 and gar.contains(car.x, car.y, -2.0):
        harness.run(game, 0.2, keys=('s',))
        t += 0.2
    assert not gar.contains(car.x, car.y) and car not in gar.cars and car.keep and car.hero
    # оставили на другом конце города и ушли: она там и стоит, и значок ведёт к ней
    tx, ty = w.city.landmarks['terminal']['road']
    car.x, car.y = tx, ty
    car.vx = car.vy = car.speed = 0.0
    car.sync()
    pl.leave_vehicle(force=True)
    harness.run(game, 0.5)
    assert hc.blip is not None and hc.blip.obj is car
    ax, ay = w.city.landmarks['airfield']['apron']
    assert math.hypot(ax - tx, ay - ty) > 400.0
    pl.teleport(ax, ay)
    harness.run(game, 40.0)
    assert hc.v is car and car in w.vehicles and not car.removed and not gar.cars
    assert math.hypot(car.x - tx, car.y - ty) < 1.0


def test_hero_car_comes_back_home(game):
    """Разбитая (или утонувшая) «Ласточка» через полминуты снова стоит в гараже — в той же окраске и с тем же
    тюнингом.  Но не на глазах у героя: пока он возле дома, гараж пуст.  Остов убирают, как любой другой."""
    from game.garage import HERO_BACK, HERO_FAR
    w = _with_hero_car(game, 43)
    pl = w.player
    gar = w.garage
    hc = w.hero_car
    car = hc.v
    car.set_paint(3)
    car.apply_tune({'engine': 2, 'neon': 1})
    harness.run(game, 0.2)
    assert hc.paint == 3 and hc.tune == {'engine': 2, 'neon': 1}
    said = []                                               # что сказано о «Ласточке» (прочие подсказки не в счёт)
    orig = w.hud.help
    w.hud.help = lambda text, dur=6.0: said.append(text) if 'Ласточк' in text else None
    try:
        # герой далеко от дома, машину взорвали прямо в гараже
        tx, ty = w.city.landmarks['terminal']['door']
        assert math.hypot(tx - gar.cx, ty - gar.cy) > HERO_FAR
        pl.teleport(tx, ty)
        car.explode(False)
        harness.run(game, 1.0)
        assert car.dead and not hc.alive() and hc.blip is None and not car.keep and not car.hero
        harness.run(game, HERO_BACK - 3.0)
        assert not hc.alive() and not said
        harness.run(game, 4.0)
        new = hc.v
        assert new is not car and hc.alive() and new.kind == 'retro' and new.hero and new.keep
        assert new.paint == 3 and new.tune == {'engine': 2, 'neon': 1} and new.health == new.max_health
        assert gar.cars == [new] and gar.contains(new.x, new.y, 0.3) and car.removed
        assert len([v for v in w.vehicles if v.kind == 'retro']) == 1
        assert len(said) == 1
        # герой возле дома: пока он тут, новая машина не появляется
        del said[:]
        pl.teleport(*gar.out(30.0))
        harness.run(game, 0.5)
        new.explode(False)
        harness.run(game, HERO_BACK + 10.0)
        assert not hc.alive() and not said and not gar.cars
        # ушёл — и она на месте
        pl.teleport(tx, ty)
        harness.run(game, 1.0)
        third = hc.v
        assert hc.alive() and third in gar.cars and third.paint == 3 and len(said) == 1
        # утонувшая возвращается так же
        third._sink()
        assert third.sunk and not hc.alive()
        harness.run(game, HERO_BACK + 1.5)
        assert hc.alive() and hc.v is not third and gar.cars == [hc.v]
        assert len([v for v in w.vehicles if v.kind == 'retro' and not v.removed]) == 1
    finally:
        w.hud.help = orig


def test_hero_car_is_saved(game):
    """Сохранение помнит окраску и тюнинг «Ласточки».  После загрузки она в гараже — одна, а не две.
    Сохранение прежней версии (без записи о ней) тоже получает машину; занятый гараж ей не помеха."""
    w = _with_hero_car(game, 47)
    hc = w.hero_car
    car = hc.v
    car.set_paint(5)
    car.apply_tune({'spoiler': 1, 'rims': 2})
    harness.run(game, 0.2)
    assert w.missions.save_game()
    data = settings_mod.load_save()
    assert data['hero'] == {'paint': 5, 'tune': {'spoiler': 1, 'rims': 2}}
    assert [c['kind'] for c in data['garage']] == ['retro']
    game.to_main_menu()
    assert not [v for v in game.world.vehicles if v.kind == 'retro'] and game.world.hero_car.v is None
    game.continue_game()
    w = game.world
    hc = w.hero_car
    retro = [v for v in w.vehicles if v.kind == 'retro']
    assert len(retro) == 1 and hc.v is retro[0] and retro[0].hero and retro[0].keep and w.garage.cars == retro
    assert retro[0].paint == 5 and retro[0].tune == {'spoiler': 1, 'rims': 2}
    # сохранение прежней версии: о «Ласточке» в нём ни слова, а гараж занят тремя машинами
    del data['hero']
    data['garage'] = [dict(kind=k, paint=1, x=x, y=y, yaw=w.garage.yaw, hp=900.0, tune={})
                      for k, (x, y) in zip(('sedan', 'hatch', 'pickup'), w.garage.slots)]
    assert settings_mod.write_save(data)
    game.to_main_menu()
    game.continue_game()
    w = game.world
    gar = w.garage
    hc = w.hero_car
    assert sorted(v.kind for v in gar.cars) == ['hatch', 'pickup', 'sedan']
    car = hc.v
    assert hc.alive() and car.kind == 'retro' and car.paint == 0 and car not in gar.cars and car.keep
    # она ждёт на площадке перед воротами и ни с чем не пересекается
    assert math.hypot(car.x - gar.out(4.2)[0], car.y - gar.out(4.2)[1]) < 0.1   # на площадке перед воротами
    assert not w.static.overlap_circle(car.x, car.y, 1.0, F_CAR)
    # новая игра начинается с чистого листа: заводская окраска, тюнинга нет
    w = harness.start_game(game, hero=True)
    assert w.hero_car.v.paint == 0 and not w.hero_car.v.tune and w.garage.cars == [w.hero_car.v]


def test_sleeping_at_home_brings_the_hero_car_back(game):
    """Оставил «Ласточку» в городе, пришёл домой и лёг спать (сохранение у кровати): к утру она в гараже —
    как было бы и после загрузки.  Об этом сказано в вопросе о сохранении.  Машину у дома не трогают."""
    w = _with_hero_car(game, 53)
    pl = w.player
    gar = w.garage
    hc = w.hero_car
    car = hc.v
    car.set_paint(2)
    mk = w.missions.save_mk
    assert not hc.away()
    tx, ty = w.city.landmarks['terminal']['road']
    _leave_in_town(game, w, car, tx, ty)
    assert hc.away()
    said = []
    orig = w.hud.help
    w.hud.help = lambda text, dur=6.0: said.append(text) if 'Ласточк' in text else None
    try:
        pl.teleport(mk.x, mk.y)
        harness.run(game, 0.3)
        assert game.state == 'shop' and 'Ласточк' in game.ui.stack[-1].text
        harness.press(game, 'enter')                         # «Сохранить игру»
        harness.run(game, 0.3)
        assert game.state == 'play'
        new = hc.v
        assert car.removed and new is not car and hc.alive() and new.paint == 2 and gar.cars == [new]
        assert not hc.away() and len(said) == 1
        assert [c['kind'] for c in settings_mod.load_save()['garage']] == ['retro']
        assert len([v for v in w.vehicles if v.kind == 'retro']) == 1
        # машина стоит перед домом, не в гараже: это тоже «дома»
        del said[:]
        pl.teleport(mk.x + 6.0, mk.y)
        harness.run(game, 0.3)
        _leave_in_town(game, w, new, *gar.out(6.0))
        assert not hc.away()
        pl.teleport(mk.x, mk.y)
        harness.run(game, 0.3)
        assert game.state == 'shop' and 'Ласточк' not in game.ui.stack[-1].text
        harness.press(game, 'enter')
        harness.run(game, 0.3)
        assert hc.v is new and not new.removed and not said
    finally:
        w.hud.help = orig


# ----------------------------------------------------------------------
# тюнинг
# ----------------------------------------------------------------------
def test_tuning_catalogue():
    """В ателье больше тридцати деталей; у каждой есть название и цена."""
    from game import tuning
    assert tuning.TOTAL >= 30 and len(tuning.PARTS) >= 12
    keys = [k for k, _, _ in tuning.PARTS]
    assert len(keys) == len(set(keys))
    for key, title, opts in tuning.PARTS:
        assert title and opts
        for name, price in opts:
            assert name and 100 <= price <= 10000
    assert tuning.clean({'engine': 3, 'neon': 9, 'ghost': 1, 'rims': 'x', 'turbo': 0}) == {'engine': 3}
    assert tuning.value({'engine': 1, 'nitro': 1}) == 1200 + 4000


def test_tuning_changes_the_car(game, world):
    """Двигатель и турбина разгоняют машину быстрее, тормоза останавливают раньше, броня добавляет прочности,
    внешние детали появляются на кузове, а сброс возвращает всё как было."""
    from game import tuning
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    lane = w.roadnet.lane_index[('h', 2, 2, 'e', 0)]
    x, y, yaw = lane.pos(4.0)

    def sprint(tune):
        if pl.vehicle is not None:
            pl.leave_vehicle(force=True)
        for v_ in list(w.vehicles):
            w.remove_vehicle(v_)
        car = w.spawn_vehicle('sedan', x, y, yaw, paint=2)
        car.apply_tune(tune)
        pl.teleport(x, y - 3.0)
        pl.enter_vehicle(car, silent=True)
        harness.run(game, 0.3)
        harness.run(game, 4.0, keys=('w',))
        v4 = car.speed
        d = 0.0
        x0_ = car.x
        while car.speed > 0.5 and d < 8.0:
            harness.run(game, 0.1, keys=('s',))
            d += 0.1
        return car, v4, car.x - x0_
    stock, v_stock, stop_stock = sprint({})
    assert stock.k_acc == 1.0 and stock.max_health == stock.spec.health and stock.tune_np is None
    fast, v_fast, stop_fast = sprint({'engine': 3, 'turbo': 1, 'gearbox': 2, 'brakes': 3, 'tyres': 2})
    assert v_fast > v_stock * 1.15, (v_stock, v_fast)
    assert fast.k_brake > 1.5
    # внешние детали и прочность
    car = fast
    car.apply_tune({'spoiler': 3, 'roof': 2, 'bumper': 1, 'neon': 1, 'rims': 3, 'armor': 3, 'susp': 1, 'exhaust': 2,
                    'horn': 2, 'xenon': 2, 'nitro': 1})
    assert car.tune_np is not None and not car.tune_np.isEmpty() and car.neon_np is not None
    assert car.max_health == car.spec.health * 2.0 and car.ride < 0.0
    assert car.horn == 'horn_tune' and car.nitro and car.snd_pitch < 1.0
    mn, mx = car.tune_np.getTightBounds(car.tilt)
    assert mx.z > car.spec.H * 0.8 and mn.y < -car.spec.L * 0.5 + 0.2 and mx.y > car.spec.L * 0.5      # крыша, корма, нос
    # перекраска не снимает детали
    car.set_paint(4)
    assert car.tune_np is not None and car.neon_np is not None and len(car.tune) == 11
    # нитро: на Shift машина едет быстрее, баллон пустеет и потом наполняется
    car.nitro_k = 1.0
    car.x, car.y, car.yaw = x, y, yaw
    car.vx = car.vy = car.speed = 0.0
    harness.run(game, 3.0, keys=('w',))
    v_plain = car.speed
    car.x, car.y, car.yaw = x, y, yaw
    car.vx = car.vy = car.speed = 0.0
    car.nitro_k = 1.0
    harness.run(game, 3.0, keys=('w', 'shift'))
    assert car.speed > v_plain * 1.08 and car.nitro_k < 0.3, (v_plain, car.speed, car.nitro_k)
    k0 = car.nitro_k
    harness.run(game, 2.0)
    assert car.nitro_k > k0
    # всё снять
    car.apply_tune({})
    assert car.tune_np is None and car.neon_np is None and car.k_acc == 1.0 and car.max_health == car.spec.health
    assert not car.nitro and car.horn is None and car.ride == 0.0


def test_tuning_shop_and_garage_remember_parts(game, world):
    """В ателье деталь покупается из меню; машина с тюнингом переживает гараж и загрузку сохранения."""
    from game import tuning
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    pl.add_money(20000)
    bx, by = w.city.landmarks['spray']['bay']
    car = w.spawn_vehicle('muscle', bx, by, math.pi / 2, paint=3)
    pl.teleport(bx + 3.0, by)
    pl.enter_vehicle(car, silent=True)
    harness.run(game, 1.2)
    assert game.state == 'shop'
    m = game.ui.stack[-1]
    labels = [it.label for it in m.items]
    assert labels[0] == 'Покраска' and 'Двигатель' in labels and 'Неон' in labels and labels[-1] == 'Выехать'
    i = labels.index('Двигатель')
    for _ in range(i):
        harness.press(game, 'arrow_down')
    harness.press(game, 'enter')
    assert game.ui.stack[-1].title == 'Двигатель'
    harness.press(game, 'arrow_down')
    harness.press(game, 'arrow_down')
    harness.press(game, 'enter')                             # «Форсированный»
    assert car.tune == {'engine': 2} and pl.money == 20000 - 2600
    harness.press(game, 'enter')                             # повторно то же — ничего не списывается
    assert pl.money == 20000 - 2600
    harness.press(game, 'escape')
    harness.press(game, 'escape')
    assert game.state == 'play'
    car.apply_tune({'engine': 2, 'spoiler': 2, 'neon': 4})
    # в гараж — и в сохранение
    gar = w.garage
    pl.leave_vehicle(force=True)
    sx, sy = gar.slots[1]
    car.x, car.y, car.yaw = sx, sy, gar.yaw
    car.vx = car.vy = car.speed = 0.0
    car.sync()
    pl.teleport(*w.city.off(sx, sy, 0.0, -9.0))
    harness.run(game, 1.0)
    assert car in gar.cars
    saved = settings_mod.load_save()['garage'][0]
    assert saved['kind'] == 'muscle' and saved['tune'] == {'engine': 2, 'spoiler': 2, 'neon': 4}
    game.to_main_menu()
    game.continue_game()
    w = game.world
    car = w.garage.cars[0]
    assert car.kind == 'muscle' and car.tune == {'engine': 2, 'spoiler': 2, 'neon': 4}
    assert car.k_acc > 1.1 and car.tune_np is not None and car.neon_np is not None
    w = harness.start_game(game)


def test_chase_car_frees_itself_when_wedged(game, world):
    """Патрульная машина, зажатая на тротуаре между стеной дома и деревом, не буксует на месте до конца погони:
    мотор толкает её вперёд, дерево возвращает назад, скорость при этом не нулевая. Водитель должен заметить,
    что машина не сдвинулась, сдать назад, отвернуть и объехать."""
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    w.police.clear()
    tree = [c for c in w.static.circles if c[4] and abs(c[0] + 205.9) < 0.3 and abs(c[1] + 115.5) < 0.3]
    lanes = [l for l in w.roadnet.lanes_near(-240.0, -175.8, 0.0, 60.0)
             if l.turn is None and abs(l.x0 + 205.0) < 0.5 and abs(l.y0 + 175.8) < 0.5 and l.x1 < l.x0]
    if not tree or not lanes:
        pytest.skip('дерево или полоса у Адмиральского проспекта переехали: сцену нужно собрать заново')
    # так машина и стояла в игре: нос на север, слева стена, справа спереди дерево, а её полоса осталась позади
    v = w.spawn_vehicle('police', -206.7, -115.8, 1.79)
    lane = w.roadnet.lane_index[('h', 2, 2, 'e', 0)]
    hx, hy, _ = lane.pos(10.0)
    pl.teleport(hx, hy - 3.0)
    pl.invincible = True
    w.police.set_level(2)
    w.police.spawn_t = 1e9                          # подмога не нужна: смотрим на одну машину
    w.police._make_unit(v)
    v.link, v.s, v.next_link = lanes[0], 1.7, None
    v.direct = False
    v.route_t = 1e9                                 # маршрут не пересчитываем: важно только, выберется ли она
    far = 0.0
    for _ in range(60 * 14):
        game.step(DT)
        w.police.spawn_t = 1e9
        far = max(far, math.hypot(v.x + 206.7, v.y + 115.8))
        if far > 9.0:
            break
    pl.invincible = False
    w.police.clear()
    w.remove_vehicle(v)
    assert far > 9.0, 'машина погони так и осталась у дерева: (%.1f, %.1f)' % (v.x, v.y)


def test_garage_keeps_a_motorcycle(game, world):
    """В гараж можно поставить и мотоцикл: он попадает в сохранение с цветом и тюнингом, а после загрузки на нём
    можно уехать — ездок снова сидит в седле."""
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    gar = w.garage
    gar.reset()
    sx, sy = gar.slots[0]
    bike = w.spawn_vehicle('chopper', sx, sy, gar.yaw, paint=2)
    bike.apply_tune({'engine': 1, 'neon': 2, 'rims': 3})
    pl.teleport(*w.city.off(sx, sy, 0.0, -9.0))
    harness.run(game, 1.0)
    assert bike in gar.cars
    saved = settings_mod.load_save()['garage'][0]
    assert saved['kind'] == 'chopper' and saved['paint'] == 2 and saved['tune'] == {'engine': 1, 'neon': 2, 'rims': 3}
    game.to_main_menu()
    game.continue_game()
    w = game.world
    pl = w.player
    assert len(w.garage.cars) == 1
    bike = w.garage.cars[0]
    assert bike.kind == 'chopper' and bike.bparts is not None and bike.paint == 2
    assert bike.tune == {'engine': 1, 'neon': 2, 'rims': 3}
    if w.interiors.current is not None:
        w.interiors.leave(instant=True)
    pl.teleport(*w.city.off(bike.x, bike.y, 0.0, -3.0))
    pl.enter_vehicle(bike, silent=True)
    harness.run(game, 0.3)
    assert pl.vehicle is bike and pl.ped.vis.cur == 'mix' and pl.ped.node.getParent() == bike.tilt
    pl.leave_vehicle(force=True)
    w.garage.reset()
    w = harness.start_game(game)


def test_old_save_with_removed_bikes_still_loads(game, world):
    """В сохранении прежних версий в гараже мог стоять мотороллер, велосипед или мотоцикл с коляской.  Этой
    техники больше нет: сохранение грузится, а остальные машины стоят на своих местах."""
    w = world
    harness.quiet(w, peds=True)
    w.garage.reset()
    w.missions.save_game(auto=True)
    data = settings_mod.load_save()
    data['garage'] = [dict(kind='sidecar', paint=1, tune={'engine': 1}), dict(kind='sedan', paint=2, tune={}),
                      dict(kind='bicycle', paint=0), dict(kind='chopper', paint=1, tune={})]
    settings_mod.write_save(data)
    game.to_main_menu()
    game.continue_game()
    w = game.world
    kinds = sorted(v.kind for v in w.garage.cars if not v.hero)
    assert kinds == ['chopper', 'sedan'], kinds
    harness.run(game, 0.5)
    assert game.state == 'play'
    w.garage.reset()
    w = harness.start_game(game)
