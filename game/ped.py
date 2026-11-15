# -*- coding: utf-8 -*-
"""Персонажи: низкополигональная модель, анимация, поведение."""
import math
import random

from panda3d.core import NodePath

from .meshbuilder import MeshBuilder
from .mathutil import clamp, approach, wrap_angle, angle_diff, turn_towards, yaw_to_h, damp, DEG
from .collision import F_PED, F_SIGHT
from .defs import WEAPONS, W_FIST, W_BAT, W_PISTOL
from .city import WATER_Z

_gun_cache = {}
_shadow = [None]


def _c(c, k=1.0):
    return (c[0] * k, c[1] * k, c[2] * k, 1.0)


def build_ped(look):
    """Возвращает dict MeshBuilder'ов: body, arm_l, arm_r, leg_l, leg_r."""
    skin = _c(look.skin)
    shirt = _c(look.shirt)
    pants = _c(look.pants)
    shoes = _c(look.shoes)
    hair = _c(look.hair)
    t = look.torso
    f = look.fat
    K = None
    body = MeshBuilder()
    tw, td = 0.22 * f, 0.12 * f
    # таз и торс
    body.box(K, -tw * 0.92, -td, 0.80, tw * 0.92, td, 0.92, pants)
    body.box(K, -tw, -td, 0.92, tw, td, 1.46, shirt)
    body.box(K, -0.06, -0.06, 1.44, 0.06, 0.06, 1.52, skin)
    fy = td + 0.004

    def fq(x0, z0, x1, z1, col, y=fy):
        body.quad(K, (x1, y, z0), (x0, y, z0), (x0, y, z1), (x1, y, z1), color=col)
    dark = _c(look.shirt, 0.6)
    if t == 'jacket':
        body.tri(K, (0.09, fy, 1.46), (-0.09, fy, 1.46), (0.0, fy, 1.08), color=(0.94, 0.94, 0.94, 1))
        fq(-0.022, 1.12, 0.022, 1.42, (0.62, 0.1, 0.12, 1), fy + 0.003)
        fq(-0.012, 0.93, 0.012, 1.08, dark)
    elif t == 'leather':
        fq(-0.012, 0.93, 0.012, 1.44, (0.6, 0.6, 0.62, 1))
        # спина: кокетка и шов, чтобы персонаж читался со спины (камера почти всегда сзади)
        by = -td - 0.004
        body.quad(K, (-tw, by, 1.30), (tw, by, 1.30), (tw, by, 1.46), (-tw, by, 1.46), color=_c(look.shirt, 1.25))
        body.quad(K, (-0.012, by, 0.93), (0.012, by, 0.93), (0.012, by, 1.30), (-0.012, by, 1.30),
                  color=_c(look.shirt, 0.7))
        body.quad(K, (-tw, by, 0.92), (tw, by, 0.92), (tw, by, 0.98), (-tw, by, 0.98), color=_c(look.shirt, 0.7))
        body.tri(K, (0.1, fy, 1.46), (-0.1, fy, 1.46), (0.0, fy, 1.30), color=(0.92, 0.92, 0.9, 1))
        fq(-tw, 0.92, tw, 0.97, (0.3, 0.3, 0.32, 1))
        for sx in (-1, 1):
            fq(tw * 0.35 * sx - 0.05, 1.10, tw * 0.35 * sx + 0.05, 1.115, (0.5, 0.5, 0.52, 1))
    elif t == 'stripes':
        for z in (0.98, 1.10, 1.22, 1.34):
            fq(-tw, z, tw, z + 0.055, dark)
            body.quad(K, (-tw, -fy, z), (tw, -fy, z), (tw, -fy, z + 0.055), (-tw, -fy, z + 0.055), color=dark)
    elif t == 'vest':
        for z in (1.02, 1.22):
            fq(-tw, z, tw, z + 0.05, (0.86, 0.86, 0.86, 1))
            body.quad(K, (-tw, -fy, z), (tw, -fy, z), (tw, -fy, z + 0.05), (-tw, -fy, z + 0.05),
                      color=(0.86, 0.86, 0.86, 1))
        fq(-0.012, 0.93, 0.012, 1.44, (0.3, 0.3, 0.3, 1))
    elif t == 'police':
        fq(-0.012, 0.98, 0.012, 1.44, (0.75, 0.75, 0.78, 1))
        fq(-tw * 0.75, 1.28, -tw * 0.42, 1.36, (0.95, 0.80, 0.25, 1))
        fq(tw * 0.3, 1.24, tw * 0.8, 1.34, dark)
        body.box(K, -tw - 0.005, -td - 0.005, 0.90, tw + 0.005, td + 0.005, 0.97, (0.06, 0.06, 0.06, 1))
        fq(-0.04, 0.90, 0.04, 0.97, (0.85, 0.75, 0.3, 1), fy + 0.008)
    elif t == 'tank':
        for sx in (-1, 1):
            pass
        body.box(K, -tw - 0.002, -td - 0.002, 1.36, -tw * 0.55, td + 0.002, 1.465, skin)
        body.box(K, tw * 0.55, -td - 0.002, 1.36, tw + 0.002, td + 0.002, 1.465, skin)
        body.tri(K, (0.1, fy, 1.46), (-0.1, fy, 1.46), (0.0, fy, 1.32), color=skin)
    elif t == 'hoodie':
        fq(-tw * 0.6, 0.98, tw * 0.6, 1.14, dark)
        fq(-0.045, 1.24, -0.03, 1.44, (0.9, 0.9, 0.9, 1))
        fq(0.03, 1.24, 0.045, 1.44, (0.9, 0.9, 0.9, 1))
        body.box(K, -0.15, -td - 0.07, 1.36, 0.15, -td + 0.02, 1.56, dark)
    elif t == 'armor':
        body.box(K, -tw - 0.02, -td - 0.03, 1.0, tw + 0.02, td + 0.03, 1.44, (0.18, 0.19, 0.2, 1))
        fq(-tw * 0.7, 1.28, tw * 0.7, 1.36, (0.9, 0.9, 0.9, 1), td + 0.034)
        body.quad(K, (-tw * 0.7, -td - 0.034, 1.24), (tw * 0.7, -td - 0.034, 1.24), (tw * 0.7, -td - 0.034, 1.36),
                  (-tw * 0.7, -td - 0.034, 1.36), color=(0.9, 0.9, 0.9, 1))
    else:
        body.tri(K, (0.07, fy, 1.46), (-0.07, fy, 1.46), (0.0, fy, 1.39), color=skin)
    if look.female and t in ('tee', 'tank', 'stripes'):
        body.box(K, -tw * 1.02, -td * 1.02, 0.72, tw * 1.02, td * 1.02, 0.92, shirt if t != 'tee' else pants)
    # голова
    hx, hy0, hy1, hz0, hz1 = 0.115, -0.12, 0.115, 1.50, 1.77
    body.box(K, -hx, hy0, hz0, hx, hy1, hz1, skin, shade=False)
    y = hy1 + 0.003

    def hq(x0, z0, x1, z1, col, yy=y):
        body.quad(K, (x1, yy, z0), (x0, yy, z0), (x0, yy, z1), (x1, yy, z1), color=col)
    eye = (0.08, 0.08, 0.10, 1)
    hq(-0.075, 1.650, -0.028, 1.682, (0.95, 0.95, 0.95, 1))
    hq(0.028, 1.650, 0.075, 1.682, (0.95, 0.95, 0.95, 1))
    hq(-0.058, 1.650, -0.034, 1.682, eye, y + 0.002)
    hq(0.034, 1.650, 0.058, 1.682, eye, y + 0.002)
    hq(-0.08, 1.692, -0.025, 1.704, hair)
    hq(0.025, 1.692, 0.08, 1.704, hair)
    hq(-0.012, 1.60, 0.012, 1.65, _c(look.skin, 0.86))
    mouth = (0.72, 0.2, 0.22, 1) if look.female else (0.5, 0.26, 0.24, 1)
    hq(-0.04, 1.555, 0.04, 1.572, mouth)
    if look.beard:
        body.box(K, -hx - 0.004, hy1 - 0.1, hz0 - 0.03, hx + 0.004, hy1 + 0.006, 1.59, hair, shade=False)
        hq(-0.035, 1.556, 0.035, 1.570, mouth, hy1 + 0.009)
    if look.glasses:
        hq(-0.095, 1.640, -0.015, 1.692, (0.05, 0.05, 0.06, 1), y + 0.004)
        hq(0.015, 1.640, 0.095, 1.692, (0.05, 0.05, 0.06, 1), y + 0.004)
        hq(-0.015, 1.662, 0.015, 1.676, (0.05, 0.05, 0.06, 1), y + 0.004)
        for sx in (-1, 1):
            body.quad2(K, (hx * sx * 1.03, hy1, 1.662), (hx * sx * 1.03, -0.02, 1.662),
                       (hx * sx * 1.03, -0.02, 1.676), (hx * sx * 1.03, hy1, 1.676), color=(0.05, 0.05, 0.06, 1))
    # волосы / головной убор
    hat = look.hat
    hc = _c(look.hat_color)
    if hat == 'cap':
        body.box(K, -hx - 0.008, hy0 - 0.008, 1.71, hx + 0.008, hy1 + 0.008, 1.80, hc, shade=False)
        body.box(K, -hx * 0.9, hy1, 1.71, hx * 0.9, hy1 + 0.11, 1.725, _c(look.hat_color, 0.7))
        body.box(K, -hx - 0.004, hy0 - 0.004, 1.58, hx + 0.004, hy0 + 0.05, 1.71, hair, shade=False)
    elif hat == 'helmet':
        body.box(K, -hx - 0.02, hy0 - 0.02, 1.68, hx + 0.02, hy1 + 0.02, 1.83, hc, shade=False)
        body.box(K, -hx - 0.02, hy0 - 0.02, 1.60, hx + 0.02, hy0 + 0.1, 1.68, hc, shade=False)
    elif hat == 'police':
        body.box(K, -hx - 0.012, hy0 - 0.012, 1.72, hx + 0.012, hy1 + 0.012, 1.80, hc, shade=False)
        body.box(K, -hx - 0.03, hy0 - 0.03, 1.80, hx + 0.03, hy1 + 0.03, 1.83, hc, shade=False)
        body.box(K, -hx * 0.9, hy1, 1.72, hx * 0.9, hy1 + 0.09, 1.735, (0.05, 0.05, 0.05, 1))
        hq(-0.025, 1.745, 0.025, 1.79, (0.95, 0.8, 0.25, 1), hy1 + 0.016)
        body.box(K, -hx - 0.004, hy0 - 0.004, 1.58, hx + 0.004, hy0 + 0.05, 1.72, hair, shade=False)
    elif not look.bald:
        body.box(K, -hx - 0.008, hy0 - 0.008, 1.715, hx + 0.008, hy1 + 0.006, 1.80, hair, shade=False)
        body.box(K, -hx - 0.008, hy0 - 0.008, 1.60, hx + 0.008, hy0 + 0.07, 1.72, hair, shade=False)
        if look.female:
            body.box(K, -hx - 0.012, hy0 - 0.03, 1.36, hx + 0.012, hy0 + 0.05, 1.62, hair, shade=False)
            for sx in (-1, 1):
                body.box(K, hx * sx - 0.012, hy0, 1.50, hx * sx + 0.012, 0.02, 1.72, hair, shade=False)
    else:
        pass
    parts = {'body': body}
    # руки (ось вращения — плечо, рука висит вдоль -Z)
    long_sleeve = t in ('jacket', 'leather', 'hoodie', 'police', 'armor', 'vest')
    for name, sx in (('arm_l', -1), ('arm_r', 1)):
        m = MeshBuilder()
        aw = 0.058
        if t == 'tank':
            m.box(K, -aw, -0.062, -0.58, aw, 0.062, 0.04, skin)
        elif long_sleeve:
            sc = shirt if t not in ('vest', 'armor') else (_c((0.35, 0.36, 0.4)) if t == 'vest' else shirt)
            m.box(K, -aw, -0.062, -0.58, aw, 0.062, 0.04, sc)
        else:
            m.box(K, -aw * 1.08, -0.066, -0.24, aw * 1.08, 0.066, 0.04, shirt)
            m.box(K, -aw, -0.06, -0.58, aw, 0.06, -0.24, skin)
        m.box(K, -aw * 0.9, -0.055, -0.68, aw * 0.9, 0.055, -0.58, skin)
        parts[name] = m
    for name in ('leg_l', 'leg_r'):
        m = MeshBuilder()
        short = look.female and t in ('tee', 'tank', 'stripes')
        if short:
            m.box(K, -0.082, -0.088, -0.2, 0.082, 0.088, 0.02, pants if t == 'tee' else shirt)
            m.box(K, -0.07, -0.075, -0.78, 0.07, 0.075, -0.2, skin)
        else:
            m.box(K, -0.082, -0.088, -0.78, 0.082, 0.088, 0.02, pants)
        m.box(K, -0.085, -0.09, -0.88, 0.085, 0.16, -0.78, shoes)
        parts[name] = m
    return parts


def gun_template(assets, wid):
    np_ = _gun_cache.get(wid)
    if np_ is None:
        mb = MeshBuilder()
        w = WEAPONS[wid]
        metal = (0.10, 0.10, 0.12, 1)
        wood = (0.42, 0.26, 0.14, 1)
        if wid == W_BAT:
            mb.box(None, -0.025, 0.0, -1.35, 0.025, 0.05, -0.56, wood)
            mb.box(None, -0.04, -0.015, -1.4, 0.04, 0.065, -1.0, wood)
        elif wid == W_FIST:
            pass
        elif w.kind == 'thrown':
            mb.box(None, -0.04, 0.0, -0.76, 0.04, 0.08, -0.62, (0.2, 0.36, 0.2, 1) if wid == 7 else
                   (0.5, 0.3, 0.1, 1))
        elif wid == 6:
            mb.box(None, -0.05, 0.0, -1.5, 0.05, 0.1, -0.3, (0.24, 0.3, 0.2, 1))
            mb.box(None, -0.07, -0.02, -1.62, 0.07, 0.12, -1.5, (0.4, 0.2, 0.16, 1))
        elif w.long:
            mb.box(None, -0.025, 0.0, -1.3, 0.025, 0.07, -0.5, metal)
            mb.box(None, -0.03, -0.01, -0.62, 0.03, 0.09, -0.36, wood)
            mb.box(None, -0.02, -0.16, -0.86, 0.02, 0.0, -0.76, metal)
        else:
            mb.box(None, -0.022, 0.0, -0.92, 0.022, 0.07, -0.62, metal)
            mb.box(None, -0.02, -0.1, -0.7, 0.02, 0.0, -0.62, metal)
        np_ = mb.build('gun', assets.apply_state)
        _gun_cache[wid] = np_
    return np_


def shadow_template(assets):
    if _shadow[0] is None:
        mb = MeshBuilder()
        mb.quad(('shadow', 'decal_c'), (-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0))
        np_ = mb.build('pshadow', assets.apply_state)
        np_.setLightOff(1)
        _shadow[0] = np_
    return _shadow[0]


# ---------------------------------------------------------------------------
class Ped(object):

    def __init__(self, world, x, y, yaw, look, kind='civ'):
        self.world = world
        self.kind = kind
        self.look = look
        self.x, self.y, self.yaw = x, y, yaw
        self.z = world.city.ground_z(x, y)
        self.vx = self.vy = self.vz = 0.0
        self.air = False
        self.health = 100.0
        self.max_health = 100.0
        self.armor = 0.0
        self.state = 'idle'
        self.timer = 1.0
        self.state_t = 0.0
        self.speed = 0.0
        self.walk_speed = 1.35 + random.random() * 0.45
        self.run_speed = 4.9 + random.random() * 1.0
        self.radius = 0.33
        self.weapon = WEAPONS[W_FIST]
        self.fire_cd = 0.0
        self.burst = 0
        self.target = None
        self.accuracy = 0.45
        self.sight = 45.0
        self.pn = None
        self.pn_prev = None
        self.tx = x
        self.ty = y
        self.lat = random.uniform(-0.45, 0.45)
        self.edge_kind = 'walk'
        self.edge_info = None
        self.crossing = False
        self.threat = (x, y)
        self.vehicle = None
        self.is_player = False
        self.dead = False
        self.removed = False
        self.gang = None
        self.hostile = False
        self.brave = random.random()
        self.money = random.randint(4, 40)
        self.on_death = None
        self.keep = False
        self.mission = None
        self.blip = None
        self.anim_phase = random.random() * 6.28
        self.punch_t = 0.0
        self.aiming = False
        self.aim_pitch = 0.0
        self.stuck_t = 0.0
        self.strafe = random.choice((-1.0, 1.0))
        self.repath_t = 0.0
        self.lie = 0.0             # 0 стоит, 1 лежит
        self.lie_dir = -1.0
        self.flee_dir = 0.0
        self.despawn_t = 0.0
        self.guard_pos = None
        self.guard_radius = 0.0
        self.follow = None
        self.talk_t = 0.0
        self.bust_t = 0.0
        self.last_attacker = None
        self.fire_t = 0.0           # горит
        self.lod_far = False
        self.spawned = False        # создан менеджером толпы
        self.unseen_t = 0.0
        self.strafe_t = 0.0
        self._los = True
        self.voice_cd = 0.0
        self.owner = None
        self._limbs = [0.0, 0.0, 0.0, 0.0]
        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        w = self.world
        parts = build_ped(self.look)
        self.node = w.dyn_root.attachNewNode('ped')
        self.model = self.node.attachNewNode('m')
        s = self.look.scale
        self.model.setScale(s)
        ap = w.assets.apply_state
        self.body = parts['body'].build('body', ap)
        self.body.reparentTo(self.model)
        f = self.look.fat
        self.arm_l = self.model.attachNewNode('al')
        self.arm_l.setPos(-0.22 * f - 0.062, 0, 1.42)
        parts['arm_l'].build('g', ap).reparentTo(self.arm_l)
        self.arm_r = self.model.attachNewNode('ar')
        self.arm_r.setPos(0.22 * f + 0.062, 0, 1.42)
        parts['arm_r'].build('g', ap).reparentTo(self.arm_r)
        self.leg_l = self.model.attachNewNode('ll')
        self.leg_l.setPos(-0.105, 0, 0.88)
        parts['leg_l'].build('g', ap).reparentTo(self.leg_l)
        self.leg_r = self.model.attachNewNode('lr')
        self.leg_r.setPos(0.105, 0, 0.88)
        parts['leg_r'].build('g', ap).reparentTo(self.leg_r)
        self.shadow = shadow_template(w.assets).copyTo(self.node)
        self.shadow.setScale(0.95)
        self.shadow.setZ(0.03)
        self.gun_np = None
        self.sync()

    def set_weapon(self, wid):
        self.weapon = WEAPONS[wid]
        if self.gun_np is not None:
            self.gun_np.removeNode()
            self.gun_np = None
        if wid != W_FIST:
            self.gun_np = gun_template(self.world.assets, wid).copyTo(self.arm_r)

    def sync(self):
        self.node.setPosHpr(self.x, self.y, self.z, yaw_to_h(self.yaw), 0, 0)

    def remove(self):
        if self.removed:
            return
        self.removed = True
        self.node.removeNode()

    def set_state(self, st, timer=0.0):
        self.state = st
        self.state_t = 0.0
        self.timer = timer

    # ------------------------------------------------------------------
    # граф тротуаров
    # ------------------------------------------------------------------
    def start_walk(self, node=None, prev=None):
        rn = self.world.roadnet
        if node is None:
            node = rn.nearest_ped_node(self.x, self.y)
        if node is None:
            self.set_state('idle', 3.0)
            return
        self.pn = node
        self.pn_prev = prev
        self.tx, self.ty = node.x, node.y
        self.edge_kind = 'walk'
        self.crossing = False
        self.set_state('walk')

    def _next_node(self):
        cur = self.pn
        edges = cur.edges
        if not edges:
            self.set_state('idle', 5.0)
            return
        opts = [e for e in edges if e[0] is not self.pn_prev]
        if not opts:
            opts = edges
        nxt, kind, info = opts[int(random.random() * len(opts))]
        self.pn_prev = cur
        self.pn = nxt
        self.edge_kind = kind
        self.edge_info = info
        dx, dy = nxt.x - cur.x, nxt.y - cur.y
        L = math.hypot(dx, dy) or 1.0
        off = self.lat
        self.tx = nxt.x - dy / L * off
        self.ty = nxt.y + dx / L * off
        if kind == 'cross':
            self.crossing = False
            self.set_state('wait', 18.0 + random.random() * 6.0)

    def _may_cross(self):
        info = self.edge_info
        if info is None:
            return True
        node, axis = info
        n = self.world.city.nodes.get(node)
        if n is None or len(n.exits) < 3:
            return True
        return self.world.roadnet.light(node, axis) == 'r'

    # ------------------------------------------------------------------
    def _move(self, tx, ty, speed, dt, collide):
        """Шаг к точке.  Возвращает расстояние до цели."""
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        if d < 1e-4:
            self.speed = 0.0
            return 0.0
        want = math.atan2(dy, dx)
        self.yaw = turn_towards(self.yaw, want, 7.0 * dt)
        step = speed * dt
        if step > d:
            step = d
        # идём вперёд по текущему курсу (плавные повороты), но не мимо цели
        ad = abs(angle_diff(want, self.yaw))
        k = 1.0 if ad < 0.6 else (0.35 if ad < 1.6 else 0.0)
        self.x += math.cos(self.yaw) * step * k
        self.y += math.sin(self.yaw) * step * k
        self.speed = speed * k
        if not self.air:
            self.z = self.world.city.ground_z(self.x, self.y)
        if collide:
            nx, ny, px, py, depth, ref = self.world.static.push_circle(self.x, self.y, self.radius, F_PED)
            if depth > 0.0:
                self.x, self.y = nx, ny
                if depth > 0.01:
                    self.stuck_t += dt
            else:
                self.stuck_t = max(0.0, self.stuck_t - dt * 0.5)
        return d

    def face(self, tx, ty, dt, rate=9.0):
        self.yaw = turn_towards(self.yaw, math.atan2(ty - self.y, tx - self.x), rate * dt)

    # ------------------------------------------------------------------
    def update(self, dt):
        if self.removed:
            return
        self.state_t += dt
        if self.fire_cd > 0.0:
            self.fire_cd -= dt
        st = self.state
        if st == 'walk':
            sp = self.walk_speed * (1.25 if self.crossing else 1.0)
            d = self._move(self.tx, self.ty, sp, dt, False)
            if d < 0.45:
                self.crossing = False
                self._next_node()
        elif st == 'wait':
            self.speed = 0.0
            self.timer -= dt
            if self._may_cross() or self.timer <= 0.0:
                self.crossing = True
                self.set_state('walk')
        elif st == 'idle':
            self.speed = 0.0
            self.timer -= dt
            if self.timer <= 0.0:
                self.start_walk()
        elif st == 'flee':
            self._flee(dt)
        elif st == 'return':
            d = self._move(self.tx, self.ty, self.walk_speed * 1.4, dt, True)
            self.timer -= dt
            if d < 0.6 or self.timer <= 0.0 or self.stuck_t > 2.0:
                self.stuck_t = 0.0
                self.start_walk(self.pn)
                self._next_node()
        elif st == 'attack':
            self._attack(dt)
        elif st == 'guard':
            self._guard(dt)
        elif st == 'follow':
            self._follow(dt)
        elif st == 'goto':
            d = self._move(self.tx, self.ty, self.run_speed if self.timer > 0 else self.walk_speed, dt, True)
            if d < 0.7:
                self.set_state('stand')
        elif st == 'stand':
            self.speed = 0.0
        elif st == 'cower':
            self.speed = 0.0
            self.timer -= dt
            if self.timer <= 0.0:
                self.flee_from(self.threat[0], self.threat[1], 5.0)
        elif st == 'down':
            self.speed = 0.0
            self.timer -= dt
            if self.timer <= 0.0 and not self.air:
                self._get_up()
        elif st == 'dead':
            self.speed = 0.0
            self.despawn_t += dt
        elif st == 'in_car':
            return
        if self.air:
            self._fly(dt)
        if self.fire_t > 0.0:
            self._burn(dt)
        self._animate(dt)

    # ------------------------------------------------------------------
    def flee_from(self, x, y, duration=8.0):
        if self.dead or self.state in ('down', 'in_car'):
            return
        self.threat = (x, y)
        self.flee_dir = math.atan2(self.y - y, self.x - x) + random.uniform(-0.5, 0.5)
        self.set_state('flee', duration * (0.7 + random.random() * 0.6))

    def _flee(self, dt):
        self.timer -= dt
        if self.timer <= 0.0:
            n = self.world.roadnet.nearest_ped_node(self.x, self.y)
            if n is None:
                self.set_state('idle', 2.0)
                return
            self.pn = n
            self.pn_prev = None
            self.tx, self.ty = n.x, n.y
            self.set_state('return', 14.0)
            return
        tx = self.x + math.cos(self.flee_dir) * 6.0
        ty = self.y + math.sin(self.flee_dir) * 6.0
        self._move(tx, ty, self.run_speed, dt, True)
        if self.stuck_t > 0.25:
            # упёрлись: бежим вдоль препятствия
            self.flee_dir += self.strafe * (math.pi * 0.5 + random.uniform(-0.3, 0.3))
            self.stuck_t = 0.0
            if random.random() < 0.3:
                self.strafe = -self.strafe
        elif random.random() < dt * 0.5:
            # время от времени корректируем курс «от угрозы»
            want = math.atan2(self.y - self.threat[1], self.x - self.threat[0])
            self.flee_dir = turn_towards(self.flee_dir, want, 0.8)

    # ------------------------------------------------------------------
    def attack(self, target):
        if self.dead or self.state == 'in_car':
            return
        self.target = target
        if self.state != 'down':
            self.set_state('attack')

    def _target_pos(self):
        t = self.target
        if t is None:
            return None
        if getattr(t, 'vehicle', None) is not None:
            v = t.vehicle
            return v.x, v.y
        return t.x, t.y

    def _attack(self, dt):
        t = self.target
        w = self.world
        if t is None or t.dead or t.removed:
            self.target = None
            self.aiming = False
            if self.guard_pos is not None:
                self.set_state('guard')
            elif self.kind in ('cop', 'swat', 'fbi', 'army'):
                self.set_state('idle', 2.0)
            else:
                self.set_state('idle', 1.5)
            return
        tx, ty = self._target_pos()
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        wp = self.weapon
        if wp.kind == 'melee':
            self.aiming = False
            in_car = getattr(t, 'vehicle', None) is not None
            reach = wp.range + (1.2 if in_car else 0.0)
            if d > reach * 0.85:
                self._chase(tx, ty, d, dt)
            else:
                self.speed = 0.0
                self.face(tx, ty, dt)
                if self.fire_cd <= 0.0:
                    self.fire_cd = wp.rate * (1.6 + random.random())
                    self.punch_t = 0.3
                    w.weapons.melee_hit(self, t, wp)
        else:
            self.repath_t -= dt
            if self.repath_t <= 0.0:
                self.repath_t = 0.4 + random.random() * 0.3
                self._los = w.static.los(self.x, self.y, tx, ty)
            los = self._los
            pref = min(wp.range * 0.5, 22.0)
            if d > pref or not los:
                self.aiming = d < wp.range and los
                self._chase(tx, ty, d, dt)
                if self.aiming and self.fire_cd <= 0.0 and random.random() < 0.5:
                    self._shoot(t, tx, ty, d)
            else:
                self.speed = 0.0
                self.aiming = True
                self.face(tx, ty, dt, 6.0)
                if d < 5.0 and wp.kind == 'gun':
                    # слишком близко: отходим боком
                    sx = self.x - dy / d * self.strafe * 2.0 - dx / d * 1.0
                    sy = self.y + dx / d * self.strafe * 2.0 - dy / d * 1.0
                    self._move(sx, sy, self.walk_speed * 1.3, dt, True)
                    self.face(tx, ty, dt, 30.0)
                if self.fire_cd <= 0.0:
                    self._shoot(t, tx, ty, d)

    def _shoot(self, t, tx, ty, d):
        wp = self.weapon
        if abs(angle_diff(math.atan2(ty - self.y, tx - self.x), self.yaw)) > 0.5:
            return
        if wp.auto:
            if self.burst <= 0:
                self.burst = random.randint(3, 6)
            self.burst -= 1
            self.fire_cd = wp.rate if self.burst > 0 else 0.7 + random.random() * 1.0
        else:
            self.fire_cd = wp.rate * (1.6 + random.random() * 1.6)
        self.world.weapons.npc_fire(self, t, wp, tx, ty, d)

    def _chase(self, tx, ty, d, dt):
        """Бежать к цели, огибая препятствия."""
        if self.stuck_t > 0.3:
            # обходим: шаг вбок
            self.stuck_t = 0.0
            self.strafe_t = 0.9
            if random.random() < 0.35:
                self.strafe = -self.strafe
        st = self.strafe_t
        if st > 0.0:
            self.strafe_t = st - dt
            dx, dy = tx - self.x, ty - self.y
            L = d or 1.0
            sx = self.x - dy / L * self.strafe * 4.0 + dx / L * 1.0
            sy = self.y + dx / L * self.strafe * 4.0 + dy / L * 1.0
            self._move(sx, sy, self.run_speed, dt, True)
        else:
            self._move(tx, ty, self.run_speed, dt, True)

    def _guard(self, dt):
        """Стоять на посту; напасть, если игрок близко (для миссий и банд)."""
        w = self.world
        self.speed = 0.0
        p = w.player.ped
        gp = self.guard_pos
        if gp is not None:
            d = math.hypot(gp[0] - self.x, gp[1] - self.y)
            if d > 1.0:
                self._move(gp[0], gp[1], self.walk_speed, dt, True)
        if self.hostile and not p.dead:
            px, py = w.player.pos()
            d2 = (px - self.x) ** 2 + (py - self.y) ** 2
            r = self.guard_radius or 22.0
            if d2 < r * r:
                self.timer -= dt
                if self.timer <= 0.0:
                    self.timer = 0.5
                    if d2 < 36.0 or w.static.los(self.x, self.y, px, py):
                        self.attack(p)

    def _follow(self, dt):
        f = self.follow
        if f is None or f.dead:
            self.set_state('idle', 1.0)
            return
        fx, fy = (f.vehicle.x, f.vehicle.y) if f.vehicle is not None else (f.x, f.y)
        d = math.hypot(fx - self.x, fy - self.y)
        if d > 2.6:
            self._chase(fx, fy, d, dt) if d > 6.0 else self._move(fx, fy, self.walk_speed * 1.5, dt, True)
        else:
            self.speed = 0.0

    # ------------------------------------------------------------------
    def hurt(self, amount, attacker=None, cause='bullet', push=None):
        """Нанести урон.  Возвращает True, если персонаж погиб."""
        if self.dead or self.removed:
            return False
        w = self.world
        if self.is_player:
            if w.player.invincible or w.player.state == 'busted':
                return False
            amount *= w.player.damage_taken_k
        if self.armor > 0.0 and cause in ('bullet', 'melee', 'explosion'):
            a = min(self.armor, amount * 0.8)
            self.armor -= a
            amount -= a
        self.health -= amount
        self.last_attacker = attacker
        if push is not None and self.vehicle is None:
            self.vx += push[0]
            self.vy += push[1]
        if self.health <= 0.0:
            self.die(attacker, cause)
            return True
        if self.is_player:
            w.on_player_hurt(amount, attacker, cause)
            return False
        w.on_ped_hurt(self, attacker, cause)
        if self.vehicle is not None:
            return False
        if cause in ('vehicle', 'explosion') and amount > 12.0:
            self.knock_down(2.0 + random.random() * 2.0)
        elif attacker is not None and attacker is not self:
            self.react_to_attack(attacker)
        return False

    def react_to_attack(self, attacker):
        if self.dead or self.state in ('down', 'in_car'):
            return
        if self.kind in ('cop', 'swat', 'fbi', 'army', 'gang', 'guard', 'enemy') or self.hostile:
            if self.target is None or self.target is not attacker:
                self.attack(attacker)
        elif self.kind == 'mission':
            pass
        else:
            if self.brave > 0.9 and attacker.weapon.kind == 'melee':
                self.attack(attacker)
            else:
                self.flee_from(attacker.x, attacker.y, 10.0)

    def knock_down(self, t=2.5, vx=0.0, vy=0.0, vz=0.0):
        if self.dead:
            return
        self.aiming = False
        self.lie_dir = random.choice((-1.0, 1.0))
        self.set_state('down', t)
        if vz > 0.0 or abs(vx) + abs(vy) > 0.5:
            self.vx, self.vy, self.vz = vx, vy, vz
            self.air = True

    def _get_up(self):
        if self.dead:
            return
        if self.is_player:
            self.set_state('player')
            return
        self.set_state('idle', 1.0)
        la = self.last_attacker
        if self.target is not None and not self.target.dead:
            self.set_state('attack')
        elif self.kind in ('cop', 'swat', 'fbi', 'army', 'gang', 'enemy') and la is not None and not la.dead:
            self.attack(la)
        elif self.guard_pos is not None:
            self.set_state('guard')
        else:
            tx, ty = self.threat if la is None else (la.x, la.y)
            self.flee_from(tx, ty, 9.0)

    def die(self, killer=None, cause='bullet'):
        if self.dead:
            return
        if self.is_player and self.world.player.state == 'busted':
            return                          # арестованного уже не убить
        self.dead = True
        self.health = 0.0
        self.aiming = False
        self.lie_dir = random.choice((-1.0, 1.0))
        if self.vehicle is not None:
            self.world.eject(self, dead=True)
        self.set_state('dead')
        self.world.on_ped_died(self, killer, cause)
        cb = self.on_death
        if cb is not None:
            self.on_death = None
            try:
                cb(self, killer)
            except Exception:
                import traceback
                traceback.print_exc()

    def _fly(self, dt):
        """Полёт после удара машиной или взрыва."""
        self.vz -= 14.0 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.z += self.vz * dt
        w = self.world
        nx, ny, px, py, depth, ref = w.static.push_circle(self.x, self.y, self.radius, F_PED)
        if depth > 0.0:
            self.x, self.y = nx, ny
            vn = self.vx * px + self.vy * py
            if vn < 0:
                self.vx -= 1.3 * vn * px
                self.vy -= 1.3 * vn * py
        gz = w.city.ground_z(self.x, self.y)
        if self.z <= gz:
            self.z = gz
            if self.vz < -3.0 and abs(self.vz) > 1.0:
                self.vz = -self.vz * 0.25
                self.vx *= 0.6
                self.vy *= 0.6
            else:
                self.vz = 0.0
                self.vx *= math.exp(-6.0 * dt)
                self.vy *= math.exp(-6.0 * dt)
                if abs(self.vx) + abs(self.vy) < 0.4:
                    self.air = False
                    self.vx = self.vy = 0.0
            if gz < WATER_Z - 0.25 and w.city.in_water(self.x, self.y):
                self.air = False
                if not self.dead:
                    self.die(None, 'drown')

    def _burn(self, dt):
        self.fire_t -= dt
        w = self.world
        if random.random() < dt * 14.0:
            w.fx.fire(self.x + random.uniform(-0.2, 0.2), self.y + random.uniform(-0.2, 0.2),
                      self.z + random.uniform(0.3, 1.5), 0.5)
        if not self.dead:
            self.hurt(22.0 * dt, self.last_attacker, 'fire')
            if not self.dead and not self.is_player and self.state not in ('flee', 'down'):
                self.flee_from(self.x + random.uniform(-1, 1), self.y + random.uniform(-1, 1), 6.0)

    # ------------------------------------------------------------------
    def _animate(self, dt):
        st = self.state
        lying = st in ('down', 'dead')
        tgt = 1.0 if lying else 0.0
        if self.lie != tgt:
            self.lie = approach(self.lie, tgt, dt * (4.5 if lying else 2.5))
            self.model.setP(self.lie * 88.0 * self.lie_dir)
            self.model.setZ(self.lie * 0.16)
        self.node.setPosHpr(self.x, self.y, self.z, yaw_to_h(self.yaw), 0, 0)
        if self.lod_far:
            return
        sp = self.speed
        L = self._limbs
        if lying:
            a = 0.0
            arm_l = arm_r = -20.0 * self.lie * self.lie_dir
            leg = 12.0 * self.lie
            leg_l, leg_r = leg, -leg
        elif sp > 0.1:
            run = sp > 3.0
            self.anim_phase += sp * dt * (2.3 if run else 3.4)
            s = math.sin(self.anim_phase)
            amp = 48.0 if run else 30.0
            leg_l, leg_r = s * amp, -s * amp
            arm_l, arm_r = -s * amp * 0.8, s * amp * 0.8
        else:
            leg_l = leg_r = 0.0
            arm_l = arm_r = 0.0
        if not lying:
            if self.punch_t > 0.0:
                self.punch_t -= dt
                k = 1.0 - abs(self.punch_t / 0.3 - 0.5) * 2.0
                arm_r = 20.0 + 95.0 * k
            elif self.aiming:
                arm_r = 90.0 + self.aim_pitch
                if self.weapon.long:
                    arm_l = 70.0 + self.aim_pitch
        if abs(L[0] - arm_l) > 0.8:
            L[0] = arm_l
            self.arm_l.setP(arm_l)
        if abs(L[1] - arm_r) > 0.8:
            L[1] = arm_r
            self.arm_r.setP(arm_r)
        if abs(L[2] - leg_l) > 0.8:
            L[2] = leg_l
            self.leg_l.setP(leg_l)
        if abs(L[3] - leg_r) > 0.8:
            L[3] = leg_r
            self.leg_r.setP(leg_r)
