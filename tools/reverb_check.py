#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The engine's reverb against the app's, impulse by impulse.

    tools/reverb_check.py [OUTDIR]          (needs build/sx_render: tests/run.sh or cc it)

The app's impulse is noise (tools/reverb_ir.mjs runs synthex-web's own buildIR and Chrome's scale);
the engine's is a feedback delay network (sx_synth.c). They cannot match sample for sample, so this
measures what a listener hears of a reverb, for every algorithm at sizes 0, 0.5, 1 and dampings 0,
0.5, 0.9: the energy (the wet level), the decay time (a line through the Schroeder curve from -5 to
-35 dB), the spectrum (1/3 octaves from 63 Hz, 20 ms to 0.5 s in, level removed), how much of the
energy is in the first 50 ms, and how alike L and R are. Two draws of the app's noise differ in
spectrum too: the limit sits on that floor (SPEC_DB + 1.5 floor), as tools/score_all.py's.
Fails outside the limits below."""
import subprocess, sys, tempfile
from pathlib import Path
import numpy as np, scipy.signal as ss

ROOT = Path(__file__).resolve().parent.parent
FS = 44100
LEVEL_DB, RT_REL, SPEC_DB, CORR = 0.5, 0.05, 1.0, 0.1
RECIPES = [(0.6, 2.5), (0.3, 1.4), (1.2, 4.5), (3.0, 9.0)]
NAMES = ["plate", "room", "hall", "galactic"]
EDGES = 63 * 2 ** (np.arange(0, 25) / 3)


def rt60(x):
    e = (x ** 2).sum(1)
    edc = 10 * np.log10(np.cumsum(e[::-1])[::-1] / e.sum() + 1e-30)
    i = np.where((edc <= -5) & (edc >= -35))[0]
    slope = np.polyfit(i / FS, edc[i], 1)[0]
    return -60 / slope


def bands(x, n):
    seg = x[int(0.02 * FS):max(int(0.02 * FS) + 4096, min(int(0.5 * FS), n))].mean(1)
    f, p = ss.welch(seg, FS, nperseg=4096)
    b = np.array([10 * np.log10(p[(f >= lo) & (f < hi)].mean() + 1e-30) for lo, hi in zip(EDGES, EDGES[1:])])
    return b - b.mean()


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
    out.mkdir(parents=True, exist_ok=True)
    print(f"{'reverb':10} {'size':>4} {'damp':>4}  {'level':>6}  {'RT60 app/C (s)':>15}  {'spec':>5} {'floor':>5}  "
          f"{'first 50 ms app/C':>17}  {'L/R corr app/C':>15}")
    bad = 0
    for a in range(4):
        for size in (0, 0.5, 1):
            for damp in (0, 0.5, 0.9):
                n = int((RECIPES[a][0] + size * (RECIPES[a][1] - RECIPES[a][0])) * FS)
                fa, fc = out / f"app-{a}-{size}-{damp}.f32", out / f"c-{a}-{size}-{damp}.f32"
                subprocess.run(["node", "--experimental-transform-types", "--no-warnings", "tools/reverb_ir.mjs",
                                str(a), str(size), str(damp), str(fa)], cwd=ROOT, check=True)
                subprocess.run([str(ROOT / "build/sx_render"), "reverb", str(a), str(size), str(damp),
                                str(1.5 * n / FS), str(fc)], cwd=ROOT, check=True)
                subprocess.run(["node", "--experimental-transform-types", "--no-warnings", "tools/reverb_ir.mjs",
                                str(a), str(size), str(damp), str(fa) + ".2"], cwd=ROOT, check=True)
                A2 = np.fromfile(str(fa) + ".2", "<f4").reshape(-1, 2).astype(float)
                A = np.fromfile(fa, "<f4").reshape(-1, 2).astype(float)
                C = np.fromfile(fc, "<f4").reshape(-1, 2).astype(float)
                lv = 10 * np.log10((C ** 2).sum() / (A ** 2).sum())
                ra, rc = rt60(A), rt60(C)
                sp = np.abs(bands(C, n) - bands(A, n)).mean()
                fl = np.abs(bands(A2, n) - bands(A, n)).mean()
                e50 = [10 * np.log10((x[:int(0.05 * FS)] ** 2).sum() / (x ** 2).sum()) for x in (A, C)]
                cr = [np.corrcoef(x[:, 0], x[:, 1])[0, 1] for x in (A, C)]
                ok = abs(lv) <= LEVEL_DB and abs(rc / ra - 1) <= RT_REL and sp <= SPEC_DB + 1.5 * fl and abs(cr[1]) <= CORR
                bad += not ok
                print(f"{NAMES[a]:10} {size:4.1f} {damp:4.1f}  {lv:+6.2f}  {ra:7.2f} {rc:7.2f}  {sp:5.2f} {fl:5.2f}  "
                      f"{e50[0]:8.1f} {e50[1]:8.1f}  {cr[0]:+7.2f} {cr[1]:+7.2f}  {'' if ok else 'FAIL'}", flush=True)
    print(f"limits: level {LEVEL_DB} dB, RT60 {RT_REL:.0%}, spectrum {SPEC_DB} dB + 1.5 floor, |L/R corr| {CORR}")
    sys.exit(1 if bad else 0)


main()
