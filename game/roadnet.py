# -*- coding: utf-8 -*-
"""Дорожная сеть: полосы для транспорта, светофоры, граф тротуаров."""
import math

from .city import AVE_W, ST_W, SIDEWALK, ROAD_X_AVE, ROAD_Y_AVE, PARK_I0, PARK_I1, PARK_J0, PARK_J1
from .mathutil import bezier2, bezier2_tangent, Rng

LANE_AVE = (1.75, 5.25)       # смещения полос от осевой (проспект)
LANE_ST = (1.9,)              # улица: одна полоса в каждую сторону
PARK_OFF = 4.75               # парковочный карман на улицах
STOP_BACK = 4.3               # стоп-линия: метров до края перекрёстка
PED_INSET = 1.6               # узлы тротуара: расстояние от бордюра

CYCLE = 26.0
DIRS = {'e': (1.0, 0.0), 'w': (-1.0, 0.0), 'n': (0.0, 1.0), 's': (0.0, -1.0)}
OPP = {'e': 'w', 'w': 'e', 'n': 's', 's': 'n'}
RIGHT_OF = {'e': 's', 's': 'w', 'w': 'n', 'n': 'e'}
LEFT_OF = {'e': 'n', 'n': 'w', 'w': 's', 's': 'e'}
DIR_YAW = {'e': 0.0, 'n': math.pi / 2, 'w': math.pi, 's': -math.pi / 2}


class Link(object):
    """Отрезок пути для машины: полоса (straight) или манёвр на перекрёстке."""
    __slots__ = ('id', 'turn', 'x0', 'y0', 'x1', 'y1', 'cx', 'cy', 'curved', 'length', 'next', 'node',
                 'dir', 'lane', 'ave', 'speed', 'signal', 'axis', 'zone', 'seg', 'kind')

    def pos(self, s):
        """Точка и направление (yaw) на расстоянии s от начала."""
        t = s / self.length if self.length > 0 else 0.0
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        if not self.curved:
            return (self.x0 + (self.x1 - self.x0) * t, self.y0 + (self.y1 - self.y0) * t,
                    math.atan2(self.y1 - self.y0, self.x1 - self.x0))
        u = 1.0 - t
        x = u * u * self.x0 + 2 * u * t * self.cx + t * t * self.x1
        y = u * u * self.y0 + 2 * u * t * self.cy + t * t * self.y1
        tx = 2 * u * (self.cx - self.x0) + 2 * t * (self.x1 - self.cx)
        ty = 2 * u * (self.cy - self.y0) + 2 * t * (self.y1 - self.cy)
        return x, y, math.atan2(ty, tx)


class PedNode(object):
    __slots__ = ('id', 'x', 'y', 'edges', 'block')        # edges: [(node, kind, info)]


class RoadNet(object):

    def __init__(self, city):
        self.city = city
        self.links = []
        self.lanes = []                # только полосы (не манёвры)
        self.lane_index = {}           # (kind, i, j, dir, lane) -> Link
        self.time = 0.0
        self._build_lanes()
        self._build_turns()
        self._build_ped_graph()
        self._build_kerb_parking()
        self._lane_grid = {}
        for l in self.lanes:
            cx = int(((l.x0 + l.x1) * 0.5) // 100)
            cy = int(((l.y0 + l.y1) * 0.5) // 100)
            self._lane_grid.setdefault((cx, cy), []).append(l)

    # ------------------------------------------------------------------
    def _new_link(self):
        l = Link()
        l.id = len(self.links)
        l.next = []
        l.curved = False
        l.cx = l.cy = 0.0
        l.signal = False
        l.axis = 0
        l.zone = 'D'
        l.seg = None
        l.kind = None
        self.links.append(l)
        return l

    def _build_lanes(self):
        c = self.city
        for key, seg in sorted(c.segs.items()):
            kind, i, j = key
            offs = LANE_AVE if seg['ave'] else LANE_ST
            a, b, cc = seg['a'], seg['b'], seg['c']
            if kind == 'h':
                dirs = (('e', (i + 1, j)), ('w', (i, j)))
            else:
                dirs = (('n', (i, j + 1)), ('s', (i, j)))
            for d, node in dirs:
                for k, off in enumerate(offs):
                    l = self._new_link()
                    l.turn = None
                    l.dir = d
                    l.lane = k
                    l.ave = seg['ave']
                    l.node = node
                    l.seg = key
                    l.kind = kind
                    # правостороннее движение: полоса справа от осевой
                    if d == 'e':
                        l.x0, l.y0, l.x1, l.y1 = a, cc - off, b, cc - off
                    elif d == 'w':
                        l.x0, l.y0, l.x1, l.y1 = b, cc + off, a, cc + off
                    elif d == 'n':
                        l.x0, l.y0, l.x1, l.y1 = cc + off, a, cc + off, b
                    else:
                        l.x0, l.y0, l.x1, l.y1 = cc - off, b, cc - off, a
                    l.length = b - a
                    l.speed = 13.5 if seg['ave'] else 10.0
                    if seg['rural']:
                        l.speed = 17.0 if seg['bridge'] is None else 15.0      # трасса и мосты — быстрее
                    n = c.nodes.get(node)
                    l.signal = (n is not None and len(n.exits) >= 3 and not n.rural)
                    l.axis = 0 if d in ('n', 's') else 1
                    l.zone = c.zone_style(c.zone_at((l.x0 + l.x1) * 0.5, (l.y0 + l.y1) * 0.5))
                    self.lanes.append(l)
                    self.lane_index[(kind, i, j, d, k)] = l

    def _out_lanes(self, node, d):
        """Полосы, выходящие из узла node в направлении d."""
        i, j = node
        if d == 'e':
            key = ('h', i, j)
        elif d == 'w':
            key = ('h', i - 1, j)
        elif d == 'n':
            key = ('v', i, j)
        else:
            key = ('v', i, j - 1)
        out = []
        k = 0
        while True:
            l = self.lane_index.get((key[0], key[1], key[2], d, k))
            if l is None:
                break
            out.append(l)
            k += 1
        return out

    def _make_turn(self, lane, out, kind):
        t = self._new_link()
        t.turn = kind
        t.dir = out.dir
        t.lane = out.lane
        t.ave = lane.ave
        t.node = lane.node
        t.x0, t.y0 = lane.x1, lane.y1
        t.x1, t.y1 = out.x0, out.y0
        t.next = [out]
        t.zone = lane.zone
        if kind == 'S':
            t.curved = False
            t.length = math.hypot(t.x1 - t.x0, t.y1 - t.y0)
            t.speed = lane.speed
        else:
            t.curved = True
            if lane.dir in ('e', 'w'):
                t.cx, t.cy = t.x1, t.y0
            else:
                t.cx, t.cy = t.x0, t.y1
            # длина кривой
            ln = 0.0
            px, py = t.x0, t.y0
            for k in range(1, 9):
                x, y = bezier2((t.x0, t.y0), (t.cx, t.cy), (t.x1, t.y1), k / 8.0)
                ln += math.hypot(x - px, y - py)
                px, py = x, y
            t.length = ln
            t.speed = 5.0 if kind == 'R' else 6.5
        lane.next.append(t)
        return t

    def _build_turns(self):
        c = self.city
        for lane in self.lanes:
            n = c.nodes.get(lane.node)
            if n is None:
                continue
            d = lane.dir
            n_in = len(self._out_lanes_in(lane))
            opts = []
            for dout in n.exits.keys():
                if dout == OPP[d]:
                    continue
                outs = self._out_lanes(lane.node, dout)
                if not outs:
                    continue
                if dout == d:
                    kind = 'S'
                    out = outs[min(lane.lane, len(outs) - 1)]
                    ok = True
                elif dout == RIGHT_OF[d]:
                    kind = 'R'
                    out = outs[-1]
                    ok = (lane.lane == n_in - 1)
                else:
                    kind = 'L'
                    out = outs[0]
                    ok = (lane.lane == 0)
                opts.append((kind, out, ok))
            chosen = [o for o in opts if o[2]]
            if not chosen:
                chosen = opts
            for kind, out, ok in chosen:
                self._make_turn(lane, out, kind)
            if not lane.next:
                # тупик: разворот
                outs = self._out_lanes(lane.node, OPP[d])
                if outs:
                    t = self._make_turn(lane, outs[0], 'L')
                    t.curved = False
                    t.length = math.hypot(t.x1 - t.x0, t.y1 - t.y0)

    def _out_lanes_in(self, lane):
        out = []
        k = 0
        while True:
            l = self.lane_index.get((lane.seg[0], lane.seg[1], lane.seg[2], lane.dir, k))
            if l is None:
                break
            out.append(l)
            k += 1
        return out

    # ------------------------------------------------------------------
    # светофоры
    # ------------------------------------------------------------------
    @staticmethod
    def _state(tt, axis):
        """Состояние для оси (0 = север-юг, 1 = запад-восток) в момент цикла tt."""
        if axis == 0:
            if tt < 10.0:
                return 'g'
            if tt < 12.5:
                return 'y'
            return 'r'
        if tt < 13.0:
            return 'r'
        if tt < 23.0:
            return 'g'
        if tt < 25.5:
            return 'y'
        return 'r'

    def light_group(self, phase_idx, axis):
        return self._state((self.time + phase_idx * 3.1) % CYCLE, axis)

    def light(self, node, axis):
        n = self.city.nodes.get(node)
        if n is None or len(n.exits) < 3 or n.rural:
            return 'g'
        return self._state((self.time + n.phase) % CYCLE, axis)

    def update(self, dt):
        self.time += dt

    # ------------------------------------------------------------------
    def lanes_near(self, x, y, rmin, rmax):
        """Полосы, середина которых на расстоянии [rmin, rmax] (грубо)."""
        out = []
        cx0 = int((x - rmax) // 100)
        cx1 = int((x + rmax) // 100)
        cy0 = int((y - rmax) // 100)
        cy1 = int((y + rmax) // 100)
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                for l in self._lane_grid.get((cx, cy), ()):
                    out.append(l)
        return out

    def nearest_lane(self, x, y, maxd=60.0):
        """(lane, s, dist) — ближайшая полоса и положение на ней."""
        best = None
        bd = maxd
        bs = 0.0
        for l in self.lanes_near(x, y, 0, maxd + 100.0):
            dx = l.x1 - l.x0
            dy = l.y1 - l.y0
            t = ((x - l.x0) * dx + (y - l.y0) * dy) / (l.length * l.length)
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            px = l.x0 + dx * t
            py = l.y0 + dy * t
            d = math.hypot(x - px, y - py)
            if d < bd:
                bd = d
                best = l
                bs = t * l.length
        return best, bs, bd

    def route(self, a, b):
        """Кратчайший путь по узлам перекрёстков от a до b (BFS): список (i, j)."""
        nodes = self.city.nodes
        if a not in nodes or b not in nodes:
            return []
        if a == b:
            return [a]
        prev = {a: None}
        queue = [a]
        qi = 0
        while qi < len(queue):
            cur = queue[qi]
            qi += 1
            if cur == b:
                break
            for nb in nodes[cur].exits.values():
                if nb not in prev and nb in nodes:
                    prev[nb] = cur
                    queue.append(nb)
        if b not in prev:
            return []
        path = []
        cur = b
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return path

    # ------------------------------------------------------------------
    # граф тротуаров
    # ------------------------------------------------------------------
    def _ped_node(self, x, y, block):
        key = (round(x, 1), round(y, 1))
        n = self._pn_index.get(key)
        if n is None:
            n = PedNode()
            n.id = len(self.ped_nodes)
            n.x, n.y = x, y
            n.edges = []
            n.block = block
            self.ped_nodes.append(n)
            self._pn_index[key] = n
        return n

    def _ped_edge(self, a, b, kind='walk', info=None):
        if a is b:
            return
        for (n, k, i) in a.edges:
            if n is b:
                return
        a.edges.append((b, kind, info))
        b.edges.append((a, kind, info))

    def _build_ped_graph(self):
        c = self.city
        self.ped_nodes = []
        self._pn_index = {}
        ins = PED_INSET
        sides = {}          # (block id, side) -> [nodes]

        def on_side(b, side, x, y):
            n = self._ped_node(x, y, b.id)
            lst = sides.setdefault((b.id, side), [])
            if n not in lst:
                lst.append(n)
            return n

        for b in c.blocks:
            x0, y0, x1, y1 = b.x0 + ins, b.y0 + ins, b.x1 - ins, b.y1 - ins
            on_side(b, 's', x0, y0)
            on_side(b, 's', x1, y0)
            on_side(b, 'n', x0, y1)
            on_side(b, 'n', x1, y1)
            on_side(b, 'w', x0, y0)
            on_side(b, 'w', x0, y1)
            on_side(b, 'e', x1, y0)
            on_side(b, 'e', x1, y1)
        # переходы через дороги у перекрёстков
        outer = []
        for key, seg in sorted(c.segs.items()):
            kind, i, j = key
            hw = seg['width'] * 0.5
            a, bb, cc = seg['a'], seg['b'], seg['c']
            for (t, node) in ((a + ins, (i, j)), (bb - ins, (i + 1, j) if kind == 'h' else (i, j + 1))):
                if kind == 'v':
                    # дорога идёт с юга на север; переход с запада на восток
                    wb = c.block_grid.get((i - 1, j))
                    eb = c.block_grid.get((i, j))
                    pw = on_side(wb, 'e', cc - hw - ins, t) if wb is not None else None
                    pe = on_side(eb, 'w', cc + hw + ins, t) if eb is not None else None
                    if pw is not None and pe is not None:
                        self._ped_edge(pw, pe, 'cross', (node, 0))
                else:
                    sb = c.block_grid.get((i, j - 1))
                    nb = c.block_grid.get((i, j))
                    ps = on_side(sb, 'n', t, cc - hw - ins) if sb is not None else None
                    pn = on_side(nb, 's', t, cc + hw + ins) if nb is not None else None
                    if ps is None and j == 0:
                        # южная набережная
                        ps = self._ped_node(t, cc - hw - 1.5, -1)
                        outer.append(ps)
                    if ps is not None and pn is not None:
                        self._ped_edge(ps, pn, 'cross', (node, 1))
        outer.sort(key=lambda n: n.x)
        for k in range(len(outer) - 1):
            self._ped_edge(outer[k], outer[k + 1])
        # парк: дорожки
        pp = c.special.get('park_paths')
        if pp:
            b = c.blocks[pp['block']]
            cx, cy = pp['cx'], pp['cy']
            ms = on_side(b, 's', cx, b.y0 + ins)
            mn = on_side(b, 'n', cx, b.y1 - ins)
            mw = on_side(b, 'w', b.x0 + ins, cy)
            me = on_side(b, 'e', b.x1 - ins, cy)
            R = 9.0
            rs = self._ped_node(cx, cy - R, b.id)
            rn = self._ped_node(cx, cy + R, b.id)
            rw = self._ped_node(cx - R, cy, b.id)
            re = self._ped_node(cx + R, cy, b.id)
            for (m, r) in ((ms, rs), (mn, rn), (mw, rw), (me, re)):
                self._ped_edge(m, r)
            for (p, q) in ((rs, re), (re, rn), (rn, rw), (rw, rs)):
                self._ped_edge(p, q)
        # рёбра вдоль сторон кварталов
        for (bid, side), lst in sides.items():
            if side in ('s', 'n'):
                lst.sort(key=lambda n: n.x)
            else:
                lst.sort(key=lambda n: n.y)
            for k in range(len(lst) - 1):
                self._ped_edge(lst[k], lst[k + 1])
        self._pn_grid = {}
        for n in self.ped_nodes:
            self._pn_grid.setdefault((int(n.x // 100), int(n.y // 100)), []).append(n)

    def ped_nodes_near(self, x, y, r):
        out = []
        for cx in range(int((x - r) // 100), int((x + r) // 100) + 1):
            for cy in range(int((y - r) // 100), int((y + r) // 100) + 1):
                out.extend(self._pn_grid.get((cx, cy), ()))
        return out

    def nearest_ped_node(self, x, y, r=80.0):
        best = None
        bd = 1e18
        for n in self.ped_nodes_near(x, y, r):
            d = (n.x - x) ** 2 + (n.y - y) ** 2
            if d < bd:
                bd = d
                best = n
        return best

    # ------------------------------------------------------------------
    def _build_kerb_parking(self):
        """Места для припаркованных машин вдоль улиц (не проспектов)."""
        c = self.city
        r = Rng(c.seed * 31 + 7)
        for key, seg in sorted(c.segs.items()):
            if seg['ave'] or seg['rural']:
                continue
            kind, i, j = key
            a, b, cc = seg['a'], seg['b'], seg['c']
            t = a + 12.0
            while t < b - 12.0:
                for sgn in (-1, 1):
                    if not r.chance(0.2):
                        continue
                    if kind == 'h':
                        x, y = t, cc + sgn * PARK_OFF
                        yaw = math.pi if sgn > 0 else 0.0
                    else:
                        x, y = cc + sgn * PARK_OFF, t
                        yaw = math.pi / 2 if sgn > 0 else -math.pi / 2
                    zone = c.zone_style(c.zone_at(x, y))
                    if zone == 'P':
                        zone = 'D'
                    c.parking.append(dict(x=x, y=y, yaw=yaw, zone=zone, kind=None, block=-1))
                t += 6.6
