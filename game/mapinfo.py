# -*- coding: utf-8 -*-
"""Привязка текстуры карты (assets/tex/map.png) к мировым координатам."""
MAP_CX = 12.0
MAP_CY = -14.0
MAP_HALF = 640.0          # карта покрывает квадрат 1280 x 1280 м


def world_to_uv(x, y):
    return ((x - (MAP_CX - MAP_HALF)) / (2.0 * MAP_HALF), (y - (MAP_CY - MAP_HALF)) / (2.0 * MAP_HALF))
