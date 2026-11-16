# -*- coding: utf-8 -*-
"""Меню тестера (F9).  Оно есть только в сборке для тестера: в обычной игре модуль game.tester не подключён."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import harness
from game import missions as M
from game.city import WATER_Z
from game.collision import F_PED, F_CAR
from game.defs import WEAPONS, W_AK, W_BAT, W_PISTOL
from game.vehicle import SPECS

ALL_MISSIONS = list(M.MISSIONS) + [M.TAXI]


@pytest.fixture(scope='module')
def game():
    return harness.make_game(640, 360)


@pytest.fixture()
def tg(game):
    """Игра с подключённым меню тестера — как в сборке для тестера.  После проверки меню снимается."""
    from game.tester import Tester
    assert game.tester is None
    game.tester = Tester(game)
    random.seed(20261115)
    errors = game._errors_total                 # счётчик общий на весь прогон: сравниваем с началом проверки
    try:
        yield game
    finally:
        if game.tester is not None:
            game.tester.destroy()
        assert game.tester is None and not game.world.player.god and game.world.police.enabled
    assert game._errors_total == errors, 'за время проверки игра записала ошибку в журнал'


def start(g, story=False):
    w = harness.start_game(g, story=story)
    w.player.invincible = False
    return w, g.tester, w.player


def sane(g):
    """Игра в состоянии, в которое можно попасть и честной игрой: герой цел, управляется, стоит на суше.

    Возвращает True либо печатает, что именно не так (и возвращает False)."""
    w = g.world
    pl = w.player
    x, y = pl.pos()
    v = pl.vehicle
    checks = [
        ('игра идёт', g.state == 'play'),
        ('герой на ногах или за рулём', pl.state in ('foot', 'car')),
        ('герой жив', not pl.ped.dead),
        ('герой управляется', not pl.freeze and pl.controls),
        ('камера свободна', w.cam.override is None),
        ('нет возрождения', w.respawn_kind is None),
        ('нет перехода через дверь', w.interiors.trans is None),
        ('герой на суше', not w.city.in_water(x, y) and w.city.ground_z(x, y) > WATER_Z - 0.2),
        ('машина цела', v is None or not (v.dead or v.sunk)),
    ]
    wrong = [name for name, ok in checks if not ok]
    if wrong:
        print('не так: %s; состояние %s/%s, точка %.1f %.1f, задание %s' % (
            ', '.join(wrong), g.state, pl.state, x, y, w.missions.active and w.missions.active.spec['id']))
    return not wrong


def skip_talk(g, seconds=16.0):
    """Долистать вступление задания (звонок или разговор) пробелом."""
    w = g.world
    pl = w.player
    for i in range(int(seconds * 30)):
        if i % 6 == 0:
            g.inp._dn('space')
        else:
            g.inp._up('space')
        g.step(1.0 / 30.0)
        if i > 30 and not pl.freeze and w.cam.override is None and not w.hud.phone_on:
            break
    g.inp._up('space')


# ---------------------------------------------------------------------------
# обычная игра
# ---------------------------------------------------------------------------
def test_regular_game_has_no_tester_menu(game):
    import game as game_pkg
    assert game_pkg.TESTER is False
    assert game.tester is None
    w = harness.start_game(game)
    harness.press(game, 'f9')
    harness.run(game, 0.2)
    assert game.state == 'play' and not game.ui.stack
    assert w.player.god is False
    game.to_main_menu()
    assert 'тестер' not in game.ui.current().subtitle.lower()


def test_tester_switch_uses_its_own_user_folder(monkeypatch, tmp_path):
    """Сборка для тестера не должна затирать настройки и сохранение обычной игры."""
    import game as game_pkg
    import main
    from game import settings
    monkeypatch.delenv('DD_USER_DIR', raising=False)
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(game_pkg, 'TESTER', False)
    monkeypatch.setattr(settings, 'APP_NAME', settings.APP_NAME)
    monkeypatch.setattr(sys, 'platform', 'linux')
    usual = settings.user_dir()
    assert main.enable_tester() is True
    assert game_pkg.TESTER is True
    mine = settings.user_dir()
    assert os.path.basename(usual) == 'DeadlyDistrict' and os.path.basename(mine) == 'DeadlyDistrict-tester'
    assert settings.save_path(0).startswith(mine + os.sep)
    monkeypatch.setattr(sys, 'platform', 'win32')
    assert settings.user_dir() == os.path.join(str(tmp_path), 'DeadlyDistrict-tester')


# ---------------------------------------------------------------------------
# само меню
# ---------------------------------------------------------------------------
def test_f9_opens_and_closes_the_menu(tg):
    w, t, pl = start(tg)
    assert not t.opened
    harness.press(tg, 'f9')
    assert t.opened and tg.state == 'pause' and tg.ui.current().title == 'Тестер'
    x0, y0 = pl.pos()
    harness.run(tg, 0.5, keys=('w',))                    # игра стоит, пока меню открыто
    assert pl.pos() == (x0, y0)
    harness.press(tg, 'f9')
    assert not t.opened and tg.state == 'play' and not tg.ui.stack
    # Esc: из вложенного меню — на уровень выше, из главного — обратно в игру
    harness.press(tg, 'f9')
    harness.press(tg, 'enter')
    assert [m.title for m in tg.ui.stack] == ['Тестер', 'Задания']
    harness.press(tg, 'escape')
    assert [m.title for m in tg.ui.stack] == ['Тестер'] and t.opened
    harness.press(tg, 'escape')
    assert tg.state == 'play' and not t.opened and not tg.ui.stack
    # F9 из вложенного меню закрывает всё сразу
    harness.press(tg, 'f9')
    harness.press(tg, 'arrow_down')
    harness.press(tg, 'enter')
    harness.press(tg, 'enter')
    assert [m.title for m in tg.ui.stack] == ['Тестер', 'Телепорт', 'Комнаты']
    harness.press(tg, 'f9')
    assert tg.state == 'play' and not t.opened and not tg.ui.stack
    # в обычной паузе и в главном меню F9 ничего не открывает
    harness.press(tg, 'escape')
    assert tg.state == 'pause' and tg.ui.current().title == 'Пауза'
    harness.press(tg, 'f9')
    assert not t.opened and tg.ui.current().title == 'Пауза'
    harness.press(tg, 'escape')
    assert tg.state == 'play'
    tg.to_main_menu()
    harness.press(tg, 'f9')
    assert not t.opened and tg.state == 'menu'
    assert 'сборка для тестера' in tg.ui.current().subtitle
    assert 'СБОРКА ДЛЯ ТЕСТЕРА' in t.status()


def test_menu_is_not_offered_during_the_prologue(tg):
    tg.new_game()
    w = tg.world
    t = tg.tester
    harness.run(tg, 0.5)
    assert w.missions.intro is not None
    harness.press(tg, 'f9')
    assert not t.opened and tg.state == 'play' and w.missions.intro is not None
    harness.start_game(tg)
    harness.press(tg, 'f9')
    assert t.opened
    harness.press(tg, 'f9')


def test_every_menu_row_works(tg):
    """Пройти клавишами по всем строкам главного меню: каждая что-то делает и ничего не роняет."""
    w, t, pl = start(tg)
    harness.press(tg, 'f9')
    main = tg.ui.current()
    titles = [it.label for it in main.items]
    assert titles == ['Задания', 'Телепорт', 'Транспорт', 'Розыск', 'Удерживать розыск', 'Бессмертие',
                      'Здоровье и броня', 'Всё оружие и патроны', 'Деньги', 'Время', 'Погода', 'Строка сведений']
    subs = {'Задания': 3 + len(ALL_MISSIONS), 'Телепорт': 2 + len(t.places()), 'Транспорт': 1 + len(SPECS)}
    for i, title in enumerate(titles):
        main.sel = i
        before = t.note
        if title in subs:
            harness.press(tg, 'enter')
            sub = tg.ui.current()
            assert sub.title == title and len(sub.items) == subs[title]
            assert all(it.label for it in sub.items)
            harness.press(tg, 'escape')
            assert tg.ui.current() is main
            continue
        it = main.items[i]
        if it.change is not None:
            v0 = it.value()
            harness.press(tg, 'arrow_right')
            assert it.value() != v0, title
            harness.press(tg, 'arrow_left')
            assert it.value() == v0, title
        else:
            harness.press(tg, 'enter')
        assert t.note and t.note != before, title
        assert t.note in main.subtitle                  # что сделано, написано внизу меню
        assert t.opened, title
    harness.press(tg, 'f9')
    harness.run(tg, 0.5)
    assert sane(tg)


def test_failed_action_does_not_close_the_game(game, monkeypatch):
    """Сбой в действии меню записывается в журнал и показывается тестеру; игра идёт дальше."""
    from game.tester import Tester
    t = Tester(game)
    game.tester = t
    try:
        w = harness.start_game(game)
        errors = game._errors_total

        def broken():
            raise RuntimeError('сломалось')

        def broken_after_close():
            t.close()
            raise RuntimeError('сломалось позже')
        monkeypatch.setattr(t, 'heal', broken)
        monkeypatch.setattr(t, 'arm', broken_after_close)
        harness.press(game, 'f9')
        main = game.ui.current()
        main.sel = [it.label for it in main.items].index('Здоровье и броня')
        harness.press(game, 'enter')
        assert game._errors_total == errors + 1
        assert t.opened and 'ошибка: сломалось' in main.subtitle
        # то же, если действие успело закрыть меню
        main.sel = [it.label for it in main.items].index('Всё оружие и патроны')
        harness.press(game, 'enter')
        assert game._errors_total == errors + 2
        assert game.state == 'play' and not t.opened
        harness.run(game, 0.5)
        assert sane(game)
        harness.press(game, 'f9')
        assert t.opened                                   # меню открывается снова
        harness.press(game, 'f9')
    finally:
        t.destroy()


def test_status_line(tg):
    w, t, pl = start(tg)
    harness.run(tg, 0.5)
    s = t.line.getText()
    x, y = pl.pos()
    assert s.startswith('ТЕСТЕР ') and ('x %.0f  y %.0f' % (x, y)) in s and 'F9' in s
    assert w.city.zone_name(x, y) in s
    t.open()
    t.spawn('sports')
    t.open()
    t.set_god(True)
    t.set_wanted(2)
    t.set_hold(True)
    t.start_mission(M.TAXI)
    harness.run(tg, 0.5)
    s = t.line.getText()
    assert '(taxi)' in s and 'задание taxi' in s and 'бессмертие' in s and 'розыск удержан' in s
    t.open()
    t.go_room(w.interiors.rooms['safehouse'])
    assert t.note.startswith('нельзя')                   # с розыском в двери не пускают — как в игре
    t.set_hold(False)
    t.set_wanted(0)
    t.cancel_mission()
    t.open()
    t.go_room(w.interiors.rooms['safehouse'])
    harness.run(tg, 0.5)
    assert w.interiors.rooms['safehouse'].title in t.line.getText()
    t.open()
    t.set_info(False)
    t.close()
    harness.run(tg, 0.5)
    assert t.line.getText() == ''
    t.set_info(True)


# ---------------------------------------------------------------------------
# розыск
# ---------------------------------------------------------------------------
def test_wanted_level(tg):
    w, t, pl = start(tg)
    pol = w.police
    t.open()
    for lv in range(7):
        t.set_wanted(lv)
        assert pol.level == lv
    t.set_wanted_by(1)
    assert pol.level == 6                                 # выше шести не бывает
    t.set_wanted(0)
    t.set_wanted_by(-1)
    assert pol.level == 0
    t.set_wanted(3)
    t.close()
    harness.run(tg, 6.0)
    assert pol.level == 3 and pol.units, 'за героем должна выехать погоня'
    # без удержания розыск живёт сам: новое преступление его поднимает
    for _ in range(6):
        pol.crime('kill_cop', *pl.pos())
    assert pol.level > 3
    t.open()
    t.set_wanted(0)
    t.close()
    harness.run(tg, 1.0)
    assert pol.level == 0 and pol.heat == 0.0


def test_hold_wanted_level(tg):
    w, t, pl = start(tg)
    pol = w.police
    t.open()
    t.set_wanted(2)
    t.set_hold(True)
    t.close()
    for _ in range(6):
        pol.crime('kill_cop', *pl.pos())
    harness.run(tg, 0.5)
    assert pol.level == 2
    pol.cool_t = 1e4                                      # героя давно не видят: розыск спал бы сам
    harness.run(tg, 1.0)
    assert pol.level == 2
    pol.set_level(5)                                      # так розыск поднимают сценарии заданий
    harness.run(tg, 0.2)
    assert pol.level == 2
    # удержание на нуле: полиции нет, что бы герой ни делал
    t.open()
    t.set_wanted(0)
    t.close()
    for _ in range(6):
        pol.crime('kill_cop', *pl.pos())
    harness.run(tg, 1.0)
    assert pol.level == 0 and t.hold
    t.open()
    t.set_hold(False)
    t.close()
    harness.run(tg, 0.2)
    pol.crime('kill_cop', *pl.pos())
    assert pol.level >= 2 and pol.enabled


# ---------------------------------------------------------------------------
# бессмертие
# ---------------------------------------------------------------------------
def test_god_mode_blocks_damage(tg):
    w, t, pl = start(tg)
    p = pl.ped
    harness.quiet(w, peds=True)
    p.health = 35.0
    t.open()
    t.set_god(True)
    t.close()
    assert p.health == p.max_health                      # включение заодно лечит
    for cause in ('bullet', 'melee', 'explosion', 'fire', 'fall', 'car'):
        p.hurt(500.0, None, cause)
    p.die('bullet')
    harness.run(tg, 0.5)
    assert p.health == p.max_health and not p.dead and sane(tg)
    # машина, в которой сидит бессмертный, не ломается; стоит выйти — снова обычная
    t.open()
    v = t._spawn('sedan')
    t.close()
    harness.run(tg, 0.2)
    assert v.immune
    v.damage(5000.0, True, 'explosion')
    v.damage(300.0, False, 'hit')
    harness.run(tg, 0.2)
    assert not v.dead and v.health == v.max_health
    pl.leave_vehicle(force=True)
    harness.run(tg, 0.2)
    assert not v.immune
    pl.enter_vehicle(v, silent=True)
    harness.run(tg, 0.2)
    assert v.immune
    # горящая машина под бессмертным гаснет, а не взрывается
    pl.leave_vehicle(force=True)
    harness.run(tg, 0.2)
    v.health = v.max_health * 0.05
    harness.run(tg, 1.0)
    assert v.burn_t > 0.5
    pl.enter_vehicle(v, silent=True)
    harness.run(tg, 8.0)
    assert not v.dead and pl.vehicle is v and v.burn_t == 0.0
    # выключили — урон снова проходит
    t.open()
    t.set_god(False)
    t.close()
    harness.run(tg, 0.2)
    assert not v.immune and not pl.god
    pl.leave_vehicle(force=True)
    p.hurt(30.0, None, 'bullet')
    assert p.health == p.max_health - 30.0
    p.hurt(500.0, None, 'bullet')
    assert p.dead


def _beach_water(w):
    """Точка на пляже у самой воды: (x, y суши, y воды)."""
    c = w.city
    b = c.special['beach']
    x = (b['x0'] + b['x1']) * 0.5
    y = b['y0']
    while not c.in_water(x, y):
        y -= 2.0
        assert y > b['y0'] - 300.0
    return x, y + 6.0, y


def test_god_mode_survives_water(tg):
    w, t, pl = start(tg)
    c = w.city
    harness.quiet(w, peds=True)
    x, y_land, y_water = _beach_water(w)
    # без бессмертия герой в воде тонет
    pl.teleport(x, y_land, -math.pi / 2)
    w.cam.yaw = -math.pi / 2
    harness.run(tg, 4.0, keys=('w',))
    assert pl.ped.dead or w.respawn_kind is not None
    # с бессмертием его возвращают на берег
    w, t, pl = start(tg)
    harness.quiet(w, peds=True)
    t.open()
    t.set_god(True)
    t.close()
    pl.teleport(x, y_land, -math.pi / 2)
    w.cam.yaw = -math.pi / 2
    harness.run(tg, 4.0, keys=('w',))
    assert sane(tg) and pl.ped.health == pl.ped.max_health
    assert math.hypot(pl.pos()[0] - x, pl.pos()[1] - y_water) < 120.0     # вернули рядом, а не через весь город
    # то же на машине: её ставят обратно на дорогу вместе с героем
    t.open()
    v = t._spawn('sedan')
    t.close()
    t._put_vehicle(v, x, y_land + 20.0, -math.pi / 2)
    harness.run(tg, 6.0, keys=('w',))
    assert pl.vehicle is v and not v.sunk and not v.dead and sane(tg)
    assert c.on_road(v.x, v.y)


def test_god_mode_blocks_arrest(tg):
    w, t, pl = start(tg)
    pol = w.police
    harness.quiet(w, peds=True)
    x, y = pl.pos()

    def cop_next_to_hero():
        from game.defs import cop_look
        cop = w.spawn_ped(x + 0.8, y, math.pi, cop_look(random), 'cop')
        cop.keep = True
        pol.cops.append(cop)
        return cop
    # без бессмертия героя, стоящего рядом с полицейским, арестовывают
    pol.set_level(1)
    cop_next_to_hero()
    harness.run(tg, 3.0)
    assert pl.state == 'busted' or w.respawn_kind == 'busted'
    w, t, pl = start(tg)
    pol = w.police
    harness.quiet(w, peds=True)
    x, y = pl.pos()
    t.open()
    t.set_god(True)
    t.set_wanted(1)
    t.set_hold(True)
    t.close()
    cop_next_to_hero()
    harness.run(tg, 4.0)
    assert pl.state == 'foot' and w.respawn_kind is None and pol.level == 1
    assert pl.ped.health == pl.ped.max_health


def test_new_game_keeps_god_mode_and_drops_the_hold(tg):
    w, t, pl = start(tg)
    t.open()
    t.set_god(True)
    t.set_wanted(4)
    t.set_hold(True)
    v = t._spawn('sedan')
    t.close()
    harness.run(tg, 0.3)
    assert v.immune and w.police.level == 4
    w, t, pl = start(tg)
    harness.run(tg, 0.5)
    assert w.police.level == 0 and not t.hold and w.police.enabled, 'новая игра начинается без розыска'
    assert t.god and pl.god, 'бессмертие остаётся, пока его не выключат'
    assert t._last is None and t._immune is None
    pl.ped.hurt(50.0, None, 'bullet')
    assert pl.ped.health == pl.ped.max_health


# ---------------------------------------------------------------------------
# герой и мир
# ---------------------------------------------------------------------------
def test_health_weapons_money_time_weather(tg):
    w, t, pl = start(tg)
    p = pl.ped
    p.health = 12.0
    p.armor = 0.0
    t.open()
    t.heal()
    assert p.health == p.max_health and p.armor == 100.0
    t.arm()
    assert len(pl.ammo) == len(WEAPONS)
    assert pl.ammo[W_AK] == 9999 and pl.ammo[W_PISTOL] == 9999 and pl.ammo[W_BAT] == -1
    m0 = pl.money
    t.cash(10000)
    t.cash(10000)
    t.cash(-10000)
    assert pl.money == m0 + 10000
    sky = w.sky
    t.shift_time(1)
    h = sky.hour
    assert h == int(h)
    t.shift_time(1)
    assert sky.hour == (h + 1) % 24
    for _ in range(24):
        t.shift_time(-1)
    assert sky.hour == (h + 1) % 24                     # сутки по кругу
    seen = set()
    for _ in range(8):
        t.shift_weather(1)
        seen.add(sky.weather)
    assert len(seen) >= 3 and 'rain' in seen
    t.close()
    for wp in WEAPONS:                                   # каждое выданное оружие берётся в руки
        pl.select(wp.id)
        harness.run(tg, 0.1)
        assert pl.weapon_id == wp.id
    assert sane(tg)


# ---------------------------------------------------------------------------
# телепорт
# ---------------------------------------------------------------------------
def test_teleport_places_on_foot(tg):
    w, t, pl = start(tg)
    c = w.city
    places = t.places()
    assert len(places) >= 26
    assert len(set(p[0] for p in places)) == len(places)
    for title, foot, car in places:
        assert t.open(), title
        t.go(title, foot, car)
        assert tg.state == 'play' and not t.opened, title
        x0, y0 = pl.pos()
        assert math.hypot(x0 - foot[0], y0 - foot[1]) < 2.5, title
        assert not w.static.overlap_circle(x0, y0, pl.ped.radius, F_PED), title
        harness.run(tg, 0.7)
        x1, y1 = pl.pos()
        assert math.hypot(x1 - x0, y1 - y0) < 0.6, '%s: героя сдвинуло' % title
        assert sane(tg), title
        assert w.interiors.current is None, '%s: герой попал в дверь' % title
        assert harness.reachable(w, x1, y1), '%s: отсюда не выйти к дороге' % title


def test_teleport_places_by_car(tg):
    w, t, pl = start(tg)
    c = w.city
    t.open()
    t.spawn('sedan')
    v = pl.vehicle
    assert v is not None
    for title, foot, car in t.places():
        assert t.open(), title
        t.go(title, foot, car)
        assert tg.state == 'play' and pl.vehicle is v, title
        x0, y0 = v.x, v.y
        assert math.hypot(x0 - car[0], y0 - car[1]) < 62.0, title
        assert not w.static.overlap_circle(x0, y0, v.spec.W * 0.5, F_CAR), '%s: машина в стене' % title
        harness.run(tg, 0.7)
        assert math.hypot(v.x - x0, v.y - y0) < 1.5, '%s: машину сдвинуло' % title
        assert v.health == v.max_health, '%s: машина побилась' % title
        assert sane(tg), title
        assert harness.reachable(w, v.x, v.y, car=True), '%s: отсюда не выехать' % title


def test_teleport_into_every_room_and_back(tg):
    w, t, pl = start(tg)
    its = w.interiors
    assert len(its.order) == 12
    title, foot, car = t.places()[0]
    for room in its.order:
        assert t.open(), room.name
        t.go_room(room)
        harness.run(tg, 0.5)
        assert its.current is room and pl.indoors and sane(tg), room.name
        assert w.citymesh.root.isHidden(), room.name
        assert not w.static.overlap_circle(pl.pos()[0], pl.pos()[1], pl.ped.radius, F_PED), room.name
        assert t.open(), room.name
        t.go(title, foot, car)                           # из комнаты — сразу на улицу
        harness.run(tg, 0.5)
        assert its.current is None and not pl.indoors and not w.citymesh.root.isHidden(), room.name
        assert sane(tg), room.name
    # из комнаты можно поставить машину: героя выводят на улицу
    t.open()
    t.go_room(its.order[0])
    harness.run(tg, 0.3)
    t.open()
    t.spawn('sedan')
    assert t.note.startswith('в помещении') and t.opened and pl.vehicle is None
    t.close()


# ---------------------------------------------------------------------------
# транспорт
# ---------------------------------------------------------------------------
def test_spawn_every_vehicle(tg):
    w, t, pl = start(tg)
    harness.quiet(w)
    assert len(SPECS) == 44
    for kind in SPECS:
        assert t.open(), kind
        t.spawn(kind)
        assert tg.state == 'play', '%s: %s' % (kind, t.note)
        harness.run(tg, 0.4)
        v = pl.vehicle
        assert v is not None and v.kind == kind and pl.state == 'car', kind
        assert not w.static.overlap_circle(v.x, v.y, v.spec.W * 0.5, F_CAR), kind
        assert v.health == v.max_health and not v.dead, kind
        assert sane(tg), kind
    # каждая новая машина заменяет прежнюю, поставленную из меню: улица ими не забивается
    street = [o for o in w.vehicles if not o.removed and getattr(o, 'room', None) is None]
    assert street == [pl.vehicle]
    # машина, из которой герой вышел, остаётся; новая встаёт рядом, не в неё
    v1 = pl.vehicle
    pl.leave_vehicle(force=True)
    harness.run(tg, 0.3)
    t.open()
    t.spawn('sports')
    harness.run(tg, 0.5)
    v2 = pl.vehicle
    assert v2 is not v1 and v2.kind == 'sports' and not v1.removed
    assert math.hypot(v1.x - v2.x, v1.y - v2.y) > 4.0
    assert v1.health == v1.max_health and v2.health == v2.max_health
    # починка
    v2.health = 40.0
    t.open()
    t.repair()
    assert v2.health == v2.max_health
    t.close()


def test_spawned_car_is_not_a_theft(tg):
    w, t, pl = start(tg)
    harness.quiet(w, peds=True)
    t.open()
    t.spawn('police')
    harness.run(tg, 3.0, keys=('w',))
    assert w.police.level == 0, 'за машину из меню розыск не дают'
    assert sane(tg)


# ---------------------------------------------------------------------------
# задания
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('spec', ALL_MISSIONS, ids=[s['id'] for s in ALL_MISSIONS])
def test_mission_start_cancel_pass(tg, spec):
    w, t, pl = start(tg, story=True)
    ms = w.missions
    its = w.interiors
    mid = spec['id']
    # начать можно и сидя за рулём, и посреди другого задания
    t.open()
    t.spawn('sedan')
    harness.run(tg, 0.3)
    t.open()
    t.start_mission(spec)
    assert tg.state == 'play' and ms.active is not None and ms.active.spec is spec, t.note
    if mid != 'taxi':
        need = t._before(mid)
        assert need <= ms.done and mid not in ms.done
        assert all(set(s['req']) <= ms.done for s in M.MISSIONS if s['id'] in ms.done), 'цепочка заданий цела'
    harness.run(tg, 1.2)                                  # идёт вступление: звонок или разговор у заказчика
    assert ms.active is not None and ms.active.spec is spec
    if spec.get('contact'):
        assert its.current is its.rooms[spec['contact']] and pl.state == 'foot'
    # отмена посреди вступления: герой снова управляется
    t.open()
    t.cancel_mission()
    harness.run(tg, 1.0)
    assert ms.active is None and mid not in ms.done and sane(tg)
    # заново: вступление, цель, перенос к цели, зачёт
    t.open()
    t.start_mission(spec)
    if mid != 'taxi':
        skip_talk(tg)
    harness.run(tg, 0.5)
    assert ms.active is not None and ms.active.spec is spec and sane(tg)
    if t.target() is not None:
        (tx, ty), obj, need_foot = t.target()
        t.open()
        t.set_god(True)                                  # цель бывает вооружённой охраной: без бессмертия туда рано
        t.to_target()
        assert tg.state == 'play', t.note
        x, y = pl.pos()
        assert math.hypot(x - tx, y - ty) < 20.0
        harness.run(tg, 1.0)
        assert sane(tg)
        assert ms.active is not None and ms.active.spec is spec, 'перенос к цели задание не срывает'
    money = pl.money
    t.open()
    t.pass_mission()
    harness.run(tg, 1.5)
    assert ms.active is None
    if mid == 'taxi':
        assert 'taxi' not in ms.done                      # подработку нельзя пройти, только закончить смену
        assert pl.money == money
    else:
        assert mid in ms.done and pl.money == money + spec['reward']
    if mid == 'p4':
        # после последнего задания — титры, как в игре
        harness.run(tg, 12.0)
        assert tg.state == 'pause' and tg.ui.current().title == 'Финал'
        harness.press(tg, 'escape')
    assert sane(tg)


def test_replaying_an_earlier_mission_rewinds_later_ones(tg):
    w, t, pl = start(tg, story=True)
    ms = w.missions
    by_id = dict((s['id'], s) for s in M.MISSIONS)
    t.open()
    t.start_mission(by_id['p4'])
    assert ms.done == set(by_id) - set(['p4'])
    t.open()
    t.start_mission(by_id['g3'])
    assert 'g3' not in ms.done and 'p4' not in ms.done and 'g2' in ms.done and 'z3' in ms.done
    assert w.interiors.resident('zakhar') is not None, 'до «Облавы» Захар у себя'
    t.open()
    t.pass_mission()
    harness.run(tg, 1.0)
    assert 'g3' in ms.done and w.interiors.resident('zakhar') is None, 'после «Облавы» Захара в городе нет'
    # «Улов»: всё, что от него зависит, снова не пройдено; остальное не тронуто
    t.open()
    t.start_mission(by_id['z1'])
    assert ms.done == set(['s1', 's2', 'v1', 'v2', 'v3', 'v4', 'r1', 'r2', 'r3', 'r4'])
    assert w.interiors.resident('zakhar') is not None
    t.open()
    t.cancel_mission()
    # сюжет: отменённое задание Брюс предложит снова, но не сразу
    t.open()
    t.start_mission(by_id['s1'])
    assert ms.done == set()
    t.open()
    t.cancel_mission()
    harness.run(tg, 20.0)
    assert ms.active is None and ms.call_t > 500.0
    assert sane(tg)
