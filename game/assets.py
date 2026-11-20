# -*- coding: utf-8 -*-
"""Загрузка текстур, шрифтов и настройка состояний отрисовки."""
import os

from panda3d.core import (Filename, Texture, SamplerState, TransparencyAttrib, ColorBlendAttrib,
                          DepthOffsetAttrib, CullFaceAttrib, TextureStage, getModelPath, LColor,
                          DynamicTextFont, TextNode, CardMaker, NodePath, LVecBase4)

from . import settings
from .masks import NO_SHADOW


# то, что под дождём становится мокрым и блестит (шейдер сцены, gfx.py)
# покрытия, которые лежат на земле: тени от них не бывает (а на них — ложится)
FLAT_TEX = frozenset(('road2', 'road4', 'road2_cap', 'road4_cap', 'asphalt', 'sidewalk', 'grass', 'pavers', 'dirt',
                      'sand', 'parking', 'manhole', 'water', 'lightpool', 'shadow'))
# прозрачное, светящееся, наклейки: тени не отбрасывают
NO_SHADOW_MODES = frozenset(('blend', 'blend_c', 'add', 'add_c', 'addc', 'decal', 'decal_c', 'glass', 'unlit',
                             'unlit_c', 'under'))
WET = frozenset(('asphalt', 'road2', 'road4', 'road2_cap', 'road4_cap', 'sidewalk', 'pavers', 'parking', 'concrete',
                 'manhole', 'roof_metal', 'planks'))


PUSH = 4.0e-4                               # шаг «утапливания» в буфере глубины (см. depth_push)


def depth_push(n):
    """Состояние «этот слой — позади соседних»: n ступеней вглубь буфера глубины.

    Слои земли лежат друг на друге вплотную (рельеф под асфальтом, перекрёсток под концами дорог), и вдали
    буфер глубины их уже не различает — они «мерцают» один сквозь другой.  Здесь слой сдвигается не числом
    (glPolygonOffset: там сдвиг зависит от наклона грани, и на пологом берегу сквозь песок проступала бы вода,
    а программный рендерер понимает его по-своему), а сжатием диапазона глубины: слой уходит вдоль луча зрения
    на долю расстояния (0,4 мм на метр за ступень).  В единицах буфера это 2300 / расстояние в метрах — то есть
    больше единицы до двух с лишним километров, а по высоте — всё равно что опустить слой на высоту камеры,
    умноженную на ту же долю: с земли — на миллиметр, с вертолёта — на ладонь."""
    return DepthOffsetAttrib.make(0, PUSH * n, 1.0)


class Assets(object):

    def __init__(self, loader):
        self.loader = loader
        self.root = settings.find_root()
        try:
            getModelPath().appendDirectory(Filename.fromOsSpecific(self.root))
        except Exception:
            pass
        self._tex = {}
        self._fonts = {}
        self.missing = []
        self.smooth_textures = False        # настройка «Текстуры: чёткие / сглаженные»
        self.aniso = 16                     # настройка «Чёткость текстур вдали»: степень анизотропной фильтрации
        self._filtered = []                 # (текстура, всегда ли сглаживать) — для смены настройки на лету

    # ------------------------------------------------------------------
    def path(self, *parts):
        return Filename.fromOsSpecific(os.path.join(self.root, 'assets', *parts))

    def tex(self, name, clamp=False, smooth=False):
        """Текстура assets/tex/<name>.png (пиксельная фильтрация по умолчанию)."""
        key = (name, clamp, smooth)
        t = self._tex.get(key)
        if t is not None:
            return t
        try:
            t = self.loader.loadTexture(self.path('tex', name + '.png'))
        except Exception:
            t = None
        if t is None:
            self.missing.append(name)
            t = Texture(name)
            t.setup2dTexture(2, 2, Texture.TUnsignedByte, Texture.FRgba)
            t.setRamImage(bytes([255, 0, 255, 255] * 4))
        t = t.makeCopy() if any(k[0] == name for k in self._tex) else t
        self.setup_filter(t, smooth)
        if clamp:
            t.setWrapU(SamplerState.WMClamp)
            t.setWrapV(SamplerState.WMClamp)
        else:
            t.setWrapU(SamplerState.WMRepeat)
            t.setWrapV(SamplerState.WMRepeat)
        self._tex[key] = t
        return t

    def setup_filter(self, t, smooth=False):
        """Фильтрация текстуры.  Вблизи — чёткие пиксели («ретро») либо сглаживание, вдали — мип-уровни
        с анизотропной фильтрацией, чтобы картинка не рябила и не превращалась в «мыло»."""
        self._filtered.append((t, smooth))
        self._filter(t, smooth)

    def _filter(self, t, smooth):
        soft = smooth or self.smooth_textures
        t.setMagfilter(SamplerState.FTLinear if soft else SamplerState.FTNearest)
        t.setMinfilter(SamplerState.FTLinearMipmapLinear)
        t.setAnisotropicDegree(self.aniso)

    def set_aniso(self, degree):
        """Настройка «Чёткость текстур вдали» (анизотропная фильтрация) — применяется сразу."""
        self.aniso = int(degree)
        for (t, smooth) in self._filtered:
            self._filter(t, smooth)

    def set_smooth(self, on):
        """Настройка «Текстуры: чёткие / сглаженные» — применяется сразу ко всем загруженным текстурам."""
        self.smooth_textures = bool(on)
        for (t, smooth) in self._filtered:
            self._filter(t, smooth)

    def font(self, name, pixels=48, outline=0.0):
        key = (name, pixels, outline)
        f = self._fonts.get(key)
        if f is None:
            try:
                f = DynamicTextFont(self.path('fonts', name))
                f.setPixelsPerUnit(pixels)
                f.setPageSize(512, 512)
                f.setTextureMargin(3)
                f.setMinfilter(SamplerState.FTLinear)
                f.setMagfilter(SamplerState.FTLinear)
                if outline > 0:
                    f.setOutline(LColor(0, 0, 0, 1), outline, 0.4)
                if not f.isValid():
                    f = TextNode.getDefaultFont()
            except Exception:
                f = TextNode.getDefaultFont()
            self._fonts[key] = f
        return f

    # ------------------------------------------------------------------
    def apply_state(self, np_, key):
        """state_fn для MeshBuilder.build().

        key:  None                — без текстуры (цвет вершин)
              'name'              — непрозрачная текстура
              ('name', mode)      — режимы: 'a' альфа-тест, 'blend' прозрачность,
                                    'add' свечение, 'decal' наклейка на земле,
                                    'unlit' без освещения, 'glass'
        """
        if key is None:
            return
        mode = None
        if isinstance(key, tuple):
            name, mode = key
        else:
            name = key
        if name is not None:
            clamp = mode in ('add_c', 'decal_c', 'blend_c', 'unlit_c')
            np_.setTexture(self.tex(name, clamp=clamp, smooth=(mode in ('add', 'add_c', 'decal_c'))))
            if name == 'shadow':
                # пятно-тень под машиной, человеком, деревом: когда от солнца ложатся настоящие тени,
                # шейдер сцены его гасит (gfx.py; без шейдеров эта пометка ничего не значит)
                np_.setShaderInput('u_mat', LVecBase4(0.0, 0.0, 0.0, 1.0))
            elif name == 'lightpool':
                np_.setShaderInput('u_mat', LVecBase4(0.0, 0.0, 1.0, 0.0))      # пятно света под фонарём
            elif name in WET:
                np_.setShaderInput('u_mat', LVecBase4(0.0, 1.0, 0.0, 0.0))      # под дождём блестит
        if name in FLAT_TEX or mode in NO_SHADOW_MODES:
            np_.hide(NO_SHADOW)             # в карты теней не попадает (см. masks.py)
        if mode is None:
            return
        if mode == 'a':
            np_.setTransparency(TransparencyAttrib.MBinary)
            np_.setTwoSided(True)
        elif mode == 'under':
            # подложка: перекрёсток под концами дорог, обочина под трассой.  Лежит вплотную под другим
            # покрытием, и вдали точности буфера глубины не хватает, чтобы их различить, — они «мерцают»
            np_.setAttrib(depth_push(1))
        elif mode in ('blend', 'blend_c'):
            np_.setTransparency(TransparencyAttrib.MAlpha)
            np_.setDepthWrite(False)
            np_.setBin('transparent', 10)
        elif mode in ('add', 'add_c'):
            np_.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha,
                                                ColorBlendAttrib.OOne))
            np_.setDepthWrite(False)
            np_.setLightOff(1)
            np_.setFogOff(1)
            np_.setBin('fixed', 20)
        elif mode == 'addc':
            # аддитивно по цвету (ночные окна: чёрное = прозрачное)
            np_.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OOne,
                                                ColorBlendAttrib.OOne))
            np_.setDepthWrite(False)
            np_.setLightOff(1)
            np_.setFogOff(1)
            np_.setAttrib(DepthOffsetAttrib.make(1))
            np_.setBin('fixed', 5)
        elif mode in ('decal', 'decal_c'):
            np_.setTransparency(TransparencyAttrib.MAlpha)
            np_.setDepthWrite(False)
            np_.setAttrib(DepthOffsetAttrib.make(1))
            np_.setBin('fixed', 2)
        elif mode in ('unlit', 'unlit_c'):
            np_.setLightOff(1)
        elif mode == 'glass':
            np_.setTransparency(TransparencyAttrib.MAlpha)
            np_.setDepthWrite(False)
            np_.setBin('transparent', 5)
