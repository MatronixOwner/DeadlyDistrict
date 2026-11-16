# -*- coding: utf-8 -*-
"""Розыск и полиция: звёзды, патрули, погони, арест."""
import math
import random

from .vehicle import Vehicle
from .defs import cop_look, swat_look, fbi_look, army_look, W_BAT, W_PISTOL, W_UZI, W_AK, W_SHOTGUN, W_FIST
from .mathutil import clamp, angle_diff
from .collision import F_CAR

THRESH = [0, 20, 70, 170, 340, 620, 1000]          # очки «хаоса» для 1..6 звёзд
MAX_UNITS = [0, 1, 2, 3, 3, 4, 4]
SPAWN_GAP = [0, 9.0, 7.0, 5.5, 5.0, 4.0, 3.5]
CRIMES = {
    'assault': 6, 'gunfire': 4, 'carjack': 14, 'hit_ped': 12, 'kill': 30, 'kill_cop': 90, 'assault_cop': 45,
    'destroy': 30, 'explosion': 45, 'ram_cop': 22, 'shoot_car': 5,
}
CRIME_TEXT = {
    'kill': 'убийство', 'kill_cop': 'убийство полицейского', 'carjack': 'угон', 'destroy': 'уничтожение имущества',
    'explosion': 'взрыв', 'assault_cop': 'нападение на полицейского',
}


class Police(object):

    def __init__(self, world):
        self.w = world
        self.level = 0
        self.heat = 0.0
        self.cool_t = 0.0             # сколько секунд игрока не видят
        self.seen = False
        self.spawn_t = 3.0
        self.units = []               # машины погони
        self.cops = []                # пешие преследователи
        self.driver = ChaseDriver(self)
        self.max_level = 6
        self.enabled = True
        self.scan_t = 0.0
        self.bust_t = 0.0
        self.gun_cd = 0.0
        self.flash = 0.0
        self.last_seen = (0.0, 0.0)
        self.stars_evaded = 0
        self.locked = None            # миссия может зафиксировать минимальный уровень

    # ------------------------------------------------------------------
    def crime(self, kind, x=None, y=None, mult=1.0):
        if not self.enabled:
            return
        w = self.w
        pts = CRIMES.get(kind, 5) * mult
        if kind == 'gunfire':
            if self.gun_cd > 0.0:
                return
            self.gun_cd = 0.8
            # стрельба в безлюдном месте остаётся незамеченной
            if self.level == 0 and not self._witness(x, y, 55.0):
                return
        elif kind in ('assault', 'carjack', 'shoot_car') and self.level == 0:
            if not self._witness(x, y, 40.0) and random.random() < 0.6:
                return
        self.heat = min(THRESH[6] + 100.0, self.heat + pts)
        if kind in ('kill_cop', 'assault_cop', 'ram_cop') and self.heat < THRESH[2]:
            self.heat = float(THRESH[2])
        self._recalc()
        self.cool_t = 0.0

    def _witness(self, x, y, r):
        if x is None:
            return True
        r2 = r * r
        for p in self.w.peds:
            if p.is_player or p.dead:
                continue
            dx, dy = p.x - x, p.y - y
            if dx * dx + dy * dy < r2:
                return True
        return False

    def _recalc(self):
        lv = 0
        for i in range(1, 7):
            if self.heat >= THRESH[i]:
                lv = i
        lv = min(lv, self.max_level)
        if self.locked is not None and lv < self.locked:
            lv = self.locked
        if lv != self.level:
            self.set_level(lv, keep_heat=True)

    def set_level(self, lv, keep_heat=False):
        lv = int(clamp(lv, 0, 6))
        old = self.level
        self.level = lv
        if not keep_heat:
            self.heat = float(THRESH[lv]) + (5.0 if lv else 0.0)
        self.cool_t = 0.0
        w = self.w
        if lv != old:
            w.hud.wanted_changed(lv, old)
            if lv > old:
                self.flash = 2.0
                self.spawn_t = min(self.spawn_t, 1.5)
            self._arm_cops()
        if lv == 0:
            self.heat = 0.0
            self.stand_down()

    def clear(self):
        self.locked = None
        self.set_level(0)

    def _arm_cops(self):
        for p in self.w.peds:
            if p.kind == 'cop' and not p.dead:
                want = W_BAT if self.level <= 1 else W_PISTOL
                if p.weapon.id != want:
                    p.set_weapon(want)

    def stand_down(self):
        """Розыск снят: погоня прекращается."""
        w = self.w
        for v in self.units:
            if v.removed or v.dead:
                continue
            v.siren = False
            v.keep = False
            # возвращаемся к обычному патрулированию
            lane, s, d = w.roadnet.nearest_lane(v.x, v.y, 60.0)
            if lane is not None:
                v.link, v.s = lane, s
                v.next_link = None
                v.ai = w.traffic.driver
                v.traffic = True
                v.npc = True
                v.panic_t = 0.0
                v.recover_t = 0.5
            else:
                v.ai = None
        self.units = []
        for p in self.cops:
            if p.removed or p.dead:
                continue
            p.target = None
            p.keep = False
            p.aiming = False
            if p.kind == 'cop':
                p.start_walk()
            else:
                p.spawned = True
                p.start_walk()
        self.cops = []
        for p in w.peds:
            if p.kind == 'cop' and p.target is w.player.ped:
                p.target = None
                p.aiming = False
                p.start_walk()

    # ------------------------------------------------------------------
    def update(self, dt):
        w = self.w
        pl = w.player
        if self.gun_cd > 0.0:
            self.gun_cd -= dt
        if self.flash > 0.0:
            self.flash -= dt
        if self.level <= 0 or pl.state in ('dead', 'busted'):
            self.bust_t = 0.0
            return
        px, py = pl.pos()
        self.scan_t -= dt
        if self.scan_t <= 0.0:
            self.scan_t = 0.35
            self._scan(px, py)
        if self.seen:
            self.cool_t = 0.0
            self.last_seen = (px, py)
        else:
            self.cool_t += dt
            lim = 16.0 + 10.0 * self.level
            if self.cool_t > lim:
                # ушёл от погони: минус звезда
                self.stars_evaded += 1
                new = self.level - 1
                if self.locked is not None and new < self.locked:
                    new = self.locked
                    self.cool_t = 0.0
                else:
                    self.set_level(new)
                    if new == 0:
                        w.on_wanted_cleared()
        if self.level <= 0:
            return
        self._update_units(dt, px, py)
        self._check_bust(dt, px, py)
        # вызываем подкрепление
        self.spawn_t -= dt
        if self.spawn_t <= 0.0:
            self.spawn_t = SPAWN_GAP[self.level] * (0.8 + random.random() * 0.5)
            alive = [v for v in self.units if not v.removed and not v.dead]
            if len(alive) < MAX_UNITS[self.level] and self.cool_t < 6.0 + 4.0 * self.level:
                self._spawn_unit(px, py)

    def _scan(self, px, py):
        """Видит ли игрока кто-нибудь из полиции; поднимаем по тревоге патрульных."""
        w = self.w
        pp = w.player.ped
        seen = False
        st = w.static
        for p in w.peds:
            if p.dead or p.removed or p.kind not in ('cop', 'swat', 'fbi', 'army'):
                continue
            dx, dy = p.x - px, p.y - py
            d2 = dx * dx + dy * dy
            if d2 > 70.0 * 70.0:
                continue
            if d2 < 12.0 * 12.0 or st.los(p.x, p.y, px, py, p.z + 1.4):
                seen = True
                if p.target is not pp and p.vehicle is None and p.state not in ('down', 'in_car'):
                    p.attack(pp)
                    if p not in self.cops:
                        p.keep = True
                        self.cops.append(p)
                        want = W_BAT if self.level <= 1 else W_PISTOL
                        if p.kind == 'cop' and p.weapon.id != want:
                            p.set_weapon(want)
        for v in self.units:
            if v.removed or v.dead:
                continue
            dx, dy = v.x - px, v.y - py
            d2 = dx * dx + dy * dy
            if d2 < 25.0 * 25.0 or (d2 < 90.0 * 90.0 and st.los(v.x, v.y, px, py)):
                seen = True
        # обычные патрульные машины в трафике тоже включаются в погоню
        if len([u for u in self.units if not u.removed and not u.dead]) < MAX_UNITS[self.level]:
            for v in w.vehicles:
                if v.kind in ('police', 'copbike') and v.npc and v.traffic and not v.dead and v not in self.units:
                    dx, dy = v.x - px, v.y - py
                    if dx * dx + dy * dy < 60.0 * 60.0:
                        self._make_unit(v)
                        break
        self.seen = seen
        self.units = [v for v in self.units if not v.removed]
        self.cops = [p for p in self.cops if not p.removed and not p.dead]

    # ------------------------------------------------------------------
    def _unit_kind(self):
        lv = self.level
        r = random.random()
        if lv >= 6:
            return 'army' if r < 0.6 else 'enforcer'
        if lv == 5:
            return 'fbi' if r < 0.65 else 'enforcer'
        if lv == 4:
            return 'enforcer' if r < 0.5 else 'police'
        # на первых звёздах в погоню выезжают и мотоциклисты
        return 'copbike' if r < 0.22 else 'police'

    def _make_unit(self, v):
        w = self.w
        if v.mode != Vehicle.PHYS:
            v.set_mode(Vehicle.PHYS)
        v.ai = self.driver
        v.npc = True
        v.traffic = False
        v.keep = True
        v.owner = 'police'
        v.siren = True
        v.crew = 4 if v.kind in ('enforcer', 'army') else (1 if v.spec.bike else 2)
        v.stuck_t = 0.0
        v.reverse_t = 0.0
        v.route_t = 0.0
        v.direct = False
        v.goal = None
        v.pass_t = 0.0
        v.f_c = v.f_l = v.f_r = 99.0
        v.gap = 99.0
        v.gap_side = 0.0
        v._route_link = None
        v.dismount_t = 0.0
        v.recover_t = 0.0
        v.panic_t = 0.0
        v.ref_x, v.ref_y, v.ref_t = v.x, v.y, 0.0
        v.esc_t = 0.0
        v.esc_side = 0.0
        if w.sky is not None and w.sky.lights_on:
            v.set_lights(True)
        self.units.append(v)

    def _spawn_unit(self, px, py):
        w = self.w
        rn = w.roadnet
        vx, vy = w.player.velocity()
        cx, cy = px + vx * 3.0, py + vy * 3.0
        lanes = rn.lanes_near(cx, cy, 0.0, 130.0)
        if not lanes:
            return None
        best = None
        for _ in range(14):
            lane = lanes[int(random.random() * len(lanes))]
            if lane.length < 14.0:
                continue
            s = random.uniform(4.0, lane.length - 8.0)
            x, y, yaw = lane.pos(s)
            d = math.hypot(x - px, y - py)
            if d < 62.0 or d > 135.0:
                continue
            if d < 110.0 and w.visible(x, y, 3.0):
                continue
            if not w.traffic._free(x, y, 10.0):
                continue
            # лучше, если машина уже едет в сторону игрока
            toward = math.cos(yaw) * (px - x) + math.sin(yaw) * (py - y)
            if toward < 0 and random.random() < 0.7:
                continue
            best = (lane, s, x, y, yaw)
            break
        if best is None:
            return None
        lane, s, x, y, yaw = best
        v = w.spawn_vehicle(self._unit_kind(), x, y, yaw)
        if v.spec.bike:
            v.add_rider(cop_look())                 # мотоциклиста видно в седле
        v.link, v.s = lane, s
        v.vx, v.vy = math.cos(yaw) * 10.0, math.sin(yaw) * 10.0
        v.speed = 10.0
        v.mode = Vehicle.PHYS
        self._make_unit(v)
        return v

    def _update_units(self, dt, px, py):
        w = self.w
        pl = w.player
        slow = pl.speed() < 3.5
        for v in self.units:
            if v.removed or v.dead or v.crew <= 0 or v.is_player:
                continue
            dx, dy = v.x - px, v.y - py
            d2 = dx * dx + dy * dy
            if d2 > 190.0 * 190.0:
                v.keep = False
                continue
            # игрок рядом и почти стоит — выходим из машины
            if slow and d2 < 17.0 * 17.0 and abs(v.speed) < 4.0:
                v.dismount_t += dt
                if v.dismount_t > 0.5:
                    self._dismount(v)
            else:
                v.dismount_t = 0.0

    def _dismount(self, v):
        w = self.w
        pp = w.player.ped
        n = v.crew
        v.crew = 0
        v.npc = False
        v.ai = None
        v.in_throttle = 0.0
        v.in_brake = 1.0
        v.keep = False
        kind = v.kind
        if v.rider is not None:                     # с мотоцикла слезает тот, кто на нём сидел
            v.remove_rider()
        for i in range(n):
            side = -1 if i % 2 == 0 else 1
            x, y = v.door_pos(side)
            off = (i // 2) * 1.2
            x -= math.cos(v.yaw) * off
            y -= math.sin(v.yaw) * off
            p = self.make_cop(x, y, v.yaw, kind)
            p.attack(pp)
            p.keep = True
            self.cops.append(p)
        w.audio.play_at('door', v.x, v.y, 0.7)

    def make_cop(self, x, y, yaw, vkind='police'):
        w = self.w
        lv = self.level
        if vkind == 'enforcer':
            p = w.spawn_ped(x, y, yaw, swat_look(), 'swat')
            p.set_weapon(W_UZI)
            p.health = p.max_health = 150.0
            p.armor = 60.0
            p.accuracy = 0.5
        elif vkind == 'fbi':
            p = w.spawn_ped(x, y, yaw, fbi_look(), 'fbi')
            p.set_weapon(W_UZI if random.random() < 0.5 else W_AK)
            p.health = p.max_health = 170.0
            p.armor = 50.0
            p.accuracy = 0.55
        elif vkind == 'army':
            p = w.spawn_ped(x, y, yaw, army_look(), 'army')
            p.set_weapon(W_AK)
            p.health = p.max_health = 200.0
            p.armor = 100.0
            p.accuracy = 0.6
        else:
            p = w.spawn_ped(x, y, yaw, cop_look(), 'cop')
            p.set_weapon(W_BAT if lv <= 1 else (W_SHOTGUN if lv >= 3 and random.random() < 0.3 else W_PISTOL))
            p.health = p.max_health = 120.0
            p.accuracy = 0.4
        p.brave = 1.0
        p.money = 0
        p.run_speed = 6.2
        return p

    def _check_bust(self, dt, px, py):
        """Арест: полицейский вплотную к игроку, который стоит или лежит."""
        w = self.w
        pl = w.player
        if pl.god or (self.level > 3 and pl.ped.state != 'down'):     # god — бессмертие из меню тестера
            self.bust_t = 0.0
            return
        v = pl.vehicle
        if v is not None:
            if math.hypot(v.vx, v.vy) > 2.0:
                self.bust_t = 0.0
                return
            reach = v.spec.W * 0.5 + 1.5
        else:
            if pl.speed() > 3.0 and pl.ped.state != 'down':
                self.bust_t = max(0.0, self.bust_t - dt)
                return
            reach = 1.5
        near = False
        for p in self.cops:
            if p.dead or p.state == 'down':
                continue
            if abs(p.x - px) < reach and abs(p.y - py) < reach and math.hypot(p.x - px, p.y - py) < reach:
                near = True
                break
        if near:
            self.bust_t += dt
            if self.bust_t > (0.9 if v is None else 1.6):
                self.bust_t = 0.0
                w.on_player_busted()
        else:
            self.bust_t = max(0.0, self.bust_t - dt * 0.5)


class ChaseDriver(object):
    """Водитель машины погони.

    Далеко от цели едет по полосам дорожной сети (маршрут — поиском в ширину
    по перекрёсткам), вблизи и при прямой видимости — напрямую на цель.
    """

    def __init__(self, police):
        self.pol = police

    def _acquire_lane(self, v, goal):
        """Подобрать ближайшую полосу, ведущую в сторону цели."""
        w = self.pol.w
        rn = w.roadnet
        best = None
        bscore = 1e9
        bs = 0.0
        for l in rn.lanes_near(v.x, v.y, 0.0, 30.0):
            dx, dy = l.x1 - l.x0, l.y1 - l.y0
            t = ((v.x - l.x0) * dx + (v.y - l.y0) * dy) / (l.length * l.length)
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            px, py = l.x0 + dx * t, l.y0 + dy * t
            d = math.hypot(v.x - px, v.y - py)
            if d > 30.0:
                continue
            path = rn.route(l.node, goal)
            score = d * 0.5 + len(path) * 10.0
            if abs(angle_diff(math.atan2(dy, dx), v.yaw)) > 1.9:
                score += 14.0
            if score < bscore:
                bscore = score
                best = l
                bs = t * l.length
        if best is None:
            best, bs, d = rn.nearest_lane(v.x, v.y, 200.0)
        v.link = best
        v.s = bs
        v.next_link = None
        v._route_link = None

    def drive(self, v, dt):
        w = self.pol.w
        pl = w.player
        tr = w.traffic
        st = w.static
        tx, ty = pl.pos()
        tvx, tvy = pl.velocity()
        dx, dy = tx - v.x, ty - v.y
        d = math.hypot(dx, dy)
        sp = abs(v.speed)
        psp = math.hypot(tvx, tvy)
        fx, fy = math.cos(v.yaw), math.sin(v.yaw)
        look = 6.0 + sp * 0.9
        # --- редкие «дорогие» проверки
        v.route_t -= dt
        if v.route_t <= 0.0:
            v.route_t = 0.35 + random.random() * 0.2
            was = v.direct
            v.direct = d < 20.0 or (d < 70.0 and st.los(v.x, v.y, tx, ty, 0.8))
            gn = w.city.nearest_node(tx, ty)
            goal = (gn.i, gn.j) if gn is not None else None
            if goal != v.goal:
                v.goal = goal
                v._route_link = None
            if not v.direct and (was or v.link is None) and goal is not None:
                self._acquire_lane(v, goal)
        v.ai_t -= dt
        if v.ai_t <= 0.0:
            v.ai_t = 0.1
            ca, sa = 0.906, 0.423                 # «усы» под 25 градусов
            v.f_c = st.raycast2d(v.x, v.y, fx, fy, look, 0.6, F_CAR)
            v.f_l = st.raycast2d(v.x, v.y, fx * ca - fy * sa, fx * sa + fy * ca, look * 0.8, 0.6, F_CAR)
            v.f_r = st.raycast2d(v.x, v.y, fx * ca + fy * sa, -fx * sa + fy * ca, look * 0.8, 0.6, F_CAR)
            gap, osp, obj = tr.probe(v, look + 4.0)
            if obj is not None and not getattr(obj, 'is_player', False) and obj is not pl.vehicle:
                v.gap = gap
                l = (obj.y - v.y) * fx - (obj.x - v.x) * fy
                v.gap_side = -1.0 if l > 0 else 1.0
                if hasattr(obj, 'spec') and gap < 14.0 and v.pass_t <= 0.0:
                    v.pass_t = 2.2                  # идём на обгон
            else:
                v.gap = 99.0
        if v.pass_t > 0.0:
            v.pass_t -= dt
        top = v.spec.top * 0.92
        tgt = top
        # --- куда рулить
        if v.direct or v.link is None:
            lead = clamp(d / max(sp, 8.0), 0.0, 1.2)
            gx, gy = tx + tvx * lead, ty + tvy * lead
            on_lane = False
        else:
            on_lane = True
            link = tr.driver.advance(v)
            if link.turn is None:
                if v.goal is not None and link.node != v.goal:
                    tr.route_step(v, v.goal)
                nl = v.next_link
                if nl is not None and nl.turn != 'S':
                    remain = link.length - v.s
                    vt = 7.0 if nl.turn == 'R' else 9.0
                    tgt = min(tgt, math.sqrt(vt * vt + 2.0 * 5.0 * max(0.0, remain - 2.0)))
            elif link.turn != 'S':
                tgt = min(tgt, 8.0 if link.turn == 'R' else 10.0)
            la = max(6.0, sp * 0.7 + 4.0)
            gx, gy, gyaw = tr.driver.point_ahead(v, la)
            if v.pass_t > 0.0 and link.turn is None:
                # смещаемся влево для обгона
                gx -= math.sin(gyaw) * 3.3
                gy += math.cos(gyaw) * 3.3
        want = math.atan2(gy - v.y, gx - v.x)
        err = angle_diff(want, v.yaw)
        # --- задний ход, если застряли
        if v.esc_t > 0.0:
            v.esc_t -= dt
        if v.reverse_t > 0.0:
            v.reverse_t -= dt
            v.in_throttle = -1.0
            v.in_brake = 0.0
            # зажатая машина, сдавая назад, отворачивает нос в свободную сторону
            v.in_steer = -v.esc_side if v.esc_t > 0.0 else clamp(-err * 2.0, -1.0, 1.0)
            v.in_handbrake = False
            return
        steer = clamp(err * 2.6, -1.0, 1.0)
        if v.esc_t > 0.0:
            steer = clamp(steer * 0.3 + v.esc_side * 0.9, -1.0, 1.0)      # и объезжает то, во что упиралась
        fc, fl, fr = v.f_c, v.f_l, v.f_r
        target_block = d < fc + 2.5
        if not target_block:
            if fc < look:
                side = 1.0 if fl > fr else -1.0
                steer = clamp(steer * 0.3 + side * (1.25 - fc / look), -1.0, 1.0)
                tgt = min(tgt, max(3.5, fc * 1.1))
            elif fl < look * 0.4:
                steer = clamp(steer - 0.45, -1.0, 1.0)
            elif fr < look * 0.4:
                steer = clamp(steer + 0.45, -1.0, 1.0)
        gap = v.gap
        if gap < look and not on_lane:
            steer = clamp(steer + v.gap_side * 0.7, -1.0, 1.0)
        if gap < 9.0:
            tgt = min(tgt, max(4.0, gap * 1.5))
        v.in_steer = steer
        # --- скорость
        if abs(err) > 0.55:
            tgt = min(tgt, 8.0)
        elif abs(err) > 0.28:
            tgt = min(tgt, 15.0)
        if not on_lane:
            if pl.vehicle is None or psp < 3.0:
                # подъезжаем и останавливаемся рядом
                if d < 12.0:
                    tgt = 0.0
                else:
                    tgt = min(tgt, 4.0 + (d - 12.0) * 0.6)
            elif d < 30.0:
                tgt = min(tgt, psp + 7.0)       # таран
        if sp < tgt - 0.5:
            v.in_throttle = 1.0
            v.in_brake = 0.0
        elif sp > tgt + 1.5:
            v.in_throttle = 0.0
            v.in_brake = clamp((sp - tgt) / 5.0, 0.3, 1.0)
        else:
            v.in_throttle = 0.3
            v.in_brake = 0.0
        if v.speed < -0.5:
            v.in_throttle = 1.0
            v.in_brake = 0.0
        v.in_handbrake = abs(err) > 1.2 and sp > 10.0
        # Застряли?  Смотрим не только на скорость, но и на то, сдвинулась ли машина на самом деле:
        # зажатая между стеной и деревом, она «едет» на месте — мотор толкает, препятствие возвращает.
        wedged = False
        v.ref_t += dt
        if v.ref_t >= 1.5:
            wedged = tgt > 2.0 and (v.x - v.ref_x) ** 2 + (v.y - v.ref_y) ** 2 < 1.0
            v.ref_x, v.ref_y, v.ref_t = v.x, v.y, 0.0
        if sp < 0.7 and tgt > 2.0:
            v.stuck_t += dt
        else:
            v.stuck_t = max(0.0, v.stuck_t - dt * 0.5)
        if v.stuck_t > 1.2 or wedged:
            v.stuck_t = 0.0
            v.reverse_t = 1.2 + random.random() * 0.6
            v.link = None                       # после манёвра выбираем полосу заново
            v.route_t = 0.0
            v.ref_t = -v.reverse_t              # пока сдаём назад, отсчёт не идёт
            if wedged:
                v.esc_side = 1.0 if v.f_l > v.f_r else -1.0
                v.esc_t = v.reverse_t + 1.3
