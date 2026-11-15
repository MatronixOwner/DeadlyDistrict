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
from game.defs import W_PISTOL, W_UZI, W_ROCKET, random_look
from game.vehicle import Vehicle

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
    harness.run(game, 2.5)
    assert pl.vehicle is v and not v.npc
    # водителя выбросили на дорогу
    assert any(p.last_attacker is pl.ped for p in w.peds if not p.is_player)
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
    assert labels[:5] == ['Режим экрана', 'Разрешение', 'Текстуры', 'Сглаживание краёв',
                          'Вертикальная синхронизация']
    tex = g.assets.tex('fac_brick_a')
    assert tex.getMagfilter() == SamplerState.FTNearest and tex.getAnisotropicDegree() == 16
    items = {it.label: it for it in m.items}
    items['Текстуры'].change(1)
    assert s.get('smooth_textures') is True and tex.getMagfilter() == SamplerState.FTLinear
    assert items['Текстуры'].value() == 'Сглаженные'
    items['Текстуры'].change(1)
    assert tex.getMagfilter() == SamplerState.FTNearest
    before = int(s.get('msaa'))
    items['Сглаживание краёв'].change(1)
    assert int(s.get('msaa')) != before and 'перезапуска' in items['Сглаживание краёв'].value()
    items['Сглаживание краёв'].change(-1)
    assert int(s.get('msaa')) == before and 'перезапуска' not in items['Сглаживание краёв'].value()
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


# ----------------------------------------------------------------------
# пролог
# ----------------------------------------------------------------------
def _after_intro(g, w, errors):
    """После пролога (досмотренного или пропущенного) игра в рабочем состоянии: герой стоит на остановке,
    управление у игрока, и ему звонит брат."""
    ms = w.missions
    pl = w.player
    assert ms.intro is None and g.state == 'play' and not g.ui.active
    assert w.interiors.current is None
    sx, sy, syaw = w.city.start_pos
    assert math.hypot(pl.ped.x - (sx - 11.5), pl.ped.y - (sy - 1.3)) < 6.0
    assert not pl.freeze and pl.script_move is None and not pl.invincible
    assert not pl.ped.node.isHidden() and abs(pl.ped.z - w.city.ground_z(*pl.pos())) < 0.05
    assert w.hud.visible and w.cam.override is None and ms.letter.isHidden()
    assert w.traffic.enabled and w.sky.time_scale == 1.0 and w.scene_engine is None
    assert not w.interiors.cinema
    assert not any(v.scripted for v in w.vehicles)
    assert ms.markers and all(not mk.np.isHidden() for mk in ms.markers)
    assert abs(w.sky.hour - 8.0) < 0.3 and w.sky.weather == 'clear'
    assert g._errors_total == errors
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


def test_intro_plays_to_the_end(game):
    """Пролог без единого нажатия: трасса, мост, остановка — и игра начинается звонком брата."""
    g = game
    random.seed(7)
    errors = g._errors_total
    g.new_game()
    w = g.world
    ms = w.missions
    pl = w.player
    assert ms.intro is not None and pl.freeze
    lines = []
    seen = dict(bus=False, hidden=False, walked=False, room=False, paused=False)
    t = 0.0
    while ms.intro is not None and t < 120.0:
        g.step(DT)
        t += DT
        text = w.hud.sub_plain
        if text and (not lines or lines[-1] != text):
            lines.append(text)
        it = ms.intro
        if it is None:
            break
        seen['bus'] |= it['bus'] is not None and abs(it['bus'].speed) > 5.0
        seen['hidden'] |= pl.ped.node.isHidden()
        seen['walked'] |= pl.script_move is not None and pl.ped.speed > 0.5
        seen['room'] |= w.interiors.current is not None
        seen['paused'] |= g.state != 'play'
        assert pl.freeze and not w.hud.visible
        assert w.police.level == 0 and pl.ped.health == 100
    assert 20.0 < t < 60.0, t
    assert len(lines) >= 4 and lines[0].startswith('Порт-Глухов')
    assert any(s_.startswith('Водитель:') for s_ in lines) and any('брат' in s_ for s_ in lines)
    assert not any('Вано' in s_ for s_ in lines)                 # старого сюжета в прологе больше нет
    assert seen == dict(bus=True, hidden=True, walked=True, room=False, paused=False), seen
    _after_intro(g, w, errors)


@pytest.mark.parametrize('when', [0.1, 3.0, 9.0, 18.0, 25.5, 30.0])
def test_intro_can_be_skipped_any_time(game, when):
    """Esc в любой момент пролога: декорации убраны, герой на остановке, пауза не открылась."""
    g = game
    random.seed(11)
    errors = g._errors_total
    g.new_game()
    w = g.world
    harness.run(g, when)
    assert w.missions.intro is not None
    harness.press(g, 'escape')
    harness.run(g, 0.3)
    _after_intro(g, w, errors)


def test_intro_enter_steps_through_shots(game):
    """Enter листает кадры пролога: за несколько нажатий он заканчивается."""
    g = game
    random.seed(13)
    errors = g._errors_total
    g.new_game()
    w = g.world
    n = 0
    while w.missions.intro is not None and n < 30:
        harness.run(g, 0.5)
        harness.press(g, 'enter')
        n += 1
    assert 3 <= n < 20, n
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


def test_intro_interrupted_by_menu(game):
    """Пролог прервали (окно потеряло фокус → пауза → главное меню): мир не остаётся «выключенным»."""
    g = game
    random.seed(19)
    errors = g._errors_total
    g.new_game()
    w = g.world
    harness.run(g, 20.0)
    assert w.missions.intro is not None and not w.traffic.enabled
    g.pause()                                   # так срабатывает потеря фокуса окна
    assert g.state == 'pause'
    g.to_main_menu()
    w = g.world
    assert w.traffic.enabled and w.sky.time_scale == 1.0 and w.scene_engine is None
    assert g.state == 'menu' and w.missions.intro is None and not w.interiors.cinema
    harness.run(g, 1.0)
    assert not any(v.scripted for v in w.vehicles)
    w = harness.start_game(g, street=False, story=True)
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
    a, b, cc = seg['a'], seg['b'], seg['c']
    mid = (a + b) * 0.5
    px, py = (mid, cc) if seg['kind'] == 'h' else (cc, mid)
    lanes = [l for l in w.roadnet.lanes_near(px, py, 0.0, 40.0)
             if l.turn is None and abs(l.length - (b - a)) < 1.0]
    assert len(lanes) >= 2
    # полоса нужного направления
    def forward(l):
        return (l.x1 - l.x0) + (l.y1 - l.y0) > 0
    lane = next(l for l in lanes if forward(l) != back)
    L = lane.length
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
    foot = [('дверь ' + r.name, r.out[0], r.out[1] - 0.6) for r in w.interiors.order]
    for x, y in ((1000.0, -243.0), (1161.0, 258.0), (686.0, 40.0)):                 # ящики «Улова»
        fx, fy = w.missions.free_spot(x, y)
        foot.append(('ящик', fx, fy))
    ap = c.landmarks['airfield']['apron']
    foot.append(('самолёт', ap[0] - 11.0, ap[1] + 14.0))
    cars = [('самолёт', ap[0] - 11.0, ap[1] + 14.0), ('фургон на причале', 470.0, 30.0),
            ('«Комета» у участка', c.landmarks['police']['road'][0] + 13.0, c.landmarks['police']['road'][1] + 2.9)]
    for name in ('grom', 'zakhar', 'vano', 'rosa', 'prof'):
        rx, ry = c.landmarks[name]['road']
        cars.append(('машина у ' + name, rx, ry))
    lost = [n for n, x, y in foot if not harness.reachable(w, x, y)]
    lost += [n + ' (на машине)' for n, x, y in cars if not harness.reachable(w, x, y, car=True)]
    assert not lost, lost
    # и проверка самой проверки: точка внутри здания недостижима
    x0, y0, x1, y1 = c.landmarks['bank']['rect']
    assert not harness.reachable(w, (x0 + x1) * 0.5, (y0 + y1) * 0.5)


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
    car = w.spawn_vehicle('sports', sx, sy - 12.0, math.pi / 2, paint=5)
    pl.teleport(sx - 2.5, sy - 12.0)
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
        w.spawn_vehicle(kind, x, y, math.pi / 2, paint=k)
    harness.run(game, 0.6)
    assert len(gar.cars) == 3
    extra = w.spawn_vehicle('hatch', gar.cx, gar.rect[1] + 1.6, 0.0, paint=3)
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
    pl.teleport(sp.x - 2.0, sp.y - 9.0)
    pl.enter_vehicle(sp, silent=True)
    sp.x, sp.y = gar.cx, gar.rect[1] - 14.0
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
    pl.teleport(gar.cx, gar.cy + 1.0, math.pi / 2)
    w.cam.yaw = -math.pi / 2                                 # смотрим из глубины гаража на ворота
    w.cam.pitch = -0.9
    w.cam.snap()
    harness.run(game, 0.6)
    assert gar.contains(w.cam.x, w.cam.y, -0.5)
    assert w.cam.z < w.city.ceiling(gar.cx, gar.cy) - 0.2


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
    car.x, car.y, car.yaw = sx, sy, math.pi / 2
    car.vx = car.vy = car.speed = 0.0
    car.sync()
    pl.teleport(sx, sy - 9.0)
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
