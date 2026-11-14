#!/usr/bin/env python3
"""Makes the bulletin's opening and closing sting, assets/audio/chime.wav.

History (owner's requests, 14 Nov 2026): first a soft chime; then "more pulsy, with a beat";
then "a BBC News type beat"; then "no, think news!". All of these are original sounds, never a copy of a real theme.
Styles (pick with --style). The owner chose "morse" (14 Nov 2026); it is the default and is what chime.wav holds.
  morse     Morse code spelling N-E-W-S over a driving beat, then three synth-brass stabs
  sounder   a local-radio news sounder: computer data bleeps over a beat, then "dun, dun, DUN" stabs
  headlines punchy TV-headlines bed: a one-note synth pulse, big drums, rising bleeps, a final hit
Mono, 24 kHz, about 3 to 4 seconds.

  python3 tools/make_sting.py --style morse                (rewrites assets/audio/chime.wav)
  python3 tools/make_sting.py --style sounder --out /tmp/sting.wav
"""
import argparse, os
import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter

SR = 24000
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RNG = np.random.default_rng(7)


def hz(note):
    return 440.0 * 2 ** ((note - 69) / 12)


def tt(length):
    return np.arange(int(length * SR)) / SR


def env(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(t / max(attack, 1e-4), 1.0) * np.exp(-t / decay)


def filt(x, cutoff, kind="low", order=2):
    w = np.clip(np.asarray(cutoff, dtype=float) / (SR / 2), 1e-4, 0.99)
    b, a = butter(order, w.tolist() if w.ndim else float(w), kind)
    return lfilter(b, a, x)


def saw(note, length, voices=3, spread=0.006, top=9000):
    t = tt(length)
    out = np.zeros(len(t))
    for v in range(voices):
        f = hz(note) * (1 + spread * (v - (voices - 1) / 2))
        ph = RNG.uniform(0, 2 * np.pi)
        k = 1
        while f * k < top:
            out += np.sin(2 * np.pi * f * k * t + ph * k) / k
            k += 1
    return out / voices


# ---- drums ----
def kick(length=0.4, gain=1.0):
    t = tt(length)
    f = 50 + 120 * np.exp(-t / 0.03)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.15)
    click = RNG.standard_normal(len(t)) * np.exp(-t / 0.003) * 0.3
    return np.tanh(2.0 * (body + click)) * gain


def snare(length=0.25):
    t = tt(length)
    tone = np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.05)
    noise = filt(RNG.standard_normal(len(t)), [1200, 9000], "band") * np.exp(-t / 0.07)
    return np.tanh(1.5 * (0.5 * tone + noise))


def clap(length=0.25):
    t = tt(length)
    e = np.zeros(len(t))
    for d in (0, 0.011, 0.022):
        e += np.where(t >= d, np.exp(-(t - d) / 0.006), 0)
    e += np.where(t >= 0.03, np.exp(-(t - 0.03) / 0.06), 0) * 0.7
    return filt(RNG.standard_normal(len(t)), [900, 5000], "band") * e * 0.9


def hat(length=0.05):
    t = tt(length)
    return filt(RNG.standard_normal(len(t)), 7000, "high") * np.exp(-t / 0.012) * 0.6


# ---- tones ----
def bleep(freq, length):
    """A clean electronic beep (sine plus a little third harmonic), the sound of a news wire."""
    t = tt(length)
    x = np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(2 * np.pi * 3 * freq * t)
    a = int(0.003 * SR)
    e = np.ones(len(t)); e[:a] = np.linspace(0, 1, a); e[-a:] = np.linspace(1, 0, a)
    return x * e * 0.5


def stab(notes, length=0.35, decay=0.12, bright=5000):
    """Synth-brass chord stab with a bright attack that closes quickly."""
    x = sum(saw(n, length, voices=3, spread=0.005) for n in notes) / len(notes)
    t = tt(length)
    b, d = filt(x, bright), filt(x, 900)
    m = np.exp(-t / 0.06)
    x = b * m + d * (1 - m)
    return x * np.minimum(t / 0.004, 1) * np.exp(-t / decay)


def sub(note, length, decay=0.2):
    t = tt(length)
    return np.tanh(1.5 * np.sin(2 * np.pi * hz(note) * t)) * env(len(t), 0.004, decay)


def whoosh(length):
    t = tt(length)
    return filt(RNG.standard_normal(len(t)), 1500, "high") * (t / length) ** 3 * 0.4


def reverb(x, wet=0.25):
    out = np.zeros(len(x))
    for d, g in ((0.0297, 0.80), (0.0371, 0.78), (0.0411, 0.76), (0.0437, 0.74)):
        k = int(d * SR); a = np.zeros(k + 1); a[0] = 1; a[k] = -g
        out += lfilter([1.0], a, x)
    for d, g in ((0.005, 0.7), (0.0017, 0.7)):
        k = int(d * SR); b = np.zeros(k + 1); b[0] = -g; b[k] = 1
        a = np.zeros(k + 1); a[0] = 1; a[k] = -g
        out = lfilter(b, a, out)
    return x * (1 - wet) + filt(out, 6000) / 2 * wet


def place(buf, sig, at, gain=1.0):
    sig = np.asarray(sig, dtype=float).copy()
    f = min(len(sig) // 4, int(0.015 * SR))
    if f:
        sig[-f:] *= np.linspace(1, 0, f)
    i = int(at * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i] * gain


def beat(out, bpm, beats, clap_on=(1, 3), hats=True):
    b = 60 / bpm
    for k in range(beats):
        place(out, kick(), k * b, 0.85)
        if k % 4 in clap_on:
            place(out, snare(), k * b, 0.55)
            place(out, clap(), k * b, 0.5)
        if hats:
            place(out, hat(), k * b + b / 2, 0.45)
            place(out, hat(0.03), k * b + 3 * b / 4, 0.2)


def finish(out, tail=0.6, hit=None):
    if hit is not None:                              # keep the build-up below the final hit so the hit lands
        i = int(hit * SR)
        out[:i] *= 0.6
    out[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))
    n = int(tail * SR)
    out[-n:] *= np.linspace(1, 0, n) ** 2
    out = filt(out, 30, "high")
    out = np.tanh(out * 1.4)
    return out / np.max(np.abs(out)) * 0.89


# ---- the three styles ----
def morse():
    bpm = 132
    b = 60 / bpm
    unit = b / 8                                     # one Morse unit = one 32nd note (about 20 words a minute)
    code = {"N": "-.", "E": ".", "W": ".--", "S": "..."}
    events, t = [], 0.0
    for li, letter in enumerate("NEWS"):
        for si, sym in enumerate(code[letter]):
            length = unit * (3 if sym == "-" else 1)
            events.append((t, length))
            t += length + unit
        t += 2 * unit                                # letter gap: 3 units in all
    end_code = t
    hit = np.ceil(end_code / b) * b                  # stabs land on the next beat
    total = hit + 2 * b + 1.4
    out = np.zeros(int(total * SR))
    beat(out, bpm, int(round(hit / b)))
    for at, length in events:
        place(out, bleep(1100, length * 0.92), at, 0.75)
    # bass pulse on 8ths under the code: D, then up to F and G as it builds
    bars = int(round(hit / b)) * 2
    for k in range(bars):
        note = 38 if k < bars * 0.5 else (41 if k < bars * 0.75 else 43)
        place(out, sub(note, b / 2 * 0.9, 0.09), k * b / 2, 0.5)
    place(out, whoosh(2 * b), hit - 2 * b, 0.6)
    # three stabs: "dun, dun, DUN" (D minor, then C, then a big D minor 9 that rings)
    for at, chord, ln, dec, g in ((hit, [62, 65, 69, 74], 0.3, 0.1, 0.9),
                                  (hit + 0.75 * b, [60, 64, 67, 72], 0.3, 0.1, 0.9),
                                  (hit + 1.5 * b, [50, 57, 62, 65, 69, 76], 1.6, 0.6, 1.2)):
        place(out, reverb(np.concatenate([stab(chord, ln, dec), np.zeros(int(0.4 * SR))])), at, g)
        place(out, kick(0.5), at, 0.9)
        place(out, sub(38, ln + 0.2, dec + 0.1), at, 0.7)
    return finish(out, hit=hit)


def sounder():
    bpm = 128
    b = 60 / bpm
    out = np.zeros(int((8 * b + 1.6) * SR))
    beat(out, bpm, 4)
    # a stream of computer data bleeps on 32nds, random but repeatable pitches from a D minor scale
    scale = [74, 77, 79, 81, 84, 86]
    r = np.random.default_rng(3)
    for k in range(32):
        if r.random() < 0.8:
            place(out, bleep(hz(scale[r.integers(len(scale))]), b / 8 * 0.7), k * b / 8, 0.45)
    for k in range(8):
        place(out, sub(38, b / 2 * 0.9, 0.08), k * b / 2, 0.55)
    place(out, whoosh(b), 3 * b, 0.6)
    hit = 4 * b
    for at, chord, ln, dec, g in ((hit, [62, 65, 69], 0.25, 0.08, 0.9),
                                  (hit + 0.75 * b, [62, 65, 69], 0.25, 0.08, 0.9),
                                  (hit + 1.5 * b, [50, 57, 62, 65, 69, 74], 1.6, 0.55, 1.2)):
        place(out, reverb(np.concatenate([stab(chord, ln, dec), np.zeros(int(0.4 * SR))])), at, g)
        place(out, kick(0.5), at, 0.9)
        place(out, snare(), at, 0.4)
        place(out, sub(38, ln + 0.2, dec + 0.1), at, 0.7)
    out = out[: int((hit + 1.5 * b + 1.6) * SR)]
    return finish(out, hit=hit)


def headlines():
    bpm = 120
    b = 60 / bpm
    hit = 6 * b
    out = np.zeros(int((hit + 1.8) * SR))
    beat(out, bpm, 6, clap_on=(1, 3))
    # one-note synth pulse on 16ths (A), the classic urgent news bed
    for k in range(24):
        x = filt(saw(69, b / 4 * 0.6, voices=2, top=7000), 2800)
        place(out, x * env(len(x), 0.002, 0.04), k * b / 4, 0.3 + 0.2 * (k % 4 == 0))
    # rising three-bleep motif at the start of each bar and a half
    for start in (0, 2 * b, 4 * b):
        for i, n in enumerate((81, 86, 88)):
            place(out, bleep(hz(n), b / 4 * 0.8), start + i * b / 4, 0.35)
    for k in range(12):
        place(out, sub(38 if k < 8 else 41, b / 2 * 0.9, 0.08), k * b / 2, 0.5)
    place(out, whoosh(1.5 * b), hit - 1.5 * b, 0.6)
    place(out, kick(0.8), hit, 1.0)
    place(out, sub(26, 1.6, 0.5), hit, 1.0)
    place(out, reverb(np.concatenate([stab([50, 57, 62, 65, 69, 76], 1.6, 0.6), np.zeros(int(0.4 * SR))])), hit, 1.2)
    return finish(out, hit=hit)


STYLES = {"morse": morse, "sounder": sounder, "headlines": headlines}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--style", choices=sorted(STYLES), default="morse")
    p.add_argument("--out", default=os.path.join(ROOT, "assets", "audio", "chime.wav"))
    a = p.parse_args()
    sig = STYLES[a.style]()
    sf.write(a.out, sig.astype(np.float32), SR, subtype="PCM_16")
    print(f"wrote {a.out} ({len(sig) / SR:.2f}s)")


if __name__ == "__main__":
    main()
