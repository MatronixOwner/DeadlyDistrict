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
    ms = w.missions
    _need(ms.intro is None, 'intro did not finish')
    _need(w.interiors.current is None and w.player.state == 'foot', 'hero is not on the street after the intro')
    # после пролога звонит Брюс: сюжет начинается со звонка, реплики листаются клавишей Enter
    for i in range(600):
        if ms.active is not None and i % 10 == 0:
            game.inp._dn('enter')
        else:
            game.inp._up('enter')
        game.step(dt)
        if ms.active is not None and w.player.controls and not w.hud.phone_on:
            break
    game.inp._up('enter')
    _need(ms.active is not None and ms.active.spec['id'] == 's1', 'the story did not start with the phone call')
    _need(not w.hud.phone_on, 'the phone call did not end')
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
    _need(all(v.minfo is not None or v.bparts is not None for v in w.vehicles), 'vehicle without a model')
    # каждая модель и каждая её текстура должны быть в сборке, а не только те, что встретились за минуту игры
    from game.vehicle import SPECS, PAINTS
    from game import bikes, tuning
    for key in sorted(mdl.meta['chars']):
        for name in mdl.char_textures(key):
            tex = mdl.char_texture(name)
            _need(tex is not None and tex.getXSize() > 8, 'character texture is missing: %s (%s)' % (name, key))
    for kind in sorted(SPECS):
        if SPECS[kind].bike:                        # мотоциклы и их родня: готовые модели или сборка кодом
            bp = bikes.build(game.assets, kind, PAINTS[0])
            _need(bp is not None and not bp['body'].isEmpty() and len(bp['wheels']) >= 2, 'bike failed: %s' % kind)
            continue
        _need(mdl.vehicle_info(kind, SPECS[kind]) is not None, 'vehicle model is missing: %s' % kind)
        _need(mdl.vehicle_body(kind, SPECS[kind], PAINTS[0]) is not None, 'vehicle body failed: %s' % kind)
    _need(not mdl.failed, 'models failed: %s' % sorted(mdl.failed))
    for name in sorted(mdl.meta['weapons']):
        _need(os.path.isfile(os.path.join(mdl.dir, 'weapons', name + '.bam')), 'weapon model is missing: %s' % name)
    for clip in ('ride', 'drive', 'sit', 'sit_ground', 'kneel', 'phone'):
        _need(clip in mdl.meta['anims'], 'animation clip is missing: %s' % clip)
    # шрифты интерфейса: без файла Panda молча подставит встроенный шрифт без кириллицы
    for name in ('Inter-Medium.ttf', 'Inter-Bold.ttf', 'Oswald-Medium.ttf', 'Oswald-Bold.ttf', 'Caveat-Bold.ttf'):
        _need(os.path.isfile(game.assets.path('fonts', name)), 'font is missing: %s' % name)
    # ездок на мотоцикле, полный тюнинг машины и гараж
    pl = w.player
    px, py = pl.pos()
    yaw = pl.ped.yaw
    bike = w.spawn_vehicle('chopper', px + 3.0, py, yaw)
    pl.enter_vehicle(bike, silent=True)
    for _ in range(10):
        game.step(dt)
    _need(pl.vehicle is bike and pl.ped.vis.cur == 'mix' and not pl.ped.node.isHidden(), 'the rider is not on the bike')
    for kind in ('chopper', 'bicycle', 'bmx'):
        _need(bikes.modelled(kind), 'bike model is missing: %s' % kind)
    _need(bike._arms is pl.ped.vis and pl.ped.vis._bars is not None, 'the rider does not hold the handlebar')
    pl.leave_vehicle(force=True)
    car = w.spawn_vehicle('sedan', px - 4.0, py, yaw)
    full = dict((k, len(opts)) for k, title, opts in tuning.parts_for(car))
    _need(tuning.TOTAL >= 30 and len(full) >= 12, 'tuning list is too short')
    car.apply_tune(full)
    for _ in range(10):
        game.step(dt)
    _need(car.tune == tuning.clean(full), 'tuning was not applied')
    gar = w.city.special['garage']
    gx0, gy0, gx1, gy1 = gar['rect']
    pl.teleport(gar['front'][0], gar['front'][1])
    car.x, car.y = (gx0 + gx1) * 0.5, (gy0 + gy1) * 0.5
    car.sync()
    for _ in range(30):
        game.step(dt)
    kept = w.garage.state()
    _need(len(kept) == 1 and kept[0]['kind'] == 'sedan' and kept[0].get('tune'), 'the garage did not keep the car')
    game.base.graphicsEngine.renderFrame()
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
