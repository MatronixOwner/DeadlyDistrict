# -*- coding: utf-8 -*-
"""Двухколёсный транспорт: позы посадки ездока и загрузка готовых моделей (bikemodels.py)."""

POSES = {
    'chair': dict(mix=0.0, lean=0.0, hand=(0.48, 0.33), foot=(0.20, 0.44, -0.44), knee=(0.22, 0.45, -0.01)),
    'cruise': dict(mix=0.2, lean=0.0, hand=(0.48, 0.27), foot=(0.24, 0.36, -0.48), knee=(0.23, 0.445, -0.055)),
    'std': dict(mix=0.35, lean=10.0, hand=(0.51, 0.135), foot=(0.28, 0.21, -0.54), knee=(0.24, 0.415, -0.16)),
    'bike': dict(mix=0.5, lean=20.0, hand=(0.505, 0.0), foot=(0.32, 0.05, -0.545), knee=(0.255, 0.36, -0.25)),
    'pillion': dict(clips=(('sit', 0.55), ('ride', 0.45)), lean=4.0),
    'tub': dict(clips=(('sit', 0.6), ('sit_ground', 0.4)), lean=0.0),
    'bench': dict(clips=(('sit', 1.0),), lean=0.0),
}
PELVIS_UP = 0.10
SOLE = 0.09

KINDS = {
    'chopper': dict(wb=1.62, rf=0.32, rr=0.32, wf=0.15, wr=0.19, seat=0.71, pose='chair'),
    'bicycle': dict(wb=1.17, rf=0.34, rr=0.34, wf=0.045, wr=0.045, seat=0.93, pose='std'),
    'bmx': dict(wb=1.08, rf=0.26, rr=0.26, wf=0.055, wr=0.055, seat=0.72, pose='cruise'),
}
_models = None


def use_models(models):
    global _models
    from . import bikemodels
    _models = models
    bikemodels.clear()


def modelled(kind):
    from . import bikemodels
    return bikemodels.has(_models, kind)


def clear():
    from . import bikemodels
    bikemodels.clear()


def geo(kind):
    from . import bikemodels
    return bikemodels.Geo(_models, kind)


def light_points(kind):
    from . import bikemodels
    return bikemodels.light_points(_models, kind)


def build(assets, kind, paint):
    from . import bikemodels
    return bikemodels.build(assets, _models, kind, paint)
