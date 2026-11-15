# -*- coding: utf-8 -*-
"""Общий облик интерфейса: цвета, шрифты и простые детали — плашка, надпись, полоска, «клавиша».

Правила, по которым собраны экран игры и меню:
  * два шрифта: Inter — текст и числа, Oswald — заголовки прописными; рукописный Caveat — только
    название задания;
  * надписи без обводки: читаемость дают тёмная плашка под текстом или мягкая тень;
  * цвета: почти чёрный, тёплый белый, серый для второстепенного и один акцент — жёлтый; зелёный и
    синий остаются только за деньгами, здоровьем и бронёй;
  * выбранная строка меню — светлая плашка с тёмным текстом, без стрелок и свечения.
"""
from panda3d.core import CardMaker, TextNode, TransparencyAttrib, NodePath, LColor
from direct.gui.OnscreenText import OnscreenText

INK = (0.055, 0.06, 0.07, 1.0)              # фон плашек и тёмный текст
PAPER = (0.94, 0.93, 0.90, 1.0)             # основной светлый
MUTE = (0.62, 0.64, 0.67, 1.0)              # второстепенный текст
DIM = (0.40, 0.42, 0.45, 1.0)               # недоступное
ACCENT = (0.96, 0.74, 0.18, 1.0)            # единственный акцент
CASH = (0.52, 0.82, 0.48, 1.0)
HEALTH = (0.42, 0.74, 0.38, 1.0)
ARMOR = (0.34, 0.60, 0.88, 1.0)
DANGER = (0.86, 0.26, 0.22, 1.0)
COOL = (0.42, 0.66, 0.92, 1.0)
SHADOW = (0.0, 0.0, 0.0, 0.72)

# старые названия цветов, которыми пользуются сценарии заданий
GOLD = ACCENT
WHITE = PAPER


def rgba(c, a=None):
    return (c[0], c[1], c[2], c[3] if a is None else a)


class Kit(object):
    """Шрифты и фабрика деталей интерфейса."""

    def __init__(self, assets):
        self.assets = assets
        f = assets.font
        self.text = f('Inter-Medium.ttf', 60)
        self.bold = f('Inter-Bold.ttf', 60)
        self.head = f('Oswald-Medium.ttf', 80)
        self.title = f('Oswald-Bold.ttf', 110)
        self.script = f('Caveat-Bold.ttf', 110)

    # ------------------------------------------------------------------
    def card(self, parent, x0, x1, z0, z1, color=INK, alpha=None, name='card'):
        """Одноцветный прямоугольник."""
        cm = CardMaker(name)
        cm.setFrame(x0, x1, z0, z1)
        np_ = parent.attachNewNode(cm.generate())
        np_.setColor(*rgba(color, alpha))
        np_.setTransparency(TransparencyAttrib.MAlpha)
        return np_

    def image(self, parent, tex, x, z, sx, sz=None, color=None, smooth=True):
        cm = CardMaker(tex)
        cm.setFrame(-1, 1, -1, 1)
        np_ = parent.attachNewNode(cm.generate())
        np_.setTexture(self.assets.tex(tex, clamp=True, smooth=smooth))
        np_.setTransparency(TransparencyAttrib.MAlpha)
        np_.setPos(x, 0, z)
        np_.setScale(sx, 1, sz if sz is not None else sx)
        if color is not None:
            np_.setColorScale(*color)
        return np_

    def label(self, parent, text='', x=0.0, z=0.0, size=0.05, color=PAPER, font=None, align='l', wrap=None,
              shadow=True):
        """Надпись.  shadow — мягкая тень (для текста поверх игры); на плашках она не нужна."""
        al = {'l': TextNode.ALeft, 'r': TextNode.ARight, 'c': TextNode.ACenter}[align]
        kw = dict(text=text, parent=parent, pos=(x, z), scale=size, fg=color, font=font or self.text, align=al,
                  mayChange=True)
        if wrap is not None:
            kw['wordwrap'] = wrap
        if shadow:
            kw['shadow'] = SHADOW
            kw['shadowOffset'] = (0.045, 0.045)
        return OnscreenText(**kw)

    def bar(self, parent, x, z, w, h, color, back=0.55):
        """Полоска-индикатор.  Возвращает узел заполнения: его масштаб по X — доля от 0 до 1."""
        self.card(parent, x, x + w, z, z + h, INK, back)
        root = parent.attachNewNode('bar')
        root.setPos(x, 0, z)
        self.card(root, 0.0, w, 0.0, h, color, 1.0)
        return root


def spaced(text, gap=u'\u2009'):
    """Разрядка прописных: тонкие пробелы между буквами (для коротких подписей)."""
    return gap.join(text)


def money(n):
    """12500 -> «$12 500» (с неразрывным пробелом между разрядами)."""
    s = '%d' % abs(int(n))
    parts = []
    while len(s) > 3:
        parts.insert(0, s[-3:])
        s = s[:-3]
    parts.insert(0, s)
    return ('-' if n < 0 else '') + '$' + u'\u00a0'.join(parts)
