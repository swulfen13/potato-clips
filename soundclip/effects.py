"""Audio-Effekte – fuer Clips (offline) UND live auf die Stimme (Streaming).

Jeder Streaming-Effekt ist ein Prozessor mit Zustand (Filter, Verzoegerungen, Phasen) und kann
Block fuer Block verarbeitet werden. Dadurch klingt derselbe Effekt live genauso wie im Clip-Editor.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np
from scipy.signal import butter, fftconvolve, lfilter, resample_poly, sosfilt

from .config import SR

# ======================================================================================== Bausteine


def _f32(x):
    return np.ascontiguousarray(x, dtype=np.float32)


def _limit(x, peak=0.98):
    m = float(np.abs(x).max()) if len(x) else 0.0
    return x * (peak / m) if m > peak else x


def _soft(x, ceiling=0.97):
    """Weiche Begrenzung: leise Signale bleiben unveraendert, Spitzen werden sanft gerundet."""
    return np.tanh(x / ceiling) * ceiling


class Filt:
    """IIR-Filter mit Zustand (fuer Streaming)."""

    def __init__(self, kind, freq, order=2):
        nyq = SR / 2
        if isinstance(freq, (list, tuple)):
            freq = [min(max(f, 20), nyq * 0.95) for f in freq]
        else:
            freq = min(max(freq, 20), nyq * 0.95)
        self.sos = butter(order, freq, btype=kind, fs=SR, output="sos")
        self.zi = None

    def __call__(self, x):
        if self.zi is None or self.zi.shape[2] != x.shape[1]:
            self.zi = np.zeros((self.sos.shape[0], 2, x.shape[1]))
        y, self.zi = sosfilt(self.sos, x, axis=0, zi=self.zi)
        return y


class Shelf:
    """RBJ-Low-Shelf (Bass-Anhebung) mit Zustand."""

    def __init__(self, freq, gain_db):
        A = 10 ** (gain_db / 40)
        w0 = 2 * np.pi * freq / SR
        cos, sin = np.cos(w0), np.sin(w0)
        alpha = sin / 2 * np.sqrt(2)
        sq = 2 * np.sqrt(A) * alpha
        b = np.array([A * ((A + 1) - (A - 1) * cos + sq), 2 * A * ((A - 1) - (A + 1) * cos),
                      A * ((A + 1) - (A - 1) * cos - sq)])
        a = np.array([(A + 1) + (A - 1) * cos + sq, -2 * ((A - 1) + (A + 1) * cos), (A + 1) + (A - 1) * cos - sq])
        self.b, self.a = b / a[0], a / a[0]
        self.zi = None

    def __call__(self, x):
        if self.zi is None or self.zi.shape[1] != x.shape[1]:
            self.zi = np.zeros((2, x.shape[1]))
        y, self.zi = lfilter(self.b, self.a, x, axis=0, zi=self.zi)
        return y


class History:
    """Gibt den Block zusammen mit den letzten `size` Eingangssamples zurueck."""

    def __init__(self, size):
        self.size = int(size)
        self.buf = None

    def __call__(self, x):
        if self.buf is None or self.buf.shape[1] != x.shape[1]:
            self.buf = np.zeros((self.size, x.shape[1]), np.float32)
        h = np.concatenate([self.buf, x])
        self.buf = h[-self.size:]
        return h  # x[0] liegt bei Index self.size


def _read(h, pos):
    """Lineare Interpolation in h an (float-)Positionen pos."""
    i0 = np.floor(pos).astype(np.int64)
    fr = (pos - i0)[:, None]
    i0 = np.clip(i0, 0, len(h) - 1)
    i1 = np.clip(i0 + 1, 0, len(h) - 1)
    return h[i0] * (1 - fr) + h[i1] * fr


class Proc:
    """Basis: Streaming-Prozessor. process() bekommt Bloecke (n, kanaele) float32."""
    max_block = 8192     # groesster erlaubter Block (wegen Rueckkopplungen)
    tail = 0.0           # Nachhall in Sekunden (fuer Clips)

    def __init__(self, a: float):
        self.a = float(np.clip(a, 0.0, 1.0))
        self.t = 0       # verarbeitete Samples (fuer LFOs)

    def process(self, x):
        return x

    def offline(self, x):
        """Ganzes Signal verarbeiten (Standard: blockweise)."""
        out = []
        b = self.max_block
        for i in range(0, len(x), b):
            out.append(self.process(x[i:i + b]))
        return np.concatenate(out) if out else x

    def lfo(self, n, hz, phase=0.0):
        t = (self.t + np.arange(n)) / SR
        return np.sin(2 * np.pi * hz * t + phase)

    def step(self, n):
        self.t += n


class Chain(Proc):
    def __init__(self, procs):
        super().__init__(0)
        self.procs = procs
        self.max_block = min([p.max_block for p in procs] + [8192])
        self.tail = sum(p.tail for p in procs)

    def process(self, x):
        for p in self.procs:
            x = p.process(x)
        return x

    def offline(self, x):
        for p in self.procs:
            x = p.offline(x)
        return x


# ======================================================================================== Effekte

class PitchShift(Proc):
    """Tonhoehe aendern OHNE die Laenge zu aendern (zwei ueberblendete Lesekoepfe)."""

    def __init__(self, a, ratio, window=0.045):
        super().__init__(a)
        self.r = float(ratio)
        self.W = int(window * SR)
        self.h = History(self.W + 4)
        self.ph = 0.0

    def process(self, x):
        n = len(x)
        h = self.h(x)
        base = self.h.size
        inc = (1.0 - self.r) / self.W
        ph1 = (self.ph + inc * np.arange(n)) % 1.0
        ph2 = (ph1 + 0.5) % 1.0
        idx = base + np.arange(n)
        g1 = (1.0 - np.abs(2 * ph1 - 1))[:, None]
        g2 = (1.0 - np.abs(2 * ph2 - 1))[:, None]
        y = _read(h, idx - ph1 * self.W) * g1 + _read(h, idx - ph2 * self.W) * g2
        self.ph = (self.ph + inc * n) % 1.0
        self.step(n)
        return y


class PitchUp(PitchShift):
    def __init__(self, a):
        super().__init__(a, 1.15 + a * 0.75)


class PitchDown(PitchShift):
    def __init__(self, a):
        super().__init__(a, 1.0 / (1.12 + a * 0.68), window=0.06)


class Overdrive(Proc):
    """Uebersteuertes Mikro: Vorverstaerkung, asymmetrische Saettigung, Klangfilter."""

    def __init__(self, a):
        super().__init__(a)
        self.g = 2 + a * 45
        self.hp = Filt("highpass", 180 + a * 250)
        self.lp = Filt("lowpass", 7000 - a * 3500)
        self.bias = 0.15 + a * 0.2

    def process(self, x):
        y = self.hp(x)
        y = np.tanh(y * self.g + self.bias) - np.tanh(self.bias)
        y = self.lp(y)
        return y * (0.55 + 0.15 * (1 - self.a))


class Potato(Proc):
    """Potato Mic: winziges Billig-Mikro – Bandbreite weg, Aliasing, Krachen, Rauschen, Clipping."""

    def __init__(self, a):
        super().__init__(a)
        self.hp = Filt("highpass", 380 + a * 320, 2)
        self.lp = Filt("lowpass", 3400 - a * 1500, 2)
        self.g = 6 + a * 60
        self.hold = int(3 + a * 6)            # 48k -> ~16k..5k "Abtastrate"
        self.bits = int(round(9 - a * 5))     # 9..4 Bit
        self.last = None
        self.env = 0.0
        self.rng = np.random.default_rng(1)
        self.post = Filt("highpass", 300, 1)

    def process(self, x):
        n, ch = x.shape
        y = self.hp(x)
        y = self.lp(y)
        y = np.clip(np.tanh(y * self.g) * 1.15, -0.85, 0.85)
        # Sample & Hold (Aliasing)
        s = self.t + np.arange(n)
        hp = (s // self.hold) * self.hold - self.t
        if self.last is None or self.last.shape[0] != ch:
            self.last = np.zeros(ch, np.float32)
        held = np.where((hp >= 0)[:, None], y[np.clip(hp, 0, n - 1)], self.last[None, :])
        self.last = held[-1].copy()
        # Bit-Reduktion
        step = 2 ** (self.bits - 1)
        y = np.round(held * step) / step
        # Rauschen + Knackser, nur wenn gesprochen wird (Huellkurve)
        lvl = float(np.abs(x).mean())
        self.env = max(lvl, self.env * 0.9)
        e = min(1.0, self.env * 25)
        noise = self.rng.standard_normal((n, 1)) * (0.012 + 0.03 * self.a) * e
        crack = (self.rng.random((n, 1)) < 0.0015 * (0.3 + self.a) * e) * self.rng.uniform(-0.6, 0.6, (n, 1))
        y = y + noise + crack
        y = self.post(y)
        self.step(n)
        return y * 0.75


class Earrape(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.g = 25 + a * 400
        self.bass = Shelf(110, 10 + a * 8)
        self.hp = Filt("highpass", 60, 1)

    def process(self, x):
        y = self.bass(self.hp(x) * self.g)
        y = np.clip(y, -1.0, 1.0)
        step = 2 ** 7
        y = np.round(y * step) / step
        return np.clip(y * 1.3, -0.96, 0.96)


class Robot(Proc):
    """Roboter: Ringmodulation + metallische Kammfilter-Resonanz."""

    def __init__(self, a):
        super().__init__(a)
        self.f = 60 + a * 90
        self.d = [int(SR * ms / 1000) for ms in (2.9, 5.3, 7.7)]
        self.h = History(max(self.d) + 1)
        self.hp = Filt("highpass", 150, 1)

    def process(self, x):
        n = len(x)
        y = x * (0.35 * (1 - self.a) + (0.65 + 0.35 * self.a) * self.lfo(n, self.f)[:, None])
        h = self.h(y)
        b = self.h.size
        out = y.copy()
        for k, d in enumerate(self.d):
            out += h[b - d:b - d + n] * (0.55 ** (k + 1))
        self.step(n)
        return self.hp(out) * 1.6


class Alien(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.pitch = PitchShift(a, 1.18 + 0.25 * a)
        self.h = History(int(0.012 * SR) + 2)

    def process(self, x):
        n = len(x)
        y = self.pitch.process(x)
        y = y * (1 - 0.5 * self.a + 0.5 * self.a * self.lfo(n, 35 + 40 * self.a)[:, None])
        h = self.h(y)
        d = (0.004 + 0.003 * (1 + self.lfo(n, 0.6))) * SR
        y = 0.6 * y + 0.6 * _read(h, self.h.size + np.arange(n) - d)
        self.step(n)
        return y * 1.7


class Telephone(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.bp = Filt("bandpass", [320, 3300], 3)
        self.g = 1.5 + a * 5

    def process(self, x):
        return np.tanh(self.bp(x) * self.g) * 0.8


class Radio(Proc):
    """Funkgeraet / Walkie-Talkie."""

    def __init__(self, a):
        super().__init__(a)
        self.bp = Filt("bandpass", [550, 2600], 3)
        self.g = 4 + a * 18
        self.env = 0.0
        self.rng = np.random.default_rng(2)

    def process(self, x):
        n = len(x)
        y = np.clip(self.bp(x) * self.g, -0.7, 0.7)
        self.env = max(float(np.abs(x).mean()), self.env * 0.92)
        e = min(1.0, self.env * 30)
        y = y + self.rng.standard_normal((n, 1)) * (0.02 + 0.04 * self.a) * e
        return y * 0.9


class Megaphone(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.hp = Filt("highpass", 650, 2)
        self.lp = Filt("lowpass", 4800 - a * 1200, 2)
        self.g = 4 + a * 20
        self.d = int(0.0011 * SR)
        self.h = History(self.d + 1)

    def process(self, x):
        n = len(x)
        y = np.tanh(self.hp(x) * self.g)
        h = self.h(y)
        y = y + 0.6 * h[self.h.size - self.d:self.h.size - self.d + n]
        return self.lp(y) * 0.6


class Underwater(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.lp = Filt("lowpass", 900 - a * 550, 4)
        self.h = History(int(0.02 * SR))

    def process(self, x):
        n = len(x)
        y = self.lp(x)
        h = self.h(y)
        d = (0.004 + 0.003 * self.a) * SR * (1 + self.lfo(n, 2.2 + self.a * 2))
        y = _read(h, self.h.size + np.arange(n) - d - 1)
        y = y * (0.75 + 0.25 * self.lfo(n, 3.1, 1.0))[:, None]
        self.step(n)
        return y * 1.6


class Echo(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.D = int((0.16 + a * 0.22) * SR)
        self.fb = 0.3 + a * 0.4
        self.max_block = self.D
        self.yh = None
        self.lp = Filt("lowpass", 5000, 1)
        self.tail = min(4.0, (self.D / SR) * np.log(0.01) / np.log(self.fb))

    def process(self, x):
        n, ch = x.shape
        if self.yh is None or self.yh.shape[1] != ch:
            self.yh = np.zeros((self.D, ch), np.float32)
        y = x + self.fb * self.lp(self.yh[:n])
        self.yh = np.concatenate([self.yh[n:], y])
        return y


_COMB = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617]
_ALLP = [556, 441, 341, 225]


class Reverb(Proc):
    """Hall nach Freeverb (8 Kammfilter + 4 Allpaesse), Raumgroesse ueber amount."""

    def __init__(self, a, room=None):
        super().__init__(a)
        sc = SR / 44100
        self.cd = [int(d * sc) for d in _COMB]
        self.ad = [int(d * sc) for d in _ALLP]
        self.max_block = min(self.ad)
        room = 0.72 + 0.26 * a if room is None else room
        self.fb = room
        self.damp = 0.35 - 0.15 * a
        self.wet = 0.25 + 0.55 * a
        self.dry = 1.0 - 0.45 * a
        self.cb = None
        self.ab = None
        self.zi = None
        self.tail = 1.0 + 4.0 * a

    def _init(self, ch):
        self.cb = [np.zeros((d, ch)) for d in self.cd]
        self.ab = [np.zeros((d, ch)) for d in self.ad]
        self.zi = [np.zeros((1, ch)) for _ in self.cd]

    def process(self, x):
        n, ch = x.shape
        if self.cb is None or self.cb[0].shape[1] != ch:
            self._init(ch)
        inp = x * 0.015
        acc = np.zeros((n, ch))
        for i, d in enumerate(self.cd):
            out = self.cb[i][:n]
            lp, self.zi[i] = lfilter([1 - self.damp], [1, -self.damp], out, axis=0, zi=self.zi[i])
            new = inp + lp * self.fb
            self.cb[i] = np.concatenate([self.cb[i][n:], new])
            acc += out
        y = acc
        for i, d in enumerate(self.ad):
            bo = self.ab[i][:n]
            o = -y + bo
            self.ab[i] = np.concatenate([self.ab[i][n:], y + bo * 0.5])
            y = o
        return x * self.dry + y * self.wet * 3.0

    def offline(self, x):
        # schneller: Impulsantwort einmal berechnen und per FFT falten (klingt identisch)
        ln = int(self.tail * SR) + 1
        imp = np.zeros((ln, 1), np.float32)
        imp[0] = 1.0
        probe = Reverb(self.a)
        probe.fb, probe.damp, probe.wet, probe.dry = self.fb, self.damp, self.wet, 0.0
        ir = Proc.offline(probe, imp)[:, 0]
        wet = fftconvolve(x, ir[:, None], axes=0)[: len(x)]
        return x * self.dry + wet


class Vibrato(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.depth = (0.0015 + 0.005 * a) * SR
        self.rate = 4.5 + 2.5 * a
        self.h = History(int(self.depth * 2 + 4))

    def process(self, x):
        n = len(x)
        h = self.h(x)
        d = self.depth * (1 + self.lfo(n, self.rate)) + 1
        y = _read(h, self.h.size + np.arange(n) - d)
        self.step(n)
        return y


class Chorus(Proc):
    """Chor / Verdopplung: mehrere leicht verstimmte Stimmen."""

    def __init__(self, a):
        super().__init__(a)
        self.voices = [(0.018, 0.33, 0.0), (0.024, 0.45, 2.1), (0.031, 0.27, 4.2)]
        self.depth = (0.002 + 0.004 * a) * SR
        self.h = History(int(0.04 * SR))
        self.mix = 0.4 + 0.4 * a

    def process(self, x):
        n = len(x)
        h = self.h(x)
        idx = self.h.size + np.arange(n)
        acc = np.zeros_like(x, dtype=np.float64)
        for base, rate, ph in self.voices:
            d = base * SR + self.depth * self.lfo(n, rate, ph)
            acc += _read(h, idx - d)
        self.step(n)
        return x * (1 - self.mix * 0.5) + acc / len(self.voices) * self.mix * 1.2


class Flanger(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.h = History(int(0.012 * SR))
        self.depth = (0.001 + 0.004 * a) * SR
        self.mix = 0.5 + 0.4 * a

    def process(self, x):
        n = len(x)
        h = self.h(x)
        d = 0.0008 * SR + self.depth * (1 + self.lfo(n, 0.35))
        y = x * 0.7 + _read(h, self.h.size + np.arange(n) - d) * self.mix * 0.7
        self.step(n)
        return y


class Bitcrush(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.bits = max(2, int(round(12 - a * 9)))
        self.hold = 1 + int(a * 11)
        self.last = None

    def process(self, x):
        n, ch = x.shape
        if self.last is None or self.last.shape[0] != ch:
            self.last = np.zeros(ch, np.float32)
        s = self.t + np.arange(n)
        hp = (s // self.hold) * self.hold - self.t
        y = np.where((hp >= 0)[:, None], x[np.clip(hp, 0, n - 1)], self.last[None, :])
        self.last = y[-1].copy()
        step = 2 ** (self.bits - 1)
        self.step(n)
        return np.round(y * step) / step


class Lofi(Proc):
    """Lo-Fi / Kassette: Leiern, dumpfer Klang, Saettigung, Rauschen."""

    def __init__(self, a):
        super().__init__(a)
        self.h = History(int(0.01 * SR))
        self.lp = Filt("lowpass", 4200 - a * 2000, 2)
        self.hp = Filt("highpass", 90, 1)
        self.rng = np.random.default_rng(3)

    def process(self, x):
        n = len(x)
        h = self.h(x)
        d = (0.002 + 0.0015 * self.a * self.lfo(n, 0.7) + 0.0004 * self.a * self.lfo(n, 6.3)) * SR + 1
        y = _read(h, self.h.size + np.arange(n) - d)
        y = np.tanh(self.lp(self.hp(y)) * (1.3 + self.a))
        y = y + self.rng.standard_normal((n, 1)) * 0.004 * (1 + 2 * self.a)
        self.step(n)
        return y * 0.85


class BassBoost(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.shelf = Shelf(120, 5 + a * 13)

    def process(self, x):
        return _soft(self.shelf(x) * 0.8)


class PhoneSpeaker(Proc):
    """Handy-Lautsprecher: kein Bass, kratzig."""

    def __init__(self, a):
        super().__init__(a)
        self.hp = Filt("highpass", 700 + a * 500, 3)
        self.lp = Filt("lowpass", 7500 - a * 2500, 2)
        self.g = 1.5 + a * 4

    def process(self, x):
        return np.tanh(self.lp(self.hp(x)) * self.g) * 1.1


class Ghost(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.c = Chain([PitchShift(a, 1.06 + 0.06 * a), Chorus(0.7), Reverb(0.6 + 0.35 * a)])
        self.hp = Filt("highpass", 400, 2)
        self.max_block, self.tail = self.c.max_block, self.c.tail

    def process(self, x):
        return self.c.process(self.hp(x)) * 2.4

    def offline(self, x):
        return self.c.offline(self.hp(x)) * 2.4


class Demon(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.c = Chain([PitchShift(a, 1.0 / (1.35 + 0.5 * a), window=0.07), Overdrive(0.15 + 0.2 * a),
                        BassBoost(0.4), Reverb(0.25 + 0.2 * a)])
        self.max_block, self.tail = self.c.max_block, self.c.tail

    def process(self, x):
        return self.c.process(x) * 0.75

    def offline(self, x):
        return self.c.offline(x) * 0.75


class Giant(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.c = Chain([PitchShift(a, 1.0 / (1.2 + 0.3 * a), window=0.06), Reverb(0.55)])
        self.max_block, self.tail = self.c.max_block, self.c.tail

    def process(self, x):
        return self.c.process(x) * 1.4

    def offline(self, x):
        return self.c.offline(x) * 1.4


class Stadium(Proc):
    def __init__(self, a):
        super().__init__(a)
        self.c = Chain([Megaphone(0.3 + 0.3 * a), Reverb(0.7 + 0.25 * a), Echo(0.2)])
        self.max_block, self.tail = self.c.max_block, self.c.tail

    def process(self, x):
        return self.c.process(x)

    def offline(self, x):
        return self.c.offline(x)


class Volume(Proc):
    def process(self, x):
        return x * (4.0 ** (2.0 * self.a - 1.0))


# ======================================================================================== Nur fuer Clips

def _speed(x, factor):
    fr = Fraction(factor).limit_denominator(60)
    return resample_poly(x, fr.denominator, fr.numerator, axis=0)


def speed_up(x, a):
    return _speed(x, 1.0 + a * 0.9)


def slow_down(x, a):
    return _speed(x, 1.0 / (1.0 + a * 0.8))


def reverse(x, a):
    return x[::-1]


def fade(x, a):
    n = min(len(x) // 2, int((0.05 + a * 1.5) * SR))
    if n <= 1:
        return x
    y = x.copy()
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)[:, None]
    y[:n] *= ramp
    y[-n:] *= ramp[::-1]
    return y


def stutter(x, a):
    seg = int((0.06 + (1 - a) * 0.12) * SR)
    reps = 2 + int(a * 5)
    if len(x) <= seg:
        return x
    return np.concatenate([np.concatenate([x[:seg]] * reps), x])


def normalize(x, a):
    m = float(np.abs(x).max()) if len(x) else 0.0
    return x * ((0.6 + 0.38 * a) / m) if m > 1e-6 else x


def glitch(x, a):
    """Zufaellige Wiederholungen/Rueckwaerts-Stuecke wie ein kaputter CD-Player."""
    rng = np.random.default_rng(int(len(x)) % 997)
    out = []
    i = 0
    seg = int(0.08 * SR)
    while i < len(x):
        s = x[i:i + seg]
        r = rng.random()
        if r < 0.25 * a:
            out.extend([s] * int(2 + rng.integers(0, 3)))
        elif r < 0.35 * a:
            out.append(s[::-1])
        else:
            out.append(s)
        i += seg
    return np.concatenate(out) if out else x


# ======================================================================================== Register

# key: (Anzeigename, Kategorie, Fabrik(amount) -> Proc | Funktion, Standard-Staerke, streaming?)
EFFECTS: dict[str, tuple] = {
    "potato": ("🥔 Potato Mic", "Stimme", Potato, 0.6, True),
    "overdrive": ("🔥 Übersteuertes Mikro", "Stimme", Overdrive, 0.5, True),
    "earrape": ("💥 Earrape (sehr laut!)", "Stimme", Earrape, 0.5, True),
    "pitch_up": ("🐿 Chipmunk / Helium", "Stimme", PitchUp, 0.5, True),
    "pitch_down": ("🐻 Tiefe Stimme", "Stimme", PitchDown, 0.5, True),
    "demon": ("😈 Dämon", "Stimme", Demon, 0.5, True),
    "giant": ("🗿 Riese", "Stimme", Giant, 0.5, True),
    "robot": ("🤖 Roboter", "Stimme", Robot, 0.5, True),
    "alien": ("👽 Alien", "Stimme", Alien, 0.5, True),
    "ghost": ("👻 Geist", "Stimme", Ghost, 0.5, True),
    "telephone": ("☎ Telefon", "Klang", Telephone, 0.5, True),
    "radio": ("📻 Funkgerät", "Klang", Radio, 0.5, True),
    "megaphone": ("📢 Megafon", "Klang", Megaphone, 0.5, True),
    "phone": ("📱 Handy-Lautsprecher", "Klang", PhoneSpeaker, 0.5, True),
    "stadium": ("🏟 Stadion-Durchsage", "Klang", Stadium, 0.5, True),
    "underwater": ("🌊 Unter Wasser", "Klang", Underwater, 0.5, True),
    "lofi": ("📼 Lo-Fi Kassette", "Klang", Lofi, 0.5, True),
    "bitcrush": ("👾 8-Bit", "Klang", Bitcrush, 0.5, True),
    "bassboost": ("🔊 Bass-Boost", "Klang", BassBoost, 0.5, True),
    "reverb": ("⛪ Hall / Kathedrale", "Raum", Reverb, 0.5, True),
    "echo": ("🏔 Echo", "Raum", Echo, 0.5, True),
    "chorus": ("👥 Chor / Doppelt", "Raum", Chorus, 0.5, True),
    "flanger": ("✈ Jet / Flanger", "Raum", Flanger, 0.5, True),
    "vibrato": ("〰 Wackelstimme", "Raum", Vibrato, 0.5, True),
    "speed_up": ("⏩ Schneller abspielen", "Clip", speed_up, 0.5, False),
    "slow_down": ("⏪ Zeitlupe", "Clip", slow_down, 0.5, False),
    "reverse": ("🔁 Rückwärts", "Clip", reverse, 1.0, False),
    "stutter": ("🔂 Stotter", "Clip", stutter, 0.5, False),
    "glitch": ("📀 Glitch / Kaputte CD", "Clip", glitch, 0.5, False),
    "fade": ("🌅 Ein-/Ausblenden", "Clip", fade, 0.3, False),
    "volume": ("🔉 Lautstärke", "Clip", Volume, 0.5, True),
    "normalize": ("📈 Lauter machen (Normalisieren)", "Clip", normalize, 0.9, False),
}

CATEGORIES = ["Stimme", "Klang", "Raum", "Clip"]
LIVE_KEYS = [k for k, v in EFFECTS.items() if v[4] and k != "volume"]


def label(key: str) -> str:
    return EFFECTS.get(key, (key,))[0]


def make_proc(key: str, amount: float) -> Proc | None:
    spec = EFFECTS.get(key)
    if not spec or not spec[4]:
        return None
    return spec[2](float(np.clip(amount, 0.0, 1.0)))


def apply_chain(x: np.ndarray, chain: list[dict]) -> np.ndarray:
    """Effektkette auf einen ganzen Clip anwenden (inkl. Nachhall-Ende)."""
    y = _f32(x)
    if not len(y) or not chain:
        return _f32(_limit(y)) if len(y) else y
    loud = False
    for e in chain:
        key = e.get("type")
        spec = EFFECTS.get(key)
        if not spec:
            continue
        amount = float(np.clip(e.get("amount", spec[3]), 0.0, 1.0))
        if spec[4]:
            proc = spec[2](amount)
            pre_len = len(y)
            if proc.tail > 0:
                y = np.concatenate([y, np.zeros((int(proc.tail * SR), y.shape[1]), np.float32)])
            y = _f32(proc.offline(y))
            if proc.tail > 0:  # leises Ende abschneiden
                env = np.abs(y).max(axis=1)
                thr = max(1e-4, float(env.max()) * 0.003)
                nz = np.nonzero(env > thr)[0]
                end = int(nz[-1]) + int(0.05 * SR) if len(nz) else len(y)
                y = y[: min(len(y), max(end, pre_len))]
        else:
            y = _f32(spec[2](y, amount))
        loud = loud or key in ("earrape", "volume", "normalize")
    if not np.isfinite(y).all():
        y = np.nan_to_num(y)
    if not loud:
        y = _limit(y)
    return _f32(np.clip(y, -1.0, 1.0))


# ======================================================================================== Live-Stimme

VOICE_PRESETS: dict[str, tuple[str, list[tuple[str, float]]]] = {
    "potato": ("🥔", [("potato", 0.65)]),
    "overdrive": ("🔥", [("overdrive", 0.55)]),
    "earrape": ("💥", [("earrape", 0.45)]),
    "pitch_up": ("🐿", [("pitch_up", 0.55)]),
    "pitch_down": ("🐻", [("pitch_down", 0.5)]),
    "demon": ("😈", [("demon", 0.6)]),
    "giant": ("🗿", [("giant", 0.5)]),
    "robot": ("🤖", [("robot", 0.6)]),
    "alien": ("👽", [("alien", 0.6)]),
    "ghost": ("👻", [("ghost", 0.6)]),
    "telephone": ("☎", [("telephone", 0.5)]),
    "radio": ("📻", [("radio", 0.6)]),
    "megaphone": ("📢", [("megaphone", 0.6)]),
    "phone": ("📱", [("phone", 0.6)]),
    "stadium": ("🏟", [("stadium", 0.5)]),
    "underwater": ("🌊", [("underwater", 0.6)]),
    "lofi": ("📼", [("lofi", 0.6)]),
    "bitcrush": ("👾", [("bitcrush", 0.55)]),
    "reverb": ("⛪", [("reverb", 0.8)]),
    "echo": ("🏔", [("echo", 0.5)]),
    "chorus": ("👥", [("chorus", 0.6)]),
    "vibrato": ("〰", [("vibrato", 0.6)]),
}


def voice_name(key: str) -> str:
    return label(key).split(" ", 1)[-1] if key in EFFECTS else key


class VoiceChanger:
    """Wendet ein Stimm-Preset live auf Mikrofon-Bloecke an (thread-sicher umschaltbar)."""

    def __init__(self):
        self._proc: Proc | None = None
        self.key = ""
        self.amount = 0.6
        self.cpu_ms = 0.0

    def set(self, key: str, amount: float):
        """amount 0..1 skaliert die Staerke des Presets (0.5 = Standard)."""
        if not key or key not in VOICE_PRESETS:
            self._proc = None
            self.key = ""
            return
        _, chain = VOICE_PRESETS[key]
        scale = 0.4 + 1.2 * float(amount)        # 0.4x .. 1.6x
        procs = [make_proc(k, min(1.0, a * scale)) for k, a in chain]
        procs = [p for p in procs if p is not None]
        self._proc = Chain(procs) if procs else None
        self.key, self.amount = key, amount

    def active(self) -> bool:
        return self._proc is not None

    def process(self, data: np.ndarray) -> np.ndarray:
        proc = self._proc
        if proc is None:
            return data
        import time as _t
        t0 = _t.perf_counter()
        mono = data.mean(axis=1, keepdims=True).astype(np.float32)
        out = []
        b = proc.max_block
        for i in range(0, len(mono), b):
            out.append(proc.process(mono[i:i + b]))
        y = np.concatenate(out) if out else mono
        y = np.nan_to_num(_soft(y, 0.95)).astype(np.float32)
        self.cpu_ms = self.cpu_ms * 0.9 + (_t.perf_counter() - t0) * 1000 * 0.1
        return np.repeat(y, 2, axis=1)
