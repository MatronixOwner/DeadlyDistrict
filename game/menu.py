# -*- coding: utf-8 -*-
"""Меню: главное, пауза, настройки, карта, магазин.

Строки меню — плашки; выбранная строка светлая с тёмным текстом.  Облик (шрифты и цвета) — в ui.py.
"""
import math

from panda3d.core import CardMaker, TextNode, TransparencyAttrib, PandaNode, NodePath

from . import ui
from .ui import INK, PAPER, MUTE, DIM, ACCENT, rgba
from .mapinfo import MAP_CX, MAP_CY, MAP_HALF

GOLD = ACCENT
WHITE = PAPER
GREY = MUTE
ROWS = 11                   # сколько строк видно сразу; длинный список прокручивается
LEFT = 0.14                 # отступ от левого края экрана
ROW_W = 1.02                # ширина строки обычного меню
ROW_WIDE = 1.46             # ...и широкого (магазин, настройки с длинными значениями)


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
        self.dim = 0.66                 # затемнение игры за меню; у ателье — слабое, машину должно быть видно
        self.on_select = None           # вызывается, когда выбранная строка меняется (предпросмотр)
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
        kit = self.kit = ui.Kit(game.assets)
        self.root = base.aspect2d.attachNewNode(PandaNode('menu'), sort=20)
        cm = CardMaker('dim')
        cm.setFrame(-5, 5, -1.5, 1.5)
        self.dim = base.aspect2d.attachNewNode(cm.generate(), sort=15)
        self.dim.setColor(INK[0], INK[1], INK[2], 0.66)
        self.dim.setTransparency(TransparencyAttrib.MAlpha)
        self.dim.hide()
        self.left = self.root.attachNewNode('left')              # всё меню привязано к левому краю экрана
        self.panel = self.left.attachNewNode('panel')            # плашка под меню поверх игры (пауза, магазины)
        self._panel_w = None
        self.panel.hide()
        # название игры в главном меню: две строки и подпись
        self.logo = kit.label(self.left, '', LEFT, 0.60, 0.21, PAPER, kit.title, 'l', shadow=False)
        self.logo2 = kit.label(self.left, '', LEFT, 0.415, 0.21, ACCENT, kit.title, 'l', shadow=False)
        self.logo_sub = kit.label(self.left, '', LEFT + 0.008, 0.335, 0.040, MUTE, kit.bold, 'l', shadow=False)
        self.title = kit.label(self.left, '', LEFT, 0.66, 0.115, PAPER, kit.title, 'l', shadow=False)
        self.rule = kit.card(self.left, LEFT, LEFT + 0.15, 0.610, 0.618, ACCENT, 1.0)
        self.body = kit.label(self.left, '', LEFT, 0.42, 0.05, PAPER, kit.text, 'l', wrap=34, shadow=False)
        self.hint = kit.label(self.left, '', LEFT, -0.915, 0.034, MUTE, kit.text, 'l', shadow=False)
        self.more_up = kit.label(self.left, u'\u2191', 0, 0, 0.040, MUTE, kit.bold, 'c', shadow=False)
        self.more_dn = kit.label(self.left, u'\u2193', 0, 0, 0.040, MUTE, kit.bold, 'c', shadow=False)
        self._first = 0
        self.rows = []
        self.labels = []
        self.values = []
        for i in range(ROWS):
            row = kit.card(self.left, 0.0, 1.0, 0.0, 1.0, INK, 0.0, 'row')
            self.rows.append(row)
            self.labels.append(kit.label(self.left, '', 0, 0, 0.06, PAPER, kit.bold, 'l', shadow=False))
            self.values.append(kit.label(self.left, '', 0, 0, 0.06, PAPER, kit.text, 'r', shadow=False))
        self.stack = []
        self.extra = None           # дополнительный узел (карта)
        self.root.hide()
        self.mouse_pos = None
        self.show_logo = False
        self.aspect = 0.0
        self._top = 0.0
        self._row_h = 0.1
        self._row_w = ROW_W
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
        self.dim.setColor(INK[0], INK[1], INK[2], m.dim)
        asp = self.base.getAspectRatio()
        self.aspect = asp
        self.left.setX(-asp)
        # плашка под столбцом меню; своей ширины она собирается заново: её края не растягиваются
        pw = LEFT + (ROW_WIDE if m.wide else ROW_W) + 0.10
        if pw != self._panel_w:
            self._panel_w = pw
            self.panel.getChildren().detach()
            self.kit.panel(self.panel, -0.3, pw, -1.6, 1.6, alpha=0.90)
        self.panel.show()
        logo = self.show_logo and len(self.stack) == 1
        if logo:
            self.logo.setText('DEADLY')
            self.logo2.setText('DISTRICT')
            self.logo_sub.setText(ui.spaced(u'ГИБЛЫЙ РАЙОН'))
            self.title.setText('')
            self.rule.hide()
        else:
            self.logo.setText('')
            self.logo2.setText('')
            self.logo_sub.setText('')
            self.title.setText((m.title or '').upper())
            if m.title:
                self.rule.show()
            else:
                self.rule.hide()
        top = 0.18 if logo else 0.50
        self.body.setText(m.text or '')
        self.body.setScale(m.text_scale * 0.86)
        self.body.setPos(LEFT, top)
        if m.text:
            # пункты под текстом
            tn = self.body.textNode
            top -= max(1, tn.getNumRows()) * tn.getLineHeight() * m.text_scale * 0.86 + 0.07
        n_items = len(m.items)
        # длинный список прокручивается: видно ROWS строк, выбранная всегда среди них
        shown = min(n_items, ROWS)
        first = getattr(m, '_first', 0)
        if m.sel < first:
            first = m.sel
        elif m.sel >= first + shown:
            first = m.sel - shown + 1
        first = max(0, min(first, n_items - shown))
        m._first = first
        self._first = first
        row_h = min(0.118, m.spacing * 0.94)
        if shown > 1:
            row_h = min(row_h, (top + 0.78) / shown)
        size = min(0.060, row_h * 0.52)
        width = ROW_WIDE if m.wide else ROW_W
        self._top = top
        self._row_h = row_h
        self._row_w = width
        self._shown = shown
        for k in range(ROWS):
            row, lab, val = self.rows[k], self.labels[k], self.values[k]
            i = first + k
            if k >= shown:
                row.hide()
                lab.setText('')
                val.setText('')
                continue
            it = m.items[i]
            z1 = top - k * row_h
            z0 = z1 - row_h + 0.010
            sel = (i == m.sel)
            row.show()
            row.setPos(LEFT, 0, z0)
            row.setScale(width, 1, z1 - z0)
            if sel and it.enabled:
                row.setColor(PAPER[0], PAPER[1], PAPER[2], 0.96)
                col = INK
            else:
                row.setColor(INK[0], INK[1], INK[2], 0.58)
                col = PAPER if it.enabled else DIM
            base_z = z0 + (z1 - z0) * 0.5 - size * 0.30
            lab.setPos(LEFT + 0.04, base_z)
            lab.setScale(size)
            lab.setFg(col)
            lab.setText(it.label)
            val.setPos(LEFT + width - 0.04, base_z)
            val.setScale(size)
            val.setFg(col if sel else (MUTE if it.enabled else DIM))
            if it.value is not None:
                v = it.value()
                if it.change is not None and sel:
                    v = u'‹  %s  ›' % v
                val.setText(v)
            else:
                val.setText('')
        # стрелки «выше есть ещё» и «ниже есть ещё»
        self.more_up.setPos(LEFT + width + 0.045, top - 0.045)
        self.more_dn.setPos(LEFT + width + 0.045, top - shown * row_h + 0.03)
        if first > 0:
            self.more_up.show()
        else:
            self.more_up.hide()
        if first + shown < n_items:
            self.more_dn.show()
        else:
            self.more_dn.hide()
        hint = u'↑↓  выбор      Enter  подтвердить'
        if m.back is not None or len(self.stack) > 1:
            hint += u'      Esc  назад'
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
            if m.on_select is not None:
                m.on_select(i)
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
        x0 = -self.aspect + LEFT
        if not (x0 <= mx <= x0 + self._row_w):
            return False
        for k in range(getattr(self, '_shown', 0)):
            i = self._first + k
            it = m.items[i]
            z1 = self._top - k * self._row_h
            if z1 - self._row_h <= mz <= z1:
                if it.enabled:
                    if i != m.sel:
                        m.sel = i
                        if m.on_select is not None:
                            m.on_select(i)
                        self.refresh()
                    return True
        return False

    def update(self, dt):
        if self.stack:
            if abs(self.base.getAspectRatio() - self.aspect) > 1e-3:
                self.refresh()                       # окно изменило форму — раскладываем заново
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
    px, py = w.map_pos()
    heading = pl.vehicle.yaw if pl.vehicle is not None else pl.ped.yaw
    put('blip_player', px, py, 0.034, (1, 1, 1, 1), 90.0 - math.degrees(heading))
    return root
