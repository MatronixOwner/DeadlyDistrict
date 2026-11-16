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
from game.vehicle import SPECS, Vehicle

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
    x, y = w.city.landmarks['terminal']['road']
    v = w.spawn_vehicle(kind, x, y - 1.5, 0.0)
    if spec.bike:
        # мотоциклы и их родня собраны кодом: два колеса по оси, у трайка и мотоцикла с коляской три, у квадроцикла четыре
        assert kind not in VEHICLE_MODELS and v.bparts is not None and v.steer_np is not None
        mn, mx = v.tilt.getTightBounds(v.tilt)
        assert abs((mx.y - mn.y) - spec.L) < 0.22 * spec.L
        assert (mx.x - mn.x) <= spec.W * 1.3 and mx.z <= spec.H * 1.15
        assert abs((mx.x + mn.x) * 0.5) < 0.12                         # модель стоит по середине своего габарита
        assert len(v.wheels) == {'quad': 4, 'kart': 4, 'caddy': 4, 'trike': 3, 'sidecar': 3, 'cargo': 3}.get(kind, 2)
        front = v.wheels[0][0].getPos(v.tilt)
        rear = v.wheels[-1][0].getPos(v.tilt)
        assert front.y > 0 > rear.y and abs(front.z - spec.wheel_r) < 0.04
    else:
        assert kind in VEHICLE_MODELS
        assert v.minfo is not None, 'нет модели для %s' % kind
        mn, mx = v.body.getTightBounds(v.tilt)
        assert abs((mx.y - mn.y) - spec.L) < 0.05 * spec.L       # длина — вдоль +Y
        assert (mx.x - mn.x) <= spec.W * 1.25                     # за зону столкновений торчат только зеркала
        assert len(v.wheels) == 4
        fl, fr, rl, rr = [piv.getPos() for piv, _ in v.wheels]
        assert fl.x < 0 < fr.x and rl.x < 0 < rr.x                # левые слева, правые справа
        assert fl.y > 0 > rl.y and fr.y > 0 > rr.y                # передние впереди
        assert abs(fl.z - v.wheel_r_vis) < 1e-3                    # колёса стоят на земле
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
    x, y = w.city.landmarks['terminal']['door']
    p = w.spawn_ped(x + 3.0, y, 0.0, look, kind)
    assert p.vis is not None and p.vis.key in expect
    w.remove_ped(p)
    assert p.vis is None


def test_every_zone_look_gets_a_model(world):
    w = world
    rnd = random.Random(9)
    x, y = w.city.landmarks['terminal']['door']
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
    x, y = w.city.landmarks['terminal']['road']
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
    assert p.vis.cur == 'idle'                       # пока не целится, рука с пистолетом опущена
    p.aiming = True
    harness.run(game, 0.3)
    assert p.vis.cur == 'pistol_aim'
    p.shot_t = 0.3
    harness.run(game, 0.1)
    assert p.vis.cur == 'pistol_shoot'
    p.aiming = False
    harness.run(game, 0.7)
    assert p.vis.cur == 'pistol_aim'                 # после выстрела ещё секунду держит наготове
    harness.run(game, 2.0)
    assert p.vis.cur == 'idle'                       # ...и опускает
    # автомат держат двумя руками
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
    x, y = w.city.landmarks['terminal']['road']
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
    x, y = w.city.landmarks['terminal']['road']
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


def test_red_shirt_guy_wears_trousers(world):
    """У модели в футболке штаны были песочные, почти в цвет кожи: издали казалось, что человек без штанов.
    Теперь они тёмные на всех текстурах этой модели."""
    from panda3d.core import PNMImage, Filename
    pts = ((385, 120), (240, 120), (200, 330), (60, 380), (370, 430), (425, 430))       # по разу на каждый кусок штанов
    chars = world.models.meta['chars']
    names = sorted(set(i['tex'] for i in chars.values() if i['tex'] == 'm_red' or i['tex'].startswith('red_')))
    assert len(names) == 8, names
    for n in names:
        img = PNMImage(Filename.fromOsSpecific(os.path.join(harness.ROOT, 'assets', 'models', 'chars', n + '.png')))
        k = img.getXSize() / 512.0
        for (x, y) in pts:
            c = img.getXel(int(x * k), int(y * k))
            assert max(c[0], c[1], c[2]) < 0.56, (n, x, y, tuple(c))                    # было 0.64–0.76


def test_long_gun_lies_in_both_hands(game, world):
    """Автомат привязан к правой кисти, но ствол должен проходить через левую ладонь — и в стойке, и на бегу.
    Раньше он был закреплён жёстко и в половине клипов торчал мимо левой руки.

    В стойке прицеливания наоборот: ствол смотрит туда, куда целятся, а левая рука приходит под цевьё
    (раньше ствол в этой позе глядел в землю, а рука была вытянута под ним)."""
    from panda3d.core import LPoint3, LVector3
    from game.defs import W_SHOTGUN, W_M4, W_DOUBLE, W_ROCKET
    w = world
    harness.quiet(w, peds=True)
    px, py = w.player.pos()
    p = w.spawn_ped(px + 3.0, py, 0.0, random_look(random.Random(4), 'D'))
    p.keep = True
    p.set_state('stand')
    p.set_weapon(W_AK)
    vis = p.vis
    for clip in ('rifle_idle', 'rifle_walk', 'rifle_run'):
        worst = 0.0
        for k in range(6):
            vis.play(clip, True, 1.0, 0.0, True, k / 6.0)
            vis.update(0.0)
            vis.actor.update(force=True)
            vis.update(0.0)
            gun = vis.gun
            left = vis.grips['_left']
            lp = left.getPos(gun)                    # левая ладонь в системе оружия: ствол — ось +Y
            assert lp.y > 0.05, (clip, k, lp)        # ладонь впереди рукояти
            worst = max(worst, math.hypot(lp.x, lp.z))
        assert worst < 0.03, (clip, worst)
        assert vis._ik is None, clip                 # левую руку ведёт клип
    for wid in (W_AK, W_M4, W_SHOTGUN, W_DOUBLE, W_ROCKET):
        p.set_weapon(wid)
        vis = p.vis
        sy, sz = vis.support
        for pitch in (0.0, 25.0, -25.0):
            vis.aim_pitch = pitch
            for k in range(4):
                vis.play('rifle_fire', True, 1.0, 0.0, True, k / 6.0)
                for _ in range(14):                  # угол подводится плавно, кости отстают на кадр
                    vis.update(0.0)
                    vis.actor.update(force=True)
                gun = vis.gun
                fwd = p.node.getRelativeVector(gun, LVector3(0, 1, 0))
                fwd.normalize()
                assert abs(fwd.x) < 0.02 and fwd.y > 0.85, (wid, pitch, fwd)
                assert abs(math.degrees(math.asin(fwd.z)) - pitch) < 1.0, (wid, pitch, fwd)
                lp = vis.grips['_left'].getPos(gun)  # костяшки левой кисти — у точки хвата под цевьём
                assert abs(lp.x) < 0.06, (wid, pitch, k, lp)
                assert -0.03 < lp.y - sy < 0.06, (wid, pitch, k, lp)
                assert -0.03 < lp.z - sz < 0.06, (wid, pitch, k, lp)
        assert vis._ik is not None
    # оружие убрали или сменили на пистолет — рука снова слушается клипа
    p.set_weapon(W_PISTOL)
    assert p.vis._ik is None
    w.remove_ped(p)


def test_fleet_has_bikes_and_new_cars(world):
    """Транспорта стало больше чем вдвое: шестнадцать видов мотоциклов и их родни и десять новых машин."""
    from game.vehicle import BIKES, ZONE_CARS
    assert len(SPECS) >= 43
    assert set(BIKES) == set(ALL_BIKES) and len(ALL_BIKES) == 16
    new_cars = {'limo', 'racer', 'minibus', 'firetruck', 'cashvan', 'icecream', 'hotrod', 'jeep', 'pizza', 'tuner'}
    assert new_cars <= set(SPECS) and new_cars <= set(VEHICLE_MODELS)
    titles = [s.title for s in SPECS.values()]
    assert len(titles) == len(set(titles))                         # у каждой машины своё название
    # всё новое действительно ездит по городу
    seen = set(k for cars in ZONE_CARS.values() for k, wgt in cars if wgt > 0)
    assert (new_cars | set(BIKES)) <= seen
    for cars in ZONE_CARS.values():
        assert all(k in SPECS for k, _ in cars)


ALL_BIKES = ['bike', 'chopper', 'scooter', 'dirt', 'bicycle', 'quad', 'moped', 'copbike', 'sidecar', 'trike', 'bmx',
             'tourer', 'courier', 'cargo', 'kart', 'caddy']


def _check_rider(v, vis, seat=None, tol=0.05):
    """Ездок сидит в седле, а не рядом с ним: таз — в точке посадки, кисти — у ручек руля."""
    from game import bikes
    g = bikes.geo(v.kind)
    sx, sy, sz = seat or v.bparts['seat']
    pv = vis.pelvis_pos(v.tilt)
    assert abs(pv.x - sx) < tol and abs(pv.y - sy) < tol and abs(pv.z - sz) < tol, (v.kind, tuple(pv), (sx, sy, sz))
    if seat is None:
        a = vis.actor
        for name, side in (('hand_l', -1), ('hand_r', 1)):
            j = vis.grips.get('_' + name)
            if j is None:
                j = vis.grips['_' + name] = a.exposeJoint(None, 'modelRoot', name)
        a.update(force=True)
        for name in ('hand_l', 'hand_r'):
            h = vis.grips['_' + name].getPos(v.tilt)
            # кисть — на руле: по длине и высоте в пределах ладони, по ширине — в пределах руля
            assert abs(h.y - g.gy) < 0.16 and abs(h.z - g.gz) < 0.14, (v.kind, name, tuple(h), (g.gy, g.gz))
            assert abs(h.x - g.x) < g.bar + 0.05, (v.kind, name, tuple(h))


@pytest.mark.parametrize('kind', ALL_BIKES)
def test_every_bike_seats_its_rider(game, world, kind):
    """У каждой модели ездок сидит в седле и держится за руль; где есть второе место — пассажир на нём."""
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    lane = w.roadnet.lane_index[('h', 2, 2, 'e', 0)]
    x, y, yaw = lane.pos(6.0)
    v = w.spawn_vehicle(kind, x, y, yaw, paint=0)
    spec = v.spec
    # колёса стоят на земле и не выходят за габарит, по которому считаются столкновения
    assert len(v.wheels) == len(v.bparts['wheels']) >= 2
    for (wx, wy, r, how, node) in v.bparts['wheels']:
        assert abs(wx) <= spec.W * 0.5 + 0.02 and abs(wy) + r <= spec.L * 0.5 + 0.08, (kind, wx, wy, r)
    pl.teleport(x, y - 2.0)
    pl.enter_vehicle(v, silent=True)
    harness.run(game, 0.2)
    p = pl.ped
    assert pl.vehicle is v and p.node.getParent() == v.tilt and not p.node.isHidden()
    _check_rider(v, p.vis)
    harness.run(game, 2.0, keys=('w',))
    assert v.speed > 2.0
    if spec.seats > 1:
        q = w.spawn_ped(x + 2.0, y - 2.5, 0.0, random_look(random.Random(5), 'O'))
        w.put_in_vehicle(q, v)
        harness.run(game, 0.1)
        assert not q.node.isHidden() and q.node.getParent() == v.tilt        # пассажира видно: он сидит на своём месте
        _check_rider(v, q.vis, seat=v.bparts['seat2'][:3])
        w.take_out(q, 1)
        harness.run(game, 0.1)
        assert q.node.getParent() != v.tilt and abs(q.z - w.city.ground_z(q.x, q.y)) < 0.05
        w.remove_ped(q)
    else:
        assert v.bparts['seat2'] is None
    harness.run(game, 1.5, keys=('s',))
    pl.leave_vehicle(force=True)
    harness.run(game, 0.3)
    assert pl.state == 'foot' and p.node.getParent() != v.tilt and p.vis.cur != 'mix'
    w.remove_vehicle(v)


def test_riding_a_motorcycle(game, world):
    """На мотоцикле героя видно в седле, мотоцикл ложится в поворот, руль поворачивается с колесом;
    сильный удар выбивает из седла."""
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    lane = w.roadnet.lane_index[('h', 2, 2, 'e', 0)]
    x, y, yaw = lane.pos(4.0)
    bike = w.spawn_vehicle('bike', x, y, yaw, paint=0)
    pl.teleport(x, y - 2.0)
    pl.enter_vehicle(bike, silent=True)
    harness.run(game, 0.2)
    p = pl.ped
    assert pl.state == 'car' and pl.vehicle is bike
    assert not p.node.isHidden() and p.node.getParent() == bike.tilt        # сидит верхом и едет вместе с ним
    assert p.vis.cur == 'mix'                                               # поза ездока — смесь «верхом» и «за рулём»
    _check_rider(bike, p.vis)
    harness.run(game, 3.0, keys=('w',))
    assert bike.speed > 14.0
    harness.run(game, 0.5, keys=('w', 'a'))
    assert bike.roll > 8.0 or bike.roll < -8.0                               # лёг в поворот
    assert abs(bike.steer_np.getH()) > 2.0
    # слезаем: герой снова на земле, сам по себе
    harness.run(game, 3.0, keys=('s',))
    pl.leave_vehicle(force=True)
    harness.run(game, 0.3)
    assert pl.state == 'foot' and p.node.getParent() != bike.tilt and not p.node.isHidden()
    assert abs(p.z - w.city.ground_z(p.x, p.y)) < 0.05
    # удар о стену на скорости
    lm = w.city.landmarks['bank']
    bx = (lm['rect'][0] + lm['rect'][2]) * 0.5
    by = lm['rect'][1] - 14.0
    b2 = w.spawn_vehicle('dirt', bx, by, math.pi / 2, paint=1)
    pl.teleport(bx - 1.5, by)
    pl.enter_vehicle(b2, silent=True)
    hp = p.health
    t = 0.0
    while pl.vehicle is b2 and t < 5.0:
        harness.run(game, 0.1, keys=('w',))
        t += 0.1
    assert pl.vehicle is None, 'после удара о стену герой должен вылететь из седла'
    assert p.health < hp and p.node.getParent() != b2.tilt
    harness.run(game, 4.0)
    assert pl.state == 'foot' and not p.dead


def test_traffic_bikers_and_jacking(game, world):
    """В потоке машин на мотоцикле сидит ездок; угнал — он оказывается на асфальте, а герой в седле."""
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    lane = w.roadnet.lane_index[('h', 2, 2, 'e', 0)]
    x, y, yaw = lane.pos(12.0)
    v = w.spawn_vehicle('chopper', x, y, yaw)
    v.npc = True
    v.add_rider(random_look(random.Random(2), 'G'))
    assert v.rider is not None and not v.rider.root.isEmpty() and v.rider.cur == 'mix'
    _check_rider(v, v.rider)
    pl.teleport(x, y - 1.6)
    harness.run(game, 0.2)
    before = set(w.peds)
    pl.enter_side = -1
    pl.enter_vehicle(v)
    harness.run(game, 0.3)
    thrown = [q for q in w.peds if q not in before and not q.is_player]
    assert v.rider is None and len(thrown) == 1                             # ездок стал настоящим и упал
    assert math.hypot(thrown[0].x - v.x, thrown[0].y - v.y) < 5.0 and thrown[0].state == 'down'
    assert pl.vehicle is v and pl.ped.node.getParent() == v.tilt
    # машину убрали из мира — герой не пропадает вместе с ней
    pl.leave_vehicle(force=True)
    pl.enter_vehicle(v, silent=True)
    w.remove_vehicle(v)
    assert not pl.ped.node.isEmpty()


def test_bicycle_breaks_instead_of_exploding(game, world):
    """У велосипеда нет ни мотора, ни бака: он не горит и не взрывается, а ломается и падает набок."""
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    lane = w.roadnet.lane_index[('h', 2, 2, 'e', 0)]
    x, y, yaw = lane.pos(8.0)
    for kind in ('bicycle', 'bmx'):
        assert SPECS[kind].nofire
    assert not SPECS['moped'].nofire and not SPECS['caddy'].nofire
    v = w.spawn_vehicle('bicycle', x, y, yaw, paint=0)
    pl.teleport(x, y - 2.0)
    pl.enter_vehicle(v, silent=True)
    harness.run(game, 0.2)
    wrecks = w.stats['wrecks']
    hp = pl.ped.health
    v.damage(v.max_health * 0.95, 'crash', False)
    harness.run(game, 0.5)
    assert v.dead and v.fallen != 0.0 and v.burning <= 0.0                  # сломан, но не горит
    assert pl.vehicle is None and pl.ped.node.getParent() != v.tilt         # ездок на асфальте, сам по себе
    assert not pl.ped.dead and pl.ped.health < hp
    assert w.stats['wrecks'] == wrecks + 1
    harness.run(game, 1.5)
    assert abs(abs(v.roll) - 84.0) < 3.0                                    # лежит на боку
    pl.ped.health = 100.0
    harness.run(game, 3.0)
    # ездок из потока машин тоже остаётся жив: он падает рядом
    x2, y2, yaw2 = lane.pos(30.0)
    b = w.spawn_vehicle('bmx', x2, y2, yaw2)
    b.npc = True
    b.add_rider(random_look(random.Random(3), 'R'))
    before = set(w.peds)
    b.damage(b.max_health * 2.0, 'explosion', True)
    harness.run(game, 0.2)
    fell = [q for q in w.peds if q not in before]
    assert b.dead and b.rider is None and len(fell) == 1 and not fell[0].dead
    w.remove_ped(fell[0])
    w.remove_vehicle(b)
    w.remove_vehicle(v)


def test_buddy_rides_pillion_and_needs_a_second_seat(game, world):
    """Брат садится пассажиром: в коляску — там его видно; на одноместный скутер не садится, и игре есть что сказать."""
    from game import story
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    lane = w.roadnet.lane_index[('h', 2, 2, 'e', 0)]
    x, y, yaw = lane.pos(10.0)

    class FakeMission(object):
        pass
    m = FakeMission()
    m.w = w
    m.ticks = []
    bruce = w.spawn_ped(x + 1.0, y - 3.0, 0.0, story.person_look('bruce'))
    bruce.keep = True
    buddy = story.Buddy(m, bruce)

    def run(sec):
        for _ in range(int(sec * 60)):
            for t in m.ticks:
                t(1 / 60.0)
            game.step(1 / 60.0)

    side = w.spawn_vehicle('sidecar', x, y, yaw, paint=0)
    pl.teleport(x, y - 2.0)
    pl.enter_vehicle(side, silent=True)
    run(4.0)
    assert buddy.riding() and bruce.vehicle is side
    assert not bruce.node.isHidden() and bruce.node.getParent() == side.tilt      # сидит в коляске, его видно
    pv = bruce.vis.pelvis_pos(side.tilt)
    assert pv.x > 0.2                                                           # именно в коляске, а не на мотоцикле
    run(1.5)
    pl.leave_vehicle(force=True)
    run(1.0)
    assert bruce.vehicle is None and bruce.node.getParent() != side.tilt and not bruce.node.isHidden()
    # одноместный скутер: брат остаётся стоять, игрок видит подсказку
    sc = w.spawn_vehicle('scooter', x + 6.0, y, yaw, paint=0)
    pl.teleport(x + 6.0, y - 2.0)
    pl.enter_vehicle(sc, silent=True)
    w.hud.help('', 0.1)
    run(3.0)
    assert bruce.vehicle is None and 'вдвоём не уехать' in w.hud.help_text.getText()
    pl.leave_vehicle(force=True)
    buddy.stop()
    w.remove_ped(bruce)
    w.remove_vehicle(side)
    w.remove_vehicle(sc)


def test_police_motorcycle_serves(game, world):
    """Патрульный мотоцикл: сирена на H, маячки светят там, где они стоят на модели, мотоциклист из потока
    включается в погоню и слезает с мотоцикла, а в ателье и покраске служебный мотоцикл не берут."""
    from game import tuning, bikes
    from game.defs import cop_look
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    w.police.clear()
    lane = w.roadnet.lane_index[('h', 2, 2, 'e', 0)]
    x, y, yaw = lane.pos(10.0)
    v = w.spawn_vehicle('copbike', x, y, yaw)
    assert tuning.parts_for(v) == []
    pl.teleport(x, y - 2.0)
    pl.enter_vehicle(v, silent=True)
    harness.run(game, 0.2)
    harness.press(game, 'h')
    harness.run(game, 0.6)
    assert v.siren and v.siren_np is not None
    beacons = bikes.light_points('copbike')[2]
    assert beacons and len(beacons) == 2
    for np_, (bx, by, bz) in zip(v.siren_np, beacons):
        b = np_.getTightBounds()
        cx, cz = (b[0].x + b[1].x) * 0.5, (b[0].z + b[1].z) * 0.5
        assert abs(cx - bx) < 0.12 and abs(cz - bz) < 0.25, (cx, cz, bx, bz)
    harness.press(game, 'h')
    harness.run(game, 0.3)
    assert not v.siren
    pl.leave_vehicle(force=True)
    w.remove_vehicle(v)
    harness.run(game, 0.5)
    # мотоциклист из потока: розыск — и он в погоне
    x2, y2, yaw2 = lane.pos(6.0)
    b = w.spawn_vehicle('copbike', x2, y2, yaw2)
    b.npc = True
    b.traffic = True
    b.mode = Vehicle.RAIL
    b.link, b.s = lane, 6.0
    b.add_rider(cop_look())
    assert b.rider is not None
    hx, hy, _ = lane.pos(44.0)                      # герой — впереди по ходу мотоцикла, у обочины
    pl.teleport(hx, hy - 3.0)
    w.police.set_level(2)
    for _ in range(240):
        game.step(1 / 60.0)
        if b in w.police.units:
            break
    assert b in w.police.units and b.crew == 1 and b.siren and b.owner == 'police'
    # подъехал к стоящему герою — слез: ровно один полицейский, в седле никого
    pl.invincible = True
    before = set(w.peds)
    for _ in range(900):
        game.step(1 / 60.0)
        if b.crew == 0:
            break
    assert b.crew == 0 and b.rider is None
    cops = [q for q in w.peds if q not in before and q.kind == 'cop']
    assert len(cops) == 1 and not cops[0].node.isHidden()
    pl.invincible = False
    w.police.clear()
    for q in cops:
        w.remove_ped(q)
    w.remove_vehicle(b)
    pl.ped.health = 100.0
    # наряд на мотоцикле приезжает с ездоком в седле
    import random as _r
    state = _r.getstate()
    try:
        kinds = set()
        _r.seed(5)
        w.police.level = 2
        for _ in range(60):
            kinds.add(w.police._unit_kind())
        assert kinds == {'police', 'copbike'}
    finally:
        w.police.clear()
        _r.setstate(state)


def test_removing_a_seated_passenger_is_safe(game, world):
    """Задание кончилось, а брат ещё сидит в коляске: его убирают прямо с мотоцикла. Игра не должна упасть
    ни сразу, ни позже — когда мотоцикл взорвут, уберут или герой с него слезет."""
    from game import story
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    lane = w.roadnet.lane_index[('h', 2, 2, 'e', 0)]
    x, y, yaw = lane.pos(10.0)
    for kind, how in (('sidecar', 'remove'), ('tourer', 'explode'), ('caddy', 'leave')):
        v = w.spawn_vehicle(kind, x, y, yaw, paint=0)
        pl.teleport(x, y - 2.0)
        pl.enter_vehicle(v, silent=True)
        npc = w.spawn_ped(x + 1.0, y - 3.0, 0.0, story.person_look('bruce'))
        w.put_in_vehicle(npc, v)
        harness.run(game, 0.3)
        assert npc in v.passengers and npc.node.getParent() == v.tilt
        w.remove_ped(npc)
        assert npc not in v.passengers and npc.vehicle is None
        harness.run(game, 0.3)
        if how == 'explode':
            pl.leave_vehicle(force=True)
            pl.teleport(x, y - 30.0)
            v.explode(False)
            harness.run(game, 0.5)
        else:
            pl.leave_vehicle(force=True)
            harness.run(game, 0.3)
        w.remove_vehicle(v)
        harness.run(game, 0.3)
        assert not pl.ped.dead and pl.vehicle is None and not pl.ped.node.isHidden()
        pl.ped.health = 100.0


def test_every_vehicle_takes_full_tuning_and_paint(game, world):
    """Любую машину и любой мотоцикл можно обвесить всем, что для них продаётся, перекрасить, прокатить и убрать:
    ни одна деталь не должна уронить игру на непривычном кузове (карт, гольф-кар, коляска)."""
    from game import tuning
    from game.vehicle import PAINTS
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    lane = w.roadnet.lane_index[('h', 2, 2, 'e', 0)]
    x, y, yaw = lane.pos(10.0)
    pl.teleport(x, y - 4.0)
    for kind in sorted(SPECS):
        v = w.spawn_vehicle(kind, x, y, yaw, paint=0)
        parts = tuning.parts_for(v)
        if kind in tuning.NO_TUNE:
            assert parts == []
        full = dict((k, len(opts)) for k, title, opts in parts)
        v.apply_tune(full)
        assert v.tune == tuning.clean(full), kind
        if v.spec.paints is None:
            v.set_paint(3)
        w.sky.set_time(23.0)
        v.set_lights(True)
        pl.enter_vehicle(v, silent=True)
        harness.run(game, 0.4, keys=('w', 'shift'))
        assert pl.vehicle is v, kind
        pl.leave_vehicle(force=True)
        for k, title, opts in parts:                 # и по одной детали, каждый вариант
            for n in range(len(opts) + 1):
                v.apply_tune({k: n})
        v.apply_tune({})
        assert not v.tune, kind
        w.remove_vehicle(v)
        harness.run(game, 0.1)
        pl.teleport(x, y - 4.0)
    w.sky.set_time(12.0)


def test_rider_is_exposed_to_bullets_and_crashes(game, world):
    """Ездок сидит на виду. Пуля выше мотоцикла попадает в него, а не пролетает сквозь нарисованную фигуру;
    чужого мотоциклиста выстрел и сильный удар сбрасывают с седла; игрок на мотоцикле ранен пулей сам."""
    from game.defs import WEAPONS, W_PISTOL, W_AK
    w = world
    pl = w.player
    harness.quiet(w, peds=True)
    w.police.clear()
    lane = w.roadnet.lane_index[('h', 2, 2, 'e', 0)]
    x, y, yaw = lane.pos(12.0)
    wpn = w.weapons
    pistol = WEAPONS[W_PISTOL]

    def traffic_bike(kind='chopper'):
        b = w.spawn_vehicle(kind, x, y, yaw)
        b.npc = True
        b.traffic = True
        b.mode = Vehicle.RAIL
        b.link, b.s = lane, 12.0
        b.speed = 0.0
        b.add_rider(random_look(random.Random(4), 'R'))
        return b

    # 1. без ездока верх мишени — сам мотоцикл; с ездоком — его голова
    b = traffic_bike()
    top_rider = b.hit_top()
    assert top_rider > b.spec.H + 0.3
    head_z = b.z + b.spec.H + 0.25                       # выше руля: тут только человек
    pl.teleport(x, y - 8.0)
    before = set(w.peds)
    t, kind, obj, nx, ny, nz = wpn.trace(x, y - 8.0, head_z, 0.0, 1.0, 0.0, 60.0, pl.ped, None)
    assert kind == 'veh' and obj is b                   # луч на высоте груди упирается в мотоцикл с ездоком
    assert b.rider_hit(head_z) == 'npc'
    wpn._apply_bullet(pistol, t, kind, obj, nx, ny, nz, x, y - 8.0, head_z, 0.0, 1.0, 0.0, pl.ped)
    fell = [q for q in w.peds if q not in before]
    assert b.rider is None and not b.npc and len(fell) == 1
    assert fell[0].last_attacker is pl.ped and (fell[0].dead or fell[0].health < fell[0].max_health)
    assert b.hit_top() == b.spec.H                      # седло опустело
    t2, kind2, obj2 = wpn.trace(x, y - 8.0, head_z, 0.0, 1.0, 0.0, 60.0, pl.ped, None)[:3]
    assert obj2 is not b                                # теперь на этой высоте пусто
    for q in fell:
        w.remove_ped(q)
    w.remove_vehicle(b)
    w.police.clear()
    # 2. сильный удар сбрасывает чужого мотоциклиста, слабый — нет
    b = traffic_bike('scooter')
    before = set(w.peds)
    w.on_vehicle_impact(b, 4.0, b.x, b.y, None, sound=False)
    assert b.rider is not None
    w.on_vehicle_impact(b, 11.0, b.x, b.y, None, sound=False)
    fell = [q for q in w.peds if q not in before]
    assert b.rider is None and len(fell) == 1 and fell[0].state in ('down', 'dead')
    for q in fell:
        w.remove_ped(q)
    w.remove_vehicle(b)
    # 3. игрок в седле: пуля выше мотоцикла ранит его самого, мотоцикл цел
    mine = w.spawn_vehicle('bike', x, y, yaw)
    pl.teleport(x, y - 2.0)
    pl.enter_vehicle(mine, silent=True)
    harness.run(game, 0.2)
    hp, vhp = pl.ped.health, mine.health
    assert mine.rider_hit(mine.z + mine.spec.H + 0.3) is pl.ped
    assert mine.rider_hit(mine.z + 0.3) is None           # по колёсам — в мотоцикл
    shooter = w.spawn_ped(x, y - 9.0, math.pi / 2, random_look(random.Random(5), 'R'), 'civ')
    hz = mine.z + mine.spec.H + 0.3
    t, kind, obj, nx, ny, nz = wpn.trace(x, y - 8.5, hz, 0.0, 1.0, 0.0, 60.0, shooter, None)
    assert kind == 'veh' and obj is mine
    wpn._apply_bullet(WEAPONS[W_AK], t, kind, obj, nx, ny, nz, x, y - 8.5, hz, 0.0, 1.0, 0.0, shooter)
    assert pl.ped.health < hp and mine.health == vhp and pl.vehicle is mine
    pl.ped.health = 100.0
    pl.leave_vehicle(force=True)
    w.remove_ped(shooter)
    w.remove_vehicle(mine)
    w.police.clear()


def _node_mesh(np_, animated=False):
    """Вершины и треугольники узла модели: ([(x, y, z)], [(i, j, k)])."""
    from panda3d.core import GeomNode, GeomVertexReader, Thread
    nodes = [np_] if isinstance(np_.node(), GeomNode) else list(np_.findAllMatches('**/+GeomNode'))
    pts, tris = [], []
    for gp in nodes:
        gn = gp.node()
        for i in range(gn.getNumGeoms()):
            geom = gn.getGeom(i).decompose()
            vd = geom.getVertexData()
            if animated:
                vd = vd.animateVertices(True, Thread.getCurrentThread())
            base = len(pts)
            r = GeomVertexReader(vd, 'vertex')
            while not r.isAtEnd():
                v = r.getData3()
                pts.append((v.x, v.y, v.z))
            for k in range(geom.getNumPrimitives()):
                prim = geom.getPrimitive(k)
                for t in range(prim.getNumPrimitives()):
                    a = prim.getPrimitiveStart(t)
                    tris.append(tuple(base + prim.getVertex(a + j) for j in range(3)))
    return pts, tris


def test_head_sits_on_the_neck_without_a_gap(world):
    """Сборный персонаж (тело одной модели, голова другой): между шеей и воротником не должно быть щели.

    Раньше тело обрезалось ниже воротника, а в него вставлялась «шея» головы: у футболки и поло в вороте
    зияла дыра, в движении шея отходила от тела.  Теперь край тела (кольцо над воротником) лежит точно на
    кольце головы и привязан к тем же костям — проверяем и в позе покоя, и с наклонённой головой."""
    import numpy as np
    m = world.models
    combos = sorted(k for k, i in m.meta['chars'].items() if i.get('head_tex') and i['model'] == k)
    assert len(combos) >= 12, combos
    for key in combos:
        a = m.actor(key)
        body, head = a.find('**/skin'), a.find('**/head')
        rest, tris = _node_mesh(body)
        rest = np.array(rest)
        # край тела у шеи: рёбра, у которых только один треугольник (вершины склеиваем по положению)
        weld = {}
        wid = [weld.setdefault(tuple(np.round(p, 4)), len(weld)) for p in rest]
        count = {}
        for t in tris:
            for u, v in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                e = (min(wid[u], wid[v]), max(wid[u], wid[v]))
                count.setdefault(e, []).append((u, v))
        free = sorted(set(u for e, uses in count.items() if len(uses) == 1 for u in uses[0]
                          if 1.40 < rest[u][2] < 1.75 and abs(rest[u][0]) < 0.2 and abs(rest[u][1]) < 0.2))
        # срез шеи — наклонная плоскость (спереди ниже; в файле модель смотрит на −Y); её край — самые
        # верхние из свободных вершин (у поло свободный край есть ещё и у отложного воротника — он ниже)
        cut = rest[free] @ np.array([0.0, -math.sin(math.radians(14.0)), math.cos(math.radians(14.0))])
        rim = [u for u, c in zip(free, cut) if c > cut.max() - 0.0015]
        assert len(rim) >= 8, (key, len(rim))
        for clip, frame, limit in ((None, 0, 0.002), ('phone', 12, 0.006), ('talk', 20, 0.006)):
            if clip is not None:
                a.pose(clip, frame)
                a.update(force=True)
            bp = np.array(_node_mesh(body, clip is not None)[0])
            hp, ht = _node_mesh(head, clip is not None)
            hp = np.array(hp)
            ht = np.array(ht)
            ea = np.concatenate([hp[ht[:, 0]], hp[ht[:, 1]], hp[ht[:, 2]]])
            eb = np.concatenate([hp[ht[:, 1]], hp[ht[:, 2]], hp[ht[:, 0]]])
            d = eb - ea
            dd = np.maximum((d * d).sum(1), 1e-12)
            worst = 0.0
            for u in rim:
                k = np.clip(((bp[u] - ea) * d).sum(1) / dd, 0.0, 1.0)
                gap = float(np.sqrt((((ea + d * k[:, None]) - bp[u]) ** 2).sum(1)).min())
                worst = max(worst, gap)
            assert worst < limit, (key, clip, round(worst, 4))
        a.cleanup()
        a.removeNode()


def test_head_skin_is_toned_to_the_body(world):
    """Кожа головы сборного персонажа подведена под кожу тела: текстура головы у него своя, с поправкой цвета."""
    m = world.models
    info = m.meta['chars']['m_shirt_h4']
    gain = info['head_gain']
    assert len(gain) == 3 and all(0.79 <= g <= 1.23 for g in gain) and max(gain) > 1.1, gain
    plain = m.char_texture(info['head_tex'])
    toned = m.char_texture(info['head_tex'], gain)
    assert toned is not plain and toned.getXSize() == plain.getXSize()
    assert m.char_texture(info['head_tex'], gain) is toned              # вторая такая же — из кэша
    assert m.char_texture(info['head_tex'], [1.0, 1.01, 0.99]) is plain   # поправка меньше 2 % не нужна
