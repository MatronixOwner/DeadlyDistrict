# -*- coding: utf-8 -*-
"""Бот для автоматического прохождения заданий (телепортируется к целям)."""
import math

from game.vehicle import Vehicle


class Bot(object):

    def __init__(self, g, verbose=True):
        self.g = g
        self.w = g.world
        self.verbose = verbose
        self.last_obj = None
        self.cool = 0.0
        self.log = []

    def say(self, *a):
        if self.verbose:
            print('   bot:', *a)

    def move_player(self, x, y):
        w = self.w
        pl = w.player
        v = pl.vehicle
        if v is not None:
            v.x, v.y = x, y
            v.vx = v.vy = 0.0
            v.speed = 0.0
            v.z = w.city.ground_z(x, y)
            v.sync()
        else:
            p = pl.ped
            p.x, p.y = x, y
            p.z = w.city.ground_z(x, y)
            pl.mvx = pl.mvy = 0.0

    def step(self, dt):
        """Один шаг логики бота.  Вызывать перед g.step()."""
        g, w = self.g, self.w
        ms = w.missions
        m = ms.active
        pl = w.player
        inp = g.inp
        self.cool -= dt
        if m is None:
            return
        if m.objective != self.last_obj:
            self.last_obj = m.objective
            self.log.append(m.objective)
            self.say('objective:', m.objective)
        if pl.freeze:
            # брифинг: пропускаем
            if self.cool <= 0.0:
                inp._dn('enter')
                self.cool = 0.5
            else:
                inp._up('enter')
            return
        inp._up('enter')
        if self.cool > 0.0:
            return
        if w.police.level > 0 and w.police.locked is None and not m.markers:
            w.police.clear()
            self.say('cleared wanted')
        if 'патрульную' in m.objective and (pl.vehicle is None or pl.vehicle.kind != 'police'):
            v = w.spawn_vehicle('police', pl.ped.x + 3.0, pl.ped.y, 0.0)
            pl.enter_side = -1
            pl.enter_vehicle(v, silent=True)
            self.say('took a police car')
            self.cool = 0.3
            return
        # сюжет: надо просто оказаться за рулём любой машины (спутник сядет рядом сам)
        if ('Садитесь с Брюсом в машину' in m.objective or 'Вернись за Брюсом' in m.objective or
                ('Брюс' in m.objective and 'порт' in m.objective)) and pl.vehicle is None and not m.arrows:
            v = w.spawn_vehicle('sedan', pl.ped.x + 3.0, pl.ped.y, 0.0)
            pl.enter_side = -1
            pl.enter_vehicle(v, silent=True)
            self.say('took a car')
            self.cool = 0.3
            return
        # спутник: бот не ждёт, пока тот добежит до двери, — сажает его в машину сразу
        for f in m.ticks:
            b = getattr(f, '__self__', None)
            if b is not None and b.__class__.__name__ == 'Buddy' and b.active and not b.p.dead:
                v = pl.vehicle
                if v is not None and b.p.vehicle is None and v.spec.seats > 1:
                    w.put_in_vehicle(b.p, v)
                    del b.trail[:]
                elif v is None and b.p.vehicle is None and math.hypot(b.p.x - pl.ped.x, b.p.y - pl.ped.y) > 6.0:
                    b._jump_near(pl.ped.x, pl.ped.y)
        # спутник отстал: ждём его рядом
        for b in list(m.blips):
            o = b.obj
            if o is not None and b.tex == 'blip_friend' and not isinstance(o, Vehicle) and o.vehicle is None:
                self.move_player(o.x + 2.5, o.y)
                self.cool = 0.6
                return
        # цель-машина, в которую надо сесть
        for a in m.arrows:
            o = a.obj
            if isinstance(o, Vehicle) and pl.vehicle is not o and not o.dead and o.owner != 'gang' and o.npc is False:
                if pl.vehicle is not None:
                    pl.leave_vehicle(force=True)
                x, y = o.door_pos(-1)
                self.move_player(x - 0.3, y)
                pl.enter_side = -1
                pl.enter_vehicle(o, silent=True)
                self.say('entered', o.kind)
                self.cool = 0.3
                return
        # враги
        for b in list(m.blips):
            o = b.obj
            if o is None or b.tex != 'blip_enemy':
                continue
            if isinstance(o, Vehicle):
                if not o.dead:
                    o.explode(True)
                    self.say('destroyed', o.kind)
                    self.cool = 0.4
                    return
            elif not o.dead:
                o.hurt(1000.0, pl.ped, 'bullet')
                self.say('killed', o.kind)
                self.cool = 0.2
                return
        # предметы
        for pk in m.pickups:
            if not pk.removed:
                if pl.vehicle is not None:
                    pl.leave_vehicle(force=True)
                self.move_player(pk.x, pk.y)
                self.say('pickup at %.0f,%.0f' % (pk.x, pk.y))
                self.cool = 0.2
                return
        # маркер
        for mk in m.markers:
            if mk.need_foot and pl.vehicle is not None:
                pl.leave_vehicle(force=True)
            if not mk.player_inside():
                self.move_player(mk.x, mk.y)
                self.say('to marker %.0f,%.0f' % (mk.x, mk.y))
                self.cool = 0.4
                return
        # пассажир ждёт у обочины (такси)
        for a in m.arrows:
            o = a.obj
            if o is not None and not isinstance(o, Vehicle) and pl.vehicle is not None:
                if math.hypot(o.x - pl.vehicle.x, o.y - pl.vehicle.y) > 7.0:
                    self.move_player(o.x + 3.5, o.y)
                    self.cool = 0.4
                    return
