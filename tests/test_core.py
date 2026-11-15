# -*- coding: utf-8 -*-
"""Модульные тесты логики, не требующей графики."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.city import City
from game.collision import StaticWorld, F_CAR, F_PED, F_WALL
from game.roadnet import RoadNet
from game import mathutil


def test_city_is_deterministic():
    a, b = City(), City()
    assert len(a.buildings) == len(b.buildings) > 200
    assert [(round(x.x0, 3), round(x.y0, 3), x.h) for x in a.buildings] == \
           [(round(x.x0, 3), round(x.y0, 3), x.h) for x in b.buildings]
    assert a.packages == b.packages


def test_landmarks_present_and_reachable():
    c = City()
    for name in ('safehouse', 'vano', 'rosa', 'prof', 'spray', 'spray2', 'hospital', 'police', 'bank', 'taxi',
                 'guns', 'guns2', 'port', 'gas'):
        lm = c.landmarks[name]
        x, y = lm['door']
        assert c.ground_z(x, y) > 0.0, name          # дверь выходит на тротуар
        rx, ry = lm['road']
        assert c.on_road(rx, ry), name               # перед зданием — проезжая часть
    assert not c.in_water(*c.start_pos[:2])


def test_road_network_connected():
    c = City()
    rn = RoadNet(c)
    assert all(l.next for l in rn.lanes)
    # из любого перекрёстка можно доехать до любого
    nodes = list(c.nodes.keys())
    for b in nodes[::7]:
        assert rn.route(nodes[0], b), b
    # граф тротуаров связен
    seen = set()
    stack = [rn.ped_nodes[0]]
    while stack:
        n = stack.pop()
        if n.id in seen:
            continue
        seen.add(n.id)
        stack.extend(e[0] for e in n.edges)
    assert len(seen) == len(rn.ped_nodes)


def test_lanes_drive_on_the_right():
    c = City()
    rn = RoadNet(c)
    for l in rn.lanes:
        x, y, yaw = l.pos(l.length * 0.5)
        seg = c.segs[l.seg]
        # правее осевой по ходу движения
        if l.dir == 'e':
            assert y < seg['c']
        elif l.dir == 'w':
            assert y > seg['c']
        elif l.dir == 'n':
            assert x > seg['c']
        else:
            assert x < seg['c']
        assert c.on_road(x, y)


def test_signals_never_green_for_both_axes():
    rn = RoadNet(City())
    t = 0.0
    while t < 60.0:
        a, b = rn._state(t % 26.0, 0), rn._state(t % 26.0, 1)
        assert not (a in 'gy' and b in 'gy'), t
        t += 0.25


def test_collision_push_and_raycast():
    st = StaticWorld()
    st.add_box(0.0, 0.0, 10.0, 10.0, 0.0, 5.0, F_WALL, ('bld', 1))
    x, y, nx, ny, depth, ref = st.push_circle(-0.2, 5.0, 0.5, F_CAR)
    assert depth > 0 and ref == ('bld', 1)
    assert abs(x + 0.5) < 1e-6 and nx < 0
    hit = st.raycast(-5.0, 5.0, 1.0, 1.0, 0.0, 0.0, 20.0)
    assert hit is not None and abs(hit[0] - 5.0) < 1e-6 and hit[4] == ('bld', 1)
    assert st.raycast(-5.0, 5.0, 6.0, 1.0, 0.0, 0.0, 20.0) is None      # выше крыши
    assert not st.los(-5.0, 5.0, 15.0, 5.0)
    assert st.los(-5.0, 15.0, 15.0, 15.0)
    cid = st.add_circle(20.0, 20.0, 1.0, 2.0, F_CAR | F_PED, ('prop', 2))
    assert st.overlap_circle(20.5, 20.0, 0.3, F_PED)
    st.remove_circle(cid)
    assert not st.overlap_circle(20.5, 20.0, 0.3, F_PED)


def test_math_helpers():
    assert abs(mathutil.angle_diff(0.1, -0.1) - 0.2) < 1e-9
    assert abs(mathutil.angle_diff(math.pi - 0.1, -math.pi + 0.1) + 0.2) < 1e-9
    assert abs(mathutil.turn_towards(0.0, 1.0, 0.25) - 0.25) < 1e-9
    assert mathutil.approach(1.0, 0.0, 2.0) == 0.0
    assert abs(mathutil.yaw_to_h(math.pi / 2)) < 1e-9          # «на север» в Panda3D — H = 0


def test_first_run_window_fits_the_screen():
    from game.settings import fit_window
    sizes = [(1024, 576), (1280, 720), (1366, 768), (1600, 900), (1920, 1080)]
    assert fit_window(sizes, (1366, 768)) == (1024, 576)        # ноутбук: окно не уходит под панель задач
    assert fit_window(sizes, (1920, 1080)) == (1600, 900)
    assert fit_window(sizes, (2560, 1440)) == (1920, 1080)
    assert fit_window(sizes, (800, 600)) == (1024, 576)         # меньше не бывает
    assert fit_window(sizes, (0, 0)) is None                    # размер экрана неизвестен — оставить как есть
