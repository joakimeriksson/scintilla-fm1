#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The Scintilla commercial as a video: the real firmware playing a score in fm1-emu's fm1-live.

    demo/ad/video.py [--fps-panel 10] [--jobs 8]
      -> build/ad/video/scintilla-short.mp4   1080x1920 (YouTube Shorts, X)
         build/ad/video/scintilla-square.mp4  1080x1080 (X timeline)

The score below goes to the firmware as MIDI into the DIN jack (program changes and notes), so the
sound is the firmware's own output and the panel is the emulator's picture of it at each moment -
one headless run per panel frame (they are cached by the score). The video adds titles, a scope
and the laser beams over the harp part, sets each part to the same loudness and the peak to -1 dBFS; the
sound is otherwise untouched.
--ab HW.wav: with three notes of the real Synthex in it (see the score), as scintilla-*-ab.mp4.
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
# The laser harp first (the hook, and the first frame is the thumbnail), then three presets in three
# seconds each with what Scintilla is, then Brass I under the end card.
# With --ab HW.wav (Per Kristian Risvik's "Elka Synthex - Presets" at 44.1 kHz, used with his permission)
# the harp's second half is his Synthex playing it (the riff at 13:09 of the recording), and Scintilla
# plays the same notes after it.
HW = sys.argv[sys.argv.index("--ab") + 1] if "--ab" in sys.argv else None
HARP, CHUNKY, CHIMES, STRINGS, BRASS = 36, 0, 28, 54, 7
PROGRAMS, CCS, NOTES, BEAMS = [(0.3, HARP)], [], [], []
# the laser harp, from the score (F minor, 4/4): C dotted half, then B-natural Bb Ab as 16th-8th-16th,
# the Ab tied into a dotted half, then Eb D-natural C the same way, the C tied into the last dotted half.
# Pitch and tempo as in the recording of it (voice memo of 2026-10-22): C sounds C2 (65 Hz), which on
# preset 36 is MIDI 48 (its OSC1 is an octave down), and a long note starts every 3.76 s, 64 BPM.
# (beat it starts on, beats it lasts, note)
BEAT, HARP_T0 = 60 / 64, 0.5
PHRASE = [(0, 3, 48), (3, 0.25, 47), (3.25, 0.5, 46), (3.75, 3.25, 44)]
ANSWER = [(7, 0.25, 51), (7.25, 0.5, 50), (7.75, 3.25, 48)]
RIFF = [(0.0, 0.24, 51), (0.22, 0.67, 50), (0.63, 3.0, 48)]     # the same three as he plays them: seconds
HW_AT, HW_LEN = 789.6, 3.0                          # where they are in the recording (demo/tour's stretch)
order = sorted({n for _, _, n in PHRASE + ANSWER})


def harp(on, off, n):
    NOTES.append((on, off - 0.02, [n], 127))
    BEAMS.append((on, off - 0.02, order.index(n), len(order)))      # (on, off, beam, beams) for the laser fan


for b, d, n in PHRASE + ([] if HW else ANSWER):
    harp(HARP_T0 + b * BEAT, HARP_T0 + (b + d) * BEAT, n)
if HW:
    HW_T = round(HARP_T0 + 7 * BEAT + 0.35, 2)      # the Synthex answers
    SC_T = round(HW_T + HW_LEN + 0.4, 2)            # and Scintilla repeats it
    for a, b, n in RIFF:
        harp(SC_T + a, SC_T + b, n)
    M = round(SC_T + HW_LEN + 0.45, 2)
    SPANS = [(-1, HW_T - 0.15), (SC_T - 0.3, M - 0.1)]              # when the laser fan is lit
else:
    HW_T = SC_T = -100.0
    M = round(HARP_T0 + 11 * BEAT + 0.45, 2)
    SPANS = [(-1, M - 0.1)]
# the montage, from M
PROGRAMS += [(M, CHUNKY), (M + 2.8, CHIMES), (M + 5.6, STRINGS)]
for k, n in enumerate([41, 41, 53, 41, 44, 41, 51, 48]):           # Chunky Synth: a bass line in F minor
    NOTES.append((M + 0.15 + 0.2 * k, M + 0.15 + 0.2 * k + (0.16 if k < 7 else 0.7), [n], 115))
for k, n in enumerate([65, 68, 72, 77, 80, 84]):                   # Chimes: the chord, upwards
    NOTES.append((M + 2.95 + 0.2 * k, M + 2.95 + 0.2 * k + 1.2, [n], 100))
CCS += [(M + 5.65, 93, 100),                        # Glide Strings: more chorus (mix 0.79, the preset's 0.5)
        (M + 5.65, 91, 32)]                         # and a bit of its plate reverb (mix 0.25; the preset's is off)
NOTES.append((M + 5.8, M + 8.1, [53, 56, 60, 65], 90))             # Fm
O = round(M + 8.4, 2)                               # the outro starts
PROGRAMS.append((O, BRASS))
NOTES += [(O + 0.2, O + 0.55, [49, 53, 56, 61], 110),     # Db stab
          (O + 0.7, O + 1.05, [51, 55, 58, 63], 110),     # Eb stab
          (O + 1.2, O + 3.2, [53, 56, 60, 65, 72], 120)]  # Fm, held
SECTIONS = [(0.0, "LASER HARP")] + ([(HW_T - 0.15, "A REAL SYNTHEX, 1981"), (SC_T - 0.3, "SCINTILLA, 2026")] if HW else []) + \
           [(M, "CHUNKY SYNTH"), (M + 2.8, "CHIMES"), (M + 5.6, "GLIDE STRINGS"), (O, "BRASS I")]
# what it is, over the montage: (from, to, line, small line)
CLAIMS = [(M + 0.1, M + 2.7, "40 FACTORY PRESETS", "decoded from the Synthex's own ROM"),
          (M + 2.9, M + 5.5, "TUNED BY MEASUREMENT", "against a recording of a real Synthex"),
          (M + 5.7, O - 0.1, "BUILT FROM ELKA'S SCHEMATICS", "ring modulator, cross-mod, LFO")]
if HW:
    CLAIMS.append((HW_T - 0.15, SC_T - 0.3, "", "recording: Per Kristian Risvik, perkristian.net"))
END = round(O + 5.4, 2)
CREDIT = O + 1.6                                    # the end card: what it is, where it is
CALL, REPO = "FREE & OPEN SOURCE", "github.com/joakimeriksson/scintilla-fm1"
AMBER, BLUE = (255, 150, 60), (63, 143, 239)        # Scintilla's trace, the Synthex's
# each part at the same loudness (the presets' own levels differ by 20 dB): where a part's gain holds
PARTS = [(0.0, HW_T - 0.15 if HW else M - 0.05)] + ([(SC_T - 0.2, M - 0.05)] if HW else []) + \
        [(M - 0.05, M + 2.75), (M + 2.75, M + 5.55), (M + 5.55, O - 0.05), (O - 0.05, END)]
LEVEL = 10 ** (-20 / 20)


def balance(audio):
    """The parts at LEVEL rms, measured while their notes sound; the gain moves over 60 ms between them."""
    g = np.ones(len(audio))
    for a, b in PARTS:
        on = [(max(a, n0), min(b, n1)) for n0, n1, _, _ in NOTES if n0 < b and n1 > a]
        i, j = int(min(x for x, _ in on) * FS), int(max(y for _, y in on) * FS)
        g[int(max(0, a) * FS):int(b * FS)] = LEVEL / np.sqrt(np.mean(audio[i:j] ** 2))
    k = int(0.06 * FS)
    g = np.convolve(np.pad(g, k, mode="edge"), np.ones(k) / k, mode="same")[k:-k]
    return audio * g[:, None]



def fan(t):
    """How bright the laser fan is at t (0 to 1)."""
    return max([0.0] + [min(1.0, (t - a) / 0.3, (b - t) / 0.3) for a, b in SPANS if a <= t < b])


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
        self.f_year = font("Futura.ttc", 330 if big else 150, 0)
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
        a = fan(t)
        real = HW_T - 0.15 <= t < SC_T - 0.3               # the recording is playing
        trace = BLUE if real else AMBER
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
        if HW and HW_T - 0.15 <= t < M - 0.1:               # the year, behind the trace
            k = min(1.0, (t - (HW_T - 0.15)) / 0.25, (M - 0.1 - t) / 0.25, abs(t - (SC_T - 0.3)) / 0.2)
            yr, c = ("1981", BLUE) if real else ("2026", AMBER)
            g.text((W / 2, (y1 - y0) * (0.5 if self.big else 0.45)), yr, font=self.f_year, fill=tuple(int(v * 0.3 * k) for v in c), anchor="mm")
        i = int(t * FS)
        seg = audio[max(0, i - 1100):i, 0] if i > 0 else np.zeros(1)
        if len(seg) > 2:
            xs = np.linspace(W * 0.06, W * 0.94, len(seg))
            mid = (y1 - y0) * ((0.5 + 0.3 * card) if a == 0 else 0.82)      # under the end card's lines
            amp = (y1 - y0) * ((0.36 - 0.24 * card) if a == 0 else 0.14)
            g.line(list(zip(xs, mid - seg * amp)), fill=tuple(int(c * (1 - (0.75 if self.big else 1.0) * card)) for c in trace), width=4)   # the square has no room under the card
        im.paste(Image.blend(glow, glow.filter(ImageFilter.GaussianBlur(9)), 0.5), (0, y0))
        lit = glow.filter(ImageFilter.GaussianBlur(22))
        base = im.crop((0, y0, W, y1))
        im.paste(Image.fromarray(np.minimum(255, np.asarray(base, np.int16) + np.asarray(lit, np.int16) * 1.4).astype(np.uint8)), (0, y0))
        d = ImageDraw.Draw(im)
        spaced(d, (W / 2, self.title_y), "SCINTILLA", self.f_title, (240, 240, 245), 22 if self.big else 16)
        sub = "the 1981 Elka Synthex, reborn on an M-VAVE FM-1"
        d.text((W / 2, self.title_y + (165 if self.big else 115)), sub, font=self.f_sub, fill=(150, 150, 160), anchor="mt")
        sec = [s for s0, s in SECTIONS if t >= s0][-1]
        spaced(d, (W / 2, y1 - (80 if self.big else 58)), sec, self.f_sec, tuple(int(c * (1 - card)) for c in (trace if real else (255, 154, 60))), 10)
        for c0, c1, line, small in CLAIMS:
            if c0 <= t < c1:
                k = max(0.0, min(1.0, (t - c0) / 0.25, (c1 - t) / 0.25))
                top = y0 + (70 if self.big else 4)
                if line:
                    spaced(d, (W / 2, top), line, self.f_sec, tuple(int(c * k) for c in (240, 240, 245)), 8 if self.big else 5)
                if small and (self.big or not line):
                    d.text((W / 2, top + (78 if self.big else 6)), small, font=self.f_sub, fill=tuple(int(c * k) for c in (170, 170, 180)), anchor="mt")
        if card > 0:
            cy = (y0 + y1) / 2
            spaced(d, (W / 2, cy - (90 if self.big else 62)), CALL, self.f_sec, tuple(int(c * card) for c in (240, 240, 245)), 10)
            d.text((W / 2, cy + (20 if self.big else 12)), REPO, font=self.f_sub, fill=tuple(int(c * card) for c in (255, 154, 60)), anchor="mt")
        p = pan.resize((W, round(pan.height * W / pan.width)), Image.Resampling.LANCZOS)
        im.paste(p, (0, self.panel_y))
        if self.foot_y:
            d.text((W / 2, self.foot_y), "real firmware in fm1-emu, levels matched  ·  not affiliated with Elka",
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
    import wave
    audio = balance(audio)
    if HW:                                                   # his three notes, as loud as Scintilla's
        with wave.open(HW) as w:
            assert w.getframerate() == FS, "the recording at 44.1 kHz"
            w.setpos(int(HW_AT * FS))
            h = np.frombuffer(w.readframes(int(HW_LEN * FS)), np.int16).reshape(-1, w.getnchannels()).astype(float).mean(1) / 32768
        i, j, k = int(SC_T * FS), int(HW_T * FS), int(0.04 * FS)
        h *= np.sqrt(np.mean(audio[i:i + len(h)] ** 2)) / np.sqrt(np.mean(h ** 2))
        h[:k] *= np.linspace(0, 1, k)
        h[-k:] *= np.linspace(1, 0, k)
        audio[j:j + len(h)] += h[:, None]
    wav = OUT / "audio.wav"
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
    for name, fr in (("scintilla-short" + ("-ab" if HW else ""), Frame(1080, 1920, 150, (430, 1120), 1150, 1860, True)),
                     ("scintilla-square" + ("-ab" if HW else ""), Frame(1080, 1080, 34, (190, 388), 388, 0, False))):
        mp4 = OUT / f"{name}.mp4"
        ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                               "-s", f"{fr.w}x{fr.h}", "-r", str(FPS), "-i", "-", "-i", str(wav),
                               "-c:v", "libx264", "-preset", "slow",
                               "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                               "-movflags", "+faststart", "-shortest", str(mp4)], stdin=subprocess.PIPE)
        cur = None
        for i in range(int(END * FPS)):
            t = i / FPS
            ms = max(700, round(1000 * int(t * pfps) / pfps))      # from the first frame the panel with its preset up
            if cur is None or cur[0] != ms:
                cur = (ms, Image.open(pngs[ms]).convert("RGB"))
            ff.stdin.write(fr.draw(t, cur[1], view).tobytes())
        ff.stdin.close()
        if ff.wait():
            sys.exit("ffmpeg failed")
        print(f"{mp4}: {fr.w}x{fr.h}, {END:.1f} s")


main()
