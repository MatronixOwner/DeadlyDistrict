# -*- coding: utf-8 -*-
"""Гараж у дома Макса: машина, которую загнали внутрь и оставили, остаётся за игроком.

Она не исчезает, когда герой уходит, попадает в сохранение вместе с цветом и тюнингом и ждёт на
своём месте после загрузки.  Мест — по числу парковочных клеток (три).  Ворота поднимаются сами,
когда герой подходит или подъезжает.
"""
import math

from .meshbuilder import MeshBuilder
from .vehicle import Vehicle, SPECS

OPEN_AT = 13.0              # с какого расстояния ворота начинают открываться
SPEED = 1.6                 # полных ходов ворот в секунду


class Garage(object):

    def __init__(self, world):
        self.w = world
        info = world.city.special.get('garage')
        self.ok = info is not None
        self.cars = []
        self.k = 0.0                    # ворота: 0 — закрыты, 1 — открыты
        self.dirty = False
        self.full_msg = None
        self.inside = False
        if not self.ok:
            return
        self.rect = info['rect']
        self.slots = info['slots']
        self.yaw = info['yaw']
        self.z = info['z']
        self.h = info['h']
        self.front = info['front']
        x0, y0, x1, y1 = self.rect
        self.cx, self.cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
        # ворота: секционное полотно, уходит под крышу
        mb = MeshBuilder()
        mb.box('corrugated', 0.0, -0.05, -(self.h - 0.12), x1 - x0, 0.05, 0.0, (0.86, 0.86, 0.84, 1), uv_m=2.0)
        self.door = mb.build('garage_door', world.assets.apply_state)
        self.door.reparentTo(world.fx.root)
        self.door.setPos(x0, y0, self.z + self.h - 0.02)
        self._pose()

    # ------------------------------------------------------------------
    def _pose(self):
        if self.ok:
            self.door.setSz(max(0.04, 1.0 - 0.96 * self.k))

    def contains(self, x, y, margin=0.0):
        if not self.ok:
            return False
        x0, y0, x1, y1 = self.rect
        return x0 + margin <= x <= x1 - margin and y0 + margin <= y <= y1 - margin

    def capacity(self):
        return len(self.slots) if self.ok else 0

    def reset(self):
        """Новая игра: гараж пуст."""
        w = self.w
        for v in self.cars:
            if not v.removed:
                v.keep = False
                w.remove_vehicle(v)
        self.cars = []
        self.dirty = False
        self.k = 0.0
        self._pose()

    # ------------------------------------------------------------------
    def update(self, dt):
        if not self.ok:
            return
        w = self.w
        pl = w.player
        px, py = pl.pos()
        # ворота
        d = math.hypot(px - self.cx, py - (self.rect[1] - 1.0))
        want = 1.0 if (d < OPEN_AT or self.contains(px, py)) and w.interiors.current is None else 0.0
        if self.k != want:
            if abs(self.k - want) > 0.98:
                w.audio.play_at('garage', self.cx, self.rect[1], 0.7)
            self.k += SPEED * dt if want > self.k else -SPEED * dt
            self.k = max(0.0, min(1.0, self.k))
            self._pose()
        if d > 60.0:
            return
        # что стоит внутри
        mine = pl.vehicle
        found = []
        for v in w.vehicles:
            if v.removed or v.dead or v.sunk or v is mine or v.npc or v.mission is not None:
                continue
            if self.contains(v.x, v.y, 0.3) and abs(v.speed) < 0.8:
                found.append(v)
        for v in found:
            if v in self.cars:
                continue
            if len(self.cars) >= self.capacity():
                if self.full_msg is not v:
                    self.full_msg = v
                    w.hud.help('Гараж полон: эта машина не сохранится. Выгони одну из тех, что стоят внутри.', 6.0)
                continue
            self.cars.append(v)
            v.keep = True
            v.garage = True
            v.mode = Vehicle.PARKED
            self.dirty = True
            w.hud.big('Машина в гараже', (0.42, 0.74, 0.38, 1.0), 3.0, v.spec.title)
            w.audio.play('pickup', 0.7)
        for v in list(self.cars):
            if v.removed or v.dead or v not in found:
                if v is not mine or not self.contains(v.x, v.y, 0.3):
                    self.cars.remove(v)
                    v.garage = False
                    if not v.removed and v is not mine:
                        v.keep = False
                    self.dirty = True
        if self.full_msg is not None and self.full_msg not in found:
            self.full_msg = None
        # перемена в гараже записывается сразу (если не идёт задание — оно сохранит всё само в конце)
        if self.dirty and w.missions is not None and w.missions.active is None and pl.state == 'foot':
            self.dirty = False
            w.missions.save_game(auto=True)

    # ------------------------------------------------------------------
    def state(self):
        """Содержимое гаража для сохранения."""
        out = []
        for v in self.cars:
            if v.removed or v.dead:
                continue
            out.append(dict(kind=v.kind, paint=int(v.paint), x=round(v.x, 2), y=round(v.y, 2), yaw=round(v.yaw, 3),
                            hp=round(float(v.health), 1), tune=dict(getattr(v, 'tune', None) or {})))
        return out

    def restore(self, items):
        """Расставить машины из сохранения."""
        if not self.ok:
            return
        w = self.w
        self.reset()
        free = list(self.slots)
        for it in (items or [])[:self.capacity()]:
            kind = it.get('kind')
            if kind not in SPECS:
                continue
            x, y, yaw = float(it.get('x', 0.0)), float(it.get('y', 0.0)), float(it.get('yaw', self.yaw))
            if not self.contains(x, y, 0.2):
                x, y = free[0]
                yaw = self.yaw
            # занятую клетку вычёркиваем
            free.sort(key=lambda s: (s[0] - x) ** 2 + (s[1] - y) ** 2)
            if free:
                free.pop(0)
            v = w.spawn_vehicle(kind, x, y, yaw, int(it.get('paint', 0)))
            v.keep = True
            v.garage = True
            v.mode = Vehicle.PARKED
            v.health = max(200.0, min(v.max_health, float(it.get('hp', v.max_health))))
            tune = it.get('tune') or {}
            if tune and hasattr(v, 'apply_tune'):
                v.apply_tune(tune)
            self.cars.append(v)
        self.dirty = False
