# -*- coding: utf-8 -*-
"""Меню: главное, пауза, настройки, карта, магазин."""
import math

from panda3d.core import CardMaker, TextNode, TransparencyAttrib, PandaNode, NodePath
from direct.gui.OnscreenText import OnscreenText

from .mapinfo import MAP_CX, MAP_CY, MAP_HALF

GOLD = (1.0, 0.82, 0.2, 1.0)
WHITE = (0.92, 0.92, 0.92, 1.0)
GREY = (0.55, 0.55, 0.58, 1.0)
SEL = (1.0, 0.86, 0.3, 1.0)


class Item(object):
    """Пункт меню.  value() — текст справа; change(d) — стрелки влево/вправо; action() — Enter."""

    def __init__(self, label, action=None, value=None, change=None, enabled=True):
        self.label = label
        self.action = action
        self.value = value
        self.change = change
        self.enabled = enabled


class Menu(object):

    def __init__(self, ui, title, items, back=None, x=-0.95, top=0.42, spacing=0.125, scale=0.085, subtitle=None,
                 text=None, wide=False):
        self.ui = ui
        self.title = title
        self.items = items
        self.back = back
        self.x = x
        self.top = top
        self.spacing = spacing
        self.scale = scale
        self.subtitle = subtitle
        self.text = text
        self.wide = wide
        self.text_scale = 0.062
        self.sel = 0
        for i, it in enumerate(items):
            if it.enabled:
                self.sel = i
                break


class MenuUI(object):
    """Отрисовка и управление стеком меню."""

    def __init__(self, game):
        self.game = game
        base = game.base
        self.base = base
        a = game.assets
        self.root = base.aspect2d.attachNewNode(PandaNode('menu'), sort=20)
        cm = CardMaker('dim')
        cm.setFrame(-5, 5, -1.5, 1.5)
        self.dim = base.aspect2d.attachNewNode(cm.generate(), sort=15)
        self.dim.setColor(0, 0, 0, 0.55)
        self.dim.setTransparency(TransparencyAttrib.MAlpha)
        self.dim.hide()
        self.f_title = a.font('DelaGothicOne.ttf', 110, outline=3.0)
        self.f_item = a.font('RussoOne.ttf', 64, outline=2.0)
        self.logo = OnscreenText(text='', parent=self.root, pos=(0, 0.66), scale=0.2, fg=GOLD, font=self.f_title,
                                 align=TextNode.ACenter, mayChange=True)
        self.logo_sub = OnscreenText(text='', parent=self.root, pos=(0, 0.53), scale=0.075, fg=(0.9, 0.3, 0.25, 1),
                                     font=self.f_title, align=TextNode.ACenter, mayChange=True)
        self.title = OnscreenText(text='', parent=self.root, pos=(-0.95, 0.6), scale=0.12, fg=GOLD,
                                  font=self.f_title, align=TextNode.ALeft, mayChange=True)
        self.body = OnscreenText(text='', parent=self.root, pos=(-0.95, 0.42), scale=0.062, fg=WHITE,
                                 font=self.f_item, align=TextNode.ALeft, mayChange=True, wordwrap=32)
        self.hint = OnscreenText(text='', parent=self.root, pos=(0, -0.93), scale=0.045, fg=GREY, font=self.f_item,
                                 align=TextNode.ACenter, mayChange=True)
        self.labels = []
        self.values = []
        for i in range(14):
            self.labels.append(OnscreenText(text='', parent=self.root, pos=(0, 0), scale=0.085, fg=WHITE,
                                            font=self.f_item, align=TextNode.ALeft, mayChange=True))
            self.values.append(OnscreenText(text='', parent=self.root, pos=(0, 0), scale=0.085, fg=WHITE,
                                            font=self.f_item, align=TextNode.ARight, mayChange=True))
        self.stack = []
        self.extra = None           # дополнительный узел (карта)
        self.root.hide()
        self.mouse_pos = None
        self.show_logo = False
        game.inp.listeners.append(self.on_key)

    # ------------------------------------------------------------------
    @property
    def active(self):
        return bool(self.stack)

    def current(self):
        return self.stack[-1] if self.stack else None

    def open(self, menu, replace=False):
        if replace and self.stack:
            self.stack.pop()
        self.stack.append(menu)
        self.refresh()

    def close(self):
        if self.stack:
            self.stack.pop()
        self.refresh()

    def close_all(self):
        self.stack = []
        self.refresh()

    def set_extra(self, node):
        if self.extra is not None:
            self.extra.removeNode()
        self.extra = node

    def refresh(self):
        m = self.current()
        if m is None:
            self.root.hide()
            self.dim.hide()
            self.set_extra(None)
            return
        self.root.show()
        self.dim.show()
        if self.show_logo and len(self.stack) == 1:
            self.logo.setText('DEADLY DISTRICT')
            self.logo_sub.setText('ГИБЛЫЙ РАЙОН')
            self.title.setText('')
        else:
            self.logo.setText('')
            self.logo_sub.setText('')
            self.title.setText(m.title)
        self.body.setText(m.text or '')
        self.body.setScale(m.text_scale)
        self.body.setPos(m.x, m.top + 0.02)
        n_items = len(m.items)
        top = m.top
        if m.text:
            # пункты под текстом
            lines = m.text.count('\n') + 1
            top = m.top - lines * m.text_scale * 1.2 - 0.1
        self._top = top
        vx = 0.95 if not m.wide else 1.15
        for i in range(len(self.labels)):
            lab, val = self.labels[i], self.values[i]
            if i >= n_items:
                lab.setText('')
                val.setText('')
                continue
            it = m.items[i]
            z = top - i * m.spacing
            lab.setPos(m.x, z)
            lab.setScale(m.scale)
            val.setPos(vx, z)
            val.setScale(m.scale)
            sel = (i == m.sel)
            if not it.enabled:
                col = (0.4, 0.4, 0.42, 1)
            elif sel:
                col = SEL
            else:
                col = WHITE
            lab.setFg(col)
            val.setFg(col)
            lab.setText(('› ' if sel else '  ') + it.label)
            if it.value is not None:
                v = it.value()
                if it.change is not None and sel:
                    v = '‹ %s ›' % v
                val.setText(v)
            else:
                val.setText('')
        hint = 'Стрелки или мышь — выбор, Enter — подтвердить'
        if m.back is not None or len(self.stack) > 1:
            hint += ', Esc — назад'
        self.hint.setText(hint if m.subtitle is None else m.subtitle)

    # ------------------------------------------------------------------
    def _move(self, d):
        m = self.current()
        n = len(m.items)
        if n == 0:
            return
        i = m.sel
        for _ in range(n):
            i = (i + d) % n
            if m.items[i].enabled:
                break
        if i != m.sel:
            m.sel = i
            self.game.audio.play('menu_move', 0.6)
            self.refresh()

    def _activate(self, d=0):
        m = self.current()
        if not m.items:
            return
        it = m.items[m.sel]
        if not it.enabled:
            return
        if d != 0 and it.change is not None:
            it.change(d)
            self.game.audio.play('menu_move', 0.6)
            self.refresh()
        elif d == 0:
            if it.action is not None:
                self.game.audio.play('menu_ok', 0.6)
                it.action()
                self.refresh()
            elif it.change is not None:
                it.change(1)
                self.game.audio.play('menu_move', 0.6)
                self.refresh()

    def _back(self):
        m = self.current()
        if m is None:
            return
        if m.back is not None:
            self.game.audio.play('menu_back', 0.6)
            m.back()
            self.refresh()
        elif len(self.stack) > 1:
            self.game.audio.play('menu_back', 0.6)
            self.close()

    def on_key(self, key):
        if not self.stack:
            return
        self.game.inp.pressed.discard(key)
        if key in ('arrow_up', 'w'):
            self._move(-1)
        elif key in ('arrow_down', 's'):
            self._move(1)
        elif key in ('arrow_left', 'a'):
            self._activate(-1)
        elif key in ('arrow_right', 'd'):
            self._activate(1)
        elif key in ('enter', 'space'):
            self._activate(0)
        elif key in ('escape', 'backspace'):
            self._back()
        elif key == 'mouse1':
            if self._hover(True):
                self._activate(0)
        elif key == 'mouse3':
            if self._hover(True):
                self._activate(-1)

    def _hover(self, click=False):
        """Пункт под курсором мыши становится выбранным."""
        m = self.current()
        if m is None:
            return False
        try:
            mw = self.base.mouseWatcherNode
            if not mw.hasMouse():
                return False
            mx = mw.getMouseX() * self.base.getAspectRatio()
            mz = mw.getMouseY()
        except Exception:
            return False
        if not click and self.mouse_pos is not None and abs(mx - self.mouse_pos[0]) < 1e-4 and \
                abs(mz - self.mouse_pos[1]) < 1e-4:
            return False
        self.mouse_pos = (mx, mz)
        for i, it in enumerate(m.items):
            z = self._top - i * m.spacing
            if z - m.spacing * 0.3 <= mz <= z + m.spacing * 0.7 and m.x - 0.05 <= mx <= 1.2:
                if it.enabled:
                    if i != m.sel:
                        m.sel = i
                        self.refresh()
                    return True
        return False

    def update(self, dt):
        if self.stack:
            self._hover()


# ---------------------------------------------------------------------------
def build_map(game, size=0.86):
    """Карта города с метками для меню паузы."""
    w = game.world
    a = game.assets
    root = NodePath('mapview')
    cm = CardMaker('map')
    cm.setFrame(-size, size, -size, size)
    card = root.attachNewNode(cm.generate())
    card.setTexture(a.tex('map', clamp=True, smooth=True))

    def put(tex, x, y, scale=0.03, color=(1, 1, 1, 1), rot=None):
        u = (x - MAP_CX) / MAP_HALF
        v = (y - MAP_CY) / MAP_HALF
        if abs(u) > 1 or abs(v) > 1:
            return None
        c = CardMaker(tex)
        c.setFrame(-1, 1, -1, 1)
        n = root.attachNewNode(c.generate())
        n.setTexture(a.tex(tex, clamp=True))
        n.setTransparency(TransparencyAttrib.MAlpha)
        n.setPos(u * size, 0, v * size)
        n.setScale(scale)
        n.setColorScale(*color)
        if rot is not None:
            n.setR(rot)
        return n

    hud = w.hud
    for b in hud.blips:
        if not b.visible:
            continue
        o = b.obj
        if o is not None and getattr(o, 'removed', False):
            continue
        x, y = hud.blip_pos(b)
        put(b.tex, x, y, 0.028 * b.scale, b.color)
    pl = w.player
    px, py = pl.pos()
    heading = pl.vehicle.yaw if pl.vehicle is not None else pl.ped.yaw
    put('blip_player', px, py, 0.034, (1, 1, 1, 1), 90.0 - math.degrees(heading))
    return root
