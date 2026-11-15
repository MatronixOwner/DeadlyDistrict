# -*- coding: utf-8 -*-
"""Привязка текстуры карты (assets/tex/map.png) к мировым координатам."""
MAP_CX = 335.0
MAP_CY = 340.0
MAP_HALF = 1100.0         # карта покрывает квадрат 2200 x 2200 м: остров, Заречье и восточный берег


def world_to_uv(x, y):
    return ((x - (MAP_CX - MAP_HALF)) / (2.0 * MAP_HALF), (y - (MAP_CY - MAP_HALF)) / (2.0 * MAP_HALF))
