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


def selftest():
    """Прогнать игру без окна: меню, новая игра, пауза.  Возвращает код выхода."""
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
        if w.missions.intro is not None and i % 12 == 0:
            game.inp._dn('enter')
        else:
            game.inp._up('enter')
        game.step(dt)
    assert w.missions.intro is None, 'intro did not finish'
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
    assert not missing, 'missing textures: %s' % missing
    # mp3 для «Астрахань FM» читает встроенный ffmpeg — убеждаемся, что он подключился
    from panda3d.core import MovieAudio
    cur = MovieAudio.get(game.assets.path('sfx', 'mp3_check.mp3')).open()
    assert cur is not None and cur.length() > 0.2, 'mp3 decoder (p3ffmpeg) is not available'
    mdl = w.models
    assert mdl.ok and mdl.chars_ok and not mdl.failed, 'models not loaded: %s' % sorted(mdl.failed)
    assert w.player.ped.vis is not None, 'player has no skeletal model'
    assert all(v.minfo is not None for v in w.vehicles), 'vehicle without a model'
    assert not game.audio._missing, 'missing sounds: %s' % sorted(game.audio._missing)
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
