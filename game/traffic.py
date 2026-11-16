# -*- coding: utf-8 -*-
"""Уличное движение: появление машин, ИИ водителей, припаркованный транспорт."""
import math
import random

from .vehicle import Vehicle, SPECS, ZONE_CARS
from .roadnet import OPP, LEFT_OF
from .mathutil import clamp, angle_diff
from .settings import TRAFFIC_LEVELS

SPAWN_MIN = 72.0
SPAWN_MAX = 135.0
DESPAWN = 165.0
PARK_MAX = 22
PARK_KINDS = ['sedan', 'hatch', 'suv', 'muscle', 'beater', 'pickup', 'van', 'sports', 'lowrider']
ZONE_PARKED = {
    'D': ['sedan', 'sedan', 'suv', 'sports', 'hatch', 'taxi'],
    'O': ['sedan', 'hatch', 'hatch', 'beater', 'van', 'muscle'],
    'G': ['beater', 'beater', 'lowrider', 'pickup', 'hatch'],
    'R': ['sedan', 'suv', 'suv', 'hatch', 'muscle', 'sports'],
    'I': ['pickup', 'van', 'beater', 'truck', 'sedan'],
    'B': ['sports', 'sedan', 'muscle', 'suv', 'hatch', 'lowrider'],
}


def pick_weighted(table):
    total = 0.0
    for _, w in table:
        total += w
    r = random.random() * total
    for k, w in table:
        r -= w
        if r <= 0.0:
            return k
    return table[-1][0]


class Traffic(object):

    def __init__(self, world):
        self.w = world
        self.rn = world.roadnet
        lv = TRAFFIC_LEVELS[int(clamp(world.settings.get('traffic'), 0, 2))]
        self.max_cars = lv[0]
        self.density = 1.0
        self.enabled = True
        self.spawn_t = 0.0
        self.park_t = 0.0
        self.parked = {}            # индекс места -> Vehicle
        self.spot_block = {}        # индекс места -> время, до которого место пустует
        self.seed = random.randrange(1 << 30)
        self.driver = LaneDriver(self)
        self.n_traffic = 0

    # ------------------------------------------------------------------
    def update(self, dt):
        w = self.w
        px, py = w.player.pos()
        n = 0
        for v in w.vehicles:
            if v.traffic and not v.dead:
                n += 1
            if v.npc and v.mode == Vehicle.RAIL:
                v.ai_t -= dt
                if v.ai_t <= 0.0:
                    self._think(v, 0.14)
                    v.ai_t = 0.11 + random.random() * 0.06
        self.n_traffic = n
        if self.enabled:
            self.spawn_t -= dt
            if self.spawn_t <= 0.0:
                self.spawn_t = 0.22
                if n < self.max_cars * self.density:
                    self._spawn(px, py, False)
            self.park_t -= dt
            if self.park_t <= 0.0:
                self.park_t = 0.6
                self._update_parked(px, py, False)
        self._despawn(px, py, dt)

    def populate(self):
        """Заполнить окрестности игрока (при старте игры и после телепортации)."""
        px, py = self.w.player.pos()
        for _ in range(int(self.max_cars * self.density) * 5):
            n = sum(1 for v in self.w.vehicles if v.traffic)
            if n >= self.max_cars * self.density:
                break
            self._spawn(px, py, True)
        self._update_parked(px, py, True)

    # ------------------------------------------------------------------
    def _free(self, x, y, r):
        r2 = r * r
        for v in self.w.vehicles:
            dx, dy = v.x - x, v.y - y
            if dx * dx + dy * dy < r2:
                return False
        return True

    def _spawn(self, px, py, initial):
        w = self.w
        pl = w.player
        # при быстрой езде машины нужны впереди
        fx, fy = pl.velocity()
        cx, cy = px + fx * 2.5, py + fy * 2.5
        lanes = self.rn.lanes_near(cx, cy, 0.0, SPAWN_MAX)
        if not lanes:
            return None
        for _ in range(8):
            lane = lanes[int(random.random() * len(lanes))]
            if lane.length < 16.0:
                continue
            s = random.uniform(5.0, lane.length - 9.0)
            x, y, yaw = lane.pos(s)
            d = math.hypot(x - px, y - py)
            if initial:
                if d < 22.0 or d > SPAWN_MAX:
                    continue
            else:
                if d < SPAWN_MIN or d > SPAWN_MAX:
                    continue
                if d < 112.0 and w.visible(x, y, 3.0):
                    continue
            if not self._free(x, y, 12.0):
                continue
            zone = lane.zone if lane.zone in ZONE_CARS else 'D'
            kind = pick_weighted(ZONE_CARS[zone])
            v = w.spawn_vehicle(kind, x, y, yaw)
            v.npc = True
            v.traffic = True
            v.mode = Vehicle.RAIL
            v.link = lane
            v.s = s
            if v.spec.bike:
                from .defs import random_look
                look = random_look(random, zone if len(zone) == 1 else 'D')
                look.female = False if kind == 'chopper' else look.female
                v.add_rider(look)
            v.persona = random.uniform(0.8, 1.08)
            v.speed = lane.speed * 0.7
            v.target_speed = v.speed
            if w.sky is not None and w.sky.lights_on:
                v.set_lights(True)
            return v
        return None

    def spawn_on_lane(self, kind, lane, s, **kw):
        x, y, yaw = lane.pos(s)
        v = self.w.spawn_vehicle(kind, x, y, yaw, kw.get('paint'))
        v.npc = True
        v.mode = Vehicle.RAIL
        v.link = lane
        v.s = s
        v.persona = kw.get('persona', 1.0)
        v.speed = v.target_speed = lane.speed * 0.6
        return v

    def _despawn(self, px, py, dt):
        w = self.w
        for v in w.vehicles:
            if v.keep or v.is_player or v.removed:
                continue
            dx, dy = v.x - px, v.y - py
            d2 = dx * dx + dy * dy
            if v.mode == Vehicle.PARKED and not v.dead and v.spot is not None:
                continue                # припаркованными занимается _update_parked
            if d2 > DESPAWN * DESPAWN:
                w.remove_vehicle(v)
                continue
            if d2 > 60.0 * 60.0:
                if w.visible(v.x, v.y, 4.0):
                    v.unseen_t = 0.0
                else:
                    v.unseen_t += dt
                    lim = 6.0 if (v.traffic and not v.dead) else 14.0
                    if v.unseen_t > lim:
                        w.remove_vehicle(v)
            elif v.dead and v.burning <= 0.0 and v.age > 90.0 and not w.visible(v.x, v.y, 4.0):
                w.remove_vehicle(v)

    # ------------------------------------------------------------------
    def _spot_kind(self, idx, spot):
        r = random.Random(self.seed * 7919 + idx)
        if r.random() > 0.5 and spot.get('kind') is None:
            return None
        k = spot.get('kind')
        if k is not None:
            if r.random() > 0.85:
                return None
            return k if k in SPECS else 'sedan'
        pool = ZONE_PARKED.get(self.w.city.zone_style(spot.get('zone') or 'D'), PARK_KINDS)
        return pool[int(r.random() * len(pool))]

    def _update_parked(self, px, py, initial):
        w = self.w
        now = w.time
        spots = w.city.parking
        for idx in list(self.parked.keys()):
            v = self.parked[idx]
            s = spots[idx]
            moved = v.removed or v.mode != Vehicle.PARKED or v.dead or v.is_player
            if moved:
                del self.parked[idx]
                self.spot_block[idx] = now + 240.0
                if not v.removed:
                    v.spot = None
                continue
            dx, dy = s['x'] - px, s['y'] - py
            if dx * dx + dy * dy > 185.0 * 185.0 and not v.keep:
                del self.parked[idx]
                w.remove_vehicle(v)
        if len(self.parked) >= PARK_MAX:
            return
        r_in = 0.0 if initial else 55.0
        for idx, s in enumerate(spots):
            dx, dy = s['x'] - px, s['y'] - py
            d2 = dx * dx + dy * dy
            if d2 > 150.0 * 150.0 or d2 < r_in * r_in or idx in self.parked:
                continue
            if self.spot_block.get(idx, 0.0) > now:
                continue
            kind = self._spot_kind(idx, s)
            if kind is None:
                continue
            if not initial and d2 < 100.0 * 100.0 and w.visible(s['x'], s['y'], 4.0):
                continue
            if not self._free(s['x'], s['y'], 4.2):
                continue
            v = w.spawn_vehicle(kind, s['x'], s['y'], s['yaw'])
            v.mode = Vehicle.PARKED
            v.spot = idx
            self.parked[idx] = v
            if len(self.parked) >= PARK_MAX:
                break

    # ------------------------------------------------------------------
    # ИИ водителя на «рельсах»
    # ------------------------------------------------------------------
    def probe(self, v, look, narrow=False):
        """Расстояние до препятствия впереди: (gap, скорость препятствия, объект)."""
        w = self.w
        fx, fy = math.cos(v.yaw), math.sin(v.yaw)
        hl = v.spec.L * 0.5
        hw = v.spec.W * 0.5
        best = look
        bspeed = 0.0
        bobj = None
        reach = look + 14.0
        x, y = v.x, v.y
        ghost = v.ghost if v.ghost_t > 0.0 else None
        for o in w.vehicles:
            if o is v or o is ghost:
                continue
            dx = o.x - x
            if dx > reach or dx < -reach:
                continue
            dy = o.y - y
            if dy > reach or dy < -reach:
                continue
            f = dx * fx + dy * fy
            if f <= 0.0:
                continue
            l = dy * fx - dx * fy
            c = abs(math.cos(o.yaw - v.yaw))
            s = abs(math.sin(o.yaw - v.yaw))
            ol, ow = o.spec.L * 0.5, o.spec.W * 0.5
            half_w = c * ow + s * ol
            half_l = c * ol + s * ow
            lim = hw + half_w + (0.1 if narrow else 0.3)
            if l > lim or l < -lim:
                continue
            gap = f - hl - half_l
            if gap < best:
                best = gap
                bobj = o
                bspeed = (o.vx * fx + o.vy * fy)
        # люди на проезжей части
        plim = hw + 0.55
        pr = min(look, 16.0)
        for p in w.peds:
            if p.z > 0.09 or p.vehicle is not None or p.state == 'dead':
                continue
            dx = p.x - x
            if dx > pr + 4 or dx < -pr - 4:
                continue
            dy = p.y - y
            if dy > pr + 4 or dy < -pr - 4:
                continue
            f = dx * fx + dy * fy
            if f <= hl * 0.5 or f > pr + hl:
                continue
            l = dy * fx - dx * fy
            lim = plim + 1.5 if p.crossing else plim
            if l > lim or l < -lim:
                continue
            gap = f - hl - 0.6
            if gap < best:
                best = gap
                bobj = p
                bspeed = 0.0
        return best, bspeed, bobj

    def _oncoming(self, v, link):
        node = link.node
        d = link.dir
        opp = OPP[d]
        left = LEFT_OF[d]
        for o in self.w.vehicles:
            if o is v or o.mode != Vehicle.RAIL:
                continue
            ol = o.link
            if ol is None or ol.node != node:
                continue
            if ol.turn is None:
                if ol.dir == opp and (ol.length - o.s) < 24.0 and o.speed > 2.0:
                    return True
            elif (ol.turn == 'S' and ol.dir == opp) or (ol.turn == 'R' and ol.dir == left):
                return True
        return False

    def _think(self, v, dt):
        link = v.link
        des = link.speed * v.persona
        hl = v.spec.L * 0.5
        remain = link.length - v.s
        signal_wait = False
        if link.turn is None:
            nl = v.next_link
            if nl is None or nl not in link.next:
                nl = link.next[int(random.random() * len(link.next))] if link.next else None
                v.next_link = nl
            if nl is not None and nl.turn != 'S':
                vt = nl.speed
                lim = math.sqrt(vt * vt + 2.0 * 2.6 * max(0.0, remain - 1.0))
                if lim < des:
                    des = lim
            if link.signal and not v.rush:
                st = self.rn.light(link.node, link.axis)
                stop_d = remain - 3.2 - hl
                must = False
                if st == 'r':
                    must = stop_d > -2.0
                elif st == 'y':
                    must = stop_d > v.speed * v.speed / 11.0
                elif nl is not None and nl.turn == 'L' and -1.0 < stop_d < 12.0 and v.block_t < 6.0:
                    must = self._oncoming(v, link)
                if must:
                    signal_wait = True
                    lim = math.sqrt(2.0 * 4.0 * stop_d) if stop_d > 0.25 else 0.0
                    if lim < des:
                        des = lim
            look = max(9.0, v.speed * 2.3 + 7.0)
            narrow = False
        else:
            look = 6.5 if link.turn != 'S' else max(9.0, v.speed * 2.0 + 6.0)
            narrow = link.turn != 'S'
        gap, ospeed, obj = self.probe(v, look, narrow)
        blocked = False
        if gap < look:
            if gap < 2.2:
                des = 0.0
                blocked = True
            else:
                lim = math.sqrt(2.0 * 4.5 * (gap - 2.2)) + max(0.0, ospeed) * 0.8
                if lim < des:
                    des = lim
        if des < 0.4 and v.speed < 0.4:
            if blocked or signal_wait and st == 'g':
                v.block_t += dt
                # сигналим тому, кто мешает
                if v.block_t > 2.5 and v.honk_cd <= 0.0 and blocked:
                    w = self.w
                    is_pl = obj is not None and (getattr(obj, 'is_player', False))
                    if is_pl or random.random() < 0.15:
                        w.audio.play_at('horn_truck' if v.spec.engine == 'truck' else 'horn', v.x, v.y, 0.7,
                                        0.92 + (id(v) % 7) * 0.03, 70.0)
                        v.honk_cd = 2.0 + random.random() * 4.0
                if blocked and obj is not None and not getattr(obj, 'is_player', False):
                    # взаимная блокировка на перекрёстке: один из двоих «просачивается»
                    if (v.block_t > 3.0 + (id(v) >> 4) % 5 and hasattr(obj, 'spec') and obj.mode == Vehicle.RAIL
                            and obj.speed < 0.5 and obj.npc):
                        v.ghost = obj
                        v.ghost_t = 3.0
                        v.block_t = 0.0
                    # затор: если совсем не вышло — исчезаем, когда никто не видит
                    elif v.block_t > 22.0 and not self.w.visible(v.x, v.y, 4.0):
                        self.w.remove_vehicle(v)
                        return
        else:
            v.block_t = max(0.0, v.block_t - dt * 2.0)
        if v.honk_cd > 0.0:
            v.honk_cd -= dt
        if v.ghost_t > 0.0:
            v.ghost_t -= dt
            if v.ghost_t <= 0.0:
                v.ghost = None
        v.target_speed = des
        v.set_brake_light(des < v.speed - 0.5 or (des < 0.3 and v.speed < 1.0))

    # ------------------------------------------------------------------
    def knock(self, v, impulse, by=None):
        """Машину на «рельсах» сильно толкнули: переводим в физический режим."""
        if v.mode != Vehicle.RAIL:
            return
        v.set_mode(Vehicle.PHYS)
        v.ai = self.driver
        v.recover_t = 1.5 + random.random() * 2.0
        v.stuck_t = 0.0
        if by is not None and getattr(by, 'is_player', False) and impulse > 5.0 and random.random() < 0.45:
            v.panic_t = 14.0

    def scare(self, v, duration=12.0):
        """Водитель в панике: давит на газ и уносится прочь."""
        if not v.npc or v.dead or v.panic_t > 0.0:
            return
        if v.mode == Vehicle.RAIL:
            v.set_mode(Vehicle.PHYS)
            v.ai = self.driver
            v.recover_t = 0.0
        v.panic_t = duration

    def route_step(self, v, goal):
        """Выбрать поворот на ближайшем перекрёстке так, чтобы ехать к перекрёстку goal=(i, j)."""
        link = v.link
        if link is None or link.turn is not None or v._route_link is link:
            return
        v._route_link = link
        best = None
        bn = 1 << 30
        for t in link.next:
            if not t.next:
                continue
            path = self.rn.route(t.next[0].node, goal)
            n = len(path) if path else 1 << 20
            if t.turn == 'S':
                n -= 0.5                  # при равных — прямо
            if n < bn:
                bn = n
                best = t
        if best is not None:
            v.next_link = best

    def take_over(self, v):
        """Подготовить машину трафика к угону/миссии: убрать с «рельс»."""
        if v.mode == Vehicle.RAIL:
            v.set_mode(Vehicle.PHYS)
        v.ai = None
        v.npc = False
        v.traffic = False
        v.panic_t = 0.0
        v.in_throttle = v.in_steer = 0.0
        v.in_brake = 0.0


class LaneDriver(object):
    """Водитель в физическом режиме: держит полосу методом «преследования точки»."""

    def __init__(self, traffic):
        self.t = traffic

    def point_ahead(self, v, dist):
        link = v.link
        s = v.s + dist
        guard = 0
        nl = v.next_link
        while s > link.length and guard < 3:
            guard += 1
            if not link.next:
                s = link.length
                break
            s -= link.length
            if nl is None or nl not in link.next:
                nl = link.next[0]
            link = nl
            nl = None
        return link.pos(s)

    def advance(self, v):
        """Обновить положение вдоль полосы по фактическим координатам."""
        link = v.link
        x, y, yaw = link.pos(v.s)
        ds = (v.x - x) * math.cos(yaw) + (v.y - y) * math.sin(yaw)
        v.s += clamp(ds, -3.0, 6.0)
        if v.s < 0.0:
            v.s = 0.0
        while v.s >= link.length:
            if not link.next:
                v.s = link.length
                break
            v.s -= link.length
            nl = v.next_link
            if nl is None or nl not in link.next:
                nl = link.next[int(random.random() * len(link.next))]
            v.next_link = None
            link = nl
            v.link = link
            if link.turn is None and link.next:
                v.next_link = link.next[int(random.random() * len(link.next))]
        return link

    def drive(self, v, dt):
        if v.recover_t > 0.0:
            v.recover_t -= dt
            v.in_throttle = 0.0
            v.in_brake = 1.0
            v.in_steer = 0.0
            return
        if v.link is None:
            lane, s, d = self.t.rn.nearest_lane(v.x, v.y, 80.0)
            if lane is None:
                v.in_throttle = 0.0
                v.in_brake = 1.0
                return
            v.link, v.s = lane, s
        link = self.advance(v)
        panic = v.panic_t > 0.0
        if panic:
            v.panic_t -= dt
        sp = abs(v.speed)
        la = max(5.5, sp * 0.75 + 3.5)
        tx, ty, tyaw = self.point_ahead(v, la)
        want = math.atan2(ty - v.y, tx - v.x)
        err = angle_diff(want, v.yaw)
        # застряли — сдаём назад
        if v.reverse_t > 0.0:
            v.reverse_t -= dt
            v.in_throttle = -0.8
            v.in_brake = 0.0
            v.in_steer = clamp(-err * 2.0, -1.0, 1.0)
            return
        v.in_steer = clamp(err * 2.4, -1.0, 1.0)
        tgt = link.speed * (1.9 if panic else 0.75)
        if abs(err) > 0.35:
            tgt = min(tgt, 6.0 if panic else 4.5)
        v.ai_t -= dt
        if v.ai_t <= 0.0:
            v.ai_t = 0.15
            gap, osp, obj = self.t.probe(v, max(8.0, sp * 1.6 + 5.0))
            v.gap = gap
        gap = v.gap
        if gap < 3.0:
            tgt = 0.0
        elif gap < 30.0:
            tgt = min(tgt, math.sqrt(2.0 * (7.0 if panic else 4.5) * (gap - 2.5)) + 1.0)
        if sp < tgt - 0.5:
            v.in_throttle = clamp((tgt - sp) / 3.0, 0.25, 1.0)
            v.in_brake = 0.0
        elif sp > tgt + 1.0:
            v.in_throttle = 0.0
            v.in_brake = clamp((sp - tgt) / 4.0, 0.2, 1.0)
        else:
            v.in_throttle = 0.15
            v.in_brake = 0.0
        if v.speed < -0.5 and tgt > 0.5:
            v.in_throttle = 1.0
        # застревание
        if sp < 0.6 and tgt > 1.0:
            v.stuck_t += dt
            if v.stuck_t > 1.6:
                v.stuck_t = 0.0
                v.reverse_t = 1.3
        else:
            v.stuck_t = max(0.0, v.stuck_t - dt)
        # вернулись в полосу — снова на «рельсы»
        if not panic and v.npc:
            x, y, yaw = link.pos(v.s)
            if (abs(v.x - x) + abs(v.y - y) < 0.8 and abs(angle_diff(yaw, v.yaw)) < 0.16 and
                    abs(v.slip) < 0.6 and sp < link.speed * 1.2):
                v.set_mode(Vehicle.RAIL)
                v.ai = None
                v.speed = sp
                v.target_speed = sp
                v.in_throttle = v.in_brake = v.in_steer = 0.0
