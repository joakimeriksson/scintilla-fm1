#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Scintilla in fm1-emu's fm1-live (headless, JIT), as the FM-1 runs it: the sound and the screen.

  tests/emu.py [--ms 3000] [--keys SCRIPT] [--out build/emu/run] [--fwsc build/scintilla.fwsc]
      -> OUT/audio.wav and OUT/panel.png (the whole panel, the screen in it, at the end)

SCRIPT is fm1-live's FM1_BENCH_KEYS: `ms:id` presses a key or a button by id (`ms:id^` releases;
keys are 14 + k, k = 0 for F3 .. 26 for G5; buttons by their BTN_ number), `ms:eN:clicks` turns
encoder N (0 SELECT, 1 ALGORITHM, 2..5 KNOB1..4, 6 PRESETS), `ms:mHEX` sends MIDI bytes.
FM1_LIVE: fm1-live (default ~/work/fm1-emu/target/release/fm1-live)."""
import argparse, os, struct, subprocess, sys, tempfile, wave
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
LIVE = Path(os.environ.get("FM1_LIVE", Path.home() / "work/fm1-emu/target/release/fm1-live"))


def run(keys, ms, out, fwsc=SRC / "build" / "scintilla.fwsc", ram=False):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, FM1_BENCH_KEYS=keys)
    with tempfile.TemporaryDirectory() as wd:
        (Path(wd) / "work").mkdir()
        raw = Path(wd) / "audio.raw"
        r = subprocess.run([str(LIVE), "--fwsc", str(fwsc), "--bench", str(ms)], cwd=wd, capture_output=True,
                           text=True, env=dict(env, FM1_BENCH_WAV=str(raw)))
        if r.returncode or not raw.exists():
            sys.exit(f"fm1-live --bench failed:\n{r.stdout[-2000:]}{r.stderr[-2000:]}")
        pcm = raw.read_bytes()
        with wave.open(str(out / "audio.wav"), "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100); w.writeframes(pcm)
        env2 = dict(env, FM1_DUMPRAM=str(out / "ram.bin")) if ram else env
        r2 = subprocess.run([str(LIVE), "--fwsc", str(fwsc), "--shot", str(ms)], cwd=wd, capture_output=True,
                            text=True, env=env2)
        log = r.stdout + r.stderr + r2.stdout + r2.stderr
        from PIL import Image
        img = Image.open(Path(wd) / "work" / "panel.ppm")
        img.save(out / "panel.png")
    s = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    return s, log


def peaks(s, step=0.25):
    n = int(44100 * step)
    return [max((abs(x) for x in s[2 * t:2 * (t + n)]), default=0) for t in range(0, len(s) // 2, n)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ms", type=int, default=3000)
    ap.add_argument("--keys", default="")
    ap.add_argument("--out", default=str(SRC / "build" / "emu" / "run"))
    ap.add_argument("--fwsc", default=str(SRC / "build" / "scintilla.fwsc"))
    a = ap.parse_args()
    s, log = run(a.keys, a.ms, a.out, a.fwsc)
    for ln in log.splitlines():
        if "halt" in ln or "crash" in ln.lower() or "emulated at" in ln:
            print(ln)
    print(f"{a.out}: {len(s) // 2 / 44100:.2f} s; peak per 0.25 s: {' '.join(map(str, peaks(s)))}")
