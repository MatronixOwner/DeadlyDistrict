# -*- coding: utf-8 -*-
"""Меню тестера (F9): задания, телепорт, розыск, бессмертие, транспорт, время и погода.

В обычную сборку игры этот модуль не входит: setup.py его исключает.  Он есть только в сборке
для тестера (точка входа tester_main.py) и при запуске из исходников: python main.py --tester.

Правило для всех действий меню: игра после них должна остаться в состоянии, в которое можно
попасть и честной игрой.  Иначе тестер будет находить ошибки, которых у игроков нет.
"""
import math

from panda3d.core import ClockObject, LColor, PandaNode

from . import __version__
from . import ui
from .city import WATER_Z
from .collision import F_PED, F_CAR
from .defs import WEAPONS
from .sky import WEATHERS, WEATHER_NAMES
from .vehicle import SPECS

# куда переносит «Телепорт»: подпись и ключ в city.landmarks (места без ключа добавляет places())
PLACES = (
    ('Дом Макса', 'safehouse'),
    ('Конечная автобуса: начало игры', 'terminal'),
    ('Дом Брюса', 'bruce'),
    ('Казино «Фортуна»', 'boss'),
    ('Гараж Вано', 'vano'),
    ('Бар «У Розы»', 'rosa'),
    ('Сарай Захара', 'zakhar'),
    ('Чайная «Заречье»', 'grom'),
    ('Башня Профа', 'prof'),
    ('Больница', 'hospital'),
    ('Полицейский участок', 'police'),
    ('Городской банк', 'bank'),
    ('Оружейный магазин: Старый город', 'guns'),
    ('Оружейный магазин: Порт', 'guns2'),
    ('Покрасочная: Старый город', 'spray'),
    ('Покрасочная: Набережная', 'spray2'),
    ('Таксопарк', 'taxi'),
    ('Заправка', 'gas'),
    ('Склад в Порту', 'port'),
    ('Аэродром: ворота', 'airfield'),
)

# Номер сборки для тестера: растёт с каждой новой сборкой, виден в строке сведений и в главном меню.
# По нему тестер и автор понимают, о какой именно сборке речь в отчёте об ошибке.
BUILD = 1
LABEL = u'%s-t%d' % (__version__, BUILD)

LINE_SCALE = 0.030            # размер букв строки сведений
STARS = ('нет', '1 звезда', '2 звезды', '3 звезды', '4 звезды', '5 звёзд', '6 звёзд')
HINT = u'↑↓  выбор      ←→  изменить      Enter  выполнить      Esc  назад      F9  закрыть'


def _on(flag):
    return 'вкл' if flag else 'выкл'


class Tester(object):

    def __init__(self, game):
        self.game = game
        self.god = False              # бессмертие: герой и машина, в которой он сидит
        self.hold = False             # розыск держится на уровне self.level и сам не меняется
        self.level = 0
        self.info = True              # строка сведений вверху экрана
        self.note = ''                # что сделано последним действием
        self.menus = []               # открытые меню тестера (пусто — меню закрыто)
        self._toggle = False
        self._immune = None           # машина, которую бессмертие сделало неуязвимой
        self._last = None             # последняя машина, поставленная из меню
        self._info_t = 0.0
        kit = game.world.hud.kit
        self.root = game.base.aspect2d.attachNewNode(PandaNode('tester'), sort=30)
        self.line = kit.label(self.root, '', 0.0, 0.950, LINE_SCALE, ui.ACCENT, kit.bold, 'c', shadow=False)
        tn = self.line.textNode                # тёмная плашка под строкой: читается на любом фоне
        tn.setCardColor(LColor(*ui.rgba(ui.INK, 0.78)))
        tn.setCardAsMargin(0.5, 0.5, 0.28, 0.22)
        tn.setCardDecal(True)
        game.inp.listeners.append(self._on_key)

    def destroy(self):
        """Убрать меню тестера из игры (нужно автоматическим проверкам)."""
        self.set_god(False)
        self.set_hold(False)
        if self.opened:
            self.close()
        self._upkeep()
        g = self.game
        if self._on_key in g.inp.listeners:
            g.inp.listeners.remove(self._on_key)
        self.root.removeNode()
        if g.tester is self:
            g.tester = None

    # ------------------------------------------------------------------
    # клавиша, кадр
    # ------------------------------------------------------------------
    def _on_key(self, key):
        if key == 'f9':
            self._toggle = True

    @property
    def opened(self):
        return bool(self.menus) and self.game.ui.current() in self.menus

    def frame(self, dt):
        """Раз в кадр, в любом состоянии игры."""
        g = self.game
        if self._toggle:
            self._toggle = False
            if self.opened:
                self.close()
            elif g.state == 'play':
                self.open()
        if g.state == 'play':
            self._upkeep()
        self._info_t -= dt
        if self._info_t <= 0.0:
            self._info_t = 0.2
            self.line.setText(self.status() if self.info else '')
            # на узком экране (4:3, 5:4) длинная строка ужимается, а не уходит за края
            wide = self.line.textNode.getWidth() * LINE_SCALE
            room = 2.0 * g.base.getAspectRatio() - 0.10
            self.line.setScale(LINE_SCALE * min(1.0, room / wide) if wide > 0.0 else LINE_SCALE)

    def _upkeep(self):
        """Держать включённое: бессмертие и розыск."""
        w = self.game.world
        pl = w.player
        pl.god = self.god
        v = pl.vehicle if self.god else None
        if v is not self._immune:
            if self._immune is not None and not self._immune.removed:
                self._immune.immune = False
            self._immune = v
            if v is not None:
                v.immune = True
                if not v.dead and v.health < v.max_health * 0.15:
                    # машина уже горела: под бессмертным она гаснет, а не взрывается через пару секунд
                    v.health = v.max_health * 0.15
                    v.burn_t = 0.0
        pol = w.police
        pol.enabled = not self.hold               # при удержании новые нарушения розыск не поднимают
        if self.hold and pol.level != self.level:
            pol.set_level(self.level)

    def world_reset(self):
        """Новая игра, загрузка или выход в главное меню: прежнего мира больше нет.

        Бессмертие остаётся включённым, пока его не выключат.  Удержание розыска снимается: розыск —
        часть мира, а новая игра начинается с пролога, где полиции взяться неоткуда."""
        self.hold = False
        self.level = 0
        self._immune = None
        self._last = None
        self.menus = []
        self.game.world.police.enabled = True

    def status(self):
        """Строка сведений: где герой, на чём, какое задание — чтобы это попадало на снимки экрана."""
        g = self.game
        w = g.world
        if g.state not in ('play', 'pause', 'shop'):
            return u'СБОРКА ДЛЯ ТЕСТЕРА %s      F9 в игре — меню тестера' % LABEL
        pl = w.player
        x, y = pl.pos()
        v = pl.vehicle
        yaw = v.yaw if v is not None else pl.ped.yaw
        room = w.interiors.current
        if room is not None:
            place = room.title
        else:
            place = w.city.zone_name(x, y) or ''
            street = w.city.street_name(x, y)
            if street:
                place = ('%s, %s' % (place, street)) if place else street
        parts = [u'ТЕСТЕР %s' % LABEL, u'x %.0f  y %.0f  курс %d°' % (x, y, int(math.degrees(yaw)) % 360)]
        if place:
            parts.append(place)
        if v is not None:
            parts.append(u'%s (%s)' % (v.spec.title, v.kind))
        m = w.missions.active
        if m is not None:
            parts.append(u'задание %s' % m.spec['id'])
        if self.god:
            parts.append(u'бессмертие')
        if self.hold:
            parts.append(u'розыск удержан')
        parts.append(u'%d к/с' % int(ClockObject.getGlobalClock().getAverageFrameRate() + 0.5))
        parts.append(u'F9 — меню')
        return u'     '.join(parts)

    # ------------------------------------------------------------------
    # открыть и закрыть
    # ------------------------------------------------------------------
    def open(self):
        g = self.game
        w = g.world
        if g.state != 'play' or w.respawn_kind is not None or w.interiors.trans is not None:
            return False
        if w.missions.intro is not None:
            w.hud.subtitle(u'Тестер: сначала пропустите пролог клавишей Esc.', 3.0, clear=True)
            return False
        g.state = 'pause'
        g.inp.capture_mouse(False)
        g.audio.pause_all(True)
        w.hud.stash(True)
        self.note = ''
        self.menus = []
        self._push(self.main_menu())
        return True

    def close(self):
        self.menus = []
        self.game.resume()

    def _push(self, menu):
        menu.dim = 0.30                       # игру за меню видно: так заметны время суток и погода
        menu.subtitle = HINT
        self.menus.append(menu)
        self.game.ui.open(menu)

    def _menu(self, title, items, back=None):
        from .menu import Menu
        for it in items:
            if it.action is not None:
                it.action = self._safe(it.action)
            if it.change is not None:
                it.change = self._safe(it.change)
        m = Menu(self.game.ui, title, items, back=back, wide=True)
        m.skin = ui.SKIN_PLATE          # серо-оливковая плашка: меню тестера с обычным не спутать
        return m

    def _safe(self, fn):
        """Действие меню не должно закрывать игру: сбой записывается в crash.log и показывается в меню."""
        def run(*args):
            try:
                return fn(*args)
            except Exception as e:
                g = self.game
                g.report_error()
                if self.opened:
                    self._say(u'ошибка: %s (подробности в crash.log)' % e)
                else:
                    if g.state == 'pause':
                        self.close()                    # действие успело убрать меню: игра не остаётся на паузе
                    g.world.hud.help(u'Тестер: ошибка — %s. Подробности в crash.log.' % e, 6.0)
                return False
        return run

    def _say(self, text, close=False):
        """Сообщить, что сделано: в открытом меню — строкой внизу, после закрытия — подсказкой на экране."""
        self.note = text
        if close:
            self.close()
            self.game.world.hud.help(u'Тестер: ' + text, 4.5)
        else:
            line = text[:1].upper() + text[1:] + u'.      Esc  назад      F9  закрыть'
            for m in self.menus:
                m.subtitle = line
            if self.opened:
                self.game.ui.refresh()
        return True

    # ------------------------------------------------------------------
    # меню
    # ------------------------------------------------------------------
    def main_menu(self):
        from .menu import Item
        g = self.game
        w = g.world
        pl = w.player
        pol = w.police
        sky = w.sky
        items = [
            Item('Задания', lambda: self._push(self.missions_menu())),
            Item('Телепорт', lambda: self._push(self.places_menu())),
            Item('Транспорт', lambda: self._push(self.vehicles_menu())),
            Item('Розыск', value=lambda: STARS[self.level if self.hold else pol.level], change=self.set_wanted_by),
            Item('Удерживать розыск', value=lambda: _on(self.hold), change=lambda d: self.set_hold(not self.hold)),
            Item('Бессмертие', value=lambda: _on(self.god), change=lambda d: self.set_god(not self.god)),
            Item('Здоровье и броня', self.heal),
            Item('Всё оружие и патроны', self.arm),
            Item('Деньги', value=lambda: ui.money(pl.money), change=lambda d: self.cash(10000 * d)),
            Item('Время', value=sky.clock_text, change=self.shift_time),
            Item('Погода', value=lambda: WEATHER_NAMES.get(sky.weather, sky.weather), change=self.shift_weather),
            Item('Строка сведений', value=lambda: _on(self.info), change=lambda d: self.set_info(not self.info)),
        ]
        return self._menu('Тестер', items, back=self.close)

    def missions_menu(self):
        from .menu import Item
        from . import missions as M
        ms = self.game.world.missions
        busy = ms.active is not None
        items = [
            Item('К цели задания', self.to_target, enabled=self.target() is not None),
            Item('Пройти текущее задание', self.pass_mission, enabled=busy),
            Item('Отменить текущее задание', self.cancel_mission, enabled=busy),
        ]
        for spec in list(M.MISSIONS) + [M.TAXI]:
            items.append(Item(spec['title'], (lambda s=spec: self.start_mission(s)),
                              value=(lambda s=spec: self.mission_state(s))))
        return self._menu('Задания', items)

    def mission_state(self, spec):
        from . import missions as M
        ms = self.game.world.missions
        mid = spec['id']
        who = 'сюжет' if spec.get('story') else (M.CONTACTS[spec['contact']]['title'] if spec.get('contact')
                                                 else 'в такси')
        if ms.active is not None and ms.active.spec is spec:
            st = 'идёт'
        elif mid in ms.done:
            st = 'пройдено'
        else:
            st = ''
        return u'%s · %s%s' % (who, mid, (u' · ' + st) if st else '')

    def places_menu(self):
        from .menu import Item
        items = [
            Item('К цели задания', self.to_target, enabled=self.target() is not None),
            Item('Комнаты', lambda: self._push(self.rooms_menu())),
        ]
        for title, foot, car in self.places():
            items.append(Item(title, (lambda t=title, f=foot, c=car: self.go(t, f, c))))
        return self._menu('Телепорт', items)

    def rooms_menu(self):
        from .menu import Item
        w = self.game.world
        items = []
        for room in w.interiors.order:
            zone = w.city.zone_name(room.out[0], room.out[1]) or ''
            items.append(Item(room.title, (lambda r=room: self.go_room(r)), value=(lambda z=zone: z)))
        return self._menu('Комнаты', items)

    def vehicles_menu(self):
        from .menu import Item
        pl = self.game.world.player
        items = [Item('Починить машину', self.repair, enabled=pl.vehicle is not None)]
        for kind, spec in SPECS.items():
            items.append(Item(spec.title, (lambda k=kind: self.spawn(k)), value=(lambda k=kind: k)))
        return self._menu('Транспорт', items)

    # ------------------------------------------------------------------
    # розыск, бессмертие, герой, мир
    # ------------------------------------------------------------------
    def set_wanted(self, level):
        level = max(0, min(6, int(level)))
        self.level = level
        pol = self.game.world.police
        if level == 0 and not self.hold:
            pol.clear()
        else:
            pol.set_level(level)
        return self._say(u'розыск: %s' % STARS[level])

    def set_wanted_by(self, d):
        cur = self.level if self.hold else self.game.world.police.level
        return self.set_wanted(cur + d)

    def set_hold(self, on):
        pol = self.game.world.police
        self.hold = bool(on)
        self.level = pol.level
        pol.enabled = not self.hold
        return self._say(u'розыск держится на уровне «%s» и сам не меняется' % STARS[self.level] if self.hold
                         else u'розыск снова растёт и спадает сам')

    def set_god(self, on):
        self.god = bool(on)
        w = self.game.world
        w.player.god = self.god
        if self.god:
            p = w.player.ped
            p.health = p.max_health
            p.fire_t = 0.0
        self._upkeep()
        return self._say(u'бессмертие включено: героя не убить и не арестовать, его машину не сломать' if self.god
                         else u'бессмертие выключено')

    def set_info(self, on):
        self.info = bool(on)
        self._info_t = 0.0
        return self._say(u'строка сведений вверху экрана: %s' % _on(self.info))

    def heal(self):
        p = self.game.world.player.ped
        p.health = p.max_health
        p.armor = 100.0
        p.fire_t = 0.0
        return self._say(u'здоровье и броня полные')

    def arm(self):
        pl = self.game.world.player
        for wp in WEAPONS:
            if wp.kind == 'melee':
                pl.give_weapon(wp.id, select=False)
            else:
                pl.ammo[wp.id] = 9999
        self.game.world.hud.weapon_changed(False)
        return self._say(u'выдано всё оружие, патронов по 9999')

    def cash(self, amount):
        pl = self.game.world.player
        pl.add_money(amount)
        return self._say(u'деньги: %s' % ui.money(pl.money))

    def shift_time(self, d):
        sky = self.game.world.sky
        sky.set_time((int(sky.hour) + d) % 24)
        return self._say(u'время: %s' % sky.clock_text())

    def shift_weather(self, d):
        sky = self.game.world.sky
        names = [n for n, p in WEATHERS]
        i = names.index(sky.weather) if sky.weather in names else 0
        sky.set_weather(names[(i + d) % len(names)])
        sky._apply(0.0)
        return self._say(u'погода: %s' % WEATHER_NAMES.get(sky.weather, sky.weather))

    # ------------------------------------------------------------------
    # перенос героя
    # ------------------------------------------------------------------
    def _busy(self):
        """Почему сейчас нельзя переносить героя (None — можно)."""
        w = self.game.world
        pl = w.player
        if pl.state not in ('foot', 'car', 'entering'):
            return u'герой сейчас не на ногах и не за рулём'
        if pl.freeze or not pl.controls or w.cam.override is not None:
            return u'идёт сценка: долистайте её клавишей Enter или отмените задание'
        return None

    def _dry(self, x, y):
        c = self.game.world.city
        return c.ground_z(x, y) > WATER_Z - 0.2 and not c.in_water(x, y)

    def _put_ped(self, x, y, yaw=None):
        """Поставить героя пешком в точку (или рядом, если точка занята стеной)."""
        w = self.game.world
        pl = w.player
        if pl.state == 'entering':
            pl.state = 'foot'
            pl.enter_v = None
        if w.static.overlap_circle(x, y, 0.45, F_PED):
            x, y = w.missions.free_spot(x, y)
        its = w.interiors
        pl.teleport(x, y, yaw)
        room = its.room_at(x, y)
        if room is not its.current:
            its._switch(room)                  # свет и видимость города — сразу, а не кадром позже
        if yaw is None:
            w.cam.face(x, y, pl.ped.yaw)

    def _put_vehicle(self, v, x, y, yaw, speed=0.0):
        """Переставить машину (вместе с героем и пассажирами)."""
        w = self.game.world
        w.missions.clear_area(x, y, v.spec.L * 0.5 + 3.0)
        v.x, v.y, v.yaw = x, y, yaw
        v.z = w.city.ground_z(x, y)
        v.vx, v.vy = math.cos(yaw) * speed, math.sin(yaw) * speed
        v.speed = speed
        v.slip = 0.0
        v.omega = 0.0
        v.sync()
        w.cam.face(x, y, yaw)

    def _lane(self, x, y, maxd):
        """Ближайшая точка проезжей части: (x, y, yaw) или None."""
        lane, s, d = self.game.world.roadnet.nearest_lane(x, y, maxd)
        if lane is None:
            return None
        return lane.pos(s)

    def _car(self):
        pl = self.game.world.player
        return pl.vehicle if pl.state == 'car' else None

    def places(self):
        """Места для телепорта: (подпись, (x, y, yaw) пешком, (x, y, yaw или None, прижать к полосе) на машине)."""
        c = self.game.world.city
        lms = c.landmarks
        sp = c.special
        out = []
        for title, key in PLACES:
            lm = lms.get(key)
            if lm is None:
                continue
            dx, dy = lm['door']
            rx, ry = lm['road']
            out.append((title, (dx, dy, lm['yaw'] + math.pi), (rx, ry, None, True)))
            if key == 'safehouse' and 'garage' in sp:
                gx, gy = sp['garage']['front']
                gyaw = sp['garage']['yaw']
                out.append(('Гараж у дома Макса', (gx, gy, gyaw), (gx, gy, gyaw, False)))
        air = lms.get('airfield')
        if air is not None and 'apron' in air:
            ax, ay = air['apron']
            out.append(('Аэродром: перрон', (ax, ay, 0.0), (ax, ay, 0.0, False)))
        piers = sp.get('piers') or []
        if piers:
            p = piers[0]
            px, py = p['x0'] + 6.0, (p['y0'] + p['y1']) * 0.5
            out.append(('Порт: первый причал', (px, py, 0.0), (px, py, 0.0, False)))
        ship = sp.get('ship')
        if ship is not None:
            sx, sy = ship['stairs_foot']
            rx, ry = ship['ramp_foot']
            out.append(('Сухогруз: трап', (sx, sy, math.pi / 2), (rx, ry, 0.0, False)))
        pier = sp.get('pier')
        if pier is not None:
            px, py = (pier['x0'] + pier['x1']) * 0.5, pier['y1'] - 3.0
            out.append(('Пляж: причал', (px, py, -math.pi / 2), (px, py + 30.0, None, True)))
        pond = sp.get('pond')
        if pond is not None:
            px, py = pond['x'] + pond['rx'] + 5.0, pond['y']
            out.append(('Парк: пруд', (px, py, math.pi), (px, py, None, True)))
        for i, seg in enumerate(c.bridges):
            m = (seg['a'] + seg['b']) * 0.5
            x, y = (m, seg['c']) if seg['kind'] == 'h' else (seg['c'], m)
            name = c.zone_name(x, y) or c.street_name(x, y) or ''
            if 'мост' not in name.lower():
                name = ('Мост: %s' % name) if name else ('Мост %d' % (i + 1))
            off = seg['width'] * 0.5 - 1.5                     # пешком — у края настила, не посреди дороги
            fx, fy = (x, y - off) if seg['kind'] == 'h' else (x + off, y)
            out.append((name, (fx, fy, None), (x, y, None, True)))
        return out

    def go(self, title, foot, car):
        why = self._busy()
        if why:
            return self._say(why)
        v = self._car()
        if v is not None:
            x, y, yaw, snap = car
            if snap:
                p = self._lane(x, y, 60.0)
                if p is not None:
                    x, y, yaw = p
            self._put_vehicle(v, x, y, v.yaw if yaw is None else yaw)
        else:
            self._put_ped(*foot)
        return self._say(u'перенос: %s' % title, close=True)

    def go_room(self, room):
        why = self._busy() or self.game.world.interiors.locked_reason()
        if why:
            return self._say(why if why[0].islower() else (u'нельзя: ' + why))
        self.game.world.interiors.enter(room.name, instant=True)
        return self._say(u'перенос в комнату: %s' % room.title, close=True)

    def rescue(self):
        """Бессмертный упал в воду: вернуть его (вместе с машиной) на ближайшую дорогу."""
        w = self.game.world
        pl = w.player
        v = self._car()
        x, y = pl.pos()
        if v is not None:
            p = self._lane(x, y, 500.0)
            if p is not None and self._dry(p[0], p[1]):
                self._put_vehicle(v, p[0], p[1], p[2])
                w.hud.help(u'Тестер: бессмертие — машину вернули из воды на дорогу.', 4.0)
                return True
        n = w.roadnet.nearest_ped_node(x, y, 500.0)
        if n is None or not self._dry(n.x, n.y):
            n = w.city.nearest_node(x, y)
        self._put_ped(n.x, n.y)
        pl.water_t = 0.0
        pl.ped.air = False
        pl.ped.vx = pl.ped.vy = pl.ped.vz = 0.0
        w.hud.help(u'Тестер: бессмертие — героя вернули из воды на берег.', 4.0)
        return True

    # ------------------------------------------------------------------
    # задания
    # ------------------------------------------------------------------
    def target(self):
        """Куда сейчас ведёт задание: ((x, y), объект или None, нужно ли идти пешком) либо None."""
        w = self.game.world
        m = w.missions.active
        if m is None:
            return None
        for mk in reversed(m.markers):
            if not mk.removed:
                return (mk.x, mk.y), None, mk.need_foot
        px, py = w.player.pos()
        best = None
        for b in m.blips:
            if b.removed:
                continue
            o = b.obj
            if o is not None:
                if getattr(o, 'removed', False) or getattr(o, 'dead', False):
                    continue
                o = getattr(o, 'vehicle', None) or o            # человек в машине — цель там, где машина
                x, y = o.x, o.y
            else:
                x, y = b.x, b.y
            d = (x - px) ** 2 + (y - py) ** 2
            if best is None or d < best[0]:
                best = (d, (x, y), o)
        if best is None:
            return None
        return best[1], best[2], None

    def to_target(self):
        why = self._busy()
        if why:
            return self._say(why)
        t = self.target()
        if t is None:
            return self._say(u'у задания сейчас нет метки')
        (x, y), obj, need_foot = t
        v = self._car()
        if obj is None:
            if v is not None and need_foot is not True:
                p = self._lane(x, y, 9.0)
                self._put_vehicle(v, x, y, p[2] if p is not None else v.yaw)        # точно в метку
            elif v is not None:
                p = self._lane(x, y, 60.0) or (x, y, v.yaw)
                self._put_vehicle(v, p[0], p[1], p[2])                              # в метку — только пешком
            else:
                self._put_ped(x, y)
        elif hasattr(obj, 'spec'):                                                  # цель — машина
            if v is obj:
                return self._say(u'вы уже в нужной машине')
            if v is not None:
                # пристроиться сзади и ехать с той же скоростью: погоня не обрывается
                yaw = obj.yaw
                bx, by = obj.x - math.cos(yaw) * 14.0, obj.y - math.sin(yaw) * 14.0
                p = self._lane(bx, by, 25.0)
                if p is not None and math.hypot(p[0] - obj.x, p[1] - obj.y) > 8.0:
                    bx, by = p[0], p[1]
                sp = math.hypot(obj.vx, obj.vy)
                self._put_vehicle(v, bx, by, yaw, sp)
            else:
                dx, dy = obj.door_pos(-1)
                k = 0.7 / (math.hypot(dx - obj.x, dy - obj.y) or 1.0)
                self._put_ped(dx + (dx - obj.x) * k, dy + (dy - obj.y) * k, obj.yaw)
        else:                                                                       # цель — человек
            if v is not None:
                p = self._lane(x, y, 40.0)
                if p is None or math.hypot(p[0] - x, p[1] - y) < 4.0:
                    p = (x - math.cos(v.yaw) * 9.0, y - math.sin(v.yaw) * 9.0, v.yaw)
                self._put_vehicle(v, p[0], p[1], p[2])
            else:
                px, py = self.game.world.player.pos()
                a0 = math.atan2(py - y, px - x)
                spot = None
                # к врагу — не вплотную: тестеру нужна секунда, чтобы оглядеться
                for r in ((18.0, 12.0, 6.0) if getattr(obj, 'kind', '') == 'enemy' else (6.0,)):
                    for k in range(8):
                        a = a0 + k * math.pi / 4.0
                        sx, sy = x + math.cos(a) * r, y + math.sin(a) * r
                        if self._dry(sx, sy) and not self.game.world.static.overlap_circle(sx, sy, 0.45, F_PED):
                            spot = (sx, sy, a + math.pi)
                            break
                    if spot is not None:
                        break
                if spot is None:
                    spot = (x, y, None)
                self._put_ped(*spot)
        return self._say(u'перенос к цели задания', close=True)

    def _calm(self):
        """После принудительного конца задания: убрать следы оборванной сценки."""
        w = self.game.world
        pl = w.player
        pl.freeze = False
        pl.controls = True
        pl.script_move = None
        pl.ped.idle_clip = None
        pl.ped.stop_act()
        w.cam.override = None
        w.hud.fade(0.0, 3.0)
        w.hud.show(True)
        for p in w.interiors.people:                    # хозяева комнат возвращаются на свои места
            if p.removed or p.dead:
                continue
            p.stop_act()
            p.x, p.y, p.yaw = p.home
            p.sync()

    def _end(self, passed, reason=''):
        w = self.game.world
        ms = w.missions
        m = ms.active
        if m is None:
            return None
        for p in list(m.peds):                          # гости сценки в комнате исчезают вместе со сценкой
            if not p.removed and p.room is None and w.interiors.room_at(p.x, p.y) is not None:
                w.remove_ped(p)
        if passed and m.spec['id'] == 'p4':
            ms.finale = True                            # последнее задание: после него идут титры
        ms._finish(passed, reason, quiet=True)
        self._calm()
        return m

    def pass_mission(self):
        m = self.game.world.missions.active
        if m is None:
            return self._say(u'задание не идёт')
        if m.side:
            # подработку нельзя «пройти»: смену можно только закончить, как клавишей T
            self._end(False, u'Смена окончена.')
            return self._say(u'подработка «%s» закончена' % m.spec['title'], close=True)
        self._end(True)
        return self._say(u'задание «%s» засчитано' % m.spec['title'], close=True)

    def cancel_mission(self):
        ms = self.game.world.missions
        m = self._end(False, u'Отменено тестером.')
        if m is None:
            return self._say(u'задание не идёт')
        if m.spec.get('story'):
            ms.call_t = 600.0                           # Брюс перезвонит не через 14 секунд, а через 10 минут
            return self._say(u'задание «%s» отменено; Брюс перезвонит через 10 минут' % m.spec['title'], close=True)
        return self._say(u'задание «%s» отменено' % m.spec['title'], close=True)

    @staticmethod
    def _before(mid):
        """Всё, что должно быть пройдено до задания mid."""
        from . import missions as M
        req = dict((s['id'], s['req']) for s in M.MISSIONS)
        out = set()
        todo = list(req.get(mid, ()))
        while todo:
            k = todo.pop()
            if k not in out:
                out.add(k)
                todo.extend(req.get(k, ()))
        return out

    def start_mission(self, spec):
        """Начать задание так, будто игрок до него дошёл: всё, что нужно раньше, — пройдено, оно само и всё
        зависящее от него — нет."""
        from . import missions as M
        g = self.game
        w = g.world
        ms = w.missions
        pl = w.player
        if pl.state not in ('foot', 'car', 'entering'):
            return self._say(u'герой сейчас не на ногах и не за рулём')
        self._end(False, u'Отменено тестером.')
        w.hud.big_t = min(w.hud.big_t, 0.01)            # плашка об отмене не висит поверх нового задания
        ms.fail_cd = 0.0
        mid = spec['id']
        if mid != 'taxi':
            need = self._before(mid)
            later = set(s['id'] for s in M.MISSIONS if mid in self._before(s['id']))
            ms.done = (set(ms.done) - later - set([mid])) | need
            for k in list(later) + [mid]:
                ms.ckpt.pop(k, None)
            ms.finale = ms.finale_shown = False
            if 'g3' not in ms.done:
                w.interiors.ensure_resident('zakhar')   # до «Облавы» Захар ещё у себя в сарае
            ms.sync_story()
        if not self.hold:
            w.police.clear()                            # задания берут без розыска
        if pl.state == 'entering':
            pl.state = 'foot'
            pl.enter_v = None
        if spec.get('contact') and pl.vehicle is not None:
            pl.leave_vehicle(force=True)                # к заказчику входят пешком: машина остаётся, где стояла
        if mid == 'taxi':
            v = self._car()
            if v is None or v.kind != 'taxi':
                if not self._spawn('taxi'):
                    return self._say(u'не нашлось места для такси')
        if not ms.start(spec):
            return self._say(u'задание не началось')
        return self._say(u'задание «%s» начато' % spec['title'], close=True)

    # ------------------------------------------------------------------
    # транспорт
    # ------------------------------------------------------------------
    def repair(self):
        v = self.game.world.player.vehicle
        if v is None:
            return self._say(u'герой не в машине')
        if v.dead:
            return self._say(u'эта машина уничтожена, её не починить')
        v.health = v.max_health
        v.burn_t = 0.0
        v.burning = 0.0
        return self._say(u'машина починена: %s' % v.spec.title)

    def _spawn(self, kind):
        """Поставить машину на дорогу рядом с героем и посадить его за руль.  Возвращает машину или None."""
        w = self.game.world
        pl = w.player
        its = w.interiors
        if its.current is not None:
            its.leave(instant=True)
        old = self._car()
        x, y = pl.pos()
        yaw = old.yaw if old is not None else pl.ped.yaw
        if old is not None:
            pl.leave_vehicle(force=True)
            if old is self._last and old.mission is None and not old.garage and not old.removed:
                w.remove_vehicle(old)               # прежняя машина из этого же меню: заменяем её новой
                x, y = old.x, old.y
            else:
                x, y = old.x + math.cos(yaw) * 7.0, old.y + math.sin(yaw) * 7.0
        else:
            p = self._lane(x, y, 25.0)
            if p is not None:
                x, y, yaw = p
            else:
                x, y = x + math.cos(yaw) * 4.0, y + math.sin(yaw) * 4.0
        spec = SPECS[kind]
        if old is not None and old.removed:
            old = None
        # машины героя (та, из которой он вышел, и поставленная из меню раньше) остаются на месте
        mine = [o for o in (old, pl.last_vehicle, self._last) if o is not None and not o.removed]
        ok = False
        for _ in range(10):
            # место должно быть сухим, не в стене и не занято машиной, которую убирать нельзя
            ok = self._dry(x, y) and not w.static.overlap_circle(x, y, spec.W * 0.5, F_CAR) and not any(
                (not o.removed) and math.hypot(o.x - x, o.y - y) < (spec.L + o.spec.L) * 0.5 + 0.8 and
                (o in mine or o.keep or o.garage or o.mission is not None) for o in w.vehicles)
            if ok:
                break
            x, y = x + math.cos(yaw) * 6.0, y + math.sin(yaw) * 6.0
        if not ok:
            if old is not None:
                pl.enter_vehicle(old, silent=True)          # места нет: герой остаётся в прежней машине
            return None
        held = [o for o in mine if not o.keep]
        for o in held:
            o.keep = True                               # случайные машины с этого места убираем, машины героя — нет
        w.missions.clear_area(x, y, spec.L * 0.5 + 2.0)
        for o in held:
            o.keep = False
        v = w.spawn_vehicle(kind, x, y, yaw)
        v.stolen = True                             # своя машина: угоном её посадка не считается
        pl.enter_vehicle(v, silent=True)
        w.cam.face(x, y, yaw)
        self._last = v
        return v

    def spawn(self, kind):
        why = self._busy()
        if why:
            return self._say(why)
        if self.game.world.interiors.current is not None:
            return self._say(u'в помещении машину не поставить: выйдите на улицу')
        v = self._spawn(kind)
        if v is None:
            return self._say(u'рядом нет свободного места для машины')
        return self._say(u'машина: %s (%s)' % (v.spec.title, kind), close=True)
