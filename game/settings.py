# -*- coding: utf-8 -*-
"""Настройки, пути и сохранения."""
import os
import sys
import json

APP_NAME = 'DeadlyDistrict'

DEFAULTS = {
    'cfg': 0,                  # версия настроек экрана (см. CFG_VERSION)
    'screen': 1,               # 0 окно, 1 во весь экран без рамки, 2 полноэкранный режим
    'fullscreen': False,       # старый ключ (до версии 0.3); теперь режим задаёт 'screen'
    'width': 1280,
    'height': 720,
    'vsync': True,
    'msaa': 4,                 # сглаживание краёв: 0, 2, 4 или 8 выборок
    'smooth_textures': False,  # False — чёткие пиксели, True — сглаженные текстуры
    'mouse_sens': 1.0,
    'invert_y': False,
    'sfx_volume': 0.8,
    'music_volume': 0.5,
    'draw_distance': 1,        # 0 близко, 1 средне, 2 далеко
    'traffic': 1,              # 0 мало, 1 норма, 2 много
    'show_fps': False,
    'blood': True,
}

# Версия настроек экрана.  Если в файле настроек она меньше, режим экрана подбирается заново:
# в версиях до 0.3 окно на экранах с масштабом Windows 125–150 % выбиралось слишком маленьким,
# а полноэкранный режим включался в заниженном разрешении — отсюда «мыльная» картинка.
CFG_VERSION = 3

SCREEN_WINDOW, SCREEN_BORDERLESS, SCREEN_EXCLUSIVE = 0, 1, 2
SCREEN_NAMES = ('В окне', 'Во весь экран', 'Полноэкранный режим')
MSAA_LEVELS = (0, 2, 4, 8)

DRAW_DIST = [(260.0, 340.0), (440.0, 560.0), (760.0, 940.0)]      # (начало тумана, дальняя плоскость)
TRAFFIC_LEVELS = [(10, 14), (18, 26), (26, 36)]                   # (машины, пешеходы)


def user_dir():
    """Папка для настроек и сохранений (создаётся при необходимости)."""
    if sys.platform.startswith('win'):
        # та же папка, куда собранное приложение пишет журнал output.log
        base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or os.path.expanduser('~')
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


_dpi_done = [False]


def dpi_aware():
    """Сообщить Windows, что игра сама работает с настоящими пикселями экрана.

    Без этого при масштабе 125–150 % система сообщает уменьшенный размер экрана, а готовую картинку
    растягивает — она выходит мутной."""
    if _dpi_done[0] or not sys.platform.startswith('win'):
        return
    _dpi_done[0] = True
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)        # Windows 8.1+: по каждому монитору
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()             # Vista / 7 / 8
    except Exception:
        pass


def desktop_size():
    """Размер основного экрана в настоящих пикселях или (0, 0), если узнать его не удалось."""
    if sys.platform.startswith('win'):
        try:
            import ctypes
            dpi_aware()
            user32 = ctypes.windll.user32
            return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
        except Exception:
            pass
    return 0, 0


def choose_screen(settings, desktop, sizes):
    """Режим экрана для первого запуска (и после обновления со старой версии).

    Экран известен — игра занимает его целиком в родном разрешении, без рамки и без смены
    видеорежима: так картинка самая чёткая.  Неизвестен — обычное окно."""
    dw, dh = desktop
    if dw >= 800 and dh >= 600:
        settings.set('screen', SCREEN_BORDERLESS)
        settings.set('width', int(dw))
        settings.set('height', int(dh))
    else:
        settings.set('screen', SCREEN_WINDOW)
        size = fit_window(sizes, desktop)
        if size is not None:
            settings.set('width', size[0])
            settings.set('height', size[1])
    if dw * dh > 2560 * 1440:
        # на экранах 4K точек вчетверо больше, чем в Full HD: сглаживание краёв там почти не заметно,
        # а встроенной видеокарте оно обходится дорого
        settings.set('msaa', 0)
    settings.set('fullscreen', False)
    settings.set('cfg', CFG_VERSION)


def fit_window(sizes, desktop):
    """Самое большое окно из списка, которое помещается на экране вместе с рамкой и панелью задач."""
    dw, dh = desktop
    if dw <= 0 or dh <= 0:
        return None
    fits = [(w, h) for (w, h) in sizes if w <= dw - 60 and h <= dh - 120]
    if not fits:
        return min(sizes)
    return max(fits)


class Settings(object):

    def __init__(self):
        self.path = os.path.join(user_dir(), 'settings.json')
        self.data = dict(DEFAULTS)
        self.fresh = True                 # файла настроек ещё нет (первый запуск)
        self.load()

    def load(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                d = json.load(f)
            for k, v in d.items():
                if k in DEFAULTS and isinstance(v, type(DEFAULTS[k])):
                    self.data[k] = v
            self.fresh = False
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
