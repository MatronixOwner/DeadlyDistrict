# -*- coding: utf-8 -*-
"""Изгиб города: из «чертежа по линейке» — в настоящие кривые улицы.

Генератор города (city.py) чертит кварталы и дороги на прямоугольной сетке — так ему проще, и так
устроены все его прямоугольники.  Этот модуль плавно сдвигает каждую точку чертежа:

    мир = W(чертёж) = чертёж + смещение(чертёж)

Отображение складывается из трёх частей (по порядку):

  1. «Неровная сетка».  Каждый перекрёсток чертежа сдвинут на свои несколько метров (lattice), а между
     перекрёстками сдвиг меняется плавно.  Улицы перестают быть прямыми и параллельными, кварталы
     становятся неровными четырёхугольниками — каждый своей формы, как в городе, который рос сам.
  2. Длинные волны (waves): плавный изгиб целых районов.
  3. «Лоскуты» (patches).  Город поделён на районы; у каждого района своё положение и свой поворот —
     район переносится целиком, как жёсткая пластина.  Между районами на чертеже оставлены промежутки
     (парки-клинья, проливы): в них отображение плавно переходит от одного района к другому, и на
     местности промежуток становится клином.  Так остров раскрывается веером вокруг бухты, а улицы
     соседних районов идут под углом друг к другу.

Соседние точки внутри района сдвигаются почти одинаково, так что вблизи всё остаётся целым: стена —
стеной, полоса — полосой.  Растягиваются только промежутки между районами, где застройки нет.

Считать всё это для каждой точки дорого, поэтому готовое отображение раскладывается в таблицу с шагом
4 метра (по плиткам, по мере надобности), а между узлами берётся линейно: fwd() и inv() — это поиск в
таблице.  Что дороги и стены строятся по той же таблице, по которой игра потом спрашивает «где я на
чертеже», даже удобно: расхождений между картинкой и столкновениями нет вовсе.

Где что считается:

  * всё, что СТРОИТСЯ (кварталы, дома, разметка, столкновения), живёт в координатах чертежа;
  * всё, что ДВИЖЕТСЯ (машины, люди, пули, камера), живёт в мире;
  * геометрия переводится в мир при сборке сеток (meshbuilder), вопросы игры к городу
    («какая здесь высота?», «упёрся ли в стену?») переводятся обратно в чертёж функцией inv().

Некоторым сооружениям гнуться нельзя: мосту, взлётной полосе, сухогрузу у причала.  Для них заданы
«прямые» — отрезки чертежа, которые обязаны остаться отрезками.  Вдоль такой прямой изгиб выправляется:
каждая точка рядом с ней сдвигается ровно на столько, на сколько волны увели с прямой ближайшую точку
отрезка.  Сама прямая становится идеально прямой, её окрестность идёт за ней, а по концам отрезка
поправка равна нулю — поэтому кварталы у въезда на мост она почти не трогает.
"""
import math
from array import array
from bisect import bisect_right

IDENT = None


def _smooth(t):
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def _tangents(vals, pos):
    """Наклоны в узлах для гладкой кривой через точки (pos[i], vals[i]): парабола по трём соседям."""
    n = len(vals)
    if n < 2:
        return [0.0] * n
    sl = [(vals[i + 1] - vals[i]) / (pos[i + 1] - pos[i]) for i in range(n - 1)]
    out = [sl[0]]
    for i in range(1, n - 1):
        h0, h1 = pos[i] - pos[i - 1], pos[i + 1] - pos[i]
        out.append((sl[i - 1] * h1 + sl[i] * h0) / (h0 + h1))
    out.append(sl[-1])
    return out


def _span(groups, x):
    """Где точка относительно районов: (g, s) — между районами g и g + 1, s — доля следующего
    (0 — целиком в районе g)."""
    if x <= groups[0][1]:
        return 0, 0.0
    n = len(groups)
    for g in range(n - 1):
        lo = groups[g + 1][0]
        if x < lo:
            hi = groups[g][1]
            return g, _smooth((x - hi) / (lo - hi))
        if x <= groups[g + 1][1]:
            return g + 1, 0.0
    return n - 1, 0.0


# многочлены Эрмита по степеням: значение в начале, значение в конце, наклон в начале, наклон в конце
_HERM = ((1.0, 0.0, -3.0, 2.0), (0.0, 0.0, 3.0, -2.0), (0.0, 1.0, -2.0, 1.0), (0.0, 0.0, -1.0, 1.0))


class Warp(object):
    """Плавное отображение чертежа в мир и обратно.

    waves:   [(ax, ay, kx, ky, phase)] — смещение (ax, ay) * sin(kx * u + ky * v + phase);
    lattice: dict(xs, ys, d) — «неровная сетка»: линии чертежа xs и ys, d[(i, j)] = (dx, dy) — на сколько
             сдвинут узел (перекрёсток) этих линий; между узлами сдвиг идёт гладко (бикубически);
    patches: dict(xg, yg, t) — районы-«лоскуты»: xg и yg — полосы чертежа [(от, до)] по x и по y, в которых
             район переносится целиком; t[h][g] = (cos, sin, tx, ty) — куда: мир = поворот * точка + сдвиг.
             Между полосами отображение плавно переходит от района к району;
    rigid:   [(x0, y0, x1, y1, r1, band)] — прямые по порядку: отрезок, который должен остаться прямым;
             ближе r1 к нему поправка действует целиком, на полосе band плавно сходит на нет.  Прямые
             выправляются по очереди, каждая следующая — поверх предыдущих, поэтому полоса следующей
             не должна доставать до предыдущих прямых;
    box:     (x0, y0, x1, y1) — где изгиб действует в полную силу; дальше, на полосе fade, он плавно
             сходит на нет (комнаты стоят далеко за краем карты, там мир совпадает с чертежом).
    """
    TAIL = 70.0          # на столько за концом прямой её поправка сходит на нет
    TILE = 64.0          # размер плитки таблицы
    STEP = 4.0           # шаг её узлов
    N = 16               # узлов на плитку по стороне (TILE / STEP)

    def __init__(self, waves, rigid=(), box=(-1e9, -1e9, 1e9, 1e9), fade=300.0, name='', extra=(),
                 lattice=None, patches=None):
        """extra: [(waves, box, fade)] — отдельные области со своими волнами далеко от основной
        (городок пролога): области не должны перекрываться, прямых (rigid) в них нет."""
        self.name = name
        self.waves = [tuple(float(v) for v in w) for w in waves]
        self.box = tuple(float(v) for v in box)
        self.fade = float(fade)
        self.extra = [([tuple(float(v) for v in w) for w in wv], tuple(float(v) for v in bx), float(fd))
                      for (wv, bx, fd) in extra]
        self._tiles = {}             # таблица «мир -> чертёж»
        self._ftiles = {}            # таблица «чертёж -> мир»
        self._memo = {}
        self._sig = [self.waves, self.box, self.fade, self.extra]
        self._lat = None
        if lattice:
            self._lat_setup(lattice)
        self._pat = None
        if patches:
            self._pat_setup(patches)
        self.rigid = []
        for (x0, y0, x1, y1, r1, band) in rigid:
            k = len(self.rigid)
            # подобие, которое переводит концы отрезка туда же, куда их переводит всё предыдущее:
            # по концам поправка равна нулю
            ax, ay = self._upto(k, x0, y0)
            bx, by = self._upto(k, x1, y1)
            dx, dy = float(x1 - x0), float(y1 - y0)
            l2 = max(dx * dx + dy * dy, 1e-9)
            ex, ey = bx - ax, by - ay
            qc = (ex * dx + ey * dy) / l2                      # q = (B' - A') / (B - A), комплексное деление
            qs = (ey * dx - ex * dy) / l2
            reach = r1 + band + self.TAIL
            self.rigid.append((float(x0), float(y0), dx, dy, l2, float(r1), float(band), ax, ay, qc, qs,
                               min(x0, x1) - reach, min(y0, y1) - reach, max(x0, x1) + reach, max(y0, y1) + reach))
        self._sig.append(self.rigid)

    # ------------------------------------------------------------------
    def signature(self):
        import hashlib
        return hashlib.md5(repr(self._sig).encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # неровная сетка
    # ------------------------------------------------------------------
    def _lat_setup(self, lat):
        xs = [float(v) for v in lat['xs']]
        ys = [float(v) for v in lat['ys']]
        d = lat['d']
        nx, ny = len(xs), len(ys)
        comp = []
        for k in (0, 1):
            f = [[float(d.get((i, j), (0.0, 0.0))[k]) for i in range(nx)] for j in range(ny)]      # f[j][i]
            fx = [_tangents(f[j], xs) for j in range(ny)]
            cols = [_tangents([f[j][i] for j in range(ny)], ys) for i in range(nx)]                # cols[i][j]
            fy = [[cols[i][j] for i in range(nx)] for j in range(ny)]
            cols = [_tangents([fx[j][i] for j in range(ny)], ys) for i in range(nx)]
            fxy = [[cols[i][j] for i in range(nx)] for j in range(ny)]
            comp.append((f, fx, fy, fxy))
        self._lat = (xs, ys, comp)
        self._lat_cells = {}
        self._sig.append(('lattice', xs, ys, sorted((k, tuple(v)) for k, v in d.items())))

    def _lat_cell(self, i, j):
        """Клетка сетки: коэффициенты двух бикубических многочленов (сдвиг по x и по y)."""
        xs, ys, comp = self._lat
        hx, hy = xs[i + 1] - xs[i], ys[j + 1] - ys[j]
        out = [xs[i], ys[j], 1.0 / hx, 1.0 / hy]
        for (f, fx, fy, fxy) in comp:
            g = ((f[j][i], f[j + 1][i], fy[j][i] * hy, fy[j + 1][i] * hy),
                 (f[j][i + 1], f[j + 1][i + 1], fy[j][i + 1] * hy, fy[j + 1][i + 1] * hy),
                 (fx[j][i] * hx, fx[j + 1][i] * hx, fxy[j][i] * hx * hy, fxy[j + 1][i] * hx * hy),
                 (fx[j][i + 1] * hx, fx[j + 1][i + 1] * hx, fxy[j][i + 1] * hx * hy, fxy[j + 1][i + 1] * hx * hy))
            c = []
            for m in range(4):                  # степень s
                for n in range(4):              # степень t
                    v = 0.0
                    for a in range(4):
                        ha = _HERM[a][m]
                        if ha != 0.0:
                            for b in range(4):
                                hb = _HERM[b][n]
                                if hb != 0.0:
                                    v += ha * g[a][b] * hb
                    c.append(v)
            out.append(tuple(c))
        r = self._lat_cells[(i, j)] = tuple(out)
        return r

    def _noise(self, u, v):
        xs, ys = self._lat[0], self._lat[1]
        i = bisect_right(xs, u) - 1
        if i < 0:
            i = 0
        elif i > len(xs) - 2:
            i = len(xs) - 2
        j = bisect_right(ys, v) - 1
        if j < 0:
            j = 0
        elif j > len(ys) - 2:
            j = len(ys) - 2
        cell = self._lat_cells.get((i, j))
        if cell is None:
            cell = self._lat_cell(i, j)
        s = (u - cell[0]) * cell[2]
        t = (v - cell[1]) * cell[3]
        if s < 0.0:
            s = 0.0
        elif s > 1.0:
            s = 1.0
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        t2 = t * t
        t3 = t2 * t
        c = cell[4]
        px = (c[0] + c[1] * t + c[2] * t2 + c[3] * t3 + s * (c[4] + c[5] * t + c[6] * t2 + c[7] * t3 + s * (
            c[8] + c[9] * t + c[10] * t2 + c[11] * t3 + s * (c[12] + c[13] * t + c[14] * t2 + c[15] * t3))))
        c = cell[5]
        py = (c[0] + c[1] * t + c[2] * t2 + c[3] * t3 + s * (c[4] + c[5] * t + c[6] * t2 + c[7] * t3 + s * (
            c[8] + c[9] * t + c[10] * t2 + c[11] * t3 + s * (c[12] + c[13] * t + c[14] * t2 + c[15] * t3))))
        return px, py

    # ------------------------------------------------------------------
    # районы-лоскуты
    # ------------------------------------------------------------------
    def _pat_setup(self, p):
        xg = [(float(a), float(b)) for (a, b) in p['xg']]
        yg = [(float(a), float(b)) for (a, b) in p['yg']]
        t = [[tuple(float(v) for v in tr) for tr in row] for row in p['t']]
        assert len(t) == len(yg) and all(len(row) == len(xg) for row in t)
        self._pat = (xg, yg, t)
        self._sig.append(('patches', xg, yg, t))

    def _patch(self, u, v, qx, qy):
        """Точка (qx, qy) — чертёж после сетки и волн; (u, v) — где она на чертеже: по ним выбирается район."""
        xg, yg, t = self._pat
        g, a = _span(xg, u)
        h, b = _span(yg, v)
        row = t[h]
        c, s, tx, ty = row[g]
        wx = c * qx - s * qy + tx
        wy = s * qx + c * qy + ty
        if a > 0.0:
            c, s, tx, ty = row[g + 1]
            wx += (c * qx - s * qy + tx - wx) * a
            wy += (s * qx + c * qy + ty - wy) * a
        if b > 0.0:
            row = t[h + 1]
            c, s, tx, ty = row[g]
            ex = c * qx - s * qy + tx
            ey = s * qx + c * qy + ty
            if a > 0.0:
                c, s, tx, ty = row[g + 1]
                ex += (c * qx - s * qy + tx - ex) * a
                ey += (s * qx + c * qy + ty - ey) * a
            wx += (ex - wx) * b
            wy += (ey - wy) * b
        return wx, wy

    # ------------------------------------------------------------------
    def _window(self, u, v):
        x0, y0, x1, y1 = self.box
        d = max(x0 - u, u - x1, y0 - v, v - y1)
        if d <= 0.0:
            return 1.0
        return 1.0 - _smooth(d / self.fade)

    def _base(self, u, v):
        """Сетка, волны и районы — без жёстких прямых."""
        x0, y0, x1, y1 = self.box
        d = max(x0 - u, u - x1, y0 - v, v - y1)
        waves, fade = self.waves, self.fade
        main = True
        if d >= fade:
            main = False
            for (waves, bx, fade) in self.extra:
                d = max(bx[0] - u, u - bx[2], bx[1] - v, v - bx[3])
                if d < fade:
                    break
            else:
                return u, v
        sx = sy = 0.0
        sin = math.sin
        for (ax, ay, kx, ky, ph) in waves:
            s = sin(kx * u + ky * v + ph)
            sx += ax * s
            sy += ay * s
        if main:
            if self._lat is not None:
                nx, ny = self._noise(u, v)
                sx += nx
                sy += ny
            if self._pat is not None:
                wx, wy = self._patch(u, v, u + sx, v + sy)
                sx, sy = wx - u, wy - v
        if d > 0.0:
            k = 1.0 - _smooth(d / fade)
            sx *= k
            sy *= k
        return u + sx, v + sy

    def _base_jac(self, u, v, h=0.5):
        x1, y1 = self._base(u + h, v)
        x0, y0 = self._base(u - h, v)
        x3, y3 = self._base(u, v + h)
        x2, y2 = self._base(u, v - h)
        k = 0.5 / h
        return (x1 - x0) * k, (x3 - x2) * k, (y1 - y0) * k, (y3 - y2) * k

    # ------------------------------------------------------------------
    def _upto(self, k, u, v):
        """Всё перечисленное и первые k выправленных прямых."""
        if k == 0:
            return self._base(u, v)
        r = self.rigid[k - 1]
        x, y = self._upto(k - 1, u, v)
        if u < r[11] or u > r[13] or v < r[12] or v > r[14]:
            return x, y
        px, py = u - r[0], v - r[1]
        t = (px * r[2] + py * r[3]) / r[4]
        # за концами отрезка прямая мысленно продолжается, а поправка плавно сходит на нет: без излома
        w = 1.0
        if t < 0.0 or t > 1.0:
            out = (-t if t < 0.0 else t - 1.0) * math.sqrt(r[4])
            if out >= self.TAIL:
                return x, y
            w = 1.0 - _smooth(out / self.TAIL)
        lx, ly = r[2] * t, r[3] * t                    # ближайшая точка прямой (от начала отрезка)
        qx, qy = px - lx, py - ly
        d = math.sqrt(qx * qx + qy * qy) - r[5]
        if d >= r[6]:
            return x, y
        if d > 0.0:
            w *= 1.0 - _smooth(d / r[6])
        bx, by = self._upto(k - 1, r[0] + lx, r[1] + ly)        # куда эту точку прямой увело
        mx = r[7] + lx * r[9] - ly * r[10]                      # где ей положено быть
        my = r[8] + lx * r[10] + ly * r[9]
        return x + (mx - bx) * w, y + (my - by) * w

    def exact(self, u, v):
        """Чертёж -> мир по формулам, без таблицы (ею пользуются fwd и всё остальное)."""
        if self.rigid:
            return self._upto(len(self.rigid), u, v)
        return self._base(u, v)

    def _region(self, x, y, pad=0.0):
        """Есть ли здесь изгиб вообще (иначе мир совпадает с чертежом)."""
        b = self.box
        f = self.fade + pad
        if b[0] - f <= x <= b[2] + f and b[1] - f <= y <= b[3] + f:
            return True
        for (wv, b, f) in self.extra:
            f += pad
            if b[0] - f <= x <= b[2] + f and b[1] - f <= y <= b[3] + f:
                return True
        return False

    def _ftile(self, key):
        """Плитка таблицы «чертёж -> мир»: (N + 1) x (N + 1) узлов."""
        n = self.N
        step = self.STEP
        bx, by = key[0] * self.TILE, key[1] * self.TILE
        xs = array('d')
        ys = array('d')
        exact = self.exact
        for j in range(n + 1):
            v = by + j * step
            for i in range(n + 1):
                x, y = exact(bx + i * step, v)
                xs.append(x)
                ys.append(y)
        t = self._ftiles[key] = (bx, by, xs, ys)
        return t

    def fwd(self, u, v):
        """Чертёж -> мир (таблица с линейной интерполяцией; ошибка — сантиметры)."""
        b = self.box
        f = self.fade
        if u < b[0] - f or u > b[2] + f or v < b[1] - f or v > b[3] + f:
            for (wv, b, f) in self.extra:
                if b[0] - f <= u <= b[2] + f and b[1] - f <= v <= b[3] + f:
                    break
            else:
                return u, v
        tx = u // 64.0
        ty = v // 64.0
        t = self._ftiles.get((tx, ty))
        if t is None:
            t = self._ftile((tx, ty))
        fx = (u - t[0]) * 0.25
        fy = (v - t[1]) * 0.25
        i = int(fx)
        j = int(fy)
        if i > 15:
            i = 15
        if j > 15:
            j = 15
        fx -= i
        fy -= j
        k = j * 17 + i
        xs = t[2]
        ys = t[3]
        gx = 1.0 - fx
        w00 = gx * (1.0 - fy)
        w10 = fx * (1.0 - fy)
        w01 = gx * fy
        w11 = fx * fy
        return (xs[k] * w00 + xs[k + 1] * w10 + xs[k + 17] * w01 + xs[k + 18] * w11,
                ys[k] * w00 + ys[k + 1] * w10 + ys[k + 17] * w01 + ys[k + 18] * w11)

    def fwd_memo(self, u, v):
        """То же, с памятью: при сборке сеток одна и та же точка встречается много раз."""
        key = (u, v)
        r = self._memo.get(key)
        if r is None:
            r = self._memo[key] = self.fwd(u, v)
        return r

    def forget(self):
        self._memo = {}

    def jac(self, u, v, h=0.25):
        """Матрица Якоби (a, b, c, d): dx = a du + b dv,  dy = c du + d dv."""
        fwd = self.fwd
        x1, y1 = fwd(u + h, v)
        x0, y0 = fwd(u - h, v)
        x3, y3 = fwd(u, v + h)
        x2, y2 = fwd(u, v - h)
        k = 0.5 / h
        return (x1 - x0) * k, (x3 - x2) * k, (y1 - y0) * k, (y3 - y2) * k

    def rot(self, u, v):
        """На какой угол повёрнут чертёж в этой точке (радианы)."""
        a, b, c, d = self.jac(u, v)
        return math.atan2(c - b, a + d)

    def dir(self, u, v, yaw):
        """Направление yaw на чертеже -> направление в мире (вдоль образа этой линии)."""
        a, b, c, d = self.jac(u, v)
        cs, sn = math.cos(yaw), math.sin(yaw)
        return math.atan2(c * cs + d * sn, a * cs + b * sn)

    def area(self, u, v):
        """Во сколько раз здесь растянута площадь (1 — как на чертеже; в клиньях между районами — больше)."""
        a, b, c, d = self.jac(u, v, 1.0)
        return a * d - b * c

    # ------------------------------------------------------------------
    # обратное отображение
    # ------------------------------------------------------------------
    def _inv_jac(self, u, v):
        a, b, c, d = self.jac(u, v, 0.5)
        det = a * d - b * c
        if abs(det) < 1e-3:
            return (1.0, 0.0, 0.0, 1.0)
        return (d / det, -b / det, -c / det, a / det)

    def _solve(self, x, y, u, v, J=None, n=40):
        """Найти точку чертежа, которая попадает в (x, y): от приближения (u, v), шагами Ньютона.
        J — обратная матрица Якоби от соседней точки (рядом она почти та же, и считать её заново незачем).
        Возвращает (u, v, J)."""
        fwd = self.fwd
        fx, fy = fwd(u, v)
        ex, ey = x - fx, y - fy
        e2 = ex * ex + ey * ey
        fresh = False
        k = 1.0
        for _ in range(n):
            if e2 < 1e-8:
                break
            if J is None:
                J = self._inv_jac(u, v)
                fresh = True
            du = (J[0] * ex + J[1] * ey) * k
            dv = (J[2] * ex + J[3] * ey) * k
            m = du * du + dv * dv
            if m > 2500.0:                              # шаг не длиннее 50 м: вдали от цели матрица уже не та
                m = 50.0 / math.sqrt(m)
                du *= m
                dv *= m
            gx, gy = fwd(u + du, v + dv)
            rx, ry = x - gx, y - gy
            r2 = rx * rx + ry * ry
            if r2 < e2 * 0.7:
                u += du
                v += dv
                ex, ey, e2 = rx, ry, r2
                fresh = False
                k = 1.0
            elif not fresh:
                J = None                                # матрица устарела
            else:
                k *= 0.5                                # свежая матрица не помогла: шаг короче
                if k < 0.02:
                    if r2 < e2:
                        u += du
                        v += dv
                    break
        return u, v, J

    def _guess(self, x, y):
        """Грубое приближение к обратному отображению: откуда начать поиск."""
        best = (x, y)
        fx, fy = self.fwd(x, y)
        e = (fx - x) ** 2 + (fy - y) ** 2
        if self._pat is not None and e > 1.0:
            seen = set()
            for row in self._pat[2]:
                for tr in row:
                    if tr in seen:
                        continue
                    seen.add(tr)
                    c, s, tx, ty = tr
                    dx, dy = x - tx, y - ty
                    u, v = c * dx + s * dy, -s * dx + c * dy
                    fx, fy = self.fwd(u, v)
                    d = (fx - x) ** 2 + (fy - y) ** 2
                    if d < e:
                        e = d
                        best = (u, v)
        return best

    def inv_exact(self, x, y):
        """Мир -> чертёж, точно (для сборки и инструментов; в игре хватает inv)."""
        u, v = self.inv(x, y)
        u, v, J = self._solve(x, y, u, v, None, 12)
        return u, v

    def _tile(self, key):
        """Плитка таблицы «мир -> чертёж»: (N + 1) x (N + 1) узлов с точным обратным отображением."""
        n = self.N
        step = self.STEP
        bx, by = key[0] * self.TILE, key[1] * self.TILE
        us = array('d', bytes(8 * (n + 1) * (n + 1)))
        vs = array('d', bytes(8 * (n + 1) * (n + 1)))
        solve = self._solve
        J = None
        u = v = None
        for j in range(n + 1):
            y = by + j * step
            if j > 0:
                # начальное приближение — от узла ниже
                k0 = (j - 1) * (n + 1)
                u, v = us[k0], vs[k0]
                if J is not None:
                    u += J[1] * step
                    v += J[3] * step
            for i in range(n + 1):
                x = bx + i * step
                if u is None:
                    u, v = self._guess(x, y)
                u, v, J = solve(x, y, u, v, J)
                us[j * (n + 1) + i] = u
                vs[j * (n + 1) + i] = v
                if J is not None:                       # следующий узел — на шаг правее
                    u += J[0] * step
                    v += J[2] * step
                else:
                    u += step
        t = self._tiles[key] = (bx, by, us, vs)
        return t

    def inv(self, x, y):
        """Мир -> чертёж (таблица с линейной интерполяцией; ошибка — сантиметры)."""
        b = self.box
        f = self.fade + 80.0
        if x < b[0] - f or x > b[2] + f or y < b[1] - f or y > b[3] + f:
            for (wv, b, f) in self.extra:
                f += 80.0
                if b[0] - f <= x <= b[2] + f and b[1] - f <= y <= b[3] + f:
                    break
            else:
                return x, y
        tx = x // 64.0
        ty = y // 64.0
        t = self._tiles.get((tx, ty))
        if t is None:
            t = self._tile((tx, ty))
        fx = (x - t[0]) * 0.25
        fy = (y - t[1]) * 0.25
        i = int(fx)
        j = int(fy)
        if i > 15:
            i = 15
        if j > 15:
            j = 15
        fx -= i
        fy -= j
        k = j * 17 + i
        us = t[2]
        vs = t[3]
        gx = 1.0 - fx
        w00 = gx * (1.0 - fy)
        w10 = fx * (1.0 - fy)
        w01 = gx * fy
        w11 = fx * fy
        return (us[k] * w00 + us[k + 1] * w10 + us[k + 17] * w01 + us[k + 18] * w11,
                vs[k] * w00 + vs[k + 1] * w10 + vs[k + 17] * w01 + vs[k + 18] * w11)

    def rot_w(self, x, y):
        """Поворот чертежа в точке мира."""
        u, v = self.inv(x, y)
        return self.rot(u, v)

    # ------------------------------------------------------------------
    def check(self, x0, y0, x1, y1, step=20.0, skip=None):
        """Насколько сильно гнётся: (наибольший поворот в градусах, наименьший и наибольший масштаб,
        наибольший перекос угла между улицами в градусах).  Для тестов и подбора.
        skip(u, v) -> True — эту точку не считать (клинья между районами растянуты намеренно)."""
        rot = skew = 0.0
        smin, smax = 9.0, 0.0
        v = y0
        while v <= y1:
            u = x0
            while u <= x1:
                if skip is None or not skip(u, v):
                    a, b, c, d = self.jac(u, v)
                    rot = max(rot, abs(math.degrees(math.atan2(c - b, a + d))))
                    lu, lv = math.hypot(a, c), math.hypot(b, d)
                    smin = min(smin, lu, lv)
                    smax = max(smax, lu, lv)
                    cosang = (a * b + c * d) / (lu * lv)
                    skew = max(skew, abs(math.degrees(math.asin(max(-1.0, min(1.0, cosang))))))
                u += step
            v += step
        return rot, smin, smax, skew
