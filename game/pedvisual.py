# -*- coding: utf-8 -*-
"""Внешний вид персонажа: модель со скелетом, выбор и плавная смена клипов анимации, оружие в руках.

Логика персонажа (ped.py) сообщает только состояние: стоит, идёт, бежит, бьёт, целится, лежит.
Здесь оно превращается в клипы анимации.  Все модели сидят на одном скелете, клипы у них общие.
"""
import random

from panda3d.core import PartBundle, LMatrix4, LVector3

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
        self.gun = None
        self.gun_kind = None
        self._rifle = None          # (точка хвата, «верх») в системе кости правой кисти
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
        t = self.models.weapon(wid)
        if t is None:
            return
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
            m = grip.getMat()
            self._rifle = (m.getRow3(3), LVector3(m.getRow3(2)), LMatrix4(m))

    def _aim_long(self):
        """Длинный ствол лежит в двух руках: правая держит рукоять, ствол смотрит на левую ладонь.

        Оружие привязано к правой кисти жёстко, а кисти в каждом клипе стоят друг относительно друга
        по-своему; без этой поправки автомат на бегу и в стойке торчит мимо левой руки."""
        grip = self.grips['rifle']
        o, up0, rest = self._rifle
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

    def remove(self):
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
