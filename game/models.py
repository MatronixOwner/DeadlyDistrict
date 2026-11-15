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
# персонажи.  Все модели — на одном скелете, клипы анимации общие; внешность задаёт текстура.
# Ключ — имя текстуры в assets/models/chars; какая к ней модель, записано в models.json.
# ---------------------------------------------------------------------------
CIV_M = {
    # одежда из внешности (defs.Look.torso) -> кто подходит
    'jacket': ('m_shirt', 'm_shirt_b', 'm_shirt_c', 'm_old'),
    'leather': ('m_grey_b', 'm_old'),
    'police': ('m_shirt_c',),
    None: ('m_red', 'm_red_b', 'm_red_c', 'm_red_d', 'm_grey', 'm_grey_b', 'm_shirt', 'm_shirt_b', 'm_old'),
}
CIV_F = ('f_goth', 'f_black', 'f_old', 'f_old_b', 'f_old_c', 'f_black', 'f_goth')
GANG = ('thug_a', 'thug_pig', 'thug_clown', 'thug_a')
FEMALE = ('f_goth', 'f_black', 'f_old', 'f_old_b', 'f_old_c', 'cop_f')

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

CHAR_HEIGHT = 1.80          # рост моделей набора, м
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
            self.ok = bool(self.meta.get('chars')) and bool(self.meta.get('vehicles')) and 'hand' in self.meta
        except Exception:
            self.ok = False
        self._files = {}
        self._bodies = {}
        self._wheels = {}
        self._actors = {}
        self._weapons = {}
        self._hand = {}
        self._ctex = {}
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

    def preload(self):
        """Загрузить все файлы заранее (на экране загрузки), чтобы игра не «запиналась», когда на улице
        впервые появляется новый персонаж или машина."""
        if not self.ok:
            return
        try:
            for key in sorted(self.meta['chars']):
                self.char_texture(key)
                # создаём по экземпляру каждой модели: при этом загружаются и привязываются все клипы
                a = self.actor(key)
                for name in self.meta['anims']:
                    a.getAnimControl(name)
                a.cleanup()
                a.removeNode()
            for name in sorted(self.meta['vehicles']):
                self._load('veh', name + '.bam')
            for wid in sorted(WEAPON_MODELS):
                self.weapon(wid)
        except Exception:
            self.ok = self.chars_ok = False

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

    def hand_matrix(self, kind):
        """(имя кости, матрица «оружие -> кость»): kind — 'pistol' (в одной руке) или 'rifle' (в двух)."""
        res = self._hand.get(kind)
        if res is None:
            h = self.meta['hand'][kind]
            r, b, u, o = h['right'], h['barrel'], h['up'], h['origin']
            res = (self.meta['hand']['joint'],
                   LMatrix4(r[0], r[1], r[2], 0, b[0], b[1], b[2], 0, u[0], u[1], u[2], 0, o[0], o[1], o[2], 1))
            self._hand[kind] = res
        return res

    # ------------------------------------------------------------------
    # персонажи
    # ------------------------------------------------------------------
    def pick_char(self, look, kind):
        """Какой персонаж (текстура и модель) соответствует внешности look и роли kind."""
        chars = self.meta['chars']
        n = int(look.fat * 977.0 + look.scale * 1313.0 + look.skin[0] * 71.0 + look.shirt[0] * 37.0 +
                look.pants[2] * 53.0)
        if kind == 'swat':
            key = 'swat'
        elif kind == 'army':
            key = 'army'
        elif kind == 'cop':
            key = 'cop_f' if (look.female or n % 4 == 0) else 'cop_m'
        elif kind == 'fbi':
            key = 'm_shirt_c'
        elif kind in ('gang', 'enemy') and not look.female:
            key = GANG[n % len(GANG)]
        elif look.female:
            key = CIV_F[n % len(CIV_F)]
        else:
            opts = CIV_M.get(look.torso) or CIV_M[None]
            key = opts[n % len(opts)]
        if key not in chars:
            key = 'f_black' if look.female else 'm_grey'
        return key

    def is_female(self, key):
        return key in FEMALE

    def actor(self, key):
        """Новый экземпляр персонажа (Actor) с текстурой и подключёнными клипами анимации."""
        from direct.actor.Actor import Actor
        model = self.meta['chars'][key]['model']
        t = self._actors.get(model)
        if t is None:
            anims = dict((name, self.path('anims', name + '.bam')) for name in self.meta['anims'])
            t = Actor(self._load('chars', model + '.bam'), anims)
            self._actors[model] = t
        a = Actor(other=t)
        a.setTexture(self.char_texture(key), 1)
        # рамки для отсечения считаем один раз: поза меняется, а рост — нет
        node = a.node()
        node.setBounds(BoundingSphere(LPoint3(0.0, 0.0, 0.95), 1.7))
        node.setFinal(True)
        return a

    def char_texture(self, key):
        t = self._ctex.get(key)
        if t is None:
            t = self.loader.loadTexture(self.path('chars', key + '.png'))
            self.assets.setup_filter(t, True)
            self._ctex[key] = t
        return t
