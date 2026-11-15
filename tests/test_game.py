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
    lm = world.city.landmarks['safehouse']
    pl.teleport(lm['door'][0] + 4.0, lm['door'][1] - 3.0)
    world.cam.yaw = math.pi / 2
    harness.run(game, 6.0, keys=('w', 'shift'))
    assert pl.pos()[1] < lm['rect'][1] + 0.1
    assert world.interiors.current is None


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
    """После пролога (досмотренного или пропущенного) игра в рабочем состоянии: герой проснулся у себя."""
    ms = w.missions
    pl = w.player
    assert ms.intro is None and g.state == 'play' and not g.ui.active
    assert w.interiors.current is not None and w.interiors.current.name == 'safehouse'
    assert not pl.freeze and pl.script_move is None and pl.ped.act is None and not pl.invincible
    assert not pl.ped.node.isHidden() and abs(pl.ped.z) < 0.05
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


def test_intro_plays_to_the_end(game):
    """Пролог без единого нажатия: автобус, остановка, звонок, комната — и игра начинается."""
    g = game
    random.seed(7)
    errors = g._errors_total
    g.new_game()
    w = g.world
    ms = w.missions
    pl = w.player
    assert ms.intro is not None and pl.freeze
    lines = []
    seen = dict(bus=False, hidden=False, walked=False, phone=False, room=False, bed=False, paused=False)
    t = 0.0
    while ms.intro is not None and t < 120.0:
        g.step(DT)
        t += DT
        text = w.hud.sub_text.getText()
        if text and (not lines or lines[-1] != text):
            lines.append(text)
        it = ms.intro
        if it is None:
            break
        seen['bus'] |= it['bus'] is not None and abs(it['bus'].speed) > 5.0
        seen['hidden'] |= pl.ped.node.isHidden()
        seen['walked'] |= pl.script_move is not None and pl.ped.speed > 0.5
        seen['phone'] |= pl.ped.act is not None and pl.ped.act[0] == 'phone'
        seen['room'] |= w.interiors.current is not None
        seen['bed'] |= pl.ped.act is not None and pl.ped.act[0] == 'sleep' and pl.ped.z > 0.3
        seen['paused'] |= g.state != 'play'
        assert pl.freeze and not w.hud.visible
        assert w.police.level == 0 and pl.ped.health == 100
    assert 40.0 < t < 90.0, t
    assert len(lines) >= 8 and lines[0].startswith('Порт-Глухов')
    assert any(s.startswith('Вано:') for s in lines) and any(s.startswith('Макс:') for s in lines)
    assert seen == dict(bus=True, hidden=True, walked=True, phone=True, room=True, bed=True, paused=False), seen
    _after_intro(g, w, errors)


@pytest.mark.parametrize('when', [0.1, 3.0, 9.0, 18.0, 25.5, 33.0, 46.0, 53.0, 59.0])
def test_intro_can_be_skipped_any_time(game, when):
    """Esc в любой момент пролога: декорации убраны, герой дома, пауза не открылась."""
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
    """Enter листает кадры пролога: за десяток-другой нажатий он заканчивается."""
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
    assert 6 <= n < 30, n
    harness.run(g, 0.3)
    _after_intro(g, w, errors)


def test_first_hints_lead_out_of_the_room(game):
    """После пролога подсказки: сначала про комнату и выход, на улице — куда идти."""
    g = game
    random.seed(17)
    g.new_game()
    w = g.world
    ms = w.missions
    said = []
    orig = w.hud.help
    w.hud.help = lambda text, dur=6.0: (said.append(text), orig(text, dur))[1]
    try:
        harness.run(g, 1.0)
        harness.press(g, 'escape')
        harness.run(g, 4.0)
        assert len(said) == 1 and 'комната' in said[0] and 'стрелк' in said[0]
        w.interiors.leave(instant=True)
        harness.quiet(w, peds=True)
        harness.run(g, 14.0)
        assert len(said) == 2 and 'Вано' in said[1]
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
    w = harness.start_game(g, street=False)
    _after_intro(g, w, errors)
