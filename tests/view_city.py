# -*- coding: utf-8 -*-
"""Отладочный просмотр города без окна: python tests/view_city.py out.png x y z h p [night]"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panda3d.core import loadPrcFileData, Filename, AmbientLight, DirectionalLight, Fog, LVector3, LColor
loadPrcFileData('', 'window-type offscreen\nload-display p3tinydisplay\nwin-size 960 540\naudio-library-name null\nsync-video 0\n')
from direct.showbase.ShowBase import ShowBase
from game.city import City
from game.citymesh import CityMesh
from game.collision import StaticWorld
from game.assets import Assets

def main():
    out = sys.argv[1]
    views = []
    args = sys.argv[2:]
    night = 'night' in args
    args = [a for a in args if a != 'night']
    base = ShowBase()
    base.disableMouse()
    t = time.time()
    city = City()
    assets = Assets(base.loader)
    static = StaticWorld()
    cm = CityMesh(city, assets, static, base.render)
    print('mesh build %.2fs' % (time.time() - t), 'missing tex:', sorted(set(assets.missing)))
    print('geoms:', base.render.findAllMatches('**/+GeomNode').getNumPaths(), 'static boxes', len(static.boxes), 'circles', len(static.circles), 'breakables', len(cm.breakables))
    al = AmbientLight('a'); dl = DirectionalLight('d')
    if night:
        al.setColor(LColor(0.22, 0.24, 0.34, 1)); dl.setColor(LColor(0.16, 0.18, 0.28, 1))
        sky = LColor(0.03, 0.04, 0.09, 1)
        cm.night_root.show()
    else:
        al.setColor(LColor(0.52, 0.54, 0.60, 1)); dl.setColor(LColor(0.95, 0.90, 0.80, 1))
        sky = LColor(0.56, 0.72, 0.92, 1)
        cm.night_root.hide()
    cm.night_root.setLightOff(1)
    alp = base.render.attachNewNode(al); dlp = base.render.attachNewNode(dl)
    dlp.setHpr(-35, -50, 0)
    base.render.setLight(alp); base.render.setLight(dlp)
    fog = Fog('f'); fog.setColor(sky); fog.setLinearRange(200, 520)
    base.render.setFog(fog)
    base.setBackgroundColor(sky)
    base.camLens.setNearFar(0.4, 620); base.camLens.setFov(70)
    cm.update_signals(0, lambda ph, ax: 'g' if ax == 0 else 'r')
    n = 0
    while len(args) >= 5:
        x, y, z, h, p = [float(v) for v in args[:5]]; args = args[5:]
        base.camera.setPos(x, y, z); base.camera.setHpr(h, p, 0)
        t = time.time()
        base.graphicsEngine.renderFrame(); base.graphicsEngine.renderFrame()
        dt = time.time() - t
        name = out if n == 0 else out.replace('.png', '_%d.png' % n)
        base.win.saveScreenshot(Filename(name))
        print('saved', name, 'frame %.2fs' % (dt / 2))
        n += 1

main()
