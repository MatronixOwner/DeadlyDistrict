# -*- coding: utf-8 -*-
"""Задания: движок сценариев, контакты, подбираемые предметы, сохранение."""
import math
import random

from .pickups import Marker, Arrow, Pickup, spot_pickup, PINK, YELLOW, BLUE, GREEN, RED
from .defs import (WEAPONS, W_FIST, W_BAT, W_PISTOL, W_UZI, W_SHOTGUN, W_AK, W_ROCKET, W_GRENADE, W_MOLOTOV,
                   make_look, gang_look, random_look, cop_look, SKINS)
from .vehicle import Vehicle
from .collision import F_PED, F_CAR
from .mathutil import clamp, angle_diff
from . import settings as settings_mod

from .ui import ACCENT as GOLD, DANGER as REDC, COOL as BLUEC      # цвета больших сообщений
from .ui import money as ui_money

CONTACTS = {
    'vano': dict(title='Вано', blip='blip_vano', place='гараж Вано'),
    'rosa': dict(title='Роза', blip='blip_rosa', place='бар «У Розы»'),
    'zakhar': dict(title='Захар', blip='blip_zakhar', place='лодочный сарай в Нефтегавани'),
    'grom': dict(title='Гром', blip='blip_grom', place='чайная в Заречье'),
    'prof': dict(title='Проф', blip='blip_prof', place='башня Профа'),
}


def contact_look(name):
    if name == 'vano':
        return make_look(skin=SKINS[2], hair=(0.1, 0.08, 0.06), shirt=(0.9, 0.9, 0.86), pants=(0.2, 0.24, 0.36),
                         torso='tank', beard=True, hat='cap', hat_color=(0.6, 0.1, 0.1), fat=1.3, scale=1.02,
                         model='m_red_h3')
    if name == 'rosa':
        return make_look(skin=SKINS[0], hair=(0.62, 0.1, 0.08), shirt=(0.8, 0.12, 0.3), pants=(0.8, 0.12, 0.3),
                         torso='tee', female=True, scale=0.97, fat=0.95, model='f_goth')
    if name == 'zakhar':
        return make_look(skin=SKINS[1], hair=(0.75, 0.75, 0.75), shirt=(0.4, 0.42, 0.44), pants=(0.2, 0.26, 0.4),
                         torso='tee', beard=True, scale=0.98, fat=1.05, model='m_grey_h4b')
    if name == 'grom':
        return make_look(skin=SKINS[1], hair=(0.2, 0.18, 0.16), shirt=(0.2, 0.3, 0.6), pants=(0.12, 0.14, 0.2),
                         torso='police', scale=1.04, fat=1.15, model='cop_m')
    if name in ('bruce', 'boss'):
        from .story import person_look
        return person_look(name)
    if name == 'kostya':
        return make_look(skin=SKINS[1], hair=(0.2, 0.16, 0.1), shirt=(0.12, 0.12, 0.12), pants=(0.2, 0.2, 0.24),
                         torso='jacket', scale=1.0, model='m_leather_b')
    return make_look(skin=SKINS[5], hair=(0.7, 0.7, 0.72), shirt=(0.3, 0.3, 0.36), pants=(0.3, 0.3, 0.36),
                     torso='jacket', glasses=True, scale=1.0, fat=0.95, model='m_old')


class MissionFailed(Exception):
    def __init__(self, reason='', quiet=False):
        Exception.__init__(self, reason)
        self.reason = reason
        self.quiet = quiet


class Run(object):
    """Контекст выполняемого задания (передаётся в сценарий-генератор)."""

    def __init__(self, ms, spec):
        self.ms = ms
        self.w = ms.w
        self.spec = spec
        self.wait = None
        self.blips = []
        self.markers = []
        self.arrows = []
        self.vehicles = []
        self.peds = []
        self.pickups = []
        self.watch_list = []
        self.ticks = []
        self.timer = None
        self.timer_fail = 'Время вышло.'
        self.reward = spec.get('reward', 0)
        self.objective = ''
        self.kills = 0
        self.side = spec.get('side', False)
        self.gen = spec['fn'](self)

    # --- сообщения
    def say(self, text, dur=None):
        self.w.hud.subtitle(text, dur)

    def obj(self, text):
        self.objective = text
        self.w.hud.subtitle(text, 5.0, clear=True)

    def help(self, text, dur=6.0):
        self.w.hud.help(text, dur)

    def counter(self, text):
        self.w.hud.set_counter(text)

    # --- метки
    def blip(self, x=0.0, y=0.0, obj=None, tex='blip_dest', color=(1, 1, 1, 1), scale=1.15):
        b = self.w.hud.add_blip(tex, x, y, obj, color, scale, True)
        self.blips.append(b)
        return b

    def unblip(self, b):
        if b is not None:
            self.w.hud.remove_blip(b)
            if b in self.blips:
                self.blips.remove(b)

    def marker(self, x, y, r=3.5, color=YELLOW):
        mk = Marker(self.w, x, y, r, color)
        self.markers.append(mk)
        self.ms.markers.append(mk)
        return mk

    def unmark(self, mk):
        if mk is not None:
            mk.remove()
            if mk in self.markers:
                self.markers.remove(mk)
            if mk in self.ms.markers:
                self.ms.markers.remove(mk)

    def arrow(self, obj, color=YELLOW):
        a = Arrow(self.w, obj, color=color)
        self.arrows.append(a)
        self.ms.arrows.append(a)
        return a

    def unarrow(self, a):
        if a is not None:
            a.remove()
            if a in self.arrows:
                self.arrows.remove(a)
            if a in self.ms.arrows:
                self.ms.arrows.remove(a)

    # --- сущности
    def car(self, kind, x, y, yaw, paint=None, clear=6.0):
        self.ms.clear_area(x, y, clear)
        v = self.w.spawn_vehicle(kind, x, y, yaw, paint)
        v.keep = True
        v.mission = self
        v.mode = Vehicle.PARKED
        self.vehicles.append(v)
        return v

    def npc(self, x, y, yaw, look, weapon=None, hp=100.0, kind='mission'):
        p = self.w.spawn_ped(x, y, yaw, look, kind)
        p.keep = True
        p.mission = self
        p.health = p.max_health = hp
        p.set_state('stand')
        if weapon is not None:
            p.set_weapon(weapon)
        self.peds.append(p)
        return p

    def enemy(self, x, y, yaw, look, weapon=W_PISTOL, hp=100.0, accuracy=0.38, radius=26.0, gang=None):
        x, y = self.ms.free_spot(x, y)
        p = self.npc(x, y, yaw, look, weapon, hp, 'enemy')
        p.hostile = True
        p.guard_pos = (x, y)
        p.guard_radius = radius
        p.accuracy = accuracy
        p.brave = 1.0
        p.gang = gang
        p.money = random.randint(40, 160)
        p.set_state('guard')
        return p

    def watch(self, obj, reason):
        self.watch_list.append((obj, reason))

    def unwatch(self, obj):
        self.watch_list = [(o, r) for (o, r) in self.watch_list if o is not obj]

    def fail(self, reason):
        raise MissionFailed(reason)

    # --- таймер
    def set_timer(self, seconds, fail='Время вышло.'):
        self.timer = float(seconds)
        self.timer_fail = fail

    def stop_timer(self):
        self.timer = None
        self.w.hud.set_timer(None)

    # --- готовые шаги (использовать через yield from)
    def goto(self, x, y, r=4.0, text=None, vehicle=None, on_foot=None, stopped=True, color=YELLOW,
             tex='blip_dest', extra=None):
        if text:
            self.obj(text)
        b = self.blip(x, y, tex=tex)
        mk = self.marker(x, y, r, color)
        mk.need_foot = on_foot
        pl = self.w.player

        def cond():
            if extra is not None and not extra():
                return False
            if vehicle is not None and pl.vehicle is not vehicle:
                return False
            if not mk.player_inside(on_foot):
                return False
            if stopped and pl.vehicle is not None and pl.speed() > 2.5:
                return False
            return True
        yield cond
        self.unblip(b)
        self.unmark(mk)

    def enter(self, v, text=None, tex='blip_friend'):
        if text:
            self.obj(text)
        b = self.blip(obj=v, tex=tex)
        a = self.arrow(v)
        pl = self.w.player
        yield lambda: pl.vehicle is v
        self.unblip(b)
        self.unarrow(a)

    def drive(self, v, x, y, r=5.0, text=None, back='Вернись в машину.', extra=None, tex='blip_dest',
              stopped=True):
        """Довести машину v до точки.  Пока игрок не за рулём, метка показывает на саму машину."""
        pl = self.w.player
        while True:
            if pl.vehicle is not v:
                yield from self.enter(v, back)
            if text:
                self.obj(text)
            b = self.blip(x, y, tex=tex)
            mk = self.marker(x, y, r)
            res = [None]

            def cond():
                if pl.vehicle is not v:
                    res[0] = 'out'
                    return True
                if extra is not None and not extra():
                    return False
                if not mk.player_inside(None):
                    return False
                if stopped and pl.speed() > 2.5:
                    return False
                res[0] = 'done'
                return True
            yield cond
            self.unblip(b)
            self.unmark(mk)
            if res[0] == 'done':
                return

    def board(self, ped, v, timeout=14.0):
        """Персонаж подбегает к машине игрока и садится."""
        w = self.w
        t = [0.0]
        ped.set_state('goto', 1.0)

        def cond():
            t[0] += w.dt
            if ped.dead or v.dead or v.removed:
                return True
            dx, dy = v.door_pos(1)
            ped.tx, ped.ty = dx, dy
            if ped.state != 'goto':
                ped.set_state('goto', 1.0)
            d = math.hypot(dx - ped.x, dy - ped.y)
            return (d < 1.3 and math.hypot(v.vx, v.vy) < 2.5) or t[0] > timeout
        yield cond
        if not ped.dead and not v.dead:
            w.put_in_vehicle(ped, v)
            w.audio.play_at('door', v.x, v.y, 0.8)

    def unboard(self, ped, walk_to=None):
        w = self.w
        if ped.vehicle is not None:
            w.take_out(ped, 1)
            w.audio.play_at('door', ped.x, ped.y, 0.8)
        if walk_to is not None:
            ped.tx, ped.ty = walk_to
            ped.set_state('goto', 0.0)

    def kill_all(self, peds, text=None, label='Осталось'):
        if text:
            self.obj(text)
        bl = [(p, self.blip(obj=p, tex='blip_enemy', scale=0.9)) for p in peds]

        def cond():
            alive = 0
            for p, b in bl:
                if p.dead or p.removed:
                    if not b.removed:
                        self.unblip(b)
                else:
                    alive += 1
            self.counter('%s: %d' % (label, alive))
            return alive == 0
        yield cond
        self.counter(None)

    def lose_cops(self, text='Уйди от погони: скройся из виду или перекрась машину.'):
        pol = self.w.police
        if pol.level > 0:
            self.obj(text)
            yield lambda: pol.level == 0

    def briefing(self, contact, lines):
        """Сценка-разговор с контактом у него в помещении (Enter или пробел — следующая реплика).

        Строка, начинающаяся с «Макс: », — реплика героя, остальные произносит хозяин.  После разговора
        герой оказывается на улице у двери, и задание продолжается там."""
        ms = self.ms
        w = self.w
        pl = w.player
        its = w.interiors
        room = its.rooms.get(contact)
        if room is None:
            yield from self._briefing_street(contact, lines)
            return
        if its.current is not room:
            its.enter(contact, instant=True)
        npc = its.resident(contact)
        x, y, yaw = room.spots['talk']
        pl.freeze = True
        p = pl.ped
        p.x, p.y = x, y
        p.speed = 0.0
        if npc is not None:
            nx, ny = npc.x, npc.y
        else:
            nx, ny = x + math.cos(yaw) * 1.6, y + math.sin(yaw) * 1.6
        d = math.hypot(nx - x, ny - y) or 1.0
        ux, uy = (nx - x) / d, (ny - y) / d
        rx, ry = uy, -ux
        p.yaw = math.atan2(uy, ux)
        p.sync()
        sit = bool(npc is not None and npc.resident['sit'])
        home = npc.yaw if npc is not None else 0.0
        if npc is not None and not sit:
            npc.yaw = math.atan2(-uy, -ux)               # хозяин поворачивается к гостю
        hz = 1.16 if sit else 1.5
        mx, my = x + ux * d * 0.5, y + uy * d * 0.5
        shots = dict(
            wide=(mx + rx * (2.4 + d * 0.5), my + ry * (2.4 + d * 0.5), 1.6, mx, my, 1.25),
            npc=(x - ux * 0.95 + rx * 0.6, y - uy * 0.95 + ry * 0.6, 1.68, nx, ny, hz),
            hero=(nx - ux * 0.2 - rx * 0.8, ny - uy * 0.2 - ry * 0.8, hz + 0.12, x, y, 1.55))
        w.hud.show(False)
        w.hud.mission_title('')              # заголовок не должен висеть поверх сценки
        ms.letterbox(True)
        w.hud.clear_subtitles()
        title = CONTACTS[contact]['title']
        inp = w.game.inp
        for i, line in enumerate(lines):
            hero = line.startswith('Макс: ')
            w.cam.override = shots['wide' if i == 0 else ('hero' if hero else 'npc')]
            if npc is not None:
                if hero:
                    npc.play('sit' if sit else 'listen', True)
                else:
                    npc.play('sit_talk' if sit else 'talk', True)
            p.play('talk' if hero else 'listen', True)
            dur = 1.8 + len(line) * 0.06
            w.hud.subtitle(line if hero else '%s: %s' % (title, line), dur + 0.5, clear=True)
            t = [0.0]

            def cond():
                t[0] += w.dt
                if t[0] > 0.4 and (inp.hit('enter') or inp.hit('space') or inp.hit('mouse1')):
                    return True
                return t[0] > dur
            yield cond
        w.hud.clear_subtitles()
        w.hud.fade(1.0, 6.0)
        yield 0.25
        if npc is not None:
            npc.stop_act()
            npc.yaw = home
        p.stop_act()
        its.leave(instant=True)
        w.cam.override = None
        pl.freeze = False
        pl.no_enter_t = 0.7                  # реплики листали клавишей Enter — она же сажает в машину
        w.hud.show(True)
        ms.letterbox(False)
        w.hud.fade(0.0, 3.0)
        w.hud.mission_title(self.spec['title'])

    def _briefing_street(self, contact, lines):
        """Разговор у двери на улице — для контактов без своего помещения."""
        ms = self.ms
        w = self.w
        pl = w.player
        lmk = w.city.landmarks[contact]
        dx, dy = lmk['door']
        npc = self.npc(dx, dy + 1.0, -math.pi / 2, contact_look(contact))
        npc.idle_clip = 'talk'
        ms.clear_area(dx, dy, 3.0, peds=True, keep=npc)
        pl.freeze = True
        p = pl.ped
        p.idle_clip = 'listen'
        p.x, p.y = dx, dy - 0.9
        p.yaw = math.pi / 2
        p.speed = 0.0
        p.sync()
        w.cam.override = (dx + 2.6, dy - 3.6, 1.9, dx - 0.3, dy + 0.4, 1.45)
        w.hud.show(False)
        w.hud.mission_title('')              # заголовок не должен висеть поверх сценки
        ms.letterbox(True)
        w.hud.clear_subtitles()
        title = CONTACTS[contact]['title']
        inp = w.game.inp
        for line in lines:
            dur = 1.8 + len(line) * 0.06
            w.hud.subtitle('%s: %s' % (title, line), dur + 0.5, clear=True)
            t = [0.0]

            def cond():
                t[0] += w.dt
                if t[0] > 0.4 and (inp.hit('enter') or inp.hit('space') or inp.hit('mouse1')):
                    return True
                return t[0] > dur
            yield cond
        w.hud.clear_subtitles()
        w.cam.override = None
        w.cam.pitch = -0.2
        w.cam.face(p.x, p.y, -math.pi / 2)
        p.yaw = -math.pi / 2
        p.idle_clip = None
        pl.freeze = False
        w.hud.show(True)
        ms.letterbox(False)
        w.remove_ped(npc)
        if npc in self.peds:
            self.peds.remove(npc)
        w.hud.mission_title(self.spec['title'])


# ---------------------------------------------------------------------------
# сценарии заданий
# ---------------------------------------------------------------------------
def m_v1(m):
    w = m.w
    c = w.city
    yield from m.briefing('vano', [
        'А, Макс! Слыхал про тебя. Говорят, баранку крутишь как бог.',
        'Проверим. Мой механик Гога застрял в Порту — тачка сдохла.',
        'Бери мою «Волну» и привези его сюда. И не поцарапай!'])
    rx, ry = c.landmarks['vano']['road']
    car = m.car('sedan', rx - 7.0, ry, 0.0, paint=1)
    m.watch(car, 'Машина Вано уничтожена.')
    m.help('F — сесть в машину. W/S — газ и тормоз, A/D — руль, пробел — ручной тормоз.', 9.0)
    yield from m.enter(car, 'Садись в «Волну» Вано.')
    px, py = c.landmarks['port']['road']
    goga = m.npc(px + 4.0, py + 3.3, -math.pi / 2,
                 make_look(skin=SKINS[3], hair=(0.05, 0.05, 0.05), shirt=(0.2, 0.3, 0.5), pants=(0.2, 0.3, 0.5),
                           torso='vest', hat='cap', hat_color=(0.2, 0.3, 0.5), beard=True))
    m.watch(goga, 'Гога погиб.')
    yield from m.goto(px, py, 5.0, 'Езжай в Порт и забери Гогу.', vehicle=car)
    m.say('Гога: Наконец-то! Я тут уже корни пустил.')
    yield from m.board(goga, car)
    yield from m.goto(rx, ry, 5.0, 'Отвези Гогу в гараж Вано.', vehicle=car,
                      extra=lambda: goga.vehicle is car)
    m.unwatch(goga)
    m.unboard(goga, c.landmarks['vano']['door'])
    m.say('Вано: Ни царапины? Ну, почти. Держи, заработал.')
    yield 2.0


def m_v2(m):
    w = m.w
    c = w.city
    yield from m.briefing('vano', [
        'Один фраер из Сосновки должен мне денег. Давно должен.',
        'Заберём долг его тачкой. Красная «Комета», стоит возле дома.',
        'Её будут искать, так что сперва перекрась — и ко мне в гараж.',
        'Каждая вмятина — минус из твоей доли.'])
    spots = [s for s in c.parking if s.get('zone') == 'R' and s.get('block', -1) >= 0 and not s.get('kind')]
    spots.sort(key=lambda s: (s['x'] - 150.0) ** 2 + (s['y'] - 250.0) ** 2)
    s = spots[0] if spots else dict(x=150.0, y=250.0, yaw=0.0)
    car = m.car('sports', s['x'], s['y'], s['yaw'], paint=0)
    m.watch(car, '«Комета» уничтожена.')
    yield from m.enter(car, 'Угони красную «Комету» в Сосновке.', tex='blip_dest')
    w.police.set_level(max(w.police.level, 2))
    w.audio.play('pager', 0.8)
    m.help('Сработала сигнализация! Покрасочная отмечена на радаре баллончиком.', 8.0)
    pol = w.police
    m.obj('Перекрась машину в покрасочной, чтобы сбить погоню.')
    yield lambda: pol.level == 0 and w.player.vehicle is car
    rx, ry = c.landmarks['vano']['road']
    yield from m.goto(rx, ry, 5.0, 'Пригони «Комету» в гараж Вано.', vehicle=car)
    k = clamp(car.health / car.max_health, 0.25, 1.0)
    m.reward = int(m.spec['reward'] * k / 50.0) * 50
    m.say('Вано: %s' % ('Как новенькая! Красавец.' if k > 0.85 else 'Ну и что ты с ней сделал, а? Вычитаю.'))
    w.player.leave_vehicle(force=True)
    car.locked = True
    car.keep = False
    yield 2.0


def m_v3(m):
    w = m.w
    c = w.city
    yield from m.briefing('vano', [
        'В Порту открылся автосервис «Мотор». Цены сбивают, гады.',
        'Спали три их фургона — пусть знают, чей это город.',
        'Вот тебе коктейли. Фирменный рецепт, бабушкин.'])
    w.player.give_weapon(W_MOLOTOV, 10)
    m.help('Колесо мыши или Q/E — выбрать коктейль Молотова. ЛКМ — бросить.', 8.0)
    spots = [s for s in c.parking if s.get('zone') == 'I']
    random.Random(5).shuffle(spots)
    chosen = []
    for s in spots:
        if all((s['x'] - o['x']) ** 2 + (s['y'] - o['y']) ** 2 > 70.0 ** 2 for o in chosen):
            chosen.append(s)
        if len(chosen) == 3:
            break
    vans = []
    for i, s in enumerate(chosen):
        v = m.car('van', s['x'], s['y'], s['yaw'], paint=2)
        vans.append(v)
        g = m.enemy(s['x'] + 3.0, s['y'] + 2.0, 0.0, gang_look('greens'), W_BAT if i == 0 else W_PISTOL, 100.0,
                    radius=16.0)
    bl = [(v, m.blip(obj=v, tex='blip_enemy')) for v in vans]
    m.obj('Уничтожь три фургона конкурентов в Порту.')

    def cond():
        left = 0
        for v, b in bl:
            if v.dead or v.removed:
                if not b.removed:
                    m.unblip(b)
            else:
                left += 1
        m.counter('Фургонов: %d' % left)
        return left == 0
    yield cond
    m.counter(None)
    yield 1.0
    yield from m.lose_cops()
    m.say('Вано: Слышал, в Порту сегодня жарко. Молодец.')
    yield 1.5


def m_v4(m):
    w = m.w
    c = w.city
    yield from m.briefing('vano', [
        'Спорим, ты не объедешь весь город за три с половиной минуты?',
        'Ставлю три штуки. Тачку даю свою, лучшую.',
        'Время пойдёт, как только тронешься. Не подведи «Комету».'])
    rx, ry = c.landmarks['vano']['road']
    car = m.car('sports', rx - 7.0, ry, 0.0, paint=6)
    m.watch(car, 'Машина разбита.')
    yield from m.enter(car, 'Садись в «Комету».')
    # маршрут по перекрёсткам проспектов
    route = [(0, 2), (3, 2), (6, 2), (8, 2), (10, 2), (10, 5), (8, 5), (6, 5), (3, 5), (0, 5), (0, 4)]
    pts = [(c.nodes[n].x, c.nodes[n].y) for n in route if n in c.nodes]
    pts.append((rx, ry))
    m.set_timer(210.0)
    n = len(pts)
    for i, (x, y) in enumerate(pts):
        m.counter('Точка %d из %d' % (i + 1, n))
        last = i == n - 1
        yield from m.goto(x, y, 9.0 if not last else 5.0, 'Гони по контрольным точкам!' if i == 0 else None,
                          vehicle=car, stopped=last, tex='blip_race')
        w.audio.play('pickup', 0.7)
    left = m.timer
    m.stop_timer()
    m.counter(None)
    m.say('Вано: Успел! Осталось %d сек. Забирай выигрыш.' % int(left))
    yield 2.0


def m_r1(m):
    w = m.w
    c = w.city
    yield from m.briefing('rosa', [
        'Ты от Вано? Проходи, красавчик. Есть дело.',
        'Четверо отморозков повадились трясти моих поставщиков.',
        'Объясни им вежливо. Вот тебе аргумент.'])
    w.player.give_weapon(W_BAT)
    w.player.select(W_BAT)
    x, y = m.ms.place_near(c.landmarks['rosa']['door'], 110.0, 190.0, seed=3)
    thugs = []
    for i in range(4):
        a = i * 1.57
        thugs.append(m.enemy(x + math.cos(a) * 1.8, y + math.sin(a) * 1.8, a + math.pi, gang_look('purple'),
                             W_BAT if i % 2 else W_FIST, 90.0, radius=13.0, gang='purple'))
    yield from m.kill_all(thugs, 'Найди вымогателей и разберись с ними.')
    m.say('Роза: Вежливо, говоришь? Мне нравится твой стиль.')
    yield 2.0


def m_r2(m):
    w = m.w
    c = w.city
    yield from m.briefing('rosa', [
        'Мои девочки развезли выручку по тайникам, а на хвост сели копы.',
        'Пять свёртков. Собери все, пока их не нашли.',
        'Потом вези сюда. И без глупостей, красавчик.'])
    door = c.landmarks['rosa']['door']
    spots = []
    for k in range(40):
        x, y = m.ms.place_near(door, 120.0, 330.0, seed=100 + k)
        if all((x - a) ** 2 + (y - b) ** 2 > 80.0 ** 2 for a, b in spots):
            spots.append((x, y))
        if len(spots) == 5:
            break
    items = []
    for (x, y) in spots:
        pk = m.ms.add_pickup('item', x, y)
        m.pickups.append(pk)
        items.append((pk, m.blip(x, y, tex='blip_pickup')))
    m.set_timer(60.0 + 36.0 * len(items))
    m.obj('Собери пять свёртков, пока не вышло время.')
    m.help('Свёртки подбираются пешком. Машина сильно сэкономит время.', 7.0)

    def cond():
        left = 0
        for pk, b in items:
            if pk.removed:
                if not b.removed:
                    m.unblip(b)
            else:
                left += 1
        m.counter('Свёртков: %d' % left)
        return left == 0
    yield cond
    m.stop_timer()
    m.counter(None)
    yield from m.goto(door[0], door[1], 1.8, 'Отнеси выручку Розе.', on_foot=True, color=PINK, tex='blip_rosa')
    m.say('Роза: Всё до копеечки. Ты мне нравишься всё больше.')
    yield 2.0


def m_r3(m):
    w = m.w
    c = w.city
    yield from m.briefing('rosa', [
        '«Красные» из Ржавого квартала решили, что мой бар теперь их.',
        'Их логово — во дворе неподалёку. Восемь стволов.',
        'Покажи им, чей это район. «Узи» и бронежилет — за счёт заведения.'])
    w.player.give_weapon(W_UZI, 180)
    w.player.select(W_UZI)
    w.player.ped.armor = 100.0
    x, y = m.ms.place_near(c.landmarks['rosa']['door'], 150.0, 260.0, seed=17, zone='G')
    gang = []
    for i in range(8):
        a = i * 0.785
        r = 2.5 + (i % 3) * 2.2
        wpn = (W_PISTOL, W_PISTOL, W_UZI, W_BAT)[i % 4]
        gang.append(m.enemy(x + math.cos(a) * r, y + math.sin(a) * r, a, gang_look('reds'), wpn, 110.0, 0.36,
                            30.0, gang='reds'))
    yield from m.kill_all(gang, 'Перебей банду «красных».', 'Бандитов')
    yield from m.lose_cops()
    m.say('Роза: Теперь в районе будет тихо. Заходи вечером — угощаю.')
    yield 2.0


def m_r4(m):
    w = m.w
    c = w.city
    yield from m.briefing('rosa', [
        'Надо отвезти кассу в банк. Сама поеду, ты — за рулём.',
        '«Красные» ничего не забыли. Будут гнаться — не останавливайся.',
        'Довезёшь меня целой — озолочу.'])
    rx, ry = c.landmarks['rosa']['road']
    car = m.car('suv', rx - 7.0, ry, 0.0, paint=3)
    car.health = car.max_health = 1900.0
    door = c.landmarks['rosa']['door']
    rosa = m.npc(door[0] + 1.5, door[1], -math.pi / 2, contact_look('rosa'), hp=160.0)
    m.watch(car, 'Машина уничтожена.')
    m.watch(rosa, 'Роза погибла.')
    yield from m.enter(car, 'Садись в машину Розы.')
    yield from m.board(rosa, car)
    bx, by = c.landmarks['bank']['road']
    chase = m.ms.start_chasers(m, ['lowrider', 'muscle', 'pickup'], 'reds', 3, 9.0)
    yield from m.goto(bx, by, 5.5, 'Отвези Розу в банк. Не дай «красным» вас достать!', vehicle=car,
                      extra=lambda: rosa.vehicle is car)
    chase['active'] = False
    m.unwatch(rosa)
    m.unboard(rosa, c.landmarks['bank']['door'])
    m.say('Роза: Ух! Давно меня так не катали. Ты — лучший.')
    yield 2.5


def m_z1(m):
    w = m.w
    c = w.city
    pl = w.player
    pol = w.police
    yield from m.briefing('zakhar', [
        'Ты и есть водитель от Розы? Захар. Рыбу не ловлю, а сети ставлю.',
        'Ночью мой катер уходил от погранцов и сбросил три ящика у берега.',
        'Макс: Кто первый нашёл — тот и молодец?',
        'Соображаешь. «Трудяга» у ворот. Привези все три. И без хвоста.'])
    rx, ry = c.landmarks['zakhar']['road']
    car = m.car('pickup', rx - 7.0, ry, 0.0, paint=2)
    m.watch(car, '«Трудяга» Захара уничтожена.')
    yield from m.enter(car, 'Садись в «Трудягу» Захара.')
    m.help('Ящики лежат в стороне от дорог. Подъезжай поближе и выходи из машины: грузить придётся руками.', 8.0)
    places = ((1000.0, -243.0, 'Первый ящик выбросило на пляж за дюной, южнее дач Маячного.'),
              (1161.0, 258.0, 'Второй ящик — в траве у дороги за аэродромом.'),
              (686.0, 40.0, 'Третий ящик — на берегу пролива у Нефтегавани.'))
    for i, (x, y, text) in enumerate(places):
        x, y = m.ms.free_spot(x, y)
        pk = m.ms.add_pickup('crate', x, y)
        m.pickups.append(pk)
        b = m.blip(x, y, tex='blip_pickup')
        m.counter('Ящиков: %d из 3' % i)
        if i == 2:
            thugs = [m.enemy(x + 2.4 * math.cos(a), y + 2.4 * math.sin(a), a + math.pi, gang_look('greens'),
                             wpn, 100.0, 0.34, 22.0, gang='greens')
                     for a, wpn in ((0.2, W_PISTOL), (1.4, W_BAT), (-1.2, W_PISTOL))]
            yield from m.kill_all(thugs, 'Третий ящик нашли чужие. Разберись с ними.', 'Чужих')
            m.counter('Ящиков: 2 из 3')
        m.obj(text)
        yield lambda: pk.removed
        m.unblip(b)
        if i == 1:
            pol.set_level(max(pol.level, 2))
            w.audio.play('siren', 0.5)
            m.help('Тебя заметил пограничный наряд! К Захару с таким хвостом нельзя.', 7.0)
    m.counter('Ящиков: 3 из 3')
    yield 0.5
    yield from m.lose_cops('За тобой хвост. Оторвись, прежде чем ехать к Захару.')
    m.counter(None)
    yield from m.drive(car, rx, ry, 5.0, 'Отвези ящики к сараю Захара.', 'Ящики в «Трудяге». Вернись в машину.')
    pl.leave_vehicle(force=True)
    car.locked = True
    car.keep = False
    m.say('Захар: Все три, и сухие. Роза не соврала — руки у тебя на месте.')
    yield 2.5


def m_z2(m):
    w = m.w
    c = w.city
    pl = w.player
    yield from m.briefing('zakhar', [
        'На причале у Портового моста стоит мой фургон. В кузове сорок ящиков «минералки».',
        'Бутылки бьются, а покупатель нервный. Каждый удар — минус из твоей доли.',
        'Макс: Куда везти?',
        'На аэродром, к самолёту. И оглядывайся: на мой товар есть охотники.'])
    vx, vy = 478.0, 30.0
    for x, y in ((470.0, 30.0), (471.0, 16.0), (490.0, 40.0)):       # свободное место между контейнерами
        if not w.static.overlap_circle(x, y, 3.8, F_CAR):
            vx, vy = x, y
            break
    van = m.car('van', vx, vy, math.pi / 2, paint=5)
    van.health = van.max_health = 1800.0
    m.watch(van, 'Фургон с грузом уничтожен.')
    yield from m.enter(van, 'Забери фургон Захара на причале у Портового моста (на острове).', tex='blip_dest')
    lm = c.landmarks['airfield']
    ax, ay = lm['apron'][0] - 11.0, lm['apron'][1] + 14.0
    pilot = m.npc(ax + 8.6, ay - 2.0, math.pi,
                  make_look(skin=SKINS[1], hair=(0.3, 0.24, 0.16), shirt=(0.42, 0.34, 0.2), pants=(0.2, 0.2, 0.22),
                            torso='jacket', hat='cap', hat_color=(0.3, 0.26, 0.18), model='m_shirt_h3'))
    chase = m.ms.start_chasers(m, ['golf', 'pickup', 'muscle'], 'greens', 2, 14.0)

    def tick(dt):
        m.counter('Груз цел на %d%%' % int(100.0 * clamp(van.health / van.max_health, 0.0, 1.0)))
    m.ticks.append(tick)
    m.help('Охотники будут таранить. Не останавливайся — иначе выйдут и откроют огонь.', 8.0)
    yield from m.drive(van, ax, ay, 6.5, 'Вези груз на аэродром, к самолёту. Береги бутылки!',
                       'Груз в фургоне. Вернись за руль.')
    chase['active'] = False
    m.ticks.remove(tick)
    m.counter(None)
    k = clamp(van.health / van.max_health, 0.25, 1.0)
    m.reward = int(m.spec['reward'] * k / 50.0) * 50
    pl.leave_vehicle(force=True)
    van.locked = True
    van.keep = False
    m.say('Лётчик: %s' % ('Ни одной битой? Захару передай — летаю только с ним.' if k > 0.8 else
                          'Звенит, как мешок стекла. Захар за это вычтет.'))
    yield 2.5


def m_z3(m):
    w = m.w
    c = w.city
    pl = w.player
    rn = w.roadnet
    yield from m.briefing('zakhar', [
        'Про рейс на аэродром знали трое: я, ты и Сиплый с Маячного.',
        'Макс: Я не болтал.',
        'Знаю. Потому и говорю с тобой, а не о тебе. Он сидит на даче, с дружками.',
        'Навести его. Только учти: почует — рванёт к трассе. Уйдёт — сдаст нас всех.'])
    pl.give_weapon(W_UZI, 150)
    pl.select(W_UZI)
    road, (hx, hy), yaw = m.ms.roadside(947.0, -8.0, 4.6)
    car = m.car('muscle', road[0] + math.sin(yaw) * 2.1, road[1] - math.cos(yaw) * 2.1, yaw, paint=0)
    guards = []
    for i, (a, wpn) in enumerate(((0.4, W_PISTOL), (1.9, W_BAT), (3.3, W_UZI), (4.9, W_PISTOL))):
        guards.append(m.enemy(hx + math.cos(a) * 3.0, hy - 2.5 + math.sin(a) * 2.5, a, gang_look('greens'), wpn,
                              100.0, 0.34, 26.0, gang='greens'))
    b = m.blip(road[0], road[1], tex='blip_dest')
    mk = m.marker(road[0] - math.cos(yaw) * 9.0, road[1] - math.sin(yaw) * 9.0, 4.0, RED)
    m.obj('Езжай на Маячный, к даче Сиплого.')

    def spooked():
        px, py = pl.pos()
        if (px - hx) ** 2 + (py - hy) ** 2 < 50.0 ** 2:
            return True
        if car.dead or car.health < car.max_health:
            return True
        return any(g.dead or g.health < g.max_health for g in guards)
    yield spooked
    m.unblip(b)
    m.unmark(mk)
    for g in guards:
        if not g.dead:
            g.attack(pl.ped)
    if car.dead or car.removed or not m.ms.launch(car, 1.15):
        # машины у него больше нет: отбивается сам
        boss = m.enemy(hx, hy - 4.0, 0.0, make_look(skin=SKINS[1], hair=(0.5, 0.5, 0.5), shirt=(0.2, 0.3, 0.22),
                                                    pants=(0.2, 0.2, 0.22), torso='jacket', model='m_grey_h3'),
                       W_SHOTGUN, 170.0, 0.4, 30.0, gang='greens')
        boss.attack(pl.ped)
        yield from m.kill_all([boss], 'Сиплый остался без колёс. Добей его.', 'Сиплый')
        m.counter(None)
    else:
        car.health = car.max_health = 1100.0
        bl = m.blip(obj=car, tex='blip_enemy')
        a = m.arrow(car, RED)
        m.obj('Сиплый прыгнул в машину! Уничтожь её, пока он не ушёл по трассе.')
        m.help('Тарань, стреляй, перегораживай дорогу — лишь бы «Бизон» не доехал до Заречья.', 8.0)
        w.audio.play_at('door', car.x, car.y, 0.9)
        goal = c.nodes.get((10, 11)) or c.nearest_node(452.0, 823.0)
        gx, gy = goal.x, goal.y

        def tick(dt):
            if car.dead or car.removed:
                return
            if car.mode == Vehicle.RAIL:
                w.traffic.route_step(car, (goal.i, goal.j))
            if math.hypot(car.x - gx, car.y - gy) < 20.0:
                raise MissionFailed('Сиплый ушёл по трассе.')
        m.ticks.append(tick)
        yield lambda: car.dead or car.removed
        m.ticks.remove(tick)
        m.unblip(bl)
        m.unarrow(a)
    yield 1.0
    yield from m.lose_cops()
    m.say('Захар (по телефону): Слышал, на Маячном нынче тихо. Заезжай — рассчитаемся.')
    yield 2.5


def m_g1(m):
    w = m.w
    c = w.city
    pl = w.player
    pol = w.police
    yield from m.briefing('grom', [
        'Майор Громов. Для своих — Гром. Сядь, не маячь.',
        'Твою «Трудягу» с ящиками засняли мои люди. Плёнка лежит у меня, а не в деле. Пока.',
        'Макс: И сколько стоит это «пока»?',
        'Услугу. У участка на острове стоит изъятая «Комета», в багажнике — чужой товар.',
        'Пригони её сюда до описи. Погоню отзову, когда доедешь. Не раньше.'])
    sx, sy = c.landmarks['police']['road']
    x, y = sx + 13.0, sy + 2.9
    for dx in (13.0, 20.0, -20.0, 27.0, -27.0):
        if not w.static.overlap_circle(sx + dx, sy + 2.9, 2.2, F_CAR):
            x = sx + dx
            break
    car = m.car('sports', x, y, 0.0, paint=0)
    m.watch(car, '«Комета» уничтожена.')
    yield from m.enter(car, 'Угони изъятую «Комету» от полицейского участка на острове.', tex='blip_dest')
    pol.locked = 3
    pol.set_level(3)
    w.audio.play('siren', 0.6)
    m.help('Весь участок на ушах. Перекраска не поможет — гони в Заречье через Большой мост.', 8.0)
    rx, ry = c.landmarks['grom']['road']
    yield from m.drive(car, rx, ry, 5.0, 'Пригони «Комету» к чайной Грома в Заречье.',
                       'Товар в багажнике «Кометы». Вернись в неё.')
    pol.locked = None
    pol.clear()
    pl.leave_vehicle(force=True)
    car.locked = True
    car.keep = False
    m.say('Гром (в рацию): Всем постам — отбой, машина найдена. …Свободен, водитель. Пока.')
    yield 3.0


def m_g2(m):
    w = m.w
    c = w.city
    pl = w.player
    pol = w.police
    yield from m.briefing('grom', [
        'В Заречье и Слободе три заведения платят мне за спокойствие. Сегодня день сбора.',
        'Возьмёшь мою служебную: человеку в такой машине вопросов не задают.',
        'Макс: А если кто-то не захочет платить?',
        'Тогда объясни ему, что спокойствие — вещь хрупкая.'])
    rx, ry = c.landmarks['grom']['road']
    car = m.car('police', rx - 7.0, ry, 0.0)
    m.watch(car, 'Служебная машина Грома уничтожена.')
    yield from m.enter(car, 'Садись в служебную машину Грома.')
    # три лавки на торговых улицах Заречья: середины сторон кварталов
    stops = ((120.0, 914.0, 'Хозяин пекарни'), (175.0, 866.0, 'Хозяйка аптеки'), (-105.0, 866.0, 'Хозяин мастерской'))
    r = random.Random(11)
    m.set_timer(240.0, 'Заведения закрылись. Гром остался без выручки.')
    for i, (x, y, who) in enumerate(stops):
        road, side, yaw = m.ms.roadside(x, y, 4.6)
        look = random_look(r, 'O')
        look.female = i == 1
        owner = m.npc(side[0], side[1], yaw + math.pi / 2, look, hp=140.0)
        m.counter('Собрано: %d из 3' % i)
        yield from m.drive(car, road[0], road[1], 5.0, 'Собери плату: точка %d из 3.' % (i + 1),
                           'Без машины Грома с тобой говорить не станут. Вернись в неё.')
        if i < 2:
            m.say('%s: %s' % (who, ('Вот, всё как договаривались. Привет майору.',
                                    'Опять? Ладно, ладно… Держи. Чтоб он подавился.')[i]))
            w.audio.play('pickup', 0.7)
            yield 1.6
            continue
        m.stop_timer()
        m.say('%s: Передай Грому: у меня теперь другая крыша. Вон она, кстати.' % who)
        yield 1.4
        thugs = []
        for k, wpn in enumerate((W_PISTOL, W_BAT, W_UZI, W_PISTOL)):
            # «крыша» бежит от углов квартала: по тротуару с обеих сторон
            d = (34.0 + k * 2.0) * (1 if k % 2 == 0 else -1)
            e = m.enemy(side[0] + math.cos(yaw) * d, side[1] + math.sin(yaw) * d, yaw + (math.pi if d > 0 else 0.0),
                        gang_look('purple'), wpn, 100.0, 0.34, 40.0, gang='purple')
            e.attack(pl.ped)
            thugs.append(e)
        pl.give_weapon(W_PISTOL, 51)
        yield from m.kill_all(thugs, 'Разберись с новой «крышей».', 'Бандитов')
        m.counter('Собрано: 2 из 3')
        pol.clear()
        m.help('Стрельбу Гром спишет на учения: полиция ничего «не видела».', 7.0)
        ox, oy = (owner.x, owner.y) if not owner.removed else side
        pk = m.ms.add_pickup('item', ox + math.cos(yaw) * 1.2, oy + math.sin(yaw) * 1.2)
        m.pickups.append(pk)
        b = m.blip(pk.x, pk.y, tex='blip_pickup')
        if not owner.dead:
            m.say('%s: Всё, всё! Плачу! Забирай!' % who)
        m.obj('Забери деньги.')
        yield lambda: pk.removed
        m.unblip(b)
    m.counter('Собрано: 3 из 3')
    yield from m.drive(car, rx, ry, 5.0, 'Отвези выручку Грому в чайную.', 'Вернись в машину Грома.')
    m.counter(None)
    pol.clear()
    pl.leave_vehicle(force=True)
    car.locked = True
    car.keep = False
    m.say('Гром: Мастерскую теперь тоже охраняю я. Твоя доля — держи.')
    yield 2.5


def m_g3(m):
    w = m.w
    c = w.city
    pl = w.player
    pol = w.police
    yield from m.briefing('grom', [
        'Плохие новости, водитель. Сверху спустили приказ: сегодня берут Захара.',
        'Макс: И ты говоришь это мне?',
        'Старик платит мне десять лет. Сядет — заговорит. Мне это ни к чему.',
        'СОБР уже выехал. Бери «Комету». Две с половиной минуты — и чтобы духу его там не было.'])
    rx, ry = c.landmarks['grom']['road']
    car = m.car('sports', rx - 7.0, ry, 0.0, paint=0)
    yield from m.enter(car, 'Садись в «Комету».')
    zl = c.landmarks['zakhar']
    zx, zy = zl['road']
    m.set_timer(150.0, 'СОБР добрался до Захара раньше тебя.')
    m.help('Самый быстрый путь — по трассе вокруг залива: на восток, потом на юг.', 8.0)
    b = m.blip(zx, zy, tex='blip_zakhar')
    mk = m.marker(zx, zy, 5.5)
    m.obj('Гони в Нефтегавань, к сараю Захара!')
    old = [None]

    def arrived():
        # старик выходит к воротам, когда игрок уже рядом
        if old[0] is None and math.hypot(pl.pos()[0] - zx, pl.pos()[1] - zy) < 90.0:
            x, y = m.ms.free_spot(zl['door'][0] + 1.2, zl['door'][1] - 0.6)
            old[0] = m.npc(x, y, -math.pi / 2, contact_look('zakhar'), hp=220.0)
            m.watch(old[0], 'Захар погиб.')
        return pl.vehicle is not None and mk.player_inside(False) and pl.speed() < 2.5
    yield arrived
    m.unblip(b)
    m.unmark(mk)
    m.stop_timer()
    zakhar = old[0]
    m.say('Захар: Гром прислал? Вот уж от кого не ждал. Поехали!')
    yield from m.board(zakhar, pl.vehicle)
    pol.locked = 4
    pol.set_level(4)
    w.audio.play('siren', 0.6)
    lm = c.landmarks['airfield']
    ax, ay = lm['apron'][0] - 11.0, lm['apron'][1] + 14.0
    yield from m.goto(ax, ay, 6.5, 'СОБР на хвосте! Вези Захара на аэродром, к самолёту.',
                      extra=lambda: zakhar.vehicle is not None and zakhar.vehicle is pl.vehicle)
    pol.locked = None
    pol.clear()
    m.unwatch(zakhar)
    m.unboard(zakhar, (lm['apron'][0] - 11.0, lm['apron'][1] + 4.0))
    m.say('Захар: Не забуду, парень. Сарай и лодки — твои, пока не вернусь.')
    yield 3.0


def m_p1(m):
    w = m.w
    c = w.city
    yield from m.briefing('prof', [
        'Молодой человек, мне вас рекомендовали. Я ценю аккуратность.',
        'Бухгалтер Сёма решил побеседовать с прокурором.',
        'Сейчас его везут в участок. Сделайте так, чтобы не довезли.'])
    w.player.give_weapon(W_PISTOL, 68)
    rn = w.roadnet
    goal = c.nearest_node(*c.landmarks['police']['road'])
    start = c.nodes.get((1, 7)) or c.nearest_node(-380.0, 300.0)
    lane, s, d = rn.nearest_lane(start.x + 30.0, start.y, 80.0)
    m.ms.clear_area(*lane.pos(s)[:2], r=14.0)
    car = w.traffic.spawn_on_lane('sedan', lane, s, paint=3, persona=1.12)
    car.keep = True
    car.mission = m
    car.health = car.max_health = 1500.0
    m.vehicles.append(car)
    b = m.blip(obj=car, tex='blip_enemy')
    a = m.arrow(car, RED)
    m.obj('Останови машину со свидетелем, пока она не доехала до участка.')
    m.help('Тарань, стреляй, жги — способ на твой вкус. Главное — уничтожить машину.', 8.0)
    gx, gy = goal.x, goal.y

    def tick(dt):
        if car.dead or car.removed:
            return
        if car.mode == Vehicle.RAIL:
            w.traffic.route_step(car, (goal.i, goal.j))
        if math.hypot(car.x - gx, car.y - gy) < 16.0:
            raise MissionFailed('Свидетель добрался до участка.')
    m.ticks.append(tick)
    yield lambda: car.dead or car.removed
    m.ticks.remove(tick)
    m.unblip(b)
    m.unarrow(a)
    yield 1.0
    yield from m.lose_cops()
    m.say('Проф: Чистая работа. Сёма, увы, больше никому ничего не расскажет.')
    yield 2.0


def m_p2(m):
    w = m.w
    c = w.city
    yield from m.briefing('prof', [
        'В порту стоит армейский грузовик с… скажем так, оборудованием.',
        'Охрана вооружена и стреляет без предупреждения.',
        'Пригоните грузовик на мой склад в промзоне. Груз должен уцелеть.'])
    w.player.give_weapon(W_SHOTGUN, 24)
    yx, yy = c.landmarks['port']['yard']
    truck = m.car('army', yx, yy, 0.0)
    m.watch(truck, 'Грузовик уничтожен.')
    guards = []
    look = lambda: make_look(skin=random.choice(SKINS), shirt=(0.12, 0.14, 0.2), pants=(0.1, 0.1, 0.14),
                             torso='armor', hat='cap', hat_color=(0.1, 0.1, 0.14))
    for i, (ox, oy, wpn) in enumerate(((6, 4, W_PISTOL), (-6, 4, W_UZI), (7, -4, W_SHOTGUN), (-7, -4, W_PISTOL),
                                       (0, -7, W_UZI))):
        guards.append(m.enemy(yx + ox, yy + oy, 0.0, look(), wpn, 120.0, 0.4, 30.0))
    for g in guards:
        m.blip(obj=g, tex='blip_enemy', scale=0.8)
    yield from m.enter(truck, 'Угони армейский грузовик из порта. Охрана вооружена!', tex='blip_dest')
    for b in list(m.blips):
        m.unblip(b)
    w.police.set_level(max(w.police.level, 3))
    gx, gy = c.landmarks['guns2']['yard']
    yield from m.goto(gx, gy, 6.0, 'Гони грузовик на склад Профа в промзоне.', vehicle=truck)
    w.police.clear()
    w.player.leave_vehicle(force=True)
    truck.locked = True
    truck.keep = False
    m.say('Проф: Превосходно. Полицию я беру на себя — у меня там свои люди.')
    yield 2.5


def m_p3(m):
    w = m.w
    c = w.city
    pl = w.player
    yield from m.briefing('prof', [
        'Кстати, о моих людях в полиции. Один из них раскрыт.',
        'Заберите его у участка. На чужой машине его не выпустят —',
        'понадобится патрульная. Потом везите на старый пирс, там ждёт катер.'])
    sx, sy = c.landmarks['police']['road']
    b = m.blip(sx, sy, tex='blip_station')
    m.obj('Раздобудь патрульную машину. Они стоят у участка.')
    yield lambda: pl.vehicle is not None and pl.vehicle.kind == 'police'
    m.unblip(b)
    car = pl.vehicle
    car.keep = True
    m.vehicles.append(car)
    m.watch(car, 'Патрульная машина уничтожена.')
    door = c.landmarks['police']['door']
    px, py = m.ms.free_spot(door[0] - 9.0, door[1])
    mole = m.npc(px, py, -math.pi / 2, cop_look(), hp=150.0)
    m.watch(mole, 'Информатор погиб.')
    yield from m.goto(sx - 9.0, sy, 5.0, 'Подбери информатора у полицейского участка.', vehicle=car)
    yield from m.board(mole, car)
    w.police.locked = 3
    w.police.set_level(3)
    m.say('Информатор: Гони! Они уже всё поняли!')
    pier = c.special['pier']
    tx, ty = (pier['x0'] + pier['x1']) * 0.5, pier['y1'] - 8.0
    yield from m.goto(tx, ty + 14.0, 6.0, 'Вези информатора к старому пирсу на Набережной.',
                      extra=lambda: mole.vehicle is not None and mole.vehicle is pl.vehicle)
    w.police.locked = None
    w.police.clear()
    m.unwatch(mole)
    m.unwatch(car)
    m.unboard(mole, (tx, pier['y0'] + 6.0))
    m.say('Информатор: Передай Профу — я в долгу не останусь.')
    yield 2.5


def m_p4(m):
    w = m.w
    c = w.city
    pl = w.player
    yield from m.briefing('prof', [
        'Пора заканчивать с мелочами. Городской банк. Сегодня.',
        'Мои люди уже внутри. Ваше дело — удержать вход, пока выносят деньги.',
        'Потом увезёте их в порт. Оружие и броня — в багажнике. Удачи, Макс.'])
    pl.give_weapon(W_AK, 300)
    pl.give_weapon(W_GRENADE, 8, select=False)
    pl.select(W_AK)
    pl.ped.armor = 100.0
    pl.ped.health = pl.ped.max_health
    door = c.landmarks['bank']['door']
    yield from m.goto(door[0], door[1], 2.0, 'Езжай к банку и встань у входа.', on_foot=True, color=RED)
    pol = w.police
    pol.locked = 4
    pol.set_level(4)
    w.audio.play('siren', 0.5)
    m.set_timer(90.0, '')
    m.obj('Удерживай вход в банк, пока выносят деньги!')
    pl.damage_taken_k = 0.5                  # бронежилет Профа держит удар лучше обычного

    def tick(dt):
        if math.hypot(pl.pos()[0] - door[0], pl.pos()[1] - door[1]) > 45.0:
            raise MissionFailed('Ты бросил своих у банка.')
    m.ticks.append(tick)
    t = [90.0]

    def hold():
        t[0] -= w.dt
        return t[0] <= 0.0
    yield hold
    m.ticks.remove(tick)
    m.stop_timer()
    rx, ry = c.landmarks['bank']['road']
    van = m.car('van', rx, ry, 0.0, paint=3)
    van.health = van.max_health = 2600.0
    m.watch(van, 'Фургон с деньгами уничтожен.')
    m.say('Проф (по рации): Деньги в фургоне! Увозите их, живо!')
    yield from m.enter(van, 'Прыгай в фургон с деньгами!')
    yx, yy = c.landmarks['port']['yard']
    yield from m.goto(yx, yy, 7.0, 'Гони в порт — там ждёт катер. Оторвись от погони!', vehicle=van)
    pol.locked = None
    pol.clear()
    pl.leave_vehicle(force=True)
    van.locked = True
    van.keep = False
    m.say('Проф: Блестяще. Ваша доля, как договаривались. Город теперь наш.')
    yield 3.0
    m.ms.finale = True


def m_taxi(m):
    """Подработка: таксист."""
    w = m.w
    c = w.city
    pl = w.player
    rn = w.roadnet
    cab = pl.vehicle
    if cab is None:
        raise MissionFailed('Смена не началась: ты вышел из такси.', True)
    fares = 0
    earned = 0
    out_t = [0.0]

    def tick(dt):
        if pl.vehicle is cab:
            out_t[0] = 0.0
        else:
            out_t[0] += dt
            if out_t[0] > 15.0 or cab.dead or cab.removed:
                raise MissionFailed('Смена окончена. Пассажиров: %d, заработано $%d.' % (fares, earned), True)
        if w.game.inp.hit('t'):
            raise MissionFailed('Смена окончена. Пассажиров: %d, заработано $%d.' % (fares, earned), True)
    m.ticks.append(tick)
    m.help('Подработка в такси: вози пассажиров по адресам. T — закончить смену.', 7.0)
    while True:
        m.counter('Пассажиров: %d' % fares)
        x, y = m.ms.place_near(pl.pos(), 90.0, 240.0, seed=random.randrange(1 << 20))
        zone = c.zone_style(c.zone_at(x, y))
        fare = m.npc(x, y, 0.0, random_look(random, zone if zone in 'DOGRIB' and len(zone) == 1 else 'D'))
        fare.keep = True
        b = m.blip(obj=fare, tex='blip_taxi')
        a = m.arrow(fare, GREEN)
        m.obj('Забери пассажира.')
        m.set_timer(25.0 + math.hypot(x - pl.pos()[0], y - pl.pos()[1]) / 7.0, 'Пассажир не дождался.')

        def near():
            if fare.dead or fare.removed:
                raise MissionFailed('Пассажир… больше никуда не едет.', True)
            return (pl.vehicle is cab and math.hypot(fare.x - cab.x, fare.y - cab.y) < 9.0 and
                    abs(cab.speed) < 2.0)
        yield near
        m.stop_timer()
        m.unblip(b)
        m.unarrow(a)
        yield from m.board(fare, cab, 10.0)
        if fare.dead or fare.vehicle is not cab:
            continue
        names = [k for k in c.landmarks.keys()]
        dest = None
        for _ in range(12):
            name = random.choice(names)
            dx, dy = c.landmarks[name]['road']
            d = math.hypot(dx - cab.x, dy - cab.y)
            if 180.0 < d < 520.0:
                dest = (dx, dy, d)
                break
        if dest is None:
            dx, dy = m.ms.place_near(pl.pos(), 200.0, 400.0, seed=random.randrange(1 << 20))
            dest = (dx, dy, math.hypot(dx - cab.x, dy - cab.y))
        dx, dy, dist = dest
        m.set_timer(18.0 + dist / 8.0, 'Пассажир опоздал и ушёл, не заплатив.')
        m.say(random.choice(['Пассажир: Шеф, только побыстрее!', 'Пассажир: Опаздываю, гони!',
                             'Пассажир: Два счётчика, если успеем.', 'Пассажир: Поехали, командир.']))
        yield from m.goto(dx, dy, 6.0, 'Отвези пассажира по адресу.', vehicle=cab,
                          extra=lambda: fare.vehicle is cab)
        tip = int(max(0.0, m.timer) * 3.0)
        m.stop_timer()
        pay = 40 + int(dist * 0.35) + tip
        fares += 1
        earned += pay
        w.stats['taxi'] += 1
        pl.add_money(pay)
        w.audio.play('money', 0.8)
        m.say('Пассажир: Спасибо! Вот $%d.' % pay)
        m.unboard(fare)
        fare.keep = False
        fare.spawned = True
        fare.start_walk()
        if fare in m.peds:
            m.peds.remove(fare)
        if fares % 5 == 0:
            bonus = fares * 100
            pl.add_money(bonus)
            earned += bonus
            w.hud.big('%d пассажиров!' % fares, GOLD, 3.0, 'Премия $%d' % bonus)
        yield 1.5


from . import story as S                                   # noqa: E402

# Сюжет — задания Брюса и босса: они начинаются телефонным звонком (contact=None).
# Остальное — подработка у знакомых: заказчики ждут в своих заведениях и открываются после сюжета.
MISSIONS = [
    dict(id='s1', contact=None, title='Брат за брата', reward=5000, fn=S.m_s1, req=[], story=True, wait=2.0),
    dict(id='s2', contact=None, title='Жёлтый контейнер', reward=10000, fn=S.m_s2, req=['s1'], story=True, wait=28.0),
    dict(id='v1', contact='vano', title='Знакомство', reward=500, fn=m_v1, req=['s2']),
    dict(id='v2', contact='vano', title='Должок', reward=1200, fn=m_v2, req=['v1']),
    dict(id='v3', contact='vano', title='Конкуренты', reward=2000, fn=m_v3, req=['v2']),
    dict(id='v4', contact='vano', title='Круг почёта', reward=3000, fn=m_v4, req=['v3']),
    dict(id='r1', contact='rosa', title='Шумные гости', reward=800, fn=m_r1, req=['v1']),
    dict(id='r2', contact='rosa', title='Курьер', reward=1500, fn=m_r2, req=['r1']),
    dict(id='r3', contact='rosa', title='Разборка', reward=2500, fn=m_r3, req=['r2']),
    dict(id='r4', contact='rosa', title='Инкассация', reward=4000, fn=m_r4, req=['r3']),
    dict(id='z1', contact='zakhar', title='Улов', reward=1500, fn=m_z1, req=['r1']),
    dict(id='z2', contact='zakhar', title='Хрупкий груз', reward=2500, fn=m_z2, req=['z1']),
    dict(id='z3', contact='zakhar', title='Длинный язык', reward=3500, fn=m_z3, req=['z2']),
    dict(id='g1', contact='grom', title='Вещдок', reward=2000, fn=m_g1, req=['z1', 'r2']),
    dict(id='g2', contact='grom', title='День сбора', reward=3000, fn=m_g2, req=['g1']),
    dict(id='g3', contact='grom', title='Облава', reward=5000, fn=m_g3, req=['g2', 'z3']),
    dict(id='p1', contact='prof', title='Свидетель', reward=3000, fn=m_p1, req=['g1']),
    dict(id='p2', contact='prof', title='Груз', reward=4000, fn=m_p2, req=['p1']),
    dict(id='p3', contact='prof', title='Свой человек', reward=5000, fn=m_p3, req=['p2']),
    dict(id='p4', contact='prof', title='Большой куш', reward=50000, fn=m_p4, req=['p3', 'v4', 'r4', 'g3']),
]
TAXI = dict(id='taxi', contact=None, title='Таксист', reward=0, fn=m_taxi, side=True)
STORY = [m for m in MISSIONS if m.get('story')]
JOBS = [m for m in MISSIONS if not m.get('story')]
STORY_TOTAL = len(STORY)
STORY_IDS = frozenset(m['id'] for m in STORY)
JOB_IDS = frozenset(m['id'] for m in JOBS)

# что сообщить игроку, когда открывается задание (ключ — id открывшегося задания)
ANNOUNCE = {
    'v1': 'Пока босс молчит, в городе есть подработка. Начни с гаража Вано в Старом городе (метка «В»).',
    'r1': 'Вано: Будет скучно — загляни к Розе в бар в Ржавом квартале. Скажешь, что от меня. (метка «Р»)',
    'z1': 'Роза: Моему поставщику нужен водитель. Захар, лодочный сарай в Нефтегавани — '
          'за Портовым мостом. (метка «З»)',
    'g1': 'Сообщение с незнакомого номера: «Чайная в Заречье, за Большим мостом. Спросить Грома. '
          'Не тяни». (метка «Г»)',
    'p1': 'Гром: С тобой хочет поговорить серьёзный человек. Башня в Деловом центре. (метка «П»)',
    'g3': 'Гром: Срочно в чайную. Это касается твоего друга-лодочника.',
    'p4': 'Проф готовит большое дело. Загляни в башню.',
}


class Missions(object):

    def __init__(self, world):
        self.w = world
        self.active = None
        self.done = set()
        self.markers = []
        self.arrows = []
        self.pickups = []
        self.packages = set()
        self.hints = set()
        self.contact_mk = {}
        self.contact_blip = {}
        self.static_blips = []
        self.fail_cd = 0.0
        self.finale = False
        self.finale_shown = False
        self.chasers = []
        self.spray_cd = {}
        self.save_mk = None
        self.shop_mks = []
        self.in_save = True
        self.in_shop = False
        self.in_heal = False
        self.heal_mk = None
        self._spray_t = 0.0
        self.letter = None
        self.respawning = False
        self.intro = None
        self.msg_t = 0.0
        self.hint_t = 3.0
        self.bonus_given = 0
        self.ckpt = {}                  # до какого места пройдено сюжетное задание (после провала — оттуда)
        self.noise = []                 # выстрелы этого кадра: (x, y, на сколько метров слышно, кто стрелял)
        self.call_t = 6.0               # через сколько секунд позвонит Брюс со следующим делом
        self.ship_door = S.ShipDoor(world)
        self._build_static()

    # ------------------------------------------------------------------
    def _build_static(self):
        w = self.w
        c = w.city
        hud = w.hud
        lm = c.landmarks
        rooms = w.interiors.rooms
        # сохранение — у кровати в комнате Макса
        sx, sy = lm['safehouse']['door']
        room = rooms.get('safehouse')
        if room is not None:
            bx, by = room.spots['bed'][:2]
            self.save_mk = Marker(w, bx, by, 0.8, BLUE, 1.2)
            sx, sy = room.out
        else:
            self.save_mk = Marker(w, sx + 2.2, sy, 1.0, BLUE, 1.4)
        self.markers.append(self.save_mk)
        self.static_blips.append(hud.add_blip('blip_save', sx, sy, edge=True, scale=1.1))
        if 'garage' in lm['safehouse']:
            gx, gy = lm['safehouse']['garage']
            self.static_blips.append(hud.add_blip('blip_garage', gx, gy - 6.0, edge=False, rng=260.0))
        for name in ('spray', 'spray2'):
            if name in lm:
                x, y = lm[name]['bay']
                self.static_blips.append(hud.add_blip('blip_tune', x, y, edge=False, rng=400.0))
        for name in ('guns', 'guns2'):
            if name in lm:
                x, y = lm[name]['door']
                room = rooms.get(name)
                if room is not None:                 # прилавок внутри магазина
                    mx, my = room.spots['shop'][:2]
                    mk = Marker(w, mx, my, 0.9, GREEN, 1.2)
                    x, y = room.out
                else:
                    mk = Marker(w, x, y, 1.1, GREEN, 1.4)
                self.markers.append(mk)
                self.shop_mks.append(mk)
                self.static_blips.append(hud.add_blip('blip_guns', x, y, edge=False, rng=400.0))
        x, y = lm['hospital']['door']
        self.heal_mk = None
        room = rooms.get('hospital')
        if room is not None:                         # регистратура: перевязка за деньги
            mx, my = room.spots['heal'][:2]
            self.heal_mk = Marker(w, mx, my, 0.9, (0.95, 0.95, 0.95, 1.0), 1.2)
            self.markers.append(self.heal_mk)
            x, y = room.out
        self.static_blips.append(hud.add_blip('blip_hospital', x, y, edge=False, rng=300.0))
        x, y = lm['police']['door']
        self.static_blips.append(hud.add_blip('blip_police', x, y, edge=False, rng=300.0))
        x, y = lm['taxi']['door']
        self.static_blips.append(hud.add_blip('blip_taxi', x, y, edge=False, rng=300.0))
        # предметы на карте
        for i, (x, y, hint) in enumerate(c.pickup_spots):
            res = spot_pickup(i, hint)
            if res is None:
                continue
            kind, wid, amount = res
            pk = Pickup(w, kind, x, y, wid, amount, respawn=240.0)
            self.pickups.append(pk)
        self._spawn_packages()
        self.refresh_contacts()

    def _spawn_packages(self):
        w = self.w
        for i, (x, y) in enumerate(w.city.packages):
            if i in self.packages:
                continue
            pk = Pickup(w, 'package', x, y)
            pk.index = i
            self.pickups.append(pk)

    def add_pickup(self, kind, x, y, wid=None, amount=0, life=None):
        pk = Pickup(self.w, kind, x, y, wid, amount)
        pk.life = life
        self.pickups.append(pk)
        return pk

    def destroy(self):
        """Убрать всё, что создано заданиями (перед новой игрой)."""
        w = self.w
        if self.active is not None:
            try:
                self._finish(False, '', True)
            except Exception:
                self.active = None
        if self.intro is not None:
            self.intro = None
            self._intro_off()
        hud = w.hud
        for mk in self.markers:
            mk.remove()
        for a in self.arrows:
            a.remove()
        for pk in self.pickups:
            pk.remove()
        for b in self.static_blips:
            hud.remove_blip(b)
        for b in self.contact_blip.values():
            if b is not None:
                hud.remove_blip(b)
        for b in list(hud.blips):
            hud.remove_blip(b)
        self.markers = []
        self.arrows = []
        self.pickups = []
        self.chasers = []
        self.contact_mk = {}
        self.contact_blip = {}
        if self.letter is not None:
            self.letter.removeNode()
            self.letter = None
        self.ship_door.remove()
        hud.phone_hide()
        hud.set_task_bar(None)
        w.player.freeze = False
        w.cam.override = None

    # ------------------------------------------------------------------
    def next_mission(self, contact):
        for spec in MISSIONS:
            if spec['contact'] != contact or spec['id'] in self.done:
                continue
            if all(r in self.done for r in spec['req']):
                return spec
            return None
        return None

    def refresh_contacts(self):
        w = self.w
        for name in CONTACTS:
            spec = self.next_mission(name) if self.active is None else None
            mk = self.contact_mk.get(name)
            if spec is None:
                if mk is not None:
                    mk.remove()
                    if mk in self.markers:
                        self.markers.remove(mk)
                    self.contact_mk[name] = None
                b = self.contact_blip.get(name)
                if b is not None:
                    w.hud.remove_blip(b)
                    self.contact_blip[name] = None
            else:
                if name not in w.city.landmarks:
                    continue
                x, y = w.city.landmarks[name]['door']
                room = w.interiors.rooms.get(name)
                if mk is None:
                    if room is not None:             # розовая метка — внутри, рядом с хозяином
                        mx, my = room.spots['talk'][:2]
                        mk = Marker(w, mx, my, 0.85, PINK, 1.2)
                    else:
                        mk = Marker(w, x, y, 1.3, PINK, 1.7)
                    self.markers.append(mk)
                    self.contact_mk[name] = mk
                if self.contact_blip.get(name) is None:
                    if room is not None:
                        x, y = room.out
                    self.contact_blip[name] = w.hud.add_blip(CONTACTS[name]['blip'], x, y, edge=True, scale=1.25)

    def progress(self):
        """Сюжет: (пройдено, всего)."""
        return len(self.done & STORY_IDS), STORY_TOTAL

    def jobs_progress(self):
        """Подработка у заказчиков: (пройдено, всего)."""
        return len(self.done & JOB_IDS), len(JOBS)

    def next_story(self):
        """Следующее сюжетное задание (его начинает звонок) или None."""
        for spec in STORY:
            if spec['id'] not in self.done:
                return spec if all(r in self.done for r in spec['req']) else None
        return None

    def _story_call(self, dt):
        """Брюс звонит со следующим делом, когда герою не до чего другого."""
        spec = self.next_story()
        if spec is None:
            return
        w = self.w
        pl = w.player
        if pl.state not in ('foot', 'car') or pl.freeze or not pl.controls or w.police.level > 0 or \
                w.interiors.trans is not None or self.fail_cd > 0.0 or w.game.state != 'play':
            return
        self.call_t -= dt
        if self.call_t <= 0.0:
            self.start(spec)

    # ------------------------------------------------------------------
    # вспомогательное для сценариев
    # ------------------------------------------------------------------
    def clear_area(self, x, y, r=6.0, peds=False, keep=None):
        w = self.w
        for v in list(w.vehicles):
            if v.keep or v.is_player or v.removed or v.mission is not None:
                continue
            if (v.x - x) ** 2 + (v.y - y) ** 2 < (r + v.spec.L * 0.5) ** 2:
                w.remove_vehicle(v)
        if peds:
            for p in list(w.peds):
                if p.is_player or p.keep or p is keep or p.removed:
                    continue
                if (p.x - x) ** 2 + (p.y - y) ** 2 < r * r:
                    w.remove_ped(p)

    def free_spot(self, x, y, tries=14):
        st = self.w.static
        if not st.overlap_circle(x, y, 0.45, F_PED):
            return x, y
        r = random.Random(int(x * 13 + y * 7))
        for i in range(tries):
            d = 1.0 + i * 0.6
            a = r.uniform(0, 6.283)
            nx, ny = x + math.cos(a) * d, y + math.sin(a) * d
            if not st.overlap_circle(nx, ny, 0.45, F_PED) and self.w.city.ground_z(nx, ny) > -0.3:
                return nx, ny
        return x, y

    def place_near(self, pos, dmin, dmax, seed=0, zone=None):
        """Точка на тротуаре на расстоянии dmin..dmax от pos."""
        rn = self.w.roadnet
        r = random.Random(seed)
        nodes = [n for n in rn.ped_nodes
                 if dmin * dmin <= (n.x - pos[0]) ** 2 + (n.y - pos[1]) ** 2 <= dmax * dmax and n.block >= 0]
        if zone is not None:
            zn = [n for n in nodes if self.w.city.zone_at(n.x, n.y) == zone]
            if zn:
                nodes = zn
        if not nodes:
            n = rn.nearest_ped_node(pos[0] + dmin, pos[1], 400.0)
            return (n.x, n.y) if n is not None else (pos[0] + dmin, pos[1])
        n = nodes[int(r.random() * len(nodes))]
        return n.x, n.y

    def roadside(self, x, y, off=4.8, side=1):
        """Ближайшая точка дороги и место у её обочины: ((x, y) на полосе, (x, y) рядом, yaw полосы)."""
        lane, s, d = self.w.roadnet.nearest_lane(x, y, 90.0)
        if lane is None:
            return (x, y), (x, y), 0.0
        px, py, yaw = lane.pos(s)
        sx, sy = px + math.sin(yaw) * off * side, py - math.cos(yaw) * off * side
        return (px, py), self.free_spot(sx, sy), yaw

    def launch(self, v, persona=1.2, rush=True):
        """Стоящая у обочины машина трогается и дальше едет сама по полосам (как трафик).

        rush: водитель удирает — не ждёт на светофорах и резче разгоняется."""
        lane, s, d = self.w.roadnet.nearest_lane(v.x, v.y, 40.0)
        if lane is None:
            return False
        v.npc = True
        v.locked = True
        v.mode = Vehicle.RAIL
        v.link = lane
        v.s = s
        v.persona = persona
        v.rush = rush
        v.speed = 0.0
        v.target_speed = lane.speed * 0.6
        return True

    def letterbox(self, on):
        from panda3d.core import CardMaker
        if self.letter is None:
            root = self.w.base.aspect2d.attachNewNode('letterbox', sort=6)
            for (z0, z1) in ((0.8, 1.5), (-1.5, -0.8)):
                cm = CardMaker('bar')
                cm.setFrame(-5, 5, z0, z1)
                n = root.attachNewNode(cm.generate())
                n.setColor(0, 0, 0, 1)
            self.letter = root
        if on:
            self.letter.show()
        else:
            self.letter.hide()

    def start_chasers(self, m, kinds, gang, count, interval):
        """Бандиты на машинах, преследующие игрока (для задания)."""
        ch = dict(active=True, units=[], t=4.0, kinds=kinds, gang=gang, count=count, interval=interval, m=m)
        self.chasers.append(ch)
        return ch

    def _update_chasers(self, dt):
        w = self.w
        pl = w.player
        px, py = pl.pos()
        for ch in list(self.chasers):
            if not ch['active'] or self.active is not ch['m']:
                for v in ch['units']:
                    if not v.removed:
                        v.keep = False
                        v.ai = None
                        v.npc = False
                        v.in_throttle = 0.0
                        v.in_brake = 1.0
                self.chasers.remove(ch)
                continue
            ch['units'] = [v for v in ch['units'] if not v.removed and not v.dead]
            ch['t'] -= dt
            if ch['t'] <= 0.0 and len(ch['units']) < ch['count']:
                ch['t'] = ch['interval']
                v = w.police._spawn_unit(px, py)
                if v is not None:
                    # полиция создала машину погони — перекрашиваем её под бандитов
                    w.police.units.remove(v)
                    kind = random.choice(ch['kinds'])
                    x, y, yaw, lane, s = v.x, v.y, v.yaw, v.link, v.s
                    w.remove_vehicle(v)
                    g = w.spawn_vehicle(kind, x, y, yaw, paint=0)
                    g.link, g.s = lane, s
                    g.mode = Vehicle.PHYS
                    w.police._make_unit(g)
                    w.police.units.remove(g)
                    g.siren = False
                    g.owner = 'gang'
                    g.crew = 2
                    g.vx, g.vy = math.cos(yaw) * 10.0, math.sin(yaw) * 10.0
                    ch['units'].append(g)
            slow = pl.speed() < 4.0
            for v in ch['units']:
                if v.crew <= 0 or v.is_player:
                    continue
                d2 = (v.x - px) ** 2 + (v.y - py) ** 2
                if d2 > 200.0 ** 2:
                    v.keep = False
                    w.remove_vehicle(v)
                    continue
                if slow and d2 < 16.0 ** 2 and abs(v.speed) < 4.0:
                    n = v.crew
                    v.crew = 0
                    v.npc = False
                    v.ai = None
                    v.in_throttle = 0.0
                    v.in_brake = 1.0
                    v.keep = False
                    for i in range(n):
                        x, y = v.door_pos(-1 if i % 2 == 0 else 1)
                        e = ch['m'].enemy(x, y, v.yaw, gang_look(ch['gang']), W_PISTOL if i else W_UZI, 90.0, 0.3,
                                          60.0, gang=ch['gang'])
                        e.keep = False
                        e.attack(pl.ped)

    # ------------------------------------------------------------------
    def start(self, spec):
        if self.active is not None:
            return False
        w = self.w
        self.active = Run(self, spec)
        self.refresh_contacts()
        w.traffic.density = 1.0
        return True

    def _finish(self, passed, reason='', quiet=False):
        w = self.w
        m = self.active
        if m is None:
            return
        self.active = None
        pl = w.player
        hud = w.hud
        hud.set_timer(None)
        hud.set_counter(None)
        w.cam.override = None
        pl.freeze = False
        pl.damage_taken_k = 1.0
        hud.show(True)
        self.letterbox(False)
        w.police.locked = None
        for b in list(m.blips):
            hud.remove_blip(b)
        for mk in list(m.markers):
            mk.remove()
            if mk in self.markers:
                self.markers.remove(mk)
        for a in list(m.arrows):
            a.remove()
            if a in self.arrows:
                self.arrows.remove(a)
        for pk in m.pickups:
            pk.remove()
        for v in m.vehicles:
            if v.removed:
                continue
            v.keep = False
            v.mission = None
            if v.npc and v.mode == Vehicle.RAIL:
                v.traffic = True
        for p in m.peds:
            if p.removed:
                continue
            p.keep = False
            p.mission = None
            if p.dead:
                continue
            if p.vehicle is not None:
                w.take_out(p, 1)
            if p.kind == 'enemy':
                p.spawned = True
            else:
                p.kind = 'civ'
                p.spawned = True
                p.start_walk()
        hud.phone_hide()
        hud.set_task_bar(None)
        pl.ped.stop_act()
        if passed:
            self.done.add(m.spec['id'])
            self.ckpt.pop(m.spec['id'], None)
            if m.reward:
                pl.add_money(m.reward)
            w.audio.play('passed', 0.9)
            hud.big('Задание выполнено', GOLD, 5.0, ('+' + ui_money(m.reward)) if m.reward else '')
            self._announce(m.spec['id'])
            self.sync_story()
            self.save_game(auto=True)
            nxt = self.next_story()
            if nxt is not None:
                self.call_t = nxt.get('wait', 25.0)
        else:
            if m.side or quiet:
                hud.big(m.spec['title'], BLUEC, 4.0, reason)
            else:
                w.audio.play('failed', 0.8)
                hud.big('Задание провалено', REDC, 4.5, reason)
            self.fail_cd = 5.0
            if m.spec.get('story'):
                self.call_t = 14.0                  # Брюс перезвонит
                self.sync_story()
        hud.clear_subtitles()
        self.refresh_contacts()

    def sync_story(self):
        """Привести мир в соответствие с пройденным сюжетом (после задания и после загрузки)."""
        # жёлтый контейнер на сухогрузе: после дела стоит открытый и пустой
        self.ship_door.set_open('s2' in self.done, instant=True)
        if 'g3' in self.done:
            # Захара вывезли из города: в лодочном сарае его больше нет
            p = self.w.interiors.resident('zakhar')
            if p is not None:
                p.keep = False
                self.w.remove_ped(p)

    def _announce(self, mid):
        """После задания подсказываем, куда идти дальше: кто открылся или у кого ещё остались дела."""
        w = self.w
        text = None
        for spec in MISSIONS:
            if mid in spec['req'] and spec['id'] not in self.done and spec['id'] in ANNOUNCE and \
                    all(r in self.done for r in spec['req']):
                text = ANNOUNCE[spec['id']]
                break
        if text is None and mid in JOB_IDS and len(self.done & JOB_IDS) < len(JOBS):
            me = next((sp['contact'] for sp in MISSIONS if sp['id'] == mid), None)
            if me is not None and self.next_mission(me) is None:
                # у этого заказчика пока пусто — напомнить, кто ещё ждёт
                rest = [CONTACTS[n]['title'] for n in CONTACTS if n != me and self.next_mission(n) is not None]
                if rest:
                    text = 'Здесь пока всё. Работа есть у других: %s.' % ', '.join(rest)
        if text:
            w.hud.help(text, 10.0)
            w.audio.play('pager', 0.7)

    def notify(self, event, obj=None, arg=None):
        if event == 'gunfire':
            self.noise.append(obj)

    def on_ped_died(self, ped, killer, by_player):
        # выпавшие деньги и оружие
        if ped.money > 0 and ped.kind not in ('cop', 'swat', 'fbi', 'army'):
            pk = self.add_pickup('money', ped.x + random.uniform(-0.6, 0.6), ped.y + random.uniform(-0.6, 0.6),
                                 amount=ped.money, life=50.0)
        if ped.weapon.id not in (W_FIST,) and ped.vehicle is None:
            wp = ped.weapon
            am = 1 if wp.kind == 'melee' else max(6, wp.pack // 3)
            self.add_pickup('weapon', ped.x + random.uniform(-0.7, 0.7), ped.y + random.uniform(-0.7, 0.7), wp.id,
                            am, life=60.0)
        if self.active is not None and by_player and ped.mission is self.active:
            self.active.kills += 1

    # ------------------------------------------------------------------
    def update(self, dt):
        w = self.w
        pl = w.player
        hud = w.hud
        px, py = pl.pos()
        on_foot = pl.vehicle is None and pl.state == 'foot'
        for mk in self.markers:
            mk.update(dt)
        for a in self.arrows:
            a.update(dt)
        # предметы
        dirty = False
        for pk in self.pickups:
            if pk.removed:
                dirty = True
                continue
            if pk.update(dt, px, py, on_foot):
                self._take(pk)
        if dirty:
            self.pickups = [p for p in self.pickups if not p.removed]
        if self.respawning:
            return
        if self.fail_cd > 0.0:
            self.fail_cd -= dt
        # активное задание
        m = self.active
        if m is not None:
            try:
                self._step(m, dt)
            except MissionFailed as e:
                self._finish(False, e.reason, e.quiet)
            except StopIteration:
                self._finish(True)
            except Exception:
                # ошибка в сценарии не должна ронять игру: задание просто срывается
                w.game.report_error()
                self._finish(False, 'Задание сорвалось.')
        else:
            if self.intro is not None:
                self._step_intro(dt)
            elif on_foot and self.fail_cd <= 0.0:
                for name, mk in self.contact_mk.items():
                    if mk is not None and mk.player_inside(True) and w.police.level == 0:
                        spec = self.next_mission(name)
                        if spec is not None:
                            self.start(spec)
                            break
                    elif mk is not None and mk.player_inside(True) and self.msg_t <= 0.0:
                        self.msg_t = 4.0
                        hud.help('Сначала избавься от полиции.', 3.0)
            if self.active is None and self.intro is None:
                self._story_call(dt)
            # такси
            v = pl.vehicle
            if v is not None and v.kind == 'taxi' and self.active is None and self.intro is None:
                if 'taxi' not in self.hints:
                    self.hints.add('taxi')
                    hud.help('Ты в такси. Нажми T, чтобы подработать таксистом.', 7.0)
                if w.game.inp.hit('t'):
                    self.start(TAXI)
        if self.msg_t > 0.0:
            self.msg_t -= dt
        del self.noise[:]                           # выстрелы этого кадра задание уже услышало
        self.ship_door.update(dt)
        self._update_chasers(dt)
        self._services(dt, px, py, on_foot)
        self._hints(dt)
        if self.finale and not self.finale_shown and self.active is None:
            self.finale_shown = True
            w.game.show_credits()

    def _step(self, m, dt):
        w = self.w
        pl = w.player
        if pl.state in ('dead', 'busted'):
            raise MissionFailed('' if m.side else ('Ты погиб.' if pl.state == 'dead' else 'Тебя арестовали.'),
                                m.side)
        for (o, reason) in m.watch_list:
            if getattr(o, 'dead', False) or getattr(o, 'removed', False):
                raise MissionFailed(reason)
        for f in list(m.ticks):
            f(dt)
        if m.timer is not None:
            m.timer -= dt
            t = max(0.0, m.timer)
            w.hud.set_timer('%d:%02d' % (int(t) // 60, int(t) % 60))
            if m.timer <= 0.0 and m.timer_fail:
                raise MissionFailed(m.timer_fail)
        for _ in range(8):
            wt = m.wait
            if wt is None:
                ready = True
            elif isinstance(wt, (int, float)):
                m.wait = wt - dt
                ready = m.wait <= 0.0
            else:
                ready = bool(wt())
            if not ready:
                return
            m.wait = next(m.gen)
            dt = 0.0

    # ------------------------------------------------------------------
    def _take(self, pk):
        w = self.w
        pl = w.player
        p = pl.ped
        hud = w.hud
        k = pk.kind
        if k == 'weapon':
            wd = WEAPONS[pk.wid]
            pl.give_weapon(pk.wid, pk.amount if wd.kind != 'melee' else None)
            hud.help('%s%s' % (wd.name, '' if wd.kind == 'melee' else ' (+%d)' % pk.amount), 2.5)
            w.audio.play('pickup', 0.8)
            if 'weapon' not in self.hints:
                self.hints.add('weapon')
                hud.help('ЛКМ — огонь, ПКМ — прицел. Колесо мыши или Q/E — смена оружия.', 8.0)
        elif k == 'health':
            if p.health >= p.max_health:
                return
            p.health = p.max_health
            w.audio.play('pickup', 0.8)
        elif k == 'armor':
            if p.armor >= 100.0:
                return
            p.armor = 100.0
            w.audio.play('pickup', 0.8)
        elif k == 'bribe':
            if w.police.level <= 0:
                return
            w.police.set_level(w.police.level - 1)
            hud.help('Взятка: розыск снижен.', 3.0)
            w.audio.play('money', 0.8)
        elif k == 'money':
            pl.add_money(pk.amount)
            w.audio.play('money', 0.5)
        elif k == 'package':
            self.packages.add(pk.index)
            n = len(self.packages)
            total = len(w.city.packages)
            pl.add_money(500)
            w.audio.play('money', 0.9)
            hud.big('Тайник %d из %d' % (n, total), GOLD, 3.0, '+$500')
            self._package_bonus(n, total)
        elif k in ('item', 'crate'):
            w.audio.play('pickup', 0.9)
        cb = pk.on_take
        pk.taken()
        if cb is not None:
            cb(pk)

    def _package_bonus(self, n, total):
        w = self.w
        step = max(1, total // 3)
        tier = min(3, n // step)
        if n == total:
            tier = 3
        if tier > self.bonus_given:
            self._safehouse_bonus(range(self.bonus_given + 1, tier + 1))
            self.bonus_given = tier
            w.hud.help('Награда за тайники ждёт у твоего убежища.', 7.0)
        if n == total:
            w.player.add_money(25000)
            w.hud.big('Все тайники найдены!', GOLD, 5.0, '+$25000')

    def _safehouse_bonus(self, tiers):
        w = self.w
        sx, sy = w.city.landmarks['safehouse']['door']
        for tier in tiers:
            if tier == 1:
                self.pickups.append(Pickup(w, 'weapon', sx - 2.5, sy, W_UZI, 90, respawn=300.0))
            elif tier == 2:
                self.pickups.append(Pickup(w, 'weapon', sx - 4.0, sy, W_SHOTGUN, 16, respawn=300.0))
            elif tier == 3:
                self.pickups.append(Pickup(w, 'weapon', sx - 7.0, sy, W_AK, 90, respawn=300.0))
                self.pickups.append(Pickup(w, 'weapon', sx - 8.5, sy, W_ROCKET, 5, respawn=300.0))

    # ------------------------------------------------------------------
    def _services(self, dt, px, py, on_foot):
        """Покрасочные, оружейные магазины, сохранение."""
        w = self.w
        pl = w.player
        hud = w.hud
        c = w.city
        v = pl.vehicle
        # покрасочная
        for name in ('spray', 'spray2'):
            lm = c.landmarks.get(name)
            if lm is None:
                continue
            x0, y0, x1, y1 = lm['bay_rect']
            inside = v is not None and x0 <= px <= x1 and y0 <= py <= y1
            if not inside:
                self.spray_cd[name] = False
                continue
            if self.spray_cd.get(name) or abs(v.speed) > 1.2:
                continue
            self.spray_cd[name] = True
            if v.kind in ('police', 'enforcer', 'fbi', 'army', 'ambulance', 'bus', 'copbike', 'firetruck'):
                hud.help('С такой машиной здесь не работают.', 4.0)
                continue
            if 'tune' not in self.hints:
                self.hints.add('tune')
            w.game.open_tuning(v, name)             # меню ателье: покраска, ремонт, тюнинг
        if self._spray_t > 0.0:
            self._spray_t -= dt
            if self._spray_t <= 0.0:
                hud.fade(0.0, 2.0)
        inside = on_foot and not pl.freeze and self.save_mk.player_inside(True)
        if inside and not self.in_save:
            if self.active is not None:
                hud.help('Во время задания сохраняться нельзя.', 3.0)
            elif w.police.level > 0:
                hud.help('Сначала избавься от полиции.', 3.0)
            else:
                w.game.open_save()               # спросить подтверждение
        self.in_save = inside
        # оружейный магазин
        inside = False
        if on_foot and not pl.freeze:
            for mk in self.shop_mks:
                if mk.player_inside(True):
                    inside = True
                    break
        if inside and not self.in_shop and w.police.level == 0:
            w.game.open_shop()
        self.in_shop = inside
        # больница: перевязка
        if self.heal_mk is not None:
            inside = on_foot and not pl.freeze and self.heal_mk.player_inside(True)
            if inside and not self.in_heal:
                p = pl.ped
                cost = 100
                if p.health >= p.max_health - 1.0:
                    hud.subtitle('Медсестра: Вы здоровы. Не занимайте очередь.', 3.0, clear=True)
                elif pl.money < cost:
                    hud.subtitle('Медсестра: Перевязка — $%d. Касса там же, где и совесть.' % cost, 3.5, clear=True)
                else:
                    pl.add_money(-cost)
                    p.health = p.max_health
                    hud.fade(1.0, 6.0)
                    self._spray_t = 0.5
                    w.audio.play('pickup', 0.8)
                    hud.help('Тебя осмотрели и перевязали: -$%d. Здоровье восстановлено.' % cost, 5.0)
            self.in_heal = inside

    def sleep_and_save(self):
        """Сохранение в убежище: проходит шесть часов, здоровье восстанавливается."""
        w = self.w
        hud = w.hud
        w.sky.advance(6.0)
        p = w.player.ped
        p.health = p.max_health
        ok = self.save_game()
        hud.fade(1.0, 5.0, instant=True)
        hud.fade(0.0, 0.8)
        hud.big('Игра сохранена' if ok else 'Не удалось сохранить', BLUEC, 3.0, w.sky.clock_text())
        w.audio.play('pickup', 0.8)
        return ok

    def _hints(self, dt):
        w = self.w
        pl = w.player
        hud = w.hud
        self.hint_t -= dt
        if self.hint_t > 0.0 or self.intro is not None:
            return
        self.hint_t = 1.0
        h = self.hints
        if pl.vehicle is not None and 'car' not in h:
            h.add('car')
            hud.help('W/S — газ и тормоз, A/D — руль, пробел — ручник. R — радио, H — сигнал, F — выйти.', 9.0)
        elif w.police.level > 0 and 'wanted' not in h:
            h.add('wanted')
            hud.help('Тебя ищет полиция! Скройся из виду, найди взятку-звезду или перекрась машину.', 9.0)
        elif 'start' not in h and pl.state == 'foot' and (self.active is None or not w.hud.sub_plain):
            h.add('start')
            self.hint_t = 11.0
            if pl.indoors:
                hud.help('Это твой дом: у кровати можно сохранить игру. WASD — движение, мышь — обзор. '
                         'Выход — дверь с жёлтой стрелкой.', 10.0)
            else:
                hud.help('WASD — движение, мышь — обзор, Shift — бег, пробел — прыжок, F — сесть в машину.', 10.0)

    # ------------------------------------------------------------------
    def start_intro(self):
        """Пролог — играбельное воспоминание: ограбление ювелирного в Гангоне (см. _intro_script).

        WASD — движение, Shift — бег, F — сесть на мотоцикл; Enter, пробел — следующие реплики;
        Esc — пропустить пролог целиком."""
        w = self.w
        pl = w.player
        it = dict(t=0.0, wait=0.0, tick=None, hint=None, stage='store')
        it['gen'] = self._intro_script(it)
        self.intro = it
        w.hud.fade(1.0, instant=True)
        w.hud.show(False)
        w.hud.mission_title('')
        pl.freeze = True
        pl.invincible = True
        pl.god = True                            # в воспоминании Макс не умирает и его не арестуют
        self.letterbox(True)
        w.traffic.enabled = False              # улицы пустые: воспоминанию не мешает случайный транспорт
        w.crowd.enabled = False
        w.sky.time_scale = 0.0
        w.interiors.cinema = True
        pl.give_weapon(W_PISTOL, 36, select=True)      # у Макса был пистолет
        for mk in self.markers:
            mk.show(False)
        # подсказка на нижней чёрной полосе
        from direct.gui.OnscreenText import OnscreenText
        from panda3d.core import TextNode
        it['hint'] = OnscreenText(text='WASD — движение      F — в транспорт      Esc — пропустить пролог',
                                  parent=self.letter, pos=(0, -0.915),
                                  scale=0.042, fg=(0.62, 0.62, 0.62, 1.0), font=w.hud.f_txt, align=TextNode.ACenter)

    def _intro_script(self, it):
        """Новый пролог — играбельное воспоминание: ограбление ювелирного в Гангоне.

        Гангон, полночь.  Макс и Лёха бьют витрину ювелирного «АВАНГАРД», хватают сумку и уходят от погони
        на мотоцикле.  На заброшенном тупике у шоссе Лёха предаёт напарника — стреляет в Макса и уезжает.
        Избитый, Макс доползает до своего мотоцикла, едет к товарному поезду и уходит в Порт-Глухов — так
        он и оказывается в этом городе.  Enter, пробел или щелчок мыши листают реплики, Esc — пропустить.
        """
        w = self.w
        c = w.city
        pl = w.player
        p = pl.ped
        hud = w.hud
        sky = w.sky
        cam = w.cam
        rn = w.roadnet
        boss = c.landmarks['boss']
        fx, fy = boss['door'][0] - 12.0, boss['rect'][1] - 0.18       # фасад смотрит на юг, на улицу
        yard = (560.0, 795.0)                                            # заброшенный тупик у шоссе
        track_y = 807.5                                                  # рельсы вдоль шоссе
        it['props'] = []

        def _add(obj, cleanup):
            it['props'].append((obj, cleanup))
            return obj

        def say(text, extra=0.0):
            dur = 1.6 + len(text) * 0.055 + extra
            hud.subtitle(text, dur + 0.6, clear=True)
            return dur

        def wait_enter(t_min, dur):
            t = [0.0]
            inp = w.game.inp

            def cond():
                t[0] += w.dt
                if t[0] > t_min and (inp.hit('enter') or inp.hit('space') or inp.hit('mouse1')):
                    return True
                return t[0] > dur
            return cond

        def dist(x, y):
            px, py = pl.pos()
            return math.hypot(px - x, py - y)

        def marker(x, y, r, color=YELLOW):
            mk = Marker(w, x, y, r, color, 1.9)
            _add(mk, mk.remove)
            it.setdefault('anim', []).append(mk)
            return mk

        def arrow(obj):
            a = Arrow(w, obj, z=2.6, color=YELLOW)
            it.setdefault('anim', []).append(a)
            return a

        # --- декорации: фасад «Авангарда», Лёха, мотоцикл, добыча
        facade = _jewel_facade(w, fx, fy)
        _add(facade, facade.removeNode)
        loot = _duffel(w, fx + 0.7, fy - 1.35)
        loot.hide()
        _add(loot, loot.removeNode)
        leo = w.spawn_ped(fx + 2.3, fy - 2.4, -math.pi / 2, gang_look('mafia'), kind='civ')
        leo.keep = True
        _add(leo, lambda: w.remove_ped(leo))
        bike = w.spawn_vehicle('chopper', fx - 3.4, fy - 3.4, math.pi / 2, 0)
        bike.keep = True
        bike.locked = False
        _add(bike, lambda: w.remove_vehicle(bike))
        it['leo'], it['bike'], it['loot'] = leo, bike, loot
        it['anim'] = it.get('anim', [])

        def tick(dt):
            for o in it['anim']:
                o.update(dt)
            leo_ = it.get('leo')
            if leo_ is not None and not leo_.dead and not leo_.removed:
                v = pl.vehicle
                if v is it['bike'] and leo_.vehicle is None:
                    # Лёха должен ехать сзади: догнать байк «за кадром» и сесть
                    if math.hypot(leo_.x - v.x, leo_.y - v.y) > 2.0:
                        leo_.x = v.x - math.cos(v.yaw) * 1.15
                        leo_.y = v.y - math.sin(v.yaw) * 1.15
                        leo_.z = c.ground_z(leo_.x, leo_.y)
                        leo_.sync()
                    leo_.set_state('stand')
                    w.put_in_vehicle(leo_, v)
            tr = it.get('train')
            if tr is not None:
                node = tr['root']
                if tr['phase'] == 'approach':
                    tr['x'] -= 17.0 * dt
                    if tr['x'] <= tr['stop_x'] + 60.0:
                        tr['phase'] = 'brake'
                    w.scene_engine = ('engine_truck', 0.75, 0.55)
                elif tr['phase'] == 'brake':
                    tr['v'] = max(0.0, tr['v'] - 2.0 * dt)
                    tr['x'] -= tr['v'] * dt
                    if tr['v'] <= 0.0:
                        tr['v'] = 0.0
                        tr['phase'] = 'done'
                        w.scene_engine = None
                elif tr['phase'] == 'leave':
                    tr['v'] = min(17.0, tr['v'] + 1.6 * dt)
                    tr['x'] -= tr['v'] * dt
                node.setX(tr['x'])
        it['tick'] = tick

        sky.set_weather('rain')
        sky.set_time(23.55)
        sky.time_scale = 0.0
        w.crowd.enabled = False
        # Макс и Лёха стоят у витрины, лица к магазину
        pl.teleport(fx + 0.6, fy - 2.4, math.pi / 2)

        # --- 1. Гангон, полночь (кино)
        cam.override = (fx + 7.6, fy - 9.2, 2.35, fx, fy + 0.4, 1.35)
        hud.fade(0.0, 1.7)
        hud.big('ГАНГОН', GOLD, 5.0, u'Ювелирный магазин «Авангард». Полночь.')
        yield 2.1
        say('Лёха: Тихо. Витрину — и сразу к кассе.')
        yield wait_enter(0.7, 3.4)
        say('Макс: Без геройства. Сумку — и к мотоциклу.')
        yield wait_enter(0.7, 3.2)
        say('Лёха: Конечно. Я же в школе отличник был.')
        yield wait_enter(0.7, 3.0)

        # --- 2. играбельно: выбить витрину и схватить сумку
        cam.override = None
        self.letterbox(False)
        hud.show(True)
        pl.freeze = False
        hud.help('Выбей витрину ювелирного — подойди вплотную!', 8.0)
        mk = marker(fx + 0.7, fy - 0.7, 1.7, RED)
        yield lambda: dist(fx + 0.7, fy - 1.1) < 1.5
        mk.remove()
        it['anim'].remove(mk)
        w.audio.play('glass', 0.95)
        w.fx.sparks(fx + 0.7, fy - 0.3, 1.6, n=16, nx=0.0, ny=-1.0, nz=0.7, color=(0.82, 0.9, 1.0))
        w.fx.debris(fx + 0.7, fy - 0.3, 1.5, n=7, color=(0.75, 0.85, 0.9), power=3.5, size=0.22)
        w.fx.add_shake(0.35)
        loot.show()
        hud.help('Сумка! Хватай!', 6.0)
        yield lambda: dist(fx + 0.7, fy - 1.35) < 1.4
        loot.hide()
        w.audio.play('money', 0.7)
        # сработала сигнализация — едут полицейские
        w.police.set_level(3)
        say('Лёха: Сработала сигнализация! Копы! К байку!')
        yield 1.5

        # --- 3. играбельно: удрать от погони на север, через мост
        hud.help('Уезжай от погони!', 9.0)
        arr = arrow(bike)
        yield lambda: pl.vehicle is bike
        arr.remove()
        if arr in it['anim']:
            it['anim'].remove(arr)
        mk = marker(70.0, 600.0, 10.0, YELLOW)
        blip = hud.add_blip('blip_dest', 70.0, 600.0)
        hud.help('Через мост на север — и вдоль трассы на северо-восток!', 9.0)
        yield lambda: pl.vehicle is bike and dist(70.0, 600.0) < 32.0
        hud.remove_blip(blip)
        mk.remove()
        it['anim'].remove(mk)
        w.police.clear()
        hud.help('Погоня отстала. Дыши.', 4.0)
        yield 1.6

        # --- 4. заброшенный тупик: «разделим добычу»
        mk = marker(yard[0], yard[1], 7.0, YELLOW)
        hud.help('Сворачивай в заброшенный тупик у трассы — разделим добычу.', 8.0)
        yield lambda: pl.vehicle is bike and dist(yard[0], yard[1]) < 8.0
        mk.remove()
        it['anim'].remove(mk)

        # --- 5. предательство (кино)
        it['stage'] = 'betrayal'
        pl.freeze = True
        pl.leave_vehicle(force=True)
        bike.x, bike.y = yard[0] + 4.6, yard[1] + 1.8
        bike.yaw = -0.8
        bike.z = c.ground_z(bike.x, bike.y)
        bike.speed = 0.0
        bike.sync()
        w.take_out(leo, 1)
        self.letterbox(True)
        hud.show(False)
        cam.override = (yard[0] + 5.4, yard[1] - 3.6, 2.35, yard[0], yard[1], 1.15)
        say('Лёха: Тихо. Встань.')
        yield wait_enter(0.7, 3.4)
        say('Макс: Лёха… что ты делаешь?')
        yield wait_enter(0.7, 2.8)
        say('Лёха: Добыча на двоих… Сам понимаешь. Деньги мне нужнее.')
        yield wait_enter(0.7, 3.6)
        # выстрел
        w.audio.play_at('pistol', leo.x, leo.y, 1.0)
        w.fx.muzzle(leo.x, leo.y, 1.32, 0.7)
        w.fx.tracer(leo.x, leo.y, 1.32, p.x, p.y, 1.05, (1.0, 0.86, 0.5), 0.06, 0.1)
        w.fx.blood(p.x, p.y, 1.0, n=7)
        pl.ped.health = 34.0
        p.knock_down(9999.0, 0.9, -0.4, 0.0)
        hud.damage_flash(72)
        w.fx.add_shake(0.6)
        yield 1.2
        say('Макс: А… а-а…')
        yield wait_enter(0.9, 2.4)
        say('Лёха: Доползи до байка. А деньги мне нужнее — у меня семья.')
        yield wait_enter(0.7, 4.0)
        # Лёха садится на «Призрак» и уезжает
        sedan = w.spawn_vehicle('phantom', yard[0] + 7.6, yard[1] + 2.3, -0.35, 0)
        sedan.keep = True
        sedan.locked = False
        _add(sedan, lambda: w.remove_vehicle(sedan))
        leo.x, leo.y = yard[0] + 5.6, yard[1] + 1.2
        leo.z = c.ground_z(leo.x, leo.y)
        leo.set_state('stand')
        leo.sync()
        w.put_in_vehicle(leo, sedan, driver=True)
        it['sedan'] = sedan

        def sedan_tick(dt):
            if sedan.removed:
                return
            sedan.x += 8.0 * dt
            sedan.speed = 8.0
            sedan.z = c.ground_z(sedan.x, sedan.y)
            sedan.sync()
            if math.hypot(sedan.x - yard[0], sedan.y - yard[1]) > 110.0:
                w.remove_vehicle(sedan)
        it['base_tick'] = it['tick']

        def tick2(dt):
            it['base_tick'](dt)
            sedan_tick(dt)
        it['tick'] = tick2
        self.letterbox(False)
        hud.show(True)
        cam.override = None

        # --- 6. играбельно: доползти до своего мотоцикла
        pl.crawl = True
        pl.freeze = False
        hud.help('Доползи до своего мотоцикла!', 10.0)
        mk = marker(bike.x, bike.y, 1.7, YELLOW)
        yield lambda: dist(bike.x, bike.y) < 1.8
        pl.crawl = False
        p.timer = 0.01                       # встанет сам
        mk.remove()
        it['anim'].remove(mk)

        # --- 7. к поезду
        mk = marker(yard[0], track_y, 4.6, YELLOW)
        hud.help('Садись и езжай к поезду!', 9.0)
        yield lambda: pl.state == 'car'
        yield lambda: dist(yard[0], track_y) < 6.0
        mk.remove()
        it['anim'].remove(mk)

        # --- 8. товарный поезд (кино)
        it['stage'] = 'train'
        pl.freeze = True
        self.letterbox(True)
        hud.show(False)
        tr = _train_build(w, track_y, 830.0)
        _add(tr['root'], tr['root'].removeNode)
        _add(tr['bed'], tr['bed'].removeNode)
        tr['phase'], tr['v'], tr['stop_x'] = 'approach', 17.0, yard[0]
        it['train'] = tr
        cam.override = (yard[0] - 9.5, yard[1] + 0.5, 2.5, yard[0] + 30.0, track_y, 2.1)
        yield lambda: tr['phase'] == 'done'
        say('Машинист: Да ты весь в крови, парень… Залезай.')
        yield wait_enter(0.8, 4.6)
        hud.fade(1.0, 1.8)
        yield 1.1
        # (дальше — утро в Порт-Глухове: _end_intro)

    def _step_intro(self, dt):
        w = self.w
        it = self.intro
        it['t'] += dt
        inp = w.game.inp
        if inp.hit('escape'):
            self._end_intro()
            return
        nxt = it['t'] > 0.3 and (inp.hit('enter') or inp.hit('space') or inp.hit('mouse1'))
        try:
            if it['tick'] is not None:
                it['tick'](dt)
            for _ in range(4):
                wt = it['wait']
                if nxt:
                    ready = True
                    nxt = False
                elif isinstance(wt, (int, float)):
                    it['wait'] = wt - dt
                    ready = it['wait'] <= 0.0
                else:
                    ready = bool(wt())
                if not ready:
                    return
                it['wait'] = next(it['gen'])
                it['t'] = 0.0
                dt = 0.0
        except StopIteration:
            self._end_intro()
        except Exception:
            # сбой в сценке не должен оставить игрока перед чёрным экраном
            w.game.report_error()
            self._end_intro()

    def _intro_off(self):
        """Вернуть миру то, что пролог выключал (в конце сценки и если её прервали выходом в меню)."""
        w = self.w
        w.traffic.enabled = True
        w.sky.time_scale = 1.0
        w.scene_engine = None

    def _end_intro(self):
        """Конец пролога (или пропуск): убрать декорации, утро, герой на остановке — и тут звонит Брюс."""
        w = self.w
        it = self.intro
        if it is None:
            return
        self.intro = None
        pl = w.player
        p = pl.ped
        hud = w.hud
        # декорации Гангона: фасад, сумка, Лёха, мотоцикл, «Призрак», маркеры, товарный поезд
        for (_, cleanup) in it.get('props', []):
            try:
                cleanup()
            except Exception:
                pass
        it['tick'] = None
        it['leo'] = None
        it['bike'] = None
        self._intro_off()
        w.crowd.enabled = True
        pl.god = False                       # в Порт-Глухове снова всё по-настоящему
        pl.crawl = False
        if p.state == 'down':                # пропуск пролога в момент, когда Макса только что подстрелили
            p.set_state('stand')
        p.air = False
        p.vx = p.vy = p.vz = 0.0
        w.police.clear()
        pl.clear_weapons()                   # пистолета у Макса не осталось
        pl.ped.health = max(pl.ped.health, 65.0)   # рана саднит, но он жив
        w.scene_engine = None
        w.interiors.cinema = False
        hud.clear_big()                      # «ГАНГОН» и подсказки не должны рваться в утро
        for mk in self.markers:
            mk.show(True)
        if it.get('hint') is not None:
            it['hint'].destroy()
        pl.invincible = False
        pl.script_move = None
        p.stop_act()
        p.node.show()
        w.sky.set_weather('clear')
        w.sky.set_time(8.0)
        w.cam.override = None
        hud.clear_subtitles()
        hud.show(True)
        self.letterbox(False)
        pl.freeze = False
        # пока шла сценка, героя носило по всей карте и улицу у дома «разобрали»: заселяем её заново
        sx, sy, syaw = w.city.start_pos
        pl.teleport(sx - 11.5, sy - 1.3, 0.0)           # у вокзала, где его высадил товарный поезд
        w.cam.face(sx - 11.5, sy - 1.3, 0.0)
        w.cam.pitch = -0.16
        w.traffic.populate()
        w.crowd.populate()
        hud.fade(1.0, instant=True)
        hud.fade(0.0, 0.9)
        self.hint_t = 14.0
        self.call_t = 1.6                               # брат уже набирает номер

    # ------------------------------------------------------------------
    # возрождение после гибели / ареста
    # ------------------------------------------------------------------
    def update_respawn(self, dt):
        """Вызывается каждый кадр; управляет экраном «ПОТРАЧЕНО» / «АРЕСТОВАН»."""
        w = self.w
        kind = w.respawn_kind
        if kind is None:
            return
        hud = w.hud
        t0 = w.respawn_t
        w.respawn_t += dt
        t = w.respawn_t
        self.respawning = True
        if t0 < 0.8 <= t:
            if kind == 'wasted':
                hud.big('ПОТРАЧЕНО', REDC, 5.0)
            else:
                hud.big('АРЕСТОВАН', BLUEC, 5.0)
        if t0 < 3.6 <= t:
            hud.fade(1.0, 1.2)
        if t >= 5.0:
            self._respawn(kind)
            w.respawn_kind = None
            self.respawning = False

    def _respawn(self, kind):
        w = self.w
        pl = w.player
        c = w.city
        if self.active is not None:
            self._finish(False, 'Ты погиб.' if kind == 'wasted' else 'Тебя арестовали.', self.active.side)
        lm = c.landmarks['hospital' if kind == 'wasted' else 'police']
        x, y = lm['door']
        w.police.clear()
        w.weapons.clear()
        w.fx.clear()
        # убираем всё лишнее вокруг старого и нового места
        for v in list(w.vehicles):
            if not v.keep:
                w.remove_vehicle(v)
        for p in list(w.peds):
            if not p.is_player and not p.keep:
                w.remove_ped(p)
        w._sweep()
        w.traffic.parked = {}
        x, y = self.free_spot(x - 2.0, y + 0.2)
        pl.revive(x, y, -math.pi / 2)
        if kind == 'wasted':
            fee = min(pl.money, 500)
            msg = 'Тебя подлатали в больнице. Счёт: $%d.' % fee
        else:
            fee = min(pl.money, 300)
            pl.clear_weapons()
            msg = 'Оружие конфисковано. Взятка следователю: $%d.' % fee
        if fee:
            pl.add_money(-fee)
        w.sky.advance(5.0)
        w.traffic.populate()
        w.crowd.populate()
        w.hud.fade(0.0, 0.8)
        w.hud.help(msg, 7.0)
        w.slowmo = 1.0
        self.refresh_contacts()

    # ------------------------------------------------------------------
    # сохранение
    # ------------------------------------------------------------------
    def save_game(self, auto=False):
        w = self.w
        pl = w.player
        data = dict(
            money=pl.money, done=sorted(self.done), packages=sorted(self.packages),
            ammo=dict((str(k), v) for k, v in pl.ammo.items()), weapon=pl.weapon_id,
            health=pl.ped.health, armor=pl.ped.armor, hour=w.sky.hour, day=w.sky.day,
            stats=w.stats, hints=sorted(self.hints), bonus=self.bonus_given, finale=self.finale_shown,
            ckpt=dict(self.ckpt), garage=w.garage.state())
        return settings_mod.write_save(data)

    def load_game(self, data):
        w = self.w
        pl = w.player
        pl.money = int(data.get('money', 0))
        w.hud.money_show = pl.money
        self.done = set(data.get('done', []))
        self.packages = set(int(i) for i in data.get('packages', []))
        self.hints = set(data.get('hints', []))
        pl.ammo = {W_FIST: -1}
        for k, v in data.get('ammo', {}).items():
            try:
                k = int(k)
            except ValueError:
                continue
            if 0 <= k < len(WEAPONS):
                pl.ammo[k] = int(v)
        wid = int(data.get('weapon', 0))
        pl.select(wid if wid in pl.ammo else W_FIST)
        pl.ped.health = clamp(float(data.get('health', 100.0)), 20.0, pl.ped.max_health)
        pl.ped.armor = clamp(float(data.get('armor', 0.0)), 0.0, 100.0)
        w.sky.hour = float(data.get('hour', 8.0)) % 24.0
        w.sky.day = int(data.get('day', 1))
        st = data.get('stats', {})
        for k in w.stats:
            if k in st:
                w.stats[k] = st[k]
        self.finale = self.finale_shown = bool(data.get('finale', False))
        self.ckpt = dict((str(k), int(v)) for k, v in data.get('ckpt', {}).items())
        self.call_t = 9.0
        w.garage.restore(data.get('garage', []))
        # убрать найденные тайники, выдать накопленные награды
        for pk in self.pickups:
            if pk.kind == 'package' and pk.index in self.packages:
                pk.remove()
        self.bonus_given = int(data.get('bonus', 0))
        if self.bonus_given:
            self._safehouse_bonus(range(1, self.bonus_given + 1))
        self.refresh_contacts()
        self.sync_story()
        # игра сохраняется у кровати — там же герой и просыпается
        if 'safehouse' in w.interiors.rooms:
            w.interiors.enter('safehouse', instant=True, spot='wake')
            self.in_save = True


# ---------------------------------------------------------------------------
# пролог: ювелирный в Гангоне (декорации, которых в городе нет — они стираются в конце пролога)
# ---------------------------------------------------------------------------
def _jewel_facade(w, x, y):
    """Фасад ювелирного «Авангард» и золотая вывеска; смотрит на юг (на улицу)."""
    from .meshbuilder import MeshBuilder
    mb = MeshBuilder()
    z0, z1 = 0.0, 4.7
    mb.wall('gf_jewel', x - 4.6, y, x + 4.6, y, z0, z1)          # стена с витриной (текстура лицом на юг)
    mb.wall('sign_jewel', x - 4.4, y - 0.06, x + 4.4, y - 0.06, 3.35, 4.15)   # золотая вывеска
    mb.box('metal_paint', x - 4.7, y - 0.12, z1 - 0.18, x + 4.7, y + 0.25, z1, (0.12, 0.11, 0.12, 1))   # козырёк
    node = mb.build('jewel', w.assets.apply_state)
    node.reparentTo(w.fx.root)
    return node


def _duffel(w, x, y):
    """Сумка с добычей: жёлто-коричневый баул."""
    from .meshbuilder import MeshBuilder
    mb = MeshBuilder()
    mb.box('metal_paint', -0.30, -0.16, 0.0, 0.30, 0.16, 0.34, (0.32, 0.26, 0.10, 1), uv_m=0.4)
    mb.box(None, -0.13, -0.02, 0.34, 0.13, 0.02, 0.44, (0.20, 0.17, 0.08, 1))
    mb.box(None, -0.06, -0.03, 0.40, 0.06, 0.03, 0.47, (0.75, 0.62, 0.25, 1))
    node = mb.build('duffel', w.assets.apply_state)
    node.reparentTo(w.fx.root)
    node.setPos(x, y, w.city.ground_z(x, y))
    return node


def _train_build(w, track_y, nose_x, z=0.0):
    """Грузовой поезд: капот, кабина, четыре вагона.  Едет с востока на запад."""
    from .meshbuilder import MeshBuilder
    mb = MeshBuilder()
    body = (0.13, 0.14, 0.16, 1)
    roof = (0.09, 0.095, 0.105, 1)
    # --- тепловоз: капот, кабина, юбка, труба
    mb.box('metal_paint', 0.0, -1.35, 0.9, -13.5, 1.35, 2.6, body, uv_m=3.2)            # длинный капот
    mb.box('metal_paint', -13.5, -1.35, 0.9, -17.5, 1.35, 4.3, body, uv_m=3.2)          # кабина
    mb.box(None, -13.6, -1.36, 2.65, -17.5, 1.36, 3.15, (0.92, 0.88, 0.55, 1))          # окна (светятся)
    mb.box(None, -12.9, -1.36, 2.15, -13.6, 1.36, 2.3, (0.86, 0.6, 0.2, 1))             # «рога» на капоте
    mb.box(None, 0.0, -1.4, 0.25, -17.5, 1.4, 0.95, (0.07, 0.07, 0.08, 1))              # юбка
    mb.cylinder('metal_paint', -3.5, 0.0, 2.6, 3.15, 0.34, 8, roof)                     # выхлопная труба
    mb.box(None, 0.0, -1.42, 1.05, -1.3, 1.42, 1.35, (0.75, 0.65, 0.2, 1))              # передняя перекладина
    # --- четыре вагона: два полувагона (ржавые) и две цистерны
    cars = [(-19.5, -33.5, (0.42, 0.26, 0.16, 1), 'box'), (-35.5, -49.5, (0.4, 0.27, 0.17, 1), 'box'),
            (-51.5, -63.5, (0.17, 0.18, 0.19, 1), 'tank'), (-65.5, -77.5, (0.2, 0.21, 0.22, 1), 'tank')]
    for (x0, x1, col, kind) in cars:
        if kind == 'box':
            mb.box('corrugated', x0, -1.3, 0.75, x1, 1.3, 3.6, col, uv_m=2.4)
            mb.box(None, x0, -1.32, 0.25, x1, 1.32, 0.8, (0.07, 0.07, 0.08, 1))
        else:
            mb.cylinder_x('metal_paint', x0, x1, 0.0, 2.0, 1.28, 10, col, cap_color=roof)
            mb.box(None, x0, -0.9, 0.25, x1, 0.9, 0.85, (0.07, 0.07, 0.08, 1))
    # голова поезда: два белых фонаря
    mb.box(None, 0.0, -0.62, 1.05, 0.12, -0.28, 1.45, (1.0, 0.98, 0.85, 1))
    mb.box(None, 0.0, 0.28, 1.05, 0.12, 0.62, 1.45, (1.0, 0.98, 0.85, 1))
    node = mb.build('train', w.assets.apply_state)
    # рельсы-«подложка»: тёмная полоса вдоль путей (декорация)
    mb = MeshBuilder()
    mb.flat(None, -600.0, track_y - 1.9, 900.0, track_y + 1.9, z - 0.02, color=(0.10, 0.10, 0.11, 1))
    bed = mb.build('railbed', w.assets.apply_state)
    bed.reparentTo(w.fx.root)
    node.reparentTo(w.fx.root)
    node.setPos(nose_x, track_y, z)
    return dict(root=node, bed=bed, x=nose_x)
