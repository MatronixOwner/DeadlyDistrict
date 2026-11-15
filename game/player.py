# -*- coding: utf-8 -*-
"""Игрок: управление пешком и за рулём, оружие, камера."""
import math
import random

from .ped import Ped
from .vehicle import Vehicle
from .defs import WEAPONS, W_FIST, W_BAT, W_PISTOL, W_UZI, W_SILENCED, weapon_sort, player_look
from .mathutil import clamp, approach, angle_diff, turn_towards, damp, damp_angle, wrap_angle, yaw_to_h, DEG
from .collision import F_PED, F_CAM, F_CAR
from .city import WATER_Z
from .audio import STATIONS

JOG = 4.3
SPRINT = 7.2
WALK = 1.9


class Camera(object):

    def __init__(self, world):
        self.w = world
        self.base = world.base
        self.yaw = math.pi / 2
        self.pitch = -0.22
        self.dist = 4.0
        self.x = self.y = 0.0
        self.z = 3.0
        self.tx = self.ty = self.tz = 0.0
        self.free_t = 0.0                 # сколько секунд назад двигали мышью (в машине)
        self.mode = 'foot'
        self.zoom = 1                     # дальность камеры: 0 близко, 1 средне, 2 далеко
        self.fov = 68.0
        self.cut = True
        self.override = None              # (x, y, z, tx, ty, tz) — «кинокамера»
        self.look_back = False
        self.hid_player = False           # персонаж скрыт, потому что камера вплотную
        self.scope = False                # смотрим в оптический прицел

    def snap(self):
        self.cut = True

    def face(self, x, y, yaw):
        """Встать за спиной персонажа; если там стена — выбрать ближайшее свободное направление."""
        st = self.w.static
        need = (2.9, 3.9, 5.4)[self.zoom] + 0.4
        best = yaw
        for off in (0.0, -0.8, 0.8, -1.5708, 1.5708, -2.35, 2.35, 3.1416):
            a = yaw + off
            if st.raycast(x, y, 1.56, -math.cos(a), -math.sin(a), 0.0, need, F_CAM) is None:
                best = a
                break
        self.yaw = wrap_angle(best)
        self.cut = True

    def forward(self):
        cp = math.cos(self.pitch)
        return math.cos(self.yaw) * cp, math.sin(self.yaw) * cp, math.sin(self.pitch)

    def update(self, dt, mdx, mdy):
        w = self.w
        pl = w.player
        st = w.settings
        sens = 0.0026 * float(st.get('mouse_sens')) * min(1.0, self.fov / 68.0)   # в прицеле мышь тише
        if mdx or mdy:
            self.yaw = wrap_angle(self.yaw - mdx * sens)
            inv = -1.0 if st.get('invert_y') else 1.0
            self.pitch = clamp(self.pitch - mdy * sens * inv, -1.25, 0.75)
            self.free_t = 0.0
        else:
            self.free_t += dt
        cam = self.base.camera
        if self.override is not None:
            if self.hid_player:
                self.hid_player = False
                if pl.ped.vehicle is None:
                    pl.ped.node.show()
            ox, oy, oz, tx, ty, tz = self.override
            cam.setPos(ox, oy, oz)
            cam.lookAt(tx, ty, tz)
            self.x, self.y, self.z = ox, oy, oz
            self.yaw = math.atan2(ty - oy, tx - ox)
            return
        v = pl.vehicle
        fov = 68.0
        scope = False
        if v is not None:
            spec = v.spec
            tx, ty = v.x, v.y
            tz = v.z + spec.H * 0.55 + 0.75
            dist = (5.2, 7.0, 10.0)[self.zoom] + spec.L * 0.55
            sp = math.hypot(v.vx, v.vy)
            # камера сама возвращается за машину
            if self.free_t > 1.6 and sp > 1.5 and v.speed > -1.0:
                k = min(1.0, (self.free_t - 1.6) * 0.8) * (2.2 + min(sp, 30.0) * 0.07)
                self.yaw = damp_angle(self.yaw, v.yaw, k, dt)
                self.pitch = damp(self.pitch, -0.2, 1.5, dt)
            fov = 68.0 + min(14.0, sp * 0.3)
            side = 0.0
            yaw = self.yaw + (math.pi if self.look_back else 0.0)
        else:
            p = pl.ped
            tx, ty = p.x, p.y
            tz = p.z + 1.56
            aim = pl.aiming
            dist = (2.9, 3.9, 5.4)[self.zoom]
            if pl.indoors:
                dist = min(dist, 3.6)
            if aim:
                dist = 2.3
                fov = 56.0
            side = 0.55 if aim or pl.weapon.kind != 'melee' else 0.25
            if aim and pl.weapon.zoom > 0.0 and pl.state == 'foot':
                # оптика: смотрим от глаз, герой не в кадре
                scope = True
                dist = 0.0
                side = 0.0
                fov = 68.0 / pl.weapon.zoom
                tz = p.z + 1.62
            yaw = self.yaw
        if scope != self.scope:
            self.scope = scope
            self.cut = True                          # в прицел и обратно — без плавного наезда
        if self.cut:
            self.tx, self.ty, self.tz = tx, ty, tz
            self.dist = dist
            self.fov = fov
        else:
            k = 1.0 - math.exp(-18.0 * dt)
            self.tx += (tx - self.tx) * k
            self.ty += (ty - self.ty) * k
            self.tz += (tz - self.tz) * (1.0 - math.exp(-10.0 * dt))
            self.fov = damp(self.fov, fov, 5.0, dt)
        cp, sp_ = math.cos(self.pitch), math.sin(self.pitch)
        dx, dy, dz = math.cos(yaw) * cp, math.sin(yaw) * cp, sp_
        # смещение «из-за плеча»
        rx, ry = math.sin(yaw), -math.cos(yaw)
        ox = self.tx + rx * side
        oy = self.ty + ry * side
        oz = self.tz
        # не даём камере уйти в стену или под землю
        want = dist
        hit = None if scope else w.static.raycast(ox, oy, oz, -dx, -dy, -dz, dist + 0.4, F_CAM)
        if hit is not None:
            want = max(0.7, hit[0] - 0.35)
        if want < self.dist or self.cut:
            self.dist = want
        else:
            self.dist = min(want, self.dist + dt * 6.0)
        d = self.dist
        cx, cy, cz = ox - dx * d, oy - dy * d, oz - dz * d
        if v is None:
            # камеру прижало к стене (или смотрим в прицел): персонаж закрыл бы весь экран — прячем его
            hide = (d < 1.05 or scope) and pl.state == 'foot'
            if hide != self.hid_player:
                self.hid_player = hide
                if hide:
                    pl.ped.node.hide()
                elif pl.ped.vehicle is None:
                    pl.ped.node.show()
        else:
            self.hid_player = False
        gz = w.city.ground_z(cx, cy)
        if gz < WATER_Z:
            gz = WATER_Z
        if cz < gz + 0.3:
            cz = gz + 0.3
        sh = w.fx.shake
        if sh > 0.0:
            cx += random.uniform(-1, 1) * sh * 0.25
            cy += random.uniform(-1, 1) * sh * 0.25
            cz += random.uniform(-1, 1) * sh * 0.25
        self.x, self.y, self.z = cx, cy, cz
        self.cut = False
        cam.setPosHpr(cx, cy, cz, yaw_to_h(yaw), self.pitch * DEG, 0)
        lens = self.base.camLens
        if abs(lens.getFov()[0] - self.fov) > 0.2:
            lens.setFov(self.fov)

    def aim_ray(self):
        """Луч прицела: начало чуть впереди персонажа, чтобы не попадать в то, что за спиной."""
        dx, dy, dz = self.forward()
        d = self.dist + 0.3
        return self.x + dx * d, self.y + dy * d, self.z + dz * d, dx, dy, dz


class Player(object):

    def __init__(self, world):
        self.w = world
        sx, sy, syaw = world.city.start_pos
        self.ped = Ped(world, sx, sy, syaw, player_look(), 'player')
        self.ped.is_player = True
        self.ped.keep = True
        self.ped.set_state('player')
        self.ped.walk_speed = WALK
        self.ped.run_speed = JOG
        world.peds.append(self.ped)
        self.vehicle = None
        self.last_vehicle = None
        self.money = 0
        self.ammo = {W_FIST: -1}
        self.weapon_id = W_FIST
        self.weapon = WEAPONS[W_FIST]
        self.aiming = False
        self.indoors = False           # герой в помещении: оружие убрано
        self.no_enter_t = 0.0          # после сценки Enter ещё мгновение не сажает в машину
        self.aim_yaw = syaw
        self.invincible = False
        self.damage_taken_k = 1.0
        self.state = 'foot'            # foot | entering | car | dead | busted
        self.enter_v = None
        self.enter_side = -1
        self.enter_t = 0.0
        self.exit_wish = False
        self.fire_cd = 0.0
        self.mvx = self.mvy = 0.0
        self.jump_z = 0.0
        self.jump_v = 0.0
        self.step_d = 0.0
        self.controls = True
        self.dead_t = 0.0
        self.water_t = 0.0
        self.horn_on = False
        self.switch_t = 0.0
        self.shots_fired = 0
        self.busy_t = 0.0
        self.script_move = None           # (x, y, скорость): сценка ведёт героя, пока freeze
        self.freeze = False

    # ------------------------------------------------------------------
    def reset(self):
        """Вернуть игрока в исходное состояние (новая игра)."""
        w = self.w
        p = self.ped
        self.vehicle = None
        self.last_vehicle = None
        p.vehicle = None
        self.money = 0
        self.ammo = {W_FIST: -1}
        self.weapon_id = W_FIST
        self.weapon = WEAPONS[W_FIST]
        p.set_weapon(W_FIST)
        p.dead = False
        p.health = p.max_health
        p.armor = 0.0
        p.fire_t = 0.0
        p.air = False
        p.vx = p.vy = p.vz = 0.0
        p.lie = 0.001
        p.aiming = False
        p.set_state('player')
        p.node.show()
        self.state = 'foot'
        self.freeze = False
        self.script_move = None
        self.controls = True
        self.aiming = False
        self.enter_v = None
        self.exit_wish = False
        self.mvx = self.mvy = 0.0
        self.jump_z = self.jump_v = 0.0
        self.water_t = 0.0
        self.fire_cd = 0.0
        self.invincible = False
        sx, sy, syaw = w.city.start_pos
        p.x, p.y, p.yaw = sx, sy, syaw
        p.z = w.city.ground_z(sx, sy)
        p.sync()
        w.cam.hid_player = False
        w.cam.pitch = -0.22
        w.cam.look_back = False
        w.cam.face(sx, sy, syaw)
        p.yaw = w.cam.yaw                   # герой смотрит туда же, куда камера
        p.sync()
        if w.hud is not None:
            w.hud.weapon_changed()

    def pos(self):
        v = self.vehicle
        if v is not None:
            return v.x, v.y
        return self.ped.x, self.ped.y

    def velocity(self):
        v = self.vehicle
        if v is not None:
            return v.vx, v.vy
        return self.mvx, self.mvy

    def speed(self):
        v = self.vehicle
        if v is not None:
            return math.hypot(v.vx, v.vy)
        return math.hypot(self.mvx, self.mvy)

    def teleport(self, x, y, yaw=None):
        if self.vehicle is not None:
            self.leave_vehicle(force=True)
        p = self.ped
        p.x, p.y = x, y
        p.z = self.w.city.ground_z(x, y)
        self.mvx = self.mvy = 0.0
        p.sync()
        if yaw is not None:
            p.yaw = yaw
            self.w.cam.face(x, y, yaw)
        else:
            self.w.cam.snap()

    # ------------------------------------------------------------------
    # оружие
    # ------------------------------------------------------------------
    def give_weapon(self, wid, ammo=None, select=True):
        w = WEAPONS[wid]
        if ammo is None:
            ammo = w.pack
        if w.kind == 'melee':
            self.ammo[wid] = -1
        else:
            self.ammo[wid] = min(9999, max(0, self.ammo.get(wid, 0)) + ammo)
        if select and (self.weapon_id == W_FIST or wid == self.weapon_id):
            self.select(wid)

    def select(self, wid):
        if wid not in self.ammo:
            return
        self.weapon_id = wid
        self.weapon = WEAPONS[wid]
        self.ped.set_weapon(W_FIST if self.indoors else wid)     # в помещении оружие убрано
        self.w.hud.weapon_changed()

    def cycle(self, d):
        ids = weapon_sort(self.ammo.keys())
        if len(ids) < 2:
            return
        i = ids.index(self.weapon_id) if self.weapon_id in ids else 0
        self.select(ids[(i + d) % len(ids)])
        self.w.audio.play('click', 0.6)

    def select_slot(self, slot):
        """Клавиши 1–8: оружие своего класса; повторное нажатие листает внутри класса."""
        ids = [wid for wid in weapon_sort(self.ammo.keys()) if WEAPONS[wid].slot == slot]
        if not ids:
            return
        if self.weapon_id in ids:
            if len(ids) < 2:
                return
            wid = ids[(ids.index(self.weapon_id) + 1) % len(ids)]
        else:
            wid = ids[0]
        self.select(wid)
        self.w.audio.play('click', 0.6)

    def use_ammo(self, n=1):
        wid = self.weapon_id
        a = self.ammo.get(wid, 0)
        if a < 0:
            return True
        if a < n:
            return False
        a -= n
        self.ammo[wid] = a
        if a <= 0:
            # патроны кончились: убираем оружие
            del self.ammo[wid]
            # берём то, что было в руках до него: ближайшее оружие «полегче»
            order = weapon_sort(list(self.ammo.keys()) + [wid])
            k = order.index(wid)
            self.select(order[k - 1] if k > 0 else W_FIST)
        return True

    def clear_weapons(self):
        self.ammo = {W_FIST: -1}
        self.select(W_FIST)

    def add_money(self, n):
        self.money = max(0, self.money + int(n))
        self.w.hud.money_changed(n)

    # ------------------------------------------------------------------
    def update(self, dt, inp):
        st = self.state
        p = self.ped
        if self.fire_cd > 0.0:
            self.fire_cd -= dt
        if st == 'dead' or st == 'busted':
            self.dead_t += dt
            self.aiming = False
            v = self.vehicle
            if v is not None:
                v.in_throttle = 0.0
                v.in_steer = 0.0
                v.in_brake = 1.0
            return
        if self.freeze or not self.controls:
            self.aiming = False
            self.mvx = self.mvy = 0.0
            p.speed = 0.0
            sm = self.script_move
            if sm is not None and self.vehicle is None and st != 'entering':
                # сценка ведёт героя к точке (tx, ty) со скоростью sm[2]
                dx, dy = sm[0] - p.x, sm[1] - p.y
                d = math.hypot(dx, dy)
                step = sm[2] * dt
                if d <= max(step, 0.04):
                    p.x, p.y = sm[0], sm[1]
                    self.script_move = None
                else:
                    p.x += dx / d * step
                    p.y += dy / d * step
                    p.yaw = turn_towards(p.yaw, math.atan2(dy, dx), 9.0 * dt)
                    p.speed = sm[2]
                p.z = self.w.city.ground_z(p.x, p.y)
            v = self.vehicle
            if v is not None:
                v.in_throttle = 0.0
                v.in_brake = 1.0
                v.in_steer = 0.0
            return
        # выбор оружия
        if inp.hit('wheel_up') or inp.hit('e'):
            self.cycle(1)
        if inp.hit('wheel_down') or inp.hit('q'):
            self.cycle(-1)
        for i in range(1, 9):
            if inp.hit(str(i)):
                self.select_slot(i)
        if inp.hit('c'):
            cam = self.w.cam
            cam.zoom = (cam.zoom + 1) % 3
        if st == 'car':
            self._drive(dt, inp)
        elif st == 'entering':
            self._entering(dt, inp)
        else:
            self._on_foot(dt, inp)

    # ------------------------------------------------------------------
    def _on_foot(self, dt, inp):
        w = self.w
        p = self.ped
        cam = w.cam
        if p.state == 'down':
            self.mvx = self.mvy = 0.0
            self.aiming = False
            return
        if p.state != 'player':
            p.set_state('player')
        ix = inp.axis('a', 'd', 'arrow_left', 'arrow_right')
        iy = inp.axis('s', 'w', 'arrow_down', 'arrow_up')
        wp = self.weapon
        fire = (inp.held('mouse1') or inp.held('control')) and not self.indoors
        self.aiming = (inp.held('mouse3') or fire) and wp.kind != 'melee' and not self.indoors
        cy, sy = math.cos(cam.yaw), math.sin(cam.yaw)
        mx = cy * iy + sy * ix
        my = sy * iy - cy * ix
        ml = math.hypot(mx, my)
        speed = 0.0
        if ml > 0.01:
            mx, my = mx / ml, my / ml
            if self.aiming:
                speed = 2.6
            elif inp.held('shift'):
                speed = SPRINT
            elif inp.held('alt'):
                speed = WALK
            else:
                speed = JOG
        k = 1.0 - math.exp(-13.0 * dt)
        self.mvx += (mx * speed - self.mvx) * k
        self.mvy += (my * speed - self.mvy) * k
        p.x += self.mvx * dt + p.vx * dt
        p.y += self.mvy * dt + p.vy * dt
        if p.vx or p.vy:                      # отдача от ударов
            e = math.exp(-8.0 * dt)
            p.vx *= e
            p.vy *= e
            if abs(p.vx) + abs(p.vy) < 0.05:
                p.vx = p.vy = 0.0
        nx, ny, a, b, depth, ref = w.static.push_circle(p.x, p.y, p.radius, F_PED)
        if depth > 0.0:
            p.x, p.y = nx, ny
        sp = math.hypot(self.mvx, self.mvy)
        p.speed = sp
        # поворот персонажа
        if self.aiming or self.fire_cd > 0.0 and wp.kind != 'melee':
            p.yaw = turn_towards(p.yaw, cam.yaw, 16.0 * dt)
            self.aim_yaw = cam.yaw
            p.aiming = True
            p.aim_pitch = clamp(cam.pitch * DEG, -50.0, 50.0)
        else:
            p.aiming = False
            if sp > 0.3:
                p.yaw = turn_towards(p.yaw, math.atan2(self.mvy, self.mvx), 11.0 * dt)
        # высота: бордюры и прыжок
        gz = w.city.ground_z(p.x, p.y)
        if self.jump_z > 0.0 or self.jump_v > 0.0:
            self.jump_v -= 15.0 * dt
            self.jump_z += self.jump_v * dt
            if self.jump_z <= 0.0:
                self.jump_z = 0.0
                self.jump_v = 0.0
        elif inp.hit('space') and not self.aiming:
            self.jump_v = 4.6
            self.jump_z = 0.001
        p.z = gz + self.jump_z
        # вода
        if gz < WATER_Z - 0.2 and w.city.in_water(p.x, p.y):
            self.water_t += dt
            p.z = WATER_Z - 1.0
            if self.water_t > 0.12 and not p.dead:
                w.fx.splash(p.x, p.y, WATER_Z, 1.2)
                w.audio.play('splash', 0.9)
                p.health = 0.0
                p.die(None, 'drown')
                return
        else:
            self.water_t = 0.0
        # шаги
        if sp > 1.0 and self.jump_z <= 0.0:
            self.step_d += sp * dt
            if self.step_d > (2.1 if sp > 5.5 else 1.5):
                self.step_d = 0.0
                w.audio.play('step', 0.25 + min(0.3, sp * 0.04), 0.9 + random.random() * 0.2)
        # действие: оружие
        if (fire or inp.held('mouse1')) and not self.indoors:
            self._fire(inp)
        # сесть в машину
        if self.no_enter_t > 0.0:
            self.no_enter_t -= dt
            if inp.hit('f') and not self.indoors:
                self._try_enter()
        elif (inp.hit('f') or inp.hit('enter')) and not self.indoors:
            self._try_enter()

    def _fire(self, inp):
        if self.fire_cd > 0.0:
            return
        wp = self.weapon
        if not wp.auto and wp.kind == 'gun':
            # полуавтомат: одно нажатие — один выстрел
            if not (inp.hit('mouse1') or inp.hit('control')):
                return
        w = self.w
        if wp.kind == 'melee':
            self.fire_cd = wp.rate
            self.ped.punch_t = 0.3
            w.weapons.player_melee(wp)
            return
        self.fire_cd = wp.rate
        w.weapons.player_fire(wp)

    # ------------------------------------------------------------------
    def _try_enter(self):
        w = self.w
        p = self.ped
        best = None
        bd = 7.0
        for v in w.vehicles:
            if v.dead or v.sunk or v.removed or v.locked:
                continue
            d = math.hypot(v.x - p.x, v.y - p.y) - v.spec.L * 0.3
            if d < bd and math.hypot(v.vx, v.vy) < 9.0:
                bd = d
                best = v
        if best is None:
            return
        # ближайшая дверь
        lx, ly = best.door_pos(-1)
        rx, ry = best.door_pos(1)
        dl = math.hypot(lx - p.x, ly - p.y)
        dr = math.hypot(rx - p.x, ry - p.y)
        self.enter_side = -1 if dl <= dr + 0.4 else 1
        self.enter_v = best
        self.enter_t = 0.0
        self.state = 'entering'
        self.aiming = False
        p.aiming = False

    def _entering(self, dt, inp):
        w = self.w
        p = self.ped
        v = self.enter_v
        self.enter_t += dt
        moved = inp.axis('a', 'd') != 0 or inp.axis('s', 'w') != 0
        if (v is None or v.removed or v.dead or v.sunk or self.enter_t > 5.0 or (moved and self.enter_t > 0.35)
                or p.state == 'down'):
            self.state = 'foot'
            self.enter_v = None
            return
        if v.mode == Vehicle.RAIL and v.npc:
            # водитель видит, что к нему лезут — притормаживает
            v.target_speed = 0.0
            v.ai_t = 0.5
        dx, dy = v.door_pos(self.enter_side)
        d = math.hypot(dx - p.x, dy - p.y)
        if d > 0.75:
            ang = math.atan2(dy - p.y, dx - p.x)
            step = min(d, SPRINT * 0.85 * dt)
            p.x += math.cos(ang) * step
            p.y += math.sin(ang) * step
            p.yaw = turn_towards(p.yaw, ang, 14.0 * dt)
            p.speed = SPRINT * 0.85
            self.mvx = math.cos(ang) * p.speed
            self.mvy = math.sin(ang) * p.speed
            nx, ny, a, b, depth, ref = w.static.push_circle(p.x, p.y, p.radius, F_PED)
            if depth > 0.0:
                p.x, p.y = nx, ny
            p.z = w.city.ground_z(p.x, p.y)
            return
        if math.hypot(v.vx, v.vy) > 7.0:
            return
        self.enter_vehicle(v)

    def enter_vehicle(self, v, silent=False):
        w = self.w
        p = self.ped
        if v.npc or v.driver is not None:
            w.carjack(v, self.enter_side)
        if v in w.police.units:
            w.police.units.remove(v)        # угнали машину у самой полиции
        v.crew = 0
        v.siren = False
        w.traffic.take_over(v)
        v.set_mode(Vehicle.PHYS)
        v.driver = p
        v.is_player = True
        v.ai = None
        stolen = not v.stolen and v.owner != 'player'
        v.stolen = True
        p.vehicle = v
        p.set_state('in_car')
        p.aiming = False
        p.speed = 0.0
        p.node.hide()
        self.vehicle = v
        self.last_vehicle = v
        self.state = 'car'
        self.enter_v = None
        self.exit_wish = False
        self.mvx = self.mvy = 0.0
        w.cam.free_t = 5.0
        if w.sky is not None:
            v.set_lights(w.sky.lights_on)
        if w.radio_pref is not None and v.spec.radio:
            v.radio = w.radio_pref              # своя станция играет в любой машине
        if not silent:
            w.audio.play('door', 0.8)
        w.on_player_enter_vehicle(v, stolen)

    def leave_vehicle(self, force=False):
        """Выйти из машины.  Возвращает False, если двери заблокированы препятствиями."""
        w = self.w
        v = self.vehicle
        p = self.ped
        if v is None:
            return True
        spot = None
        for side in (-1, 1):
            x, y = v.door_pos(side)
            if w.static.overlap_circle(x, y, p.radius, F_PED):
                continue
            if w.city.ground_z(x, y) < WATER_Z:
                continue
            spot = (x, y)
            break
        if spot is None:
            if not force:
                return False
            spot = v.door_pos(-1)
        v.driver = None
        v.is_player = False
        v.in_throttle = v.in_steer = 0.0
        v.in_brake = 0.0
        v.in_handbrake = False
        v.siren = False
        v.set_brake_light(False)
        p.vehicle = None
        p.x, p.y = spot
        p.z = w.city.ground_z(p.x, p.y)
        p.yaw = v.yaw
        p.set_state('player')
        p.node.show()
        p.sync()
        self.vehicle = None
        self.state = 'foot'
        self.mvx, self.mvy = v.vx * 0.5, v.vy * 0.5
        self.exit_wish = False
        w.audio.play('door', 0.7)
        w.on_player_leave_vehicle(v)
        return True

    # ------------------------------------------------------------------
    def _drive(self, dt, inp):
        w = self.w
        v = self.vehicle
        if v is None or v.removed:
            self.vehicle = None
            self.state = 'foot'
            self.ped.vehicle = None
            self.ped.set_state('player')
            self.ped.node.show()
            return
        p = self.ped
        p.x, p.y, p.z, p.yaw = v.x, v.y, v.z, v.yaw
        thr = inp.axis('s', 'w', 'arrow_down', 'arrow_up')
        steer = inp.axis('d', 'a', 'arrow_right', 'arrow_left')
        v.in_throttle = thr
        v.in_steer = steer
        v.in_brake = 0.0
        v.in_handbrake = inp.held('space')
        v.set_brake_light((thr < 0 and v.speed > 1.0) or (thr > 0 and v.speed < -1.0) or v.in_handbrake)
        w.cam.look_back = inp.held('b')
        # сигнал / сирена
        if inp.hit('h'):
            if v.kind in ('police', 'ambulance', 'enforcer', 'fbi'):
                v.siren = not v.siren
            else:
                w.audio.play('horn_truck' if v.spec.engine == 'truck' else 'horn', 0.9)
                w.crowd.panic(v.x, v.y, 14.0)
        if inp.hit('r') and v.spec.radio:
            v.radio = (v.radio + 1) % len(STATIONS)
            w.radio_pref = v.radio
            w.audio.play('static', 0.6)
            w.hud.radio_changed(STATIONS[v.radio][0])
        if inp.hit('n') and v.spec.radio and w.audio.next_track():
            w.audio.play('static', 0.4)
        # стрельба из окна
        self.aiming = False
        if inp.held('mouse1') or inp.held('control'):
            wp = self.weapon
            if wp.id in (W_PISTOL, W_UZI, W_SILENCED) and self.fire_cd <= 0.0:
                if wp.auto or inp.hit('mouse1') or inp.hit('control'):
                    self.fire_cd = wp.rate
                    w.weapons.player_fire(wp, driveby=True)
        # выход
        if self.no_enter_t > 0.0:
            self.no_enter_t -= dt
        if inp.hit('f') or (inp.hit('enter') and self.no_enter_t <= 0.0):
            self.exit_wish = True
        if self.exit_wish:
            if thr > 0.0:
                self.exit_wish = False
            elif math.hypot(v.vx, v.vy) > 2.2:
                v.in_throttle = 0.0
                v.in_brake = 1.0
            else:
                if not self.leave_vehicle():
                    self.exit_wish = False
                    w.hud.help('Двери заблокированы — отъезжай от стены.', 3.0)
        if v.dead and self.vehicle is v and v.burning > 0.0 and not v.sunk:
            # машина взорвалась вместе с нами
            self.leave_vehicle(force=True)

    # ------------------------------------------------------------------
    def on_death(self):
        self.state = 'dead'
        self.dead_t = 0.0
        self.aiming = False

    def bust(self):
        if self.state in ('dead', 'busted'):
            return
        self.state = 'busted'
        self.dead_t = 0.0
        self.aiming = False
        self.ped.aiming = False

    def revive(self, x, y, yaw):
        p = self.ped
        if self.vehicle is not None:
            v = self.vehicle
            v.driver = None
            v.is_player = False
            self.vehicle = None
            p.vehicle = None
        p.dead = False
        p.health = p.max_health
        p.armor = 0.0
        p.fire_t = 0.0
        p.air = False
        p.vx = p.vy = p.vz = 0.0
        p.lie = 0.001
        p.set_state('player')
        p.node.show()
        self.state = 'foot'
        self.water_t = 0.0
        self.jump_z = self.jump_v = 0.0
        self.teleport(x, y, yaw)
