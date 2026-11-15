# -*- coding: utf-8 -*-
"""Радио: настоящий звуковой движок (OpenAL без устройства), свои песни, переключение станций."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def test_radio_plays_user_music_on_real_audio_engine():
    env = dict(os.environ, ALSOFT_DRIVERS='null')
    env.pop('DD_USER_DIR', None)
    r = subprocess.run([sys.executable, os.path.join(HERE, 'radio_check.py')], env=env, capture_output=True,
                       text=True, timeout=180)
    assert r.returncode == 0 and 'RADIO OK' in r.stdout, r.stdout[-1500:] + r.stderr[-3000:]
