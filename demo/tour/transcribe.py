#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The notes of a stretch of Per Kristian's run-through, found with the engine's own notes.

    demo/tour/transcribe.py HW.wav SLOT START LEN [--out notes.txt]

Each key of the preset (MIDI 24..96) is rendered alone by the host engine (build/sc_render) and its
spectrum, on a semitone-spaced log-frequency axis, becomes a template. The stretch's spectrogram is
then explained as a non-negative mix of those templates (KL multiplicative updates, templates fixed),
so a preset's footages, transposes and timbre are in the templates and the activations are keys.
A key's activation that rises above a share of the loudest one starts a note; it ends when it falls
back. The result is a scenario for sc_render (on / off lines) with times from the stretch's start.
"""
import os, subprocess, sys, tempfile, wave
os.environ.setdefault("OMP_NUM_THREADS", "1")
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RENDER = ROOT / "build/sc_render"
FS, HOP, NFFT = 44100, 441, 8192
KEYS = range(36, 97)                         # the Synthex's keyboard: 61 keys, C2 to C7
CACHE = ROOT / "build/tour/templates"


def read_wav(path, start=0.0, dur=None):
    with wave.open(str(path)) as w:
        fs, ch = w.getframerate(), w.getnchannels()
        assert fs == FS, f"{path}: {fs} Hz"
        w.setpos(int(start * fs))
        n = w.getnframes() - int(start * fs) if dur is None else int(dur * fs)
        x = np.frombuffer(w.readframes(n), np.int16).reshape(-1, ch).astype(float) / 32768
    return x.mean(1)


def logbins():
    """Third-semitone bins from 30 Hz to 11 kHz: a matrix from FFT bins."""
    f = np.fft.rfftfreq(NFFT, 1 / FS)
    centers = 30 * 2 ** (np.arange(0, 3 * 12 * np.log2(11000 / 30)) / 36)
    M = np.zeros((len(centers), len(f)))
    for i, c in enumerate(centers):
        lo, hi = c * 2 ** (-1 / 72), c * 2 ** (1 / 72)
        sel = (f >= lo) & (f < hi)
        if not sel.any():
            sel = np.abs(f - c) == np.abs(f - c).min()
        M[i, sel] = 1 / sel.sum()
    return M


MEL = logbins()


def spec(x):
    win = np.hanning(NFFT)
    x = np.concatenate([np.zeros(NFFT // 2), x, np.zeros(NFFT // 2)])
    n = 1 + (len(x) - NFFT) // HOP
    fr = np.lib.stride_tricks.as_strided(x, (n, NFFT), (x.strides[0] * HOP, x.strides[0]))
    return MEL @ np.abs(np.fft.rfft(fr * win, axis=1)).T          # bins x frames


def template(slot, key, span=0.8):
    """A key's spectrum on the preset, averaged over its first span seconds past the attack's tick."""
    out = CACHE / f"{slot}-{key}-{span}.npy"
    if out.exists():
        return np.load(out)
    with tempfile.TemporaryDirectory() as d:
        sc = Path(d) / "s.txt"
        sc.write_text(f"dur {span + 0.4}\non 0.0 {key} 1.0\noff {span + 0.2} {key}\n")
        subprocess.run([str(RENDER), "synth", str(slot - 10), str(sc), f"{d}/o.wav"], check=True, capture_output=True)
        S = spec(read_wav(f"{d}/o.wav"))
    t = S[:, 3:round(span * FS / HOP)].mean(1)
    np.save(out, t)
    return t


def templates(slot, span=0.8):
    CACHE.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(os.cpu_count()) as ex:
        W = np.stack(list(ex.map(lambda k: template(slot, k, span), KEYS)), 1)
    return W / (W.sum(0, keepdims=True) + 1e-12)


def activations(S, W, iters=200):
    H = np.full((W.shape[1], S.shape[1]), S.sum(0).mean() / W.shape[1] + 1e-9)
    for _ in range(iters):
        H *= (W.T @ (S / (W @ H + 1e-12))) / (W.sum(0)[:, None] + 1e-12)
    return H


def notes(H, rel=0.18, min_len=0.07, gap=0.05):
    """Key activations -> (on, off, key). A note starts where a key's activation passes rel x the
    stretch's loud frames and carries a fair share of its frame; it holds while it stays above a quarter
    of its own peak (a decay to the sustain is not a new note) and splits where it climbs back to twice
    its dip (a repeated key)."""
    fps = FS / HOP
    tot = H.sum(0)
    thr_on = rel * np.percentile(tot, 95)
    out = []
    for i, k in enumerate(KEYS):
        a = np.convolve(H[i], np.ones(3) / 3, "same")
        share = a / (tot + 1e-12)
        on = None
        for t in range(len(a)):
            if on is None:
                if a[t] > thr_on and share[t] > 0.12:
                    on, peak, dip = t, a[t], a[t]
                continue
            peak, dip = max(peak, a[t]), min(dip, a[t])
            end = a[t] < max(0.25 * peak, 0.3 * thr_on) or share[t] < 0.04 or t == len(a) - 1
            again = dip < 0.6 * peak and a[t] > 2 * dip and a[t] > thr_on and t - on > 0.08 * fps
            if end or again:
                if (t - on) / fps >= min_len:
                    out.append([on / fps, t / fps, k])
                on = t if again else None
                if again:
                    peak = dip = a[t]
    # octave ghosts: a note mostly covered by one an octave or twelfth away, and quieter, goes
    out.sort()
    keep = []
    for n in out:
        i = KEYS.index(n[2])
        e = H[i, int(n[0] * fps):int(n[1] * fps) + 1].sum()
        rivals = [m for m in out if m is not n and abs(m[2] - n[2]) in (12, 19, 24)
                  and min(m[1], n[1]) - max(m[0], n[0]) > 0.6 * (n[1] - n[0])]
        if any(H[KEYS.index(m[2]), int(n[0] * fps):int(n[1] * fps) + 1].sum() > 2 * e for m in rivals):
            continue
        keep.append(n)
    # bridge tiny gaps in the same key (vibrato, tremolo dips)
    keep.sort(key=lambda n: (n[2], n[0]))
    merged = []
    for n in keep:
        if merged and merged[-1][2] == n[2] and n[0] - merged[-1][1] < gap:
            merged[-1][1] = n[1]
        else:
            merged.append(n)
    return sorted(merged)


def scenario(ns, dur):
    lines = [f"dur {dur:.3f}"]
    for on, off, k in ns:
        lines += [f"on {on:.3f} {k} 1.0", f"off {off:.3f} {k}"]
    return "\n".join(lines) + "\n"


def main():
    hw, slot, start, dur = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    W = templates(slot)
    S = spec(read_wav(hw, start, dur))
    H = activations(S, W)
    ns = notes(H)
    txt = scenario(ns, dur)
    if out:
        Path(out).write_text(txt)
    else:
        sys.stdout.write(txt)


if __name__ == "__main__":
    main()
