# -*- coding: utf-8 -*-
"""Проверка радио на НАСТОЯЩЕМ звуковом движке (OpenAL), без звуковой карты.

Запускается отдельным процессом (см. test_radio.py): звуковая библиотека выбирается при старте.
    ALSOFT_DRIVERS=null python tests/radio_check.py
Если задать ALSOFT_DRIVERS=wave и ALSOFT_CONF с [wave] file=..., OpenAL запишет в файл то,
что игрок услышал бы из колонок.
"""
import math
import os
import shutil
import struct
import sys
import tempfile
import time
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

os.environ.setdefault('ALSOFT_DRIVERS', 'null')
USER = tempfile.mkdtemp(prefix='dd_radio_')
os.environ['DD_USER_DIR'] = USER


def tone(path, freq, seconds, rate=22050):
    n = int(seconds * rate)
    data = [int(12000 * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)]
    if path.endswith('.wav'):
        with wave.open(path, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(struct.pack('<%dh' % n, *data))
    elif path.endswith('.ogg'):
        import numpy as np
        import soundfile as sf
        sf.write(path, np.array(data, dtype='float32') / 32768.0, rate, format='OGG', subtype='VORBIS')
    elif path.endswith('.flac'):
        import numpy as np
        import soundfile as sf
        sf.write(path, np.array(data, dtype='float32') / 32768.0, rate, format='FLAC')
    elif path.endswith('.m4a'):
        import av                                           # PyAV: только чтобы сделать тестовый файл
        import numpy as np
        out = av.open(path, 'w', format='mp4')
        st = out.add_stream('aac', rate=rate)
        st.layout = 'mono'
        fr = av.AudioFrame.from_ndarray(np.array(data, dtype='int16').reshape(1, -1), format='s16', layout='mono')
        fr.sample_rate = rate
        rs = av.AudioResampler(format=st.codec_context.format, layout='mono', rate=rate)
        for f in rs.resample(fr):
            for pk in st.encode(f):
                out.mux(pk)
        for pk in st.encode(None):
            out.mux(pk)
        out.close()
    elif path.endswith('.mp3'):
        import lameenc
        enc = lameenc.Encoder()
        enc.set_bit_rate(96)
        enc.set_in_sample_rate(rate)
        enc.set_channels(1)
        enc.set_quality(7)
        raw = enc.encode(struct.pack('<%dh' % n, *data)) + enc.flush()
        with open(path, 'wb') as f:
            f.write(raw)


def main():
    mdir = os.path.join(USER, 'music')
    os.makedirs(os.path.join(mdir, 'Подборка'))
    names = ['Глюкоза - Швайне.mp3', '02. Дорожная.ogg', os.path.join('Подборка', 'трек_три.wav'),
             'Четвёртая.flac', os.path.join('Подборка', 'Пятая.m4a')]
    made = []
    for i, n in enumerate(names):
        try:
            tone(os.path.join(mdir, n), 330.0 + 110.0 * i, 1.2)
            made.append(n)
        except ImportError:
            pass                    # нет кодировщика для теста — формат пропускаем
    with open(os.path.join(mdir, 'заметки.txt'), 'w') as f:
        f.write('не музыка')

    from panda3d.core import loadPrcFileData
    loadPrcFileData('', 'window-type offscreen\nload-display p3tinydisplay\nwin-size 320 200\nsync-video 0\n'
                        'textures-power-2 none\nnotify-level-device fatal\n')
    from game import app as appmod
    from game.settings import Settings
    appmod.configure(Settings(), headless=True)          # включает p3openal_audio и ffmpeg
    from direct.showbase.ShowBase import ShowBase
    base = ShowBase()
    g = appmod.Game(base=base, headless=True)
    import harness
    harness._game[0] = g
    from game import audio as A
    w = harness.start_game(g)
    harness.quiet(w, peds=True)
    au = g.audio
    pl = w.player

    def frames(sec, real=False):
        t0 = time.time()
        n = max(1, int(sec * 30))
        for _ in range(n):
            g.step(1 / 30.0)
            base.taskMgr.step()                           # звуковой менеджер обновляется задачей ShowBase
            if real:
                time.sleep(max(0.0, 1 / 30.0 - 0.004))
        return time.time() - t0

    def playing():
        s = au.music_snd
        return s is not None and s.status() == s.PLAYING

    def started(timeout=3.0):
        """Дождаться, пока звуковой движок действительно заиграет: на занятой машине это не мгновенно."""
        t0 = time.time()
        while not playing() and time.time() - t0 < timeout:
            frames(0.1, real=True)
        return playing()

    assert base.musicManager is not None and base.musicManager.isValid(), 'звуковой движок не запустился'
    tracks = A.scan_tracks()
    assert len(tracks) == len(made), tracks
    assert A.track_title('x/Глюкоза - Швайне.mp3') == 'Глюкоза — Швайне'
    assert A.track_title('02. Дорожная.ogg') == 'Дорожная'

    frames(0.3)
    assert not playing(), 'пешком радио молчит'
    x, y = w.city.landmarks['terminal']['road']
    car = w.spawn_vehicle('sedan', x, y - 1.5, 0.0)
    car.radio = A.USER_STATION
    pl.teleport(x, y - 4.0)
    pl.enter_vehicle(car, silent=True)
    frames(0.3)
    assert au.station == A.USER_STATION and started(), 'в машине радио не заиграло'
    assert au.user_tracks == len(made)
    heard = set()
    for _ in range(len(made)):
        t = au.playlist[au.track_i][1]
        assert playing() and au.music_snd.length() > 0.5, 'не читается: %s' % t
        heard.add(t)
        assert au.next_track()
        frames(0.1)
    want = {A.track_title(n) for n in made}
    assert heard == want, (heard, want)

    # песня кончилась — сама включается следующая
    # (ждём по настоящим часам: тестовые песни длятся чуть больше секунды; считаем смены, а не сравниваем
    #  номера — за это время список может успеть пройти по кругу)
    i0 = au.track_i
    changed = False
    t0 = time.time()
    while time.time() - t0 < 6.0 and not changed:
        frames(0.1, real=True)
        changed = au.track_i != i0
    frames(0.1)
    assert changed and playing(), 'после конца песни следующая не началась'

    # R — следующая станция; каждая что-то играет, последняя — тишина
    for k in range(1, len(A.STATIONS)):
        harness.press(g, 'r')
        frames(0.2)
        assert car.radio == k and w.radio_pref == k
        if A.STATIONS[k][1] is None:
            assert not playing(), 'станция «выключено» должна молчать'
        else:
            assert started(), 'молчит станция %s' % A.STATIONS[k][0]
    harness.press(g, 'r')
    frames(0.2)
    assert car.radio == A.USER_STATION and started()

    # вышел из машины — тишина; сел в другую — та же станция
    pl.leave_vehicle(force=True)
    frames(0.3)
    assert not playing()
    car2 = w.spawn_vehicle('hatch', x + 8.0, y - 1.5, 0.0)
    car2.radio = 3
    pl.enter_vehicle(car2, silent=True)
    frames(0.3)
    assert car2.radio == A.USER_STATION and started()

    # без своих песен станция не молчит: играет программа из музыки игры
    pl.leave_vehicle(force=True)
    frames(0.2)
    shutil.rmtree(mdir)
    pl.enter_vehicle(car2, silent=True)
    frames(0.3)
    assert au.user_tracks == 0 and started() and len(au.playlist) >= 4

    if os.environ.get('DD_RADIO_LISTEN'):
        frames(float(os.environ['DD_RADIO_LISTEN']), real=True)
    print('RADIO OK: formats %s' % sorted(os.path.splitext(n)[1] for n in made))


if __name__ == '__main__':
    try:
        main()
    finally:
        shutil.rmtree(USER, ignore_errors=True)
