# -*- coding: utf-8 -*-
"""Общие определения: оружие, внешность персонажей."""
import random

# ---------------------------------------------------------------------------
# оружие
# ---------------------------------------------------------------------------
W_FIST, W_BAT, W_PISTOL, W_UZI, W_SHOTGUN, W_AK, W_ROCKET, W_GRENADE, W_MOLOTOV = range(9)


class WeaponDef(object):
    def __init__(self, wid, name, icon, kind, damage, rate, rng, spread=0.0, auto=False, pellets=1,
                 sound=None, long=False, price=0, pack=0, car_k=1.5):
        self.id = wid
        self.name = name
        self.icon = icon
        self.kind = kind            # 'melee' | 'gun' | 'rocket' | 'thrown'
        self.damage = damage
        self.rate = rate            # секунд между выстрелами
        self.range = rng
        self.spread = spread
        self.auto = auto
        self.pellets = pellets
        self.sound = sound
        self.long = long            # длинный ствол (модель в руке)
        self.price = price          # цена в магазине
        self.pack = pack            # патронов в пачке / в подбираемом оружии
        self.car_k = car_k          # множитель урона по технике


WEAPONS = [
    WeaponDef(W_FIST, 'Кулаки', 'w_fist', 'melee', 12, 0.42, 1.35, sound='punch'),
    WeaponDef(W_BAT, 'Бита', 'w_bat', 'melee', 30, 0.55, 1.75, sound='punch', long=True, price=80, pack=1),
    WeaponDef(W_PISTOL, 'Пистолет', 'w_pistol', 'gun', 25, 0.30, 60.0, 0.012, sound='pistol', price=250,
              pack=34),
    WeaponDef(W_UZI, 'Узи', 'w_uzi', 'gun', 15, 0.085, 55.0, 0.034, auto=True, sound='uzi', price=800, pack=90),
    WeaponDef(W_SHOTGUN, 'Дробовик', 'w_shotgun', 'gun', 13, 0.95, 32.0, 0.075, pellets=9, sound='shotgun',
              long=True, price=1200, pack=16),
    WeaponDef(W_AK, 'Автомат', 'w_ak', 'gun', 30, 0.11, 90.0, 0.018, auto=True, sound='ak', long=True,
              price=2500, pack=90),
    WeaponDef(W_ROCKET, 'Гранатомёт', 'w_rocket', 'rocket', 250, 1.5, 120.0, sound='rocket', long=True,
              price=6000, pack=5),
    WeaponDef(W_GRENADE, 'Гранаты', 'w_grenade', 'thrown', 220, 1.0, 30.0, sound='throw', price=1500, pack=6),
    WeaponDef(W_MOLOTOV, 'Коктейль Молотова', 'w_molotov', 'thrown', 60, 1.0, 26.0, sound='throw', price=900,
              pack=6),
]

# ---------------------------------------------------------------------------
# внешность
# ---------------------------------------------------------------------------
SKINS = [(0.96, 0.80, 0.68), (0.90, 0.72, 0.58), (0.78, 0.58, 0.42), (0.58, 0.40, 0.28), (0.40, 0.27, 0.20),
         (0.98, 0.84, 0.74)]
HAIRS = [(0.10, 0.08, 0.06), (0.26, 0.16, 0.08), (0.48, 0.32, 0.14), (0.78, 0.66, 0.34), (0.55, 0.55, 0.55),
         (0.50, 0.14, 0.08), (0.04, 0.04, 0.05)]
SHIRTS = [(0.82, 0.16, 0.14), (0.16, 0.32, 0.70), (0.92, 0.92, 0.90), (0.12, 0.12, 0.14), (0.20, 0.52, 0.28),
          (0.92, 0.76, 0.16), (0.54, 0.20, 0.56), (0.90, 0.48, 0.14), (0.46, 0.50, 0.56), (0.30, 0.62, 0.70),
          (0.86, 0.52, 0.62), (0.44, 0.30, 0.20)]
PANTS = [(0.16, 0.22, 0.42), (0.12, 0.12, 0.14), (0.42, 0.36, 0.26), (0.30, 0.32, 0.36), (0.20, 0.26, 0.20),
         (0.50, 0.50, 0.54), (0.24, 0.16, 0.12)]
SHOES = [(0.08, 0.08, 0.08), (0.90, 0.90, 0.90), (0.34, 0.22, 0.12)]


class Look(object):
    __slots__ = ('skin', 'hair', 'shirt', 'pants', 'shoes', 'torso', 'hat', 'hat_color', 'female', 'glasses',
                 'beard', 'bald', 'scale', 'fat')

    def __init__(self):
        self.skin = SKINS[0]
        self.hair = HAIRS[0]
        self.shirt = SHIRTS[0]
        self.pants = PANTS[0]
        self.shoes = SHOES[0]
        self.torso = 'tee'
        self.hat = None
        self.hat_color = (0.1, 0.1, 0.1)
        self.female = False
        self.glasses = False
        self.beard = False
        self.bald = False
        self.scale = 1.0
        self.fat = 1.0


def random_look(rnd=None, zone='D'):
    r = rnd or random
    lk = Look()
    lk.skin = r.choice(SKINS)
    lk.hair = r.choice(HAIRS)
    lk.shirt = r.choice(SHIRTS)
    lk.pants = r.choice(PANTS)
    lk.shoes = r.choice(SHOES)
    lk.female = r.random() < 0.45
    lk.scale = 0.94 + r.random() * 0.12
    lk.fat = 0.92 + r.random() * 0.3
    if lk.female:
        lk.scale *= 0.95
        lk.fat = 0.88 + r.random() * 0.2
    p = r.random()
    if zone == 'D':
        lk.torso = 'jacket' if p < 0.5 else ('tee' if p < 0.8 else 'stripes')
        if lk.torso == 'jacket':
            lk.shirt = r.choice([(0.14, 0.14, 0.18), (0.24, 0.26, 0.32), (0.20, 0.18, 0.30), (0.42, 0.40, 0.36)])
            lk.pants = lk.shirt if p < 0.35 else r.choice(PANTS)
    elif zone == 'G':
        lk.torso = 'hoodie' if p < 0.4 else ('tank' if p < 0.7 else 'tee')
    elif zone == 'I':
        lk.torso = 'vest' if p < 0.45 else ('tee' if p < 0.8 else 'hoodie')
        if lk.torso == 'vest':
            lk.shirt = r.choice([(0.95, 0.55, 0.08), (0.80, 0.90, 0.10)])
            lk.hat = 'helmet'
            lk.hat_color = r.choice([(0.95, 0.80, 0.10), (0.92, 0.92, 0.92), (0.9, 0.4, 0.1)])
    elif zone == 'B':
        lk.torso = 'tank' if p < 0.45 else ('tee' if p < 0.8 else 'stripes')
    else:
        lk.torso = r.choice(['tee', 'tee', 'stripes', 'hoodie', 'jacket'])
    if not lk.female:
        lk.beard = r.random() < 0.18
        lk.bald = r.random() < 0.1
    lk.glasses = r.random() < 0.12
    if lk.hat is None and r.random() < 0.16:
        lk.hat = 'cap'
        lk.hat_color = r.choice(SHIRTS)
    return lk


def make_look(**kw):
    lk = Look()
    for k, v in kw.items():
        setattr(lk, k, v)
    return lk


def cop_look(r=None):
    r = r or random
    return make_look(skin=r.choice(SKINS), hair=r.choice(HAIRS), shirt=(0.16, 0.22, 0.42), pants=(0.10, 0.12, 0.20),
                     torso='police', hat='police', hat_color=(0.10, 0.12, 0.22), beard=r.random() < 0.15)


def swat_look(r=None):
    r = r or random
    return make_look(skin=r.choice(SKINS), shirt=(0.08, 0.09, 0.12), pants=(0.08, 0.09, 0.12), torso='armor',
                     hat='helmet', hat_color=(0.07, 0.08, 0.10), glasses=True, fat=1.15)


def fbi_look(r=None):
    r = r or random
    return make_look(skin=r.choice(SKINS), hair=r.choice(HAIRS), shirt=(0.06, 0.06, 0.08), pants=(0.06, 0.06, 0.08),
                     torso='jacket', glasses=True)


def army_look(r=None):
    r = r or random
    return make_look(skin=r.choice(SKINS), shirt=(0.26, 0.31, 0.20), pants=(0.22, 0.27, 0.18), torso='armor',
                     hat='helmet', hat_color=(0.24, 0.29, 0.18), fat=1.1)


def medic_look(r=None):
    r = r or random
    return make_look(skin=r.choice(SKINS), hair=r.choice(HAIRS), shirt=(0.94, 0.94, 0.94), pants=(0.85, 0.2, 0.2),
                     torso='vest', female=r.random() < 0.5)


GANG_COLORS = {'reds': (0.75, 0.10, 0.10), 'greens': (0.10, 0.50, 0.18), 'purple': (0.42, 0.10, 0.48),
               'mafia': (0.10, 0.10, 0.12)}


def gang_look(gang='reds', r=None):
    r = r or random
    c = GANG_COLORS.get(gang, (0.5, 0.1, 0.1))
    if gang == 'mafia':
        return make_look(skin=r.choice(SKINS[:3]), hair=r.choice(HAIRS[:2] + HAIRS[6:]), shirt=c, pants=c,
                         torso='jacket', glasses=r.random() < 0.5, fat=1.0 + r.random() * 0.25)
    return make_look(skin=r.choice(SKINS), hair=r.choice(HAIRS), shirt=c, pants=r.choice(PANTS[:3]),
                     torso=r.choice(['hoodie', 'tank', 'tee']), hat=('cap' if r.random() < 0.6 else None),
                     hat_color=c, beard=r.random() < 0.3)


def player_look():
    return make_look(skin=SKINS[1], hair=(0.20, 0.13, 0.08), shirt=(0.40, 0.24, 0.13), pants=(0.22, 0.30, 0.50),
                     shoes=SHOES[1], torso='leather')
