# -*- coding: utf-8 -*-
"""Изгиб города: из «чертежа по линейке» — в настоящие кривые улицы.

Генератор города (city.py) чертит кварталы и дороги на прямоугольной сетке — так ему проще, и так
устроены все его прямоугольники.  Этот модуль плавно сдвигает каждую точку чертежа:

    мир = W(чертёж) = чертёж + смещение(чертёж)

Смещение — сумма нескольких длинных волн, поэтому улицы плавно гнутся, перекрёстки перестают быть
прямыми, кварталы становятся неровными четырёхугольниками, и ни одна улица не идёт строго по оси.
Соседние точки сдвигаются почти одинаково, так что вблизи всё остаётся целым: стена — стеной,
полоса — полосой (ширина меняется на несколько процентов).

Где что считается:

  * всё, что СТРОИТСЯ (кварталы, дома, разметка, столкновения), живёт в координатах чертежа;
  * всё, что ДВИЖЕТСЯ (машины, люди, пули, камера), живёт в мире;
  * геометрия переводится в мир при сборке сеток (meshbuilder), вопросы игры к городу
    («какая здесь высота?», «упёрся ли в стену?») переводятся обратно в чертёж функцией inv().

Некоторым сооружениям гнуться нельзя: мосту, взлётной полосе, причалу с кораблём.  Для них заданы
«жёсткие» области — внутри такой области чертёж только сдвинут и повёрнут как целое.
"""
import math

IDENT = None


def _smooth(t):
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


class Warp(object):
    """Плавное отображение чертежа в мир и обратно.

    waves:  [(ax, ay, kx, ky, phase)] — смещение (ax, ay) * sin(kx * u + ky * v + phase);
    rigid:  [(x0, y0, x1, y1, r1, r2)] — отрезок-ось жёсткой области: ближе r1 к оси всё жёстко,
            дальше r2 — как у всех, между ними плавный переход;
    box:    (x0, y0, x1, y1) — где изгиб действует в полную силу; дальше, на полосе fade, он плавно
            сходит на нет (комнаты стоят далеко за краем карты, там мир совпадает с чертежом).
    """
    TILE = 64.0          # размер плитки таблицы обратного отображения
    STEP = 8.0           # шаг её узлов
    N = 8                # узлов на плитку по стороне (TILE / STEP)

    def __init__(self, waves, rigid=(), box=(-1e9, -1e9, 1e9, 1e9), fade=300.0, name=''):
        self.name = name
        self.waves = [tuple(float(v) for v in w) for w in waves]
        self.box = tuple(float(v) for v in box)
        self.fade = float(fade)
        self._tiles = {}
        self._memo = {}
        self.rigid = []
        for (x0, y0, x1, y1, r1, r2) in rigid:
            # подобие, которое переводит концы оси туда же, куда их переводят волны: по концам области
            # жёсткий кусок совпадает с окружением, и переход получается мягким
            ax, ay = self._base(x0, y0)
            bx, by = self._base(x1, y1)
            dx, dy = float(x1 - x0), float(y1 - y0)
            l2 = max(dx * dx + dy * dy, 1e-9)
            ex, ey = bx - ax, by - ay
            qc = (ex * dx + ey * dy) / l2                      # q = (B' - A') / (B - A), комплексное деление
            qs = (ey * dx - ex * dy) / l2
            self.rigid.append((float(x0), float(y0), dx, dy, l2, float(r1), float(r2),
                               float(x0), float(y0), ax, ay, qc, qs,
                               min(x0, x1) - r2, min(y0, y1) - r2, max(x0, x1) + r2, max(y0, y1) + r2))

    # ------------------------------------------------------------------
    def signature(self):
        import hashlib
        return hashlib.md5(repr((self.waves, self.rigid, self.box, self.fade)).encode()).hexdigest()[:12]

    def _window(self, u, v):
        x0, y0, x1, y1 = self.box
        d = max(x0 - u, u - x1, y0 - v, v - y1)
        if d <= 0.0:
            return 1.0
        return 1.0 - _smooth(d / self.fade)

    def _base(self, u, v):
        """Волны без жёстких областей."""
        x0, y0, x1, y1 = self.box
        d = max(x0 - u, u - x1, y0 - v, v - y1)
        if d >= self.fade:
            return u, v
        sx = sy = 0.0
        sin = math.sin
        for (ax, ay, kx, ky, ph) in self.waves:
            s = sin(kx * u + ky * v + ph)
            sx += ax * s
            sy += ay * s
        if d > 0.0:
            k = 1.0 - _smooth(d / self.fade)
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
    def fwd(self, u, v):
        """Чертёж -> мир."""
        x, y = self._base(u, v)
        hits = None
        for r in self.rigid:
            if u < r[13] or u > r[15] or v < r[14] or v > r[16]:
                continue
            px, py = u - r[0], v - r[1]
            t = (px * r[2] + py * r[3]) / r[4]
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            qx, qy = px - r[2] * t, py - r[3] * t
            dist = math.sqrt(qx * qx + qy * qy)
            if dist >= r[6]:
                continue
            if hits is None:
                hits = [(r, dist)]
            else:
                hits.append((r, dist))
        if hits is None:
            return x, y
        for (r, dist) in hits:
            w = 1.0 - _smooth((dist - r[5]) / (r[6] - r[5]))
            if len(hits) > 1:
                # рядом другая жёсткая область: в её середину эта не вмешивается
                for (o, od) in hits:
                    if o is not r:
                        w *= _smooth((od - o[5]) / 20.0)
            lx, ly = u - r[7], v - r[8]
            mx = r[9] + lx * r[11] - ly * r[12]
            my = r[10] + lx * r[12] + ly * r[11]
            x += (mx - x) * w
            y += (my - y) * w
        return x, y

    def rigid_at(self, u, v):
        """Номер жёсткой области, в середине которой лежит точка чертежа (-1 — не лежит).
        Там чертёж только сдвинут и повёрнут: прямое остаётся прямым."""
        k = -1
        for r in self.rigid:
            k += 1
            if u < r[13] or u > r[15] or v < r[14] or v > r[16]:
                continue
            px, py = u - r[0], v - r[1]
            t = (px * r[2] + py * r[3]) / r[4]
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            qx, qy = px - r[2] * t, py - r[3] * t
            if qx * qx + qy * qy < r[5] * r[5]:
                return k
        return -1

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
        x1, y1 = self.fwd(u + h, v)
        x0, y0 = self.fwd(u - h, v)
        x3, y3 = self.fwd(u, v + h)
        x2, y2 = self.fwd(u, v - h)
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

    # ------------------------------------------------------------------
    def _solve(self, x, y, u, v, n=6):
        """Обратное отображение итерациями от начального приближения (u, v)."""
        fwd = self.fwd
        for _ in range(n):
            fx, fy = fwd(u, v)
            ex, ey = x - fx, y - fy
            u += ex
            v += ey
            if ex * ex + ey * ey < 1e-8:
                break
        return u, v

    def inv_exact(self, x, y):
        """Мир -> чертёж, точно (для сборки и инструментов; в игре хватает inv)."""
        u, v = self.inv(x, y)
        a, b, c, d = self.jac(u, v)
        det = a * d - b * c
        for _ in range(4):
            fx, fy = self.fwd(u, v)
            ex, ey = x - fx, y - fy
            if ex * ex + ey * ey < 1e-10:
                break
            u += (d * ex - b * ey) / det
            v += (a * ey - c * ex) / det
        return u, v

    def _tile(self, key):
        """Плитка таблицы: (N + 1) x (N + 1) узлов с точным обратным отображением."""
        n = self.N
        step = self.STEP
        bx, by = key[0] * self.TILE, key[1] * self.TILE
        us = [0.0] * ((n + 1) * (n + 1))
        vs = [0.0] * ((n + 1) * (n + 1))
        # начальное приближение — от соседней готовой плитки, иначе сама точка
        u = v = None
        for j in range(n + 1):
            y = by + j * step
            if j > 0:
                u, v = us[(j - 1) * (n + 1)] , vs[(j - 1) * (n + 1)] + step
            for i in range(n + 1):
                x = bx + i * step
                if u is None:
                    u, v = x, y
                    u, v = self._solve(x, y, u, v, 40)
                else:
                    u, v = self._solve(x, y, u, v, 12)
                us[j * (n + 1) + i] = u
                vs[j * (n + 1) + i] = v
                u += step
        t = self._tiles[key] = (bx, by, us, vs)
        return t

    def inv(self, x, y):
        """Мир -> чертёж (таблица с линейной интерполяцией; ошибка — сантиметры)."""
        b = self.box
        f = self.fade + 80.0
        if x < b[0] - f or x > b[2] + f or y < b[1] - f or y > b[3] + f:
            return x, y
        tx = x // 64.0
        ty = y // 64.0
        t = self._tiles.get((tx, ty))
        if t is None:
            t = self._tile((tx, ty))
        fx = (x - t[0]) * 0.125
        fy = (y - t[1]) * 0.125
        i = int(fx)
        j = int(fy)
        if i > 7:
            i = 7
        if j > 7:
            j = 7
        fx -= i
        fy -= j
        k = j * 9 + i
        us = t[2]
        vs = t[3]
        gx = 1.0 - fx
        w00 = gx * (1.0 - fy)
        w10 = fx * (1.0 - fy)
        w01 = gx * fy
        w11 = fx * fy
        return (us[k] * w00 + us[k + 1] * w10 + us[k + 9] * w01 + us[k + 10] * w11,
                vs[k] * w00 + vs[k + 1] * w10 + vs[k + 9] * w01 + vs[k + 10] * w11)

    def rot_w(self, x, y):
        """Поворот чертежа в точке мира."""
        u, v = self.inv(x, y)
        return self.rot(u, v)

    # ------------------------------------------------------------------
    def check(self, x0, y0, x1, y1, step=20.0):
        """Насколько сильно гнётся: (наибольший поворот в градусах, наименьший и наибольший масштаб,
        наибольший перекос угла между улицами в градусах).  Для тестов и подбора волн."""
        rot = skew = 0.0
        smin, smax = 9.0, 0.0
        v = y0
        while v <= y1:
            u = x0
            while u <= x1:
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
