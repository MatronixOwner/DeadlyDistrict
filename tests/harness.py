# -*- coding: utf-8 -*-
"""Запуск игры без окна (программный рендер) для автоматических проверок."""
import math
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('DD_USER_DIR', tempfile.mkdtemp(prefix='dd_test_'))

from panda3d.core import loadPrcFileData, Filename      # noqa: E402

_game = [None]


def make_game(width=960, height=540):
    if _game[0] is not None:
        return _game[0]
    # По умолчанию — программный рендер TinyDisplay: он есть везде, но шейдеров не умеет.  Чтобы проверить
    # картинку с шейдерами (тени, свечение, сглаживание), задайте DD_TEST_DISPLAY=p3headlessgl — нужен OpenGL
    # без окна (EGL; годится программная Mesa llvmpipe)
    display = os.environ.get('DD_TEST_DISPLAY', 'p3tinydisplay')
    # программный OpenGL рисует «Ультру» минутами: для него окно можно уменьшить, например DD_TEST_SIZE=320x180
    if os.environ.get('DD_TEST_SIZE'):
        width, height = [int(v) for v in os.environ['DD_TEST_SIZE'].lower().split('x')]
    loadPrcFileData('', 'window-type offscreen\nload-display %s\nwin-size %d %d\n'
                        'audio-library-name null\nsync-video 0\ntextures-power-2 none\nnotify-level-device fatal\n'
                        'text-minfilter linear\ntext-magfilter linear\n' % (display, width, height))
    from direct.showbase.ShowBase import ShowBase
    from game.app import Game
    base = ShowBase()
    g = Game(base=base, headless=True)
    _game[0] = g
    return g


def shot(g, path):
    g.base.graphicsEngine.renderFrame()
    g.base.graphicsEngine.renderFrame()
    g.base.win.saveScreenshot(Filename(path))
    return path


def run(g, seconds, dt=1.0 / 30.0, keys=(), each=None):
    """Прокрутить игру на seconds секунд с зажатыми клавишами keys."""
    n = int(seconds / dt)
    for k in keys:
        g.inp._dn(k)
    for i in range(n):
        if each is not None:
            each(i)
        g.step(dt)
    for k in keys:
        g.inp._up(k)


def side(x, y, yaw, right=0.0, fwd=0.0):
    """Точка сбоку от курса yaw: right метров вправо и fwd вперёд.  Улицы города изогнуты, поэтому
    «в двух метрах от полосы» считается от её курса в этой точке, а не по осям мира."""
    import math
    return (x + math.sin(yaw) * right + math.cos(yaw) * fwd, y - math.cos(yaw) * right + math.sin(yaw) * fwd)


def press(g, key, dt=1.0 / 30.0):
    g.inp._dn(key)
    g.step(dt)
    g.inp._up(key)
    g.step(dt)


def start_game(g, street=True, story=False, hero=False):
    """Новая игра с пропуском пролога.

    story=False — сюжет считается пройденным и Брюс не звонит: большинству проверок нужен просто
    свободный город.  hero=False — по той же причине в гараже нет «Ласточки», машины героя (и она
    туда не возвращается).  street: если герой оказался в помещении, вывести его на улицу."""
    g.new_game()
    w = g.world
    for i in range(12):
        if w.missions.intro is None:
            break
        run(g, 0.35)
        press(g, 'escape')
    ms = w.missions
    assert ms.intro is None, 'intro not skipped'
    if not story:
        from game import missions as M
        ms.done |= M.STORY_IDS
        ms.call_t = 1e9
        ms.refresh_contacts()
        ms.sync_story()
    if not hero:
        w.hero_car.remove()
    run(g, 0.5)
    if street and w.interiors.current is not None:
        w.interiors.leave(instant=True)
        run(g, 0.2)
    return w


def quiet(w, peds=False):
    """Убрать с улиц случайный транспорт (и прохожих), чтобы проверки были воспроизводимыми."""
    w.traffic.enabled = False
    for v in list(w.vehicles):
        # машины в интерьерах остаются; машина героя (если проверка её оставила) — тоже
        if not v.is_player and getattr(v, 'room', None) is None and not v.hero:
            w.remove_vehicle(v)
    if peds:
        w.crowd.enabled = False
        for p in list(w.peds):
            if p is not w.player.ped and p.room is None:              # жильцы интерьеров остаются
                w.remove_ped(p)


def reachable(w, tx, ty, car=False, step=1.0, margin=60.0, maxd=220.0):
    """Можно ли добраться до точки от ближайших дорог (пешком или на машине): поиск пути по сетке.

    Проверяет статику мира (стены, заборы, воду), машины и людей не учитывает."""
    from collections import deque
    from game.collision import F_PED, F_CAR
    st = w.static
    c = w.city
    r = 1.25 if car else w.player.ped.radius
    mask = F_CAR if car else F_PED
    starts = []
    for l in w.roadnet.lanes_near(tx, ty, 0.0, maxd):
        if l.turn is not None:
            continue
        for s in (0.0, l.length * 0.5, l.length):
            x, y, _ = l.pos(s)
            starts.append((math.hypot(x - tx, y - ty), x, y))
    starts.sort()
    starts = starts[:12]
    if not starts:
        return False
    x0 = min([tx] + [s[1] for s in starts]) - margin
    y0 = min([ty] + [s[2] for s in starts]) - margin
    x1 = max([tx] + [s[1] for s in starts]) + margin
    y1 = max([ty] + [s[2] for s in starts]) + margin
    wn = int((x1 - x0) / step) + 1
    hn = int((y1 - y0) / step) + 1
    cache = {}

    zs = {}

    def free(i, j):
        v = cache.get((i, j))
        if v is None:
            x, y = x0 + i * step, y0 + j * step
            z = c.ground_z(x, y)
            zs[(i, j)] = z
            v = not st.overlap_circle(x, y, r, mask) and not (c.in_water(x, y) and z < -0.2)
            cache[(i, j)] = v
        return v
    goal = set((int(round((x - x0) / step)), int(round((y - y0) / step))) for d, x, y in starts)
    ti, tj = int(round((tx - x0) / step)), int(round((ty - y0) / step))
    reach = 3 if car else 1                                  # машину достаточно подогнать вплотную
    seen = set((ti + di, tj + dj) for di in range(-reach, reach + 1) for dj in range(-reach, reach + 1)
               if free(ti + di, tj + dj))
    q = deque(seen)
    while q:
        i, j = q.popleft()
        if (i, j) in goal:
            return True
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (i + di, j + dj)
            if 0 <= n[0] < wn and 0 <= n[1] < hn and n not in seen and free(n[0], n[1]):
                if abs(zs[n] - zs[(i, j)]) > 0.75 * step:
                    continue                                 # уступ: ни шагнуть, ни съехать (обрыв палубы, край пирса)
                seen.add(n)
                q.append(n)
    return False
