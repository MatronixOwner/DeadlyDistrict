# -*- coding: utf-8 -*-
"""Внешний вид персонажа: модель со скелетом, выбор и плавная смена клипов анимации, оружие в руках.

Логика персонажа (ped.py) сообщает только состояние: стоит, идёт, бежит, бьёт, целится, лежит.
Здесь оно превращается в клипы анимации.  Все модели сидят на одном скелете, клипы у них общие.
"""
import math
import random

from panda3d.core import PartBundle, LMatrix4, LVector3, NodePath

from .models import CHAR_HEIGHT, PED_HEIGHT

# скорость (м/с), при которой ступни клипа не «скользят» по земле
REF = {'walk': 1.05, 'walk_f': 1.15, 'jog': 3.6, 'sprint': 5.5, 'run_f': 4.0, 'pistol_walk': 1.35,
       'rifle_walk': 1.35, 'rifle_run': 3.9, 'texting': 1.05, 'walk_back': 1.3}
JOG_FROM = 2.3              # с какой скорости персонаж переходит на бег трусцой
SPRINT_FROM = 4.6           # ...и на быстрый бег

FADE = 0.18                 # время плавного перехода между клипами, с
DEATHS = ('death_a', 'death_b', 'death_c')
# клипы, в которых длинный ствол держат двумя руками: оружие в них направляется от правой ладони к левой
TWO_HANDS = ('rifle_idle', 'rifle_walk', 'rifle_run', 'rifle_fire')
SHOULDERED = 'rifle_fire'   # стойка прицеливания и стрельбы: ствол смотрит туда, куда целятся
# Где левая ладонь поддерживает оружие в стойке: (вперёд от рукояти, вверх от неё), м — низ цевья.
# У автомата и карабина перед рукоятью висит магазин, цевьё начинается за ним.
SUPPORT = {'ak': (0.41, 0.115), 'm4': (0.32, 0.082), 'shotgun': (0.36, -0.01), 'double': (0.27, 0.022),
           'sniper': (0.34, 0.05), 'rocket': (0.30, 0.04)}
SUPPORT_ANY = (0.34, 0.03)
AIM_PITCH = 32.0            # дальше этого угла ствол за взглядом не идёт: корпус персонажа не наклоняется
ELBOW = LVector3(0.55, 0.2, -0.8)       # куда смотрит левый локоть: наружу и вниз (модель глядит в −Y, лево — +X)
RIDE_ELBOW = {'l': LVector3(0.62, 0.25, -0.74), 'r': LVector3(-0.62, 0.25, -0.74)}     # локти ездока: в стороны и вниз


def _arc(v0, v1):
    """Матрица кратчайшего поворота от направления v0 к v1 (оба единичные)."""
    ax = v0.cross(v1)
    s = ax.length()
    if s < 1e-6:
        return LMatrix4.identMat()
    ax /= s
    return LMatrix4.rotateMat(math.degrees(math.atan2(s, v0.dot(v1))), ax)


def _about(m, p, rot):
    """Матрица кости m, повёрнутая матрицей rot вокруг точки p."""
    return m * LMatrix4.translateMat(-p) * rot * LMatrix4.translateMat(p)


class PedVisual(object):

    def __init__(self, models, parent, look, kind):
        self.models = models
        key = getattr(look, 'model', None)
        if key not in models.meta['chars']:
            key = models.pick_char(look, kind)
        self.key = key
        self.female = models.is_female(key)
        a = models.actor(key)
        self.actor = a
        s = PED_HEIGHT / CHAR_HEIGHT * look.scale
        if self.female:
            s *= 0.985
        k = 1.0 + (look.fat - 1.0) * 0.25           # полнота — немного шире в плечах
        self.scale = s
        self.root = parent.attachNewNode('m')
        a.reparentTo(self.root)
        a.setH(180.0)                               # модели набора смотрят в -Y, персонажи игры — в +Y
        a.setScale(s * k, s * k, s)
        tint = getattr(look, 'tint', None)
        if tint is not None:
            a.setColorScale(tint[0], tint[1], tint[2], 1.0)
        b = a.getPartBundle('modelRoot')
        b.setAnimBlendFlag(True)
        b.setBlendType(PartBundle.BTNormalizedLinear)
        self.bundle = b
        self.ctrls = {}
        self.cur = None
        self.cur_ctrl = None
        self.prev_ctrl = None
        self.fade = 0.0
        self.fade_len = FADE
        self.rate = 1.0
        self.loop = True
        self.time = 0.0
        self.nframes = 1
        self.fps = 30.0
        self.frame = 0
        self.done = False
        self.hold = None            # кадр, на котором клип «заморожен» (поза прицеливания)
        self.death = random.choice(DEATHS)
        self.punch_n = random.randrange(2)
        self.grips = {}
        self.mix_ctrls = []         # клипы застывшей смешанной позы (ездок)
        self.gun = None
        self.gun_kind = None
        self._rifle = None          # (точка хвата, «верх») в системе кости правой кисти
        self.support = SUPPORT_ANY  # где левая ладонь держит оружие в стойке
        self.aim_pitch = 0.0        # куда целятся: угол над горизонтом, градусы (задаёт ped.py)
        self._pitch = 0.0
        self._ik = None             # узлы, ведущие кости левой руки, пока она на цевье
        self._bars = None           # узлы, ведущие кости обеих рук ездока, пока он держится за руль
        self._legs = None           # узлы, ведущие кости ног сидящего в салоне
        self.play('idle', True, 1.0, 0.0)
        self.time = random.random() * 2.0           # чтобы толпа не дышала в такт

    # ------------------------------------------------------------------
    def _ctrl(self, name):
        c = self.ctrls.get(name)
        if c is None:
            c = self.actor.getAnimControl(name)
            if c is None:
                return None
            self.ctrls[name] = c
        return c

    def play(self, name, loop=True, rate=1.0, fade=FADE, restart=False, hold=None):
        """Включить клип.  Повторный вызов с тем же именем только подправляет темп.

        hold — доля длины клипа (0..1): клип не идёт, персонаж стоит в этой позе."""
        if name == self.cur and not restart and hold == self.hold:
            self.rate = rate
            return
        n = self._ctrl(name)
        if n is None:
            return
        if self.mix_ctrls:                          # была застывшая поза из смеси клипов — снимаем её
            for m in self.mix_ctrls:
                if m is not n:
                    self.bundle.setControlEffect(m, 0.0)
            self.mix_ctrls = []
            self.cur_ctrl = self.prev_ctrl = None
        c = self.cur_ctrl
        b = self.bundle
        p = self.prev_ctrl
        if c is not None and c is not n and fade > 0.0:
            if p is not None and p is not n and p is not c:
                b.setControlEffect(p, 0.0)
            self.prev_ctrl = c
            self.fade = self.fade_len = fade
            b.setControlEffect(n, 0.02)
            b.setControlEffect(c, 0.98)
        elif c is not n:
            if c is not None:
                b.setControlEffect(c, 0.0)
            if p is not None and p is not n:
                b.setControlEffect(p, 0.0)
            self.prev_ctrl = None
            self.fade = 0.0
            b.setControlEffect(n, 1.0)
        self.cur = name
        self.cur_ctrl = n
        self.loop = loop
        self.rate = rate
        self.hold = hold
        self.nframes = max(1, n.getNumFrames())
        self.fps = n.getFrameRate()
        self.done = False
        if hold is not None:
            self.frame = int((self.nframes - 1) * hold)
            self.time = self.frame / self.fps
            self.done = True
        else:
            self.time = 0.0
            self.frame = 0
        n.pose(self.frame)

    def pose_mix(self, mix, frame=10):
        """Застывшая поза — смесь клипов: mix = ((имя, вес), ...).  Так сидит ездок на мотоцикле:
        между «верхом» и «за рулём», в зависимости от того, как устроено седло и где руль."""
        b = self.bundle
        for c in (self.cur_ctrl, self.prev_ctrl):
            if c is not None:
                b.setControlEffect(c, 0.0)
        for c in self.mix_ctrls:
            b.setControlEffect(c, 0.0)
        self.mix_ctrls = []
        for name, wgt in mix:
            c = self._ctrl(name)
            if c is None or wgt <= 0.0:
                continue
            c.pose(min(frame, max(0, c.getNumFrames() - 1)))
            b.setControlEffect(c, wgt)
            self.mix_ctrls.append(c)
        self.cur = 'mix'
        self.cur_ctrl = self.prev_ctrl = None
        self.fade = 0.0
        self.hold = 0.0
        self.loop = True
        self.done = True

    def pelvis_pos(self, rel):
        """Где сейчас таз фигуры в осях узла rel (None, если модель без костей)."""
        a = self.actor
        if a is None:
            return None
        pj = self.grips.get('_pelvis')
        if pj is None:
            pj = self.grips['_pelvis'] = a.exposeJoint(None, 'modelRoot', 'pelvis')
        if pj is None:
            return None
        a.update(force=True)
        return pj.getPos(rel)

    def update(self, dt):
        """Продвинуть клип на dt секунд игрового времени и довести плавный переход.

        Кадр выставляется вручную, а не часами движка: так анимация замирает на паузе,
        замедляется вместе с миром и одинаково идёт в тестах."""
        if not self.done:
            self.time += dt * self.rate
            f = self.time * self.fps
            if self.loop:
                f %= self.nframes
            elif f >= self.nframes - 1:
                f = self.nframes - 1
                self.done = True
            fi = int(f)
            if fi != self.frame:
                self.frame = fi
                self.cur_ctrl.pose(fi)
        if self._rifle is not None and self.gun_kind == 'rifle':
            self._aim_long()
        if self.fade > 0.0:
            self.fade -= dt
            k = self.fade / self.fade_len
            b = self.bundle
            p = self.prev_ctrl
            if k <= 0.0:
                self.fade = 0.0
                b.setControlEffect(self.cur_ctrl, 1.0)
                if p is not None:
                    b.setControlEffect(p, 0.0)
                    self.prev_ctrl = None
            else:
                b.setControlEffect(self.cur_ctrl, 1.0 - k)
                if p is not None:
                    b.setControlEffect(p, k)

    def busy(self):
        """Идёт ли ещё одноразовый клип (удар, подъём с земли)."""
        return not self.loop and not self.done

    # ------------------------------------------------------------------
    def move_anim(self, speed, armed=None, aiming=False, walk_clip=None):
        """Клип и темп для движения с данной скоростью.  armed: None, 'pistol' или 'rifle'."""
        if armed == 'rifle':
            name = 'rifle_run' if speed > JOG_FROM else 'rifle_walk'
        elif armed == 'pistol' and aiming and speed <= JOG_FROM:
            name = 'pistol_walk'
        elif speed > SPRINT_FROM:
            name = 'run_f' if self.female else 'sprint'
        elif speed > JOG_FROM:
            name = 'run_f' if self.female else 'jog'
        else:
            name = walk_clip or ('walk_f' if self.female else 'walk')
        r = speed / REF[name]
        self.play(name, True, 0.7 if r < 0.7 else (1.7 if r > 1.7 else r))

    def strike(self, bat, restart):
        """Удар кулаком или битой."""
        if bat:
            self.play('swing', False, 3.2, 0.06, restart)
        else:
            if restart:
                self.punch_n += 1
            self.play('punch_b' if self.punch_n % 2 else 'punch_a', False, 2.6, 0.06, restart)

    # ------------------------------------------------------------------
    def set_weapon(self, wid, kind):
        """Вложить оружие в руку.  kind — 'pistol' (одной рукой) или 'rifle' (двумя)."""
        if self.gun is not None:
            self.gun.removeNode()
            self.gun = None
        self.gun_kind = None
        self._free_arm()
        t = self.models.weapon(wid)
        if t is None:
            return
        self.support = SUPPORT.get(self.models.weapon_name(wid), SUPPORT_ANY)
        grip = self.grips.get(kind)
        if grip is None:
            joint, mat = self.models.hand_matrix(kind)
            hand = self.grips.get('_hand')
            if hand is None:
                hand = self.grips['_hand'] = self.actor.exposeJoint(None, 'modelRoot', joint)
            grip = self.grips[kind] = hand.attachNewNode('grip')
            grip.setMat(mat)
        self.gun = t.copyTo(grip)                   # у шаблона своя текстура, чужая на него не ложится
        self.gun_kind = kind
        if kind == 'rifle' and self._rifle is None:
            if '_left' not in self.grips:
                self.grips['_left'] = self.actor.exposeJoint(None, 'modelRoot', 'middle_01_l')
                self.grips['_clav'] = self.actor.exposeJoint(None, 'modelRoot', 'clavicle_l')
            m = grip.getMat()
            self._rifle = (m.getRow3(3), LVector3(m.getRow3(2)), LMatrix4(m))

    def _aim_long(self):
        """Длинный ствол лежит в двух руках: правая держит рукоять, ствол смотрит на левую ладонь.

        Оружие привязано к правой кисти жёстко, а кисти в каждом клипе стоят друг относительно друга
        по-своему; без этой поправки автомат на бегу и в стойке торчит мимо левой руки."""
        grip = self.grips['rifle']
        o, up0, rest = self._rifle
        if self.cur == SHOULDERED:
            self._shoulder(grip, o)
            return
        self._free_arm()
        if self.cur not in TWO_HANDS:
            grip.setMat(rest)
            return
        d = self.grips['_left'].getPos(self.grips['_hand']) - o
        if d.lengthSquared() < 0.0036:              # ладони сошлись (меньше 6 см): направление ненадёжно
            return
        d.normalize()
        r = d.cross(up0)
        if r.lengthSquared() < 1e-6:
            return
        r.normalize()
        up = r.cross(d)
        grip.setMat(LMatrix4(r.x, r.y, r.z, 0.0, d.x, d.y, d.z, 0.0, up.x, up.y, up.z, 0.0, o.x, o.y, o.z, 1.0))

    def _shoulder(self, grip, o):
        """Стойка прицеливания с длинным стволом.

        В клипе левая рука вытянута вперёд ниже оружия: если вести ствол к ней, он смотрит в землю, если
        держать его ровно — рука висит в воздухе под цевьём.  Поэтому наоборот: ствол ставим по линии
        прицела, а левую руку ведём к цевью — плечо и предплечье поворачиваются так, чтобы запястье
        пришло под точку хвата (обычная задача о двух звеньях).  Всё считается в осях модели."""
        k = self.aim_pitch
        k = AIM_PITCH if k > AIM_PITCH else (-AIM_PITCH if k < -AIM_PITCH else k)
        self._pitch += (k - self._pitch) * 0.35
        p = math.radians(self._pitch)
        f = LVector3(0.0, -math.cos(p), math.sin(p))            # модель смотрит в −Y
        up = LVector3(0.0, math.sin(p), math.cos(p))
        hand = self.grips['_hand'].getMat()                     # правая кисть в осях модели
        g = hand.xformPoint(o)
        inv = LMatrix4(hand)
        inv.invertInPlace()
        grip.setMat(LMatrix4(-1.0, 0.0, 0.0, 0.0, f.x, f.y, f.z, 0.0, up.x, up.y, up.z, 0.0, g.x, g.y, g.z, 1.0) * inv)
        # --- левая рука: запястье чуть позади и ниже точки хвата, ладонь ложится под цевьё
        ik = self._ik
        if ik is None:
            ik = self._ik = (NodePath('upperarm_l'), NodePath('lowerarm_l'))
            self.actor.controlJoint(ik[0], 'modelRoot', 'upperarm_l')
            self.actor.controlJoint(ik[1], 'modelRoot', 'lowerarm_l')
        m1, m2, l1, l2 = self.models.arm_ref()
        sy, sz = self.support
        t = g + f * (sy - 0.05) + up * (sz - 0.025) + LVector3(0.02, 0.0, 0.0)
        clav = self.grips['_clav'].getMat()
        n1 = m1 * clav
        sh = LVector3(n1.getRow3(3))                             # плечевой сустав
        d = t - sh
        dist = d.length()
        if dist < 1e-4:
            return
        d /= dist
        dist = min(dist, (l1 + l2) * 0.998)
        a = (l1 * l1 - l2 * l2 + dist * dist) / (2.0 * dist)
        h = math.sqrt(max(0.0, l1 * l1 - a * a))
        pole = ELBOW - d * ELBOW.dot(d)
        pole.normalize()
        el = sh + d * a + pole * h                              # локоть
        wr = sh + d * dist                                      # запястье
        v0 = n1.xformVec(LVector3(0.0, 0.0, 1.0))               # кости руки идут вдоль своей оси Z
        v1 = el - sh
        v1.normalize()
        n1 = _about(n1, sh, _arc(v0, v1))
        n2 = m2 * n1
        w0 = n2.xformVec(LVector3(0.0, 0.0, 1.0))
        w1 = wr - el
        w1.normalize()
        n2 = _about(n2, el, _arc(w0, w1))
        ci = LMatrix4(clav)
        ci.invertInPlace()
        ni = LMatrix4(n1)
        ni.invertInPlace()
        ik[0].setMat(n1 * ci)
        ik[1].setMat(n2 * ni)

    def ride_arms(self, rel, left, right, mix, twist=0.0, lean=0.0, frame=10):
        """Ездок держится за руль: ладони ложатся на ручки — точки left и right в осях узла rel.

        В клипах посадки кисти стоят в 25 см друг от друга, как на автомобильной баранке, а ручки руля
        у мотоцикла разнесены на 55–75 см и к тому же ходят вместе с вилкой.  Поэтому руки ведём сами: плечо и
        предплечье каждой поворачиваются так, чтобы ладонь пришла на ручку (та же задача о двух звеньях, что
        у левой руки на цевье).  mix — клипы позы посадки: от неё берётся исходное положение рук.

        twist и lean (градусы) — корпус выше поясницы разворачивается вслед за рулём и подаётся вперёд: иначе
        при вывернутом руле до дальней ручки не дотянуться.  Таз и ноги остаются на месте."""
        a = self.actor
        if a is None:
            return
        ref = self.models.rider_ref(mix, frame)
        ik = self._bars
        if ik is None:
            ik = self._bars = {}
            for s in 'lr':
                n1, n2 = NodePath('upperarm_' + s), NodePath('lowerarm_' + s)
                a.controlJoint(n1, 'modelRoot', 'upperarm_' + s)
                a.controlJoint(n2, 'modelRoot', 'lowerarm_' + s)
                ik[s] = (n1, n2)
            ik['spine'] = NodePath('spine_01')
            a.controlJoint(ik['spine'], 'modelRoot', 'spine_01')
        pel, ms = ref['spine']
        b0 = ms * pel
        turn = None
        if twist or lean:
            # модель глядит в −Y: наклон вперёд — поворот вокруг +X, разворот плеч — вокруг вертикали
            sp = LVector3(b0.getRow3(3))
            turn = (LMatrix4.translateMat(-sp) * LMatrix4.rotateMat(lean, LVector3(1.0, 0.0, 0.0)) *
                    LMatrix4.rotateMat(twist, LVector3(0.0, 0.0, 1.0)) * LMatrix4.translateMat(sp))
            b0 = b0 * turn
        pi = LMatrix4(pel)
        pi.invertInPlace()
        ik['spine'].setMat(b0 * pi)
        for s, pt in (('l', left), ('r', right)):
            clav, m1, m2, mh, palm, l1, l2 = ref[s]
            if turn is not None:
                clav = clav * turn
            t = a.getRelativePoint(rel, pt)                     # ручка в осях модели
            b1 = m1 * clav
            sh = LVector3(b1.getRow3(3))                        # плечевой сустав
            b2 = m2 * b1
            off = (mh * b2).xformVec(palm)                      # от запястья до середины ладони
            n1, n2 = b1, b2
            for _ in range(2):                                  # кисть поворачивается вместе с предплечьем
                d = LVector3(t) - off - sh
                dist = d.length()
                if dist < 1e-4:
                    break
                d /= dist
                dist = min(dist, (l1 + l2) * 0.995)
                k = (l1 * l1 - l2 * l2 + dist * dist) / (2.0 * dist)
                h = math.sqrt(max(0.0, l1 * l1 - k * k))
                e = RIDE_ELBOW[s]
                pole = e - d * e.dot(d)
                pole.normalize()
                el = sh + d * k + pole * h                      # локоть
                wr = sh + d * dist                              # запястье
                v0 = LVector3(b2.getRow3(3)) - sh
                v0.normalize()
                v1 = el - sh
                v1.normalize()
                n1 = _about(b1, sh, _arc(v0, v1))
                n2 = m2 * n1
                w0 = LVector3((mh * n2).getRow3(3)) - el
                w0.normalize()
                w1 = wr - el
                w1.normalize()
                n2 = _about(n2, el, _arc(w0, w1))
                off = (mh * n2).xformVec(palm)
            ci = LMatrix4(clav)
            ci.invertInPlace()
            ni = LMatrix4(n1)
            ni.invertInPlace()
            ik[s][0].setMat(n1 * ci)
            ik[s][1].setMat(n2 * ni)

    def ride_legs(self, rel, left, right, mix, toe=(0.0, 1.0, 0.25), spread=0.35, frame=10):
        """Сидящий ставит стопы в точки left и right (лодыжки, в осях узла rel).

        В клипах посадки человек сидит как на стуле: голени уходят вниз на полметра.  Салон машины ниже: пол
        под самым сиденьем, а место для ног — впереди.  Поэтому ноги ведём так же, как руки ездока: бедро и
        голень поворачиваются, чтобы лодыжка пришла в заданную точку, колено уходит вверх и чуть наружу
        (spread), стопа ложится носком по направлению toe (оси rel)."""
        a = self.actor
        if a is None:
            return
        ref = self.models.rider_ref(mix, frame)
        ik = self._legs
        if ik is None:
            ik = self._legs = {}
            for s in 'lr':
                ns = (NodePath('thigh_' + s), NodePath('calf_' + s), NodePath('foot_' + s))
                for n, j in zip(ns, ('thigh_', 'calf_', 'foot_')):
                    a.controlJoint(n, 'modelRoot', j + s)
                ik[s] = ns
        pel = ref['spine'][0]
        tdir = a.getRelativeVector(rel, LVector3(*toe))
        tdir.normalize()
        up = a.getRelativeVector(rel, LVector3(0.0, 0.0, 1.0))
        up.normalize()
        fwd = a.getRelativeVector(rel, LVector3(0.0, 1.0, 0.0))
        fwd.normalize()
        side = fwd.cross(up)                                    # вправо от сидящего (в осях модели)
        for s, pt in (('l', left), ('r', right)):
            m1, m2, mf, toe0, l1, l2 = ref['leg_' + s]
            t = a.getRelativePoint(rel, pt)                     # лодыжка в осях модели
            b1 = m1 * pel
            hip = LVector3(b1.getRow3(3))
            b2 = m2 * b1
            d = LVector3(t) - hip
            dist = d.length()
            if dist < 1e-4:
                continue
            d /= dist
            dist = min(dist, (l1 + l2) * 0.995)
            k = (l1 * l1 - l2 * l2 + dist * dist) / (2.0 * dist)
            h = math.sqrt(max(0.0, l1 * l1 - k * k))
            e = up + side * (spread if s == 'r' else -spread)   # колено: вверх и наружу
            pole = e - d * e.dot(d)
            pole.normalize()
            kn = hip + d * k + pole * h                         # колено
            an = hip + d * dist                                 # лодыжка
            v0 = LVector3(b2.getRow3(3)) - hip
            v0.normalize()
            v1 = kn - hip
            v1.normalize()
            n1 = _about(b1, hip, _arc(v0, v1))
            n2 = m2 * n1
            w0 = LVector3((mf * n2).getRow3(3)) - kn
            w0.normalize()
            w1 = an - kn
            w1.normalize()
            n2 = _about(n2, kn, _arc(w0, w1))
            nf = mf * n2
            # стопа: носок — по направлению toe
            t0 = nf.xformVec(toe0)
            t0.normalize()
            nf = _about(nf, LVector3(nf.getRow3(3)), _arc(t0, tdir))
            pi = LMatrix4(pel)
            pi.invertInPlace()
            i1 = LMatrix4(n1)
            i1.invertInPlace()
            i2 = LMatrix4(n2)
            i2.invertInPlace()
            ik[s][0].setMat(n1 * pi)
            ik[s][1].setMat(n2 * i1)
            ik[s][2].setMat(nf * i2)

    def ride_legs_off(self):
        """Вернуть ноги клипу анимации (седок вышел из машины)."""
        if self._legs is not None:
            self._legs = None
            a = self.actor
            if a is not None:
                for s in 'lr':
                    for j in ('thigh_', 'calf_', 'foot_'):
                        a.releaseJoint('modelRoot', j + s)

    def ride_arms_off(self):
        """Вернуть руки клипу анимации (ездок слез)."""
        if self._bars is not None:
            self._bars = None
            a = self.actor
            if a is not None:
                for s in 'lr':
                    a.releaseJoint('modelRoot', 'upperarm_' + s)
                    a.releaseJoint('modelRoot', 'lowerarm_' + s)
                a.releaseJoint('modelRoot', 'spine_01')

    def _free_arm(self):
        """Вернуть левую руку клипу анимации."""
        if self._ik is not None:
            self._ik = None
            a = self.actor
            if a is not None:
                a.releaseJoint('modelRoot', 'upperarm_l')
                a.releaseJoint('modelRoot', 'lowerarm_l')

    def remove(self):
        self._ik = None
        self._bars = None
        a = self.actor
        if a is not None:
            self.actor = None
            self.ctrls = {}
            self.cur_ctrl = self.prev_ctrl = None
            try:
                a.cleanup()
            except Exception:
                pass
            a.removeNode()
