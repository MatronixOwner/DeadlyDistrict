# -*- coding: utf-8 -*-
"""Настройки, пути и сохранения."""
import os
import sys
import json

APP_NAME = 'DeadlyDistrict'

DEFAULTS = {
    'fullscreen': False,
    'width': 1280,
    'height': 720,
    'vsync': True,
    'mouse_sens': 1.0,
    'invert_y': False,
    'sfx_volume': 0.8,
    'music_volume': 0.5,
    'draw_distance': 1,        # 0 близко, 1 средне, 2 далеко
    'traffic': 1,              # 0 мало, 1 норма, 2 много
    'show_fps': False,
    'retro': False,            # «пиксельный» рендер в низком разрешении
    'blood': True,
}

DRAW_DIST = [(240.0, 300.0), (360.0, 440.0), (520.0, 620.0)]      # (начало тумана, дальняя плоскость)
TRAFFIC_LEVELS = [(10, 14), (18, 26), (26, 36)]                   # (машины, пешеходы)


def user_dir():
    """Папка для настроек и сохранений (создаётся при необходимости)."""
    if sys.platform.startswith('win'):
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    elif sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    override = os.environ.get('DD_USER_DIR')
    path = override if override else os.path.join(base, APP_NAME)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        path = os.getcwd()
    return path


def find_root():
    """Найти папку, в которой лежит assets/ (и при запуске из исходников, и из exe)."""
    cands = []
    if os.environ.get('DD_ROOT'):
        cands.append(os.environ['DD_ROOT'])
    try:
        cands.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    except Exception:
        pass
    try:
        from panda3d.core import ExecutionEnvironment, Filename
        md = ExecutionEnvironment.getEnvironmentVariable('MAIN_DIR')
        if md:
            cands.append(Filename(md).toOsSpecific())
    except Exception:
        pass
    try:
        cands.append(os.path.dirname(os.path.abspath(sys.executable)))
    except Exception:
        pass
    try:
        cands.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    except Exception:
        pass
    cands.append(os.getcwd())
    for c in cands:
        try:
            if c and os.path.isdir(os.path.join(c, 'assets', 'tex')):
                return c
        except Exception:
            pass
    return cands[0] if cands else os.getcwd()


class Settings(object):

    def __init__(self):
        self.path = os.path.join(user_dir(), 'settings.json')
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                d = json.load(f)
            for k, v in d.items():
                if k in DEFAULTS and isinstance(v, type(DEFAULTS[k])):
                    self.data[k] = v
        except Exception:
            pass

    def save(self):
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=1)
        except Exception:
            pass

    def __getitem__(self, k):
        return self.data.get(k, DEFAULTS.get(k))

    def __setitem__(self, k, v):
        self.data[k] = v

    def get(self, k):
        return self.data.get(k, DEFAULTS.get(k))

    def set(self, k, v):
        self.data[k] = v


def save_path(slot=0):
    return os.path.join(user_dir(), 'save%d.json' % slot)


def load_save(slot=0):
    try:
        with open(save_path(slot), 'r', encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d, dict) and d.get('version') == 1:
            return d
    except Exception:
        pass
    return None


def write_save(data, slot=0):
    try:
        data = dict(data)
        data['version'] = 1
        tmp = save_path(slot) + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, save_path(slot))
        return True
    except Exception:
        return False
