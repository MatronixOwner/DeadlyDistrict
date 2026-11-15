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
    # в стену дома пройти нельзя
    world.cam.yaw = math.pi / 2
    harness.run(game, 6.0, keys=('w', 'shift'))
    lm = world.city.landmarks['safehouse']
    assert pl.pos()[1] < lm['rect'][1] + 0.1


def test_enter_drive_exit(game, world):
    w = world
    pl = w.player
    harness.quiet(w)
    x, y = w.city.landmarks['safehouse']['road']
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
    for _ in range(200):
        v = w.nearest_vehicle(pl.ped.x, pl.ped.y, 150.0, lambda q: q.npc and q.mode == Vehicle.RAIL)
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
    x, y = w.city.landmarks['safehouse']['road']
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
    x, y = w.city.landmarks['safehouse']['road']
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
    paint = car.paint
    harness.run(game, 1.5)
    assert w.police.level == 0 and car.health == car.max_health
    assert pl.money == 700 and car.paint != paint


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
    harness.press(game, 'arrow_down')                        # пистолет
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
    x, y = w.city.landmarks['vano']['door']
    pl.teleport(x, y - 6.0)
    harness.run(game, 0.3)
    assert ms.active is None
    w.cam.yaw = math.pi / 2                       # лицом к гаражу
    harness.run(game, 3.0, keys=('w',))           # идём в розовый маркер
    assert ms.active is not None and ms.active.spec['id'] == 'v1'
    assert pl.freeze                              # идёт брифинг
    for _ in range(8):                            # пролистываем реплики
        if not pl.freeze:
            break
        harness.run(game, 0.6)
        harness.press(game, 'enter')
    harness.run(game, 0.5)
    assert not pl.freeze
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
