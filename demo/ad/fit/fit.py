#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fit preset 36 "Ring mod." (the laser harp) to the Elka-X capture of its Laser Harp preset.

    demo/ad/fit/fit.py [REF.wav] [--rounds 3]

REF defaults to synthex-web's tools/compare/refs/patch-laser-harp.wav: D3 held ~9.9 s in Elka-X
(chorus mode 1), the capture synthex-web's Synthex was fitted to. Each candidate is one note rendered by
demo/ad/fit/one_note.c (the FM-1 engine, on this computer - bit-identical to the FM-1). The score
is the mean |dB| difference over 1/3-octave bands 63 Hz - 16 kHz in three windows (attack 0-0.4 s,
glide 0.4-1.5 s, sustain 1.5-9.5 s), level included. Coordinate descent over the fields below."""
import subprocess, sys, tempfile
from pathlib import Path
import numpy as np, scipy.io.wavfile as wf, scipy.signal as ss

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "fm1"))
from run import cc  # noqa: E402

REF = Path.home() / "work/ai-smarthome/audio/software-synth/synthex/tools/compare/refs/patch-laser-harp.wav"
EXE = ROOT / "build/ad/one_note"
WIN = ((0.0, 0.4), (0.4, 1.5), (1.5, 9.5))
EDGES = 63 * 2 ** (np.arange(0, 25) / 3)          # 1/3 octaves, 63 Hz .. 16 kHz
# field: (start, lo, hi) in raw Q16 units; the starts are preset 36's values (after the 2026-10-22 fit:
# it began at env_amt 32768, ef_d 65536, o2_pwm 25559, o1_pwm 32768, cross 36045, mix 45875/45875, mm4 49152)
FIELDS = {
    "cutoff": (28836, 6554, 65536), "env_amt": (49152, 0, 65536), "reso": (0, 0, 52429),
    "ef_s": (42598, 0, 65536), "ef_d": (6554, 6554, 327680),
    "o2_pwm": (40305, 3277, 62259), "o1_pwm": (47514, 3277, 62259), "cross": (11469, 0, 65536),
    "mix_o1": (29491, 0, 65536), "mix_o2": (62259, 0, 65536), "mm4": (65536, 0, 65536),
    "key_track": (32768, 0, 65536), "volume": (52429, 13107, 65536),
    "rev_mix": (16384, 0, 32768), "cho_mix": (36045, 0, 65536), "cho_depth": (39322, 0, 65536),
    "lfo1_rate": (60948, 6554, 131072), "lfo1_da": (34734, 0, 65536),
}


def load(path):
    sr, x = wf.read(str(path))
    x = x.astype(float)
    if np.abs(x).max() > 2:
        x /= 32768
    x = x.mean(1) if x.ndim > 1 else x
    on = int(np.argmax(np.abs(x) > 1e-3))
    return x[on:on + int(9.6 * sr)]


def bands(x):
    out = []
    for a, b in WIN:
        f, p = ss.welch(x[int(a * 44100):int(b * 44100)], 44100, nperseg=4096)
        out.append([10 * np.log10(np.mean(p[(f >= lo) & (f < hi)]) + 1e-20) for lo, hi in zip(EDGES, EDGES[1:])])
    return np.array(out)


def render(v, wd):
    raw = Path(wd) / "o.raw"
    subprocess.run([str(EXE), str(raw), "50", "0.1", "10.0", "10.0", *[f"{k}={int(x)}" for k, x in v.items()]], check=True)
    return np.frombuffer(raw.read_bytes(), np.int16).reshape(-1, 2).mean(1) / 32768


def main():
    args = sys.argv[1:]
    rounds = int(args.pop(args.index("--rounds") + 1)) if "--rounds" in args else 3
    if "--rounds" in args: args.remove("--rounds")
    ref = load(Path(args[0]) if args and "=" not in args[0] and args[0] != "--from" else REF)
    subprocess.run([*cc(), "-O2", "-o", str(EXE), "demo/ad/fit/one_note.c", "engine/sc_voice.c", "engine/sc_synth.c"],
                   cwd=ROOT, check=True)
    R = bands(ref)
    with tempfile.TemporaryDirectory() as wd:
        def score(v):
            o = render(v, wd)
            on = int(np.argmax(np.abs(o) > 1e-3))
            d = bands(o[on:on + int(9.6 * 44100)]) - R
            return float(np.mean(np.abs(d))), d
        v = {k: s for k, (s, lo, hi) in FIELDS.items()}
        if "--from" in args:                                   # resume: field=value ...
            v.update({k: int(x) for k, x in (a.split("=") for a in args[args.index("--from") + 1:])})
        best, d = score(v)
        print(f"preset 36 as it is: {best:.2f} dB  (per window {np.abs(d).mean(1).round(2)})", flush=True)
        for r in range(rounds):
            step = 0.25 / 2 ** r
            for k, (s, lo, hi) in FIELDS.items():
                for sgn in (+1, -1):
                    while True:
                        t = dict(v)
                        t[k] = min(hi, max(lo, v[k] + sgn * step * (hi - lo)))
                        if t[k] == v[k]:
                            break
                        sc, dd = score(t)
                        if sc < best - 0.01:
                            v, best, d = t, sc, dd
                            print(f"  r{r} {k} = {v[k]} ({v[k] / 65536:.3f}): {best:.2f} dB", flush=True)
                        else:
                            break
        print(f"fit: {best:.2f} dB  (per window {np.abs(d).mean(1).round(2)})")
        print("  " + " ".join(f"{k}={int(x)}" for k, x in v.items() if x != FIELDS[k][0]))
        print("  sustain, ours - ref per 1/3 octave from 63 Hz:", " ".join(f"{x:+.0f}" for x in d[2]))


main()
