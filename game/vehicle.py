# -*- coding: utf-8 -*-
"""Транспорт: типы машин, модели, аркадная физика, повреждения."""
import math
import random

from panda3d.core import NodePath, LPoint3, LVector3, LQuaternion

from .meshbuilder import MeshBuilder
from .mathutil import clamp, approach, wrap_angle, angle_diff, yaw_to_h, damp, DEG
from .collision import F_CAR
from .city import CURB, WATER_Z

GLASS = (0.16, 0.24, 0.33, 1.0)
DARK = (0.07, 0.07, 0.08, 1.0)
TYRE = (0.06, 0.06, 0.07, 1.0)
HUB = (0.62, 0.64, 0.66, 1.0)
LIGHT_F = (1.0, 0.97, 0.80, 1.0)
LIGHT_R = (0.75, 0.06, 0.05, 1.0)
CHROME = (0.72, 0.74, 0.78, 1.0)

PAINTS = [
    (0.80, 0.10, 0.09), (0.12, 0.26, 0.62), (0.90, 0.90, 0.88), (0.10, 0.10, 0.12), (0.55, 0.57, 0.60),
    (0.10, 0.42, 0.22), (0.92, 0.72, 0.10), (0.42, 0.10, 0.44), (0.85, 0.42, 0.10), (0.36, 0.22, 0.14),
    (0.16, 0.56, 0.66), (0.60, 0.08, 0.20), (0.80, 0.76, 0.60), (0.24, 0.28, 0.34),
]
PAINT_NAMES = ['Красный', 'Синий', 'Белый', 'Чёрный', 'Серебристый', 'Зелёный', 'Жёлтый', 'Фиолетовый', 'Оранжевый',
               'Коричневый', 'Бирюзовый', 'Вишнёвый', 'Бежевый', 'Графитовый']
RUST_PAINTS = [(0.42, 0.30, 0.22), (0.36, 0.38, 0.34), (0.50, 0.44, 0.34), (0.30, 0.24, 0.26)]


class Spec(object):
    def __init__(self, name, title, L, W, H, **kw):
        self.name = name
        self.title = title
        self.L, self.W, self.H = L, W, H
        self.clear = 0.22
        self.belt = 0.78
        self.hood = 1.15
        self.trunk = 0.85
        self.ws_rake = 0.55
        self.rw_rake = 0.5
        self.nose_drop = 0.08
        self.tail_drop = 0.04
        self.cabin_inset = 0.14
        self.wheel_r = 0.31
        self.wheel_w = 0.2
        self.front_axle = L / 2 - 0.82
        self.rear_axle = -L / 2 + 0.86
        self.mass = 1300.0
        self.accel = 5.5
        self.top = 36.0
        self.brake = 15.0
        self.grip = 7.5
        self.steer = 0.60
        self.health = 1000.0
        self.seats = 4
        self.cargo = 0.0            # доля салона (сзади) без окон
        self.box = None             # (длина, высота, цвет) — фургон грузовика
        self.extras = ()
        self.paints = None          # фиксированные цвета
        self.value = 400
        self.radio = True
        self.engine = 'car'
        self.bike = False           # ездок сидит верхом и виден (мотоциклы, велосипед, квадроцикл)
        self.lean = False           # наклоняется в повороты (двухколёсные)
        self.nofire = False         # ни мотора, ни бака: не горит и не взрывается, а просто ломается (велосипеды)
        self.kit = ()               # обвес с завода: детали, которые есть у машины всегда (см. tuning.KIT)
        self.tune = None            # заводской тюнинг: словарь «деталь -> вариант»
        for k, v in kw.items():
            setattr(self, k, v)
        self.wheelbase = self.front_axle - self.rear_axle
        r = W * 0.5
        span = L * 0.5 - r
        n = max(2, int(math.ceil((2 * span) / (1.55 * r))) + 1)
        self.circles = [(-span + 2 * span * i / (n - 1)) for i in range(n)]
        self.cr = r
        self.bound = math.hypot(L * 0.5, W * 0.5)


SPECS = {}


def _add(spec):
    SPECS[spec.name] = spec


_add(Spec('sedan', 'Волна', 4.5, 1.8, 1.5))
_add(Spec('hatch', 'Кроха', 3.9, 1.65, 1.45, trunk=0.02, rw_rake=0.35, hood=0.9, top=31.0, accel=5.0,
          mass=950.0, value=250))
_add(Spec('sports', 'Комета', 4.6, 1.86, 1.3, hood=1.4, ws_rake=0.8, rw_rake=0.9, trunk=0.5, nose_drop=0.2,
          belt=0.68, clear=0.16, top=56.0, accel=9.5, grip=9.5, extras=('spoiler',), value=2500, mass=1200.0))
_add(Spec('muscle', 'Бизон', 5.2, 1.9, 1.42, hood=1.7, trunk=1.0, top=48.0, accel=8.2, grip=6.2, value=1200,
          mass=1500.0))
_add(Spec('suv', 'Хозяин', 4.6, 1.95, 1.8, belt=1.0, clear=0.36, wheel_r=0.40, trunk=0.02, rw_rake=0.3,
          mass=2200.0, top=37.0, accel=5.6, health=1300.0, value=1500))
_add(Spec('pickup', 'Трудяга', 4.6, 1.9, 1.74, belt=0.95, clear=0.34, hood=1.25, trunk=2.1, rw_rake=0.1,
          wheel_r=0.38, mass=1900.0, top=34.0, accel=5.2, health=1200.0, extras=('bed',), value=600))
_add(Spec('van', 'Грузовичок', 5.2, 1.95, 2.36, hood=0.7, ws_rake=0.45, trunk=0.02, rw_rake=0.04, belt=1.0,
          cargo=0.6, mass=2300.0, top=32.0, accel=4.6, health=1300.0, value=500, wheel_r=0.34))
_add(Spec('taxi', 'Такси', 5.0, 1.8, 1.56, extras=('taxi',), paints=[(0.95, 0.74, 0.08)], value=450))
_add(Spec('police', 'Патруль', 5.1, 1.84, 1.6, extras=('police',), paints=[(0.92, 0.92, 0.94)], top=47.0,
          accel=8.4, grip=8.5, health=1400.0, value=0, radio=False))
_add(Spec('ambulance', 'Скорая', 5.4, 2.05, 2.5, hood=0.75, ws_rake=0.45, trunk=0.02, rw_rake=0.04, belt=1.0,
          cargo=0.62, mass=2600.0, top=36.0, accel=5.6, health=1500.0, extras=('ambulance',),
          paints=[(0.94, 0.94, 0.94)], value=0, wheel_r=0.36, radio=False))
_add(Spec('bus', 'Автобус', 10.5, 2.5, 3.0, belt=1.1, hood=0.1, ws_rake=0.12, trunk=0.02, rw_rake=0.05,
          clear=0.36, wheel_r=0.48, wheel_w=0.3, mass=9000.0, top=25.0, accel=3.0, steer=0.5, health=2600.0,
          front_axle=3.3, rear_axle=-2.9, seats=8, value=800, engine='truck',
          paints=[(0.86, 0.52, 0.10), (0.16, 0.42, 0.70), (0.86, 0.86, 0.84)]))
_add(Spec('truck', 'Тягач', 6.8, 2.4, 2.5, hood=0.35, ws_rake=0.2, trunk=4.9, rw_rake=0.05, belt=1.25,
          clear=0.45, wheel_r=0.48, wheel_w=0.3, mass=7000.0, top=28.0, accel=3.3, steer=0.5, health=2200.0,
          front_axle=2.4, rear_axle=-2.1, seats=2, box=(4.4, 3.1, (0.86, 0.86, 0.84)), value=700,
          engine='truck', tail_drop=0.35))
_add(Spec('enforcer', 'Спецназ', 5.8, 2.2, 2.7, hood=0.8, ws_rake=0.4, trunk=0.02, rw_rake=0.04, belt=1.1,
          cargo=0.66, mass=3800.0, top=41.0, accel=6.8, health=2600.0, extras=('lightbar',),
          paints=[(0.10, 0.13, 0.24)], value=0, wheel_r=0.4, clear=0.38, radio=False, engine='truck'))
_add(Spec('fbi', 'Агент', 4.7, 1.86, 1.46, paints=[(0.05, 0.05, 0.06)], top=53.0, accel=9.4, grip=9.0,
          health=1600.0, value=0, radio=False))
_add(Spec('army', 'Барракуда', 6.8, 2.4, 2.6, hood=0.4, ws_rake=0.2, trunk=4.7, rw_rake=0.05, belt=1.3,
          clear=0.5, wheel_r=0.52, wheel_w=0.32, mass=8000.0, top=34.0, accel=4.6, steer=0.5, health=3200.0,
          front_axle=2.4, rear_axle=-2.1, seats=2, box=(4.3, 3.1, (0.26, 0.31, 0.2)),
          paints=[(0.26, 0.31, 0.2)], value=0, radio=False, engine='truck', tail_drop=0.35))
_add(Spec('beater', 'Ржавчина', 4.4, 1.76, 1.5, paints=RUST_PAINTS, top=29.0, accel=4.2, health=750.0,
          value=120, grip=6.5))
_add(Spec('lowrider', 'Барон', 4.3, 1.8, 2.0, hood=1.6, trunk=1.2, clear=0.14, top=42.0, accel=6.5,
          paints=[(0.42, 0.10, 0.44), (0.10, 0.42, 0.22), (0.60, 0.08, 0.20)], value=900, grip=6.8))

# --- машины на тех же кузовах, но других пропорций, окраски и назначения
_add(Spec('limo', 'Лимузин', 6.9, 1.9, 1.42, hood=1.7, trunk=1.0, top=40.0, accel=5.6, grip=5.8, value=3000,
          mass=2300.0, seats=6, health=1300.0, steer=0.5,
          paints=[(0.05, 0.05, 0.06), (0.92, 0.92, 0.90), (0.60, 0.08, 0.20)]))
_add(Spec('racer', 'Болид', 4.5, 1.9, 1.16, hood=1.4, ws_rake=0.8, rw_rake=0.9, trunk=0.5, nose_drop=0.2,
          belt=0.62, clear=0.12, top=66.0, accel=12.0, grip=11.0, brake=19.0, value=6000, mass=1050.0,
          paints=[(0.92, 0.72, 0.10), (0.80, 0.10, 0.09), (0.12, 0.26, 0.62)], kit=('wing',)))
_add(Spec('minibus', 'Маршрутка', 4.7, 1.9, 2.0, hood=0.5, ws_rake=0.45, trunk=0.02, rw_rake=0.04, belt=1.0,
          mass=1900.0, top=31.0, accel=4.4, health=1300.0, value=600, wheel_r=0.31, seats=8,
          paints=[(0.92, 0.72, 0.10), (0.90, 0.90, 0.88), (0.30, 0.50, 0.62), (0.62, 0.20, 0.14)], kit=('route',)))
_add(Spec('firetruck', 'Пожарная', 7.6, 2.5, 3.1, hood=0.5, ws_rake=0.3, trunk=0.02, rw_rake=0.04, belt=1.2,
          clear=0.42, wheel_r=0.46, wheel_w=0.3, mass=7500.0, top=34.0, accel=4.4, steer=0.5, health=3000.0,
          front_axle=2.7, rear_axle=-2.4, seats=4, paints=[(0.80, 0.10, 0.09)], value=0, radio=False,
          engine='truck', kit=('ladder',)))
_add(Spec('cashvan', 'Инкассатор', 5.6, 2.1, 2.5, hood=0.75, ws_rake=0.45, trunk=0.02, rw_rake=0.04, belt=1.0,
          cargo=0.62, mass=3600.0, top=34.0, accel=4.8, health=3400.0, value=0, wheel_r=0.36,
          paints=[(0.10, 0.30, 0.20)], engine='truck', kit=('beacon',)))
_add(Spec('icecream', 'Мороженое', 5.2, 1.95, 2.4, hood=0.7, ws_rake=0.45, trunk=0.02, rw_rake=0.04, belt=1.0,
          cargo=0.6, mass=2300.0, top=27.0, accel=3.8, health=1200.0, value=400, wheel_r=0.34,
          paints=[(0.96, 0.84, 0.88)], kit=('cone',)))
_add(Spec('hotrod', 'Хот-род', 4.0, 1.86, 1.62, hood=1.6, trunk=1.2, clear=0.12, top=54.0, accel=9.6, grip=7.4,
          paints=[(0.80, 0.10, 0.09), (0.05, 0.05, 0.06), (0.85, 0.42, 0.10)], value=3200, mass=1100.0,
          kit=('blower', 'pipes')))
_add(Spec('jeep', 'Вездеход', 4.5, 2.0, 2.02, belt=1.1, clear=0.50, wheel_r=0.44, trunk=0.02, rw_rake=0.3,
          mass=2100.0, top=36.0, accel=6.0, grip=8.2, health=1600.0, value=1800,
          paints=[(0.26, 0.31, 0.20), (0.44, 0.38, 0.26), (0.24, 0.28, 0.34)], kit=('bullbar', 'lightbar', 'spare')))
_add(Spec('pizza', 'Доставка', 3.9, 1.65, 1.45, trunk=0.02, rw_rake=0.35, hood=0.9, top=33.0, accel=5.6,
          mass=950.0, value=300, paints=[(0.80, 0.10, 0.09), (0.90, 0.90, 0.88)], kit=('box',)))
_add(Spec('brick', 'Кирпич', 4.8, 1.76, 1.44, hood=1.35, trunk=1.0, top=33.0, accel=4.8, mass=1350.0, value=320,
          health=1150.0, grip=7.2))
_add(Spec('tuner', 'Дрифт', 3.9, 1.7, 1.38, trunk=0.02, rw_rake=0.35, hood=0.9, top=46.0, accel=8.6, grip=8.0,
          mass=900.0, value=2400, clear=0.14,
          paints=[(0.16, 0.56, 0.66), (0.42, 0.10, 0.44), (0.85, 0.42, 0.10), (0.10, 0.42, 0.22)],
          tune={'spoiler': 3, 'rims': 3, 'susp': 1, 'neon': 0, 'exhaust': 1}))
# --- мотоциклы, скутер, мопед, велосипеды, квадроцикл, трайк, мотоцикл с коляской (модели собирает bikes.py)
_add(Spec('bike', 'Стрела', 2.10, 0.74, 1.16, bike=True, lean=True, seats=1, mass=230.0, top=64.0, accel=13.0,
          grip=9.0, brake=18.0, health=420.0, wheel_r=0.30, front_axle=0.70, rear_axle=-0.70, radio=False,
          value=2200, engine='bike', steer=0.50))
_add(Spec('chopper', 'Ворон', 2.60, 0.86, 1.30, bike=True, lean=True, seats=2, mass=310.0, top=50.0, accel=9.0,
          grip=7.6, brake=14.0, health=520.0, wheel_r=0.32, front_axle=0.81, rear_axle=-0.81, radio=False,
          value=1900, engine='bike', steer=0.44,
          paints=[(0.05, 0.05, 0.06), (0.60, 0.08, 0.20), (0.12, 0.26, 0.62), (0.36, 0.22, 0.14)]))
_add(Spec('scooter', 'Оса', 1.80, 0.66, 1.16, bike=True, lean=True, seats=1, mass=120.0, top=27.0, accel=6.0,
          grip=7.5, brake=12.0, health=300.0, wheel_r=0.22, front_axle=0.63, rear_axle=-0.63, radio=False,
          value=350, engine='bike', steer=0.56))
_add(Spec('dirt', 'Кузнечик', 2.16, 0.80, 1.28, bike=True, lean=True, seats=1, mass=150.0, top=44.0, accel=11.0,
          grip=8.2, brake=15.0, health=380.0, wheel_r=0.34, front_axle=0.73, rear_axle=-0.73, radio=False,
          value=1200, engine='bike', steer=0.54, clear=0.34))
_add(Spec('bicycle', 'Велосипед', 1.85, 0.58, 1.14, bike=True, lean=True, seats=1, mass=40.0, top=11.5, accel=3.2,
          grip=8.5, brake=9.0, health=140.0, wheel_r=0.34, front_axle=0.585, rear_axle=-0.585, radio=False,
          value=60, engine='none', steer=0.6, nofire=True))
_add(Spec('quad', 'Квадро', 2.20, 1.22, 1.20, bike=True, lean=False, seats=1, mass=280.0, top=34.0, accel=8.0,
          grip=8.8, brake=14.0, health=560.0, wheel_r=0.29, front_axle=0.63, rear_axle=-0.63, radio=False,
          value=900, engine='bike', steer=0.5, clear=0.26,
          paints=[(0.80, 0.10, 0.09), (0.92, 0.72, 0.10), (0.10, 0.42, 0.22), (0.12, 0.26, 0.62)]))
_add(Spec('moped', 'Стриж', 1.78, 0.60, 1.08, bike=True, lean=True, seats=1, mass=70.0, top=17.0, accel=4.4,
          grip=7.6, brake=10.0, health=240.0, wheel_r=0.28, front_axle=0.59, rear_axle=-0.59, radio=False,
          value=180, engine='bike', steer=0.58,
          paints=[(0.80, 0.10, 0.09), (0.10, 0.42, 0.22), (0.12, 0.26, 0.62), (0.85, 0.42, 0.10), (0.30, 0.50, 0.62)]))
_add(Spec('copbike', 'Патрульный мотоцикл', 2.60, 0.86, 1.50, bike=True, lean=True, seats=1, mass=320.0, top=58.0,
          accel=11.5, grip=8.8, brake=17.0, health=640.0, wheel_r=0.32, front_axle=0.81, rear_axle=-0.81, radio=False,
          value=0, engine='bike', steer=0.48, paints=[(0.92, 0.92, 0.94)]))
_add(Spec('sidecar', 'Тайга', 2.60, 1.72, 1.30, bike=True, lean=False, seats=2, mass=380.0, top=38.0, accel=6.6,
          grip=7.8, brake=12.0, health=620.0, wheel_r=0.32, front_axle=0.81, rear_axle=-0.81, radio=False,
          value=800, engine='bike', steer=0.46,
          paints=[(0.24, 0.30, 0.20), (0.05, 0.05, 0.06), (0.36, 0.22, 0.14), (0.14, 0.24, 0.40)]))
_add(Spec('trike', 'Мамонт', 2.60, 1.44, 1.30, bike=True, lean=False, seats=2, mass=430.0, top=46.0, accel=8.4,
          grip=8.0, brake=13.0, health=680.0, wheel_r=0.32, front_axle=0.81, rear_axle=-0.81, radio=False,
          value=2100, engine='bike', steer=0.44,
          paints=[(0.60, 0.08, 0.20), (0.05, 0.05, 0.06), (0.85, 0.42, 0.10), (0.42, 0.10, 0.44)]))
_add(Spec('bmx', 'Трюкач', 1.60, 0.62, 1.12, bike=True, lean=True, seats=1, mass=30.0, top=13.0, accel=4.2,
          grip=9.0, brake=10.0, health=160.0, wheel_r=0.26, front_axle=0.54, rear_axle=-0.54, radio=False,
          value=90, engine='none', steer=0.66, nofire=True,
          paints=[(0.80, 0.10, 0.09), (0.92, 0.72, 0.10), (0.16, 0.56, 0.66), (0.05, 0.05, 0.06), (0.42, 0.10, 0.44)]))
_add(Spec('tourer', 'Странник', 2.70, 0.92, 1.50, bike=True, lean=True, seats=2, mass=400.0, top=52.0, accel=8.6,
          grip=8.4, brake=15.0, health=640.0, wheel_r=0.32, front_axle=0.81, rear_axle=-0.81, radio=True,
          value=2600, engine='bike', steer=0.46,
          paints=[(0.50, 0.08, 0.12), (0.10, 0.20, 0.42), (0.08, 0.08, 0.09), (0.60, 0.62, 0.64), (0.10, 0.34, 0.26)]))
_add(Spec('courier', 'Курьер', 1.86, 0.66, 1.16, bike=True, lean=True, seats=1, mass=130.0, top=25.0, accel=5.6,
          grip=7.5, brake=12.0, health=300.0, wheel_r=0.22, front_axle=0.63, rear_axle=-0.63, radio=False,
          value=380, engine='bike', steer=0.56,
          paints=[(0.12, 0.12, 0.13), (0.80, 0.10, 0.09), (0.16, 0.50, 0.28), (0.90, 0.90, 0.88)]))
_add(Spec('cargo', 'Муравей', 2.20, 1.10, 1.30, bike=True, lean=False, seats=1, mass=260.0, top=20.0, accel=4.2,
          grip=7.4, brake=11.0, health=460.0, wheel_r=0.22, front_axle=0.75, rear_axle=-0.75, radio=False,
          value=420, engine='bike', steer=0.5,
          paints=[(0.16, 0.36, 0.56), (0.30, 0.40, 0.26), (0.62, 0.20, 0.14), (0.56, 0.56, 0.52)]))
_add(Spec('kart', 'Карт', 1.60, 1.12, 0.80, bike=True, lean=False, seats=1, mass=120.0, top=33.0, accel=10.0,
          grip=10.5, brake=16.0, health=260.0, wheel_r=0.14, front_axle=0.53, rear_axle=-0.53, radio=False,
          value=700, engine='bike', steer=0.62, clear=0.05,
          paints=[(0.80, 0.10, 0.09), (0.92, 0.72, 0.10), (0.12, 0.26, 0.62), (0.10, 0.42, 0.22), (0.90, 0.90, 0.88)]))
_add(Spec('caddy', 'Гольф-кар', 2.30, 1.20, 1.72, bike=True, lean=False, seats=2, mass=320.0, top=15.0, accel=4.0,
          grip=7.6, brake=10.0, health=420.0, wheel_r=0.21, front_axle=0.78, rear_axle=-0.78, radio=False,
          value=500, engine='none', steer=0.55,
          paints=[(0.92, 0.92, 0.88), (0.16, 0.44, 0.30), (0.10, 0.20, 0.42), (0.60, 0.10, 0.14)]))
BIKES = tuple(k for k, s in SPECS.items() if s.bike)

# какие машины встречаются в каком районе (тип, вес)
ZONE_CARS = {
    'D': [('sedan', 5), ('taxi', 4), ('sports', 1.2), ('suv', 2), ('hatch', 2), ('bus', 0.8), ('van', 1), ('brick', 2),
          ('muscle', 0.6), ('limo', 0.5), ('minibus', 0.9), ('bike', 0.7), ('scooter', 0.9), ('pizza', 0.6),
          ('cashvan', 0.3), ('racer', 0.15), ('firetruck', 0.2), ('tourer', 0.5), ('copbike', 0.35),
          ('courier', 1.0)],
    'O': [('sedan', 4), ('hatch', 4), ('taxi', 2), ('van', 1.5), ('beater', 1.5), ('bus', 0.6), ('pickup', 1), ('brick', 3),
          ('minibus', 1.2), ('scooter', 1.4), ('bicycle', 1.0), ('pizza', 0.8), ('icecream', 0.3), ('chopper', 0.4),
          ('moped', 1.0), ('sidecar', 0.4), ('copbike', 0.25), ('courier', 1.1), ('cargo', 0.7)],
    'G': [('beater', 6), ('lowrider', 2.5), ('pickup', 2), ('hatch', 2), ('van', 1), ('muscle', 1), ('chopper', 1.6), ('brick', 1.5),
          ('hotrod', 0.6), ('dirt', 0.8), ('bicycle', 0.8), ('moped', 1.0), ('trike', 0.7), ('bmx', 0.8),
          ('sidecar', 0.5), ('cargo', 0.8), ('kart', 0.3)],
    'R': [('sedan', 4), ('suv', 4), ('hatch', 3), ('pickup', 1.5), ('muscle', 1), ('sports', 0.5), ('jeep', 1.0), ('brick', 2.5),
          ('bicycle', 1.4), ('scooter', 0.8), ('icecream', 0.5), ('minibus', 0.6), ('quad', 0.3), ('bmx', 0.9),
          ('moped', 0.6), ('tourer', 0.4), ('sidecar', 0.5), ('caddy', 0.9), ('courier', 0.6), ('kart', 0.3)],
    'I': [('truck', 4), ('van', 4), ('pickup', 3), ('beater', 2), ('sedan', 1), ('jeep', 0.8), ('dirt', 0.7), ('brick', 1),
          ('cashvan', 0.3), ('sidecar', 0.5), ('moped', 0.5), ('cargo', 1.4)],
    'B': [('sports', 2.5), ('sedan', 3), ('taxi', 3), ('muscle', 2), ('suv', 2), ('hatch', 2), ('bus', 0.5),
          ('limo', 0.8), ('bike', 1.4), ('chopper', 1.0), ('tuner', 1.2), ('racer', 0.4), ('hotrod', 0.6),
          ('quad', 0.5), ('icecream', 0.6), ('trike', 0.8), ('tourer', 0.7), ('bmx', 0.5), ('caddy', 1.0),
          ('kart', 0.6), ('courier', 0.5)],
    'P': [('sedan', 4), ('taxi', 3), ('hatch', 2), ('bicycle', 1.5), ('scooter', 0.8), ('bmx', 1.0), ('caddy', 0.8)],
}

_body_cache = {}
_wheel_cache = {}
_extra_cache = {}


def _shade(c, k):
    return (c[0] * k, c[1] * k, c[2] * k, 1.0)


def build_body(spec, paint, wreck=False):
    """Кузов машины (+Y — вперёд)."""
    mb = MeshBuilder()
    K = None
    p = (paint[0], paint[1], paint[2], 1.0)
    p2 = _shade(paint, 0.82)
    glass = GLASS if not wreck else (0.03, 0.03, 0.03, 1.0)
    hl, hw = spec.L * 0.5, spec.W * 0.5
    cl, belt, roof = spec.clear, spec.belt, spec.H
    yf, yr = hl, -hl
    y_wsb = yf - spec.hood
    y_wst = y_wsb - spec.ws_rake
    y_rwb = yr + spec.trunk
    y_rwt = y_rwb + spec.rw_rake
    if y_rwt > y_wst - 0.3:
        y_rwt = y_wst - 0.3
    zf = belt - spec.nose_drop
    zr = belt - spec.tail_drop
    ci = spec.cabin_inset
    xb = hw - 0.03          # салон: низ
    xt = hw - ci            # салон: верх
    for sx in (-1.0, 1.0):
        x = hw * sx

        def q(a, b, c, d, col, key=K):
            if sx > 0:
                mb.quad(key, a, b, c, d, color=col)
            else:
                mb.quad(key, b, a, d, c, color=col)
        # борта
        q((x, yr, cl), (x, y_rwb, cl), (x, y_rwb, belt), (x, yr, zr), p)
        q((x, y_rwb, cl), (x, y_wsb, cl), (x, y_wsb, belt), (x, y_rwb, belt), p)
        q((x, y_wsb, cl), (x, yf, cl), (x, yf, zf), (x, y_wsb, belt), p)
        # пороги
        q((x * 1.005, yr + 0.3, cl), (x * 1.005, yf - 0.3, cl), (x * 1.005, yf - 0.3, cl + 0.1),
          (x * 1.005, yr + 0.3, cl + 0.1), DARK)
        # колёсные арки
        for wy in (spec.front_axle, spec.rear_axle):
            r = spec.wheel_r + 0.07
            q((x * 1.004, wy - r, cl), (x * 1.004, wy + r, cl), (x * 1.004, wy + r * 0.8, cl + r * 1.25),
              (x * 1.004, wy - r * 0.8, cl + r * 1.25), DARK)
        # окна салона
        xbs, xts = xb * sx, xt * sx
        cab_len = y_wsb - y_rwb
        y_c = y_rwb + cab_len * spec.cargo      # граница грузового отсека
        if spec.cargo > 0.01:
            q((xbs, y_rwb, belt), (xbs, y_c, belt), (xts, min(y_c, y_wst), roof), (xts, y_rwt, roof), p)
            q((xbs, y_c, belt), (xbs, y_wsb, belt), (xts, y_wst, roof), (xts, min(y_c, y_wst), roof), glass)
        else:
            q((xbs, y_rwb, belt), (xbs, y_wsb, belt), (xts, y_wst, roof), (xts, y_rwt, roof), glass)
            # стойки
            e = 1.006
            ym = (y_rwb + y_wsb) * 0.5 - 0.1
            ymt = (y_rwt + y_wst) * 0.5 - 0.1
            q((xbs * e, ym - 0.06, belt), (xbs * e, ym + 0.06, belt), (xts * e, ymt + 0.06, roof),
              (xts * e, ymt - 0.06, roof), p2)
            if cab_len > 4.0:
                for k in (0.25, 0.75):
                    ya = y_rwb + cab_len * k
                    yb = y_rwt + (y_wst - y_rwt) * k
                    q((xbs * e, ya - 0.06, belt), (xbs * e, ya + 0.06, belt), (xts * e, yb + 0.06, roof),
                      (xts * e, yb - 0.06, roof), p2)
        # рамка крыши над окнами
        q((xts * 1.004, y_rwt, roof - 0.07), (xts * 1.004, y_wst, roof - 0.07), (xts * 1.004, y_wst, roof),
          (xts * 1.004, y_rwt, roof), p2)
    # капот, багажник, крыша
    hood_c = p
    mb.quad(K, (-hw, y_wsb, belt), (hw, y_wsb, belt), (hw, yf, zf), (-hw, yf, zf), color=hood_c)
    if 'bed' in spec.extras:
        mb.quad(K, (-hw + 0.1, yr + 0.08, belt - 0.42), (hw - 0.1, yr + 0.08, belt - 0.42),
                (hw - 0.1, y_rwb, belt - 0.42), (-hw + 0.1, y_rwb, belt - 0.42), color=DARK)
        for sx in (-1, 1):
            x = (hw - 0.1) * sx
            a, b_ = (x, yr + 0.08, belt - 0.42), (x, y_rwb, belt - 0.42)
            c_, d_ = (x, y_rwb, belt), (x, yr + 0.08, belt)
            if sx > 0:
                mb.quad(K, b_, a, d_, c_, color=p2)
            else:
                mb.quad(K, a, b_, c_, d_, color=p2)
            mb.quad(K, (min(x, hw * sx), yr, belt), (max(x, hw * sx), yr, belt), (max(x, hw * sx), y_rwb, belt),
                    (min(x, hw * sx), y_rwb, belt), color=p)
        mb.quad(K, (-hw + 0.1, yr + 0.08, belt - 0.42), (-hw + 0.1, yr + 0.08, belt),
                (hw - 0.1, yr + 0.08, belt), (hw - 0.1, yr + 0.08, belt - 0.42), color=p2)
    else:
        mb.quad(K, (-hw, yr, zr), (hw, yr, zr), (hw, y_rwb, belt), (-hw, y_rwb, belt), color=p)
    mb.quad(K, (-xt, y_rwt, roof), (xt, y_rwt, roof), (xt, y_wst, roof), (-xt, y_wst, roof), color=p)
    # лобовое и заднее стёкла
    mb.quad(K, (xb, y_wsb, belt), (-xb, y_wsb, belt), (-xt, y_wst, roof), (xt, y_wst, roof), color=glass)
    if spec.cargo > 0.01:
        mb.quad(K, (-xb, y_rwb, belt), (xb, y_rwb, belt), (xt, y_rwt, roof), (-xt, y_rwt, roof), color=p)
        # задние двери
        mb.quad(K, (0.02, yr - 0.004, cl + 0.15), (-0.02, yr - 0.004, cl + 0.15), (-0.02, yr - 0.004, roof - 0.1),
                (0.02, yr - 0.004, roof - 0.1), color=DARK)
    else:
        mb.quad(K, (-xb, y_rwb, belt), (xb, y_rwb, belt), (xt, y_rwt, roof), (-xt, y_rwt, roof), color=glass)
    # перед
    mb.quad(K, (hw, yf, cl), (-hw, yf, cl), (-hw, yf, zf), (hw, yf, zf), color=p)
    e = yf + 0.012
    gz0, gz1 = cl + 0.2, zf - 0.08
    mb.quad(K, (hw * 0.5, e, gz0), (-hw * 0.5, e, gz0), (-hw * 0.5, e, gz1), (hw * 0.5, e, gz1), color=DARK)
    lf = LIGHT_F if not wreck else DARK
    lr = LIGHT_R if not wreck else DARK
    for sx in (-1, 1):
        x0, x1 = hw * 0.56 * sx, hw * 0.94 * sx
        mb.quad(K, (max(x0, x1), e, gz1 - 0.2), (min(x0, x1), e, gz1 - 0.2), (min(x0, x1), e, gz1),
                (max(x0, x1), e, gz1), color=lf)
    mb.box(K, -hw - 0.03, yf - 0.05, cl - 0.02, hw + 0.03, yf + 0.08, cl + 0.2, DARK, faces='xXYZz')
    # зад
    mb.quad(K, (-hw, yr, cl), (hw, yr, cl), (hw, yr, zr), (-hw, yr, zr), color=p)
    e = yr - 0.012
    tz1 = zr - 0.08
    for sx in (-1, 1):
        x0, x1 = hw * 0.5 * sx, hw * 0.95 * sx
        mb.quad(K, (min(x0, x1), e, tz1 - 0.18), (max(x0, x1), e, tz1 - 0.18), (max(x0, x1), e, tz1),
                (min(x0, x1), e, tz1), color=lr)
    mb.quad(K, (-0.26, e, cl + 0.24), (0.26, e, cl + 0.24), (0.26, e, cl + 0.38), (-0.26, e, cl + 0.38),
            color=(0.9, 0.9, 0.86, 1.0) if not wreck else DARK)
    mb.box(K, -hw - 0.03, yr - 0.08, cl - 0.02, hw + 0.03, yr + 0.05, cl + 0.2, DARK, faces='xXyZz')
    # днище
    mb.quad(K, (-hw, yf, cl), (hw, yf, cl), (hw, yr, cl), (-hw, yr, cl), color=DARK)
    # дополнения
    ex = spec.extras
    if spec.box:
        bl, bh, bc = spec.box
        if wreck:
            bc = (0.12, 0.11, 0.1)
        y0 = yr + 0.02
        mb.box(K, -hw, y0, belt - 0.25, hw, y0 + bl, bh, (bc[0], bc[1], bc[2], 1.0))
        mb.quad(K, (0.02, y0 - 0.004, belt - 0.1), (-0.02, y0 - 0.004, belt - 0.1), (-0.02, y0 - 0.004, bh - 0.1),
                (0.02, y0 - 0.004, bh - 0.1), color=DARK)
        mb.box(K, -hw * 0.5, yr + 0.3, cl + 0.05, hw * 0.5, y_rwb, belt - 0.25, DARK)
    if 'spoiler' in ex:
        mb.box(K, -hw * 0.92, yr + 0.02, zr + 0.16, hw * 0.92, yr + 0.3, zr + 0.2, p2)
        for sx in (-0.6, 0.6):
            mb.box(K, hw * sx - 0.03, yr + 0.1, zr - 0.02, hw * sx + 0.03, yr + 0.2, zr + 0.16, DARK)
    if 'taxi' in ex and not wreck:
        mb.box(K, -0.32, -0.25, roof, 0.32, 0.05, roof + 0.16, (0.98, 0.9, 0.3, 1.0), shade=False)
        mb.quad(K, (-0.22, -0.254, roof + 0.03), (0.22, -0.254, roof + 0.03), (0.22, -0.254, roof + 0.13),
                (-0.22, -0.254, roof + 0.13), color=DARK)
        mb.quad(K, (0.22, 0.054, roof + 0.03), (-0.22, 0.054, roof + 0.03), (-0.22, 0.054, roof + 0.13),
                (0.22, 0.054, roof + 0.13), color=DARK)
        # шашечки
        for sx in (-1, 1):
            x = hw * sx * 1.004
            n = 10
            for k in range(n):
                if k % 2:
                    continue
                ya = y_rwb + (y_wsb - y_rwb) * k / n
                yb = y_rwb + (y_wsb - y_rwb) * (k + 1) / n
                a, b_, c_, d_ = (x, ya, belt - 0.2), (x, yb, belt - 0.2), (x, yb, belt - 0.08), (x, ya, belt - 0.08)
                if sx > 0:
                    mb.quad(K, a, b_, c_, d_, color=DARK)
                else:
                    mb.quad(K, b_, a, d_, c_, color=DARK)
    if ('police' in ex or 'ambulance' in ex) and not wreck:
        band = (0.10, 0.22, 0.62, 1.0) if 'police' in ex else (0.82, 0.10, 0.10, 1.0)
        for sx in (-1, 1):
            x = hw * sx * 1.005
            a, b_ = (x, yr + 0.05, belt - 0.3), (x, yf - 0.05, belt - 0.3)
            c_, d_ = (x, yf - 0.05, belt - 0.12), (x, yr + 0.05, belt - 0.12)
            if sx > 0:
                mb.quad(K, a, b_, c_, d_, color=band)
            else:
                mb.quad(K, b_, a, d_, c_, color=band)
        mb.quad(K, (-hw * 0.7, y_wsb + 0.1, belt + 0.004), (hw * 0.7, y_wsb + 0.1, belt + 0.004),
                (hw * 0.7, yf - 0.1, zf + 0.004), (-hw * 0.7, yf - 0.1, zf + 0.004), color=band)
    if ('police' in ex or 'ambulance' in ex or 'lightbar' in ex) and not wreck:
        ym = (y_wst + y_rwt) * 0.5 if 'police' in ex else y_wst - 0.3
        mb.box(K, -hw * 0.62, ym - 0.12, roof, -0.04, ym + 0.12, roof + 0.13, (0.85, 0.08, 0.06, 1.0), shade=False)
        mb.box(K, 0.04, ym - 0.12, roof, hw * 0.62, ym + 0.12, roof + 0.13, (0.08, 0.16, 0.9, 1.0), shade=False)
        mb.box(K, -0.04, ym - 0.1, roof, 0.04, ym + 0.1, roof + 0.1, CHROME)
    return mb


def build_wheel(spec):
    mb = MeshBuilder()
    r, w = spec.wheel_r, spec.wheel_w
    mb.cylinder_x(None, -w * 0.5, w * 0.5, 0.0, 0.0, r, 8, TYRE, cap_color=TYRE)
    # колпаки с «спицами», чтобы было видно вращение
    for sx in (-1, 1):
        x = (w * 0.5 + 0.004) * sx
        rr = r * 0.6
        n = 6
        for i in range(n):
            a0, a1 = i * 2 * math.pi / n, (i + 1) * 2 * math.pi / n
            col = HUB if i % 2 == 0 else (0.42, 0.44, 0.46, 1.0)
            p0 = (x, math.cos(a0) * rr, math.sin(a0) * rr)
            p1 = (x, math.cos(a1) * rr, math.sin(a1) * rr)
            if sx > 0:
                mb.tri(None, (x, 0, 0), p0, p1, color=col)
            else:
                mb.tri(None, (x, 0, 0), p1, p0, color=col)
    return mb


def body_template(assets, kind, paint_idx, wreck=False):
    key = (kind, paint_idx, wreck)
    np_ = _body_cache.get(key)
    if np_ is None:
        spec = SPECS[kind]
        if wreck:
            paint = (0.11, 0.10, 0.09)
        elif spec.paints:
            paint = spec.paints[paint_idx % len(spec.paints)]
        else:
            paint = PAINTS[paint_idx % len(PAINTS)]
        np_ = build_body(spec, paint, wreck).build('body', assets.apply_state)
        _body_cache[key] = np_
    return np_


def wheel_template(assets, kind):
    np_ = _wheel_cache.get(kind)
    if np_ is None:
        np_ = build_wheel(SPECS[kind]).build('wheel', assets.apply_state)
        _wheel_cache[kind] = np_
    return np_


def _light_points(kind, info):
    """Где у машины фары, задние огни и маячок: по модели, а если её нет — по габаритам."""
    spec = SPECS[kind]
    hl, hw = spec.L * 0.5, spec.W * 0.5
    head = tail = siren = None
    if spec.bike:
        from . import bikes
        head, tail, siren = bikes.light_points(kind)
        return head, tail, siren or [(0.0, 0.0, spec.H)]
    if info is not None:
        head = info.get('head') or None
        tail = info.get('tail') or None
        siren = info.get('siren') or None
    if not head:
        z = spec.belt - spec.nose_drop - 0.18
        head = [(-hw * 0.75, hl, z), (hw * 0.75, hl, z)]
    if not tail:
        zt = spec.belt - spec.tail_drop - 0.17
        tail = [(-hw * 0.72, -hl, zt), (hw * 0.72, -hl, zt)]
    if not siren:
        y_wsb = spec.L * 0.5 - spec.hood
        y_wst = y_wsb - spec.ws_rake
        y_rwt = -spec.L * 0.5 + spec.trunk + spec.rw_rake
        ym = (y_wst + y_rwt) * 0.5 if 'police' in spec.extras else y_wst - 0.3
        siren = [(0.0, ym, spec.H)]
    return head, tail, siren


def lights_template(assets, kind, info=None):
    """Ночные огни: фары, луч на асфальте, габариты."""
    key = ('lights', kind)
    np_ = _extra_cache.get(key)
    if np_ is None:
        spec = SPECS[kind]
        mb = MeshBuilder()
        hl = spec.L * 0.5
        head, tail, _ = _light_points(kind, info)
        G = ('glow', 'add')
        for (x, y, z) in head:
            y = max(y, hl - 0.12) + 0.05
            s = 0.55
            mb.quad(G, (x - s, y, z - s), (x + s, y, z - s), (x + s, y, z + s), (x - s, y, z + s),
                    color=(1.0, 0.95, 0.8, 1.0))
            mb.quad(G, (x, y - s, z - s), (x, y + s, z - s), (x, y + s, z + s), (x, y - s, z + s),
                    color=(1.0, 0.95, 0.8, 0.8))
        for (x, y, z) in tail:
            y = min(y, -hl + 0.12) - 0.05
            s = 0.34
            mb.quad(G, (x + s, y, z - s), (x - s, y, z - s), (x - s, y, z + s), (x + s, y, z + s),
                    color=(1.0, 0.1, 0.05, 0.9))
        bw = 4.2
        mb.quad(('beam', 'add_c'), (-bw, hl - 0.5, 0.06), (bw, hl - 0.5, 0.06), (bw, hl + 15.0, 0.06),
                (-bw, hl + 15.0, 0.06), (0, 0, 1, 1), (1.0, 0.95, 0.8, 0.5))
        np_ = mb.build('lights', assets.apply_state)
        _extra_cache[key] = np_
    return np_


def brake_template(assets, kind, info=None):
    key = ('brake', kind)
    np_ = _extra_cache.get(key)
    if np_ is None:
        spec = SPECS[kind]
        mb = MeshBuilder()
        hl = spec.L * 0.5
        _, tail, _ = _light_points(kind, info)
        for (x, y, z) in tail:
            y = min(y, -hl + 0.12)
            s = 0.5
            mb.quad(('glow', 'add'), (x + s, y - 0.06, z - s), (x - s, y - 0.06, z - s),
                    (x - s, y - 0.06, z + s), (x + s, y - 0.06, z + s), color=(1.0, 0.1, 0.05, 1.0))
            if info is None:
                mb.quad(None, (x + 0.2, y - 0.02, z - 0.08), (x - 0.2, y - 0.02, z - 0.08),
                        (x - 0.2, y - 0.02, z + 0.08), (x + 0.2, y - 0.02, z + 0.08), color=(1.0, 0.25, 0.2, 1))
        np_ = mb.build('brake', assets.apply_state)
        np_.setLightOff(1)
        _extra_cache[key] = np_
    return np_


def siren_template(assets, kind, which, info=None):
    key = ('siren', kind, which)
    np_ = _extra_cache.get(key)
    if np_ is None:
        spec = SPECS[kind]
        mb = MeshBuilder()
        hw = spec.W * 0.5
        _, _, siren = _light_points(kind, info)
        if len(siren) >= 2:                         # у модели свои маячки (патрульный мотоцикл): светят они
            x, ym, z = siren[which]
            z += 0.05
        else:
            ym = siren[0][1]
            z = siren[0][2] + 0.12
            x = -hw * 0.33 if which == 0 else hw * 0.33
        col = (1.0, 0.1, 0.05, 1.0) if which == 0 else (0.1, 0.25, 1.0, 1.0)
        s = 1.5
        G = ('glow', 'add')
        mb.quad(G, (x - s, ym, z - s), (x + s, ym, z - s), (x + s, ym, z + s), (x - s, ym, z + s), color=col)
        mb.quad(G, (x, ym - s, z - s), (x, ym + s, z - s), (x, ym + s, z + s), (x, ym - s, z + s), color=col)
        mb.quad(G, (x - s, ym - s, z), (x + s, ym - s, z), (x + s, ym + s, z), (x - s, ym + s, z), color=col)
        np_ = mb.build('siren', assets.apply_state)
        _extra_cache[key] = np_
    return np_


def shadow_template(assets):
    np_ = _extra_cache.get('shadow')
    if np_ is None:
        mb = MeshBuilder()
        mb.quad(('shadow', 'decal_c'), (-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0))
        np_ = mb.build('shadow', assets.apply_state)
        np_.setLightOff(1)
        _extra_cache['shadow'] = np_
    return np_


# ---------------------------------------------------------------------------
class Vehicle(object):
    PARKED, RAIL, PHYS = 0, 1, 2

    def __init__(self, world, kind, x, y, yaw, paint=None):
        self.world = world
        self.kind = kind
        self.spec = spec = SPECS[kind]
        self.x, self.y, self.yaw = x, y, yaw
        self.z = world.city.ground_z(x, y)
        self.vx = self.vy = 0.0
        self.omega = 0.0
        self.speed = 0.0                 # продольная скорость (м/с, со знаком)
        self.slip = 0.0                  # боковая скорость
        self.steer = 0.0
        self.in_throttle = 0.0
        self.in_steer = 0.0
        self.in_brake = 0.0
        self.in_handbrake = False
        self.mode = Vehicle.PARKED
        self.health = spec.health
        self.max_health = spec.health
        self.dead = False
        self.burning = 0.0
        self.fallen = 0.0                 # сломанный велосипед лежит на боку: -1 или 1
        self.sunk = False
        self.driver = None               # Ped
        self.passengers = []
        self.is_player = False
        self.ai = None                   # объект с методом drive(vehicle, dt)
        self.link = None
        self.s = 0.0
        self.target_speed = 0.0
        self.rush = False                # на «рельсах»: спешит и не ждёт на светофорах (беглец)
        self.scripted = False            # положение и скорость задаёт сценка (режим PARKED)
        self.persona = 1.0
        self.wait_t = 0.0
        self.creep_t = 0.0
        self.honk_cd = 0.0
        self.siren = False
        self.removed = False
        self.keep = False                # не удалять автоматически (миссии, машина игрока)
        self.garage = False              # стоит в гараже игрока: сохраняется вместе с игрой
        self.tune = {}                   # тюнинг: категория -> уровень или вариант (см. tuning.py)
        self.k_acc = self.k_top = self.k_brake = self.k_grip = 1.0      # множители ходовых качеств от тюнинга
        self.ride = 0.0                  # высота посадки относительно заводской, м
        self.nitro = False               # стоит баллон закиси азота
        self.nitro_k = 0.0               # сколько в нём осталось (0..1)
        self.boost = False               # нитро сейчас включено
        self.horn = None                 # свой сигнал (иначе — по типу машины)
        self.snd_pitch = 1.0             # выхлоп: тон и громкость мотора
        self.snd_gain = 1.0
        self.light_tint = None
        self.tune_np = None
        self.neon_np = None
        self.mission = None
        self.spot = None                 # индекс парковочного места
        self.stolen = False
        self.alarm = 0.0
        self.locked = False
        self.owner = None                # 'police', 'gang', ...
        self.last_hit_by_player = -999.0
        self.radius = spec.bound
        self.cr = spec.cr
        self.circles = spec.circles
        self.roll = 0.0
        self.pitch = 0.0
        self.slope_p = 0.0            # наклон по рельефу: тангаж и крен, градусы
        self.slope_r = 0.0
        self.wheel_rot = 0.0
        self.smoke_t = 0.0
        self.skid_t = 0.0
        self.stuck_t = 0.0
        self.reverse_t = 0.0
        self.age = 0.0
        self.blip = None
        self.lights_on = False
        self.brake_on = False
        self.recover_t = 0.0
        self.immune = False
        self.col_cd = 0.0
        self.npc = False                 # за рулём «виртуальный» водитель (обычный трафик)
        self.traffic = False             # машина создана менеджером трафика
        self.next_link = None
        self.ghost = None
        self.ghost_t = 0.0
        self._route_link = None
        self.crew = 0
        self.gap = 99.0
        self.ai_t = random.random() * 0.2
        self.panic_t = 0.0
        self.block_t = 0.0
        self.unseen_t = 0.0
        self.radio = random.randrange(5)         # станция, на которую настроено радио (см. audio.STATIONS)
        self.driver_look = None
        self.hits = 0
        self.burn_t = 0.0
        self.paint = paint if paint is not None else random.randrange(len(spec.paints or PAINTS))
        self._build()
        if spec.kit or spec.tune:
            # заводской обвес и заводской тюнинг (у «Дрифта» ещё и неон случайного цвета)
            t = dict(spec.tune or {})
            if 'neon' in t and not t['neon']:
                t['neon'] = random.randint(1, 5)
            self.apply_tune(t)

    # ------------------------------------------------------------------
    def _paint_rgb(self):
        pal = self.spec.paints or PAINTS
        return pal[self.paint % len(pal)]

    def _paint_idx(self):
        pal = self.spec.paints or PAINTS
        return self.paint % len(pal)

    def _new_body(self, wreck=False):
        """Кузов: готовая модель, перекрашенная в цвет машины; если её нет — собранный из плоскостей."""
        w = self.world
        if self.spec.bike:
            from . import bikes
            parts = bikes.build(w.assets, self.kind, (0.16, 0.14, 0.13) if wreck else self._paint_rgb())
            self.bparts = parts
            np_ = parts['body'].copyTo(self.tilt)
            if wreck:
                np_.setColorScale(0.35, 0.33, 0.32, 1.0)
            return np_
        mdl = getattr(w, 'models', None)
        if self.minfo is not None:
            t = mdl.vehicle_body(self.kind, self.spec, self._paint_rgb(), wreck, self._paint_idx())
            if t is not None:
                return t.copyTo(self.tilt)
        return body_template(w.assets, self.kind, 0 if wreck else self.paint, wreck=wreck).copyTo(self.tilt)

    def _build(self):
        w = self.world
        spec = self.spec
        self.node = w.dyn_root.attachNewNode('veh')
        self.tilt = self.node.attachNewNode('tilt')
        mdl = getattr(w, 'models', None)
        self.minfo = mdl.vehicle_info(self.kind, spec) if (mdl is not None and mdl.ok) else None
        self.bparts = None
        self.fork = None
        self.steer_np = None
        self.steer_wheels = []
        self.rider = None                # (узел, облик) нарисованного ездока у мотоцикла в потоке машин
        self._arms = None                # фигура, чьи руки лежат на руле (ездок за рулём)
        self._arms_deg = 0.0
        self._steer_ax = None            # ось поворота руля (вдоль вилки) и точка на ней; None — вертикальная
        self._steer_deg = 0.0
        self.body = self._new_body()
        self.wheels = []
        self.wheel_r_vis = spec.wheel_r
        made = False
        if spec.bike:
            # вилка с передним колесом поворачивается вокруг своей оси; у квадроцикла поворачиваются сами колёса
            bp = self.bparts
            stx, sty = bp['steer']
            self.steer_np = self.tilt.attachNewNode('steer')
            self.steer_np.setPos(stx, sty, 0.0)
            self.fork = bp['fork'].copyTo(self.steer_np)
            self.steer_wheels = []
            top = bp.get('axis')
            if top is not None:
                # руль и вилка поворачиваются вокруг оси вилки (она наклонена назад), а не вокруг вертикали
                # через ось колеса: иначе руль, стоящий далеко позади колеса, ходит из стороны в сторону
                r0 = bp['wheels'][0][2]
                ax = LVector3(0.0, top[0] - sty, top[1] - r0)
                if ax.z > 0.15 and ax.normalize():
                    self._steer_ax = (ax, LPoint3(stx, sty, r0), LPoint3(stx, sty, 0.0))
            for (wx, wy, r, how, wnode) in bp['wheels']:
                if how == 'fork':                           # колесо в вилке: поворачивается вместе с ней
                    piv = self.steer_np.attachNewNode('wp')
                    piv.setPos(wx - stx, wy - sty, r)
                else:
                    piv = self.tilt.attachNewNode('wp')
                    piv.setPos(wx, wy, r)
                    if how == 'self':                       # колесо на рычагах: поворачивается само
                        self.steer_wheels.append(piv)
                self.wheels.append((piv, wnode.copyTo(piv)))
            made = True
        if self.minfo is not None and len(self.minfo['wheels']) == 4 and not made:
            # колёса модели: переднее левое, переднее правое, заднее левое, заднее правое
            tr = mdl.vehicle_wheel(self.kind, spec, False)
            tl = mdl.vehicle_wheel(self.kind, spec, True)
            if tr is not None and tl is not None:
                for (wx, wy, r, left) in self.minfo['wheels']:
                    piv = self.tilt.attachNewNode('wp')
                    piv.setPos(wx, wy, r)
                    wn = (tl if left else tr).copyTo(piv)
                    self.wheels.append((piv, wn))
                self.wheel_r_vis = self.minfo['wheel_r']
                self._texture_wheels()
                made = True
        if not made:
            wt = wheel_template(w.assets, self.kind)
            hw = spec.W * 0.5 - spec.wheel_w * 0.5 + 0.03
            for (wx, wy) in ((-hw, spec.front_axle), (hw, spec.front_axle), (-hw, spec.rear_axle),
                             (hw, spec.rear_axle)):
                piv = self.tilt.attachNewNode('wp')
                piv.setPos(wx, wy, spec.wheel_r)
                wn = wt.copyTo(piv)
                self.wheels.append((piv, wn))
        sh = shadow_template(w.assets).copyTo(self.node)
        sh.setScale(spec.W * 0.72, spec.L * 0.62, 1.0)
        sh.setZ(0.04)
        self.shadow = sh
        self.lights = None
        self.brake_np = None
        self.siren_np = None
        self.sync()

    def _texture_wheels(self):
        """Колёса модели нарисованы на той же текстуре, что и кузов (у старинных машин они ещё и в цвет)."""
        tex = self.world.models.vehicle_texture(self.kind, self.spec, self._paint_rgb(), self._paint_idx())
        if tex is not None:
            for piv, wn in self.wheels:
                wn.setTexture(tex, 1)

    def set_paint(self, idx):
        self.paint = idx
        self.body.removeNode()
        self.body = self._new_body()
        if self.spec.bike:
            self.fork.removeNode()
            self.fork = self.bparts['fork'].copyTo(self.steer_np)
        elif self.minfo is not None and len(self.minfo['wheels']) == 4:
            self._texture_wheels()
        if self.tune:
            from . import tuning
            tuning.apply(self)                       # детали в цвет кузова красятся заново

    # ------------------------------------------------------------------
    # ездок верхом (мотоциклы, велосипед, квадроцикл)
    # ------------------------------------------------------------------
    def _pose_rider(self, vis, node, seat, pose, bars=False):
        """Усадить фигуру: поза из смеси клипов, наклон корпуса, таз — точно в точку seat (оси машины).
        bars — это ездок за рулём: его руки ложатся на ручки."""
        from . import bikes
        P = bikes.POSES[pose]
        mix = P.get('clips') or (('ride', P['mix']), ('drive', 1.0 - P['mix']))
        vis.pose_mix(mix)
        node.reparentTo(self.tilt)
        node.setPosHpr(0.0, 0.0, 0.0, 0.0, -P['lean'], 0.0)
        pv = vis.pelvis_pos(self.tilt)
        if pv is None:
            node.setPos(seat[0], seat[1], seat[2] - 0.92)
        else:
            node.setPos(seat[0] - pv.x, seat[1] - pv.y, seat[2] - pv.z)
        if bars and pv is not None and self.bparts.get('grips') is not None:
            self._arms = vis
            self._arms_mix = mix
            self._reach()

    def _reach(self):
        """Подвести руки ездока к ручкам руля там, где они сейчас (руль поворачивается вместе с вилкой).
        Корпус идёт за рулём: плечи разворачиваются в сторону поворота, ездок подаётся вперёд."""
        gx, gy, gz = self.bparts['grips']
        sty = self.bparts['steer'][1]
        deg = self._steer_deg
        self._arms_deg = deg
        self._arms.ride_arms(self.steer_np, LPoint3(-gx, gy - sty, gz), LPoint3(gx, gy - sty, gz), self._arms_mix,
                             deg * 0.3, min(8.0, abs(deg) * 0.33))

    def _let_go(self, vis):
        if vis is not None and self._arms is vis:
            self._arms = None
            vis.ride_arms_off()

    def _turn_fork(self, deg):
        self._steer_deg = deg
        ax = self._steer_ax
        if ax is None:
            self.steer_np.setH(deg)
            return
        q = LQuaternion()
        q.setFromAxisAngle(deg, ax[0])
        self.steer_np.setQuat(q)
        self.steer_np.setPos(ax[1] + q.xform(ax[2] - ax[1]))

    def seat_ped(self, ped, passenger=False):
        """Посадить персонажа в седло (или на место пассажира): он виден и едет вместе с машиной."""
        bp = self.bparts
        if passenger:
            s2 = bp.get('seat2')
            if s2 is None:
                return False
            seat, pose = s2[:3], s2[3]
        else:
            seat, pose = bp['seat'], bp['pose']
        if getattr(ped, '_ride_parent', None) is None:
            ped._ride_parent = ped.node.getParent()
        vis = ped.vis
        if vis is None:
            ped.node.reparentTo(self.tilt)
            ped.node.setPosHpr(seat[0], seat[1], seat[2] - 0.92, 0.0, 0.0, 0.0)
        else:
            self._pose_rider(vis, ped.node, seat, pose, bars=not passenger)
        ped.node.show()
        return True

    def unseat_ped(self, ped):
        par = getattr(ped, '_ride_parent', None)
        ped._ride_parent = None
        self._let_go(ped.vis)
        if ped.removed or ped.node.isEmpty():
            return                                  # фигуру уже убрали: возвращать некого
        if par is not None and not par.isEmpty():
            ped.node.reparentTo(par)
            ped.node.setHpr(0, 0, 0)
        if ped.vis is not None:
            ped.vis.play('idle', True, 1.0, 0.0, True)

    def hit_top(self):
        """Верх того, во что может попасть пуля: у мотоцикла с ездоком это голова ездока, а не руль."""
        spec = self.spec
        top = max(spec.H, spec.box[1]) if spec.box else spec.H
        if spec.bike and not self.dead and (self.rider is not None or self.driver is not None):
            top = max(top, self.bparts['seat'][2] + 0.82)
        return top

    def rider_hit(self, hz):
        """В кого попала пуля на высоте hz: None — в сам мотоцикл, 'npc' — в ездока из потока машин,
        иначе — персонаж за рулём (игрок или участник задания).  Ездок сидит на виду и ничем не прикрыт."""
        if not self.spec.bike or self.dead:
            return None
        who = 'npc' if (self.rider is not None and self.npc) else self.driver
        if who is None:
            return None
        rel = hz - self.z
        if rel > self.spec.H:
            return who                              # выше мотоцикла — только человек
        if rel > self.bparts['seat'][2] - 0.15 and random.random() < 0.5:
            return who
        return None

    def add_rider(self, look):
        """Нарисовать ездока на мотоцикле из потока машин (настоящим персонажем он станет, если его сбросят)."""
        from .pedvisual import PedVisual
        mdl = getattr(self.world, 'models', None)
        if mdl is None or not mdl.chars_ok or self.rider is not None:
            return
        bp = self.bparts
        vis = PedVisual(mdl, self.tilt, look, 'cop' if self.kind == 'copbike' else 'civ')
        self._pose_rider(vis, vis.root, bp['seat'], bp['pose'], bars=True)
        self.rider = vis
        self.driver_look = look

    def remove_rider(self):
        vis = self.rider
        if vis is not None:
            self.rider = None
            if self._arms is vis:
                self._arms = None
            vis.remove()
            vis.root.removeNode()

    def apply_tune(self, tune=None):
        """Поставить тюнинг (словарь «деталь -> вариант»; None — применить заново то, что уже стоит)."""
        from . import tuning
        tuning.apply(self, tune)

    def _ensure_lights(self):
        if self.lights is None:
            self.lights = lights_template(self.world.assets, self.kind, self.minfo).copyTo(self.tilt)
            self.lights.hide()
            if self.light_tint is not None:
                self.lights.setColorScale(self.light_tint[0], self.light_tint[1], self.light_tint[2], 1.0)
        return self.lights

    def set_lights(self, on):
        if on == self.lights_on:
            return
        self.lights_on = on
        l = self._ensure_lights()
        if on:
            l.show()
        else:
            l.hide()

    def set_brake_light(self, on):
        if on == self.brake_on:
            return
        self.brake_on = on
        if self.brake_np is None:
            self.brake_np = brake_template(self.world.assets, self.kind, self.minfo).copyTo(self.tilt)
        if on:
            self.brake_np.show()
        else:
            self.brake_np.hide()

    def update_siren(self, t):
        if not self.siren or self.dead:
            if self.siren_np is not None:
                self.siren_np[0].hide()
                self.siren_np[1].hide()
            return
        if self.siren_np is None:
            a = siren_template(self.world.assets, self.kind, 0, self.minfo).copyTo(self.tilt)
            b = siren_template(self.world.assets, self.kind, 1, self.minfo).copyTo(self.tilt)
            self.siren_np = (a, b)
        ph = int(t * 5.0) % 2
        if ph == 0:
            self.siren_np[0].show()
            self.siren_np[1].hide()
        else:
            self.siren_np[0].hide()
            self.siren_np[1].show()

    def sync(self):
        self.node.setPosHpr(self.x, self.y, self.z, yaw_to_h(self.yaw), 0, 0)

    def remove(self):
        if self.removed:
            return
        self.removed = True
        self._free_riders()
        self.node.removeNode()

    def _free_riders(self):
        """Перед тем как убрать или сжечь машину: седок верхом не должен исчезнуть вместе с её узлом."""
        self.remove_rider()
        for d in [self.driver] + list(self.passengers):
            if d is not None and getattr(d, '_ride_parent', None) is not None:
                self.unseat_ped(d)

    # ------------------------------------------------------------------
    def forward(self):
        return math.cos(self.yaw), math.sin(self.yaw)

    def door_pos(self, side=-1):
        """Точка у двери (side=-1 — водительская, слева)."""
        fx, fy = math.cos(self.yaw), math.sin(self.yaw)
        rx, ry = fy, -fx
        d = self.spec.W * 0.5 + 0.55
        o = 0.15
        return self.x + fx * o + rx * d * side, self.y + fy * o + ry * d * side

    def circle_pos(self, i):
        fx, fy = math.cos(self.yaw), math.sin(self.yaw)
        o = self.circles[i]
        return self.x + fx * o, self.y + fy * o

    def set_mode(self, mode):
        if mode == self.mode:
            return
        if mode == Vehicle.PHYS and self.mode == Vehicle.RAIL:
            fx, fy = math.cos(self.yaw), math.sin(self.yaw)
            self.vx, self.vy = fx * self.speed, fy * self.speed
        self.mode = mode

    def occupied(self):
        return self.driver is not None or self.npc

    # ------------------------------------------------------------------
    def update(self, dt):
        if self.removed:
            return
        self.age += dt
        if self.col_cd > 0:
            self.col_cd -= dt
        if self.sunk:
            self.z -= dt * 1.2
            self.node.setZ(self.z)
            self.tilt.setP(self.tilt.getP() + dt * 8.0)
            return
        if self.mode == Vehicle.RAIL:
            self._update_rail(dt)
        elif self.mode == Vehicle.PHYS:
            if self.ai is not None and not self.dead:
                self.ai.drive(self, dt)
            n = 2 if dt > 0.022 else 1
            h = dt / n
            for _ in range(n):
                self._update_phys(h)
        elif not self.scripted:
            self.speed = 0.0
            self.vx = self.vy = 0.0
        self._update_damage(dt)
        self._update_visual(dt)

    def _update_rail(self, dt):
        v = self.speed
        tv = self.target_speed
        if tv > v:
            v = min(tv, v + (5.2 if self.rush else 3.2) * dt)
        else:
            v = max(tv, v - 9.0 * dt)
        self.speed = v
        self.s += v * dt
        link = self.link
        guard = 0
        while self.s >= link.length and guard < 4:
            guard += 1
            self.s -= link.length
            nxt = link.next
            if not nxt:
                self.s = link.length
                self.speed = 0.0
                break
            nl = self.next_link
            if nl is None or nl not in nxt:
                nl = nxt[int(random.random() * len(nxt))] if len(nxt) > 1 else nxt[0]
            self.next_link = None
            link = nl
            self.link = link
        x, y, yaw = link.pos(self.s)
        self.x, self.y = x, y
        old = self.yaw
        self.yaw = yaw
        d = angle_diff(yaw, old)
        self.steer = clamp(d / max(dt, 1e-3) * 0.25, -0.5, 0.5) if v > 0.5 else 0.0
        self.vx = math.cos(yaw) * v
        self.vy = math.sin(yaw) * v
        self.slip = 0.0
        # обычная улица лежит на нуле; на мосту полоса поднимается вместе с полотном
        self.z = 0.0 if link.flat else self.world.city.ground_z(x, y)

    def _update_phys(self, dt):
        spec = self.spec
        fx, fy = math.cos(self.yaw), math.sin(self.yaw)
        vf = self.vx * fx + self.vy * fy
        thr = self.in_throttle
        brk = self.in_brake
        if self.dead:
            thr = 0.0
            brk = 0.3
        elif self.driver is None and not self.npc:
            thr = 0.0
            brk = max(brk, 0.4)             # пустая машина стоит на «ручнике»
        hp_k = 1.0 if self.health > 300 else (0.55 + 0.45 * max(0.0, self.health) / 300.0)
        # тюнинг и нитро: свои разгон, предельная скорость, тормоза
        top = spec.top * self.k_top
        accel = spec.accel * self.k_acc
        brake = spec.brake * self.k_brake
        if self.nitro:
            if self.boost and self.nitro_k > 0.0 and thr > 0.0:
                self.nitro_k = max(0.0, self.nitro_k - dt / 3.2)
                accel *= 1.7
                top *= 1.16
            else:
                self.boost = False
                self.nitro_k = min(1.0, self.nitro_k + dt / 14.0)
        acc = 0.0
        if thr > 0.0:
            if vf >= -0.8:
                k = 1.0 - (vf / (top * hp_k)) ** 2 if vf > 0 else 1.0
                acc = accel * thr * max(0.0, k) * hp_k
                if vf < 8.0:
                    acc *= 1.25
            else:
                acc = brake * thr
        elif thr < 0.0:
            if vf > 0.8:
                acc = brake * thr
            else:
                rev_top = spec.top * 0.32
                k = 1.0 - (vf / -rev_top) ** 2 if vf < 0 else 1.0
                acc = spec.accel * 0.8 * thr * max(0.0, k)
        vf0 = vf
        vf += acc * dt
        if brk > 0.0:
            vf = approach(vf, 0.0, brake * brk * dt)
        # сопротивление
        vf -= vf * 0.045 * dt
        if thr == 0.0:
            vf = approach(vf, 0.0, 1.4 * dt)
        self.vx += (vf - vf0) * fx
        self.vy += (vf - vf0) * fy
        # руление
        sp = abs(vf)
        max_st = spec.steer / (1.0 + (sp / 17.0) ** 1.6)
        target = self.in_steer * max_st
        rate = 2.6 if abs(target) > abs(self.steer) else 4.5
        self.steer = approach(self.steer, target, rate * dt)
        yaw_rate = vf * math.tan(self.steer) / spec.wheelbase
        # ограничение по сцеплению
        lim = (spec.grip * self.k_grip * 1.35) / max(sp, 4.0)
        if self.in_handbrake:
            lim *= 1.6
        yaw_rate = clamp(yaw_rate, -lim, lim)
        self.yaw = wrap_angle(self.yaw + (yaw_rate + self.omega) * dt)
        self.omega *= math.exp(-3.5 * dt)
        if abs(self.omega) < 0.01:
            self.omega = 0.0
        # раскладываем скорость по новым осям: боковая составляющая гасится сцеплением
        nfx, nfy = math.cos(self.yaw), math.sin(self.yaw)
        rx, ry = nfy, -nfx
        vf2 = self.vx * nfx + self.vy * nfy
        vr = self.vx * rx + self.vy * ry
        grip = spec.grip * self.k_grip
        if self.in_handbrake:
            grip *= 0.22
            vf2 = approach(vf2, 0.0, spec.brake * 0.5 * dt)
        elif abs(vr) > 5.0:
            grip *= 0.55
        vr *= math.exp(-grip * dt)
        self.vx = nfx * vf2 + rx * vr
        self.vy = nfy * vf2 + ry * vr
        self.speed = vf2
        self.slip = vr
        self.x += self.vx * dt
        self.y += self.vy * dt
        self._collide_static()
        w = self.world
        gz = w.city.ground_z(self.x, self.y)
        if gz < WATER_Z - 0.2 and w.city.in_water(self.x, self.y):
            self._sink()
            return
        self.z = damp(self.z, gz, 14.0, dt)

    def _collide_static(self):
        st = self.world.static
        fx, fy = math.cos(self.yaw), math.sin(self.yaw)
        r = self.cr
        hit_n = None
        best = 0.0
        hit_o = 0.0
        hit_ref = None
        for o in self.circles:
            cx = self.x + fx * o
            cy = self.y + fy * o
            nx_, ny_, nx, ny, depth, ref = st.push_circle(cx, cy, r, F_CAR)
            if depth > 0.0:
                # ломаемые объекты
                if ref is not None and ref[0] == 'break':
                    sp = math.hypot(self.vx, self.vy)
                    if sp > 2.5:
                        self.world.break_prop(ref[1], self)
                        self.vx *= 0.93
                        self.vy *= 0.93
                        continue
                self.x += nx_ - cx
                self.y += ny_ - cy
                if depth > best:
                    best = depth
                    hit_n = (nx, ny)
                    hit_o = o
                    hit_ref = ref
        if hit_n is not None:
            nx, ny = hit_n
            vn = self.vx * nx + self.vy * ny
            if vn < 0.0:
                e = 0.18
                self.vx -= (1.0 + e) * vn * nx
                self.vy -= (1.0 + e) * vn * ny
                # трение о стену
                self.vx *= 0.985
                self.vy *= 0.985
                imp = -vn
                # вращение от удара не по центру
                tq = (fx * hit_o) * ny - (fy * hit_o) * nx
                self.omega += clamp(-tq * imp * 0.05, -2.5, 2.5) * (1.0 if abs(hit_o) > 0.1 else 0.0)
                if imp > 2.0:
                    self.world.on_vehicle_impact(self, imp, self.x - nx * r, self.y - ny * r, None)

    def _sink(self):
        if self.sunk:
            return
        self.sunk = True
        self.dead = True
        self.world.on_vehicle_sunk(self)

    # ------------------------------------------------------------------
    def damage(self, amount, by_player=False, cause='hit'):
        if self.dead or self.immune:
            return
        self.health -= amount
        if by_player:
            self.last_hit_by_player = self.world.time
        if self.health <= 0.0:
            if self.spec.nofire:
                self.break_down(by_player)
            elif cause == 'explosion' and amount > self.max_health * 1.1:
                self.explode(by_player)                 # прямое попадание
            else:
                # загорается и скоро взорвётся (цепная реакция выглядит эффектнее с задержкой)
                self.health = 1.0
                if cause in ('explosion', 'fire'):
                    self.burn_t = max(self.burn_t, 4.5 - random.uniform(0.25, 1.0))

    def _update_damage(self, dt):
        if self.dead:
            if self.burning > 0:
                self.burning -= dt
                self.smoke_t -= dt
                if self.smoke_t <= 0:
                    self.smoke_t = 0.12
                    self.world.fx.fire(self.x, self.y, self.z + self.spec.belt, 1.2)
                    self.world.fx.smoke(self.x, self.y, self.z + self.spec.H, 1.6, dark=True)
            return
        hp = self.health
        if self.spec.nofire:
            if hp < self.max_health * 0.14:
                self.break_down(self.world.time - self.last_hit_by_player < 12.0)
            return
        if hp < self.max_health * 0.35:
            self.smoke_t -= dt
            if self.smoke_t <= 0:
                fx, fy = math.cos(self.yaw), math.sin(self.yaw)
                hx = self.x + fx * (self.spec.L * 0.5 - 0.6)
                hy = self.y + fy * (self.spec.L * 0.5 - 0.6)
                if hp < self.max_health * 0.14:
                    self.smoke_t = 0.07
                    self.world.fx.fire(hx, hy, self.z + self.spec.belt, 0.8)
                    self.world.fx.smoke(hx, hy, self.z + self.spec.belt + 0.4, 1.0, dark=True)
                else:
                    self.smoke_t = 0.16
                    self.world.fx.smoke(hx, hy, self.z + self.spec.belt, 0.8,
                                        dark=hp < self.max_health * 0.24)
        if hp < self.max_health * 0.14:
            # горит и скоро взорвётся
            self.health = max(0.5, self.health - self.max_health * 0.03 * dt)
            self.burn_t += dt
            if self.burn_t > 4.5:
                self.explode(self.world.time - self.last_hit_by_player < 12.0)

    def break_down(self, by_player=False):
        """Велосипед не горит и не взрывается: он ломается и падает набок, а ездок летит на асфальт."""
        if self.dead:
            return
        w = self.world
        vx, vy = self.vx, self.vy
        if self.is_player:
            w.player.thrown_off(self, 10.0)
        elif self.npc and self.rider is not None:
            w.unseat_rider(self)
        self.dead = True
        self.health = 0.0
        self.burning = 0.0
        self.fallen = random.choice((-1.0, 1.0))
        self.set_lights(False)
        self._free_riders()
        w.traffic.take_over(self)
        self.vx *= 0.3
        self.vy *= 0.3
        w.stats['wrecks'] += 1
        w.audio.play_at('crash1', self.x, self.y, 0.7, 1.3, 60.0)
        if w.missions is not None:
            w.missions.notify('vehicle_destroyed', self)

    def explode(self, by_player=False):
        if self.dead:
            return
        self.dead = True
        self.health = 0.0
        self.burning = 14.0
        self.siren = False
        self.set_lights(False)
        self.set_brake_light(False)
        self.body.removeNode()
        self.body = self._new_body(wreck=True)
        self._free_riders()
        for piv, wn in self.wheels:
            piv.setColorScale(0.16, 0.15, 0.14, 1.0)         # обгоревшие колёса
        self.set_mode(Vehicle.PHYS)
        self.ai = None
        self.vx *= 0.3
        self.vy *= 0.3
        self.omega += random.uniform(-2, 2)
        self.world.on_vehicle_exploded(self, by_player)

    # ------------------------------------------------------------------
    def _update_visual(self, dt):
        spec = self.spec
        # наклон по земле: въезд на мост, холмы, бордюры (вблизи камеры; вдали его не разглядеть)
        w = self.world
        cam = w.cam
        if self.is_player or (abs(self.x - cam.x) < 130.0 and abs(self.y - cam.y) < 130.0):
            gz = w.city.ground_z
            fx, fy = math.cos(self.yaw), math.sin(self.yaw)
            hl, hw = spec.L * 0.36, spec.W * 0.40
            zf = gz(self.x + fx * hl, self.y + fy * hl)
            zr = gz(self.x - fx * hl, self.y - fy * hl)
            zl = gz(self.x - fy * hw, self.y + fx * hw)
            zrt = gz(self.x + fy * hw, self.y - fx * hw)
            sp = clamp(math.atan2(zf - zr, 2.0 * hl) * DEG, -24.0, 24.0)
            sr = clamp(math.atan2(zl - zrt, 2.0 * hw) * DEG, -20.0, 20.0)
            self.slope_p = damp(self.slope_p, sp, 12.0, dt)
            self.slope_r = damp(self.slope_r, sr, 12.0, dt)
        self.node.setPosHpr(self.x, self.y, self.z, yaw_to_h(self.yaw), self.slope_p, self.slope_r)
        v = self.speed
        self.wheel_rot = (self.wheel_rot - v * dt / self.wheel_r_vis * DEG) % 360.0
        st = self.steer * DEG
        ws = self.wheels
        rot = self.wheel_rot
        if spec.bike:
            if self.steer_wheels:
                deg = st * 0.6
                for piv in self.steer_wheels:
                    piv.setH(st)
            else:
                deg = st
            if deg != self._steer_deg:
                self._turn_fork(deg)
                if self._arms is not None and abs(deg - self._arms_deg) > 0.7 and (
                        self.is_player or (abs(self.x - cam.x) < 70.0 and abs(self.y - cam.y) < 70.0)):
                    self._reach()                           # руки идут за рулём
            for piv, wn in ws:
                wn.setP(rot)
            if self.fallen:
                self.roll = damp(self.roll, 84.0 * self.fallen, 8.0, dt)
                self.tilt.setHpr(0, 0, self.roll)
                return
            if spec.lean:
                # мотоцикл ложится в поворот тем сильнее, чем быстрее едет
                lean = clamp(v * math.tan(self.steer) * 2.6, -34.0, 34.0) if self.mode == Vehicle.PHYS else 0.0
                self.roll = damp(self.roll, lean, 7.0, dt)
                pt = clamp((self.in_brake * 2.0 - self.in_throttle * 2.5) * (1.0 if abs(v) > 1 else 0.0), -4.0, 3.0)
                self.pitch = damp(self.pitch, pt if self.mode == Vehicle.PHYS else 0.0, 5.0, dt)
                self.tilt.setHpr(0, self.pitch, self.roll)
                return
        else:
            ws[0][0].setH(st)
            ws[1][0].setH(st)
            for i in range(4):
                ws[i][1].setP(rot)
        if self.mode == Vehicle.PHYS:
            # крен в поворотах и «клевок» при торможении
            lat = clamp(-self.slip * 0.9 - v * math.tan(self.steer) * 0.35, -7.0, 7.0)
            self.roll = damp(self.roll, lat, 6.0, dt)
            pt = clamp((self.in_brake * 2.0 - self.in_throttle * 1.2) * (1.0 if abs(v) > 1 else 0.0), -2.5, 2.5)
            self.pitch = damp(self.pitch, pt, 5.0, dt)
            self.tilt.setHpr(0, self.pitch, self.roll)
        elif self.roll != 0.0 or self.pitch != 0.0:
            self.roll = self.pitch = 0.0
            self.tilt.setHpr(0, 0, 0)
