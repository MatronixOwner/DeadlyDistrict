# -*- coding: utf-8 -*-
"""Ввод: клавиатура и мышь.

Буквенные клавиши слушаются и по обычным, и по «сырым» (raw-) событиям,
поэтому управление работает при любой раскладке (в том числе русской).
"""
from panda3d.core import ModifierButtons, WindowProperties

LETTERS = 'wasdqerfhtcmpgbxzvlnyk'
SPECIAL = ['space', 'shift', 'lshift', 'rshift', 'control', 'lcontrol', 'rcontrol', 'alt', 'lalt', 'enter',
           'escape', 'tab', 'backspace', 'arrow_up', 'arrow_down', 'arrow_left', 'arrow_right', 'mouse1',
           'mouse2', 'mouse3', 'wheel_up', 'wheel_down', 'f1', 'f2', 'f3', 'f5', 'f9', 'f10', 'f11', 'f12',
           '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', 'delete', 'insert', 'home', 'end', 'page_up',
           'page_down', '-', '=', ',', '.']
ALIAS = {'lshift': 'shift', 'rshift': 'shift', 'lcontrol': 'control', 'rcontrol': 'control', 'lalt': 'alt'}


class Input(object):

    def __init__(self, base):
        self.base = base
        self.down = set()
        self.pressed = set()
        self.any_key = False
        self.mouse_dx = 0.0
        self.mouse_dy = 0.0
        self.captured = False
        self._skip = 2
        self.listeners = []           # функции f(key) для меню
        try:
            base.mouseWatcherNode.setModifierButtons(ModifierButtons())
            base.buttonThrowers[0].node().setModifierButtons(ModifierButtons())
        except Exception:
            pass
        for ch in LETTERS:
            base.accept(ch, self._dn, [ch])
            base.accept(ch + '-up', self._up, [ch])
            base.accept('raw-' + ch, self._dn, [ch])
            base.accept('raw-' + ch + '-up', self._up, [ch])
        for k in SPECIAL:
            name = ALIAS.get(k, k)
            base.accept(k, self._dn, [name])
            base.accept(k + '-up', self._up, [name])
            if k.startswith('arrow') or k in ('enter', 'backspace'):
                base.accept(k + '-repeat', self._repeat, [name])

    # ------------------------------------------------------------------
    def _dn(self, key):
        if key not in self.down:
            self.down.add(key)
            self.pressed.add(key)
            self.any_key = True
            for f in list(self.listeners):
                f(key)
        elif key.startswith('wheel'):
            self.pressed.add(key)

    def _repeat(self, key):
        for f in list(self.listeners):
            f(key)

    def _up(self, key):
        self.down.discard(key)

    def held(self, key):
        return key in self.down

    def hit(self, key):
        """Нажата ли клавиша в этом кадре (однократно)."""
        if key in self.pressed:
            self.pressed.discard(key)
            return True
        return False

    def axis(self, neg, pos, neg2=None, pos2=None):
        d = self.down
        v = 0.0
        if pos in d or (pos2 is not None and pos2 in d):
            v += 1.0
        if neg in d or (neg2 is not None and neg2 in d):
            v -= 1.0
        return v

    def end_frame(self):
        self.pressed.clear()
        self.any_key = False
        # колесо мыши не имеет события «отпускания»
        self.down.discard('wheel_up')
        self.down.discard('wheel_down')

    def clear(self):
        self.down.clear()
        self.pressed.clear()

    # ------------------------------------------------------------------
    def capture_mouse(self, on):
        """Захватить мышь для управления камерой (курсор скрыт и держится в центре окна)."""
        win = self.base.win
        if win is None:
            return
        self.captured = on
        self._skip = 2
        try:
            props = WindowProperties()
            props.setCursorHidden(on)
            try:
                props.setMouseMode(WindowProperties.M_confined if on else WindowProperties.M_absolute)
            except Exception:
                pass
            win.requestProperties(props)
        except Exception:
            pass

    def poll_mouse(self):
        self.mouse_dx = self.mouse_dy = 0.0
        if not self.captured:
            return
        win = self.base.win
        try:
            if not win.getProperties().getForeground():
                self._skip = 2
                return
            cx = win.getXSize() // 2
            cy = win.getYSize() // 2
            md = win.getPointer(0)
            if not md.getInWindow():
                self._skip = 2
            x, y = md.getX(), md.getY()
            if self._skip > 0:
                self._skip -= 1
            else:
                self.mouse_dx = x - cx
                self.mouse_dy = y - cy
            if x != cx or y != cy:
                win.movePointer(0, cx, cy)
        except Exception:
            pass
