# -*- coding: utf-8 -*-
"""Маленькие математические помощники (всё в метрах и радианах).

Соглашение об углах: yaw — обычный математический угол в плоскости XY
(0 = +X, pi/2 = +Y).  Для Panda3D:  H = degrees(yaw) - 90.
"""
import math
import random

PI = math.pi
TAU = math.pi * 2.0
DEG = 180.0 / math.pi
RAD = math.pi / 180.0


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def lerp(a, b, t):
    return a + (b - a) * t


def approach(cur, target, delta):
    """Сдвинуть cur к target не более чем на delta."""
    if cur < target:
        cur += delta
        return target if cur > target else cur
    cur -= delta
    return target if cur < target else cur


def wrap_angle(a):
    """Привести угол к диапазону (-pi, pi]."""
    a = (a + PI) % TAU - PI
    return a


def angle_diff(a, b):
    """Кратчайшая разница a - b в (-pi, pi]."""
    return (a - b + PI) % TAU - PI


def turn_towards(cur, target, max_delta):
    d = angle_diff(target, cur)
    if d > max_delta:
        d = max_delta
    elif d < -max_delta:
        d = -max_delta
    return wrap_angle(cur + d)


def damp(cur, target, rate, dt):
    """Экспоненциальное сглаживание, не зависящее от FPS."""
    return target + (cur - target) * math.exp(-rate * dt)


def damp_angle(cur, target, rate, dt):
    return wrap_angle(target + angle_diff(cur, target) * math.exp(-rate * dt))


def dist2(ax, ay, bx, by):
    dx = ax - bx
    dy = ay - by
    return dx * dx + dy * dy


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def yaw_to_h(yaw):
    return yaw * DEG - 90.0


def h_to_yaw(h):
    return (h + 90.0) * RAD


def smoothstep(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp_color(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))


def seg_point_dist2(px, py, ax, ay, bx, by):
    """Квадрат расстояния от точки до отрезка и параметр t."""
    dx = bx - ax
    dy = by - ay
    l2 = dx * dx + dy * dy
    if l2 <= 1e-9:
        return dist2(px, py, ax, ay), 0.0
    t = ((px - ax) * dx + (py - ay) * dy) / l2
    t = clamp(t, 0.0, 1.0)
    cx = ax + dx * t
    cy = ay + dy * t
    return dist2(px, py, cx, cy), t


def bezier2(p0, p1, p2, t):
    u = 1.0 - t
    return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])


def bezier2_tangent(p0, p1, p2, t):
    u = 1.0 - t
    return (2 * u * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0]),
            2 * u * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1]))


class Rng(random.Random):
    """random.Random с парой удобных методов."""

    def chance(self, p):
        return self.random() < p

    def rangef(self, a, b):
        return a + (b - a) * self.random()

    def pick(self, seq):
        return seq[int(self.random() * len(seq)) % len(seq)]

    def weighted(self, pairs):
        """pairs: [(item, weight), ...]"""
        total = 0.0
        for _, w in pairs:
            total += w
        r = self.random() * total
        for item, w in pairs:
            r -= w
            if r <= 0:
                return item
        return pairs[-1][0]
