# -*- coding: utf-8 -*-
"""Готовые модели: персонажи со скелетной анимацией, машины, оружие.

Файлы лежат в assets/models и получены скриптом tools/import_models.py из свободных
наборов Quaternius (CC0).  Здесь — только то, как игра их использует: какую модель
взять для машины или человека, как её перекрасить и какие клипы анимации проигрывать.
Чтобы подставить другие модели, достаточно положить свои .bam и поправить таблицы ниже.
"""
import json
import os

from panda3d.core import Filename, NodePath, LMatrix4, BoundingSphere, LPoint3

from .defs import (W_FIST, W_BAT, W_PISTOL, W_UZI, W_SHOTGUN, W_AK, W_ROCKET, W_GRENADE, W_MOLOTOV)

# ---------------------------------------------------------------------------
# машины: тип из vehicle.SPECS -> (файл модели, особенности)
#   trim   — цвет второй группы деталей: 'dark' (темнее кузова) или готовый цвет
#   siren  — оставить ли на крыше маячки
# ---------------------------------------------------------------------------
VEHICLE_MODELS = {
    'sedan': ('sedan', {}),
    'hatch': ('hatch', {}),
    'sports': ('coupe', {}),
    'muscle': ('muscle', {}),
    'suv': ('suv', {}),
    'pickup': ('pickup', {}),
    'van': ('box', {'trim': 'dark'}),
    'taxi': ('taxi', {}),
    'police': ('police', {'siren': True}),
    'ambulance': ('box', {'trim': (0.80, 0.10, 0.10), 'siren': True}),
    'bus': ('bus', {'trim': 'dark'}),
    'truck': ('truck', {}),
    'enforcer': ('box', {'trim': (0.86, 0.86, 0.90), 'siren': True}),
    'fbi': ('sport4', {}),
    'army': ('truck', {}),
    'beater': ('sedan', {}),
    'lowrider': ('sport4', {}),
}

WRECK = (0.13, 0.12, 0.11)

# ---------------------------------------------------------------------------
# персонажи.  Узлы модели называются «Часть|Материал»; здесь сказано, какой материал
# чем считать: кожей, волосами, верхом, низом, обувью, головным убором.  Остальное
# остаётся того цвета, каким его сделал автор модели.
# ---------------------------------------------------------------------------
COMMON_ROLES = {
    'Skin': 'skin', 'Skin_Darker': 'skin2', 'Hair': 'hair', 'Hair_Brown': 'hair', 'Hair_Blond': 'hair',
    'Hair_Black': 'hair', 'Eyebrows': 'hair2', 'Moustache': 'hair2',
}
CHAR_ROLES = {
    'm_casual': {'LightBrown': 'shirt', 'LightBlue': 'pants', 'Red_Dark': 'shoes'},
    'm_hoodie': {'Purple': 'shirt', 'LightBlue': 'pants', 'Feet|Purple': 'shoes'},
    'm_beach': {'LightBrown': 'shirt', 'Red_Dark': 'pants', 'Feet|Red_Dark': 'shoes'},
    'm_punk': {'Body|Black': 'shirt', 'LightBlue': 'pants', 'Feet|Black': 'shoes', 'Red': 'hair',
               'Red_Dark': 'hair2'},
    'm_suit': {'Suit': 'shirt', 'Legs|Suit': 'pants', 'Tie': 'shirt2', 'Feet|Black': 'shoes', 'White': 'collar'},
    'm_worker': {'Worker_Vest': 'shirt', 'Brown': 'pants', 'Brown2': 'pants2', 'Feet|Black': 'shoes',
                 'Head|Worker_Yellow': 'hat'},
    'm_farmer': {'Body|LightBlue': 'pants', 'Legs|LightBlue': 'pants', 'Body|Beige': 'shirt',
                 'Feet|Brown': 'shoes', 'Head|Beige': 'hat'},
    'm_jacket': {'Green': 'shirt', 'LightGreen': 'shirt3', 'Brown': 'pants', 'Brown2': 'pants2',
                 'Feet|Black': 'shoes'},
    'm_swat': {'Swat': 'shirt', 'Legs|Swat': 'pants', 'Head|Swat': 'hat'},
    'f_casual': {'White': 'shirt', 'Orange': 'pants', 'Grey': 'shoes', 'Head|Brown': 'hair2'},
    'f_formal': {'LimeGreen': 'shirt', 'Feet|Red': 'shoes', 'Head|Red': 'hair', 'Head|Brown': 'hair2'},
    'f_punk': {'Body|Black': 'shirt', 'Legs|Black': 'pants', 'Feet|Black': 'shoes', 'Head|Pink': 'hair',
               'Head|Brown': 'hair2', 'Head|Black': 'hair2'},
    'f_suit': {'Body|Black': 'shirt', 'Legs|Black': 'pants', 'Feet|Black': 'shoes', 'Head|Brown': 'hair2',
               'White': 'collar'},
    'f_worker': {'Worker_Vest': 'shirt', 'Brown2': 'pants', 'Brown_02': 'pants2', 'Feet|Black': 'shoes',
                 'Head|Worker_Yellow': 'hat', 'Head|Brown': 'hair2', 'Head|DarkBrown': 'hair'},
    'f_soldier': {'Swat': 'shirt', 'Legs|Swat': 'pants', 'Feet|Black': 'shoes', 'Head|Brown': 'hair2'},
    'f_jacket': {'Green': 'shirt', 'LightGreen': 'shirt3', 'Legs|Brown2': 'pants', 'Legs|Brown_02': 'pants2',
                 'Feet|Brown2': 'shoes', 'Head|Brown': 'hair2'},
}

# какие модели подходят под «тип одежды» из внешности (defs.Look.torso)
CHAR_BY_TORSO = {
    False: {'tee': ('m_casual', 'm_casual', 'm_punk'), 'stripes': ('m_casual', 'm_beach'),
            'tank': ('m_beach', 'm_punk'), 'jacket': ('m_suit',), 'leather': ('m_jacket',),
            'hoodie': ('m_hoodie',), 'vest': ('m_worker',), 'police': ('m_suit',), 'armor': ('m_swat',)},
    True: {'tee': ('f_casual', 'f_formal'), 'stripes': ('f_casual', 'f_punk'), 'tank': ('f_formal', 'f_punk'),
           'jacket': ('f_suit',), 'leather': ('f_jacket',), 'hoodie': ('f_casual', 'f_jacket'),
           'vest': ('f_worker',), 'police': ('f_suit',), 'armor': ('f_soldier',)},
}

# оружие: идентификатор -> (файл, доворот в руке: курс, тангаж, крен)
WEAPON_MODELS = {
    W_BAT: ('bat', (0.0, 90.0, 0.0)),
    W_PISTOL: ('pistol', (0.0, 0.0, 0.0)),
    W_UZI: ('uzi', (0.0, 0.0, 0.0)),
    W_SHOTGUN: ('shotgun', (0.0, 0.0, 0.0)),
    W_AK: ('ak', (0.0, 0.0, 0.0)),
    W_ROCKET: ('rocket', (0.0, 0.0, 0.0)),
    W_GRENADE: ('grenade', (0.0, 0.0, 0.0)),
    W_MOLOTOV: ('molotov', (0.0, 0.0, 0.0)),
}

CHAR_HEIGHT = 1.87          # рост моделей набора, м
PED_HEIGHT = 1.80           # рост персонажа в игре при look.scale == 1


def _mul(c, k):
    return (min(1.0, c[0] * k), min(1.0, c[1] * k), min(1.0, c[2] * k))


class Models(object):

    def __init__(self, assets, loader):
        self.assets = assets
        self.loader = loader
        self.dir = os.path.join(assets.root, 'assets', 'models')
        self.meta = {}
        self.ok = False
        try:
            with open(os.path.join(self.dir, 'models.json'), encoding='utf-8') as f:
                self.meta = json.load(f)
            self.ok = bool(self.meta.get('chars')) and bool(self.meta.get('vehicles'))
        except Exception:
            self.ok = False
        self._files = {}
        self._bodies = {}
        self._wheels = {}
        self._actors = {}
        self._weapons = {}
        self._hand = {}
        self.failed = set()
        self.chars_ok = self.ok

    # ------------------------------------------------------------------
    def path(self, *parts):
        return Filename.fromOsSpecific(os.path.join(self.dir, *parts))

    def _load(self, *parts):
        key = '/'.join(parts)
        np_ = self._files.get(key)
        if np_ is None:
            np_ = self.loader.loadModel(self.path(*parts))
            self._files[key] = np_
        return np_

    # ------------------------------------------------------------------
    # машины
    # ------------------------------------------------------------------
    def vehicle_info(self, kind, spec):
        """Сведения о модели машины, подогнанной под габариты spec, или None."""
        if not self.ok or kind in self.failed:
            return None
        ent = VEHICLE_MODELS.get(kind)
        if ent is None:
            return None
        info = self.meta['vehicles'].get(ent[0])
        if info is None:
            return None
        height = spec.H
        if spec.box:
            height = max(height, spec.box[1])
        sx, sy, sz = spec.W / info['W'], spec.L / info['L'], height / info['H']
        ws = (sy * sz) ** 0.5                        # колёса остаются круглыми
        wheels = []
        for w in info['wheels']:
            r = w['r'] * ws
            wheels.append((w['x'] * sx, w['y'] * sy, r, w['x'] < 0))

        def pts(name):
            return [(p[0] * sx, p[1] * sy, p[2] * sz) for p in info.get(name, [])]
        return dict(model=ent[0], opt=ent[1], scale=(sx, sy, sz), wheel_scale=ws, wheels=wheels,
                    wheel_r=(wheels[0][2] if wheels else spec.wheel_r), head=pts('head'), tail=pts('tail'),
                    siren=pts('siren'), height=height)

    def vehicle_body(self, kind, spec, paint, wreck=False):
        """Кузов нужного цвета (NodePath-шаблон, его копируют) или None, если модели нет."""
        key = (kind, tuple(paint), wreck)
        np_ = self._bodies.get(key)
        if np_ is not None:
            return np_
        info = self.vehicle_info(kind, spec)
        if info is None:
            return None
        try:
            src = self._load('veh', info['model'] + '.bam').find('body')
            root = NodePath('body')
            m = src.copyTo(root)
            m.setScale(*info['scale'])
            opt = info['opt']
            pn = m.find('paint')
            if not pn.isEmpty():
                pn.setColorScale(paint[0], paint[1], paint[2], 1.0)
            tn = m.find('trim')
            if not tn.isEmpty():
                tc = opt.get('trim', 'dark')
                if tc == 'dark':
                    tc = _mul(paint, 0.62)
                tn.setColorScale(tc[0], tc[1], tc[2], 1.0)
            sn = m.find('siren')
            if not sn.isEmpty() and not opt.get('siren'):
                sn.removeNode()
            if wreck:
                m.setColorScale(WRECK[0], WRECK[1], WRECK[2], 1.0)
            root.flattenStrong()                     # масштаб и цвета — прямо в вершины
        except Exception:
            self.failed.add(kind)
            return None
        self._bodies[key] = root
        return root

    def vehicle_wheel(self, kind, spec, left=False):
        """Колесо (ось вращения — X).  У левого наружная сторона смотрит в -X."""
        key = (kind, left)
        np_ = self._wheels.get(key)
        if np_ is not None:
            return np_
        info = self.vehicle_info(kind, spec)
        if info is None:
            return None
        try:
            src = self._load('veh', info['model'] + '.bam').find('wheel')
            if src.isEmpty():
                return None
            root = NodePath('wheel')
            m = src.copyTo(root)
            m.setScale(info['wheel_scale'])
            if left:
                m.setH(180.0)
            root.flattenStrong()
        except Exception:
            self.failed.add(kind)
            return None
        self._wheels[key] = root
        return root

    # ------------------------------------------------------------------
    # оружие
    # ------------------------------------------------------------------
    def weapon(self, wid):
        """Модель оружия: ствол вдоль +Y, верх +Z, начало координат — в точке хвата."""
        if not self.ok or wid not in WEAPON_MODELS:
            return None
        np_ = self._weapons.get(wid)
        if np_ is None:
            name, hpr = WEAPON_MODELS[wid]
            try:
                src = self._load('weapons', name + '.bam')
            except Exception:
                return None
            np_ = NodePath('weapon')
            m = src.copyTo(np_)
            m.setHpr(*hpr)
            np_.flattenStrong()
            self._weapons[wid] = np_
        return np_

    def hand_matrix(self, sex):
        """(имя кости, матрица «оружие -> кость») — как оружие лежит в правой руке."""
        res = self._hand.get(sex)
        if res is None:
            h = self.meta['hand'][sex]
            r, b, u, o = h['right'], h['barrel'], h['up'], h['origin']
            res = (h['joint'], LMatrix4(r[0], r[1], r[2], 0, b[0], b[1], b[2], 0, u[0], u[1], u[2], 0,
                                        o[0], o[1], o[2], 1))
            self._hand[sex] = res
        return res

    # ------------------------------------------------------------------
    # персонажи
    # ------------------------------------------------------------------
    def pick_char(self, look, kind):
        if kind in ('swat', 'army'):
            key = 'f_soldier' if look.female else 'm_swat'
        else:
            table = CHAR_BY_TORSO[bool(look.female)]
            opts = table.get(look.torso) or table['tee']
            key = opts[int(look.fat * 977.0 + look.scale * 131.0) % len(opts)]
        if key not in self.meta['chars']:
            key = 'f_casual' if look.female else 'm_casual'
        return key

    def actor(self, key):
        """Новый экземпляр персонажа (Actor) с подключёнными клипами анимации."""
        from direct.actor.Actor import Actor
        t = self._actors.get(key)
        if t is None:
            sex = key[0]
            anims = dict((name, self.path('anims', '%s_%s.bam' % (sex, name))) for name in self.meta['anims'][sex])
            t = Actor(self._load('chars', key + '.bam'), anims)
            for np_ in t.findAllMatches('**/Pistol|*'):
                np_.removeNode()                # пистолет, «приросший» к руке модели: оружие выдаём своё
            self._actors[key] = t
        a = Actor(other=t)
        # рамки для отсечения считаем один раз: поза меняется, а рост — нет
        node = a.node()
        node.setBounds(BoundingSphere(LPoint3(0.0, 0.0, 0.95), 1.7))
        node.setFinal(True)
        return a

    def colors(self, key, look):
        """Цвета ролей для данного персонажа и внешности (None — оставить цвет модели)."""
        return {
            'skin': look.skin, 'skin2': _mul(look.skin, 0.86), 'hair': look.hair, 'hair2': _mul(look.hair, 0.72),
            'shirt': look.shirt, 'shirt2': _mul(look.shirt, 0.55), 'shirt3': _mul(look.shirt, 1.25),
            'pants': look.pants, 'pants2': _mul(look.pants, 0.78), 'shoes': look.shoes,
            'hat': look.hat_color if look.hat else None,
            'collar': (0.60, 0.72, 0.90) if look.torso == 'police' else (0.88, 0.88, 0.90),
        }

    def paint_char(self, actor, key, look):
        roles = CHAR_ROLES.get(key, {})
        cols = self.colors(key, look)
        for np_ in actor.findAllMatches('**/+GeomNode'):
            name = np_.getName()
            mat = name.split('|')[-1]
            role = roles.get(name) or roles.get(mat) or COMMON_ROLES.get(mat)
            if role is None:
                continue
            c = cols[role]
            if c is not None:
                np_.setColor(c[0], c[1], c[2], 1.0)
