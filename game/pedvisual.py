# -*- coding: utf-8 -*-
"""Внешний вид персонажа: модель со скелетом, выбор и плавная смена клипов анимации, оружие в руке.

Логика персонажа (ped.py) сообщает только состояние: стоит, идёт, бежит, бьёт, целится, лежит.
Здесь оно превращается в клипы анимации.
"""
from panda3d.core import PartBundle

from .defs import W_BAT
from .models import CHAR_HEIGHT, PED_HEIGHT

# скорость, при которой ступни клипа не «скользят» по земле (м/с при росте модели из набора)
WALK_REF = {'m': 1.44, 'f': 1.44}
RUN_REF = {'m': 3.6, 'f': 3.1}
RUN_FROM = 2.6              # с какой скорости персонаж переходит на бег

FADE = 0.16                 # время плавного перехода между клипами, с


class PedVisual(object):

    def __init__(self, models, parent, look, kind):
        self.models = models
        key = getattr(look, 'model', None) or models.pick_char(look, kind)
        if key not in models.meta['chars']:
            key = models.pick_char(look, kind)
        self.key = key
        self.sex = key[0]
        a = models.actor(key)
        self.actor = a
        s = PED_HEIGHT / CHAR_HEIGHT * look.scale
        k = 0.97 + (look.fat - 1.0) * 0.30          # полнота — немного шире в плечах
        self.scale = s
        self.root = parent.attachNewNode('m')
        a.reparentTo(self.root)
        a.setH(180.0)                               # модели набора смотрят в -Y, персонажи игры — в +Y
        a.setScale(s * k, s * k, s)
        models.paint_char(a, key, look)
        # вдали скелет пересчитывается реже: глазу незаметно, а процессору легче
        a.setLODAnimation(90.0, 16.0, 0.22)
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
        self.walk_ref = WALK_REF[self.sex] * s
        self.run_ref = RUN_REF[self.sex] * s
        self.grip = None
        self.gun = None
        self.play('Idle', True, 1.0, 0.0)

    # ------------------------------------------------------------------
    def _ctrl(self, name):
        c = self.ctrls.get(name)
        if c is None:
            c = self.actor.getAnimControl(name)
            if c is None:
                return None
            self.ctrls[name] = c
        return c

    def play(self, name, loop=True, rate=1.0, fade=FADE, restart=False):
        """Включить клип.  Повторный вызов с тем же именем только подправляет темп."""
        if name == self.cur and not restart:
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
        else:
            if c is not None and c is not n:
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
        self.time = 0.0
        self.nframes = max(1, n.getNumFrames())
        self.fps = n.getFrameRate()
        self.frame = 0
        self.done = False
        n.pose(0)

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

    # ------------------------------------------------------------------
    def move_anim(self, speed, armed_aim=False):
        """Клип и темп для движения с данной скоростью."""
        if speed > RUN_FROM:
            r = speed / self.run_ref
            self.play('Run_Shoot' if armed_aim else 'Run', True, 0.8 if r < 0.8 else (1.7 if r > 1.7 else r))
        else:
            r = speed / self.walk_ref
            self.play('Walk', True, 0.6 if r < 0.6 else (1.9 if r > 1.9 else r))

    def strike(self, weapon_id, restart):
        """Удар кулаком, битой или бросок."""
        if weapon_id == W_BAT:
            self.play('Sword_Slash', False, 2.4, 0.06, restart)
        else:
            self.play('Punch_Right', False, 2.3, 0.06, restart)

    # ------------------------------------------------------------------
    def set_weapon(self, wid):
        if self.gun is not None:
            self.gun.removeNode()
            self.gun = None
        t = self.models.weapon(wid)
        if t is None:
            return
        if self.grip is None:
            joint, mat = self.models.hand_matrix(self.sex)
            hand = self.actor.exposeJoint(None, 'modelRoot', joint)
            self.grip = hand.attachNewNode('grip')
            self.grip.setMat(mat)
        self.gun = t.copyTo(self.grip)

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
