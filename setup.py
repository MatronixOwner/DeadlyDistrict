# -*- coding: utf-8 -*-
"""Сборка игры в готовое приложение.

    python setup.py build_apps      -> build/win_amd64/DeadlyDistrict.exe (+ DLL и assets)

Собирать можно на любой ОС: нужные файлы для Windows скачиваются из PyPI.
"""
import os

from setuptools import setup

from game import __version__

setup(
    name='DeadlyDistrict',
    version=__version__,
    description='Deadly District — криминальный боевик в открытом мире в духе GTA III',
    options={
        'build_apps': {
            'gui_apps': {
                'DeadlyDistrict': 'main.py',
            },
            'console_apps': ({'DeadlyDistrict-selftest': 'main.py'} if os.environ.get('DD_SELFTEST') else {}),
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
                'assets/models/veh/*.bam',
                'assets/models/veh/*.png',          # слои краски и деталей машин
                'assets/models/weapons/*.bam',
                'assets/terrain/*',                 # рельеф: высоты и готовая геометрия
            ],
            'include_modules': {'*': ['game.*']},
            'icons': {
                'DeadlyDistrict': [
                    'assets/icon/icon-256.png',
                    'assets/icon/icon-128.png',
                    'assets/icon/icon-64.png',
                    'assets/icon/icon-48.png',
                    'assets/icon/icon-32.png',
                    'assets/icon/icon-16.png',
                ],
            },
            'log_filename': '$USER_APPDATA/DeadlyDistrict/output.log',
            'log_append': False,
            'requirements_path': 'requirements.txt',
        },
    },
)
