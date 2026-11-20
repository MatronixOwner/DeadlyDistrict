# -*- coding: utf-8 -*-
"""Тексты шейдеров (см. gfx.py).

Язык — GLSL 1.20: его понимает любая видеокарта с OpenGL 2.1 и новее, то есть почти всё, что выпущено
с 2007 года.  Тексты лежат строками в модуле, а не файлами: так они сами попадают в собранную игру.

Возможности включаются строками «#define» в начале текста (их дописывает gfx.Gfx): чем проще настройки
графики, тем короче шейдер и тем меньше работы видеокарте.
"""

import re

HEAD = '#version 120\n'

# ---------------------------------------------------------------------------
# Сцена: всё, что нарисовано в мире.  Повторяет обычный расчёт видеокарты (цвет вершины × текстура × свет,
# потом туман) и добавляет то, чего в нём нет: свет считается в каждой точке, а не в вершинах, есть тени
# от солнца, блики, огни фонарей и фар.
#
# Чем шейдер узнаёт, что предмету свет не положен (небо, огни, искры): у такого предмета нет источников
# света, и Panda3D сообщает «рассеянный свет = 1».  Туман выключен — у него «начало = конец» (длина 0).
#
# От самой Panda3D шейдер берёт только эти два признака — «есть свет» и «есть туман».  Цвета света и
# тумана, их дальность игра передаёт сама и каждый кадр (gfx.Gfx._frame_inputs): значения Panda3D
# обновляет лишь при смене состояния предмета, и у воды, например, цвет тумана застыл бы на первом кадре.
# ---------------------------------------------------------------------------
SCENE_VERT = r"""
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
uniform mat4 p3d_TextureMatrix;
attribute vec4 p3d_Vertex;
attribute vec3 p3d_Normal;
attribute vec4 p3d_Color;
attribute vec2 p3d_MultiTexCoord0;
varying vec4 v_color;
varying vec2 v_uv;
varying vec3 v_wpos;
varying vec3 v_wnrm;
#if SHADOWS
uniform mat4 u_sh_mat0;
uniform vec4 u_sh_par;              // сила тени, сдвиг по нормали (ближний каскад), то же для дальнего, —
varying vec3 v_sc0;
#if CASCADES > 1
uniform mat4 u_sh_mat1;
varying vec3 v_sc1;
#endif
#endif
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    vec4 wp = p3d_ModelMatrix * p3d_Vertex;
    vec3 wn = (p3d_ModelMatrix * vec4(p3d_Normal, 0.0)).xyz;
    v_wpos = wp.xyz;
    v_wnrm = wn;
    v_color = p3d_Color;
    v_uv = (p3d_TextureMatrix * vec4(p3d_MultiTexCoord0, 0.0, 1.0)).xy;
#if SHADOWS
    // точку перед поиском в карте теней чуть сдвигаем по нормали: иначе грань затеняет сама себя
    vec3 n = wn * inversesqrt(max(dot(wn, wn), 1e-8));
    v_sc0 = (u_sh_mat0 * vec4(wp.xyz + n * u_sh_par.y, 1.0)).xyz;
#if CASCADES > 1
    v_sc1 = (u_sh_mat1 * vec4(wp.xyz + n * u_sh_par.z, 1.0)).xyz;
#endif
#endif
}
"""

TONEMAP = r"""
// Длина 1 без риска деления на ноль: у нулевого вектора normalize() даёт «не число», и такая точка
// расползается по кадру чёрным пятном, как только включено свечение.
vec3 snorm(vec3 v) { return v * inversesqrt(max(dot(v, v), 1e-8)); }
// Яркость выше «колена» плавно сжимается к белому, а не обрезается: солнечная стена и блик на капоте
// остаются светлыми, но не выгорают в ровное белое пятно.  Ниже колена картинка не меняется.
vec3 tonemap(vec3 c) {
    c *= u_look.x;
    vec3 a = max(c - 0.72, 0.0);
    return min(c, 0.72) + 0.28 * (1.0 - exp(-a / 0.28));
}
// Цветокоррекция «как в кино»: чуть больше контраста и насыщенности, тени холоднее, света теплее.
vec3 grade(vec3 c) {
    float l = dot(c, vec3(0.299, 0.587, 0.114));
    c = mix(vec3(l), c, u_look.y);
    c = (c - 0.5) * u_look.z + 0.5;
    c += (l - 0.5) * vec3(0.035, 0.008, -0.040) * u_look.w;
    return clamp(c, 0.0, 1.0);
}
"""

SCENE_FRAG = r"""
uniform sampler2D p3d_Texture0;
uniform vec4 p3d_ColorScale;
uniform struct p3d_LightModelParameters { vec4 ambient; } p3d_LightModel;
uniform struct p3d_FogParameters { vec4 color; float density; float start; float end; float scale; } p3d_Fog;
uniform vec3 u_cam;                 // камера (в мире)
uniform vec3 u_sun_dir;             // на солнце (ночью — на луну)
uniform vec3 u_sun_col;
uniform vec3 u_fill_dir;            // подсветка с обратной стороны
uniform vec3 u_fill_col;
uniform vec3 u_amb_sky;             // рассеянный свет сверху…
uniform vec3 u_amb_gnd;             // …и снизу, от земли
uniform vec3 u_sky_zen;             // небо: зенит и горизонт (отражения)
uniform vec3 u_sky_hor;
uniform vec4 u_mat;                 // материал: блеск, «мокнет ли под дождём», пятно света (1), пятно-тень (1)
uniform vec4 u_env;                 // дождь (мокрый асфальт), ночь, сила бликов солнца, видимость пятен-теней
uniform vec4 u_lfocus;              // огни: середина освещённого круга (x, y), его радиус — внутренний и внешний
uniform vec4 u_look;                // выдержка, насыщенность, контраст, тонирование
uniform vec4 u_fog;                 // туман: цвет…
uniform vec4 u_fog_rng;             // …и дальность: начало, конец
uniform float u_emit;               // яркость того, что светится само (солнце ярче белого: вокруг него ореол)
varying vec4 v_color;
varying vec2 v_uv;
varying vec3 v_wpos;
varying vec3 v_wnrm;
#if SHADOWS
uniform sampler2DShadow u_sh_tex0;
uniform vec4 u_sh_par;
uniform vec4 u_sh_geo;              // размер точки карты (ближний, дальний), запас по глубине (ближний, дальний)
varying vec3 v_sc0;
#if CASCADES > 1
uniform sampler2DShadow u_sh_tex1;
varying vec3 v_sc1;
#endif
#endif
#if LIGHTS > 0
uniform float u_lnum;               // сколько огней зажжено сейчас (остальные места в массивах пусты)
uniform vec4 u_lpos[LIGHTS];        // огни: место и радиус
uniform vec4 u_lcol[LIGHTS];        // цвет; w > 0 — фара: светит конусом…
uniform vec4 u_ldir[LIGHTS];        // …в эту сторону (w — косинус половины угла)
#endif
""" + TONEMAP + r"""
#if GLOSS
float hash2(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash2(i), hash2(i + vec2(1.0, 0.0)), f.x), mix(hash2(i + vec2(0.0, 1.0)), hash2(i + vec2(1.0, 1.0)), f.x), f.y);
}
#endif
#if SHADOWS
float sh_tap0(vec3 c) { return shadow2D(u_sh_tex0, c).r; }
float sh_near(vec3 sc) {
    float t = u_sh_geo.x;
    sc.z -= u_sh_geo.z;
#if PCF >= 16
    // 16 выборок по кругу: мягкий край тени (полутень сантиметров в десять)
    float s = 0.0;
    s += sh_tap0(sc + vec3(-0.94, -0.40, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3( 0.95, -0.77, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3(-0.09, -0.93, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3( 0.34,  0.29, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3(-0.92,  0.46, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3(-0.82, -0.88, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3(-0.38,  0.28, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3( 0.97,  0.45, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3( 0.44, -0.98, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3( 0.54, -0.14, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3(-0.26, -0.42, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3( 0.79,  0.19, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3(-0.24,  1.00, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3(-0.81,  0.91, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3( 0.20,  0.79, 0.0) * t * 3.2);
    s += sh_tap0(sc + vec3( 0.14, -0.14, 0.0) * t * 3.2);
    return s * 0.0625;
#elif PCF >= 4
    float s = sh_tap0(sc + vec3(-0.75, -0.75, 0.0) * t) + sh_tap0(sc + vec3(0.75, -0.75, 0.0) * t)
            + sh_tap0(sc + vec3(-0.75, 0.75, 0.0) * t) + sh_tap0(sc + vec3(0.75, 0.75, 0.0) * t);
    return s * 0.25;
#else
    return sh_tap0(sc);
#endif
}
#if CASCADES > 1
float sh_far(vec3 sc) {
    float t = u_sh_geo.y;
    sc.z -= u_sh_geo.w;
    float s = shadow2D(u_sh_tex1, sc + vec3(-0.5, -0.5, 0.0) * t).r + shadow2D(u_sh_tex1, sc + vec3(0.5, -0.5, 0.0) * t).r
            + shadow2D(u_sh_tex1, sc + vec3(-0.5, 0.5, 0.0) * t).r + shadow2D(u_sh_tex1, sc + vec3(0.5, 0.5, 0.0) * t).r;
    return s * 0.25;
}
#endif
// 1 — точка на свету, 0 — в тени
float sun_shadow() {
    vec3 e0 = abs(v_sc0 - 0.5) * 2.0;                 // 0 в середине карты, 1 на её краю
    float k0 = 1.0 - smoothstep(0.86, 0.98, max(e0.x, e0.y));
    float s = 1.0;
#if CASCADES > 1
    vec3 e1 = abs(v_sc1 - 0.5) * 2.0;
    float k1 = 1.0 - smoothstep(0.84, 0.98, max(e1.x, e1.y));
    float f = 1.0;
    if (k0 < 1.0 && k1 > 0.0) f = mix(1.0, sh_far(v_sc1), k1);
    if (k0 > 0.0) s = mix(f, sh_near(v_sc0), k0); else s = f;
#else
    if (k0 > 0.0) s = mix(1.0, sh_near(v_sc0), k0);
#endif
    return mix(1.0, s, u_sh_par.x);
}
#endif

void main() {
    vec4 col = texture2D(p3d_Texture0, v_uv) * v_color;
    vec3 rgb = col.rgb;
    vec3 la = p3d_LightModel.ambient.rgb;
    bool lit = min(la.r, min(la.g, la.b)) < 0.999;
    vec3 tocam = u_cam - v_wpos;
    float dist = length(tocam);
    if (lit) {
        vec3 N = v_wnrm;
        float nl = dot(N, N);
        N = nl > 1e-8 ? N * inversesqrt(nl) : vec3(0.0, 0.0, 1.0);
        vec3 V = tocam / max(dist, 1e-4);
        float ndl = max(dot(N, u_sun_dir), 0.0);
        float sh = 1.0;
#if SHADOWS
        if (ndl > 0.0 && u_sh_par.x > 0.0) sh = sun_shadow();
#endif
        vec3 light = mix(u_amb_gnd, u_amb_sky, N.z * 0.5 + 0.5)
                   + u_sun_col * (ndl * sh)
                   + u_fill_col * max(dot(N, u_fill_dir), 0.0);
        vec3 spec = vec3(0.0);
#if GLOSS
        // под дождём всё, что смотрит вверх и «мокнет» (дороги, тротуары, крыши машин), темнеет и блестит;
        // на дороге, кроме того, стоят лужи — в них небо отражается, как в зеркале
        float wet = u_env.x * u_mat.y * smoothstep(0.75, 0.95, N.z);
        float gloss = u_mat.x;
        if (wet > 0.01) {
            float pud = smoothstep(0.46, 0.64, vnoise(v_wpos.xy * 0.21) * 0.62 + vnoise(v_wpos.xy * 0.57) * 0.38);
            pud *= step(u_mat.x, 0.05);                 // лужи — на земле, а не на крыше машины
            rgb *= 1.0 - wet * (0.30 + 0.12 * pud);
            gloss = max(gloss, wet * (0.38 + 0.62 * pud));
        }
#endif
#if LIGHTS > 0
        vec3 lamps = vec3(0.0);
        for (int i = 0; i < LIGHTS; i++) {
            if (float(i) >= u_lnum) break;              // днём огней нет: цикл кончается сразу
            vec3 d = u_lpos[i].xyz - v_wpos;
            float r2 = dot(d, d);
            float q = r2 / (u_lpos[i].w * u_lpos[i].w);         // 1 — на границе освещённого круга
#if GLOSS
            // отражение огня в мокром асфальте и в лаке видно намного дальше, чем сам его свет
            float reach = (gloss > 0.15) ? 16.0 : 1.0;
#else
            float reach = 1.0;
#endif
            if (q < reach) {
                vec3 Ld = d * inversesqrt(r2 + 1e-4);
                float cone = 1.0;
                if (u_lcol[i].w > 0.5) {
                    // фара: светит конусом
                    cone = smoothstep(u_ldir[i].w, mix(u_ldir[i].w, 1.0, 0.45), dot(-Ld, u_ldir[i].xyz));
                }
                if (q < 1.0) {
                    float a = (1.0 - q) * (1.0 - q) * cone;
                    lamps += u_lcol[i].rgb * (a * (0.2 + 0.8 * max(dot(N, Ld), 0.0)));
                }
#if GLOSS
                if (gloss > 0.01) {
                    float as = 1.0 - q * 0.0625;
                    vec3 H = snorm(Ld + V);
                    spec += u_lcol[i].rgb * (cone * as * as * gloss * 0.40 * pow(max(dot(N, H), 0.0), 36.0 + 90.0 * gloss));
                }
#endif
            }
        }
        // рядом с фонарём свет не «выжигает» стену добела: его яркость плавно ограничена
        light += 1.7 * (1.0 - exp(-lamps / 1.7));
#endif
        rgb *= light;
#if GLOSS
        if (gloss > 0.01) {
            // блик солнца и отражение неба: чем острее угол взгляда, тем сильнее (как на лаке и на воде)
            vec3 R = reflect(-V, N);
            float fr = pow(clamp(1.0 - dot(N, V), 0.0, 1.0), 4.0);
            float k = gloss * (0.05 + 0.55 * fr);
            vec3 env = mix(u_sky_hor, u_sky_zen, clamp(R.z * 1.6, 0.0, 1.0));
            env = mix(u_amb_gnd * 0.55, env, smoothstep(-0.12, 0.06, R.z));
            rgb = mix(rgb, env, k);
            vec3 H = snorm(u_sun_dir + V);
            spec += u_sun_col * (sh * u_env.z * gloss * 1.6 * pow(max(dot(N, H), 0.0), 40.0 + 160.0 * gloss));
            rgb += spec;
        }
#endif
    }
    else {
        rgb *= u_emit;
    }
    rgb *= p3d_ColorScale.rgb;
    if (p3d_Fog.end - p3d_Fog.start > 0.01) {
        rgb = mix(u_fog.rgb, rgb, clamp((u_fog_rng.y - dist) / max(u_fog_rng.y - u_fog_rng.x, 1.0), 0.0, 1.0));
    }
#if !HDR
    // без обработки кадра яркость сжимает сам шейдер сцены
    rgb = grade(tonemap(rgb));
#endif
    float alpha = col.a * p3d_ColorScale.a;
    // пятна-тени под предметами гаснут, когда от солнца ложатся настоящие тени
    alpha *= 1.0 - u_mat.w * (1.0 - u_env.w);
#if LIGHTS > 0
    // нарисованные пятна света под фонарями: рядом с игроком вместо них светят настоящие огни
    if (u_mat.z > 0.5) alpha *= smoothstep(u_lfocus.z, u_lfocus.w, distance(v_wpos.xy, u_lfocus.xy));
#endif
    gl_FragColor = vec4(rgb, alpha);
}
"""

# ---------------------------------------------------------------------------
# Карта теней: сцена глазами солнца, нужна только глубина.
# ---------------------------------------------------------------------------
SHADOW_VERT = r"""
uniform mat4 p3d_ModelViewProjectionMatrix;
attribute vec4 p3d_Vertex;
attribute vec4 p3d_Color;
attribute vec2 p3d_MultiTexCoord0;
varying vec2 v_uv;
varying float v_a;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_uv = p3d_MultiTexCoord0;
    v_a = p3d_Color.a;
}
"""

SHADOW_FRAG = r"""
uniform sampler2D p3d_Texture0;
uniform vec4 p3d_ColorScale;
varying vec2 v_uv;
varying float v_a;
void main() {
    // листва и решётки отбрасывают ажурную тень, стекло не отбрасывает никакой
    if (texture2D(p3d_Texture0, v_uv).a * v_a * p3d_ColorScale.a < 0.5) discard;
    gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);
}
"""

# ---------------------------------------------------------------------------
# Вода: рябь из двух слоёв текстуры, отражение неба и солнечная дорожка.
# ---------------------------------------------------------------------------
WATER_VERT = r"""
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
attribute vec4 p3d_Vertex;
attribute vec4 p3d_Color;
attribute vec2 p3d_MultiTexCoord0;
varying vec4 v_color;
varying vec2 v_uv;
varying vec3 v_wpos;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_wpos = (p3d_ModelMatrix * p3d_Vertex).xyz;
    v_color = p3d_Color;
    v_uv = p3d_MultiTexCoord0;
}
"""

WATER_FRAG = r"""
uniform sampler2D p3d_Texture0;
uniform struct p3d_FogParameters { vec4 color; float density; float start; float end; float scale; } p3d_Fog;
uniform vec3 u_cam;
uniform vec3 u_sun_dir;
uniform vec3 u_sun_col;
uniform vec3 u_amb_sky;
uniform vec3 u_sky_zen;
uniform vec3 u_sky_hor;
uniform vec4 u_env;
uniform vec4 u_look;
uniform vec4 u_fog;
uniform vec4 u_fog_rng;
uniform float u_time;
varying vec4 v_color;
varying vec2 v_uv;
varying vec3 v_wpos;
""" + TONEMAP + r"""
// высота ряби в точке: два слоя текстуры воды бегут навстречу
float wave(vec2 p) {
    float a = texture2D(p3d_Texture0, p * 0.060 + vec2(u_time * 0.010, u_time * 0.017)).g;
    float b = texture2D(p3d_Texture0, p * 0.023 - vec2(u_time * 0.008, u_time * 0.004)).g;
    return a * 0.6 + b * 0.8;
}
void main() {
    vec3 tocam = u_cam - v_wpos;
    float dist = length(tocam);
    vec3 V = tocam / max(dist, 1e-4);
    vec2 p = v_wpos.xy;
    float e = 0.35;
    float h0 = wave(p);
    // наклон поверхности — по разности высот ряби; вдали рябь сглаживается, иначе она рябит и в глазах
    float calm = 1.0 / (1.0 + dist * 0.004);
    vec3 N = snorm(vec3((h0 - wave(p + vec2(e, 0.0))) * 1.5 * calm, (h0 - wave(p + vec2(0.0, e))) * 1.5 * calm, 1.0));
    float fr = 0.04 + 0.96 * pow(clamp(1.0 - dot(N, V), 0.0, 1.0), 5.0);
    vec3 R = reflect(-V, N);
    // волны наклонены, поэтому вода отражает небо не у самого горизонта, а повыше — там оно синее
    vec3 sky = mix(u_sky_hor, u_sky_zen, clamp(R.z * 1.4 + 0.30, 0.0, 1.0));
    vec3 tex = texture2D(p3d_Texture0, v_uv + vec2(u_time * 0.012, u_time * 0.02)).rgb * v_color.rgb;
    vec3 deep = tex * (u_amb_sky * 0.80 + u_sun_col * (0.50 * max(u_sun_dir.z, 0.0)));
    vec3 rgb = mix(deep, sky, clamp(fr, 0.0, 1.0) * 0.62);
    vec3 H = snorm(u_sun_dir + V);
    float ndh = clamp(dot(N, H), 0.0, 1.0);
    rgb += u_sun_col * (u_env.z * (2.2 * pow(ndh, 140.0) + 0.22 * pow(ndh, 18.0)));
    if (p3d_Fog.end - p3d_Fog.start > 0.01) {
        rgb = mix(u_fog.rgb, rgb, clamp((u_fog_rng.y - dist) / max(u_fog_rng.y - u_fog_rng.x, 1.0), 0.0, 1.0));
    }
#if !HDR
    rgb = grade(tonemap(rgb));
#endif
    gl_FragColor = vec4(rgb, 1.0);
}
"""

# ---------------------------------------------------------------------------
# Обработка готового кадра.
# ---------------------------------------------------------------------------
POST_VERT = r"""
uniform mat4 p3d_ModelViewProjectionMatrix;
attribute vec4 p3d_Vertex;
attribute vec2 p3d_MultiTexCoord0;
varying vec2 v_uv;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_uv = p3d_MultiTexCoord0;
}
"""

# яркие места кадра, уменьшенные вчетверо: из них получится свечение
BRIGHT_FRAG = r"""
uniform sampler2D u_src;
uniform vec4 u_px;                  // размер точки исходника (x, y), порог, ширина перехода
varying vec2 v_uv;
void main() {
    vec3 c = texture2D(u_src, v_uv + u_px.xy * vec2(-1.0, -1.0)).rgb + texture2D(u_src, v_uv + u_px.xy * vec2(1.0, -1.0)).rgb
           + texture2D(u_src, v_uv + u_px.xy * vec2(-1.0, 1.0)).rgb + texture2D(u_src, v_uv + u_px.xy * vec2(1.0, 1.0)).rgb;
    c *= 0.25;
    float l = max(c.r, max(c.g, c.b));
    float k = clamp((l - u_px.z) / u_px.w, 0.0, 1.0);
    gl_FragColor = vec4(clamp(c, 0.0, 8.0) * (k * k), 1.0);
}
"""

# размытие по одной оси (9 точек за 5 выборок)
BLUR_FRAG = r"""
uniform sampler2D u_src;
uniform vec4 u_px;                  // шаг (x, y)
varying vec2 v_uv;
void main() {
    vec2 d = u_px.xy;
    vec3 c = texture2D(u_src, v_uv).rgb * 0.2270270;
    c += (texture2D(u_src, v_uv + d * 1.3846154).rgb + texture2D(u_src, v_uv - d * 1.3846154).rgb) * 0.3162162;
    c += (texture2D(u_src, v_uv + d * 3.2307692).rgb + texture2D(u_src, v_uv - d * 3.2307692).rgb) * 0.0702703;
    gl_FragColor = vec4(c, 1.0);
}
"""

# Затенение в углах и щелях (SSAO) по карте глубины: чем больше соседних точек «нависает» над этой,
# тем она темнее.  Считается в половинном разрешении.
SSAO_FRAG = r"""
uniform sampler2D u_depth;
uniform vec4 u_proj;                // ближняя и дальняя плоскости, tg(угол/2) по x и по y
uniform vec4 u_px;                  // размер точки экрана (x, y), радиус в метрах, сила
varying vec2 v_uv;
float eye_z(vec2 uv) {
    float d = texture2D(u_depth, uv).r;
    return u_proj.x * u_proj.y / (u_proj.y - d * (u_proj.y - u_proj.x));
}
vec3 eye_pos(vec2 uv) {
    float z = eye_z(uv);
    return vec3((uv * 2.0 - 1.0) * u_proj.zw * z, z);
}
void main() {
    vec3 P = eye_pos(v_uv);
    if (P.z > 140.0) { gl_FragColor = vec4(1.0); return; }
    // нормаль — по соседним точкам; из двух соседей берём того, что ближе по глубине (иначе на рёбрах шум)
    vec3 px = eye_pos(v_uv + vec2(u_px.x, 0.0)) - P;
    vec3 mx = P - eye_pos(v_uv - vec2(u_px.x, 0.0));
    vec3 py = eye_pos(v_uv + vec2(0.0, u_px.y)) - P;
    vec3 my = P - eye_pos(v_uv - vec2(0.0, u_px.y));
    vec3 dx = abs(px.z) < abs(mx.z) ? px : mx;
    vec3 dy = abs(py.z) < abs(my.z) ? py : my;
    vec3 N = cross(dy, dx);
    float n2 = dot(N, N);
    // у края экрана соседней точки нет: наклон поверхности неизвестен — такую точку не затеняем
    if (n2 < 1e-12) { gl_FragColor = vec4(1.0); return; }
    N *= inversesqrt(n2);
    float rad = u_px.z;
    // радиус на экране: дальше — меньше
    vec2 sr = vec2(rad / (u_proj.z * P.z), rad / (u_proj.w * P.z)) * 0.5;
    // поворот выборок — свой у каждой точки, но по ровному узору: размытие 4×4 убирает его без остатка
    float rnd = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) * 6.2831853;
    float occ = 0.0;
    for (int i = 0; i < SSAO_TAPS; i++) {
        float t = (float(i) + 0.5) / float(SSAO_TAPS);
        float a = rnd + float(i) * 2.3999632;
        vec2 o = vec2(cos(a), sin(a)) * (sqrt(t) * sr);
        vec3 S = eye_pos(v_uv + o) - P;
        float l2 = dot(S, S);
        float nd = dot(N, S) * inversesqrt(l2 + 1e-5);
        occ += max(nd - 0.12, 0.0) / (1.0 + l2 / (rad * rad) * 2.0) * step(l2, rad * rad * 4.0);
    }
    float ao = 1.0 - clamp(occ / float(SSAO_TAPS) * 2.4 * u_px.w, 0.0, 1.0);
    ao = mix(ao, 1.0, smoothstep(90.0, 140.0, P.z));
    gl_FragColor = vec4(ao, ao, ao, 1.0);
}
"""

# размытие затенения 4×4 (шум выборок → ровная тень): четыре выборки между точками, каждая усредняет 2×2
AOBLUR_FRAG = r"""
uniform sampler2D u_src;
uniform vec4 u_px;
varying vec2 v_uv;
void main() {
    float s = texture2D(u_src, v_uv + u_px.xy * vec2(-1.5, -1.5)).r + texture2D(u_src, v_uv + u_px.xy * vec2(0.5, -1.5)).r
            + texture2D(u_src, v_uv + u_px.xy * vec2(-1.5, 0.5)).r + texture2D(u_src, v_uv + u_px.xy * vec2(0.5, 0.5)).r;
    gl_FragColor = vec4(vec3(s * 0.25), 1.0);
}
"""

# сборка кадра: сцена × затенение + свечение, потом сжатие яркости, цветокоррекция и затемнение по краям
COMPOSITE_FRAG = r"""
uniform sampler2D u_scene;
#if BLOOM
uniform sampler2D u_bloom0;
uniform sampler2D u_bloom1;
#endif
#if SSAO
uniform sampler2D u_ao;
#endif
uniform vec4 u_look;
uniform vec4 u_fx;                  // сила свечения, затемнение по краям, —, —
varying vec2 v_uv;
""" + TONEMAP + r"""
void main() {
    vec3 c = texture2D(u_scene, v_uv).rgb;
#if SSAO
    c *= texture2D(u_ao, v_uv).r;
#endif
#if BLOOM
    c += (texture2D(u_bloom0, v_uv).rgb * 0.55 + texture2D(u_bloom1, v_uv).rgb * 0.75) * u_fx.x;
#endif
    c = grade(tonemap(c));
    vec2 q = v_uv - 0.5;
    c *= 1.0 - u_fx.y * smoothstep(0.25, 0.95, dot(q, q) * 2.2);
    gl_FragColor = vec4(c, 1.0);
}
"""

# готовая картинка — на экран как есть, только с затемнением по краям (сглаживал её сам буфер сцены)
COPY_FRAG = r"""
uniform sampler2D u_src;
uniform vec4 u_fx;
varying vec2 v_uv;
void main() {
    vec3 c = texture2D(u_src, v_uv).rgb;
    vec2 q = v_uv - 0.5;
    c *= 1.0 - u_fx.y * smoothstep(0.25, 0.95, dot(q, q) * 2.2);
    gl_FragColor = vec4(c, 1.0);
}
"""

# сглаживание краёв по готовой картинке (FXAA); VIGNETTE — заодно затемнить углы (когда сборки кадра нет)
FXAA_FRAG = r"""
uniform sampler2D u_src;
uniform vec4 u_px;
#if VIGNETTE
uniform vec4 u_fx;
#endif
varying vec2 v_uv;
float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }
vec3 finish(vec3 c) {
#if VIGNETTE
    vec2 q = v_uv - 0.5;
    c *= 1.0 - u_fx.y * smoothstep(0.25, 0.95, dot(q, q) * 2.2);
#endif
    return c;
}
void main() {
    vec2 px = u_px.xy;
    vec3 m = texture2D(u_src, v_uv).rgb;
    float lNW = luma(texture2D(u_src, v_uv + vec2(-1.0, -1.0) * px).rgb);
    float lNE = luma(texture2D(u_src, v_uv + vec2(1.0, -1.0) * px).rgb);
    float lSW = luma(texture2D(u_src, v_uv + vec2(-1.0, 1.0) * px).rgb);
    float lSE = luma(texture2D(u_src, v_uv + vec2(1.0, 1.0) * px).rgb);
    float lM = luma(m);
    float lMin = min(lM, min(min(lNW, lNE), min(lSW, lSE)));
    float lMax = max(lM, max(max(lNW, lNE), max(lSW, lSE)));
    if (lMax - lMin < max(0.03, lMax * 0.10)) { gl_FragColor = vec4(finish(m), 1.0); return; }
    vec2 dir = vec2(-((lNW + lNE) - (lSW + lSE)), (lNW + lSW) - (lNE + lSE));
    float red = max((lNW + lNE + lSW + lSE) * 0.03125, 0.0078125);
    float rcp = 1.0 / (min(abs(dir.x), abs(dir.y)) + red);
    dir = clamp(dir * rcp, vec2(-8.0), vec2(8.0)) * px;
    vec3 a = 0.5 * (texture2D(u_src, v_uv + dir * (1.0 / 3.0 - 0.5)).rgb + texture2D(u_src, v_uv + dir * (2.0 / 3.0 - 0.5)).rgb);
    vec3 b = a * 0.5 + 0.25 * (texture2D(u_src, v_uv - dir * 0.5).rgb + texture2D(u_src, v_uv + dir * 0.5).rgb);
    float lB = luma(b);
    gl_FragColor = vec4(finish((lB < lMin || lB > lMax) ? a : b), 1.0);
}
"""


_COMMENT = re.compile(r'//[^\n]*')


def source(text, **defs):
    """Текст шейдера с заголовком и строками #define.

    Пояснения из текста убираются: язык шейдеров знает только латиницу, и строгий драйвер видеокарты
    вправе споткнуться о русские буквы даже в комментарии."""
    lines = [HEAD]
    for k in sorted(defs):
        v = defs[k]
        lines.append('#define %s %d\n' % (k, int(v)))
    body = _COMMENT.sub('', text)
    body = '\n'.join(ln.rstrip() for ln in body.split('\n'))
    return ''.join(lines) + body
