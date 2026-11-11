#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The tuning page's data (docs/tuning/): the tour's sound, spectrograms and scores, from video.py's last run.

    demo/tour/page.py HW.wav DOCS [ROUND.txt ...]

Reads build/tour/film and build/tour/audio.wav (the firmware's run and the sound track of
build/tour/scintilla-presets.mp4: run video.py without --ab first) and writes into DOCS/tuning/:
  tour.mp3          the video's sound track (Scintilla alone); the page plays each preset from it
  tour.webp         its spectrogram, the whole tour in one strip
  spec/{slot}.webp  the recording's stretch above Scintilla's, the same notes, one colour scale
  data.js           per preset: the stretch, the notes, the video's score, the two third-octave spectra
                    (level-free) and where it sits in tour.mp3; ROUND.txt (video.py's printouts of
                    earlier runs, oldest first) add each preset's score in each round
The recording itself stays here: only its spectrum and spectrogram go on the page."""
import json, re, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image

hw, docs, rounds = sys.argv[1], Path(sys.argv[2]), sys.argv[3:]
sys.argv = sys.argv[:2]                         # video.py reads its own flags at import
sys.path.insert(0, str(Path(__file__).parent))
import video as V
import transcribe as T

FS = V.FS
OUT = docs / "tuning"
(OUT / "spec").mkdir(parents=True, exist_ok=True)

segs, harp, end = V.plan(hw, None)
d = V.OUT / "film"
t0 = float(re.search(r"audio from ([0-9.]+) ms", (d / "live.log").read_text()).group(1)) / 1000
a = np.frombuffer((d / "fr/audio.raw").read_bytes(), np.int16).reshape(-1, 2).astype(float) / 32768
sc = np.vstack([np.zeros((round(t0 * FS), 2)), a])
assert len(sc) >= int(end * FS) - FS, f"{d} is not the run of this plan ({len(sc) / FS:.1f} s, {end:.1f} s)"
track = V.OUT / "audio.wav"

past = []
for f in rounds:
    r = {}
    for line in open(f):
        m = re.match(r"\s+(\d+) .+? at\s+[\d.]+ s\s+\d+ notes\s+([\d.]+) dB", line)
        if m:
            r[int(m[1])] = float(m[2])
    past.append(r)

# third-octave bands: twelve of transcribe.py's third-semitone bins each
n_bins = T.MEL.shape[0]
centers = [30 * 2 ** ((i + 5.5) / 36) for i in range(0, n_bins, 12)]


def level_free(h, e):
    a, b = V.third(h), V.third(e)
    keep = a > a.max() - 50
    off = (a - b)[keep].mean()
    top = a[keep].max()
    return [round(x - top, 1) for x in a], [round(x + off - top, 1) for x in b], keep.tolist()


# spectrograms: 4096-point frames, rows on a log axis from F_LO to F_HI, RANGE dB under the clip's loudest
F_LO, F_HI, RANGE, ROWS = 40.0, 11000.0, 72.0, 320
STOPS = [(0.00, (11, 10, 12)), (0.22, (38, 14, 36)), (0.45, (112, 30, 22)), (0.66, (206, 92, 26)),
         (0.84, (242, 160, 72)), (1.00, (255, 243, 220))]


def spectrogram(x, hop=128, nfft=4096):
    x = np.concatenate([np.zeros(nfft // 2), x, np.zeros(nfft // 2)])
    n = 1 + (len(x) - nfft) // hop
    fr = np.lib.stride_tricks.as_strided(x, (n, nfft), (x.strides[0] * hop, x.strides[0]))
    P = np.abs(np.fft.rfft(fr * np.hanning(nfft), axis=1)) ** 2
    f = F_LO * (F_HI / F_LO) ** (np.arange(ROWS)[::-1] / (ROWS - 1))      # top row: F_HI
    k = f / (FS / nfft)
    lo = np.floor(k).astype(int)
    w = k - lo
    G = P[:, lo] * (1 - w) + P[:, lo + 1] * w                              # frames x rows
    return 10 * np.log10(G.T + 1e-14)


def colour(db, ref):
    v = np.clip((db - ref + RANGE) / RANGE, 0, 1) ** 1.15
    out = np.zeros(v.shape + (3,))
    for (p0, c0), (p1, c1) in zip(STOPS, STOPS[1:]):
        m = (v >= p0) & (v <= p1)
        t = ((v - p0) / (p1 - p0))[m][:, None]
        out[m] = np.array(c0) * (1 - t) + np.array(c1) * t
    return out.astype(np.uint8)


def image(db, ref, width, height):
    return Image.fromarray(colour(db, ref)).resize((width, height), Image.Resampling.LANCZOS)


presets = []
W_, H_, GAP = 1200, 260, 8
for s in segs:
    k = int(s["len"] * FS)
    h = T.read_wav(hw, s["hw_at"], s["len"])
    j = int(s["t_sc"] * FS)
    e = sc[j:j + k].mean(1)
    sh, se, keep = level_free(h, e)
    Sh, Se = spectrogram(h), spectrogram(e)     # each panel on its own loudest point: level-free, as the score
    im = Image.new("RGB", (W_, 2 * H_ + GAP), STOPS[0][1])
    im.paste(image(Sh, Sh.max(), W_, H_), (0, 0))
    im.paste(image(Se, Se.max(), W_, H_), (0, H_ + GAP))
    im.save(OUT / "spec" / f"{s['slot']}.webp", quality=82, method=6)
    presets.append(dict(slot=s["slot"], name=s["name"], at=round(s["hw_at"], 2), len=s["len"],
                        t=round(s["t_sc"], 3), notes=len(s["evs"]) // 2, score=round(V.closeness(h, e), 2),
                        rounds=[r.get(s["slot"]) for r in past], hw=sh, sc=se, keep=keep))
    print(f"  {s['slot']} {s['name']:18} {presets[-1]['score']:5.2f} dB", flush=True)

# the whole tour in one strip, near its loudest point at the top of the scale
x = T.read_wav(track)
S = spectrogram(x, hop=512)
image(S, np.percentile(S, 99.9), 3200, 360).save(OUT / "tour.webp", quality=80, method=6)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(track), "-c:a", "libmp3lame", "-b:a", "128k",
                str(OUT / "tour.mp3")], check=True)

data = dict(bands=[round(c) for c in centers], spec=dict(lo=F_LO, hi=F_HI, range=RANGE),
            tour=dict(end=round(len(x) / FS, 3), harp=round(harp["t"], 3)), presets=presets)
(OUT / "data.js").write_text("// generated by demo/tour/page.py: do not edit\nwindow.TUNING = " +
                             json.dumps(data, separators=(",", ":")) + ";\n")
print(f"mean {np.mean([p['score'] for p in presets]):.2f} dB; rounds",
      *(f"{np.mean([v for v in r.values()]):.2f}" for r in past))
