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

GOLD = (1.0, 0.82, 0.2, 1.0)
REDC = (0.95, 0.2, 0.15, 1.0)
BLUEC = (0.35, 0.6, 1.0, 1.0)

CONTACTS = {
    'vano': dict(title='Вано', blip='blip_vano', place='гараж Вано'),
    'rosa': dict(title='Роза', blip='blip_rosa', place='бар «У Розы»'),
    'prof': dict(title='Проф', blip='blip_prof', place='башня Профа'),
}


def contact_look(name):
    if name == 'vano':
        return make_look(skin=SKINS[2], hair=(0.1, 0.08, 0.06), shirt=(0.9, 0.9, 0.86), pants=(0.2, 0.24, 0.36),
                         torso='tank', beard=True, hat='cap', hat_color=(0.6, 0.1, 0.1), fat=1.3, scale=1.02)
    if name == 'rosa':
        return make_look(skin=SKINS[0], hair=(0.62, 0.1, 0.08), shirt=(0.8, 0.12, 0.3), pants=(0.8, 0.12, 0.3),
                         torso='tee', female=True, scale=0.97, fat=0.95)
    return make_look(skin=SKINS[5], hair=(0.7, 0.7, 0.72), shirt=(0.3, 0.3, 0.36), pants=(0.3, 0.3, 0.36),
                     torso='jacket', glasses=True, scale=1.0, fat=0.95)


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
        """Короткая сценка-разговор с контактом (пропуск — Enter или пробел)."""
        ms = self.ms
        w = self.w
        pl = w.player
        lmk = w.city.landmarks[contact]
        dx, dy = lmk['door']
        npc = self.npc(dx, dy + 1.0, -math.pi / 2, contact_look(contact))
        ms.clear_area(dx, dy, 3.0, peds=True, keep=npc)
        pl.freeze = True
        p = pl.ped
        p.x, p.y = dx, dy - 0.9
        p.yaw = math.pi / 2
        p.speed = 0.0
        p.sync()
        w.cam.override = (dx + 2.6, dy - 3.6, 1.9, dx - 0.3, dy + 0.4, 1.45)
        w.hud.show(False)
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
    chase = m.ms.start_chasers(m, ['lowrider', 'muscle', 'beater'], 'reds', 3, 9.0)
    yield from m.goto(bx, by, 5.5, 'Отвези Розу в банк. Не дай «красным» вас достать!', vehicle=car,
                      extra=lambda: rosa.vehicle is car)
    chase['active'] = False
    m.unwatch(rosa)
    m.unboard(rosa, c.landmarks['bank']['door'])
    m.say('Роза: Ух! Давно меня так не катали. Ты — лучший.')
    yield 2.5


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
        zone = c.zone_at(x, y)
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


MISSIONS = [
    dict(id='v1', contact='vano', title='Знакомство', reward=500, fn=m_v1, req=[]),
    dict(id='v2', contact='vano', title='Должок', reward=1200, fn=m_v2, req=['v1']),
    dict(id='v3', contact='vano', title='Конкуренты', reward=2000, fn=m_v3, req=['v2']),
    dict(id='v4', contact='vano', title='Круг почёта', reward=3000, fn=m_v4, req=['v3']),
    dict(id='r1', contact='rosa', title='Шумные гости', reward=800, fn=m_r1, req=['v2']),
    dict(id='r2', contact='rosa', title='Курьер', reward=1500, fn=m_r2, req=['r1']),
    dict(id='r3', contact='rosa', title='Разборка', reward=2500, fn=m_r3, req=['r2']),
    dict(id='r4', contact='rosa', title='Инкассация', reward=4000, fn=m_r4, req=['r3']),
    dict(id='p1', contact='prof', title='Свидетель', reward=3000, fn=m_p1, req=['v3', 'r2']),
    dict(id='p2', contact='prof', title='Груз', reward=4000, fn=m_p2, req=['p1']),
    dict(id='p3', contact='prof', title='Свой человек', reward=5000, fn=m_p3, req=['p2']),
    dict(id='p4', contact='prof', title='Большой куш', reward=50000, fn=m_p4, req=['p3', 'v4', 'r4']),
]
TAXI = dict(id='taxi', contact=None, title='Таксист', reward=0, fn=m_taxi, side=True)
STORY_TOTAL = len(MISSIONS)


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
        self._spray_t = 0.0
        self.letter = None
        self.respawning = False
        self.intro = None
        self.msg_t = 0.0
        self.hint_t = 3.0
        self.bonus_given = 0
        self._build_static()

    # ------------------------------------------------------------------
    def _build_static(self):
        w = self.w
        c = w.city
        hud = w.hud
        lm = c.landmarks
        sx, sy = lm['safehouse']['door']
        self.save_mk = Marker(w, sx + 2.2, sy, 1.0, BLUE, 1.4)
        self.markers.append(self.save_mk)
        self.static_blips.append(hud.add_blip('blip_save', sx, sy, edge=True, scale=1.1))
        for name in ('spray', 'spray2'):
            if name in lm:
                x, y = lm[name]['bay']
                self.static_blips.append(hud.add_blip('blip_spray', x, y, edge=False, rng=400.0))
        for name in ('guns', 'guns2'):
            if name in lm:
                x, y = lm[name]['door']
                mk = Marker(w, x, y, 1.1, GREEN, 1.4)
                self.markers.append(mk)
                self.shop_mks.append(mk)
                self.static_blips.append(hud.add_blip('blip_guns', x, y, edge=False, rng=400.0))
        x, y = lm['hospital']['door']
        self.static_blips.append(hud.add_blip('blip_hospital', x, y, edge=False, rng=300.0))
        x, y = lm['police']['door']
        self.static_blips.append(hud.add_blip('blip_police', x, y, edge=False, rng=300.0))
        x, y = lm['taxi']['door']
        self.static_blips.append(hud.add_blip('blip_taxi', x, y, edge=False, rng=300.0))
        # предметы на карте
        for i, (x, y, hint) in enumerate(c.pickup_spots):
            kind, wid, amount = spot_pickup(i, hint)
            pk = Pickup(w, kind, x, y, wid, amount, respawn=240.0)
            self.pickups.append(pk)
        hx, hy = lm['hospital']['door']
        self.pickups.append(Pickup(w, 'health', hx - 3.0, hy, respawn=120.0))
        px, py = lm['police']['door']
        self.pickups.append(Pickup(w, 'armor', px + 12.0, py + 0.3, respawn=240.0))
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
                x, y = w.city.landmarks[name]['door']
                if mk is None:
                    mk = Marker(w, x, y, 1.3, PINK, 1.7)
                    self.markers.append(mk)
                    self.contact_mk[name] = mk
                if self.contact_blip.get(name) is None:
                    self.contact_blip[name] = w.hud.add_blip(CONTACTS[name]['blip'], x, y, edge=True, scale=1.25)

    def progress(self):
        return len([m for m in MISSIONS if m['id'] in self.done]), STORY_TOTAL

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
        if passed:
            self.done.add(m.spec['id'])
            if m.reward:
                pl.add_money(m.reward)
            w.audio.play('passed', 0.9)
            hud.big('МИССИЯ ВЫПОЛНЕНА!', GOLD, 5.0, '$%d' % m.reward if m.reward else '')
            self._announce(m.spec['id'])
            self.save_game(auto=True)
        else:
            if m.side or quiet:
                hud.big(m.spec['title'], BLUEC, 4.0, reason)
            else:
                w.audio.play('failed', 0.8)
                hud.big('МИССИЯ ПРОВАЛЕНА', REDC, 4.5, reason)
            self.fail_cd = 5.0
        hud.clear_subtitles()
        self.refresh_contacts()

    def _announce(self, mid):
        """После задания подсказываем, куда идти дальше."""
        w = self.w
        text = None
        if mid == 'v2':
            text = 'Вано: Загляни к Розе в бар в Ржавом квартале. Скажешь — от меня. (метка «Р»)'
        elif mid in ('v3', 'r2') and 'v3' in self.done and 'r2' in self.done:
            text = 'Тобой заинтересовался серьёзный человек. Башня в Деловом центре (метка «П»).'
        elif mid in ('p3', 'v4', 'r4') and all(k in self.done for k in ('p3', 'v4', 'r4')):
            text = 'Проф готовит большое дело. Загляни в башню.'
        if text:
            w.hud.help(text, 10.0)
            w.audio.play('pager', 0.7)

    def notify(self, event, obj=None, arg=None):
        pass

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
            # такси
            v = pl.vehicle
            if v is not None and v.kind == 'taxi' and self.active is None:
                if 'taxi' not in self.hints:
                    self.hints.add('taxi')
                    hud.help('Ты в такси. Нажми T, чтобы подработать таксистом.', 7.0)
                if w.game.inp.hit('t'):
                    self.start(TAXI)
        if self.msg_t > 0.0:
            self.msg_t -= dt
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
        elif k == 'item':
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
                self.pickups.append(Pickup(w, 'armor', sx - 5.5, sy, respawn=300.0))
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
            if v.kind in ('police', 'enforcer', 'fbi', 'army', 'ambulance', 'bus'):
                hud.help('Такую машину здесь не перекрасят.', 4.0)
                continue
            cost = 300
            if pl.money < cost:
                hud.help('Перекраска стоит $%d. Приходи с деньгами.' % cost, 4.0)
                continue
            pl.add_money(-cost)
            old = v.paint
            v.set_paint((old + 1 + random.randrange(8)) % 14)
            v.health = v.max_health
            v.burn_t = 0.0
            w.police.locked = None if self.active is None else w.police.locked
            if w.police.locked is None:
                w.police.clear()
            w.audio.play('spray', 0.9)
            hud.fade(1.0, 4.0)
            self._spray_t = 0.7
            hud.help('Новая покраска и ремонт: -$%d. Розыск снят.' % cost, 5.0)
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
        elif 'start' not in h and self.active is None and pl.state == 'foot':
            h.add('start')
            hud.help('WASD — движение, мышь — обзор, Shift — бег, пробел — прыжок, F — сесть в машину.', 10.0)
        elif 'goal' not in h and w.time > 14.0 and self.active is None and not self.done:
            h.add('goal')
            hud.help('Иди к Вано: розовая метка «В» на радаре. Его гараж — к западу от убежища.', 10.0)

    # ------------------------------------------------------------------
    def start_intro(self):
        w = self.w
        self.intro = dict(t=0.0, i=-1, lines=[
            'Порт-Глухов. Город, в который не приезжают — в него попадают.',
            'Тебя зовут Макс. Три года за рулём у чужих людей, одно неудачное дело — и вот ты здесь.',
            'Из имущества — ключ от комнаты в Старом городе и номер человека по имени Вано.',
            'Пора напомнить этому городу, кто здесь лучший водитель.'], dur=0.0)
        w.hud.fade(1.0, instant=True)
        w.hud.show(False)
        w.player.freeze = True
        self.letterbox(True)

    def _step_intro(self, dt):
        w = self.w
        it = self.intro
        it['t'] += dt
        inp = w.game.inp
        skip = it['t'] > 0.25 and (inp.hit('enter') or inp.hit('space') or inp.hit('mouse1') or inp.hit('escape'))
        if it['t'] >= it['dur'] or skip:
            it['i'] += 1
            it['t'] = 0.0
            if it['i'] == 1:
                w.hud.fade(0.0, 0.5)
            if it['i'] >= len(it['lines']):
                self.intro = None
                w.hud.clear_subtitles()
                w.hud.fade(0.0, 1.0)
                w.hud.show(True)
                w.player.freeze = False
                self.letterbox(False)
                w.cam.override = None
                w.cam.pitch = -0.22
                w.cam.face(w.city.start_pos[0], w.city.start_pos[1], w.city.start_pos[2])
                w.hud.mission_title('Гиблый район')
                return
            line = it['lines'][it['i']]
            it['dur'] = 2.4 + len(line) * 0.055
            w.hud.subtitle(line, it['dur'] + 0.5, clear=True)
        # облёт: камера медленно кружит над убежищем
        sx, sy, syaw = w.city.start_pos
        a = w.time * 0.12
        w.cam.override = (sx + math.cos(a) * 26.0, sy - 14.0 + math.sin(a) * 8.0, 15.0, sx, sy, 2.0)

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
            stats=w.stats, hints=sorted(self.hints), bonus=self.bonus_given, finale=self.finale_shown)
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
        # убрать найденные тайники, выдать накопленные награды
        for pk in self.pickups:
            if pk.kind == 'package' and pk.index in self.packages:
                pk.remove()
        self.bonus_given = int(data.get('bonus', 0))
        if self.bonus_given:
            self._safehouse_bonus(range(1, self.bonus_given + 1))
        self.refresh_contacts()
