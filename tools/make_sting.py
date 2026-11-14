#!/usr/bin/env python3
"""Makes the bulletin's opening and closing sting, assets/audio/chime.wav.

History (owner's requests, 14 Nov 2026): first a soft chime; then "more pulsy, with a beat";
then "a bit kid like, let's try a BBC News type beat". This is the third: an original news-ident
in that serious broadcast style, not a copy of any real theme. A ticking 16th-note pulse,
driving low strings in D minor, timpani hits and a riser, landing on a big low boom and a brass
chord that rings out, with a quiet high synth pulse on 16ths. Mono, 24 kHz, about 4 seconds.

  python3 tools/make_sting.py            (rewrites assets/audio/chime.wav)
  python3 tools/make_sting.py --out /tmp/sting.wav
"""
import argparse, os
import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter

SR = 24000
BPM = 118
BEAT = 60 / BPM
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RNG = np.random.default_rng(7)


def hz(note):  # MIDI note number to frequency
    return 440.0 * 2 ** ((note - 69) / 12)


def tt(length):
    return np.arange(int(length * SR)) / SR


def env(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(t / max(attack, 1e-4), 1.0) * np.exp(-t / decay)


def lowpass(x, cutoff, order=2):
    b, a = butter(order, cutoff / (SR / 2), "low")
    return lfilter(b, a, x)


def highpass(x, cutoff, order=2):
    b, a = butter(order, cutoff / (SR / 2), "high")
    return lfilter(b, a, x)


def saw(note, length, voices=3, spread=0.006, top=9000):
    """Band-limited, slightly detuned sawtooth: the raw material for strings and brass."""
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


def tick(accent=False):
    """A tight, high tick, like a newsroom clock, on every 16th."""
    t = tt(0.025)
    f = 3200 if accent else 2600
    return np.sin(2 * np.pi * f * t) * np.exp(-t / (0.006 if accent else 0.004)) * (1.0 if accent else 0.55)


def timpani(note=38, length=0.9, gain=1.0):
    t = tt(length)
    f = hz(note) * (1 + 0.04 * np.exp(-t / 0.05))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.4 * np.sin(2 * np.pi * np.cumsum(f * 1.5) / SR)
    skin = highpass(RNG.standard_normal(len(t)), 300) * np.exp(-t / 0.02) * 0.3
    return np.tanh(1.3 * (body * np.exp(-t / 0.35) + skin)) * gain


def boom(length=2.2):
    """Deep cinematic hit: falling sub plus a burst of filtered noise."""
    t = tt(length)
    f = 34 + 60 * np.exp(-t / 0.08)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.7)
    hitn = lowpass(RNG.standard_normal(len(t)), 1800) * np.exp(-t / 0.12) * 0.5
    return np.tanh(1.5 * (sub + hitn))


def string_stab(note, length):
    """Short, punchy low-string 8th note."""
    x = saw(note, length) + 0.6 * saw(note + 12, length)
    x = lowpass(x, 1400)
    n = len(x)
    return x * env(n, 0.008, 0.09) * 0.5


def brass(notes, length=2.0):
    """A held brass-and-strings chord that swells slightly, then rings away."""
    n = int(length * SR)
    x = np.zeros(n)
    for note in notes:
        x += saw(note, length, voices=4, spread=0.004)
    t = np.arange(n) / SR
    # brighter at the attack, darker as it decays: blend two filtered copies
    bright, dark = lowpass(x, 4200), lowpass(x, 1200)
    mix = np.exp(-t / 0.25)
    x = bright * mix + dark * (1 - mix)
    return x * np.minimum(t / 0.012, 1.0) * np.exp(-t / 0.9) / len(notes) * 0.9


def riser(length):
    """Rising noise swell (a reversed cymbal feel) leading into the hit."""
    t = tt(length)
    noise = RNG.standard_normal(len(t))
    swell = (t / length) ** 3
    return highpass(noise, 2500) * swell * 0.35


def reverb(x, wet=0.22):
    """Small Schroeder reverb so the final chord sounds like it is in a room, not a toy."""
    out = np.zeros(len(x))
    for d, g in ((0.0297, 0.80), (0.0371, 0.78), (0.0411, 0.76), (0.0437, 0.74)):
        k = int(d * SR)
        a = np.zeros(k + 1); a[0] = 1; a[k] = -g
        out += lfilter([1.0], a, x)
    for d, g in ((0.005, 0.7), (0.0017, 0.7)):
        k = int(d * SR)
        b = np.zeros(k + 1); b[0] = -g; b[k] = 1
        a = np.zeros(k + 1); a[0] = 1; a[k] = -g
        out = lfilter(b, a, out)
    out = lowpass(out, 5000)
    return x * (1 - wet) + out / 4 * wet * 2


def place(buf, sig, at, gain=1.0):
    sig = np.asarray(sig, dtype=float).copy()
    f = min(len(sig) // 4, int(0.02 * SR))           # short fade-out so no sound ends with a click
    if f:
        sig[-f:] *= np.linspace(1, 0, f)
    i = int(at * SR)
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i] * gain


def make():
    bar = 4 * BEAT
    hit = bar + BEAT / 2                              # lands on the "and" after the bar, for urgency
    total = hit + 2.0
    out = np.zeros(int(total * SR))
    eighth, sixteenth = BEAT / 2, BEAT / 4

    # ticking clock on every 16th, accent on each beat, stopping just before the hit
    i = 0
    while i * sixteenth < hit - 0.01:
        place(out, tick(i % 4 == 0), i * sixteenth, 0.55)
        i += 1

    # driving low strings on 8ths in D minor: D D D D | Bb Bb C C, getting louder
    line = [38, 38, 38, 38, 34, 34, 36, 36, 37]
    for k, note in enumerate(line):
        place(out, string_stab(note, eighth * 0.9), k * eighth, 0.55 + 0.05 * k)

    # timpani on beats 1 and 3, then a quick roll into the hit
    place(out, timpani(38), 0, 0.7)
    place(out, timpani(34), 2 * BEAT, 0.7)
    for k, at in enumerate(np.arange(3 * BEAT, hit - 0.02, sixteenth / 1.5)):
        place(out, timpani(33, 0.25), at, 0.2 + 0.05 * k)

    # high synth pulse on 16ths for urgency: A, A, D, A over each beat, rising to Bb and C as the strings move
    pulse = [69, 69, 74, 69] * 2 + [70, 70, 74, 70, 72, 72, 76, 72, 73, 73, 76]
    for k, note in enumerate(pulse):
        x = lowpass(saw(note, sixteenth * 0.8, voices=2, top=7000), 3500)
        place(out, x * env(len(x), 0.003, 0.05), k * sixteenth, 0.16 + 0.006 * k)

    # riser over the last beat and a half
    place(out, riser(hit - 2.5 * BEAT), 2.5 * BEAT, 0.55)

    pre = out.copy()                                  # keep the build-up below the hit
    out *= 0
    out += pre * 0.62

    # the hit: boom, timpani and a D minor brass chord with an added ninth
    place(out, boom(), hit, 1.0)
    place(out, timpani(26, 1.4), hit, 0.8)
    chord = reverb(np.concatenate([brass([50, 57, 62, 65, 69, 76], 2.0), np.zeros(int(0.3 * SR))]))
    place(out, chord, hit, 1.2)

    fade_in = int(0.004 * SR)
    out[:fade_in] *= np.linspace(0, 1, fade_in)
    tail = int(0.7 * SR)
    out[-tail:] *= np.linspace(1, 0, tail) ** 2
    out = highpass(out, 28)                           # no sub rumble below hearing
    out = np.tanh(out * 1.3)
    return out / np.max(np.abs(out)) * 0.89


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=os.path.join(ROOT, "assets", "audio", "chime.wav"))
    a = p.parse_args()
    sig = make()
    sf.write(a.out, sig.astype(np.float32), SR, subtype="PCM_16")
    print(f"wrote {a.out} ({len(sig) / SR:.2f}s)")


if __name__ == "__main__":
    main()
