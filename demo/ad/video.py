#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The Scintilla commercial as a video: the real firmware playing a score in fm1-emu's fm1-live.

    demo/ad/video.py [--fps-panel 10] [--jobs 8]
      -> build/ad/video/scintilla-short.mp4   1080x1920 (YouTube Shorts, X)
         build/ad/video/scintilla-square.mp4  1080x1080 (X timeline)

The score below goes to the firmware as MIDI into the DIN jack (program changes and notes), so the
sound is the firmware's own output and the panel is the emulator's picture of it at each moment -
one headless run per panel frame (they are cached by the score). The video adds titles, a scope
and the laser beams over the harp part, and sets the peak to -1 dBFS; the sound is otherwise untouched.
FM1_LIVE: fm1-live (default ~/work/fm1-emu/target/release/fm1-live)."""
import hashlib, os, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FWSC = ROOT / "firmware/build/scintilla.fwsc"
LIVE = Path(os.environ.get("FM1_LIVE", Path.home() / "work/fm1-emu/target/release/fm1-live"))
OUT = ROOT / "build/ad/video"
FS, FPS = 44100, 30

# --- the score: (seconds, program), (seconds, CC, value) and (seconds on, seconds off, notes, velocity) -
INTRO, HARP, OUTRO = 54, 36, 7                      # Glide Strings, Ring mod. (the laser harp), Brass I
PROGRAMS = [(0.3, INTRO), (8.8, HARP)]              # and the outro's, below
CCS = [(0.35, 93, 100),                             # Glide Strings: more chorus (mix 0.79, the preset's 0.5)
       (0.35, 91, 32)]                              # and a bit of its plate reverb (mix 0.25; the preset's is off)
NOTES = [(0.6, 2.5, [53, 56, 60, 65], 90),          # Fm
         (2.6, 4.5, [49, 53, 56, 61], 90),          # Db
         (4.6, 6.4, [48, 52, 55, 60], 95)]          # C
# the laser harp, from the score (F minor, 4/4): C dotted half, then B-natural Bb Ab as 16th-8th-16th,
# the Ab tied into a dotted half, then Eb D-natural C the same way, the C tied into the last dotted half.
# Pitch and tempo as in the recording of it (voice memo of 2026-10-22): C sounds C2 (65 Hz), which on
# preset 36 is MIDI 48 (its OSC1 is an octave down), and a long note starts every 3.76 s, 64 BPM.
# (beat it starts on, beats it lasts, note)
BEAT, HARP_T0 = 60 / 64, 9.0
HARP = [(0, 3, 48),
        (3, 0.25, 47), (3.25, 0.5, 46), (3.75, 3.25, 44),
        (7, 0.25, 51), (7.25, 0.5, 50), (7.75, 3.25, 48)]
order = sorted({n for _, _, n in HARP})
BEAMS = []                                          # (on, off, beam, beams) for the laser fan
for b, d, n in HARP:
    on, off = HARP_T0 + b * BEAT, HARP_T0 + (b + d) * BEAT - 0.02
    NOTES.append((on, off, [n], 127))
    BEAMS.append((on, off, order.index(n), len(order)))
O = round(HARP_T0 + max(b + d for b, d, _ in HARP) * BEAT + 0.55, 2)   # the outro starts
PROGRAMS.append((O, OUTRO))
NOTES += [(O + 0.2, O + 0.55, [49, 53, 56, 61], 110),     # Db stab
          (O + 0.7, O + 1.05, [51, 55, 58, 63], 110),     # Eb stab
          (O + 1.2, O + 3.2, [53, 56, 60, 65, 72], 120)]  # Fm, held
SECTIONS = [(0.0, "GLIDE STRINGS"), (8.8, "LASER HARP"), (O, "BRASS I")]
END = round(O + 5.4, 2)
CREDIT = O + 1.6                                    # the end card: what it is, where it is
CALL, REPO = "FREE & OPEN SOURCE", "github.com/joakimeriksson/scintilla-fm1"


def keys():
    ev = [(t, f"mc0{p:02x}") for t, p in PROGRAMS] + [(t, f"mb0{c:02x}{v:02x}") for t, c, v in CCS]
    for on, off, ns, v in NOTES:
        ev += [(on, f"m90{n:02x}{v:02x}") for n in ns] + [(off, f"m80{n:02x}00") for n in ns]
    return ",".join(f"{round(t * 1000)}:{m}" for t, m in sorted(ev))


def live(ms, env, wd):
    (Path(wd) / "work").mkdir(exist_ok=True)
    r = subprocess.run([str(LIVE), "--fwsc", str(FWSC), "--bench", str(ms)], cwd=wd, capture_output=True,
                       text=True, env=dict(os.environ, FM1_BENCH_KEYS=keys(), **env))
    if r.returncode or "halt" in r.stdout + r.stderr:
        sys.exit(f"fm1-live --bench {ms} failed:\n{r.stdout[-1500:]}{r.stderr[-1500:]}")


def panel_png(ms, cache):
    """A panel frame's file, named by the part of the score it has seen: an edit late in the score
    keeps the frames before it."""
    seen = ",".join(k for k in keys().split(",") if int(k.split(":")[0]) <= ms)
    return cache / f"{ms:06d}-{hashlib.sha1(seen.encode()).hexdigest()[:8]}.png"


def panel(ms, cache):
    png = panel_png(ms, cache)
    if not png.exists():
        with tempfile.TemporaryDirectory() as wd:
            live(ms, {"FM1_BENCH_PANEL": f"{wd}/p.ppm"}, wd)
            Image.open(f"{wd}/p.ppm").convert("RGB").save(png)
    return png


def font(name, size, index=0):
    for p in (f"/System/Library/Fonts/Supplemental/{name}", f"/System/Library/Fonts/{name}"):
        if Path(p).exists():
            return ImageFont.truetype(p, size, index=index)
    return ImageFont.load_default()


def spaced(d, xy, text, f, fill, track, anchor_center=True):
    w = sum(d.textlength(c, font=f) for c in text) + track * (len(text) - 1)
    x, y = xy
    x -= w / 2 if anchor_center else 0
    for c in text:
        d.text((x, y), c, font=f, fill=fill)
        x += d.textlength(c, font=f) + track


class Frame:
    """One video format: where the title, the stage (scope and beams) and the panel go."""

    def __init__(self, w, h, title_y, stage, panel_y, foot_y, big):
        self.w, self.h, self.title_y, self.stage, self.panel_y, self.foot_y, self.big = w, h, title_y, stage, panel_y, foot_y, big
        self.f_title = font("Futura.ttc", 120 if big else 84, 0)
        self.f_sub = font("Avenir Next.ttc", 38 if big else 30, 0)
        self.f_sec = font("Futura.ttc", 54 if big else 40, 0)
        self.f_foot = font("Avenir Next.ttc", 28 if big else 24, 0)

    def draw(self, t, pan, audio):
        W, H = self.w, self.h
        im = Image.new("RGB", (W, H), (8, 8, 12))
        card = max(0.0, min(1.0, (t - CREDIT) / 0.5))       # the end card fades in, the scope down
        y0, y1 = self.stage
        # the stage: laser beams in the harp part, a scope always
        glow = Image.new("RGB", (W, y1 - y0), (0, 0, 0))
        g = ImageDraw.Draw(glow)
        # as on Jarre's laser harp: the whole fan is lit through the harp part, and a note is a hand in
        # its beam - the beam stops at the hand, which it lights, until the note is let go
        n = BEAMS[0][3]
        a = max(0.0, min(1.0, (t - 8.8) / 0.3, (O - t) / 0.3)) if 8.8 <= t < O else 0.0
        cut = [1.0] * n                                    # how far up each beam reaches
        for on, off, k, _ in BEAMS:
            if on <= t < off:
                cut[k] = 0.40 + 0.06 * (k % 3)             # the hand, at about chest height
        if a > 0:
            ox, oy = W / 2, y1 - y0
            col = tuple(int(c * a) for c in (40, 255, 90))
            for k in range(n):
                bx = W / 2 + (k - (n - 1) / 2) * (W * 0.62 / max(1, n - 1))
                hx, hy = ox + (bx - ox) * cut[k], oy * (1 - cut[k])
                g.line([(ox, oy), (hx, hy)], fill=col, width=7 if self.big else 5)
                if cut[k] < 1:
                    r = 16 if self.big else 11
                    g.ellipse([hx - r, hy - r, hx + r, hy + r], fill=tuple(int(c * a) for c in (190, 255, 200)))
        i = int(t * FS)
        seg = audio[max(0, i - 1100):i, 0] if i > 0 else np.zeros(1)
        if len(seg) > 2:
            xs = np.linspace(W * 0.06, W * 0.94, len(seg))
            mid = (y1 - y0) * (0.5 if not (8.8 <= t < O) else 0.82)
            amp = (y1 - y0) * (0.36 if not (8.8 <= t < O) else 0.14)
            g.line(list(zip(xs, mid - seg * amp)), fill=tuple(int(c * (1 - 0.75 * card)) for c in (255, 150, 60)), width=4)
        im.paste(Image.blend(glow, glow.filter(ImageFilter.GaussianBlur(9)), 0.5), (0, y0))
        lit = glow.filter(ImageFilter.GaussianBlur(22))
        base = im.crop((0, y0, W, y1))
        im.paste(Image.fromarray(np.minimum(255, np.asarray(base, np.int16) + np.asarray(lit, np.int16) * 1.4).astype(np.uint8)), (0, y0))
        d = ImageDraw.Draw(im)
        spaced(d, (W / 2, self.title_y), "SCINTILLA", self.f_title, (240, 240, 245), 22 if self.big else 16)
        sub = "the 1981 Elka Synthex, reborn on a M-VAVE FM-1"
        d.text((W / 2, self.title_y + (165 if self.big else 115)), sub, font=self.f_sub, fill=(150, 150, 160), anchor="mt")
        sec = [s for s0, s in SECTIONS if t >= s0][-1]
        spaced(d, (W / 2, y1 - (80 if self.big else 58)), sec, self.f_sec, tuple(int(c * (1 - card)) for c in (255, 154, 60)), 10)
        if card > 0:
            cy = (y0 + y1) / 2
            spaced(d, (W / 2, cy - (90 if self.big else 62)), CALL, self.f_sec, tuple(int(c * card) for c in (240, 240, 245)), 10)
            d.text((W / 2, cy + (20 if self.big else 12)), REPO, font=self.f_sub, fill=tuple(int(c * card) for c in (255, 154, 60)), anchor="mt")
        p = pan.resize((W, round(pan.height * W / pan.width)), Image.Resampling.LANCZOS)
        im.paste(p, (0, self.panel_y))
        if self.foot_y:
            d.text((W / 2, self.foot_y), "real firmware in fm1-emu, sound unedited  ·  not affiliated with Elka",
                   font=self.f_foot, fill=(110, 110, 120), anchor="mt")
        fade = min(1.0, (END - t) / 0.8)                     # no fade-in: the first frame is the thumbnail
        return im if fade >= 1 else Image.eval(im, lambda v: int(v * max(0.0, fade)))


def main():
    jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else os.cpu_count()
    pfps = int(sys.argv[sys.argv.index("--fps-panel") + 1]) if "--fps-panel" in sys.argv else 10
    OUT.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha1(FWSC.read_bytes()).hexdigest()[:10]                   # one cache per firmware
    cache = OUT / f"panels-{tag}"
    cache.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory() as wd:                 # the sound: one run, the whole score
        live(round(END * 1000), {"FM1_BENCH_WAV": f"{wd}/a.raw"}, wd)
        audio = np.frombuffer(Path(f"{wd}/a.raw").read_bytes(), np.int16).reshape(-1, 2).astype(float) / 32768
    # the audio starts when the firmware's does, ~0.15 s after power-on; the panels count from power-on
    audio = np.vstack([np.zeros((max(0, int(END * FS) - len(audio)), 2)), audio, np.zeros((FS, 2))])
    wav = OUT / "audio.wav"
    import wave
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(FS)
        w.writeframes(np.round(audio[:int(END * FS)] * (10 ** (-1 / 20) / np.abs(audio).max()) * 32767).astype(np.int16).tobytes())
    print(f"{wav}: the firmware's sound, peak {20 * np.log10(np.abs(audio).max() + 1e-12):.1f} dBFS")

    times = sorted({max(100, round(1000 * k / pfps)) for k in range(int(END * pfps) + 1)})
    pngs = {ms: panel_png(ms, cache) for ms in times}
    todo = [ms for ms in times if not pngs[ms].exists()]
    print(f"{len(times)} panel frames, {len(todo)} to run ({jobs} at a time)")
    with ThreadPoolExecutor(jobs) as ex:
        for k, _ in enumerate(ex.map(lambda ms: panel(ms, cache), todo)):
            if k % 20 == 19:
                print(f"  {k + 1}/{len(todo)}", flush=True)

    view = audio / max(1e-9, np.abs(audio).max())
    for name, fr in (("scintilla-short", Frame(1080, 1920, 150, (430, 1120), 1150, 1860, True)),
                     ("scintilla-square", Frame(1080, 1080, 34, (190, 388), 388, 0, False))):
        mp4 = OUT / f"{name}.mp4"
        ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                               "-s", f"{fr.w}x{fr.h}", "-r", str(FPS), "-i", "-", "-i", str(wav),
                               "-c:v", "libx264", "-preset", "slow",
                               "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                               "-movflags", "+faststart", "-shortest", str(mp4)], stdin=subprocess.PIPE)
        cur = None
        for i in range(int(END * FPS)):
            t = i / FPS
            ms = max(100, round(1000 * int(t * pfps) / pfps))
            if cur is None or cur[0] != ms:
                cur = (ms, Image.open(pngs[ms]).convert("RGB"))
            ff.stdin.write(fr.draw(t, cur[1], view).tobytes())
        ff.stdin.close()
        if ff.wait():
            sys.exit("ffmpeg failed")
        print(f"{mp4}: {fr.w}x{fr.h}, {END:.1f} s")


main()
