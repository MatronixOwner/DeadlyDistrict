# -*- coding: utf-8 -*-
"""Рельеф за пределами кварталов: берега, пляжи, холмы.

Высоты посчитаны заранее скриптом tools/gen_terrain.py и лежат в assets/terrain:

    terrain.json   размеры сетки и подпись раскладки города, для которой рельеф построен
    height.bin     высоты узлов сетки (int16, сантиметры) и карта покрытия (uint8)
    terrain.bam    готовая геометрия (её читает citymesh.py)

Здесь — только чтение и быстрый ответ на вопрос «какая высота земли в точке».
Город (дороги и кварталы) плоский и лежит чуть выше рельефа: под ним рельеф прижат к FLAT.
"""
import array
import json
import os

FLAT = -0.05            # высота рельефа под городом и рядом с дорогами, м
WATER_Z = -0.7          # уровень моря (то же число, что в city.py)

# покрытие (terrain.cover)
C_GRASS, C_SAND, C_ROCK, C_FOREST, C_FIELD, C_SEA = 0, 1, 2, 3, 4, 5


class Terrain(object):

    def __init__(self, root=None):
        self.ok = False
        self.x0 = self.y0 = 0.0
        self.step = 10.0
        self.nx = self.ny = 0
        self.h = []                 # высоты, м (построчно: y, затем x)
        self.cover = b''
        self.meta = {}
        self.signature = None
        if root is not None:
            self.load(os.path.join(root, 'assets', 'terrain'))

    def load(self, folder):
        try:
            with open(os.path.join(folder, 'terrain.json'), encoding='utf-8') as f:
                meta = json.load(f)
            nx, ny = int(meta['nx']), int(meta['ny'])
            with open(os.path.join(folder, 'height.bin'), 'rb') as f:
                raw = f.read()
            n = nx * ny
            if len(raw) < n * 3:
                return False
            a = array.array('h')
            a.frombytes(raw[:n * 2])
            if a.itemsize != 2:
                return False
            import sys
            if sys.byteorder != 'little':
                a.byteswap()
            self.h = [v * 0.01 for v in a]
            self.cover = raw[n * 2:n * 3]
            self.nx, self.ny = nx, ny
            self.x0, self.y0 = float(meta['x0']), float(meta['y0'])
            self.step = float(meta['step'])
            self.meta = meta
            self.signature = meta.get('signature')
            self.ok = True
        except Exception:
            self.ok = False
        return self.ok

    # ------------------------------------------------------------------
    @property
    def x1(self):
        return self.x0 + (self.nx - 1) * self.step

    @property
    def y1(self):
        return self.y0 + (self.ny - 1) * self.step

    def height(self, x, y):
        """Высота земли в точке (м).  За краем сетки — высота ближайшего края."""
        if not self.ok:
            return FLAT
        step = self.step
        nx = self.nx
        fx = (x - self.x0) / step
        fy = (y - self.y0) / step
        if fx < 0.0:
            fx = 0.0
        elif fx > nx - 1.001:
            fx = nx - 1.001
        if fy < 0.0:
            fy = 0.0
        elif fy > self.ny - 1.001:
            fy = self.ny - 1.001
        ix = int(fx)
        iy = int(fy)
        tx = fx - ix
        ty = fy - iy
        k = iy * nx + ix
        h = self.h
        h00 = h[k]
        h11 = h[k + nx + 1]
        # клетка делится на два треугольника диагональю 00-11 — так же, как в готовой геометрии
        if tx > ty:
            h10 = h[k + 1]
            return h00 + (h10 - h00) * tx + (h11 - h10) * ty
        h01 = h[k + nx]
        return h00 + (h11 - h01) * tx + (h01 - h00) * ty

    def cover_at(self, x, y):
        """Покрытие в точке: трава, песок, камень, лес, поле или море."""
        if not self.ok:
            return C_GRASS
        ix = int(round((x - self.x0) / self.step))
        iy = int(round((y - self.y0) / self.step))
        if ix < 0 or iy < 0 or ix >= self.nx or iy >= self.ny:
            return C_SEA
        return self.cover[iy * self.nx + ix]

    def slope(self, x, y, d=4.0):
        """Уклон в точке: (dz/dx, dz/dy)."""
        return ((self.height(x + d, y) - self.height(x - d, y)) / (2.0 * d),
                (self.height(x, y + d) - self.height(x, y - d)) / (2.0 * d))
