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
                       fbi_look, gang_look, medic_look, player_look, make_look)
from game.models import VEHICLE_MODELS, WEAPON_MODELS
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
    for key, info in m.meta['chars'].items():
        for tex in m.char_textures(key):
            assert os.path.isfile(os.path.join(m.dir, 'chars', tex + '.png')), key
        assert os.path.isfile(os.path.join(m.dir, 'chars', info['model'] + '.bam')), key
    # в игре про город нет персонажей из фильмов ужасов
    assert not [k for k in m.meta['chars'] if 'thug' in k or 'killer' in k or 'monster' in k]
    for clip in ('idle', 'walk', 'walk_f', 'jog', 'sprint', 'run_f', 'punch_a', 'punch_b', 'swing', 'pistol_idle',
                 'pistol_aim', 'pistol_shoot', 'rifle_idle', 'rifle_fire', 'rifle_walk', 'rifle_run', 'throw',
                 'hit_a', 'death_a', 'death_b', 'death_c', 'getup', 'talk', 'listen', 'cower', 'air'):
        assert clip in m.meta['anims'], clip
        assert os.path.isfile(os.path.join(m.dir, 'anims', clip + '.bam'))


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
    assert (mx.x - mn.x) <= spec.W * 1.25                         # за зону столкновений торчат только зеркала
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
    ('player', player_look(), 'civ', ('hero',)),
    ('cop', cop_look(), 'cop', ('cop_m', 'cop_f')),
    ('swat', swat_look(), 'swat', ('swat',)),
    ('army', army_look(), 'army', ('army',)),
    ('fbi', fbi_look(), 'fbi', ('m_shirt_c',)),
    ('medic', medic_look(), 'civ', ('medic',)),
    ('mafia', gang_look('mafia'), 'gang', ('m_leather', 'm_leather_b', 'm_leather_c', 'm_shirt_h3b')),
    ('vano', M.contact_look('vano'), 'mission', ('m_red_h3',)),
    ('rosa', M.contact_look('rosa'), 'mission', ('f_goth',)),
    ('prof', M.contact_look('prof'), 'mission', ('m_old',)),
])
def test_character_model_choice(world, name, look, kind, expect):
    w = world
    x, y = w.city.landmarks['safehouse']['door']
    p = w.spawn_ped(x + 3.0, y, 0.0, look, kind)
    assert p.vis is not None and p.vis.key in expect
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
    assert 'hero' not in keys                                     # облик героя — только у героя
    # и его лицо тоже: голова «m_red» больше никому не достаётся
    assert not [k for k in w.models.meta['chars'] if k != 'hero' and w.models.meta['chars'][k].get('head_tex') == 'm_red']
    assert 'm_red' not in w.models.meta['chars']


def test_animation_follows_state(game, world):
    w = world
    x, y = w.city.landmarks['safehouse']['road']
    p = w.spawn_ped(x + 4.0, y - 3.0, 0.0, make_look(model='m_grey_h2'), 'mission')
    p.keep = True
    p.set_state('stand')
    harness.run(game, 0.3)
    assert p.vis.cur == 'idle'
    # идёт
    p.set_state('goto')
    p.tx, p.ty, p.timer = p.x + 60.0, p.y, 0.0
    harness.run(game, 0.5)
    assert p.vis.cur == 'walk'
    # бежит
    p.timer = 5.0
    harness.run(game, 0.6)
    assert p.vis.cur in ('jog', 'sprint')
    # сбит с ног, потом встаёт
    p.knock_down(1.0)
    harness.run(game, 0.3)
    assert p.vis.cur in ('death_a', 'death_b', 'death_c')
    p.target = None
    harness.run(game, 1.2)
    assert p.state != 'down' and not p.vis.cur.startswith('death')
    # пистолет: в руке, прицеливание, выстрел
    p.set_state('stand')
    harness.run(game, 1.0)
    p.set_weapon(W_PISTOL)
    assert p.vis.gun is not None and p.vis.gun_kind == 'pistol'
    harness.run(game, 0.3)
    assert p.vis.cur == 'pistol_idle'
    p.aiming = True
    harness.run(game, 0.3)
    assert p.vis.cur == 'pistol_aim'
    p.shot_t = 0.3
    harness.run(game, 0.1)
    assert p.vis.cur == 'pistol_shoot'
    # автомат держат двумя руками
    p.aiming = False
    p.set_weapon(W_AK)
    assert p.vis.gun_kind == 'rifle'
    harness.run(game, 0.5)
    assert p.vis.cur == 'rifle_idle'
    p.aiming = True
    harness.run(game, 0.3)
    assert p.vis.cur == 'rifle_fire' and p.vis.hold is not None      # замер в позе прицеливания
    p.set_state('goto')
    p.tx, p.ty, p.timer = p.x + 60.0, p.y, 0.0
    harness.run(game, 0.4)
    assert p.vis.cur == 'rifle_walk'
    p.set_state('stand')
    p.aiming = False
    # удары
    p.set_weapon(W_FIST)
    assert p.vis.gun is None
    harness.run(game, 0.4)
    p.punch_t = 0.3
    harness.run(game, 0.1)
    assert p.vis.cur in ('punch_a', 'punch_b')
    p.set_weapon(W_BAT)
    harness.run(game, 0.5)
    p.punch_t = 0.3
    harness.run(game, 0.1)
    assert p.vis.cur == 'swing'
    # убит
    p.hurt(500.0, None, 'bullet')
    harness.run(game, 0.3)
    assert p.dead and p.vis.cur.startswith('death')


def test_women_and_special_poses(game, world):
    w = world
    x, y = w.city.landmarks['safehouse']['road']
    p = w.spawn_ped(x + 4.0, y - 3.0, 0.0, make_look(model='f_old', female=True), 'mission')
    p.keep = True
    p.set_state('goto')
    p.tx, p.ty, p.timer = p.x + 60.0, p.y, 0.0
    harness.run(game, 0.5)
    assert p.vis.female and p.vis.cur == 'walk_f'
    p.timer = 5.0
    harness.run(game, 0.6)
    assert p.vis.cur == 'run_f'
    p.set_state('stand')
    p.idle_clip = 'talk'
    harness.run(game, 0.5)
    assert p.vis.cur == 'talk'


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
    assert pl.ped.vis is not None and pl.ped.vis.key == 'hero'
    pl.give_weapon(W_AK, 30)
    assert pl.ped.vis.gun is not None
    pl.ped.hurt(500.0, None, 'bullet')
    harness.run(game, 7.0)
    assert pl.state == 'foot' and not pl.ped.vis.cur.startswith('death')


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


def test_hands_are_mittens(world):
    """У моделей кисть — «варежка»: четыре пальца одним куском.  Если привязать её вершины к костям
    разных пальцев, в движении кисть рвёт веером.  Все пальцы, кроме большого, должны слушаться
    костей среднего."""
    from panda3d.core import GeomNode, JointVertexTransform
    m = world.models
    seen = 0
    for model in sorted(set(info['model'] for info in m.meta['chars'].values())):
        root = m._load('chars', model + '.bam')
        names = set()
        for gnp in root.findAllMatches('**/+GeomNode'):
            gn = gnp.node()
            for i in range(gn.getNumGeoms()):
                tbt = gn.getGeom(i).getVertexData().getTransformBlendTable()
                for b in range(tbt.getNumBlends()):
                    blend = tbt.getBlend(b)
                    for k in range(blend.getNumTransforms()):
                        t = blend.getTransform(k)
                        if isinstance(t, JointVertexTransform):
                            names.add(t.getJoint().getName())
        assert names, model
        bad = [n for n in names if n.split('_')[0] in ('index', 'ring', 'pinky')]
        assert not bad, (model, bad)
        seen += 1
    assert seen >= 20


def test_combined_character_has_two_textures(world):
    """Сборный персонаж: тело одной модели, голова другой — каждая часть со своей текстурой."""
    m = world.models
    info = m.meta['chars']['hero']
    assert info['tex'] == 'm_leather' and info['head_tex'] == 'm_red'
    a = m.actor('hero')
    body, head = a.find('**/skin'), a.find('**/head')
    assert not body.isEmpty() and not head.isEmpty()
    tb, th = body.getTexture(), head.getTexture()
    assert tb is not None and th is not None and tb != th
    # у обычной модели узла «head» нет
    b = m.actor('m_shirt')
    assert b.find('**/head').isEmpty()
    for x in (a, b):
        x.cleanup()
        x.removeNode()
