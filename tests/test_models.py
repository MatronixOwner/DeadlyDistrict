# -*- coding: utf-8 -*-
"""Готовые модели: всё загружается, подогнано под игровые габариты, анимация следует за состоянием."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import harness
from game import missions as M
from game.defs import (W_PISTOL, W_BAT, W_AK, W_FIST, WEAPONS, random_look, cop_look, swat_look, army_look,
                       fbi_look, gang_look, medic_look, player_look)
from game.models import VEHICLE_MODELS, WEAPON_MODELS, CHAR_ROLES
from game.vehicle import SPECS

DT = 1.0 / 30.0


@pytest.fixture(scope='module')
def game():
    return harness.make_game(640, 360)


@pytest.fixture()
def world(game):
    random.seed(77)
    w = harness.start_game(game)
    harness.quiet(w, peds=True)
    return w


def test_models_are_available(world):
    m = world.models
    assert m.ok and m.chars_ok
    assert set(CHAR_ROLES) == set(m.meta['chars'])              # для каждой модели описано, что перекрашивать
    for sex in 'mf':
        for clip in ('Idle', 'Walk', 'Run', 'Punch_Right', 'Sword_Slash', 'Idle_Gun', 'Idle_Gun_Pointing',
                     'Idle_Gun_Shoot', 'Run_Shoot', 'HitRecieve', 'Death'):
            assert clip in m.meta['anims'][sex], (sex, clip)
            assert os.path.isfile(os.path.join(m.dir, 'anims', '%s_%s.bam' % (sex, clip)))


@pytest.mark.parametrize('kind', sorted(SPECS))
def test_vehicle_model_fits_its_spec(world, kind):
    """Модель подогнана под те габариты, по которым машина сталкивается и ездит."""
    w = world
    spec = SPECS[kind]
    assert kind in VEHICLE_MODELS
    x, y = w.city.landmarks['safehouse']['road']
    v = w.spawn_vehicle(kind, x, y - 1.5, 0.0)
    assert v.minfo is not None, 'нет модели для %s' % kind
    mn, mx = v.body.getTightBounds(v.tilt)
    assert abs((mx.y - mn.y) - spec.L) < 0.05 * spec.L           # длина — вдоль +Y
    assert (mx.x - mn.x) <= spec.W * 1.02                         # кузов не шире зоны столкновений
    assert len(v.wheels) == 4
    fl, fr, rl, rr = [piv.getPos() for piv, _ in v.wheels]
    assert fl.x < 0 < fr.x and rl.x < 0 < rr.x                    # левые слева, правые справа
    assert fl.y > 0 > rl.y and fr.y > 0 > rr.y                    # передние впереди
    assert abs(fl.z - v.wheel_r_vis) < 1e-3                        # колёса стоят на земле
    # перекраска и «обгоревший» кузов не падают
    v.set_paint(v.paint + 1)
    v.set_lights(True)
    v.set_brake_light(True)
    v.explode(False)
    harness.run(harness._game[0], 0.2)
    assert v.dead


@pytest.mark.parametrize('name,look,kind,expect', [
    ('player', player_look(), 'civ', 'm_jacket'),
    ('cop', cop_look(), 'cop', 'm_suit'),
    ('swat', swat_look(), 'swat', 'm_swat'),
    ('army', army_look(), 'army', 'm_swat'),
    ('fbi', fbi_look(), 'fbi', 'm_suit'),
    ('mafia', gang_look('mafia'), 'gang', 'm_suit'),
    ('vano', M.contact_look('vano'), 'mission', 'm_beach'),
    ('rosa', M.contact_look('rosa'), 'mission', 'f_formal'),
    ('prof', M.contact_look('prof'), 'mission', 'm_suit'),
])
def test_character_model_choice(world, name, look, kind, expect):
    w = world
    x, y = w.city.landmarks['safehouse']['door']
    p = w.spawn_ped(x + 3.0, y, 0.0, look, kind)
    assert p.vis is not None and p.vis.key == expect
    w.remove_ped(p)
    assert p.vis is None


def test_every_zone_look_gets_a_model(world):
    w = world
    rnd = random.Random(9)
    x, y = w.city.landmarks['safehouse']['door']
    keys = set()
    for zone in 'DOGRIBP':
        for _ in range(40):
            p = w.spawn_ped(x + 3.0, y, 0.0, random_look(rnd, zone), 'civ')
            assert p.vis is not None
            keys.add(p.vis.key)
            w.remove_ped(p)
    assert len(keys) >= 10                                        # на улицах — разные люди
    assert {k[0] for k in keys} == {'m', 'f'}


def test_animation_follows_state(game, world):
    w = world
    x, y = w.city.landmarks['safehouse']['road']
    p = w.spawn_ped(x + 4.0, y - 3.0, 0.0, random_look(random.Random(3), 'D'), 'civ')
    p.keep = True
    p.set_state('stand')
    harness.run(game, 0.3)
    assert p.vis.cur == 'Idle'
    # идёт
    p.set_state('goto')
    p.tx, p.ty, p.timer = p.x + 60.0, p.y, 0.0
    harness.run(game, 0.5)
    assert p.vis.cur == 'Walk'
    # бежит
    p.timer = 5.0
    harness.run(game, 0.6)
    assert p.vis.cur == 'Run'
    # сбит с ног, потом встаёт
    p.knock_down(1.0)
    harness.run(game, 0.3)
    assert p.vis.cur == 'Death'
    p.target = None
    harness.run(game, 1.5)
    assert p.state != 'down' and p.vis.cur != 'Death'
    # вооружён и целится
    p.set_state('stand')
    p.set_weapon(W_PISTOL)
    assert p.vis.gun is not None
    p.aiming = True
    harness.run(game, 0.4)
    assert p.vis.cur == 'Idle_Gun_Pointing'
    p.aiming = False
    harness.run(game, 0.4)
    assert p.vis.cur == 'Idle_Gun'
    # удар
    p.set_weapon(W_FIST)
    assert p.vis.gun is None
    p.punch_t = 0.3
    harness.run(game, 0.1)
    assert p.vis.cur == 'Punch_Right'
    p.set_weapon(W_BAT)
    harness.run(game, 0.5)
    p.punch_t = 0.3
    harness.run(game, 0.1)
    assert p.vis.cur == 'Sword_Slash'
    # убит
    p.hurt(500.0, None, 'bullet')
    harness.run(game, 0.3)
    assert p.dead and p.vis.cur == 'Death'


def test_weapons_have_models(world):
    m = world.models
    for wid in WEAPON_MODELS:
        t = m.weapon(wid)
        assert t is not None and not t.isEmpty(), WEAPONS[wid].name
        mn, mx = t.getTightBounds()
        assert 0.08 < (mx - mn).length() < 1.6                    # размеры — в метрах, не «в попугаях»


def test_player_keeps_model_through_respawn(game, world):
    w = world
    pl = w.player
    assert pl.ped.vis is not None and pl.ped.vis.key == 'm_jacket'
    pl.give_weapon(W_AK, 30)
    assert pl.ped.vis.gun is not None
    pl.ped.hurt(500.0, None, 'bullet')
    harness.run(game, 7.0)
    assert pl.state == 'foot' and pl.ped.vis.cur != 'Death'


def test_animation_runs_on_game_time(game, world):
    """Клипы идут по игровому времени: на паузе персонажи замирают, а не шагают на месте."""
    w = world
    x, y = w.city.landmarks['safehouse']['road']
    p = w.spawn_ped(x + 4.0, y - 3.0, 0.0, random_look(random.Random(4), 'D'), 'civ')
    p.keep = True
    p.set_state('goto')
    p.tx, p.ty, p.timer = p.x + 80.0, p.y, 0.0
    harness.run(game, 0.5)
    frames = set()
    for _ in range(12):
        game.step(DT)
        frames.add(p.vis.frame)
    assert len(frames) > 6                                   # кадры клипа сменяются
    game.pause()
    t0, f0 = p.vis.time, p.vis.frame
    harness.run(game, 0.5)
    assert (p.vis.time, p.vis.frame) == (t0, f0)
    game.resume()
    harness.run(game, 0.2)
    assert p.vis.time != t0
