# -*- coding: utf-8 -*-
"""Стрельба, взрывы, огонь."""
import math
import random

from .defs import WEAPONS, W_ROCKET, W_GRENADE, W_MOLOTOV, W_SHOTGUN
from .meshbuilder import MeshBuilder
from .mathutil import clamp, angle_diff, yaw_to_h
from .collision import F_BULLET, F_PED
from .city import WATER_Z


class Projectile(object):
    __slots__ = ('kind', 'x', 'y', 'z', 'vx', 'vy', 'vz', 'life', 'owner', 'np', 'smoke_t')


class Flame(object):
    __slots__ = ('x', 'y', 'z', 'r', 'life', 'owner', 't')


class Weapons(object):

    def __init__(self, world):
        self.w = world
        self.projectiles = []
        self.flames = []
        self._models = {}
        self.flame_t = 0.0

    def clear(self):
        for pr in self.projectiles:
            pr.np.removeNode()
        self.projectiles = []
        self.flames = []

    # ------------------------------------------------------------------
    # поиск попаданий
    # ------------------------------------------------------------------
    def trace(self, ox, oy, oz, dx, dy, dz, maxd, shooter=None, skip_vehicle=None):
        """Луч против мира, людей и машин.

        Возвращает (t, kind, obj, nx, ny, nz); kind: 'world' | 'ped' | 'veh' | None.
        """
        w = self.w
        best = maxd
        kind = None
        obj = None
        nx = ny = 0.0
        nz = 1.0
        hit = w.static.raycast(ox, oy, oz, dx, dy, dz, maxd, F_BULLET)
        if hit is not None:
            best = hit[0]
            kind = 'world'
            obj = hit[4]
            nx, ny, nz = hit[1], hit[2], hit[3]
        hl = math.hypot(dx, dy)
        # люди: вертикальный цилиндр
        for p in w.peds:
            if p is shooter or p.removed or p.vehicle is not None:
                continue
            rx, ry = p.x - ox, p.y - oy
            if abs(rx) > best + 1 or abs(ry) > best + 1:
                continue
            lying = p.state in ('down', 'dead')
            r = 0.75 if lying else 0.36
            top = 0.45 if lying else 1.82 * p.look.scale
            if hl > 1e-6:
                # ближайшая точка луча к оси цилиндра (в плане)
                tca = (rx * dx + ry * dy) / (hl * hl)
                if tca <= 0.0:
                    continue
                px, py = rx - dx * tca, ry - dy * tca
                d2 = px * px + py * py
                if d2 > r * r:
                    continue
                thc = math.sqrt(r * r - d2) / hl
                t = tca - thc
                if t < 0.0:
                    t = 0.0
            else:
                if rx * rx + ry * ry > r * r:
                    continue
                t = (oz - (p.z + top)) if dz < 0 else maxd
            if t >= best:
                continue
            z = oz + dz * t
            if z < p.z - 0.05 or z > p.z + top:
                # луч может войти в цилиндр сверху/снизу дальше по ходу
                t2 = tca + thc if hl > 1e-6 else t
                z2 = oz + dz * t2
                if (z - (p.z + top)) * (z2 - (p.z + top)) < 0 or (z - p.z) * (z2 - p.z) < 0:
                    t = (t + t2) * 0.5
                    if t >= best:
                        continue
                    z = clamp(oz + dz * t, p.z, p.z + top)
                else:
                    continue
            best = t
            kind = 'ped'
            obj = p
            nx, ny, nz = -dx, -dy, z - p.z          # nz: высота попадания над землёй
        # машины: ориентированный параллелепипед
        for v in w.vehicles:
            if v is skip_vehicle or v.removed:
                continue
            rx, ry = v.x - ox, v.y - oy
            reach = best + v.radius
            if abs(rx) > reach or abs(ry) > reach:
                continue
            c, s = math.cos(v.yaw), math.sin(v.yaw)
            # в систему машины: X' — вдоль, Y' — влево
            lox = -(rx * c + ry * s)
            loy = -(-rx * s + ry * c)
            ldx = dx * c + dy * s
            ldy = -dx * s + dy * c
            hl2, hw2 = v.spec.L * 0.5, v.spec.W * 0.5
            z0, z1 = v.z + v.spec.clear * 0.5, v.z + v.hit_top()
            tmin, tmax = 0.0, best
            ok = True
            face = 0
            for (o, d, lo, hi, f) in ((lox, ldx, -hl2, hl2, 1), (loy, ldy, -hw2, hw2, 2), (oz, dz, z0, z1, 3)):
                if abs(d) < 1e-9:
                    if o < lo or o > hi:
                        ok = False
                        break
                    continue
                t0 = (lo - o) / d
                t1 = (hi - o) / d
                if t0 > t1:
                    t0, t1 = t1, t0
                if t0 > tmin:
                    tmin = t0
                    face = f
                if t1 < tmax:
                    tmax = t1
                if tmin > tmax:
                    ok = False
                    break
            if not ok or tmin >= best:
                continue
            best = tmin
            kind = 'veh'
            obj = v
            if face == 1:
                sg = -1.0 if ldx > 0 else 1.0
                nx, ny, nz = c * sg, s * sg, 0.0
            elif face == 2:
                sg = -1.0 if ldy > 0 else 1.0
                nx, ny, nz = -s * sg, c * sg, 0.0
            else:
                nx, ny, nz = 0.0, 0.0, 1.0
        return best, kind, obj, nx, ny, nz

    # ------------------------------------------------------------------
    def _apply_bullet(self, wp, t, kind, obj, nx, ny, nz, ox, oy, oz, dx, dy, dz, shooter, dmg_k=1.0):
        w = self.w
        hx, hy, hz = ox + dx * t, oy + dy * t, oz + dz * t
        fx = w.fx
        by_player = shooter is not None and shooter.is_player
        if kind == 'ped':
            dmg = wp.damage * dmg_k
            head = nz > 1.48 * obj.look.scale and obj.state not in ('down', 'dead')
            if head:
                dmg *= 3.0
            if w.settings.get('blood'):
                fx.blood(hx, hy, hz, 4, dx, dy)
            else:
                fx.dust(hx, hy, hz, 2)
            if not obj.dead:
                obj.hurt(dmg, shooter, 'bullet', (dx * 1.2, dy * 1.2))
        elif kind == 'veh':
            who = obj.rider_hit(hz)
            if who is None:
                fx.sparks(hx, hy, hz, 3, nx, ny, nz)
                obj.damage(wp.damage * wp.car_k * dmg_k, by_player, 'bullet')
                w.on_vehicle_shot(obj, shooter, hx, hy, hz, dx, dy, dz)
            else:
                # пуля досталась тому, кто сидит верхом
                if w.settings.get('blood'):
                    fx.blood(hx, hy, hz, 4, dx, dy)
                else:
                    fx.dust(hx, hy, hz, 2)
                if who == 'npc':
                    w.unseat_rider(obj, wp.damage * dmg_k, shooter, 'bullet')
                elif not who.dead:
                    who.hurt(wp.damage * dmg_k, shooter, 'bullet')
                if by_player and w.missions is not None:
                    w.missions.notify('vehicle_shot', obj)
        elif kind == 'world':
            if hz < WATER_Z + 0.2 and w.city.in_water(hx, hy):
                fx.splash(hx, hy, WATER_Z, 0.3)
            else:
                fx.sparks(hx, hy, hz, 2, nx, ny, nz)
                fx.dust(hx, hy, hz, 1)
                if obj is not None and obj[0] == 'break':
                    br = obj[1]
                    if br.kind in ('cone', 'crate', 'barrel', 'bin', 'umbrella', 'newsbox', 'tires'):
                        w.break_prop(br, None)
                if random.random() < 0.12:
                    w.audio.play_at('ricochet', hx, hy, 0.5, 0.8 + random.random() * 0.5, 50.0)
        return hx, hy, hz

    def player_fire(self, wp, driveby=False):
        w = self.w
        pl = w.player
        p = pl.ped
        cam = w.cam
        if not pl.use_ammo(1):
            w.audio.play('click', 0.7)
            return
        if driveby:
            v = pl.vehicle
            dx, dy, dz = cam.forward()
            if dz < -0.25:
                dz = -0.25
            n = math.sqrt(dx * dx + dy * dy + dz * dz)
            dx, dy, dz = dx / n, dy / n, dz / n
            # стреляем из окна с той стороны, куда смотрит камера
            side = angle_diff(math.atan2(dy, dx), v.yaw)
            sx = 1.0 if side < 0 else -1.0
            rx, ry = math.sin(v.yaw), -math.cos(v.yaw)
            mx = v.x + rx * sx * (v.spec.W * 0.5 + 0.25)
            my = v.y + ry * sx * (v.spec.W * 0.5 + 0.25)
            mz = v.z + v.spec.belt + 0.25
            ox, oy, oz = mx, my, mz
            skip = v
        else:
            p.shot_t = 0.3
            ox, oy, oz, dx, dy, dz = cam.aim_ray()
            fwd_x, fwd_y = math.cos(cam.yaw), math.sin(cam.yaw)
            rx, ry = fwd_y, -fwd_x
            mx = p.x + fwd_x * 0.55 + rx * 0.3
            my = p.y + fwd_y * 0.55 + ry * 0.3
            mz = p.z + 1.38
            skip = None
        if wp.kind == 'rocket':
            self.launch('rocket', mx, my, mz, dx, dy, dz, 46.0, p)
            w.audio.play('rocket', 0.9)
            w.fx.muzzle(mx, my, mz, 1.2)
            w.on_gunfire(p, mx, my, loud=True)
            return
        if wp.kind == 'thrown':
            up = max(0.12, dz + 0.3)
            n = math.sqrt(dx * dx + dy * dy + up * up)
            sp = 17.0
            self.launch('grenade' if wp.id == W_GRENADE else 'molotov', mx, my, mz + 0.3, dx / n, dy / n, up / n,
                        sp, p)
            w.audio.play('swing', 0.8)
            p.punch_t = 0.3
            return
        w.audio.play(wp.sound, 0.85, 0.96 + random.random() * 0.08)
        w.fx.muzzle(mx, my, mz, 0.2 if wp.silent else (0.55 if wp.pellets == 1 else 0.9))
        # конус разброса вокруг оси прицела
        ux, uy, uz = -dy, dx, 0.0
        ul = math.hypot(ux, uy) or 1.0
        ux, uy = ux / ul, uy / ul
        vx, vy, vz = dy * uz - dz * uy, dz * ux - dx * uz, dx * uy - dy * ux
        spread = wp.spread * (1.6 if (pl.speed() > 3.0 or driveby) else 1.0)
        for _ in range(wp.pellets):
            a = random.uniform(0, 6.2832)
            r = spread * math.sqrt(random.random())
            ca, sa = math.cos(a) * r, math.sin(a) * r
            bx, by, bz = dx + ux * ca + vx * sa, dy + uy * ca + vy * sa, dz + uz * ca + vz * sa
            n = math.sqrt(bx * bx + by * by + bz * bz)
            bx, by, bz = bx / n, by / n, bz / n
            t, kind, obj, nx, ny, nz = self.trace(ox, oy, oz, bx, by, bz, wp.range, p, skip)
            if kind is not None:
                hx, hy, hz = self._apply_bullet(wp, t, kind, obj, nx, ny, nz, ox, oy, oz, bx, by, bz, p)
            else:
                hx, hy, hz = ox + bx * t, oy + by * t, oz + bz * t
            w.fx.tracer(mx, my, mz, hx, hy, hz, width=0.06 if wp.pellets == 1 else 0.04)
        w.on_gunfire(p, mx, my, silent=wp.silent)

    def player_melee(self, wp):
        w = self.w
        pl = w.player
        p = pl.ped
        w.audio.play('swing', 0.5, 1.0 + random.random() * 0.2)
        fx_, fy_ = math.cos(p.yaw), math.sin(p.yaw)
        best = None
        bd = wp.range + 0.4
        for o in w.peds:
            if o is p or o.removed or o.vehicle is not None or o.state == 'dead':
                continue
            dx, dy = o.x - p.x, o.y - p.y
            d = math.hypot(dx, dy)
            if d < bd and (d < 0.5 or (dx * fx_ + dy * fy_) / d > 0.35):
                bd = d
                best = o
        if best is not None:
            self.melee_hit(p, best, wp)
            return
        # удар по машине
        for v in w.vehicles:
            dx, dy = v.x - p.x, v.y - p.y
            if abs(dx) > 8 or abs(dy) > 8 or v.removed:
                continue
            for i in range(len(v.circles)):
                cx, cy = v.circle_pos(i)
                ddx, ddy = cx - p.x, cy - p.y
                d = math.hypot(ddx, ddy)
                if d < v.cr + wp.range and (ddx * fx_ + ddy * fy_) > 0.0:
                    w.audio.play('crash1', 0.35, 1.3)
                    v.damage(wp.damage * 1.2, True, 'melee')
                    w.fx.sparks(p.x + fx_ * 0.9, p.y + fy_ * 0.9, p.z + 1.0, 2)
                    w.on_vehicle_shot(v, p, v.x, v.y, 1.0, fx_, fy_, 0.0, melee=True)
                    return

    def melee_hit(self, attacker, target, wp):
        w = self.w
        if target.dead or target.removed:
            return
        dx, dy = target.x - attacker.x, target.y - attacker.y
        d = math.hypot(dx, dy) or 1.0
        if target.vehicle is not None:
            # бьём по машине, в которой сидит цель
            v = target.vehicle
            v.damage(wp.damage * 0.8, attacker.is_player, 'melee')
            w.audio.play_at('crash1', v.x, v.y, 0.3, 1.3)
            return
        w.audio.play_at('punch', target.x, target.y, 0.8, 0.9 + random.random() * 0.25, 50.0)
        if w.settings.get('blood') and wp.damage > 20:
            w.fx.blood(target.x, target.y, target.z + 1.4, 2, dx / d, dy / d)
        dmg = wp.damage * (1.0 if attacker.is_player else 0.6)
        dead = target.hurt(dmg, attacker, 'melee', (dx / d * 2.5, dy / d * 2.5))
        if not dead and not target.is_player and target.health < target.max_health * 0.45 and random.random() < 0.6:
            target.knock_down(1.5 + random.random() * 1.5, dx / d * 2.0, dy / d * 2.0, 1.5)
        if not dead and random.random() < 0.5 and target.voice_cd <= 0.0:
            w.audio.play_at('ouch_f' if target.look.female else 'ouch_m', target.x, target.y, 0.7,
                            0.9 + random.random() * 0.2, 45.0)

    def npc_fire(self, ped, target, wp, tx, ty, d):
        """Выстрел ИИ: вероятность попадания вместо точной баллистики по цели-игроку."""
        w = self.w
        fx_, fy_ = math.cos(ped.yaw), math.sin(ped.yaw)
        mx, my, mz = ped.x + fx_ * 0.55, ped.y + fy_ * 0.55, ped.z + 1.38
        w.audio.play_at(wp.sound, mx, my, 0.7, 0.94 + random.random() * 0.1, 30.0 if wp.silent else 100.0)
        w.fx.muzzle(mx, my, mz, 0.2 if wp.silent else 0.5)
        tv = target.vehicle
        tz = (tv.z + tv.spec.belt) if tv is not None else target.z + 1.1
        if tv is not None:
            tsp = math.hypot(tv.vx, tv.vy)
        elif target.is_player:
            tsp = w.player.speed()
        else:
            tsp = target.speed
        chance = ped.accuracy * clamp(1.15 - d / wp.range, 0.15, 1.0) / (1.0 + tsp * 0.09)
        if wp.pellets > 1:
            chance = min(0.95, chance * 1.5)
        hit = random.random() < chance
        if hit:
            ax, ay, az = tx, ty, tz + random.uniform(-0.3, 0.3)
        else:
            # промах: пуля уходит рядом с целью
            off = random.uniform(0.7, 2.2) * random.choice((-1.0, 1.0))
            ax, ay, az = tx - (ty - my) / max(d, 1.0) * off, ty + (tx - mx) / max(d, 1.0) * off, tz + \
                random.uniform(-0.6, 0.9)
        dx, dy, dz = ax - mx, ay - my, az - mz
        n = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        dx, dy, dz = dx / n, dy / n, dz / n
        t, kind, obj, nx, ny, nz = self.trace(mx, my, mz, dx, dy, dz, wp.range, ped, ped.vehicle)
        k = 1.0
        if target.is_player or (tv is not None and tv.is_player):
            k = 0.55                      # полиция и бандиты бьют слабее игрока
        if wp.pellets > 1:
            k *= 3.0
        if kind is not None:
            if kind == 'veh' and obj is tv and hit and not tv.dead:
                # часть урона достаётся водителю
                obj.damage(wp.damage * 0.8 * k, False, 'bullet')
                w.fx.sparks(mx + dx * t, my + dy * t, mz + dz * t, 3, nx, ny, nz)
                if random.random() < 0.3:
                    target.hurt(wp.damage * 0.5 * k, ped, 'bullet')
            elif kind == 'ped' and obj is not target and ped.gang is not None and obj.gang == ped.gang:
                pass                          # своих не задевают: перекрёстный огонь не решает бой за игрока
            else:
                self._apply_bullet(wp, t, kind, obj, nx, ny, nz, mx, my, mz, dx, dy, dz, ped, k)
        w.fx.tracer(mx, my, mz, mx + dx * t, my + dy * t, mz + dz * t, width=0.05)
        w.on_gunfire(ped, mx, my, silent=wp.silent)

    # ------------------------------------------------------------------
    # снаряды
    # ------------------------------------------------------------------
    def _model(self, kind):
        m = self._models.get(kind)
        if m is None:
            mb = MeshBuilder()
            if kind == 'rocket':
                mb.box(None, -0.07, -0.45, -0.07, 0.07, 0.3, 0.07, (0.3, 0.34, 0.26, 1))
                mb.box(None, -0.05, 0.3, -0.05, 0.05, 0.5, 0.05, (0.7, 0.2, 0.15, 1))
                mb.box(None, -0.16, -0.5, -0.015, 0.16, -0.3, 0.015, (0.2, 0.2, 0.2, 1))
                mb.box(None, -0.015, -0.5, -0.16, 0.015, -0.3, 0.16, (0.2, 0.2, 0.2, 1))
            elif kind == 'grenade':
                mb.blob(None, 0, 0, 0, 0.09, 0.09, 0.11, (0.2, 0.34, 0.2, 1))
                mb.box(None, -0.03, -0.03, 0.09, 0.03, 0.03, 0.16, (0.5, 0.5, 0.5, 1))
            else:
                mb.box(None, -0.05, -0.05, -0.12, 0.05, 0.05, 0.08, (0.5, 0.32, 0.12, 1))
                mb.box(None, -0.02, -0.02, 0.08, 0.02, 0.02, 0.2, (0.9, 0.9, 0.85, 1))
            m = mb.build(kind, self.w.assets.apply_state)
            self._models[kind] = m
        return m

    def launch(self, kind, x, y, z, dx, dy, dz, speed, owner):
        pr = Projectile()
        pr.kind = kind
        pr.x, pr.y, pr.z = x, y, z
        pr.vx, pr.vy, pr.vz = dx * speed, dy * speed, dz * speed
        pr.life = 4.0 if kind == 'rocket' else (2.6 if kind == 'grenade' else 6.0)
        pr.owner = owner
        pr.smoke_t = 0.0
        pr.np = self._model(kind).copyTo(self.w.dyn_root)
        pr.np.setPos(x, y, z)
        pr.np.setH(yaw_to_h(math.atan2(dy, dx)))
        self.projectiles.append(pr)
        return pr

    def update(self, dt):
        w = self.w
        if self.projectiles:
            keep = []
            for pr in self.projectiles:
                if self._step(pr, dt):
                    keep.append(pr)
                else:
                    pr.np.removeNode()
            self.projectiles = keep
        if self.flames:
            self._update_flames(dt)

    def _step(self, pr, dt):
        w = self.w
        pr.life -= dt
        sp = math.sqrt(pr.vx * pr.vx + pr.vy * pr.vy + pr.vz * pr.vz)
        if pr.kind != 'rocket':
            pr.vz -= 12.0 * dt
        step = sp * dt
        if sp > 0.01:
            dx, dy, dz = pr.vx / sp, pr.vy / sp, pr.vz / sp
            owner_v = pr.owner.vehicle if pr.owner is not None else None
            t, kind, obj, nx, ny, nz = self.trace(pr.x, pr.y, pr.z, dx, dy, dz, step + 0.15, pr.owner, owner_v)
            if kind is not None:
                hx, hy, hz = pr.x + dx * t, pr.y + dy * t, pr.z + dz * t
                if pr.kind == 'rocket':
                    self.explode(hx - dx * 0.2, hy - dy * 0.2, max(0.2, hz), 7.5, 260.0, pr.owner)
                    return False
                if pr.kind == 'molotov':
                    self.ignite(hx, hy, max(0.0, hz - 0.2), pr.owner)
                    return False
                # граната отскакивает
                if kind == 'world':
                    vn = pr.vx * nx + pr.vy * ny + pr.vz * nz
                    pr.vx = (pr.vx - 2.0 * vn * nx) * 0.45
                    pr.vy = (pr.vy - 2.0 * vn * ny) * 0.45
                    pr.vz = (pr.vz - 2.0 * vn * nz) * 0.35
                    if abs(pr.vz) < 0.8 and nz > 0.7:
                        pr.vz = 0.0
                else:
                    pr.vx *= -0.2
                    pr.vy *= -0.2
                pr.x, pr.y, pr.z = hx + nx * 0.06, hy + ny * 0.06, hz + (nz * 0.06 if kind == 'world' else 0.0)
                if random.random() < 0.6:
                    w.audio.play_at('click', hx, hy, 0.6, 0.6, 40.0)
            else:
                pr.x += pr.vx * dt
                pr.y += pr.vy * dt
                pr.z += pr.vz * dt
        if pr.z < WATER_Z and w.city.in_water(pr.x, pr.y):
            w.fx.splash(pr.x, pr.y, WATER_Z, 0.8)
            if pr.kind == 'rocket':
                self.explode(pr.x, pr.y, WATER_Z, 5.0, 150.0, pr.owner)
            return False
        pr.np.setPos(pr.x, pr.y, pr.z)
        if pr.kind == 'rocket':
            pr.smoke_t -= dt
            if pr.smoke_t <= 0.0:
                pr.smoke_t = 0.03
                w.fx.smoke(pr.x, pr.y, pr.z, 0.5, life=0.9)
                w.fx.fire(pr.x, pr.y, pr.z, 0.35)
        else:
            pr.np.setHpr(pr.np.getH() + 400 * dt, pr.np.getP() + 500 * dt, 0)
            if pr.kind == 'molotov' and random.random() < 0.4:
                w.fx.fire(pr.x, pr.y, pr.z + 0.15, 0.25)
        if pr.life <= 0.0:
            if pr.kind == 'molotov':
                self.ignite(pr.x, pr.y, max(0.0, pr.z), pr.owner)
            else:
                self.explode(pr.x, pr.y, max(0.2, pr.z), 7.0 if pr.kind == 'grenade' else 7.5, 240.0, pr.owner)
            return False
        return True

    # ------------------------------------------------------------------
    def explode(self, x, y, z, radius, damage, owner=None, size=1.0):
        w = self.w
        w.fx.explosion(x, y, z, size)
        w.audio.play_at('explosion', x, y, 1.0, 0.9 + random.random() * 0.2, 260.0)
        px, py = w.player.pos()
        d = math.hypot(px - x, py - y)
        if d < 60.0:
            w.fx.add_shake(1.0 - d / 60.0)
        by_player = owner is not None and owner.is_player
        for p in list(w.peds):
            if p.removed:
                continue
            dx, dy = p.x - x, p.y - y
            dd = math.hypot(dx, dy)
            if dd > radius:
                continue
            if p.vehicle is not None:
                continue
            k = 1.0 - dd / radius
            if dd > 2.0 and not w.static.los(x, y, p.x, p.y, 1.0):
                k *= 0.3
            n = dd or 1.0
            if not p.dead:
                p.hurt(damage * k, owner, 'explosion')
            if not p.is_player or p.dead:
                p.air = True
                p.vx, p.vy, p.vz = dx / n * 9.0 * k, dy / n * 9.0 * k, 3.0 + 6.0 * k
            elif k > 0.25 and not p.dead:
                p.knock_down(1.6, dx / n * 6.0 * k, dy / n * 6.0 * k, 4.0 * k)
        for v in list(w.vehicles):
            if v.removed:
                continue
            dx, dy = v.x - x, v.y - y
            dd = math.hypot(dx, dy) - v.spec.L * 0.3
            if dd > radius:
                continue
            k = 1.0 - max(0.0, dd) / radius
            n = math.hypot(dx, dy) or 1.0
            if v.mode == 1:
                w.traffic.knock(v, 10.0, owner)
            if v.mode != 0 or k > 0.4:
                if v.mode == 0:
                    v.set_mode(2)
                imp = 9.0 * k * (1300.0 / v.spec.mass) ** 0.5
                v.vx += dx / n * imp
                v.vy += dy / n * imp
                v.omega += random.uniform(-2.5, 2.5) * k
            v.damage(damage * 4.5 * k, by_player, 'explosion')
        # ломаем уличные объекты
        for ci in w.static.query_circles(x, y, radius * 0.7, 0xff):
            ref = w.static.circles[ci][5]
            if ref is not None and ref[0] == 'break':
                w.break_prop(ref[1], None, silent=True)
        w.on_explosion(x, y, owner)

    def ignite(self, x, y, z, owner=None):
        w = self.w
        w.audio.play_at('glass', x, y, 0.8, 1.0, 80.0)
        w.fx.flash(x, y, z + 0.5, 6.0, (1.0, 0.6, 0.2))
        gz = max(0.0, w.city.ground_z(x, y))
        for i in range(5):
            f = Flame()
            a = random.uniform(0, 6.283)
            r = 0.0 if i == 0 else random.uniform(0.8, 2.0)
            f.x, f.y, f.z = x + math.cos(a) * r, y + math.sin(a) * r, gz
            f.r = 1.5
            f.life = 6.0 + random.random() * 3.0
            f.owner = owner
            f.t = 0.0
            self.flames.append(f)
        w.fx.decal('scorch', x, y, 4.5, life=60.0)
        w.on_explosion(x, y, owner, fire=True)

    def _update_flames(self, dt):
        w = self.w
        keep = []
        self.flame_t -= dt
        tick = self.flame_t <= 0.0
        if tick:
            self.flame_t = 0.25
        for f in self.flames:
            f.life -= dt
            if f.life <= 0.0:
                continue
            keep.append(f)
            if random.random() < dt * 16.0:
                w.fx.fire(f.x + random.uniform(-0.6, 0.6), f.y + random.uniform(-0.6, 0.6), f.z + 0.3, 1.0)
            if random.random() < dt * 2.0:
                w.fx.smoke(f.x, f.y, f.z + 1.2, 0.9, dark=True)
            if not tick:
                continue
            r2 = f.r * f.r
            for p in w.peds:
                if p.dead or p.vehicle is not None:
                    continue
                dx, dy = p.x - f.x, p.y - f.y
                if dx * dx + dy * dy < r2 and p.z < f.z + 1.0:
                    if p.fire_t <= 0.0:
                        p.last_attacker = f.owner
                        if not p.is_player and p.voice_cd <= 0.0:
                            w.crowd.scream(p)
                    p.fire_t = 3.0 if not p.is_player else 1.2
            for v in w.vehicles:
                if v.dead:
                    continue
                dx, dy = v.x - f.x, v.y - f.y
                if dx * dx + dy * dy < (f.r + v.cr) ** 2:
                    v.damage(22.0, f.owner is not None and f.owner.is_player, 'fire')
        self.flames = keep
