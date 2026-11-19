# -*- coding: utf-8 -*-
"""Отладочные виды игры без окна: несколько кадров на одном листе (только для разработки).

    python tests/view.py out.jpg [параметры] ВИД [ВИД ...]

ВИД (координаты мира; с приставкой «p:» — координаты чертежа, см. game/warp.py):
    x,y,h            сверху: с высоты h на точку (x, y)
    x,y,z,tx,ty,tz   из точки (x, y, z) на точку (tx, ty, tz)
    ...!             «далёкий» кадр: без тумана, дальняя плоскость 9 км (карта целиком)
    ...@             перед кадром перенести героя в точку, куда смотрит камера, и дать городу ожить

Параметры:
    hour=23.5  weather=rain  size=960x640  cols=2  hud  intro (не пропускать пролог)  run=2.0 (секунд перед кадрами)

Рендер — как в tests/harness.py: программный TinyDisplay либо OpenGL без окна (DD_TEST_DISPLAY=p3headlessgl).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness                                      # noqa: E402


def parse(spec):
    far = tp = plan = False
    while spec and spec[-1] in '!@':
        far = far or spec[-1] == '!'
        tp = tp or spec[-1] == '@'
        spec = spec[:-1]
    if spec.startswith('p:'):
        plan = True
        spec = spec[2:]
    v = [float(s) for s in spec.split(',')]
    return v, far, tp, plan


def main(argv):
    out = argv[0]
    opts = dict(hour=None, weather=None, size='960x640', cols='2', run='0')
    flags = set()
    views = []
    for a in argv[1:]:
        if '=' in a and a.split('=')[0] in opts:
            k, v = a.split('=', 1)
            opts[k] = v
        elif a in ('hud', 'intro'):
            flags.add(a)
        else:
            views.append(parse(a))
    wd, ht = [int(v) for v in opts['size'].split('x')]
    t0 = time.time()
    g = harness.make_game(wd, ht)
    if 'intro' in flags:
        g.new_game()
        w = g.world
    else:
        w = harness.start_game(g)
    print('make_game %.2f' % (time.time() - t0))
    c = w.city
    if opts['hour'] is not None:
        w.sky.set_time(float(opts['hour']))
    if opts['weather'] is not None:
        w.sky.set_weather(opts['weather'])
    w.sky.time_scale = 0.0
    if 'hud' not in flags:
        w.hud.show(False)
    if float(opts['run']) > 0.0:
        harness.run(g, float(opts['run']))
    from PIL import Image
    shots = []
    base = g.base
    for k, (v, far, tp, plan) in enumerate(views):
        if len(v) == 3:
            x, y, h = v
            if plan:
                x, y = c.to_world(x, y)
            cam = (x, y - h * 0.02, h, x, y, 0.0)
        else:
            x, y, z, tx, ty, tz = v
            if plan:
                x, y = c.to_world(x, y)
                tx, ty = c.to_world(tx, ty)
            cam = (x, y, z, tx, ty, tz)
        if tp:
            w.player.teleport(cam[3], cam[4])
            harness.run(g, 1.5)
        w.cam.override = cam
        harness.run(g, 1.0 / 30.0 + 1e-4)
        if far:
            w.root.setFogOff(10)
            base.camLens.setNearFar(2.0, 9000.0)
        path = '%s.%d.png' % (out, k)
        t1 = time.time()
        harness.shot(g, path)
        print('view %d: %.1f s' % (k, time.time() - t1))
        if far:
            w.root.setFog(w.sky.fog)
        shots.append(Image.open(path).convert('RGB'))
        os.remove(path)
    w.cam.override = None
    if not shots:
        return 0
    cols = min(int(opts['cols']), len(shots))
    rows = (len(shots) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * wd, rows * ht), (20, 20, 20))
    for k, im in enumerate(shots):
        sheet.paste(im, ((k % cols) * wd, (k // cols) * ht))
    if sheet.size[0] > 1920:
        sheet = sheet.resize((1920, int(sheet.size[1] * 1920.0 / sheet.size[0])), Image.LANCZOS)
    sheet.save(out, quality=88)
    print('saved', out, sheet.size)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
