# -*- coding: utf-8 -*-
"""Загрузка текстур, шрифтов и настройка состояний отрисовки."""
import os

from panda3d.core import (Filename, Texture, SamplerState, TransparencyAttrib, ColorBlendAttrib,
                          DepthOffsetAttrib, CullFaceAttrib, TextureStage, getModelPath, LColor,
                          DynamicTextFont, TextNode, CardMaker, NodePath, LVecBase4)

from . import settings


# то, что под дождём становится мокрым и блестит (шейдер сцены, gfx.py)
WET = frozenset(('asphalt', 'road2', 'road4', 'road2_cap', 'road4_cap', 'sidewalk', 'pavers', 'parking', 'concrete',
                 'manhole', 'roof_metal', 'planks'))


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
        t.setAnisotropicDegree(16)

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
        if mode is None:
            return
        if mode == 'a':
            np_.setTransparency(TransparencyAttrib.MBinary)
            np_.setTwoSided(True)
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
