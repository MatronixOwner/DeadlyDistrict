# -*- coding: utf-8 -*-
"""Deadly District — точка входа.

    python main.py              обычный запуск
    python main.py --selftest   быстрая самопроверка без окна (для сборочного конвейера)
"""
import os
import sys
import traceback


def _crash_log(text):
    try:
        from game import settings
        path = os.path.join(settings.user_dir(), 'crash.log')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path
    except Exception:
        return None


def _message_box(text):
    """Окно с сообщением об ошибке (в собранном приложении консоли нет)."""
    if not sys.platform.startswith('win'):
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, 'Deadly District', 0x10)
    except Exception:
        pass


class SelfTestError(Exception):
    pass


def _need(cond, text):
    """Проверка самотеста.  Не assert: в собранном приложении Python работает в режиме оптимизации,
    и операторы assert там не выполняются вовсе."""
    if not cond:
        raise SelfTestError(text)


def selftest():
    """Прогнать игру без окна: меню, новая игра, пауза; проверить, что все файлы на месте.

    Возвращает код выхода.  Запускается и из исходников, и из собранного приложения
    (DeadlyDistrict-selftest --selftest) — так ловится нехватка файлов в сборке."""
    from panda3d.core import loadPrcFileData
    loadPrcFileData('', 'window-type offscreen\nload-display p3tinydisplay\naudio-library-name null\n'
                        'sync-video 0\nwin-size 640 360\ntextures-power-2 none\n')
    from direct.showbase.ShowBase import ShowBase
    from game.app import Game
    game = Game(base=ShowBase(), headless=True)
    w = game.world
    dt = 1.0 / 30.0
    for _ in range(30):
        game.step(dt)
    game.new_game()
    for i in range(240):
        # пролог: сначала листаем кадры клавишей Enter, потом пропускаем остаток клавишей Esc
        key = 'enter' if i < 120 else 'escape'
        if w.missions.intro is not None and i % 12 == 0:
            game.inp._dn(key)
        else:
            game.inp._up('enter')
            game.inp._up('escape')
        game.step(dt)
    _need(w.missions.intro is None, 'intro did not finish')
    _need(w.interiors.current is not None and w.interiors.current.name == 'safehouse', 'hero is not at home')
    w.interiors.leave(instant=True)
    game.inp._dn('w')
    for _ in range(90):
        game.step(dt)
    game.inp._up('w')
    game.pause()
    for _ in range(5):
        game.step(dt)
    game.resume()
    for _ in range(5):
        game.step(dt)
    game.base.graphicsEngine.renderFrame()
    missing = sorted(set(game.assets.missing))
    _need(not missing, 'missing textures: %s' % missing)
    # mp3 для «Астрахань FM» читает встроенный ffmpeg — убеждаемся, что он подключился
    from panda3d.core import MovieAudio
    cur = MovieAudio.get(game.assets.path('sfx', 'mp3_check.mp3')).open()
    _need(cur is not None and cur.length() > 0.2, 'mp3 decoder (p3ffmpeg) is not available')
    mdl = w.models
    _need(mdl.ok and mdl.chars_ok and not mdl.failed, 'models not loaded: %s' % sorted(mdl.failed))
    _need(w.player.ped.vis is not None, 'player has no skeletal model')
    _need(all(v.minfo is not None for v in w.vehicles), 'vehicle without a model')
    # каждая модель и каждая её текстура должны быть в сборке, а не только те, что встретились за минуту игры
    from game.vehicle import SPECS, PAINTS
    for key in sorted(mdl.meta['chars']):
        for name in mdl.char_textures(key):
            tex = mdl.char_texture(name)
            _need(tex is not None and tex.getXSize() > 8, 'character texture is missing: %s (%s)' % (name, key))
    for kind in sorted(SPECS):
        _need(mdl.vehicle_info(kind, SPECS[kind]) is not None, 'vehicle model is missing: %s' % kind)
        _need(mdl.vehicle_body(kind, SPECS[kind], PAINTS[0]) is not None, 'vehicle body failed: %s' % kind)
    _need(not mdl.failed, 'models failed: %s' % sorted(mdl.failed))
    for name in sorted(mdl.meta['weapons']):
        _need(os.path.isfile(os.path.join(mdl.dir, 'weapons', name + '.bam')), 'weapon model is missing: %s' % name)
    _need(not game.audio._missing, 'missing sounds: %s' % sorted(game.audio._missing))
    print('SELFTEST OK: vehicles=%d peds=%d models=%d root=%s' % (
        len(w.vehicles), len(w.peds), len(mdl.meta['chars']) + len(mdl.meta['vehicles']), game.assets.root))
    return 0


def main():
    if '--selftest' in sys.argv:
        try:
            code = selftest()
        except Exception:
            traceback.print_exc()
            code = 1
        sys.stdout.flush()
        os._exit(code)
    try:
        from game.app import Game
        game = Game()
        game.run()
    except SystemExit:
        raise
    except Exception:
        text = traceback.format_exc()
        sys.stderr.write(text)
        sys.stderr.flush()
        path = _crash_log(text)
        last = text.strip().splitlines()[-1] if text.strip() else ''
        _message_box('Игра не смогла запуститься.\n\n%s\n\nПодробности записаны в файл:\n%s'
                     % (last, path or 'crash.log'))
        sys.exit(1)


if __name__ == '__main__':
    main()
