# -*- coding: utf-8 -*-
"""Статический мир для столкновений: 2D-сетка из коробок и кругов с высотой.

Вся физика игры двумерная (вид сверху) + высоты, этого хватает для
плоского города и работает быстро даже на чистом Python.
"""
import math

F_CAR = 1        # не пускает машины
F_PED = 2        # не пускает пешеходов
F_SIGHT = 4      # закрывает обзор ИИ
F_BULLET = 8     # останавливает пули
F_BREAK = 16     # ломается от удара машины
F_CAM = 32       # мешает камере
F_SOLID = F_CAR | F_PED | F_BULLET
F_WALL = F_SOLID | F_SIGHT | F_CAM

CELL = 16.0
INV_CELL = 1.0 / CELL


class StaticWorld(object):

    def __init__(self):
        self.boxes = []          # [x0, y0, x1, y1, z0, z1, flags, ref]
        self.circles = []        # [x, y, r, z1, flags, ref]
        self.grid = {}           # (cx, cy) -> ([box ids], [circle ids])
        self._stamp = 0
        self._bstamp = []
        self._cstamp = []

    # ------------------------------------------------------------------
    def _cell(self, cx, cy):
        c = self.grid.get((cx, cy))
        if c is None:
            c = self.grid[(cx, cy)] = ([], [])
        return c

    def add_box(self, x0, y0, x1, y1, z0, z1, flags=F_WALL, ref=None):
        idx = len(self.boxes)
        self.boxes.append([x0, y0, x1, y1, z0, z1, flags, ref])
        self._bstamp.append(0)
        for cx in range(int(math.floor(x0 * INV_CELL)), int(math.floor(x1 * INV_CELL)) + 1):
            for cy in range(int(math.floor(y0 * INV_CELL)), int(math.floor(y1 * INV_CELL)) + 1):
                self._cell(cx, cy)[0].append(idx)
        return idx

    def add_circle(self, x, y, r, z1, flags=F_SOLID, ref=None):
        idx = len(self.circles)
        self.circles.append([x, y, r, z1, flags, ref])
        self._cstamp.append(0)
        for cx in range(int(math.floor((x - r) * INV_CELL)), int(math.floor((x + r) * INV_CELL)) + 1):
            for cy in range(int(math.floor((y - r) * INV_CELL)), int(math.floor((y + r) * INV_CELL)) + 1):
                self._cell(cx, cy)[1].append(idx)
        return idx

    def remove_circle(self, idx):
        self.circles[idx][4] = 0

    def remove_box(self, idx):
        self.boxes[idx][6] = 0

    # ------------------------------------------------------------------
    def push_circle(self, x, y, r, mask, out=None):
        """Вытолкнуть круг из препятствий.

        Возвращает (x, y, nx, ny, depth, ref): нормаль и глубина самого
        сильного контакта (depth == 0 — контактов не было).
        """
        grid = self.grid
        boxes = self.boxes
        circles = self.circles
        bnx = bny = 0.0
        bdepth = 0.0
        bref = None
        cx0 = int(math.floor((x - r) * INV_CELL))
        cx1 = int(math.floor((x + r) * INV_CELL))
        cy0 = int(math.floor((y - r) * INV_CELL))
        cy1 = int(math.floor((y + r) * INV_CELL))
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                cell = grid.get((cx, cy))
                if cell is None:
                    continue
                for bi in cell[0]:
                    b = boxes[bi]
                    if not (b[6] & mask):
                        continue
                    x0 = b[0]
                    y0 = b[1]
                    x1 = b[2]
                    y1 = b[3]
                    if x + r <= x0 or x - r >= x1 or y + r <= y0 or y - r >= y1:
                        continue
                    px = x0 if x < x0 else (x1 if x > x1 else x)
                    py = y0 if y < y0 else (y1 if y > y1 else y)
                    dx = x - px
                    dy = y - py
                    d2 = dx * dx + dy * dy
                    if d2 >= r * r:
                        continue
                    if d2 > 1e-10:
                        d = math.sqrt(d2)
                        nx = dx / d
                        ny = dy / d
                        depth = r - d
                    else:
                        # центр внутри коробки: выталкиваем по ближайшей грани
                        dl = x - x0
                        dr = x1 - x
                        db = y - y0
                        dt = y1 - y
                        m = min(dl, dr, db, dt)
                        if m == dl:
                            nx, ny, depth = -1.0, 0.0, dl + r
                        elif m == dr:
                            nx, ny, depth = 1.0, 0.0, dr + r
                        elif m == db:
                            nx, ny, depth = 0.0, -1.0, db + r
                        else:
                            nx, ny, depth = 0.0, 1.0, dt + r
                    x += nx * depth
                    y += ny * depth
                    if depth > bdepth:
                        bdepth = depth
                        bnx = nx
                        bny = ny
                        bref = b[7]
                for ci in cell[1]:
                    c = circles[ci]
                    if not (c[4] & mask):
                        continue
                    dx = x - c[0]
                    dy = y - c[1]
                    rr = r + c[2]
                    d2 = dx * dx + dy * dy
                    if d2 >= rr * rr:
                        continue
                    if d2 > 1e-10:
                        d = math.sqrt(d2)
                        nx = dx / d
                        ny = dy / d
                    else:
                        d = 0.0
                        nx, ny = 1.0, 0.0
                    depth = rr - d
                    x += nx * depth
                    y += ny * depth
                    if depth > bdepth:
                        bdepth = depth
                        bnx = nx
                        bny = ny
                        bref = c[5]
        return x, y, bnx, bny, bdepth, bref

    def overlap_circle(self, x, y, r, mask):
        """Есть ли пересечение круга с чем-нибудь (без выталкивания)?"""
        res = self.push_circle(x, y, r, mask)
        return res[4] > 0.0

    def query_circles(self, x, y, r, mask):
        """Список кругов (id), пересекающих данный круг."""
        out = []
        grid = self.grid
        circles = self.circles
        for cx in range(int(math.floor((x - r) * INV_CELL)), int(math.floor((x + r) * INV_CELL)) + 1):
            for cy in range(int(math.floor((y - r) * INV_CELL)), int(math.floor((y + r) * INV_CELL)) + 1):
                cell = grid.get((cx, cy))
                if cell is None:
                    continue
                for ci in cell[1]:
                    c = circles[ci]
                    if not (c[4] & mask):
                        continue
                    dx = x - c[0]
                    dy = y - c[1]
                    rr = r + c[2]
                    if dx * dx + dy * dy < rr * rr and ci not in out:
                        out.append(ci)
        return out

    # ------------------------------------------------------------------
    def raycast(self, ox, oy, oz, dx, dy, dz, maxdist, mask=F_BULLET):
        """Луч в 3D.  (dx, dy, dz) — единичный вектор.

        Возвращает (t, nx, ny, nz, ref) или None.
        """
        self._stamp += 1
        stamp = self._stamp
        bstamp = self._bstamp
        cstamp = self._cstamp
        boxes = self.boxes
        circles = self.circles
        grid = self.grid
        best_t = maxdist
        best = None
        # земля
        if dz < -1e-6:
            tg = -oz / dz
            if 0.0 <= tg < best_t:
                best_t = tg
                best = (tg, 0.0, 0.0, 1.0, None)
        # обход сетки (DDA) в плоскости XY
        hl = math.hypot(dx, dy)
        if hl < 1e-6:
            cells = [(int(math.floor(ox * INV_CELL)), int(math.floor(oy * INV_CELL)))]
            steps = 0
        else:
            cells = None
        cx = int(math.floor(ox * INV_CELL))
        cy = int(math.floor(oy * INV_CELL))
        if cells is None:
            sx = 1 if dx > 0 else -1
            sy = 1 if dy > 0 else -1
            if abs(dx) > 1e-9:
                nxt = (cx + (1 if dx > 0 else 0)) * CELL
                tmx = (nxt - ox) / dx
                tdx = CELL / abs(dx)
            else:
                tmx = 1e30
                tdx = 1e30
            if abs(dy) > 1e-9:
                nyt = (cy + (1 if dy > 0 else 0)) * CELL
                tmy = (nyt - oy) / dy
                tdy = CELL / abs(dy)
            else:
                tmy = 1e30
                tdy = 1e30
        t_enter = 0.0
        guard = 0
        while guard < 400:
            guard += 1
            cell = grid.get((cx, cy))
            if cell is not None:
                for bi in cell[0]:
                    if bstamp[bi] == stamp:
                        continue
                    bstamp[bi] = stamp
                    b = boxes[bi]
                    if not (b[6] & mask):
                        continue
                    # slab-тест
                    t0 = 0.0
                    t1 = best_t
                    nx = ny = nz = 0.0
                    ok = True
                    # X
                    if abs(dx) < 1e-9:
                        if ox < b[0] or ox > b[2]:
                            continue
                    else:
                        ta = (b[0] - ox) / dx
                        tb = (b[2] - ox) / dx
                        sgn = -1.0
                        if ta > tb:
                            ta, tb = tb, ta
                            sgn = 1.0
                        if ta > t0:
                            t0 = ta
                            nx, ny, nz = sgn, 0.0, 0.0
                        if tb < t1:
                            t1 = tb
                        if t0 > t1:
                            continue
                    # Y
                    if abs(dy) < 1e-9:
                        if oy < b[1] or oy > b[3]:
                            continue
                    else:
                        ta = (b[1] - oy) / dy
                        tb = (b[3] - oy) / dy
                        sgn = -1.0
                        if ta > tb:
                            ta, tb = tb, ta
                            sgn = 1.0
                        if ta > t0:
                            t0 = ta
                            nx, ny, nz = 0.0, sgn, 0.0
                        if tb < t1:
                            t1 = tb
                        if t0 > t1:
                            continue
                    # Z
                    if abs(dz) < 1e-9:
                        if oz < b[4] or oz > b[5]:
                            continue
                    else:
                        ta = (b[4] - oz) / dz
                        tb = (b[5] - oz) / dz
                        sgn = -1.0
                        if ta > tb:
                            ta, tb = tb, ta
                            sgn = 1.0
                        if ta > t0:
                            t0 = ta
                            nx, ny, nz = 0.0, 0.0, sgn
                        if tb < t1:
                            t1 = tb
                        if t0 > t1:
                            continue
                    if t0 < best_t:
                        best_t = t0
                        best = (t0, nx, ny, nz, b[7])
                for ci in cell[1]:
                    if cstamp[ci] == stamp:
                        continue
                    cstamp[ci] = stamp
                    c = circles[ci]
                    if not (c[4] & mask):
                        continue
                    if hl < 1e-6:
                        continue
                    # луч против вертикального цилиндра
                    fx = ox - c[0]
                    fy = oy - c[1]
                    a = dx * dx + dy * dy
                    bq = fx * dx + fy * dy
                    cq = fx * fx + fy * fy - c[2] * c[2]
                    disc = bq * bq - a * cq
                    if disc < 0.0:
                        continue
                    t = (-bq - math.sqrt(disc)) / a
                    if t < 0.0 or t >= best_t:
                        continue
                    hz = oz + dz * t
                    if hz < 0.0 or hz > c[3]:
                        continue
                    hx = (fx + dx * t) / c[2]
                    hy = (fy + dy * t) / c[2]
                    best_t = t
                    best = (t, hx, hy, 0.0, c[5])
            if cells is not None:
                break
            # следующая клетка
            if tmx < tmy:
                t_enter = tmx
                tmx += tdx
                cx += sx
            else:
                t_enter = tmy
                tmy += tdy
                cy += sy
            if t_enter > best_t:
                break
        return best

    def los(self, ax, ay, bx, by, z=1.4, mask=F_SIGHT):
        """Прямая видимость между двумя точками (на высоте z)."""
        dx = bx - ax
        dy = by - ay
        d = math.hypot(dx, dy)
        if d < 0.01:
            return True
        hit = self.raycast(ax, ay, z, dx / d, dy / d, 0.0, d, mask)
        return hit is None

    def raycast2d(self, ax, ay, dx, dy, maxdist, z=1.0, mask=F_CAR):
        hit = self.raycast(ax, ay, z, dx, dy, 0.0, maxdist, mask)
        return maxdist if hit is None else hit[0]
