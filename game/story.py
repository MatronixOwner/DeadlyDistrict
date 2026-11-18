# -*- coding: utf-8 -*-
"""Сюжет: Макс, его брат Брюс и босс.

Предыстория — в прологе (missions.Missions.start_intro): три года назад Макс был водителем у грабителей банка,
у моста их ждал заслон; теперь он отсидел своё и вернулся в город, где брат сберёг его машину.
Задания начинаются телефонным звонком Брюса: где бы ни был герой, звонит телефон — и дело пошло.
Здесь лежат сами сценарии и то, что нужно только им: звонок, спутник, который ходит и ездит вместе
с героем, часовые с ограниченным обзором и ворота жёлтого контейнера.
"""
import math
import random

from panda3d.core import NodePath

from .defs import W_PISTOL, W_BAT, W_UZI, W_SILENCED, make_look, gang_look
from .collision import F_PED, F_WALL
from .meshbuilder import MeshBuilder
from .vehicle import Vehicle

# кто есть кто: имя на экране, цвет кружка в телефоне, облик
PEOPLE = {
    'bruce': dict(title='Брюс', color=(0.84, 0.38, 0.17),
                  look=lambda: make_look(model='m_grey_h4', scale=1.0, fat=1.0)),
    'boss': dict(title='Босс', color=(0.47, 0.24, 0.59),
                 look=lambda: make_look(model='m_leather_c', scale=1.02, fat=1.15)),
}
SHIP_GANG = 'ship'


def person_look(name):
    return PEOPLE[name]['look']()


# ---------------------------------------------------------------------------
# телефон
# ---------------------------------------------------------------------------
def phone_call(m, who, lines, ring=2.6):
    """Звонок: телефон звонит, герой отвечает, реплики идут субтитрами.

    lines — [(кто говорит, текст), ...].  Во время разговора можно идти и ехать; Enter — следующая реплика."""
    w = m.w
    hud = w.hud
    pl = w.player
    inp = w.game.inp
    info = PEOPLE[who]
    hud.phone_show(info['title'], info['color'], 'ring')
    w.audio.play('phone', 0.8)
    t = [0.0, False]

    def ringing():
        t[0] += w.dt
        if t[0] > 1.35 and not t[1]:
            t[1] = True
            w.audio.play('phone', 0.8)
        return t[0] > ring
    yield ringing
    w.audio.play('phone_up', 0.7)
    hud.phone_show(info['title'], info['color'], 'talk')
    p = pl.ped
    p.play('phone', True)                          # когда герой стоит, он держит трубку у уха
    for (name, text) in lines:
        dur = 1.4 + len(text) * 0.058
        hud.subtitle('%s: %s' % (name, text), dur + 0.5, clear=True)
        tt = [0.0]

        def cond():
            tt[0] += w.dt
            pl.no_enter_t = 0.25                   # Enter сейчас листает реплики, а не открывает дверь машины
            if tt[0] > 0.35 and inp.hit('enter'):
                return True
            return tt[0] > dur
        yield cond
    hud.clear_subtitles()
    hud.phone_hide()
    w.audio.play('phone_down', 0.6)
    p.stop_act()


# ---------------------------------------------------------------------------
# спутник
# ---------------------------------------------------------------------------
class Buddy(object):
    """Спутник героя: идёт следом, садится к нему в машину и выходит вместе с ним.

    Идёт он не напрямик, а по следу героя — так он поднимается по тому же трапу и обходит те же углы,
    а не шагает с пирса в воду."""

    def __init__(self, m, ped):
        self.m = m
        self.p = ped
        self.active = True
        self.lost_t = 0.0
        self.hint_t = 0.0
        self.trail = []
        ped.set_state('stand')
        m.ticks.append(self.tick)

    def stop(self):
        self.active = False

    def riding(self):
        """Едет ли спутник в одной машине с героем."""
        v = self.m.w.player.vehicle
        return v is not None and self.p.vehicle is v

    def near(self, r=14.0):
        pl = self.m.w.player
        if self.riding():
            return True
        px, py = pl.pos()
        return (self.p.x - px) ** 2 + (self.p.y - py) ** 2 < r * r and self.p.vehicle is None

    def _dry(self, ax, ay, bx, by):
        """Можно ли пройти по прямой, не свалившись в воду и не спрыгнув с высоты."""
        c = self.m.w.city
        n = int(math.hypot(bx - ax, by - ay) / 0.8) + 1
        z = c.ground_z(ax, ay)
        for k in range(1, n + 1):
            x, y = ax + (bx - ax) * k / n, ay + (by - ay) * k / n
            z2 = c.ground_z(x, y)
            if z2 < -0.4 or abs(z2 - z) > 0.9:
                return False
            z = z2
        return True

    def tick(self, dt):
        p = self.p
        if not self.active or p.dead or p.removed:
            return
        w = self.m.w
        pl = w.player
        v = pl.vehicle if pl.state == 'car' else None
        px, py = pl.pos()
        tr = self.trail
        if pl.state == 'foot' and pl.vehicle is None:
            if not tr or (tr[-1][0] - px) ** 2 + (tr[-1][1] - py) ** 2 > 1.0:
                tr.append((px, py))
                if len(tr) > 90:
                    del tr[0]
        if p.vehicle is not None:
            if p.vehicle is not v and (v is not None or pl.state == 'foot'):
                w.take_out(p, 1)                   # герой вышел — выходим следом
                w.audio.play_at('door', p.x, p.y, 0.7)
                p.set_state('stand')
                del tr[:]
            return
        if p.state == 'down':
            return
        gx, gy = px, py
        board = False
        if v is not None:
            if v.spec.seats < 2:
                # второго места нет: ждёт, где стоял, а игроку объясняем, почему он не садится
                self.hint_t -= dt
                if self.hint_t <= 0.0 and (p.x - px) ** 2 + (p.y - py) ** 2 < 40.0 * 40.0:
                    self.hint_t = 12.0
                    w.hud.help('На «%s» вдвоём не уехать: нужна машина или мотоцикл с местом для пассажира.'
                               % v.spec.title, 6.0)
                return
            gx, gy = v.door_pos(1)
            if w.static.overlap_circle(gx, gy, p.radius, F_PED):
                gx, gy = v.door_pos(-1)            # правая дверь у стены — садится с другой стороны
            tight = w.static.overlap_circle(gx, gy, p.radius, F_PED)        # машина зажата (стоит в контейнере)
            d = math.hypot(gx - p.x, gy - p.y)
            if math.hypot(v.vx, v.vy) < 3.0 and (d < 1.6 or (tight and math.hypot(v.x - p.x, v.y - p.y) < 5.0)):
                w.put_in_vehicle(p, v)
                w.audio.play_at('door', v.x, v.y, 0.8)
                del tr[:]
                return
            if tight:
                gx = v.x - math.cos(v.yaw) * (v.spec.L * 0.5 + 1.0)
                gy = v.y - math.sin(v.yaw) * (v.spec.L * 0.5 + 1.0)
            board = True
        d = math.hypot(gx - p.x, gy - p.y)
        # пройденные точки следа выбрасываем
        while tr and (tr[0][0] - p.x) ** 2 + (tr[0][1] - p.y) ** 2 < 0.8:
            del tr[0]
        if not board and d < 2.5:
            if p.state != 'stand':
                p.set_state('stand')
            del tr[:]
            self.lost_t = 0.0
            return
        if d < 7.0 and self._dry(p.x, p.y, gx, gy):
            tx, ty = gx, gy                         # цель рядом и путь свободен — напрямик
            ok = True
        elif tr:
            tx, ty = tr[0]
            ok = self._dry(p.x, p.y, tx, ty)
        else:
            tx, ty = gx, gy
            ok = self._dry(p.x, p.y, tx, ty)
        if ok:
            p.tx, p.ty = tx, ty
            if p.state != 'goto':
                p.set_state('goto', 1.0)
            p.timer = 1.0 if d > 5.0 else 0.0       # далеко — бегом, рядом — шагом
        elif p.state != 'stand':
            p.set_state('stand')
        # не пройти, застрял или сильно отстал — догоняет «за кадром»
        if not ok or d > 30.0 or p.stuck_t > 1.5 or p.z < -0.4:
            self.lost_t += dt
        else:
            self.lost_t = max(0.0, self.lost_t - dt)
        if self.lost_t > 2.0 and (not w.visible(p.x, p.y, 1.5) or self.lost_t > 6.0 or p.z < -0.4):
            self._jump_near(gx, gy)

    def _jump_near(self, gx, gy):
        w = self.m.w
        p = self.p
        cam = w.cam
        gz = w.city.ground_z(gx, gy)
        for back in (5.0, 7.0, 3.5, 2.2):
            for side in (0.0, 1.6, -1.6):
                x = gx - math.cos(cam.yaw) * back + math.sin(cam.yaw) * side
                y = gy - math.sin(cam.yaw) * back - math.cos(cam.yaw) * side
                if w.static.overlap_circle(x, y, p.radius + 0.1, F_PED) or w.city.in_water(x, y):
                    continue
                if abs(w.city.ground_z(x, y) - gz) > 1.2 or not self._dry(x, y, gx, gy):
                    continue
                p.x, p.y = x, y
                p.z = w.city.ground_z(x, y)
                p.stuck_t = 0.0
                p.sync()
                del self.trail[:]
                self.lost_t = 0.0
                return


# ---------------------------------------------------------------------------
# жёлтый контейнер на палубе сухогруза
# ---------------------------------------------------------------------------
class ShipDoor(object):
    """Ворота жёлтого контейнера: закрыты, пока их не откроют ключом; закрытые — преграда."""

    def __init__(self, world):
        self.w = world
        sh = world.city.special.get('ship')
        self.ok = sh is not None
        self.open = False
        self.k = 0.0
        self.box = None
        self.leaves = []
        if not self.ok:
            return
        yx0, yy0, yx1, yy1 = sh['yellow']
        dz = sh['deck']
        self.rect = (yx0, yy0, yx1, yy1)
        self.dz = dz
        self.root = world.fx.root.attachNewNode('shipdoor')
        hw = (yy1 - yy0) * 0.5
        for side in (-1, 1):
            mb = MeshBuilder()
            # створка: петля у края проёма, полотно тянется к середине
            y_a, y_b = (0.0, hw) if side < 0 else (-hw, 0.0)
            mb.box('corrugated', -0.06, y_a, 0.0, 0.06, y_b, 2.95, (0.93, 0.74, 0.12, 1), uv_m=2.6)
            mb.box(None, -0.10, (y_a + y_b) * 0.5 - 0.05, 0.9, -0.06, (y_a + y_b) * 0.5 + 0.05, 2.0, (0.2, 0.2, 0.22, 1))
            leaf = mb.build('leaf', world.assets.apply_state)
            leaf.reparentTo(self.root)
            leaf.setPos(yx0, yy0 if side < 0 else yy1, dz)
            self.leaves.append((leaf, side))
        self._block(True)

    def _block(self, on):
        st = self.w.static
        if on and self.box is None:
            x0, y0, x1, y1 = self.rect
            self.box = st.add_box(x0 - 0.12, y0, x0 + 0.12, y1, self.dz, self.dz + 3.0, F_WALL)
        elif not on and self.box is not None:
            st.remove_box(self.box)
            self.box = None

    def set_open(self, on, instant=False):
        if not self.ok:
            return
        self.open = on
        self._block(not on)
        if instant:
            self.k = 1.0 if on else 0.0
            self._pose()

    def _pose(self):
        for leaf, side in self.leaves:
            leaf.setH(side * 105.0 * self.k)

    def update(self, dt):
        if not self.ok:
            return
        want = 1.0 if self.open else 0.0
        if self.k != want:
            self.k += (0.9 * dt) if want > self.k else (-0.9 * dt)
            self.k = max(0.0, min(1.0, self.k))
            self._pose()

    def remove(self):
        if not self.ok:
            return
        self._block(False)
        self.root.removeNode()
        self.ok = False


# ---------------------------------------------------------------------------
# задание 1
# ---------------------------------------------------------------------------
def m_s1(m):
    """«Брат за брата»: звонок Брюса, дорога домой, порт, двое бандитов, брата — домой."""
    w = m.w
    ms = m.ms
    c = w.city
    pl = w.player
    lm = c.landmarks
    home = lm['safehouse']
    home_addr = c.address('safehouse')
    if ms.ckpt.get('s1', 0) < 1:
        yield from phone_call(m, 'bruce', [
            ('Брюс', 'Хей, братан, как приехал?'),
            ('Макс', 'Да прекрасно добрался.'),
            ('Брюс', 'Не хочешь заработать лёгких денег?'),
            ('Макс', 'Не буду против.'),
            ('Брюс', 'А кстати, я тебе домик купил. %s.' % home_addr),
            ('Брюс', 'И «Ласточку» твою сберёг: стоит там в гараже, тебя дожидается.'),
            ('Макс', 'Спасибо, брат. На тебя можно положиться.'),
            ('Брюс', 'Удачи.'),
        ])
        w.hud.mission_title(m.spec['title'])
        if pl.vehicle is None:
            m.help('До дома далеко. Подойди к любой машине и нажми F — хозяин возражать будет, но недолго.', 9.0)
        dx, dy = home['road']
        yield from m.goto(dx, dy + 3.2, 5.5, 'Доберись до дома: %s.' % home_addr, tex='blip_save', stopped=False)
        ms.ckpt['s1'] = 1
        m.help('Это твой дом. Жёлтая стрелка у двери — вход, синий маркер у кровати сохраняет игру. '
               'В гараже справа стоит твоя «Ласточка»; туда же можно загнать ещё две машины — они останутся твоими.',
               11.0)
        yield 2.5
        yield from phone_call(m, 'bruce', [('Брюс', 'Приезжай быстро! Порт, первый причал!')], ring=1.8)
    else:
        yield from phone_call(m, 'bruce', [('Брюс', 'Макс! Приезжай быстро! Порт, первый причал!')], ring=1.8)
        w.hud.mission_title(m.spec['title'])
    # без оружия против двоих делать нечего: у двери дома лежит пистолет
    if not any(k in pl.ammo for k in (W_PISTOL, W_UZI, W_SILENCED)):
        gx, gy = home['door'][0] + 2.2, home['door'][1] + 1.2
        pk = ms.add_pickup('weapon', gx, gy, W_PISTOL, 34)
        m.pickups.append(pk)
        b = m.blip(gx, gy, tex='blip_pickup', scale=0.9)
        m.obj('Возьми пистолет у крыльца — в порту он пригодится.')
        yield lambda: pk.removed or W_PISTOL in pl.ammo
        m.unblip(b)
    # порт: первый (южный) причал
    pier = c.special['piers'][0]
    sx, sy = pier['x0'] + 26.0, (pier['y0'] + pier['y1']) * 0.5
    ms.clear_area(sx, sy, 16.0, peds=True)
    bruce = m.npc(sx, sy, math.pi, person_look('bruce'), hp=400.0)
    bruce.play('kneel', True)
    m.watch(bruce, 'Брюс погиб.')
    thugs = []
    for (ox, oy, wpn, yaw) in ((1.6, 1.3, W_PISTOL, math.pi + 0.6), (1.4, -1.5, W_BAT, math.pi - 0.6)):
        e = m.enemy(sx + ox, sy + oy, yaw, gang_look('purple'), wpn, 85.0, 0.26, 22.0, gang='purple')
        e.guard_radius = 26.0
        thugs.append(e)
    ax, ay = pier['x0'] + 6.0, sy
    yield from m.goto(ax, ay, 7.0, 'Гони в порт, на первый причал!', stopped=False)
    yield from m.kill_all(thugs, 'Разберись с бандитами.', 'Бандитов')
    # брат свободен
    bruce.stop_act()
    bruce.play('getup', False)
    yield 1.2
    bruce.stop_act()
    buddy = Buddy(m, bruce)
    m.obj('Садитесь с Брюсом в машину.')
    yield lambda: buddy.riding()
    m.say('Брюс: Спасибо тебе, братан. Буду должен жизнью.', 4.5)
    yield 4.0
    bh = lm['bruce']
    bx, by = bh['road']
    while True:
        yield from m.goto(bx, by, 5.0, 'Отвези Брюса домой: %s.' % c.address('bruce'), stopped=True)
        if buddy.riding() or buddy.near(12.0):
            break
        m.obj('Вернись за Брюсом.')
        b = m.blip(obj=bruce, tex='blip_friend')
        yield lambda: buddy.near(10.0)
        m.unblip(b)
    buddy.stop()
    m.unwatch(bruce)
    if bruce.vehicle is not None:
        m.unboard(bruce, walk_to=bh['door'])
    else:
        bruce.tx, bruce.ty = bh['door']
        bruce.set_state('goto', 0.0)
    m.say('Брюс: Держи, заслужил.', 3.0)
    yield 2.6


# ---------------------------------------------------------------------------
# задание 2
# ---------------------------------------------------------------------------
def boss_scene(m, bruce_look, lines):
    """Разговор у босса: Макс и Брюс стоят перед диваном.  lines — [(кто, текст), ...]."""
    ms = m.ms
    w = m.w
    pl = w.player
    its = w.interiors
    room = its.rooms['boss']
    w.hud.fade(1.0, 5.0)
    yield 0.3
    its.enter('boss', instant=True)
    boss = its.resident('boss')
    x, y, yaw = room.spots['talk']
    sx, sy, syaw = room.spots['side']
    p = pl.ped
    pl.freeze = True
    p.x, p.y = x, y
    p.speed = 0.0
    bx, by = (boss.x, boss.y) if boss is not None else (x, y + 2.8)
    p.yaw = math.atan2(by - y, bx - x)
    p.sync()
    bruce = m.npc(sx, sy, math.atan2(by - sy, bx - sx), bruce_look, hp=400.0)
    bruce.fixed = True
    w.hud.show(False)
    w.hud.mission_title('')
    ms.letterbox(True)
    w.hud.clear_subtitles()
    mx, my = (x + sx) * 0.5, (y + sy) * 0.5
    shots = dict(
        wide=(mx + 3.4, my - 2.2, 1.75, (mx + bx) * 0.5, (my + by) * 0.5, 1.15),
        boss=(mx + 0.9, my - 0.4, 1.55, bx, by, 1.12),
        pair=(bx + 0.8, by - 0.9, 1.25, mx, my, 1.5))
    w.hud.fade(0.0, 3.0)
    inp = w.game.inp
    for i, (who, text) in enumerate(lines):
        is_boss = who == 'Босс'
        w.cam.override = shots['wide' if i == 0 else ('boss' if is_boss else 'pair')]
        if boss is not None:
            boss.play('sit_talk' if is_boss else 'sit', True)
        p.play('talk' if 'Макс' in who else 'listen', True)
        bruce.play('talk' if 'Брюс' in who else 'listen', True)
        dur = 1.8 + len(text) * 0.06
        w.hud.subtitle('%s: %s' % (who, text), dur + 0.5, clear=True)
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
    if boss is not None:
        boss.stop_act()
    p.stop_act()
    w.remove_ped(bruce)
    if bruce in m.peds:
        m.peds.remove(bruce)
    its.leave(instant=True)
    w.cam.override = None
    pl.freeze = False
    pl.no_enter_t = 0.7
    w.hud.show(True)
    ms.letterbox(False)
    w.hud.fade(0.0, 3.0)


def ship_guards(m):
    """Охрана на палубе: часовые смотрят перед собой, двое ходят вдоль проезда."""
    w = m.w
    sh = w.city.special['ship']
    x0, y0, x1, y1, cy = sh['x0'], sh['y0'], sh['x1'], sh['y1'], sh['cy']
    yx0 = sh['yellow'][0]
    posts = [
        # (x, y, куда смотрит, оружие, точки обхода)
        (x0 + 4.0, cy + 5.5, math.pi, W_PISTOL, None),                           # у аппарели, смотрит на причал
        (x0 + 24.0, cy, 0.0, W_PISTOL, [(x0 + 24.0, cy), (x0 + 36.0, cy)]),       # ходит по проезду
        (yx0 - 4.0, cy - 2.2, math.pi, W_UZI, None),                             # у жёлтого контейнера
        (yx0 + 4.0, y1 - 0.85, math.pi, W_PISTOL, [(yx0 + 4.0, y1 - 0.85), (x0 + 30.0, y1 - 0.85)]),   # вдоль борта
        (x1 - 19.5, cy + 3.0, math.pi, W_UZI, None),                             # у надстройки
    ]
    guards = []
    for (x, y, yaw, wpn, route) in posts:
        e = m.enemy(x, y, yaw, gang_look('mafia'), wpn, 90.0, 0.30, 24.0, gang=SHIP_GANG)
        e.yaw = yaw
        e.sight_cos = math.cos(math.radians(60.0))
        e.route = route
        e.route_i = 0
        e.route_t = random.uniform(2.0, 5.0)
        guards.append(e)
    state = dict(alarm=False, t=0.0)

    def tick(dt):
        pl = w.player
        hot = False
        for e in guards:
            if e.dead or e.removed:
                continue
            if e.state == 'attack':
                hot = True
            elif e.route and e.state == 'guard':
                # обход: постоять, перейти к следующей точке
                gx, gy = e.guard_pos
                if math.hypot(gx - e.x, gy - e.y) < 1.2:
                    e.route_t -= dt
                    if e.route_t <= 0.0:
                        e.route_t = random.uniform(3.0, 6.0)
                        e.route_i = (e.route_i + 1) % len(e.route)
                        e.guard_pos = e.route[e.route_i]
        # выстрел без глушителя слышит вся палуба
        for (nx, ny, nr, who) in m.ms.noise:
            if who is pl.ped and nr > 20.0:
                for e in guards:
                    if not e.dead and e.state == 'guard' and (e.x - nx) ** 2 + (e.y - ny) ** 2 < nr * nr:
                        e.attack(pl.ped)
                        hot = True
        if hot and not state['alarm']:
            state['t'] += dt
            if state['t'] > 1.6:
                # тревога: кто заметил — поднял остальных
                state['alarm'] = True
                w.hud.help('Тревога! Охрана знает, что вы на борту.', 5.0)
                w.audio.play('pager', 0.8)
                for e in guards:
                    if not e.dead and e.state == 'guard':
                        e.sight_cos = None
                        e.attack(pl.ped)
    m.ticks.append(tick)
    return guards


def m_s2(m):
    """«Жёлтый контейнер»: знакомство с боссом, сухогруз, охрана, машина из контейнера."""
    w = m.w
    ms = m.ms
    c = w.city
    pl = w.player
    lm = c.landmarks
    boss = lm['boss']
    addr = c.address('boss')
    sh = c.special['ship']
    door = ms.ship_door
    bruce_look = person_look('bruce')
    if ms.ckpt.get('s2', 0) < 1:
        yield from phone_call(m, 'bruce', [('Брюс', 'Братан, приезжай сюда: %s. Познакомлю с боссом.' % addr)])
        w.hud.mission_title(m.spec['title'])
        room = w.interiors.rooms['boss']
        yield from m.goto(room.out[0], room.out[1] - 0.9, 1.6, 'Езжай в казино: %s.' % addr, on_foot=True,
                          tex='blip_boss')
        yield from boss_scene(m, bruce_look, [
            ('Брюс', 'Босс, это мой брат Макс.'),
            ('Босс', 'Эй, знаете этот грузовой корабль?'),
            ('Макс и Брюс', 'Да?'),
            ('Босс', 'Его владелец задолжал мне лям. Проберитесь на корабль, кокните охрану '
                     'и найдите жёлтый контейнер.'),
            ('Босс', 'Вот этим ключом откроете. Внутри будет тачка. Не смейте её поцарапать — '
                     'она стоит больше вашей жизни!'),
        ])
        ms.ckpt['s2'] = 1
    else:
        yield from phone_call(m, 'bruce', [('Брюс', 'Братан, я у казино. Корабль сам себя не обчистит.')], ring=1.8)
        w.hud.mission_title(m.spec['title'])
        room = w.interiors.rooms['boss']
        yield from m.goto(room.out[0], room.out[1] - 2.2, 4.0, 'Забери Брюса у казино: %s.' % addr, tex='blip_boss',
                          stopped=True)
    # Брюс идёт с нами
    px, py = pl.pos()
    bx, by = ms.free_spot(px + 1.4, py - 0.6)
    bruce = m.npc(bx, by, pl.ped.yaw, bruce_look, hp=450.0)
    m.watch(bruce, 'Брюс погиб.')
    buddy = Buddy(m, bruce)
    if W_SILENCED not in pl.ammo:
        pl.give_weapon(W_SILENCED, 51)
    pl.select(W_SILENCED)
    m.help('У тебя ключ от контейнера и пистолет с глушителем: его выстрелов охрана не слышит. '
           'Часовые смотрят перед собой — заходи со спины.', 11.0)
    # сухогруз
    door.set_open(False, instant=True)
    cx, cy_, cyaw = sh['yellow_car']
    car = m.car('sports', cx, cy_, cyaw, paint=0, clear=0.0)
    car.locked = True
    m.watch(car, 'Машина уничтожена. Босс вас закопает.')
    guards = ship_guards(m)
    fx, fy = sh['stairs_foot']
    while True:
        yield from m.goto(fx, fy, 6.0, 'Отправляйтесь с Брюсом в порт, к сухогрузу.', stopped=False, tex='blip_ship')
        if buddy.near(40.0):
            break
        m.obj('Вернись за Брюсом.')
        b = m.blip(obj=bruce, tex='blip_friend')
        yield lambda: buddy.near(12.0)
        m.unblip(b)
    lx0, ly0, lx1, ly1 = sh['landing']
    yield from m.goto((lx0 + lx1) * 0.5, sh['y0'] + 1.6, 2.2, 'Поднимитесь на корабль по трапу.', on_foot=True)
    yield from m.kill_all(guards, 'Уберите охрану.', 'Охрана')
    dx, dy = sh['yellow_door']
    yield from m.goto(dx - 1.5, dy, 1.5, 'Открой жёлтый контейнер ключом босса.', on_foot=True)
    door.set_open(True)
    w.audio.play('garage', 0.8)
    car.locked = False
    yield 1.3
    # машина босса: возим аккуратно
    limit = 0.55

    def care(dt):
        frac = max(0.0, car.health / car.max_health)
        col = (0.42, 0.74, 0.38) if frac > 0.85 else ((0.96, 0.74, 0.18) if frac > 0.68 else (0.86, 0.26, 0.22))
        w.hud.set_task_bar('Состояние машины', (frac - limit) / (1.0 - limit), col)
        if frac < limit:
            m.fail('Машина разбита. Босс вам этого не простит.')
    m.ticks.append(care)
    yield from m.enter(car, 'Садитесь в машину.')
    yield lambda: buddy.riding() or not buddy.near(60.0)
    px_, py_ = boss['park']
    while True:
        yield from m.drive(car, px_, py_, 4.5, 'Отвезите машину боссу: %s. Не поцарапайте!' % addr, tex='blip_boss')
        if buddy.riding() or buddy.near(14.0):
            break
        m.obj('Вернись за Брюсом.')
        b = m.blip(obj=bruce, tex='blip_friend')
        yield lambda: buddy.near(10.0)
        m.unblip(b)
    m.ticks.remove(care)
    w.hud.set_task_bar(None)
    m.unwatch(car)
    m.unwatch(bruce)
    buddy.stop()
    scratched = car.health < car.max_health * 0.97
    pl.leave_vehicle(force=True)
    car.locked = True
    if bruce.vehicle is not None:
        m.unboard(bruce, walk_to=boss['door'])
    m.say('Босс: Целая. Значит, головы у вас пока на месте.' if not scratched else
          'Босс: Царапина. Вычту из вашей доли в следующий раз.', 4.5)
    yield 1.8
