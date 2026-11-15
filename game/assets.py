# -*- coding: utf-8 -*-
"""Загрузка текстур, шрифтов и настройка состояний отрисовки."""
import os

from panda3d.core import (Filename, Texture, SamplerState, TransparencyAttrib, ColorBlendAttrib,
                          DepthOffsetAttrib, CullFaceAttrib, TextureStage, getModelPath, LColor,
                          DynamicTextFont, TextNode, CardMaker, NodePath)

from . import settings


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
        soft = smooth or self.smooth_textures
        t.setMagfilter(SamplerState.FTLinear if soft else SamplerState.FTNearest)
        t.setMinfilter(SamplerState.FTLinearMipmapLinear)
        t.setAnisotropicDegree(16)

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
