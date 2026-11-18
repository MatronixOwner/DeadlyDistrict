# -*- coding: utf-8 -*-
"""Гараж у дома Макса: машина, которую загнали внутрь и оставили, остаётся за игроком.

Она не исчезает, когда герой уходит, попадает в сохранение вместе с цветом и тюнингом и ждёт на
своём месте после загрузки.  Мест — по числу парковочных клеток (три).  Ворота поднимаются сами,
когда герой подходит или подъезжает.

Здесь же — машина героя, «Ласточка» (HeroCar): она своя с самого начала и стоит в этом гараже.
"""
import math

from .meshbuilder import MeshBuilder
from .vehicle import Vehicle, SPECS

OPEN_AT = 13.0              # с какого расстояния ворота начинают открываться
SPEED = 1.6                 # полных ходов ворот в секунду
HERO_KIND = 'retro'         # машина героя (vehicle.SPECS)
HERO_BACK = 25.0            # через сколько секунд пропавшая машина героя снова стоит у дома
HERO_FAR = 90.0             # …если герой в это время не ближе стольких метров от гаража
HERO_NEAR = 40.0            # ближе к гаражу машина считается стоящей «у дома»: её не перегоняют


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
                    if not v.removed and v is not mine and not v.hero:
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
        # техника, которой в игре больше нет (старые сохранения), места в гараже не занимает
        known = [it for it in (items or []) if it.get('kind') in SPECS]
        for it in known[:self.capacity()]:
            kind = it.get('kind')
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


class HeroCar(object):
    """Машина героя — «Ласточка».

    Она одна на весь город и своя с первой минуты: за её угон не ищут, на карте она отмечена значком.
    Ждёт в гараже у дома.  Если её разбили, утопили или она пропала, через некоторое время она снова стоит
    в гараже — в той же окраске и с тем же тюнингом.  Оставленную где-то в городе пригоняют к дому, пока герой
    спит (сохранение у кровати): после загрузки она всё равно стояла бы в гараже."""

    def __init__(self, world):
        self.w = world
        self.v = None
        self.paint = 0
        self.tune = {}
        self.lost_t = 0.0
        self.blip = None
        self.enabled = True                 # False — «Ласточки» в этой игре нет: её не ставят и не возвращают

    def reset(self):
        """Мир очищен (новая игра, выход в меню): машину уже убрали вместе со всеми остальными."""
        self._unblip()
        self.enabled = True
        self.v = None
        self.paint = 0
        self.tune = {}
        self.lost_t = 0.0

    def _unblip(self):
        if self.blip is not None:
            self.w.hud.remove_blip(self.blip)
            self.blip = None

    def alive(self):
        v = self.v
        return v is not None and not v.removed and not v.dead and not v.sunk

    def adopt(self, v):
        v.hero = True
        v.keep = True
        v.owner = 'player'
        v.stolen = True                     # своя: в счёт угонов не идёт
        self.v = v
        self.lost_t = 0.0

    def spawn_home(self):
        """Поставить машину у дома: в свободную клетку гаража, а если гараж занят — на площадку перед воротами."""
        w = self.w
        g = w.garage
        if not self.enabled or not g.ok or HERO_KIND not in SPECS:
            return None
        for c in list(w.vehicles):              # остов прежней машины места в гараже не занимает
            if c.dead and not c.removed and not c.is_player and g.contains(c.x, c.y):
                c.keep = False
                w.remove_vehicle(c)
        g.cars = [c for c in g.cars if not c.removed and not c.dead]
        spot = None
        for (sx, sy) in g.slots:
            if not any(not c.removed and (c.x - sx) ** 2 + (c.y - sy) ** 2 < 2.4 ** 2 for c in w.vehicles):
                spot = (sx, sy)
                break
        inside = spot is not None
        if not inside:
            x0, y0, x1, y1 = g.rect
            spot = ((x0 + x1) * 0.5, y0 - 4.2)
            for c in list(w.vehicles):          # площадка должна быть свободна
                if not c.keep and (c.x - spot[0]) ** 2 + (c.y - spot[1]) ** 2 < 4.5 ** 2:
                    w.remove_vehicle(c)
        v = w.spawn_vehicle(HERO_KIND, spot[0], spot[1], g.yaw, self.paint)
        v.mode = Vehicle.PARKED
        if self.tune:
            v.apply_tune(dict(self.tune))
        self.adopt(v)
        if inside and len(g.cars) < g.capacity():
            g.cars.append(v)
            v.garage = True
        return v

    def remove(self):
        """Убрать машину из игры насовсем (свободный город без «Ласточки»: так начинают проверки)."""
        w = self.w
        v = self.v
        self.reset()
        self.enabled = False
        if v is not None and not v.removed:
            if v in w.garage.cars:
                w.garage.cars.remove(v)
            v.keep = False
            w.remove_vehicle(v)

    def update(self, dt):
        w = self.w
        pl = w.player
        if not self.enabled:
            return
        if self.alive():
            v = self.v
            self.paint = int(v.paint)
            self.tune = dict(v.tune or {})
            self.lost_t = 0.0
            # значок на карте — пока герой не за её рулём
            if pl.vehicle is v:
                self._unblip()
            elif self.blip is None:
                self.blip = w.hud.add_blip('blip_car', obj=v, scale=1.0, edge=False)
            return
        self._unblip()
        old = self.v
        if old is not None and old.hero:
            old.hero = False                    # разбитая машина — обычный остов: его уберут, как любой другой
            old.keep = False
        ms = w.missions
        if ms is None or ms.intro is not None or w.respawn_kind is not None:
            return
        self.lost_t += dt
        g = w.garage
        if self.lost_t < HERO_BACK or not g.ok:
            return
        px, py = pl.pos()
        if math.hypot(px - g.cx, py - g.cy) < HERO_FAR and self.v is not None:
            return                              # на глазах у героя машины не появляются
        had = self.v is not None
        if self.spawn_home() is not None and had:
            w.hud.help('«Ласточку» вернули в гараж у дома.', 6.0)

    def away(self):
        """Машины нет у дома: она оставлена где-то в городе, разбита или пропала."""
        w = self.w
        g = w.garage
        if not self.enabled or not g.ok:
            return False
        v = self.v
        if self.alive():
            return w.player.vehicle is not v and math.hypot(v.x - g.cx, v.y - g.cy) >= HERO_NEAR
        return True

    def come_home(self):
        """Герой лёг спать дома: машину, которой нет у дома, за это время пригоняют в гараж.
        Возвращает True, если её пришлось перегонять."""
        w = self.w
        if not self.away():
            return False
        v = self.v
        if self.alive():
            self.paint = int(v.paint)
            self.tune = dict(v.tune or {})
            v.hero = False
            v.keep = False
            w.remove_vehicle(v)
        self._unblip()
        return self.spawn_home() is not None

    # ------------------------------------------------------------------
    def state(self):
        """Для сохранения: окраска и тюнинг (место — всегда гараж у дома)."""
        if not self.enabled:
            return dict(off=True)
        return dict(paint=int(self.paint), tune=dict(self.tune or {}))

    def restore(self, info):
        """После загрузки: машина героя — та «Ласточка», что стоит в гараже; если её там нет — ставим.
        В сохранениях прежних версий записи о ней нет: там она просто появляется в гараже."""
        w = self.w
        self.reset()
        if info and info.get('off'):
            self.enabled = False
            return
        if info:
            self.paint = int(info.get('paint', 0))
            self.tune = dict(info.get('tune') or {})
        for c in w.garage.cars:
            if c.kind == HERO_KIND and not c.removed:
                self.adopt(c)
                return
        self.spawn_home()
