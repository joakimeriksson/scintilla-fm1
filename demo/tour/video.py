#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""The forty presets on Scintilla, each with how close it comes to the Synthex it was tuned towards.

    demo/tour/video.py HW.wav [--ab] [--only 10,46]
      -> build/tour/scintilla-presets.mp4      1920x1080, Scintilla alone
         build/tour/scintilla-presets-ab.mp4   with --ab: each stretch of the recording first (for us, not
                                               for publishing: the recording is Per Kristian's)

HW.wav is Per Kristian Risvik's run-through of the Synthex's ROM presets ("Elka Synthex - Presets",
perkristian.net) at 44.1 kHz: ffmpeg -i "Elka Synthex - Presets.mp3" -ar 44100 hw.wav. For each preset
the real firmware in fm1-live plays the notes transcribe.py found in a stretch of it (from marks.tsv, at
the passage scorecard.tsv scored), on the same preset. Each stretch is set to the same loudness; the
sound is otherwise unedited. The number under the name is the difference between the recording's
stretch and Scintilla's third-octave spectra, level-free, in dB rms. Ring mod. closes with the laser harp
phrase of demo/ad/video.py.
FM1_LIVE: fm1-live (default ~/work/fm1-emu/target/release/fm1-live)."""
import csv, os, re, subprocess, sys, time, wave
os.environ.setdefault("OMP_NUM_THREADS", "1")
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import transcribe as T

ROOT = T.ROOT
FWSC = ROOT / "firmware/build/scintilla.fwsc"
LIVE = Path(os.environ.get("FM1_LIVE", Path.home() / "work/fm1-emu/target/release/fm1-live"))
OUT = ROOT / "build/tour"
FS, FPS, PANEL_MS = 44100, 30, 40
L, L_SLOW = 3.0, 4.5                       # a stretch; the slow sweeps get longer
SLOW = {16, 26, 29, 40, 41, 42, 43, 44, 47}
# by hand, where the transcription misses what a slow sweep's first seconds play: (on, off, key)
HAND = {42: [(0.12, 4.5, 36)],              # Take-off: the C2 at 682.14 s (tools/synthex-rom/README.md), held
        43: [(0.05, 4.5, 41)]}              # Landing: its note sounds from the stretch's start
PIN = {46: 789.6}                          # Ring mod.: the riff the tuning page shows (13:10)
INTRO, GAP, NEXT, OUTRO = 4.0, 0.35, 0.6, 6.0
LEVEL = 10 ** (-20 / 20)                    # every stretch's rms
REPO = "github.com/joakimeriksson/scintilla-fm1"
AB = "--ab" in sys.argv                     # the recording's stretch before each of Scintilla's
CREDIT = "tuned towards Per Kristian Risvik's Synthex recording"

# the laser harp (demo/ad/video.py): (beat, beats, note) at 64 BPM on preset 46
BEAT = 60 / 64
HARP = [(0, 3, 48), (3, 0.25, 47), (3.25, 0.5, 46), (3.75, 3.25, 44),
        (7, 0.25, 51), (7.25, 0.5, 50), (7.75, 3.25, 48)]
HARP_LEN = max(b + d for b, d, _ in HARP) * BEAT + 1.2


def t_of(s):
    m, x = s.split(":")
    return 60 * int(m) + float(x)


def stretch(hw, a, b, p, ln):
    """Where the stretch starts: on a clear note onset inside the preset's mark (a, b), the one whose
    stretch sounds most of its time (no pause in the playing), the nearest to p (the passage the
    scorecard scored) among the ones that sound within 5 % of the best."""
    x = T.read_wav(hw, a, b - a)
    S = np.log(T.spec(x) + 1e-6)
    fps = FS / T.HOP
    flux = np.convolve(np.maximum(0, np.diff(S, axis=1)).sum(0), np.ones(3) / 3, "same")
    e = 10 * np.log10((np.exp(S) ** 2).sum(0) + 1e-12)
    loud = e > np.percentile(e, 95) - 25
    n = int(ln * fps)
    top = flux.max()
    peaks = [k for k in range(3, len(flux) - n) if flux[k] > 0.4 * top and flux[k] == flux[k - 3:k + 4].max()]
    if not peaks:
        return min(p, b - ln)
    sound = {k: loud[k:k + n].mean() for k in peaks}
    best = max(sound.values())
    k = min((k for k in peaks if sound[k] >= best - 0.05), key=lambda k: abs(a + k / fps - p))
    return a + max(0, k - 4) / fps


def plan(hw, only):
    marks = list(csv.DictReader(open(ROOT / "demo/tour/marks.tsv"), delimiter="\t"))
    score = {r["slot"]: r for r in csv.DictReader(open(ROOT / "demo/tour/scorecard.tsv"), delimiter="\t")}
    notes_dir = OUT / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    segs, t = [], INTRO
    for m in marks:
        slot = int(m["slot"])
        if only and slot not in only:
            continue
        a, b = float(m["start_s"]), float(m["end_s"])
        ln = L_SLOW if slot in SLOW else L
        p = max(a, t_of(score[m["slot"]]["passage_at"])) if m["slot"] in score else a
        st = PIN.get(slot) or stretch(hw, a, b, p, ln)
        nf = notes_dir / f"{slot}-{st:.2f}-{ln}.txt"
        if slot in HAND:
            nf.write_text(T.scenario(HAND[slot], ln))
        elif not nf.exists():
            S = T.spec(T.read_wav(hw, st, ln))
            nf.write_text(T.scenario(T.notes(T.activations(S, T.templates(slot, ln if slot in SLOW else 0.8))), ln))
        evs = []
        for l in nf.read_text().splitlines():
            w = l.split()
            if w[0] in ("on", "off"):
                evs.append((float(w[1]), w[0], int(w[2])))
        if AB:
            segs.append(dict(slot=slot, name=m["name"], hw_at=st, len=ln, t_hw=t, t_sc=t + ln + GAP, evs=evs))
            t += 2 * ln + GAP + NEXT
        else:                                   # t_hw: the preset's title (and its program change) only
            segs.append(dict(slot=slot, name=m["name"], hw_at=st, len=ln, t_hw=t, t_sc=t + 0.3, evs=evs))
            t += 0.3 + ln + NEXT
    harp = None
    if not only or 46 in only:
        harp = dict(t=t + 0.4)
        t += 0.4 + HARP_LEN + 0.6
    return segs, harp, t + OUTRO


def midi(segs, harp):
    ev = []
    for s in segs:
        ev.append((s["t_hw"], f"mc0{s['slot'] - 10:02x}"))
        for at, w, k in s["evs"]:
            at = min(at, s["len"] - 0.05)
            ev.append((s["t_sc"] + at, f"m90{k:02x}64" if w == "on" else f"m80{k:02x}00"))
    if harp:
        ev.append((harp["t"] - 0.3, "mc024"))
        for b, d, n in HARP:
            ev += [(harp["t"] + b * BEAT, f"m90{n:02x}7f"), (harp["t"] + (b + d) * BEAT - 0.02, f"m80{n:02x}00")]
    ev.sort(key=lambda e: (e[0], e[1][:3] != "m80"))     # at one time: note-offs first
    return ",".join(f"{round(t * 1000)}:{m}" for t, m in ev)


def shrink(ppm):
    """A panel frame as a JPEG at the size the video shows it: a 5 min film of PPMs is 25 GB."""
    im = Image.open(ppm).convert("RGB")
    im.resize((PANEL_W, round(im.height * PANEL_W / im.width)), Image.Resampling.LANCZOS).save(ppm.with_suffix(".jpg"), quality=92)
    ppm.unlink()


def film(keys, end, d):
    """The firmware's run: its sound, and its panel every PANEL_MS as d/fr/NNNNNN.jpg (shrunk while it runs)."""
    (Path(d) / "work").mkdir(exist_ok=True)
    fr = Path(d) / "fr"
    logf = open(Path(d) / "live.log", "w+")
    p = subprocess.Popen([str(LIVE), "--fwsc", str(FWSC), "--bench", str(round(end * 1000))], cwd=d,
                         stdout=logf, stderr=subprocess.STDOUT,
                         env=dict(os.environ, FM1_BENCH_KEYS=keys, FM1_BENCH_FRAMES=f"{fr},{PANEL_MS}"))
    while p.poll() is None:
        for ppm in sorted(fr.glob("*.ppm"))[:-1]:          # the newest may be half written
            shrink(ppm)
        time.sleep(0.2)
    for ppm in sorted(fr.glob("*.ppm")):
        try:
            shrink(ppm)
        except OSError:                                    # the last frame, cut off when the run ended
            ppm.unlink()
    logf.seek(0)
    log = logf.read()
    if p.returncode or "halt" in log:
        sys.exit(f"fm1-live failed:\n{log[-3000:]}")
    t0 = float(re.search(r"audio from ([0-9.]+) ms", log).group(1)) / 1000
    a = np.frombuffer((fr / "audio.raw").read_bytes(), np.int16).reshape(-1, 2).astype(float) / 32768
    return np.vstack([np.zeros((round(t0 * FS), 2)), a])


def third(x):
    S = T.spec(x) ** 2
    return 10 * np.log10(np.add.reduceat(S, np.arange(0, S.shape[0], 12), 0).sum(1) + 1e-12)


def closeness(h, e):
    a, b = third(h), third(e)
    keep = a > a.max() - 50
    d = (a - b)[keep]
    return float(np.sqrt(np.mean((d - d.mean()) ** 2)))


def fit(x, fade=0.04, out=None, k=None):
    """A stretch at LEVEL rms (measured on its first k samples), with short fades so a cut does not
    click; out: a longer fade at the end (a release let ring)."""
    x = x * (LEVEL / (np.sqrt(np.mean(x[:k] ** 2)) + 1e-12))
    n, m = int(fade * FS), int((out or fade) * FS)
    r = np.ones(len(x))
    r[:n], r[-m:] = np.linspace(0, 1, n), np.linspace(1, 0, m)
    return x * r[:, None]


def font(name, size):
    for p in (f"/System/Library/Fonts/Supplemental/{name}", f"/System/Library/Fonts/{name}"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def spaced(d, xy, text, f, fill, track, center=False):
    w = sum(d.textlength(c, font=f) for c in text) + track * (len(text) - 1)
    x, y = xy
    x -= w / 2 if center else 0
    for c in text:
        d.text((x, y), c, font=f, fill=fill)
        x += d.textlength(c, font=f) + track


def mix(c, k):
    return tuple(int(v * k) for v in c)


W, H = 1920, 1080
BG, FG, MUTED, AMBER, LED, LEDBG = (10, 10, 13), (238, 236, 230), (128, 126, 120), (255, 154, 60), (255, 64, 40), (30, 14, 12)
F_TITLE, F_SUB, F_NAME = font("Futura.ttc", 64), font("Avenir Next.ttc", 30), font("Futura.ttc", 92)
F_LED, F_SRC, F_SMALL, F_NUM = font("Futura.ttc", 120), font("Futura.ttc", 34), font("Avenir Next.ttc", 24), font("Futura.ttc", 60)
PANEL_W = 1000
PANEL_XY = (W - PANEL_W - 50, 330)


def draw(t, pan, view, segs, harp, end, scores):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    fade = max(0.0, min(1.0, (end - t) / 0.8))
    cur = next((s for s in reversed(segs) if t >= s["t_hw"] - 0.05), None)
    in_harp = harp and t >= harp["t"] - 0.4
    card = max(0.0, min(1.0, (t - (end - OUTRO + 0.4)) / 0.5))
    intro = t < INTRO - 0.1

    # the wordmark, always
    spaced(d, (60, 48), "SCINTILLA", F_TITLE, FG, 14)
    d.text((62, 128), "the Elka Synthex's forty factory presets, " + ("against the 1981 original" if AB else "on an M-VAVE FM-1"),
           font=F_SUB, fill=MUTED)

    # the FM-1, playing
    p = pan
    im.paste(p, PANEL_XY)
    d.text((PANEL_XY[0] + PANEL_W / 2, PANEL_XY[1] + p.height + 14), "M-VAVE FM-1 running Scintilla: the real firmware in fm1-emu",
           font=F_SMALL, fill=MUTED, anchor="mt")

    # the scope over the panel, coloured by who plays
    i = int(t * FS)
    seg = view[max(0, i - 1500):i]
    src = None
    if AB and cur and cur["t_hw"] <= t < cur["t_hw"] + cur["len"]:
        src = "hw"
    elif cur and cur["t_sc"] <= t < cur["t_sc"] + cur["len"] or in_harp:
        src = "sc"
    glow = Image.new("RGB", (PANEL_W, 140), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    if len(seg) > 2 and src:
        xs = np.linspace(10, PANEL_W - 10, len(seg))
        g.line(list(zip(xs, 70 - np.clip(seg, -1, 1) * 62)), fill=FG if src == "hw" else AMBER, width=4)
    glow = Image.blend(glow, glow.filter(ImageFilter.GaussianBlur(6)), 0.45)
    im.paste(glow, (PANEL_XY[0], 180))

    x0 = 60
    if intro:
        a = min(1.0, t / 0.4)
        spaced(d, (x0, 300), "40 PRESETS", F_NAME, mix(FG, a), 6)
        lines = (["First the Synthex itself:", "Per Kristian Risvik's recording of his.",
                  "Then Scintilla on an FM-1,", "the same notes, the same preset."] if AB else
                 ["Each one tuned towards", "Per Kristian Risvik's recording of a real 1981 Synthex,",
                  "played on an FM-1 by Scintilla,", "and how close it comes."])
        for k, l in enumerate(lines):
            d.text((x0, 440 + 52 * k), l, font=F_SUB, fill=mix(FG if k % 2 == 0 else MUTED, a))
    elif cur and not in_harp and card == 0:
        s = cur
        # the program display: two red digits, as on the Synthex
        d.rounded_rectangle([x0, 230, x0 + 230, 380], 6, fill=LEDBG)
        d.text((x0 + 115, 305), f"{s['slot']}", font=F_LED, fill=LED, anchor="mm")
        b, pg = divmod(s["slot"] - 10, 10)
        d.text((x0 + 260, 250), f"BANK {b + 1}  ·  PROGRAM {pg}", font=F_SMALL, fill=MUTED)
        d.text((x0 + 258, 280), s["name"].upper(), font=F_NAME if d.textlength(s["name"].upper(), font=F_NAME) < 560 else F_NUM, fill=FG)
        # the two sources
        rows = ((("hw", "1981 ELKA SYNTHEX", "recording: Per Kristian Risvik, perkristian.net"),
                 ("sc", "SCINTILLA ON FM-1", "the same notes, transcribed from his")) if AB else
                (("sc", "SCINTILLA ON FM-1", CREDIT),))
        for k, (key, label, by) in enumerate(rows):
            y = 450 + 120 * k
            on = src == key
            done = (key == "hw" and t >= s["t_hw"] + s["len"]) or (key == "sc" and t >= s["t_sc"] + s["len"])
            col = (AMBER if key == "sc" else FG) if on else MUTED
            d.ellipse([x0, y + 8, x0 + 26, y + 34], fill=col if on else None, outline=col, width=3)
            spaced(d, (x0 + 46, y), label, F_SRC, col, 4)
            d.text((x0 + 48, y + 48), by, font=F_SMALL, fill=MUTED)
            st = s["t_hw"] if key == "hw" else s["t_sc"]
            prog = max(0.0, min(1.0, (t - st) / s["len"]))
            d.rounded_rectangle([x0 + 48, y + 86, x0 + 700, y + 92], 3, fill=(40, 40, 46))
            if prog > 0:
                d.rounded_rectangle([x0 + 48, y + 86, x0 + 48 + 652 * prog, y + 92], 3, fill=col if not done else mix(col, 0.6))
        # how close: shown once Scintilla has played
        if t >= s["t_sc"] + s["len"] * 0.6:
            a = min(1.0, (t - s["t_sc"] - s["len"] * 0.6) / 0.3)
            v = scores[s["slot"]]
            d.text((x0, 720), "SPECTRUM DIFFERENCE" + ("" if AB else " TO THE REAL SYNTHEX"), font=F_SMALL, fill=mix(MUTED, a))
            d.text((x0, 752), f"{v:.1f} dB", font=F_NUM, fill=mix(AMBER, a))
            d.text((x0 + 260, 776), "third-octave, level-free, rms", font=F_SMALL, fill=mix(MUTED, a))
    if in_harp and card == 0:
        a = min(1.0, (t - harp["t"] + 0.4) / 0.4)
        spaced(d, (x0, 260), "THE LASER HARP", F_NAME, mix(AMBER, a), 4)
        d.text((x0, 380), "Preset 46, Ring mod.: the Synthex sound of", font=F_SUB, fill=mix(FG, a))
        d.text((x0, 422), "Jean-Michel Jarre's laser harp, on an FM-1.", font=F_SUB, fill=mix(FG, a))
        # the fan of beams, a note a hand in its beam (demo/ad/video.py)
        order = sorted({n for _, _, n in HARP})
        beams = Image.new("RGB", (800, 360), (0, 0, 0))
        bd = ImageDraw.Draw(beams)
        ox, oy = 400, 360
        for k in range(len(order)):
            cut = 1.0
            for b, du, n in HARP:
                if order.index(n) == k and harp["t"] + b * BEAT <= t < harp["t"] + (b + du) * BEAT - 0.02:
                    cut = 0.42 + 0.06 * (k % 3)
            bx = 400 + (k - (len(order) - 1) / 2) * 120
            hx, hy = ox + (bx - ox) * cut, oy * (1 - cut)
            bd.line([(ox, oy), (hx, hy)], fill=mix((40, 255, 90), a), width=6)
            if cut < 1:
                bd.ellipse([hx - 13, hy - 13, hx + 13, hy + 13], fill=mix((190, 255, 200), a))
        beams = Image.blend(beams, beams.filter(ImageFilter.GaussianBlur(10)), 0.5)
        base = np.asarray(im.crop((x0, 520, x0 + 800, 880)), np.int16)
        im.paste(Image.fromarray(np.minimum(255, base + np.asarray(beams, np.int16)).astype(np.uint8)), (x0, 520))
        d = ImageDraw.Draw(im)
    if card > 0:
        spaced(d, (x0, 300), "FREE & OPEN SOURCE", F_NUM, mix(FG, card), 6)
        d.text((x0, 400), REPO, font=F_SUB, fill=mix(AMBER, card))
        d.text((x0, 460), "for the M-VAVE FM-1, from the Firmware Hub", font=F_SUB, fill=mix(MUTED, card))

    # where we are: forty dots
    if segs and not intro:
        for k, s in enumerate(segs):
            cx = x0 + 18 * k
            lit = cur is s and not in_harp
            d.ellipse([cx, 900, cx + 10, 910], fill=LED if lit else ((90, 40, 34) if t > s["t_hw"] else (40, 40, 46)))
    d.text((W / 2, H - 46), ("levels matched, sound otherwise unedited" if AB else
                             "the Synthex recording: Per Kristian Risvik, perkristian.net  ·  sound unedited but for the level")
           + "  ·  not affiliated with Elka or Jean-Michel Jarre",
           font=F_SMALL, fill=(96, 96, 104), anchor="mt")
    return im if fade >= 1 else Image.eval(im, lambda v: int(v * fade))


def main():
    hw = sys.argv[1]
    only = {int(s) for s in sys.argv[sys.argv.index("--only") + 1].split(",")} if "--only" in sys.argv else None
    OUT.mkdir(parents=True, exist_ok=True)
    segs, harp, end = plan(hw, only)
    print(f"{len(segs)} presets, {end:.1f} s")
    d = OUT / "film"
    subprocess.run(["rm", "-rf", str(d)], check=True)
    d.mkdir()
    sc = film(midi(segs, harp), end, d)
    frames = sorted((d / "fr").glob("*.jpg"))
    # the sound track: each stretch at the same loudness, the hardware's from the recording
    n = int(end * FS)
    track = np.zeros((n, 2))
    scores = {}
    for s in segs:
        k = int(s["len"] * FS)
        h = T.read_wav(hw, s["hw_at"], s["len"])
        with wave.open(hw) as w:
            w.setpos(int(s["hw_at"] * FS))
            h2 = np.frombuffer(w.readframes(k), np.int16).reshape(-1, 2).astype(float) / 32768
        i, j = int(s["t_hw"] * FS), int(s["t_sc"] * FS)
        e2 = sc[j:j + k]
        scores[s["slot"]] = closeness(h, e2.mean(1))
        if AB:
            track[i:i + len(h2)] += fit(h2)
            track[j:j + len(e2)] += fit(e2)
        else:                                   # alone, the last notes' release rings into the gap
            e3 = sc[j:j + k + int(0.4 * FS)]
            track[j:j + len(e3)] += fit(e3, out=0.35, k=k)
        print(f"  {s['slot']} {s['name']:18} at {s['hw_at']:6.1f} s  {len(s['evs']) // 2:2d} notes  {scores[s['slot']]:4.1f} dB")
    if harp:
        i = int((harp["t"] - 0.1) * FS)
        k = int((HARP_LEN + 0.2) * FS)
        track[i:i + k] += fit(sc[i:i + k], 0.1) * 1.2
    peak = np.abs(track).max()
    track *= min(1.0, 10 ** (-1 / 20) / peak)
    wav = OUT / "audio.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(FS)
        w.writeframes(np.round(track * 32767).astype(np.int16).tobytes())
    view = track.mean(1) / (np.abs(track).max() + 1e-9)
    mp4 = OUT / ("scintilla-presets-ab.mp4" if AB else "scintilla-presets.mp4")
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart",
                           "-shortest", str(mp4)], stdin=subprocess.PIPE)
    pan, shown = None, -1
    for f in range(int(end * FPS)):
        t = f / FPS
        k = min(len(frames) - 1, int(t * 1000 / PANEL_MS))
        if k != shown:
            pan, shown = Image.open(frames[k]).convert("RGB"), k
        ff.stdin.write(draw(t, pan, view, segs, harp, end, scores).tobytes())
    ff.stdin.close()
    if ff.wait():
        sys.exit("ffmpeg failed")
    print(f"{mp4}: {W}x{H}, {end:.1f} s")


if __name__ == "__main__":
    main()
