# -*- coding: utf-8 -*-
"""Генератор звуков и музыки (только для разработки).

Все звуки игры синтезируются этим скриптом — никаких сторонних записей.
Запуск из корня репозитория:  python tools/gen_sounds.py
Зависимости: numpy, scipy, soundfile.
"""
import os
import sys

import numpy as np
from scipy import signal
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SFX = os.path.join(ROOT, 'assets', 'sfx')
MUS = os.path.join(ROOT, 'assets', 'music')
SR = 22050
MSR = 32000
rng = np.random.RandomState(1337)


# ---------------------------------------------------------------------------
# помощники
# ---------------------------------------------------------------------------
def tt(dur, sr=SR):
    return np.arange(int(dur * sr)) / float(sr)


def noise(n):
    return rng.uniform(-1.0, 1.0, int(n))


def lp(x, fc, sr=SR, order=2):
    b, a = signal.butter(order, min(0.99, fc / (sr * 0.5)), 'low')
    return signal.lfilter(b, a, x)


def hp(x, fc, sr=SR, order=2):
    b, a = signal.butter(order, min(0.99, fc / (sr * 0.5)), 'high')
    return signal.lfilter(b, a, x)


def bp(x, f0, f1, sr=SR, order=2):
    b, a = signal.butter(order, [f0 / (sr * 0.5), min(0.99, f1 / (sr * 0.5))], 'band')
    return signal.lfilter(b, a, x)


def env_exp(n, tau, sr=SR):
    return np.exp(-np.arange(int(n)) / (tau * sr))


def fade(x, a=0.003, r=0.01, sr=SR):
    x = np.array(x, dtype=np.float64)
    na, nr = int(a * sr), int(r * sr)
    if na > 0:
        x[:na] *= np.linspace(0, 1, na)
    if nr > 0:
        x[-nr:] *= np.linspace(1, 0, nr)
    return x


def norm(x, peak=0.9):
    m = np.max(np.abs(x))
    return x * (peak / m) if m > 1e-9 else x


def sweep(f0, f1, dur, sr=SR, curve=1.0):
    """Фаза синуса с частотой, меняющейся от f0 к f1."""
    n = int(dur * sr)
    k = np.linspace(0, 1, n) ** curve
    f = f0 + (f1 - f0) * k
    return 2 * np.pi * np.cumsum(f) / sr


def loopify(x, xf=0.08, sr=SR):
    """Сделать бесшовную петлю: конец плавно переходит в начало."""
    n = int(xf * sr)
    body = x[:-n].copy()
    tail = x[-n:]
    k = np.linspace(0, 1, n)
    body[:n] = body[:n] * k + tail * (1 - k)
    return body


def save(name, x, sr=SR, peak=0.9):
    x = norm(np.asarray(x, dtype=np.float64), peak)
    path = os.path.join(SFX, name + '.wav')
    sf.write(path, (x * 32767).astype(np.int16), sr, subtype='PCM_16')
    return path


# ---------------------------------------------------------------------------
# машины
# ---------------------------------------------------------------------------
def engine(base=52.0, rough=0.25, dur=1.0):
    cycles = round(base * dur)
    dur = cycles / base
    t = tt(dur)
    x = np.zeros_like(t)
    for h, a in ((1, 1.0), (2, 0.7), (3, 0.5), (4, 0.34), (5, 0.24), (6, 0.2), (8, 0.12), (10, 0.08), (12, 0.05)):
        x += a * np.sin(2 * np.pi * base * h * t + h * 0.7)
    # полгармоники дают «ворчание» мотора
    x += 0.45 * np.sin(2 * np.pi * base * 0.5 * t)
    x += 0.2 * np.sin(2 * np.pi * base * 1.5 * t + 1.0)
    pulse = 0.6 + 0.4 * np.clip(np.sin(2 * np.pi * base * t), 0, 1) ** 3
    n = lp(noise(len(t)), 900) * rough
    # шум, зацикленный без шва
    n = np.concatenate([n, n[:2000]])
    n = loopify(n, 2000 / SR)[:len(t)]
    x = np.tanh((x * 0.5 + n) * pulse * 1.4)
    return x


def skid():
    t = tt(1.1)
    x = bp(noise(len(t)), 900, 3200) * 0.9
    for f in (1150, 1420, 1730):
        vib = 1 + 0.02 * np.sin(2 * np.pi * 7 * t + f)
        x += 0.22 * np.sin(2 * np.pi * f * vib * t)
    x *= 0.8 + 0.2 * np.sin(2 * np.pi * 13 * t)
    return loopify(x, 0.15)


def crash(big=False):
    dur = 0.9 if big else 0.5
    t = tt(dur)
    n = len(t)
    x = noise(n) * env_exp(n, 0.09 if big else 0.05)
    x = lp(x, 5000) + 0.6 * bp(noise(n), 300, 1800) * env_exp(n, 0.16 if big else 0.08)
    x += 1.2 * np.sin(sweep(110, 45, dur)) * env_exp(n, 0.12)
    for f in ([410, 733, 1290, 2110, 2950] if big else [620, 1480, 2630]):
        x += 0.25 * np.sin(2 * np.pi * f * t + f) * env_exp(n, 0.07 + rng.rand() * 0.1)
    if big:
        # осыпающиеся осколки
        for k in range(14):
            p = int((0.12 + rng.rand() * 0.6) * SR)
            m = min(n - p, int(0.03 * SR))
            x[p:p + m] += 0.3 * hp(noise(m), 3000) * env_exp(m, 0.008)
    return fade(np.tanh(x * 1.2), 0.001, 0.05)


def horn(f1=415.0, f2=523.0, dur=0.5):
    t = tt(dur)
    x = np.zeros_like(t)
    for f in (f1, f2):
        for h in range(1, 9):
            x += (1.0 / h) * np.sin(2 * np.pi * f * h * t) * (1.0 if h % 2 else 0.6)
    x = lp(x, 3200)
    return fade(x, 0.012, 0.05)


def siren():
    dur = 2.4
    n = int(dur * SR)
    k = np.arange(n) / float(n)
    f = 660 + 620 * (0.5 - 0.5 * np.cos(2 * np.pi * k))
    ph = 2 * np.pi * np.cumsum(f) / SR
    # фаза должна замкнуться: корректируем линейно
    total = ph[-1]
    ph += (np.round(total / (2 * np.pi)) * 2 * np.pi - total) * k
    x = np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.22 * np.sin(3 * ph) + 0.1 * np.sin(4 * ph)
    return x


def alarm():
    """Звонок охранной сигнализации: молоточек колотит по чашке 16 раз в секунду.  Петля ровно в секунду:
    отзвук последних ударов заворачивается в её начало."""
    n = SR
    x = np.zeros(n)
    rate = 16
    m = int(0.30 * SR)
    tk = np.arange(m) / float(SR)
    hit = (np.sin(2 * np.pi * 2140 * tk) + 0.55 * np.sin(2 * np.pi * 3420 * tk) + 0.3 * np.sin(2 * np.pi * 5310 * tk)
           + 0.5 * np.sin(2 * np.pi * 1290 * tk)) * np.exp(-tk / 0.05)
    hit[:40] += rng.randn(40) * np.linspace(0.8, 0.0, 40)          # сам удар молоточка
    for k in range(rate):
        i0 = k * n // rate
        idx = (i0 + np.arange(m)) % n
        x[idx] += hit * (0.9 + 0.1 * (k % 2))
    return x


# ---------------------------------------------------------------------------
# оружие
# ---------------------------------------------------------------------------
def gunshot(dur, tau, body_f, bright, crack=1.0):
    t = tt(dur)
    n = len(t)
    x = lp(noise(n), bright) * env_exp(n, tau) * crack
    x += 0.5 * hp(noise(n), 2500) * env_exp(n, tau * 0.35)
    x += 1.1 * np.sin(sweep(body_f, body_f * 0.35, dur)) * env_exp(n, tau * 1.6)
    # эхо выстрела
    d = int(0.045 * SR)
    if n > d * 2:
        x[d:] += 0.25 * lp(x[:-d], 1800)
    return fade(np.tanh(x * 1.8), 0.0005, 0.03)


def rocket():
    dur = 1.0
    t = tt(dur)
    n = len(t)
    x = bp(noise(n), 250, 2600) * (np.minimum(1.0, t / 0.04) * env_exp(n, 0.45))
    x += 0.8 * np.sin(sweep(190, 70, dur)) * env_exp(n, 0.3)
    x += 0.5 * hp(noise(n), 3000) * env_exp(n, 0.05)
    return fade(np.tanh(x * 1.5), 0.002, 0.1)


def explosion():
    dur = 2.2
    t = tt(dur)
    n = len(t)
    x = lp(noise(n), 700) * env_exp(n, 0.55) * 1.4
    x += lp(noise(n), 3500) * env_exp(n, 0.12)
    x += 1.5 * np.sin(sweep(75, 28, dur)) * env_exp(n, 0.5)
    x += 0.8 * noise(n) * env_exp(n, 0.02)
    # раскаты
    for k in range(5):
        p = int((0.25 + rng.rand() * 0.9) * SR)
        m = min(n - p, int(0.3 * SR))
        x[p:p + m] += 0.35 * lp(noise(m), 500) * env_exp(m, 0.1)
    return fade(np.tanh(x * 1.5), 0.0005, 0.3)


def punch():
    dur = 0.16
    t = tt(dur)
    n = len(t)
    x = lp(noise(n), 1400) * env_exp(n, 0.025)
    x += 1.2 * np.sin(sweep(170, 70, dur)) * env_exp(n, 0.04)
    return fade(np.tanh(x * 1.6), 0.0005, 0.02)


def swing():
    dur = 0.28
    t = tt(dur)
    n = len(t)
    e = np.sin(np.pi * t / dur) ** 2
    x = bp(noise(n), 500, 2800) * e
    return fade(x, 0.01, 0.03)


def glass():
    dur = 0.7
    t = tt(dur)
    n = len(t)
    x = hp(noise(n), 3500) * env_exp(n, 0.05) * 0.9
    for k in range(26):
        p = int(rng.rand() ** 1.5 * 0.45 * SR)
        f = 2200 + rng.rand() * 6000
        m = n - p
        x[p:] += 0.16 * np.sin(2 * np.pi * f * t[:m]) * env_exp(m, 0.02 + rng.rand() * 0.06)
    return fade(x, 0.0005, 0.05)


def clatter():
    dur = 0.5
    n = int(dur * SR)
    x = np.zeros(n)
    for k in range(6):
        p = int(rng.rand() * 0.28 * SR)
        m = n - p
        f = 180 + rng.rand() * 500
        x[p:] += (0.6 * np.sin(2 * np.pi * f * tt(m / SR)[:m]) + lp(noise(m), 2500)) * env_exp(m, 0.03) * \
            (1.0 - k * 0.1)
    return fade(np.tanh(x), 0.0005, 0.05)


def ricochet():
    dur = 0.35
    n = int(dur * SR)
    x = np.sin(sweep(3400, 1100, dur, curve=0.6)) * env_exp(n, 0.09)
    x += 0.3 * hp(noise(n), 4000) * env_exp(n, 0.01)
    return fade(x, 0.0005, 0.05)


# ---------------------------------------------------------------------------
# голоса (формантный синтез)
# ---------------------------------------------------------------------------
def voice(f0a, f0b, dur, formants, breath=0.06, jitter=0.03):
    n = int(dur * SR)
    k = np.linspace(0, 1, n)
    f0 = f0a + (f0b - f0a) * k
    f0 *= 1 + jitter * np.sin(2 * np.pi * 9 * k * dur) + 0.012 * lp(noise(n), 40) * 6
    ph = np.cumsum(f0) / SR
    src = 2.0 * (ph % 1.0) - 1.0                     # пилообразный «голосовой» источник
    src = src + breath * noise(n)
    out = np.zeros(n)
    for (fc, bw, g) in formants:
        b, a = signal.iirpeak(fc / (SR * 0.5), fc / bw)
        out += g * signal.lfilter(b, a, src)
    e = np.minimum(1.0, k / 0.06) * np.minimum(1.0, (1 - k) / 0.25)
    return fade(out * e, 0.004, 0.03)


A_FORM = ((820, 110, 1.0), (1250, 130, 0.7), (2600, 180, 0.35), (3400, 220, 0.15))
A_FORM_F = ((950, 130, 1.0), (1500, 150, 0.7), (2900, 200, 0.4), (3900, 240, 0.2))
O_FORM = ((520, 90, 1.0), (920, 110, 0.6), (2400, 170, 0.2))
E_FORM = ((560, 90, 1.0), (1750, 140, 0.6), (2500, 180, 0.3))


# ---------------------------------------------------------------------------
# интерфейс
# ---------------------------------------------------------------------------
def tone(freq, dur, kind='sine', tau=None, sr=SR):
    t = tt(dur, sr)
    if kind == 'sine':
        x = np.sin(2 * np.pi * freq * t)
    elif kind == 'square':
        x = np.sign(np.sin(2 * np.pi * freq * t)) * 0.6
    elif kind == 'tri':
        x = 2 * np.abs(2 * ((freq * t) % 1.0) - 1) - 1
    else:
        x = 2 * ((freq * t) % 1.0) - 1
    if tau:
        x = x * env_exp(len(t), tau, sr)
    return fade(x, 0.003, 0.01, sr)


def seq(parts, sr=SR):
    """parts: [(start, array)] -> сумма."""
    n = max(int(s * sr) + len(a) for s, a in parts)
    out = np.zeros(n)
    for s, a in parts:
        p = int(s * sr)
        out[p:p + len(a)] += a
    return out


def bell(freq, dur):
    t = tt(dur)
    x = np.zeros_like(t)
    for h, a, tau in ((1, 1.0, 0.25), (2.76, 0.5, 0.12), (5.4, 0.25, 0.07), (8.9, 0.12, 0.04)):
        x += a * np.sin(2 * np.pi * freq * h * t) * env_exp(len(t), tau)
    return fade(x, 0.001, 0.02)


def brass(freq, dur):
    t = tt(dur)
    x = np.zeros_like(t)
    for h in range(1, 10):
        x += (1.0 / h ** 0.9) * np.sin(2 * np.pi * freq * h * t + 0.3 * h)
    e = np.minimum(1.0, t / 0.03) * (0.75 + 0.25 * env_exp(len(t), 0.15))
    return fade(lp(x * e, 3500), 0.004, 0.06)


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12.0)


def jingle_passed():
    # победная фанфара (до мажор)
    notes = [(0.00, 60, 0.16), (0.16, 64, 0.16), (0.32, 67, 0.16), (0.48, 72, 0.34), (0.86, 67, 0.16),
             (1.02, 72, 1.3)]
    parts = [(s, brass(midi(m), d) * 0.8) for s, m, d in notes]
    for m in (52, 55, 60, 64):
        parts.append((1.02, brass(midi(m), 1.3) * 0.45))
    for m in (48, 55):
        parts.append((0.0, brass(midi(m), 0.46) * 0.4))
        parts.append((0.48, brass(midi(m + 5), 0.5) * 0.4))
    x = seq(parts)
    d = int(0.11 * SR)
    x[d:] += 0.25 * x[:-d]
    return fade(x, 0.002, 0.25)


def jingle_failed():
    notes = [(0.0, 58, 0.3), (0.3, 55, 0.3), (0.6, 51, 0.3), (0.9, 46, 1.2)]
    parts = [(s, brass(midi(m), d) * 0.8) for s, m, d in notes]
    for m in (34, 41, 49):
        parts.append((0.9, brass(midi(m), 1.2) * 0.45))
    return fade(seq(parts), 0.002, 0.3)


def sting_wasted():
    dur = 3.0
    t = tt(dur)
    x = np.zeros_like(t)
    for m, a in ((33, 1.0), (40, 0.6), (45, 0.6), (48, 0.5), (51, 0.35), (57, 0.25)):
        f = midi(m)
        for h in (1, 2, 3, 4):
            x += a / h * np.sin(2 * np.pi * f * h * t * (1 + 0.002 * np.sin(2 * np.pi * 0.7 * t)))
    x *= np.minimum(1.0, t / 0.02) * env_exp(len(t), 1.1)
    x += 0.8 * np.sin(sweep(90, 35, dur)) * env_exp(len(t), 0.4)
    return fade(lp(x, 2500), 0.002, 0.4)


# ---------------------------------------------------------------------------
# музыка
# ---------------------------------------------------------------------------
class Track(object):
    def __init__(self, bpm, beats, sr=MSR):
        self.sr = sr
        self.bpm = bpm
        self.beat = 60.0 / bpm
        self.n = int(round(beats * self.beat * sr))
        self.dry = np.zeros(self.n)
        self.wet = np.zeros(self.n)

    def add(self, beat, x, gain=1.0, wet=0.0):
        p = int(round(beat * self.beat * self.sr)) % self.n
        x = x * gain
        m = len(x)
        for buf, g in ((self.dry, 1.0), (self.wet, wet)):
            if g <= 0:
                continue
            if p + m <= self.n:
                buf[p:p + m] += x * g
            else:
                k = self.n - p
                buf[p:] += x[:k] * g
                rest = x[k:]
                while len(rest) > 0:
                    q = min(len(rest), self.n)
                    buf[:q] += rest[:q] * g
                    rest = rest[q:]

    def render(self, reverb=0.9, wet_gain=0.5, drive=1.3):
        sr = self.sr
        m = int(reverb * sr)
        ir = rng.uniform(-1, 1, m) * np.exp(-np.arange(m) / (reverb * sr * 0.28))
        ir = lp(ir, 5000, sr)
        ir /= np.sqrt(np.sum(ir ** 2))
        w2 = np.concatenate([self.wet, self.wet])
        rv = signal.fftconvolve(w2, ir)[self.n:2 * self.n]
        x = self.dry + rv * wet_gain
        x = x / (np.percentile(np.abs(x), 99.7) + 1e-9)
        x = np.tanh(x * drive) / np.tanh(drive)
        return x * 0.8


def m_tt(dur):
    return np.arange(int(dur * MSR)) / float(MSR)


def m_env(n, a, d, s, r):
    """ADSR на n сэмплов (r — затухание в конце)."""
    e = np.ones(n) * s
    na, nd, nr = int(a * MSR), int(d * MSR), int(r * MSR)
    na = min(na, n)
    e[:na] = np.linspace(0, 1, na)
    nd = min(nd, n - na)
    if nd > 0:
        e[na:na + nd] = np.linspace(1, s, nd)
    nr = min(nr, n)
    if nr > 0:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def saw(f, t, detune=0.0):
    x = 2 * ((f * t) % 1.0) - 1
    if detune:
        x = x + (2 * ((f * (1 + detune) * t + 0.3) % 1.0) - 1) + (2 * ((f * (1 - detune) * t + 0.6) % 1.0) - 1)
        x /= 3.0
    return x


def sq(f, t, pw=0.5):
    return np.where((f * t) % 1.0 < pw, 1.0, -1.0)


def i_bass(m, dur, cutoff=700):
    t = m_tt(dur)
    f = midi(m)
    x = saw(f, t) * 0.6 + np.sin(2 * np.pi * f * t) * 0.8 + sq(f * 0.5, t) * 0.15
    x = lp(x, cutoff, MSR)
    return x * m_env(len(t), 0.005, 0.08, 0.7, 0.03)


def i_pad(m, dur, cutoff=1800):
    t = m_tt(dur)
    x = saw(midi(m), t, 0.006)
    x = lp(x, cutoff, MSR)
    return x * m_env(len(t), 0.12, 0.2, 0.8, min(0.3, dur * 0.4))


def i_lead(m, dur, cutoff=3200, vib=0.004):
    t = m_tt(dur)
    f = midi(m) * (1 + vib * np.sin(2 * np.pi * 5.5 * t) * np.minimum(1.0, t / 0.25))
    ph = np.cumsum(f) / MSR
    x = np.where(ph % 1.0 < 0.35, 1.0, -1.0) * 0.6 + (2 * (ph % 1.0) - 1) * 0.4
    x = lp(x, cutoff, MSR)
    return x * m_env(len(t), 0.01, 0.1, 0.75, min(0.06, dur * 0.3))


def i_pluck(m, dur, cutoff=2600):
    t = m_tt(dur)
    f = midi(m)
    x = saw(f, t) * 0.7 + sq(f, t, 0.3) * 0.3
    x = lp(x, cutoff, MSR)
    return x * np.exp(-t / 0.16) * np.minimum(1.0, t / 0.003)


def i_epiano(m, dur):
    t = m_tt(dur)
    f = midi(m)
    x = np.sin(2 * np.pi * f * t + 1.6 * np.sin(2 * np.pi * f * t) * np.exp(-t / 0.3))
    x += 0.3 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t / 0.12)
    return x * np.exp(-t / 0.7) * np.minimum(1.0, t / 0.004) * m_env(len(t), 0.002, 0.01, 1.0, 0.03)


def i_guitar(m, dur):
    """Перегруженный «пауэр-аккорд»: тоника + квинта + октава."""
    t = m_tt(dur)
    x = np.zeros_like(t)
    for k, a in ((0, 1.0), (7, 0.8), (12, 0.6)):
        x += a * saw(midi(m + k), t, 0.003)
    x = np.tanh(x * 3.0)
    x = lp(hp(x, 120, MSR), 2800, MSR)
    return x * m_env(len(t), 0.004, 0.05, 0.85, 0.03)


def i_accordion(m, dur):
    t = m_tt(dur)
    f = midi(m)
    x = np.zeros_like(t)
    for dt_ in (-0.004, 0.0, 0.004):
        ff = f * (1 + dt_)
        x += sq(ff, t, 0.42) * 0.5 + saw(ff, t) * 0.5
    x = lp(x, 2600, MSR) / 3.0
    trem = 1 + 0.08 * np.sin(2 * np.pi * 5.0 * t)
    return x * trem * m_env(len(t), 0.03, 0.05, 0.9, min(0.05, dur * 0.3))


def d_kick(punchy=1.0):
    dur = 0.32
    t = m_tt(dur)
    ph = 2 * np.pi * np.cumsum(48 + 110 * np.exp(-t / 0.028)) / MSR
    x = np.sin(ph) * np.exp(-t / 0.13)
    x += 0.4 * punchy * lp(rng.uniform(-1, 1, len(t)), 3000, MSR) * np.exp(-t / 0.006)
    return np.tanh(x * 1.6)


def d_snare():
    dur = 0.24
    t = m_tt(dur)
    n = rng.uniform(-1, 1, len(t))
    x = bp(n, 1200, 7000, MSR) * np.exp(-t / 0.07)
    x += 0.7 * np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.045)
    return np.tanh(x * 1.4)


def d_hat(open_=False):
    dur = 0.3 if open_ else 0.06
    t = m_tt(dur)
    x = hp(rng.uniform(-1, 1, len(t)), 7000, MSR) * np.exp(-t / (0.09 if open_ else 0.018))
    return x


def d_clap():
    dur = 0.2
    t = m_tt(dur)
    n = bp(rng.uniform(-1, 1, len(t)), 900, 3500, MSR)
    e = np.zeros_like(t)
    for d in (0.0, 0.011, 0.023):
        k = int(d * MSR)
        e[k:] += np.exp(-t[:len(t) - k] / 0.012)
    e += np.exp(-t / 0.08) * 0.5
    return n * e


def d_tom(f=110):
    dur = 0.3
    t = m_tt(dur)
    ph = 2 * np.pi * np.cumsum(f * (1 + 0.5 * np.exp(-t / 0.04))) / MSR
    return np.sin(ph) * np.exp(-t / 0.12)


CH = {  # аккорды: смещения от тоники
    'm': (0, 3, 7), 'M': (0, 4, 7), 'm7': (0, 3, 7, 10), 'M7': (0, 4, 7, 11), '7': (0, 4, 7, 10),
    'sus': (0, 5, 7),
}


def track_retro():
    """Синтвейв, ля минор, 104 уд/мин, 32 такта."""
    tr = Track(104, 32 * 4)
    prog = [(57, 'm'), (53, 'M'), (48, 'M'), (55, 'M')] * 4 + [(50, 'm'), (57, 'm'), (53, 'M'), (52, 'M')] * 2 + \
           [(57, 'm'), (53, 'M'), (48, 'M'), (52, 'M')] * 2
    kick, snare, hat, ohat, clap = d_kick(), d_snare(), d_hat(), d_hat(True), d_clap()
    lead_a = [(0, 76, 1.5), (1.5, 74, 0.5), (2, 72, 1), (3, 69, 1), (4, 72, 1.5), (5.5, 74, 0.5), (6, 76, 2),
              (8, 79, 1.5), (9.5, 76, 0.5), (10, 72, 1), (11, 76, 1), (12, 74, 3), (15, 71, 1)]
    lead_b = [(0, 77, 1), (1, 76, 1), (2, 74, 1), (3, 77, 1), (4, 76, 2), (6, 72, 2), (8, 74, 1), (9, 72, 1),
              (10, 69, 1), (11, 72, 1), (12, 71, 2), (14, 68, 2)]
    for bar, (root, q) in enumerate(prog):
        b0 = bar * 4
        full = bar >= 4
        for k in range(8):                               # бас восьмыми
            tr.add(b0 + k * 0.5, i_bass(root - 24 + (12 if k % 4 == 3 else 0), tr.beat * 0.45), 0.5)
        for o in CH[q]:
            tr.add(b0, i_pad(root + o, tr.beat * 4.0), 0.13, wet=0.8)
        if full:
            arp = [0, 1, 2, 1, 0, 1, 2, 1] if bar % 2 == 0 else [2, 1, 0, 1, 2, 1, 0, 2]
            for k in range(16):
                o = CH[q][arp[k % 8] % len(CH[q])]
                tr.add(b0 + k * 0.25, i_pluck(root + 12 + o, tr.beat * 0.24), 0.13, wet=0.5)
        if bar >= 2:
            for k in (0, 2):
                tr.add(b0 + k, kick, 0.75)
            for k in (1, 3):
                tr.add(b0 + k, snare, 0.42, wet=0.25)
                tr.add(b0 + k, clap, 0.2, wet=0.3)
            for k in range(8):
                tr.add(b0 + k * 0.5, hat, 0.12 if k % 2 else 0.07)
            if bar % 4 == 3:
                tr.add(b0 + 3.5, ohat, 0.14)
                for k, f in ((3.0, 150), (3.25, 125), (3.5, 105), (3.75, 90)):
                    tr.add(b0 + k, d_tom(f), 0.35, wet=0.3)
    for sec in (8, 24):
        for (b, m, d) in lead_a:
            tr.add(sec * 4 + b, i_lead(m, tr.beat * d * 0.95), 0.22, wet=0.6)
    for (b, m, d) in lead_b:
        tr.add(16 * 4 + b, i_lead(m, tr.beat * d * 0.95), 0.22, wet=0.6)
        tr.add(20 * 4 + b, i_lead(m + (12 if b < 8 else 0), tr.beat * d * 0.95), 0.18, wet=0.6)
    return tr.render(1.1, 0.55)


def track_beat():
    """Неспешный фанк/хип-хоп, ми минор, 92 уд/мин, 24 такта."""
    tr = Track(92, 24 * 4)
    prog = [(52, 'm7'), (52, 'm7'), (57, 'm7'), (59, '7')] * 4 + [(48, 'M7'), (50, '7'), (52, 'm7'), (52, 'm7')] * 2
    kick, snare, hat, ohat = d_kick(1.3), d_snare(), d_hat(), d_hat(True)
    riff = [(0, 0), (0.75, 0), (1.5, 7), (2.0, 10), (2.75, 12), (3.25, 10), (3.5, 7)]
    riff2 = [(0, 0), (0.5, 0), (1.5, 3), (2.0, 5), (2.5, 7), (3.5, 10)]
    for bar, (root, q) in enumerate(prog):
        b0 = bar * 4
        for (b, o) in (riff if bar % 2 == 0 else riff2):
            tr.add(b0 + b, i_bass(root - 24 + o, tr.beat * 0.4, 900), 0.55)
        for k in (0.0, 2.5):
            tr.add(b0 + k, kick, 0.8)
        if bar % 2 == 1:
            tr.add(b0 + 1.75, kick, 0.6)
        for k in (1, 3):
            tr.add(b0 + k, snare, 0.5, wet=0.2)
        for k in range(16):
            sw = 0.04 if k % 2 else 0.0                     # свинг
            tr.add(b0 + k * 0.25 + sw, hat, 0.11 if k % 4 == 0 else 0.06)
        if bar % 4 == 3:
            tr.add(b0 + 3.5, ohat, 0.13)
        if bar >= 4:
            for (b, d) in ((0.0, 0.4), (1.5, 0.3), (2.25, 0.3)):
                for o in CH[q]:
                    tr.add(b0 + b, i_epiano(root + 12 + o, tr.beat * d * 2.2), 0.13, wet=0.5)
    mel = [(0, 71, 0.5), (0.75, 74, 0.5), (1.5, 76, 1.0), (3, 74, 0.5), (3.5, 71, 0.5), (4, 69, 1.5), (6, 67, 0.5),
           (6.5, 69, 0.5), (7, 71, 1), (8, 76, 0.75), (8.75, 79, 0.75), (9.5, 78, 0.5), (10, 76, 1),
           (11.5, 74, 0.5), (12, 71, 2), (14.5, 69, 0.5), (15, 67, 1)]
    for sec in (8, 16):
        for (b, m, d) in mel:
            tr.add(sec * 4 + b, i_lead(m, tr.beat * d * 0.9, 2400, 0.003), 0.16, wet=0.5)
    return tr.render(0.7, 0.4)


def track_rock():
    """Гаражный рок, ми минор, 138 уд/мин, 32 такта."""
    tr = Track(138, 32 * 4)
    prog = ([40, 40, 43, 45] * 2 + [40, 40, 48, 47] * 2) + ([45, 45, 43, 40] * 2 + [48, 50, 47, 47] * 2)
    kick, snare, hat, ohat = d_kick(1.4), d_snare(), d_hat(), d_hat(True)
    lead = [(0, 76, 1), (1, 79, 1), (2, 81, 1.5), (3.5, 79, 0.5), (4, 76, 2), (6, 74, 1), (7, 76, 1),
            (8, 79, 1), (9, 81, 1), (10, 83, 1.5), (11.5, 81, 0.5), (12, 79, 1), (13, 76, 1), (14, 74, 2)]
    for bar, root in enumerate(prog):
        b0 = bar * 4
        pat = (0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5) if bar % 4 != 3 else (0, 0.5, 1.0, 2.0, 2.5, 3.0)
        for k in pat:
            tr.add(b0 + k, i_guitar(root, tr.beat * 0.42), 0.26)
            tr.add(b0 + k, i_bass(root - 12, tr.beat * 0.42, 600), 0.42)
        for k in (0, 1.5, 2):
            tr.add(b0 + k, kick, 0.8)
        for k in (1, 3):
            tr.add(b0 + k, snare, 0.55, wet=0.25)
        for k in range(8):
            tr.add(b0 + k * 0.5, hat if k != 7 else ohat, 0.1)
        if bar % 8 == 7:
            for k, f in ((2.0, 170), (2.5, 150), (3.0, 125), (3.5, 100)):
                tr.add(b0 + k, d_tom(f), 0.45, wet=0.25)
                tr.add(b0 + k + 0.25, snare, 0.35)
    for sec in (8, 24):
        for (b, m, d) in lead:
            tr.add(sec * 4 + b, i_lead(m, tr.beat * d * 0.92, 3800, 0.006), 0.2, wet=0.5)
    return tr.render(0.8, 0.35, drive=1.6)


def track_chanson():
    """Дворовый вальс «под шансон»: ре минор, 3/4, 132 уд/мин, 32 такта."""
    tr = Track(132, 32 * 3)
    prog = [(50, 'm'), (50, 'm'), (55, 'm'), (55, 'm'), (57, '7'), (57, '7'), (50, 'm'), (50, 'm'),
            (53, 'M'), (53, 'M'), (48, 'M'), (48, 'M'), (55, 'm'), (57, '7'), (50, 'm'), (57, '7')] * 2
    mel = [  # (такт, доля, нота, длительность в долях)
        (0, 0, 69, 2), (0, 2, 74, 1), (1, 0, 77, 3), (2, 0, 74, 2), (2, 2, 79, 1), (3, 0, 82, 3),
        (4, 0, 81, 2), (4, 2, 79, 1), (5, 0, 76, 3), (6, 0, 74, 1), (6, 1, 77, 1), (6, 2, 76, 1), (7, 0, 74, 3),
        (8, 0, 72, 2), (8, 2, 77, 1), (9, 0, 81, 3), (10, 0, 79, 2), (10, 2, 76, 1), (11, 0, 72, 3),
        (12, 0, 70, 1), (12, 1, 74, 1), (12, 2, 79, 1), (13, 0, 76, 2), (13, 2, 73, 1), (14, 0, 74, 3),
        (15, 0, 76, 1), (15, 1, 73, 1), (15, 2, 69, 1)]
    kick, hat = d_kick(0.6), d_hat()
    for bar, (root, q) in enumerate(prog):
        b0 = bar * 3
        tr.add(b0, i_bass(root - 24, tr.beat * 0.8, 500), 0.6)
        tr.add(b0, kick, 0.35)
        for k in (1, 2):
            for o in CH[q]:
                tr.add(b0 + k, i_accordion(root + o, tr.beat * 0.4), 0.12, wet=0.4)
            tr.add(b0 + k, hat, 0.06)
        if bar % 2 == 1:
            tr.add(b0 + 2, i_bass(root - 24 + 7, tr.beat * 0.5, 500), 0.4)
    for rep in (0, 16):
        for (bar, b, m, d) in mel:
            g = 0.26
            tr.add((bar + rep) * 3 + b, i_accordion(m, tr.beat * d * 0.94), g, wet=0.5)
            if rep:                                         # второй раз — в терцию
                tr.add((bar + rep) * 3 + b, i_accordion(m - (3 if m % 12 in (2, 9, 4) else 4), tr.beat * d * 0.94),
                       0.12, wet=0.5)
    return tr.render(0.9, 0.45)


def track_theme():
    """Тема главного меню: медленно и мрачно, до минор, 76 уд/мин, 16 тактов."""
    tr = Track(76, 16 * 4)
    prog = [(48, 'm'), (44, 'M'), (41, 'm'), (43, 'M')] * 4
    kick, snare, hat = d_kick(0.8), d_snare(), d_hat()
    mel = [(0, 67, 3), (3, 70, 1), (4, 72, 4), (8, 68, 3), (11, 67, 1), (12, 65, 2), (14, 62, 2),
           (16, 67, 3), (19, 70, 1), (20, 75, 4), (24, 72, 2), (26, 68, 2), (28, 67, 4)]
    for bar, (root, q) in enumerate(prog):
        b0 = bar * 4
        for o in CH[q]:
            tr.add(b0, i_pad(root + o, tr.beat * 4.0, 1300), 0.16, wet=0.9)
            tr.add(b0, i_pad(root + o + 12, tr.beat * 4.0, 1000), 0.06, wet=0.9)
        for k in (0, 1.5, 2.5):
            tr.add(b0 + k, i_bass(root - 24 if root > 44 else root - 12, tr.beat * 0.7, 420), 0.6)
        if bar >= 4:
            tr.add(b0, kick, 0.7)
            tr.add(b0 + 2.5, kick, 0.5)
            tr.add(b0 + 2, snare, 0.3, wet=0.5)
            for k in range(8):
                tr.add(b0 + k * 0.5, hat, 0.05)
        if bar >= 8:
            for k in range(8):
                o = CH[q][k % 3]
                tr.add(b0 + k * 0.5, i_pluck(root + 24 + o, tr.beat * 0.45, 2000), 0.07, wet=0.8)
    for (b, m, d) in mel:
        tr.add(8 * 4 + b, i_lead(m, tr.beat * d * 0.96, 2200, 0.005), 0.17, wet=0.8)
    return tr.render(1.6, 0.7)


def save_music(name, x):
    path = os.path.join(MUS, name + '.ogg')
    data = x.astype(np.float32)
    with sf.SoundFile(path, 'w', samplerate=MSR, channels=1, format='OGG', subtype='VORBIS') as f:
        step = MSR * 4
        for i in range(0, len(data), step):
            f.write(data[i:i + step])
    return path


# ---------------------------------------------------------------------------
def main():
    for d in (SFX, MUS):
        if not os.path.isdir(d):
            os.makedirs(d)
    only = sys.argv[1:]
    out = []

    def S(name, fn, peak=0.9):
        if only and name not in only:
            return
        out.append(save(name, fn(), peak=peak))

    S('engine', lambda: engine(52.0, 0.2))
    S('engine_truck', lambda: engine(36.0, 0.4))
    S('skid', skid, 0.7)
    S('crash1', lambda: crash(False))
    S('crash2', lambda: crash(True))
    S('horn', lambda: horn())
    S('horn_truck', lambda: horn(185.0, 233.0, 0.7))
    S('siren', siren, 0.7)
    S('alarm', alarm, 0.6)
    S('pistol', lambda: gunshot(0.32, 0.035, 190, 4200))
    S('uzi', lambda: gunshot(0.18, 0.022, 260, 5500))
    S('shotgun', lambda: gunshot(0.6, 0.07, 120, 3000, 1.3))
    S('ak', lambda: gunshot(0.3, 0.04, 150, 3800, 1.2))
    S('silenced', lambda: lp(gunshot(0.16, 0.016, 150, 1500, 0.6), 2400), 0.42)
    S('sniper', lambda: gunshot(0.95, 0.085, 105, 3600, 1.5))
    S('rocket', rocket)
    S('explosion', explosion)
    S('punch', punch)
    S('swing', swing, 0.6)
    S('glass', glass, 0.7)
    S('break', clatter, 0.8)
    S('ricochet', ricochet, 0.5)
    S('scream_m', lambda: voice(310, 230, 0.75, A_FORM), 0.75)
    S('scream_f', lambda: voice(640, 480, 0.8, A_FORM_F, jitter=0.04), 0.7)
    S('ouch_m', lambda: voice(190, 130, 0.26, O_FORM), 0.7)
    S('ouch_f', lambda: voice(380, 280, 0.26, E_FORM), 0.65)
    S('pickup', lambda: seq([(0.0, tone(880, 0.09)), (0.08, tone(1320, 0.16, tau=0.08))]), 0.6)
    S('money', lambda: seq([(0.0, bell(2093, 0.25)), (0.09, bell(2637, 0.4))]), 0.6)
    S('passed', jingle_passed, 0.85)
    S('failed', jingle_failed, 0.8)
    S('wasted', sting_wasted, 0.85)
    S('menu_move', lambda: tone(660, 0.05, 'tri', 0.02), 0.45)
    S('menu_ok', lambda: seq([(0.0, tone(660, 0.07, 'tri')), (0.06, tone(990, 0.12, 'tri', 0.06))]), 0.5)
    S('menu_back', lambda: seq([(0.0, tone(660, 0.07, 'tri')), (0.06, tone(440, 0.12, 'tri', 0.06))]), 0.5)
    S('door', lambda: fade(lp(noise(int(0.22 * SR)), 900) * env_exp(int(0.22 * SR), 0.03) +
                           0.8 * np.sin(sweep(140, 60, 0.22)) * env_exp(int(0.22 * SR), 0.035), 0.001, 0.03), 0.75)
    S('rain', lambda: loopify(hp(noise(int(2.6 * SR)), 1500) * 0.6 + bp(noise(int(2.6 * SR)), 300, 1200) * 0.5,
                              0.3), 0.5)
    S('ambience', lambda: loopify(bp(np.cumsum(noise(int(4.4 * SR))) / 30.0, 45, 420) +
                                  0.04 * lp(noise(int(4.4 * SR)), 2000), 0.4), 0.5)
    S('splash', lambda: fade(bp(noise(int(0.9 * SR)), 300, 3500) * np.sin(np.pi * tt(0.9) / 0.9) ** 0.6 *
                             env_exp(int(0.9 * SR), 0.3) + 0.8 * np.sin(sweep(100, 50, 0.9)) *
                             env_exp(int(0.9 * SR), 0.1), 0.004, 0.2), 0.75)
    S('spray', lambda: fade(hp(noise(int(1.1 * SR)), 3000), 0.08, 0.3), 0.45)
    S('pager', lambda: seq([(k * 0.14, tone(1976, 0.08, 'square')) for k in range(3)]), 0.35)
    S('step', lambda: fade(lp(noise(int(0.07 * SR)), 1100) * env_exp(int(0.07 * SR), 0.012), 0.001, 0.01), 0.4)
    S('static', lambda: fade(bp(noise(int(0.3 * SR)), 800, 6000) * (0.6 + 0.4 * np.sign(np.sin(
        2 * np.pi * 31 * tt(0.3)))), 0.01, 0.05), 0.35)
    S('fire', lambda: loopify(lp(noise(int(1.8 * SR)), 600) * 0.7 + hp(noise(int(1.8 * SR)), 2000) *
                              (rng.rand(int(1.8 * SR)) > 0.985) * 3.0, 0.2), 0.6)
    S('click', lambda: tone(1500, 0.03, 'square', 0.008), 0.3)
    # телефон: звонок (две трели), снятие трубки и отбой
    S('phone', lambda: seq([(k * 0.085 + g * 0.62, tone(1318 if k % 2 else 1568, 0.07, 'square', 0.05))
                            for g in range(2) for k in range(5)]), 0.32)
    S('phone_up', lambda: seq([(0.0, tone(988, 0.05, 'tri')), (0.05, tone(1318, 0.09, 'tri', 0.05))]), 0.4)
    S('phone_down', lambda: seq([(0.0, tone(784, 0.06, 'tri')), (0.06, tone(523, 0.12, 'tri', 0.06))]), 0.4)
    # ворота гаража: гул привода и лязг секций
    S('garage', lambda: fade(lp(noise(int(1.1 * SR)), 260) * 0.9 +
                             0.5 * np.sin(2 * np.pi * 62 * tt(1.1)) * (0.7 + 0.3 * np.sin(2 * np.pi * 9 * tt(1.1))) +
                             1.6 * hp(noise(int(1.1 * SR)), 1800) * (rng.rand(int(1.1 * SR)) > 0.992), 0.06, 0.25), 0.6)
    # мастерская: трещотка гаечного ключа
    S('wrench', lambda: seq([(k * 0.07, fade(bp(noise(int(0.035 * SR)), 1800, 5200) *
                                             env_exp(int(0.035 * SR), 0.008), 0.0005, 0.004))
                             for k in range(7)]), 0.5)
    S('engine_bike', lambda: engine(92.0, 0.5))
    # сигналы из тюнинг-ателье: мелодия на пять нот и «крякалка»
    S('horn_tune', lambda: seq([(k * 0.16, horn(f, f * 1.26, 0.15)) for k, f in
                                enumerate((392.0, 392.0, 523.0, 659.0, 784.0))]), 0.8)
    S('horn_quack', lambda: seq([(k * 0.19, fade(np.sign(np.sin(sweep(620.0, 330.0, 0.15))) * 0.6 *
                                                 env_exp(int(0.15 * SR), 0.12), 0.002, 0.02)) for k in range(3)]), 0.6)
    for name, fn in (('retro', track_retro), ('beat', track_beat), ('rock', track_rock),
                     ('chanson', track_chanson), ('theme', track_theme)):
        if only and name not in only:
            continue
        x = fn()
        out.append(save_music(name, x))
    total = 0
    for p in out:
        sz = os.path.getsize(p)
        total += sz
        info = sf.info(p)
        print('%-28s %7.2f s %8d B' % (os.path.relpath(p, ROOT), info.duration, sz))
    print('files: %d, total %.2f MB' % (len(out), total / 1e6))


if __name__ == '__main__':
    main()
