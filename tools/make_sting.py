#!/usr/bin/env python3
"""Makes the bulletin's opening and closing sting, assets/audio/chime.wav.

The owner asked (14 Nov 2026) for the sting to be more pulsy, with a beat, in place of the first soft chime.
It keeps the old chime's C, E, G notes, now over one bar of four-on-the-floor at 122 bpm,
then ends on a C major chord that rings out. Mono, 24 kHz, about 3 seconds.

  python3 tools/make_sting.py            (rewrites assets/audio/chime.wav)
  python3 tools/make_sting.py --out /tmp/sting.wav
"""
import argparse, os
import numpy as np
import soundfile as sf

SR = 24000
BPM = 122
BEAT = 60 / BPM
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def hz(note):  # MIDI note number to frequency
    return 440.0 * 2 ** ((note - 69) / 12)


def env(n, attack, decay):
    t = np.arange(n) / SR
    a = np.minimum(t / max(attack, 1e-4), 1.0)
    return a * np.exp(-t / decay)


def kick(length=0.35):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = 48 + 110 * np.exp(-t / 0.035)               # pitch drops from about 160 Hz to 48 Hz
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.16)
    click = np.random.default_rng(1).standard_normal(n) * np.exp(-t / 0.004) * 0.25
    return np.tanh(1.6 * (body + click))


def hat(length=0.06, seed=0):
    n = int(length * SR)
    noise = np.random.default_rng(seed).standard_normal(n)
    noise = np.diff(np.concatenate([[0], noise]))    # crude high-pass
    return noise * env(n, 0.001, 0.014) * 0.35


def pluck(note, length=0.32, bright=1.0, decay=0.18):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = hz(note)
    # a little detuned saw-ish tone from a few harmonics, which decays darker over time
    tone = np.zeros(n)
    for k in range(1, 7):
        if f * k > 10000:  # stay well under the 12 kHz limit at 24 kHz
            break
        tone += np.sin(2 * np.pi * f * k * t * (1 + 0.0015 * (k % 2))) / k * np.exp(-t * k * 6 / bright)
    return tone * env(n, 0.003, decay) * 0.5


def bass(note, length, decay=0.11):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = hz(note)
    tone = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) + 0.12 * np.sin(2 * np.pi * 3 * f * t)
    return np.tanh(1.4 * tone) * env(n, 0.004, decay) * 0.55


def place(buf, sig, at, gain=1.0):
    sig = sig.copy()
    f = min(len(sig) // 4, int(0.02 * SR))           # short fade-out so no sound ends with a click
    sig[-f:] *= np.linspace(1, 0, f)
    i = int(at * SR)
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i] * gain


def make():
    bar = 4 * BEAT
    total = bar + 1.25
    out = np.zeros(int(total * SR))
    eighth, sixteenth = BEAT / 2, BEAT / 4

    for b in range(4):                                # four-on-the-floor kick
        place(out, kick(), b * BEAT, 0.9)
    place(out, kick(0.6), bar, 1.0)                   # final hit with the chord
    for b in range(4):                                # off-beat hats, plus a 16th pickup into the last beat
        place(out, hat(seed=b), b * BEAT + eighth, 0.8)
    place(out, hat(seed=9), 3 * BEAT + 3 * sixteenth, 0.5)

    # pulsing bass on 8ths, ducked under each kick (C2, then up to G2 for the last two 8ths)
    for i in range(8):
        note = 36 if i < 6 else 43
        place(out, bass(note, eighth * 0.95), i * eighth + 0.012, 0.85 if i % 2 else 0.6)
    place(out, bass(36, 1.0, decay=0.35), bar + 0.01, 0.9)

    # the old chime's motif as a 16th-note arpeggio, rising across the bar: C E G C | E G C E ...
    arp = [72, 76, 79, 84, 76, 79, 84, 88, 79, 84, 88, 91, 84, 88, 91, 96]
    for i, note in enumerate(arp):
        place(out, pluck(note, bright=0.8 + i / 20), i * sixteenth, 0.38 + 0.2 * (i % 4 == 0))

    # closing C major chord that rings out
    for note in (60, 64, 67, 72, 76, 79):
        place(out, pluck(note, length=1.25, bright=4.0, decay=0.45), bar, 0.3)

    # gentle fade in over the first few ms and a fade at the tail
    fade_in = int(0.004 * SR)
    out[:fade_in] *= np.linspace(0, 1, fade_in)
    tail = int(0.5 * SR)
    out[-tail:] *= np.linspace(1, 0, tail) ** 2
    out = np.tanh(out * 1.2)                          # glue it together
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
