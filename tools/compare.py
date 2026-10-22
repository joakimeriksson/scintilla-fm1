#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Score a C render against the VoiceCore reference (both raw float32 mono, 44.1 kHz).

    compare.py REF.f32 C.f32 [--json]

level: rms of each in dB and the difference; snr: the reference over (reference - C), sample by
sample, which is only meaningful for patches without noise or random LFOs; spec: the mean absolute
difference of the two Welch spectra in dB, over 40 Hz - 16 kHz where the reference is within 80 dB
of its peak (the measure that holds for random patches too)."""
import json, sys
import numpy as np

def welch_db(x, n=4096):
    w = np.hanning(n)
    segs = [x[i:i + n] * w for i in range(0, len(x) - n, n // 2)]
    if not segs:
        segs = [np.pad(x, (0, n - len(x))) * w]
    p = np.mean([np.abs(np.fft.rfft(s)) ** 2 for s in segs], axis=0)
    return 10 * np.log10(p + 1e-30)

def score(ref, c):
    n = min(len(ref), len(c))
    ref, c = ref[:n].astype(np.float64), c[:n].astype(np.float64)
    rms = lambda x: 10 * np.log10(np.mean(x ** 2) + 1e-30)
    err = np.sum((ref - c) ** 2)
    snr = 10 * np.log10(np.sum(ref ** 2) / err) if err > 0 else 999.0
    a, b = welch_db(ref), welch_db(c)
    f = np.fft.rfftfreq(4096, 1 / 44100)
    m = (f >= 40) & (f <= 16000) & (a > a.max() - 80)
    spec = float(np.mean(np.abs(a[m] - b[m]))) if m.any() else 0.0
    return {"ref_db": rms(ref), "c_db": rms(c), "level": rms(c) - rms(ref), "snr": snr, "spec": spec,
            "peak_ref": float(np.max(np.abs(ref))), "peak_c": float(np.max(np.abs(c)))}

if __name__ == "__main__":
    r = score(np.fromfile(sys.argv[1], "<f4"), np.fromfile(sys.argv[2], "<f4"))
    print(json.dumps(r) if "--json" in sys.argv else
          f"level {r['ref_db']:.2f} / {r['c_db']:.2f} dB ({r['level']:+.2f})  snr {r['snr']:.1f} dB  spec {r['spec']:.2f} dB")
