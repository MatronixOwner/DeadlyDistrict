# -*- coding: utf-8 -*-
"""Запуск игры без окна (программный рендер) для автоматических проверок."""
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
    loadPrcFileData('', 'window-type offscreen\nload-display p3tinydisplay\nwin-size %d %d\n'
                        'audio-library-name null\nsync-video 0\ntextures-power-2 none\nnotify-level-device fatal\n'
                        'text-minfilter linear\ntext-magfilter linear\n' % (width, height))
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


def press(g, key, dt=1.0 / 30.0):
    g.inp._dn(key)
    g.step(dt)
    g.inp._up(key)
    g.step(dt)


def start_game(g):
    """Новая игра с пропуском вступления."""
    g.new_game()
    w = g.world
    for i in range(12):
        if w.missions.intro is None:
            break
        run(g, 0.35)
        press(g, 'enter')
    run(g, 0.5)
    assert w.missions.intro is None, 'intro not skipped'
    return w


def quiet(w, peds=False):
    """Убрать с улиц случайный транспорт (и прохожих), чтобы проверки были воспроизводимыми."""
    w.traffic.enabled = False
    for v in list(w.vehicles):
        if not v.is_player:
            w.remove_vehicle(v)
    if peds:
        w.crowd.enabled = False
        for p in list(w.peds):
            if p is not w.player.ped:
                w.remove_ped(p)
