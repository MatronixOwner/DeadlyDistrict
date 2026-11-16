# -*- coding: utf-8 -*-
"""Готовые модели: персонажи со скелетной анимацией, машины, оружие.

Файлы лежат в assets/models и получены скриптами tools/import_psx.py (люди и машины в стиле
PlayStation 1) и tools/import_models.py (оружие).  Здесь — только то, как игра их использует:
какую модель взять для машины или человека, как её покрасить и какие клипы анимации проигрывать.
Чтобы подставить другие модели, достаточно положить свои .bam и поправить таблицы ниже.
"""
import json
import os

from panda3d.core import Filename, NodePath, LMatrix4, BoundingSphere, LPoint3, PNMImage, Texture, LColorf

from .defs import (W_FIST, W_BAT, W_PISTOL, W_UZI, W_SHOTGUN, W_AK, W_ROCKET, W_GRENADE, W_MOLOTOV, W_SILENCED,
                   W_M4, W_DOUBLE, W_SNIPER, W_KNIFE)

# ---------------------------------------------------------------------------
# машины: тип из vehicle.SPECS -> (модель, особенности)
#   overlay — накладка поверх краски (ржавчина, красный крест); словарь — по номеру цвета
#   siren   — оставить ли на крыше маячки
#   wheel_k — колёса крупнее обычных (и кузов выше), для внедорожника
#   dull    — множитель яркости краски
# ---------------------------------------------------------------------------
VEHICLE_MODELS = {
    'sedan': ('wagon', {}),
    'hatch': ('hatch', {}),
    'sports': ('sleek', {}),
    'muscle': ('caprice', {}),
    'suv': ('minivan', {'wheel_k': 1.17}),
    'pickup': ('minivan', {}),
    'van': ('stepvan', {'overlay': {12: 'stepvan_mail'}}),
    'taxi': ('taxi', {}),
    'police': ('police', {'siren': True}),
    'ambulance': ('stepvan', {'overlay': 'stepvan_ambulance', 'siren': True}),
    'bus': ('bus', {}),
    'truck': ('stepvan', {'overlay': {2: 'stepvan_mail'}}),
    'enforcer': ('stepvan', {'siren': True}),
    'fbi': ('volvo', {}),
    'army': ('stepvan', {}),
    'beater': ('dacia', {}),
    'lowrider': ('vintage', {}),
    # новые машины на тех же кузовах: модель растягивается под свои габариты (см. vehicle_info)
    'limo': ('caprice', {'wheel_k': 0.86}),
    'racer': ('sleek', {}),
    'minibus': ('hiace', {}),
    'firetruck': ('stepvan', {'siren': True, 'wheel_k': 1.1}),
    'cashvan': ('stepvan', {}),
    'icecream': ('stepvan', {}),
    'hotrod': ('vintage', {'wheel_k': 1.12}),
    'jeep': ('minivan', {'wheel_k': 1.3}),
    'pizza': ('hatch', {}),
    'tuner': ('hatch', {}),
    'brick': ('volvo', {}),
}

WRECK = (0.20, 0.18, 0.16)
# Текстуры набора нарисованы приглушёнными красками; цвета игры приводим к тому же виду.
PAINT_GAIN = 0.74
PAINT_SAT = 0.86

# ---------------------------------------------------------------------------
# персонажи.  Все модели — на одном скелете, клипы анимации общие; внешность задаёт текстура.
# Ключ — имя текстуры в assets/models/chars; какая к ней модель, записано в models.json.
# ---------------------------------------------------------------------------
CIV_M = {
    # одежда из внешности (defs.Look.torso) -> кто подходит
    'jacket': ('m_shirt', 'm_shirt_b', 'm_shirt_c', 'm_shirt_h3', 'm_shirt_h3b', 'm_shirt_h4', 'm_shirt_h4b',
               'm_old', 'm_old_h3'),
    'leather': ('m_leather', 'm_leather_c', 'm_grey_h4b'),
    'police': ('m_shirt_c', 'm_shirt_h4c'),
    None: ('m_red_h2', 'm_red_h2b', 'm_red_h2c', 'm_red_h3b', 'm_red_h3c', 'm_red_h4b', 'm_red_h4c',
           'm_grey_h2', 'm_grey_h2b', 'm_grey_h3', 'm_grey_h4', 'm_grey_h4b', 'm_shirt', 'm_shirt_h4c', 'm_old'),
}
CIV_F = ('f_goth', 'f_black', 'f_old', 'f_old_b', 'f_old_c', 'f_black', 'f_goth')
GANG = ('m_leather_b', 'm_red_h3c', 'm_leather', 'm_grey_h4b')
FEMALE = ('f_goth', 'f_black', 'f_old', 'f_old_b', 'f_old_c', 'cop_f')
HERO = 'hero'               # этот облик — только у главного героя

# оружие: идентификатор -> (файл, доворот в руке: курс, тангаж, крен)
WEAPON_MODELS = {
    W_BAT: ('bat', (0.0, 90.0, 0.0)),
    W_KNIFE: ('knife', (0.0, 90.0, 0.0)),
    W_PISTOL: ('pistol', (0.0, 0.0, 0.0)),
    W_SILENCED: ('silenced', (0.0, 0.0, 0.0)),
    W_UZI: ('uzi', (0.0, 0.0, 0.0)),
    W_SHOTGUN: ('shotgun', (0.0, 0.0, 0.0)),
    W_DOUBLE: ('double', (0.0, 0.0, 0.0)),
    W_AK: ('ak', (0.0, 0.0, 0.0)),
    W_M4: ('m4', (0.0, 0.0, 0.0)),
    W_SNIPER: ('sniper', (0.0, 0.0, 0.0)),
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
            from . import bikes
            bikes.use_models(self)
        except Exception:
            self.ok = False
        self._files = {}
        self._bodies = {}
        self._wheels = {}
        self._actors = {}
        self._weapons = {}
        self._hand = {}
        self._arm = None
        self._ride = {}
        self._ctex = {}
        self._vinfo = {}
        self._vtex = {}
        self._images = {}
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
                for tex in self.char_textures(key):
                    self.char_texture(tex)
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
        res = self._vinfo.get(kind)
        if res is not None:
            return res
        ent = VEHICLE_MODELS.get(kind)
        if ent is None:
            return None
        info = self.meta['vehicles'].get(ent[0])
        if info is None:
            return None
        opt = ent[1]
        height = spec.H
        if spec.box:
            height = max(height, spec.box[1])
        sx, sy, sz = spec.W / info['W'], spec.L / info['L'], height / info['H']
        ws = (sy * sz) ** 0.5                        # колёса остаются круглыми
        wk = opt.get('wheel_k', 1.0)
        lift = 0.0
        wheels = []
        for w in info['wheels']:
            r = w['r'] * ws
            lift = r * (wk - 1.0)
            wheels.append((w['x'] * sx, w['y'] * sy, r * wk, w['x'] < 0))

        def pts(name):
            return [(p[0] * sx, p[1] * sy, p[2] * sz + lift) for p in info.get(name, [])]
        res = dict(model=ent[0], opt=opt, scale=(sx, sy, sz), wheel_scale=ws * wk, wheels=wheels, lift=lift,
                   wheel_r=(wheels[0][2] if wheels else spec.wheel_r), head=pts('head'), tail=pts('tail'),
                   siren=pts('siren') if opt.get('siren') else [], height=height + lift,
                   fixed=bool(info.get('fixed')))
        self._vinfo[kind] = res
        return res

    def _pnm(self, name):
        img = self._images.get(name)
        if img is None:
            img = PNMImage()
            if not img.read(Filename.fromOsSpecific(os.path.join(self.dir, 'veh', name + '.png'))):
                raise IOError(name)
            if img.isGrayscale():
                img.makeRgb()                # у серой картинки значение лежит только в одном канале
            self._images[name] = img
        return img

    def vehicle_texture(self, kind, spec, paint, idx=0):
        """Текстура кузова, окрашенная в цвет paint (idx — номер цвета: от него зависят накладки).

        Краска собирается из слоёв: цвет × светотень, сверху накладка (ржавчина, эмблема), сверху всё,
        что не красится, — стёкла, шины, фары, хром."""
        info = self.vehicle_info(kind, spec)
        if info is None:
            return None
        model = info['model']
        opt = info['opt']
        overlay = opt.get('overlay')
        if isinstance(overlay, dict):
            overlay = overlay.get(idx)
        if info['fixed']:
            key = (model,)
        else:
            key = (model, int(paint[0] * 255), int(paint[1] * 255), int(paint[2] * 255), overlay)
        tex = self._vtex.get(key)
        if tex is not None:
            return tex
        if info['fixed']:
            img = self._pnm(model)
        else:
            detail = self._pnm(model)
            w, h = detail.getXSize(), detail.getYSize()
            g = (paint[0] * 0.30 + paint[1] * 0.59 + paint[2] * 0.11)
            k = PAINT_GAIN * opt.get('dull', 1.0)
            img = PNMImage(w, h, 3)
            img.fill(min(1.0, (g + (paint[0] - g) * PAINT_SAT) * k), min(1.0, (g + (paint[1] - g) * PAINT_SAT) * k),
                     min(1.0, (g + (paint[2] - g) * PAINT_SAT) * k))
            img.multSubImage(self._pnm(model + '_shade'), 0, 0, 0, 0, w, h, 2.0)
            if overlay:
                img.blendSubImage(self._pnm(overlay), 0, 0, 0, 0, w, h)
            img.blendSubImage(detail, 0, 0, 0, 0, w, h)
        tex = Texture('veh-%s' % '-'.join(str(x) for x in key))
        tex.load(img)
        self.assets.setup_filter(tex)
        self._vtex[key] = tex
        return tex

    def vehicle_body(self, kind, spec, paint, wreck=False, idx=0):
        """Кузов нужного цвета (NodePath-шаблон, его копируют) или None, если модели нет."""
        key = (kind, tuple(paint), wreck, idx)
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
            m.setZ(info['lift'])
            sn = m.find('siren')
            if not sn.isEmpty() and not info['opt'].get('siren'):
                sn.removeNode()
            skin = m.find('skin')
            skin.setTexture(self.vehicle_texture(kind, spec, paint, idx), 1)
            if wreck:
                m.setColorScale(WRECK[0], WRECK[1], WRECK[2], 1.0)
            root.flattenStrong()                     # масштаб и цвета — прямо в вершины
        except Exception:
            self.failed.add(kind)
            return None
        self._bodies[key] = root
        return root

    def vehicle_wheel(self, kind, spec, left=False):
        """Колесо (ось вращения — X).  У левого наружная сторона смотрит в -X.  Текстуру ставит машина."""
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
            # Своя текстура оружия должна перекрыть текстуру персонажа, в чьей руке оно окажется;
            # у моделей без текстуры (бита, гранаты) чужую текстуру просто отключаем.
            tex = None
            for t in np_.findAllTextures():
                tex = t
                break
            if tex is not None:
                self.assets.setup_filter(tex)
                np_.setTexture(tex, 3)
            else:
                np_.setTextureOff(3)
            np_.setColorScaleOff(3)
            self._weapons[wid] = np_
        return np_

    def weapon_name(self, wid):
        """Имя модели оружия («ak», «shotgun»…) или None."""
        m = WEAPON_MODELS.get(wid)
        return m[0] if m else None

    def arm_ref(self):
        """Левая рука в стойке прицеливания с длинным стволом: (плечо, предплечье, длина плеча, длина
        предплечья).  Первые два — матрицы костей upperarm_l и lowerarm_l относительно своих родителей в
        первом кадре клипа rifle_fire.  Скелет у всех персонажей общий, поэтому снимается один раз."""
        if self._arm is None:
            a = self.actor('hero')
            b = a.getPartBundle('modelRoot')
            c = a.getAnimControl('rifle_fire')
            b.setAnimBlendFlag(True)
            b.setControlEffect(c, 1.0)
            c.pose(0)
            up = a.exposeJoint(None, 'modelRoot', 'upperarm_l', localTransform=True)
            lo = a.exposeJoint(None, 'modelRoot', 'lowerarm_l', localTransform=True)
            ha = a.exposeJoint(None, 'modelRoot', 'hand_l', localTransform=True)
            a.update(force=True)
            m1, m2 = LMatrix4(up.getMat()), LMatrix4(lo.getMat())
            self._arm = (m1, m2, m2.getRow3(3).length(), ha.getMat().getRow3(3).length())
            a.cleanup()
            a.removeNode()
        return self._arm

    def rider_ref(self, mix, frame=10):
        """Руки ездока в позе посадки mix = ((клип, вес), ...) — то, от чего считается хват руля.

        Для каждой руки ('l', 'r'): матрица ключицы в осях модели, матрицы плеча, предплечья и кисти
        относительно родителей, точка ладони в осях кисти, длины плеча и предплечья; 'spine' — матрица таза
        в осях модели и матрица поясницы относительно него (корпус ездока поворачивается за рулём).  Поза у
        ездока застывшая, скелет у всех персонажей общий, поэтому снимается один раз на посадку."""
        from panda3d.core import PartBundle
        key = (tuple(mix), frame)
        res = self._ride.get(key)
        if res is None:
            a = self.actor('hero')
            b = a.getPartBundle('modelRoot')
            b.setAnimBlendFlag(True)
            b.setBlendType(PartBundle.BTNormalizedLinear)
            for name, wgt in mix:
                c = a.getAnimControl(name)
                if c is None or wgt <= 0.0:
                    continue
                c.pose(min(frame, max(0, c.getNumFrames() - 1)))
                b.setControlEffect(c, wgt)
            nodes = {}
            for s in 'lr':
                nodes[s] = (a.exposeJoint(None, 'modelRoot', 'clavicle_' + s),
                            a.exposeJoint(None, 'modelRoot', 'upperarm_' + s, localTransform=True),
                            a.exposeJoint(None, 'modelRoot', 'lowerarm_' + s, localTransform=True),
                            a.exposeJoint(None, 'modelRoot', 'hand_' + s, localTransform=True),
                            a.exposeJoint(None, 'modelRoot', 'hand_' + s),
                            a.exposeJoint(None, 'modelRoot', 'middle_01_' + s))
            pel = a.exposeJoint(None, 'modelRoot', 'pelvis')
            sp = a.exposeJoint(None, 'modelRoot', 'spine_01', localTransform=True)
            a.update(force=True)
            res = {'spine': (LMatrix4(pel.getMat()), LMatrix4(sp.getMat()))}
            for s in 'lr':
                clav, up, lo, ha, net, mid = nodes[s]
                m1, m2, mh = LMatrix4(up.getMat()), LMatrix4(lo.getMat()), LMatrix4(ha.getMat())
                inv = LMatrix4(net.getMat())
                inv.invertInPlace()
                wrist = net.getPos()
                palm = inv.xformPoint(wrist + (mid.getPos() - wrist) * 0.62)      # середина ладони — ближе к костяшкам
                res[s] = (LMatrix4(clav.getMat()), m1, m2, mh, palm, m2.getRow3(3).length(), mh.getRow3(3).length())
            a.cleanup()
            a.removeNode()
            self._ride[key] = res
        return res

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
            key = 'f_black' if look.female else 'm_shirt'
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
        info = self.meta['chars'][key]
        head = info.get('head_tex')
        if head:
            # сборный персонаж: у тела и головы свои текстуры
            a.find('**/skin').setTexture(self.char_texture(info['tex']), 1)
            a.find('**/head').setTexture(self.char_texture(head, info.get('head_gain')), 1)
        else:
            a.setTexture(self.char_texture(info.get('tex', key)), 1)
        # рамки для отсечения считаем один раз: поза меняется, а рост — нет
        node = a.node()
        node.setBounds(BoundingSphere(LPoint3(0.0, 0.0, 0.95), 1.7))
        node.setFinal(True)
        return a

    def char_textures(self, key):
        """Имена файлов текстур персонажа: одежда и, у сборных, голова."""
        info = self.meta['chars'][key]
        names = [info.get('tex', key)]
        if info.get('head_tex'):
            names.append(info['head_tex'])
        return names

    def char_texture(self, name, gain=None):
        """Текстура assets/models/chars/<name>.png.

        gain — поправка цвета (r, g, b): у сборного персонажа кожа головы подводится под кожу тела,
        иначе лицо и шея одного оттенка, а грудь в вырезе ворота и руки — другого."""
        if gain is not None and max(abs(g - 1.0) for g in gain) < 0.02:
            gain = None
        key = name if gain is None else (name, tuple(gain))
        t = self._ctex.get(key)
        if t is None:
            if gain is None:
                t = self.loader.loadTexture(self.path('chars', name + '.png'))
            else:
                img = PNMImage()
                img.read(Filename.fromOsSpecific(os.path.join(self.dir, 'chars', name + '.png')))
                img.makeRgb()
                img *= LColorf(gain[0], gain[1], gain[2], 1.0)
                t = Texture(name + '_tone')
                t.load(img)
            self.assets.setup_filter(t, True)
            self._ctex[key] = t
        return t

    # ------------------------------------------------------------------
    # мебель для интерьеров (tools/import_furniture.py)
    # ------------------------------------------------------------------
    def _furn_meta(self):
        m = getattr(self, '_fmeta', None)
        if m is None:
            try:
                with open(os.path.join(self.dir, 'furn', 'furn.json'), encoding='utf-8') as f:
                    m = json.load(f)
                self._furn_root = self.loader.loadModel(self.path('furn', 'furn.bam'))
            except Exception:
                m = dict(items={}, alpha=[])
                self._furn_root = None
            self._fmeta = m
            self._ftex = {}
            self._furn = {}
        return m

    def furn_size(self, name):
        """Габариты предмета мебели (ширина, глубина, высота) или None, если такого нет."""
        it = self._furn_meta()['items'].get(name)
        return (it['w'], it['d'], it['h']) if it else None

    def furn_seat(self, name):
        """Сиденье предмета мебели (см. tools/furn_seats.py) или None, если на нём не сидят."""
        it = self._furn_meta()['items'].get(name)
        return it.get('seat') if it else None

    def furn(self, name):
        """Образец предмета мебели: стоит на полу серединой в начале координат, лицом в -Y.  Копировать copyTo."""
        meta = self._furn_meta()
        np_ = self._furn.get(name)
        if np_ is not None:
            return np_
        if name not in meta['items'] or self._furn_root is None:
            return None
        src = self._furn_root.find('**/' + name)
        if src.isEmpty():
            return None
        np_ = src.copyTo(NodePath('furn'))
        from panda3d.core import TransparencyAttrib
        for g in np_.getChildren():
            tn = g.getName()
            t = self._ftex.get(tn)
            if t is None:
                t = self.loader.loadTexture(self.path('furn', tn + '.png'))
                self.assets.setup_filter(t)
                self._ftex[tn] = t
            g.setTexture(t)
            if tn in meta['alpha']:
                g.setTransparency(TransparencyAttrib.MBinary)
                g.setTwoSided(True)
        self._furn[name] = np_
        return np_

