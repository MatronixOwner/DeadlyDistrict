# -*- coding: utf-8 -*-
"""Игровой мир: все сущности, столкновения между ними и игровые события."""
import math
import random

from .city import City, WATER_Z
from .citymesh import CityMesh
from .collision import StaticWorld, F_PED
from .roadnet import RoadNet
from .vehicle import Vehicle
from .ped import Ped
from .fx import Fx
from .traffic import Traffic
from .crowd import Crowd
from .weapons import Weapons
from .police import Police
from .player import Player, Camera
from .models import Models
from .interiors import Interiors
from .defs import random_look, cop_look, medic_look, gang_look, W_PISTOL, W_SHOTGUN, W_FIST, WEAPONS
from .mathutil import clamp, angle_diff
from .audio import STATIONS

PROP_COLORS = {
    'lamp': (0.2, 0.2, 0.22), 'bench': (0.45, 0.3, 0.16), 'bin': (0.16, 0.22, 0.4), 'hydrant': (0.8, 0.12, 0.1),
    'newsbox': (0.75, 0.2, 0.15), 'mailbox': (0.15, 0.25, 0.6), 'cone': (0.95, 0.45, 0.08),
    'crate': (0.6, 0.45, 0.25), 'barrel': (0.3, 0.4, 0.5), 'tires': (0.08, 0.08, 0.08), 'umbrella': (0.85, 0.3, 0.2),
}


class World(object):

    def __init__(self, game, progress=None):
        self.game = game
        self.base = game.base
        self.assets = game.assets
        self.audio = game.audio
        self.settings = game.settings
        self.render = self.base.render
        self.root = self.render.attachNewNode('world')
        self.dyn_root = self.root.attachNewNode('dyn')
        self.time = 0.0
        self.dt = 0.016
        self.frame = 0
        self.vehicles = []
        self.peds = []
        self.emitters = []
        self.stats = dict(kills=0, cops=0, wrecks=0, wasted=0, busted=0, dist_car=0.0, dist_foot=0.0, stolen=0,
                          play_time=0.0, max_wanted=0, taxi=0, shots=0)

        def step(frac, text):
            if progress is not None:
                progress(frac, text)

        step(0.05, 'Строим город…')
        self.city = City(root=self.assets.root)
        self.roadnet = RoadNet(self.city)
        self.static = StaticWorld()
        step(0.15, 'Возводим кварталы…')
        self.citymesh = CityMesh(self.city, self.assets, self.static, self.root,
                                 progress=(lambda f: step(0.15 + 0.6 * f, 'Возводим кварталы…')))
        step(0.8, 'Заселяем улицы…')
        self.models = Models(self.assets, self.base.loader)
        self.models.preload()
        self.interiors = None
        self.fx = Fx(self)
        self.sky = None
        self.hud = None
        self.cam = Camera(self)
        self.player = Player(self)
        self.traffic = Traffic(self)
        self.crowd = Crowd(self)
        self.weapons = Weapons(self)
        self.police = Police(self)
        self.missions = None
        step(0.9, 'Обставляем комнаты…')
        self.interiors = Interiors(self)
        self._cam_fx = 0.0
        self._cam_fy = 1.0
        self.slowmo = 1.0
        self.respawn_t = 0.0
        self.respawn_kind = None
        self.hurt_cd = 0.0
        self.scene_engine = None          # (звук, громкость, тон) мотора в сценке
        self.engine_rate = 0.6
        self.radio_station = -1
        self.radio_pref = None             # станция, которую выбрал игрок: включается в любой машине
        self._music_hint = False
        self.cheat_fast = False

    # ------------------------------------------------------------------
    # сущности
    # ------------------------------------------------------------------
    def spawn_vehicle(self, kind, x, y, yaw, paint=None):
        v = Vehicle(self, kind, x, y, yaw, paint)
        self.vehicles.append(v)
        return v

    def spawn_ped(self, x, y, yaw, look, kind='civ'):
        p = Ped(self, x, y, yaw, look, kind)
        self.peds.append(p)
        return p

    def remove_vehicle(self, v):
        if v.removed:
            return
        for p in list(v.passengers):
            if not p.is_player:
                self.remove_ped(p)
        if v.driver is not None and not v.driver.is_player:
            self.remove_ped(v.driver)
        if v.is_player:
            self.player.leave_vehicle(force=True)
        v.remove()

    def remove_ped(self, p):
        if p.removed or p.is_player:
            return
        p.remove()

    def _sweep(self):
        if any(v.removed for v in self.vehicles):
            self.vehicles = [v for v in self.vehicles if not v.removed]
        if any(p.removed for p in self.peds):
            self.peds = [p for p in self.peds if not p.removed]

    def visible(self, x, y, margin=0.0):
        """Находится ли точка в поле зрения камеры (без учёта стен)."""
        cam = self.cam
        dx, dy = x - cam.x, y - cam.y
        f = dx * self._cam_fx + dy * self._cam_fy
        if f < -margin:
            return False
        l = abs(dy * self._cam_fx - dx * self._cam_fy)
        return l - margin < f * 1.25 + 2.0

    def map_pos(self):
        """Положение героя на карте города (в помещении — дверь здания, где он находится)."""
        its = self.interiors
        if its is not None:
            p = its.map_pos()
            if p is not None:
                return p
        return self.player.pos()

    def nearest_vehicle(self, x, y, maxd=10.0, cond=None):
        best = None
        bd = maxd
        for v in self.vehicles:
            if v.removed:
                continue
            d = math.hypot(v.x - x, v.y - y)
            if d < bd and (cond is None or cond(v)):
                bd = d
                best = v
        return best

    # ------------------------------------------------------------------
    def update(self, dt, inp):
        self.time += dt
        self.dt = dt
        self.frame += 1
        self.stats['play_time'] += dt
        pl = self.player
        cam = self.cam
        self._cam_fx, self._cam_fy = math.cos(cam.yaw), math.sin(cam.yaw)
        pl.update(dt, inp)
        its = self.interiors
        its.update(dt)
        room = its.current.name if its.current is not None else None
        indoor = room is not None
        if not indoor:
            # пока герой в помещении, улица стоит: её никто не видит, а всё останется на своих местах
            self.roadnet.update(dt)
            self.traffic.update(dt)
            for v in self.vehicles:
                v.update(dt)
            self.crowd.update(dt)
        for p in self.peds:
            if not p.is_player:
                if p.room != room:
                    continue
                if p.lod_far and (self.frame + id(p) // 8) % 2:
                    continue
                p.update(dt * 2.0 if p.lod_far else dt)
        pp = pl.ped
        if pp.state == 'down' or pp.air or pp.dead or pp.fire_t > 0.0:
            pp.update(dt)
        elif pl.state != 'car':
            pp._animate(dt)
        if not indoor:
            self._collide_vehicles()
        self._collide_peds(dt)
        self.weapons.update(dt)
        if not indoor:
            self.police.update(dt)
        if self.missions is not None:
            self.missions.update(dt)
        self._update_emitters(dt)
        self.fx.update(dt)
        self._sweep()
        if self.hurt_cd > 0.0:
            self.hurt_cd -= dt
        # пройденный путь
        sp = pl.speed()
        if pl.vehicle is not None:
            self.stats['dist_car'] += sp * dt
        else:
            self.stats['dist_foot'] += sp * dt
        if self.police.level > self.stats['max_wanted']:
            self.stats['max_wanted'] = self.police.level
        self.citymesh.update_signals(self.roadnet.time, self.roadnet.light_group)
        self.citymesh.scroll_water(self.time)
        t = self.time
        for v in self.vehicles:
            if v.siren:
                v.update_siren(t)
            elif v.siren_np is not None:
                v.update_siren(t)

    # ------------------------------------------------------------------
    # столкновения
    # ------------------------------------------------------------------
    def _collide_vehicles(self):
        vs = self.vehicles
        n = len(vs)
        PHYS = Vehicle.PHYS
        for i in range(n):
            a = vs[i]
            if a.sunk or a.removed:
                continue
            am = a.mode
            ax, ay, ar = a.x, a.y, a.radius
            for j in range(i + 1, n):
                b = vs[j]
                if am != PHYS and b.mode != PHYS:
                    continue
                rr = ar + b.radius
                dx = b.x - ax
                if dx > rr or dx < -rr:
                    continue
                dy = b.y - ay
                if dy > rr or dy < -rr or b.sunk or b.removed:
                    continue
                self._vv(a, b)

    def _vv(self, a, b):
        ca, sa = math.cos(a.yaw), math.sin(a.yaw)
        cb, sb = math.cos(b.yaw), math.sin(b.yaw)
        best = 0.0
        nx = ny = 0.0
        ra = a.cr
        rb = b.cr
        r = ra + rb
        r2 = r * r
        oa_best = ob_best = 0.0
        for oa in a.circles:
            pax = a.x + ca * oa
            pay = a.y + sa * oa
            for ob in b.circles:
                ddx = b.x + cb * ob - pax
                ddy = b.y + sb * ob - pay
                d2 = ddx * ddx + ddy * ddy
                if d2 < r2:
                    d = math.sqrt(d2)
                    pen = r - d
                    if pen > best:
                        best = pen
                        if d > 1e-4:
                            nx, ny = ddx / d, ddy / d
                        else:
                            nx, ny = 1.0, 0.0
                        oa_best, ob_best = oa, ob
        if best <= 0.0:
            return
        PHYS, RAIL, PARKED = Vehicle.PHYS, Vehicle.RAIL, Vehicle.PARKED
        vrel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
        closing = -vrel
        # будим припаркованные и сбиваем с «рельс» при сильном ударе
        for u, o in ((a, b), (b, a)):
            if u.mode == PARKED and closing > 0.8:
                u.set_mode(PHYS)
            elif u.mode == RAIL and (closing > 3.2 or (closing > 1.5 and o.is_player)):
                self.traffic.knock(u, closing, o.driver if o.driver is not None else None)
        ima = 1.0 / a.spec.mass if a.mode == PHYS else 0.0
        imb = 1.0 / b.spec.mass if b.mode == PHYS else 0.0
        tot = ima + imb
        if tot <= 0.0:
            return
        ka, kb = ima / tot, imb / tot
        a.x -= nx * best * ka
        a.y -= ny * best * ka
        b.x += nx * best * kb
        b.y += ny * best * kb
        if vrel < 0.0:
            jimp = -(1.25) * vrel / tot
            a.vx -= jimp * ima * nx
            a.vy -= jimp * ima * ny
            b.vx += jimp * imb * nx
            b.vy += jimp * imb * ny
            # закручивание от удара не по центру масс
            cra = (ca * oa_best) * ny - (sa * oa_best) * nx
            crb = (cb * ob_best) * ny - (sb * ob_best) * nx
            a.omega = clamp(a.omega - jimp * ima * cra * 0.45, -3.0, 3.0)
            b.omega = clamp(b.omega + jimp * imb * crb * 0.45, -3.0, 3.0)
            if closing > 1.6:
                cx = a.x + ca * oa_best + nx * ra
                cy = a.y + sa * oa_best + ny * ra
                ma, mb = a.spec.mass, b.spec.mass
                self.on_vehicle_impact(a, closing * 2.0 * mb / (ma + mb), cx, cy, b)
                self.on_vehicle_impact(b, closing * 2.0 * ma / (ma + mb), cx, cy, a, sound=False)

    def _collide_peds(self, dt):
        pl = self.player
        pp = pl.ped
        for v in self.vehicles:
            if v.sunk or v.removed:
                continue
            vx, vy = v.vx, v.vy
            fast = (vx * vx + vy * vy) > 4.0 and v.mode != Vehicle.PARKED
            R = v.radius + 0.6
            x, y = v.x, v.y
            c = s = None
            for p in self.peds:
                dx = p.x - x
                if dx > R or dx < -R:
                    continue
                dy = p.y - y
                if dy > R or dy < -R or p.vehicle is not None or p.removed:
                    continue
                st = p.state
                if st == 'dead' or p.air:
                    continue
                if c is None:
                    c, s = math.cos(v.yaw), math.sin(v.yaw)
                r = v.cr + p.radius * 0.7
                best = 0.0
                nx = ny = 0.0
                for o in v.circles:
                    ddx = p.x - (x + c * o)
                    ddy = p.y - (y + s * o)
                    d2 = ddx * ddx + ddy * ddy
                    if d2 < r * r:
                        d = math.sqrt(d2) or 0.001
                        if r - d > best:
                            best = r - d
                            nx, ny = ddx / d, ddy / d
                if best <= 0.0:
                    continue
                if p.is_player and (pl.jump_z > 1.0):
                    continue
                vn = vx * nx + vy * ny
                if fast and vn > 2.4:
                    if st == 'down':
                        if p.voice_cd <= 0.0:
                            p.voice_cd = 0.5
                            p.hurt(30.0, v.driver, 'vehicle')
                        continue
                    self._run_over(v, p, vn, nx, ny)
                elif st != 'down':
                    p.x += nx * best
                    p.y += ny * best
                    if st == 'walk' and not p.is_player and vn > 0.3:
                        p.stuck_t += dt
        # игрок расталкивает прохожих
        if pl.vehicle is None and not pp.dead:
            px, py = pp.x, pp.y
            for p in self.peds:
                if p is pp or p.vehicle is not None:
                    continue
                dx = p.x - px
                if dx > 0.7 or dx < -0.7:
                    continue
                dy = p.y - py
                if dy > 0.7 or dy < -0.7 or p.state in ('dead', 'down'):
                    continue
                d2 = dx * dx + dy * dy
                if d2 < 0.49:
                    d = math.sqrt(d2) or 0.01
                    k = (0.7 - d)
                    if p.fixed:
                        pp.x -= dx / d * k
                        pp.y -= dy / d * k
                        continue
                    p.x += dx / d * k * 0.7
                    p.y += dy / d * k * 0.7
                    pp.x -= dx / d * k * 0.3
                    pp.y -= dy / d * k * 0.3
        for p in self.peds:
            if p.voice_cd > 0.0:
                p.voice_cd -= dt

    def _run_over(self, v, p, vn, nx, ny):
        drv = v.driver
        by_player = v.is_player
        dmg = (vn - 1.2) * 7.0 * (1.0 if v.spec.mass < 3000 else 1.4)
        if p.is_player:
            dmg *= 0.55
        self.audio.play_at('punch', p.x, p.y, 1.0, 0.7, 70.0)
        self.audio.play_at('crash1', p.x, p.y, 0.3, 0.8, 60.0)
        if self.settings.get('blood') and dmg > 25:
            self.fx.blood(p.x, p.y, p.z + 1.0, 5, nx, ny)
        p.last_attacker = drv
        dead = p.hurt(dmg, drv, 'vehicle')
        k = 0.85
        p.knock_down(2.0 + random.random() * 2.0, v.vx * k + nx * 2.0, v.vy * k + ny * 2.0, 2.0 + vn * 0.22)
        v.vx *= 0.975
        v.vy *= 0.975
        if by_player:
            self.fx.add_shake(0.15)
            if not dead:
                self.police.crime('hit_ped', p.x, p.y)

    # ------------------------------------------------------------------
    # пассажиры и водители
    # ------------------------------------------------------------------
    def make_driver(self, v):
        """Превратить «виртуального» водителя трафика в настоящего персонажа."""
        zone = self.city.zone_style(self.city.zone_at(v.x, v.y))
        if zone not in 'DOGRIB' or len(zone) != 1:
            zone = 'D'
        if v.kind in ('police', 'enforcer', 'fbi', 'army') or v.owner == 'police':
            p = self.police.make_cop(v.x, v.y, v.yaw, v.kind)
        elif v.kind == 'ambulance':
            p = self.spawn_ped(v.x, v.y, v.yaw, medic_look(), 'civ')
        else:
            p = self.spawn_ped(v.x, v.y, v.yaw, v.driver_look or random_look(random, zone), 'civ')
            p.spawned = True
        v.npc = False
        return p

    def carjack(self, v, side=-1):
        drv = v.driver
        if drv is not None and drv.is_player:
            return None
        if drv is None:
            if not v.npc:
                return None
            drv = self.make_driver(v)
        else:
            drv.vehicle = None
            drv.node.show()
            v.driver = None
        x, y = v.door_pos(side)
        fx_, fy_ = math.cos(v.yaw), math.sin(v.yaw)
        drv.x, drv.y = x + fx_ * 0.9, y + fy_ * 0.9
        drv.z = self.city.ground_z(drv.x, drv.y)
        pp = self.player.ped
        drv.last_attacker = pp
        drv.threat = (pp.x, pp.y)
        drv.knock_down(1.2 + random.random(), -fy_ * side * 1.5, fx_ * side * 1.5, 1.0)
        if drv.kind == 'civ' and random.random() < 0.18:
            drv.target = pp               # смельчак лезет в драку
        self.crowd.scream(drv)
        if drv.kind in ('cop', 'swat', 'fbi', 'army'):
            self.police.crime('assault_cop', v.x, v.y)
            self.police.cops.append(drv)
            drv.target = pp
        else:
            self.police.crime('carjack', v.x, v.y)
        self.stats['stolen'] += 1
        return drv

    def put_in_vehicle(self, ped, v, driver=False):
        ped.vehicle = v
        ped.set_state('in_car')
        ped.aiming = False
        ped.speed = 0.0
        ped.node.hide()
        if driver:
            v.driver = ped
        elif ped not in v.passengers:
            v.passengers.append(ped)

    def take_out(self, ped, side=1):
        v = ped.vehicle
        if v is None:
            return
        if v.driver is ped:
            v.driver = None
        if ped in v.passengers:
            v.passengers.remove(ped)
        ped.vehicle = None
        x, y = v.door_pos(side)
        if self.static.overlap_circle(x, y, ped.radius, F_PED):
            x, y = v.door_pos(-side)
        ped.x, ped.y = x, y
        ped.z = self.city.ground_z(x, y)
        ped.yaw = v.yaw
        ped.node.show()
        ped.set_state('stand')
        ped.sync()

    def eject(self, ped, dead=False):
        if ped.is_player:
            self.player.leave_vehicle(force=True)
            return
        self.take_out(ped)

    # ------------------------------------------------------------------
    # события
    # ------------------------------------------------------------------
    def break_prop(self, br, by=None, silent=False):
        if not self.citymesh.break_prop(br):
            return
        col = PROP_COLORS.get(br.kind, (0.5, 0.5, 0.5))
        self.fx.debris(br.x, br.y, 0.8, 5, col, 5.0, 0.3)
        if not silent:
            self.audio.play_at('glass' if br.kind == 'lamp' else 'break', br.x, br.y, 0.8,
                               0.85 + random.random() * 0.3, 70.0)
        if br.kind == 'hydrant':
            self.emitters.append(['water', br.x, br.y, self.time + 25.0, 0.0])
            self.audio.play_at('splash', br.x, br.y, 0.6, 1.2, 60.0)
        elif br.kind == 'lamp':
            self.fx.sparks(br.x, br.y, 4.5, 6)
        if by is not None and by.is_player and self.missions is not None:
            self.missions.notify('prop', br)

    def _update_emitters(self, dt):
        if not self.emitters:
            return
        keep = []
        t = self.time
        for e in self.emitters:
            if t > e[3]:
                continue
            keep.append(e)
            e[4] -= dt
            if e[4] <= 0.0:
                e[4] = 0.05
                if e[0] == 'water':
                    self.fx.spawn('smoke', e[1], e[2], 0.4, random.uniform(-0.8, 0.8), random.uniform(-0.8, 0.8),
                                  random.uniform(8, 11), 1.1, 0.5, 1.6, (0.75, 0.88, 1.0), 0.6, grav=12.0)
        self.emitters = keep

    def on_vehicle_impact(self, v, imp, x, y, other, sound=True):
        by_player = v.is_player or (other is not None and other.is_player)
        if imp > 2.6:
            v.damage((imp - 2.6) * 10.0, by_player, 'crash')
            v.hits += 1
        if sound and v.col_cd <= 0.0:
            v.col_cd = 0.22
            vol = clamp(imp / 13.0, 0.15, 1.0)
            self.audio.play_at('crash2' if imp > 9.0 else 'crash1', x, y, vol, 0.85 + random.random() * 0.3, 90.0)
            self.fx.sparks(x, y, 0.6, 2 + int(min(6, imp * 0.4)))
            if imp > 7.0:
                self.fx.debris(x, y, 0.7, 3, (0.25, 0.25, 0.27), 4.0, 0.2)
        if v.is_player:
            self.fx.add_shake(min(0.5, imp * 0.03))
            if imp > 13.0:
                self.player.ped.hurt((imp - 13.0) * 1.3, None, 'crash')
        if other is not None and other.is_player and v.owner == 'police' and imp > 4.0:
            self.police.crime('ram_cop', x, y)
        if self.missions is not None and by_player:
            self.missions.notify('impact', v, imp)

    def on_vehicle_sunk(self, v):
        self.fx.splash(v.x, v.y, WATER_Z, 2.2)
        self.audio.play_at('splash', v.x, v.y, 1.0, 0.8, 120.0)
        v.npc = False
        v.ai = None
        if v.is_player:
            pp = self.player.ped
            if not pp.dead:
                pp.health = 0.0
                pp.dead = True
                pp.set_state('dead')
                self.on_ped_died(pp, None, 'drown')
        for p in list(v.passengers):
            if not p.dead and not p.is_player:
                p.dead = True
                cb = p.on_death
                p.on_death = None
                if cb is not None:
                    cb(p, None)
        if self.missions is not None:
            self.missions.notify('vehicle_destroyed', v)

    def on_vehicle_exploded(self, v, by_player):
        owner = self.player.ped if by_player else None
        self.stats['wrecks'] += 1
        had_npc = v.npc
        v.npc = False
        v.traffic = False
        if v.is_player:
            pp = self.player.ped
            if not pp.dead:
                pp.hurt(1000.0, None, 'explosion')
        drv = v.driver
        if drv is not None and not drv.is_player and not drv.dead:
            drv.die(owner, 'explosion')
        for p in list(v.passengers):
            if not p.dead and not p.is_player:
                p.die(owner, 'explosion')
        self.weapons.explode(v.x, v.y, v.z + 0.6, 6.0, 150.0, owner, 1.25)
        if by_player:
            self.police.crime('destroy', v.x, v.y)
            if had_npc:
                self.stats['kills'] += 1
                self.police.crime('kill_cop' if v.owner == 'police' else 'kill', v.x, v.y)
        if self.missions is not None:
            self.missions.notify('vehicle_destroyed', v)

    def on_vehicle_shot(self, v, shooter, hx, hy, hz, dx, dy, dz, melee=False):
        by_player = shooter is not None and shooter.is_player
        if v.npc and v.owner is None and not v.dead:
            if not melee and hz > v.z + v.spec.belt and random.random() < 0.1:
                # пуля досталась водителю
                v.npc = False
                if v.mode == Vehicle.RAIL:
                    v.set_mode(Vehicle.PHYS)
                v.ai = None
                v.in_throttle = 0.0
                if by_player:
                    self.stats['kills'] += 1
                    self.police.crime('kill', v.x, v.y)
                self.audio.play_at('horn', v.x, v.y, 0.7, 0.9, 80.0)
            else:
                self.traffic.scare(v)
        if by_player:
            self.police.crime('assault_cop' if v.owner == 'police' else 'shoot_car', v.x, v.y)
            if self.missions is not None:
                self.missions.notify('vehicle_shot', v)

    def on_gunfire(self, ped, x, y, loud=False):
        self.crowd.panic(x, y, 60.0 if loud else 36.0, ped)
        if ped.is_player:
            self.stats['shots'] += 1
            self.police.crime('gunfire', x, y)

    def on_explosion(self, x, y, owner, fire=False):
        self.crowd.panic(x, y, 45.0 if fire else 70.0, owner)
        if owner is not None and owner.is_player:
            self.police.crime('explosion', x, y, 0.5 if fire else 1.0)

    def on_ped_hurt(self, ped, attacker, cause):
        if ped.voice_cd <= 0.0 and cause != 'fire':
            ped.voice_cd = 0.8
            self.audio.play_at('ouch_f' if ped.look.female else 'ouch_m', ped.x, ped.y, 0.7,
                               0.9 + random.random() * 0.2, 50.0)
        if attacker is None or not attacker.is_player:
            return
        if ped.kind in ('cop', 'swat', 'fbi', 'army'):
            self.police.crime('assault_cop', ped.x, ped.y)
        elif ped.kind in ('civ', 'gang'):
            self.police.crime('assault', ped.x, ped.y)
        if ped.gang is not None:
            # свои своих не бросают
            for o in self.peds:
                if o.gang == ped.gang and o is not ped and not o.dead and o.target is None and \
                        o.state in ('walk', 'wait', 'idle', 'guard', 'stand'):
                    if abs(o.x - ped.x) < 30.0 and abs(o.y - ped.y) < 30.0:
                        o.attack(attacker)
        if self.missions is not None:
            self.missions.notify('ped_hurt', ped)

    def on_ped_died(self, ped, killer, cause):
        if self.settings.get('blood') and cause != 'drown':
            self.fx.decal('blood', ped.x, ped.y, 1.6 + random.random() * 0.8, life=45.0)
        if ped.is_player:
            self.stats['wasted'] += 1
            self.player.on_death()
            self.respawn_kind = 'wasted'
            self.respawn_t = 0.0
            self.audio.play('wasted', 0.9)
            self.audio.play('scream_m', 0.6, 0.85)
            if self.missions is not None:
                self.missions.notify('player_dead', None)
            return
        if ped.voice_cd <= 0.3:
            self.audio.play_at('scream_f' if ped.look.female else 'scream_m', ped.x, ped.y, 0.7,
                               0.8 + random.random() * 0.2, 60.0)
        by_player = killer is not None and killer.is_player
        if by_player:
            self.stats['kills'] += 1
            if ped.kind in ('cop', 'swat', 'fbi', 'army'):
                self.stats['cops'] += 1
                self.police.crime('kill_cop', ped.x, ped.y)
            elif ped.kind in ('civ', 'gang', 'mission'):
                self.police.crime('kill', ped.x, ped.y)
        if self.missions is not None:
            self.missions.on_ped_died(ped, killer, by_player)
        self.crowd.panic(ped.x, ped.y, 14.0, killer)

    def on_player_hurt(self, amount, attacker, cause):
        if self.hud is not None:
            self.hud.damage_flash(amount)
        if self.hurt_cd <= 0.0 and amount > 3.0:
            self.hurt_cd = 0.6
            self.audio.play('ouch_m', 0.6, 0.95 + random.random() * 0.1)

    def on_player_busted(self):
        pl = self.player
        if pl.state in ('dead', 'busted'):
            return
        self.stats['busted'] += 1
        pl.bust()
        pp = pl.ped
        pp.fire_t = 0.0
        for p in self.peds:                 # арест состоялся: прекратить огонь
            if p.target is pp:
                p.target = None
                p.aiming = False
        self.respawn_kind = 'busted'
        self.respawn_t = 0.0
        self.audio.play('failed', 0.8)
        if self.missions is not None:
            self.missions.notify('player_busted', None)

    def on_player_enter_vehicle(self, v, stolen):
        if self.hud is not None:
            self.hud.vehicle_name(v.spec.title)
        if v.kind == 'police' and not getattr(v, 'looted', False):
            v.looted = True
            self.player.give_weapon(W_SHOTGUN, 5, select=False)
            if self.hud is not None:
                self.hud.help('В патрульной машине нашёлся дробовик.', 4.0)
        if self.missions is not None:
            self.missions.notify('enter_vehicle', v)

    def on_player_leave_vehicle(self, v):
        if self.missions is not None:
            self.missions.notify('leave_vehicle', v)

    def on_wanted_cleared(self):
        pass

    # ------------------------------------------------------------------
    def update_audio(self, dt):
        """Петли: мотор, занос, сирена, радио."""
        au = self.audio
        pl = self.player
        cam = self.cam
        au.set_listener(cam.x, cam.y)
        v = pl.vehicle
        if v is not None and not v.dead:
            sp = abs(v.speed)
            top = v.spec.top
            # условные «передачи», чтобы звук мотора не рос монотонно
            g = sp / top * 4.0
            frac = g - int(g) if g < 4.0 else 1.0
            rate = 0.55 + 0.25 * min(g, 4.0) / 4.0 + 0.5 * frac + abs(v.in_throttle) * 0.12
            self.engine_rate += (rate - self.engine_rate) * min(1.0, dt * 6.0)
            ev = 0.33 + 0.3 * abs(v.in_throttle) + 0.1 * min(1.0, sp / 20.0)
            if au.radio_playing():
                ev *= 0.5                       # с включённым радио мотор тише, как в салоне
            au.loop('engine', 'engine_truck' if v.spec.engine == 'truck' else 'engine', ev, self.engine_rate)
            slip = abs(v.slip)
            if (slip > 3.0 or (v.in_handbrake and sp > 5.0)) and sp > 3.0:
                au.loop('skid', 'skid', min(0.7, 0.25 + slip * 0.06), 0.9 + min(0.3, slip * 0.02))
            else:
                au.loop('skid', None)
        elif self.scene_engine is not None:
            # сценка: слышен мотор машины, которую показывает камера
            au.loop('engine', self.scene_engine[0], self.scene_engine[1], self.scene_engine[2])
            au.loop('skid', None)
        else:
            au.loop('engine', None)
            au.loop('skid', None)
        # сирены: ближайшая слышна
        best = 1e9
        for o in self.vehicles:
            if o.siren and not o.dead:
                d = (o.x - cam.x) ** 2 + (o.y - cam.y) ** 2
                if d < best:
                    best = d
        if best < 150.0 * 150.0:
            k = 1.0 - math.sqrt(best) / 150.0
            au.loop('siren', 'siren', 0.6 * k * k + 0.05, 1.0)
        else:
            au.loop('siren', None)
        # радио
        st = -1
        if v is not None and v.spec.radio and not v.dead and pl.state == 'car':
            st = v.radio
        changed = st != self.radio_station
        if changed:
            self.radio_station = st
            au.set_station(st)
        title = au.update_radio()
        if st >= 0 and self.hud is not None and (title or changed):
            self.hud.radio_changed(STATIONS[st][0], title)
            if changed and STATIONS[st][1] == 'user' and au.user_tracks == 0 and not self._music_hint:
                self._music_hint = True
                self.hud.help('«Астрахань FM» играет ваши песни: положите файлы mp3 в папку music рядом с игрой. '
                              'N — следующая песня.', 9.0)
        sky = self.sky
        if sky is not None:
            k = 0.3 if sky.indoor is not None else 1.0          # за стенами улицу слышно глухо
            au.loop('rain', 'rain' if sky.rain > 0.05 else None, 0.55 * sky.rain * k)
            au.loop('amb', 'ambience', 0.22 * (0.5 + 0.5 * (1.0 - sky.night)) * k)
