# -*- coding: utf-8 -*-
"""Графика: уровни качества, шейдерное освещение, тени от солнца, обработка кадра.

Игра умеет рисовать двумя способами.

* Без шейдеров («Минимум»): свет считает сама видеокарта по вершинам, как в играх начала 2000-х.  Так игра
  шла всегда; этот способ работает на любом железе, в том числе на запасном программном рендерере.
* С шейдерами («Среднее», «Ультра»): свет считается в каждой точке экрана, от солнца ложатся настоящие
  тени, машины блестят, ночью светят фонари и фары, а готовый кадр проходит обработку — свечение ярких
  мест, затенение в углах, цветокоррекция, сглаживание краёв.

Что именно включено, решают настройки (settings.py, ключи gfx_*).  Набор «Минимум / Среднее / Ультра»
просто записывает в них готовые значения; «Пользовательские» — игрок меняет их сам.

Если шейдеры на этой видеокарте не собрались, игра сама возвращается к рисованию без них.
"""
import math
import re
import time

from panda3d.core import (Shader, Texture, SamplerState, FrameBufferProperties, WindowProperties, GraphicsPipe,
                          GraphicsOutput, OrthographicLens, Camera, NodePath, LMatrix4, LVecBase4,
                          LVector3, ColorWriteAttrib, CullFaceAttrib, DepthOffsetAttrib, ClockObject,
                          PTA_LVecBase4f, PTA_LVecBase3f, PTA_LMatrix4f, PTA_float, LVecBase3f, LVecBase4f)

from . import shaders as S
from .masks import SHADOW_NEAR, SHADOW_FAR
from .settings import DRAW_DIST

PRESET_MIN, PRESET_MED, PRESET_ULTRA, PRESET_CUSTOM = 0, 1, 2, 3
PRESET_NAMES = ('Минимум', 'Среднее', 'Ультра', 'Пользовательские')
PRESET_HINTS = (
    'Для старых и очень слабых компьютеров: без шейдеров, теней и сглаживания, близкая прорисовка.',
    'Для обычных и слабых компьютеров: тени от солнца, блеск машин, свет фонарей, сглаживание FXAA.',
    'Вся красота: мягкие дальние тени, свечение, затенение в углах, вода с бликами, дальняя прорисовка.',
    'Каждая настройка выбрана вручную — в «Подробных настройках».',
)
# настройки, которые задаёт набор качества
PRESETS = {
    PRESET_MIN: dict(gfx_shaders=False, gfx_shadows=0, gfx_bloom=False, gfx_ssao=False, gfx_gloss=False,
                     gfx_lights=0, gfx_water=False, gfx_aniso=0, msaa=0, draw_distance=0),
    PRESET_MED: dict(gfx_shaders=True, gfx_shadows=2, gfx_bloom=False, gfx_ssao=False, gfx_gloss=True,
                     gfx_lights=1, gfx_water=True, gfx_aniso=2, msaa=1, draw_distance=1),
    PRESET_ULTRA: dict(gfx_shaders=True, gfx_shadows=3, gfx_bloom=True, gfx_ssao=True, gfx_gloss=True,
                       gfx_lights=2, gfx_water=True, gfx_aniso=2, msaa=4, draw_distance=2),
}
GFX_KEYS = tuple(sorted(PRESETS[PRESET_ULTRA]))

SHADOW_NAMES = ('Выкл', 'Низкие', 'Средние', 'Высокие')
# тени: размер карты, сколько метров она накрывает, число выборок на точку, дальний каскад (размер, метры)
SHADOW_LEVELS = (
    None,
    dict(size=1024, span=64.0, pcf=1, far=None),
    dict(size=2048, span=88.0, pcf=4, far=None),
    dict(size=4096, span=110.0, pcf=16, far=(2048, 540.0)),
)
ANISO_NAMES = ('Низкая', 'Средняя', 'Высокая')
ANISO_LEVELS = (2, 8, 16)                   # степень анизотропной фильтрации текстур
LIGHT_NAMES = ('Выкл', 'Немного', 'Много')
LIGHT_COUNTS = (0, 6, 12)
AA_LEVELS = (0, 1, 2, 4, 8)                 # 1 — FXAA (по готовой картинке), 2–8 — MSAA
FPS_LIMITS = (60, 120, 180, 240)

LIGHT_CELL = 40.0                           # клетка сетки огней, м
LIGHT_REACH = 70.0                          # дальше этого фонари не зажигаются
SHADOW_DEPTH = 500.0                        # на таком расстоянии от середины карты теней стоит «солнце»
SUN_GAIN = 1.32                             # с шейдерами солнце ярче, а рассеянный свет слабее и холоднее:
AMB_GAIN = 0.84                             # тени читаются, как в ясный день
# Первый запуск: набор качества выбран по названию видеокарты, то есть наугад, — поэтому он проверяется
# делом.  Несколько секунд считаем кадры; если их меньше нужного, набор понижается на ступень.
TUNE_SKIP = 3.0                             # секунд после смены набора не считаем: шейдеры и текстуры ещё грузятся
TUNE_TIME = 4.0                             # столько секунд длится замер
# сколько кадров в секунду нужно, чтобы набор остался.  На «Минимуме» упрощать графику уже некуда —
# там убавляется движение на улицах: его считает процессор, и на старом компьютере мешает именно оно
TUNE_FPS = {PRESET_ULTRA: 45.0, PRESET_MED: 27.0, PRESET_MIN: 24.0}
SHADOW_DARK = 0.84                          # насколько тень гасит прямой свет солнца (1 — полностью)
LOOK = (1.0, 1.12, 1.07, 1.0)               # выдержка, насыщенность, контраст, тонирование


# «освещённого круга нет»: радиусы отрицательные, поэтому нарисованные пятна света видны везде
NO_FOCUS = LVecBase4f(0, 0, -2, -1)

FAR_EVERY = 2.0                             # дальняя карта перерисовывается не реже чем раз в столько секунд…
FAR_SHIFT = 0.10                            # …и сразу, если взгляд ушёл дальше этой доли её размера


def aa_name(n):
    n = int(n)
    return 'Выкл' if n <= 0 else ('FXAA' if n == 1 else 'MSAA %d×' % n)


def set_preset(settings, preset, desktop=(0, 0)):
    """Записать в настройки набор качества."""
    preset = int(preset)
    settings.set('gfx_preset', preset)
    vals = PRESETS.get(preset)
    if vals is None:
        return
    for k, v in vals.items():
        settings.set(k, v)
    if preset == PRESET_ULTRA and desktop[0] * desktop[1] > 2560 * 1440:
        # на экранах 4K точек вчетверо больше, чем в Full HD: MSAA там обходится дорого, а заметно мало
        settings.set('msaa', 1)


def detect_preset(settings):
    """Какому набору соответствуют настройки сейчас (или «Пользовательские»)."""
    for p in (PRESET_MIN, PRESET_MED, PRESET_ULTRA):
        vals = PRESETS[p]
        if all(settings.get(k) == v or (k == 'msaa' and p == PRESET_ULTRA and settings.get(k) == 1)
               for k, v in vals.items()):
            return p
    return PRESET_CUSTOM


def guess_preset(renderer, supported=True):
    """Набор качества для первого запуска — по названию видеокарты."""
    if not supported:
        return PRESET_MIN
    n = renderer.lower()
    if any(k in n for k in ('llvmpipe', 'softpipe', 'swiftshader', 'swrast', 'gdi generic', 'microsoft basic')):
        return PRESET_MIN                   # программный рендерер: видеокарты, считай, нет
    strong = re.search(r'rtx|titan|gtx\s*(9[5-9]0|1\d\d\d)|rx\s*(4[6-9]0|5[5-9]0|5[5-7]00|[6-9]\d00)|arc\S*\s*[ab]\d', n)
    if strong and 'vega' not in n:
        return PRESET_ULTRA
    return PRESET_MED


def guess_fps_limit(refresh):
    """Ограничение кадров для первого запуска: наименьшее, что не ниже частоты монитора."""
    for n in FPS_LIMITS:
        if n >= refresh - 1:
            return n
    return FPS_LIMITS[-1]


def tune_state():
    """Замер кадров после первого запуска (Gfx._autotune): skip — сколько секунд ещё не считаем, t и n — время
    и число сосчитанных кадров, slow — долгих кадров подряд, hit — долгих кадров за замер, last — время
    прошлого кадра."""
    return dict(skip=TUNE_SKIP, t=0.0, n=0, last=None, slow=0, hit=0)


def grade_color(c):
    """То же, что tonemap + grade в шейдере, — для цвета фона (он рисуется без шейдера)."""
    c = [v * LOOK[0] for v in c[:3]]
    c = [min(v, 0.72) + 0.28 * (1.0 - math.exp(-max(v - 0.72, 0.0) / 0.28)) for v in c]
    l = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    c = [l + (v - l) * LOOK[1] for v in c]
    c = [(v - 0.5) * LOOK[2] + 0.5 for v in c]
    c = [v + (l - 0.5) * t * LOOK[3] for v, t in zip(c, (0.035, 0.008, -0.040))]
    return tuple(max(0.0, min(1.0, v)) for v in c)


def _norm(v):
    l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if l < 1e-6:
        return (0.0, 0.0, 1.0)
    return (v[0] / l, v[1] / l, v[2] / l)


class _Cascade(object):
    """Одна карта теней: сцена глазами солнца."""

    def __init__(self, gfx, idx, size, span, mask):
        base = gfx.base
        self.size = size
        self.span = span
        self.aim = None                     # куда карта наведена: середина (до выравнивания по точкам)…
        self.sun = None                     # …и направление на солнце
        self.age = 1e9                      # сколько секунд назад её рисовали
        fb = FrameBufferProperties()
        fb.setRgbColor(False)
        fb.setRgbaBits(0, 0, 0, 0)
        fb.setDepthBits(24)
        fb.setMultisamples(0)
        fb.setBackBuffers(0)
        # Порядок отрисовки (-2000) — раньше буфера сцены, который заводит обработка кадра (у него -1000).
        # Иначе сцена рисовалась бы по карте теней прошлого кадра, а матрицу брала бы от нынешнего: на ходу
        # все тени отставали бы на шаг камеры и дрожали
        self.buf = base.graphicsEngine.makeOutput(
            base.pipe, 'shadow%d' % idx, -2000 + idx, fb, WindowProperties.size(size, size),
            GraphicsPipe.BFRefuseWindow, base.win.getGsg(), base.win)
        if self.buf is None:
            raise RuntimeError('shadow buffer')
        tex = self.tex = Texture('shadow%d' % idx)
        tex.setMinfilter(SamplerState.FTShadow)
        tex.setMagfilter(SamplerState.FTShadow)
        tex.setWrapU(SamplerState.WMBorderColor)
        tex.setWrapV(SamplerState.WMBorderColor)
        tex.setBorderColor(LVecBase4(1, 1, 1, 1))
        self.buf.addRenderTexture(tex, GraphicsOutput.RTMBindOrCopy, GraphicsOutput.RTPDepth)
        self.buf.setClearColorActive(False)
        self.buf.setClearDepthActive(True)
        lens = self.lens = OrthographicLens()
        lens.setFilmSize(span, span)
        lens.setNearFar(1.0, SHADOW_DEPTH * 2.0)
        cam = Camera('shadow%d' % idx)
        cam.setLens(lens)
        cam.setScene(base.render)
        cam.setCameraMask(mask)
        st = NodePath('st')
        st.setShader(gfx.shadow_shader, 1000)
        st.setAttrib(ColorWriteAttrib.make(ColorWriteAttrib.COff), 1000)
        st.setAttrib(CullFaceAttrib.make(CullFaceAttrib.MCullNone), 1000)
        st.setAttrib(DepthOffsetAttrib.make(-2), 1000)
        cam.setInitialState(st.getState())
        self.np = base.render.attachNewNode(cam)
        dr = self.buf.makeDisplayRegion()
        dr.setCamera(self.np)
        dr.disableClears()
        self.mat = LMatrix4()
        self.texel = span / float(size)

    def fit(self, base, cam_pos, fwd, ground_z, sun):
        """Поставить карту так, чтобы она накрывала то, что видит игрок."""
        span = self.span
        t = span * 0.40
        if fwd[2] < -0.02:
            t = min(t, max(0.0, (cam_pos[2] - ground_z) / -fwd[2]))
        cx, cy = cam_pos[0] + fwd[0] * t, cam_pos[1] + fwd[1] * t
        cz = ground_z
        self.aim = (cx, cy)
        self.sun = (sun[0], sun[1], sun[2])
        self.age = 0.0
        np_ = self.np
        D = SHADOW_DEPTH
        np_.setPos(cx + sun[0] * D, cy + sun[1] * D, cz + sun[2] * D)
        np_.lookAt(cx, cy, cz)
        # сдвиг — целыми точками карты: иначе при каждом шаге камеры края теней «дрожат»
        render = base.render
        rt = render.getRelativeVector(np_, LVector3(1, 0, 0))
        up = render.getRelativeVector(np_, LVector3(0, 0, 1))
        tx = self.texel
        a = cx * rt[0] + cy * rt[1] + cz * rt[2]
        b = cx * up[0] + cy * up[1] + cz * up[2]
        da = round(a / tx) * tx - a
        db = round(b / tx) * tx - b
        cx += rt[0] * da + up[0] * db
        cy += rt[1] * da + up[1] * db
        cz += rt[2] * da + up[2] * db
        np_.setPos(cx + sun[0] * D, cy + sun[1] * D, cz + sun[2] * D)
        m = LMatrix4(render.getMat(np_))
        m *= self.lens.getProjectionMat()
        m *= LMatrix4.scaleMat(0.5)
        m *= LMatrix4.translateMat(0.5, 0.5, 0.5)
        self.mat = m

    def stale(self, cam_pos, fwd, sun):
        """Пора ли перерисовать дальнюю карту: взгляд ушёл, солнце сдвинулось или просто давно не рисовали."""
        if self.aim is None or self.age >= FAR_EVERY:
            return True
        t = self.span * 0.40
        dx = cam_pos[0] + fwd[0] * t - self.aim[0]
        dy = cam_pos[1] + fwd[1] * t - self.aim[1]
        lim = self.span * FAR_SHIFT
        if dx * dx + dy * dy > lim * lim:
            return True
        return self.sun[0] * sun[0] + self.sun[1] * sun[1] + self.sun[2] * sun[2] < 0.99996      # полградуса

    def destroy(self, base):
        try:
            base.graphicsEngine.removeWindow(self.buf)
        except Exception:
            pass
        self.np.removeNode()


class Gfx(object):

    def __init__(self, game, first=False):
        self.game = game
        self.base = game.base
        self.settings = game.settings
        self.supported = False              # видеокарта умеет шейдеры
        self.can_shadow = False
        self.failed = False                 # шейдеры не собрались: рисуем без них
        self.fps_applied = 0                # действующее ограничение кадров (0 — его нет)
        self.active = False                 # шейдерное освещение сейчас включено
        self.cfg = None                     # с чем собрано сейчас (см. _want)
        self.scene_shader = None
        self.shadow_shader = None
        self.water_shader = None
        self.cascades = []
        self.fm = None                      # обработка кадра (FilterManager)
        self.post = {}
        self._shaders = []
        self._post_shaders = []
        self._no_post = False               # обработку кадра эта видеокарта не собрала
        self._no_water = False              # то же — шейдер воды
        self._bg = None                     # цвет фона: (каким его задало небо, каким сделали мы)
        self._watch = 0
        self.time = 0.0
        self.lights = []                    # огни мира: (x, y, z, радиус, r, g, b)
        self._light_grid = {}
        self._lpos = self._lcol = self._ldir = None
        self.renderer = ''
        self._lamps = []                    # отобранные фонари: [огонь, яркость]
        self._lamps_t = 0.0
        self._lamps_r = LIGHT_REACH
        self._focus_r = LIGHT_REACH
        self._lamp_k = {}                   # фонари, которые сейчас светят: id -> [огонь, яркость]
        self._u = {}                        # входы шейдера, которые правятся на месте (см. _setup)
        self._lfocus = NO_FOCUS
        self._sh_sun = None                 # направление на солнце, под которое нарисованы карты теней
        self._clock = time.perf_counter
        self._tune = None                   # замер кадров после первого запуска (см. _autotune)
        self._load_lights()
        self._probe()
        s = self.settings
        if first and int(s.get('gfx_cfg')) < 1:
            # первый запуск этой версии: набор качества подбирается по видеокарте…
            self.first_run()
            s.set('gfx_cfg', 1)
            s.save()
        elif not self.supported and not game.headless and s.get('gfx_shaders'):
            # шейдеров на этом компьютере нет (сменили видеокарту или драйвер): записываем «Минимум»,
            # чтобы сглаживание и прочее дальше настраивались по-старому
            set_preset(s, PRESET_MIN)
            s.save()
        if first and int(s.get('gfx_cfg')) == 1:
            # …а потом проверяется замером (если игру закрыли раньше, чем он кончился, — при следующем запуске)
            self._tune = tune_state()
        self.apply()
        self.apply_fps_limit()

    # ------------------------------------------------------------------
    def _probe(self):
        base = self.base
        try:
            gsg = base.win.getGsg()
            self.renderer = '%s / %s' % (gsg.getDriverVendor(), gsg.getDriverRenderer())
            self.supported = bool(base.pipe.getInterfaceName() == 'OpenGL' and gsg.getSupportsBasicShaders()
                                  and gsg.getSupportsGlsl())
            self.can_shadow = bool(self.supported and gsg.getSupportsDepthTexture()
                                   and gsg.getSupportsShadowFilter())
        except Exception:
            self.supported = self.can_shadow = False

    def first_run(self):
        """Первый запуск (или обновление со старой версии): подобрать набор качества под видеокарту."""
        s = self.settings
        p = guess_preset(self.renderer, self.supported)
        set_preset(s, p, self.game.desktop())
        try:
            di = self.base.pipe.getDisplayInformation()
            i = di.getCurrentDisplayModeIndex()
            hz = int(di.getDisplayModeRefreshRate(i)) if i >= 0 else 0
            if hz >= 50:
                s.set('fps_limit', guess_fps_limit(hz))
        except Exception:
            pass
        return p

    def _want(self):
        s = self.settings
        on = bool(s.get('gfx_shaders')) and self.supported and not self.failed
        aa = int(s.get('msaa'))
        sh = int(max(0, min(3, int(s.get('gfx_shadows'))))) if (on and self.can_shadow) else 0
        post_ok = on and not self._no_post
        bloom = post_ok and bool(s.get('gfx_bloom'))
        ssao = post_ok and bool(s.get('gfx_ssao')) and self.can_shadow
        fxaa = post_ok and aa == 1
        msaa = aa if (post_ok and aa >= 2) else 0
        # сцена рисуется в отдельный буфер, если кадр нужно обработать или сгладить (MSAA — свойство буфера)
        post = bloom or ssao or fxaa or msaa > 0
        # запас яркости (16 бит на цвет) и сборка кадра нужны только свечению и затенению; одному
        # сглаживанию хватает обычного буфера — яркость тогда сжимает сам шейдер сцены
        return dict(on=on, shadows=sh, bloom=bloom, ssao=ssao, fxaa=fxaa, post=post, msaa=msaa,
                    hdr=bloom or ssao,
                    gloss=on and bool(s.get('gfx_gloss')),
                    lights=LIGHT_COUNTS[int(max(0, min(2, int(s.get('gfx_lights')))))] if on else 0,
                    water=on and bool(s.get('gfx_water')) and not self._no_water)

    def apply(self, user=False):
        """Привести графику в соответствие с настройками (можно звать на лету, из меню).
        user — настройку поменял сам игрок: автоматический подбор набора больше не нужен."""
        if user:
            self._tune_done()
        self.apply_draw_distance()
        self.apply_textures()
        want = self._want()
        if want == self.cfg:
            return
        self._teardown()
        self.cfg = want
        if not want['on']:
            return
        try:
            self._setup(want)
        except Exception:
            self.game.report_error()
            self._fail()

    def apply_draw_distance(self):
        w = self.game.world
        sky = getattr(w, 'sky', None) if w is not None else None
        if sky is None:
            return
        from .sky import set_lens_range
        dd = DRAW_DIST[int(max(0, min(2, int(self.settings.get('draw_distance')))))]
        if (sky.fog_start, sky.far) != dd:
            sky.fog_start, sky.far = dd
            set_lens_range(self.base, sky.far)
            sky._apply(0.0)

    def apply_textures(self):
        deg = ANISO_LEVELS[int(max(0, min(2, int(self.settings.get('gfx_aniso')))))]
        assets = self.game.assets
        if assets.aniso != deg:
            assets.set_aniso(deg)

    def apply_fps_limit(self):
        """Ограничение частоты кадров.  Без окна (проверки) кадры идут как можно быстрее."""
        if self.game.headless:
            return
        try:
            n = int(self.settings.get('fps_limit'))
            if n not in FPS_LIMITS:
                n = FPS_LIMITS[0]
            clock = ClockObject.getGlobalClock()
            hz = self._refresh()
            if self.game._boot[1] and hz >= 50 and n >= hz - 1:
                # Синхронизация с экраном и так не даёт кадрам идти чаще экрана.  Второй ограничитель на ту же
                # частоту поверх неё только сбивал бы шаг: кадр то успевает к обновлению экрана, то нет
                clock.setMode(ClockObject.MNormal)
            else:
                clock.setMode(ClockObject.MLimited)
                clock.setFrameRate(float(n))
            self.fps_applied = n
        except Exception:
            pass

    def _refresh(self):
        """Частота обновления экрана, Гц (0 — неизвестна)."""
        try:
            di = self.base.pipe.getDisplayInformation()
            i = di.getCurrentDisplayModeIndex()
            return int(di.getDisplayModeRefreshRate(i)) if i >= 0 else 0
        except Exception:
            return 0

    # ------------------------------------------------------------------
    def _make(self, vert, frag, **defs):
        sh = Shader.make(Shader.SL_GLSL, S.source(vert, **defs), S.source(frag, **defs))
        self._shaders.append(sh)
        return sh

    def _setup(self, c):
        base = self.base
        render = base.render
        w = self.game.world
        lv = SHADOW_LEVELS[c['shadows']]
        defs = dict(SHADOWS=1 if lv else 0, CASCADES=2 if (lv and lv['far']) else 1, PCF=lv['pcf'] if lv else 1,
                    LIGHTS=c['lights'], GLOSS=1 if c['gloss'] else 0, HDR=1 if c['hdr'] else 0)
        self.scene_shader = self._make(S.SCENE_VERT, S.SCENE_FRAG, **defs)
        if lv:
            self.shadow_shader = self._make(S.SHADOW_VERT, S.SHADOW_FRAG)
            self.cascades = [_Cascade(self, 0, lv['size'], lv['span'], SHADOW_NEAR)]
            if lv['far']:
                self.cascades.append(_Cascade(self, 1, lv['far'][0], lv['far'][1], SHADOW_FAR))
        n = max(1, c['lights'])
        self._lpos = PTA_LVecBase4f.emptyArray(n)
        self._lcol = PTA_LVecBase4f.emptyArray(n)
        self._ldir = PTA_LVecBase4f.emptyArray(n)
        # Входы шейдера, которые меняются каждый кадр, заведены массивами из одного элемента и дальше
        # правятся на месте.  Если вместо этого каждый кадр звать render.setShaderInput, у корня сцены каждый
        # кадр будет новое состояние — и движок заново соберёт состояние каждого предмета в кадре (их
        # сотни): это время процессора, потраченное впустую
        u = self._u = {}
        for name in ('u_cam', 'u_sun_dir', 'u_sun_col', 'u_fill_dir', 'u_fill_col', 'u_amb_sky', 'u_amb_gnd',
                     'u_sky_zen', 'u_sky_hor'):
            u[name] = PTA_LVecBase3f.emptyArray(1)
        for name in ('u_env', 'u_fog', 'u_fog_rng', 'u_look', 'u_lfocus', 'u_sh_par', 'u_sh_geo'):
            u[name] = PTA_LVecBase4f.emptyArray(1)
        for name in ('u_time', 'u_lnum'):
            u[name] = PTA_float.emptyArray(1)
        for name in ('u_sh_mat0', 'u_sh_mat1'):
            u[name] = PTA_LMatrix4f.emptyArray(1)
        u['u_lfocus'][0] = NO_FOCUS
        u['u_look'][0] = LVecBase4f(*LOOK)
        inputs = dict(u)
        inputs.update(u_mat=LVecBase4(0, 0, 0, 0), u_emit=1.0, u_lpos=self._lpos, u_lcol=self._lcol, u_ldir=self._ldir)
        if self.cascades:
            inputs['u_sh_tex0'] = self.cascades[0].tex
            inputs['u_sh_tex1'] = self.cascades[-1].tex
        render.setShaderInputs(**inputs)
        self._lamp_k = {}
        self._sh_sun = None
        sky = getattr(w, 'sky', None) if w is not None else None
        if sky is not None:
            sky.sun_card.setShaderInput('u_emit', 3.0)      # солнце ярче белого: со свечением вокруг него ореол
        self._frame_inputs(0.0)
        render.setShader(self.scene_shader)
        if c['water'] and w is not None and getattr(w.citymesh, 'water', None) is not None:
            self.water_shader = self._make(S.WATER_VERT, S.WATER_FRAG, HDR=defs['HDR'])
            w.citymesh.water.setShader(self.water_shader, 10)
        if c['post']:
            n0 = len(self._shaders)
            ok = self._setup_post(c)
            self._post_shaders = self._shaders[n0:] if ok else []
            if not ok:
                # обработку кадра видеокарта не потянула: остаётся свет и тени, яркость сжимает шейдер сцены
                self._drop_post()
                c['post'] = c['bloom'] = c['ssao'] = c['fxaa'] = c['hdr'] = False
                c['msaa'] = 0
                defs['HDR'] = 0
                self.scene_shader = self._make(S.SCENE_VERT, S.SCENE_FRAG, **defs)
                render.setShader(self.scene_shader)
                if self.water_shader is not None:
                    self.water_shader = self._make(S.WATER_VERT, S.WATER_FRAG, HDR=0)
                    w.citymesh.water.setShader(self.water_shader, 10)
        self.active = True
        self._watch = 4

    def _teardown(self):
        base = self.base
        self._drop_post()
        for cs in self.cascades:
            cs.destroy(base)
        self.cascades = []
        w = self.game.world
        if w is not None and getattr(w, 'citymesh', None) is not None and getattr(w.citymesh, 'water', None) is not None:
            w.citymesh.water.clearShader()
        if self.active or self.scene_shader is not None:
            base.render.clearShader()
        self.scene_shader = self.shadow_shader = self.water_shader = None
        self._shaders = []
        self._post_shaders = []
        if self._bg is not None:
            try:
                if (base.win.getClearColor() - self._bg[1]).lengthSquared() < 1e-9:
                    base.win.setClearColor(self._bg[0])         # фон — как его задало небо
            except Exception:
                pass
            self._bg = None
        self.active = False
        self._watch = 0

    def _fail(self):
        """Шейдеры не работают на этой видеокарте: дальше — без них."""
        self.failed = True
        self._teardown()
        self.cfg = self._want()
        if not self.game.headless:
            set_preset(self.settings, PRESET_MIN)
            self.settings.save()
        self._hint('Видеокарта не справилась с шейдерами: графика переключена на «Минимум».')

    # ------------------------------------------------------------------
    # обработка кадра
    # ------------------------------------------------------------------
    def _tex(self, name, linear=True):
        t = Texture(name)
        f = SamplerState.FTLinear if linear else SamplerState.FTNearest
        t.setMinfilter(f)
        t.setMagfilter(f)
        t.setWrapU(SamplerState.WMClamp)
        t.setWrapV(SamplerState.WMClamp)
        return t

    def _setup_post(self, c):
        from direct.filter.FilterManager import FilterManager
        base = self.base
        fm = self.fm = FilterManager(base.win, base.cam)
        p = self.post = dict(stages=[])
        scene = self._tex('dd-scene')
        depth = self._tex('dd-depth', linear=False) if c['ssao'] else None
        final = None
        # буфер сцены: яркость с запасом (16 бит на цвет) и сглаживание; не вышло — пробуем без сглаживания
        hdr = c['hdr']
        for ms in ([int(c['msaa']), 0] if c['msaa'] else [0]):
            fb = FrameBufferProperties()
            if hdr:
                fb.setFloatColor(True)
                fb.setRgbaBits(16, 16, 16, 16)
            else:
                fb.setRgbaBits(8, 8, 8, 8)
            fb.setDepthBits(24)
            fb.setMultisamples(ms)
            final = fm.renderSceneInto(colortex=scene, depthtex=depth, fbprops=fb)
            if final is not None:
                c['msaa'] = ms
                break
        if final is None:
            return False
        p['scene_buf'] = fm.buffers[0]
        hdr = FrameBufferProperties()
        hdr.setFloatColor(True)
        hdr.setRgbaBits(16, 16, 16, 16)
        hdr.setMultisamples(0)
        ldr = FrameBufferProperties()
        ldr.setRgbaBits(8, 8, 8, 8)
        ldr.setMultisamples(0)
        post_vert = S.POST_VERT

        def stage(name, frag, div, props, src, kind, **defs):
            tex = self._tex('dd-' + name)
            q = fm.renderQuadInto('dd-' + name, div=div, colortex=tex, fbprops=props)
            if q is None:
                raise RuntimeError('post stage ' + name)
            q.setShader(self._make(post_vert, frag, **defs))
            q.setShaderInput('u_src', src)
            q.setShaderInput('u_px', LVecBase4(0, 0, 0, 0))
            p['stages'].append((q, kind, div))
            return tex, q

        if not hdr:
            # Ни свечения, ни затенения: яркость уже сжал шейдер сцены, и кадр готов.  Остаётся сгладить
            # края (или просто вывести картинку, если сглаживал буфер) и затемнить углы — один проход
            if c['fxaa']:
                final.setShader(self._make(post_vert, S.FXAA_FRAG, VIGNETTE=1))
            else:
                final.setShader(self._make(post_vert, S.COPY_FRAG))
            final.setShaderInput('u_src', scene)
            final.setShaderInput('u_px', LVecBase4(0, 0, 0, 0))
            final.setShaderInput('u_fx', LVecBase4(0.5, 0.22, 0, 0))
            p['stages'].append((final, 'full', 1))
            return True
        try:
            comp_in = dict(u_scene=scene)
            if c['bloom']:
                b0, _ = stage('bright', S.BRIGHT_FRAG, 4, hdr, scene, 'bright')
                b1, _ = stage('blur-h', S.BLUR_FRAG, 4, hdr, b0, 'h')
                b2, _ = stage('blur-v', S.BLUR_FRAG, 4, hdr, b1, 'v')
                b3, _ = stage('wide-h', S.BLUR_FRAG, 16, hdr, b2, 'h')
                b4, _ = stage('wide-v', S.BLUR_FRAG, 16, hdr, b3, 'v')
                comp_in['u_bloom0'] = b2
                comp_in['u_bloom1'] = b4
            if c['ssao']:
                a0, q = stage('ssao', S.SSAO_FRAG, 2, ldr, depth, 'ssao', SSAO_TAPS=12)
                q.setShaderInput('u_depth', depth)
                q.setShaderInput('u_proj', LVecBase4(1, 100, 1, 1))
                p['ssao_quad'] = q
                a1, _ = stage('ao-blur', S.AOBLUR_FRAG, 2, ldr, a0, 'ao')
                comp_in['u_ao'] = a1
        except RuntimeError:
            return False
        cdefs = dict(BLOOM=1 if c['bloom'] else 0, SSAO=1 if c['ssao'] else 0)
        comp = self._make(post_vert, S.COMPOSITE_FRAG, **cdefs)
        if c['fxaa']:
            tex = self._tex('dd-ldr')
            cq = fm.renderQuadInto('dd-composite', colortex=tex, fbprops=ldr)
            if cq is None:
                return False
            final.setShader(self._make(post_vert, S.FXAA_FRAG, VIGNETTE=0))
            final.setShaderInput('u_src', tex)
            final.setShaderInput('u_px', LVecBase4(0, 0, 0, 0))
            p['stages'].append((final, 'full', 1))
        else:
            cq = final
        cq.setShader(comp)
        for k, v in comp_in.items():
            cq.setShaderInput(k, v)
        cq.setShaderInput('u_look', LVecBase4(*LOOK))
        cq.setShaderInput('u_fx', LVecBase4(0.5, 0.22, 0, 0))
        p['comp'] = cq
        return True

    def _drop_post(self):
        if self.fm is not None:
            try:
                self.fm.cleanup()
                self.fm.ignoreAll()
            except Exception:
                pass
            self.fm = None
        self.post = {}

    # ------------------------------------------------------------------
    # каждый кадр
    # ------------------------------------------------------------------
    def update(self, dt):
        if self._tune is not None:
            self._autotune()
        if not self.active:
            return
        if self.game.state in ('play', 'menu'):
            self.time += dt                 # на паузе вода и лужи замирают вместе с миром
        self._watch -= 1
        if self._watch <= 0:
            self._watch = 45
            if self._check():
                return
        self._frame_inputs(dt)

    def _check(self):
        """Все ли шейдеры собрались.  Видеокарта собирает шейдер, когда впервые им рисует, — поэтому
        проверка идёт всё время, а не один раз.  True — графику пришлось перестроить."""
        bad = [sh for sh in self._shaders if sh.getErrorFlag()]
        if not bad:
            return False
        extra = [sh for sh in bad if sh is self.water_shader or sh in self._post_shaders]
        if len(extra) < len(bad):
            self._fail()                    # не собрался сам шейдер сцены или теней
            return True
        # не собрались только вода или обработка кадра: выключаем их, свет и тени остаются
        if self.water_shader in bad:
            self._no_water = True
        if any(sh in self._post_shaders for sh in bad):
            self._no_post = True
        self.cfg = None
        self.apply()
        self._hint('Часть эффектов эта видеокарта не поддерживает: они выключены.')
        return True

    def _tune_done(self):
        self._tune = None
        s = self.settings
        if int(s.get('gfx_cfg')) < 2:
            s.set('gfx_cfg', 2)
            if not self.game.headless:
                s.save()

    def _autotune(self):
        """Замер кадров после первого запуска: мало кадров — набор качества понижается на ступень."""
        tn = self._tune
        game = self.game
        now = self._clock()
        last, tn['last'] = tn['last'], now
        if last is None:
            return
        d = now - last
        ok = game.state in ('menu', 'play')
        if ok and not game.headless:
            try:
                ok = bool(self.base.win.getProperties().getForeground())    # свёрнутое окно рисуется кое-как
            except Exception:
                pass
        s = self.settings
        p = int(s.get('gfx_preset'))
        need = TUNE_FPS.get(p)
        if need is None or detect_preset(s) != p or (p == PRESET_MIN and int(s.get('traffic')) <= 0):
            self._tune_done()               # настройки уже свои или убавлять больше нечего
            return
        if not ok:
            # пауза, свёрнутое окно: после возврата — секунда на раскачку, сосчитанное остаётся
            tn['slow'] = 0
            tn['skip'] = max(tn['skip'], 1.0)
            return
        if tn['skip'] > 0.0:
            tn['skip'] -= d                 # первые секунды не в счёт: видеокарта собирает шейдеры, грузит текстуры
            return
        if d > 0.4:
            # Кадр дольше 0,4 с — это либо подгрузка, либо игра и правда еле идёт.  Одиночный такой кадр
            # в замер просто не идёт (начинать из-за него замер заново нельзя: на компьютере с частыми
            # подёргиваниями он не кончился бы никогда).  Четыре таких кадра подряд или восемь за один
            # замер — игра стоит на месте, и ждать конца замера незачем
            tn['slow'] += 1
            tn['hit'] += 1
            if tn['slow'] < 4 and tn['hit'] < 8:
                return
        else:
            tn['slow'] = 0
            tn['t'] += d
            tn['n'] += 1
            if tn['t'] < TUNE_TIME:
                return
            if tn['n'] / tn['t'] >= need:
                self._tune_done()           # набор этой видеокарте по силам
                return
        if p == PRESET_MIN:
            s.set('traffic', int(s.get('traffic')) - 1)
            game.apply_traffic()
            text = 'Мало кадров в секунду: машин и прохожих на улицах стало меньше. Вернуть можно в настройках.'
        else:
            set_preset(s, p - 1, game.desktop())
            self.apply()
            text = ('Мало кадров в секунду: качество графики понижено до «%s». Вернуть можно в настройках.'
                    % PRESET_NAMES[p - 1])
        if not game.headless:
            s.save()
        tn.update(skip=TUNE_SKIP, t=0.0, n=0, slow=0, hit=0)
        self._hint(text)

    def _hint(self, text):
        try:
            hud = self.game.world.hud
            if hud is not None:
                hud.help(text, 6.0)
        except Exception:
            pass

    def _frame_inputs(self, dt):
        base = self.base
        render = base.render
        w = self.game.world
        sky = getattr(w, 'sky', None) if w is not None else None
        c = self.cfg
        cam = base.cam
        cp = cam.getPos(render)
        if sky is None:
            sun = (0.3, -0.3, 0.9)
            fill = (-0.3, 0.3, 0.6)
            sc, fc, ac = (0.6, 0.6, 0.6), (0.2, 0.2, 0.2), (0.6, 0.6, 0.6)
            zen = hor = fog_col = (0.5, 0.6, 0.8)
            fog_rng = (400.0, 600.0)
            indoor = False
            night = rain = clouds = 0.0
            hour = 12.0
        else:
            fog_col = sky.fog.getColor()
            fog_rng = (sky.fog.getLinearOnsetPoint()[1], sky.fog.getLinearOpaquePoint()[1])
            sun = _norm(sky.sun_np.getPos())
            fill = _norm(sky.fill_np.getPos())
            sc, fc, ac = sky.sun.getColor(), sky.fill.getColor(), sky.amb.getColor()
            indoor = sky.indoor is not None
            night, rain, clouds, hour = sky.night, sky.rain, sky.clouds_k, sky.hour
            hor = sky.fog_color
            zen = getattr(sky, 'zen_color', hor)
        if indoor:
            # под крышей свет комнаты ровный: без поправок и без теней от «солнца»
            sun_col = (sc[0], sc[1], sc[2])
            amb_sky = amb_gnd = (ac[0], ac[1], ac[2])
            zen = hor = amb_sky
            sh_k = 0.0
            glint = 0.25
        else:
            # ясный день: солнце ярче, рассеянный свет слабее и синее — тени читаются.  Под тучами наоборот:
            # света от солнца мало, он ровный и серый, резких теней нет
            k = 1.0 - clouds
            g = 1.0 + (SUN_GAIN - 1.0) * k
            sun_col = (sc[0] * g * (1.0 + 0.03 * k), sc[1] * g, sc[2] * g * (1.0 - 0.06 * k))
            # низкое солнце — длинные тени на пол-улицы: чтобы вечер не выходил мрачным, рассеянного света
            # тогда больше (в жизни так и есть: небо светит по-прежнему, а солнце — вскользь)
            low = 1.0 - max(0.0, min(1.0, (sun[2] - 0.2) / 0.5))
            a = AMB_GAIN + (1.02 - AMB_GAIN) * max(low * k, 0.0) + (1.04 - AMB_GAIN) * clouds
            amb_sky = (ac[0] * a * (1.0 - 0.02 * k), ac[1] * a * (1.0 + 0.03 * k), ac[2] * a * (1.0 + 0.12 * k))
            amb_gnd = (ac[0] * a * 0.80, ac[1] * a * 0.78, ac[2] * a * 0.74)
            # в миг, когда солнце сменяется луной (и наоборот), тени гаснут: иначе они бы прыгали
            sw = min(abs(hour - 6.0), abs(hour - 20.0))
            # тень не глухая: в городе её подсвечивают освещённые солнцем стены вокруг
            sh_k = SHADOW_DARK * max(0.0, min(1.0, sw / 0.3)) * (1.0 - 0.7 * clouds)
            glint = (1.0 - 0.75 * night) * (1.0 - 0.8 * clouds)
        # пятна-тени под машинами и деревьями: чем заметнее настоящие тени, тем они слабее
        blob = 1.0
        if self.cascades and not indoor:
            direct = max(sc[0], sc[1], sc[2]) * sh_k / SHADOW_DARK  # ясный день — около 0.56, пасмурно и ночью — 0.15
            blob = 1.0 - 0.85 * max(0.0, min(1.0, (direct - 0.12) / 0.3))
        u = self._u
        u['u_cam'][0] = LVecBase3f(cp[0], cp[1], cp[2])
        u['u_sun_dir'][0] = LVecBase3f(*sun)
        u['u_sun_col'][0] = LVecBase3f(*sun_col)
        u['u_fill_dir'][0] = LVecBase3f(*fill)
        u['u_fill_col'][0] = LVecBase3f(fc[0], fc[1], fc[2])
        u['u_amb_sky'][0] = LVecBase3f(*amb_sky)
        u['u_amb_gnd'][0] = LVecBase3f(*amb_gnd)
        u['u_sky_zen'][0] = LVecBase3f(zen[0], zen[1], zen[2])
        u['u_sky_hor'][0] = LVecBase3f(hor[0], hor[1], hor[2])
        u['u_env'][0] = LVecBase4f(rain, night, glint, blob)
        u['u_fog'][0] = LVecBase4f(fog_col[0], fog_col[1], fog_col[2], 1.0)
        u['u_fog_rng'][0] = LVecBase4f(fog_rng[0], fog_rng[1], 0.0, 0.0)
        u['u_time'][0] = float(self.time)
        cs = self.cascades
        if cs:
            fwd = render.getRelativeVector(cam, LVector3(0, 1, 0))
            gz = cp[2] - 3.0
            try:
                pl = w.player
                gz = pl.pos()[2] if len(pl.pos()) > 2 else w.city.ground_z(*pl.pos()[:2])
            except Exception:
                pass
            if indoor or sh_k <= 0.0:
                sh_k = 0.0
            c0 = cs[0]
            c1 = cs[1] if len(cs) > 1 else cs[0]
            on = sh_k > 0.0                 # под крышей и в миг смены солнца луной теней нет: карты не рисуем
            # Солнце ползёт по небу непрерывно, и если каждый кадр рисовать карту теней под чуть иным углом,
            # края теней (особенно ажурных — от листвы) непрерывно рябят.  Поэтому направление для карт
            # меняется шагами по 0,2° — раз в секунду без малого; между шагами картинка неподвижна
            held = self._sh_sun
            if held is None or held[0] * sun[0] + held[1] * sun[1] + held[2] * sun[2] < 0.999994:
                held = self._sh_sun = (sun[0], sun[1], sun[2])
            sun = held
            c0.buf.setActive(on)
            if on:
                c0.fit(base, cp, fwd, gz, sun)
            if c1 is not c0:
                # дальняя карта — только неподвижный город, поэтому каждый кадр её рисовать незачем: хватает
                # раза в пару секунд и тогда, когда взгляд ушёл в сторону
                c1.age += dt
                redo = on and c1.stale(cp, fwd, sun)
                c1.buf.setActive(redo)
                if redo:
                    c1.fit(base, cp, fwd, gz, sun)
                u['u_sh_mat1'][0] = c1.mat
            rng = SHADOW_DEPTH * 2.0 - 1.0
            u['u_sh_mat0'][0] = c0.mat
            u['u_sh_par'][0] = LVecBase4f(sh_k, c0.texel * 1.6, c1.texel * 1.6, 0.0)
            u['u_sh_geo'][0] = LVecBase4f(1.0 / c0.size, 1.0 / c1.size, 0.03 / rng, 0.25 / rng)
        if c is not None and c['lights'] > 0:
            self._pick_lights(cp, render.getRelativeVector(cam, LVector3(0, 1, 0)), night, indoor, dt)
            u['u_lfocus'][0] = self._lfocus if (night > 0.25 and not indoor) else NO_FOCUS
        p = self.post
        if p:
            p['night'] = 0.0 if indoor else night
            self._post_inputs(p)
            if not c['hdr']:
                # яркость сжимает шейдер сцены — значит, и фон буфера (он рисуется без шейдера) нужен уже сжатый
                try:
                    p['scene_buf'].setClearColor(LVecBase4(*(grade_color(base.win.getClearColor()) + (1.0,))))
                except Exception:
                    pass
        else:
            # без обработки кадра цвета правит сам шейдер сцены — значит, и фон (он рисуется без шейдера)
            # надо поправить так же: иначе дома, ушедшие в туман, проступали бы на небе силуэтами.
            # Небо ставит цвет фона не каждый кадр (на паузе — нет): свой, уже исправленный, не трогаем
            try:
                cur = LVecBase4(base.win.getClearColor())
                if self._bg is None or (cur - self._bg[1]).lengthSquared() > 1e-9:
                    self._bg = (cur, LVecBase4(*(grade_color(cur) + (1.0,))))
                    base.win.setClearColor(self._bg[1])
            except Exception:
                pass

    # ------------------------------------------------------------------
    # огни: фонари, костры в бочках, фары, маячки
    # ------------------------------------------------------------------
    def _load_lights(self):
        """Ночные огни города (их «звёздочки» построил citymesh) — в сетку для быстрого поиска ближайших."""
        self._light_grid = {}
        w = self.game.world
        cm = getattr(w, 'citymesh', None) if w is not None else None
        if cm is None:
            return
        city = w.city
        for (x, y, z, size, r, g, b) in getattr(cm, 'lights', ()):
            if size < 1.5:
                continue
            try:
                if z - city.ground_z(x, y) > 9.5:
                    continue                            # огни на крышах и мачтах до земли не достают
            except Exception:
                pass
            m = max(r, g, b, 1e-3)
            k = 2.1 / m
            # цвет огня — как у его «звёздочки», но насыщеннее: тёплый свет фонарей на синей ночной улице
            r, g, b = r * k, g * k * (0.86 if g < r else 1.0), b * k * (0.70 if b < r else 1.0)
            self._light_grid.setdefault((int(x // LIGHT_CELL), int(y // LIGHT_CELL)), []).append(
                (x, y, z - 0.25, 5.4 * size, r, g, b))
        cm.on_break = self._on_break

    def _on_break(self, br):
        """Фонарь сбили: его свет гаснет."""
        try:
            x, y = self.game.world.city.to_world(br.x, br.y)
        except Exception:
            x, y = br.x, br.y
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                key = (int(x // LIGHT_CELL) + dx, int(y // LIGHT_CELL) + dy)
                lst = self._light_grid.get(key)
                if lst:
                    self._light_grid[key] = [l for l in lst if (l[0] - x) ** 2 + (l[1] - y) ** 2 > 3.5 * 3.5]
        self._lamps_t = 0.0

    def _pick_lamps(self, fx, fy, n):
        """n ближайших к точке (fx, fy) фонарей; дальний из них светит слабее — чтобы смена была незаметной."""
        cx, cy = int(fx // LIGHT_CELL), int(fy // LIGHT_CELL)
        cand = []
        for ix in range(cx - 2, cx + 3):
            for iy in range(cy - 2, cy + 3):
                for l in self._light_grid.get((ix, iy), ()):
                    d2 = (l[0] - fx) ** 2 + (l[1] - fy) ** 2
                    if d2 < LIGHT_REACH * LIGHT_REACH:
                        cand.append((d2, l))
        cand.sort(key=lambda t: t[0])
        dmax = math.sqrt(cand[n][0]) if len(cand) > n else LIGHT_REACH
        out = []
        for d2, l in cand[:n]:
            k = max(0.0, min(1.0, (dmax - math.sqrt(d2)) / (0.3 * dmax)))
            if k > 0.0:
                out.append((l, k))
        return out, dmax

    def _pick_lights(self, cp, fwd, night, indoor, dt):
        n = len(self._lpos)
        w = self.game.world
        out = []                            # (место и радиус, цвет и признак фары, направление и угол)
        if not indoor and w is not None:
            fl = math.hypot(fwd[0], fwd[1]) or 1.0
            fx, fy = cp[0] + fwd[0] / fl * 12.0, cp[1] + fwd[1] / fl * 12.0
            # фары: машина игрока и ближайшие машины с зажжённым светом
            cars = []
            pv = w.player.vehicle
            for v in w.vehicles:
                if v.dead or not v.lights_on:
                    continue
                d2 = (v.x - fx) ** 2 + (v.y - fy) ** 2
                if d2 < 55.0 * 55.0:
                    cars.append((-1.0 if v is pv else d2, v))
            cars.sort(key=lambda t: t[0])
            for d2, v in cars[:(3 if n >= 12 else 2)]:
                c, s = math.cos(v.yaw), math.sin(v.yaw)
                hl = v.spec.L * 0.5
                k = 1.0 if d2 < 0 else max(0.0, min(1.0, (55.0 - math.sqrt(d2)) / 12.0))
                out.append((LVecBase4(v.x + c * (hl - 0.3), v.y + s * (hl - 0.3), v.z + 0.75, 30.0),
                            LVecBase4(3.2 * k, 3.0 * k, 2.5 * k, 1.0),
                            LVecBase4(c * 0.98, s * 0.98, -0.17, 0.80)))
                if v.siren and len(out) < n - 2:
                    # маячки: красный и синий по очереди
                    ph = int(self.time * 5.0) % 2
                    col = (1.5, 0.12, 0.09) if ph == 0 else (0.12, 0.30, 1.7)
                    out.append((LVecBase4(v.x, v.y, v.z + 2.0, 16.0), LVecBase4(col[0], col[1], col[2], 0.0),
                                LVecBase4(0, 0, -1, 0)))
            # фонари
            g = max(0.0, min(1.0, (night - 0.25) / 0.4))
            kk = self._lamp_k
            if g > 0.0:
                self._lamps_t -= dt
                if self._lamps_t <= 0.0:
                    self._lamps_t = 0.12
                    self._lamps, self._lamps_r = self._pick_lamps(fx, fy, max(1, n - len(out)))
                # Яркость каждого фонаря идёт к своей цели плавно.  Отбор обновляется восемь раз в секунду,
                # и без этого свет на асфальте менялся бы ступеньками: на ходу это видно как мерцание
                a = min(1.0, dt * 7.0)
                want = dict((id(l), (l, k)) for (l, k) in self._lamps)
                for key, (l, k) in want.items():
                    cur = kk.get(key)
                    k0 = cur[1] if cur is not None else 0.0
                    kk[key] = [l, k0 + (k - k0) * a]
                for key in list(kk):
                    if key not in want:
                        e = kk[key]
                        e[1] -= e[1] * a + 0.004
                        if e[1] <= 0.01:
                            del kk[key]
                # круг, в котором нарисованные пятна света уступают настоящим огням, идёт за взглядом каждый кадр
                self._focus_r += (max(self._lamps_r, 4.0) - self._focus_r) * a
                self._lfocus = LVecBase4f(fx, fy, self._focus_r * 0.70, self._focus_r)
                for (l, k) in sorted(kk.values(), key=lambda e: -e[1]):
                    if len(out) >= n:
                        break
                    k *= g
                    out.append((LVecBase4(l[0], l[1], l[2], l[3]), LVecBase4(l[4] * k, l[5] * k, l[6] * k, 0.0),
                                LVecBase4(0, 0, -1, 0)))
            elif kk:
                kk.clear()
        for i in range(n):
            if i < len(out):
                self._lpos[i], self._lcol[i], self._ldir[i] = out[i]
            else:
                self._lpos[i] = LVecBase4(0, 0, -1000, 0.01)
                self._lcol[i] = LVecBase4(0, 0, 0, 0)
                self._ldir[i] = LVecBase4(0, 0, -1, 0)
        self._u['u_lnum'][0] = float(min(n, len(out)))      # шейдер перебирает только зажжённые огни

    def _post_inputs(self, p):
        base = self.base
        win = base.win
        wx, wy = max(1, win.getXSize()), max(1, win.getYSize())
        try:
            p['scene_buf'].setClearColor(win.getClearColor())
        except Exception:
            pass
        for (q, kind, div) in p['stages']:
            sx, sy = max(1, wx // div), max(1, wy // div)
            if kind == 'bright':
                # днём светятся только пересветы (блики, белые стены на солнце), ночью — все огни и окна
                v = LVecBase4(1.0 / wx, 1.0 / wy, 1.0 - 0.45 * p.get('night', 0.0), 0.55)
            elif kind == 'h':
                v = LVecBase4(1.0 / sx, 0.0, 0, 0)
            elif kind == 'v':
                v = LVecBase4(0.0, 1.0 / sy, 0, 0)
            elif kind == 'ssao':
                v = LVecBase4(1.0 / sx, 1.0 / sy, 0.9, 1.3)
            elif kind == 'ao':
                v = LVecBase4(1.0 / sx, 1.0 / sy, 0, 0)
            else:
                v = LVecBase4(1.0 / wx, 1.0 / wy, 0, 0)
            q.setShaderInput('u_px', v)
        q = p.get('ssao_quad')
        if q is not None:
            lens = base.camLens
            fov = lens.getFov()
            q.setShaderInput('u_proj', LVecBase4(lens.getNear(), lens.getFar(),
                                                 math.tan(math.radians(fov[0]) * 0.5),
                                                 math.tan(math.radians(fov[1]) * 0.5)))
