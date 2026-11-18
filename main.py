# -*- coding: utf-8 -*-
"""Deadly District — точка входа.

    python main.py              обычный запуск
    python main.py --tester     запуск с меню тестера (F9); настройки и сохранения — в отдельной папке
    python main.py --selftest   быстрая самопроверка без окна (для сборочного конвейера)
"""
import math
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


def enable_tester():
    """Включить меню тестера (F9).  Вызывается до создания игры.

    У сборки для тестера своя папка настроек и сохранений: читы и пропуск заданий не должны
    попадать в сохранение обычной игры."""
    import importlib
    import game
    from game import settings
    try:
        importlib.import_module('game.tester')
    except ImportError:
        return False                    # обычная сборка: меню тестера в ней нет, ключ ничего не меняет
    game.TESTER = True
    settings.APP_NAME = 'DeadlyDistrict-tester'
    return True


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
    ms = w.missions
    hero = w.hero_car.v
    _need(hero is not None and hero.kind == 'retro' and hero in w.garage.cars, 'the hero car is not in the garage')

    def enter_until(done, frames):
        """Листать кадры пролога клавишей Enter, пока не выполнится условие."""
        for i in range(frames):
            if done():
                break
            if i % 12 == 0:
                game.inp._dn('enter')
            else:
                game.inp._up('enter')
            game.step(dt)
        game.inp._up('enter')
        game.step(dt)

    # пролог: сценка у банка, потом погоня — машину ведёт игрок, в салоне видно всех троих
    enter_until(lambda: ms.intro is None or ms.intro['play'], 600)
    it = ms.intro
    _need(it is not None and it['play'], 'the prologue chase did not start')
    car = it['car']
    _need(w.player.vehicle is car and car.cabin is not None and len(car.cabin['who']) == 3 and car.swheel is not None,
          'the getaway car has no cabin with its crew')
    _need(w.police.level == 3 and it['marker'] is not None, 'the prologue chase has no police or no goal')
    game.inp._dn('w')
    for _ in range(60):
        game.step(dt)
    _need(car.speed > 3.0, 'the getaway car does not drive')
    # до моста — там заслон; дальше арест, «три года спустя», автобус
    car.x, car.y, car.yaw = it['marker'].x, it['marker'].y - 20.0, math.pi / 2
    car.sync()
    for _ in range(150):
        if it['end'] is not None:
            break
        game.step(dt)
    game.inp._up('w')
    _need(it['end'] == 'bridge', 'the prologue chase did not end on the bridge: %s' % it['end'])
    for _ in range(45):
        game.step(dt)
    _need(len(it['cars']) == 3 and len(it['peds']) >= 6, 'no roadblock on the bridge')
    enter_until(lambda: ms.intro is None, 900)
    _need(ms.intro is None, 'intro did not finish')
    _need(w.interiors.current is None and w.player.state == 'foot', 'hero is not on the street after the intro')
    _need(w.police.level == 0 and [v for v in w.vehicles if v.kind == 'retro'] == [hero],
          'the prologue left its props behind')
    # после пролога звонит Брюс: сюжет начинается со звонка, реплики листаются клавишей Enter
    for i in range(300):
        if w.hud.phone_on:
            break
        game.step(dt)
    _need(ms.active is not None and ms.active.spec['id'] == 's1' and w.hud.phone_on,
          'the story did not start with the phone call')
    for i in range(600):
        if not w.hud.phone_on:
            break
        if i % 10 == 0:
            game.inp._dn('enter')
        else:
            game.inp._up('enter')
        game.step(dt)
    game.inp._up('enter')
    game.step(dt)
    _need(not w.hud.phone_on and w.player.controls and ms.active is not None, 'the phone call did not end')
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
    from game import props
    _need(len(props.models()) >= 7, 'street prop models (assets/models/props.json) not loaded')
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
    _need(sorted(k['kind'] for k in kept) == ['retro', 'sedan'] and all(k.get('tune') for k in kept if k['kind'] == 'sedan'),
          'the garage did not keep the car')
    # машина героя: водитель виден в салоне, руки — на рулевом колесе
    pl.teleport(hero.x - 1.6, hero.y)
    pl.enter_vehicle(hero, silent=True)
    for _ in range(10):
        game.step(dt)
    _need(pl.vehicle is hero and not pl.ped.node.isHidden() and hero.cabin['who'].get(pl.ped) == 0 and
          hero._arms is pl.ped.vis, 'the driver is not visible in the hero car')
    pl.leave_vehicle(force=True)
    for _ in range(10):
        game.step(dt)
    game.base.graphicsEngine.renderFrame()
    _need(not game.audio._missing, 'missing sounds: %s' % sorted(game.audio._missing))
    import game as game_pkg
    if game_pkg.TESTER:
        _selftest_tester(game, dt)
    else:
        _need(game.tester is None, 'the regular game must not have the tester menu')
        if not os.path.isfile(getattr(game_pkg, '__file__', None) or ''):
            # собранное приложение: в обычной сборке модуля меню тестера быть не должно
            _need(not enable_tester() and game_pkg.TESTER is False,
                  'the regular build contains the tester menu (game.tester)')
    _need(game._errors_total == 0, 'errors were reported during the self-test: %d' % game._errors_total)
    print('SELFTEST OK: vehicles=%d peds=%d models=%d tester=%s root=%s' % (
        len(w.vehicles), len(w.peds), len(mdl.meta['chars']) + len(mdl.meta['vehicles']),
        'yes' if game.tester is not None else 'no', game.assets.root))
    return 0


def _selftest_tester(game, dt):
    """Сборка для тестера: меню на F9 открывается, и каждое его действие работает."""
    import shutil
    import tempfile
    from game import settings
    _need(game.tester is not None, 'the tester build has no tester menu')
    _need(settings.APP_NAME == 'DeadlyDistrict-tester', 'the tester build must keep its saves in its own folder')
    # засчитанное задание сохраняет игру: настоящее сохранение тестера самопроверка трогать не должна
    keep = os.environ.get('DD_USER_DIR')
    tmp = tempfile.mkdtemp(prefix='dd_selftest_')
    os.environ['DD_USER_DIR'] = tmp
    try:
        _selftest_tester_menu(game, dt)
        _need(os.path.isfile(os.path.join(tmp, 'save0.json')), 'passing a mission did not save the game')
    finally:
        if keep is None:
            os.environ.pop('DD_USER_DIR', None)
        else:
            os.environ['DD_USER_DIR'] = keep
        shutil.rmtree(tmp, ignore_errors=True)


def _selftest_tester_menu(game, dt):
    from game import missions as M
    t = game.tester
    w = game.world
    pl = w.player
    ms = w.missions

    def steps(n):
        for _ in range(n):
            game.step(dt)

    def key(name):
        game.inp._dn(name)
        game.step(dt)
        game.inp._up(name)
        game.step(dt)
    key('f9')
    _need(t.opened and game.state == 'pause', 'F9 did not open the tester menu')
    game.base.graphicsEngine.renderFrame()
    for name in ('arrow_down', 'enter', 'arrow_down', 'enter'):          # Телепорт -> Комнаты
        key(name)
    _need([m.title for m in game.ui.stack] == ['Тестер', 'Телепорт', 'Комнаты'],
          'tester submenus do not open: %s' % ' / '.join(m.title for m in game.ui.stack))
    game.base.graphicsEngine.renderFrame()
    key('f9')
    _need(not t.opened and game.state == 'play', 'F9 did not close the tester menu')
    # бессмертие и розыск
    _need(t.open(), 'the tester menu did not open')
    t.set_god(True)
    t.set_wanted(3)
    t.set_hold(True)
    t.heal()
    t.arm()
    t.cash(10000)
    t.shift_time(1)
    t.shift_weather(1)
    t.close()
    pl.ped.hurt(500.0, None, 'bullet')
    steps(10)
    _need(pl.ped.health == pl.ped.max_health and w.police.level == 3, 'god mode or the wanted level did not hold')
    _need(t.open(), 'the tester menu did not open')
    t.set_hold(False)
    t.set_wanted(0)
    # задание, перенос к его цели, зачёт
    spec = [s for s in M.MISSIONS if s['id'] == 'v2'][0]
    t.start_mission(spec)
    _need(ms.active is not None and ms.active.spec is spec and set(['s1', 's2', 'v1']) <= ms.done,
          'the tester menu did not start a mission')
    for i in range(600):
        game.inp._dn('space') if i % 6 == 0 else game.inp._up('space')
        game.step(dt)
        if i > 30 and not pl.freeze and w.cam.override is None and not w.hud.phone_on:
            break
    game.inp._up('space')
    _need(t.target() is not None and t.open(), 'the mission has no target after the briefing')
    t.to_target()
    steps(20)
    _need(game.state == 'play' and ms.active is not None, 'teleport to the mission target failed')
    _need(t.open(), 'the tester menu did not open')
    t.pass_mission()
    steps(20)
    _need(ms.active is None and 'v2' in ms.done, 'the tester menu did not pass the mission')
    # все места, все комнаты, весь транспорт
    for title, foot, car in t.places():
        _need(t.open(), 'the tester menu did not open')
        t.go(title, foot, car)
        steps(4)
        _need(game.state == 'play' and pl.state == 'foot' and not pl.ped.dead, 'teleport failed: %s' % title)
    for room in w.interiors.order:
        _need(t.open(), 'the tester menu did not open')
        t.go_room(room)
        steps(4)
        _need(w.interiors.current is room, 'teleport into a room failed: %s' % room.name)
    title, foot, car = t.places()[0]
    _need(t.open(), 'the tester menu did not open')
    t.go(title, foot, car)
    steps(4)
    from game.vehicle import SPECS
    for kind in sorted(SPECS):
        _need(t.open(), 'the tester menu did not open')
        t.spawn(kind)
        steps(4)
        _need(pl.vehicle is not None and pl.vehicle.kind == kind, 'vehicle was not spawned: %s' % kind)
    _need(t.open(), 'the tester menu did not open')
    t.set_god(False)
    t.close()
    steps(10)
    game.base.graphicsEngine.renderFrame()


def main():
    if '--tester' in sys.argv:
        enable_tester()
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
