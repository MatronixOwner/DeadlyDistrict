# -*- coding: utf-8 -*-
"""Приложение: окно, главный цикл, состояния игры и меню."""
import math
import os
import sys
import time

from panda3d.core import (loadPrcFileData, WindowProperties, Filename, TextNode, CardMaker, TransparencyAttrib,
                          AntialiasAttrib, ClockObject, PandaNode)

from . import GAME_TITLE, __version__
from . import settings as settings_mod
from . import audio as audio_mod
from .settings import (Settings, DRAW_DIST, TRAFFIC_LEVELS, SCREEN_WINDOW, SCREEN_BORDERLESS, SCREEN_EXCLUSIVE,
                       SCREEN_NAMES, MSAA_LEVELS)
from .sky import set_lens_range

RESOLUTIONS = [(1024, 576), (1280, 720), (1366, 768), (1600, 900), (1920, 1080), (2560, 1440), (3840, 2160)]

CONTROLS_TEXT = (
    'ПЕШКОМ\n'
    'W A S D — движение, мышь — обзор\n'
    'Shift — бег, пробел — прыжок\n'
    'ЛКМ — удар или выстрел, ПКМ — прицел\n'
    'Колесо мыши, Q / E, 1–9 — выбор оружия\n'
    'F или Enter — сесть в машину (угнать)\n'
    '\n'
    'ЗА РУЛЁМ\n'
    'W / S — газ, тормоз и задний ход, A / D — руль\n'
    'Пробел — ручной тормоз, B — взгляд назад\n'
    'ЛКМ — стрельба из окна (пистолет, «Узи»)\n'
    'H — сигнал или сирена, R — радио\n'
    'T — подработка в такси, F — выйти из машины\n'
    '\n'
    'ОБЩЕЕ\n'
    'C — дальность камеры, Esc — пауза и карта\n'
    'F12 — снимок экрана')

CREDITS_TEXT = (
    'Город теперь твой, Макс.\n'
    '\n'
    'DEADLY DISTRICT — ГИБЛЫЙ РАЙОН\n'
    'Игра в духе классических криминальных боевиков начала 2000-х.\n'
    '\n'
    'Люди — Elbolilloduro («Characters PSX»), анимация — Mesh2Motion.\n'
    'Машины — GGBot («PSX Style Cars»), оружие — Quaternius.\n'
    'Материалы города — Classic64 Asset Library (Craig Snedeker).\n'
    'Здания, автобус, вывески, звуки и музыка созданы кодом игры.\n'
    '\n'
    'Движок: Panda3D.  Шрифты: Russo One, Dela Gothic One, Oswald (OFL).\n'
    '\n'
    'Спасибо за игру! Город открыт: тайники, такси и хаос ждут.')


def configure(settings, headless=False):
    s = settings
    mode = int(s.get('screen'))
    msaa = int(s.get('msaa'))
    prc = [
        'window-title %s' % GAME_TITLE,
        'win-size %d %d' % (int(s.get('width')), int(s.get('height'))),
        # Окно всегда открывается обычным образом (в рамке либо без неё, во весь экран).  Полноэкранный
        # видеорежим, если он выбран, включается уже после открытия окна: откажет видеокарта — игра
        # просто останется в окне, а не упадёт на запуске.
        'fullscreen 0',
        'undecorated %d' % (0 if mode == SCREEN_WINDOW else 1),
        'win-origin %s' % ('-2 -2' if mode == SCREEN_WINDOW else '0 0'),
        'sync-video %d' % (1 if s.get('vsync') else 0),
        'textures-power-2 none',
        'framebuffer-multisample %d' % (1 if msaa > 0 else 0),
        'multisamples %d' % max(0, msaa),
        'show-frame-rate-meter 0',
        'model-cache-dir',
        'audio-library-name p3openal_audio',
        'load-audio-type * p3ffmpeg',           # mp3, m4a и прочее — для песен игрока на радио
        'notify-level warning',
        'default-directnotify-level warning',
        'text-minfilter linear',
        'text-magfilter linear',
        'text-page-size 512 512',
        'garbage-collect-states 1',
        'want-pstats 0',
        'paste-emit-keystrokes 0',
        'depth-bits 24',
    ]
    if not headless:
        prc.append('load-display pandagl')
        prc.append('aux-display p3tinydisplay')
    loadPrcFileData('deadly-district', '\n'.join(prc))


class Game(object):

    def __init__(self, base=None, headless=False):
        self.settings = Settings()
        self.headless = headless
        self._win_todo = []                # отложенные шаги смены режима экрана: (через сколько кадров, что)
        opened_here = base is None
        if base is None and not headless:
            self._choose_screen()          # может поменять и сглаживание, поэтому — до запоминания
        # с какими значениями открыто окно: по ним меню пишет «после перезапуска»
        self._boot = (int(self.settings.get('msaa')), bool(self.settings.get('vsync')))
        if base is None:
            configure(self.settings, headless)
            from direct.showbase.ShowBase import ShowBase
            base = ShowBase()
        self.base = base
        if opened_here and not headless:
            self.settings.save()
            if int(self.settings.get('screen')) == SCREEN_EXCLUSIVE:
                self.apply_window()         # запрос выполнится на первом же кадре экрана загрузки
        base.disableMouse()
        base.setBackgroundColor(0.02, 0.02, 0.03)
        from .assets import Assets
        from .audio import Audio
        from .input import Input
        self.assets = Assets(base.loader)
        self.assets.smooth_textures = bool(self.settings.get('smooth_textures'))
        self.audio = Audio(base, self.assets, self.settings)
        self.inp = Input(base)
        self.state = 'loading'
        self.world = None
        self.ui = None
        self.dt = 0.016
        self.t = 0.0
        self.attract_t = 0.0
        self.focus_lost = False
        self.credits_pending = False
        self._errors_row = 0
        self._errors_total = 0
        self._set_icon()
        try:
            base.render.setAntialias(AntialiasAttrib.MMultisample)
        except Exception:
            pass
        self._loading_begin()
        from .world import World
        from .sky import Sky
        from .hud import Hud
        from .missions import Missions
        from .menu import MenuUI
        self.world = World(self, progress=self._loading_progress)
        w = self.world
        w.sky = Sky(w)
        self._loading_progress(0.88, 'Настраиваем приборы…')
        w.hud = Hud(w)
        w.missions = Missions(w)
        self.ui = MenuUI(self)
        self._loading_progress(1.0, 'Готово')
        self._loading_end()
        base.accept('f12', self.screenshot)
        base.taskMgr.add(self._update, 'game-update', sort=10)
        self.to_main_menu(first=True)

    # ------------------------------------------------------------------
    def _set_icon(self):
        try:
            path = self.assets.path('icon', 'icon.ico')
            props = WindowProperties()
            props.setIconFilename(path)
            props.setTitle(GAME_TITLE)
            self.base.win.requestProperties(props)
        except Exception:
            pass

    def _loading_begin(self):
        from direct.gui.OnscreenText import OnscreenText
        a2d = self.base.aspect2d
        self._ld = a2d.attachNewNode('loading')
        f1 = self.assets.font('DelaGothicOne.ttf', 110, outline=3.0)
        f2 = self.assets.font('RussoOne.ttf', 56, outline=2.0)
        OnscreenText(text='DEADLY DISTRICT', parent=self._ld, pos=(0, 0.25), scale=0.2, fg=(1.0, 0.82, 0.2, 1),
                     font=f1, align=TextNode.ACenter)
        OnscreenText(text='ГИБЛЫЙ РАЙОН', parent=self._ld, pos=(0, 0.1), scale=0.08, fg=(0.9, 0.3, 0.25, 1), font=f1,
                     align=TextNode.ACenter)
        self._ld_text = OnscreenText(text='Загрузка…', parent=self._ld, pos=(0, -0.42), scale=0.06,
                                     fg=(0.85, 0.85, 0.85, 1), font=f2, align=TextNode.ACenter, mayChange=True)
        cm = CardMaker('bar_bg')
        cm.setFrame(-0.6, 0.6, -0.55, -0.52)
        bg = self._ld.attachNewNode(cm.generate())
        bg.setColor(0.2, 0.2, 0.22, 1)
        cm = CardMaker('bar')
        cm.setFrame(0, 1.2, -0.55, -0.52)
        self._ld_bar = self._ld.attachNewNode(cm.generate())
        self._ld_bar.setColor(1.0, 0.82, 0.2, 1)
        self._ld_bar.setPos(-0.6, 0, 0)
        self._ld_bar.setScale(0.001, 1, 1)
        self._render()

    def _loading_progress(self, frac, text=''):
        try:
            self._ld_bar.setScale(max(0.001, min(1.0, frac)), 1, 1)
            if text:
                self._ld_text.setText(text)
            self._render()
        except Exception:
            pass

    def _loading_end(self):
        self._ld.removeNode()
        self._ld = None

    def _render(self):
        try:
            self.base.graphicsEngine.renderFrame()
        except Exception:
            pass

    def screenshot(self):
        try:
            name = os.path.join(settings_mod.user_dir(), 'screenshot_%d.png' % int(time.time()))
            self.base.win.saveScreenshot(Filename.fromOsSpecific(name))
            if self.world is not None and self.state == 'play':
                self.world.hud.help('Снимок сохранён.', 2.0)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # сброс и запуск игры
    # ------------------------------------------------------------------
    def reset_world(self):
        from .missions import Missions
        w = self.world
        ms = w.missions
        if ms is not None:
            ms.destroy()
        for v in list(w.vehicles):
            v.remove()
        pl = w.player
        for p in list(w.peds):
            if not p.is_player:
                p.remove()
        w.vehicles = []
        w.peds = [pl.ped]
        w.traffic.parked = {}
        w.traffic.spot_block = {}
        w.traffic.density = 1.0
        w.crowd.density = 1.0
        w.police.locked = None
        w.police.clear()
        w.police.units = []
        w.police.cops = []
        w.weapons.clear()
        w.fx.clear()
        w.emitters = []
        w.respawn_kind = None
        w.respawn_t = 0.0
        w.cam.override = None
        for k in list(w.stats.keys()):
            w.stats[k] = 0.0 if isinstance(w.stats[k], float) else 0
        pl.reset()
        w.sky.day = 1
        w.sky.set_weather('clear')
        w.sky.set_time(8.0)
        hud = w.hud
        hud.money_show = 0
        hud.clear_subtitles()
        hud.help_text.hide()
        hud.help_t = 0.0
        hud.big_t = hud.title_t = hud.zone_t = hud.veh_t = hud.radio_t = 0.0
        hud.zone_name = None
        hud.set_timer(None)
        hud.set_counter(None)
        w.interiors.reset()
        w.missions = Missions(w)
        self.audio.stop_loops()
        w.radio_station = -1

    def to_main_menu(self, first=False):
        w = self.world
        self.reset_world()
        self.state = 'menu'
        w.hud.stash(False)
        pl = w.player
        pl.freeze = True
        pl.ped.node.hide()
        # красивое место для фона: перекрёсток в центре
        n = w.city.nodes.get((6, 2)) or w.city.nearest_node(0.0, 0.0)
        self.attract_pos = (n.x, n.y)
        pl.ped.x, pl.ped.y = n.x, n.y - 30.0
        w.sky.set_time(18.6)
        w.hud.show(False)
        w.hud.fade(0.0, instant=True)
        w.traffic.populate()
        w.crowd.populate()
        self.inp.capture_mouse(False)
        self.audio.pause_all(False)
        self.audio.music('theme', 0.9, random_start=False)
        self.ui.close_all()
        self.ui.show_logo = True
        self.ui.open(self.main_menu())

    def new_game(self):
        self._begin()
        w = self.world
        w.player.add_money(0)
        w.missions.start_intro()

    def continue_game(self):
        data = settings_mod.load_save()
        if data is None:
            return
        self._begin()
        w = self.world
        w.missions.load_game(data)
        w.sky.set_time(w.sky.hour)
        w.hud.fade(1.0, instant=True)
        w.hud.fade(0.0, 0.8)

    def _begin(self):
        w = self.world
        self.reset_world()
        w.hud.stash(False)
        self.ui.show_logo = False
        self.ui.close_all()
        self.audio.music(None)
        self.audio.pause_all(False)
        pl = w.player
        pl.ped.node.show()
        w.hud.show(True)
        w.traffic.populate()
        w.crowd.populate()
        w.cam.snap()
        self.state = 'play'
        self.inp.clear()
        self.inp.capture_mouse(True)

    def pause(self):
        if self.state != 'play':
            return
        self.state = 'pause'
        self.inp.capture_mouse(False)
        self.audio.pause_all(True)
        self.world.hud.stash(True)
        self.ui.open(self.pause_menu())

    def resume(self):
        self.ui.close_all()
        self.world.hud.stash(False)
        self.state = 'play'
        self.audio.pause_all(False)
        self.inp.clear()
        self.inp.capture_mouse(True)

    def quit(self):
        self.settings.save()
        try:
            self.base.userExit()
        except SystemExit:
            raise
        except Exception:
            sys.exit(0)

    # ------------------------------------------------------------------
    # меню
    # ------------------------------------------------------------------
    def main_menu(self):
        from .menu import Menu, Item
        has_save = settings_mod.load_save() is not None
        items = [
            Item('Новая игра', self.new_game),
            Item('Продолжить', self.continue_game, enabled=has_save),
            Item('Настройки', lambda: self.ui.open(self.settings_menu())),
            Item('Управление', lambda: self.ui.open(self.text_menu('Управление', CONTROLS_TEXT, 0.052))),
            Item('Выход', self.quit),
        ]
        m = Menu(self.ui, '', items, x=-0.45, top=0.22, spacing=0.14, scale=0.1,
                 subtitle='Версия %s — стрелки или мышь, Enter — выбрать' % __version__)
        if has_save:
            m.sel = 1
        return m

    def pause_menu(self):
        from .menu import Menu, Item
        items = [
            Item('Продолжить', self.resume),
            Item('Карта', self.open_map),
            Item('Статистика', lambda: self.ui.open(self.text_menu('Статистика', self.stats_text(), 0.06))),
            Item('Настройки', lambda: self.ui.open(self.settings_menu())),
            Item('Управление', lambda: self.ui.open(self.text_menu('Управление', CONTROLS_TEXT, 0.052))),
            Item('В главное меню', self.to_main_menu),
            Item('Выйти из игры', self.quit),
        ]
        return Menu(self.ui, 'Пауза', items, back=self.resume)

    def text_menu(self, title, text, scale=0.06, back=None):
        from .menu import Menu, Item
        m = Menu(self.ui, title, [Item('Назад', back or self.ui.close)], text=text, back=back, top=0.44)
        m.text_scale = scale
        return m

    def open_map(self):
        from .menu import Menu, Item, build_map
        node = build_map(self)
        node.reparentTo(self.ui.root)
        node.setPos(0.42, 0, -0.02)
        self.ui.set_extra(node)

        def back():
            self.ui.set_extra(None)
            self.ui.close()
        w = self.world
        px, py = w.map_pos()
        done, total = w.missions.progress()
        text = ('Район: %s\nВремя: %s, день %d\nПогода: %s\n\nСюжет: %d из %d\nТайники: %d из %d\n\n'
                'В — Вано, Р — Роза\nЗ — Захар, Г — Гром\nП — Проф') % (
            w.city.zone_name(px, py) or '—', w.sky.clock_text(), w.sky.day, self._weather_name(), done, total,
            len(w.missions.packages), len(w.city.packages))
        m = Menu(self.ui, 'Карта', [Item('Назад', back)], text=text, back=back, x=-1.25, top=0.44)
        m.text_scale = 0.055
        self.ui.open(m)

    def _weather_name(self):
        from .sky import WEATHER_NAMES
        return WEATHER_NAMES.get(self.world.sky.weather, '')

    def stats_text(self):
        w = self.world
        s = w.stats
        done, total = w.missions.progress()
        t = int(s['play_time'])
        lines = [
            'Сюжетных заданий: %d из %d' % (done, total),
            'Тайников найдено: %d из %d' % (len(w.missions.packages), len(w.city.packages)),
            'Денег: $%d' % w.player.money,
            'Время в игре: %d ч %02d мин' % (t // 3600, (t % 3600) // 60),
            'Проехано: %.1f км, пройдено: %.1f км' % (s['dist_car'] / 1000.0, s['dist_foot'] / 1000.0),
            'Угнано машин: %d' % s['stolen'],
            'Уничтожено машин: %d' % s['wrecks'],
            'Убито: %d (полицейских: %d)' % (s['kills'], s['cops']),
            'Пассажиров в такси: %d' % s['taxi'],
            'Максимум звёзд розыска: %d' % s['max_wanted'],
            'Потрачено: %d, арестован: %d' % (s['wasted'], s['busted']),
        ]
        return '\n'.join(lines)

    def settings_menu(self):
        from .menu import Menu, Item
        s = self.settings
        w = self.world

        def pct(key):
            return lambda: '%d%%' % int(round(float(s.get(key)) * 100))

        def ch_vol(key):
            def f(d):
                s.set(key, round(min(1.0, max(0.0, float(s.get(key)) + d * 0.1)), 2))
                self.audio.set_volumes(s.get('sfx_volume'), s.get('music_volume'))
                if key == 'sfx_volume':
                    self.audio.play('pickup', 0.8)
            return f

        def ch_sens(d):
            s.set('mouse_sens', round(min(3.0, max(0.2, float(s.get('mouse_sens')) + d * 0.1)), 2))

        def toggle(key, after=None):
            def f(d=1):
                s.set(key, not s.get(key))
                if after is not None:
                    after()
            return f

        def yn(key):
            return lambda: 'Да' if s.get(key) else 'Нет'

        def ch_draw(d):
            s.set('draw_distance', int(min(2, max(0, int(s.get('draw_distance')) + d))))
            dd = DRAW_DIST[int(s.get('draw_distance'))]
            w.sky.fog_start, w.sky.far = dd
            set_lens_range(self.base, w.sky.far)
            w.sky._apply(0.0)

        def ch_traffic(d):
            s.set('traffic', int(min(2, max(0, int(s.get('traffic')) + d))))
            lv = TRAFFIC_LEVELS[int(s.get('traffic'))]
            w.traffic.max_cars = lv[0]
            w.crowd.max_peds = lv[1]

        def res_list():
            dw, dh = self.desktop()
            lst = [r for r in RESOLUTIONS if dw <= 0 or (r[0] <= dw and r[1] <= dh)]
            if dw > 0 and (dw, dh) not in lst:
                lst.append((dw, dh))
            cur = (int(s.get('width')), int(s.get('height')))
            if cur not in lst:
                lst.append(cur)
            lst.sort()
            return lst, cur

        def res_text():
            t = '%d × %d' % (int(s.get('width')), int(s.get('height')))
            if int(s.get('screen')) == SCREEN_BORDERLESS:
                t += ' (как у экрана)'
            return t

        def ch_res(d):
            if int(s.get('screen')) == SCREEN_BORDERLESS:
                return                                   # окно во весь экран всегда в родном разрешении
            lst, cur = res_list()
            i = (lst.index(cur) + d) % len(lst)
            s.set('width', lst[i][0])
            s.set('height', lst[i][1])
            self.apply_window()

        def ch_screen(d):
            mode = (int(s.get('screen')) + d) % 3
            s.set('screen', mode)
            dw, dh = self.desktop()
            if mode == SCREEN_EXCLUSIVE and dw > 0:
                # полноэкранный режим — сразу в родном разрешении экрана: в заниженном картинку
                # растягивает монитор, и она выходит мутной
                s.set('width', dw)
                s.set('height', dh)
            elif mode == SCREEN_WINDOW:
                size = settings_mod.fit_window(RESOLUTIONS[:5], (dw, dh))
                if size is not None:
                    s.set('width', size[0])
                    s.set('height', size[1])
            self.apply_window()

        def ch_tex(d):
            s.set('smooth_textures', not s.get('smooth_textures'))
            self.assets.set_smooth(s.get('smooth_textures'))

        def msaa_text():
            n = int(s.get('msaa'))
            t = 'Выкл' if n <= 0 else '%d×' % n
            return t + (' (после перезапуска)' if n != self._boot[0] else '')

        def ch_msaa(d):
            n = int(s.get('msaa'))
            i = MSAA_LEVELS.index(n) if n in MSAA_LEVELS else 2
            s.set('msaa', MSAA_LEVELS[(i + d) % len(MSAA_LEVELS)])

        def vsync_text():
            on = bool(s.get('vsync'))
            return ('Да' if on else 'Нет') + (' (после перезапуска)' if on != self._boot[1] else '')

        def back():
            s.save()
            self.ui.close()

        music_n = [0, -10.0]

        def music_count():
            # папку перечитываем не чаще раза в секунду: значение спрашивают каждый кадр
            if time.time() - music_n[1] > 1.0:
                music_n[0] = len(audio_mod.scan_tracks())
                music_n[1] = time.time()
            return ('песен: %d — открыть папку' % music_n[0]) if music_n[0] else 'пусто — открыть папку'

        def open_music(d=0):
            path = audio_mod.user_music_dir()
            try:
                if sys.platform == 'win32':
                    os.startfile(path)
                else:
                    import subprocess
                    subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', path])
            except Exception:
                pass

        def gfx_back():
            s.save()
            self.ui.close()

        def graphics():
            gi = [
                Item('Режим экрана', value=lambda: SCREEN_NAMES[int(s.get('screen')) % 3], change=ch_screen),
                Item('Разрешение', value=res_text, change=ch_res),
                Item('Текстуры', value=lambda: 'Сглаженные' if s.get('smooth_textures') else 'Чёткие',
                     change=ch_tex),
                Item('Сглаживание краёв', value=msaa_text, change=ch_msaa),
                Item('Вертикальная синхронизация', value=vsync_text, change=toggle('vsync')),
                Item('Дальность прорисовки',
                     value=lambda: ('Близко', 'Средне', 'Далеко')[int(s.get('draw_distance'))], change=ch_draw),
                Item('Счётчик кадров', value=yn('show_fps'), change=toggle('show_fps')),
                Item('Назад', gfx_back),
            ]
            self.ui.open(Menu(self.ui, 'Графика', gi, back=gfx_back, top=0.42, spacing=0.105, scale=0.068,
                              wide=True))

        items = [
            Item('Графика и экран', graphics, value=lambda: SCREEN_NAMES[int(s.get('screen')) % 3].lower()),
            Item('Громкость звуков', value=pct('sfx_volume'), change=ch_vol('sfx_volume')),
            Item('Громкость музыки', value=pct('music_volume'), change=ch_vol('music_volume')),
            Item('Песни для «Астрахань FM»', open_music, value=music_count),
            Item('Чувствительность мыши', value=lambda: '%.1f' % float(s.get('mouse_sens')), change=ch_sens),
            Item('Инверсия мыши по вертикали', value=yn('invert_y'), change=toggle('invert_y')),
            Item('Плотность движения', value=lambda: ('Мало', 'Норма', 'Много')[int(s.get('traffic'))],
                 change=ch_traffic),
            Item('Кровь', value=yn('blood'), change=toggle('blood')),
            Item('Назад', back),
        ]
        return Menu(self.ui, 'Настройки', items, back=back, top=0.44, spacing=0.105, scale=0.068, wide=True)

    # ------------------------------------------------------------------
    # экран
    # ------------------------------------------------------------------
    def desktop(self):
        """Размер экрана в настоящих пикселях; (0, 0), если он неизвестен."""
        d = settings_mod.desktop_size()
        if d[0] <= 0 and getattr(self, 'base', None) is not None:
            try:
                d = (int(self.base.pipe.getDisplayWidth()), int(self.base.pipe.getDisplayHeight()))
            except Exception:
                d = (0, 0)
        return d

    def _choose_screen(self):
        """Перед открытием окна: режим экрана для первого запуска и проверка сохранённого."""
        s = self.settings
        settings_mod.dpi_aware()
        desk = settings_mod.desktop_size()
        if s.fresh or int(s.get('cfg')) < settings_mod.CFG_VERSION:
            settings_mod.choose_screen(s, desk, RESOLUTIONS[:5])
            return
        mode = int(s.get('screen'))
        if mode not in (SCREEN_WINDOW, SCREEN_BORDERLESS, SCREEN_EXCLUSIVE):
            mode = SCREEN_BORDERLESS
            s.set('screen', mode)
        if mode == SCREEN_BORDERLESS:
            if desk[0] > 0:
                s.set('width', desk[0])             # экран могли сменить с прошлого запуска
                s.set('height', desk[1])
            else:
                s.set('screen', SCREEN_WINDOW)
        elif desk[0] > 0 and (int(s.get('width')) > desk[0] or int(s.get('height')) > desk[1]):
            s.set('width', desk[0])
            s.set('height', desk[1])

    def apply_window(self):
        """Применить режим экрана и разрешение из настроек к открытому окну.

        Делается в два шага: сначала рамка и полноэкранный режим, через пару кадров — место и размер
        (иначе Windows считает размер ещё по старой рамке)."""
        s = self.settings
        mode = int(s.get('screen'))
        try:
            win = self.base.win
            if mode == SCREEN_BORDERLESS:
                dw, dh = self.desktop()
                if dw > 0:
                    s.set('width', dw)
                    s.set('height', dh)
                else:
                    mode = SCREEN_WINDOW
                    s.set('screen', mode)
            w_, h_ = int(s.get('width')), int(s.get('height'))
            props = WindowProperties()
            if mode == SCREEN_EXCLUSIVE:
                props.setFullscreen(True)
                props.setSize(w_, h_)
                win.requestProperties(props)
                self._win_todo = [[30, 'check']]
            else:
                props.setFullscreen(False)
                props.setUndecorated(mode == SCREEN_BORDERLESS)
                win.requestProperties(props)
                self._win_todo = [[2, 'place']]
        except Exception:
            pass

    def _window_steps(self):
        """Отложенные шаги смены режима экрана (вызывается каждый кадр)."""
        if not self._win_todo:
            return
        step = self._win_todo[0]
        step[0] -= 1
        if step[0] > 0:
            return
        self._win_todo.pop(0)
        s = self.settings
        try:
            win = self.base.win
            what = step[1]
            if what == 'place':
                mode = int(s.get('screen'))
                props = WindowProperties()
                if mode == SCREEN_BORDERLESS:
                    props.setOrigin(0, 0)
                else:
                    props.setOrigin(-2, -2)                 # по центру экрана
                props.setSize(int(s.get('width')), int(s.get('height')))
                win.requestProperties(props)
            elif what == 'check':
                if not win.getProperties().getFullscreen():
                    # видеокарта не приняла режим — возвращаемся к окну во весь экран
                    s.set('screen', SCREEN_BORDERLESS)
                    s.save()
                    self.apply_window()
        except Exception:
            pass

    def open_shop(self):
        from .menu import Menu, Item
        from .defs import WEAPONS, W_BAT, W_PISTOL, W_UZI, W_SHOTGUN, W_AK, W_ROCKET, W_GRENADE, W_MOLOTOV
        if self.state != 'play':
            return
        w = self.world
        pl = w.player
        self.state = 'shop'
        self.inp.capture_mouse(False)
        self.audio.pause_all(True)
        w.hud.stash(True)

        def close():
            self.ui.close_all()
            w.hud.stash(False)
            self.state = 'play'
            self.audio.pause_all(False)
            self.inp.clear()
            self.inp.capture_mouse(True)

        def buy(wid):
            def f():
                wd = WEAPONS[wid]
                if pl.money < wd.price:
                    self.audio.play('menu_back', 0.7)
                    return
                if wd.kind == 'melee' and wid in pl.ammo:
                    return
                pl.add_money(-wd.price)
                pl.give_weapon(wid)
                self.audio.play('money', 0.7)
                m.title = 'Оружейный магазин — $%d' % pl.money
            return f

        def buy_armor():
            if pl.money < 800 or pl.ped.armor >= 100.0:
                self.audio.play('menu_back', 0.7)
                return
            pl.add_money(-800)
            pl.ped.armor = 100.0
            self.audio.play('money', 0.7)
            m.title = 'Оружейный магазин — $%d' % pl.money

        def label(wid):
            wd = WEAPONS[wid]
            return wd.name if wd.kind == 'melee' else '%s (%d)' % (wd.name, wd.pack)

        def have(wid):
            def f():
                wd = WEAPONS[wid]
                a = pl.ammo.get(wid)
                own = '' if a is None else ('  есть' if a < 0 else '  есть: %d' % a)
                return '$%d%s' % (wd.price, own)
            return f
        items = [Item(label(wid), buy(wid), value=have(wid))
                 for wid in (W_BAT, W_PISTOL, W_UZI, W_SHOTGUN, W_AK, W_GRENADE, W_MOLOTOV, W_ROCKET)]
        items.append(Item('Бронежилет', buy_armor, value=lambda: '$800'))
        items.append(Item('Уйти', close))
        m = Menu(self.ui, 'Оружейный магазин — $%d' % pl.money, items, back=close, top=0.44, spacing=0.11,
                 scale=0.075, wide=True)
        self.ui.open(m)

    def open_save(self):
        """Синий маркер у убежища: спросить, сохранять ли игру."""
        from .menu import Menu, Item
        if self.state != 'play':
            return
        w = self.world
        self.state = 'shop'
        self.inp.capture_mouse(False)
        self.audio.pause_all(True)
        w.hud.stash(True)

        def close():
            self.ui.close_all()
            w.hud.stash(False)
            self.state = 'play'
            self.audio.pause_all(False)
            self.inp.clear()
            self.inp.capture_mouse(True)

        def save():
            close()
            w.missions.sleep_and_save()
        text = 'Макс отоспится в общаге: пройдёт шесть часов,\nздоровье восстановится, игра будет сохранена.'
        if settings_mod.load_save() is not None:
            text += '\n\nПрежнее сохранение будет заменено.'
        m = Menu(self.ui, 'Убежище', [Item('Сохранить игру', save), Item('Уйти', close)], text=text, back=close,
                 top=0.44)
        m.text_scale = 0.058
        self.ui.open(m)

    def show_credits(self):
        self.credits_pending = True

    def _open_credits(self):
        from .menu import Menu, Item
        self.credits_pending = False
        if self.state != 'play':
            return
        self.state = 'pause'
        self.world.hud.stash(True)
        self.inp.capture_mouse(False)
        self.audio.pause_all(True)
        self.audio.music('theme', 0.9, random_start=False)

        def back():
            self.audio.music(None)
            self.resume()
        m = Menu(self.ui, 'Финал', [Item('Продолжить', back)], text=CREDITS_TEXT, back=back, top=0.44)
        m.text_scale = 0.058
        self.ui.open(m)

    # ------------------------------------------------------------------
    # главный цикл
    # ------------------------------------------------------------------
    def _update(self, task):
        dt = ClockObject.getGlobalClock().getDt()
        if dt > 0.05:
            dt = 0.05
        if dt <= 0.0:
            dt = 0.001
        try:
            self._window_steps()
            self.step(dt)
            self._errors_row = 0
        except Exception:
            # единичный сбой в одном кадре не должен закрывать игру; если же ошибка
            # повторяется из кадра в кадр — выходим с сообщением
            self._errors_row += 1
            self.report_error()
            if self._errors_row > 20:
                raise
            try:
                self.inp.end_frame()
            except Exception:
                pass
        return task.cont

    def report_error(self):
        """Записать текущее исключение в журнал (crash.log и стандартный вывод ошибок)."""
        import traceback
        text = traceback.format_exc()
        try:
            sys.stderr.write(text)
            sys.stderr.flush()
        except Exception:
            pass
        self._errors_total += 1
        if self._errors_total > 40:
            return
        try:
            path = os.path.join(settings_mod.user_dir(), 'crash.log')
            with open(path, 'a' if self._errors_total > 1 else 'w', encoding='utf-8') as f:
                f.write('[t=%.1f state=%s]\n%s\n' % (self.t, self.state, text))
        except Exception:
            pass

    def step(self, dt):
        self.dt = dt
        self.t += dt
        inp = self.inp
        w = self.world
        inp.poll_mouse()
        st = self.state
        if st == 'play':
            # потеря фокуса окна — автоматическая пауза
            if not self.headless:
                try:
                    fg = self.base.win.getProperties().getForeground()
                except Exception:
                    fg = True
                if not fg:
                    self.pause()
                    inp.end_frame()
                    return
            if (inp.hit('escape') or inp.hit('p')) and w.respawn_kind is None and w.missions.intro is None:
                self.pause()
            else:
                wdt = dt * (0.45 if (w.respawn_kind == 'wasted' and w.respawn_t < 3.6) else 1.0)
                w.update(wdt, inp)
                w.missions.update_respawn(dt)
                w.cam.update(dt, inp.mouse_dx, inp.mouse_dy)
                w.sky.update(wdt)
                w.sky.follow(w.cam, dt)
                w.hud.update(dt)
                w.update_audio(dt)
                if self.credits_pending:
                    self._open_credits()
        elif st == 'menu':
            # фон главного меню: живой город, камера медленно кружит
            self.attract_t += dt
            a = self.attract_t * 0.05
            ax, ay = self.attract_pos
            w.cam.override = (ax + math.cos(a) * 60.0, ay + math.sin(a) * 60.0, 30.0 + 6.0 * math.sin(a * 1.7),
                              ax, ay, 9.0)
            w.update(dt, inp)
            w.cam.update(dt, 0.0, 0.0)
            w.sky.time_scale = 0.0
            w.sky.update(dt)
            w.sky.time_scale = 1.0
            w.sky.follow(w.cam, dt)
            w.hud.update(dt)
            self.audio.set_listener(w.cam.x, w.cam.y)
        else:
            # пауза / магазин: мир стоит
            w.hud.layout()
        self.ui.update(dt)
        inp.end_frame()

    def run(self):
        self.base.run()
