# -*- coding: utf-8 -*-
"""Стресс-тест: бот хаотично жмёт кнопки, игра не должна падать.

    python tests/soak.py [секунд игрового времени] [seed]
"""
import math
import random
import sys
import time
import traceback

import harness
from game.defs import *            # noqa: F401,F403


def main():
    total = float(sys.argv[1]) if len(sys.argv) > 1 else 300.0
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    rnd = random.Random(seed)
    random.seed(seed)
    g = harness.make_game()
    w = harness.start_game(g)
    pl = w.player
    for wid, am in ((W_BAT, None), (W_PISTOL, 500), (W_UZI, 900), (W_SHOTGUN, 200), (W_AK, 900), (W_ROCKET, 40),
                    (W_GRENADE, 40), (W_MOLOTOV, 40)):
        pl.give_weapon(wid, am, select=False)
    pl.add_money(5000)
    dt = 1.0 / 30.0
    t = 0.0
    held = set()
    keys = ['w', 'w', 'w', 'a', 'd', 's', 'shift', 'space', 'mouse1', 'mouse1', 'mouse3']
    taps = ['f', 'f', 'e', 'q', 'h', 'r', 'c', 't', '1', '3', '5', '7', '8', '9', 'enter']
    next_change = 0.0
    t0 = time.time()
    frames = 0
    try:
        while t < total:
            if t >= next_change:
                next_change = t + rnd.uniform(0.3, 2.5)
                for k in list(held):
                    if rnd.random() < 0.5:
                        g.inp._up(k)
                        held.discard(k)
                for _ in range(rnd.randint(0, 3)):
                    k = rnd.choice(keys)
                    g.inp._dn(k)
                    held.add(k)
                if rnd.random() < 0.5:
                    k = rnd.choice(taps)
                    g.inp._dn(k)
                    g.inp._up(k)
                # иногда — особые события
                r = rnd.random()
                if r < 0.03:
                    w.police.set_level(rnd.randint(1, 6))
                elif r < 0.05:
                    lm = rnd.choice(list(w.city.landmarks.values()))
                    pl.teleport(lm['road'][0], lm['road'][1])
                elif r < 0.06:
                    w.sky.set_time(rnd.uniform(0, 24))
                    w.sky.set_weather(rnd.choice(['clear', 'cloudy', 'rain', 'fog']))
                elif r < 0.08 and g.state == 'play':
                    g.pause()
                    for _ in range(3):
                        g.step(dt)
                    g.resume()
                elif r < 0.09 and w.missions.active is None and pl.state == 'foot':
                    from game import missions as M
                    w.missions.fail_cd = 0
                    w.police.clear()
                    w.missions.start(rnd.choice(M.MISSIONS))
                elif r < 0.10:
                    pl.ped.health = pl.ped.max_health
                elif r < 0.22 and pl.state == 'foot' and g.state == 'play':
                    # сесть в ближайшую машину (в том числе угнать у водителя)
                    v = w.nearest_vehicle(pl.ped.x, pl.ped.y, 90.0, lambda q: not q.dead and not q.sunk)
                    if v is not None:
                        for k in list(held):
                            g.inp._up(k)
                        held.clear()
                        x, y = v.door_pos(-1)
                        pl.ped.x, pl.ped.y = x - 1.0, y
                        g.inp._dn('f')
                        g.inp._up('f')
                        for _ in range(45):
                            g.step(dt)
                            t += dt
                elif r < 0.25 and pl.vehicle is not None:
                    pl.vehicle.health = pl.vehicle.max_health
            # мышь
            g.inp.mouse_dx = rnd.uniform(-30, 30) if rnd.random() < 0.3 else 0.0
            w.cam.yaw += g.inp.mouse_dx * 0.003
            w.cam.pitch = max(-0.6, min(0.4, w.cam.pitch + rnd.uniform(-0.02, 0.02)))
            if g.state != 'play':
                # магазин или финальные титры — закрываем
                g.inp._dn('escape')
                g.inp._up('escape')
            g.step(dt)
            t += dt
            frames += 1
            if frames % 1800 == 0:
                print('t=%4.0fs state=%s pl=%s hp=%3.0f wanted=%d veh=%d peds=%d fx=%d mission=%s stats=%s' % (
                    t, g.state, pl.state, pl.ped.health, w.police.level, len(w.vehicles), len(w.peds),
                    len(w.fx.active), w.missions.active.spec['id'] if w.missions.active else None,
                    dict((k, int(v)) for k, v in w.stats.items())))
                sys.stdout.flush()
    except Exception:
        traceback.print_exc()
        print('FAILED at t=%.1f state=%s player=%s' % (t, g.state, pl.state))
        return 1
    if g._errors_total:
        print('FAILED: %d ошибок в сценариях заданий (см. вывод выше)' % g._errors_total)
        return 1
    el = time.time() - t0
    print('SOAK OK: %.0f s game time in %.1f s (%.1fx), %.2f ms/frame' % (t, el, t / el, el / frames * 1000))
    return 0


if __name__ == '__main__':
    sys.exit(main())
