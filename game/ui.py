# -*- coding: utf-8 -*-
"""Общий облик интерфейса: цвета, шрифты и простые детали — плашка, надпись, полоска, «клавиша».

Правила, по которым собраны экран игры и меню:
  * два шрифта: Inter — текст и числа, Oswald — заголовки прописными; рукописный Caveat — только
    название задания;
  * надписи без обводки: читаемость дают тёмная плашка под текстом или мягкая тень;
  * цвета: почти чёрный, тёплый белый, серый для второстепенного и один акцент — жёлтый; зелёный и
    синий остаются только за деньгами, здоровьем и бронёй;
  * выбранная строка меню — светлая плашка с тёмным текстом, без стрелок и свечения;
  * большие плашки (меню, рамка мини-карты, полоса сообщений, экран загрузки) — не ровная заливка, а «шлифованный
    металл» в духе меню игр для PlayStation: текстуры набора Free PSX UI (ROHHSA).  Края плашки при любом её
    размере остаются одной толщины: картинка режется на девять частей, растягивается только середина.
"""
from panda3d.core import CardMaker, TextNode, TransparencyAttrib, NodePath, LColor, LTexCoord
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

# текстуры плашек (assets/tex/ui_*.png, 512x128): расцветки набора Free PSX UI
SKIN_PANEL = 'ui_panel'                     # стальной синий: меню, рамка мини-карты, экран загрузки
SKIN_BAND = 'ui_band'                       # тёмно-бордовый: полоса больших сообщений
SKIN_PLATE = 'ui_plate'                     # серо-оливковый: подсказки
SKIN_ALERT = 'ui_alert'                     # красный: «потрачено», «арестован»
# края картинки, которые не растягиваются: доли ширины и высоты (слева/справа, снизу, сверху)
PANEL_EDGE_U = 0.060
PANEL_EDGE_V0 = 0.20
PANEL_EDGE_V1 = 0.22


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

    def panel(self, parent, x0, x1, z0, z1, skin=SKIN_PANEL, alpha=1.0, edge=0.045, turn=False, tint=1.0,
              name='panel'):
        """Плашка с текстурой: края толщиной edge не растягиваются, середина тянется под размер.

        turn — картинка повёрнута на четверть оборота (для высоких плашек: «шлифовка» идёт сверху вниз, светлая
        кромка — по правому краю).  Возвращает узел; прозрачность можно менять через setAlphaScale."""
        tex = self.assets.tex(skin, clamp=True, smooth=True)
        root = parent.attachNewNode(name)
        k = tex.getYSize() / float(max(1, tex.getXSize()))          # 128 / 512
        eu, ev0, ev1 = PANEL_EDGE_U, PANEL_EDGE_V0, PANEL_EDGE_V1
        U = (0.0, eu, 1.0 - eu, 1.0)
        V = (0.0, ev0, 1.0 - ev1, 1.0)
        # толщина краёв на экране: у длинной стороны картинки — edge, у короткой — в ту же меру точек
        ea = edge
        eb0, eb1 = edge * ev0 * k / eu, edge * ev1 * k / eu
        if turn:
            xs = self._cuts(x0, x1, eb0, eb1)
            zs = self._cuts(z0, z1, ea, ea)
        else:
            xs = self._cuts(x0, x1, ea, ea)
            zs = self._cuts(z0, z1, eb0, eb1)
        for i in range(3):
            for j in range(3):
                if xs[i + 1] - xs[i] < 1e-6 or zs[j + 1] - zs[j] < 1e-6:
                    continue
                cm = CardMaker('p')
                cm.setFrame(xs[i], xs[i + 1], zs[j], zs[j + 1])
                if turn:
                    cm.setUvRange(LTexCoord(U[j], V[i]), LTexCoord(U[j], V[i + 1]),
                                  LTexCoord(U[j + 1], V[i + 1]), LTexCoord(U[j + 1], V[i]))
                else:
                    cm.setUvRange(LTexCoord(U[i], V[j]), LTexCoord(U[i + 1], V[j]),
                                  LTexCoord(U[i + 1], V[j + 1]), LTexCoord(U[i], V[j + 1]))
                root.attachNewNode(cm.generate())
        root.flattenStrong()
        root.setTexture(tex)
        root.setColor(tint, tint, tint, alpha)
        root.setTransparency(TransparencyAttrib.MAlpha)
        return root

    @staticmethod
    def _cuts(a, b, e0, e1):
        """Четыре границы вдоль стороны: край, начало и конец середины, край.  Узкой плашке края ужимаются."""
        if e0 + e1 > (b - a):
            s = (b - a) / (e0 + e1)
            e0, e1 = e0 * s, e1 * s
        return (a, a + e0, b - e1, b)

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
