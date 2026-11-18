# -*- coding: utf-8 -*-
"""Векторное увеличение пиксельной текстуры.

Текстура 128×128, натянутая на машину, вблизи выглядит «лесенкой»: наклонный край стекла идёт ступеньками
в несколько точек экрана, швы дверей — зубчатые.  Простое увеличение (ближайшая точка, билинейное, EPX)
ступеньки не убирает — они длинные, пологие.  Здесь картинка разбирается на слои, у каждого слоя край
обводится линиями и кривыми (potrace: оптимальный многоугольник по контуру точек) и заново закрашивается
в большом размере, уже без ступенек:

    слой 0 — «некрашеное» (стёкла, швы, фары, колесо) поверх краски;
    слои 1, 2, … — то же, но только точки светлее очередного порога яркости (levels): спицы на чёрной шине,
    блики на спицах.  Слои вложены друг в друга, поэтому щелей между ними не бывает.

Внутри слоя цвет — плавная интерполяция точек этого слоя (соседние слои в неё не подмешиваются, край остаётся
резким).

Нужен пакет potracer (чистый Python, GPL) — только здесь, при подготовке картинок; в игру он не входит.
"""
import numpy as np


def _bilinear(a, k):
    """Плавное увеличение в k раз (центры точек совпадают)."""
    from PIL import Image
    h, w = a.shape[:2]
    if a.ndim == 2:
        return np.asarray(Image.fromarray(a.astype(np.float32), 'F').resize((w * k, h * k), Image.BILINEAR))
    return np.stack([_bilinear(a[..., i], k) for i in range(a.shape[2])], axis=2)


def field(rgb, mask, k, soft=1.0):
    """Цвет точек mask, плавно растянутый в k раз и продолженный за пределы маски ближайшим значением.

    soft — размытие внутри маски (в точках исходника): художник сглаживал наклонные края вручную, чередуя
    тёмные и светлые точки, — после обводки это чередование превратилось бы в «гребёнку» вдоль края."""
    from scipy import ndimage
    if not mask.any():
        return np.zeros((rgb.shape[0] * k, rgb.shape[1] * k, rgb.shape[2]), np.float32)
    m = mask.astype(np.float32)
    src = rgb.astype(np.float32)
    if soft > 0.0:
        den = ndimage.gaussian_filter(m, soft, mode='constant')
        num = np.stack([ndimage.gaussian_filter(src[..., i] * m, soft, mode='constant')
                        for i in range(src.shape[2])], axis=2)
        src = np.where(mask[..., None], num / np.maximum(den, 1e-6)[..., None], src)
    # продолжаем цвет за край маски: интерполяция у края не должна тянуть чужие точки
    idx = ndimage.distance_transform_edt(~mask, return_distances=False, return_indices=True)
    return _bilinear(src[idx[0], idx[1]], k)


def _flatten(curve, steps):
    def P(q):
        return (float(q.x), float(q.y))
    pts = [P(curve.start_point)]
    for s in curve.segments:
        if s.is_corner:
            pts.append(P(s.c))
            pts.append(P(s.end_point))
        else:
            p0, c1, c2, p3 = np.array(pts[-1]), np.array(P(s.c1)), np.array(P(s.c2)), np.array(P(s.end_point))
            for i in range(1, steps + 1):
                t = i / float(steps)
                p = (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t * t * c2 + t ** 3 * p3
                pts.append((float(p[0]), float(p[1])))
    return pts


def _area(pts):
    a = np.array(pts)
    return 0.5 * abs(float(np.dot(a[:, 0], np.roll(a[:, 1], -1)) - np.dot(a[:, 1], np.roll(a[:, 0], -1))))


def _fit(pts, i, j, tol, out):
    """Ломаная по точкам pts[i..j]: если они ложатся на прямую (с допуском tol) — один отрезок по прямой
    наименьших квадратов, иначе делим в самой далёкой от хорды точке."""
    seg = pts[i:j + 1]
    c = seg.mean(0)
    if j - i >= 2:
        u, sv, vt = np.linalg.svd(seg - c)
        d = vt[0]
        dev = np.abs((seg - c).dot(vt[1]))
        if dev.max() <= tol:
            t = (seg - c).dot(d)
            out.append((c + d * t[0], c + d * t[-1]))
            return
        ch = pts[j] - pts[i]
        n = np.array([-ch[1], ch[0]]) / max(1e-9, float(np.hypot(ch[0], ch[1])))
        far = np.abs((seg - pts[i]).dot(n))
        m = i + int(far.argmax())
        if m == i or m == j:
            m = (i + j) // 2
        _fit(pts, i, m, tol, out)
        _fit(pts, m, j, tol, out)
    else:
        out.append((pts[i], pts[j]))


def thin_lines(mask, tol=0.6, least=4):
    """Тонкие линии маски (в одну точку шириной) — ломаными по их серединам: [[(x, y), …], …] в точках.

    potrace такие линии портит: у оптимального многоугольника для полоски в одну точку три стороны, и линия
    выходит клином.  Поэтому швы и обводки проводим отдельно, пером постоянной ширины."""
    from scipy import ndimage
    from collections import deque
    thick = ndimage.binary_opening(mask, structure=np.ones((2, 2), bool))
    thin = mask & ~thick
    lab, n = ndimage.label(thin, structure=np.ones((3, 3), bool))
    lines = []
    for comp in range(1, n + 1):
        cells = set((int(x), int(y)) for y, x in np.argwhere(lab == comp))
        while len(cells) >= least:
            def nbrs(c):
                x, y = c
                res = [q for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if q in cells]
                for dx in (-1, 1):
                    for dy in (-1, 1):
                        q = (x + dx, y + dy)
                        if q in cells and (x + dx, y) not in cells and (x, y + dy) not in cells:
                            res.append(q)
                return res

            def far(src):
                prev = {src: None}
                dq = deque([src])
                last = src
                while dq:
                    c = dq.popleft()
                    last = c
                    for q in nbrs(c):
                        if q not in prev:
                            prev[q] = c
                            dq.append(q)
                return last, prev
            a, _ = far(min(cells))
            b, prev = far(a)
            path = []
            c = b
            while c is not None:
                path.append(c)
                c = prev[c]
            if len(path) < least:
                break
            pts = np.array(path, dtype=np.float64) + 0.5
            segs = []
            _fit(pts, 0, len(pts) - 1, tol, segs)
            line = [tuple(segs[0][0])]
            for q in range(len(segs)):
                if q + 1 < len(segs):
                    line.append(tuple((segs[q][1] + segs[q + 1][0]) * 0.5))
                else:
                    line.append(tuple(segs[q][1]))
            lines.append(line)
            cells -= set(path)
    return lines


def coverage(mask, k, alphamax=0.0, ss=4, pen=0.9):
    """Маска, обведённая заново и закрашенная в k раз крупнее: доля покрытия каждой точки, 0..1."""
    import potrace
    from PIL import Image, ImageDraw
    h, w = mask.shape
    if not mask.any():
        return np.zeros((h * k, w * k), np.float32)
    # potracer считает закрашенным «чёрное» (False)
    path = potrace.Bitmap(~mask).trace(turdsize=0, turnpolicy=potrace.POTRACE_TURNPOLICY_MINORITY,
                                       alphamax=alphamax, opticurve=False)
    polys = []
    for c in path:
        pts = _flatten(c, 8)
        polys.append((_area(pts), bool(c._path.sign), pts))
    polys.sort(key=lambda q: -q[0])                 # сначала внешние контуры, потом их дыры, потом острова в дырах
    s = k * ss
    img = Image.new('L', (w * s, h * s), 0)
    dr = ImageDraw.Draw(img)
    for a, sign, pts in polys:
        dr.polygon([(x * s, y * s) for x, y in pts], fill=255 if sign else 0)
    # тонкие линии — пером шириной pen точек исходника, со скруглёнными концами и изломами
    r = pen * s * 0.5
    for line in thin_lines(mask):
        q = [(x * s, y * s) for x, y in line]
        dr.line(q, fill=255, width=int(round(r * 2)))
        for (x, y) in q:
            dr.ellipse((x - r, y - r, x + r, y + r), fill=255)
    big = np.asarray(img, dtype=np.float32) / 255.0
    return big.reshape(h * k, ss, w * k, ss).mean((1, 3))


def upscale(rgb, paint, shade, k=8, levels=(), shades=(), keep=None, alphamax=0.0):
    """rgb (h, w, 3) — картинка, paint (h, w) bool — где краска, shade (h, w) — светотень краски (0..255,
    127.5 — ровная краска).

    levels — пороги яркости для слоёв некрашеного; shades — пороги светотени (в долях ровной краски, по
    убыванию) для слоёв краски: тёмные швы и тени на краске обводятся так же, как стёкла.  keep (h, w) bool —
    точки, которые остаются пиксельными (колесо: рисунок диска мелкий, обводка его только портит).

    Возвращает (rgba, shade) в k раз крупнее: у rgba прозрачно там, где краска."""
    lum = rgb.astype(np.float32).dot(np.array([0.30, 0.59, 0.11], np.float32))
    solid = ~paint
    alpha = coverage(solid, k, alphamax)
    lv = [-1.0] + [float(v) for v in levels] + [1e9]
    col = field(rgb, solid & (lum < lv[1]), k)
    for i in range(1, len(lv) - 1):
        m = solid & (lum >= lv[i])
        if not m.any():
            continue
        c = coverage(m, k, alphamax)[..., None]
        col = col * (1.0 - c) + field(rgb, m & (lum < lv[i + 1]), k) * c
    # краска: ровная — основа, поверх неё слои потемнее; каждый слой обводится вместе с некрашеным,
    # чтобы между тенью у стекла и самим стеклом не оставалось щели
    rel = shade.astype(np.float32) / 127.5
    sv = [1e9] + [float(v) for v in shades] + [-1.0]
    sh = field(shade.astype(np.float32)[..., None], paint & (rel >= sv[1]), k)[..., 0]
    for i in range(1, len(sv) - 1):
        m = paint & (rel < sv[i])
        if not m.any():
            continue
        c = coverage(m | solid, k, alphamax)
        sh = sh * (1.0 - c) + field(shade.astype(np.float32)[..., None], m & (rel >= sv[i + 1]), k)[..., 0] * c
    if keep is not None and keep.any():
        big = np.repeat(np.repeat(keep, k, 0), k, 1)
        nn = np.repeat(np.repeat(rgb, k, 0), k, 1)
        col = np.where(big[..., None], nn, col)
        alpha = np.where(big, np.repeat(np.repeat(solid, k, 0), k, 1).astype(np.float32), alpha)
        sh = np.where(big, np.repeat(np.repeat(shade.astype(np.float32), k, 0), k, 1), sh)
    out = np.zeros(alpha.shape + (4,), np.uint8)
    out[..., :3] = np.clip(col + 0.5, 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(alpha * 255.0 + 0.5, 0, 255).astype(np.uint8)
    sh = np.where(alpha >= 0.999, 128.0, sh)        # под некрашеным светотень не нужна
    return out, np.clip(sh + 0.5, 0, 255).astype(np.uint8)
