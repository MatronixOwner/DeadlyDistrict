# -*- coding: utf-8 -*-
"""Модульные тесты логики, не требующей графики."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.city import City, CURB, WATER_Z
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
    c.go_live()                                      # как в игре: точки и вопросы — в мире, на изогнутых улицах
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
    # из любого перекрёстка можно доехать до любого — в пределах своей карты: Зимогорск (городок пролога)
    # стоит отдельно, дорог между ним и Порт-Глуховом нет
    from game.city import INTRO_I0
    nodes = [k for k in c.nodes if k[0] < INTRO_I0]
    town = [k for k in c.nodes if k[0] >= INTRO_I0]
    assert len(nodes) > 150 and len(town) > 20
    for b in nodes[::7]:
        assert rn.route(nodes[0], b), b
    for b in town[::3]:
        assert rn.route(town[0], b), b
    assert not rn.route(nodes[0], town[0])
    # граф тротуаров связен внутри каждого берега: остров, Заречье, восточный берег — и отдельно Зимогорск
    # (по мостам и трассе пешком не ходят)
    seen = set()
    parts = []
    for start in rn.ped_nodes:
        if start.id in seen:
            continue
        part = set()
        stack = [start]
        while stack:
            n = stack.pop()
            if n.id in part:
                continue
            part.add(n.id)
            stack.extend(e[0] for e in n.edges)
        seen |= part
        parts.append(part)
    assert sorted(len(p) for p in parts)[0] >= 20, [len(p) for p in parts]
    assert len(parts) == 4, [len(p) for p in parts]


def test_lanes_drive_on_the_right():
    c = City()
    rn = RoadNet(c)
    c.go_live()
    for l in rn.lanes:
        for k in (0.03, 0.5, 0.97):
            x, y, yaw = l.pos(l.length * k)
            assert c.on_road(x, y)
            u, v = c.to_plan(x, y)                   # на чертеже улица идёт по оси: полоса правее осевой по ходу
            seg = c.segs[l.seg]
            if l.dir == 'e':
                assert v < seg['c']
            elif l.dir == 'w':
                assert v > seg['c']
            elif l.dir == 'n':
                assert u > seg['c']
            else:
                assert u < seg['c']
        # полоса — плавная кривая: курс вдоль неё не скачет, длина честная
        x0, y0, a0 = l.pos(0.0)
        x1, y1, a1 = l.pos(1.0)
        assert abs(math.hypot(x1 - x0, y1 - y0) - 1.0) < 0.02
        assert abs(mathutil.angle_diff(math.atan2(y1 - y0, x1 - x0), a0)) < 0.05


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


class _FakeSettings(dict):
    def set(self, k, v):
        self[k] = v


def test_first_run_takes_the_whole_screen_at_native_resolution():
    """Первый запуск: окно без рамки во весь экран в родном разрешении; экран неизвестен — обычное окно."""
    from game import settings as S
    sizes = [(1024, 576), (1280, 720), (1366, 768), (1600, 900), (1920, 1080)]
    st = _FakeSettings(width=1280, height=720)
    S.choose_screen(st, (1920, 1080), sizes)
    assert (st['screen'], st['width'], st['height']) == (S.SCREEN_BORDERLESS, 1920, 1080)
    assert st['cfg'] == S.CFG_VERSION and st['fullscreen'] is False
    assert 'msaa' not in st                                   # Full HD: сглаживание остаётся как было
    st = _FakeSettings(width=1280, height=720)
    S.choose_screen(st, (3840, 2160), sizes)
    assert (st['screen'], st['width'], st['height'], st['msaa']) == (S.SCREEN_BORDERLESS, 3840, 2160, 0)
    st = _FakeSettings(width=1280, height=720)
    S.choose_screen(st, (0, 0), sizes)
    assert (st['screen'], st['width'], st['height']) == (S.SCREEN_WINDOW, 1280, 720)


def test_old_settings_file_gets_the_screen_mode_chosen_again(tmp_path, monkeypatch):
    """Файл настроек от версии 0.2 (без поля cfg) читается, а режим экрана будет подобран заново."""
    import json
    from game import settings as S
    monkeypatch.setenv('DD_USER_DIR', str(tmp_path))
    with open(tmp_path / 'settings.json', 'w', encoding='utf-8') as f:
        json.dump({'fullscreen': True, 'width': 1024, 'height': 576, 'music_volume': 0.3, 'retro': True}, f)
    st = S.Settings()
    assert not st.fresh and st.get('music_volume') == 0.3
    assert st.get('cfg') < S.CFG_VERSION                      # значит, Game._choose_screen() подберёт режим заново
    assert st.get('msaa') == 4 and st.get('smooth_textures') is False
    S.choose_screen(st, (1920, 1080), [(1280, 720)])
    st.save()
    st2 = S.Settings()
    assert (st2.get('screen'), st2.get('width'), st2.get('cfg')) == (S.SCREEN_BORDERLESS, 1920, S.CFG_VERSION)


def test_window_config_for_each_screen_mode():
    """Окно никогда не открывается сразу в полноэкранном видеорежиме: он включается после открытия."""
    from panda3d.core import ConfigVariableBool, ConfigVariableInt, ConfigVariableString, unloadPrcFile
    from panda3d.core import ConfigPageManager
    from game import app, settings as S

    def page():
        mgr = ConfigPageManager.getGlobalPtr()
        for i in range(mgr.getNumExplicitPages()):
            pg = mgr.getExplicitPage(i)
            if pg.getName() == 'deadly-district':
                return pg
        return None

    for mode, undec, origin in ((S.SCREEN_WINDOW, False, '-2 -2'), (S.SCREEN_BORDERLESS, True, '0 0'),
                                (S.SCREEN_EXCLUSIVE, True, '0 0')):
        st = _FakeSettings(dict(S.DEFAULTS))
        st.get = st.__getitem__
        st.update(screen=mode, width=1920, height=1080, msaa=8)
        app.configure(st, headless=True)
        pg = page()
        try:
            assert ConfigVariableBool('fullscreen').getValue() is False
            assert ConfigVariableBool('undecorated').getValue() is undec
            assert ConfigVariableString('win-origin').getValue() == origin
            assert ConfigVariableInt('multisamples').getValue() == 8
        finally:
            unloadPrcFile(pg)


def test_build_includes_every_asset_file():
    """Каждый файл из assets/ должен попадать в сборку: в версии 0.3 в неё чуть не ушли модели без текстур."""
    import ast
    import os
    from panda3d.core import GlobPattern           # так же сопоставляет шаблоны сборщик build_apps
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, 'setup.py'), encoding='utf-8').read()
    patterns = None
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == 'include_patterns':
                    patterns = [e.value for e in v.elts]
    assert patterns, 'include_patterns не найдены в setup.py'
    dev_only = {'assets/tex/_photo.json'}                  # нужен только генераторам текстур
    missed = []
    for base, dirs, files in os.walk(os.path.join(root, 'assets')):
        for name in files:
            rel = os.path.relpath(os.path.join(base, name), root).replace(os.sep, '/')
            if rel in dev_only:
                continue
            if not any(GlobPattern(pat).matches(rel) for pat in patterns):
                missed.append(rel)
    assert not missed, 'не попадут в сборку: %s' % missed[:10]


def test_selftest_does_not_rely_on_assert():
    """В собранном приложении assert не выполняется — самопроверка должна обходиться без него."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, 'main.py'), encoding='utf-8').read()
    body = src[src.index('def selftest():'):src.index('def main():')]
    assert '\n    assert ' not in body
    assert body.count('_need(') >= 10


def test_antialiasing_note_matches_what_the_window_was_opened_with(tmp_path, monkeypatch):
    """На экране 4K первый запуск выключает сглаживание ДО открытия окна, и меню не должно
    после этого писать «после перезапуска»: окно уже открыто без сглаживания."""
    from game import app, settings as S
    monkeypatch.setenv('DD_USER_DIR', str(tmp_path))
    monkeypatch.setattr(S, 'dpi_aware', lambda: None)
    monkeypatch.setattr(S, 'desktop_size', lambda: (3840, 2160))
    seen = {}

    class Stop(Exception):
        pass

    def fake_configure(settings, headless=False):
        seen['msaa'] = int(settings.get('msaa'))
        raise Stop()                                          # окно не открываем

    monkeypatch.setattr(app, 'configure', fake_configure)
    g = app.Game.__new__(app.Game)
    try:
        g.__init__()
    except Stop:
        pass
    assert seen['msaa'] == 0                                  # с этим значением открывается окно
    assert g._boot[0] == 0                                    # и его же помнит меню
    assert g.settings.get('screen') == S.SCREEN_BORDERLESS and g.settings.get('width') == 3840


# ---------------------------------------------------------------------------
# большой мир: три берега, мосты, рельеф
# ---------------------------------------------------------------------------
def test_terrain_is_built_for_this_layout():
    """Рельеф считается заранее (tools/gen_terrain.py) под конкретные дороги и кварталы.
    Поменяли раскладку — рельеф нужно пересобрать, иначе дороги уйдут под землю или повиснут."""
    c = City()
    t = c.terrain
    assert t.ok, 'нет файлов рельефа в assets/terrain'
    assert t.signature == c.signature(), 'рельеф устарел: запустите python tools/gen_terrain.py'
    # под дорогами и кварталами рельеф лежит ниже них
    from game.terrain import FLAT
    for seg in c.segs.values():
        if seg['bridge'] is not None:
            continue
        for k in range(5):
            u = seg['a'] + (seg['b'] - seg['a']) * (k + 0.5) / 5.0
            x, y = (u, seg['c']) if seg['kind'] == 'h' else (seg['c'], u)
            assert t.height(x, y) <= FLAT + 0.01, seg['key']
    for b in c.blocks:
        cx, cy = b.center()
        assert t.height(cx, cy) <= FLAT + 0.01, (b.i, b.j)


def test_three_shores_and_the_sea_between_them():
    c = City()
    zones = set(b.zone for b in c.blocks)
    assert {'D', 'O', 'B', 'V', 'S', 'H', 'A', 'L'} <= zones          # остров, Заречье, восточный берег
    bn = c.segs[('v', 6, 8)]                                           # Большой мост: с острова в Заречье
    be = c.segs[('h', 10, 5)]                                          # Портовый: с причалов на восток
    # под серединой каждого моста — вода, а на мосту — полотно над ней
    for seg in (bn, be):
        mid = (seg['a'] + seg['b']) * 0.5
        x, y = (mid, seg['c']) if seg['kind'] == 'h' else (seg['c'], mid)
        assert c.terrain.height(x, y) < WATER_Z
        assert not c.in_water(x, y)
        assert c.ground_z(x, y) == seg['bridge']['height'] > 5.0
        # сбоку от моста, в проливе, — вода
        sx, sy = (x, y + 40.0) if seg['kind'] == 'h' else (x + 40.0, y)
        assert c.in_water(sx, sy)
        # въезд плавный: высота растёт без ступенек
        prev = 0.0
        for k in range(1, 60):
            z = c.bridge_z(seg, k * 2.0)
            assert 0.0 <= z - prev < 0.45, (k, z, prev)
            prev = z
            if z >= seg['bridge']['height']:
                break
    assert c.zone_name(bn['c'], (bn['a'] + bn['b']) * 0.5) == 'Большой мост'
    assert c.zone_name((be['a'] + be['b']) * 0.5, be['c']) == 'Портовый мост'
    # берега не слиплись: между островом и материком — море
    assert c.in_water(c.xs[3], (c.ys[8] + c.ys[9]) * 0.5)
    assert c.in_water((c.xs[10] + c.xs[11]) * 0.5 + 20.0, c.ys[3])
    # в чистом поле за городом — суша, не дорога и не вода
    x, y = c.xs[11] - 60.0, c.ys[12]
    assert c.where(x, y)[0] is None and not c.in_water(x, y) and c.zone_at(x, y) == 'wild'


def test_every_town_is_reachable_by_road():
    c = City()
    rn = RoadNet(c)
    home = c.nearest_node(*c.landmarks['terminal']['road'])
    start = (home.i, home.j)
    for goal in ((5, 11), (8, 12), (12, 4), (13, 3), (12, 8), (12, 11)):       # Заречье, восток, трасса
        assert goal in c.nodes, goal
        path = rn.route(start, goal)
        assert path and path[0] == start and path[-1] == goal, goal
    # по трассе и мостам машины едут без светофоров и не упираются в тупик
    for l in rn.lanes:
        seg = c.segs[l.seg]
        if seg['rural']:
            assert l.next, l.seg
            assert not l.signal or not c.nodes[l.node].rural
    assert all(l.flat == (c.segs[l.seg]['bridge'] is None) for l in rn.lanes)


def test_outer_sidewalks_are_walkable_pads():
    """У крайней улицы тротуар есть и с внешней стороны; по нему ходят на высоте бордюра."""
    c = City()
    assert len(c.walk_strips) > 100
    for (x0, y0, x1, y1) in c.walk_strips[::9]:
        cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
        assert abs(c.ground_z(cx, cy) - CURB) < 1e-6
        assert not c.on_road(cx, cy) and not c.in_water(cx, cy)
    # причалы и пирс — тоже площадки
    dk = c.special['docks']
    assert abs(c.ground_z((dk['x0'] + dk['x1']) * 0.5, (dk['y0'] + dk['y1']) * 0.5) - CURB) < 1e-6
    assert c.zone_at((dk['x0'] + dk['x1']) * 0.5, dk['y0'] + 30.0) == 'docks'
    pier = c.special['pier']
    assert c.ground_z((pier['x0'] + pier['x1']) * 0.5, pier['y0'] + 5.0) == pier['z']
