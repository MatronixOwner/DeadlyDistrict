# -*- coding: utf-8 -*-
"""Отладка: рендер всех машин и нескольких персонажей в PNG."""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panda3d.core import loadPrcFileData, Filename, AmbientLight, DirectionalLight, LColor, CardMaker
loadPrcFileData('', 'window-type offscreen\nload-display p3tinydisplay\nwin-size 1280 720\naudio-library-name null\nsync-video 0\n')
from direct.showbase.ShowBase import ShowBase
from game.assets import Assets
from game import vehicle, ped, defs

base = ShowBase(); base.disableMouse()
assets = Assets(base.loader)
al = AmbientLight('a'); al.setColor(LColor(0.55, 0.56, 0.6, 1)); dl = DirectionalLight('d'); dl.setColor(LColor(0.9, 0.88, 0.8, 1))
alp = base.render.attachNewNode(al); dlp = base.render.attachNewNode(dl); dlp.setHpr(-40, -50, 0)
base.render.setLight(alp); base.render.setLight(dlp)
base.setBackgroundColor(0.55, 0.7, 0.9)
cm = CardMaker('g'); cm.setFrame(-60, 60, -60, 60); g = base.render.attachNewNode(cm.generate()); g.setP(-90); g.setColor(0.3, 0.3, 0.32, 1)
kinds = list(vehicle.SPECS.keys())
random.seed(3)
for n, k in enumerate(kinds):
    spec = vehicle.SPECS[k]
    row, col = divmod(n, 6)
    root = base.render.attachNewNode(k); root.setPos(col * 4.2 - 10.5, row * 12.0, 0); root.setH(-28)
    vehicle.body_template(assets, k, random.randrange(14)).copyTo(root)
    hw = spec.W * 0.5 - spec.wheel_w * 0.5 + 0.03
    for (wx, wy) in ((-hw, spec.front_axle), (hw, spec.front_axle), (-hw, spec.rear_axle), (hw, spec.rear_axle)):
        w = vehicle.wheel_template(assets, k).copyTo(root); w.setPos(wx, wy, spec.wheel_r)
    sh = vehicle.shadow_template(assets).copyTo(root); sh.setScale(spec.W * 0.72, spec.L * 0.62, 1); sh.setZ(0.04)
class W: pass
class C:
    def ground_z(self, x, y): return 0.0
w = W(); w.assets = assets; w.dyn_root = base.render; w.city = C()
looks = [defs.player_look(), defs.cop_look(), defs.swat_look(), defs.fbi_look(), defs.army_look(), defs.medic_look(), defs.gang_look('reds'), defs.gang_look('mafia')]
for z in 'DGIBRO':
    looks.append(defs.random_look(random, z)); looks.append(defs.random_look(random, z))
peds = []
for n, lk in enumerate(looks):
    p = ped.Ped(w, n * 0.9 - 8.5, -7.0, -1.2 if n % 2 else -1.9, lk)
    if n in (1, 2, 4): p.set_weapon(n + 1); p.aiming = True
    if n == 6: p.set_weapon(1)
    p.speed = 1.5 if n % 3 == 0 else 0.0
    p.state = 'stand'; p._animate(0.3)
    peds.append(p)
base.camLens.setFov(50)
shots = [((0, -24, 10), (0, -19, 0)), ((0, -13.5, 1.6), (0, -5, 0)), ((14, -6, 9), (30, -24, 0))]
for i, (pos, hpr) in enumerate(shots):
    base.camera.setPos(*pos); base.camera.setHpr(*hpr)
    base.graphicsEngine.renderFrame(); base.graphicsEngine.renderFrame()
    base.win.saveScreenshot(Filename('/tmp/models_%d.png' % i))
print('ok')
