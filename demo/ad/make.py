#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The Scintilla laser-harp commercial: three parts played on the emulated FM-1, then laid end to end.

    demo/ad/make.py            -> build/ad/scintilla-laser-harp-ad.wav

Each part is rendered by fm1/listen.py (so each is the FM-1's own output, checked sample for
sample against this computer's render); the only thing done here is the edit - where each part
starts, its gain, short fades, and the final peak level."""
import subprocess, sys, wave
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FS = 44100
#        name     preset  starts at  gain dB  fade in, out (s)
PARTS = [("intro", 32, 0.0, -3.0, 0.0, 0.6),       # Take-off
         ("harp",  36, 4.2, +2.0, 0.0, 0.3),       # Ring mod. - the laser harp
         ("outro", 33, 9.4, -2.0, 0.3, 0.8)]       # Landing


def load(p):
    with wave.open(str(p)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2).astype(float) / 32768


def main():
    out = ROOT / "build/ad/scintilla-laser-harp-ad.wav"
    parts = []
    for name, preset, at, db, fi, fo in PARTS:
        wav = ROOT / f"build/ad/{name}.wav"
        if "--no-render" not in sys.argv:
            subprocess.run([sys.executable, "fm1/listen.py", str(wav), "--part", f"{preset}:demo/ad/{name}.txt"],
                           cwd=ROOT, check=True)
        x = load(wav) * 10 ** (db / 20)
        ramp = np.ones(len(x))
        if fi: ramp[:int(fi * FS)] = np.linspace(0, 1, int(fi * FS))
        if fo: ramp[-int(fo * FS):] *= np.linspace(1, 0, int(fo * FS))
        parts.append((int(at * FS), x * ramp[:, None]))
    mix = np.zeros((max(a + len(x) for a, x in parts), 2))
    for a, x in parts:
        mix[a:a + len(x)] += x
    nz = np.nonzero(np.abs(mix).max(axis=1) > 10 ** (-70 / 20))[0]
    mix = mix[:nz[-1] + FS // 4]                                # trim the silence, keep a breath
    mix *= 10 ** (-1 / 20) / np.abs(mix).max()                 # peak at -1 dBFS
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(FS)
        w.writeframes(np.round(mix * 32767).astype(np.int16).tobytes())
    print(f"{out}: {len(mix) / FS:.1f} s")


main()
