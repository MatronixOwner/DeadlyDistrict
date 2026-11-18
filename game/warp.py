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

Некоторым сооружениям гнуться нельзя: мосту, взлётной полосе, сухогрузу у причала.  Для них заданы
«прямые» — отрезки чертежа, которые обязаны остаться отрезками.  Вдоль такой прямой изгиб выправляется:
каждая точка рядом с ней сдвигается ровно на столько, на сколько волны увели с прямой ближайшую точку
отрезка.  Сама прямая становится идеально прямой, её окрестность идёт за ней, а по концам отрезка
поправка равна нулю — поэтому кварталы у въезда на мост она почти не трогает.
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
    rigid:  [(x0, y0, x1, y1, r1, band)] — прямые по порядку: отрезок, который должен остаться прямым;
            ближе r1 к нему поправка действует целиком, на полосе band плавно сходит на нет.  Прямые
            выправляются по очереди, каждая следующая — поверх предыдущих, поэтому полоса следующей
            не должна доставать до предыдущих прямых;
    box:    (x0, y0, x1, y1) — где изгиб действует в полную силу; дальше, на полосе fade, он плавно
            сходит на нет (комнаты стоят далеко за краем карты, там мир совпадает с чертежом).
    """
    TAIL = 70.0          # на столько за концом прямой её поправка сходит на нет
    TILE = 64.0          # размер плитки таблицы обратного отображения
    STEP = 4.0           # шаг её узлов
    N = 16               # узлов на плитку по стороне (TILE / STEP)

    def __init__(self, waves, rigid=(), box=(-1e9, -1e9, 1e9, 1e9), fade=300.0, name=''):
        self.name = name
        self.waves = [tuple(float(v) for v in w) for w in waves]
        self.box = tuple(float(v) for v in box)
        self.fade = float(fade)
        self._tiles = {}
        self._memo = {}
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
    def _upto(self, k, u, v):
        """Волны и первые k выправленных прямых."""
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

    def fwd(self, u, v):
        """Чертёж -> мир."""
        if self.rigid:
            return self._upto(len(self.rigid), u, v)
        return self._base(u, v)

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
