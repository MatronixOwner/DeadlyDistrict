# -*- coding: utf-8 -*-
"""Сборка игры в готовое приложение.

    python setup.py build_apps               -> build/win_amd64/DeadlyDistrict.exe (+ DLL и assets)
    DD_TESTER=1 python setup.py build_apps   -> build/win_amd64/DeadlyDistrict-tester.exe: сборка для тестера

Собирать можно на любой ОС: нужные файлы для Windows скачиваются из PyPI.

Сборка для тестера — та же игра с меню тестера на F9 (game/tester.py, точка входа tester_main.py).
В обычную сборку модуль game.tester не попадает: он исключён явно.
"""
import os

from setuptools import setup

from game import __version__

TESTER = bool(os.environ.get('DD_TESTER'))
APP = 'DeadlyDistrict-tester' if TESTER else 'DeadlyDistrict'
MAIN = 'tester_main.py' if TESTER else 'main.py'

setup(
    name=APP,
    version=__version__,
    description='Deadly District — криминальный боевик в открытом мире в духе GTA III',
    options={
        'build_apps': {
            'gui_apps': {
                APP: MAIN,
            },
            'console_apps': ({APP + '-selftest': MAIN} if os.environ.get('DD_SELFTEST') else {}),
            # DD_PLATFORMS=manylinux2014_x86_64,win_amd64 — собрать под другие платформы
            'platforms': os.environ.get('DD_PLATFORMS', 'win_amd64').split(','),
            'plugins': ['pandagl', 'p3openal_audio', 'p3tinydisplay', 'p3ffmpeg'],
            'include_patterns': [
                'assets/tex/*.png',
                'assets/fonts/*',
                'assets/sfx/*.wav',
                'assets/sfx/*.mp3',
                'assets/music/*.ogg',
                'assets/icon/*',
                'assets/models/*.json',
                'assets/models/*.md',
                'assets/models/chars/*.bam',
                'assets/models/chars/*.png',        # текстуры персонажей
                'assets/models/anims/*.bam',
                'assets/models/furn/*.bam',         # мебель для интерьеров
                'assets/models/furn/*.png',
                'assets/models/furn/*.json',
                'assets/models/veh/*.bam',
                'assets/models/veh/*.png',          # слои краски и деталей машин
                'assets/models/weapons/*.bam',
                'assets/models/weapons/*.png',      # текстуры оружия
                'assets/terrain/*',                 # рельеф: высоты и готовая геометрия
            ],
            'include_modules': {'*': ['game.*']},
            # меню тестера — только в сборке для тестера
            'exclude_modules': {} if TESTER else {'*': ['game.tester']},
            'icons': {
                APP: [
                    'assets/icon/icon-256.png',
                    'assets/icon/icon-128.png',
                    'assets/icon/icon-64.png',
                    'assets/icon/icon-48.png',
                    'assets/icon/icon-32.png',
                    'assets/icon/icon-16.png',
                ],
            },
            'log_filename': '$USER_APPDATA/%s/output.log' % APP,
            'log_append': False,
            'requirements_path': 'requirements.txt',
        },
    },
)
